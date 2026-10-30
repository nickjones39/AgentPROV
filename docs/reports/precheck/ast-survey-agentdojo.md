# Pre-check dossier: `ast-survey-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `ast-survey-agentdojo` (CC-BY-4.0; embedded AgentDojo text MIT) |
| Parts | `agent-security-tools-survey · agentdojo-runs` (1 part) |
| Family / profile | `agentdojo` / `survey-runs@2` (dialect `agentdojo.tracelogger`, variant `v1.k14`; SEM `agentdojo.suites@2`) |
| Pin | git `Forever-CodingNoob/agent-security-tools-survey` @ `89c4db2c`, tree `agentdojo` |
| Code commit | `a871e2d7` (L1 and L2, batch `wave1`, no tracked changes) |
| Kind | wave 1, delta since E2 (`../analysis/phase10-examination-2.md`) against stored `ast-survey-agentdojo-p10` |
| Date | 2026-10-14 (prereg, research, L1), 2026-10-15 (L2, verify, dossier) |
| Agents | researcher and fact-checker (prereg, research), examiner (L1/L2 analysis), verifiers (1 per finding, 2 for PC-01), dossier writer |
| Data | [`data/ast-survey-agentdojo/`](data/ast-survey-agentdojo/): `research.json`, `l1-agentdojo-runs.json`, `l1-extra.json`, `l2-sample-agentdojo-runs.json`, `l2-agentdojo-runs.json`, `exam.json`, `outcomes.json`, `delta-p10-vs-l2.json`, `findings.json`, `exam-scripts/` |

