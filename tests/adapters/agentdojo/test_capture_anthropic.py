"""Provider-``anthropic`` capture sessions (D-656; C.13.10 item 22): the Anthropic Messages wire mapped by
``agentdojo.capture`` under the ``anthropic_messages`` catalogue.

``tests/fixtures/capture/anthropic/<scenario>/session/`` holds real ``capture/0.1`` sessions of AgentDojo 0.1.35 driven
by the declared port of ``AnthropicLLM`` on a real ``AsyncAnthropic`` client over ``ScriptedTransport`` in Messages
mode (synthetic replies; ``backends/agentdojo/tools/make_capture_fixtures.py``). A discarded streamed reply, which the
port's retries never produce from a 2xx, is built here as a synthetic log. The fixtures are read programmatically;
nothing here prints their content.
"""

from __future__ import annotations

import copy
import hashlib
import json
from functools import cache
from pathlib import Path

import pytest
from capture_cells import IDENTITY, PROMPT, SYS, Cell, text
from capture_support import FIXTURES, MappedSession, map_built, map_staged_session

from agentprov.adapters.agentdojo.capture_mapper import native_comparable
from agentprov.adapters.agentdojo.messages_wire import BAD, STOCK_COT_PROMPT, decode_reply, match_inputs
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.projection import common_projection
from agentprov.aer.rules import load_catalogue

ANTHROPIC = FIXTURES / "anthropic"
SCENARIOS = ("anthropic_benign_banking", "anthropic_injection_important_instructions", "anthropic_retries",
             "anthropic_filtered_and_cut_calls", "anthropic_torn_stream")
#: The sha256 of the profile bytes the scratch corpus recorded (migration-work/agentdojo-env, aer stage
#: profile_sha256 sha256:388950f3...) and of autodojo-live as it stood before D-656, both archived byte for byte.
RECORDED_AGENTDOJO_LIVE_V1 = "388950f31180751dac530ec253e880ec9d00bf02fd32885f2cf43bf82e97f44a"
RECORDED_AUTODOJO_LIVE_V1 = "5d75391f4571b69cf1d457b806704e8b8a97832db8aab0ef98c51fe727a37426"
NEW_ITEMS = ("agentdojo.anthropic_element_port@1", "agentdojo.anthropic_max_tokens@1")


@cache
def _mapped(scenario: str) -> MappedSession:
    staged = ANTHROPIC / scenario / "session"
    if not (staged / "raw" / "capture").is_dir():
        pytest.skip(f"capture fixture {scenario} is not present")
    m = map_staged_session(Path(staged))
    report = m.validate()
    assert report.ok, [(f.code, f.pointer) for f in report.errors]
    return m


def _rule_ids(record: dict) -> list[str]:
    return [r.split("#", 1)[0] for r in record.get("rule") or ()]


# ------------------------------------------------------------------------------------------------ profiles
@pytest.mark.parametrize("profile_id, recorded", [("agentdojo-live", RECORDED_AGENTDOJO_LIVE_V1),
                                                  ("autodojo-live", RECORDED_AUTODOJO_LIVE_V1)])
def test_live_profiles_accept_the_port_from_version_2_with_version_1_archived(profile_id, recorded):
    current, v2, archived = load_profile(profile_id), load_profile(profile_id, 2), load_profile(profile_id, 1)
    assert current.version == 3 and v2.version == 2  # v3: the defence items (D-670, D-677; v2 archived, item 167)
    assert archived.version == 1 and archived.sha256 == recorded
    for profile in (current, v2):
        assert set(NEW_ITEMS) <= set(profile.data["family"]["agentdojo"]["live"]["instrumentation_accepted"])
    assert not set(NEW_ITEMS) & set(archived.data["family"]["agentdojo"]["live"]["instrumentation_accepted"])
    assert dict(current.data["import"]["rules"])["anthropic_messages"] == load_catalogue("anthropic_messages").version


def test_agentdojo_live_guards_the_ports_stock_sources():
    guarded = load_profile("agentdojo-live").data["family"]["agentdojo"]["live"]["guarded_sources"]
    assert {"agentdojo.agent_pipeline.llms.anthropic_llm._conversation_to_anthropic",
            "agentdojo.agent_pipeline.llms.anthropic_llm.chat_completion_request",
            "agentdojo.agent_pipeline.llms.anthropic_llm.AnthropicLLM.query"} <= set(guarded)


