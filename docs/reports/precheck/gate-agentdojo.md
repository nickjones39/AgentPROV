# Pre-check dossier: `gate-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `gate-agentdojo` (own corpus, AGPL-3.0-only, D-94; logs embed AgentDojo suite text, MIT) |
| Parts | `gate-agentdojo · head` (1 part) |
| Family / profile | `agentdojo` / `gate-agentdojo@1` (dialect `agentdojo.tracelogger`, variants `v1.k14`, `v1.k14.incomplete`; semantics `agentdojo.suites@2`) |
| Pin | git `dafarusd/gate` @ `925b9926` (2026-09-26T20:57:02Z, = HEAD), tree 4,155 blobs |
| Code commit | `d97d3a57` (batch `wave3`, steps l1, l1_10, sample, import_j2, import_j1, check all rc 0; tracked_changes false) |
| Kind | wave 3, first examination (not in FA or E2, so no delta since E2); no stored corpus |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (L1, L2 batch), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), examiner (this dossier); adversarial verifier (1/1, 2026-10-21: 6 confirmed, 1 added, 0 refuted) |
| Data | [`data/gate-agentdojo/`](data/gate-agentdojo/): `research.json`, `l1-head.json`, `l1-10-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `findings.json`, `pop.json`, `os1-population.json`, `os2-sample.json`, `exam-scripts/` |

- Code identity, part `head` ([`code-head.json`](data/gate-agentdojo/code-head.json)): commit `d97d3a57` (tracked_changes false); engine code aer `856b7a09e0cf`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `agentdojo.tracelogger@0.1.0` `03d8bc6d30df`; profile sha256 `cf2c70ccc2cc`, rules agentdojo 2 / aer 1; lockfile `b0455f1058c8`, limits `5d6dbb210259`. This run is after the CC-08 tool fixes (5efa3575), so the twin split and the L1 `null_final` / `trailing_calls` rules are the fixed ones.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Repository | https://github.com/dafarusd/gate @ `925b9926` (1 branch, 0 tags, releases, issues or forks) | the data; README, STATE.md: `results/` arms |
| Draft paper | https://github.com/dafarusd/gate/blob/925b99260beec53d94bd48b587b0bdc33614e3df/paper/DRAFT.md (unpublished, revised 2026-08-25) | `gatellml/results/` arms (§2-§6) |
| Pre-registrations | `gatellml/STATE.md` Addenda A-R, `gatellml/results/FINAL_SUMMARY.md` (at the pin) | g4-g8 arms and summary tables |
| Data record | none (no arXiv, DOI, Zenodo, HF or Figshare) | git blob ids only |
| Harness | AgentDojo 0.1.35 (unpinned install); `agentdojo.scripts.benchmark` for `local`, `src/run_defended.py` for the rest | producer and scorer |
| Upstream issues | ethz-spylab/agentdojo [#181](https://github.com/ethz-spylab/agentdojo/issues/181), [#161](https://github.com/ethz-spylab/agentdojo/issues/161), [#168](https://github.com/ethz-spylab/agentdojo/issues/168), [#214](https://github.com/ethz-spylab/agentdojo/issues/214) | checker and harness defects |

Data-versus-paper notes (research.json, checked against the data):

- All 126 pre-registered per-experiment numbers reproduce exactly from the raw `utility`/`security` fields (section 6). This covers the README headline, ladder and focused grid, the STATE.md phases, and the draft's §2/§4/§5/§6 and FINAL_SUMMARY.
- The README's "0 in 135" holdout figure leaves out the empty h03 log; the logs give 0/136 with it.
- The v1-CONTAMINATED "≈5 %" from STATE.md is exactly 3/61. 1 more attacked log is incomplete and has no outcome.
- The `local` directory (215 logs) is all benchmark v1.2.2. Every other log is v1.2. Which model is in `local` is documented only (STATE.md), so it is still unresolved (D-105).
- The ladder models qwen3-5-9b and qwen3-6-35b-a3b end with an empty answer in 234 of 366 logs (PC-03). The other 75 35b logs make no structured tool call; 72 write `<function` text instead (PC-07). The README reports the 0 % rows without saying so.

## 3. Expectations

Pre-registration: [`prereg/gate-agentdojo.md`](prereg/gate-agentdojo.md), committed in `fd75f8a3` (2026-10-14), before any data check. Amendments 2 (strata, outcome levels), 4 (D-529 not substituted) and 6 (batch execution) apply. Amendment 1 does not, because there is no stored corpus. Classes follow R1-R6 and CC-01..CC-11 of [`cross-cutting.md`](cross-cutting.md).

| H | Result | Note |
|---|---|---|
| H1 | supported | 126/126 targets equal (per experiment ASR, utility under attack in both tools' readings, benign utility; c1/c2/sk1/tk1; block episodes b3 25/27, t3 2/21, s3 11/15; holdout gated UA 61.1-72.2 %) |
| H2 | supported | attacked `security` true 125 of 2,379; v1-CONTAMINATED 3, v5-fullgrid 0/70, v6-focused 0/28, smoke-gatellm 0/1 |
| H3 | supported | `local` = 154 + 40 + 1 + 10 + 10 = 215, all v1.2.2; the other 3,657 (incl. 2 demo) v1.2 |
| H4 | not tested | the sample holds both demo labels (each `identity_unresolved`) but not their v2/v6 twins, so no dedup ran; full import needed (follow-up 1) |
| H5 | supported (with a correction) | logs with an orphan tool result 819 = logs with a denial 819; 0 orphans without a denial; 0 denials in the 215 `local` logs. The 819th log is the demo gated copy, not a `local` log (PC-04) |
| H6 | supported | 1,101 denial messages in `gate-*` (all 376, gatellm 695, echo 30) + 1 in the demo copy; 0 in `gate-off` |
| H7 | supported | 0 September logs outside g4..g8, 0 August logs inside |
| H8 | supported | every experiment falls on its documented day (one 235b ladder dir runs 08-21..08-22) |
| H9 | supported (gap clause) | b4 has 1 gap > 1 h, c2 and all other dirs have 0; the duplicate clause cannot fail at path level (prereg note) |
| H10 | supported | 0 secret-like strings and 0 account paths in 3,872 logs and 5 auxiliary JSON; L1-10: 23 context files, 0 hits |
| H11 | supported | 0 of 6 echo travel `injection_task_6` finals contain the payload term (non-echo 480b gatellm: 10/15) |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: the staged bare clone at `925b9926` (`--git`, lazy fetch off), `l1_scan` at `d97d3a57`, 3.5 s.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 4,155 walked = 3,872 selected + 28 context + 254 not selected + 1 absent blob (the PNG); 0 excluded or rejected; 3,872 units = registry figure = census | as expected (283 not selected) |
| L1-02 parse | strict ok 3,872/3,872; auxiliary 5/5; 0 defects of any class | as expected |
| L1-03 encodings | 0 controls, bidi, zero-width, U+FFFD or mojibake. Escaped `\uXXXX` residues: 151 files / 203 strings, all in tool output (`/messages/*/content/*/content`). Escaped newlines in 902 files; escaped quotes in 49; JSON-in-string args (`participants`, `attachments`) in 36 | as expected (#214-type residues, model-serialised args) |
| L1-04 duplicates | byte-identical: 2 groups / 4 files = the 2 `results/demo` copies (v2, v6). Trajectory-identical (CC-01): 415 groups / 1,165 of 3,870 fingerprinted units (pre-passes, k-repeats, ladder dirs). `_cross/l1-xdup.json`: 2 cross-corpus groups touching gate (ceferisbarov 2, authority-caps, dca, interbolt, melon 1 each; short trajectories) | byte duplicates as expected; the 2 cross-corpus groups are a CC-01 fingerprint property, not shared data |
| L1-05 arms | 83 strata (pipeline_dir × attack_dir × suite), 152 experiment dirs; grid as in prereg §3 (h03 2 files, no 35b benign-gated dir, ladder workspace only) | as expected (H1, H2) |
| L1-06 secrets/paths | 0 / 3,872; auxiliary 0 / 5; L1-10 23 context files, 0 hits, 0 operator hits | as expected (H10) |
| L1-07 timestamps | `/evaluation_timestamp` 3,872/3,872, all naive, 0 parse failures, 2026-08-20..2026-09-18. The 12 "non-monotone" units are benchmark calendar arguments, not run times | as expected (H7, H8) |
| L1-08 degenerate | zero_messages 2 (the h03 logs), incomplete 3 (2 h03 + 1 v1-CONTAMINATED), trailing_calls 13, layout_mismatch 2 (demo), `error` null 3,872. **null_final 234**: qwen3-5-9b 131/188, qwen3-6-35b-a3b 103/178, 0 in any other model. All 234 have empty text blocks; 0 have content null | null_final ≠ the profile's silent-rerun count 0 (whose trigger is content null): PC-03 |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`l2-sample-head.json`](data/gate-agentdojo/l2-sample-head.json) (sha256 `ab01b69cd216...`): 300 of 3,872, 83 strata, quotas reduced to the cap (mostly 4 per stratum), seed 20261011 |
| Import | 2 scratch corpora (`l2-head-j2.partial`, `-j1.partial`). 300/300 mapped: 298 agent_execution + 2 outcome_only (the h03 logs). Status: 239 ok, 61 ok_with_issues. 0 degenerate, 0 `adapter_defect`, 0 failed. Join 300 labels → 300 executions, 1:1 |
| Validation | tiers aer, sem, prov, linkage: 300/300 pass, 300 reproduced, linkage 300/300. SHACL not implemented (skipped); regression n/a |
| Recompute | `--dry-run`: 300 identical, 0 changed, 0 unexplained |
| Verify chain | 0 failures; only `checksums.absent` (working tree). No sealed copy needed (no `[withhold]`, 0 L1-06 hits) |
| Determinism | j2 vs j1: 1,235/1,235 files, 0 differ, index identical |
| A2 register codes | accounting_unverifiable 298, earlier_attempts_unobservable 298, identity_unresolved 8 (6 `local` + 2 demo), orphan_tool_result 51, unexecuted_tool_call 1, no_execution_observed 2, no_outcome_recorded 2. Only the trial's code set appears |
| A3 PROV issues | 0 dangling, missing or invented relations over 127,505 statements / 216,220 relation arguments. 1,815 messages with `generated_by`, 1,039 model calls with input, 707 tool executions with a call. The 1 unexecuted call is represented |
| Gate decisions | run logs: 68 raw denial messages in 50 sampled logs → 68 `decision` records (rule `agentdojo.defence_denial_message@1`, class I) in 50 executions; no tool execution for a denied call. Demo gated copy: its 1 denial becomes a `tool_execution` (status error, call ambiguous, positional match) and there is no decision (PC-04) |
| Evidence classes | AER: every agentdojo D rule appears only as its `_unverified` twin (D-24, D-103). PROV: core D 1,457 (engine rules) / O 7,137; inference I 37,774; assessment I 10,323 / O 600 / D 5. Statement-level split (CC-08, fixed): twin assessment I 4,893, inference I 31,701, inference none 2,941; mixed inference I 4,588; native 0 |
| Judgement origins | `harness_default` 116 benign/pre-pass security judgements are excluded from ASR (`benign_security_constant`) |
| Identity | 0 direct mismatches. Model from the pipeline dir via the table (class I) for every resolved dir. `local` (6) and demo (2) are unresolved. Defence: off/`local` → none, all → gate-all, gatellm → gate-gatellm, echo → gate-gatellm-echo. The header pipeline names of the 480b gate-all/off dirs map to 2 AER values only because of the 2 demo copies |
| Judgements (OS-2) | raw = AER on 49 of 50 arms. The one exception is a tool keying artefact: the 2 unresolved demo copies fold into `none|none|important_instructions` with 3 `local` runs (PC-06). Per label the values are equal |
| Redaction | 908 AER/SEM/PROV files, 0 hits |
| Withholding | not applicable (no policy; nothing to withhold) |
| Degenerate | 234 empty-answer logs (24 in the sample) map to an assistant message with empty text. No issue code, no silent-rerun inference (PC-03). 4 sampled 35b text-written-call logs: 0 SEM/PROV `text_tool_call` annotations (PC-07) |

## 6. Outcome comparison

**Level 1, per experiment (the paper's reading).** The prereg §4 list has 122 per-experiment targets plus the 4 repeat groups. Each was compared with the raw tallies of [`os1-population.json`](data/gate-agentdojo/os1-population.json). Metrics:

- ASR: attacked files only.
- Utility under attack: `aggregate.py` reading (attacked + pre-pass) for `results/`, `suite_summary.py` reading (attacked only) for `gatellml/`.
- Benign utility: `user_task_*/none` files.

**126/126 equal, gap 0.00 pp in every row.** Headline rows:

| Experiment (arm) | n | Metric | Logs (Wilson 95 %) | Paper | Gap | Verdict |
|---|---|---|---|---|---|---|
| p1 (`local` 32k, none, ws) | 140 | ASR | 1.43 (2/140) [0.39, 5.06] | 2/140 | 0 | match |
| p2 (32k gate-all v1, ws) | 140 | ASR | 0.00 (0/140) [0.00, 2.67] | 0/140 | 0 | match |
| v2 / v3 (480b off / all, ws) | 70 | ASR | 7.14 (5/70) / 0.00 (0/70) | 5/70, 0/70 | 0 | match |
| ladder 235b off | 70 | ASR | 31.43 (22/70) [21.76, 43.03] | 22/70 | 0 | match |
| ladder 9b, 35b off/all | 70 each | ASR | 0.00 (0/70) [0.00, 5.20] | 0/70 | 0 | match; 9b: answering logs 0/43 too; 35b: empty finals + text-written calls (PC-03, PC-07) |
| ladder 35b off | 10 | benign utility | 0.00 (0/10) [0.00, 27.75] | 0/10 | 0 | match; empty finals 7 + no-call 3 (PC-03, PC-07) |
| p3-holdout h01..h10 (480b all) | 136 | ASR | 0.00 (0/136) | 0/135 (h03 empty excluded) | 0 | match |
| b4 / b3 (480b off / all, banking) | 27 | ASR | 88.89 (24/27) [71.94, 96.15] / 0.00 (0/27) | 24/27, 0/27 | 0 | match as logged; #181 (PC-01) |
| l5 ungated / gate (32k, banking) | 27 | ASR | 48.15 (13/27) [30.74, 66.01] / 0.00 | 13/27, 0/27 | 0 | match as logged; #181 (PC-01) |
| s4 / s3 (480b off / all, slack) | 15 | ASR | 73.33 (11/15) / 26.67 (4/15) | 11/15, 4/15 | 0 | match |
| t4 / t3 (480b off / all, travel) | 21 | ASR | 19.05 (4/21) / 14.29 (3/21) | 4/21, 3/21 | 0 | match |
| gw2 / g6 (480b gatellm, ws) | 140 | ASR; UA | 0/140; 56/140, 64/140 | same | 0 | match |
| b1 / g-banking-benign-gated | 16 | benign utility | 56.25 (9/16) / 43.75 (7/16) | 9/16, 7/16 | 0 | match as logged; #161 1 each (PC-02) |
| b4 banking, GOAL-datum re-score (info) | 27 | ASR | 77.78 (21/27) [59.24, 89.39] | 24/27 | −11.11 | not the logged metric (PC-01) |
| b4 banking, precedence-only fix (info; it1 datum `me`) | 27 | ASR | 74.07 (20/27) | 24/27 | −14.81 | not the logged metric (PC-01, verifier) |
| l5 ungated, GOAL-datum re-score (info) | 27 | ASR | 40.74 (11/27) [24.51, 59.27] | 13/27 | −7.41 | not the logged metric (PC-01) |
| b1 / g-banking gated without vacuous UT5 (info) | 16 | benign utility | 50.00 (8/16) / 37.50 (6/16) | 9/16, 7/16 | −6.25 | not the logged metric (PC-02) |

The pooled population rates per arm (model × defence × attack) are in [`os2-sample.json`](data/gate-agentdojo/os2-sample.json). They pool experiments that the paper reports separately (for example 480b gate-all ASR 18/335 includes sk1/tk1 10/10). The paper has no pooled figure, so the gap rule is applied per experiment, above.

**CC-07 on this data** ([`pop.json`](data/gate-agentdojo/pop.json)):

- #181: 15 banking IT0/1/3 successes. 5 have no GOAL datum in any executed attacker-bound transfer: b4 3/9, l5 2/6. 0 have no executed attacker transfer at all. The gated banking arms have 0 successes and are unaffected. Verifier: 0 of the 5 hold the datum after normalising case and separators. A precedence-only fix (upstream it1 datum `me`, as interbolt PC-01) flips all 5 it1 successes, so b4 → 20/27, l5 → 11/27.
- #161: 4 benign `user_task_5` logs, all with utility true. 2 have no executed Spotify payment (b1 gate-all 1, g-banking-benign-gated 1; the gate denied the payment).

**CC-10 (#168):** 33 attacked slack `injection_task_5` logs, 3 successes (s4, 480b off). All 3 executed every membership call, so the count is 0 affected.

**Level 2 (mapped AER of the 300-unit sample).** No arm reaches 20 sampled executions (most have 4, at most 16), so the sample gap rule gives no verdict (amendment 2.2, R6). Selected arms:

| Arm (model / defence / attack) | n | Metric | Sample (Wilson 95 %) | Population | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|
| 480b / none / II | 12 | ASR | 41.7 (5/12) [19.3, 68.0] | 23.2 (47/203) | +18.5 | n < 20 |
| 480b / gate-all / II | 16 | ASR | 12.5 (2/16) [3.5, 36.0] | 5.4 (18/335) | +7.1 | n < 20 |
| 480b / gate-gatellm / II | 16 | ASR | 0.0 (0/16) [0.0, 19.4] | 2.9 (14/488) | −2.9 | n < 20 |
| 32k / none / II | 12 | ASR | 25.0 (3/12) [8.9, 53.2] | 28.6 (18/63) | −3.6 | n < 20 |
| 32k / gate-all / II | 16 | utility | 31.2 (5/16) [14.2, 55.6] | 58.1 (118/203) | −26.9 | n < 20 (2.5 pp outside Wilson, under 5) |
| 480b / none / none | 9 | utility | 66.7 (6/9) [35.4, 87.9] | 73.8 (121/164) | −7.1 | n < 20 |
| 35b / both / II | 4 + 4 | utility | 0.0 (0/4) each | 0.0 (0/70) each | 0.0 | n < 20 |

## 7. Findings

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-gate-agentdojo-01 | [CC-07, #181] banking IT0/1/3 successes without the GOAL datum: 5 of 15 (b4 3/9, l5 2/6) | expected-known (R2, CC-07; scope gap CC-09) | S3 | confirmed (1/1); precedence-only re-score added | Disclose next to b4 24/27 (GOAL-datum 21/27, precedence-only 20/27) and l5 13/27 (11/27 both); keep the logged booleans |
| PC-gate-agentdojo-02 | [CC-07, #161] banking `user_task_5` vacuous passes: 2 of 4 (b1, g-banking-benign-gated) | expected-known (R2, CC-07) | S3 | confirmed (1/1) | Disclose (gated benign utility −1/16 each) |
| PC-gate-agentdojo-03 | Empty final answers in 234 logs (9b 131/188, 35b 103/178). The silent-rerun trigger (content null) does not fire. They co-occur with utility loss (9b attacked 0/97 vs 43/43 answering), not with the 9b 0 % ASR | source-defect (R1, uncatalogued) | S2 | confirmed (1/1); causal claim corrected | Disclose on the capability-ladder rows; no exclusion; the family owner decides on the v1.k14 empty-text trigger (as agentdojo-upstream PC-08) and catalogues the class |
| PC-gate-agentdojo-04 | The identity-less denial is in the demo gated copy, not a `local` log (profile comment, r1 census, prereg). It maps to a `tool_execution` with status error and no decision; if dedup keeps the demo origin, the v6 execution inherits this | documentation-mismatch (R4) | S3 | confirmed (1/1) | Fix the profile comment; the family owner decides on dedup origin preference or a D-92 row for `results/demo` |
| PC-gate-agentdojo-05 | [CC-09] reference: no `artefacts.toml` entry scopes `gate-agentdojo`; quirk counts verified | documentation-mismatch (CC-09) | S3 | confirmed (1/1) | Counted once in CC-09; scope rows below |
| PC-gate-agentdojo-06 | `l2_check` arm key renders unresolved as `none` (demo copies fold into the `local` arm) | analysis-artefact (R5) | S3 | confirmed (1/1) | Tool owner: key unresolved values distinctly |
| PC-gate-agentdojo-07 | 35b: 75 of 178 logs make no structured tool call; 72 write `<function` text in their single turn (heuristic). With PC-03 this covers 178/178 35b logs and its 0 % rows | expected-known (R2: `agentdojo.art.text_tool_call`; scope gap CC-09), raised to S2 (drives an undisclosed ladder row) | S2 | added by verifier | Disclose on the 35b ladder rows; no exclusion; scope row for the family owner |

7 findings (6 examiner + 1 verifier-added), all confirmed, 0 security-relevant, 0 mapping defects, 0 refuted. PC-05 (reference) and PC-06 (R5) do not count in the readiness verdict.

Proposed `artefacts.toml` entries (text only; route to the AgentDojo family owner):

```toml
# PC-01 / PC-02: extend agentdojo.art.validity_defects
#   scope.sources += "gate-agentdojo"; scope.profiles += "gate-agentdojo" (snapshot gate-agentdojo:head)
expected += [
  { snapshot = "gate-agentdojo:head", count = 5, unit = "executions", basis = "pre-check PC-gate-agentdojo-01: banking IT0/1/3 security true without the GOAL datum in an executed attacker-bound transfer (b4 3/9, l5 2/6)", status = "proposed" },
  { snapshot = "gate-agentdojo:head", count = 2, unit = "executions", basis = "pre-check PC-gate-agentdojo-02: banking user_task_5 utility true without an executed Spotify payment (b1 1, g-banking-benign-gated 1)", status = "proposed" },
]
# PC-07: extend agentdojo.art.text_tool_call: scope += gate-agentdojo
#   expected += { snapshot = "gate-agentdojo:head", count = 72, unit = "executions", basis = "pre-check PC-gate-agentdojo-07: qwen3-6-35b-a3b single-turn logs with <function text and no tool_calls (heuristic)", status = "proposed" }
# PC-03: new entry (cause unverified: provider/harness; detector = all text blocks empty and no tool_calls)
# [[artefact]] id = "agentdojo.art.empty_final_answer"; scope gate-agentdojo
#   expected = [{ snapshot = "gate-agentdojo:head", count = 234, unit = "logs", basis = "pre-check PC-gate-agentdojo-03 (9b 131, 35b 103)", status = "proposed" }]
# PC-05 (CC-09): scope += gate-agentdojo on benign_security_constant 1491, injection_task_as_user 562,
#   incomplete_run 3, empty_log 2, naive_timestamp 3872, defence_benign_intervention (count from the round's full import)
```

Items for AGENTS.md section 12:

- PC-01/02 (CC-07): gate banking ungated ASR as logged is b4 24/27 and l5 13/27. With the GOAL datum, #181 re-scores them to 21/27 and 11/27 (precedence-only fix: 20/27 and 11/27). b1 and g-banking-benign-gated benign utility each include 1 vacuous UT5 pass.
- PC-03/07: the gate ladder 9b/35b arms end with an empty answer in 234 of 366 logs; this costs utility (9b attacked 0/97 vs 43/43 answering), but the 9b 0 % ASR also holds for answering logs. The 35b arm's 0 % rows reflect degenerate runs (103 empty finals after tool calls + 75 logs with no structured call, 72 text-written), not robustness. Disclose; do not exclude.

## 8. Recommendations and readiness

1. Route the PC-01/PC-02 scope rows (CC-07), the PC-03 candidate entry, the PC-07 `text_tool_call` scope row and the PC-05 scope widening (CC-09) to the AgentDojo family owner.
2. PC-04: correct the profile comment (lines 176-177) and decide which origin the dedup keeps: the run path, or `results/demo` with a D-92 row. Test H4 in the full import (follow-up 1).
3. Disclose PC-01/02/03/07 next to the paper-derived numbers in the datasheet. Report the logged values as primary and any re-score in a separate, labelled column.
4. No exclusion of any data. The zero-ASR arms (ladder 9b/35b, gated arms) stay in.

Verifier (2026-10-21): every count re-run over the 3,872 pinned blobs (`exam-scripts/verify_counts.py`, `verify_35b_textcalls.py`, `verify_it1_precedence.py`), `os1.py` re-run byte-identical (126/126, 0 differing). Readiness unchanged.

**Readiness: `ready-with-caveats`.**

- The import is correct and deterministic: 300/300 mapped, validation 300/300, recompute 0 unexplained, j1/j2 byte-identical (1,235 files). Gate denials become class-I decisions (68/68). Identity has 0 mismatches and redaction 0 hits. L1 outcomes match the paper on 126/126 targets.
- Caveats, none blocking: PC-01/02 (CC-07 disclosure), PC-03 (empty answers in two ladder arms; utility loss), PC-07 (35b text-written calls; with PC-03 every 35b log either ends empty after tool calls, 103, or makes no structured call, 75), PC-04 (one demo-path execution without a decision; dedup origin).

## 9. Reproduction

Batch (wave 3; plan `tools/precheck/plans/wave3.toml`):

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave3 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave3.toml
```

