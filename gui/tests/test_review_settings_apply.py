"""GUI review GR-32: Settings › General's checkout and the stored settings apply to new jobs once OK is pressed.
Before, the job manager kept the CLI it was built with at start, so new jobs ran the old checkout's ``agentprov``
while About reported the new checkout. (The queue budgets are the core's since D-704: ``agentprov jobs start`` reads
``compute.*_budget``; tests/jobs.)"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def _checkout(root: Path) -> Path:
    bindir = root / ".venv" / "bin"
    bindir.mkdir(parents=True)
    for name in ("agentprov", "python"):
        (bindir / name).write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (bindir / name).chmod(0o755)
    return root


def test_settings_ok_applies_checkout(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtCore import QSettings, QThreadPool

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui import mainwindow
    from agentprov_gui.ui.dialogs import SettingsDialog

    old = tmp_path / "old-checkout"  # no CLI: viewer only at start
    old.mkdir()
    new = _checkout(tmp_path / "new-checkout")
    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    settings.checkout = old
    win = mainwindow.MainWindow(settings, cache_dir=tmp_path / "c", home=tmp_path / "home")
    assert not win.runs.new_btn.isEnabled()
    win.runs._options[("info",)] = frozenset({"--stale"})
    win.runs.stored["compute."] = {"compute.queue_cpu": 7}

    class Driven(SettingsDialog):
        def exec(self) -> int:
            self.checkout.setText(str(new))
            self._accept()
            return self.result()

    monkeypatch.setattr(mainwindow, "SettingsDialog", Driven)
    win._settings()
    assert win.manager.cli.program[0].startswith(str(new))  # D-704: jobs start through the new checkout's CLI
    assert win.package.checkout == new and win.licences.checkout == new
    assert win.runs._options == {} and win.runs.stored == {}  # D-700: the settings are read again
    assert win.runs.new_btn.isEnabled()
    QThreadPool.globalInstance().waitForDone(30_000)  # the new checkout's version check
    qapp.processEvents()
    win.close()
