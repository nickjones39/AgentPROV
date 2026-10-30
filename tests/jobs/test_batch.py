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


def _wait_jobs(manager: JobManager, timeout: float = 60) -> None:
    from agentprov.jobs.record import list_jobs

    end = time.monotonic() + timeout
    while time.monotonic() < end and any(j.state == "running" for j in list_jobs(manager.home)):
        time.sleep(0.05)


def test_advance_runs_in_order_blocks_after_exit_4_and_holds_r2(tmp_path: Path) -> None:
    manager = JobManager(tmp_path / "home", environ={"PATH": os.environ["PATH"]})
    steps = [_step("info"), _step("validate", "--corpus", str(tmp_path / "missing")), _step("info"),
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


def _until_finished(cli: Callable[..., Run], bid: str, timeout: float = 90) -> dict[str, object]:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        doc = json.loads(cli("batch", "show", bid, "--format", "json").out)
        if all(s["state"] in ("done", "failed", "blocked", "skipped") for s in doc["steps"]) and not doc[
                "driver_running"]:
            return doc
        time.sleep(0.2)
    raise AssertionError("the batch did not finish")


def test_a_batch_runs_as_one_driver_job(cli: Callable[..., Run], tmp_path: Path) -> None:
    created = cli("batch", "create", _spec(tmp_path, [{"argv": ["info"]}, {"argv": ["info", "--format", "json"]}]),
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
