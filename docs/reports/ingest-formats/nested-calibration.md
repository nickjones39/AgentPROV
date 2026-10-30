# Calibration of nested-archive reads (D-386; method of D-60/D-245)

Date: 2026-10-13. Branch `ingest-formats-3`.

**Setup.** Host: M2 Max, 32 GB, macOS arm64, CPython 3.14.8. The machine was shared with other sessions (load average
19–26 during the runs).

**Evidence (outside Git).** Everything is under `~/.agentprov/migration-work/ingest/`:
- `calib-nested/` holds the script `scripts/nested_calibration.py`, the logs `synthetic-run.log`,
  `synthetic-rerun-1.95.log`, `real-run.log` and `real-run-2.log`, and the scratch stores;
- `nested-probe/` holds the design-time probes;
- `neutrality/` holds the byte-neutrality check.

**Real staged bytes.** The calibration read the staged split zip 3-002 of control-arena (user-approved on 2026-10-13).
It was read into scratch stores, nothing was downloaded, and only counts, sizes, codes and timings were recorded.

## Method

- Each container job ran in a fresh T1 worker (`workers=1`, `jobs_per_worker=1`), with the request that
  `expand_containers` builds.
- **Worker CPU** is `RUSAGE_CHILDREN` measured after the worker exits.
- **Worker peak RSS** is the parent watchdog's sample.
- **Budget** is G.4.3's `with_expand_scaling(max_total_bytes)`: 540 s CPU and 1,080 s wall.
- **Parent peak** is the importer process's `ru_maxrss`, measured at checkpoints.
- The nested selection is a `logs/*.zip` (synthetic) or `**/*.zip` (real) child, with `max_member_bytes` 2 GiB and
  `max_depth` 3. Level-3 containers use the Inspect member patterns.

## Results

| Case | Job | Bytes returned | Worker CPU | Job wall | Worker peak | Parent peak |
|---|---|---:|---:|---:|---:|---:|
| Synthetic, inner 0.25 GiB (deflate level 0) | level 1 (inner zip streamed) | 271,099,756 | 1.8 s | 1.2 s | 62 MiB | — |
| Synthetic, inner 1.0 GiB | level 1 (streamed) | 1,076,490,988 | 2.7 s | 2.8 s | 61 MiB | — |
| | level 2 (inner zip from the store) | 2,627,080 | 1.1 s | 1.5 s | 47 MiB | — |
| Synthetic, inner 1.95 GiB | level 1 (streamed) | 2,100,009,012 | 4.0–4.3 s | 4.9–5.2 s | 61–62 MiB | +12 MiB over the harness |
| | level 2 | 2,627,080 | 1.6–1.7 s | 2.3–2.5 s | 47 MiB | |
| | level 3 (5 `.eval`-shaped containers) | 131,086 each | 0.4 s each | 0.4–0.6 s | 42 MiB | |
| **Real 3-002** (8 parts, 2,147,478,676 B) | level 1 (the 2,091,106,621 B nested zip streamed, plus 70 direct logs) | 2,148,379,877 | 4.2 s | 5.2–5.3 s | 74–76 MiB | 170 MiB (after the fix below; 2,114 MiB before) |
| | level 2 (535 nested `.eval`, up to 7.9 MB each, read whole) | 2,116,852,279 | 7.5 s | 11–13 s | 144 MiB | |
| | level 3 (the three largest nested `.eval`) | about 48 MB each | 0.5 s each | 0.6–0.7 s | 101–109 MiB | |
| | level 3, all 535 nested `.eval` (4 workers) | 2,103 selected, 3,156 not selected | — | 34–36 s in all | — | |

The real run had no `ingest.*` code at any level, and all 535 nested logs opened at level 3.

## Reading

1. **Worker memory is flat in the member size.** A streamed nested zip costs the same worker RSS at 0.25, 1.0 and 1.95
   GiB (about 61 MiB). The real 2.09 GB member costs 76 MiB (D-383: chunks of 1 MiB, never held whole). Level-2 and
   level-3 jobs hold one member at a time, as D-58 has them do. The real level-2 job peaked at 144 MiB.
2. **CPU and wall time: at least 70× headroom.** Streaming costs about 2 s of worker CPU per GiB, and a level-2
   expansion about 3.5 s per GiB. At the largest member a profile can declare (`NESTED_MAX_MEMBER_BYTES`, 2 GiB), that
   is under 8 s against 540 s, so the expand budgets of G.4.3 stay as they are.
3. **A T0 memory defect was found and fixed.** A returned member below the spool threshold (8 MiB) stays in the
   parent's memory until its job's result is stored. The real level-2 job returned 535 logs of up to 7.9 MB, and the
   importer process peaked at **2,114 MiB**.
   - This predates this branch: any zip with many 1–8 MiB members does it, up to `max_total_bytes`.
   - `io/workers.py` now caps what one job may hold in memory (`SPOOL_MEMORY_PER_JOB`, 64 MiB). Past it, a returned
     member spools to disk from its first byte.
   - The same run then peaked at **170 MiB**, with identical rows and objects.
   - The bound is **per job**, not parent-wide: `WorkerPool.run` returns a whole batch (up to 256 results) before
     the parent consumes any, so a batch can in theory still hold up to 256 × 64 MiB. A pool-wide budget (one counter
     over unclosed results) is pipeline-perf's D-414.
   - Test: `test_a_job_holds_at_most_its_spool_budget_of_returned_members_in_memory`.
4. **The parent's other costs.**
   - The synthetic harness itself used about 540 MiB (it cuts the input into 256 MiB parts); the expand added 12 MiB.
   - The streamed member's spool is an unnamed file in the store's `tmp_dir`, at most one member long (2.09 GB here),
     then copied into the store with its size and CRC-32 checked.
5. **The limits are confirmed.**
   - `NESTED_MAX_MEMBER_BYTES` 2 GiB: the largest observed member is 2,091,106,621 B, 2.6% below it. A larger nested
     zip would need its own decision; the store bound is `max_artefact_bytes`.
   - `NESTED_MAX_DEPTH` 3: the observed shapes need 3.
   - The ratio of every observed nested zip is about 1.0, so no ratio raise is needed.

## Byte neutrality on a stored corpus

Method: `recompute --out` on a copy of `ast-survey-agentharm-p10` (the stored container-dialect corpus), once with
origin/main's code (`2f4c12b`, exported into a scratch directory) and once with this branch. Both runs exited 0.

The two output trees differ only where predicted:
- `derivation.json`: the `expand` `engine_code_sha256`/`fn_digest` and the `aer` `engine_code_sha256`/`fn_digest`;
- `raw/members.jsonl`: the `fn_digest` field of all 1,691 rows. Every other field is equal.

Every AER, SEM, PROV, register and index byte and `corpus.json` is identical.
