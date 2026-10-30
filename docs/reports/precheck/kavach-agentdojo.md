# Pre-check dossier: `kavach-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `kavach-agentdojo` (MIT, LICENSE blob `01b2613e` at all three pins; no data licence or use clause) |
| Parts | `main` @ `53df9545`, `nav-fixer2` @ `f2dd7efa`, `rearch-forcedformat-fix` @ `6b31a554` (import order; one corpus, 2,625 distinct executions) |
| Family / profile | `agentdojo` / `kavach-agentdojo@1` (dialect `agentdojo.tracelogger`, variants `v1.k14`, `v1.k14.incomplete`; SEM `agentdojo.suites@2`; identity table `kavach_run_dirs`) |
| Code commit | `d97d3a57` (L1 and L2, batch `wave7`, all 18 steps rc 0; tracked changes true; contains the CC-08 fixes of `5efa3575`) |
| Kind | wave 7, first examination (not in FA or E2); no stored corpus |
| Date | 2026-10-14 (prereg), 2026-10-15/16 (L1, L2), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), batch (L1/L2), examiner (this dossier), adversarial verifier (2026-10-21) |
| Data | [`data/kavach-agentdojo/`](data/kavach-agentdojo/): `research.json`, `l1-<part>.json`, `l1-10-<part>.json`, `l2-sample-<part>.json`, `l2-<part>.json`, `code-<part>.json`, `exam.json`, `findings.json`, `raw-census.json`, `os1-population.json`, `os2-sample.json`, `shape-counts.json`, `exam-scripts/` |

Code identity (from `code-<part>.json`; the same for all three parts): commit `d97d3a57` (tracked_changes true); engine code aer `856b7a09e0cf`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `agentdojo.tracelogger@0.1.0` `03d8bc6d30df`; profile sha256 `c7002b1d1821`, rules agentdojo 2 / aer 1; lockfile `b0455f1058c8`, limits `5d6dbb210259`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Repository | https://github.com/Ishani018/Kavach (9 branches; the 3 pins are branch heads; 6 other branches hold `main`'s 223 logs) | the data |
| Run summaries | `agentdojo_summary*.json` in four run directories | outcome reference. No paper exists: the in-repo drafts leave the Kavach AgentDojo ASR as `[TBD]` |
| Invalid note | `INVALID_README.md` (merge `9e00ac41`) | the slack directory is declared invalid by the source. It is included and disclosed (D-253) |
| Data record | none (no Zenodo/HF/Figshare); integrity rests on git blob ids | n/a |
| Harness | AgentDojo 0.1.35 per the logs; runner `benchmarks/run_agentdojo_kavach.py`; local Ollama models | producer |
| Upstream issues | ethz-spylab/agentdojo #150, #154, #202, #219, #220 (LocalLLM); #181, #161, #168 (checkers) | partly inherited (Kavach overrides `LocalLLM.query`) |

Data-versus-documentation notes, checked against the data:
- The six reference arms reproduce exactly (section 6).
- The summary's Kavach block count (40 of 108 calls) does not match the logs: 45 denials, 121 calls (PC-03).
- The INVALID_README 93/90 counts are trajectories that died at message 5: token echo 88/85 plus 5/5 all-empty finals (PC-04, refuted by the verifier).
- `agentdojo_summary1.json` in `not_forced` is the forced summary renamed. That directory is one log set made of 41 forced-run files plus 43 new runs (PC-01).

## 3. Expectations

The pre-registration is [`prereg/kavach-agentdojo.md`](prereg/kavach-agentdojo.md), committed at `eb7151ee` before any data check.
- Amendments 2, 3 and 5 apply. Amendment 5 sets the stratum key to `model_dir × suite × attack_dir`, giving 5 / 17 / 17 strata.
- Deviation: the prereg planned one scratch corpus with the three snapshots in order. The batch imported each part separately. Cross-snapshot collapse is therefore not exercised at L2 (follow-up 1).
- Findings are classed by R1-R6 and CC-01..CC-11 of [`cross-cutting.md`](cross-cutting.md).

