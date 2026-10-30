# Post-check dossier: `mandate-agentdojo-eval`

## 1. Header

| | |
|---|---|
| Tree | `~/.agentprov/corpora/mandate-agentdojo-eval-rg1.partial` (working tree, read only) |
| Predecessor | `mandate-agentdojo-eval-p10.pre-regen.partial` |
| Built at | `5b1f6fdf` (the round) |
| Pre-check corpus · parts | `mandate-agentdojo-eval` · `head` |
| Post-check code | `505fa46d`, `7fedec72`, `c1cf3bfc`, `d9f86cc5` (stage code: PC0) |
| Data | [`data/mandate-agentdojo-eval/`](data/mandate-agentdojo-eval/) |

## 2. Checks

| Check | Result |
|---|---|
| PC1 raw (8.3.1) | objects 400, equal True; origins rows equal True (object-origin pairs True); member rows equal True |
| PC2 population | ids 396 common, only old 0, only new 0; completeness = round True; issue codes net {} (= round True); stage digests changed {'aer': 396, 'prov': 396, 'sem': 396, 'validation': 396} |
| PC3 verify chain | exit 0, ok; executions_checked 396, raw_rehashed 400, failed 0; issues: `checksums.absent` 1 |
| PC4 recompute --dry-run --jobs 4 | exit 0, ok; identical 396, changed_explained 0, unexplained_change 0, failed 0, unverified 0; issues: none |
| PC5 validate --strict (aer,sem,prov,linkage) | exit 0, ok; passed 396, failed 0, checks_skipped 0, results_differ 0, linkage_resolved 396; issues: none |
| PC6 full population | executions 396 → 396; degenerate [0, 0], adapter_defect [0, 0]; SEM net = round True; 16 changed census leaves |
| PC8 outcomes | 23 arm × measure judgement counts, 0 moved |
| PC10 release-scan forecast | native 0, gitleaks 0 (section 4) |
| PC11 seal forecast | 0 refusal(s); 11 checks; 7 datasheet statements apply; withholding policy False |
| PC7 sample `head` | 40/40 sampled labels found; pre-check scratch → rg1: 3 leaves |
| PC7b tie `head` | 40/40 executions with every digest equal; differ by stage {}; stage code equal {'aer': True, 'prov': True, 'sem': True, 'validation': True} |
| Dispatch census | 0 executions, 0 unexecuted parts; {} |

## 3. Movement and attribution

SEM annotations, p10 → rg1 (net, by type and evidence class; the round's `compare.json` for the base corpus beside it):

| Type, class | Post-check | Round |
|---|---|---|
| outcome D | -369 | -369 |
| outcome I | 369 | 369 |

Outcome annotations by log variant: outcome D v1.k14 -369, outcome I v1.k14 369.

Level-2 census leaves that changed, p10 → rg1 (16; by section {'executions': 2, 'prov': 14}):

| Leaf | Old | New |
|---|---|---|
| `executions.stages.sem:agentdojo.suites@1:ok` | 396 | — |
| `executions.stages.sem:agentdojo.suites@2:ok` | — | 396 |
| `prov.checked.relation_arguments` | 184,838 | 299,263 |
| `prov.checked.statements` | 124,180 | 180,363 |
| `prov.evidence_by_bundle_class.assessment:D` | 1,487 | 1,118 |
| `prov.evidence_by_bundle_class.assessment:I` | 14,453 | 14,822 |
| `prov.evidence_by_bundle_class.core:D` | 27,772 | 4,047 |
| `prov.evidence_by_bundle_class.inference:I` | 28,217 | 57,404 |
| `prov.evidence_by_bundle_class.inference:none` | 396 | 4,751 |
| `prov.evidence_by_bundle_class.top:O` | 27,463 | 66,677 |
| `prov.evidence_by_bundle_class.top:none` | 2,740 | 9,892 |
| `prov.mixed_twin_and_native_by_bundle_class.inference:I` | — | 8,911 |
| `prov.native_unverified_rule_by_bundle_class.inference:I` | 8,911 | — |
| `prov.unverified_twin_by_bundle_class.assessment:I` | — | 6,676 |
| `prov.unverified_twin_by_bundle_class.inference:I` | — | 46,840 |
| `prov.unverified_twin_by_bundle_class.inference:none` | — | 4,355 |

Sample `head`: pre-check scratch (code `d97d3a57`) → rg1, per-execution leaves (0; the corpus-wide register codes and the file count differ by scope, R5):
- none

Attribution:

- SEM profile `agentdojo.suites@1` → `@2` (D-31 bump, item 1); every execution's SEM stage is renamed.
- Outcome annotations D→I 369, all v1.k14: D-359 (premise propagation through `checker_outcome`; user decision, option A, docs only).
- Inference-bundle twin statements grew between the pre-check scratch import (`d97d3a57`) and the round (`5b1f6fdf`): equal I and unclassed increments in the inference bundles, the same kind in every AgentDojo-family part. Engine and catalogue items landed in that window (D-621 #15-#26, part C, regeneration items 105-167); the round's closed-world compare covers them. The post-check confirms the kind and the determinism (dry run identical, validation clean, release-mode re-import byte-identical), not a per-item split: the pre-check scratch trees no longer exist.

## 4. Release-scan forecast

| Scanner | Area : rule | Findings | Files |
|---|---|---|---|
| both | — | 0 | 0 |

Distinct account names (ordinals, never names): 0.

- Nothing to triage.

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

Datasheet statements that apply: `art-benign-security-constant`, `art-defences-in-benign-runs`, `art-mandate-allows-inferred`, `art-n7-activity-times`, `art-payload-never-reached`, `implied-prov-inferences`, `redaction-labels-guessable`.

## 6. Pre-check findings

| Finding | Status after the round |
|---|---|
| PC-mandate-agentdojo-eval-01 | data unchanged (a raw-level checker defect, catalogued); the catalogue part is fixed: `agentdojo.art.validity_defects` now scopes this profile (CC-07, CC-09) |
| PC-mandate-agentdojo-eval-02 | data unchanged (a raw-level checker defect, catalogued); the catalogue part is fixed: `agentdojo.art.validity_defects` now scopes this profile (CC-07, CC-09) |
| PC-mandate-agentdojo-eval-03 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |
| PC-mandate-agentdojo-eval-04 | decided (D-359, option A, docs only); numbers confirmed: outcome D→I 369, all v1.k14 (PC6 SEM census = the round's compare) |
| PC-mandate-agentdojo-eval-05 | open with the family owner (documentation); the round changes no data here |
| PC-mandate-agentdojo-eval-08 | superseded by the post-check: SEM net = the round's compare; the sample from the pre-check scratch to rg1 has 0 per-execution leaves changed |
| PC-mandate-agentdojo-eval-09 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |
| PC-mandate-agentdojo-eval-10 | resolved by the round: fresh strict validation of the regenerated tree, 0 failed and `results_differ` 0 (PC5) |
| PC-mandate-agentdojo-eval-11 | resolved: `agentdojo.art.validity_defects` scopes `mandate-agentdojo-eval` |

## 7. Post-check findings

| Id | Class | Severity | Security | Title | Verdict |
|---|---|---|---|---|---|


## 8. Readiness for sealing

**ready**: Every check passes; the release-scan forecast is empty (0 native, 0 gitleaks findings); the seal forecast gives 0 refusals; the decided D-359 count (outcome D→I 369, v1.k14) is confirmed.

## 9. Reproduction

```bash
uv run python tools/precheck/run_postcheck.py --list --only mandate-agentdojo-eval
uv run python tools/precheck/postcheck_compare.py --corpus mandate-agentdojo-eval
```
