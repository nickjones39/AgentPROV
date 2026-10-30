# Post-check dossier: `adprov-v1-release-rg2`

## 1. Header

| | |
|---|---|
| Tree | `~/.agentprov/corpora/adprov-v1-release-rg2.partial` (working tree, read only) |
| Predecessor | `adprov-v1-release-rg1.partial` |
| Built at | `5b1f6fdf` (`derive --prov-spec adprov-v2.3-compat` from rg1, by the regeneration-plan session) |
| Pre-check corpus · parts | `adprov-v1` · `release` |
| Post-check code | `2a4c2f8c`, `7fedec72`, `d9f86cc5` (stage code: PC0) |
| Data | [`data/adprov-v1-release-rg2/`](data/adprov-v1-release-rg2/) |

## 2. Checks

| Check | Result |
|---|---|
| PC1 raw (8.3.1) | objects 17,664, equal True; origins rows equal True (object-origin pairs True); member rows equal True |
| PC2 population | ids 17,664 common, only old 0, only new 0; completeness = round True; issue codes net {} (= round True); stage digests changed {'aer': 0, 'prov': 17664, 'sem': 0, 'validation': 0} |
| PC3 verify chain | exit 0, ok; executions_checked 17,664, raw_rehashed 17,664, failed 0; issues: `checksums.absent` 1 |
| PC4 recompute --dry-run --jobs 4 | exit 0, ok; identical 17,664, changed_explained 0, unexplained_change 0, failed 0, unverified 0; issues: none |
| PC5 validate --strict (aer,sem,prov,linkage) | exit 0, ok; passed 17,664, failed 0, checks_skipped 0, results_differ 0, linkage_resolved 17,664; issues: none |
| PC6 full population | executions 17,664 → 17,664; degenerate [0, 0], adapter_defect [0, 0]; SEM net = round False; 27 changed census leaves |
| PC8 outcomes | 84 arm × measure judgement counts, 0 moved |
| PC10 release-scan forecast | native 17, gitleaks 4 (section 4) |
| PC11 seal forecast | 0 refusal(s); 11 checks; 14 datasheet statements apply; withholding policy False |
| PC7 sample `release` | 300/300 sampled labels found; pre-check scratch → rg2: 35 leaves |
| PC7b tie `release` | 0/300 executions with every digest equal; differ by stage {'prov': 300}; stage code equal {'aer': True, 'compat': False, 'prov': True, 'sem': True, 'validation': True} |
| Dispatch census | 47 executions, 48 unexecuted parts; {'core|entity|apv:NotDispatched': 48} |
| Oracle vs release graphs | {'byte_identical': 17664} (release pairs 17664) |

## 3. Movement and attribution

