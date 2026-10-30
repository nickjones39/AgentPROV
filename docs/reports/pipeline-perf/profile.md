# Pipeline profile: import, map, SEM, PROV, validate, verify (pipeline-perf Phase 1)

Session: pipeline-perf, branch `pipeline-perf`. Measured 2026-10-14 at base commit `c4fd0dc2`, then after D-410/D-412
as noted.

**Machine.** MacBook Pro, M2 Max: 12 cores (8 performance + 4 efficiency), 32 GB, macOS (Darwin 27.0.0), CPython 3.14.8
(uv). The worker isolation grade is `watchdog` (libproc sampler, no `RLIMIT_AS`).

**Load.** The machine was shared with several other sessions' test suites and imports. The load average ranged from
8.6 to 114 during the measurements.

**Method.** Wall-clock times would mostly measure the other sessions. Every number here is therefore **CPU time of one
process** (`time.process_time`):
- an in-process run (`--in-process`, with the importer's background prov thread made synchronous) of the real job
  functions, with per-stage timers wrapped around them;
- cProfile only to find hot spots, never for shares, because it inflates call-heavy code 2–3×.

**Data.** Corpora: clones under `~/.agentprov/migration-work/pipeline-perf/` (an APFS clone of `rope-p10.partial`;
Mandate imported from regen-plan's pinned input tree). Only counts, sizes and timings were recorded; no corpus text.

**Scripts.** Scratch scripts (not committed): `prof_import.py`, a per-stage CPU timer harness around the CLI;
`unit_costs.py`, per-execution post-AER costs on a stored corpus; `simulate.py`, a model of the importer's batch
schedule; and `bytediff.py`.

## 1. Where an import's CPU goes

### 1.1 Mandate: 396 executions, in-process, base `c4fd0dc2`

| Stage | CPU s | Share |
|---|---|---|
| **T1 `prov` job** (SEM + PROV + tiers 3–4) | 296.5 | 80% |
| ↳ tier 4 `validate_prov` | 264.4 | 72% |
| ↳↳ PROV-JSON → PROV-O round trip (`pv.roundtrip.*`) | 239.2 | 65% |
| ↳↳↳ `encode_nquads` ×2 (prov 3.2.2 serializer) | 151.2 | 41% |
| ↳↳↳ `parse_nquads` (rdflib) / `decode` / completeness / JSON load | 38.9 / 20.4 / 10.8 / 9.8 | |
| ↳ derive (`agentprov-prov/0.1`) | 21.8 | 6% |
| ↳ tier 3 (SEM validation) | 6.2 | 2% |
| **T1 `map` job** | 58.1 | 16% |
| **Rule-catalogue TOML parsing, all callers** (8,851 parses) | 71.4 | 19% (overlaps the rows above) |
| T0 parent: seal (AerWriter) + AER validator + finish + frames + writes | ≈ 13 | 3.5% |
| Total | 368.7 | |

### 1.2 ROPE: 300 executions (first 300 by label), in-process, base

| Stage | CPU s | Share |
|---|---|---|
| T1 `prov` job | 428.6 | 82% |
| ↳ tier 4 (round trip 356.7) | 389.7 | 74% |
| T1 `map` job | 72.9 | 14% |
| Rule-catalogue parsing (8,455 parses) | 79.5 | 15% |
| T0 parent serial | ≈ 17 | 3% |
| Total | 525.1 (1.75 s per execution) | |

### 1.3 ROPE: stratified sample of 2,000 executions, post-AER stages per execution

The sample is 200 per AER-size decile, seeded, on the clone of `rope-p10`.

| Stage | Total CPU over the sample | Share |
|---|---|---|
| T0 AER validator | 24.9 s | 1.1% |
| load AER / SEM annotate / tier 3 | 12.0 / 16.6 / 29.2 s | 2.6% |
| derive | 163.3 s | 7.4% |
| **tier 4** | **1,960.5 s** | **88.9%** |
| ↳ round trip | 1,783.1 s | 80.8% |

Per execution: mean 1.09 s, p50 0.89, p90 2.08, p99 3.19, max 7.27. Tier 4 costs about **2.5 µs per byte of
PROV-JSON**. ROPE's PROV is 4.37 GB (mean 405 KB, max 2.8 MB). Extrapolated, ROPE's post-AER stages are **3.3 CPU-h**.

## 2. Hot spots, ranked

1. **The tier-4 round trip (65–81% of all CPU).**
   - Where: `validate/roundtrip.py` over the `prov` library's `ProvRDFSerializer.encode_document`, which rebuilds a
     relation's qualification head once per attribute (2.55 M head builds for 245 k relations on Mandate). AgentPROV
     relations carry many `apv:` attributes.
   - Both encodes are inherent to the check. One encodes the document; the other encodes the model decoded back from
     it, and `pv.roundtrip.graphs` compares the two. D-89 had already removed the second parse.
   - A faster library would change the `prov`/`rdflib` versions recorded in every validation row, so it is **not
     byte-identical: out of scope.**
   - The lever is parallelism: in the import and `derive` it already runs in T1 `prov` jobs; in `validate --corpus`
     it does not (D-413).
2. **Rule-catalogue reparsing (15–19%).**
   - `load_catalogue` parsed the TOML on every call: the twin lookups in `code_verification._resolve`, a fresh
     `RuleRegistry` per job and unit, and `MapContext._version`. That is about 22 parses per execution.
   - **Fixed by D-410:** map 58.1 → 2.7 s on Mandate; ROPE map about 10 ms per execution after, about 240 ms before.
3. **The strict JSON loader's depth passes** (`_prescan_depth` regex scan plus `_walk`).
   - 57% of `verify --level chain` under cProfile.
   - **D-412:** skip both where a byte count proves they cannot fire. CPU −9% on verify chain; under 1% of an import.
4. **JCS (pure-Python `rfc8785`)** in `prov/engine._assemble`, `validate/prov._canonical` and `aer/canon.dumps_line`.
   - About 2–4% of an import.
   - Not changed: the canonical bytes are the identity of everything. A faster JCS needs a new dependency (the user's
     yes) and a full differential proof. It is noted, not proposed.
5. **The parent's serial work** (seal with the AerWriter validator, AER validator, finish, frames, writes): about 3%
   of CPU. It is not a bottleneck (§4).
6. **Worker start-up:** about 0.5 s CPU per spawn.
   - Mostly TOML parsing of the semantics profiles that `provjob` preloads. Bytecode compilation is minor.
   - At 64 jobs per worker this is under 0.5% of an import.
7. **CLI start-up:** 0.65–0.83 s for `agentprov --help`. `cli.main` imported 290 modules.
   - **D-411** (lazy migration-engine imports): cli.main plus the parser 0.27 → 0.24 s, `--help` 0.30–0.37 s.
   - A further split of `cli/` was judged not worth it.

## 3. `validate --corpus` and `verify --level chain`

- **`validate --corpus`** runs every tier in the CLI process. 95% of it is tier 4 and 86% the round trip (cProfile, 60
  Mandate executions). It costs 0.69 s per execution on Mandate (274 s predicted against the 291 s measured by
  regen-plan) and about 0.97 s on ROPE. Across all stored corpora (§5) that is about 20 CPU-h on one core.
  → **D-413** (T1 `validate` jobs).
- **`verify --level chain`** (Mandate, about 11 s wall): the strict loader (57% under cProfile) and re-canonicalising AER
  lines through JCS. → D-412 (−9% CPU).

## 4. The flat `-j8`/`-j3` scaling (regen-plan's ROPE recompute: 5,520 s against 6,051 s)

The hypothesis was a serial parent. The measured costs do not support it.

**Model.** A discrete-event model of the importer's real schedule (`_Pipeline.run`):
- the map pool runs batch k (W workers, list scheduling, a barrier);
- the parent seals batch k serially;
- it waits for prov batch k−1 and finishes it serially;
- it submits prov batch k to the second pool.

Input: ROPE's 2,000-execution per-unit costs resampled to 10,791, map at the D-410 rate, and the measured seal and
finish costs.

| W | B = 64 | B = 256 (default) | B = 1024 | No-barrier ideal |
|---|---|---|---|---|
| 3 | 68.7 min (97%) | 67.6 (98%) | 67.6 (98%) | 66.4 |
| 6 | 36.9 (90%) | 34.9 (95%) | 34.7 (96%) | 33.2 |
| 8 | 29.2 (85%) | 26.8 (93%) | 26.5 (94%) | 24.9 |
| 12 | 21.8 (76%) | 18.8 (89%) | 18.3 (91%) | 16.6 |

The batch barriers and the serial parent cost 5–7% at W = 6–8, so they do not explain a flat curve. What does:
- the `-j8` run's load average of about 28 on 12 cores (other sessions' suites and imports);
- the M2 Max's 4 efficiency cores (the model assumes 12 equal cores);
- before D-410, about 0.7 CPU-h of catalogue reparsing in ROPE's map stage.

The `-j3` run at load 2.6–6.6 (101 min) is within about 50% of the model's 68 min, which takes no account of the slower
cores or the re-map's pre-D-410 parsing. **A real pool run in a quiet window should confirm this**, with throughput and
RSS against W, for the worker-count calibration (D-415, pending the window).

## 5. What this means for the regeneration round (estimates; machine otherwise idle)

Post-AER CPU scales with PROV bytes: about 2.7 µs per byte across all post-AER stages (ROPE). The stored
`agentprov-prov/0.1` volume of the current corpora:

| Corpus | Stored PROV |
|---|---|
| agentdyn-a | 11.77 GiB |
| head | 5.62 GiB |
| rope | 4.07 GiB |
| 2024-06 | 2.63 GiB |
| adprov-v1 | 2.37 GiB |
| survey-agentdojo | 0.56 GiB |
| agentharm | 0.14 GiB |
| mandate | 0.05 GiB |
| **Total** | **27.2 GiB (about 29 GB)** |

- **Import (expand + map + SEM + PROV + tiers 3–4):** about 22 CPU-h, nearly all post-AER.
  - At W = 8 with the measured efficiency, about **3–4 h** of wall time for the whole round on the M2 Max.
  - Allow up to 1.5× for the efficiency cores and for measurement under load, so 3–6 h, against regen-plan's
    15–19 h. That estimate was made from runs under load, before D-410.
- **Full `validate --corpus` of every corpus with D-413:** about 20 CPU-h, so about 3 h at W = 8.
  - This repeats the import's own tiers 3–4.
  - Full validation (instead of sampled, F-3) becomes realistic. It is the user's call.
- **M5 Ultra (proposal, unmeasured):** about 3× the performance cores, so roughly 1–1.5 h per stage. Calibrate there.

## 6. Parent memory

- Measured by D-323 (runner session): 215 → 982 MiB on the 105.7 MiB MCPHunt document. 144.1 MiB of JSON frames are
  held decoded until the file is processed.
- regen-plan's ROPE runs: parent peak 829–910 MiB.
- Causes: decoded frames per `JobResult`, a whole batch of results returned at once, 8 MiB in-memory member spools,
  and `split_unit_frames` materialising every unit.
- **D-414** (design, reviewed by runner, deferrals and ingest-formats-3): keep frames as spooled bytes and process them
  in two streaming passes after `DONE`, keeping the D-321/D-323/D-218 hold semantics.
- To build after D-323, ingest-formats-3 and deferrals-carved-hold land. Its RSS measurement waits for the quiet
  window.

## 7. Decisions (proposals for the user)

| Decision | Change | Status |
|---|---|---|
| D-410 | Catalogue cache | Built |
| D-411 | Lazy migration-engine imports in the CLI | Built |
| D-412 | Loader depth fast path | Built; deferrals-reviewed |
| D-413 | `validate` job kind | Built on `pipeline-perf-d413`; runner- and deferrals-reviewed |
| D-414 | Parent frame spooling | Design, reviewed |
| D-415 | Import worker-count calibration and presets | Pending the quiet window |
| D-416..D-419 | | Unused |
