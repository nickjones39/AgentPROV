"""The graph canvas's wheel (the Viewer's Graph tab): a mouse wheel zooms, anchored under the pointer, one zoom step a
notch, within the same limits as the − and + buttons and ⌘− ⌘+; a trackpad scroll (a scroll phase), Shift with the
wheel and a sideways scroll pan instead; ⌘/Ctrl or ⌥ with a trackpad scroll zooms."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def view(qapp: Any) -> Any:
    from PySide6.QtCore import QRectF
    from PySide6.QtWidgets import QGraphicsScene

    from agentprov_gui.ui.graphview import GraphView

    v = GraphView()
    scene = QGraphicsScene(v)
    scene.setSceneRect(QRectF(0, 0, 4000, 3000))
    scene.addRect(QRectF(0, 0, 4000, 3000))
    v.setScene(scene)
    v.resize(400, 300)
    v.show()
    qapp.processEvents()
    v.set_zoom(1.0)
    v.centerOn(2000, 1500)
    yield v
    v.close()
    v.deleteLater()
    qapp.processEvents()


def wheel(qapp: Any, view: Any, *, angle: tuple[int, int] = (0, 0), pixel: tuple[int, int] = (0, 0),
          phase: Any = None, modifiers: Any = None, at: tuple[float, float] = (100.0, 80.0)) -> Any:
    """Send ``view`` a wheel event at ``at`` (viewport coordinates); returns the event (``isAccepted``)."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    pos = QPointF(*at)
    event = QWheelEvent(pos, QPointF(view.viewport().mapToGlobal(pos.toPoint())), QPoint(*pixel), QPoint(*angle),
                        Qt.MouseButton.NoButton, modifiers or Qt.KeyboardModifier.NoModifier,
                        phase or Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(view.viewport(), event)
    qapp.processEvents()
    return event


def scroll(view: Any) -> tuple[int, int]:
    return view.horizontalScrollBar().value(), view.verticalScrollBar().value()


def test_a_wheel_notch_zooms_one_step_under_the_pointer(qapp: Any, view: Any) -> None:
    from PySide6.QtCore import QPoint

    from agentprov_gui.ui.graphview import ZOOM_STEP

    at = QPoint(100, 80)
    under = view.mapToScene(at)
    wheel(qapp, view, angle=(0, 120), at=(100.0, 80.0))
    assert view.current_scale() == pytest.approx(ZOOM_STEP)
    moved = view.mapFromScene(under) - at
    assert abs(moved.x()) <= 1 and abs(moved.y()) <= 1  # the scene point under the pointer stays under it
    wheel(qapp, view, angle=(0, -120), at=(100.0, 80.0))
    assert view.current_scale() == pytest.approx(1.0)
    moved = view.mapFromScene(under) - at
    assert abs(moved.x()) <= 2 and abs(moved.y()) <= 2


def test_a_wheel_zooms_within_the_buttons_limits(qapp: Any, view: Any) -> None:
    from agentprov_gui.ui.graphview import MAX_SCALE, MIN_SCALE, ZOOM_STEP

    for _ in range(40):
        wheel(qapp, view, angle=(0, 120))
    assert view.current_scale() == pytest.approx(MAX_SCALE)
    for _ in range(80):
        wheel(qapp, view, angle=(0, -120))
    assert view.current_scale() == pytest.approx(MIN_SCALE)
    view.set_zoom(1.0)
    for _ in range(40):
        view.zoom_by(ZOOM_STEP)  # what the + button and ⌘+ do
    assert view.current_scale() == pytest.approx(MAX_SCALE)
    view.set_zoom(100.0)
    assert view.current_scale() == pytest.approx(MAX_SCALE)


def test_a_trackpad_scroll_pans(qapp: Any, view: Any) -> None:
    from PySide6.QtCore import Qt

    before = scroll(view)
    event = wheel(qapp, view, angle=(0, -80), pixel=(0, -40), phase=Qt.ScrollPhase.ScrollUpdate)
    assert view.current_scale() == pytest.approx(1.0)
    assert scroll(view) != before and event.isAccepted()


def test_a_zoom_modifier_with_a_trackpad_scroll_zooms(qapp: Any, view: Any) -> None:
    from PySide6.QtCore import Qt

    wheel(qapp, view, angle=(0, 60), pixel=(0, 30), phase=Qt.ScrollPhase.ScrollUpdate,
          modifiers=Qt.KeyboardModifier.ControlModifier)
    assert view.current_scale() > 1.0


def test_shift_or_a_sideways_wheel_scrolls(qapp: Any, view: Any) -> None:
    from PySide6.QtCore import Qt

    before = scroll(view)
    wheel(qapp, view, angle=(0, -120), modifiers=Qt.KeyboardModifier.ShiftModifier)
    assert view.current_scale() == pytest.approx(1.0) and scroll(view) != before
    before = scroll(view)
    wheel(qapp, view, angle=(-120, 0))
    assert view.current_scale() == pytest.approx(1.0) and scroll(view)[0] != before[0]


def test_wheel_pans_rule(qapp: Any) -> None:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent

    from agentprov_gui.ui.graphview import wheel_pans

    def ev(angle: tuple[int, int], phase: Any = Qt.ScrollPhase.NoScrollPhase,
           mods: Any = Qt.KeyboardModifier.NoModifier, pixel: tuple[int, int] = (0, 0)) -> QWheelEvent:
        return QWheelEvent(QPointF(1, 1), QPointF(1, 1), QPoint(*pixel), QPoint(*angle), Qt.MouseButton.NoButton,
                           mods, phase, False)

    assert not wheel_pans(ev((0, 120)))  # a mouse wheel zooms
    assert not wheel_pans(ev((0, 120), pixel=(0, 12)))  # also with precise deltas (some mice on macOS)
    for phase in (Qt.ScrollPhase.ScrollBegin, Qt.ScrollPhase.ScrollUpdate, Qt.ScrollPhase.ScrollMomentum,
                  Qt.ScrollPhase.ScrollEnd):
        assert wheel_pans(ev((0, 30), phase, pixel=(0, 15)))  # a trackpad pans
    assert wheel_pans(ev((0, 120), mods=Qt.KeyboardModifier.ShiftModifier))
    assert wheel_pans(ev((120, 0)))
    for mod in (Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.MetaModifier,
                Qt.KeyboardModifier.AltModifier):
        assert not wheel_pans(ev((0, 30), Qt.ScrollPhase.ScrollUpdate, mod))


def test_the_zoom_buttons_use_the_wheel_step_and_say_so(qapp: Any) -> None:
    from PySide6.QtWidgets import QPushButton

    from agentprov_gui.ui.graphview import ZOOM_STEP, GraphTab

    tab = GraphTab(None, narrow=True)
    try:
        buttons = {b.accessibleName(): b for b in tab.findChildren(QPushButton)}
        tab.view.set_zoom(1.0)
        buttons["Zoom in"].click()
        assert tab.view.current_scale() == pytest.approx(ZOOM_STEP)
        buttons["Zoom out"].click()
        buttons["Zoom out"].click()
        assert tab.view.current_scale() == pytest.approx(1 / ZOOM_STEP)
        for name in ("Zoom in", "Zoom out"):
            assert "mouse wheel" in buttons[name].toolTip()
    finally:
        tab.deleteLater()
        qapp.processEvents()
