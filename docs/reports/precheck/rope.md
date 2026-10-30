# Pre-check dossier: `rope`

## 1. Header

| | |
|---|---|
| Corpus | `rope` (MIT, named holders; papers CC BY 4.0) |
| Parts | `rope · head` (10,791 TraceLogger logs under `runs/`) and `autodojo · rope-slice` (via `rope`: the 2,847 `runs/<model>/<suite>/user_task_*/autodojo/*.json` logs inside the head) |
| Family / profiles | `agentdojo` / `rope@2` (semantics `agentdojo.suites@2`, variants `v1.k14` 10,789 + `v1.k14.incomplete` 2) and `autodojo-via-rope@1` |
| Pin | git `xhOwenMa/ROPE` @ `64495e16` (HEAD of the only branch), tree `c4df12c3`, `runs/` tree `6a8c86f2`; local clean clone |
| Code commit | L1 `db6ef512`; L2 imports and checks `c4ee3dd1` (no tracked changes); batch `wave1` |
| Kind | wave 1, delta since E2 (stored corpus `rope-p10.partial`, commit `afe7038`) |
| Date | 2026-10-14 (prereg, research, L1), 2026-10-15 (L2 analysis, verify, dossier) |
| Agents | researcher and fact-checker (prereg, research), examiner (L1/L2 analysis), one verifier per finding (7), dossier writer |
| Data | [`data/rope/`](data/rope/): `research.json`, `l1-head.json`, `l2-sample-head.json`, `l2-sample-rope-slice.json`, `l2-head.json`, `l2-rope-slice.json`, `exam.json`, `exam-l1-cells.json`, `exam-outcomes.json`, `exam-stored-corrections.json`, `exam-delta-head.json`, `exam-delta-rope-slice.json`, `exam-sample-checks-{head,rope-slice}.json`, `l2-targeted-head.json`, `findings.json`, `exam-scripts/` |

