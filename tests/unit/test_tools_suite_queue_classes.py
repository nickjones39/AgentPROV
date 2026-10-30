"""``tools/suite_queue.py`` job classes and the machine budget (D-427), and the holder-ticket display fix.

Each test uses its own queue directory under ``tmp_path``. Children are tiny Python programs that log and wait for a
gate file; budgets are set through the environment so no assertion depends on the machine's size or load
(``--load-wait 0`` lets the load guard start at once).
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

CHILD = ("import os, sys, time; p, g, n = sys.argv[1:4]\n"
         "open(p, 'a').write(f'start {n}\\n')\n"
         "while not os.path.exists(g + n): time.sleep(0.05)\n"
         "open(p, 'a').write(f'end {n}\\n')")


@pytest.fixture(scope="module")
def sq():
    sys.path.insert(0, str(TOOL.parent))
    try:
        import suite_queue

        yield suite_queue
    finally:
        sys.path.remove(str(TOOL.parent))


def _env(**budget: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENTPROV_JOB_", "AGENTPROV_QUEUE_SLOTS"))}
    env.update({f"AGENTPROV_JOB_{k.upper()}": v for k, v in budget.items()})
    return env


def _job(qdir: Path, log: Path, name: str, *opts: str, env: dict[str, str]) -> subprocess.Popen[str]:
    argv = [sys.executable, str(TOOL), "--queue-dir", str(qdir), "--poll", "0.05", "--no-precompile", "--load-wait",
            "0", "--label", name, *opts, "--", sys.executable, "-c", CHILD, str(log), str(log) + ".gate-", name]
    return subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)


def _wait_for(predicate, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition not reached"
        time.sleep(0.05)


def _labels(directory: Path) -> list[str]:
    """The labels of the records in ``directory`` right now. A record removed between the listing and the read (a job
    giving its reservation back, as the tool's own ``_read_json`` allows for) is skipped, not an error."""
    labels = []
    for path in sorted(directory.glob("*.json")):
        try:
            labels.append(json.loads(path.read_text())["label"])
        except FileNotFoundError:
            continue
    return labels


def _started(log: Path, *names: str) -> bool:
    return log.exists() and all(f"start {n}" in log.read_text() for n in names)


def _release(log: Path, name: str) -> None:
    Path(str(log) + ".gate-" + name).touch()


def _finish(*procs: subprocess.Popen[str]) -> None:
    for proc in procs:
        _out, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, err


def test_default_costs_and_budget(sq) -> None:
    n, host = sq.ncpu(), sq.host_default_workers()
    # ceil(0.8 x workers): the measured -n 10 gate averages 6.5-7.0 CPUs (docs/reports/suite-perf/results.md)
    assert sq.default_cost("suite", ["pytest", "-n", "10"]) == (8.0, 12.0)
    assert sq.default_cost("suite", ["pytest", "-n", "8"]) == (7.0, 10.5)
    assert sq.default_cost("suite", ["pytest", "-n8"]) == (7.0, 10.5)
    assert sq.default_cost("suite", ["pytest", "--numprocesses=4"]) == (4.0, 6.0)
    # Mac Studio headroom (2026-10-28): workers past 10 count half
    assert sq.default_cost("suite", ["pytest", "-n", "24"]) == (15.0, 22.5)
    assert sq.default_cost("suite", ["pytest", "-n", "11"]) == (9.0, 13.5)  # ceil(8.5)
    auto = float(max(1, -(-(8 * min(n, 10) + 5 * max(0, n - 10)) // 10)))
    assert sq.default_cost("suite", ["pytest", "-n", "auto"]) == (auto, 1.5 * auto)
    assert sq.default_cost("suite", ["pytest", "-n", "0"]) == (1.0, 1.5)
    assert sq.default_cost("suite", ["pytest", "-q"]) == (1.0, 1.5)
    assert sq.default_cost("import", ["agentprov", "import", "x", "--workers", "3"]) == (3.0, 12.0)
    assert sq.default_cost("rehearsal", ["agentprov", "recompute", "--jobs=6"]) == (6.0, 24.0)
    assert sq.default_cost("import", ["agentprov", "import", "x"]) == (float(host), 4.0 * host)  # the CLI's 0
    assert sq.default_cost("import", ["agentprov", "import", "x", "--jobs", "0"]) == (float(host), 4.0 * host)
    ram = sq.physical_gib()
    assert host == max(1, min(n, int(0.75 * ram // 4) if ram else n))
    assert sq.budget({"AGENTPROV_JOB_CPU_BUDGET": "4", "AGENTPROV_JOB_MEM_GIB_BUDGET": "16"}) == (4.0, 16.0)
    cpu, mem = sq.budget({})
    assert cpu == max(1, n - 2) and mem > 0


def test_an_old_version_suite_holder_counts_against_the_budget(sq, tmp_path: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """During the rollout an old wrapper runs a suite with no jobs/running record: count its default reservation."""
    old_pid = 4242
    monkeypatch.setattr(sq, "pid_is_queue_process", lambda pid: pid in (os.getpid(), old_pid))
    (tmp_path / "holder.json").write_text(json.dumps({"pid": old_pid, "label": "old suite",
                                                      "command": "pytest -n 16"}), encoding="utf-8")
    env = {"AGENTPROV_JOB_CPU_BUDGET": "10", "AGENTPROV_JOB_MEM_GIB_BUDGET": "512"}
    adm = sq.Admission(tmp_path / "jobs", "import", "x", {"pid": os.getpid(), "enqueued_at": 1.0, "cpu": 1,
                                                         "mem_gib": 1}, load_guard=False, load_wait=0, environ=env)
    # its default reservation (-n 16: 11, clamped to 10) leaves imports no suite headroom
    assert "running (10 CPUs), so imports and rehearsals get 0+1 of 0 CPUs" in str(adm.try_admit(time.time()))
    (tmp_path / "holder.json").unlink()
    assert adm.try_admit(time.time()) is None


def test_a_head_held_only_by_the_load_guard_never_stalls_a_suite(sq, tmp_path: Path,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sq.os, "getloadavg", lambda: (10.0 * sq.ncpu(), 0.0, 0.0))
    monkeypatch.setattr(sq, "pid_is_queue_process", lambda pid: True)
    env = {"AGENTPROV_JOB_CPU_BUDGET": "64", "AGENTPROV_JOB_MEM_GIB_BUDGET": "512"}
    old_import = sq.Admission(tmp_path, "import", "old", {"pid": 1111, "enqueued_at": 1.0, "cpu": 1, "mem_gib": 1},
                              load_guard=True, load_wait=600, environ=env)
    assert "load" in str(old_import.try_admit(100.0))
    assert json.loads((tmp_path / "waiting" / "import-old.json").read_text())["blocked"] == "load"
    suite = sq.Admission(tmp_path, "suite", "new", {"pid": 2222, "enqueued_at": 2.0, "cpu": 8, "mem_gib": 8},
                         load_guard=False, load_wait=600, environ=env)
    assert suite.try_admit(101.0) is None  # younger, but the older head waits only for the load guard
    budget_env = {"AGENTPROV_JOB_CPU_BUDGET": "8", "AGENTPROV_JOB_MEM_GIB_BUDGET": "512"}
    blocked = sq.Admission(tmp_path, "rehearsal", "big", {"pid": 3333, "enqueued_at": 3.0, "cpu": 4, "mem_gib": 1},
                           load_guard=False, load_wait=0, environ=budget_env)
    assert str(blocked.try_admit(102.0)).startswith("suite headroom")  # the running suite leaves 0 of 8
    small = sq.Admission(tmp_path, "rehearsal", "small", {"pid": 4444, "enqueued_at": 4.0, "cpu": 0, "mem_gib": 0},
                         load_guard=False, load_wait=0, environ=budget_env)
    # any wait other than the load guard holds younger heads of the import and rehearsal lanes
    assert "an older rehearsal job waits for the suite headroom" in str(small.try_admit(103.0))


def test_import_class_runs_two_at_a_time(tmp_path: Path) -> None:
    log, env = tmp_path / "log.txt", _env(cpu_budget="64", mem_gib_budget="512")
    env["AGENTPROV_QUEUE_SLOTS"] = "import=2"  # a 64-CPU budget alone would give 12 slots (A1)
    a = _job(tmp_path / "q", log, "a", "--class", "import", "--cpu", "1", env=env)
    b = _job(tmp_path / "q", log, "b", "--class", "import", "--cpu", "1", env=env)
    _wait_for(lambda: _started(log, "a", "b"))
    c = _job(tmp_path / "q", log, "c", "--class", "import", "--cpu", "1", env=env)
    _wait_for(lambda: len(list((tmp_path / "q" / "jobs" / "import" / "tickets").glob("*.json"))) == 3)
    time.sleep(0.5)
    assert "start c" not in log.read_text()  # two slots, both busy
    _release(log, "a")
    _wait_for(lambda: _started(log, "c"))
    for name in ("b", "c"):
        _release(log, name)
    _finish(a, b, c)
    assert (tmp_path / "q" / "jobs" / "import" / "history.jsonl").read_text().count('"exit": 0') == 3
    assert not list((tmp_path / "q" / "jobs" / "running").glob("*.json"))
    assert not (tmp_path / "q" / "history.jsonl").exists()  # the suite class is untouched


def test_budget_and_fifo_among_class_heads(tmp_path: Path) -> None:
    """A (import, 3 CPUs) runs; B (suite, 3) must wait for the budget of 4; C (rehearsal, 1) would fit but is younger
    than B, so it waits until B has started."""
    log, env = tmp_path / "log.txt", _env(cpu_budget="4", mem_gib_budget="512")
    q = tmp_path / "q"
    a = _job(q, log, "a", "--class", "import", "--cpu", "3", env=env)
    _wait_for(lambda: _started(log, "a"))
    b = _job(q, log, "b", "--cpu", "3", env=env)
    _wait_for(lambda: len(list((q / "jobs" / "waiting").glob("*.json"))) == 1)
    c = _job(q, log, "c", "--class", "rehearsal", "--cpu", "1", env=env)
    _wait_for(lambda: len(list((q / "jobs" / "rehearsal" / "tickets").glob("*.json"))) == 1)
    time.sleep(0.5)
    assert log.read_text() == "start a\n"
    _release(log, "a")
    _wait_for(lambda: _started(log, "b", "c"))
    for name in ("b", "c"):
        _release(log, name)
    _finish(a, b, c)
    (b_run,) = [json.loads(x) for x in (q / "history.jsonl").read_text().splitlines()]
    (c_run,) = [json.loads(x) for x in (q / "jobs" / "rehearsal" / "history.jsonl").read_text().splitlines()]
    assert b_run["admitted_at"] <= c_run["admitted_at"]  # admitted in arrival order (child start times may race)
    assert (b_run["cpu"], c_run["cpu"]) == (3.0, 1.0)


def test_a_reservation_larger_than_the_budget_is_clamped(sq, tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    adm = sq.Admission(root, "suite", "x", {"pid": os.getpid(), "enqueued_at": 1.0, "cpu": 99, "mem_gib": 999},
                       load_guard=False, load_wait=0, environ={"AGENTPROV_JOB_CPU_BUDGET": "4",
                                                               "AGENTPROV_JOB_MEM_GIB_BUDGET": "8"})
    assert (adm.record["cpu"], adm.record["mem_gib"]) == (4.0, 8.0)


def test_dead_reservations_are_returned(sq, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "jobs"
    (root / "running").mkdir(parents=True)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    (root / "running" / "import-old.json").write_text(json.dumps({"pid": dead.pid, "cpu": 4, "mem_gib": 8,
                                                                  "enqueued_at": 0}), encoding="utf-8")
    monkeypatch.setattr(sq, "pid_is_queue_process", lambda pid: pid == os.getpid())
    adm = sq.Admission(root, "import", "new", {"pid": os.getpid(), "enqueued_at": 5.0, "cpu": 4, "mem_gib": 8},
                       load_guard=False, load_wait=0, environ={"AGENTPROV_JOB_CPU_BUDGET": "4",
                                                               "AGENTPROV_JOB_MEM_GIB_BUDGET": "8"})
    assert adm.try_admit(time.time()) is None
    assert sorted(p.name for p in (root / "running").iterdir()) == ["import-new.json"]
    adm.leave()
    assert not list((root / "running").iterdir())


def test_load_guard_waits_then_starts(sq, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sq.os, "getloadavg", lambda: (10.0 * sq.ncpu(), 0.0, 0.0))
    monkeypatch.setattr(sq, "pid_is_queue_process", lambda pid: pid == os.getpid())
    env = {"AGENTPROV_JOB_CPU_BUDGET": "64", "AGENTPROV_JOB_MEM_GIB_BUDGET": "512"}
    adm = sq.Admission(tmp_path, "import", "x", {"pid": os.getpid(), "enqueued_at": 1.0, "cpu": 1, "mem_gib": 1},
                       load_guard=True, load_wait=30, environ=env)
    assert "load from outside the queue" in str(adm.try_admit(1000.0))
    assert adm.try_admit(1029.0) is not None
    assert adm.try_admit(1031.0) is None  # waited long enough: starts anyway
    suite = sq.Admission(tmp_path, "suite", "y", {"pid": os.getpid(), "enqueued_at": 2.0, "cpu": 1, "mem_gib": 1},
                         load_guard=False, load_wait=30, environ=env)
    assert suite.try_admit(1000.0) is None  # the suite class has no load guard


def test_import_and_rehearsal_keep_the_session_environment(tmp_path: Path) -> None:
    out = tmp_path / "env.json"
    env = _env(cpu_budget="64", mem_gib_budget="512")
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX="/session/prefix")
    dump = (f"import json, os; json.dump({{k: os.environ.get(k) for k in "
            f"('PYTHONDONTWRITEBYTECODE', 'PYTHONPYCACHEPREFIX')}}, open({str(out)!r}, 'w'))")
    for job_class, expected in (("import", {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPYCACHEPREFIX": "/session/prefix"}),
                                ("suite", None)):
        argv = [sys.executable, str(TOOL), "--queue-dir", str(tmp_path / "q"), "--poll", "0.05", "--no-precompile",
                "--load-wait", "0", "--class", job_class, "--", sys.executable, "-c", dump]
        done = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=120)
        assert done.returncode == 0, done.stderr
        got = json.loads(out.read_text())
        if expected is not None:
            assert got == expected
        else:  # D-406 still applies to suites
            assert got["PYTHONDONTWRITEBYTECODE"] is None and got["PYTHONPYCACHEPREFIX"] != "/session/prefix"


def test_status_and_position_do_not_count_the_running_holder(sq, tmp_path: Path,
                                                              capsys: pytest.CaptureFixture[str]) -> None:
    log, env = tmp_path / "log.txt", _env(cpu_budget="64", mem_gib_budget="512")
    q = tmp_path / "q"
    a = _job(q, log, "a", env=env)
    _wait_for(lambda: _started(log, "a") and (q / "holder.json").exists())
    # b's stderr goes to a file, so the test can wait for b's own waiting line instead of for time: b writes its
    # ticket before its first poll, and under load a released too early would let b start without ever waiting.
    b_err_file = tmp_path / "b.err"
    with b_err_file.open("w", encoding="utf-8") as b_err_fh:
        b = subprocess.Popen(
            [sys.executable, str(TOOL), "--queue-dir", str(q), "--poll", "0.05", "--no-precompile", "--load-wait", "0",
             "--label", "b", "--", sys.executable, "-c", CHILD, str(log), str(log) + ".gate-", "b"],
            stdout=subprocess.DEVNULL, stderr=b_err_fh, text=True, env=env)
    _wait_for(lambda: "position 1 of 1" in b_err_file.read_text(encoding="utf-8"))
    capsys.readouterr()
    assert sq.main(["--queue-dir", str(q), "--status"]) == 0
    out = capsys.readouterr().out
    assert "running:   a (" in out
    assert "  running. pid" in out and "  1. pid" in out and "  2. pid" not in out
    assert "budget:    " in out
    _release(log, "a")
    _wait_for(lambda: _started(log, "b"))
    _release(log, "b")
    _a_out, _a_err = a.communicate(timeout=120)
    assert b.wait(timeout=120) == 0 and a.returncode == 0
    assert "position 2" not in b_err_file.read_text(encoding="utf-8")  # the holder's own ticket is never counted


def test_before_head_runs_next_and_records_its_reason(sq, tmp_path: Path,
                                                      capsys: pytest.CaptureFixture[str]) -> None:
    """Sanctioned jumps: c, then d, queue before the ordinary waiter b, FIFO among themselves (a, c, d, b)."""
    log, env = tmp_path / "log.txt", _env(cpu_budget="64", mem_gib_budget="512")
    q = tmp_path / "q"
    a = _job(q, log, "a", env=env)
    _wait_for(lambda: _started(log, "a") and (q / "holder.json").exists())
    b = _job(q, log, "b", env=env)
    _wait_for(lambda: len(list((q / "tickets").glob("*.json"))) == 2)
    c = _job(q, log, "c", "--before-head", "--reason", "gate-integrity fix (orchestrator-approved)", env=env)
    _wait_for(lambda: len(list((q / "tickets").glob("*.json"))) == 3)
    d = _job(q, log, "d", "--before-head", "--reason", "second fix", env=env)
    _wait_for(lambda: len(list((q / "tickets").glob("*.json"))) == 4)
    names = sorted(p.name for p in (q / "tickets").glob("*.json"))
    tickets = [json.loads((q / "tickets" / n).read_text()) for n in names]
    assert [t["label"] for t in tickets] == ["a", "c", "d", "b"]  # after the holder and earlier jumps, before b
    assert tickets[1]["order_at"] < tickets[2]["order_at"] < tickets[3]["enqueued_at"]
    capsys.readouterr()
    assert sq.main(["--queue-dir", str(q), "--status"]) == 0
    out = capsys.readouterr().out
    assert "  1. pid" in out and "[priority: gate-integrity fix" in out and "  3. pid" in out
    _release(log, "a")
    _wait_for(lambda: _started(log, "c"))
    assert "start d" not in log.read_text() and "start b" not in log.read_text()
    for name in ("c", "d", "b"):
        _release(log, name)
    _finish(a, b, c, d)
    assert [x for x in log.read_text().splitlines() if x.startswith("start")] == ["start a", "start c", "start d",
                                                                                   "start b"]
    runs = {r["label"]: r for r in (json.loads(x) for x in (q / "history.jsonl").read_text().splitlines())}
    assert runs["c"]["priority_reason"] == "gate-integrity fix (orchestrator-approved)"
    assert runs["d"]["priority_reason"] == "second fix" and "priority_reason" not in runs["b"]


def test_before_head_needs_a_reason_and_is_plain_when_nobody_waits(sq, tmp_path: Path) -> None:
    done = subprocess.run([sys.executable, str(TOOL), "--queue-dir", str(tmp_path / "q"), "--before-head", "--",
                           sys.executable, "-c", "pass"], capture_output=True, text=True, timeout=60)
    assert done.returncode == 2 and "--before-head needs --reason" in done.stderr
    (tmp_path / "q" / "tickets").mkdir(parents=True, exist_ok=True)
    stem, order_at = sq.priority_stem(tmp_path / "q", "suite", os.getpid(), 123.0)
    assert stem.endswith(f"-{os.getpid()}") and order_at == 123.0


def _unrelated_group() -> subprocess.Popen[bytes]:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"], start_new_session=True)


def _dead_pid() -> int:
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    return dead.pid


@pytest.mark.parametrize("identity", [
    {"child_lstart": "Thu Jan  1 00:00:00 1970", "child_command": "pytest -n 8"},  # the pgid was recycled
    {},  # an older wrapper's record: cannot be verified
])
def test_a_recycled_or_unverifiable_pgid_is_never_waited_for_or_killed(sq, tmp_path: Path, identity) -> None:
    """A dead holder's recorded child_pgid now names an unrelated live group: no wait, and no signal even though the
    dead holder's own run timeout has long passed."""
    group = _unrelated_group()
    try:
        _wait_for(lambda: sq.process_identity(group.pid) is not None)
        (tmp_path / "tickets").mkdir()
        (tmp_path / "holder.json").write_text(json.dumps({
            "pid": _dead_pid(), "child_pgid": group.pid, "label": "dead", "started_at": time.time() - 9000,
            "run_timeout_s": 10, **identity}), encoding="utf-8")
        assert sq.orphan(json.loads((tmp_path / "holder.json").read_text()), time.time()) is None
        done = subprocess.run([sys.executable, str(TOOL), "--queue-dir", str(tmp_path), "--poll", "0.05",
                               "--no-precompile", "--grace", "1", "--wait-timeout", "30", "--", sys.executable, "-c",
                               "pass"], capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, done.stderr
        assert "orphaned suite" not in done.stderr
        assert group.poll() is None  # the unrelated group was not signalled
        sq._stop_pgid(group.pid, 1, {"child_lstart": "x", "child_command": "y"})
        time.sleep(0.3)
        assert group.poll() is None  # the kill path re-checks too
    finally:
        if group.poll() is None:
            os.killpg(group.pid, signal.SIGKILL)
        group.wait()


def test_the_recorded_identity_still_finds_a_real_orphan(sq) -> None:
    group = _unrelated_group()
    try:
        _wait_for(lambda: sq.process_identity(group.pid) is not None)
        identity = sq.process_identity(group.pid)
        assert identity is not None and "time.sleep(600)" in identity["command"]
        holder = {"pid": _dead_pid(), "child_pgid": group.pid, "started_at": time.time(), "run_timeout_s": 7200,
                  "child_lstart": identity["lstart"], "child_command": identity["command"]}
        assert sq.orphan(holder, time.time()) == (group.pid, False)
    finally:
        os.killpg(group.pid, signal.SIGKILL)
        group.wait()


def test_a_priority_ticket_overtakes_a_budget_blocked_head(tmp_path: Path) -> None:
    """The head of the suite class waits for the budget without holding suite.lock, so a --before-head job that fits
    runs first (it used to be stuck behind the head's lock)."""
    log, env = tmp_path / "log.txt", _env(cpu_budget="4", mem_gib_budget="512")
    q = tmp_path / "q"
    a = _job(q, log, "a", "--class", "import", "--cpu", "3", env=env)
    _wait_for(lambda: _started(log, "a"))
    h = _job(q, log, "h", "--cpu", "3", env=env)  # 3 + 3 > 4: waits for the budget
    _wait_for(lambda: len(list((q / "jobs" / "waiting").glob("*.json"))) == 1)
    p = _job(q, log, "p", "--cpu", "1", "--before-head", "--reason", "gate-integrity fix", env=env)  # 3 + 1 fits
    _wait_for(lambda: _started(log, "p"))
    assert "start h" not in log.read_text()
    assert not list((q / "jobs" / "waiting").glob("*.json"))  # h is no longer a head and holds nobody back
    _release(log, "p")
    p.communicate(timeout=120)
    time.sleep(0.5)
    assert "start h" not in log.read_text()  # still waiting for a's budget
    _release(log, "a")
    _wait_for(lambda: _started(log, "h"))
    _release(log, "h")
    _finish(a, h)
    assert p.returncode == 0


def test_an_admitted_job_waiting_for_the_lock_yields_to_a_priority_job(tmp_path: Path) -> None:
    """suite-perf's deadlock: A is admitted while the finishing holder still has suite.lock; P (--before-head) then
    queues before A. A must give its reservation back, or P's admission waits for A while A waits for P."""
    log, env = tmp_path / "log.txt", _env(cpu_budget="4", mem_gib_budget="512")
    q = tmp_path / "q"
    (q / "tickets").mkdir(parents=True)
    gate = tmp_path / "release-lock"
    finishing = subprocess.Popen([sys.executable, "-c", (
        "import fcntl, os, sys, time; fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600); "
        "fcntl.flock(fd, fcntl.LOCK_EX); open(sys.argv[2] + '.held', 'w').close(); "
        "[time.sleep(0.05) for _ in iter(lambda: os.path.exists(sys.argv[2]), True)]"), str(q / "suite.lock"),
        str(gate)])
    try:
        _wait_for(lambda: Path(str(gate) + ".held").exists())  # a holder whose ticket is gone, its lock not yet
        a = _job(q, log, "a", "--cpu", "3", env=env)
        _wait_for(lambda: len(list((q / "jobs" / "running").glob("*.json"))) == 1)  # admitted, blocked on the lock
        p = _job(q, log, "p", "--cpu", "3", "--before-head", "--reason", "gate-integrity fix", env=env)
        _wait_for(lambda: len(list((q / "tickets").glob("*.json"))) == 2)
        _wait_for(lambda: _labels(q / "jobs" / "running") == ["p"])  # a gave its reservation back; p is admitted (3 + 3 > 4 would not fit beside a)
        gate.touch()
        _wait_for(lambda: _started(log, "p"))
        assert "start a" not in log.read_text()
        _release(log, "p")
        _wait_for(lambda: _started(log, "a"))
        _release(log, "a")
        _finish(p, a)
        lines = log.read_text().splitlines()
        assert lines.index("end p") < lines.index("start a")
    finally:
        gate.touch()
        finishing.wait(timeout=60)


# --------------------------------------------------------------------------------------------- follow-up batch

WORKER_CHILD = """import os, subprocess, sys, time
pidfile, mode = sys.argv[1], sys.argv[2]
w = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"], start_new_session=True)
open(pidfile, "w").write(str(w.pid))
time.sleep(600 if mode == "hang" else 1.0)  # a suite runs for a while after starting its workers
"""


def _alive(pid: int) -> bool:
    out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return bool(out.stdout.strip()) and not out.stdout.strip().startswith("Z")


@pytest.mark.parametrize("mode", ["hang", "exit"])
def test_workers_in_their_own_session_do_not_outlive_the_slot(sq, tmp_path: Path, mode: str) -> None:
    """BF-1: an agentprov.worker starts its own session, so stopping the suite's process group missed it. After a
    run timeout ("hang") or when the suite exits and leaves it behind ("exit"), it must be gone before run_child
    returns, i.e. before the queue releases the slot and the budget."""
    pidfile = tmp_path / "worker.pid"
    code = sq.run_child([sys.executable, "-c", WORKER_CHILD, str(pidfile), mode],
                        run_timeout=3.0 if mode == "hang" else 60.0, grace=2.0, track_every=0.2)
    wpid = int(pidfile.read_text())
    try:
        assert code == (sq.EX_TIMEOUT if mode == "hang" else 0)
        assert not _alive(wpid)
    finally:
        if _alive(wpid):
            os.kill(wpid, signal.SIGKILL)


def test_sweep_leaves_a_reused_pid_alone(sq) -> None:
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    try:
        assert sq.sweep({other.pid: "Thu Jan  1 00:00:00 1970"}, 1.0) == 0  # same pid, other start time
        assert other.poll() is None
    finally:
        other.kill()
        other.wait()


def test_clearing_the_bytecode_cache_tolerates_a_concurrent_writer(sq, tmp_path: Path,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """BF-2: another session's interpreter drops a .pyc into a directory the clear has listed; no OSError, and the
    gate goes on. The tree is renamed aside first; what a writer leaves there goes with the next clear."""
    prefix = tmp_path / "cache" / "agentprov" / "pycache"
    dirs = []
    for i in range(20):
        d = prefix / "Users" / "x" / f"wt{i}" / "__pycache__"
        d.mkdir(parents=True)
        (d / "m.cpython-314.pyc").write_bytes(b"\0" * 16)
        dirs.append(d)
    real_rmdir, fired = os.rmdir, []

    def racing_rmdir(path, *a, **kw):
        if not fired and os.fspath(path) == "__pycache__":
            fired.append(1)
            for leftover in (tmp_path / "cache" / "agentprov").glob("pycache.trash-*/Users/x/wt0/__pycache__"):
                (leftover / "late.cpython-314.pyc").write_bytes(b"\0")
        return real_rmdir(path, *a, **kw)

    monkeypatch.setattr(os, "rmdir", racing_rmdir)
    sq.clear_pycache(prefix)
    monkeypatch.setattr(os, "rmdir", real_rmdir)
    assert not prefix.exists()
    sq.clear_pycache(prefix)  # the next clear removes any leftover trash
    assert not list((tmp_path / "cache" / "agentprov").glob("pycache.trash-*"))


def test_cpu_alone_scales_the_memory_reservation(sq) -> None:
    assert sq.reservation("suite", ["pytest", "-n", "10"], 4.0, None) == (4.0, 6.0)  # not 18 GiB
    assert sq.reservation("import", ["agentprov", "import", "--jobs", "2"], 3.0, None) == (3.0, 12.0)
    assert sq.reservation("suite", ["pytest", "-n", "10"], 4.0, 20.0) == (4.0, 20.0)
    assert sq.reservation("suite", ["pytest", "-n", "10"], None, None) == (8.0, 12.0)


def test_a_queued_suite_keeps_an_existing_session_status_current(tmp_path: Path) -> None:
    repo = tmp_path / "wt"
    repo.mkdir()
    git_env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
               "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["init", "-q", "-b", "feature"], ["commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(["git", *cmd], cwd=repo, check=True, env=git_env, capture_output=True)
    env = {**_env(cpu_budget="64", mem_gib_budget="512"), **git_env, "AGENTPROV_HOME": str(tmp_path / "home")}
    for var in ("AGENTPROV_SESSION_NAME", "AGENTPROV_SESSIONS_DIR"):  # the caller's own session must not leak in
        env.pop(var, None)
    status_tool = [sys.executable, str(TOOL.with_name("session_status.py")), "-C", str(repo)]
    queue = [sys.executable, str(TOOL), "--queue-dir", str(tmp_path / "q"), "--poll", "0.05", "--no-precompile",
             "--", sys.executable, "-c", "pass"]
    done = subprocess.run(queue, cwd=repo, env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert not (tmp_path / "home" / "sessions").exists()  # no status file: none is created
    subprocess.run([*status_tool, "set", "--state", "building"], env=env, check=True, capture_output=True)
    done = subprocess.run(queue, cwd=repo, env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    doc = json.loads((tmp_path / "home" / "sessions" / "feature.json").read_text())
    assert doc["state"] == "green" and doc["last_suite"]["result"] == "green"
    assert doc["last_suite"]["command"].endswith("-c pass")


def test_a_failing_status_update_never_reaches_the_gate(sq, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """suite-perf's review (a): a status update that fails in any way (bad bytes, any exception) returns None, so the
    run's exit code and its history line are never lost to it."""
    tool = tmp_path / "session_status.py"
    tool.write_bytes(b"import sys; sys.stdout.buffer.write(b'\\xff\\xfe /x/path'); sys.exit(0)\n")
    session = sq.SessionStatus.__new__(sq.SessionStatus)
    session.tool, session.cwd, session.enabled = tool, tmp_path, True
    assert session._run("path") is not None  # undecodable bytes are replaced, not raised
    monkeypatch.setattr(sq.subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(ValueError("boom")))
    assert session._run("path") is None
    session.update("suite", "--result", "green")  # no exception


def test_the_sweep_spares_detached_git_maintenance(sq, tmp_path: Path) -> None:
    """suite-perf's review (b): a test's git may detach `git gc --auto`; the sweep leaves it alone. The stand-in is a
    Python process whose command line reads exactly ``git gc --auto`` (argv[0] "git", a script file named "gc")."""
    (tmp_path / "gc").write_text("import time; time.sleep(600)\n", encoding="utf-8")
    pidfile = tmp_path / "gc.pid"
    child = ("import subprocess, sys, time\n"
             f"g = subprocess.Popen(['git', 'gc', '--auto'], executable=sys.executable, cwd={str(tmp_path)!r}, "
             "start_new_session=True)\n"
             f"open({str(pidfile)!r}, 'w').write(str(g.pid))\n"
             "time.sleep(1.0)\n")
    assert sq.run_child([sys.executable, "-c", child], run_timeout=60.0, grace=1.0, track_every=0.2) == 0
    gpid = int(pidfile.read_text())
    try:
        out = subprocess.run(["ps", "-ww", "-o", "command=", "-p", str(gpid)], capture_output=True, text=True)
        assert out.stdout.strip() == "git gc --auto"
        assert _alive(gpid)
    finally:
        os.kill(gpid, signal.SIGKILL)


def test_granted_env_unit(sq) -> None:
    gib = 2**30
    assert sq.granted_env(None, "suite", 12.0, {"A": "1"}) is None
    assert sq.granted_env({"A": "1"}, "import", 3.0, {}) == {"A": "1", sq.MEMORY_BUDGET_VAR: str(3 * gib)}
    assert sq.granted_env(None, "rehearsal", 1.5, {"A": "1"}) == {"A": "1", sq.MEMORY_BUDGET_VAR: str(int(1.5 * gib))}
    kept = {sq.MEMORY_BUDGET_VAR: "123"}
    assert sq.granted_env(None, "import", 3.0, kept) is None  # the caller's value stands
    assert sq.granted_env(dict(kept), "import", 3.0, {}) == kept


def test_an_admitted_import_learns_the_memory_the_queue_granted(tmp_path: Path) -> None:
    """D-554 (pipeline-perf): the child of an import/rehearsal job sees AGENTPROV_MEMORY_BUDGET_BYTES = the granted,
    clamped reservation; a caller's value is kept; a suite gets none."""
    out = tmp_path / "seen.txt"
    dump = (f"import os; open({str(out)!r}, 'w').write(os.environ.get('AGENTPROV_MEMORY_BUDGET_BYTES', 'none'))")

    def run(*opts: str, extra: dict[str, str] | None = None) -> str:
        env = _env(cpu_budget="64", mem_gib_budget="8")
        env.pop("AGENTPROV_MEMORY_BUDGET_BYTES", None)  # not inherited from the session running the tests
        env.update(extra or {})
        done = subprocess.run([sys.executable, str(TOOL), "--queue-dir", str(tmp_path / "q"), "--poll", "0.05",
                               "--no-precompile", "--load-wait", "0", *opts, "--", sys.executable, "-c", dump],
                              capture_output=True, text=True, env=env, timeout=120)
        assert done.returncode == 0, done.stderr
        return out.read_text()

    assert run("--class", "import", "--cpu", "1", "--mem-gib", "3") == str(3 * 2**30)
    assert run("--class", "rehearsal", "--cpu", "1", "--mem-gib", "999") == str(8 * 2**30)  # clamped to the budget
    assert run("--class", "import", "--cpu", "1", "--mem-gib", "3",
               extra={"AGENTPROV_MEMORY_BUDGET_BYTES": "4242"}) == "4242"
    assert run("--cpu", "1", "--mem-gib", "3") == "none"  # suite class


def test_go_env_unit(sq) -> None:
    assert sq.go_env({"A": "1"}, 4.0, {}) == {"A": "1", sq.GO_THREADS_VAR: "4"}
    assert sq.go_env(None, 1.5, {"A": "1"}) == {"A": "1", sq.GO_THREADS_VAR: "2"}  # rounded up
    assert sq.go_env(None, 0.25, {})[sq.GO_THREADS_VAR] == "1"  # at least one thread
    kept = {sq.GO_THREADS_VAR: "7"}
    assert sq.go_env(None, 4.0, kept) is None  # the caller's value stands
    assert sq.go_env(dict(kept), 4.0, {}) == kept


def test_an_admitted_job_caps_go_threads_at_its_cpus(tmp_path: Path) -> None:
    """A queued job's child sees GOMAXPROCS = its granted CPUs (every class, clamped to the budget); a caller's value
    is kept. Go tools (gitleaks) otherwise use every core whatever --cpu reserved."""
    out = tmp_path / "seen.txt"
    dump = f"import os; open({str(out)!r}, 'w').write(os.environ.get('GOMAXPROCS', 'none'))"

    def run(*opts: str, extra: dict[str, str] | None = None) -> str:
        env = _env(cpu_budget="6", mem_gib_budget="8")
        env.pop("GOMAXPROCS", None)  # not inherited from the session running the tests
        env.update(extra or {})
        done = subprocess.run([sys.executable, str(TOOL), "--queue-dir", str(tmp_path / "q"), "--poll", "0.05",
                               "--no-precompile", "--load-wait", "0", *opts, "--", sys.executable, "-c", dump],
                              capture_output=True, text=True, env=env, timeout=120)
        assert done.returncode == 0, done.stderr
        return out.read_text()

    assert run("--class", "import", "--cpu", "4", "--mem-gib", "1") == "4"
    assert run("--class", "rehearsal", "--cpu", "99", "--mem-gib", "1") == "6"  # clamped to the budget
    assert run("--cpu", "2", "--mem-gib", "1") == "2"  # suite class too
    assert run("--class", "import", "--cpu", "4", "--mem-gib", "1", extra={"GOMAXPROCS": "3"}) == "3"
