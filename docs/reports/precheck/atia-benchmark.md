# Pre-check dossier: `atia-benchmark`

## 1. Header

| | |
|---|---|
| Corpus | `atia-benchmark` (own permissive corpus, MIT, Matthew Nguyen) |
| Parts | `atia-benchmark · logs` (1 part, registry `planned`) |
| Family / profile | `inspect` / `atia-benchmark@1` (dialect `inspect.eval` v2, no semantics profile, D-307) |
| Pin | git `mattngyn/atia_benchmark` @ `cc71caf5`, tree `logs` (5 blobs, 162,365,512 B; blob ids 8b5bca05, a01b477f, 55136410, 7ab115ca, ed49f4ef) |
| Code commit | `d97d3a57` (L1 and L2, batch `wave4`, steps l1, l1_10, sample, import_j2, import_j1, check all rc 0; tracked_changes false) |
| Kind | wave 4, first examination (not in FA or E2, never stored) |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (batch), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), examiner (this dossier), adversarial verifier 2026-10-21 (7/7 confirmed) |
| Data | [`data/atia-benchmark/`](data/atia-benchmark/): `research.json`, `l1-logs.json`, `l1-10-logs.json`, `l2-sample-logs.json`, `l2-logs.json`, `code-logs.json`, `exam.json`, `findings.json`, `os-population.json`, `raw-census.json`, `score-polarity.json`, `aer-pass.json`, `exam-scripts/` |

- Code identity, part `logs` ([`code-logs.json`](data/atia-benchmark/code-logs.json)): commit `d97d3a57` (tracked_changes false); engine code expand `3b1d412bb77a`, aer `856b7a09e0cf`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `inspect.eval@0.1.0` `1867569d63c9`; profile sha256 `e610a5bc0949`; rules aer 1 / inspect 2 (inspect `7643c8ae876c`); prov rules `79b0a1e78dc7`; lockfile `b0455f1058c8`, limits `5d6dbb210259`; CPython 3.14.8.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Source repository | https://github.com/mattngyn/atia_benchmark @ `cc71caf5` (6 commits; later commits touch README/LICENSE only; 0 issues/tags/releases) | the data (`logs/*.eval`), scorer `harmful_tool_invoked`, README design |
| Third-party fork | https://github.com/danieljson15/atia_benchmark @ `6b8feb4c` (`parsed/rollups/`) | only outcome reference (reproduction target, not independent) |
| Paper | none (arXiv and web search, 2026-10-14) | n/a |
| Producer | inspect_ai 0.3.112 (`a61f8517`) | harness; Google provider, `generate()` with `tool_calls="loop"` |
| Model | `google/gemini-2.0-flash` (shut down 2026-06-01) | not re-runnable |

Data-versus-documentation notes (checked against the data):

- The README describes 10 harm categories, 6 jailbreak methods and 500+ attacks. The logs hold 1 task (`account_takeover_suite`), 4 `attack_type` labels and 35 distinct samples (PC-07, pre-registered as expected missing).
- The header `revision` commits that wrote the logs (`1192ce1` in 4 logs, `1a88256` in 1 log) are not in the public history, so the run-time scorer cannot be recovered.
- The fact-check's open question is answered: each of the 81 samples with a tool call makes **2** model calls (the tool-call loop), and the 42 without one make 1. The census wording "single assistant turn" is wrong (PC-02).
- The 18 request strings over 1 MiB, against 20 image message parts, fit the 2 errored image samples, which have no request copy (H-08).
- The two status-`error` logs score with inverted polarity (PC-01). The fork rollup reproduces the logged mix exactly.

## 3. Expectations

Pre-registration: [`prereg/atia-benchmark.md`](prereg/atia-benchmark.md), committed in `fd75f8a3` (2026-10-14) before any check of this corpus ran. Amendments 2–4 (README §8) apply. Under amendment 2.3 the sample unit is the file, so the part's 5 `.eval` units (< 30) were imported whole: **123 executions, not the pre-registered 30-sample draw**. As a result, L2 covers the whole population.

