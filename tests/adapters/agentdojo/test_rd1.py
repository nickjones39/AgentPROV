"""RD-1 (core review D, routed to regen-items-2-12) with core review A's CA-19 and CA-11 copy: regeneration-batch items
77, 78 and 87-93 in the TraceLogger mapper, its family checker and the transcript/v1 view. Synthetic logs only."""

from __future__ import annotations

from typing import Any

import pytest
from agentdojo_support import map_log, new_log
from source_support import blocks, call, final, log_with, map_synthetic, ok, v1_log
from test_mandate import DECLINE, MONEY, PROFILE, mandate_log

from agentprov.adapters.agentdojo.profile import check_against_schema
from agentprov.views.transcript_v1 import _native_message_turn, render_converted


def _unk(record: dict[str, Any]) -> dict[str, str]:
    return dict(record.get("unk", {}))


# ------------------------------------------------------------------------------------------------ item 87 (CD-10)
@pytest.mark.parametrize("name", ["none", "unknown", "-"])
def test_a_deny_listed_tool_name_keeps_the_log(name):
    doc = new_log()
    doc["messages"][2]["tool_calls"][0]["function"] = name
    doc["messages"][3]["tool_call"]["function"] = name
    doc["messages"][3]["content"], doc["messages"][3]["error"] = "", f"Invalid tool {name} provided."
    m = map_log(doc)
    assert "adapter_defect" not in m.codes
    ok(m)
    (te,) = m.of_kind("tool_execution")
    assert te["name"] == name and _unk(te)["/name"] == "ambiguous"
    part = next(p for p in m.get("m2")["parts"] if p["t"] == "tool_call")
    assert part["name"] == name and _unk(m.get("m2"))["/parts/" + str(m.get("m2")["parts"].index(part)) + "/name"] == "ambiguous"


# ------------------------------------------------------------------------------------------------ item 88 (CD-11)
@pytest.mark.parametrize(("key", "value"), [("attack_type", "none"), ("suite_name", "unknown"), ("injection_task_id", "-")])
def test_a_placeholder_in_a_typed_header_slot_is_malformed(key, value):
    m = map_log(new_log(**{key: value}))
    assert m.outcome.degenerate and "unparseable_artefact" in m.codes and "adapter_defect" not in m.codes
    task = m.header["task"]
    assert value not in task.values()


def test_a_placeholder_in_an_ext_field_still_maps():
    """``error`` and ``pipeline_name`` go to ext (verbatim fields, C.7.3): no deny-list there."""
    m = map_log(new_log(error="none", utility=False))
    assert not m.outcome.degenerate
    assert m.header["ext"]["agentdojo"]["error"] == "none"


# ------------------------------------------------------------------------------------------------ item 89 (CD-12)
def _two_calls(answered: str, *, last: bool) -> dict[str, Any]:
    doc = new_log()
    first = {"function": "send_money", "args": {"recipient": "X", "amount": 10.0}, "id": "call_a"}
    second = {"function": "send_money", "args": {"recipient": "Y", "amount": 5.0}, "id": "call_b"}
    doc["messages"][2]["tool_calls"] = [first, second]
    echo = first if answered == "call_a" else second
    doc["messages"][3].update(tool_call_id=answered, tool_call=dict(echo))
    if last:
        doc["messages"].pop()
    return doc


@pytest.mark.parametrize(("last", "code"), [(False, "missing_tool_result"), (True, "unexecuted_tool_call")])
@pytest.mark.parametrize("answered", ["call_a", "call_b"])
def test_an_unanswered_call_of_an_id_linked_batch_is_reported(answered, last, code):
    m = map_log(_two_calls(answered, last=last))
    m2 = m.get("m2")
    unanswered = "call_b" if answered == "call_a" else "call_a"
    k = next(k for k, p in enumerate(m2["parts"]) if p["t"] == "tool_call" and p.get("provider_call_id") == unanswered)
    (issue,) = m.issues(code)
    assert issue["ids"] == [f"m2#{k}"]


# ------------------------------------------------------------------------------------------------ items 90 (CD-13) and 77 (CA-19)
def _assistant_blocks(content: list[dict[str, Any]]) -> Any:
    doc = v1_log()
    doc["messages"][-1]["content"] = content
    return doc, map_log(doc)


def test_thinking_signature_extra_keys_and_absent_content_are_kept():
    content = [{"type": "thinking", "content": "hmm", "id": "SIG"}, {"type": "text", "content": "Paid.", "extra_key": "X"},
               {"type": "text"}]
    doc, m = _assistant_blocks(content)
    ok(m)
    last = m.get(f"m{len(doc['messages']) - 1}")
    reasoning, extra, absent = last["parts"]
    assert reasoning == {"t": "reasoning", "text": "hmm", "signature": "SIG"}
    assert extra["t"] == "other" and extra["value"] == content[1] and absent["t"] == "other" and absent["value"] == content[2]
    assert "agentdojo.unknown_message_shape" in m.codes
    # the converted view still reads every block as the baseline converter does
    assert render_converted(m.records)["turns"][-1] == _native_message_turn(doc["messages"][-1])


