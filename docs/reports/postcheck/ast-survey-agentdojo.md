# Post-check dossier: `ast-survey-agentdojo`

## 1. Header

| | |
|---|---|
| Tree | `~/.agentprov/corpora/ast-survey-agentdojo-rg1.partial` (working tree, read only) |
| Predecessor | `ast-survey-agentdojo-p10.pre-regen.partial` |
| Built at | `5b1f6fdf` (the round) |
| Pre-check corpus · parts | `ast-survey-agentdojo` · `agentdojo-runs` |
| Post-check code | `505fa46d`, `64afde6b`, `6d29418b`, `7fedec72`, `d9f86cc5` (stage code: PC0) |
| Data | [`data/ast-survey-agentdojo/`](data/ast-survey-agentdojo/) |

## 2. Checks

| Check | Result |
|---|---|
| PC1 raw (8.3.1) | objects 3,253, equal True; origins rows equal True (object-origin pairs True); member rows equal True |
| PC2 population | ids 3,243 common, only old 0, only new 0; completeness = round True; issue codes net {} (= round True); stage digests changed {'aer': 3243, 'prov': 3243, 'sem': 3243, 'validation': 3243} |
| PC3 verify chain | exit 0, ok; executions_checked 3,243, raw_rehashed 3,253, failed 0; issues: `checksums.absent` 1 |
| PC4 recompute --dry-run --jobs 4 | exit 0, ok; identical 3,243, changed_explained 0, unexplained_change 0, failed 0, unverified 0; issues: none |
| PC5 validate --strict (aer,sem,prov,linkage) | exit 0, ok; passed 3,243, failed 0, checks_skipped 0, results_differ 0, linkage_resolved 3,243; issues: none |
| PC6 full population | executions 3,243 → 3,243; degenerate [0, 0], adapter_defect [0, 0]; SEM net = round True; 24 changed census leaves |
| PC8 outcomes | 18 arm × measure judgement counts, 0 moved |
| PC10 release-scan forecast | native 58, gitleaks 0 (section 4) |
| PC11 seal forecast | 2 refusal(s); 10 checks; 15 datasheet statements apply; withholding policy True |
| PC7 sample `agentdojo-runs` | 120/120 sampled labels found; pre-check scratch → rg1: 18 leaves |
| PC7b tie `agentdojo-runs` | 0/120 executions with every digest equal; differ by stage {'validation': 120}; stage code equal {'aer': True, 'prov': True, 'sem': True, 'validation': True} |
| Dispatch census | 48 executions, 49 unexecuted parts; {'inf|entity|apv:NotDispatched': 49} |

## 3. Movement and attribution