SEM annotations, rg1 → rg2 (net, by type and evidence class; the round's `compare.json` for the base corpus beside it):

| Type, class | Post-check | Round |
|---|---|---|
| agentdojo.partial_payload D | — | 787 |

Level-2 census leaves that changed, rg1 → rg2 (27; by section {'executions': 1, 'prov': 24, 'redaction': 2}):

| Leaf | Old | New |
|---|---|---|
| `executions.stages.prov:adprov-v2.3-compat:ok` | — | 17,664 |
| `prov.a3.missing_generation.by.assistant` | — | 64,897 |
| `prov.a3.missing_generation.by.tool` | — | 64,781 |
| `prov.a3.missing_generation.count` | — | 129,678 |
| `prov.a3.missing_generation.executions` | — | 17,664 |
| `prov.a3.missing_use_input.count` | — | 64,897 |
| `prov.a3.missing_use_input.executions` | — | 17,664 |
| `prov.a3.missing_use_request.count` | — | 64,781 |
| `prov.a3.missing_use_request.executions` | — | 16,247 |
| `prov.a3.time_not_run_scope.by.activity:unknown` | — | 64,779 |
| `prov.a3.time_not_run_scope.by.used:unknown` | — | 121,493 |
| `prov.a3.time_not_run_scope.by.wasGeneratedBy:unknown` | — | 64,779 |
| `prov.a3.time_not_run_scope.count` | 64,780 | 315,831 |
| `prov.a3.unexecuted_missing.by.no_node` | — | 48 |
| `prov.a3.unexecuted_missing.count` | — | 48 |
| `prov.a3.unexecuted_missing.executions` | — | 47 |
| `prov.checked.messages_with_generated_by` | 129,678 | 259,356 |
| `prov.checked.model_calls_with_input` | 64,897 | 129,794 |
| `prov.checked.relation_arguments` | 12,477,819 | 13,125,201 |
| `prov.checked.statements` | 7,845,231 | 8,333,812 |
| `prov.checked.statements_with_time` | 82,444 | 333,495 |
| `prov.checked.tool_executions_with_call` | 64,781 | 129,562 |
| `prov.checked.unexecuted_call_parts` | 48 | 96 |
| `prov.documents` | 17,664 | 35,328 |
| `prov.evidence_by_bundle_class.top:none` | 372,298 | 860,879 |
| `redaction.files_scanned` | 53,000 | 70,664 |
| `redaction.hits.prov.account-path /activity/{k}/adprov:args` | — | 6 |

Sample `release`: pre-check scratch (code `d97d3a57`) → rg2, per-execution leaves (29; the corpus-wide register codes and the file count differ by scope, R5):
- `executions.stages.prov:adprov-v2.3-compat:ok` — → 300
- `prov.a3.missing_generation.by.assistant` — → 1,114
- `prov.a3.missing_generation.by.tool` — → 1,177
- `prov.a3.missing_generation.count` — → 2,291
- `prov.a3.missing_generation.executions` — → 300
- `prov.a3.missing_use_input.count` — → 1,114
- `prov.a3.missing_use_input.executions` — → 300
- `prov.a3.missing_use_request.count` — → 1,177
- `prov.a3.missing_use_request.executions` — → 268
- `prov.a3.time_not_run_scope.by.activity:unknown` — → 1,177
- `prov.a3.time_not_run_scope.by.used:unknown` — → 2,154
- `prov.a3.time_not_run_scope.by.wasGeneratedBy:unknown` — → 1,177
- `prov.a3.time_not_run_scope.count` 1,177 → 5,685
- `prov.a3.unexecuted_missing.by.no_node` — → 2
- `prov.a3.unexecuted_missing.count` — → 2
- `prov.a3.unexecuted_missing.executions` — → 2
- `prov.checked.messages_with_generated_by` 2,291 → 4,582
- `prov.checked.model_calls_with_input` 1,114 → 2,228
- `prov.checked.relation_arguments` 204,191 → 222,881
- `prov.checked.statements` 128,166 → 141,608
- `prov.checked.statements_with_time` 1,477 → 5,985
- `prov.checked.tool_executions_with_call` 1,177 → 2,354
- `prov.checked.unexecuted_call_parts` 2 → 4
- `prov.documents` 300 → 600
- `prov.evidence_by_bundle_class.inference:I` 42,125 → 44,411
- `prov.evidence_by_bundle_class.inference:none` 2,891 → 5,177
- `prov.evidence_by_bundle_class.top:none` 6,188 → 15,058
- `prov.unverified_twin_by_bundle_class.inference:I` 34,539 → 36,825
- `prov.unverified_twin_by_bundle_class.inference:none` 2,591 → 4,877

Attribution:

- Only the 17,664 added `adprov-v2.3-compat` documents: `prov.documents` doubles, and their A3 `missing_generation` / `missing_use_*` / `time_not_run_scope` counts are the frozen v2.3 representation (invariant 8), not defects of `agentprov-prov/0.1`.
- Index rows: the compat entry and the H.3.1 fields `derive` writes (cell, ev, facets, oracles).

## 4. Release-scan forecast

| Scanner | Area : rule | Findings | Files |
|---|---|---|---|
| native path scan | aer:account-path | 6 | 2 |
| native path scan | prov:account-path | 5 | 4 |
| native path scan | raw-object:account-path | 6 | 2 |
| gitleaks 8.30.1 | aer:generic-api-key | 2 | |
| gitleaks 8.30.1 | raw-object:generic-api-key | 2 | |

Distinct account names (ordinals, never names): 1.

Triage against the benchmark suite data (in memory; `triage.json`, `triage-context.json`): the JSON member a match sits under and what follows the account segment (toolchain directory, user folder or other) are counts, never values:

| Ordinal | Length | Areas | Path in suite data | Name in suite data | JSON keys | Path tail |
|---|---|---|---|---|---|---|
| #1 | 4 | {'aer': 6, 'prov': 6, 'raw-object': 6} | False | True | {'(none)': 6, 'file_path': 12} | {'other': 12, 'user_dirs': 6} |

- The sample tie compares a release-mode scratch import without the compat spec, so PROV digests differ by that entry only (`stage_code_equal` aer, sem, prov, validation true).

## 5. Seal forecast

| Check | Result |
|---|---|
| working | pass |
| shard_depth | pass |
| changelog | pass |
| profile_version | pass |
| profile_digest | pass |
| context | pass |
| stages | pass |
| licences | pass |
| origin:release | pass |
| card_mode | pass |
| card_lint | pass |

Datasheet statements that apply: `adprov-release-writer`, `art-benign-security-constant`, `art-iteration-cap-cut`, `art-n2-escaped-newlines`, `art-n5-dropped-high-bytes`, `art-n6-completeness-model-confounded`, `art-n7-activity-times`, `art-n8-argument-types`, `art-payload-never-reached`, `art-silent-rerun`, `art-text-tool-calls`, `art-vacuous-utility`, `implied-prov-inferences`, `redaction-labels-guessable`.

## 6. Pre-check findings

| Finding | Status after the round |
|---|---|
| PC-adprov-v1-01 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |
| PC-adprov-v1-02 | n/a (a pre-registration comparison basis; no data issue) |
| PC-adprov-v1-03 | unchanged: 1 account ordinal, model-written fictional banking paths (`file_path`; the name occurs in the AgentDojo suite data), in raw 6, AER 6, PROV 5 (the compat `adprov:args` now carries it too); release-scan triage `synthetic-benchmark` or `false-positive` (see POST-adprov-v1-release-02) |
| PC-adprov-v1-04 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |
| PC-adprov-v1-05 | unchanged (expected-known; no exclusion) |
| PC-adprov-v1-06 | unchanged (the walk skips the 8 `.DS_Store` files) |
| PC-adprov-v1-07 | unchanged (raw-level) |
| PC-adprov-v1-08 | unchanged (DL-9 not exercised; not needed) |
| PC-adprov-v1-09 | resolved by the round: fresh strict validation of the regenerated tree, 0 failed and `results_differ` 0 (PC5) |
| PC-adprov-v1-10 | superseded by the post-check (PC6 = the round's compare; the sample's movement since the pre-check is the inference-twin kind, section 3) |
| PC-adprov-v1-11 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |

## 7. Post-check findings

| Id | Class | Severity | Security | Title | Verdict |
|---|---|---|---|---|---|
| POST-adprov-v1-release-02 | documentation-mismatch | S3 | False | Statement `benchmark-and-model-home-paths` does not list adprov-v1-release or rope | confirmed |

- **POST-adprov-v1-release-02**: Both hold model-written or benchmark home-directory paths in derived records (release-scan findings: adprov rg2 1 ordinal, AER 6 and PROV 5; rope 2 ordinals, AER 9 and PROV 3; all names occur in the AgentDojo or AgentDyn suite data), the case the statement discloses for agentdyn-a and ast-survey-agentharm. R4 / CC-03. Recommendation: Datasheet owner: the statement's text and figures are specific to its two corpora, so adding the ids is not enough: add a sentence or statement with these corpora's own counts (or record why none is needed) before the datasheets are rendered.

## 8. Readiness for sealing

**ready-with-caveats**: Every check passes: the seal forecast gives 0 refusals; the oracle is byte-identical to the AgentDojo-PROV release graphs for 17,664/17,664 traces; AER, SEM, `agentprov-prov/0.1` and validation digests equal rg1's on every row. Caveats before a deposit: release-scan triage of 1 account ordinal (model-written fictional banking paths) and 4 gitleaks `generic-api-key` findings, and the datasheet statement scope (POST-adprov-v1-release-02).

## 9. Reproduction

```bash
uv run python tools/precheck/run_postcheck.py --list --variant adprov-v1-release:rg2:rg1
uv run python tools/precheck/postcheck_compare.py --corpus adprov-v1-release-rg2 --variant adprov-v1-release:rg2:rg1
```
