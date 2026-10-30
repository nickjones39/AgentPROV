## Phase 12b `expand` bundle (2026-10-12; D-56, C3, F-08, D-90 if approved; user decision: bundle on `phase-12b`)

**What moves.** Changes to `EXPAND_MODULES` files (`ingest/names.py`, `errors.py`, `ingest/archives.py`,
`ingest/streams.py`, `raw/members.py`) change `raw.members.engine_code_sha256`, so the `expand` stage's `fn_digest`
(in `derivation.json` and on every `raw/members.jsonl` row) moves. No AER, SEM or PROV byte changes, and no golden or
gate-D digest. A paused import cannot resume across the change (its identity check refuses), so the bundle merges only
when no import is paused, as for every `src/` change.

**Contents (implemented on `phase-12b` as one merge unit):**
1. D-56 (= D-91): `:` inside a member component is a label character; drive-form components are traversal in every
   position; one info finding `ingest.name.colon` per container.
2. D-58 (C3, D-47 item 3, HL.R7): streaming `expand`; member bytes and rows identical (tests compare them), only memory
   changes (505 → 134 MiB on a 380 MB archive).
3. D-59 (F-08, D-52): a selection-pattern segment holds at most two `*`; no shipped selection changes.
4. D-57 (= D-90, user-approved 2026-10-12): nested `tar.gz` inside a zip, read by a bounded framing parser. No stored
   corpus holds a nested `tar.gz`, and a gzip that is not a tar keeps its current code, so no existing row changes.

**Prediction per corpus** (read-only scan of every stored `raw/members.jsonl`, 2026-10-12): only the four
`ast-survey-agentharm*` corpora hold archive members (1,691 rows each); none was rejected `ingest.name.invalid` and none
has `:` in a label. At regeneration their rows keep every member digest, label and disposition; only `fn_digest`
changes. Every other corpus has no `members.jsonl` rows. Figshare 32657856 (3,866 `:` members) is not imported.

