"""GUI review GR-18: a program that cannot be started is a refusal, not an exception, and leaves no job directory.
After D-704 the program is the checkout's ``agentprov jobs start``; a batch step that cannot start is the core's
(``tests/jobs``)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from agentprov_gui.jobs.commands import FORMS, FormError, JobSpec, build_spec
from agentprov_gui.jobs.manager import CliLocator, JobManager, SpawnRefused

FAKE = Path(__file__).parent / "fake" / "fake_cli.py"
_NUL = chr(0)


def _missing(tmp_path: Path) -> JobManager:
    return JobManager(tmp_path / "home", CliLocator(None, (str(tmp_path / "missing" / "agentprov"),)))


def _job_dirs(manager: JobManager) -> list[Path]:
    return sorted(manager.jobs_dir.iterdir()) if manager.jobs_dir.is_dir() else []


def _spec(tmp_path: Path) -> JobSpec:
    return JobSpec("validate", ("validate", "--corpus", str(tmp_path / "c")), "R0", "v")


def test_a_missing_program_is_refused_and_leaves_no_job_directory(tmp_path: Path) -> None:
    m = _missing(tmp_path)
    with pytest.raises(SpawnRefused) as caught:
        m.spawn(_spec(tmp_path))
    assert caught.value.code == "gui.spawn.failed"
    assert str(tmp_path) not in caught.value.reason
    assert _job_dirs(m) == [] and m.jobs == {}


def test_an_argv_popen_rejects_is_refused_and_leaves_no_job_directory(tmp_path: Path) -> None:
    m = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))))
    spec = JobSpec("stats", ("stats", "--tables", "a" + _NUL + "b"), "R0", "s")
    with pytest.raises(SpawnRefused) as caught:
        m.spawn(spec)
    assert caught.value.code == "gui.spawn.failed"
    assert _job_dirs(m) == []


def test_runs_page_reports_a_spawn_failure(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtCore import QSettings

    import agentprov_gui.ui.runs as runs_mod
    from agentprov_gui.settings import Settings

    shown: list[str] = []

    class Box:
        def __init__(self, *a: Any, **k: Any) -> None:
            shown.append(str(k.get("informative", "")))

        def exec(self) -> int:
            return 0

    monkeypatch.setattr(runs_mod, "safe_message_box", Box)
    page = runs_mod.RunsPage(_missing(tmp_path), Settings(QSettings(str(tmp_path / "s.ini"),
                                                                     QSettings.Format.IniFormat)))
    try:
        assert page.start(_spec(tmp_path)) is None
        assert shown and str(tmp_path) not in shown[0]
        assert _job_dirs(page.manager) == []
    finally:
        page.tick_timer.stop()
        page.list_timer.stop()
        page.deleteLater()


@pytest.mark.parametrize("bad", [_NUL, chr(10), chr(13), chr(27), chr(127)])
def test_additional_options_refuse_control_characters(tmp_path: Path, bad: str) -> None:
    with pytest.raises(FormError, match="control characters"):
        build_spec(FORMS["stats"], {"corpus": str(tmp_path / "c")}, extra="--tables 'a" + bad + "b'")


def test_a_job_record_that_cannot_be_written_is_refused_and_leaves_no_job_directory(tmp_path: Path) -> None:
    """GR-52: a lone surrogate (a Linux ``surrogateescape`` name) in argv fails the job.json encode after mkdir."""
    m = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))))
    lone = chr(0xDC00 + 0xFF)
    spec = JobSpec("validate", ("validate", "--corpus", str(tmp_path / ("corpus-" + lone))), "R0", "v")
    with pytest.raises(SpawnRefused) as caught:
        m.spawn(spec)
    assert caught.value.code in ("gui.spawn.failed", "jobs.spawn.failed")  # refused by the GUI or by `jobs start`
    assert _job_dirs(m) == [] and m.jobs == {}
