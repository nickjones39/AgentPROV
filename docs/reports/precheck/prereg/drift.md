# Pre-registration: `drift`

| | |
|---|---|
| Corpus | `drift` (source `drift`, family `agentdojo`, profile `drift` version 1, dialect/mapper `agentdojo.tracelogger` through the DRIFT build, variant `drift.k18.conversations`) |
| Parts | `head`: 1,569 logs at `SaFo-Lab/DRIFT@6fd3df4763fad77398c3c273c2a4fe14dd50f7ea`, `runs/` tree `5a0ab766…`. `history` (1,046 at `53dbc6c5`, licence policy `reference`) is out of scope (README §1) |
| Wave / mode | wave 5. **Full checks.** `drift` was not examined in FA or E2 and has no stored corpus, so there is no E2 delta. The baseline is the phase-10l mapper trial |
| Code | `065b0d36` or later on `precheck-corpora` (the examiner records the exact commit) |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Nothing here was computed from the raw data in this step. Every number comes from a cited earlier report, the profile, the registry, GitHub metadata or the paper. Rates are arithmetic on those counts |
| Desk research | [`../data/drift/research.json`](../data/drift/research.json) (sources, versions, issues, licence, all reported values with URLs) |

Sources: profile `src/agentprov/adapters/agentdojo/profiles/drift.profile.toml` (P); registry `adapters/registry/__init__.py` and
`tools/readme_corpora.toml` (REG); phase-10l census, trials and AER mapping (`docs/reports/phase10l/`: 10L-C, 10L-T, 10L-M);
investigation `AgentPROV/investigation/sources/drift.md` (INV) and `verify/drift.md` (VER); DECISIONS D-270..D-279 (DEC);
`regen-batch.md` (RB); paper arXiv:2506.12104 v1-v3 (PAP); AgentDyn issues #5, #6, #8 (AD#n).

## 1. Desk research in brief

