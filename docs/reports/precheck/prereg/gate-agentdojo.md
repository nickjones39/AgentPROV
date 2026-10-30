# Pre-registration: `gate-agentdojo`

| | |
|---|---|
| Corpus | `gate-agentdojo` (family `agentdojo`, profile `gate-agentdojo` v1, dialect/mapper `agentdojo.tracelogger`, variants `v1.k14`, `v1.k14.incomplete`); own AGPL-3.0-only corpus (D-94) |
| Parts | `head`: GitHub `dafarusd/gate` @ `925b99260beec53d94bd48b587b0bdc33614e3df` (2026-09-26T20:57:02Z, still HEAD) |
| Wave | 3 (first examination; not in FA or E2, so there is no delta since E2) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Inputs: our own reports (phase-10c census summaries `~/.agentprov/migration-work/phase10c/census/gate@925b99260bee.*`, `docs/reports/phase10d/gate-agentdojo.{census,trial,reconcile}.json`, `r1/gate-agentdojo.census.json`), the profile, the identity table, the registry, `artefacts.toml`, DECISIONS, the GitHub tree listing at the pin, and desk research (`data/gate-agentdojo/research.json`). Nothing here was computed from the raw logs. |
| Method | [`../README.md`](../README.md) |

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Repository | <https://github.com/dafarusd/gate>; 0 tags, releases, issues, forks; one branch `main` | GitHub API |
| Documents | `README.md` (workspace headline, capability ladder, hold-out), `STATE.md` (run log of `results/`), `paper/DRAFT.md` (unpublished draft, revised 2026-08-25; `gatellml/` arms), `gatellml/STATE.md` (pre-registrations and Addenda A-R incl. the 2026-09-18 arms g4-g8), `gatellml/results/FINAL_SUMMARY.md` | pin |
| Paper / data record | none (no arXiv, DOI, Zenodo, HF, Figshare) | research.json |
| Harness | AgentDojo 0.1.35 (unpinned install). `agentdojo.scripts.benchmark` for `results/p1-*`, `runs*` (pipeline `local`, suites v1.2.2); `src/run_defended.py` for all else (suites v1.2, name `local-<model>-gate-<arm>[-echo]`) | `src/phase1_before.sh`, `src/run_defended.py`, phase-10c census |
| Providers | Venice API (OpenAILLM behind a sanitising proxy, hidden prompt disabled except `v1-CONTAMINATED-superseded`): 480b and ladder models. Ollama (LocalLLM): `qwen3-coder-32k:latest` arms and `local` | STATE.md, `run_defended.py` |
| Defences | PolicyGate v1/v2/v3/v3.1 (label `gate-all`), GatellmGate auto / hand v1 (withdrawn) / v2 / v3 manifests (label `gate-gatellm`), plus AnswerEchoFilter (`-echo`). Both gates strip blocked calls from the assistant message and append error tool results starting `BLOCKED by security policy` (PolicyGate: `BLOCKED by security policy: <rule>...`; GatellmGate: `BLOCKED by security policy (<rule>)...`, **corrected** in fact-check) | `src/defenses/policy_gate.py`, `src/gatellm_gate.py` |
| Run dates | 2026-08-20 15:21:57 .. 2026-09-18 15:39:18 (naive local time; Aug 3,421, Sep 449 logs) | phase-10c census `ts_range`, `ts_month` |

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Tree blobs at pin | 4,155 (33,233,807 B; PNG 53,663 B absent locally, others 33,180,144 B) | profile `expected_files`; GitHub tree; trial `pin.absent_blobs` |
| Selected files (profile globs) | **3,872** (32,006,982 B; 815..215,378 B) | `readme_corpora.toml` (census `/files`); phase-10d census; GitHub tree |
| Distinct blobs / byte-identical pairs | 3,870 / 2 (the `results/demo/*` copies of a v2 and a v6 log, documented in `results/demo/SOURCE.md`) | reconcile; GitHub tree |
| Not selected | 283 (8 non-run JSON, 105 `.log`, 80 `DONE`, 9 `.SHA`, 1 `.echo.jsonl`, code, docs) | GitHub tree |
| JSON parse ok | 3,872 / 3,872 | phase-10c census |
| Executions | 3,870 (2 `dedup.collapsed`); units agent_execution 3,868 + outcome_only 2 | trial (jobs 8) |
| Sealed clean / with issues | 2,822 / 1,048; validation 68 checks, 0 failed | trial |
| Variants | `v1.k14` 3,869 + `v1.k14.incomplete` 3 (over files) | census |
| Register codes (executions) | accounting_unverifiable 3,868; earlier_attempts_unobservable 3,868; identity_unresolved 217; orphan_tool_result 818; unexecuted_tool_call 13; no_execution_observed 2; no_outcome_recorded 2; incomplete_run 1 | trial |
| `benchmark_version` | v1.2: 3,655 (+2 demo); v1.2.2: 215 (all `local`) | phase-10c census |
| Outcome keys (3,870 distinct) | utility T 1,722 / F 2,145 / missing 3; security T 1,616 / F 2,251 / missing 3 | phase-10c novel census |

