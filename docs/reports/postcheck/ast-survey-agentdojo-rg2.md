# Post-check dossier: `ast-survey-agentdojo-rg2`

## 1. Header

| | |
|---|---|
| Tree | `~/.agentprov/corpora/ast-survey-agentdojo-rg2.partial` (working tree, read only) |
| Predecessor | `ast-survey-agentdojo-rg1.partial` |
| Built at | `d93aa261` (main, train 10; D-771 re-import by the regeneration-plan session) |
| Pre-check corpus · parts | `ast-survey-agentdojo` · `agentdojo-runs` |
| Post-check code | `d9f86cc5` (stage code: PC0) |
| Data | [`data/ast-survey-agentdojo-rg2/`](data/ast-survey-agentdojo-rg2/) |

## 2. Checks

| Check | Result |
|---|---|
| PC1 raw (8.3.1) | objects 3,253, equal True; origins rows equal True (object-origin pairs True); member rows equal True |
| PC2 population | ids 3,243 common, only old 0, only new 0; completeness = round True; issue codes net {} (= round True); stage digests changed {'aer': 3243, 'prov': 3243, 'sem': 3243, 'validation': 0} |
| PC3 verify chain | exit 0, ok; executions_checked 3,243, raw_rehashed 3,253, failed 0; issues: `checksums.absent` 1 |
| PC4 recompute --dry-run --jobs 4 | exit 0, ok; identical 3,243, changed_explained 0, unexplained_change 0, failed 0, unverified 0; issues: none |
| PC5 validate --strict (aer,sem,prov,linkage) | exit 0, ok; passed 3,243, failed 0, checks_skipped 0, results_differ 0, linkage_resolved 3,243; issues: none |
| PC6 full population | executions 3,243 → 3,243; degenerate [0, 0], adapter_defect [0, 0]; SEM net = round False; 5 changed census leaves |
| PC8 outcomes | 18 arm × measure judgement counts, 0 moved |
| PC10 release-scan forecast | native 58, gitleaks 0 (section 4) |
| PC11 seal forecast | 0 refusal(s); 11 checks; 15 datasheet statements apply; withholding policy True |
| PC7 sample `agentdojo-runs` | 120/120 sampled labels found; pre-check scratch → rg2: 23 leaves |
| PC7b tie `agentdojo-runs` | 120/120 executions with every digest equal; differ by stage {}; stage code equal {'aer': False, 'prov': True, 'sem': True, 'validation': True} |
| Dispatch census | 48 executions, 49 unexecuted parts; {'inf|entity|apv:NotDispatched': 49} |

## 3. Movement and attribution

