# Post-check dossier: `agentdojo-upstream-head`

## 1. Header

| | |
|---|---|
| Tree | `~/.agentprov/corpora/agentdojo-upstream-head-rg1.partial` (working tree, read only) |
| Predecessor | `agentdojo-upstream-head-p10.pre-regen.partial` |
| Built at | `5b1f6fdf` (the round) |
| Pre-check corpus · parts | `agentdojo-upstream` · `head` |
| Post-check code | `505fa46d`, `7fedec72`, `d9f86cc5` (stage code: PC0) |
| Data | [`data/agentdojo-upstream-head/`](data/agentdojo-upstream-head/) |

## 2. Checks

| Check | Result |
|---|---|
| PC1 raw (8.3.1) | objects 36,679, equal True; origins rows equal True (object-origin pairs True); member rows equal True |
| PC2 population | ids 36,679 common, only old 0, only new 0; completeness = round True; issue codes net {} (= round True); stage digests changed {'aer': 36679, 'prov': 36679, 'sem': 36679, 'validation': 36679} |
| PC3 verify chain | exit 0, ok; executions_checked 36,679, raw_rehashed 36,679, failed 0; issues: `checksums.absent` 1 |
| PC4 recompute --dry-run --jobs 4 | exit 0, ok; identical 36,679, changed_explained 0, unexplained_change 0, failed 0, unverified 0; issues: none |
| PC5 validate --strict (aer,sem,prov,linkage) | exit 0, ok; passed 36,679, failed 0, checks_skipped 0, results_differ 0, linkage_resolved 36,679; issues: none |
| PC6 full population | executions 36,679 → 36,679; degenerate [0, 0], adapter_defect [0, 0]; SEM net = round True; 24 changed census leaves |
| PC8 outcomes | 258 arm × measure judgement counts, 0 moved |
| PC10 release-scan forecast | native 0, gitleaks 2 (section 4) |
| PC11 seal forecast | 0 refusal(s); 11 checks; 20 datasheet statements apply; withholding policy False |
| PC7 sample `head` | 313/313 sampled labels found; pre-check scratch → rg1: 20 leaves |
| PC7b tie `head` | 313/313 executions with every digest equal; differ by stage {}; stage code equal {'aer': True, 'prov': True, 'sem': True, 'validation': True} |
| Dispatch census | 800 executions, 815 unexecuted parts; {'core|entity|apv:NotDispatched': 136, 'inf|entity|apv:NotDispatched': 679} |

## 3. Movement and attribution

