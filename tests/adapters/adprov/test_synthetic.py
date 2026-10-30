"""Synthetic transcript/v1 documents under gates A1 and A2 for every field (J.2.5; R-32, MIG-5; K.7.2).

No frozen transcript carries ``discarded_attempts``, ``meta.n_attempts``, ``meta.capture``, ``reasoning``, ``refusal``,
``placeholder_args`` or ``reasoning_alignment``, so they are exercised here. The documents are built in code and
serialised exactly as the baseline writer does (``json.dumps(doc, indent=2)``); ``tools/migration/make_synthetic_v1.py``
(baseline-environment fixtures, J.2.5) is not part of this build. Lexical hazards that the golden set lacks (nested
non-lexicographic objects, integral floats at depth, exponent floats, ``-0.0``, non-ASCII text, JSON-Pointer-hostile
keys, empty containers) are covered too.
"""

from __future__ import annotations

import hashlib

from agentprov.io.canonical import jcs_bytes
from agentprov.ingest.loaders import strict_json_loads
from agentprov.testing import golden
from agentprov.views.transcript_v1 import render


def _gates(m) -> None:
    rendered = render(m.records[:-1])
    assert jcs_bytes(rendered) == jcs_bytes(strict_json_loads(m.raw)), "A1: JCS value identity"
    golden.assert_bytes_equal(m.raw, m.view_bytes(), what="A2")
    report = m.validate()
    assert report.ok, sorted({f.code + " " + f.pointer for f in report.errors})


def _digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def _environment(changed: bool) -> dict:
    record = {"before_sha256": "a" * 64, "after_sha256": ("b" if changed else "a") * 64, "changed": changed}
    if changed:
        record["diff"] = {"n_changes": 1, "entries": [{"path": "/bank/balance", "before": 10.0, "after": 9.5}],
                          "truncated": False}
    return record


def test_synthetic_multi_pass_round_trip(v1):
    """Two passes: a discarded one (with a re-run trigger) and the scored one, with the capture block (J.2.5)."""
    doc = v1.released()
    first_pass = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "Do the synthetic task."},
        {"role": "assistant", "text": None},
    ]
    doc["discarded_attempts"] = [{"turns": first_pass, "reasoning_alignment": "mismatch: 2 model calls, 1 assistant turns"}]
    meta = doc["meta"]
    meta["model_config"]["usage"]["n_llm_calls"] = 3
    meta["model_config"]["finish_reasons"] = ["stop", "tool_calls", "stop"]
    meta["n_attempts"] = 2
    meta["capture"] = {
        "complete": True,
        "n_attempts": 2,
        "llm_calls_total": 3,
        "assistant_turns_total": 3,
        "passes": [
            {"pass": 1, "llm_calls": 1, "assistant_turns": 1, "tool_calls": 0, "tool_results": 0,
             "environment": _environment(False)},
            {"pass": 2, "llm_calls": 2, "assistant_turns": 2, "tool_calls": 1, "tool_results": 1,
             "environment": _environment(True)},
        ],
    }
    m = v1.map(v1.dump(doc))
    by = m.by_id()
    assert by["att0"]["index"] == 0 and by["att0"]["scored"] is False
    assert by["att1"]["index"] == 1 and by["att1"]["scored"] is True
    assert [msg["id"] for msg in m.of_kind("message") if msg["scope"] == "att0"] == ["d0m0", "d0m1", "d0m2"]
    states = m.of_kind("state_change")
    assert [s["scope"] for s in states] == ["att0", "att1"] and states[1]["changed"] is True
    assert states[1]["canon"] == "adprov.envstate@1" and states[1]["diff"]["format"] == "adprov.envstate_diff"
    assert [c.get("finish_reason") for c in m.of_kind("model_call")] == ["stop", "tool_calls", "stop"]
    assert m.info.accounting.status == "consistent"
    _gates(m)


def test_synthetic_reasoning_and_refusal_round_trip(v1):
    """Reasoning in the native position and attached after the refusal; refusal and placeholder_args (I evidence)."""
    doc = v1.released()
    turns = doc["turns"]
    turns[2] = {"role": "assistant", "text": "", "reasoning": "think (native position)",
                "tool_calls": [{"id": "call_1", "function": "get_balance", "args": {"z": 1, "a": 2.0},
                                "placeholder_args": {"z": "$z", "a": "$a"}}]}
    turns[4] = {"role": "assistant", "text": "No.", "refusal": "I cannot help with that.", "reasoning": "think (log)"}
    m = v1.map(v1.dump(doc))
    by = m.by_id()
    first, last = by["m2"], by["m4"]
    assert first["parts"][1]["t"] == "reasoning" and first["evf"]["/parts/1"] == "I"
    assert "adprov.reasoning_log_alignment@1#/parts/1" in first["rule"]
    assert "placeholder_args" in first["ext"]["adprov"]
    assert [p["t"] for p in last["parts"]] == ["text", "reasoning", "refusal"]
    assert last["ext"]["adprov"]["keys"] == ["role", "text", "refusal", "reasoning"]
    assert "adprov.refusal_log_alignment@1#/parts/2" in last["rule"]
    assert "adprov.v1_layout_unexpected_order" not in m.issue_codes()  # the writer does produce this order
    _gates(m)


def test_synthetic_lexical_hazards_round_trip(v1):
    """Member order at depth, integral and exponent floats, -0.0, non-ASCII text and pointer-hostile keys."""
    args = {
        "zeta": {"b": [1.0, {"y": -0.0, "x": 1e-07}], "a": {}},
        "a/b": [],
        "t~1": 1e21,
        "alpha": "café ☃ \U0001f600",
        "n": 12345678901234,
    }
    doc = v1.released(wall_clock_s=7.0)
    doc["turns"][2]["tool_calls"][0]["args"] = args
    doc["turns"][3] = v1.tool_turn("call_1", "get_balance", args, "résultat \U0001f600",
                                   timing=("2026-06-01T10:00:01.000001+00:00", "2026-06-01T10:00:01.000002+00:00"))
    doc["meta"]["injections"] = {"v/ec~tor": "payïload", "plain": ""}
    m = v1.map(v1.dump(doc))
    assert "/t/dur_s" in m.by_id()["run"]["ext"]["lex"]["flt"]
    _gates(m)


def test_synthetic_converted_variants_round_trip(v1):
    """Converted layout with run_error, a DoS attack and a positional batch of two calls."""
    doc = v1.converted(attack_type="captcha_dos", run_error="InternalServerError (synthetic)")
    calls = [{"id": "", "function": "f", "args": {"q": 1}}, {"id": "", "function": "g", "args": {}}]
    doc["turns"][2] = {"role": "assistant", "text": None, "tool_calls": calls}
    doc["turns"][3:4] = [
        v1.tool_turn("", "f", {"q": 1}, "one", timing=("0", "0")),
        v1.tool_turn("", "g", {}, "", error="ValueError: boom", timing=("0", "0")),
    ]
    m = v1.map(v1.dump(doc))
    statuses = [te["status"] for te in m.of_kind("tool_execution")]
    assert statuses == ["ok", "error"]
    assert "outcome_imposed_by_runner" in m.issue_codes()
    _gates(m)
