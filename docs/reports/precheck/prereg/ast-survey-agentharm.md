# Pre-registration: `ast-survey-agentharm`

| | |
|---|---|
| Corpus | `ast-survey-agentharm` (restricted-use class: CC-BY-4.0 + AgentHarm use clause) |
| Parts | `agent-security-tools-survey · agentharm` (family `inspect`, profile `survey-agentharm@1`, semantics `inspect.agentharm@2`, dialect `inspect.eval` v2) |
| Wave / kind | Wave 1; examined in E2, so this pre-check covers the **delta since E2** |
| Code | `065b0d36` or later on `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Inputs: desk research (`../data/ast-survey-agentharm/research.json`, URLs there) and our prior reports only. No raw data read, nothing computed from it |

Sources used: survey `agentharm/README.md` and `run_full_benchmark.sh` @ `89c4db2c` (run-time script: `agentharm/run_full.sh` @ `2a8bee89`); root `README.md` @ `89c4db2c` (Ollama 0.23.1); Zenodo API; HF API; inspect_evals AgentHarm
changelog and issues; inspect_ai tags; `docs/reports/inspect/README.md` and `import-cli-agentharm.json` (import, phase 6);
E2 (`../../analysis/phase10-examination-2.md`); `../../analysis/regen-batch.md`; `src/agentprov/adapters/inspect/`
(profile, `artefacts.toml`, semantics); investigation `sources/` and `verify/agent-security-tools-survey.md` (2026-10-07).

## 1. Expected counts

| Quantity | Expected | Source |
|---|---|---|
| Pinned tree `agentharm/results` | 7 blobs, 11,911,647 B | import report (`pinned_snapshot_check`), verify §2.2 |
| Candidate files (`.eval`) | 6, 11,825,414 B; sizes/sha256/blob ids = SWEEP_r2 EV-3 | profile `expected_files`/`expected_bytes`; import report |
| Not candidates | `timing_summary.csv` (86,233 B, context artefact); `.DS_Store`/`._*` excluded if present | profile `[import]` |
| Archive members | 1,691 `raw/members.jsonl` rows: 1,062 selected (6 `header.json` + 1,056 samples), 629 not selected | import report `expand`; regen-batch (12b bundle) |
| Members per log (cross-check) | 286 per log per verify §2.3 → 1,716; differs from 1,691 by 25 (lead L-10) | verify report |
| Units (samples) | 1,056 = 6 × 176; `epoch` 1 only | registry `tools/readme_corpora.toml` (1056), import report, survey README |
| Executions (AER) | 1,056; failed 0; degenerate 0; status ok 1,052 / ok_with_issues 4 | import report; E2 §7.1 |
| Completeness (current code) | verified_complete 1,052 / known_incomplete 4 (was 1,056 / 0 in E2) | regen-batch items 9/11 (D-372) |
| Model events | 5,261 = agent 3,660 + judge 1,601 | verify §2.3; E2 7.2 (1,601 judge inputs) |
| Tool events / tool spans | 4,164 / 4,164 | verify §2.3; `inspect.art.tool_span_separate_from_tool_event` |
| Step activities | 8,388 = 4,164 tool + 4 × 1,056 run spans | regen-batch item 12 |
| Reasoning blocks | 2,282 (qwen14_harmful 509 / qwen14_benign 584 / coder_harmful 0 / coder_benign 0 / gptoss_harmful 269 / gptoss_benign 920) [labels added by fact-check] | verify §2.3 |
| `sample_limit` | 54 samples (coder_benign 9, gptoss_benign 33, qwen14_benign 6, qwen14_harmful 6) | `inspect.art.sample_limit` |
| Lost tool results | 16 tool events in 4 samples (coder_benign 4, qwen14_benign 12), all at the limit | `inspect.art.tool_result_lost_at_limit`; E2 7.2 |
| Empty agent assistant text | 2,345 messages (coder_benign 417 / coder_harmful 221 / gptoss_benign 820 / gptoss_harmful 104 / qwen14_benign 426 / qwen14_harmful 357) [CORRECTED by fact-check: labels added; the order differs from the reasoning-block row] | `inspect.art.empty_assistant_text` |
| `max_tokens` stops / text-encoded calls | 23 / 12 (qwen3-coder `<function=`, 14 turns) | E2 A02, 10.1 |
| Integers beyond I-JSON in raw | 10 (→ 6 `$int` wrappers in AER) | E2 X01/A04 |
| AER records / SEM records (stored, E2) | 54,832 / 16,700 | E2 §3.1 |

## 2. Expected arms

No defence and no attack facet (`no_attack = true`; harmful request is the task itself, `payload_in_task_prompt` 1,056).

| Model (agent) | harmful (`inspect_evals/agentharm`) | benign (`inspect_evals/agentharm_benign`) | Judge (refusal + semantic) |
|---|---:|---:|---|
| `ollama/gpt-oss:120b` | 176 | 176 | `ollama/qwen3:14b` |
| `ollama/qwen3-coder:30b` | 176 | 176 | `ollama/qwen3:14b` |
| `ollama/qwen3:14b` | 176 | 176 | `ollama/qwen3:14b` (self-judging, separated by spans) |

Split `test_public` only; `val`, chat and `test_private` absent by design. Expected missing cells: none. Expected extra
cells: none (one log per cell, header status `success` × 6, no rerun). Task version 2 (`full_task_version` 2-B), bench
code commit abbreviated (`2dd469a`, declared ambiguous). L2 strata = these 6 cells; ~5 per stratum → **30 sampled
executions**.

## 3. Expected outcome rates (reference for L2 and H-05/H-06)

The AgentHarm paper (arXiv 2410.09024, Table 9) evaluates none of these models (15 models; Qwen3 and gpt-oss postdate v3). Its Table 1 public test set is 264 behaviours; the released HF `test_public` has 176 harmful + 176 benign, which is what n = 176 rests on (L-15, context only). The only reference is the survey
README, `agentharm/README.md` @ `89c4db2c`, "Our Results" l. 342-349 (= the log headers' `results`, reproduced in
verify §2.3). n = 176 per arm.

| Arm | avg_score | avg_full_score | avg_refusals (count) | avg_score_non_refusals |
|---|---:|---:|---:|---:|
| gpt-oss:120b harmful | 0.131 | 0.108 | 0.915 (161) | 0.769 |
| gpt-oss:120b benign | 0.640 | 0.432 | 0.528 (93) | 0.717 |
| qwen3-coder:30b harmful | 0.394 | 0.205 | 0.619 (109) | 0.727 |
| qwen3-coder:30b benign | 0.791 | 0.540 | 0.199 (35) | 0.808 |
| qwen3:14b harmful | 0.495 | 0.199 | 0.290 (51) | 0.586 |
| qwen3:14b benign | 0.607 | 0.284 | 0.063 (11 = 0.0625) | 0.608 |

Refusals total 460 of 1,056 (= E2 10.1). Per-category claims (README l. 396-399): gpt-oss harmful refuses 100 % of
Harassment, Hate, Cybercrime, Sexual; 75 % Disinformation; 83 % Copyright; qwen3:14b harmful 13 % Copyright, 15 %
Disinformation. Wall clock (l. 355-359): gpt-oss 108/165 min, coder 62/89, qwen3:14b 247/289.

**Metric mapping.** `scores.combined_scorer.value.score` → judgement `combined_scorer.score` → SEM claim
`inspect.harmful_task_score` / `inspect.benign_task_score` (graded, unit interval); `.refusal` → `combined_scorer.refusal`
→ `inspect.refusal` (flag). avg_score = mean score; avg_refusals = mean refusal; avg_score_non_refusals = mean score where
refusal = 0; avg_full_score = share with score = 1.0, **but at 2-B it skips samples whose score is not a float (#2146)**.
All are 2-B semantics (lead L-02). L2 compares refusal rate and mean score per arm on n ≈ 5 with Wilson intervals
(score: mean and range); no verdict below 20 per arm; the "interval excludes the reference by > 5 points" rule applies.

## 4. Known quirks (expected-known)

| Id / decision | Expected |
|---|---|
| `inspect.art.sample_limit` | 54 |
| `inspect.art.tool_result_lost_at_limit` | 16 events / 4 samples (`dangling_source_ref` 16, `missing_tool_result` 16) |
| `inspect.art.judge_same_model_as_agent` | 2 logs (qwen14) |
| `inspect.art.event_order_not_time_order`, `message_list_not_creation_order` | all 1,056 samples |
| `inspect.art.tool_span_separate_from_tool_event` | 4,164 spans |
| `inspect.art.empty_assistant_text` | 2,345 |
| `inspect.art.abbreviated_revision` | 6 logs |
| `inspect.art.condensed_references` | 0 dangling input/attachment refs |
| E2 b5 (not catalogued, lead L-11) | `abnormal_finish#max_tokens` 23, `text_encoded_call#marker` 12 unclassified in the safety net |
| E2 c3/c4 → D-374/D-375 | harness association and input attribution (section 7) |
| Producer verified | `inspect_ai` `+g53c1fa98b` is in the item-12 rules' code list → D rules cited at D, no `_unverified` twins |
| Restricted use | U-05 class; AgentHarm credential-shaped strings are synthetic (114 triaged in the deposit rehearsal) |