# ------------------------------------------------------------------------------------------------ fixtures
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_scenario_maps_valid_and_agrees_with_its_native_log(scenario):
    m = _mapped(scenario)
    assert "anthropic_messages" in m.header["rules"]
    assert not {"agentdojo.capture_sent_form_unexplained", "agentdojo.capture_reply_mismatch",
                "agentdojo.instrumentation_unrecognised", "live_native_divergence"} & set(m.codes), m.codes
    assert m.info.accounting.status == "consistent"
    # context membership is observed (input_at verified against the stock Messages rendering)
    assert all("input" in mc and "/input" not in mc.get("evf", {}) for mc in m.of_kind("model_call"))


def test_openai_format_sessions_do_not_cite_the_messages_catalogue():
    staged = FIXTURES / "benign_banking_single_pass" / "session"
    if not staged.is_dir():
        pytest.skip("capture fixture benign_banking_single_pass is not present")
    assert "anthropic_messages" not in map_staged_session(staged).header["rules"]


def test_sent_forms_are_explained():
    m = _mapped("anthropic_retries")
    calls = m.of_kind("model_call")
    assert [c["status"] for c in calls] == ["error", "error", "kept", "kept"]
    assert [c.get("retry_of") for c in calls] == [None, "mc0", "mc1", None]
    last = calls[-1]
    # system, user, assistant (tool calls), two tool results merged into one user turn: every item a plain id
    assert all(isinstance(item, str) for item in last["input"]) and len(last["input"]) == 5
    assert calls[2]["usage"] == {"input_tokens": 100, "output_tokens": 20, "cache_read_tokens": 0,
                                 "cache_write_tokens": 0}


def test_omitted_thinking_is_withheld():
    m = _mapped("anthropic_benign_banking")
    replies = [r for r in m.of_kind("message") if r.get("generated_by") and r.get("role") == "assistant"]
    assert len(replies) == 2
    for reply in replies:
        reasoning = reply["parts"][0]
        assert reasoning["t"] == "reasoning" and "text" not in reasoning and reasoning["signature"]
        assert reply["unk"]["/parts/0/text"] == "withheld"
        assert "anthropic_messages.thinking_omitted@1" in _rule_ids(reply)
        assert reply["ext"]["agentdojo"]["thinking_omitted"] == [0]
        assert any("blob" in s and "p" not in s for s in reply["src"])  # the stream blob, whole
    # the live-versus-native projection compares the empty text both the wire and the native log hold
    restored = [r for r in native_comparable(m.records) if r.get("id") == replies[0]["id"]][0]
    assert restored["parts"][0]["text"] == ""
    assert common_projection(native_comparable(m.records))


def test_filtered_and_cut_calls_follow_the_stock_reading():
    m = _mapped("anthropic_filtered_and_cut_calls")
    assert [t["status"] for t in m.of_kind("tool_execution")] == ["ok"]  # the invalid name was never dispatched
    assert [c["finish_reason"] for c in m.of_kind("model_call")] == ["tool_use", "max_tokens"]
    final = [r for r in m.of_kind("message") if r.get("generated_by") == "mc1"][0]
    assert [p["t"] for p in final["parts"]] == ["text"]  # max_tokens: the stock element parses no tool call


def test_a_torn_stream_is_kept_as_the_element_took_it():
    m = _mapped("anthropic_torn_stream")
    (call,) = m.of_kind("model_call")
    assert call["status"] == "kept" and "finish_reason" not in call
    # R1-3: disclosed in the AER
    assert [i for i in m.issues("anthropic_messages.stream_incomplete")]


# ------------------------------------------------------------------------------------------------ the wire readers
def _sse(*events: tuple[str, dict]) -> bytes:
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events).encode()


