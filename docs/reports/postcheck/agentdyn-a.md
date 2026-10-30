# Post-check dossier: `agentdyn-a`

## 1. Header

| | |
|---|---|
| Tree | `~/.agentprov/corpora/agentdyn-a-rg1.partial` (working tree, read only) |
| Predecessor | `agentdyn-a-p10.pre-regen.partial` |
| Built at | `5b1f6fdf` (the round) |
| Pre-check corpus · parts | `agentdyn` · `a` |
| Post-check code | `2a4c2f8c`, `505fa46d`, `7fedec72`, `d9f86cc5` (stage code: PC0) |
| Data | [`data/agentdyn-a/`](data/agentdyn-a/) |

## 2. Checks

| Check | Result |
|---|---|
| PC1 raw (8.3.1) | objects 47,723, equal True; origins rows equal True (object-origin pairs True); member rows equal True |
| PC2 population | ids 38,281 common, only old 0, only new 0; completeness = round True; issue codes net {'map.unattributed_additional_user_message': -266} (= round True); stage digests changed {'aer': 38281, 'prov': 38281, 'sem': 38281, 'validation': 38281} |
| PC3 verify chain | exit 0, ok; executions_checked 38,281, raw_rehashed 47,723, failed 0; issues: `checksums.absent` 1 |
| PC4 recompute --dry-run --jobs 4 | exit 0, ok; identical 38,281, changed_explained 0, unexplained_change 0, failed 0, unverified 0; issues: none |
| PC5 validate --strict (aer,sem,prov,linkage) | exit 0, ok; passed 38,281, failed 0, checks_skipped 0, results_differ 0, linkage_resolved 38,281; issues: none |
| PC6 full population | executions 38,281 → 38,281; degenerate [0, 0], adapter_defect [0, 0]; SEM net = round True; 38 changed census leaves |
| PC8 outcomes | 361 arm × measure judgement counts, 0 moved |
| PC10 release-scan forecast | native 3,028, gitleaks 2,498 (section 4) |
| PC11 seal forecast | 0 refusal(s); 11 checks; 28 datasheet statements apply; withholding policy False |
| PC7 sample `a` | 360/360 sampled labels found; pre-check scratch → rg1: 24 leaves |
| PC7b tie `a` | 360/360 executions with every digest equal; differ by stage {}; stage code equal {'aer': True, 'prov': True, 'sem': True, 'validation': True} |
| Dispatch census | 1683 executions, 1800 unexecuted parts; {'inf|entity|apv:NotDispatched': 1800} |

## 3. Movement and attribution

