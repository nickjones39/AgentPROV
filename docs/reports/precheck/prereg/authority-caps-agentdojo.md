# Pre-registration: `authority-caps-agentdojo`

| Field | Value |
|---|---|
| Corpus | `authority-caps-agentdojo` (family `agentdojo`, profile `authority-caps-agentdojo` v1, dialect/mapper `agentdojo.tracelogger`, variants `v1.k14`, `v1.k14.incomplete`) |
| Parts | `head` (only part): 21,999 TraceLogger members, 18,739 executions, 3,260 re-packed byte copies (D-250) |
| Pin | Zenodo record 23138310 (v2.1.0, 2026-10-04; concept 22973265), file `agent-authority-caps-v2.0.0.zip`, 40,160,657 B, md5 `3fba8031…6ace`, sha256 `1dce0380…05bf`; 3 declared nested tars (exp4, exp5, exp7) |
| Code commit | `6b76c15e` (or later on `precheck-corpora`; phase 10j merged to main 2026-10-15, after the pre-check began; satisfies "065b0d36 or later") |
| Date | 2026-10-15 (wave 7) |
| Status | **Written before any pre-check data check of this corpus.** Inputs: desk research (`../data/authority-caps-agentdojo/research.json`), the profile, the identity table `tables/authority_caps_pipeline_dirs.toml`, the registry row, `docs/reports/phase10j/` (census.md/json, trials.md, routing.md), DECISIONS D-250..D-258 and D-560, `artefacts.toml`, the systematic-search shortlist row 5, and the deposit's published README and Supplementary Material v2.1.0 (Tables S1–S25). No raw log or zip member was read for this file; every derived number is arithmetic on those reports. |

## 1. Expected counts

| Quantity | Expected | Source |
|---|---:|---|
| Zip file | 40,160,657 B; md5 = record checksum `3fba80315a4879d381fb3b14fd386ace` (same file in v2.0.0 record 22996368) | Zenodo API `records/23138310`, `records/22996368`; profile pin |
| Zip + nested members | 22,250 = 3,038 level-1 non-container + 19,212 nested (census gate rows: `d1:selected` 3,041 incl. the 3 containers, `d2:selected` 19,212; reconcile at L1-01) | census.json `members`, `gate` |
| JSON members (strict parse ok) | 22,012 = 21,999 TraceLogger + 13 other JSON (incl. `MANIFEST.sha256.json`) | census.json `json`, `parse` |
| TraceLogger members (selected) | 21,999 = level 1 2,813 (current_models 2,631 + pilot 182) + exp4 6,024 + exp5 10,684 + exp7 2,478 | census; profile `nested` notes |
| Nested non-log members | 26 (19,212 − 19,186) | census arithmetic |
| TraceLogger members outside the include globs | 0 (21,999 = 2,813 + 19,186) | census |
| Executions (byte-distinct) | 18,739: `v1.k14` 18,734, `v1.k14.incomplete` 5 | census; trial (18,266 ok, 473 ok with issues) |
| `dedup.collapsed` | 3,260 = 1,506 (gpt-4o-mini base in exp4 = exp5 = exp7) + 753 (gpt-6-luna) + 753 (gpt-6-sol) + 124 + 124 (haiku/luna autoconfirm benign) (current_models ≡ exp5) | census `byte_identical_extra_copies`; trial |
| Content repeats with different bytes | 4 groups / 13 files (18,730 distinct `fp_run`) | census |
| Paper count | 18,557 new runs = 2,631 replication + 7,749 caps/no-egress/repeats + 8,177 exploratory; **18,739 − 18,557 = 182 = the pilot** | Supplementary Note 5 |
| v1.0 (record 22973266) | 2,813 logs, all byte-identical members of the pin (lineage only); its description says 2,259 new runs + an auto-confirm condition (2,259 + 372 + 182 = 2,813) | census `zenodo_v1_0_in_v2_1`; Zenodo `records/22973266` |
| Context artefacts | 8 (`README.md`, `CITATION.cff`, `original-study/README.md`, `LICENSE-CODE`, `LICENSE-DATA`, `RESULTS_new_models.md`, `source-snapshots/run_new_models.py`, `AGENTDOJO_LICENSE`) | profile; trial chain: 18,751 raw objects = 18,739 + zip + 3 tars + 8 |

