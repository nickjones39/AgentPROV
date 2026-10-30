# Pre-registration: `sentry-agentdojo`

| | |
|---|---|
| Corpus | `sentry-agentdojo` (family `agentdojo`, profile `sentry-agentdojo` v1, dialect/mapper `agentdojo.tracelogger`, variants `v1.k14`, `v1.k14.incomplete`) |
| Parts | `head` (only part; AGPL-3.0-only, own corpus, D-94) |
| Wave | 3 (first examination; not in FA or E2) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: our phase-10d census, reconcile and trial reports, the profile and identity table, the registry, `artefacts.toml`, DECISIONS, and desk research (`data/sentry-agentdojo/research.json`). Per-cell counts come from the GitHub tree listing at the pin (paths only). Nothing here was computed from the raw logs. |
| Method | [`../README.md`](../README.md) |

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Repository | [vinhqdang/SENTRY-…-LLM-Agent-Action-Streams](https://github.com/vinhqdang/SENTRY-Anytime-Valid-E-Process-Monitoring-of-LLM-Agent-Action-Streams), AGPL-3.0 (canonical text, no copyright line) | LICENSE, README at pin |
| Pin | `938e8be757f4`, 2026-08-31T11:10:34Z (= profile); still head of `main`, 0 issues/PRs/releases | GitHub API |
| Logs committed | 2026-07-09 (free router) to 2026-07-22 08:58Z (`4f21dcbc`, an "in progress" snapshot); no later commit touches `real_data/agentdojo/`. [corrected] The free-router set reached 72 only in `d781dc7c` (2026-07-22 02:18Z, a "DeepSeek" commit that adds 2 and rewrites 2 free-router logs, among them the incomplete banking user_task_3/ii/injection_task_2); the first 7 DeepSeek logs came in `1259ee20` | commits API, path filter |
| Paper | unpublished manuscript `manuscript/sentry_ml.tex` (Dang, BUV); no arXiv/DOI/data record | research.json |
| Harness | AgentDojo 0.1.35 (logs; install undeclared), suites v1.2.2 (`run.py`; not logged), stock pipeline, no defence, default system prompt, OpenRouter client; no temperature sent (0.1.35 `temperature or NOT_GIVEN`) | `run.py`, agentdojo v0.1.35 source |
| Use of the logs by the authors | offline detector evaluation; outcome = AgentDojo `security` (True = compromised; polarity fixed 2026-07-25, `e4ab5208`) | README, NOTES.md §11 [corrected: was §12] |

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Tree blobs at pin | 782 (16,334,321 bytes; 21 binaries absent in staging, 1,550,351 bytes) | profile `expected_files`; census `absent_blobs`; trees API |
| Selected logs (`real_data/agentdojo/*/*/*/*/*/*.json`) | 674 (7,259,398 bytes) | registry/`readme_corpora.toml` (census `/files`); phase-10d census; tree |
| Not selected under `real_data/agentdojo/` | 1 (`run.py`); 0 `.DS_Store`/`._*`; context artefacts LICENSE, README.md, NOTES.md, pyproject.toml | tree; profile |
| Units / executions | 674 `agent_execution` / 674 | census, trial jobs 8 (674). [corrected] The jobs-3 trial import covered a 137-log subset; the comparison (mode `subset`, 552 objects) found 0 differences, so byte-identity is shown on that subset only |
| Variants | `v1.k14` 670, `v1.k14.incomplete` 4 | census |
| Sealed ok / ok_with_issues | 596 / 78 | trial |
| Register codes | `accounting_unverifiable` 672, `earlier_attempts_unobservable` 674, `identity_unresolved` 72, `incomplete_run` 4, `retry_passes_inferred` 2, `unexecuted_tool_call` 5 | census, trial |

Per cell (log set / pipeline dir × suite; attacked / benign), from the tree:

| Log set (pipeline dir) | Attack | banking | workspace | travel | slack | Attacked | Benign | Total |
|---|---|---|---|---|---|---:|---:|---:|
| `logs` (`openrouter-free-router-local`) | ii | 21 / 16 | 15 / 8 | 6 / 0 | 6 / 0 | 48 | 24 | 72 |
| `logs_deepseek` (`deepseek-v4-flash-local`) | ii | 48 / 16 | 80 / 30 | 42 / 18 | 45 / 18 | 215 | 82 | 297 |
| `logs_deepseek_injecagent` (`deepseek-v4-flash-local`) | injecagent | 18 / 2 | 15 / 0 | 6 / 0 | 6 / 0 | 45 | 2 | 47 |
| `logs_gpt4omini` (`gpt-4o-mini-local`) | ii | 48 / 16 | 80 / 30 | 42 / 18 | **6** / 18 | 176 | 82 | 258 |
| Total | | | | | | 484 | 190 | 674 |

ii = `important_instructions`. Injection tasks: DeepSeek/GPT ii banking 0-3, workspace 0-3, travel 0,1,6, slack 1-3;
injecagent and free router banking 0-2 (free router +3 in one cell), workspace 0-2, travel 0,6, slack 1-2. Pre-pass
(injection task as user task) 0. Model split = identity table: deepseek 344, gpt-4o-mini 258, unresolved 72.

## 3. Expected arms

| Facet | Values | Expected missing / extra |
|---|---|---|
| Model | `deepseek-v4-flash`, `gpt-4o-mini` (via OpenRouter, class I); free router unresolved (D-92/D-105) | none extra |
| Defence | none (SENTRY is a post-hoc monitor) | any defence label = extra |
| Attack | `important_instructions`; `injecagent` (DeepSeek only, own log set); benign (`attack_type` null, dir `none`) | injecagent × GPT and × free router missing by design |
| Suite | banking, workspace, travel, slack (v1.2.2 per `run.py`; `benchmark_version` null) | free-router benign travel/slack missing: FULL config has no benign travel/slack, and the later free-router `--max` run (whose MAX_CONFIG does) stopped in banking (`4b2e4c03`, `cfc6fbfb`, `d781dc7c`) [corrected: was "by design"] |
| Collection shortfall | GPT-4o-mini slack attacked: 6 of 45 `MAX_CONFIG` cells (user_task_0..1 only; last one incomplete) | 39 cells missing (collection stopped at the `4f21dcbc` snapshot) |
| Extra | 2 benign banking logs in `logs_deepseek_injecagent` (user_task_0/1) repeat cells of `logs_deepseek` under the same pipeline name | expected; authors exclude them (`corpus_table.py`) |

## 4. Expected outcome rates (L2 comparison targets)

Metric mapping (`real_data/corpus_table.py`, `adapters.py` at the pin): compromised = `security == true` on attacked logs
(attack_type not null); the paper keeps only logs with ≥ 2 tool calls and non-null `security`/`utility`. Benign
`security` is the runner constant (not a rate). Utility is never reported.

| Arm | Paper (≥ 2 actions), Table `tab:corpus` | Unfiltered, NOTES.md §11 [corrected: was §12] / `e4ab5208` | Expected on all judged logs |
|---|---|---|---|
| deepseek / ii / 4 suites | 18 / 198 (9%) | 18 / 215 (8%); 13 of 18 with a sink call | 18 / 215 |
| deepseek / injecagent / 4 suites | 0 / 42 | 0 / 45 | 0 / 45 |
| gpt-4o-mini / ii / 4 suites | 72 / 153 (47%) | 72 / 175 (41%); 61 of 72 with a sink call | 72 / 175 (176 files, 1 incomplete without outcome) |
| deepseek benign | 71 kept of 82 | - | 82 files; 11 with < 2 calls |
| gpt-4o-mini benign | 70 kept of 82 (commit `0624afe1`: 81 before filter) | - | 82 files; 12 with < 2 calls |
| banking attacked, 3 paper sets (`tab:polarity`) | 107: security True 31 (all pay the attacker IBAN), False 76 (3 pay) | - | 114 files; security True 31 |
| free router / ii | none of record (collection discarded) | superseded RESULTS.md at `befae2aa`: 16 True / 16 False (old 63-log tree) | context only |

L2 samples about 5 per stratum (about 27 strata: log set × suite × attack dir; about 130 units, all < 300), so every arm
has n < 20: L2 reports Wilson intervals only. The decisive comparison is H2 (whole-population tally at L1-05).

## 5. Known quirks

| Id | Expected | Source |
|---|---|---|
| `agentdojo.benign_security_constant` (art. `agentdojo.art.benign_security_constant`) | 190 files, rule applied 189 (the incomplete benign log has no outcome) | profile, census |
| `agentdojo.injection_task_as_user_task_prepass` | 0 | profile |
| `agentdojo.args_mutated_in_place` | 669 files with calls (so 5 logs without any tool call) | profile, census |
| `agentdojo.placeholder_args_never_injection_evidence` | 2,903 present, all null | profile, census |
| `agentdojo.unexecuted_trailing_calls` (art. `agentdojo.art.max_iters_pending`) | 5 calls in 5 logs, all DeepSeek slack (user_task_7 × it1-3, user_task_12 × it1, it3) | profile, census samples |
| `agentdojo.silent_rerun_last_pass_only` (art. `agentdojo.art.silent_rerun`) | 2 null-final logs (DeepSeek slack user_task_7 × it1, it2) → `retry_passes_inferred` 2; `earlier_attempts_unobservable` 674 | profile, census, reconcile (phase-10c 4 includes 2 incomplete) |
| `agentdojo.incomplete_run` (art. `agentdojo.art.incomplete_run`) | 4 logs, no utility/security/duration, `null_outcome_files` 0 | profile, census, artefacts.toml |
| `agentdojo.package_version_not_code_identity` | 0 without version (all `0.1.35`) | profile |
| Identity | free router 72 → `identity_unresolved` (D-92, D-105); `benchmark_version` null → `not_recorded` (D-102) | profile, table `sentry_pipeline_dirs` |
| System prompt | 469-char AgentDojo default in all 674 | profile `system_prompt_variants` |
| `agentdojo.art.naive_timestamp` | naive `evaluation_timestamp`, no per-call times | artefacts.toml (generic) |
| Accounting | `unverifiable` 672, `consistent` 2 | census |
| Evidence | `verified_code = []`: every D rule through its `_unverified` twin (D-24, D-103) | profile |
| Denials | none (no defence; routing.md: SENTRY logs no denial) | phase10d routing.md |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2 tables; selection by `include` glob; `run.py` not selected |
| L1-02 strict parse | yes | expect 0 defects (trial: 674 raw ok) |
| L1-03 encodings | yes | AgentDojo #214 `\uXXXX` residues in tool content possible: count, expected-known |
| L1-04 duplicates | yes | within part: the 2 injecagent-set benign logs vs `logs_deepseek` cells; across corpora: other deepseek-v4-flash or gpt-4o-mini AgentDojo runs (e.g. kongminOS DeepSeek V4-Flash) |
| L1-05 arm coverage | yes | §3; plus the whole-population outcome tally for H2/H3 |
| L1-06 secrets / account paths | yes | expect 0 (key read from `.env`; TraceLogger records no paths) |
| L1-07 timestamps | yes (partly) | presence, parse, naive zone, range; within-unit monotonicity n/a (one timestamp per log) |
| L1-08 degenerate | yes | 4 incomplete, 5 zero-call logs, 2 null-final; 0 empty files, 0 run errors expected |
| L2 import, validate, recompute, determinism | yes | trial: 0 failures, byte-identical across jobs |
| L2 A2 / A3 classes | yes | expect only the trial's register codes |
| L2 evidence classes | yes | D rules as `_unverified` twins only; model rows class I |
| L2 degenerate / adapter_defect | yes | expect 0 / 0 |
| L2 identity | yes | 3 pipeline dirs; injecagent vs ii from `attack_type`; log set not a facet of identity |
| L2 redaction | yes | expect no account path in AER/SEM/PROV |
| L2 withholding | conditional | only if L1-06 finds a secret-like string |
| L2 outcome sanity | yes (Wilson only) | §4 |
| Delta since E2 | no | not examined in FA/E2 |

## 7. Hypotheses (falsifiable)

| # | Expectation | Refuted if |
|---|---|---|
| H1 | Per-cell counts of §2 (log set × suite × attacked/benign) and injection-task sets hold exactly; 674 total, 0 pre-pass | any cell differs by ≥ 1 |
| H2 | `security == true` on attacked logs: DeepSeek ii 18 of 215, injecagent 0 of 45, GPT-4o-mini 72 of 175 judged | any count differs by ≥ 1 |
| H3 | Applying the paper's filter (≥ 2 tool calls, non-null outcome) gives 198 / 42 / 153 attacked and 71 / 70 benign (DeepSeek / GPT) | any differs by ≥ 1 |
| H4 | Banking attacked logs of the three paper sets: 114; `security == true` 31 | true count outside 31-33 |
| H5 | The 4 incomplete logs are exactly the four named in the census; none has a boolean `utility`/`security` or a `duration` | any differs |
| H6 | The 2 benign logs of `logs_deepseek_injecagent` are separate runs: not byte-identical to the `logs_deepseek` cells, different `evaluation_timestamp` | byte-identical (then expected-known duplicate, S3) |
| H7 | Exactly 3 `pipeline_name` values, each equal to its directory; `attack_type` ∈ {`important_instructions`, `injecagent`, null}; `benchmark_version` null in 674; package `0.1.35` in 674 | any extra value |
| H8 | `evaluation_timestamp` naive and parseable in 674, in 2026-07-09..2026-07-22 (local date); free-router logs ≤ the DeepSeek logs ≤ the GPT/injecagent logs per collection order | any outside 2026-07-08..2026-07-23, or order violated |
| H9 | 0 secret-like strings and 0 account paths | ≥ 1 |
| H10 | The 469-char default system prompt in all 674 | any other prompt |
| H11 | GPT-4o-mini slack attacked = 6 logs (user_task_0..1 × injection_task_1..3) | ≠ 6 |
| H12 | Cross-corpus: 0 byte-identical logs; identical trajectory fingerprints ≤ 1% of the 602 model-resolved logs | above either threshold |
| H13 | No log has a non-null `error` (no context-length runner imposition) | ≥ 1 |

## 8. Discrepancy leads carried to the dossier

Paper denominators use a two-action filter, so raw rates are lower (8% vs 9%, 41% vs 47%); the GPT-4o-mini slack attack
arm is a 6-log stub of a planned 45 and the collection was never completed after the "in progress" snapshot; the 72
free-router logs were discarded by the authors yet are in the corpus (model unknowable); runs used provider-default
temperature (not logged); `benchmark_version` is null although `run.py` loads v1.2.2; repository texts before
2026-07-25 (and the superseded RESULTS.md) use inverted outcome labels; tau-bench logs (5 files) are outside this
profile but count in the paper's benign total.

## Fact-check (2026-10-14)

An adversarial re-check used the pinned repository files (README, NOTES.md, LICENSE, `run.py`, `adapters.py`,
`corpus_table.py`, `results_*.json`, RESULTS.md, `sentry_ml.tex`, `reproduce.sh` at `938e8be7`), the GitHub trees,
commits and issues APIs, the agentdojo v0.1.35 source and issues, the arXiv API, and our phase-10d census/trial, profile,
pipeline table, `readme_corpora.toml` and DECISIONS. No raw log was read and no expectation was added.

**Confirmed.** `tab:corpus` (71/198/18, 42/0, 70/153/72, 50 tau-bench; totals 191/393/90/303) and `results_corpus.json`.
`tab:polarity` 31/0/3/73. NOTES table 215/18 (13 sink), 45/0, 175/72 (61 sink), the same as the `e4ab5208` message.
`results_generalization.json` 125/198, 21/42, 110/153. The pin is still the head of `main`. The tree has 782 blobs
(16,334,321 bytes, not truncated), 674 logs (7,259,398 bytes) and 21 binaries (1,550,351 bytes). Every §2 cell and
injection-task set matches the tree. The MAX/ATTACK_EXPANSION config products match the DeepSeek, GPT and injecagent
cells. GPT slack attacked is 6 = 2 user tasks × 3. The LICENSE sha256 and size match. It is AGPL v3 with no project
copyright line. No arXiv record exists. AgentDojo 0.1.35 is `a75aba76`. The temperature `or NOT_GIVEN` behaviour, the
TraceLogger save-per-step and 'Local model' naming are confirmed. Issues #168, #188 and #214 are open. The census and
trial figures in §2 and §5 are confirmed.

**Corrected** (marked `[corrected]` above and in `research.json`):
1. The unfiltered table is in NOTES.md §11, not §12.
2. The first 7 DeepSeek logs came in `1259ee20`. The free-router set reached 72 in `d781dc7c` (a "DeepSeek" commit that
   also adds 2 and rewrites 2 free-router logs, including the incomplete banking user_task_3/ii/injection_task_2), not
   in `cfc6fbfb` (70). So the free-router run was still writing after the switch to DeepSeek. The order assumption in
   H8 is therefore weaker than it reads, but the hypothesis is left unchanged.
3. The up-to-3 passes of `agentdojo.art.silent_rerun` come from `TaskSuite.run_task_with_pipeline`'s `range(3)` loop,
   not from tenacity. Tenacity retries API requests and is not logged.
4. The paper's null-outcome exclusion is in `corpus_table.py`. `adapters.py` drops only zero-action logs.
5. Trial determinism: the jobs-3 import covered 137 logs (compare mode `subset`, 0 differences). It was not a full
   second import.
6. Free-router benign travel/slack are absent because FULL_CONFIG has none and the later `--max` run stopped in banking,
   not purely by design.
7. ESWA retarget is dated 2026-07-28.

**Notes.** The `tab:polarity` caption says "all 107 attacked banking-suite trajectories", but `corpus_table.py` counts
them after the two-action filter, so 107 is filtered (114 files). It is unverifiable whether the NOTES §11 figures
(215/45/175) went through `adapters.py`, which drops zero-action logs. The H2 counts are therefore "judged logs with at
least one action" if they did.
