# AgentDojo `2024-06` full import and gate R (phase 6, 2026-10-08)

Written by `tools/agentdojo/import_scan.py` (numbers, issue codes and pinned paths only). Source: the 18,241
`runs/**/*.json` blobs of `ethz-spylab/agentdojo@c274885610efaaafec38b6d3eb07152ba7ff3f94` (`runs` tree
`1227480d…`), read from the bare, extraction-free object store with no checkout, each blob checked against its git
SHA-1. Profile `agentdojo-upstream` (version 1), adapter `agentdojo.tracelogger` 0.1.0, catalogues `aer` 1 and
`agentdojo` 1. Gate R compares with the converted tree of the frozen baseline (`579a908`,
`corpus/corpus-og-agentdojo-runs-prov`). Run on an M2 Max with 11 workers: 1,606 s, dominated by `validate_prov`
(derive alone: median 41 ms, p99 188 ms per execution).

| Import (`import-2024-06.json`) | |
|---|---|
| Blobs / bytes | 18,241 / 188,873,874 |
| Sealed / crashes / degenerate | 18,241 / 0 / 0 |
| Variant | `v0.k11` 18,241 |
| `agent_execution` / `outcome_only` | 18,034 / 207 |
| Mixtral logs (not in the baseline copy) | 7 of 7 sealed |
| AER validator, release mode (locators resolved) | 18,241 pass |
| `agentprov-prov/0.1` derive + `validate_prov` (tier 4) | 18,241 pass |
| Accounting | `unverifiable` 18,008, `consistent` 233 |

| Seal issue (files) | |
|---|---|
| `earlier_attempts_unobservable` | 18,034 |
| `accounting_unverifiable` | 18,008 |
| `no_execution_observed` | 207 |
| `unexecuted_tool_call` | 145 (153 calls) |
| `outcome_imposed_by_runner` | 106 |
| `retry_passes_inferred` | 47 |
| `incomplete_run` | 4 |
| any `agentdojo.*` issue code | 0 |

| Gate R (`gate-r-full.json`; J.4.3) | Result |
|---|---|
| R1 `serialise(render_converted(AER)) == converted transcript bytes` | 18,027 / 18,027 |
| R2 compat graph bytes | 18,027 / 18,027 |
| Claim gate (R1 and R2 at full scope, 0 mismatches) | **pass** |
| R4 `EXCLUDED.json` rows equal to the outcome-only AER | 207 / 207 |
| R5 native-only | the 7 Mixtral logs |
| R5 v1-only | none |
| R3 field-level diff | not run in phase 6 (J.4.6) |

`census_2024_06` in the import report holds the quantities of the profile's `2024-06` `observed` counts;
`tests/full_corpus/test_upstream_pinned_import.py` asserts them (D.6.10 item 3).

Reproduce (needs the bare cache and `AGENTPROV_BASELINE_CORPUS`):

```bash
uv run python tools/agentdojo/import_scan.py --out docs/reports/agentdojo --workers 11
uv run pytest -m full_corpus tests/full_corpus/test_upstream_pinned_import.py
```

## Product import through `agentprov import` (phase 6, 2026-10-08)

`import-cli-2024-06.json` records the same snapshot imported through the product path, written by
`tools/import_report.py` from the working corpus and the command's `--summary-json` (numbers, codes and digests only):

```bash
uv run agentprov import agentdojo --fetch --allow-network --release --jobs 10 \
    --corpus ~/.agentprov/corpora/agentdojo-upstream-2024-06 --summary-json <summary>
uv run python tools/import_report.py --corpus ~/.agentprov/corpora/agentdojo-upstream-2024-06.partial \
    --summary <summary> --out docs/reports/agentdojo/import-cli-2024-06.json --compare docs/reports/agentdojo/import-2024-06.json
```

`--fetch` read the pinned commit from the cached bare object store: the commit was present, so no network call was made
(`--allow-network` is required by N.1.11 all the same). AgentPROV source at commit `61b39d3` (the commit that adds the
command; `src/` clean), CPython 3.14.8, M2 Max, 10 T1 workers, **release mode** (AER validator release mode with
locators resolved against the raw store; tier 4 strict, a skipped check counts as a failure).

| `agentprov import agentdojo` | |
|---|---|
| Exit code / wall time | 0 / 1,614.6 s |
| Candidates (`seen`) / mapped / sealed clean / with issues / degenerate / failed | 18,241 / 18,241 / 17,747 / 494 / 0 / 0 |
| Registered / duplicates / excluded / filtered | 0 / 0 / 0 / 0 |
| Origins | `git` (pinned commit, path, blob id) for all 18,241 |
| `agent_execution` / `outcome_only` | 18,034 / 207 |
| AER execution digests equal to the index / AER validator pass (release) | 18,241 / 18,241 |
| `agentprov-prov/0.1` derived / tier-4 pass (strict) | 18,241 / 18,241 |
| PROV re-derived from the stored AER in a fresh process, byte-identical to the stored file | 18,241 / 18,241 |
| Completeness (index) | `verified_complete` 232, `known_incomplete` 51, `unverifiable` 17,958 |
| Register | 36,551 entries, all `map.*` seal issues, disposition `sealed` |

