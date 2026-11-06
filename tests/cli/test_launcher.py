"""``agentprov launcher`` (D-1130): the desktop app's Terminal command.

Every test runs with a temporary ``HOME`` and ``PATH`` and with :data:`agentprov.cli.launcher.SYSTEM_DIR` moved into
its temporary folder, so nothing outside the test's folders is read or written. The app is a fake executable named
``AgentPROV`` (``--app``), standing in for the bundle's ``AgentPROV --cli``."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from agentprov.cli import launcher as L
from agentprov.cli.main import main

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="runs the POSIX launcher")


@pytest.fixture
def box(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    home, pathbin, shared = tmp_path / "home", tmp_path / "pathbin", tmp_path / "usr-local-bin"
    appdir = tmp_path / "Apps" / "Agent PROV's $app" / "MacOS"  # a space, a quote and a dollar in the path
    for d in (home, pathbin, shared, appdir):
        d.mkdir(parents=True)
    app = appdir / L.app_name()
    app.write_text('#!/bin/sh\necho "app $*"\nexit 7\n', encoding="utf-8")
    app.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("PATH", str(pathbin))
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "aphome"))
    monkeypatch.setattr(L, "SYSTEM_DIR", str(shared))
    return {"home": home, "bin": pathbin, "shared": shared, "app": app, "local": home / ".local" / "bin",
            "launcher": home / ".local" / "bin" / L.launcher_name()}


def cli(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, Any, str]:
    code = main(["launcher", *argv, "--format", "json", "--progress", "off", "-q"])
    out = capsys.readouterr()
    return code, (json.loads(out.out) if out.out.strip() else None), out.err


@posix_only
def test_install_runs_the_app_and_passes_every_argument(box: dict[str, Path], capsys: Any) -> None:
    code, doc, _ = cli(capsys, "install", "--app", str(box["app"]))
    assert code == 0 and doc["changed"] == "installed" and doc["launcher"] == str(box["launcher"])
    assert doc["runs"] == [str(box["app"]), "--cli"] and doc["on_path"] is False
    assert doc["path_hint"] and "export PATH=\"$HOME/.local/bin:$PATH\"" in doc["path_hint"][1]
    assert L.is_launcher(box["launcher"]) and L.launcher_app(box["launcher"]) == str(box["app"])
    assert os.access(box["launcher"], os.X_OK)
    done = subprocess.run([str(box["launcher"]), "info", "a b", "$HOME", "'q'"], capture_output=True, text=True,
                          check=False)
    assert done.returncode == 7 and done.stdout == "app --cli info a b $HOME 'q'\n"
    # again: unchanged; then for a new app place: updated
    code, doc, _ = cli(capsys, "install", "--app", str(box["app"]))
    assert code == 0 and doc["changed"] == "unchanged"
    moved = box["app"].parent.parent.parent / "Other" / L.app_name()
    moved.parent.mkdir()
    box["app"].rename(moved)
    done = subprocess.run([str(box["launcher"])], capture_output=True, text=True, check=False)
    assert done.returncode == 127 and "no longer at" in done.stderr and "moved or deleted" in done.stderr
    assert str(box["launcher"]) in done.stderr  # the reply names the launcher to delete
    code, doc, _ = cli(capsys, "install", "--app", str(moved))
    assert code == 0 and doc["changed"] == "updated" and L.launcher_app(box["launcher"]) == str(moved)


@posix_only
def test_on_path_and_shadowed(box: dict[str, Path], capsys: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    other = box["bin"] / "agentprov"
    other.write_text("#!/usr/bin/python3\n", encoding="utf-8")
    other.chmod(0o755)
    monkeypatch.setenv("PATH", f"{box['bin']}{os.pathsep}{box['local']}")
    code, doc, _ = cli(capsys, "install", "--app", str(box["app"]))
    assert code == 0 and doc["on_path"] is True and doc["path_hint"] == [] and doc["shadowed_by"] == str(other)


@pytest.mark.parametrize("kind", ["pip", "uv-tool", "pipx", "venv", "plain"])
def test_never_replaces_or_removes_another_agentprov(box: dict[str, Path], capsys: Any, kind: str,
                                                    tmp_path: Path) -> None:
    box["local"].mkdir(parents=True)
    target = box["launcher"]
    expected = {"pip": "installed with pip", "uv-tool": "installed with uv tool", "pipx": "installed with pipx",
                "venv": "virtual environment", "plain": "not this app's launcher"}[kind]
    if kind == "pip":
        target.write_text("#!/usr/bin/python3\nfrom agentprov.cli.main import main\n", encoding="utf-8")
    elif kind == "plain":
        target.write_text("#!/bin/sh\n# agentprov-launcher/0\n", encoding="utf-8")  # an older or forged marker
    else:
        real = tmp_path / {"uv-tool": "share/uv/tools/agentprov/bin", "pipx": "share/pipx/venvs/agentprov/bin",
                           "venv": "checkout/.venv/bin"}[kind] / "agentprov"
        real.parent.mkdir(parents=True)
        real.write_text("#!/x/python\n", encoding="utf-8")
        if sys.platform == "win32":
            pytest.skip("symbolic links")
        target.symlink_to(real)
    before = os.readlink(target) if target.is_symlink() else target.read_bytes()
    code, doc, err = cli(capsys, "install", "--app", str(box["app"]))
    assert code == 4 and doc is None and "another agentprov is already there" in err and expected in err
    code, doc, err = cli(capsys, "remove")
    assert code == 0 and doc["removed"] == [] and doc["left"][0]["path"] == str(target)
    code, doc, err = cli(capsys, "remove", "--dir", str(box["local"]))
    assert code == 4 and "only a launcher this app made is removed" in err
    assert (os.readlink(target) if target.is_symlink() else target.read_bytes()) == before


def test_remove_deletes_only_the_launchers_it_made(box: dict[str, Path], capsys: Any) -> None:
    for d in (box["local"], box["shared"]):
        assert cli(capsys, "install", "--app", str(box["app"]), "--dir", str(d))[0] == 0
    keep = box["shared"] / "agentprov-other"
    keep.write_text("x", encoding="utf-8")
    # status and remove without --dir look in the shared folder (SYSTEM_DIR) on POSIX only; on Windows, the default
    system = sys.platform != "win32"
    code, doc, _ = cli(capsys, "status", "--app", str(box["app"]))
    assert code == 0 and [e["launcher"] for e in doc["entries"]] == ([True, True] if system else [True])
    assert all(e["current"] and e["app_exists"] for e in doc["entries"]) and doc["system_dir_writable"] is system
    code, doc, _ = cli(capsys, "remove")
    assert code == 0 and doc["changed"] == "removed" and len(doc["removed"]) == (2 if system else 1)
    assert not box["local"].joinpath(L.launcher_name()).exists() and keep.exists()
    assert box["shared"].joinpath(L.launcher_name()).exists() is not system
    code, doc, _ = cli(capsys, "remove")
    assert code == 0 and doc["changed"] == "absent"


def test_folder_rules(box: dict[str, Path], capsys: Any, tmp_path: Path) -> None:
    code, _, err = cli(capsys, "install", "--app", str(box["app"]), "--dir", str(tmp_path / "missing"))
    assert code == 4 and "does not exist" in err and not (tmp_path / "missing").exists()
    if sys.platform != "win32" and os.geteuid() != 0:
        locked = tmp_path / "locked"
        locked.mkdir()
        locked.chmod(0o555)
        try:
            code, _, err = cli(capsys, "install", "--app", str(box["app"]), "--dir", str(locked))
            assert code == 4 and "never uses sudo" in err and not any(locked.iterdir())
        finally:
            locked.chmod(0o755)
    # the app's own folder: on Windows AgentPROV.exe is the agentprov.exe it would run before agentprov.cmd; on a
    # case-insensitive file system (APFS, the macOS default) agentprov and AgentPROV are one file; on a case-sensitive
    # one (ext4: the Linux CI legs) they are two, and the launcher goes beside the app
    beside = box["app"].parent / L.launcher_name()
    one_file = beside.exists()
    code, _, err = cli(capsys, "install", "--app", str(box["app"]), "--dir", str(box["app"].parent))
    if sys.platform == "win32":  # agentprov.exe is the app itself: refused as the app's folder (D-1130 review)
        assert code == 4 and "this is the app's own folder" in err
    elif one_file:
        assert code == 4 and ("would replace the app" in err or "already there" in err)
    else:
        assert code == 0 and L.launcher_app(beside) == str(box["app"])
    assert box["app"].read_text(encoding="utf-8").startswith("#!/bin/sh\necho")


def test_the_app_must_be_the_bundle(box: dict[str, Path], capsys: Any, tmp_path: Path) -> None:
    code, _, err = cli(capsys, "install")  # not frozen, no --app
    assert code == 4 and "no desktop app to link to" in err and not box["local"].exists()
    wrong = tmp_path / "agentprov-gui"
    wrong.write_text("#!/bin/sh\n", encoding="utf-8")
    wrong.chmod(0o755)
    assert cli(capsys, "install", "--app", str(wrong))[0] == 2
    assert cli(capsys, "install", "--app", str(tmp_path / "nope" / L.app_name()))[0] == 2
    # a launcher named AgentPROV would run itself
    fake = tmp_path / "loop" / L.app_name()
    fake.parent.mkdir()
    fake.write_text(L.render(str(fake)), encoding="utf-8")
    fake.chmod(0o755)
    code, _, err = cli(capsys, "install", "--app", str(fake))
    assert code == 2 and "run itself" in err


def test_frozen_uses_its_own_executable(box: dict[str, Path], capsys: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(box["app"]))
    code, doc, _ = cli(capsys, "install")
    assert code == 0 and doc["app"] == str(box["app"]) and L.launcher_app(box["launcher"]) == str(box["app"])


def test_windows_launcher_text() -> None:
    app = r"C:\Program Files (x86)\A&B\AgentPROV.exe"
    text = L.render(app, "win32")
    lines = text.split("\r\n")
    assert lines[0] == "@echo off" and lines[1] == f"rem {L.MARKER}"
    assert f'set "AGENTPROV_APP={app}"' in lines and '"%AGENTPROV_APP%" --cli %*' in lines
    assert not any(line.rstrip().endswith("(") for line in lines)  # no block a ")" in the path could close
    assert L.app_name("win32") == "AgentPROV.exe" and L.launcher_name("win32") == "agentprov.cmd"
    assert L._bad_chars(r"C:\100%\AgentPROV.exe", "win32") and L._bad_chars('C:\\a"b', "win32")
    assert not L._bad_chars(r"C:\Program Files (x86)\A&B", "win32") and L._bad_chars("/a\nb", "darwin")


def test_windows_launcher_is_recognised(tmp_path: Path) -> None:
    app = r"C:\Users\u\AppData\Local\AgentPROV\AgentPROV.exe"
    path = tmp_path / "agentprov.cmd"
    path.write_bytes(L.render(app, "win32").encode())
    assert L.is_launcher(path) and L.launcher_app(path) == app


def test_text_output(box: dict[str, Path], capsys: Any) -> None:
    assert main(["launcher", "install", "--app", str(box["app"]), "--progress", "off", "-q"]) == 0
    out = capsys.readouterr().out
    assert f"Terminal command installed: {box['launcher']}" in out and f'It runs: "{box["app"]}" --cli ARGS' in out
    assert main(["launcher", "status", "--progress", "off", "-q"]) == 0
    out = capsys.readouterr().out
    assert "this app's launcher" in out and "first agentprov on PATH: none" in out
