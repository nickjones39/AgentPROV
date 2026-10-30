"""D-704: the core job manager (``agentprov.jobs``): supervised detached jobs, the writer and slot rules, stop, kill,
drain, resume and prune, the tier rules, and the ``--tool`` restriction (attacks: ``..``, absolute paths, symlinks,
files outside ``tools/``). Real child processes, a temporary home, no network."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from agentprov.jobs import tiers
from agentprov.jobs.manager import JobManager, JobRequest, SpawnRefused, resolve_tool
from agentprov.jobs.record import list_jobs, load_job

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX signals and sessions")

SLEEPER = '''import signal, sys, time
signal.signal(signal.SIGTERM, lambda *a: sys.exit(130))
print("started", flush=True)
time.sleep(float(sys.argv[-1]))  # argv: -C ROOT x y SECONDS
'''


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A fake checkout with one tool."""
    r = tmp_path / "checkout"
    (r / "tools").mkdir(parents=True)
    (r / "tools" / "sleeper.py").write_text(SLEEPER)
    return r


@pytest.fixture
def manager(tmp_path: Path, root: Path) -> JobManager:
    environ = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "TMPDIR")}
    environ["FAKE_PROVIDER_API_KEY"] = "sk-" + "never-passed-0123"
    return JobManager(tmp_path / "home", environ=environ, root=root)


def _wait(job_dir: Path, timeout: float = 30) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = load_job(job_dir)
        if job is not None and job.state != "running":
            return
        time.sleep(0.05)
    raise AssertionError("the job did not end")


def _wait_started(job_dir: Path) -> None:
    end = time.monotonic() + 20
    while time.monotonic() < end and b"started" not in (job_dir / "stdout.txt").read_bytes():
        time.sleep(0.05)


def test_a_supervised_job_records_its_real_exit_code_and_an_allowlisted_env(manager: JobManager) -> None:
    job = manager.spawn(JobRequest(("info", "--format", "json"), label="info"))
    assert job.pid is not None and job.supervisor_pid is not None
    _wait(job.directory)
    done = load_job(job.directory)
    assert done is not None and done.state == "ended" and done.exit_code == 0 and done.ended_how == "waited"
    record = json.loads((job.directory / "job.json").read_text())
    assert "FAKE_PROVIDER_API_KEY" not in record["env_names"] and "sk-never" not in json.dumps(record)
    assert record["argv"][1:4] == ["-I", "-m", "agentprov"] and "--summary-json" in record["argv"]
    assert oct(job.directory.stat().st_mode)[-3:] == "700"


def test_stop_is_one_sigterm_and_kill_takes_the_tree(manager: JobManager) -> None:
    job = manager.spawn(JobRequest(("x", "y", "60"), tool="tools/sleeper.py"))
    _wait_started(job.directory)
    assert manager.stop(job)
    _wait(job.directory)
    assert load_job(job.directory).exit_code == 130  # type: ignore[union-attr]
    other = manager.spawn(JobRequest(("x", "y", "60"), tool="tools/sleeper.py"))
    _wait_started(other.directory)
    assert manager.kill(other)
    _wait(other.directory)
    killed = load_job(other.directory)
    assert killed is not None and killed.outcome == "killed" and killed.state == "ended"
    assert not manager.stop(killed) and not manager.kill(killed)  # the identity no longer holds


