"""G5 cross-platform note (docs/reports/gui/g5-cross-platform.md), the GUI's portability fixes, tested on any host:

* P-1: without a keychain, Settings › Keys shows the CLI's reason (per OS) and the fallback;
* P-4: Run Live offers ``sandbox-exec`` only on macOS and says plainly that ``dedicated-user`` and ``vm`` are declared,
  not enforced (also in the R2 confirmation);
* P-5: the Windows long-path warning appears only when long paths are known to be off;
* P-6: the native-toolbar setting is hidden off macOS.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentprov_gui.live import runspec


def _settle(qapp: Any) -> None:
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(60_000)
    qapp.processEvents()


@pytest.mark.parametrize(("platform", "expected"), [
    ("darwin", ("sandbox-exec", "dedicated-user", "vm")),
    ("linux", ("dedicated-user", "vm")),
    ("win32", ("dedicated-user", "vm")),
])
def test_containment_choices_per_os(platform: str, expected: tuple[str, ...]) -> None:
    assert runspec.containment_choices(platform) == expected


def test_declared_containment_reads_as_declared_never_enforced() -> None:
    for value in ("dedicated-user", "vm"):
        line = runspec.containment_line(value)
        assert "declared" in line and "not enforced" in line
    assert "probed" in runspec.containment_line("sandbox-exec")
    assert "does not enforce or check" in runspec.DECLARED_CONTAINMENT


def test_run_live_off_macos_never_offers_sandbox_exec(qapp: Any, tmp_path: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.jobs.manager import CliLocator, JobManager
    from agentprov_gui.ui import runlive
    from agentprov_gui.ui.safe import SafeLabel

    monkeypatch.setattr(runlive, "containment_choices", lambda: runspec.containment_choices("linux"))
    dlg = runlive.RunLiveDialog(JobManager(tmp_path / "home", CliLocator(None, ())), home=tmp_path / "home",
                                checkout=None, run=lambda *a, **k: (127, b"", b""))
    _settle(qapp)
    items = [dlg.containment.itemText(i) for i in range(dlg.containment.count())]
    assert items == ["", "dedicated-user", "vm"]
    notes = [w.text() for w in dlg.findChildren(SafeLabel) if w.accessibleName() == "Containment note"]
    assert notes == [runspec.DECLARED_CONTAINMENT]
    dlg.deleteLater()


def test_keys_pane_shows_why_there_is_no_keychain(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.live import keychain
    from agentprov_gui.ui.livepanes import NO_KEYCHAIN, KeysPane

    reason = "no Secret Service is answering on this session's D-Bus; keys then come from .env"
    monkeypatch.setattr(keychain, "status", lambda cli: keychain.KeychainStatus(False, None, reason))
    pane = KeysPane(None, None)
    pane.refresh()
    text = pane.status.text()
    assert text.startswith(NO_KEYCHAIN) and "Secret Service" in text and not pane.store_btn.isEnabled()
    pane.deleteLater()


@pytest.mark.parametrize(("value", "warned"), [(False, True), (True, False), (None, False)])
def test_long_path_warning_only_when_known_off(value: bool | None, warned: bool) -> None:
    from agentprov_gui.platform.windows import LONG_PATHS_WARNING, long_path_warning, long_paths_enabled

    assert (long_path_warning(lambda: value) == LONG_PATHS_WARNING) is warned
    if not __import__("sys").platform.startswith("win"):
        assert long_paths_enabled() is None  # never guessed off Windows


def test_native_toolbar_setting_is_hidden_off_macos(qapp: Any, tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui import dialogs

    for platform, shown in (("linux", False), ("darwin", True)):
        monkeypatch.setattr(dialogs.sys, "platform", platform)
        dlg = dialogs.SettingsDialog(Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)))
        assert dlg.native.isHidden() is not shown
        dlg.deleteLater()
    _settle(qapp)
