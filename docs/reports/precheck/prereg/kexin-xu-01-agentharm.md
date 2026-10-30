# Pre-registration: `kexin-xu-01-agentharm`

| | |
|---|---|
| Corpus | `kexin-xu-01-agentharm` (restricted-use class: MIT + AgentHarm use clause; family `inspect`, profile `kexin-xu-01-agentharm` v1, dialect/mapper `inspect.eval` v2, semantics `inspect.agentharm@2`) |
| Parts | `logs` (only part; registry `planned`, figure 2,825 samples, basis census) |
| Wave / kind | Wave 4; first pre-check examination (not in FA or E2), so section 8 (movement since E2) is n/a; movement since the phase-10h trial is given instead |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Inputs: desk research (`../data/kexin-xu-01-agentharm/research.json`, every URL there), our prior reports (phase-10e card §3.3, phase-10h README/routing/redaction design, the phase-10h census and map-census JSON under `~/.agentprov/migration-work/phase10h/census/`, DECISIONS D-180..D-188, regen-batch), the profile and the registry. Nothing was read from or computed on the raw logs in this step |
| Method | [`../README.md`](../README.md) |

**Account names.** No account name or path containing one appears here. The three local checkpoints are named
`run 40` (SFT-GRPO-v3, merged), `run 42` (SFT-v4, merged) and `run 56` (SFT-v5, LoRA), as in the author's own reports.

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Repository | [Kexin-xu-01/agentharm](https://github.com/Kexin-xu-01/agentharm): personal working copy of `inspect_evals` (not a GitHub fork) with run logs and analysis; created 2026-09-12, 0 issues | GitHub API |
| Pin | `859c34f411fd` = HEAD of `main`, 2026-09-26T22:39:28Z; tree `logs/` 68 blobs, 36,467,328 B (26 / 20 / 2 / 20 in `logs/`, `patched-judge/`, `-v2/`, `-v3/`) | GitHub trees API; profile |
| Log history | 68 logs added by 10 commits 2026-09-12..09-26 (bd5d9bf 7, 0b88ad1 9, 54be0bc 6, d23b92e 2, 0eb546e 2, d393605 6, 545a638 14, 89913d8 2, 8a12ac0 2, 2627c9b 18); no log modified after it was added; the pin commit adds only analysis files | GitHub commits API |
| Paper | none for this data. Benchmark paper AgentHarm (arXiv 2410.09024 v1 2024-10-11, v2 2024-10-14, v3 2025-04-18, ICLR 2025) | arXiv |
| Documentation | `analysis/*.md` at the pin: full-model comparison, paper-style tables, refusal-judge artifact, patched re-run (v1 → v3), v2 re-run, content-filter blind spot, prompt-bias caveat | repository |
| Data record | none (no Zenodo/HF/Figshare); author's results also pushed to an external evaluation service (Hedgerow), not a data record | repository docs |
| Harness | `inspect_ai` 0.3.263 (PyPI 2026-09-04), `inspect_evals` 0.20.0 (= upstream `360484a`, 2026-09-11); agentharm source files at the pin are blob-identical to upstream v0.20.0; task version 8 (8-B) | census; PyPI; GitHub contents API |
| Judges | refusal + semantic judge `openai/gpt-4o-2024-08-06` (task default) in every finished log; logs under `patched-judge*/` were scored by the author's locally patched scorer (v1, v2, v3) | census; analysis docs |
| Benchmark subset | AgentHarm `test_public`, Fraud (24) + Cybercrime (20) = 44 behaviours per log, harmful and benign, no attack (direct request), epoch 1 | analysis docs; census |

## 2. Expected counts (part `logs`)

| Quantity | Expected | Source |
|---|---:|---|
| Tree entries at pin under `logs/` | 68 blobs, 36,467,328 B | profile `expected_files/bytes`; GitHub tree (2026-10-14) |
| Selected `.eval` files | 68 (no `.DS_Store`/`._*`) | profile `[import]`; tree |
| Finished logs (`header.json`) / unfinished (`_journal/` only) | 66 / 2 | census (D-181) |
| Log status | success 63, error 3, none 2 | census |
| Samples (registry figure) | **2,825** = 2,797 in finished logs + 28 in unfinished | `tools/readme_corpora.toml`; census |
| Samples by directory | `logs/` 977 (924 success-log + 25 error-log + 28 unfinished), `patched-judge/` 880, `-v2/` 88, `-v3/` 880 | census |
| Importable executions (all finished logs) | 2,797; the 28 unfinished samples register `select.dialect_planned` | D-181; map-census |
| Logs naming a local-path model / their samples | 18 / 792 (6 per directory `logs/`, `patched-judge/`, `-v3/`) | census; profile quirk |
| Importable without the 18 (L2 population) | 48 finished + 2 unfinished logs; **2,005** executions | phase-10h trial (D-187) |
| Sample errors | 25 (all in the 3 error logs: 1 + 4 + 20) | census |
| Message limits (`sample_limit`) | 298 (logs/ 96, patched-judge 96, -v2 7, -v3 99) | census; profile quirk |
| Samples with ≥ 1 tool call | 2,043 | census |
| Tool events / tool calls | 11,036 / 11,036 (34 tools) | census |
| Model events | 19,061 (judge-span 8,797) | census |
| Events: score / sample_init / span_begin / state / info / logger / error | 2,800 / 2,825 / 36,411 / 13,802 / 2,344 / 196 / 25 | census |
| Messages by role | system 2,825, user 2,825, assistant 10,239, tool 10,926 | census |
| Tool errors | `file_not_found` 530, `parsing` 127 | census |
| Zip compression | method 93 (zstd) on all members | census (`methods`) |
| Distinct message-list digests | 2,450 of 2,825; 230 text-equal groups (2-9 samples), 0 byte-identical members expected | census; D-181 |
| Distinct first user prompts | 89 (44 harmful + 44 benign + 1 Disinformation `1-1`) | census overlap |
| Secret-like matches | 33 (in 10 logs), all inside longer tokens of simulated terminal output | census; D-188 |
| Account-path pointers (header) | `/eval/dataset/location` 66 logs (2 accounts); `/eval/model` 18 logs; `_journal/start.json` of the 2 unfinished logs | census; redaction design §1 |
| Trial (50 logs, phase 10h) | 2,005 mapped; 1,965 ok / 40 ok_with_issues; register: `inspect.sample_limit` 186, `inspect.unmapped_event` 47, `missing_tool_result` 40, `dangling_source_ref` 40; 0 failed, 0 degenerate | phase-10h README §4 |

## 3. Expected arms

Facets (L1 `STRATA`): `judge_variant` (directory: base, patched-judge, patched-judge-v2, patched-judge-v3) × `model` ×
`task` (harmful `inspect_evals/agentharm`, benign `inspect_evals/agentharm_benign`). L1 buckets the three local
checkpoints into one `<local-path-model>` value. No defence and no attack facet (`no_attack = true`).

| Model (agent) | base H / B | patched-judge (v1) H / B | v2 H / B | v3 H / B |
|---|---|---|---|---|
| `anthropic/claude-sonnet-5` | 44 (+4 error) / 44 (+20 error) | 44 / 44 | 44 / 44 | 44 / 44 |
| `google/gemini-2.5-pro` | **44 + 44 (two success logs)** / 44 | 44 / 44 | – | 44 / 44 |
| `google/gemini-2.5-flash` | 44 / 44 | 44 / 44 | – | 44 / 44 |
| `google/gemini-2.5-flash-lite` | 44 / 44 | 44 / 44 | – | 44 / 44 |
| `openai/gpt-4o-2024-08-06` | 44 (+ 2 unfinished: 18 + 10) / 44 | 44 / 44 | – | 44 / 44 |
| `openai/gpt-4o-mini` | 44 / 44 | 44 / 44 | – | 44 / 44 |
| `vllm/Qwen/Qwen3-14B` (base) | 44 / 44 | 44 / 44 | – | 44 / 44 |
| local run 40 (SFT-GRPO-v3, merged) | 44 / 44 | 44 / 44 | – | 44 / 44 |
| local run 42 (SFT-v4, merged) | 44 / 44 | 44 / 44 | – | 44 / 44 |
| local run 56 (SFT-v5, LoRA on Qwen3-14B) | 44 / 44 | 44 / 44 | – | 44 / 44 |
| `anthropic/claude-sonnet-4-5-20250929` | 1 (error, 176-sample dataset) / – | – | – | – |

- **Design (author's docs):** 10 models × 2 tasks × 44 behaviours in `logs/`, `patched-judge/` and `patched-judge-v3/`;
  `patched-judge-v2/` Claude Sonnet 5 only. Expected missing cells: none.
- **Expected extra cells (not in any doc table):** a second Gemini 2.5 Pro harmful success log in `logs/` (88 samples,
  docs report 44); two error logs of Claude Sonnet 5 (4 and 20 samples, the docs' expired-key 401 attempt); one
  Claude Sonnet 4.5 error log (1 sample, `Disinformation 1-1`, no behaviour filter); two unfinished GPT-4o harmful logs
  (18 + 10 samples, judged, no header).
- L1 strata: 52 (17 base with header + 1 unfinished, 16 v1, 2 v2, 16 v3). L2 unit = the `.eval` log (selected whole,
  `l2_import.py`); after `--exclude-flag` for the local-path-model logs (the import guard refuses them, D-182 table
  pending) 50 logs in 46 strata remain, every stratum ≤ 5 logs, so **the L2 sample is all 50 logs (2,005 executions +
  28 `dialect_planned`)**. Arms run 40/42/56 (18 logs) are L1 only.
- Categories per finished 44-sample log: Fraud 24, Cybercrime 20 (sums: Fraud 1,542, Cybercrime 1,282, Disinformation 1).

## 4. Expected outcome rates (L2 comparison reference)

No paper evaluates this subset. References are the author's `analysis/` documents at the pin (raw scorer for `logs/`)
and the patched re-run documents (v1 at `545a638`, v2 at `89913d8`, v3 at the pin). n = 44 per arm; 1 sample = 2.27 pp,
so a percentage is converted to a count (round(rate × 44)) and compared as a count.

**Base (`logs/`, raw upstream scorer; full-model comparison / paper-style Table 1 at the pin):**

| Model | H refusal (count) | H harm score | H non-refusal score | B refusal (count) | B score |
|---|---:|---:|---:|---:|---:|
| Base Qwen3-14B | 20.5 % (9) | 0.571 | 0.689 | 0.0 % (0) | 0.716 |
| run 42 SFT-v4 | 50.0 % (22) | 0.352 | 0.705 | 0.0 % (0) | 0.749 |
| run 56 SFT-v5 | 61.4 % (27) | 0.274 | 0.669 | 2.3 % (1) | 0.720 |
| run 40 SFT-GRPO-v3 | 50.0 % (22) | 0.369 | 0.707 | 0.0 % (0) | 0.711 |
| GPT-4o | 45.5 % (20) | 0.462 | 0.807 | 0.0 % (0) | 0.853 |
| GPT-4o-mini | 25.0 % (11) | 0.523 | 0.631 | 0.0 % (0) | 0.762 |
| Gemini 2.5 Pro | 50.0 % (22) | 0.444 | 0.717 | 6.8 % (3) | 0.748 |
| Gemini 2.5 Flash | 59.1 % (26) | 0.334 | 0.802 | 0.0 % (0) | 0.774 |
| Gemini 2.5 Flash-Lite | 86.4 % (38) | 0.235 | ~0 | 72.7 % (32) | 0.454 |
| Claude Sonnet 5 | 70.5 % (31) | 0.091 | 0.231 | 61.4 % (27) | 0.610 |

Per-category (Fraud/Cybercrime) refusal and score for every arm are in the same table and are used for H-08.

**`patched-judge/` (v1 patch; patched re-run doc at `545a638`):** H refusal / H score / B refusal / B score:
Base Qwen 13.6 % (6) / 0.510 / 0 / 0.733; SFT-v4 59.1 % (26) / 0.355 / 0 / 0.709; SFT-v5 63.6 % (28) / 0.288 / 2.3 % (1)
/ 0.733; SFT-GRPO-v3 47.7 % (21) / 0.388 / 0 / 0.744; GPT-4o 54.5 % (24) / 0.412 / 0 / 0.844; GPT-4o-mini 25.0 % (11) /
0.610 / 0 / 0.751; Gemini Pro 27.3 % (12) / 0.514 / 0 / 0.767; Flash 54.5 % (24) / 0.357 / 2.3 % (1) / 0.794; Flash-Lite
52.3 % (23) / 0.236 / 0 / 0.505; Claude Sonnet 5 72.7 % (32) / 0.091 / 43.2 % (19) / 0.641.

**`patched-judge-v2/` (Claude only; v2 doc):** H 68.2 % (30) / 0.091; B 9.1 % (4) / 0.611.

**`patched-judge-v3/` (table at the pin):** Base Qwen 13.6 % (6) / 0.533 / 0 / 0.700; SFT-v4 54.5 % (24) / 0.323 / 0 /
0.715; SFT-v5 63.6 % (28) / 0.260 / 2.3 % (1) / 0.718; SFT-GRPO-v3 50.0 % (22) / 0.399 / 0 / 0.713; GPT-4o 47.7 % (21) /
0.472 / 0 / 0.844; GPT-4o-mini 27.3 % (12) / 0.545 / 0 / 0.729; Gemini Pro 25.0 % (11) / 0.470 / 0 / 0.715; Flash 56.8 %
(25) / 0.373 / 2.3 % (1) / 0.789; Flash-Lite 59.1 % (26) / 0.181 / 2.3 % (1) / 0.551; Claude Sonnet 5 84.1 % (37) / 0.100
/ 22.7 % (10) / 0.578. The prose of the same document still quotes several v1 values (lead L-05).

**Context only (not a verdict reference):** AgentHarm paper v3 Table 9, all 11 categories, no attack: GPT-4o harm 48.4 %,
refusals 48.9 %, non-refusal harm score 90.1 %, benign non-refusal score 89.9 % [label corrected by fact-check]; GPT-4o mini 62.5 % / 22.0 % / 77.5 % / 79.9 %.

**Metric mapping.** Sample `scores.combined_scorer.value.score` → judgement `combined_scorer.score` → SEM
`inspect.harmful_task_score` / `inspect.benign_task_score`; `.value.refusal` → `inspect.refusal`. "refusal rate" /
"false-positive refusal rate" = mean refusal; "harm score" / "completion score" = mean score; "non-refusal score" = mean
score over refusal = 0 (NaN when all refused, 4-B). Header `results` also holds `avg_full_score` (share of score 1.0,
affected by #2146 at 0.20.0, not used by the author). Verdict rule for base, v1, v2 and v3 arms that L2 imports
(whole logs, n = 44 ≥ 20): the refusal count must equal the reference count and the mean score must be within ±0.0005;
a gap above 15 pp or outside the binomial rule of README §4 is a finding; any count difference ≥ 1 is investigated
(rounding of a percentage cannot explain it). The Gemini 2.5 Pro base harmful arm has two logs: compared per log
(H-04). Arms of the 18 local-path logs are compared only if L1 records the per-sample score and refusal.

## 5. Known quirks (expected-known)

| Id / decision | Expected |
|---|---|
| profile `inspect.judge_model_separate_from_agent` | judge = gpt-4o-2024-08-06 everywhere; equals the agent in the 6 finished GPT-4o logs (+ 2 unfinished); separated by spans |
| profile `inspect.unfinished_log` | 2 logs / 28 samples, `select.dialect_planned`, "no header.json member" (R-H2) |
| profile `inspect.patched_judge_reruns` | `patched-judge*/` are fresh runs (distinct uuids and message ids), not rescorings |
| profile `inspect.local_path_model_id` | 18 logs / 792 samples; D-182 implemented (2026-10-13) but **the profile has no `redact` table yet** (R-H1 owner action) |
| profile `inspect.sample_limit` | 298 samples |
| profile `inspect.event_order_not_time_order`, `attachment_refs`, `tool_span_separate_from_tool_event` | all samples / per rule |
| `artefacts.toml` | **no entry scoped to kexin**: the `inspect.art.*` entries name the survey only; analogous behaviour (empty assistant text, lost tool results, judge equals agent) is expected but uncatalogued here |
| D-181 | 230 text-equal groups are independent runs (no dedup); 49 cross-source groups with fragfuse; 0 with the survey |
| D-186 option (c) | raw with account paths ships unchanged; AER/SEM/PROV must be redacted (D-182) |
| D-188 | 33 secret-like matches, synthetic, no withholding |
| R-H4 | `inspect.unmapped_event` for `logger` (196) and `error` (25) events; kexin not affected by item 16 (1,551 parallel batches agree with their call ids; 110 pruned results → `missing_tool_result`) |
| Producer | `inspect_ai` 0.3.263 is not in the verified code list → `_unverified` twin rules expected (regen-batch item 12 note) |
| Bench identity | **[corrected by fact-check]** header `revision` (phase-10h census): origin `Kexin-xu-01/agentharm.git` with a kexin-repo commit (7 values, 35 logs); origin upstream `UKGovernmentBEIS/inspect_evals.git` @ `360484a` (1 log, Claude Sonnet 4.5); none in 30 finished logs (24 vLLM + the 6 `patched-judge/` logs of Claude Sonnet 5, Gemini 2.5 Pro, Flash-Lite); unfinished logs have no header. `revision` marks the run batch, not the judge variant |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | section 2; 68 files, 66 headers, 2,825 sample members; selected 68 / not selected 0 |
| L1-02 strict parse | yes | zstd members through `agentprov.ingest`; expect 0 failures (census read all members) |
| L1-03 encodings | yes | expect 0 bidi/tag/U+FFFD/mojibake in harness fields; model text may hold emoji/variation selectors (counts only) |
| L1-04 duplicates | yes | 0 byte-identical members; 230 text-equal groups; cross-corpus with fragfuse (49 groups) and survey (0) |
| L1-05 arm coverage | yes | section 3 (judge_variant × model × task); attack/defence facets n/a |
| L1-06 secrets/paths | yes | counts and pointers only; section 2 figures (H-13) |
| L1-07 timestamps | yes | per-event ISO with offset; file-name time is the UTC start; bounded by the adding commit (H-12) |
| L1-08 degenerate | yes | 2 unfinished, 3 error logs (25 error-only samples), 298 limit-stopped |
| L2 A2 error classes | yes | the 25 error-only samples of the 3 error logs are in the 50 logs and map with run status `error` (map-census: 25); limit stops 186; `logger`/`error` events kept in `ext` |
| L2 A3 PROV classes | yes | dangling/missing tool results (~40 in the 50 logs), unattributed judge prompts |
| L2 evidence classes | yes | D/I/O with `_unverified` twins (producer not verified) |
| L2 degenerate / `adapter_defect` | yes | expect 0 |
| L2 identity | yes | 8 agent model ids in the 50 logs + gpt-4o judge; bench `agentharm` task version 8; patched-judge variant not recorded in-log (H-10) |
| L2 redaction | yes | in the 50 logs: 0 account segment in AER/SEM/PROV (dataset location not copied); the 18 local-path logs are guarded out, so the D-182 gap is reported as expected-known, not tested |
| L2 withholding | no | profile has no `[withhold]` table and D-186 (c) adds none; check only that nothing is withheld |
| L2 outcome sanity | yes | section 4, whole-log arms n = 44 |
| L2 determinism | yes | second import with other `--jobs`, byte-identical (trial: 8,153 files identical) |

## 7. Hypotheses (falsifiable, thresholds)

| Id | Lead | Expectation | Fails if |
|---|---|---|---|
| H-01 | – | 68 logs: 66 headers (63 success, 3 error), 2 journal-only; 2,825 sample members; per-log samples as section 3 | any count differs |
| H-02 | L-02 | the 3 error logs: every sample errored, 0 scored; the Claude Sonnet 5 error samples carry an authentication (401) error | any scored sample, or another error class in those logs |
| H-03 | L-02 | the 2 unfinished logs: agent and judge `gpt-4o-2024-08-06`, harmful task, 18 + 10 samples each with a score | other model/task, or unscored samples |
| H-04 | L-01 | of the two Gemini 2.5 Pro base harmful logs, exactly one reproduces 22/44 refusals and mean 0.444 ± 0.0005 | neither or both match |
| H-05 | – | base arms: refusal counts and mean scores equal section 4 (20 arms, the 2 Claude error logs excluded) | any refusal count off by ≥ 1 or a mean off by > 0.0005 |
| H-06 | L-05 | v1 arms equal the `545a638` table; v2 equals the v2 doc; v3 arms equal the pin table | any count off; if v3 rows equal v1 values instead, record as documentation-mismatch (S2) |
| H-07 | L-11 | Claude Sonnet 5 model events with `stop_reason = content_filter`: 8 harmful + 4 or 5 benign samples per run; refusal = 1 for them only in v3, 0 in base/v1/v2 | different counts or flags |
| H-08 | – | per category per arm (Fraud 24 / Cybercrime 20) refusal counts equal the docs' per-category rates | any off by ≥ 1 |
| H-09 | L-07 | benign samples with a `read_file`/`edit_txt`/`convert_pdf_to_text` not-found result > 0 (census: 530 `file_not_found` tool errors over all samples) | 0 → lead refuted; ≥ 1 in benign → finding (S2, documentation-mismatch: benign scores depressed by #2439) |
| H-10 | L-03 | patched-judge* headers name the same scorer (`combined_scorer`), `inspect_evals` 0.20.0 and task version 8 as base logs; the variant is visible only by directory and by explanation text | header differs between variants (then identity can be recorded) |
| H-11 | L-08 | 0 refusal explanations holding `Error in RefusalJudgeLLM` | ≥ 1 → finding (S2) |
| H-12 | L-18 | every event timestamp parses, has an offset, lies after the file-name start time and before the commit that added the log | any outside |
| H-13 | L-16 | account-path pointers: `/eval/dataset/location` 66/66 headers, `/eval/model` 18; 0 in other header pointers; 0 in AER/SEM/PROV of the 50 imported logs | any other pointer, or any hit in derived records |
| H-14 | – | secret-like matches 33, 0 whole tokens, 0 in headers | other |
| H-15 | L-14 | `logger` events (196) concentrate in Claude Sonnet 5 logs (temperature not supported warning) | < 50 % of them in Claude logs |
| H-16 | – | L2 (50 logs): 2,005 executions, 0 failed, 0 degenerate, `sample_limit` 186, `unmapped_event` 47, `missing_tool_result` 40 | any count differs by > 0 without an explained code change (section 8) |
| H-17 | L-13 | per finished 44-sample log: the same 44 behaviour ids per task (harmful set = benign set of id numbers), Fraud 24 / Cybercrime 20 | any log with another set |
| H-18 | – | 0 byte-identical sample members; text-equal groups 230 ± 0 within the part | other |

## 8. Expected movement since the phase-10h trial (no E2 baseline)

| Change | Expected on this corpus |
|---|---|
| Item 12, D-374/D-375, U6-a/U6-b | run scope and span activities gain harness association; judge actors `unk` code/version; `/params/transmitted` `lost` after 5 kept calls per model per sample (counts not predicted) |
| Item 30 (D-31 option B) | AER `rules` declares `inspect` at 2, SEM `inspect.agentharm@2`; every digest differs from the trial |
| D-372 (completeness) | samples with a lost/missing tool result may move from `verified_complete` to `known_incomplete` (≤ 40 in the 50 logs) |
| D-182 (redaction code) | no effect without a profile table; 18 logs still excluded |
| Items 16, 25, 28, R-10p-2 | no AER body change expected (0.3.263: no first-of-batch message ids, no strings > 1 MiB, no `model_roles`) |
| Expand bundles | `fn_digest` and `limits_sha256` move; member digests unchanged |

## 9. Fact-check (adversarial, 2026-10-14, desk only; no raw data read)

Checked against the cited sources (GitHub API at the pin, upstream `inspect_evals` at `360484a`, PyPI, HF API, arXiv
v3 HTML and abs page) and our own phase-10h census/README (no new computation on raw logs).

| Claim | Verdict |
|---|---|
| Pin `859c34f4` = HEAD of `main` (2026-09-26T22:39:28Z), `pushed_at` 22:39:34Z; repo public, MIT, not a fork, created 2026-09-12, 0 issues | confirmed |
| `logs/` at the pin: 68 blobs, 36,467,328 B (26/20/2/20) = profile `expected_files/bytes` | confirmed |
| 10 log-adding commits and their counts (7, 9, 6, 2, 2, 6, 14, 2, 2, 18); no later modification; pin commit adds only analysis files; `logs/` gitignored upstream | confirmed |
| Base table (10 arms, refusal/harm/non-refusal/benign/FP) and per-category rates, `analysis/agentharm_full_model_comparison.md` at the pin; percentage → count conversions | confirmed |
| v1 table at `545a638`, v2 table, v3 table at the pin (refusal, FP, harm, completion; all 10 rows) | confirmed |
| L-05: v3 doc prose still quotes v1 values; "where the data lives" (only Claude's JSONL rows v3) contradicts the content-filter doc (all 880 rows v3) | confirmed |
| Content-filter samples (harmful 22-1..4, 45-1..4; benign 22-1..4 + mid-conversation 43-2); documented on the v2 run, verified in v3 via explanation text, and asserted by the author to recur in every run (base/v1 counts are the author's assertion, not a table) | confirmed (with that caveat) |
| 62 contradiction samples (Flash-Lite 30, Claude 19, Pro 7, ...); 15 Gemini Pro tool-only samples; Claude 401 expired key; Claude temperature note | confirmed |
| AgentHarm paper v1/v2/v3 dates, ICLR 2025; Table 9 GPT-4o 48.4/48.9/90.1/89.9 and GPT-4o mini 62.5/22.0/77.5/79.9 | confirmed; **label corrected**: the fourth figure is the benign *non-refusal* score, not a plain benign score |
| `inspect_ai` 0.3.263 (PyPI 2026-09-04), `inspect_evals` v0.20.0 = `360484a` (2026-09-11); agentharm `scorer.py`, `agentharm.py`, `metric.py`, `utils.py`, `LICENSE` blob-identical to upstream | confirmed |
| Changelog: 8-B latest entry at v0.20.0 and v0.24.0; 5-B introduced the `<reasoning redacted="true" />` marker (#2107) | confirmed |
| #2439 open, reproduced with `inspect-ai==0.3.263` + `360484a`; #2212 open; #2312 open; #2146 closed 2026-10-01 by #2154; #2108 open; #2290 open; inspect_ai #4553 (zstd, method 93) | confirmed |
| Root LICENSE MIT (c) 2024 UK AISI, blob `72fc8774`; agentharm LICENSE MIT with additional AI-safety-only clause (Gray Swan AI + UK AISI); HF card licence `other`, not gated, sha `e23b3fe6` (2024-12-19) | confirmed |
| No paper and no data record for the logs | not refutable (none found); unverifiable in the strict sense |
| Section 2 census figures (2,825; 66/2; 63/3; 977/880/88/880; 18/792; 298; 2,043; event counts; roles; tool errors; 2,450/230; 33 in 10 logs; method 93; pointers) and trial figures (2,005; 1,965/40; 186/47/40; 8,153) | confirmed against the phase-10h census.json and README |
| Section 3 arm table (per-log model × task × status × samples) and L1 52 / L2 46 strata arithmetic | confirmed against census `per_log` |
| Unfinished logs are GPT-4o harmful (18 + 10) | unverifiable from the census (model/task not recorded without a header); consistent with the adding commit (`0b88ad1`, GPT-4o + Gemini Pro) and the file names (task `agentharm`); left as hypothesis H-03 |
| L-04 / section 5 "Bench identity": `revision.origin` names upstream for the kexin commits | **refuted and corrected**: origin is the kexin repository for those 35 logs; only the Claude Sonnet 4.5 log names upstream; 30 finished logs have no revision (24 vLLM + 6 `patched-judge/` v1 API logs) |

Corrections applied: (1) section 5 "Bench identity" row and research.json L-04; (2) Table 9 benign column label in
section 4 and research.json. Note for H-10: `revision` differs between directories because it records the run batch;
that difference does not by itself identify the judge variant and must not be read as H-10 failing. No expectation was
added from data.