STREAM = _sse(
    ("message_start", {"type": "message_start", "message": {"id": "msg_x", "model": "claude-x", "content": []}}),
    ("content_block_start", {"type": "content_block_start", "index": 0,
                             "content_block": {"type": "thinking", "thinking": "", "signature": ""}}),
    ("content_block_delta", {"type": "content_block_delta", "index": 0,
                             "delta": {"type": "signature_delta", "signature": "c2ln"}}),
    ("content_block_start", {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}}),
    ("content_block_delta", {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "Hi"}}),
    ("content_block_start", {"type": "content_block_start", "index": 2,
                             "content_block": {"type": "tool_use", "id": "toolu_1", "name": "get_balance", "input": {}}}),
    ("content_block_delta", {"type": "content_block_delta", "index": 2,
                             "delta": {"type": "input_json_delta", "partial_json": '{"a": 1'}}),
    ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use"}}),
    ("message_stop", {"type": "message_stop"}),
)


def test_decode_reply_rebuilds_a_stream_and_keeps_raw_arguments():
    reply = decode_reply(STREAM, "text/event-stream; charset=utf-8")
    assert reply is not None and reply.streamed and reply.complete and reply.error is None
    assert (reply.id, reply.model, reply.stop_reason) == ("msg_x", "claude-x", "tool_use")
    (thinking, _), (text_block, _), (tool, pointer) = reply.blocks
    assert thinking["signature"] == "c2ln" and thinking["thinking"] == "" and text_block["text"] == "Hi"
    assert tool["input_json"] == '{"a": 1' and tool["input"] is BAD and pointer is None
    assert decode_reply(b"not json", "application/json") is None
    error = decode_reply(_sse(("error", {"type": "error", "error": {"type": "overloaded_error"}})), "text/event-stream")
    assert error is not None and error.error == {"type": "overloaded_error"}


def test_match_inputs_explains_the_stock_rendering_and_error_substitution():
    natives = [
        {"role": "system", "content": [{"type": "text", "content": "S"}]},
        {"role": "user", "content": [{"type": "text", "content": "U"}]},
        {"role": "assistant", "content": [{"type": "thinking", "content": "", "id": "sig"}],
         "tool_calls": [{"function": "f", "args": {"x": 1}, "id": "t1"}]},
        {"role": "tool", "content": [{"type": "text", "content": ""}], "tool_call_id": "t1", "error": "boom"},
    ]
    request = {"system": "S", "messages": [
        {"role": "user", "content": [{"type": "text", "text": "U", "citations": None}]},
        {"role": "assistant", "content": [{"type": "thinking", "thinking": "", "signature": "sig"},
                                          {"type": "tool_use", "id": "t1", "name": "f", "input": {"x": 1}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True,
                                      "content": [{"type": "text", "text": "boom"}]}]},
    ]}
    matches = match_inputs(natives, request)
    assert matches is not None and [(f, t) for f, t, _u in matches] == [
        (True, []), (True, []), (True, []), (True, ["error_substitution"])]
    assert matches[3][2] == {"role": "user", "content": request["messages"][2]["content"]}
    # wire content the natives do not account for: nothing is claimed
    extra = copy.deepcopy(request)
    extra["messages"].append({"role": "user", "content": [{"type": "text", "text": "more"}]})
    assert match_inputs(natives, extra) is None
    changed = copy.deepcopy(request)
    changed["messages"][0]["content"][0]["text"] = "V"
    assert match_inputs(natives, changed)[1][0] is False


