"""Regen item 34 (bug pass BF-23), agentops: a C.7.3 placeholder tool name is kept with ``unk: ambiguous``, never typed as
known, so the run keeps its records (agentops checked no tool name; the writer refused the record and the run became an
``adapter_defect``). Inputs are built here.
"""

from __future__ import annotations

import json

import agentops_support as ao
import pytest

from agentprov.adapters.agentops import mapper
from agentprov.aer.validate import _SENTINELS as VALIDATOR


def test_the_placeholder_list_holds_the_validators():
    assert VALIDATOR <= mapper._SENTINELS


@pytest.mark.parametrize("name", ["-", "none", "unknown"])
def test_agentops_a_placeholder_tool_name_keeps_its_run(name):
    call = {"tool_name": name, "arguments": {}, "timestamp": "t"}
    result = {"tool_name": name, "result": "ok", "latency_ms": 1.0, "injected_failure": None, "injected_payload": None}
    step = {"step_number": 1, "llm_input_tokens": 1, "llm_output_tokens": 1, "reasoning": None,
            "tool_calls": [call], "tool_results": [result]}
    trace = {"task_id": "code/001", "agent_id": "openai/gpt-x", "condition": "clean", "steps": [step],
             "total_input_tokens": 1, "total_output_tokens": 1, "total_cost_usd": 0.0, "wall_time_seconds": 1.0,
             "completed": True, "final_output": None, "error": None}
    data = json.dumps({"task_id": "code/001", "agent_id": "openai/gpt-x", "condition": "clean", "run_number": 1,
                       "trace": trace, "scores": {}}).encode()
    mapped = ao.map_label("pilot_v1_seeded/gpt/openai_gpt-x/clean/code_001_run1.json", data=data, tasks={})
    assert "adapter_defect" not in [i["code"] for i in mapped.issues]
