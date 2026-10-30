## Item 156 (ultra seal-release #10; requested by the orchestrator 2026-10-22, ultrareview pre-round fixes, "fix every finding"; commit 657cd64a on `integration-fix-ultra-b`)

**What changes.** The `DATASHEET.md` snapshot table's "Pinned origin" cell renders the pin itself for every origin
kind, through `corpus/datasheet.py` `_origin_text` (the per-unit table's renderer, extended with the corpus branch):

| Origin kind | Before | After |
|---|---|---|
| `git` | ``repo @ `commit` [`subtree`]`` | unchanged, byte for byte |
| `corpus` | ``corpus version @ `producer_commit` `` | unchanged, byte for byte |
| `capture` | `capture` | unchanged |
| `zenodo` | `zenodo` | ``Zenodo `DOI` file`` |
| `hf` | `hf` | ``dataset @ `revision` [path]`` (a single file or a split directory) |
| `url` | `url` | the URL |

Every value still goes through the F-12C-03 escaping (`_md`, `_code`).

**What moves (class 0).**
- `corpus/datasheet.py` is in no stage digest (`stage_scopes.py` names no `corpus/` file) and in no `EXPAND_MODULES`
  file, so no `engine_code_sha256` moves and no AER, SEM, PROV, register, origin or manifest byte changes.
- **Stored bytes.** `DATASHEET.md` is written at sealing. For a corpus with a `zenodo`, `hf` or `url` snapshot origin
  (`sources[].snapshots[].origin.kind` in `corpus.json`), the next seal writes a different `DATASHEET.md`, and so a
  different `checksums.sha256` and **root digest**; its `content_digest` is unchanged (the manifest does not move).
  A deposit copies the datasheet (`DATASHEET-<corpus_id>.md`), so its bytes change too. Corpora whose snapshots are
  all `git`, `corpus` or `capture` seal byte-identical.
- A context row (D-221 per-unit table) with a `corpus`-kind origin, which `agentprov-corpus/0.2` admits, now shows the
  corpus text instead of `corpus`. No importer is known to write one.