def test_a_discarded_messages_reply_is_decoded():
    cell = Cell()
    identity = copy.deepcopy(IDENTITY)
    identity["agent"]["provider"] = "anthropic"
    cell.s.events[2]["data"] = identity
    cell.start_pass()
    body = {"system": SYS, "messages": [{"role": "user", "content": [{"type": "text", "text": PROMPT}]}],
            "max_tokens": 64, "stream": True}
    for status in ("discarded", "kept"):
        cid = cell.request(wire_messages=body["messages"])
        cell.s.events[-1]["data"]["request"] = cell.s.blob(body)
        data = {"call": cid, "status": status, "response": cell.s.blob(STREAM, "text/event-stream")}
        if status == "discarded":
            data["reason"] = "element_raised:ValueError"
        cell.s.emit("llm.response", data, pass_=cell.pass_index, actor="agent")
    cell.messages.append({"role": "assistant", "content": [{"type": "thinking", "content": "", "id": "c2ln"},
                                                           {"type": "text", "content": "Hi"}], "tool_calls": None})
    cell.end_pass()
    cell.outcome()
    m = map_built(cell.close())
    assert m.validate().ok
    (discarded,) = [r for r in m.of_kind("message") if r.get("generated_by") == "mc0"]
    reasoning, said, tool = discarded["parts"]
    assert reasoning["t"] == "reasoning" and "text" not in reasoning and discarded["unk"]["/parts/0/text"] == "withheld"
    assert said == {"t": "text", "text": "Hi"}
    assert tool["t"] == "tool_call" and tool["args_raw"] == '{"a": 1' and discarded["unk"]["/parts/2/args"] == "ambiguous"
    assert "anthropic_messages.discarded_reply@1" in _rule_ids(discarded)
    assert "unexecuted_tool_call" in m.codes
    assert text("x")  # the shared builders stay importable



# ------------------------------------------------------------------------------------------------ review round 1
def _ev(name: str, payload: dict) -> tuple[str, dict]:
    return (name, payload)


START = _ev("message_start", {"type": "message_start", "message": {"id": "m", "model": "c", "content": []}})
TEXT0 = _ev("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})
DELTA0 = _ev("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "a"}})
STOP = _ev("message_stop", {"type": "message_stop"})


@pytest.mark.parametrize("events, why", [
    ((TEXT0, DELTA0, STOP), "before_message_start"),
    ((START, START), "message_start"),
    ((START, TEXT0, TEXT0), "block_index"),
    ((START, _ev("content_block_start", {"type": "content_block_start", "index": 3,
                                         "content_block": {"type": "text", "text": ""}})), "block_index"),
    ((START, TEXT0, _ev("content_block_delta", {"type": "content_block_delta", "index": 0,
                                                "delta": {"type": "thinking_delta", "thinking": "x"}})), "delta_type"),
    ((START, TEXT0, _ev("content_block_stop", {"type": "content_block_stop", "index": 0}), DELTA0), "block_index"),
    ((START, TEXT0, STOP, DELTA0), "after_message_stop"),
    ((START, _ev("content_block_delta", {"type": "message_stop"})), "event_payload"),
])
def test_stream_reading_is_strict_and_disclosed(events, why):
    reply = decode_reply(_sse(*events), "text/event-stream")
    assert reply is not None and reply.inconsistent == why
    ok = decode_reply(_sse(START, TEXT0, DELTA0, _ev("ping", {"type": "ping"}), STOP), "text/event-stream")
    assert ok is not None and ok.inconsistent is None and ok.complete and not ok.torn
    assert ok.blocks[0][0]["text"] == "a"
    torn = decode_reply(_sse(START, TEXT0, DELTA0, STOP)[:-1], "text/event-stream")  # ends inside the last event
    assert torn is not None and not torn.complete and torn.torn


def test_json_bodies_must_be_messages():
    assert decode_reply(b'{"a": 1}', "application/json") is None
    assert decode_reply(b'{"type": "message", "role": "assistant", "content": [1]}', "application/json") is None
    ok = decode_reply(b'{"type": "message", "role": "assistant", "content": [], "stop_reason": "end_turn"}',
                      "application/json")
    assert ok is not None and ok.complete and ok.stop_reason == "end_turn"


def test_delta_joining_is_linear():
    import time

    body = _sse(START, TEXT0, *([DELTA0] * 100_000), STOP)
    began = time.perf_counter()
    reply = decode_reply(body, "text/event-stream")
    assert reply is not None and reply.blocks[0][0]["text"] == "a" * 100_000
    assert time.perf_counter() - began < 30  # quadratic joining took minutes at this size


def test_sent_form_includes_the_stock_cot_prefix_and_refuses_an_unaccounted_system():
    natives = [{"role": "system", "content": [{"type": "text", "content": "S"}]},
               {"role": "user", "content": [{"type": "text", "content": "U"}]}]
    user = [{"role": "user", "content": [{"type": "text", "text": "U"}]}]
    haiku3 = {"model": "claude-3-haiku-20240307", "system": f"{STOCK_COT_PROMPT}\n\nS", "messages": user}
    assert [f for f, _t, _u in match_inputs(natives, haiku3)] == [True, True]
    assert match_inputs(natives, {**haiku3, "system": "S"})[0][0] is False
    assert [f for f, _t, _u in match_inputs(natives, {"model": "claude-haiku-5-5", "system": "S", "messages": user})] \
        == [True, True]
    assert match_inputs(natives[1:], {"model": "claude-haiku-5-5", "system": "S", "messages": user}) is None
    assert match_inputs(natives[1:], {"model": "claude-haiku-5-5", "messages": user}) is not None


def _anthropic_cell() -> Cell:
    cell = Cell()
    identity = copy.deepcopy(IDENTITY)
    identity["agent"]["provider"] = "anthropic"
    cell.s.events[2]["data"] = identity
    cell.start_pass()
    return cell


REDACTED = _sse(
    START,
    _ev("content_block_start", {"type": "content_block_start", "index": 0,
                                "content_block": {"type": "redacted_thinking", "data": "ZW5j"}}),
    _ev("content_block_stop", {"type": "content_block_stop", "index": 0}),
    _ev("content_block_start", {"type": "content_block_start", "index": 1,
                                                         "content_block": {"type": "text", "text": ""}}),
    _ev("content_block_delta", {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "Hi"}}),
    _ev("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn"}}),
    STOP,
)