**Per pipeline directory (byte-distinct; the full-arm unit is 753 = 97 benign + 27 direct-goal (`injection_task_*`, attack none) + 629 attacked).**

| Location | Directory → distinct logs | Design (paper) |
|---|---|---|
| L1 `current_models` | `claude-haiku-4-5-20251001` 753; `-autoconfirm` 124 (also in exp5); `gpt-6-luna` 753 (≡ exp5); `-autoconfirm` 124 (≡ exp5); `gpt-6-sol` 753 (≡ exp5); `-autoconfirm` 124 | 3 × 753 + 3 × 124 = 2,631 (Note 5) |
| L1 `pilot` | haiku 169; haiku-autoconfirm 3; luna 5; sol 5 | paper: 169 Haiku banking runs (Note 2); the other 13 are not described |
| exp4 `runs_exp4.tar.gz` | `gpt-3.5-turbo-0125` 753 (1 incomplete); `-capA3` 753; `-capA4` 753; `gpt-4o-mini-2024-07-18` 753 (≡ exp5, exp7); `-capA3` 753; `-capA4` 753; `gpt-6-luna-capA3` 753 (1 incomplete); `-capA4` 753 | 6 capped + 2 same-period full-authority = 6,024 (Note 5) |
| exp5 `runs_exp5.tar.gz` | haiku-autoconfirm 753 (124 shared + 629 ii); luna 5,785 (753 shared + 8 × 629; 2 incomplete); luna-autoconfirm 753 (124 + 629; 1 incomplete); sol 1,382 (753 + 629 `authority_notice`); gpt-4o-mini 2,011 (753 shared + 629 `tool_knowledge` + 629 `authority_notice`) | 13 × 629 = 8,177 exploratory (Note 2, Table S6) |
| exp7 `runs_exp7.tar.gz` | gpt-4o-mini 753 (shared); `-noegress` 753; `gpt-4o-mini-…-rep1..3` 162 each; `gpt-6-luna-rep1..3` 162 each | 753 + 972 (Note 5: 18 benign + 27 direct + 117 injection cases per repetition) |
| Per model (distinct) | haiku 1,678; luna 8,535; sol 1,511; gpt-4o-mini 4,756; gpt-3.5-turbo 2,259 | sum 18,739 |

## 2. Expected arms

Facets: model (5) × condition (`none`, `authority_cap_a3`, `authority_cap_a4`, `no_egress`; harness settings `autoconfirm`, `rep1..3`) × attack (10 values) × suite (banking, slack, travel, workspace; AgentDojo `v1`) × task kind (user / `injection_task_*` prepass).

