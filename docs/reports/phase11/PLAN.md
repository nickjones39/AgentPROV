# Phase 11 plan: corpus sealing, derive/recompute, verify, package/release, stats, the remaining CLI

Branch `phase-11` (own worktree), rebased on `main` at each merge point. Started 2026-10-11. This file is the working
contract for the phase-11 implementation units. It is replaced by the as-built notes (AGENTS.md, DECISIONS.md, spec)
when the phase closes.

## Binding rules (user, 2026-10-11)

1. **Ownership** (AGENTS.md §0 "Parallel sessions"). Phase 11 owns `src/agentprov/corpus/`, `release/`, `stats/`,
   `render/` and the new N.2 CLI commands. It must **not** edit `src/agentprov/adapters/` (except new append-only files
   in the shared `adapters/registry/`), `src/agentprov/ingest/`, `src/agentprov/raw/`, `src/agentprov/worker.py`,
   `tests/security/`, `tests/property/` or fuzz tests. Shared files (AGENTS.md, DECISIONS.md, `docs/architecture/`,
   `cli/main.py`, `adapters/registry/`): small, append-only edits.
2. **Decision numbers** D-30–D-49 only.
3. **No corpus is rewritten or regenerated.** Tests use fixtures and *copies* of corpora (in the scratch area, never
   `~/.agentprov/corpora/*` in place). The regeneration batch (`docs/reports/analysis/regen-batch.md`) is not applied.
4. **`derive` and `recompute` never write in place.** Output is always a new corpus version (`--out NEW`). They must
   cover regen-batch.md: re-derive SEM/PROV/validation from stored AERs, and re-map from the stored raw objects (no
   network) when an adapter change alters the AER.
5. **`render` is on demand only** (selected single executions), never a render of every graph.
6. Any change that would alter the AER/SEM/PROV bytes of an existing corpus goes into regen-batch.md for approval.
7. Do not push. The phase is offered for merge when the full pytest suite, `ruff check .`, `mypy` and
   `tools/check_unicode.py` pass.
8. aer/0.1 and capture/0.1 are frozen; `prov/compat/adprov_v2_3/` is frozen; golden digests must not change.

## Inventory at start (c4ed6c5 / bf1b463)

- `render/` + `cli/render.py`: **done** (K.5.12 items 1, 2, 4–6); it has an `--all` mode that rule 5 removes.
- `corpus/` working writer, index (phase-3 row subset), register: exist. `corpus.json` is a working subset written
  by `adapters/runner/importer.py:_manifest`; missing fields listed in H.2. Real working corpora have a `local` snapshot
  origin for every `--input` import, and agentharm has `candidates: 6, executions: 1056` (breaks H.2.3).
- Absent: sealing, full manifest + schema, index facets, `checksums.sha256` / root digest, `DATASHEET.md`, compat
  outputs (`apv:RegressionOracle`), `verify`, `derive`, `recompute`, `package`, `release/`, `stats/`, `inspect`,
  `purge`, `api.py`, `formats.py`, `testing/fs_guard.py`, the claims library (`adapters/registry/claims.py`).
- Registered CLI commands: info, validate, import, fetch, run, backends, migrate, render (8 of 15). Missing: derive,
  recompute, verify, inspect, package, stats, purge. `validate --corpus` handles tier `aer` only.

## Decisions reserved for this phase (write the text into `docs/reports/phase11/decisions/D-NN.md`; the orchestrator
consolidates them into DECISIONS.md at the end)