def _respond(cell: Cell, status: str, blob: bytes, **extra: object) -> str:
    body = {"system": SYS, "messages": [{"role": "user", "content": [{"type": "text", "text": PROMPT}]}],
            "max_tokens": 64, "stream": True}
    cid = cell.request(wire_messages=body["messages"])
    cell.s.events[-1]["data"]["request"] = cell.s.blob(body)
    data = {"call": cid, "status": status, "response": cell.s.blob(blob, "text/event-stream"), **extra}
    cell.s.emit("llm.response", data, pass_=cell.pass_index, actor="agent")
    return cid


def test_a_redacted_thinking_reply_agrees_with_the_stock_dump():
    cell = _anthropic_cell()
    _respond(cell, "kept", REDACTED)
    cell.messages.append({"role": "assistant", "content": [{"type": "redacted_thinking", "content": "ZW5j"},
                                                           {"type": "text", "content": "Hi"}], "tool_calls": None})
    cell.end_pass()
    cell.outcome()
    m = map_built(cell.close())
    assert "agentdojo.capture_reply_mismatch" not in m.codes
    (reply,) = [r for r in m.of_kind("message") if r.get("role") == "assistant"]
    assert reply["generated_by"] == "mc0" and reply["parts"][0].get("redacted") is True


def test_a_redacted_place_of_a_discarded_reply_is_withheld_and_an_inconsistent_one_is_refused():
    cell = _anthropic_cell()
    hexdigest = hashlib.sha256(STREAM).hexdigest()
    _respond(cell, "discarded", STREAM, reason="element_raised:ValueError",
             redactions=[{"blob": f"sha256:{hexdigest}", "p": "", "rule": "cap.secret.env_value@1"}])
    _respond(cell, "discarded", _sse(TEXT0, DELTA0), reason="element_raised:ValueError")  # no message_start
    _respond(cell, "kept", STREAM)
    cell.messages.append({"role": "assistant", "content": [{"type": "thinking", "content": "", "id": "c2ln"},
                                                           {"type": "text", "content": "Hi"}], "tool_calls": None})
    cell.end_pass()
    cell.outcome()
    m = map_built(cell.close())
    (first,) = [r for r in m.of_kind("message") if r.get("generated_by") == "mc0"]
    assert first["unk"]["/parts/1/text"] == "withheld" and "text" not in first["parts"][1]
    assert first["unk"]["/parts/2/args"] == "withheld"
    assert [r for r in m.of_kind("message") if r.get("generated_by") == "mc1"] == []
    assert "capture_error" in m.codes and "anthropic_messages.stream_inconsistent" in m.codes


# ------------------------------------------------------------------------------------------------ review round 3
EMPTY_DELTA = _ev("content_block_delta", {"type": "content_block_delta", "index": 0,
                                          "delta": {"type": "text_delta", "text": ""}})


