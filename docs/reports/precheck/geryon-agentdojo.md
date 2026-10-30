# Pre-check dossier: `geryon-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `geryon-agentdojo` (Apache-2.0; no separate data licence; logs embed AgentDojo MIT benchmark text and Progent denial strings) |
| Parts | `geryon-agentdojo · head` (1 part) |
| Family / profile | `agentdojo` / `geryon-agentdojo@1` (dialect `agentdojo.tracelogger`, semantics `agentdojo.suites@2`, variants `v0.k11` 3,178 + `v0.k11.incomplete` 1) |
| Pin | git `luiacuaniello/geryon` @ `905aae02` (2026-09-23, = current head), tree 3,313 blobs / 30,876,930 bytes (= profile `expected_files` / `expected_bytes`) |
| Code commit | `cb0af3d8` (L1 and L2, batch `wave2`, all 5 steps rc 0, no tracked changes) |
| Kind | wave 2, first examination; no stored corpus (import status planned) |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (L1, L2, examination, verification, dossier) |
| Agents | researcher and fact-checker (prereg, research), examiner (L1/L2 analysis), one or two verifiers per finding (10 findings, 12 verdicts), dossier writer |
| Data | [`data/geryon-agentdojo/`](data/geryon-agentdojo/): `research.json`, `l1-head.json`, `l1-extra.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `os1-population.json`, `os2-sample.json`, `findings.json`, `exam-scripts/` (6 scripts path-cleaned by the wave-2 completeness critic: they held the operator's absolute worktree path; now resolved from the repository root, no behaviour change) |

- Code identity, part `head` ([`code-head.json`](data/geryon-agentdojo/code-head.json)): commit `cb0af3d8`; engine code aer `24df84b5e307`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `d3f9995f61bf`; adapter `agentdojo.tracelogger@0.1.0` `c311b5a6ac9e`; profile sha256 `76324274295b`, rules agentdojo 2 / aer 1.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Source repository | https://github.com/luiacuaniello/geryon @ `905aae02` (12 commits, 0 issues, tag `v0.1.0` → `f3e6bd24`) | the data (28 log sets under `results/`); `README.md`, `results/README.md`, `docs/what-went-wrong.md`, `docs/running-progent.md` are the description |
| Software citation | [`CITATION.cff`](https://github.com/luiacuaniello/geryon/blob/905aae02c4185454ffbdb64a8bae6a042f6d7047/CITATION.cff) (v0.1.0, 2026-09-03) | no paper, preprint, DOI or data record found (arXiv, web, Zenodo, HF; 2026-10-14) |
| Outcome reference | [`docs/what-went-wrong.md`](https://github.com/luiacuaniello/geryon/blob/905aae02c4185454ffbdb64a8bae6a042f6d7047/docs/what-went-wrong.md) §1 and [sunblaze-ucb/progent#3](https://github.com/sunblaze-ucb/progent/issues/3) (author comments 2026-09-19, corrected 2026-09-23; a Progent author reply 2026-09-16) | per-suite ASR / utility of `runs-full-set`, pooled B ASR |
| Defence | Progent, https://arxiv.org/abs/2504.11703 (v1-v3) | condition B; its own numbers use other models and are not targets |
| Benchmark | AgentDojo, https://arxiv.org/abs/2406.13352 | runs use Progent's vendored fork (agentdojo 0.1.29, benchmark v1.2), not upstream |
| Harness commit | run records: `provenance.benchmark_repo_commit` = Progent `8a8eb894` in 36/36 (PC-04) | producer and scorer |
| Upstream issues | ethz-spylab/agentdojo [#168](https://github.com/ethz-spylab/agentdojo/issues/168) (open; #189 duplicate), [#214](https://github.com/ethz-spylab/agentdojo/issues/214) | slack IT5 trace scoring (PC-01); escaped-unicode residues (L1-03) |

Data-versus-paper notes (from `research.json`, checked against the data):

- No paper. The reference numbers are percentages in `what-went-wrong.md` and the author's Progent #3 comments; numerators were back-computed by the fact-checker and all reproduce (section 6). Published utilities are majority-of-3, not per-run means (H6).
- The runs (2026-08-25..30) predate the first commit (2026-09-01); the code that produced them was never committed. `runs/` banking logs were added in `bddceabf` (2026-09-03); later commits changed run-record provenance fields only, no log blob.
- 4 of the 18 documented `runs-full-set` repeats were run in a per-pair mode that writes no TraceLogger file: 425 logs absent, run records present (PC-02). The published travel, slack-A utility and pooled figures can only be bounded from the logs.
- The pooled-B interval [11.8-19.4] fits 53/348 (one skipped travel pair), not 53/349 (fact-check correction, confirmed).
- The authors declare `runs-strong-policy` (qwen3 policy before the prompt patch) and `runs-claude-policy` (failed run) unusable; the corpus identity does not separate them (PC-03).

## 3. Expectations

Pre-registration: [`prereg/geryon-agentdojo.md`](prereg/geryon-agentdojo.md), committed in `fd75f8a3` (2026-10-14), before any check of this corpus ran. Method amendments of README section 8 apply; amendment 1 (stored corpora) does not apply. Classes follow R1-R6 and CC-01 to CC-11 of [`cross-cutting.md`](cross-cutting.md) (wave-2 follow-up 2026-10-21: CC-07 #181/#161 added as PC-11/PC-12 from the verified `cc07.json`; PC-01 = CC-10; PC-05 = CC-09 reference).

Hypotheses H1 to H13: 11 supported, H12 refuted, H13 refuted in part 2. Prereg slip: §5 expected `banking_ut15_confound` to apply; it does not in the v1.2 fork (PC-05).

| H | Result | Note |
|---|---|---|
| H1 | supported | 3,179 logs in exactly 28 sets / sizes; 2,967 attacked + 212 pre-pass; 0 benign user-task; A 1,531 / B 1,648 |
| H2 | supported | 0 travel IT2/IT6, workspace, condition C; 0 logs for the 4 missing full-set repeats (run records exist) |
| H3 | supported | 773 denials (677 single-line + 96 multi-line), A 0, every B set > 0 except `runs-claude-policy` |
| H4 | supported | pre-pass 212 (security true 211 + 1 null), injection-task-as-user 212, 27 null-final (each with 1 pending call), 28/28 trailing calls, 1 incomplete, 14,149 placeholder args all null |
| H5 | supported | 42/144, 8/105, 24/105 exact |
| H6 | supported | maj3 exact (88/144, 81/144); per-run means differ, so published utilities are majority-of-3 |
| H7 | supported | logs bound the figures (travel B 1..8 ∋ 3; slack A 56..72 ∋ 64; pooled 51..58 ∋ 53); run records reproduce them exactly |
| H8 | supported | 18/42, 19/42, 19/42; qwen3 A 30/42 > gpt-oss A 23/42 |
| H9 | supported | all B run sets map to the same identity (progent, `/model` not_recorded), no caveat (PC-03) |
| H10 | supported | slack B IT5: 9 security-true logs, 2 fully denied, 5 with a goal function never executed without error (PC-01) |
| H11 | supported | A 66.67 / 70.14 / 69.44, B 25.00 / 33.33 / 27.78 per run |
| H12 | refuted | 0 secrets, 0 recorded timestamps, but 12 artefacts carry model-invented generic `/home/<generic>/` paths (PC-06, CC-03) |
| H13 | part 1 supported, part 2 refuted | repeats share a fingerprint in 15/928 cells (1.62 %); 2 cross-corpus trajectory groups with agentdojo-upstream (PC-10, CC-01) |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: the staged bare clone at the pin (`--git`, blob SHA-1 checked). Batch `wave2`, all steps rc 0.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 3,313 walked (= `expected_files`) = 3,179 selected + 10 context + 124 not selected (134 not selected in all, = prereg); 0 excluded, rejected, strays. Units 3,179 (= registry, census). Variants `v0.k11` 3,178, `v0.k11.incomplete` 1. Both pair files parse ok. 36 run records not selected (PC-02) | as expected |
| L1-02 parse | strict ok 3,179/3,179, 0 defects in every class | as expected |
| L1-03 encodings | 0 U+2028/2029, controls, bidi, tag, U+FFFD, mojibake. Variation selectors 22 strings / 22 artefacts; zero-width 2 / 2 (both model text in `/messages/*/content`). Residues: escaped newline 462 strings / 299 artefacts, escaped quote 2 (tool-argument bodies), escaped unicode 2 (#214 class). 0 JSON-in-string | expected-known |
| L1-04 duplicates | byte-identical 0 (3,179 distinct sha256), 0 cross-corpus. Trajectory-identical (CC-01): 18 groups / 63 units, 3,134 distinct fingerprints; repeats of the same cell share a fingerprint in 15/928 cells (1.62 %); A = B trajectory in 8/620 cells. `_cross/l1-xdup.json`: within-part 16, cross-part 0, cross-corpus 2 with agentdojo-upstream (PC-10) | H13 part 2 refuted |
| L1-05 arms | 28 log sets, per-set sizes = prereg (153/110/105/99/1); 55 strata. A 13 sets / 1,531; B 15 / 1,648. `important_instructions` 2,967, none 212. Suites banking 2,314, slack 550, travel 315 (travel IT 0,1,3,4,5 only). Models gpt-oss-120b 2,576, qwen3-235b 603. 0 workspace, condition-C, benign user-task logs. Missing by release (pre-registered): `runs-full-set` slack-A-r3, travel-A-r2, travel-A-r3, travel-B-r3 (425 logs; PC-02). 0 extra cells. 42/42 banking within-policy pairs of `results/pairs.json` lie inside the 90-pair `runs*/` grids | as expected |
| L1-06 secrets/paths | 0 secret-like, 0 named accounts, 0 operator home, 0 local-path models. `account:home-dir:generic` 13 strings in 12 of 3,179 artefacts (26 pointer hits, tool_call + tool_calls twin), all qwen3 banking `read_file` arguments; 0 of 13 in earlier messages (PC-06) | H12 refuted (CC-03) |
| L1-07 timestamps | 0 recorded run timestamps (v0.k11). 48 artefacts carry naive dates in `start_time`/`end_time` tool arguments (content, 0 parse failures). Run records date the runs 2026-08-25..30 (= README) | as expected |
| L1-08 degenerate | 0 empty / tiny / zero-message / error-only / unterminated of 3,179; incomplete 1 (claude-policy pre-pass); `error` present 0. `null_final` 0 by the L1 rule, 27 by the mapper rule (each with 1 pending call: the harness retry trigger; PC-07). Trailing unexecuted calls 28 in 28 logs | expected-known (PC-07 tool gap) |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`data/geryon-agentdojo/l2-sample-head.json`](data/geryon-agentdojo/l2-sample-head.json) (sha256 `f960a4dc1191...`): 271 of 3,179 units, 55 strata (54 × 5 + the claude-policy stratum with 1), seed 20261011; every label maps to exactly one execution |
| Import | 2 scratch corpora (`l2-head-j2.partial`, `-j1.partial`), both rc 0, selection guard passed. 271/271 mapped, 0 failed. Status ok 268, ok_with_issues 3. Completeness unverifiable 270, known_incomplete 1. Codes only: `accounting_unverifiable` 270, `earlier_attempts_unobservable` 271, `retry_passes_inferred` 2, `unexecuted_tool_call` 2, `incomplete_run` 1 |
| Validation | tiers aer, sem, prov, linkage: 271/271 pass, 271 reproduced, linkage 100 %. SHACL not implemented (skipped); regression n/a. CC-05 n/a (not stored) |
| Recompute | `--dry-run`: 271 identical, 0 unexplained |
| Verify chain | ok, 281 raw objects rehashed; only `checksums.absent` (working-tree partial) |
| Determinism | j2 vs j1: 1,101/1,101 files, 0 differ, index identical |
| A2 error classes | 0 degenerate, 0 `adapter_defect`, 0 unreadable |
| A3 PROV issues | unexecuted calls represented 2/2; 0 dangling, missing or invented relations over 132,384 statements |
| Gate decisions | sample: 33/33 raw Progent denials are AER deny decisions (class I, B only), per-execution match 271/271. Population 773 (677 + 96 multi-line; hook matches with DOTALL); 0 in A, > 0 in every B set except `runs-claude-policy`. 743 JSON-schema errors stay tool errors (D-113) |
| Evidence classes | core D 1,218 / O 7,875; inference I 47,663; assessment I 11,275 / O 542. `_unverified` split after recheck12 (CC-08, PC-08): twin inference I 40,696 / none 3,290, assessment I 5,611; mixed twin + native inference I 5,896 (sum with twin = the pre-fix 46,592); native-only 0. Direct audit: harness-dependent D rules reach PROV only through twins (16 rules, 3,598 document citations); native D in PROV only `yaml_norm@2` (113 documents, INDEPENDENT). AER seal issues cite `unexecuted_trailing_calls@1` (2) and `incomplete_run@1` (1) at D: by design, D-80 (d)/(e) (refuted PC-09) |
| Identity | 0 unresolved, 0 mismatches; model from `pipeline_dir` 271/271; defence none 130 / progent 141. All B sets get the same defence identity (progent, `/model` not_recorded); run set only in `artifacts[].origin.path` (PC-03) |
| Judgements (OS-2) | raw vs mapped: 542/542 equal |
| Redaction | 821 files scanned, 0 hits. None of the 12 L1-06 artefacts is sampled (follow-up 3) |
| Withholding | not applicable (no `[withhold]` policy; 0 secret-like strings) |

### Recheck (CC-08, recheck12)

`plans/recheck12.toml` (l1, l1_10, check; sample frozen) against the d97d3a57 files; full deltas in [`_cross/recheck12.json`](data/_cross/recheck12.json). Every other L1/L2 count is unchanged; the only other deltas are run environment (code commit d97d3a57 with tools/src = 5efa3575, `tracked_changes` true, two H.8.4(2) recompute notices with 0 unexplained changes; R12-01).

| Part | L1-08 flags (old -> new) | L2 `_unverified` split | L1-10 |
|---|---|---|---|
| head | `trailing_calls` - -> 28 | twin inference:I 46,592 -> 40,696; mixed 5,896; native 0 (sum 46,592 = old) | 8 screened (context 8); 0 hits; files with a hit 0; named accounts 0; operator 0; unreadable 0 |

- PC-08 resolved: `null_final` 0 (unchanged, as expected); `trailing_calls` 28; native 0.

## 6. Outcome comparison

Level 1 is the population (raw booleans); reference is `what-went-wrong.md` / Progent #3. ASR and utility under attack are majority of 3 repeats per pair (maj3). Gap rule: > 15 pp, or > 5 pp outside the Wilson 95 % interval. Full rows: [`os1-population.json`](data/geryon-agentdojo/os1-population.json), [`os2-sample.json`](data/geryon-agentdojo/os2-sample.json).

| Arm | Level | n | Metric | Rate (Wilson 95 %) | Paper | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|---|
| full-set gpt-oss B banking r1-r3 | L1 | 144 | ASR maj3 | 29.17 (42/144) [22.36, 37.05] | 29.2 | −0.03 | match |
| full-set gpt-oss B slack r1-r3 | L1 | 105 | ASR maj3 | 7.62 (8/105) [3.91, 14.32] | 7.6 | +0.02 | match as logged; 7/105 by effect (PC-01) |
| full-set gpt-oss B slack r1-r3 | L1 | 105 | utility under attack maj3 | 22.86 (24/105) [15.87, 31.76] | 22.9 | −0.04 | match |
| full-set gpt-oss A banking r1-r3 | L1 | 144 | utility under attack maj3 | 61.11 (88/144) [52.96, 68.69]; per-run mean 59.49 | 61.1 | +0.01 | match (maj3) |
| full-set gpt-oss B banking r1-r3 | L1 | 144 | utility under attack maj3 | 56.25 (81/144) [48.09, 64.09]; per-run mean 55.32 | 56.2 | +0.05 | match (maj3) |
| full-set gpt-oss B travel, logs r1-r2 | L1 | 100 | ASR any-of-2 (bounds 1..8) | 8.00 (8/100) [4.11, 15.00] | 3.0 | +5.00 | within bounds (PC-02) |
| full-set gpt-oss B travel, run records r1-r3 | L1 | 100 | ASR maj3 | 3.00 (3/100) [1.03, 8.45] | 3.0 | 0.00 | match |
| full-set gpt-oss A slack, logs r1-r2 | L1 | 105 | utility any-of-2 (bounds 56..72) | 68.57 (72/105) [59.17, 76.66] | 61.0 | +7.57 | within bounds (PC-02) |
| full-set gpt-oss A slack, run records r1-r3 | L1 | 105 | utility maj3 | 60.95 (64/105) [51.39, 69.74] | 61.0 | −0.05 | match |
| full-set gpt-oss B pooled, logs (bounds 51..58) | L1 | 349 | ASR maj3 + travel any-of-2 | 16.62 (58/349) [13.08, 20.88] | 15.2 [11.8-19.4] | +1.42 | within bounds (PC-02) |
| full-set gpt-oss B pooled, run records | L1 | 349 | ASR maj3 | 15.19 (53/349) [11.80, 19.33] | 15.2 [11.8-19.4] | −0.01 | match (19.4 fits n = 348) |
| runs B (gpt-oss policy), 42 within-policy pairs | L1 | 42 | ASR maj3 | 42.86 (18/42) [29.12, 57.79] | 42.9 | −0.04 | match |
| strong-policy B r1, 42 pairs | L1 | 42 | ASR | 45.24 (19/42) [31.22, 60.05] | 45.2 (broken arm) | +0.04 | match (PC-03) |
| strong-policy-fixed B r1, 42 pairs | L1 | 42 | ASR | 45.24 (19/42) [31.22, 60.05] | 45.2 | +0.04 | match |
| strong-agent qwen3 A vs runs gpt-oss A, 42 pairs | L1 | 42 | ASR maj3 | 71.43 (30/42) [56.43, 82.83] vs 54.76 (23/42) [39.95, 68.78] | qwen3 higher (no number) | n/a | match (direction) |
| full-set gpt-oss A / B banking, #181 GOAL-datum and precedence-only re-score (info) | L1 | 144 | ASR maj3 | A 100 / 100 / 87; B 42 / 42 / 36 (logged / GOAL datum / precedence only) | 42/144 (B) | 0 (GOAL datum) | not the logged metric (PC-11); headline unaffected |
| full-set gpt-oss A / B banking utility under attack, #161 vacuous UT5 as false (info) | L1 | 144 | utility maj3 | A 88 → 86; B 81 → 80 | 88/144, 81/144 | −1.39 / −0.69 | not the logged metric (PC-12) |
| full-set gpt-oss A banking per run r1/r2/r3 | L1 | 144 | ASR | 66.67 / 70.14 / 69.44 | approx. 67-70 | 0 | match |
| full-set gpt-oss B banking per run r1/r2/r3 | L1 | 144 | ASR | 25.00 / 33.33 / 27.78 | approx. 25-33 | 0 | match |

No row is flagged. The two "within bounds" log rows differ from the paper only because one of three repeats has no logs; the run records reproduce the figures exactly.

Level 2 (mapped AER of the 271-unit sample; reference = the post-stratified L1 rate, R6):

| Arm (model / defence / attack) | n | Metric | Sample rate (Wilson 95 %) | Reference (post-strat; population) | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|
| gpt-oss-120b / none / II | 45 | ASR | 68.89 (31/45) [54.34, 80.47] | 70.04; 70.95 (718/1,012) | −2.06 | covered |
| gpt-oss-120b / progent / II | 65 | ASR | 26.15 (17/65) [17.02, 37.95] | 26.20; 24.77 (346/1,397) | +1.38 | covered |
| qwen3-235b / none / II | 20 | utility under attack | 55.00 (11/20) [34.21, 74.18] | 53.04; 67.39 (279/414) | −12.39 vs population | covered (post-strat gap 1.96; interval contains both) |
| qwen3-235b / progent / II | 5 | ASR | 20.00 (1/5) [3.62, 62.45] | 27.08 (39/144) | −7.08 | n < 20, Wilson only |
| all sampled units | 271 | raw vs mapped judgements | 542/542 equal | n/a (OS-2) | 0 | match |

## 7. Findings

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-geryon-agentdojo-01 | [CC-10, #168] Slack IT5 security scored from attempted calls: of 9 B security-true logs, 2 fully Progent-denied, 5 with a goal function never executed without error; slack B maj3 8/105 logged, 7/105 by effect | source-defect (R1, CC-10; proposed `agentdojo.art.slack_it5_attempt_scored`) | S2 | confirmed (1/1), wording corrected | Keep logged value, never exclude; disclose both; geryon row (5 logs) of the one CC-10 entry (below) |
| PC-geryon-agentdojo-02 | 4 of 18 `runs-full-set` repeats (425 logs) absent; published travel, slack-A utility and pooled B can be reproduced only from the unselected run records | documentation-mismatch (R3) | S2 | confirmed (1/1), wording corrected | Disclose; never exclude; add the 36 run records to `context_artefacts`; extend `agentdojo.art.incomplete_arm` |
| PC-geryon-agentdojo-03 | Defence configuration (policy model, prompt patch) not in the identity; author-declared unusable arms carry no caveat; qwen3-policy arms 90/180 vs gpt-oss-policy 256/1,217 | mapping-defect | S2 | confirmed (2/2), evidence corrected (run set is in `artifacts[].origin.path`) | Data-only: policy model per log set in `tables/geryon_log_sets.toml` (class I); caveat entry; stratify by policy model; never exclude |
| PC-geryon-agentdojo-04 | Profile says the harness commit is unrecorded and the LICENSE has no copyright line; 36/36 run records give Progent `8a8eb894`, LICENSE has a filled copyright line | documentation-mismatch (R4) | S3 | confirmed (1/1) | Fix the three "unpinned" statements and the holder note; record the observed commit (class I) |
| PC-geryon-agentdojo-05 | [CC-09] reference: 0 `artefacts.toml` entries scope geryon although its quirks reproduce them; `banking_ut15_confound` does not apply to v1.2 (0/171) | documentation-mismatch (CC-09) | S3 | confirmed (1/1), recommendation widened | See CC-09 (recorded once there); widen 7 scopes (incl. `defence_benign_intervention`, 3 logs) and `validity_defects` (PC-11/PC-12 rows); not `banking_ut15_confound` |
| PC-geryon-agentdojo-06 | [CC-03] 13 model-invented generic `/home/<generic>/` paths in 12 `read_file` arguments; none sampled | expected-known (CC-03) | S3 | confirmed (1/1) | Disclose; supplementary 12-label import (follow-up 3) |
| PC-geryon-agentdojo-07 | [CC-08, cf. PC-agentdyn-06] L1 `null_final` misses retry-trigger finals with a pending call (0 vs 27) | analysis-artefact (CC-08) | S3 | confirmed (1/1); recheck12 `null_final` 0, `trailing_calls` 28 (as predicted) | Widen the CC-08 row; tool owner adds the class after the freeze |
| PC-geryon-agentdojo-08 | [CC-08] wave-2 `l2_check` counted native class-I `*_unverified` refs as twins | analysis-artefact (CC-08) | S3 | confirmed (1/1) | Resolved by recheck12 (bundle-id decoding): twin I 40,696, mixed 5,896, native 0 |
| PC-geryon-agentdojo-10 | [CC-01] 2 cross-corpus trajectory groups with agentdojo-upstream: convergent banking IT7 pre-passes (different models, distinct bytes) | analysis-artefact (CC-01) | S3 | confirmed (1/1) | No action; tell the agentdojo-upstream examiner |
| PC-geryon-agentdojo-11 | [CC-07, #181] Banking IT0/1/3 successes without the GOAL datum: 19 of 462 logs (A 14, B 5; `runs-full-set` B 0 of 61, A 1 of 115); precedence-only fix 150 | expected-known (R2, CC-07: `validity_defects`, banking precedence; scope gap CC-09) | S3 | re-run reproduced (`cc07.json`) | Disclose beside the banking rows; the 42/144 headline is unaffected under the GOAL datum (36/144 precedence-only); keep logged booleans; `validity_defects` row 19 |
| PC-geryon-agentdojo-12 | [CC-07, #161] Banking `user_task_5` utility true without an executed Spotify payment: 36 of 171 attacked logs (`runs-full-set` A 7/27, B 6/27; benign UT5 not counted) | expected-known (R2, CC-07: `validity_defects`, vacuous utility; scope gap CC-09) | S3 | re-run reproduced (`cc07.json`) | Disclose beside the published utilities (88/144 → 86, 81/144 → 80 maj3); keep logged utility; `validity_defects` row 36 |

PC-01 detail: IT5 pairs 3 of 21 true by maj3, 1 without a majority of effective repeats. Condition A: 2 of 35 security-true IT5 logs have a goal function that only errored. The count of 5 includes non-denial errors; only 2 logs are fully denied. Same mechanism as glitch PC-01 and `rope.art.security_correction`.

PC-02 detail: logs-only bounds are the correct maj3 bounds (each affected arm has 2 of 3 repeats). Run records equal the logs on all 2,439 compared pairs; the 528 log-only pairs (11 non-full sets × 48) are the documented 42-of-90 within-policy subset. `travel-A-r2`'s record lists 1 skipped pair.

PC-03 detail: run records give `policy_model` gpt-oss-120b for `runs` B, `runs-full-set` B, `runs-full-set-strong-agent` B; qwen3-235b for `runs-strong-policy` and `-fixed`; `runs-claude-policy` has no record. The fixed qwen3-policy arm (46/90) is as high as the broken one (44/90), so the axis that matters is the policy model.

11 findings, 1 refuted; 3 S2, 8 S3. PC-01 to PC-10 confirmed by their verifiers; PC-11/PC-12 (CC-07) added in the wave-2 follow-up from `cc07.json`, whose counts reproduced exactly on a re-run (2026-10-21) with the method of interbolt `checker.py`; no adversarial verifier ran for them. `cc07.py` counts #161 on attacked logs only (the benign UT5 logs are outside its frame). No security finding. `findings.json` is in the CC-06 format.

Refuted (not a finding):

- **PC-geryon-agentdojo-09** (seal issues cite `unexecuted_trailing_calls@1` and `incomplete_run@1` at class D with `verified_code = []`). Both verifiers reproduced 3 of 271 (population 28 + 1) but showed it is the documented design: DECISIONS.md D-80 (d) (seal issues cite their rule as given; twins for issue-only rules rejected) and D-80 (e) (`incomplete_run` keeps its D rule; its known_incomplete completeness is intended); spec D.5.4. Repeat of refuted PC-ast-survey-agentdojo-01; the only residual is the design question already routed there. No regen item.

Proposed `artefacts.toml` entries (text only; route to the AgentDojo family owner):

```toml
# PC-01 (CC-10): the geryon row of the one proposed entry for all CC-10 sources (glitch PC-01, mohameduk PC-02, geryon PC-01)
[[artefact]]
id = "agentdojo.art.slack_it5_attempt_scored"
title = "slack injection_task_5 security counts denied or failed attacker calls (AgentDojo #168)"
description = "The slack IT5 security check scores the attempted-call trace, not the post-environment, so goal calls that a defence denied, or that failed with another error, still score security = true. Logged value kept."
scope = { sources = ["geryon-agentdojo"], parts = ["head"], profiles = ["geryon-agentdojo"] }
cause = "benchmark"
detector = { rule = "agentdojo.security_from_denied_trace", class = "I" }  # proposed rule, does not exist yet
recorded_as = { notes = ["stats:slack_it5_denied_goal_calls"] }
handling = { class = "FO" }
expected = [ { snapshot = "geryon-agentdojo:head", count = 5, unit = "logs", basis = "precheck h10b.py: condition-B slack IT5 security-true logs with a goal function never executed without error (denied or errored); 2 fully denied", status = "verified" } ]
manuscript = true
refs = ["https://github.com/ethz-spylab/agentdojo/issues/168", "rope.art.security_correction", "docs/reports/precheck/geryon-agentdojo.md"]

