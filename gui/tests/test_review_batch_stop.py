"""User report 2026-11-05: a dev run could not be stopped. Runs › Batches has Stop Batch… (the selected batch) and Runs ›
Dev Runs has Stop Dev Run… (the latest running dev run's batch, and a running live dev-run job): each asks first, runs
``agentprov batch stop ID --steps`` off the UI thread and is enabled only while there is something running to stop. The
CLI's rules (the driver and every step job stopped, no further step started) are tested in ``tests/jobs/test_batch.py``.
"""

from __future__ import annotations

import json
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from agentprov_gui.jobs import batch as batch_client
from agentprov_gui.jobs.commands import JobSpec
from agentprov_gui.jobs.manager import CliLocator, Job, JobManager
from test_viewer import wait

FAKE = Path(__file__).parent / "fake" / "fake_cli.py"
RUN = "20261105T000000Z"


@pytest.fixture
def page(qapp: Any, tmp_path: Path) -> Iterator[Any]:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.runs import RunsPage

    manager = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))))
    runs = RunsPage(manager, Settings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)))
    runs.tick_timer.stop()
    runs.list_timer.stop()
    yield runs
    for j in list(runs.manager.refresh()):
        if j.state == "running":
            runs.manager.kill(j)
    runs.deleteLater()


def _dev_batch(page: Any) -> str:
    """A planted two-step dev-run batch (not started)."""
    specs = [JobSpec("import", ("import", "--units", "1"), "R1", "dev run · import a/p", extra={"devrun": RUN}),
             JobSpec("validate", ("validate", "--units", "1"), "R0", "dev run · validate a/p", extra={"devrun": RUN})]
    return batch_client.create(page.manager, f"dev run {RUN}", specs)


def _show(page: Any, jobs: list[Job]) -> None:
    """The views as a refresh leaves them, with ``jobs`` as the job list (no processes)."""
    from agentprov_gui.jobs.batch import Batch

    page.batches = Batch.load_all(page.manager.home)
    page.model.set_jobs(jobs)
    page._batches_view()
    page._dev_view()


def _job(tmp_path: Path, job_id: str, **record: Any) -> Job:
    return Job(job_id, tmp_path / job_id, {"label": job_id, **record}, "running")


def test_the_stop_buttons_are_enabled_only_while_something_runs(page: Any, tmp_path: Path) -> None:
    bid = _dev_batch(page)
    _show(page, [])
    page.batch_table.setCurrentCell(0, 0)
    assert not page.stop_batch_btn.isEnabled() and not page.stop_dev_btn.isEnabled()  # created, nothing runs
    _show(page, [_job(tmp_path, "step-job", batch_id=bid, devrun=RUN)])
    page.batch_table.setCurrentCell(0, 0)
    assert page.stop_batch_btn.isEnabled() and page.stop_dev_btn.isEnabled()
    assert page.dev_run_targets()[0].batch_id == bid
    ended = _job(tmp_path, "step-job", batch_id=bid, devrun=RUN)
    ended.state = "ended"
    _show(page, [ended])
    assert not page.stop_batch_btn.isEnabled() and not page.stop_dev_btn.isEnabled()
    # a live dev run is one job outside any batch: Stop Dev Run covers it, and the tab says where else it stops
    _show(page, [_job(tmp_path, "live-job", command="run", devrun=True)])
    assert page.stop_dev_btn.isEnabled() and not page.stop_batch_btn.isEnabled()
    assert "Stop Dev Run" in page.dev_info.text() and "Jobs tab" in page.dev_info.text()