@pytest.mark.parametrize("body, media", [
    (_sse(START, TEXT0), "text/event-stream"),                         # cut right after content_block_start
    (_sse(START, TEXT0, EMPTY_DELTA, STOP), "text/event-stream"),      # an empty delta
    (b'{"type": "message", "role": "assistant", "content": [{"type": "text", "text": ""}], "stop_reason": "end_turn"}',
     "application/json"),                                              # a JSON empty text block
])
def test_a_discarded_messages_reply_with_empty_text_maps(body, media):
    """Review R3-1: an empty text is ambiguous, as in _assistant_message; it no longer aborts the session's mapping."""
    cell = _anthropic_cell()
    cid = cell.request(wire_messages=[{"role": "user", "content": [{"type": "text", "text": PROMPT}]}])
    cell.s.emit("llm.response", {"call": cid, "status": "discarded", "reason": "element_raised:ValueError",
                                 "response": cell.s.blob(body, media)}, pass_=cell.pass_index, actor="agent")
    _respond(cell, "kept", STREAM)
    cell.messages.append({"role": "assistant", "content": [{"type": "thinking", "content": "", "id": "c2ln"},
                                                           {"type": "text", "content": "Hi"}], "tool_calls": None})
    cell.end_pass()
    cell.outcome()
    m = map_built(cell.close())
    assert m.validate().ok
    (discarded,) = [r for r in m.of_kind("message") if r.get("generated_by") == "mc0"]
    assert discarded["parts"][0] == {"t": "text", "text": ""} and discarded["unk"]["/parts/0/text"] == "ambiguous"


def test_an_openai_discarded_reply_with_empty_content_maps():
    """Review R3-1 on the OpenAI path (content "")."""
    cell = Cell()
    cell.start_pass()
    cell.reply(content="", status="discarded", reason="superseded_by_retry")
    cell.reply(content="Your balance is 1810.0.")
    cell.end_pass()
    cell.outcome()
    m = map_built(cell.close())
    assert m.validate().ok
    (discarded,) = [r for r in m.of_kind("message") if r.get("generated_by") == "mc0"]
    assert discarded["parts"][0] == {"t": "text", "text": ""} and discarded["unk"]["/parts/0/text"] == "ambiguous"


@pytest.mark.parametrize("body", [b"not a stream at all", b"", _sse(_ev("ping", {"type": "ping"}))])
def test_a_discarded_stream_without_message_start_yields_no_message(body):
    """Review R3-2: the SDK's get_final_message asserts without message_start, so there was no message."""
    reply = decode_reply(body, "text/event-stream")
    assert reply is not None and reply.inconsistent == "no_message_start"
    cell = _anthropic_cell()
    _respond(cell, "discarded", body, reason="element_raised:AssertionError")
    _respond(cell, "kept", STREAM)
    cell.messages.append({"role": "assistant", "content": [{"type": "thinking", "content": "", "id": "c2ln"},
                                                           {"type": "text", "content": "Hi"}], "tool_calls": None})
    cell.end_pass()
    cell.outcome()
    m = map_built(cell.close())
    assert [r for r in m.of_kind("message") if r.get("generated_by") == "mc0"] == []
    assert "capture_error" in m.codes


def test_a_forged_start_input_json_and_forwarded_event_names_follow_the_sdk():
    """Review R3-4: the SDK's JSON buffer is its own (a start block's input_json never seeds it), and an event name
    the SDK forwards besides the six makes the stream inconsistent."""
    forged = _ev("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {
        "type": "tool_use", "id": "t", "name": "f", "input": {}, "input_json": '{"forged": 1}'}})
    reply = decode_reply(_sse(START, forged, STOP), "text/event-stream")
    assert reply is not None and reply.inconsistent is None and reply.blocks[0][0]["input"] == {}
    assert "input_json" not in reply.blocks[0][0]
    for name in ("message", "completion", "agent.message", "session.updated"):
        odd = decode_reply(_sse(START, _ev(name, {"type": name}), STOP), "text/event-stream")
        assert odd is not None and odd.inconsistent == "forwarded_event", name
