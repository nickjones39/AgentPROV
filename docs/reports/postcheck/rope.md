# Post-check dossier: `rope`

## 1. Header

| | |
|---|---|
| Tree | `~/.agentprov/corpora/rope-rg1.partial` (working tree, read only) |
| Predecessor | `rope-p10.pre-regen.partial` |
| Built at | `5b1f6fdf` (the round) |
| Pre-check corpus · parts | `rope` · `head`; `rope` · `rope-slice` |
| Post-check code | `2a4c2f8c`, `505fa46d`, `7fedec72`, `d9f86cc5` (stage code: PC0) |
| Data | [`data/rope/`](data/rope/) |

## 2. Checks

| Check | Result |
|---|---|
| PC1 raw (8.3.1) | objects 10,826, equal True; origins rows equal True (object-origin pairs True); member rows equal True |
| PC2 population | ids 10,791 common, only old 0, only new 0; completeness = round True; issue codes net {} (= round True); stage digests changed {'aer': 10791, 'prov': 10791, 'sem': 10791, 'validation': 10791} |
| PC3 verify chain | exit 0, ok; executions_checked 10,791, raw_rehashed 10,826, failed 0; issues: `checksums.absent` 1 |
| PC4 recompute --dry-run --jobs 4 | exit 0, ok; identical 10,791, changed_explained 0, unexplained_change 0, failed 0, unverified 0; issues: none |
| PC5 validate --strict (aer,sem,prov,linkage) | exit 0, ok; passed 10,791, failed 0, checks_skipped 0, results_differ 0, linkage_resolved 10,791; issues: none |
| PC6 full population | executions 10,791 → 10,791; degenerate [0, 0], adapter_defect [0, 0]; SEM net = round True; 25 changed census leaves |
| PC8 outcomes | 48 arm × measure judgement counts, 0 moved |
| PC10 release-scan forecast | native 21, gitleaks 292 (section 4) |
| PC11 seal forecast | 0 refusal(s); 11 checks; 24 datasheet statements apply; withholding policy False |
| PC7 sample `head` | 300/300 sampled labels found; pre-check scratch → rg1: 21 leaves |
| PC7b tie `head` | 300/300 executions with every digest equal; differ by stage {}; stage code equal {'aer': True, 'prov': True, 'sem': True, 'validation': True} |
| PC7 sample `rope-slice` | 90/90 sampled labels found; pre-check scratch → rg1: 21 leaves |
| PC7b tie `rope-slice` | 90/90 executions with every digest equal; differ by stage {}; stage code equal {'aer': True, 'prov': True, 'sem': True, 'validation': True} |
| Dispatch census | 675 executions, 753 unexecuted parts; {'inf|entity|apv:Denied': 1709, 'inf|entity|apv:NotDispatched': 753} |

## 3. Movement and attribution

