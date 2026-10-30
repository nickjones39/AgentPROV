# Post-check dossier: `agentdojo-upstream-2024-06`

## 1. Header

| | |
|---|---|
| Tree | `~/.agentprov/corpora/agentdojo-upstream-2024-06-rg1.partial` (working tree, read only) |
| Predecessor | `agentdojo-upstream-2024-06-p10.pre-regen.partial` |
| Built at | `5b1f6fdf` (the round) |
| Pre-check corpus · parts | `agentdojo-upstream` · `2024-06` |
| Post-check code | `505fa46d`, `7fedec72`, `d9f86cc5` (stage code: PC0) |
| Data | [`data/agentdojo-upstream-2024-06/`](data/agentdojo-upstream-2024-06/) |

## 2. Checks

| Check | Result |
|---|---|
| PC1 raw (8.3.1) | objects 18,241, equal True; origins rows equal True (object-origin pairs True); member rows equal True |
| PC2 population | ids 18,241 common, only old 0, only new 0; completeness = round True; issue codes net {} (= round True); stage digests changed {'aer': 18241, 'prov': 18241, 'sem': 18241, 'validation': 18241} |
| PC3 verify chain | exit 0, ok; executions_checked 18,241, raw_rehashed 18,241, failed 0; issues: `checksums.absent` 1 |
| PC4 recompute --dry-run --jobs 4 | exit 0, ok; identical 18,241, changed_explained 0, unexplained_change 0, failed 0, unverified 0; issues: none |
| PC5 validate --strict (aer,sem,prov,linkage) | exit 0, ok; passed 18,241, failed 0, checks_skipped 0, results_differ 0, linkage_resolved 18,241; issues: none |
| PC6 full population | executions 18,241 → 18,241; degenerate [0, 0], adapter_defect [0, 0]; SEM net = round True; 13 changed census leaves |
| PC8 outcomes | 156 arm × measure judgement counts, 0 moved |
| PC10 release-scan forecast | native 0, gitleaks 2 (section 4) |
| PC11 seal forecast | 0 refusal(s); 11 checks; 17 datasheet statements apply; withholding policy False |
| PC7 sample `2024-06` | 300/300 sampled labels found; pre-check scratch → rg1: 7 leaves |
| PC7b tie `2024-06` | 300/300 executions with every digest equal; differ by stage {}; stage code equal {'aer': True, 'prov': True, 'sem': True, 'validation': True} |
| Dispatch census | 145 executions, 153 unexecuted parts; {'core|entity|apv:NotDispatched': 153} |

## 3. Movement and attribution

SEM annotations, p10 → rg1 (net, by type and evidence class; the round's `compare.json` for the base corpus beside it):

| Type, class | Post-check | Round |
|---|---|---|
| agentdojo.partial_payload D | 537 | 537 |
| agentdojo.success_without_visible_payload D | 9 | 9 |

Level-2 census leaves that changed, p10 → rg1 (13; by section {'executions': 4, 'prov': 9}):

| Leaf | Old | New |
|---|---|---|
| `executions.counts.completeness:unverifiable` | 17,958 | 18,190 |
| `executions.counts.completeness:verified_complete` | 232 | — |
| `executions.stages.sem:agentdojo.suites@1:ok` | 18,241 | — |
| `executions.stages.sem:agentdojo.suites@2:ok` | — | 18,241 |
| `prov.checked.relation_arguments` | 9,177,743 | 9,724,337 |
| `prov.checked.statements` | 6,127,962 | 6,408,911 |
| `prov.evidence_by_bundle_class.assessment:D` | 107,094 | 107,640 |
| `prov.evidence_by_bundle_class.assessment:none` | 408,527 | 409,073 |
| `prov.evidence_by_bundle_class.core:D` | 1,320,994 | 1,291,972 |
| `prov.evidence_by_bundle_class.inference:I` | 1,492,483 | 1,588,290 |
| `prov.evidence_by_bundle_class.top:O` | 1,242,912 | 1,420,472 |
| `prov.evidence_by_bundle_class.top:none` | 150,081 | 185,593 |
| `prov.unverified_twin_by_bundle_class.inference:I` | — | 86,882 |

Sample `2024-06`: pre-check scratch (code `d97d3a57`) → rg1, per-execution leaves (0; the corpus-wide register codes and the file count differ by scope, R5):
- none

Attribution:

- SEM profile `agentdojo.suites@1` → `@2` (D-31 bump, item 1); every execution's SEM stage is renamed.
- AER activity records added (the round's compare: 16,210); item 5's environment-load activities are among them (gate D's crosscount on this tree: 16,003).
- SEM annotations added: `agentdojo.partial_payload` (item 6, the `partial` marker status) and `agentdojo.success_without_visible_payload` (D-377).
- Completeness: item 9 (and D-372 on head), as the round's table.
- `apv:dispatchStatus apv:NotDispatched` stays in the core bundle for all 153 unexecuted parts: this harness code is verified, so the unexecuted rule stays D (dispatch census).
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
| origin:2024-06 | pass |
| card_mode | pass |
| card_lint | pass |

Datasheet statements that apply: `art-benign-security-constant`, `art-defences-in-benign-runs`, `art-iteration-cap-cut`, `art-n2-escaped-newlines`, `art-n4-empty-final-replies`, `art-n7-activity-times`, `art-outcome-only-logs`, `art-payload-never-reached`, `art-provider-call-ids`, `art-run-error-imposed`, `art-silent-rerun`, `art-success-without-exposure`, `art-text-tool-calls`, `art-vacuous-utility`, `content-addressed-execution-ids`, `implied-prov-inferences`, `redaction-labels-guessable`.

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


## 8. Readiness for sealing

**ready-with-caveats**: Every check passes (0 seal refusals; release-mode re-import byte-identical). Caveat before a deposit: 2 gitleaks `generic-api-key` findings (the model-written UUID of PC-agentdojo-upstream-09, AER 1 and raw 1) need a `false-positive` triage entry.

## 9. Reproduction

```bash
uv run python tools/precheck/run_postcheck.py --list --only agentdojo-upstream-2024-06
uv run python tools/precheck/postcheck_compare.py --corpus agentdojo-upstream-2024-06
```
