"""Package page tooltips: every input (field, button, the step list) says what it does, and each of the nine steps in
the side list says what it shows or runs and what it needs."""

from __future__ import annotations

from typing import Any


def _page() -> Any:
    from agentprov_gui.ui.package import PackagePage

    return PackagePage(lambda spec: None, None)


def test_every_package_input_has_a_tooltip(qapp: Any) -> None:
    from PySide6.QtWidgets import (
        QAbstractButton,
        QAbstractSpinBox,
        QComboBox,
        QLineEdit,
        QListWidget,
        QWidget,
    )

    page = _page()
    kinds = (QLineEdit, QAbstractButton, QComboBox, QAbstractSpinBox, QListWidget)
    inputs = [w for w in page.findChildren(QWidget) if isinstance(w, kinds)
              and not isinstance(w.parent(), (QComboBox, QAbstractSpinBox))]  # (their own line edits)
    assert len(inputs) >= 16  # seven fields, six buttons on the steps, Back, Continue, the step list
    bare = [f"{type(w).__name__} {w.accessibleName()}" for w in inputs if not w.toolTip()]
    assert not bare, "Package inputs without a tooltip: " + "; ".join(bare)
    page.timer.stop()


def test_every_step_has_its_own_tooltip(qapp: Any) -> None:
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtWidgets import QApplication, QToolTip

    from agentprov_gui.ui.package import STEPS

    page = _page()
    tips = [page.steps.item(row).toolTip() for row in range(page.steps.count())]
    assert page.steps.count() == len(STEPS) == 9
    assert all(tips) and len(set(tips)) == len(tips)
    assert "dry-run" in tips[0] and "--deposit" in tips[7] and "release_scan.py" in tips[6]
    assert all(t.startswith("<p") and "\N{NO-BREAK SPACE}" not in t for t in tips)  # plain text, wrapping (S1)
    page.show()
    qapp.processEvents()
    QToolTip.showText(QPoint(5, 5), "sentinel", page)
    spot = page.steps.visualItemRect(page.steps.item(4)).center()
    viewport = page.steps.viewport()
    QApplication.sendEvent(viewport, QHelpEvent(QEvent.Type.ToolTip, spot, viewport.mapToGlobal(spot)))
    qapp.processEvents()
    assert "Seals the working corpus" in QToolTip.text()
    QToolTip.hideText()
    page.timer.stop()
    page.hide()
