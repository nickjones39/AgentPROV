# Pre-check dossier: `agentdojo-upstream`

## 1. Header

| | |
|---|---|
| Corpus | `agentdojo-upstream` (MIT by repository; see PC-10 for the 2024-06 pin) |
| Parts | `agentdojo · head` (36,679 TraceLogger logs: v0.k11 24,914, v1.k14 11,764, v1.k14.incomplete 1), `agentdojo · 2024-06` (18,241: v0.k11 18,237 + v0.k11.incomplete 4) |
| Family / profile | `agentdojo` / `agentdojo-upstream@2` (sha256 `ab0ccd4f...`; dialect `agentdojo.tracelogger`; rules aer 1, agentdojo 2; SEM `agentdojo.suites@2`) |
| Pins | git `ethz-spylab/agentdojo` head `089ed468` (`runs/` tree `472cbb2e`, 426,293,413 B) and 2024-06 `c2748856` (`runs/` tree `1227480d`, 188,873,874 B). Input `--use-pin` (fetch-cache clone, full history) |
| Code commit | L1 2024-06 at `a871e2d7`, L1 head and both L2 at `db6ef512` (clean tree). Batch `wave1` committed in `8138e1e3` |
| Kind | wave 1, delta corpus: imported in full at `afe7038` and examined in E2 (`../analysis/phase10-examination-2.md`); stored corpora `agentdojo-upstream-{head,2024-06}-p10.partial` |
| Date | 2026-10-14 (prereg, research, L1), 2026-10-15 (L2, exam, verify, dossier) |
| Agents | researcher and fact-checker (prereg, research), examiner (L1/L2 analysis), one verifier per finding (11), dossier writer |
| Data | [`data/agentdojo-upstream/`](data/agentdojo-upstream/): `research.json`, `l1-head.json`, `l1-2024-06.json`, `l1-extra.json`, `l2-sample-head.json`, `l2-sample-2024-06.json`, `l2-head.json`, `l2-2024-06.json`, `exam.json`, `os1-population.json`, `os2-sample.json`, `dl1-delta.json`, `findings.json`, `exam-scripts/`; cross-corpus `data/_cross/l1-xdup.json` |

- Code identity, part `2024-06` (Level 2, [`code-2024-06.json`](data/agentdojo-upstream/code-2024-06.json)): commit `db6ef512`; engine code aer `24df84b5e307`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `d3f9995f61bf`; adapter agentdojo.tracelogger c311b5a6ac9e.
- Code identity, part `head` (Level 2, [`code-head.json`](data/agentdojo-upstream/code-head.json)): commit `db6ef512`; engine code aer `24df84b5e307`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `d3f9995f61bf`; adapter agentdojo.tracelogger c311b5a6ac9e.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Repository | https://github.com/ethz-spylab/agentdojo (head pin `089ed468`, 2026-06-02, still HEAD of main on 2026-10-14; 2024-06 pin `c2748856`, 2024-06-05, package `function-calling-pi 0.1.0`) | the data (`runs/`); MIT LICENSE added `bd533515` (2024-06-10), absent at `c2748856` |
| Paper P1 | https://arxiv.org/abs/2406.13352v1 (2024-06-19) | Tables 2-5; describes the 2024-06 part (no `runs/` commit between `c2748856` and v1) |
| Paper P3 | https://arxiv.org/abs/2406.13352v3 (2024-11-24, NeurIPS D&B; numbers = v2 of 2024-07-18) | Tables 2-5; describes the head part for the 2024 models (after the July travel and Llama re-runs) |
| Paper SA | https://arxiv.org/abs/2507.02735 (Meta SecAlign; v1 2025-07-03, v2 2025-11-10, v3/v4 repeat v2) | only published numbers for the 11,765 local v1.k14 logs (PR #96/#97, committed 2025-07-25) |
| Results page W | https://agentdojo.spylab.ai/results/ (generated from `runs/` by `util_scripts/create_results_table.py`) | 28 rows; mean of logged security (run errors included) |
| Data record | Zenodo concept 10.5281/zenodo.12528188 (36 software archives; v0.1.35 record 17458493 = head `runs/`; v0.1.8 record 12742856 = 2024-06 baseline without Mixtral). CC-BY-4.0 on v0.1.7-v0.1.22, MIT from "v1.1.23" | alternative origins; md5 per zip only |
| Issues | #154 (run errors set security=true), #95/#119 (security=true = attack succeeded), #62 (single run), #150/#202/#219/#220 (LocalLLM parsing, empty answers), #181/#161/#168 (checker defects), #117 (PI-detector bug, absent at `c2748856`), #213 (v1.2 workspace IT6-13) | known defects |

Data-versus-paper notes (from `research.json`):

