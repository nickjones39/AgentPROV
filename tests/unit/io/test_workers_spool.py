"""D-414: a pool keeps its results' frames as bytes, in memory under a pool-wide budget or in one spool file per batch.

Where an output sits (memory or the batch spool) depends on arrival order and is never observable: a batch run with the
budget at 0 (everything on disk) and unbounded gives the same results. One batch holds one descriptor, read with
``pread`` only, and a consumer that raises mid-batch leaks no descriptor and no file.
"""

from __future__ import annotations

import gc
import os
from pathlib import Path

import pytest

from agentprov.io import workers
from agentprov.io.workers import Job, WorkerPool, result_fingerprint

TEXTS = ["a" * 300, "b" * (3 << 20), "c", "d" * (70 << 10)]  # one member above MemberOutput.SPOOL_MAX (1 MiB)
SMALL = ["a" * 300, "b" * 5000, "c", "d" * 900]


def jobs(n: int, texts: list[str]) -> list[Job]:
    return [Job(f"{k:04d}", "echo", params={"k": k, "members": [{"label": f"m{i}", "text": t} for i, t in enumerate(texts)]})
            for k in range(n)]  # fmt: skip


def run(tmp_path: Path, n: int, budget: int, *, in_process: bool = True, texts: list[str] = TEXTS
        ) -> list[workers.JobResult]:
    pool = WorkerPool(workers=1 if in_process else 2, in_process=in_process, test_kinds=True, spool_dir=tmp_path)
    pool._budget = workers._Budget(budget)
    return pool.run(jobs(n, texts))


def read_all(results: list[workers.JobResult]) -> list[object]:
    out: list[object] = []
    for r in results:
        out.append([o.read_bytes() if isinstance(o, workers.MemberOutput) else dict(o) for o in r.iter_outputs()])
    return out


@pytest.mark.parametrize("in_process", [True, False])
def test_where_an_output_is_kept_is_never_observable(tmp_path: Path, in_process: bool) -> None:
    on_disk = run(tmp_path, 6, 0, in_process=in_process)
    in_memory = run(tmp_path, 6, 1 << 40, in_process=in_process)
    try:
        assert result_fingerprint(on_disk) == result_fingerprint(in_memory)
        assert read_all(on_disk) == read_all(in_memory)
        assert [r.json for r in on_disk] == [r.json for r in in_memory]
        assert any(m._batch is not None for r in on_disk for m in r.members)  # really spilled
        assert all(m._batch is None for r in in_memory for m in r.members if m.size <= workers.MemberOutput.SPOOL_MAX)
    finally:
        for r in (*on_disk, *in_memory):
            r.close()


def test_the_budget_is_returned_when_results_close(tmp_path: Path) -> None:
    pool = WorkerPool(workers=1, in_process=True, test_kinds=True, spool_dir=tmp_path)
    results = pool.run(jobs(3, SMALL))
    assert pool._budget.used > 0
    for r in results:
        r.close()
        r.close()  # idempotent
    assert pool._budget.used == 0


def test_a_full_batch_rolled_to_disk_holds_one_descriptor(tmp_path: Path) -> None:
    def open_fds() -> int:
        return len(os.listdir("/dev/fd"))

    before = open_fds()
    results = run(tmp_path, 256, 0, texts=SMALL)
    try:
        assert open_fds() - before <= 1  # one batch spool file for 256 results and their 1,024 members
        assert len({id(m._batch) for r in results for m in r.members}) == 1 and results[0].members[0]._batch is not None
    finally:
        for r in results:
            r.close()
    gc.collect()
    assert open_fds() <= before


def test_reads_of_one_batch_can_interleave(tmp_path: Path) -> None:
    results = run(tmp_path, 2, 0)
    try:
        a, b = results[0].members[1], results[1].members[1]
        ia, ib = a.iter_chunks(chunk_size=4096), b.iter_chunks(chunk_size=4096)
        got_a, got_b = [], []
        for chunk_a, chunk_b in zip(ia, ib, strict=False):  # alternate reads on the shared descriptor (pread only)
            got_a.append(chunk_a)
            got_b.append(chunk_b)
        got_a.extend(ia)
        got_b.extend(ib)
        assert b"".join(got_a) == a.read_bytes() and b"".join(got_b) == b.read_bytes()
        assert set(b"".join(got_a)) == {ord("b")}
    finally:
        for r in results:
            r.close()


def test_a_consumer_that_raises_mid_batch_leaks_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Deferrals' D-414 condition: the importer's ``for ... in zip(stored, pool.run(jobs))`` closes only the result in
    hand when it raises; the others are released when they are collected, and the batch file is closed."""
    spools: list[workers._BatchSpool] = []
    real = workers._BatchSpool

    class Recording(real):  # type: ignore[valid-type,misc]
        def __init__(self, directory):  # type: ignore[no-untyped-def]
            super().__init__(directory)
            spools.append(self)

    monkeypatch.setattr(workers, "_BatchSpool", Recording)

    def consume() -> None:
        for n, result in enumerate(run(tmp_path, 5, 0, texts=SMALL)):
            try:
                if n == 2:
                    raise RuntimeError("a consumer fails on the third result")
            finally:
                result.close()

    before = len(os.listdir("/dev/fd"))
    with pytest.raises(RuntimeError):
        consume()
    gc.collect()
    assert spools and all(s.closed for s in spools)
    assert len(os.listdir("/dev/fd")) <= before
    assert list(tmp_path.iterdir()) == []  # unlinked at creation: no file remains


def test_a_batch_that_spills_nothing_opens_no_file(tmp_path: Path) -> None:
    results = run(tmp_path, 3, 1 << 40, texts=SMALL)
    try:
        assert all(m._batch is None for r in results for m in r.members)
    finally:
        for r in results:
            r.close()
    assert list(tmp_path.iterdir()) == []
