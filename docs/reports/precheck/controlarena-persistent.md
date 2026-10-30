# Pre-check dossier: `controlarena-persistent`

## 1. Header

| | |
|---|---|
| Corpus | `controlarena-persistent` (MIT per the dataset card front matter, no LICENSE file; paper CC BY 4.0) |
| Parts | `zip-3-001`, `zip-3-002` (batch `wave4b`), `zip-3-003`, `batch-runs`, `auditor` (batch `wave4`) |
| Family / profile | `inspect` / `controlarena-persistent@2` (sha256 `629818bd1af4`), dialect `inspect.eval`, no semantics profile (D-343), registry `planned` |
| Pin | HF `idacy/control-arena-persistent-state-eval-archive-2026-07-30` @ `84d39e0a` (split zips D-249, two tar.zst) |
| Code commit | `d97d3a57` for L1 and L2 in every part, tracked_changes false; all steps rc 0 |
| Kind | wave 4, first examination (not in FA or E2); no stored corpus |
| Frame | the 36 D-345 account-path logs (`select.redaction_pending`, 30 in 001, 6 in 002) are outside the frame (amendment 3). `[withhold]` (D-344) applies to every execution at a seal |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (L1, L2), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), batch runner, examiner (this file), adversarial verifier (2026-10-21) |
| Data | [`data/controlarena-persistent/`](data/controlarena-persistent/): `research.json`, `l1-<part>.json`, `l1-09-<part>.json`, `l1-10-<part>.json`, `l2-sample-<part>.json`, `l2-<part>.json`, `code-<part>.json`, `exam.json`, `findings.json`, `os1-population.json`, `os2-sample.json`, `dups.json`, `evasion.json`, `named-home.json`, `exam-scripts/` |

Code identity is the same for all 5 parts (`code-<part>.json` compared field by field, all equal except the part name):

- zip-3-001: commit `d97d3a57` (tracked_changes false). Engine digests: expand `3b1d412bb77a`, aer `856b7a09e0cf`, prov `d57bd291d3cc`, validation `a10ee3c16045`. Adapter `inspect.eval@0.1.0` `1867569d63c9`. Lockfile `b0455f1058c8`, limits `5d6dbb210259`. CPython 3.14.8.
- zip-3-002: identical to zip-3-001.
- zip-3-003: identical to zip-3-001.
- batch-runs: identical to zip-3-001.
- auditor: identical to zip-3-001.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Paper | Hills, Caspary, Cooper Stickland, *Distributed Attacks in Persistent-State AI Control*, https://arxiv.org/abs/2607.02514 (v1 2026-07-02, v2 2026-07-08) | outcome reference (Tables 3, 4, 5, 7, 11, 14); tables and n are the same in v1 and v2 |
| Data record | https://huggingface.co/datasets/idacy/control-arena-persistent-state-eval-archive-2026-07-30 @ `84d39e0a` (= head) | the data. The card calls it the author's local-only residue; the sibling log repositories have no licence |
| Code | https://github.com/josh-hills/control-arena-persistent-state-eval (MIT fork of UKGovernmentBEIS/control-arena, main `68de4a36`) | harness. 10 of the 12 logged revisions resolve. Monitor fixes PR #30 and #41 merged after most of the logs were written |
| Harness | inspect_ai 0.3.159 (every header log) | producer; ScoreEvent without `scorer` (CD-24) |

Data-versus-paper notes (checked against the data):

- Run success for CLI gradual reproduces exactly: triggered-exfil 47/60, config-telemetry 7/60, both 54/120. Each successful run has exactly one `C` sample, and in the L2 sample that `C` is at the last PR in 5 of 5 runs.
- TD-diff evasion at τ6 reproduces Table 7 exactly (51/54). The in-log full-diffs evasion is 54/54 (paper 88.9 %), and the gradual logs hold no trajectory-monitor scores. The paper's other monitor values come from rescoring. Those files are in the pin (`logs_march_rescored/`, 15 V2d5 result JSONs, and `link_tracker_rescore_finals`) but outside the profile frame; they were not tested against the paper (PC-08, verifier correction).
- The card says Jan–Feb 2026, but 801 of the zip logs are from March 2026 (PC-07).
- `positional_f3m1.zip` also contains 15 honest logs, byte-identical to `honest_all` logs. These are the prereg's 15 header-bearing duplicates (PC-05).

