"""D-1063 (regen-batch row 176; review UC-39, UC-40), openhands: a lone UTF-16 surrogate in a typed text field or an object
key is replaced by U+FFFD with a disclosure (the D-378 pass, ``openhands.lone_surrogate_replaced@1``), and a token count
beyond the AER's integer range stays out of the typed usage (verbatim in ``ext.openhands.usage_raw``), instead of the
writer refusing the run. Synthetic event lists built here, never written to disk. UC-41: the family has its own
``openhands.content_not_inlined@1`` since phase 10g; since AU-NC-308 (regen-batch row 181) a string over 1 MiB its own
handling does not reach goes through the shared pass (``adapters/not_inlined.py``)."""

from __future__ import annotations

import json
from typing import Any

import openhands_support as oh

from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import validate_records

LABEL = "evaluation/m/traj_t1.json"
RULE = "openhands.lone_surrogate_replaced@1"
CUT = "cut mid-emoji \ud83d"


def _events(*, user: str = "do", args: str = "{}", usage: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    response = {"id": "r1", "model": "m-1", "choices": [{"finish_reason": "tool_calls", "message": {
        "content": "", "tool_calls": [{"id": "c1", "function": {"name": "run", "arguments": args}}]}}],
        "usage": usage if usage is not None else {"prompt_tokens": 1, "completion_tokens": 1}}
    return [
        {"id": 0, "timestamp": "2025-01-01T00:00:00", "source": "user", "action": "message", "args": {"content": user}},
        {"id": 1, "timestamp": "2025-01-01T00:00:01", "source": "agent", "action": "run", "args": {"command": "ls"},
         "tool_call_metadata": {"function_name": "run", "tool_call_id": "c1", "model_response": response}},
        {"id": 2, "timestamp": "2025-01-01T00:00:02", "source": "agent", "observation": "run", "content": "o", "cause": 1,
         "tool_call_metadata": {"function_name": "run"}},
    ]


def _map(events: list[dict[str, Any]], files: dict[str, bytes] | None = None) -> oh.Mapped:
    data = json.dumps(events).encode()  # ensure_ascii: a lone surrogate is an escape, as in the review's input
    mapped = oh.map_label(LABEL, {LABEL: data, **(files or {})}, source="oas", data=data)
    assert "adapter_defect" not in mapped.codes() and not mapped.outcome.degenerate
    report = validate_records([*mapped.doc.records, mapped.doc.seal], store=None, catalogues=RuleRegistry.default(),
                              mode="release")
    assert report.ok, [(f.code, f.pointer) for f in report.findings][:5]
    return mapped


def _issue(mapped: oh.Mapped, code: str) -> dict[str, Any] | None:
    return next((i for i in mapped.issues if i["code"] == code), None)


def test_a_lone_surrogate_in_a_typed_field_is_replaced():
    mapped = _map(_events(user=CUT))
    (user,) = [m for m in mapped.of("message") if m.get("role") == "user"]
    assert user["parts"][0]["text"] == "cut mid-emoji \N{REPLACEMENT CHARACTER}"
    assert user["evf"]["/parts/0/text"] == "D" and f"{RULE}#/parts/0/text" in user["rule"]
    issue = _issue(mapped, "openhands.lone_surrogate_replaced")
    assert issue is not None and user["id"] in issue["ids"]


def test_a_lone_surrogate_in_an_argument_key_is_replaced():
    mapped = _map(_events(args=json.dumps({"k\ud800": "v"})))
    (call,) = [p for m in mapped.of("message") for p in m.get("parts", ()) if p.get("t") == "tool_call"]
    assert call["args"] == {"k\N{REPLACEMENT CHARACTER}": "v"}
    assert _issue(mapped, "openhands.lone_surrogate_replaced") is not None


def test_a_lone_surrogate_in_an_auxiliary_json_key_is_replaced():
    """AU-NC-305 (D-1063, regen-batch row 181): the auxiliary JSON (here the eval_<task>.json checkpoint copied into a
    judgement value) is scrubbed like the event list, so a lone-surrogate key no longer makes the run adapter_defect."""
    def eval_file(checkpoint: dict[str, Any]) -> dict[str, bytes]:
        return {"evaluation/m/eval_t1.json": json.dumps({"checkpoints": [checkpoint],
                                                          "final_score": {"total": 1, "result": 1}}).encode()}

    plain = _map(_events(), eval_file({"total": 1, "result": 1}))
    assert _issue(plain, "openhands.lone_surrogate_replaced") is None
    mapped = _map(_events(), eval_file({"total\ud800": 1, "result": 1}))
    values = json.dumps([j.get("value") for j in mapped.of("judgement")], ensure_ascii=False)
    assert "total\N{REPLACEMENT CHARACTER}" in values and len(mapped.of("judgement")) == len(plain.of("judgement"))
    issue = _issue(mapped, "openhands.lone_surrogate_replaced")
    assert issue is not None and "exec" in issue["ids"]


def test_text_without_a_lone_surrogate_is_unchanged():
    mapped = _map(_events())
    assert _issue(mapped, "openhands.lone_surrogate_replaced") is None
    assert not any(RULE in r for rec in mapped.records for r in rec.get("rule", ()))


def test_a_count_beyond_the_aer_range_stays_out_of_the_typed_usage():
    big = 2**60
    mapped = _map(_events(usage={"prompt_tokens": big, "completion_tokens": 7}))
    (mc,) = [r for r in mapped.of("model_call") if "usage" in r]
    assert mc["usage"] == {"output_tokens": 7}
    raw = mc["ext"]["openhands"]["usage_raw"]["prompt_tokens"]
    assert raw == {"$int": str(big)}  # verbatim, I-JSON-wrapped, in a Json position


BIG = "x" * ((1 << 20) + 1)
R_NOT_INLINED = "openhands.content_not_inlined@1"


def _digest(text: str) -> dict[str, Any]:
    import hashlib

    raw = text.encode("utf-8", "surrogatepass")
    return {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}


def test_a_user_text_over_1_mib_is_not_inlined():
    """AU-NC-308 (D-1063, regen-batch row 181): the family's own not-inlined handling covered observations, action
    arguments and the assistant's content; a user message text over 1 MiB made the writer refuse the run
    (aer.string.inline_limit). The shared pass (adapters/not_inlined.py) after the redaction now turns it into an
    ``other`` part of type ``text`` holding the digest, D under openhands.content_not_inlined@1."""
    mapped = _map(_events(user=BIG + "\ud83d"))
    (user,) = [m for m in mapped.of("message") if m.get("role") == "user"]
    assert user["parts"] == [{"t": "other", "type": "text", "value": _digest(BIG + "\N{REPLACEMENT CHARACTER}")}]
    assert user["evf"]["/parts/0/value"] == "D" and f"{R_NOT_INLINED}#/parts/0/value" in user["rule"]
    assert f"{RULE}#/parts/0/value" in user["rule"] and not any(r.endswith("/parts/0/text") for r in user["rule"])
    issue = _issue(mapped, "openhands.content_not_inlined")
    assert issue is not None and user["id"] in issue["ids"]


def test_tool_call_arguments_over_1_mib_are_not_inlined():
    """AU-NC-308: a model response's tool-call arguments over 1 MiB: the decoded ``args`` hold the digest in place, the
    verbatim ``args_raw`` is not copied and its digest goes to ``ext.openhands.args_raw_not_inlined.<k>``."""
    raw = json.dumps({"q": BIG})
    mapped = _map(_events(args=raw))
    rec = next(m for m in mapped.of("message") if any(p.get("t") == "tool_call" for p in m.get("parts", ())))
    k, call = next((k, p) for k, p in enumerate(rec["parts"]) if p.get("t") == "tool_call")
    assert call["args"] == {"q": _digest(BIG)} and "args_raw" not in call
    assert rec["ext"]["openhands"]["args_raw_not_inlined"] == {str(k): _digest(raw)}
    assert f"{R_NOT_INLINED}#/parts/{k}/args/q" in rec["rule"]
    assert f"{R_NOT_INLINED}#/ext/openhands/args_raw_not_inlined/{k}" in rec["rule"]
    issue = _issue(mapped, "openhands.content_not_inlined")
    assert issue is not None and rec["id"] in issue["ids"]


def test_a_count_at_the_aer_limit_is_typed():
    top = 2**53 - 1
    mapped = _map(_events(usage={"prompt_tokens": top, "completion_tokens": 7}))
    (mc,) = [r for r in mapped.of("model_call") if "usage" in r]
    assert mc["usage"] == {"input_tokens": top, "output_tokens": 7}
