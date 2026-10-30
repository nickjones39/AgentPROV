"""D-554: memory admission for the T1 pools.

The controller only delays jobs: one FIFO across every pool with head-of-line blocking, idle workers counted at their
footprint, a job larger than the budget admitted alone, waiters woken by an abort. A pool with a charge policy gives the
same results as one without, whatever the budget; a worker that peaked above the retire threshold is replaced.
"""

from __future__ import annotations

import threading
import time

import pytest

from agentprov.host import Footprint
from agentprov.io import workers
from agentprov.io.workers import Job, WorkerPool, result_fingerprint

MIB = 1 << 20


class FakeMemory:
    def __init__(self) -> None:
        self.by_pid: dict[int, int] = {}

    def __call__(self, pid: int) -> Footprint | None:
        return Footprint(self.by_pid.get(pid, 0), None, "test")


def acquire_in_thread(adm: workers._Admission, charge: int, abort: threading.Event, out: list[object]) -> threading.Thread:
    t = threading.Thread(target=lambda: out.append(adm.acquire(charge, "prov", abort)))
    t.start()
    return t


def test_tickets_are_served_in_one_fifo_with_head_of_line_blocking() -> None:
    mem = FakeMemory()
    adm = workers._Admission(1000 * MIB, mem)
    abort = threading.Event()
    first = adm.acquire(600 * MIB, "prov", abort)
    assert first is not None
    big: list[object] = []
    small: list[object] = []
    tb = acquire_in_thread(adm, 600 * MIB, abort, big)  # does not fit while `first` runs
    time.sleep(0.1)
    ts = acquire_in_thread(adm, 100 * MIB, abort, small)  # would fit, but queues behind the head
    time.sleep(0.4)
    assert big == [] and small == []
    adm.release(first)
    tb.join(timeout=5)
    assert big and big[0] is not None
    ts.join(timeout=5)  # 600 + 100 <= 1000: admitted once the head is
    assert small and small[0] is not None


def test_idle_workers_count_at_their_footprint() -> None:
    mem = FakeMemory()
    adm = workers._Admission(1000 * MIB, mem)
    abort = threading.Event()
    first = adm.acquire(100 * MIB, "prov", abort)
    assert first is not None
    adm.bind(first, 4242)
    mem.by_pid[4242] = 800 * MIB  # its footprint is above its charge
    adm.release(first)  # the worker is idle now, still holding 800 MiB
    running = adm.acquire(50 * MIB, "map", abort)
    assert running is not None
    waiting: list[object] = []
    t = acquire_in_thread(adm, 300 * MIB, abort, waiting)
    time.sleep(0.4)
    assert waiting == []  # 800 (idle) + 50 + 300 > 1000
    adm.unregister(4242)  # the idle worker is retired
    t.join(timeout=5)
    assert waiting and waiting[0] is not None


def test_a_job_larger_than_the_budget_runs_alone() -> None:
    adm = workers._Admission(100 * MIB, FakeMemory())
    abort = threading.Event()
    huge = adm.acquire(4096 * MIB, "prov", abort)  # nothing runs: admitted although it exceeds the budget
    assert huge is not None
    other: list[object] = []
    t = acquire_in_thread(adm, 1 * MIB, abort, other)
    time.sleep(0.3)
    assert other == []
    adm.release(huge)
    t.join(timeout=5)
    assert other and other[0] is not None


def test_an_abort_wakes_every_waiter() -> None:
    adm = workers._Admission(100 * MIB, FakeMemory())
    abort = threading.Event()
    running = adm.acquire(90 * MIB, "prov", abort)
    assert running is not None
    waiting: list[object] = []
    t = acquire_in_thread(adm, 50 * MIB, abort, waiting)
    time.sleep(0.2)
    abort.set()
    adm.wake()
    t.join(timeout=5)
    assert waiting == [None] and not t.is_alive()


def test_the_overshoot_of_a_kind_is_recorded() -> None:
    mem = FakeMemory()
    adm = workers._Admission(1000 * MIB, mem)
    ticket = adm.acquire(100 * MIB, "validate", threading.Event())
    assert ticket is not None
    adm.bind(ticket, 7)
    mem.by_pid[7] = 130 * MIB
    adm.observe(ticket, 7)
    adm.release(ticket)
    assert adm.stats["overshoot"]["validate"] == pytest.approx(1.3)


def test_the_prov_charge_follows_the_model() -> None:
    assert workers.prov_charge(0) == int(1.25 * (47 + 3.6) * MIB)
    four = workers.prov_charge(4 * MIB)
    assert four == int(1.25 * (47 + 3.6 + 80.2 * 4) * MIB)
    assert workers.prov_charge(400 * MIB, cap=4 << 30) == 4 << 30
    assert workers.prov_charge(4 * MIB, hit="validate") < workers.prov_charge(4 * MIB, hit="prov") < four


