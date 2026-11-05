"""D-1061: ``agentprov jobs cancel ID`` stops a running job as ``jobs stop`` does and marks it cancelled
(``abandoned.json`` in its directory), so ``jobs resume`` refuses it (exit 4, ``jobs.resume.cancelled``); an ended job
is only marked; nothing is deleted. ``jobs stop`` is unchanged: a stopped job is not cancelled and still resumes. Real
child processes, a temporary home, no network."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from agentprov.cli.main import main
from agentprov.jobs.manager import JobManager, JobRequest, SpawnRefused
from agentprov.jobs.record import ABANDONED, ABANDONED_FORMAT, abandoned_mark, load_job

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX signals and sessions")

SLEEPER = '''import signal, sys, time
signal.signal(signal.SIGTERM, lambda *a: sys.exit(130))
print("started", flush=True)
time.sleep(float(sys.argv[-1]))  # argv: -C ROOT x y SECONDS
'''


@pytest.fixture
def manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JobManager:
    root = tmp_path / "checkout"
    (root / "tools").mkdir(parents=True)
    (root / "tools" / "sleeper.py").write_text(SLEEPER)
    environ = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "TMPDIR")}
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    return JobManager(tmp_path / "home", environ=environ, root=root)


def _wait(job_dir: Path, timeout: float = 30) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = load_job(job_dir)
        if job is not None and job.state != "running":
            return
        time.sleep(0.05)
    raise AssertionError("the job did not end")


def _settled_names(job_dir: Path, timeout: float = 30) -> list[str]:
    """The job folder's file names once the supervisor has finished writing: no atomic-write temporary left and two
    listings 0.2 s apart agree (under load the supervisor can still be rewriting job.json after the state is ended)."""
    end = time.monotonic() + timeout
    names = sorted(p.name for p in job_dir.iterdir())
    while time.monotonic() < end:
        time.sleep(0.2)
        again = sorted(p.name for p in job_dir.iterdir())
        if again == names and not any(".tmp-" in n for n in names):
            return names
        names = again
    raise AssertionError(f"the job folder did not settle: {names}")


def _sleeper(manager: JobManager) -> Path:
    job = manager.spawn(JobRequest(("x", "y", "60"), tool="tools/sleeper.py", label="sleeper"))
    end = time.monotonic() + 20
    while time.monotonic() < end and b"started" not in (job.directory / "stdout.txt").read_bytes():
        time.sleep(0.05)
    return job.directory


def _cli(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    capsys.readouterr()
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def test_cancel_stops_a_running_job_and_resume_refuses_it(manager: JobManager,
                                                          capsys: pytest.CaptureFixture[str]) -> None:
    directory = _sleeper(manager)
    code, _out, err = _cli(capsys, "jobs", "cancel", directory.name)
    assert code == 0 and "cancelled" in err and "stop sent" in err
    _wait(directory)
    job = load_job(directory)
    assert job is not None and job.exit_code == 130 and job.abandoned  # the graceful stop: exit 130, as jobs stop
    mark = json.loads((directory / ABANDONED).read_text())
    assert mark["format"] == ABANDONED_FORMAT and mark["job_id"] == directory.name and mark["state"] == "running"
    code, _out, err = _cli(capsys, "jobs", "resume", directory.name)
    assert code == 4 and "[jobs.resume.cancelled]" in err and "cancelled" in err
    with pytest.raises(SpawnRefused) as refused:
        manager.resume(job)
    assert refused.value.code == "jobs.resume.cancelled"
    assert [j.name for j in manager.jobs_dir.iterdir()] == [directory.name]  # no new job was started
    code, out, _err = _cli(capsys, "jobs", "list", "--format", "json")
    assert code == 0 and json.loads(out)["jobs"][0]["abandoned"] is True
    code, out, err = _cli(capsys, "jobs", "list")
    assert f"{directory.name}  ended exit 130 cancelled  " in out + err


def test_cancel_of_an_ended_job_only_marks_it_and_a_second_cancel_keeps_the_mark(
        manager: JobManager, capsys: pytest.CaptureFixture[str]) -> None:
    directory = _sleeper(manager)
    assert manager.stop(load_job(directory))  # type: ignore[arg-type]
    _wait(directory)
    files = _settled_names(directory)
    code, _out, err = _cli(capsys, "jobs", "cancel", directory.name[:12])
    assert code == 0 and "is now cancelled" in err and "stop sent" not in err
    first = (directory / ABANDONED).read_bytes()
    assert json.loads(first)["state"] == "ended"
    assert _settled_names(directory) == sorted([*files, ABANDONED])  # nothing else changed
    code, _out, err = _cli(capsys, "jobs", "cancel", directory.name)
    assert code == 0 and "was already cancelled" in err and (directory / ABANDONED).read_bytes() == first


def test_stop_is_unchanged_a_stopped_job_is_not_cancelled_and_resumes(manager: JobManager,
                                                                      capsys: pytest.CaptureFixture[str]) -> None:
    directory = _sleeper(manager)
    code, _out, _err = _cli(capsys, "jobs", "stop", directory.name)
    assert code == 0
    _wait(directory)
    job = load_job(directory)
    assert job is not None and job.exit_code == 130 and not job.abandoned and abandoned_mark(directory) is None
    again = manager.resume(job)
    assert again.job_id != job.job_id and again.record["subcommand_argv"] == ["x", "y", "60"]
    manager.kill(again)
    _wait(again.directory)


TEARDOWN = '''import sys, time
from pathlib import Path
from agentprov.cli.common import install_signal_handlers
with install_signal_handlers():
    try:
        print("started", flush=True)
        time.sleep(60)
    except KeyboardInterrupt:
        time.sleep(1.5)  # the clean interrupt path: seal aborted sessions, flush, release the lock
        Path(sys.argv[-1]).write_text("done")  # argv: -C ROOT MARKER
        raise SystemExit(130)
'''


def test_cancel_after_stop_only_marks_so_the_teardown_finishes(manager: JobManager, tmp_path: Path,
                                                                capsys: pytest.CaptureFixture[str]) -> None:
    """AU-NC-101: a second SIGTERM is the CLI's hard abort (``os._exit(130)``), so a cancel sent while ``jobs stop``'s
    teardown runs must not signal again: the job is marked, and its teardown finishes."""
    assert manager.root is not None
    (manager.root / "tools" / "teardown.py").write_text(TEARDOWN)
    marker = tmp_path / "teardown.txt"
    job = manager.spawn(JobRequest((str(marker),), tool="tools/teardown.py", label="teardown"))
    directory = job.directory
    end = time.monotonic() + 20
    while time.monotonic() < end and b"started" not in (directory / "stdout.txt").read_bytes():
        time.sleep(0.05)
    code, _out, _err = _cli(capsys, "jobs", "stop", directory.name)
    assert code == 0
    time.sleep(0.3)
    code, _out, err = _cli(capsys, "jobs", "cancel", directory.name)
    assert code == 0 and "is now cancelled" in err
    _wait(directory)
    ended = load_job(directory)
    assert ended is not None and ended.exit_code == 130 and ended.abandoned
    assert marker.read_text() == "done"  # the teardown was not cut short


def test_a_damaged_mark_still_cancels(manager: JobManager) -> None:
    directory = _sleeper(manager)
    manager.kill(load_job(directory))  # type: ignore[arg-type]
    _wait(directory)
    (directory / ABANDONED).write_bytes(b"not json")
    job = load_job(directory)
    assert job is not None and job.abandoned and abandoned_mark(directory) == {}
    with pytest.raises(SpawnRefused):
        manager.resume(job)


def test_cancel_of_an_unknown_job_is_a_usage_error(manager: JobManager, capsys: pytest.CaptureFixture[str]) -> None:
    code, _out, err = _cli(capsys, "jobs", "cancel", "0000000000")
    assert code == 2 and "no job" in err