| H | Result | Note |
|---|---|---|
| H-01 | refuted as worded | 5 files / 162,365,512 B, 123 samples, epoch 1, per log 25/19/19/25/35 as expected; archive members **155**, not 143 (PC-02) |
| H-02 | supported | 35 distinct ids; the two 25-logs have the same ids; both 19-logs are subsets |
| H-03 | supported | error logs = the two 19-sample logs, 1 errored sample each, both `Summarize_Image` |
| H-04 | supported | None 25 / Audio 49 / Image 39 / Video 10; no other label; media kind = label 123/123 |
| H-05 | supported | C 59 / I 62 of 121; per type 15/30/7/7; header accuracy 0.6 / 0.6 / 0.628571 = own recounts 15/25, 15/25, 22/35 |
| H-06 | **refuted** | 36 of 121 disagree, all in the 2 error logs (18/18 each); 81 one-call and 42 no-call samples as expected (PC-01) |
| H-07 | supported | `tool_call.id` = `function` 81/81 |
| H-08 | supported | 0 `BASE_64_DATA_REMOVED`; image `inlineData` 37 parts; audio `fileData` 98, video 17; 0 audio/video base64; 18 request strings > 1 MiB |
| H-09 | supported | 202/202 requests with 5 × `BLOCK_NONE` (the 2 errored calls have no request) |
| H-10 | supported | header model 5/5; `modelVersion` `gemini-2.0-flash` 202 (2 errored calls: none) |
| H-11 | supported | 2,688/2,688 event timestamps carry −04:00, inside the range; 0 `Z` |
| H-12 | supported in substance | 0 UTC `t.start`, 0 time edges, `/t/start` not_recorded 1,223/1,223; `t.raw` on 1,100/1,223 (the other 123 are duration-only sample scopes, PC-02) |
| H-13 | supported | 2 judgements per scored sample (`score`, `harmful_tool_invoked`), equal 121/121; 0 for the 2 errored |
| H-14 | supported | twins only: `sample_input_from_benchmark_unverified` 123, `sample_run_by_harness_unverified` 611, `tool_span_by_runtime_unverified` 81; 0 D originals |
| H-15 | supported (on 123) | 0 failures, 0 degenerate, 0 `adapter_defect`; issues `inspect.unmapped_event` 2, `inspect.content_not_inlined` 24 |
| H-16 | supported | 0 account paths in raw headers/samples or in AER/PROV; dataset location is a Windows path with no account name (5/5) |
| H-17 | refuted as worded, supported in substance | secret-shaped matches occur only inside base64 media payloads; 0 in free text (PC-03) |
| H-18 | supported | 0 byte-identical members; 19 trajectory groups / 61 units, each 1 sample id across logs; 0 across ids |
| H-19 | supported | j2 vs j1 386/386 files identical, index identical; recompute 123 identical |
| H-20 | supported | 59/121 = 48.76 % [40.03, 57.57] vs 48.76, gap 0 (on all 123) |

