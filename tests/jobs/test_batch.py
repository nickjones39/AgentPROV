"""D-704: batches (``agentprov.jobs.batch`` and ``agentprov batch``): a batch runs as one driver job; steps are
checked again before they start (attacks: an unknown, recursive or destructive step, a tampered batch file, a raised
tier); R2 steps need ``--confirm-r2``; a changed checkout blocks the rest; blocking exits; the dev-run fallback."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest

from agentprov.cli.batch import validate_argv
from agentprov.cli.main import main
from agentprov.jobs.batch import Batch, BatchStep, advance, check_step, first_n_argv, sample_unsupported
from agentprov.jobs.manager import JobManager, JobRequest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX signals and sessions")


class Run(NamedTuple):
    code: int
    out: str
    err: str


#: A job that ends at once. ``info`` probes the host (about 1 s idle, tens of seconds at load ~50, 2026-11-05),
#: which none of these tests checks; ``settings list`` is an R0 read of the job's own home (0.2 s).
QUICK = ("settings", "list")
#: How long a test waits for a detached job to change state: polled, so a passing run never waits it out; long
#: enough for a supervisor and its child to start and end on a loaded machine (2026-11-05: 30 s failed at
#: load ~50).
JOB_WAIT_S = 180.0


def _step(*argv: str, **kw: object) -> BatchStep:
    step = BatchStep(JobRequest(tuple(argv), **kw))  # type: ignore[arg-type]
    step.recorded_tier = step.request.tier
    return step


@pytest.mark.parametrize(("argv", "why"), [
    (("nosuchcommand",), "not run:"), (("info", "--no-such-option"), "not run:"),
    (("jobs", "start", "--", "info"), "never starts jobs"), (("batch", "run", "x"), "never starts jobs"),
    (("purge", "sha256:" + "0" * 64, "--reason", "x", "--yes"), "irreversible"), (("--help",), "not run:"),
])
def test_unknown_recursive_and_destructive_steps_are_blocked(argv: tuple[str, ...], why: str) -> None:
    reason = check_step(_step(*argv), validate_argv)
    assert reason is not None and why in reason


def test_a_step_whose_argv_now_needs_r2_is_blocked() -> None:
    step = _step("import", "agentdojo", "--corpus", "/c")
    step.request = JobRequest(("import", "agentdojo", "--corpus", "/c", "--fetch", "--allow-network"))
    assert "higher tier" in (check_step(step, validate_argv) or "")
    assert check_step(_step("info"), validate_argv) is None


def test_the_dev_run_fallback_helpers() -> None:
    argv = ("import", "x", "--sample", "5", "--sample-mode", "spread", "--seed", "7")
    assert first_n_argv(argv) == ("import", "x", "--sample", "5", "--sample-mode", "first")
    assert sample_unsupported(5, {"refusal": {"code": "import.sample.unsupported"}})
    assert not sample_unsupported(1, {"refusal": {"code": "import.sample.unsupported"}})


def _wait_jobs(manager: JobManager, timeout: float = JOB_WAIT_S) -> None:
    from agentprov.jobs.record import list_jobs

    end = time.monotonic() + timeout
    while time.monotonic() < end and any(j.state == "running" for j in list_jobs(manager.home)):
        time.sleep(0.05)


def test_advance_runs_in_order_blocks_after_exit_4_and_holds_r2(tmp_path: Path) -> None:
    manager = JobManager(tmp_path / "home", environ={"PATH": os.environ["PATH"]})
    steps = [_step(*QUICK), _step("validate", "--corpus", str(tmp_path / "missing")), _step(*QUICK),
             _step("fetch", "--corpus", "/c", "--allow-network")]
    batch = Batch.new(manager.home, "t", steps, pin={"commit": "a"})
    pin = {"commit": "a"}

    def tick() -> None:
        advance(batch, manager, validate=validate_argv, pin_now=lambda: pin, driver_job_id="driver-1")
        _wait_jobs(manager)

    for _ in range(6):
        tick()
    states = [s.state for s in batch.steps]
    assert states[0] == "done" and states[1] == "failed" and batch.steps[1].exit_code not in (None, 0)
    if batch.steps[1].exit_code in (4, 70):
        assert states[2:] == ["blocked", "blocked"]
    else:
        assert states[2] == "done" and states[3] == "held"  # R2 under a driver that did not confirm


def test_a_changed_checkout_blocks_every_remaining_step(tmp_path: Path) -> None:
    manager = JobManager(tmp_path / "home", environ={"PATH": os.environ["PATH"]})
    batch = Batch.new(manager.home, "t", [_step("info"), _step("info")], pin={"commit": "a"})
    advance(batch, manager, validate=validate_argv, pin_now=lambda: {"commit": "b"}, driver_job_id=None)
    assert [s.state for s in batch.steps] == ["blocked", "blocked"] and "checkout changed" in batch.steps[0].note


# ---------------------------------------------------------------------------------------------- the CLI
@pytest.fixture
def cli(capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., Run]:
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))

    def run(*argv: str, stdin: bytes | None = None) -> Run:
        import io
        import sys

        capsys.readouterr()
        if stdin is not None:
            monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(stdin)))
        code = main([*argv[:2], "--progress", "off", *argv[2:]])
        out, err = capsys.readouterr()
        return Run(code, out, err)

    return run


def _spec(tmp_path: Path, steps: list[dict[str, object]]) -> str:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps({"steps": steps}))
    return str(path)


def _until_finished(cli: Callable[..., Run], bid: str, timeout: float = 2 * JOB_WAIT_S) -> dict[str, object]:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        doc = json.loads(cli("batch", "show", bid, "--format", "json").out)
        if all(s["state"] in ("done", "failed", "blocked", "skipped") for s in doc["steps"]) and not doc[
                "driver_running"]:
            return doc
        time.sleep(0.2)
    raise AssertionError("the batch did not finish")


def test_a_batch_runs_as_one_driver_job(cli: Callable[..., Run], tmp_path: Path) -> None:
    created = cli("batch", "create", _spec(tmp_path, [{"argv": [*QUICK]}, {"argv": [*QUICK, "--format", "json"]}]),
                  "--label", "two", "--format", "json")
    assert created.code == 0, created.err
    bid = json.loads(created.out)["batch_id"]
    started = json.loads(cli("batch", "start", bid, "--format", "json").out)
    doc = _until_finished(cli, bid)
    assert [s["state"] for s in doc["steps"]] == ["done", "done"] and doc["driver_job_id"] == started["driver_job_id"]
    jobs = json.loads(main_json(cli, "jobs", "list", "--format", "json"))["jobs"]
    driver = next(j for j in jobs if j["job_id"] == started["driver_job_id"])
    assert driver["subcommand_argv"] == ["batch", "run", bid] and driver["exit_code"] == 0
    assert {j["batch_id"] for j in jobs if j["job_id"] != driver["job_id"]} == {bid}


def main_json(cli: Callable[..., Run], *argv: str) -> str:
    return cli(*argv).out


@pytest.mark.parametrize("step", [
    {"argv": ["purge", "sha256:" + "0" * 64, "--reason", "x", "--yes"]}, {"argv": ["jobs", "list"]},
    {"argv": ["nosuchcommand"]}, {"argv": []}, {"argv": "info"}, {"argv": ["info"], "queue_cpu": 0},
    {"argv": ["info"], "slot": "anything"},
])
def test_create_refuses_bad_steps(cli: Callable[..., Run], tmp_path: Path, step: dict[str, object]) -> None:
    run = cli("batch", "create", _spec(tmp_path, [step]))
    assert run.code == 2 and "refused" in run.err


def test_r2_needs_confirmation_and_a_tampered_file_is_checked_again(cli: Callable[..., Run], tmp_path: Path) -> None:
    r2 = cli("batch", "create", _spec(tmp_path, [{"argv": ["fetch", "--corpus", str(tmp_path / "c"),
                                                           "--allow-network"]}]), "--format", "json")
    bid = json.loads(r2.out)["batch_id"]
    assert cli("batch", "start", bid).code == 4  # R2 without --confirm-r2
    ok = cli("batch", "create", _spec(tmp_path, [{"argv": ["info"]}]), "--format", "json")
    oid = json.loads(ok.out)["batch_id"]
    path = tmp_path / "home" / "batches" / f"{oid}.json"
    doc = json.loads(path.read_text())
    doc["steps"][0]["argv"] = ["purge", "sha256:" + "0" * 64, "--reason", "x", "--yes"]  # edited after create
    path.write_text(json.dumps(doc))
    cli("batch", "start", oid)
    done = _until_finished(cli, oid)
    assert done["steps"][0]["state"] == "blocked" and "irreversible" in done["steps"][0]["note"]


def test_create_from_stdin_and_list(cli: Callable[..., Run]) -> None:
    run = cli("batch", "create", "--stdin", "--format", "json",
              stdin=json.dumps({"steps": [{"argv": ["info"]}]}).encode())
    assert run.code == 0, run.err
    listed = json.loads(cli("batch", "list", "--format", "json").out)
    assert listed["format"] == "agentprov-batches-list/0.1" and len(listed["batches"]) == 1
    assert cli("batch", "show", "../../etc").code == 2


def test_r2_is_held_under_a_driver_that_did_not_confirm_and_runs_under_one_that_did(tmp_path: Path) -> None:
    manager = JobManager(tmp_path / "home", environ={"PATH": os.environ["PATH"]})
    batch = Batch.new(manager.home, "t", [_step("fetch", "--corpus", str(tmp_path / "c"), "--allow-network")])
    batch.r2_confirmed_by = "driver-a"
    assert advance(batch, manager, validate=validate_argv, pin_now=lambda: None, driver_job_id="driver-b") == []
    assert batch.steps[0].state == "held" and "--confirm-r2" in batch.steps[0].note
    assert advance(batch, manager, validate=validate_argv, pin_now=lambda: None, driver_job_id=None) == []
    started = advance(batch, manager, validate=validate_argv, pin_now=lambda: None, driver_job_id="driver-a")
    assert len(started) == 1 and batch.steps[0].state == "running"
    _wait_jobs(manager)


def test_the_dev_run_fallback_inserts_a_first_n_import_or_skips_the_part(tmp_path: Path) -> None:
    from agentprov.jobs.batch import FALLBACK_NOTE, SKIPPED_NOTE, _devrun_followup

    spread = ("import", "x", "--corpus", "/c", "--sample", "5", "--sample-mode", "spread", "--seed", "1")
    steps = [_step(*spread, extra={"part": "p1"}), _step("validate", "--corpus", "/c", extra={"part": "p1"}),
             _step("validate", "--corpus", "/d", extra={"part": "p2"})]
    batch = Batch("b", "t", steps, path=tmp_path / "b.json")
    steps[0].state, steps[0].exit_code = "failed", 5
    _devrun_followup(batch, 0, {"refusal": {"code": "import.sample.unsupported"}})
    assert batch.steps[1].request.argv == first_n_argv(spread) and batch.steps[1].note == FALLBACK_NOTE
    other = Batch("b2", "t", [_step("import", "x", extra={"part": "p1"}), _step("validate", extra={"part": "p1"}),
                              _step("validate", extra={"part": "p2"})], path=tmp_path / "b2.json")
    other.steps[0].state, other.steps[0].exit_code = "failed", 1
    _devrun_followup(other, 0, {})
    assert [s.state for s in other.steps[1:]] == ["skipped", "pending"] and other.steps[1].note == SKIPPED_NOTE


def test_the_checkout_pin_follows_commits_and_uncommitted_edits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch
                                                                ) -> None:
    """GR-70 with a real git checkout: a new commit or an uncommitted edit changes the pin."""
    import subprocess

    from agentprov.cli import batch as batch_cmd
    from agentprov.jobs import manager as manager_mod

    repo = tmp_path / "checkout"
    repo.mkdir()

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args], check=True,
                       capture_output=True)

    git("init", "-q")
    (repo / "a.txt").write_text("one")
    git("add", "a.txt")
    git("commit", "-q", "-m", "one")
    monkeypatch.setattr(manager_mod, "checkout_root", lambda: repo)
    first = batch_cmd.checkout_pin()
    assert first is not None and first["checkout"] == str(repo) and len(first["commit"]) == 40
    (repo / "a.txt").write_text("two")  # uncommitted
    edited = batch_cmd.checkout_pin()
    assert edited is not None and edited != first and edited["commit"] == first["commit"]
    git("commit", "-q", "-am", "two")
    assert batch_cmd.checkout_pin() not in (first, edited)


@pytest.mark.parametrize(("stored", "flag", "expected"), [
    (None, (), False), (True, (), True), (False, (), False),
    (True, ("--no-continue-on-failure",), False), (False, ("--continue-on-failure",), True),
])
def test_create_follows_the_continue_on_failure_setting(cli: Callable[..., Run], tmp_path: Path, stored: bool | None,
                                                        flag: tuple[str, ...], expected: bool) -> None:
    """D-700: without a flag, ``batch create`` follows ``jobs.continue_on_failure`` (Settings › Jobs)."""
    from agentprov import settings

    if stored is not None:
        settings.set("jobs.continue_on_failure", stored, home=tmp_path / "home")
    run = cli("batch", "create", _spec(tmp_path, [{"argv": ["info"]}]), *flag, "--format", "json")
    assert run.code == 0, run.err
    assert json.loads(run.out)["continue_on_failure"] is expected


def test_create_refuses_a_corrupt_settings_file(cli: Callable[..., Run], tmp_path: Path) -> None:
    (tmp_path / "home").mkdir(exist_ok=True)
    (tmp_path / "home" / "settings.json").write_text("not json")
    run = cli("batch", "create", _spec(tmp_path, [{"argv": ["info"]}]))
    assert run.code == 2 and "settings" in run.err
    assert cli("batch", "create", _spec(tmp_path, [{"argv": ["info"]}]), "--continue-on-failure").code == 0


def test_create_resolves_relative_step_paths_against_the_callers_cwd(cli: Callable[..., Run], tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """F-14 (D-704): a step runs in its own job folder, so batch create records its relative paths absolute."""
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    run = cli("batch", "create", "--stdin", "--format", "json", stdin=json.dumps({"steps": [
        {"argv": ["validate", "--corpus", "corpora/mini"], "writes": ["out"], "reads": ["corpora/mini"]}]}).encode())
    assert run.code == 0, run.err
    step = json.loads(run.out)["steps"][0]
    assert step["argv"] == ["validate", "--corpus", str(work / "corpora" / "mini")]
    assert step["writes"] == [str(work / "out")] and step["reads"] == [str(work / "corpora" / "mini")]


def test_a_running_step_whose_job_was_pruned_does_not_stay_running(tmp_path: Path) -> None:
    """Review UC-26: after ``batch stop`` and a prune of the step's job directory, the step held its slot forever and
    the batch never finished; it now fails with a fixed note."""
    from agentprov.jobs.batch import GONE_NOTE

    manager = JobManager(tmp_path / "home", environ={"PATH": os.environ["PATH"]})
    steps = [_step(*QUICK), _step(*QUICK)]
    batch = Batch.new(manager.home, "t", steps, pin={"commit": "a"})
    batch.steps[0].state, batch.steps[0].job_id = "running", "0190a0a0-0000-7000-8000-000000000000"  # no such job
    advance(batch, manager, validate=validate_argv, pin_now=lambda: {"commit": "a"}, driver_job_id="driver-1")
    assert (batch.steps[0].state, batch.steps[0].exit_code, batch.steps[0].note) == ("failed", None, GONE_NOTE)
    assert batch.steps[1].state == "running"  # the slot is free again
    _wait_jobs(manager)
    advance(batch, manager, validate=validate_argv, pin_now=lambda: {"commit": "a"}, driver_job_id="driver-1")
    assert batch.finished


def test_a_stopped_batch_s_pruned_running_step_does_not_keep_its_dev_run_busy(tmp_path: Path) -> None:
    """Review UC-26: with the driver stopped nothing advances the batch, so ``devrun prune`` must not read a running
    step whose job record is gone as a busy run."""
    from agentprov.cli.devrun import busy_runs

    manager = JobManager(tmp_path / "home", environ={"PATH": os.environ["PATH"]})
    run = manager.home / "dev-runs" / "20261101T000000Z"
    run.mkdir(parents=True)
    step = _step("info", extra={"devrun": run.name})
    step.state, step.job_id = "running", "0190a0a0-0000-7000-8000-000000000000"
    Batch.new(manager.home, "t", [step], pin={"commit": "a"}).save()
    assert run.resolve() not in busy_runs(manager.home)
    pending = _step("info", extra={"devrun": run.name})
    Batch.new(manager.home, "u", [pending], pin={"commit": "a"}).save()
    assert run.resolve() in busy_runs(manager.home)  # an unfinished step still holds it


# ---------------------------------------------------------------------------------------------- batch stop
SLEEPER = '''import signal, sys, time
signal.signal(signal.SIGTERM, lambda *a: sys.exit(130))
print("started", flush=True)
time.sleep(float(sys.argv[-1]))  # argv: -C ROOT x y SECONDS
'''


def _running_batch(tmp_path: Path) -> tuple[JobManager, Batch, str, str]:
    """A batch whose first step is a running job (a sleeper the step's job id names), whose second waits, and whose
    driver job runs: the driver cannot start the second step until the first ends."""
    from agentprov.jobs.manager import new_job_id

    root = tmp_path / "checkout"
    (root / "tools").mkdir(parents=True)
    (root / "tools" / "sleeper.py").write_text(SLEEPER)
    environ = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "TMPDIR")}
    manager = JobManager(tmp_path / "home", environ=environ, root=root)
    batch = Batch.new(manager.home, "t", [_step(*QUICK), _step(*QUICK), _step(*QUICK, label="next")])
    sleeper = manager.spawn(JobRequest(("x", "y", "60"), tool="tools/sleeper.py", batch_id=batch.batch_id))
    end = time.monotonic() + JOB_WAIT_S
    while time.monotonic() < end and b"started" not in sleeper.file("stdout.txt").read_bytes():
        time.sleep(0.05)
    # the first step's job is gone, so the driver's first tick fails it and saves: then the driver is past its start
    batch.steps[0].state, batch.steps[0].job_id = "running", "0190a0a0-0000-7000-8000-000000000000"
    batch.steps[1].state, batch.steps[1].job_id = "running", sleeper.job_id
    batch.driver_job_id = new_job_id()
    batch.save()
    driver = manager.spawn(JobRequest(("batch", "run", batch.batch_id, "--interval", "0.2"), label="driver"),
                           job_id=batch.driver_job_id)
    assert driver.state == "running" and batch.path is not None
    while time.monotonic() < end and (Batch.load(batch.path) or batch).steps[0].state == "running":
        time.sleep(0.05)
    return manager, batch, sleeper.job_id, driver.job_id


def _job_state(manager: JobManager, job_id: str) -> tuple[str, int | None]:
    from agentprov.jobs.manager import find

    job = find(manager.home, job_id)
    assert job is not None
    return job.state, job.exit_code


def test_batch_stop_steps_stops_the_driver_and_the_running_step_and_starts_nothing_more(
        cli: Callable[..., Run], tmp_path: Path) -> None:
    """The user's report (2026-11-05): a dev run could not be stopped. ``batch stop --steps`` stops the driver and every
    running step job, and no further step starts; ``batch resume`` goes on from the pending step."""
    from agentprov.jobs.batch import STOPPED_NOTE
    from agentprov.jobs.record import list_jobs

    manager, batch, sleeper, driver = _running_batch(tmp_path)
    run = cli("batch", "stop", batch.batch_id, "--steps", "--wait", "30", "--format", "json")
    assert run.code == 0, run.err
    doc = json.loads(run.out)
    assert doc["format"] == "agentprov-batch-stop/0.1" and doc["driver"] == "stopped"
    assert doc["steps_stopped"] == [sleeper] and doc["steps_unsignalled"] == [] and doc["still_running"] == []
    assert _job_state(manager, sleeper) == ("ended", 130) and _job_state(manager, driver) == ("ended", 130)
    time.sleep(1.0)  # several driver intervals: nothing may start the second step
    assert batch.path is not None
    stored = Batch.load(batch.path)
    assert stored is not None and stored.stopped is not None
    assert [(s.state, s.exit_code) for s in stored.steps] == [("failed", None), ("failed", 130), ("pending", None)]
    assert stored.steps[1].note == STOPPED_NOTE
    assert len(list_jobs(manager.home)) == 2  # the sleeper and the driver only
    resumed = cli("batch", "resume", batch.batch_id, "--format", "json")
    assert resumed.code == 0, resumed.err
    done = _until_finished(cli, batch.batch_id)
    assert [s["state"] for s in done["steps"]] == ["failed", "failed", "done"] and done["stopped"] is None


def test_batch_stop_without_steps_still_stops_only_the_driver(cli: Callable[..., Run], tmp_path: Path) -> None:
    """The default is unchanged (D-704): the driver stops and the step it started keeps running; the batch is marked
    stopped, so no driver tick starts the next step."""
    from agentprov.jobs.manager import find

    manager, batch, sleeper, driver = _running_batch(tmp_path)
    run = cli("batch", "stop", batch.batch_id, "--wait", "30", "--format", "json")
    assert run.code == 0, run.err
    doc = json.loads(run.out)
    assert doc["driver"] == "stopped" and doc["steps_stopped"] == []
    assert _job_state(manager, driver) == ("ended", 130) and _job_state(manager, sleeper)[0] == "running"
    job = find(manager.home, sleeper)
    assert job is not None and manager.stop(job)
    _wait_jobs(manager)
    again = cli("batch", "stop", batch.batch_id, "--wait", "0", "--format", "json")
    assert again.code == 0 and json.loads(again.out)["driver"] == "not running"


def test_batch_stop_steps_exits_1_when_a_step_job_cannot_be_signalled(
        cli: Callable[..., Run], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov.jobs.manager import find

    manager, batch, sleeper, driver = _running_batch(tmp_path)
    real_stop = JobManager.stop
    monkeypatch.setattr(JobManager, "stop", lambda self, job: job.job_id == driver and real_stop(self, job))
    run = cli("batch", "stop", batch.batch_id, "--steps", "--wait", "30", "--format", "json")
    assert run.code == 1
    doc = json.loads(run.out)
    assert doc["driver"] == "stopped" and doc["steps_unsignalled"] == [sleeper] and doc["steps_stopped"] == []
    assert "could not be signalled" in run.err
    monkeypatch.undo()
    job = find(manager.home, sleeper)
    assert job is not None and manager.stop(job)
    _wait_jobs(manager)


def test_a_stopped_batch_starts_no_step_but_records_ended_ones(tmp_path: Path) -> None:
    manager = JobManager(tmp_path / "home", environ={"PATH": os.environ["PATH"]})
    batch = Batch.new(manager.home, "t", [_step("info"), _step("info")])
    batch.steps[0].state, batch.steps[0].job_id = "running", "0190a0a0-0000-7000-8000-000000000000"  # no such job
    batch.stopped = "2026-11-05T00:00:00Z"
    assert advance(batch, manager, validate=validate_argv, pin_now=lambda: None, driver_job_id="d") == []
    assert [s.state for s in batch.steps] == ["failed", "pending"]
    assert batch.path is not None
    reloaded = Batch.load(batch.path)
    assert reloaded is not None and reloaded.stopped == "2026-11-05T00:00:00Z"