**Equal to the ad-hoc scan** (`comparison` in the report; 13 of 13 keys): sealed, degenerate and crashes, units,
variants, accounting (`consistent` 233, `unverifiable` 18,008), seal issues by code and by file (the table above),
AER-validator passes, derivations, tier-4 passes, PROV statements by rule and bundles.

Determinism: a second full import with `--jobs 6` (1,830.8 s) into another working corpus gave a byte-identical tree:
54,731 of 54,731 files, `corpus.json` and `derivation.json` included (`determinism` in the report,
`tools/import_compare.py --whole`).


## `head` full import (phase 10; recorded 2026-10-09, refreshed on the integrated code 2026-10-11)

`import-cli-head.json` records the import of the 36,679 `runs/` logs of `ethz-spylab/agentdojo@089ed468` (part `head`, profile
`agentdojo-upstream`, corpus `agentdojo-upstream`) through `agentprov import`, written by `tools/import_report.py`;
`census-head.json` is the profile census over the same snapshot (`tools/agentdojo/profile_census.py`). **The first report
(2026-10-09, wave-1 branch code) predated the history fields (D.6.16) and the wave-2 mapper changes; it was regenerated on
2026-10-11 from the integrated import** (`head.summary.json` of the phase-10 run script, step `head`; `main` `afe7038`,
CPython 3.14.8, M2 Max, 10 T1 workers, `--release`, 5,186 s). Numbers, codes and digests only.

```bash
uv run agentprov import agentdojo --snapshot head --input <clone> --verify-against-pin --release --jobs 10 \
    --corpus ~/.agentprov/corpora/agentdojo-upstream-head-p10 --summary-json <summary>
uv run python tools/import_report.py --corpus ~/.agentprov/corpora/agentdojo-upstream-head-p10.partial --summary <summary> \
    --out docs/reports/agentdojo/import-cli-head.json --extra <history fields, census, determinism note>
uv run python tools/agentdojo/profile_census.py --profile agentdojo-upstream --part head --workers 2 --out docs/reports/agentdojo/census-head.json
```

| `agentprov import agentdojo --snapshot head` | |
|---|---|
| Exit code / wall time | 0 / 5,186 s |
| Candidates / mapped / sealed clean / with issues / degenerate / failed | 36,679 / 36,679 / 33,745 / 2,934 / 0 / 0 |
| Variant | `v0.k11` 24,914, `v1.k14` 11,764, `v1.k14.incomplete` 1 |
| `agent_execution` / `outcome_only` | 36,472 / 207 |
| Origins | `git` 36,679 (pin check: 36,679 blobs equal their tree entries) |
| AER valid (release) / SEM annotated / PROV tier 4 (strict) / PROV re-derived byte-identically | 36,679 each |
| Accounting / completeness | `unverifiable` 36,447, `consistent` 232 / `unverifiable` 36,364, `known_incomplete` 83, `verified_complete` 232 |
| Records | 1,153,595 |

Seal issues (files): `earlier_attempts_unobservable` 36,472, `accounting_unverifiable` 36,447, `agentdojo.local_parse_drop_possible`
1,854 (2,996 turns), `unexecuted_tool_call` 800, `no_execution_observed` 207, `outcome_imposed_by_runner` 105,
`retry_passes_inferred` 82, `incomplete_run` 1.

**What the refresh changed.** Every count above equals the 2026-10-09 report's. The report differs from it in the profile digest
(`bbc96ce0…` to `a13b76ba…`: the D.6.16 history-table pin), the AER stage code digests and the wall time (4,565 s), and in new keys:
`history_fields`, `profile_census` and `determinism`. The history index was cached, so the AERs now carry what the first report's
AERs did not: `introduced_in_commit` on every origin and `ext.agentdojo.committed_no_later_than` (36,679 logs; 50 distinct
introducing commits, 2024-06-02T12:26:48Z to 2025-07-25T17:05:15Z), and `benchmark_era` on the 24,914 `v0.k11` logs (`v1`
pre-versioning 14,182, `v1` 4,470, `v1.1` 1,088, `v1.1.1` 2,259, `v1.2` 2,915; the 11,765 `v1.k14` logs record their version and
get none), all equal to D.6.16 item 9. The census was regenerated: every `observed` count reproduces (`differences: []`); the
only change in `census-head.json` is the zero counts of the keys the wave-2 hooks added.

**Reproducibility.** No second import of this snapshot was run (`determinism.second_import = "not_run"`). The wave-1 branch copy
(`agentdojo-upstream-head-p10.pre-integration.partial`) is an independent import without the history index: against it the AERs
differ only in the history mechanism (profile digest, `introduced_in_commit`, the two ext members and their `evf` tags, the rule and
source lists that cite them, `records_sha256`), the SEM documents only in `aer_digest` and `records_sha256`, and the PROV documents
of all 36,679 executions are equal once identifiers and values derived from the AER digest and the `agentdojo` catalogue's
`apv:sha256` are set aside (`docs/reports/sem/README.md`, "Re-derivation after phase 10").
`docs/reports/sem/import-agentdojo-head.json` is the SEM-stage report of the same corpus.
