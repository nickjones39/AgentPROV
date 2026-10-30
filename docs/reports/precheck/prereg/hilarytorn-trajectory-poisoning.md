# Pre-registration: `hilarytorn-trajectory-poisoning`

| | |
|---|---|
| Corpus | `hilarytorn-trajectory-poisoning` (family `agentdojo`, profile `hilarytorn-trajectory-poisoning` v1, dialect/mapper `agentdojo.tracelogger`, variant `v1.k14`) |
| Parts | `head` (only part) |
| Wave | 2 (first examination; not in FA or E2) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: our prior reports (phase-10c census summaries, phase-10d census, trial, reconcile), the profile, the registry, `artefacts.toml`, DECISIONS, and desk research (`data/hilarytorn-trajectory-poisoning/research.json`; GitHub API metadata, docs and result summaries at the pin). Nothing here was computed from the raw logs. |
| Method | [`../README.md`](../README.md) |

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Repository | [HilaryTorn/in-context-trajectory-poisoning](https://github.com/HilaryTorn/in-context-trajectory-poisoning), MIT, (c) 2026 Hilary Torn | LICENSE at pin |
| Pin | `d71ab8bc2aa9db35ff443cc81e475e70ee8da215`, 2026-05-26T09:39:29Z ("updated readme", README only), = `main` HEAD on 2026-10-14 | GitHub API |
| Paper / data record | No arXiv/DOI/Zenodo/HF. Hackathon report (Apart AI Control Hackathon, page 2026-03-22) and project write-up (hilarytorn.com, 2026-04-12, updated 2026-04-18); results also in `data/results/e2e-evals.md` and `data/results/e2e_eval/<run>/summary.json` | research.json |
| Study | Attacks on an LLM agent **monitor** (LlamaFirewall AlignmentCheck, Qwen2.5-7B): priming strings spliced into AgentDojo slack injections. The monitor's decisions are **not** in the logs; the logs are the agent runs only | README, `src/e2e_evaluate.py` |
| Harness | AgentDojo 0.1.35 per logs and e2e manifests (requirements.txt pins 0.1.29); benchmark `v1.2.1`; slack; `important_instructions` (base) and `ImportantInstructionsAttack` renamed `e2e_<condition>_<injection_task>` with a spliced candidate (e2e) | census, manifests |
| Agent model | `gpt-4o-2024-05-13` (OpenAI), no defence in the agent loop; temperature not sent (agentdojo 0.1.35 drops 0.0, so provider default; write-up says T=1.0; fact-check addition) | census, manifests, [openai_llm.py v0.1.35](https://raw.githubusercontent.com/ethz-spylab/agentdojo/v0.1.35/src/agentdojo/agent_pipeline/llms/openai_llm.py) |
| Run dates (naive) | base 2026-03-20; e2e 2026-04-14: smoke 06:14:07-06:17:11, run 1 06:36:04-08:09:20, run 2 15:56:09-16:46:39, run 3 17:29:29-18:48:25 (manifests; consistent with commit times at about UTC+3) | manifests, census `ts_range` 2026-03-20 11:26:54 .. 2026-04-14 18:40:49 |

**Directory history (commit metadata only).** `e2e/tap` and `e2e/seeded_pair` were written by run 1 (`d7a689f4`), copied to
`*_run1` (`c9fdccc2`, whose `e2e/tap/.../injection_task_1/none/none.json` already holds a transient run-2 write; **corrected by fact-check:** the `tap_run1` copy of that file has the run-1 blob SHA, identical to `d7a689f4`),
overwritten by run 2 (`d88905e0`), copied to `*_run2` (`99d7acd4`), and overwritten by run 3 (`757d1e76`). Inferred
mapping: `tap`/`seeded_pair` = run 3, `*_run1` = run 1, `*_run2` = run 2 (fact-check: confirmed at git blob-SHA level, 110/110 per directory against `757d1e76`, `d7a689f4`, `d88905e0`; no blob shared between runs). Two `e2e/baseline` logs
(`injection_task_1/none/none.json`, `user_task_0/e2e_baseline_injection_task_1/injection_task_1.json`) were committed in
`3071d6af` before run 1 and never rewritten (smoke run; run 1 reused AgentDojo's cache without `--force-rerun`).

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Tree entries at pin | 1,294 blobs (73,070,963 bytes; 1,276 non-PNG = 71,494,512 bytes; 18 PNG absent locally) | profile `expected_files`; phase-10c census; GitHub tree |
| Selected logs (`data/traces/*/*/*/*/*.json`) | 990 (12,578,066 bytes) | registry / `readme_corpora.toml` (census `/files`); phase-10c/10d census; tree |
| Not selected | 304 (results, charts, scripts, `successful_injections.json`, `.gitkeep`); 7 context artefacts stored as supporting; 0 `.DS_Store`/`._*` | tree; profile |
| JSON parse ok | 990 / 990 (1,240 / 1,240 JSON blobs in the tree) | phase-10c census |
| Units / executions | 990 `agent_execution` / 990 | phase-10d census; trial (jobs 8: 990, jobs 3 subset 198; byte-identical) |
| Sealed clean / with issues | 990 / 0; register codes `map.accounting_unverifiable` 990, `map.earlier_attempts_unobservable` 990 | trial |
| Variant | `v1.k14` 990 | census |
| Messages | system 990, user 990, assistant 5,741, tool 6,920; 6,920 calls (all with `placeholder_args`, all null); 369 tool errors | phase-10c census |
| Outcomes | utility true 690 / false 300; security true 828 / false 162; `error` null 990 | phase-10c census |

Per directory (file listing at the pin): every one of the 9 directories holds 110 = 105 attacked (21 user tasks x 5
injection tasks) + 5 injection-task pre-pass (`attack_dir` `none`).

| Directory (arm) | Attack label(s) | Attacked | Pre-pass | Run |
|---|---|---:|---:|---|
| `data/traces/gpt-4o-2024-05-13` (no arm) | `important_instructions` | 105 | 5 | base, 2026-03-20 |
| `e2e/baseline` | `e2e_baseline_injection_task_{1..5}` (21 each) | 105 | 5 | run 1 (2 smoke) |
| `e2e/persona_v3` | `e2e_persona_v3_injection_task_{1..5}` | 105 | 5 | run 1 |
| `e2e/tap_run1`, `e2e/tap_run2`, `e2e/tap` | `e2e_tap_injection_task_{1..5}` | 3 x 105 | 3 x 5 | runs 1, 2, 3 |
| `e2e/seeded_pair_run1`, `e2e/seeded_pair_run2`, `e2e/seeded_pair` | `e2e_seeded_pair_injection_task_{1..5}` | 3 x 105 | 3 x 5 | runs 1, 2, 3 |
| **Total** | 22 labels (incl. `None` 45) | **945** | **45** | |

## 3. Expected arms

| Facet | Values | Expected missing / extra |
|---|---|---|
| Model | `gpt-4o-2024-05-13` only | none extra |
| Defence | none (the monitor is outside the agent loop) | 0 denials, 0 defence messages |
| Attack / condition | base `important_instructions`; e2e `baseline`, `persona_v3`, `tap` (x3 runs), `seeded_pair` (x3 runs); `none` (pre-pass) | baseline and persona_v3 single run by design; no cold-start PAIR or one-shot e2e runs (search-only) |
| Suite | slack `v1.2.1` | other suites not run (documented) |
| Tasks | user_task_0..20 x injection_task_1..5; pre-pass injection_task_1..5 | **benign user-task runs absent in all 9 dirs by design** |
| Run | arm = path component above the pipeline dir (`{arm?}`); the attack label does not distinguish tap/tap_run1/tap_run2 | |

## 4. Expected outcome rates (L2 comparison targets)

Metric mapping: the author's *injection rate* = `num_security_true / num_valid` over the 105 attacked logs of a
condition run, where `security` is the AgentDojo field (true = injection goal reached), read unchanged by
`src/e2e_evaluate.py` (`injection_success = security`). Pre-pass logs (`none`) are outside every reported rate.
Monitor-level metrics (e2e ASR, conditional bypass, simulated ASR) are **not** testable from the logs. Utility is not
reported by the author; only the census total (690/990) exists.

| Arm (directory) | Injection rate (security true / attacked) | Per injection task 1..5 (of 21) | Source |
|---|---|---|---|
| base | 96/105 (91.4%) | not reported | README Methodology step 1; write-up "96-trace"; `successful_injections.json` |
| e2e/baseline (run 1) | 97/105 (92.4%) | 18, 17, 20, 21, 21 | e2e-evals.md Run 1; `20260414_063604/summary.json` |
| e2e/persona_v3 (run 1) | 77/105 (73.3%) | 17, 9, 13, 18, 20 | same |
| e2e/tap_run1 (run 1) | 86/105 (81.9%) | 15, 17, 17, 18, 19 | same |
| e2e/seeded_pair_run1 (run 1) | 83/105 (79.0%) | 17, 18, 16, 15, 17 | same |
| e2e/tap_run2 (run 2) | 92/105 (87.6%) | 17, 17, 19, 20, 19 | e2e-evals.md Run 2; `20260414_155608/summary.json` |
| e2e/seeded_pair_run2 (run 2) | 80/105 (76.2%) | 15, 16, 14, 17, 18 | same |
| e2e/tap (run 3) | 91/105 (86.7%) | 17, 17, 17, 19, 21 | e2e-evals.md Run 3; `20260414_172929/summary.json` |
| e2e/seeded_pair (run 3) | 81/105 (77.1%) | 17, 15, 14, 17, 18 | same |
| **All attacked** | **783/945** | | sum; equals census 828 − 45 pre-pass |
| Pre-pass (45) | security true 45/45 (constant) | | profile quirk `benign_security_constant` |

L2 sample: strata = (arm dir, attack label) gives 9 x 5 attacked strata of 21 (5 drawn each) + 9 pre-pass strata of 5
(all drawn): about 270 units, 25 attacked per arm. The 15-pp threshold applies per arm (n ≥ 20); per-injection-task cells
(n = 5) get Wilson intervals only. The exact comparison is H1 (whole population, L1-05 tally).

## 5. Known quirks

| Id | Expected | Source |
|---|---|---|
| `agentdojo.benign_security_constant` (art. `agentdojo.art.benign_security_constant`) | 45 files, 45 origin-rule judgements (all pre-pass) | profile `observed`, census, reconcile |
| `agentdojo.injection_task_as_user_task_prepass` (art. `agentdojo.art.injection_task_as_user`) | 45 files | profile, census |
| `agentdojo.args_mutated_in_place` | 990 files | profile, census |
| `agentdojo.placeholder_args_never_injection_evidence` | 6,920 present, 6,920 null | profile, census |
| `agentdojo.unexecuted_trailing_calls` (art. `agentdojo.art.max_iters_pending`) | 0 calls, 0 logs | profile, census |
| `agentdojo.silent_rerun_last_pass_only` (art. `agentdojo.art.silent_rerun`) | 0 null-final logs; `earlier_attempts_unobservable` 990 | profile, trial |
| `agentdojo.package_version_not_code_identity` | 0 files without package version (all `0.1.35`); requirements 0.1.29 | profile, census |
| System prompt | AgentDojo default (469 chars, sha256 `a021a92b…`) in 990 | profile, phase-10c census |
| Naive timestamp (art. `agentdojo.art.naive_timestamp`, generic; scope does not list this source) | one naive `evaluation_timestamp` per log | artefacts.toml, census |
| Accounting | `unverifiable` 990 | census, trial |
| Evidence | `verified_code = []` (D-24, D-103): every D rule cited through its `_unverified` twin | profile |
| Identity | model from `pipeline_dir` (`agentdojo.pipeline_dir_is_model_identity@1`, D-101); `pipeline_name_policy = verbatim_unreliable_when_differs` | profile |
| Provider ids | 0 null, 0 duplicate call ids | census, reconcile |
| `artefacts.toml` | no entry scoped to this source | artefacts.toml |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2; selection by `include` glob (layout depth 6 base, 8 e2e via `{arm?}`), `context_artefacts` |
| L1-02 strict parse | yes | expect 0 defects (census parse ok 990) |
| L1-03 encodings | yes | AgentDojo #214 escape residues possible in tool content; spliced attacker candidates may carry unusual characters: count, classify |
| L1-04 duplicates | yes | within part: pre-pass logs across 9 dirs; tap_run1 vs tap (backup copy); cross-corpus: other gpt-4o-2024-05-13 slack v1.x `important_instructions` logs (e.g. glitch, agentdojo head) |
| L1-05 arm coverage | yes | §3; plus the whole-population tally for H1 |
| L1-06 secrets / account paths | yes | expect 0 in the 990 logs; account paths exist in non-selected `data/results/e2e_eval/*/manifest.json` (report separately, outside selection) |
| L1-07 timestamps | yes (partly) | presence, parse, zone (naive), range and per-dir windows (H3); within-unit monotonicity n/a (one timestamp per log) |
| L1-08 degenerate | yes | expect 0 empty, 0 null-final, 0 run errors, 0 null outcome |
| L2 import, validate, recompute, determinism | yes | trial: 0 failures, byte-identical across jobs 8/3 |
| L2 A2 / A3 classes | yes | expect only the trial's two register codes |
| L2 evidence classes | yes | D rules only as `_unverified` twins (class I); 0 denials |
| L2 degenerate / adapter_defect | yes | expect 0 / 0 |
| L2 identity | yes | model `gpt-4o-2024-05-13`; arm from path (9 distinct values); attack label verbatim; no defence |
| L2 redaction | yes | expect no account path in AER/SEM/PROV |
| L2 withholding | conditional | only if L1-06 finds a secret-like string in the logs |
| L2 outcome sanity | yes (security per arm) | §4; utility: no external target (population only) |
| Delta since E2 | no | not in FA/E2 |

## 7. Hypotheses (falsifiable)

| # | Expectation | Refuted if |
|---|---|---|
| H1 | Per-directory attacked `security == true` tallies equal §4 under the inferred mapping (base 96, baseline 97, persona_v3 77, tap_run1 86, seeded_pair_run1 83, tap_run2 92, seeded_pair_run2 80, tap 91, seeded_pair 81), including the per-injection-task counts | any count differs by ≥ 1 (then test the alternative mapping; a mismatch under every mapping is a `documentation-mismatch`) |
| H2 | Total attacked security true = 783 of 945; pre-pass security true 45/45; utility true 690 of 990 | any differs |
| H3 | Timestamps: base 110 on 2026-03-20/21; `*_run1` + baseline + persona_v3 within 2026-04-14 06:14:07-08:09:20; `*_run2` within 15:56:09-16:46:39; `tap`/`seeded_pair` within 17:29:29-18:48:25 | > 1 log outside its window (1 allowed: the backup-race file, H4) |
| H4 | Exactly 2 `e2e/baseline` logs (injection_task_1 pre-pass, user_task_0 x injection_task_1) predate 06:36:04 (smoke run); `tap_run1/.../injection_task_1/none/none.json` lies in the run-1 window (git metadata already shows its blob equals the run-1 commit `d7a689f4`; fact-check) | any other count, or that file in the run-2 window (then S3, disclose) |
| H5 | Every (dir, user task, injection task) cell and every (dir, pre-pass task) occurs exactly once; 0 benign user-task logs | duplicate, missing or extra cell |
| H6 | Only model `gpt-4o-2024-05-13`, only suite slack `v1.2.1`, only the 22 attack labels, `agentdojo_package_version` 0.1.35 in all | any extra label or version |
| H7 | Byte-identical log files across the 9 dirs = 0 (each run rewrote its files; copies `*_run1`/`*_run2` differ from `tap`/`seeded_pair`); identical trajectory fingerprints between run copies ≤ 5% of attacked logs | above either threshold (would mean a backup duplicated a run, not a rerun) |
| H8 | Among slack `injection_task_5` logs with security true, those whose invite/add/remove call returned a tool error (AgentDojo #168 exposure) ≤ 2% of 189 | above |
| H9 | Spliced candidate text is present in the tool outputs of e2e tap/seeded_pair/persona_v3 attacked logs and absent in base/baseline (payload reached the agent) | candidate absent in > 5% of a condition's logs |
| H10 | 0 secret-like strings and 0 account paths in the 990 logs | ≥ 1 |

## 8. Discrepancy leads carried to the dossier

The run-to-directory mapping is inferred from commit history (no run tag in the logs); requirements.txt (0.1.29) vs
logs/manifests (0.1.35), and dirty working trees in runs 1-2; hackathon report (2026-03-22) vs later write-up/README
monitor numbers differ (PAIR 12.5% vs 9.4% average; Llama transfer 16.7% vs 8.3%), monitor-level only; README says the e2e reruns were at temperature 0, but the write-up says the agent ran at T=1.0 and agentdojo 0.1.35 sends no temperature for 0.0 (not testable from the logs); the e2e payload
is the stock injection plus a monitor-targeted priming string; no benign utility runs; the monitor decisions behind
the headline results are only in `data/results/**`, outside the selection.

## Fact-check (2026-10-14, adversarial, desk only)

Done from GitHub API metadata, the files at the pin, the two write-ups and our own phase-10c/10d reports. No raw log was read.

| Checked | Verdict |
|---|---|
| §4 injection counts: e2e-evals.md (Run 1/2/3 FULL rows) and the three `summary.json` (`num_security_true`, `num_valid` 105); per-injection-task numerators; base 96 (README step 1); sum 783 | confirmed |
| §2 tree counts: 1,294 blobs / 73,070,963 B; 18 PNG / 1,576,451 B; 990 logs / 12,578,066 B; 9 x (105 + 5); label counts (105, 21 each, 63 each, 45 `none`); 1,240 JSON | confirmed (trees API) |
| Census totals (utility 690/300, security 828/162, 6,920 tool, 5,741 assistant, 369 tool errors, ts range) | confirmed against the phase-10c census summary |
| Pin, history (28 commits, 0 tags/issues, 1 fork), per-commit file lists, run mapping | confirmed; mapping now also holds at blob-SHA level |
| `c9fdccc2` "run-2 overwrite" and the `tap_run1` pre-pass | **corrected**: the `tap_run1` copy is the run-1 blob; the overwritten `e2e/tap` file in `c9fdccc2` matches neither run 1 nor the final run 2 |
| Agent temperature | **corrected**: research.json said AgentDojo default 0; v0.1.35 drops 0.0 (`temperature or NOT_GIVEN`), and the write-up states T=1.0 |
| Manifests (0.1.35, llamafirewall 1.0.3, dirty runs 1-2, clean run 3 at `99d7acd4`), smoke runs 061406/061627 | confirmed |
| Write-up (2026-04-12/18; 3.1/9.4/16.3/14.6; e2e 96-subset ASR; Llama 8.3%) and hackathon page (2026-03-22; PAIR 12.5%, p=0.028; Llama 16.7%) | confirmed |
| Licence: MIT at pin, (c) 2026 Hilary Torn; no data record on Zenodo/HF/Figshare | confirmed |
| AgentDojo #168/#188/#194/#214/#218 open, #189 closed; v0.1.35 = latest release (2025-10-27) | confirmed |
| Which invocation produced run-1 persona_v3/tap/seeded_pair; OpenAI output terms | unverifiable |
