# Post-check dossier: `ast-survey-agentharm`

## 1. Header

| | |
|---|---|
| Tree | `~/.agentprov/corpora/ast-survey-agentharm-rg1.partial` (working tree, read only) |
| Predecessor | `ast-survey-agentharm-p10.pre-regen.partial` |
| Built at | `5b1f6fdf` (the round) |
| Pre-check corpus · parts | `ast-survey-agentharm` · `agentharm` |
| Post-check code | `2a4c2f8c`, `505fa46d`, `7fedec72`, `c1cf3bfc`, `d9f86cc5` (stage code: PC0) |
| Data | [`data/ast-survey-agentharm/`](data/ast-survey-agentharm/) |

## 2. Checks

| Check | Result |
|---|---|
| PC1 raw (8.3.1) | objects 1,068, equal True; origins rows equal True (object-origin pairs True); member rows equal False |
| PC2 population | ids 1,056 common, only old 0, only new 0; completeness = round True; issue codes net {} (= round True); stage digests changed {'aer': 1056, 'prov': 1056, 'sem': 1056, 'validation': 1056} |
| PC3 verify chain | exit 0, ok; executions_checked 1,056, raw_rehashed 1,068, failed 0; issues: `checksums.absent` 1 |
| PC4 recompute --dry-run --jobs 4 | exit 0, ok; identical 1,056, changed_explained 0, unexplained_change 0, failed 0, unverified 0; issues: none |
| PC5 validate --strict (aer,sem,prov,linkage) | exit 0, ok; passed 1,056, failed 0, checks_skipped 0, results_differ 0, linkage_resolved 1,056; issues: none |
| PC6 full population | executions 1,056 → 1,056; degenerate [0, 0], adapter_defect [0, 0]; SEM net = round True; 10 changed census leaves |
| PC8 outcomes | 0 arm × measure judgement counts, 0 moved |
| PC10 release-scan forecast | native 2,599, gitleaks 114 (section 4) |
| PC11 seal forecast | 0 refusal(s); 11 checks; 5 datasheet statements apply; withholding policy False |
| PC7 sample `agentharm` | 6/6 sampled labels found; pre-check scratch → rg1: 1 leaves |
| PC7b tie `agentharm` | 1,056/1,056 executions with every digest equal; differ by stage {}; stage code equal {'aer': True, 'expand': True, 'prov': True, 'sem': True, 'validation': True} |
| Dispatch census | 0 executions, 0 unexecuted parts; {} |

## 3. Movement and attribution