Per pipeline directory × task kind (files; GitHub tree at pin, demo excluded):

| Pipeline dir | Attacked | Benign user task | Pre-pass | Total |
|---|---:|---:|---:|---:|
| `local` (unresolved, D-105) | 140 | 61 | 14 | 215 |
| `...-480b-...-gate-off` | 340 | 164 | 89 | 593 |
| `...-480b-...-gate-all` | 471 | 98 | 155 | 724 |
| `...-480b-...-gate-gatellm` | 488 | 312 | 98 | 898 |
| `...-480b-...-gate-gatellm-echo` | 42 | 20 | 14 | 76 |
| `qwen3-coder-32k:latest` off / all / gatellm | 63 / 203 / 72 | 41 / 81 / 82 | 21 / 35 / 24 | 125 / 319 / 178 |
| 235b, 9b, 80b × off and all (each) | 70 | 10 | 14 | 94 |
| 35b off / all | 70 / 70 | 10 / 0 | 14 / 14 | 94 / 84 |
| **Total** | **2,379** | **929** | **562** | **3,870** |

Suites: workspace 2,508, travel 634, slack 483, banking 245 (+2 demo workspace). Attack labels: important_instructions
2,107; `holdout_h01..h10` 272 (9 × 30, h03 2); none 1,491 (= `benign_security_constant` files).

## 3. Expected arms

| Facet | Values | Expected missing / extra |
|---|---|---|
| Model | 480b, 32k, 235b, 9b, 80b, 35b (identity table, verbatim); `local` unresolved (215) | demo copies unresolved (2) |
| Defence | none (`gate-off`, `local`), `gate-all`, `gate-gatellm`, `gate-gatellm-echo` | version (PolicyGate v1..v3.1, manifest auto/v1/v2/v3) only in the experiment dir |
| Attack | important_instructions; holdout_h01..h10 (480b workspace only); none | h03: 14 of 15 cells per arm missing, the 1 present per arm holds no messages |
| Suite | workspace (all models); banking, slack, travel (480b and 32k only, user tasks 0-2) | ladder models: workspace only, by design |
| Experiment | 152 dirs (`results/` 55 = 37 top-level dirs with each of the 20 `p3-holdout*/hNN_*` attack subdirs counted separately; `gatellml/results/` 97; **corrected** from 70 / 82 in fact-check) | `v1-CONTAMINATED-superseded`: 61 of 70 attacked (user_task_4 × 9 missing); no `ladder-qwen3-6-35b-a3b-benign-gated` dir |
| Repeats (extra, by design) | c1/c2 ×10, sk1/tk1 ×5, smoke dirs (4), pre-passes rerun per attack dir | 651 (pipeline, suite, task, attack, file) keys repeat across experiments (1,897 files) |

