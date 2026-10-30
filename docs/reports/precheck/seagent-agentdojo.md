# Pre-check dossier: `seagent-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `seagent-agentdojo` (data CC-BY-4.0, code Apache-2.0, vendored AgentDojo MIT; `paper.pdf` not relicensed) |
| Parts | `seagent-agentdojo · head` (1 part; registry status `planned`, DF-3) |
| Family / profile | `agentdojo` / `seagent-agentdojo@1` (dialect `agentdojo.tracelogger`, variant `v1.k14`, semantics `agentdojo.suites@2`; identity table `tables/seagent_run_dirs.toml`, D-152) |
| Pin | Zenodo 10.5281/zenodo.23218779, `seagent-acsac2026-ae-v2.zip` (sha256 `e15a8f0f…764bd`, verified at L1 and import) |
| Code commit | L1 `d97d3a57`; L2 import j2 (batch `wave5`) and j1 + check (batch `followup2`); `code-head.json` commit `4a3e40c1`, tracked_changes false |
| Kind | wave 5, first examination (not in FA or E2); no stored corpus |
| Date | 2026-10-14 (prereg, research), 2026-10-16 (L1, L2), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), examiner (this dossier); adversarial verifier 2026-10-21 (11/11 confirmed, 2 wording corrections: PC-01, PC-10; scripts `~/.agentprov/migration-work/precheck/seagent-agentdojo/exam/verify/v1-v5.py`) |
| Data | [`data/seagent-agentdojo/`](data/seagent-agentdojo/): `research.json`, `l1-head.json`, `l1-09-head.json`, `l1-10-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `exam-census.json`, `os1-population.json`, `os2-sample.json`, `cc07.json`, `findings.json`, `exam-scripts/` |

- Code identity, part `head` ([`code-head.json`](data/seagent-agentdojo/code-head.json)): commit `4a3e40c1` (tracked_changes false); engine code expand `3b1d412bb77a`, aer `856b7a09e0cf`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `agentdojo.tracelogger@0.1.0` `03d8bc6d30df`; profile `seagent-agentdojo@1` `30b76ce0183f`; rules aer@1 `55b64d5e05ba`, agentdojo@2 `d4d9d6c8074a`; prov rules `79b0a1e78dc7`; limits `5d6dbb210259`; lockfile `b0455f1058c8`; Python 3.14.8. The j1 scratch corpus records adapter digest `0f8bc8aa6e5b` and, in `derivation.json`, aer engine digest `7e71c65f`: adapter and aer code moved between the two batches (PC-10).

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Data record | https://zenodo.org/records/23218779 (concept record, 4 versions; pin = latest) | the data; 5,342 logs CRC-identical in v2 and v4 |
| Accepted paper | SEAgent, ACSAC 2026 (`seagent-ae/paper.pdf` in the deposit) | Table 2 macro and Table 3 per-suite ASR/UUA = outcome reference |
| Preprint | https://arxiv.org/abs/2509.22256 (v1-v4, "CSAgent") | v1 Table 4 PVAgent travel of 140 (H9) |
| Authors' provenance note | deposit `aggregate-results/agentdojo-provenance/` (README, workbook, csv) | baseline 47.18 / 52.09; SEAgent workspace UUA 312/560 erratum |
| AgentDojo | https://arxiv.org/abs/2406.13352; harness 0.1.34, benchmark v1.2.1 | producer and scorer |
| Upstream issues | ethz-spylab/agentdojo #181, #161, #168, #189, #214 | CC-07, CC-10 |
| AgentSpec | https://github.com/haoyuwang99/AgentSpec (revision `e6fa3902e2cf`, no licence upstream) | the agentspec arm |

Data-versus-paper notes (checked against the data):

- Every AgentSpec-LLM, PVAgent, SEAgent and SEAgent-RF suite cell of the paper and workbook reproduces from the raw `security`/`utility` booleans with 0 runs off (40 of 40 cells, section 6).
- The paper prints SEAgent workspace UUA as 50.71%. The logs give 312/560 (55.71%), as the authors' provenance note states (PC-06).
- The paper's Vanilla row has no episodes in the deposit. The deposited baseline arm gives the authors' 47.18 / 52.09 (PC-07).
- The SEAgent guard writes a shape that no profile note describes. It renames the blocked call to `<tool>BLOCKED_BY_SEAGENT`, answers it with an empty tool message, drops the other calls of the batch and then adds a user-role warning. This shape is the cause of the `failed` status (PC-01, PC-02).

## 3. Expectations

Pre-registration: [`prereg/seagent-agentdojo.md`](prereg/seagent-agentdojo.md), committed in `fd75f8a3` (2026-10-14) before any check of this corpus. Amendments 2-5 (README section 8) apply. Amendment 1 does not, because there is no stored corpus. Stratum key: `kind × arm × suite`, 40 strata.

| H | Result | Note |
|---|---|---|
| H1 | supported | 26,033 = 5,342 + 37 context + 20,654 not selected; arms 1,060/1,060/1,081/1,081/1,060; attacked 4,685, `none` 657 |
| H2 | supported | strict parse 5,342/5,342, every class 0 |
| H3 | supported | 0 U+FFFD, mojibake, bidi/tag; escaped `\uXXXX` 598 files (#214) |
| H4 | refuted as worded | 0 byte-identical, 0 cross-corpus. 150 trajectory-identical attacked groups span arms (CC-01, not copies; PC-11) |
| H5 | supported | `0.1.34` / `v1.2.1` 5,342/5,342 |
| H6 | supported | IT6 20 attacked + 1 prepass in pvagent and seagent travel only |
| H7 | supported | 40/40 cells exact, incl. seagent workspace UUA 312 (PC-06) |
| H8 | supported | baseline macro 47.1825 / 52.0933; does not reproduce the paper's Vanilla (PC-07) |
| H9 | supported | pvagent travel of 140: 26 / 57; IT6 7 / 9 of 20 |
| H10 | supported | benign macro 75.119 / 34.003 / 47.143 / 70.045 |
| H11 | supported | `duration` macro 10.7515 / 19.2269 / 11.2701 / 10.8084 s |
| H12 | supported | 5,342 naive. Per-arm ranges within the run-directory dates; none after 2026-03-26T14:20 (range level) |
| H13 | supported | 0 secret-like or account-path hits in the logs or the 37 context files |
| H14 | refuted as worded | 0 empty, incomplete or error-only. 1 L1 null-final (an empty text block); the product counts 0 (PC-09) |
| H15 | supported | 960 warnings / 863 logs, seagent arms only; 740 call-less assistant messages / 541 logs, pvagent only |
| H16 | reported | agentspec slack IT5: 8 of 8 successes have no executed membership call (PC-03, CC-10) |
| H17 | supported, with diagnosis | all 200 units pass every stage; failed 7 = sampled units among the 94 `missing_tool_result` logs. The 94 are guard batch aborts (PC-01). j1/j2 differ only in code digests (PC-10) |
| H18 | gap rule fired once, investigated | baseline UUA sample +17.9 pp (n = 20); raw = mapped; the population reproduces the reference, so this is sampling variance |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: the staged zip (`--input`, archive mode, pin verified). Tool `l1_scan` at `d97d3a57`, 6.2 s, batch `wave5`, all L1 steps rc 0 (`l1_09` skipped: no metadata members).

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 26,033 walked = 5,342 selected + 37 context + 20,654 not selected; 0 excluded / rejected; units 5,342 = registry = census | as expected (H1) |
| L1-02 parse | strict ok 5,342/5,342; 0 duplicate keys, non-finite, big ints, surrogates, BOM, trailing data, invalid UTF-8, truncation, depth | as expected |
| L1-03 encodings | escaped newline 2,293 files / 3,481 strings (tool outputs 3,463, call args 18); escaped quote 477 / 528; escaped `\uXXXX` 598 / 833 (tool outputs, #214); JSON-in-string 1; 0 of every other class | as expected (H3) |
| L1-04 duplicates | byte-identical 0; trajectory-identical (CC-01) 174 groups / 417 units: multi-arm attacked 150 (364 units), multi-arm benign 20, mixed 1, single-arm 3; 22 attacked groups differ only by injection task; `_cross/l1-xdup.json`: 0 seagent groups across parts or corpora | H4 refuted as worded (PC-11) |
| L1-05 arms | 40 strata; per arm × suite attacked 144/105/120/560 (pvagent and seagent travel 140), prepass 9/5/6/14 (7 for pvagent and seagent travel), perf 16/21/20/40; pipeline dirs 2,996/226/1,060/950/110; 336 logs with a model id without a date | as expected (§3) |
| L1-06 secrets/paths | logs 0 / 5,342; L1-10: 37 context files screened, 0 hits, 0 operator | as expected (H13) |
| L1-07 timestamps | `/evaluation_timestamp` 5,342/5,342, naive, 0 parse failures, 2025-07-29..2026-03-26; 5 units non-monotone only in tool-argument calendar times (benchmark content) | as expected (H12) |
| L1-08 degenerate | flags: `trailing_calls` 317 (= census `unexecuted_tool_call` 317), `null_final` 1; 0 empty / tiny / error-only / incomplete | null-final 1 (PC-09) |
| L1-09 | 0 metadata members | n/a |
| L1-10 | 37 context (3 docs, 10 csv, 24 log) screened, 0 hits | as expected |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`l2-sample-head.json`](data/seagent-agentdojo/l2-sample-head.json) (sha256 `d7809e32…`): 200 of 5,342, 40 strata × 5, seed 20261011 |
| Import | j2 (wave 5) and j1 (followup2), both **exit 1** because the importer exits 1 when `failed` > 0. Counters are equal: 200 mapped / annotated / derived / validated, sealed clean 129, with issues 64, **failed 7**, 0 degenerate, 0 `adapter_defect`; all 200 labels join 1:1 to executions |
| Failed status (diagnosis) | All 7 carry `map.missing_tool_result` at error severity (rule `agentdojo.unexecuted_trailing_calls@1`). The sample's 7 are exactly the sampled labels among the population's 94 such logs. Each is a SEAgent guard batch abort: one call is renamed `<tool>BLOCKED_BY_SEAGENT` and answered by an empty tool message, the batch's other calls get no message, and a user-role warning follows. The runner applies the spec rule (failed if any issue has severity error). The defect is the family mapper's treatment of guard-skipped calls as a declared loss: the source property is real, the error severity is ours (PC-01) |
| Validation | tiers aer, sem, prov, linkage: 200/200 pass, 200 reproduced, linkage 100%. SHACL is not implemented (skipped); regression n/a |
| Recompute | `--dry-run`: 200 identical, 0 changed, 0 unexplained (notice: aer code digest changed, declared versions equal) |
| Verify chain | 0 failures; only `checksums.absent` (working tree) |
| Determinism | 5,987 files on each side, index identical. 1 compared file differs: `corpus.json`, at `/adapters/0/code_sha256` only. `derivation.json` (excluded from the comparison by `l2_check` by design) also differs, in stage 1 adapter and aer engine digests and `fn_digest` (verifier). Both are code moves between the two batches (PC-10). All AER/SEM/PROV/validation bytes are equal |
| A2 error classes | `accounting_unverifiable` 200, `earlier_attempts_unobservable` 200, `unattributed_additional_user_message` 40, `orphan_tool_result` 20, `agentdojo.unknown_message_shape` 20, `unexecuted_tool_call` 11, `accounting_inconsistent` 9, `missing_tool_result` 7; completeness known_incomplete 9 (the 7, plus 2 whose skipped calls precede the blocked call) |
| A3 PROV issues | 0 dangling / missing / invented relations over 84,935 statements / 140,749 relation arguments; 13 unexecuted call parts represented; 723 tool executions with a call |
| Gate decisions | none mapped. 41 blocked calls appear in AER as `tool_execution` status ok under the renamed tool name (population 960) (PC-02) |
| Evidence classes | class D only from engine rules: core `aprov.n_gap@1` 749, `aprov.n_capture_profile@1` 200, assessment `aprov.a_label@1` 5. Agentdojo D rules are cited only by their `_unverified` twins: twin inference I 23,303, assessment I 4,330, inference none 2,306; mixed inference I 3,890; native unverified 0 |
| Judgement origins | 103 harness-default security judgements (perf + prepass, `benign_security_constant`) excluded from ASR |
| Identity | defence from the run-dir table 200/200: baseline→`none`, agentspec, pvagent, seagent→`seagent-initial`, seagent-RF/rf→`seagent-refined`. `*-seagent_mcp` resolves to 3 defences, as designed (D-152). Model `deepseek-v3-250324` 175, `deepseek-v3` 25 (date-less kept). 0 unresolved, 0 direct mismatches |
| Judgements (OS-2) | raw vs mapped on the sample: ASR n/k and UUA k equal for all 5 defences ([`os2-sample.json`](data/seagent-agentdojo/os2-sample.json)) |
| Redaction | 608 AER/SEM/PROV files, 0 hits |
| Withholding | no policy (inert, as pre-registered) |

## 6. Outcome comparison

Level 1 is the population (raw booleans). Travel is IT0-5 (120) for every arm; prepass logs are excluded. Reference is the paper Table 3 or the workbook (counts). Gap rule: > 15 pp with n ≥ 20, or > 5 pp outside Wilson 95%. Full rows: [`os1-population.json`](data/seagent-agentdojo/os1-population.json). **40 of 40 reference cells match exactly (0 runs off); the gap rule fires on none.**

| Arm | Suite | n | ASR k (paper) | UUA k (paper) | Verdict |
|---|---|---|---|---|---|
| agentspec | banking / slack / travel / workspace | 144 / 105 / 120 / 560 | 6 / 43 / 41 / 20 (=) | 58 / 19 / 29 / 311 (=) | match; slack ASR includes 8 IT5 attempts (PC-03); banking UT5 vacuous (PC-05) |
| pvagent | same | same | 0 / 0 / 19 / 4 (=) | 53 / 5 / 48 / 283 (=) | match |
| seagent | same | same | 0 / 0 / 0 / 0 (=) | 65 / 26 / 49 / **312** (paper prints 284) | match with the deposit (PC-06) |
| seagent-RF | same | same | 0 / 0 / 0 / 0 (=) | 81 / 40 / 65 / 383 (=) | match |
| baseline (deposited) | same | same | 58 / 96 / 59 / 44 | 79 / 67 / 35 / 339 | no per-suite reference; macro below |

| Arm | Macro ASR (ref) | Macro UUA (ref) | Benign utility macro (ref) | Perf duration macro s (ref) |
|---|---|---|---|---|
| agentspec | 20.7143 (20.715) | 34.5188 (34.5225) | 57.6042 (none) | n/a |
| pvagent | 4.1369 (4.135) | 33.0258 (33.0275) | 34.003 (34.0025) | 19.2269 (19.225) |
| seagent | 0 (0) | 41.6121 (41.61) | 47.1429 (47.1425) | 11.2701 (11.27) |
| seagent-RF | 0 (0) | 54.2262 (54.2275) | 70.0446 (70.045) | 10.8084 (10.81) |
| baseline | 47.1825 (47.18 deposit; paper Vanilla 46.61) | 52.0933 (52.09; Vanilla 54.26) | 75.119 (75.12) | 10.7515 (10.7525) |

Extra: pvagent travel of 140 is 26/140 ASR and 57/140 UUA (arXiv v1, exact). The IT6 subset is pvagent 7/20 / 9/20 and seagent 9/20 / 8/20.

Disclosure re-scores (info, not the logged metric): agentspec slack ASR 35/105 = 33.33 (logged 40.95; macro 18.81) without the 8 IT5 attempts (CC-10). Baseline banking ASR 49/144 = 34.03 (logged 40.28) with the #181 GOAL datum. Banking UUA without vacuous attacked UT5 passes (#161): agentspec 49, seagent 59, seagent-RF 75, baseline 77, pvagent ≥ 48 of 144.

Level 2 (mapped AER of the 200-unit sample, pooled over suites, 5 per suite stratum). Raw equals mapped in every arm. References are the paper macros (§4 of the prereg).

| Arm (defence) | Metric | n | Sample (Wilson 95%) | Reference | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|
| none (baseline) | ASR | 20 | 35.0 (7/20) [18.1, 56.7] | 47.18 | −12.18 | within rule |
| none (baseline) | UUA | 20 | 70.0 (14/20) [48.1, 85.5] | 52.09 | +17.91 | **flagged**, investigated: raw = mapped, population = 52.09 exactly, reference inside the interval → sampling variance, not a finding |
| seagent-initial | ASR | 20 | 0.0 (0/20) [0, 16.1] | 0 | 0 | match |
| seagent-initial | UUA | 20 | 45.0 (9/20) [25.8, 65.8] | 41.61 | +3.39 | within rule |
| agentspec | ASR / UUA | 19 | 5.26 [0.9, 24.6] / 52.63 [31.7, 72.7] | 20.72 / 34.52 | −15.46 / +18.11 | n < 20 (1 prepass drawn) |
| pvagent | ASR / UUA | 19 | 5.26 [0.9, 24.6] / 52.63 [31.7, 72.7] | 4.14 / 33.03 | +1.12 / +19.60 | n < 20 |
| seagent-refined | ASR / UUA | 19 | 0.0 [0, 16.8] / 47.37 [27.3, 68.3] | 0 / 54.23 | 0 / −6.86 | n < 20 |
| none / pvagent / seagent-initial / seagent-refined / agentspec | benign utility | 20 each | 75.0 / 40.0 / 60.0 / 65.0 / 55.0 | 75.12 / 34.00 / 47.14 / 70.05 / (57.60 L1) | −0.12 / +6.0 / +12.86 / −5.05 / −2.6 | within rule |

## 7. Findings

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-seagent-agentdojo-01 | SEAgent guard batch abort mapped as a lost result: 166 never-executed calls in 107 logs. 94 logs get `missing_tool_result` at error severity and index status `failed` (7/200 in L2), so every import exits 1; 13 logs (their only skipped call at batch index 0) get only `accounting_inconsistent` | mapping-defect (family/profile gap; runner per spec) | S2 | confirmed | AgentDojo family owner, with D-153: add a quirk that records the skipped calls as unexecuted calls of a defence intervention (warning), the same way before and after the blocked call. Byte-changing for 107 logs, so it belongs in the regen list and needs approval. Never filter `failed` out of rates |
| PC-seagent-agentdojo-02 | The blocked call is mapped as an executed tool: 960 `<tool>BLOCKED_BY_SEAGENT` calls become `tool_execution` status ok with an empty result (41 in the sample); no deny decision | mapping-defect | S2 | confirmed | same route: map it as a deny decision on the original tool, as interbolt's `defence_denial_message` does; disclose the tool-execution counts until then |
| PC-seagent-agentdojo-03 | [CC-10, #168/#189] agentspec slack IT5: all 8 successes have no executed membership call | source-defect (CC-10, R1) | S2 | confirmed | add 8 to `agentdojo.art.slack_it5_attempt_scored`; disclose beside the AgentSpec slack ASR and macro |
| PC-seagent-agentdojo-04 | [CC-07, #181] baseline banking IT0/1/3: 9 of 25 successes lack the GOAL datum; 0 successes in the other arms | expected-known (CC-07) | S3 | confirmed | `validity_defects` scope + count 9 |
| PC-seagent-agentdojo-05 | [CC-07, #161] banking UT5 utility true 50/50; 30 without an executed Spotify payment (agentspec 10, baseline 2, pvagent 5, seagent 7, seagent-RF 6) | expected-known (CC-07) | S3 | confirmed | `validity_defects` scope + count 30; disclose (inflates the defended arms most) |
| PC-seagent-agentdojo-06 | Paper Table 3 SEAgent workspace UUA 50.71%; logs 312/560, as the deposit's note says | documentation-mismatch (R3) | S3 | confirmed | cite the deposit's correction |
| PC-seagent-agentdojo-07 | The paper's Vanilla row is not deposited; the baseline arm gives 47.18 / 52.09 | documentation-mismatch (R3) | S2 | confirmed | datasheet: label the baseline as the December rerun; keep it |
| PC-seagent-agentdojo-08 | [CC-09] no `artefacts.toml` entry scopes this source; quirk counts verified | documentation-mismatch (CC-09) | S3 | confirmed | widen scopes with these counts |
| PC-seagent-agentdojo-09 | [CC-08] L1 null-final 1 (empty text block) vs product/profile 0 (trigger `content is None`) | analysis-artefact (R5) | S3 | confirmed | question to the family owner on v1.k14 empty finals |
| PC-seagent-agentdojo-10 | Determinism pair spans two code states (code digests only: adapter in `corpus.json`; adapter, aer engine and `fn_digest` in `derivation.json`) | analysis-artefact (R5) | S3 | confirmed | post-check: both imports in one chain |
| PC-seagent-agentdojo-11 | [CC-01] 150 multi-arm trajectory-identical attacked groups; 0 byte-identical | analysis-artefact (CC-01) | S3 | confirmed | none; verifier compares timestamps in a few groups |

PC-01 detail. There are 960 blocked batches (seagent 575, seagent-RF 385; 0 in other arms). Each batch has exactly 1 renamed call and exactly 1 tool message, which answers the renamed call (error null, empty content). The next message is a user-role warning in 960 of 960, and the batch is never the last assistant turn. Of the 166 skipped calls, 140 follow the blocked call and 26 precede it. The mapper flags only the skipped calls at a batch index at or beyond the number of results, so 94 logs get `missing_tool_result`: 51 seagent, 43 seagent-RF; 84 security, 10 perf; the same 94 as the census and the part-A trial. The other 13 logs get only `accounting_inconsistent`: 16 logs have only skipped calls before the blocked one, and the 13 unflagged are those whose single skipped call sits at batch index 0 (below the one result), so the outcome depends on call position, not on what the guard did. The `failed` status is therefore not a runner or tool defect. It is also not data loss: the source never executed these calls, and the family rule's declared-loss severity misdescribes a defence intervention. The part-A trial calls this "a disclosed source fact". The source shape is a fact; the error severity is ours. All 94 `failed` executions are defence-intervention runs, so filtering on status would be an outcome-dependent exclusion.

7 findings count toward readiness: PC-01 to PC-07; PC-08 is a CC-09 reference. Refuted: none. No security finding.

Verifier notes (2026-10-21, independent recounts, `exam/verify/v1-v5.py`):

- PC-01: own positional rule gives 960 / 166 / 107 / 94; every flagged log has a blocked batch (0 other causes). Alternative "results lost by the logger" rejected: 33 of 166 skipped calls are re-issued later with identical function and args, and all 960 blocked-call results are empty strings. Not R2: D-153 covers only the warnings; the part-A line is a report, not a quirk. The 7 failed units keep their judgements (raw = mapped), so S2, not S1.
- PC-02: 749 AER tool executions in the sample, 41 blocked with status ok, no decision record kind; precedents `rope.art.guard_denial` and the interbolt denial quirk.
- PC-03/04/05: re-counted on wider bases (every tool, every argument field); 8/8, 9/25, 30/50 unchanged.
- PC-07: the baseline arm is one run per suite (2025-12-23 security); its suite counts match none of the paper's Vanilla cells.
- PC-10: `derivation.json` also differs (aer engine digest, `fn_digest`); `l2_check` excludes it by design. Scope corrected, verdict unchanged.
- PC-11: 171/171 multi-arm groups have distinct `evaluation_timestamp` and `duration` and different run dirs: separate runs, not copies.
- PC-08 addendum: the 10 perf logs with guard blocks also belong under `agentdojo.art.defence_benign_intervention` when its scope is widened.

Proposed `artefacts.toml` entries (text only; route to the AgentDojo family owner):

```toml
# PC-01 / PC-02 (new)
# [[artefact]] id = "agentdojo.art.seagent_guard_batch_abort"; scope.sources = ["seagent-agentdojo"]
#   the guard renames one call per batch to "<tool>BLOCKED_BY_SEAGENT", answers it with an empty tool message,
#   drops the batch's other calls and adds a user-role warning
#   expected = [{snapshot="seagent-agentdojo:head", count=960, unit="blocked calls (mapped as executions)"},
#               {count=166, unit="skipped calls"}, {count=107, unit="logs"}, {count=94, unit="logs with missing_tool_result"}]
# PC-03 (CC-10): agentdojo.art.slack_it5_attempt_scored expected += {snapshot="seagent-agentdojo:head", count=8}
# PC-04 / PC-05 (CC-07): agentdojo.art.validity_defects scope += seagent-agentdojo; counts 9 (#181), 30 (#161)
# PC-08 (CC-09): generic entries scope += seagent-agentdojo: benign_security_constant 657 (485 perf + 172 prepass),
#   injection_task_as_user_task_prepass 172, unexecuted trailing calls 317 logs, guard warnings 960 / 863 logs,
#   pvagent call-less assistant messages 740 / 541 logs
```

Items for AGENTS.md section 12:

- PC-01: the 94 `failed` executions of seagent-agentdojo are SEAgent guard batch aborts (166 never-executed calls in 107 logs), not data loss. A family quirk is routed; never filter them out.
- PC-03: AgentSpec-LLM slack ASR 43/105 includes 8 IT5 successes scored from unexecuted calls (#168/#189); without them it is 35/105.
- PC-05: banking UT5 passes 50/50; 30 have no executed payment (#161), mostly in the defended arms.
- PC-07: the baseline arm is not the paper's Vanilla run (47.18/52.09 vs 46.61/54.26).

## 8. Recommendations and readiness

1. Route PC-01 and PC-02 to the AgentDojo family owner together with D-153 (defence-authored messages). Both change bytes for 107 and 863 logs respectively, so they go on the code-fix list before the regeneration round and need approval (memory rule: list fixes before re-import). If the round runs without them, the import exits 1 with `failed` 94. Disclose that.
2. Route the CC-07 counts (9, 30), the CC-10 count (8) and the CC-09 scope widening.
3. Datasheet and manuscript: report the logged values as primary. Note the seagent workspace erratum (PC-06) and the baseline-is-not-Vanilla point (PC-07); put re-scores in separate, labelled columns.
4. No exclusion of any data: not the baseline arm, not the 0%-ASR arms, not the `failed` executions.

**Readiness: `ready-with-caveats`** (confirmed by the verifier: no S0/S1, every caveat routed, outcome fidelity re-checked).

- The outcome fidelity is exact: 40/40 paper cells, all macros, benign utility and latency reproduce from the raw data, and raw = mapped on the sample. All 200 units pass validate, recompute and chain verify; determinism holds except for one code-digest field; identity resolves 100%; redaction finds 0 hits.
- Caveats, owned and routed: PC-01/PC-02 (mapping gap for the SEAgent guard; preferably fixed before the round), PC-03 (CC-10), PC-07 (disclosure).
- Not counted: PC-08 (CC-09 reference) and PC-09 to PC-11 (R5).

## 9. Reproduction

Batches: `tools/precheck/plans/wave5.toml` (l1, l1_10, sample, import_j2) and `tools/precheck/plans/followup2.toml` (import_j1, check), run through `tools/suite_queue.py --class import --cpu 2` (W = `~/.agentprov/migration-work/precheck/seagent-agentdojo`, D = `docs/reports/precheck/data/seagent-agentdojo`):

```bash
uv run python tools/precheck/l1_scan.py --source seagent-agentdojo --part head --corpus-id seagent-agentdojo --jobs 2 --emit-fp --input ~/.agentprov/staging/10f/seagent-zenodo-23218779/seagent-acsac2026-ae-v2.zip
uv run python tools/precheck/l2_sample.py select --units W/l1-units-head.jsonl --source seagent-agentdojo --part head --corpus-id seagent-agentdojo --out D/l2-sample-head.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j2 --source seagent-agentdojo --part head --jobs 2   # rc 1 (failed 7)
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j1 --source seagent-agentdojo --part head --jobs 1   # rc 1 (failed 7)
uv run python tools/precheck/l2_check.py --corpus W/l2-head-j2.partial --out D/l2-head.json --sample D/l2-sample-head.json --l1-units W/l1-units-head.jsonl --compare-with W/l2-head-j1.partial --jobs 2
```

Examiner scripts. They are read-only. They read the 5,342 raw objects of the scratch corpus (sha256-checked, strict parse) and parse them through `agentprov.ingest`. S = `D/exam-scripts`, E = `W/exam`:

```bash
uv run python -I S/failed_probe.py                         # PC-01: skeletons of the 7 failed executions
uv run python -I S/pop.py E/pop.json                        # H5-H16, PC-01 anatomy, CC-07 #181, null-final
uv run python -I S/blocked.py E/blocked.json                # PC-01/PC-02 blocked-batch anatomy
uv run python -I S/skip_pos.py E/skip_pos.json              # PC-01 skipped-call positions (107 logs, 166 calls)
uv run python -I S/mtr_sample.py D/l2-sample-head.json      # 94 population / 7 sampled
uv run python -I S/os1.py E/pop.json D/os1-population.json  # section 6, L1
uv run python -I S/os2.py D                                 # section 6, L2 raw vs mapped
uv run python -I S/cc07_161.py D/cc07.json                  # PC-04, PC-05
uv run python -I S/dclass.py E/dclass.json                  # class-D rules, blocked executions in AER
uv run python -I S/dup.py E/dup.json                        # PC-11
uv run python -I S/probe.py                                 # PC-03, PC-05, PC-09 skeletons
grep -c seagent src/agentprov/adapters/agentdojo/artefacts.toml   # PC-08: 0
```

Follow-up (heavy; not run): the full import of the part (5,342) is the round's job; the part-A trial already recorded `failed` 94 there.