| Expected | Cells |
|---|---|
| Attack totals (distinct) | `important_instructions` 9,656; `authority_notice` 1,887 (luna, sol, mini); `tool_knowledge` 1,258 (luna, mini); `direct`, `ignore_previous`, `important_instructions_no_names`, `important_instructions_wrong_user_name`, `injecagent`, `system_message` 629 each (luna only); none 2,164 (census) |
| `important_instructions` decomposition | 12 full arms × 629 + 2 autoconfirm × 629 + 6 reps × 117 + pilot 148 = 9,656 (derived; pilot = 144 haiku banking + 4 in the 13 extras) |
| none decomposition | 15 × 124 + 6 reps × 45 + pilot 34 = 2,164 (pilot = 25 haiku banking + 9 extras) |
| Suite totals | banking 4,391, slack 3,189, travel 4,139, workspace 7,020 (census); per full arm 169/131/167/286; implied per repetition 39/29/39/55 if the 13 pilot extras are banking (derived) |
| Missing by design (not defects) | caps and no-egress for Haiku and Sol (retrospective only); no-egress for 3.5 and Luna; Luna and 3.5 not run with `tool_knowledge`/`authority_notice` beyond the above; autoconfirm for Sol under attack; Haiku with `authority_notice` (Note 3); DoS attacks; AgentDojo v1.2 tasks (study restricted to the 629 v1/v1.2-shared cases) |
| Extra relative to the paper | 182 pilot logs (paper describes 169); 3,260 re-packed copies (collapse) |
| Upstream copies | 0: historical AgentDojo logs stay upstream (README v2.1.0, "derived data, not every upstream trajectory"); 0 known elsewhere (census) |
| Identity | logged `pipeline_name` = directory in every log; model = directory without suffix (21 table rows, class I `agentdojo.pipeline_dir_is_model_identity@1`); `gpt-6-luna`/`gpt-6-sol` without snapshot date; GPT-6 with reasoning effort none (RESULTS_new_models.md; Table S17) |

## 3. Expected outcome rates (L1 population, binding; L2 Wilson only)