SEM annotations, p10 → rg1 (net, by type and evidence class; the round's `compare.json` for the base corpus beside it):

| Type, class | Post-check | Round |
|---|---|---|
| agentdojo.partial_payload D | 156 | 156 |
| injection_marker D | -18,368 | -18,368 |
| injection_marker I | 18,368 | 18,368 |
| outcome D | -6,069 | -6,069 |
| outcome I | 6,069 | 6,069 |

Outcome annotations by log variant: outcome D v1.k14 -6,069, outcome I v1.k14 6,069.

Level-2 census leaves that changed, p10 → rg1 (24; by section {'executions': 4, 'prov': 20}):

| Leaf | Old | New |
|---|---|---|
| `executions.register_codes.select.dialect_planned` | 4 | — |
| `executions.register_codes.select.owned_elsewhere` | 6 | — |
| `executions.stages.sem:agentdojo.suites@1:ok` | 3,243 | — |
| `executions.stages.sem:agentdojo.suites@2:ok` | — | 3,243 |
| `prov.a3.unexecuted_missing.by.None` | — | 49 |
| `prov.a3.unexecuted_missing.count` | — | 49 |
| `prov.a3.unexecuted_missing.executions` | — | 48 |
| `prov.a3.unexecuted_represented.count` | 49 | — |
| `prov.a3.unexecuted_represented.executions` | 0 | — |
| `prov.checked.relation_arguments` | 2,014,843 | 2,771,438 |
| `prov.checked.statements` | 1,279,251 | 1,657,228 |
| `prov.evidence_by_bundle_class.assessment:D` | 17,335 | 156 |
| `prov.evidence_by_bundle_class.assessment:I` | 138,899 | 156,234 |
| `prov.evidence_by_bundle_class.assessment:none` | 69,040 | 69,196 |
| `prov.evidence_by_bundle_class.core:D` | 73,316 | 15,798 |
| `prov.evidence_by_bundle_class.inference:I` | 458,885 | 567,576 |
| `prov.evidence_by_bundle_class.inference:none` | 31,344 | 72,422 |
| `prov.evidence_by_bundle_class.top:O` | 331,640 | 569,485 |
| `prov.evidence_by_bundle_class.top:none` | 46,870 | 94,439 |
| `prov.mixed_twin_and_native_by_bundle_class.inference:I` | 48,006 | 75,196 |
| `prov.native_unverified_rule_by_bundle_class.inference:I` | 27,190 | — |
| `prov.unverified_twin_by_bundle_class.assessment:I` | 22,474 | 73,494 |
| `prov.unverified_twin_by_bundle_class.inference:I` | 372,758 | 484,714 |
| `prov.unverified_twin_by_bundle_class.inference:none` | 28,079 | 69,157 |

Sample `agentdojo-runs`: pre-check scratch (code `d97d3a57`) → rg1, per-execution leaves (13; the corpus-wide register codes and the file count differ by scope, R5):
- `prov.a3.unexecuted_missing.by.None` — → 1
- `prov.a3.unexecuted_missing.count` — → 1
- `prov.a3.unexecuted_missing.executions` — → 1
- `prov.a3.unexecuted_represented.count` 1 → —
- `prov.a3.unexecuted_represented.executions` 0 → —
- `prov.checked.relation_arguments` 97,783 → 101,396
- `prov.checked.statements` 57,840 → 60,246
- `prov.evidence_by_bundle_class.inference:I` 19,672 → 20,872
- `prov.evidence_by_bundle_class.inference:none` 1,559 → 2,759
- `prov.evidence_by_bundle_class.top:O` 21,045 → 21,050
- `prov.evidence_by_bundle_class.top:none` 3,489 → 3,490
- `prov.unverified_twin_by_bundle_class.inference:I` 16,897 → 18,097
- `prov.unverified_twin_by_bundle_class.inference:none` 1,439 → 2,639

Attribution:

- SEM profile `agentdojo.suites@1` → `@2` (D-31 bump, item 1); every execution's SEM stage is renamed.
- SEM outcome and injection-marker annotations move D to I by item 3 / D-24 / D-80: the SEM rules' `_unverified` twins on unverified-harness code (`verified_code = []`). The pre-check's stored-vs-fresh tables attributed the same move on the samples.
- `apv:dispatchStatus apv:NotDispatched` moved from the core bundle to an inference-bundle mention for 49 of 49 unexecuted parts (D-80 addendum (d), 2026-10-15, regeneration-batch item 103: the TraceLogger and DRIFT builds cite the resolved rule, the `_unverified` twin under `verified_code = []`; the issue is a PROV premise since item 24). `l2_check`'s A3 `unexecuted` class reads the core element only and reports the moved parts as `unexecuted_missing`: a tool property (POST-tool-01), not a loss.
- Inference-bundle twin statements grew between the pre-check scratch import (`d97d3a57`) and the round (`5b1f6fdf`): equal I and unclassed increments in the inference bundles, the same kind in every AgentDojo-family part. Engine and catalogue items landed in that window (D-621 #15-#26, part C, regeneration items 105-167); the round's closed-world compare covers them. The post-check confirms the kind and the determinism (dry run identical, validation clean, release-mode re-import byte-identical), not a per-item split: the pre-check scratch trees no longer exist.

## 4. Release-scan forecast

| Scanner | Area : rule | Findings | Files |
|---|---|---|---|
| native path scan | raw-object:account-path | 58 | 5 |

Distinct account names (ordinals, never names): 1.

- 58 `account-path` findings, all in the 5 console-log raw objects (2b736e23f895 ×25, bc1bc47b0262 ×28, 979bdc64963c ×2, d269cdc4106e ×2, 827662f31d68 ×1); 0 in derived records; gitleaks 0.

## 5. Seal forecast

| Check | Result |
|---|---|
| working | refused — `package.refused.spec`: the spec's source or profile differs from the working corpus's |
| shard_depth | pass |
| changelog | pass |
| profile_version | pass |
| profile_digest | fail |
| stages | pass |
| licences | pass |
| origin:agentdojo-runs | pass |
| card_mode | pass |
| card_lint | pass |

Datasheet statements that apply: `art-benign-security-constant`, `art-empty-assistant-text`, `art-identical-trajectories`, `art-iteration-cap-cut`, `art-n2-escaped-newlines`, `art-n4-empty-final-replies`, `art-n7-activity-times`, `art-payload-never-reached`, `art-run-error-imposed`, `art-survey-security-gloss`, `art-text-tool-calls`, `art-vacuous-utility`, `core-only-consumers`, `implied-prov-inferences`, `redaction-labels-guessable`.

## 6. Pre-check findings

| Finding | Status after the round |
|---|---|
| PC-ast-survey-agentdojo-13 | confirmed in rg1 (5 raw console logs, 58 matches, 1 account); fixed by D-771 (survey-runs@3 withhold; user decision (a)); see `ast-survey-agentdojo-rg2` |

## 7. Post-check findings

| Id | Class | Severity | Security | Title | Verdict |
|---|---|---|---|---|---|


## 8. Readiness for sealing

**never seal**: Superseded: it records survey-runs@2, which has no withholding policy, so a seal would ship the 5 console logs with a named account (PC-ast-survey-agentdojo-13, confirmed: 5 raw objects, 58 matches, ordinal #1). The user chose a withhold rule (D-771); the tree to seal is `ast-survey-agentdojo-rg2`. At today's spec (survey-runs@3) the seal forecast refuses rg1 (`package.refused.spec`, profile digest). Every other check passed.

## 9. Reproduction

```bash
uv run python tools/precheck/run_postcheck.py --list --only ast-survey-agentdojo
uv run python tools/precheck/postcheck_compare.py --corpus ast-survey-agentdojo
```
