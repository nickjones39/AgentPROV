"""GUI review GR-33: Settings › Jobs and Settings › CI never claim to do what nothing does. A batch started without an
explicit ``continue_on_failure`` follows the stored "Batches continue after exit 4 or 70" (D-704: ``agentprov batch
create`` reads ``jobs.continue_on_failure``); job retention is what ``agentprov jobs prune`` keeps by default; the
default CI target is not used yet, and its row says so."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from agentprov import settings as core_settings

from agentprov_gui.jobs.manager import CliLocator, JobManager

FAKE = Path(__file__).parent / "fake" / "fake_cli.py"


def _page(tmp_path: Path) -> Any:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.runs import RunsPage

    manager = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))))
    runs = RunsPage(manager, Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)))
    runs.tick_timer.stop()
    runs.list_timer.stop()
    return runs


@pytest.mark.parametrize("stored", [True, False, None])
def test_start_batch_follows_the_jobs_setting(qapp: Any, tmp_path: Path, stored: bool | None) -> None:
    """D-704: the batch is the CLI's (``batch create --stdin``), which needs at least one step."""
    from agentprov_gui.jobs.commands import JobSpec

    page = _page(tmp_path)
    if stored is not None:
        core_settings.set("jobs.continue_on_failure", stored, home=page.manager.home)
    step = [JobSpec("import", ("import", "--units", "0"), "R1", "s")]
    try:
        first = page.start_batch("one", step)
        assert first is not None and first.continue_on_failure is (stored is True)
        second = page.start_batch("explicit", step, continue_on_failure=stored is not True)
        assert second is not None and second.continue_on_failure is (stored is not True)
    finally:
        page.deleteLater()


def test_rows_say_what_the_settings_do(qapp: Any) -> None:
    from agentprov_gui.ui.safe import SafeLabel
    from agentprov_gui.ui.settings_panes import CiPane, JobsPane

    jobs, ci = JobsPane(None), CiPane(None)
    try:
        def label_of(pane: Any, field: Any) -> str:
            labels = [w for w in pane.findChildren(SafeLabel) if w.buddy() is field]
            assert len(labels) == 1
            return str(labels[0].text())

        assert "agentprov jobs prune" in label_of(jobs, jobs.retention)
        assert "not used yet" in label_of(ci, ci.target)
    finally:
        jobs.deleteLater()
        ci.deleteLater()
