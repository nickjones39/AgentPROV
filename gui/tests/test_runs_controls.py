"""D-1061 and the Runs page in the house style: the selected job's header (state badge, progress, the facts a live run
records), the controls Pause, Resume, Stop, Cancel Run… and Force Kill… each enabled only when it applies, Cancel's
confirmation and its ``agentprov jobs cancel ID`` off the UI thread, Resume refused for a cancelled job, and the
terminal command cards built from the ``jobs``, ``batch`` and ``devrun`` forms with the real ids. The CLI's rules
(the mark, the refusal, stop unchanged) are tested in ``tests/jobs/test_jobs_cancel.py``."""

from __future__ import annotations

import json
import os
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from agentprov_gui.jobs.commands import FORMS, JobSpec, build_spec
from agentprov_gui.jobs.manager import CliLocator, Job, JobManager
from test_viewer import wait

FAKE = Path(__file__).parent / "fake" / "fake_cli.py"


@pytest.fixture
def page(qapp: Any, tmp_path: Path) -> Iterator[Any]:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.runs import RunsPage

    manager = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))))
    runs = RunsPage(manager, Settings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)))
    runs.tick_timer.stop()
    runs.list_timer.stop()
    runs.resize(1100, 900)
    yield runs
    for j in list(runs.manager.refresh()):
        if j.state == "running":
            runs.manager.kill(j)
    runs.deleteLater()


def _job(tmp_path: Path, job_id: str, state: str = "running", *, exit_code: int | None = None,
         outcome: str | None = None, control: str | None = None, abandoned: bool = False, **record: Any) -> Job:
    """A planted job (no process): its directory with the control request and the cancel mark it should have."""
    directory = tmp_path / "jobs" / job_id
    directory.mkdir(parents=True, exist_ok=True)
    if control is not None:
        (directory / "control.json").write_text(json.dumps({"format": "agentprov-control/0.1", "request": control,
                                                            "issued": "2026-11-05T01:00:00Z", "nonce": "0" * 16}))
    if abandoned:
        (directory / "abandoned.json").write_text(json.dumps({"format": "agentprov-job-abandoned/0.1"}))
    rec = {"label": job_id, "command": "import", "argv": ["agentprov", "import"], "subcommand_argv": ["import"],
           "created": "2026-11-05T01:02:03Z", "tier": "R1", **record}
    return Job(job_id, directory, rec, state, exit_code, outcome)


def _show(page: Any, job: Job) -> None:
    page.model.set_jobs([job])
    page.select(job.job_id)


def _enabled(page: Any) -> dict[str, bool]:
    return {name: getattr(page, f"{name}_btn").isEnabled() for name in ("drain", "resume", "stop", "cancel", "kill")}


# ------------------------------------------------------------------------------------------------- states
@pytest.mark.parametrize(("state", "kw", "word"), [
    ("running", {}, "Running"),
    ("running", {"control": "drain", "control_file": True}, "Pausing"),
    ("running", {"control": "stop", "control_file": True}, "Stopping"),
    ("running", {"stop_requested_at": 1.0}, "Stopping"),
    ("running", {"abandoned": True}, "Stopping"),
    ("ended", {"exit_code": 0, "control": "drain", "control_file": True}, "Paused"),
    ("ended", {"exit_code": 0}, "Ended"),
    ("ended", {"exit_code": 130, "outcome": "interrupted"}, "Stopped"),
    ("ended", {"exit_code": None, "outcome": "killed"}, "Stopped"),
    ("ended", {"exit_code": 130, "abandoned": True}, "Cancelled"),
    ("ended", {"exit_code": 1, "outcome": "failures"}, "Failed"),
    ("unobserved", {}, "Ended, unobserved"),
])
def test_the_state_words(tmp_path: Path, state: str, kw: dict[str, Any], word: str) -> None:
    from agentprov_gui.ui.runs import JobInfo, job_status

    job = _job(tmp_path, "j", state, **kw)
    assert job_status(job, JobInfo.read(job))[0] == word


def test_a_drain_that_ended_with_exit_0_is_paused_only_by_the_progress_outcome_when_there_is_one(tmp_path: Path
                                                                                                ) -> None:
    from agentprov_gui.ui.runs import JobInfo, job_status

    job = _job(tmp_path, "j", "ended", exit_code=0, control="drain", control_file=True)
    info = JobInfo.read(job)
    assert job_status(job, info, outcome="drained")[0] == "Paused"
    assert job_status(job, info, outcome="ok")[0] == "Ended"  # it finished every unit before the drain took effect
    assert job_status(_job(tmp_path, "k", "ended", exit_code=0), JobInfo(), outcome="drained")[0] == "Paused"


