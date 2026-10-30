"""``tools/suite_queue.py`` suite headroom: imports and rehearsals leave a queued or running suite its CPUs.

Admission is exercised directly on a queue directory under ``tmp_path`` (pids are faked as live queue processes), and
once end to end with real wrappers. Budgets come from the environment, so no assertion depends on the machine.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOL = REPO / "tools" / "suite_queue.py"
ENV = {"AGENTPROV_JOB_CPU_BUDGET": "10", "AGENTPROV_JOB_MEM_GIB_BUDGET": "512"}

CHILD = ("import os, sys, time; p, g, n = sys.argv[1:4]\n"
         "open(p, 'a').write(f'start {n}\\n')\n"
         "while not os.path.exists(g + n): time.sleep(0.05)\n"
         "open(p, 'a').write(f'end {n}\\n')")


@pytest.fixture
def sq(monkeypatch: pytest.MonkeyPatch):
    import suite_queue  # tools/ is on sys.path (conftest.py)

    monkeypatch.setattr(suite_queue, "pid_is_queue_process", lambda pid: True)
    return suite_queue


def _admission(sq, qdir: Path, job_class: str, name: str, cpu: float, enqueued_at: float, pid: int):
    return sq.Admission(qdir / "jobs", job_class, name, {"pid": pid, "enqueued_at": enqueued_at, "cpu": cpu,
                                                         "mem_gib": 1}, load_guard=False, load_wait=0, environ=ENV)


def _suite_ticket(qdir: Path, name: str, **fields: object) -> None:
    (qdir / "tickets").mkdir(parents=True, exist_ok=True)
    (qdir / "tickets" / f"{name}.json").write_text(json.dumps({"pid": 9000, "enqueued_at": 1.0, **fields}),
                                                   encoding="utf-8")


def _waiting(qdir: Path, job_class: str, name: str) -> dict:
    return json.loads((qdir / "jobs" / "waiting" / f"{job_class}-{name}.json").read_text())


def _blocked(qdir: Path, job_class: str, name: str) -> str | None:
    """The real reason: "held" in the compatible form of a headroom wait, else "blocked"."""
    record = _waiting(qdir, job_class, name)
    return record.get("held") or record["blocked"]


def test_without_a_suite_ticket_admission_is_unchanged(sq, tmp_path: Path) -> None:
    assert _admission(sq, tmp_path, "import", "a", 4, 1.0, 101).try_admit(10.0) is None
    assert _admission(sq, tmp_path, "rehearsal", "b", 6, 2.0, 102).try_admit(11.0) is None  # 4+6 of 10
    assert str(_admission(sq, tmp_path, "import", "c", 1, 3.0, 103).try_admit(12.0)).startswith("budget")


def test_a_queued_suite_leaves_imports_and_rehearsals_the_headroom(sq, tmp_path: Path) -> None:
    started = _admission(sq, tmp_path, "import", "before", 4, 1.0, 101)
    assert started.try_admit(10.0) is None  # admitted before any suite queued
    _suite_ticket(tmp_path, "s", cpu=8.0, command="pytest -n 10")
    assert (tmp_path / "jobs" / "running" / "import-before.json").exists()  # never pre-empted
    big = _admission(sq, tmp_path, "rehearsal", "big", 1, 2.0, 102)
    why = big.try_admit(11.0)
    assert str(why).startswith("suite headroom") and "4+1 of 2 CPUs" in str(why)  # the budget alone would admit it
    assert _blocked(tmp_path, "rehearsal", "big") == "headroom"
    started.leave()
    assert big.try_admit(12.0) is None  # 0+1 of 2
    assert _admission(sq, tmp_path, "import", "fits", 1, 3.0, 103).try_admit(13.0) is None  # 1+1 of 2
    assert str(_admission(sq, tmp_path, "import", "over", 1, 4.0, 104).try_admit(14.0)).startswith("suite headroom")


def test_the_suite_reservation_comes_from_its_ticket_or_its_command(sq, tmp_path: Path) -> None:
    _suite_ticket(tmp_path, "old", command="pytest -n 4")  # an older wrapper's ticket: no cpu, ceil(0.8 x 4) = 4
    assert _admission(sq, tmp_path, "import", "six", 6, 1.0, 101).try_admit(10.0) is None
    one = _admission(sq, tmp_path, "import", "one", 1, 2.0, 102)
    assert "of 6 CPUs" in str(one.try_admit(11.0))
    one.leave()
    _suite_ticket(tmp_path, "new", cpu=10.0, command="pytest -n 12")  # the largest suite present counts
    assert "of 0 CPUs" in str(_admission(sq, tmp_path, "import", "two", 1, 3.0, 103).try_admit(12.0))


def test_a_suite_is_never_held_back_by_an_import_that_yields_to_it(sq, tmp_path: Path) -> None:
    """A headroom-blocked head (and a head waiting behind it) must not hold back the suite it yields to: that would
    deadlock. FIFO among imports and rehearsals is unchanged."""
    _suite_ticket(tmp_path, "s", cpu=8.0, command="pytest -n 10")
    assert str(_admission(sq, tmp_path, "import", "old", 4, 1.0, 101).try_admit(10.0)).startswith("suite headroom")
    young = _admission(sq, tmp_path, "rehearsal", "young", 1, 2.0, 102)  # fits the headroom, but FIFO holds
    assert "an older import job waits for the suite headroom" in str(young.try_admit(11.0))
    assert _blocked(tmp_path, "rehearsal", "young") == "fifo"
    suite = _admission(sq, tmp_path, "suite", "s", 8, 3.0, 9000)
    assert suite.try_admit(12.0) is None
    assert str(young.try_admit(13.0)).startswith("an older import job waits")


def test_fifo_among_heads_is_unchanged_without_a_suite(sq, tmp_path: Path) -> None:
    assert _admission(sq, tmp_path, "import", "a", 8, 1.0, 101).try_admit(10.0) is None
    assert str(_admission(sq, tmp_path, "rehearsal", "b", 4, 2.0, 102).try_admit(11.0)).startswith("budget")
    assert "an older rehearsal job waits" in str(_admission(sq, tmp_path, "import", "c", 1, 3.0, 103).try_admit(12.0))


def _job(qdir: Path, log: Path, name: str, *opts: str) -> subprocess.Popen[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENTPROV_JOB_", "AGENTPROV_QUEUE_SLOTS"))} | ENV
    argv = [sys.executable, str(TOOL), "--queue-dir", str(qdir), "--poll", "0.05", "--no-precompile", "--load-wait",
            "0", "--no-session-status", "--label", name, *opts, "--", sys.executable, "-c", CHILD, str(log),
            str(log) + ".gate-", name]
    return subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, env=env)


def _wait_for(predicate, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition not reached"
        time.sleep(0.05)


def _started(log: Path, name: str) -> bool:
    return log.exists() and f"start {name}" in log.read_text()


def test_end_to_end_a_queued_suite_holds_an_import_and_status_says_why(tmp_path: Path) -> None:
    q, log = tmp_path / "q", tmp_path / "log.txt"
    first = _job(q, log, "first", "--cpu", "1")
    _wait_for(lambda: _started(log, "first"))
    queued = _job(q, log, "queued", "--cpu", "8")  # waits for the suite slot, not for the budget
    _wait_for(lambda: len(list((q / "tickets").glob("*.json"))) == 2)
    assert any(json.loads(p.read_text()).get("cpu") == 8.0 for p in (q / "tickets").glob("*.json"))
    imp = _job(q, log, "imp", "--class", "import", "--cpu", "4")  # 1+4 of 10 fits the budget
    _wait_for(lambda: any(p.name.startswith("import-") for p in (q / "jobs" / "waiting").glob("*.json")))
    out = subprocess.run([sys.executable, str(TOOL), "--queue-dir", str(q), "--status"], capture_output=True,
                         text=True, check=True, env=os.environ | ENV).stdout
    assert "[suite headroom: a suite is queued or running (8 CPUs)" in out
    for name in ("first", "queued"):
        Path(str(log) + ".gate-" + name).touch()
        _wait_for(lambda name=name: f"end {name}" in log.read_text())
    _wait_for(lambda: _started(log, "imp"))  # no suite left: the import starts
    Path(str(log) + ".gate-imp").touch()
    for proc in (first, queued, imp):
        _out, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, err
    text = log.read_text()
    assert text.index("start imp") > text.index("end queued")


def test_an_old_version_suite_waiting_behind_imports_gets_no_headroom(sq, tmp_path: Path) -> None:
    """Mixed versions (2026-10-21): an old wrapper's suite head waits ("fifo") behind an older import head, which the
    new wrapper held back for that suite: nothing ran for hours. The import must not hold headroom for it."""
    _suite_ticket(tmp_path, "s-old", command="pytest -n 10")  # an old wrapper's ticket: no cpu
    _suite_ticket(tmp_path, "s-behind", cpu=8.0, command="pytest -n 10")  # another suite queued behind it
    old_suite = {"pid": 9000, "job_class": "suite", "label": "regen-held-2", "enqueued_at": 2.0, "cpu": 8,
                 "mem_gib": 12, "blocked": "fifo"}  # what the old version writes while it defers to the import
    (tmp_path / "jobs" / "waiting").mkdir(parents=True, exist_ok=True)
    (tmp_path / "jobs" / "waiting" / "suite-s-old.json").write_text(json.dumps(old_suite), encoding="utf-8")
    trial = _admission(sq, tmp_path, "import", "trial", 4, 1.0, 101)
    assert trial.try_admit(10.0) is None  # admitted on the budget alone (4 of 10)
    (tmp_path / "jobs" / "waiting" / "suite-s-old.json").unlink()  # the old suite head now waits for the budget
    old_suite["blocked"] = "budget"
    (tmp_path / "jobs" / "waiting" / "suite-s-old.json").write_text(json.dumps(old_suite), encoding="utf-8")
    # a younger import queues behind that suite (global FIFO), and none of this is a cycle: the suite waits only for
    # the running trial
    assert "an older suite job waits for the budget (regen-held-2)" in str(
        _admission(sq, tmp_path, "import", "next", 1, 3.0, 102).try_admit(11.0))


OLD_VERSION = "7b7c5189~1"  # the last suite_queue.py before the suite headroom


def _old_tool(rev: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """``tools/suite_queue.py`` at ``rev``, read from git history (read-only), imported under another name."""
    shown = subprocess.run(["git", "show", f"{rev}:tools/suite_queue.py"], cwd=REPO, capture_output=True,
                           text=True, env=os.environ | {"GIT_NO_LAZY_FETCH": "1"})
    if shown.returncode != 0:
        pytest.skip(f"{rev} is not in this checkout's history")
    name = "old_suite_queue_" + "".join(c if c.isalnum() else "_" for c in rev)
    path = tmp_path / f"{name}.py"
    path.write_text(shown.stdout, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "pid_is_queue_process", lambda pid: True)
    return module


@pytest.fixture
def old_sq(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The pre-headroom tool."""
    return _old_tool(OLD_VERSION, tmp_path, monkeypatch)


