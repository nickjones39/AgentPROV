# Pre-registration: `openagentsafety`

| | |
|---|---|
| Corpus | `openagentsafety` (family `openhands`, profile `openagentsafety` v1, dialect/mapper `openhands.events`, variant `oas-0.28`) |
| Parts | `head` (only part; 1,560 runs) |
| Wave | 5 (first examination; not in FA or E2) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: our phase-10g reports (`docs/reports/phase10g/README.md`, `openagentsafety.census.json`, `openagentsafety.detail.json`), the profile, the registry, `artefacts.toml`, DECISIONS D-170..D-179, and desk research (`data/openagentsafety/research.json`: GitHub API metadata and git trees, docs and scripts at the pin, arXiv v1/v2, HF metadata). Nothing here was computed from the raw logs; the only arithmetic is on published percentages and on our census counts. |
| Method | [`../README.md`](../README.md) |

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Repository | [sani903/OpenAgentSafety](https://github.com/sani903/OpenAgentSafety), MIT (LICENSE copyright line: TheAgentCompany 2024) | LICENSE at pin, GitHub API |
| Pin | `857798ff26c4ce6e1d7911ee4d8b3f84a71184e0`, committed 2026-08-10T05:38:08Z (README only; profile says 2026-08-09), = `main` HEAD on 2026-10-14; tree 14,887 blobs (7,827 PNG not fetched) | GitHub API |
| Data history | `evaluation/{claude-sonnet,gpt-4o,o3-mini}` in the initial commit `e49e0623` (2025-05-10T05:07Z); `deepseek_v3` `b20c257b` (05:21Z); `deepseek_r1` `75282882` (19:28Z). No later commit touches `evaluation/<model>/`; tasks unchanged since 2025-05-10 except one macOS resource fork removed (`058f9f28`) | GitHub API |
| Paper | arXiv [2507.06134](https://arxiv.org/abs/2507.06134) v1 2025-07-08 (5 models, 356 tasks); v2 2026-02-16 (ICLR 2026; adds Claude Sonnet 4 and GPT-5 and a "successful completion" column; five original models' numbers unchanged; v1 T4/T5/T6 = v2 T3/T4/T5; data link moved to the maintained copy). No publisher DOI; arXiv DOI 10.48550/arXiv.2507.06134 [corrected: was "No DOI"], no Zenodo/HF data record (HF `sani903/openagentsafety` holds task definitions only, CC-BY-4.0) | arXiv, HF API |
| Maintained copy | [Open-Agent-Safety/OpenAgentSafety](https://github.com/Open-Agent-Safety/OpenAgentSafety) (D-148: lead, not used): all 1,560 trajectories have the same git blob ids; 81 `evaluator.py` fixed after the release (PR #4, 2026-08-09) | GitHub trees |
| Harness | OpenHands fork `adityasoni9998/OpenHands@5a13eacf` (2025-04-07; lock `openhands-ai 0.28.1`; not in the logs); CodeActAgent, BrowserOutputCondenser, `max_iterations` 75/60/50 by service dependency, budget 4 USD per task; FakeUser `gpt-4o-2024-05-13`; NPCs through Sotopia with an unrecorded env LLM | `evaluation/run_eval.py` at pin; D-172 |
| Judging | (a) rule-based `eval_<task>.json` written by the task's `utils/evaluator.py` in the container; (b) GPT-4.1 judge (`evaluation/llm_as_judge.py`, temperature 0): `Label: -1` failure, `0` safe, `1` unsafe incomplete, `2` unsafe complete; `rule_based_score` = -1 (no eval or `final_score.total == 0`), 1 (`result == 1`), else 0; the judge reads `state_<task>.json` when the trajectory is missing | scripts at pin; paper §2.3, App. A.3 |
| Models (served) | `claude-3-7-sonnet-20250219`, `deepseek-chat` (alias; V3-0324 in 2025-05), `deepseek-reasoner` (alias; original R1, R1-0528 came 2025-05-28), `gpt-4o-2024-08-06`, `o3-mini-2025-01-31`; claude/deepseek routed `openai/neulab/...` | census §3.4; DeepSeek API news |
| Run dates (naive) | 2025-05-05T06:43:21 .. 2025-05-10T16:39:55 | census `numbers.first_ts`/`last_ts` |

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Tree blobs at pin | 14,887 (7,060 non-PNG staged; 7,827 PNG absent) | profile pin note; GitHub tree; phase-10g §1 |
| Selected `evaluation/*/traj_*.json` | **1,560** (1,377,042,866 B; max 34,524,664) | registry / `readme_corpora.toml` (census `/totals/files/n`); GitHub tree |
| per model dir | claude-sonnet 289, deepseek_r1 316, deepseek_v3 322, gpt-4o 321, o3-mini 312 | census; tree |
| Auxiliary (not units) | `eval_` 1,474 (280/298/301/299/296), `state_` 1,705 (303/352/350/351/349), 4 judge summaries (none for o3-mini), task dirs 361 (`task.md` 359, `checkpoints.md` 357, `scenarios.json` 196, `evaluator.py` 359) | census; tree |
| Not selected | `deepseek_r1_analysis/` (4 files: 2 JSON + 2 PNG; the PNGs are among the 7,827) [corrected: was "2 files"], scripts, docs, 145 state files without trajectory (`select.not_execution_artefact`) | tree; D-177 |
| Units / executions | 1,560 `agent_execution` / 1,560 | trial (§8.4) |
| Trial status | ok 1,375, ok_with_issues 185, completeness `verified_complete` 1,560; 0 failed validation checks | phase-10g §8.4 |
| Events | 45,832 (min 5, median 16, max 233 per run) | census `numbers.events` |
| Strict parse | 1,560 / 1,560 ok | census §3.1 |

## 3. Expected arms

| Facet | Values | Expected missing / extra |
|---|---|---|
| Model (dir) | 5 dirs; served id per dir as §1 | no extra; **Claude Sonnet 4 and GPT-5 (paper v2) absent** |
| Task | 352 tasks with a run (of 361 dirs; paper: 356) | per model of 352: claude 63 missing, o3-mini 40, r1 36, gpt-4o 31, v3 30 (= 200 of 1,760); coverage 211 tasks x 5, 101 x 4, 25 x 3, 11 x 2, 4 x 1 |
| Missing cells by kind | of the 200: 132 have a state file only (claude 12, r1 34, v3 25, gpt-4o 27, o3-mini 34) and 68 nothing (claude 51, r1 2, v3 5, gpt-4o 4, o3-mini 6); the other 13 state-only files (2/2/3/3/3) are on 3 tasks with no trajectory at all (`safety-base64-text`, `safety-migrate`, `safety-wiki-page`), so states cover 355 tasks | GitHub tree (file names only) |
| Defence / attack | none recorded (risk lives in the task design: user and NPC intent, risk category; not in the logs) | `attack_id` none, `defense_id` `not_recorded` (D-171/§6.2) |
| Runs per cell | 1 (one file per model x task; resume overwrites, earlier attempts unobservable) | `run_eval.sh` |

L2 strata (`l1_families.py`: `model`): 5 strata; with about 5 per stratum and the minimum of 30, expected **30 units (6 per model)**.

## 4. Expected outcome rates (comparison targets)

Metric mapping: failure = judge `llm_label` `"Label: -1"`; unsafe = `"Label: 1"` or `"Label: 2"` (the paper's arithmetic also counts the 2 `"Label: Label"` entries as unsafe, see H2); rule unsafe = `rule_based_score` 1 = `eval` `final_score.result == 1` with `total != 0`. Paper denominators: failure over all judged runs; unsafe and rule rates over runs with label != -1. In AER these are the `oas_llm_judge` judgements (`llm_label`, `rule_based_score`) and the `oas_checker` judgements (`final_score`), values verbatim (D-177).

Paper (v1 Tables 4 and 6; v2 Tables 3 and 5) and the integer counts back-solved from the published rates (unique solution in N 150..420, our arithmetic; several Table 4 cells are truncated, not rounded, e.g. Claude 106/207 = 51.208 printed 51.20, GPT-4o 11/193 = 5.699 printed 5.69, v3 61/188 = 32.447 printed 32.44, so the solve must accept truncation or rounding [corrected: was "from the rounded rates"]):

| Model | Judge unsafe (vuln.) | Rule unsafe (vuln.) | Disagree (vuln.) | Failure | Back-solved N / -1 / unsafe / safe / rule-unsafe / disagree | Release summary (census) entries / -1 / 0 / 1 / 2 / `Label` |
|---|---:|---:|---:|---:|---|---|
| Claude Sonnet 3.7 | 51.20 | 32.85 | 9.17 | 40.30 | 347 / 140 / 106 / 101 / 68 / 19 | 165 / 66 / 55 / 6 / 38 / 0 (not reproducible) |
| o3-mini | 72.73 | 32.32 | 6.57 | 43.30 | 349 / 151 / 144 / 54 / 64 / 13 | **no summary file** |
| GPT-4o | 65.80 | 32.64 | 5.69 | 45.00 | 351 / 158 / 127 / 66 / 63 / 11 | 351 / 158 / 66 / 22 / 104 / 1 |
| Deepseek-v3 | 62.23 | 32.44 | 6.91 | 46.30 | 350 / 162 / 117 / 71 / 61 / 13 | 350 / 162 / 71 / 16 / 100 / 1 |
| Deepseek-R1 | 62.78 | 32.78 | 6.67 | 48.90 | 352 / 172 / 113 / 67 / 59 / 12 | 352 / 172 / 67 / 22 / 91 / 0 |

Full-set rates (v1 T6): judge unsafe 30.60 / 41.26 / 36.18 / 33.50 / 32.10; rule 19.60 / 18.34 / 17.90 / 17.43 / 16.76; failure as above.
Not testable from the release: v2 "successful completion" (33.88 / 17.29 / 21.77 / 22.12 / 20.86), the v2-only models, the human study (v1 T5).

Rule-based checkpoints in the release (census; eval files beside trajectories): final_score 1/1 claude 100, r1 104, v3 103, gpt-4o 108, o3-mini 119; 0/1 144 / 163 / 160 / 152 / 145; 0/0 36 / 31 / 38 / 39 / 32; eval missing 9 / 18 / 21 / 22 / 16.

The paper's numbers are over the judged runs (state-file population), not over the 1,560 trajectories; the decisive comparison is therefore population-level on the auxiliary files (H2-H5). The L2 sample (6 per model) is below n = 20: Wilson intervals only, plus value identity between AER judgements and source files (H13).

## 5. Known quirks

| Id | Expected | Source |
|---|---|---|
| `openhands.art.filtered_events` | 1,560 executions (3,338 missing ids) | artefacts.toml, profile, census §3.7 |
| `openhands.art.task_text_not_seen` | 1,284 | artefacts.toml (trial; part-A prefix count 1,140) |
| `openhands.art.content_not_inlined` | 322 executions (321 with set-of-marks; 7,973 images; 117 strings > 1 MiB) | artefacts.toml, profile; R-10g-2 (no blob surface) |
| `openhands.art.not_executed_notice` | 168 (always last event; + core `unexecuted_tool_call` 168) | artefacts.toml, D-175 |
| `openhands.art.summary_entry_missing` | 128 (claude) | artefacts.toml, D-177 |
| `openhands.art.eval_missing` | 86 (9 / 18 / 21 / 22 / 16) | artefacts.toml, D-177 |
| `openhands.art.harness_error` | 2 observations | artefacts.toml |
| core `no_outcome_recorded` | 22 runs (no eval file and no judge entry) | trial §8.4 |
| profile quirks | `parallel_calls` 78 responses (gpt-4o); `fake_user` 594 messages, 140 fixed (sha256 `9e6ed959…`) | profile |
| Runs without `finish` | 418; state `agent_state=error` 564 of 1,705 | census §4 |
| NPC `chat` | 1,390 calls, 286 error replies, 135 calls name an NPC not in `scenarios.json` | census §3.6 |
| Judge oddities | `"Label: Label"` 2; rule score -1 = eval missing or 0/0 | census; `llm_as_judge.py` |
| Secret-like strings | 423 occurrences (388 in task defs, GitLab login in 211 first messages), 3 distinct values not in task defs; kept (D-179 option A) | detail census, D-179 |
| Evidence | `verified_code` = fork `5a13eacf`: `cause` / execution / call links class D | profile, D-172 addendum |
| Identity | served model O from `model_response`; requested from `llm_metrics.token_usages[].model`; dir name cross-check only | D-173 |
| Worker RSS | R-10g-4: unit `ex_lmecr3yelohcqvymkabizjz4vx` (21.6 MB PROV) lost at 3 workers | phase-10g §5 |
| Pending code change | BF-23 / regen item 34 (served-model sentinel check; none expected in the pinned data) | bugpass proposals |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2; selection by `include` glob, auxiliary globs; 145 state-only files not units |
| L1-02 strict parse | yes | expect 0 defects in 1,560 trajectories (and in eval/state/summary files) |
| L1-03 encodings | yes | browser text and tool outputs may carry U+FFFD, controls, mojibake; base64 screenshots excluded from text classes; no baseline: count and classify |
| L1-04 duplicates | yes | H12; cross-corpus vs `redcode-exec-openhands` (other variant) |
| L1-05 arm coverage | yes | §3 (model x task); tally for H1 |
| L1-06 secrets / account paths | yes | H11; counts and pointers only |
| L1-07 timestamps | yes | naive per event; monotonic within a run; range §1; H9 |
| L1-08 degenerate | yes | H10 |
| L2 import, validate, recompute, determinism | yes | through `l2_import.py` (git pin, `include_paths`, per-unit auxiliary inputs); trial: byte-identical across 8/3 jobs except R-10g-4 |
| L2 A2 / A3 classes | yes | expect only the §5 register codes; no PI classes |
| L2 evidence classes | yes | links D (verified fork); authorship, NPC, fixtures, order I; H8 may require a class change for deepseek tool calls |
| L2 degenerate / adapter_defect | yes | expect 0 / 0 |
| L2 identity | yes | 5 served ids, requested ids, `harness 0.28.1` (I), FakeUser model (I), judge actors `oas_checker`, `oas_llm_judge` |
| L2 redaction | yes | expect no account path in AER/SEM/PROV |
| L2 withholding | no (verify absence) | no `[withhold]` (D-179 option A); check nothing is withheld |
| L2 outcome sanity | partial | Wilson only (n about 6 per model); H13 value identity; paper comparison at population level (H2-H5) |
| Delta since E2 | no | not in FA/E2 |

## 7. Hypotheses (falsifiable)

| # | Expectation | Refuted if |
|---|---|---|
| H1 | 1,560 trajectories, per model 289/316/322/321/312, 352 distinct tasks, 1,560 distinct (model, task); missing cells per model 63/36/30/31/40 | any count differs |
| H2 | Judge summaries reproduce the paper: gpt-4o / v3 / r1 entries 351 / 350 / 352; `-1` 158 / 162 / 172; `0` 66 / 71 / 67; N - (-1) - (0) = 127 / 117 / 113; entries with label != -1 and rule 1 = 63 / 61 / 59; label 0 and rule 1 = 11 / 13 / 12 | any differs by >= 1 (documentation-mismatch) |
| H3 | Claude and o3-mini paper figures are not reproducible from the release: claude summary 165 entries (paper N 347), no o3-mini summary | a pinned file with >= 347 claude or >= 349 o3-mini judge entries exists |
| H4 | The 145 state-only runs are paper runs: each has an entry in its model's summary (r1 36, v3 28, gpt-4o 30; claude: count reported) with `rule_based_score` -1 | < 100 % for r1 / v3 / gpt-4o |
| H5 | `rule_based_score` equals the `llm_as_judge.py` mapping of the joined eval file in 100 % of joined entries; per-model summary rule tallies equal the census (e.g. gpt-4o -1 91 / 0 152 / 1 108) | any mismatch |
| H6 | Evaluator defects (issue #5) shape the eval files: (a) >= 90 % of the 176 `0/0` eval files are on the 46 §A.2 tasks and >= 90 % of §A.2 eval files are `0/0`; (b) >= 80 % of trajectories of the 9 §A.1 tasks with runs have no eval file; (c) 100 % of eval files of `delete-config`, `bug-reports`, `logs` are `1/1`; (d) >= 95 % of eval files of the 19 §B/§C tasks other than `reimburse-policy` [corrected: was "the 20 §B/§C tasks"; issue #5 says `reimburse-policy`'s mismatch is in `checkpoints.md` only and misinforms the LLM judge, not the rule-based evaluator] are `0/1` or `0/0` | any threshold missed (then the issue does not describe the evaluators that ran) |
| H7 | The 132 state files with `max_iterations` 100 (not a value of the pin's `run_eval.py`) concentrate in <= 2 model dirs (>= 90 %) | spread over >= 3 dirs (then test the non-headless extension: every such run has a later user message) |
| H8 | Mocked function calling for deepseek: >= 99 % of tool-call ids in deepseek_v3 and deepseek_r1 trajectories match `^toolu_\d{2,}$`; <= 1 % in claude / gpt-4o / o3-mini | either bound missed |
| H9 | Timestamps naive, non-decreasing in 1,560 / 1,560, all within 2025-05-05T06:43:21 .. 2025-05-10T16:39:56; latest event of claude / gpt-4o / o3-mini <= 2025-05-10T19:07 and of v3 <= 2025-05-10T19:21 (commit time + 14 h) | any violation |
| H10 | 0 empty or zero-event files (min 5 events); every run starts with the user message (2 distinct texts: 1,349 / 211); 418 runs without `finish`; 168 notices, all last; 2 uncaused errors | any differs |
| H11 | Secret-like occurrences 423 (claude 100, r1 53, v3 44, gpt-4o 184, o3-mini 42) by the census patterns; 3 distinct values not in task defs; 0 personal account paths (any `/Users/<name>`, `/home/<name>` other than generic `ubuntu`/`openhands`/`root`) | a different total, or >= 1 personal account path |
| H12 | 0 byte-identical trajectory pairs; 0 identical step fingerprints between different (model, task); 0 overlaps with other corpora | >= 1 |
| H13 | In the L2 sample every judgement value (checkpoints, `final_score`, `llm_label`, `rule_based_score`) equals its source file, and every `served_model` equals the dir's id | any mismatch |
| H14 | Population register counts as the trial: `task_text_not_seen` 1,284, `content_not_inlined` 322, `summary_entry_missing` 128, `eval_missing` 86, `no_outcome_recorded` 22; the sample's rate of each is consistent with them | a population rate outside the sample's Wilson 95 % interval |

## 8. Discrepancy leads carried to the dossier

The released trajectories are a subset of the runs the paper scored (paper N = state-file counts for four models; 145
state-only runs; Claude N 347 vs 289 trajectories and a 165-entry summary; o3-mini summary absent); the eval files are
the output of evaluators later fixed upstream (issue #5, PR #4); `max_iterations` 100 is outside the pin's harness
code; deepseek tool calls are probably OpenHands reconstructions (mocked function calling), which bears on D-173's O
class; small arithmetic inconsistencies in v1 Table 6 and the human-study n (100 stated, 92 fits); the paper's 356
tasks vs 352 run and 361 task dirs; v2's extra models and success metric have no released data.

## Fact-check (2026-10-14, adversarial pass before any data check)

Re-opened every cited source; no raw data was read. Arithmetic is on the published percentages and on GitHub/HF metadata only.

| Checked | Verdict | Evidence |
|---|---|---|
| v1 Table 4 / Table 6 and v2 Table 3 / Table 5 values for all five released models (judge, rule, disagreement, failure; full-set rates) | confirmed | [v1 HTML](https://arxiv.org/html/2507.06134v1), [v2 HTML](https://arxiv.org/html/2507.06134v2): every cell as in §4; the five models' values are identical in v1 and v2 |
| Metric definitions (disagreement = judge safe and rule unsafe; vulnerable-state denominators) | confirmed | v1 §3.1 metric definitions and Table 4 caption |
| v2 "Successful" column (33.88 Claude 3.7, 21.77 GPT-4o, 17.29 o3-mini, 22.12 v3, 20.86 R1) and Claude Sonnet 4 / GPT-5 rows | confirmed | v2 Table 3 |
| Human study n: text says 100, Table 5 fits 92 | confirmed | v1 §5.2 and v2 RQ4 say 100; the only n in 50..200 fitting all of 21.7/35.9/42.4/7.6/71.7/20.7/18.5/81.5 at one decimal are 92 and 184 |
| Back-solved N / counts (347, 349, 351, 350, 352 and their splits) | confirmed, with a caveat (corrected) | unique in N 150..420 when truncation is allowed; under strict two-decimal rounding Claude, GPT-4o and v3 have no integer solution (truncated cells listed in §4). Table 6 mismatches (30.60, 17.90, 33.50) confirmed |
| `"Label: Label"` counted as unsafe by the paper | confirmed (arithmetic) | census summary tallies: GPT-4o 22 + 104 + 1 = 127, v3 16 + 100 + 1 = 117 equal the back-solved unsafe counts |
| Paper versions, dates, sizes, comment, licence | confirmed; DOI corrected | arXiv abs/API: v1 2025-07-08 (2,148 KB), v2 2026-02-16 (2,334 KB), comment names ICLR 2026 and IASEAI 2026, CC BY 4.0; arXiv DOI 10.48550/arXiv.2507.06134 exists |
| Paper is the source of these logs | confirmed | v1 footnote links sani903/OpenAgentSafety for code and data; README at the pin says the five models' trajectories are in `evaluation/` |
| Pin 857798ff (2026-08-10T05:38:08Z, README only), main HEAD, 13 commits, data commits e49e0623 / b20c257b / 75282882, 058f9f28 removes one `__MACOSX` file, no later commit touches `evaluation/` or tasks | confirmed | GitHub commits API. The profile date 2026-08-09 is the same instant in US local time (UTC-7), not an error |
| Tree: 14,887 blobs, 7,827 PNG, not truncated; traj 1,560 (1,377,042,866 B, max 34,524,664) and per-model traj/eval/state counts; 4 judge summaries; 361 task dirs (task.md 359, checkpoints.md 357, scenarios.json 196, evaluator.py 359) | confirmed | git tree API at the pin |
| `deepseek_r1_analysis/` "2 files" | corrected | 4 files (2 JSON, 2 PNG) |
| Coverage: 352 tasks with traj; missing 63/36/30/31/40; state-only-in-missing 12/34/25/27/34; nothing 51/2/5/4/6; 13 off-traj state files on 3 tasks; states cover 355 tasks; 211/101/25/11/4 | confirmed | git tree file names |
| Licence MIT, blob 5fcb0510 (1,072 B), copyright line TheAgentCompany 2024; README MIT; HF CC-BY-4.0 | confirmed | LICENSE blob at the pin; HF API (sha 6d65bdaf, last modified 2025-05-11, 361 task dirs) |
| HF "2,230 common files, 1 size difference" | unverifiable | HF tree-with-sizes API not read in this pass; 2,233 siblings = 3 root files + 2,230 under task dirs |
| Harness: fork 5a13eacf (2025-04-07) via poetry.lock `openhands-ai 0.28.1`; run_eval.py 75/60/50, budget 4, FakeUser gpt-4o-2024-05-13, state written before evaluator, traj/eval moved after; run_eval.sh skips existing eval files | confirmed | files at the pin |
| Judge: gpt-4.1, temperature 0, labels -1..2, state fallback, rule-score mapping | confirmed | `llm_as_judge.py` at the pin (it also skips tasks without `checkpoints.md`) |
| Mocked function calling for deepseek | confirmed as code path (data effect still a hypothesis, H8) | fork `llm.py`: support list has claude-3-7-sonnet, gpt-4o, o3-mini, not deepseek; substring match; `native_tool_calling` overrides; converter mints `toolu_NN` ids |
| `max_iterations` 100 not producible by the pin's run_eval.py; non-headless extension exists | confirmed | run_eval.py; fork `agent_controller.py` l. 433-436, 528-536; the fork's default is 500 (`OH_MAX_ITERATIONS`), so 100 is not a default either |
| Issue #5 counts (11 / 46 / 8 / 13 / 3 / 6 / 1, duplicates), closed 2026-09-15, fixes in Open-Agent-Safety PR #4 (merged 2026-08-09) | confirmed, one nuance corrected | issue text and comments. Section C's 13 include `reimburse-policy`, whose mismatch only misinforms the judge, so H6(d) now uses 19 tasks. 9 of the 11 §A.1 tasks have runs (the two `new-infra-task*` have none) |
| Maintained copy: 1,560 traj blob ids identical; 81 evaluator.py, 6 task.md, 3 checkpoints.md differ; 4 task dirs removed; only run_eval.py / run_eval.sh differ in `evaluation/`, plus `safe_completion_eval.py`; issue #2 open | confirmed | git tree of Open-Agent-Safety `master` 2fdd4057 (2026-08-10T15:49:52Z); issue #2 |
| DeepSeek alias mapping (V3-0324 from 2025-03-25; R1-0528 on 2025-05-28) | confirmed by page titles/slugs only | DeepSeek API news pages news250325, news250528; the alias wording itself was not re-read |
| Census and trial numbers (events 45,832; ok 1,375 / 185; register codes; summary tallies; eval 1/1, 0/1, 0/0, missing) | confirmed against our reports | `docs/reports/phase10g/README.md` §3.8, §8.4; `openagentsafety.census.json` |

Corrections applied: arXiv DOI; `deepseek_r1_analysis/` file count; truncation caveat on the back-solve; H6(d) task set 20 -> 19.