- P1 benign utility is k/629 (each benign task weighted by its suite's injection-task count, inferred); W uses k/97. P1 Table 5 prints the GPT-4o benign value as 69.07 (k/97) and Table 3 as 69.00.
- W vs paper ASR differs for Command-R+, Gemini-1.5-pro-001, GPT-3.5 and Llama-3-70b by 22/19/12/35 cells, while UA agrees (L-01; tested as H-11, PC-02).
- GPT-4o head ASR: P3 Table 3 47.69 vs Tables 4/5 57.69 (L-03). P1 Table 5 Repeat-prompt benign 73.13 equals Tool filter's; v2/v3 give 85.53 (L-04, copy error).
- Llama-3.3-repeat holds 151 fewer logs than the design (L-05). SA v1 and v2 print different AgentDojo numbers for the same arms (L-06).
- 2024-06 vs head: 4,052 superseded June logs (travel re-runs, Gemini travel fix, Llama update, GPT-3.5 missing task) plus 7 Mixtral logs only at 2024-06 (L-09). Mixtral and claude-3-sonnet-repeat appear in no table (L-08).
- Single run per experiment (#62); identical trajectories across injection tasks reduce the effective n (L-10).

## 3. Expectations

Pre-registration: [`prereg/agentdojo-upstream.md`](prereg/agentdojo-upstream.md), committed in `fd75f8a3` (2026-10-14) before any check of this corpus ran, with an adversarial fact-check (its section 10; corrections: Zenodo licences, 29 later commits, census source of `local_parse_drop_possible`, SA table numbering). Method amendments 1 to 3 (README section 8) apply; amendment 1 covers the stored corpora's `validate.results.differ`.

Hypotheses: H-01 to H-09, H-11 to H-13, H-16, H-17, H-18 and H-20 supported. H-15 supported on the sample only (population count after the round). H-10 refuted on one row (PC-03). H-14 refuted (PC-01). H-19 refuted in its prediction text only: the movement is fully attributed, but section 6 missed three effects (PC-04, PC-05, and PC-06, which is cross-cutting item CC-04).

Classes follow the canonical rules R1-R6 and the cross-cutting items CC-01 to CC-08 of [`cross-cutting.md`](cross-cutting.md) (harmonisation pass 2026-10-15).

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Both parts read from the git pins (`--use-pin`); runs tree ids confirmed in the full-history cache. head 36 s, 2024-06 13 s at jobs 2.

| Check | head | 2024-06 | vs expectation |
|---|---|---|---|
| L1-01 counts | walked 36,679 / selected 36,679 / excluded 0 / rejected 0 / units 36,679; 426,293,413 B. With trajectory 36,472, outcome-only 207 | 18,241 / 18,241 / 0 / 0 / 18,241; 188,873,874 B. With trajectory 18,034, outcome-only 207 | equal to pins, census and registry (H-01). 2024-06 variants: v0.k11 18,237 + incomplete 4 (census counts all 18,241 as v0.k11) |
| L1-02 parse | 36,679/36,679 ok | 18,241/18,241 ok | 0 duplicate keys, non-finite, big ints, lone surrogates, BOM, trailing data, invalid UTF-8, truncation or depth failures |
| L1-03 encodings | 0 U+2028/2029/0085, C0/C1, bidi, tag, zero-width, U+FFFD, mojibake. Residues by design (Python-repr tool output): escaped newline 11,617, escaped quote 1,343, escaped unicode 2,662 of 36,679 artefacts; JSON-in-string 9 (12 strings) | same zeros; 5,541 / 486 / 868 of 18,241; JSON-in-string 5 (6 strings) | as expected (residues in tool arguments = E2 N2, counted here as strings) |
| L1-04 duplicates | 0 byte-identical within part. Trajectory-identical 649 groups / 4,837 units (of 36,472); 598 of the 649 differ only by injection task (payload never read) | 0 byte-identical; 396 groups / 1,948 units (of 18,034) | not comparable with FA's 382/3,612 and 150/816 (FA hashed AER lists with provider call ids; CC-01: both figures are reported, the difference is a tool definition). Cross-part: 14,182 shared (path, blob) pairs (= E2 N1), 12,691 trajectory groups. 2024-06-only blobs 4,059 = 4,052 replaced + 7 Mixtral (H-06 100 %); head-only 22,497 = 10,732 v0.k11 + 11,765 v1.k14. Cross-corpus: 0 byte-identical; 2 trajectory groups with `adprov-v1` (routed) |
| L1-05 arms | 29 directories; every per-dir and per-(dir, attack) count equals prereg section 3 (6,899 / 753 / 1,081 / 2,979 / 2,828 / 40 / 7); `path_must_agree` 0 mismatches. Llama-3.3-repeat important_instructions 798 of 949 (slack 0/105, banking 98/144: 26 whole user tasks + 1 partial); claude-3-sonnet-repeat 40 workspace benign logs only; v1.2 workspace IT6-13 only in the six v1.2 dirs; flash-exp has the 27-task shape | 18 directories; counts equal section 3; Mixtral 7 benign logs over four suites (workspace 3, slack 2, travel 1, banking 1); claude-3-sonnet-repeat 40 | H-02 to H-05 supported (PC-01 for the paper side) |
| L1-06 secrets/paths | 0 account paths, 0 named accounts, 0 operator-home, 0 local-path model ids. Secret-like 1 artefact (generic-credential-assignment, `/messages/*/content`) | same zeros; the same shared blob, 1 artefact | a model-written UUID, not a credential (PC-09) |
| L1-07 timestamps | `/evaluation_timestamp` in 11,765 of 36,679 (all v1.k14); 100 % parse, 100 % naive, 2025-07-24..2025-07-25. Any timestamp pointer 14,933 artefacts; "non-monotone" 90 | 0 of 18,241. Any timestamp pointer 2,303; "non-monotone" 88 | H-17 supported. The other pointers are benchmark calendar data in tool arguments (`start_time`, `end_time`, `date`, ...), so the 90 / 88 non-monotone units are content, not a clock property (one run timestamp per log) |
| L1-08 degenerate | zero_messages 207, error_only 25 (command-r-plus 3 none + 22 important_instructions), incomplete 1, null_final 77, empty/tiny files 0, run errors 105 | 207, 25, 4, 48, 0, 106 | null_final is not the census silent-rerun count (82 / 47). 2024-06's 48 = E2 N4; head misses the 266 local v1.k14 empty-text-block finals (PC-08, CC-08), so H-18 is answered from E2's AER scan |
| L1-09 | does not apply (git trees, no archive members) | n/a | n/a |

Duplicate group counts in this table are the per-part L1 summaries (`l1-head.json`, `l1-2024-06.json`), and this dossier uses them. `data/_cross/l1-xdup.json` counts a group under `within_part` only when all its members are in one part; groups that span parts move to `cross_part` (or `cross_corpus`), so its within-part figures are lower (trajectory groups head 323 vs 649, 2024-06 73 vs 396). A comparison with the post-check must use the same basis.

## 5. Level 2

| Item | head | 2024-06 |
|---|---|---|
| Sample | [`data/agentdojo-upstream/l2-sample-head.json`](data/agentdojo-upstream/l2-sample-head.json): 313 of 36,679, 313 strata `pipeline_dir x attack_dir x suite x variant`, 1 each (`over_maximum`); seed 20261011 | [`data/agentdojo-upstream/l2-sample-2024-06.json`](data/agentdojo-upstream/l2-sample-2024-06.json): 300 of 18,241 over 191 strata |
| Import | scratch `l2-head-j2.partial` and `-j1.partial` at `db6ef512` with the history index. 313/313 mapped; ok 291 / ok_with_issues 22; degenerate 0; failed 0; join 1:1 | 300/300; ok 286 / ok_with_issues 14; 0 / 0; join 1:1 |
| Validation | tiers aer, sem, prov, linkage: 313/313 passed, results reproduced 313, linkage 313/313. SHACL not implemented (skipped); regression n/a | 300/300, 300, 300/300 |
| Recompute | `--dry-run`: 313 identical, 0 unexplained | 300 identical, 0 unexplained |
| Determinism | j2 vs j1: 1,259 files, 0 differ, index identical (first determinism evidence for head) | 1,207 files, 0 differ, index identical |
| Verify chain | 0 failures; only `checksums.absent` (working tree). The prereg's sealed-copy run was not made: README section 4 asks for it only where withholding applies, and this profile has no `[withhold]` table | same |
| A2 | 0 degenerate, 0 adapter_defect, 0 unreadable. Index codes: accounting_unverifiable 312, earlier_attempts_unobservable 312, local_parse_drop_possible 14 (seal 41 occurrences), unexecuted_tool_call 8, incomplete_run 1, no_execution_observed 1. Completeness unverifiable 312 / known_incomplete 1 | 0 / 0 / 0. accounting_unverifiable 296, earlier_attempts_unobservable 298, incomplete_run 4, outcome_imposed_by_runner 3, no_execution_observed 2, retry_passes_inferred 1, unexecuted_tool_call 4. Completeness unverifiable 295 / known_incomplete 5 |
| A3 | 0 dangling, missing or invented relations; unexecuted calls represented 8/8 | 0; 4/4 |
| Evidence classes | core D 10,557 / O 9,790; inference I 45,047; assessment D 991 / I 14,110 / O 626. Non-c6 twins (catalogue test): 169 of 313 executions, exactly the 169 head-only blobs; 0 of the 144 shared (H-15, sample) | core D 20,232 / O 8,723; inference I 25,611; assessment D 1,113 / I 11,634 / O 600. Non-c6 twins 0 of 300 (c6 twins only). The `l2_check` "twin" counter (7,503) over-counts native I rules (PC-07, CC-08) |
| Identity | 22 models, 0 unresolved, 0 mismatches (`local` pipeline resolved by directory) | 13 models, 5 defences, 16 attacks; 0 unresolved, 0 mismatches |
| Redaction | 0 hits in 947 files | 0 hits in 908 files |
| Withholding | no `[withhold]` policy (profile has none): not applicable, as pre-registered | same |
| OS-2 (raw vs mapped) | 0 of 1,226 judgements differ over both parts (613 labels) | |
| DL-1 (stored `*-p10.partial` vs scratch, same 313 / 300 ids) | every AER/SEM/PROV/validation digest differs, as predicted, and every differing pointer is attributed: item 30 (profile @1->@2, rules agentdojo 2, suites@2); item 3 c6 twins (`committed_no_later_than`, `functions_runtime` in all executions; empty_assistant_text 15/15; env actor and tool associations core D -> inference I); items 3 (v1.k14) and 13/D-84 (head-only v0.k11) twins in exactly the 169 head-only executions; item 5/D-370 `load_environment` on 200/200 attacked; item 14/D-87 `/after` -> I in 23 executions; item 17/D-207 system-prompt variant on 248 v0.k11; U6-c/D-373 `/params` not_recorded on 1,354 model calls as `apv:paramsStatus` (PC-06, CC-04); item 9/B2 completeness refresh 1 row (PC-05); suites@2 partial_payload 4 annotations in 3 executions, 0 success_without_visible_payload, 0 marker value changes; D-86/D-84 SEM twins and D-83 propagation (PC-04). 0 unexplained; no held-branch item | same attribution: `load_environment` 176/176; `/after` -> I in 58; system-prompt variant 298; `/params` 1,198/1,198; completeness refresh 3 rows; 0 non-c6 twins. 0 unexplained |

Stored `validate --corpus` on the `*-p10.partial` corpora gives `validate.results.differ`, expected-known under amendment 1 (PC-12, CC-05); not re-run here (optional follow-up, section 10).

### Recheck (CC-08, recheck12)

`plans/recheck12.toml` (l1, l1_10, check; sample frozen) against the d97d3a57 files; full deltas in [`_cross/recheck12.json`](data/_cross/recheck12.json). Every other L1/L2 count is unchanged; the only other deltas are run environment (code commit d97d3a57 with tools/src = 5efa3575, `tracked_changes` true, two H.8.4(2) recompute notices with 0 unexplained changes; R12-01).

| Part | L1-08 flags (old -> new) | L2 `_unverified` split | L1-10 |
|---|---|---|---|
| 2024-06 | `trailing_calls` - -> 145 | twin inference:I 7,503 -> 1,405; mixed 0; native 6,098 (sum 7,503 = old) | 0 screened (-); 0 hits; files with a hit 0; named accounts 0; operator 0; unreadable 0 |
| head | `null_final` 77 -> 343; `trailing_calls` - -> 800 | twin inference:I 35,884 -> 28,888; mixed 4,193; native 2,803 (sum 35,884 = old) | 0 screened (-); 0 hits; files with a hit 0; named accounts 0; operator 0; unreadable 0 |

- PC-07 resolved: native class-I `_unverified` refs now split out (2024-06 native 6,098 of the old 7,503; head native 2,803, mixed 4,193).
- PC-08 resolved: head `null_final` 343 = 77 + 266, as predicted; 2024-06 unchanged (not v1.k14).

## 6. Outcome comparison

L1 is the population recount (OS-1) of the raw utility/security fields. Paper references: W (results page), P1 (arXiv v1), P3 (v3 = v2), SA1/SA2 (Meta SecAlign v1 / v2). Benign utility follows the paper convention (suite-weighted k/629) unless stated. The Wilson 95 % interval is on the pooled k/n. Gap rule (README section 4): more than 15 pp, or more than 5 pp outside the Wilson interval. Full rows: `os1-population.json`, `os2-sample.json`.

| Arm | Level | n | Metric | Rate (Wilson 95 %) | Paper | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|---|
| head, all 28 W rows | L1 | 97 / 629 | utility k/97, UA, ASR | 84 of 84 values equal W | W | 0 | match (H-08) |
| head gpt-4o-2024-05-13 important_instructions | L1 | 629 | ASR | 47.69 (300/629) [43.82, 51.60] | P3 T3 47.69 (T4/T5 57.69) | 0.00 | match (H-12; paper-internal conflict L-03) |
| head command-r-plus important_instructions | L1 | 629 | ASR | 4.45 [3.10, 6.36]; 0.95 excl. 22 run errors | P3 0.95 | +3.50 raw / 0 excl. | match after exclusion (PC-02) |
| head gpt-3.5-turbo-0125 important_instructions | L1 | 629 | ASR | 10.33 [8.19, 12.96]; 8.43 excl. 12 | P3 8.43 | +1.90 / 0 | match after exclusion (PC-02) |
| head gemini-1.5-pro-001 important_instructions | L1 | 629 | ASR | 28.62 [25.22, 32.27]; 25.60 excl. 19 | P3 25.60 | +3.02 / 0 | match after exclusion (PC-02) |
| head Llama-3-70b-chat-hf important_instructions | L1 | 629 | ASR | 25.60 [22.34, 29.15]; 20.03 excl. 35 | P3 20.03 | +5.57 / 0 | within rule; match after exclusion (PC-02) |
| head, P3 14 rows (10 models + 4 defences) | L1 | 629 | benign utility, UA | 28 of 28 within 0.1 pp | P3 Tables 3/5 | <= 0.07 | match (H-09) |
| 2024-06 gpt-4o-2024-05-13 important_instructions | L1 | 629 | ASR | 53.10 (334/629) [49.19, 56.97] | P1 53.10 | 0.00 | match |
| 2024-06 gemini-1.5-pro-001 important_instructions | L1 | 629 | UA | 27.50 (173/629) [24.16, 31.12] | P1 29.61 | -2.11 | within rule; no k/629 gives 29.61 (PC-03) |
| 2024-06 gemini-1.5-pro-001 important_instructions | L1 | 629 | ASR | 31.48 [27.97, 35.21]; 28.30 excl. 20 | P1 27.50 (= raw UA) | +3.98 / +0.80 | within rule; not explained by run errors (PC-03) |
| 2024-06 Llama-3-70b-chat-hf important_instructions | L1 | 629 | ASR | 20.67 [17.69, 24.01]; 15.10 excl. 35 | P1 15.10 | +5.57 / 0 | within rule; match after exclusion (PC-02) |
| 2024-06 command-r-plus important_instructions | L1 | 629 | ASR | 4.61 [3.23, 6.54]; 0.95 excl. 23 | P1 0.95 | +3.66 / 0 | match after exclusion (PC-02) |
| 2024-06 command-r-plus none | L1 | 97 | benign utility | 28.78 [19.89, 37.47] | P1 27.78 | +1.00 | within rule; probable paper typo (PC-03) |
| 2024-06 gpt-4o repeat_user_prompt none | L1 | 97 | benign utility | 85.53 [76.04, 90.40] | P1 73.13 (copy error; v3 85.53) | +12.40 | within rule; known copy error (H-13) |
| 2024-06 gpt-4o ablations (5) and direct / ignore_previous / injecagent | L1 | 629 each | ASR | 45.79 / 23.21 / 25.12 / 49.76 / 44.36; 3.66 / 5.41 / 5.72 | P1 Tables 2/4 | <= 0.04 | match |
| head Meta-SecAlign-70B-repeat important_instructions | L1 | 949 | UA | 80.08 (760/949) [77.42, 82.50] | SA1 72.3 (SA2 79.5) | +7.78 (SA2 +0.58) | gap vs SA1; match vs SA2 (PC-01) |
| head Meta-SecAlign-70B-repeat none | L1 | 97 | utility | 85.57 (83/97) [77.22, 91.20] | SA2 84.5 (SA1 77.3) | +1.07 | match vs SA2 |
| head Meta-SecAlign-70B-repeat important_instructions | L1 | 949 | ASR | 2.11 (20/949) [1.37, 3.23] | SA2 1.9 | +0.21 | match |
| head Llama-3.3-70B-Instruct-repeat important_instructions | L1 | 798 (slack absent) | ASR | 9.02 (72/798) [7.23, 11.21] | SA2 14.7 (n 949) | -5.68 | within rule; different suite mix (PC-01) |
| head Llama-3.3-70B-Instruct-repeat important_instructions | L1 | 798 | UA | 39.47 (315/798) [36.14, 42.91] | SA2 43.4 (SA1 39.0) | -3.93 | within rule (PC-01) |
| head Llama-3.3-70B-Instruct none | L1 | 97 | utility | 57.73 (56/97) [47.79, 67.08] | SA2 62.9 (SA1 55.7) | -5.17 | within rule; unexplained 5 tasks (PC-01) |
| head Llama-3.3-70B-Instruct important_instructions | L1 | 949 | ASR | 23.08 (219/949) [20.51, 25.86] | SA2 23.0 | +0.08 | match |
| head Meta-SecAlign-70B important_instructions | L1 | 949 | UA / ASR | 77.98 [75.23, 80.50] / 2.21 | SA2 77.1 / 2.3 | +0.88 / -0.09 | match |
| head pooled important_instructions, 753-type dirs | L2 | 88 | UA | 43.18 [33.33, 53.60] | W sample-weighted 42.24 | +0.94 | match |
| head pooled important_instructions, 753-type dirs | L2 | 88 | ASR | 20.45 [13.35, 30.03] | W sample-weighted 20.37 | +0.08 | match |
| head pooled important_instructions, six v1.2 dirs | L2 | 24 | ASR | 16.67 [6.68, 35.85] | population strata 15.26 | +1.41 | match |
| head gpt-4o base dir, all attacks | L2 | 60 | ASR | 25.00 [15.78, 37.23] | population strata 32.65 | -7.65 | within rule |
| 2024-06 pooled important_instructions, P1 dirs | L2 | 96 | UA | 41.67 [32.31, 51.66] | P1 sample-weighted 39.78 | +1.88 | match |
| 2024-06 pooled important_instructions, P1 dirs | L2 | 96 | ASR | 20.83 [13.91, 30.00] | P1 sample-weighted 21.06 | -0.22 | match |
| 2024-06 gpt-4o base dir, all attacks | L2 | 60 | ASR | 25.00 [15.78, 37.23] | population strata 34.22 | -9.22 | within rule |
| both parts, raw vs mapped on the same labels | L2 | 613 labels | utility and security values | 0 of 1,226 differ | raw L1 fields | 0 | match (mapping faithful) |

The only row flagged by the gap rule is SA1's SecAlign-repeat UA; SA2 reproduces it within 0.58 pp. No gap comes from the mapping (OS-2 0/1,226). No arm is excluded or recommended for exclusion for its attack outcome; the incomplete arms are kept and disclosed (PC-01).

## 7. Findings

12 findings. The 11 examined findings were confirmed by their verifier (0 refuted); PC-12 is the numbered CC-05 finding added in the harmonisation pass. Verifier corrections and the harmonisation entries are in `findings.json` (CC-06 format). Analysis-artefacts (R5: PC-07, PC-08, PC-09, PC-11) are tool or process properties and are not counted in the readiness verdict; PC-06 is a reference to CC-04, which is recorded once in `cross-cutting.md`.

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-agentdojo-upstream-01 | Local-model arms do not reproduce Meta SecAlign's tables (SA1 off, SA2 within 1 pp on UA/ASR for 3 of 4 arms); Llama-3.3-repeat important_instructions has 798 of 949 cells (slack 0/105, banking 98/144) | documentation-mismatch | S2 | confirmed, with correction (benign denominators; cite prereg L-05/L-06, H-03) | Cite SA v2+; disclose the 798-cell arm and the residual 1-5-task benign gaps; keep all four arms; artefact entry below |
| PC-agentdojo-upstream-02 | W vs paper ASR gaps equal the run-error logs scored security=true (head 22/19/12/35; 2024-06 23/20/12/35) | expected-known (R2, `agentdojo.art.run_error_imposed`, 105/106) | S2 | confirmed | ASR statistics state whether `harness_default` judgements (`agentdojo.run_error_imposed_outcome@1`) are included; report both values for these arms |
| PC-agentdojo-upstream-03 | Three P1 rows do not follow from the 2024-06 logs: Gemini-1.5-pro-001 UA 29.61 (no k/629) and ASR 27.50 (= raw UA), Command-R+ benign 27.78 vs 28.78 | documentation-mismatch | S3 | confirmed, with additions (Command-R+ gap exactly 1.00 pp, likely a typo; v1 also prints GPT-4o benign 69.07 vs 69.00) | Cite AgentDojo v3 (= v2) only; disclose the three v1 rows |
| PC-agentdojo-upstream-04 | Head SEM outcome and marker annotations of head-only logs move to class I (D-84 + D-86 twins; D-83 propagation for 47 v1.k14 security outcomes), against the item-1 table and prereg section 6 | documentation-mismatch | S3 | confirmed, wording refined | Correct `regen-batch.md` l. 165 and the prereg row; manuscript head SEM class shares from post-round counts |
| PC-agentdojo-upstream-05 | Prereg section 6 omitted the B2 completeness refresh (vacuous verified_complete -> unverifiable: head 1/1, 2024-06 3/3) | documentation-mismatch | S3 | confirmed, with qualifier | Post-check: 2024-06 0 / 51 / 18,190; head 0 / 47 / 36,632, the 47 to be confirmed on the population (no retry row in the head sample) |
| PC-agentdojo-upstream-06 | [CC-04] reference: U6-c is `apv:paramsStatus apv:NotRecorded` (1,354/1,354 and 1,198/1,198 model calls), not one `apv:Gap` per call; engine follows spec E.4.5 | documentation-mismatch (CC-04) | S3 | confirmed, evidence uses the direct count | See CC-04: one `regen-batch.md` U6-c correction for agentdojo-upstream, ast-survey-agentdojo, rope and mandate-agentdojo-eval (regen-batch owner); not counted as a separate corpus finding |
| PC-agentdojo-upstream-07 | [CC-08] `l2_check` counts native class-I rules (`auto_execution_unverified`, `checker_inputs_unverified`) as twins: 4,993 of the 7,503 at 2024-06 | analysis-artefact (CC-08) | S3 | confirmed | Tool owner after the batch: count twins from the catalogue, report native-I and twin-backed separately |
| PC-agentdojo-upstream-08 | [CC-08] L1 `null_final` misses all-empty text-block finals of v1.k14 logs (head 77 vs E2 343; 266 local missed) | analysis-artefact (CC-08) | S3 | confirmed, wording refined | Tool owner after the batch: "all text blocks empty AND no tool_calls"; re-run head L1 (expect 343) |
| PC-agentdojo-upstream-09 | The one L1-06 secret-like hit (same shared blob in both parts) is a model-written UUID in the final answer, not a credential | analysis-artefact | S3 | confirmed | No action; optionally let the generic rule skip UUID-shaped values (follow-up, tool frozen) |
| PC-agentdojo-upstream-10 | Licence basis "MIT by repository" does not hold for the 2024-06 pin as such (no LICENSE at `c2748856`; Zenodo 12742856 declares CC-BY-4.0) | documentation-mismatch | S3 | confirmed; softened (the 2024-06 `runs/` tree is unchanged at `bd533515`, so MIT covers it there) | Family owner extends the profile basis text (proposed wording in `findings.json`) |
| PC-agentdojo-upstream-11 | Shared session scratchpad: examiner scripts overwrote each other; all results re-run from a private copy | analysis-artefact | S3 | confirmed | Per-corpus scratch directories for examiners; each examiner re-checks committed outputs against its `exam-scripts/` copy |
| PC-agentdojo-upstream-12 | [CC-05] Stored corpora `agentdojo-upstream-{head,2024-06}-p10.partial` give `validate.results.differ` (rows predate regen item 10's `pv.constraints.*` checks) | expected-known (CC-05) | S3 | added in the harmonisation pass; evidence is the amendment-1 proof, not re-run here | None before the round; compare like with like after re-validation (amendment 1) |

Refuted: none.

Proposed `artefacts.toml` entry (text only; route to the agentdojo family owner; denominators corrected by the verifier):

```toml
[[artefact]]
id = "agentdojo.art.incomplete_arm"
title = "Published arms with fewer cells than the benchmark design"
description = "meta-llama_Llama-3.3-70B-Instruct-repeat_user_prompt / important_instructions has 798 of 949 cells (slack 0/105; banking 98/144, user_task_10 partial and 26 whole user tasks absent); direct and ignore_previous are complete. claude-3-sonnet-20240229-repeat_user_prompt is benign-only and workspace-only (40 logs = all 40 workspace benign tasks; a complete dir holds 124 benign logs). mistralai_Mixtral-8x7B-Instruct-v0.1 (2024-06 only) is 7 benign logs over four suites. Rates over these arms cover a different suite mix than the papers' n."
scope = { sources = ["agentdojo"], parts = ["head", "2024-06"], profiles = ["agentdojo-upstream"] }
cause = "upstream_harness"
detector = { rule = "artefact.generic.arm_coverage (proposed)", class = "D" }
claims = []
recorded_as = { notes = ["stats:arm_cells"] }
handling = { class = "FO" }
expected = [{ snapshot = "head", count = 151, unit = "missing cells", basis = "precheck L1-05 2026-10-14", status = "verified" }, { snapshot = "head", count = 40, unit = "executions", basis = "precheck L1-05 (claude-3-sonnet-repeat)", status = "verified" }, { snapshot = "2024-06", count = 40, unit = "executions", basis = "precheck L1-05 (claude-3-sonnet-repeat)", status = "verified" }, { snapshot = "2024-06", count = 7, unit = "executions", basis = "precheck L1-05 (Mixtral)", status = "verified" }]
manuscript = true
refs = ["docs/reports/precheck/prereg/agentdojo-upstream.md (L-05, L-06, L-08, H-03, H-04)", "arXiv:2507.02735 v2 Tables III/IX"]
```

Items for AGENTS.md section 12:

- PC-01: the head local-model arms back Meta SecAlign v2 (not v1); Llama-3.3-repeat important_instructions has 798 of 949 cells. `agentdojo.art.incomplete_arm` is pending with the family owner. All arms kept.
- PC-02: corpus ASR for command-r-plus, gemini-1.5-pro-001, gpt-3.5-turbo-0125 and Llama-3-70b equals the results page only when `harness_default` run-error judgements are included; the papers exclude them. Statistics must say which convention they use.
- PC-04: after the round, head SEM outcome and marker annotations of head-only logs are class I (D-84/D-86, D-83 propagation); the item-1 table's "head stays D" is wrong.

## 8. Recommendations and readiness

1. Route `agentdojo.art.incomplete_arm` and the licence basis text (PC-10) to the agentdojo family owner. Datasheet notes for PC-01, PC-02 and PC-03 (cite AgentDojo v3 and Meta SecAlign v2+; give both ASR conventions).
2. Correct `docs/reports/analysis/regen-batch.md`: item-1 table row (PC-04); U6-c PROV wording (PC-06, routed once for four corpora under CC-04). Post-check expectations for this corpus: completeness 2024-06 0 / 51 / 18,190, head 0 / 47 / 36,632 (PC-05); `apv:paramsStatus` per model call, no new `apv:Gap` (PC-06, CC-04); head SEM class shares from the regenerated corpus (PC-04).
3. After the round: re-run `exam-scripts/dl1.py` on the regenerated corpora with the same ids and count H-15 over the population (expect 22,497 head-only executions citing twins, 0 shared).
4. Tools, after the batch freeze (CC-08): fix `l2_check` twin counting (PC-07) and `null_final` (PC-08), then re-run head L1 and `l2_check` for both parts for corrected baselines (section 10).
5. Route the 2 cross-corpus trajectory groups to the adprov-v1 examiner. Give examiners per-corpus scratch directories (PC-11).
6. No exclusion of any data: incomplete, benign-only and zero-success arms are kept.

**Readiness: `ready-with-caveats`.**

- Both parts import correctly and deterministically: validation 313/313 and 300/300; recompute 0 unexplained; j1/j2 byte-identical (first determinism evidence for head); DL-1 0 unexplained pointers and no held-branch item; OS-2 raw = mapped (0 of 1,226 differ); all 28 W rows and 25 of 27 P3/P1 rows reproduce, the rest explained or attributed to the papers.
- Caveats, all owned and routed: the S2 disclosures PC-01 and PC-02 and the artefact entry (family owner); documentation corrections PC-04/05 and the CC-04 reference PC-06 (regen-batch owner, post-check); H-15 population count after the round; stored-corpus `validate.results.differ`, expected-known under amendment 1 (PC-12, CC-05).
- Not counted (R5, analysis-artefacts): tool fixes PC-07/08 (CC-08, after the freeze), PC-09, PC-11.
- None of these means the data cannot be imported correctly.

## 9. Reproduction

Batch (wave 1; plan entries in `tools/precheck/plans/wave1.toml`):

```toml
[[part]]
corpus_id = "agentdojo-upstream"
source = "agentdojo"
part = "2024-06"
l1 = ["--use-pin"]

[[part]]
corpus_id = "agentdojo-upstream"
source = "agentdojo"
part = "head"
l1 = ["--use-pin"]
```

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave1 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave1.toml
```

Steps the batch ran per part P in {head, 2024-06}. W = `~/.agentprov/migration-work/precheck/agentdojo-upstream`, D = `docs/reports/precheck/data/agentdojo-upstream`:

```bash
uv run python tools/precheck/l1_scan.py --source agentdojo --part P --corpus-id agentdojo-upstream --jobs 2 --emit-fp --use-pin
uv run python tools/precheck/l2_sample.py select --units W/l1-units-P.jsonl --source agentdojo --part P --corpus-id agentdojo-upstream --out D/l2-sample-P.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-P.json --corpus W/l2-P-j2 --source agentdojo --part P --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-P.json --corpus W/l2-P-j1 --source agentdojo --part P --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-P-j2.partial --out D/l2-P.json --sample D/l2-sample-P.json --l1-units W/l1-units-P.jsonl --compare-with W/l2-P-j1.partial --jobs 2
# inside l2_check:
uv run agentprov validate --corpus W/l2-P-j2.partial --tiers aer,sem,prov,linkage,shacl,regression --jobs 2
uv run agentprov recompute --corpus W/l2-P-j2.partial --dry-run --jobs 2 -q
uv run agentprov verify --corpus W/l2-P-j2.partial --level chain
```

Examiner and verifier scripts (read-only; from the worktree root):

```bash
uv run python -I D/exam-scripts/pop.py <pop.json>                 # OS-1 / L1-05 population recount
uv run python -I D/exam-scripts/os1.py <pop.json> <out>           # OS-1 vs W/P1/P3/SA1/SA2, gap rule (PC-01..03)
uv run python -I D/exam-scripts/os2.py <out>                      # OS-2 raw vs mapped
uv run python -I D/exam-scripts/os2b.py <out>                     # pooled L2 rates
uv run python -I D/exam-scripts/dl1.py P <out>                    # DL-1 vs ~/.agentprov/corpora/agentdojo-upstream-P-p10.partial (PC-04..06)
uv run python -I D/exam-scripts/bundles.py P; uv run python -I D/exam-scripts/afterpos.py P   # bundle and /after moves
uv run python -I D/exam-scripts/exam_build.py                     # builds D/exam.json
```

Follow-ups for the orchestrator: section 10.

Process note: the session scratchpad was shared by parallel examiners (PC-11). All agentdojo-upstream results were re-run from a private copy; `exam-scripts/` holds those copies (path-cleaned).

## 10. Open follow-ups

Not run in the harmonisation pass (they need a re-run, a tool fix or the round). W and D as in section 9.

| # | What | Command | When |
|---|---|---|---|
| 1 | CC-08 / PC-08: re-run head L1 after the `null_final` fix (expect null_final 343 = 77 + 266) | `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-adu-l1-head -- uv run python tools/precheck/l1_scan.py --source agentdojo --part head --corpus-id agentdojo-upstream --jobs 2 --emit-fp --use-pin` | after the tool fix lands (chain drained) |
| 2 | CC-08 / PC-07: re-run `l2_check` for both parts after the twin-counting fix (native-I and twin-backed counted separately) | `uv run python tools/precheck/l2_check.py --corpus W/l2-P-j2.partial --out D/l2-P.json --sample D/l2-sample-P.json --l1-units W/l1-units-P.jsonl --compare-with W/l2-P-j1.partial --jobs 2` for P in head, 2024-06 (through `tools/suite_queue.py --class import --cpu 2 --label precheck-adu-l2check`) | after the tool fix lands |
| 3 | H-15 over the population (expect 22,497 head-only executions citing twins, 0 shared) and DL-1 on the same ids | `uv run python -I D/exam-scripts/dl1.py P <out>` with old = the stored `agentdojo-upstream-P-p10.partial`, new = the regenerated corpus | after the round |
| 4 | CC-05 / PC-12, optional: show `validate.results.differ` on the stored corpora directly | `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-adu-validate -- uv run agentprov validate --corpus ~/.agentprov/corpora/agentdojo-upstream-head-p10.partial` (and the 2024-06 twin) | optional, any time |
| 5 | Route the 2 cross-corpus trajectory groups to the adprov-v1 examiner (covered there by PC-adprov-v1-05) | no command | done by routing |
