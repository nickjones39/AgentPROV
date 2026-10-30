"""Regen item 34 (bug pass BF-23), openhands: the family's placeholder list holds the validator's C.7.3 list (``"0"`` and
``"-"`` were missing), and a placeholder served or requested model is kept as an unknown (it was never checked), so the
run keeps its records. Inputs are built here.
"""

from __future__ import annotations

import json

import openhands_support as oh
import pytest

from agentprov.adapters.openhands import mapper
from agentprov.aer.validate import _SENTINELS as VALIDATOR


def test_the_placeholder_list_holds_the_validators():
    assert VALIDATOR <= mapper._SENTINELS


def _openhands_events(tool: str, model: str) -> list[dict]:
    response = {"id": "r1", "model": model, "choices": [{"finish_reason": "tool_calls", "message": {
        "content": "", "tool_calls": [{"id": "c1", "function": {"name": tool, "arguments": "{}"}}]}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
    return [
        {"id": 0, "timestamp": "2025-01-01T00:00:00", "source": "user", "action": "message", "args": {"content": "do"}},
        {"id": 1, "timestamp": "2025-01-01T00:00:01", "source": "agent", "action": "run", "args": {"command": "ls"},
         "tool_call_metadata": {"function_name": tool, "tool_call_id": "c1", "model_response": response}},
        {"id": 2, "timestamp": "2025-01-01T00:00:02", "source": "agent", "observation": "run", "content": "o", "cause": 1,
         "tool_call_metadata": {"function_name": tool}},
    ]


@pytest.mark.parametrize(("tool", "model"), [("-", "m-1"), ("0", "m-1"), ("run", "unknown"), ("run", "-")])
def test_openhands_a_placeholder_tool_name_or_model_keeps_its_run(tool, model):
    label = "evaluation/m/traj_t1.json"
    data = json.dumps(_openhands_events(tool, model)).encode()
    mapped = oh.map_label(label, {label: data}, source="oas", data=data)
    assert "adapter_defect" not in [i["code"] for i in mapped.issues]
