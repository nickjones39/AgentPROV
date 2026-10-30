"""The transcript/v1 view on the C.16.2 vector and on small hand-built AER (docs/architecture C.15.3, C.11.4; K.7.2).

The C.16.2 vector is frozen specification data (docs/architecture/examples/C), so these tests need no golden fixture:
its source transcript has 5,904 bytes and SHA-256 a8ef75b8…1335 (C.16.2), and the view must regenerate exactly that.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agentprov.views.transcript_v1 import render, render_converted, serialise

REPO = Path(__file__).resolve().parents[3]
VECTOR = REPO / "docs" / "architecture" / "examples" / "C" / "adprov_v1_llama_injecagent.aer.jsonl"
SOURCE_SHA256 = "a8ef75b854a1bddbb9b3b265fdd48094f5ca689aab762da24a05472e56221335"


def _records() -> list[dict]:
    return [json.loads(line) for line in VECTOR.read_bytes().splitlines()]


def test_the_c16_2_vector_regenerates_its_source_bytes():
    data = serialise(render(_records()))
    assert len(data) == 5904 and hashlib.sha256(data).hexdigest() == SOURCE_SHA256


def test_render_ignores_a_trailing_seal_and_accepts_records_without_it():
    records = _records()
    assert serialise(render(records)) == serialise(render(records[:-1]))


def test_serialise_is_the_baseline_writer_layout():
    doc = {"b": [1, {"x": "é"}], "a": 0.0, "z": None, "e": {}, "l": []}
    data = serialise(doc)
    assert data == b'{\n  "b": [\n    1,\n    {\n      "x": "\\u00e9"\n    }\n  ],\n  "a": 0.0,\n  "z": null,\n  "e": {},\n  "l": []\n}'
    assert not data.endswith(b"\n") and data.isascii()


def test_lexical_hints_restore_member_order_and_integral_floats():
    records = _records()
    agent = next(r for r in records if r["id"] == "agent")
    m4 = next(r for r in records if r["id"] == "m4")
    doc = render(records)
    assert doc["meta"]["model_config"]["temperature"] == 0 and isinstance(doc["meta"]["model_config"]["temperature"], float)
    assert list(doc["turns"][4]["tool_calls"][0]["args"]) == m4["ext"]["lex"]["ord"]["/parts/1/args"]
    assert agent["ext"]["lex"] == {"flt": ["/params/temperature"]}
    del agent["ext"]
    assert isinstance(render(records)["meta"]["model_config"]["temperature"], int)


def test_a_null_attack_renders_benign_and_absent_sources_render_null():
    records = _records()
    header = records[0]
    header["task"]["attack_id"] = None
    del next(r for r in records if r["id"] == "bench")["version"]
    meta = render(records)["meta"]
    assert meta["attack_type"] == "benign" and meta["benchmark_version"] is None


def test_finish_reasons_come_from_the_calls_or_the_verbatim_list():
    records = _records()
    assert render(records)["meta"]["model_config"]["finish_reasons"] == ["tool_calls", "tool_calls", "tool_calls", "stop"]
    records[0]["ext"]["adprov"]["v1"]["finish_reasons"] = ["stop"] * 7
    assert render(records)["meta"]["model_config"]["finish_reasons"] == ["stop"] * 7


def test_an_aer_02_withheld_member_renders_null_never_a_placeholder():
    """D-211: an absent, declared part member is unknown. The view renders it as null; the converted rendering keeps the
    converter's own rule for an absent value (``args or {}``, ``""``), as for any other absent source value."""
    records = _records()
    records[0]["aer"] = "0.2"
    m0 = next(r for r in records if r["id"] == "m0")
    del m0["parts"][0]["text"]
    m0["unk"] = {"/parts/0/text": "withheld"}
    m4 = next(r for r in records if r["id"] == "m4")
    del m4["parts"][1]["args"]
    m4["unk"] = {**m4.get("unk", {}), "/parts/1/args": "withheld"}
    doc = render(records)
    assert doc["turns"][0]["content"] is None and doc["turns"][4]["tool_calls"][0]["args"] is None
    converted = render_converted(records)
    assert converted["turns"][0]["content"] == "" and converted["turns"][4]["tool_calls"][0]["args"] == {}


def test_a_degenerate_aer_has_no_transcript_f2():
    """Pre-round review F-2 (#32): a degenerate AER (D.2.8 case 3: header, run scope, seal) holds no run. The view is
    refused (``view.transcript_v1``; derive then registers the view and the compat graph failed) instead of rendering a
    complete benign run with no turns and an empty user query."""
    import pytest

    from agentprov.views.transcript_v1 import ViewError

    records = _records()
    header, seal = records[0], records[-1]
    run = {"k": "scope", "id": "run", "kind": "run", "ev": "O", "by": "source", "src": [{"a": "a0"}],
           "unk": {"/status": "not_recorded", "/t": "not_recorded"}}
    for renderer in (render, render_converted):
        with pytest.raises(ViewError, match="degenerate"):
            renderer([header, run, seal])
    assert render(_records())["turns"]  # a complete AER still renders


def test_a_withheld_reasoning_part_renders_null_not_absent_35():
    """Pre-round review #35: under aer/0.2 a reasoning or refusal part may have its text withheld (D-211). The part is
    still part of the message, so the view renders the member as null instead of dropping it."""
    from agentprov.views.transcript_v1 import _Aer, _render_assistant

    header = _records()[0]
    message = {"k": "message", "id": "m1", "role": "assistant", "parts": [
        {"t": "text", "text": "answer"}, {"t": "reasoning"}, {"t": "refusal"}],
        "unk": {"/parts/1/text": "withheld", "/parts/2/text": "withheld"}}
    built = _render_assistant(_Aer([header, message]), message)
    assert "reasoning" in built and built["reasoning"] is None
    assert "refusal" in built and built["refusal"] is None
