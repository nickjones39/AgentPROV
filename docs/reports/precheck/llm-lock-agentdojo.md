# Pre-check dossier: `llm-lock-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `llm-lock-agentdojo` (GPL-3.0, own corpus, D-94; logs embed AgentDojo benchmark text, MIT) |
| Parts | `llm-lock-agentdojo · head` (1 part) |
| Family / profile | `agentdojo` / `llm-lock-agentdojo@1` (dialect `agentdojo.tracelogger`, variant `v1.k14`, semantics `agentdojo.suites@2`, identity table `tables/llmlock_defence_arms.toml`) |
| Pin | git `Wakeful-Cloud/llm-lock` @ `7bb9915b` (2025-12-15, the only commit), tree 70,075 blobs |
| Code commit | `d97d3a57` (L1 and L2, batch `wave3`, all six steps rc 0, tracked_changes false) |
| Kind | wave 3, first examination (not in FA or E2); no stored corpus |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (L1, L2 batch), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), examiner (this dossier); adversarial verifier (2026-10-21, all 8 confirmed, 0 refuted) |
| Data | [`data/llm-lock-agentdojo/`](data/llm-lock-agentdojo/): `research.json`, `l1-head.json`, `l1-10-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `findings.json`, `os1-population.json`, `os2-sample.json`, `detectors.json`, `l1-06-followup.json`, `verify-align.json`, `exam-scripts/` |

- Code identity, part `head` ([`code-head.json`](data/llm-lock-agentdojo/code-head.json)): commit `d97d3a57` (tracked_changes false); engine code aer `856b7a09e0cf`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `agentdojo.tracelogger@0.1.0` `03d8bc6d30df`; profile sha256 `3a35e8f40ca4`, rules agentdojo 2 / aer 1; lockfile `b0455f1058c8`, limits `5d6dbb210259`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Repository | https://github.com/Wakeful-Cloud/llm-lock @ `7bb9915b` (CS562 final project, UIUC; 0 issues, 0 tags) | the data; nine `data/agentdojo/<arm>/results.json` (author `compute-results`) = outcome reference |
| Paper / data record | none (arXiv, Zenodo, HF: 0 hits) | n/a |
| Harness | AgentDojo 0.1.35, benchmark v1.2.2 (logged in 53,307/53,307); dependency `Wakeful-Cloud/agentdojo@6ebf27e7` = upstream + 2 crash fixes ([PR #136](https://github.com/ethz-spylab/agentdojo/pull/136)) | producer and scorer |
| Sampling | temperature never sent at 0.1.35 ([PR #141](https://github.com/ethz-spylab/agentdojo/pull/141)) | server-default sampling |
| Upstream checker issues | ethz-spylab/agentdojo [#181](https://github.com/ethz-spylab/agentdojo/issues/181), [#161](https://github.com/ethz-spylab/agentdojo/issues/161) | CC-07 (section 7) |

Data-versus-documentation notes (checked against the data):

- Every `results.json` cell reproduces from the raw booleans (18,333 attacked cells, 873 benign, 36 injection-task cells; 0 differ). The author's ASR includes DoS logs and the author's "UuA" is `utility and not security`; neither is AgentDojo's definition (prereg §4).
- The code at the pin is not the producing code for four arms: the three redacting arms (the profile's note) and the embedding arm, whose pinned `detect` returns `is_benign` as the flag, while every logged abort follows p_mal > 0.5 (PC-04).
- `scripts/run.sh` launches both hybrid arms with the qualifire Sentinel model; the `hybrid/protectai` label rests on the directory name (PC-04).
- `pipeline_name` = `transformer` in 585 logs, all in transformer/qualifire banking (PC-06). The `none` README's "half-complete attacks" are absent (0 extra attack labels).
- 2,635 logs predate the fork's crash fixes (before 2025-11-21 00:57, naive clock).
- Model not recorded (D-92). PR #136 (same author) names "Ollama + Llama 4": a D-92 review item for the orchestrator, not a mapping change.

## 3. Expectations

Pre-registration: [`prereg/llm-lock-agentdojo.md`](prereg/llm-lock-agentdojo.md), committed in `fd75f8a3` (2026-10-14), before any check of this corpus. Amendments 2 and 4 apply (stratum key `model_dir × attack_dir × suite` = 288 strata, 300 units); amendment 1 does not (no stored corpus).

| H | Result | Note |
|---|---|---|
| H1 | supported | 53,307; 5,923 per arm; 905/677/887/3,454 per suite; 97 benign, 35 pre-pass, 949 per attack, 97 dos |
| H2 | supported | 288 strata, identical label sets in 9 arms; 7 attack types + none; 0 byte-identical |
| H3 | supported | 0 of 18,333 + 873 + 36 cells differ; security true 3,205, utility true 6,371, both true on attacked 299 |
| H4 | supported | every §5 count exact (section 4, PC-07), incl. aborts 1,281/1,694/4,278/4,252, unrecorded 1,341, 13,857 redactions in 5,376 logs |
| H5 | supported | sentinel only in the 3 redacting arms; tool-ending logs only in the 4 aborting arms |
| H6 | supported | 585 = transformer/qualifire banking {direct, ignore_previous, injecagent, system_message} × 144 + 9 pre-pass (banking now measured) |
| H7 | refuted (opposite pattern) | aborts at p_mal > 0.5: 1,281/1,281; non-aborted checks ≤ 0.5: 17,536/17,536 → pinned code is not the producing code (PC-04) |
| H8 | supported | ≥ 0.5 count = redactions in 4,944/4,944 (protectai) and 4,882/4,882 (qualifire); hybrid/qualifire (outside H8) shows the inverse (PC-03) |
| H9 | supported | detector keys in 35,928 files, 7 detector arms only; 0 in none and data-delimiter |
| H10 | supported | 53,307 naive, 0 parse failures, 0 zoned, 2025-11-18 07:05:17 .. 2025-12-15 06:06:22; 2,635 pre-fix |
| H11 | refuted as worded | 0 anchored key shapes (the census pair is 1 unanchored `sk-` match); 57 credential-assignment files and 10 account-path files, all model-generated (PC-05) |
| H12 | supported | travel non-DoS security 0/840 in all 9 arms; benign 0/20 except hybrid/qualifire 1/20 |
| H13 | supported | post-stratified ASR gaps −2.2 .. +6.4 pp; benign n < 20 per arm (no verdict) |
| H14 | supported | 679 groups / 2,607 units = 4.89 % (CC-01 definition); cross-corpus 0 |
| H15 | supported | 0 adapter_defect, 0 degenerate, identity_unresolved 300/300, 0 failing checks, j1 = j2 |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: staged bare clone at `7bb9915b` (`--git`, lazy fetch off), `l1_scan` at `d97d3a57`, 65 s. Exam scripts re-read every log by blob id (sha256 = L1 row).

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 70,075 walked = 53,307 selected + 30 context + 16,715 not selected + 23 absent_blob (notebook outputs missing from the partial clone, not selectable; PC-08). Units 53,307 = registry = census | as expected |
| L1-02 parse | strict ok 53,307/53,307; auxiliary (9 results.json) 9/9 | as expected |
| L1-03 encodings | escaped newline 22,823 files, escaped unicode 10,506, escaped quote 758, JSON-in-string 36, CR 6, zero-width 3; 0 bidi, tag, C1, U+FFFD | expected-known (AgentDojo escape residues) |
| L1-04 duplicates | byte-identical 0; trajectory-identical 679 groups / 2,607 units (4.89 %; largest 229 = embedding workspace UT28, model's first call identical across injection tasks); cross-part / cross-corpus 0 (`_cross/l1-xdup.json`) | H14 |
| L1-05 arms | 288 strata = 9 arms × 8 attack dirs × 4 suites, full factorial; 0 missing, 0 extra cells | H1, H2 |
| L1-06 secrets/paths | logs: credential-assignment 57 files, 0 anchored key shapes; account paths generic 7 files, named 3 (2 names). All in assistant turns; names = generic, the benchmark persona and 1 unidentified 8-char name; 0 operator; L1-10: 21 non-JSON context files, 0 hits | PC-05 (CC-03) |
| L1-07 timestamps | `/evaluation_timestamp` 53,307, all naive, range as pre-registered; tool-arg dates are benchmark calendar content (41 non-monotone units, not a run clock) | H10 |
| L1-08 degenerate | 0 empty, 0 error; trailing_calls 1,697 logs (1,699 calls); null_final 198 (empty-text finals; content None 0) | PC-08 (CC-08) |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`l2-sample-head.json`](data/llm-lock-agentdojo/l2-sample-head.json) (sha256 `47bf350ca31b…`): 300 of 53,307, 288 strata (1-2 per stratum; data-delimiter 44, others 32, by the sorted-order remainder rule), seed 20261011 |
| Import | j2 and j1 scratch corpora at `d97d3a57`: 300/300 mapped, status ok_with_issues 300 (info codes only), 0 degenerate, 0 adapter_defect; join 300 labels → 300 executions |
| Validation | tiers aer, sem, prov, linkage: 300/300 pass, 300 reproduced, linkage 300/300; SHACL skipped (not implemented) |
| Recompute | `--dry-run`: 300 identical, 0 unexplained |
| Verify chain | 0 failures (working-tree partial); no withholding policy |
| Determinism | j2 vs j1: 1,237/1,237 files, 0 differ, index identical |
| A2 / register | accounting_unverifiable 300, earlier_attempts_unobservable 300, identity_unresolved 300, unknown_top_level_key 194, unexecuted_tool_call 10, detector_abort_output_unrecorded 7 (= the trial's codes) |
| A3 PROV | 146,043 statements / 243,184 relation arguments, 0 dangling or invented; 10 unexecuted call parts represented; 1,049 tool executions with call |
| Evidence classes | `_unverified` twin statements 50,824 (inference I 41,339, assessment I 6,032, inference none 3,453), mixed twin + native 6,543, native-only 0; core D 1,456 (verifier: confirm these are engine rules, as in the other AgentDojo-format parts) |
| Identity | defence per table for all 9 dirs (data-delimiter → spotlighting_with_delimiting); model not recorded for all 300 (incl. 5 `transformer` pipeline logs); attack and suite 0 mismatches |
| Judgements | raw vs mapped: 0 of 72 arm × attack cells differ (security and benign utility) |
| Redaction | 908 files, 1 execution with a generic, model-generated account path in AER (4 pointers) and PROV `apv:args` (1); 0 operator (CC-03) |
| Withholding | not applicable (no policy; no withhold-class hit) |

## 6. Outcome comparison

Level 1 (population, raw booleans) vs the author's `results.json`: every arm reproduces exactly; the table gives the headline metrics (Wilson 95 %). ASR incl. dos is the author's metric (5,791 per arm).

| Arm | Benign utility | Inj.-task util. | ASR incl. dos | ASR excl. dos | Author UuA | Ref. | Gap | Verdict |
|---|---|---|---|---|---|---|---|---|
| none | 19/97 19.59 [12.91, 28.58] | 16/35 | 440 7.60 [6.94, 8.31] | 357 6.27 | 664 | = | 0 | match |
| data-delimiter | 16/97 16.49 | 18/35 | 405 6.99 [6.36, 7.68] | 324 5.69 | 637 | = | 0 | match |
| embedding | 13/97 13.40 | 12/35 | 256 4.42 [3.92, 4.98] | 173 3.04 | 650 | = | 0 | match |
| llm | 13/97 13.40 | 9/35 | 129 2.23 [1.88, 2.64] | 44 0.77 | 767 | = | 0 | match |
| multiclass | 11/97 11.34 | 7/35 | 127 2.19 [1.85, 2.60] | 41 0.72 | 734 | = | 0 | match |
| transformer/protectai | 16/97 16.49 | 10/35 | 165 2.85 [2.45, 3.31] | 74 1.30 | 581 | = | 0 | match |
| transformer/qualifire | 18/97 18.56 | 15/35 | 143 2.47 [2.10, 2.90] | 56 0.98 | 553 | = | 0 | match |
| hybrid/protectai | 13/97 13.40 | 13/35 | 202 3.49 [3.05, 3.99] | 114 2.00 | 670 | = | 0 | match (model identity: PC-04) |
| hybrid/qualifire | 14/97 14.43 | 15/35 | 150 2.59 [2.21, 3.03] | 63 1.11 | 568 | = | 0 | match |

Per arm × attack ASR (of 949) and per arm × suite cells also match (0 of 18,333). Travel: 0/840 non-DoS successes in every arm (degenerate in the author's own numbers; disclosed, never excluded).

CC-07 on this data (informational re-scores, not the logged metric; `os1-population.json`):

| Arm | Banking ASR logged (of 880) | #181 GOAL re-score | UT5 vacuous passes (of 56) |
|---|---|---|---|
| none | 21.25 | 17.16 (−36) | 22 |
| data-delimiter | 18.98 | 14.89 (−36) | 29 |
| embedding | 13.41 | 10.57 (−25) | 33 |
| llm | 3.18 | 1.93 (−11) | 53 |
| multiclass | 3.07 | 1.70 (−12) | 56 |
| transformer/protectai | 4.20 | 2.39 (−16) | 56 |
| transformer/qualifire | 3.41 | 1.70 (−15) | 52 |
| hybrid/protectai | 6.02 | 4.20 (−16) | 55 |
| hybrid/qualifire | 3.52 | 1.93 (−14) | 45 |

Level 2 (mapped AER of the sample; raw values of the same labels equal in 72/72 cells). Each arm has 28-40 attacked units, so the gap rule applies to ASR; benign n is 1-4 per arm (no verdict). The raw sample over-represents dos (4 of 28 vs 97 of 5,791 per arm, dos ASR ≈ 88 %), so the post-stratified rate (population attack weights) is the comparison (R6).

| Arm | n | Sample ASR (Wilson 95 %) | Post-strat. | Pop. | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|
| none | 28 | 25.00 [12.68, 43.36] | 13.97 | 7.60 | +6.37 | within 15 pp; raw 5.1 pp outside Wilson, explained by dos weight (R6) |
| data-delimiter | 40 | 22.50 [12.32, 37.50] | 7.61 | 6.99 | +0.62 | ok; raw 5.3 pp outside Wilson (R6) |
| embedding | 28 | 21.43 [10.21, 39.54] | 9.87 | 4.42 | +5.45 | ok; raw 5.8 pp outside Wilson (R6) |
| llm | 28 | 14.29 [5.70, 31.49] | 1.68 | 2.23 | −0.55 | ok |
| multiclass | 28 | 14.29 [5.70, 31.49] | 1.68 | 2.19 | −0.51 | ok |
| transformer/protectai | 28 | 14.29 [5.70, 31.49] | 1.68 | 2.85 | −1.17 | ok |
| transformer/qualifire | 28 | 10.71 [3.71, 27.20] | 1.26 | 2.47 | −1.21 | ok |
| hybrid/protectai | 28 | 10.71 [3.71, 27.20] | 1.26 | 3.49 | −2.23 | ok |
| hybrid/qualifire | 28 | 10.71 [3.71, 27.20] | 1.26 | 2.59 | −1.33 | ok |

## 7. Findings

| Id | Title | Class | Sev. | Verdict |
|---|---|---|---|---|
| PC-llm-lock-agentdojo-01 | [CC-07, #181] banking IT0/1/3 successes without the GOAL datum: 181 of 327 (precedence-only 178), all 9 arms | expected-known (R2, CC-07; scope gap CC-09) | S3 | confirmed |
| PC-llm-lock-agentdojo-02 | [CC-07, #161] banking UT5 utility true 504/504; 401 without an executed Spotify payment (5 benign) | expected-known (R2, CC-07) | S3 | confirmed |
| PC-llm-lock-agentdojo-03 | hybrid/qualifire logs the benign probability as `secondary_classification_malicious_probability` (= 1 - transformer/qualifire on 3,379/3,379 identical outputs; decisions follow s < 0.5 in 5,923/5,923 logs); decisions correct, the arm still blocks payloads (1,161 vs 2,521 payload-reaching logs in none) | source-defect (R1; no outcome bias) | S3 | confirmed |
| PC-llm-lock-agentdojo-04 | H7 refuted (opposite pattern): pinned embedding `detect` (and the abort-only `query`) did not produce the logs; run.sh names the Sentinel for both hybrid arms, but hybrid/protectai's secondary values equal transformer/protectai on 2,643/2,643 identical outputs (label verified by data) | documentation-mismatch (R3) | S3 | confirmed |
| PC-llm-lock-agentdojo-05 | [CC-03] model-generated account-path (10 logs) and credential-assignment (57 logs) shapes; 0 operator; prereg/profile counts differ | expected-known (CC-12c / CC-03) + R4 note | S3 | confirmed |
| PC-llm-lock-agentdojo-06 | profile says pipeline.name constant `local` (585 `transformer`); profile repeats the half-complete-attacks claim (0 logs); registry cites the draft census | documentation-mismatch (R4) | S3 | confirmed |
| PC-llm-lock-agentdojo-07 | [CC-09] reference: no artefacts.toml scope; all quirk counts verified | documentation-mismatch (CC-09) | S3 | confirmed |
| PC-llm-lock-agentdojo-08 | [CC-08] L1 null_final 198 vs product trigger 0 (content None); 23 absent_blob notebook outputs | analysis-artefact (R5) | S3 | confirmed |

No mapping defect; no security finding (PC-05: no operator path, no provider-key shape, no real account; CC-11 trigger not met). CC-10 (#168 slack IT5) not quantified here: follow-up 4. Details, evidence and reproduction per finding: [`findings.json`](data/llm-lock-agentdojo/findings.json) (CC-06 format).

Proposed `artefacts.toml` entries (text only; route to the AgentDojo family owner):

```toml
# PC-01 / PC-02: extend agentdojo.art.validity_defects (scope += "llm-lock-agentdojo")
expected += [
  { snapshot = "llm-lock-agentdojo:head", count = 181, unit = "executions", basis = "pre-check PC-llm-lock-agentdojo-01: banking IT0/1/3 security true without the GOAL datum in an executed attacker-bound transfer, 9 arms (precedence-only fix 178)", status = "proposed" },
  { snapshot = "llm-lock-agentdojo:head", count = 401, unit = "executions", basis = "pre-check PC-llm-lock-agentdojo-02: banking user_task_5 utility true without an executed payment to the Spotify IBAN (#161); 396 attacked, 5 benign", status = "proposed" },
]
# PC-03: new entry
# [[artefact]] id = "agentdojo.art.llmlock_hybrid_qualifire_prob_inverted"; scope llm-lock-agentdojo, model_dir hybrid/qualifire-*;
#   expected { snapshot = "llm-lock-agentdojo:head", count = 3553, unit = "logs", basis = "every logged secondary value (7,005) is 1 - malicious probability; decisions consistent in 5,923/5,923 logs (verifier, vfy_align.py)", status = "proposed" }; no outcome effect
# PC-07 (CC-09): scope += llm-lock-agentdojo on benign_security_constant 1188, injection_task_as_user 315, dos_polarity 873,
#   max_iters_pending 1697 logs / 1699 calls, naive_timestamp 53307, defence_benign_intervention (aborts in benign logs
#   llm 96, multiclass 92, embedding 33, hybrid/protectai 29; redacting benign logs transformer/protectai 53, hybrid/qualifire 19,
#   transformer/qualifire 8), payload_not_reaching_agent, banking_ut15_confound (scope only)
```

Items for AGENTS.md section 12:

- PC-01/02 (CC-07): llm-lock banking ASR is inflated by #181 in every arm (181 of 327 IT0/1/3 successes). In the detector arms almost every banking UT5 pass is vacuous (#161; multiclass and transformer/protectai 56/56).
- PC-04: `hybrid/protectai` ran the protectai DeBERTa classifier (secondary values equal transformer/protectai on 2,643/2,643 identical outputs, 0 equal transformer/qualifire), although `run.sh` at the pin names the qualifire Sentinel. The pinned code and `run.sh` are not what produced the logs.

## 8. Recommendations and readiness

1. Route the CC-07 rows (181, 401), the PC-03 entry and the CC-09 scope widening (PC-07 counts) to the AgentDojo family owner.
2. Profile owner: reword the identity and half-complete-attack comments, correct the secret and account-path counts (PC-05, PC-06), and point the registry evidence at the sealed census.
3. Disclose in the datasheet: travel is degenerate (0/840 non-DoS success in every arm, author's own numbers; never excluded), the author's ASR includes DoS, #181/#161 re-scores, PC-03 and PC-04.
4. Done by the verifier: PC-03 per-check alignment (5,923/5,923) and PC-04 hybrid identity (protectai, 2,643/2,643). Identity-table owner: cite this in the hybrid/protectai `basis`.
5. No exclusion of any data.

**Readiness: `ready-with-caveats`.** The import is exact and deterministic: 300/300 mapped, validation 300/300, recompute 0 unexplained, j1 = j2 (1,237 files), raw = mapped in 72/72 cells, and the population equals `results.json` in all 19,242 cells. The caveats are disclosure items (PC-01..05) and doc fixes (PC-06). None blocks the round. PC-07 and PC-08 are not counted. Verifier (2026-10-21): all 8 findings confirmed by re-running pop.py, det.py, os2.py (identical output) and a new alignment script; PC-03 widened to every logged secondary value, PC-04's open identity question settled in favour of the directory label; readiness unchanged.

## 9. Reproduction

Batch (wave 3; `tools/precheck/plans/wave3.toml`):

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave3 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave3.toml
```

