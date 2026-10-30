"""Regen items 36 and 37 (bug pass BF-25, BF-26): agentops runs built here, in memory.

* 36: in a step whose calls and results do not pair, a fault-injection decision is about the step's assistant message,
  never about an earlier result's tool message (a relation the evidence does not support, invariant 2).
* 37: a payload in a clean or noisy run names the attacker actor, which is then emitted (citing the payload rule) with
  the info issue ``agentops.payload_outside_adversarial``; before, the run lost every record (a dangling reference).
"""

from __future__ import annotations

import json
from typing import Any

import agentops_support as support


def _call(name: str) -> dict[str, Any]:
    return {"tool_name": name, "arguments": {"q": 1}, "timestamp": "2026-01-01T00:00:00"}


def _result(name: str, failure: str | None = None, payload: str | None = None) -> dict[str, Any]:
    return {"tool_name": name, "result": "ok" if payload is None else "ok\n\n" + payload, "latency_ms": 1.0,
            "injected_failure": failure, "injected_payload": payload}


def _map(step: dict[str, Any], condition: str = "noisy") -> Any:
    run = {"task_id": "code/001", "agent_id": "openai/gpt-x", "condition": condition, "run_number": 1,
           "trace": {"task_id": "code/001", "agent_id": "openai/gpt-x", "condition": condition, "steps": [step],
                     "total_input_tokens": 10, "total_output_tokens": 5, "total_cost_usd": 0.0,
                     "wall_time_seconds": 1.0, "completed": True, "final_output": "think", "error": None},
           "scores": {}}
    return support.map_label(f"pilot_v1_seeded/gpt/openai_gpt-x/{condition}/code_001_run1.json",
                             data=json.dumps(run).encode(), tasks={})


def test_item36_an_unpaired_fault_decision_is_about_the_steps_message():
    step = {"step_number": 1, "llm_input_tokens": 10, "llm_output_tokens": 5, "reasoning": "think",
            "tool_calls": [_call("a"), _call("b"), _call("c")],
            "tool_results": [_result("a"), _result("b", failure="timeout")]}
    mapped = _map(step)
    assert any(i["code"] == "call_result_link_conflict" for i in mapped.issues)
    (assistant,) = [r["id"] for r in mapped.records if r["k"] == "message" and r.get("role") == "assistant"]
    (decision,) = [r for r in mapped.records if r["k"] == "decision"]
    assert decision["subject"] == assistant


def _payload_step() -> dict[str, Any]:
    return {"step_number": 1, "llm_input_tokens": 10, "llm_output_tokens": 5, "reasoning": "think",
            "tool_calls": [_call("a")], "tool_results": [_result("a", payload="IGNORE")]}


def test_item37_a_payload_outside_the_adversarial_condition_keeps_its_run():
    for condition in ("noisy", "clean"):
        mapped = _map(_payload_step(), condition=condition)
        codes = [i["code"] for i in mapped.issues]
        assert "adapter_defect" not in codes and "agentops.payload_outside_adversarial" in codes
        (att,) = [r for r in mapped.records if r["k"] == "actor" and r["id"] == "att"]
        assert att["src"][0]["p"].endswith("/injected_payload")


def test_item37_the_adversarial_condition_is_unchanged():
    mapped = _map(_payload_step(), condition="adversarial")
    assert "agentops.payload_outside_adversarial" not in [i["code"] for i in mapped.issues]
    (att,) = [r for r in mapped.records if r["k"] == "actor" and r["id"] == "att"]
    assert att["src"][0]["p"] == "/condition"