SEM annotations, rg1 → rg2 (net, by type and evidence class; the round's `compare.json` for the base corpus beside it):

| Type, class | Post-check | Round |
|---|---|---|
| agentdojo.partial_payload D | — | 156 |
| injection_marker D | — | -18,368 |
| injection_marker I | — | 18,368 |
| outcome D | — | -6,069 |
| outcome I | — | 6,069 |

Level-2 census leaves that changed, rg1 → rg2 (5; by section {'withholding': 5}):

| Leaf | Old | New |
|---|---|---|
| `withholding.elapsed_s` | — | 2.6 |
| `withholding.executions_total` | — | 3,243 |
| `withholding.executions_withheld` | — | 0 |
| `withholding.objects_by_basis.profile_rule:personal_data` | — | 5 |
| `withholding.objects_withheld` | — | 5 |

Sample `agentdojo-runs`: pre-check scratch (code `d97d3a57`) → rg2, per-execution leaves (18; the corpus-wide register codes and the file count differ by scope, R5):
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
- `withholding.elapsed_s` — → 0.9
- `withholding.executions_total` — → 120
- `withholding.executions_withheld` — → 0
- `withholding.objects_by_basis.profile_rule:personal_data` — → 5
- `withholding.objects_withheld` — → 5

Attribution:

- survey-runs@2 → @3 (D-771: the `[withhold]` table `console-home-account-path`); AER header profile digest and version change on every execution.
- Value level: no census leaf other than the withholding plan changed (statements, evidence classes, A3, SEM, outcomes); the post-check does not compare masked PROV statement values.
- Stage code: aer adapter and engine and prov engine digests moved (d93aa261: regeneration item 165, the defence rules, `session.py`); sem and validation unchanged.

## 4. Release-scan forecast

| Scanner | Area : rule | Findings | Files |
|---|---|---|---|
| native path scan | raw-object:account-path | 58 | 5 |

Distinct account names (ordinals, never names): 1.

Triage against the benchmark suite data (in memory; `triage.json`, `triage-context.json`): the JSON member a match sits under and what follows the account segment (toolchain directory, user folder or other) are counts, never values:

| Ordinal | Length | Areas | Path in suite data | Name in suite data | JSON keys | Path tail |
|---|---|---|---|---|---|---|
| #1 | 8 | {'raw-object': 58} | False | False | — | — |

- The withholding plan (survey-runs@3) withholds 2b736e23f895, 827662f31d68, 979bdc64963c, bc1bc47b0262 and d269cdc4106e: exactly the 5 raw objects with the 58 `account-path` findings.
- The sample tie's `stage_code_equal.aer` is false only because main moved the aer engine digest after `d93aa261` (class-1 live-part registry caveats, D-720/D-722/D-729/D-744); all 120 executions are byte-identical.
- The register's out-of-pin rows (6 `select.owned_elsewhere`, 4 `select.dialect_planned` in p10) are absent, as in rg1: POST-agentdyn-a-01.

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
| origin:agentdojo-runs | pass |
| card_mode | pass |
| card_lint | pass |

Datasheet statements that apply: `art-benign-security-constant`, `art-empty-assistant-text`, `art-identical-trajectories`, `art-iteration-cap-cut`, `art-n2-escaped-newlines`, `art-n4-empty-final-replies`, `art-n7-activity-times`, `art-payload-never-reached`, `art-run-error-imposed`, `art-survey-security-gloss`, `art-text-tool-calls`, `art-vacuous-utility`, `core-only-consumers`, `implied-prov-inferences`, `redaction-labels-guessable`.

## 6. Pre-check findings

| Finding | Status after the round |
|---|---|
| PC-ast-survey-agentdojo-02 | unchanged, as expected: a source-documentation or paper-vs-log item about raw-level outcomes; PC8 finds 0 outcome values moved; the disclosure stays with the datasheet and manuscript owner |
| PC-ast-survey-agentdojo-03 | unchanged, as expected: a source-documentation or paper-vs-log item about raw-level outcomes; PC8 finds 0 outcome values moved; the disclosure stays with the datasheet and manuscript owner |
| PC-ast-survey-agentdojo-04 | data unchanged (a raw-level checker defect, catalogued); the catalogue part is fixed: `agentdojo.art.validity_defects` now scopes this profile (CC-07, CC-09) |
| PC-ast-survey-agentdojo-05 | open (CC-04, documentation of U6-c); the engine still records `apv:paramsStatus` |
| PC-ast-survey-agentdojo-06 | moved as predicted (item 3 / D-80): SEM outcome D→I 6,069 and injection markers D→I 18,368 at full population, equal to the round's compare |
| PC-ast-survey-agentdojo-07 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |
| PC-ast-survey-agentdojo-08 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |
| PC-ast-survey-agentdojo-09 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |
| PC-ast-survey-agentdojo-10 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |
| PC-ast-survey-agentdojo-11 | resolved by the round: fresh strict validation of the regenerated tree, 0 failed and `results_differ` 0 (PC5) |
| PC-ast-survey-agentdojo-12 | resolved in scope (`validity_defects` scopes `survey-runs`); the expected row's content is not re-verified here |
| PC-ast-survey-agentdojo-13 | fixed by D-771: survey-runs@3 withholds the 5 console logs at seal (see section 4) |

## 7. Post-check findings

| Id | Class | Severity | Security | Title | Verdict |
|---|---|---|---|---|---|


## 8. Readiness for sealing

**ready**: Every check passes at its building code (`d93aa261`, a merge of main at the post-check): the seal forecast gives 0 refusals; the full-population census equals rg1's except the new withholding plan; the plan withholds exactly the 5 console logs that hold every one of the 58 account-path findings (0 executions), so the release-scan forecast has no residue after the seal; gitleaks finds nothing; dry run 3,243 identical; release-mode re-import byte-identical 120/120.

## 9. Reproduction

```bash
uv run python tools/precheck/run_postcheck.py --list --variant ast-survey-agentdojo:rg2:rg1
uv run python tools/precheck/postcheck_compare.py --corpus ast-survey-agentdojo-rg2 --variant ast-survey-agentdojo:rg2:rg1
```
