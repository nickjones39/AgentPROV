# Pipeline performance: results (pipeline-perf, D-410–D-416, D-554)

Session: pipeline-perf. The Phase 1 profile is in `profile.md`, and the design notes for D-412, D-413 and D-414 are in
this directory.

- **Machine:** M2 Max (8 performance + 4 efficiency cores, 32 GB), CPython 3.14.8.
- **Load:** the machine was shared with other sessions' suites and imports (load 8–114). CPU-time figures are reliable
  under that load; wall times are labelled with the conditions they were measured under.
- **Data:** scratch clones only, under `~/.agentprov/migration-work/pipeline-perf/`. Counts and timings only.

## 1. What landed

| Decision | Change | Pushed | Byte identity | Digest move |
|---|---|---|---|---|
| D-410 | Rule catalogues parsed once per process, keyed by `(source, sha256 of the bytes)` | `e24bf772` | Mandate import before/after: 1,595 of 1,596 files identical; the only difference is `derivation.json` aer `engine_code_sha256`/`fn_digest` | aer engine (regen-batch item 32) |
| D-411 | The `migrate` engine is imported when `migrate` runs, not at CLI start-up | `e24bf772` | `--help` for the root and every command byte-identical | none |
| D-412 | The strict JSON loader skips depth checks that a byte count proves cannot fire | `e24bf772` | Mandate import 1,596 of 1,596 files identical; differential and property tests against the old path | none |
| D-413 | `validate --corpus` runs tiers 3–4 in T1 `validate` jobs | `da127648` | `validate` reports byte-identical in-process and with `--jobs 3` (§4) | none (`corpus/`, `io/`, `cli/`) |
| D-414 | The parent holds job results' frames as bytes under a pool-wide budget, with one spool file per batch; the importer reads results in two passes | `b57006d0` | §5 | aer engine (regen-batch item 42) |
| D-415 | Worker count: pools with a charge policy default to every logical CPU (calibrated) | pending | §6 | none |
| D-416 | Corpus reader: guarded stdlib JCS fast path, one default `IngestLimits`, register `rid` once | `db8f4829` | §8 | none |
| D-554 | Memory admission for pools with a charge policy (prov-perf's PROV-size model) | `db8f4829` | §8 | none |

Gates for every push: a full suite green on the pushed commit, or on its parent when only a clean, non-overlapping
merge of main followed (the user's rule, 2026-10-14), plus golden, gate D, compat and the C.16 vectors.

## 2. Import: CPU per stage (Mandate, 396 executions, in-process, CPU seconds)

| Stage | Base `c4fd0dc2` | + D-410 | + D-410 + D-412 |
|---|---|---|---|
| T1 `map` job | 58.1 | 2.7 | 2.1 |
| Rule-catalogue parsing (all callers; 8,851 → 2 parses) | 71.4 | 0.0 | 0.0 |
| T1 `prov` job | 296.5 | 197.8 | 186.8 |
| ↳ tier 4 | 264.4 | 181.8 | 172.3 |
| T0 seal (AerWriter + AER validator) | 9.4 | 6.6 | 5.3 |
| **Total** | **368.7** | **210.6** | **197.3** |

The `map` job and catalogue-parsing changes are the effect of D-410. Part of the `prov` and tier-4 drop is D-410 too
(`validate_prov`'s linkage check builds a registry per call). The rest is load variance between runs: the round trip,
which parses no catalogue, moved about 25% between runs.

ROPE, measured the same way: the `map` job fell from about 243 ms to about 10 ms per execution (§1 of `profile.md`).

## 3. `verify --level chain` (Mandate, CPU, three alternating runs each)

5.22–5.33 s → 4.76–4.88 s (−9%, D-412).

## 4. `validate --corpus` (D-413): in process against `--jobs 3`, under shared load (load 30–60)

| Corpus, mode | In process | `--jobs 3` | Report |
|---|---|---|---|
| Mandate (pre-D-31 scratch import), dev | 461 s | 249 s | identical, 1,272,391 B |
| Mandate (same), `--strict` | 663 s | 185 s | identical, 1,274,110 B |
| ROPE, `--strict --sample 300` (code at `2fbdd367`) | 674 s | 368 s | identical, 1,060,124 B |
| Mandate (drift-window import) on main + D-413 | 776 s | 269 s | identical, 1,412,569 B (failing rows) |
| ROPE, `--strict --sample 100` on main + D-413 | 310 s | 78 s | identical, 340,722 B |
| Mandate, fresh import on main + D-413, dev | 230 s | 148 s | identical, 1,272,391 B, all rows pass |

- **Failing paths:** these are byte-identical too. Rows failing from the pre-D-31 drift window (explained by the
  orchestrator) and from a profile edited in place (explained by regen-plan) were reproduced exactly by both paths.
- **Expected on an idle machine** (`profile.md` §5): tier 4 is about 95% of `validate --corpus`, so the speed-up is close
  to linear in workers. All 126k stored executions take about 20 CPU-h, so about 3 h at 8 workers. The 8-worker
  measurement comes with D-415.

## 5. Parent memory (D-414)

**Run:** through `suite_queue --class import`, under shared load (about 20).
- **Before:** `origin/main` `9999c41e`.
- **After:** the same plus D-414 (`1e7251e3` merge + `4e75e0f6`).
- **Mandate:** release mode. The ROPE subset ran in dev mode, because `--release` forbids `--limit`; the mode is the
  same before and after.
- **Synthetic deposit:** credleak-format cells built at run time, members stored uncompressed (deflated filler trips
  the `ingest.archive.ratio` guard, as it should).

| Case | Executions | Before vs after (`-j8`) | After `-j8` vs `-j3` | Parent RSS peak | Tree RSS peak | Wall `-j8` |
|---|---|---|---|---|---|---|
| Synthetic multi-execution, 24 files × 300 runs | 7,200 | 7,230 of 7,231 files identical | 7,231 of 7,231 | **1,191 → 674 MiB (−43%)** | 1,354 → 888 MiB | 381 → 418 s |
| ROPE, `--limit 1500` | 1,500 | 6,042 of 6,043 | 6,043 of 6,043 | 420 → 399 MiB | 2,187 → 2,097 MiB | 485 → 390 s |
| Mandate, release | 396 | 1,595 of 1,596 | 1,596 of 1,596 | 167 → 150 MiB | 1,146 → 1,129 MiB | 42 → 40 s |

- **The one difference** in every before/after pair is `derivation.json`'s `aer` `engine_code_sha256` and `fn_digest`
  (`adapters/runner/` is in that digest; regen-batch item 42). Every AER, SEM, PROV, register, index and manifest byte
  is identical.
- **Wall times:** they move in both directions under the load, so no throughput claim is made.
- **What remains in the parent** on the synthetic case is the batch's `_Unit` AER bytes, which are held until the prov
  stage (design §7.3). The frames that the D-323 calibration showed dominating are gone.
- **Also fixed** on this branch: a worker pool race. A successful result's stderr tail could miss the job's last bytes,
  which made `test_stray_stdout…` flaky under load. The last result of a worker now gets the tail read after the drain
  thread is joined (`4e75e0f6`; `io/` is in no digest).

## 6. Worker count (D-415)

**Setup:** calibrated on 2026-10-15 at `main` 2663d44d, as one exclusive queue ticket (10 CPUs, load 3–4). The decision
and the table are in D-415 (DECISIONS).

**ROPE, first 1,500 executions, wall time:**

| Workers | Wall | vs 3 |
|---|---|---|
| 3 | 476 s | 1.00× |
| 6 | 263 s | 1.81× |
| 8 | 223 s | 2.13× |
| 10 | 202 s | 2.36× |
| 12 | 193 s | 2.47× |

Beyond 8 workers the gains are smaller, because the extra cores are the efficiency cores.

**The full ROPE import** at 8 workers took 24.0 min; `profile.md` §4's model predicted 27. The recompute dry-run at 3
workers took 10.8 min.

**Time caps and memory:**
- The worst job used 3.1% of its time cap at 12 workers, against the one-third gate.
- The process tree peaked at 3.0 GiB.
- Size hints changed nothing, because memory was never the limit.

**Byte identity:** the corpora at 3, 6, 8, 10 and 12 workers and with hints are identical (6,043 of 6,043 files).

**Adopted (user, 2026-10-21):** pools with a charge policy default to one worker per logical CPU. The D-554 constants
are unchanged.

## 7. Not done, and why

- **The tier-4 round trip (65–81% of CPU)** is the `prov` library's encoder. Changing or upgrading it changes the
  library versions recorded in every validation row, so it is not byte-identical. Recorded; out of scope.
- **The second N-Quads encode** is inherent to `pv.roundtrip.graphs`, which compares two serialisations. It is not our
  call pattern; D-89 already removed the second parse.
- **Batch size:** 1,024 instead of 256 would gain 1–2% by the model. Not proposed.
- **Splitting every `cli/` module** into register and handler parts: about 0.1 s per call. Not worth the churn.
- **A faster JCS** needs a new dependency and a full differential proof. Noted only.

## 8. Corpus reader (D-416) and memory admission (D-554)

**D-416 time** (stored corpora, read-only, CPU seconds, before → after; the same rows and entries, identical
fingerprints):

| Corpus | `iter_index()` | `register()` |
|---|---|---|
| agentdyn-a-p10 (38,281 rows, 90,474 entries) | 5.6–6.1 → 2.8–3.1 | 9.3 → 2.6–2.8 |
| agentdojo-upstream-head-p10 (36,679 rows, 75,968 entries) | 4.3–4.5 → 2.6–3.2 | 6.9–7.6 → 1.8–2.2 |
| rope-p10 (10,791 rows, 37,594 entries) | 1.4–1.6 → 0.8–1.0 | 3.9–4.4 → 0.9–1.2 |

**D-416 evidence:**
- **Differential sweep:** the fast path writes exactly `rfc8785`'s bytes for 466,848 stored documents in 8 corpora (every
  index, register, origins and members line, plus sampled AER, SEM and PROV documents).
- **Unit tests:** they cover every code point as a value, every BMP code point and astral samples as keys, both stdlib
  encoders, the subclass, depth, cycle and recursion-limit cases, and Hypothesis differentials.
- **Independent review:** core review B checked the code against RFC 8785 and the `rfc8785` source and found 2 issues.
  - **A:** the guard ran outside the `try` near the recursion limit.
  - **B1/B2:** two mutants (`isinstance` in place of the exact int and dict checks) were not equivalent but no test
    caught them.

  Both were fixed in `087e66d6` and B re-confirmed.

**Byte identity** (scratch imports, D-416 at `087e66d6` against `de8cb649`, and D-554 against `7192947c`):
- **Mandate (release):** 1,596 of 1,596 files identical before and after, and at 8 workers against 3.
- **ROPE (first 1,500):** 6,043 of 6,043 files identical before and after, and at 8 workers against 3.
- **D-554 derive:** 1,596 of 1,596 files identical.
- **Reports:** the `validate --corpus` reports are identical, and `verify --level chain` passed on both sides (its output
  differs only in the elapsed-time line).
- **`derivation.json`:** unchanged everywhere, because no stage code digest covers the changed files.
- **Gap:** a ROPE `validate --strict --sample 100` comparison ran on neither side, because the script omitted the
  `--seed` that `--sample` requires.

**D-554** behaviour is covered by the admission unit tests and by the byte identity above. Its calibration is §6.

