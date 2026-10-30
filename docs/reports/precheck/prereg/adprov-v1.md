# Pre-registration: `adprov-v1`

| | |
|---|---|
| Corpus | `adprov-v1` (stored as `adprov-v1-release`; family `adprov`, profile `adprov-v1@2`, rules `aer 1 / adprov 2 / agentdojo 2`, SEM `agentdojo.suites@2`; E2 examined it at profile `@1`, SEM `suites@1`) |
| Parts | `release`: 17,664 `*.transcript.json` (transcript/v1), tree `corpus/corpus-prov` of `nickjones39/agentdojo-prov` @ `579a908354b9…`, read in place from `../AgentDojo-PROV-framework`, pinned by the J.1.4 listing digest `46273b01df12…` (the tree is gitignored at the commit) |
| Code commit | `065b0d36` (branch `precheck-corpora`) or later |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Wave 1, delta corpus (full import examined in E2, `docs/reports/analysis/phase10-examination-2.md` §7) |
| Desk research | `../data/adprov-v1/research.json` (all URLs there) |

Sources: **P** = profile `src/agentprov/adapters/adprov/profiles/adprov-v1.profile.toml`; **A** = `src/agentprov/adapters/adprov/artefacts.toml`;
**I** = `docs/reports/adprov/import-cli-release.json` (phase 6, `61b39d3`); **E2** = examination 2 and
`phase10-examination-2-data/reuse-summary-new-corpora.json` (corpus `adprov-v1-release-p10`, `afe7038`); **RB** =
`docs/reports/analysis/regen-batch.md`; **M** = the producer's manuscript `3. AgentDojo-PROV/paper/adprov_paper.tex` and
`macros.tex` (2026-10-10; V2 PDF 2026-08-30); **Z** = Zenodo record 23276620 (v2.3) and its `DATASHEET.md`,
`VALIDATION.json`, `PARTS.json`; **C** = `CHANGELOG.md` of the baseline at `579a908`; **G** = GitHub/PyPI APIs 2026-10-14.

## 1. Desk research summary

- **Paper:** the producer's own manuscript (Jones, Whaiduzzaman, Jan), unpublished, no arXiv id or DOI. Versions: V2
  (2026-08-30) reported rates over all traces; the current version (2026-10-10) excludes 168 "unscored" injection traces
  from every rate (Llama utility 36.2 → 36.3, DeepSeek 84.0 → 84.2, Qwen ASR 14.5 → 14.6). The data did not change
  (C: transcripts byte-identical since v2.0). Benchmark paper: AgentDojo, arXiv 2406.13352 v1–v3.
- **Data record:** Zenodo concept `10.5281/zenodo.20692312`: v1.0.0 (2026-06-14, DeepSeek + GPT-5-nano, 5,888 traces), v2.0,
  v2.1, v2.2 (2026-06-30; `corpus-prov.zip` 106,017,696 B), and **v2.3 (record 23276620, published 2026-10-10,
  `framework_commit` 579a908, 17,664 traces in `corpus-prov.part01–18.zip`, 35,346 entries)**. The profile, D-4 and J.7.2
  row 1 [corrected FC-1: was "J.1.2 row 1"] still say v2.3 is not deposited (DL-1). We did not download the payload.
- **Repository:** public, head = pin `579a908` (2026-10-06 UTC; the profile's 2026-10-07 is the baseline-tag date). The
  runs (2026-06-05..27) predate the first commit (2026-08-09). Tag `corpus-v2.3` → `a7002b4`, 26 commits before the pin
  (DL-2). No issues, no releases.
- **Harness:** `agentdojo==0.1.35` (tag `a75aba7`, 2025-10-27, latest), suites v1.2.2, no defence, temperature 0.0
  configured but never transmitted. Upstream issues that touch the data: #181 (banking IT0/1/3 success = any transfer to
  the attacker), #213 (workspace IT6–13 empty ground truth), #214 (non-ASCII tool output as `\uXXXX`), #161/#138 and #139
  (banking UT5, UT14 utility), #162 (workspace UT34), #189/#168/#218 (proposed calls scored; only 47 cut traces here).
