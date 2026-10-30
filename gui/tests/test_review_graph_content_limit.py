"""GR-29 (design §6.6): the graph popover and inspector truncate shown content at the Settings viewer limit, like the
PROV-JSON and AER tabs, both from the start and after Settings changes it; never at a fixed 500."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentprov.render.graph import build_model

from _corpus_support import first_prov, poison

PAYLOAD = "lo" + "ng " * 700 + "tail"


def test_graph_takes_the_viewer_limit(qapp: Any) -> None:
    from agentprov_gui.ui.viewer import ViewerPage

    v = ViewerPage([], None, content_limit=2000)
    assert v.preview.graph.content_limit == 2000
    v.set_show_content_limit(100)
    assert v.preview.graph.content_limit == 100
    v.preview.graph.content_cb.setChecked(True)
    assert v.preview.graph.show_content and v.preview.graph.content_limit == 100
    v.set_show_content_limit(10_000)
    assert v.preview.graph.content_limit == v.content_limit and v.preview.graph.show_content  # clamped; the switch is kept


def test_graph_inspector_truncates_at_the_viewer_limit(qapp: Any, mini_corpus: Path) -> None:
    from agentprov_gui.graph.viewgraph import full_view
    from agentprov_gui.ui.graphview import attribute_text
    from agentprov_gui.ui.viewer import ViewerPage

    ex, doc = first_prov(mini_corpus)
    bad, placed = poison(doc, [PAYLOAD])
    assert placed
    view = full_view(build_model(bad, ex=ex, mode="all"))
    key, name = next((n.key, k) for n in view.model.nodes for k, v in n.attrs.items() if v == PAYLOAD)
    v = ViewerPage([], None, content_limit=2000)
    g = v.preview.graph
    g.view_graph, g.locator = view, "prov/x/aa/ex_1.prov.json"
    g.content_cb.setChecked(True)
    g._selected = key
    g._fill_inspector(key)
    for limit in (2000, 100):
        if limit != 2000:
            v.set_show_content_limit(limit)  # refreshes the inspector of the selected node
        r = next(i for i in range(g.inspector.rowCount()) if g.inspector.item(i, 0).text() == name)
        locator = f"{g.locator}#{key}/{name}"
        assert g.inspector.item(r, 1).text() == attribute_text(PAYLOAD, True, limit, locator)
        assert dict(g._rows_for(key))[name] == attribute_text(PAYLOAD, True, limit, locator)
