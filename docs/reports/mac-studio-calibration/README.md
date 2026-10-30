# Mac Studio calibration: `m5ultra` version 2

**Date:** 2026-10-28. **Machine:** Mac Studio M5 Ultra (36 CPU cores, 256 GB). **Design:** [`design.md`](design.md)
(D-820..D-829). **Raw sweep reports:** [`tune-jobs/`](tune-jobs/), one folder per sweep, each with the
`agentprov-tune-jobs/0.1` JSON and its Markdown table.

This report is the `calibration` that `presets.toml` names for `m5ultra` v2 (D-823).

## 1. What was measured

`agentprov run agentdojo --m5ultra --tune-jobs 1,2,4,6,8,12` against oMLX on `127.0.0.1:8000`.

- **The sample (each arm):** 24 cells, the default sample (D-820). That is banking, slack, travel and workspace × user
  tasks 0–2, each benign and with `important_instructions` (injection task 0, slack 1).
- **Run setup:** 1 repeat, at most 2 attempts per cell, a warm-up before the first arm, `--containment sandbox-exec`,
  LLM element `gateway_compat` (D-829). Request timeout 900 s, start stagger 1 s per worker.
- **Software:** commit `8d187c61`, clean tree.
- **Backend environment:** `agentdojo-db3901f1`, the same build in every arm.

| Model | Size | Facts from |
|---|---|---|
| `Qwen3.8-Flash-Next-UD-Q4_K_XL` | 103.7 GiB weights (4 split GGUF files), 6 B active, MoE 512 experts / 10 per token | weights and architecture from the model folder; active parameters from the Local Models setting (D-828) |
| `Qwen3.5-4B-MLX-4bit` | 2.8 GiB weights | model folder |

### Measurement conditions

The approved design took an exclusive `--cpu 34` queue ticket for every timed run. On 2026-10-28 the user chose
instead, in this session's window, to run the sweeps alongside wave 2's imports.

- **Shared tickets:** `--cpu 12`, plus the model's memory reserved (`--mem-gib 8` and `--mem-gib 120`), since oMLX
  holds the weights outside the queue's accounting.
- **Load recorded:** a sampler logged the 1-minute load average and the queue's reservations every 60 s.
- **The rationale:** token generation runs on the GPU, which no import uses, so the CPU load mainly adds harness
  latency.
- **The re-measure rule:** an ambiguous knee is re-measured at 1–2 points in a quiet window.

The full Qwen3.8 sweep is **measured under load**. Jobs 4 and 6 were then re-measured on an exclusive ticket.

## 2. Results

### Qwen3.8-Flash-Next Q4, full sweep (shared ticket)

| jobs | traces/h | wall s | s/cell | cell p50 / p90 s | call p50 / p90 ms | gen tok/s | load (1 min) |
|---|---|---|---|---|---|---|---|
| 1 | 429 | 201.5 | 8.4 | 4.4 / 15.4 | 1271 / 3443 | 107 | 8–11 |
| 2 | 724 | 119.3 | 9.9 | 6.5 / 14.4 | 1689 / 5480 | 167 | 7–9 |
| **4** | **968** | 89.2 | 14.9 | 7.1 / 27.1 | 2443 / 8585 | 220 | 7–9 |
| 6 | 872 | 99.1 | 24.8 | 13.0 / 33.0 | 3459 / 10014 | 221 | 7–25 |
| 8 | 780 | 110.8 | 36.9 | 22.3 / 43.6 | 5621 / 12250 | 185 | 8–34 |
| 12 | 869 | 99.4 | 49.7 | 24.7 / 38.0 | 5851 / 13476 | 206 | 22–39 |

- **Outcomes:** every arm had 24 of 24 cells conclusive, with no timeouts, call errors or canary stops.
- **Queue load:** 24 of 34 CPUs and 184 of 192 GiB were reserved throughout.
- **Above the server limit:** at 12 jobs the arm exceeds oMLX's 8 concurrent requests, so oMLX queued the extra
  requests.
- **Recommendation:** 4 jobs, the smallest N within 90 % of the peak, with no timeouts and no failed cell.
- **Why re-measure:** the load rose from jobs 6 onward, so the drop after 4 could have been the load. Jobs 4 and 6 were
  re-measured on a quiet machine.

How the columns are computed:

- **s/cell** is wall × jobs ÷ cells.
- **cell p50/p90** come from each cell's run span in the AER (`mono_end_ns − mono_start_ns`).
- **gen tok/s** is completion tokens ÷ wall.

### Qwen3.8-Flash-Next Q4, quiet re-measure (exclusive `--cpu 34`)

| jobs | traces/h | wall s | s/cell | cell p50 / p90 s | call p50 / p90 ms | gen tok/s | load (1 min) |
|---|---|---|---|---|---|---|---|
| **4** | **1009** | 85.6 | 14.3 | 8.7 / 20.2 | 1909 / 6997 | 225 | 2.3–4.5 |
| 6 | 834 | 103.6 | 25.9 | 12.8 / 32.1 | 4016 / 10361 | 221 | 2.3–2.9 |

The re-measure confirms the knee:

- **Generation is saturated by 4 jobs:** about 222 tok/s at both 4 and 6.
- **More jobs only lengthen each cell:** the call latency p50 doubles from 4 to 6 jobs.
- **The drop is not load:** the quiet throughput at 6 jobs is below the loaded run's 872 traces/h, so the server, not
  the CPU load, sets the knee.
- **Throughput at 4 jobs:** 1009 traces/h quiet, against 968 under load, about 4 % lower under load.

### Qwen3.5-4B-MLX-4bit (stopped)

- **What happened:** the campaign canary (D.10.9) checks the first 10 cells. In that check 1 of 41 calls was flagged
  A4 ("text-encoded tool call suspected"), so the arm at 1 job stopped. The sweep stops with it, so no other arm ran.
