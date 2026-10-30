"""G4: the experimental live PROV preview (design §9; D-398). Synthetic capture lines only; content strings are built
from fragments, so a leak would show up as a fragment in a delta."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from agentprov_gui.preview.model import BANNER, CaptureTail, PreviewGraph, capture_log

SESSION = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"
SECRET = "ignore " + "previous " + "instructions"


def _lines(events: list[dict[str, Any]]) -> list[bytes]:
    out, prev = [], None
    for seq, e in enumerate(events):
        line = json.dumps({"seq": seq, "ts": "2026-10-22T00:00:00.000000Z", "mono_ns": seq, "actor": "agent",
                           "pass": e.pop("pass", 0), "prev": prev, **e}, sort_keys=True).encode() + b"\n"
        prev = hashlib.sha256(line).hexdigest()
        out.append(line)
    return out


EVENTS: list[dict[str, Any]] = [
    {"type": "session.start", "data": {"actors": {"agent": {"model": SECRET}, "env": {}}, "session": SESSION}},
    {"type": "pass.start", "pass": 0, "data": {"env": {"$blob": "sha256:" + "0" * 64, "bytes": 3}}},
    {"type": "llm.request", "data": {"call": "c1", "n_messages": 2, "request": {"messages": [SECRET]}}},
    {"type": "llm.response", "data": {"call": "c1", "status": "ok", "response": SECRET}},
    {"type": "tool.dispatch", "data": {"occ": "o1", "at": "c1", "name": "send_" + "money", "args": {"x": SECRET}}},
    {"type": "tool.result", "data": {"occ": "o1", "status": "denied", "rendered": SECRET}},
    {"type": "llm.request", "data": {"call": "c2", "input_at": ["o1"], "n_messages": 4}},
    {"type": "pass.end", "data": {"messages": [SECRET], "aborted": False, "env": {}}},
    {"type": "outcome", "data": {"judgements": [SECRET]}},
    {"type": "session.end", "data": {"status": "complete", "n_events": 10, "appended_by": "worker"}},
]


def _deltas(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    graph = PreviewGraph(SESSION)
    return [d.to_json() for e in events for d in graph.apply(e)]


def test_the_mapping_uses_metadata_only() -> None:
    events = [json.loads(line) for line in _lines([dict(e) for e in EVENTS])]
    deltas = _deltas(events)
    text = json.dumps(deltas)
    assert SECRET not in text and "money" not in text  # no content, no tool name
    kinds = {d["kind"] for d in deltas if d["op"] == "node"}
    assert kinds == {"run", "agent", "pass", "model", "tool", "outcome"}
    edges = {(d["src"].split(":", 1)[1], d["dst"].split(":", 1)[1], d["kind"]) for d in deltas if d["op"] == "edge"}
    assert ("occ:o1", "call:c1", "informed_by") in edges and ("call:c2", "occ:o1", "used") in edges
    assert any(d["op"] == "close" and d["kind"] == "decision" for d in deltas)  # a denied tool result is a Decision
    assert any(d["op"] == "close" and d.get("label") == "Run (complete)" for d in deltas)


def test_ids_outside_the_closed_pattern_are_dropped() -> None:
    evil = [dict(EVENTS[0]), {"type": "llm.request", "data": {"call": "../../" + SECRET}}]
    assert all(d["kind"] in ("run", "agent", "associated") for d in _deltas(evil))


def test_the_tail_follows_partial_lines_and_checks_the_chain(tmp_path: Path) -> None:
    lines = _lines([dict(e) for e in EVENTS])
    path = tmp_path / "s.capture.jsonl"
    path.write_bytes(lines[0] + lines[1][:10])
    tail = CaptureTail(path)
    assert len(tail.poll()) == 1
    with open(path, "ab") as fh:
        fh.write(lines[1][10:] + b"".join(lines[2:5]))
    assert len(tail.poll()) == 4 and tail.stopped is None
    with open(path, "ab") as fh:
        fh.write(lines[6])  # line 5 skipped: the chain breaks
    assert tail.poll() == [] and tail.stopped == "the hash chain is broken"


def test_a_missing_log_waits_and_a_shrunk_one_stops(tmp_path: Path) -> None:
    path = tmp_path / "s.capture.jsonl"
    tail = CaptureTail(path)
    assert tail.poll() == [] and tail.stopped is None
    path.write_bytes(b"".join(_lines([dict(e) for e in EVENTS[:3]])))
    assert len(tail.poll()) == 3
    path.write_bytes(b"")
    assert tail.poll() == [] and "shrank" in (tail.stopped or "")


def test_session_ids_never_name_other_paths(tmp_path: Path) -> None:
    assert capture_log(tmp_path, SESSION) == (tmp_path / "staging" / SESSION / "raw" / "capture"
                                              / f"{SESSION}.capture.jsonl")
    assert capture_log(tmp_path, "../x") is None and capture_log(tmp_path, "a/b") is None


def test_the_helper_process_streams_deltas_and_exits_on_eof(tmp_path: Path) -> None:
    log = capture_log(tmp_path, SESSION)
    assert log is not None
    log.parent.mkdir(parents=True)
    lines = _lines([dict(e) for e in EVENTS])
    log.write_bytes(b"".join(lines[:4]))
    proc = subprocess.Popen([sys.executable, "-I", "-m", "agentprov_gui.preview", str(tmp_path)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, env={"PATH": os.environ.get("PATH", "")})
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(json.dumps({"watch": SESSION}).encode() + b"\n")
    proc.stdin.flush()
    first = json.loads(proc.stdout.readline())
    assert first["session"] == SESSION and first["op"] == "node" and first["kind"] == "run"
    with open(log, "ab") as fh:
        fh.write(b"".join(lines[4:]))
    seen = [first]
    end = time.monotonic() + 20
    while time.monotonic() < end and not any(d.get("label") == "Run (complete)" for d in seen):
        seen.append(json.loads(proc.stdout.readline()))
    assert any(d.get("label") == "Run (complete)" for d in seen) and SECRET not in json.dumps(seen)
    proc.stdin.close()
    assert proc.wait(timeout=10) == 0
    assert not list((tmp_path / "gui").glob("**/*")) if (tmp_path / "gui").exists() else True  # writes nothing


def test_the_banner_says_it_is_not_provenance() -> None:
    assert "Not corpus provenance" in BANNER and BANNER.startswith("Preview: provisional graph")


def test_the_window_draws_the_preview_and_stops_its_helper(qapp: Any, tmp_path: Path) -> None:
    from PySide6.QtCore import QEventLoop

    from agentprov_gui.ui.preview import PreviewWindow

    log = capture_log(tmp_path, SESSION)
    assert log is not None
    log.parent.mkdir(parents=True)
    log.write_bytes(b"".join(_lines([dict(e) for e in EVENTS])))
    window = PreviewWindow(tmp_path, lambda: [SESSION], title="t")
    window.show()
    end = time.monotonic() + 20
    while time.monotonic() < end and not any(n["label"] == "Run (complete)" for n in window.nodes.values()):
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        time.sleep(0.05)
        window._tick()
    assert any(n["label"] == "Run (complete)" for n in window.nodes.values())
    texts = [i.text() for i in window.scene.items() if hasattr(i, "text")]
    assert "PREVIEW" in texts and SECRET not in " ".join(texts)
    assert BANNER in [w.text() for w in window.findChildren(type(window.status))]
    proc = window.proc
    window.close()
    assert proc is not None and proc.wait(timeout=10) == 0