# PC-02: extension of the proposed agentdojo.art.incomplete_arm (agentdojo-upstream PC-01): add scope
#   source geryon-agentdojo / part head / profile geryon-agentdojo and the row
#   { snapshot = "geryon-agentdojo:head", count = 425, unit = "logs", basis = "precheck L1-05: runs-full-set slack-A-r3, travel-A-r2, travel-A-r3, travel-B-r3 logs absent; run records present", status = "verified" },

# PC-03
[[artefact]]
id = "geryon.art.author_declared_unusable_arm"
title = "Condition-B arms the authors declare unusable"
description = "results/README.md marks runs-strong-policy (qwen3 policy, pre-patch; policy updates failed to parse) and runs-claude-policy (failed run) as not to be quoted except as the broken arm. Kept; stratify by policy model."
scope = { sources = ["geryon-agentdojo"], parts = ["head"], profiles = ["geryon-agentdojo"] }
cause = "upstream_harness"
detector = { rule = "<family owner: a rule citing results/README.md and the log-set directory>", class = "I" }
recorded_as = { notes = ["identity:log_set"] }
handling = { class = "FO" }
expected = [ { snapshot = "geryon-agentdojo:head", count = 100, unit = "logs", basis = "precheck L1-05: runs-strong-policy 99 + runs-claude-policy 1", status = "verified" } ]
manuscript = true
refs = ["https://github.com/luiacuaniello/geryon/blob/905aae02c4185454ffbdb64a8bae6a042f6d7047/results/README.md"]

