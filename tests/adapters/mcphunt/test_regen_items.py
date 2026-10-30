"""Regen items 38-41 (bug pass BF-27, BF-29, BF-30, BF-31): MCPHunt traces built here, in memory (no fixture bytes).

* 38 (security): ``mcphunt.canary_flagged``, the D-289 / RW-1 withhold trigger, is raised for every trace with a
  flagged event, also when the event pairs with no call (another call-name form, an off-by-one turn); its ids are the
  paired executions, plus the attempt when a flagged event paired with none.
* 39: a provider call id reused in two turns links neither call to a tool message by id (no class D link to the first
  message twice); the conflict is an issue and each tool message is emitted exactly once, from its own source index.
* 40: every source message is kept: a user or system message after the first assistant turn
  (``mcphunt.unplaced_message``) and a tool message without a call id (``orphan_tool_result``) follow in source order.
* 41: a token counter in ``turn_log`` that is not an integer is a data problem (the counters check is
  ``unverifiable``), never a crash that turns the trace into an ``adapter_defect``.
"""

from __future__ import annotations

from typing import Any

import pytest

from agentprov.adapters.mcphunt.mapper import McpHuntMapper
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import aer_bytes, map_unit
from agentprov.adapters.types import ArtefactRef, ExecutionUnit, LocatedItem, Locator, Origin
from agentprov.aer.reader import load_aer_bytes


def _trace(turn_log: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "do"},
            {"role": "assistant", "content": "done", "tool_calls": []}]
    trace = {"task_id": "T1", "task_prompt": "do", "model": "m", "messages": msgs, "events": [], "turn_log": turn_log,
             "labeling": {"any_risk": False}, "measurement": {}, "env_snapshot": {}, "final_message": "done",
             "env_type": "benign", "defense": "none"}
    return {**trace, **extra}


def _map(trace: dict[str, Any]) -> Any:
    origin = Origin.from_json({"kind": "hf", "repo": "x/y", "revision": "c4c69322bf9ed7690f5265577365709dad5dd454",
                               "path": "main/a.json"})
    art = ArtefactRef(id="a0", sha256="0" * 64, bytes=1, media="application/json", origin=origin, role="primary",
                      prov_primary="native")
    item = LocatedItem(artefact=art, locator=Locator(a="a0", p="/traces/0"), dialect="mcphunt.traces",
                       variant="v2.0.0", flags=frozenset(), value={"envelope": {}, "trace": trace})
    sealed, _ = aer_bytes(map_unit(ExecutionUnit(primary=item), McpHuntMapper(), load_profile("mcphunt")))
    return load_aer_bytes(sealed)


def _codes(doc: Any) -> list[str]:
    return [i["code"] for i in doc.seal.get("issues", [])]


def _counters_check(doc: Any) -> dict[str, Any]:
    (check,) = [c for c in doc.seal["accounting"]["checks"] if c["id"].startswith("mcphunt.acc.counters")]
    return check


def _turn(**counters: Any) -> dict[str, Any]:
    return {"turn": 1, "n_tool_calls": 0, "has_text": True, "finish_reason": "stop", **counters}


@pytest.mark.parametrize("bad", ["n/a", "12", [1], {"a": 1}, True], ids=["text", "digits", "list", "dict", "bool"])
def test_item41_a_counter_that_is_not_an_integer_is_unverifiable_not_a_defect(bad):
    doc = _map(_trace([_turn(prompt_tokens=bad, completion_tokens=3)]))
    assert "adapter_defect" not in _codes(doc)
    check = _counters_check(doc)
    assert check["verdict"] == "unverifiable" and check["reason"] == "counters_not_integers"


def test_item41_integer_and_absent_counters_are_unchanged():
    doc = _map(_trace([_turn(prompt_tokens=5, completion_tokens=None)]))
    assert "adapter_defect" not in _codes(doc)
    assert _counters_check(doc)["reason"] == "counters_not_recorded"  # this trace reports no counters to compare with


def _event(tool: str, turn: int, result: str, *, flagged: bool = False) -> dict[str, Any]:
    return {"args": {}, "canary_in_args": False, "canary_in_result": flagged, "canary_visible_to_llm": False,
            "error": None, "latency_ms": 1, "result_chars": len(result), "result_full": result,
            "result_preview": result, "result_truncated": False, "server": "filesystem", "success": True,
            "timestamp": "t", "tool": tool, "turn": turn}


def _call(cid: str, name: str) -> dict[str, Any]:
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": "{}"}}