L2 strata (pipeline × suite × attack_dir): 83 incl. demo, so the 300 cap applies; the sampler records `experiment` and
task kind for every drawn unit.

## 4. Expected outcome rates (L2 comparison targets)

Metric mapping: `security == true` = attack succeeded (AgentDojo; README and STATE.md say so). Two tools compute the
published numbers. **`src/aggregate.py`** (README, STATE.md: `results/`) takes utility under attack over attacked +
pre-pass files (59.1% = 91/154) and ASR over attacked files only. **`suite_summary.py`** (paper, FINAL_SUMMARY,
Addenda: `gatellml/results/`) uses attacked `injection_task_*.json` only, excludes pre-pass ("calib"), takes benign over
`user_task_*/none/none.json`, and counts blocks as episodes with a tool error containing `BLOCKED`. The L2 comparison uses
attacked files for ASR and benign user tasks for benign utility. Pre-pass and benign `security` stay out of every rate.

Per experiment (exact targets for H1):

| Experiment dir(s) | Pipeline | ASR | Utility under attack | Benign utility | Ref |
|---|---|---|---|---|---|
| p1-attack / p1-benign | `local` (32k) | 2/140 | 91/154 (incl. pre-pass) | 18/40 | README headline; STATE |
| p2-gateall-attack / -benign | 32k gate-all (v1) | 0/140 | 90/154 | 17/40 | README headline |
| v2-venice-undefended-clean / v4-benign-ungated | 480b off | 5/70 | 35/84 | 8/10 | README headline, ladder |
| v3-venice-gateall / v4-benign-gated | 480b all (v1) | 0/70 | 28/84 | 7/10 | README headline |
| p3-adaptive-gateall / -gatev2 / v7-focused-gatev31 | 480b all v1 / v2 / v3.1 | 1/28 / 0/28 / 0/28 | 35.7% / 7.1% (v1, v2) | v5-benign 3/10; v7-benign 7/10 | README focused grid; STATE |
| v1-CONTAMINATED-superseded | 480b off | ≈5% (3/61) | - | - | STATE "Venice arm" |
| ladder 235b / 80b / 9b / 35b | off; all | 22/70, 0/70, 0/70, 0/70; all 0/70 | - | ungated 8/10, 9/10, 4/10, 0/10 | README ladder |
| p3-holdout h01..h10 / -CONTROL | 480b all (v1) / off | 0/135 / 0 | 61-72% | - | README; STATE Phase 3 |
| b4 / b3 | 480b off / all | 24/27 / 0/27 (25 blocks) | 9/27 / 6/27 | b2 11/16 / b1 9/16 | paper §2; FINAL_SUMMARY |
| t4 / t3 | 480b off / all | 4/21 / 3/21 (2) | 10/21 / 10/21 | t2 14/20 / t1 15/20 | paper §2 |
| s4 / s3 | 480b off / all | 11/15 / 4/15 (11) | 15/15 / 7/15 | s2 17/21 / s1 6/21 | paper §2 |
| gw2, g-banking, g-slack, g-travel | 480b gatellm auto | 0/140, 0/27, 3/15, 4/21 | 56/140, 7/27, 7/15, 9/21 | gw1 4/10, gw1-full 20/40; g-* gated 7/16, 6/21, 11/20; ungated 13/16, 16/21, 13/20; w2 29/40 | paper §4.1; FINAL_SUMMARY |
| g2-* (withdrawn) | 480b gatellm v1 | slack 0/15, travel 0/21 | 5/15, 0/21 | 2/21, 0/20 | paper §4.2 |
| g3-* | 480b gatellm v2 | 0/15, 2/21 | - | 2/21, 10/20 | paper §4.2 |
| g4-* / g5-* | 480b gatellm v2/v3 | 0/15, 2/21 / 0/15, 3/21 | - | 2/21, 9/20 / 2/21, 11/20 | gatellml/STATE J, L |
| g6-workspace-* | 480b gatellm auto | 0/140 | 64/140 | 18/40 | gatellml/STATE O |
| g7-* / g8 (echo) | 480b gatellm-echo | 0/21 / 0/21 | 13/21 / 13/21 | 10/20 | gatellml/STATE P, Q |
| l2 / l4 / l5 ungated vs gate | 32k off / all | 1/15 vs 0/15; 4/21 vs 2/21; 13/27 vs 0/27 | 10/15 vs 5/15; 16/21 vs 19/21; 8/27 vs 7/27 | l1 10/21 vs 4/21; l3 11/20 vs 11/20 | paper §6; FINAL_SUMMARY |
| l2/l4 gB (withdrawn); l6 gB2 | 32k gatellm | 0/15, 0/21; 0/15, 2/21 | 5/15, 0/21 | l1 2/21, l3 0/20; l6 2/21, 7/20 | paper §4.2, §6 |
| c1 / c2; sk1 / tk1 | 480b all / off; all | 0/10 / 0/10; 5/5 / 5/5 | - | - | paper §5; FINAL_SUMMARY |
| v5-frontier-fullgrid-gatev2, v6-focused-gatev3 | 480b all | **not reported**; 0/70, 0/28 implied (H2) | - | v6-benign not reported | census arithmetic |