SEM annotations, p10 → rg1 (net, by type and evidence class; the round's `compare.json` for the base corpus beside it):

| Type, class | Post-check | Round |
|---|---|---|
| agentdojo.partial_payload D | 1,020 | 1,020 |
| agentdojo.success_without_visible_payload D | 10 | 10 |
| channel I | 96,640 | 96,640 |
| injection_marker D | -441,750 | -441,750 |
| injection_marker I | 441,750 | 441,750 |
| outcome D | -71,352 | -71,352 |
| outcome I | 71,352 | 71,352 |

Outcome annotations by log variant: outcome D v1.k14 -71,352, outcome I v1.k14 71,352.

Level-2 census leaves that changed, p10 → rg1 (38; by section {'executions': 8, 'issues': 2, 'prov': 21, 'redaction': 7}):

| Leaf | Old | New |
|---|---|---|
| `executions.counts.completeness:known_incomplete` | 837 | 12 |
| `executions.counts.completeness:unverifiable` | 37,444 | 38,269 |
| `executions.counts.status:ok` | 35,904 | 36,070 |
| `executions.counts.status:ok_with_issues` | 2,377 | 2,211 |
| `executions.register_codes.map.unattributed_additional_user_message` | 266 | — |
| `executions.register_codes.select.owned_elsewhere` | 949 | — |
| `executions.stages.sem:agentdojo.suites@1:ok` | 38,281 | — |
| `executions.stages.sem:agentdojo.suites@3:ok` | — | 38,281 |
| `issues.index_issue_codes.map.unattributed_additional_user_message` | 266 | — |
| `issues.seal_issue_codes.unattributed_additional_user_message` | 1,674 | — |
| `prov.a3.unexecuted_missing.by.None` | — | 1,800 |
| `prov.a3.unexecuted_missing.count` | — | 1,800 |
| `prov.a3.unexecuted_missing.executions` | — | 1,683 |
| `prov.a3.unexecuted_represented.count` | 1,800 | — |
| `prov.a3.unexecuted_represented.executions` | 0 | — |
| `prov.checked.model_calls_with_input` | 231,952 | 229,610 |
| `prov.checked.relation_arguments` | 37,469,176 | 46,675,871 |
| `prov.checked.statements` | 24,700,855 | 28,900,316 |
| `prov.evidence_by_bundle_class.assessment:D` | 210,676 | 1,030 |
| `prov.evidence_by_bundle_class.assessment:I` | 5,229,889 | 4,492,647 |
| `prov.evidence_by_bundle_class.assessment:none` | 1,119,837 | 1,217,507 |
| `prov.evidence_by_bundle_class.core:D` | 829,593 | 188,172 |
| `prov.evidence_by_bundle_class.inference:I` | 10,284,781 | 11,690,718 |
| `prov.evidence_by_bundle_class.inference:none` | 557,051 | 1,231,589 |
| `prov.evidence_by_bundle_class.top:O` | 4,025,004 | 7,033,025 |
| `prov.evidence_by_bundle_class.top:none` | 575,315 | 1,176,919 |
| `prov.mixed_twin_and_native_by_bundle_class.inference:I` | 840,630 | 1,308,356 |
| `prov.native_unverified_rule_by_bundle_class.inference:I` | 467,726 | — |
| `prov.unverified_twin_by_bundle_class.assessment:I` | 420,608 | 1,227,143 |
| `prov.unverified_twin_by_bundle_class.inference:I` | 8,435,484 | 9,947,966 |
| `prov.unverified_twin_by_bundle_class.inference:none` | 484,917 | 1,187,330 |
| `redaction.hits.prov.account-path /bundle/xd:bundle.core.ldhunsnxmroupxdxjgbobmhonb/entity/{k}/apv:args` | 1 | — |
| `redaction.hits.prov.account-path /bundle/xd:bundle.core.ldhunsnxmroupxdxjgbobmhonb/entity/{k}/apv:error` | 1 | — |
| `redaction.hits.prov.account-path /bundle/xd:bundle.core.pyqbragccktlqfbgjutewxrdft/entity/{k}/apv:args` | 8 | — |
| `redaction.hits.prov.account-path /bundle/{k}/entity/{k}/apv:args` | 527 | 536 |
| `redaction.hits.prov.account-path /bundle/{k}/entity/{k}/apv:error` | 66 | 67 |
| `redaction.hits.prov.secret:private-key-header /bundle/xd:bundle.core.sjfujplcbwgkawyaeuvmrqbzaj/entity/{k}/apv:args` | — | 1 |
| `redaction.hits.prov.secret:private-key-header /bundle/{k}/entity/{k}/apv:args` | 70 | 69 |

Sample `a`: pre-check scratch (code `d97d3a57`) → rg1, per-execution leaves (13; the corpus-wide register codes and the file count differ by scope, R5):
- `prov.a3.unexecuted_missing.by.None` — → 21
- `prov.a3.unexecuted_missing.count` — → 21
- `prov.a3.unexecuted_missing.executions` — → 18
- `prov.a3.unexecuted_represented.count` 21 → —
- `prov.a3.unexecuted_represented.executions` 0 → —
- `prov.checked.relation_arguments` 389,692 → 404,590
- `prov.checked.statements` 239,403 → 249,287
- `prov.evidence_by_bundle_class.inference:I` 93,565 → 98,453
- `prov.evidence_by_bundle_class.inference:none` 5,939 → 10,827
- `prov.evidence_by_bundle_class.top:O` 64,385 → 64,475
- `prov.evidence_by_bundle_class.top:none` 10,717 → 10,735
- `prov.unverified_twin_by_bundle_class.inference:I` 80,161 → 85,049
- `prov.unverified_twin_by_bundle_class.inference:none` 5,525 → 10,413

Attribution:

- SEM profile `agentdojo.suites@1` → `@3` (regeneration-batch item 27 (b); the spec's semantics profile).
- SEM outcome and injection-marker annotations move D to I by item 3 / D-24 / D-80: the SEM rules' `_unverified` twins on unverified-harness code (`verified_code = []`). The pre-check's stored-vs-fresh tables attributed the same move on the samples.
- Channel annotations I +96,640 (the round's compare).
- Register: the 949 `select.owned_elsewhere` rows (DRIFT copies under `src/`, owner `drift`) are not recorded: they lie outside the pin's subtree `runs/`, which the round's `--fetch` import walks; the p10 import walked the whole local clone (POST-agentdyn-a-01).
- Issue codes: `map.unattributed_additional_user_message` −266 (item 2: CaMeL interpreter feedback is attributed, so those 266 logs lose the code; regen-batch items 2-4-12).
- Completeness: known_incomplete → unverifiable 825 (the round's table).
- `apv:dispatchStatus apv:NotDispatched` moved from the core bundle to an inference-bundle mention for 1,800 of 1,800 unexecuted parts (D-80 addendum (d), 2026-10-15, regeneration-batch item 103: the TraceLogger and DRIFT builds cite the resolved rule, the `_unverified` twin under `verified_code = []`; the issue is a PROV premise since item 24). `l2_check`'s A3 `unexecuted` class reads the core element only and reports the moved parts as `unexecuted_missing`: a tool property (POST-tool-01), not a loss.
- Inference-bundle twin statements grew between the pre-check scratch import (`d97d3a57`) and the round (`5b1f6fdf`): equal I and unclassed increments in the inference bundles, the same kind in every AgentDojo-family part. Engine and catalogue items landed in that window (D-621 #15-#26, part C, regeneration items 105-167); the round's closed-world compare covers them. The post-check confirms the kind and the determinism (dry run identical, validation clean, release-mode re-import byte-identical), not a per-item split: the pre-check scratch trees no longer exist.

## 4. Release-scan forecast

| Scanner | Area : rule | Findings | Files |
|---|---|---|---|
| native path scan | aer:account-path | 1,248 | 111 |
| native path scan | prov:account-path | 94 | 94 |
| native path scan | raw-object:account-path | 1,686 | 140 |
| gitleaks 8.30.1 | aer:generic-api-key | 1,114 | |
| gitleaks 8.30.1 | aer:private-key | 139 | |
| gitleaks 8.30.1 | prov:private-key | 6 | |
| gitleaks 8.30.1 | raw-object:generic-api-key | 1,134 | |
| gitleaks 8.30.1 | raw-object:private-key | 105 | |

Distinct account names (ordinals, never names): 20.

Triage against the benchmark suite data (in memory; `triage.json`, `triage-context.json`): the JSON member a match sits under and what follows the account segment (toolchain directory, user folder or other) are counts, never values:

| Ordinal | Length | Areas | Path in suite data | Name in suite data | JSON keys | Path tail |
|---|---|---|---|---|---|---|
| #1 | 9 | {'aer': 42, 'prov': 14, 'raw-object': 30} | False | False | {'(none)': 14, 'file_path': 5, 'local_dir_path': 20, 'local_path': 20, 'path': 10, 'save_dir': 5} | {'user_dirs': 86} |
| #2 | 11 | {'aer': 808, 'prov': 132, 'raw-object': 763} | False | True | {'(none)': 863, 'content': 87, 'local_dir_path': 196, 'local_path': 108, 'path': 236, 'text': 75} | {'other': 786, 'user_dirs': 917} |
| #3 | 11 | {'aer': 587, 'prov': 141, 'raw-object': 530} | False | False | {'(none)': 526, 'content': 66, 'destination_path': 85, 'local_dir_path': 219, 'path': 117, 'source_path': 85} | {'other': 1085, 'user_dirs': 173} |
| #4 | 4 | {'aer': 201, 'prov': 46, 'raw-object': 172} | False | True | {'(none)': 96, 'content': 45, 'local_dir_path': 131, 'local_path': 47, 'path': 40, 'text': 40} | {'other': 341, 'user_dirs': 78} |
| #5 | 4 | {'aer': 510, 'prov': 134, 'raw-object': 438} | False | True | {'(none)': 296, 'content': 88, 'local_dir_path': 108, 'local_path': 109, 'path': 223, 'text': 74} | {'other': 965, 'user_dirs': 117} |
| #6 | 12 | {'aer': 177, 'prov': 45, 'raw-object': 153} | False | True | {'(none)': 46, 'content': 46, 'local_dir_path': 59, 'local_path': 50, 'path': 46, 'save_dir': 51} | {'other': 261, 'user_dirs': 114} |
| #7 | 5 | {'aer': 3, 'prov': 1, 'raw-object': 2} | False | False | {'(none)': 1, 'save_dir': 5} | {'other': 6} |
| #8 | 15 | {'aer': 20, 'prov': 5, 'raw-object': 15} | False | False | {'(none)': 5, 'content': 5, 'local_dir_path': 10, 'local_path': 10, 'path': 5, 'text': 5} | {'other': 24, 'user_dirs': 16} |
| #9 | 16 | {'aer': 4, 'prov': 1, 'raw-object': 3} | False | True | {'(none)': 1, 'content': 1, 'local_dir_path': 5, 'text': 1} | {'other': 8} |
| #10 | 3 | {'aer': 8, 'prov': 1, 'raw-object': 8} | False | True | {'(none)': 15, 'path': 2} | {'other': 3, 'user_dirs': 14} |
| #11 | 18 | {'aer': 10, 'prov': 3, 'raw-object': 7} | False | True | {'(none)': 3, 'content': 1, 'file_path': 5, 'path': 10, 'text': 1} | {'other': 20} |
| #12 | 11 | {'aer': 3, 'prov': 1, 'raw-object': 2} | False | False | {'(none)': 1, 'save_dir': 5} | {'other': 6} |
| #13 | 4 | {'aer': 4, 'prov': 1, 'raw-object': 3} | False | True | {'(none)': 1, 'content': 1, 'local_dir_path': 5, 'text': 1} | {'other': 8} |
| #14 | 11 | {'aer': 1, 'prov': 1, 'raw-object': 1} | False | False | {'(none)': 1, 'local_dir_path': 2} | {'other': 3} |
| #15 | 7 | {'aer': 4, 'prov': 1, 'raw-object': 3} | False | True | {'(none)': 1, 'content': 1, 'local_dir_path': 5, 'text': 1} | {'other': 8} |
| #16 | 11 | {'aer': 32, 'prov': 10, 'raw-object': 23} | False | True | {'(none)': 12, 'file_path': 10, 'local_dir_path': 10, 'local_path': 5, 'path': 20, 'text': 3} | {'other': 65} |
| #17 | 4 | {'aer': 4, 'prov': 2, 'raw-object': 3} | False | True | {'(none)': 2, 'error': 2, 'path': 5} | {'other': 9} |
| #18 | 10 | {'raw-object': 2} | False | False | {'file_path': 2} | {'other': 2} |
| #19 | 8 | {'raw-object': 2} | False | False | {'source_path': 2} | {'other': 2} |
| #20 | 12 | {'raw-object': 19} | False | False | {'(none)': 7, 'content': 6, 'local_dir_path': 4, 'path': 2} | {'other': 16, 'user_dirs': 3} |

Other rules, by whether the finding's line shares a 16+ character token (or a private-key header) with the suite data: aer:generic-api-key:in_suite_data 13, aer:generic-api-key:not_in_suite_data 1,101, aer:private-key:in_suite_data 136, aer:private-key:not_in_suite_data 3, prov:private-key:in_suite_data 5, prov:private-key:not_in_suite_data 1, raw-object:generic-api-key:in_suite_data 16, raw-object:generic-api-key:not_in_suite_data 1,118, raw-object:private-key:in_suite_data 102, raw-object:private-key:not_in_suite_data 3.


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
| origin:a | pass |
| card_mode | pass |
| card_lint | pass |

Datasheet statements that apply: `agentdyn-gemini-2-5-pro-undefended`, `agentdyn-gemini-undefended-baseline`, `agentdyn-suite-fixture-key`, `art-agentdyn-generations`, `art-benign-security-constant`, `art-camel-feedback-as-user`, `art-defences-in-benign-runs`, `art-drift-post-isolation`, `art-empty-assistant-text`, `art-identical-trajectories`, `art-iteration-cap-cut`, `art-n2-escaped-newlines`, `art-n4-empty-final-replies`, `art-n5-dropped-high-bytes`, `art-n7-activity-times`, `art-n8-argument-types`, `art-package-version-not-code`, `art-payload-never-reached`, `art-provider-call-ids`, `art-run-error-imposed`, `art-silent-rerun`, `art-success-without-exposure`, `art-text-tool-calls`, `art-vacuous-utility`, `benchmark-and-model-home-paths`, `core-only-consumers`, `implied-prov-inferences`, `redaction-labels-guessable`.

## 6. Pre-check findings

| Finding | Status after the round |
|---|---|
| PC-agentdyn-01 | unchanged, as expected: a source-documentation or paper-vs-log item about raw-level outcomes; PC8 finds 0 outcome values moved; the disclosure stays with the datasheet and manuscript owner |
| PC-agentdyn-02 | unchanged, as expected: a source-documentation or paper-vs-log item about raw-level outcomes; PC8 finds 0 outcome values moved; the disclosure stays with the datasheet and manuscript owner |
| PC-agentdyn-03 | unchanged, as expected: a source-documentation or paper-vs-log item about raw-level outcomes; PC8 finds 0 outcome values moved; the disclosure stays with the datasheet and manuscript owner |
| PC-agentdyn-04 | unchanged, as expected: a source-documentation or paper-vs-log item about raw-level outcomes; PC8 finds 0 outcome values moved; the disclosure stays with the datasheet and manuscript owner |
| PC-agentdyn-05 | unchanged (raw-level source defect, AgentDyn issue #6); artefact and datasheet note with the family owner |
| PC-agentdyn-06 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |
| PC-agentdyn-07 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |
| PC-agentdyn-08 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |
| PC-agentdyn-09 | n/a (pre-registration wording) |
| PC-agentdyn-10 | unchanged (C5 table; no exclusion) |
| PC-agentdyn-11 | unchanged (C5 table) |
| PC-agentdyn-12 | unchanged, disclosed by `benchmark-and-model-home-paths` (agentdyn-a listed); triage counts in section 4 |
| PC-agentdyn-13 | unchanged, disclosed by `agentdyn-suite-fixture-key`; 243 of 250 `private-key` findings are the fixture |
| PC-agentdyn-14 | resolved by the round: fresh strict validation of the regenerated tree, 0 failed and `results_differ` 0 (PC5) |
| PC-agentdyn-15 | n/a for this tree (part b is not in the round) |
| PC-agentdyn-16 | n/a for this tree (part b) |
| PC-agentdyn-17 | n/a for this tree (part b) |

## 7. Post-check findings

| Id | Class | Severity | Security | Title | Verdict |
|---|---|---|---|---|---|
| POST-agentdyn-a-01 | documentation-mismatch | S3 | False | The register's out-of-pin `select.*` rows depend on the import route | confirmed |

- **POST-agentdyn-a-01**: rg1 (imported with `--fetch`) records 0 of p10's 949 `select.owned_elsewhere` rows (DRIFT copies under `src/agentdojo/defenses/drift/runs/`, owner `drift`); ast-survey-agentdojo likewise 0 of 6 `select.owned_elsewhere` (the AgentHarm `.eval` files, owner ast-survey-agentharm) and 0 of 4 `select.dialect_planned` (`asb/` CSVs). All lie outside the pin's subtree (`runs/`, `agentdojo`): a fetched git-pin tree walks only the pin's subtree, the p10 `--input` import walked the whole local clone. Every file of the snapshot keeps its disposition; executions, verify and the seal forecast are unaffected. p10's origins are `local` (the `--input` route), which `package` refuses (D-33), so the register the spec describes (`D_adapters.md`: the 949 DRIFT copies `select.owned_elsewhere`; the survey's six `.eval` rows) belongs to a route that cannot be sealed. Side effect: these profile excludes (`src/agentdojo/defenses/drift/runs/**`, `agentharm/results/**/*.eval`, `asb/results/*.csv`) can never fire under `--fetch`. R4. Recommendation: Runner/spec owner: state which route defines the register (pin subtree only, or the whole tree), update the D.6.x text and the H.6.2 ownership reading accordingly. No corpus change needed for the seal.

## 8. Readiness for sealing

**ready-with-caveats**: Every check passes (0 seal refusals; release-mode re-import byte-identical 360/360). Caveats before a deposit: a large release-scan triage. 3,028 `account-path` findings in 20 ordinals: AgentDyn personas and model-written tool-argument paths (`local_dir_path`, `save_dir`, `path`, `file_path`), none under a toolchain directory; 3 raw-only ordinals (#18-#20) are tool arguments in raw logs that do not map to AER. 2,498 gitleaks findings: 250 `private-key` (243 the AgentDyn fixture key, CC-02, statement `agentdyn-suite-fixture-key`; 7 not in the suite data) and 2,248 `generic-api-key` (29 sharing a token with the suite data). Disclosures stay as the pre-check routed them.

## 9. Reproduction

```bash
uv run python tools/precheck/run_postcheck.py --list --only agentdyn-a
uv run python tools/precheck/postcheck_compare.py --corpus agentdyn-a
```
