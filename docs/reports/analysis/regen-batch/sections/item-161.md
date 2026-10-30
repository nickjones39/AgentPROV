## Item 161: pre-round review area D, the ingest/io trust boundary (D-630; `integration-fix-ultra-io`, 2026-10-22)

Findings #0–#4, #6, #7, #9–#14 of `docs/reports/pre-round-review/def-review.md` (area D). Each fix has a regression test
that fails at `c4d7b785`.

**Stage code digests that move (D-451 closures):**
- **aer and expand:** `ingest/archives.py`, `ingest/limits.py`, `ingest/names.py`, `io/workers.py`.
- **sem:** `ingest/limits.py`, `io/jsonschema_subset.py`.
- **prov and validation:** `ingest/yamlsafe.py`, `ingest/jsonstream.py`, `ingest/limits.py`, `ingest/archives.py`,
  `ingest/names.py`, `ingest/quote.py`; validation also `io/jsonschema_subset.py`.
- **The families' aer and sem closures:** `ingest/yamlsafe.py`, `ingest/jsonstream.py`, `ingest/quote.py`,
  `io/jsonschema_subset.py`, `io/workers.py`.

`io/atomic.py`, `worker.py`, `io/worker_testjobs.py`, `cli/backends.py` and `corpus/layout.py` are in no digest.

**Bytes:** none is predicted for any stored corpus. The behaviour changes only on these inputs:

| # | Input that now behaves differently | Was | Now |
|---|---|---|---|
| #4 | a YAML tool output with a base-60 int scalar over 4,300 characters | about 50 s per MiB, then constructed | `YAMLError`, so the marker falls back (SEM) |
| #9 | archive members whose names collide only under the canonical caseless match (APFS U+0345 cases) | both selected | both rejected `ingest.archive.duplicate` |
| #2 | a classic-EOCD or member-level multi-disk zip | opened | refused `ingest.archive.format` |
| #3 | a zip with a UTF-8-flagged undecodable name | "unreadable zip structure" | a reason naming the defect (the whole archive is still refused: the recorded G.3.5 deviation) |
| #11 | a request between 4 and 64 MiB | a degenerate `worker.protocol` unit | mapped as in process |
| #0 | envelope depth and repeated declared arrays | the same codes | the same codes, refused early |
| #1 | non-finite ratios | accepted | refused (no profile declares one) |
| #10 | datasheet values that begin a line with `~~~` or spaces | written as is | escaped (rendering, class 0) |

- **#11:** no stored register has a `worker.protocol` row (scanned 2026-10-22).
- **No output bytes:** #6, #7, #12, #13 and #14.

