"""GUI review GR-19: the job queue, the checkout tools and ``queue_status.py`` run with the interpreter the CLI locator
resolved (the ``.venv`` python, or ``uv run --locked --project <checkout> python``), never a hard-coded ``.venv`` path,
and a queue that cannot be run is a refusal (D-704: the checkout's ``agentprov jobs start`` refuses it,
``jobs.queue.unavailable``; ``tests/jobs``)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

import agentprov_gui.jobs.manager as manager_mod
from agentprov_gui.jobs.commands import JobSpec
from agentprov_gui.jobs.manager import CliLocator, JobManager, SpawnRefused

FAKE = Path(__file__).parent / "fake" / "fake_cli.py"
posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX executable script")


def _checkout(tmp_path: Path, *, queue: bool = True) -> Path:
    ck = tmp_path / "checkout"
    (ck / "tools").mkdir(parents=True)
    (ck / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    if queue:
        (ck / "tools" / "suite_queue.py").write_text("print('queue')\n", encoding="utf-8")
    (ck / "tools" / "ci_local.py").write_text("print('ci')\n", encoding="utf-8")
    (ck / "tools" / "queue_status.py").write_text("print('{}')\n", encoding="utf-8")
    return ck


def _fake_uv(tmp_path: Path) -> tuple[Path, Path]:
    """A stand-in ``uv`` that records its argv and prints a queue_status-shaped JSON document."""
    record = tmp_path / "uv-argv.json"
    uv = tmp_path / "bin" / "uv"
    uv.parent.mkdir(parents=True)
    uv.write_text(f"#!{sys.executable}\nimport json, sys\n"
                  f"open({str(record)!r}, 'w').write(json.dumps(sys.argv[1:]))\nprint(json.dumps({{'sessions': []}}))\n",
                  encoding="utf-8")
    uv.chmod(0o755)
    return uv, record


def _uv_locator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ck: Path) -> tuple[CliLocator, Path]:
    uv, record = _fake_uv(tmp_path)
    monkeypatch.setattr(manager_mod.shutil, "which", lambda name, *a, **k: str(uv) if name == "uv" else None)
    cli = CliLocator.for_checkout(ck)
    assert not (ck / ".venv").exists()
    return cli, record


def _queued(tmp_path: Path) -> JobSpec:
    return JobSpec("validate", ("validate", "--corpus", str(tmp_path / "c")), "R0", "v", extra={"queue_cpu": 2})


def _page(manager: JobManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    from PySide6.QtCore import QSettings

    import agentprov_gui.ui.runs as runs_mod
    from agentprov_gui.settings import Settings

    class Box:  # a refusal is reported, never shown modally (it would block the offscreen test)
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        def exec(self) -> int:
            return 0

    monkeypatch.setattr(runs_mod, "safe_message_box", Box)
    return runs_mod.RunsPage(manager, Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)))


def _close(page: Any) -> None:
    page.tick_timer.stop()
    page.list_timer.stop()
    page.sessions_timer.stop()
    page.deleteLater()


def test_the_uv_fallback_starts_queued_jobs_through_the_checkouts_cli(tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """D-704: the queue wrapper is built by the checkout's own ``agentprov jobs start`` with its own interpreter (under
    the uv fallback that is ``uv run --locked --project <checkout>``); the GUI passes ``--queue-cpu``."""
    ck = _checkout(tmp_path)
    cli, record = _uv_locator(tmp_path, monkeypatch, ck)
    run = (cli.program[0], "run", "--locked", "--project", str(ck))
    assert cli.program == (*run, "agentprov") and cli.python == (*run, "python")
    with pytest.raises(SpawnRefused):  # the stand-in uv prints no job id
        JobManager(tmp_path / "home", cli).spawn(_queued(tmp_path))
    seen = json.loads(record.read_text(encoding="utf-8"))
    assert seen[:7] == ["run", "--locked", "--project", str(ck), "agentprov", "jobs", "start"]
    assert seen[seen.index("--queue-cpu") + 1] == "2" and not any(".venv" in a for a in seen)


def test_a_venv_cli_brings_its_venv_python(tmp_path: Path) -> None:
    ck = _checkout(tmp_path)
    exe = ck / ".venv" / ("Scripts/agentprov.exe" if os.name == "nt" else "bin/agentprov")
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")
    cli = CliLocator.for_checkout(ck)
    assert cli.python == (str(ck / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")),)


@posix_only
def test_tools_and_sessions_use_the_resolved_python(qapp: Any, tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov_gui.ui.runs as runs_mod

    ck = _checkout(tmp_path)
    cli, record = _uv_locator(tmp_path, monkeypatch, ck)
    monkeypatch.setattr(runs_mod, "submit", lambda owner, fn, done, *a, **k: done(fn(None)))
    page = _page(JobManager(tmp_path / "home", cli), tmp_path, monkeypatch)
    try:
        assert page.tool_program("tools/ci_local.py") == (*cli.python, str(ck / "tools" / "ci_local.py"), "-C", str(ck))
        page._sessions_refresh()
        assert json.loads(record.read_text(encoding="utf-8")) == [
            "run", "--locked", "--project", str(ck), "python", str(ck / "tools" / "queue_status.py"), "--json"]
    finally:
        _close(page)
