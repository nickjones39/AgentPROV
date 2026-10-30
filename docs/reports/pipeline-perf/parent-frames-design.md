# Parent memory: job results held as spooled frame bytes (design D-414, for review)

Status: **design, not built.** The pipeline-perf session wrote this on 2026-10-14. It goes to the orchestrator, then to
the runner session (D-320/D-321/D-323 own the per-item paths) and the deferrals session (D-218 check-and-hold). It is
built on top of D-323 once that lands, after both reviews and the user's yes.

## 1. Problem

The parent holds every frame of a job result as a parsed Python object until the batch is processed.

- D-323 calibration: the 105.7 MiB MCPHunt document produced 144.1 MiB of JSON frames. Holding them decoded, and
  building the 723 outcomes, took the parent from 215 to 982 MiB.
- regen-plan's ROPE runs: parent peak 829–910 MiB at `--jobs 8`.

The causes, in `io/workers.py` and `adapters/runner/importer.py`:

1. `_collect` parses every `JSON` frame with `strict_loads` and keeps the resulting dict in `JobResult.outputs` until
   the result is closed. Decoded JSON is several times its byte size in CPython.
2. `WorkerPool.run` returns a whole batch of results (256 by default) at once. Each `map` result holds its frames, and
   each `prov` result holds its SEM and PROV members in a `SpooledTemporaryFile` that stays in memory up to 8 MiB.
3. `split_unit_frames(result.json)` builds lists of every unit's frames for a multi-execution file. `_rows_refused`,
   `_aborted` (D-323) and `_seal_items` each walk `result.json`.

## 2. Constraint: nothing is committed before the job's last frame

This is the reason "seal each unit as its frames arrive" is not proposed. A unit's frames cannot be acted on when
they arrive, because a later frame can change what happens to the whole file:

- a `FAIL` (job error, `worker.limit.*`) makes the file one degenerate AER (`_job_failure`);
- D-323: an `abort` frame, emitted **last**, seals the file whole (`_seal_whole`);
- D-321: `register` rows, which in streamed mode can follow the units, are validated together, and any invalid row
  seals the file whole;
- D-218: carved blobs are stored only when the file is not refused or aborted.

Sealing early would need every side effect of `_seal` to be undoable, including register rows, counters, index rows,
the AER write and validation. That is a different design and outside a byte-identical speed-up.

## 3. Design

Keep the frames as **bytes** and parse them when they are consumed, one unit at a time, after `DONE`.

### 3.1 `io/workers.py`

- `_collect` still parses each `JSON` frame with `strict_loads`. It keeps every protocol check: an object, the member
  header, the caps. It then **stores the frame's payload bytes** in a per-result spool (length-prefixed records in a
  `SpooledTemporaryFile` with a small in-memory threshold, e.g. 1 MiB) instead of the parsed dict. Member headers stay
  parsed, because they are small and `MemberOutput` needs them.
- `JobResult` gains `iter_json()`, a generator that re-parses each stored payload with `strict_loads` in frame order.
  `JobResult.json` keeps its meaning (a tuple of every JSON object) for existing callers and small results, and is
  built from `iter_json()` on access.
- `MemberOutput`'s spool threshold drops from 8 MiB to 1 MiB, so a batch's PROV and SEM members go to disk. The bytes
  read back are identical.

### 3.2 `adapters/runner/importer.py` (per-item and container paths)

- **Pass 1 (scan):** one `iter_json()` pass collects only what decides the file's fate: `register` rows,
  `{"unit": …}` heads (their `loc` and `sha256`), and an `abort` or `not_dialect`/`select` frame. Record frames are
  parsed and dropped. `_rows_refused`, `_aborted` and `_rejected_entries` work from this summary.
- **Pass 2 (seal):** when the file is to be imported, a second `iter_json()` pass groups frames by unit as a stream.
  Each unit's frames become one `outcome_from_frames(...)` and one `_seal(...)`, and are then dropped, in the same order
  as today. `split_unit_frames` gets a streaming twin that yields `(head, frames)` one unit at a time.
- Whole-file (non-multi) results keep `outcome_from_frames(result.json)`. Their size is one execution.

### 3.3 What does not change

- Frame order, unit order, the sealing order, register order (canonical locator order, D-321), the carved-blob decision
  and every byte the parent writes.
- The worker side: `JobContext.emit`, the frames and the protocol.
- The security checks on worker output: `strict_loads` runs on every frame on arrival, as now, and again on each read.
  The second parse is of bytes already checked.

