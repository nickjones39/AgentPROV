# Pre-check dossier: `melon-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `melon-agentdojo` (MIT at the pin; the LICENSE is the upstream AgentDojo text, no fork copyright line, no data licence; the MELON detector code derives from `kaijiezhu11/MELON`, which has no licence) |
| Parts | `melon-agentdojo · head` (1 part) |
| Family / profile | `agentdojo` / `melon-agentdojo@1` (dialect `agentdojo.tracelogger`, semantics `agentdojo.suites@2`, variants `v1.k14` / `v1.k14.incomplete`) |
| Pin | git `xwsdid/MELON` @ `71d99dff` (2026-06-17, = HEAD of main); tree 38,780 entries, 3 absent blobs (report binaries); 36,679 upstream AgentDojo copies are `select.owned_elsewhere:agentdojo` |
| Code commit | L1 `f7d7eced`; L2 `cb0af3d8` (batch `wave2`, all steps rc 0, no tracked changes) |
| Kind | wave 2, first examination (not in FA or E2); no stored corpus |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (L1, L2, examination, verification, dossier) |
| Agents | researcher and fact-checker (prereg, research), examiner (L1/L2 analysis), verifiers (one per finding, two for PC-03 and PC-04: 13 verdicts), dossier writer |
| Data | [`data/melon-agentdojo/`](data/melon-agentdojo/): `research.json`, `l1-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `os1-population.json`, `os2-sample.json`, `defence-content.json`, `cc07.json` (CC-07 #181/#161 on the whole population), `findings.json`, `exam-scripts/` |

- Code identity, part `head` ([`code-head.json`](data/melon-agentdojo/code-head.json)): commit `cb0af3d8`; engine code aer `24df84b5e307`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `d3f9995f61bf`; adapter `agentdojo.tracelogger@0.1.0` `c311b5a6ac9e`; profile sha256 `9757a714918c`, rules agentdojo 2 / aer 1.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Source repository | https://github.com/xwsdid/MELON @ `71d99dff` (not a GitHub fork; carries AgentDojo history to `18b501a6`; 0 issues, releases, PRs) | the data (`runs/*-melon*`, 9 pipeline dirs) |
| Own commits | `605d9999` (adds the runs, `runs/detection_stats.json`, `report/`, README); `71d99dff` (only `pi_detector.py`: comments and strings translated, no behaviour change) | data origin |
| Fork report | README "experiment results" and `report/MELON_SATM_AT_补充内容.md` (course project, Chinese) | the only description and outcome reference (sections 6.2.1, 6.3.1, summary) |
| MELON paper | https://arxiv.org/abs/2502.05174 (ICML 2025; v1-v4) | builds_on only; no MELON-R/SM/AT and no banking-only numbers; its runs are not here |
| Original MELON code | https://github.com/kaijiezhu11/MELON (no licence) | origin of the detector |
| AgentDojo | https://arxiv.org/abs/2406.13352; vendored `agentdojo` 0.1.35, benchmark `v1.2.2` in all 1,911 logs | benchmark, harness, scorer |
| Upstream issues | ethz-spylab/agentdojo #181, #161, #139, #189, #214 | banking checker defects (CC-07), proposed-call scoring, `\uXXXX` escapes |

Data-versus-paper notes (from `research.json`, checked against the data):

- The README and report label all results GPT-4o, but 904 of 1,911 logs are `gpt-4o-mini-2024-07-18`; the report's note 3 says the docx named GPT-4o-mini as the base model. Two README GPT-4o rows equal gpt-4o-mini cells exactly (PC-01).
- 4 README GPT-4o cells have 0 logs and 2 are partial (65/144, 13/144); there is no undefended run (PC-02).
- Not all runs were made with committed code: the `melon_r` RECOVERY text in the logs is the first 5 of the 6 lines at the pin, and `melon_rp` is not in the pin's `DEFENSES` list (16 logs from uncommitted code).
- The base MELON class writes a defence-authored assistant stop message on detection; MELON-R writes BLOCK messages, RECOVERY system inserts and sanitised tool outputs (PC-03, PC-04, PC-05).
- `runs/detection_stats.json` is the only committed detector artefact; `defense_logs.jsonl` is not committed (PC-07).

## 3. Expectations

Pre-registration: [`prereg/melon-agentdojo.md`](prereg/melon-agentdojo.md), committed in `fd75f8a3` (2026-10-14), before any check of this corpus ran. Amendments 2 to 4 of README section 8 apply (amendment 1 does not: no stored corpus). Classes follow R1-R6 and CC-01 to CC-11 of [`cross-cutting.md`](cross-cutting.md) (wave-2 harmonisation pass 2026-10-15: CC-07 #181/#161 added as PC-12/PC-13, CC-09 for the scope gap, CC-01 and CC-08 as analysis-artefacts).

Hypotheses H1 to H16: 11 supported (H6 with PC-06), 5 refuted in whole or part (H4 third clause, H7, H11 mapping clause, H13, H15).

| H | Result | Note |
|---|---|---|
| H1 | supported | 1,911 selected; 9 dirs and 29 strata = prereg section 3; walked 38,780 |
| H2 | supported | 1,911/1,911 strict ok; auxiliary ok |
| H3 | supported | 0 U+FFFD, 0 mojibake; CJK in message content only in `*-melon_r` / `*-melon_rp` |
| H4 | refuted (third clause; explained) | 0 byte-identical; 145 trajectory-identical groups span defences (126) and models (12), all runs cut short by the defence or never reaching the payload (PC-08, CC-01) |
| H5 | supported | 4 README cells with 0 logs, 2 partial, no undefended arm (PC-02) |
| H6 | supported | 12 UA/ASR + 2 BU values exact under k/144; two ASR cells 1 run off when the incomplete log is excluded (PC-06) |
| H7 | refuted | README "GPT-4o" MELON and MELON-R ignore_previous = gpt-4o-mini cells (PC-01) |
| H8 | supported | L1-06 0 in 1,911 + 1; L2 redaction 0 hits in 410 files |
| H9 | supported | 1,911 naive, 2026-05-24..06-16, none after the pin |
| H10 | supported | 6 incomplete, 0 empty, 0 error-only |
| H11 | refuted (mapping clause) | data clauses hold; L2 maps the stop message as model output (PC-03) and the RECOVERY insert as the system prompt (PC-04) |
| H12 | supported | 910 sentinel redactions in 910 logs, 0 in the 88 pre-passes |
| H13 | refuted | sanitise marker in 120 tool messages / 101 logs, not 7; second marker in 4 (PC-05) |
| H14 | supported | 134/134 every stage ok; recompute 0; j2 = j1; identity 100 % |
| H15 | refuted | `detection_stats.json` 215 events, melonsm only, TP 0 (PC-07) |
| H16 | supported | all 14 sampled gpt-4o melon_sm/melon_at cells contain the README value in Wilson 95 % |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: the staged bare clone at the pin (`--git`). Batch `wave2`, L1 2.0 s at `f7d7eced`, rc 0.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 38,780 walked (= profile `expected_files`) = 1,911 selected + 36,679 `owned_elsewhere:agentdojo` + 182 not selected + 5 context + 3 absent blobs; rejected 0. Units 1,911 (= registry, census); auxiliary 1 (`runs/detection_stats.json`, parse ok) | as expected (H1) |
| L1-02 parse | strict ok 1,911/1,911, 0 in every class; auxiliary 1/1 | as expected (H2) |
| L1-03 encodings | 0 U+2028/2029/0085, C0/C1, bidi, tag, zero-width, U+FFFD, mojibake. Escaped newline 27 strings in 27/1,911 at `/messages/*/content/*/content` (Python-repr tool output, by design). CJK only in `*-melon_r` / `*-melon_rp` | as expected (H3) |
| L1-04 duplicates | byte-identical 0 within part, 0 cross-corpus. Trajectory-identical (CC-01 fingerprint): 145 groups / 1,086 of 1,911 units (970 distinct fp); one user task and one outcome per group; 126 span defences, 36 attacks, 12 both models (all 5- or 7-message stop-sentinel runs). `_cross/l1-xdup.json`: within part 142; cross-corpus 5 groups, same model and task (interbolt 4; glitch + mandate 1). No copied runs | H4 third clause refuted, explained (PC-08) |
| L1-05 arms | 29 strata, all = prereg section 3. Against the README design (gpt-4o banking, 4 defences × 3 attacks × 144): 6 cells complete (melon_sm, melon_at), 4 cells 0 logs, 2 partial (melon direct 65/144, melon_r direct 13/144), no undefended arm. Extra cells kept: gpt-4o-mini 904 logs, melon_rp 16, travel 17 | H5 supported (PC-02) |
| L1-06 secrets/paths | 0 secret-like, 0 account paths, 0 named accounts, 0 operator home, 0 local-path model ids (of 1,911 + 1). Critic screen of the 5 non-JSON context artefacts (outside L1-06, which reads JSON only; same patterns): 0 account paths; 1 `generic-credential-assignment` shape in `README.md` (line 49), a length withheld placeholder of the "your ... here" form, not a credential | as expected (H8) |
| L1-07 timestamps | `/evaluation_timestamp` 1,911/1,911, all parse, all naive, 2026-05-24..2026-06-16, 0 non-monotone. The 125 May logs are exactly the gpt-4o melon/melon_r/melon_rp dirs (74 + 35 + 16); `duration` absent in 3 | as expected (H9) |
| L1-08 degenerate | incomplete 6 (outcome keys absent; 4 end on a tool message, 2 on the user message); empty 0; error-only 0; `null_final` 0 under both the old and the CC-08 rule | as expected (H10) |
| L1-09 | n/a (git tree, no archive) | — |
| Outcome fields | utility T 904 / F 1,001 / absent 6; security T 125 / F 1,780 / absent 6 | = census |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`data/melon-agentdojo/l2-sample-head.json`](data/melon-agentdojo/l2-sample-head.json) (sha256 `260f03f99438...`): 134 of 1,911 units, 29 strata × 5 (strata of 1, 1 and 2 taken whole), seed 20261011 |
| Import | j2 and j1 at `cb0af3d8`: mapped 134, filtered 1,777, excluded 36,679, failed 0, degenerate 0; sealed clean 131, sealed with issues 3 (`incomplete_run`); join 134/134 1:1 |
| Validation | tiers aer, sem, prov, linkage: 134/134 pass, 134 reproduced, linkage 100 %; SHACL not implemented (skipped); regression n/a |
| Recompute | `--dry-run` (shim): 134 identical, 0 unexplained |
| Verify chain | only `checksums.absent` (working-tree partial) |
| Determinism | j2 vs j1: 548 files, 0 differ, index identical |
| A2 error classes | 0 degenerate, 0 `adapter_defect`, 0 unreadable, 0 failing checks. Index codes `accounting_unverifiable` 133, `earlier_attempts_unobservable` 134, `incomplete_run` 3; completeness unverifiable 131 / known incomplete 3 |
| A3 PROV issues | `l2_check` flags 0 over 51,988 statements. Not caught by A3: the 34 sampled base-MELON stop messages carry a class-I `generated_by` from the model call that the pinned code contradicts (PC-03) |
| Defence content | Sentinel redactions 34/34 sampled = `def0` redact decisions (correct). Stop message mapped as agent output `generated_by` the model call 34/34 (PC-03). RECOVERY text at index 0 mapped as the bench system prompt, variant `melon_r_prompt`, 3/3; the real default prompt then has `/actor` not recorded 3/3; 129-char inserts actor none 8/8 (PC-04). Sanitised tool outputs mapped as plain env tool output (PC-05). 3 BLOCK messages not sampled |
| Evidence classes | core D 623 (engine rules only: `aprov.n_gap` 489, `aprov.n_capture_profile` 134) / O 2,874 / none 294; inference I 13,714 / none 1,337; assessment I 2,944 / O 268 / none 1,932; top O 23,938. Family D rules native only where they read logged bytes (`system_prompt_variant_digest` 134, `incomplete_run` 3); all others via `_unverified` twins. Twin counts after recheck12 (CC-08, `l2-head.json`): twin assessment I 1,858, inference I 11,155, inference none 1,203; mixed inference I 1,766; native 0. Verifier recount (PC-11): twin inference I 12,352 / none 531, native inference I 569 / none 672; totals agree, the split does not (R12-02, open) |
| Identity | model, defence, attack, suite 134/134 resolved, 0 mismatches; `melon_rp` resolves by suffix |
| Judgements (OS-2) | raw = mapped on 131 complete labels (0 of 262 differ); 3 incomplete labels have no judgement in raw or AER; security origin checker 79, harness_default 52 (pre-pass constant) |
| Redaction | 410 files scanned, 0 hits |
| Withholding | policy null; inert as pre-registered |

### Recheck (CC-08, recheck12)

`plans/recheck12.toml` (l1, l1_10, check; sample frozen) against the d97d3a57 files; full deltas in [`_cross/recheck12.json`](data/_cross/recheck12.json). Every other L1/L2 count is unchanged; the only other deltas are run environment (code commit d97d3a57 with tools/src = 5efa3575, `tracked_changes` true, two H.8.4(2) recompute notices with 0 unexplained changes; R12-01).

| Part | L1-08 flags (old -> new) | L2 `_unverified` split | L1-10 |
|---|---|---|---|
| head | no change | twin inference:I 12,921 -> 11,155; mixed 1,766; native 0 (sum 12,921 = old) | 4 screened (context 4); secret:generic-credential-assignment 1; files with a hit 1; named accounts 0; operator 0; unreadable 0 |

- PC-11: twin I 11,155, mixed 1,766, native 0; twin inference:none 1,203. **Disagrees with the verifier recount** (twin I 12,352 / none 531, native I 569 / none 672): totals match (I 12,921; none 1,203), the split does not; the tool puts the 672 none-class statements under twin. Unexpected, see R12-02.
- L1-10: 1 `generic-credential-assignment` in 1 of 4 screened files = the README placeholder the critic screened (critic screened 5 files).

## 6. Outcome comparison

Level 1 is the population (raw booleans); reference is the fork README / report at the pin. Gap rule: > 15 pp, or > 5 pp outside the Wilson 95 % interval (n ≥ 20). UA = utility under attack, ASR = security true. Incomplete logs excluded from n unless stated. Full rows: [`os1-population.json`](data/melon-agentdojo/os1-population.json), [`os2-sample.json`](data/melon-agentdojo/os2-sample.json).

| Arm (gpt-4o banking unless stated) | Level | n | Rate (k) | Wilson 95 % | Paper | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|---|
| melon_sm direct | L1 | 144 | UA 52.08 (75) / ASR 0.00 | [43.98, 60.08] / [0.00, 2.60] | 52.08 / 0.00 | 0.00 / 0.00 | match |
| melon_sm important_instructions | L1 | 143 | UA 33.57 (48) / ASR 1.40 (2) | [26.35, 41.65] / [0.38, 4.96] | 33.33 / 2.08 | +0.24 / −0.68 (0 as k/144: 48, 3) | match (PC-06); #181 1 of 2, #161 9 of 9 UT5 (PC-12, PC-13) |
| melon_sm ignore_previous | L1 | 144 | UA 52.78 (76) / ASR 0.00 | [44.66, 60.75] / [0.00, 2.60] | 52.78 / 0.00 | 0.00 | match |
| melon_sm none (pre-pass) | L1 | 9 | BU 88.89 (8) | [56.50, 98.01] | 88.89 | 0.00 | match |
| melon_at direct | L1 | 144 | UA 62.50 (90) / ASR 0.00 | [54.36, 69.99] / [0.00, 2.60] | 62.50 / 0.00 | 0.00 | match |
| melon_at important_instructions | L1 | 143 | UA 43.36 (62) / ASR 12.59 (18) | [35.51, 51.55] / [8.11, 19.02] | 43.06 / 13.19 | +0.30 / −0.60 (0 as k/144: 62, 19) | match (PC-06); #181 3 of 18, #161 9 of 9 UT5 (PC-12, PC-13) |
| melon_at important_instructions, #181 GOAL-datum re-score (info) | L1 | 143 | ASR 10.49 (15) | [6.46, 16.59] | 13.19 | −2.70 | not the logged metric (PC-12); precedence-only 8.39 (12) [4.87, 14.09] |
| melon_sm important_instructions, #181 GOAL-datum re-score (info) | L1 | 143 | ASR 0.70 (1) | [0.12, 3.85] | 2.08 | −1.38 | not the logged metric (PC-12); precedence-only the same |
| melon_at / melon_sm important_instructions, without vacuous UT5 (info) | L1 | 143 | UA 37.06 / 27.27 | — | 43.06 / 33.33 | −6.00 / −6.06 | not the logged metric (PC-13; denominator kept) |
| melon_at ignore_previous | L1 | 144 | UA 60.42 (87) / ASR 0.00 | [52.26, 68.03] / [0.00, 2.60] | 60.42 / 0.00 | 0.00 | match |
| melon_at none (pre-pass) | L1 | 9 | BU 100.00 (9) | [70.09, 100.00] | 100.00 | 0.00 | match |
| melon direct (65 of 144 logs) | L1 | 64 | UA 60.94 (39) | [48.69, 71.94] | 38.19 (55/144) | +22.75 | **flagged** (PC-02) |
| melon direct | L1 | 64 | ASR 0.00 | [0.00, 5.66] | 0.00 | 0.00 | match |
| melon_r direct (13 of 144) | L1 | 13 | UA 84.62 (11) | [57.77, 95.67] | 45.83 (66/144) | +38.79 (outside by 11.94) | **flagged** (PC-02) |
| melon_r direct | L1 | 13 | ASR 0.00 | [0.00, 22.81] | 2.08 | −2.08 | covered |
| README "GPT-4o" MELON ignore_previous vs **gpt-4o-mini** melon ignore_previous | L1 | 144 | UA 37.50 (54) / ASR 0.00 | [30.01, 45.64] / [0.00, 2.60] | 37.50 / 0.00 (0 gpt-4o logs) | 0.00 on another model's cell | **flagged** (PC-01) |
| README "GPT-4o" MELON-R ignore_previous vs **gpt-4o-mini** melon_r ignore_previous | L1 | 144 | UA 43.06 (62) / ASR 2.78 (4) | [35.25, 51.22] / [1.09, 6.92] | 43.06 / 2.78 (0 gpt-4o logs) | 0.00 on another model's cell | **flagged** (PC-01) |
| No Defense direct | L1 | 0 | no fork log; upstream gpt-4o banking copy 70.14 / 11.81 (101, 17 of 144) | — | 43.06 / 55.56 | unbacked | **flagged** (PC-02) |
| melon important_instructions, ignore_previous; melon_r important_instructions, ignore_previous | L1 | 0 | 0 gpt-4o logs | — | 29.86/0.00, 37.50/0.00, 44.44/8.33, 43.06/2.78 | unbacked (ignore rows: see PC-01) | PC-02 (H5) |
| gpt-4o-mini melon_at direct; ignore_previous | L1 | 144; 144 | UA 34.72 (50) / ASR 2.08 (3); 35.42 (51) / 0.00 | [27.43, 42.80] / [0.71, 5.95]; [28.08, 43.51] / [0.00, 2.60] | none | — | no reference |
| gpt-4o-mini melon_sm direct; ignore_previous | L1 | 144; 144 | UA 38.19 (55) / ASR 4.86 (7); 35.42 (51) / 2.78 (4) | [30.66, 46.34] / [2.37, 9.69]; [28.08, 43.51] / [1.09, 6.92] | none | — | no reference |
| melon_rp direct | L1 | 8 | UA 100.00 (8) / ASR 0.00 | [67.56, 100.00] / [0.00, 32.44] | none | — | no reference |
| all 9 pre-pass arms | L1 | 87 | BU 90.80 (79) | [82.89, 95.27] | only SM 8/9, AT 9/9 | — | covered |
| Sample: gpt-4o melon_sm + melon_at attacked (6 cells × 5) | L2 | 30 | UA 46.67 (14) / ASR 0.00 | [30.23, 63.86] / [0.00, 11.35] | pop. sample-weighted 50.78 / 2.33 | −4.11 / −2.33 | covered (R6) |
| Sample: all attacked | L2 | 79 | UA 54.43 (43) / ASR 2.53 (2) | [43.50, 64.95] / [0.70, 8.77] | pop. sample-weighted 53.36 / 1.68 | +1.07 / +0.85 | covered |
| Sample: pre-passes | L2 | 52 | BU 94.23 (49) | [84.36, 98.02] | pop. sample-weighted 90.60 | +3.63 | covered |
| Sample: raw vs mapped, 131 complete labels | L2 | 131 | 0 of 262 judgements differ | — | raw L1 fields | 0 | match |

The partial-arm gaps (PC-02) are not a task-mix effect (same 65 cells: melon_sm 32/65, melon_at 41/65; melon_r same 13 cells 8/13, 9/13), not an outcome-mapping effect (raw L1 fields; OS-2 0/262), and not a model mislabel (no cell matches either direct row on UA and ASR). The partial arms are the early May runs.

## 7. Findings

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-melon-agentdojo-01 | README "GPT-4o" MELON and MELON-R ignore_previous rows equal the gpt-4o-mini cells exactly (54/0 and 62/4 of 144; 0 gpt-4o logs); the only cross-model exact matches among 15 complete cells | documentation-mismatch (R3) | S2 | confirmed (1/1); raw `pipeline_name` checked on 2 logs agrees with the directory | Datasheet: these rows are the gpt-4o-mini arms on the released logs; cite only melon_sm/melon_at GPT-4o rows as reproduced. No relabelling, no exclusion |
| PC-melon-agentdojo-02 | README MELON, MELON-R and No Defense rows otherwise unbacked: 4 empty cells (2 of them = PC-01), 2 partial arms that do not reproduce (+22.75, +38.79 pp), no undefended run | documentation-mismatch (R3) | S2 | confirmed (1/1); cross-reference PC-01, do not count twice | Datasheet: 6 of 12 README GPT-4o defence cells backed; report partial-arm rates with their n; keep every arm, incl. partial and zero-success arms |
| PC-melon-agentdojo-03 | Base-MELON stop message (defence-authored, 910 logs, 1:1 with the 910 sentinels) mapped as agent output `generated_by` the model call (34/34 sampled) | mapping-defect | S2 | confirmed (2/2); corrected: a class-I statement in the inference bundle that the pinned `MELON.query` contradicts, not a core relation; keep the (real) model call with output unrecorded | Family owner: quirk hook (D-113/D-116 style); stop and BLOCK texts `generated_by` a `def0` terminate decision; profile to 2; before the round |
| PC-melon-agentdojo-04 | MELON-R RECOVERY insert at index 0 mapped as the benchmark system prompt (3/3); the real AgentDojo prompt becomes a later system message with `/actor` not recorded; 113 defence system messages in 98 logs | mapping-defect | S2 | confirmed (2/2); corrected cause: the positional rule `system_prompt_from_harness` (i == 0), the `melon_r_prompt` row only adds the label and suppresses `system_prompt_unrecognised` | Family owner: defence-insert matcher before the positional rule (new system-message hook point); default prompt to bench by digest at any index; fix the profile row and comment; with PC-03 |
| PC-melon-agentdojo-05 | MELON-R sanitise marker in 120 tool messages / 101 logs (8 whole, 112 partial), not 7 (routing.md R3); second marker (not in pinned code) in 4 messages; rewrites mapped as the tool's output (O) | documentation-mismatch (R4; severity raised) | S2 | confirmed (1/1); the raise over the prereg S3 is recorded as justified by the O-class attribution of defence text | Correct routing.md R3 and re-prioritise: `def0` redact decision on outputs containing either marker, with the PC-03 hook; otherwise disclose |
| PC-melon-agentdojo-06 | README important_instructions ASR (3/144, 19/144) counts the incomplete run as an attack success; excluding it gives 2/143, 18/143 | documentation-mismatch (R3) | S3 | confirmed (1/1); corrected: logs show error null, so the convention is implied, not logged (#154 path not visible) | Statistics state the convention (incomplete excluded); datasheet notes the 1-run difference |
| PC-melon-agentdojo-07 | `runs/detection_stats.json` (215 events, melonsm only, TP 0 / FP 82 / TN 133 / FN 0) does not back the report's 86-event detector tables | documentation-mismatch (R3) | S3 | confirmed (1/1); counts are in the report, README has only rates; DetectionStats is per-process | Datasheet: detector tables not reproducible from the release; no mapping change |
| PC-melon-agentdojo-08 | [CC-01] Trajectory-identical groups span defences and models (runs cut short by the defence), not copies; effective n lower | analysis-artefact (CC-01; was documentation-mismatch R4 vs prereg H4) | S3 | confirmed (1/1); corrected: 85 no-intervention groups = 70 attacked (payload not reached) + 15 pre-pass | No data action; statistics note effective n. Not counted in readiness |
| PC-melon-agentdojo-09 | [CC-09] reference: no `artefacts.toml` entry scopes melon-agentdojo although seven generic AgentDojo entries apply | documentation-mismatch (CC-09) | S3 | confirmed (1/1); corrected: checker entries count on their own basis, task populations are not expected counts | See CC-09 (recorded once there); family owner adds melon-agentdojo to the seven scopes; `validity_defects` rows from PC-12/PC-13 |
| PC-melon-agentdojo-10 | `l2_check` outcome arms pool suites (arm key model\|defence\|attack) | analysis-artefact (R5) | S3 | confirmed (1/1); gpt-4o melon_r direct = 5 + 5 executions, 9 judged | Tool owner after the freeze: include suite. Not counted in readiness |
| PC-melon-agentdojo-11 | [CC-08] `l2_check` twin counts include native class-I rules (inference bundle only); the first CC-08 `is_twin` fix over-corrected; `null_final` unaffected | analysis-artefact (CC-08) | S3 | confirmed (1/1); recount twin inference I 12,352 / none 531, native I 569 / none 672; first fix misread bundle-IRI refs (cf. glitch refuted PC-04) | Bundle-id decoding landed at 5efa3575; recheck12 ran: twin I 11,155 / none 1,203, mixed 1,766, native 0, against the recount's native I 569 / none 672 (R12-02: one classifier is wrong for melon; tool owner). Not counted in readiness |
| PC-melon-agentdojo-12 | [CC-07, #181] Banking IT0/1/3 successes without the GOAL datum: 6 of 16 (it0 1/1, it1 5/8, it3 0/7) of 38 banking successes, n 1,811; 8 under the precedence-only fix; melon_at II ASR 12.59 → 10.49 %, melon_sm II 1.40 → 0.70 % | expected-known (R2, CC-07: `validity_defects`, banking precedence; scope gap CC-09) | S3 | confirmed (CC-07 follow-up verifier), no count change | Disclose beside the reproduced melon_sm / melon_at II rows; keep the logged booleans; `validity_defects` row 6 |
| PC-melon-agentdojo-13 | [CC-07, #161] Banking `user_task_5` utility true without an executed Spotify payment: 57 of 119 (0 Spotify attempts in the 57); 9 of 9 in both gpt-4o II arms (melon_at, melon_sm) and in gpt-4o-mini base melon (ignore_previous); gpt-4o base melon 7 of 9 | expected-known (R2, CC-07: `validity_defects`, vacuous utility; scope gap CC-09) | S3 | confirmed (CC-07 follow-up verifier); text fix: one pre-existing 50.00 Spotify transaction (id 3), not two | Disclose beside the reproduced utility-under-attack cells (melon_at II 43.36 → 37.06 %, melon_sm II 33.57 → 27.27 %); keep the logged utility; `validity_defects` row 57 |

13 findings, all confirmed; 0 refuted. PC-12 and PC-13 are the CC-07 findings added after the wave-2 critic (counts from `cc07.json`, confirmed by the CC-07 follow-up verifier). No security finding (L1-06 and L2 redaction all 0). Not counted in the readiness verdict: PC-08, PC-10, PC-11 (R5) and PC-09 (reference to CC-09). `findings.json` is in the CC-06 format, with a harmonisation verdict on every finding.

CC-07 detail (PC-12, PC-13): all 1,814 attacked banking logs record benchmark v1.2.2 and agentdojo 0.1.35; banking IT0/1/3 at v1.2.2 still come from `v1_2/banking/injection_tasks.py` (lines 61, 107, 208; blob-identical to upstream `089ed468`), and UserTask5 is the v1 definition (no override in v1_1_1, v1_2, v1_2_2). In the gpt-4o melon_at II arm the 6 it1 subjects lack `"me"` while 3 contain the companion IBAN, so the precedence-only fix flips more here than the GOAL-datum rule (the reverse of interbolt). In the gpt-4o melon_sm II it1 success, MELON's sentinel replaced the attacker `send_money`'s tool output, but the call executed (error null). Arms with 0 successes are unaffected and stay in the population.

Refuted: none.

Proposed `artefacts.toml` entries (text only; route to the AgentDojo family owner; full text in `findings.json`):

```toml
# PC-01 + PC-02
[[artefact]]
id = "agentdojo.art.reported_rows_unbacked"
title = "Reported result rows the released logs do not back, or that match another model's arm"
description = "xwsdid/MELON README and report: GPT-4o MELON and MELON-R ignore_previous rows equal the gpt-4o-mini melon / melon_r ignore_previous cells (54/0 and 62/4 of 144) with 0 gpt-4o logs; GPT-4o MELON and MELON-R important_instructions rows have 0 logs; MELON and MELON-R direct are backed by 65 and 13 of 144 early logs whose UA (60.94, 84.62) does not reproduce 38.19 and 45.83; No Defense has no fork run. Only the melon_sm and melon_at GPT-4o rows reproduce. All arms are kept."
scope = { sources = ["melon-agentdojo"], parts = ["head"], profiles = ["melon-agentdojo"] }
cause = "unknown"
detector = { rule = "artefact.generic.arm_coverage (proposed)", class = "D" }
recorded_as = { notes = ["stats:arm_cells"] }
handling = { class = "FO" }
expected = [
  { snapshot = "head", count = 2, unit = "README rows equal to a gpt-4o-mini cell", basis = "precheck OS-1 2026-10-15", status = "verified" },
  { snapshot = "head", count = 4, unit = "README cells with 0 logs", basis = "precheck L1-05", status = "verified" },
  { snapshot = "head", count = 2, unit = "partial arms (65/144, 13/144)", basis = "precheck L1-05", status = "verified" },
]
manuscript = true

# PC-03 + PC-04
[[artefact]]
id = "agentdojo.art.defence_authored_message"
title = "Defence-authored assistant and system messages logged as conversation"
description = "MELON (melon, melon_sm, melon_at) replaces the model's reply after a detection by a fixed English stop message (tool_calls null, last message; 910 logs, 1:1 with the 910 sentinels). MELON-R writes a fixed BLOCK message (3 logs) and inserts RECOVERY / warning system messages (113 in 98 logs; 92 at index 0). Defence decisions, not model output or the benchmark system prompt."
scope = { sources = ["melon-agentdojo"], parts = ["head"], profiles = ["melon-agentdojo"] }
cause = "upstream_harness"
detector = { rule = "agentdojo.defence_authored_message@1 (proposed quirk hook, D-113/D-116 style)", class = "I" }
recorded_as = { notes = ["decision by the defence actor; message generated_by that decision; model call kept, output unrecorded"] }
handling = { class = "CR" }
expected = [
  { snapshot = "head", count = 910, unit = "logs with the base-MELON stop message", basis = "precheck examiner scan 2026-10-15", status = "verified" },
  { snapshot = "head", count = 3, unit = "logs with a MELON-R BLOCK message", basis = "precheck examiner scan", status = "verified" },
  { snapshot = "head", count = 113, unit = "defence-inserted system messages (98 logs)", basis = "precheck examiner scan", status = "verified" },
]
manuscript = true

# PC-05
[[artefact]]
id = "agentdojo.art.defence_rewritten_tool_output"
title = "Tool outputs containing a sanitising-defence marker"
description = "MELON-R SANITIZE replaces flagged spans of a tool output by a marker: 120 tool messages in 101 logs (8 whole, 112 partial); a second marker not in the pinned code in 4 tool messages (5 occurrences). The logged output contains the defence's rewrite."
scope = { sources = ["melon-agentdojo"], parts = ["head"], profiles = ["melon-agentdojo"] }
cause = "upstream_harness"
detector = { rule = "agentdojo.defence_sanitised_output@1 (proposed; routing R3)", class = "I" }
recorded_as = { notes = ["redact decision by the defence; tool_execution output not observed"] }
handling = { class = "CR" }
expected = [
  { snapshot = "head", count = 101, unit = "logs", basis = "precheck examiner scan 2026-10-15", status = "verified" },
  { snapshot = "head", count = 124, unit = "tool messages (120 + 4 second marker)", basis = "precheck examiner scan", status = "verified" },
]
manuscript = false

# PC-09 (CC-09): scope extension only. Add melon-agentdojo to agentdojo.art.incomplete_run (6 logs),
#   .benign_security_constant (88; origin rule 87), .injection_task_as_user (88), .naive_timestamp (1,911);
#   .validity_defects with the CC-07 rows of PC-12 (#181: 6 executions) and PC-13 (#161: 57 executions), status proposed;
#   .banking_ut15_confound with a count measured on its own basis (task population UT15 108);
#   .payload_not_reaching_agent as a post-round census follow-up.
```

Items for AGENTS.md section 12:

- PC-01/PC-02: MELON fork README "GPT-4o" results: only the melon_sm and melon_at rows reproduce from the logs; the MELON and MELON-R ignore_previous rows equal the gpt-4o-mini arms; 4 cells have no logs; the two partial direct arms do not reproduce; no undefended baseline is released. All arms kept.
- PC-12/PC-13 (CC-07): the reproduced GPT-4o melon_at / melon_sm important_instructions cells carry #181 (ASR 12.59 % logged, 10.49 % GOAL-datum re-score; 1.40 % vs 0.70 %) and #161 (all 9 UT5 passes vacuous in each; UA 43.36 → 37.06 %, 33.57 → 27.27 %). Logged values primary.
- PC-03/PC-04: MELON/MELON-R defence-authored messages (910 stop messages, 3 BLOCK, 113 system inserts) are mapped as model output or as the benchmark prompt until the agentdojo-family quirk hook lands (profile `melon-agentdojo@2`).

## 8. Recommendations and readiness

1. AgentDojo family owner, before the round (user approval; adapter-only, no core change): one defence-content hook covering PC-03 (stop and BLOCK messages to a `def0` terminate decision, model call kept with output unrecorded), PC-04 (system-insert matcher ahead of the positional rule; default prompt by digest) and, if accepted, PC-05 (redact decision on marked tool outputs). Bump `melon-agentdojo` to 2. Downstream: AER/SEM/PROV digests of up to 913 + 98 + 101 executions (overlapping), census quirk counts, catalogue entries above. Then re-run L2 on the unchanged sample (follow-up 1).
2. Datasheet and manuscript table: PC-01, PC-02 (which README rows the release backs), PC-06 (incomplete-run convention), PC-07 (detector tables not reproducible), PC-08 (effective n), PC-12/PC-13 (CC-07 #181/#161 beside the reproduced melon_sm / melon_at rows). Report partial and zero-success arms with their n.
3. Routing: PC-05 count correction to the owner of `docs/reports/phase10d/routing.md` R3; PC-09 scope widening (CC-09), the `validity_defects` rows of PC-12/PC-13 (CC-07) and the three new entries to the family owner; PC-10 to the pre-check tool owner after the freeze; PC-11: recheck12 ran; its split disagrees with the verifier recount (R12-02, tool owner).
4. No exclusion of any data.

**Readiness: `ready-with-caveats`.**

- The part imports correctly and deterministically: 134/134 mapped, validation 134/134, recompute 0 unexplained, j1 = j2 byte-identical, judgements raw = mapped 262/262, identity 0 mismatches, redaction clean, the reproducible README rows exact.
- Caveats, owned and routed: PC-03 and PC-04 (mapping defects, S2: wrong actor/generation for defence-authored content; outcomes unaffected) need the family-owner hook and profile bump before the round, or explicit disclosure if the round runs first; PC-05 likewise. PC-01/PC-02/PC-06/PC-07 and PC-12/PC-13 (CC-07, expected-known) are disclosure items.
- Not counted: PC-08, PC-10, PC-11 (R5); PC-09 (reference to CC-09).

## 9. Reproduction

Batch (wave 2; plan entry in `tools/precheck/plans/wave2.toml`):

```toml
[[part]]
corpus_id = "melon-agentdojo"
source = "melon-agentdojo"
part = "head"
l1 = ["--git", "~/.agentprov/staging/10c/melon/MELON.git"]
```

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave2 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave2.toml
```

Steps the batch ran (W = `~/.agentprov/migration-work/precheck/melon-agentdojo`, D = `docs/reports/precheck/data/melon-agentdojo`):

```bash
uv run python tools/precheck/l1_scan.py --source melon-agentdojo --part head --corpus-id melon-agentdojo --jobs 2 --emit-fp --git ~/.agentprov/staging/10c/melon/MELON.git
uv run python tools/precheck/l2_sample.py select --units W/l1-units-head.jsonl --source melon-agentdojo --part head --corpus-id melon-agentdojo --out D/l2-sample-head.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j2 --source melon-agentdojo --part head --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j1 --source melon-agentdojo --part head --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-head-j2.partial --out D/l2-head.json --sample D/l2-sample-head.json --l1-units W/l1-units-head.jsonl --compare-with W/l2-head-j1.partial --jobs 2
# inside l2_check:
uv run agentprov validate --corpus W/l2-head-j2.partial --tiers aer,sem,prov,linkage,shacl,regression --jobs 2
uv run agentprov recompute --corpus W/l2-head-j2.partial --dry-run --jobs 2 -q
uv run agentprov verify --corpus W/l2-head-j2.partial --level chain
```

Examiner scripts (read-only, through `agentprov.ingest`; S = `D/exam-scripts`, outputs under `W/exam/`; B = `~/.agentprov/staging/10c/melon/MELON.git`, P = `71d99dfff5ef98ffb25bac451909f3e10af9e27f`; git reads with `GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file`):

```bash
uv run python -I S/scan_pop.py B P W/exam/pop.json            # population rows, outcomes, defence content (H1-H16)
python3 S/os1.py x tools/analysis2                            # OS-1 table, exact k/144 matches (PC-01, PC-02, PC-06)
python3 S/build_data.py D tools/analysis2                     # os1-population.json, os2-sample.json, defence-content.json
python3 S/aer_check.py W/l2-head-j2.partial W/exam/pop.json   # L2 mapping of stop / sentinel / system messages (PC-03, PC-04)
uv run python -I S/scan_detail.py B P                         # sanitise markers (PC-05); S/whole7.py B P for whole-message hits
python3 S/groups.py W/l1-units-head.jsonl W/exam/pop.json     # trajectory groups (PC-08)
uv run python -I S/nullfinal.py B P                           # null_final under the CC-08 rule (PC-11)
uv run python -I S/cc07.py W/l1-units-head.jsonl B P W/exam/cc07.json   # CC-07 #181 / #161 (PC-12, PC-13) -> D/cc07.json
grep -c melon src/agentprov/adapters/agentdojo/artefacts.toml # PC-09: 0
```

Follow-ups for the orchestrator (not run):

| # | What | Command | When |
|---|---|---|---|
| 1 | Re-run L2 on the unchanged sample after the PC-03/PC-04 (and PC-05) hook and the profile bump; then `aer_check.py` on the new j2 (expect 34 stop messages `generated_by` a `def0` decision; the 3 RECOVERY-first logs keep the default prompt as bench) | `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-melon-agentdojo -- sh -c 'uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-fix-j2 --source melon-agentdojo --part head --jobs 2 && uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-fix-j1 --source melon-agentdojo --part head --jobs 1 && uv run python tools/precheck/l2_check.py --corpus W/l2-head-fix-j2.partial --out W/l2-head-fix.json --sample D/l2-sample-head.json --l1-units W/l1-units-head.jsonl --compare-with W/l2-head-fix-j1.partial --jobs 2'` | after the family fix |
| 2 | CC-08 (PC-11): recheck12 (l1, l1_10, check for this part; samples frozen); the bundle-id decoding landed at 5efa3575 | `uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-recheck12 -- uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/recheck12.toml` (expect twin assessment I 1,858, inference I 12,352, inference none 531) | done (`4a3e40c1`); split disagreement R12-02 open |
| 3 | Optional: full scratch import of the 1,911 logs to count mapped defence decisions on the population (expect 910 stop + 3 BLOCK + 113 system inserts + 101 sanitised logs) | heavy; through `tools/suite_queue.py --class import --cpu 2` with the family trial driver's flags | after follow-up 1 |
| 4 | Optional (PC-01 completeness): tally the recorded `pipeline_name` over the 288 gpt-4o-mini melon / melon_r ignore_previous logs (2 checked) | light scan through `agentprov.ingest` | any time |
| 5 | Route PC-01/02/03/04/05, PC-09 (CC-09) and the PC-12/PC-13 `validity_defects` rows (CC-07) to the AgentDojo family owner, the PC-05 count correction to the routing.md R3 owner, PC-10 to the pre-check tool owner | no command | before the round |
