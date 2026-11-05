"""Settings › Appearance › Show tooltips: on by default, stored across restarts, applied when OK is pressed. Off, the
application's tooltip filter swallows every tooltip event (widgets, list items, column headers, tabs) and the graph's
popover stays hidden."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture
def tip_filter(qapp: Any) -> Iterator[Any]:
    from PySide6.QtWidgets import QToolTip

    from agentprov_gui.ui import safe

    f = safe.TooltipFilter(qapp)
    qapp.installEventFilter(f)
    yield f
    qapp.removeEventFilter(f)
    safe.set_tooltips_shown(True)
    QToolTip.hideText()
    f.deleteLater()


def _shows_tip(qapp: Any, target: Any, local: Any) -> bool:
    """Whether a tooltip event at ``local`` in ``target`` replaces a sentinel tip (hideText only starts a timer)."""
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtWidgets import QApplication, QToolTip

    QToolTip.showText(QPoint(5, 5), "sentinel", target)
    qapp.processEvents()
    event = QHelpEvent(QEvent.Type.ToolTip, local, target.mapToGlobal(local))
    QApplication.sendEvent(target, event)
    qapp.processEvents()
    return "sentinel" not in QToolTip.text()


def test_show_tooltips_is_on_by_default_and_persists(tmp_path: Path) -> None:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings

    ini = str(tmp_path / "s.ini")
    s = Settings(QSettings(ini, QSettings.Format.IniFormat))
    assert s.show_tooltips is True
    s.show_tooltips = False
    s.store.sync()
    assert Settings(QSettings(ini, QSettings.Format.IniFormat)).show_tooltips is False  # a restart reads it back
    s.show_tooltips = True
    assert s.show_tooltips is True


def test_off_swallows_every_tooltip(qapp: Any, tip_filter: Any) -> None:
    from PySide6.QtWidgets import QListWidget, QPushButton, QTabWidget, QWidget

    from agentprov_gui.ui.safe import (
        set_control_tooltip,
        set_list_item_tooltip,
        set_tab_tooltip,
        set_tooltips_shown,
    )

    button = QPushButton("Seal…")
    set_control_tooltip(button, "Seals the corpus")
    steps = QListWidget()
    steps.addItems(["1 Corpus"])
    set_list_item_tooltip(steps.item(0), "What step 1 does")
    tabs = QTabWidget()
    tabs.addTab(QWidget(), "Corpora")
    set_tab_tooltip(tabs, 0, "The corpora list")
    for w in (button, steps, tabs):
        w.show()
    qapp.processEvents()
    item_spot = steps.visualItemRect(steps.item(0)).center()
    tab_spot = tabs.tabBar().tabRect(0).center()
    cases = ((button, button.rect().center()), (steps.viewport(), item_spot), (tabs.tabBar(), tab_spot))
    assert all(_shows_tip(qapp, target, spot) for target, spot in cases)  # on: each shows its tooltip
    set_tooltips_shown(False)
    assert not any(_shows_tip(qapp, target, spot) for target, spot in cases)
    set_tooltips_shown(True)
    assert _shows_tip(qapp, button, button.rect().center())
    for w in (button, steps, tabs):
        w.hide()


def test_off_hides_the_graph_popover(qapp: Any, tip_filter: Any) -> None:
    from PySide6.QtCore import QPoint

    from agentprov_gui.ui.graphview import GraphTab
    from agentprov_gui.ui.safe import set_tooltips_shown

    shown: list[str] = []
    tab = SimpleNamespace(isVisible=lambda: True, _rows_for=lambda key: [("id", key)],
                          popover=SimpleNamespace(show_rows=lambda rows, at: shown.append(rows[0][1])))
    GraphTab._hover(tab, "e1", QPoint(10, 10))  # type: ignore[arg-type]
    set_tooltips_shown(False)
    GraphTab._hover(tab, "e2", QPoint(10, 10))  # type: ignore[arg-type]
    assert shown == ["e1"]


def test_settings_ok_applies_show_tooltips(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                           tip_filter: Any) -> None:
    from PySide6.QtCore import QSettings, QThreadPool
    from PySide6.QtWidgets import QCheckBox

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui import mainwindow
    from agentprov_gui.ui.dialogs import SettingsDialog
    from agentprov_gui.ui.safe import tooltips_shown

    ini = str(tmp_path / "s.ini")
    settings = Settings(QSettings(ini, QSettings.Format.IniFormat))
    settings.checkout = tmp_path / "no-checkout"
    win = mainwindow.MainWindow(settings, cache_dir=tmp_path / "c", home=tmp_path / "home")
    seen: list[Any] = []

    class Driven(SettingsDialog):
        def exec(self) -> int:
            box = self.show_tips
            assert isinstance(box, QCheckBox) and box.isChecked() and box.toolTip()  # on by default, explained
            seen.append(box)
            box.setChecked(False)
            self._accept()
            return self.result()

    monkeypatch.setattr(mainwindow, "SettingsDialog", Driven)
    win._settings()
    assert seen and not tooltips_shown()  # applied on OK
    assert Settings(QSettings(ini, QSettings.Format.IniFormat)).show_tooltips is False  # and stored
    QThreadPool.globalInstance().waitForDone(30_000)
    qapp.processEvents()
    win.close()
