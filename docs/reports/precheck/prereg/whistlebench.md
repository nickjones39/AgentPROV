# Pre-registration: `whistlebench`

| | |
|---|---|
| Corpus | `whistlebench` (family `inspect`, profile `whistlebench` v1, dialect/mapper `inspect.eval`, variant `v2`, `no_attack`) |
| Parts | `final-runs` (only part) |
| Wave | 4 (first examination; not in FA or E2) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: our prior reports (phase-10f census, trial and second import, regen-batch items 16/25/28, core review D), the profile, the registry, `artefacts.toml`, DECISIONS (D-147, D-150..D-156, D-372, D-374, D-375), and desk research (`data/whistlebench/research.json`). Paper numbers were read from the geometry of the paper's figure SVGs. Nothing here was computed from log contents. |
| Method | [`../README.md`](../README.md) |

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Repository | [legobridge/whistlebench](https://github.com/legobridge/whistlebench), MIT (Copyright 2025 Kushal Agrawal, Guido Bergman, Frank Xiao; the licence text grants rights to "software and associated documentation files", so its application to the logs is by repository scope, with no separate data licence); 4 commits, 0 issues, 0 PRs, 0 releases | GitHub API |
| Pin | `9c27637c3cf6dfb2c0d5801c7f3d91358cb587bc`, 2025-11-27 = **current head**. All logs and code arrive in the squashed `71688cd9` "Initial public release" (2025-11-18); the 3 later commits change README only | GitHub commits API |
| Paper | arXiv [2511.17085](https://arxiv.org/abs/2511.17085v3) (Agrawal, Xiao, Bergman, Cooper Stickland), v1 2025-11-21, v2 2025-12-27, v3 2026-04-23; CC BY 4.0. Text edits only (affiliation, one sentence in 3.2); **all figure SVGs byte-identical v1-v3**. Results only as bar charts | arXiv abs/html |
| Data record | none outside git (Zenodo, HF: 0 hits). Tree `final_runs/` at the pin: 223 blobs, 523,183,391 B = profile pin | git trees API |
| Harness | Inspect AI 0.3.130 (161 logs) and 0.3.134.dev31+geb46eef8 (23 logs, awareness only). **Task `high_agency` (176 logs)**: `react` agent with `Submit`, `message_limit=30`, `eval_set` epochs 50, `retry_on_error=10`, reasoning effort medium; judge `openai/gpt-5` (default `grader_model`), whistleblowing judge called only after an email or an outside write. **[corrected, fact-check]** The 8 SnitchBench logs come from a different task, `high_agency_deliberation_awareness` in `highagency/snitchbench/tasks.py` at the pin: `message_limit=15`, `AgentSubmit` without a name (Inspect default `submit`), tools `write_logs` + `send_email`, default `grader_model` **`openai/gpt-4.1`**, snitching scorers + `deliberation_analysis`; no driver at the pin calls it, so its eval settings (epochs, reasoning effort, grader) are not documented by code | `whistlebench/eval.py`, `tasks.py`, `scorers.py`; `snitchbench/tasks.py`, `snitchbench/eval.py` at the pin |
| Run dates | eval starts 2025-09-28 .. 2025-10-24 (log names); offsets -05:00 (consistent with America/Chicago CDT; **[corrected]** the paper names America/Chicago only inside the scenario system prompt, not as the run machine's zone), -04:00 (1_responsibility 2025-10-14 batch), -07:00 (awareness_blackbox) | census per-log paths |
| Scope | unsanctioned whistleblowing = unauthorised agent action; no attacker, no defence (D-147) | profile, DECISIONS |

## 2. Expected counts (part `final-runs`)

| Quantity | Expected | Source |
|---|---:|---|
| Tree entries under `final_runs/` | 223 (523,183,391 B) | profile `expected_files/bytes`; git trees API |
| Selected `.eval` (`final_runs/**/*.eval`) | 184 (522,052,717 B; 1,420,537..4,717,315 B; 184 distinct blob SHAs) | census; tree |
| Not selected (context artefacts) | 39 = 19 `.csv` + 9 `logs.json` + 2 `eval-set.json` + 9 `.eval-set-id` (`all_models` has no `logs.json`/`.eval-set-id`) | tree; profile `context_artefacts` |
| Units / executions | 9,200 samples = 9,200 executions; 50 per log | registry (`readme_corpora.toml` count 9200, census `/samples`); trial mapped/derived/validated 9,200 |
| Producers | 0.3.130: 161 logs / 8,050 samples; 0.3.134.dev31+geb46eef8: 23 / 1,150 | census; regen-batch item 16 |
| Log status / version | 184 `success` / 184 v2 | census |
| Sample errors / limits | 0 errors; 12 limits (11 `message`, 1 `operator`) | census, profile quirk |

| Experiment (dir) | Logs | Samples | Models (logs each) | Producer |
|---|---:|---:|---|---|
| `0_baseline` | 12 | 600 | Opus 4.1, Gemini 2.5 Pro, Grok 4 (4) | 0.3.130 |
| `0_baseline_gpt_4.1_grader` | 12 | 600 | same 3 (4) | 0.3.130 |
| `1_responsibility` | 24 | 1,200 | same 3 (8; batches 2025-10-05 and 2025-10-14, 4 each) | 0.3.130 |
| `2_boldness` | 36 | 1,800 | same 3 (12) | 0.3.130 |
| `3_detailed_instructions` | 12 | 600 | same 3 (4) | 0.3.130 |
| `4_distractor_docs` | 12 | 600 | same 3 (4) | 0.3.130 |
| `5_distractor_tools` | 12 | 600 | same 3 (4) | 0.3.130 |
| `all_models` | 36 | 1,800 | 9 models (4 each; Gemini/Grok/Llama from 3-4 batches) | 0.3.130 |
| `awareness_blackbox/habench_summarization` | 20 | 1,000 | Opus **4** (`claude-opus-4-20250514`), Gemini, Grok, Qwen3-32B (5 each) | 0.3.134 |
| `awareness_blackbox/snitchbench` | 8 | 400 | Opus 4, Sonnet 4, GPT-4.1, GPT-5, Qwen3-max (0.3.130); Gemini, Grok, Qwen3-32B (0.3.134) | mixed |
| **Total** | **184** | **9,200** | 11 agent models | |

## 3. Expected arms

| Facet | Values | Expected missing / extra |
|---|---|---|
| Experiment | 10 dirs of section 2 | none extra |
| Agent model | 11 ids (census); paper Table 2 lists 9 | extra vs paper: Qwen3-32B (Fig 7 only), Qwen3-max (no figure) |
| Storyline | autonomous_vehicles, food_safety, medical_devices, mining (one log each per model and condition) | habench_summarization: a 5th log per model, probably `pharma` (in `types.py`, not in the paper) |
| Condition (`task_args.params`) | responsibility (summarization; pii_detection, ediscovery_review in 1_responsibility); boldness (medium; none/low/high in 2_boldness; **high in all_models**); workflow details (on in 3_); distractor docs (off in 4_ and **all_models**); distractor tools (on in 5_); deliberation (on in awareness_blackbox) | missing: translation responsibility, harmful tools (README/`types.py` only) |
| Judge (`grader_model`) | `openai/gpt-5`; `openai/gpt-4.1` in 0_baseline_gpt_4.1_grader; SnitchBench logs: not documented (task default `openai/gpt-4.1`) **[corrected]** | missing: Claude Sonnet 4 judge replication (paper 3.4) |
| Attack / defence | none (`no_attack`) | n/a |

L2 strata = (experiment, model) (`tools/precheck/l1_families.py` STRATA): 42 strata x 5 = **210 sampled units**.

## 4. Expected outcome rates (comparison targets)

Metric mapping (pinned `scorers.py`; census score names): whistleblowing rate = share of samples with
`scores.email_whistleblowing.value.<gov|media|internal>_whistleblowing == "C"`; refusal = `scores.refusal.value == "C"`;
evaluation awareness / hypothetical recognition = `scores.test_awareness.value.<key> == "C"`; deliberation =
`scores.deliberation_analysis.value == "C"`. Paper bars pool 4 storylines x 50 epochs (n = 200; Fig 7: n = 50 per
storyline log). Counts below are bar height x N, read from the SVG geometry (every bar an exact multiple of 1/200).

**Fig 2 / 3 (`all_models`, boldness high, distractor docs off), counts of 200**

| Model | Gov | Media | Internal | Refusal | Eval aware | Hypothetical |
|---|---:|---:|---:|---:|---:|---:|
| Claude Opus 4 | 47 | 33 | 0 | 4 | 0 | 0 |
| Claude Opus 4.1 | 116 | 102 | 0 | 9 | 0 | 0 |
| Claude Sonnet 4 | 5 | 2 | 1 | 109 | 2 | 4 |
| Claude Sonnet 4.5 | 137 | 38 | 16 | 197 | 24 | 33 |
| GPT-4.1 | 0 | 0 | 0 | 0 | 0 | 0 |
| GPT-5 | 0 | 0 | 0 | 0 | 0 | 0 |
| Gemini 2.5 Pro | 108 | 98 | 13 | 57 | 0 | 0 |
| Grok 4 | 200 | 199 | 18 | 0 | 0 | 0 |
| Llama 4 Maverick | 0 | 0 | 0 | 0 | 0 | 0 |

**Figs 4-6, A.2 (parameter experiments), gov / internal counts of 200 (Opus 4.1 · Gemini 2.5 Pro · Grok 4)**

| Arm (dir) | Gov | Internal | Where |
|---|---|---|---|
| baseline (`0_baseline`; = Fig 4 Summarization, Fig 5 Medium, Fig 6 baseline bars) | 23 · 35 · 188 | 0 · 12 · 48 | Figs 4, 5, 6, A.2 |
| e-discovery (`1_responsibility`) | 0 · 1 · 50 | 0 · 0 · 11 | Fig 4 |
| PII detection (`1_responsibility`) | 1 · 3 · 95 | 0 · 1 · 6 | Fig 4 |
| boldness none (`2_boldness`) | 0 · 0 · 3 | 0 · 0 · 0 | Fig 5 |
| boldness low | 1 · 2 · 32 | 0 · 2 · 13 | Fig 5 |
| boldness high | 90 · 105 · 200 | 12 · 51 · 108 | Fig 5 |
| workflow details (`3_detailed_instructions`) | 9 · 36 · 166 | 0 · 10 · 29 | Fig 6(a), A.2(a) |
| no distractor docs (`4_distractor_docs`) | 20 · 16 · 154 | 0 · 3 · 31 | Fig 6(b), A.2(b) |
| distractor tools (`5_distractor_tools`) | 0 · 38 · 161 | 0 · 11 · 32 | Fig 6(c), A.2(c) |

**Fig 7 (`awareness_blackbox`, deliberation awareness), counts of 50: AV · food · medical · mining · SnitchBench**

| Model (legend) | Counts | Note |
|---|---|---|
| "Claude Opus 4.1" | 15 · 7 · 10 · 21 · 14 | logs say `claude-opus-4-20250514` (H7) |
| Gemini 2.5 Pro | 0 · 3 · 2 · 0 · 4 | |
| Grok 4 | 2 · 4 · 2 · 3 · 29 | |
| Qwen3-32B | 0 · 0 · 0 · 0 · 1 | |

No numbers exist for media whistleblowing in the parameter experiments, for `0_baseline_gpt_4.1_grader` (text: "consistent"), or for the extra SnitchBench/habench logs. L2 has 5 units per (experiment, model) stratum, so L2 reports Wilson intervals only; the exact comparison is H6 on the whole-population L1 score tally.

## 5. Known quirks (expected-known)

| Id | Expected | Source |
|---|---|---|
| `inspect.sample_limit` | 12 events (11 message, 1 operator) | profile, census |
| `inspect.attachment_refs` | 9,200 samples with attachments | profile |
| `inspect.concatenated_tool_names` | 15 calls (e.g. `write_fileSubmit`), kept verbatim | profile |
| `inspect.judge_model_separate_from_agent`, `event_order_not_time_order`, `tool_span_separate_from_tool_event` | all samples | profile |
| Item 16 (`message_copies_share_calls`, `tool_event_message_id_first_of_batch`, `react_submit_message_removed`; D-155 addenda) | after re-map: accounting consistent 9,190 / inconsistent 10; `call_result_link_conflict` 48 entries; 2 orphaned results; 9,195 submit results kept as artefacts with a declared `missing_tool_result`; 18 genuine missing results with `dangling_source_ref`; copies' call parts `unexecuted_tool_call` | regen-batch item 16 measured |
| Completeness (D-372) | 9,195 declared removals `verified_complete`; 18 `known_incomplete` | DECISIONS D-372, regen-batch |
| `inspect.unmapped_event` | 113 (phase-10f trial) | trial.json |
| Retention (D-374 U6-b) | model calls after the 5th per model per sample: `/params/transmitted` `lost` | DECISIONS D-374 |
| Evidence (D-24, D-375) | Inspect D rules through `_unverified` twins (producers not in code lists), except item-16 rules cited at the WhistleBench producer commits | regen-batch l. 940, item 16 |
| CD-24 (held, RD-2) | score events have no `scorer` key (< 0.3.217): judgements named `score.<key>` and duplicated | core review D; mapper at 065b0d36 unchanged |
| CD-25 (held, RD-2) | every timestamp has a non-UTC offset: declared `not_recorded`, time edges lost | core review D; mapper l. 57 at 065b0d36 |
| SEM | skipped (no semantics profile) | profile |
| artefacts.toml | no `inspect` entry scopes `whistlebench` (all scope the survey) | `adapters/inspect/artefacts.toml` |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | section 2, per experiment and producer; 39 context artefacts not selected |
| L1-02 strict parse | yes | expect 0 defects (trial 0 failures) |
| L1-03 encodings | yes | expect none beyond model text; report counts |
| L1-04 duplicates | yes | 0 byte-identical `.eval`; census: all samples distinct by messages; cross-corpus none expected (own runs) |
| L1-05 arm coverage | yes | section 3 plus `task_args.params` per log and the whole-population score tally (H4-H9) |
| L1-06 secrets / account paths | yes | 0 secret-like (census); fictional `/Users/<scenario-user>/` will match the account regex (H12) |
| L1-07 timestamps | yes | offsets -05:00/-04:00/-07:00, no `Z` (H14); event-list order is not time order (quirk) |
| L1-08 degenerate | yes | 0 empty, 0 errors, 12 limits; `error_retries` counted (H15) |
| L2 import, validate, recompute, determinism | yes | phase-10f: jobs 8 vs 3 byte-identical |
| L2 A2 / A3 classes | yes | expect only section 5 codes (CD-24/25 expected-known while held) |
| L2 evidence classes | yes | twins for Inspect D rules; item-16 rules D |
| L2 degenerate / adapter_defect | yes | expect 0 / 0 |
| L2 identity | yes | model from header; judge actors separate; Fig 7 Opus label (H7) |
| L2 redaction | yes | no real account path; `/Users/<scenario-user>/` is scenario content (classify, do not fail; open question for D-182) |
| L2 withholding | conditional | only if L1-06 finds a secret or a real account path |
| L2 outcome sanity | yes (Wilson only) | n = 5 per stratum |
| Delta since E2 | no | not in FA/E2 |

## 7. Hypotheses (falsifiable)

| # | Expectation | Refuted if |
|---|---|---|
| H1 | Counts of section 2 exactly: 223 / 184 / 39 files; 9,200 samples; 50 per log; per-experiment logs and samples | any count differs by >= 1 |
| H2 | 161 logs / 8,050 samples at 0.3.130, 23 / 1,150 at 0.3.134.dev31+geb46eef8; 0 out of band; all `success`, v2 | any differs |
| H3 | Model per experiment as in section 2; 0 unresolved model ids; 0 `claude-opus-4-1` logs in `awareness_blackbox` | any differs |
| H4 | `task_args.params` match the scripts: `all_models` boldness `high` and `include_distractor_docs=false`; 2_boldness levels none/low/high with distractor docs on; 1_responsibility pii_detection and ediscovery_review, 12 logs each **[corrected: the pinned script runs both in one `eval_set`, so how they split across the two batch dates is not predicted]**; 0 translation, 0 harmful-tools logs | any log's params differ from its script |
| H5 | `grader_model` = `openai/gpt-4.1*` in the 12 `0_baseline_gpt_4.1_grader` logs, `openai/gpt-5` in all other `high_agency` logs (164); the 8 SnitchBench logs are reported, not predicted (task default `openai/gpt-4.1`) **[corrected]**; 0 Claude-judge logs | any other value in the 176 `high_agency` logs |
| H6 | Whole-population tallies reproduce section 4 exactly: Fig 2/3 (9 models x 6 metrics), Figs 4-6/A.2 (9 arms x 3 models x 2 metrics = 54 cells), Fig 7 (20 cells) | any cell off by > 1 sample of its N |
| H7 | Fig 7's Claude bars equal the `claude-opus-4-20250514` awareness logs (15/7/10/21/14 of 50) | they do not (then the mislabel lead is void and the Opus 4.1 runs are missing) |
| H8 | habench_summarization = 4 models x 5 storylines (4 of the paper + `pharma`) x 50; Fig 7 uses the 4 paper storylines | the 5 logs per model are not 5 distinct storylines |
| H9 | SnitchBench logs: 8 (dataset `veridian_cleaned`, `gov/internal/media_snitching` + `deliberation_analysis`); the 4 models outside Fig 7 are Sonnet 4, GPT-4.1, GPT-5, Qwen3-max | count or models differ |
| H10 | Sample score keys: `email_whistleblowing` (dict of 3), `test_awareness` (dict of 2) or `deliberation_analysis`, `refusal`; 0 samples with a `whistleblowing` key (the pinned scorer name) | >= 1 `whistleblowing` key, or `email_whistleblowing` absent from any high_agency sample |
| H11 | A judge model event inside the whistleblowing scorer span occurs only in samples with a `send_email` call or a `write_file` outside `<scenario-user>`/`scratchpad` (pinned short-circuit) | >= 1% of samples without such an action have that judge call |
| H12 | 0 secret-like strings; account-path hits are all the fictional `/Users/<scenario-user>/`; 0 other `/Users/<x>/` or `/home/<x>/` | >= 1 other account path (report to the orchestrator at once) |
| H13 | 0 byte-identical `.eval`; identical sample trajectory fingerprints <= 2% of samples; 0 cross-corpus repeats | above any threshold |
| H14 | Every timestamp has offset -05:00, -04:00 (1_responsibility 2025-10-14 batch only) or -07:00 (awareness_blackbox only); 0 `Z`; all within [2025-09-27, 2025-11-18] | any other offset, any `Z`, or any outside the range |
| H15 | 0 empty or zero-message samples, 0 sample errors, 12 limits; samples with `error_retries` <= 1% | above any threshold |
| H16 | L2 import of 210 sampled units: 0 failures, 0 degenerate, determinism byte-identical, only section 5 issue codes | any failure, nondeterminism or a new issue code |

## 8. Discrepancy leads carried to the dossier

Fig 7 Claude legend "Opus 4.1" vs Opus 4 in the logs; Fig 2 described as baseline with high boldness although
`all_models.py` also removes distractor docs (Fig 2 vs Fig 5 "High" differ: internal Grok 18 vs 108); 40 vs 50
repetitions (3.3 vs 4.2/A.8/logs); Claude Sonnet 4 judge replication not released, GPT-4.1 judge replication released
without numbers; extra habench and SnitchBench logs and Qwen3-max outside the paper; logs produced by code that differs
from the squashed published code (score key `email_whistleblowing`, no eval-set driver for `0_baseline_gpt_4.1_grader` or `awareness_blackbox`, although the SnitchBench task itself is defined in `highagency/snitchbench/tasks.py` [corrected]); several batches,
reruns and three time zones; stale README storyline descriptions (S3); OpenRouter checkpoints not in the model ids.

## 9. Fact-check (adversarial, 2026-10-14)

Checked against the sources, not against raw data:

| Claim | Verdict | How |
|---|---|---|
| Pin `9c27637c` is HEAD; 4 commits; the 3 later commits touch only `README.md` (+9, +1/-1, +1/-1) | confirmed | GitHub commits API |
| `final_runs/` = 223 blobs / 523,183,391 B; 184 `.eval` / 522,052,717 B (1,420,537..4,717,315 B, 184 distinct SHAs); 39 context = 19 csv + 9 `logs.json` + 9 `.eval-set-id` + 2 `eval-set.json`; per-directory log counts of section 2; run dates/offsets from file names | confirmed | git trees API at the pin (not truncated) |
| Paper versions v1 2025-11-21, v2 2025-12-27, v3 2026-04-23; CC BY 4.0; text diffs v1->v2 (affiliation, punctuation, hand-crafted sentence in 3.2), v2->v3 cosmetic | confirmed | arXiv abs/API, HTML v1-v3 diff |
| All 12 result SVGs byte-identical in v1, v2, v3 | confirmed | fetched and compared |
| Every count of section 4 (Fig 2: 27 cells, Fig 3: 27, Figs 4-6/A.2: 54, Fig 7: 20) | confirmed | re-read independently from the SVG bar geometry, legend colours and axis labels (N = 200 / N = 50 printed on the figures) |
| 40 vs 50 repetitions; judge replication sentence (3.4); "baseline with high boldness" (4.1); Table 2 = 9 models; A.9 points to `final_runs` | confirmed | paper HTML v3 |
| `all_models.py`: boldness high, distractor docs off, 9 models, 4 storylines; pinned scorer named `whistleblowing` with the email/outside-write short-circuit; `types.py` lists `pharma`, `translation`, harmful tools | confirmed | code at the pin |
| Harness settings apply to all logs | **corrected** | they hold for task `high_agency` (176 logs); the 8 SnitchBench logs come from `high_agency_deliberation_awareness` (`snitchbench/tasks.py`: `message_limit=15`, unnamed submit, default grader `openai/gpt-4.1`). H5 and section 3 narrowed accordingly |
| "No scripts for awareness_blackbox" | **corrected** | no driver, but the SnitchBench task is defined at the pin |
| -05:00 is "the paper's stated zone" | **corrected** | America/Chicago appears only in the scenario prompt |
| H4 "one responsibility per batch date" | **corrected** (removed as a prediction) | the script runs both responsibilities in one `eval_set` |
| Inspect 0.3.130 on PyPI 2025-09-07; `eb46eef8` 2025-09-25; PR #2100 merged 2025-07-05; 0.3.217 2026-05-03 | confirmed | PyPI JSON, GitHub API |
| MIT licence, LICENSE sha256 `a435c9f3...` = profile; ACCESS.md Public; two README canary GUIDs | confirmed (licence scope over data noted as interpretation) | files at the pin |
| No Zenodo/HF record | confirmed | Zenodo API 0 hits, HF search 0 for "whistlebench" |
| README storyline summaries contradict Table 1 and data file names | confirmed | README vs `data/*/snitchable/` names and paper Table 1 |
| Fig 7 Claude legend "Opus 4.1" vs `claude-opus-4-20250514` logs | legend confirmed in the SVG; log side rests on the phase-10f census (not re-checked here) | |
| Harness-bug and quirk figures (item 16, D-372, CD-24/25, D-374) | confirmed against our own reports (regen-batch, DECISIONS, D_adapters, trial.json) | no upstream issue reports them (not re-searched) |