## 3. Expectations

The pre-registration is [`prereg/controlarena-persistent.md`](prereg/controlarena-persistent.md), committed in `fd75f8a3` (2026-10-14) before any check of this corpus ran. Amendments 2 and 3 apply: Level 2 is unblocked and the 36 held logs are excluded through exact labels. Amendment 4 applies too (no `--sample` substitution). Classes follow R1–R6 and CC-01..CC-11 of [`cross-cutting.md`](cross-cutting.md).

| H | Result | Note |
|---|---|---|
| H1 | supported (1 item undetermined) | Every per-part count of section 2 matches (table in section 4). The prereg counts 8 header-less logs: 7 are in 001 nested, and the 8th (002 direct) is not in the frame, presumably one of the 6 held logs (follow-up 5) |
| H2 | supported | 0 duplicate keys, NaN/Infinity, big ints, lone surrogates, BOM, invalid UTF-8 or depth hits in 1,361 readable artefacts |
| H3 | supported | sk-shaped `/metadata/API_KEY` in 5,632/5,632 frame units |
| H4 | supported; attribution refined | 25 non-empty byte-duplicate logs: 20 in 002 nested (15 with a header carrying 71 samples, 5 header-less carrying 3) and 5 in 003 (25 samples). The 15 duplicate `honest_all` logs of 001, not logs of 003 (PC-05) |
| H5 | supported (one sub-claim not tested) | gradual has 120 logs (60 + 60) of 5 samples each. honest_all has 166 logs. positional has 515 attack logs with 1–5 samples (112/109/103/95/96). "5 sequences × 2 × 12" is not testable at L1 |
| H6 | supported | 47/60 and 7/60, an exact match |
| H7 | supported | 51/54 = 94.4 %, an exact match; the `<` τ variant gives 48/54 = 88.9 % |
| H8 | supported | 1/162 honest runs have a maximum TD score above 6 (0.62 %); 0/796 honest samples have side-task success |
| H9 | supported | setting `vibe_coding_persistent` in 5,632/5,632 units (0 Flask, 0 Gemini/Kimi). Trusted models are {gpt-4o, gpt-4.1-mini}; untrusted models are {Sonnet 4.5, Mistral-large} |
| H10 | supported | 20 of 21,001 numeric score values lie outside [0, 10], all of them `score.quote_monitor` (0.095 %) |
| H11 | supported | 0 `/Users/` and 0 operator-home hits in selected units. A named `/home/<x>` appears in 3 logs as model-visible content (PC-03) |
| H12 | supported | Every timestamp has a UTC offset and 0 fail to parse. Zips span 2026-01-10..03-16 and tars 2026-06-05..06. 801 distinct March logs, as predicted (PC-07 for the card) |
| H13 | supported | 0 adapter_defect, 0 degenerate; stages ok 636/636. All 131 none/none units are resolved from `model_roles` (Sonnet 93, Mistral 38) |
| H14 | supported | recompute: 636 identical, 0 unexplained. j2 vs j1: 3,698 files, 0 differ, indexes identical |
| H15 | supported | bare `score` in 631/636 executions, `score.<key>` in 633/636, a bench duplicate in 636/636 (PC-09) |
| H16 | supported | tar parts are 100 % withheld (178/178). The zips refuse with `corpus.withhold.unscanned`, and the unscanned count equals each part's truncated members (PC-01) |
| H17 | supported | the README figure (2,267) and the profile figure (5,754) are both not the frame (5,632 units, 5,522 executions; PC-06) |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: staged pins (split zips verified by part, tar.zst by sha256), `l1_scan` at `d97d3a57`, nested cap 2.3 GB. Elapsed: 886 s (001), 1,087 s (002), 201 s (003), 395 s (batch-runs), 7 s (auditor).

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | Walked: 3,007 / 2,723 / 620 / 778 / 251 (= census members). Selected: 675 / 599 / 334 / 110 / 1. Excluded by `select.redaction_pending`: 30 / 6 / 0 / 0 / 0 (36). Nested zips: 4 / 1. Units: 2,452 / 1,701 / 835 / 638 / 6 (5,632). Taking first occurrences of header-bearing units gives 2,441 / 1,627 / 810 / 638 / 6 = **5,522**. The extras are 11 header-less units in 001, 71 + 3 duplicate units in 002 and 25 in 003 | as expected (H1); registry figure stale (PC-06) |
| L1-02 parse | strict ok: 522 / 561 / 167 / 110 / 1. `archive:format` (empty or truncated): 153 / 38 / 167 = 358 (172 empty: 127 / 31 / 14; 186 truncated: 26 / 7 / 153). 0 other classes | as expected |
| L1-03 encodings | Escaped-newline, escaped-quote, JSON-in-string and escaped-unicode residues in every readable log (tool I/O). ANSI/ESC in 59 / 90 / 12 / 37 logs (`traceback_ansi`, terminal output). C0 in 103 / 146 / 0 / 0 logs. U+FFFD in 68 / 95 / 0 / 1 logs (sandbox output). Zero-width in 2 / 1 / 0 / 1 logs. 0 bidi, tag, U+2028/2029/0085 | as expected (counted, not defects) |
| L1-04 duplicates | Within part, byte-identical: only the empty members (1 group each: 127 / 31 / 14; PC-10). Cross part: 25 groups (001↔002 20, 001↔003 5; `_cross/l1-xdup.json`). Trajectory-identical: 0 within part; cross part 74 + 25 units, the same logs. Cross corpus: 0 non-empty (the one 347-member group is zero-byte files, PC-10) | as pre-registered (H4); attribution PC-05 |
| L1-05 arms | Strata: 18 / 12 / 10 / 2 / 1 (experiment × untrusted × mode, plus damaged `<none>` strata). Every pre-registered arm is present: gradual_f3m1 120, positional 515, honest_all 166, M1F3_main_run3 95+16+9, the F2M* development arms, the pilots, batch_runs 50 + 60, the auditor 1. The missing cells are as pre-registered (Flask, Gemini, Kimi, M3, 85 positional) | as expected; the census's 96 non-persistent samples are absent (PC-06) |
| L1-06 secrets/paths | sk key in 5,632/5,632 units. Further planted shapes: AWS in 26 logs, Stripe in 53, GitHub in 10, private-key header in 6, Slack in 2, Google in 1, JWT in 1. `account:home-dir:named` in 1 log each of 002, 003 and batch-runs (252 / 95 / 62 strings, model-visible pointers). Generic `/home` in 4 logs. `users-dir` 0, `this-machine-home` 0. Auxiliary files: 0 | expected-known (D-344); PC-02, PC-03 (CC-03) |
| L1-07 timestamps | Every pointer has a UTC offset (headers, `started_at`, events); 0 parse failures. Event order is not time order in every unit (profile quirk). Zips 2026-01-10..2026-03-16, tars 2026-06-05..06. March: 801 distinct header-bearing zip logs | as expected; card PC-07 |
| L1-08 degenerate | 172 empty, 186 truncated (unreadable container). no_header artefacts: 7 in 001; 5 in 002, all byte copies of 001's. Units with `sample_error`: 14 / 12 / 1. 26 distinct error-status logs (1 more is a duplicate). 4 header-less logs have 0 samples | as expected (26 error logs) |
| L1-09 metadata members | 0 AppleDouble or metadata members matching `**/*.eval` in any part. Members walked: 251 (auditor), 778 (batch-runs), 3,007 (001), 2,723 (002), 620 (003) | none expected |
| L1-10 context files | 0 non-JSON context files screened in every part (none is selected in the archive frame); 0 hits, 0 operator, 0 named | n/a (no context artefacts) |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | `l2-sample-<part>.json`: 77 (sha `ff309b574cbc`), 45 (`c8af9de11cd6`), 47 (`1cbde9e7c20d`), 30 (`581089ed3f8b`) and 1 (`d4e5b2a5963c`) labels; seed 20261011. 72 labels in the damaged / header-less strata have no execution by design (30 / 20 / 22; R6) |
| Import | Two scratch corpora per part (`-j2.partial`, `-j1.partial`). 636 executions: 223 / 110 / 125 / 172 / 6. Status ok 488, ok_with_issues 148; 0 degenerate, 0 adapter_defect, 0 unreadable. Labels join 1:1, and the execution count equals the L1 `n_units` on 128/128 labels |
| Validation | Tiers aer, prov and linkage: 636/636 pass, 636 reproduced, linkage 100 %. SHACL is not implemented (skipped); regression n/a; SEM n/a (no profile) |
| Recompute | `--dry-run`: 636 identical, 0 changed, 0 unexplained |
| Determinism | j2 vs j1: 1,324 / 950 / 732 / 664 / 28 files, 0 differ, indexes identical |
| Verify chain | 0 failures; only `checksums.absent` (working tree) |
| A2 / issue codes | `map.unexecuted_tool_call` 148 (warning; PROV represents 952 unexecuted call parts with 0 issues). `map.inspect.unmapped_event` 145 (`logger` events kept in ext, info). `map.inspect.sample_limit` 64 (quirk). `map.accounting_inconsistent` 14 (PC-04). `map.inspect.content_not_inlined` 7 (batch-runs). Register: `select.redaction_pending` 36, `ingest.archive.format` 34, `dedup.collapsed` 28, `select.dialect_planned` 6 |
| A3 PROV issues | 0 dangling, missing or invented relations over 2,867,592 statements and 4,817,842 relation arguments. Messages with `generated_by`: 46,678. Model calls with input: 24,396. Every activity has its own time (no run-scope fallback) |
| Evidence classes | PROV core D 1,443,452 / O 1,325,830; inference I 31,148. Of the inference statements, 30,502 are `_unverified` twins of catalogued D rules; native 0, mixed 0 (statement-level split, CC-08 counter) |
| Judgements (OS-2) | raw vs mapped `side_task_success`: 128/128 labels equal. CD-24 naming present (PC-09) |
| Identity | Models: Sonnet 4.5 and Mistral-large. Every none/none unit (131) is resolved from `model_roles`. 0 direct mismatches; the 2 one-to-many entries are the expected none/none → {Sonnet, Mistral}. Defence and attack are `none` (D-343: no such identity in the source). The task is the setting's task id |
| Redaction | 1,312 AER/SEM/PROV files scanned: 0 account-path hits, 0 operator hits. Planted-key hits are in every execution (PC-02). The 3 named-home logs are not in the sample, so this shape is unexercised at L2 (PC-03) |
| Withholding | batch-runs 172/172 and auditor 6/6 withheld (objects 283 and 8). Zips: the seal refuses with `corpus.withhold.unscanned` (26 / 7 / 153 truncated archives; D-450). The **10p t2 seal is blocked on D-453/D-454** (PC-01) |