Examiner scripts (read-only; S = `docs/reports/precheck/data/llm-lock-agentdojo/exam-scripts`, W = `~/.agentprov/migration-work/precheck/llm-lock-agentdojo`, B = `~/.agentprov/staging/10c/llm-lock/llm-lock.git 7bb9915b57e087536b6bdeae0066adb0d8999958`):

```bash
uv run python -I S/pop.py  W/l1-units-head.jsonl B W/exam/pop.json   # H1-H12, results.json cells, quirks, CC-07 (≈ 5 min)
uv run python -I S/det.py  W/l1-units-head.jsonl B W/exam/det.json   # PC-03/PC-04 payload reach, benign interventions, unrecorded aborts
uv run python -I S/acct.py W/l1-units-head.jsonl B W/exam/acct.json  # PC-05 roles/classes/digests
uv run python -I S/vfy_align.py W/l1-units-head.jsonl B W/exam/verify/align.json  # verifier: PC-03 alignment, PC-04 identity (-> D/verify-align.json)
python3 -I S/os2.py D/l2-head.json W/exam/sample_raw.json W/exam/pop.json D/os2-sample.json   # section 6 L2 table
GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file git -C <bare> show "7bb9915b…:agentdojo/embedding_defense.py" | grep -n is_benign   # PC-04
grep -c llm-lock src/agentprov/adapters/agentdojo/artefacts.toml   # PC-07: 0
```

Follow-ups (not run):

| # | What | Command | When |
|---|---|---|---|
| 1 | Route CC-07/CC-09/PC-03 rows to the family owner; PC-05/PC-06 to the profile owner | none | before the round |
| 2 | PC-03 verification: per-check alignment (done by the verifier: 5,923/5,923 consistent) | `exam-scripts/vfy_align.py` (≈ 25 s) | done |
| 3 | PC-04 hybrid model identity (done by the verifier: protectai 2,643/2,643 text pairs) | same | done |
| 4 | CC-10 (#168) count for slack IT5 successes on attempted/denied membership calls | extend `pop.py` (slack attacked, IT5) | with the CC-10 sweep |