## 4. Cost

Re-parsing costs about 66 µs per frame (ROPE: `strict_loads` 1.12 s for 16,934 frames). With two extra passes, a ROPE
execution adds about 7 ms, or 0.4% of its 1.75 s CPU. The parent's peak becomes one unit's frames plus the spool
buffers. For the MCPHunt document that is its largest trace, not the whole document.

## 5. Identity proofs (before merge)

- Differential tests in `tests/adapters/runner/` on the FooBench and credleak fixtures: the same AER, register and index
  bytes with and without spooling, including:
  - an `abort` after units;
  - streamed `register` rows after units;
  - an invalid rejected row;
  - carved blobs with refusal;
  - a `FAIL` part-way.
- Mandate and ROPE scratch re-imports byte-diffed against the D-410 baselines, at `--jobs 8` and `--jobs 3`.
- Golden, gate D, compat and C.16 unchanged. `adapters/runner/` is in the aer stage's `engine_code_sha256`, so that
  digest moves (a regen-batch row, through `reserve_id`). `io/` is in no stage digest.
- Parent RSS measured on a synthetic multi-execution document of the calibrated size (scratch only), against 982 MiB.

## 6. Order

This depends on D-323 (the `abort` frame and `_seal_whole`), so it is built on main after D-323 lands. Because it
moves the aer engine digest, it should land before part C, like D-410.

## 7. Revised design after the reviews (2026-10-14)

Reviews: ingest-formats-3 (no conflict; it lands first), runner (OK in principle, four required changes) and deferrals (OK
with changes, settle item 1 before building). The build sits on main after D-323 (landed, `24d27c27`), ingest-formats-3
and deferrals-carved-hold (`e96ebbfa`, the `_held` fix). This section supersedes §3–§5 where they differ.

### 7.1 One ordered output stream per result (ingest-formats-3 requirement)

`raw.members._parse_outputs` pairs a streamed member (header `"streamed": true`) with the JSON frame right after it
(`{"end"}` or `{"abort"}`). So a result keeps **frame order across members and JSON**:

- `JobResult.iter_outputs()` yields, in frame order, parsed JSON objects and `MemberOutput`s interleaved;
- `iter_json()` is the JSON subsequence of it;
- the names that tests rely on stay as they are: `MemberOutput(header, spool_max, spool_dir)`, `MemberOutput.SPOOL_MAX`
  (lowered from 8 MiB to 1 MiB) and `io.workers.SPOOL_MEMORY_PER_JOB`.

A differential test covers a streamed nested member followed by `end`, and one followed by `abort`, using the shapes in
`tests/unit/raw/test_nested_expand.py`.

### 7.2 Where the bytes go: one batch spool, no descriptor per result (runner requirement 1)

macOS's default soft `RLIMIT_NOFILE` is 256. A file per result (frame spools, member spools and carved-hold's held
members) can exhaust it in a 256-job batch (`EMFILE`). So:

- **JSON payloads** of every result in a pool batch go to **one** append-only unnamed file per `WorkerPool.run` call,
  in `spool_dir`. Each result keeps its own `(offset, length)` list into it. The file closes when the last result of
  the batch closes.
- **Members** keep `MemberOutput`'s spool. When the in-memory budget (§7.3) is exhausted, a member goes to the shared
  batch file too, with an offset range rather than its own file. So there is one descriptor per batch, not per member.
- The differential includes a full 256-result batch with every payload and member rolled to disk, under the default
  `RLIMIT_NOFILE`.

### 7.3 One memory budget for the whole pool (deferrals item 1, runner item 4)

`SPOOL_MEMORY_PER_JOB` (64 MiB) bounds one job. A batch returned whole can still hold 256 × 64 MiB, about 16 GiB. D-414
makes the budget **pool-wide**:

- a counter per `WorkerPool`, `SPOOL_MEMORY_PER_POOL` (proposed 256 MiB), covers the in-memory bytes of every result not
  yet closed: frame payloads and members both;
- bytes are released when a result is closed;
- a member or payload that would exceed the budget goes to the batch file;
- the per-job cap still applies inside it.

The parent's worst case is then: pool budget + one unit's decoded frames during sealing + the `_Unit` AER bytes of two
batches (§1, cause 3). The RSS measurement uses a batch of many multi-member jobs (a synthetic multi-execution
document of the calibrated size, scratch only) as well as one large document.

