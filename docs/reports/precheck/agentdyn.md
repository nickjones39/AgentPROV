# Pre-check dossier: `agentdyn`

## 1. Header

| | |
|---|---|
| Corpus | `agentdyn` (MIT as declared, not legally settled) |
| Parts | `agentdyn · a` (v1.k14 + v1.k14.incomplete, 38,281), `agentdyn · b` (v0.k11, Progent with vendored AgentDojo 0.1.29, 5,184; registry `planned`), `agentdyn · c` (drift.k18.messages, 4,258; registry `partial`) |
| Family / profile | `agentdojo` / `agentdyn@2` (dialect `agentdojo.tracelogger`; rules aer 1, agentdojo 2, agentdyn 2, drift 1) |
| Pin | git `SaFo-Lab/AgentDyn` @ `5353cf76`, `runs/` tree `90d6d50d` (47,723 files, 598,326,615 B). Input: a local shallow checkout; `--pin-check` verified a 38,281/38,281, b 5,184/5,184, c 4,258/4,258 |
| Code commit | `c4ee3dd1` (batch `wave1`; every agentdyn step rc 0). `l2-c.json` records `260385bf`: a plan-only commit (`tools/precheck/plans/wave4*.toml`) landed while the part-c import ran; no `src/` or tool change against `c4ee3dd1`. Branch HEAD `8138e1e3` adds reports only |
| Kind | wave 1; part a is a delta since E2 (`../analysis/phase10-examination-2.md`), parts b and c are first examinations |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (L1, L2, verify, dossier) |
| Agents | researcher and fact-checker (prereg, research), examiner (L1/L2 analysis), one verifier per finding (13), dossier writer |
| Data | [`data/agentdyn/`](data/agentdyn/): `research.json`, `l1-a/b/c.json`, `l2-sample-a/b/c.json`, `l2-a/b/c.json`, `code-a/b/c.json`, `exam.json` (part b under `part_b_followup1`), `exam-b.json`, `exam-supplement.json`, `os1-population.json`, `os2-sample.json`, `h03-it1-checker.json`, `h12-pairs.json`, `dl1-a-aer/sem/prov.json`, `findings.json`, `exam-scripts/` |

