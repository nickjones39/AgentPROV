# Pre-registration: `atia-benchmark`

| | |
|---|---|
| Corpus | `atia-benchmark` (own permissive corpus, MIT) |
| Parts | `atia-benchmark · logs` (family `inspect`, profile `atia-benchmark@1`, dialect `inspect.eval` v2, no semantics profile; registry part `planned`) |
| Wave / kind | Wave 4; **first examination** (not in FA or E2, never stored). Prior evidence: phase-10n census and scratch trials |
| Code | `065b0d36` or later on `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Inputs: desk research (`../data/atia-benchmark/research.json`, URLs there) and our prior reports only. No raw data read, nothing computed from it |

Sources used: GitHub API for `mattngyn/atia_benchmark` (commits, tree at `cc71caf5`, README, LICENSE, code, forks,
issues); the third-party fork `danieljson15/atia_benchmark@6b8feb4c` (`parsed/` rollups only); inspect_ai source and
CHANGELOG at tag 0.3.112 (`a61f8517`) and later; Google's Gemini 2.0 Flash model page; `docs/reports/phase10n/` (README
§5, `routing.md`); profile `atia-benchmark.profile.toml`; registry; `tools/readme_corpora.toml`; DECISIONS D-307–D-309;
spec D.9.10; `regen-batch.md` items 25 and 28; `review-core-d/findings.md` CD-24 and CD-25; `tools/precheck/l1_families.py`.
**No paper exists** (arXiv and web search, 2026-10-14). The README reports no results.

## 1. Expected counts

| Quantity | Expected | Source |
|---|---|---|
| Candidate files (`logs/*.eval`) | 5, 162,365,512 B; blob ids 8b5bca05, a01b477f, 55136410 (corrected, was 5513641e), 7ab115ca, ed49f4ef | profile `expected_files`/`expected_bytes`; GitHub tree at the pin |
| Not candidates | `adversarial_inputs/` (421), `clean_inputs/` (66), `datasets/`, code: outside the pinned `logs/` tree | profile (pin `tree = "logs"`) |
| Archive members | 143, all selected; 123 sample members (`samples/*_epoch_1.json`) + 20 others | census §5.2 (the 20 by subtraction) |
| Samples per log | 01-47-02: 25 · 01-51-09: 19 · 01-52-51: 19 · 01-54-19: 25 · 02-52-21: 35 | census; fork `parsed/eval_summary.csv` |
| Units = executions | **123** (registry count 123, basis census); 1 epoch | `tools/readme_corpora.toml`; trial 123 mapped |
| Log status | 3 `success`, 2 `error` (the two 19-sample logs) | census |
| Scored / errored samples | 121 / 2 (2 `error` events → `inspect.unmapped_event` 2) | census; trials |
| Tool calls | 81 samples with exactly 1, 42 with none, 0 parallel batches; 81 tool events, 0 with `message_id` | census; regen item 25 |
| Media parts in the user turn | 98 samples: image 39, audio 49, video 10; 25 text-only | census |
| Strings > 1 MiB (raw-resolved) | 42: 24 message parts (20 image, 4 video) + 18 request copies | census; item 28 |
| Trial corpus (on item 25, `3cacde6`) | 123 validated, 123 sealed clean, 0 degenerate, 386 files, byte-identical at 8 and 3 workers | phase10n §5.3 |

## 2. Expected arms

One model and one task; no defence. The arm key is the attack type (the `attack_type` sample metadata; L1 facet), with
the log as a secondary facet.

| Model | Task | attack_type | Samples | Media |
|---|---|---|---:|---|
| `google/gemini-2.0-flash` | `account_takeover_suite` | `None` | 25 | text only |
| | | `Summarize_Audio` | 49 | audio |
| | | `Summarize_Image` | 39 | image |
| | | `Summarize_Video` | 10 | video |

Counts per type: fork rollup `by_attack.csv` (`n` column), which agrees with the census media counts.
**Expected missing** against the README: 9 of 10 harm categories, any other model, and the methods named Zou et al.
2023 (text), Gray Swan silent characters and hidden text in images (no label expected). **Expected extra:** re-runs (the
same sample ids in several logs; at most 35 distinct ids) and 2 error logs. **L2 strata:** `("task",)` for this profile,
so there is 1 stratum and a **30-sample draw** (the part minimum) out of 123.

## 3. Expected outcome rates (reference for L2)

There are no author numbers. The only reference is a third party's rollup of the same five logs (fork
`danieljson15/atia_benchmark@6b8feb4c`, `parsed/rollups/`). It is a reproduction target, not an independent value.
Counts are derived from the published means.

| Arm | n rows / scored | ASR (harmful tool invoked) | Count | Where |
|---|---:|---:|---:|---|
| all | 123 / 121 | 0.4876 | 59 | `by_modality.csv` |
| `None` | 25 / 25 | 0.600 | 15 | `by_attack.csv` |
| `Summarize_Audio` | 49 / 49 | 0.612 | 30 | `by_attack.csv` |
| `Summarize_Image` | 39 / 37 | 0.189 | 7 | `by_attack.csv` (mean skips 2 unscored rows) |
| `Summarize_Video` | 10 / 10 | 0.700 | 7 | `by_attack.csv` |

**How the metric maps.** The scorer `harmful_tool_invoked` (`scorer_methods/default.py`) returns `C` when any assistant
`tool_calls[].function` is in `metadata.harmful_tools` and `I` otherwise; its `accuracy` is therefore the ASR. Raw
fields: `samples/*.json` `/scores/harmful_tool_invoked/value` (`C`/`I`; absent for the 2 errored samples) and the score
event. In the AER (no SEM profile) the value is a judgement. On `065b0d36`, CD-24 is open, so the judgement appears
twice: once named `score` (from the event) and once named `harmful_tool_invoked` (actor `bench`, from `sample.scores`).
L2 reads the value from either and checks that the two agree. The header `results` of the 3 success logs are the
second reference, read at L1. At 0.3.112 those results have no scored/unscored counts.
**Verdicts:** only the overall arm (n = 30 ≥ 20) can reach a verdict, by the README §4 thresholds (15 points, or the
Wilson 95% interval excludes 0.488 by more than 5 points). The per-type cells (about 6/12/9/3 expected in the draw) get
Wilson intervals only.

## 4. Known quirks (expected-known)

| Id / decision | Expected |
|---|---|
| profile quirk `inspect.error_logs` | 2 logs with status `error`; their finished samples kept |
| profile quirk `inspect.attachment_refs` | 123 samples with `attachment://` references (media as base64 data URIs) |
| profile quirk `inspect.event_order_not_time_order` | rule `inspect.no_order_from_event_list@1` |
| `inspect.tool_event_no_message_id@1` (item 25, R-10n-1) | 81 calls linked by `tool_call_id`; 0 `missing_tool_result`/`dangling_source_ref` |
| `inspect.content_not_inlined@1` (item 28, R-10n-2, D-308 (a)) | 42 strings not inlined (24 parts, 18 Json values), info issue `inspect.content_not_inlined` |
| D-307 | `task.attack_id` unrecorded; `attack_type` in `ext.inspect.sample_metadata`; SEM skipped |
| D-309 | no real fixture committed |
| `artefacts.toml` | **no ATIA entry** (every `inspect.art.*` is scoped to other sources) |
| CD-24 (open, RD-2) | score events have no `scorer` (< 0.3.217) → judgement named `score` + bench duplicate |
| CD-25 (open, RD-2) | local-offset timestamps (−04:00) → `t` declared `not_recorded` with `t.raw`, span ends dropped, no time edges |
| Producer 0.3.112 has no `+g` commit | item-12/U6 rules resolve to their `_unverified` twins (inspect.rules.toml l.474-477) |

## 5. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §1; files, members, samples per log, status |
| L1-02 strict parse | yes | headers and samples; large base64 strings (up to about 3 MB); expect 0 failures |
| L1-03 encodings | yes | expect 0 in harness fields; any zero-width/bidi in user text is benchmark content (silent-character attack), counted, not a defect |
| L1-04 duplicates | yes, within part | re-runs: same sample ids and media hashes across logs expected; byte-identical members not expected. Cross-corpus: n/a (no other ATIA source) |
| L1-05 arm coverage | yes (attack_type × log) | defence n/a; one model |
| L1-06 secrets/paths | yes | counts and pointers only; header dataset location is a Windows path without an account name; Files API URIs are not secrets |
| L1-07 timestamps | yes | all with offset −04:00; range inside 2025-07-17T05:47Z..09:00Z |
| L1-08 degenerate | yes | 2 errored samples; 42 samples without a tool call are a valid outcome, not degenerate |
| L2 A2 error classes | yes | 2 error events (`inspect.unmapped_event`) |
| L2 A3 PROV classes | yes | expect the time class (CD-25: no time edges); 0 dangling/missing results |
| L2 evidence classes | yes | D/I/O; `_unverified` twins expected for the item-12/U6 rules |
| L2 degenerate / `adapter_defect` | yes | expect 0 |
| L2 identity | yes | model `google/gemini-2.0-flash` (`model_roles` exists at 0.3.112 but is expected empty, since `main.py` passes only `model=` (corrected wording) → `eval.model`), no judge model, scorer `harmful_tool_invoked` |
| L2 redaction | check only | no redact table; expect 0 account segments |
| L2 withholding | no | no withhold table; check nothing is withheld |
| L2 SEM | no | no semantics profile (D-307) |
| L2 outcome sanity | yes | overall arm only for a verdict (§3) |
| L2 determinism | yes | second import with another `--jobs`, byte-identical |

## 6. Hypotheses (falsifiable, thresholds)

| Id | Lead | Expectation | Fails if |
|---|---|---|---|
| H-01 | — | 5 files / 162,365,512 B; 143 members; 123 sample members, epoch 1 only; per log 25/19/19/25/35 | any count differs |
| H-02 | L-03 | distinct sample ids ≤ 35; the two 25-sample logs have the same 25 ids; each 19-sample log's ids ⊂ those 25 | otherwise |
| H-03 | L-04 | the 2 `error` logs are the 19-sample logs, each with exactly 1 errored sample; both errored samples have `attack_type` `Summarize_Image` | otherwise |
| H-04 | L-01, L-02 | `attack_type` counts None 25 / Summarize_Audio 49 / Summarize_Image 39 / Summarize_Video 10; no other label; media kind matches the label in 123/123 | any difference |
| H-05 | L-12 | recount from `/scores/harmful_tool_invoked/value`: C = 59 of 121; per type 15/30/7/7; header accuracy of each success log = its own recount ±0.0005 | any count differs |
| H-06 | — | score C ⇔ an assistant tool call names a tool in `harmful_tools`: 121/121 agree; 81 samples with one call, 42 with none | ≥ 1 disagreement |
| H-07 | L-07 | every `tool_call.id` equals its `function` (81/81) | ≠ 81 |
| H-08 | L-08 | image request copies carry raw base64 under `inlineData.data` and 0 `BASE_64_DATA_REMOVED` markers; audio/video requests carry Files API URIs (`fileData`), no audio/video base64; 18 request strings > 1 MiB | any marker, any audio/video base64 in a request, or ≠ 18 |
| H-09 | L-09 | every model request has all 5 safety settings `BLOCK_NONE` | any other value |
| H-10 | L-10 | header model `google/gemini-2.0-flash` in 5/5; any `modelVersion` in responses is a single value | > 1 value |
| H-11 | L-05 | 100% of event/sample timestamps parse and carry −04:00; 0 `Z`/`+00:00`; within 2025-07-17T05:47Z..09:00Z | otherwise |
| H-12 | L-05 (CD-25) | on `065b0d36`: every timed AER record has `t.raw` and `not_recorded` on `/t/start` (and `/t/end` where present); 0 `after {b: time}` edges | any UTC `t.start`, or any time edge |
| H-13 | L-06 (CD-24) | on `065b0d36`: exactly 2 judgements per scored sample (`score` and `harmful_tool_invoked`), with equal values; 0 for the errored samples | other count, or the values differ |
| H-14 | — | the item-12/U6 rules are cited only through their `_unverified` twins (0 citations of the D-class originals) | any D original cited |
| H-15 | — | L2 sample (30): 0 failures, 0 degenerate, 0 `adapter_defect`; issues only `inspect.unmapped_event` (≤ 2), `inspect.content_not_inlined` (info) | any other issue code |
| H-16 | — | 0 account paths (`C:\Users\<x>`, `/Users/<x>`, `/home/<x>`) in harness fields of the raw data; 0 in AER/PROV | ≥ 1 (security report at once) |
| H-17 | — | 0 secret-shaped strings (API keys, bearer tokens) in raw or AER | ≥ 1 |
| H-18 | L-03 | 0 byte-identical sample members; trajectory fingerprints may repeat across re-runs of one id (counted, not a defect); 0 repeats across different ids | a byte-identical member, or a repeat across different ids |
| H-19 | — | determinism: two scratch imports (different `--jobs`) byte-identical; `recompute --dry-run` 0 differences | any difference |
| H-20 | — | overall ASR on the 30-sample draw within 15 points of 0.488 and its Wilson 95% interval contains 0.488 ±5 points | otherwise → finding |

## 7. Expected movement (no E2 baseline; against the phase-10n trial on `3cacde6`)

| Change (source) | Expected on this corpus |
|---|---|
| Item 28 (`f0da0ad`, D-308 (a)) | 42 strings not inlined: 24 parts become `blob`/`other` parts with `{sha256, bytes, media}`, 18 `params.transmitted` values `{not_inlined}`; AER smaller; the D-308 import blocker is satisfied |
| Item 12, U6-a/b (D-374/D-375) | harness association of the run and spans through `_unverified` twins; input message `actor: bench` through its twin; `/params/transmitted` retention through its twin |
| Item 30 (D-31) | AER `rules` declares `inspect` at its current version; every digest differs from the 10n trial |
| R-10p-2 / D-182 | agent model from `model_roles` if present, else `eval.model`; no redaction (no table) |
| Items 7, 80, BF-21/22 | no body change expected (no lone surrogates, no sandbox events) |
| CD-24, CD-25 | **not on `065b0d36`**: no movement now; when they land, judgements halve to 1 per scored sample and every `t` becomes UTC with time edges (a later regen item) |

## Fact-check (2026-10-14, desk only, no raw data read)

Checked against the GitHub API (repository, commits, recursive tree and files at `cc71caf5`), the fork
`danieljson15/atia_benchmark@6b8feb4c` (`parsed/rollups/*.csv`, `parsed/eval_summary.csv`, `report.py`,
`parse_eval_zip.py`, `taxonomy.yaml`), inspect_ai at `a61f8517` (`google.py`, `log/_transcript.py`, `log/_log.py`,
`solver/_solver.py`) and its CHANGELOG, the Gemini 2.0 Flash model page, and our own profile, registry, census
(phase 10n §5), regen-batch item 28, review-core-d CD-24/CD-25 and `tools/precheck/l1_families.py`. Details in
`research.json` → `fact_check`.

**Confirmed.** The pin and history: 6 commits, every later commit touches only README.md or LICENSE, 0 issues, tags or
releases. The tree: 5 log blobs, 162,365,512 B, with the listed sizes. LICENSE: MIT, Matthew Nguyen, sha256 equal to
the profile's, absent from the root commit. The requirements pins, scorer and model constant. Every §3 number:
by_attack 25/0.6, 49/0.6122, 39/0.18919, 10/0.7, by_modality 123/0.48760, samples per log 25/19/19/25/35. The derived
counts 15/30/7/7 = 59/121 are the only integer solutions, so both unscored rows fall in `Summarize_Image` in the fork's
parse. The pandas mean skips the NaN rows. Harness claims (1)-(8): the version each feature arrived in, the BLOCK_NONE
defaults, the `inline_data`-only filter (unchanged at HEAD), images inline and audio/video by URI, tool-call
id = function name. Gemini 2.0 Flash shut down on 1 June 2026. L2 strata `("task",)`. No ATIA entry in any
`artefacts.toml`. The census figures match their sources.

**Corrected.** (1) The third log's blob id is `55136410…`, not `5513641e` (§1). (2) `research.json` said the single
`generate()` gives at most one assistant turn. Wrong: at 0.3.112, `generate()` defaults to `tool_calls="loop"`, so a
sample with a tool call should make a second model call. This contradicts the census wording "a single assistant
turn". It is recorded as an open question for L1. No expected count was changed, and the L-08 explanation of 18
versus 20 is now marked speculative. (3) `model_roles` wording (§5). (4) Mapper line `_RFC3339_UTC` is l.57. (5) The
README's own sample schema lists `attack_type` values including `Qi et al. 2023` and `None` (L-02, L-11).

**Unverifiable.** That no paper exists (search only). That the fork's `logs_json` match the pinned blobs byte for byte.
The census-only counts (members, log status, tool calls, media, strings over 1 MiB), which are not recomputed before the
checks, by rule.
