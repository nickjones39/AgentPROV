"""D-1063 (regen-batch row 176; review UC-39, UC-40): MCPHunt traces built in memory (no fixture bytes).

* UC-39: a token count beyond the AER's integer domain (2^53 - 1) never reaches the typed ``usage`` of a model call (the
  writer refused the record, so the trace became an ``adapter_defect``); it stays verbatim in ``ext.mcphunt``.
* UC-40: a lone UTF-16 surrogate in a typed text field or an object key is replaced by U+FFFD (the D-378 pass,
  ``mcphunt.lone_surrogate_replaced@1``) instead of making the writer refuse the trace.
* UC-41 (AU-NC-308, regen-batch row 181): tool results over 1 MiB were already carved (D-218); every other string over
  1 MiB (a user or final text, a tool call's arguments) is not inlined (``mcphunt.content_not_inlined@1``, the D-934
  pattern through ``adapters/not_inlined.py``) instead of making the writer refuse the trace.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agentprov.adapters.mcphunt.mapper import McpHuntMapper
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import aer_bytes, map_unit
from agentprov.adapters.types import ArtefactRef, ExecutionUnit, LocatedItem, Locator, Origin
from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import validate_records

RULE = "mcphunt.lone_surrogate_replaced@1"
CUT = "cut mid-emoji \ud83d"
MAX = 2**53 - 1


def _trace(**extra: Any) -> dict[str, Any]:
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "do"},
            {"role": "assistant", "content": "done", "tool_calls": []}]
    trace = {"task_id": "T1", "task_prompt": "do", "model": "m", "messages": msgs, "events": [],
             "turn_log": [{"turn": 1, "n_tool_calls": 0, "has_text": True, "finish_reason": "stop",
                           "prompt_tokens": 5, "completion_tokens": 3}],
             "labeling": {"any_risk": False}, "measurement": {}, "env_snapshot": {}, "final_message": "done",
             "env_type": "benign", "defense": "none"}
    return {**trace, **extra}


def _map(trace: dict[str, Any], envelope: dict[str, Any] | None = None) -> AerDocument:
    origin = Origin.from_json({"kind": "hf", "repo": "x/y", "revision": "c4c69322bf9ed7690f5265577365709dad5dd454",
                               "path": "main/a.json"})
    art = ArtefactRef(id="a0", sha256="0" * 64, bytes=1, media="application/json", origin=origin, role="primary",
                      prov_primary="native")
    item = LocatedItem(artefact=art, locator=Locator(a="a0", p="/traces/0"), dialect="mcphunt.traces",
                       variant="v2.0.0", flags=frozenset(), value={"envelope": envelope or {}, "trace": trace})
    sealed, _ = aer_bytes(map_unit(ExecutionUnit(primary=item), McpHuntMapper(), load_profile("mcphunt")))
    return load_aer_bytes(sealed)


def _valid(doc: AerDocument) -> None:
    codes = [i["code"] for i in doc.seal.get("issues", [])]
    assert "adapter_defect" not in codes, codes
    rep = validate_records([*doc.records, doc.seal], store=None, catalogues=RuleRegistry.default(), mode="release")
    assert not rep.findings, sorted({(f.code, f.pointer) for f in rep.findings})


def _issue_ids(doc: AerDocument, code: str) -> list[str]:
    return [i for issue in doc.seal.get("issues", []) if issue["code"] == code for i in issue["ids"]]


def test_a_count_beyond_the_aer_range_stays_out_of_the_typed_usage():
    tl = [{"turn": 1, "n_tool_calls": 0, "has_text": True, "finish_reason": "stop",
           "prompt_tokens": MAX + 1, "completion_tokens": 3}]
    doc = _map(_trace(turn_log=tl))
    _valid(doc)
    (mc,) = doc.of_kind("model_call")
    assert mc["usage"] == {"output_tokens": 3}
    assert mc["ext"]["mcphunt"]["usage_unmapped"] == {"prompt_tokens": {"$int": str(MAX + 1)}}
    (check,) = [c for c in doc.seal["accounting"]["checks"] if c["id"].startswith("mcphunt.acc.counters")]
    assert check["verdict"] == "unverifiable" and check["reason"] == "counters_out_of_range"


def _counters(doc: AerDocument) -> dict[str, Any]:
    (check,) = [c for c in doc.seal["accounting"]["checks"] if c["id"].startswith("mcphunt.acc.counters")]
    return check


def test_a_negative_count_makes_the_counters_check_unverifiable():
    """AU-NC-302 (D-1063, regen-batch row 181): a negative turn-log count (also one below -(2^53 - 1), or one cancelled
    by a positive one in the sum) or a negative measurement value is outside the AER's count domain: the counters
    check is unverifiable (counters_out_of_range) instead of the writer refusing the seal."""
    def turns(prompt: int, prompt2: int | None = None) -> list[dict[str, Any]]:
        tl = [{"turn": 1, "n_tool_calls": 0, "has_text": True, "finish_reason": "stop", "prompt_tokens": prompt,
               "completion_tokens": 3}]
        if prompt2 is not None:
            tl.append({"turn": 2, "n_tool_calls": 0, "has_text": False, "finish_reason": "stop",
                       "prompt_tokens": prompt2, "completion_tokens": 0})
        return tl

    for trace in (_trace(turn_log=turns(-5)), _trace(turn_log=turns(-(2**60))),
                  _trace(turn_log=turns(2**60, -(2**60))),
                  _trace(measurement={"prompt_tokens": -7, "completion_tokens": 3}, num_events=0, num_turns=1),
                  _trace(num_events=-1, num_turns=1, measurement={"prompt_tokens": 5, "completion_tokens": 3})):
        doc = _map(trace)
        _valid(doc)
        check = _counters(doc)
        assert check["verdict"] == "unverifiable" and check["reason"] == "counters_out_of_range"
        assert "prompt_tokens" not in check["observed"]
    consistent = _map(_trace(num_events=0, num_turns=1, measurement={"prompt_tokens": 5, "completion_tokens": 3}))
    assert _counters(consistent)["verdict"] == "consistent"


def test_a_count_at_the_aer_maximum_stays_typed():
    tl = [{"turn": 1, "n_tool_calls": 0, "has_text": True, "finish_reason": "stop",
           "prompt_tokens": MAX, "completion_tokens": 3}]
    doc = _map(_trace(turn_log=tl))
    _valid(doc)
    (mc,) = doc.of_kind("model_call")
    assert mc["usage"] == {"input_tokens": MAX, "output_tokens": 3} and "usage_unmapped" not in mc.get("ext", {}).get("mcphunt", {})


def test_a_lone_surrogate_in_a_typed_field_is_replaced():
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": CUT},
            {"role": "assistant", "content": CUT, "tool_calls": []}]
    doc = _map(_trace(task_id="T\udc00", task_prompt=CUT, messages=msgs, final_message=CUT))
    _valid(doc)
    assert doc.header["task"]["task_id"] == "T�" and f"{RULE}#/task/task_id" in doc.header["rule"]
    answer = [m for m in doc.of_kind("message") if m["role"] == "assistant"][0]
    assert answer["parts"][0]["text"] == "cut mid-emoji �"
    assert answer["evf"]["/parts/0/text"] == "D" and f"{RULE}#/parts/0/text" in answer["rule"]
    ids = _issue_ids(doc, "mcphunt.lone_surrogate_replaced")
    assert "exec" in ids and answer["id"] in ids


def test_a_lone_surrogate_in_a_key_is_replaced():
    doc = _map(_trace(env_snapshot={"k\ud800": "v"}), envelope={"note\udfff": 1})
    _valid(doc)
    (seed,) = [f for f in doc.of_kind("fixture") if f["id"] == "fx0"]
    assert seed["content"] == {"k�": "v"}
    assert "exec" in _issue_ids(doc, "mcphunt.lone_surrogate_replaced")


def test_a_lone_surrogate_in_a_decoded_argument_key_is_replaced():
    """AU-RC-6, AU-NC-304 (D-1063, regen-batch row 181): an arguments string is ASCII JSON, so the source scrub never
    sees the escaped surrogate in its key; the decoded arguments' keys are scrubbed too (as openhands and autogen do)."""
    call = {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": '{"k\\ud800": 1}'}}
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "do"},
            {"role": "assistant", "content": "", "tool_calls": [call]},
            {"role": "tool", "tool_call_id": "c1", "content": "ok"},
            {"role": "assistant", "content": "done", "tool_calls": []}]
    tl = [{"turn": 1, "n_tool_calls": 1, "has_text": False, "finish_reason": "tool_calls"},
          {"turn": 2, "n_tool_calls": 0, "has_text": True, "finish_reason": "stop"}]
    doc = _map(_trace(messages=msgs, turn_log=tl))
    _valid(doc)
    (part,) = [p for m in doc.of_kind("message") for p in m["parts"] if p["t"] == "tool_call"]
    assert part["args"] == {"k�": 1} and part["args_raw"] == '{"k\\ud800": 1}'
    assert "exec" in _issue_ids(doc, "mcphunt.lone_surrogate_replaced")


