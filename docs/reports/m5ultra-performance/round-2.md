# Mac Studio M5 Ultra: performance round 2 (2026-10-28)

Session perf-round-2 (branch `claude/perf-round-2-d493a2`), coordinated by the Mac Studio orchestrator. Brief:
`~/.agentprov/handoff/m5ultra-performance-round-2.md`. Machine: 36 cores (12 performance, 24 efficiency), 256 GB,
`AGENTPROV_HOME` on its own APFS volume. Decisions D-890..D-895 (D-896..D-899 reserved, unused).

**Bottom line**

| Item | Result | Commit / decision | Class |
|---|---|---|---|
| 1 recompute/validate scaling | The 117.6 s (j3) / 322.6 s (j8) gap does not reproduce as worker scaling; it was a cold tier-4 cache. Real limits were found and the class-0 ones were fixed. | — | — |
| 1a temp trees on the source's volume | Hard links work again (3,253 linked, 0 copied); the speed effect is negligible | `60982880`, D-891 | 0 |
| 1b validate pipelining | j8 −28 %, j16 −21 %, j4 −40 % (quietest pair) | `99b08a0c`, D-893 | 0 |
| 1b derive/recompute batch follows the workers | j16 −20 % (79.7 → 64.1 s), j8 −5 % | `f0f00b52`, D-895 | 0 |
| 1c tier-4 cache cap setting | `compute.validation_cache_gib`; 32 GiB recommended here | `7fbfa091`, D-894 | 0 |
| 1 the parent's floor (~63 s on the small corpus) | persistent workers, no fsync in throwaway trees, AER validation in the worker | held until the round-1 seal | 1 |
| 2 several suites at once | 2 × `-n 24`: 1,231 s each against 379.6 s alone (62 % worse than back to back); 3 × `-n 10`: 1,106 s against 3 × 335.4 s (10 % worse) | keep 1 suite slot | — |
| 3 suite scheduling | `worksteal` rejected (breaks the `serial` group); SEC-22 out of `serial` measured without gain and rejected (D-401 unchanged) | D-892 (rejected) | — |
| 3b suite temp on the `AGENTPROV_HOME` volume | rejected (the pre-check guard refuses it; no system-time gain) | — | — |
| 4 lower QoS for bulk jobs | rejected: the suite got slower (566 → 585 → 616 s) | — | — |
| 5 parallel `withhold_scan` | 44–48 s → 7.3 s at 16 workers | `6fd15ad8`, D-890 | 0 |

Outputs stayed byte-identical at every point measured (invariant 4): every `recompute --dry-run` reported 3,243
(small) or 18,241 (large) identical and 0 unexplained, at every worker count and batch size; every validate report
had byte-identical rows; every `withhold_scan` result had the same fingerprint.

## How it was measured

- **Code.** Item 1 baselines ran main's code from a pinned scratch worktree at `9e7e990c` (main `49898828` plus item 5,
  which no measured command uses). Before/after pairs ran from pinned worktrees at the exact commits named, so later
  edits could not change a run.
- **Harness.** One JSON line per run: wall time, children's user and system time, and samples every 0.5 s of the
  process tree's summed CPU, the parent's CPU (from the second batch of runs on) and the whole machine's CPU, plus the
  1-minute load at the start. The queue's `--status` was saved next to every timed run. Suite runs also logged
  per-test start and stop per xdist worker.
- **Queue.** Main's `tools/suite_queue.py` by absolute path, with the user's priority jump (`--before-head`).
  - From 14:16, by the user's rule: runs at `--jobs` 1–4 reserved what they used, beside other work, and the `--jobs`
    8/16 points and the two-suite test ran in one exclusive window (16:24–17:07; machine CPU 3–11 for item 1).
  - Wave 2 has the machine 21:00–08:00.
- **Load.** Most shared runs saw load averages of 20–35, with wave-2 imports and pre-release jobs alongside, so their
  timings are noisy. The conclusions rest on the exclusive window and on paired runs; each table gives its conditions.
- **The tier-4 cache is a confound.** A miss costs ~4× a hit. One large corpus evicts another's entries from the
  shared 2 GiB cache, so a run can turn cold between two "warm" runs. Each cold run is identified by its user time
  (~1,100–1,700 CPU-s against ~200–350 warm) and excluded from comparisons.

## 1. recompute, validate and derive with more workers

### Reproduction (small corpus `ast-survey-agentdojo-rg2`, 3,243 executions; main's code)

`recompute --dry-run`, warm cache, 13:59–14:09 (load 4–12, exclusive ticket):