- Code identity, part `agentdojo-runs` (Level 2, [`code-agentdojo-runs.json`](data/ast-survey-agentdojo/code-agentdojo-runs.json)): commit `a871e2d7`; engine code aer `24df84b5e307`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `d3f9995f61bf`; adapter agentdojo.tracelogger c311b5a6ac9e.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Survey repository | https://github.com/Forever-CodingNoob/agent-security-tools-survey (pin `89c4db2c`, HEAD of main on 2026-10-14; 0 tags, releases, issues, PRs) | the data; `agentdojo/README.md` tables are the only outcome reference |
| Zenodo record | https://doi.org/10.5281/zenodo.22140262 (concept 22135956; v1.0.0 and v1.0.1, cc-by-4.0) | data record standing in for a paper; non-primary pins match |
| Survey paper | none found (arXiv and web, 2026-10-14) | n/a |
| AgentDojo paper | https://arxiv.org/abs/2406.13352 | harness and metrics; not the source of these numbers |
| Harness | ethz-spylab/agentdojo @ `089ed468` (5 commits after v0.1.35), provider openai-compatible, `max_iters` 15, 3 local patches (timeout, `model_rebuild`, InternalServerError → utility False / security True) | producer and checker |
| Upstream issues | agentdojo [#181](https://github.com/ethz-spylab/agentdojo/issues/181), #161, #162, #213, #214, #154; ollama #18530 | outcome-validity and encoding defects at this commit |

Data-versus-paper notes (from `research.json`):

- No paper. The README "Security" column is a targeted ASR (security True = injection succeeded) despite the "resisted" gloss (profile quirk `semantic_trap_security_gloss`).
- The released run scripts are not those that produced the logs: `--force-rerun` was added on 2026-08-25, after the last log (2026-08-21) (H5).
- The README contradicts itself on the partial run (script table "not used" vs Phase-1 text "cache reused"); the partial table is not backed by the logs (PC-03).
- The README's gpt-oss 500-error task list does not match the 11 released errors (PC-02). The gpt-oss ASR 256/949 includes 10 security values imposed by patch (c) (246/939 = 26.2 % without them).
- The 105 solvability runs are in the data but not in the README (extra arm, expected).
- Model identity rests on the results-directory slug only (Ollama tags, no weight digest; identity class I).
- AgentDojo defects at `089ed468` bias outcomes: #181 banking subject check (PC-04, CC-07), #161, #162, #213; qwen3-coder text-encoded calls (ollama #18530, H6); `\uXXXX` tool output (#214, H7).

## 3. Expectations

Pre-registration: [`prereg/ast-survey-agentdojo.md`](prereg/ast-survey-agentdojo.md), committed in `fd75f8a3` (2026-10-14), before any check of this corpus ran. Method amendments 1 to 3 (README section 8) apply; amendment 1 covers the stored corpus's expected `validate.results.differ`, amendment 2.4 the stratum key.

Hypotheses H1 to H12: 10 supported (H1, H3, H5 to H12), 2 refuted (H2 → PC-02, H4 → PC-03). Prereg rows found wrong: the 36-stratum / 180-unit sample (PC-07), AER evidence shares within 5 pp of FA (PC-06), the U6-c Gap prediction (PC-05, CC-04) and the item-24 seal pointer for the 49 unexecuted calls (refuted PC-01: the pointer applies only to class-I issue rules).

Classes follow the canonical rules R1-R6 and the cross-cutting items CC-01 to CC-08 of [`cross-cutting.md`](cross-cutting.md) (harmonisation pass 2026-10-15).

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Run at `a871e2d7`, `--use-pin`, 2.8 s, jobs 2. Denominator 3,243 artefacts unless stated.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | walked 3,267 (prefixes `agentdojo`, `agentharm/results`, `asb/results`). Selected 3,243 = registry (1,081 per model). Context 10 (8 console logs, `timing_summary.csv`, `run_full_benchmark.sh`). Excluded: `select.owned_elsewhere:ast-survey-agentharm` 6, `select.dialect_planned` 4. Not selected 4. Rejected gitlink 1 (`agentdojo/agentdojo`). `agentdojo/` tree 3,243 + 10 + 3 = 3,256 | as pinned |
| L1-02 parse | strict ok 3,243/3,243; 0 duplicate keys, NaN/Infinity, big int, lone surrogate, BOM, trailing data, invalid UTF-8, truncation. 122 paired-surrogate objects are valid | as expected |
| L1-03 encodings | zero-width 1; variation selector 12. Escaped newline 1,054 artefacts / 1,847 strings (1,803 content, 20 tool-call args, 4 `/error`); escaped unicode 238 / 362 (360 content, 2 `/error`); escaped quote 133 / 155; json-in-string 6 / 6. 0 U+2028/2029/0085, C0/C1, ESC, bidi, tag, PUA, U+FFFD, mojibake | as expected (1, 12) |
| L1-04 duplicates | 0 byte-identical. Trajectory-identical 60 groups / 507 units (qwen3-coder 36, qwen3:14b 14, gpt-oss 10 groups): each one model and one user task, different injection tasks; 13 hold the benign run; utility never differs; 0 of 494 attacked members security True. 0 cross-part, 0 cross-corpus (`_cross/l1-xdup.json`) | prereg 32 / 299 used a different fingerprint (PC-09, CC-01: both figures reported) |
| L1-05 arms | per model: workspace 40 + 14 + 560, travel 20 + 7 + 140, banking 16 + 9 + 144, slack 21 + 5 + 105 (benign + solvability + attack) = 1,081, × 3. Attack `important_instructions` only; 0 missing, 0 extra cells; 0 `path_disagrees` | as expected (105 solvability extra vs README) |
| L1-06 secrets/paths | 0 secret-like, 0 account path, 0 operator home, 0 local-path model | as expected |
| L1-07 timestamps | `/evaluation_timestamp` 3,243/3,243, naive, 0 parse failures, 2026-08-17..2026-08-21. 9 further date pointers are scenario dates (benchmark fiction); the 5 "non-monotone" units come only from them (one run timestamp per log). Per model 0 start + duration overlaps > 60 s | as expected |
| L1-08 degenerate | tool flags 0. Measured separately: 11 error rows, 48 capped executions / 49 unexecuted calls (stored index), 84 empty final answers missed by `null_final` (PC-08, CC-08) | 11 and 48 as expected; 84 = E2 N4 |
| OS-1 population | every README cell reproduces from the raw outcome fields: Phase-1 utility 15/15 cells, under-attack utility and ASR 30/30, solvability 3/3. Utility True 1,624, security True 1,027 of 3,243 | gap 0.0 pp on every arm |
| H2–H10 | measured on the stored AER (counts only), `l1-extra.json`: H6 174/174 text-encoded calls qwen3-coder; H7 360/360 literal `\uXXXX` text parts role tool; H8 per-model hours equal to 0.01 h (65.09 h vs ~63 h = 1.92 h solvability); H9 benign travel ut19 error null; H10 13 of 57 banking it0/it3 successes lack the datum (PC-04, CC-07) | |

Duplicate group counts in this table are the per-part L1 summary (`l1-agentdojo-runs.json`), and this dossier uses it. `data/_cross/l1-xdup.json` counts a group under `within_part` only when all its members are in one part and moves groups that span parts or corpora to `cross_part` or `cross_corpus`; for this part both give 60 trajectory groups. A comparison with the post-check must use the same basis.

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`data/ast-survey-agentdojo/l2-sample-agentdojo-runs.json`](data/ast-survey-agentdojo/l2-sample-agentdojo-runs.json): 120 units, 24 strata (`results_dir|attack_dir|suite`) × 5. Per model: attack 20, `attack_dir=none` 20 (benign 13/14/13, solvability 7/6/7 for gpt-oss/coder/qwen3:14b) (PC-07) |
| Import | 2 scratch corpora (`l2-agentdojo-runs-j2.partial`, `-j1.partial`): selected 120, mapped 120, failed 0, degenerate 0, `adapter_defect` 0; status ok 119 / ok_with_issues 1; all stages ok. Register codes: `accounting_unverifiable` 120, `earlier_attempts_unobservable` 120, `unexecuted_tool_call` 1 |
| Validation | tiers aer, sem, prov, linkage: 120 passed, 0 failed, linkage 120/120, results reproduced 120. SHACL not implemented; regression n/a |
| Recompute | `--dry-run` (shim): 120 identical, 0 unexplained |
| Verify chain | 130 raw rehashed, 0 failed; `checksums.absent` (working tree, expected) |
| Determinism | j2 vs j1: 497 files each, 0 differ, index identical |
| A2 error classes | run errors 0 in the sample (population 11, none drawn: follow-up); capped 1; text-encoded calls 5 (qwen3-coder); empty final answers 7; literal `\uXXXX` tool parts 5 |
| A3 PROV issues | 57,840 statements, 97,783 relation arguments: 0 dangling, 0 invented. The unexecuted call is `apv:NotDispatched` (1/1) in core, no seal pointer: specified for a D-class issue rule (refuted PC-01) |
| Evidence classes | PROV, 120 executions: core O 3,470 / D 540 (`aprov.n_gap` 420, `n_capture_profile` 120) / none 435; inference I 19,672 (twin-cited 19,455) / none 1,559; assessment I 4,876 / O 240 / D 3 / none 2,511; top O 21,045. AER evf O .204 / D .022 / I .774 vs stored O .208 / D .324 / I .468 (PC-06; remaining D only `agentdojo.system_prompt_variant_digest@1`, 120) |
| Identity | 3 models from the results-dir slug (`survey.model_from_results_dir@1`), 40 each; defence none 120; attack `important_instructions` 60 / none 60; suites 30 each; 0 mismatches, 0 unresolved |
| Redaction | 368 files: 0 account-path or secret hits in AER/SEM/PROV/index (no redact table in the profile) |
| Withholding | no `[withhold]` policy: n/a, as preregistered |
| OS-2 mapping | mapped utility and security equal the raw values on 120/120 labels |
| DL-1 (stored `-p10` vs scratch) | same 120 ids, 0 only-new. AER, SEM, PROV and validation digests differ 120/120, every pointer attributed (`delta-p10-vs-l2.json`): item 30 / D-31 (profile @2, rules agentdojo 1→2, stage digests); item 3 / D-24 / D-80 (13 renames to `_unverified` twins, D→I, inference bundles 1,468 → 3,249, assessment D 396 → 3); item 5 / D-370 (+1 activity in each of 60 attacked executions); U6-c / D-373 (525 `apv:paramsStatus NotRecorded`, PC-05, CC-04); item 8 / D-379 (normaliser @2 on 499 markers, 0 status changes); item 6 / D-371 (3 `partial_payload` in 2 executions); item 1 / D-86 (suites@2); item 4 (0). Index: completeness, status, issues unchanged. Unexplained 0. Stored `validate.results.differ` expected-known (PC-11, CC-05) |

