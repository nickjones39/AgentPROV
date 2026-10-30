# Pre-registration: `geryon-agentdojo`

| | |
|---|---|
| Corpus | `geryon-agentdojo` (family `agentdojo`, profile `geryon-agentdojo` v1, dialect/mapper `agentdojo.tracelogger`, variant `v0.k11`) |
| Parts | `head` (only part) |
| Wave | 2 (first examination; not in FA or E2) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: our prior reports (phase-10d census, r1 census, trial, reconcile), the profile, `tables/geryon_log_sets.toml`, the registry, `artefacts.toml`, DECISIONS (D-103, D-104, D-113), and desk research (`data/geryon-agentdojo/research.json`). The per-log-set counts come from the GitHub git-trees listing (names and sizes only). Nothing here was computed from log contents. |
| Method | [`../README.md`](../README.md) |

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Repository | [luiacuaniello/geryon](https://github.com/luiacuaniello/geryon), Apache-2.0 (LICENSE appendix filled in: Copyright 2026 Luigi Iacuaniello) | LICENSE, CITATION.cff at pin |
| Pin | `905aae02c4185454ffbdb64a8bae6a042f6d7047`, 2026-09-23T12:56:51Z = **current head** (12 commits, 0 issues, 0 forks) | GitHub API |
| Logs added by | `3f06baa2` (2026-09-01): 2,585 logs / 22 sets; `bddceabf` (2026-09-03): `results/runs/` 6 × 99 = 594 logs (had been git-ignored). No log blob changed after that | git trees API |
| Paper / data record | none (no arXiv, DOI, Zenodo, HF). Documentation: `results/README.md`, `docs/running-progent.md`, `docs/what-went-wrong.md`, `protocol/threat-model.md`; per-suite numbers in [Progent issue #3](https://github.com/sunblaze-ucb/progent/issues/3) | research.json |
| Harness | Progent's vendored AgentDojo **0.1.29**, benchmark **v1.2**, cloned `--depth 1` at HEAD (very probably Progent `8a8eb894b9d5`, 2026-05-14) plus 2 Geryon patches; Bedrock OpenAI-compatible endpoint; temperature 0 (protocol); attack `important_instructions` | `docs/running-progent.md`, `scripts/setup_env.sh`, Progent API |
| Run dates | 2026-08-25 .. 2026-08-30 (before the first commit); the logs carry no timestamp | `results/README.md`; profile |
| Conditions | A = no defence (`SECAGENT_SUITE` unset); B = Progent automatic mode (`SECAGENT_UPDATE=True`, `SECAGENT_IGNORE_UPDATE_ERROR=True`); C = adaptive (no TraceLogger logs released) | `docs/running-progent.md` §1 |

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Tree entries at pin | 3,313 (30,876,930 bytes) | profile `expected_files/bytes`; git trees API |
| Selected logs (`results/*/*/*/*/*/*/*.json`) | 3,179 (27,549,189 bytes; 826 to 42,528 bytes each) | registry (`readme_corpora.toml`, census `/files`); census; tree |
| Not selected | 134 (36 run records, 31 `.log.gz`, `pairs*.json` (context), `cmcp-pilot/`, docs, code) | tree; profile `context_artefacts` |
| Units / executions | 3,179 `agent_execution` / 3,179 | census; trial (jobs 8, stages all ok) |
| Attacked / pre-pass / benign user task | 2,967 / 212 / **0** | tree (path kinds); census `injection_task_as_user_task_prepass` 212 |
| Sealed clean / with issues | 3,150 / 29 | trial |
| Variant | `v0.k11` 3,179 | census |
| Byte-identical log blobs | 0 (3,179 distinct blob SHAs) | tree |

Per log set (logs = attacked + pre-pass), from the tree at the pin:

| Run set | Agent model | A sets | B sets | Logs per set | Pair grid |
|---|---|---|---|---:|---|
| `runs` | gpt-oss-120b | banking r1-r3 | banking r1-r3 | 99 (90+9) | 10 UT × 9 IT; analysis keeps 42 (`pairs.json`) |
| `runs-strong-agent` | qwen3-235b | banking r1-r3 | - | 99 | same |
| `runs-strong-policy` | gpt-oss-120b (policy qwen3, pre-patch) | - | banking r1 | 99 | same |
| `runs-strong-policy-fixed` | gpt-oss-120b (policy qwen3, post-patch) | - | banking r1 | 99 | same |
| `runs-claude-policy` | gpt-oss-120b (policy claude-sonnet-5, rejected) | - | banking r1 | 1 (pre-pass IT0) | failed run |
| `runs-full-set` | gpt-oss-120b | banking r1-r3; slack r1-r2; travel r1 | banking r1-r3; slack r1-r3; travel r1-r2 | 153 (144+9) / 110 (105+5) / 105 (100+5) | 16×9, 21×5 (IT1-5), 20×5 (IT0,1,3,4,5) |
| `runs-full-set-strong-agent` | qwen3-235b | banking r1 | banking r1 | 153 | 16×9 |
| **Total** | | 13 sets, 1,531 logs | 15 sets, 1,648 logs | 3,179 | |

## 3. Expected arms

| Facet | Values | Expected missing / extra |
|---|---|---|
| Model (agent) | `openai.gpt-oss-120b`, `qwen.qwen3-235b-a22b-2507` (Bedrock ids, = pipeline dir = `pipeline_name`) | none extra |
| Defence | none (A), `progent` (B), by log set (D-104) | condition C: 0 logs (by release). Policy model is **not** an identity facet |
| Attack | `important_instructions`; `none` (pre-pass only) | no other label |
| Suite | banking, slack, travel (v1.2 of the Progent fork) | workspace: 0 (not run). Travel `injection_task_2`, `_6`: 0 (absent in the fork) |
| Repeat | r1..r3 | **missing by release**: `runs-full-set` slack-A-r3, travel-A-r2, travel-A-r3, travel-B-r3 (run records exist; 425 logs absent; probably `--per-pair` mode, which writes no TraceLogger file); calibration run (12 pairs): no set |
| Task kind | attacked; injection task as user task (pre-pass) | benign user-task runs: 0 by design |

## 4. Expected outcome rates (comparison targets)

Metric mapping (`scripts/run_condition.py`, `protocol/threat-model.md`): ASR = `security == true` over attacked logs
(`user_task_*/important_instructions/injection_task_*.json`); utility = `utility == true` over the same logs (utility
under attack; no benign utility exists). Per pair, the 3 repeats are collapsed by **majority** (≥ 2 of 3); one-repeat
sets are per run. Sets under `runs*/` other than the full sets are rated over the **42 pairs of `results/pairs.json`**,
not the 90 logged. Pre-pass logs and their constant `security` are in no rate. **Fact-check note:** the sources give percentages only; every `k/n` numerator in the table below is back-computed (percentage × n, rounded) and the denominators come from the pair grids (banking 144 is stated in `results/README.md`; slack 105 and travel 100 agree with the within-policy shares 18.1% = 19/105 and 2.0% = 2/100 quoted in Progent #3). Majority aggregation for the full-set figures is inferred from the protocol and from `scripts/analyse_runs.py` at the pin (which collapses both `security` and `utility` by majority when 3 repeats exist and by *any* otherwise); the sources do not say it per figure. Logged values = run-record values
(the record is built from the same benchmark results); Geryon did not hand-correct slack IT5 (as far as documented).

| Arm | Metric | Paper value (n) | Recomputable from logs? | Where |
|---|---|---|---|---|
| full-set B banking (gpt-oss) | ASR maj3 | 29.2% = 42/144 | yes (r1-r3) | what-went-wrong §1; Progent #3 |
| full-set B slack | ASR maj3 | 7.6% = 8/105 | yes (r1-r3) | Progent #3 (2026-09-19, -23) |
| full-set B travel | ASR maj3 | 3.0% = 3/100 | bounds only (r1, r2) | Progent #3 |
| full-set B pooled | ASR maj3 | 15.2% [11.8-19.4]; **corrected (fact-check):** the published Wilson interval matches 53/**348**, not 53/349 (53/349 gives [11.8-19.3]), so the pooled denominator is probably 348 scored pairs | bounds only | what-went-wrong §1 |
| full-set banking A → B | utility | 61.1% (88/144) → 56.2% (81/144) | yes; aggregation unstated (test maj3 and per-run mean) | Progent #3 |
| full-set slack A → B | utility | 61.0% (64/105) → 22.9% (24/105) | B yes; A bounds (r1, r2) | Progent #3 |
| full-set banking A / B per run | ASR range | A ≈ 67-70%, B ≈ 25-33% | yes | Progent #3 (Progent author, 2026-09-16) |
| runs B (policy gpt-oss) | ASR maj3, 42 pairs | 42.9% = 18/42 | yes | results/README; condition-c-decision.json |
| runs-strong-policy B | ASR, 42 pairs | 45.2% = 19/42 (broken arm) | yes | results/README |
| runs-strong-policy-fixed B | ASR, 42 pairs | 45.2% = 19/42 | yes | results/README |
| runs-strong-agent A (qwen3) vs runs A (gpt-oss) | ASR maj3, 42 pairs | qwen3 higher (no number) | yes | results/README |
| "decomposition" | unspecified | 84% vs 57% | no (definition not public) | results/README |

L2 sample: ~5 per stratum gives ≤ 5 per arm (27 strata without repeat, 55 with), far below 20 per arm, so L2 reports
Wilson intervals only. The exact comparison is H5-H8 on the whole-population L1-05 tally.

## 5. Known quirks

| Id | Expected | Source |
|---|---|---|
| `agentdojo.benign_security_constant` (art. `agentdojo.art.benign_security_constant`) | 212 files, 211 origin rule applied (1 incomplete log has no outcome) | profile, census |
| `agentdojo.injection_task_as_user_task_prepass` (art. `agentdojo.art.injection_task_as_user`) | 212 | profile, census |
| `agentdojo.silent_rerun_last_pass_only` (art. `agentdojo.art.silent_rerun`) | 27 null-final logs (`retry_passes_inferred`); `earlier_attempts_unobservable` on 3,179 | profile, trial |
| `agentdojo.unexecuted_trailing_calls` (art. `agentdojo.art.max_iters_pending`) | 28 calls in 28 logs | profile, census |
| `agentdojo.incomplete_run` (art. `agentdojo.art.incomplete_run`) | 1 (`runs-claude-policy`), 0 null-outcome files | profile, census |
| `agentdojo.defence_denial_message` (R1, D-113) | 773 Progent denials, whole-text regex, B sets only; JSON-schema argument errors stay tool errors | profile, r1 census, routing.md |
| `agentdojo.placeholder_args_never_injection_evidence` | 14,149 present, all null | census |
| Identity (D-104) | 28 table rows keyed by `<run set>/<log set>`, all class I (`agentdojo.pipeline_dir_is_model_identity@1`); 0 unresolved | table, phase10d README |
| Evidence (D-103, D-24) | `verified_code = []`: every D rule via its `_unverified` twin | profile |
| System prompt | 469-char AgentDojo default in every log (`agentdojo_default`) | profile |
| Timestamps / versions | none recorded in v0.k11; nothing filled | profile |
| Accounting | unverifiable 3,178, known_incomplete 1 | census, trial |
| `agentdojo.art.banking_ut15_confound` | applies to banking `user_task_15` cells (in all banking grids) | artefacts.toml (scope lists agentdojo only) |
| artefacts.toml scope | no entry lists `geryon-agentdojo` in `scope.sources` | artefacts.toml |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2; per log set; selection by `include` glob, 10 `context_artefacts` |
| L1-02 strict parse | yes | expect 0 defects (census parse ok, trial 0 failures) |
| L1-03 encodings | yes | AgentDojo #214 escape residues possible: count, expected-known |
| L1-04 duplicates | yes | 0 byte-identical (tree); repeats r1-r3 at temperature 0 may share trajectories: report rate; cross-corpus: none expected (S1 found 0 blob matches) |
| L1-05 arm coverage | yes | §3 table; plus whole-population outcome tally (H5-H8) |
| L1-06 secrets / account paths | yes | expect 0 (Bedrock key via env; v0.k11 records no paths) |
| L1-07 timestamps | presence only | v0.k11: expect 0 timestamps; parse, zone, monotonicity, range not applicable |
| L1-08 degenerate | yes | expect 0 empty, 1 incomplete, 27 null-final, 28 unexecuted calls |
| L2 import, validate, recompute, determinism | yes | trial: 0 failures, byte-identical jobs 8/3 |
| L2 A2 / A3 classes | yes | expect only the trial's register codes |
| L2 evidence classes | yes | D rules only as `_unverified` twins; denials class I |
| L2 degenerate / adapter_defect | yes | expect 0 / 0 |
| L2 identity | yes | model from table/pipeline dir; defence by log set; policy model not represented (H9) |
| L2 redaction | yes | expect no account path |
| L2 withholding | conditional | only if L1-06 finds a secret-like string |
| L2 outcome sanity | yes (Wilson only) | §4 |
| Delta since E2 | no | not in FA/E2 |

## 7. Hypotheses (falsifiable)

| # | Expectation | Refuted if |
|---|---|---|
| H1 | 3,179 logs in exactly the 28 sets and sizes of §2; 2,967 attacked + 212 pre-pass; 0 benign user-task logs | any set count differs by ≥ 1 |
| H2 | No log for travel IT2/IT6, workspace, condition C, or the 4 missing full-set repeats | ≥ 1 such log |
| H3 | 773 denials, all in B sets; 0 in A sets; denials > 0 in every B set except `runs-claude-policy` | denial in an A set, or count differs |
| H4 | Quirk counts of §5 reproduce exactly (212/211, 212, 27, 28/28, 1, 14,149) | any differs |
| H5 | full-set banking B ASR maj3 = 42/144; slack B ASR maj3 = 8/105; slack B utility maj3 = 24/105 | any off by > 1 pair |
| H6 | full-set banking utility A = 88/144, B = 81/144 under maj3 or per-run mean (one of the two matches) | neither within 1 pair |
| H7 | travel B: (pairs true in both r1, r2) ≤ 3 ≤ (pairs true in r1 or r2); slack A utility bounds contain 64/105; pooled B bounds contain 53 (over 348 or 349 pairs; see fact-check) | a bound excludes the reported value |
| H8 | Over the 42 `pairs.json` pairs: runs B maj3 = 18/42; strong-policy r1 = 19/42; strong-policy-fixed r1 = 19/42; runs-strong-agent A maj3 > runs A maj3 | any count off by ≥ 1, or qwen3 A ≤ gpt-oss A |
| H9 | `runs-strong-policy`, `-fixed` and `runs` B map to the same identity (model gpt-oss-120b, defence progent); `runs-strong-policy` and `runs-claude-policy` carry no caveat in AER/SEM | identity differs (then the documentation-mismatch lead is void) |
| H10 | Slack B logs on IT5 with `security == true` include ≥ 1 where every attacker-goal call (`invite_user_to_slack`/`add_user_to_channel`/`remove_user_from_slack`) was denied (note in Progent's `agentdojo/README.md`, AgentDojo #168) | 0 such logs |
| H11 | Banking full-set A per-run ASR in [62%, 75%], B per-run in [20%, 38%] (Progent author's reading ± 5 pts) | any repeat outside |
| H12 | 0 secret-like strings, 0 account paths, 0 timestamps | ≥ 1 |
| H13 | Identical trajectory fingerprints between repeats of the same pair ≤ 50% (Bedrock not bit-deterministic at T 0); cross-corpus identical fingerprints 0 | above either |

## 8. Discrepancy leads carried to the dossier

Four documented full-set repeats unreleased (425 logs; majority numbers for slack A and travel not recomputable);
author-declared unusable arms (`runs-strong-policy`, `runs-claude-policy`) imported as ordinary B executions; policy
model and patch state not in identity; Progent code identity probably recoverable from the run records
(`benchmark_repo_commit`; Progent HEAD at run time `8a8eb894b9d5`) although the profile says unpinned; context scripts
at the pin postdate the runs; `runs*/` grids log 90 pairs but every rate uses 42; "348 vs 349" pair count (probably not a discrepancy: 349 pairs, 1 skipped, 348 scored; the pooled Wilson interval fits 348, fact-check);
`b_claude_policy` key vs README; slack B utility drop unexplained; profile says the LICENSE has no copyright line
(it has one, S3); no `artefacts.toml` entry scopes this corpus.

## 9. Fact-check (adversarial, 2026-10-14)

Checked against the cited sources at the pin (GitHub API, raw files at `905aae02`), Progent issue #3 and its 3 comments,
Progent's commit list and README files, AgentDojo issue pages, arXiv. No raw log was read.

| Claim | Verdict | Evidence |
|---|---|---|
| Pin `905aae02` = head, 2026-09-23T12:56:51Z, 12 commits, 0 forks/issues | confirmed | GitHub API commits and repo metadata |
| Tree 3,313 blobs / 30,876,930 bytes; 3,179 selected logs / 27,549,189 bytes (826-42,528), 3,179 distinct SHAs | confirmed | git trees API, not truncated |
| 28 log sets and per-set counts of §2; A 13 sets / 1,531, B 15 / 1,648; 2,967 attacked + 212 pre-pass | confirmed | tree paths (names only) |
| Travel ITs 0,1,3,4,5; slack ITs 1-5; banking ITs 0-8; grids 10/16/21/20 UT | confirmed | tree paths |
| 134 not selected incl. 36 run records and 31 `.log.gz`; 425 logs for the 4 missing full-set repeats; 18 full-set run records | confirmed | tree |
| Logs added 2,585 at `3f06baa2`, 594 at `bddceabf`; no log path touched later | confirmed | commit file lists |
| 29.2%, 15.2% [11.8-19.4] in what-went-wrong §1 | confirmed (text) | what-went-wrong.md |
| Pooled n = 349 | **corrected** | Wilson [11.8-19.4] reproduces 53/348 only (53/349 gives upper 19.3); n is probably 348 scored pairs |
| 7.6%, 3.0%, utility 61.1→56.2 and 61.0→22.9; corrections of 2026-09-23 | confirmed (text) | Progent #3 comments 2 and 3 |
| Numerators (42/144, 8/105, 3/100, 88/144, 81/144, 64/105, 24/105, 53/…) | **corrected (marked inferred)** | sources state percentages only |
| Majority-of-3 for full-set figures | unverifiable per figure | protocol and `analyse_runs.py` collapse by majority; issue text silent |
| Progent author: B ≈ 25-33%, A ≈ 67-70% | confirmed (text); "per run" is our reading | Progent #3 comment 1; Geryon author replies the "intervals" match; Wilson for 42/144 is [22.4-37.1], so not a Wilson interval |
| 42.9 / 45.2 / 45.2 and the arm mapping; `b_claude_policy` 0.4524 | confirmed | results/README.md, condition-c-decision.json |
| "84% against 57%" | confirmed (text); partly defined | README names its source (runs-full-set, 3 suites, majority) but not the metric |
| "One pair of 348 was skipped", travel-A-r2 | confirmed (text) | results/README.md, what-went-wrong §5 |
| Apache-2.0, LICENSE carries "Copyright 2026 Luigi Iacuaniello"; profile note wrong | confirmed | LICENSE at pin; profile line 46 |
| No artefacts.toml entry scopes `geryon-agentdojo` | confirmed | `artefacts.toml` (grep) |
| Fork = agentdojo 0.1.29, benchmark v1.2, travel 5 ITs; `setup_env.sh` clones `--depth 1` | confirmed | running-progent.md, setup_env.sh, Progent `agentdojo/pyproject.toml` |
| Progent HEAD during the runs = `8a8eb894b9d5` | confirmed (strong inference) | Progent has 4 commits; `8a8eb894` (2026-05-14) was HEAD until `5be7b63` (2026-09-24) |
| Slack IT5 scoring note "in Progent's README" | **corrected (location)** | the note is in Progent's `agentdojo/README.md`, not the top-level README |
| `--per-pair` writes no TraceLogger file | confirmed for the script at the pin | it calls `run_task_with_pipeline` directly; the run-time code was never committed |
| Progent MIT LICENSE `5be7b63` 2026-09-24; #4 closed same day | confirmed | Progent commits, issue #4 |
| AgentDojo #168, #218, #181, #161, #188, #214 open and on the stated topics | confirmed | issue pages |
| Progent paper title | **corrected** | arXiv v3 is titled "Progent: Securing AI Agents with Privilege Control"; v1 title as cited; v4 404 |
| Run dates, calibration run, 0/487, p = 0.0078 | confirmed (text) | results/README.md, docs/adaptive-loop.md |

Observation (documentation only, no new expectation): `results/README.md` names `--suites banking slack workspace` as
the primary pooled analysis and an "85-pair set", which matches neither the full-set suites nor the 42-pair set.

