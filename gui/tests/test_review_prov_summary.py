"""GR-8 (S2): the PROV-JSON tree's statement summary shows grammar-checked tokens only, never free text, whatever
the Show content switch says."""

from __future__ import annotations

from typing import Any

import pytest

SECRET = "free text " + "that must stay hidden"
RULE = "rule slot " + "free text"


def _summaries(attrs: dict[str, Any]) -> list[str]:
    from agentprov_gui.ui.detail import ProvJsonTab

    tab = ProvJsonTab()
    doc = {"prefix": {}, "entity": {"ex:m1": dict(attrs)},
           "bundle": {"urn:b.core.1": {"activity": {"ex:a1": dict(attrs)}}}}
    tab.set_documents({"agentprov-prov/0.1": (doc, "{}", "prov/x.prov.json", 2)}, 500)
    assert not tab.show_cb.isChecked()
    for _ in range(3):  # expand every level: document, bundle, section
        for item in list(tab._iter_items()):
            item.setExpanded(True)
    out = [item.text(1) for item in tab._iter_items()
           if (item.data(0, 256) or ("",))[0] == "statement"]
    assert len(out) == 2
    return out


@pytest.mark.parametrize("ptype", [
    SECRET,
    {"$": SECRET, "type": "xsd:string"},
    [{"$": "apv:X", "type": "prov:QUALIFIED_NAME"}, SECRET],
    {"$": SECRET, "lang": "en"},
    {"$": SECRET, "type": "prov:QUALIFIED_NAME"},
])
def test_summary_hides_free_text(qapp: Any, ptype: Any) -> None:
    for text in _summaries({"prov:type": ptype, "apv:rule": RULE}):
        assert "hidden" not in text and "rule slot" not in text, text
        assert "(rule)" in text


def test_summary_shows_grammar_tokens(qapp: Any) -> None:
    attrs = {"prov:type": {"$": "apv:ToolCall", "type": "prov:QUALIFIED_NAME"}, "apv:rule": "agentprov.core.call@1"}
    for text in _summaries(attrs):
        assert text == "apv:ToolCall · agentprov.core.call@1"
