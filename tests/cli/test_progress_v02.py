"""``agentprov-progress/0.2`` (D-393; design.md §5): the run header, ``seq``, ``stage`` events, heartbeats, ``end.outcome``,
appending and rotation of ``--progress-file``. 0.2 is a superset of 0.1: the 0.1 events keep their shape
(``test_feedback.py``).
"""

from __future__ import annotations

import io
import json
import uuid
from pathlib import Path
from typing import Any

from agentprov.cli.feedback import FeedbackConfig, FeedbackSink, make_sink
from agentprov.progress import ProgressEvent


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def _sink(path: Path, *, clock: Clock | None = None, queue_size: int = 4096, **cfg: Any) -> FeedbackSink:
    config = FeedbackConfig("off", "plain", str(path), header={"command": "import", "mode": "dev", "dry_run": False},
                            **cfg)
    file = open(path, "a", encoding="utf-8", newline="\n")  # noqa: SIM115 - closed by the sink
    return FeedbackSink(config, io.StringIO(), file=file, clock=clock or Clock(), wall=lambda: 1_700_000_000.0,
                        start_thread=False, queue_size=queue_size)


def _units(sink: FeedbackSink, n: int, status: str = "sealed") -> None:
    for i in range(n):
        sink.emit(ProgressEvent("unit_start", unit=f"u{i}"))
        sink.emit(ProgressEvent("unit_done", unit=f"u{i}", status=status, codes=("aer.x",) if i % 2 else ()))


def test_every_segment_starts_with_a_run_line_and_every_line_carries_the_run_and_a_seq(tmp_path):
    path = tmp_path / "p.jsonl"
    sink = _sink(path)
    sink.emit(ProgressEvent("start", total=2, fields={"command": "import", "workers": 3}))
    _units(sink, 2)
    sink.close(0)
    lines = _lines(path)
    head = lines[0]
    assert head["event"] == "run" and head["segment"] == 0 and head["command"] == "import" and head["mode"] == "dev"
    assert isinstance(head["pid"], int) and head["agentprov_version"] and head["dry_run"] is False
    assert uuid.UUID(head["run"]).version == 7
    assert {line["run"] for line in lines} == {head["run"]} and {line["v"] for line in lines} == {"agentprov-progress/0.2"}
    assert [line["seq"] for line in lines] == list(range(len(lines)))
    end = lines[-1]
    assert end["event"] == "end" and end["outcome"] == "ok" and end["exit_code"] == 0


def test_a_dropped_event_leaves_a_seq_gap_and_the_heartbeat_keeps_the_true_counts(tmp_path):
    path = tmp_path / "p.jsonl"
    sink = _sink(path, queue_size=2)
    sink.emit(ProgressEvent("start", total=10, fields={"command": "import"}))
    _units(sink, 10)  # the queue holds 2: most lines are dropped, the counters are not
    sink.close(1)
    lines = _lines(path)
    seqs = [line["seq"] for line in lines]
    assert seqs == sorted(seqs) and seqs != list(range(len(seqs)))  # in order, with a gap a reader can see
    beat = [line for line in lines if line["event"] == "heartbeat"][-1]
    assert beat["units_done"] == 10 and beat["counts"] == {"sealed": 10} and beat["dropped"] > 0
    assert beat["issues_top"] == {"aer.x": 5} and beat["queue"] == {"pending": 0}
    assert lines[-1]["outcome"] == "failures"


def test_heartbeats_come_every_interval_and_at_each_stage_end(tmp_path):
    path = tmp_path / "p.jsonl"
    clock = Clock()
    sink = _sink(path, clock=clock, progress_interval=2.0)
    sink.emit(ProgressEvent("start", total=None, fields={"command": "package", "workers": 4}))
    sink.pump()
    assert not [x for x in _lines(path) if x["event"] == "heartbeat"]
    clock.t = 2.5
    sink.pump()
    assert len([x for x in _lines(path) if x["event"] == "heartbeat"]) == 1
    sink.emit(ProgressEvent("stage", stage="write", fields={"phase": "begin"}))
    sink.emit(ProgressEvent("worker", fields={"pid": 4242, "tier": "t1", "phase": "spawn"}))
    sink.pump()
    clock.t = 3.0
    sink.emit(ProgressEvent("stage", stage="write", duration_s=0.5, fields={"phase": "end", "done": 7, "total": 7}))
    sink.pump()
    beats = [x for x in _lines(path) if x["event"] == "heartbeat"]
    assert len(beats) == 2  # the stage end forced one before the interval
    assert beats[-1]["stages"]["write"] == {"state": "done", "done": 7, "total": 7, "failed": 0}
    assert beats[-1]["workers"] == {"configured": 4, "alive": 1, "pids": [4242]} and beats[-1]["elapsed_s"] == 3.0
    stage_lines = [x for x in _lines(path) if x["event"] == "stage"]
    assert [(x["stage"], x["phase"]) for x in stage_lines] == [("write", "begin"), ("write", "end")]
    sink.close(0, outcome="drained")
    assert _lines(path)[-1]["outcome"] == "drained"


def test_the_file_is_appended_so_a_resumed_job_keeps_its_history(tmp_path):
    path = tmp_path / "p.jsonl"
    for _ in range(2):
        sink = _sink(path)
        _units(sink, 1)
        sink.close(130)
    lines = _lines(path)
    runs = [x for x in lines if x["event"] == "run"]
    assert len(runs) == 2 and runs[0]["run"] != runs[1]["run"] and [r["segment"] for r in runs] == [0, 0]
    assert [x["outcome"] for x in lines if x["event"] == "end"] == ["interrupted", "interrupted"]


def test_rotation_keeps_one_older_file_and_the_new_one_starts_with_run_and_heartbeat(tmp_path):
    path = tmp_path / "p.jsonl"
    sink = _sink(path, progress_max_bytes=4096)
    sink.emit(ProgressEvent("start", total=400, fields={"command": "import"}))
    for _ in range(20):
        _units(sink, 20)
        sink.pump()
    sink.close(0)
    older = Path(str(path) + ".1")
    assert older.is_file() and path.stat().st_size <= 4096 + 2048 and older.stat().st_size <= 4096 + 2048
    current = _lines(path)
    assert current[0]["event"] == "run" and current[0]["segment"] >= 1 and current[1]["event"] == "heartbeat"
    assert current[1]["units_done"] > 0  # a reader of the current file alone recovers the counters
    assert not Path(str(path) + ".2").exists()


def test_the_cli_writes_the_header_stages_and_a_final_heartbeat(cli, tmp_path, monkeypatch):
    events = tmp_path / "events.jsonl"
    run = cli("info", "--format", "json", "--progress-file", str(events), "--summary-json", str(tmp_path / "s.json"))
    assert run.code == 0, run.err
    lines = _lines(events)
    assert lines[0]["event"] == "run" and lines[0]["command"] == "info" and lines[0]["summary"].endswith("s.json")
    assert [x["event"] for x in lines][-2:] == ["heartbeat", "end"] and lines[-1]["summary"].endswith("s.json")


def test_make_sink_honours_the_interval_and_size_options(tmp_path):
    cfg = FeedbackConfig("off", "plain", str(tmp_path / "p.jsonl"), progress_interval=5.0, progress_max_bytes=70000)
    sink = make_sink(cfg, io.StringIO())
    assert sink is not None and sink._cfg.progress_interval == 5.0 and sink._jsonl[0]._max_bytes == 70000
    sink.close(0)


def test_interval_and_size_options_are_bounded(cli):
    assert cli("info", "--progress-interval", "0.5").code == 2
    assert cli("info", "--progress-max-bytes", "1000").code == 2
