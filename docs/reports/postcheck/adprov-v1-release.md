# Post-check dossier: `adprov-v1-release`

## 1. Header

| | |
|---|---|
| Tree | `~/.agentprov/corpora/adprov-v1-release-rg1.partial` (working tree, read only) |
| Predecessor | `adprov-v1-release-p10.pre-regen.partial` |
| Built at | `5b1f6fdf` (the round) |
| Pre-check corpus · parts | `adprov-v1` · `release` |
| Post-check code | `505fa46d`, `6d29418b`, `d9f86cc5` (stage code: PC0) |
| Data | [`data/adprov-v1-release/`](data/adprov-v1-release/) |

## 2. Checks

| Check | Result |
|---|---|
| PC1 raw (8.3.1) | objects 17,664, equal True; origins rows equal True (object-origin pairs True); member rows equal True |
| PC2 population | ids 17,664 common, only old 0, only new 0; completeness = round True; issue codes net {} (= round True); stage digests changed {'aer': 17664, 'prov': 17664, 'sem': 17664, 'validation': 17664} |
| PC3 verify chain | exit 0, ok; executions_checked 17,664, raw_rehashed 17,664, failed 0; issues: `checksums.absent` 1 |
| PC4 recompute --dry-run --jobs 4 | exit 0, ok; identical 17,664, changed_explained 0, unexplained_change 0, failed 0, unverified 0; issues: none |
| PC5 validate --strict (aer,sem,prov,linkage) | exit 0, ok; passed 17,664, failed 0, checks_skipped 0, results_differ 0, linkage_resolved 17,664; issues: none |
| PC6 full population | executions 17,664 → 17,664; degenerate [0, 0], adapter_defect [0, 0]; SEM net = round True; 16 changed census leaves |
| PC8 outcomes | 84 arm × measure judgement counts, 0 moved |
| PC10 release-scan forecast | native 14, gitleaks 4 (section 4) |
| PC11 seal forecast | 1 refusal(s); 11 checks; 14 datasheet statements apply; withholding policy False |
| PC7 sample `release` | 300/300 sampled labels found; pre-check scratch → rg1: 12 leaves |
| PC7b tie `release` | 300/300 executions with every digest equal; differ by stage {}; stage code equal {'aer': True, 'prov': True, 'sem': True, 'validation': True} |
| Dispatch census | 47 executions, 48 unexecuted parts; {'core|entity|apv:NotDispatched': 48} |

## 3. Movement and attribution

