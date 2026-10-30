# D-323 calibration: streamed MCPHunt documents in T1 workers (2026-10-14)

This calibration is the enable gate for RB-2, and it measures the worker CPU and wall time and the parent RSS asked
for by the deferrals session's review (conditions 2, 4 and 5).

## Setup

- **Data:** phase 10m's staged MCPHunt documents (`~/.agentprov/staging/10m/hf_mcphunt/`), read in place with the
  user's yes. Nothing was copied into the repository. The reports below are numbers only.
- **Code:** a scratch export of branch `d323-stream`, with phase 10m's `adapters/mcphunt/` from `phase-10m-readers`
  laid over it. For the calibration only, the profile's limit was moved to `[import] limits`, the reader marked
  `multi_execution`, and the registry given its reader and mapper.
- **Jobs:** each job is the real streaming `per_item` map job (`_job_map_stream`). It runs in a release-mode
  `WorkerPool` with one worker and the default `WorkerLimits`: map RSS cap 2 GiB, 300 s CPU, 600 s wall, 16 MiB per
  frame, and 256 MiB of JSON per job.
- **Machine:** M2 Max, 32 GB, shared with other sessions' runs, so times are upper-bound-ish.

## Element census (pass over all 26 staged documents)

| | |
|---|---|
| Documents / traces | 26 / 6,786 |
| Traces above the 16 MiB default | 4: 44.8 MiB (`mitigation/minimax_m3_rv1.json`), 24.4 MiB (`mitigation/gpt54_m0.json`), 24.4 MiB (`main/gpt_5_4.json`), 19.5 MiB (`main/deepseek_v4_flash.json`) |
| Largest document | `main/deepseek_v4_flash.json`, 105.7 MiB (the "111 MB" file), 723 traces |

Element sizes are taken from `JsonStreamItem.offset` differences, which include the separator. They match 10m's census
(four traces of 20.5 to 46.9 MB).

## Results

| Run | Element limit | Outcome | Worker peak RSS | Job elapsed |
|---|---|---|---|---|
| 105.7 MiB document | 64 MiB | 723 units, 0 degenerate | 694 MiB | 58.0 s |
| 52.7 MiB document holding the 44.8 MiB trace | 64 MiB | `worker.limit.output` after the trace parsed | 1,481 MiB | 63.4 s |
| Synthetic 64 MiB element (the 44.8 MiB trace with its longest string padded; scratch only, deleted) | 64 MiB | `worker.limit.output` after parse and map | 1,197 MiB | 130.0 s |
| 52.7 MiB document holding the 44.8 MiB trace | 16 MiB (default) | one degenerate AER for the file (`ingest.size.record` in pass 1) | 68 MiB | 6.5 s |

### Parent RSS (condition 2)

While the parent held the 105.7 MiB document's job result (144.1 MiB of JSON frames, decoded) and built all 723
outcomes, the parent process's peak RSS went from 215 to 982 MiB, about 767 MiB for that document. `JobResult` holds
every frame, so the parent's footprint scales with a document's frame volume, not with its element size. One batch
holds at most `batch_size` such results at a time.

## Findings

1. **RB-2 gate: passed at 64 MiB.**
   - A 64 MiB element streams through `open_json_stream` and the MCPHunt mapper within the 2 GiB map RSS cap (1,197
     MiB) and well inside the CPU and wall budgets.
   - The allowlist ceiling for `max_json_element_bytes` is therefore set to the calibrated **64 MiB**
     (`ingest.profile_limits.PROFILE_RAISABLE`), not the 256 MiB of the design. A higher ceiling needs a new calibration
     (review condition 5: "the ceiling drops to what passed").
2. **CPU and wall (condition 4): no change needed.** The slowest job (130 s, the synthetic 64 MiB element) used under
   half of the 300 s CPU budget and about a fifth of the 600 s wall. The 105.7 MiB document took 58 s.
3. **The traces above 16 MiB need RB-3 (carving) before they can import.**
   - With the raised limit they parse.
   - The MCPHunt mapper then copies the large tool result into a record bigger than the 16 MiB frame cap, so the job
     fails `worker.limit.output` and the importer seals the document as one degenerate AER (never half of it). This
     affects 3 documents in the staged set (the 19.5 MiB trace's document mapped fully).
   - Raising the frame cap is not proposed. Carving the result into a `$blob` (D-218; 10m's RB-3) is the fix, and the
     streaming job already gives the mapper a lazy source reader for it.
4. **A defect found by this calibration, fixed before commit.** The first version's broad `except` around the
   streaming loop also covered mapping and frame emission. So a frame-cap failure was relabelled as a reader defect (an
   `abort` with `adapter.defect`). The abort now wraps only the reader's own iteration. A mapping failure stays that
   item's degenerate AER, and an emit failure fails the job with the worker's limit code, as on the byte path.