| `--jobs` | 1 | 2 | 3 | 4 | 8 | 16 |
|---|---|---|---|---|---|---|
| wall (s) | 209.6 | 131.9 | 105.7 | 94.0 | 72.4 | 86.5 |
| system (s) | 28.9 | 31.0 | 39.0 | 42.3 | 86.1 | 262.7 |
| tree CPU (mean) | 0.93 | 1.55 | 2.05 | 2.31 | 3.77 | 6.41 |

- **No slowdown at j8.** The cold warm-up run at j8 took 199.3 s (1,197 user CPU-s), and j3 with
  `--no-validation-cache` took 400.9 s. The pre-release report's 322.6 s at j8 is most likely a cold cache plus load.
- **What is wrong:**
  - scaling flattens after j4;
  - j16 is slower than j8, with system time growing with worker starts (about 1 s each);
  - the parent saturates one core.
- **Large corpus** (`agentdojo-upstream-2024-06-rg1`, 18,241 executions; load 31–34):
  - j4 (cold warm-up) took 2,770 s, and j1 2,914 s. Both 18,241 identical, 0 unexplained.
  - The queue's 2 h run timeout stopped the j2 step. j8/16 were not run, to keep the exclusive window short.

### Where the time goes (cProfile of the parent, j3 and j16; main thread)

- The default `recompute` **re-maps from the stored raw objects**: the parent seals every AER and runs the AER
  validator twice (cumulative ~137 s profiled).
- `RawObjectStore.put` writes and fsyncs every object of the throwaway dry-run tree: 9,739 puts, ~1.7 ms each, fsync
  bound. The cost is the same on both volumes (5,000 puts: 7.9–9.9 s on each).
- The tier-4 cache hints are read serially (35 s).
- Every worker is retired at the end of each 256-unit batch, and teardown waits for each exit (107 s).
- Parent CPU: mean 0.86–0.87, p90 1.0 at j3 and at j16.

### Fixes (class 0)

**1a. Temporary trees on the source's filesystem (D-891).** A dry-run or rederive tree in the system temporary directory
could not hard-link raw objects across volumes. They now link (3,253 linked, 0 copied).

- The bytes saved are small: 49 MB on the small corpus, 223 MB on the large one.
- The end-to-end A/B (6 runs, load 26–35) ranged from 181 to 432 s per arm. That is too noisy to show a gain, and
  none is claimed.

**1b. validate overlaps staging and the pool (D-893).** Main's code before, `c2369e48` after (same as `99b08a0c`):

| Point | Before | After | Change | Conditions |
|---|---|---|---|---|
| `--jobs 8` | 43.5 s | 31.5 s | −28 % | exclusive window, machine CPU 3–5 |
| `--jobs 16` | 46.7 s | 37.0 s | −21 % | exclusive window, machine CPU 5–7 |
| `--jobs 4` | 58.8 s | 35.3 s | −40 % | load 11–13 (quietest pair) |
| `--jobs 4` | 223.9 s | 101.3 s | — | load 28–32 |

The parent's mean CPU rose from 0.59 to 0.95. The rows were byte-identical in all seven reports. One `--jobs 4` pair
was discarded: its "after" run found the cache cold.

**1b. The batch size follows the worker count (D-895):** 64 units per worker, between 256 and 1024. Exclusive window,
system time in brackets:

| Workers | Batch 256 | Batch 1024 | Batch 4096 |
|---|---|---|---|
| 8 | 66.2 s (97 s) | 63.0 s (58 s) | — |
| 16 | 79.7 s (334 s) | 64.1 s (141 s) | 65.5 s (102 s) |

**1c. A cap for the tier-4 cache (D-894).** The `compute.validation_cache_gib` setting applies to every command that
uses the cache. The user chose 32 GiB for this machine: `agentprov settings set compute.validation_cache_gib 32`, to
be applied by the user once it is on main. The built-in default (`validate/cache.py`, validation scope) stays 2 GiB
until after the seal.

### Next round's candidates (class 1: designed, not built until after the round-1 seal)

The ~63 s floor on the small corpus is the parent process. Each lever below changes a file in a stage scope, so it moves
stage code digests. Each would need the usual proof: `recompute --dry-run` 0 differences at two worker counts, and the
golden and compat gates.

