"""GR-53 (GR-9 follow-up): after Show content is turned off, the PROV-JSON tree keeps no fenced content anywhere.
A statement that was collapsed when the switch went off, and an attribute whose name is escaped or longer than the
displayed line, must both show the placeholder again."""

from __future__ import annotations

from typing import Any

FENCE = "<<" + "UNTRUSTED"


def _tab_and_statement() -> tuple[Any, Any, list[str]]:
    from PySide6.QtCore import Qt

    from agentprov_gui.ui.detail import ProvJsonTab

    rlo = chr(0x202E)
    content = "pay" + "load " + "x" * 25
    names = ["apv:na" + rlo + "me", "apv:" + "n" * 90, "prov:value"]
    attrs: dict[str, Any] = {n: content for n in names}
    attrs["prov:type"] = "prov:Entity"
    doc = {"prefix": {"ex": "http://e/"}, "bundle": {"ex:b.core.1": {"entity": {"ex:m1": attrs}}}}
    tab = ProvJsonTab()
    tab.set_documents({"agentprov-prov/0.1": (doc, "{}", "prov/x.prov.json", 2)}, 4000)
    for item in list(tab._iter_items()):
        p = item.data(0, Qt.ItemDataRole.UserRole)
        if p and p[0] == "section":
            item.setExpanded(True)
    stmt = next(i for i in tab._iter_items() if (i.data(0, Qt.ItemDataRole.UserRole) or ("",))[0] == "statement")
    return tab, stmt, names


def _values(stmt: Any) -> list[str]:
    return [stmt.child(i).text(1) for i in range(stmt.childCount())]


def test_escaped_and_long_attribute_names_go_back_to_the_placeholder(qapp: Any) -> None:
    tab, stmt, names = _tab_and_statement()
    tab.show_cb.setChecked(True)
    stmt.setExpanded(True)
    assert sum(v.startswith(FENCE) for v in _values(stmt)) == len(names)
    tab.show_cb.setChecked(False)
    assert not any(FENCE in v for v in _values(stmt)), _values(stmt)
    tab.close()


def test_collapsed_statement_reexpanded_after_toggle_off_shows_no_content(qapp: Any) -> None:
    tab, stmt, names = _tab_and_statement()
    tab.show_cb.setChecked(True)
    stmt.setExpanded(True)
    stmt.setExpanded(False)
    tab.show_cb.setChecked(False)
    stmt.setExpanded(True)
    values = _values(stmt)
    assert not any(FENCE in v for v in values), values
    assert sum(v.startswith("‹text, ") for v in values) == len(names), values
    tab.show_cb.setChecked(True)  # and back on: the collapsed statement is fenced again
    assert sum(v.startswith(FENCE) for v in _values(stmt)) == len(names)
    tab.close()