def test_one_writer_per_corpus_one_job_per_slot_and_the_lock(manager: JobManager, tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    first = manager.spawn(JobRequest(("x", "y", "60"), tool="tools/sleeper.py", writes=(str(corpus),),
                                     slot="network"))
    _wait_started(first.directory)
    with pytest.raises(SpawnRefused) as busy:
        manager.spawn(JobRequest(("info",), writes=(str(corpus) + ".partial",)))
    assert busy.value.code == "jobs.writer.busy"
    with pytest.raises(SpawnRefused) as slot:
        manager.spawn(JobRequest(("info",), slot="network"))
    assert slot.value.code == "jobs.slot.busy"
    manager.kill(first)
    _wait(first.directory)
    locked = tmp_path / "other.partial"
    locked.mkdir()
    (locked / ".agentprov.lock").write_text("{}")
    with pytest.raises(SpawnRefused) as lock:
        manager.spawn(JobRequest(("info",), writes=(str(tmp_path / "other"),)))
    assert lock.value.code == "jobs.writer.locked"


def test_drain_needs_a_control_file_and_resume_repeats_the_request(manager: JobManager) -> None:
    plain = manager.spawn(JobRequest(("x", "y", "60"), tool="tools/sleeper.py"))
    assert not manager.request(plain, "drain")
    manager.kill(plain)
    _wait(plain.directory)
    again = manager.resume(load_job(plain.directory))  # type: ignore[arg-type]
    assert again.job_id != plain.job_id and again.record["subcommand_argv"] == ["x", "y", "60"]
    assert again.record["tool"] == "tools/sleeper.py"
    manager.kill(again)
    _wait(again.directory)


def test_prune_keeps_the_newest_and_never_a_running_job(manager: JobManager) -> None:
    for _ in range(3):
        _wait(manager.spawn(JobRequest(("info",))).directory)
    running = manager.spawn(JobRequest(("x", "y", "60"), tool="tools/sleeper.py"))
    candidates = manager.prune_candidates(keep=1)
    assert len(candidates) == 2 and running.job_id not in {j.job_id for j in candidates}
    assert manager.delete(candidates) == 2 and len(list_jobs(manager.home)) == 2
    manager.kill(running)


def test_prune_defaults_come_from_the_retention_settings(manager: JobManager, capsys: pytest.CaptureFixture[str],
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """D-700: ``jobs prune`` keeps ``jobs.retention`` (else 200) jobs and ``jobs.retention_days`` (else 90) days."""
    from agentprov import settings
    from agentprov.cli.main import main

    monkeypatch.setenv("AGENTPROV_HOME", str(manager.home))
    for _ in range(12):
        _wait(manager.spawn(JobRequest(("info",))).directory)

    def listed(*extra: str) -> int:
        capsys.readouterr()
        assert main(["jobs", "prune", "--progress", "off", "--format", "json", *extra]) == 0
        return len(json.loads(capsys.readouterr().out)["jobs"])

    assert listed() == 0  # 12 jobs, default 200 kept
    settings.set("jobs.retention", 10, home=manager.home)
    assert listed() == 2 and listed("--keep", "11") == 1
    (manager.home / "settings.json").write_text("not json")
    capsys.readouterr()
    assert main(["jobs", "prune", "--progress", "off"]) == 2
    assert len(list_jobs(manager.home)) == 12  # nothing deleted


def test_a_job_never_starts_jobs(manager: JobManager) -> None:
    for argv in (("jobs", "start", "--", "info"), ("batch", "start", "x")):
        with pytest.raises(SpawnRefused) as exc:
            manager.spawn(JobRequest(argv))
        assert exc.value.code == "jobs.argv.recursive"


# ---------------------------------------------------------------------------------------------- --tool attacks
@pytest.mark.parametrize("name", ["../evil.py", "tools/../evil.py", "/tmp/evil.py", "tools/sub/../../evil.py",
                                  "evil.py", "tools/notpython.sh", "tools\\sleeper.py", "C:tools/sleeper.py",
                                  "tools/missing.py", "tools"])
def test_tool_paths_that_leave_tools_are_refused(root: Path, name: str) -> None:
    (root / "evil.py").write_text("raise SystemExit(99)")
    (root / "tools" / "notpython.sh").write_text("exit 99")
    with pytest.raises(SpawnRefused):
        resolve_tool(root, name)


def test_symlinks_are_never_followed(root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("raise SystemExit(99)")
    (root / "tools" / "link.py").symlink_to(outside)
    (root / "tools" / "inner.py").write_text("pass")
    (root / "tools" / "alias.py").symlink_to(root / "tools" / "inner.py")  # even one pointing inside
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "x.py").write_text("raise SystemExit(99)")
    (root / "tools" / "dir").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    for name in ("tools/link.py", "tools/alias.py", "tools/dir/x.py"):
        with pytest.raises(SpawnRefused) as exc:
            resolve_tool(root, name)
        assert exc.value.code == "jobs.tool.symlink", name
    assert resolve_tool(root, "tools/inner.py") == (root / "tools" / "inner.py").resolve()


def test_a_symlinked_tools_directory_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "real-tools"
    real.mkdir()
    (real / "t.py").write_text("pass")
    checkout = tmp_path / "co"
    checkout.mkdir()
    (checkout / "tools").symlink_to(real, target_is_directory=True)
    with pytest.raises(SpawnRefused):
        resolve_tool(checkout, "tools/t.py")


def test_no_checkout_no_tool(tmp_path: Path) -> None:
    with pytest.raises(SpawnRefused) as exc:
        resolve_tool(None, "tools/x.py")
    assert exc.value.code == "jobs.tool.no_checkout"


# ---------------------------------------------------------------------------------------------- tiers
@pytest.mark.parametrize(("argv", "tier"), [
    (("info",), "R0"), (("validate", "--corpus", "c"), "R0"), (("validate", "--corpus", "c", "--report", "r"), "R1"),
    (("import", "agentdojo", "--corpus", "c"), "R1"), (("import", "x", "--dry-run"), "R0"),
    (("import", "x", "--fetch", "--allow-network"), "R2"), (("import", "x", "--dry-run", "--allow-net"), "R2"),
    (("run", "agentdojo", "--keychain"), "R2"), (("run", "a", "--max-calls", "5"), "R2"), (("fetch",), "R2"),
    (("prices", "refresh", "--allow-network"), "R2"), (("prices", "set", "e", "m"), "R1"), (("prices", "list"), "R0"),
    (("settings", "get", "k"), "R0"), (("purge", "x", "--yes"), "R1"),
])
def test_tiers(argv: tuple[str, ...], tier: str) -> None:
    assert tiers.tier_of_argv(argv) == tier


def test_destructive() -> None:
    assert tiers.is_destructive(("purge", "x")) and not tiers.is_destructive(("purge", "x", "--dry-run"))
    assert not tiers.is_destructive(("import", "x"))


def test_the_child_runs_this_interpreter(manager: JobManager) -> None:
    job = manager.spawn(JobRequest(("info",)))
    assert job.record["argv"][0] == sys.executable
    _wait(job.directory)


WRAPPER = '''import subprocess, sys, time
from pathlib import Path
out = Path(sys.argv[-1])
child = subprocess.Popen([sys.executable, "-c", "import time\\nwhile True: time.sleep(0.1)"], start_new_session=True)
out.write_text(str(child.pid))
child.wait()
'''


def test_kill_reaches_a_child_in_its_own_session(manager: JobManager, root: Path, tmp_path: Path) -> None:
    """GR-17: the queue wrapper starts the CLI with ``start_new_session=True``; ``kill`` must stop it too."""
    import psutil

    (root / "tools" / "wrapper.py").write_text(WRAPPER)
    pid_file = tmp_path / "child.pid"
    job = manager.spawn(JobRequest((str(pid_file),), tool="tools/wrapper.py"))
    child = None
    try:
        end = time.monotonic() + 15
        while child is None and time.monotonic() < end:
            if pid_file.is_file() and pid_file.read_text():
                child = psutil.Process(int(pid_file.read_text()))
            time.sleep(0.05)
        assert child is not None and os.getpgid(child.pid) != os.getpgid(job.pid or 0)
        assert manager.kill(job)
        child.wait(timeout=5)
        assert not child.is_running()
    finally:
        if child is not None and child.is_running():
            child.kill()


def test_queue_cpu_without_the_queue_tool_is_refused(manager: JobManager) -> None:
    """GR-19 in the core: --queue-cpu needs tools/suite_queue.py of this checkout (the fake checkout has none)."""
    with pytest.raises(SpawnRefused) as exc:
        manager.spawn(JobRequest(("info",), queue_cpu=2))
    assert exc.value.code == "jobs.queue.unavailable" and list(manager.jobs_dir.iterdir()) == []


def test_the_queue_budget_comes_from_the_settings_unless_the_environment_has_it(manager: JobManager) -> None:
    from agentprov import settings

    settings.set("compute.cpu_budget", "6", home=manager.home)
    settings.set("compute.mem_gib_budget", "12.5", home=manager.home)
    env = manager.child_env()
    assert env["AGENTPROV_JOB_CPU_BUDGET"] == "6" and env["AGENTPROV_JOB_MEM_GIB_BUDGET"] == "12.5"
    manager.environ["AGENTPROV_JOB_CPU_BUDGET"] = "3"
    assert manager.child_env()["AGENTPROV_JOB_CPU_BUDGET"] == "3"