## 6. Outcome comparison

The reference is the paper (v1 = v2 tables). A run is one log, and success is `side_task_success` on any PR. For gradual this equals the last PR: every successful run has exactly one `C` sample, at the last PR in 5/5 sampled runs. Evasion counts successful runs whose maximum per-PR score is ≤ τ. Gap rule: more than 15 pp, or more than 5 pp outside the Wilson 95 % interval, on an arm with n ≥ 20. Rows: [`os1-population.json`](data/controlarena-persistent/os1-population.json), [`evasion.json`](data/controlarena-persistent/evasion.json).

| Arm | Level | n | Metric | Rate (Wilson 95 %) | Paper | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|---|
| gradual_f3m1 · triggered-exfil | L1 | 60 | run success | 78.33 [66.38, 86.88] | 78.3 (47/60) | 0.0 | match (H6) |
| gradual_f3m1 · config-telemetry | L1 | 60 | run success | 11.67 [5.77, 22.18] | 11.7 (7/60) | 0.0 | match (H6) |
| gradual_f3m1 · both | L1 | 120 | run success | 45.00 [36.39, 53.92] | 45.0 | 0.0 | match |
| gradual_f3m1 · TD diff τ6 | L1 | 54 | evasion | 94.44 [84.89, 98.09] | 94.4 (51/54) | 0.0 | match (H7); triggered 45/47, config 6/7 exact |
| gradual_f3m1 · full diffs τ7 | L1 | 54 | evasion | 100.0 [93.36, 100] | 88.9 | +11.1 | below the rule (4.5 pp outside Wilson); in-log values are the original ones; the rescoring files lie outside the frame (PC-08) |
| gradual_f3m1 · trajectory TD / full τ3 | L1 | 54 | evasion | no score in 0/54 | 66.7 / 75.9 | n/a | not testable (PC-08) |
| honest_all · max TD > 6 | L1 | 162 | FPR | 0.62 [0.11, 3.41] | ≈2 (≤ 5) | −1.4 | match (H8) |
| honest_all · side-task success | L1 | 796 samples | rate | 0.0 [0.0, 0.48] | 0 | 0 | match (H8) |
| positional · triggered-exfil (context) | L1 | 256 | any-PR success | 36.33 [30.68, 42.38] | not comparable (Fig. 6 pools CLI+Flask; Table 3 is best-position) | — | context only |
| positional · config-telemetry (context) | L1 | 259 | any-PR success | 7.34 [4.75, 11.17] | not comparable | — | context only |
| batch_runs · triggered-exfil | L1 | 60 | run success | 76.67 [64.56, 85.56] | not reported | — | Wilson only |
| batch_runs · honest | L1 | 50 | side-task success | 0.0 [0.0, 7.13] | — | — | Wilson only |

