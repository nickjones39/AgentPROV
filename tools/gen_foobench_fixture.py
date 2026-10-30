"""Generate the FooBench fixture of the future-framework test (docs/architecture D.12.1 row 8; K.4.3, K.6.4).

FooBench is a self-authored toy JSONL format, so the fixture is generated from the event list below instead of being
kept as an opaque blob: the content is reviewable here. It is bland and synthetic by construction. The output goes to
``tests/fixtures/foobench/``:

* ``trace-001.jsonl``       the primary file: a header line, then one event per line
* ``sub-trace-001.jsonl``   the hand-off's second file (the sub-agent's events)
* ``screenshot-0.png``      the 67-byte 1x1 PNG whose digest the screenshot event carries
* ``SOURCE.json``           licence class ``permissive``, ``synthetic: true``

Every D.12 event type occurs: ``llm_request``, ``llm_response``, ``tool_start``, ``tool_end``, ``guard_verdict``,
``plan_update``, ``memory_write``, ``memory_read``, ``screenshot``, ``handoff``, ``approval`` (one ``approve``, one
``edit``), ``text_action``, ``checkpoint_restore`` and the unknown type ``telemetry``.

Run ``python tools/gen_foobench_fixture.py`` to rewrite the files, or ``--check`` to compare them with the generator.
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "foobench"
PRIMARY = "trace-001.jsonl"
SUB = "sub-trace-001.jsonl"
PNG = "screenshot-0.png"


def png_bytes() -> bytes:
    """A 1x1 RGB PNG (deterministic)."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\x10\x20\x30", 9)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def ts(second: int) -> str:
    return f"2026-10-01T12:00:{second:02d}Z"


def primary_lines(shot: bytes) -> list[dict[str, Any]]:
    blob = {"sha256": hashlib.sha256(shot).hexdigest(), "bytes": len(shot), "media": "image/png"}
    ctx3 = ["u0", "a1", "t2", "t3", "t4", "h5", "e6"]
    ctx4 = [*ctx3, "a7", "t8"]
    ctx5 = [*ctx4, "a9", "t10"]
    ctx6 = [*ctx5, "a11", "t12"]
    ctx7 = [*ctx6, "a13", "t14"]
    return [
        {"schema": "foobench/1", "run": "run-001", "task": "task-001", "agent_model": "foo-agent-1",
         "planner_model": "foo-planner-1", "t": ts(0)},
        # the planner thread: an LLM reply, then the runtime turns it into a structured plan (not an LLM step)
        {"type": "llm_request", "ts": ts(1), "id": "r0", "thread": "planner", "actor": "planner"},
        {"type": "llm_response", "ts": ts(2), "request": "r0", "finish": "stop",
         "reply": {"id": "p0", "role": "assistant", "text": "Plan: look up the note, save it, delegate, then act."}},
        {"type": "plan_update", "ts": ts(3), "reply": "p0", "plan": {"steps": ["lookup", "save", "delegate", "act"]}},
        {"type": "telemetry", "ts": ts(3), "counters": {"tokens": 42, "latency_ms": 120}},
        # the main thread: one reply with three parallel calls (lookup, save_memory, a hand-off)
        {"type": "llm_request", "ts": ts(4), "id": "r1", "thread": "main", "actor": "agent",
         "add": [{"id": "u0", "role": "user", "author": "user", "text": "Look up the note and act on it."}],
         "context": ["u0"]},
        {"type": "llm_response", "ts": ts(5), "request": "r1", "finish": "tool_calls",
         "reply": {"id": "a1", "role": "assistant", "text": "Looking up the note, saving it and delegating.",
                   "calls": [{"id": "c1", "name": "lookup", "args": {"topic": "note"}},
                             {"id": "c2", "name": "save_memory", "args": {"key": "note", "value": "remember the plan"}},
                             {"id": "c3", "name": "transfer_to_researcher", "args": {"topic": "note"}}]}},
        {"type": "guard_verdict", "ts": ts(6), "call": "c1", "guard": "guard-1", "verdict": "pass"},
        {"type": "tool_start", "ts": ts(7), "call": "c1", "name": "lookup", "args": {"topic": "note"}},
        {"type": "tool_end", "ts": ts(8), "call": "c1", "status": "ok", "output": "note body (synthetic)", "message": "t2"},
        {"type": "tool_start", "ts": ts(9), "call": "c2", "name": "save_memory",
         "args": {"key": "note", "value": "remember the plan"}},
        {"type": "memory_write", "ts": ts(10), "call": "c2", "key": "note", "value": "remember the plan",
         "store_patch": [{"op": "add", "path": "/note", "value": "remember the plan"}]},
        {"type": "tool_end", "ts": ts(11), "call": "c2", "status": "ok", "output": "saved", "message": "t3"},
        {"type": "handoff", "ts": ts(12), "call": "c3", "name": "transfer_to_researcher", "to": "researcher",
         "sub_file": SUB, "result": "The researcher found nothing unusual.", "message": "t4"},
        # the harness retrieves the memory item and the environment takes a screenshot (neither is a tool call)
        {"type": "memory_read", "ts": ts(13), "key": "note", "content": "remember the plan"},
        {"type": "screenshot", "ts": ts(14), "action": "click", **blob},
        {"type": "llm_request", "ts": ts(15), "id": "r3", "thread": "main", "actor": "agent",
         "add": [{"id": "h5", "role": "user", "origin": "harness", "text": "Memory: note = remember the plan"},
                 {"id": "e6", "role": "user", "origin": "env", "blob": blob}],
         "context": ctx3},
        {"type": "llm_response", "ts": ts(16), "request": "r3", "finish": "tool_calls",
         "reply": {"id": "a7", "role": "assistant", "text": "Clicking ok.",
                   "calls": [{"id": "c4", "name": "click", "args": {"target": "ok"}}]}},
        {"type": "approval", "ts": ts(17), "call": "c4", "approver": "human", "decision": "approve"},
        {"type": "tool_start", "ts": ts(18), "call": "c4", "name": "click", "args": {"target": "ok"}},
        {"type": "tool_end", "ts": ts(19), "call": "c4", "status": "ok", "output": "clicked", "message": "t8"},
        {"type": "checkpoint_restore", "ts": ts(20), "checkpoint": "cp-1"},
        {"type": "llm_request", "ts": ts(21), "id": "r4", "thread": "main", "actor": "agent", "context": ctx4},
        {"type": "llm_response", "ts": ts(22), "request": "r4", "finish": "tool_calls",
         "reply": {"id": "a9", "role": "assistant", "text": "Sending a note.",
                   "calls": [{"id": "c5", "name": "send_note", "args": {"to": "alice", "body": "draft"}}]}},
        {"type": "approval", "ts": ts(23), "call": "c5", "approver": "human", "decision": "edit",
         "edited_args": {"to": "alice", "body": "edited draft"}},
        {"type": "tool_start", "ts": ts(24), "call": "c5", "name": "send_note",
         "args": {"to": "alice", "body": "edited draft"}},
        {"type": "tool_end", "ts": ts(25), "call": "c5", "status": "ok", "output": "sent", "message": "t10"},
        {"type": "llm_request", "ts": ts(26), "id": "r5", "thread": "main", "actor": "agent", "context": ctx5},
        {"type": "llm_response", "ts": ts(27), "request": "r5", "finish": "stop",
         "reply": {"id": "a11", "role": "assistant", "text": "scroll(direction=down)"}},
        {"type": "text_action", "ts": ts(28), "reply": "a11", "raw": "scroll(direction=down)", "status": "ok",
         "output": "scrolled", "message": "t12"},
        {"type": "llm_request", "ts": ts(29), "id": "r6", "thread": "main", "actor": "agent", "context": ctx6},
        {"type": "llm_response", "ts": ts(30), "request": "r6", "finish": "tool_calls",
         "reply": {"id": "a13", "role": "assistant", "text": "Deleting the file.",
                   "calls": [{"id": "c6", "name": "delete_file", "args": {"path": "scratch.txt"}}]}},
        {"type": "guard_verdict", "ts": ts(31), "call": "c6", "guard": "guard-1", "verdict": "block",
         "reason": "policy", "replacement": "Blocked by the guard.", "message": "t14"},
        {"type": "llm_request", "ts": ts(32), "id": "r7", "thread": "main", "actor": "agent", "context": ctx7},
        {"type": "llm_response", "ts": ts(33), "request": "r7", "finish": "stop",
         "reply": {"id": "a15", "role": "assistant", "text": "Done."}},
    ]


