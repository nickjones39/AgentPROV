"""Makes ``import_support`` (tests/adapters) and ``fetch_support`` (tests/unit/raw) importable for the pipeline tests."""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS = Path(__file__).resolve().parents[2]
for _path in (_TESTS / "adapters", _TESTS / "unit" / "raw"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import pytest  # noqa: E402

from agentprov.io import workers  # noqa: E402


class _GuardedResult(workers.JobResult):
    """D-414: a ``per_item`` or ``container`` map result must be read by the two streaming passes, never through ``.json``
    (which would decode and keep every frame)."""

    @property
    def json(self):  # type: ignore[no-untyped-def,override]
        raise AssertionError("D-414: a per_item or container map result was read through .json")


@pytest.fixture(autouse=True, params=["mem", "disk"])
def spool_budget(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Every pipeline test runs twice (D-414): with every output kept in memory, and with every output in the batch spool
    (the pool budget at 0). Where an output sits must never change a result. Per-item and container map results are
    guarded against ``.json``."""
    budget = 0 if request.param == "disk" else 1 << 40
    if request.param == "mem":
        monkeypatch.setattr(workers, "SPOOL_MEMORY_PER_JOB", 1 << 40)
    real_init, real_run = workers.WorkerPool.__init__, workers.WorkerPool.run

    def init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        real_init(self, *args, **kwargs)
        self._budget = workers._Budget(budget)

    def run(self, jobs, progress=None):  # type: ignore[no-untyped-def]
        batch = list(jobs)
        results = real_run(self, batch, progress)
        for job, result in zip(sorted(batch, key=lambda j: j.key), results, strict=True):
            if job.kind == "map" and (job.params.get("per_item") or job.params.get("mode") == "container"):
                result.__class__ = _GuardedResult
        return results

    monkeypatch.setattr(workers.WorkerPool, "__init__", init)
    monkeypatch.setattr(workers.WorkerPool, "run", run)
    return str(request.param)