| H | Result | Note |
|---|---|---|
| H1 | supported | selected 223 / 1,518 / 1,518; byte-distinct 223 / 1,477 / 1,518; union 2,625; new in import order 223 / 1,254 / 1,148; every §3 cell count matches |
| H2 | supported | strict parse ok 223 / 1,518 / 1,518 (+ aux 1 / 2 / 3) |
| H3 | supported | 0 U+FFFD, mojibake, lone surrogates |
| H4 | supported, overlap present | the 41 nav copies all pair `workspace_forced/logs/local` with `results_v2/logs/local`; `not_forced` = nav `results_v2/logs/local` 84/84; 41 logs carry both labels (PC-01, S2) |
| H5 | refuted | 45 denials, all in pair logs (45 logs), 0 in pre-passes, 0 in workspace; summary says 40 (PC-03) |
| H6 | supported as worded | 0 of 574 workspace Kavach logs per branch (1,148 across both) has any tool call, so the arm is tool-free, not unscreened (PC-02) |
| H7 | supported on the README's definition (verifier) | token echo 88/105 local, 85/105 kavach; plus 5/5 all-empty finals at message 5 = 93/90 as stated; workspace ≤ 0.3 % (PC-04 refuted) |
| H8 | supported | all 6 reference arms exact (5/105, 0/105; 27/560, 0; 11/560, 10/560; Kavach 0/0) |
| H9 | supported | census T/F/absent reproduce per part after removing nav's 41 copies (14 prepass + 27 utility-true pairs) |
| H10 | supported at L1 | gemma4:26b 2,516, unresolved 109 (43 from `results_v2/logs`), kavach 1,258; `pipeline_name` is `local` / `local-kavach` only. The three-snapshot L2 was not run |
| H11 | partly supported | in the nav L2, the collapsed copy (n_origins 2) keeps the first origin (forced, gemma4:26b). Cross-snapshot behaviour not tested |
| H12 | supported | every directory is inside its bound (e.g. slack max 07-06 13:17 ≤ 13:22; not_forced2 max 07-16 15:32 ≤ 15:34); 0 non-monotone |
| H13 | supported | 0 secret-like strings, 0 account paths in the logs; L1-10 0 hits |
| H14 | refuted | 5 incomplete logs, one per partial directory, `error` null 2,625/2,625; but banking user_task_0 is complete and the incomplete one is user_task_2 (PC-06) |
| H15 | supported | `2e867516` in 220 / 1,474 / 1,515 distinct runner logs; `a021a92b` in the 3 banking logs, which alone carry v1.2.2 |
| H16 | supported | 21 user tasks × 5 = 105 (the draft says 20; PC-06) |
| H17 | supported | every L2 stage ok, 0 failing, 0 degenerate, 0 `adapter_defect`, recompute 0, j1 = j2, raw = mapped 392/392 judgements |
| H18 | supported | profile text (PC-09) |
| H19 | refuted on share | same-cell local/local-kavach pairs are 43 of 59 groups (72.9 %, below 80 %; report only). Outcomes agree in 319/319 groups, so no source-defect |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input is the staged bare clone at each pin (`--git`, blob SHA-1 checked). Tool `l1_scan` at `d97d3a57`. Values are given as main / nav / rearch.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | walked 867 / 1,913 / 1,892. Selected 223 / 1,518 / 1,518. Context 19 / 14 / 15. Not selected 617 / 373 / 351. Absent blobs 8 each. 0 excluded / rejected. Units = selected; aux JSON 1 / 2 / 3 | as expected |
| L1-02 parse | strict ok 100 % (logs and aux); 0 of every class | as expected |
| L1-03 encodings | `json_in_string` 9 / 103 / 103 strings; escaped newline 0 / 119 / 88; escaped quote 0 / 4 / 6; escaped unicode 0 / 13 / 13. All are in tool content, call function or error strings. 0 controls, bidi, zero-width, U+FFFD, mojibake | as expected (content) |
| L1-04 duplicates | Byte groups within part: 0 / 41 / 0. Cross-part pairs: main∩nav 223, main∩rearch 223, nav∩rearch 370. Cross-corpus 0 (`_cross/l1-xdup.json`). Trajectory groups (CC-01): 59 / 141 / 119 (166 / 1,358 / 1,264 files). Census `fp_run`: 57 / 590 / 561 (whole-message definition) | as expected; CC-01 |
| L1-05 arms | 5 / 17 / 17 strata; every §3 cell present. Missing by design: travel, benign pass, the `_fix2` slack run, Kavach arms of dell/llama/forced2/logs/not_forced. Partial runs: dell, forced_llama3.1, llama3.1, forced2 | as expected |
| L1-06 secrets/paths | 0 of 223 / 1,518 / 1,518; aux 0; L1-10 18 / 12 / 12 context files, 0 hits, 0 operator | as expected (H13) |
| L1-07 timestamps | `/evaluation_timestamp` 100 % naive, 0 parse failures, 2026-07-06..07-16. Tool-arg dates are 2024-05-30 (benchmark content) | as expected (H12) |
| L1-08 degenerate | incomplete 1 / 5 / 5; trailing_calls 0 / 7 / 6 (= profile); null_final 11 / 41 / 89 (all-empty text blocks, no tool call; profile says 0: PC-05). Not flagged by L1 but found by the exam: workspace Kavach arms have 0 tool calls (PC-02) | PC-05, PC-02 |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | `l2-sample-<part>.json`: 31 (5 strata) / 83 (17) / 83 (17), seed 20261011 |
| Import | per-part scratch corpora `l2-<part>-j2.partial` and `-j1.partial`. Executions 31 / 82 / 83; nav has 83 labels and 1 `dedup.collapsed` (an in-pin copy). ok 28 / 39 / 50, ok_with_issues 3 / 43 / 33, 0 degenerate, 0 `adapter_defect`, 0 failed |
| Validation | aer, sem, prov, linkage: 31 / 82 / 83 pass, reproduced, linkage 100 %. SHACL not implemented |
| Recompute | `--dry-run`: all identical, 0 unexplained |
| Verify chain | 0 failures; only `checksums.absent` (working tree) |
| Determinism | j2 vs j1: 150 / 349 / 354 files, 0 differ, index identical |
| A2 register codes | `accounting_unverifiable` 30 / 81 / 82; `earlier_attempts_unobservable` all; `identity_unresolved` 3 / 42 / 33 (= the sampled unresolved directories); `incomplete_run` 1 / 3 / 2; `unexecuted_tool_call` 0 / 6 / 4 |
| A3 PROV | 0 dangling / missing / invented relations over 10,269 / 33,521 / 32,849 statements; unexecuted calls represented 6 / 4 |
| Evidence classes | AER: D rules cited only by their `_unverified` twins (code identity unpinned). PROV statement-level split (CC-08 decoder): twin 2,442 / 11,839 / 11,152, native 0, mixed 280 / 1,194 / 1,152; core D 144 / 402 / 398 (engine rules) |
| Judgements (OS-2) | raw vs mapped: 0 of 62 / 164 / 166 differ. Origins: utility checker; security checker on attacked runs, `harness_default` on benign and pre-pass runs (12 / 44 / 46) |
| Decisions | Kavach denials mapped (D-113): 5 / 2 / 3 decision records in the sampled slack Kavach logs |
| Identity | model `gemma4:26b` for slack, forced, not_forced, not_forced2; unresolved for banking, dell, llama, forced_llama, forced2, results_v2/logs; defence `kavach` for `local-kavach` only; 0 direct mismatches. Join artefact in nav (PC-10) |
| Redaction | 101 / 254 / 257 AER/SEM/PROV files, 0 hits |
| Withholding | none (D-257: no table) |

