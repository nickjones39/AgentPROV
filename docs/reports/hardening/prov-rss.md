# Memory of the `prov` job on the longest DTap runs (phase 12b, D-55)

Date: 2026-10-12. Branch `phase-12b` on `main` @ `2c419e9` (after round-trip step 2, D-89, and D-131). Host: M2 Max,
32 GB, macOS arm64, CPython 3.14.8. The machine was shared with other sessions (load average 40–110), which inflates
wall times by about 2–3× against the bench's idle runs; memory peaks are not affected. Scripts and raw results:
`~/.agentprov/migration-work/phase12b/prov-rss/` (`measure_prov_rss.py`, `candidates.json`, `run1/results.jsonl`,
`diagnose.jsonl`). No network; staging and the phase-10b sample cache were read only.

## Method

- **Selection** from the DTap census of all 67,816 runs (`phase10b/census/c03_records.jsonl`): the 6 longest runs by
  steps, the 6 longest by steps × agent calls (they coincide), the 6 largest files, and the two LFS objects (the runs
  D.16.18 item 14 reported over 2 GiB before D-89). 14 runs. The round-trip bench's "largest DTap" (`bda-4`, 153 steps)
  is the largest *file*, not the longest run.
- **Mapping:** `map_artefact` with profile `dtap-bench`, as the bench did (no task-config join).
- **Measurement:** the real `prov` job (SEM `dtap.tools@1`, derivation, tiers 3–4, release mode) in a real T1 worker,
  one fresh worker per run (`workers=1, jobs_per_worker=1`), under 16 GiB RSS and 3,600 s CPU/wall so that nothing is
  killed. The peak is the parent watchdog's own sample (`JobResult.peak_rss_bytes`), the value the cap is compared with.

## Results

| Run (`DTap-Bench-Agent-Trajectories` path) | Chosen by | Steps | AER records | AER MB | PROV MB | Peak MiB | MiB per PROV MB | Wall s | Outcome |
|---|---|---|---|---|---|---|---|---|---|
| `openclaw/gpt-5.2/customer-service/malicious/direct/bulk_destructive_actions/bda-4_001/20260320_095520.json` | size | 153 | 317 | 9.0 | 10.9 | 989 | 90 | 117 | pass |
| `openclaw/gpt-5.2/customer-service/malicious/direct/pii_disclosure/pii-4_001/20260320_101615.json` | steps | 1,557 | 3,126 | 7.5 | **991.2** | 4,523 | — | 369 | `worker.limit.output` |
| `openaisdk/gpt-5.2/finance/malicious/indirect/excessive_trading/10/20260327_183731.json` | steps | 996 | 1,342 | 1.0 | 68.3 | 446 | — | 19 | fail: `pv.prov_structure.not_json` |
| `openaisdk/gpt-5.2/workflow/benign/325/trajectory.json` | steps | 582 | 708 | 0.4 | 7.4 | 639 | 87 | 57 | pass |
| `openaisdk/gpt-5.4/workflow/benign/111/trajectory.json` | steps | 552 | 688 | 0.5 | 8.8 | 821 | 94 | 46 | pass |
| `openaisdk/gpt-5.2/workflow/benign/132/trajectory.json` | steps | 544 | 652 | 0.5 | 6.3 | 598 | 95 | 33 | pass |
| `claudesdk/claude-sonnet-4-5/windows/benign/30/20260401_092943.json` | steps | 491 | 748 | 7.9 | 30.1 | **2,518** | 84 | 138 | pass |
| `claudesdk/claude-opus-4-6/windows/benign/11/20260328_002148.json` | size | 241 | 493 | 10.2 | 28.8 | **2,293** | 80 | 182 | pass |
| `claudesdk/claude-sonnet-4-5/windows/benign/41/20260401_104546.json` | size | 467 | 712 | 8.9 | 25.3 | 1,860 | 73 | 128 | pass |
| `claudesdk/claude-sonnet-4-5/windows/benign/26/20260401_085012.json` | size | 363 | 556 | 8.7 | 16.8 | 1,384 | 82 | 99 | pass |
| `claudesdk/claude-sonnet-4-5/windows/benign/23/20260401_080748.json` | size | 355 | 544 | 8.6 | 16.2 | 1,328 | 82 | 88 | pass |
| `claudesdk/claude-sonnet-4-5/windows/benign/68/20260401_154201.json` | size | 447 | 682 | 8.5 | 24.0 | 1,949 | 81 | 366 | pass |
| `claudesdk/claude-sonnet-4-5/windows/benign/32/20260401_095722.json` | LFS | (LFS) | 748 | 12.7 | 29.5 | **2,282** | 77 | 289 | pass |
| `claudesdk/claude-sonnet-4-5/windows/benign/49/20260401_113303.json` | LFS | (LFS) | 718 | 11.0 | 29.2 | 1,796 | 62 | 536 | pass |