## 5. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | section 1; reconcile members 1,691 vs 1,716 (H-02) |
| L1-02 strict parse | yes | all `header.json` and sample members (and the other members if read); expect only the 10 big integers |
| L1-03 encodings | yes | raw ≥ AER counts of E2 (variation selectors 260, intact Windows paths 110, literal escapes 1,492); 0 bidi/tag/zero-width/U+FFFD/mojibake |
| L1-04 duplicates | yes | within part, cross-part and cross-corpus (kexin-xu-01-agentharm, fragfuse-agentharm share task prompts, not runs) |
| L1-05 arm coverage | yes (model × split) | defence/attack facets n/a (no attacker) |
| L1-06 secrets/paths | yes | counts and pointers only; header dataset location holds an account path (H-15) |
| L1-07 timestamps | yes | per-event ISO UTC, µs; list order ≠ time order (quirk) |
| L1-08 degenerate | yes | 0 empty, 0 sample errors; 54 limit-stopped |
| L2 A2 error classes | yes | `max_tokens` 23, empty text, text-encoded calls |
| L2 A3 PROV classes | yes | section 7 delta |
| L2 evidence classes | yes | D/I/O; I only for `system_message_from_task_plan` and SEM tables |
| L2 degenerate / `adapter_defect` | yes | expect 0 |
| L2 identity | yes | 3 agent models, judge qwen3:14b, bench `agentharm` v"2", code `2dd469a` ambiguous |
| L2 redaction | yes | no `redact` table; expect 0 author account segment anywhere in AER/SEM/PROV |
| L2 withholding | no | profile has no withhold table; check only that nothing is withheld |
| L2 outcome sanity | yes, Wilson only | 6 × ~5; paper not a reference (other models) |
| L2 determinism | yes | second import with other `--jobs`, byte-identical |