Pooled ASR per L2 stratum (attacked files): `local` ws 2/140; 480b off ws 8/141 (≈); 480b all ws 1/262; 480b gatellm ws
0/281, slack 3/75, travel 11/105, banking 0/27; echo travel 0/42; 480b off banking 24/27, slack 11/15, travel 4/21; 480b
all banking 0/27, slack 9/20, travel 8/26; 32k off banking 13/27, slack 1/15, travel 4/21; 32k all ws 0/140, banking 0/27,
slack 0/15, travel 2/21; 32k gatellm slack 0/30, travel 2/42; 235b off 22/70; every other ladder stratum 0/70; holdout
strata 0/15 (h03 0/1, empty). L2 samples about 5 per stratum, far below 20, so L2 reports Wilson intervals only; the exact
test is H1 and H2 at L1-05.

## 5. Known quirks

| Id | Expected | Source |
|---|---|---|
| `agentdojo.benign_security_constant` | 1,491 files / 1,491 judgements | profile, census |
| `agentdojo.injection_task_as_user_task_prepass` | 562 files | profile, census |
| `agentdojo.defence_denial_message` (R1, D-113) | 1,101 denials, `gate-*`, prefix `BLOCKED by security policy`, content = error; 1 more in a `local` log stays a tool error | profile, r1 census |
| `agentdojo.args_mutated_in_place` | 3,444 files (3,618 before R1; 174 logs hold only denied calls) | profile, r1 census |
| `agentdojo.placeholder_args_never_injection_evidence` | 8,334 present, all null (10c: 8,329, difference = demo copies) | profile, reconcile |
| `agentdojo.provider_call_id_anomalies` | null ids 1,848 in 790 logs; 1 log repeats an id | profile |
| `agentdojo.unexecuted_trailing_calls` | 13 calls in 13 logs | profile |
| `agentdojo.incomplete_run` | 3 files (`v1.k14.incomplete`), 0 null-outcome | profile |
| `agentdojo.empty_messages_without_outcome` | 2 (the h03 attacked logs, 815 B each) | profile |
| `agentdojo.silent_rerun_last_pass_only` | 0 null-final logs | profile |
| `agentdojo.package_version_not_code_identity` | 0 without version (all `0.1.35`) | profile |
| Orphan tool results (R6) | 819 logs (818 executions): gates strip the blocked call from `tool_calls` | census, routing R6 |
| Identity | 217 unresolved = 215 `local` + 2 demo; 3,655 via `tables/gate_pipeline_dirs.toml` (class I) | trial, table |
| System prompt | AgentDojo default (469 chars, digest `a021a92b...`) in all 3,868 non-empty logs | 10c census, profile |
| Tool errors | 1,780 tool messages with an error (1,101 denials + 679 other) | 10c census |
| Path/field | 2 mismatches = the 2 empty h03 logs (no fields) | 10c census `path_agree` |
| Evidence | `verified_code = []`; every D rule via its `_unverified` twin (D-24, D-103) | profile |
| `artefacts.toml` | no entry is scoped to `gate-agentdojo` (scopes list `agentdojo-upstream`, rope, agentdyn, mandate, survey only); generic classes apply by analogy: `naive_timestamp`, `incomplete_run`, `empty_log`, `injection_task_as_user`, `benign_security_constant`, `defence_benign_intervention` | artefacts.toml |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2: 3,872 selected, 283 not selected with reason (include globs, `context_artefacts`) |
| L1-02 strict parse | yes | expect 0 defects (10c parse ok 3,880 JSON) |
| L1-03 encodings | yes | holdout h05 (Spanish) and h10 (homoglyph) payloads: non-ASCII and confusables expected in tool content, by design; AgentDojo #214 `\uXXXX` residues possible; count, class expected-known |
| L1-04 duplicates | yes | byte-identical = exactly the 2 demo pairs; trajectory repeats expected in pre-passes and k-repeats; cross-corpus: none expected (models unique to this source) |
| L1-05 arm coverage | yes | §3 grid + whole-population outcome tally (H1, H2) |
| L1-06 secrets / account paths | yes | expect 0 credentials (Venice key from env, never logged) and 0 account paths; AgentDojo's synthetic codes and IBANs may trip detectors: count by pointer only |
| L1-07 timestamps | partly | presence, parse, naive zone, range 2026-08-20..2026-09-18, per-experiment ranges vs STATE chronology; within-unit monotonicity n/a (one timestamp per file) |
| L1-08 degenerate | yes | 2 empty (h03), 3 incomplete, 13 trailing unexecuted, 0 run errors (`error` null in all) |
| L2 import, validate, recompute, determinism | yes | trial: 0 failures, byte-identical across jobs 8/3 |
| L2 A2 / A3 classes | yes | expect only the trial's register codes; orphan results unlinked (R6), never an invented request link |
| L2 evidence classes | yes | D rules only as `_unverified` twins; denials class I deny decisions, no `tool_execution` |
| L2 degenerate / adapter_defect | yes | expect 0 / 0 |
| L2 identity | yes | table rows per pipeline dir; `local` and demo unresolved; check the 2 dedup survivors (H4) |
| L2 redaction | yes | expect no account path in AER/SEM/PROV |
| L2 withholding | conditional | only if L1-06 finds a real secret |
| L2 outcome sanity | yes (Wilson only) | §4 pooled targets |
| Delta since E2 | no | not examined in FA or E2 |

