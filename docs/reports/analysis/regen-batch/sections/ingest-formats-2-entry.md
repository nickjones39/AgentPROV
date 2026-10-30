## `ingest-formats-2` entry (2026-10-13; D-247–D-249 user-approved 2026-10-13; branch `ingest-formats-2`; design `docs/reports/ingest-formats/followup-design.md`)

**What moves.** (1) `ingest/archives.py` and `ingest/limits.py` (`EXPAND_MODULES`): the `expand` `fn_digest` moves again;
the new field `max_pax_header_bytes` changes `limits_sha256` in the `expand` and `aer` stages and the `corpus.json`
limits record of every corpus at its next import. (2) `adapters/runner/importer.py` (split archive inputs): the `aer`
stage's `engine_code_sha256` (`adapters/runner` + `aer`) moves for every corpus at its next import. `raw/origins.py`,
`raw/fetch.py`, `corpus/manifest.py`, `corpus/rawtree.py` and `cli/import_.py` are in no stage digest. **No AER, SEM or
PROV byte changes**: no stored corpus has a split input, a top-level tar or a pax header. Merges only when no import is
paused; the deferrals session reviews the runner diff first.

**Contents:** a gzip tar at depth 1 and tests that top-level `tar.zst`/`tar.gz` archive inputs meet the zip's limits
(D-247; RI-3, D-192 part 1); pax `x` headers through a closed allowlist (D-248; D-192 part 2); the `split` origin kind,
split download pins and split archive inputs on the D-200 path, replayed by `recompute`/`rederive`, sealed with `parts`
(D-249; RI-1, RI-2, RI-5).