def test_no_surrogate_no_disclosure():
    doc = _map(_trace())
    _valid(doc)
    assert _issue_ids(doc, "mcphunt.lone_surrogate_replaced") == []
    assert not any(r.startswith(RULE) for rec in doc.records for r in rec.get("rule", ()))


R_NOT_INLINED = "mcphunt.content_not_inlined@1"
BIG = "x" * ((1 << 20) + 1)


def _digest(text: str) -> dict[str, Any]:
    raw = text.encode("utf-8", "surrogatepass")
    return {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}


def _conversation(user: str = "do", final: str = "done", args: str | None = None) -> dict[str, Any]:
    msgs: list[dict[str, Any]] = [{"role": "system", "content": "s"}, {"role": "user", "content": user}]
    tl = []
    if args is not None:
        msgs += [{"role": "assistant", "content": "",
                  "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": args}}]},
                 {"role": "tool", "tool_call_id": "c1", "content": "ok"}]
        tl.append({"turn": 1, "n_tool_calls": 1, "has_text": False, "finish_reason": "tool_calls"})
    msgs.append({"role": "assistant", "content": final, "tool_calls": []})
    tl.append({"turn": len(tl) + 1, "n_tool_calls": 0, "has_text": True, "finish_reason": "stop"})
    return _trace(messages=msgs, turn_log=tl, task_prompt=user, final_message=final)