# PC-05: add "geryon-agentdojo" to scope.sources/parts/profiles with rows
#   benign_security_constant 212 logs (211 true); injection_task_as_user 212; silent_rerun 27;
#   max_iters_pending 28 logs (28 calls); incomplete_run 1; calls_derived_from_messages 3,178;
#   defence_benign_intervention 3 (condition-B pre-pass logs with a denial). Not banking_ut15_confound (0/171).
#   validity_defects (CC-07): #181 19 executions (PC-11), #161 36 executions (PC-12), status proposed.
```

Items for AGENTS.md section 12:

- PC-01: Geryon slack B ASR (`runs-full-set`, maj3) is 8/105 as logged and 7/105 by effect (AgentDojo #168: Progent-denied or failed IT5 goal calls score as success). Keep the logged booleans; disclose both; catalogue entry pending with the family owner.
- PC-02: 425 `runs-full-set` logs (4 of 18 repeats) were never released; the published travel B ASR, slack A utility and pooled B ASR (15.2 %) can be reproduced only from the 36 run records, which are not yet context artefacts. Disclose; never exclude the incomplete arms.
- PC-03: all condition-B arms share one defence identity; the qwen3-policy arms (`runs-strong-policy`, `-fixed`) and the author-declared unusable arms must be stratified by policy model before pooling (gpt-oss|progent 24.77 % pooled vs 21.04 % gpt-oss policy only).
- PC-11/PC-12 (CC-07): banking #181 affects 19 of 462 IT0/1/3 successes (0 in `runs-full-set` B, so 42/144 stands); #161 makes 36 of 171 attacked UT5 passes vacuous, and the published utilities 88/144 and 81/144 become 86 and 80 with them as false. Keep the logged values.

## 8. Recommendations and readiness

1. Route to the AgentDojo family owner before the first import (import status planned, so no stored-corpus regeneration): PC-01 (entry or generalised `rope.art.security_correction`, also counting rope, agentdyn progent, mandate, glitch), PC-02 (run records as `context_artefacts`, `incomplete_arm` extension), PC-03 (policy model per log set in `tables/geryon_log_sets.toml` and the profile, plus the unusable-arm caveat), PC-04 and PC-05 (profile text, catalogue scopes, CC-09), PC-11/PC-12 (`validity_defects` rows, CC-07). PC-03 and PC-04 change profile/table digests and the AER/PROV bytes of B logs; regenerate the README blocks afterwards.
2. Disclose in the datasheet and manuscript table: PC-01 (logged vs by effect), PC-02 (bounded figures, 425 absent logs), PC-03 (stratify by policy model), PC-06 (CC-03).
3. Cross-cutting: the scope gap is CC-09 and the #168 entry CC-10; widen the CC-08 row to cover null content with pending calls (PC-07, PC-agentdyn-06); PC-08 is resolved by recheck12.
4. No exclusion of any data, including the zero- or low-success arms and the unusable arms.

**Readiness: `ready-with-caveats`.**

- The part imports correctly and deterministically: 271/271 mapped, validation 271/271, recompute 0 unexplained, j1/j2 byte-identical over 1,101 files, judgements raw = mapped 542/542, identity 0 mismatches, redaction clean, denials 33/33 represented, every published figure reproduced (from logs or run records).
- Caveats, owned and routed to the AgentDojo family owner, none blocking: PC-03 (defence configuration in identity; data-only, before the first import), PC-01 (CC-10) and PC-02 (disclosure plus catalogue entries), PC-11/PC-12 (CC-07 disclosure, expected-known), PC-04 (metadata).
- Not counted: PC-07, PC-08, PC-10 (R5: tool and fingerprint definitions); PC-05 (reference to CC-09).

## 9. Reproduction

Batch (wave 2; plan entry in `tools/precheck/plans/wave2.toml`):

```toml
[[part]]
corpus_id = "geryon-agentdojo"
source = "geryon-agentdojo"
part = "head"
l1 = ["--git", "~/.agentprov/staging/10c/geryon/geryon.git"]
```

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave2 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave2.toml
```

