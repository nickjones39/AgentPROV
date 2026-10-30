"""Regen item 34 (bug pass BF-23), credleak: the family's placeholder list holds the validator's C.7.3 list (``"0"`` and
``"-"`` were missing), so such a tool name is kept as an unknown and the run keeps its records. Inputs are built here.
"""

from __future__ import annotations

import credleak_support as cs
import pytest

from agentprov.adapters.credleak import mapper
from agentprov.aer.validate import _SENTINELS as VALIDATOR


def test_the_placeholder_list_holds_the_validators():
    assert VALIDATOR <= mapper._SENTINELS


@pytest.mark.parametrize("tool", ["-", "0"])
def test_credleak_a_placeholder_tool_name_keeps_its_run(tool):
    turn = {"turnNumber": 0, "userMessage": "u", "assistantResponse": "done",
            "toolCalls": [{"tool": tool, "input": {}, "output": "x"}]}
    [mapped] = cs.map_cell("p15b-run-data/01-injection-map/ch/test-model/run__x.json", cs.synthetic_cell(turns=[turn]),
                           sem=False, prov=False)
    assert "adapter_defect" not in mapped.codes()