## 6. Outcome comparison

Level 1 gives population rates: attacked pairs, raw booleans, labels deduplicated across parts. The reference is the harness summary (there is no paper). Gap rule: more than 15 pp, or more than 5 pp outside Wilson 95 %. L2 arms are all n < 20, so they get Wilson intervals only and no verdict. Full rows are in [`os1-population.json`](data/kavach-agentdojo/os1-population.json).

| Arm (dir · pipeline, model) | n | Utility % (Wilson) | Ref | ASR % (Wilson) | Ref | Gap | Verdict |
|---|---:|---|---:|---|---:|---:|---|
| slack · local (gemma4:26b) | 105 | 4.76 (5) [2.05, 10.67] | 4.76 | 0.00 [0.00, 3.53] | 0.0 | 0 / 0 | match (dir source-invalid) |
| slack · local-kavach | 105 | 0.00 [0.00, 3.53] | 0.0 | 0.00 [0.00, 3.53] | 0.0 | 0 / 0 | match |
| workspace_forced · local | 560 | 4.82 (27) [3.33, 6.92] | 4.82 | 0.00 [0.00, 0.68] | 0.0 | 0 / 0 | match; 532/560 tool-free (PC-02) |
| workspace_forced · local-kavach | 560 | 0.00 [0.00, 0.68] | 0.0 | 0.00 [0.00, 0.68] | 0.0 | 0 / 0 | match; 0 tool calls (PC-02) |
| workspace_not_forced2 · local | 560 | 1.96 (11) [1.10, 3.48] | 1.96 | 1.79 (10) [0.97, 3.26] | 1.79 | 0 / 0 | match; 482/560 tool-free |
| workspace_not_forced2 · local-kavach | 560 | 0.00 [0.00, 0.68] | 0.0 | 0.00 [0.00, 0.68] | 0.0 | 0 / 0 | match; 0 tool calls (PC-02) |
| not_forced = results_v2/logs · local | 70 | 38.57 (27) [28.05, 50.28] | none | 8.57 (6) [3.99, 17.47] | none | – | 27/27 successes are forced copies (PC-01) |
| dell · local | 12 (+1 null) | 0.00 [0.00, 24.25] | none | 0.00 [0.00, 24.25] | none | – | Wilson only |
| forced_llama3.1 · local | 6 (+1 null) | 0.00 [0.00, 39.03] | none | 0.00 [0.00, 39.03] | none | – | Wilson only |