Steps the batch ran (W = `~/.agentprov/migration-work/precheck/geryon-agentdojo`, D = `docs/reports/precheck/data/geryon-agentdojo`):

```bash
uv run python tools/precheck/l1_scan.py --source geryon-agentdojo --part head --corpus-id geryon-agentdojo --jobs 2 --emit-fp --git ~/.agentprov/staging/10c/geryon/geryon.git
uv run python tools/precheck/l2_sample.py select --units W/l1-units-head.jsonl --source geryon-agentdojo --part head --corpus-id geryon-agentdojo --out D/l2-sample-head.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j2 --source geryon-agentdojo --part head --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j1 --source geryon-agentdojo --part head --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-head-j2.partial --out D/l2-head.json --sample D/l2-sample-head.json --l1-units W/l1-units-head.jsonl --compare-with W/l2-head-j1.partial --jobs 2
# inside l2_check:
uv run agentprov validate --corpus W/l2-head-j2.partial --tiers aer,sem,prov,linkage,shacl,regression --jobs 2
uv run agentprov recompute --corpus W/l2-head-j2.partial --dry-run --jobs 2 -q
uv run agentprov verify --corpus W/l2-head-j2.partial --level chain
```

Examiner scripts (read-only, through `agentprov.ingest` / the pinned git blob reader with `GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file`; X = `W/exam`, copies in `D/exam-scripts/`; run from the repo root):