SEM annotations, p10 → rg1 (net, by type and evidence class; the round's `compare.json` for the base corpus beside it):

| Type, class | Post-check | Round |
|---|---|---|
| (none) | 0 | 0 |

Level-2 census leaves that changed, p10 → rg1 (10; by section {'executions': 4, 'prov': 6}):

| Leaf | Old | New |
|---|---|---|
| `executions.counts.completeness:known_incomplete` | — | 4 |
| `executions.counts.completeness:verified_complete` | 1,056 | 1,052 |
| `executions.stages.sem:inspect.agentharm@1:ok` | 1,056 | — |
| `executions.stages.sem:inspect.agentharm@2:ok` | — | 1,056 |
| `prov.checked.relation_arguments` | 424,112 | 468,344 |
| `prov.checked.statements` | 345,858 | 366,830 |
| `prov.evidence_by_bundle_class.core:D` | 116,119 | 126,531 |
| `prov.evidence_by_bundle_class.inference:I` | — | 1,056 |
| `prov.evidence_by_bundle_class.top:O` | 45,408 | 53,856 |
| `prov.evidence_by_bundle_class.top:none` | 2,112 | 3,168 |

Sample `agentharm`: pre-check scratch (code `d97d3a57`) → rg1, per-execution leaves (0; the corpus-wide register codes and the file count differ by scope, R5):
- none

Attribution:

- SEM profile `inspect.agentharm@1` → `@2` (D-31).
- Completeness verified_complete → known_incomplete 4 (item 11; the round's table).
- Raw member rows: only the expand `fn_digest` changed on all 1,691 rows (D-451/BF-39, CB-22); container, label, digest, size and CRC equal.
- PROV: inference I +1,056 (one per execution) and statement counts up; no per-execution leaf changed on the sample from the pre-check scratch.

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

Other rules, by whether the finding's line shares a 16+ character token (or a private-key header) with the suite data: aer:generic-api-key:in_suite_data 6, aer:generic-api-key:not_in_suite_data 70, prov:generic-api-key:not_in_suite_data 4, raw-object:facebook-secret:in_suite_data 1, raw-object:generic-api-key:in_suite_data 33.

- Account paths: 20 ordinals. 19 are benchmark or model content (tool-argument keys `image_path`, `video_path`, `file_path`, `mp3_path`, `base_img`, message `content`, AgentHarm prompts), in AER and PROV as well as raw, as the bug pass's /home/ triage classified (synthetic-benchmark or false-positive); statement `benchmark-and-model-home-paths` covers the derived records. The statement counts 18 names; this scan finds 19 such ordinals (it also matches `/Users/`, escaped and Windows forms): the difference is not reconciled here.
- Ordinal #20 is not: see POST-ast-survey-agentharm-01.
- gitleaks: 113 `generic-api-key` (39 lines share a token with the AgentHarm prompts; 74 do not) and 1 `facebook-secret` (in the prompts): every one needs a release-scan triage entry before a deposit.

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

## 7. Post-check findings

| Id | Class | Severity | Security | Title | Verdict |
|---|---|---|---|---|---|
| POST-ast-survey-agentharm-01 | source-defect | S2 | True | Raw `.eval` headers name a third-party account's home directory in `eval.dataset.location` | confirmed |

- **POST-ast-survey-agentharm-01**: Ordinal #20 (8 characters; neither a generic cloud or CI account nor on the release scan's allowlist): 6 matches, one in the `header.json` member of each of the 6 `.eval` logs (member objects 9b6feb8ee59d, 5ac78e51ddfc, 2040b443f665, 754609adf039, 655ac59e381f, 8e86d3ce28fc), under JSON key `location`, the path continuing into a dot-directory (a dataset cache); each `.eval` container holds the same header compressed (of the 85 archive-member findings inside the 6 containers, at most 6 are header copies; the rest are sample members with ordinals #1-#19). It is the same account as PC-ast-survey-agentdojo-13: the survey author's workstation account (the verifier's comparison, names held in memory only). The bare name occurs 0 times in aer/, sem/, prov/, validation/, the index, the register, corpus.json and the raw origin and member rows: the Inspect mapper never copies `eval.dataset` (D-235). Raw only, so CC-11 (S2), not CC-12(a) S0. kexin's `dataset-location-home` pattern matches all 6 headers; no statement covers them (`agentharm-raw-withheld-account-paths` names fragfuse and kexin only). The pre-check missed it (L1-10 screened 0 non-JSON files; the JSON screen did not open the `.eval` header). Recommendation: User decision (sent to the orchestrator 2026-10-24; one decision can cover both survey parts, as D-771 did for PC-13): (a) a D-604 object-scope withhold in survey-agentharm (@1 → @2), anchored on the header key `location` as kexin's `dataset-location-home`, withholding the 6 headers and their containers, then a re-import (1,056 executions); or (b) `pinned-account` plus a datasheet disclosure (D-604 item 7). Recommended: (a). Done: the user chose (a), D-811 (survey-agentharm@2), re-imported as `ast-survey-agentharm-rg2`; its post-check finds residue 0 (see that dossier).

## 8. Readiness for sealing

**never seal**: Superseded: survey-agentharm@1 has no withholding policy, so a seal would ship 6 raw `.eval` headers naming the survey author's account in `eval.dataset.location` (POST-ast-survey-agentharm-01). The user chose (a), a D-604 object-scope withhold (D-811, survey-agentharm@2); the tree to seal is `ast-survey-agentharm-rg2`. Every other check passed (release-mode re-import byte-identical 1,056/1,056; 0 seal refusals).

## 9. Reproduction

```bash
uv run python tools/precheck/run_postcheck.py --list --only ast-survey-agentharm
uv run python tools/precheck/postcheck_compare.py --corpus ast-survey-agentharm
```