# ---- pools ----------------------------------------------------------------------------------------------------------

JOBS = [Job(f"{k:03d}", "echo", params={"k": k, "members": [{"label": "m", "text": "x" * (k * 101)}]}) for k in range(8)]


def run(pool: WorkerPool) -> str:
    results = pool.run(JOBS)
    try:
        return result_fingerprint(results)
    finally:
        for r in results:
            r.close()


@pytest.fixture
def fresh_admission(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def install(budget: int) -> workers._Admission:
        from agentprov.host import footprint_reader

        adm = workers._Admission(budget, footprint_reader())
        monkeypatch.setattr(workers, "_ADMISSION", adm)
        return adm

    return install


def test_admission_never_changes_results(fresh_admission) -> None:  # type: ignore[no-untyped-def]
    plain = run(WorkerPool(workers=3, test_kinds=True))
    adm = fresh_admission(1 << 30)  # about one 512 MiB charge beside the parent and workers at a time
    gated = run(WorkerPool(workers=3, test_kinds=True, charge=lambda job, root: 512 * MIB))
    assert gated == plain
    assert adm.stats["admitted"] == len(JOBS) and adm.stats["waited"] >= 1


def test_a_worker_that_peaked_above_the_threshold_is_replaced(fresh_admission, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fresh_admission(64 << 30)
    monkeypatch.setattr(workers, "ADMISSION_RETIRE_PEAK", 1)  # every worker qualifies
    results = WorkerPool(workers=1, test_kinds=True, charge=lambda job, root: MIB).run(JOBS[:3])
    try:
        assert len({r.worker_pid for r in results}) == 3  # a fresh worker for every job
    finally:
        for r in results:
            r.close()


def test_without_a_policy_the_default_worker_count_is_unchanged() -> None:
    pool = WorkerPool(workers=0)
    assert pool.charge is None and pool.workers == workers.resolve_worker_count(0)


def test_with_a_policy_the_default_is_every_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-415: a pool with a charge policy and ``workers=0`` gets one slot per logical CPU; ``--jobs`` still wins."""
    import dataclasses

    from agentprov.host import detect_host

    host = dataclasses.replace(detect_host(probe=False), cpu_count=12)
    policy = lambda job, root: MIB  # noqa: E731
    assert WorkerPool(workers=0, charge=policy, host=host).workers == 12
    assert WorkerPool(workers=3, charge=policy, host=host).workers == 3
    assert WorkerPool(workers=0, host=host).workers == workers.resolve_worker_count(0, profile=host)
    monkeypatch.setattr(workers, "ADMISSION_DEFAULT_SLOTS", None)
    assert WorkerPool(workers=0, charge=policy, host=host).workers == workers.resolve_worker_count(0, profile=host)
    monkeypatch.setattr(workers, "ADMISSION_DEFAULT_SLOTS", 5)
    assert WorkerPool(workers=0, charge=policy, host=host).workers == 5


def test_a_failed_spawn_releases_its_admission_ticket(fresh_admission, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Pre-round review D #12: a ticket admitted for a job whose worker could not be started (Popen EMFILE, a mkdtemp
    failure) stayed in ``_running``, so a later pool's job that fits the budget alone waited forever."""
    adm = fresh_admission(1 << 30)
    real_init = workers._Worker.__init__
    calls = {"n": 0}

    def failing_init(self, pool):  # type: ignore[no-untyped-def]
        if pool.charge is not None:  # the internal calibration pool (no charge) spawns first: let it
            calls["n"] += 1
            if calls["n"] == 1:  # the first worker of a charged pool, after its job was admitted
                raise OSError(24, "Too many open files (simulated spawn failure)")
        real_init(self, pool)

    monkeypatch.setattr(workers._Worker, "__init__", failing_init)
    with pytest.raises(OSError):
        WorkerPool(workers=1, test_kinds=True, charge=lambda job, root: 600 * MIB).run(JOBS[:1])
    assert calls["n"] == 1 and adm.stats["admitted"] == 1  # the ticket was taken before the spawn failed
    assert adm._running == {}
    done: list[str] = []
    second = threading.Thread(
        target=lambda: done.append(run(WorkerPool(workers=1, test_kinds=True, charge=lambda job, root: 700 * MIB))),
        daemon=True,
    )
    second.start()
    second.join(timeout=60)
    assert done, "a job that fits the budget alone never started"
