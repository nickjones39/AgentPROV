# Pre-check dossier: `ceferisbarov-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `ceferisbarov-agentdojo` (MIT LICENSE at the pin, identical to upstream's; no data licence) |
| Parts | `ceferisbarov-agentdojo · head` (1 part) |
| Family / profile | `agentdojo` / `ceferisbarov-agentdojo@1` (dialect `agentdojo.tracelogger`, variants `v1.k14` 18,403, `v1.k14.incomplete` 39; semantics `agentdojo.suites@2`) |
| Pin | git `ceferisbarov/agentdojo` @ `2273e1cd` (2026-02-11, = head of `main`); 55,302 files |
| Code commit | `d97d3a57` (L1 and L2, batch `wave3`, all six steps rc 0; tracked_changes false) |
| Kind | wave 3, first examination (not in FA or E2); no stored corpus |
| Date | 2026-10-14 (prereg), 2026-10-15 (L1, L2), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), examiner (this dossier); adversarial verifier 2026-10-21 (12/12 confirmed, 0 refuted) |
| Data | [`data/ceferisbarov-agentdojo/`](data/ceferisbarov-agentdojo/): `research.json`, `l1-head.json`, `l1-10-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `findings.json`, `exam-census.json`, `exam-extra.json`, `exam-h8.json`, `cc07` in `exam-census.json`, `cc10.json`, `exam-scripts/` |

- Code identity, part `head` ([`code-head.json`](data/ceferisbarov-agentdojo/code-head.json)): commit `d97d3a57` (tracked_changes false); engine code aer `856b7a09e0cf`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `agentdojo.tracelogger@0.1.0` `03d8bc6d30df`; profile sha256 `26567f5cca50`, rules agentdojo 2 / aer 1; lockfile `b0455f1058c8`, limits `5d6dbb210259`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Source repository | https://github.com/ceferisbarov/agentdojo @ `2273e1cd` (fork of ethz-spylab/agentdojo, merge base `5cea5891`) | the data (`reruns/`) |
| Paper | arXiv:2602.05066, *Bypassing AI Control Protocols via Agent-as-a-Proxy Attacks* (v1 2026-02-04, v2 2026-02-25; CC BY 4.0) | agent-level kept-trace counts (4.1, 5.4, 5.5) and monitor ASRs (Tables 2-6) |
| Paper code | https://github.com/dspl-lab/agent-as-a-proxy-attack (submodule = this fork at `2273e1cd`) | `bash_scripts/agentdojo.sh` writes both adapted and unadapted runs to `reruns/original` |
| Upstream issues | ethz-spylab/agentdojo #181, #161, #168 | checker defects (CC-07, CC-10) |

Data-versus-paper notes (checked against the data):

- The logs reproduce section 4.1 exactly: optim_str × gpt-4o × slack has 89 successes; the only user task with 0 successes is `user_task_20`, so the paper's 20 × 5 grid gives 89/100 (PC-07). The profile's `paper = "none found"` is wrong.
- Sections 5.5 (96/120) and 5.4 (161/220) do not reproduce from any released cell (PC-06).
- The arm directory `original` is not one goal variant: 601 gemini-2.5-pro banking/workspace logs ran the adapted goal (PC-01), consistent with the attack repository's script.
- 110 logs were rewritten by the last log commit `5cec9793` (PC-08); the pin's error policy and escaping postdate every log (PC-10).

## 3. Expectations

Pre-registration: [`prereg/ceferisbarov-agentdojo.md`](prereg/ceferisbarov-agentdojo.md), committed in `fd75f8a3` (2026-10-14), before any data check. Amendments 2-5 apply (README section 8); amendment 2.4 fixes the stratum key to `arm × pipeline_dir` (112 strata; the prereg's L2 note estimated 161 from arm × pipeline × suite). Classes follow R1-R6 and CC-01..CC-11 ([`cross-cutting.md`](cross-cutting.md)).

| H | Result | Note |
|---|---|---|
| H1 | supported | 17,426 + 1,016; 161 cells = 130 + 15 + 16; partial cells and counts as listed; 0 benign user-task logs |
| H2 | supported | 0 parse defects; 0 byte-identical within the part or across corpora |
| H3 | supported (tested items) | 1,016 / 1,016 / null-content finals 0 / 58 calls in 53 logs / 39 / 877 in 220 / 65 / 5; 17,387, 84,028 and 993 not re-derived. Separate: 614 empty-text finals (PC-05) |
| H4 | supported | the 5 empty logs are the only attacked logs of the five 1-attacked-log cells |
| H5 | refuted | 32/39 (82.1 %) in partial or pre-pass-only cells; 7 in full cells |
| H6 | supported | 742 at 0.1.34 = original × gpt-4o travel 58 + workspace 574, optim_str × gpt-4o slack 110 |
| H7 | supported | v1.2.1 in 18,442/18,442 |
| H8 | refuted | optim_str 2,264/2,264, k/1_ arms 0/12,644; **original 601/2,518** (PC-01) |
| H9a | supported | 89/105 = 84.76 % [76.67, 90.40]; 89/100 exact without `user_task_20` |
| H9b | refuted | 72/144 = 50.0 % vs 80.0 % (PC-06) |
| H9c | refuted | 218/498 = 43.78 % vs 73.2 % (PC-06) |
| H10 | supported | every family's gpt-4o slack arms are above Table 3 (min mistral 67.62, qwen 57.14, llama 65.71) |
| H11 | supported | 65/65 error, utility false, security true; all Llama-3.1-70B (0 OpenAI) |
| H12 | refuted | pre-pass sharing 119/679 = 17.5 %; 70 cross-arm attacked groups (PC-09) |
| H13 | refuted as worded | residue logs 70.1 % in `*_fixed` (< 80 %); attribution undetermined (PC-10) |
| H14 | refuted | 0 bidi/zero-width/tag/C1/U+FFFD in any injections value |
| H15 | refuted (count) | 8 files > 5, all model-generated assistant text; 0 account paths (PC-11) |
| H16 | refuted as worded | all present, naive, 2025-11-12..2026-01-30; 110 rewritten after their add (PC-08) |
| H17 | supported | 220 logs / 877 calls, all command-r-plus-08-2024 |
| H18 | supported | 21 models, 0 unresolved, command-r-plus spellings distinct, no provider field |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: staged bare clone at `2273e1cd` (`--git`, lazy fetch off), `l1_scan` at `d97d3a57`, 38.6 s; examiner re-read of all 18,442 blobs (sha1 + sha256 checked, 0 raw-vs-L1 outcome differences).

| Check | Result (denominator) | Expected | Verdict |
|---|---|---|---|
| L1-01 counts | walked 55,302: selected 18,442, excluded `select.owned_elsewhere` 36,679, context 4, not_selected 177; units 18,442 | 18,442 (registry, census) | match |
| L1-02 strict parse | ok 18,442/18,442 | 0 defects | match |
| L1-03 encodings | escaped_quote 6,490, escaped_newline 2,484, escaped_unicode 255; c0 128, esc 92, cr 11, variation selector 8, U+FFFD 3, ansi 1, zero-width 1, JSON-in-string 1 (artefacts) | GCG Unicode in injections (H14) | escape residues only in injections; other classes in messages (H14 refuted) |
| L1-04 duplicates | byte-identical 0; trajectory groups 141 / 635 units; cross-corpus 0 byte, 11 trajectory groups (8 corpora) | 0 / pre-pass repeats | PC-09, CC-01 |
| L1-05 arms | 61 arms × 21 pipeline dirs, 161 cells (130/15/16), 112 strata; suites banking 7,645, slack 8,575, travel 500, workspace 1,722 | as section 3 | match (H1) |
| L1-06 secrets / accounts | 9 strings, 8 files (model text); 0 account paths; L1-10: 4 context files, 0 hits | ≤ 5, 0 | PC-11 |
| L1-07 timestamps | `evaluation_timestamp` 18,442 naive, 2025-11-12..2026-01-30, 0 parse failures | H16 | PC-08 |
| L1-08 degenerate | zero_messages 5, incomplete 39, error_only 26, trailing_calls 53 (58 calls), null_final 614 (empty text blocks; content null 0), secret_like 8 | 5 / 39 / 0 / 53 | PC-05 |

CC-07 on the population (raw census, [`exam-census.json`](data/ceferisbarov-agentdojo/exam-census.json) `cc07`):

| Defect | Affected | Denominator | Logged rate | Re-scored |
|---|---:|---:|---|---|
| #181 banking IT0/1/3 without the GOAL datum | 331 (it0 24, it1 272, it3 35) | 1,567 IT0/1/3 successes; 7,109 banking attacked | 43.78 % [42.63, 44.93] | 39.12 % [37.99, 40.26] (precedence-only 39.18 %) |
| #161 banking UT5 utility pass without a Spotify payment | 65 | 438 UT5 passes (441 logs) | — | — |
| #168 (CC-10) slack IT5 success without an attempted goal call | 3 | 1,009 IT5 successes; 8,148 slack attacked | — | −0.04 pp |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`l2-sample-head.json`](data/ceferisbarov-agentdojo/l2-sample-head.json) (sha256 `135457fd2e6e`): 300 of 18,442, 112 strata, seed 20261011, not over maximum |
| Import | 2 scratch corpora (`l2-head-j2.partial`, `-j1.partial`) at `d97d3a57`; 300/300 mapped; ok 280, ok_with_issues 20; 0 degenerate, 0 `adapter_defect`; 300 labels → 300 executions 1:1 |
| Validation | aer, sem, prov, linkage: 300/300 pass, 300 reproduced, linkage 100 %; SHACL not implemented (skipped); regression n/a |
| Recompute | dry-run 300 identical, 0 unexplained |
| Verify chain | 0 failures; `checksums.absent` only (working tree); no sealed copy needed (no `[withhold]`) |
| Determinism | j2 vs j1: 1,211/1,211 files, 0 differ, index identical |
| A2 classes | `earlier_attempts_unobservable` 299, `accounting_unverifiable` 286, `incomplete_run` 16, `unexecuted_tool_call` 2, `no_execution_observed` 1, `no_outcome_recorded` 1, `outcome_imposed_by_runner` 1; completeness known_incomplete 16 / unverifiable 284 |
| A3 PROV issues | 0 dangling / missing / invented relations over 151,650 statements and 252,663 relation arguments; 2,541 messages with `generated_by`, 1,279 model calls with input; 2 unexecuted call parts represented |
| Evidence classes | AER: 0 records at D (O 4,863, I 4,291). PROV D only engine rules (`aprov.n_gap` 1,131, `n_capture_profile` 300, `a_label` 91). Twin / native / mixed (CC-08 split): twin inference:I 43,697 + inference:none 3,706 + assessment:I 7,297; mixed inference:I 7,961; native 0 |
| Judgements | AER vs raw: 0/600 differ; origins utility checker 282 / harness_default 1, security checker 249 / harness_default 34 |
| Identity | 21 models verbatim from the pipeline dir; defence `none`; attack `important_instructions` / `none`; 0 unresolved, 0 mismatches, 0 one-to-many; no provider field (H18); arm only in the origin path (R5) |
| Redaction | 908 AER/SEM/PROV files, 0 hits |
| Withholding | not applicable (no policy; no real secret, PC-11) |

## 6. Outcome comparison

Level 1 = raw booleans of every attacked complete log; security true = the paper's kept traces (no utility in the paper). Gap rule: > 15 pp on n ≥ 20, or > 5 pp outside Wilson 95 %.

| Arm (arm / model / suite) | Level | n | Rate (Wilson 95 %) | Paper | Gap (pp) | Verdict |
|---|---|---:|---|---|---:|---|
| optim_str / gpt-4o / slack | L1 | 105 | 84.76 (89) [76.67, 90.40] | 89.0 (89/100) | −4.24 | match; 89/100 without `user_task_20` |
| optim_str / gpt-4o / banking | L1 | 144 | 50.00 (72) [41.94, 58.06] | 80.0 (96/120) | −30.0 | flagged → PC-06 |
| same, paper grid (no UT15, IT8) | L1 | 120 | 51.67 (62) [42.81, 60.42] | 80.0 | −28.3 | flagged → PC-06 |
| same, #181 re-score (info) | L1 | 144 | 44.44 (64) | 80.0 | — | not the logged metric (PC-02) |
| optim_str / {gpt-4o-mini, Llama-3.1-70B} / {slack, banking} | L1 | 498 | 43.78 (218) [39.48, 48.16] | 73.2 (161/220) | −29.4 | flagged → PC-06 |
| same, without 28 imposed (info) | L1 | 470 | 40.43 (190) | 73.2 | — | info |
| mistral_k / qwen_k / llama_k gpt-4o slack (H10) | L1 | 105 each | min 67.62 / 57.14 / 65.71 | ≥ 50.0 / 17.5 / 54.6 | — | consistent (upper-bound check) |
| original / gemini-2.5-pro / banking, literal vs not (info) | L1 | 102 / 41 | 10.8 / 29.3 | — | — | PC-01 |
| all attacked | L1 | 17,407 | 44.53 [43.79, 45.27] | — | — | reference |
| all attacked | L2 | 250 | 44.40 [38.37, 50.60] | L1 44.53 | −0.13 | R6; no arm reaches n = 20 (largest optim_str 33 over 21 pipelines) |

Monitor ASRs (Tables 2-6) are not testable: the logs contain no monitor verdicts.

## 7. Findings

| Id | Title | Class | Sev | Verdict |
|---|---|---|---|---|
| PC-01 | `original` arm mixes adapted-goal runs: 601 gemini-2.5-pro banking/workspace logs carry the literal `{optim_str}` | source-defect (R1) | S2 | confirmed |
| PC-02 | [CC-07 #181] 331 of 1,567 banking IT0/1/3 successes without the GOAL datum | expected-known (CC-07) | S3 | confirmed |
| PC-03 | [CC-07 #161] 65 of 438 UT5 passes without a Spotify payment | expected-known (CC-07) | S3 | confirmed |
| PC-04 | [CC-10 #168] 3 of 1,009 slack IT5 successes lack an attempted goal call | source-defect (CC-10) | S3 | confirmed |
| PC-05 | 614 empty final answers (gpt-oss-20b 452, Llama-3.1-70B 139, gemini-2.5-pro 19) | source-defect (R1) | S3 | confirmed |
| PC-06 | Paper 5.5 (96/120) and 5.4 (161/220) not reproduced by any cell | documentation-mismatch (R3) | S3 | confirmed |
| PC-07 | Profile `paper = none found`; logs reproduce arXiv:2602.05066 section 4.1 | documentation-mismatch (R4) | S3 | confirmed |
| PC-08 | 110 logs rewritten by `5cec9793`; prereg's "no blob changed" is wrong | documentation-mismatch (R4) | S3 | confirmed |
| PC-09 | 70 cross-arm identical attacked trajectories (payload never reached the agent) | expected-known (R2, CC-01, CC-09) | S3 | confirmed |
| PC-10 | Code identity unrecorded: pin's error policy and escaping postdate every log | expected-known (R2) | S3 | confirmed |
| PC-11 | 8 files with secret-like model text (prereg ≤ 5, shortlist 2) | documentation-mismatch (R4) | S3 | confirmed |
| PC-12 | [CC-09] no artefacts.toml entry scopes this corpus; per-entry counts | documentation-mismatch (CC-09) | S3 | confirmed |

Verifier (2026-10-21): every count re-derived by an independent script over all 18,442 blobs (scratch `exam/verify/`); 12/12 confirmed, no class or severity change. Refinements: PC-01's banking literal injections are byte-identical to optim_str x gemini-2.5-pro banking (optim_str-arm-equivalent runs filed under `original`); PC-02 holds at 319-331 under looser call matching; PC-04's 3 are vacuous successes (no call denied without a defence); PC-06's gap is not explained by commit timing (runs <= 2026-01-30); PC-09 recount 71/371 includes the one zero-message group the examiner excluded.

Full evidence, reproduction and recommendations: [`findings.json`](data/ceferisbarov-agentdojo/findings.json). No finding is security-relevant (0 account paths, 0 operator hits, no real secret).

Proposed `artefacts.toml` entries (text only; to the AgentDojo family owner):

```toml
# PC-01
# [[artefact]] id = "agentdojo.art.arm_dir_mixes_adapted_runs"; scope ceferisbarov-agentdojo:head; cause upstream_harness;
#   detector: injections value holds the literal {optim_str}; handling FO; expected 601 logs (gemini-2.5-pro banking 102, workspace 499)
# PC-05
# [[artefact]] id = "agentdojo.art.empty_final_answer" (or widen tacit's proposed local_empty_final);
#   detector agentdojo.empty_assistant_text_ambiguous_unverified@1 (I); handling FO; expected 614 logs
# PC-02/03/04/09/12 (CC-07, CC-09, CC-10): scope.sources/profiles += "ceferisbarov-agentdojo", status "proposed":
#   validity_defects 331 (#181) + 65 (#161); slack_it5_attempt_scored 3; run_error_imposed 65; benign_security_constant 1016;
#   injection_task_as_user 1016; silent_rerun 0 null-final / 18437 unobservable; max_iters_pending 58 calls / 53 logs;
#   provider_ids 877 / 220; incomplete_run 39; empty_log 5; naive_timestamp 18442; payload_not_reaching_agent >= 366
```

Items for AGENTS.md §12: (1) the `original` arm of this corpus is not one goal variant, and the arm is only a path facet (R5); (2) the profile's paper field is wrong (arXiv:2602.05066).

## 8. Recommendations and readiness

1. Profile owner: set `paper` to arXiv:2602.05066 and the code repository; note the grid differences (PC-07).
2. Report original × gemini-2.5-pro banking/workspace split by the injections literal; never pool it with the other original cells (PC-01). R5 owner: consider an arm field.
3. Disclose CC-07 (#181 re-scored banking 39.12 % vs 43.78 % logged; #161 65 passes), empty finals per pipeline (PC-05), and that 5.4/5.5 are not reproducible from the release (PC-06).
4. Widen the catalogue scopes with the PC-12 counts (CC-09); pre-clear the 8 secret-like files in release_scan (PC-11).
5. No data is excluded; zero-success arms (e.g. Qwen2.5-7B) stay in.

**Readiness: `ready-with-caveats`.** L1 counts, identity and the whole L2 pipeline are clean (300/300, deterministic, 0 recompute differences). The caveats are disclosures (one S2, the rest S3) and documentation fixes; none blocks the round. Verifier (2026-10-21): confirmed; no S0/S1, no security finding, outcome gaps H9b/H9c re-derived (72/144, 218/498) and stay documentation-mismatch.

## 9. Reproduction

```bash
W=~/.agentprov/migration-work/precheck/ceferisbarov-agentdojo
BARE=~/.agentprov/staging/10c/ceferisbarov/agentdojo.git; PIN=2273e1cd42493398d1581121c4c4439a8ecc072a
X=docs/reports/precheck/data/ceferisbarov-agentdojo/exam-scripts
# batch (already run): tools/precheck/run_batch.py --plan tools/precheck/plans/wave3.toml (l1, l1_10, sample, import_j2, import_j1, check)
uv run python -I $X/exam.py  $W/l1-units-head.jsonl $BARE $PIN $W/exam/exam-census.json ~/.agentprov/upstream/github.com/ethz-spylab/agentdojo.git
uv run python -I $X/extra.py $W/l1-units-head.jsonl $BARE $PIN $W/exam/extra.json
uv run python -I $X/h8it.py  $W/l1-units-head.jsonl $BARE $PIN $W/exam/h8it.json
uv run python -I $X/cc10.py  $W/l1-units-head.jsonl $BARE $PIN $W/exam/cc10.json
GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file git --git-dir $BARE log --no-renames --diff-filter=MD --name-status --format='C %h %cI' $PIN -- reruns
# round (heavy, not run): uv run agentprov import ceferisbarov-agentdojo --input $BARE --verify-against-pin --corpus <corpus>
```
