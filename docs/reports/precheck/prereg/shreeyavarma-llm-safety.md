# Pre-registration: `shreeyavarma-llm-safety`

| | |
|---|---|
| Corpus | `shreeyavarma-llm-safety` (family `agentdojo`, profile `shreeyavarma-llm-safety` v1, dialect/mapper `agentdojo.tracelogger`, identity table `shreeyavarma_pipeline_dirs`) |
| Parts | `head`: GitHub `ShreeyaVarma/llm_safety` @ `78d22e4a3daa5e76c77b75076c30ceb1faab22c1` |
| Wave | 2 (full pre-check; not examined in FA or E2, so there is no delta since E2) |
| Code commit | `065b0d36` or later |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Inputs: our own prior reports, GitHub metadata (tree listing, commit list, the fork's code and docs) and desk research only (`data/shreeyavarma-llm-safety/research.json`). No raw log was read and nothing was computed from the logs |

## 1. Sources (details and URLs in `research.json`)

- **Repository.** <https://github.com/ShreeyaVarma/llm_safety>. It is not a GitHub fork, but it carries the AgentDojo history up to upstream `acb4220a` (2025-06-07), which lies between v0.1.34 and v0.1.35. It has exactly one commit of its own, the pin `78d22e4a` (2025-09-10). That commit adds the 672 logs, the hidden-state classifier code and analysis outputs, and modifies 22 harness files. Most of those edits are typing changes. The behavioural edits are a `hf_qwen_agent` provider, the name "Local model" forced for `Qwen/` ids, and the `local` provider's port default set to 11434 (`vllm_parsed` keeps 8000; precision added by fact-check). The repository has 0 issues, 0 releases and 0 PRs. README.md and LICENSE are the unchanged upstream blobs.
- **Paper or results.** None. The repository's own reports evaluate a classifier on 1,000-conversation samples of AgentDojo result files; the reports do not name the directory, but the driver script defaults to a `runs/` directory, so these logs are most likely not their data (softened by fact-check). The AgentDojo v1 numbers (results page; arXiv:2406.13352 v3 Table 3) are **context only**.
- **Data record.** There is no Zenodo, HF or Figshare record. Integrity rests on the git blob ids at the pin. All 24,914 `runs/` blobs have the same blob sha as upstream `acb4220a` and as our `agentdojo · head` pin `089ed468`.
- **Licence.** MIT (the upstream AgentDojo LICENSE, with no fork copyright line). Policy include. Model-provider terms are unassessed.

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Blobs at pin | 28,307 (39,084 tree entries incl. 10,777 dirs) | profile `expected_files`; phase-10c census `files.all_tree_entries` (= 28,307 blobs); GitHub tree API (39,084 / 10,777) — source attribution corrected by fact-check |
| JSON blobs | 25,617 (parse ok 25,617) | phase-10c census `files.json_blobs` |
| Absent blobs (not fetched: nodejs/, PDFs, PNGs, weights) | 2,386; none under the six result dirs | census/trial `pin.absent_blobs` |
| Selected logs (units) | **672** (9,397,898 bytes) | `tools/readme_corpora.toml` (count 672, census); `docs/reports/phase10d/shreeyavarma-llm-safety.census.json` `/files`; GitHub tree |
| `select.owned_elsewhere` (owner agentdojo) | 24,914 | profile `exclude`; trial `counters.excluded` |
| Non-TraceLogger JSON (not matched by `include`) | 31 | 25,617 − 24,914 − 672; phase-10c `non_tl_dirs` (31 analysis outputs) |
| Executions | 672: sealed_clean 614, sealed_with_issues 58 | `shreeyavarma-llm-safety.trial.json` (jobs 8; jobs 3 subset of 137 byte-identical) |
| Units | agent_execution 670, outcome_only 2 | trial `summary.units` |
| Variants | v1.k14 668; v1.k14.incomplete 4 | census `variants`; phase-10c |
| Register codes | accounting_unverifiable 668; earlier_attempts_unobservable 670; identity_unresolved 58; incomplete_run 2; no_execution_observed 2; no_outcome_recorded 2 | trial `register_codes` |
| Suite / version | workspace 672; `benchmark_version` v1.2.1 and package 0.1.34 in all 672 | phase-10c novel census |
| `pipeline_name` | gpt-4o-2024-05-13 614; `local` 56; `Local model` 2 | phase-10c novel census |
| Attacks | tool_knowledge 588; none 84 (of which 29 injection-task pre-passes) | phase-10c novel census; census quirks |
| Roles | assistant 2,204; tool 1,841; system 670; user 670; calls 1,841; tool errors 87 | phase-10c novel census |
| System prompt | default (sha256 `a021a92b…`, 469 chars) 670; none 2 | phase-10c novel census; profile |
| Timestamps (naive) | 2025-06-18 23:41:52 .. 2025-07-12 13:04:08 (June 670, July 2) | phase-10c novel census |
| Outcome fields | utility True 316 / False 352; security True 172 / False 496; 4 logs without either key | phase-10c novel census |
| L2 sample | **32 units** (6 strata × 5 + 2 strata of 1) | README §4 rule applied to §3 strata |

## 3. Expected arms (L1-05 facets: results_dir × model × defence × suite × attack × task kind)

Defence is `none` in every log, and the suite is workspace v1.2.1 throughout (40 user tasks, 14 injection tasks). Strata come from the GitHub tree at the pin.

| Stratum (results_dir / pipeline_dir) | Model (identity) | Attack | Task kind | Logs | L2 draw |
|---|---|---|---|---:|---:|
| my_runs_conda / gpt-4o-2024-05-13 | gpt-4o-2024-05-13 (table row) | none | user_task 0..39 | 40 | 5 |
| my_runs_conda_with_attack / gpt-4o-2024-05-13 | gpt-4o-2024-05-13 | none | injection_task 0..13 (pre-pass) | 14 | 5 |
| my_runs_conda_with_attack / gpt-4o-2024-05-13 | gpt-4o-2024-05-13 | tool_knowledge | 40 × 14 | 560 | 5 |
| my_runs_qwen_agent / local | unresolved (D-105) | none | injection_task 0..13 (pre-pass) | 14 | 5 |
| my_runs_qwen_agent / local | unresolved | tool_knowledge | user_task 0, 1 × 14 | 28 | 5 |
| my_runs_qwen2_agent_no_attack / local | unresolved | none | user_task 0,1,2,3,5,6,7,8,9,10,11,12,14,21 | 14 | 5 |
| my_runs_hf_qwen_agent / Local model | unresolved | none | injection_task_0 | 1 | 1 |
| qwen_hf_unattacked / Local model | unresolved | none | user_task_0 | 1 | 1 |
| **Total** | | | | **672** | **32** |

- **Design.** No design is documented. gpt-4o covers the full v1.2.1 workspace grid: 40 benign, 14 pre-pass and 560 attacked runs.
- **Missing cells.** The local runs are fragments. They lack tool_knowledge for user tasks 2..39 (532 cells), 26 of the 40 benign user tasks for qwen2, and the pre-pass for the qwen2 and hf runs. No other suite, attack or defence is present.
- **Extra cells.** None expected.
- **Exclusion rule.** No stratum is excluded for being a fragment or for zero successes (user rule).
- **Alternative stratification.** If L2 strata were keyed by pipeline_dir × attack only, there would be 5 strata and 22 units, below the 30 minimum. The results-dir key above is pre-registered as the stratum.

## 4. Expected outcome rates (L2 outcome sanity; population tallies H6, H7)

The metrics map to logged fields as follows (AgentDojo):

- **UA** is the mean of `utility` over tool_knowledge logs.
- **ASR** is the mean of `security` over the same logs (True means the injection task succeeded).
- **Benign utility** is the mean of `utility` over `user_task_*/none` logs.
- **Pre-pass utility** is the mean of `utility` over the `injection_task_*/none` logs, read as "injection goal solvable".
- Benign `security` is the runner's constant True (`agentdojo.art.benign_security_constant`) and enters no rate.
- Logs without outcome keys (4) are excluded from denominators and reported separately.

| Arm | Logs with outcome | Expectation | Basis |
|---|---:|---|---|
| gpt-4o · tool_knowledge · ASR | 560 | **11.4% ≤ ASR ≤ 16.3%** (64..91 of 560) | Derived from census tallies: security True 172 − 81 benign constants = 91 attacked successes over 587 attacked logs with outcome (560 gpt-4o + 27 local). Assumes the constant is True in all 81 |
| all attacked (gpt-4o + local) · ASR | 587 | 91/587 = 15.5% (exact, same assumption) | census |
| all complete logs · utility | 668 | 316 True / 352 False (exact) | census |
| gpt-4o · tool_knowledge · UA; gpt-4o benign utility; local arms | – | no reported number: Wilson 95% only | – |
| context only (no verdict) | – | v1 all-suite gpt-4o tool_knowledge: utility 69.07%, UA 57.71%, ASR 34.50% (results page states neither suite version nor case count); important_instructions UA 50.08%, ASR 47.69% | <https://agentdojo.spylab.ai/results/>; arXiv:2406.13352v3 Table 3 |

At 5 sampled logs per stratum, no L2 cell reaches n ≥ 20, so L2 rates get Wilson intervals only. The comparison of record is the whole-population raw tally (H6, H7). It reads raw fields and needs no mapping.

## 5. Known quirks (expected-known findings)

| Id / source | Expected | Reference |
|---|---|---|
| `agentdojo.args_mutated_in_place` | 614 files | profile `observed`; census |
| `agentdojo.benign_security_constant` | 84 files, origin rule applied 81 | profile; census; `agentdojo.art.benign_security_constant` (scope does not list this source) |
| `agentdojo.injection_task_as_user_task_prepass` | 29 files (gpt-4o 14, local 14, hf 1) | profile; census; `agentdojo.art.injection_task_as_user` |
| `agentdojo.placeholder_args_never_injection_evidence` | 1,841 present and null | profile; census |
| `agentdojo.incomplete_run` | variant incomplete 4; register incomplete_run 2 (the two `Local model` logs) | profile; census; trial |
| `agentdojo.empty_messages_without_outcome` | 2 files (no_execution_observed) | profile (but see H11 on its location note) |
| `silent_rerun_last_pass_only` / `unexecuted_trailing_calls` | 0 / 0 | profile; reconcile (10c = 10d) |
| `local_model_raw_completion` (tag mismatches) | 0 turns | census `measured` |
| `pi_detector_redaction`, `tool_filter_aux_llm`, `spotlighting`, `repeat_user_prompt` | 0 | census `measured` |
| `package_version_not_code_identity` | 0 without package version; `code_identity = "range"`, `verified_code = []`, so D rules are cited via `_unverified` twins | profile; D-24 |
| Identity | 614 resolved via the table row (class I, `pipeline_dir_is_model_identity@1`); 58 `identity_unresolved`, `unk /model not_recorded` | D-92, D-105; table |
| Path with a space (`Local model`) | 2 logs; affects `tools/check_unicode.py` splitting (R7) | `docs/reports/phase10d/routing.md` R7 |
| Upstream copies | 24,914 byte-identical to `agentdojo · head` (blob sha equal at 089ed468) | profile `lineage.duplicates`; GitHub trees |
| `artefacts.toml` | **No entry is scoped to `shreeyavarma-llm-safety`.** Generic classes that should still occur: `agentdojo.art.benign_security_constant`, `.injection_task_as_user`, `.incomplete_run`, `.naive_timestamp`, `.payload_not_reaching_agent`, `.local_parse_drop` (0 expected), `.max_iters_pending` | `src/agentprov/adapters/agentdojo/artefacts.toml` |
| Census accounting | unverifiable 668, consistent 4 | census |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2. Reason codes: owned_elsewhere 24,914; 31 non-TL JSON outside `include`; 2,386 absent blobs outside the result dirs |
| L1-02 strict parse | yes | 672 logs |
| L1-03 encodings | yes | Local Qwen output may contain CJK or other non-Latin text; count it, but it is not a defect. `\uXXXX` residues are possible (AgentDojo #214) |
| L1-04 duplicates | yes | Within the part, and across corpora with `l1_xdup.py`. Expect 0 overlap with any other corpus. The 24,914 excluded copies overlap `agentdojo · head` by design |
| L1-05 arm coverage | yes | §3 (8 strata) |
| L1-06 secrets / account paths | yes | Counts and pointers only. Workspace benchmark content (security codes, passwords in emails) is benchmark text. Repository docs hold a cluster home path, but logs are expected to hold none |
| L1-07 timestamps | yes | Naive `evaluation_timestamp`; no per-call times; range in §2; all before the pin commit (2025-09-10) |
| L1-08 degenerate | yes | 2 empty-message logs, 2 incomplete; resolve the `empty_messages_with_outcome` = 2 counter (H5) |
| L2 import / validate / recompute / determinism | yes | Scratch corpus via the queue, `--cpu 2`, 32 units |
| L2 A2 / A3 classes, evidence classes | yes | Expect I-class `_unverified` citations only for family D rules |
| L2 identity | partial | gpt-4o resolves via the table. The 58 local logs must stay `identity_unresolved` (D-105). Resolving a Qwen model would be a defect |
| L2 redaction | yes | Expect no account path in AER/SEM/PROV |
| L2 withholding | inert | MIT, policy include, no copyleft or use rule. Only the generic secret path applies |
| L2 outcome sanity | partial | No paper numbers. Verdict-capable only through the population tally (H6) and its derived gpt-4o ASR bracket |
| Defence facet | no | No defence in any log |
| Delta since E2 | no | Not in E2 |

## 7. Hypotheses (falsifiable; each threshold fixed now)

| Id | Expectation | Falsified if | Class if falsified |
|---|---|---|---|
| H1 | L1 selects exactly 672 logs, with the per-stratum counts of §3 and 24,914 owned_elsewhere | any count differs by ≥ 1 | mapping-defect or source drift |
| H2 | All 672 parse strictly: 0 duplicate keys, NaN, BOM, invalid UTF-8, truncation | any hit | source-defect |
| H3 | U+FFFD 0, mojibake 0, C0/C1 controls 0 outside JSON escapes | any hit (non-Latin script in local logs is counted, not a hit) | source-defect, S3 |
| H4 | 0 byte-identical pairs among the 672. 0 cross-corpus byte overlap. 0 identical attacked trajectories across results dirs | ≥ 1 | documentation-mismatch, S2 |
| H5 | Exactly 2 logs have an empty `messages` list, and both lack utility and security. Exactly 2 further logs (both `Local model`) have messages but no outcome. 4 lack outcome keys in all. The census counter `empty_messages_with_outcome` = 2 is a counter artefact | an empty log carries outcome keys, or the counts differ | analysis-artefact (census counter) or source-defect, S3 |
| H6 | Raw tally over complete logs: utility 316/352 and security 172/496. All 81 benign logs with outcome have security True | any difference | census drift or mapping-defect |
| H7 | gpt-4o tool_knowledge ASR lies in [64, 91] of 560 (11.4–16.3%). Exploratory: the local tool_knowledge ASR over 27 is at most 27 | outside the bracket | documentation-mismatch (benign constant or census), S2 |
| H8 | 0 provider keys (`sk-`, bearer) and 0 account paths (`/Users/`, `/home/`, `/cluster/home/`, `C:\Users\`) in the 672 | any hit | security finding, reported at once |
| H9 | 672 naive timestamps, all within 2025-06-18..2025-07-12 and none after the pin commit (2025-09-10T15:18Z). The 2 July logs are the `Local model` (hf) logs | out of range; July logs elsewhere | source-defect, S3 (location: documentation note only) |
| H10 | `pipeline_name` equals the pipeline dir in all 672 (gpt-4o 614, local 56, Local model 2). `agentdojo_package_version` 0.1.34 and `benchmark_version` v1.2.1 in all | any mismatch | mapping-defect or source-defect, S3 |
| H11 | The two empty-message logs are `my_runs_qwen2_agent_no_attack/local/workspace/user_task_14/none/none.json` and `my_runs_qwen_agent/local/workspace/user_task_1/tool_knowledge/injection_task_13.json`. The profile note ("both in my_runs_qwen2_agent_no_attack") is therefore wrong | both are in qwen2 | documentation-mismatch in our profile, S3 (route to family owner) |
| H12 | #213 effect: in the 560 gpt-4o attacked logs, the injected tool_knowledge text for injection_task_6..13 lists no tool-call sequence, while 0..5 do | any 6..13 payload lists calls, or any 0..5 payload lacks them | documentation-mismatch of the lead, S3 |
| H13 | (exploratory) #116 effect: every gpt-4o `user_task_16` log (1 benign + 14 attacked) that calls `get_unread_emails` has utility False | any such log with utility True | refutes the lead (no finding) |
| H14 | (exploratory) LocalLLM defects (#150, #202, #219, #220): count the local assistant turns with 0 parsed calls whose text holds call-like syntax (`<function=`, a fenced JSON call or `<tool_call>`), and the local runs whose final answer is empty. Expected: ≤ 5% of the 56 local logs show either | > 5% (≥ 3 logs) | expected-known extension of `agentdojo.art.local_parse_drop`, S2 (propose scope incl. this source) |
| H15 | L2 on 32 units: every stage ok, 0 failing checks, 0 degenerate, 0 `adapter_defect`. `recompute --dry-run` reports 0 differences. A second import with different `--jobs` is byte-identical. gpt-4o identity resolves for 100%; local units are 100% `identity_unresolved` | any failure | mapping-defect |
| H16 | The 2 `outcome_only` units of the trial are exactly the 2 empty-message logs. Their AER carries no invented outcome (no utility or security judgement) | an invented judgement, or other units | mapping-defect (S1 if an outcome is invented) |
| H17 | No defence-authored, tool-filter or detector message occurs in any log (census measured 0) | any | mapping-defect or source-defect, S3 |

Rule: no stratum is excluded for zero attack successes or for being a fragment.

## 8. Fact-check (2026-10-14, adversarial pass; desk sources only, no data read)

Checked and **confirmed**:

- Pin and record (GitHub API): `78d22e4a` is HEAD of the only branch, author and committer date 2025-09-10T15:18:57Z, single parent upstream `acb4220a` (PR #85 merge, 2025-06-07); repo fork=false, MIT, 0 issues / PRs / releases. Recursive tree, not truncated: 39,084 entries, 28,307 blobs, 10,777 trees. Against `acb4220a`: 3,223 added, 22 changed (all under `src/agentdojo/`), 0 removed. README.md and LICENSE are unchanged blobs. All 24,914 `runs/` blobs have the same sha at `acb4220a` and at `089ed468` (head has 36,679 runs blobs).
- §3 strata from the tree: 40 / 14 / 560 / 14 / 28 / 14 / 1 / 1 = 672 logs, 9,397,898 bytes. qwen2 user tasks {0,1,2,3,5,6,7,8,9,10,11,12,14,21}; qwen_agent tool_knowledge only user_task_0/1, the pair used in the README example. The two smallest logs (381 B and 1,316 B) are the ones H11 names.
- §2 counts against our reports: trial (jobs 8) sealed_clean 614 / with issues 58, units 670 / 2, register codes as listed, excluded 24,914; census variants 668 / 4, quirks 614 / 84 / 81 / 29 / 1,841, accounting 668 / 4, no_execution_observed samples = H11 paths; phase-10c full census json_blobs 25,617, `non_tl_dirs` 31 (24,914 + 672 + 31 = 25,617); novel census outcome tallies 316/352/4 and 172/496/4, roles, timestamps, model×attack. `readme_corpora.toml` count 672.
- §4 bracket arithmetic: 172 − 81 = 91 over 560 + 27 = 587; 64/560 = 11.4%, 91/560 = 16.25%. The 84 − 81 = 3 benign logs without outcome match 1 empty qwen2 log + 2 `Local model` logs.
- Harness: pyproject 0.1.34, uv.lock 0.1.32 (pin and base); `--benchmark-version` default v1.2.1 at both; the `hf_qwen_agent` provider, the forced name "Local model" for `Qwen/` ids, and the port default change (`local` provider only) in `agent_pipeline.py`.
- Bugs: #116 is closed. Its fix (PR #130) changes UserTask16 only under `v1_2_2`, and the maintainer says it shipped in 0.1.35, so v1.2.1 is affected. #213 is open. `ground_truth()` returns `[]` for workspace injection_task_6..13 in `v1_2`/`v1_2_1` at the pin, and the fork's `ToolKnowledgeAttack` builds its payload from `ground_truth()`, so H12 is well founded (40 × 8 = 320). #150, #202, #219, #220 are open LocalLLM defects; #89 was closed without Ollama support; #71/#75 were fixed 2025-04-30, before the base. #168, #218 are open and #189 is closed; they concern trace scoring.
- Context numbers: results page row gpt-4o-2024-05-13 / tool_knowledge 2024-06-05: 69.07 / 57.71 / 34.50%; arXiv v3 (2024-11-24, Llama fix and travel-suite update) Table 3 GPT-4o 69.00 / 50.08 / 47.69%; Table 4 has no tool_knowledge row; v1 workspace 40 × 6, 629 cases in total.
- Licence: LICENSE at the pin is MIT, (c) 2024 Debenedetti, Zhang, Balunovic, Beurer-Kellner, Fischer, Tramèr; GitHub reports MIT. `artefacts.toml` has no entry scoped to this source; all seven generic classes named in §5 exist.

**Corrected** (marked in `research.json`):

1. `acb4220a` is **14** commits after v0.1.34 (compare API), not 4. The figure of 26 commits before v0.1.35 is right.
2. The results page states neither the benchmark version nor the number of cases. "629 (v1)" for the page row is an inference.
3. The 11434 port default applies to the `local` provider only.
4. The repository reports do not name `runs/` themselves. The claim that they did not use the 672 logs rests on the classifier script's default directory, so it is softened.
5. The phase-10c `all_tree_entries` figure is 28,307 (blobs). The 39,084 / 10,777 figures come from the GitHub tree API.

**Unverifiable here**: which Qwen checkpoints were used. Also whether the pinned harness produced the logs, since the commit is about two months later than the logs. No hypothesis threshold changed.