PRE_STARVE = "ae3eb427~1"  # the last suite_queue.py before the starvation guard


def test_a_pre_headroom_suite_waiter_passes_imports_held_by_the_headroom(sq, old_sq, tmp_path: Path) -> None:
    """The 2026-10-21 deadlock, with the real old code: imports held by the headroom (and one queued behind them)
    are written as blocked="load", which every older version lets a suite pass, so the old suite runs first."""
    _suite_ticket(tmp_path, "s-old", command="pytest -n 10")
    trial = _admission(sq, tmp_path, "import", "trial", 4, 1.0, 101)
    assert str(trial.try_admit(10.0)).startswith("suite headroom")
    behind = _admission(sq, tmp_path, "import", "behind", 1, 2.0, 102)
    assert "waits for the suite headroom" in str(behind.try_admit(11.0))
    for name, held in (("trial", "headroom"), ("behind", "fifo")):
        record = _waiting(tmp_path, "import", name)
        assert (record["blocked"], record["held"], record["via_headroom"]) == ("load", held, True)
    old_suite = old_sq.Admission(tmp_path / "jobs", "suite", "s-old", {"pid": 9000, "enqueued_at": 3.0, "cpu": 8,
                                                                      "mem_gib": 12},
                                 load_guard=False, load_wait=0, environ=ENV)
    assert old_suite.try_admit(12.0) is None  # the old version no longer defers to them
    assert "waits for the suite headroom" in str(behind.try_admit(13.0))  # FIFO among imports still holds


