## `bugpass BF-19/BF-15` entry (2026-10-14; D-461; branch `bf19-bf15`)

**What moves.**
- `ingest/limits.py` (`max_split_parts` 64 → 32) is an `EXPAND_MODULES` file, and the `IngestLimits` record changes,
  so the `expand` `engine_code_sha256`/`fn_digest` and `limits_sha256` (a notice only, D-31 addendum) move for every
  archive or container corpus at its next import or re-expansion. Member digests, labels and dispositions do not move.
- `corpus/verify.py` (the `withheld.container` check) and `io/workers.py` (`worker.input.nofile`) are in no stage
  digest.

**No AER, SEM or PROV byte changes.** No stored corpus has a split archive with more than 32 parts. The largest
observed has 8.