# ------------------------------------------------------------------------------------------------- controls
def test_each_control_is_enabled_only_when_it_applies(page: Any, tmp_path: Path) -> None:
    _show(page, _job(tmp_path, "a", control_file=True))
    assert page.state_badge.text() == "Running" and page.state_badge.kind == "info"
    assert _enabled(page) == {"drain": True, "resume": False, "stop": True, "cancel": True, "kill": True}
    _show(page, _job(tmp_path, "b"))  # no control file: no Pause
    assert _enabled(page) == {"drain": False, "resume": False, "stop": True, "cancel": True, "kill": True}
    assert "cannot be paused" in page.command_note.text()
    _show(page, _job(tmp_path, "c", control="drain", control_file=True))  # pausing: Pause was asked for
    assert page.state_badge.text() == "Pausing"
    assert _enabled(page) == {"drain": False, "resume": False, "stop": True, "cancel": True, "kill": True}
    _show(page, _job(tmp_path, "d", "ended", exit_code=130, outcome="interrupted"))
    assert page.state_badge.text() == "Stopped"
    assert _enabled(page) == {"drain": False, "resume": True, "stop": False, "cancel": True, "kill": False}
    _show(page, _job(tmp_path, "e", "ended", exit_code=130, abandoned=True))
    assert page.state_badge.text() == "Cancelled" and page.state_badge.kind == "neutral"
    assert _enabled(page) == {"drain": False, "resume": False, "stop": False, "cancel": False, "kill": False}
    assert "never resumed" in page.command_note.text()
    _show(page, _job(tmp_path, "f", abandoned=True))  # cancelled, its stop not through yet: Stop and Kill stay
    assert page.state_badge.text() == "Stopping"
    assert _enabled(page) == {"drain": False, "resume": False, "stop": True, "cancel": True, "kill": True}


def test_cancel_reads_run_for_a_live_run_and_job_otherwise(page: Any, tmp_path: Path) -> None:
    _show(page, _job(tmp_path, "r", command="run", label="guide"))
    assert page.cancel_btn.text() == "Cancel Run…" and page.title.text() == "Live run · guide"
    assert "cells" in page.control_help[0].text() and "caps carry over" in page.control_help[1].text()
    _show(page, _job(tmp_path, "i"))
    assert page.cancel_btn.text() == "Cancel Job…" and "units" in page.control_help[0].text()


