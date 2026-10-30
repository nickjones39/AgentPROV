"""Viewer execution tabs (D-840..D-845): open, focus, close, the cap and its eviction order, live graph scenes, corpus
switching, Reload Execution, keys and menus, escaped tab titles, accessible names, and no write inside a corpus."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from _corpus_support import tree_state
from test_viewer import wait, window  # noqa: F401  (the window fixture)


def _open_corpus(qapp: Any, w: Any, corpus: Path) -> Any:
    v = w.viewer
    v.open_path(corpus)
    wait(qapp, lambda: v.table is not None and v.model.rowCount() > 0
         and v.summary is not None and v.summary.path.name.startswith(corpus.name))
    return v


def _ready(qapp: Any, pane: Any) -> Any:
    wait(qapp, lambda: pane.state == "ready" and pane.graph.scene_ is not None)
    return pane


def test_open_focus_and_the_corpora_tab(qapp: Any, window: Any, mini_corpus: Path) -> None:  # noqa: F811
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QTabBar

    from agentprov_gui.ui.execution import ExecutionPane

    v = _open_corpus(qapp, window, mini_corpus)
    assert v.doc_tabs.count() == 1 and v.doc_tabs.tabText(0) == "Corpora"
    for side in (QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide):
        assert v.doc_tabs.tabBar().tabButton(0, side) is None  # D-840: not closable
    # a double-click opens a tab and shows it
    v.exec_view.doubleClicked.emit(v.model.index(0, 0))
    pane = v.doc_tabs.currentWidget()
    assert isinstance(pane, ExecutionPane) and not pane.compact and v.doc_tabs.count() == 2
    _ready(qapp, pane)
    assert pane.ex == v.table.ex(v.model.table_row(0))
    assert v.doc_tabs.tabText(1).startswith(pane.ex[:5]) and "1 of 12 open" in v.tab_count.text()
    # opening it again focuses the same tab, from the Corpora tab too
    v.show_corpora()
    assert v.open_row(0) is pane and v.doc_tabs.currentWidget() is pane and v.doc_tabs.count() == 2
    # Return in the table opens the selected row
    v.show_corpora()
    v.exec_view.setFocus()
    v.exec_view.selectRow(1)
    QTest.keyClick(v.exec_view, Qt.Key.Key_Return)
    assert v.doc_tabs.count() == 3 and v.doc_tabs.currentWidget().ex == v.table.ex(v.model.table_row(1))
    # the Corpora tab stays first when a tab is dragged in front of it
    v.doc_tabs.tabBar().moveTab(2, 0)
    assert v.doc_tabs.widget(0) is v.browser


def test_graph_and_prov_json_side_by_side_and_linked(qapp: Any, window: Any, mini_corpus: Path) -> None:  # noqa: F811
    v = _open_corpus(qapp, window, mini_corpus)
    pane = _ready(qapp, v.open_row(0))
    assert pane.tabs.tabText(0) == "Graph + PROV-JSON"
    assert [pane.tabs.tabText(i) for i in range(1, pane.tabs.count())] == \
        ["AER", "SEM", "Register", "Validation", "Raw", "Index Row"]
    assert pane.graph.isVisible() and pane.prov.isVisible()  # both on the first sub-tab
    assert pane.prov.tree.topLevelItemCount() == 1
    # graph → PROV-JSON: "Show in PROV-JSON" selects the statement without leaving the sub-tab
    key = next(k for k in pane.graph.scene_.nodes if pane.prov.reveal(k))
    pane.prov.tree.setCurrentItem(None)
    pane.graph.select(key)
    pane.graph.prov_btn.click()
    assert pane.tabs.currentIndex() == 0 and pane.prov.tree.currentItem() is not None
    # PROV-JSON → graph
    pane.graph.select(None)
    pane.prov.statement_selected.emit(key)
    assert pane.graph._selected == key
    # S2: content is off in a new tab
    assert not pane.prov.show_cb.isChecked() and not pane.aer.show_cb.isChecked() and not pane.graph.show_content


def test_close_tabs_and_keys(qapp: Any, window: Any, mini_corpus: Path) -> None:  # noqa: F811
    v = _open_corpus(qapp, window, mini_corpus)
    a, b, c = (v.open_row(i) for i in range(3))
    assert v.doc_tabs.count() == 4
    assert not v.close_tab(0) and v.doc_tabs.count() == 4  # the Corpora tab never closes
    # ⌘W closes the current execution tab (the action, as the menu and the key trigger it)
    v.doc_tabs.setCurrentWidget(c)
    window.action_map["closeTab"].trigger()
    assert v.doc_tabs.count() == 3 and c not in v.exec_tabs.values() and window.isVisible()
    # ⌥⌘W keeps the current one
    v.doc_tabs.setCurrentWidget(b)
    window.action_map["closeOtherTabs"].trigger()
    assert list(v.exec_tabs.values()) == [b] and v.doc_tabs.count() == 2
    # next / previous tab wrap around
    window.action_map["nextTab"].trigger()
    assert v.doc_tabs.currentIndex() == 0
    window.action_map["previousTab"].trigger()
    assert v.doc_tabs.currentWidget() is b
    window.action_map["corporaTab"].trigger()
    assert v.doc_tabs.currentIndex() == 0
    # ⌘W on the Corpora tab closes the window, as before
    window.action_map["closeTab"].trigger()
    assert not window.isVisible()
    del a


def test_shortcuts(qapp: Any, window: Any) -> None:  # noqa: F811
    import sys

    from PySide6.QtGui import QKeySequence

    shortcut = {k: [s.toString() for s in window.action_map[k].shortcuts()] for k in
                ("closeTab", "closeOtherTabs", "closeWindow", "nextTab", "previousTab")}
    assert "Ctrl+W" in shortcut["closeTab"]
    assert shortcut["closeOtherTabs"] == ["Ctrl+Alt+W"] and shortcut["closeWindow"] == ["Ctrl+Shift+W"]
    if sys.platform == "darwin":  # ⌘⇧] / ⌘⇧[, never ⌘Tab (the app switcher)
        assert "Ctrl+}" in shortcut["nextTab"] and "Ctrl+{" in shortcut["previousTab"]
    else:
        assert shortcut["nextTab"] == ["Ctrl+PgDown"] and shortcut["previousTab"] == ["Ctrl+PgUp"]
    assert all("Ctrl+Tab" not in s for s in shortcut.values())
    assert QKeySequence("Ctrl+W").toString() == "Ctrl+W"


def test_the_cap_closes_the_least_recently_viewed(qapp: Any, window: Any, mini_corpus: Path,  # noqa: F811
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.ui import viewer as viewer_mod

    monkeypatch.setattr(viewer_mod, "MAX_TABS", 2)
    v = _open_corpus(qapp, window, mini_corpus)
    messages: list[str] = []
    v.status_message.connect(messages.append)
    first, second = v.open_row(0), v.open_row(1)
    v.doc_tabs.setCurrentWidget(first)  # now `second` is the least recently viewed
    v.show_corpora()
    third = v.open_row(2)
    assert set(v.exec_tabs.values()) == {first, third} and second not in v.exec_tabs.values()
    assert v.doc_tabs.count() == 3 and any("Closed the tab of" in m and "at most 2" in m for m in messages)
    # opening from the current tab (the menu) closes the least recently viewed other tab, never the current one
    v.doc_tabs.setCurrentWidget(first)  # viewed: third, then first
    fourth = v.open_row(1)
    assert set(v.exec_tabs.values()) == {first, fourth} and third not in v.exec_tabs.values()


def test_only_recent_tabs_keep_a_live_scene(qapp: Any, window: Any, mini_corpus: Path,  # noqa: F811
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.ui import viewer as viewer_mod

    monkeypatch.setattr(viewer_mod, "LIVE_SCENES", 1)
    v = _open_corpus(qapp, window, mini_corpus)
    a = _ready(qapp, v.open_row(0))
    b = _ready(qapp, v.open_row(1))
    assert a.graph.scene_ is None and a.graph.released and a.graph.result is not None  # layout kept
    assert b.graph.scene_ is not None
    v.doc_tabs.setCurrentWidget(a)  # rebuilt from the kept layout, no new layout job
    assert a.graph.scene_ is not None and not a.graph.released
    assert b.graph.scene_ is None and b.graph.released


def test_tabs_survive_another_corpus_and_name_it(qapp: Any, window: Any, mini_corpus: Path,  # noqa: F811
                                                 derived_corpus: Path) -> None:
    v = _open_corpus(qapp, window, mini_corpus)
    mini_tab = _ready(qapp, v.open_row(0))
    assert " · " not in v.doc_tabs.tabText(1)  # one corpus: no corpus name in the title
    v = _open_corpus(qapp, window, derived_corpus)
    assert mini_tab in v.exec_tabs.values() and mini_tab.detail is not None  # kept, as a snapshot
    derived_tab = _ready(qapp, v.open_row(0))
    assert derived_tab is not mini_tab and v.doc_tabs.count() == 3
    titles = [v.doc_tabs.tabText(i) for i in (1, 2)]
    assert all(" · " in t for t in titles)  # two corpora: the corpus name is added
    # Show in Corpora on the first tab opens its corpus again and selects its row
    v.reveal_in_corpora(mini_tab)
    wait(qapp, lambda: v.summary is not None and v.summary.path.name.startswith(mini_corpus.name)
         and v.table is not None and v.exec_view.currentIndex().isValid())
    assert v.doc_tabs.currentIndex() == 0
    assert v.table.ex(v.model.table_row(v.exec_view.currentIndex().row())) == mini_tab.ex


def test_reload_execution_and_a_missing_corpus(qapp: Any, window: Any, corpus_copy: Path) -> None:  # noqa: F811
    v = _open_corpus(qapp, window, corpus_copy)
    pane = _ready(qapp, v.open_row(0))
    before = pane.detail
    pane.reload()
    assert pane.state == "loading"
    wait(qapp, lambda: pane.state == "ready" and pane.detail is not before)
    assert pane.detail.ex == before.ex
    shutil.rmtree(corpus_copy.with_name("mini.partial"))  # the test's own temporary copy
    kept = pane.detail
    pane.reload()
    wait(qapp, lambda: pane.state == "ready" and "cannot be reloaded" in pane.title.text())
    assert pane.detail is kept  # the earlier snapshot stays


def test_closing_a_loading_tab_is_safe(qapp: Any, window: Any, mini_corpus: Path) -> None:  # noqa: F811
    v = _open_corpus(qapp, window, mini_corpus)
    v.cache.clear()
    pane = v.open_row(0)
    assert pane.state == "loading"
    assert v.close_tab(v.doc_tabs.indexOf(pane))
    wait(qapp, lambda: not v.pool.activeThreadCount())
    for _ in range(20):
        qapp.processEvents()
    assert v.exec_tabs == {} and v.doc_tabs.count() == 1


def test_tabs_write_nothing_inside_a_corpus(qapp: Any, window: Any, mini_corpus: Path) -> None:  # noqa: F811
    before = tree_state(mini_corpus.parent)
    v = _open_corpus(qapp, window, mini_corpus)
    panes = [_ready(qapp, v.open_row(i)) for i in range(v.model.rowCount())]
    panes[0].reload()
    wait(qapp, lambda: panes[0].state == "ready")
    v.close_other_tabs(panes[0])
    assert tree_state(mini_corpus.parent) == before


def test_tab_titles_are_escaped_and_elided(qapp: Any, window: Any, mini_corpus: Path) -> None:  # noqa: F811
    from agentprov_gui.ui.viewer import elide_middle

    assert elide_middle("ex_22nv7qrg2ritadahmj5xqaiqzd") == "ex_22nv7q…mj5xqaiqzd"
    assert len(elide_middle("x" * 80)) == 20 and elide_middle("ex_0001") == "ex_0001"
    v = _open_corpus(qapp, window, mini_corpus)
    pane = _ready(qapp, v.open_row(0))
    real = pane.ex
    pane.ex = "a&b" + chr(0x202E) + "c" + chr(10) + "d"  # assembled at run time (K.4.2)
    v._refresh_tabs()
    title = v.doc_tabs.tabText(1)
    assert "&&" in title and chr(0x202E) not in title and chr(10) not in title
    assert chr(0x202E) not in v.doc_tabs.tabBar().accessibleTabName(1)
    pane.ex = real


def test_tab_controls_are_named(qapp: Any, window: Any, mini_corpus: Path) -> None:  # noqa: F811
    from PySide6.QtWidgets import QAbstractButton, QAbstractItemView, QComboBox, QTabBar, QWidget

    v = _open_corpus(qapp, window, mini_corpus)
    pane = _ready(qapp, v.open_row(0))
    bar = v.doc_tabs.tabBar()
    assert v.doc_tabs.accessibleName() == "Viewer tabs" and bar.accessibleTabName(0) == "Corpora browser"
    assert bar.accessibleTabName(1) == f"Execution {pane.ex} in corpus mini, ready"
    buttons = [bar.tabButton(1, s) for s in (QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide)]
    assert [b.accessibleName() for b in buttons if b is not None] == [f"Close {pane.ex}"]
    unnamed = [type(w).__name__ for w in pane.findChildren(QWidget)
               if isinstance(w, QAbstractButton | QAbstractItemView | QComboBox) and not w.accessibleName()
               and not (isinstance(w, QAbstractButton) and w.text())
               and not isinstance(w.parent(), QAbstractItemView | QComboBox)
               and type(w).__name__ not in ("QListView", "QToolButton")]
    assert not unnamed, unnamed