SEM annotations, p10 → rg1 (net, by type and evidence class; the round's `compare.json` for the base corpus beside it):

| Type, class | Post-check | Round |
|---|---|---|
| agentdojo.partial_payload D | 784 | 784 |
| agentdojo.success_without_visible_payload D | 11 | 11 |
| injection_marker D | -100,688 | -100,688 |
| injection_marker I | 100,688 | 100,688 |
| outcome D | -31,207 | -31,207 |
| outcome I | 31,207 | 31,207 |

Outcome annotations by log variant: outcome D v0.k11 -19,971, outcome D v1.k14 -11,236, outcome I v0.k11 19,971, outcome I v1.k14 11,236.

Level-2 census leaves that changed, p10 → rg1 (24; by section {'executions': 5, 'prov': 19}):

| Leaf | Old | New |
|---|---|---|
| `executions.counts.completeness:known_incomplete` | 83 | 47 |
| `executions.counts.completeness:unverifiable` | 36,364 | 36,632 |
| `executions.counts.completeness:verified_complete` | 232 | — |
| `executions.stages.sem:agentdojo.suites@1:ok` | 36,679 | — |
| `executions.stages.sem:agentdojo.suites@2:ok` | — | 36,679 |
| `prov.a3.unexecuted_missing.by.None` | — | 679 |
| `prov.a3.unexecuted_missing.count` | — | 679 |
| `prov.a3.unexecuted_missing.executions` | — | 672 |
| `prov.a3.unexecuted_represented.count` | 815 | 136 |
| `prov.checked.relation_arguments` | 19,732,718 | 26,754,036 |
| `prov.checked.statements` | 13,062,000 | 16,606,364 |
| `prov.evidence_by_bundle_class.assessment:D` | 216,760 | 138,644 |
| `prov.evidence_by_bundle_class.assessment:I` | 1,541,113 | 1,620,024 |
| `prov.evidence_by_bundle_class.assessment:none` | 852,619 | 853,414 |
| `prov.evidence_by_bundle_class.core:D` | 2,601,277 | 1,096,943 |
| `prov.evidence_by_bundle_class.inference:I` | 3,573,275 | 5,620,609 |
| `prov.evidence_by_bundle_class.inference:none` | 39,570 | 459,278 |
| `prov.evidence_by_bundle_class.top:O` | 2,551,393 | 4,701,448 |
| `prov.evidence_by_bundle_class.top:none` | 312,212 | 742,223 |
| `prov.mixed_twin_and_native_by_bundle_class.inference:I` | — | 592,914 |
| `prov.native_unverified_rule_by_bundle_class.inference:I` | 900,534 | 307,620 |
| `prov.unverified_twin_by_bundle_class.assessment:I` | — | 518,448 |
| `prov.unverified_twin_by_bundle_class.inference:I` | — | 3,852,612 |
| `prov.unverified_twin_by_bundle_class.inference:none` | — | 420,193 |

Sample `head`: pre-check scratch (code `d97d3a57`) → rg1, per-execution leaves (12; the corpus-wide register codes and the file count differ by scope, R5):
- `prov.a3.unexecuted_missing.by.None` — → 5
- `prov.a3.unexecuted_missing.count` — → 5
- `prov.a3.unexecuted_missing.executions` — → 5
- `prov.a3.unexecuted_represented.count` 8 → 3
- `prov.checked.relation_arguments` 219,177 → 222,515
- `prov.checked.statements` 136,468 → 138,680
- `prov.evidence_by_bundle_class.inference:I` 45,047 → 46,138
- `prov.evidence_by_bundle_class.inference:none` 2,675 → 3,766
- `prov.evidence_by_bundle_class.top:O` 38,271 → 38,296
- `prov.evidence_by_bundle_class.top:none` 5,964 → 5,969
- `prov.unverified_twin_by_bundle_class.inference:I` 28,888 → 29,979
- `prov.unverified_twin_by_bundle_class.inference:none` 2,337 → 3,428

Attribution:

- SEM profile `agentdojo.suites@1` → `@2` (D-31 bump, item 1); every execution's SEM stage is renamed.
- Outcome D→I 31,207: v1.k14 11,236 (D-359, decided) and v0.k11 19,971 (D-84, item 13: head-only logs cite the `_unverified` twins). Injection markers D→I 100,688 by the same rules.
- SEM annotations added: `agentdojo.partial_payload` (item 6, the `partial` marker status) and `agentdojo.success_without_visible_payload` (D-377).
- Completeness: item 9 (and D-372 on head), as the round's table.
- `apv:dispatchStatus apv:NotDispatched` moved from the core bundle to an inference-bundle mention for 679 of 815 unexecuted parts; 136 stay in core, where the rule stays D on verified code (D-80 addendum (d), 2026-10-15, regeneration-batch item 103: the TraceLogger and DRIFT builds cite the resolved rule, the `_unverified` twin under `verified_code = []`; the issue is a PROV premise since item 24). `l2_check`'s A3 `unexecuted` class reads the core element only and reports the moved parts as `unexecuted_missing`: a tool property (POST-tool-01), not a loss.
- Inference-bundle twin statements grew between the pre-check scratch import (`d97d3a57`) and the round (`5b1f6fdf`): equal I and unclassed increments in the inference bundles, the same kind in every AgentDojo-family part. Engine and catalogue items landed in that window (D-621 #15-#26, part C, regeneration items 105-167); the round's closed-world compare covers them. The post-check confirms the kind and the determinism (dry run identical, validation clean, release-mode re-import byte-identical), not a per-item split: the pre-check scratch trees no longer exist.

## 4. Release-scan forecast

| Scanner | Area : rule | Findings | Files |
|---|---|---|---|
| gitleaks 8.30.1 | aer:generic-api-key | 1 | |
| gitleaks 8.30.1 | raw-object:generic-api-key | 1 | |

Distinct account names (ordinals, never names): 0.

Triage against the benchmark suite data (in memory; `triage.json`, `triage-context.json`): the JSON member a match sits under and what follows the account segment (toolchain directory, user folder or other) are counts, never values:

| Ordinal | Length | Areas | Path in suite data | Name in suite data | JSON keys | Path tail |
|---|---|---|---|---|---|---|

Other rules, by whether the finding's line shares a 16+ character token (or a private-key header) with the suite data: aer:generic-api-key:not_in_suite_data 1, raw-object:generic-api-key:not_in_suite_data 1.


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
| origin:head | pass |
| card_mode | pass |
| card_lint | pass |

Datasheet statements that apply: `art-benign-security-constant`, `art-defences-in-benign-runs`, `art-empty-assistant-text`, `art-identical-trajectories`, `art-iteration-cap-cut`, `art-n2-escaped-newlines`, `art-n4-empty-final-replies`, `art-n7-activity-times`, `art-outcome-only-logs`, `art-package-version-not-code`, `art-payload-never-reached`, `art-provider-call-ids`, `art-run-error-imposed`, `art-silent-rerun`, `art-success-without-exposure`, `art-text-tool-calls`, `art-vacuous-utility`, `content-addressed-execution-ids`, `implied-prov-inferences`, `redaction-labels-guessable`.

## 6. Pre-check findings

| Finding | Status after the round |
|---|---|
| PC-agentdojo-upstream-01 | unchanged, as expected: a source-documentation or paper-vs-log item about raw-level outcomes; PC8 finds 0 outcome values moved; the disclosure stays with the datasheet and manuscript owner |
| PC-agentdojo-upstream-02 | unchanged, as expected: a source-documentation or paper-vs-log item about raw-level outcomes; PC8 finds 0 outcome values moved; the disclosure stays with the datasheet and manuscript owner |
| PC-agentdojo-upstream-03 | unchanged, as expected: a source-documentation or paper-vs-log item about raw-level outcomes; PC8 finds 0 outcome values moved; the disclosure stays with the datasheet and manuscript owner |
| PC-agentdojo-upstream-04 | moved as D-84 (item 13) predicts and as the pre-check found: head outcome D→I 19,971 v0.k11 (head-only logs) besides the D-359 11,236 v1.k14; the item-1 table correction is D-359's |
| PC-agentdojo-upstream-05 | resolved by the round: completeness transitions equal the round's table (item 9: verified_complete → unverifiable 232 on each; head also D-372 36) |
| PC-agentdojo-upstream-06 | open (CC-04 documentation); the engine still records `apv:paramsStatus` |
| PC-agentdojo-upstream-07 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |
| PC-agentdojo-upstream-08 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |
| PC-agentdojo-upstream-09 | unchanged: the one secret-like hit is a model-written UUID; gitleaks reports it as `generic-api-key` (AER 1, raw 1): release-scan triage `false-positive` |
| PC-agentdojo-upstream-10 | open (licence-basis text with the family owner) |
| PC-agentdojo-upstream-11 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |
| PC-agentdojo-upstream-12 | resolved by the round: fresh strict validation of the regenerated tree, 0 failed and `results_differ` 0 (PC5) |

## 7. Post-check findings

| Id | Class | Severity | Security | Title | Verdict |
|---|---|---|---|---|---|
| POST-tool-01 | analysis-artefact | S3 | False | l2_check's A3 `unexecuted` class reads only the core bundle | confirmed |

- **POST-tool-01**: l2_check's `_unexecuted` reads `view.elements`, which keeps the first declaration across bundles (the core element). Where D-80 addendum (d) (item 103) moved `apv:NotDispatched` into an inference-bundle mention, the A3 class reports the parts as `unexecuted_missing`. The dispatch census matches exactly: head 679 (of 815; 136 stay core), agentdyn-a 1,800, rope 753, ast-survey-agentdojo 49; 2024-06 (153) and adprov (48) did not move. Cross-cutting: recorded once, here. Recommendation: Future pre-checks: count `apv:dispatchStatus` in every bundle (post_check.py dispatch), or teach l2_check the inference-bundle mention; never read `unexecuted_missing` as a loss.

## 8. Readiness for sealing

**ready-with-caveats**: Every check passes (0 seal refusals; release-mode re-import byte-identical). Caveat before a deposit: 2 gitleaks `generic-api-key` findings (the model-written UUID of PC-agentdojo-upstream-09, AER 1 and raw 1) need a `false-positive` triage entry.

## 9. Reproduction

```bash
uv run python tools/precheck/run_postcheck.py --list --only agentdojo-upstream-head
uv run python tools/precheck/postcheck_compare.py --corpus agentdojo-upstream-head
```
