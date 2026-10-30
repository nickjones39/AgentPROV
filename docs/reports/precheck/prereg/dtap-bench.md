# Pre-registration: `dtap-bench`

| | |
|---|---|
| Corpus | `dtap-bench` (family `dtap`, profile `dtap-bench` v1, dialect/mapper `dtap.trajectory`, semantics `dtap.tools@1`, catalogue `dtap` v1) |
| Parts | `head`: HF `AI-Secure/DTap-Bench-Agent-Trajectories` @ `836caf2fdd78b888ddd14fb62dc038e932e17898` (runs, primary). Context: HF `AI-Secure/DecodingTrust-Agent-Platform` @ `a3edc9b7c48cbf16c2ea9c18990fb94c7494dd04` (6,682 `config.yaml`). Plus 2 pinned LFS objects |
| Wave | 5. This is a full pre-check. The corpus was not in FA or E2, and the registry status is `planned`, so no corpus is stored and there is no delta since E2 |
| Code commit | `065b0d36` or later |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Inputs: our own prior reports and desk research only (`data/dtap-bench/research.json`). Prior reports used: `sources/dtap.md` and `verify/dtap.md` (AgentPROV/investigation), census JSON `phase10b/census/c01e`, `c04`, `c19`, `candidates/dtap-bench.md`, `analysis/dtap-sample-check.md`, the profile, `artefacts.toml`, `rates.toml`, D-26, D-28, D-29 (+ addendum), D-82 and D-182. No raw data was read and nothing new was computed from it |

## 1. Sources (details and URLs in `research.json`)

