"""``agentprov.testing.projections.common_projection`` (docs/architecture K.3.2, K.9.1; D.10.4)."""

from __future__ import annotations

import copy
from typing import Any

from agentprov.testing.projections import common_projection, projection_bytes, projection_differences


def _records() -> list[dict[str, Any]]:
    return [
        {"k": "execution", "id": "exec"},
        {"k": "scope", "id": "run", "kind": "run"},
        {"k": "scope", "id": "att0", "kind": "attempt", "parent": "run", "scored": False},
        {"k": "scope", "id": "att1", "kind": "attempt", "parent": "run", "scored": True},
        {"k": "fixture", "id": "fx0", "kind": "injection_payload", "vector": "v", "content": "payload"},
        {"k": "message", "id": "m0", "scope": "att0", "role": "user", "parts": [{"t": "text", "text": "earlier pass"}]},
        {"k": "message", "id": "m1", "scope": "att1", "role": "user", "parts": [{"t": "text", "text": "Q"}]},
        {"k": "model_call", "id": "mc0", "scope": "att1", "status": "discarded", "t": {"start": "2026-10-07T12:00:00Z"}},
        {"k": "message", "id": "m9", "scope": "att1", "role": "assistant", "generated_by": "mc0", "parts": []},
        {"k": "message", "id": "m2", "scope": "att1", "role": "assistant",
         "parts": [{"t": "tool_call", "name": "pay", "args": {"a": 2, "b": 1}}],  # as read from a JCS line
         "ext": {"lex": {"ord": {"/parts/0/args": ["b", "a"]}, "flt": ["/parts/0/args/a"]}}},
        {"k": "tool_execution", "id": "te0", "scope": "att1", "name": "pay", "status": "ok", "t": {"dur_s": 1}},
        {"k": "judgement", "id": "j0", "name": "utility", "value": True},
    ]


def test_projection_keeps_the_scored_pass_and_lexical_form():
    projection = common_projection(_records())
    assert [m["parts"][0].get("text") for m in projection["messages"]] == ['"Q"', None]
    assert projection["messages"][1]["parts"][0]["args"] == '{"b":1,"a":2.0}'
    assert projection["tool_executions"] == [{"name": '"pay"', "status": "ok"}]
    assert projection["judgements"] == [{"name": '"utility"', "value": "true"}]
    assert projection["fixtures"] == [{"content": '"payload"', "kind": "injection_payload", "vector": '"v"'}]


def test_times_are_excluded_and_differences_are_named():
    base = _records()
    timed = copy.deepcopy(base)
    timed[10]["t"] = {"dur_s": 99}
    assert projection_bytes(common_projection(base)) == projection_bytes(common_projection(timed))
    reordered = copy.deepcopy(base)
    reordered[9]["ext"]["lex"]["ord"] = {}
    left, right = common_projection(base), common_projection(reordered)
    assert projection_bytes(left) != projection_bytes(right)
    assert projection_differences(left, right) == ["/messages/1/parts/0/args"]


def _with_parts(base: list[dict[str, Any]], parts: list[dict[str, Any]], call_at: int) -> list[dict[str, Any]]:
    out = copy.deepcopy(base)
    out[9]["parts"] = parts
    out[9]["ext"]["lex"] = {"ord": {f"/parts/{call_at}/args": ["b", "a"]}, "flt": [f"/parts/{call_at}/args/a"]}
    return out


def test_tool_call_parts_are_projected_after_the_other_parts():
    """Calls are a member separate from a message's content: the importers list them last, the capture mapper adds the
    reply facts only the wire carries after them (D.10.4a); content order itself is kept."""
    base = _records()
    call = base[9]["parts"][0]
    importer = _with_parts(base, [{"t": "text", "text": None}, {"t": "reasoning", "text": "r"}, call], 2)
    live = _with_parts(base, [{"t": "text", "text": None}, call, {"t": "reasoning", "text": "r"}], 1)
    a, b = common_projection(importer), common_projection(live)
    assert projection_bytes(a) == projection_bytes(b)
    assert [p["t"] for p in a["messages"][1]["parts"]] == ["text", "reasoning", "tool_call"]
    swapped = _with_parts(base, [{"t": "reasoning", "text": "r"}, {"t": "text", "text": None}, call], 2)
    assert projection_bytes(common_projection(swapped)) != projection_bytes(a)  # content order still counts