CC-07 / CC-10:
- #181: 0 banking attacks, so 0 of 0 affected.
- #161: banking has user tasks 0-2 only, so 0 of 0 affected.
- slack injection_task_5: 0 successes of 42.
- Re-scored rates equal the logged rates (PC-07).

No arm is excluded for zero attack successes.

## 7. Findings

| Id | Title (short) | Class | Sev | CC | Verdict |
|---|---|---|---|---|---|
| PC-01 | 41 logs labelled both forced and not_forced; not_forced utility 27/70 is all forced copies | source-defect (R1; verifier corrected from documentation-mismatch) | S2 | – | confirmed |
| PC-02 | workspace Kavach arms: 0 tool calls in 574/574 logs per branch (1,148 total); payload never reaches the agent | expected-known (`payload_not_reaching_agent`), raised | S2 | CC-09 | confirmed |
| PC-03 | 45 Kavach denials (pairs only) vs summary 40 of 108 | documentation-mismatch (R3) | S3 | – | confirmed |
| PC-05 | 89 empty-text-block finals vs profile null_final 0; no extra passes inferred | documentation-mismatch (R4) | S3 | CC-08 | confirmed |
| PC-06 | banking UT0 complete (incomplete is UT2); slack 21 vs draft 20 user tasks | documentation-mismatch (R3) | S3 | – | confirmed |
| PC-07 | #181 / #161 / slack IT5 affect 0 executions | expected-known (R2) | S3 | CC-07, CC-10 | confirmed |
| PC-08 | no `artefacts.toml` entry scopes kavach; generic counts | documentation-mismatch | S3 | CC-09 | confirmed |
| PC-09 | profile "agentdojo per requirements.txt" (requirements.txt names agentdojo 0 times at all pins) | documentation-mismatch (R4) | S3 | – | confirmed |
| PC-10 | `l2_check` join by sha256 mis-attributes the collapsed nav execution | analysis-artefact (R5) | S3 | – | confirmed |

Refuted by the verifier: PC-04 (`<|tool_response>` 88/85 vs INVALID_README 93/90). The README counts trajectories that died at message 5, and token echo 88/85 plus 5/5 all-empty finals at message 5 gives exactly 93/90 (moved to `refuted` in `findings.json`).

Verifier (2026-10-21) re-counted every finding from the pinned git trees directly (not from the L1 units; strict ingest, blob sha1 checked; scratch `exam/verify.json`). All other counts reproduce exactly. PC-01 was reclassed to `source-defect` S2 because the copied files and the copied summary are the source's own data assembly, no entry covers them, and they bias the not_forced utility. PC-02 was reworded to 574 per branch.

There are no security findings and no mapping defect. Evidence and reproduction are in [`findings.json`](data/kavach-agentdojo/findings.json) (CC-06 format).

Proposed `artefacts.toml` entries (text only; route to the AgentDojo family owner):