### Recheck (CC-08, recheck12)

`plans/recheck12.toml` (l1, l1_10, check; sample frozen) against the d97d3a57 files; full deltas in [`_cross/recheck12.json`](data/_cross/recheck12.json). Every other L1/L2 count is unchanged; the only other deltas are run environment (code commit d97d3a57 with tools/src = 5efa3575, `tracked_changes` true, two H.8.4(2) recompute notices with 0 unexplained changes; R12-01).

| Part | L1-08 flags (old -> new) | L2 `_unverified` split | L1-10 |
|---|---|---|---|
| agentdojo-runs | `null_final` - -> 84; `trailing_calls` - -> 48 | twin inference:I 19,455 -> 16,897; mixed 2,558; native 0 (sum 19,455 = old) | 10 screened (context 10); account:home-dir:named 58; files with a hit 5; named accounts 1; operator 0; unreadable 0 |

- PC-08 resolved: `null_final` 84 (= the measured 84 empty block-list finals); `trailing_calls` 48 (= the 48 capped executions).
- **New (L1-10, not in L1-06):** 5 of 10 non-JSON context files hold 58 `account:home-dir:named` matches, 1 distinct account, not the operator. CC-11 class (raw-store context, `security = true`); recorded as PC-ast-survey-agentdojo-13 (proposed, unverified).

