# Expand-job budgets and streaming `expand` (phase 12b; D-47 items 1 and 3; D-58, D-60)

Date: 2026-10-12. Branch `phase-12b`. Host: M2 Max, 32 GB, macOS arm64, CPython 3.14.8, shared with other sessions
(load average 31–37 during the runs). Script and raw results: `~/.agentprov/migration-work/phase12b/expand-calib/`
(`expand_calibration.py`, `run.log`, `results.jsonl`) and `expand-calib-main/` (the same synthetic case on unmodified
`origin/main`). The survey archive was read from the fetch cache; no download.

## Method

One real `expand` job per archive, in a fresh T1 worker (`workers=1, jobs_per_worker=1`), with exactly the request
`expand_containers` builds (default `IngestLimits`, include `**`, release mode). Worker CPU time is `RUSAGE_CHILDREN`
after the worker exits; the peak is the parent watchdog's sample; the budget is what G.4.3 gives this job
(`with_expand_scaling(max_total_bytes)`: 300 + 240 s CPU, 600 + 480 s wall).

## Results

| Case | Container | Selected | Members | Worker CPU | Job wall | Peak memory | Budget CPU / wall |
|---|---|---|---|---|---|---|---|
| Synthetic seeded zip (16 × 16 MiB stored random, 16 × 16 MiB deflated text; seed 20261012) | 380 MB | 512 MiB | 32 | 2.1 s | 2.7 s | **134 MiB** | 540 s / 1,080 s |
| Survey `artifact.zip` (Zenodo 22135957; 44,287 entries, almost all deflate) | 244 MB | 652 MiB | 44,281 | 4.4 s | 9.4 s | 227 MiB | 540 s / 1,080 s |
| Synthetic, **before** streaming (`origin/main` @ `2c419e9`) | 380 MB | 512 MiB | 32 | 2.2 s | 2.0 s | **505 MiB** | 540 s / 1,080 s |

## Reading

1. **CPU and wall:** about 4–7 s of worker CPU per GiB of selected members (the provisional increment is 60 s/GiB) and
   at most 15 s of wall time per GiB under load. At the 4 GiB `max_total_bytes` cap that projects to about 30 s CPU and
   60 s wall, against a budget of 540 s and 1,080 s: **at least 10× headroom**. The provisional values are kept as the
   calibrated ones (D-60): lowering them would buy nothing but a risk on a slower host, and a stuck job is still
   bounded. As built, every expand job gets the increments for the full `max_total_bytes` (the parent cannot know an
   archive's declared total before the worker opens it), which this calibration covers.
2. **Streaming (D-58):** before, the worker read the whole container into memory (`read_input`), so its peak exceeded
   the container size (505 MiB for a 380 MB archive). Now the container is opened by digest, hashed in 1 MiB chunks and
   read through the handle (`JobContext.open_input`); the peak is set by one selected member (≤ `max_member_bytes`,
   read whole before its header is sent so that a defect never yields partial bytes) plus the interpreter: 134 MiB.
   CPU is unchanged (2.1 s against 2.2 s).
3. **Tests:** `tests/security/test_expand_budget.py` (slow) builds a 288 MiB-selected seeded archive at test time and
   asserts the job succeeds with ≥ 10× budget headroom and a peak below the container size; a second case stores
   272 MiB member by member through `expand_containers`.
