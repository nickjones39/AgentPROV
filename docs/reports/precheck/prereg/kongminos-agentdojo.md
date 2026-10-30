# Pre-registration: `kongminos-agentdojo`

| | |
|---|---|
| Corpus | `kongminos-agentdojo` (family `agentdojo`, profile `kongminos-agentdojo` v1, dialect/mapper `agentdojo.tracelogger`, variant `v1.k14`) |
| Parts | `head` (only part) |
| Wave | 3 (first examination; not in FA or E2) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: our prior reports (phase-10c census summaries, phase-10d census, trial, reconcile), the profile, the identity table `kongminos_pipeline_dirs`, the registry, `artefacts.toml`, DECISIONS (D-92, D-100, D-103, D-105, D-106), and desk research (`data/kongminos-agentdojo/research.json`). The per-cell counts below come from the GitHub tree listing (metadata), not the raw logs. |
| Method | [`../README.md`](../README.md) |

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Repository | [kongminOS/jspace-agentdojo-950](https://github.com/kongminOS/jspace-agentdojo-950): not a fork, branch `main` only, no tags, issues or PRs; MIT | GitHub API |
| Pin | `f341af69` (2026-08-22T04:49:25Z), still head. It changes one README line, the model: "DeepSeek V4 Pro / J-Space combinations" becomes "DeepSeek V4-Flash, unrelated to J-Space" | [commit](https://github.com/kongminOS/jspace-agentdojo-950/commit/f341af69498ee36a8d1a2e69040ab70bd8e20a01) |
| Data commit | `47a44d18` (03:06:09Z): all 950 logs, README, `recompute_agentdojo.py` ("v3 calibrated"). Then 4 article PNGs (04:34Z) | GitHub API |
| Paper / data record | none. The README serves an article ("J-Space 翻车全记录"); it was not found. No Zenodo, HF or Figshare record | research.json |
| Harness | logs say agentdojo `0.1.35`, which names the distribution, not the code. `benchmark_version` is `v1.2.2` in 950/950. `pipeline_name` is `local` (AgentDojo `LocalLLM`, prompt-parsed `<function=…>` calls, null ids). Attack: `tool_knowledge` only | phase-10c census, `local_llm.py`@a75aba76 |
| Model | `deepseek-v4-flash` (README l. 9, class I, D-92). [corrected] The V4-Flash API was moved to the re-trained 0731 model on 2026-07-31; whether the id is a rolling alias is not documented. Checkpoint, endpoint and thinking mode not recorded | identity table, research.json |
| Run time | 2026-08-21 12:40:34 to 15:07:40 (naive) | phase-10c census `ts_range` |

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Tree blobs at pin | 957 (16,997,212 bytes, incl. 4 PNGs 1,317,158) | profile `expected_files`; git trees API; census `all_tree_entries` |
| Selected logs (`data/*/*/*/*/*/*.json`) | 950 (15,674,195 bytes; 2,188 to 84,567 per file; 950 distinct blob SHAs) | registry/`readme_corpora.toml` (census `/files`); trees API |
| Not selected | 7: `LICENSE`, `README.md`, `recompute_agentdojo.py` (context artefacts, supporting); 4 PNG absent blobs (`covering_paths` 4) | profile, census `pin` |
| JSON parse ok | 950 / 950 | phase-10c census |
| Units / executions | 950 `agent_execution` / 950 | phase-10d census and trial (jobs 8; subset 191 at jobs 3, byte-identical) |
| Sealed clean / with issues | 925 / 25 (`unexecuted_tool_call`) | trial |
| Register codes | `map.accounting_unverifiable` 950, `map.earlier_attempts_unobservable` 950, `map.unexecuted_tool_call` 25 | trial |
| Messages | assistant 4,236; tool 3,286; system 950; user 950; calls 3,311 (all ids null); tool errors 232 | phase-10c census |

Per cell, from the tree listing: attacked / pre-pass / benign.

| Run set | Suite | Attacked (`tool_knowledge`) | Pre-pass (`injection_task_*/none`) | Benign (`user_task_*/none`) | Total |
|---|---|---:|---:|---:|---:|
| `ad_full_*` | workspace | 560 (40 × 14) | 14 | 40 | 614 |
| `ad_tb_*` | banking | 144 (16 × 9) | 9 | 16 | 169 |
| `ad_tb_*` | travel | 140 (20 × 7) | 7 | 20 | 167 |
| | **Total** | **844** | **30** | **76** | **950** |

The README's "874 attack combinations" are 844 attacked logs plus 30 pre-pass logs, all in the `ad_*_attack` directories.
No (suite, task dir, file) key occurs in both run sets.

## 3. Expected arms

| Facet | Values | Expected missing / extra |
|---|---|---|
| Model | `deepseek-v4-flash` (one table row for dir `local`) | none extra |
| Defence | none | none |
| Attack | `tool_knowledge` (844); `none` (106 = 76 benign + 30 pre-pass) | no other attack label |
| Suite | workspace, banking, travel (v1.2.2) | **slack absent by design**; 29 "ad_runs" logs named by the README are not released (0 expected) |
| Task kind | user task; injection task as user task (pre-pass) | pre-pass 30 = injection tasks of v1.2.2 (14 + 9 + 7) |

Strata for L2: run set × suite × task kind gives 9 strata, about 5 units each. That is 45 units (minimum 30).

## 4. Expected outcome rates (L2 comparison targets)

Metric mapping. The README uses the script's definitions:
- Benign = `utility` over the `ad_*_benign` logs.
- UA = `utility` over all `ad_*_attack` files.
- ASR = `security` over all `ad_*_attack` files, so the denominator 874 includes the 30 pre-pass logs.

Our AgentDojo convention differs:
- targeted ASR = `security == true` over the 844 `tool_knowledge` logs.
- UA = `utility` over the same 844 logs.
- Benign utility = `utility` over the 76 benign logs.
- Pre-pass `utility` measures whether an injection task can be solved. It is reported separately.
- Benign and pre-pass `security` is the runner's constant `true` and enters no rate.

| Arm | Quantity | Source value | Our-convention target | Source |
|---|---|---|---|---|
| v4-flash / none / benign (all suites) | utility | **67/76** (88.16%) | 67/76 | README table row 1 |
| v4-flash / `ad_*_attack` (874) | utility | 82.38% → **720/874** | (720 − pre-pass utility true) / 844 | README row 2 (count = % × n) |
| v4-flash / `ad_*_attack` (874) | security | **34/874** (3.89%) | **4/844 (0.47%)** if all 30 pre-pass are constant true | README row 3; census security true 110 = 76 + 34 |
| per suite (workspace / banking / travel) | all | not reported | none (Wilson only) | script prints, README omits |

Whole-population census reference (not a source number): utility true 787 (= 67 + 720), security true 110 (= 76 + 34).
L2 samples about 5 per stratum, below 20 per arm, so L2 gives Wilson intervals only. The exact test is H1/H2.

## 5. Known quirks

| Id | Expected | Source |
|---|---|---|
| `agentdojo.benign_security_constant` | 106 files, rule applied 106 (76 benign + 30 pre-pass) | profile `observed`, census |
| `agentdojo.injection_task_as_user_task_prepass` | 30 files | profile, census, reconcile |
| `agentdojo.args_mutated_in_place` | 907 files (files with calls; 43 without any call) | profile, census |
| `agentdojo.placeholder_args_never_injection_evidence` | 3,311 present, all null | profile, census |
| `agentdojo.provider_call_id_anomalies` | 3,311 null ids in 907 logs; 0 absent, empty or duplicate | profile, census |
| `agentdojo.unexecuted_trailing_calls` | 25 calls in 25 logs (samples: workspace `user_task_25` × several, pre-pass `injection_task_13`) | profile, census `issue_samples` |
| `agentdojo.silent_rerun_last_pass_only` | 0 null-final logs; `earlier_attempts_unobservable` 950 | profile, trial |
| `agentdojo.package_version_not_code_identity` | 0 without version (all `0.1.35`); `code_identity = "unpinned"`, `verified_code = []` (D-103) | profile |
| `agentdojo.local_model_raw_completion` | turns with more tags than calls 0; turns with tags and no calls 0 | census `measured` |
| Identity | `pipeline_name` `local` = `config_tag_never_model` (D-106); model from table row, class I, basis README (D-92, D-105) | profile, table |
| System prompt | 469-char AgentDojo default in 950/950 | profile, census |
| `agentdojo.art.*` entries | none scoped to profile `kongminos-agentdojo` yet. The generic ones apply in substance: `local_parse_drop`, `max_iters_pending`, `naive_timestamp`, `calls_derived_from_messages`, `validity_defects`, `payload_not_reaching_agent`, `injection_task_as_user`, `benign_security_constant` | `artefacts.toml` |
| Accounting | `unverifiable` 950 | census |

Census arithmetic shows one call per assistant message:
- 3,311 calls = 3,286 executed + 25 trailing.
- 4,236 assistant messages = 3,311 with a call + 925 final messages without one.

This matches LocalLLM's first-tag-only parser (#150).

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2; selection by the profile `include`, 2 `select.not_execution_artefact` globs (expect 0 hits), 3 context artefacts |
| L1-02 strict parse | yes | expect 0 defects (parse ok 950) |
| L1-03 encodings | yes | expect 0 U+FFFD and 0 invalid UTF-8. Count CJK text in model output (DeepSeek) as information only |
| L1-04 duplicates | yes | 0 byte-identical (950 distinct blob SHAs). Trajectory repeats are expected within (suite, user task) across injection tasks where no payload is read (H8). Cross-corpus: other `deepseek-v4-flash` corpora (SENTRY) use other attacks, so expect 0 |
| L1-05 arm coverage | yes | §2 grid; plus the whole-population tallies for H1-H3 |
| L1-06 secrets / account paths | yes | expect 0 (README says no keys or configs; LocalLLM logs no endpoint). AgentDojo fixture passwords and IBANs are expected-known |
| L1-07 timestamps | yes (partly) | presence, parse, zone (naive), range 2026-08-21 12:40:34 to 15:07:40, per-run-set ranges; within-unit monotonicity does not apply |
| L1-08 degenerate | yes | expect 0 empty, 0 null-final, 0 run errors, 0 null utility; 25 unexecuted trailing calls; empty-final-answer runs (#220) H5 |
| L2 import, validate, recompute, determinism | yes | trial: 0 failures, byte-identical across jobs 8/3 |
| L2 A2 / A3 classes | yes | expect only the trial's register codes; no `call_result_link_conflict` (one call per turn) |
| L2 evidence classes | yes | D rules only as `_unverified` twins; call-result links positional (I); model identity class I |
| L2 degenerate / adapter_defect | yes | expect 0 / 0 |
| L2 identity | yes (reduced) | model = table row `deepseek-v4-flash`, class I with README basis; defence none; no logged model to compare |
| L2 redaction | yes | expect no account path in AER/SEM/PROV |
| L2 withholding | conditional | only if L1-06 finds a secret-like string; none expected |
| L2 outcome sanity | yes (Wilson only) | §4; no per-suite source numbers |
| Defence / denial checks | no | no defence arm |
| Delta since E2 | no | not examined in FA/E2 |

## 7. Hypotheses (falsifiable)

| # | Expectation | Refuted if |
|---|---|---|
| H1 | The README's own tallies reproduce exactly on the released files: benign utility 67/76, `ad_*_attack` utility 720/874, `ad_*_attack` security 34/874 | any count differs (the released files are not the "v3 report" set; `documentation-mismatch`) |
| H2 | All 30 pre-pass logs have `security == true`, and targeted ASR over the 844 attacked logs is **4/844**. The README's 3.89% overstates targeted ASR about 8-fold (S2, documentation-mismatch in the source's figure) | attacked security true ≠ 4, or any pre-pass security false |
| H3 | Workspace `injection_task_6..13` (320 cells): payloads contain no "use the tool" instruction (empty ground truth, #213) and 0 security true. Every other attacked payload names ≥ 1 tool. Payloads address "Local model" (MODEL_NAMES['local']) in 844/844 | any IT6-13 payload with tool instructions, any IT6-13 success, or a different model name in payloads (then the code is not stock 0.1.35) |
| H4 | Of the ≤ 4 attacked successes, every banking `injection_task_0/1/3` success has the required data in the transaction subject. If not, it is a #181 false positive (S2) | n/a (counted): report successes by (suite, injection task) and the subject check |
| H5 | 0 runs end with an empty final assistant text and no call (#220 server-error-as-answer) among the 43 zero-call logs and in total | ≥ 1 such run (S2: infrastructure failures scored as failed attacks / tasks) |
| H6 | Each of the 3,311 call-bearing assistant messages has exactly one call and its text holds exactly one `<function=` tag. 0 messages hold a tag without a parsed call (#150/#202/#219) | any message with > 1 call; ≥ 1 % of call messages without a tag (the client is not stock LocalLLM); any tag without a call (dropped call, S2) |
| H7 | The 25 unexecuted trailing calls are max-iteration stops: each such log has exactly 15 executed tool messages | any of the 25 with ≠ 15 tool messages (stop cause unknown) |
| H8 | Trajectory-equal groups (if any) fall ≥ 90 % within one (suite, user task) across injection tasks, with no payload in any tool result | < 90 %, or a repeat across suites or user tasks (copying) |
| H9 | Each (suite, user task, injection task) cell occurs exactly once (844 + 30 + 76). `benchmark_version` is `v1.2.2` in 950. Injection task ids are 0-13 / 0-8 / 0-6 | duplicate, hole, extra label or other version |
| H10 | Timestamps: per-run-set ranges lie within 2026-08-21 12:40:34-15:07:40. All 950 predate the data commit (2026-08-22T03:06Z) under any zone UTC-12…+14 | a timestamp outside the range, or after the commit |
| H11 | System prompt equals the 469-char default in 950/950, and no message role other than system/user/assistant/tool appears (no visible J-Space or other harness layer) | any other prompt or role |
| H12 | 0 secret-like strings and 0 account paths in the 950 logs | ≥ 1 |

## 8. Discrepancy leads carried to the dossier

| Lead | Class (expected) |
|---|---|
| README ASR/UA include the 30 pre-pass logs (H2) | documentation-mismatch, S2 |
| Model asserted from one README line, rewritten in the pin commit from "V4 Pro / J-Space" to "V4-Flash". The repo description still links the data to the J-Space article. Checkpoint, endpoint and thinking mode are unrecorded (the V4-Flash API changed to the re-trained 0731 model on 2026-07-31 [corrected: not documented as a rolling alias]) | documentation-mismatch / disclosure, S2 (datasheet: model-level analyses carry the class-I caveat) |
| LocalLLM parser and error defects (#150, #202, #219, #220) may under-count attack success and utility (H5, H6) | expected-known if 0; source-defect otherwise |
| v1.2.2 workspace IT6-13 carry no tool instructions (#213) and banking IT0/1/3 scoring is lenient (#181) (H3, H4) | source-defect (benchmark), S2 |
| 29 unreleased "ad_runs" logs; undocumented dedup choice | documentation-mismatch, S3 |
| README links `princeton-pli/AgentDojo` (404) | documentation-mismatch, S3 |
| `artefacts.toml` scopes no entry to this profile | mapping/catalogue gap, S3 (route to family owner) |

## 9. Fact-check (adversarial, 2026-10-14)

Re-checked against the GitHub API, the files at the pin, upstream AgentDojo at `a75aba76` and our own prior reports. No raw log was read.

| Claim | Verdict | Evidence |
|---|---|---|
| README "v3 report" figures: Benign 88.16% (67/76), UA 82.38%, ASR 3.89% (34/874); table identical in `47a44d18` and `f341af69` | confirmed | README at both commits; the diff is line 9 only. 67/76 = 88.16%, 34/874 = 3.89%. 720/874 = 82.38% (719 and 721 give 82.27% and 82.49%, so 720 is the only count that fits) |
| Metric definitions | confirmed, with a note | `recompute_agentdojo.py` keys attack logs by the JSON fields (suite_name, user_task_id, injection_task_id) and benign logs by (suite_name, user_task_id), then counts `is True`. So "over all files" holds only if those keys are unique. Pre-pass logs (user_task_id = injection_task_k, no injection id) keep separate keys, and README n = 874 equals the file count. The owner's `rein-test-suite/docs/metrics.md` uses the same ASR/UA convention |
| 874 = 844 + 30; 30 pre-pass security constant true; derived 4/844 | confirmed (derivation) | `task_suite.py`@a75aba76 l. 409-410 returns `utility, True` when injection_task is None. Phase-10c census: security true 110, utility true 787, attack_type tool_knowledge 844 / None 106; benign_security_constant files 106. Then 787 − 67 = 720 and 110 − 76 − 30 = 4, consistent with the README |
| Tree: 957 blobs / 16,997,212 B; 950 logs / 15,674,195 B; 2,188-84,567 B; 950 distinct SHAs; non-image 15,680,054 B; per-cell 560/14/40, 144/9/16, 140/7/20; 40/16/20 user tasks under attack; 14 injection ids; no key in both run sets | confirmed | git trees API at `f341af69` (not truncated), re-listed |
| Data commit `47a44d18` holds all 950 logs; later commits change only README and add 4 PNGs | confirmed | tree at `47a44d18` (953 blobs) vs the pin: only README.md and the 4 PNGs differ |
| Pin = head; commit history and times; 1 h 43 min gap | confirmed | commits API (03:06:09Z to 04:49:25Z) |
| Repo: not a fork, main only, no tags, releases, issues or PRs; MIT | confirmed | repos API |
| Licence | confirmed | LICENSE at the pin is the standard MIT text, "Copyright (c) 2026 kongminOS" (identical to the GitHub MIT template apart from whitespace). Upstream AgentDojo is MIT, (c) 2024 Debenedetti et al. No use restriction found |
| Expected counts from registry, census and trial (950 files; 925/25 sealed; register codes; 191-execution subset at jobs 3, n_differ 0; message, call and id counts; ts_range; 469-char system prompt) | confirmed | `tools/readme_corpora.toml`, `docs/reports/phase10d/kongminos-agentdojo.{census,trial}.json`, phase-10c census summary `kongminos@f341af69498e.summary.json` |
| No paper or data record; article not findable | confirmed (absence) | web search for the article title: no hit. AgentDojo arXiv:2406.13352 v3 (2024-11-24) is the benchmark paper only |
| Upstream issues #150, #181, #201, #202, #213, #219, #220 say what is claimed | confirmed | issue titles and bodies (all open). #181: an operator-precedence bug reduces the IT0/1/3 checks to "any transfer to the attacker IBAN". #213: workspace IT6-13 `ground_truth()` returns []; ToolKnowledgeAttack builds its tool text from ground_truth, so those payloads get none. #201 is a question (0/560 on another model), not a finding |
| `princeton-pli/AgentDojo` returns 404 | confirmed | repos API 404 |
| v0.1.35 = `a75aba76` (2025-10-27); main still 0.1.35 at `089ed468` (2026-06-02); LocalLLM temperature 0.0, random seed; MODEL_NAMES['local'] = "Local model" | confirmed | tags API; pyproject at `089ed468`; `local_llm.py`, `models.py` at a75aba76 |
| deepseek-v4-flash is a "rolling alias" | corrected | TechNode (2026-07-31) reports a re-trained V4-Flash-0731 and limits the change to the V4-Flash API. No source states that the id `deepseek-v4-flash` is rolling. Reworded in §1 and §8 |
| Minor research.json details | corrected | AgentDojo v3 is the 2024-11-24 revision (Llama bug fix and travel-suite update), not "camera-ready". ToolKnowledgeAttack.get_tools_sequence is at l. 113-131 at a75aba76, not l. 111-130 |

No expected count or hypothesis was changed. No new expectation was derived from data.

