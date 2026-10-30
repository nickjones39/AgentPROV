# Pre-check dossier: `kexin-xu-01-agentharm`

## 1. Header

| | |
|---|---|
| Corpus | `kexin-xu-01-agentharm` (restricted use: MIT + AgentHarm AI-safety clause; logs carry no licence of their own) |
| Parts | `logs` (1 part; registry `planned`, 2,825 samples, census basis) |
| Family / profile | `inspect` / `kexin-xu-01-agentharm@1` (dialect `inspect.eval`, semantics `inspect.agentharm@2`) |
| Pin | git `Kexin-xu-01/agentharm` @ `859c34f4` (2026-09-26T22:39:28Z, repository HEAD), tree `logs/` 68 blobs |
| Code commit | `d97d3a57` (L1, sample, both imports and check, batch `wave4`, every step rc 0, tracked changes false) |
| Kind | wave 4, first examination (not in FA or E2); no stored corpus |
| Sample frame | the 18 local-checkpoint logs are excluded (`--exclude-facet model=<local-path-model>`, README §8 amendment 2.5) |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (L1, L2), 2026-10-21 (examination) |
| Agents | researcher and fact-checker (prereg), batch runner, examiner (this dossier), adversarial verifier (2026-10-21: 10 confirmed, 1 refuted; PC-02 corrected, PC-07 S2 -> S3) |
| Data | [`data/kexin-xu-01-agentharm/`](data/kexin-xu-01-agentharm/): `research.json`, `l1-logs.json`, `l1-10-logs.json`, `l2-sample-logs.json`, `l2-logs.json`, `code-logs.json`, `exam.json`, `findings.json`, `os1-population.json`, `raw-hypotheses.json`, `l2-aer-pass.json`, `exam-scripts/` |