(The census counts the LFS runs as their 133-byte pointer files, hence no step count.)

## Reading

1. **Peak memory scales with the PROV size, not the file size:** about 80–90 MiB per MB of PROV-JSON (62–95 over the
   twelve completed runs). A 1.0 MB AER of 996 steps gives 68 MB of PROV; a 10 MB AER of 153 steps gives 11 MB.
2. **Under the old 2 GiB cap** (watchdog trigger about 1.52 GiB on this host), five completed runs would be killed
   (1,796–2,518 MiB) and `benign/41` (1,860 MiB) too. Under the **4 GiB** default (trigger about 3.5 GiB) every run that
   completes today fits, with 1.4× headroom over the largest (2,518 MiB).
3. **Two runs fail for reasons a memory cap does not fix** (routed to the validator owner, `validate/`):
   - `excessive_trading/10`: its PROV-JSON is 68,338,798 B, over the 64 MiB `max_json_bytes` of the default
     `IngestLimits`, so tier 4's `strict_json_loads` refuses it (`pv.prov_structure.not_json`, the only failing check;
     in-process diagnosis). It therefore never reaches the round trip; at about 85 MiB per MB the full tier 4 would need
     about 5.7 GiB, more than the 4 GiB default.
   - `pii-4` (1,557 steps): the worker stopped on the output cap (`worker.limit.output`) after reaching 4.5 GiB, which
     means its PROV-JSON exceeds the 256 MiB `max_member_bytes`: an in-process derivation gives **991,220,960 B** of
     PROV-JSON (657 s, 4.0 GiB for the derivation alone). At the measured scaling its tier 4 would need on the order of
     80 GB; no declared cap up to the 16 GiB ceiling makes it fit.
4. **Wall time:** `benign/49` took 536 s and `benign/68` 366 s under load ~55–70; the `prov` job's wall limit is 600 s
   and its CPU budget 300 s. On an idle machine these are about 2–3× shorter (the bench's `bda-4`: 30–47 s against 117 s
   here). Not changed by D-55; to be watched in the step-4 import (a run over a time limit is registered
   `worker.limit.cpu`/`wall` with its sealed AER kept).

5. **How many runs are this long.** Census step counts over all 67,816 runs: 66,119 under 100 steps, 1,542 at 100–199,
   111 at 200–299, 39 at 300–499, 4 at 500–999 and 1 (`pii-4`) at 1,000 or more. PROV size grows faster than linearly
   with steps (996 steps: 68 MB; 1,557 steps: 991 MB), so the runs over 4 GiB are expected among the few dozen longest;
   the step-4 import's register will name them (`worker.limit.rss`, `worker.limit.output`, or `pv.prov_structure.not_json`).

## Decision

D-55 (user decisions 2026-10-12): `prov` 4 GiB, every cap bounded by 16 GiB, the default worker count from the largest
cap. A recorded per-run override up to the ceiling needs a CLI flag and a field in the corpus producer block (routed).
