# Pre-registration: `bookkeeper-agentdojo`

| | |
|---|---|
| Corpus | `bookkeeper-agentdojo` (family `agentdojo`, profile `bookkeeper-agentdojo` v1, dialect/mapper `agentdojo.tracelogger`, variants `v1.k14`, `v1.k14.incomplete`) |
| Parts | `head` (only part; GPL-3.0-or-later, own corpus per D-94) |
| Wave | 3 (first examination; not in FA or E2) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: our prior reports (phase-10c census `~/.agentprov/migration-work/phase10c/census/bookkeeper@0fe09bb6e8c0.*`, phase-10d census, trial, reconcile and `r1` census), the profile, the identity table, the registry, `artefacts.toml`, DECISIONS, and desk research (`data/bookkeeper-agentdojo/research.json`: GitHub tree listing, repository documents and harness code, the 11 `results_*.json` run summaries). No run log was read and nothing here was computed from the logs. |
| Method | [`../README.md`](../README.md) |

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Repository | [sricursion/bookkeeper](https://github.com/sricursion/bookkeeper) ("Munim", a deterministic money gate), 2 commits, 0 issues/PRs/forks | GitHub API |
| Pin | `0fe09bb6e8c0c864cee5daa9451f2647c2c846be`, 2026-09-05T15:00:51Z = head of `main`; adds LICENSE, docs, Razorpay demo; touches nothing under `runs/agentdojo/` or `eval/agentdojo/` | GitHub API |
| Logs added by | `bb4ae402d6ff` (2026-09-05T08:34:24Z, first commit, no LICENSE yet) | GitHub API |
| Paper / data record | none (arXiv, Zenodo, HF searched); documentation = `README.md`, `eval/agentdojo/README.md`, `docs/numbers.md`, `runs/agentdojo/summary.md`, `results_*.json` | research.json |
| Harness | AgentDojo 0.1.35 (per logs; install undeclared), suite `v1` banking (`get_suite("v1","banking")`, `benchmark_version` null, D-102), attacks `important_instructions`, `tool_knowledge`; Munim as `GatedToolsExecutor`; custom `SteadyOpenAILLM` wrapper (documented for the g4 runs only; **[corrected: was "v2+ runs"; the wrapper used before gate v4 is not recorded]**) | `eval/agentdojo/run.py` at pin |
| Models / provider | `glm-5.3-flash` = Fireworks `accounts/fireworks/models/glm-5p3-flash`; `gpt-oss-120b` = Fireworks `accounts/fireworks/models/gpt-oss-120b`; `llama-3.1-8b` provider unrecorded | `results_*.json` `model_id` |
| Run date | 2026-09-05 02:45:22 to 13:41:03, naive **IST** (+05:30, per `finished_at` offsets), i.e. all before the first commit (14:04:24 IST) | phase-10c census `ts_range`; results files |
| Labels | `g<N>` = gate version (`GATE_VERSION`), `cap2` = per-action cap multiplier 2; untagged `-none`/`-munim` predate version tagging | `run.py` l.197, eval README |

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Tree entries at pin | 1,020 (5,937,000 bytes) | profile `expected_files/bytes`; GitHub tree; phase-10c census |
| Selected logs (`runs/agentdojo/*/*/*/*/*/*.json`) | 570 (3,900,025 bytes) | registry/`readme_corpora.toml` (census `/files`); phase-10d census; GitHub tree |
| Not selected | 450: 26 context artefacts (supporting), 299 Munim ledgers (`.jsonl`), 103 Razorpay run files, 22 other (code incl. `eval/agentdojo/*`, docs, tests, `summary.md`); 0 `.DS_Store`/`._*` | GitHub tree; profile |
| JSON parse ok | 570 / 570 (594 / 594 JSON blobs in the tree) | phase-10c census |
| Units / executions | 570 `agent_execution` / 570 | phase-10d census, trial (jobs 8 on all 570; jobs 3 on a 120-unit subset **[corrected]**) |
| Variants | `v1.k14` 566, `v1.k14.incomplete` 4 | census |
| Sealed clean / with issues | 565 / 5 (`incomplete_run` 4, `unexecuted_tool_call` + `retry_passes_inferred` 1) | trial |
| Register codes | `accounting_unverifiable` 569, `earlier_attempts_unobservable` 570, `incomplete_run` 4, `retry_passes_inferred` 1, `unexecuted_tool_call` 1 | trial |
| Messages | system 570, user 570, assistant 1,825, tool 1,346; tool calls 1,347 (all with `placeholder_args`, all null); tool errors 180 | phase-10c census |
| Outcomes (all files) | utility T 270 / F 296 / null 4; security T 167 / F 399 / null 4 | phase-10c census |

Per cell (pipeline dir × attack dir), from the git tree listing (file names only):

| Pipeline dir | `important_instructions` | `tool_knowledge` | pre-pass (`none`) | Total |
|---|---:|---:|---:|---:|
| `glm-5.3-flash-none` | 27 | 27 | 9 | 63 |
| `glm-5.3-flash-none-g4` | 27 | 27 | 9 | 63 |
| `glm-5.3-flash-munim` (gate v1) | 27 | - | 9 | 36 |
| `glm-5.3-flash-munim-cap2-g2` | 27 | 27 | 9 | 63 |
| `glm-5.3-flash-munim-cap2-g3` | 23 | - | 9 | 32 |
| `glm-5.3-flash-munim-g4-cap2` | 27 | 27 | 9 | 63 |
| `gpt-oss-120b-none` | 27 | 27 | 9 | 63 |
| `gpt-oss-120b-none-g4` | 27 | 27 | 9 | 63 |
| `gpt-oss-120b-munim-cap2-g2` | 27 | 5 | 9 | 41 |
| `gpt-oss-120b-munim-cap2-g3` | 10 | - | 9 | 19 |
| `gpt-oss-120b-munim-g4-cap2` | 27 | 27 | 9 | 63 |
| `llama-3.1-8b-none` | - | - | 1 | 1 |
| **Total** | 276 | 194 | 100 | 570 |

Attacked logs by user task: 0 → 167, 1 → 154, 2 → 149 (= 470); pre-pass logs by injection task: 0 → 12, 1-8 → 11 each (= 100). No benign user-task run exists.

## 3. Expected arms

| Facet | Values | Expected missing / extra |
|---|---|---|
| Model | `glm-5.3-flash`, `gpt-oss-120b`, `llama-3.1-8b` | llama is a one-log stray (62 of 63 cells missing) |
| Defence | `none` (two runs per model: untagged and `-g4`), `munim` at gate v1, v2 (`cap2-g2`), v3 (`cap2-g3`), v4 (`g4-cap2`); identity table keeps the label verbatim | gpt-oss has no v1 run |
| Attack | `important_instructions`, `tool_knowledge`; `none` = injection-task pre-pass | no clean-utility run |
| Suite | banking (v1) | only suite |
| Task cells | user tasks 0-2 × injection tasks 0-8 = 27 per attack, + 9 pre-pass per pipeline name | missing vs 63 per dir: glm v1 27, glm v3 31, gpt v2 22, gpt v3 44 (= 124) + llama 62; 12 × 63 − 570 = 186 |

**L1-05 / L2 stratum key:** (pipeline_dir, attack_dir) = 31 strata, because the pipeline dir carries model, defence and harness version; collapsing to the identity defence would pool replicates (`none` and `none-g4`) that ran with different sampling. L2 sample: 30 strata × 5 + 1 (llama) = **151 units**.

## 4. Expected outcome rates (comparison targets)

Metric mapping (`run.py`): utility under attack = mean of logged `utility` over the 27 attacked logs of a run; attack success = mean of logged `security` (AgentDojo: true = injection goal reached). Pre-pass logs are excluded from every reported rate (`security` there is the runner's constant True). Exact per-pair targets exist for the 11 cells with a results file (297 pairs, `utility_results` / `security_results` keyed `user_task|injection_task`); gate-v2 cells have aggregates in `summary.md` only.

| Stratum (dir / attack) | n | Utility T | Security T | Gate pair (all) allow/hold/deny | Source |
|---|---:|---:|---:|---|---|
| glm-none / II | 27 | 18 | 0 | - | `none/results_important_instructions.json` (02:56; `temperature` and `pipeline_name` keys absent **[corrected: was "temp null"]**) |
| glm-none / TK | 27 | 18 | 0 | - | `none/results_tool_knowledge.json` (12:49; `temperature` key absent **[corrected]**) |
| glm-munim (v1) / II | 27 | 18 | 0 | 10/5/1 (scope unrecorded: v1 schema has one `gate_stats`, no pair/all split **[corrected]**) | `munim/results_important_instructions.json` (03:04) |
| glm-munim-cap2-g2 / II | 27 | 17 | 0 | 9/4/0 | `summary.md` v2 13:03 |
| glm-munim-cap2-g2 / TK | 27 | 16 | 0 | 8/2/0 | `summary.md` v2 13:08 |
| glm-none-g4 / II | 27 | 18 | 0 | - | `none/results_important_instructions_glm-5.3-flash.json` |
| glm-none-g4 / TK | 27 | 18 | 0 | - | `none/results_tool_knowledge_glm-5.3-flash.json` |
| glm-munim-g4-cap2 / II | 27 | 18 | 0 | 9/0/0 (10/6/0) | `munim/results_important_instructions_glm-5.3-flash.json`; eval README |
| glm-munim-g4-cap2 / TK | 27 | 18 | 0 | 9/0/0 (same) | `munim/results_tool_knowledge_glm-5.3-flash.json` |
| gpt-none / II | 27 | 11 | 20 | - | `summary.md` v2 13:02 |
| gpt-none / TK | 27 | 12 | 14 | - | `summary.md` v2 13:08 |
| gpt-munim-cap2-g2 / II | 27 | 6 | 0 | 6/46/22 | `summary.md` v2 13:14 |
| gpt-none-g4 / II | 27 | 11 | 20 | - | `none/results_important_instructions_gpt-oss-120b.json`; README, numbers.md |
| gpt-none-g4 / TK | 27 | 13 | 14 | - | `none/results_tool_knowledge_gpt-oss-120b.json` |
| gpt-munim-g4-cap2 / II | 27 | 12 | 0 | 8/8/12 (9/11/12) | `munim/results_important_instructions_gpt-oss-120b.json` |
| gpt-munim-g4-cap2 / TK | 27 | 11 | 0 | 4/10/3 (same) | `munim/results_tool_knowledge_gpt-oss-120b.json` |
| glm-munim-cap2-g3 / II; gpt-munim-cap2-g2 / TK; gpt-munim-cap2-g3 / II; all pre-pass | 23; 5; 10; 100 | not reported | not reported | - | absent from every document |

L2 has about 5 per stratum (< 20), so L2 reports Wilson intervals only; the decisive comparison is the whole-population tally (H1-H4).

## 5. Known quirks

| Id | Expected | Source |
|---|---|---|
| `agentdojo.benign_security_constant` (art. `agentdojo.art.benign_security_constant`) | 100 files, origin rule on 99 (llama incomplete) | profile `observed`, census |
| `agentdojo.injection_task_as_user_task_prepass` (art. `agentdojo.art.injection_task_as_user`) | 100 files | profile, census |
| `agentdojo.args_mutated_in_place` | 565 files | profile, census |
| `agentdojo.placeholder_args_never_injection_evidence` | 1,347 present, all null | profile, census |
| `agentdojo.incomplete_run` (art. `agentdojo.art.incomplete_run`) | 4 files, 0 null-outcome among complete; the last cell of each partial run + llama | profile, census `issue_samples` |
| `agentdojo.silent_rerun_last_pass_only` (art. `agentdojo.art.silent_rerun`) | 1 null-final log (complete logs); phase-10c 3 incl. incomplete (reconciled) | profile, reconcile |
| `agentdojo.unexecuted_trailing_calls` (art. `agentdojo.art.max_iters_pending`) | 1 call in 1 log (`gpt-oss-120b-munim-cap2-g2/.../tool_knowledge/injection_task_1.json`) | profile, census |
| `agentdojo.package_version_not_code_identity` | 0 files without package version (all `0.1.35`) | profile |
| `agentdojo.defence_denial_message` (R1, D-113) | 180 denials, prefix `Declined by the account's money gate. `, `munim*` only; holds mapped as deny | profile, `r1` census, routing R1 |
| System prompt | 469-char AgentDojo default in 570 | profile, phase-10c census |
| `agentdojo.art.naive_timestamp` | naive `evaluation_timestamp`, IST; no per-call times | artefacts.toml (generic; scope does not list this source) |
| `agentdojo.art.defence_benign_intervention` | gate acts in pre-pass logs (§7 H5) | artefacts.toml (scope does not list this source) |
| Identity | model from `pipeline_dir` (table sha `a4c3b7cc…`), `pipeline_name` = dir in 570 | profile, census `prefix_pipeline_dir_name` |
| Evidence | `verified_code = []`: D rules via `_unverified` twins (class I), D-24, D-103 | profile |
| Accounting | `unverifiable` 569, `consistent` 1 | census |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2; selection by `include` glob; 26 `context_artefacts`; ledgers, Razorpay runs, `eval/agentdojo/*`, `summary.md` not selected (record reason) |
| L1-02 strict parse | yes | expect 0 defects |
| L1-03 encodings | yes | AgentDojo #214 escape residues possible in tool content: count, class expected-known |
| L1-04 duplicates | yes | within part: `none` vs `none-g4`, munim versions (same cells, different runs); cross-corpus: expect 0 (no other corpus with glm-5.3-flash or Munim) |
| L1-05 arm coverage | yes | §2-§3 table; plus the whole-population outcome tally for H1-H4 |
| L1-06 secrets / account paths | yes | expect 0 in logs and in the 26 context artefacts (desk check of the 11 results files: no account-path-like string, no `ledger_dir`) |
| L1-07 timestamps | yes (partly) | presence, parse, zone (naive IST), range, run windows (H6); within-unit monotonicity n/a (one timestamp per file) |
| L1-08 degenerate | yes | expect 0 empty, 4 incomplete, 0 `error`, 4 null utility/security, 1 null-final, 1 unexecuted trailing call |
| L2 import, validate, recompute, determinism | yes | trial: 0 failures, 0 failing checks, jobs 8 (570) vs jobs 3 (120-unit subset): 0 differing objects in subset compare **[corrected: not a full 570-unit byte comparison]** |
| L2 A2 / A3 classes | yes | expect only the trial's register codes |
| L2 evidence classes | yes | D rules only as `_unverified` twins; denials class I (`agentdojo.defence_denial_message@1`) |
| L2 degenerate / adapter_defect | yes | expect 0 / 0 |
| L2 identity | yes | 12 dirs → models and verbatim defence labels per table; check no provider id is claimed |
| L2 redaction | yes | expect no account path in AER/SEM/PROV |
| L2 withholding | conditional | only if L1-06 finds a secret-like string; none expected |
| L2 outcome sanity | yes (Wilson only) | §4; n per stratum ≤ 5 |
| Delta since E2 | no | not examined in FA/E2 |

## 7. Hypotheses (falsifiable)

| # | Expectation | Refuted if |
|---|---|---|
| H1 | For the 11 cells with a results file (§4), logged `utility` and `security` equal `utility_results`/`security_results` for each of the 297 pairs | any pair differs |
| H2 | The 5 gate-v2 cells reproduce `summary.md`: glm-cap2-g2 II 17/0, TK 16/0; gpt-none II 11/20, TK 12/14; gpt-cap2-g2 II 6/0 (utility T / security T of 27) | any count differs by ≥ 1 |
| H3 | Attacked `security == true` = 68 in all = 20 + 14 in `gpt-oss-120b-none` + 20 + 14 in `-none-g4`; 0 in every munim dir, every glm dir and every unreported partial arm (census arithmetic: 167 − 99 pre-pass constants) | any success in a munim/glm/partial arm, or total ≠ 68 |
| H4 | Attacked `utility == true` over the 16 reported cells = 235; the remaining 35 of the census's 270 lie in pre-pass and partial-arm logs | sum ≠ 235 |
| H5 | Denial messages: 180, all in `munim*` dirs; 0 tool errors in `none` dirs; exactly 6 in `glm-5.3-flash-munim` (5 hold + 1 deny; assumes the v1 `gate_stats` counted all episodes, which the v1 results schema does not state **[fact-check note]**), 6 in `glm-5.3-flash-munim-g4-cap2` (all in pre-pass logs), 36 in `gpt-oss-120b-munim-g4-cap2` (3 pre-pass holds; II 8 hold + 12 deny; TK 10 hold + 3 deny); ≥ 6 in `glm-…-cap2-g2` attacked logs; ≥ 68 in `gpt-…-cap2-g2` II logs (46 hold + 22 deny). Assumes one tool message per gate hold/deny | any exact count differs or a bound is violated |
| H6 | Timestamps are naive, 2026-09-05 02:45:22-13:41:03, and each documented run's logs lie in its window ±60 s: glm-none II 02:45:22-02:56:13; glm-munim 02:56:13-03:04:40; glm-none TK 12:44:07-12:49:30; gpt-none-g4 II 13:16:34-13:23:04; gpt-munim-g4 II 13:23:04-13:31:27; glm-none-g4 II 13:16:36-13:24:03; glm-munim-g4 II 13:24:03-13:31:55; gpt-none-g4 TK 13:31:37-13:36:55; gpt-munim-g4 TK 13:36:55-13:41:21; glm-none-g4 TK 13:32:02-13:36:09; glm-munim-g4 TK 13:36:09-13:40:18 (= `finished_at` − `seconds`) | any log outside its window; in particular any `glm-5.3-flash-none` log at 12:53-13:10 (then the v2 glm none rows were fresh runs, not cache reuse) |
| H7 | Each partial arm is a prefix of AgentDojo's (user task, injection task) order ending in its one incomplete log (glm-cap2-g3 II: ut2×it4; gpt-cap2-g2 TK: ut0×it4; gpt-cap2-g3 II: ut1×it0; llama: it0 pre-pass) | a hole before the last cell, or an incomplete log elsewhere |
| H8 | Each (pipeline dir, user task, attack, injection task) occurs exactly once; path facets agree with logged fields in 570/570 | duplicate or disagreement |
| H9 | Harness-authored assistant turns (`[malformed tool call arguments:` or `[response truncated at the output limit]`) = 0 | ≥ 1 (then a finding: the mapper attributes harness text to the model) |
| H10 | The injection text in `gpt-oss-120b` attacked logs does not address the model as "GLM" | "GLM" in ≥ 1 gpt-oss injection (S3 documentation-mismatch: `--model-family` default) |
| H11 | 0 byte-identical files within the part; 0 identical trajectories across corpora | ≥ 1 cross-corpus repeat (within-part identical trajectories between `none-g4` and `munim-g4-cap2` glm pairs are expected and reported, not a finding) |
| H12 | 0 secret-like strings and 0 account paths in the 570 logs and the 26 context artefacts | ≥ 1 |
| H13 | Pre-pass: 100 logs, `security` true in 99 complete; in each model's munim dirs pre-pass utility ≤ its `none` dirs' (the gate holds injection goals run as user tasks) | a munim dir exceeds the model's best `none` dir by ≥ 2 of 9 |

## 8. Discrepancy leads carried to the dossier

No paper: targets are repository files, and gate-v2 per-pair results were overwritten (only `summary.md` aggregates). Four unreported partial or stray arms (§2). `glm-5.3-flash-none`/`-munim` results files carry no `temperature` key (sampling unrecorded; if the stock AgentDojo 0.1.35 wrapper was used it drops 0.0) **[corrected: was "temperature unset"]**, `-g4` runs record 0.0; the identity table pools `none` and `none-g4` as defence `none`. The pinned `run.py` is newer than every log (name format, missing `ledger_dir`); gate v1-v3 code is absent. The identity table calls the cap/g labels unexplained (`run.py` explains them) and omits the Fireworks model ids. Ledgers (299), `eval/agentdojo/run.py`, `munim_defense.py` and `summary.md` are not stored as context artefacts; ledger run tags do not map one-to-one to log dirs (131118: 32 episodes for two v3 runs; 130234: 35 for 36 logs; 130841: 7 for 5). AgentDojo #181 (banking injection tasks 0/1/3 score any transfer to the attacker) affects logged and reported ASR alike. `artefacts.toml` scopes omit this source. Licence: the logs were first committed (`bb4ae402`) with README "License: MIT." and pyproject `license = MIT` (no LICENSE file); the pin relicensed to GPL-3.0-or-later, and `runs/agentdojo/` is identical at both commits (881 blobs, same SHAs) **[corrected: was "logs committed before the LICENSE"]**. README/`docs/numbers.md` say GLM 5.3 Flash had "nothing held"; that holds for pair episodes only (results all-episode stats: 6 holds in the g4 II pre-pass).

## Fact-check (2026-10-14, adversarial pass)

Re-opened at the pin through the GitHub API: the git tree (1,020 blobs / 5,937,000 bytes, not truncated; 570 selected logs / 3,900,025 bytes; 299 ledgers; 103 Razorpay files; 594 `.json`), every per-cell count of §2 and the per-user-task / per-injection-task counts (from file names only), the last cell of each partial arm (H7), `runs/agentdojo/summary.md`, all 11 `results_*.json`, `eval/agentdojo/README.md`, `docs/numbers.md`, `README.md`, `pyproject.toml`, `LICENSE` (blob `f288702d`, 35,149 bytes, standard GPL v3 text), `eval/agentdojo/run.py` (l.33 `GATE_VERSION = 4`, l.197 name format, l.236 `MODEL_NAMES.setdefault`, l.279 `ledger_dir`, l.311 `--model-family` default `GLM`), `munim_defense.py` (decline prefix), the two commits and the pin diff; AgentDojo v0.1.35 (`a75aba76`, PyPI 2025-10-27, still latest) `benchmark.py` (reuse checks l.101 and, for the pre-pass, l.268), `openai_llm.py` l.162, `models.py` (no key that is a substring of these pipeline names), `v1/banking/injection_tasks.py` (#181 pattern at l.61/107/208), issues #67/#181/#194/#208/#214 states; arXiv 2406.13352 v1-v3 dates; Zenodo (0 hits), HF (none), our census/trial/registry/profile/identity table/`artefacts.toml`.

Confirmed: all 16 reported-cell utility/security counts of §4 against their cited file (per-pair tallies of the 11 results files: 18/0 in the 7 glm files, 11/20, 13/14, 12/0, 11/0 for gpt g4; summary.md v2 rows 17/0, 16/0, 11/20, 12/14, 6/0 and gate triples); H4 sum 235; H6 windows (= `finished_at` − `seconds`); counts, arms, missing-cell arithmetic (186), 151-unit sample size; the ledger-tag episode counts (36 untagged + 263 tagged); identity-table wording; no `artefacts.toml` scope lists this source.

Corrected: (1) early results files have no `temperature`/`pipeline_name` key (not null); (2) `SteadyOpenAILLM` documented only for the g4 runs, not "v2+"; (3) trial determinism compared jobs 8 (570) with jobs 3 on a 120-unit subset, not 570 vs 570; (4) gate v1 `gate_stats` scope is unrecorded (H5's exact 6 rests on it); (5) licence history: the logs were first published under a declared MIT licence (README and pyproject at `bb4ae402`, no LICENSE file) and relicensed to GPL-3.0-or-later at the pin; `runs/agentdojo/` is byte-identical (881 blob SHAs) at both commits, so the claim "logs committed before any LICENSE" was incomplete; (6) the first-commit tree is now verified directly (1,012 blobs, 570 selected logs), not inferred from the pin diff; (7) the pin's README change is +2/−1 lines. Unverifiable: whether pre-v4 runs used the stock wrapper; the ledger-tag-to-run mapping; the census figures that come from logs (taken from our own reports, not recomputed).

