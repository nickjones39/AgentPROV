# Worker count by evidence: memory admission for the T1 pools (design D-554, with D-415's calibration)

Status: **design.**
- **Approval:** user-approved in direction on 2026-10-14 (prov-perf's D-554, routed through the orchestrator).
- **Review:** this note goes to the orchestrator first. The deferrals session reviews it, because it owns `io/` and
  `host.py`.
- **Build:** after the review. The push needs the user's yes in the pipeline-perf window.
- **Data:** prov-perf's memory profile (`docs/reports/prov-perf/memory-profile.md`, branch `prov-perf`) and its
  confirmation run (89 documents), handed over 2026-10-15.

## 1. Problem

`resolve_worker_count(0)` is `min(CPUs, floor(0.75 × RAM / max RSS cap))`, and the largest cap is 4 GiB (`prov`, and the
validate pool's own cap). So on the 32 GB M2 the default is **6 workers**, sized as if every job could reach its cap at
once.

Measured (prov-perf, 89 documents, a fresh process each, 2 ms RSS sampling):
- **Model:** peak RSS of a `prov`/`validate` job ≈ **base + 3.6 MiB + 80.2 MiB × PROV MiB** (R² 0.997), where base is
  46–47 MiB.
- **Accuracy:** measured/predicted is 0.93–1.09 above 0.5 MiB, so **×1.25** covers every document seen. DTap's large
  literals are +7–8%.
- **Stored corpora:** at most 3.98 MiB of PROV, so at most about 374 MiB, far below 4 GiB.
- **Long-run sources:** the phase-10o `cam-j4` trial (18.2 MiB of PROV) reaches 1.43–1.49 GB; DTap reaches 0.97 GB.
- **What it depends on:** PROV bytes, not AER bytes. The AER→PROV fit across corpora is poor (R² 0.69).
- **Cache hits:** with D-550's tier-4 cache warm, a `validate` job builds no RDF, and peaks at about base + 8 MiB per PROV
  MiB.

## 2. What must not change

1. **Outputs:** every AER, SEM, PROV, validation, register, index and manifest byte, whatever the worker count. G.4.8
   already guarantees order independence; §5 proves it again.
2. **No job is ever stopped for pool pressure.**
   - A stopped job becomes a degenerate AER or a `validate.worker` row, which changes outputs.
   - Admission may only **delay** a job. The per-job hard caps of G.4.3 (D-55: 2 GiB default, 4 GiB `prov`/`validate`;
     CPU, wall) stay the only limits that stop a job, exactly as today.
   - A job's wall clock starts when it starts, not when it was queued.
3. **The G.4.2 launch, rlimits, environment, audit hook and T0/T1 split** are unchanged.

## 3. Design

### 3.1 Slots become CPUs; memory gates admission

- `resolve_worker_count(0)` returns `min(CPUs, floor(0.75 × RAM / pessimistic_charge))`, so it is CPU-bound for any
  realistic charge.
- One **admission controller per parent process** is shared by every pool of that process. An import has a map pool and
  a prov pool, so up to 2W processes; one budget covers both.
- **Budget:** `B = 0.75 × RAM − reserve(parent)`. The parent's own RSS is sampled at admission, because the orchestrator
  saw phase 10p's import parent reach about 3.9 GiB.
- **Admission:** a slot takes its next job only when `in_use + charge(job) ≤ B`. Otherwise it waits on a condition
  variable. Jobs are still taken in queue order (FIFO), so a large job is never starved.
- **`in_use`:** the sum over running jobs of `max(charge(job), sampled RSS of its worker)`. The watchdog already samples
  every worker each interval, so a job that grows past its prediction is counted at its real size from then on.

### 3.2 The charge of a job

| Job | Charge |
|---|---|
| `prov` / `validate`, PROV size known | `1.25 × (47 + 3.6 + 80.2 × PROV MiB)` MiB, at most the job's hard cap |
| `validate` with a staged D-550 cache hint | `1.25 × (47 + 8 × PROV MiB)` MiB. prov-perf measured warm growth of 7.0–8.6 MiB per PROV MiB on 0.96–3.98 MiB documents, against 90–134 cold |
| `prov` (derive/recompute) with a staged D-550 hint | `1.25 × (47 + 16 × PROV MiB)` MiB. The hint skips only the round trip; derive (about 7 per MiB) and the tier-4 pre-checks still run (prov-perf) |
| `prov` with no known PROV size | the job's hard cap (4 GiB): today's behaviour |
| `map`, `expand` and the rest | the job's hard cap (2 GiB), or an input-size model **only** if D-415 measures one with a margin; otherwise the cap |

Where a known PROV size comes from:
- **`validate --corpus`, `derive`, `recompute`:** the stored PROV file's size (the reader stats it; the index records
  its digest).
- **Re-import** (the round): `import --size-hints DIR` reads PROV sizes by execution id from the previous version of the
  corpus (the round's renamed `*.pre-regen` directory), read-only. A hint is only ever a charge, never an input, so a
  wrong or missing hint changes timing, never bytes.
- **A new source** has no hint, so the job is charged its cap.

### 3.3 If a prediction is wrong

- A job above its charge but below its cap is counted at its sampled RSS from the next watchdog tick, so admissions
  stop until memory frees.
- In the worst case, every running job overshoots by more than the ×1.25 margin at once and the host swaps. That is a
  performance event, never an output change: no job is stopped by the controller.
- The per-job cap still stops a runaway job, as today.
- Each run records the controller's numbers (budget, charges, peak `in_use`, waits) in the progress stream, never in a
  corpus.

### 3.4 What the worker count becomes

| Machine | Before | After |
|---|---|---|
| M2 Max, 32 GB, 12 CPUs (8 performance + 4 efficiency) | 6 | up to 12 slots, gated by memory |
| M5 Ultra, 256 GB | CPU-bound | unchanged; CPU-bound |

The real gain on the M2 depends on the 4 efficiency cores and on the two pools of an import competing. D-415 measures
it rather than assuming the 1.6×.

## 4. Files

| File | Change | Digest |
|---|---|---|
| `io/workers.py` | the controller, the charges, slot admission | none |
| `host.py` | default worker count | none |
| `corpus/derive.py`, `corpus/validation.py` | pass PROV sizes as job charges | none |
| `adapters/runner/importer.py` | pass the `--size-hints` charges | moves the aer engine digest: a regen-batch row through `reserve_id`, landing before part C |
| `cli/import_.py` | `--size-hints DIR` | none |

The importer change is the only digest move. It could be avoided by passing hints from the CLI layer; that option is
looked at during the build.

## 5. Proofs and calibration (with D-415, in the orchestrator's quiet window; every run through `suite_queue --class import`)

1. **Byte identity across worker counts:**
   - a ROPE 1,500 subset and Mandate imported at W = 3, 6, 8, 12, all identical;
   - `validate --corpus` reports at `--jobs 3, 8, 12` identical to in-process;
   - `derive --dry-run` zero differences at 3 and 12.
2. **Calibration** (D-415): throughput and parent/tree RSS against W, for:
   - a ROPE import at W = 3, 6, 8, 10, 12 (with and without admission);
   - a full ROPE import at `-j8` and a recompute dry-run at `-j3` (regen-plan's rows);
   - `validate --corpus` at 6 against 12.

   The default worker count and an M5 Ultra preset come from these numbers.
3. **Controller tests** (unit, synthetic):
   - admission never exceeds `B` with exact charges;
   - FIFO order;
   - an overshooting job blocks further admission;
   - a job whose charge exceeds `B` alone still runs when nothing else is running (otherwise it would never run);
   - the controller never stops a job.
4. **Round estimate:** recomputed from the calibration and sent to regen-plan.

## 6. Deferrals review (2026-10-15): OK with changes, all adopted

This section supersedes §2–§5 where they differ.

1. **Time caps (blocker 1).**
   - **The risk:** the wall cap (600 s) and the CPU cap (soft `RLIMIT_CPU`, 300 s per job) depend on load and on core
     type. Twelve slots put jobs on the 4 efficiency cores and add memory-bandwidth contention, so a job that finishes
     today could reach `worker.limit.wall` or `worker.limit.cpu`. That is an output change.
   - **Calibration:** D-415 records, per job kind, the largest job wall time and CPU time as a ratio of its cap, at each
     W with both import pools busy.
   - **Refusal threshold:** the default W is the largest W whose worst ratio is **≤ 0.33** (a 3× margin), and the
     report states the margin.
   - **§3.3 restated:** swapping is a performance event only while every job stays under its time caps, and the
     threshold is what keeps them there.
2. **Idle reused workers (blocker 2).**
   - `in_use` is the sum over **every live worker** (running or idle, both pools) of `max(charge of its current job or
     0, sampled memory)`.
   - In addition, a worker whose sampled peak during a job exceeded **512 MiB** is retired after that job, before its
     slot waits for admission. Its memory goes back to the host, rather than sitting idle and blocking admissions.
3. **Metric.**
   - Admission samples **`phys_footprint`** (`proc_pid_rusage`, `RUSAGE_INFO_V2` or later). Resident size falls under
     compression exactly when the host is short.
   - The per-job **cap keeps today's metric**, so it fires exactly as it does now.
   - prov-perf is asked to confirm, or refit, the model with `phys_footprint`.
4. **One ticket order across both pools.**
   - Every waiting slot of every pool of the parent takes a ticket in one global FIFO, with head-of-line blocking:
     when the head does not fit, no later ticket is admitted, even one that would fit.
   - **Oversize rule:** a head whose charge exceeds B alone is admitted when **no job is running in either pool**.
     Idle workers are retired first, so their baselines cannot block it.
   - Both behaviours are tested.
5. **Deadlock.**
   - The admission wait stays in `take()`, before a request is written, never inside `_execute`.
   - A job's charge is released when its result is collected or the job is killed. It is not released when the parent
     later closes the `JobResult`: held results are parent memory, covered by the parent reserve and D-414's
     `SPOOL_MEMORY_PER_POOL`.
   - `_abort` wakes every waiter (`notify_all`), so `run()` cannot hang after another slot fails. Tested.
6. **Watchdog.**
   - The parent's memory is re-sampled at every admission decision.
   - The progress stream records the largest observed overshoot (sampled memory / charge) per job kind, so model drift
     shows in the round's logs.
7. **Size hints.**
   - Hints are keyed by **`source_key`** (artefact sha and key locator), which stays stable across mapping and profile
     versions, unlike `ex` after D-31.
   - The previous corpus is read only through `CorpusReader`'s index (sizes and digests), read-only.
   - Hints stay out of `ProvOptions` and everything recorded. A test shows that a corpus imported with and without
     hints is byte-identical.
8. **No aer digest move.**
   - Charges come from the CLI or derive layer as a `charge(job) -> bytes` policy handed to the pools, keyed by
     what the job already carries. For an import's `prov` job, that is the sealed AER it reads, whose header gives the
     `source_key`. The parent reads its own sealed AER, nothing untrusted.
   - `importer.py` is left untouched if a pool-level policy hook allows it; otherwise it is a `reserve_id` regen row,
     landing before part C.
9. **Minor points.**
   - The default without a charge policy stays `min(CPUs, floor(0.75 × RAM / 4 GiB))` = 6, unchanged. Slots become
     CPUs only where a policy is installed (`validate --corpus`, `derive`/`recompute`, an import with `--size-hints`).
   - The calibration includes worker counts where map + prov slots ≤ CPUs (no oversubscription).
   - **Two parents.** B is the smaller of 0.75 × RAM minus the parent's memory and the machine budget that
     `suite_queue` granted the job (D-427, through an environment value it sets for `--class import` jobs). The round
     runs one import parent at a time.

**Deferrals (2026-10-15): §6 accepted.** A note on item 8: the importer already holds each unit's `source_key` in memory
when it stages a `prov` job (`unit.primary`: artefact sha256 and key locator, as used for resume). Taking it from there
saves re-reading the sealed AER header in T0, but touches `importer.py`, which moves the aer digest. The build weighs
the two. Either way the key comes from the parent's own sealed or held data, never from a worker's output.

**prov-perf (2026-10-15): the model under `phys_footprint`.** Six documents (0.32–18.18 MiB of PROV, including
`cam-j4` and DTap), each in a fresh process, recording resident size and footprint in one sampler:

| PROV MiB | Resident growth | Footprint growth | Model growth (3.6 + 80.2 × P) |
|---|---|---|---|
| 0.32 | 27 | 27 | 29 |
| 1.21 | 103 | 103 | 101 |
| 3.98 | 330 | 333 | 322 |
| 6.65 | 528 | 529 | 537 |
| 10.44 (DTap) | 934 | 934 | 841 (+11%) |
| 18.18 | 1,498 | 1,499 | 1,461 |

- **Growth:** the same under both metrics, within 3 MiB. The footprint base is about 35 MiB, against 47 MiB resident.
- **Charges:** keep the conservative base of 47 MiB, the 80.2 slope and the ×1.25 margin. The DTap outlier (+11%) is
  inside the margin.
- **Measurement in the controller:**
  - **memory held** (idle and running workers, the parent): the current `phys_footprint` from `proc_pid_rusage`
    (`RUSAGE_INFO_V4`);
  - **overshoot detection** (§6.6): the kernel's `ri_interval_max_phys_footprint` since the last read, so no short spike
    between watchdog samples is missed;
  - **the 512 MiB retire rule** (§6.2): the lifetime maximum, `ri_lifetime_max_phys_footprint`.
- **Caveat:** these ran without memory pressure. Under compression, footprint keeps counting compressed pages while
  resident size drops, which is why footprint is the admission metric.

**Field positions** (prov-perf's correction, checked in a live process): in `rusage_info_v4`, after the 16-byte uuid,
the uint64 fields are `phys_footprint` [7], `ri_lifetime_max_phys_footprint` [28] and `ri_interval_max_phys_footprint`
[33]; [34] is `ri_runnable_time`. The build defines the whole struct as a `ctypes.Structure` with the SDK's field names,
rather than raw indices, and a test checks the three fields against a live process.
