"""Bug pass BF-22 (routed to regen-items-2-12): an Inspect tool whose real name is on the C.7.3 deny-list (``none``,
``-``, ``unknown``) keeps the sample: the name stays verbatim, declared ``unk ambiguous``, instead of an
``adapter_defect`` AER. Synthetic samples only."""

from __future__ import annotations

import json

import inspect_support as s
import pytest

from agentprov.aer.reader import load_aer_bytes


@pytest.mark.parametrize("name", ["get_x", "none", "None", "-", "unknown"])
def test_a_deny_listed_tool_name_keeps_the_sample(name, tmp_path):
    sample = json.loads(json.dumps(s.basic_sample()).replace('"get_x"', json.dumps(name)))
    imported = s.import_log(s.build_eval(s.synthetic_header(), {"s1_epoch_1.json": sample}), tmp_path)
    (u,) = imported.units
    assert not u.outcome.degenerate, u.outcome.error_code
    doc = load_aer_bytes(u.data)
    assert "adapter_defect" not in {i["code"] for i in doc.seal.get("issues", [])}
    (te,) = [r for r in doc.records if r["k"] == "tool_execution"]
    assert te["name"] == name
    if name != "get_x":
        assert te["unk"]["/name"] == "ambiguous"
    else:
        assert "/name" not in te.get("unk", {})