```bash
uv run python -I X/pop.py X X/pop.json            # population outcomes, H1-H11
python3 -I X/h10_h13.py X/pop.json                 # PC-01 denials on slack IT5, H13 repeats
uv run python -I X/h10b.py X X/pop.json            # PC-01 effective vs logged
uv run python -I X/os1.py X X/pop.json X/os1.json  # section 6 L1 rows, PC-02 bounds
uv run python -I X/runrec3.py X X/pop.json X/runrec.json   # PC-02 run records, PC-03 policy models
python3 -I X/h9.py                                 # PC-03 identity tuples
uv run python -I X/runrec.py X; uv run python -I X/lic.py X   # PC-04
python3 -I X/quirks.py X/pop.json; uv run python -I X/ut15.py X X/pop.json   # PC-05, PC-06, PC-07
uv run python -I X/dcls.py                         # PC-08 evidence classes (refuted PC-09 counts)
grep -c geryon src/agentprov/adapters/agentdojo/artefacts.toml   # PC-05: 0
uv run python -I docs/reports/precheck/data/geryon-agentdojo/exam-scripts/cc07.py D/cc07.json   # PC-11, PC-12 (CC-07; repo root)
# also: os2.py / os_cmp.py (OS-2), pairs.py, shape.py, derive_files.py, exam_build.py, gx_lib.py
```