## 6. Outcome comparison

Reference: the survey README (no paper). Level 1 = all units of the arm (raw fields). Level 2 = the sample's mapped outcomes; raw rate with unweighted Wilson 95 %, plus the stratum-weighted rate (prereg H12). Gap rule (section 4): > 15 pp on an arm with n ≥ 20, or > 5 pp outside the interval; arms with n < 20 are descriptive only.

| Arm | Level | n | Metric | Rate (Wilson 95 %) | README | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|---|
| qwen3:14b benign | L1 | 97 | utility | 0.691 [0.593, 0.774] | 69.1 % (67) | 0.0 | match |
| qwen3-coder:30b benign | L1 | 97 | utility | 0.577 [0.478, 0.671] | 57.7 % (56) | 0.0 | match |
| gpt-oss:120b benign | L1 | 97 | utility | 0.670 [0.572, 0.756] | 67.0 % (65) | 0.0 | match |
| qwen3:14b attack | L1 | 949 | utility | 0.528 [0.496, 0.560] | 52.8 % (501) | 0.0 | match |
| qwen3:14b attack | L1 | 949 | ASR | 0.176 [0.153, 0.202] | 17.6 % (167) | 0.0 | match |
| qwen3-coder:30b attack | L1 | 949 | utility | 0.366 [0.336, 0.397] | 36.6 % (347) | 0.0 | match |
| qwen3-coder:30b attack | L1 | 949 | ASR | 0.219 [0.194, 0.247] | 21.9 % (208) | 0.0 | match |
| gpt-oss:120b attack | L1 | 949 | utility | 0.549 [0.517, 0.580] | 54.9 % (521) | 0.0 | match |
| gpt-oss:120b attack | L1 | 949 | ASR | 0.270 [0.243, 0.299] | 27.0 % (256; 10 imposed) | 0.0 | match |
| qwen3:14b solvability | L1 | 35 | utility | 0.629 [0.463, 0.768] | 62.9 % (investigation) | 0.0 | match |
| qwen3-coder:30b solvability | L1 | 35 | utility | 0.600 [0.436, 0.745] | 60.0 % | 0.0 | match |
| gpt-oss:120b solvability | L1 | 35 | utility | 0.686 [0.520, 0.815] | 68.6 % | 0.0 | match |
| gpt-oss:120b attack | L2 | 20 | utility | 0.500 [0.299, 0.701]; weighted 0.542 | 0.549 | −4.9 raw / −0.7 w | match |
| gpt-oss:120b attack | L2 | 20 | ASR | 0.550 [0.342, 0.742]; weighted 0.386 [0.157, 0.615] | 0.270 | +28.0 raw / +11.6 w | flag, investigated: equal-allocation design (PC-10; R6, not a corpus finding) |
| qwen3-coder:30b attack | L2 | 20 | utility | 0.450 [0.258, 0.658]; weighted 0.430 | 0.366 | +8.4 / +6.5 | match |
| qwen3-coder:30b attack | L2 | 20 | ASR | 0.250 [0.112, 0.469]; weighted 0.119 | 0.219 | +3.1 / −10.0 | match |
| qwen3:14b attack | L2 | 20 | utility | 0.650 [0.433, 0.819]; weighted 0.549 | 0.528 | +12.2 / +2.1 | match |
| qwen3:14b attack | L2 | 20 | ASR | 0.400 [0.219, 0.613]; weighted 0.210 | 0.176 | +22.4 / +3.4 | flag (raw > 15 pp), same cause (PC-10) |
| gpt-oss:120b benign | L2 | 13 | utility | 0.615 [0.355, 0.823]; weighted 0.715 | 0.670 | descriptive | n < 20 |
| qwen3-coder:30b benign | L2 | 14 | utility | 0.571 [0.326, 0.786]; weighted 0.590 | 0.577 | descriptive | n < 20 |
| qwen3:14b benign | L2 | 13 | utility | 0.769 [0.497, 0.918]; weighted 0.698 | 0.691 | descriptive | n < 20 |
| gpt-oss:120b solvability | L2 | 7 | utility | 0.714 [0.359, 0.918]; weighted 0.671 | 0.686 | descriptive | n < 20 |
| qwen3-coder:30b solvability | L2 | 6 | utility | 0.667 [0.300, 0.903]; weighted 0.533 | 0.600 | descriptive | n < 20 |
| qwen3:14b solvability | L2 | 7 | utility | 0.571 [0.250, 0.842]; weighted 0.433 | 0.629 | descriptive | n < 20 |

