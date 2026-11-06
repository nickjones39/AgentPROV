"""Install Command Line Tool… and Uninstall Command Line Tool (D-1130, :mod:`agentprov_gui.ui.clitool`).

Every test runs with a temporary ``HOME`` and ``PATH``: the flows drive the real core ``agentprov launcher`` (as a
subprocess of this interpreter, with ``--app`` naming a fake app executable in place of the bundle) and nothing is
written outside the test's folders. The launcher is never taken for a separately installed ``agentprov``
(:func:`~agentprov_gui.jobs.manager.installed_program`), so Settings › General's precedence (checkout, an installed
agentprov, the bundle's own) is unchanged and the app never runs itself through it."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX launcher; the .cmd form is tested in the core")


@pytest.fixture
def box(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    home, bindir, appdir = tmp_path / "home", tmp_path / "pathbin", tmp_path / "Apps" / "AgentPROV.app" / "MacOS"
    shared = tmp_path / "usr-local-bin"
    for d in (home, bindir, appdir, shared):
        d.mkdir(parents=True)
    app = appdir / "AgentPROV"
    app.write_text('#!/bin/sh\necho "app $*"\n', encoding="utf-8")
    app.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(bindir))
    return {"home": home, "bin": bindir, "app": app, "local": home / ".local" / "bin", "shared": shared}


def _runner(box: dict[str, Path], seen: list[list[str]] | None = None) -> Any:
    """The core CLI, as the bundle's ``--cli`` would run it, with ``--app`` naming the fake app."""

    def run(argv: Sequence[str]) -> tuple[int, bytes, bytes]:
        args = list(argv)
        if args[:2] in (["launcher", "install"], ["launcher", "status"]):
            args += ["--app", str(box["app"])]
        if seen is not None:
            seen.append(args)
        env = {**os.environ, "HOME": str(box["home"]), "PATH": str(box["bin"])}
        # the shared folder (/usr/local/bin) is a temporary one too: nothing outside the test's folders is looked at
        code = ("import sys; import agentprov.cli.launcher as L; L.SYSTEM_DIR = sys.argv.pop(1); "
                "from agentprov.cli.main import main; raise SystemExit(main(sys.argv[1:]))")
        done = subprocess.run([sys.executable, "-I", "-c", code, str(box["shared"]), *args, "--progress", "off"],
                              capture_output=True, env=env, check=False, timeout=120, stdin=subprocess.DEVNULL)
        return done.returncode, done.stdout, done.stderr

    return run