## 7. Hypotheses (falsifiable)

| # | Expectation | Refuted if |
|---|---|---|
| H1 | Tallying each experiment dir with the paper's reading (§4 mapping) reproduces every count in the §4 table | any count differs by ≥ 1 (≥ 1 point for the % rows) |
| H2 | Attacked `security == true` = 125 over the 3,870 distinct logs (1,616 − 1,491 benign constants; 126 if one of the 3 logs without `security` is benign), of which v1-CONTAMINATED 3, v5-frontier-fullgrid-gatev2 0, v6-focused-gatev3 0, and the unreported `smoke-gatellm` attacked cell (1 log) 0. Caveat (fact-check): the v1-CONTAMINATED 3 is inferred from STATE.md's "5%", which is not an exact count, so the v5/v6 split is conditional on it | total outside 125..126, or v5/v6 > 0 (then the README omits successes) |
| H3 | `local` = p1-attack 154 + p1-benign 40 + runs-benign 10 + runs-benign-32k 10 + runs 1; all `benchmark_version` v1.2.2; every other log v1.2 | any other split |
| H4 | The 2 dedup-collapsed executions are stored under `results/demo/*` with `identity_unresolved`, the v2/v6 paths recorded as duplicates | the stored origin is the run path (then 215 unresolved) |
| H5 | Logs with an orphan tool result (819) ⊆ logs with ≥ 1 `BLOCKED by security policy` message; none outside `gate-*` dirs except the one `local` log | ≥ 1 orphan without a denial, or ≥ 2 denial logs in `local` |
| H6 | Denial messages = 1,101 in `gate-*`; 0 in any `gate-off` dir | any denial in `gate-off` |
| H7 | September-dated logs (449) = exactly the 449 files of g4 (90 incl. g4-smoke), g5 (89), g6 (194), g7 (48), g8 (28); **corrected** in fact-check (the earlier "425 + 24 others" mis-added the GitHub tree counts) | any September-dated log outside g4..g8, or any August timestamp inside g4..g8 |
| H8 | Timestamps per experiment follow STATE chronology: p1/runs 2026-08-20, p2..v7 and ladder 2026-08-21/22, gatellml b..s/t/l/c/g/g2/g3/l6 2026-08-23/24, g4..g8 2026-09-18 | any experiment outside its documented day ± 1 |
| H9 | No (pipeline, suite, task, attack, injection) cell occurs twice within one experiment dir; resumed arms (b4, c2) show one session gap at most | duplicate within a dir |
| H10 | 0 credentials and 0 account paths in the 3,872 files | ≥ 1 |
| H11 | `-echo` logs (76): no final assistant text in g7/g8 attacked injection_task_6 cells contains "Riverside" (filter removed it) | ≥ 1 occurrence |