- Code identity, part `logs` ([`code-logs.json`](data/kexin-xu-01-agentharm/code-logs.json)): commit `d97d3a57` (tracked_changes false); engine code expand `3b1d412bb77a`, aer `856b7a09e0cf`, sem `a8141c23af13`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `inspect.eval@0.1.0` `1867569d63c9`; profile sha256 `df445ef1dac5`, rules aer 1 / inspect 2, SEM `inspect.agentharm@2` `2fca152bb906`; lockfile `b0455f1058c8`, limits `5d6dbb210259`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Repository | https://github.com/Kexin-xu-01/agentharm @ `859c34f4` | the data and the only documentation (`analysis/*.md`), which gives the outcome references |
| Benchmark paper | https://arxiv.org/abs/2410.09024 (v3, ICLR 2025) | context only (other models, all 11 categories) |
| Harness | `inspect_ai` 0.3.263, `inspect_evals` 0.20.0 (`360484a`) | producer; agentharm files blob-identical to upstream |
| Upstream issues | inspect_evals [#2439](https://github.com/UKGovernmentBEIS/inspect_evals/issues/2439), #2212, #2312, #2146 | #2439 shows up in the data (PC-02) |
| Data record | none | – |

Data-versus-documentation notes (checked against the data):

- Every reported refusal count and mean score in the base, v1, v2 and v3 tables comes out exactly from the raw scores (section 6).
- `logs/` holds runs that no table reports: a second Gemini 2.5 Pro harmful log, 3 error logs and 2 unfinished logs (PC-03).
- The patched scorer leaves no trace in the log headers; only the directory name (raw origin label) tells the variants apart (PC-07).
- The research lead L-14 got the source of the logger events wrong: they come from vLLM, not Claude (PC-04).

## 3. Expectations

Pre-registration: [`prereg/kexin-xu-01-agentharm.md`](prereg/kexin-xu-01-agentharm.md), committed in `fd75f8a3` (2026-10-14), before any check ran. Amendment 2.5 (frame) applies. Amendment 1 does not apply (no stored corpus).

| H | Result | Note |
|---|---|---|
| H-01 | supported | 68 logs; 66 headers (63 success, 3 error); 2 journal-only; 2,825 samples |
| H-02 | supported | 25/25 error-log samples errored, 0 scored, all 401 |
| H-03 | supported | unfinished logs: gpt-4o agent and judges, harmful, 18 + 10 scored |
| H-04 | supported | one Pro log matches (22, 0.4437); the other gives 18, 0.4505 |
| H-05 | supported | 21 base logs equal the docs (local logs by best assignment) |
| H-06 | supported | v1 20/20, v2 2/2, v3 20/20; v3 values are not v1 values |
| H-07 | supported | content_filter: harmful 8 per run; benign 5 (base, v2) and 4 (v1, v3); refusal = 1 only in v3 |
| H-08 | partly tested | Base Qwen Fraud 6/24 and Cybercrime 3/20 equal the docs; other per-category references not extracted (follow-up 3) |
| H-09 | lead confirmed | finding PC-02 |
| H-10 | supported | headers identical across variants (PC-07) |
| H-11 | supported | 0 `Error in RefusalJudgeLLM` |
| H-12 | supported | 0 violations; upper bound is the pin time (no per-commit history in the cache) |
| H-13 | supported | location in 66 headers + 2 journals; `/eval/model` 18; 0 in derived records (PC-01, PC-09) |
| H-14 | partly | 0 in headers; AER tokens are benchmark fixtures; counts come from another detector |
| H-15 | refuted | 180/196 logger events in vLLM logs (PC-04) |
| H-16 | supported | all L2 counts exact (section 5) |
| H-17 | supported | 63/63 44-sample logs: same 11 ids × 4, Fraud 24 / Cybercrime 20 |
| H-18 | supported | 0 byte-identical files; 230 groups |

Movement since the phase-10h trial (prereg §8) matches the prediction: 40 executions are `known_incomplete` (D-372), with rules inspect 2 and SEM `inspect.agentharm@2`.

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: `--use-pin` fetch cache at `859c34f4`, `l1_scan` at `d97d3a57`, 24.8 s.

| Check | Result (denominator) |
|---|---|
| L1-01 | 68 walked, 68 selected, 0 rejected, 0 auxiliary; 2,825 units = registry figure |
| L1-02 | 68/68 strict ok |
| L1-03 | ANSI/ESC in 3 logs (the error tracebacks); variation selectors in 5 (model text); escape residues and JSON-in-string in tool arguments and attachments; 0 bidi, tag, U+FFFD or mojibake |
| L1-04 | 0 byte-identical groups; 230 trajectory groups (605 of 2,825 units; 2,450 distinct). `l1-xdup`: 49 cross-corpus groups with fragfuse-agentharm (D-181), 0 with the survey; xdup's within-part count is 203 (it uses a different group definition) |
| L1-05 | 52 strata; 0 missing cells. Extra cells as pre-registered: Pro rerun, 3 error logs, 2 unfinished logs |
| L1-06 | account-path classes: home-dir named 58 logs / generic 57, windows-users named 8, users-dir named 3, local-path-model 18. Pointers outside samples: `/eval/dataset/location` only (named 24 + 24 journal, generic 42 + 44 journal) and `/eval/model` 18. Secret shapes: anthropic 3 logs, openai 3, generic assignment 32. 0 operator hits |
| L1-07 | 125,209 event timestamps, all with offset, 0 parse failures, 2026-09-12..09-26; 2,043 of 2,825 units non-monotone (`event_order_not_time_order`); tool-argument dates (2023-2025, 2 naive) are benchmark content |
| L1-08 | no_header 2 logs (28 units); sample_error 25; sample_limit 298 |
| L1-09 / L1-10 | no strays; 0 context files to screen |

## 5. Level 2 (50 non-local logs, whole)

| Item | Result |
|---|---|
| Sample | [`l2-sample-logs.json`](data/kexin-xu-01-agentharm/l2-sample-logs.json): 50/50 logs in 46 strata (frame minus 18 local logs); 2,005 executions + 2 `select.dialect_planned` |
| Import | j2 and j1: mapped 2,005, failed 0, degenerate 0, filtered 18, sealed clean 1,965 / with issues 40 |
| Validate | 2,005 passed, 0 failed (shacl not built, regression n/a); linkage 100 % |
| Recompute dry-run | 2,005 identical, 0 unexplained |
| Determinism | 8,153 vs 8,153 files, 0 differ, index identical |
| Verify chain | 2,005 checked, 0 failed; `checksums.absent` (working tree, expected) |
| A2 | register: `sample_limit` 186, `unmapped_event` 47, `missing_tool_result` 40, `dangling_source_ref` 40; adapter_defect 0; tool_execution ok 7,345 / error 393 / invalid 128 |
| A3 | 0 dangling, missing, invented or forbidden; `time_not_run_scope` 46,130 (informational: inspect events carry their own times) |
| Evidence | inference:I 21,851: unverified twins 19,846, native 0, mixed 0 (producer 0.3.263 is not verified, as expected); core D 232,676 / O 201,211 |
| Identity | 8 agent model ids map 1:1; judge `gpt-4o-2024-08-06` in 1,854 executions. In the 126 judged executions without a judge actor, the raw sample has no refusal explanations (the judge was not called; 12 of them are v3 content-filter refusals), so this is not a mapping gap. The scorer variant is not in the header or an identity facet; it is recoverable from the raw origin path label (PC-07) |
| Mapping check | 48/48 containers: mapped scored / refused / mean equal the L1 raw values (`l2-aer-pass.json`) |
| Redaction | account-path hits in AER for 146 executions and PROV for 47: all benchmark or model content (PC-09, CC-03); 0 hits for the dataset-location account; 0 operator hits; secret shapes are benchmark fixtures (PC-10) |
| Withholding | no policy; nothing withheld (as expected) |
| CC-07 | n/a (not AgentDojo format) |

## 6. Outcome comparison (L1 population = L2, since whole logs are imported; n = 44 per log)

Refusal count k/44 (Wilson 95 %) / mean score against the docs (count, mean). The same values are mapped at L2 for every non-local row.

| Variant | Model | H: k (CI) / mean | doc | B: k (CI) / mean | doc | Verdict |
|---|---|---|---|---|---|---|
| base | Qwen3-14B | 9 (11.2-34.5) / 0.5708 | 9 / 0.571 | 0 (0-8.0) / 0.7165 | 0 / 0.716 | match |
| base | GPT-4o | 20 (31.7-59.9) / 0.4616 | 20 / 0.462 | 0 / 0.8526 | 0 / 0.853 | match |
| base | GPT-4o-mini | 11 / 0.5230 | 11 / 0.523 | 0 / 0.7617 | 0 / 0.762 | match |
| base | Gemini 2.5 Pro (np9GTPhB) | 22 (35.8-64.2) / 0.4437 | 22 / 0.444 | 3 / 0.7481 | 3 / 0.748 | match |
| base | Gemini 2.5 Pro (PFaxbfVw, unreported) | 18 (27.7-55.6) / 0.4505 | – | – | – | extra run, −9.1 pp, inside the CI (PC-03) |
| base | Gemini 2.5 Flash | 26 / 0.3344 | 26 / 0.334 | 0 / 0.7740 | 0 / 0.774 | match |
| base | Flash-Lite | 38 / 0.2346 | 38 / 0.235 | 32 / 0.4542 | 32 / 0.454 | match |
| base | Claude Sonnet 5 | 31 / 0.0909 | 31 / 0.091 | 27 / 0.6100 | 27 / 0.610 | match |
| v1 | 7 API models | all equal | | all equal | | 14/14 match |
| v2 | Claude Sonnet 5 | 30 / 0.0909 | 30 / 0.091 | 4 / 0.6111 | 4 / 0.611 | match |
| v3 | 7 API models | all equal (e.g. Claude 37 / 0.1000, Pro 11 / 0.4698) | | all equal | | 14/14 match |
| base, v1, v3 | runs 40/42/56 (L1 only) | 6/6 cells equal under one assignment | | | | match (identity bucketed) |

Every row is in [`os1-population.json`](data/kexin-xu-01-agentharm/os1-population.json). 44 of 45 API logs equal the docs. The one that differs is the unreported rerun, which the README §4 rule does not flag (−9.1 pp, inside the interval); it was investigated as a count difference (H-04). AgentHarm paper (context only): GPT-4o refusals 48.9 % vs 45.5 % here; the paper covers other categories.

## 7. Findings (verified 2026-10-21)

| Id | Class / sev | Sec | Title (short) | CC | Verdict |
|---|---|---|---|---|---|
| PC-01 | source-defect S2 | **yes** | named third-party account in raw `/eval/dataset/location` of 24 logs (+ journals); 0 in derived records. 6 of the 24 are in the L2 frame, 18 are the local logs | CC-11 vs D-186(c) | confirmed |
| PC-02 | source-defect S2 | no | #2439 bundled `read_file` failures: 556 events (443 on bundled names). Every affected sample is behaviour 43, so the bias is that task 43 cannot be completed (at most 4/44 per log). The 0.155 vs 0.738 contrast is task confounding (within id 43: +0.07) | R1 | confirmed, corrected |
| PC-03 | documentation-mismatch S3 | no | unreported runs: Pro rerun, 3 auth-error logs (25), 2 unfinished (28) | R3 | confirmed |
| PC-04 | documentation-mismatch S3 | no | logger events come from vLLM logs (180/196), not Claude | R4 | confirmed |
| PC-05 | documentation-mismatch S3 | no | no `inspect.art.*` scope covers this source | CC-09 analogue | confirmed |
| ~~PC-06~~ | refuted | no | census 530 / 127 are tool-message counts (recount 530 / 127); 556 / 128 are tool events. A difference of basis, not a mismatch | R4 | refuted |
| PC-07 | source-defect S3 | no | patched scorer variant not in the header or an AER identity facet; recoverable from the raw origin path label (50/50 logs). No metric bias | R1 | confirmed, S2 -> S3 |
| PC-08 | expected-known S3 | no | 18 local-checkpoint logs only at L1 (D-182 table pending; it must also redact `/eval/dataset/location`) | R2 | confirmed |
| PC-09 | expected-known S3 | no | account-path shapes in AER/PROV are benchmark or model content | CC-12c / CC-03 | confirmed |
| PC-10 | expected-known S3 | no | secret-shaped tokens are benchmark fixtures | CC-13 fixture, D-188 (AER only, PROV 0) | confirmed |
| PC-11 | analysis-artefact S3 | no | `l2_check` outcome arms are empty for inspect | R5 | confirmed |

Proposed `artefacts.toml` entries (text in `findings.json`): widen the scope of `inspect.art.bundled_file_not_found` (PC-02) and add a new `inspect.art.patched_scorer_unrecorded` (PC-07). The PC-05 scope widening goes to the inspect family owner.
AGENTS.md §12 items: PC-01 (security route), PC-02, PC-05, PC-07.

## 8. Recommendations and readiness

**ready-with-caveats.** Validation, recompute, determinism and the mapping check are clean, and every documented number comes out of the data. The caveats:

1. PC-01 goes to the orchestrator now. The open decision is whether CC-11 (withhold at seal) or D-186(c) (ship raw unchanged) applies to these 24 primary logs. 6 of them are imported, and a withhold must also cover their extracted header member objects in the raw store. The other 18 are the local logs, and their D-182 table must cover `/eval/dataset/location`.
2. Disclose #2439 (PC-02) in the datasheet as "behaviour 43 (4 ids) cannot be completed; at most 4/44 of each log's mean". Do not use the sample-level 0.155 vs 0.738 contrast. Disclose the scorer variant (PC-07) too: take it from the origin path, and never pool across subdirectories without it.
3. The 18 local logs need the D-182 redact table, then a supplementary L2 run.

No data is recommended for exclusion.

## 9. Reproduction

```bash
# from the worktree root; scratch under ~/.agentprov/migration-work/precheck/kexin-xu-01-agentharm/
W=~/.agentprov/migration-work/precheck/kexin-xu-01-agentharm; D=docs/reports/precheck/data/kexin-xu-01-agentharm
B="$HOME/.agentprov/cache/git/github.com/Kexin-xu-01/agentharm.git 859c34f411fdf8d6a01670da2d2460d21e739e7e"
# batch (already run): tools/precheck/run_batch.py --plan tools/precheck/plans/wave4.toml (l1 --use-pin; sample --exclude-facet model=<local-path-model>; import_j2/j1; check)
python3 -I $D/exam-scripts/os1_population.py $W/l1-units-logs.jsonl $D/os1-population.json
GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file uv run python -I $D/exam-scripts/raw_checks.py "$PWD" $B $W/exam/raw.json
uv run python -I $D/exam-scripts/aer_pass.py "$PWD" $W/l2-logs-j2.partial $W/exam/aer.json
GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file uv run python -I $D/exam-scripts/pass2.py "$PWD" $B $W/l2-logs-j2.partial $W/l1-units-logs.jsonl $W/exam/raw.json $W/exam/pass2.json
GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file uv run python -I $D/exam-scripts/readfile_2439.py "$PWD" $B $W/l2-logs-j2.partial $W/exam/readfile.json
python3 -I $D/exam-scripts/summarise.py $W/exam $D
```

Follow-ups (not run): (1) a supplementary L2 run of the 18 local logs after the D-182 table, through `tools/suite_queue.py --class import --cpu 2` (command in `exam.json`); (2) the orchestrator/user decision on PC-01; (3) the H-08 per-category comparison against `analysis/agentharm_full_model_comparison.md`; (4) inspect outcome arms in `l2_check` (PC-11).
