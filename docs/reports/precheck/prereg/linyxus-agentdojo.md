# Pre-registration: `linyxus-agentdojo`

| | |
|---|---|
| Corpus | `linyxus-agentdojo` (family `agentdojo`, profile `linyxus-agentdojo` v1, dialect/mapper `agentdojo.tracelogger`, variants `v1.k14`, `v1.k14.incomplete`, identity table `linyxus_pipeline_dirs.toml`) |
| Parts | `head`: GitHub `Linyxus/agentdojo` branch `lacuna-exp` @ `698d7ff29cac4bb5dccb5ed2d06f5e8364547a97` (2026-05-24; still branch HEAD on 2026-10-14) |
| Wave | 3. This is a full pre-check. The corpus was not examined in FA or E2, so there is no delta since E2 |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: our prior reports (the phase-10c census summaries, the phase-10d census, trial and reconcile), the profile and identity table, the registry, `artefacts.toml`, DECISIONS, and desk research (`data/linyxus-agentdojo/research.json`). Per-cell counts come from the GitHub trees API listing of the pin and of earlier commits (paths, blob ids and sizes only). No outcome was tallied from raw data or from the per-file census |
| Method | [`../README.md`](../README.md) |

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Repository | [Linyxus/agentdojo](https://github.com/Linyxus/agentdojo), a fork of ethz-spylab/agentdojo (merge base `18b501a6`, 2026-03-30). MIT, with upstream's LICENSE text unchanged. Issues are disabled. Branches: main (no runs), tacit-exp `4bd1de08` (7,367 logs, all present at the pin with the same blob ids), lacuna-exp = pin | GitHub API |
| Paper 1 (TACIT) | [arXiv:2603.00991](https://arxiv.org/abs/2603.00991v2), *Tracking Capabilities for Safer Agents* (Odersky, Zhao, Xu, Bračevac, Pham). v1 (2026-03-01) has **no** AgentDojo results. v2 (2026-05-07) adds Sec. 4.1 "Stock AgentDojo domains" and **App. E.2 Table 4**. ACM CAIS 2026, DOI 10.1145/3786335.3813127 | arXiv API/HTML |
| Paper 2 (LACUNA) | [arXiv:2605.28617v1](https://arxiv.org/abs/2605.28617v1), *LACUNA: Safe Agents as Recursive Program Holes* (2026-05-27). **Sec. 7.4 Table 3**: LACUNA rows from the lacuna-runs sets, TACIT rows copied from Paper 1 | arXiv API/HTML |
| Our docs | The profile says `paper = "none found (phase 10c)"` and does not mention LACUNA | profile |
| Data record | None (Zenodo 0, HF 0). The git repository is the only release | research.json |
| Harness | A vendored AgentDojo fork. Logs say 0.1.35 / v1.2.2. Code changed during and after the runs (`code_identity = "range"`, `verified_code = []`). TACIT is a local jar build with no version. Provider is OpenRouter via LiteLLM. Attack is `important_instructions` only | profile; commits |
| Mechanism | Under `--use-tacit` the agent calls `eval_scala` (21,030 of 21,627 calls). Environment calls are only in the extra key `backend_tool_traces`. The classified answer is in `tacit_secure_output` and `*.secure-channel.txt` | phase-10c census; commits `02205e01`, `10095f3c` |
| Result scripts at pin | `util_scripts/render_run_results.py` reads one root: utility under attack and `security=True` over the attacked logs that validate. `render_lacuna_results.py` reads all `lacuna-runs*` roots and dedups per model × suite by (attack, UT, IT); the latest `evaluation_timestamp` wins | repo at pin |

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Tree blobs / bytes at pin | 17,656 / 196,887,263 | profile `expected_files`/`expected_bytes`; git tree |
| Selected logs (units) | **9,068** (191,704,610 bytes) | `tools/readme_corpora.toml` (9068, census `/files`); phase-10d census; git tree |
| Not selected: `*.secure-channel.txt` | 8,383 (`select.not_execution_artefact`) | trial `counters.excluded`; git tree |
| Not selected: code/docs | 205 (incl. `.devcontainer/devcontainer.json`, the only non-TraceLogger JSON) | git tree; phase-10c census `non_tl_dirs` |
| Executions | 9,068 = `agent_execution` 9,065 + `outcome_only` 3 | phase-10d census `units` |
| Variants | `v1.k14` 9,053; `v1.k14.incomplete` 15 | census |
| Register codes (full population) | accounting_unverifiable 9,061; earlier_attempts_unobservable 9,065; unknown_top_level_key 9,055; system_prompt_unrecognised 8,759; pipeline_name_mismatch 685; retry_passes_inferred 355; unexecuted_tool_call 42; incomplete_run 12; no_execution_observed 3; no_outcome_recorded 3; undeclared_quirk 3 | phase-10d census `files_by_issue_code` |
| Run roots | runs-0 685; runs-1 155; runs-2 1,970; runs-3 1,623; runs-4 2,935; lacuna-runs-0 880; lacuna-runs-1 820 | census `prefix`; git tree |
| Suites | workspace 3,885; banking 2,675; travel 1,420; slack 1,088 | census |
| Attack | important_instructions 8,654 (all `user_task_*`); none 414 (all `injection_task_*` pre-pass) | census; git tree |
| Benchmark / package | v1.2.2 / 0.1.35 in 9,068; `error` null in 9,068 | census |
| Timestamps (naive) | 2026-04-13 19:53:09 .. 2026-05-23 18:52:51. April 7,367 (= tacit-exp); May 1,701 (= 1,700 lacuna + 1 deepseek) | census `ts_range`, `ts_month` |
| Extra keys | backend_tool_traces 9,053; tool_trace_source 9,053 (backend_runtime 8,747, assistant_messages 306); tacit_secure_output 8,372; model 1,701 | census `flags` |
| Outcome fields | utility T 4,855 / F 4,198 / None 15; security T 557 / F 8,496 / None 15 | census |
| Trial (phase 10d) | Subsets only: 4,540 (every 2nd) and 920 (every 10th). All stages ok, 0 failing checks, byte-identical across jobs 8 and 3 | trial.json |
| L2 sample | **≈ 252 units**: 52 strata (§3), Σ min(5, n) = 252 ≤ 300, so there is no reduction | README §4 applied to git-tree strata |

## 3. Expected arms (L1-05; L2 strata)

The stratum key is run family (`runs-*` = TACIT era; `lacuna-runs-*` = LACUNA era) × pipeline dir (model, defence) × suite × attack (II = important_instructions, pre = injection-task pre-pass). That gives 52 strata. The repetition (`runs-N`) is a reporting facet. Full cell per run: banking 144+9, slack 105+5, travel 140+7, workspace 560+14.

Attacked logs per run root (git tree; "+p" = pre-pass logs):

| Pipeline dir | Suite | runs-0 | runs-1 | runs-2 | runs-3 | runs-4 | lacuna-0 | lacuna-1 |
|---|---|---|---|---|---|---|---|---|
| o4-mini-high-tacit | banking | 144+9 | 144+9 | 144+9 | 144+9 | 144+9 | 144+9 | 144+9 |
| o4-mini-high-tacit | workspace | – | – | 560+14 | 560+14 | 560+14 | 560+14 | – |
| o4-mini-high-tacit | slack / travel | – | – | 105+5 / 140+7 | 105+5 / 140+7 | 105+5 / 140+7 | – | 105+5 / 140+7 |
| gemini-2.5-pro-tacit | banking | 144+9 | 0+1 | 144+9 | 144+9 | 144+9 | 144+9 | 144+9 |
| gemini-2.5-pro-tacit | workspace | – | – | 560+14 | **215**+14 | **298**+14 | – | **–** |
| gemini-2.5-pro-tacit | slack / travel | – | – | 105+5 / 140+7 | 105+5 / 140+7 | 105+5 / 140+7 | – | 105+5 / 140+7 |
| o4-mini-high (native) | banking | 144+9 | – | – | – | – | – | – |
| gemini-2.5-pro (native) | banking | 144+9 | – | – | – | – | – | – |
| gpt-5.4-nano-tacit | banking | **63**+9 | – | – | – | 144+9 | – | – |
| gpt-5.4-nano-tacit | slack / travel / workspace | – | 0/0/0+1 (ws) | 0+2 (travel) | – | 105+5 / 140+7 / **276**+14 | – | – |
| claude-sonnet-4-tacit | b / s / t / w | – | – | – | – | 144+9 / **93**+5 / **88**+7 / **168**+14 | – | – |
| gpt-5.4-tacit | banking | 0+1 | – | – | – | – | – | – |
| deepseek-v4-flash-tacit | workspace | – | – | – | – | 0+1 | – | – |

- **Missing compared with the papers.** gemini-2.5-pro LACUNA workspace has 0 logs, although Table 3 reports 315/560 and 4/560. All 8 TACIT cells of Table 4 are backed by at least runs-2.
- **Extra (no paper number).** The native gemini and o4 banking arms (306), gpt-5.4-nano (775), claude-sonnet-4 (528), gpt-5.4 (1), deepseek-v4-flash (1), every repetition beyond the one each paper used, and the 379 runs-0 tacit logs, which share an early 3,158-char prompt.
- **Partial cells** are in bold above. There are no benign (no-attack) user-task runs.
- No stratum is excluded for zero attack successes (user rule). Most defended cells are expected at 0.

## 4. Expected outcome rates (L2 outcome sanity; whole-population tally H4–H6)

**Metric mapping.** Both papers' "Utility" is the mean of `utility` over the **attacked** logs of the cell (the denominators are 144/560/105/140). "Attack" is the count of `security == true` over the same logs (`security` true = injection goal reached; the fork's scripts say so too). Pre-pass logs (`attack_type` None) are excluded; their `security` is the benign constant. Incomplete logs (no outcome keys) are excluded from numerator and denominator, as the fork's scripts drop them, and are reported separately.

**Aggregation.** For TACIT, test (A) each single run root and (B) a latest-`evaluation_timestamp`-wins merge across `runs-*` per model × suite. For LACUNA, use the merge of lacuna-runs-0 and -1 deduped by (attack, UT, IT), latest wins (the `render_lacuna_results.py` rule).

| Arm | Paper utility (k/n; k back-computed) | Paper attacks | Logs available | Table |
|---|---|---|---|---|
| gemini TACIT banking | 56.94% (82/144) | 0/144 | runs-0, 2, 3, 4 | 2603.00991v2 T4 |
| gemini TACIT workspace | 50.54% (283/560) | 0/574 printed | runs-2 (full); 3, 4 partial | T4 |
| gemini TACIT slack | 40.00% (42/105) | 0/105 | runs-2, 3, 4 | T4 |
| gemini TACIT travel | 64.29% (90/140) | 0/140 | runs-2, 3, 4 | T4 |
| o4 TACIT banking | 59.03% (85/144) | 0/144 | runs-0..4 | T4 |
| o4 TACIT workspace | 52.86% (296/560) | 0/574 printed | runs-2, 3, 4 | T4 |
| o4 TACIT slack | 47.62% (50/105) | 0/105 | runs-2, 3, 4 | T4 |
| o4 TACIT travel | 68.57% (96/140) | 1/140 | runs-2, 3, 4 | T4 |
| gemini LACUNA banking | 63.19% (91/144) | 0/144 | lacuna-0, -1 (merge) | 2605.28617v1 T3 |
| gemini LACUNA workspace | 56.25% (315/560) | 4/560 | **none** | T3 (unbacked) |
| gemini LACUNA slack | 42.86% (45/105) | 2/105 | lacuna-1 | T3 |
| gemini LACUNA travel | 63.57% (89/140) | 1/140 | lacuna-1 | T3 |
| o4 LACUNA banking | 65.97% (95/144) | 0/144 | lacuna-0, -1 (merge) | T3 |
| o4 LACUNA workspace | 55.54% (311/560) | 0/560 | lacuna-0 | T3 |
| o4 LACUNA slack | 49.52% (52/105) | 1/105 | lacuna-1 | T3 |
| o4 LACUNA travel | 71.43% (100/140) | 0/140 | lacuna-1 | T3 |
| nano, claude, gpt-5.4, deepseek, native arms | – | – | see §3 | none: Wilson 95% only |

At about 5 sampled logs per stratum, no L2 cell reaches n ≥ 20. L2 rates are therefore reported with Wilson intervals. The comparison of record is the whole-population raw tally (H4–H6), which reads raw `utility`/`security` only and needs no mapping. The CaMeL rows are context only.

## 5. Known quirks (expected-known)

| Id / source | Expected | Reference |
|---|---|---|
| `agentdojo.benign_security_constant` | 414 files; origin rule applied 409 | profile `observed`; census |
| `agentdojo.injection_task_as_user_task_prepass` | 414 files | profile; census |
| `agentdojo.args_mutated_in_place` | 8,369 files | profile; census |
| `agentdojo.placeholder_args_never_injection_evidence` | 21,627 present, all null | profile; census |
| `agentdojo.silent_rerun_last_pass_only` | 355 null-final logs (10c 359; reconcile explains 4) | profile; reconcile |
| `agentdojo.unexecuted_trailing_calls` | 46 calls in 42 logs | profile; census |
| `agentdojo.incomplete_run` | 15 files (12 `incomplete_run` + 3 empty), 0 null-outcome | profile; census |
| `agentdojo.empty_messages_without_outcome` | 3 (runs-1 nano workspace IT0, runs-2 nano travel IT0, runs-4 deepseek workspace IT0: all pre-pass) | profile; census samples |
| `agentdojo.package_version_not_code_identity` | 0 without version; D rules via `_unverified` twins | profile; D-24 |
| `pipeline_name_mismatch` | 685 = all runs-0 logs (underscore form) | census; identity table |
| System prompts | 24 digests. Default `a021a92b…` (469) in the 306 native logs. `3e374aee…` (3,158) in 379 (= runs-0 tacit). 3 empty logs have none | phase-10c census |
| Extra keys | kept verbatim in `ext.agentdojo.extra`; `*.secure-channel.txt` registered, not mapped | profile |
| Tool names | eval_scala 21,030. Direct AgentDojo names (566 calls) are expected mostly in the 306 native logs. Facade-style names (`getChannels` 17, `getMostRecentTransactions` 8, `getCurrentDay` 3, `getUnreadEmails` 1, `eval_aleval_scala` 1, `run` 1) are expected to fail. Tool errors total 42 | phase-10c census |
| `artefacts.toml` | **No entry scopes `linyxus-agentdojo`.** The generic entries `benign_security_constant`, `injection_task_as_user`, `silent_rerun`, `max_iters_pending`, `validity_defects`, `payload_not_reaching_agent` apply by analogy only | `artefacts.toml` |
| DECISIONS | No linyxus-specific decision. D-24 (unverified twins) and D-100 (trial) apply | DECISIONS; phase10d README |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2. Selection: include globs; secure-channel txt excluded with its code; context artefacts LICENSE, README.md, pyproject.toml, CITATION.bib |
| L1-02 strict parse | yes | 9,068 logs; expect 0 defects (census parse ok 9,069) |
| L1-03 encodings | yes | Scala code in `eval_scala` args contains legitimate escapes and braces; do not count Scala string escapes in args as residues. #214 `\uXXXX` in tool content: count. Non-ASCII benchmark text (e.g. "Café") is legitimate |
| L1-04 duplicates | yes | Within part across the repeated run sets and the two lacuna rounds; cross-corpus with `l1_xdup.py` (tacit-exp is not a separate registry part) |
| L1-05 arm coverage | yes | §3 table, 52 strata, plus the per-run-root tally for H4–H6 |
| L1-06 secrets / account paths | yes | Counts and pointers only. Benchmark tokens and codes (password-reset URLs, "463820") are benchmark content. Elevated risk: Scala compiler/runtime diagnostics in tool results (H11) |
| L1-07 timestamps | partly | Presence, parse, naive zone, range, and order against the commits that added each root. Within-unit monotonicity n/a (one timestamp per log) |
| L1-08 degenerate | yes | 3 empty, 15 incomplete, 355 null-final, 0 run errors |
| L2 import / validate / recompute / determinism | yes | Queue, `--cpu 2`, two `--jobs` values |
| L2 A2 / A3 classes | yes | Expect only the census register codes |
| L2 evidence classes | yes | D rules only through `_unverified` twins (`verified_code = []`) |
| L2 degenerate / adapter_defect | yes | Expect 0 adapter_defect, including the facade-style tool names |
| L2 identity | yes | Model = OpenRouter route from the dir (class I). Defence from the table: `tacit` for every `-tacit` dir **including the 1,700 lacuna-runs logs** (H8) |
| L2 redaction | yes | Expect no account path in AER/SEM/PROV |
| L2 withholding | conditional | Applies only if L1-06 hits |
| L2 outcome sanity | Wilson only per stratum | Verdicts come from the population tally (H4–H6) |
| Delta since E2 | no | Not in FA/E2 |

## 7. Hypotheses (falsifiable; thresholds fixed now)

| Id | Expectation | Falsified if | Class if falsified |
|---|---|---|---|
| H1 | L1 selects exactly 9,068 logs with the per-root/per-cell counts of §3; 8,383 txt excluded; every txt has its log | any count differs by ≥ 1 | source-defect or mapping-defect |
| H2 | All logs parse strictly (0 duplicate keys, NaN, BOM, invalid UTF-8, truncation) | any hit | source-defect |
| H3 | The 15 incomplete + 3 empty logs: the empty ones are the 3 pre-pass logs of §5. The 11 logs that have a secure-channel txt but no `tacit_secure_output` key are all among these 18 | a mismatch | source-defect, S3 |
| H4 | TACIT Table 4: for each of the 8 model × suite cells, at least one single root (A) or the merge (B) reproduces utility k and attack k within ±1 run. One root reproduces all 4 suites of a model where it is complete | no root/merge within ±1 for a cell (> 0.7 pp banking); a gap > 15 pp → S1 candidate | documentation-mismatch, S2 |
| H5 | LACUNA Table 3: the latest-wins merge of lacuna-runs-0/-1 reproduces the 7 backed cells (utility and attacks) within ±1 run | any cell off by > 1 run | documentation-mismatch, S2 |
| H6 | gemini-2.5-pro LACUNA workspace: 0 logs in the release | ≥ 1 log found | refutes the lead |
| H7 | Attacked `security == true` totals 148 (= 557 − 409 constant pre-pass), and the reported defended TACIT/LACUNA arms each have ≤ 4 | another total, or a defended reported arm > 4 in the matching root | documentation-mismatch, S2 |
| H8 | L2 maps all lacuna-runs logs to defence `tacit` (as the table says), with no LACUNA marker. This is expected to become a finding: identity incomplete or mismatched with Paper 2 | L2 shows a distinct defence for lacuna-runs | documentation-mismatch in our table/profile, S2 |
| H9 | Timestamps: runs-* (except deepseek) all in April 2026; lacuna-runs-0 ≤ 2026-05-22T19:56Z and lacuna-runs-1 ≤ 2026-05-24T10:56Z (commit times, naive vs UTC with ±14 h slack); deepseek and lacuna logs carry the `model` key (1,701) | a log after its adding commit, or `model` outside these 1,701 | source-defect, S3 |
| H10 | Byte-identical log pairs = 0. Identical attacked-trajectory fingerprints across repetitions ≤ 1% of 8,654. Cross-corpus overlap = 0 | above either | documentation-mismatch (copied runs), S2 |
| H11 | 0 provider keys (`sk-or-`, `sk-`, bearer). Account paths (`/Users/`, `/home/`, `C:\Users\`) = 0. **Risk noted**: TACIT compiler diagnostics may carry them | any hit | security finding, reported to the orchestrator at once; L2 redaction must remove them |
| H12 | Mapped tool activities in `-tacit` logs are `eval_scala` (+ the few facade-style names). `backend_tool_traces` produce 0 activities and stay in `ext.agentdojo.extra` | backend calls mapped as executions without a rule | mapping-defect (invariant 2), S1 |
| H13 | L2 on ≈ 252 units: every stage ok; 0 failing checks; 0 adapter_defect; `recompute --dry-run` 0 differences; second import byte-identical; identity resolved 100% | any failure | mapping-defect |
| H14 | `pipeline_name_mismatch` only in runs-0 (685); never used to change identity | elsewhere, or identity follows `pipeline_name` | mapping-defect |
| H15 | (exploratory) The L2 sample rates of the 15 backed paper cells lie inside the README §4 gap rule | gap rule fires | investigate identity/outcome mapping |

## 8. Discrepancy leads carried to the dossier

These are the defence identity of the lacuna-runs (H8); the missing paper identifiers in the profile (two papers, Paper 1's AgentDojo results only in v2); the gemini LACUNA workspace arm, which is reported but not released (H6); the TACIT 574 vs 560 workspace denominator (pre-pass in the printed n is a hypothesis only: Table 4 prints 0/574 for the cited CaMeL rows too); the unstated choice of run set (H4); reruns overwritten in git history (2026-04-17 commit `32d9ff74` modifies 91 logs and 60 secure-channel txt, so 91 earlier attempts are observable only in history; **corrected by fact-check**: the ≥ 297 removals in `aaa71a91` are the runs → runs-3 move, not lost data); harness drift (24 prompts, unversioned TACIT jar, a retry change after the last run); outcome evidence outside the mapped trace (`backend_tool_traces`, the secure channel; H12); no benign baseline, with the papers comparing utility under attack against cited CaMeL numbers; account-path risk (H11); and `artefacts.toml` scopes that omit this source. Proposed text-only routes: a profile `[source].paper` update and a lacuna defence row or marker in the identity table, both via the orchestrator to the agentdojo family owner.

## Fact-check (2026-10-14, desk only; no raw data read)

Checked against the cited sources:

- **Paper numbers (§4).** All 16 rows re-opened. TACIT: [arXiv:2603.00991v2](https://arxiv.org/html/2603.00991v2) App. E.2 Table 4 (v1 of 2026-03-01 has no stock-AgentDojo results; v2 is 2026-05-07; CC BY 4.0; related DOI 10.1145/3786335.3813127). LACUNA: [arXiv:2605.28617v1](https://arxiv.org/html/2605.28617v1) Sec. 7.4 Table 3, whose TACIT rows are credited to Odersky et al. 2026. Percentages and attack counts match. **Correction:** both papers print utility as a percentage only. The k in "k/n" is back-computed (each fits one k for the attacked n), so the column header is marked.
- **574 vs 560.** Confirmed that Table 4 prints 0/574 for workspace. It does so for the CaMeL rows too, which are cited from Debenedetti et al. 2025, while LACUNA Table 3 prints 0/560 for every row. **Correction:** the "560 + 14 pre-pass" explanation is now marked as a hypothesis.
- **Pin and record.** `698d7ff2` is still the HEAD of `lacuna-exp` (2026-05-24T13:32:16Z). The trees API listing (paths and sizes only) gives 17,656 blobs / 196,887,263 bytes, which equals the profile. It also gives 9,068 logs (191,704,610 bytes) and 8,383 secure-channel txt files, each with its log. The 379 logs without a txt are all in runs-0. Every cell of §3, the per-model totals, 8,654 attacked / 414 pre-pass, 52 strata and Σ min(5, n) = 252 are reproduced from the same listing. All 7,367 tacit-exp logs are present with the same blob ids, and 2,934 of them moved runs/ → runs-4. Zenodo and HF: 0 hits. The fork has no PRs, and Linyxus has no upstream issues.
- **Licence.** The LICENSE at the pin is MIT. Its blob `006aed0b` is identical to upstream's (© 2024 Debenedetti et al.). Confirmed.
- **Scripts.** Confirmed that `render_lacuna_results.py` dedups by (attack_type, user_task_id, injection_task_id), keeps the latest `evaluation_timestamp`, and skips pre-pass. Confirmed that `render_run_results.py` reads one root.
- **Upstream issues.** #95, #213, #181, #168 and #214 exist with the cited topics.
- **Git history (lead "reruns overwritten").** **Correction:** `32d9ff74` has a full file list (281 files). It modifies 151 files: 91 logs and 60 txt. None of the 91 earlier log blobs is at the pin. `4b38d5a8` ("rename") adds files under runs-3, and `aaa71a91` removes ≥ 297 files from runs/. All 149 removed `.json` in that listing are unchanged blobs under runs-3 at the pin, so the removals are the move, not superseded reruns.
- **Unverifiable here.** The census-derived tallies (utility/security totals, 8,372 `tacit_secure_output`, 21,030 `eval_scala`, 24 prompt digests) come from phase-10c summaries that are not in the repository and were not re-opened. The phase-10d census `units`, `variants` and `files_by_issue_code`, and the profile `observed` counts, were confirmed.