- Code identity, part `head` (Level 2, [`code-head.json`](data/rope/code-head.json)): commit `c4ee3dd1`; engine code aer `24df84b5e307`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `d3f9995f61bf`; adapter agentdojo.tracelogger c311b5a6ac9e.
- Code identity, part `rope-slice` (Level 2, [`code-rope-slice.json`](data/rope/code-rope-slice.json)): commit `c4ee3dd1`; engine code aer `24df84b5e307`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `d3f9995f61bf`; adapter agentdojo.tracelogger c311b5a6ac9e.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Source repository | https://github.com/xhOwenMa/ROPE @ `64495e16` (2026-08-31; 3 commits; 0 tags, releases, issues, PRs, forks on 2026-10-14) | the data; `runs/` holds the logs and the aggregators of every reported table |
| Primary paper | ROPE, arXiv [2608.27496v1](https://arxiv.org/abs/2608.27496v1) (only version) | Tables 2-6, 11-14 computed from `runs/` (effect-corrected security, macro means) |
| AutoDojo paper | arXiv [2606.15057v3](https://arxiv.org/abs/2606.15057v3) (v1, v2, v3; cite v3) | attack of the 2,847-log slice; its ROPE rows (raw security, micro) reproduce from the logs |
| AgentLAB paper | arXiv [2602.16901v1](https://arxiv.org/abs/2602.16901v1) | source of the 760 long-horizon replays; `agentlab/res/**` owned elsewhere (`ext:agentlab`) |
| AgentDojo paper | https://arxiv.org/abs/2406.13352 | benchmark; harness is an unreleased AgentDojo 0.1.35 fork (vendored AutoDojo) |
| External data record | none (HF, Zenodo searched 2026-10-14); the git tree is the record | n/a |
| Upstream issues | ethz-spylab/agentdojo #168/#189 (slack IT5, = ROPE correction), #218, #181, #188, #214, #161/#138, #212/#177; SaFo-Lab/AgentDyn [#6](https://github.com/SaFo-Lab/AgentDyn/issues/6) (closed before `5353cf76`), [#8](https://github.com/SaFo-Lab/AgentDyn/issues/8) (open) | checker and harness defects relevant to these logs |

Data-versus-paper notes (from `research.json`, leads L-01..L-18):

- Two published derivations from the same logs: AutoDojo v3 uses raw security, micro-averaged; ROPE uses effect-corrected security, macro-averaged (raw AutoDojo-arm successes 88, corrected 71). Both reproduce (section 6).
- Router study (ROPE Table 5): `+clamp` trees exist only for `router/{gemini-3-flash,gpt-oss-20b}-clamp/dailylife`; 7 of the 9 per-suite clamp cells and the 3 clamp overall values (and every Opus clamp value) cannot be reproduced from the release (L-01; confirmed by H-07).
- The paper names Opus 4.8 as router; no log names it. gpt-4o-mini main-tree tags mix iter4 1,774 / iter2 178 (2026-06-16) / final-opus 63 (2026-08-12) code states (L-02, H-08). Enforcer denial text changes about 2026-06-29 (L-03, H-09).
- The logged system prompt cannot be produced by the released `autodojo/` harness (L-04). 322 null-final logs are third passes after two unlogged passes (L-05).
- README says all runs use OpenRouter; Gemini ran on the native Google API and Qwen on a local vLLM; the qwen3-235b AutoDojo logs carry a gpt-4o-mini tag (L-06, H-18).
- AgentDyn #8: github `user_task_5/7/8/11` utility can never be true (H-06: false 428/428). AgentDojo #181: banking attacked security true 0 (H-23).
- The gpt-4o AgentDojo-suite logs (389 attacked + 57 clean) are in no reported table; AutoDojo-paper ROPE rows for GPT-5.4-mini, DeepSeek-v4-Flash, Claude-Haiku-4.5 have no released logs.
- `artefacts.toml` ROPE entries stale after regen items 1 and 4 (L-15; finding PC-rope-01).

## 3. Expectations

Pre-registration: [`prereg/rope.md`](prereg/rope.md), committed in `fd75f8a3` (2026-10-14), before any check of this corpus ran. Method amendments 1 to 3 (README section 8) apply; amendment 1 covers the stored corpus's `validate.results.differ` (PC-rope-03), amendment 2 item 5 the slice frame (`--where attack_dir=autodojo`).

Hypotheses H-01..H-23: 23/23 supported, three of them in part. H-12: the 2 empty LH logs are untested (not sampled). H-13: the positive side is untested. H-20: holds under the census definition, with the id-free baseline as a new figure (PC-rope-05, CC-01). H-22 is supported as finding PC-rope-01. Untested items are in the targeted import (section 10). Two check-map rows are not backed by an L1 count: the L1-03 YAML-escape figure and the L1-08 unexecuted-tail and minimum-size figures (see the L1 table and section 10).

Classes follow the canonical rules R1-R6 and the cross-cutting items CC-01 to CC-08 of [`cross-cutting.md`](cross-cutting.md) (harmonisation pass 2026-10-15).

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Run at `db6ef512` on a local clean clone, `--pin-check` (10,813 blobs verified), jobs 2. All batch steps rc 0.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 24,909 files / 265,463,047 B outside `.git` = pin. Dispositions: selected 10,791 (175,263,358 B; slice 2,847 / 48,275,981 B), context 35, excluded 14,066 (`select.owned_elsewhere` 13,765 + `select.not_execution_artefact` 301), not selected 17 (+ 29 `.git` internals counted by the walk, PC-rope-06). Units 10,791 = registry | as expected (H-01) |
| L1-02 parse | strict ok 10,791/10,791 and auxiliary 22/22; 0 in every class (duplicate key, non-finite, big int, lone surrogate, BOM, trailing data, invalid UTF-8, truncation, depth) | as expected |
| L1-03 encodings | 0 U+2028/2029/0085, C0/C1, ESC, bidi, tag, zero-width, PUA, U+FFFD, mojibake. By design: `escaped_newline` 6,073 artefacts (11,887 strings), `escaped_quote` 1,298, `escaped_unicode` 1,751 (2,033 strings, AgentDojo #214), `json_in_string` 6 / 13, `variation_selector` 9 / 12 (= E2) | zero classes as expected. The prereg's "about 3,824 wholly escaped YAML AutoDojo payloads" is not tested by L1: L1-03 has no YAML-escape class (the AutoDojo escape shows in `escaped_newline` / `escaped_quote` together with the Python-repr tool outputs); count in section 10 |
| L1-04 duplicates | 0 byte-identical (part, cross-part, cross-corpus). Id-free fingerprint: 235 groups / 1,042 units (10,789 fingerprinted, 9,982 distinct); within one cell 156 / 660. With provider ids (census definition, stored AER): 53 / 396. Cross-corpus with agentdyn a: 7 groups, 15 ROPE + 9 AgentDyn logs (PC-rope-05) | census definition as expected (H-20); definition finding PC-rope-05 (CC-01: both figures reported, a tool definition) |
| L1-05 arms | 103 strata, every cell equals prereg section 3 (H-02). Missing by design: LH travel `user_task_0 x injection_task_2` (gpt-4o-mini, qwen3-235b); gpt-4o AutoDojo/LH; AgentDojo suites in ablation/router; github/shopping clamp; every undefended/baseline arm. Extra: gpt-4o AgentDojo-suite 389 + 57; 2 aborted LH logs. Path components agree 10,791/10,791 except `attack_dir` on the 760 LH logs (profile alias; PC-rope-04) | as expected |
| L1-06 secrets/paths | `generic-credential-assignment` 2,830 artefacts (4,222 strings, 8 pointers); `private-key-block` 79 (all dailylife; fixture header); home-dir 3 named (2 distinct names) + 3 generic (persona/env); operator_home 0; local-path model 0; 12 credential-shaped strings in auxiliary injection caches. All benchmark fiction (PC-rope-07; CC-02 for the dailylife key header, CC-03 for the home paths) | as expected (trap 11) |
| L1-07 timestamps | `/evaluation_timestamp` 10,791/10,791, 0 parse failures, all naive, 2026-06-16..2026-08-12; 0 non-monotone; the 35 "non-monotone" artefacts are tool-argument scenario dates (PC-rope-06); no per-step times | as expected (H-21) |
| L1-08 degenerate | zero_messages + incomplete 2 (empty LH logs); error_only 0; non-null error 0/10,791; null_final 33 (all gemini, empty final turn; not the 322 reruns; the CC-08 rule fix applies to this v1.k14 part) | 2 empty and 0 error as expected. The prereg's 675 unexecuted-tail logs and minimum file size 1,751 B are not tested by L1 (no unexecuted-tail flag; the minimum unit size is not reported); 675 appears here only as the stored-index population rate in section 5; counts in section 10 |
| OS-1 outcomes | 36/36 AutoDojo-paper per-suite integers equal (gpt-4o-mini, gemini; CU, II raw, AutoDojo raw); every AP micro and RP macro aggregate within 0.05 pp. Recorded security true: II 444, AutoDojo 88, LH 0/758, clean constant 748. Banking attacked true 0 (H-23); github ut5/7/8/11 utility false 428/428 (H-06). Tags iter4 1,774 / iter2 178 / final-opus 63 (H-08); clamp only in router `*-clamp` dailylife, 440 logs (H-07). Stored recomputed judgements: slack IT5 32→0, dailylife IT7 39→22, github IT1 5→0, 678 recomputed (198/260/220); AutoDojo 88→71 (33→19, 19→19, 36→33); II corrected in paper cells 90 = 24/22/31/13 with the Table 6 split (H-04, H-05); ablation/router corrected ASR and CU equal RP T4/T5 in 22/22 reproducible cells | 0 arms flagged |

Duplicate group counts in this table are the per-part L1 summary (`l1-head.json`), and this dossier uses it. `data/_cross/l1-xdup.json` counts a group under `within_part` only when all its members are in one part; groups that span parts or corpora move to `cross_part` or `cross_corpus`, so its within-part figure is lower (trajectory groups 233 vs 235). A comparison with the post-check must use the same basis.

## 5. Level 2

| Item | Result |
|---|---|
| Sample | head [`data/rope/l2-sample-head.json`](data/rope/l2-sample-head.json) (sha256 `ce9a0f0d...`): 300 units over 103 strata (2-3 each, cap 300). Slice [`data/rope/l2-sample-rope-slice.json`](data/rope/l2-sample-rope-slice.json) (sha256 `09522238...`): 90 units, 18 AutoDojo strata × 5. 4 labels in both |
| Import | `GitPinTree` at the pin, dev mode, `rope@2`. Head 300/300 mapped (ok 264, ok_with_issues 36), 0 failed / degenerate / `adapter_defect`. Slice 90/90 (58 + 32) |
| Issue codes | head: `accounting_unverifiable` 300, `earlier_attempts_unobservable` 300, `identity_conflict` 18 (all qwen3-235b AutoDojo), `retry_passes_inferred` 14 (4.7 % [2.8, 7.7]; population 3.0 %), `unexecuted_tool_call` 20 (6.7 %; population 6.3 %). Slice: 90 / 90 / 30 / 3 / 9 |
| Validation | tiers aer, sem, prov, linkage: 300/300 and 90/90 pass, results_reproduced, linkage 100 %. SHACL not implemented (skipped); regression n/a |
| Recompute | `--dry-run`: identical 300 / 90, 0 unexplained |
| Verify chain | 335 raw objects re-hashed (head), 0 failed; only `checksums.absent` (working tree). The prereg's sealed-copy run was not made: README section 4 asks for it only where withholding applies, and the profile has no `[withhold]` table |
| Determinism | j2 vs j1: head 1,242/1,242 files and the index identical; slice 0 differ (H-19) |
| A2 error classes | 0 degenerate, 0 `adapter_defect`, 0 unreadable |
| A3 PROV issues | 0 PI-class hits; all 32 unexecuted-call parts carry `apv:NotDispatched`; 0 dangling or invented relations; core I 0 |
| Evidence classes | head PROV: core O 14,228 / D 1,471 / none 2,315 / I 0; inference I 105,163 (101,570 via `_unverified` twins); assessment I 52,099 / O 600 / D 153. AER records: model_call I 2,245, tool_execution I 2,020, activity I 191, decision I 272, judgement O 600 / D 20 (`rope.security_correction` stays D) |
| Identity | 0 unresolved. Models from the directory (ablation/router → gpt-4o-mini; `rope.model_dir_identity@1`); qwen3-235b AutoDojo logs carry a gpt-4o-mini tag → qwen3-235b with `identity_conflict` (18 + 30); defence `rope` with `ext.rope.arm`. The 27 l2_check "direct mismatches" are the LH alias (PC-rope-04) |
| Judgements | raw vs mapped on the same 390 labels: utility 390/390, recorded security 390/390. Recomputed judgement on exactly the 24 sampled corrected-task executions, none elsewhere; 2 change true→false |
| Regen item checks | U6-c: `/params` not_recorded 2,891/2,891 model calls (H-17). Item 5: exactly 1 class-I `load_environment` on 281/281 attacked, 0 on 109 clean (H-14). Items 9/11: completeness unverifiable 390/390, verified_complete 0; 17 null-final rows known_incomplete → unverifiable. suites@2: AgentDyn tool roles unknown 3,468/3,468, AgentDojo-suite 0/2,088 (H-16). B1: AutoDojo executions with a present marker slice 78/90 = 86.7 % [78.1, 92.2] (stored 38/90), head 46/54 (stored 21/54) (H-15); marker transitions only on AutoDojo; item 8 changes 0 statuses. `partial_payload` 27/300 (9.0 % [6.3, 12.8]) and 12/90. `success_without_visible_payload` 0/390 |
| Redaction | head 0 hits in 908 files; slice 1 execution with the dailylife fixture key header (header only) in AER and PROV (PC-rope-07, CC-02); 0 account paths in AER/SEM/PROV/index; the 6 L1 home-dir labels were not sampled |
| Withholding | not applicable (no `[withhold]` table; none expected) |
| DL-1 (stored `rope-p10.partial` `afe7038` vs scratch, same 390 ids) | every file and digest differs; every pointer attributed, 0 unexplained (PC-rope-02): item 30, item 3 (15 twin swaps), U6-c (prediction text: CC-04), item 5, items 9/11, D-86 and items 1/4/6/8 (SEM), item 3/5 (PROV core→inference, new inference bundles), B1 and item 6 (assessment). 0 judgement value changes, 0 record removals. Stored validation rows: `validate.results.differ` expected-known (PC-rope-03, CC-05), not re-run |

### Recheck (CC-08, recheck12)

`plans/recheck12.toml` (l1, l1_10, check; sample frozen) against the d97d3a57 files; full deltas in [`_cross/recheck12.json`](data/_cross/recheck12.json). Every other L1/L2 count is unchanged; the only other deltas are run environment (code commit d97d3a57 with tools/src = 5efa3575, `tracked_changes` true, two H.8.4(2) recompute notices with 0 unexplained changes; R12-01).

| Part | L1-08 flags (old -> new) | L2 `_unverified` split | L1-10 |
|---|---|---|---|
| head | `trailing_calls` - -> 675 | twin inference:I 101,570 -> 89,438; mixed 12,132; native 0 (sum 101,570 = old) | 13 screened (context 13); 0 hits; files with a hit 0; named accounts 0; operator 0; unreadable 0 |
| rope-slice | absent | twin inference:I 29,460 -> 25,546; mixed 3,914; native 0 (sum 29,460 = old) | n/a (no l1 input) |

- PC-rope-06 item (e): `null_final` stays 33 under the widened rule (no all-empty text-block finals beyond the 33); `trailing_calls` 675 new. rope-slice has no L1 (units from head); its L2 split as for head.

## 6. Outcome comparison

Level 1 is the population (raw booleans and the stored recomputed judgements, 10,791 logs). Level 2 is the AER of the sample. References: AP = AutoDojo v3 Tables 5/6/8/9 (raw, micro); RP = ROPE v1 tables (corrected, macro where marked). Gap rule: more than 15 pp, or more than 5 pp outside the Wilson 95 % interval; on the sample only for arms with at least 20 executions (all L2 arms here have 27 or more). L2 references are population rates weighted to the sample's strata.

| Arm (model / attack / suites) | Level | n | Metric | Rate (Wilson 95 %) | Paper | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|---|
| gpt-4o-mini / II / AgentDojo | L1 | 389 | ASR raw / UA | 6.43 % 25 [4.4, 9.3] / 45.50 % 177 [40.6, 50.5] | 6.4 / 45.5 AP | +0.03 / 0.00 | match |
| gpt-4o-mini / AutoDojo / AgentDojo | L1 | 389 | ASR raw / UA | 4.37 % 17 [2.7, 6.9] / 49.61 % 193 [44.7, 54.6] | 4.4 / 49.6 AP | -0.03 / +0.01 | match |
| gemini-2.5-flash / II / AgentDojo | L1 | 389 | ASR raw / UA | 3.34 % 13 [2.0, 5.6] / 51.67 % 201 [46.7, 56.6] | 3.3 / 51.7 AP | +0.04 / -0.03 | match |
| gemini-2.5-flash / AutoDojo / AgentDojo | L1 | 389 | ASR raw / UA | 3.86 % 15 [2.4, 6.3] / 50.64 % 197 [45.7, 55.6] | 3.9 / 50.6 AP | -0.04 / +0.04 | match |
| gpt-4o-mini / II / AgentDyn | L1 | 560 | ASR raw / UA | 2.14 % 12 [1.2, 3.7] / 36.07 % 202 [32.2, 40.1] | 2.1 / 36.1 AP | +0.04 / -0.03 | match |
| gpt-4o-mini / AutoDojo / AgentDyn | L1 | 560 | ASR raw / UA | 2.86 % 16 [1.8, 4.6] / 33.57 % 188 [29.8, 37.6] | 2.9 / 33.6 AP | -0.04 / -0.03 | match |
| gemini-2.5-flash / II / AgentDyn | L1 | 560 | ASR raw / UA | 1.61 % 9 [0.8, 3.0] / 20.89 % 117 [17.7, 24.5] | 1.6 / 20.9 AP | +0.01 / -0.01 | match |
| gemini-2.5-flash / AutoDojo / AgentDyn | L1 | 560 | ASR raw / UA | 0.71 % 4 [0.3, 1.8] / 12.32 % 69 [9.9, 15.3] | 0.7 / 12.3 AP | +0.01 / +0.02 | match |
| qwen3-235b / none / AgentDyn | L1 | 60 | CU | 53.33 % 32 [40.9, 65.4] | 53.3 RP T2/T11 | +0.03 | match |
| gpt-4o / none / AgentDyn | L1 | 60 | CU | 53.33 % 32 [40.9, 65.4] | 53.3 RP T11 | +0.03 | match |
| gpt-4o-mini / LH / AgentDojo | L1 | 253 | ASR raw | 0.00 % 0 [0.0, 1.5] | 0.0 RP T3 | 0.00 | match |
| gemini-2.5-flash / LH / AgentDojo | L1 | 254 | ASR raw | 0.00 % 0 [0.0, 1.5] | 0.0 RP T3 | 0.00 | match |
| qwen3-235b / LH / AgentDojo | L1 | 253 | ASR raw | 0.00 % 0 [0.0, 1.5] | 0.0 RP T3 | 0.00 | match |
| ablation always-fully-specified / II / github, shopping, dailylife | L1 | 180 / 180 / 200 | ASR corrected | 0.00 % 0 [0.0, 2.1] / 5.00 % 9 [2.7, 9.2] / 0.50 % 1 [0.1, 2.8] | 0.0 / 5.0 / 0.5 RP T4 | 0.00 / 0.00 / 0.00 | match |
| ablation always-action-open / II / github, shopping, dailylife | L1 | 180 / 180 / 200 | ASR corrected | 35.00 % 63 [28.4, 42.2] / 28.89 % 52 [22.8, 35.9] / 68.00 % 136 [61.2, 74.1] | 35.0 / 28.9 / 68.0 RP T4 | 0.00 / -0.01 / 0.00 | match |
| router gemini-3-flash / II / github, shopping, dailylife | L1 | 180 / 180 / 200 | ASR corrected | 1.67 % 3 [0.6, 4.8] / 5.00 % 9 [2.7, 9.2] / 6.00 % 12 [3.5, 10.2] | 1.7 / 5.0 / 6.0 RP T5 | -0.03 / 0.00 / 0.00 | match |
| router gpt-oss-20b / II / github, shopping, dailylife | L1 | 180 / 180 / 200 | ASR corrected | 1.11 % 2 [0.3, 4.0] / 7.22 % 13 [4.3, 12.0] / 0.50 % 1 [0.1, 2.8] | 1.1 / 7.2 / 0.5 RP T5 | +0.01 / +0.02 / 0.00 | match |
| router gemini-3-flash-clamp / II / dailylife | L1 | 200 | ASR corrected | 0.00 % 0 [0.0, 1.9] | 0.0 RP T5 | 0.00 | match |
| router gpt-oss-20b-clamp / II / dailylife | L1 | 200 | ASR corrected | 0.50 % 1 [0.1, 2.8] | 0.5 RP T5 | 0.00 | match |
| qwen3-235b / II / AgentDojo | L1 | 389 | ASR corrected (macro) | 4.60 (n/a, macro) | 4.6 RP T13 | 0.00 | match |
| qwen3-235b / AutoDojo / AgentDojo | L1 | 389 | ASR corrected (macro) | 5.00 (n/a) | 5.0 RP T14 | 0.00 | match |
| qwen3-235b / II / AgentDyn | L1 | 560 | ASR corrected (macro) | 2.57 (n/a) | 2.6 RP T2/T11 | -0.03 | match |
| gpt-4o / II / AgentDyn | L1 | 560 | ASR corrected (macro) | 2.37 (n/a) | 2.4 RP T11 | -0.03 | match |
| qwen3-235b / none / AgentDojo | L1 | 57 | CU (macro) | 67.90 (n/a) | 67.9 RP T13 | 0.00 | match |
| head ablation+router / II / AgentDyn | L2 | 38 | UA / ASR raw / ASR corr. | 23.68 % [13.0, 39.2] / 10.53 % [4.2, 24.1] / 7.89 % [2.7, 20.8] | 29.03 / 12.79 / 12.34 | -5.34 / -2.26 / -4.44 | covered |
| head ablation+router / none / AgentDyn | L2 | 37 | CU | 35.14 % [21.8, 51.2] | 36.08 | -0.95 | covered |
| head main / LH / AgentDojo | L2 | 27 | UA / ASR raw / ASR corr. | 44.44 % [27.6, 62.7] / 0.00 % [0.0, 12.5] / 0.00 % [0.0, 12.5] | 41.27 / 0.0 / 0.0 | +3.17 / 0 / 0 | covered |
| head main / AutoDojo / AgentDojo | L2 | 27 | UA / ASR raw / ASR corr. | 55.56 % [37.3, 72.4] / 3.70 % [0.7, 18.3] / 0.00 % [0.0, 12.5] | 53.65 / 4.89 / 3.94 | +1.91 / -1.19 / -3.94 | covered |
| head main / AutoDojo / AgentDyn | L2 | 27 | UA / ASR raw / ASR corr. | 29.63 % [15.9, 48.5] / 7.41 % [2.1, 23.4] / 7.41 % [2.1, 23.4] | 28.64 / 2.10 / 1.65 | +0.99 / +5.30 / +5.75 | no flag (ref. 0.45 pp below the interval, under 5 pp) |
| head main / II / AgentDojo | L2 | 36 | UA / ASR raw / ASR corr. | 41.67 % [27.1, 57.8] / 2.78 % [0.5, 14.2] / 2.78 % [0.5, 14.2] | 54.23 / 5.85 / 4.03 | -12.56 / -3.08 / -1.25 | covered |
| head main / II / AgentDyn | L2 | 36 | UA / ASR raw / ASR corr. | 41.67 % [27.1, 57.8] / 0.00 % [0.0, 9.6] / 0.00 % [0.0, 9.6] | 37.19 / 2.19 / 2.10 | +4.47 / -2.19 / -2.10 | covered |
| head main / none / AgentDojo | L2 | 36 | CU | 69.44 % [53.1, 82.0] | 64.75 | +4.69 | covered |
| head main / none / AgentDyn | L2 | 36 | CU | 36.11 % [22.5, 52.4] | 43.75 | -7.64 | covered |
| slice / AutoDojo / AgentDojo | L2 | 45 | UA / ASR raw / ASR corr. | 55.56 % [41.2, 69.1] / 4.44 % [1.2, 14.8] / 4.44 % [1.2, 14.8] | 53.65 / 4.89 / 3.94 | +1.91 / -0.45 / +0.50 | covered |
| slice / AutoDojo / AgentDyn | L2 | 45 | UA / ASR raw / ASR corr. | 28.89 % [17.7, 43.4] / 0.00 % [0.0, 7.9] / 0.00 % [0.0, 7.9] | 28.64 / 2.10 / 1.65 | +0.25 / -2.10 / -1.65 | covered |

II = important_instructions, LH = long_horizon (AgentLAB replay). Zero-success arms (LH, banking, clamp) are kept and reported like every other arm. 0 arms flagged at either level. The mapping reproduces the raw booleans in 390/390.

## 7. Findings

7 findings, all confirmed by their verifier (0 refuted). Verifier corrections and the harmonisation entries are in `findings.json` (CC-06 format). Analysis-artefacts (R5: PC-rope-04, PC-rope-05, PC-rope-06) are tool properties and are not counted in the readiness verdict. The U6-c prediction text ("one `apv:Gap` per model call", prereg l.162) is cross-cutting item CC-04, recorded once in `cross-cutting.md`; PC-rope-02 references it and is not a separate CC-04 finding.

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-rope-01 | Three ROPE `artefacts.toml` entries (`autodojo_payload_escaped`, `security_without_exposure`, `pipeline_tag_not_identity`, all `manuscript = true`) are stale against suites@2 and the data | documentation-mismatch | S2 | confirmed (1/1), corrections | Route to the agentdojo family owner; update the entries before the datasheet/manuscript pass; recount suites@2 values on the regenerated corpus |
| PC-rope-05 | [CC-01] Identical-trajectory counts depend on fingerprinting provider call ids: id-free 235/1,042 vs census 53/396 (with-id groups contain only null-id providers); manuscript artefact row 7 labels 53/396 "byte-identical" | analysis-artefact (CC-01; was documentation-mismatch S2) | S3 | confirmed (1/1), corrections; the verifier's S2 rested on row 7 | CC-01: report both counts with their definitions. Manuscript row 7 (rope, agentdojo-upstream head and AgentDyn entries) is one decision, routed once under CC-01 to the manuscript owner; define the I_matrix §I.2.4/C27 count |
| PC-rope-02 | DL-1: every stored-vs-scratch difference on 390 ids attributed (items 30, 3, U6-c, 5, 9/11, D-86, 1/4/6/8, B1); 0 unexplained | expected-known | S3 | confirmed (1/1), coverage notes | None before the round; post-check expects the same pointer set; U6-c wording: CC-04 |
| PC-rope-03 | [CC-05] Stored validation rows predate item 10 (0/10,791 carry the 4 checks; they pass in scratch); digests also differ by mode (release vs dev) and SEM key (suites@1 vs @2) | expected-known (CC-05) | S3 | confirmed (1/1), evidence replaced | Compare like with like: same validation mode, sem profile normalised, check sets not digests |
| PC-rope-07 | [CC-02, CC-03] Benchmark-fiction secret and home-path shapes reach AER/PROV verbatim (fixture key header; 3 model-written placeholder key blocks; persona home paths); no real secret | expected-known (CC-02, CC-03) | S2 (CC-02; was S3) | confirmed (1/1), corrections | CC-02: the family owner widens RT-10 to every part with AgentDyn suites, rope head included (79 logs), and decides a `[withhold]` rule or a catalogue entry before release (one decision with PC-agentdyn-13); datasheet disclosure as benchmark fiction; optional catalogue entry |
| PC-rope-04 | LH attack alias flagged as path/identity mismatch by the pre-check tools (760 L1, 27 L2) | analysis-artefact | S3 | confirmed (1/1) | Tool owner after the batch: apply `attack_dir_alias` in the L1 hook and l2_check identity |
| PC-rope-06 | Tool counting notes: walk includes `.git` (29), pin-check skips 13 context `.py`, argument-date monotonicity, arm key folds ablation/router, `null_final` name (item (e): CC-08) | analysis-artefact | S3 | confirmed (1/1) | Tool owner after the batch; raw counts do not change; re-run L1-08 after the CC-08 fix |

Corrections applied (in `findings.json`):

- PC-rope-01: the count 5 for `success_without_visible_payload` is a pre-registered expectation (0/390 in the sample; targeted import pending) and stays `pending`. The entry 1 basis row also names the re-measure (1,235 executions / 1,840 markers, regen-batch.md). Entry 2 names `checker_outcome_unverified@1` (class I) as now cited. The existing entry 3 also wrongly generalises to "the AutoDojo arm": only the qwen3-235b directory carries a foreign tag.
- PC-rope-05: the multi-model group count is 120, not 115 (115 with one attack, 5 with several; 70 include gpt-4o-mini). The 7 cross-corpus groups hold 15 ROPE and 9 AgentDyn logs, so the census "9" counts the AgentDyn side. This is a wording gap, not a conflict.
- PC-rope-02: added the item-3 PROV bundle statements (+4,821 entity / specializationOf / wasGeneratedBy, wasDerivedFrom +15,294, inf:mentionOf +900) and SEM `span` +40 on the B1 markers. U6-c appears as `apv:paramsStatus` (apv:Gap unchanged 6,828), so the prereg wording "one apv:Gap per model call" was a wrong expectation. Item 8 bumps the normaliser label with 0 status changes.
- PC-rope-03: the evidence is the missing check set, not the digest count. Mode and SEM-key differences have been added.
- PC-rope-07: "header only" holds for the slice. The head has 3 model-written placeholder OPENSSH blocks with no key material. The home paths are also echoed in tool results. The home-dir unit is 6 artefacts with 2 distinct names.

Refuted (not findings): none.

Proposed `artefacts.toml` entries (text only; route to the agentdojo family owner):

```toml
# PC-rope-01, entry 1 (update)
[[artefact]]
id = "rope.art.autodojo_payload_escaped"
description = "AutoDojo writes its payload YAML-escaped into the log's injections while tool outputs show the decoded text. Under agentdojo.suites@2 the marker compares the payload with the escape undone where the cache link holds (agentdojo.autodojo_payload_unescape@1; _unverified twin on this harness); under suites@1 the marker was a wrong absent."
handling = { class = "CR", rule = "agentdojo.autodojo_payload_unescape@1" }
expected = [
  { snapshot = "rope:head", count = 1166, basis = "suites@1 (phase-10 analysis section 8 row 12; re-measured 1,235 executions / 1,840 markers)", status = "verified" },
  { snapshot = "rope:head", count = "<recount at the round; prereg 2528 of 2847>", basis = "suites@2: AutoDojo executions with >= 1 present marker", status = "pending" },
]
manuscript = true
refs = ["D.6.13 item 9", "regen-batch item 1 (B1, D-86)"]

# PC-rope-01, entry 2 (update)
[[artefact]]
id = "rope.art.security_without_exposure"
detector = { rule = "agentdojo.success_without_visible_payload@1", class = "D" }   # checker_outcome now cited via checker_outcome_unverified@1 (I)
handling = { class = "FO" }
expected = [
  { snapshot = "rope:head", count = 22, basis = "suites@1", status = "verified" },
  { snapshot = "rope:head", count = 5, basis = "suites@2 annotation (regen item 4); expected, not yet observed", status = "pending" },
]

# PC-rope-01, entry 3 (description only)
# rope.art.pipeline_tag_not_identity: "The pipeline_name of the qwen3-235b AutoDojo arm is a configuration tag naming gpt-4o-mini, not the agent model; the model comes from the release directory (identity_conflict on these 949 logs). The other AutoDojo arms carry tags of their own models."

# PC-rope-07 (new, optional)
[[artefact]]
id = "agentdojo.art.fixture_secret_shapes"
title = "Benchmark fixtures contain secret- and home-path-shaped strings"
scope = { sources = ["rope"], parts = ["head"], profiles = ["rope", "autodojo-via-rope"] }
cause = "benchmark"
detector = { rule = "none (pre-check L1-06 / redaction screen)", class = "O" }
handling = { class = "FO" }
expected = [
  { snapshot = "rope:head", count = 79, unit = "logs", basis = "L1-06 private-key-block (dailylife fixture header; 3 also hold model-written placeholder blocks)", status = "verified" },
  { snapshot = "rope:head", count = 2830, unit = "logs", basis = "L1-06 generic-credential-assignment", status = "verified" },
  { snapshot = "rope:head", count = 6, unit = "logs", basis = "L1-06 home-dir (3 named, 2 distinct names; 3 generic)", status = "verified" },
]
manuscript = false
refs = ["CORPUS-CHECK-PROTOCOL 8.4 trap 11"]
```

Items for AGENTS.md section 12:

- PC-rope-01: three ROPE catalogue entries flagged for the manuscript (`autodojo_payload_escaped`, `security_without_exposure`, `pipeline_tag_not_identity`) describe suites@1 behaviour and a wrong tag. They are stale until the family owner updates them. Recount them on the regenerated corpus.
- PC-rope-05: the ROPE duplicate count 53/396 is with provider call ids and groups only null-id providers. The id-free count is 235/1,042 (0 byte-identical files). Manuscript artefact row 7 needs the id-free count and its definition, and its other entries need the same check.

## 8. Recommendations and readiness

1. Route PC-rope-01 (the three entries) and the optional PC-rope-07 entry to the agentdojo family owner. Update before the datasheet/manuscript pass. PC-rope-07 also goes into the CC-02 decision: widen RT-10 to rope head (79 logs) and decide a `[withhold]` rule or a catalogue entry before release, together with agentdyn.
2. Manuscript owner, under CC-01 (one decision for all row-7 entries): report the id-free and the with-id duplicate counts with their definitions and add the definition to I_matrix §I.2.4/C27 (PC-rope-05).
3. Run the targeted 43-label import (section 10) to close H-12 (2 empty LH logs) and the positive side of H-13 (`success_without_visible_payload` on the 5 ablation II candidates). Optionally add the 6 home-dir labels.
4. Tool owner after the batches: PC-rope-04 and PC-rope-06 (item (e) with the CC-08 `null_final` fix). No corpus effect. Count the two prereg figures L1 does not report (YAML-escaped payloads, unexecuted tails and minimum size; section 10).
5. After the round: re-run `delta.py` and `stored_corr.py` on the regenerated corpus (expect 32→0 / 39→22 / 5→0 / 88→71). Compare validation like with like (PC-rope-03, CC-05).
6. No data is excluded. The zero-success arms (LH 0/758, banking, clamp) stay in.

**Readiness: `ready-with-caveats`.**

- Both parts import correctly and deterministically: 390/390 mapped, validation pass, recompute 0 unexplained, j1/j2 identical, DL-1 0 unexplained, judgements equal raw on 390/390, and every population arm reproduces both papers (0 flags).
- The caveats are all owned and routed, and none blocks the import:
  - PC-rope-01: catalogue update, family owner.
  - PC-rope-07: S2 disclosure and the RT-10 / `[withhold]` decision (CC-02), family owner.
  - H-12/H-13 untested on the sample: targeted import (section 10).
  - L1-03 YAML-escape and L1-08 unexecuted-tail / minimum-size expectations not counted by L1 (section 10).
  - PC-rope-03: stored `validate.results.differ`, expected-known under amendment 1 (CC-05).
- Not counted (R5, analysis-artefacts): PC-rope-05 (CC-01; the manuscript row-7 wording is routed under CC-01), PC-rope-04, PC-rope-06.

## 9. Reproduction

Batch (wave 1; plan entries in `tools/precheck/plans/wave1.toml`):

```toml
[[part]]
corpus_id = "rope"
source = "rope"
part = "head"
l1 = ["--input", "~/Desktop/PhD/Labs/AgentPROV-upstream/rope", "--pin-check"]

[[part]]
corpus_id = "rope"
source = "autodojo"
part = "rope-slice"
units_from = "head"
steps = ["sample", "import_j2", "import_j1", "check"]
sample = ["--where", "attack_dir=autodojo"]
```

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave1 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave1.toml
```

Steps the batch ran (W = `~/.agentprov/migration-work/precheck/rope`, D = `docs/reports/precheck/data/rope`; P = `head` or `rope-slice`, source `rope` or `autodojo`):

```bash
uv run python tools/precheck/l1_scan.py --source rope --part head --corpus-id rope --jobs 2 --emit-fp --input ~/Desktop/PhD/Labs/AgentPROV-upstream/rope --pin-check
uv run python tools/precheck/l2_sample.py select --units W/l1-units-head.jsonl --source rope --part head --corpus-id rope --out D/l2-sample-head.json
uv run python tools/precheck/l2_sample.py select --units W/l1-units-head.jsonl --source autodojo --part rope-slice --corpus-id rope --where attack_dir=autodojo --out D/l2-sample-rope-slice.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-P.json --corpus W/l2-P-j2 --source <source> --part P --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-P.json --corpus W/l2-P-j1 --source <source> --part P --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-P-j2.partial --out D/l2-P.json --sample D/l2-sample-P.json --l1-units W/l1-units-head.jsonl --compare-with W/l2-P-j1.partial --jobs 2
# inside l2_check:
uv run agentprov validate --corpus W/l2-P-j2.partial --tiers aer,sem,prov,linkage,shacl,regression --jobs 2
uv run agentprov recompute --corpus W/l2-P-j2.partial --dry-run --jobs 2 -q
uv run agentprov verify --corpus W/l2-P-j2.partial --level chain
```

Examiner and verifier scripts (read-only; S = `~/.agentprov/corpora/rope-p10.partial`):

```bash
python3 D/exam-scripts/l1_out.py; python3 D/exam-scripts/l1_it.py   # OS-1 population outcomes from W/l1-units-head.jsonl (exam-l1-cells.json)
uv run python D/exam-scripts/stored_corr.py; uv run python D/exam-scripts/stored_misc.py   # stored recomputed judgements (exam-stored-corrections.json)
python3 D/exam-scripts/targeted.py --print   # builds D/l2-targeted-head.json (counts only)
uv run python D/exam-scripts/delta.py S W/l2-head-j2.partial <scratch>/delta-head.json         # DL-1, PC-rope-02
uv run python D/exam-scripts/delta.py S W/l2-rope-slice-j2.partial <scratch>/delta-slice.json  # DL-1, PC-rope-01
uv run python D/exam-scripts/sample.py W/l2-rope-slice-j2.partial <scratch>/s.json             # B1, markers (exam-sample-checks-*.json)
python3 D/exam-scripts/stored_extra.py; python3 D/exam-scripts/l1_dup.py                        # PC-rope-05
uv run python -I D/exam-scripts/pk.py; uv run python -I D/exam-scripts/acct2.py <6 labels>      # PC-rope-07
uv run python D/exam-scripts/outcomes.py W/l2-head-j2.partial   # L2 outcome pooling by tree (exam-outcomes.json)
```

Follow-ups for the orchestrator: section 10.

## 10. Open follow-ups

Not run in the harmonisation pass (they need a re-run, a new counts-only script, a tool fix or the round). W, D and S as in section 9.

| # | What | Command | When |
|---|---|---|---|
| 1 | Targeted 43-label import for H-12 (2 empty LH logs) and the positive side of H-13 (`success_without_visible_payload` on the 5 ablation II candidates); optionally add the 6 home-dir labels | `uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-rope -- uv run python tools/precheck/l2_import.py --sample D/l2-targeted-head.json --corpus W/l2-targeted-j2 --source rope --part head --jobs 2`, then `uv run python tools/precheck/l2_check.py --corpus W/l2-targeted-j2.partial --out W/l2-targeted.json --sample D/l2-targeted-head.json --l1-units W/l1-units-head.jsonl --jobs 2` and `uv run python D/exam-scripts/sample.py W/l2-targeted-j2.partial <scratch>/rope-targeted.json` | when the queue admits it |
| 2 | L1-08 minimum file size (prereg 1,751 B), counts only from the committed L1 units | `python3 -I -c "import json,os;R=[json.loads(l) for l in open(os.path.expanduser('~/.agentprov/migration-work/precheck/rope/l1-units-head.jsonl'))];print(min(r['size'] for r in R), sum(r['size'] for r in R))"` | any time (light) |
| 3 | L1-08 unexecuted-tail logs (prereg 675 logs / 753 calls) and L1-03 wholly YAML-escaped AutoDojo payloads (prereg about 3,824): no L1 class exists for either | needs a new counts-only exam script (none exists yet), e.g. `D/exam-scripts/l1_tails.py` reading the 10,791 pinned logs through `agentprov.ingest` and writing `D/l1-extra.json`; run as `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-rope-extra -- uv run python -I D/exam-scripts/l1_tails.py --root ~/Desktop/PhD/Labs/AgentPROV-upstream/rope --units W/l1-units-head.jsonl --out D/l1-extra.json`. Until then the stored index gives the unexecuted-tail population rate (`unexecuted_tool_call` 675, section 5) | after the script is written |
| 4 | CC-08: re-run head L1 after the `null_final` fix (v1.k14 part) | `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-rope-l1 -- uv run python tools/precheck/l1_scan.py --source rope --part head --corpus-id rope --jobs 2 --emit-fp --input ~/Desktop/PhD/Labs/AgentPROV-upstream/rope --pin-check` | after the tool fix lands |
| 5 | After the round: DL-1 and the stored recomputed judgements on the regenerated corpus (expect 32→0 / 39→22 / 5→0 / 88→71) | `uv run python D/exam-scripts/delta.py <regenerated rope corpus> W/l2-head-j2.partial <scratch>/delta-post.json`; `uv run python D/exam-scripts/stored_corr.py` | after the round |
| 6 | CC-02 / PC-rope-07: RT-10 widening and the `[withhold]` or catalogue decision; CC-01 / PC-rope-05: manuscript row 7 | no command (family owner; manuscript owner) | before the datasheet/manuscript pass |