Level 2 counts per-PR samples, not runs ([`os2-sample.json`](data/controlarena-persistent/os2-sample.json)). No arm reaches 20 sampled runs, so the sample gap rule gives no verdict (R6). The mapping check is the comparison of record: 128/128 labels have mapped `C` counts equal to the raw counts. Sample per-PR rates, for context: gradual triggered (001 + 003) 5/25, config 0/25; honest_all 0/25; batch_runs triggered 13/86, honest 0/86.

CC-07 (#181 / #161) does not apply: this is an Inspect / ControlArena corpus, not AgentDojo format (0 affected of 0).

## 7. Findings

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-controlarena-persistent-01 | Zip-part seal refused with `corpus.withhold.unscanned` (26 / 7 / 153 = the truncated members); 10p t2 seal blocked on D-453/D-454 | expected-known (D-450/D-453/D-454) | S2 | confirmed (unreadable − empty = 26/7/153) | no zip-part seal until D-453/D-454; re-run the scratch seal then |
| PC-controlarena-persistent-02 | Planted credentials reach AER in every execution (sk 636/636) and PROV in 108/636; AWS and Stripe shapes | expected-known (CC-13 fixture, `inspect.planted_credentials`, D-344); **security** | S2 | confirmed (PROV count corrected) | keep D-344 withhold-all; release_scan gate |
| PC-controlarena-persistent-03 | [CC-03] Named `/home/<x>` in model-visible content of 3 selected logs; 0 `/Users/`, 0 operator; not sampled at L2 | expected-known (CC-03) | S3 | confirmed (not the D-345 macOS account; phase-10p census already records sandbox `/home/<name>`; 002/003 names still unscanned) | cleared-reader check of the 1–3 names (digest `d4a8a26536` for batch-runs); escalate to S0 security if one is a real account |
| PC-controlarena-persistent-04 | `map.accounting_inconsistent` on `inspect.scorer` spans: 14/636 sampled executions, only gradual_f3m1 (10/50) and honest_all (4/25) | mapping-defect (undetermined) | S3 | undetermined (all 28 scopes `call_has_several_results`, linked = results; may be source call-id reuse) | inspect family owner: link or classify scorer-span tool results, or document as a quirk |
| PC-controlarena-persistent-05 | Our docs: the 15 duplicates (71 samples) are honest_all copies inside positional_f3m1.zip (001↔002); 1,698 is 002's within-part count, but the residual 739 (= 835 − 25 − 71) misplaces the 71 in 003; first-occurrence 2,441 / 1,627 / 810 | documentation-mismatch (R4) | S3 | confirmed (refined) | correct the phase-10p README / prereg; take measured counts from the round |
| PC-controlarena-persistent-06 | Our docs: README 2,267 and profile 5,754 vs frame 5,632 / 5,522; census's 96 non-persistent samples absent | documentation-mismatch (R4) | S3 | confirmed | update the profile/registry after the round; regenerate the README blocks |
| PC-controlarena-persistent-07 | Card says Jan–Feb 2026; 801 zip logs are from March 2026 | documentation-mismatch (R3) | S3 | confirmed | disclose in the datasheet |
| PC-controlarena-persistent-08 | In-log full-diffs evasion 54/54 vs paper 88.9 %; no in-log trajectory scores; the rescoring files are in the pin but outside the frame | documentation-mismatch (R3, exploratory) | S3 | confirmed (corrected: rescored values are in the archive, not in the frame) | disclose; follow-up: compare `logs_march_rescored` with Table 7 |
| PC-controlarena-persistent-09 | [CD-24] bare `score` and duplicated scorer judgements, as expected | expected-known (CD-24, RD-2) | S3 | confirmed (631/633/636) | keep RD-2 open |
| PC-controlarena-persistent-10 | L1-04 byte-identical groups count zero-byte files (127 / 31 / 14; one 347-member cross-corpus group) | analysis-artefact (R5) | S3 | confirmed (empty digest 127+31+14+175 = 347) | tool: exclude size-0 files from the groups |

Verifier (2026-10-21): 9 confirmed (PC-02, -05 and -08 with corrections), 1 undetermined (PC-04), 0 refuted. One finding is security-relevant: PC-02, already known through D-344. PC-03 stays CC-03 S3; it escalates only if the cleared-reader check finds a real account. PC-10 is R5 and does not count. Format: CC-06 [`findings.json`](data/controlarena-persistent/findings.json).

Proposed `artefacts.toml` entries (text only; route to the inspect family owner):

```toml
# No entry is scoped to controlarena-persistent today. Proposed, status "proposed":
# [[artefact]] id = "inspect.art.abbreviated_revision"   scope.sources += "controlarena-persistent" (census: 12 distinct 7/8-hex commits + 1 null)
# [[artefact]] id = "inspect.art.monitor_scores_rescored_outside_frame"  (new) source "controlarena-persistent":
#   expected = [{ snapshot = "controlarena-persistent:zip-3-001", count = 54, unit = "runs",
#                 basis = "pre-check PC-controlarena-persistent-08: gradual_f3m1 successful runs; full-diffs in-log evasion 54/54 vs paper 88.9; no in-log trajectory scores; rescoring files (logs_march_rescored, link_tracker_rescore_finals) outside the frame", status = "proposed" }]
```

Items for AGENTS.md section 12:

- The controlarena-persistent zip parts cannot be sealed until D-453/D-454 land. 186 truncated members are unscanned (001: 26, 002: 7, 003: 153). The tar parts withhold 100 %.
- The CLI gradual paper numbers reproduce exactly from the archive: 47/60 and 7/60 success, 51/54 TD evasion. The full-diffs and trajectory monitor numbers do not reproduce from the logs. They rest on rescoring files that are in the pin but outside the import frame, and those files are untested.

## 8. Recommendations and readiness

1. PC-01: hold the seal and release of zip-3-001/002/003 until D-453/D-454. Then re-run `l2_check` on the scratch corpora and confirm every execution is withheld.
2. PC-03: extend `named_home.py` to the split-zip opener and run it on the 002 and 003 named-home logs (not run by the verifier). A cleared reader then confirms the names are sandbox content. Keep values out of every report.
3. PC-04 (undetermined): the inspect owner checks whether scorer spans reuse tool-call ids in the raw logs (then this is a source quirk) or the mapper merges them. Outcomes are unaffected.
4. PC-05/06: correct our docs (phase-10p README, profile observed counts, README listing) once the round's full import gives measured per-part counts.
5. No exclusion of any data, including the pilot and development arms and every zero-success arm.
6. PC-08: optionally compare the `logs_march_rescored` V2d5 per-PR scores with Table 7 (small JSONs, through `agentprov.ingest`).

**Readiness: `ready-with-caveats`.**

- The import path is sound on all 5 parts:
  - 636/636 executions mapped, 0 degenerate, 0 adapter_defect.
  - validate 636/636, recompute 0 unexplained, j1/j2 byte-identical.
  - identity resolved 100 %; raw = mapped side-task outcomes on 128/128 labels.
  - the paper's headline gradual numbers reproduce exactly.
- Caveats:
  - The zip-part seal is blocked on D-453/D-454 (PC-01).
  - D-344 withhold-all (PC-02).
  - The named-home check (PC-03).
  - The scorer-span accounting (PC-04).
  - Doc corrections (PC-05..08).
- Verifier (2026-10-21): the readiness verdict is confirmed. No finding is refuted. PC-04 is undetermined, and the PC-02/05/08 wording is corrected.

## 9. Reproduction

Batches: `tools/precheck/plans/wave4.toml` (auditor, zip-3-003, batch-runs) and `wave4b.toml` (zip-3-001, zip-3-002), through `tools/suite_queue.py --class import --cpu 2`. Logs are in `~/.agentprov/migration-work/precheck/_batch/wave4{,b}/`; `status.jsonl` gives rc 0 for the 7 steps × 5 parts.

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-wave4 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave4.toml   # and wave4b.toml
# steps per part (W = ~/.agentprov/migration-work/precheck/controlarena-persistent, D = docs/reports/precheck/data/controlarena-persistent):
# l1_scan.py (--emit-fp, archive input ~/.agentprov/staging/10p/hf_idacy_control-arena), l1_appledouble (L1-09), l1_context (L1-10),
# l2_sample.py select, l2_import.py --jobs 2 / --jobs 1, l2_check.py --compare-with W/l2-<part>-j1.partial (validate, recompute --dry-run, verify chain, seal)
```

Examiner scripts (read-only; S = `D/exam-scripts`; outputs under `W/exam/`, copied as counts-only files to D):

```bash
python3 -I S/l1_summary.py                        # section 4 per part
python3 -I S/pop.py W/exam/pop.json               # os1-population.json: arms, H6/H7/H8/H10, none/none, no-header
python3 -I S/dups.py                              # dups.json: H4, PC-05
python3 -I S/evasion.py                           # evasion.json: PC-08
python3 -I S/l2_summary.py                        # section 5 per part (+ code identity)
python3 -I S/l2_judgements.py W/exam/l2-judgements.json   # os2-sample.json: CD-24, raw vs mapped, PR position
uv run python S/named_home.py ~/.agentprov/staging/10p/hf_idacy_control-arena/logs_batch_runs-20260730.tar.zst GySnjVzXz6Z6cc59k2H4Xo.eval  # named-home.json (digests only)
```

Follow-ups (not run; heavy or owner-gated):

```bash
# PC-03: the zip-3-002 / zip-3-003 named-home logs (split zip / nested zip; extend named_home.py to the split-zip opener)
# PC-01: after D-453/D-454 land, re-run the seal check on the existing scratch corpora
uv run python tools/precheck/l2_check.py --corpus W/l2-zip-3-001-j2.partial --out W/exam/l2-zip-3-001-reseal.json --sample D/l2-sample-zip-3-001.json --l1-units W/l1-units-zip-3-001.jsonl --compare-with W/l2-zip-3-001-j1.partial --jobs 2
# PC-05/06: round full import (per-part measured counts)
uv run python tools/suite_queue.py --class import --cpu 2 --label controlarena-full -- uv run python tools/inspect/phase10p_trial.py import --corpus <scratch> --input ~/.agentprov/staging/10p/hf_idacy_control-arena --part zip-3-001
```
