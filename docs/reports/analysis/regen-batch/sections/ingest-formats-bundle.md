## `ingest-formats` bundle (2026-10-12; D-240–D-246 user-approved 2026-10-13; branch `ingest-formats`; design `docs/reports/ingest-formats/design.md`)

**What moves.** Like the phase 12b `expand` bundle, plus the limits record. (1) `EXPAND_MODULES` files change
(`errors.py`, `ingest/archives.py`, `ingest/limits.py`, `ingest/streams.py`, `raw/members.py`) and the tuple gains
`ingest/parts.py`, so `raw.members.engine_code_sha256` and the `expand` stage's `fn_digest` move (in `derivation.json`
and on every `raw/members.jsonl` row). (2) New `IngestLimits` fields (`max_tar_stream_bytes`, `max_zstd_frames`,
`max_json_stream_bytes`, `max_json_element_bytes`, `max_json_elements`, `max_split_parts`, `max_split_bytes`) change
`limits_sha256` in the `expand` **and `aer`** stages of `derivation.json`, and the `limits.effective` record of
`corpus.json`, for every corpus at its next import or re-map. **No AER, SEM or PROV byte changes**; no golden or gate-D
digest moves. A paused import cannot resume across the change (its G4 identity check compares `fn_digest` and the `aer`
stage's `limits_sha256`), so the bundle merges only when no import is paused.

**Contents (one merge unit):** streaming `tar.zst` at depth 1 and 2 through the D-57 tar framing reader with a zstd
frame pre-parse (D-240, D-241); declared-array streaming of JSON documents above `max_json_bytes`, element slices
parsed by `strict_json_loads` (D-242; `ingest/jsonstream.py`, not an expand module); zips stored as declared,
digest-pinned byte parts (D-243, D-244); calibrated budgets (D-245), including a fix of the tar block reader shared with
D-57 (memory only: member bytes, rows and digests unchanged; peak 1,733 → 324 MiB for 2 GiB selected).

**Prediction per corpus:** the four `ast-survey-agentharm*` corpora keep every member digest, label and disposition;
only `fn_digest` and `limits_sha256` change. Every other corpus: `limits_sha256` of the `aer` stage and the
`corpus.json` limits record only. No stored corpus holds a `tar.zst`, a split zip or a JSON document read by streaming.

