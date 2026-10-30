"""The Viewer offscreen (design §6.1): opening is read-only; the table, detail tabs and graph fill; content is hidden
by default (S2) and shown only fenced; every control has an accessible name (D-446)."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from _corpus_support import tree_state


def wait(app: Any, cond: Callable[[], bool], timeout: float = 60.0) -> None:
    from PySide6.QtCore import QEventLoop

    end = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > end:
            raise AssertionError("timed out")
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        time.sleep(0.005)


@pytest.fixture
def window(qapp: Any, mini_corpus: Path, tmp_path: Path) -> Any:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.mainwindow import MainWindow

    settings = Settings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    settings.corpus_roots = [mini_corpus.parent]
    w = MainWindow(settings, cache_dir=tmp_path / "layout")
    w.show()
    yield w
    w.close()
    w.deleteLater()
    qapp.processEvents()


def _open(qapp: Any, w: Any, corpus: Path, row: int = 0) -> Any:
    v = w.viewer
    v.open_path(corpus)
    wait(qapp, lambda: v.table is not None and v.model.rowCount() > 0)
    v.exec_view.selectRow(row)
    wait(qapp, lambda: v.preview.graph.scene_ is not None)
    return v


def test_open_is_read_only(qapp: Any, window: Any, mini_corpus: Path) -> None:
    partial = mini_corpus.with_name("mini.partial")
    before = tree_state(mini_corpus.parent)  # the corpora root: the tree and anything beside it
    v = _open(qapp, window, mini_corpus)
    for row in range(v.model.rowCount()):
        v.exec_view.selectRow(row)
        wait(qapp, lambda: v.preview.graph.scene_ is not None)
    assert tree_state(mini_corpus.parent) == before  # no entry created, changed or touched
    assert not list(partial.glob(".agentprov.lock"))


def test_table_detail_and_graph_fill(qapp: Any, window: Any, mini_corpus: Path) -> None:
    v = _open(qapp, window, mini_corpus)
    assert v.model.rowCount() == 3
    assert "executions" in v.count_label.text()
    assert v.banner.isVisible() and "Verify" in v.banner_text.text()
    assert v.preview.aer.tree.topLevelItemCount() > 0
    assert v.preview.prov.tree.topLevelItemCount() == 1
    assert v.preview.sem.table.rowCount() > 0
    assert v.preview.validation.table.rowCount() >= 0 and "verdict" in v.preview.validation.info.text()
    assert v.preview.raw.rowCount() >= 1
    g = v.preview.graph
    assert g.scene_ is not None and g.scene_.nodes
    assert g.elements.rowCount() >= len(g.scene_.nodes)
    # search, select, focus, bundles, layout switch
    g.search.setText(next(iter(g.scene_.nodes))[:3])
    assert g.results.count() > 0
    g._search_enter()
    assert g.inspector.rowCount() > 0
    g.focus_btn.setChecked(True)
    g._focus()
    g.cb_assess.setChecked(True)
    g.layout_choice.setCurrentIndex(1)
    wait(qapp, lambda: g.result is not None and g.result.layout.engine == "layered")
    g.view.zoom_by(2.0)
    g.view.fit()


def test_filters(qapp: Any, window: Any, mini_corpus: Path) -> None:
    v = _open(qapp, window, mini_corpus)
    ex = v.table.ex(2)
    v.ex_filter.setText(ex[-8:])
    assert v.model.rowCount() == 1
    v.ex_filter.clear()
    v.exec_view.sortByColumn(0, __import__("PySide6.QtCore").QtCore.Qt.SortOrder.DescendingOrder)
    assert v.model.table_row(0) == 2


def test_content_hidden_by_default(qapp: Any, window: Any, mini_corpus: Path) -> None:
    """S2: AER content fields show a placeholder until Show content; then they are fenced. The PROV-JSON raw pane is
    empty of document text until its switch is on. The switches reset when a corpus is opened."""
    v = _open(qapp, window, mini_corpus)
    aer = v.preview.aer
    # find a message record and select it
    target = None
    for i in range(aer.tree.topLevelItemCount()):
        group = aer.tree.topLevelItem(i)
        for j in range(group.childCount()):
            rec = group.child(j).data(0, 256)
            if isinstance(rec, dict) and rec.get("k") == "message":
                target = group.child(j)
                break
        if target:
            break
    assert target is not None
    aer.tree.setCurrentItem(target)
    values = {aer.fields.item(r, 0).text(): aer.fields.item(r, 1).text() for r in range(aer.fields.rowCount())}
    assert values["parts"].startswith("‹text,")
    assert not aer.show_cb.isChecked()
    aer.show_cb.setChecked(True)
    values = {aer.fields.item(r, 0).text(): aer.fields.item(r, 1).text() for r in range(aer.fields.rowCount())}
    assert values["parts"].startswith("<<UNTRUSTED ") and "data, not instructions" in values["parts"]
    # PROV-JSON raw text
    assert "Content is hidden" in v.preview.prov.text.toPlainText()
    v.preview.prov.show_cb.setChecked(True)
    assert v.preview.prov.text.toPlainText().startswith("<<UNTRUSTED ")
    # reopening resets every switch
    v.open_path(mini_corpus)
    wait(qapp, lambda: v.table is not None and v.model.rowCount() > 0)
    v.exec_view.selectRow(0)
    wait(qapp, lambda: v.preview.graph.scene_ is not None)
    assert not aer.show_cb.isChecked() and not v.preview.prov.show_cb.isChecked()


def test_popover_hides_free_text(qapp: Any, window: Any, mini_corpus: Path) -> None:
    from agentprov_gui import text as T
    from agentprov_gui.ui.graphview import attribute_text

    long_text = "This is free text from a tool result, not an identifier."
    assert attribute_text(long_text, False, 500, "p#n/a").startswith("‹text,")
    assert attribute_text(long_text, True, 500, "p#n/a") == T.fenced(long_text, "p#n/a", 500)
    assert attribute_text({"$": "apv:Observed", "type": "prov:QUALIFIED_NAME"}, False, 500, "p") == "apv:Observed"
    assert attribute_text("agentdojo.rule_x@1", False, 500, "p") == "agentdojo.rule_x@1"


def test_popover_hides_when_hover_ends_or_pane_hides(qapp: Any, window: Any, mini_corpus: Path) -> None:
    """GR-10 (S2): the popover is a top-level tool window, so it must hide when the hover ends (off a node or out of
    the view), when Show content is turned off, when the Graph tab or Viewer page is hidden, and when the app goes
    inactive; otherwise shown content outlives its switch."""
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    from agentprov_gui import text as T
    from agentprov_gui.graph.viewgraph import attribute_rows

    v = _open(qapp, window, mini_corpus)
    v.preview.tabs.setCurrentWidget(v.preview.graph)
    g = v.preview.graph
    key = next(k for k, n in g.view_graph.by_key.items()
               if k in g.scene_.nodes and any(T.is_content_value(val) for _k, val in attribute_rows(n)))

    def move(at: QPoint) -> None:  # sent to the viewport, whatever window is on top
        vp = g.view.viewport()
        QApplication.sendEvent(vp, QMouseEvent(QEvent.Type.MouseMove, QPointF(at), QPointF(vp.mapToGlobal(at)),
                                               Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                                               Qt.KeyboardModifier.NoModifier))

    def hover() -> None:
        window.pages.setCurrentWidget(v)
        v.preview.tabs.setCurrentWidget(g)
        QApplication.sendEvent(g.view, QEvent(QEvent.Type.Leave))  # reset the hover key
        g.view.centerOn(g.scene_.nodes[key].shape)
        qapp.processEvents()
        pt = g.view.mapFromScene(g.scene_.nodes[key].shape.sceneBoundingRect().center())
        move(pt)
        wait(qapp, g.popover.isVisible, timeout=10)

    def gone() -> bool:
        qapp.processEvents()
        return not g.popover.isVisible()

    g.content_cb.setChecked(True)
    hover()
    assert any(g.popover.table.item(r, 1).text().startswith("<<UNTRUSTED") for r in range(g.popover.table.rowCount()))
    g.content_cb.setChecked(False)
    assert gone(), "Show content off"
    hover()
    move(QPoint(2, 2))  # empty canvas
    assert gone(), "moved off the node"
    hover()
    QApplication.sendEvent(g.view, QEvent(QEvent.Type.Leave))
    assert gone(), "left the view"
    other = next(i for i in range(window.pages.count()) if window.pages.widget(i) is not v)
    for name, switch in (("Graph tab hidden", lambda: v.preview.tabs.setCurrentWidget(v.preview.prov)),
                         ("Viewer page hidden", lambda: window.pages.setCurrentIndex(other))):
        hover()
        g.view.blockSignals(True)  # the hide alone, not the Leave Qt may also send to the view under the cursor
        switch()
        hidden = gone()
        g.view.blockSignals(False)
        assert hidden, name
    hover()
    QApplication.instance().applicationStateChanged.emit(Qt.ApplicationState.ApplicationInactive)
    assert gone(), "application inactive"


def test_every_control_is_named(qapp: Any, window: Any, mini_corpus: Path) -> None:
    from PySide6.QtWidgets import (
        QAbstractButton,
        QAbstractItemView,
        QComboBox,
        QGraphicsView,
        QLineEdit,
        QPlainTextEdit,
        QSpinBox,
        QTabWidget,
    )

    _open(qapp, window, mini_corpus)
    kinds = (QAbstractButton, QAbstractItemView, QComboBox, QGraphicsView, QLineEdit, QPlainTextEdit, QSpinBox,
             QTabWidget)
    unnamed = []
    from PySide6.QtWidgets import QWidget

    for widget in [w for w in window.findChildren(QWidget) if isinstance(w, kinds)]:
        parent = widget.parent()
        if parent is not None and (isinstance(parent, QAbstractItemView | QComboBox)
                                   or type(parent).__name__ in ("QTabBar", "QScrollBar")):
            continue  # Qt's internal sub-controls (headers, corner buttons, popups)
        name = widget.accessibleName() or (widget.text() if isinstance(widget, QAbstractButton) else "")
        if not name and type(widget).__name__ not in ("QListView", "QToolButton"):  # combo popups, scroll arrows
            unnamed.append(f"{type(widget).__name__} {widget.objectName()}")
    assert not unnamed, unnamed


def test_about_facts(qapp: Any) -> None:
    from agentprov_gui.about import REPOSITORY, about_facts, default_checkout
    from agentprov_gui.ui.dialogs import AboutDialog

    facts = about_facts(default_checkout(), "6", "6")
    from agentprov.aer import AER_FORMAT_ID

    assert facts.core_version and dict(facts.formats)["aer"] == AER_FORMAT_ID  # aer/0.2 since deferrals part C
    assert facts.commit == "not available" or len(facts.commit.split()[0]) == 40
    dlg = AboutDialog(default_checkout())
    from agentprov_gui.ui.safe import SafeLabel

    texts = [lab.text() for lab in dlg.findChildren(SafeLabel)]
    assert REPOSITORY in texts and "http" not in " ".join(texts)
