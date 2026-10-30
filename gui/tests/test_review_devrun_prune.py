"""GUI review GR-25: a dev run's prune never deletes a run folder that is in use (a running job's paths, a resumed
dev-run job, an unfinished batch's pending steps)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from agentprov_gui.jobs.commands import JobSpec
from agentprov_gui.jobs.manager import CliLocator, JobManager
from test_viewer import wait

FAKE = Path(__file__).parent / "fake" / "fake_cli.py"
OLD = ("20261001T000000Z", "20261002T000000Z", "20261003T000000Z")


@pytest.fixture
def page(qapp: Any, tmp_path: Path) -> Any:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.runs import RunsPage

    manager = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))))
    runs = RunsPage(manager, Settings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)))
    runs.tick_timer.stop()  # no batch advances behind the test's back
    runs.list_timer.stop()
    yield runs
    for j in list(runs.manager.jobs.values()):
        if j.state == "running":
            runs.manager.kill(j)
    runs.deleteLater()


def test_resume_keeps_the_dev_run_keys(qapp: Any, page: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov_gui.ui.jobdialog as jd

    extra = {"devrun": OLD[0], "part": "a/p", "queue_cpu": 3}
    job = page.start(JobSpec("import", ("import", "--units", "1"), "R1", "dev run · import a/p", extra=extra))
    assert job is not None
    wait(qapp, lambda: page.manager.refresh() is not None and page.manager.jobs[job.job_id].state != "running", 30)
    page.refresh()
    page.select(job.job_id)
    seen: list[JobSpec] = []
    monkeypatch.setattr(jd, "confirm", lambda parent, spec, preview: seen.append(spec))
    page.resume()
    assert {k: seen[0].extra.get(k) for k in extra} == extra and seen[0].extra.get("resumes") == job.job_id
    page.selected.record.update(devrun=["x"], part=7, queue_cpu=True)  # wrong types are dropped, never carried
    page.resume()
    assert not {"devrun", "part", "queue_cpu"} & set(seen[1].extra)


def test_start_dev_run_plans_confirms_and_starts_through_the_cli(qapp: Any, page: Any,
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """D-705: Start Dev Run asks ``agentprov devrun plan`` for the confirmation text and then runs ``devrun start
    --confirm-r2``; a cancelled confirmation starts nothing. The run folder, its batch and the pruning (GR-25, GR-26)
    are the CLI's (``tests/devrun``)."""
    import json

    import agentprov_gui.ui.runs as runs_mod

    calls: list[list[str]] = []
    plan = {"format": "agentprov-devrun-plan/0.1", "settings": {"mode": "first", "keep": 5, "queue_cpu": 2},
            "parts": [{"source": "a", "part": "p", "samples": 5}], "steps": [{}, {}, {}], "queue": True}

    def call(argv: list[str], **_k: Any) -> tuple[int, bytes, bytes]:
        calls.append(list(argv))
        if argv[:2] == ["devrun", "plan"]:
            return 0, json.dumps(plan).encode(), b""
        return 0, b'{"run_dir": "/x", "batch_id": "b", "driver_job_id": "d"}', b""

    page.manager.cli = CliLocator(page.manager.home, page.manager.cli.program)  # a configured checkout
    monkeypatch.setattr(page.manager, "call", call)
    monkeypatch.setattr(runs_mod, "ask", lambda *a, **k: False)
    page.start_dev_run()
    assert [c[:2] for c in calls] == [["devrun", "plan"]]
    monkeypatch.setattr(runs_mod, "ask", lambda *a, **k: True)
    page.start_dev_run()
    assert calls[-1] == ["devrun", "start", "--confirm-r2", "--format", "json"]