1. **Workers that live across `WorkerPool.run` calls** (`io/workers.py`; AER scope).
   - Today every `run` ends by retiring its workers, so each 256-unit batch and each `withhold_scan` container starts
     fresh `python -I -B` processes: about 0.6 s wall and about 1 s of system time each.
   - Design:
     - the pool keeps idle workers between calls, up to `jobs_per_worker` (64, the G.4.7 recycling limit);
     - it retires them in an explicit `close()` (a context manager) or when a call changes the limits;
     - a worker's per-job limits are re-armed per job as today.
   - Expected: most of the remaining spawn cost at `--jobs 16` (system 141 s at batch 1024), and the per-container start
     in item 5's walk.
   - Risks:
     - a worker's state outliving one batch (the job table is closed, so only caches);
     - memory growth, already bounded by the D-554 lifetime-peak retirement.
2. **No fsync in a throwaway tree** (`raw/store.py`; AER scope).
   - A dry run writes and fsyncs every object of a tree it deletes afterwards: 9,739 puts at ~1.7 ms each (about 17 s of
     the parent's serial time on the small corpus).
   - Design: a `RawObjectStore(durable=False)` that keeps the temp-and-link publish (atomicity) but skips `fsync`, used
     only by `--dry-run` and `verify --level rederive` trees. A sealed or `--out` tree never uses it.
3. **AER validation in the T1 job** (`aer/`, `adapters/runner/`; AER scope).
   - The re-mapping parent runs the AER validator for every execution (twice in a re-map: importer and derive).
   - Design: the `prov` job, which already parses the AER, returns the validator's report alongside its outputs. The
     parent keeps only the comparison.
   - This moves the largest serial block (~137 s cumulative in the j3 profile) onto the workers.
4. **A larger built-in tier-4 cache default** (`validate/cache.py`; validation scope). The setting from D-894 covers
   this machine until then.

Also not done (class 0, unmeasured): a host-sized `POOL_BATCH` for validate, like D-895 for derive.

## 2. Several suites at once

| Run | Wall | User / system CPU-s | Tree CPU (mean) | Machine CPU (mean) |
|---|---|---|---|---|
| One `-n 24` suite alone (16:40, exclusive) | 379.6 s | 2,821 / 3,881 | 15.4 | 16.4 |
| Two `-n 24` at once (16:47, exclusive) | 1,230.9 s each | 3,829–4,213 / 8,934–9,411 | 9.9 each | 20.9 |

- Back to back, the two would take 759 s. Together they took 1,231 s, which is 62 % worse. Every test passed in both.
- The machine was not CPU-bound (about 21 of 36 CPUs in use), but each suite's system time more than doubled. The limit
  is kernel work: process creation (each T1 worker is a fresh `python -I -B`) and file churn.

**The user's target, 3 × `-n 10`** (round 1 only, by the user's choice). It ran 2026-10-29 06:48–07:12, in an exclusive
ticket (34 CPUs) queued once wave 2's DTap import had finished; nothing else ran. One suite alone, then three at once
from three pinned checkouts of `9e7e990c`:

| Run | Wall | User / system CPU-s | Tree CPU (mean) | Machine CPU (mean) | Load at start |
|---|---|---|---|---|---|
| One `-n 10` suite alone | 335.4 s | 1,856 / 1,345 | 7.5 | 8.3 | 8.3 |
| Three `-n 10` at once | 1,086.7 / 1,105.9 / 1,105.9 s (1,106 s in all) | 2,991–3,221 / 4,549–4,773 | 6.3 each | 19.7–20.1 | 16.5–22.0 |

- Back to back, the three would take 1,006 s. Together they took 1,106 s: 10 % worse, with no gain anywhere in the
  range. Each suite took 3.3 times as long as alone (18 min against 5.6 min), so every waiting gate would finish later.
- Every suite passed: 11,277 passed and 111 skipped in all four runs. `test_worker_isolation`, SEC-22 and the
  rlimit and timeout tests passed too. The two `RLIMIT_AS` tests skip on macOS, as they always do.
- The pattern is the same as with two suites. About 20 of 36 CPUs were busy. Each suite's system time rose from 1,345
  to ~4,600 CPU-s (3.4 times), while user time rose only 1.6–1.7 times. Disk traffic scaled linearly: 14,112 MB alone,
  41,730 MB for the three. The limit is kernel work, not cores or disk.