- **What the arm measured:** 453 traces/h over 10 cells, 81 tok/s generation.
- **The flag doesn't help:** `--allow-text-tool-calls` covers the preflight probe, not the canary.
- **Decision:** the user chose to drop this model from the calibration. A model the canary rejects shouldn't calibrate
  a preset for live runs.

## 3. `m5ultra` version 2

| Field | v1 | v2 | Why |
|---|---|---|---|
| `calibrated` / `calibration` | absent | `true` / this file | D-823 |
| `compute_caps` ≤ 15 B active | 8 | **4, measured** | Qwen3.8-Flash-Next (6 B active): knee at 4, confirmed quiet |
| `compute_caps` 15–40 B | 6 | 4, provisional | No model measured. Capped at the measured 4, because a larger model should not get more concurrent jobs than a smaller one on the same server |
| `compute_caps` > 40 B (catch-all) | 4 | 4, provisional | No model measured. Unchanged, and equal to the cap |
| `cell_seconds` ≤ 15 B | none | p50 14.3 s, p90 27.4 s, jobs 4 | See below |
| `request_timeout_s` | 900 | 900 | The longest call in any arm was 29.0 s (jobs 4, under load), far below |
| `start_stagger_per_worker_s` | 1 | 1 | No timeouts or errors at any N |
| `server_max_concurrency_default` | 8 | 8 | oMLX ran with its default |
| memory terms (`gpu_budget_fraction` 0.75, reserves) | | unchanged | J_memory for Qwen3.8 is 20, so memory never bound. v2's plan for it: J_compute 4, J_memory 20, J_server 8, jobs 4 |
| `evidence` | 4 prior rows | + 3 rows | One per sweep report, each with the report's sha256 |

**How the `cell_seconds` row is derived.** `agentprov estimate` gives a run's time as ⌈cells ÷ jobs⌉ × one cell's
seconds. So the row holds the quiet arm at 4 jobs.

- **p50 = 14.3 s:** the arm's wall × jobs ÷ cells, 85.642 × 4 ÷ 24. This reproduces the arm's measured wall time,
  overheads included.
- **p90 = 27.4 s:** the p50 scaled by the cells' p90 ÷ mean run span, 14.274 × 20.207 ÷ 10.509. This matches the
  priors' reading of p90, every cell at its p90.
- **No catch-all row.** Only one class was measured, so the row is bounded at 15 B. A larger model, or one of unknown
  size, keeps the priors' time.
- **Code change:** a bounded last row was not allowed before. D-826's addendum allows it (`presets.py`).

**What the bump changes.**

- **Stored data:** no corpus has recorded a preset, so nothing stored changes.
- **Live runs:** preset live runs (`--m5ultra` without `--tune-jobs`) are now admitted (D-823) and run at 4 jobs.
- **Estimates:** a local-model estimate on this machine takes the measured time for models up to 15 B active.
- **Digests:** the change is class 0. `presets.py`, `presets.toml`, `cli/` and `estimate/` are in no stage digest
  scope (`stage_scopes`, checked 2026-10-28).

## 4. Findings and follow-ups

1. **Live AER has no `t.dur_s`.** Its run scopes record `mono_start_ns`/`mono_end_ns`, but the estimate's usage
   reader (`estimate/usage.py`) reads only `dur_s`. So a live corpus given to `estimate --stats-corpus` contributes
   no time. The shipped priors come from imported corpora and are unaffected. This is a follow-up and is not fixed
   here.
2. **The canary's A4 check can't be overridden.** A model that sometimes writes a tool call as text stops a campaign
   after its first 10 cells, whatever the flags. That is by design (D.10.9), but it means small local models may not
   finish a sweep at all.
3. **Not yet measured:**
   - the 15–40 B and > 40 B classes;
   - oMLX with `--max-concurrent-requests` other than 8;
   - a sample beyond user tasks 0–2.

   A dense model above 15 B would replace the provisional rows.
4. **Still open from the hand-off:** two class-1 doc changes, held until after the round-1 seal:
   - D-829's caveat text;
   - the `constants_for` docstring in `host.py` gaining the Studio's allocation rate (§5). `host.py` is in the AER
     stage's import closure, so even a docstring change moves a stage digest.

## 5. Memory-watchdog allocation rate (D-825)

The allocation-rate probe (`job_calibrate`, run by `get_calibration` once per process) ran 20 times on 2026-10-28.

- **How:** each run was a fresh process, all inside one exclusive `--cpu 34` queue ticket. Load average 4.7–5.0. No
  model and no network.
- **Results:** all 20 were `ok`. Each wrote 256 MiB in 14.9–15.9 ms.

| Machine | min | median | max |
|---|---|---|---|
| Mac Studio M5 Ultra (this run) | 15.77 GiB/s | 16.47 GiB/s | 16.79 GiB/s |
| MacBook Pro M2 Max (earlier figure) | 11.9 GiB/s | | 12.3 GiB/s |

- **The default stays:** the minimum is far above the 4 GiB/s `DEFAULT_ALLOC_RATE`, so the fallback stays
  conservative and unchanged (D-825).
- **Where the figure is used:** every worker pool measures its own rate. So on the Studio, the RSS kill margin
  without a hard cap is `clamp(16.5 GiB/s × 20 ms × 2, 32 MiB, cap/2)`, about 0.66 GiB (675 MiB) before the cap/2 clamp.
- **Where it is recorded:** `G_security.md` now gives both machines' figures. The `host.py` docstring waits for the
  class-1 window (§4).
- **Raw results:** `~/.agentprov/calibration/watchdog-probes-2026-10-28.jsonl`, outside the repo.
