# Suite performance: decisions D-400..D-409

Session "AgentPROV test-suite performance" (branch `suite-perf`, 2026-10-14). These are proposals for the user unless
marked otherwise. Measurements are in `baseline.md` and `results.md`. A pointer goes into `docs/architecture/DECISIONS.md`
once the merge queue has drained (every branch appends there, so it is left alone until then).

**Why this work exists.** The full suite (7,042 tests) is the merge gate for every branch. It ran in one process for
23–45 minutes, and up to six sessions ran it at once on one 12-core M2 Max, so each run took longer still and the
load-sensitive tests ran close to their limits.

## D-400: how the suite is measured

- Per-test wall time from `--durations=0`. Per-test process CPU, child CPU (`RUSAGE_CHILDREN`), process spawns by kind,
  and `time.sleep` totals come from a measurement-only plugin that is never committed.
- Wall times taken while other suites run are labelled **contended**, with the load average. CPU figures are the
  load-independent comparison.
- Collected ids and outcome sets are compared from JUnit XML. The `@<group>` suffix that xdist adds to the node ids of
  grouped tests is stripped first.

## D-401: pytest-xdist in the dev group; `--dist loadgroup`; grouping in `tests/conftest.py`

**User-approved 2026-10-14.** `pytest-xdist` (3.8.0, with `execnet` 2.1.2) goes in `[dependency-groups] dev` only.
The core environment is unchanged.

`tests/conftest.py` holds `XDIST_GROUPS`: a table of path prefixes and groups. Its hook runs before xdist's own worker
hook, which turns the markers into `@group` node ids. One `serial` group keeps the tests that are sensitive to load
(rlimits, wall/CPU timeouts, calibration) and the determinism checks with their own worker pools together on one
worker, so they never overlap each other.

*Rejected:*
- Editing hundreds of test files to add markers: a large diff that would conflict with the queued branches.
- `--dist loadscope`: it keeps whole modules together and balances worse.
- A separate serial pytest invocation: two commands, and the gate is then two runs.

## D-402: an isolated `$AGENTPROV_HOME` per test and a write guard

Every test gets a fresh tmp `$AGENTPROV_HOME`, and each worker process gets one for its session fixtures.

An audit hook refuses, and the test then fails on, any write, rename, remove, chmod, utime or copy to an absolute path
outside the temporary directories. Allowed are pytest's basetemp, `$TMPDIR`, `/dev`, the repository's `.hypothesis`
and `.pytest_cache`, and any `__pycache__`. The repository checkout and `~` are therefore protected.
`AGENTPROV_TEST_WRITE_GUARD=report` records without refusing; `off` disables the guard.

Limits: relative paths are not checked, because production code walks directories with `dir_fd` and the audit event
does not carry the descriptor. Child processes are not covered.

*Rejected:*
- A per-test `git status` of the checkout: too slow, and it races with other workers.
- Running every test with `HOME` pointed at a temporary directory: it changes what `Path.home()` tests observe.

## D-403: `tools/suite_queue.py`, a machine-wide FIFO for full suites

- Tickets `<queue-dir>/tickets/<time_ns>-<pid>.json` define the order.
- An `flock` on `suite.lock` gives mutual exclusion. The kernel releases it when the holder dies, so a crash never
  wedges the queue.
- Stale tickets are dropped by a pid check, which also verifies the pid is still this tool (pid reuse).
- Waiters see their position, the running holder and their own wait time.
- `--wait-timeout` exits 75; `--run-timeout` (default 2 h) stops the suite's process group and exits 124.
- Signals are forwarded to the suite's process group.
- A local `history.jsonl` records each run.
- The queue directory is `$AGENTPROV_SUITE_QUEUE_DIR`, else `$AGENTPROV_HOME/locks/suite-queue`, else
  `~/.agentprov/locks/suite-queue`.

The interface is frozen until any extension (a heavy-job scheduler, proposed by workflow-tools) is agreed through the
orchestrator.

*Rejected:*
- A lock file holding a pid, without `flock`: crash recovery then depends on pid checks alone.
- A server process: more moving parts than a lock needs.

## D-404: targeted runs bypass the queue

`suite_queue.py --targeted -- pytest <paths>` runs at once with the same environment (D-406, D-407).