@pytest.fixture
def boxes(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """The message boxes shown (title, text + informative), answered at once."""
    from PySide6.QtWidgets import QMessageBox

    shown: list[tuple[str, str]] = []

    def exec_(self: QMessageBox) -> int:
        shown.append((self.windowTitle(), self.text() + "\n" + self.informativeText()))
        return int(QMessageBox.StandardButton.Ok)

    monkeypatch.setattr(QMessageBox, "exec", exec_)
    return shown


def test_the_marker_matches_the_core() -> None:
    from agentprov.cli import launcher

    from agentprov_gui.jobs import manager

    assert manager.LAUNCHER_MARKER == launcher.MARKER


def test_install_then_uninstall_through_the_menu_flows(qapp: Any, box: dict[str, Path],
                                                       boxes: list[tuple[str, str]]) -> None:
    from agentprov_gui.ui import clitool

    seen: list[list[str]] = []
    dialogs: list[clitool.ConfirmInstall] = []

    def accept(dlg: clitool.ConfirmInstall) -> bool:
        dialogs.append(dlg)
        return True

    doc = clitool.install(None, run=_runner(box, seen), confirm=accept)
    assert doc is not None and doc["changed"] == "installed"
    launcher = box["local"] / "agentprov"
    assert doc["launcher"] == str(launcher) and launcher.is_file()
    # the confirmation named the launcher and what it runs, and the default folder needs no rights
    shown = dialogs[0].details.text()
    assert f"Launcher: {launcher}" in shown and f'It runs: "{box["app"]}" --cli ARGS' in shown
    assert dialogs[0].ok.isEnabled() and dialogs[0].chosen_dir() == str(box["local"])
    assert seen[1][:4] == ["launcher", "install", "--dir", str(box["local"])]
    # the reply says how to put the folder on PATH (it is not there)
    assert "is installed" in boxes[-1][1] and "export PATH=" in boxes[-1][1] and "is not found, add" in boxes[-1][1]
    out = subprocess.run([str(launcher), "info", "x y"], capture_output=True, text=True, check=True).stdout
    assert out == "app --cli info x y\n"

    removed = clitool.uninstall(None, run=_runner(box), confirm=lambda q: str(launcher) in q)
    assert removed is not None and removed["removed"] == [str(launcher)] and not launcher.exists()
    assert "is removed" in boxes[-1][1]
    assert clitool.uninstall(None, run=_runner(box), confirm=lambda q: True) is None
    assert "No agentprov command of this app" in boxes[-1][1]


def test_another_agentprov_is_never_replaced_or_removed(qapp: Any, box: dict[str, Path],
                                                        boxes: list[tuple[str, str]]) -> None:
    from agentprov_gui.ui import clitool

    box["local"].mkdir(parents=True)
    pip = box["local"] / "agentprov"
    pip.write_text("#!/home/u/.venv/bin/python\nfrom agentprov.cli.main import main\n", encoding="utf-8")
    pip.chmod(0o755)
    before = pip.read_bytes()
    dialogs: list[clitool.ConfirmInstall] = []
    assert clitool.install(None, run=_runner(box), confirm=lambda d: dialogs.append(d) or False) is None
    assert not dialogs[0].ok.isEnabled() and "There is already an agentprov there" in dialogs[0].details.text()
    assert "virtual environment" in dialogs[0].details.text()
    # the CLI refuses too (a confirmation that went ahead anyway)
    assert clitool.install(None, run=_runner(box), confirm=lambda d: True) is None
    assert "not installed" in boxes[-1][1] and "another agentprov is already there" in boxes[-1][1]
    assert clitool.uninstall(None, run=_runner(box), confirm=lambda q: True) is None
    assert "Left as it is" in boxes[-1][1]
    assert pip.read_bytes() == before


def test_not_a_bundle_says_so_and_runs_nothing(qapp: Any, monkeypatch: pytest.MonkeyPatch,
                                               boxes: list[tuple[str, str]]) -> None:
    from agentprov_gui.ui import clitool

    monkeypatch.setattr(clitool, "bundled_program", lambda: ())
    assert not clitool.available()
    assert clitool.install(None) is None and clitool.uninstall(None) is None
    assert all("not the desktop app bundle" in text for _, text in boxes) and len(boxes) == 2


def test_the_launcher_is_not_an_installed_agentprov(box: dict[str, Path], tmp_path: Path) -> None:
    """installed_program skips it (on PATH, in ~/.local/bin, or named in Settings), so CliLocator's precedence keeps
    the bundle's own CLI as the bundle's, and a real installed agentprov behind it is still found."""
    from agentprov.cli import launcher as core

    from agentprov_gui.jobs import manager

    box["local"].mkdir(parents=True)
    ours = box["local"] / "agentprov"
    ours.write_text(core.render(str(box["app"])), encoding="utf-8")
    ours.chmod(0o755)
    (box["bin"] / "agentprov").symlink_to(ours)  # a link to it on PATH is the launcher too (realpath)
    assert manager.is_cli_launcher(ours) and not manager.is_cli_launcher(box["bin"] / "agentprov")
    env = {"PATH": f"{box['local']}{os.pathsep}{box['bin']}"}
    found = manager.installed_program(None, env)
    assert found is not None and found == box["bin"] / "agentprov"  # a link: not the marked file, so taken as given
    (box["bin"] / "agentprov").unlink()
    assert manager.installed_program(None, env) is None
    assert manager.installed_program(ours) is None  # named in Settings › General: still not an installed agentprov
    pip = tmp_path / "venv" / "agentprov"
    pip.parent.mkdir()
    pip.write_text("#!/usr/bin/python3\n", encoding="utf-8")
    pip.chmod(0o755)
    assert manager.installed_program(None, {"PATH": f"{box['local']}{os.pathsep}{pip.parent}"}) == pip
    # without a checkout and without an installed agentprov, the bundle runs its own (never the launcher)
    manager.set_installed_program(None)
    old = os.environ["PATH"]
    try:
        os.environ["PATH"] = str(box["local"])
        loc = manager.CliLocator.for_checkout(None)
    finally:
        os.environ["PATH"] = old
    assert str(ours) not in loc.program


def test_the_menu_items(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """In the macOS application menu (ApplicationSpecificRole; Help elsewhere), tooltipped, shown only in a bundle."""
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QAction

    from agentprov_gui import parity
    from agentprov_gui.settings import Settings
    from agentprov_gui.ui import clitool, mainwindow

    for bundled in (False, True):
        monkeypatch.setattr(clitool, "bundled_program", (lambda: ("/A/AgentPROV", "--cli")) if bundled else (lambda: ()))
        settings = Settings(QSettings(str(tmp_path / f"s{bundled}.ini"), QSettings.Format.IniFormat))
        win = mainwindow.MainWindow(settings, cache_dir=tmp_path / f"c{bundled}", home=tmp_path / "home")
        for key, name in (("installCli", clitool.INSTALL_NAME), ("uninstallCli", clitool.UNINSTALL_NAME)):
            act = win.action_map[key]
            assert act.text() == name and act.isVisible() is bundled
            assert act.menuRole() == QAction.MenuRole.ApplicationSpecificRole
            assert "agentprov launcher" in act.toolTip().replace("\xa0", " ") and act.isEnabled() is bundled
            assert parity.ACTIONS[name][0] == "launcher"
        win.close()
        win.deleteLater()


def test_the_confirmation_offers_the_default_folder_itself_and_shows_cli_text_as_data(qapp: Any) -> None:
    """D-1130 review: ~/.local/bin2 is not the default ~/.local/bin, and the CLI's paths and words are shown escaped."""
    status = {"format": "agentprov-launcher/0.1", "action": "status", "app": "/Apps/AgentPROV\u202e.app/AgentPROV",
              "default_dir": "/h/.local/bin", "system_dir_writable": False,
              "entries": [{"path": "/h/.local/bin2/agentprov", "exists": False, "launcher": False, "on_path": True},
                          {"path": "/h/.local/bin/agentprov", "exists": True, "launcher": False, "on_path": True,
                           "is": "installed with pip\u0007"}]}
    from agentprov_gui.ui import clitool

    dlg = clitool.ConfirmInstall(status)
    assert dlg.chosen_dir() == "/h/.local/bin" and dlg.folder.count() == 1
    text = dlg.details.text()
    assert "\u202e" not in text and "\u0007" not in text and not dlg.ok.isEnabled()
    dlg.deleteLater()
