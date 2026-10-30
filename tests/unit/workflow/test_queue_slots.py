"""``tools/suite_queue.py`` slot counts (Mac Studio tuning A1): scaled with the CPU budget, ``$AGENTPROV_QUEUE_SLOTS``
overrides them, and copies from before the change share one queue directory with this one safely.

The mixed-version tests run real wrappers of both versions (the older one read from git history at ``OLD_VERSION``,
the last commit before A1) against a queue directory under ``tmp_path``, never the live queue. Budgets come from the
environment, so no assertion depends on the machine.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOL = REPO / "tools" / "suite_queue.py"
OLD_VERSION = "8c244150"  # main when A1 was built: 2 import slots, slot-0 first
ENV = {"AGENTPROV_JOB_CPU_BUDGET": "34", "AGENTPROV_JOB_MEM_GIB_BUDGET": "512"}  # the Mac Studio: 6 import slots

CHILD = ("import os, sys, time; p, g, n = sys.argv[1:4]\n"
         "open(p, 'a').write(f'start {n}\\n')\n"
         "while not os.path.exists(g + n): time.sleep(0.05)\n"
         "open(p, 'a').write(f'end {n}\\n')")


@pytest.fixture
def sq():
    import suite_queue  # tools/ is on sys.path (conftest.py)

    return suite_queue


# ------------------------------------------------------------------------------------------------ counts
@pytest.mark.parametrize(("cpu_budget", "imports", "rehearsals"), [("10", 2, 2), ("34", 6, 4), ("4", 2, 2),
                                                                   ("70", 14, 8)])
def test_slots_scale_with_the_cpu_budget(sq, cpu_budget: str, imports: int, rehearsals: int) -> None:
    env = {"AGENTPROV_JOB_CPU_BUDGET": cpu_budget, "AGENTPROV_JOB_MEM_GIB_BUDGET": "64"}
    assert (sq.slots("suite", env), sq.slots("import", env), sq.slots("rehearsal", env)) == (1, imports, rehearsals)


def test_the_override_wins_and_is_checked(sq) -> None:
    env = {**ENV, "AGENTPROV_QUEUE_SLOTS": " import=8 , rehearsal=1 "}
    assert (sq.slots("suite", env), sq.slots("import", env), sq.slots("rehearsal", env)) == (1, 8, 1)
    assert sq.slots("rehearsal", {**ENV, "AGENTPROV_QUEUE_SLOTS": "import=3"}) == 4  # the other class keeps its default
    for bad in ("suite=2", "import=0", "import=65", "import=x", "import", "import=2,import=3", "imports=2"):
        with pytest.raises(sq.BudgetError):
            sq.slots("import", {**ENV, "AGENTPROV_QUEUE_SLOTS": bad})


def test_a_bad_override_is_refused_at_start(tmp_path: Path) -> None:
    env = {**os.environ, **ENV, "AGENTPROV_QUEUE_SLOTS": "suite=3"}
    done = subprocess.run([sys.executable, str(TOOL), "--queue-dir", str(tmp_path), "--status"], env=env,
                          capture_output=True, text=True)
    assert done.returncode == 2 and "AGENTPROV_QUEUE_SLOTS" in done.stderr


def test_the_highest_slot_is_tried_first_and_holders_match(sq, tmp_path: Path) -> None:
    locks, holders = sq.slot_locks(tmp_path, "import", ENV), sq.holder_files(tmp_path, "import", ENV)
    assert [p.name for p in locks] == [f"slot-{i}.lock" for i in (5, 4, 3, 2, 1, 0)]
    assert [p.name for p in holders] == [f"holder-{i}.json" for i in (5, 4, 3, 2, 1, 0)]
    (tmp_path / "holder-9.json").write_text("{}")  # written under another count
    assert sq.all_holder_files(tmp_path, "import")[-1].name == "holder-9.json"


# ------------------------------------------------------------------------------------------------ mixed versions
@pytest.fixture
def old_tool(tmp_path: Path) -> Path:
    """The pre-A1 wrapper as a file named ``suite_queue.py`` (the stale-ticket check matches that name)."""
    shown = subprocess.run(["git", "show", f"{OLD_VERSION}:tools/suite_queue.py"], cwd=REPO, capture_output=True,
                           text=True, env=os.environ | {"GIT_NO_LAZY_FETCH": "1"})
    if shown.returncode != 0:
        pytest.skip(f"{OLD_VERSION} is not in this checkout's history")
    path = tmp_path / "old" / "suite_queue.py"
    path.parent.mkdir()
    path.write_text(shown.stdout, encoding="utf-8")
    return path


class Jobs:
    def __init__(self, tmp_path: Path, old_tool: Path) -> None:
        self.q, self.log, self.old = tmp_path / "q", tmp_path / "log.txt", old_tool
        self.procs: dict[str, subprocess.Popen[str]] = {}

    def start(self, name: str, old: bool) -> None:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENTPROV_JOB_", "AGENTPROV_QUEUE"))} | ENV
        tool = self.old if old else TOOL
        before = self.tickets()
        argv = [sys.executable, str(tool), "--queue-dir", str(self.q), "--poll", "0.05", "--no-precompile",
                "--load-wait", "0", "--no-session-status", "--class", "import", "--cpu", "1", "--label", name, "--",
                sys.executable, "-c", CHILD, str(self.log), str(self.log) + ".gate-", name]
        self.procs[name] = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, env=env)
        wait_for(lambda: self.tickets() > before)  # ticket names are times: one at a time keeps the order

    def tickets(self) -> int:
        folder = self.q / "jobs" / "import" / "tickets"
        return len(list(folder.glob("*.json"))) if folder.is_dir() else 0

    def lines(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def started(self, name: str) -> bool:
        return f"start {name}" in self.lines()

    def release(self, name: str) -> None:
        Path(str(self.log) + ".gate-" + name).touch()
        assert self.procs[name].wait(timeout=60) == 0, self.procs[name].stderr.read() if self.procs[name].stderr else ""

    def slot_of(self, name: str) -> int:
        pid = self.procs[name].pid
        for path in (self.q / "jobs" / "import").glob("holder-*.json"):
            if json.loads(path.read_text()).get("pid") == pid:
                return int(path.stem.removeprefix("holder-"))
        raise AssertionError(f"{name} holds no slot")

    def stop(self) -> None:
        for name, proc in self.procs.items():
            Path(str(self.log) + ".gate-" + name).touch()
            if proc.poll() is None:
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()


def wait_for(predicate, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition not reached (a deadlock?)"
        time.sleep(0.05)


@pytest.fixture
def jobs(tmp_path: Path, old_tool: Path):
    j = Jobs(tmp_path, old_tool)
    yield j
    j.stop()


def test_old_waiters_behind_new_jobs_wait_their_turn_and_then_run(jobs: Jobs) -> None:
    """Four new jobs take slots 5..2; two old waiters behind them are not heads in their own (2-slot) view, so they
    wait, and each runs on slot 0 or 1 once it is one of the first two tickets."""
    for name in ("n1", "n2", "n3", "n4"):
        jobs.start(name, old=False)
    wait_for(lambda: all(jobs.started(n) for n in ("n1", "n2", "n3", "n4")))
    assert sorted(jobs.slot_of(n) for n in ("n1", "n2", "n3", "n4")) == [2, 3, 4, 5]
    jobs.start("o1", old=True)
    jobs.start("o2", old=True)
    time.sleep(1.0)
    assert not jobs.started("o1") and not jobs.started("o2")  # the FIFO skip: not heads yet in the old view
    jobs.release("n1")
    jobs.release("n2")
    time.sleep(0.5)
    assert not jobs.started("o1")  # tickets n3, n4, o1, o2: o1 is third
    jobs.release("n3")
    wait_for(lambda: jobs.started("o1"))
    assert jobs.slot_of("o1") in (0, 1) and not jobs.started("o2")
    jobs.release("n4")
    wait_for(lambda: jobs.started("o2"))
    assert jobs.slot_of("o2") in (0, 1) and jobs.slot_of("o2") != jobs.slot_of("o1")
    jobs.release("o1")
    jobs.release("o2")


def test_new_jobs_run_beside_old_holders_on_the_other_slots(jobs: Jobs) -> None:
    """Two old holders take slots 0 and 1; four new jobs behind them start at once on slots 5..2 (six in all). An old
    waiter behind them starts on a freed low slot once it is one of the first two tickets."""
    for name in ("o1", "o2"):
        jobs.start(name, old=True)
    wait_for(lambda: jobs.started("o1") and jobs.started("o2"))
    assert sorted((jobs.slot_of("o1"), jobs.slot_of("o2"))) == [0, 1]
    for name in ("n1", "n2", "n3", "n4"):
        jobs.start(name, old=False)
    wait_for(lambda: all(jobs.started(n) for n in ("n1", "n2", "n3", "n4")))
    assert sorted(jobs.slot_of(n) for n in ("n1", "n2", "n3", "n4")) == [2, 3, 4, 5]
    assert not any(line.startswith("end") for line in jobs.lines())  # six at once
    jobs.start("o3", old=True)
    time.sleep(0.5)
    assert not jobs.started("o3")  # both of its slots are taken
    jobs.release("o1")
    time.sleep(0.5)
    assert not jobs.started("o3")  # tickets o2, n1..n4, o3: slot 0 or 1 is free, but o3 is not a head in its view
    for name in ("n1", "n2", "n3", "n4"):
        jobs.release(name)
    wait_for(lambda: jobs.started("o3"))  # tickets o2, o3
    assert jobs.slot_of("o3") in (0, 1)
    for name in ("o2", "o3"):
        jobs.release(name)
