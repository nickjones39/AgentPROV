"""D-1060: the Viewer's three panes (the user's 2026-11-05 design), on the derived mini corpus (``derived_corpus``).

* The corpora list is a source list grouped by state (each heading with its count), each row the corpus's name and its
  execution count; choosing a row opens the corpus; a filter box narrows it. Corpus Details shows what the corpora
  table showed.
* The filters are chips: every facet's chip makes the same selection, and so the same ``agentprov stats --select``
  argv, as the old picker for that value; + Add filter lists each facet's values with how many executions each would
  show.
* The inspector's segmented control shows the same views the detail tabs showed.
* The side panes collapse to a labelled strip and open again from the toolbar button, the View menu and the strip;
  their states and widths are remembered; a narrow window collapses the inspector first; the shortcuts are unique.
* No pane needs more width than it gets at 1200 px.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from agentprov_gui.readmodel.executions import TableFilter, cli_selection
from test_viewer import choose_filter, wait

ATTACK = "outcome.attack_succeeded"


def _window(qapp: Any, tmp_path: Path, roots: list[Path], width: int = 1400) -> Any:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.mainwindow import MainWindow

    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    settings.corpus_roots = roots
    w = MainWindow(settings, cache_dir=tmp_path / "cache", home=tmp_path / "home")
    w.resize(width, 900)
    w.show()
    qapp.processEvents()
    return w


def _close(qapp: Any, w: Any) -> None:
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(30_000)
    qapp.processEvents()
    w.close()
    w.deleteLater()
    qapp.processEvents()


@pytest.fixture
def window(qapp: Any, tmp_path: Path, derived_corpus: Path) -> Any:
    w = _window(qapp, tmp_path, [derived_corpus.parent])
    yield w
    _close(qapp, w)


def _open(qapp: Any, window: Any, corpus: Path) -> Any:
    v = window.viewer
    v.open_path(corpus)
    wait(qapp, lambda: v.table is not None and v.model.rowCount() == 3)
    return v


def test_three_panes_and_the_corpora_source_list(qapp: Any, tmp_path: Path, corpus_copy: Path,
                                                 derived_corpus: Path) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    broken = corpus_copy.parent / "broken"  # a corpus.json the core cannot read: its own group
    broken.mkdir()
    (broken / "corpus.json").write_text("not json", encoding="utf-8")
    w = _window(qapp, tmp_path, [corpus_copy.parent, derived_corpus.parent])
    try:
        v = w.viewer
        assert [v.pane_split.widget(i) for i in range(3)] == [v.corpora_pane, v.middle, v.inspector_pane]
        assert v.pane_split.handleWidth() == 1  # 1 px dividers (HIG)
        lst = v.corpora_list
        rows = [(lst.item(i).text(), lst.item(i).data(v.corpora_list.itemDelegate().COUNT_ROLE),
                 bool(lst.item(i).flags() & Qt.ItemFlag.ItemIsSelectable)) for i in range(lst.count())]
        assert rows == [("WORKING · 2", None, False), ("derived", "3", True), ("mini", "3", True),
                        ("UNREADABLE · 1", None, False), ("broken", "—", True)]
        # the arrow keys move between corpora (headings are never current) and choosing one opens it
        lst.setFocus()
        lst.setCurrentRow(1)
        QTest.keyClick(lst, Qt.Key.Key_Down)
        assert lst.currentItem().text() == "mini"
        wait(qapp, lambda: v.table is not None and v.summary is not None and v.summary.name == "mini")
        assert v.corpus_title.full_text() == "mini" and v.count_label.full_text() == "3 executions"
        assert v.corpora_pane.strip.label == "CORPORA · mini"
        # the filter box narrows the list; the open corpus stays selected without opening it again
        v.corpora_filter.setText("MIN")
        assert [lst.item(i).text() for i in range(lst.count())] == ["WORKING · 1", "mini"]
        assert lst.currentItem().text() == "mini"
        v.corpora_filter.clear()
        # Corpus Details: the facts the corpora table showed
        details = v.show_details()
        assert details is not None and details.isVisible()
        facts = {k: details.facts.value(k) for k in details.facts.values}
        assert facts["Corpus"] == "mini" and facts["State"].endswith("working") and facts["Executions"] == "3"
        assert facts["Corpus id"] == (v.summary.corpus_id or "—") and facts["Folder"] == str(corpus_copy.parent)
        assert "corpus_version" in details.facts.names["Version"].toolTip()
        details.close()
        # an unreadable corpus opens to its notice, with its reason in Corpus Details
        lst.setCurrentRow(4)
        wait(qapp, lambda: v.summary is not None and v.summary.name == "broken")
        assert v.banner_badge.text() == "Cannot be opened" and v.state_badge.text() == "Unreadable"
        details = v.show_details()
        assert details.error.isVisibleTo(details) and "cannot be opened" in details.error.text()
        details.close()
        # AU-NG-4: every open reuses the one popover (a closed one is never left behind)
        from agentprov_gui.ui.viewer import CorpusDetails

        for _ in range(3):
            v.show_details().close()
            qapp.processEvents()
        assert len(v.findChildren(CorpusDetails)) == 1
    finally:
        _close(qapp, w)


def _expected(key: str, value: str) -> TableFilter:
    return TableFilter(issue_code=value) if key == "issue" else TableFilter(((key, frozenset({value})),))


def test_every_chip_selects_what_the_old_picker_selected(qapp: Any, window: Any, derived_corpus: Path) -> None:
    """For every facet and every value: the chip's selection and its stats argv are the old picker's."""
    from agentprov_gui.ui.viewer import FACETS, ISSUE

    v = _open(qapp, window, derived_corpus)
    final = os.path.realpath(derived_corpus)
    tried = 0
    for key in (*FACETS, ISSUE):
        if not v.filter_offered(key):
            continue
        for value, _label, count in v.filter_values(key):
            choose_filter(v, key, value)
            expected = _expected(key, value)
            assert v.model.filter == expected, (key, value)
            assert v.model.order == v.table.select(expected) and v.model.rowCount() == count
            assert v.cli_argv()[0] == ["stats", "--corpus", final, *cli_selection(expected)[0]]
            assert list(v.chips) == [key]
            v.chips[key].click()  # its × removes it
            assert v.model.filter == TableFilter() and not v.chips
            tried += 1
    assert tried >= 12  # status, completeness, source, record type, the task and outcome facets
    # several chips: the selection lists them in the old pickers' order, whatever order they were added in
    choose_filter(v, ATTACK, "true")
    choose_filter(v, "cell.suite", "banking")
    choose_filter(v, "status", "ok")
    old = TableFilter((("status", frozenset({"ok"})), ("cell.suite", frozenset({"banking"})),
                       (ATTACK, frozenset({"true"}))))
    assert v.model.filter == old and v.cli_argv()[0][3:] == cli_selection(old)[0]
    choose_filter(v, "cell.suite", "workspace")  # another value of the same facet replaces it
    assert dict(v.model.filter.pickers)["cell.suite"] == frozenset({"workspace"}) and v.model.rowCount() == 0
    v.clear_filters_btn.click()
    assert v.model.filter == TableFilter() and v.model.rowCount() == 3 and not v.clear_filters_btn.isVisibleTo(v)


def test_add_filter_lists_values_with_counts(qapp: Any, window: Any, derived_corpus: Path) -> None:
    v = _open(qapp, window, derived_corpus)
    v.filter_menu.aboutToShow.emit()
    titles = [a.text() for a in v.filter_menu.actions()]
    assert titles[:4] == ["Status", "Completeness", "Source", "Record type"] and "Attack succeeded" in titles
    sub = next(a.menu() for a in v.filter_menu.actions() if a.data() == "cell.suite")
    sub.aboutToShow.emit()
    assert [a.text() for a in sub.actions()] == ["banking  (2)", "workspace  (1)"]
    # with another filter applied, a value counts the executions it would show beside it
    choose_filter(v, ATTACK, "true")
    for value, _label, count in v.filter_values("cell.suite"):
        both = TableFilter((("cell.suite", frozenset({value})), (ATTACK, frozenset({"true"}))))
        assert count == len(v.table.select(both))
    sub = next(a.menu() for a in v.filter_menu.actions() if a.data() == ATTACK)
    sub.aboutToShow.emit()
    texts = [a.text() for a in sub.actions()]
    assert texts[0] == "Remove the attack succeeded filter" and "yes  (1)" in texts
    assert next(a for a in sub.actions() if a.data() == "true").isChecked()


def test_the_inspector_shows_the_old_tabs_as_segments(qapp: Any, window: Any, derived_corpus: Path) -> None:
    v = _open(qapp, window, derived_corpus)
    v.exec_view.selectRow(0)
    pane = v.preview
    wait(qapp, lambda: pane.state == "ready")
    titles = ["Graph", "AER", "SEM", "PROV-JSON", "Register", "Validation", "Raw", "Index Row"]
    assert [pane.views.itemText(i) for i in range(pane.views.count())] == titles
    assert [pane.tabs.tabText(i) for i in range(pane.tabs.count())] == titles and not pane.tabs.tabBar().isVisible()
    widgets = [pane.graph, pane.aer, pane.sem, pane.prov, pane.register, pane.validation, pane.raw, pane.row_json]
    for i, widget in enumerate(widgets):
        pane.views.buttons[i].click()
        assert pane.tabs.currentWidget() is widget and widget.isVisibleTo(pane)
    pane.tabs.setCurrentIndex(1)  # and the other way round (⌃Tab, Show in PROV-JSON)
    assert pane.views.currentIndex() == 1
    assert not pane.aer.show_cb.isChecked() and not pane.prov.show_cb.isChecked()  # S2: content hidden
    assert pane.terminal is not None and pane.command_card.commands  # its inspect and render, in the disclosure
    assert v.inspector_pane.strip.label == f"EXECUTION · {pane.ex[:9]}…"


def test_collapse_and_reopen_by_button_menu_and_strip(qapp: Any, window: Any, derived_corpus: Path) -> None:
    from agentprov_gui.ui.viewer import STRIP

    v = _open(qapp, window, derived_corpus)
    corpora, inspector = v.corpora_pane, v.inspector_pane
    menu = window.action_map["toggleCorpora"]
    assert menu.text() == "Hide Corpora" and window.action_map["toggleInspector"].text() == "Hide Inspector"
    v.corpora_toggle.click()  # the toolbar button
    qapp.processEvents()
    assert not corpora.is_open() and corpora.strip.isVisibleTo(v) and not v.corpora_toggle.isChecked()
    assert corpora.width() == STRIP and menu.text() == "Show Corpora"
    menu.trigger()  # View › Show Corpora
    qapp.processEvents()
    assert corpora.is_open() and not corpora.strip.isVisibleTo(v) and corpora.width() > STRIP
    window.action_map["toggleInspector"].trigger()
    qapp.processEvents()
    assert not inspector.is_open() and inspector.strip.isVisibleTo(v)
    inspector.strip.click()  # the strip
    qapp.processEvents()
    assert inspector.is_open() and v.inspector_toggle.isChecked()
    # from an execution tab, the command shows the Corpora tab
    v.open_row(0)
    assert v.doc_tabs.currentIndex() == 1
    menu.trigger()
    assert v.doc_tabs.currentIndex() == 0 and not corpora.is_open()


def test_pane_states_and_widths_are_remembered(qapp: Any, tmp_path: Path, derived_corpus: Path) -> None:
    w = _window(qapp, tmp_path, [derived_corpus.parent])
    try:
        v = w.viewer
        v.set_pane_open("inspector", False)
        sizes = v.pane_split.sizes()
        v.pane_split.moveSplitter(sizes[0] + 60, 1)  # a wider corpora list
        qapp.processEvents()
        width = v.pane_split.sizes()[0]
        assert width > sizes[0]
    finally:
        _close(qapp, w)
    w = _window(qapp, tmp_path, [derived_corpus.parent])
    try:
        v = w.viewer
        qapp.processEvents()
        assert v.corpora_pane.is_open() and not v.inspector_pane.is_open()
        assert v.pane_split.sizes()[0] == width
    finally:
        _close(qapp, w)


def test_no_pane_is_wider_than_the_window_at_1200(qapp: Any, window: Any, derived_corpus: Path) -> None:
    from PySide6.QtWidgets import QScrollBar

    v = _open(qapp, window, derived_corpus)
    v.exec_view.selectRow(1)
    wait(qapp, lambda: v.preview.state == "ready")
    window.resize(1200, 860)
    qapp.processEvents()
    qapp.processEvents()
    assert window.width() == 1200 and window.minimumSizeHint().width() <= 1200
    assert v.corpora_pane.is_open() and v.inspector_pane.is_open()  # three panes fit at 1200
    for part in (v.corpora_pane.content, v.middle, v.inspector_pane.content, v.preview):
        assert part.minimumSizeHint().width() <= part.width(), part.accessibleName()
    for i in range(v.preview.views.count()):  # every view of the inspector fits it too
        v.preview.views.buttons[i].click()
        qapp.processEvents()
        widget = v.preview.tabs.currentWidget()
        assert widget.minimumSizeHint().width() <= v.preview.tabs.width(), v.preview.tabs.tabText(i)
    # the page itself never scrolls sideways (the table scrolls inside its own pane)
    bars = [b for b in v.browser.findChildren(QScrollBar) if b.orientation().name == "Horizontal" and b.isVisible()]
    assert all(b.parent() is not None and b.parent().parent() is not v.browser for b in bars)


def test_a_narrow_window_collapses_the_inspector_first(qapp: Any, window: Any, derived_corpus: Path) -> None:
    v = _open(qapp, window, derived_corpus)
    window.resize(1000, 860)
    qapp.processEvents()
    assert not v.inspector_pane.is_open() and v.inspector_pane.auto and v.corpora_pane.is_open()
    assert v.middle.width() >= v.middle.minimumWidth()
    # still reachable: opening it collapses the corpora list instead
    v.inspector_pane.strip.click()
    qapp.processEvents()
    assert v.inspector_pane.is_open() and not v.corpora_pane.is_open() and v.corpora_pane.auto
    assert v.middle.width() >= v.middle.minimumWidth()
    window.resize(1500, 860)
    qapp.processEvents()
    assert v.inspector_pane.is_open() and v.corpora_pane.is_open()  # wide again: both come back
    # the narrowest window: the inspector is a strip, and opening it still fits beside the middle
    window.resize(window.minimumWidth(), 860)
    qapp.processEvents()
    assert not v.inspector_pane.is_open() and v.middle.width() >= v.middle.minimumWidth()
    v.set_pane_open("inspector", True)
    qapp.processEvents()
    assert v.inspector_pane.is_open() and not v.corpora_pane.is_open()
    assert v.middle.width() >= v.middle.minimumWidth()
    assert sum(v.pane_split.sizes()) + 2 <= v.pane_split.width()  # nothing beyond the right edge


def test_pane_shortcuts_do_not_clash(qapp: Any, window: Any) -> None:
    from PySide6.QtGui import QAction, QKeySequence

    keys = [s.toString() for a in window.findChildren(QAction) for s in a.shortcuts() if not s.isEmpty()]
    assert len(keys) == len(set(keys)), sorted(k for k in keys if keys.count(k) > 1)
    assert window.action_map["toggleCorpora"].shortcut() == QKeySequence("Ctrl+Alt+1")
    assert window.action_map["toggleInspector"].shortcut() == QKeySequence("Ctrl+Alt+I")


def test_tab_moves_through_the_panes_in_order(qapp: Any, window: Any, derived_corpus: Path) -> None:
    """Tab goes left to right: the corpora list, its filter, the middle's controls and table (Tab leaves the table; the
    arrows move inside it), then the inspector; Shift+Tab goes back."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    v = _open(qapp, window, derived_corpus)
    v.exec_view.selectRow(1)
    wait(qapp, lambda: v.preview.state == "ready")
    window.activateWindow()
    v.corpora_list.setFocus()
    qapp.processEvents()
    seen: list[Any] = []
    for _ in range(40):
        widget = QApplication.focusWidget()
        seen.append(widget)
        if v.inspector_pane.isAncestorOf(widget):
            break
        QTest.keyClick(widget, Qt.Key.Key_Tab)
        qapp.processEvents()
    order = [s for s in (v.corpora_list, v.corpora_filter, v.details_btn, v.add_filter_btn, v.exec_view,
                         v.terminal.button) if s in seen]
    assert order == [v.corpora_list, v.corpora_filter, v.details_btn, v.add_filter_btn, v.exec_view, v.terminal.button]
    assert seen.index(v.exec_view) < seen.index(v.terminal.button) and seen[-1] is v.preview.open_btn
    QTest.keyClick(v.preview.open_btn, Qt.Key.Key_Tab)
    assert QApplication.focusWidget() is v.preview.views.buttons[0]  # then the views, not the hidden tab bar
    v.exec_view.setFocus()
    QTest.keyClick(v.exec_view, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
    assert QApplication.focusWidget() is v.add_filter_btn


def test_the_viewer_tab_bar_has_no_platform_band(window: Any) -> None:
    """The Viewer's tab bar sits on the page like the window's own tabs: no grey band (the tab bar's base) behind it."""
    assert window.viewer.doc_tabs.tabBar().drawBase() is False
    assert window.tabs.tabBar().drawBase() is False