def test_cancel_asks_then_calls_the_cli_off_the_ui_thread(page: Any, tmp_path: Path,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov_gui.ui.runs as runs_mod

    job = _job(tmp_path, "0190aaaa-bbbb-7ccc-8ddd-eeeeffff0001", command="run")
    _show(page, job)
    monkeypatch.setattr(page, "refresh", lambda: _show(page, job))
    calls: list[tuple[list[str], bool]] = []
    monkeypatch.setattr(page.manager, "call", lambda argv, **_k: calls.append(
        (list(argv), threading.current_thread() is threading.main_thread())) or (0, b"", b""))
    asked: list[tuple[str, str, str]] = []
    monkeypatch.setattr(runs_mod, "ask", lambda _p, title, text, info="", **_k: asked.append((title, text, info))
                        or False)
    page.cancel()
    assert calls == [] and asked[0][:2] == ("Cancel run", "Cancel this run?")  # declined: nothing sent
    assert "aborted" in asked[0][2] and "never be resumed" in asked[0][2] and "Nothing is deleted" in asked[0][2]
    monkeypatch.setattr(runs_mod, "ask", lambda *a, **k: True)
    page.cancel()
    expected = list(build_spec(FORMS["jobs_cancel"], {"job_id": job.job_id}).argv)
    assert calls == [(expected, False)] and expected == ["jobs", "cancel", job.job_id]
    assert "stop_requested_at" in job.record
    # the card lists the very command Cancel runs, with the real id
    assert ("cancel: stop, and never resume", tuple(expected)) in page.command_card.commands


def test_cancel_of_an_ended_job_says_it_only_marks_it(page: Any, tmp_path: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov_gui.ui.runs as runs_mod

    _show(page, _job(tmp_path, "x", "ended", exit_code=130))
    asked: list[str] = []
    monkeypatch.setattr(runs_mod, "ask", lambda _p, _t, _x, info="", **_k: asked.append(info) or False)
    page.cancel()
    assert "aborted" not in asked[0] and "never be resumed" in asked[0]


def test_resume_is_refused_for_a_cancelled_job(page: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov_gui.ui.runs as runs_mod

    _show(page, _job(tmp_path, "y", "ended", exit_code=130, abandoned=True))
    shown: list[str] = []

    class Box:
        def __init__(self, _p: Any, _title: str, text: str, **_k: Any) -> None:
            shown.append(text)

        def exec(self) -> int:
            return 0

    monkeypatch.setattr(runs_mod, "safe_message_box", Box)
    monkeypatch.setattr(page, "start", lambda *a, **k: pytest.fail("a cancelled job is never resumed"))
    page.resume()
    assert shown == ["This job was cancelled, so it is not resumed."]


# ------------------------------------------------------------------------------------------------- command cards
def test_the_job_command_card_uses_the_real_id_and_only_the_commands_that_apply(page: Any, tmp_path: Path) -> None:
    from agentprov_gui.ui.runs import JobInfo, job_commands

    def forms(job: Job, *names: str) -> list[tuple[str, ...]]:
        return [build_spec(FORMS[f"jobs_{n}"], {"job_id": job.job_id, "format": None}).argv for n in names]

    running = _job(tmp_path, "0190aaaa-bbbb-7ccc-8ddd-eeeeffff0002", control_file=True)
    _show(page, running)
    assert [argv for _c, argv in page.command_card.commands] == forms(running, "drain", "stop", "resume", "cancel",
                                                                      "follow")
    assert page.command_card.plain().splitlines()[1] == f"agentprov jobs drain {running.job_id}"
    ended = _job(tmp_path, "0190aaaa-bbbb-7ccc-8ddd-eeeeffff0003", "ended", exit_code=130)
    assert [a for _c, a in job_commands(ended, JobInfo())] == forms(ended, "resume", "cancel", "follow")
    cancelled = _job(tmp_path, "0190aaaa-bbbb-7ccc-8ddd-eeeeffff0004", "ended", exit_code=130, abandoned=True)
    assert [a for _c, a in job_commands(cancelled, JobInfo.read(cancelled))] == forms(cancelled, "follow")


def test_the_card_commands_are_what_stop_and_pause_run(page: Any, tmp_path: Path,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop and Pause run ``jobs stop ID`` and ``jobs drain ID`` (the GUI manager's calls): the card shows the same."""
    import agentprov_gui.ui.runs as runs_mod

    job = _job(tmp_path, "0190aaaa-bbbb-7ccc-8ddd-eeeeffff0005", control_file=True)
    _show(page, job)
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(page.manager, "call", lambda argv, **_k: calls.append(tuple(argv)) or (0, b"", b""))
    monkeypatch.setattr(runs_mod, "ask", lambda *a, **k: True)
    page.drain()
    page.stop()
    card = {argv[1]: argv for _c, argv in page.command_card.commands}
    assert calls == [card["drain"], card["stop"]]


def test_the_batch_and_dev_run_cards(page: Any, tmp_path: Path) -> None:
    from agentprov_gui.jobs import batch as batch_client
    from agentprov_gui.jobs.batch import Batch

    bid = batch_client.create(page.manager, "b", [JobSpec("import", ("import",), "R1", "step",
                                                          extra={"devrun": "20261105T000000Z"})])
    page.batches = Batch.load_all(page.manager.home)
    page.model.set_jobs([_job(tmp_path, "step-job", batch_id=bid)])
    page._batches_view()
    page.batch_table.setCurrentCell(0, 0)
    argvs = [argv for _c, argv in page.batch_card.commands]
    assert ("batch", "show", bid) in argvs and ("batch", "resume", "--confirm-r2", bid) in argvs
    assert ("batch", "stop", "--steps", "--wait", "5.0", bid) in argvs  # it runs
    page._dev_view()
    dev = [argv for _c, argv in page.dev_card.commands]
    assert dev[:3] == [("devrun", "plan"), ("devrun", "start", "--confirm-r2"), ("devrun", "list")]
    assert ("batch", "stop", "--steps", "--wait", "5.0", bid) in dev and page.dev_badge.text() == "Running"


# ------------------------------------------------------------------------------------------------- a live run
def test_a_live_run_shows_the_facts_its_files_record(qapp: Any, page: Any, tmp_path: Path) -> None:
    from agentprov_gui.ui.runs import Follower

    corpus = tmp_path / "corpora" / "guide"
    (corpus.with_name("guide.partial")).mkdir(parents=True)
    (corpus.with_name("guide.partial") / "corpus.json").write_text(json.dumps({"format": "agentprov-corpus/0.1", "live": {
        "model_requested": "gpt-4o-mini", "endpoint": "openai", "transport": "http", "jobs": 4,
        "caps": {"max_calls": 5000, "billed_calls": 1204, "max_cost_usd": "5", "spend_upper_bound_usd": "0.41"}}}))
    job = _job(tmp_path, "live", command="run", label="agentdojo-live-guide", writes=[str(corpus)],
               control_file=True)
    lines = [{"event": "start", "total": 160}, *[{"event": "unit_start"}, {"event": "unit_done", "status": "sealed"}]
             * 61, *[{"event": "unit_start"}] * 3]
    (job.directory / "progress.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    page.followers[job.job_id] = Follower(job)
    page.followers[job.job_id].tick()
    _show(page, job)
    wait(qapp, lambda: "Model calls" in page.facts.text(), 20)
    facts = page.facts.text()
    assert facts.startswith("61 of 160 cells · 3 in progress · Model calls 1,204 of 5,000 cap · Cost (upper bound) "
                            "$0.41 of $5.00 cap")
    assert page.title.text() == "Live run · agentdojo-live-guide"
    assert "gpt-4o-mini through openai · 4 traces at once" in page.subtitle.text()
    assert page.subtitle.text().startswith("Started ") and ("NZ" in page.subtitle.text() or "today" in
                                                            page.subtitle.text() or "2026" in page.subtitle.text())
    assert page.bar.maximum() == 160 and page.bar.value() == 61


def test_a_run_without_caps_shows_no_call_or_cost_facts(page: Any, tmp_path: Path) -> None:
    from agentprov_gui.ui.runs import live_facts

    assert live_facts({"transport": "scripted", "endpoint": "scripted", "model_requested": "scripted-fake"}) == {
        "model": "a scripted model"}
    assert live_facts(None) == {} and live_facts({"caps": "x", "jobs": True}) == {}
    assert live_facts({"caps": {"billed_calls": 3}})["calls"] == "3"  # no cap recorded: the count alone


# ------------------------------------------------------------------------------------------------- end to end
@pytest.mark.skipif(os.name != "posix", reason="POSIX signals")
def test_cancel_end_to_end_stops_marks_and_resume_is_refused(qapp: Any, page: Any,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """Through the fake CLI (the core's ``jobs``): Cancel stops the job (exit 130), its mark is written, the badge says
    Cancelled, Resume is disabled, and ``agentprov jobs resume`` refuses it (exit 4)."""
    import agentprov_gui.ui.runs as runs_mod

    job = page.start(JobSpec("import", ("import", "--units", "200", "--sleep", "0.05"), "R1", "long"))
    assert job is not None
    wait(qapp, lambda: (job.directory / "progress.jsonl").is_file(), 30)
    monkeypatch.setattr(runs_mod, "ask", lambda *a, **k: True)
    page.select(job.job_id)
    page.cancel()
    wait(qapp, lambda: page.manager.refresh() and page.manager.jobs[job.job_id].state != "running", 30)
    page.refresh()
    page.select(job.job_id)
    assert page.manager.jobs[job.job_id].exit_code == 130 and (job.directory / "abandoned.json").is_file()
    assert page.state_badge.text() == "Cancelled" and not page.resume_btn.isEnabled()
    code, _out, err = page.manager.call(["jobs", "resume", job.job_id])
    assert code == 4 and b"jobs.resume.cancelled" in err
    assert len(page.manager.refresh()) == 1  # nothing was started


def test_a_closed_run_live_dialog_is_deleted(qapp: Any, page: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """AU-NG-2: Runs deletes the Run Live dialog once it is closed, so no hidden dialog keeps working."""
    from PySide6.QtCore import QCoreApplication, QEvent

    from agentprov_gui.ui.runlive import RunLiveDialog

    monkeypatch.setattr(RunLiveDialog, "exec", lambda self: (self.reject(), 0)[1])
    assert page.run_live() is None
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert page.findChildren(RunLiveDialog) == []


def test_cancel_and_force_kill_take_the_destructive_style(page: Any) -> None:
    """They end the job for good (Cancel marks it never to be resumed; Force Kill skips the clean-up): red, the words
    still saying what they do; Pause, Resume and Stop stay plain."""
    assert page.cancel_btn.property("apvRole") == "destructive" and page.kill_btn.property("apvRole") == "destructive"
    for b in (page.drain_btn, page.resume_btn, page.stop_btn):
        assert (b.property("apvRole") or "") == ""