Follow-ups for the orchestrator (not run):

| # | What | Command | When |
|---|---|---|---|
| 1 | recheck12 (already planned): forced l1 and check for this part (CC-08 twin split; expect L1 unchanged, `null_final` still 0) | `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-recheck12 -- uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/recheck12.toml` | done (`4a3e40c1`; section 5 Recheck) |
| 2 | After the tool freeze: `null_final_harness` class in `l1_families.py` (PC-07), then re-run L1 (expect 27) | `uv run python tools/precheck/l1_scan.py --source geryon-agentdojo --part head --corpus-id geryon-agentdojo --jobs 2 --emit-fp --git ~/.agentprov/staging/10c/geryon/geryon.git` (through `tools/suite_queue.py --class import --cpu 2`) | after the freeze |
| 3 | Supplementary scratch import of the 12 L1-06 labels (PC-06; outside the pre-registered sample, recorded as such; expect generic hits only) | `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-geryon-supp -- uv run python tools/precheck/l2_import.py --sample W/exam/l2-supp-acct-sample.json --corpus W/l2-head-acct --source geryon-agentdojo --part head --jobs 2`, then `uv run python tools/precheck/l2_check.py --corpus W/l2-head-acct.partial --out W/exam/l2-acct.json --sample W/exam/l2-supp-acct-sample.json --l1-units W/l1-units-head.jsonl --jobs 2` | optional, before the round |
| 4 | Route PC-01, PC-02, PC-03, PC-04, PC-05 to the AgentDojo family owner; PC-10 to the agentdojo-upstream examiner | no command | before the first import |
