"""Regen item 35 (bug pass BF-24): a run whose model is missing, a placeholder or not a string still seals.

The agent actor is observed (``ev O``), so AER-V13 needs a locator for it on every path; before the fix only the branch
with a usable model gave one, and the writer refused the record, so the whole run became a 2-record ``adapter_defect``.
"""

from __future__ import annotations

import json

import credleak_support as support
import pytest

DROP = object()


@pytest.mark.parametrize("model", [DROP, "unknown", 7, None], ids=["missing", "placeholder", "int", "null"])
def test_an_agent_without_a_usable_model_keeps_its_run(model):
    cell = json.loads(support.synthetic_cell())
    if model is DROP:
        del cell["runs"][0]["model"]
    else:
        cell["runs"][0]["model"] = model
    [mapped] = support.map_cell("cell.json", json.dumps(cell).encode(), sem=False, prov=False)
    assert "adapter_defect" not in mapped.codes()
    (agent,) = [r for r in mapped.records if r.get("k") == "actor" and r.get("id") == "agent"]
    assert agent["src"] and agent["unk"]["/model"] == "not_recorded"
