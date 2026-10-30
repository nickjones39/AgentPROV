"""``render_converted`` from an ``agentdojo.tracelogger`` AER (docs/architecture C.15.3, D.7.4 gate R; erratum E8).

The view's converter rules are pinned here on the C.16.1 vector (the June-2024 PI-detector log, specification data).
Gate R itself (bytes against the stored converted transcripts, C01-C09) is ``tests/golden/test_render_converted.py``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agentprov.views.transcript_v1 import render_converted, serialise

REPO = Path(__file__).resolve().parents[3]
VECTOR = REPO / "docs" / "architecture" / "examples" / "C" / "agentdojo_2024_pi_detector.aer.jsonl"


def _doc() -> dict:
    records = [json.loads(line) for line in VECTOR.read_bytes().splitlines()]
    return render_converted(records)


def test_the_converter_field_rules_are_applied_in_the_view():
    doc = _doc()
    meta = doc["meta"]
    assert list(meta) == [
        "model", "model_id", "suite", "user_task_id", "injection_task_id", "attack_type", "injections", "utility",
        "security", "started_at", "ended_at", "wall_clock_s", "agentdojo_version", "benchmark_version", "source",
        "pipeline_name", "timing_stubbed",
    ]
    assert meta["model"] == meta["model_id"] == meta["pipeline_name"] == "gpt-4o-2024-05-13-transformers_pi_detector"
    assert meta["started_at"] is None and meta["agentdojo_version"] is None and meta["timing_stubbed"] is True
    assert meta["wall_clock_s"] == round(2.078678846359253, 3) and meta["source"] == "agentdojo_native_run_log"
    assert meta["attack_type"] == "important_instructions" and "run_error" not in meta


def test_turns_follow_message_to_turn_and_the_timing_stub():
    turns = _doc()["turns"]
    assert [t["role"] for t in turns] == ["system", "user", "assistant", "tool", "assistant"]
    assistant, tool = turns[2], turns[3]
    assert assistant["text"] is None and assistant["tool_calls"][0]["function"] == "read_file"
    assert list(tool) == ["role", "tool_call_id", "function", "args", "content", "content_sha256", "error",
                          "started_at", "ended_at"]
    assert tool["started_at"] == tool["ended_at"] == "0"
    assert tool["tool_call_id"] == assistant["tool_calls"][0]["id"] and tool["function"] == "read_file"
    assert tool["content_sha256"] == "sha256:" + hashlib.sha256(tool["content"].encode()).hexdigest()


def test_a_null_attack_renders_benign_and_a_run_error_is_kept():
    records = [json.loads(line) for line in VECTOR.read_bytes().splitlines()]
    records[0]["task"]["attack_id"] = None
    records[0]["ext"]["agentdojo"]["error"] = "context_length_exceeded"
    meta = render_converted(records)["meta"]
    assert meta["attack_type"] == "benign" and meta["run_error"] == "context_length_exceeded"
    assert serialise(render_converted(records)).isascii()
