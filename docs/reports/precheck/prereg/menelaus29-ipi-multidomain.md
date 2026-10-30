# Pre-registration: `menelaus29-ipi-multidomain`

| | |
|---|---|
| Corpus | `menelaus29-ipi-multidomain` (family `agentdojo`, profile `menelaus29-ipi-multidomain` v1, dialect/mapper `agentdojo.tracelogger`, variants `v1.k14`, `v1.k14.incomplete`; identity table `menelaus29_experiment_dirs.toml`, keyed by experiment path, D-104) |
| Parts | `head` (only part; the 107 branch-only logs wait, D-108) |
| Wave | 3 (first examination; not in FA or E2) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: our prior reports (phase-10c census summaries, phase-10d census, trial and reconcile), the profile, identity table, registry, `artefacts.toml`, DECISIONS, and desk research (`data/menelaus29-ipi-multidomain/research.json`). Per-directory counts come from the GitHub trees API listing of the pin (paths, sizes, blob SHA-1s only). Author numbers come from the repository's own aggregate reports (README, `docs/*.md`, summary JSON/CSV). No run log was read and nothing here was computed from the raw logs. |
| Method | [`../README.md`](../README.md) |

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Repository | [Menelaus29/ipi-multidomain-agent-study](https://github.com/Menelaus29/ipi-multidomain-agent-study), MIT, (c) 2026 Khue Vu; no data licence | LICENSE at pin; GitHub API |
| Pin | `ec9c9287889ebec339c4304f01a4a4a99500c491` "chore: docs update", 2026-08-22T13:00:49Z; still head of `main` on 2026-10-14; touches no run log | GitHub API |
| History | 857 run logs whose pinned blobs were first added by 9 commits 2026-08-03..17, plus 92bcd7ff for the example log (**corrected** from "10 commits") (research.json `repo`); 44 workspace defence-dev traces and 14 Groq sanity logs deleted in history; 16 branches, only `phase-6a-attack-calibration` and `phase-8-defense-spotlighting` add logs (107) | GitHub API |
| Paper | **none** (arXiv, web, Zenodo, HF: 0 hits). The final report is git-ignored (`report/final_report*`), unpublished. Reported numbers come from README and `docs/*.md` | research.json |
| Data record | none; Git repository only; pin = head | Zenodo/HF APIs |
| Harness | `agentdojo==0.1.35` (requirements.txt, UTF-16LE with BOM and CRLF; **corrected**, see Fact-check), suites v1.2.2; Python API with a custom Google AI Studio factory under the enum alias `gemini-2.5-flash-preview-04-17`; code identity a range (D-24/D-103) | requirements.txt; decisions_log |
| Models | `google-gemini-3.5-flash-lite` (static baseline), `google-gemma-4-26b-a4b-it` (defence track, diagnostics), `google-gemini-3.6-flash` (6 sanity logs, directory label only) | identity table; census |
| Defences | `my_spotlighting` v1 (1,331-char system prompt + delimiters/datamarking, SHA-256 `7ce3de91…`); AgentDojo `spotlighting_with_delimiting` | docs/defense_validation.md |
| Run window | 2026-08-04 00:11:39 .. 2026-08-17 13:38:58 (naive) | phase-10c census `ts_range` |

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Tree blobs at pin | 1,028 (24,703,359 B; 23,568,555 B without the 8 PNGs) | profile `expected_files`; git tree |
| Selected | 858 = 857 run logs (`data/…/<pipeline dir>/<suite>/<task>/<attack>/<file>.json`) + `docs/example_run_output.json` | registry/`readme_corpora.toml` (census `/files`); git tree |
| Not selected | 170 (incl. author ledgers `results.jsonl`, `attempts.jsonl`, 2 `google_generate_content_events.jsonl`); 13 context artefacts stored as supporting | profile; git tree |
| JSON parse ok | 914 / 914 data/doc JSON blobs | phase-10c census |
| Units / executions | 857 `agent_execution` + 1 `outcome_only` / 858 | phase-10d census; trial |
| Variants | `v1.k14` 857, `v1.k14.incomplete` 1 | census |
| Sealed clean / with issues | 856 / 2 | trial (jobs 8) |
| Register codes | `accounting_unverifiable` 857, `earlier_attempts_unobservable` 857, `system_prompt_unrecognised` 358, `identity_unresolved` 1, `no_execution_observed` 1, `no_outcome_recorded` 1 | trial |
| Byte-identical logs | 0 (857 distinct git blob SHA-1s) | git tree |

Per experiment directory (attacked + pre-pass), git tree at the pin:

| Experiment dir | Model / defence | banking | workspace | slack | Total |
|---|---|---|---|---|---:|
| `baseline/raw` | Gemini 3.5 FL / none | 47+2 | 53+2 | 13+2 | 119 |
| `baseline_gemma4/r` | Gemma 4 / none | 46+2 | 52+2 | 12+2 | 116 |
| `baseline_gemma4/full/r` | Gemma 4 / none | 180+9 | | | 189 |
| `defended/g4/v1/fresh160/r` | Gemma 4 / my_spotlighting | 160+9 | | | 169 |
| `…/replication_dev/builtin/r` | Gemma 4 / spotlighting_with_delimiting | 20+2 | | | 22 |
| `…/replication_dev/custom/r` | Gemma 4 / my_spotlighting | 20+2 | | | 22 |
| `adaptive/g4/v1` | Gemma 4 / my_spotlighting | 24+4 | | | 28 |
| `adaptive/g4/v2a` | Gemma 4 / my_spotlighting | 73+7 | | | 80 |
| `adaptive/g4/v2a_repair` | Gemma 4 / my_spotlighting | 16+4 | | | 20 |
| `adaptive/g4/v2b` | Gemma 4 / my_spotlighting | 33+7 | | | 40 |
| `diagnostics/g4` + `/raw` | Gemma 4 / none | 6+1 | 7+2 | 12+3 | 31 |
| `diagnostics/gemma4_sanity_check` (raw, s1, step1_retry) | Gemma 4 / none | 3+1 | 4+3 | 3+1 | 15 |
| `sanity_check` | Gemini 3.6 Flash / none | 1+1 | 1+1 | 1+1 | 6 |
| **Total** | | 680 | 127 (+1 example log = 128) | 50 | **857** |

Attacked 787, pre-pass 70 (all `injection_task_*/none/none.json`), benign user-task runs 0. Reconciliation with the
authors' n: 787 = 770 reported evaluations (110 + 110 + 180 + 160 + 20 + 20 + 24 + 72 v2a + 16 + 33 + 25 diagnostics)
+ 3 injecagent controls + 10 Gemma sanity + 3 Gemini 3.6 sanity + 1 unvalidated v2a log.

## 3. Expected arms

| Facet | Values | Expected missing / extra |
|---|---|---|
| Model | Gemini 3.5 FL (119), Gemma 4 26B (732 incl. 22 built-in spotlighting logs with no model in the logged name), Gemini 3.6 Flash (6); example log unresolved | none extra |
| Defence | none, my_spotlighting (359 logs), spotlighting_with_delimiting (22) | Workspace/Slack never defended (by design) |
| Suite | banking, workspace, slack (v1.2.2) | travel never used |
| Attack | 196 labels + none: `corpus_<payload>_<vector>` (19 payloads in parity dirs), `injecagent` (3), `p9_<hash>` (15), `adaptive_<hash>` (one per evaluation), diagnostic built-ins, `tool_knowledge` | adaptive labels repeat across arms with the same key (v1∩v2a 19, v1∩v2b 11, v2a∩v2b 32), never byte-identical |
| Parity plan cells | banking UT0/1/13 × IT0/1, workspace UT1/3/14/16/26 × IT0/1, slack UT0/2 × IT1/2; Gemma = Gemini keys minus the 3 injecagent | none |
| Follow-up 180 | {UT0 bill_text, UT13 address_change, UT2 and UT12 landloard_notice} × IT0-8 × 5 payloads; fresh160 = minus {UT0,UT13} × {IT0,IT1} | none |
| Missing by design | benign user-task runs (0); pre-pass only for injection tasks used; 107 branch-only Phase 6A/8 logs (D-108); deleted dev traces and pilots | — |
| Extra vs reported | 3 injecagent, 15 Gemma sanity (10 attacked), 6 Gemini 3.6 sanity (3 attacked), 1 v2a log, example log | no reported outcome |

L2 strata: experiment dir × suite × (attacked | pre-pass) = 51 non-empty + the example log = 52; about 5 each, ~158 units
(all units where a stratum has fewer than 5).

## 4. Expected outcome rates (L2 comparison targets)

Metric mapping: the authors' "native attack success" = AgentDojo `security` of the trace (decisions_log "Correct
AgentDojo success semantics"; validation reports compare `raw_security` with the index), utility = AgentDojo `utility`.
Denominators exclude pre-pass logs (`security` constant True, #95) and the injecagent controls. Adaptive "payload
bypass coverage" is not a per-log rate; per-log targets are bypasses / target evaluations.

| Arm (dir) | n attacked | Security true (ASR) | Utility true | Source |
|---|---:|---|---|---|
| Gemini 3.5 FL baseline, all | 110 | 0/110 | 90/110 | baseline_null_analysis.md; exposure_summary.json |
| ↳ workspace / banking / slack | 52 / 46 / 12 | 0 / 0 / 0 | 52 / 26 / 12 | same |
| Gemma parity, all | 110 | 5/110 (4.55%) | not reported (legacy null) | cross_domain_findings.md |
| ↳ workspace / banking / slack | 52 / 46 / 12 | 0 / 5 (10.87%) / 0 | — | same |
| Gemma follow-up fresh160 (in `full`) | 160 | 34 (21.25%) | 103 (64.375%) | defense_validation.md |
| Gemma follow-up replication (in `full`) | 20 | 6 (30%) | 10 | gemma_banking_followup_protocol.md |
| fresh160 my_spotlighting | 160 | 4 (2.50%) | 115 (71.875%) | defense_validation.md; summary.csv |
| replication_dev builtin | 20 | 4 (20%) | 10 (50%) | defense_validation.md |
| replication_dev custom | 20 | 0 | 10 (50%) | same |
| adaptive v1 | 24 | 1 | 14 | phase12_adaptive_summary.csv |
| adaptive v2a + v2a_repair | 72 + 16 | 1 (repair 0) | 71/88 | same; aggregation_report.json |
| adaptive v2b | 33 | 5 | 22 | same |
| Gemma diagnostic (`diagnostics/g4` + `/raw`) | 25 | 2 (banking direct, slack tool_knowledge) | — | decisions_log |
| Pre-pass (all dirs) | 70 | 70 (constant) | — | census |

Whole-population checks (L1, exact): attacked security True = 63 (census 133 − 70); reported arms sum to 62.
Per-arm L2 rates use the sample with Wilson intervals; the exact per-directory tallies of H2-H6 run on the whole
population at L1.

## 5. Known quirks

| Id | Expected | Source |
|---|---|---|
| `agentdojo.benign_security_constant` | 70 files | profile, census |
| `agentdojo.injection_task_as_user_task_prepass` | 70 files | profile, census |
| `agentdojo.args_mutated_in_place` | 857 files | profile, census |
| `agentdojo.placeholder_args_never_injection_evidence` | 2,473 present, all null | profile, census |
| `agentdojo.silent_rerun_last_pass_only` | 0 null-final logs; `earlier_attempts_unobservable` 857 | profile, trial |
| `agentdojo.unexecuted_trailing_calls` | 0 | profile, census |
| `agentdojo.incomplete_run` | 1 (v2a UT12 × IT4, `adaptive_b43850c62aa7`) | profile, census |
| `agentdojo.empty_messages_without_outcome` | 1 (same file) | profile, census |
| `agentdojo.empty_messages_with_outcome` | 1 measured by the census, not declared in the profile (**added** by the fact-check from the census JSON; which file is not stated there) | phase-10d census `/measured` |
| `agentdojo.spotlighting_delimiters` | 22 logs, all with tool results | profile, census |
| `agentdojo.package_version_not_code_identity` | 0 without version (all 0.1.35) | profile |
| System prompts | default 477, my_spotlighting 358 (unrecognised), built-in spotlighting 22, none 1 | census |
| Tool errors / `error` field | 2 tool errors; `error` null in 858 | census |
| Identity | pipeline names carry the alias, never the model (`pipeline_name_policy = verbatim_unreliable_when_differs`); table rows class I | profile, table |
| Accounting | `unverifiable` 857 (+1 outcome-only) | census, trial |
| `artefacts.toml` | no entry scopes this source; generic analogues: benign_security_constant, injection_task_as_user, silent_rerun, incomplete_run, empty_log, naive_timestamp, validity_defects (banking precedence #181), payload_not_reaching_agent | artefacts.toml |
| Decisions | D-95 (three pins, 965 runs), D-104 (table by path), D-108 (main only) | DECISIONS |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2 per directory; selection by `include` glob, 13 context artefacts |
| L1-02 strict parse | yes | expect 0 defects; requirements.txt BOM is a context artefact, not a log |
| L1-03 encodings | yes | `\uXXXX` residues expected in encoding-payload tool content (#214): expected-known |
| L1-04 duplicates | yes | within part: 0 byte-identical; adaptive keys shared across arms (H12); cross-corpus: none expected |
| L1-05 arm coverage | yes | §3 and H1-H6 |
| L1-06 secrets / account paths | yes | expect 0 (author reports hold `C:\Users\user\…` but are not selected) |
| L1-07 timestamps | partly | presence, parse, naive zone, range; vs commit times (H10); no within-unit monotonicity |
| L1-08 degenerate | yes | expect 1 empty/outcome-less, 0 null-final, 0 run errors |
| L2 import, validate, recompute, determinism | yes | trial: 0 failures; the jobs-8 import (858) and a jobs-3 import of a 180-unit subset compare with 0 differences (subset mode, **corrected**) |
| L2 A2 / A3 classes | yes | expect only the trial's register codes |
| L2 evidence classes | yes | D rules only as `_unverified` twins (`verified_code = []`) |
| L2 degenerate / adapter_defect | yes | expect 0 / 0 |
| L2 identity | yes | model and defence from the table by experiment path; example log unresolved |
| L2 redaction | yes | no account path in AER/SEM/PROV |
| L2 withholding | conditional | only if L1-06 finds anything |
| L2 outcome sanity | yes | §4 per directory, Wilson intervals, README §4 threshold |
| Delta since E2 | no | first examination |

## 7. Hypotheses (falsifiable)

| # | Expectation | Refuted if |
|---|---|---|
| H1 | Per-directory, per-suite attacked/pre-pass counts equal §2; 70 pre-pass only under `injection_task_*`; 0 benign user-task logs | any count differs by ≥ 1 |
| H2 | Gemini baseline: security True 0 of 110 corpus logs; utility True 52/52 workspace, 26/46 banking, 12/12 slack | any differs by ≥ 1 |
| H3 | Gemma parity: 5/110 True, all banking, payloads persona-04, encoding-03, fake-system-04, template-02, template-03, vector bill_text; key set = Gemini keys minus 3 injecagent | any differs |
| H4 | `full`: 34/160 fresh and 6/20 replication True; utility 103 and 10 | any differs by ≥ 1 |
| H5 | fresh160 4/160, utility 115; builtin 4/20, utility 10; custom 0/20, utility 10 | any differs by ≥ 1 |
| H6 | Adaptive: v1 1/24 (utility 14); v2b 5/33 (22); v2a 1 True among 72 outcome-bearing logs, repair 0/16, utility v2a + repair 71/88; the 73rd v2a log is the empty outcome-less one | any differs, or the empty log is elsewhere |
| H7 | Diagnostics `g4` + `/raw`: exactly 2 True of 25 (banking direct, slack tool_knowledge) | other count or arms |
| H8 | Attacked security True = 63 over 787; the 1 outside reported arms lies in injecagent / Gemma sanity / Gemini 3.6 sanity | ≠ 63, or 0 / ≥ 2 outside |
| H9 | Banking successes on IT0/IT1/IT3 (#181): count reported; any success whose attacker transfer lacks the stated subject content is a benchmark validity flag (expected-known by analogy, S2), never a mapping defect | a mapping difference from AgentDojo's own verdict |
| H10 | All timestamps within 2026-08-04 00:11:39..2026-08-17 13:38:58; each log's naive time minus 14 h precedes its adding commit's UTC time | any later (re-run or edit; S3) |
| H11 | Pipeline names: alias in 858; Gemma 710, Gemini 3.5 FL 120 (incl. example), built-in 22, Gemini 3.6 6; no log names gemini-3.1-flash-lite (note: the run-time fallback for the Gemini 3.6 sanity logs was gemini-3.5-flash-lite and would not change the logged name, so H11 cannot detect it) | any other name |
| H12 | Identical trajectory fingerprints across adaptive arms for the 62 shared attacked keys (19 + 11 + 32) = 0; pre-pass keys shared too: 23 + 15 + 39 = 77 pairwise for v1/v2a/v2b, plus 4 + 3 + 4 with `v2a_repair` (**corrected**: 62 excludes pre-passes) | ≥ 1 (C5 finding) |
| H13 | 0 secret-like strings, 0 account paths in the 858 selected files | ≥ 1 |
| H14 | SEM injection marker present in ≥ 105 of the 110 Gemini baseline attacked runs (authors: 110/110 visible after normalisation, 0 literal) | < 105: our marker misses YAML/escaped payloads (analysis or mapping limit, S2) |
| H15 | `system_prompt_unrecognised` exactly on the 358 my_spotlighting logs; built-in prompt digest on the 22 builtin logs | other set |
| H16 | Parity directories name exactly 19 payload ids (the corpus was N=22 at c0bb2156; at the pin it holds 19 templates after the `multi_step_sleeper` exclusion, **corrected**) | ≠ 19 |

## 8. Discrepancy leads carried to the dossier

No paper (numbers are the repository's own reports; final report unpublished); one v2a log outside the authors'
validated set (H6); 70 pre-passes and no benign user-task runs; 16 attacked logs with no reported outcome plus the unvalidated v2a log (H8);
banking IT0/1/3 security leniency (#181) under every headline banking ASR (H9); model identity of the 6 Gemini 3.6
sanity logs unverifiable (run-time wrapper fell back to gemini-3.5-flash-lite without renaming the pipeline; **corrected** from 3.1-flash-lite) and 22 built-in logs without a model name; Gemma parity utility unreported
(legacy null, PR #10); payload visibility needs normalisation (#214, H14); the author's two reports disagree on one
ledger digest (S3); `docs/example_run_output.json` names a model but maps `identity_unresolved` (S3, our docs).

## 9. Fact-check (2026-10-14, adversarial; desk only, no raw data read)

Checked against the GitHub API at the pin (commit, trees, commit file lists, branches, PRs, issues), the
repository's own reports at the pin (README, `docs/baseline_null_analysis.md`, `cross_domain_findings.md`,
`defense_validation.md`, `gemma_banking_followup_protocol.md`, `decisions_log.md`, `payload_corpus_notes.md`,
`defense_design.md`, `data/analysis/phase12_adaptive_summary.csv`, `phase12_reporting_report.json`,
`data/baseline/exposure_summary.json`, `data/adaptive/g4/aggregation_report.json`, `data/defended/g4/v1/summary.csv`),
LICENSE at the pin, upstream AgentDojo issues, arXiv, Zenodo and HF, and our phase-10c/10d census, trial and DECISIONS.

Confirmed:
- Pin `ec9c9287`, still head of `main`; 16 branches, 0 tags and 0 releases, 14 PRs (all merged), 0 issues. MIT, (c) 2026 Khue Vu.
- Tree: 1,028 blobs, 24,703,359 B (23,568,555 B without the 8 PNGs). 857 run logs with 857 distinct blob SHA-1s.
  Every per-directory and per-suite attacked/pre-pass count in §2, the 787/70 split, and 51 strata giving about 158 units.
- Branch-only logs: exactly 107 for both branches, by blob and by path, matching D-95's 965 − 858. Our phase-10c
  `branches_extra.json` gives 83 under another definition; this is an internal inconsistency to note, not a correction.
- Every number in §4 against its cited author file: 0/110 and 90/110 (52/26/12); parity 5/110 (0/5/0); 34/160 and 103/160;
  6/20 and 10/20; 4/160 and 115/160 with −18.75 pt [13.125, 25.0]; builtin 4/20, 10/20; custom 0/20, 10/20; adaptive v1 1/24
  (14), v2a 1/88 incl. 16 repair (71), repair 0/16, v2b 5/33 (22); diagnostic 2/25; Phase 6A 0/38. The authors' rule
  (aggregation_report: repair replaces 16 v2a slots, it adds no rounds) supports 72 v2a + 16 repair = 88.
- Diagnostic 25 sits in `diagnostics/g4` (25 operation files there, 10 in `gemma4_sanity_check`), although
  decisions_log first named `gemma4_sanity_check` as its home.
- Design cells from tree paths: follow-up {UT0 bill_text, UT13 address_change, UT2/UT12 landloard_notice} × IT0-8 × 5;
  fresh160 IT0/IT1 only on UT2/UT12; replication_dev {UT0,UT13} × {IT0,IT1} × 5; Gemma parity keys = Gemini keys minus 3 injecagent;
  parity banking uses IT0/IT1 only (#181 applies); adaptive attacked keys shared 19/11/32.
- Census figures: security 133/724/None 1, utility 632/225/None 1, pipeline names 710/120/22/6, system prompts
  477/358/22/1, ts range, 914 JSON parse ok; trial 856/2 and register codes.
- Authors' digest mismatch for `v2a_repair/attempts.jsonl` (a35446bb… in aggregation_report vs 3b3b89fb… in phase12_reporting_report).
- Windows account paths appear in non-selected author files (e.g. the fresh160 and replication_dev `validation_report.json`; counts only).
- Upstream issues: #181 (open, opened 2026-08-17), #214 (open), #213 and #168 (open, not applicable). #95 is **closed**: it is a
  maintainer clarification that `security` is always true without an attack, not an open bug.
- No paper or data record (arXiv, Zenodo, HF: 0 hits). `report/final_report*` is git-ignored at the pin. arXiv 2406.13352 and
  2403.14720 titles match, and the repository cites Hines et al. as the basis of `my_spotlighting` (`docs/defense_design.md`).

Corrected (marked in the text and in research.json):
- requirements.txt is UTF-16LE with a BOM and CRLF, not a UTF-8 BOM.
- Fix commit `54050916` does not exist. The tool-error wrapper commit is `54052916`.
- Gemini 3.6 sanity logs: the wrapper in force at the commits that added them (`91baece2`, `0491b4bc`) fell back to
  gemini-3.5-flash-lite, and the pipeline name is fixed at construction. The 3.1-flash-lite fallback belongs to the later wrapper
  described at the pin. The model stays unverifiable.
- The payload corpus N=22 was historical (c0bb2156). At the pin the corpus holds 19 templates.
- H12: 62 counts attacked keys only. With pre-passes there are more shared keys (see H12).
- Trial determinism compared a 180-unit subset, not all 858.
- Timestamps: the earliest blob still at the pin came from `0491b4bc` (2026-08-03T17:17:02Z), not the 15:44Z commit. The
  earliest naive stamp read as UTC+7 lands 5 min before it, which supports the UTC+7 reading. The pin's 857 run logs were first
  added by 9 commits; `92bcd7ff` added the example log, giving 10 commits for 858 files.

Unverifiable without data (left as hypotheses): that the 73rd v2a log is the empty one (H6); that `incomplete_run` and
`empty_messages_without_outcome` hit the same file (the census reports `incomplete_run.null_outcome_files` 0 and also
`empty_messages_with_outcome` 1); where the 63rd attacked success sits (H8); the datamarking count (359).