- **Models:** deepseek-chat, gpt-5-nano (vendor APIs), google/gemini-2.5-flash, meta-llama/llama-3.3-70b-instruct,
  qwen/qwen-2.5-72b-instruct, z-ai/glm-4.6 (OpenRouter). Served model and route not recorded (A12).
- **Licence:** data CC-BY-4.0 (Zenodo metadata; repository LICENSE = MIT code + CC-BY note for `corpus/`); AgentDojo MIT
  for embedded benchmark text. Model-output terms unassessed (Llama 3.3 licence s.1.b.i names outputs; Qwen licence).

## 2. Expected counts (part `release`)

| Quantity | Expected | Source |
|---|---:|---|
| Selected `**/*.transcript.json` = units = executions | 17,664 (6 × 2,944) | P `expected_files`; I; README listing; M; Z |
| Listing digest | `46273b01df12d7636da355c07b9fea6d77c328dcd025e6340b183eac6dd8a1ed` | P; I (`verified 17,664`) |
| Not selected (outside the include glob) | 17,664 PROV-JSON graphs + 18 per-model files (`manifest.json`, `outcome_replay.json`, `checksums.sha256` × 6); total files 35,346 if the tree equals Z | baseline README at pin; Z `PARTS.json` |
| Excluded by the profile | `.DS_Store` / `._*` only (`select.not_execution_artefact`); expected 0 | P |
| Archive members | 0 | P (plain tree) |
| Variant / unit | `v1` 17,664 / `agent_execution` 17,664 | I; E2 |
| Status ok / ok_with_issues / failed / degenerate | 17,584 / 80 / 0 / 0 | I; E2 |
| Completeness verified / known_incomplete / unverifiable | 14,688 / 32 / 2,944 (all deepseek-chat) | I; E2 N6 |
| Seal issues (files) | `earlier_attempts_unobservable` 3,097; `accounting_unverifiable` 2,944; `unexecuted_tool_call` 47; `accounting_inconsistent` 32 (qwen 20, gemini 12); `adprov.tool_timing_overwritten` 1 (glm) | I; E2 |
| Messages system / user / assistant / tool | 17,664 / 17,664 / 64,897 / 64,781 | E2 |
| Tool calls / executed / unexecuted (traces) | 64,829 / 64,781 / 48 (47) | E2; M (64,781) |
| Model calls (AER) / paper model calls | 67,287 / 54,880 (5 models with usage) | E2; M |
| Traces with ≥1 tool call / none | 16,247 / 1,417 | E2; M (8.0 % no tool call) |
| Logged outcomes | utility true 10,500 / false 7,164; security true 1,289, false 15,793, null (benign) 582 | E2; Z DATASHEET (1,289) |
| Payload surfaced (attacked) | 14,048 of 17,082 (82.2 %); success without surfaced payload 0 | E2; M |
| Identical-trajectory groups / executions | 112 / 431; 0 with differing utility for the same user task | E2 |
| Byte-identical transcripts | 0 | E2 (`dup_source_sha` 0) |

## 3. Expected arms (L1-05) and outcome rates (L2)

Facets: model × attack × suite (defence `none` everywhere; benchmark v1.2.2; agentdojo 0.1.35). 96 cells, each model the
same grid (M Table tab:composition; Z DATASHEET; E2 facets):

| Suite | UT × IT | benign | direct | important_instructions | injecagent | per model | × 6 |
|---|---|---:|---:|---:|---:|---:|---:|
| workspace | 40 × 14 | 40 | 560 | 560 | 560 | 1,720 | 10,320 |
| banking | 16 × 9 | 16 | 144 | 144 | 144 | 448 | 2,688 |
| travel | 20 × 7 | 20 | 140 | 140 | 140 | 440 | 2,640 |
| slack | 21 × 5 | 21 | 105 | 105 | 105 | 336 | 2,016 |
| all | | 97 | 949 | 949 | 949 | 2,944 | 17,664 |