| Id | Topic | Unit |
|---|---|---|
| D-30 | derive/recompute live in `corpus/` (L5) and reuse the T1 job kind `prov` by name; re-map uses the public `adapters.runner.importer.import_source` with a `StoredRawTree` (called from the CLI layer); stage definitions and `index_completeness` re-implemented in `corpus/` and pinned equal by tests; **always a new output corpus, never in place** | U2 |
| D-31 | version-bump discipline for the regen batch — **user: strict (2026-10-11)**: every catalogue/profile whose bytes the batch changes gets a new integer version, old versions shipped under `rules/archive/`, spec id stays `agentprov-prov/0.1`; phase 11 implements the H.8.4 classification | — |
| D-32 | raw objects in `recompute --out` are copied by default; `--link-raw` opt-in (user-approved 2026-10-11) | U2 |
| D-33 | snapshot reconciliation (candidates = selected execution-bearing files/members) and the sealed snapshot origin built from the recorded pin, never `local`; `subtree` string / `subtrees` array | U3 |
| D-34 | v0.1 index facets = H.3.3 core facets; generic `cell`, `logical_key`, `ev`, `oracles`; adapter `x.*` facets and `--pipeline` deferred | U1 |
| D-35 | the 2024-06 and head working corpora both carry `corpus_id` `agentdojo-upstream`; per D-27 c2 they are two corpora (ids such as `agentdojo-upstream-2024-06`, `agentdojo-upstream-head`; the corpus id comes from the corpus spec at sealing, checked to appear in no AER/SEM/PROV bytes) that deliberately share content-addressed execution ids (14,182 shared); the datasheet says so (datasheet item 3); **two corpora confirmed by the user 2026-10-11** | U3 |
| D-36 | the claims library is a new file `adapters/registry/claims.py` (shared registry, append-only; user-approved 2026-10-11) | U3 |
| D-37 | compat outputs via `derive --prov-spec adprov-v2.3-compat` (lazy loader in `prov/specs.py`); flags in `oracle_specs`, row `oracles`, CLI notice (R-55); **user (2026-10-11): released adprov-v1 carries the compat graphs; no other corpus does** | U2 |
| D-38 | deposit verification input and archive mode (no extraction; per-member label/size/crc32/sha256) | U4 |
| D-39 | `verify --root-digest sha256:…` | U4 |
| D-40 | `ValidationSummary` fields (`mode`, per-check `version`/`tier`, `libraries`) | U3 |
| D-41 | `sources[].lineage` = the profile's `[lineage]` table verbatim; `duplicates` shape | U3 |
| D-42 | licence classes (AD-20(b), D-25): class = (derived spdx, sorted restrictions); GPL-3.0, AGPL-3.0 distinct; `-nc` corpora under `nc_partition`; mixed classes refused | U5 |
| D-43 | live corpora: `recompute --stages aer` exits 5; SEM/PROV/validation re-derive works | U2 |
| D-44 | corpus specs in git: `.gitignore` M.3.1 negations; `corpora/<id>/{corpus-spec.toml,CARD.md,CHANGES.toml}`; **user (2026-10-11): derived licence `inherit` for every corpus; `ast-survey-agentharm` is its own restricted-use class** | U3 |
| D-45 | `render` on demand only: `--all` removed; `--select` requires `--limit` | U7 |
| D-46 | `purge` lives in `corpus/purge.py`, not `raw/purge.py` (ownership rule) | U7 |
| D-47 | SEC-07 >256 MiB calibration of the G.4.3 expand budgets and expand streaming (HL.R7) moved to phase 12 (owns `raw/`, `worker.py`, `tests/security/`) — user-approved 2026-10-11 | — |

## derive / recompute design (rules 3, 4, 6)

- `recompute --corpus SRC (--out NEW | --dry-run) [--stages expand,aer,sem,prov,validation,views] [--jobs N]`.
  `derive --corpus SRC --out NEW [--stages …] [--prov-spec adprov-v2.3-compat] [--trig DIR]` adds missing layers
  (views, compat, TriG) to a new version. Neither writes in SRC. SRC (sealed, working, or `.partial`) is opened
  read-only and checked unchanged with `testing/fs_guard.py`. NEW is created as `NEW.partial`, disjoint from SRC,
  outside git, not pre-existing; it is resumable after interruption. The manifest gets
  `derived_from: {corpus_id, corpus_version|null, root_digest|null, state, manifest_sha256}`.
- **Inputs first:** re-hash every raw object SRC lists (`raw.digest.mismatch` refuses); check rules digests against
  the package at the recorded versions (`rules.mismatch` / `rules.unavailable`); catalogues and profiles only from the
  package (AD-14). Copy objects (D-32), `origins.jsonl`, and register rows that cannot be re-derived (select/ingest
  `not_imported` rows).
- **Re-map (`expand,aer`):** `StoredRawTree` yields one candidate per non-member origin row (sorted by label bytes;
  label = git `origin.path` or the family listing path), reads from the SRC store with a digest check, takes the
  snapshot origin from SRC's manifest; passed to `adapters.runner.importer.import_source(...)` with the values recorded
  in SRC's manifest and `derivation.json`. No network. Acceptance: re-mapping each fixture family gives byte-identical
  AER.
- **Re-derive (`sem,prov,validation`):** stream index rows; stage each AER into a scratch store; submit
  `Job(kind="prov", …)` in batches over `WorkerPool(jobs)`, consumed in index order; copy AER unchanged and re-verify
  its seal.
- **views / compat:** `transcript-v1` and `adprov-v2.3-compat` (notice printed when compat output is written).
- **Index rebuild** (full H.3.1 rows; B2 completeness), **`derivation.json`** (recomputed stage definitions, carried
  stages kept), **working `corpus.json`** (counts recomputed per D-33).
