"""Tooltip placement: the application's tooltip filter (``safe.TooltipFilter``, installed by ``app.py``) puts every
tooltip a small fixed offset right of and below the pointer's hot spot, scaled by the pointer size, instead of Qt's
offset of a whole cursor image (on macOS 80 px below the hot spot at pointer size 2 for a wrapped tip). Widgets, item
view cells and column headers get the same place, and so does the graph's popover; the screen edges still apply."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest


@pytest.fixture
def tip_filter(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """The filter on the application for one test, at the standard pointer size (the host's own setting aside)."""
    from PySide6.QtWidgets import QToolTip

    from agentprov_gui.ui import safe

    monkeypatch.setattr(safe, "pointer_scale", lambda: 1.0)
    f = safe.TooltipFilter(qapp)
    qapp.installEventFilter(f)
    yield f
    qapp.removeEventFilter(f)
    QToolTip.hideText()
    f.deleteLater()


def _label(qapp: Any) -> Any:
    shown = [w for w in qapp.topLevelWidgets() if w.objectName() == "qtooltip_label" and w.isVisible()]
    assert shown, "no tooltip is showing"
    return shown[0]


def _hover(qapp: Any, target: Any, local: Any) -> Any:
    """A tooltip event at ``local`` in ``target``; returns the hot spot (global)."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtWidgets import QApplication, QToolTip

    QToolTip.hideText()
    qapp.processEvents()
    spot = target.mapToGlobal(local)
    QApplication.sendEvent(target, QHelpEvent(QEvent.Type.ToolTip, local, spot))
    qapp.processEvents()
    return spot


def _expected(qapp: Any, spot: Any) -> Any:
    from agentprov_gui.ui.safe import screen_rect, tip_position

    label = _label(qapp)
    return tip_position(spot, label.size(), screen_rect(spot, label))


def test_offset_is_small_fixed_and_scales_with_the_pointer() -> None:
    from PySide6.QtCore import QPoint, QRect, QSize

    from agentprov_gui.ui.safe import TIP_OFFSET, tip_position

    screen, size = QRect(0, 0, 1000, 800), QSize(200, 60)
    assert tip_position(QPoint(100, 100), size, screen) == QPoint(100, 100) + TIP_OFFSET == QPoint(104, 120)
    assert tip_position(QPoint(100, 100), size, screen, 2.0) == QPoint(108, 140)  # clear of a pointer twice the size
    # Qt's own clamping: left of the hot spot at the right edge, above it at the bottom, never off the screen
    assert tip_position(QPoint(950, 100), size, screen) == QPoint(950 - 4 - 200, 120)
    assert tip_position(QPoint(100, 780), size, screen) == QPoint(104, 780 - 4 - 60)
    assert tip_position(QPoint(10, 10), QSize(1200, 900), screen) == QPoint(0, 0)


def test_widget_tooltip_is_placed_at_the_offset(qapp: Any, tip_filter: Any) -> None:
    from PySide6.QtWidgets import QPushButton

    from agentprov_gui.ui.safe import TIP_OFFSET, set_control_tooltip

    button = QPushButton("Seal…")
    button.resize(200, 40)
    button.show()
    for text in ("Short.", "A long explanation that wraps over several lines of the tooltip. " * 5):
        set_control_tooltip(button, text)
        spot = _hover(qapp, button, button.rect().center())
        label = _label(qapp)
        assert label.pos() == _expected(qapp, spot)
        if label.width() < 300:  # well inside the offscreen screen: no clamping applies
            assert label.pos() == spot + TIP_OFFSET
    button.hide()


def test_item_and_header_tooltips_get_the_same_place(qapp: Any, tip_filter: Any) -> None:
    from PySide6.QtWidgets import QListWidget, QTableWidget, QTableWidgetItem

    from agentprov_gui.ui.safe import set_header_tooltips, set_list_item_tooltip

    steps = QListWidget()
    steps.addItems(["1 Corpus", "2 Withholding"])
    set_list_item_tooltip(steps.item(1), "What step 2 shows")
    steps.resize(300, 200)
    steps.show()
    qapp.processEvents()
    viewport = steps.viewport()
    spot = _hover(qapp, viewport, steps.visualItemRect(steps.item(1)).center())
    assert "shows" in _label(qapp).text()
    assert _label(qapp).pos() == _expected(qapp, spot)

    table = QTableWidget(1, 2)
    table.setHorizontalHeaderItem(0, QTableWidgetItem("id"))
    table.setHorizontalHeaderItem(1, QTableWidgetItem("state"))
    set_header_tooltips(table, ["The id", "The state"])
    table.resize(400, 200)
    table.show()
    qapp.processEvents()
    header = table.horizontalHeader()
    local = header.viewport().rect().topLeft()
    local.setX(header.sectionViewportPosition(1) + 5)
    local.setY(header.height() // 2)
    spot = _hover(qapp, header.viewport(), local)
    assert "state" in _label(qapp).text()
    assert _label(qapp).pos() == _expected(qapp, spot)
    steps.hide()
    table.hide()


def test_a_gated_setting_shows_no_tooltip_to_place(qapp: Any, tip_filter: Any) -> None:
    """The setting gates still decide first: a disabled control's tooltip is swallowed before any placement."""
    from PySide6.QtWidgets import QPushButton, QToolTip

    from agentprov_gui.ui.safe import set_control_tooltip

    button = QPushButton("Verify")
    set_control_tooltip(button, "Runs verify")
    button.setEnabled(False)
    button.show()
    _hover(qapp, button, button.rect().center())
    assert not QToolTip.isVisible()
    button.hide()


def test_graph_popover_uses_the_tooltip_offset(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QWidget

    from agentprov_gui.ui import graphview
    from agentprov_gui.ui.safe import screen_rect, tip_position

    monkeypatch.setattr(graphview, "pointer_scale", lambda: 1.0)
    owner = QWidget()
    popover = graphview.Popover(owner)
    at = QPoint(40, 30)
    popover.show_rows([("id", "e1"), ("section", "entity")], at)
    assert popover.pos() == tip_position(at, popover.size(), screen_rect(at, popover))
    assert popover.pos() == QPoint(44, 50)  # the offscreen screen holds it without clamping
    popover.hide()
