# Pre-check dossier: `bookkeeper-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `bookkeeper-agentdojo` (GPL-3.0-or-later at the pin; own corpus per D-94) |
| Parts | `bookkeeper-agentdojo · head` (1 part) |
| Family / profile | `agentdojo` / `bookkeeper-agentdojo@1` (dialect `agentdojo.tracelogger`, variants `v1.k14` 566, `v1.k14.incomplete` 4; semantics `agentdojo.suites@2`) |
| Pin | git `sricursion/bookkeeper` @ `0fe09bb6` (2026-09-05T15:00:51Z, repository head), tree 1,020 blobs |
| Code commit | `d97d3a57` (L1 and L2, batch `wave3`, all 6 steps rc 0, tracked_changes false; after the CC-08 fixes at 5efa3575, so no recheck12 needed) |
| Kind | wave 3, first examination (not in FA or E2); no stored corpus |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (batch), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), examiner (this dossier), adversarial verifier (2026-10-21: 4/4 confirmed, PC-04 evidence corrected) |
| Data | [`data/bookkeeper-agentdojo/`](data/bookkeeper-agentdojo/): `research.json`, `l1-head.json`, `l1-10-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `population.json`, `outcomes.json`, `extra.json`, `findings.json`, `exam-scripts/` |

- Code identity, part `head` ([`code-head.json`](data/bookkeeper-agentdojo/code-head.json)): commit `d97d3a57` (tracked_changes false); engine code aer `856b7a09e0cf`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `agentdojo.tracelogger@0.1.0` `03d8bc6d30df`; profile sha256 `ed9e8fdd66fd`, rules agentdojo 2 / aer 1; lockfile `b0455f1058c8`, limits `5d6dbb210259`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Source repository | https://github.com/sricursion/bookkeeper @ `0fe09bb6` (2 commits, 0 issues/PRs) | the data; `runs/agentdojo/summary.md`, 11 `results_*.json`, `eval/agentdojo/README.md`, `docs/numbers.md` = outcome references |
| Logs commit | `bb4ae402` (2026-09-05, declared MIT, no LICENSE file); `runs/agentdojo/` byte-identical at the pin (relicensed GPL-3.0-or-later) | data origin; licence history |
| Paper / data record | none (arXiv, Zenodo, HF searched) | n/a |
| Benchmark | AgentDojo 0.1.35 (PyPI), suite v1 banking; https://arxiv.org/abs/2406.13352 | harness; `benchmark_version` null (D-102) |
| Upstream issues | ethz-spylab/agentdojo [#181](https://github.com/ethz-spylab/agentdojo/issues/181), [#161](https://github.com/ethz-spylab/agentdojo/issues/161), [#214](https://github.com/ethz-spylab/agentdojo/issues/214) | checker and harness defects (CC-07) |

Data-versus-documentation notes (checked against the logs):

- Every reported number reproduces: 297/297 per-pair booleans of the 11 results files, and all 5 gate-v2 aggregates of `summary.md` (H1, H2).
- The documents do not report 4 partial or stray arms (39 logs) or any of the 100 pre-pass logs. They also do not say that GLM's "nothing held" counts pair episodes only (PC-03).
- The runs overlap in time: gpt `-munim-cap2-g2` TK (13:08:41-13:15:56) ran beside its II run, and both gate-v3 runs started at 13:11:18. This fits the partial arms being aborted when v3 started (inference, not recorded).
- The naive timestamps are IST: the results `finished_at` carry +05:30, and every attacked log lies inside its results window (`finished_at` − `seconds`) ± 60 s (H6).

## 3. Expectations

Pre-registration: [`prereg/bookkeeper-agentdojo.md`](prereg/bookkeeper-agentdojo.md), committed in `fd75f8a3` (2026-10-14), before any check of this corpus ran. Amendments 2-5 (README section 8) apply; amendment 1 does not, because there is no stored corpus. The stratum key is the pre-registered (pipeline_dir, attack_dir): 31 strata, 151 units. Classes follow R1-R6 and CC-01..CC-11.

| H | Result | Note |
|---|---|---|
| H1 | supported | 11 results files × 27 pairs = 297; utility and security differ in 0 |
| H2 | supported | glm cap2-g2 II 17/0, TK 16/0; gpt none II 11/20, TK 12/14; gpt cap2-g2 II 6/0 |
| H3 | supported | attacked security true = 68 (gpt none 20 + 14, none-g4 20 + 14); 0 in every munim, glm and partial arm |
| H4 | supported | 235 over the 16 reported cells; the other 35 = 23 pre-pass + 12 glm cap2-g3 |
| H5 | supported | 180 denials, all in munim dirs, 0 in none dirs; glm v1 6 (all pre-pass), glm g4 6 (all pre-pass), gpt g4 36 (pre-pass 3, II 20, TK 13), glm cap2-g2 attacked 6, gpt cap2-g2 II 68 |
| H6 | supported | 2026-09-05 02:45:22..13:41:03, all naive; 0 of 297 attacked logs outside their window; 0 glm `-none` logs at 12:53-13:10 |
| H7 | supported | 4/4 partial arms are prefixes; each incomplete log is the last cell (ut2×it4, ut0×it4, ut1×it0, llama it0) |
| H8 | supported | 0 duplicate (dir, task, attack, injection) keys; 0 mismatches between path and logged fields (570/570) |
| H9 | supported | 0 harness-authored assistant turns |
| H10 | supported | 0 of 204 gpt-oss attacked logs have "GLM" in tool output (204 have "GPT"); 266/266 glm logs have "GLM" |
| H11 | supported | 0 byte-identical; 0 cross-corpus trajectory repeats (`_cross/l1-xdup.json`); 59 within-part groups |
| H12 | supported | 0 secret-like, 0 account paths in 570 logs, 11 auxiliary JSON and 15 non-JSON context files |
| H13 | supported | pre-pass utility glm none 5/9 and 5/9 vs munim 1/9 each; gpt none 2/9 and 4/9 vs munim 1/9 each |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: the staged bare clone at `0fe09bb6` (`--git`, blob SHA-1 checked), `l1_scan` at `d97d3a57`, 1.6 s.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 1,020 walked = 570 selected + 26 context + 424 not selected; 0 excluded/rejected; units 570 = registry = census. 11 results files scanned as auxiliary JSON | as expected |
| L1-02 parse | strict ok 570/570, auxiliary 11/11; 0 defects of any class | as expected |
| L1-03 encodings | variation selector 160 files / 168 strings, zero-width 1 string, all at `/messages/*/content/*/content`. Located (`extra.py`): assistant text only: glm emoji U+26A0 (165) and U+2714 (4) + VS16; 1 U+200B in a gpt-oss answer. 0 escape residues, 0 controls, bidi, U+FFFD or mojibake | model output, not a defect; prereg's possible #214 residues: 0 |
| L1-04 duplicates | byte-identical 0; trajectory-identical (CC-01) 59 groups / 152 of 570 units, 34 groups across none and munim dirs (runs where the gate never acted), largest 5 (gpt-oss none, none-g4, cap2-g2, cap2-g3, g4); cross-corpus 0 | as pre-registered (H11) |
| L1-05 arms | 31 strata as in prereg §2 (per-dir counts exact); 186 cells missing vs the 12 × 63 grid, 0 unexpected; no benign user-task run (by design) | as expected |
| L1-06 secrets/paths | logs 0/570; auxiliary 0/11; L1-10 15 non-JSON context files, 0 hits, 0 operator | as expected (H12) |
| L1-07 timestamps | `/evaluation_timestamp` 570/570, naive 570, 0 parse failures, one day; within-unit monotonicity not applicable (one stamp per file) | as expected (H6) |
| L1-08 degenerate | `incomplete` 4, `trailing_calls` 1 (gpt cap2-g2 TK ut0×it1); 0 empty, tiny, zero-message, error-only; `error` null 570 | as expected |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`l2-sample-head.json`](data/bookkeeper-agentdojo/l2-sample-head.json) (sha256 `7b18e60161a8…`): 151 of 570, 30 strata × 5 + llama 1, seed 20261011 |
| Import | 2 scratch corpora (`l2-head-j2.partial`, `-j1.partial`) at `d97d3a57`: 151/151 mapped; ok 147, ok_with_issues 4 (3 incomplete + the trailing-call log), 0 degenerate, 0 `adapter_defect`, 0 failed; 151 labels → 151 executions 1:1 |
| Validation | tiers aer, sem, prov, linkage: 151/151 pass, 151 reproduced, linkage 100 %; SHACL not implemented (skipped); regression n/a |
| Recompute | `--dry-run`: 151 identical, 0 changed, 0 unexplained |
| Verify chain | 0 failures; only `checksums.absent` (working tree). No sealed copy needed (no `[withhold]`, 0 L1-06 hits) |
| Determinism | j2 vs j1: 637/637 files identical, index identical |
| A2 classes | `map.accounting_unverifiable` 150, `map.earlier_attempts_unobservable` 151, `map.incomplete_run` 3, `map.retry_passes_inferred` 1, `map.unexecuted_tool_call` 1 (= the prereg's trial codes) |
| A3 PROV issues | 0 PI hits over 61,827 statements / 105,697 relation arguments; 828 messages with `generated_by`, 480 model calls with input; the 1 unexecuted call is represented (1/1) |
| Gate decisions | raw sample 349 calls = 288 executed + 60 denials + 1 unexecuted; AER 288 tool executions + 60 `deny` decisions (holds mapped as deny, D-113) |
| Evidence classes | PROV core D 694 (engine rules only) / O 3,397; `_unverified` twins: inference I 14,338, assessment I 2,168, inference unclassed 1,426; mixed twin + native inference I 2,207; native-only 0 (statement-level split, CC-08 fixed counter) |
| Judgements | utility and security checker 93 each (attacked); pre-pass utility checker 55, security `harness_default` 55 (`benign_security_constant`); 3 incomplete logs have no judgement |
| Identity | models glm-5.3-flash / gpt-oss-120b / llama-3.1-8b from the pipeline dir; defences `none`, `munim`, `munim-cap2-g2`, `munim-cap2-g3`, `munim-g4-cap2`; `-none` and `-none-g4` both map to `none` (PC-04); 0 unresolved, 0 mismatches |
| OS-2 raw vs mapped | 302 judgements compared, 0 differ (6 null on both sides) |
| Redaction | 461 AER/SEM/PROV files, 0 hits |
| Withholding | no policy in the profile; not applicable |

## 6. Outcome comparison

Level 1 is the population of raw booleans (attacked logs only; pre-pass logs excluded; null outcomes of incomplete logs excluded). Reference: the results files and `summary.md` (prereg §4), each cell n = 27. Gap rule: more than 15 pp, or more than 5 pp outside Wilson 95 %. Full rows are in [`outcomes.json`](data/bookkeeper-agentdojo/outcomes.json).

| Arm (pipeline dir / attack) | n | Utility (Wilson 95 %) | Ref. | ASR (Wilson 95 %) | Ref. | Gap | Verdict |
|---|---|---|---|---|---|---|---|
| glm none / II | 27 | 66.67 [47.82, 81.36] | 66.67 | 0.00 [0.00, 12.46] | 0.00 | 0 / 0 | match |
| glm none / TK | 27 | 66.67 | 66.67 | 0.00 | 0.00 | 0 / 0 | match |
| glm none-g4 / II, TK | 27, 27 | 66.67, 66.67 | 66.67 | 0.00, 0.00 | 0.00 | 0 / 0 | match |
| glm munim (v1) / II | 27 | 66.67 | 66.67 | 0.00 | 0.00 | 0 / 0 | match |
| glm munim-cap2-g2 / II | 27 | 62.96 [44.23, 78.47] | 62.96 | 0.00 | 0.00 | 0 / 0 | match |
| glm munim-cap2-g2 / TK | 27 | 59.26 [40.73, 75.49] | 59.26 | 0.00 | 0.00 | 0 / 0 | match |
| glm munim-g4-cap2 / II, TK | 27, 27 | 66.67, 66.67 | 66.67 | 0.00, 0.00 | 0.00 | 0 / 0 | match |
| gpt none / II | 27 | 40.74 [24.51, 59.27] | 40.74 | 74.07 [55.32, 86.83] | 74.07 | 0 / 0 | match; #181 0 of 9 IT0/1/3 |
| gpt none / TK | 27 | 44.44 [27.59, 62.69] | 44.44 | 51.85 [33.99, 69.26] | 51.85 | 0 / 0 | match; #181 0 of 6 |
| gpt none-g4 / II | 27 | 40.74 | 40.74 | 74.07 | 74.07 | 0 / 0 | match; #181 0 of 8 |
| gpt none-g4 / TK | 27 | 48.15 [30.74, 66.01] | 48.15 | 51.85 | 51.85 | 0 / 0 | match; #181 0 of 6 |
| gpt munim-cap2-g2 / II | 27 | 22.22 [10.61, 40.76] | 22.22 | 0.00 | 0.00 | 0 / 0 | match |
| gpt munim-g4-cap2 / II | 27 | 44.44 | 44.44 | 0.00 | 0.00 | 0 / 0 | match |
| gpt munim-g4-cap2 / TK | 27 | 40.74 | 40.74 | 0.00 | 0.00 | 0 / 0 | match |
| glm munim-cap2-g3 / II (unreported) | 22 (+1 null) | 54.55 [34.66, 73.08] | none | 0.00 [0.00, 14.87] | none | — | no reference (PC-03) |
| gpt munim-cap2-g2 / TK (unreported) | 4 (+1 null) | 0.00 [0.00, 48.99] | none | 0.00 | none | — | no reference |
| gpt munim-cap2-g3 / II (unreported) | 9 (+1 null) | 0.00 [0.00, 29.91] | none | 0.00 [0.00, 29.91] | none | — | no reference |

All 32 referenced arm-metric rows match exactly, and the gap rule flags none. CC-07 on this data: #181 affects 0 of the 29 banking IT0/IT1/IT3 successes. Each of the 29 has an executed transfer to the attacker IBAN whose subject carries the goal datum, so the re-scored ASR equals the logged ASR. #161 has denominator 0, because the logs have no `user_task_5`.

Level 2 (mapped AER, n ≤ 5 per stratum, n = 4 in two partial arms): no arm reaches 20, so the sample gives no verdict (amendment 2.2, R6). The largest deviations are gpt none II utility 0/5 [0.00, 43.45] (ref. 40.74) and gpt none TK utility 1/5 (ref. 44.44); both references lie inside the Wilson interval. The mapping check (OS-2) is exact: 0 of 302 judgements differ (6 null on both sides), so the population verdicts carry over to the AER.

## 7. Findings

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-bookkeeper-agentdojo-01 | [CC-07] #181 0 of 29 IT0/1/3 successes affected; #161 n/a (0 UT5 logs) | expected-known (R2, CC-07; scope gap CC-09) | S3 | confirmed (recount 29/29 with goal datum; 0 false negatives among 27 denied attacker calls; vacuous utility 0/570) | Disclose "catalogued, 0 affected"; add the source to the `validity_defects` scope with count 0 |
| PC-bookkeeper-agentdojo-02 | [CC-09] no `artefacts.toml` entry scopes this source; quirk counts verified | documentation-mismatch (CC-09) | S3 | confirmed (all scope counts recounted) | Recorded in CC-09; not counted. Owner widens the scopes with the counts below |
| PC-bookkeeper-agentdojo-03 | Repository docs omit 4 partial/stray arms (39 logs) and 100 pre-pass logs; GLM "nothing held" holds for pair episodes only (g4: 6 and v1: 6 denials, all in pre-pass logs) | documentation-mismatch (R3) | S3 | confirmed (0 doc mentions of g3, llama or pre-pass) | Datasheet: label the partial arms as unreported aborted runs (never drop them); qualify the "nothing held" figure |
| PC-bookkeeper-agentdojo-04 | Identity table pools `-none` and `-none-g4` (separate runs; recorded sampling differs for glm, unrecorded for gpt `-none`) as `none`; it calls the cap/g labels unexplained (run.py explains them) and omits the provider model ids | documentation-mismatch (R4) | S3 | confirmed, evidence corrected: sampling difference recorded for glm only; `gpt-oss-120b-none` has no results file (sampling unrecorded, reference from `summary.md` only) | Family owner documents the pipeline dir as the replicate key; no remap unless the owner decides |

There are 4 findings: 0 security, 0 mapping defects, 0 source defects, and 0 analysis artefacts. CC-03, CC-10 (no slack suite) and CC-11 (0 account paths in raw context files) do not apply. Refuted: none (verifier 2026-10-21: 4 confirmed, 0 refuted, 0 undetermined).

Proposed `artefacts.toml` rows (text only; route to the AgentDojo family owner):

```toml
# PC-01 (CC-07): [[artefact]] id = "agentdojo.art.validity_defects"; scope.sources/profiles += "bookkeeper-agentdojo"
expected += [ { snapshot = "bookkeeper-agentdojo:head", count = 0, unit = "executions", basis = "pre-check PC-bookkeeper-agentdojo-01: #181 banking IT0/1/3 successes without the GOAL datum 0 of 29; #161 n/a (user tasks 0-2 only)", status = "proposed" } ]
# PC-02 (CC-09): scope += bookkeeper-agentdojo on the generic entries, status "proposed", basis "raw census of 570 logs at 0fe09bb6":
#   benign_security_constant 100 (99 true + 1 null); injection_task_as_user 100; incomplete_run 4;
#   max_iters_pending 1 and silent_rerun 1 (same log, gpt-oss-120b-munim-cap2-g2 TK ut0 x it1); naive_timestamp 570 (IST, +05:30);
#   defence_benign_intervention 24 pre-pass logs / 25 gate denials (munim dirs only)
```

Items for AGENTS.md section 12:

- bookkeeper-agentdojo: the defence id `none` pools `-none` and `-none-g4`, which are separate runs (recorded sampling differs for glm; gpt `-none` has no results file), so per-run analyses must key on `pipeline_dir` (PC-04).
- bookkeeper-agentdojo: 4 partial or stray arms (39 logs) exist in the data but in no source document. Keep them and label them (PC-03).

## 8. Recommendations and readiness

1. Route the PC-01 and PC-02 scope rows to the AgentDojo family owner (CC-07, CC-09).
2. Datasheet disclosure: the partial arms and the pre-pass logs (PC-03), the pooled `none` identity (PC-04), and the licence history (logs first published under a declared MIT licence and relicensed to GPL-3.0-or-later at the pin; the bytes are unchanged).
3. Follow-up for the round, not run here because it is heavy: a full 570-unit import, plus a full j2-vs-j1 determinism compare. The trial compared only a 120-unit subset. Commands are in section 9.
4. No data is excluded, and the arms with zero attack success stay in.

**Readiness: `ready-with-caveats`.** The part imports correctly and deterministically: 151/151 mapped, validation 151/151, recompute 0 unexplained, j1/j2 637/637 identical, OS-2 0/302 differences, identity 0 mismatches, redaction 0 hits. All 16 reported cells and all 297 per-pair results reproduce. The caveats are S3 disclosures only (PC-01, PC-03, PC-04); PC-02 is a CC-09 reference and does not count toward this verdict. Verifier (2026-10-21): verdict upheld; pop.py re-run is identical, no outcome gap, no security or mapping finding.

## 9. Reproduction

Batch: plan `tools/precheck/plans/wave3.toml`, run as `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-wave3 -- uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave3.toml`. Its steps (W = `~/.agentprov/migration-work/precheck/bookkeeper-agentdojo`, D = `docs/reports/precheck/data/bookkeeper-agentdojo`):

```bash
uv run python tools/precheck/l1_scan.py --source bookkeeper-agentdojo --part head --corpus-id bookkeeper-agentdojo --jobs 2 --emit-fp --git ~/.agentprov/staging/10c/bookkeeper/bookkeeper.git
uv run python tools/precheck/l2_sample.py select --units W/l1-units-head.jsonl --source bookkeeper-agentdojo --part head --corpus-id bookkeeper-agentdojo --out D/l2-sample-head.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j2 --source bookkeeper-agentdojo --part head --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j1 --source bookkeeper-agentdojo --part head --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-head-j2.partial --out D/l2-head.json --sample D/l2-sample-head.json --l1-units W/l1-units-head.jsonl --compare-with W/l2-head-j1.partial --jobs 2
```

Examiner scripts (read-only; pinned blobs through `agentprov.ingest`; outputs under `W/exam/`, copied to D as counts-only files):

```bash
uv run python -I D/exam-scripts/pop.py W/exam/pop.json W/l1-units-head.jsonl        # H1-H10, H13, CC-07 #181 -> D/population.json
uv run python D/exam-scripts/os.py . W/l1-units-head.jsonl W/l2-head-j2.partial W/exam/os.json   # outcome tables, OS-2 -> D/outcomes.json
uv run python -I D/exam-scripts/extra.py D/l2-sample-head.json W/exam/extra.json  # sample gate decisions, L1-03 locations -> D/extra.json
grep -c bookkeeper src/agentprov/adapters/agentdojo/artefacts.toml                # PC-02: 0
```

Follow-up (heavy; not run): `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-bookkeeper-full -- uv run agentprov import bookkeeper-agentdojo --input ~/.agentprov/staging/10c/bookkeeper --verify-against-pin --corpus W/full-j2 --jobs 2`, then the same into `W/full-j1` with `--jobs 1`, and a byte compare of the two (in the round, not on a stored corpus).