Targeted runs are short and mostly single-process. Queueing them behind a full suite would stall every session's
edit-test loop. The full suite's load-sensitive tests are already isolated from each other by the `serial` group, and
they passed serially under loads of 50–117.

*Rejected:* a light lane (a counting semaphore for targeted runs). It is more machinery, and a targeted run would
still wait behind full suites.

## D-405: Hypothesis profiles

- `HYPOTHESIS_PROFILE=gate` (the default) is registered as a copy of the profile Hypothesis would load anyway:
  `default` locally, or Hypothesis's own `ci` profile under `CI`. The gate therefore never gets weaker.
- `HYPOTHESIS_PROFILE=dev` lowers the *default* `max_examples` to 20 for targeted re-runs. Tests that set their own
  `max_examples`, and the fuzz budgets (`AGENTPROV_FUZZ`), keep theirs.

## D-406: bytecode for the suite's own process, cached outside every source tree

**Decided by the orchestrator under the user's delegation, 2026-10-14.**

The Claude desktop app sets `PYTHONDONTWRITEBYTECODE=1` for session processes. It is not in the user's shell profiles,
`launchctl`, `~/.claude` settings or the repository. As a result, every run recompiled every module and re-ran
pytest's assertion rewriting on all 456 test modules: collection took 43 s wall / 19 s CPU, against 21 s / 10.4 s with
bytecode.

The wrapper's child process runs without that variable and with `PYTHONPYCACHEPREFIX=$AGENTPROV_PYCACHE_PREFIX`, else
`~/.cache/agentprov/pycache`. The cache mirrors absolute source paths, so worktrees never collide, and `.pyc` files are
validated against the source. pytest 9.1.1 honours `sys.pycache_prefix` for rewritten modules.

In-tree bytecode was rejected: `.gitignore` re-includes `tests/golden/**`, so a `tests/golden/__pycache__` dirties the
checkout and breaks the tests that run `git ls-files --others`.

Constraints:
- G.4.2 is unchanged: workers keep `python -I -B` and gain nothing from the prefix (obs-G6).
- No interpreter that runs baseline or old-repo code is affected. All such launches use `-I -B` (audit in
  `results.md`), and HL item 2 and J.0.3 hold.

## D-407: precompiled `src/agentprov` for the workers (wrapper only)

**Decided by the orchestrator under the user's delegation, 2026-10-14, with these conditions.**

- Before a queued or targeted run, the wrapper runs `python -m compileall -q --invalidation-mode checked-hash` on
  `src/agentprov` only. The output goes into its git-ignored `__pycache__`, and `git status --porcelain` stays empty,
  which a test asserts.
- `checked-hash` means a `.pyc` file is valid only for the source bytes it was built from, so a rebase or a checkout
  can never serve a stale one.
- Workers keep `-I -B` (G.4.2): they read these files and never write any.
- None of this is in product code.
- Measured: a worker-style import (worker, runner, PROV engine, SEM engine) costs 0.11–0.12 s CPU against 0.28–0.31 s,
  and checked-hash keeps the full timestamp-mode gain. The compile step costs about 1 s CPU per run. The suite-level
  saving is in `results.md`.

## D-408: the recommended commands (AGENTS.md §8, proposal)

- Full suite: `uv run python tools/suite_queue.py --label <branch> -- pytest -n 10 --dist loadgroup -p no:randomly -p no:cacheprovider`
  (10 workers: user decision 2026-10-14; first proposed at 8)
- Targeted: `uv run python tools/suite_queue.py --targeted -- pytest <paths>`; only the affected tests:
  `... --targeted -- pytest --testmon <paths>` (pytest-testmon in the dev group, user-approved 2026-10-14; never the gate)

The worker count is set from the `-n 4 / 8 / auto` measurements in `results.md`.

## D-409: phase 3 rules (after the merge queue drains)

- Session-scope the expensive builds behind read-only or copy-on-write guards.
- Replace CLI subprocesses with in-process `main()` calls where a test does not test the process boundary.
- Mark genuinely slow tests `slow`.
- Add `-B` to the five core-test children that start with `-I` only (approved by the orchestrator).
- Fix the quadratic module-level string build in `tests/adapters/inspect/test_item28.py`.
- Fix any test that fails or flakes in parallel at its cause; never with retries.
