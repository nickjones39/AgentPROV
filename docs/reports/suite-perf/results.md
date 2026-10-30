# Suite performance: results (D-400..D-409)

These are the 2026-10-14 measurements from the suite-perf session. `baseline.md` has the serial baseline;
`decisions.md` has the decisions.

All runs were on the M2 Max (12 cores, 32 GB) while other sessions worked, so every wall time comes with its 1-minute
load average. CPU is the whole process tree's user + system time (`/usr/bin/time -l`). Load also inflates CPU
somewhat, through contention and cache misses.

## Full suite: before and after

| Run | Commit | Workers | Wall | Load | CPU | Peak RSS | Result |
|---|---|---|---:|---|---:|---:|---|
| Serial baseline | `c4fd0dc2` | 1 | **55 min 10 s** | 20–117 | 2,098 s | 2.8 GB | 6,911 passed, 128 skipped, 3 xfailed |
| Phase 2 gate | `f5ba6876` | 8 | 7 min 00 s | 8–24 | 2,273 s | 2.5 GB | 7,032 passed |
| Phase 2 repeat | `f5ba6876` | 8 | 13 min 18 s | 30–35 | 2,712 s | 2.2 GB | 7,032 passed (identical outcomes) |
| Gate fix | `46b7e754` | 8 | 5 min 59 s | 29–52 | — | — | 7,095 passed, 128 skipped |
| Phase 3 | `9c11256a` | 10 | **5 min 37 s** | 14–24 | 2,191 s | — | 7,166 passed, 129 skipped |
| Phase 3b | `7525bd57` | 10 | 5 min 34 s | beside a 6-CPU import | 2,354 s | 2.7 GB | 7,291 passed, 131 skipped, 5 xfailed |
| Pool groups | `c5463294` | 10 | 6 min 07 s | 23–32 | 2,454 s | 2.3 GB | 7,354 passed, 132 skipped, 5 xfailed |

None of the runs listed has a failure. The test count grew as other branches merged.

**Speed-up.**
- **Wall:** 55 min 10 s down to about 5.6 min, roughly 9.9× (90 % less). This overstates the gain, because the baseline
  ran at loads of 20–117. A quiet serial run on the current code (see "Not measured") gives the like-for-like figure.
- **CPU:** about the same as serial, between 4 % and 17 % higher. The speed-ups removed real work: collection fell from
  43 s to about 6 s per process, the schema compilation and template corpora saved about 200–300 s, and about 700 git
  calls are gone. Ten workers each collecting and importing, plus contention, add back about as much. The gain comes
  from using the cores, not from doing less.
- **The rest of the drain:** most branch suites through the queue took 5–8 min each, against 23–80 min before.

## What made it faster

| Change | Effect |
|---|---|
| pytest-xdist, `-n 10 --dist loadgroup`, with `serial` and `pools` groups (D-401) | Uses the cores; load-sensitive and pool-starting tests are bounded |
| Bytecode cache outside the trees (D-406) and precompiled `src/agentprov` for the workers (D-407) | Collection 43 s → 21 s, then about 6 s with the fixes below; about 0.1 s per worker spawn |
| `test_item28` noise strings built in linear time | About 7 s less per worker import (about 70 s CPU per gate) |
| Closed-schema tests compile their schema once | The inspect schema test: about 60 s CPU → 0.5 s |
| Template corpora and repositories copied per test (`test_tamper`, `fetch_support`, `history_support`, `test_gate_g0`) | About 50 s CPU and about 700 git calls fewer |
| Cached mappings (`_real_mappings`, `phase10d map_fixture`) returned as fresh copies; one `RuleRegistry` per mapper test | Repeated mapping and catalogue parsing removed |
| The tree's Unicode check in-process | About 10 s of `uv run` start-up removed |
| Pool groups sized to the host, `max(2, CPUs // 6)`, balanced by measured time | M2: 235 s / 230 s (was 203 s / 261 s); a 32-core host: 5 groups, the longest about 105 s |

