"""Regeneration-batch item 2 (B3, D-376): in AgentDyn CaMeL logs the interpreter's error feedback is written by the
camel defence, not the simulated user, and the privileged planner's input is not recorded (CaMeL ``privileged_llm.py``
l. 86-134, 306-321, 372-375 at AgentDyn 5353cf76; the logs predate that code, so the rules are cited through their
``_unverified`` twins). Synthetic ``v1.k14`` logs only."""

from __future__ import annotations

from typing import Any

from test_agentdyn import _block, _call, _census, _ok, a_log, map_a

CAMEL = "gpt-4o-mini-2024-07-18-camel"
FEEDBACK = "Running the code gave the following error:\nTraceback (most recent call last):\nNameError: name 'x' is not defined"


def camel_log(feedback: str = FEEDBACK) -> dict[str, Any]:
    call = _call("get_shopping_account_user_information", {}, None)
    return a_log(CAMEL, pipeline_name=CAMEL + "+camel", messages=[
        {"role": "user", "content": _block("Show my account.")},
        {"role": "assistant", "content": _block("print(x)"), "tool_calls": None},
        {"role": "user", "content": _block(feedback)},
        {"role": "assistant", "content": _block("info = get_shopping_account_user_information()"), "tool_calls": [call]},
        {"role": "tool", "content": _block("{'Email': 'x'}"), "tool_call_id": None, "tool_call": call, "error": None},
        {"role": "assistant", "content": _block("Done."), "tool_calls": []},
    ])


def test_interpreter_feedback_is_the_defences():
    m = map_a(camel_log(), CAMEL)
    _ok(m)
    camel = next(a for a in m.of_kind("actor") if a.get("name") == "camel")
    feedback = [r for r in m.of_kind("message") if r.get("role") == "user"][1]
    assert feedback["actor"] == camel["id"] and feedback["evf"]["/actor"] == "I"
    assert "agentdyn.camel_interpreter_feedback_unverified@1#/actor" in feedback["rule"]
    assert "generated_by" not in feedback  # written by the defence; no decision about a call
    assert not m.issues("unattributed_additional_user_message")
    assert _census(m)["agentdojo.camel_interpreter_feedback"]["feedback_messages"] == 1


def test_other_later_user_messages_stay_unattributed():
    m = map_a(camel_log("Please also check my orders."), CAMEL)
    _ok(m)
    later = [r for r in m.of_kind("message") if r.get("role") == "user"][1]
    assert later["actor"] == "user" and m.issues("unattributed_additional_user_message")


def test_planner_calls_declare_their_input_not_recorded():
    m = map_a(camel_log(), CAMEL)
    calls = [mc for mc in m.of_kind("model_call") if mc["role"] == "agent"]
    assert len(calls) == 3
    for mc in calls:
        assert "input" not in mc and mc["unk"]["/input"] == "not_recorded"
        assert "agentdyn.camel_planner_input_not_logged_unverified@1#/input" in mc["rule"]
        assert not any(r.startswith("agentdojo.context_is_prefix") for r in mc["rule"])
    assert _census(m)["agentdojo.camel_interpreter_feedback"]["planner_calls"] == 3


def test_outside_camel_the_prefix_input_and_the_fallback_stay():
    doc = a_log()
    doc["messages"].append({"role": "user", "content": _block(FEEDBACK)})
    m = map_a(doc)
    assert all("input" in mc for mc in m.of_kind("model_call"))
    assert [r for r in m.of_kind("message") if r.get("role") == "user"][-1]["actor"] == "user"
