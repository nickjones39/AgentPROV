# Pre-check dossier: `adprov-v1`

## 1. Header

| | |
|---|---|
| Corpus | `adprov-v1` (AgentDojo-PROV, the producer's own corpus; CC-BY-4.0 data, MIT code) |
| Parts | `adprov-v1 · release` (17,664 `*.transcript.json`). Out of scope: `converted-legacy` (compat oracle, owned by `agentdojo · 2024-06`) |
| Family / profile | `adprov` / `adprov-v1@2` (sha256 `e8f39d32...`), dialect `adprov.transcript_v1`, semantics `agentdojo.suites@2` |
| Pin | git `nickjones39/agentdojo-prov` @ `579a908` tree `corpus/corpus-prov` (gitignored at the commit), J.1.4 listing digest `46273b01df12...`, 17,664 files; L1 input = the local producer checkout |
| Code commit | `a871e2d7` (L1 and L2, batch `wave1`, every step rc 0) |
| Kind | wave 1, delta since E2 (stored corpus `adprov-v1-release-p10.partial`, profile @1) |
| Date | 2026-10-14 (prereg, research, L1), 2026-10-15 (L2 analysis, verify, dossier) |
| Agents | researcher and fact-checker (prereg, research), examiner (L1/L2 analysis), one verifier per finding (11), dossier writer |
| Data | [`data/adprov-v1/`](data/adprov-v1/): `research.json`, `l1-release.json`, `l2-sample-release.json`, `l2-release.json`, `exam.json`, `os1-population-release.json`, `os2-sample-release.json`, `delta-e2-release.json`, `findings.json`, `exam-scripts/` |

- Code identity, part `release` (Level 2, [`code-release.json`](data/adprov-v1/code-release.json)): commit `a871e2d7`; engine code aer `24df84b5e307`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `d3f9995f61bf`; adapter adprov.transcript_v1 0a2d1baf87b8.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Producer paper | AgentDojo-PROV (Jones, Whaiduzzaman, Jan), unpublished manuscript; no arXiv id or DOI (arXiv search 0 hits). Local tex/macros (current 2026-10-10), V2 PDF 2026-08-30 | source of every reported number; current version excludes unscored traces (V2 = logged rates) |
| Producer repository | https://github.com/nickjones39/agentdojo-prov @ `579a908` (branch head; 0 issues, 0 releases) | capture/replay code; runs (2026-06-05..27) predate the first commit `53439a4` (2026-08-09) |
| Data record | Zenodo concept [10.5281/zenodo.20692312](https://doi.org/10.5281/zenodo.20692312); v2.3 [record 23276620](https://zenodo.org/records/23276620) (2026-10-10, `corpus-prov.part01-18.zip`, 35,346 entries, VALIDATION trace_count 17,664) | published copy of the pinned tree |
| Benchmark | AgentDojo [arXiv:2406.13352](https://arxiv.org/abs/2406.13352); harness `agentdojo==0.1.35` (tag `a75aba7`), suites v1.2.2 | harness and scorer; reports no numbers for these six models |
| Attack origin | InjecAgent, [doi:10.18653/v1/2024.findings-acl.624](https://doi.org/10.18653/v1/2024.findings-acl.624) | `injecagent` template |
| Upstream issues | ethz-spylab/agentdojo [#181](https://github.com/ethz-spylab/agentdojo/issues/181), [#213](https://github.com/ethz-spylab/agentdojo/issues/213), [#214](https://github.com/ethz-spylab/agentdojo/issues/214), [#161](https://github.com/ethz-spylab/agentdojo/issues/161), #139, #162, #189/#168/#218, #201 | checker and harness properties present in the data |

Data-versus-paper notes (from `research.json`, fact-checked FC-1..FC-8):

- v2.3 **is** deposited on Zenodo; the profile note, D-4 and J.7.2 row 1 say it is not (DL-1). L1 supports equality in count (walked 35,346 = deposit entries) and the listing digest equals the pin; a byte comparison with the Zenodo parts was not run (needs the user's yes).
- Tag `corpus-v2.3` points at `a7002b4`, the deposit names `579a908`; 26 commits in between changed capture/replay/builder, transcripts claimed byte-identical (DL-2).
- Paper rates exclude 168 unscored injection traces (162 unwinnable workspace IT0 cells; 6 re-runs, 5 logged true); ASR point estimates use scored denominators although the caption names 2,847 (FC-8). Logged successes 1,289 = 1,284 scored + 5.
- Paper/artefacts counts with another basis: abnormal finish 184 vs E2 non-null 4 (DL-4), text tool calls 470 vs E2 detector 135 (DL-5).
- Model folders differ from `meta.model_id` (DL-11); served model and provider route not recorded; temperature 0.0 configured but not transmitted by 0.1.35.
- Upstream properties: #181 (banking transfer counted without content, 38), #214 (`\uXXXX` in tool outputs), workspace IT0 unwinnable (v1_1_2 fix not loaded by 0.1.35).

## 3. Expectations

Pre-registration: [`prereg/adprov-v1.md`](prereg/adprov-v1.md), committed in `fd75f8a3` (2026-10-14), before any check of this corpus ran. Method amendments 1 to 3 (README section 8) apply; amendment 1 covers the stored corpus's expected `validate.results.differ`.

| H | Result |
|---|---|
| H1 listing digest | supported (recomputed from 17,664 L1 sha256 rows = `46273b01df12...`) |
| H2 96 cells, full grids | supported (0 missing / 0 extra / 0 duplicate) |
| H3 logged outcomes | supported (security true 1,289 / 17,082; utility true 10,500; per-model = E2) |
| H4 162 unwinnable IT0 all false | supported (162/162 false) |
| H5 sample rates within rule | refuted as stated: 1 of 12 arms flagged (qwen ASR), sampling variance (PC-01) |
| H6 153 lost-pass traces | supported on the mapped basis only (stored index: 153 outside deepseek incl. 32 inconsistent); raw `n_llm_calls` census not run (follow-up) |
| H7 abnormal finish 184 / 4 | not tested (L1 hook does not extract finish reasons; sample abnormal 0) |
| H8 text-call detector ≤ 150 | not tested (no detector in L1 or `l2_check`; needs a new counts-only script, section 10) |
| H9 0 later-capture keys | not tested (meta census follow-up) |
| H10 deepseek no `model_config` | not tested at population; sample 48/48 deepseek unverifiable, 252/252 others cite `finish_reason_positional` |
| H11 dates | partially supported (all in 2026-06-05..27; per-model first date and wall-clock not checked) |
| H12 duplicates | byte-identical 0 supported; 112/431 refuted as stated: instrument differs (PC-04, CC-01) |
| H13 DL-9 | not tested (pin prepared over all candidates, PC-08) |
| H14 folder ↔ model bijection | supported (6 folders) |
| H15 0 account paths | refuted in raw (5 artefacts / 12 strings, fictional persona paths, PC-03, CC-03); supported in L2 (0 hits, labels not sampled) |

Classes follow the canonical rules R1-R6 and the cross-cutting items CC-01 to CC-08 of [`cross-cutting.md`](cross-cutting.md) (harmonisation pass 2026-10-15).
| H16 surfaced payload ±5 pp of 82.2 % | supported (81.72 %) |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Run at `a871e2d7`, local tree input, jobs 2, 17.0 s. All batch steps rc 0.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 35,346 walked (= Zenodo v2.3 entries) = 17,664 selected + 17,682 not selected (17,664 PROV graphs + 18 per-model files); 0 excluded, 0 rejected, 0 archive members; 8 `.DS_Store` skipped by the walk (PC-06). Units 17,664 = registry. Listing digest = pin | as expected (H1) |
| L1-02 parse | strict ok 17,664/17,664; 0 in every class | as expected |
| L1-03 encodings | artefacts / 17,664 (strings): `escaped_newline` 5,463 (10,058; 9,752 tool outputs, ~115 tool args = E2 N2/N8), `escaped_unicode` 1,508 (2,134; 2,107 tool outputs = #214), `escaped_quote` 936, `variation_selector` 460 (490), `json_in_string` 116 (142), CR 4, C0 1 + C1 1 (same artefact, E2 U04), mojibake 1, zero-width 1; 0 U+2028/2029/0085, bidi, tag, PUA, U+FFFD | as E2 (raw counts call args twice) |
| L1-04 duplicates | byte-identical 0; trajectory-identical 169 groups / 593 units (17,240 distinct): no call ids in the L1 fingerprint (PC-04, CC-01: both figures reported). In groups: utility differs 0, security differs 0 (non-null), user task mixed 0. Cross-part 0; cross-corpus 2 groups with `agentdojo-upstream` (3 tool-free qwen traces, PC-05) | instrument differs from prereg |
| L1-05 arms | 96 strata = 6 models × {benign, direct, II, injecagent} × 4 suites; per model benign 97 (40/16/20/21), each attack 949 (560/144/140/105); 0 missing, 0 extra, 0 duplicate; defence none; path facets = meta 17,664/17,664; folder ↔ model bijection | as expected (H2, H14) |
| L1-06 secrets/paths | 0 secret-like; 0 operator home; account-path shapes 5 artefacts / 12 strings, only model-written banking `read_file` `file_path` arguments (llama 2, deepseek 3), all persona names, 0 operator (PC-03, CC-03) | prereg 0 misread E2 U14 |
| L1-07 timestamps | `/meta/started_at`, `ended_at` 17,664/17,664, UTC offset, 0 parse failures, 2026-06-05..27; tool-turn start/end 64,781 each in 16,247 units; 27 non-monotone units: 26 scenario dates in tool arguments, 1 = the GLM timing-overwritten trace (PC-07) | 1 known execution-level unit |
| L1-08 degenerate | 0 empty, zero-message, error-only, unterminated, tiny; `run_error` false 17,664/17,664 | as expected |
| Outcomes | utility true 10,500 / false 7,164; security true 1,289 / false 15,793 / null 582 (= benign); `outcome_replay.json`: 162 unwinnable IT0 traces, 0 true; replay vs logged security differs on 6 (gemini 2, llama 4; 5 logged true) = paper's 6 unscored re-runs; utility differs on 9 | as expected (H3, H4) |

Duplicate group counts in this table are the per-part L1 summary (`l1-release.json`), and this dossier uses it. `data/_cross/l1-xdup.json` counts a group under `within_part` only when all its members are in one part; groups that span parts or corpora move to `cross_part` or `cross_corpus`, so its within-part figure is lower (trajectory groups 168 vs 169). A comparison with the post-check must use the same basis.

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`data/adprov-v1/l2-sample-release.json`](data/adprov-v1/l2-sample-release.json) (sha256 `5f0a6c2a...`): 300 of 17,664 units, 96 strata, 3 per stratum and 4 in 21 gemini strata (gemini 60, others 48); benign 76, direct 76, II 76, injecagent 72 |
| Import | `l2-release-j2.partial`, `-j1.partial`: 300 mapped, 0 failed, 0 degenerate, 17,364 filtered; sealed clean 298, with issues 2; listing pin prepared over all 17,664 candidates, verified 300/300 (DL-9 not exercised, PC-08) |
| Validation | tiers aer, sem, prov, linkage: 300 passed, 0 failed, 300 reproduced, linkage 100 %. SHACL and regression not implemented in this build (skipped) |
| Recompute | `--dry-run`: 300 identical, 0 changed, 0 unexplained |
| Verify chain | 300 raw re-hashed, 0 failed; `checksums.absent` on the unsealed tree (expected) |
| Determinism | j2 vs j1: 1,207/1,207 files and the index byte-identical |
| A2 error classes | model calls 1,130: finish `tool_calls` 645 / `stop` 250 / not_recorded 235 (deepseek 48 executions without `model_config` + 16 lost calls); abnormal 0; empty assistant turns 0; tool executions 1,177: ok 1,099 / error 67 / invalid 11; unexecuted calls 2 |
| A3 PROV issues | 128,166 statements: dangling, missing generation/use, forbidden, invented, time-inferred all 0; `NotDispatched` 2/2; 1,177 times on non-run nodes = observed tool-turn times (class O) |
| Evidence classes | PROV top O 39,940 / none 6,188; core D 4,368 / O 11,091 / none 1,179; inference I 42,125 / none 2,891; assessment D 1,424 / I 11,760 / O 600 / none 6,600. On `_unverified` twins: inference I 41,496, none 2,591, assessment I 600. AER: 0 class-D citations of the 11 twinned rules; 48 deepseek attempt scopes D (`adprov.turns_hold_last_pass`, code-cited). SEM: 0 twin citations; outcome 524 D, injection_marker 1,705 D (present 446 / absent 1,259), partial_payload 8 |
| Status / issues | ok 298 / ok_with_issues 2; `accounting_unverifiable` 48, `earlier_attempts_unobservable` 49, `unexecuted_tool_call` 2; no new code; completeness verified 252 / unverifiable 48 (all deepseek); 0 `adapter_defect` |
| Identity | 6 models 1:1 to AER model ids; defence none 300; attacks direct 76 / II 76 / injecagent 72 / none 76 (benign under `adprov.v1_benign_label@1`; the 76 tool "mismatches" are this naming, PC-11); suites 75 each; v1.2.2, 0.1.35 |
| Redaction | 908 files scanned, 0 hits; the 5 L1 account-path labels are not sampled (PC-03) |
| Withholding | not applicable (no `[withhold]`/`[redact]`, policy null) |
| Judgements | mapped = raw on 300/300 (utility) and 300/300 (security; benign null 76) |
| DL-1 (stored `-p10` vs j2, same 300 ids) | 0 unexplained (PC-10). Index: profile @1→@2 only. AER: D-31 bumps 300; ev/evf D→I (model_call 1,130, actor 600, scope 253, message `/after` 2,591, `/generated_by` 2,291, `responds_to` 1,177, tool_execution after/call/status 1,177); 16 base→`_unverified` swaps (item 3/E2-c6). SEM: `yaml_norm@2` on 1,705 markers, status unchanged (item 8); 8 partial_payload in 4 executions (item 6); ns +2 (items 6, 4). PROV: core D 20,170→4,368, inference I 20,478→42,125, core O unchanged; `afterCausal` 3,468 core→inference (item 14: 2,291 message entities + 1,177 tool executions, the latter on `apv:Assessment` entities). Validation: 4 `pv.constraints.*` (item 10; stored `validate.results.differ` is PC-09, CC-05), suites@2, 300/300 pass. Data: [`delta-e2-release.json`](data/adprov-v1/delta-e2-release.json) |

### Recheck (CC-08, recheck12)

`plans/recheck12.toml` (l1, l1_10, check; sample frozen) against the d97d3a57 files; full deltas in [`_cross/recheck12.json`](data/_cross/recheck12.json). Every other L1/L2 count is unchanged; the only other deltas are run environment (code commit d97d3a57 with tools/src = 5efa3575, `tracked_changes` true, two H.8.4(2) recompute notices with 0 unexplained changes; R12-01).

| Part | L1-08 flags (old -> new) | L2 `_unverified` split | L1-10 |
|---|---|---|---|
| release | no change | twin inference:I 41,496 -> 34,539; mixed 6,389; native 568 (sum 41,496 = old) | 0 screened (-); 0 hits; files with a hit 0; named accounts 0; operator 0; unreadable 0 |

- Only corpus here with native class-I refs in both mixed and native-only statements (native 568). L1 unchanged.

## 6. Outcome comparison

L1 = population (raw `meta` booleans, 17,664); L2 = AER of the 300-unit sample, post-stratified. Reference: paper macros (`tab:outcomes`; scored denominators). Gap rule: > 15 pp, or > 5 pp outside the Wilson 95 % interval; on the sample only arms with n ≥ 20. II = important_instructions.

| Arm (model / attack) | Level | n | Metric | Rate (Wilson 95 %) | Paper | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|---|
| deepseek-chat / all | L1 | 2,944 | utility | 84.04 % [82.67, 85.31] | 84.2 | -0.16 | match |
| deepseek-chat / attacked | L1 | 2,847 | ASR | 4.32 % [3.63, 5.13] | 4.4 | -0.08 | match |
| deepseek-chat / benign | L1 | 97 | utility | 87.63 % [79.61, 92.78] | 87.6 | +0.03 | match |
| deepseek-chat / II | L1 | 949 | utility (task-weighted) | 78.4 % (pooled 79.98) | 78.4 | 0.0 | match (PC-02) |
| gemini-2.5-flash / all | L1 | 2,944 | utility | 39.03 % [37.28, 40.80] | 39.0 | +0.03 | match |
| gemini-2.5-flash / attacked | L1 | 2,847 | ASR | 8.61 % [7.63, 9.69] | 8.7 | -0.09 | match |
| gemini-2.5-flash / benign | L1 | 97 | utility | 55.67 % [45.76, 65.15] | 55.7 | -0.03 | match |
| gemini-2.5-flash / II | L1 | 949 | utility (task-weighted) | 29.1 % (pooled 26.55) | 29.2 | -0.1 | match (PC-02) |
| gpt-5-nano / all | L1 | 2,944 | utility | 73.54 % [71.92, 75.10] | 73.5 | +0.04 | match |
| gpt-5-nano / attacked | L1 | 2,847 | ASR | 1.51 % [1.12, 2.03] | 1.5 | +0.01 | match |
| gpt-5-nano / benign | L1 | 97 | utility | 75.26 % [65.82, 82.77] | 75.3 | -0.04 | match |
| gpt-5-nano / II | L1 | 949 | utility (task-weighted) | 68.9 % (pooled 73.45) | 68.9 | 0.0 | match (PC-02) |
| llama-3.3-70b / all | L1 | 2,944 | utility | 36.24 % [34.53, 38.00] | 36.3 | -0.06 | match |
| llama-3.3-70b / attacked | L1 | 2,847 | ASR | 8.82 % [7.83, 9.91] | 8.8 | +0.02 | match |
| llama-3.3-70b / benign | L1 | 97 | utility | 40.21 % [31.00, 50.16] | 40.2 | +0.01 | match |
| llama-3.3-70b / II | L1 | 949 | utility (task-weighted) | 33.1 % (pooled 33.51) | 33.1 | 0.0 | match |
| qwen-2.5-72b / all | L1 | 2,944 | utility | 40.32 % [38.56, 42.10] | 40.2 | +0.12 | match |
| qwen-2.5-72b / attacked | L1 | 2,847 | ASR | 14.51 % [13.26, 15.85] | 14.6 | -0.09 | match |
| qwen-2.5-72b / benign | L1 | 97 | utility | 50.52 % [40.74, 60.25] | 50.5 | +0.02 | match |
| qwen-2.5-72b / II | L1 | 949 | utility (task-weighted) | 30.6 % (pooled 27.92) | 30.6 | 0.0 | match (PC-02) |
| glm-4.6 / all | L1 | 2,944 | utility | 83.49 % [82.11, 84.79] | 83.6 | -0.11 | match |
| glm-4.6 / attacked | L1 | 2,847 | ASR | 7.52 % [6.60, 8.54] | 7.6 | -0.08 | match |
| glm-4.6 / benign | L1 | 97 | utility | 88.66 % [80.83, 93.55] | 88.7 | -0.04 | match |
| glm-4.6 / II | L1 | 949 | utility (task-weighted) | 75.8 % (pooled 78.71) | 75.8 | 0.0 | match (PC-02) |
| all / direct | L1 | 5,694 | ASR | 3.23 % 184 [2.80, 3.72] | 3.3 (184) | -0.07 | match |
| all / II | L1 | 5,694 | ASR | 16.02 % 912 [15.09, 16.99] | 16.1 (907) | -0.08 | match (5 = logged-true unscored re-runs) |
| all / injecagent | L1 | 5,694 | ASR | 3.39 % 193 [2.95, 3.89] | 3.4 (193) | -0.01 | match |
| all / attacked | L1 | 17,082 | ASR | 7.55 % [7.16, 7.95] | 7.5 logged | +0.05 | match |
| all / all | L1 | 17,664 | utility | 59.44 % [58.72, 60.16] | 59.4 | +0.04 | match |
| deepseek-chat / all | L2 | 48 | utility | 89.58 % [77.83, 95.47]; post-str. 90.60 | 84.2 | +6.40 | within rule |
| deepseek-chat / attacked | L2 | 36 | ASR | 11.11 % [4.41, 25.31]; post-str. 5.37 | 4.4 | +0.97 | within rule |
| gemini-2.5-flash / all | L2 | 60 | utility | 31.67 % [21.31, 44.23]; post-str. 27.78 | 39.0 | -11.22 | within rule |
| gemini-2.5-flash / attacked | L2 | 44 | ASR | 4.55 % [1.26, 15.13]; post-str. 1.84 | 8.7 | -6.86 | within rule |
| gpt-5-nano / all | L2 | 48 | utility | 62.50 % [48.36, 74.78]; post-str. 72.18 | 73.5 | -1.32 | within rule |
| gpt-5-nano / attacked | L2 | 36 | ASR | 0.00 % [0.00, 9.64] | 1.5 | -1.50 | within rule |
| llama-3.3-70b / all | L2 | 48 | utility | 39.58 % [27.02, 53.69]; post-str. 42.66 | 36.3 | +6.36 | within rule |
| llama-3.3-70b / attacked | L2 | 36 | ASR | 8.33 % [2.87, 21.83]; post-str. 4.60 | 8.8 | -4.20 | within rule |
| qwen-2.5-72b / all | L2 | 48 | utility | 47.92 % [34.47, 61.67]; post-str. 31.94 | 40.2 | -8.26 | within rule |
| **qwen-2.5-72b / attacked** | L2 | 36 | ASR | 38.89 % [24.78, 55.14]; post-str. 29.60 | 14.6 | +15.00 | **flagged; sampling variance (PC-01)** |
| glm-4.6 / all | L2 | 48 | utility | 77.08 % [63.46, 86.69]; post-str. 87.78 | 83.6 | +4.18 | within rule |
| glm-4.6 / attacked | L2 | 36 | ASR | 16.67 % [7.87, 31.89]; post-str. 9.16 | 7.6 | +1.56 | within rule |
| all / direct | L2 | 76 | ASR | 7.89 % [3.67, 16.17]; post-str. 4.60 | pop. 3.23 | +1.37 | within rule |
| all / II | L2 | 76 | ASR | 22.37 % [14.46, 32.93]; post-str. 16.56 | pop. 16.02 | +0.54 | within rule |
| all / injecagent | L2 | 72 | ASR | 8.33 % [3.88, 17.01]; post-str. 4.12 | pop. 3.39 | +0.73 | within rule |
| all / attacked | L2 | 224 | payload surfaced | 81.72 % post-str. (186/224) | 82.24 (E2) | -0.52 | match (H16) |

Defence none in every arm. L1: 0 flags over 29 compared rows (max |gap| 0.16 pp). The exam's "paper not reported" for the three per-attack rows is corrected here from the paper macros (`AdpAsr{Direct,Important,Injecagent}Pct`). L2: 1 flag of 12 per-model arms, explained by the sample design (R6: post-stratified 29.60 % and population 14.51 % beside it; raw = AER 300/300; population = paper; P = 0.008 under the same allocation).

## 7. Findings

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-adprov-v1-01 | Qwen sample ASR flagged by the gap rule: sampling variance (R6 situation) | analysis-artefact | S3 | confirmed (1/1), weight corrected | Verdict from OS-1; post-check: stratified variance on post-stratified estimates |
| PC-adprov-v1-02 | Prereg compared pooled II utility with the paper's user-task-weighted column | documentation-mismatch | S3 | confirmed (1/1), source added | Compare like with like; fix research.json's `n` text |
| PC-adprov-v1-03 | [CC-03] 5 raw transcripts / 12 strings hold fictional persona account paths (model-written `read_file` args; E2 U14; 0 operator hits) | expected-known (CC-03) | S3 | confirmed (1/1) | Scenario fiction; no redaction; correct the prereg's reading of E2 |
| PC-adprov-v1-04 | [CC-01] L1 trajectory groups 169/593 vs E2 112/431: provider call ids are the whole difference | analysis-artefact (CC-01; was documentation-mismatch) | S3 | confirmed (1/1), equivalence shown | CC-01: state both bases in H12 |
| PC-adprov-v1-05 | 3 tool-free qwen traces converge with gpt-4o upstream runs | expected-known | S3 | confirmed (1/1) | List as convergent in C5; no exclusion |
| PC-adprov-v1-06 | 8 `.DS_Store` skipped by the ingest walk | expected-known | S3 | confirmed (1/1), mechanism corrected | None |
| PC-adprov-v1-07 | 27 non-monotone units: 26 scenario dates in tool args, 1 known GLM timing overwrite | expected-known | S3 | confirmed (1/1) | Report 1 execution-level unit; the 26 are an L1-07 scope limit |
| PC-adprov-v1-08 | L2 pin check prepared over all candidates, so DL-9 / H13 untested | documentation-mismatch | S3 | confirmed (1/1) | Record as a prereg deviation (stronger check); DL-9 only if needed |
| PC-adprov-v1-09 | [CC-05] Stored vs fresh validation rows: item-10 checks, SEM rename, AER mode release vs dev | expected-known (CC-05) | S3 | confirmed (1/1), mode added | Re-validate in the round, same AER mode |
| PC-adprov-v1-10 | DL-1 delta fully attributed, 0 unexplained | expected-known | S3 | confirmed (1/1), additions | Post-check expects these movements; item-14 prediction names message entities |
| PC-adprov-v1-11 | `l2_check`: benign↔none counted as identity mismatch; A3 pass classes show executions 0 | analysis-artefact | S3 | confirmed (1/1) | Tool owner after the batch |

Corrections applied (in `findings.json`):

- PC-01: stratum weight 560 of 2,847 (not 1,707); under equal allocation the expected unweighted qwen ASR is about 23 %, so the Wilson interval of the unweighted k/n is the wrong comparison.
- PC-02: producer `docs/stats.tex` ("Definitional trap") documents the cell weighting. The paper macro `AdpGemImportantUtilityPct` is 29.2 (checked by the dossier writer), so `research.json` is right; the 0.1 pp Gemini gap plausibly comes from the paper's exclusion of unscored re-runs (not verified).
- PC-04: "security differs 0" holds among non-null values (21 benign/attacked groups have benign null).
- PC-06: skipped by `agentprov.ingest.paths` discover, before profile selection.
- PC-07: the 26 argument-date units are a scope limit of the check, not a source artefact.
- PC-10: tool-execution `afterCausal` sits on `apv:Assessment` entities in the new inference bundle; one seal issue's rule ref moves to its `_unverified` twin; `delta-e2-release.json` omits the positional SEM sections that `delta.py` emits (noise from 4 executions).

Refuted (not findings): none.

11 findings, all confirmed by their verifier. `findings.json` is now in the CC-06 format (`agentprov-precheck-findings/0.1`, a `verdicts` list with lens, verdict, class, severity and reasoning; part, reproduction and hypothesis_ref filled from the examiner's records in `exam.json`). Analysis-artefacts (R5: PC-01, PC-04, PC-11) are tool properties and are not counted in the readiness verdict; PC-01 is the R6 situation (sample design), reported with the post-stratified and population rates in section 6. The adprov prereg declares `/params` and predicts no `apv:Gap`, so CC-04 does not apply.

Security: none. No secret value; the account-path shapes are persona fiction, 0 operator matches (PC-03, CC-03).

Proposed `artefacts.toml` entries: none. Every observation is covered by existing entries (`adprov.art.timing_overwritten_by_id`, `benign_security_normalised`, #214/#181 upstream notes) or is a tool/documentation matter.

Items for AGENTS.md section 12: none new. (The pooled-vs-weighted II utility basis, PC-02, is a manuscript/research.json note, already in the producer's docs.)

## 8. Recommendations and readiness

1. Correct the prereg/research basis notes: II utility is task-weighted (PC-02), the H12 basis includes provider call ids (PC-04, CC-01), E2 U14 attributes the persona paths to benchmark content (PC-03), the L2 pin check deviation (PC-08).
2. Item-14 prediction for adprov-v1: 3,468 `afterCausal` (2,291 message entities + 1,177 tool executions, on `apv:Assessment`), and the post-check counts them that way (PC-10).
3. Run the queued meta census (H6, H7, H9, H10, H11) and write a counts-only text-call detector script for H8 before the A/M counts (184, 470, 153) are relied on (section 10).
4. Tool fixes after the batches (PC-11); post-check sample rule on post-stratified estimates (PC-01).
5. Re-validate the stored corpus in the round, same AER mode (PC-09, CC-05, amendment 1). No exclusion of any data.

**Readiness: `ready-with-caveats`.**

- The part imports correctly and deterministically: 300/300 mapped, validation 300/300, recompute 0 unexplained, j1/j2 byte-identical, DL-1 0 unexplained, judgements = raw 300/300, redaction clean, L1 population = paper in 29/29 rows.
- Caveats (none blocking, all S3): hypotheses H6, H7 and H9-H11 rest on the queued meta census, and H8 on a text-call detector script that does not exist yet (section 10); H13/DL-9 untested (PC-08, CD-8 held on `review-core-d-regen`); stored `validate.results.differ` expected-known under amendment 1 until the round re-validates (PC-09, CC-05).
- Not counted (R5, analysis-artefacts): PC-01 (R6 sample design), PC-04 (CC-01), PC-11; no corpus effect.

## 9. Reproduction

Batch (wave 1; plan entry in `tools/precheck/plans/wave1.toml`):

```toml
[[part]]
corpus_id = "adprov-v1"
source = "adprov-v1"
part = "release"
l1 = ["--input", "~/Desktop/PhD/Labs/AgentDojo-PROV-framework/corpus/corpus-prov"]
```

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave1 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave1.toml
```

Steps the batch ran (W = `~/.agentprov/migration-work/precheck/adprov-v1`, D = `docs/reports/precheck/data/adprov-v1`, IN = the plan's `--input` tree):

```bash
uv run python tools/precheck/l1_scan.py --source adprov-v1 --part release --corpus-id adprov-v1 --jobs 2 --emit-fp --input IN
uv run python tools/precheck/l2_sample.py select --units W/l1-units-release.jsonl --source adprov-v1 --part release --corpus-id adprov-v1 --out D/l2-sample-release.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-release.json --corpus W/l2-release-j2 --source adprov-v1 --part release --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-release.json --corpus W/l2-release-j1 --source adprov-v1 --part release --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-release-j2.partial --out D/l2-release.json --sample D/l2-sample-release.json --l1-units W/l1-units-release.jsonl --compare-with W/l2-release-j1.partial --jobs 2
# inside l2_check:
uv run agentprov validate --corpus W/l2-release-j2.partial --tiers aer,sem,prov,linkage,shacl,regression --jobs 2
uv run agentprov recompute --corpus W/l2-release-j2.partial --dry-run --jobs 2 -q
uv run agentprov verify --corpus W/l2-release-j2.partial --level chain
```

Examiner scripts (read-only; S = `~/.agentprov/corpora/adprov-v1-release-p10.partial`):

```bash
python3 D/exam-scripts/os1.py W/l1-units-release.jsonl D/os1-population-release.json   # OS-1 population rates
python3 D/exam-scripts/os2.py W/l2-release-j2.partial W/l1-units-release.jsonl D/os2-sample-release.json   # OS-2, PC-01
uv run python tools/analysis2/exam2_p9diff.py --old S --new W/l2-release-j2.partial --out <out>/p9diff.json --jobs 2   # DL-1
python3 D/exam-scripts/delta.py S W/l2-release-j2.partial <out>                # DL-1 -> D/delta-e2-release.json, PC-10
```

Follow-ups for the orchestrator: section 10.

## 10. Open follow-ups

Not run in the harmonisation pass. W, D, S and IN as in section 9. Every batch step had rc 0; determinism, validation and recompute are clean, so none of these is a re-run of the batch.

| # | What | Command | When |
|---|---|---|---|
| 1 | Raw meta census for H6, H7, H9, H10, H11 (one strict `agentprov.ingest` read of 17,664 transcripts, ~20 s, counts and model ids only) | `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-adprov-v1 -- uv run python -I docs/reports/precheck/data/adprov-v1/exam-scripts/meta_census.py src ~/Desktop/PhD/Labs/AgentDojo-PROV-framework/corpus/corpus-prov ~/.agentprov/migration-work/precheck/adprov-v1/meta-census-release.json` | before the A/M counts 184 and 153 are relied on |
| 2 | H8 (DL-5): generic text-call detector count, expected ≤ 150 corpus-wide (A/M 470 has another basis; E2 detector 135) | no script exists yet: needs a new counts-only exam script over the stored AER or the raw transcripts (for example `D/exam-scripts/textcall_census.py`), run through `tools/suite_queue.py --class import --cpu 2 --label precheck-adprov-v1` | before the A/M count 470 is relied on |
| 3 | Optional, only if DL-9 must be settled (PC-08): a one-label CLI import with the listing pin into `W/dl9` through the queue | `agentprov import adprov-v1 --input IN --verify-against-pin` with an include of one label (see `agentprov import --help`), via `tools/suite_queue.py --class import --cpu 2` | optional |
| 4 | Tool owner after the batch (PC-11): `l2_check` identity benign≡none keyed on `adprov.v1_benign_label@1`; count executions for A3 pass classes | no command (tool change, then re-run the `check` step of section 9) | after the tool freeze |
| 5 | Exam owner: add a note to `delta-e2-release.json` that the positional SEM sections were replaced by the multiset comparison; fix the `research.json` II-utility `n` text (PC-02) | no command (data note) | any time |