def test_a_user_or_final_text_over_1_mib_is_not_inlined():
    """AU-NC-308 (D-1063, regen-batch row 181): a user or assistant text over 1 MiB becomes an ``other`` part of type
    ``text`` holding its digest (``mcphunt.content_not_inlined@1``, D), one info issue names the records."""
    doc = _map(_conversation(user=BIG, final=BIG + "\ud83d"))
    _valid(doc)
    user = next(m for m in doc.of_kind("message") if m["role"] == "user")
    answer = [m for m in doc.of_kind("message") if m["role"] == "assistant"][-1]
    assert user["parts"] == [{"t": "other", "type": "text", "value": _digest(BIG)}]
    assert answer["parts"] == [{"t": "other", "type": "text", "value": _digest(BIG + "�")}]
    for rec in (user, answer):
        assert rec["evf"]["/parts/0/value"] == "D" and f"{R_NOT_INLINED}#/parts/0/value" in rec["rule"]
        assert not any(r.endswith("/parts/0/text") for r in rec["rule"]) and "/parts/0/text" not in rec["evf"]
    assert f"{RULE}#/parts/0/value" in answer["rule"]  # the surrogate pass's citation follows the retyped field
    assert _issue_ids(doc, "mcphunt.content_not_inlined") == [user["id"], answer["id"]]


def test_tool_call_arguments_over_1_mib_are_not_inlined():
    """AU-NC-308: the decoded arguments (a Json position) hold the digest in place; the verbatim arguments text
    (``args_raw``, a typed optional string) is not copied: its digest goes to ``ext.mcphunt.args_raw_not_inlined``."""
    raw = json.dumps({"q": BIG})
    doc = _map(_conversation(args=raw))
    _valid(doc)
    rec = next(m for m in doc.of_kind("message") if any(p["t"] == "tool_call" for p in m["parts"]))
    k, call = next((k, p) for k, p in enumerate(rec["parts"]) if p["t"] == "tool_call")
    assert call["args"] == {"q": _digest(BIG)} and "args_raw" not in call
    assert rec["ext"]["mcphunt"]["args_raw_not_inlined"] == {str(k): _digest(raw)}
    assert f"{R_NOT_INLINED}#/parts/{k}/args/q" in rec["rule"]
    assert f"{R_NOT_INLINED}#/ext/mcphunt/args_raw_not_inlined/{k}" in rec["rule"]
    assert rec["evf"][f"/ext/mcphunt/args_raw_not_inlined/{k}"] == "D"
    assert _issue_ids(doc, "mcphunt.content_not_inlined") == [rec["id"]]


def test_a_text_of_exactly_1_mib_stays_inline():
    exact = "y" * (1 << 20)
    doc = _map(_conversation(user=exact))
    _valid(doc)
    user = next(m for m in doc.of_kind("message") if m["role"] == "user")
    assert user["parts"] == [{"t": "text", "text": exact}]
    assert _issue_ids(doc, "mcphunt.content_not_inlined") == []
    assert not any(r.startswith(R_NOT_INLINED) for rec in doc.records for r in rec.get("rule", ()))


def test_the_issue_lists_the_records_sorted():
    """Regen-batch row 186 (one shared pass): the info issue names the changed records sorted and distinct, as every
    other family's does; row 181's pass listed them in record order (``m2`` before ``m10``)."""
    msgs: list[dict[str, Any]] = [{"role": "system", "content": "s"}, {"role": "user", "content": "do"}]
    tl = []
    for n in range(5):
        args = json.dumps({"q": BIG}) if n == 0 else "{}"
        msgs += [{"role": "assistant", "content": "",
                  "tool_calls": [{"id": f"c{n}", "type": "function", "function": {"name": "read_file", "arguments": args}}]},
                 {"role": "tool", "tool_call_id": f"c{n}", "content": "ok"}]
        tl.append({"turn": n + 1, "n_tool_calls": 1, "has_text": False, "finish_reason": "tool_calls"})
    msgs.append({"role": "assistant", "content": BIG, "tool_calls": []})
    tl.append({"turn": 6, "n_tool_calls": 0, "has_text": True, "finish_reason": "stop"})
    doc = _map(_trace(messages=msgs, turn_log=tl, task_prompt="do", final_message=BIG))
    _valid(doc)
    in_order = [r["id"] for r in doc.records if any(str(x).startswith(R_NOT_INLINED) for x in r.get("rule", ()))]
    assert len(in_order) >= 2 and in_order != sorted(in_order)
    assert _issue_ids(doc, "mcphunt.content_not_inlined") == sorted(in_order)