- **Decision (the user's rule, 2026-10-28):** several suites at once are slower than back to back, so the queue keeps
  1 suite slot. There is no queue change and no design note. Rounds 2 and 3 were not run.

## 3. Suite scheduling

**Per-worker timelines** (three `-n 24 --dist loadgroup` suites at `9e7e990c`, load 25–35: 432.8 / 445.8 / 443.3 s):

- The `serial` group runs on one worker for the whole suite and is always the last to finish (372–387 s).
- Every other worker finishes within about 20 s of the others (339–359 s).
- About 60 s pass before the first test starts, while 24 workers collect 11,388 tests. One collection alone takes 27 s.

**`--dist worksteal`:** 353.4 / 436.6 / 390.4 s (mean 393.5 against 440.7, −11 %), every test green. But it ignores
the groups: the `serial` tests ran on 10 workers, up to 5 at once. **Rejected.**

**Moving SEC-22 determinism out of `serial` (D-892): measured, then rejected by the user.**

- `test_sec22_derive_determinism.py` is 214 s of the group's ~386 s, and it is an "own pools" file. The flake the tuning
  session hardened is in `test_worker_isolation.py`, which was never moved.
- Three rounds, `bb34cb1a` against the same tree with the move (`540f2aaa`), `-n 24`, loads 18–34:

  | Round | Before | After |
  |---|---|---|
  | 1 | 504.5 s | 502.2 s |
  | 2 | 470.9 s | 469.5 s |
  | 3 | 461.2 s | 466.5 s |

- `serial` stopped being the tail: it ended at 281–307 s instead of 368–406 s. But the median worker end moved from
  339–375 s to 369–402 s, so there is no gain. Under load the suite is bound by its total work and kernel contention.
- The user's decision: drop it, and keep D-401 unchanged.
- Unrelated: one "before" run failed in a queue test, `test_an_admitted_job_waiting_for_the_lock_yields_to_a_priority_job`.
  It was a race in the test: it read a running record that the job under test had just removed. Fixed in `1739c0c9`;
  the 200-run proof is below.
- **The queue-test race, proven (18:39–18:51, load 14–36).** The test ran beside a `-n 24` suite that the ticket
  started as load (the suite passed, 646 s), 8 runs at a time, old and fixed versions interleaved in batches of 25:

  | Version | Passed | Failed |
  |---|---|---|
  | old (`bb34cb1a`) | 199 | 1 (run 46: the same `FileNotFoundError` on a vanished record) |
  | fixed (`1739c0c9`) | 200 | 0 |

  `suite_queue.py` itself is unchanged.

**3b. Suite temp directories on the `AGENTPROV_HOME` volume:** two rounds, `TMPDIR` and `--basetemp` under
`~/.agentprov/tmp`. **Rejected.**

- 57 tests failed both times: the pre-check tools rightly refuse output inside the real `~/.agentprov` under pytest.
- System time was equal on both volumes: 5,388 against 5,201 s, and 4,615 against 4,597 s.
- pytest's own cleanup of old numbered basetemps (one collect-only run spent 190 s deleting 212k files) is real, but
  the old trees found at the time were transient; nothing stale was left to clear.

## 4. Lower QoS for bulk jobs

A `-n 24` suite (pinned tree) beside two bulk jobs. Each bulk job loops `recompute --dry-run --jobs 8` on the small
corpus as a stand-in for an import. 17:32–18:09, load 18–22, one run per variant, every suite green:

| Bulk jobs at | Suite wall | Bulk recompute (median) |
|---|---|---|
| default | 565.9 s | 228 s |
| `taskpolicy -c utility` | 584.8 s | 244 s |
| `taskpolicy -c background` | 616.5 s | 306 s |

Clamping the bulk jobs made both the suite and the bulk jobs slower. This is consistent with §2: the contention is
kernel work, not core placement. **Rejected:** no QoS option in the queue wrapper.

## 5. `withhold_scan` in parallel (D-890)

72 synthetic zips: 8 deflated members each, every fourth with a nested zip, 16 canary hits. Same worker code; 3
repeats after, 2 before; load 8–19:

| Workers | Before (`49898828`) | After (`9e7e990c`) |
|---|---|---|
| 1 | — | 44.9 s |
| 4 | 44.5–47.8 s | 13.9 s |
| 16 | — | 7.3 s |
| 36 | 44.1–46.9 s | 10.0 s |

The fingerprint (hits, unscanned, partial) is identical at every point.

## Housekeeping

These scratch outputs are listed for the user's ok (Trash only):

- four `perf-r2-store-*` directories, 23 MB each (two in `/var/folders/…/T`, two in `~/.agentprov/tmp`);
- `~/.agentprov/tmp/perf-r2-suite-tmp` (7.2 GB, item 3b);
- the session's ten pinned scratch worktrees under its scratchpad (333–345 MB each, about 3.4 GB), also listed as git
  worktrees.
