"""``--progress-file`` coverage (MN N.1.14; CLI robustness item 5).

The file is what a job manager tails, so it must not depend on what stderr shows: it records at least the ``status``
level (unit events) when stderr is at ``summary`` (the non-interactive default) or ``off``, and commands without live
feedback on stderr (``info``, ``inspect``, ``purge``, ``backends``) still write their ``start`` and ``end`` lines.
``fetch`` reports one unit per recipe. ``package`` and ``verify`` are covered in ``test_package_cmd.py``.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from agentprov.cli.feedback import FeedbackConfig, make_sink
from agentprov.progress import ProgressEvent


def _events(path: Path) -> list[dict[str, Any]]:
    """The event lines, without the 0.2 ``run`` header and ``heartbeat`` snapshots (tested in test_progress_v02.py)."""
    return [e for e in map(json.loads, path.read_text().splitlines()) if e["event"] not in ("run", "heartbeat")]


def _feed(sink: Any) -> None:
    sink.emit(ProgressEvent("start", total=1, fields={"command": "validate"}))
    sink.emit(ProgressEvent("unit_start", unit="u"))
    sink.emit(ProgressEvent("step", unit="u", stage="map"))
    sink.emit(ProgressEvent("unit_done", unit="u", status="ok"))
    sink.close(0)


def test_the_file_records_unit_events_while_stderr_shows_only_the_summary(tmp_path):
    path = tmp_path / "events.jsonl"
    out = io.StringIO()
    sink = make_sink(FeedbackConfig("summary", "plain", str(path)), out)
    assert sink is not None
    _feed(sink)
    assert [e["event"] for e in _events(path)] == ["start", "unit_start", "unit_done", "end"]  # no step: above status
    assert "unit" not in out.getvalue().split("finished")[0].split("\n", 1)[1]  # stderr: banner and table only


def test_progress_off_still_writes_the_file_and_nothing_to_stderr(tmp_path):
    path = tmp_path / "events.jsonl"
    out = io.StringIO()
    sink = make_sink(FeedbackConfig("off", "plain", str(path)), out)
    assert sink is not None
    _feed(sink)
    assert out.getvalue() == ""
    assert [e["event"] for e in _events(path)] == ["start", "unit_start", "unit_done", "end"]
    assert make_sink(FeedbackConfig("off", "plain"), out) is None  # no file: no sink, nothing opened


def test_a_higher_progress_level_also_raises_the_file(tmp_path):
    path = tmp_path / "events.jsonl"
    sink = make_sink(FeedbackConfig("steps", "plain", str(path)), io.StringIO())
    assert sink is not None
    _feed(sink)
    assert "step" in [e["event"] for e in _events(path)]


def test_a_command_without_live_feedback_writes_start_and_end_but_nothing_on_stderr(cli, tmp_path):
    path = tmp_path / "events.jsonl"
    plain = cli("info", "--format", "json")
    run = cli("info", "--format", "json", "--progress-file", str(path))
    assert run.code == 0 and run.out == plain.out and run.err == plain.err
    seen = _events(path)
    assert [e["event"] for e in seen] == ["start", "end"] and seen[0]["command"] == "info" and seen[1]["exit_code"] == 0


def test_fetch_reports_each_recipe(cli, tmp_path):
    path = tmp_path / "events.jsonl"
    run = cli("fetch", "--profile", "agentdojo-upstream", "--dry-run", "--cache-dir", str(tmp_path / "cache"),
              "--progress", "off", "--progress-file", str(path))
    assert run.code == 0, run.err
    seen = _events(path)
    assert seen[0]["event"] == "start" and seen[0]["command"] == "fetch" and seen[0]["total"] >= 1
    done = [e for e in seen if e["event"] == "unit_done"]
    assert len(done) == seen[0]["total"] and {e["status"] for e in done} <= {"cached", "would_fetch"}
    assert seen[-1]["event"] == "end" and seen[-1]["units_done"] == len(done)