Steps (W = `~/.agentprov/migration-work/precheck/gate-agentdojo`, D = `docs/reports/precheck/data/gate-agentdojo`):

```bash
uv run python tools/precheck/l1_scan.py --source gate-agentdojo --part head --corpus-id gate-agentdojo --jobs 2 --emit-fp --git ~/.agentprov/staging/10c/gate/gate.git
uv run python tools/precheck/l2_sample.py select --units W/l1-units-head.jsonl --source gate-agentdojo --part head --corpus-id gate-agentdojo --out D/l2-sample-head.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j2 --source gate-agentdojo --part head --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j1 --source gate-agentdojo --part head --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-head-j2.partial --out D/l2-head.json --sample D/l2-sample-head.json --l1-units W/l1-units-head.jsonl --compare-with W/l2-head-j1.partial --jobs 2
```

Examiner scripts (read-only, pinned blobs by id through `agentprov.ingest`; B = `~/.agentprov/staging/10c/gate/gate.git`, C = `925b99260beec53d94bd48b587b0bdc33614e3df`, S = `D/exam-scripts`):

```bash
GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file uv run python -I S/pop.py W/l1-units-head.jsonl B C W/exam/pop.json   # H3, H5-H11, blocks, null_final, CC-07, CC-10
python3 -I S/os1.py W/l1-units-head.jsonl D/os1-population.json                                                    # H1, H2 (126 targets)
python3 -I S/os2.py W/l1-units-head.jsonl D/l2-sample-head.json D/l2-head.json D/os2-sample.json                   # OS-2 raw vs AER
GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file uv run python -I S/localdeny.py W/l1-units-head.jsonl B C              # PC-04 (0/215)
GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file uv run python -I S/sampledeny.py W/l1-units-head.jsonl D/l2-sample-head.json B C   # 68 denials -> 68 decisions
grep -c gate-agentdojo src/agentprov/adapters/agentdojo/artefacts.toml                                             # PC-05: 0
```

Follow-ups (heavy, not run):

1. A full scratch import tests H4 (which origin dedup keeps; 217 unresolved) and gives the full-population decision count (1,101 expected). It also gives the PC-04 tool-execution count: `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-gate-full -- uv run agentprov import gate-agentdojo --input ~/.agentprov/staging/10c/gate/gate-925b99260beec53d94bd48b587b0bdc33614e3df --verify-against-pin --corpus ~/.agentprov/migration-work/precheck/gate-agentdojo/full-scratch`
