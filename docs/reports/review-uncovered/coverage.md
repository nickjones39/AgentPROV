# Review coverage map (review-uncovered, 2026-11-01)

This map records which review last covered each part of the product code, at which commit, and how much has changed
since. It sets the scope of the `review-uncovered` pass (findings in [findings.md](findings.md)). HEAD for this pass is
`394ee707` (identical to `release/v0.1.1` on 2026-11-01).

## The reviews on record

| Review | Date | Commit reviewed | Scope | Record |
|---|---|---|---|---|
| Bug pass `bugpass-perf-10` | 2026-10-14 | `0949cb18` | suite/pipeline perf, workflow tools, phase-10 families 10f..10p (credleak, mcphunt, openhands, geminicli, autogen, wirelog, agentops), ingest formats, runner, withholding | `docs/reports/bugpass/` |
| Core review A | 2026-10-14 | `7f8f8cb3` | `aer/`, `sem/`, `views/`, `vocab/`, `schemas/`, `versions.py`, `formats.py`, `errors.py` | `docs/reports/review-core-a/` |
| Core review B | 2026-10-14 | `7f8f8cb3` | `corpus/`, `release/`, `raw/`, `migration/`, `stats/`, `render/` | `docs/reports/review-core-b/` |
| Core review C | 2026-10-14 | `7f8f8cb3` | `cli/` (not `cli/backends.py`), `api.py`, `host.py`, `presets*`, `progress.py`, `envinfo.py` | `docs/reports/review-core-c/` |
| Core review D | 2026-10-14 | `7f8f8cb3` | `adapters/registry/`, `adapters/types.py`, `adapters/runner/` (parts), `adapters/agentdojo/` (not `drift_mapper.py`), `adapters/adprov/`, `adapters/inspect/` (base), `adapters/dtap/`, `adapters/foobench/` | `docs/reports/review-core-d/` |
| GUI review (two waves) | 2026-10-15/16 | `3a7896d4` | `gui/src/agentprov_gui` (G1 viewer, G2 job runner, D-440 macOS chrome) | `docs/reports/review-gui/` |
| Bug pass `bugpass-new-families` | 2026-10-21 | `37be83cd` | 10j agentdojo-family profiles, memo-ozdincer dialect, shared agentdojo redaction, `qwencode`, agentops context pins, AgentDyn history, `import --sample` | `docs/reports/bugpass-new-families/` |
| Pre-round integration review | 2026-10-22 | `cdd26e34` (diff vs main `238b34a8`) | the merged pre-round branches only (importer, derive chain, part C, redaction/withholding, versions/digests) | `docs/reports/pre-round-review/report.md`, `recheck.md` |
| Ultrareview `pipeline` | 2026-10-22 | `39eeed41` | `adapters/runner/`, `corpus/derive.py` | `~/.agentprov/review/pipeline.findings.json`; fixes `d3d98773`, `a37f8cd9` |
| Ultrareview `seal-release` | 2026-10-22 | `39eeed41` | `corpus/{package,manifest,verify,datasheet}.py`, `release/`, `tools/release_scan.py` | `~/.agentprov/review/seal-release.findings.json`; records `bf7df22f` |
| Ultrareview `raw-withhold` | 2026-10-22 | `39eeed41` | `raw/`, `corpus/{rawtree,withhold,withheld,purge}.py` | `~/.agentprov/review/raw-withhold.findings.json` |
| Local review D/E/F | 2026-10-22 | `c4d7b785` | D: `ingest/`, `io/`, `worker.py`, `cli/backends.py`; E: `prov/` (not `compat/`), `validate/`; F: `aer/`, `sem/`, `views/` | `docs/reports/pre-round-review/def-review.md` |
| Rebuild-window review (rounds 1-3) | 2026-10-22 | `a5f47998`..`bcfbd634` (diff vs main `32c89f96`) | the D-656 Anthropic window: `ingest/sse.py`, `messages_wire`, the `capture_mapper` Anthropic dispatch, defence catalogue home, D-664 egress (diff only) | `docs/reports/pre-round-review/rebuild-window-review.md` |

The ultrareview's three areas were chosen on 2026-10-22 (commit `c4d7b785`), replacing the 2026-10-11 plan. The
original `live-capture` area (`capture/src`, `backends/shared/src`) was deferred ("later, not used in the round") and
never ran; `trust-boundary` and `provenance-core` became the local D/E/F review, which left out `artefacts/`. The
2026-10-30 docs review (`docs/reports/release/docs-review-v0.1.0.md`) covered documentation only.

## Path -> last review, and change since (at HEAD `394ee707`)

Lines are `.py`/`.toml`/`.yml` lines now (tests excluded); "changed" is `git diff --numstat <commit>..HEAD`.