**Developer lanes.**
- `pytest -n 10 -m "not slow"` deselects 193 of 7,427 tests: the 181 measured in `tests/slow_tests.txt` plus 12 that
  their own files mark. `tools/slow_tests.py` regenerates the list from `--durations=0` call times.
- `pytest --testmon tests/<area>` reruns only the tests whose code changed. In the trial, 7 of 228 tests ran in 0.5 s
  instead of 84 s.
- The full gate deselects nothing; `tests/unit/testing/test_slow_lane.py` checks this.

## Acceptance

- **Collected ids.** No run lost an id against the one before it. Every new id comes from a test file changed by a
  merge in between.
- **Outcomes.**
  - The two `-n 8` runs on `f5ba6876` were identical.
  - Each later gate was compared with the previous one: 0 outcome changes on common ids.
  - Every new skip or xfail belongs to a newly merged family:
    - the `test_the_branch_touches_only_the_family` skips of autogen, mcphunt, wirelog and geminicli;
    - mcphunt's RB-1 and RB-2 strict xfails, already routed.
- **One gate weakening, found and fixed.**
  - The per-test temporary `$AGENTPROV_HOME` also moved the default fetch cache. As a result, 11 pinned-tree tests
    skipped in every run from `f5ba6876` to the fix `d2f7b41c`, which put the cache back where it was.
  - The comparison with the baseline found it; the fix's gate restored the baseline's skip count.
  - The lesson: compare outcome sets after any isolation change.
- **Determinism.** The 3-, 4- and 8-worker determinism checks passed in every parallel run, inside the `serial` and
  `pools` groups.
- **Faults found in parallel runs were fixed at their cause, never with retries.** They were:
  - the guard refusing the bytecode cache;
  - the live-backend home being overridden;
  - `-n` without `loadgroup`;
  - the shared TMPDIR being allowed;
  - an inherited failed calibration;
  - unbounded default pools;
  - the fetch cache moving;
  - two write-guard bypasses from the bug pass: BF-3 (symlinks) and BF-4 (`mkdir` of an allowed file's parent).
- **Production code.** Nothing under `src/` changed in this work.

## The queue in use

| | |
|---|---|
| Suites run through `tools/suite_queue.py` on 2026-10-14 | 31 (25 green, 6 with their branches' own failures), from 16 worktrees |
| Wall per suite | 4.9–17.5 min (most 5–8 min; the longest ran beside heavy load) |
| Suites running at once | Always one, with no overlap seen |
| Order | FIFO by arrival, plus orchestrator-approved priority jumps |

Lessons, which D-427 (workflow-tools) now addresses:
- **A head held its slot lock while waiting for budget**, so a priority ticket could not overtake it. Admission now
  comes before the lock.
- **`--cpu` did not scale the memory reservation.** It now does.
- **Pgid reuse.** A dead holder's recorded process group could name an unrelated later group. The leader's identity is
  now verified before any wait or signal.

## Not measured

- **The worker-count and serial comparisons.** The `-n 4`, `-n auto` and extra `-n 8` runs were dropped at the user's
  request: each would have waited 1–2 hours behind the drain. The serial run on the current code is still to do once
  the queue drains.
- **A 32-core host (estimate, not measured).** For an M5 Ultra-class host (about 32 CPU cores, each about 1.7× an M2
  core):
  - about 3–3.5 min with two pool groups;
  - about 1.5–2 min with the host-sized groups that are now in place.
- **What to calibrate there:** `-n 16`, `-n 24` and `auto`, and the host-default pool size (`--jobs 0` = 32 workers on
  that host).

## Open items (handed to the orchestrator)

- **The live-backend fixtures leak `AGENTPROV_HOME`.** `tests/integration/test_run_live_*.py` set it with
  `os.environ[...]` in session fixtures, so later tests on that worker keep the live home. The files are touched by
  queued branches.
- **`test_semantics_reviewed.py` imports `test_semantics` by its bare name**, and that name exists in several
  directories, so targeted subsets fail at collection. The file is touched by queued branches.
- **Further work, if wanted:** the serial and `-n 10` measurement runs after the drain.
