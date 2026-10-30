"""Machine-wide FIFO queue for full test-suite runs: one full suite at a time across all sessions and worktrees.

Usage (proposal D-403; AGENTS.md push discipline)::

    uv run python tools/suite_queue.py -- pytest -n 10 --dist loadgroup -p no:randomly
    uv run python tools/suite_queue.py --status

Several sessions on one machine each run the full suite as their merge gate. Run concurrently, they slow each other
down and push the load-sensitive tests (rlimits, worker isolation, wall timeouts) towards their limits. This wrapper
runs its command only when it holds the queue, so suites run one after another in arrival order.

* **Queue.** Each waiter writes a ticket ``<queue-dir>/tickets/<time_ns>-<pid>.json``. The oldest *live* ticket runs.
  The queue directory is ``$AGENTPROV_SUITE_QUEUE_DIR``, else ``$AGENTPROV_HOME/locks/suite-queue``, else
  ``~/.agentprov/locks/suite-queue``.
* **Mutual exclusion.** The holder also takes an exclusive ``flock`` on ``<queue-dir>/suite.lock``. The kernel releases
  it when the holder dies, however it dies, so a crashed holder never blocks the queue.
* **Orphans.** ``holder.json`` records the suite's process group and its leader's start time and command line
  (``ps -o lstart= -o command=``). A later holder waits for, or after its run timeout stops, a dead holder's group only
  while that leader is still the same process: process-group ids are recycled pids, and an unrelated group that
  reused the id is never waited for or signalled. A record without the identity counts as gone.
* **Stale tickets.** A ticket whose pid is gone, or whose pid now belongs to a process that is not this tool (pid
  reuse), is removed by the next waiter that sees it.
* **Waiting display.** The waiter shows its position, the running holder (label, branch, worktree, elapsed time) and
  its own wait time. On a terminal it rewrites one line; otherwise it prints a line every minute.
* **Timeouts.** ``--wait-timeout`` gives up waiting (exit 75, ``EX_TEMPFAIL``). ``--run-timeout`` (default 2 h) stops
  a hung suite: SIGTERM to its process group, SIGKILL after a grace period, then exit 124 as ``timeout(1)`` does.
* **Signals.** SIGINT, SIGTERM and SIGHUP are forwarded to the child's process group; the ticket is always removed.
* **History.** Each finished run appends one line to ``<queue-dir>/history.jsonl``: start, end, wall time, waited
  time, exit code, label, and (D-427) the admission time and the CPU and memory reservation. It is local to the machine and holds no test output.

The child runs in its own session (process group), so a timeout or an interrupt reaches pytest, its xdist workers and
their ``agentprov.worker`` children. The command's exit code is returned unchanged (128 + n for a signal n).

Targeted runs do not use the queue (D-404). They are short and mostly single-process, and putting them behind a
full suite would stall the edit-test loop of every session. ``--targeted`` runs the command at once, outside the queue,
with the same environment.

**Bytecode** (D-406). The Claude Code harness sets ``PYTHONDONTWRITEBYTECODE=1`` for session processes, so every run
recompiled every module and re-ran pytest's assertion rewriting. The child here runs without that variable and with
``PYTHONPYCACHEPREFIX`` set to ``$AGENTPROV_PYCACHE_PREFIX``, else ``~/.cache/agentprov/pycache``. The cache mirrors
each source file's absolute path, so worktrees never share entries, ``.pyc`` files are validated against the source's
mtime and size, and nothing is written into a source tree (``tests/golden/**`` is un-ignored by ``.gitignore``, so an
in-tree ``__pycache__`` there would dirty the checkout). ``agentprov.worker`` processes run ``python -I -B``, which
ignores both variables; they gain nothing from this and are unchanged. ``--keep-bytecode-env`` passes the environment
through untouched. A full run whose cache has grown past ``--pycache-max-mb`` clears it first, while it holds the queue;
``--clear-pycache`` clears it and exits.

**Job classes and the machine budget** (D-427, agreed with suite-perf; design ``docs/reports/workflow-tools/design.md``
§5). ``--class`` picks a FIFO lane: ``suite`` (the default, 1 slot, everything above unchanged), ``import`` (imports
and trial imports into scratch corpora) and ``rehearsal`` (rehearsals, ``recompute``, ``derive``, ``verify`` in
scratch). The new classes live under ``<queue-dir>/jobs/<class>/`` (``tickets/``, ``slot-<i>.lock``,
``holder-<i>.json``, ``history.jsonl``); the suite class keeps its files where they were.

* **Slots** (Mac Studio tuning A1, 2026-10-28). A slot only caps how many jobs of a class run at once; the budget below
  decides admission. ``suite`` always has 1. ``import`` has max(2, ⌊CPU budget / 5⌋) and ``rehearsal``
  max(2, ⌊CPU budget / 8⌋): 6 and 4 on the Mac Studio (budget 34), 2 and 2 on the M2 Max (budget 10, as before).
  ``$AGENTPROV_QUEUE_SLOTS`` (for example ``import=8,rehearsal=4``; integers 1 to 64; not ``suite``) overrides them.
  **Mixed versions:** copies from before this change have 2 slots (``slot-0``, ``slot-1``) and count the first 2
  tickets as heads. This version takes its highest free slot first, so older waiters find slots 0 and 1 free for as
  long as possible; a slot is an ``flock``, so two versions never hold one slot. An older waiter behind more than one
  ticket waits until it is one of the first two while younger, newer waiters may run: FIFO is skipped, nothing
  deadlocks (``tests/unit/workflow/test_queue_slots.py`` runs both versions on one queue directory). ``--status`` reads
  every ``holder-*.json``, so it shows holders on slots its own count does not cover.

* **Budget.** A job declares a CPU and memory *reservation* (``--cpu``, ``--mem-gib``; not a measurement). Defaults:
  a suite with ``-n`` N reserves ⌈0.8 · min(N, 10) + 0.5 · max(0, N − 10)⌉ CPUs (``auto`` = every CPU, none or 0 = 1
  worker; measured: the ``-n 10`` gate averages 6.5-7.0 CPUs with short peaks above 10,
  ``docs/reports/suite-perf/results.md``; workers past 10 count half (Mac Studio headroom, 2026-10-28): a ``-n 24``
  suite there reserves 15, not 20, so two 8-CPU imports fit beside it in the 34-CPU budget. Measured at 0ce598ac:
  alone it averaged 17.9 CPUs (7.6 min); beside 16 busy processes (two 8-CPU imports) 16.1 CPUs in 6.7 min, beside 24
  11.7 CPUs in 8.4 min, every test passing each time; ``-n 24`` takes no less wall time than ``-n 10``) and 1.5 GiB
  per CPU; an import or
  rehearsal reserves its ``--workers``/``--jobs`` value, or for 0 or none the CLI's host default
  (min(CPUs, ⌊0.75 · RAM / 4 GiB⌋)), and 4 GiB per worker (the per-job cap of D-55). ``--cpu N`` alone also scales
  the memory: N times the class's GiB per CPU. The
  budget is ``ncpu - 2`` CPUs and 75 % of physical memory (``$AGENTPROV_JOB_CPU_BUDGET``,
  ``$AGENTPROV_JOB_MEM_GIB_BUDGET``, each a finite number above 0 or the tool refuses to run; with the memory size
  unknown, 4 GiB per budgeted CPU); a reservation larger than the budget is clamped to it and so runs alone.
  ``--cpu`` and ``--mem-gib`` take finite numbers, 0 or above.
* **Admission.** A class head that holds a slot starts when its reservation fits beside the running ones and no older
  head of any class is still waiting for the budget (global FIFO among heads: a small import never starves a queued
  suite). A head held only by the load guard holds nobody back. A live suite holder without a reservation (an
  older wrapper during the rollout) counts with the default suite reservation.
* **Suite headroom.** While any suite ticket is queued or running, an ``import`` or ``rehearsal`` head starts only if
  the CPUs reserved by running imports and rehearsals, plus its own, stay within the budget minus the suite's
  reservation (its ticket's ``cpu``, else the default for its command; ``-n 10`` on the M2 Max: 8 of 10, so 2 CPUs;
  ``-n 24`` on the Mac Studio: 15 of 34, so 19 CPUs). With no suite
  ticket nothing changes; running jobs are never pre-empted. A suite therefore never waits behind an older import or
  rehearsal head (they yield to it; otherwise a head held by the headroom and the suite would wait for each other),
  while FIFO among imports and rehearsals is unchanged. ``--status`` shows the reason. A suite head that waits
  behind an import or rehearsal (``blocked: fifo``: an older version of this tool, still global FIFO) gets no
  headroom, or each would wait for the other. A wait that traces back to the headroom is written as
  ``blocked: load`` with the real reason in ``held`` (and ``via_headroom``): ``load`` is the tag every older version
  lets a suite pass, so an old suite waiter never defers to an import that defers to it; this version reads
  ``held``. ``--status`` prints ``DEADLOCK?`` when nothing runs, 0 CPUs are reserved and every head has waited over
  ``--deadlock-minutes`` (15).
* **Starvation.** An import or rehearsal head that has waited ``--starve-minutes`` (60) on the headroom or the
  budget ignores the headroom, and no new suite starts until it has; the running suite is never pre-empted. The paused
  suite's record is written as ``blocked: load`` (``held: starve``), so nothing, an older version included, waits
  behind it. Suites pause only for a head whose record has ``starve_override`` (written by this version on): an older
  waiter still honours the headroom, so pausing for it would deadlock. ``--status`` prints ``starvation: suites paused for <label>``. The decision is taken under ``<queue-dir>/jobs/admit.lock``; running reservations are
  ``<queue-dir>/jobs/running/*.json``, each holding the **wrapper's** pid, pruned with the same pid-reuse check as
  tickets, so a reservation comes back exactly when its slot lock does.
* **Load guard** (``import`` and ``rehearsal`` only). If the 1-minute load average minus the CPUs reserved by running
  queued jobs is above half the CPUs (load from work outside the queue), a head waits up to ``--load-wait`` (default
  600 s), then starts anyway and says so.
* **Granted memory.** An admitted ``import`` or ``rehearsal`` job gets ``AGENTPROV_MEMORY_BUDGET_BYTES`` = its granted
  (clamped) memory reservation in bytes, unless the caller set it; a pipeline parent sizes its admission budget to it
  (pipeline-perf D-554). Suites get nothing.
* **Granted CPUs for Go tools.** Every admitted job gets ``GOMAXPROCS`` = its granted CPUs (rounded up), unless the
  caller set it, so a Go tool such as gitleaks keeps to its ``--cpu`` reservation instead of one thread per core.
* **Environment.** D-406 and D-407 are for test runs: ``import`` and ``rehearsal`` run with the session's environment
  unchanged and without precompiling (corpus-producing runs see exactly what the session sees).
* **Session status.** For a queued suite, the session's status file (``tools/session_status.py``) follows the queue:
  ``waiting-for-slot`` on enqueue, ``suite-running`` on start, then the result. Only an existing status file is
  updated; ``--no-session-status`` turns this off.
* ``--status`` shows every class, the running reservations and the budget; a holder's own ticket is shown as
  ``running`` and is not counted as a waiter.
* **Priority** (``--before-head --reason TEXT``): for a sanctioned jump, such as a gate-integrity fix approved by the
  orchestrator. The ticket is named just before the class's first ordinary waiter and after any earlier priority
  jobs (FIFO among them), so it runs after the running holder and the priority jobs already queued; it takes that
  place in the budget's FIFO too. The reason is recorded in the ticket and in
  ``history.jsonl``. Renaming a waiting ticket by hand deadlocks (the waiter rewrites its own ticket), which is why
  this is a flag.

**Precompiled sources for the workers** (D-407). Before a queued or targeted run, the wrapper runs
``python -m compileall -q --invalidation-mode checked-hash`` on ``src/agentprov`` of the current checkout, and on
nothing else. The ``.pyc`` files go into the git-ignored ``src/agentprov/**/__pycache__`` (``.gitignore`` line
``__pycache__/``), so the tree stays clean. ``checked-hash`` makes a file valid only for the source bytes it was built
from, so a rebase or a checkout can never serve a stale one. Workers keep ``python -I -B`` (G.4.2): they read these
files and never write any. This happens only in this wrapper, never in the product. ``--no-precompile`` skips it.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import math
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

EX_TEMPFAIL = 75
EX_TIMEOUT = 124
TOOL_NAME = "suite_queue.py"
#: Job classes and their slot counts before Mac Studio tuning A1 (D-427), still the minimum; see :func:`slots`.
CLASSES: dict[str, int] = {"suite": 1, "import": 2, "rehearsal": 2}
#: CPUs of the budget per slot (A1): import max(2, budget // 5), rehearsal max(2, budget // 8)
CPUS_PER_SLOT: dict[str, int] = {"import": 5, "rehearsal": 8}
SLOTS_VAR = "AGENTPROV_QUEUE_SLOTS"
GIB = 2**30


def pycache_prefix(environ: dict[str, str] | os._Environ[str] = os.environ) -> Path:
    if environ.get("AGENTPROV_PYCACHE_PREFIX"):
        return Path(environ["AGENTPROV_PYCACHE_PREFIX"])
    return Path.home() / ".cache" / "agentprov" / "pycache"


def child_env(environ: dict[str, str] | os._Environ[str], prefix: Path) -> dict[str, str]:
    """The suite's environment: bytecode on, cached under ``prefix`` (outside every source tree)."""
    env = {k: v for k, v in environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
    env["PYTHONPYCACHEPREFIX"] = str(prefix)
    return env


def tree_bytes(root: Path) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            with contextlib.suppress(OSError):
                total += os.lstat(os.path.join(dirpath, name)).st_size
    return total


def clear_pycache(prefix: Path) -> None:
    """Remove the bytecode cache; refuses anything that does not look like one (a guard against a wrong prefix).

    Other sessions' interpreters write into the shared cache at any time, so the tree is first renamed aside (atomic;
    new writes start a fresh tree) and then removed, tolerating files that a writer still drops into it. What cannot
    be removed now is removed by a later clear (BF-2)."""
    for old in prefix.parent.glob(f"{prefix.name}.trash-*") if prefix.parent.is_dir() else []:
        shutil.rmtree(old, ignore_errors=True)
    if not prefix.exists():
        return
    if prefix.is_symlink() or not prefix.is_dir() or prefix == Path.home() or len(prefix.resolve().parts) < 3:
        raise SystemExit(f"suite-queue: refusing to clear {prefix}: not a plain cache directory")
    for _dirpath, _dirs, files in os.walk(prefix):
        if any(".pyc" not in f for f in files):  # atomic-write temporaries are "<name>.pyc.<id>"
            raise SystemExit(f"suite-queue: refusing to clear {prefix}: it holds files other than .pyc")
    aside = prefix.with_name(f"{prefix.name}.trash-{os.getpid()}-{time.time_ns()}")
    try:
        os.rename(prefix, aside)
    except OSError:
        return  # another run is clearing it right now
    shutil.rmtree(aside, ignore_errors=True)


def precompile(checkout: Path) -> bool:
    """D-407: hash-checked ``.pyc`` files for ``<checkout>/src/agentprov`` only. An optimisation, so a failure (a module
    that does not compile, a missing interpreter) is reported and the suite runs anyway; True when it succeeded."""
    package = checkout / "src" / "agentprov"
    if not (package / "__init__.py").is_file():
        return False
    try:
        done = subprocess.run(
            [sys.executable, "-m", "compileall", "-q", "--invalidation-mode", "checked-hash", str(package)],
            env={k: v for k, v in os.environ.items() if k != "PYTHONPYCACHEPREFIX"}, capture_output=True, text=True,
            timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        sys.stderr.write(f"suite-queue: precompile skipped ({type(exc).__name__}); the suite runs without it\n")
        return False
    if done.returncode != 0:
        sys.stderr.write(f"suite-queue: precompile of {package} failed (exit {done.returncode}); the suite runs anyway "
                         "and reports the module that does not compile\n")
        return False
    return True


def _toplevel(cwd: Path) -> Path | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True,
                             timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return Path(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None


def queue_dir(environ: dict[str, str] | os._Environ[str] = os.environ) -> Path:
    if environ.get("AGENTPROV_SUITE_QUEUE_DIR"):
        return Path(environ["AGENTPROV_SUITE_QUEUE_DIR"])
    home = Path(environ["AGENTPROV_HOME"]) if environ.get("AGENTPROV_HOME") else Path.home() / ".agentprov"
    return home / "locks" / "suite-queue"


def _write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def jobs_root(qdir: Path) -> Path:
    """Where the job classes and the budget live: inside the suite queue directory, so one root isolates them all."""
    return qdir / "jobs"


def class_dir(qdir: Path, job_class: str) -> Path:
    return qdir if job_class == "suite" else jobs_root(qdir) / job_class


def slot_override(environ: dict[str, str] | os._Environ[str] = os.environ) -> dict[str, int]:
    """``$AGENTPROV_QUEUE_SLOTS`` as ``{class: slots}``; raises :class:`BudgetError` for anything but
    ``import=N`` / ``rehearsal=N`` items (N from 1 to 64), comma-separated."""
    raw = environ.get(SLOTS_VAR, "").strip()
    out: dict[str, int] = {}
    for item in filter(None, (part.strip() for part in raw.split(","))):
        name, _eq, value = item.partition("=")
        name, value = name.strip(), value.strip()
        if name not in CPUS_PER_SLOT or not value.isdigit() or not 1 <= int(value) <= 64 or name in out:
            raise BudgetError(f"${SLOTS_VAR} takes import=N,rehearsal=N with N from 1 to 64 (the suite class always "
                              f"has 1 slot), not {raw[:60]!r}")
        out[name] = int(value)
    return out


def slots(job_class: str, environ: dict[str, str] | os._Environ[str] = os.environ) -> int:
    """How many jobs of ``job_class`` run at once (A1; module docstring, "Slots")."""
    if job_class == "suite":
        return 1
    override = slot_override(environ).get(job_class)
    if override is not None:
        return override
    return max(CLASSES[job_class], int(budget(environ)[0]) // CPUS_PER_SLOT[job_class])


def slot_locks(cdir: Path, job_class: str, environ: dict[str, str] | os._Environ[str] = os.environ) -> list[Path]:
    """The class's slot locks in the order this version tries them: the highest first (A1, mixed versions)."""
    return [cdir / "suite.lock"] if job_class == "suite" else [cdir / f"slot-{i}.lock" for i in
                                                              reversed(range(slots(job_class, environ)))]


def holder_files(cdir: Path, job_class: str, environ: dict[str, str] | os._Environ[str] = os.environ) -> list[Path]:
    """The holder records matching :func:`slot_locks`, in the same order."""
    return [cdir / "holder.json"] if job_class == "suite" else [cdir / f"holder-{i}.json" for i in
                                                               reversed(range(slots(job_class, environ)))]


def all_holder_files(cdir: Path, job_class: str) -> list[Path]:
    """Every holder record present, whatever slot count wrote it (another version or another override)."""
    if job_class == "suite":
        return [cdir / "holder.json"]
    present = {p for p in cdir.glob("holder-*.json") if p.stem.removeprefix("holder-").isdigit()}
    return sorted(present | set(holder_files(cdir, job_class)), key=lambda p: int(p.stem.removeprefix("holder-")))


def ncpu() -> int:
    return os.cpu_count() or 1


class BudgetError(ValueError):
    """A budget variable that is not a finite number above 0."""


def _budget_var(environ: dict[str, str] | os._Environ[str], name: str) -> float | None:
    raw = environ.get(name)
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not math.isfinite(value) or value <= 0:  # "inf", "nan", 0 or below would switch the budget off (GR-30)
        raise BudgetError(f"${name} must be a finite number above 0, not {raw[:40]!r}")
    return value


def budget(environ: dict[str, str] | os._Environ[str] = os.environ) -> tuple[float, float]:
    """(CPUs, GiB) that queued jobs may reserve together: ``ncpu - 2`` and 75 % of physical memory by default; with
    the memory size unknown, 4 GiB per budgeted CPU. Raises :class:`BudgetError` for a non-finite or non-positive
    ``$AGENTPROV_JOB_CPU_BUDGET`` or ``$AGENTPROV_JOB_MEM_GIB_BUDGET``."""
    cpu = _budget_var(environ, "AGENTPROV_JOB_CPU_BUDGET") or float(max(1, ncpu() - 2))
    mem = _budget_var(environ, "AGENTPROV_JOB_MEM_GIB_BUDGET")
    if mem is not None:
        return cpu, mem
    ram = physical_gib()
    return cpu, 0.75 * ram if ram else 4.0 * cpu


def _option_int(command: list[str], names: tuple[str, ...]) -> int | str | None:
    for i, token in enumerate(command):
        for name in names:
            value = None
            if token == name and i + 1 < len(command):
                value = command[i + 1]
            elif token.startswith(name + "=") or (len(name) == 2 and token.startswith(name) and len(token) > 2):
                value = token[len(name) + 1:] if token.startswith(name + "=") else token[len(name):]
            if value is not None:
                return int(value) if value.isdigit() else value
    return None


def physical_gib() -> float | None:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / GIB
    except (ValueError, OSError, AttributeError):
        return None


def host_default_workers() -> int:
    """A local copy of the CLI's host default for ``--jobs 0``: min(CPUs, ⌊0.75 · RAM / 4 GiB⌋), at least 1."""
    ram = physical_gib()
    by_memory = int(0.75 * ram // 4) if ram else ncpu()
    return max(1, min(ncpu(), by_memory))


def default_cost(job_class: str, command: list[str]) -> tuple[float, float]:
    """The default reservation (CPUs, GiB) of a command: see the module docstring."""
    if job_class == "suite":
        n = _option_int(command, ("-n", "--numprocesses"))
        workers = ncpu() if n in ("auto", "logical") else max(1, n) if isinstance(n, int) else 1
        # Measured (docs/reports/suite-perf/results.md): the -n 10 gate averages 6.5-7.0 CPUs (2,191-2,454 CPU s in
        # 5.6-6.1 min), with short peaks above 10 when pool groups start. 0.8 per worker sits between the two.
        # Workers past 10 count half: the suite is tail-bound (the serial group) and the extra workers land on the
        # efficiency cores. On the Mac Studio -n 24 averaged 17.9 CPUs alone and 16.1 beside two 8-CPU imports, with no
        # loss of wall time or tests (0ce598ac); it takes no less wall time than -n 10.
        cpu = float(max(1, math.ceil(0.8 * min(workers, 10) + 0.5 * max(0, workers - 10))))
        return cpu, 1.5 * cpu  # memory: the tree's total RSS was not measured (largest process 2.2-2.8 GB)
    jobs = _option_int(command, ("--workers", "--jobs"))
    cpu = float(jobs) if isinstance(jobs, int) and jobs > 0 else float(host_default_workers())  # absent or 0
    return cpu, 4.0 * cpu


MEMORY_BUDGET_VAR = "AGENTPROV_MEMORY_BUDGET_BYTES"


def granted_env(env: dict[str, str] | None, job_class: str, mem_gib: float,
                environ: dict[str, str] | os._Environ[str] = os.environ) -> dict[str, str] | None:
    """The child's environment with the memory the queue granted an ``import`` or ``rehearsal`` job, as
    ``AGENTPROV_MEMORY_BUDGET_BYTES`` (the granted, clamped ``--mem-gib`` × 2^30), so a pipeline parent sizes its own
    admission budget (D-554) to what the queue gave it rather than to 0.75 · RAM. A value the caller already set is
    kept; suite jobs get nothing. ``None`` still means "the unchanged environment"."""
    base = env if env is not None else environ
    if job_class == "suite" or MEMORY_BUDGET_VAR in base:
        return env
    return {**base, MEMORY_BUDGET_VAR: str(int(mem_gib * 2**30))}


GO_THREADS_VAR = "GOMAXPROCS"


def go_env(env: dict[str, str] | None, cpu: float,
           environ: dict[str, str] | os._Environ[str] = os.environ) -> dict[str, str] | None:
    """The child's environment with ``GOMAXPROCS`` = the job's granted CPUs (rounded up, at least 1), for every
    class. A Go tool (gitleaks) otherwise runs one thread per core whatever ``--cpu`` reserved: a 4-CPU gitleaks
    triage measured about 2,640 % CPU on the 36-core host (2026-10-28). A value the caller already set is kept.
    ``None`` still means "the unchanged environment"."""
    base = env if env is not None else environ
    if GO_THREADS_VAR in base:
        return env
    return {**base, GO_THREADS_VAR: str(max(1, math.ceil(cpu)))}


def reservation(job_class: str, command: list[str], cpu: float | None, mem_gib: float | None) -> tuple[float, float]:
    """The (CPUs, GiB) a job reserves: the defaults of :func:`default_cost`, with ``--cpu`` and ``--mem-gib`` applied.
    ``--cpu`` alone also scales the memory, at the class's GiB per CPU (a ``--cpu 4`` suite reserves 6 GiB, not the
    18 GiB of the default 12 CPUs)."""
    default_cpu, default_mem = default_cost(job_class, command)
    if cpu is not None:
        default_mem = default_mem / default_cpu * cpu
        default_cpu = cpu
    return default_cpu, mem_gib if mem_gib is not None else default_mem


#: an import or rehearsal head that has waited this long on the headroom or the budget pauses new suites
STARVE_AFTER = 60 * 60.0


class Admission:
    """The budget decision for one job (D-427): call :meth:`try_admit` while holding a slot; :meth:`leave` always."""

    def __init__(self, root: Path, job_class: str, name: str, record: dict[str, Any], *, load_guard: bool,
                 load_wait: float, environ: dict[str, str] | os._Environ[str] = os.environ,
                 starve_after: float = STARVE_AFTER) -> None:
        self.root, self.name, self.record = root, f"{job_class}-{name}.json", dict(record, job_class=job_class)
        self.cpu_budget, self.mem_budget = budget(environ)
        self.record["cpu"] = min(float(record["cpu"]), self.cpu_budget)
        self.record["mem_gib"] = min(float(record["mem_gib"]), self.mem_budget)
        self.load_guard, self.load_wait = load_guard, load_wait
        self.starve_after = starve_after
        self.load_since: float | None = None
        self.waiting_since: float | None = None  # since it first waited as a head (--status: deadlock)
        self.admitted_at: float | None = None
        for sub in ("running", "waiting"):
            (root / sub).mkdir(parents=True, exist_ok=True)

    def _records(self, sub: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for path in sorted((self.root / sub).glob("*.json")):
            data = _read_json(path)
            pid = data.get("pid") if data else None
            if data is None or not isinstance(pid, int) or not pid_is_queue_process(pid):
                if data is None and time.time() - _mtime(path) < 10:
                    continue  # being written right now
                with contextlib.suppress(FileNotFoundError):
                    path.unlink()
                continue
            if path.name != self.name:
                out.append(data)
        return out

    def try_admit(self, now: float) -> str | None:
        """None when admitted (the reservation is recorded), else why the job still waits."""
        fd = os.open(self.root / "admit.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            running, waiting = self._records("running"), self._records("waiting")
            running += self._unrecorded_suite(running)
            is_suite = self.record["job_class"] == "suite"
            # Only heads that wait for the budget (or behind one) hold younger heads back; a head held only by the
            # load guard does not, so it can never stall a queued suite (the merge gate). A suite is never held back
            # by an import or rehearsal head: while it is queued they yield to it (suite headroom), and waiting for
            # each other would deadlock.
            older = [w for w in waiting if w.get("enqueued_at", now) < self.record["enqueued_at"]
                     and _tag(w) not in ("load", "starve") and (not is_suite or w.get("job_class") == "suite")]
            cpu = sum(float(r.get("cpu", 0)) for r in running)
            mem = sum(float(r.get("mem_gib", 0)) for r in running)
            # A suite head that waits behind an import or rehearsal head ("fifo") runs an older version of this tool
            # (from before 7b7c5189, still global FIFO): holding the headroom for it would make each wait for the
            # other forever (regen-held-2 and the 10m trial, 2026-10-21). It gets no headroom; it runs after them.
            old_suite = any(w.get("job_class") == "suite" and w.get("blocked") == "fifo" for w in waiting)
            # Starvation (2026-10-21: one import head too big for the headroom held 12 imports for 4 h while suites
            # ran back to back): an import or rehearsal head that has waited --starve-minutes ignores the headroom,
            # and no new suite starts until it has (the running suite is never pre-empted).
            # Only a head that writes starve_override (this version or later) takes the override; a suite pausing for
            # an older waiter, which still honours the headroom, would wait for it forever (r107-coverage,
            # 2026-10-21). An older head keeps the older rule; the compatibility guard already lets suites pass it.
            starving = [w for w in waiting if w.get("job_class") in ("import", "rehearsal")
                        and w.get("starve_override") and _tag(w) in ("headroom", "budget")
                        and now - float(w.get("waiting_since") or w.get("enqueued_at") or now) >= self.starve_after]
            self_starving = (not is_suite and self.waiting_since is not None
                             and now - self.waiting_since >= self.starve_after)
            suite_cpu = None if is_suite or old_suite or self_starving else self._suite_cpu(running)
            jobs_cpu = sum(float(r.get("cpu", 0)) for r in running if r.get("job_class") in ("import", "rehearsal"))
            reason: tuple[str, str] | None = None
            if is_suite and starving:
                w = starving[0]
                reason = ("starve", f"starvation: suites paused for {_label(w)} ({w.get('job_class')} head waiting "
                                    f"{_fmt(now - float(w.get('waiting_since') or w.get('enqueued_at') or now))})")
            elif older:
                waits_for = "the suite headroom" if _tag(older[0]) == "headroom" else "the budget"
                reason = ("fifo", f"an older {older[0].get('job_class', '?')} job waits for {waits_for} "
                                  f"({_label(older[0])})")
            elif suite_cpu is not None and jobs_cpu + self.record["cpu"] > self.cpu_budget - suite_cpu:
                reason = ("headroom", f"suite headroom: a suite is queued or running ({suite_cpu:g} CPUs), so imports "
                                      f"and rehearsals get {jobs_cpu:g}+{self.record['cpu']:g} of "
                                      f"{self.cpu_budget - suite_cpu:g} CPUs")
            elif cpu + self.record["cpu"] > self.cpu_budget or mem + self.record["mem_gib"] > self.mem_budget:
                reason = ("budget", f"budget: {cpu:g}+{self.record['cpu']:g} of {self.cpu_budget:g} CPUs, "
                                    f"{mem:g}+{self.record['mem_gib']:g} of {self.mem_budget:g} GiB reserved")
            elif self.load_guard:
                outside = os.getloadavg()[0] - cpu
                if outside > 0.5 * ncpu():
                    self.load_since = self.load_since or now
                    if now - self.load_since < self.load_wait:
                        reason = ("load", f"load from outside the queue {outside:.1f} > {0.5 * ncpu():g}")
                    else:
                        sys.stderr.write(f"\nsuite-queue: load from outside the queue is still {outside:.1f}; "
                                         f"starting after {_fmt(self.load_wait)} anyway\n")
            if reason is not None:
                self.waiting_since = self.waiting_since or now
                # A wait that traces back to the suite headroom is written as blocked="load" (the real reason in
                # "held"): the one tag that every older version of this tool lets a suite pass, so a pre-headroom
                # suite waiter never defers to an import that is deferring to it. This version reads "held".
                # A paused suite is written the same way, so no waiter (an older version included) defers to it.
                via = reason[0] in ("headroom", "starve") or (reason[0] == "fifo" and any(
                    _tag(o) == "headroom" or o.get("via_headroom") for o in older))
                shown = {"blocked": "load", "held": reason[0], "via_headroom": True} if via else {"blocked": reason[0]}
                _write_json(self.root / "waiting" / self.name, dict(self.record, **shown, why=reason[1],
                                                                    waiting_since=self.waiting_since,
                                                                    starve_override=not is_suite))
                return reason[1]
            _write_json(self.root / "running" / self.name, dict(self.record, started_at=now))
            self.admitted_at = now
            with contextlib.suppress(FileNotFoundError):
                (self.root / "waiting" / self.name).unlink()
            return None
        finally:
            os.close(fd)

    def _unrecorded_suite(self, running: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """A live suite holder with no reservation (an old-version wrapper during the rollout) counts with the
        default suite reservation, so nothing is admitted beside it as if it were idle."""
        holder = _read_json(self.root.parent / "holder.json")
        pid = holder.get("pid") if holder else None
        if not holder or not isinstance(pid, int) or pid == self.record.get("pid") or any(
                r.get("pid") == pid for r in running) or not pid_is_queue_process(pid):
            return []
        cpu, mem = default_cost("suite", shlex.split(str(holder.get("command", ""))))
        return [{"pid": pid, "job_class": "suite", "label": _label(holder), "cpu": min(cpu, self.cpu_budget),
                 "mem_gib": min(mem, self.mem_budget), "unrecorded": True}]

    def _suite_cpu(self, running: list[dict[str, Any]]) -> float | None:
        """The CPUs a present suite reserves (the largest of the running and queued ones), or None with no suite."""
        cpus = [float(r.get("cpu", 0)) for r in running if r.get("job_class") == "suite"]
        tickets = self.root.parent / "tickets"
        for path in live_tickets(tickets, alive=pid_is_queue_process) if tickets.is_dir() else []:
            ticket = _read_json(path) or {}
            if isinstance(ticket.get("cpu"), (int, float)):
                cpus.append(float(ticket["cpu"]))
                continue
            try:  # an older wrapper's ticket has no reservation; one being written counts as a default suite
                command = shlex.split(str(ticket.get("command", "pytest -n 10")))
            except ValueError:
                command = ["pytest", "-n", "10"]
            cpus.append(default_cost("suite", command)[0])
        return min(max(cpus), self.cpu_budget) if cpus else None

    def withdraw(self) -> None:
        """Drop this job's waiting record (it is no longer a class head)."""
        self.waiting_since = None
        with contextlib.suppress(FileNotFoundError):
            (self.root / "waiting" / self.name).unlink()

    def release(self) -> None:
        """Give back a reservation that was admitted but never used (the job lost its head position first)."""
        with contextlib.suppress(FileNotFoundError):
            (self.root / "running" / self.name).unlink()
        self.admitted_at = None

    def leave(self) -> None:
        for sub in ("running", "waiting"):
            with contextlib.suppress(FileNotFoundError):
                (self.root / sub / self.name).unlink()


def _tag(record: dict[str, Any]) -> str | None:
    """Why a waiting head waits: "held" when the record has it (the compatible form of a headroom wait)."""
    return record.get("held") or record.get("blocked")


def _label(record: dict[str, Any]) -> str:
    return str(record.get("label") or record.get("branch") or "?")


def pid_is_queue_process(pid: int) -> bool:
    """True when ``pid`` is alive and is (still) this tool, so a reused pid does not keep a stale ticket alive."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # alive, owned by another user; leave it be
    try:
        # -ww: never truncate to $COLUMNS or the terminal width, which would cut the script name off
        out = subprocess.run(["ps", "-ww", "-o", "command=", "-p", str(pid)], capture_output=True, text=True,
                             timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return True
    if out.returncode != 0 or not out.stdout.strip():
        return True  # exited meanwhile or not visible; the next poll decides
    return any(os.path.basename(token) == TOOL_NAME for token in out.stdout.split())


def live_tickets(tickets: Path, alive=pid_is_queue_process) -> list[Path]:
    """The tickets in queue order, after removing the stale ones."""
    out = []
    for path in sorted(tickets.glob("*.json")):
        data = _read_json(path)
        pid = data.get("pid") if data else None
        if not isinstance(pid, int) or not alive(pid):
            if data is None and time.time() - _mtime(path) < 10:
                out.append(path)  # being written right now
                continue
            with contextlib.suppress(FileNotFoundError):
                path.unlink()
            continue
        out.append(path)
    return out


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return time.time()


def _git_branch(cwd: Path) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd, capture_output=True, text=True,
                             timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return "?"
    return out.stdout.strip() or "?"


def _fmt(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600}h{seconds // 60 % 60:02d}m" if seconds >= 3600 else f"{seconds // 60}m{seconds % 60:02d}s"


def describe(holder: dict[str, Any] | None, now: float) -> str:
    if not holder:
        return "nobody"
    since = holder.get("started_at")
    elapsed = f" for {_fmt(now - since)}" if isinstance(since, (int, float)) else ""
    return f"{holder.get('label') or holder.get('branch', '?')} ({holder.get('cwd', '?')}){elapsed}"


def group_alive(pgid: int) -> bool:
    """True while any process of process group ``pgid`` exists and is not a zombie (a killed process stays a zombie
    until its parent reaps it, and ``killpg(pgid, 0)`` still counts it)."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass  # another user's group, or (macOS) a group whose members are all zombies: ps decides
    try:
        out = subprocess.run(["ps", "-A", "-ww", "-o", "pgid=,stat="], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return True
    if out.returncode != 0:
        return True
    for line in out.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] == str(pgid) and not fields[1].startswith("Z"):
            return True
    return False


def process_identity(pid: int) -> dict[str, str] | None:
    """The start time and command line of ``pid`` (``ps -o lstart= -o command=``, C locale), or None if it is gone.

    Process-group ids are recycled pids, so a recorded ``child_pgid`` alone could name an unrelated later group; the
    identity of its leader, recorded at spawn, tells them apart."""
    try:
        out = subprocess.run(["ps", "-ww", "-o", "lstart=", "-o", "command=", "-p", str(pid)], capture_output=True,
                             text=True, timeout=10, env={**os.environ, "LC_ALL": "C", "LANG": "C"})
    except (OSError, subprocess.TimeoutExpired):
        return None
    fields = out.stdout.strip().split(None, 5) if out.returncode == 0 else []
    if len(fields) < 6:
        return None
    return {"lstart": " ".join(fields[:5]), "command": fields[5]}


def same_group(holder: dict[str, Any], pgid: int) -> bool:
    """True only while the leader of ``pgid`` is still the process the holder spawned (same start time and command).

    A holder written without the identity (an older wrapper) cannot be verified and counts as gone: an unverified
    group is never waited for and never signalled."""
    lstart, command = holder.get("child_lstart"), holder.get("child_command")
    if not isinstance(lstart, str) or not isinstance(command, str):
        return False
    now = process_identity(pgid)
    return now is not None and now["lstart"] == lstart and now["command"] == command


def orphan(holder: dict[str, Any] | None, now: float) -> tuple[int, bool] | None:
    """A suite left behind by a holder that died without its ``finally`` (SIGKILL, a killed session): ``(pgid,
    expired)`` while its process group still runs **and its leader is still the recorded process**, else None.
    ``expired`` once its own run timeout has passed."""
    if not holder or holder.get("pid") == os.getpid():
        return None
    pid, pgid = holder.get("pid"), holder.get("child_pgid")
    if not isinstance(pgid, int) or (isinstance(pid, int) and pid_is_queue_process(pid)) or not group_alive(pgid):
        return None
    if not same_group(holder, pgid):
        return None  # a recycled pgid, or an unverifiable record: treat the orphan as gone
    started, limit = holder.get("started_at"), holder.get("run_timeout_s")
    expired = isinstance(started, (int, float)) and isinstance(limit, (int, float)) and limit > 0 and \
        now > started + limit
    return pgid, expired


def running_pids(cdir: Path, job_class: str) -> set[int]:
    """Pids of the live holders of a class: their own tickets stay in ``tickets/`` while they run."""
    pids = set()
    for path in all_holder_files(cdir, job_class):
        holder = _read_json(path)
        if holder and _holder_alive(holder):
            pids.add(holder["pid"])
    return pids


def priority_stem(cdir: Path, job_class: str, pid: int, enqueued_at: float) -> tuple[str, float]:
    """A ticket name and a budget position just before the class's first *ordinary* waiter and after every earlier
    priority job (FIFO among priority jobs); a plain new name when no ordinary job waits.

    Each priority ticket takes the midpoint between the ticket before that waiter (the last priority job, else the
    running holder) and the waiter, in nanoseconds for the name and in seconds for the budget order."""
    tickets = live_tickets(cdir / "tickets") if (cdir / "tickets").is_dir() else []
    running = running_pids(cdir, job_class)
    data = {t: _read_json(t) or {} for t in tickets}
    head = next((t for t in tickets if data[t].get("pid") not in running and not data[t].get("priority_reason")), None)
    if head is None:
        return f"{time.time_ns():020d}-{pid}", enqueued_at
    k = tickets.index(head)
    head_ns = int(head.name.split("-", 1)[0])
    head_at = float(data[head].get("enqueued_at", enqueued_at))
    before = tickets[k - 1] if k > 0 else None
    low_ns = int(before.name.split("-", 1)[0]) if before else head_ns - 10**9
    low_at = float(data[before].get("order_at", data[before].get("enqueued_at", head_at - 1.0))) if before \
        else head_at - 1.0
    ns = (low_ns + head_ns) // 2
    taken = {int(t.name.split("-", 1)[0]) for t in tickets}
    if ns <= low_ns or ns in taken:  # no room left between them (about 30 jumps in one gap): go just before the head
        ns = head_ns - 1
        while ns in taken:
            ns -= 1
    return f"{ns:020d}-{pid}", (low_at + head_at) / 2


#: --status flags a suspected deadlock after this long with every head waiting and nothing running
DEADLOCK_AFTER = 15 * 60.0


def status(qdir: Path, deadlock_after: float = DEADLOCK_AFTER) -> int:
    now = time.time()
    anyone_running = False
    print(f"queue dir: {qdir}")
    for job_class in CLASSES:
        cdir = class_dir(qdir, job_class)
        if job_class != "suite" and not cdir.is_dir():
            continue
        tickets = live_tickets(cdir / "tickets") if (cdir / "tickets").is_dir() else []
        holders = [h for h in (_read_json(p) for p in all_holder_files(cdir, job_class)) if h and _holder_alive(h)]
        anyone_running = anyone_running or bool(holders)
        running = running_pids(cdir, job_class)
        if job_class != "suite":
            print(f"class {job_class} ({slots(job_class)} slots):")
        if job_class == "suite" or not holders:
            print(f"running:   {describe(holders[0], now) if holders else 'nobody'}")
        for h in holders[1:] if job_class == "suite" else holders:
            print(f"running:   {describe(h, now)}")
        i = 0
        for path in tickets:
            t = _read_json(path) or {}
            if t.get("pid") in running:
                print(f"  running. pid {t.get('pid')} {t.get('label') or t.get('branch', '?')} ({t.get('cwd', '?')})")
                continue
            i += 1
            why = f" [priority: {t['priority_reason']}]" if t.get("priority_reason") else ""
            held = _read_json(jobs_root(qdir) / "waiting" / f"{job_class}-{path.stem}.json") or {}
            if held.get("why"):
                why += f" [{held['why']}]"
            print(f"  {i}. pid {t.get('pid')} {t.get('label') or t.get('branch', '?')} ({t.get('cwd', '?')}), "
                  f"waiting {_fmt(now - t.get('enqueued_at', now))}{why}")
    root = jobs_root(qdir)
    if (root / "running").is_dir():
        cpu_budget, mem_budget = budget()
        records = [r for r in (_read_json(p) for p in sorted((root / "running").glob("*.json"))) if r and
                   isinstance(r.get("pid"), int) and pid_is_queue_process(r["pid"])]
        cpu = sum(float(r.get("cpu", 0)) for r in records)
        mem = sum(float(r.get("mem_gib", 0)) for r in records)
        print(f"budget:    {cpu:g} of {cpu_budget:g} CPUs, {mem:g} of {mem_budget:g} GiB reserved")
        for r in records:
            print(f"  {r.get('job_class', '?')}: {_label(r)} cpu {r.get('cpu')} mem {r.get('mem_gib')} GiB")
        anyone_running = anyone_running or bool(records)
    paused = [w for w in (_read_json(p) for p in sorted((root / "waiting").glob("suite-*.json")))
              if w and w.get("held") == "starve" and isinstance(w.get("pid"), int)
              and pid_is_queue_process(w["pid"])] if (root / "waiting").is_dir() else []
    for w in paused:
        print(f"{w.get('why', 'starvation: suites paused')}; the running suite is not stopped")
    heads = [w for w in (_read_json(p) for p in sorted((root / "waiting").glob("*.json"))) if w and
             isinstance(w.get("pid"), int) and pid_is_queue_process(w["pid"])] if (root / "waiting").is_dir() else []
    if heads and not anyone_running:
        # an older wrapper's record has no waiting_since: its enqueue time over-states the wait, which is safe
        stuck = min(now - float(w.get("waiting_since") or w.get("enqueued_at") or now) for w in heads)
        if stuck > deadlock_after:
            print(f"DEADLOCK?  nothing runs and 0 CPUs are reserved, and every head has waited at least "
                  f"{_fmt(stuck)}:")
            for w in heads:
                print(f"  {w.get('job_class', '?')}: {_label(w)} (pid {w.get('pid')}): {w.get('why') or _tag(w) or '?'}")
            print("  A waiter keeps the code it started with: re-queue the old-version one with main's "
                  "tools/suite_queue.py.")
    return 0


def _holder_alive(holder: dict[str, Any]) -> bool:
    pid = holder.get("pid")
    return isinstance(pid, int) and pid_is_queue_process(pid)


class Waiter:
    """Prints the waiting display: one rewritten line on a terminal, else a line per ``every`` seconds."""

    def __init__(self, stream=sys.stderr, every: float = 60.0) -> None:
        self.stream, self.every, self.last, self.tty, self.shown = stream, every, float("-inf"), stream.isatty(), False

    def show(self, text: str, now: float) -> None:
        if self.tty:
            self.stream.write("\r\x1b[2K" + text)
            self.stream.flush()
            self.shown = True
        elif now - self.last >= self.every:
            self.stream.write(text + "\n")
            self.stream.flush()
            self.last = now

    def done(self) -> None:
        if self.tty and self.shown:
            self.stream.write("\r\x1b[2K")
            self.stream.flush()


def acquire(qdir: Path, ticket: Path, lock_fd: int, *, poll: float, wait_timeout: float | None,
            waiter: Waiter, data: dict[str, Any] | None = None, grace: float = 30.0,
            extra_lock_fds: tuple[int, ...] = (), holders: list[Path] | None = None,
            admit: Admission | None = None, slot: list[int] | None = None) -> bool:
    """Wait until ``ticket`` may take a slot, (with ``admit``) the budget admits it, then a slot lock is ours and no
    orphaned suite still runs on it; False on ``wait_timeout``. ``qdir`` is the class directory; the suite class has
    one slot (``lock_fd``), the other classes pass their further slot locks in ``extra_lock_fds``. A ticket that
    vanished (removed by another waiter's mistaken stale check) is written again under its original name, so it keeps
    its place. The slot taken is appended to ``slot``."""
    fds = [lock_fd, *extra_lock_fds]
    holder_paths = holders or [qdir / "holder.json"]
    start = time.monotonic()
    locked: int | None = None
    admitted = admit is None
    while True:
        line = live_tickets(qdir / "tickets")
        if ticket not in line and data is not None:
            _write_json(ticket, data)
            line = live_tickets(qdir / "tickets")
        now = time.time()
        index = line.index(ticket) if ticket in line else len(line)
        blocked = None
        # Admission first, the slot lock after it (admission is serialised by its own lock): a head that waits for
        # the budget holds no slot, so a --before-head ticket can overtake it.
        if admit is not None and locked is None and index >= len(fds):
            # Not (or no longer) a head, e.g. a priority ticket went before it: hold nobody back. An admitted job
            # that has not taken its slot yet gives its reservation back too, or the priority job's admission would
            # wait for it while it waits for the head position (a deadlock; suite-perf's review). It is admitted
            # again when it is a head again.
            admit.withdraw()
            if admitted:
                admit.release()
                admitted = False
        if not admitted and admit is not None and index < len(fds):
            blocked = admit.try_admit(now)
            admitted = blocked is None
        if admitted and locked is None and index < len(fds):
            for i, fd in enumerate(fds):
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = i
                    break
                except BlockingIOError:
                    pass  # a previous holder is finishing (its ticket is gone, its lock not yet), or the slot is busy
        holder = _read_json(holder_paths[locked if locked is not None else 0])
        left = orphan(holder, now) if locked is not None else None
        if locked is not None and left is None:
            waiter.done()
            if slot is not None:
                slot.append(locked)
            return True
        if left is not None and left[1]:
            sys.stderr.write(f"\nsuite-queue: stopping the orphaned suite (process group {left[0]}) of a dead holder; "
                             "its own run timeout has passed\n")
            _stop_pgid(left[0], grace, holder)
            continue
        waited = time.monotonic() - start
        if wait_timeout is not None and waited >= wait_timeout:
            waiter.done()
            if locked is not None:
                fcntl.flock(fds[locked], fcntl.LOCK_UN)
            return False
        running = {h["pid"] for h in (_read_json(p) for p in holder_paths) if h and isinstance(h.get("pid"), int)}
        ahead = [t for t in line[:index] if (_read_json(t) or {}).get("pid") not in running]
        waiting = [t for t in line if (_read_json(t) or {}).get("pid") not in running]
        position = len(ahead) + 1
        what = (f"an orphaned suite of a dead holder (process group {left[0]}; kill -TERM -{left[0]} to stop it) "
                f"from {describe(holder, now)}" if left else blocked if blocked else describe(holder, now))
        waiter.show(f"suite-queue: position {position} of {max(len(waiting), position)}; "
                    f"{'waiting: ' if blocked else 'running: '}{what}; waited {_fmt(waited)}", now)
        time.sleep(poll)


#: Commands the sweep leaves alone: a test's git may detach ``git gc --auto`` (gc.autoDetach); it ends by itself and
#: holds no budgeted CPU worth a signal (suite-perf's review).
SWEEP_SPARES = ("git gc", "git maintenance")


def process_table() -> dict[int, tuple[int, str]]:
    """Every process as ``pid -> (ppid, start time)`` (``ps -A``, C locale), without the ones the sweep spares;
    empty if ``ps`` fails."""
    try:
        out = subprocess.run(["ps", "-A", "-ww", "-o", "pid=,ppid=,lstart=,command="], capture_output=True, text=True,
                             errors="replace", timeout=10, env={**os.environ, "LC_ALL": "C", "LANG": "C"})
    except (OSError, subprocess.TimeoutExpired):
        return {}
    table: dict[int, tuple[int, str]] = {}
    for line in out.stdout.splitlines():
        fields = line.split(None, 7)
        if len(fields) >= 7 and fields[0].isdigit() and fields[1].isdigit():
            command = fields[7] if len(fields) > 7 else ""
            words = command.split()
            spared = len(words) >= 2 and Path(words[0]).name == "git" and " ".join(["git", words[1]]) in SWEEP_SPARES
            if not spared:
                table[int(fields[0])] = (int(fields[1]), " ".join(fields[2:7]))
    return table


def descendants(root: int, table: dict[int, tuple[int, str]] | None = None) -> dict[int, str]:
    """The processes below ``root`` (by parent pid), as ``pid -> start time``. An ``agentprov.worker`` starts its own
    session, so the suite's process group does not contain it; the process tree does, while its parents live."""
    table = process_table() if table is None else table
    children: dict[int, list[int]] = {}
    for pid, (ppid, _start) in table.items():
        children.setdefault(ppid, []).append(pid)
    out: dict[int, str] = {}
    todo = list(children.get(root, []))
    while todo:
        pid = todo.pop()
        if pid not in out and pid != root:
            out[pid] = table[pid][1]
            todo.extend(children.get(pid, []))
    return out


def sweep(known: dict[int, str], grace: float) -> int:
    """Stop the processes in ``known`` that still run as the same process (pid and start time), SIGTERM then SIGKILL
    after ``grace``, and wait until they are gone; returns how many were found. Leftovers of a suite hold CPU that the
    budget counts as free once the slot is released (BF-1)."""
    def live() -> list[int]:
        now = process_table()
        return [pid for pid, start in known.items() if pid in now and now[pid][1] == start]

    left = live()
    if not left:
        return 0
    for pid in left:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + grace
    while (still := live()) and time.monotonic() < deadline:
        time.sleep(0.2)
    for pid in still:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(pid, signal.SIGKILL)
    deadline = time.monotonic() + 10
    while live() and time.monotonic() < deadline:
        time.sleep(0.2)
    return len(left)


class SessionStatus:
    """Keeps the invoking session's status file (``tools/session_status.py``, D-428) in step with a queued suite:
    waiting for the slot, running, then green or red. Only a session that already has a status file is updated (the
    queue never creates one), and any failure is ignored: the status is a convenience, never part of the gate."""

    def __init__(self, cwd: Path, enabled: bool) -> None:
        self.tool = Path(__file__).resolve().with_name("session_status.py")
        self.cwd = cwd
        self.enabled = enabled and self.tool.is_file() and self._exists()

    def _run(self, *args: str) -> str | None:
        try:
            out = subprocess.run([sys.executable, str(self.tool), "-C", str(self.cwd), *args], capture_output=True,
                                 text=True, errors="replace", timeout=30)
            return out.stdout.strip() if out.returncode == 0 else None
        except Exception:  # noqa: BLE001 - a status update is never part of the gate (suite-perf's review)
            return None

    def _exists(self) -> bool:
        path = self._run("path")
        return path is not None and path != "" and Path(path).is_file()

    def update(self, *args: str) -> None:
        if self.enabled:
            self._run(*args)


def run_child(command: list[str], *, run_timeout: float | None, grace: float, env: dict[str, str] | None = None,
              on_start: Any = None, track_every: float = 2.0, forward_every: float = 0.1) -> int:
    """Run ``command`` in its own session; forward signals to its process group; enforce ``run_timeout``.

    The process tree below the child is recorded every ``track_every`` seconds (and again before a stop), so the
    processes that left its process group (``agentprov.worker`` starts its own session) are stopped too after a
    timeout or a signal, and any that outlive the child are swept before the slot is released (BF-1). A process
    started within the last ``track_every`` seconds before the child exits on its own can escape the record (once its
    parent is gone, the tree no longer leads to it); a timeout or a signal records the tree right before stopping.

    **Forwarding** (B2, 2026-10-28). A handler only records a signal; the loop sends it, every ``forward_every`` seconds,
    and only right after ``child.wait`` has said the child is not reaped yet. An unreaped child's pid cannot be reused,
    so its process group is ours; after the reap nothing is signalled by group id. On macOS ``killpg`` fails with EPERM,
    not ESRCH, when every member of the group is a zombie (the child exited, not yet reaped): that is "already gone"."""
    child = subprocess.Popen(command, start_new_session=True, env=env)
    if on_start is not None:
        on_start(child)
    received: list[int] = []
    sent = 0  # how many of ``received`` were forwarded
    known: dict[int, str] = {}

    def record(signum: int, _frame: Any) -> None:
        received.append(signum)

    previous = {s: signal.signal(s, record) for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    timed_out = False
    try:
        deadline = None if run_timeout is None else time.monotonic() + run_timeout
        tracked = time.monotonic()
        while True:
            left = None if deadline is None else max(0.0, deadline - time.monotonic())
            try:
                code = child.wait(timeout=forward_every if left is None else min(forward_every, left))
                break
            except subprocess.TimeoutExpired:  # not reaped: child.pid is still our group's id
                if sent < len(received):
                    known.update(descendants(child.pid))
                    for signum in received[sent:]:
                        _signal_group(child, signal.SIGINT if signum == signal.SIGINT else signal.SIGTERM)
                    sent = len(received)
                elif time.monotonic() - tracked >= track_every:
                    known.update(descendants(child.pid))
                    tracked = time.monotonic()
                if deadline is not None and time.monotonic() >= deadline:
                    sys.stderr.write(f"suite-queue: run timeout ({_fmt(run_timeout or 0)}); stopping the suite\n")
                    known.update(descendants(child.pid))
                    _stop_group(child, grace)
                    timed_out = True
                    break
    finally:
        for s, handler in previous.items():
            signal.signal(s, handler)
        found = sweep(known, grace)
        if found:
            sys.stderr.write(f"suite-queue: stopped {found} leftover process(es) of the suite (workers in their own "
                             "sessions)\n")
    if timed_out:
        return EX_TIMEOUT
    if received and code == 0:
        return 128 + received[0]
    return 128 - code if code < 0 else code


def _stop_pgid(pgid: int, grace: float, holder: dict[str, Any] | None = None) -> None:
    """SIGTERM, then SIGKILL after ``grace``, to process group ``pgid``. With ``holder``, nothing is sent unless the
    group's leader is still the process that holder spawned. While any member of the group lives, its id cannot be
    reused, so the SIGKILL that follows a continuous wait reaches the same group."""
    if holder is not None and not same_group(holder, pgid):
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pgid, signal.SIGTERM)
    deadline = time.monotonic() + grace
    while group_alive(pgid) and time.monotonic() < deadline:
        time.sleep(0.2)
    if holder is not None and not same_group(holder, pgid):
        return  # the group ended and its id may have been reused meanwhile (B2): verify again before the SIGKILL
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pgid, signal.SIGKILL)


def _signal_group(child: subprocess.Popen[bytes], sig: int) -> None:
    """Signal the child's process group while the child is unreaped (its pid, the group id, cannot be reused yet).
    ESRCH and EPERM both mean the group has no live member left (EPERM: macOS, only zombies; see :func:`run_child`)."""
    if child.returncode is not None:
        return  # reaped: the id may already name another group
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(child.pid, sig)


def _stop_group(child: subprocess.Popen[bytes], grace: float) -> None:
    """SIGTERM, then SIGKILL after ``grace``, to the unreaped child's group (called only after a wait timed out)."""
    _signal_group(child, signal.SIGTERM)
    try:
        child.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        _signal_group(child, signal.SIGKILL)
        child.wait()


def _amount(text: str) -> float:
    """``--cpu`` / ``--mem-gib``: a finite number, 0 or above (a NaN reservation would compare as always fitting)."""
    value = float(text)
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError(f"must be a finite number, 0 or above, not {text[:40]!r}")
    return value


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    command: list[str] = []
    if "--" in args:
        cut = args.index("--")
        args, command = args[:cut], args[cut + 1:]
    p = argparse.ArgumentParser(allow_abbrev=False, prog="suite_queue.py", description="Run a full test suite through the machine-wide queue.")
    p.add_argument("--queue-dir", type=Path, help="queue directory (default $AGENTPROV_SUITE_QUEUE_DIR, else "
                   "$AGENTPROV_HOME/locks/suite-queue, else ~/.agentprov/locks/suite-queue)")
    p.add_argument("--label", help="shown to waiters (default: the git branch)")
    p.add_argument("--wait-timeout", type=float, metavar="S", help="give up after waiting S seconds (exit 75)")
    p.add_argument("--run-timeout", type=float, default=7200.0, metavar="S",
                   help="stop the suite after S seconds (exit 124; default 7200; 0 = none)")
    p.add_argument("--grace", type=float, default=30.0, metavar="S", help="SIGTERM to SIGKILL grace (default 30)")
    p.add_argument("--poll", type=float, default=2.0, metavar="S", help="queue poll interval (default 2)")
    p.add_argument("--status", action="store_true", help="show the running holder and the waiters, then exit")
    p.add_argument("--deadlock-minutes", type=_amount, default=DEADLOCK_AFTER / 60, metavar="M",
                   help="--status: flag a suspected deadlock after M minutes with every head waiting and nothing "
                        "running (default 15)")
    p.add_argument("--targeted", action="store_true",
                   help="run now, outside the queue (targeted runs), with the same bytecode environment")
    p.add_argument("--keep-bytecode-env", action="store_true",
                   help="pass PYTHONDONTWRITEBYTECODE / PYTHONPYCACHEPREFIX through unchanged")
    p.add_argument("--pycache-max-mb", type=float, default=1024.0, metavar="MB",
                   help="a full run clears a bytecode cache larger than this first (default 1024)")
    p.add_argument("--clear-pycache", action="store_true", help="remove the bytecode cache, then exit")
    p.add_argument("--no-precompile", action="store_true",
                   help="do not precompile src/agentprov for the workers (D-407)")
    p.add_argument("--class", dest="job_class", choices=list(CLASSES), default="suite",
                   help="job class (D-427): suite (default), import or rehearsal")
    p.add_argument("--cpu", type=_amount, metavar="N", help="CPUs to reserve (default: from the command, see above)")
    p.add_argument("--mem-gib", type=_amount, metavar="G", help="memory to reserve in GiB (default: from the command)")
    p.add_argument("--before-head", action="store_true",
                   help="queue just before the current head waiter (a sanctioned jump; needs --reason)")
    p.add_argument("--reason", help="why --before-head is used (recorded in the ticket and history.jsonl)")
    p.add_argument("--no-session-status", action="store_true",
                   help="do not update the session's status file (tools/session_status.py) for a queued suite")
    p.add_argument("--load-wait", type=float, default=600.0, metavar="S",
                   help="import/rehearsal: wait at most S seconds for outside load to drop (default 600)")
    p.add_argument("--starve-minutes", type=_amount, default=STARVE_AFTER / 60, metavar="M",
                   help="an import or rehearsal head waiting M minutes on the headroom or the budget ignores the "
                        "headroom, and no new suite starts until it has (default 60)")
    opts = p.parse_args(args)
    try:
        budget()
        slot_override()
    except BudgetError as exc:
        p.error(str(exc))
    if opts.before_head and not (opts.reason or "").strip():
        p.error("--before-head needs --reason")
    if opts.job_class != "suite":  # D-406/D-407 are for test runs; corpus-producing runs keep the session's environment
        opts.keep_bytecode_env = opts.no_precompile = True
    prefix = pycache_prefix()
    if opts.clear_pycache:
        clear_pycache(prefix)
        return 0
    env = None if opts.keep_bytecode_env else child_env(os.environ, prefix)
    qdir = opts.queue_dir or queue_dir()
    (qdir / "tickets").mkdir(parents=True, exist_ok=True)
    if opts.status:
        return status(qdir, opts.deadlock_minutes * 60)
    if not command:
        p.error("no command given (use: suite_queue.py [options] -- pytest ...)")
    top = None if opts.no_precompile else _toplevel(Path.cwd())
    if opts.targeted:
        if top is not None:
            precompile(top)
        return run_child(command, run_timeout=opts.run_timeout or None, grace=opts.grace, env=env)

    cwd = Path.cwd()
    cdir = class_dir(qdir, opts.job_class)
    (cdir / "tickets").mkdir(parents=True, exist_ok=True)
    cpu, mem = reservation(opts.job_class, command, opts.cpu, opts.mem_gib)
    me: dict[str, Any] = {"pid": os.getpid(), "host": socket.gethostname(), "cwd": str(cwd), "branch": _git_branch(cwd),
                          "label": opts.label, "command": shlex.join(command), "enqueued_at": time.time()}
    me.update(cpu=cpu, mem_gib=mem)  # a suite ticket's reservation sets the suite headroom
    if opts.job_class != "suite":
        me.update(job_class=opts.job_class)
    stem = f"{time.time_ns():020d}-{os.getpid()}"
    order_at = me["enqueued_at"]
    if opts.before_head:
        stem, order_at = priority_stem(cdir, opts.job_class, os.getpid(), me["enqueued_at"])
        me.update(priority_reason=opts.reason, order_at=order_at)
        sys.stderr.write(f"suite-queue: queued before the head waiter: {opts.reason}\n")
    ticket = cdir / "tickets" / f"{stem}.json"
    _write_json(ticket, me)
    session: SessionStatus | None = None
    lock_fds = [os.open(path, os.O_RDWR | os.O_CREAT, 0o600) for path in slot_locks(cdir, opts.job_class)]
    lock_fd = lock_fds[0]
    holders = holder_files(cdir, opts.job_class)
    admission = Admission(jobs_root(qdir), opts.job_class, stem, {**me, "enqueued_at": order_at, "cpu": cpu,
                                                                 "mem_gib": mem},
                          load_guard=opts.job_class != "suite", load_wait=opts.load_wait,
                          starve_after=opts.starve_minutes * 60)
    slot: list[int] = []
    try:
        def leave(signum: int, _frame: Any) -> None:
            raise SystemExit(128 + signum)  # runs the finally below, which removes the ticket

        previous = {s: signal.signal(s, leave) for s in (signal.SIGTERM, signal.SIGHUP)}
        # after the handlers: a signal during these calls still removes the ticket
        session = SessionStatus(cwd, enabled=opts.job_class == "suite" and not opts.no_session_status)
        session.update("set", "--state", "waiting-for-slot", "--waits-on", "slot", "suite queue")
        try:
            got = acquire(cdir, ticket, lock_fd, poll=opts.poll, wait_timeout=opts.wait_timeout, waiter=Waiter(),
                          data=me, grace=opts.grace, extra_lock_fds=tuple(lock_fds[1:]), holders=holders,
                          admit=admission, slot=slot)
        except KeyboardInterrupt:
            return 130
        finally:
            for s, handler in previous.items():
                signal.signal(s, handler)
        if not got:
            sys.stderr.write(f"suite-queue: gave up after waiting {_fmt(opts.wait_timeout or 0)}\n")
            return EX_TEMPFAIL
        if env is not None and prefix.exists() and tree_bytes(prefix) > opts.pycache_max_mb * 2**20:
            sys.stderr.write(f"suite-queue: bytecode cache over {opts.pycache_max_mb:g} MB; clearing {prefix}\n")
            try:
                clear_pycache(prefix)
            except (OSError, SystemExit) as exc:  # an optimisation: never stop the gate for it
                sys.stderr.write(f"suite-queue: bytecode cache not cleared ({exc}); the suite runs anyway\n")
        if top is not None:
            precompile(top)  # while holding the queue: compiling is the suite's own CPU
        started = time.time()
        if session is not None:
            session.update("suite-start")
        holding = {**me, "started_at": started, "run_timeout_s": opts.run_timeout or 0}
        holder_path = holders[slot[0]]
        _write_json(holder_path, holding)
        sys.stderr.write(f"suite-queue: running after waiting {_fmt(started - me['enqueued_at'])}: {me['command']}\n")

        def record_child(child: subprocess.Popen[bytes]) -> None:  # lets a later holder find an orphaned suite
            # Popen returns after the exec, so this is the child's own start time and command line.
            identity = process_identity(child.pid) or {}
            _write_json(holder_path, {**holding, "child_pgid": child.pid,
                                      **{f"child_{k}": v for k, v in identity.items()}})

        env = granted_env(env, opts.job_class, admission.record["mem_gib"])
        env = go_env(env, admission.record["cpu"])
        code = run_child(command, run_timeout=opts.run_timeout or None, grace=opts.grace, env=env,
                         on_start=record_child)
        ended = time.time()
        if session is not None:
            session.update("suite", "--result", "green" if code == 0 else "red", "--command", me["command"])
        with open(cdir / "history.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"label": opts.label or me["branch"], "cwd": me["cwd"], "command": me["command"],
                                 "enqueued_at": me["enqueued_at"], "started_at": started, "ended_at": ended,
                                 "waited_s": round(started - me["enqueued_at"], 3), "wall_s": round(ended - started, 3),
                                 "exit": code, "admitted_at": admission.admitted_at,
                                 **({"priority_reason": opts.reason} if opts.before_head else {}),
                                 "cpu": admission.record["cpu"], "mem_gib": admission.record["mem_gib"]},
                                sort_keys=True) + "\n")
        return code
    finally:
        for path in holders:
            holder = _read_json(path)
            if holder and holder.get("pid") == os.getpid():
                with contextlib.suppress(FileNotFoundError):
                    path.unlink()
        admission.leave()  # the reservation goes with the slot lock
        with contextlib.suppress(FileNotFoundError):
            ticket.unlink()
        for fd in lock_fds:
            os.close(fd)  # releases the flock


if __name__ == "__main__":
    sys.exit(main())
