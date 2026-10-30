"""GR-49: the stale-lock notice uses the core's own staleness rule (``agentprov.io.atomic``: a well-formed lock record,
the same host, a pid no live process has), so it never suggests a ``--break-stale-lock`` job the core would refuse.

``agentprov.io`` is not allowlisted, so the rule is restated in the GUI; these cases pin where the two once disagreed.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

from agentprov_gui.jobs.manager import CliLocator, JobManager, atomic_write_json

FAKE = Path(__file__).parent / "fake" / "fake_cli.py"


def _dead_pid() -> int:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def _job_with_lock(tmp_path: Path, job_pid: int, lock: dict[str, object]) -> tuple[JobManager, Path, Path]:
    """An unobserved job (its pid's create time does not match) whose one write target holds ``lock``."""
    home = tmp_path / "home"
    corpus = tmp_path / "corpora" / "c"
    corpus.with_name("c.partial").mkdir(parents=True)
    d = home / "jobs" / "019a0000-0000-7000-8000-000000000049"  # D-704: $AGENTPROV_HOME/jobs
    d.mkdir(parents=True)
    atomic_write_json(d / "job.json", {"format": "agentprov-job-record/0.1", "job_id": d.name, "pid": job_pid,
                                       "pid_create_time": 1.0, "created": "2026-10-15T10:00:00Z", "argv": [],
                                       "command": "import", "writes": [str(corpus)]})
    path = corpus.with_name("c.partial") / ".agentprov.lock"
    path.write_text(json.dumps(lock))
    return JobManager(home, CliLocator(None, (sys.executable, str(FAKE)))), corpus, path


def _lock(pid: int, **over: object) -> dict[str, object]:
    record: dict[str, object] = {"pid": pid, "host": platform.node(), "command": "import",
                                 "started": "2026-10-15T10:00:05Z"}
    record.update(over)
    return {k: v for k, v in record.items() if v is not None}


def test_a_live_holder_reusing_the_job_pid_is_not_stale(tmp_path: Path) -> None:
    me = os.getpid()  # alive, and job.json names it with another create time: the job's pid was reused
    m, _corpus, lock = _job_with_lock(tmp_path, me, _lock(me))
    job = m.load_all()[0]
    assert job.state == "unobserved" and job.stale_lock is None
    assert lock.exists()


@pytest.mark.parametrize("over", [
    {"host": platform.node() + "-elsewhere"},  # another host cannot be checked
    {"host": None},                            # not a lock record the core can read
    {"command": None},
    {"started": None},
    {"started": 5},
    {"host": 7},
])
def test_the_job_pid_branch_needs_a_breakable_lock(tmp_path: Path, over: dict[str, object]) -> None:
    pid = _dead_pid()
    m, _corpus, lock = _job_with_lock(tmp_path, pid, _lock(pid, **over))
    job = m.load_all()[0]
    assert job.state == "unobserved" and job.stale_lock is None
    assert lock.exists()


def test_a_dead_holder_with_the_job_pid_is_still_reported(tmp_path: Path) -> None:
    pid = _dead_pid()  # any started time: the lock names the job's own pid
    m, corpus, lock = _job_with_lock(tmp_path, pid, _lock(pid, started="2026-10-15T09:00:00Z"))
    job = m.load_all()[0]
    assert job.state == "unobserved" and job.stale_lock == str(corpus)
    assert lock.exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX zombies")
def test_a_zombie_holder_is_alive_to_the_core(tmp_path: Path) -> None:
    """``os.kill(pid, 0)`` succeeds on an unreaped child, so the core's ``pid_alive`` says alive and refuses a break."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    try:
        end = time.monotonic() + 20
        while psutil.Process(child.pid).status() != psutil.STATUS_ZOMBIE:
            assert time.monotonic() < end
            time.sleep(0.02)
        m, _corpus, lock = _job_with_lock(tmp_path, _dead_pid(), _lock(child.pid))
        job = m.load_all()[0]
        assert job.state == "unobserved" and job.stale_lock is None
        assert lock.exists()
    finally:
        child.wait()