SEM annotations, p10 → rg1 (net, by type and evidence class; the round's `compare.json` for the base corpus beside it):

| Type, class | Post-check | Round |
|---|---|---|
| agentdojo.partial_payload D | 787 | 787 |

Level-2 census leaves that changed, p10 → rg1 (16; by section {'executions': 2, 'prov': 14}):

| Leaf | Old | New |
|---|---|---|
| `executions.stages.sem:agentdojo.suites@1:ok` | 17,664 | — |
| `executions.stages.sem:agentdojo.suites@2:ok` | — | 17,664 |
| `prov.checked.relation_arguments` | 8,379,694 | 12,477,819 |
| `prov.checked.statements` | 5,601,815 | 7,845,231 |
| `prov.evidence_by_bundle_class.assessment:D` | 106,090 | 106,877 |
| `prov.evidence_by_bundle_class.assessment:none` | 385,477 | 386,264 |
| `prov.evidence_by_bundle_class.core:D` | 1,172,390 | 269,166 |
| `prov.evidence_by_bundle_class.inference:I` | 1,209,210 | 2,571,273 |
| `prov.evidence_by_bundle_class.inference:none` | 17,664 | 296,773 |
| `prov.evidence_by_bundle_class.top:O` | 1,138,165 | 2,391,410 |
| `prov.evidence_by_bundle_class.top:none` | 121,649 | 372,298 |
| `prov.mixed_twin_and_native_by_bundle_class.inference:I` | — | 384,893 |
| `prov.native_unverified_rule_by_bundle_class.inference:I` | 419,470 | 34,577 |
| `prov.unverified_twin_by_bundle_class.assessment:I` | — | 35,328 |
| `prov.unverified_twin_by_bundle_class.inference:I` | — | 2,107,733 |
| `prov.unverified_twin_by_bundle_class.inference:none` | — | 279,109 |

Sample `release`: pre-check scratch (code `d97d3a57`) → rg1, per-execution leaves (6; the corpus-wide register codes and the file count differ by scope, R5):
- `prov.checked.relation_arguments` 204,191 → 211,049
- `prov.checked.statements` 128,166 → 132,738
- `prov.evidence_by_bundle_class.inference:I` 42,125 → 44,411
- `prov.evidence_by_bundle_class.inference:none` 2,891 → 5,177
- `prov.unverified_twin_by_bundle_class.inference:I` 34,539 → 36,825
- `prov.unverified_twin_by_bundle_class.inference:none` 2,591 → 4,877

Attribution:

- SEM partial_payload D +787 (item 6, the `partial` injection-marker status).
- `apv:dispatchStatus apv:NotDispatched` stays in the core bundle for all 48 unexecuted parts: this harness code is verified, so the unexecuted rule stays D (dispatch census).
- Inference-bundle twin statements grew between the pre-check scratch import (`d97d3a57`) and the round (`5b1f6fdf`): equal I and unclassed increments in the inference bundles, the same kind in every AgentDojo-family part. Engine and catalogue items landed in that window (D-621 #15-#26, part C, regeneration items 105-167); the round's closed-world compare covers them. The post-check confirms the kind and the determinism (dry run identical, validation clean, release-mode re-import byte-identical), not a per-item split: the pre-check scratch trees no longer exist.

## 4. Release-scan forecast

| Scanner | Area : rule | Findings | Files |
|---|---|---|---|
| native path scan | aer:account-path | 6 | 2 |
| native path scan | prov:account-path | 2 | 2 |
| native path scan | raw-object:account-path | 6 | 2 |
| gitleaks 8.30.1 | aer:generic-api-key | 2 | |
| gitleaks 8.30.1 | raw-object:generic-api-key | 2 | |

Distinct account names (ordinals, never names): 1.


## 5. Seal forecast

| Check | Result |
|---|---|
| working | pass |
| shard_depth | pass |
| changelog | pass |
| profile_version | pass |
| profile_digest | pass |
| context | pass |
| stages | refused — `package.refused.stages`: an execution lacks a spec'd PROV or validation stage |
| licences | pass |
| origin:release | pass |
| card_mode | pass |
| card_lint | pass |

Datasheet statements that apply: `adprov-release-writer`, `art-benign-security-constant`, `art-iteration-cap-cut`, `art-n2-escaped-newlines`, `art-n5-dropped-high-bytes`, `art-n6-completeness-model-confounded`, `art-n7-activity-times`, `art-n8-argument-types`, `art-payload-never-reached`, `art-silent-rerun`, `art-text-tool-calls`, `art-vacuous-utility`, `implied-prov-inferences`, `redaction-labels-guessable`.

## 6. Pre-check findings

| Finding | Status after the round |
|---|---|

## 7. Post-check findings

| Id | Class | Severity | Security | Title | Verdict |
|---|---|---|---|---|---|
| POST-adprov-v1-release-01 | documentation-mismatch | S2 | False | The corpus spec requires the regression-oracle PROV, which no import produces | confirmed |

- **POST-adprov-v1-release-01**: `corpora/adprov-v1-release/corpus-spec.toml` (since df67f9ac, phase 11, 2026-10-11) has `prov_specs = ["agentprov-prov/0.1", "adprov-v2.3-compat"]`; every execution of rg1 (and of p10) has only `agentprov-prov/0.1`; the round driver ran no `derive --prov-spec adprov-v2.3-compat`. The seal forecast refuses `stages`. Recommendation: Done: user decision (a), `adprov-v1-release-rg2` derived at 5b1f6fdf; post-checked (pass). For the next re-import, `tools/regen/round/run_round.sh` (or the regen plan) needs the step `agentprov derive --prov-spec adprov-v2.3-compat` after the import (`import` defers the compat spec). S2, not R4's S3 default, because it blocked the seal.

## 8. Readiness for sealing

**never seal**: Superseded: `package` refuses it (`package.refused.stages`): the corpus spec names `adprov-v2.3-compat`, which no execution has (POST-adprov-v1-release-01). The user chose (a), a derive with the compat spec: `adprov-v1-release-rg2`. Every other check passed.

## 9. Reproduction

```bash
uv run python tools/precheck/run_postcheck.py --list --only adprov-v1-release
uv run python tools/precheck/postcheck_compare.py --corpus adprov-v1-release
```