SEM annotations, p10 → rg1 (net, by type and evidence class; the round's `compare.json` for the base corpus beside it):

| Type, class | Post-check | Round |
|---|---|---|
| agentdojo.partial_payload D | 2,659 | 2,659 |
| agentdojo.success_without_visible_payload D | 5 | 5 |
| injection_marker D | -183,896 | -183,896 |
| injection_marker I | 183,896 | 183,896 |
| outcome D | -21,508 | -21,508 |
| outcome I | 21,508 | 21,508 |

Outcome annotations by log variant: outcome D v1.k14 -21,508, outcome I v1.k14 21,508.

Level-2 census leaves that changed, p10 → rg1 (25; by section {'executions': 5, 'prov': 20}):

| Leaf | Old | New |
|---|---|---|
| `executions.counts.completeness:known_incomplete` | 322 | — |
| `executions.counts.completeness:unverifiable` | 10,467 | 10,791 |
| `executions.counts.completeness:verified_complete` | 2 | — |
| `executions.stages.sem:agentdojo.suites@1:ok` | 10,791 | — |
| `executions.stages.sem:agentdojo.suites@2:ok` | — | 10,791 |
| `prov.a3.unexecuted_missing.by.None` | — | 753 |
| `prov.a3.unexecuted_missing.count` | — | 753 |
| `prov.a3.unexecuted_missing.executions` | — | 675 |
| `prov.a3.unexecuted_represented.count` | 753 | — |
| `prov.a3.unexecuted_represented.executions` | 0 | — |
| `prov.checked.relation_arguments` | 12,942,819 | 16,030,919 |
| `prov.checked.statements` | 8,472,594 | 10,052,952 |
| `prov.evidence_by_bundle_class.assessment:D` | 79,896 | 2,664 |
| `prov.evidence_by_bundle_class.assessment:I` | 1,805,641 | 1,891,015 |
| `prov.evidence_by_bundle_class.assessment:none` | 397,907 | 400,571 |
| `prov.evidence_by_bundle_class.core:D` | 248,637 | 55,915 |
| `prov.evidence_by_bundle_class.inference:I` | 3,618,633 | 4,074,125 |
| `prov.evidence_by_bundle_class.inference:none` | 199,914 | 420,291 |
| `prov.evidence_by_bundle_class.top:O` | 1,303,990 | 2,214,406 |
| `prov.evidence_by_bundle_class.top:none` | 187,140 | 363,129 |
| `prov.mixed_twin_and_native_by_bundle_class.inference:I` | 300,802 | 483,091 |
| `prov.native_unverified_rule_by_bundle_class.inference:I` | 182,289 | — |
| `prov.unverified_twin_by_bundle_class.assessment:I` | 139,904 | 428,034 |
| `prov.unverified_twin_by_bundle_class.inference:I` | 2,958,024 | 3,435,899 |
| `prov.unverified_twin_by_bundle_class.inference:none` | 163,809 | 395,778 |

Sample `head`: pre-check scratch (code `d97d3a57`) → rg1, per-execution leaves (13; the corpus-wide register codes and the file count differ by scope, R5):
- `prov.a3.unexecuted_missing.by.None` — → 23
- `prov.a3.unexecuted_missing.count` — → 23
- `prov.a3.unexecuted_missing.executions` — → 20
- `prov.a3.unexecuted_represented.count` 23 → —
- `prov.a3.unexecuted_represented.executions` 0 → —
- `prov.checked.relation_arguments` 419,682 → 435,440
- `prov.checked.statements` 262,887 → 273,336
- `prov.evidence_by_bundle_class.inference:I` 105,163 → 110,323
- `prov.evidence_by_bundle_class.inference:none` 6,309 → 11,469
- `prov.evidence_by_bundle_class.top:O` 59,818 → 59,927
- `prov.evidence_by_bundle_class.top:none` 9,763 → 9,783
- `prov.unverified_twin_by_bundle_class.inference:I` 89,438 → 94,598
- `prov.unverified_twin_by_bundle_class.inference:none` 5,715 → 10,875

Sample `rope-slice`: pre-check scratch (code `d97d3a57`) → rg1, per-execution leaves (13; the corpus-wide register codes and the file count differ by scope, R5):
- `prov.a3.unexecuted_missing.by.None` — → 9
- `prov.a3.unexecuted_missing.count` — → 9
- `prov.a3.unexecuted_missing.executions` — → 9
- `prov.a3.unexecuted_represented.count` 9 → —
- `prov.a3.unexecuted_represented.executions` 0 → —
- `prov.checked.relation_arguments` 122,335 → 126,910
- `prov.checked.statements` 75,758 → 78,783
- `prov.evidence_by_bundle_class.inference:I` 30,609 → 32,093
- `prov.evidence_by_bundle_class.inference:none` 1,831 → 3,315
- `prov.evidence_by_bundle_class.top:O` 18,344 → 18,392
- `prov.evidence_by_bundle_class.top:none` 3,010 → 3,019
- `prov.unverified_twin_by_bundle_class.inference:I` 25,546 → 27,030
- `prov.unverified_twin_by_bundle_class.inference:none` 1,647 → 3,131

Attribution:

- SEM profile `agentdojo.suites@1` → `@2` (D-31 bump, item 1); every execution's SEM stage is renamed.
- SEM outcome and injection-marker annotations move D to I by item 3 / D-24 / D-80: the SEM rules' `_unverified` twins on unverified-harness code (`verified_code = []`). The pre-check's stored-vs-fresh tables attributed the same move on the samples.
- Completeness: D-372 322 and item 9 2, as the round's table.
- `apv:dispatchStatus apv:NotDispatched` moved from the core bundle to an inference-bundle mention for 753 of 753 unexecuted parts (D-80 addendum (d), 2026-10-15, regeneration-batch item 103: the TraceLogger and DRIFT builds cite the resolved rule, the `_unverified` twin under `verified_code = []`; the issue is a PROV premise since item 24). `l2_check`'s A3 `unexecuted` class reads the core element only and reports the moved parts as `unexecuted_missing`: a tool property (POST-tool-01), not a loss.
- `apv:Denied` (1,709 parts, the ROPE guard denials) was already in the inference bundle in p10.
- Inference-bundle twin statements grew between the pre-check scratch import (`d97d3a57`) and the round (`5b1f6fdf`): equal I and unclassed increments in the inference bundles, the same kind in every AgentDojo-family part. Engine and catalogue items landed in that window (D-621 #15-#26, part C, regeneration items 105-167); the round's closed-world compare covers them. The post-check confirms the kind and the determinism (dry run identical, validation clean, release-mode re-import byte-identical), not a per-item split: the pre-check scratch trees no longer exist.

## 4. Release-scan forecast

| Scanner | Area : rule | Findings | Files |
|---|---|---|---|
| native path scan | aer:account-path | 9 | 3 |
| native path scan | prov:account-path | 3 | 3 |
| native path scan | raw-object:account-path | 9 | 3 |
| gitleaks 8.30.1 | aer:generic-api-key | 64 | |
| gitleaks 8.30.1 | aer:private-key | 74 | |
| gitleaks 8.30.1 | prov:private-key | 4 | |
| gitleaks 8.30.1 | raw-object:generic-api-key | 72 | |
| gitleaks 8.30.1 | raw-object:private-key | 78 | |

Distinct account names (ordinals, never names): 2.

Triage against the benchmark suite data (in memory; `triage.json`, `triage-context.json`): the JSON member a match sits under and what follows the account segment (toolchain directory, user folder or other) are counts, never values:

| Ordinal | Length | Areas | Path in suite data | Name in suite data | JSON keys | Path tail |
|---|---|---|---|---|---|---|
| #1 | 11 | {'aer': 8, 'prov': 2, 'raw-object': 6} | False | True | {'(none)': 2, 'content': 2, 'local_dir_path': 10, 'text': 2} | {'other': 16} |
| #2 | 4 | {'aer': 4, 'prov': 1, 'raw-object': 3} | False | True | {'(none)': 1, 'content': 1, 'local_dir_path': 5, 'text': 1} | {'other': 8} |

Other rules, by whether the finding's line shares a 16+ character token (or a private-key header) with the suite data: aer:generic-api-key:in_suite_data 14, aer:generic-api-key:not_in_suite_data 50, aer:private-key:in_suite_data 74, prov:private-key:in_suite_data 4, raw-object:generic-api-key:in_suite_data 22, raw-object:generic-api-key:not_in_suite_data 50, raw-object:private-key:in_suite_data 78.


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

Datasheet statements that apply: `agentdyn-suite-fixture-key`, `art-autodojo-yaml-escaped`, `art-benign-security-constant`, `art-defences-in-benign-runs`, `art-identical-trajectories`, `art-iteration-cap-cut`, `art-n2-escaped-newlines`, `art-n4-empty-final-replies`, `art-n7-activity-times`, `art-n8-argument-types`, `art-outcome-only-logs`, `art-package-version-not-code`, `art-payload-never-reached`, `art-provider-call-ids`, `art-rope-effect-corrections`, `art-rope-long-horizon-version`, `art-rope-tag-names-another-model`, `art-silent-rerun`, `art-success-without-exposure`, `art-text-tool-calls`, `art-vacuous-utility`, `core-only-consumers`, `implied-prov-inferences`, `redaction-labels-guessable`.

## 6. Pre-check findings

| Finding | Status after the round |
|---|---|
| PC-rope-01 | open with the family owner: the three entries are present; recounting their values on rg1 is not part of this post-check |
| PC-rope-02 | superseded by the post-check (PC6 = the round's compare; release-mode re-import byte-identical) |
| PC-rope-03 | resolved by the round: fresh strict validation of the regenerated tree, 0 failed and `results_differ` 0 (PC5) |
| PC-rope-04 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |
| PC-rope-05 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |
| PC-rope-06 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |
| PC-rope-07 | unchanged, disclosed: the fixture key by statement `agentdyn-suite-fixture-key`; the persona home paths need `benchmark-and-model-home-paths` to list rope (POST-adprov-v1-release-02) |

## 7. Post-check findings

| Id | Class | Severity | Security | Title | Verdict |
|---|---|---|---|---|---|


## 8. Readiness for sealing

**ready-with-caveats**: Every check passes (0 seal refusals; release-mode re-imports byte-identical, head 300/300 and rope-slice 90/90). Caveats before a deposit: release-scan triage (2 account ordinals, both AgentDyn suite personas; 156 `private-key` findings, all the AgentDyn fixture key of CC-02, statement `agentdyn-suite-fixture-key`; 136 `generic-api-key`, 36 sharing a token with the suite data) and the statement scope of POST-adprov-v1-release-02.

## 9. Reproduction

```bash
uv run python tools/precheck/run_postcheck.py --list --only rope
uv run python tools/precheck/postcheck_compare.py --corpus rope
```