### 7.4 Two passes, the same decisions at the same points (runner items 2–3, deferrals items 2–4)

- **Pass 1 (summary)**, over `iter_json()` before anything is stored, registered or sealed:
  - every framing check `split_unit_frames` runs today, raising `adapter.job_incomplete` at the same point (a record
    or seal frame before the first unit frame);
  - it collects the `register` rows (in streamed mode they may follow the units), the unit heads, `abort`,
    `not_dialect`, `select`;
  - `_rejected_entries` is computed **once** here.

  One summary feeds `_rows_refused`, `_aborted`, the `not_dialect`/`select` checks (importer, about lines 1483–1493)
  and `_seal_items`' row validation.
- **Order with D-218:** pass 1; then `if refused or aborted: self._held = {}` (with `_seal_whole` for an abort), else
  `result = self._carved(result, sources)`; then pass 2. Everything stays inside the existing `try`/`finally` that
  closes the result.
- **Pass 2 (seal):** units in order, one unit's frames decoded at a time.
  - It skips `register` frames and is never entered when pass 1 saw an abort.
  - It may raise only what today's per-unit loop raises.
  - `--limit` stops inside a multi-execution file exactly as today; later units stay unsealed.
- Carved-hold's held members are released per file, as today. Releasing them per unit would change when `_held` is
  cleared, so it is left for a later change agreed with deferrals.

### 7.5 `JobResult.json`

`JobResult.json` stays for other callers. It is memoised (built once from `iter_json()`) for small results, and the
per-item and container paths **never** call it. A differential guard (a `JobResult` subclass whose `.json` raises,
used for `per_item` and `container` results) proves that.

### 7.6 Extra differential cases (both reviews)

- a record before its first unit frame;
- `not_dialect` and `select` on a `per_item` result;
- a streamed file with rejected rows after its units;
- an `abort` after units;
- `--limit` inside a multi-execution file;
- an invalid rejected row;
- carved blobs with refusal;
- a `FAIL` part-way;
- the 256-result batch rolled to disk;
- the streamed nested-member `end` and `abort` shapes.

### 7.7 Digests and order

- `adapters/runner/` moves the `aer` stage's `engine_code_sha256`: a regen-batch row through `reserve_id`. `io/` moves
  no digest.
- It lands before part C. The identity proofs follow §5: Mandate and ROPE byte-diffs at `--jobs 8` and 3, golden,
  gate D, compat, C.16.

### 7.8 Deferrals' answer on §7 (2026-10-14): OK, both choices confirmed, with these conditions

1. **The batch spool (§7.2).**
   - **Reads:** only with `os.pread(fd, n, offset)`, never through a shared file position. So `iter_chunks`,
     `read_bytes` and the frame readers can interleave (carved-hold reads one held member through `_HeldStore` while
     `_commit_carved` streams another).
   - **Lifetime:** the file is refcounted per result and closed on the last close.
   - **Leaks:** a consumer that raises mid-batch must not leak the rest. The importer's
     `for … in zip(stored, self.map_pool.run(jobs))` closes only the result in hand, so a `weakref.finalize` on the batch
     file plus a pool-level close of unclosed results ends the batch either way. Test: raise in the third result of a
     batch, then assert that no descriptor and no file remain.
   - **The file:** `tempfile.TemporaryFile` (unlinked at creation) in a 0700 `spool_dir` under `AGENTPROV_HOME`'s temp
     area.
   - **Disk bound:** the sum of the batch's spilled outputs, at most 256 × `max_json_job_bytes` plus the members'
     `max_total_bytes`.
   - **Write safety:** every write happens in `_collect` before `run` returns, and `pread` keeps reads safe even if
     `run` streams results one day.
2. **The pool budget (§7.3, 256 MiB).**
   - Whether a payload or member sits in memory or on disk depends on arrival order and is **never observable**. The
     differential runs once with the pool budget at 0 (everything on disk) and once unbounded, and compares the bytes.
   - The worst case adds one carved blob read whole by the validator through `_HeldStore.read_bytes`, up to
     `max_member_bytes`.
3. **§7.4 stands:** carved members are released per file; per-unit release stays out.
4. **§7.5:** `.json` is memoised **always** (not only for small results). The raising-subclass guard also covers the
   live-session container path: `session.py` calls `split_unit_frames(result.json)`, so it moves to the pass-1/pass-2
   form too.
5. **§7.6 and §7.7: OK,** plus the mid-batch descriptor test from item 1.