Expected missing cells 0, extra cells 0; every (UT, IT) pair once per model and attack. Re-attempted cells left no trace
(A `discarded_attempts_unrecorded`), so cell completeness says nothing about selection.

**Metric mapping.** Utility = `meta.utility` (AER judgement `utility`, checker). Attack success = `meta.security` true over
injection traces (benign `security` null → harness default, no claim). The paper excludes "unscored" traces: 162
unwinnable workspace IT0 cells (27 per model, all logged false) and 6 re-runs (gemini 2, llama 4; 5 logged true). So the
logged rate lies inside the paper's bounds column; compare the sample with the logged column and report the paper column.

| Model | Utility logged (E2) | Utility paper | Benign util. (n 97) | imp_instr util. | ASR logged (of 2,847) | ASR paper [Wilson] {bounds} |
|---|---:|---:|---:|---:|---:|---:|
| deepseek-chat | 84.0 % (2,474) | 84.2 % | 87.6 % | 78.4 % | 4.3 % (123) | 4.4 [3.7, 5.2] {4.3, 5.3} |
| gemini-2.5-flash | 39.0 % (1,149) | 39.0 % | 55.7 % | 29.2 % | 8.6 % (245–246) [FC-2] | 8.7 [7.7, 9.8] {8.6, 9.6} |
| gpt-5-nano | 73.5 % (2,165) | 73.5 % | 75.3 % | 68.9 % | 1.5 % (43) | 1.5 [1.1, 2.0] {1.5, 2.5} |
| llama-3.3-70b | 36.2 % (1,067) | 36.3 % | 40.2 % | 33.1 % | 8.8 % (250–251) [FC-2] | 8.8 [7.8, 9.9] {8.7, 9.8} |
| qwen-2.5-72b | 40.3 % (1,187) | 40.2 % | 50.5 % | 30.6 % | 14.5 % (413) | 14.6 [13.4, 16.0] {14.5, 15.5} |
| glm-4.6 | 83.5 % (2,458) | 83.6 % | 88.7 % | 75.8 % | 7.5 % (214) | 7.6 [6.7, 8.6] {7.5, 8.5} |
| all | 59.4 % (10,500) | — | 66.3 % (pooled) | — | 7.5 % (1,289 of 17,082) | {7.5, 8.5} |

Sources: M Table tab:outcomes (l. 2083) and `macros.tex`; E2 `utility_true_by_model`, `security_true_attacked`; V2 PDF §5.

**L2 sample.** Stratum = model × attack × suite (96). 5 per stratum gives 480 > 300, so the README rule scales to about
3 per stratum (≈ 300 units, ≈ 50 per model: ≈ 37 injection, ≈ 12 benign). Strata are not proportional to population
(workspace 560 vs slack 105 per attack), so per-model rates are compared **post-stratified** (weights N_h / n_h) and the
unweighted rate is reported beside them. Arms with ≥ 20 sampled: per-model utility (all) and per-model ASR, per-attack
ASR pooled over models; benign and per-condition utility per model (< 20) are Wilson-only, no verdict.

## 4. Known quirks (expected-known findings)