Expected movement (§7): item 28 is seen (24 parts + 18 transmitted values not inlined, rule `inspect.content_not_inlined@1`). The item-12/U6 twins are seen. Rules declare inspect 2. Two items were **not tested**: the `/params/transmitted` retention twin (no AER rule ref of that name in this pass) and the digest comparison with the 10n trial (no trial corpus at hand).

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: the git pin at `cc71caf5` (`--use-pin`, cache clone), tool `l1_scan` at `d97d3a57`, 17 s. Batch `wave4`, all rc 0.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 5 walked = 5 selected; 0 excluded/rejected; 162,365,512 B; units 123 = registry 123 = census. Members (product listing) 155 = 123 samples + `header.json` 5 + `summaries.json` 5 + `_journal/start.json` 5 + `_journal/summaries/*` 14 + `reductions.json` 3. Status success 3 / error 2 | members ≠ 143 (PC-02) |
| L1-02 parse | strict ok 5/5; 0 duplicate keys, non-finite, big ints, surrogates, BOM, trailing data, truncation | as expected |
| L1-03 encodings | ANSI/ESC 6 strings and escaped newlines 12, in 2 artefacts, all at `*/error/traceback(_ansi)` (inspect's ANSI traceback field, by design); 0 zero-width, bidi, tag, U+FFFD, mojibake, so no silent-character content | prereg said 0 in harness fields (PC-02, wording) |
| L1-04 duplicates | byte-identical 0; trajectory-identical (CC-01) 19 groups / 61 of 123 units, every group one sample id re-run across logs (facets differing: log 19, status 13); `_cross/l1-xdup.json`: 0 cross-part, 0 cross-corpus | as expected |
| L1-05 arms | 1 stratum (`task=account_takeover_suite`); model 1, producer 0.3.112 5/5; attack_type 25/49/39/10; media none 25 / audio 49 / image 39 / video 10 | as expected; README design not covered (PC-07) |
| L1-06 secrets/paths | `secret:google-api-key` 9 strings / 5 artefacts, `openai-api-key` 6 / 3, `hf-token` 3 / 3, all at `samples:/attachments/<key>`; every match lies inside a base64 run (examiner); 0 account paths; L1-10 0 files screened (the pin tree holds no context files) | PC-03 (not secrets) |
| L1-07 timestamps | `/events/*/timestamp` 2,405 and `/completed` 283, header 15, journal 5: 100 % offset form, 0 parse failures, one day 2025-07-17; units non-monotone 81 (= the 81 two-call samples) | quirk `event_order_not_time_order` (PC-06) |
| L1-08 degenerate | unit flags `sample_error` 2; artefact flag `secret_like` 5 (PC-03); 0 empty/tiny/zero-message; the 42 no-call samples are valid outcomes | as expected |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`l2-sample-logs.json`](data/atia-benchmark/l2-sample-logs.json) (sha256 `c5b66871…`): 5 of 5 file units (< 30, amendment 2.3), giving 123 executions (per label 25/19/19/25/35) |
| Import | 2 scratch corpora (`l2-logs-j2.partial`, `-j1.partial`) at `d97d3a57`: 123/123 mapped, ok 123, completeness verified_complete 123, 0 degenerate, 0 `adapter_defect`, 0 failed |
| Validation | tiers aer, sem, prov, linkage: 123/123 pass, 123 reproduced, linkage 123/123 (100 %); SHACL not implemented (skipped); regression n/a |
| Recompute | `--dry-run`: 123 identical, 0 changed, 0 unexplained |
| Verify chain | 0 failures; only `checksums.absent` (working tree); 133 raw objects rehashed |
| Determinism | j2 vs j1: 386/386 files, 0 differ, index identical |
| A2 error classes | register `map.inspect.unmapped_event` 2 (the 2 error events), `map.inspect.content_not_inlined` 24 (info) |
| A3 PROV issues | 0 dangling/missing/invented over 15,326 statements / 19,642 relation arguments; 285 messages with `generated_by`, 204 model calls with input, 81 tool executions with call; 0 time terms (`prov:startedAtTime`/`endedAtTime`), 732 `apv:afterCausal` only (CD-25) |
| Evidence classes | PROV core D 4,519 / O 3,728 / none 81; inference I 815, all **twin** (0 native, 0 mixed); top O 5,733 / none 450 |
| Judgements (OS-2) | raw = AER in 123/123 (C 59, I 62, unscored 2); 2 per scored sample (CD-24) |
| Identity | agent `google/gemini-2.0-flash` 123/123; served `gemini-2.0-flash` 202 + requested echo 2 (errored); defence none, attack_id none (D-307; `attack_type` in `ext.inspect.sample_metadata`); suite `account_takeover_suite`, benchmark `atia`; no judge model; 0 unresolved, 0 mismatches. Harness `/code/commit` ambiguous 123 (two revision commits) |
| Redaction | 254 files scanned, 0 account paths; secret-shaped hits AER 60 / PROV 54, all inside base64 payloads (PC-03) |
| Withholding | n/a (no `[withhold]` in the profile); nothing withheld |
| CC-07 | n/a: an inspect-format corpus, not AgentDojo (#181/#161 do not apply) |

## 6. Outcome comparison

Level 1 (raw, 123) and Level 2 (AER, the same 123) give identical counts. Reference: the fork rollup (no author numbers). Gap rule: > 15 pp on n ≥ 20, or > 5 pp outside the Wilson 95 % interval. Rows: [`os-population.json`](data/atia-benchmark/os-population.json).

| Arm (gemini-2.0-flash / account_takeover) | n | Metric | Rate (Wilson 95 %) | Reference | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|
| all | 121 | ASR logged | 48.76 (59/121) [40.03, 57.57] | 48.76 | 0.00 | match; mixes polarities (PC-01) |
| None | 25 | ASR logged | 60.00 (15/25) [40.74, 76.60] | 60.00 | 0.00 | match |
| Summarize_Audio | 49 | ASR logged | 61.22 (30/49) [47.25, 73.57] | 61.22 | 0.00 | match |
| Summarize_Image | 37 | ASR logged | 18.92 (7/37) [9.48, 34.20] | 18.92 | 0.00 | match |
| Summarize_Video | 10 | ASR logged | 70.00 (7/10) [39.68, 89.22] | 70.00 | 0.00 | n < 20 |
| success logs (3) | 85 | ASR logged | 61.18 (52/85) [50.55, 70.84] | — | — | logged = tool-call 85/85 |
| error logs (2) | 36 | ASR logged | 19.44 (7/36) [9.75, 35.03] | — | — | inverted 36/36 (PC-01) |
| all, tool-call re-score (info) | 121 | ASR | 66.94 (81/121) [58.15, 74.69] | 48.76 | +18.18 | not the logged metric (PC-01) |
| None, re-score (info) | 25 | ASR | 100.0 (25/25) [86.68, 100] | 60.00 | +40.00 | not the logged metric |
| Summarize_Audio, re-score (info) | 49 | ASR | 100.0 (49/49) [92.73, 100] | 61.22 | +38.78 | not the logged metric |
| Summarize_Image, re-score (info) | 37 | ASR | 0.0 (0/37) [0.00, 9.41] | 18.92 | −18.92 | not the logged metric |
| Summarize_Video, re-score (info) | 10 | ASR | 70.0 (7/10) [39.68, 89.22] | 70.00 | 0.00 | n < 20 |

The logged metric reproduces the reference in every arm. The flagged gaps are in the info rows, and the investigation explains them: in the two status-`error` logs, `harmful_tool_invoked` is C exactly when no harmful tool was called (PC-01). The mapping does not cause this (raw = AER).

## 7. Findings

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-atia-benchmark-01 | Score polarity inverted in the 2 error logs (36/36 scored samples), success logs consistent 85/85; logged ASR 48.76 % vs tool-call 66.94 % | source-defect (R1; no catalogue entry) | S2 | confirmed | Keep logged values; catalogue entry (below); disclose; re-score only as a labelled column |
| PC-atia-benchmark-02 | Our docs vs data: census members 143 (data 155), "single assistant turn" (81 two-call samples); prereg H-12 / L1-03 wording; 30-draw vs whole-part import | documentation-mismatch (R4) | S3 | confirmed | Route to the phase-10n census owner |
| PC-atia-benchmark-03 | Secret-shaped matches (L1 18 strings, AER 60, PROV 54) only inside base64 media payloads, 0 free text | analysis-artefact (R5) | S3 | confirmed | Detector skips base64 runs in a later tool version; follow-up: confirm `release_scan` does not gate on them |
| PC-atia-benchmark-04 | `l2_check` outcome block is AgentDojo-only (arms `{}` here); examiner recount | analysis-artefact (R5) | S3 | confirmed | Post-check reuses `exam-scripts/aer.py` |
| PC-atia-benchmark-05 | [CD-24, CD-25] duplicate judgement (2 × 121, equal) and local-offset times declared not_recorded, 0 time edges | expected-known (R2, CD-24/CD-25, RD-2) | S3 | confirmed | None now |
| PC-atia-benchmark-06 | Profile quirks / items 25, 28 / D-307: 2 unmapped error events, 81 non-monotone units, 81 tool links by `tool_call_id`, 42 not-inlined strings (24 executions), attack_id unrecorded | expected-known (R2) | S3 | confirmed | None |
| PC-atia-benchmark-07 | README design (10 categories, 6 methods, 500+ attacks) vs logs (1 task, 4 labels, 35 samples, 1 model) | documentation-mismatch (R3; no paper) | S3 | confirmed | Disclose coverage in the datasheet |

PC-01 detail: in the error logs (01-51-09, 01-52-51), 29 samples score I although they made the harmful call, and 7 score C although they made none. The score's `answer` field lists the same sample's `ToolCall` (or `[]`), so this is inverted polarity, not a misattributed sample. Each of the 81 calls names the sample's only offered tool. Both error logs share revision `1192ce1` with two success logs, so a working-tree or scorer change at run time is the likely cause, but it cannot be verified (the commit is not public). No CC item covers this, because it is not AgentDojo-format.

Verifier (2026-10-21, own scripts, counts only): PC-01 re-run independently. The two error logs (created 01:51:09 and 01:52:51) sit between two consistent success logs of the same revision `1192ce1` (01:47:02, 01:54:19) and declare the same scorer with the same options. Rejected alternatives: a stricter positive-polarity scorer (cannot score C on the 7 no-call samples), misattributed answers, differing `harmful_tools` metadata (1 harmful tool = the only offered tool, same metadata keys in all logs), inspect re-scoring (1 score event per sample, equal). Wilson intervals recomputed. PC-02: 155 member rows; the 81 one-call samples have 2 assistant messages and 2 model events. PC-03: an independent, looser pattern set finds every match inside a pure-base64 400-char window at `attachments`, 0 elsewhere. PC-07 is a coverage disclosure (the README describes the repository's 10 datasets, not the logs), kept as R3 S3. Readiness unchanged.

No mapping defect and no security finding (0 account paths; the secret shapes are base64 noise). CC-03: 0 hits. CC-11: no context artefacts. CC-07, CC-09, CC-10: n/a (inspect). PC-03/PC-04 (R5) do not count in the readiness verdict.

Proposed `artefacts.toml` entry (text only; route to the inspect family owner):

```toml
# [[artefact]] id = "inspect.art.atia_error_log_score_polarity"
#   scope.sources = ["atia-benchmark"]; scope.profiles = ["atia-benchmark"]
#   refs = ["https://github.com/mattngyn/atia_benchmark"]
expected = [
  { snapshot = "atia-benchmark:logs", count = 36, unit = "executions", basis = "pre-check PC-atia-benchmark-01: harmful_tool_invoked is the complement of the tool-call condition in all 36 scored samples of the two status=error logs (29 I with a harmful call, 7 C with none); success logs 85/85 consistent", status = "proposed" },
]
```

Items for AGENTS.md section 12:

- PC-01: the ATIA logged ASR of 59/121 (48.76 %, which the fork rollup reproduces) mixes two scorer polarities. The 36 scored samples of the 2 error logs are inverted. The consistent tool-call figure is 81/121 (66.94 %). Disclose; the logged values stay primary; no exclusion.

## 8. Recommendations and readiness

1. Route the PC-01 catalogue entry to the inspect family owner, and disclose PC-01 next to any ATIA ASR in the datasheet or manuscript. Logged values are primary; the re-score goes in a separate labelled column.
2. PC-02 goes to the phase-10n census owner (member count, two-call wording).
3. Follow-up (heavy, not run): a sealed scratch copy plus `release_scan`, to confirm that the base64 secret-shaped matches (PC-03) do not block the deposit. If they do, allowlist base64 media payloads in the scan, with no data change.
4. No exclusion of any data.

**Readiness: `ready-with-caveats`.** The part imports correctly and deterministically: 123/123 mapped and validated, recompute 0 unexplained, j1/j2 byte-identical (386 files), raw = AER judgements 123/123, identity 0 mismatches, 0 account paths. One caveat: PC-01, an S2 source-defect disclosure (verifier-confirmed). PC-02, PC-05, PC-06 and PC-07 are S3 records. PC-03 and PC-04 are R5 and not counted.

## 9. Reproduction

Batch (wave 4; plan entry in `tools/precheck/plans/wave4.toml`: `corpus_id = source = "atia-benchmark"`, `part = "logs"`, `l1 = ["--use-pin"]`):

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave4 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave4.toml
```

Steps (W = `~/.agentprov/migration-work/precheck/atia-benchmark`, D = `docs/reports/precheck/data/atia-benchmark`):

```bash
uv run python tools/precheck/l1_scan.py --source atia-benchmark --part logs --corpus-id atia-benchmark --jobs 2 --emit-fp --use-pin
uv run python tools/precheck/l2_sample.py select --units W/l1-units-logs.jsonl --source atia-benchmark --part logs --corpus-id atia-benchmark --out D/l2-sample-logs.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-logs.json --corpus W/l2-logs-j2 --source atia-benchmark --part logs --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-logs.json --corpus W/l2-logs-j1 --source atia-benchmark --part logs --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-logs-j2.partial --out D/l2-logs.json --sample D/l2-sample-logs.json --l1-units W/l1-units-logs.jsonl --compare-with W/l2-logs-j1.partial --jobs 2
```

Examiner scripts (read-only; raw objects through `agentprov.ingest.loaders.strict_json_loads`, AER through `agentprov.aer.reader`; outputs under `W/exam/`, counts-only copies in D):

```bash
uv run python -I D/exam-scripts/raw.py W/l2-logs-j2.partial/raw W/exam/raw.json   # H-01..H-11, H-16..H-18, L1-06 context -> D/raw-census.json
uv run python -I D/exam-scripts/h06.py W/l2-logs-j2.partial/raw W/exam/h06.json   # PC-01 polarity breakdown -> D/score-polarity.json
uv run python -I D/exam-scripts/aer.py W/l2-logs-j2.partial W/exam/aer.json       # H-12..H-15, OS-2, identity, PROV time terms -> D/aer-pass.json
```