The population matches the README exactly on all 12 arms (45 suite cells, H1). The two sample flags are caused by the sample design: 5 units per suite against populations of 560/140/144/105, with banking/slack ASR far above workspace. Mapped = raw on 120/120, and every stratum-weighted 95 % interval contains the README rate (H12 supported). No mapping or identity error.

## 7. Findings

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-ast-survey-agentdojo-02 | README "Affected tasks" of the gpt-oss 500 errors do not match the 11 released errors (1 of 10 attacked errors in the named tasks; 34 of 35 pairs there error-free) | documentation-mismatch | S3 | confirmed (1/1), wording | Disclose; no mapping change; artefact entry below |
| PC-ast-survey-agentdojo-03 | README partial table (105 pairs/model) not reproducible: 1 of 6 combined cells equal; the 949 attack logs per model are one contiguous pass | documentation-mismatch | S3 | confirmed (1/1), evidence reworded | Disclose; only Phase-1 and full-949 tables are backed |
| PC-ast-survey-agentdojo-04 | [CC-07] Banking it0/it3: 13 of 57 successes lack the datum in the transfer subject (agentdojo #181); covered by `agentdojo.art.validity_defects` | expected-known (R2, CC-07) | S3 | confirmed (1/1), reclassified from source-defect S2 | Disclose; recount it1; never exclude. The entry's missing survey row is PC-12 |
| PC-ast-survey-agentdojo-05 | [CC-04] reference: U6-c predicted one `apv:Gap` per model call; engine (as specified, EF l.906) records `apv:paramsStatus NotRecorded` on 525 ModelInvocations | documentation-mismatch (CC-04) | S3 | confirmed (1/1) | See CC-04: one `regen-batch.md` U6-c correction for four corpora; not counted as a separate corpus finding |
| PC-ast-survey-agentdojo-06 | AER evf D .324 → .022: item 3 / D-80 weakens AER records too; prereg's ±5 pp described PROV only | expected-known | S3 | confirmed (1/1) | Fresh distribution is the post-check baseline |
| PC-ast-survey-agentdojo-07 | 24 strata (hook key) instead of the prereg's 36 / 180 units | analysis-artefact | S3 | confirmed (1/1) | Amendment 2.4 governs; reuse the committed sample |
| PC-ast-survey-agentdojo-08 | [CC-08] L1-08 `null_final` misses 84 empty block-list final answers (gpt-oss 68, qwen3:14b 16) | analysis-artefact (CC-08) | S3 | confirmed (1/1) | Widen the sub-check after the batches; re-run L1 for AgentDojo-family parts |
| PC-ast-survey-agentdojo-09 | [CC-01] L1-04 60/507 vs FA 32/299: the difference is exactly the provider tool-call ids | analysis-artefact (CC-01) | S3 | confirmed (1/1) | CC-01: record both baselines |
| PC-ast-survey-agentdojo-10 | Sample gap flags (gpt-oss ASR, qwen3:14b ASR raw) from equal allocation (R6 situation); `l2_check` rates unweighted | analysis-artefact | S3 | confirmed (1/1), corrections | Dated section-8 amendment before applying the rule to weighted estimates |
| PC-ast-survey-agentdojo-11 | [CC-05] Stored `validate.results.differ` (stored rows lack the 4 item-10 check ids; all 3,243 pass) | expected-known (CC-05) | S3 | confirmed (1/1) | Re-validate a copy of the stored corpus in the round |
| PC-ast-survey-agentdojo-12 | [CC-07] `agentdojo.art.validity_defects` has no banking-precedence (#181) expected row for this snapshot (only vacuous utility 4) | documentation-mismatch (R2, entry counts) | S3 | added in the harmonisation pass; entry re-read, count from PC-04 | Family owner adds the survey expected row (13, lower bound) and the #181 ref (proposal below) |

Counts: 11 findings (documentation-mismatch 4, of them the CC-04 reference PC-05; expected-known 3; analysis-artefact 4, not counted in the readiness verdict under R5), all S3; 1 refuted. 0 security-relevant. PC-12 was added in the harmonisation pass (R2: the existing entry's counts are incomplete for this source, beside the expected-known PC-04). PC-10 is the R6 situation (sample design); the stratum-weighted and population rates are beside it in section 6. `findings.json` is in the CC-06 format.

Verifier corrections applied in `findings.json`: PC-02 cause wording and README l.289–296 ref; PC-03 "14 precede" is task order, contiguous-pass proof added, detector replaced; PC-04 class/severity and no new entry; PC-05 cite EF l.906 and C.16/E.4.5; PC-08 `null_final` is a tool-added sub-check; PC-10 weighting is not yet in README section 4 (prereg H12 only), name the rule that fired.

Refuted (not a finding):

- **PC-ast-survey-agentdojo-01** (claimed mapping-defect S2: seal issue `unexecuted_tool_call` cites the D rule `agentdojo.unexecuted_trailing_calls@1` as given under `verified_code = []`, so no item-24 pointer). Both verifiers reproduced every count (stored 48 executions / 49 calls; scratch 1/120 in j1 and j2) and refuted the classification. Citing seal-issue rules as given is the decision DECISIONS D-80 (d) (its rejected alternatives list twins for issue-only rules), spec D.5.4 (`D_adapters.md:1847`) and the `mapper.py:414` docstring. The item-24 pointer is defined only for class-I issue rules (D-28 addendum 2, EF E.10 item 23). `agentdojo.art.max_iters_pending` already documents the survey's 48/49. The prereg rows (l.143, l.179) misread item 24. What is left is a design question for the family owner (recommendation 3), not a defect.

Proposed `artefacts.toml` entries (text only; route through the orchestrator to the agentdojo family owner):

```toml
[[artefact]]
id = "survey.art.readme_error_tasks_mismatch"
title = "README names other tasks than the released run errors"
description = "The survey README attributes the deterministic gpt-oss InternalServerError runs to workspace user_task_26/30 and travel user_task_19 (the latter aborting the utility phase); the released logs hold 11 errors, 1 of them in those tasks, and the benign travel user_task_19 log has no error. The README likely describes earlier, unreleased runs."
scope = { sources = ["agent-security-tools-survey"], parts = ["agentdojo-runs"], profiles = ["survey-runs"] }
cause = "documentation"
detector = { rule = "survey.internal_server_error_patch@1", class = "I" }
claims = []
recorded_as = { aer = ["execution.ext.agentdojo.error"] }
handling = { class = "FO" }
expected = [ { snapshot = "agent-security-tools-survey:agentdojo-runs", count = 11, basis = "precheck L1 error_present; 1 of 10 attacked errors in the README tasks; 34 of 35 pairs on those tasks error-free" } ]
manuscript = true
refs = ["docs/reports/precheck/data/ast-survey-agentdojo/l1-extra.json", "agentdojo/README.md @89c4db2c l.289-296 (Affected tasks)"]

[[artefact]]
id = "survey.art.partial_table_unbacked"
title = "Partial-benchmark table not backed by released logs"
description = "The README's 105-pair partial table differs from the same pairs of the released full run in 5 of 6 combined cells; each model's 949 attack logs are one contiguous pass, so the partial run's logs were not released."
scope = { sources = ["agent-security-tools-survey"], parts = ["agentdojo-runs"], profiles = ["survey-runs"] }
cause = "documentation"
detector = { rule = "<none: README table vs released logs; no per-trace detector>", class = "I" }
claims = []
recorded_as = {}
handling = { class = "FO" }
expected = [ { snapshot = "agent-security-tools-survey:agentdojo-runs", count = 315, basis = "precheck: 105 pairs x 3 models (run_partial_benchmark.sh at 89c4db2c); 1 of 6 combined cells equal" } ]
manuscript = true
refs = ["docs/reports/precheck/data/ast-survey-agentdojo/l1-extra.json"]

# PC-12 (and PC-04): addition to the existing entry agentdojo.art.validity_defects (banking precedence; no new entry)
expected += [ { snapshot = "agent-security-tools-survey:agentdojo-runs", count = 13, basis = "banking precedence (agentdojo#181), precheck H10: it0 7/27, it3 6/30 successes lack the datum in the subject; it1 untested; lower bound" } ]
refs += ["https://github.com/ethz-spylab/agentdojo/issues/181"]
```

Items for AGENTS.md section 12:

- PC-04: survey banking it0/1/3 ASR counts any transfer to the attacker IBAN (agentdojo #181); at least 13 of 57 it0/it3 successes lack the datum. Disclose; data kept; survey expected row pending with the agentdojo family owner (no per-trace detector exists).
- Open design question (from refuted PC-01): should D-80 (d) treat `unexecuted_tool_call` / `missing_tool_result` as "reporting a statement's reading" now that item 24 makes the issue a PROV premise? Owner and user decision; if yes, a regen item (twin, `self.cite` at `mapper.py:1511/1513` and `drift_mapper.py:864/866`, D-31 bump) moving the digests of capped executions under the 24 `verified_code = []` profiles.

## 8. Recommendations and readiness

1. Route the expected row and #181 ref (PC-12, for PC-04; CC-07) to the agentdojo family owner; recount it1 (section 10). Disclose banking ASR semantics in the datasheet and manuscript.
2. Add the two survey documentation entries (PC-02, PC-03) to the manuscript artefact table. No corpus bytes change.
3. Put the D-80 (d) question (refuted PC-01) to the family owner as a design decision, not a defect. Correct prereg rows l.143/l.179 to "pointer only when the issue's rule is class I".
4. Correct the U6-c prediction in `regen-batch.md` (PC-05; routed once for four corpora under CC-04).
5. Method: record a dated section-8 amendment before applying the sample gap rule to stratum-weighted estimates (PC-10). Tools, after the batches: `null_final` for block lists (PC-08, CC-08).
6. Run the targeted L2 import of the 11 run-error and 4 capped logs (section 10) so `survey.internal_server_error_patch@1` is exercised at current main.
7. No exclusion of any data.

**Readiness: `ready-with-caveats`.**

- The sample imports deterministically and cleanly: 120/120 validated, recompute 0 unexplained, j1/j2 byte-identical, DL-1 0 unexplained, redaction clean, mapped = raw 120/120. The population reproduces every README outcome cell exactly.
- Caveats, all owned and routed; none blocks the regeneration:
  - the 11 run errors were not in the sample (targeted import, section 10);
  - PC-04 / PC-12 survey expected row under `validity_defects` (CC-07, family owner);
  - the D-80 (d) design question (family owner, optional);
  - stored `validate.results.differ`, expected-known under amendment 1 until the round re-validates (PC-11, CC-05).
- Not counted (R5, analysis-artefacts): PC-07, PC-08 (CC-08), PC-09 (CC-01), PC-10 (R6).

## 9. Reproduction

Batch (wave 1; plan entry in `tools/precheck/plans/wave1.toml`):

```toml
[[part]]
corpus_id = "ast-survey-agentdojo"
source = "agent-security-tools-survey"
part = "agentdojo-runs"
l1 = ["--use-pin"]
```

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave1 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave1.toml
```

Steps the batch ran (W = `~/.agentprov/migration-work/precheck/ast-survey-agentdojo`, D = `docs/reports/precheck/data/ast-survey-agentdojo`):

```bash
uv run python tools/precheck/l1_scan.py --source agent-security-tools-survey --part agentdojo-runs --corpus-id ast-survey-agentdojo --jobs 2 --emit-fp --use-pin
uv run python tools/precheck/l2_sample.py select --units W/l1-units-agentdojo-runs.jsonl --source agent-security-tools-survey --part agentdojo-runs --corpus-id ast-survey-agentdojo --out D/l2-sample-agentdojo-runs.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-agentdojo-runs.json --corpus W/l2-agentdojo-runs-j2 --source agent-security-tools-survey --part agentdojo-runs --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-agentdojo-runs.json --corpus W/l2-agentdojo-runs-j1 --source agent-security-tools-survey --part agentdojo-runs --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-agentdojo-runs-j2.partial --out D/l2-agentdojo-runs.json --sample D/l2-sample-agentdojo-runs.json --l1-units W/l1-units-agentdojo-runs.jsonl --compare-with W/l2-agentdojo-runs-j1.partial --jobs 2
# inside l2_check:
uv run agentprov validate --corpus W/l2-agentdojo-runs-j2.partial --tiers aer,sem,prov,linkage,shacl,regression --jobs 2
uv run agentprov recompute --corpus W/l2-agentdojo-runs-j2.partial --dry-run --jobs 2 -q
uv run agentprov verify --corpus W/l2-agentdojo-runs-j2.partial --level chain
```

Examiner and verifier scripts (read-only, counts only):

```bash
python3 -I D/exam-scripts/pop.py ~/.agentprov/corpora/ast-survey-agentdojo-p10.partial pop_rows.json   # OS-1, H2-H4, H10
python3 -I D/exam-scripts/hyp.py pop_rows.json                                                          # H4 partial table (PC-03)
python3 -I D/exam-scripts/evf.py W/l2-agentdojo-runs-j2.partial                                        # PC-06
python3 -I D/exam-scripts/evf.py ~/.agentprov/corpora/ast-survey-agentdojo-p10.partial W/l2-agentdojo-runs-j2.partial/executions.jsonl
python3 -I D/exam-scripts/outcomes.py W/l1-units-agentdojo-runs.jsonl W/l2-agentdojo-runs-j2.partial D/l2-sample-agentdojo-runs.json tools/analysis2 os2.json  # section 6, PC-10
# DL-1 (stored -p10 vs W/l2-agentdojo-runs-j2.partial, same 120 ids) -> D/delta-p10-vs-l2.json:
#   D/exam-scripts/aerdiff.py, semdiff.py, markdiff.py, provcls.py, provtypes.py, gaps2.py (each run separately with python3 -I)
```

Follow-ups for the orchestrator: section 10.

## 10. Open follow-ups

Not run in the harmonisation pass. W and D as in section 9.

| # | What | Command | When |
|---|---|---|---|
| 1 | Targeted L2 of the 11 run-error logs (`outcomes.error_present` true in `W/l1-units-agentdojo-runs.jsonl`) plus 4 capped logs, so `survey.internal_server_error_patch@1` and the 10 imposed security values are exercised at current main. Needs a hand-written sample file in `l2-sample` format (no tool produces it yet) | `uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-ast-survey-agentdojo -- uv run python tools/precheck/l2_import.py --sample <sample of the 11 error_present + 4 capped labels> --corpus W/l2-errors-j2 --source agent-security-tools-survey --part agentdojo-runs --jobs 2`, then `uv run python tools/precheck/l2_check.py --corpus W/l2-errors-j2.partial --out W/l2-errors.json --sample <file> --l1-units W/l1-units-agentdojo-runs.jsonl` | after the sample file is written |
| 2 | PC-04: recount banking it1 (subject vs the pizza companion's IBAN) | no script yet (counts-only extension of `D/exam-scripts/pop.py`) | before the datasheet |
| 3 | CC-08 / PC-08: re-run L1 after the `null_final` fix (expect 84 more empty finals flagged) | `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-ast-survey-agentdojo-l1 -- uv run python tools/precheck/l1_scan.py --source agent-security-tools-survey --part agentdojo-runs --corpus-id ast-survey-agentdojo --jobs 2 --emit-fp --use-pin` | after the tool fix lands |
| 4 | CC-05 / PC-11: re-validate a copy of the stored corpus (never in place); expect `results_differ` 0 after re-validation | copy `~/.agentprov/corpora/ast-survey-agentdojo-p10.partial` to `W/stored-copy`, then `uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-ast-survey-agentdojo -- uv run agentprov validate --corpus W/stored-copy --tiers aer,sem,prov,linkage,shacl,regression --jobs 2` | optional, or in the round |
