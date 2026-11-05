"""G5 note P-2, P-3: the job manager's Windows paths, taken on any host by patching :func:`on_windows`.

Windows has no SIGTERM, so every ``agentprov`` job gets a control file (the graceful stop); a supervisor whose parent's
job object forbids breakaway starts without it and says so; a kill terminates the process tree through psutil and never
calls ``killpg``; the machine-wide job queue (``fcntl``) is refused with a clear reason. No process is started here.
"""

from __future__ import annotations

import io
import json
import types
from pathlib import Path
from typing import Any

import pytest

from agentprov.jobs import manager as mod
from agentprov.jobs.manager import JobManager, JobRequest, SpawnRefused


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "on_windows", lambda: True)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = tmp_path / "checkout"
    (r / "tools").mkdir(parents=True)
    (r / "tools" / "suite_queue.py").write_text("")
    return r


def test_the_queue_is_available_on_posix_with_the_tool_only(root: Path, tmp_path: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "on_windows", lambda: False)
    assert mod.queue_available(root) and not mod.queue_available(tmp_path) and not mod.queue_available(None)
    monkeypatch.setattr(mod, "on_windows", lambda: True)
    assert not mod.queue_available(root)


def test_queue_cpu_is_refused_on_windows(windows: None, root: Path, tmp_path: Path) -> None:
    manager = JobManager(tmp_path / "home", environ={}, root=root)
    with pytest.raises(SpawnRefused) as exc:
        manager.spawn(JobRequest(("info",), queue_cpu=2))
    assert exc.value.code == "platform.unsupported" and exc.value.exit_code == 4  # D-1064: the platform table's refusal
    assert str(exc.value).startswith("The machine-wide job queue (--queue-cpu, tools/suite_queue.py) is available on "
                                     "macOS and Linux. On Windows it is not available: ")
    assert not any(manager.jobs_dir.iterdir())  # nothing left behind