```toml
# PC-02 (CC-09): agentdojo.art.payload_not_reaching_agent  scope += kavach-agentdojo
expected += [
  { snapshot = "kavach-agentdojo:nav-fixer2", count = 1092, unit = "executions", basis = "pre-check PC-kavach-agentdojo-02: attacked logs with 0 tool executions (kavach 560 + local 532); lower bound", status = "proposed" },
  { snapshot = "kavach-agentdojo:rearch-forcedformat-fix", count = 1042, unit = "executions", basis = "same (kavach 560 + local 482)", status = "proposed" },
]
# PC-01: identity/condition note (agentdojo.art.identity_folding or a kavach entry):
#   kavach-agentdojo:rearch-forcedformat-fix, 41 executions, not_forced files byte-equal to nav workspace_forced (14 prepass + 27 utility-true pairs)
# PC-07 (CC-07): agentdojo.art.validity_defects scope += kavach-agentdojo, count 0 (no banking attack; no banking UT5)
# PC-08 (CC-09): generic rows (files main/nav/rearch): benign_security_constant 13/98/98; injection_task_as_user 10/95/95;
#   incomplete_run 1/5/5; max_iters_pending 0/7/6; naive_timestamp 223/1518/1518; silent_rerun pending PC-05
```

Items for AGENTS.md §12:
- PC-02: Kavach was never exercised in workspace. Its 574 logs per branch (1,148 total) contain no tool call, so its 0 % ASR there is not a defence result. Only the slack arm (45 denials, source-declared invalid) shows Kavach acting.
- PC-01: the `not_forced` / `results_v2/logs` 70-pair set is 41 forced-run files plus 43 new runs. Its 38.6 % utility comes entirely from forced-run copies.

## 8. Recommendations and readiness

1. Disclose PC-01 and PC-02 in the datasheet and in any table that uses Kavach numbers. Report the logged values. Keep every log, with no exclusion (user rule).
2. Family owner:
   - the PC-01 condition/identity note;
   - the PC-02, PC-07 and PC-08 scope rows (CC-09, CC-07);
   - PC-05, deciding whether the silent-rerun trigger covers v1.k14 all-empty text blocks (a regen item if the rule changes);
   - the PC-09 profile text.
3. Tool owner: PC-10 (join on origins, not on sha256 alone).
4. Run the three-snapshot L2 (follow-up 1) to test H10/H11 cross-snapshot collapse.

**Readiness: `ready-with-caveats`.**
- Every part imports deterministically and validates.
- Mapped judgements equal the raw values for 392 of 392.
- The six reference arms reproduce exactly.
- Redaction has 0 hits.
- Caveats: PC-01 and PC-02 are S2 disclosures, not blockers. PC-10 is R5 and is not counted.
- Verifier (2026-10-21): readiness confirmed. 9 findings confirmed and 1 refuted (PC-04). PC-01 is reclassed to source-defect S2, which is still a disclosure and not a blocker. There is no outcome gap.

## 9. Reproduction

Batch: `tools/precheck/plans/wave7.toml` via `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-wave7 -- uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave7.toml`. Logs are in `~/.agentprov/migration-work/precheck/_batch/wave7/kavach-agentdojo.<part>.<step>.log` (status rc 0 for all 18 steps).

Examiner scripts (read-only; S = `docs/reports/precheck/data/kavach-agentdojo/exam-scripts`, W = `~/.agentprov/migration-work/precheck/kavach-agentdojo`):

```bash
uv run python -I S/pop.py W/exam/pop.json         # union, overlaps, H4, H19, per-cell raw counts, timestamps, prompt digests, null-final detail
uv run python -I S/extra.py W/exam/extra.json     # H7 token counts, message shapes, incomplete labels
uv run python -I S/textcall.py W/exam/textcall.json  # PC-02 three-message final text shape
python3 -I S/os1.py W/exam/os1.json               # section 6
python3 -I S/os2.py W/exam/os2.json               # OS-2, multi-origin executions
python3 -I S/write_findings.py docs/reports/precheck/data/kavach-agentdojo/findings.json
grep -c -i kavach src/agentprov/adapters/agentdojo/artefacts.toml   # PC-08: 0
```

Follow-ups (not run):

| # | What | Command |
|---|---|---|
| 1 | Three-snapshot L2 in one scratch corpus (union of the three samples, import order main → nav → rearch), then `l2_check`; expect the 84 rearch `not_forced` copies to collapse (41 onto forced, 43 onto `results_v2/logs`, unresolved) | `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-kavach-3snap -- uv run python tools/precheck/l2_import.py --source kavach-agentdojo --part <each, in order> --sample data/kavach-agentdojo/l2-sample-<part>.json --corpus W/l2-all-j2 --jobs 2` |
| 2 | Verifier pass on PC-01..PC-10: done 2026-10-21 (9 confirmed, PC-04 refuted) | per README §2 step 4 |
| 3 | Routing of PC-01/02/05/07/08/09 to the AgentDojo family owner; PC-10 to the tool owner | no command |