- **The pin is still HEAD.** `main` = `6fd3df47` (2026-07-16, "Add MIT License"), with no push since. The `runs/` tree sha
  `5a0ab766` equals the profile pin. Per the GitHub tree API on 2026-10-14 (not truncated) the part has 1,569 `.json` blobs
  and 22,083,267 bytes. There are no tags, releases, Zenodo, Figshare or HF records. One issue is open (#1, HF outreach).
  A new fork with no own commits (`shenyimings/DRIFT`, 2026-10-12) is the only change since the investigation.
- **Run dates.** No log names its code. The stamps in tool outputs date the AgentDojo-suite runs to 2026-02-13, which
  falls between `763a7d65` and `336dca9e` (detector prompt) by VER's −06:00 reading. They date the AgentDyn-suite runs to
  2026-03-21/22, after `336dca9e`. These runs were committed at `7c7d9827` (2026-02-14) and `f9ef3a36` (2026-04-18).
- **Paper versions.** v1 2025-06-13, v2 2025-10-24 (the GPT-4o-mini DRIFT rows are unchanged from v1) and v3 2026-03-26.
  v3 changes the GPT-4o-mini DRIFT AgentDojo row from 47.91 / 1.29 to 50.93 / 1.35 and benign utility from 58.48 to 57.29.
  It also adds AgentDyn, but only as Figure 5 (no table; **corrected by fact-check:** the figure is an SVG whose bar labels
  give the DRIFT overall BU 18.3 / UA 20.3 / ASR 3.1, no per-suite values). The text says 629 injection tasks (v1), but every per-suite
  value is k/n on the v1.2 grid of 949, which is the logs' grid.
- **AgentDyn-suite numbers.** These come from the maintainer's comment on AD#5 (2026-04-19), which names these logs as
  "original DRIFT code": shopping 10.00/12.22/1.67, github 30.00/32.78/0.56, dailylife 15.00/16.00/7.00 (BU/UA/ASR). The
  AgentDyn paper's DRIFT × GPT-4o-mini row is a different run set and is not a target.
- **Harness.** The harness is `agentdojo==0.1.35` (`requirements.txt`). The AgentDyn suites ran on an AgentDyn checkout
  whose commit is unknown, before its 2026-05-02 github IT1 checker fix (AD#6). Known 0.1.35 issue: `v1_1_2` is never
  imported, so workspace `user_task_13` runs in its pre-v1.1.2 form (agentdojo PR #146).
- **Licence.** MIT, "Copyright (c) 2026 Hao Li", added only at the pin (badge from `840c24db`). There is no data licence.
  Policy `include` for head.

## 2. Expected counts (part `head`)

| Measure | Expected | Source |
|---|---:|---|
| Files selected (= units = executions) | 1,569 | P `expected_files`; REG count 1569 (census); 10L-C §1; GitHub tree 2026-10-14 |
| Bytes | 22,083,267 | P `expected_bytes`; INV §2; GitHub tree |
| Other blobs at the pin, outside `include = runs/**/*.json` (ASB_DRIFT, docs, code) | 277 (1,846 − 1,569) | INV §1 (1,846 blobs at HEAD) |
| Cells: banking / slack / travel / workspace (attacked only) | 144 / 105 / 140 / 560 | INV §3.2; GitHub tree |
| Cells: dailylife / github / shopping attacked + benign | 200+20 / 180+20 / 180+20 | same |
| Attacked / benign | 1,509 / 60 | 10L-C §3 |
| Messages (user / assistant / tool) | 16,868 (2,402 / 8,291 / 6,175) | 10L-C §3; VER §3 |
| CALL ERROR `user` messages (files; trajectory / checklist) | 833 (538; 326 / 507) | P quirk; 10L-C §3 |
| Assistant re-serialised / raw | 7,341 / 950 | P quirk |
| Tool calls = tool messages; call batches | 6,175; 5,889 | 10L-C §3 |
| Tool errors (invalid tool / ValidationError / exception) | 579 (49 / 114 / 416) | 10L-C §3 |
| Final turns with call text and empty `tool_calls` (re-serialised / raw) | 317 (311 / 6) | P quirk; VER §4 |
| Runs without any tool call (all 2-message files) | 20 | 10L-C §4; VER §4 |
| `initial_checklist` raw / `None`; plan semantics `initial_plan` | 1,512 / 57; 1,569 (contradicted 0) | 10L-C §4; P quirk |
| Call ids distinct / in more than one file (max files) | 3,265 / 975 (9) | P quirk; VER §3 |
| Runs with run-time stamps in tool outputs | 371 | 10L-C §5; VER §3 |
| `total_tokens` sum; `duration` sum | 64,972,778; 79,823 s | VER §3 |
| AER (10L mapper trial): valid; decisions (isolation + CALL ERROR); tool executions; model calls | 1,569; 6,722 (5,889 + 833); 6,175; 8,291 | 10L-T |
| Seal issues (10L-T) | `accounting_unverifiable` 1,569; `drift.agent_prompt_not_recorded` 1,569; `drift.injection_map_not_recorded` 1,509; `drift.calls_in_text_not_executed` 317 | 10L-T |
| L2 sample | 50 (10 strata × 5) | README §4 rule; `l1_families` arm key (`suite`, `attack_dir`) |

## 3. Expected arms

A single model (`gpt-4o-mini-2024-07-18` = directory = `pipeline_name` in 1,569 of 1,569; provider OpenAI by prefix; served
model not recorded) and a single defence: DRIFT with all three modules, `adaptive_attack` false in every file. The facets
are therefore attack (`important_instructions` / benign `none`) and suite (7). The 10 non-empty cells are the L2 strata.

| Suite | Benchmark (P) | Attacked | Benign | Notes |
|---|---|---:|---:|---|
| banking | agentdojo v1.2 | 144 | 0 | |
| slack | agentdojo v1.2 | 105 | 0 | |
| travel | agentdojo v1.2 | 140 | 0 | |
| workspace | agentdojo v1.2 | 560 | 0 | 14 injection tasks (v1.2.1 changes absent: label `v1.2`) |
| dailylife | agentdyn | 200 | 20 | `v1.2` is a label only (D-278) |
| github | agentdyn | 180 | 20 | old IT1 checker (AD#6); 4 unwinnable user tasks (AD#8) |
| shopping | agentdyn | 180 | 20 | |

- **Expected missing cells** (against PAP v3): AgentDojo benign (97 runs, deleted at `7c7d9827`; held in the history part),
  GPT-4o, Claude-3.5-sonnet and Claude-3.5-haiku; ReAct baselines; ablations (Table 1); adaptive attacks (Table 2: manual,
  PAIR); other defences (Table 3, Figs. 3-5); open-ended tasks (Table 4); ASB (Table 5; the CSVs are under `ASB_DRIFT/logs`
  and not selected).
- **Expected extra cells:** none against the logs' own grid. The AgentDyn-suite cells have no paper table; the per-suite
  target is AD#5, and PAP v3 Figure 5 prints only the overall (18.3 / 20.3 / 3.1; corrected by fact-check).

## 4. Expected outcome rates and the mapping

**Mapping.** `utility` is the user task's checker result. `security = true` means the injection task succeeded (ASR); it is
the constant `true` on benign runs (`drift.benign_security_constant@1`). Per suite:
- UA = share of `important_instructions` files with `utility = true`;
- ASR = share with `security = true`;
- BU = share of `none/none` files with `utility = true`.

The paper's **overall is the unweighted mean of the suite rates**: (40.97+49.52+53.57+59.64)/4 = 50.93, and
(4.86+0+0+0.54)/4 = 1.35. The pooled rate (e.g. INV's 517/949 = 54.48) is not the paper's metric.

| Cell | n | Paper (k) | Expected from prior counts (k) | Gap (pp) | Paper source |
|---|---:|---|---|---:|---|
| banking UA / ASR | 144 | 40.97 (59) / 4.86 (7) | 40.97 (59) / 4.86 (7) | 0 / 0 | PAP v3 Tables 7, 8 (= Table 2 row 1) |
| slack UA / ASR | 105 | 49.52 (52) / 0.00 (0) | 52.38 (55) / 0.95 (1) | +2.86 / +0.95 | same |
| travel UA / ASR | 140 | 53.57 (75) / 0.00 (0) | 53.57 (75) / 0.00 (0) | 0 / 0 | same |
| workspace UA / ASR | 560 | 59.64 (334) / 0.54 (3) | 58.57 (328) / 1.61 (9) | −1.07 / +1.07 | same |
| AgentDojo overall UA / ASR (macro) | 949 | 50.93 / 1.35 | 51.37 / 1.86 | +0.44 / +0.51 | PAP v3 Tables 1, 2, 5, 7, 8 |
| AgentDojo BU | 0 at head | 57.29 (v3 Table 6) | n/a | n/a | not testable (no benign AgentDojo runs) |
| shopping BU / UA / ASR | 20 / 180 / 180 | 10.00 / 12.22 / 1.67 | 2 / 22 / 3 | 0 | AD#5 maintainer comment |
| github BU / UA / ASR | 20 / 180 / 180 | 30.00 / 32.78 / 0.56 | 6 / 59 / 1 | 0 | AD#5 |
| dailylife BU / UA / ASR | 20 / 200 / 200 | 15.00 / 16.00 / 7.00 | 3 / 32 / 14 | 0 | AD#5 |
| AgentDyn overall (macro) | 60 / 560 | 18.33 / 20.33 / 3.07 (PAP v3 Fig. 5 labels: 18.3 / 20.3 / 3.1) | same | 0 | arithmetic on AD#5; PAP v3 Figure 5 bar labels (corrected by fact-check) |

"Expected from prior counts" = INV §4.2, reproduced by VER §6. The superseded paper values (v1/v2: UA 40.97/47.62/42.86/60.18,
ASR 2.08/0.95/1.43/0.71) are reported for context only. **L2:** 5 units per stratum, so no arm reaches n = 20. Rates are
given with Wilson 95% intervals and carry no verdict. **L1-05b** (the whole-population recount of the raw outcome fields
under this mapping, as proposed for agentdyn) carries the comparison.

## 5. Known quirks (do not report as new)

| Id / source | What | Expected (head) |
|---|---|---|
| P `drift_tool_output_post_isolation` (D-274, BF-28) | one isolation decision on the last tool message of each batch; edits are invisible | 5,889 decisions / 6,175 tool messages |
| P `drift_assistant_reserialised` | template text, not the raw completion | 7,341 / 950 |
| P `drift_call_error_as_user` (D-273) | validator refusal logged as `user` | 833 messages, 538 files |
| P `drift_calls_in_text_not_executed` (D-277) | de-duplication, cap, parse failure; partial drops are unmarked | 317 final turns (+ ≤ 20 partial-drop turns, upper bound; VER: 6) |
| P `drift_no_system_no_injections` | no system message, no payload map | 0 / 0 |
| P `drift_plan_fields_by_commit` (D-276) | `initial_*` = initial plan at head | 1,569 / 0 contradicted |
| P `benign_security_constant` | benign `security` constant true | 60 files |
| P `args_mutated_in_place` | 0.1.35 `ToolsExecutor` | 1,549 files with a call |
| P `provider_call_id_anomalies` | seeded ids reused across logs | 975 of 3,265 ids; 0 in-file duplicates |
| 10L-C §5, VER §3 | run-time stamps in tool outputs are content, not AER time (D.6.8) | 371 runs |
| 10L-C §5 | isolation sees only `messages[-1]`; earlier results keep intact frames | 44 intact frames in non-last positions; 1,306 excised in last positions (census regex) |
| INV §5.2, D-275 | DRIFT's own LLM calls and the agent prompt are not logged; `total_tokens` covers all DRIFT calls | every file |
| INV §5.3 | no temperature sent (provider default) | code reading |
| D-272 | `verified_code = []`, `code_identity = range`: every harness rule is cited at class I | every AER |
| D-278 | `benchmark_version` `v1.2` is a label only for AgentDyn suites | 620 files |
| artefacts.toml | **no entry is scoped to `drift`**; the quirks above live only in the profile | report as a documentation gap (S3), not a corpus property |

## 6. Check map

| Check | Applies | Expected / why |
|---|---|---|
| L1-01 counts | yes | section 2; any difference from 1,569 files / 22,083,267 bytes / per-cell counts is a finding. 277 non-`runs/` blobs are outside `include` (a blobless clone may hold them absent; they are not selected) |
| L1-02 strict parse | yes | 0 failures; one 18-key set in one order; 0 extra keys; `benchmark_version` `v1.2`, flags T/T/T/F in all files (10L-C §2, VER §3) |
| L1-03 encodings | yes | no prior count. `json.dump` uses `ensure_ascii`, so non-ASCII is `\uXXXX`-escaped (INV §3.1); report C0/C1, bidi, zero-width, U+FFFD, escape residues per pointer. The CALL ERROR wrapper holds a Python `repr` with escaped text, a known literal-escape residue (833 messages) |
| L1-04 duplicates | yes | 0 byte-identical files within head (VER: 0 identical conversations head vs history). Cross-corpus within the population: 0 (agentdyn part c shares no bytes, 10L-C §1.1; agentdyn part d's 949 copies are out of scope and `owned_elsewhere` in agentdyn). Identical-trajectory groups: no prior count (report only) |
| L1-05 arm coverage | yes | 10 cells as in section 3; missing and extra as listed; L1-05b outcome recount (section 4) |
| L1-06 secrets, account paths | yes | 0 private-key headers at head (10L-C §5); 0 publisher account paths expected; counts and pointers only |
| L1-07 timestamps | presence only | 0 timestamp fields (no `evaluation_timestamp`). Content stamps: 371 runs. AgentDojo suites (workspace 144, travel 6) on 2026-02-13 02:03-19:10; AgentDyn suites (dailylife 92, github 69, shopping 60) 2026-03-21 01:05 to 03-22 00:12 (VER §3) |
| L1-08 degenerate | yes | 0 empty files; 20 two-message files without a call; every run ends with an assistant message; min/median/max messages 2/10/23 |
| L2 import, validate (all tiers), `recompute --dry-run` | yes | first product-path import of DRIFT head (10L was mapper-level). Registry `planned`: run via `l2_import.py`, labelled a trial if the CLI gate refuses |
| L2 determinism (second import, other `--jobs`) | yes | byte-identical (10L-T: identical AER-set digest with 10 and 3 workers) |
| L2 A2 error classes, A3 PROV issue classes | yes | 0 `adapter_defect`, 0 degenerate, 0 `drift.quirk_hook_not_applied`, 0 `drift.call_error_unrecognised`, 0 `drift.plan_semantics_contradicted` |
| L2 evidence classes | yes | 0 class-D citations (twins only); logged values O |
| L2 identity | yes | model `gpt-4o-mini-2024-07-18` from the directory; defence `drift` from the key set; 0 `identity_unresolved`, 0 `pipeline_name_mismatch` |
| L2 redaction | yes | no `redact` table; no account path in AER/SEM/PROV |
| L2 withholding / sealed chain | chain only | no `[withhold]` table and no secret strings: the withholding check does not apply; `verify --level chain` runs |
| L2 outcome sanity | report only | n = 5 per stratum (section 4) |
| E2 delta | no | not in FA/E2; see section 8 for the expected movement since the 10L trial |

## 7. Hypotheses (falsifiable)

| Id | Expectation | Refuted if | Level |
|---|---|---|---|
| H-01 | 1,569 files, 22,083,267 bytes, cells as in section 3 | any difference | L1-01/05 |
| H-02 | 1,569 parse strictly; one key set (18 keys) in one order; `pipeline_name` = directory in 1,569; `benchmark_version` `v1.2` and flags T/T/T/F in all | any exception | L1-02 |
| H-03 | outcome counts per cell exactly as in section 4 ("expected" column), benign `security = true` 60/60 | any count differs | L1-05b |
| H-04 | against PAP v3 per suite: banking and travel gap 0.00 pp on UA and ASR; slack and workspace gaps ≤ 3 pp; macro overall within 1 pp (UA +0.44, ASR +0.51) | any suite gap > 3 pp or overall > 1 pp | L1-05b |
| H-05 | per-suite AgentDyn BU/UA/ASR equal the AD#5 values within 0.01 pp | any > 0.01 pp | L1-05b |
| H-06 | github `user_task_5`, `7`, `8`, `11`: 0 `utility = true` in their 40 files (AD#8) | any `true` (then DRIFT's AgentDyn checkout differs from 5353cf76: documentation note) | L1-05b |
| H-07 | the single github `security = true` file is reported with its (user, injection) task. If it is `user_task_2` / `injection_task_1`, it holds no executed `git_delete_repo` call (AD#6 false positive) | it is u2/IT1 and holds such a call | L1 (call names) |
| H-08 | plan fields: checklist raw text 1,512, `None` 57, JSON 0; `drift.plan_semantics_contradicted` 0 | JSON checklist or any contradiction | L1-02/L2 |
| H-09 | content stamps only on 2026-02-13 for AgentDojo suites and 2026-03-21/22 for AgentDyn suites; none after the commits that added the files (2026-02-14 23:29 UTC; 2026-04-18 06:22 UTC), with ±14 h for the unknown zone | any stamp outside | L1-07 |
| H-10 | 0 secret-like strings with key/credential shape and 0 account paths | any | L1-06 |
| H-11 | 0 byte-identical pairs within head; 0 byte overlap with every in-scope part of the population | any (an overlap equal to agentdyn's 949 `src/…/drift/runs` files is expected-known if the xdup input includes them) | L1-04 |
| H-12 | L2: all 50 sampled executions valid in every tier; determinism byte-identical; seal-issue rates as 10L-T (`accounting_unverifiable` and `agent_prompt_not_recorded` 100%, `injection_map_not_recorded` = attacked share, `calls_in_text_not_executed` about 20%) | any validation error, nondeterminism, or a new issue code | L2 |
| H-13 | SEM under `agentdojo.suites@2`: in the 30 AgentDyn-suite sampled executions ≥ 90% of tool outputs carry an unknown-tool label (`agentdojo.unknown_tool@1`, integrity unknown). In the 20 AgentDojo-suite executions ≤ 5% do (only hallucinated names: 49 of 6,175 calls) | AgentDyn share < 50% (then @2 covers them) or AgentDojo share > 5% | L2 |
| H-14 | L2 decisions per execution = call batches + CALL ERROR messages (isolation on the last tool message of a batch only) | any execution where they differ | L2 |
| H-15 | 0 class-D rule citations in AER/PROV (D-272) | any | L2 |

Rule: no cell is excluded or proposed for exclusion because no attack succeeded (travel 0/140 and slack 1/105 are low; they
stay in).

## 8. Expected movement (no E2; baseline = phase-10l mapper trial, 2026-10-13)

The 10L-T AER-set digest `0a1f921a…` is **not** expected to reproduce. These changes came later and touch DRIFT AERs:

| Change | Expected in L2 |
|---|---|
| `d12b973b` U6-c (D-373) | every `model_call` has `unk /params not_recorded` |
| `446e9f13` BF-28 | isolation decisions on the last tool message of a batch by role. This is byte-neutral on well-formed batches (10L-C: 0 orphan tool messages), so the decision count stays 5,889 on the population |
| `9410c7d3` item 7 (D-378) | lone surrogates mapped with a disclosure: expect 0 at head (no prior count; L1-02 reports) |
| `b0087de8` D-31 bumps | header: profile `drift` v1, rules `aer` 1, `agentdojo` 2, `drift` 1; SEM `agentdojo.suites@2` |
| items 22/23 (RT-1, RT-3) | product-path dispatch to `DriftBuild` (not `unsupported_variant`); tool label read through `drift.isolation_pass` |
| unchanged | message, tool-execution, model-call and decision counts per execution; seal-issue codes and rates as in section 2 |

Any other difference between an L2 AER and the 10L-T mapping of the same file (by count per execution) is a finding.

## 9. Not in scope

The `history` part (1,046 runs, reference policy), agentdyn part `d` (the 949 copies; counted here), third-party copies
(drift-1, drift-clean, JinmingWang02), Figshare 32657856 and EnvironmentOptim DRIFT files (other sources), the `ASB_DRIFT` CSVs,
and the OpenReview supplementary zip (contents unknown).

## 10. Fact-check (2026-10-14, desk only; no raw data read)

An adversarial check re-opened the cited sources. Details and URLs: `fact_check` in
[`../data/drift/research.json`](../data/drift/research.json).

**Confirmed.**
- Pin and data record: `6fd3df47` is still HEAD of `main` (pushed 2026-07-16T06:24:21Z, 27 commits, 0 tags, 5 forks). The
  `runs/` tree `5a0ab766` is not truncated: 1,569 `.json` blobs, 22,083,267 bytes, and every per-cell count in sections 2-3
  (16×9, 21×5, 20×7, 40×14; 20×10+20, 20×9+20, 20×9+20). There are 1,846 blobs at the pin. Commits `53dbc6c5` (+1,046),
  `7c7d9827` (949 modified, 97 removed) and `f9ef3a36` (+620) are as stated. Zenodo has 0 hits and HF has none.
- Licence: `LICENSE` at the pin is MIT, "Copyright (c) 2026 Hao Li". Only `6fd3df47` touches it, and the badge comes from
  `840c24db`. `requirements.txt` pins `agentdojo==0.1.35` (PyPI upload 2025-10-27).
- Paper values: v3 Tables 7/8 (per suite), Table 2 ("w/o Adaptive Attack"), Table 1 (full DRIFT row), Table 5 and
  Table 6 (57.29) are as in section 4. The v1 Tables 2-4 and v2 Tables 6-8 superseded values are as stated. The text
  says 629 injection tasks in every version. All k/n, gaps and macro means in section 4 recompute exactly.
- Paper attribution: the DRIFT paper (arXiv:2506.12104, NeurIPS 2025) is the source of these logs. AD#5 (maintainer,
  2026-04-19) points to `runs/gpt-4o-mini-2024-07-18` with the per-suite AgentDyn values as stated. The AgentDyn paper's
  DRIFT × GPT-4o mini row (v1 28.33/22.05/2.72; v3 18.33/19.31/3.39) differs from them.
- Harness and bugs: agentdojo `v0.1.35` `load_suites.py` imports `v1_1`, `v1_1_1`, `v1_2`, `v1_2_1` and `v1_2_2` but not
  `v1_1_2`, and PR #146 is open. AD#6 was fixed on 2026-05-02 (`ae6513a8`..`2c99edcb`), after the 2026-03 runs, and the
  tool is `git_delete_repo`. AD#8 is open, tested at `5353cf76`, and names the four tasks.

**Corrected.**
- PAP v3 Figure 5 (AgentDyn) is not image-only. It is an SVG whose bar labels give the DRIFT overall:
  BU 18.3 / UA 20.3 / ASR 3.1. That equals the AD#5 macro (18.33 / 20.33 / 3.07) to one decimal, so the paper does print
  the AgentDyn overall, although not per suite. The bar-to-defence mapping was checked by decoding Figure 3 (AgentDojo)
  in the same way: it gives DRIFT 57.3 / 50.9 / 1.4, which matches Tables 6-8. Sections 1, 3 and 4 and research.json
  were amended. H-05 is unchanged. ASR 3.07 is the mean of the exact fractions; the mean of the rounded suite values
  is 3.08.

**Unverifiable.** The contents of the OpenReview supplement (bot challenge again; not bypassed). That the AgentDyn paper v3
row is agentdyn part a's rerun: only its inequality with AD#5 was checked. The census, VER and 10L-T message and quirk
counts were checked for consistency with the cited reports only, not recomputed, by the pre-registration rule.