def test_queue_cpu_is_refused_when_the_platform_table_sees_windows(root: Path, tmp_path: Path,
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """D-1064: the refusal follows ``agentprov.platforms`` too (``platform.system``), not only :func:`on_windows`."""
    monkeypatch.setattr(mod, "on_windows", lambda: False)
    monkeypatch.setattr("agentprov.platforms.host", lambda: ("Windows", "arm64"))
    manager = JobManager(tmp_path / "home", environ={}, root=root)
    with pytest.raises(SpawnRefused) as exc:
        manager.spawn(JobRequest(("info",), queue_cpu=2))
    assert exc.value.code == "platform.unsupported"
    monkeypatch.setattr("agentprov.platforms.host", lambda: ("Linux", "x86_64"))
    mod.check_queue_platform()  # macOS and Linux: not refused


def test_a_batch_step_refused_for_the_platform_fails_at_once(windows: None, root: Path, tmp_path: Path) -> None:
    """A step whose ``queue_cpu`` cannot run here fails with the refusal's code instead of being retried each tick."""
    from agentprov.jobs.batch import Batch, BatchStep, advance

    manager = JobManager(tmp_path / "home", environ={}, root=root)
    batch = Batch.new(manager.home, "b", [BatchStep(JobRequest(("info",), queue_cpu=2))])
    advance(batch, manager, validate=lambda argv: None, pin_now=lambda: None, driver_job_id=None)
    assert (batch.steps[0].state, batch.steps[0].note) == ("failed", "platform.unsupported")


def test_prune_keeps_the_record_of_a_job_with_a_file_held_open(tmp_path: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """AU-RT-4: Windows refuses to delete a file another process holds open (the GUI's log tail); simulated with an
    ``os.unlink`` that refuses ``log.jsonl``. The job keeps its job.json, is not counted, and a later prune deletes it."""
    import os

    from agentprov.jobs.record import JOB_FORMAT, list_jobs

    manager = JobManager(tmp_path / "home", environ={}, root=None)
    job_id = mod.new_job_id()
    directory = manager.jobs_dir / job_id
    directory.mkdir(parents=True)
    mod.atomic_write_json(directory / "job.json", {"format": JOB_FORMAT, "job_id": job_id,
                                                   "created": "2026-01-01T00:00:00Z", "argv": ["x"]})
    mod.atomic_write_json(directory / "ended.json", {"exit_code": 0, "outcome": "ok", "how": "waited",
                                                     "observed": "2026-01-01T00:00:00Z"})
    (directory / "log.jsonl").write_bytes(b"{}\n")
    real = os.unlink

    def unlink(path: Any, *, dir_fd: Any = None) -> None:
        if os.fsdecode(path).endswith("log.jsonl"):
            raise PermissionError(32, "The process cannot access the file", os.fsdecode(path))
        real(path, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", unlink)
    assert manager.delete(manager.prune_candidates(keep=0)) == 0
    assert (directory / "job.json").exists() and [j.job_id for j in list_jobs(manager.home)] == [job_id]
    monkeypatch.setattr(os, "unlink", real)
    assert manager.delete(manager.prune_candidates(keep=0)) == 1 and not directory.exists()


class _Proc:
    def poll(self) -> int:
        return 0


def test_every_agentprov_job_gets_a_control_file_on_windows(windows: None, root: Path, tmp_path: Path,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(JobManager, "_start_supervisor", staticmethod(lambda directory, env, err: _Proc()))
    manager = JobManager(tmp_path / "home", environ={}, root=root)
    job = manager.spawn(JobRequest(("info",)), wait_s=0.1)
    record = json.loads((job.directory / "job.json").read_text())
    assert record["control_file"] is True and "--control-file" in record["argv"]
    (root / "tools" / "t.py").write_text("")
    tool = manager.spawn(JobRequest(("x",), tool="tools/t.py"), wait_s=0.1)  # a tool has no --control-file
    assert json.loads((tool.directory / "job.json").read_text())["control_file"] is False


def test_a_forbidden_breakaway_starts_without_it_and_says_so(windows: None, tmp_path: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def popen(argv: list[str], **kw: Any) -> _Proc:
        flags = kw["creationflags"]
        calls.append(flags)
        assert "start_new_session" not in kw
        if flags & mod._CREATE_BREAKAWAY_FROM_JOB:
            raise PermissionError(5, "Access is denied")
        return _Proc()

    monkeypatch.setattr(mod.subprocess, "Popen", popen)
    err = io.BytesIO()
    JobManager._start_supervisor(tmp_path, {}, err)
    detached = mod._DETACHED_PROCESS | mod._CREATE_NEW_PROCESS_GROUP
    assert calls == [detached | mod._CREATE_BREAKAWAY_FROM_JOB, detached]
    assert b"without CREATE_BREAKAWAY_FROM_JOB" in err.getvalue()


def test_kill_on_windows_terminates_the_tree_without_killpg(windows: None, tmp_path: Path,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    import psutil

    killed: list[int] = []

    class Fake:
        def __init__(self, pid: int, kids: list[Fake] | None = None) -> None:
            self.pid, self.kids = pid, kids or []

        def children(self, recursive: bool = False) -> list[Fake]:
            return self.kids

        def kill(self) -> None:
            killed.append(self.pid)

    leader = Fake(100, [Fake(101), Fake(102)])
    monkeypatch.setattr(psutil, "Process", lambda pid: leader)
    monkeypatch.setattr(psutil, "wait_procs", lambda procs, timeout=None: ([], []))
    monkeypatch.setattr(mod, "same_supervisor", lambda job: True)
    monkeypatch.setattr(mod.os, "killpg", lambda *a: pytest.fail("killpg on Windows"), raising=False)
    job = types.SimpleNamespace(supervisor_pid=100, record={"supervisor_create_time": 1.0},
                                file=lambda name: tmp_path / name)
    assert JobManager(tmp_path / "home", environ={}).kill(job)  # type: ignore[arg-type]
    assert killed == [100, 101, 102]
    assert json.loads((tmp_path / "ended.json").read_text())["how"] == "killed"


def test_stop_without_a_control_file_is_not_a_signal_on_windows(windows: None, tmp_path: Path,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod.os, "kill", lambda *a: pytest.fail("os.kill on Windows is TerminateProcess"))
    manager = JobManager(tmp_path / "home", environ={})
    monkeypatch.setattr(manager, "request", lambda job, what: False)
    job = types.SimpleNamespace(pid=7, record={"pid_create_time": 1.0})
    assert manager.stop(job) is False  # type: ignore[arg-type]


def test_a_record_write_retries_while_a_reader_holds_the_file_on_windows(windows: None, tmp_path: Path,
                                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """G5 clean-machine run (Windows x64): ``os.replace`` onto ``job.json`` failed with WinError 5 while the manager
    read it, and the supervisor crashed. The write is retried; a reader holds the file only briefly."""
    from agentprov.io import atomic

    real, calls = atomic.atomic_write_bytes, []

    def busy_twice(path: Path, data: bytes, **kw: Any) -> None:
        calls.append(path)
        if len(calls) <= 2:
            raise PermissionError(5, "Access is denied")
        real(path, data, **kw)

    monkeypatch.setattr(atomic, "atomic_write_bytes", busy_twice)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    mod.atomic_write_json(tmp_path / "job.json", {"state": "running"})
    assert len(calls) == 3 and json.loads((tmp_path / "job.json").read_text()) == {"state": "running"}


def test_a_record_write_gives_up_after_its_retries_and_never_retries_off_windows(tmp_path: Path,
                                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov.io import atomic

    calls: list[Path] = []

    def always_busy(path: Path, data: bytes, **kw: Any) -> None:
        calls.append(path)
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(atomic, "atomic_write_bytes", always_busy)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(mod, "on_windows", lambda: False)
    with pytest.raises(PermissionError):
        mod.atomic_write_json(tmp_path / "job.json", {})
    assert len(calls) == 1  # POSIX renames over an open file; a PermissionError there is real
    calls.clear()
    monkeypatch.setattr(mod, "on_windows", lambda: True)
    with pytest.raises(PermissionError):
        mod.atomic_write_json(tmp_path / "job.json", {})
    assert len(calls) == mod._REPLACE_RETRIES


def test_settings_and_price_writes_retry_while_a_reader_holds_the_file_on_windows(tmp_path: Path,
                                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """Review UC-30: the settings and price-override writes had no retry of the Windows rename race that job.json's
    write retries (``agentprov.io.atomic`` itself is in the aer stage scope and unchanged)."""
    from agentprov import settings
    from agentprov.estimate import prices
    from agentprov.io import atomic, replace_retry

    real, calls = atomic.atomic_write_bytes, []

    def busy_twice(path: Path, data: bytes, **kw: Any) -> None:
        calls.append(path)
        if len(calls) % 3:
            raise PermissionError(5, "Access is denied")
        real(path, data, **kw)

    monkeypatch.setattr(atomic, "atomic_write_bytes", busy_twice)
    monkeypatch.setattr(replace_retry, "_windows", lambda: True)
    monkeypatch.setattr(replace_retry.time, "sleep", lambda s: None)
    settings.set("jobs.retention", 70, home=tmp_path)
    assert settings.items("jobs.", home=tmp_path)["jobs.retention"] == 70 and len(calls) == 3
    prices.set_override(tmp_path, "openai", "gpt-4o", input="2.5", output="10")
    assert len(calls) == 6 and "openai:gpt-4o" in prices.load_overrides(tmp_path)
