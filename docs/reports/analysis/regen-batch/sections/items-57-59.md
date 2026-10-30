## Items 57–59 (core review B, class 1; user-confirmed 2026-10-14; built on `review-core-b-regen`, in the pre-round integration): row recorded at integration from the owner's records

Source: `docs/reports/review-core-b/findings.md` (CB-4, CB-20, CB-22) and `proposals.md`. Digest predictions follow the
D-451 scopes (`src/agentprov/stage_scopes.py`). They were re-checked at integration by mapping each fix's changed
source files onto `aer_scope(f)` for every family, `prov_scope()` and `validation_scope()`.

- **57 (CB-4, 4bde755e): `corpus/manifest.py` `corpus_counts` `by_stage.expand`.** `ok = len(containers)`, with
  nothing subtracted, because a failed container writes no `members.jsonl` row. `failed` counts distinct
  `(snapshot_id, source_key or path)` pairs among the expand errors.
  - **Prediction:** no stage digest moves; `corpus/` is in no scope. AER, SEM and PROV are unchanged.
  - **Moves:** `corpus.json` bytes (and the content and root digests), only for corpora with an expand register error.
  - `verify` recomputes the counts with the same function, so an older sealed corpus with an expand failure reports a
    counts mismatch at main until it is regenerated.
- **58 (CB-20, e19faf22): `adapters/runner/importer.py` and `corpus/writer.py`.** An archive input is stored only if
  it still hashes to its verified pin: `add_object(expected_sha256=, expected_size=)`, refused with
  `raw.object.mismatch` before the object or its origin is recorded.
  - **Prediction:** the aer stage `engine_code_sha256` moves for every family, and so does `fn_digest`.
    `corpus/writer.py` is outside every scope.
  - Stored AER, SEM and PROV bytes are unchanged for honest inputs.
- **59 (CB-22, b3450b57): `raw/members.py` `expand_containers`.** A nested archive reached again with another
  selection becomes an `expand.conflict` event instead of aborting the import.
  - **Prediction:** the expand stage digest moves for every container corpus. `raw/members.py` is also in every
    family's aer closure, so that digest moves too, and in the `agentdojo` semantics closure (`sem_scope` of
    `adapters/agentdojo/semantics`; no other family's), so the sem stage `engine_code_sha256` and `fn_digest` of every
    corpus with an `agentdojo` semantics profile move as well (pre-round re-check RC-10).
  - `members.jsonl` and register bytes change only for an archive where the conflict occurs. No stored corpus
    declares the `[import] nested` chains that produce it, so no stored row moves.