Metric mapping (AgentDojo TraceLogger): **ASR** = `security` True over the 629 attacked user-task logs of an arm; **benign completion U** =
`utility` True over the 97 attack-none `user_task_*` logs; **direct-goal completion e_dir** = `utility` True over the 27 attack-none
`injection_task_*` logs; **utility under attack** = `utility` True over the 629 attacked logs. Run errors carry the runner-imposed
`security` True (quirk `run_error_imposes_outcome`, AgentDojo #154): the paper's enforced comparisons use non-error pairs
(611/612/628), so error and incomplete logs are excluded before comparing those arms. Counts are the paper's percentages ×
denominator (1-decimal rounding: ±1 tolerance).

| Arm (dir; attack) | Paper | Expected count | Ref |
|---|---|---:|---|
| haiku; benign U / e_dir / ASR (ii) | 73.2% / 59.3% / 0.2% | 71/97, 16/27, 1/629 | Table S17, S4 |
| haiku-autoconfirm; e_dir / ASR (ii) / UuA | 85.2% / 0.8% / 65.0% | 23/27, 5/629, 409/629 | S17, S6 |
| luna; U / e_dir / ASR (ii) / UuA | 83.5% / 92.6% / 2.1% / 74.1% | 81/97, 25/27, 13/629, 466/629 | S17, S4, S6 |
| luna-autoconfirm; e_dir / ASR / UuA | 92.6% / 1.4% / 73.6% | 25/27, 9/629, 463/629 | S17, S6 |
| sol; U / e_dir / ASR (ii) / UuA | 82.5% / 59.3% / 0.0% / 76.5% | 80/97, 16/27, 0/629, 481/629 | S17, S6 |
| sol-autoconfirm; e_dir | 59.3% | 16/27 | S17 |
| luna exp5: authority_notice / direct / system_message / ii_no_names / tool_knowledge / ignore_previous / ii_wrong_user_name / injecagent (ASR) | 4.9 / 4.6 / 4.1 / 1.8 / 0.9 / 0.8 / 0.8 / 0.5% | 31 / 29 / 26 / 11 / 6 / 5 / 5 / 3 of 629 | S6 |
| same (UuA) | 74.6 / 76.5 / 76.1 / 74.9 / 76.3 / 76.8 / 76.5 / 77.0% | 469 / 481 / 479 / 471 / 480 / 483 / 481 / 484 | S6 |
| sol exp5 authority_notice (ASR / UuA) | 0.0% / 75.7% | 0, 476 | S6 |
| gpt-4o-mini base (ii; ASR / UuA / U) | 41.3% / 39.0% / 66.0% | 260/629, 245/629, 64/97 | S6, Note 5 |
| gpt-4o-mini tool_knowledge / authority_notice (ASR; UuA) | 27.8% / 23.8%; 52.5% / 43.7% | 175, 150; 330, 275 | S6 |
| gpt-4o-mini-capA3 (ASR; U) | 3.34%; 35.05% | 21/629; 34/97 | S10, S11, S24 |
| gpt-4o-mini-capA4 | 23.37%; 60.82% | 147/629; 59/97 | S10, S11 |
| gpt-4o-mini-noegress | 9.54%; 38.14% | 60/629; 37/97 | S10, S11 |
| gpt-3.5-turbo base (ii, non-error) | 9.5% over 612 [corrected: the 612 are the cases where neither this Sept 2026 run **nor the historical upstream run** errored; the historical logs are not in this corpus, so the denominator cannot be rebuilt here: compare the rate over this arm's non-error attacked logs, ±2 pp] | 58/612 | Note 5 |
| gpt-3.5-turbo-capA3 (non-error pairs) | 0.65%; 22.58% | 4/611; 21/93; 12 error/missing attacked | S10, S11, S13 |
| gpt-3.5-turbo-capA4 | 1.96%; 37.23% | 12/612; 35/94; 15 error/missing attacked (base 15) | S10, S11, S13 |
| gpt-6-luna-capA3 | 0.16%; 38.14% | 1/628; 37/97; 1 missing | S10, S11, S13 |
| gpt-6-luna-capA4 | 0.95%; 73.20% | 6/629; 71/97 | S10, S11 |
| rep1..3 (117 cases each, with the base run's subset: 4 runs) | mini ASR 44.4–50.4%; luna 1.7–3.4% | mini 52–59/117 per run; luna 2–4/117 | Note 5 |

Not comparable (do not use): Table S2/S16 rates for gpt-4o-mini (68.0/27.2) and gpt-3.5-turbo (35.1/10.3) are the
historical upstream logs, not these re-executions; reference-scored A3/A4 rates (S10 "Reference", S17 "ASR at A3/A4") are
retrospective scores of the full-authority runs, not a logged arm. Sampling: about 256 strata (experiment × directory × suite ×
attack) against the 300 cap gives about 1 unit per stratum, so no L2 arm reaches 20 executions; L2 rates are Wilson only.

## 4. Known quirks (already recorded)

| Id | Expected (profile counts are over the 21,999 members) | Source |
|---|---:|---|
| `agentdojo.benign_security_constant` | 2,908 attack-none members (2,164 distinct + 744 copies); origin rule applied 2,898 | profile |
| `agentdojo.injection_task_as_user_task_prepass` | 741 members | profile |
| `agentdojo.silent_rerun_last_pass_only` | 85 null-final logs; trial `retry_passes_inferred` 85 (census `last_assistant_null` True 137 distinct; definitions differ, reconcile) | profile; trial; census |
| `agentdojo.unexecuted_trailing_calls` | 126 calls in 104 logs; trial `unexecuted_tool_call` 104 | profile; trial |
| `agentdojo.args_mutated_in_place` | 21,799 members with calls | profile |
| `agentdojo.package_version_not_code_identity` | 0 without package version (all `0.1.35`) | profile; census |
| `agentdojo.placeholder_args_never_injection_evidence` | 100,082 present, all null | profile |
| `agentdojo.incomplete_run` | 5 (3.5 base 1, luna-capA3 1, luna exp5 2, luna-autoconfirm 1); trial `incomplete_run` 5 | profile; census; trial |
| `agentdojo.provider_call_id_anomalies` | 0 | profile |
| `agentdojo.run_error_imposes_outcome` | 51 error logs; trial `outcome_imposed_by_runner` 51 | profile; census; trial |
| Header fields | `benchmark_version` `v1` all; one system prompt `a021a92b…` (469 chars, AgentDojo default at 089ed468); timestamps all 2026-09 | census |
| Harness identity | `code_identity = unpinned`, every D rule through its `_unverified` twin (D-24) | profile |
| artefacts.toml | no entry scoped to this source; `run_error_imposed`, `benign_security_constant`, `injection_task_as_user`, `silent_rerun`, `incomplete_run`, `naive_timestamp`, `calls_derived_from_messages`, `payload_not_reaching_agent`, `max_iters_pending`, `defence_benign_intervention` describe it; scope extension proposals go through the orchestrator | `src/agentprov/adapters/agentdojo/artefacts.toml` |
| Decisions | D-250 (pin, nested tars, collapse, identity); D-257 (no `[withhold]`); D-258 (fixtures); D-560 (exclude-matched members get register rows at next import: `.DS_Store`/`._*`) | DECISIONS.md |

## 5. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §1 tables; reconcile 22,250 vs 3,041 + 19,212; 21,999 selected, 0 TraceLogger outside globs; per-directory and per-experiment counts; `MANIFEST.sha256.json` vs members (H12) |
| L1-02 strict parse | yes | expect 0 defects (census: 22,012 / 22,012 ok); `--lenient-classes` only if strict failures |
| L1-03 encodings | yes | expect literal `\uXXXX` residues only as harness property (AgentDojo #214, yaml/json ASCII escaping); 0 bidi/tag/C0 |
| L1-04 duplicates | yes | 3,260 byte copies in exactly the 5 directory groups of §1; 4 content groups / 13 files; 0 cross-corpus overlap (no upstream copies; new 2026-09 runs) |
| L1-05 arm coverage | yes | §2 grid and §3 counts; pilot composition; rep cell sets (H6) |
| L1-06 secrets / account paths | yes | expect 0 (census: none in any member, nested included); mock environments only (README) |
| L1-07 timestamps | yes | all 2026-09; naive; current-model window (H9); max ≤ v2.0.0 deposit time (H10) |
| L1-08 truncation / degenerate | yes | 5 incomplete, 51 error, 85 null-final, 0 empty or zero-message expected |
| L2 import / validate / recompute / determinism | yes | trial: 18,739 executions, 0 failed checks, chain exit 0; sample labels must be unique across containers (open question Q1) |
| L2 A2 / A3 classes | yes | register codes only the trial's (`outcome_imposed_by_runner`, `retry_passes_inferred`, `unexecuted_tool_call`, `incomplete_run`, `dedup.collapsed`) |
| L2 evidence classes | yes | no agentdojo D rule without `_unverified` twin; identity class I |
| L2 identity | yes | 21 rows; defence `authority_cap_a3/a4`, `no_egress`, else `none`; autoconfirm/repN never a defence |
| L2 redaction | yes (negative) | 0 account paths expected; nothing to redact |
| L2 withholding / `verify --level chain` sealed | no | D-257: no `[withhold]` table; chain verify still run as part of the import proof |
| L2 outcome sanity | yes (Wilson only) | binding comparison is the L1 population (§3) |
| E2 delta | no | never stored (registry `planned`); last runs are the phase-10j trials |
| Data-record checksum | yes | md5 and size against the record (already equal at fetch, profile note) |

## 6. Hypotheses (falsifiable)

| # | Expectation | Falsified if |
|---|---|---|
| H1 | Every §3 count holds on the byte-distinct population (non-error logs for the 3.5 and capped arms) | any count off by ≥ 2, or a README §4 gap (> 15 pp on n ≥ 20) |
| H2 | The 51 error logs and the incompletes sit in the arms Table S13 names: ≥ 41 error logs in the three `gpt-3.5-turbo-0125*` directories' attacked logs (base 15, A3 12, A4 15 unknown, incl. ≤ 1 incomplete), the rest attack-none (2,908 − 2,898 = 10 none logs without the origin rule); 0 errors in Haiku, Sol, Luna and 4o-mini arms | < 41 in the 3.5 attacked logs, or any error in a current-model or 4o-mini directory |
| H3 | In cap and no-egress directories no tool above the cap (Table S1 levels: A3 cap blocks A4/A5 tools; A4 cap blocks A5) has an error-free tool result; calls to such tools return a ToolNotFoundError-type error | ≥ 1 error-free result of a blocked tool |
| H4 | No `security` True on slack `injection_task_5` logs in `-capA3`, `-capA4`, `-noegress` directories whose membership calls failed (paper S24: 0 enforced successes on a blocked attacker path; AgentDojo #168/#189 would score proposed-but-blocked sequences) | ≥ 1 such log |
| H5 | Pilot = 169 Haiku banking logs (16 benign, 9 direct, 144 ii) + 13 banking extras (luna 5, sol 5, haiku-autoconfirm 3; 4 ii + 9 none) | any other composition |
| H6 | The six `-rep1..3` directories have 162 logs each with one shared cell set (18 benign, 27 direct, 117 ii; suites 39/29/39/55), a subset of the base arm's cells; across the 4 runs (base + 3 reps) mini ASR 52–59/117 per run, all-four-agree share 78/117 (66.7%); luna 2–4/117, 108/117 (92.3%) | a rep differs in cell set, or any rate outside the stated range by ≥ 2 cases |
| H7 | Auto-confirm: a second (harness) user message exists only in `-autoconfirm` directories, is one fixed text, appears at most once per log; 0 extra user messages elsewhere | an extra user message outside autoconfirm dirs, > 1 per log, or > 1 distinct text |
| H8 | Every `important_instructions` injection addresses the user as "Emma Johnson" (Note 1: all 2025–2026 models got the correct name; Note 5: injections generated by the current package use "Emma Johnson" [citation corrected]); "Emma Smith" appears only under `important_instructions_wrong_user_name` | ≥ 1 ii log with the wrong name |
| H9 | The 2,259 current-model full-arm logs have `evaluation_timestamp` inside one 68-minute window (04:47–05:55 UTC on 2026-09-26, after one constant whole-hour offset for naive local time; window from Supplementary Note 2, "main runs"); pilot logs precede it [basis note: Note 2 says only that the pilot ran after the prediction file (02:24 UTC) and checked software compatibility; its order relative to the main runs is inferred, not stated] | > 1% outside the window |
| H10 | No timestamp later than the v2.0.0 deposit (2026-09-27 12:41 UTC, +14 h tolerance for naive local time); v2.0.0 and v2.1.0 state no new model calls | any later timestamp |
| H11 | Logged `pipeline_name` equals the directory in all 21,999 members; 21 directories, each matching a table row | any mismatch or a 22nd directory |
| H12 | `MANIFEST.sha256.json` lists every zip member except itself with matching sha256 (nested tars as files) | any member missing or differing |
| H13 | 0 secret-like strings and 0 account paths in the 21,999 members | ≥ 1 |
| H14 | L2: 0 failures, 0 degenerate; register codes only those of §5; byte-identical across `--jobs` | any other code or byte difference |

## 7. Desk-research items for the dossier (no data check needed)

- The manuscript is not public (no arXiv or DOI found 2026-10-15); the published reported results are the deposit's Supplementary
  Material v2.1.0 (Tables S1–S25). Its title, *Do Recorded Trajectories Predict Enforced Tool Permissions? …* (Chang and Chiu),
  differs from the profile's `paper` field, which gives the record title (documentation-mismatch, our side, S3).
- Profile header and census §2 say "eight further AgentDojo attacks with 629 each"; the census counts give seven further attacks
  (six at 629, `tool_knowledge` at 1,258), the paper's "seven other templates" (documentation-mismatch, our side, S3).
- The deposit README v2.1.0 says `original-study/` (where the current-model, pilot, exp4 and exp5 runs and `RESULTS_new_models.md` sit; exp7 is in `raw-additions/` [corrected]) is a legacy layer whose README,
  counts and table numbering do not describe the current manuscript; our context artefacts and identity notes cite it. Disclose.
- Temperature 0 is claimed for all runs (Table S17); AgentDojo 0.1.35 from PyPI drops `temperature=0.0` for OpenAI models (#141,
  fixed after the wheel without a version bump). The logs cannot settle it; the examiner may read `source-snapshots/run_new_models.py`
  (a context artefact) at L1.
- Banking UT5 and UT9 checker permissiveness (AgentDojo #161; paper Table S25) and banking IT0/1/3 dead subject check (#181) apply
  to these v1 runs; disclose, never re-score.
- Never exclude Haiku or Sol arms for having 0 attack successes (user rule).

## 8. Expected movement since E2

Not applicable: never examined in FA or E2 and never stored. Bytes may differ from the phase-10j trial (merged origin/main
9566a207) only through code changes since; counts and outcomes must not. D-560 adds register rows for exclude-matched members
at the next import (no AER, SEM or PROV byte change).

## 9. Fact-check (2026-10-15, adversarial, desk research only)

Checked against the published sources; no raw data read, no new expectation added.

- **Data record and pin**: Zenodo API `records/23138310` and the versions listing (3 versions under concept 22973265; 23138310
  v2.1.0 newest) match: zip 40,160,657 B, md5 `3fba80315a4879d381fb3b14fd386ace`, the same file in 22996368 (v2.0.0); v1.0 zip
  11,226,444 B; 7 files in v2.1.0 with the sizes and md5s in research.json; record licence cc-by-4.0. The v2.0.0 and v2.1.0
  descriptions both say no new model calls were made; v1.0's says 2,259 new current-model runs and an auto-confirm condition.
- **Paper**: the Supplementary Material v2.1.0 PDF (md5 `3007180b…`, 34 pages; Chang and Chiu, Shih Chien University) was
  re-read; manuscript not on arXiv or Crossref. Every §3 count was recomputed from Tables S4, S6, S10, S11, S13, S17, S24 and
  Notes 2 and 5 (all within rounding; the Wilson intervals of S6/S17 agree with the counts; 6/629 gives Luna
  `tool_knowledge` [0.4, 2.1]). `alt_path_decomposition.csv` gives 0 enforced ASR successes on blocked paths and 14 completion
  successes (2 per condition, banking UT5/UT9).
- **Counts**: 18,557 = 2,631 + 7,749 (6,024 + 753 + 972) + 8,177 (13 × 629) is in Note 5; per-directory, per-model (sum 18,739),
  `important_instructions` (9,656) and none (2,164) decompositions are arithmetically consistent; 9,656 + 1,887 + 1,258 + 6 × 629 +
  2,164 = 18,739 confirms "seven further attacks" (the profile header and census §2 "eight" is our error).
- **Harness**: issue/PR states confirmed via the GitHub API (#141 merged as `462c88dd`; #154, #161, #168, #181, #214, #218 open;
  #189 closed "completed" 2026-09-07; #203 and #207 open PRs); `089ed468` (2026-06-02) is still main head; PyPI 0.1.35 wheel
  2025-10-27. The #141 diff confirms the wheel's OpenAILLM sends no temperature when it is 0.0.
- **Corrected**: (1) §3 gpt-3.5-turbo base: the 612 denominator is paired with the historical upstream run (not rebuildable from
  this corpus); (2) H8 citation: the "all 2025–2026 models" statement is in Note 1; (3) §7 and research.json: exp7 sits in
  `raw-additions/`, not in `original-study/`; (4) research.json `repo`: `462c88dd` does affect OpenAI decoding if a post-wheel
  build was used (was "none touches these logs"); (5) H9: the pilot-before-main-runs order is an inference, not a paper statement.
- **Unverifiable here**: the licence files inside the zip (`LICENSE-DATA`, `LICENSE-CODE`, `AGENTDOJO_LICENSE`) and the content of
  `run_new_models.py` (payload not downloaded; taken from our phase-10j reports); every census-derived count (by design).