## 8. Discrepancy leads carried to the dossier

- The 215 `local` logs have documented models (STATE.md, `src/phase1_before.sh`): 32k for 204, qwen3-coder:30b at 4k
  context for 11. A D-92 class-I row is possible; this is a decision for the family owner.
- `gate-all` and `gate-gatellm` each fold several defence versions. The version appears only in experiment names, and
  the README's "v3.1: 0 in 373" includes cells run with v1.
- Defence-edited logs: blocked calls are stripped from assistant messages, `-echo` final answers are post-filter, and
  the v1-CONTAMINATED Venice hidden prompt is unlogged.
- The code that ran is not public: the `.SHA` commits are in a private clone, and the substring defect was fixed after
  every PolicyGate run.
- LocalLLM defects (AgentDojo #150, #202, #219, #220) bias the 32k and `local` arms downwards.
- No `artefacts.toml` entry is scoped to this source. Proposed entries go through the orchestrator if L1 confirms them.

## Fact-check (adversarial, 2026-10-14, before any data check)

Method: re-opened every cited document at the pin through the GitHub API (README.md, STATE.md, paper/DRAFT.md,
gatellml/STATE.md, gatellml/results/FINAL_SUMMARY.md, results/demo/SOURCE.md, LICENSE, NOTICE, src/aggregate.py,
gatellml/src/suite_summary.py, src/phase1_before.sh, src/run_defended.py, both gate modules, gatellml/lang/runtime.py),
recomputed the structural counts from the git tree listing at the pin (paths and sizes only, no payload), and re-read our
own phase-10c/10d/r1 reports. No raw log was read.

Confirmed:
- Pin `925b9926` = HEAD of `main` (2026-09-26T20:57:02Z); 0 tags, releases, issues, forks. Tree: 4,155 blobs, 33,233,807 B,
  not truncated; PNG 53,663 B. Profile globs select 3,872 files (32,006,982 B, 815..215,378 B), 3,870 distinct blob ids;
  the only duplicates are the 2 `results/demo/*` copies of the v2 and v6 `user_task_2 × injection_task_2` logs. 283 not selected.
- Per pipeline × task-kind table, suite totals, attack labels (2,107 / 272 / 1,491), 83 strata incl. demo, 2,624 keys
  with 651 repeated (1,897 files): all reproduced from the tree listing. v1-CONTAMINATED: 61 attacked (user_task_4 has 5 of 14).
- Trial, census, reconcile and r1 figures (3,870 executions, 2,822 / 1,048, register codes, variants, 1,101 denials,
  3,444 / 3,618 args-mutated, 1,848 null ids in 790 logs, 13 trailing calls) match our reports. Phase-10c novel census:
  utility T 1,722 / F 2,145, security T 1,616 / F 2,251, v1.2 3,655 / v1.2.2 215, Aug 3,421 / Sep 449, ts range as stated.
- Every §4 outcome number was found in the cited table/section: README headline, focused grid and ladder; STATE.md
  Phase 1 FINAL, HEADLINE TABLE, Phase 3, Gate evolution; FINAL_SUMMARY (all b/t/s/g/g2/gw/l/w2 rows, c1/c2, sk1/tk1 5×1/1);
  paper §2, §4.1, §4.2 (g3, l6, withdrawn arms), §5, §6; gatellml/STATE Addenda F, J, L, O, P, Q. Utility-under-attack
  fractions (91/154, 90/154, 35/84, 28/84) are consistent with `aggregate.py` (all files with outcome keys, pre-pass
  included); `suite_summary.py` excludes pre-pass ("calib") and counts block episodes. The README's 0-in-373 = 140 + 70 + 28 + 135.
- Paper attribution: the draft's §1 names the same model, AgentDojo v1.2 suites and `gatellml/results/` raw JSON; its §2
  table labels the gated column "PolicyGate v3.1", which answers the version question for the gatellml s/t/b gate arms.
- Harness: `run_defended.py` defaults to `--benchmark-version v1.2` and the `local` name prefix; AgentDojo v0.1.35
  (tag `a75aba76`) `scripts/benchmark.py` defaults to v1.2.2; PR #130 (merged 2025-10-27) adds v1.2.2 versions of
  workspace UserTask16 and banking UserTask6 only (plus a helper function). Issues #150, #161, #168, #188, #201, #202,
  #214, #219, #220 open and #189 closed, titles as described. Both gates strip blocked calls from `tool_calls`.
- Private-clone SHAs (5c11374, d59e1d4, ac1077f, 5266dcb, ab27de2, 98f0692): the GitHub API returns 422 for each.
- Licence: LICENSE is the AGPL v3 text (blob `bae94e18`), GitHub detects AGPL-3.0; NOTICE as summarised.
- No data record: Zenodo, Hugging Face, arXiv and Figshare queries all return 0 hits.

Corrected:
- §3 Experiment: 152 = `results/` 55 + `gatellml/results/` 97 (was 70 / 82).
- §7 H7: the g4..g8 directories hold 449 files (90 + 89 + 194 + 48 + 28), which equals the census September count, so
  no September log is unexplained (was "425 + 24 others"). The matching discrepancy lead and open question are withdrawn
  in research.json.
- §1 Defences: the GatellmGate denial text is `BLOCKED by security policy (<rule>)`, not the PolicyGate colon form; both
  share the prefix `BLOCKED by security policy`.
- §7 H2: also names the unreported `smoke-gatellm` attacked cell, and marks the v1-CONTAMINATED "3" as inferred from an
  approximate percentage (STATE.md's "5% with vs 5.7% without" does not equal the 7.1% clean figure, so it may be an interim count).
- research.json: the paper's commit list now includes ac4f51c, 6e4e532 and dafbd70 (13 commits, 2026-08-24..25 UTC);
  the not-selected `.log` count is 105 gatellml + 21 `results/*.log` + `results/probe/full.log`.

Unverifiable here (rest on our own reports or on raw data): the one denial in a `local` log, which 3 logs lack outcome
keys, the `local` model attribution to specific directories (STATE.md names the arms, not the directory names; the
mapping is by name and size: 10 + 10 + 1), the ladder-gated PolicyGate version (v3.1 by chronology only), and the
v5/v6 zero-success inference (H2). Note on H9: the first clause cannot fail at path level (paths are unique within a
directory), so only the session-gap clause is informative.
