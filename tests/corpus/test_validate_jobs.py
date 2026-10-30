"""D-413: ``validate --corpus`` with T1 ``validate`` jobs gives the in-process result byte for byte.

Each case validates the same corpus copy in process (``jobs=None``) and with workers (``jobs=1`` and ``jobs=3``). It
compares the report document's JSON bytes, which hold every row, the counters, the failures, the notices, the summary
and the D-40 ``validation`` member. Cases:
- every tier in each mode;
- each tier alone;
- a seeded sample;
- a tampered PROV file;
- a removed SEM file;
- an AER that cannot be read;
- an unresolvable semantics profile (through an in-process pool, which sees the patch);
- the parent's exact verified buffers (TOCTOU);
- a killed worker.
"""

from __future__ import annotations

import functools
import json
import time
from pathlib import Path
from typing import Any

import pytest
import verify_support as vs

from agentprov.corpus import validation
from agentprov.corpus.reader import CorpusReader
from agentprov.corpus.validation import WORKER_CHECK, validate_corpus
from agentprov.io.workers import WorkerLimits


def report_bytes(root: Path, **kwargs: Any) -> bytes:
    outcome = validate_corpus(CorpusReader.open(root), **kwargs)
    return json.dumps(outcome.report({"corpus_id": "x"}), sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8")


def assert_same_everywhere(root: Path, **kwargs: Any) -> bytes:
    baseline = report_bytes(root, jobs=None, **kwargs)
    for jobs in (1, 3):
        assert report_bytes(root, jobs=jobs, **kwargs) == baseline, f"jobs={jobs} differs from the in-process path"
    return baseline


@pytest.mark.parametrize("mode", ["dev", "release"])
def test_every_tier_in_each_mode(sealed: Path, mode: str) -> None:
    document = json.loads(assert_same_everywhere(sealed, mode=mode))
    assert document["counters"]["executions"] == 3


@pytest.mark.parametrize("tier", ["aer", "sem", "prov", "linkage"])
def test_each_tier_alone(sealed: Path, tier: str) -> None:
    assert_same_everywhere(sealed, tiers=(tier,), mode="release")


def test_a_seeded_sample(sealed: Path) -> None:
    document = json.loads(assert_same_everywhere(sealed, mode="release", sample=2, seed="7"))
    assert document["sample"]["n"] == 2


def test_a_tampered_prov_file(sealed: Path) -> None:
    prov = vs.first_file(sealed, "prov")
    prov.write_bytes(prov.read_bytes() + b" ")
    document = json.loads(assert_same_everywhere(sealed, mode="release"))
    assert document["counters"]["failed"] == 1


def test_a_removed_sem_file(sealed: Path) -> None:
    vs.first_file(sealed, "sem").unlink()
    document = json.loads(assert_same_everywhere(sealed, mode="release"))
    assert document["counters"]["failed"] == 1


def test_an_unreadable_aer(sealed: Path) -> None:
    aer = vs.first_file(sealed, "aer")
    aer.write_bytes(b"{}\n")
    document = json.loads(assert_same_everywhere(sealed, mode="release"))
    assert any(any(c.startswith("aer.read:") for c in f["checks"]) for f in document["failures"])


def test_an_unresolvable_semantics_profile(sealed: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A ref the package cannot resolve gives ``<ref>:profile = skipped`` in both paths. The worker sees the patch
    because the pool runs in process here (same dispatch and frame round trip, G.4.9)."""
    from agentprov.corpus import validation_job

    ref = CorpusReader.open(sealed).index()[0].sem
    assert ref
    unresolved = next(iter(ref))

    def refuse(name: str) -> Any:
        raise validation.AgentProvError(f"not shipped: {name}")

    monkeypatch.setattr(validation, "default_semantics_profile", refuse)
    monkeypatch.setattr(validation_job, "default_semantics_profile", refuse)
    monkeypatch.setattr(validation_job, "_PROFILES", {})
    monkeypatch.setattr(validation, "WorkerPool", functools.partial(validation.WorkerPool, in_process=True))
    baseline = report_bytes(sealed, jobs=None, mode="dev")
    assert report_bytes(sealed, jobs=2, mode="dev") == baseline
    rows = json.loads(baseline)["results"]
    assert all(row["checks"].get(f"{unresolved}:profile") == "skipped" for row in rows)


def test_jobs_get_the_verified_buffer_not_the_file_read_again(sealed: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TOCTOU (D-413 §3.3): the PROV file is changed right after the parent read it; the job validates what was read."""
    baseline = report_bytes(sealed, jobs=None, mode="release")
    real = CorpusReader.prov_bytes

    def read_then_tamper(self: CorpusReader, row: Any, spec: str) -> bytes:
        data = real(self, row, spec)
        path = self.root / row.prov_paths[spec]
        path.chmod(0o644)
        path.write_bytes(b"{}")  # the stored file no longer holds what was verified
        return data

    monkeypatch.setattr(CorpusReader, "prov_bytes", read_then_tamper)
    assert report_bytes(sealed, jobs=2, mode="release") == baseline


def test_a_killed_worker_fails_its_row_with_the_worker_check(sealed: Path) -> None:
    """A ``validate`` job over its RSS cap (forced to the 64 MiB floor here) is stopped; the row fails with
    ``validate.worker``, the limit code goes to a notice, and the run's exit is a failure, never a silent pass."""
    limits = WorkerLimits(kind_rss_bytes={"prov": 4 << 30, "validate": 64 << 20})
    outcome = validate_corpus(CorpusReader.open(sealed), jobs=1, mode="release", limits=limits)
    assert not outcome.ok
    for row in outcome.rows:
        assert row["checks"][WORKER_CHECK] == "fail" and row["verdict"] == "fail"
    assert all(f["checks"] == [WORKER_CHECK] for f in outcome.failures)
    assert any("worker.limit.rss" in notice for notice in outcome.notices)


def test_pipelined_batches_give_the_same_report(sealed: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """D-893: with one row per batch, the parent stages batch k+1 while the pool runs batch k; the report is still the
    in-process one, byte for byte, in each mode."""
    monkeypatch.setattr(validation, "POOL_BATCH", 1)
    for mode in ("dev", "release"):
        assert json.loads(assert_same_everywhere(sealed, mode=mode))["counters"]["executions"] == 3


def test_a_batch_never_loses_a_staged_input_to_the_previous_batch(sealed: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """D-893: every input of a batch is still in the staging store when its jobs start, although the previous batch is
    recorded (and its staged copies removed) meanwhile. A row's AER is staged twice here, so a removal by digest alone
    would take the next batch's copy too."""
    monkeypatch.setattr(validation, "POOL_BATCH", 1)
    rows = CorpusReader.open(sealed).index()
    monkeypatch.setattr(CorpusReader, "index", lambda self: [rows[0], rows[0], *rows[1:]])  # one AER in two batches
    real_run = validation.WorkerPool.run
    missing: list[str] = []

    def checked(self: Any, jobs: Any, progress: Any = None) -> Any:
        jobs = list(jobs)
        time.sleep(1.0)  # the previous one-row batch is recorded (and its staged copies removed) meanwhile
        for job in jobs:
            for item in job.inputs:
                sha = str(item["sha256"])
                if not list((Path(self.store_root) / sha[:2]).glob(sha + ".*")):
                    missing.append(sha)
        return real_run(self, jobs, progress)

    monkeypatch.setattr(validation.WorkerPool, "run", checked)
    outcome = validate_corpus(CorpusReader.open(sealed), jobs=2, mode="release")
    assert outcome.counters["executions"] == 4 and missing == []