def _one_call_trace(name: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "do"},
            {"role": "assistant", "content": "", "tool_calls": [_call("c1", name)]},
            {"role": "tool", "tool_call_id": "c1", "content": "result text"},
            {"role": "assistant", "content": "done", "tool_calls": []}]
    turns = [{"turn": 1, "n_tool_calls": 1, "has_text": False, "finish_reason": "tool_calls"},
             {"turn": 2, "n_tool_calls": 0, "has_text": True, "finish_reason": "stop"}]
    return {**_trace(turns), "messages": msgs, "events": events, "final_message": "bye"}


def _canary(doc: Any) -> dict[str, Any] | None:
    return next((i for i in doc.seal.get("issues", []) if i["code"] == "mcphunt.canary_flagged"), None)


@pytest.mark.parametrize(("name", "turn", "paired"), [
    ("read_file", 1, True),  # the control: paired
    ("filesystem-read_file", 1, False),  # a call-name form the name guard does not accept
    ("read_file", 0, False),  # the event's turn is off by one
], ids=["paired", "name-form", "turn-off-by-one"])
def test_item38_every_flagged_trace_raises_the_canary_issue(name, turn, paired):
    doc = _map(_one_call_trace(name, [_event("read_file", turn, "x", flagged=True)]))
    issue = _canary(doc)
    assert issue is not None and issue["detail"] == "1 canary-flagged event(s)"
    executions = [r["id"] for r in doc.records if r.get("k") == "tool_execution"]
    assert issue["ids"] == (executions if paired else ["att0"])


def test_item38_an_unflagged_trace_raises_none():
    assert _canary(_map(_one_call_trace("filesystem-read_file", [_event("read_file", 1, "x")]))) is None


def test_item39_a_reused_call_id_links_nothing_and_emits_every_message_once():
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "do"},
            {"role": "assistant", "content": "", "tool_calls": [_call("call_0", "read_file")]},
            {"role": "tool", "tool_call_id": "call_0", "content": "R1"},
            {"role": "assistant", "content": "", "tool_calls": [_call("call_0", "read_file")]},
            {"role": "tool", "tool_call_id": "call_0", "content": "R2"},
            {"role": "assistant", "content": "done", "tool_calls": []}]
    turns = [{"turn": k, "n_tool_calls": n, "has_text": text, "finish_reason": reason}
             for k, n, text, reason in ((1, 1, False, "tool_calls"), (2, 1, False, "tool_calls"), (3, 0, True, "stop"))]
    events = [_event("read_file", 1, "R1"), _event("read_file", 2, "R2")]
    doc = _map({**_trace(turns), "messages": msgs, "events": events, "final_message": "bye"})
    tools = [r for r in doc.records if r.get("k") == "message" and r.get("role") == "tool"]
    assert sorted(r["src"][0]["p"] for r in tools) == ["/traces/0/messages/3", "/traces/0/messages/5"]
    assert all("responds_to" not in r["parts"][0] for r in tools)  # no D link by a reused id
    conflicts = [i for i in doc.seal["issues"] if i["code"] == "call_result_link_conflict"]
    assert [i.get("detail") for i in conflicts].count("call_id_not_unique") == 2


def test_item40_every_source_message_is_kept():
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "do"},
            {"role": "assistant", "content": "a", "tool_calls": []},
            {"role": "user", "content": "FOLLOW-UP"},
            {"role": "tool", "content": "stray"},
            {"role": "assistant", "content": "done", "tool_calls": []}]
    turns = [{"turn": 1, "n_tool_calls": 0, "has_text": True, "finish_reason": "stop"},
             {"turn": 2, "n_tool_calls": 0, "has_text": True, "finish_reason": "stop"}]
    doc = _map({**_trace(turns), "messages": msgs, "final_message": "done"})
    pointers = sorted(r["src"][0]["p"] for r in doc.records if r.get("k") == "message" and r.get("src")
                      and r["src"][0]["p"].startswith("/traces/0/messages/"))
    assert pointers == [f"/traces/0/messages/{i}" for i in range(len(msgs))]
    by_pointer = {r["src"][0]["p"]: r["id"] for r in doc.records if r.get("k") == "message" and r.get("src")}
    issues = {(i["code"], tuple(i["ids"])) for i in doc.seal["issues"]}
    assert ("mcphunt.unplaced_message", (by_pointer["/traces/0/messages/3"],)) in issues
    assert ("orphan_tool_result", (by_pointer["/traces/0/messages/4"],)) in issues
