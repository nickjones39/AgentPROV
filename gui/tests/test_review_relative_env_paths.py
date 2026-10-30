"""GR-50: every path-valued allowlist entry reaches a GUI subprocess absolute and ``~``-expanded, not only
``AGENTPROV_HOME``. A child runs with its cwd in its job directory (or the checkout), so a relative
``AGENTPROV_SUITE_QUEUE_DIR`` gave each queued job a private queue, and ``tools/queue_status.py`` resolved a relative
``AGENTPROV_HOME`` against the checkout: the Sessions tab read a different queue from the one the jobs used."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

import agentprov_gui.jobs.manager as manager_mod
from agentprov_gui.jobs.manager import CliLocator, JobManager, allowlisted_env

posix_only = pytest.mark.skipif(os.name != "posix", reason="symlinked interpreter stand-in")
_PATHS = ("AGENTPROV_SUITE_QUEUE_DIR", "AGENTPROV_UPSTREAM_CACHE", "AGENTPROV_BASELINE_CORPUS", "TMPDIR")
_REL = "q" + "dir"


def test_child_env_makes_every_path_variable_absolute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(manager_mod, "_START_CWD", str(tmp_path))
    environ = {name: f"{_REL}-{i}" for i, name in enumerate(_PATHS)} | {"AGENTPROV_HOME": "rel" + "home"}
    env = JobManager(tmp_path / "home", CliLocator(None, (sys.executable,)), environ=environ).child_env()
    for i, name in enumerate(_PATHS):
        assert env[name] == str(tmp_path / f"{_REL}-{i}"), name
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    tilde = allowlisted_env({"AGENTPROV_UPSTREAM_CACHE": "~" + "/cache", "AGENTPROV_HOME": "~" + "/ap"})
    assert tilde == {"AGENTPROV_UPSTREAM_CACHE": str(tmp_path / "h" / "cache"),
                     "AGENTPROV_HOME": str(tmp_path / "h" / "ap")}


def test_paths_resolve_against_the_start_cwd_and_empty_stays_unset(tmp_path: Path,
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    start, later = tmp_path / "start", tmp_path / "later"
    start.mkdir()
    later.mkdir()
    monkeypatch.setattr(manager_mod, "_START_CWD", str(start))
    monkeypatch.chdir(later)
    env = allowlisted_env({"AGENTPROV_SUITE_QUEUE_DIR": _REL, "AGENTPROV_BASELINE_CORPUS": "", "PATH": "bin"})
    assert env == {"AGENTPROV_SUITE_QUEUE_DIR": str(start / _REL), "AGENTPROV_BASELINE_CORPUS": "", "PATH": "bin"}


def test_a_relative_path_is_dropped_when_the_start_cwd_is_unknown(monkeypatch: pytest.MonkeyPatch,
                                                                  caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(manager_mod, "_START_CWD", None)
    env = allowlisted_env({"AGENTPROV_SUITE_QUEUE_DIR": _REL, "AGENTPROV_UPSTREAM_CACHE": "/abs/cache"})
    assert env == {"AGENTPROV_UPSTREAM_CACHE": "/abs/cache"}
    assert any("AGENTPROV_SUITE_QUEUE_DIR" in r.getMessage() for r in caplog.records)


@posix_only
def test_queue_status_sees_the_jobs_home_and_queue(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtCore import QSettings

    import agentprov_gui.ui.runs as runs_mod
    from agentprov_gui.settings import Settings

    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setattr(manager_mod, "_START_CWD", str(work))
    monkeypatch.setenv("AGENTPROV_HOME", "rel" + "home")
    monkeypatch.setenv("AGENTPROV_SUITE_QUEUE_DIR", _REL)
    checkout = tmp_path / "checkout"
    dump = tmp_path / "queue-env.json"
    (checkout / "tools").mkdir(parents=True)
    (checkout / "tools" / "queue_status.py").write_text(
        "import json, os\n"
        f"open({str(dump)!r}, 'w').write(json.dumps(dict(os.environ)))\n"
        "print(json.dumps({'sessions': []}))\n", encoding="utf-8")
    (checkout / ".venv" / "bin").mkdir(parents=True)
    (checkout / ".venv" / "bin" / "python").symlink_to(sys.executable)
    monkeypatch.setattr(runs_mod, "submit", lambda owner, fn, done, *a, **k: done(fn(None)))
    manager = JobManager(Path("rel" + "home"), CliLocator(checkout, (sys.executable, "-c", "pass"),
                                                          (str(checkout / ".venv" / "bin" / "python"),)))
    page = runs_mod.RunsPage(manager, Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)))
    try:
        page._sessions_refresh()
    finally:
        page.tick_timer.stop()
        page.list_timer.stop()
        page.sessions_timer.stop()
        page.deleteLater()
    env = json.loads(dump.read_text(encoding="utf-8"))
    assert env["AGENTPROV_HOME"] == str(manager.home) == str(work / ("rel" + "home"))
    assert env["AGENTPROV_SUITE_QUEUE_DIR"] == str(work / _REL)
