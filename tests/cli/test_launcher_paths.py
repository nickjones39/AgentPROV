"""D-1130 review: the Terminal launcher never names an app path that will not last (macOS App Translocation, a
read-only disk image), and on Windows the app's own folder is refused as the app's, not described as a pip install.
A temporary ``HOME`` and ``PATH`` throughout; the platform is the launcher's seam (``_env``)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from agentprov.cli import launcher as L
from agentprov.cli.main import main


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("USERPROFILE", str(h))
    monkeypatch.setenv("PATH", str(tmp_path / "nobin"))
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "aphome"))
    monkeypatch.setattr(L, "SYSTEM_DIR", str(tmp_path / "usr-local-bin"))
    return h


def _platform(monkeypatch: pytest.MonkeyPatch, platform: str) -> None:
    monkeypatch.setattr(L, "_env", lambda ctx: L._Env(platform, ctx.env, Path.home()))


def _app(folder: Path, platform: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    app = folder / L.app_name(platform)
    app.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    app.chmod(0o755)
    return app


def _install(capsys: Any, *argv: str) -> tuple[int, Any, str]:
    code = main(["launcher", "install", *argv, "--format", "json", "--progress", "off", "-q"])
    out = capsys.readouterr()
    return code, (json.loads(out.out) if out.out.strip() else None), out.err


def test_transient_locations_are_named_on_macos_only() -> None:
    translocated = Path("/private/var/folders/x/T/AppTranslocation/1A2B/d/AgentPROV.app/Contents/MacOS/AgentPROV")
    assert "App Translocation" in (L.transient_location(translocated, "darwin") or "")
    dmg = Path("/Volumes/AgentPROV 0.2.1/AgentPROV.app/Contents/MacOS/AgentPROV")
    assert "disk image" in (L.transient_location(dmg, "darwin", read_only=lambda p: True) or "")
    assert L.transient_location(dmg, "darwin", read_only=lambda p: False) is None  # a writable external disk
    assert L.transient_location(Path("/Applications/AgentPROV.app/Contents/MacOS/AgentPROV"), "darwin") is None
    assert L.transient_location(translocated, "linux") is None


def test_an_app_run_from_app_translocation_gets_no_launcher(home: Path, tmp_path: Path, capsys: Any,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    _platform(monkeypatch, "darwin")
    app = _app(tmp_path / "AppTranslocation" / "1A2B" / "d" / "AgentPROV.app" / "Contents" / "MacOS", "darwin")
    code, _doc, err = _install(capsys, "--app", str(app))
    assert code == 4 and "not in a lasting place" in err and "Move AgentPROV.app to Applications" in err
    assert not (home / ".local" / "bin" / "agentprov").exists()
    lasting = _app(tmp_path / "Applications" / "AgentPROV.app" / "Contents" / "MacOS", "darwin")
    code, doc, err = _install(capsys, "--app", str(lasting))
    assert code == 0 and doc["changed"] == "installed", err


def test_status_and_remove_work_for_an_app_in_a_transient_place(home: Path, tmp_path: Path, capsys: Any,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """Only install refuses an app that is not in a lasting place: the app's Uninstall Command Line Tool asks status
    first, and an app opened from its disk image (or translocated) must still find and remove a launcher an earlier
    copy in Applications made."""
    _platform(monkeypatch, "darwin")
    lasting = _app(tmp_path / "Applications" / "AgentPROV.app" / "Contents" / "MacOS", "darwin")
    code, _doc, err = _install(capsys, "--app", str(lasting))
    assert code == 0, err
    moved = _app(tmp_path / "AppTranslocation" / "1A2B" / "d" / "AgentPROV.app" / "Contents" / "MacOS", "darwin")
    code = main(["launcher", "status", "--app", str(moved), "--format", "json", "--progress", "off", "-q"])
    out = capsys.readouterr()
    assert code == 0, out.err
    entries = [e for e in json.loads(out.out)["entries"] if e["launcher"]]
    assert len(entries) == 1 and entries[0]["app"] == str(lasting) and not entries[0]["current"]
    code = main(["launcher", "remove", "--format", "json", "--progress", "off", "-q"])
    out = capsys.readouterr()
    assert code == 0 and json.loads(out.out)["changed"] == "removed", out.err


def test_on_windows_the_apps_own_folder_is_refused_as_the_apps(home: Path, tmp_path: Path, capsys: Any,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """NTFS matches agentprov.exe to AgentPROV.exe: that is the app itself, never "a program pip put there"."""
    _platform(monkeypatch, "win32")
    folder = tmp_path / "AgentPROV"
    app = _app(folder, "win32")
    if not os.path.lexists(folder / "agentprov.exe"):  # a case-sensitive file system: the same file by a link
        os.link(app, folder / "agentprov.exe")
    code, _doc, err = _install(capsys, "--app", str(app), "--dir", str(folder))
    assert code == 4 and "this is the app's own folder" in err and "pip" not in err
    assert not (folder / "agentprov.cmd").exists()
