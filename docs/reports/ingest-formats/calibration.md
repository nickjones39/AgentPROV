# Calibration of the D-240–D-243 readers (D-245; method of D-60)

Date: 2026-10-13. Branch `ingest-formats`. Host: M2 Max, 32 GB, macOS arm64, CPython 3.14.8, libzstd 1.5.7, shared with
other sessions (load average 19–39 during the runs). Script and raw results: `~/.agentprov/migration-work/ingest/calib/`
(`ingest_calibration.py`, `json_file_case.py`, `zst_frames.py`, `run1.log`, `run2.log`, `results.jsonl`,
`results_raw.json`). Synthetic inputs are seeded (20261013) and generated in that scratch directory. No download.

## Method

Archive cases run as one real `expand` job in a fresh T1 worker (`workers=1, jobs_per_worker=1`), with the request
`expand_containers` builds (`raw.members._job`; default `IngestLimits`; release mode). Worker CPU is `RUSAGE_CHILDREN`
after the worker exits; the peak is the parent watchdog's sample; the budget is G.4.3's
(`with_expand_scaling(max_total_bytes)`: 300 + 240 s CPU, 600 + 480 s wall). The JSON cases and the real file run in a
fresh `-I` subprocess that reports its own CPU and `ru_maxrss`.

**Real file (user-approved read, 2026-10-13):** the staged `RESULTS_raw.tar.zst` (Zenodo 20404563, 207,950,011 B,
sha256 `f7186010…`) was read in memory with nothing selected: no member stored or printed; only frame parameters,
counts and timings were recorded.

## Results

| Case | Input | Worker / process CPU | Wall | Peak memory | Budget CPU / wall |
|---|---|---|---|---|---|
| `tar.zst`, synthetic, nothing selected (two passes) | 2.0 GiB stream (64 × 32 MiB, half random, half text), 1.30 GB compressed, window 2^27 | 4.3–5.0 s | 3.9–5.7 s | 191–193 MiB | 540 s / 1,080 s |
| `tar.zst`, synthetic, all selected, **before** the block-reader fix | same; 2 GiB selected | 4.9 s | 8.7 s | **1,733 MiB** | 540 s / 1,080 s |
| `tar.zst`, synthetic, all selected, after the fix | same | 3.9 s | 5.3 s | **324 MiB** | 540 s / 1,080 s |
| Split zip, synthetic, all selected | 8 parts of 256 MiB, 2.09 GB logical, 88 members (stored random and deflated text), 2.95 GB selected | 6.8 s | 11.5 s | 223 MiB | 540 s / 1,080 s |
| Streamed JSON from a file handle (`messages`/`events` shape) | 314,748,138 B, 671,088 elements | 32.9 s (both passes) | 41.8 s | **32 MiB** | (map job) 300 s / 600 s |
| Streamed JSON from bytes in memory | 115 MB, 208,201 elements | 12.5 s (both passes) | — | — | — |
| `RESULTS_raw.tar.zst` (real), nothing selected | 1,464,483,840 B stream, one frame, window 2^23, checksum, no dictionary; 63,384 files, 12,193 directories, 1,642 GNU long names; largest file 32.7 MB | 3.7 s | 3.8 s | 77 MiB | 540 s / 1,080 s |
| gzip decoder alone (D-57 path) | 355 MiB, mixed | 0.55 s/GiB | — | — | — |

## Reading

1. **CPU and wall (D-60 rule: ≥ 10× headroom at the cap).** A zstd tar costs about 2–2.5 s of worker CPU per GiB of
   stream for both passes together. At `max_tar_stream_bytes` = 16 GiB that projects to about 40 s, against 540 s:
   **13× headroom**. The gzip path decodes faster than zstd on mixed data; with a conservative 4 s/GiB per pass for
   text-heavy gzip, 16 GiB projects to about 130 s (4×), but a nested `tar.gz` is a zip member of at most
   `max_member_bytes` (256 MiB) compressed, so its stream is far below the cap in practice. A split zip costs about the
   same per GiB as an ordinary zip (D-60: 4–7 s/GiB), plus hashing the parts at open. **The expand-job budgets stay as
   they are**; no tar-stream term is added to `with_expand_scaling`.
2. **Memory: a defect found and fixed.** With every member selected, the tar reader's peak grew by one member size per
   member (1,733 MiB for 2 GiB selected; a 2 GiB cap would kill a larger job). Python's live memory stayed flat
   (tracemalloc: 68 MiB); the growth was the abandoned regions of a `bytearray` grown by reallocation, which macOS keeps
   resident. The block reader now collects whole chunks and joins them once per read, as the zip path does: 324 MiB,
   flat over the members (`test_tar_zst.py::test_reading_many_large_members_keeps_memory_flat`, which fails on the old
   code). This also applies to D-57's nested `tar.gz`, which had not been calibrated with large selected members.
3. **Streamed JSON** holds one element and the envelope: 32 MiB peak for a 315 MB document read from a handle. CPU is
   about 0.1 s per MB for both passes (110.9 MB, MCPHunt's largest: about 12 s), against the 300 s map-job budget
   (25×). Whole-document `strict_json_loads` is about 4× faster per pass but would hold about 24× the bytes.
4. **Limit values confirmed:** `max_tar_stream_bytes` 16 GiB (11.7× the real 1.36 GiB); `zstd_window_log_max` 27 (the
   real file uses 23); `max_zstd_frames` 1,024 (real: 1); `max_members` 100,000 is enough for the real file (75,577
   entries counted, of which 63,384 files are gated); `max_json_stream_bytes` 1 GiB; `max_split_parts` 64 and
   `max_split_bytes` 8 GiB.
5. **Calibration note (not a defect of the readers):** a `WorkerPool` given a relative `store_root` finds no inputs,
   because workers run in their own working directory (`worker.input.missing`); every caller in `src/` passes the
   store's absolute `objects_dir`.