- **Paper.** arXiv:2605.04808 has a single version, v1, dated 2026-05-06; v2 returns 404. Section 6 gives Table 3 (ASR, indirect and direct, 8 rows × 14 domains), Table 4 (BSR, 9 rows) and Table 5 (ASR by injection vector). Appendix Tables 8–83 give, per domain, BSR, indirect ASR, direct ASR without red-teaming ("baseline") and direct ASR with red-teaming. **Overall is the unweighted mean of the 14 domain columns.** We verified this for all 25 rows of Tables 3–4 to within 0.06 pp (**corrected** from 0.05: 24 rows lie within 0.05 pp; Claude Code Sonnet-4.5 direct is 26.84 against 26.9). Each domain value is itself a mean over risk categories (the captions of Tables 8, 9 and 11).
- **Data record.** Both HF heads still equal our pins (API, 2026-10-14), and neither dataset has HF discussions. The runs card claims the "full collection" of trajectories, but its body is a copy of the task card. There is no Zenodo or Figshare record. The trajectories were first offered on decodingtrust-agent.com/benchmark (issue #11); that copy is not pinned.
- **Harness.** `AI-secure/DecodingTrust-Agent` (Apache-2.0, public since 2026-04-25, 35 public commits: 31 release syncs, 1 PR merge and 3 direct commits; **corrected** from "35 sync commits"). The SDK first appeared on PyPI on 2026-05-13 (0.1.0), after every run. No log records a harness version. Judge bugs in the public harness: #14, #21, #23 (open), #24 (open), #19.
- **Timeline.** The runs date from 2026-02-12 to 2026-05-05T03:53:41Z. The paper followed on 2026-05-06. The judges were re-judged on 2026-04-26. The 20 synthetic trajectories are dated 2026-05-12. The macOS and Windows logs were uploaded on 2026-07-01, which is also the pin date.
- **Licence.** Apache-2.0 per both cards, through the upstream LICENSE. Neither dataset has a LICENSE or NOTICE file. There is no use restriction, and our policy is include (D-29 item 10, option A).

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Files in the runs tree at the pin | 133,851 | profile pin note; census c01e `file_classes_total` |
| Trajectory-bearing JSON (units) | **67,808** = 64,110 `<TS>.json` + 3,590 `trajectory.json` + 99 `<TS>_N.json` + 8 `(1)` + 1 `partial_trajectory.json` | `tools/readme_corpora.toml` (67808, census); c01e |
| Parse as raw | 67,806; 2 are LFS pointers, resolved by the pinned LFS objects (D-29 item 4) | census §2.3; profile `lfs_object` pins |
| Not executions | 20 synthetic (`select.not_execution_artefact`); 8 `red_teaming_agent_*`; 122 screenshot pointers; README; `.gitattributes` | profile `[import] exclude`; D-29 item 1 |
| Judge files | 65,902 `judge_result.json`, plus 8 byte-identical `(1)` copies; 22 judge-only directories | census §4.2, §5 |
| Executions (derived) | 67,780 trajectory executions (67,808 − 20 − 8 dedup), less any byte-identical `_N`/plain pair (≥ 1 in the sample), plus ≤ 22 outcome-only judge-only units | D-29 items 3, 6, 7; sample check R01c |
| By split (all names) | benign 25,792; direct 16,958; indirect 18,330; direct_prompt 4,808; direct_no_attack 1,920 | c01e |
| By framework | claudesdk 15,245; googleadk 7,556; openaisdk 27,829; openclaw 17,178 | c01e |
| Steps | 1,609,274 (agent 834,985, tool 716,489, user 57,800) | census §3.2 |
| Integrity quirks | harness failures 47; empty trajectories 17; partial 1; judge errors 14; `audit_correction` 458; re-run directories 1,291 (1,828 surplus files) | profile quirks; census |
| Join tiers | A 62,419; B 2,899; C 1,693; missing 786; unparseable 9 | profile `dtap.join_tiers` |
| Paper design | 6,682 tasks: 2,806 benign, 1,878 direct, 1,998 indirect. Runs per task not stated | arXiv Sec. 6; Table 6 |
| L2 sample | **240 units**: stratum = framework/model/split (48 strata × 5). Domain is recorded per unit but is not a stratum: with domain the strata would exceed 300 (about 420) | README §4 rule |

## 3. Expected arms (L1-05 facets: framework × model × split × domain; risk category below)

Trajectory files per pair and split (census c01e, all names). In brackets: judge directories, which are the paper's unit.

| Pair | benign | direct | indirect | direct_prompt | direct_no_attack | In paper |
|---|---:|---:|---:|---:|---:|---|
| openaisdk gpt-5.1 | 2,041 [2,041] | 1,209 [1,191] | 1,232 [1,149] | 408 [400] | – | BSR only (Table 4); DTap-Red surrogate |
| openaisdk gpt-5.2 | 3,181 [2,806] | 1,916 [1,835] | 2,121 [1,969] | 500 | 240 | Tables 3–5 |
| openaisdk gpt-5.4 | 2,806 | 1,858 [1,836] | 2,072 [1,986] | 500 | 240 | Tables 3–5 |
| openaisdk gpt-oss-120b | 2,923 [2,804] | 1,857 [1,836] | 1,985 | 500 | 240 | Tables 3–5 |
| claudesdk claude-opus-4-6 | 2,807 [2,806] | 1,972 [1,836] | 1,994 [1,986] | 500 | 240 | appendix only |
| claudesdk claude-sonnet-4-5 | 2,961 [2,806] | 1,881 [1,836] | 2,150 [1,986] | 500 | 240 | Tables 3–5 ("Claude Code") |
| googleadk gemini-3-pro-preview | 2,806 | 1,892 [1,836] | 2,118 [1,984] | 500 | 240 | Tables 3–5 |
| openclaw claude-opus-4-6 | 2,854 [2,806] | 1,874 [1,836] | 1,986 | 500 | 240 | appendix only |
| openclaw gpt-5.2 | 2,813 [2,806] | 1,899 [1,836] | 2,072 [1,986] | 500 | 240 | Tables 3–5 |
| openclaw gpt-5.4 | 600 | 600 | 600 | 400 | – | finance and legal appendix only (Tables 62–65, 70–73) |

- **Domain coverage.** direct_prompt covers only finance (2,000), legal (2,008) and windows (800). direct_no_attack covers only medical (1,920). openclaw gpt-5.4 covers finance, legal and **one more domain** (200 per split) that no paper table reports. gpt-5.1 and openclaw gpt-5.4 have no windows direct_prompt.
- **Missing relative to the paper.**
  - The OpenClaw **GPT-5.5** and **DeepSeek-V4-Pro** rows (Tables 3–5) have no runs.
  - Direct-baseline arms (no red-teaming) are absent for 10 domains (**corrected** from 11; Tables 10, 15, 20, 25, 30, 35, 40, 45, 57, 77: workflow, CRM, CS, travel, code, browser, research, OS-FS, macOS, telecom).
  - Per pair, the direct judge directories number 1,836 against 1,878 tasks, and the indirect ones 1,986 against 1,998.
  - 93 configurations are referenced by no run.
- **Extra relative to the paper tables.** The gpt-5.1 attack runs; the third domain of openclaw gpt-5.4; the re-run attempts (1,828 surplus files). None of these is excluded for having no reported number or for having zero successes (user rule).

## 4. Expected outcome rates (comparison of record: the population judge tally; L2 sample: Wilson only)

**Mapping.** ASR = `attack_success` true / judged non-null, using the stored (effective, re-judged) value at the judge-file level. BSR = `task_success` true over benign judge files.

- The paper's Overall is a **macro** over domains (and, within a domain, over risk categories). The comparison is therefore made **per pair × split × domain** against the domain columns: micro rate within the domain and category-macro, both reported. The pair-level micro rate is reported only as context.
- Default rate exclusions (`rates.toml`): harness failure, unresolved re-run attempt, outcome-only, and `harness_default` judgement origins (`direct_prompt` `task_success`, benign `attack_success`).
- Gap rule (README §4): more than 15 pp on a cell with n ≥ 20, or a cell that a binomial 95% interval excludes by more than 5 pp.

| Pair | Paper indirect ASR | Census micro | Paper direct ASR | Census micro | Paper BSR | Census micro |
|---|---:|---:|---:|---:|---:|---:|
| openaisdk gpt-5.4 | 40.0 (T3) | 40.1 | 51.0 | 53.9 | 85.3 (T4) | 86.4 |
| openaisdk gpt-5.2 | 46.7 | 48.1 | 58.8 | 61.7 | 80.5 | 79.5 |
| openaisdk gpt-oss-120b | 28.5 | 31.7 | 46.5 | 52.7 | 36.2 | 40.3 |
| openaisdk gpt-5.1 | – | 60.4 | – | 79.6 | 78.7 | 73.3 |
| claudesdk sonnet-4-5 | 25.2 | 27.5 | 26.9 | 30.5 | 80.8 | 78.0 |
| googleadk gemini-3-pro | 55.7 | 56.5 | 47.9 | 51.1 | 87.0 | 88.3 |
| openclaw gpt-5.2 | 35.6 | 38.3 | 38.6 | 41.1 | 78.5 | 78.2 |
| claudesdk opus-4-6 | 8.2* | 8.1 | 22.1* | 25.1 | 86.5* | 82.3 |
| openclaw opus-4-6 | 10.7* | 11.8 | 21.7* | 24.6 | 86.0* | 84.5 |
| openclaw gpt-5.4 | fin 34.9 / legal 59.1 | 39.3 (3 domains) | 18.5 / 42.0 | 29.7 | 96.7 / 86.9 | 89.2 |

\* These are not paper numbers. They are our macro of the 14 appendix domain values; the per-domain values and table numbers are in `research.json` `paper_domain_values`.

**Baseline splits** (paper tables are per domain and need no macro):

| Pair | direct_prompt finance / legal / windows (T64 / T72 / T50) | Census direct_prompt (all 3 domains) | direct_no_attack medical (T82) | Census |
|---|---|---:|---:|---:|
| openaisdk gpt-5.4 | 0.0 / 3.5 / 20.0 | 41/500 | 15.1 | 14.6 |
| openaisdk gpt-5.2 | 0.0 / 5.0 / 17.5 | 38/500 | 27.9 | 27.9 |
| openaisdk gpt-oss-120b | 0.0 / 17.5 / 10.8 | 54/500 | 23.3 | 23.3 |
| claudesdk opus-4-6 | 0.0 / 1.5 / 20.0 | 36/500 | 12.9 | 12.9 |
| claudesdk sonnet-4-5 | 0.0 / 2.0 / 9.2 | 31/500 | 21.7 | 21.7 |
| googleadk gemini-3-pro | 2.5 / 24.0 / 15.0 | 84/500 | 19.6 | 19.6 |
| openclaw opus-4-6 | 0.0 / 3.0 / 13.3 | 41/500 | 14.2 | 14.2 |
| openclaw gpt-5.2 | 0.0 / 8.5 / 13.3 | 48/500 | 10.8 | 10.8 |
| openclaw gpt-5.4 | 0.0 / 5.0 / – | 10/400 | – | – |
| openaisdk gpt-5.1 | – | 21/400 | – | – |

With about 5 sampled units per stratum, no L2 cell reaches n ≥ 20, so the L2 sample yields Wilson intervals only (H16). The verdicts come from H6–H8 on the population tally. That tally reads raw judge fields and needs no mapping.

## 5. Known quirks (expected-known)

| Id / source | Expected | Reference |
|---|---|---|
| `dtap.art.synthetic_trajectory` | 20 files (claudesdk workflow indirect `financial-fraud`); not executions | profile quirk; D-29 item 1 |
| `dtap.art.harness_failure_judged` | 47 OpenClaw runs (15 task true, 32 false, 0 attack true) | D-29 item 2; `rates.toml` |
| `dtap.art.empty_trajectory` / `.judge_error` | 17 (googleadk 14, claudesdk 3) / 14 (Gemini 400, windows) | D-29 item 3 |
| `dtap.art.lfs_pointer_json` / `_png` | 2 (resolved by pinned objects) / 122 (excluded) | D-29 item 4 |
| `dtap.art.rejudged_results` | 458 (`h5_rejudge_20260426`; direct 179, indirect 279) | D-29 item 5 |
| `dtap.art.rerun_single_judge` | 1,291 directories, 1,828 surplus; judge linked by content or unresolved | D-29 item 6 |
| `dtap.art.copy_duplicate` / `.partial_trajectory` | 8 + 8 / 1 (`unverifiable`, D-82) | D-29 items 7–8 |
| `dtap.art.direct_prompt_constant_task_success` / `.control_attack_judged` | 4,800 constant true / 1,920 judged controls | D-29 item 9 |
| `dtap.art.config_join_drift`, `.config_missing_or_unparseable`, `.instruction_truncated_500`, `.goal_rewritten_at_eval`, `.goal_text_appended` | tiers B 2,899 / C 1,693; missing 786, unparseable 9; 7,353; 1,183; 1,826 | census §6 |
| `dtap.art.pairing_ambiguous_batch`, `.claudesdk_unknown_result_name`, `.no_call_ids` | 61,651 results in multi-call batches; 20,318 `unknown`; 501,228 calls | census §3.8 |
| `dtap.art.no_user_step`, `.python_repr_results`, `.injection_unobservable`, `.environment_payload_unobserved` | 10,154 files; 188,050 results; 3,533 of 6,162 indirect successes; 4,041 | census §3, §7 |
| `dtap.art.no_model_id`, `.naive_timestamp`, `.trace_id_not_unique`, `.task_id_not_unique`, `.event_times_not_recorded` | all files; 7,415 (googleadk); 517 shared values; 78 keys | census §3.5–3.6 |
| `dtap.art.source_truncation_marker` / `.secret_like_strings` | 54 files / 1,206 files (`unverified`) | artefacts.toml |
| Sample-check items N16–N18, Q1–Q4 | user-only runs; path/`task_info` domain spellings; utility true with no tool call; shared `raw:` variants accepted | `dtap-sample-check.md`; D-29 addendum |
| Secrets | include all, flag none; `env_vars` never in derived records (DT01) | D-29 item 10 |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2. Selection codes: synthetic, red-teaming and PNG files as `select.not_execution_artefact`; `(1)` copies as `dedup.collapsed`; the two LFS pointers resolved through the pins |
| L1-02 strict parse | yes | 67,808 trajectory files + 65,910 judge files. Expected: 0 duplicate keys, NaN, lone surrogates or BOMs; 2 `ingest.json.syntax` (raw LFS pointers); 8 red-teaming files of another schema. Context configs: 1 duplicate-key file (`crm/.../dangerous-actions/26`) |
| L1-03 encodings | yes | Literal `\n` and quote residues are **expected** in 188,050 Python-repr tool states (openaisdk 183,668); classify them by pointer before counting them as defects. Base64 images in about 477 files. Count U+FFFD and mojibake without prior |
| L1-04 duplicates | yes | Within the part: 8 + 8 `(1)` copies; ≥ 1 `_N`/plain identical pair; identical canned one-message runs (sample: one group of 10). Across corpora: expect 0 (`l1_xdup.py`) |
| L1-05 arm coverage | yes | §3 (48 pair × split strata; domain and risk category as sub-facets) |
| L1-06 secrets / account paths | yes | Counts and pointers only. 1,206 secret-like files; 1,443 `(token:` files. Home-directory strings in tool content (sample U14), including one account name matching a paper author: count by pointer class, harness field versus tool content |
| L1-07 timestamps | yes | 60,371 aware with microseconds; 20 aware (synthetic); 7,415 naive (googleadk). Range 2026-02-12T21:45:14Z..2026-05-05T03:53:41Z; synthetic runs 2026-05-12. The timestamp is the run end. No per-step times |
| L1-08 degenerate | yes | 17 empty; 47 error-only (OpenClaw); 1 partial; user-only runs; `agent_final_response` null in 558 |
| L2 import / validate / recompute / determinism | yes | Through `tools/dtap/import_dtap.py` tree classes (runs + tasks + LFS) in a scratch corpus via the queue at `--cpu 2`, with a second import at different `--jobs` |
| L2 A2 / A3 classes, evidence classes | yes | Core holds O and D, no I; the inference bundle holds I only; assessment I/D/O. Completeness `unverifiable` for runs with an agent turn and `verified_complete` for runs without (D-29 addendum Q2) |
| L2 identity | yes | Framework and model from the path in 100% of units. Never from free-text mentions |
| L2 redaction | yes | DT01: no `env_vars` value in derived records, except values the run's own raw holds. Account paths: see H11 |
| L2 withholding | inert | Option A (D-29 item 10). No withheld executions expected |
| L2 outcome sanity | partial | Wilson only on the sample; the verdicts come from the population tally (H6–H8) |
| Delta since E2 | no | Not in FA or E2. The movement since the 2026-10-12 sample check is in §8 |

## 7. Hypotheses (falsifiable; thresholds fixed now)

| Id | Expectation | Falsified if | Class if falsified |
|---|---|---|---|
| H1 | L1 counts equal §2: 67,808 trajectory-bearing files, the per pair × split counts of §3, 65,902 judges, 22 judge-only directories | any count differs by ≥ 1 | census drift (analysis-artefact) or source-defect |
| H2 | Strict parse: 0 duplicate keys, NaN, BOM, lone surrogates or invalid UTF-8 in 67,806 + 65,910 files; exactly 2 raw syntax rejects; both LFS objects verify against their sha256 | any other hit, or an LFS mismatch | source-defect (S2) |
| H3 | Paper rows OpenClaw GPT-5.5 and DeepSeek-V4-Pro have **0** runs; no model directory other than the 7 models of §3 | any run of either model, or another model directory | documentation-mismatch (refutes the lead) |
| H4 | Per pair, judge directories are 1,836 direct and 1,986 indirect (gpt-5.1: 1,191 / 1,149; openclaw gpt-5.4: 600 / 600), short of the paper's 1,878 / 1,998 | the counts reach the paper's task counts | – (refutes the lead) |
| H5 | openclaw gpt-5.4 covers exactly 3 domains, finance and legal among them; the third domain has 200 per split | other coverage | documentation-mismatch, S3 |
| H6 | Per pair × split × domain with n ≥ 20 judges, the population tally lies within 15 pp of the paper domain value (Table 3/4 for the 7 main pairs; appendix tables for the 3 others) in ≥ 90% of cells | > 10% of cells breach 15 pp, or any breach > 30 pp | documentation-mismatch, S2 (S1 if > 30 pp) |
| H7 | Medical direct_no_attack reproduces Table 82 within ±1 run per pair (8 pairs; gpt-5.4 may differ by ≤ 2 runs, consistent with 29 versus 30 tasks per category) | > 1 run off (> 2 for gpt-5.4) | mapping or tally error (analysis-artefact first) |
| H8 | direct_prompt finance ASR ≤ 5% (≤ 10/200) for every pair, matching Table 64 (all 0.0, Gemini 2.5) | any pair > 5% | documentation-mismatch, S2 (census excess lead) |
| H9 | The paper used the stored (re-judged) values: for the 458 corrected judges, switching to `original_attack_success` moves the per-domain gaps of H6 away from the paper in the majority of affected cells | the originals fit better | documentation-mismatch, S3 |
| H10 | Judge metadata contradict the paper's no-LLM-judge statement: ≥ 1 judge file carries `llm_judge`/`llm_model` or `gpt_model` keys (expected ≥ 458 and about 1,734) | 0 such files | – (refutes the lead) |
| H11 | Account-path strings occur only in tool output or agent content (benchmark and model content, D-182: not redacted), never in a harness-written field (`traj_info`, `debug`, `task_info`, `metadata`) | any account path in a harness field, or any in an AER/SEM/PROV field outside verbatim content | security finding (report at once), S1 |
| H12 | Public-harness judge bugs absent from the released judges: (a) 0 customer-service judges with the "No judge_tool set" error (#14); (b) Delete-sensitive-files indirect ASR varies by pair as in Table 29 (17.6–100%) and is not ≥ 90% for every pair (#21) | (a) ≥ 1 such judge; (b) uniform ≥ 90% | source-defect, S2 |
| H13 | The 12 legal indirect tasks of issue #23 show ASR ≥ 90% across pairs; the self-matching judge applies to the released judgements | ASR < 90% over those tasks | if confirmed: source-defect (judge false positive), S2, proposed `artefacts.toml` entry |
| H14 | `os-filesystem/malicious/indirect/unauthorized-access-and-illegal-interception/52` has `task_success` false in ≥ 90% of its runs across pairs (issue #24: another task's judge) | < 90% false | – (refutes the lead); if confirmed, S3 |
| H15 | Free-text `claude-sonnet-4-20250514` mentions (237 files) are in tool, user or `task_info` content, not in claudesdk sonnet-4-5 agent self-reports | > 10 agent-step mentions inside claudesdk sonnet-4-5 runs | documentation-mismatch (model identity), S2 |
| H16 | L2 on 240 units: every stage ok, 0 `adapter_defect`, determinism byte-identical, `recompute --dry-run` 0 differences, identity 100%, 0 `worker.limit.rss` failures (cap raised after the sample check) | any failure | mapping-defect (RSS failure: known issue, S3) |
| H17 | Timestamps: 0 after 2026-05-05T03:53:41Z except the 20 synthetic runs (2026-05-12); 0 after the pin date 2026-07-01 | any other | source-defect, S3 |
| H18 | 0 identical-trajectory groups across different pairs, except degenerate canned runs (≤ 3 steps) | a non-degenerate group spanning pairs | documentation-mismatch (relabelled runs), S2 |

Rule: no stratum is excluded for zero attack successes or for having no paper number.

## 8. Expected movement since the protocol-v1 sample check (2026-10-12, `2c95a5b`, 500 runs)

There is no E2 delta. Against the sample check: the safety net leaves 0 findings unclassified (was 1,229; b1). There are no P07 media-type variants of auxiliary artefacts (b2; every DTap AER digest moved). `dtap.tools@1` labels 99.88% of tool calls (was 18.1%; follow-up item 4). The 2 claudesdk `worker.limit.rss` failures should no longer occur (prov RSS cap; AGENTS.md phase 12b). The HF dataset pins can now be fetched and verified (phase 12b). No byte expectation is carried over from the sample: it was a scratch corpus.

## 9. Fact-check (adversarial, 2026-10-14)

Re-opened every cited source; no raw data read. Checked:

- **Paper.** arXiv API lists one version (v1, 2026-05-06T11:59:48Z, "279 pages, 148 figures"); `abs/2605.04808v2` returns 404. Both HF cards carry the tag `arxiv:2605.04808`. Re-parsed the v1 HTML tables (https://arxiv.org/html/2605.04808v1): every Table 3 and Table 4 value in §4 matches (right table, arm, metric). All 465 per-domain values in `research.json` `paper_domain_values` equal the Overall column of the cited appendix table (Tables 8–83, incl. "Claude Code SDK" rows in Tables 75–78 and 81). The starred Opus macros recompute to 8.2 / 22.1 / 86.5 and 10.7 / 21.7 / 86.0. Tables 62–65 and 70–73 give OpenClaw GPT-5.4 96.7/86.9, 34.9/59.1, 18.5/42.0, 0.0/5.0; OpenClaw GPT-5.4 appears in no other table, and OpenClaw GPT-5.5 / DeepSeek-V4-Pro only in Tables 3–5. Tables 64, 72, 50 and 82 match the baseline table. Table 82 GPT-5.4 values are multiples of 1/29 (H7 note holds). Table 29 Delete-sensitive-files spans 17.6–100 (H12b). Table 6: 6,682 = 2,806 + 1,878 + 1,998; the task counts are in Sec. 6.1 and A.1. Judge statements are in Sec. 4.2 and A.3; GPT-5.1 is named as surrogate with a 10-iteration budget; GPT-5.1 rows exist only in BSR tables.
- **Corrected.** (1) Overall = unweighted domain mean holds to 0.06 pp, not 0.05 pp. (2) Direct-baseline arms missing for 10 domains, not 11. (3) The harness repo's 35 commits are not all syncs.
- **Expected counts.** Census `c01e` reproduces 133,851 files, 67,808 = 64,110 + 3,590 + 99 + 8 + 1, the split and framework totals, every pair × split count of §3 and the 65,902 judge files with the bracketed per-pair judge counts; `c19` reproduces every census micro rate of §4 and the 458 re-judged (direct 179, indirect 279). The direct_prompt excess over the weighted paper tables holds for 8 of 9 pairs (openclaw gpt-5.4 exactly 10/400). The `gpt_*` medical attribution (1,734 = 699 + 1,035 key sets) rests on `sources/dtap.md` only.
- **Pin and record.** HF API: runs sha `836caf2f…` (lastModified 2026-07-01T04:46:10Z, usedStorage 39,087,617, not gated), tasks sha `a3edc9b7…` (27,567 files); commits 170 and 57 with the stated date ranges and pre-pin commits; card sha256 `2a168915…`, "full collection" claim and `*/benign/**/config.yaml` config confirmed; no discussions. Both LFS objects match the profile pins (oid and size via HF paths-info).
- **Licence.** GitHub SPDX Apache-2.0, LICENSE added in `e0e38455` (2026-04-25), blob `261eeb9e`; no LICENSE/NOTICE in either HF dataset (404); PyPI 0.1.0 on 2026-05-13, latest 0.2.12 on 2026-06-18.
- **Issues.** #11, #14 (fixed `d4750e48`), #19, #21 (17 judges; fixed 2026-06-13), #23 (open; 12 tasks listed), #24 (open; os-filesystem indirect/52 carries the os-filesystem-190 judge) and commit `c6a80fb6` (trajectory-enabled-judge sync) confirmed as described.
- **Not verifiable from desk sources.** Table 50 implying about 120 Windows baseline tasks per pair (the values are consistent with 20 per category but do not fix n). The paper's own text names "OpenClaw + GPT-5.1" for the workflow domain, but no table has such a row; recorded as a paper-internal inconsistency, not a data expectation.
