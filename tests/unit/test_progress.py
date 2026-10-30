"""``agentprov.progress`` and the worker pool's progress hook (MN N.1.14(6); DECISIONS D-8 F2).

Library code reports through the ``Progress`` sink and never prints. The pool reports one ``unit_done`` per job from its
collecting thread; a sink that raises or stalls must not change a result.
"""

from __future__ import annotations

import dataclasses
import threading
import time

import pytest

from agentprov.io.workers import Job, WorkerPool, result_fingerprint
from agentprov.progress import EVENT_KINDS, NULL_PROGRESS, FieldValue, NullProgress, Progress, ProgressEvent


class Collect:
    def __init__(self) -> None:
        self.events: list[ProgressEvent] = []
        self._lock = threading.Lock()

    def emit(self, event: ProgressEvent) -> None:
        with self._lock:
            self.events.append(event)


def jobs(n: int = 4) -> list[Job]:
    return [Job(f"job-{i:02d}", "echo", params={"n": i}) for i in range(n)]


def test_event_is_frozen_slotted_and_validates_its_kind():
    event = ProgressEvent("unit_done", unit="u", status="ok", codes=("a.b",), fields={"k": 1})
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.unit = "other"  # type: ignore[misc]
    assert not hasattr(event, "__dict__")
    with pytest.raises(ValueError):
        ProgressEvent("unknown")
    assert set(EVENT_KINDS) == {"start", "unit_start", "unit_done", "step", "trace",
                                "stage", "worker", "session", "control"}  # 0.2 adds the last four (D-393)


def test_default_fields_are_shared_and_read_only():
    a, b = ProgressEvent("step"), ProgressEvent("trace")
    assert a.fields is b.fields and len(a.fields) == 0
    with pytest.raises(TypeError):
        a.fields["x"] = 1  # type: ignore[index]


def test_null_progress_is_a_progress_and_discards_everything():
    sink: Progress = NULL_PROGRESS
    assert isinstance(sink, NullProgress)
    assert sink.emit(ProgressEvent("start")) is None
    assert FieldValue  # the scalar alias is part of the interface


def test_a_collector_satisfies_the_protocol():
    sink: Progress = Collect()
    sink.emit(ProgressEvent("step"))
    assert len(sink.events) == 1  # type: ignore[attr-defined]


def test_the_core_package_has_no_print_calls_outside_the_cli():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "agentprov"
    offenders = []
    for path in root.rglob("*.py"):
        parts = path.relative_to(root).parts
        if parts[0] == "cli" or path.name == "worker_testjobs.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    assert offenders == []


# ---------------------------------------------------------------------------------------------- the pool hook


def test_in_process_pool_reports_one_unit_done_per_job():
    sink = Collect()
    results = WorkerPool(in_process=True).run(jobs(3), progress=sink)
    assert [e.kind for e in sink.events] == ["unit_done"] * 3
    assert [e.unit for e in sink.events] == ["job-00", "job-01", "job-02"]
    assert all(e.status == "ok" and e.codes == () and e.duration_s is not None and e.duration_s >= 0 for e in sink.events)
    assert all(e.fields["kind"] == "echo" and e.fields["isolation"] == "in-process" for e in sink.events)
    assert len(results) == 3


def test_worker_pool_reports_status_duration_and_peak_rss_per_job():
    sink = Collect()
    pool = WorkerPool(workers=2, test_kinds=True)
    batch = [*jobs(3), Job("job-99-bad", "test.raise_error")]
    results = pool.run(batch, progress=sink)
    by_unit = {e.unit: e for e in sink.events}
    assert set(by_unit) == {j.key for j in batch}
    for key in ("job-00", "job-01", "job-02"):
        assert by_unit[key].status == "ok" and by_unit[key].codes == ()
    bad = by_unit["job-99-bad"]
    assert bad.status == "failed" and len(bad.codes) == 1 and bad.codes[0].startswith("worker.")
    for event in sink.events:
        assert event.duration_s is not None and event.duration_s > 0
        assert event.fields["isolation"] == "worker" and isinstance(event.fields["worker_pid"], int)
    results_by_key = {r.key: r for r in results}
    for key, event in by_unit.items():
        assert event.fields.get("peak_rss_bytes") == results_by_key[key].peak_rss_bytes or "peak_rss_bytes" not in event.fields
    assert len(sink.events) == len(batch)  # exactly one event per job


def test_the_progress_hook_never_changes_results():
    plain = WorkerPool(in_process=True).run(jobs(5))
    reported = WorkerPool(in_process=True).run(jobs(5), progress=Collect())
    assert result_fingerprint(plain) == result_fingerprint(reported)
    worker = WorkerPool(workers=2, test_kinds=True).run(jobs(5), progress=Collect())
    assert result_fingerprint(plain) == result_fingerprint(worker)


def test_a_sink_that_raises_does_not_break_the_pool():
    class Broken:
        def emit(self, event: ProgressEvent) -> None:
            raise RuntimeError("display exploded")

    results = WorkerPool(workers=2, test_kinds=True).run(jobs(4), progress=Broken())
    assert [r.ok for r in results] == [True] * 4
    assert [r.ok for r in WorkerPool(in_process=True).run(jobs(2), progress=Broken())] == [True, True]


def test_the_pool_never_waits_on_a_slow_sink_beyond_its_own_call():
    """F2 on the T1 side: ``emit`` is called from the collecting slot; a sink that is O(1) costs nothing, and the
    run is not affected by how long the display takes because the CLI sink only enqueues. Here a sink sleeps a little
    per event to confirm the hook is synchronous and bounded by the sink's own cost."""
    delay = 0.05

    class Slowish:
        def __init__(self) -> None:
            self.n = 0

        def emit(self, event: ProgressEvent) -> None:
            time.sleep(delay)
            self.n += 1

    sink = Slowish()
    started = time.monotonic()
    WorkerPool(in_process=True).run(jobs(4), progress=sink)
    assert sink.n == 4 and time.monotonic() - started >= 4 * delay


def test_no_progress_argument_is_the_default_and_costs_nothing():
    results = WorkerPool(in_process=True).run(jobs(2))
    assert [r.ok for r in results] == [True, True]


def test_feedback_sink_receives_pool_events_and_counts_them():
    import io

    from agentprov.cli.feedback import FeedbackConfig, FeedbackSink

    out = io.StringIO()
    sink = FeedbackSink(FeedbackConfig("steps", "plain"), out)
    sink.emit(ProgressEvent("start", total=3, fields={"command": "pool"}))
    WorkerPool(in_process=True).run(jobs(3), progress=sink)
    sink.close(0)
    assert "units    3 of 3: ok 3" in out.getvalue()
    assert out.getvalue().count("  unit ok job-0") == 3