| Id / decision | Quirk | Expected |
|---|---|---|
| A `rerun_passes_lost` + `reported_calls_exceed` | silent re-runs: earlier passes lost | 121 lost-call + 32 inconsistent = 153 (M 153) |
| A `single_attempt_inferred` | attempt 0 from the call counter | 14,567 executions (now via `_unverified` twin) |
| A `usage_absent` (E2 N6) | deepseek-chat has no usage/model_config | 2,944 `unverifiable` |
| A `last_pass_only` | earlier passes not recorded | `earlier_attempts_unobservable` 3,097 |
| A `calls_pending_at_limit` | max_iters cut with calls pending | 47 traces, 48 calls |
| A `abnormal_finish` | finish reason outside stop/tool_calls | A/M say 184; E2 non-null 4 (error 3, length 1): DL-4 |
| A `text_tool_call` | calls written as text | A/M 470 (Llama 469); E2 detector 135: DL-5 |
| A `provider_call_ids`, `timing_overwritten_by_id` | repeated GLM call id | 1 trace |
| A `benign_security_normalised` | benign security null | 582 |
| A `temperature_not_transmitted`, `model_display_name`, `harness_side_effects`, `served_model_unrecorded`, `times_not_recorded`, `null_reply_as_empty`, `additional_user_turn`, `context_taint_used` | declared, every released trace | 17,664 (instrumentation I; NR/FO) |
| E2-b5 (not applied) | `artefact.unclassified.sentinel_time#unknown_lost` | 121 unclassified (DL-10) |
| E2 U04/U05/N5 | control chars from dropped high byte (2 values; 5 strings), mojibake 1, emoji VS 519 strings, zero-width 1 execution | as E2 |
| E2 N2/N8, U08 | literal `\n` in tool args (104 executions); strings holding lists 235, unparseable JSON args 20 | as E2 |
| E2 X | paired surrogate escapes in 1,007 raw objects (valid); lone 0 | as E2 |
| M tab:artefacts | unwinnable IT0 162; banking transfer without content 38 (#181); utility with no tool call 151 (banking UT10 52, UT9 42, UT8 28, UT5 27, UT6 2) | as M / E2 |
| D-4, D-86 addendum, D-24/D-27 c6, D-87, D-370, D-378, D-31, D-44 | see section 7 | |

## 5. Check map

| Check | Applies | Note / expected |
|---|---|---|
| L1-01 counts | yes | 17,664 selected, digest equal; non-selected graphs + 18 model files; 0 excluded expected |
| L1-02 strict parse | yes | 0 duplicate keys, NaN/Infinity, I-JSON overflow, lone surrogates, BOM, trailing data, invalid UTF-8, truncation |
| L1-03 encodings | yes | as section 4; literal `\uXXXX` residues in tool outputs are AgentDojo #214 (upstream), counted, not a defect |
| L1-04 duplicates | yes | 0 byte-identical; trajectory groups 112 / 431; no raw object or execution id shared with any other corpus part (E2 §7.3) |
| L1-05 arm coverage | yes | 96 cells as section 3; 0 missing, 0 extra; defence facet single-valued |
| L1-06 secrets / account paths | yes | 0 account paths (E2 U14); secret-like hits are benchmark fixtures (fictional passwords, IBANs, card numbers): counts and pointers only |
| L1-07 timestamps | yes | `meta.started_at`/`ended_at` in all 17,664; tool-turn start/end on 64,781 tool turns (one overwritten); range 2026-06-05..2026-06-28; per-model first start = M run date; `started_at ≤ ended_at`; no per-message times (format) |
| L1-08 degenerate | yes | 0 empty / 0 zero-message (min 3 messages); 1,417 tool-free traces (not degenerate); 47 cut at max_iters; 0 run errors |
| L2 selection | yes | ≈ 300 units, 96 strata (section 3) |
| L2 import | yes, **without** a listing pin check (DL-9, CD-8 held) | dev mode, queue `--class import --cpu 2` |
| L2 validate (all tiers) / recompute `--dry-run` / determinism (2nd import, other `--jobs`) | yes | 0 failures; 0 differences; byte-identical |
| L2 verify `--level chain` with withholding | **no** | the profile has no `[withhold]`/`[redact]`; nothing is withheld |
| L2 A2 error classes | yes | finish reasons, empty turns (E2: 1), text calls, argument type errors, tool errors (`te_status` error 6,043 / invalid 877 of 64,781) |
| L2 A3 PROV classes | yes | 0 dangling, 0 invented relations, 0 forbidden statements; unexecuted calls as `NotDispatched` |
| L2 evidence classes | yes | section 7 movement |
| L2 degenerate / adapter_defect | yes | 0 / 0 |
| L2 identity | yes | 6 models from `meta.model_id` (folders differ, DL-11); defence none; attacks 3 + benign; v1.2.2; 0.1.35 |
| L2 redaction | yes | 0 account paths in AER/SEM/PROV (no redact table needed) |
| L2 outcome sanity | yes | section 3 table; thresholds of README §4 |

## 6. Hypotheses (each falsifiable)

| Id | Expectation | Fails if |
|---|---|---|
| H1 | listing digest over the selected files = `46273b01…`, 17,664 files | any mismatch |
| H2 | 96 cells with exactly the section-3 counts; full UT × IT grids | any missing or extra cell |
| H3 | logged security true = 1,289 of 17,082; utility true = 10,500; per-model utility counts = E2 | any difference (L1 census of `meta` fields) |
| H4 | the 162 workspace IT0 traces in the 9 unwinnable user-task cells are all security false | ≥ 1 true |
| H5 | post-stratified sample ASR and utility per model within the README §4 thresholds of the logged column | gap > 15 pp (n ≥ 20) or interval excludes by > 5 pp |
| H6 | `usage.n_llm_calls` > assistant turns in exactly 153 traces (121 reconciled + 32 inconsistent: qwen 20, gemini 12); deepseek 0 checkable | ≠ 153 |
| H7 (DL-4) | traces with a finish reason outside {stop, tool_calls} incl. null/absent entries = 184; non-null abnormal = 4 | non-null ≠ 4 (E2 instrument) or total ≠ 184 (A/M basis) |
| H8 (DL-5) | the generic text-call detector flags ≤ 150 traces corpus-wide (A/M 470 has another basis) | > 150 |
| H9 (DL-3) | 0 of 17,664 carry `model_config.malformed_tool_calls`, `upstream_errors`, `discarded_usage`, `response`, `reasoning_effort`, `abnormal_finish`, or `meta.n_attempts`, `meta.capture`, top-level `discarded_attempts` | any present |
| H10 (DL-8) | `meta.model_config` absent in 2,944/2,944 deepseek traces; present with `temperature` 0.0 and `usage.n_llm_calls` in 14,720/14,720 others | any other split |
| H11 | every `started_at` in [2026-06-05, 2026-06-29); per-model earliest start date = M run date (DS 06-05, GPT 06-14, Gemini/Llama 06-26, Qwen/GLM 06-27); `|wall_clock_s − (ended − started)| ≤ 1 s` in ≥ 99 % | outside range or > 1 % off |
| H12 | 0 byte-identical files; trajectory groups 112 / 431 (± 0 at the same fingerprint) | other counts |
| H13 (DL-9) | an L2 import with a listing pin check and include paths registers 100 % `raw.origin.blob_mismatch`; without it 0 | other behaviour |
| H14 (DL-11) | folder ↔ `meta.model_id` is a bijection over 6 folders | any mixing |
| H15 | 0 account paths in raw transcripts and in L2 outputs | ≥ 1 |
| H16 | sampled surfaced-payload share (post-stratified) within ± 5 pp of 82.2 % | outside |

## 7. Expected movement since E2 (L2 scratch import at `065b0d36` vs the stored phase-10 corpus, same execution ids)

| Item (RB / decision) | Expected effect on the sampled executions |
|---|---|
| 30, D-31 | every AER header: `profile` `adprov-v1` 1 → 2 (digest), `rules` adprov/agentdojo 1 → 2; SEM `suites@1` → `@2`; all SEM/PROV digests change (`recompute` class `changed_explained`) |
| 3 + E2-c6 (D-24, D-27 c6, D-80/81) | 11 rules cited only through `_unverified` twins (class I): `adprov.assistant_turn_one_call` (100 % of executions), `call_id_unique_match`, `tool_turn_is_one_execution` (92.0 %, 16,247), `finish_reason_positional` (83.3 %, 14,720), `single_attempt_from_call_count` (82.5 %, 14,567), `lost_calls_from_count` (0.7 %, 121); `agentdojo.functions_runtime`, `messages_append_ordered`, `system_prompt_from_harness`, `user_is_simulated` (100 %), `tool_status_from_error` (92.0 %). **0 class-D citations of these rules** in the sample (R07b). Model invocations, message/part generation, model use/association, tool-result generation, request use and tool-runtime association move core D → inference I; passes and `apv:partOf` to inference. Core O records (messages, tool executions, judgements) unchanged |
| 1 + D-86 addendum (`a75aba7` verified for `transcript = released`) | outcome judgements and SEM outcome/marker rules stay class D: 0 SEM `_unverified` twin citations for `security_polarity`, `utility_meaning`, `injection_marker_yaml` |
| 14 (D-87) | `apv:afterCausal` of every tool execution (64,781 in 16,247 executions) moves to the inference bundle |
| 7 (D-378) | 0 replacements, 0 `adprov.lone_surrogate_replaced` issues; adprov catalogue digest only |
| 15, 8 (yaml_norm@2), 6 (partial_payload), 4 (account_confound) | catalogue attributes change; marker `present` share moves ≤ 2 pp from E2's 82.24 % (H16 uses 5 pp); 0 `account_confound` flags (E2: 0 successes without a payload); `partial_payload` count recorded, no expectation |
| 5 (D-370), U6-c (D-373) | none: gate D keeps adprov fixtures attribute-linked; adprov already declares `/params` |
| 9 (D-372), 3 | completeness shares unchanged: 83.15 % / 0.18 % / 16.67 %; the 121 lost-call executions stay `verified_complete` (a move to `unverifiable` would contradict RB item 3's prediction: report) |
| 10 (E2-b1) | validation rows change (new constraint checks); every sampled document passes |
| 16, 21, 22, 24, 29, 32 | code digests in `derivation.json` only |
| Not on main at `065b0d36` | regen items 33–41 (bug pass), 43–56 incl. CD-8 (core review D), 60–79 incl. CA-14..CA-17 adprov mapper/view fixes (core review A): **no effect expected**; a difference attributable to them is an analysis artefact |
| Status / issues | ok_with_issues share 0.45 % (80 / 17,664), same issue-code set as I; 0 new codes |


## 8. Fact-check (2026-10-14, adversarial, desk only; no raw data read, nothing computed from data)

**Checked and confirmed.**
- **Outcome table.** Every per-model value in section 3 was re-opened in M: `tables/tab_outcomes.tex` and the `macros.tex`
  macros behind it, including the bounds and unscored counts (29 / 31 / 27 × 4 = 168). Also confirmed: V2 PDF §5
  (36.2 %, 84.0 %, 14.5 % [13.3, 15.8]), `tab_artefacts.tex` (153, 162, 470, 47, 184, 151, 840, 372, 38, 20, 1,366;
  Llama 469 = `AdpArtUnexecLlamaN`), and the run dates and model ids in `tab_models` / macros.
- **Our expected counts.** I `import-cli-release.json`: status, completeness, the seal-issue codes and the listing pin.
  E2 `reuse-summary-new-corpora.json`: roles, tool calls 64,829 / 64,781 / 48, model calls 67,287, judgements
  10,500 / 7,164 / 1,289 / 15,793 / 582, `utility_true_by_model`, marker 14,048, text calls 90 + 44 + 1 = 135, abnormal
  finish 3 + 1, and `earlier_attempts_unobservable` 2,944 + 153 = 3,097. E2 §7 table: groups 112 / 431. Arithmetic
  checks: 10,500 / 17,664 = 59.4 %, 14,048 / 17,082 = 82.2 % and 386 / 582 = 66.3 %.
- **Zenodo** (API, 2026-10-14). Five versions under concept 20692312. Record 23276620 (v2.3) was published 2026-10-10:
  CC-BY-4.0, 59 files, 240,475,906 B; its 18 `corpus-prov` parts hold 35,346 entries and 88,152,754 B (`PARTS.json`).
  `VALIDATION.json` gives `framework_commit` 579a908, trace_count 17,664 and checksums_verified 35,334. The DATASHEET
  counts per condition and suite match section 3. The v2.2 md5 `5aac3036…` matches J.7.2 row 1, and v1.0.0 has
  5,888 traces and 166 successes.
- **GitHub.**
  - Pin `579a908` was committed 2026-10-06T02:04:48Z and is the head of `master`.
  - The local tag `agentprov-baseline-2026-10-07` was created 2026-10-07 (+1300).
  - Tag `corpus-v2.3` points to `a7002b4`, 26 commits behind the pin.
  - The first commit is `53439a4` (2026-08-09).
  - The repository has 0 issues and 0 releases.
  - The local baseline checkout has uncommitted README / CHANGELOG edits that name DOI 23276620.
  - CHANGELOG at the pin: transcripts byte-identical since v2.0 (l.12); item 7 under "2026-10-06 — seven fixes"
    (malformed arguments were previously fatal).
- **Licence.** LICENSE at the pin is MIT and carries a CC-BY-4.0 note for `corpus/`. The profile has `[licence]` CC-BY-4.0,
  `include` and no restrictions. Llama 3.3 licence s.1.b.i: confirmed. Qwen: licence "other/qwen". GLM-4.6: MIT (HF API).
- **Upstream harness.**
  - agentdojo v0.1.35 = `a75aba7` (2025-10-27) is the latest PyPI release (wheel sha256 `364bea421971…`).
  - `temperature or NOT_GIVEN` is present in `openai_llm.py`.
  - Issues #181, #213, #214, #161, #138, #139, #162, #189, #168 and #218 exist with the stated topics.
  - arXiv 2406.13352 v1 / v2 / v3 have the stated dates.
  - An arXiv search for AgentDojo-PROV returns 0 hits.
  - OpenAlex W4399912700 has the conflated title and DOI.
- **Decisions and docs.** D-4 and the profile note say v2.3 is not deposited; DL-1 stands.

**Corrected.**
- **FC-1.** The "J.1.2 row 1" citation is row 1 of the J.7.2 table (`J_migration.md` l.1289). J.1.2 does not mention
  the deposit.
- **FC-2.** Logged attack successes are Gemini 245–246 and Llama 250–251 (was 244–246 and 247–251). The 6 unscored
  re-runs are Gemini 2 and Llama 4 (29 and 31 unscored, minus 27 IT0 traces each). IT0 holds 0 successes, and
  1,289 − 1,284 = 5. Llama's logged rate is therefore 8.8 % (was 8.7–8.8 %). This is derived from M only, not from data.
- **FC-3.** The up-to-3 silent re-runs on an empty final reply are AgentDojo 0.1.35's own `run_task_with_pipeline`
  loop (`task_suite.py`), not the capture (research.json `harness`).
- **FC-4.** The workspace IT0 unwinnability is an upstream AgentDojo defect: the v1_1_2 fix is not loaded by 0.1.35
  (M l.2585–2589; DATASHEET). It was labelled a "paper-side" defect. Its expectations are unchanged.
- **FC-5.** The paper's completeness figures are 14,567 / 153 / 2,944. Section 2's 14,688 / 32 / 2,944 is our import's
  accounting basis (I), which is a different basis and not an error in section 2.
- **FC-6.** Zenodo v2.1 date: 2026-06-29.
- **FC-7.** `a7002b4` was committed 2026-09-29. The date 2026-09-30 is the annotated tag's.
- **FC-8.** The paper's ASR point estimates reproduce only over scored injection traces (2,816–2,820), although the
  caption names 2,847. The bounds use 2,847. This changes no expectation.

**Unverifiable here.**
- Equality of the deposited transcripts with listing digest `46273b01…` (needs the payload).
- The paper's utility denominators after its exclusions (not printed).
- "54,880 model calls = 5 models with usage" (the macro is confirmed; its basis is not stated next to it).