- Code identity, part `a` (Level 2, [`code-a.json`](data/agentdyn/code-a.json)): commit `c4ee3dd1`; engine code aer `24df84b5e307`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `d3f9995f61bf`; adapter agentdojo.tracelogger c311b5a6ac9e.
- Code identity, part `b` (Level 2, first mapping, [`code-b.json`](data/agentdyn/code-b.json)): commit `d97d3a57` (batch `followup1`, 2026-10-16); engine code aer `856b7a09e0cf`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter agentdojo.tracelogger 03d8bc6d30df; profile agentdyn@2 `418fbcbd38a9`. The aer, validation and adapter digests differ from parts a and c (later `main`), so b is compared with the post-check by `code-b.json`, not with a/c.
- Code identity, part `c` (Level 2, [`code-c.json`](data/agentdyn/code-c.json)): commit `260385bf`; engine code aer `24df84b5e307`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `d3f9995f61bf`; adapter agentdojo.tracelogger c311b5a6ac9e.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Repository | https://github.com/SaFo-Lab/AgentDyn (pin `5353cf76` = HEAD of main on 2026-10-14; 26 commits, no tags or releases) | the data (`runs/`); MIT LICENSE with the AgentDojo authors' line only |
| Paper | https://arxiv.org/abs/2602.03117 (v1 2026-02-03, v2 2026-02-06, v3 2026-05-07) | outcome reference: v3 Tables 9-17 (BU/UA/ASR per model x defence and suite) |
| DRIFT | https://github.com/SaFo-Lab/DRIFT | producer of part c (original pipeline, January 2026, before `1af2672c`); LICENSE added 2026-07-16 |
| Harness | AgentDojo v0.1.35 fork (a); Progent vendored AgentDojo 0.1.29 (b); standalone DRIFT `pipeline_main.py` (c) | `agentdojo 0.1.35` name/version unchanged, so the version does not identify the code; January runs predate the repository |
| Data record | none (no Zenodo/Figshare/HF execution record); HF `agentdyn-dataset/agentdyn` holds task definitions only, no licence | not used |
| Issues | [#2-#4](https://github.com/SaFo-Lab/AgentDyn/issues/2) temperature 0.0 dropped (fixed 2026-03-04); [#5](https://github.com/SaFo-Lab/AgentDyn/issues/5) DRIFT variant; [#6](https://github.com/SaFo-Lab/AgentDyn/issues/6) GitHub IT1 false positive (checker fixed 2026-05-02, logs not rescored); [#7](https://github.com/SaFo-Lab/AgentDyn/issues/7) Gemini-2.5-Pro UA 56.95 vs logs 47.43 (open); [#8](https://github.com/SaFo-Lab/AgentDyn/issues/8) github user_task_5/7/8/11 unwinnable (open; PR #9 unmerged) | known defects |

Data-versus-paper notes (from `research.json`):

- v1 to v3: the only changed shared cell is GPT-4o mini x DRIFT (v1 28.33/22.05/2.72 to v3 18.33/19.31/3.39), matching the 2026-04-19 integrated rerun. v3 adds Claude, Qwen3-Coder and Kimi rows with no logs at the pin (H-14: 0 files).
- The Gemini None rows: the OpenRouter directories at the pin were added in `73ee3416` (after v1); the Google-API copies were removed in `2d4ad05a`. The paper rows plausibly come from the removed runs (history part, out of scope).
- The OpenAI-compatible client of the January code drops temperature 0.0; the Google client sends it (H-12).
- Part c comes from the original DRIFT code, as the maintainer states in issue #5; the paper DRIFT row is the integrated rerun in part a.
- Paper overall rates are the unweighted mean of the three suite rates; the recount (L1-05b) uses the same convention.
- Paper cells absent from the logs: CaMeL for 7 of 8 models; gpt-5-mini tool_filter (6 aborted files); 82 gpt-5.1-drift github attacked cells; the Table 8 attacks other than Important Instructions.

## 3. Expectations

Pre-registration: [`prereg/agentdyn.md`](prereg/agentdyn.md), committed in `fd75f8a3` (2026-10-14), before any check of this corpus ran, with a fact-check (section 10) that corrected the b/c other-variant counts and the CaMeL cells. Method amendments 1 to 3 (README section 8) apply. Amendment 1 covers the stored corpus's `validate.results.differ`. Amendment 3 gives part b a scratch-only first mapping (plan `followup1.toml`).

Hypotheses: H-02 to H-11, H-14, H-17, H-18 and H-24 supported. H-01 supported in part: file, byte, exclusion and attack-class counts equal the prereg, but the message, tool-call and tool-error totals were not emitted (follow-up, section 10). H-15 supported (partly tested) and H-16 supported (range only): the remainder is in the follow-up. H-12 refuted (PC-agentdyn-10). H-13 not tested, because the L1 flag does not measure it (PC-agentdyn-06, CC-08). Part b (first mapping, 2026-10-21): H-01/02/03/04/18 and the L2 check-map rows supported, H-15 in part, H-17 with qualification (PC-16); section 6b.

Classes follow the canonical rules R1-R6 and the cross-cutting items CC-01 to CC-08 of [`cross-cutting.md`](cross-cutting.md) (harmonisation pass 2026-10-15).

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Run at `c4ee3dd1`, `--input <local checkout> --pin-check`, jobs 2 (a 59 s, b 79 s, c 67 s).

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | walked 48,672; selected 47,723; a 38,281 (v1.k14 38,269 + incomplete 12), b 5,184, c 4,258; `select.owned_elsewhere:drift` 949; rejected 0. Other-variant a 9,442 / b 42,539 / c 43,465. Bytes a 479,526,175 / b 53,706,779 / c 65,093,661. Directories: a 62 (57 x 648 + camel 386 + gpt-5.1 939 + 12 + 6 + 2), b 8 x 648, c 6 x 620 + 538. Attack classes a 32,800 attacked / 5,190 benign (3,543 + pre-pass 1,647) / 291 direct; b 4,480 / 704 / 0; c 3,838 / 420 / 0 | as expected (fact-checked figures). Message, tool-call and tool-error totals not emitted: not tested (follow-up) |
| L1-02 parse | 0 strict failures in a, b and c | as expected |
| L1-03 encodings | a: C0 in 4 artefacts (8 occurrences, each under tool_call and tool_calls), CR 2 artefacts (3 strings), VS 5; escaped newline 9,197, escaped unicode 3,635, JSON-in-string 213, escaped quote 47 artefacts (new baseline). b: C0 1, zero-width 1, VS 1. c: VS 1, JSON-in-string 3,400 (DRIFT plan fields). 0 bidi, tag, U+2028/2029/0085, U+FFFD, mojibake | as expected. E2's 12 C0/C1 strings were AER strings (other layer) |
| L1-04 duplicates | byte-identical 0 within, across parts and across corpora. Trajectory-identical within part: a 889 groups / 4,940 units, b 97 / 299, c 61 / 274; across a/b/c 0; across corpora 7 groups with ROPE head (9 a units, PC-11). Google-API gemini-flash detector pairs 425 / 357 / 275 of 648 (= E2 S01). llama-3.3 OpenRouter pairs 10.2-18.5 % (PC-10) | H-12 refuted (PC-10). The prereg's "about 390 identical-message groups" (INV/VER: identical `messages`, more than 3 messages, distinct runs) is another definition and is not comparable with the L1 fingerprint's 889 (CC-01, the same basis question as PC-rope-05, PC-adprov-v1-04, PC-ast-survey-agentdojo-09: both figures are reported, the difference is a tool definition); the rest as expected |
| L1-05 arms | no missing or extra cell beyond the prereg list. CaMeL: dailylife attacked 0/200, benign 8/20, pre-pass 0/10, shopping attacked 140/180. gpt-5-mini tool_filter 6 files; gpt-5.1-drift github attacked 98. Extras: direct 291 (shopping 180, github 111), travel strays 12 + 2, pre-pass a 1,647 / b 224 / c 0. 0 Claude, Kimi, Qwen3-Coder | as expected (H-14, H-24) |
| L1-05b OS-1 outcome recount | 225 paper values, 222 comparable: 201 within 0.05 pp (90.5 %), 21 off by > 0.05 pp, 11 off by > 5 pp; gap rule flags 5. Part b 24/24 and part c 21/21 within 0.05 pp | H-04 supported (threshold 90 %); the 11 values are PC-01 to PC-04 |
| L1-05b raw hypotheses | H-02: github user_task_5/7/8/11 utility=true a 0/590 each, b 0/80 each, c 0/70, 0/70, 0/70, 0/61. H-03: user_task_2 IT1 security=true without git_delete_repo a 16/16, b 1/1, c 4/4 (PC-05). H-10 CaMeL 0 utility=true (BU 0/46, UA 0/319). H-11 6 files [system, user] only. H-18 benign security=true a 5,180/5,180 (10 without outcomes), b 704/704, c 420/420 | as expected |
| L1-06 secrets/paths | account-path shapes in files: a 133, b 19, c 28 (unique files; 16 distinct names). 0 path tails with harness tokens, 0 operator_home, 0 local-path model ids, 0 withhold-rule matches; 7 names occur only in model tool arguments or echoing tool errors (PC-12, CC-03). Secret-like a 9,841 files; private-key blocks a 86 files / 237 strings, b 21 / 55, c 4 / 11, all benchmark fiction (PC-13, CC-02) | c = 4 as expected (H-17); a and b key counts are new (outside RT-10's scope) |
| L1-07 timestamps | a: `evaluation_timestamp` 38,281/38,281, naive, 0 parse failures, 2026-01-21 .. 2026-04-19; 28 non-monotone units, all tool-argument datetimes (content). b, c: 0 timestamp fields | H-16 range supported; day histogram not emitted (follow-up) |
| L1-08 degenerate | a: incomplete 12 (= prereg breakdown), error_present 5, 0 empty, zero-message or error-only. `null_final` a 114 / b 489 / c 36 uses a narrower definition, not comparable with silent_rerun 826 or E2 4,631 (PC-06, CC-08) | H-13 not tested; prereg counts of not-ending-in-assistant (16), no-call runs (b 879, c 677) and c [user, assistant]-only (564) not emitted (follow-up) |
| L1-09 | does not apply (git tree, not an archive) | n/a |

Duplicate group counts in this table are the per-part L1 summaries (`l1-a.json`, `l1-b.json`, `l1-c.json`), and this dossier uses them. `data/_cross/l1-xdup.json` counts a group under `within_part` only when all its members are in one part; groups that span parts move to `cross_part` (or `cross_corpus`), so its within-part figures can be lower (trajectory groups a 887 vs 889; b 97 and c 61 equal). A comparison with the post-check must use the same basis.

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`data/agentdyn/l2-sample-a.json`](data/agentdyn/l2-sample-a.json): 360 of 38,281 (360 strata `pipeline_dir x attack_dir x suite`, 1 each, `over_maximum`; 62/62 directories, 57 with 6 units, the others 8, 5, 3, 1, 1). [`data/agentdyn/l2-sample-c.json`](data/agentdyn/l2-sample-c.json): 210 of 4,258 (42 strata x 5; 7 directories x 30). The prereg set the stratum to the pipeline directory (a 62/300, c 7/35): deviation PC-07; the prereg governs, the sample is reused unchanged. Part b: no L2 in wave 1 (`l2_blocked`); first mapping run by `followup1.toml` (amendment 3), results in section 6b |
| Import | 2 scratch corpora per part (`l2-<part>-j2.partial`, `-j1.partial`). a 360/360 mapped, sealed_clean 333 / with_issues 27, degenerate 0, failed 0. c 210/210, 124 / 86, 0 / 0. Sample join 1:1 for every label |
| Validation | tiers aer, sem, prov, linkage: a 360/360 and c 210/210 passed, results reproduced, linkage 100 %. SHACL not implemented (skipped); regression n/a |
| Recompute | `--dry-run`: a 360 identical, c 210 identical, 0 unexplained |
| Verify chain | 0 failed; `checksums.absent` (working tree, expected) |
| Determinism | j2 vs j1: a 1,447 files, c 847 files, 0 differ, index identical |
| A2 error classes | examiner count (`l2_check` has no record-status table, PC-08). a: tool_execution ok 1,665 / error 116 / invalid 12 (7.1 %; population 7.2 %); model_call kept 2,012; run_error 0; decisions redact 221 / deny 2. c: ok 799 / error 60 / invalid 54; decisions other 846 + deny 185. Issue codes a: retry_passes_inferred 12, unexecuted_tool_call 18, incomplete_run 4, local_parse_drop 3, pipeline_name_mismatch 1, orphan_tool_result 8 (seal). c: drift.agent_prompt_not_recorded 210, injection_map_not_recorded 105 (attacked units), calls_in_text_not_executed 86, accounting_unverifiable 210. Completeness a unverifiable 356 / known_incomplete 4; c unverifiable 210 |
| A3 PROV issues | 0 PI hits. 21/21 unexecuted call parts represented as `apv:NotDispatched` (the 21 under `a3` in l2-a is a pass count, PC-08) |
| Evidence classes | 0 AER records with ev D in a and c. AER evf D 349 = code-independent `system_prompt_variant_digest`; SEM D 9 = `partial_payload@1` (item 6; stored corpus 2,820). PROV core:D = engine rules `n_gap`, `n_capture_profile`. inference:I 93,565, of which 90,072 cite an `_unverified` twin (unpinned January code). adapter_defect 0 |
| Identity | 0 unresolved, 0 mismatches; models, defences, attacks, suites follow the 76-row identity table (SecAlign `local` resolved by directory). Header rules: a {aer 1, agentdojo 2, agentdyn 2} 360/360; c adds drift 1, 210/210 (PC-09) |
| Redaction | 0 account paths in AER/SEM/PROV/index. Vacuous for account paths: 0/360 (a) and 0/210 (c) sampled labels carry an L1 account flag (PC-12, CC-03). 1 a execution carries a benchmark private-key header in AER (4 pointers) and PROV `apv:args` (PC-13, CC-02); c 0 |
| Withholding | policy null (no `[withhold]` table; RT-10 open), as pre-registered |
| OS-2 (raw vs mapped) | a 720/720, c 420/420 judgements agree |
| DL-1 (stored `agentdyn-a-p10.partial` vs scratch, 360 shared ids) | every difference attributed: header profile 1->2 and rules 1->2 (item 30); D->I `_unverified` twins (items 3, 13); +178 `load_environment` activities = 176 attacked + 2 direct (item 5); `/params` not_recorded on 2,012 model calls (U6-c); CaMeL planner input not recorded (19 calls) and feedback user->def0 (10 messages) (item 2); index suites@1->@3, 12 known_incomplete->unverifiable (items 9/11, D-372); SEM unknown_tool 291->8 (items 27b/30), marker changes 0 (item 8), partial_payload in 1 (item 6); PROV +5,556 inference bundles, g_* +178, a_exposure -1,071 and a_taint -3,397 (reviewed labels replace unknown roles). 0 unexplained pointers. Stored `validate.results.differ` is expected-known (amendment 1; PC-14, CC-05), not re-run |

### Recheck (CC-08, recheck12)

`plans/recheck12.toml` (l1, l1_10, check; sample frozen) against the d97d3a57 files; full deltas in [`_cross/recheck12.json`](data/_cross/recheck12.json). Every other L1/L2 count is unchanged; the only other deltas are run environment (code commit d97d3a57 with tools/src = 5efa3575, `tracked_changes` true, two H.8.4(2) recompute notices with 0 unexplained changes; R12-01).

| Part | L1-08 flags (old -> new) | L2 `_unverified` split | L1-10 |
|---|---|---|---|
| a | `null_final` 114 -> 4,478; `trailing_calls` - -> 1,683 | twin inference:I 90,072 -> 80,161; mixed 9,911; native 0 (sum 90,072 = old) | 0 screened (-); 0 hits; files with a hit 0; named accounts 0; operator 0; unreadable 0 |
| b | `trailing_calls` - -> 97 | new (absent at d97d3a57) | 0 screened (-); 0 hits; files with a hit 0; named accounts 0; operator 0; unreadable 0 |
| c | no change | twin inference:I 33,336 -> 28,321; mixed 5,015; native 0 (sum 33,336 = old) | 0 screened (-); 0 hits; files with a hit 0; named accounts 0; operator 0; unreadable 0 |

- PC-06: part a `null_final` 114 -> 4,478 (v1.k14 empty text blocks now counted); b 489 and c 36 unchanged (not v1.k14), as the CC-08 scope predicts. 4,478 is still 153 below E2's 4,631 empty finals; `trailing_calls` (a 1,683, b 97, c 0) holds the with-calls finals. The 153 gap is not reconciled (follow-up below).
- Part b `l2-b.json` has no d97d3a57 version (first check ran in followup1, same tool commit, clean tree); not a recheck delta.

## 6. Outcome comparison

L1 is the population recount (OS-1) of the raw utility/security fields; the reference is arXiv v3 Tables 9-17. Rate = unweighted mean of suite rates (paper convention); the Wilson 95 % interval is on the pooled k/n. Gap rule (README section 4): more than 15 pp, or more than 5 pp outside the Wilson interval. L2 arms have n < 20 and get no verdict. Full rows: `os1-population.json`, `os2-sample.json`.

| Arm | Level | n | Metric | Rate (Wilson 95 %) | Paper | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|---|
| a: gemini-2.5-flash none | L1 | 60 | BU | 5.00 [1.71, 13.70] | 30.00 | -25.00 | gap (PC-03) |
| a: gemini-2.5-flash none | L1 | 560 | UA | 7.61 [5.75, 10.18] | 24.29 | -16.68 | gap (PC-03) |
| a: gemini-2.5-flash none | L1 | 560 | ASR | 13.61 [11.47, 17.24] | 37.61 | -24.00 | gap (PC-03) |
| a: gemini-2.5-pro none | L1 | 60 | BU | 53.33 [40.89, 65.37] | 51.67 | +1.66 | match |
| a: gemini-2.5-pro none | L1 | 560 | UA | 47.43 [43.40, 51.64] | 56.95 | -9.52 | gap (PC-03, issue #7) |
| a: gemini-2.5-pro none | L1 | 560 | ASR | 21.43 [18.57, 25.39] | 20.61 | +0.82 | match |
| a: qwen3-235b none | L1 | 60 | BU | 6.67 [2.62, 15.93] | 23.33 | -16.66 | gap (PC-01) |
| a: qwen3-235b none | L1 | 560 | UA | 5.35 [4.08, 7.96] | 10.74 | -5.39 | within rule; > 5 pp (PC-01) |
| a: qwen3-235b none | L1 | 560 | ASR | 14.02 [11.96, 17.81] | 22.67 | -8.65 | within rule; > 5 pp (PC-01) |
| a: gpt-4o-mini PromptGuard2 | L1 | 60 | BU | 45.00 [33.09, 57.51] | 30.00 | +15.00 | within rule; github cells = PIGuard (PC-02) |
| a: gpt-4o-mini PromptGuard2 | L1 | 560 | UA | 19.44 [16.56, 23.14] | 13.70 | +5.74 | within rule (PC-02) |
| a: gpt-4o-mini PromptGuard2 | L1 | 560 | ASR | 33.91 [31.68, 39.59] | 28.54 | +5.37 | within rule (PC-02) |
| a: gpt-4o-mini repeat_user_prompt | L1 | 60 / 560 / 560 | BU / UA / ASR | 50.00 / 38.61 / 33.63 | 43.33 / 37.78 / 33.80 | +6.67 / +0.83 / -0.17 | within rule (PC-04) |
| a: gpt-4o-mini spotlighting | L1 | 60 / 560 | BU / UA | 36.67 / 35.44 | 38.33 / 35.78 | -1.66 / -0.34 | match (PC-04) |
| a: gpt-4o-mini tool_filter | L1 | 560 / 560 | UA / ASR | 5.30 / 5.65 | 4.80 / 6.15 | +0.50 / -0.50 | match (PC-04) |
| a: gpt-5-mini spotlighting | L1 | 60 | BU | 70.00 [57.49, 80.10] | 68.33 | +1.67 | match (PC-04) |
| a: gpt-4o repeat_user_prompt | L1 | 559 | UA | 56.25 [52.03, 60.23] | 56.13 | +0.12 | match (outcome-less file, PC-04) |
| a: gpt-5-mini tool_filter | L1 | 0 | BU/UA/ASR | n/a (6 aborted files) | 0.00 / 0.00 / 0.00 | n/a | no log support (expected) |
| a: gpt-4o-mini CaMeL | L1 | 319 (BU 46) | UA / ASR | 0.00 [0.00, 1.19] / 0.00 [0.00, 1.19] | 0.00 / 0.00 | 0.00 | match |
| a: gpt-4o-mini DRIFT (integrated) | L1 | 60 / 560 / 560 | BU / UA / ASR | 18.33 / 19.31 / 3.39 | 18.33 / 19.31 / 3.39 | 0.00 | match (v3) |
| c: gemini-2.5-pro DRIFT | L1 | 560 | UA (BU 36.67, ASR 1.09 also exact) | 33.04 [29.44, 37.22] | 33.04 | 0.00 | match |
| c: gpt-5.1 DRIFT | L1 | 478 | UA / ASR | 6.12 / 0.00 [0.00, 0.80] | 6.12 / 0.00 | 0.00 | match |
| all 75 paper rows (a 60, b 8, c 7) | L1 | 222 values | within 0.05 pp | 201/222 = 90.5 % | H-04 >= 90 % | n/a | supported |
| b: 8 Progent directories | L1 | 24 values | within 0.05 pp | 24/24 | v3 Tables 9-17 | 0 | match |
| c: 7 DRIFT directories | L1 | 21 values | within 0.05 pp | 21/21 | v3 Tables 9-17 | 0 | match |
| c: qwen3-235b DRIFT | L2 | 15 | BU | 53.33 [30.1, 75.2] | 36.67 (population = paper) | n/a | report only (n < 20) |
| c: gpt-4o DRIFT | L2 | 15 | UA | 40.00 [19.8, 64.3] | 27.09 (population = paper) | n/a | report only (n < 20) |
| a: all sampled arms pooled | L2 | 121 | BU | 25.62 | n/a | n/a | report only (n <= 3 per arm) |
| a / c: raw vs mapped judgements | L2 | 720 / 420 | agreement | 720/720 / 420/420 | n/a | 0 | match (mapping faithful) |

No gap comes from the mapping: OS-2 agrees on every sampled judgement, and the population recount reads raw fields. No arm is excluded or recommended for exclusion for its attack outcome.

## 6b. Part b (first mapping, followup1)

Batch `_batch/followup1` (2026-10-16, plan `tools/precheck/plans/followup1.toml`, `l2_import.py --allow-first-mapping`, amendment 3): l1 skipped (wave-1 rows reused), l1_10, sample, import_j2, import_j1, check; every step rc 0. Scratch only (`l2-b-j2.partial`, `l2-b-j1.partial`); no stored corpus touched. Registry status stays `planned`: this is a **trial**, not an import of record. Examiner script `exam-scripts/exam_b.py` → [`exam-b.json`](data/agentdyn/exam-b.json) (counts, truncated digests, normalised pointers). Code identity: section 1.

### Level 1 (part b; recheck12 rows at `d97d3a57`, after the CC-08 tool fix)

| Check | Result (denominator 5,184) | vs prereg |
|---|---|---|
| L1-01 | walked 48,672; scanned 5,184; 8 dirs x 648; pin-check 5,184/5,184; other-variant a 38,281 / c 4,258; owned_elsewhere 949 | H-01 counts supported |
| L1-02 | 5,184 ok, 0 strict failures | as expected |
| L1-03 | C0 1 artefact (2 strings, tool-call `body`), zero-width 1 (`collaborator_email` arg), VS 1; escaped newline 1,787, escaped unicode 646, JSON-in-string 28, escaped quote 9 artefacts; 0 bidi/tag/U+2028/U+FFFD/mojibake | new baseline (no prior count) |
| L1-04 | byte-identical 0; trajectory groups 97 / 299 units (4,982 distinct fp); `l1-xdup`: within 97, cross-part 0, cross-corpus 0 | as expected (CC-01 basis) |
| L1-05 | attacked 4,480 / benign 704 (user 480 + pre-pass 224); suites dailylife 1,840, github 1,672, shopping 1,672; model x progent x {II, none} x suite = 48 cells, 0 missing, 0 extra; 0 banking | as expected; prereg grid |
| L1-05b | 24/24 paper values reproduced exactly (re-derived in `exam-b.json`, gap 0.00 on every value) | H-04 (b share) supported |
| L1-06 | account shapes: home-dir generic 8, home-dir named 9, users-dir named 1, windows-users named 1 files (distinct named 4 + 1 + 1); secret-like: generic credential 1,601 files, private-key block 21 files / 55 strings | CC-03 / CC-02 (PC-12, PC-13) |
| L1-07 | 0 run timestamps; 369 files with content datetimes in tool args (naive, 0 parse failures; 14 non-monotone, content) | H-15 (no `evaluation_timestamp`) supported |
| L1-08 | 0 empty; `null_final` 489, `trailing_calls` 97 (post-CC-08 definitions); account_path named 11 / generic 8 files; secret_like 1,607 | 879 no-call figure not emitted (follow-up 2) |
| L1-09 | not emitted for agentdyn | n/a |
| L1-10 | 0 files screened (part b has no auxiliary or context files, `auxiliary_scanned` 0); operator hits 0 | vacuous |

### Level 2

| Item | Result |
|---|---|
| Sample | [`l2-sample-b.json`](data/agentdyn/l2-sample-b.json): 240 of 5,184, 48 strata `pipeline_dir x attack_dir x suite` x 5 (not over maximum). The prereg set 8 strata (pipeline dir, about 40 units): PC-07 applies to b as well; the sample is reused unchanged. The sample was drawn from the wave-1 L1 rows (`1d741bfe…`); recheck12 then rewrote the rows (`d9c8d767…`): 240/240 labels present with the same stratum and raw sha256 (flags only changed) |
| Import | j2 and j1: 240/240 mapped, sealed_clean 233 / with_issues 7, degenerate 0, failed 0, adapter_defect 0; join 1:1 |
| Validation | aer, sem, prov, linkage 240/240 passed, results reproduced 240, linkage 100 %; SHACL not implemented (skipped), regression n/a |
| Recompute `--dry-run` | 240 identical, 0 unexplained |
| Determinism | j2 vs j1: 967 files, 0 differ, index identical |
| Verify chain | 0 failed; `checksums.absent` (working tree, expected) |
| A2 | tool_execution ok 824 / error 60 / invalid 66 (13.3 % non-ok of 950); model_call kept 1,246; decisions deny 152; run_error 0. Seal codes: accounting_unverifiable 240, earlier_attempts_unobservable 240 (D_adapters LastPassOnlyLogging; part-a sample predates the code), unexecuted_tool_call 7, retry_passes_inferred 1. Completeness unverifiable 240 |
| Progent denials | 278 raw tool-error messages in the sample, 152 with the Progent/policy pattern; AER: 152 `decision deny` (`agentdyn.progent_denial_pattern@1`, actor `def0`), result messages authored by `def0`; the other 126 are tool_execution error 60 + invalid 66. 152 = 152: every denial is a decision, none is a tool failure |
| A3 | 0 PI hits; 7/7 unexecuted call parts represented (`apv:NotDispatched`); checked 144,417 statements |
| Evidence classes | 0 AER records with ev D (I: tool_execution 950, model_call 1,246, decision 152, actor 1,200, scope 240, activity 120). PROV core:D 1,080 = engine rules (as in a). `_unverified` split: twin 55,059 (inference:I 45,638, assessment:I 6,113, inference:none 3,308), mixed 5,821 (inference:I), native 0 |
| SEM | `agentdojo.unknown_tool@1` in 86/240 executions: 152 annotations in 85 executions are the fail-closed fallback for Progent-denial results (premise `<decision>/verdict`), 3 executions (1.3 %) are unlisted tool names (PC-15) |
| Identity | 0 unresolved, 0 mismatches, 0 `pipeline_name_mismatch` (prereg: b 0). Model from the bare `pipeline_name` = directory model for 240/240; defence `progent` 240/240; attack II 120 / none 120; suites 80 each |
| Redaction | operator hits 0. 1 execution carries a named home path that the model built from a benchmark scenario identity (assistant tool-call args and their echoes in tool errors; the bare name occurs 242 times in benchmark src, 48 of them in suite data yaml; not the local user, not an upstream author; verifier correction): AER 16 pointers, PROV 13 (`apv:args` 7, `apv:error` 6) (PC-16, CC-03). 1 execution carries a benchmark private-key header in AER message text (1 pointer), PROV 0 (PC-17, CC-02) |
| Withholding | policy null (no `[withhold]` table; RT-10 open), as pre-registered |
| OS-2 | raw vs mapped judgements 480/480 agree |
| CC-07 | #181 (banking precedence) and #161 (banking user_task_5): 0 of 5,184 units are banking, so 0 affected successes; not applicable. AgentDyn's own IT1 checker defect is PC-05 (b 2 in the population) |

### Outcomes vs the Progent rows of the paper (v3 Tables 9-17)

Population (L1, n 60 BU / 560 UA / 560 ASR per arm): all 24 values equal the paper (gap 0.00). Sample (L2, mapped AER, rate = mean of the 3 suite rates, Wilson 95 % on pooled k/n): no arm has n >= 20, so no verdict (amendment 2.2); every paper value lies inside the sample interval or less than 5 pp outside it (outside: gpt-4o UA 1.2 pp, gpt-5.1 UA 4.8 pp; verifier re-run).

| Arm (progent) | BU k/n (Wilson) | paper | UA k/n (Wilson) | paper | ASR k/n (Wilson) | paper | Verdict |
|---|---|---|---|---|---|---|---|
| gemini-2.5-flash | 0/9 [0.0, 29.9] | 1.67 | 1/15 [1.2, 29.8] | 2.04 | 1/15 [1.2, 29.8] | 2.24 | report only |
| gemini-2.5-pro | 3/14 [7.6, 47.6] | 25.00 | 4/15 [10.9, 52.0] | 16.06 | 1/15 [1.2, 29.8] | 1.59 | report only |
| gpt-4o | 2/12 [4.7, 44.8] | 6.67 | 3/15 [7.1, 45.2] | 5.83 (1.2 pp below) | 0/15 [0.0, 20.4] | 1.69 | report only |
| gpt-4o-mini | 0/10 [0.0, 27.8] | 6.67 | 2/15 [3.7, 37.9] | 3.83 | 2/15 [3.7, 37.9] | 10.33 | report only |
| gpt-5-mini | 2/13 [4.3, 42.2] | 23.33 | 3/15 [7.1, 45.2] | 17.63 | 0/15 [0.0, 20.4] | 0.00 | report only |
| gpt-5.1 | 2/9 [6.3, 54.7] | 15.00 | 6/15 [19.8, 64.3] | 14.98 (4.8 pp below) | 1/15 [1.2, 29.8] | 1.22 | report only (closest to the rule) |
| llama-3.3-70b | 0/11 [0.0, 25.9] | 3.33 | 1/15 [1.2, 29.8] | 2.28 | 0/15 [0.0, 20.4] | 0.52 | report only |
| qwen3-235b | 1/11 [1.6, 37.7] | 8.33 | 0/15 [0.0, 20.4] | 2.19 | 4/15 [10.9, 52.0] | 13.59 | report only |

The gpt-5.1 UA sample rate (40.0) is sampling variation: the population rate of the same arm is 14.98 = paper, and OS-2 shows the mapping returns the raw judgement for every sampled run (R6, not a finding). No arm is excluded or proposed for exclusion for its attack outcome (gpt-5-mini and llama-3.3 have 0 sampled successes and stay in).

### Hypotheses (part b share)

| Id | Verdict for b | Evidence |
|---|---|---|
| H-01 | supported (counts) | L1-01/05 above; message totals still follow-up 2 |
| H-02 | supported | github user_task_5/7/8/11 utility=true 0/80 each (section 4) |
| H-03 | supported | IT1 security=true without deletion 1/1 (PC-05) |
| H-04 | supported | b 24/24 |
| H-15 | supported in part | `pipeline_name` = bare model 5,184 (L1 `h_pipeline`); 0 `evaluation_timestamp`; system digest and package-version field not tested (follow-up 2) |
| H-17 | supported with qualification | 0 publisher or operator path; 1 sampled execution carries a model-invented named path into AER/PROV (PC-16) |
| H-18 | supported | benign security=true 704/704 |
| L2 rows of the check map (import, determinism, A2/A3, evidence, identity, redaction) | supported | 0 degenerate, 0 adapter_defect, every D rule via `_unverified` twin (native 0), 0 identity_unresolved, b `pipeline_name_mismatch` 0 |
| H-05..H-14, H-16, H-24 | not applicable to b | a/c arms only |

### New findings (part b)

| Id | Finding | Class | Sev | Verdict | Recommendation |
|---|---|---|---|---|---|
| PC-agentdyn-15 | `agentdojo.unknown_tool@1` is the fail-closed fallback for all 152 Progent-denial results (85/240 executions); unlisted tool names only 3/240 | documentation-mismatch (R4) | S3 | confirmed | Family owner: own rule id for defence-denial results or a spec sentence; split unknown-tool metrics by premise. No byte change before the round |
| PC-agentdyn-16 | [CC-03] 1/240 sampled executions carry a named home path built from a benchmark scenario identity into AER (16) and PROV (13); 0 operator | expected-known (CC-12c / CC-03) | S3 | confirmed (title corrected: the name is benchmark text) | Datasheet note with PC-12; D-182 decision by the family owner |
| PC-agentdyn-17 | [CC-02] 1/240 sampled executions carry a benchmark private-key header into AER text (1); PROV 0 | expected-known (CC-02) | S2 | confirmed | With PC-13: widen RT-10 to b, `[withhold]` or catalogue decision before release |

Analysis notes (R5, not findings): PC-07 (stratum key) and PC-08 (`l2_check` A2 table) extend to part b; the sample basis changed after the draw (recheck12) with 240/240 labels, strata and raw digests unchanged.

## 7. Findings

17 findings. The 13 examined findings for parts a/c were confirmed by their verifier (0 refuted); PC-14 is the numbered CC-05 finding added in the harmonisation pass. The part b findings PC-15/16/17 were confirmed by the part b adversarial verifier (0 refuted; PC-16's title corrected: the path's name is a benchmark scenario identity, not model-invented). Verifier corrections and the harmonisation entries are in `findings.json` (CC-06 format). Analysis-artefacts (R5: PC-06, PC-07, PC-08) are tool properties and are not counted in the readiness verdict. The `/params` not_recorded movement in DL-1 is U6-c at the AER level; the agentdyn prereg predicts no `apv:Gap`, so CC-04 does not apply here.

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-agentdyn-01 | Qwen3-235B undefended row (a) does not reproduce from the logs: BU 6.67 vs 23.33, UA 5.35 vs 10.74, ASR 14.02 vs 22.67; other 6 qwen3 arms exact; values unchanged since v1 | documentation-mismatch | S2 | confirmed | Datasheet disclosure beside the Gemini rows; artefact entry below; optional history-part check |
| PC-agentdyn-02 | Paper PromptGuard2 x GPT-4o mini github cells equal the PIGuard github cells (20.00/3.89/0.00); logs 65.00/21.11/16.11 | documentation-mismatch | S2 | confirmed | Disclose as a probable paper transcription error (in the PC-01 entry) |
| PC-agentdyn-03 | Gemini-2.5 Pro/Flash undefended rows differ as pre-registered (issue #7; H-05, H-06) | expected-known | S2 | confirmed, with correction | Keep D-27 c1 (flash only); propose a new datasheet-items row for gemini-2.5-pro citing issue #7 (user approval) |
| PC-agentdyn-04 | Small per-suite differences in gpt-4o-mini dailylife arms and single-file cells; the paper counts outcome-less files as failures | documentation-mismatch | S3 | confirmed | Disclose as minor; use the paper's convention when comparing |
| PC-agentdyn-05 | GitHub IT1 security=true without a deletion (pre-fix checker, issue #6): a 31 (29 transfers), b 2, c 4; completed deletion with security=false a 5 (plausible), b 0, c 0 | source-defect (R1: no `artefacts.toml` entry covers AgentDyn #6) | S2 | confirmed, with correction (62/4/1 -> 5/0/0) | Artefact entry below; datasheet note; keep logged values, no rescoring |
| PC-agentdyn-06 | [CC-08] L1-08 `null_final` misses null-with-calls and empty-text-block finals (47 = 45 + 2) | analysis-artefact (CC-08) | S3 | confirmed | Tool owner splits the flag after the freeze; run `exam_l1_extra.py` |
| PC-agentdyn-07 | Sample strata `pipeline_dir x attack_dir x suite`, not the pre-registered pipeline directory | analysis-artefact | S3 | confirmed, with correction | Recorded here; reuse the sample; align hook key and preregs |
| PC-agentdyn-08 | `l2_check` has no A2 record-status table; `a3` prints a pass count (l2-a only) | analysis-artefact | S3 | confirmed, scope refined | Tool owner, after the freeze |
| PC-agentdyn-09 | Prereg section 8 (item 30 row) expects `drift 1` in part-a headers; headers list catalogues used (spec C.3.1) | documentation-mismatch | S3 | confirmed | Note only; the product is correct |
| PC-agentdyn-10 | llama-3.3 OpenRouter defence arms share 10.2-18.5 % identical cells (H-12 refuted) | documentation-mismatch | S3 | confirmed, with correction (L2 count 7) | C5 identical-trajectory table; no dedup or exclusion |
| PC-agentdyn-11 | 7 trajectory-identical groups (9 a units) shared with ROPE head; 0 byte-identical | expected-known (examiner: documentation-mismatch) | S3 | confirmed, reclassified | Cross-corpus C5 table citing prereg/rope.md H-20 |
| PC-agentdyn-12 | [CC-03] Account-path shapes are benchmark or model content (a 133, b 19, c 28 files; 16 names; 0 operator hits); L2 redaction screen not exercised on them | expected-known (CC-03) | S3 | confirmed, counts corrected | Datasheet note on model-invented home paths; optional targeted scratch import |
| PC-agentdyn-13 | [CC-02] Private-key-shaped benchmark strings reach AER and PROV (1 a sample execution); no `[withhold]` table | expected-known (CC-02) | S2 | confirmed, scope widened | CC-02: the family owner widens RT-10 to every part with AgentDyn suites (here a 86 / b 21 / c 4 files; also rope head 79 logs, drift) and decides a `[withhold]` rule or catalogue entry before release; datasheet |
| PC-agentdyn-14 | [CC-05] Stored corpus `agentdyn-a-p10.partial` gives `validate.results.differ` (rows predate regen item 10's `pv.constraints.*` checks) | expected-known (CC-05) | S3 | added in the harmonisation pass; evidence is the amendment-1 proof, not re-run here | None before the round; compare like with like after re-validation (amendment 1) |
| PC-agentdyn-15 | Part b: `agentdojo.unknown_tool@1` is the fail-closed fallback for all 152 Progent-denial results (85/240 executions); unlisted tool names 3/240 (section 6b) | documentation-mismatch (R4) | S3 | confirmed | Family owner: denial-result rule id or spec sentence; split the metric by premise |
| PC-agentdyn-16 | [CC-03] Part b L2: 1/240 executions carry a named home path built from a benchmark scenario identity into AER (16 pointers) and PROV (13); 0 operator | expected-known (CC-12c / CC-03) | S3 | confirmed; title corrected (the name occurs in benchmark src, so not model-invented) | Datasheet note with PC-12; D-182 decision |
| PC-agentdyn-17 | [CC-02] Part b L2: 1/240 executions carry a benchmark private-key header into AER text (1 pointer); PROV 0 | expected-known (CC-02) | S2 | confirmed | With PC-13: RT-10 widened to b, `[withhold]` decision before release |

Verifier corrections (applied in `findings.json`):

- PC-01: only BU breaks the gap rule. UA and ASR are more than 5 pp off, but their Wilson intervals miss the paper value by less than 5 pp. The undefended files are smaller (median 3,659 B vs >= 5,039 B), consistent with a different run.
- PC-05: `h03_all.py` counted an error-free `git_delete_repo` message as a deletion. The tool returns status strings and deletes only after OTP verification. That is an analysis-artefact of the exam script; the security=true side stands.
- PC-07: the hook's stratum key was set after the prereg (`fd75f8a3` before `3f51be79`), so the prereg governs.
- PC-10: cause partly explained, since output-side defences are inert when no tool is called; llama pairs with spotlighting, tool_filter, progent or drift share 0 cells.
- PC-12: `acct_err2.py` scanned content and error fields only, not tool-call arguments (exam-script note).
- PC-13: RT-10's stated scope is the 4 part-c files; the a and b counts are new.

Refuted: none.

Proposed `artefacts.toml` entries (text only; route to the agentdojo family owner):

```toml
[[artefact]]
id = "agentdyn.art.paper_row_not_in_logs"
title = "Paper rows that the released runs/ logs do not reproduce"
description = "Recounting logged utility/security per pipeline directory (paper convention: unweighted mean of suite rates) does not give the v3 values for qwen3-235b none (6.67/5.35/14.02 vs 23.33/10.74/22.67), gemini-2.5-pro none (UA 47.43 vs 56.95, issue #7) and gemini-2.5-flash none (5.00/7.61/13.61 vs 30.00/24.29/37.61); the paper's gpt-4o-mini PromptGuard2 github cells equal the PIGuard github cells. The corpus records the logs."
scope = { sources = ["agentdyn"], parts = ["a"], profiles = ["agentdyn"] }
cause = "publication"
detector = { rule = "none (analysis recount, docs/reports/precheck/data/agentdyn/os1-population.json)", class = "O" }
claims = []
recorded_as = { notes = ["datasheet"] }
handling = { class = "DS" }
expected = [{ snapshot = "a", count = 4, unit = "directories", basis = "precheck OS-1 2026-10-15", status = "verified" }]
manuscript = true
refs = ["arXiv:2602.03117v3 Tables 9-17", "https://github.com/SaFo-Lab/AgentDyn/issues/7"]

[[artefact]]
id = "agentdyn.art.github_it1_checker_prefix"
title = "GitHub injection task 1 scored by the pre-fix checker"
description = "The released runs/ were scored before the IT1 checker fix of 2026-05-02 (issue #6, closed without rescoring). The pre-fix check tests whether the original repository path disappeared, so runs that transferred rather than deleted a repository (git_transfer_repo_ownership) are logged security=true. A few runs with a completed deletion (verify_github_account) of a target repository are logged security=false. Both are kept as logged."
scope = { sources = ["agentdyn"], parts = ["a", "b", "c"], profiles = ["agentdyn"] }
cause = "benchmark"
detector = { rule = "none yet (analysis: logged security vs a completed deletion reported by verify_github_account, not a git_delete_repo message without an error)", class = "O" }
claims = []
recorded_as = { notes = ["datasheet"] }
handling = { class = "DS" }
expected = [{ snapshot = "a", count = 31, unit = "executions", basis = "precheck 2026-10-15: security=true without git_delete_repo (29 transferred)", status = "verified" }, { snapshot = "a", count = 5, unit = "executions", basis = "precheck 2026-10-15: completed deletion of a REPO_LIST repo with security=false (target match not checked)", status = "plausible" }, { snapshot = "b", count = 2, unit = "executions", basis = "precheck 2026-10-15", status = "verified" }, { snapshot = "c", count = 4, unit = "executions", basis = "precheck 2026-10-15", status = "verified" }]
manuscript = true
refs = ["https://github.com/SaFo-Lab/AgentDyn/issues/6", "docs/reports/precheck/data/agentdyn/h03-it1-checker.json"]
```

Items for AGENTS.md section 12:

- PC-01/PC-02: the AgentDyn v3 rows qwen3-235b none and the gpt-4o-mini PromptGuard2 github cells do not reproduce from `runs/` at `5353cf76`. The corpus records the logs. `agentdyn.art.paper_row_not_in_logs` is pending with the family owner.
- PC-03: D-27 c1 covers only the gemini-2.5-flash undefended row. A datasheet item for gemini-2.5-pro (issue #7, UA 47.43 vs 56.95) is still to be proposed (user approval).
- PC-05: github IT1 attack success in the released logs is inflated by the pre-fix checker (a 31, b 2, c 4 transfers scored as success). `agentdyn.art.github_it1_checker_prefix` is pending. Logged values are kept.

## 8. Recommendations and readiness

1. Route the two artefact entries to the agentdojo family owner. Add datasheet notes for PC-01/02/03/04/05/12/13, and propose a datasheet-items row for gemini-2.5-pro (PC-03, user approval).
2. Widen RT-10 to every part with AgentDyn suites (a, b, c here; rope head and drift elsewhere), and decide the `[withhold]` rule or a catalogue entry for benchmark key material before release (PC-13, CC-02; one decision with PC-rope-07). It does not block the round.
3. Run plan `followup1.toml` (part b first mapping, scratch only) and `exam_l1_extra.py` (H-01 message counts, H-13, H-15 digest, H-16 histogram); append the results to this dossier.
4. Tools, after the batch freeze: split `null_final` (CC-08), add an A2 record-status table to `l2_check`, and align the stratum key with the preregs (PC-06/07/08). The exam scripts `h03_all.py` and `acct_err2.py` carry the verifier notes. `exam.json` is the examiner's pre-verification output; its stale account-path and IT1 counts are annotated inline with the verifier-corrected figures (harmonisation pass, no recomputation).
5. Issue #8 (github user_task_5/7/8/11 unwinnable, H-02 supported in every part) has no artefact entry yet. It is an open question for the family owner, not a finding here.
6. No exclusion of any data: CaMeL, zero-success and outcome-less arms are kept.
7. Part b (section 6b): route PC-15 (denial-result SEM rule) to the AgentDojo family owner; PC-16/17 join PC-12/13. The followup1 mapping is a scratch trial; promoting b from `planned` is the AgentDyn owner's decision.

**Readiness: `ready-with-caveats`.**

- Parts a and c import correctly and deterministically:
  - validation 360/360 and 210/210
  - recompute 0 unexplained
  - j1/j2 byte-identical
  - DL-1 0 unexplained pointers
  - OS-2 raw = mapped (720/720, 420/420)
  - population outcomes reproduce the paper in 201/222 values, including all of b and c
- Caveats, all owned and routed:
  - part b first mapping (followup1, scratch trial; registry stays `planned`): 240/240 mapped and valid, recompute 0 unexplained, j1/j2 byte-identical (967 files), OS-2 480/480, 0 degenerate / adapter_defect / identity_unresolved, Progent denials 152 = 152 decisions; population 24/24 paper values. New caveats PC-15 (S3, SEM rule naming), PC-16 (CC-03, S3), PC-17 (CC-02, S2), all confirmed by the part b verifier; none blocks the round. Promoting b from `planned` to imported is the AgentDyn owner's decision
  - PC-01/02/03/05 S2 disclosures and the two artefact entries (family owner)
  - RT-10 widening and the `[withhold]` decision (PC-13, CC-02)
  - stored-corpus `validate.results.differ`, expected-known under amendment 1 (PC-14, CC-05)
- Not counted (R5, analysis-artefacts): PC-06 (CC-08), PC-07, PC-08.
- None of these means the data cannot be imported correctly.

## 9. Reproduction

Batch (wave 1; plan entries in `tools/precheck/plans/wave1.toml`):

```toml
[[part]]
corpus_id = "agentdyn"
source = "agentdyn"
part = "a"
l1 = ["--input", "~/Desktop/PhD/Labs/AgentPROV-upstream/agentdyn", "--pin-check"]

[[part]]
corpus_id = "agentdyn"
source = "agentdyn"
part = "b"
l1 = ["--input", "~/Desktop/PhD/Labs/AgentPROV-upstream/agentdyn", "--pin-check"]
l2_blocked = "first mapping of part b needs the AgentDyn owner's decision (l2_import --allow-first-mapping)"

[[part]]
corpus_id = "agentdyn"
source = "agentdyn"
part = "c"
l1 = ["--input", "~/Desktop/PhD/Labs/AgentPROV-upstream/agentdyn", "--pin-check"]
```

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave1 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave1.toml
```

Steps the batch ran per part P in {a, c} (L1 only for b). W = `~/.agentprov/migration-work/precheck/agentdyn`, D = `docs/reports/precheck/data/agentdyn`, IN = `~/Desktop/PhD/Labs/AgentPROV-upstream/agentdyn`:

```bash
uv run python tools/precheck/l1_scan.py --source agentdyn --part P --corpus-id agentdyn --jobs 2 --emit-fp --input IN --pin-check
uv run python tools/precheck/l2_sample.py select --units W/l1-units-P.jsonl --source agentdyn --part P --corpus-id agentdyn --out D/l2-sample-P.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-P.json --corpus W/l2-P-j2 --source agentdyn --part P --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-P.json --corpus W/l2-P-j1 --source agentdyn --part P --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-P-j2.partial --out D/l2-P.json --sample D/l2-sample-P.json --l1-units W/l1-units-P.jsonl --compare-with W/l2-P-j1.partial --jobs 2
# inside l2_check:
uv run agentprov validate --corpus W/l2-P-j2.partial --tiers aer,sem,prov,linkage,shacl,regression --jobs 2
uv run agentprov recompute --corpus W/l2-P-j2.partial --dry-run --jobs 2 -q
uv run agentprov verify --corpus W/l2-P-j2.partial --level chain
```

Examiner and verifier scripts (read-only):

```bash
python3 -I D/exam-scripts/os1.py <out>                                   # L1-05b OS-1, PC-01..04
uv run python -I D/exam-scripts/os2.py ...                                # OS-2 raw vs mapped
uv run python -I D/exam-scripts/h03_all.py <out>                          # H-03, PC-05 (see verifier note)
python3 -I D/exam-scripts/h12.py <out>                                    # H-12, PC-10
uv run python -I D/exam-scripts/nullfinal.py                              # PC-06
python3 -I D/exam-scripts/a2.py W/l2-a-j2.partial                         # A2, PC-08
python3 -I D/exam-scripts/aerstats.py W/l2-a-j2.partial                   # headers, PC-09 (and W/l2-c-j2.partial)
uv run python -I D/exam-scripts/acct_probe.py <out>; uv run python -I D/exam-scripts/acct_err2.py   # PC-12
uv run python -I D/exam-scripts/dl1.py / dl1_sem.py / dl1_prov.py ...      # DL-1 vs ~/.agentprov/corpora/agentdyn-a-p10.partial
```

Follow-ups for the orchestrator: section 10.

Process note: the session scratchpad was shared by parallel examiners. All agentdyn outputs were regenerated from `W/exam/`. Examiners who reused scratchpad `dl1.py` or `os2.py` after 09:22 should re-check their outputs.

Part b (followup1; W as above):

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-followup1 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/followup1.toml   # l1 reused, l1_10, sample, import j2/j1 (--allow-first-mapping), check
uv run python -I docs/reports/precheck/data/agentdyn/exam-scripts/exam_b.py W/exam/exam-b-full.json   # copied to D/exam-b.json
```

## 10. Open follow-ups

Not run in the harmonisation pass (they need a re-run, a tool fix or an owner's decision). W, D and IN as in section 9.

| # | What | Command | When |
|---|---|---|---|
| 1 | DONE 2026-10-16 (results section 6b). Part b first mapping, scratch only (amendment 3) | `uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-followup1 -- uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/followup1.toml` | when the queue admits it |
| 2 | H-01 message, tool-call and tool-error totals; H-13 and L1-08 last-message shapes (PC-06); H-15 b system digest; H-16 day histogram | `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-agentdyn-extra -- uv run python -I docs/reports/precheck/data/agentdyn/exam-scripts/exam_l1_extra.py --root ~/Desktop/PhD/Labs/AgentPROV-upstream/agentdyn --units-dir ~/.agentprov/migration-work/precheck/agentdyn --out docs/reports/precheck/data/agentdyn/l1-extra.json` | when the queue admits it |
| 3 | CC-08 / PC-06: re-run L1 for a, b and c after the `null_final` fix, only if the post-check needs the corrected L1-08 counts | `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-agentdyn-l1 -- uv run python tools/precheck/l1_scan.py --source agentdyn --part P --corpus-id agentdyn --jobs 2 --emit-fp --input IN --pin-check` for P in a, b, c | after the tool fix lands |
| 4 | Optional: check the Qwen3 none / Gemini none rows against the history part before the datasheet note (PC-01, PC-03) | no command (history part out of pre-check scope) | before the datasheet |
| 5 | CC-02 / PC-13: RT-10 widening and the `[withhold]` or catalogue decision | no command (AgentDojo family owner) | before release |
