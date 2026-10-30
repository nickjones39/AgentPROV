# Post-check dossier: `ast-survey-agentharm-rg2`

## 1. Header

| | |
|---|---|
| Tree | `~/.agentprov/corpora/ast-survey-agentharm-rg2.partial` (working tree, read only) |
| Predecessor | `ast-survey-agentharm-rg1.partial` |
| Built at | `5fc39c16` (train 18 `785c6c28` + D-811 survey-agentharm@2 + a SEC-12 test change; the regeneration-plan session) |
| Pre-check corpus · parts | `ast-survey-agentharm` · `agentharm` |
| Post-check code | `33337b24` (stage code: PC0) |
| Data | [`data/ast-survey-agentharm-rg2/`](data/ast-survey-agentharm-rg2/) |

## 2. Checks

| Check | Result |
|---|---|
| PC1 raw (8.3.1) | objects 1,068, equal True; origins rows equal True (object-origin pairs True); member rows equal True |
| PC2 population | ids 1,056 common, only old 0, only new 0; completeness = round False; issue codes net {} (= round True); stage digests changed {'aer': 1056, 'prov': 1056, 'sem': 1056, 'validation': 0} |
| PC3 verify chain | exit 0, ok; executions_checked 1,056, raw_rehashed 1,068, failed 0; issues: `checksums.absent` 1 |
| PC4 recompute --dry-run --jobs 4 | exit 0, ok; identical 1,056, changed_explained 0, unexplained_change 0, failed 0, unverified 0; issues: none |
| PC5 validate --strict (aer,sem,prov,linkage) | exit 0, ok; passed 1,056, failed 0, checks_skipped 0, results_differ 0, linkage_resolved 1,056; issues: none |
| PC6 full population | executions 1,056 → 1,056; degenerate [0, 0], adapter_defect [0, 0]; SEM net = round True; 6 changed census leaves |
| PC8 outcomes | 0 arm × measure judgement counts, 0 moved |
| PC10 release-scan forecast | native 2,599, gitleaks 114 (section 4) |
| PC11 seal forecast | 0 refusal(s); 11 checks; 5 datasheet statements apply; withholding policy True |
| PC7 sample `agentharm` | 6/6 sampled labels found; pre-check scratch → rg2: 7 leaves |
| PC7b tie `agentharm` | 1,056/1,056 executions with every digest equal; differ by stage {}; stage code equal {'aer': True, 'expand': True, 'prov': True, 'sem': True, 'validation': True} |
| Dispatch census | 0 executions, 0 unexecuted parts; {} |

## 3. Movement and attribution