def test_a_null_content_text_block_is_not_content_null():
    doc, m = _assistant_blocks([{"type": "text", "content": None}])
    ok(m)
    last = m.get(f"m{len(doc['messages']) - 1}")
    assert last["parts"] == [{"t": "text", "text": None}] and last["ext"]["agentdojo"]["null_text_blocks"] == [0]
    turn = render_converted(m.records)["turns"][-1]
    assert turn["text"] == "" and turn == _native_message_turn(doc["messages"][-1])


def test_content_null_still_renders_null():
    doc = new_log()
    m = map_log(doc)
    assert render_converted(m.records)["turns"][2]["text"] is None


# ------------------------------------------------------------------------------------------------ item 91 (CD-14)
@pytest.mark.parametrize("call_id", [5, {"x": 1}])
def test_a_non_string_call_id_keeps_the_message_verbatim(call_id):
    doc = new_log()
    doc["messages"][2]["tool_calls"][0]["id"] = call_id
    m = map_log(doc)
    assert "adapter_defect" not in m.codes
    ok(m)
    part = m.get("m2")["parts"][0]
    assert part["t"] == "other" and part["type"] == "agentdojo.unknown_message"


@pytest.mark.parametrize("block", [{"type": "text", "content": 5}, {"type": "thinking", "content": {"a": 1}}])
def test_a_non_string_block_content_is_an_unknown_block(block):
    doc, m = _assistant_blocks([block])
    assert "adapter_defect" not in m.codes
    ok(m)
    last = m.get(f"m{len(doc['messages']) - 1}")
    assert last["parts"] == [{"t": "other", "type": "agentdojo.unknown_block", "value": block}]


# ------------------------------------------------------------------------------------------------ item 92 (CD-16)
@pytest.mark.parametrize("stamp", ["2025-13-40 25:61:61", "2025-02-30 11:07:03"])
def test_an_impossible_evaluation_timestamp_keeps_raw_only(stamp):
    m = map_log(v1_log(evaluation_timestamp=stamp))
    ok(m)
    run = m.get("run")
    assert "start_naive" not in run["t"] and run["t"]["raw"]["start"] == stamp and run["unk"]["/t/start"] == "ambiguous"


def test_a_real_evaluation_timestamp_is_still_naive_time():
    run = map_log(v1_log(evaluation_timestamp="2024-02-29 11:07:03.25")).get("run")
    assert run["t"]["start_naive"] == "2024-02-29T11:07:03.25"


# ------------------------------------------------------------------------------------------------ item 93 (CD-23)
def test_a_decline_with_no_call_takes_no_subject_by_position():
    c = call("send_money", MONEY, "call_1")
    orphan = {"role": "tool", "content": blocks(DECLINE), "tool_call_id": "call_1", "tool_call": c, "error": DECLINE}
    doc, path = mandate_log("intent", [orphan, final()])
    m = map_synthetic(PROFILE, doc, path)
    ok(m)
    assert not m.of_kind("decision") and not m.of_kind("tool_execution")
    msg = m.get("m2")
    assert msg["role"] == "tool" and "generated_by" not in msg
    assert _unk(msg) == {"/generated_by": "not_recorded", "/parts/0/responds_to": "ambiguous"}
    actor = next(a for a in m.of_kind("actor") if a.get("kind") == "defense")
    assert msg["actor"] == actor["id"]
    assert [i["ids"] for i in m.issues("orphan_tool_result")] == [["m2"]]


def test_a_decline_with_its_call_is_unchanged():
    c = call("send_money", MONEY, "call_1")
    doc, path = mandate_log("intent", log_with([])["messages"][2:] + [
        {"role": "assistant", "content": None, "tool_calls": [c]},
        {"role": "tool", "content": blocks(DECLINE), "tool_call_id": "call_1", "tool_call": c, "error": DECLINE}, final()])
    m = map_synthetic(PROFILE, doc, path)
    ok(m)
    k = next(k for k, p in enumerate(m.get("m2")["parts"]) if p["t"] == "tool_call")
    assert m.get("dc0")["subject"] == f"m2#{k}"


# ------------------------------------------------------------------------------------------------ item 78 (CA-11 copy)
def test_the_family_checker_enum_does_not_take_true_for_1():
    assert check_against_schema(True, {"enum": [1, 2]})
    assert check_against_schema(1, {"enum": [True]})
    assert check_against_schema(1, {"enum": [1, 2]}) == []