- **Comparison:** per execution, AER bytes + seal digest, SEM digest per profile, PROV file sha256 per spec,
  validation-row JCS digest; bytes/JCS only. Classes: `identical`, `changed_explained` (a declared version differs),
  `unexplained_change` (exit 1), `failed`, `unverified`. Code-digest-only change with identical output passes.
  Index-row deltas reported separately (`index_refreshed`). `--show-diff N`: first differing JCS line (escaped) + PROV
  semantic diff (`prov/diff.py`, ported from the baseline's `diff_documents`).
- **Regen-batch paths** (for the record; the batch is not applied in phase 11): B1, C1, C3, F-10, E2-b1 → re-derive
  from AER; B3, B6+C6, F-01, E2-b3 and any catalogue bump declared in AER headers → re-map from raw; B2, E2-b2 → index
  rebuild. Realistic duration ≈ the p10 import time (≈ 6.5 h; tier-4 validation dominates), not minutes.
- Determinism: `--jobs 1` vs 4 vs in-process, two hash seeds, reversed `scandir` → identical bytes.

## Units

U1 → {U2, U3, U6, U7} → {U4 (after U2, U3), U5 (after U3)} → U9. Opus: U1–U5 core (U6 tables). Sonnet: U6 CLI/output,
U7, U9 docs/tests. Each unit runs only its targeted tests; the orchestrator runs the full suite at merge points (one
full-suite run at a time on the M2 Max).

- **U1 Corpus model foundation (Opus).** `corpus/facets.py`, `corpus/integrity.py` (part 1: `set_digest`,
  `content_digest`, `root_digest`, `write_checksums`, `verify_checksums`, closed world), `corpus/reader.py`
  (`CorpusReader`: sealed / working / `.partial` per N.1.5), `formats.py`, `testing/fs_guard.py`; full H.3.1 index rows
  with tolerant decoding of working rows (`corpus/index.py`), all H.1.2 paths (`corpus/layout.py`). Tests under
  `tests/unit/corpus/`. No AER/SEM/PROV change; render tests stay green.
- **U2 derive/recompute engine (Opus).** `corpus/derive.py`, `corpus/rawtree.py`, `prov/serialise/trig.py`,
  `prov/diff.py`, lazy compat loader in `prov/specs.py`, `cli/derive.py` (`derive`, `recompute`). Tests: RPR-1..5, 8, 9;
  HL-T5/T6/T14/T15; stage definitions equal to the importer's; re-map identical AER per family; fs_guard; compat
  flags + notice (Q.30); `--jobs` invariance; Q.14.
- **U3 Sealing (Opus).** `corpus/manifest.py` + `validate_manifest` + `schemas/corpus-0.1.schema.json`,
  `corpus/spec.py`, `corpus/datasheet.py`, `corpus/package.py` (`seal()`), `corpus/rules/corpus.rules.toml`,
  `adapters/registry/claims.py` (new file), `cli/package.py` (seal mode), `validate --card`, `.gitignore` negations,
  `rules/`, `schemas/`, `LICENSES/` writers. Tests: HL-T1, T3, T4, T7, T8; two seals identical; preconditions exit 4.
  **DATASHEET.md must carry every statement of `docs/reports/analysis/datasheet-items.md`** (C4; D-27 c1, c2, c5; the artefact disclosures N2, N4–N8 with the proposed wording of `phase10-corpus-analysis.md` §8 and `phase10-examination-2.md` §8.3/§10), each emitted only for the corpora its row names, from committed data (per-corpus `corpora/<id>/` card or a datasheet-statements table), with a test per row.
- **U4 verify + validate corpus mode (Opus).** `verify` levels checksums / chain / rederive, archive mode, `--root-digest`,
  `--against-pins`, `--sample/--seed`; `validate --corpus` tiers sem/prov/linkage. Tamper tests in
  `tests/corpus/test_tamper.py` (not `tests/security/`). Q.19.
- **U5 Release / deposit builder (Opus).** `release/{__init__,builder,metadata}.py`, `tools/release_scan.py`
  (injectable scanner; gitleaks 8.30.1 installed via Homebrew 2026-10-11 with the user's approval; record its version), `package --deposit`; deterministic zips; licence-class grouping and
  refusals (D-42). Tests: HL-T9, Q.20, mixed-class matrix.
- **U6 stats + `api.py`.** `stats/{__init__,tables,output}.py`, `stats/field_groups.toml`, `stats --artefacts`,
  `cli/stats.py`, `api.py`. K.5.11; Q.32.
- **U7 Remaining CLI (Sonnet).** `cli/inspect.py`, `corpus/purge.py` + `cli/purge.py`, `import --dry-run --artefacts`,
  render `--all` removal (D-45). K.15 parts.
- **U9 Integration and docs (Sonnet + orchestrator).** `test_cli_contract.py` (15 commands; exit codes), DECISIONS
  D-30…, AGENTS.md, spec as-built notes, regen-batch path table; rehearsal on copies of `ast-survey-agentharm-p10` and
  `mandate-agentdojo-eval-p10` (recompute 0 diffs, seal twice, deposit twice, mixed-class refusal).

## Additions (user, 2026-10-11, from `docs/reports/phase13/figure-inventory.md` §8.1 and D.16.17)

- **U6 stats:** `--tables {counts,statements,unknowns,field_groups}`; `field_groups` with `stats/field_groups.toml` (the
  paper's headline information-loss metric); `statements` also at per-execution grain (O.3.5); `counts` incl.
  `n_executions` and `n_outcome_only`; `stats --artefacts`. Rate exclusions come only from data the adapter's
  catalogue/profile declares (issue codes, origins), never from hard-coded source-specific codes (D.16.17 item 4);
  role `agent` grouped with `assistant` through a documented data mapping (D.16.17 item 3).
- **Validation:** corpus `validation/` summary carries the tier results and `linkage_resolved_pct` (O C1 `c1-linkage`);
  U3 defines the field (D-40), U4 produces it in `validate --corpus`.
- **U10 gate D full (Sonnet):** `agentprov migrate gate-d [--scope golden|full]` and the `full_corpus` test
  `test_validation_all` (K.7.4); reads stored AERs read-only, re-derives in scratch, J.3.5 acceptance, invariants and
  timings. Unblocks the CLI route of gate E. Decision text, if any, as D-49.

- **Derive performance (from the phase-10b session, user-relayed):** a content-addressed reuse cache in `derive` (key:
  AER digest + digests of every declared profile/semantics table/catalogue + SEM/PROV engine and spec versions; reused
  vs recomputed recorded in derivation.json; `--no-reuse` to force; byte-identical with and without reuse, across
  `--jobs`); per-stage profile of a ~200-execution derive on a scratch copy and a `--jobs` 10/11/12 comparison before
  any optimisation; no threads (worker processes are a security boundary). Part of U2, recorded under D-30.

## At merge (to do in U9)

- Add to `docs/reports/analysis/regen-batch.md` (user, 2026-10-11) the U6 smoke findings
  (`docs/reports/phase11/stats-smoke.md`): fields absent from AER without an `unk` declaration — AgentHarm checker
  version/code (1,056) and transmitted sampling parameters (200); Mandate transmitted sampling parameters (396).
  Adapter-owned fixes; they change AER bytes.
- `stats.tables.datasheet_field_groups(manifest) -> str` so the sealed DATASHEET carries the field-group table (U3 hook).
- Tighten U1 row classes to the schema (HL-T1 findings: `""` in `model.*` / register `ids`, non-string outcome
  `name`, `paths.aer=None`).
- `seal()` runs `verify --level chain` (N.2.11 step 3) once U4 lands; references/withheld in `raw_set`.
- Spec as-built notes from U3 (M.5.3 `cli.package` git subprocess; H.1.6 `licence.decided_by`/`files`; H.2 `layout`,
  `datasheet.statements`, `ProfileRef.paths`, `validation.tiers`/`linkage`/`linkage_resolved_pct`,
  `counts.members.rejected`); U10 gate-D notes in J; figure-inventory §8.1 rows closed.
- Gate D full has no converted-tree input (no v1 AERs of the converted tree are stored); runs need `--accept-gap converted`.
- From U5: U4 plugs `verify --level chain` into `cli/deposit.py` (`verify=`) and adds archive-mode verify of a deposit
  (D-38; HL-T9 last clause); spec notes: default `--max-archive-bytes` 2**31−1 (no ZIP64), two new format ids,
  `--corpus-version` is seal-mode only; the gitleaks allowlist for the AgentPROV-generated key fields (**done, user-approved**; D-42 note); the AgentHarm
  credential-shaped strings are fake (**user, 2026-10-11**): triage `synthetic-benchmark` at release.
- **`pv.roundtrip` speed-up (decided 2026-10-12, at the user's request):** not in phase 11. A separate branch after the
  phase-11 merge and before the regeneration batch, coordinated with the regen-batch session (which edits `validate/`
  for item 10). Adopted only if every validation result row is byte-identical (golden set; copies of Mandate and
  AgentHarm); the only permitted difference is the validation stage code digest.