SEM annotations, rg1 → rg2 (net, by type and evidence class; the round's `compare.json` for the base corpus beside it):

| Type, class | Post-check | Round |
|---|---|---|
| (none) | 0 | 0 |

Level-2 census leaves that changed, rg1 → rg2 (6; by section {'withholding': 6}):

| Leaf | Old | New |
|---|---|---|
| `withholding.elapsed_s` | — | 5.3 |
| `withholding.executions_total` | — | 1,056 |
| `withholding.executions_withheld` | — | 0 |
| `withholding.objects_by_basis.container:personal_data` | — | 6 |
| `withholding.objects_by_basis.profile_rule:personal_data` | — | 6 |
| `withholding.objects_withheld` | — | 12 |

Sample `agentharm`: pre-check scratch (code `d97d3a57`) → rg2, per-execution leaves (6; the corpus-wide register codes and the file count differ by scope, R5):
- `withholding.elapsed_s` — → 5.3
- `withholding.executions_total` — → 1,056
- `withholding.executions_withheld` — → 0
- `withholding.objects_by_basis.container:personal_data` — → 6
- `withholding.objects_by_basis.profile_rule:personal_data` — → 6
- `withholding.objects_withheld` — → 12

Attribution:

- survey-agentharm@1 → @2 (D-811: kexin's `dataset-location-home` rule, object scope); AER header profile digest and version on every execution; SEM and PROV digests follow; validation unchanged.
- Value level: no census leaf other than the withholding plan changed (statements, evidence classes, A3, SEM); the post-check does not compare masked PROV statement values.

## 4. Release-scan forecast

| Scanner | Area : rule | Findings | Files |
|---|---|---|---|
| native path scan | aer:account-path | 2,064 | 246 |
| native path scan | prov:account-path | 198 | 198 |
| native path scan | raw-object:account-path | 337 | 258 |
| gitleaks 8.30.1 | aer:generic-api-key | 76 | |
| gitleaks 8.30.1 | prov:generic-api-key | 4 | |
| gitleaks 8.30.1 | raw-object:facebook-secret | 1 | |
| gitleaks 8.30.1 | raw-object:generic-api-key | 33 | |

Distinct account names (ordinals, never names): 20.

Triage against the benchmark suite data (in memory; `triage.json`, `triage-context.json`): the JSON member a match sits under and what follows the account segment (toolchain directory, user folder or other) are counts, never values:

| Ordinal | Length | Areas | Path in suite data | Name in suite data | JSON keys | Path tail |
|---|---|---|---|---|---|---|
| #1 | 30 | {'aer': 286, 'prov': 16, 'raw-object': 389} | True | True | {'(none)': 203, 'content': 82, 'image_path': 128, 'prompt': 72, 'replaced': 96, 'text': 31} | {'other': 691} |
| #2 | 9 | {'aer': 115, 'prov': 11, 'raw-object': 250} | False | True | {'(none)': 67, 'content': 151, 'file_path': 80, 'image_path': 8, 'result': 35, 'text': 35} | {'other': 376} |
| #3 | 20 | {'aer': 270, 'prov': 29, 'raw-object': 458} | False | False | {'(none)': 149, 'content': 156, 'image_path': 224, 'prompt': 36, 'replaced': 48, 'text': 48} | {'other': 757} |
| #4 | 27 | {'aer': 736, 'prov': 98, 'raw-object': 1269} | False | False | {'(none)': 657, 'base_img': 96, 'content': 278, 'image_path': 688, 'result': 121, 'text': 142} | {'other': 2022, 'user_dirs': 81} |
| #5 | 7 | {'aer': 1388, 'prov': 200, 'raw-object': 2356} | True | True | {'(none)': 1146, 'content': 457, 'mp3_path': 240, 'replaced': 192, 'video': 334, 'video_path': 808} | {'other': 3569, 'user_dirs': 375} |
| #6 | 20 | {'aer': 685, 'prov': 117, 'raw-object': 1213} | False | False | {'(none)': 590, 'attachments': 104, 'content': 203, 'image_path': 820, 'result': 97, 'text': 119} | {'other': 2015} |
| #7 | 23 | {'aer': 107, 'prov': 14, 'raw-object': 237} | False | False | {'(none)': 51, 'content': 128, 'file_path': 112, 'reasoning': 7, 'result': 27, 'text': 31} | {'other': 358} |
| #8 | 21 | {'aer': 250, 'prov': 31, 'raw-object': 398} | True | True | {'(none)': 181, 'content': 78, 'image_path': 240, 'prompt': 36, 'replaced': 48, 'text': 29} | {'other': 679} |
| #9 | 19 | {'aer': 5, 'prov': 1, 'raw-object': 9} | False | False | {'(none)': 7, 'image_path': 8} | {'other': 15} |
| #10 | 7 | {'aer': 23, 'prov': 2, 'raw-object': 33} | False | False | {'(none)': 39, 'command': 8, 'reasoning': 7, 'text': 4} | {'other': 53, 'user_dirs': 5} |
| #11 | 9 | {'aer': 8, 'prov': 3, 'raw-object': 20} | False | False | {'(none)': 9, 'mp3_path': 22} | {'other': 27, 'user_dirs': 4} |
| #12 | 11 | {'aer': 2, 'raw-object': 2} | False | False | {'(none)': 4} | {'other': 4} |
| #13 | 16 | {'aer': 10, 'prov': 2, 'raw-object': 23} | False | False | {'(none)': 7, 'content': 3, 'file_path': 12, 'reasoning': 5, 'result': 2, 'text': 5} | {'other': 35} |
| #14 | 25 | {'aer': 1, 'raw-object': 2} | False | False | {'(none)': 3} | {'other': 3} |
| #15 | 8 | {'aer': 3, 'prov': 1, 'raw-object': 7} | False | False | {'(none)': 3, 'base_img': 8} | {'other': 1, 'user_dirs': 10} |
| #16 | 26 | {'aer': 2, 'raw-object': 2} | False | False | {'a34d12be10aa0b2d36666daa851b5a6e': 1, 'reasoning': 2, 'text': 1} | {'other': 4} |
| #17 | 14 | {'aer': 2, 'raw-object': 2} | False | False | {'(none)': 4} | {'other': 4} |
| #18 | 9 | {'aer': 2, 'raw-object': 2} | False | False | {'(none)': 4} | {'other': 4} |
| #19 | 15 | {'aer': 5, 'prov': 1, 'raw-object': 12} | False | False | {'(none)': 3, 'content': 5, 'mp3_path': 8, 'result': 1, 'text': 1} | {'other': 14, 'user_dirs': 4} |
| #20 | 8 | {'raw-object': 6} | False | False | {'location': 6} | {'toolchain': 6} |

- The scan forecast runs on the working tree, which still holds the 12 withheld objects: ordinal #20's 6 raw-object findings leave with them at the seal (residue 0).
- The other 19 ordinals and the gitleaks findings are those of rg1 (benchmark or model content; triage needed before a deposit).

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
| origin:agentharm | pass |
| card_mode | pass |
| card_lint | pass |

Datasheet statements that apply: `art-n7-activity-times`, `art-text-tool-calls`, `benchmark-and-model-home-paths`, `implied-prov-inferences`, `redaction-labels-guessable`.

## 6. Pre-check findings

| Finding | Status after the round |
|---|---|
| PC-ast-survey-agentharm-01 | unchanged (a raw-level source defect, inspect_evals #2439); the disclosure stays open with the datasheet owner |
| PC-ast-survey-agentharm-02 | resolved: `inspect.art.abnormal_finish_max_tokens` and `inspect.art.text_tool_call` are in the Inspect catalogue |
| PC-ast-survey-agentharm-03 | open (documentation of the verify report); no data change |
| PC-ast-survey-agentharm-04 | unchanged (expected-known); the wording suggestion stays with the family owner |
| PC-ast-survey-agentharm-05 | n/a: a property of a pre-check tool (R5); the post-check measures do not depend on it |
| PC-ast-survey-agentharm-07 | resolved by the round: fresh strict validation of the regenerated tree, 0 failed and `results_differ` 0 (PC5) |

## 7. Post-check findings

| Id | Class | Severity | Security | Title | Verdict |
|---|---|---|---|---|---|


## 8. Readiness for sealing

**ready-with-caveats**: Every check passes at its building code: the seal forecast gives 0 refusals; the withholding plan withholds 12 objects (the 6 `header.json` members by `dataset-location-home`, their 6 `.eval` containers by closure) and 0 executions; the withheld account has 0 bare-name and 0 home-path hits in the 4,232 files outside them and no archive lies outside them (residue); the full-population census equals rg1's except the withholding plan; dry run 1,056 identical; validation 1,056 passed; release-mode re-import byte-identical 1,056/1,056. Caveats before a deposit: release-scan triage of the 19 benchmark or model ordinals and the 114 gitleaks findings (as rg1), and the PC-01 disclosure.

## 9. Reproduction

```bash
uv run python tools/precheck/run_postcheck.py --list --variant ast-survey-agentharm:rg2:rg1
uv run python tools/precheck/postcheck_compare.py --corpus ast-survey-agentharm-rg2 --variant ast-survey-agentharm:rg2:rg1
```