## 6. Hypotheses (falsifiable, thresholds)

| Id | Lead | Expectation | Fails if |
|---|---|---|---|
| H-01 | — | 6 logs × 176 samples, header status `success` 6/6, 0 sample errors, 1 epoch | any count differs |
| H-02 | L-10 | members per log sum to the 1,691 rows; any difference is explained by entries the expander does not list (directories) | an unexplained member, or a member not in `members.jsonl` |
| H-03 | — | raw strict parse: 0 failures other than 10 integers beyond I-JSON | ≠ 10 or any other class |
| H-04 | — | the 3 harmful logs share one set of 176 sample ids; the 3 benign logs share one set | any id missing or extra |
| H-05 | L-09 | header `results` metrics equal the README table to ±0.0005 (24 cells) | any cell off |
| H-06 | — | recount from raw sample scores: refusals 161/93/109/35/51/11; mean score per log within ±0.0005 of avg_score | any count differs |
| H-07 | L-03 (#2107) | agent assistant messages with reasoning and empty text: > 0 in the 4 qwen14/gptoss logs, 0 in the 2 coder logs | coder > 0 or a reasoning log = 0 |
| H-08 | L-05 (#2101) | benign samples graded by `grade_setup_meeting_location`: 0 with score 1.0 | any = 1.0 |
| H-09 | L-06 (#2146) | count JSON-integer score tokens; where > 0, avg_full_score over all 176 differs from the header | integers present and no difference (or the reverse) |
| H-10 | L-07 (#2439) | count benign `read_file`/`edit_txt` tool errors and `convert_pdf_to_text` "not found" results; direction not predicted | ≥ 1 → finding (S2, documentation-mismatch: benign scores depressed by a harness defect) |
| H-11 | L-08 (#2212) | 0 samples whose refusal explanations hold a judge error | ≥ 1 → finding (S2) |
| H-12 | — | the 54 limit-stopped samples each hold ≥ 20 messages (limit 20); the 4 lost-result samples are among them | otherwise |
| H-13 | L-13 | judge model events: no `seed`, no `max_tokens`; agent events: temperature 0, seed 0, max_tokens 4096 | otherwise |
| H-14 | — | all event timestamps parse, UTC, inside 2026-08-21T21:23:06Z..2026-08-22T13:23:23Z; models run one after another (no overlap of sample windows across models); per-log sum of sample `total_time` within 5 % of the README minutes | otherwise |
| H-15 | L-12 | the header dataset-location pointer holds an account path in 6/6 logs; 0 occurrences of that account segment in AER/SEM/PROV; ~85 `/home/`/`/Users/` strings in content pointers (benchmark text) only | any account segment in a harness field or outside content |
| H-16 | L-11 | safety net: `max_tokens` 23, text-encoded calls 12, both unclassified | different counts, or classified |
| H-17 | — | 0 byte-identical sample members and 0 identical trajectories within the part (E2: 0 groups); 0 identical members with the other AgentHarm corpora | ≥ 1 |
| H-18 | — | 0 secret-shaped strings in AER (E2 U14); raw credential-shaped strings only synthetic benchmark values | a real-looking key outside AgentHarm content |

## 7. Expected movement since E2 (current code vs the E2 corpora)

| Change (source) | Expected on this corpus |
|---|---|
| Items 9/11, D-372 (E2-b2) | completeness: 4 `verified_complete` → `known_incomplete`; index/`corpus.json` only |
| Item 12, D-374/D-375 (E2-b3, c3, c4) | run scope `actor: harness` (D, 1,056); spans `init`/`solvers`/`scorers`/`scorer` → harness (D, 1,056 each), `tool` → `env` (D, 4,164); PROV: run and all 8,388 step activities gain `wasAssociatedWith` → E2 orphans run 1,056 → 0, step 7,946 → 0, harness agent → 0. Input user message (m1) `actor: bench` D 1,056; system message (m0) → bench I 1,056 (inference bundle); judge prompts 1,598 stay unattributed (E2's 3,710 unattributed parts fall accordingly). Execution description stays attribute-linked (by design) |
| U6-a (D-374) | judge actors `unk /code,/version not_recorded` in 1,012 executions; bench `/version` "2" (D) in 1,056 |
| U6-b (D-374) | `/params/transmitted` `lost` on 630 calls in 266 executions (489 agent + 141 judge); 0 `not_recorded` |
| Item 30 (D-31, option B) | AER header `rules` declares `inspect` at 2; SEM profile `inspect.agentharm@2`; profile `survey-agentharm` stays 1. Every AER/SEM/PROV digest differs from E2 |
| Items 16, 25, 28, 7, R-10p-2, D-182, item 80, BF-21/22 | no AER body change (0 orphaned results, no role, no string > 1 MiB, no lone surrogate, no redact table, no sandbox event, no deny-listed tool name); catalogue and code digests only; new info issues: 0 |
| Expand bundles (12b, ingest-formats 1-3, BF-19) | member digests, labels, dispositions unchanged; `fn_digest` and `limits_sha256` move |
| Not changed | E2-b5 catalogue entries (absent, L-11); seal issues `inspect.sample_limit` 54, `dangling_source_ref`/`missing_tool_result` 16 in 4; X01-U14 string classes as in E2 |

Rehearsal evidence for these predictions: regen-batch item 12 (`recompute --out` of a clone, 1,056 `changed_explained`, 0
failed, 4 `index_refreshed`, tier 4 pass), repeated after R-10p-2/D-182/item 7 (1,056/1,056 byte-identical AERs).

## Fact-check (2026-10-14, adversarial, desk only; no raw data read)

Re-opened, with results:

- **Outcome table**: survey `agentharm/README.md` @ `89c4db2c` l. 342-349. All 24 cells, the minutes (l. 355-359) and the
  per-category claims (l. 399) match section 3. Refusal counts from rate × 176 round to 161/93/109/35/51/11 = 460, which
  equals E2 l. 751. Confirmed.
- **Paper**: arXiv 2410.09024 v1 2024-10-11, v2 2024-10-14, v3 2025-04-18 (489/489/518 KB). Table 9 covers the public
  test set and Table 10 the private set, with 15 models and no Qwen or gpt-oss. Confirmed. New context lead **L-15**: the
  paper's Table 1 gives a 264-behaviour public test set, but the released HF split has 176/176/44 rows
  (harmful/benign/chat, datasets-server size API). This is not a defect of this corpus.
- **Pin and tree**: HEAD of main is `89c4db2c` ("update doi", 2026-08-28T07:18:31Z). Tree `agentharm/results` has 7 blobs and
  11,911,647 B: 6 `.eval` files (11,825,414 B) plus `timing_summary.csv` (86,233 B). Log commits: only `26692cd6ea42`.
  The repository has 0 issues, PRs, tags and releases. Confirmed.
- **Corrected**: (1) 2a8bee89 edited `agentharm/run_full.sh`, the script in place at run time; `run_full_benchmark.sh`
  only appeared at 26692cd6. Both scripts `cd` into the submodule, which was `2dd469ac` at both commits, so the L-07
  premise holds. (2) 35f51954 also changes `run_full_benchmark.sh` (comment lines only), so "README/report text only" was
  wrong. (3) The Ollama 0.23.1 / UCI claim is in the root `README.md` l. 56-59, not in `agentharm/README.md`. (4) The
  research file's "8 harm categories in the public split" had no source and was withdrawn. (5) The two event-count rows now
  carry per-log labels; the two rows use different orders.
- **Zenodo**: v1.0.0 `22135957` 243,606,319 B md5 `2cdcea49…`; v1.0.1 `22140262` 243,606,321 B md5 `f623f7f7…`; concept
  `22135956`; cc-by-4.0; last update 2026-08-28. Confirmed.
- **Licence**: the repository LICENSE is 18,658 B, spdx CC-BY-4.0. HF `LICENSE` @ `e23b3fe6` reads "MIT License with an
  additional clause", © Gray Swan AI and UK AI Safety Institute. The copy in inspect_evals @ `2dd469ac` says "Security
  Institute". The use restriction (AI safety/security only) is confirmed. The HF sha `e23b3fe6` (2024-12-19) is still
  current. Confirmed.
- **Harness**: inspect_ai `53c1fa98` is 69 commits ahead of 0.3.246 and 132 commits behind 0.3.247 (compare API). The
  survey README l. 270 says v0.3.247. `eval.yaml` @ `2dd469ac` reads `version: "2-B"`. Confirmed.
- **Issue states**: #2107 closed 2026-08-24, #2101 closed 2026-08-24, #1913 PR merged and closed 2026-08-24, and #2146 closed
  2026-10-01 by PR #2154 (that fix is not in the changelog on main). #2108, #2212, #2312, #2439 and #2290 are open. The
  #2439 and #2146 descriptions match L-07 and L-06. The changelog dates are not monotone (7-B and 8-B are dated
  2026-08-11). Confirmed.
- **Our own counts**: 1,062 + 629 = 1,691 (inspect README l. 31); registry count 1056; statuses 1,052/4; E2 AER/SEM 54,832/16,700;
  verify: 286 members per log, model events 3,660 + 1,601 = 5,261, tool events 4,164, `sample_limit` 54 by log;
  `artefacts.toml` has 9 ids and no max_tokens or text-call entry (L-11). Confirmed.
- **Not verifiable at desk**: whether v1.0.0's `agentharm/results` equals git (L-14); the 25-member gap (L-10); whether
  inspect_ai changes the working directory for package tasks (L-07 open question).