def test_stop_batch_asks_then_calls_the_cli_off_the_ui_thread(page: Any, tmp_path: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov_gui.ui.runs as runs_mod

    bid = _dev_batch(page)
    _show(page, [_job(tmp_path, "driver")])
    doc = json.loads((page.manager.home / "batches" / f"{bid}.json").read_text())
    doc["driver_job_id"] = "driver"
    (page.manager.home / "batches" / f"{bid}.json").write_text(json.dumps(doc))
    calls: list[tuple[list[str], bool]] = []

    def call(argv: list[str], **_k: Any) -> tuple[int, bytes, bytes]:
        calls.append((list(argv), threading.current_thread() is threading.main_thread()))
        return 0, json.dumps({"driver": "stopped", "steps_stopped": [], "steps_unsignalled": [],
                              "still_running": []}).encode(), b""

    monkeypatch.setattr(page.manager, "call", call)
    monkeypatch.setattr(page, "refresh", lambda: _show(page, [_job(tmp_path, "driver")]))
    _show(page, [_job(tmp_path, "driver")])
    page.batch_table.setCurrentCell(1, 0)
    assert page.stop_batch_btn.isEnabled()
    asked: list[str] = []
    monkeypatch.setattr(runs_mod, "ask", lambda parent, title, text, info="", **k: asked.append(info) or False)
    page.stop_batch()
    assert calls == [] and "Resume Batch" in asked[0] and "130" in asked[0]  # cancelled: nothing stopped
    monkeypatch.setattr(runs_mod, "ask", lambda *a, **k: True)
    page.stop_batch()
    assert calls == [(["batch", "stop", "--steps", "--wait", "5.0", "--format", "json", bid], False)]


def test_the_stop_cards_are_the_argv_the_buttons_run(page: Any, tmp_path: Path) -> None:
    """AU-NG-3: Stop Batch's and Stop Dev Run's terminal cards show the argv ``batch stop`` runs (its ``--wait``
    included), only without ``--format json``, as every job card."""
    from agentprov_gui.jobs.batch import Batch, BatchStep
    from agentprov_gui.ui.runs import batch_commands, dev_commands

    calls: list[list[str]] = []
    manager = type("M", (), {"call": lambda self, argv, **_k: calls.append(list(argv)) or (0, b"{}", b"")})()
    batch_client.stop(manager, "b1", steps=True)  # type: ignore[arg-type]
    (action,) = calls
    i = action.index("--format")
    shown = tuple(action[:i] + action[i + 2:])
    assert "--wait" in shown
    b = Batch("b1", "label", [BatchStep(JobSpec("validate", ("validate",), "R0", "x"))])
    assert dict(batch_commands(b, True))["stop it and its running steps"] == shown
    assert dict(dev_commands(b, []))["stop the running dev run"] == shown


def test_stop_dev_run_stops_a_live_dev_run_job_off_the_ui_thread(page: Any, tmp_path: Path,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov_gui.ui.runs as runs_mod

    live = _job(tmp_path, "live-job", command="run", devrun=True)
    monkeypatch.setattr(page, "refresh", lambda: _show(page, [live]))
    _show(page, [live])
    seen: list[tuple[str, str, bool]] = []
    monkeypatch.setattr(page.manager, "request", lambda job, what: seen.append(
        (job.job_id, what, threading.current_thread() is threading.main_thread())) and False)
    monkeypatch.setattr(page.manager, "stop", lambda job: seen.append(
        (job.job_id, "sigterm", threading.current_thread() is threading.main_thread())) or True)
    monkeypatch.setattr(page.manager, "call", lambda *a, **k: pytest.fail("no batch to stop"))
    monkeypatch.setattr(runs_mod, "ask", lambda *a, **k: True)
    page.stop_dev_run()
    assert seen == [("live-job", "stop", False), ("live-job", "sigterm", False)]
    assert "stop_requested_at" in live.record


def test_stop_dev_run_stops_a_real_running_dev_run_batch(qapp: Any, page: Any, monkeypatch: pytest.MonkeyPatch
                                                         ) -> None:
    """End to end through the fake CLI (the core's ``batch``): the running import step and the driver stop, the
    validate step never starts, and the views show it."""
    import agentprov_gui.ui.runs as runs_mod

    specs = [JobSpec("import", ("import", "--units", "200", "--sleep", "0.1"), "R1", "dev run · import a/p",
                     extra={"devrun": RUN}),
             JobSpec("validate", ("validate", "--units", "1"), "R0", "dev run · validate a/p", extra={"devrun": RUN})]
    batch = page.start_batch(f"dev run {RUN}", specs, continue_on_failure=True)
    assert batch is not None

    def step_running() -> bool:
        page.refresh()
        return page.dev_run_targets()[0] is not None and any(s.state == "running" for s in page.batches[-1].steps)

    wait(qapp, step_running, 60)
    assert page.stop_dev_btn.isEnabled()
    monkeypatch.setattr(runs_mod, "ask", lambda *a, **k: True)
    page.stop_dev_run()
    wait(qapp, lambda: page.refresh() is None and not any(j.state == "running" for j in page.model.jobs), 60)
    page.refresh()
    (stopped,) = [b for b in page.batches if b.batch_id == batch.batch_id]
    assert [(s.state, s.exit_code) for s in stopped.steps] == [("failed", 130), ("pending", None)]
    assert len(page.model.jobs) == 2  # the driver and the import step: nothing started after the stop
    assert not page.stop_dev_btn.isEnabled() and not page.stop_batch_btn.isEnabled()
