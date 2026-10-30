# Pre-check dossier: `linyxus-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `linyxus-agentdojo` (MIT, upstream AgentDojo LICENSE unchanged; no separate data record) |
| Parts | `linyxus-agentdojo · head` (1 part) |
| Family / profile | `agentdojo` / `linyxus-agentdojo@1` (dialect `agentdojo.tracelogger`, variants `v1.k14`, `v1.k14.incomplete`; identity `tables/linyxus_pipeline_dirs.toml`; semantics `agentdojo.suites@2`) |
| Pin | git `Linyxus/agentdojo` branch `lacuna-exp` @ `698d7ff2` (2026-05-24), 17,656 blobs |
| Code commit | `d97d3a57` (L1 and L2, batch `wave3`, steps l1, l1_10, sample, import_j2, import_j1, check all rc 0; tracked_changes false) |
| Kind | wave 3, first examination (not in FA or E2); no stored corpus |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (batch), 2026-10-21 (examination) |
| Agents | researcher + fact-checker (prereg), batch runner, examiner (this dossier), adversarial verifier (2026-10-21: 10/10 confirmed, PC-03 pooled figure corrected, PC-09 addendum) |
| Data | [`data/linyxus-agentdojo/`](data/linyxus-agentdojo/): `research.json`, `l1-head.json`, `l1-10-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `findings.json`, `os1-population.json`, `pop-population.json`, `gaps.json`, `misc.json`, `os2-sample.json`, `exam-scripts/` |

- Code identity, part `head` ([`code-head.json`](data/linyxus-agentdojo/code-head.json)): commit `d97d3a57` (tracked_changes false); engine code aer `856b7a09e0cf`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `agentdojo.tracelogger@0.1.0` `03d8bc6d30df`; profile sha256 `9901b7d36424`, rules agentdojo 2 / aer 1; lockfile `b0455f1058c8`, limits `5d6dbb210259`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Repository | https://github.com/Linyxus/agentdojo @ `698d7ff2` (fork of ethz-spylab/agentdojo; branches main, tacit-exp `4bd1de08` = subset, lacuna-exp = pin) | the data; only release (Zenodo/HF 0) |
| TACIT paper | https://arxiv.org/abs/2603.00991v2 (App. E.2 Table 4; v1 has no AgentDojo results) | reference for 8 TACIT cells |
| LACUNA paper | https://arxiv.org/abs/2605.28617v1 (Sec. 7.4 Table 3) | reference for 8 LACUNA cells (TACIT rows copied) |
| Benchmark | AgentDojo v1.2.2 / package 0.1.35 (logs), `important_instructions` only; upstream issues #181, #161, #168, #214 | checker defects (CC-07, CC-10) |

Data-versus-paper notes (checked against the data): TACIT Table 4 reproduces 8/8 cells exactly, from mixed roots (PC-04). LACUNA Table 3 reproduces 5 of the 7 backed cells; gemini travel and o4 workspace do not, and gemini workspace has no logs (PC-01, PC-02). Each paper cell uses one run root, but the corpus maps all roots, LACUNA included, to defence `tacit` (PC-03). The profile names no paper (PC-05). Environment calls exist only in `backend_tool_traces` (PC-06).

## 3. Expectations

Pre-registration: [`prereg/linyxus-agentdojo.md`](prereg/linyxus-agentdojo.md), committed in `fd75f8a3` before any check. Amendments 2-5 apply. Amendment 2.4 fixes the stratum key to the family hook (27 strata, 127 units), not the prereg's 52 strata / 252 units (with attack). Classes follow R1-R6 and CC-01..CC-11 ([`cross-cutting.md`](cross-cutting.md)).

| H | Result | Note |
|---|---|---|
| H1 | supported | 9,068 selected; 8,383 txt excluded, each with its log; per-root/per-cell counts as prereg §3 |
| H2 | supported | 9,068/9,068 strict ok |
| H3 | supported | the 3 empty logs are the listed pre-pass IT0 logs; 11 txt-without-key logs, all among the 15 incomplete |
| H4 | supported per cell; second clause refuted | 8/8 exact, but workspace comes from runs-2 and the rest from runs-4 (PC-04) |
| H5 | refuted | gemini travel 57 vs 89, o4 workspace 261 vs 311 (PC-01) |
| H6 | supported | 0 gemini LACUNA workspace logs (PC-02) |
| H7 | supported | attacked security true 148 (= 557 − 409); matching-root defended cells ≤ 2 |
| H8 | supported (finding) | lacuna-runs → `tacit` (PC-03) |
| H9 | supported | runs-* April 7,367 + deepseek May 1; lacuna maxima 2026-05-21 23:39 / 05-23 18:52 (naive) before the adding commits; `model` key exactly 1,701 |
| H10 | supported | 0 byte-identical; 0 trajectory groups across repetitions; 0 cross-corpus (`_cross/l1-xdup.json`) |
| H11 | supported | 0 keys, 0 account paths; 1 false-positive hit (PC-09) |
| H12 | supported | backend traces produce 0 activities (PC-06) |
| H13 | supported | 127/127 ok, 0 failing, 0 adapter_defect, recompute 0, determinism 519/519 |
| H14 | supported | `pipeline_name_mismatch` 17/17 sampled runs-0 logs, 0 elsewhere; identity from the directory |
| H15 | not tested per paper cell | the sample pools roots, n ≤ 10 per stratum; pooled arms in §6 |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: staged bare clone `~/.agentprov/staging/10c/linyxus/agentdojo.git` at `698d7ff2` (`--git`), `l1_scan` at `d97d3a57`, 16 s.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 17,656 walked = 9,068 selected + 8,383 excluded (`select.not_execution_artefact`) + 201 not selected + 4 context; units 9,068 = registry = census | as expected |
| L1-02 parse | 9,068/9,068 ok; 0 duplicate keys, non-finite, big ints, surrogates, BOM, trailing, invalid UTF-8, truncation | as expected |
| L1-03 encodings | escaped newline 7,859 files (mostly `eval_scala` code args: Scala source, legitimate); escaped quote 205; variation selector 123 (benchmark emoji); ANSI/ESC 33 files / 35 strings at tool-result content (Scala runtime diagnostics); C0 7; escaped `\uXXXX` 6 files / 11 strings (#214 candidates); zero-width 4; JSON-in-string 1; 0 bidi, tag, U+FFFD, mojibake | as expected; no finding |
| L1-04 duplicates | byte-identical 0. Trajectory-identical (CC-01) 357 groups / 1,005 of 9,065 units, all within one cell and differing only in the injection task (the payload never reached the agent's view; largest 14 = one runs-2 workspace UT across 14 ITs); 0 across repetitions, 0 cross-corpus | H10 holds |
| L1-05 arms | 27 strata; attacked 8,654, pre-pass 414; every prereg §3 cell count equal; missing vs paper: gemini LACUNA workspace (PC-02); extra: native arms 306, nano 775, claude 528, gpt-5.4 1, deepseek 1, extra repetitions | as expected |
| L1-06 secrets/paths | 1 `generic-credential-assignment` at `/tacit_secure_output`, which is a symbol-only false positive (PC-09); 0 provider keys, 0 account paths; L1-10: 4 context files, 0 hits | H11 holds |
| L1-07 timestamps | `/evaluation_timestamp` 9,068/9,068 naive, 0 parse failures, 2026-04-13..2026-05-23; the other pointers (backend args, secure output) carry benchmark calendar dates 2024-2026 (content) | as expected |
| L1-08 degenerate | zero messages 3, incomplete 15, null_final 344 (runs 247, lacuna 97), trailing calls 42 logs, `error` null 9,068 | census silent_rerun 355 vs 344: different definitions, follow-up |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`l2-sample-head.json`](data/linyxus-agentdojo/l2-sample-head.json) (sha256 `ca1a0e37e4f6…`): 127 of 9,068, 27 strata, seed 20261011; by root runs-4 50, lacuna-1 21, runs-0 17, runs-3 17, lacuna-0 14, runs-2 8 |
| Import | `l2-head-j2.partial`, `-j1.partial`: 127 mapped (agent_execution 126, outcome_only 1), ok 103, ok_with_issues 24, 0 degenerate, 0 `adapter_defect`; join 127 → 127 |
| Validation | aer, sem, prov, linkage: 127/127 pass, 127 reproduced, linkage 100 %; SHACL skipped (not implemented) |
| Recompute | `--dry-run`: 127 identical, 0 unexplained |
| Verify chain | only `checksums.absent` (working tree) |
| Determinism | j2 vs j1: 519/519 files, 0 differ, index identical |
| A2 codes | accounting_unverifiable 125, earlier_attempts_unobservable 126, unknown_top_level_key 126, system_prompt_unrecognised 116, pipeline_name_mismatch 17, retry_passes_inferred 4, unexecuted_tool_call 4, incomplete_run 1, no_execution_observed 1, no_outcome_recorded 1. All are census codes |
| A3 | 0 dangling/missing/invented over 67,456 statements / 111,166 relation arguments; 973 messages with `generated_by`, 549 model calls with input; 4 unexecuted calls represented |
| Tool executions | 424 AER `tool_execution` = 424 raw tool results (eval_scala 408 + native 16, the same names); 617 backend-trace calls → 0 activities (PC-06) |
| Evidence classes | core D 626 / O 3,680; inference I 23,488; assessment I 9,097 / O 254; top O 22,044. Unverified split (CC-08 statement level): twin inference I 19,802, assessment I 2,238, inference none 1,476; native 0; mixed inference I 3,030 |
| Identity | models resolved 100 % (OpenRouter route from the dir); defence `tacit` for every `-tacit` dir including lacuna-runs (PC-03), `none` for the 2 native dirs; attack II / none; 0 unresolved, 0 mismatches |
| OS-2 | raw vs mapped outcomes of the sampled labels: 6/6 arms equal (`os2-sample.json`) |
| Redaction | 389 AER/SEM/PROV files, 0 hits |
| Withholding | not applicable (no policy; the only L1-06 hit is a false positive) |

## 6. Outcome comparison

Level 1 population: raw booleans, attacked complete logs (pre-pass and incomplete logs excluded, as the fork's scripts do). The "Source" column gives the root that reproduces the cell, and "merge" is the latest-wins merge. Gap rule: > 15 pp with n ≥ 20, or > 5 pp outside Wilson 95 %. Full rows are in [`os1-population.json`](data/linyxus-agentdojo/os1-population.json).

| Paper / model / suite | Source | n | Utility (Wilson 95 %) | Paper | Gap (pp) | Attacks k (paper) | Verdict |
|---|---|---|---|---|---|---|---|
| TACIT gemini banking | runs-4 = merge | 144 | 56.94 [48.78, 64.75] | 56.94 | 0 | 0 (0) | exact; #161 re-score 53.47 |
| TACIT gemini workspace | runs-2 | 560 | 50.54 [46.41, 54.66] | 50.54 | 0 | 0 (0) | exact (merge 290) |
| TACIT gemini slack | runs-4 = merge | 105 | 40.00 [31.14, 49.56] | 40.00 | 0 | 0 (0) | exact (runs-2: 39 attacks) |
| TACIT gemini travel | runs-4 = merge | 140 | 64.29 [56.06, 71.74] | 64.29 | 0 | 0 (0) | exact |
| TACIT o4 banking | runs-4 = merge | 144 | 59.03 [50.86, 66.72] | 59.03 | 0 | 0 (0) | exact; #161 re-score 56.25 |
| TACIT o4 workspace | runs-2 | 560 | 52.86 [48.72, 56.96] | 52.86 | 0 | 0 (0) | exact (runs-4/merge 312) |
| TACIT o4 slack | runs-4 = merge | 105 | 47.62 [38.32, 57.09] | 47.62 | 0 | 0 (0) | exact |
| TACIT o4 travel | runs-4 = merge | 140 | 68.57 [60.47, 75.68] | 68.57 | 0 | 1 (1) | exact |
| LACUNA gemini banking | lacuna-1 = merge | 144 | 63.19 [55.07, 70.63] | 63.19 | 0 | 0 (0) | exact; #161 re-score 57.64 |
| LACUNA gemini workspace | none | 0 | – | 56.25 | – | – (4) | unbacked (PC-02) |
| LACUNA gemini slack | lacuna-1 = merge | 105 | 42.86 [33.81, 52.41] | 42.86 | 0 | 2 (2) | exact |
| LACUNA gemini travel | lacuna-1 = merge | 140 | 40.71 [32.93, 48.99] | 63.57 | −22.86 | 1 (1) | **gap rule fires** (PC-01) |
| LACUNA o4 banking | lacuna-1 = merge | 144 | 65.97 [57.91, 73.21] | 65.97 | 0 | 0 (0) | exact; #161 re-score 61.81 |
| LACUNA o4 workspace | lacuna-0 = merge | 560 | 46.61 [42.51, 50.75] | 55.54 | −8.93 | 0 (0) | 4.79 pp outside Wilson; H5 refuted (PC-01) |
| LACUNA o4 slack | lacuna-1 = merge | 105 | 49.52 [40.15, 58.93] | 49.52 | 0 | 1 (1) | exact |
| LACUNA o4 travel | lacuna-1 = merge | 140 | 71.43 [63.45, 78.26] | 71.43 | 0 | 0 (0) | exact |

Gap investigation (gemini travel): raw = L1 = mapped. Each path has a single add in git history, so no other version exists. 44 of 140 logs have no agent tool call (vs 10 of 140 in TACIT runs-4), and the commit "Retry when agent message is empty" (`dfdaca9d`) comes after the data. The cause is undetermined, and the source's documentation does not match its data.

Level 2, mapped AER sample pooled by the `l2_check` arm key (model|defence|attack, attacked):

| Arm | n | Utility (Wilson 95 %) | ASR (Wilson 95 %) | Population utility / ASR | Verdict |
|---|---|---|---|---|---|
| claude-sonnet-4 / tacit | 20 | 65.0 [43.3, 81.9] | 0 [0, 16.1] | 71.63 / 0.61 | inside |
| gemini-2.5-pro / tacit | 33 | 39.4 [24.7, 56.3] | 3.0 [0.5, 15.3] | 50.05 / 2.37 | inside |
| gpt-5.4-nano / tacit | 20 | 30.0 [14.5, 51.9] | 0 [0, 16.1] | 48.41 / 1.52 | −18.4 pp on the pooled rate. R6: the post-stratified population (equal suite weight) is 45.73, inside the interval; raw = mapped |
| o4-mini-high / tacit | 38 | 57.9 [42.2, 72.1] | 0 [0, 9.2] | 51.73 / 0.33 | inside |
| gemini-2.5-pro / none | 4 | 100 | 25.0 | 73.61 / 32.64 | n < 20 |
| o4-mini-high / none | 5 | 20.0 | 0 | 68.75 / 2.78 | n < 20 |

CC-07 (population, banking attacked complete, 2,509 logs). #181: 33 IT0/1/3 successes. 0 lack the GOAL datum, the precedence-only fix flips 7, and 0 have no attacker-bound transfer. #161: 118 of the 162 UT5 utility-true logs have no executed Spotify transfer, which inflates the paper banking cells by 3.5 to 5.6 pp (table above). CC-10: 0 of the 15 slack IT5 successes are attempt-only.

## 7. Findings

| Id | Title | Class | Sev | CC | Verdict |
|---|---|---|---|---|---|
| PC-01 | LACUNA Table 3: 2 of 7 backed cells not reproduced (gemini travel −22.86 pp, o4 workspace −8.93 pp) | documentation-mismatch (R3) | S2 | – | confirmed |
| PC-02 | LACUNA gemini workspace reported, 0 logs released | documentation-mismatch (R3) | S2 | – | confirmed |
| PC-03 | Identity folds LACUNA and 5 TACIT roots into `tacit`. Unreported repetitions reach defended ASR 39/105 (runs-2 gemini slack, different prompt digest); pooled runs-family gemini-tacit slack 42/314 = 13.4 % attacked complete (verifier; the examiner's 57/330 = 17.3 % counted 15 pre-pass benign-constant trues) vs the paper's 0 % | documentation-mismatch (R4, raised to S2: it changes pooled outcome metrics) | S2 | – | confirmed |
| PC-04 | TACIT Table 4 exact from mixed roots (workspace runs-2, rest runs-4); root choice unstated; merge fails on workspace | documentation-mismatch (R3) | S3 | – | confirmed |
| PC-05 | Profile `paper = "none found"`; two papers exist | documentation-mismatch (R4) | S3 | – | confirmed |
| PC-06 | Environment calls only in `backend_tool_traces` (32,601 in 8,076 logs), not activities | expected-known (profile extra keys) | S2 disclosure | – | confirmed |
| PC-07 | #181 0/33 (precedence-only 7); #161 118/162 vacuous; CC-10 0/15 | expected-known (R2) | S3 | CC-07, CC-10 | confirmed |
| PC-08 | No artefacts.toml entry scopes linyxus; per-entry counts | documentation-mismatch | S3 | CC-09, CC-01 | confirmed |
| PC-09 | The L1-06 hit is a symbol-only value (false positive); L1-06 also misses key-named credential fields: 1 sandbox `update_password` argument at `/backend_tool_traces/*/args/password` (runs-3 banking, model-chosen, not a real secret) | analysis-artefact (R5) | S3 | – | confirmed |
| PC-10 | Prereg fact-check: "379 logs without txt" is really 685 (all of runs-0) | documentation-mismatch (R4, prereg) | S3 | – | confirmed |

Verifier notes: PC-01 paper values re-read from arXiv 2605.28617v1 Table 3 (89/140, 311/560); no root or denominator reproduces them (runs-4 TACIT gives 90 and 312, one higher, which proves nothing). PC-03 class `mapping-defect` was considered and rejected: the source itself names the lacuna dirs `-tacit`. PC-07 #161 (118/162) and the 33 #181 successes re-counted independently; the 0/7 GOAL/precedence split is the examiner's.

CC-02, CC-03, CC-11: not applicable (no AgentDyn suites; 0 account paths in logs or context files). CC-04, CC-05: not applicable.

Proposed `artefacts.toml` changes (text only, routed to the agentdojo family owner):

```toml
# PC-07 / PC-08 (CC-07, CC-09): scope.sources += "linyxus-agentdojo"; scope.profiles += "linyxus-agentdojo"; status "proposed",
#   basis "pre-check PC-linyxus-agentdojo-07/08, raw census of 9,068 logs at 698d7ff2":
#   validity_defects 118 (banking UT5 vacuous utility); #181 GOAL-datum 0, precedence-only 7
#   benign_security_constant 409; injection_task_as_user 414; incomplete_run 15; empty_log 3; max_iters_pending 42 logs;
#   silent_rerun 355 (census); naive_timestamp 9068; payload_not_reaching_agent: scope only, count from the round's full import
```

Items for AGENTS.md §12: the identity of the linyxus lacuna-runs and the missing run-root facet (PC-03); the LACUNA Table 3 cells the release cannot reproduce (PC-01/02); environment calls outside the PROV graph (PC-06).

## 8. Recommendations and readiness

1. PC-03: before the round, give lacuna-runs its own defence id or marker and record the run root as a configuration facet. This changes AER bytes, so it goes through a regen item and the family owner.
2. PC-05: update the profile's paper field and re-run the README generator if the field is listed.
3. Datasheet disclosures: PC-01, PC-02, PC-04 (root per cell), PC-06 and the PC-07 re-scored banking utility.
4. CC-09 scope widening with the PC-07/PC-08 counts.
5. No data is excluded, including the zero-ASR defended cells and the high-ASR repetitions.

**Readiness: `ready-with-caveats` (verifier: upheld).** There is no S0 or S1 finding; all 10 findings are confirmed by an independent tally (`exam-scripts/verify_v1.py`..`v4.py`, `verify-tally.json`). Level 2 is clean and deterministic, and identity resolves 100 %. The caveats are the S2 identity folding (PC-03), which should be resolved or disclosed before the round, and the S2 source documentation mismatches (PC-01, PC-02, PC-06), which are disclosures.

## 9. Reproduction

```bash
# repository root; W=~/.agentprov/migration-work/precheck/linyxus-agentdojo
uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave3.toml       # L1, L1-10, sample, imports, check (done)
uv run python -I docs/reports/precheck/data/linyxus-agentdojo/exam-scripts/pop.py $W/exam/pop.json      # OS-1, H3, H9, H12, CC-07
uv run python -I docs/reports/precheck/data/linyxus-agentdojo/exam-scripts/outcomes.py                  # os1-population.json
uv run python -I docs/reports/precheck/data/linyxus-agentdojo/exam-scripts/gaps.py $W/exam/gaps.json    # PC-01, PC-03
uv run python -I docs/reports/precheck/data/linyxus-agentdojo/exam-scripts/misc.py $W/exam/misc.json    # H9, H12 (L2), H14, CC-10, PC-09
uv run python -I docs/reports/precheck/data/linyxus-agentdojo/exam-scripts/secret_where.py              # PC-09
python3 -I docs/reports/precheck/data/linyxus-agentdojo/exam-scripts/os2.py                             # OS-2
uv run python -I docs/reports/precheck/data/linyxus-agentdojo/exam-scripts/pooled.py                    # pooled population
uv run python -I docs/reports/precheck/data/linyxus-agentdojo/exam-scripts/verify_v1.py docs/reports/precheck/data/linyxus-agentdojo/exam-scripts $W/exam/verify/v1.json   # verifier tally (v2: #161 + raw-byte L1-06; v3/v4: hit shape and pointer, no value)
GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file git --git-dir ~/.agentprov/staging/10c/linyxus/agentdojo.git log --format='%h %cI %s' 698d7ff2 -- lacuna-runs lacuna-runs-0 lacuna-runs-1
# follow-up (heavy, not run): full import through the queue, --cpu 2, into a scratch corpus, to count retry_passes_inferred and SEM injection_marker absent
```
