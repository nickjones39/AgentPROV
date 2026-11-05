"""Review-uncovered findings in the ``agentdojo.capture`` mapper (2026-11-01; 0.2.0 change batch D-1063,
regeneration-batch item 174): UC-12 (a deny-listed tool name), UC-40 (a lone surrogate in a typed text field) and
UC-42 (type confusion in the session's events and blobs). All content is synthetic."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

import pytest
from capture_support import (
    ENDPOINT,
    ENV_DIGEST,
    IDENTITY,
    INSTRUMENTATION,
    PARAMS,
    SESSION,
    TOOLS,
    MappedSession,
    Session,
    call,
    session_objects,
    start_data,
    text,
)

from agentprov.adapters.agentdojo.capture_mapper import AgentDojoCaptureMapper
from agentprov.adapters.agentdojo.capture_reader import CaptureLogReader
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import aer_bytes, map_unit


def _seal(s: Session) -> MappedSession:
    profile = load_profile("agentdojo-live")
    log = s.log_bytes()
    objects = {hashlib.sha256(log).hexdigest(): log, **s.blobs}
    plan = CaptureLogReader().plan(session_objects(log, s.blobs, s.native, s.session), objects.__getitem__, profile)
    assert len(plan.units) == 1, plan.register
    unit, mapper = plan.units[0], AgentDojoCaptureMapper()
    outcome = map_unit(unit, mapper, profile, auxiliary=plan.auxiliary)
    data, info = aer_bytes(outcome, unit=unit, mapper=mapper, profile=profile)
    return MappedSession(log, objects, outcome, data, info, profile, plan.register)


def _ok(m: MappedSession) -> None:
    assert not m.outcome.degenerate and "adapter_defect" not in m.codes, m.codes
    report = m.validate()
    assert report.ok, [(f.code, f.pointer) for f in report.errors]


def _session(name: str = "get_balance", *, answer: Any = "Your balance is 1810.0.", tool_text: Any = "1810.0",
             native_tool_calls: Any = None, resp0_message: dict[str, Any] | None = None,
             as_logged: bool = False) -> Session:
    """The C.13.8 shape (one tool call, one answer) with the tool name, the answer, the tool output and the native
    ``tool_calls`` value as given; ``as_logged``: the blobs as ``json.dumps`` writes them (ASCII escapes, so a lone
    surrogate can be held), not JCS."""
    s = Session(SESSION)
    if as_logged:
        jcs_blob = s.blob
        s.blob = lambda obj, media="application/json": jcs_blob(json.dumps(obj).encode(), media)  # type: ignore[method-assign]
    msgs = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "Q"}]
    req0 = {"model": "scripted-fake", "messages": msgs, "tools": TOOLS}
    msg0 = resp0_message or {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_0", "type": "function", "function": {"name": name, "arguments": "{}"}}]}
    resp0 = {"id": "fake-0", "model": "scripted-fake", "choices": [{"index": 0, "finish_reason": "tool_calls",
                                                                    "message": msg0}],
             "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17}}
    error = None if name == "get_balance" else f"Invalid tool {name} provided."
    visible = tool_text if error is None else error
    req1 = {"model": "scripted-fake", "messages": msgs + [msg0, {"role": "tool", "tool_call_id": "call_0",
                                                                "content": visible}], "tools": TOOLS}
    resp1 = {"id": "fake-1", "model": "scripted-fake", "choices": [{"index": 0, "finish_reason": "stop", "message": {
        "role": "assistant", "content": answer}}], "usage": {"prompt_tokens": 20, "completion_tokens": 7, "total_tokens": 27}}
    native = [{"role": "system", "content": text("SYS")},
              {"role": "user", "content": text("Q")},
              {"role": "assistant", "content": None,
               "tool_calls": [call(name, {}, "call_0")] if native_tool_calls is None else native_tool_calls},
              {"role": "tool", "content": text(tool_text if error is None else ""), "tool_call_id": "call_0",
               "tool_call": call(name, {}, "call_0"), "error": error},
              {"role": "assistant", "content": text(answer), "tool_calls": None}]
    s.emit("session.start", start_data())
    s.emit("instrumentation", {"items": copy.deepcopy(INSTRUMENTATION)})
    s.emit("identity", copy.deepcopy(IDENTITY))
    s.emit("pass.start", {"env": {"sha256": ENV_DIGEST, "canon": "jcs-rfc8785"}}, pass_=0)
    s.emit("llm.request", {"call": "c0", "role": "agent", "attempt": 0, "endpoint": ENDPOINT, "params": PARAMS,
                           "input_at": [0, 1], "n_messages": 2, "request": s.blob(req0)}, pass_=0, actor="agent")
    s.emit("llm.response", {"call": "c0", "status": "kept", "response": s.blob(resp0), "finish_reason": "tool_calls",
                            "served_model": "scripted-fake", "response_id": "fake-0",
                            "usage": {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17}}, pass_=0, actor="agent")
    s.emit("tool.dispatch", {"occ": "o0", "at": {"message": 2, "call": 0}, "provider_call_id": "call_0",
                             "name": name, "args": {}, "args_raw": "{}"}, pass_=0, actor="env")
    if error is None:
        s.emit("tool.result", {"occ": "o0", "status": "ok", "args_effective": {}, "returned": tool_text,
                               "rendered": tool_text, "model_visible": tool_text, "error": None}, pass_=0, actor="env")
    else:
        s.emit("tool.result", {"occ": "o0", "status": "error", "args_effective": {}, "returned": None, "rendered": "",
                               "model_visible": error, "error": error}, pass_=0, actor="env")
    s.emit("llm.request", {"call": "c1", "role": "agent", "attempt": 0, "endpoint": ENDPOINT, "params": PARAMS,
                           "input_at": [0, 1, 2, 3], "n_messages": 4, "request": s.blob(req1)}, pass_=0, actor="agent")
    s.emit("llm.response", {"call": "c1", "status": "kept", "response": s.blob(resp1), "finish_reason": "stop",
                            "served_model": "scripted-fake", "response_id": "fake-1",
                            "usage": {"input_tokens": 20, "output_tokens": 7, "total_tokens": 27}}, pass_=0, actor="agent")
    s.emit("pass.end", {"aborted": False, "messages": s.blob(native),
                        "env": {"sha256": ENV_DIGEST, "canon": "jcs-rfc8785", "changed": False}}, pass_=0)
    s.emit("outcome", {"judgements": [{"name": "utility", "value": error is None, "origin": "checker"}]})
    s.close("complete")
    return s


def test_the_control_session_seals():
    _ok(_seal(_session()))


# ------------------------------------------------------------------------------------------------ UC-12
@pytest.mark.parametrize("name", ["none", "-", "unknown"])
def test_a_deny_listed_tool_name_keeps_the_session_and_is_declared_ambiguous(name: str):
    """UC-12: the capture mapper declares a deny-listed tool name ``unk ambiguous`` (C.7.2(2)) as the TraceLogger
    (CD-10, item 87), DRIFT (item 97) and Inspect (BF-22) mappers do, instead of losing the whole session."""
    m = _seal(_session(name))
    _ok(m)
    [te] = m.of_kind("tool_execution")
    assert te["name"] == name and te["unk"]["/name"] == "ambiguous"
    calls = [(r, k) for r in m.of_kind("message") for k, p in enumerate(r["parts"]) if p.get("t") == "tool_call"]
    assert calls and all(r["parts"][k]["name"] == name and r["unk"][f"/parts/{k}/name"] == "ambiguous"
                         for r, k in calls)


# ------------------------------------------------------------------------------------------------ UC-42
def _with(s: Session, *events: dict[str, Any]) -> Session:
    s.events.pop()  # session.end
    s.events.extend(events)
    s.close("complete")
    return s


def _capture_errors(m: MappedSession) -> list[str]:
    return [str(i.get("detail")) for i in m.issues("capture_error")]


@pytest.mark.parametrize("bad", [["defence_message"], {"k": 1}])
def test_a_note_kind_that_is_not_a_string_is_ignored_not_a_crash(bad: Any):
    """UC-42: a set-membership test on an unhashable ``kind`` raised TypeError and lost the session."""
    m = _seal(_with(_session(), {"type": "note", "pass": 0, "actor": None,
                                 "data": {"ns": "agentdojo", "kind": bad, "payload": {}}}))
    _ok(m)


def test_an_instrumentation_item_of_unhashable_kind_is_malformed_not_a_crash():
    s = _session()
    s.events[1]["data"]["items"].append({"id": "agentdojo.extra@1", "kind": ["behaviour_preserving"], "recorded": "full"})
    m = _seal(s)
    _ok(m)
    assert all(i.get("id") != "agentdojo.extra@1" for i in m.header["instrumentation"])


def test_a_fixture_of_unhashable_kind_is_malformed_not_a_crash():
    m = _seal(_with(_session(), {"type": "fixture", "pass": None, "actor": None,
                                 "data": {"kind": ["environment"], "content": {}}}))
    _ok(m)
    assert any("fixture" in d for d in _capture_errors(m)) and not m.of_kind("fixture")


def test_a_response_status_that_is_not_a_string_is_ambiguous_not_a_crash():
    s = _session()
    resp = next(e for e in s.events if e["type"] == "llm.response")
    resp["data"]["status"] = ["kept"]
    m = _seal(s)
    _ok(m)
    assert m.get("mc0")["unk"]["/status"] == "ambiguous"


def test_a_judgement_origin_that_is_not_a_string_is_malformed_not_a_crash():
    s = _session()
    s.events[-2]["data"]["judgements"].append({"name": "security", "value": True, "origin": ["checker"]})
    m = _seal(s)
    _ok(m)
    assert any("outcome judgement" in d for d in _capture_errors(m))
    assert [j["name"] for j in m.of_kind("judgement")] == ["utility"]


def test_an_actor_of_unhashable_kind_is_a_malformed_session_not_a_mapper_defect():
    s = _session()
    s.events[0]["data"]["actors"]["agent"]["kind"] = ["llm_agent"]
    m = _seal(s)
    assert m.outcome.degenerate and "adapter_defect" not in m.codes, m.codes


@pytest.mark.parametrize("bad", [5, [5], "x"])
def test_a_native_tool_calls_value_of_another_type_does_not_crash_the_alignment(bad: Any):
    """UC-42: ``_sent`` read the native ``tool_calls`` as a list of dicts (``len`` and ``.get`` raised); without
    ``input_at`` the dump is aligned against the wire request, so every dump message reaches it."""
    s = _session(native_tool_calls=bad)
    for e in s.events:
        if e["type"] == "llm.request":
            e["data"].pop("input_at")
    m = _seal(s)
    assert not m.outcome.degenerate and "adapter_defect" not in m.codes, m.codes


@pytest.mark.parametrize("bad", [7, {"id": "call_9"}])
def test_a_discarded_reply_whose_tool_calls_is_not_a_list_is_kept_as_other(bad: Any):
    from capture_cells import Cell

    cell = Cell()
    cell.start_pass()
    cell.reply(status="discarded", reason="element_raised:ValueError", message_extra={"tool_calls": bad})
    cell.reply(content="Your balance is 1810.0.")
    cell.end_pass()
    cell.outcome()
    m = _seal(cell.close())
    _ok(m)
    msg = next(r for r in m.of_kind("message") if r.get("generated_by") == "mc0")
    assert [p["t"] for p in msg["parts"]] == ["text", "other"] and msg["parts"][1]["value"] == bad
    assert m.issues("agentdojo.unknown_message_shape")


@pytest.mark.parametrize("field,bad", [("content", 5), ("tool_calls", 5)])
def test_messages_wire_alignment_of_a_native_value_of_another_type_is_unavailable_not_a_crash(field: str, bad: Any):
    from agentprov.adapters.agentdojo import messages_wire as mw

    natives: list[dict[str, Any]] = [{"role": "user", "content": text("Q")},
                                     {"role": "assistant", "content": text("A"), "tool_calls": None},
                                     {"role": "user", "content": text("Q2")}]
    natives[1 if field == "tool_calls" else 2][field] = bad
    request = {"messages": [{"role": "user", "content": [{"type": "text", "text": "Q"}]},
                            {"role": "assistant", "content": [{"type": "text", "text": "A"}]},
                            {"role": "user", "content": [{"type": "text", "text": "Q2"}]}]}
    assert mw.match_inputs(natives, request) is None


# ------------------------------------------------------------------------------------------------ UC-40
def test_a_lone_surrogate_in_a_typed_text_is_replaced_and_disclosed():
    """UC-40 (D-378): the capture mapper lacked the lone-surrogate pass of its sibling mappers, so a provider reply text
    holding an escaped lone surrogate (an emoji cut in half) made the session an ``adapter_defect``."""
    m = _seal(_session(answer="Balance: 1810.0 \ud83d", as_logged=True))
    _ok(m)
    last = [r for r in m.of_kind("message") if r.get("role") == "assistant"][-1]
    assert last["parts"][0]["text"] == "Balance: 1810.0 \ufffd"
    assert last["evf"]["/parts/0/text"] == "D"
    assert "agentdojo.lone_surrogate_replaced@1#/parts/0/text" in last["rule"]
    [issue] = m.issues("agentdojo.lone_surrogate_replaced")
    assert last["id"] in issue["ids"]