| Path | Last review | Commit | Lines now | Changed since | Status for this pass |
|---|---|---|---:|---|---|
| `src/agentprov/aer` | A + F | `c4d7b785` | 5,210 | +58/-8 (4 files) | diff reviewed |
| `src/agentprov/sem`, `views` | A + F | `c4d7b785` | 2,268 | +13/-1 | diff reviewed |
| `src/agentprov/vocab`, `schemas`, `versions.py`, `formats.py`, `errors.py` | A | `7f8f8cb3` | (data) | schemas +10,940 (generated JSON), formats +48 | not re-reviewed (generated schemas; small) |
| `src/agentprov/ingest`, `io`, `worker.py` | D | `c4d7b785` | 7,261 | +343/-41 (14 files) | diff reviewed |
| `src/agentprov/cli/backends.py` | D | `c4d7b785` | 431 | +138/-17 | diff reviewed |
| `src/agentprov/prov` (not `compat/`), `validate` | E | `c4d7b785` | 12,334 | +1,522/-76 (most in archived catalogue TOMLs) | diff reviewed |
| `src/agentprov/raw` | ultra raw-withhold | `39eeed41` | 4,866 | +104/-29 (incl. `origins.py`) | diff reviewed |
| `src/agentprov/corpus/{rawtree,withhold,withheld,purge}.py` | ultra raw-withhold | `39eeed41` | 2,801 | +312/-32 | diff reviewed |
| `src/agentprov/corpus/derive.py`, `adapters/runner` | ultra pipeline | `39eeed41` | 7,264 | +460/-245 | diff reviewed |
| `src/agentprov/corpus/{package,manifest,verify,datasheet}.py` | ultra seal-release | `39eeed41` | 5,218 | +215/-68 | diff reviewed (time-boxed) |
| `src/agentprov/release` | ultra seal-release | `39eeed41` | 2,747 | +1,008/-52 (`index.py` mostly) | diff reviewed |
| `tools/release_scan.py` | ultra seal-release | `39eeed41` | 1,113 | +397/-73 | diff reviewed |
| `src/agentprov/corpus` (other files, e.g. `personas.py` new) | B | `7f8f8cb3` | — | +4,493/-526 across 32 files (overlaps the rows above) | diff reviewed |
| `src/agentprov/migration`, `stats`, `render` | B | `7f8f8cb3` | 8,387 | +414/-90 (24 commits) | **not re-reviewed** (out of depth for this pass) |
| `src/agentprov/cli` (not `backends.py`) | C | `7f8f8cb3` | 19,818 | +10,081/-493 (43 files) | diff reviewed: `run.py`, `cli/live/*`, `assist.py`, `models.py`, `prices.py`, `jobs.py`, `batch.py`, `devrun.py`, `estimate.py`, `keys.py` |
| `src/agentprov/api.py`, `host.py`, `presets*`, `progress.py`, `envinfo.py` | C | `7f8f8cb3` | 2,633 | +358/-58 | diff reviewed |
| `src/agentprov/adapters/registry`, `types.py` | D | `7f8f8cb3` | 3,015 | +724/-200 | diff reviewed |
| `src/agentprov/adapters/agentdojo` | D + NF bug pass (+ rebuild window, Anthropic parts) | `37be83cd` | 36,945 | +7,692/-276 (55 files; much TOML) | Python diff reviewed |
| `src/agentprov/adapters/adprov` | D | `7f8f8cb3` | 2,997 | +95/-20 (incl. D-1011 fuzz fixes) | diff reviewed |
| `src/agentprov/adapters/inspect` | D | `7f8f8cb3` | 7,239 | +3,228/-137 | diff reviewed |
| `src/agentprov/adapters/dtap` | D | `7f8f8cb3` | 22,013 | +12,744/-39 (mostly semantics TOML) | Python diff reviewed |
| `src/agentprov/adapters/foobench` | D | `7f8f8cb3` | 1,912 | +14/-3 | not re-reviewed (trivial diff) |
| `src/agentprov/adapters/{agentops,qwencode}` | NF bug pass | `37be83cd` | 8,192 | +2,545/-174 | diff reviewed |
| `src/agentprov/adapters/{credleak,mcphunt,openhands,geminicli,autogen,wirelog}` | bug pass | `0949cb18` | 21,099 | +4,615/-127 (wirelog unchanged) | diff reviewed |
| `src/agentprov/artefacts` | **none** (dropped from trust-boundary) | — | 1,327 | all | full review |
| `src/agentprov/jobs`, `keys`, `devrun`, `estimate`, `settings.py`, `stage_scopes.py`, `stage_definitions.py`, `drain.py`, `testing` | **none** (new after 2026-10-14) | — | 6,980 | all | full review |
| `capture/src` | **none** (`live-capture` never ran) | — | 2,609 | all | full review |
| `backends/shared/src` | **none** (`live-capture` never ran; D-656 diff only) | — | 8,221 | all | full review |
| `backends/{agentdojo,autodojo,agentdyn,inspect}` | **none** | — | 2,314 | all | full review |
| `gui/src/agentprov_gui` | GUI review | `3a7896d4` | 15,383 | +7,983/-1,485 (59 files, 127 commits) | diff reviewed (help/safe/assistant pane in full) |
| `zenodo/src` | **none** | — | 1,270 | all | full review |
| `.github/workflows` | **none** | — | 504 | all | full review |
| `tools/` | **none** as a whole (only `release_scan.py`) | — | 39,978 | all | reviewed: `public_export.py`, `building_commit_snapshots.py`, `zenodo_draft.py`, `release_triage.py`, `scan_origins.py`, `scan_personas.py`, CI helpers; the rest (precheck, gen_*, estimate priors) not reviewed |

## Areas still without a review after this pass

- `src/agentprov/migration`, `stats`, `render` changes since `7f8f8cb3` (24 commits, about 500 lines).
- Most of `tools/` (maintenance scripts: `precheck/`, `gen_*`, `estimate/`, `suite_queue.py`).
- `src/agentprov/schemas` (generated JSON Schemas; checked by tests, not reviewed by hand).
- The archived catalogue and profile TOMLs (frozen copies; compared against the live ones only where a finding needed it).
