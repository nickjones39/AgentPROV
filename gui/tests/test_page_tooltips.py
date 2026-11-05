"""Tooltips on every page: each control of the main window (Viewer with an execution tab open, Runs, Logs, System,
Licences, Package, Help) says what it does when the pointer rests on it, every column header says what the column
holds, and a control's tooltip shows only while it is enabled, as in Settings (test_settings_tooltips)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from test_settings_tooltips import SENTINEL, _hover
from test_viewer import _open, window  # noqa: F401 (the fixture)


def _controls(top: Any) -> list[Any]:
    from PySide6.QtWidgets import (
        QAbstractButton,
        QAbstractItemView,
        QAbstractSpinBox,
        QComboBox,
        QLineEdit,
        QScrollBar,
        QTabBar,
        QWidget,
    )

    kinds = (QAbstractButton, QComboBox, QLineEdit, QAbstractSpinBox)
    internal = (QAbstractItemView, QComboBox, QAbstractSpinBox, QLineEdit, QTabBar, QScrollBar)
    return [w for w in top.findChildren(QWidget) if isinstance(w, kinds)
            and not isinstance(w.parent(), internal)  # Qt's own parts: line edits of spin boxes, clear and close buttons
            and not w.objectName().startswith("qt_")]  # the tool bar's and menu bar's own overflow buttons


def test_every_page_control_has_a_tooltip(qapp: Any, window: Any, mini_corpus: Path) -> None:  # noqa: F811
    v = _open(qapp, window, mini_corpus)
    v.open_current_in_tab()  # the full execution pane (Show in Corpora, two graph rows)
    controls = _controls(window)
    assert len(controls) >= 60  # the walk sees every page (a vacuous pass would see none)
    bare = sorted({f"{type(w).__name__} {w.accessibleName() or getattr(w, 'text', lambda: '')()}"
                   for w in controls if not w.toolTip()})
    assert not bare, "controls without a tooltip: " + "; ".join(bare)


def test_every_column_header_has_a_tooltip(qapp: Any, window: Any, mini_corpus: Path) -> None:  # noqa: F811
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTableView, QTreeView

    v = _open(qapp, window, mini_corpus)
    v.open_current_in_tab()
    bare = []
    for view in window.findChildren(QTableView) + window.findChildren(QTreeView):
        if view.model() is None:
            continue
        header = view.horizontalHeader() if isinstance(view, QTableView) else view.header()
        if header.isHidden():
            continue
        model = view.model()
        for column in range(model.columnCount()):
            if not model.headerData(column, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole):
                bare.append(f"{view.accessibleName()}: {model.headerData(column, Qt.Orientation.Horizontal)}")
    assert not bare, "column headers without a tooltip: " + "; ".join(bare)


def test_page_tooltip_only_while_enabled(qapp: Any, window: Any, mini_corpus: Path) -> None:  # noqa: F811
    v = window.viewer
    v.preview.clear()  # no execution selected: Open in New Tab and Export Graph are disabled
    window.show()
    qapp.processEvents()
    assert not v.preview.open_btn.isEnabled()
    assert _hover(qapp, window, v.preview.open_btn) == SENTINEL
    v = _open(qapp, window, mini_corpus)
    assert v.preview.open_btn.isEnabled()
    assert "tab of its own" in _hover(qapp, window, v.preview.open_btn)
    assert "contains this text" in _hover(qapp, window, v.corpora_filter)
