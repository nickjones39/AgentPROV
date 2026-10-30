"""GUI review GR-5: every GUI subprocess gets the environment allowlist (design §4.2, S8), not the GUI's whole
environment. The ``--version`` probe, ``tools/queue_status.py`` and the About/manifest ``git`` calls used to inherit
``*_API_KEY``, ``UV_*`` and ``GIT_*`` variables."""

from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from _ast_support import modules, rel
from agentprov_gui.jobs.manager import ENV_ALLOWLIST, CliLocator, JobManager, allowlisted_env

posix_only = pytest.mark.skipif(os.name != "posix", reason="shell-script stand-ins")
SPAWNERS = {"run", "Popen", "check_output", "check_call", "call", "getoutput", "getstatusoutput"}
KEY = "OPENAI_" + "API_KEY"
SECRET = "sk-" + "proj-" + "x" * 24
GIT_DIR = "/nonexistent/" + "user-git-dir"


def _inherits_environ(value: ast.expr) -> bool:
    """An ``env=`` value that reads ``os.environ`` itself; the allowlist lives in one helper (``allowlisted_env``)."""
    return any(isinstance(node, ast.Attribute) and node.attr == "environ" for node in ast.walk(value))


def _subprocess_calls(tree: ast.Module) -> list[ast.Call]:
    imported = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "subprocess"
                for a in n.names}
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if (isinstance(f, ast.Attribute) and f.attr in SPAWNERS and isinstance(f.value, ast.Name)
                and f.value.id == "subprocess") or (isinstance(f, ast.Name) and f.id in imported & SPAWNERS):
            calls.append(node)
    return calls


def test_every_subprocess_call_passes_an_allowlisted_env() -> None:
    bad, seen = [], 0
    for path, tree in modules():
        for call in _subprocess_calls(tree):
            seen += 1
            env = next((k.value for k in call.keywords if k.arg == "env"), None)
            if env is None:
                bad.append(f"{rel(path)}:{call.lineno}: no env=")
            elif _inherits_environ(env):
                bad.append(f"{rel(path)}:{call.lineno}: env= inherits os.environ")
    assert seen >= 5, "the scan found too few subprocess calls; did the helper names change?"
    assert not bad, "\n".join(bad)


def test_allowlisted_env_keeps_only_the_allowlist() -> None:
    env = allowlisted_env({"PATH": "/bin", KEY: SECRET, "UV_INDEX_URL": "x", "GIT_DIR": GIT_DIR, "HOME": "/h"})
    assert env == {"PATH": "/bin", "HOME": "/h"} and set(env) <= set(ENV_ALLOWLIST)


def _hostile_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY, SECRET)
    monkeypatch.setenv("UV_" + "INDEX_URL", "https://user:pw@" + "index.invalid/simple")
    monkeypatch.setenv("GIT_" + "DIR", GIT_DIR)


def _dumper(path: Path, dump: Path) -> Path:
    """A Python script that records its environment in ``dump`` (and prints a queue_status-shaped JSON document)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("import json, os, sys\n"
                    f"open({str(dump)!r}, 'w').write(json.dumps(dict(os.environ)))\n"
                    "print(json.dumps({'sessions': []}))\n", encoding="utf-8")
    return path


def _assert_clean(dump: Path) -> None:
    """Only names and verdicts reach an assertion message, never an environment value."""
    env: dict[str, Any] = json.loads(dump.read_text(encoding="utf-8"))
    leaked = sorted(k for k in env if k == KEY or k.startswith(("UV_", "GIT_DIR")) or SECRET in env[k])
    assert not leaked, f"inherited: {leaked}"
    assert "PATH" in env


def test_version_probe_gets_the_allowlist(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov_gui.ui.worker as worker
    from agentprov_gui.ui.mainwindow import MainWindow

    _hostile_environ(monkeypatch)
    dump = tmp_path / "version-env.json"
    script = _dumper(tmp_path / "cli" / "dump.py", dump)
    ran: list[Any] = []
    monkeypatch.setattr(worker, "submit", lambda owner, fn, done, *a, **k: ran.append(fn(None)))

    class Owner:
        manager = JobManager(tmp_path / "home", CliLocator(tmp_path, (sys.executable, str(script))))

    MainWindow._version_check(Owner())  # type: ignore[arg-type]
    assert ran and dump.is_file()
    _assert_clean(dump)


@posix_only
def test_queue_status_gets_the_allowlist(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtCore import QSettings

    import agentprov_gui.ui.runs as runs_mod
    from agentprov_gui.settings import Settings

    _hostile_environ(monkeypatch)
    checkout = tmp_path / "checkout"
    dump = tmp_path / "queue-env.json"
    _dumper(checkout / "tools" / "queue_status.py", dump)
    (checkout / ".venv" / "bin").mkdir(parents=True)
    (checkout / ".venv" / "bin" / "python").symlink_to(sys.executable)
    monkeypatch.setattr(runs_mod, "submit", lambda owner, fn, done, *a, **k: done(fn(None)))
    manager = JobManager(tmp_path / "home", CliLocator(checkout, (sys.executable, "-c", "pass"), (str(checkout / ".venv" / "bin" / "python"),)))
    page = runs_mod.RunsPage(manager, Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)))
    try:
        page._sessions_refresh()
    finally:
        page.tick_timer.stop()
        page.list_timer.stop()
        page.sessions_timer.stop()
        page.deleteLater()
    assert dump.is_file()
    _assert_clean(dump)


@posix_only
def test_git_gets_the_allowlist_and_its_fixed_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui import about

    _hostile_environ(monkeypatch)
    dump = tmp_path / "git-env.json"
    bindir = tmp_path / "bin"
    git = _dumper(bindir / "git", dump)
    git.write_text(f"#!{sys.executable}\n" + git.read_text(encoding="utf-8"), encoding="utf-8")
    git.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    about.git_commit(tmp_path)
    assert dump.is_file()
    _assert_clean(dump)
    env = json.loads(dump.read_text(encoding="utf-8"))
    assert env["GIT_OPTIONAL_LOCKS"] == "0" and env["GIT_TERMINAL_PROMPT"] == "0" and env["LC_ALL"] == "C"
