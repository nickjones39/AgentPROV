## Item 155 (phase 10i pre-round fixes: PR-4, PR-5, PR-8, PR-11 #4, re-check RC-5, RC-2, and RC-13, RC-14, RC-16, RC-17; requested by the orchestrator 2026-10-22; commits 2c02bb2a (merged at 58213f5d), 14f15acc (merged at 8994c0ee) and `integration-fix-ultra-10i`)

Records: DECISIONS D-530 addendum (2026-10-22). Reports: `docs/reports/pre-round-review/report.md`, `recheck.md`.

| Fix | Files | Class | Effect on outputs |
|---|---|---|---|
| PR-4: the context archive is checked against its pin before it is stored | `adapters/runner/importer.py` | 1 | none when the archive matches its pin; a swapped one is refused before storing |
| PR-5: a re-map leaves out per-unit inputs absent on purpose; no NF-25 check on re-maps | `corpus/rawtree.py`, `corpus/derive.py`, one `importer.py` hunk | 0 (+1) | only corpora with a purged or withheld context or pinned object: their re-map runs (it used to exit 70), and the dependent executions are unverified |
| PR-8: a pinned object's sample keys are `label\x00pinned…`; a pointer never competes | `importer.py` | 1 | `--sample` runs with pinned objects only: the right executions and register rows (MCPHunt `--sample 1` sealed every trace) |
| PR-11 #4: url context pin `retrieved_at` from the cache record | `cli/import_.py` | 0 | a url context pin without its own `retrieved_at` imports instead of being refused |
| RC-5: a pointer passes the sample exactly with its object | `importer.py` | 1 | sampled DTap imports no longer write the judge row a full import lacks |
| RC-2: labels of the affected executions' inputs are accounted in the corpus-file comparison | `corpus/derive.py` | 0 | `recompute`/`verify --level rederive` after a purged LFS object exit 0 (they exited 1) |
| RC-14, RC-16: only labels used exclusively by those executions, as JCS strings | `corpus/derive.py` | 0 | a change to an input a verified execution shares is reported again; a non-ASCII label is accounted |
| RC-13: inputs used only by absent-dependent executions are left out of the re-map | `corpus/derive.py` | 0 | a purged DTap trajectory's judge file is no longer mapped as a new judge-only execution |
| RC-13: corpus files compared as multisets | `corpus/derive.py` | 0 | a duplicated row is reported (the order stays uncompared) |
| RC-13: a purged context archive's role recorded as skipped | `corpus/rawtree.py` | 0 | `recompute --out` writes `context_skipped: [role]` (D-221) instead of dropping the role silently |
| RC-13 (c): derive's present-layer check ignored `--skip-prov-conformance` | — | — | fixed under D-623 #6 (item 159), not here |

**What moves.**
- **The `aer` stage `engine_code_sha256`** is `code_sha256(aer_scope(family))` since the D-451 addendum. The seeds and
  closure are shared, plus a family closure, so `derivation.json` records one value per family. **RC-17:** an earlier
  version of this row quoted `code_sha256(['adapters/runner', 'aer'])`, the seeds only, which no corpus records.
  - The values below are first 8 and last 6 hex digits, read at each commit with that commit's `stage_scopes.py`.
  - Each 10i merge moves every family once. Between 8994c0ee and the integration head `c4d7b785` nothing else moved it,
    and `integration-fix-ultra-10i` (all `corpus/`) moves none.

  | Family | 58213f5d^1 | 58213f5d (PR-4/5/8, #4) | 8994c0ee^1 | 8994c0ee (RC-5) = c4d7b785 |
  |---|---|---|---|---|
  | no family closure | `520f825d…ea7baf` | `e9b19b5e…de4f81` | `b43b2dec…4a0eaf` | `9830cafd…ad8526` |
  | adprov | `2cd6846c…77d48f` | `fa3b1426…6a2966` | `d4aeedcf…2ced62` | `a5ccb145…bb7535` |
  | agentdojo | `aff99b83…6e9aaf` | `ea6ee3e6…507e28` | `611a4ccb…ea6d89` | `25e4f6a0…018199` |
  | agentops, dtap | `b903c576…253387` | `a7dc3580…6f2bc6` | `2d4bf06e…0cc661` | `c53cfed7…6dce06` |
  | autogen, openhands | `eaf92902…60cd20` | `6ea7ec72…4b4863` | `707a017f…159449` | `8f36e483…d2c33b` |
  | credleak, foobench, geminicli, qwencode, wirelog | `d2fab93c…c90407` | `0bebfae8…7b1720` | `c31c8169…3170ac` | `898b1b6b…9aed2e` |
  | inspect | `b26f1a0a…01e2aa` | `72a36e6d…7f6592` | `1ba23e7a…5c38a9` | `f3f8048e…61899c` |
  | mcphunt | `23c70a4d…5b5166` | `9d04584f…50d0fd` | `19c69b80…db922c` | `17a4934f…0c1bcc` |

  Any later commit inside a family's `aer_scope` moves that family's value again.
- **No full import changes.** No AER, SEM, PROV, register, origin or manifest byte of a full import changes. The changes
  are confined to:
  - refused inputs (PR-4, #4);
  - `--sample` runs with pinned objects (PR-8, RC-5);
  - re-maps of corpora whose context, pinned object or primary is absent on purpose (PR-5, RC-2, RC-13);
  - the comparison itself (RC-13 multisets, RC-14/RC-16 mask).
- **No `expand` code digest moves.** No `EXPAND_MODULES` file is touched. `cli/` and `corpus/` are in no stage digest.

