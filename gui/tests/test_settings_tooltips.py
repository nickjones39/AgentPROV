"""Settings tooltips: every control in the Settings dialog says what it does when the pointer rests on it, and only
while the setting is in use. A greyed-out setting (a pane still loading, the job queue on Windows, a local model's
fields before a model id is chosen) or one the current choice makes moot (the preset name unless "named preset" is
chosen, the seed unless the sampling mode is random) shows no tooltip; Qt alone would show one on a disabled widget."""

from __future__ import annotations

from pathlib import Path
from typing import Any

SENTINEL = "sentinel"


def _settle(qapp: Any) -> None:
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(60_000)
    qapp.processEvents()


def _hover(qapp: Any, top: Any, widget: Any) -> str:
    """The tooltip text after a tooltip event on ``widget``'s centre; :data:`SENTINEL` when none was shown."""
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtWidgets import QApplication, QToolTip

    QToolTip.showText(QPoint(5, 5), SENTINEL, top)
    qapp.processEvents()
    centre = widget.rect().center()
    QApplication.sendEvent(widget, QHelpEvent(QEvent.Type.ToolTip, centre, widget.mapToGlobal(centre)))
    qapp.processEvents()
    return str(QToolTip.text())


def test_every_settings_control_has_a_tooltip(qapp: Any, tmp_path: Path, fake_checkout: Path) -> None:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QLineEdit,
        QPlainTextEdit,
        QPushButton,
        QSpinBox,
        QTableWidget,
        QWidget,
    )

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.dialogs import SettingsDialog

    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    settings.checkout = fake_checkout
    dlg = SettingsDialog(settings)
    _settle(qapp)
    kinds = (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QPlainTextEdit, QPushButton, QTableWidget)
    controls = [w for w in dlg.stack.findChildren(QWidget) if isinstance(w, kinds)
                and not isinstance(w.parent(), (QSpinBox, QDoubleSpinBox, QComboBox))]  # (their own line edits)
    assert len(controls) >= 60  # the walk sees every pane (a vacuous pass would see none)
    bare = [w.accessibleName() or type(w).__name__ for w in controls if not w.toolTip()]
    assert not bare, "settings controls without a tooltip: " + ", ".join(bare)
    dlg.deleteLater()


def test_tooltip_only_while_the_setting_is_in_use(qapp: Any) -> None:
    from PySide6.QtWidgets import QSpinBox, QWidget

    from agentprov_gui.ui.safe import SafeForm

    top = QWidget()
    form = SafeForm(top)
    spin = QSpinBox(top)
    label = form.add("Thing", spin, "what <b>the</b> thing does")
    applies = {"yes": True}
    other = QSpinBox(top)
    other_label = form.add("Other", other, "the other one", active=lambda: applies["yes"])
    top.resize(400, 200)
    top.show()
    qapp.processEvents()
    tip = _hover(qapp, top, spin)
    assert "what" in tip and "<b>" not in tip and "&lt;b&gt;" in tip  # shown, and as plain text (S1)
    assert "&nbsp;" not in tip and "\xa0" not in tip  # ordinary spaces, so a long tip wraps
    assert _hover(qapp, top, spin.lineEdit()) == tip  # the spin box's own line edit hands it on
    assert _hover(qapp, top, label) == tip  # the row's label shows it too
    spin.setEnabled(False)
    assert _hover(qapp, top, spin) == SENTINEL
    assert _hover(qapp, top, label) == SENTINEL  # the label follows its field
    top.setEnabled(False)  # a pane still loading
    assert _hover(qapp, top, other) == SENTINEL
    top.setEnabled(True)
    assert "other" in _hover(qapp, top, other)
    applies["yes"] = False
    assert _hover(qapp, top, other) == SENTINEL
    assert _hover(qapp, top, other_label) == SENTINEL
    top.close()
    top.deleteLater()


def test_moot_settings_show_no_tooltip(qapp: Any, tmp_path: Path, fake_checkout: Path) -> None:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.dialogs import SettingsDialog
    from agentprov_gui.ui.safe import _SettingTipGate

    def in_use(widget: Any) -> bool:
        from PySide6.QtCore import Qt

        # the widget's own gate (a segmented control's segments have theirs: D-1060)
        (gate,) = widget.findChildren(_SettingTipGate, options=Qt.FindChildOption.FindDirectChildrenOnly)
        return bool(gate.in_use())

    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    settings.checkout = fake_checkout
    dlg = SettingsDialog(settings)
    _settle(qapp)
    _jobs, compute, _ci, dev = dlg.panes[:4]
    assert compute.body.isEnabled() and dev.body.isEnabled()
    assert in_use(compute.preset) and not in_use(compute.preset_name)
    assert compute.preset_name_row.isHidden()  # a row the choice makes moot is hidden too (D-1060 rule 3)
    compute.preset.setCurrentText("Named preset")
    assert in_use(compute.preset_name) and not compute.preset_name_row.isHidden()
    assert not in_use(dev.seed) and dev.seed_row.isHidden()
    dev.mode.setCurrentText("random")
    assert in_use(dev.seed) and not dev.seed_row.isHidden()
    compute.queue.setEnabled(False)  # as on Windows (no job queue)
    assert not in_use(compute.queue)
    dlg.deleteLater()