def _record(qdir: Path, sub: str, name: str, **fields: object) -> None:
    (qdir / "jobs" / sub).mkdir(parents=True, exist_ok=True)
    (qdir / "jobs" / sub / f"{name}.json").write_text(json.dumps({"pid": 9100, **fields}), encoding="utf-8")


def test_status_flags_a_suspected_deadlock(sq, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    long_ago = time.time() - 3 * 3600
    _record(tmp_path, "waiting", "suite-a", job_class="suite", label="old suite", enqueued_at=long_ago,
            blocked="fifo")  # an older wrapper's record: no waiting_since
    _record(tmp_path, "waiting", "import-b", job_class="import", label="trial", enqueued_at=long_ago,
            waiting_since=long_ago, blocked="load", held="headroom", why="suite headroom: ...")
    assert sq.status(tmp_path) == 0
    out = capsys.readouterr().out
    assert "DEADLOCK?  nothing runs and 0 CPUs are reserved" in out
    assert "suite: old suite (pid 9100): fifo" in out and "import: trial (pid 9100): suite headroom: ..." in out
    assert sq.status(tmp_path, deadlock_after=4 * 3600) == 0  # not yet long enough
    assert "DEADLOCK" not in capsys.readouterr().out
    _record(tmp_path, "running", "import-c", job_class="import", label="running", cpu=2, mem_gib=8)
    assert sq.status(tmp_path) == 0  # something runs: waiting is normal
    assert "DEADLOCK" not in capsys.readouterr().out


def _adm(sq, qdir: Path, job_class: str, name: str, cpu: float, enqueued_at: float, pid: int, starve: float = 60.0):
    return sq.Admission(qdir / "jobs", job_class, name, {"pid": pid, "label": name, "enqueued_at": enqueued_at,
                                                         "cpu": cpu, "mem_gib": 1},
                        load_guard=False, load_wait=0, environ=ENV, starve_after=starve)


def test_a_starving_import_head_pauses_new_suites_until_it_starts(sq, tmp_path: Path,
                                                                 capsys: pytest.CaptureFixture[str]) -> None:
    """2026-10-21: suites back to back, and an import head too big for the headroom held 12 imports for 4 h."""
    _suite_ticket(tmp_path, "s2", cpu=8.0, command="pytest -n 10")
    s1 = _adm(sq, tmp_path, "suite", "s1", 8, 0.5, 9001)
    assert s1.try_admit(5.0) is None  # running
    big = _adm(sq, tmp_path, "import", "big", 4, 1.0, 101)
    assert str(big.try_admit(10.0)).startswith("suite headroom")
    s2 = _adm(sq, tmp_path, "suite", "s2", 8, 2.0, 9002)
    assert str(s2.try_admit(20.0)).startswith("budget")  # not starving yet (10 s of 60)
    assert str(big.try_admit(80.0)).startswith("budget")  # starving: the headroom no longer holds it, the budget does
    assert (tmp_path / "jobs" / "running" / "suite-s1.json").exists()  # never pre-empted
    s1.leave()
    why = str(s2.try_admit(90.0))
    assert why.startswith("starvation: suites paused for big") and "(import head waiting 1m20s)" in why
    record = _waiting(tmp_path, "suite", "s2")
    assert (record["blocked"], record["held"]) == ("load", "starve")  # nothing waits behind a paused suite
    assert sq.status(tmp_path) == 0
    assert "starvation: suites paused for big" in capsys.readouterr().out
    assert big.try_admit(95.0) is None  # 0+4 of 10: the import starts
    assert str(s2.try_admit(100.0)).startswith("budget")  # suites resume; s2 waits only for the budget
    young = _adm(sq, tmp_path, "import", "young", 1, 3.0, 102)
    assert "an older suite job waits for the budget" in str(young.try_admit(101.0))  # then the suite goes first


def test_no_starvation_before_the_threshold(sq, tmp_path: Path) -> None:
    _suite_ticket(tmp_path, "s", cpu=8.0, command="pytest -n 10")
    big = _adm(sq, tmp_path, "import", "big", 4, 1.0, 101, starve=3600)
    assert str(big.try_admit(10.0)).startswith("suite headroom")
    assert str(big.try_admit(3500.0)).startswith("suite headroom")
    suite = _adm(sq, tmp_path, "suite", "s", 8, 2.0, 9002, starve=3600)
    assert suite.try_admit(3600.0) is None  # the import's record says 3490 s: under the hour, the suite starts


def test_suites_do_not_pause_for_a_pre_starvation_import_head(sq, tmp_path: Path,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """r107-coverage, 2026-10-21: an import head on the pre-ae3eb427 code honours the headroom and has no override;
    new suites that paused for it ("starving" for 2 h) left nothing running. With the real old code: no pause."""
    old = _old_tool(PRE_STARVE, tmp_path, monkeypatch)
    _suite_ticket(tmp_path, "s", cpu=8.0, command="pytest -n 10")
    head = old.Admission(tmp_path / "jobs", "import", "r107", {"pid": 101, "label": "r107-coverage",
                                                              "enqueued_at": 1.0, "cpu": 4, "mem_gib": 1},
                         load_guard=False, load_wait=0, environ=ENV)
    assert str(head.try_admit(10.0)).startswith("suite headroom")
    assert "starve_override" not in _waiting(tmp_path, "import", "r107")
    suite = _adm(sq, tmp_path, "suite", "s", 8, 2.0, 9002)
    assert suite.try_admit(10.0 + 2 * 3600) is None  # two hours later: the suite runs instead of pausing
    assert str(head.try_admit(10.0 + 2 * 3600 + 1)).startswith("suite headroom")  # the old head keeps the old rule


def test_a_current_head_records_that_it_takes_the_override(sq, tmp_path: Path) -> None:
    _suite_ticket(tmp_path, "s", cpu=8.0, command="pytest -n 10")
    assert str(_adm(sq, tmp_path, "import", "big", 4, 1.0, 101).try_admit(10.0)).startswith("suite headroom")
    assert _waiting(tmp_path, "import", "big")["starve_override"] is True


PRE_HALF = "49898828"  # main before workers past 10 counted half


def test_older_waiters_read_the_smaller_suite_reservation_from_the_ticket(sq, tmp_path: Path,
                                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    """Mac Studio headroom (2026-10-28): a -n 24 suite reserves 15 of 34 CPUs, written into its ticket, so an import
    waiter of either version sees 19 CPUs of headroom and two 8-CPU imports run beside the suite."""
    old = _old_tool(PRE_HALF, tmp_path, monkeypatch)
    env = {"AGENTPROV_JOB_CPU_BUDGET": "34", "AGENTPROV_JOB_MEM_GIB_BUDGET": "512"}
    cpu = sq.default_cost("suite", ["pytest", "-n", "24"])[0]
    assert cpu == 15.0 and old.default_cost("suite", ["pytest", "-n", "24"])[0] == 20.0
    _suite_ticket(tmp_path, "s", cpu=cpu, command="pytest -n 24")
    for module, q in ((sq, tmp_path), (old, tmp_path / "old-view")):
        if q != tmp_path:  # the same ticket, read by the older version from its own copy of the queue
            (q / "tickets").mkdir(parents=True)
            (q / "tickets" / "s.json").write_text((tmp_path / "tickets" / "s.json").read_text(), encoding="utf-8")
        first = module.Admission(q / "jobs", "import", "a", {"pid": 101, "enqueued_at": 2.0, "cpu": 8, "mem_gib": 1},
                                 load_guard=False, load_wait=0, environ=env)
        second = module.Admission(q / "jobs", "import", "b", {"pid": 102, "enqueued_at": 3.0, "cpu": 8, "mem_gib": 1},
                                  load_guard=False, load_wait=0, environ=env)
        third = module.Admission(q / "jobs", "import", "c", {"pid": 103, "enqueued_at": 4.0, "cpu": 8, "mem_gib": 1},
                                 load_guard=False, load_wait=0, environ=env)
        assert first.try_admit(10.0) is None and second.try_admit(11.0) is None, module.__name__
        assert "16+8 of 19 CPUs" in str(third.try_admit(12.0)), module.__name__  # a third would exceed the headroom