def sub_lines() -> list[dict[str, Any]]:
    return [
        {"schema": "foobench/1", "parent": {"run": "run-001", "call": "c3"}, "agent": "researcher",
         "agent_model": "foo-sub-1"},
        {"type": "llm_request", "ts": ts(12), "id": "sr0", "thread": "sub", "actor": "researcher",
         "add": [{"id": "su0", "role": "user", "author": "agent", "text": "Research the note topic."}],
         "context": ["su0"]},
        {"type": "llm_response", "ts": ts(12), "request": "sr0", "finish": "stop",
         "reply": {"id": "sa1", "role": "assistant", "text": "The researcher found nothing unusual."}},
    ]


def dump(lines: list[dict[str, Any]]) -> bytes:
    return b"".join(json.dumps(line, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n" for line in lines)


def build() -> dict[str, bytes]:
    shot = png_bytes()
    files = {PRIMARY: dump(primary_lines(shot)), SUB: dump(sub_lines()), PNG: shot}
    source = []
    for name in (PRIMARY, SUB, PNG):
        data = files[name]
        source.append(
            {
                "sample_file": name,
                "url": None,
                "repository": "https://github.com/nickjones39/AgentPROV",
                "commit_or_revision": None,
                "original_path": "tools/gen_foobench_fixture.py",
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
                "licence": "MIT (the AgentPROV repository licence; self-authored)",
                "licence_class": "permissive",
                "synthetic": True,
                "retrieved_at": None,
                "note": "FooBench is a self-authored toy format for the future-framework test (D.12); generated, bland, synthetic.",
            }
        )
    files["SOURCE.json"] = (json.dumps(source, indent=2) + "\n").encode("utf-8")
    return files


def main(argv: list[str]) -> int:
    files = build()
    if "--check" in argv:
        stale = [n for n, d in files.items() if not (OUT / n).is_file() or (OUT / n).read_bytes() != d]
        for name in stale:
            print(f"stale: {name}")
        return 1 if stale else 0
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (OUT / name).write_bytes(data)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
