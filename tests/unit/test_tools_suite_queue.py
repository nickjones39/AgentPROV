"""``tools/suite_queue.py``: the machine-wide FIFO for full-suite runs (D-403).

Each test uses its own queue directory under ``tmp_path`` (never the user's ``~/.agentprov/locks``). The end-to-end
cases run the tool as a subprocess with a tiny Python child; their waits are bounded by generous timeouts, and no
assertion depends on how fast the machine is.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "suite_queue.py"


@pytest.fixture(scope="module")
def sq():
    sys.path.insert(0, str(TOOL.parent))
    try:
        import suite_queue

        yield suite_queue
    finally:
        sys.path.remove(str(TOOL.parent))


def _tool(qdir: Path, *args: str, child: str | None = None) -> subprocess.Popen[str]:
    argv = [sys.executable, str(TOOL), "--queue-dir", str(qdir), "--poll", "0.05", "--no-precompile", *args]
    if child is not None:
        argv += ["--", sys.executable, "-c", child]
    return subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _wait_for(predicate, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition not reached"
        time.sleep(0.05)


def test_queue_dir_resolution(sq, tmp_path: Path) -> None:
    assert sq.queue_dir({"AGENTPROV_SUITE_QUEUE_DIR": str(tmp_path / "q")}) == tmp_path / "q"
    assert sq.queue_dir({"AGENTPROV_HOME": str(tmp_path)}) == tmp_path / "locks" / "suite-queue"
    assert sq.queue_dir({}) == Path.home() / ".agentprov" / "locks" / "suite-queue"


def test_stale_and_reused_pid_tickets_are_removed_in_order(sq, tmp_path: Path) -> None:
    tickets = tmp_path / "tickets"
    tickets.mkdir()
    for name, pid in (("002-2", 2), ("001-1", 1), ("003-3", 3)):
        (tickets / f"{name}.json").write_text(json.dumps({"pid": pid}))
    (tickets / "000-0.json").write_text("{not json")
    os.utime(tickets / "000-0.json", (0, 0))  # an old unreadable ticket is stale too
    live = sq.live_tickets(tickets, alive=lambda pid: pid != 2)
    assert [p.name for p in live] == ["001-1.json", "003-3.json"]
    assert sorted(p.name for p in tickets.iterdir()) == ["001-1.json", "003-3.json"]


def test_a_live_pid_that_is_not_the_tool_does_not_hold_a_ticket(sq) -> None:
    assert sq.pid_is_queue_process(os.getpid()) is False  # pytest is alive but is not suite_queue
    assert sq.pid_is_queue_process(2**22 + 12345) is False  # no such process


def test_runs_the_command_and_returns_its_exit_code_and_history(tmp_path: Path) -> None:
    proc = _tool(tmp_path, "--label", "t", child="import sys; sys.exit(3)")
    _, err = proc.communicate(timeout=120)
    assert proc.returncode == 3, err
    (entry,) = [json.loads(line) for line in (tmp_path / "history.jsonl").read_text().splitlines()]
    assert entry["exit"] == 3 and entry["label"] == "t" and entry["wall_s"] >= 0
    assert list((tmp_path / "tickets").iterdir()) == [] and not (tmp_path / "holder.json").exists()


def test_suites_run_one_at_a_time_in_arrival_order(tmp_path: Path) -> None:
    log = tmp_path / "log.txt"
    gate = tmp_path / "gate"
    child = ("import os, sys, time; p, g, n = sys.argv[1:4]\n"
             "open(p, 'a').write(f'start {n}\\n')\n"
             "while n == 'a' and not os.path.exists(g): time.sleep(0.05)\n"
             "open(p, 'a').write(f'end {n}\\n')")
    def start(name: str) -> subprocess.Popen[str]:
        argv = [sys.executable, str(TOOL), "--queue-dir", str(tmp_path / "q"), "--poll", "0.05", "--no-precompile", "--",
                sys.executable, "-c", child, str(log), str(gate), name]
        return subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    a = start("a")
    _wait_for(lambda: log.exists() and "start a" in log.read_text())
    b = start("b")
    _wait_for(lambda: len(list((tmp_path / "q" / "tickets").glob("*.json"))) == 2)
    c = start("c")
    _wait_for(lambda: len(list((tmp_path / "q" / "tickets").glob("*.json"))) == 3)
    assert log.read_text() == "start a\n"  # b and c wait while a holds the queue
    gate.touch()
    for proc in (a, b, c):
        proc.communicate(timeout=120)
        assert proc.returncode == 0
    assert log.read_text().splitlines() == ["start a", "end a", "start b", "end b", "start c", "end c"]


def test_wait_timeout_gives_up_with_ex_tempfail_and_leaves_no_ticket(tmp_path: Path) -> None:
    gate = tmp_path / "gate"
    holder = _tool(tmp_path, child=f"import os, time\nwhile not os.path.exists({str(gate)!r}): time.sleep(0.05)")
    _wait_for(lambda: (tmp_path / "holder.json").exists())
    waiter = _tool(tmp_path, "--wait-timeout", "0.5", child="pass")
    _, err = waiter.communicate(timeout=120)
    assert waiter.returncode == 75 and "gave up" in err
    gate.touch()
    holder.communicate(timeout=120)
    assert holder.returncode == 0 and list((tmp_path / "tickets").iterdir()) == []


def test_run_timeout_stops_the_whole_process_group(tmp_path: Path) -> None:
    pidfile = tmp_path / "grandchild.pid"
    child = ("import subprocess, sys, time\n"
             f"g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])\n"
             f"open({str(pidfile)!r}, 'w').write(str(g.pid))\n"
             "time.sleep(600)")
    proc = _tool(tmp_path, "--run-timeout", "3", "--grace", "5", child=child)
    _, err = proc.communicate(timeout=120)
    assert proc.returncode == 124 and "run timeout" in err
    grandchild = int(pidfile.read_text())
    _wait_for(lambda: not _alive(grandchild), timeout=30)


def test_sigterm_while_waiting_removes_the_ticket(tmp_path: Path) -> None:
    gate = tmp_path / "gate"
    holder = _tool(tmp_path, child=f"import os, time\nwhile not os.path.exists({str(gate)!r}): time.sleep(0.05)")
    _wait_for(lambda: (tmp_path / "holder.json").exists())
    waiter = _tool(tmp_path, child="pass")
    _wait_for(lambda: len(list((tmp_path / "tickets").glob("*.json"))) == 2)
    waiter.send_signal(signal.SIGTERM)
    waiter.communicate(timeout=120)
    assert waiter.returncode == 128 + signal.SIGTERM
    assert len(list((tmp_path / "tickets").glob("*.json"))) == 1
    gate.touch()
    holder.communicate(timeout=120)


def test_status_lists_holder_and_waiters(sq, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert sq.main(["--queue-dir", str(tmp_path), "--status"]) == 0
    assert "running:   nobody" in capsys.readouterr().out


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # a zombie is reaped by init only after its parent exits; ``ps`` shows it as Z
    out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return bool(out.stdout.strip()) and not out.stdout.strip().startswith("Z")


def test_child_env_turns_bytecode_on_under_the_prefix(sq, tmp_path: Path) -> None:
    env = sq.child_env({"PYTHONDONTWRITEBYTECODE": "1", "KEEP": "x"}, tmp_path / "pyc")
    assert env == {"KEEP": "x", "PYTHONPYCACHEPREFIX": str(tmp_path / "pyc")}
    assert sq.pycache_prefix({"AGENTPROV_PYCACHE_PREFIX": str(tmp_path)}) == tmp_path
    assert sq.pycache_prefix({}) == Path.home() / ".cache" / "agentprov" / "pycache"


def test_clear_pycache_removes_only_a_bytecode_tree(sq, tmp_path: Path) -> None:
    cache = tmp_path / "pyc" / "a" / "b"
    cache.mkdir(parents=True)
    (cache / "m.cpython-314.pyc").write_bytes(b"x")
    (cache / "t.cpython-314-pytest-9.1.1.pyc.4711").write_bytes(b"x")
    sq.clear_pycache(tmp_path / "pyc")
    assert not (tmp_path / "pyc").exists()
    other = tmp_path / "other"
    other.mkdir()
    (other / "notes.txt").write_text("keep")
    with pytest.raises(SystemExit, match="other than .pyc"):
        sq.clear_pycache(other)
    assert (other / "notes.txt").exists()


def test_targeted_runs_now_outside_the_queue_with_the_bytecode_env(tmp_path: Path) -> None:
    gate = tmp_path / "gate"
    holder = _tool(tmp_path, child=f"import os, time\nwhile not os.path.exists({str(gate)!r}): time.sleep(0.05)")
    _wait_for(lambda: (tmp_path / "holder.json").exists())
    out = tmp_path / "env.json"
    child = (f"import json, os, sys; json.dump([os.environ.get('PYTHONPYCACHEPREFIX'), "
             f"os.environ.get('PYTHONDONTWRITEBYTECODE'), sys.flags.dont_write_bytecode], open({str(out)!r}, 'w'))")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "AGENTPROV_PYCACHE_PREFIX": str(tmp_path / "pyc")}
    targeted = subprocess.run([sys.executable, str(TOOL), "--queue-dir", str(tmp_path), "--targeted", "--no-precompile", "--",
                               sys.executable, "-c", child], env=env, capture_output=True, text=True, timeout=120)
    assert targeted.returncode == 0, targeted.stderr  # did not wait for the holder
    assert json.loads(out.read_text()) == [str(tmp_path / "pyc"), None, 0]
    gate.touch()
    holder.communicate(timeout=120)


def test_precompile_writes_hash_checked_bytecode_and_leaves_the_checkout_clean(tmp_path: Path) -> None:
    """D-407: ``src/agentprov`` only, ``checked-hash`` .pyc files, and ``git status --porcelain`` stays empty under the
    repository's own ``.gitignore``."""
    repo = tmp_path / "checkout"
    (repo / "src" / "agentprov" / "sub").mkdir(parents=True)
    (repo / "tests").mkdir()
    for rel in ("src/agentprov/__init__.py", "src/agentprov/sub/__init__.py", "src/agentprov/sub/m.py", "tests/t.py"):
        (repo / rel).write_text("X = 1\n")
    (repo / ".gitignore").write_bytes((REPO / ".gitignore").read_bytes())
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", "-C", str(repo)]
    for argv in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "init"]):
        subprocess.run([*git, *argv], check=True, capture_output=True)
    done = subprocess.run([sys.executable, str(TOOL), "--queue-dir", str(tmp_path / "q"), "--targeted", "--",
                           sys.executable, "-c", "pass"], cwd=repo, capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr
    pycs = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*.pyc"))
    assert pycs and all(p.startswith("src/agentprov/") and "/__pycache__/" in p for p in pycs)
    for pyc in repo.rglob("*.pyc"):
        flags = int.from_bytes(pyc.read_bytes()[4:8], "little")
        assert flags == 0b11  # hash-based and checked against the source (PEP 552)
    status = subprocess.run([*git, "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True,
                            check=True)
    assert status.stdout == ""


def test_a_waiter_whose_ticket_vanished_writes_it_again_and_keeps_its_place(tmp_path: Path) -> None:
    gate = tmp_path / "gate"
    holder = _tool(tmp_path, child=f"import os, time\nwhile not os.path.exists({str(gate)!r}): time.sleep(0.05)")
    _wait_for(lambda: (tmp_path / "holder.json").exists())
    waiter = _tool(tmp_path, child="pass")
    _wait_for(lambda: len(list((tmp_path / "tickets").glob("*.json"))) == 2)
    mine = max((tmp_path / "tickets").glob("*.json"))
    mine.unlink()  # as a mistaken stale check by another waiter would
    _wait_for(mine.exists)
    gate.touch()
    holder.communicate(timeout=120)
    waiter.communicate(timeout=120)
    assert waiter.returncode == 0 and list((tmp_path / "tickets").iterdir()) == []


def _orphan_group(tmp_path: Path, *, started_at: float, run_timeout_s: float) -> subprocess.Popen[bytes]:
    """A process group left running by a holder that died (a dead pid in ``holder.json``)."""
    group = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"], start_new_session=True)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    sys.path.insert(0, str(TOOL.parent))
    try:
        import suite_queue  # the identity a real holder records at spawn (the pgid-reuse guard)
    finally:
        sys.path.remove(str(TOOL.parent))
    _wait_for(lambda: suite_queue.process_identity(group.pid) is not None)
    identity = {f"child_{k}": v for k, v in (suite_queue.process_identity(group.pid) or {}).items()}
    (tmp_path / "holder.json").write_text(json.dumps({"pid": dead.pid, "child_pgid": group.pid, "label": "dead",
                                                      "started_at": started_at, "run_timeout_s": run_timeout_s,
                                                      **identity}))
    return group


def test_an_orphaned_suite_of_a_dead_holder_is_waited_for(tmp_path: Path) -> None:
    (tmp_path / "tickets").mkdir()
    group = _orphan_group(tmp_path, started_at=time.time(), run_timeout_s=7200)
    try:
        waiter = _tool(tmp_path, "--wait-timeout", "1.5", child="pass")
        _, err = waiter.communicate(timeout=120)
        assert waiter.returncode == 75  # it did not start next to the orphan
        waiter = _tool(tmp_path, child="pass")
        time.sleep(0.5)
        assert waiter.poll() is None
        os.killpg(group.pid, signal.SIGTERM)
        waiter.communicate(timeout=120)
        assert waiter.returncode == 0
    finally:
        if group.poll() is None:
            os.killpg(group.pid, signal.SIGKILL)
        group.wait()


def test_an_orphan_past_its_own_run_timeout_is_stopped(tmp_path: Path) -> None:
    (tmp_path / "tickets").mkdir()
    group = _orphan_group(tmp_path, started_at=time.time() - 100, run_timeout_s=10)
    try:
        waiter = _tool(tmp_path, "--grace", "5", child="pass")
        _, err = waiter.communicate(timeout=120)
        assert waiter.returncode == 0 and "orphaned suite" in err
        assert group.wait(timeout=30) is not None
    finally:
        if group.poll() is None:
            os.killpg(group.pid, signal.SIGKILL)
            group.wait()


def test_a_failed_precompile_still_runs_the_suite(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    (repo / "src" / "agentprov").mkdir(parents=True)
    (repo / "src" / "agentprov" / "__init__.py").write_text("X = 1\n")
    (repo / "src" / "agentprov" / "broken.py").write_text("def (:\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    done = subprocess.run([sys.executable, str(TOOL), "--queue-dir", str(tmp_path / "q"), "--targeted", "--",
                           sys.executable, "-c", "import sys; sys.exit(7)"], cwd=repo, capture_output=True, text=True,
                          timeout=300)
    assert done.returncode == 7 and "precompile" in done.stderr and "Traceback" not in done.stderr
