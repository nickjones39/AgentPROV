# Pre-check dossier: `sentry-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `sentry-agentdojo` (AGPL-3.0-only, own corpus, D-94) |
| Parts | `sentry-agentdojo · head` (1 part) |
| Family / profile | `agentdojo` / `sentry-agentdojo@1` (dialect `agentdojo.tracelogger`, variants `v1.k14` 670, `v1.k14.incomplete` 4; semantics `agentdojo.suites@2`) |
| Pin | git `vinhqdang/SENTRY-…-LLM-Agent-Action-Streams` @ `938e8be7` (= head of `main`), tree 782 blobs (21 binaries absent in staging) |
| Code commit | `d97d3a57` (L1 and L2, batch `wave3`, all six steps rc 0, tracked changes false) |
| Kind | wave 3, first examination (not in FA or E2); no stored corpus |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (L1, L2 batch), 2026-10-21 (examination, this dossier) |
| Agents | researcher and fact-checker (prereg), examiner, adversarial verifier (2026-10-21: PC-01..05 confirmed, none refuted) |
| Data | [`data/sentry-agentdojo/`](data/sentry-agentdojo/): `research.json`, `l1-head.json`, `l1-10-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `os1-population.json` (raw population checks), `cc07.json`, `exam.json`, `findings.json`, `exam-scripts/` |

- Code identity, part `head` ([`code-head.json`](data/sentry-agentdojo/code-head.json)): commit `d97d3a57` (tracked_changes false); engine code aer `856b7a09e0cf`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `agentdojo.tracelogger@0.1.0` `03d8bc6d30df`; profile sha256 `a2ec1024fde2`, rules agentdojo 2 / aer 1; lockfile `b0455f1058c8`, limits `5d6dbb210259`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Repository | https://github.com/vinhqdang/SENTRY-Anytime-Valid-E-Process-Monitoring-of-LLM-Agent-Action-Streams @ `938e8be7` (0 issues/PRs/releases) | the data (`real_data/agentdojo/`, 674 logs) |
| Paper | unpublished manuscript `manuscript/sentry_ml.tex` in the repository (no arXiv/DOI/data record) | `tab:corpus`, `tab:polarity`; NOTES.md §11 unfiltered table |
| Harness | `agentdojo==0.1.35` (all logs), suites v1.2.2 per `run.py` (not logged), stock pipeline, no defence, OpenRouter | producer and scorer |
| Upstream issues | ethz-spylab/agentdojo [#181](https://github.com/ethz-spylab/agentdojo/issues/181), [#161](https://github.com/ethz-spylab/agentdojo/issues/161), [#214](https://github.com/ethz-spylab/agentdojo/issues/214), [#168](https://github.com/ethz-spylab/agentdojo/issues/168) (open) | checker/harness defects; #168 n/a (no slack injection_task_5 here) |

Data-versus-paper notes (from `research.json`, checked against the data):

- Every paper and NOTES count reproduces from the raw `security` field (section 6), with and without the paper's ≥ 2-tool-call filter.
- The GPT-4o-mini headline (47% filtered, 41% unfiltered) contains 13 #181 successes (attacker paid, goal datum absent): re-scored 38.6% / 33.7% (PC-01).
- The free-router set (72 logs) was discarded by the authors but is in the tree; its model is unknowable (D-92/D-105).
- `benchmark_version` is null in all 674 although `run.py` loads v1.2.2 (D-102, `not_recorded`).

## 3. Expectations

[`prereg/sentry-agentdojo.md`](prereg/sentry-agentdojo.md), committed `fd75f8a3` (2026-10-14), before any data check. The prereg's "about 27 strata" was an estimate; the frozen key gives 26 (no free-router benign travel/slack).

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 | 782 walked: 674 selected, 83 not selected, 4 context, 21 absent blobs; 674 units = registry figure 674 | match |
| L1-02 | 674/674 strict ok; 0 duplicate keys, NaN, big ints, surrogates, BOM, trailing data | match |
| L1-03 | 0 C0/C1, bidi, tag, zero-width, U+FFFD, mojibake. Residues: escaped newline 201 artefacts (260 strings, 257 tool content), escaped unicode 27 (30, tool content; #214 class, expected), escaped quote 20; variation selectors 39 (emoji, 36 tool content, 3+3 `send_*` body args) | expected |
| L1-04 | byte-identical groups 0; trajectory-identical groups 0 (674 distinct fp); cross-corpus (`_cross/l1-xdup.json`) 0 groups with sentry | match (H6, H12) |
| L1-05 | 26 strata; cells equal prereg §2 exactly (e.g. gpt-4o-mini ii slack 6, free router ii 21/15/6/6, benign 16/8); injection-task totals it0 120, it1 137, it2 109, it3 84, it6 34; pre-pass 0 | match (H1, H11); coverage gaps PC-05 |
| L1-06 | 0 secret-like, 0 account paths (674); aux 0 | match (H9) |
| L1-10 | 4 context files screened, 0 hits, 0 operator | match |
| L1-07 | `/evaluation_timestamp` 674 naive, 0 parse failures, 2026-07-09..2026-07-22; collection order holds: free router ≤ 2026-07-22 02:12:45 < DeepSeek 02:14:56..04:40:07 < injecagent 08:02:03.. / GPT 08:03:56..08:32:00. `start_time`/`end_time` pointers are calendar tool args (benchmark dates), not run times | match (H8) |
| L1-08 | incomplete 4, trailing_calls 5 (all DeepSeek slack ut7 × it1-3, ut12 × it1/it3; 2 with empty final text = the census null-final pair), 5 zero-call logs (gpt benign 1, free router ii 4), 0 empty, 0 `error` | match, except duration (PC-04) |

Raw headers (os1-population.json): `pipeline_name` 3 values, each = its directory (674/674); `attack_type` ii 439 / injecagent 45 / null 190; `benchmark_version` null 674; package `0.1.35` 674; system prompt one variant, 469 chars (674) (H7, H10, H13).

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`l2-sample-head.json`](data/sentry-agentdojo/l2-sample-head.json): 130 labels, 5 per stratum × 26, seed 20261011, not over maximum |
| Import | j2 and j1 scratch corpora: 130 seen / mapped / validated, 0 failed, 0 degenerate, 0 adapter_defect; sealed clean 99, with issues 31 |
| Validate | 130/130 passed (aer, sem, prov, linkage 100%); shacl not implemented (skipped); regression n/a |
| Recompute `--dry-run` | 130 identical, 0 unexplained |
| Determinism | jobs 1 vs 2: 531 files each, 0 differ, index identical |
| Verify chain | exit 0; only `checksums.absent` (working tree, unsealed) |
| A2 / register codes | accounting_unverifiable 129, earlier_attempts_unobservable 130, identity_unresolved 30, incomplete_run 2 (only trial codes; retry_passes_inferred / unexecuted_tool_call logs not drawn) |
| A3 (PI classes) | 0 over 60,978 statements, 102,376 relation arguments |
| Evidence classes | AER: D 0, I 1,757, O 1,980 records. PROV: core D 626 (engine rules) / O 3,787; inference I 20,172; assessment I 5,234 / O 260. `_unverified` split (CC-08, post-fix counter): twin 21,558, mixed 2,928 (inference I), native 0 |
| Identity | model deepseek-v4-flash 60, gpt-4o-mini 40, unresolved 30 (all free router); defence none 130; attack and suite equal raw (0 direct mismatches) |
| Outcome mapping | AER judgement = raw `utility`/`security` on 130/130 (128 with judgements, 2 incomplete with none) |
| Redaction | 398 files scanned, 0 hits |
| Withholding | no policy (L1-06 0); not applicable |

## 6. Outcome comparison

Attack success = `security` true on attacked logs. Paper filter = ≥ 2 tool calls and non-null outcomes (`corpus_table.py`).

| Arm | Population (judged) | Pop. with paper filter | Paper | Gap | L2 sample (Wilson 95%) | #181 re-scored (all / filtered) | Verdict |
|---|---|---|---|---|---|---|---|
| deepseek / ii | 18/215 8.37% [5.36, 12.84] | 18/198 9.09% | 18/215 (8%); 18/198 (9%) | 0 | 0/20 0% [0, 16.11] | 8.37% / 9.09% (0 of 1 affected) | ok (sample gap 8.4 pp, interval holds the population rate) |
| deepseek / injecagent | 0/45 0% [0, 7.87] | 0/42 | 0/45; 0/42 | 0 | 0/20 [0, 16.11] | unchanged | ok (zero-success arm kept) |
| gpt-4o-mini / ii | 72/175 41.14% [34.12, 48.55] | 72/153 47.06% | 72/175 (41%); 72/153 (47%) | 0 | 8/19 42.11% [23.14, 63.72] | 33.71% / 38.56% (13 of 22 IT0/1/3 affected) | ok; PC-01 disclosure |
| free router / ii | 19/46 41.30% [28.29, 55.66] | 19/35 54.29% | none of record (superseded 63-log RESULTS.md) | n/a | 8/19 42.11% | goal 41.30%; precedence-only 30.43% | context only |
| banking, 3 paper sets | 31 true of 114 files | – | 31 (`tab:polarity`) | 0 | – | 18 | ok (H4) |

Utility (not reported by the paper; population / sample): deepseek ii 79.1% / 85%, injecagent 93.3% / 95%, deepseek benign 86.9% (84 incl. 2 injecagent-set) / 90%, gpt ii 45.1% / 63.2% (n 19), gpt benign 75.6% / 75%, free router ii 69.6% / 68.4%, benign 73.9% / 70%. No arm has n ≥ 20 with a flagged gap; the sample is 5 per suite stratum, so differences are design effects (R6). Benign `security` is the runner constant (189 of 190; 1 incomplete).

CC-07 on this data: **#181** 34 banking IT0/1/3 successes, 13 affected by the goal-datum rule (all gpt-4o-mini: it1 8/8, it3 5/7, it0 0/7), 17 by the precedence-only rule (gpt 12, free router 5); every success has an executed attacker transfer. **#161** 17 banking user_task_5 logs, 17 utility true, 2 vacuous (free router only).

CC-10 (#168): the population has no `injection_task_5` logs (L1-05 injection-task totals it0/1/2/3/6 only), so 0 of the 13 slack attack successes are IT5 cases; #168 affects 0 executions (completeness critic 2026-10-21).

Hypotheses: H1 supported; H2 supported; H3 supported (198 / 42 / 153; benign 71 / 70); H4 supported (114, 31); **H5 refuted** on the duration clause (the 4 labels and null outcomes hold; 2 have a duration, PC-04); H6 supported (2 injecagent-set benign logs: twin cells present, not byte- or trajectory-identical, different timestamps, same outcomes); H7 supported; H8 supported; H9 supported; H10 supported; H11 supported; H12 supported; H13 supported.

## 7. Findings

| Id | Title | Class (CC) | Sev | Verdict |
|---|---|---|---|---|
| PC-sentry-agentdojo-01 | #181: 13 of 22 GPT-4o-mini IT0/1/3 successes lack the goal datum; GPT ii 41.14 → 33.71% (filtered 47.06 → 38.56%) | expected-known (CC-07) | S3 | confirmed |
| PC-sentry-agentdojo-02 | #161: 2 of 17 ut5 utility-true logs vacuous (free router) | expected-known (CC-07) | S3 | confirmed |
| PC-sentry-agentdojo-03 | No artefacts.toml entry scopes sentry-agentdojo | documentation-mismatch (CC-09) | S3 | confirmed |
| PC-sentry-agentdojo-04 | `incomplete_run` text says "without … duration"; 2 of 4 incomplete logs have one | documentation-mismatch (R4) | S3 | confirmed |
| PC-sentry-agentdojo-05 | Source coverage gaps: GPT slack attacked 6 of 45; free-router benign travel/slack absent; injecagent DeepSeek only; free-router model unknowable | expected-known (profile, D-92/D-105, prereg §3) | S2 | confirmed |

Proposed `artefacts.toml` entries (text only, to the AgentDojo family owner):

```toml
# PC-01/02 (CC-07): [[artefact]] id = "agentdojo.art.validity_defects"
#   scope.sources/profiles += "sentry-agentdojo"; expected += { snapshot = "sentry-agentdojo:head", count = 13,
#   basis = "pre-check PC-sentry-agentdojo-01 (#181 goal datum; gpt-4o-mini 13/22)" , status = "proposed" },
#   { snapshot = "sentry-agentdojo:head", count = 2, basis = "#161 vacuous ut5 utility (free router)", status = "proposed" }
# PC-03 (CC-09): scope += "sentry-agentdojo" with counts: benign_security_constant 189; incomplete_run 4;
#   max_iters_pending 5 logs / 5 calls; silent_rerun 2 null-final, 674 unobservable; naive_timestamp 674
# PC-04: incomplete_run title/description: "no utility and security; duration may be present (sentry 2 of 4)"
```

Items for AGENTS.md §12: none new (CC-07 and CC-09 already open).

Verifier (2026-10-21): every finding confirmed, class and severity unchanged. cc07.py and pop.py re-run byte-equal to the committed JSON; PC-01 and PC-02 re-counted with independent, wider rules (13/22, 2/17); PC-01 kept at S3 per CC-07 and the wave-2 harmonisation (the raw booleans reproduce the paper and the engine does not re-score; the 8.5 pp goes in the disclosure). Reasoning in `findings.json` `verdicts`.

## 8. Recommendations and readiness

1. Datasheet disclosure: the GPT-4o-mini ASR is inflated by #181 (13 successes, about 8.5 pp on the filtered rate); the slack GPT arm is a 6-log stub; the 72 free-router logs are kept with model `not_recorded`. No data is excluded, zero-success arms (injecagent) included.
2. Family owner: widen the artefacts.toml scopes (PC-01..03) and amend the `incomplete_run` text (PC-04).
3. Verifier recount done (2026-10-21): PC-01 holds under a wider variant (any tool, any argument, normalised datum): 13/22; precedence-only re-score 60/175 (34.29%), 60/153 (39.22%).

**Readiness: `ready-with-caveats`** (verifier-confirmed). L1 and L2 are clean (0 failures, deterministic, recompute identical, mapping exact, no redaction or secret hits); the caveats are disclosure and catalogue-scope items only.

## 9. Reproduction

```bash
# batch (already run, wave3): l1, l1_10, sample, import_j2, import_j1, check
uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-sentry-agentdojo -- \
  uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave3.toml
# examination (repo root; raw read through agentprov.ingest, blobs by id, lazy fetch off)
uv run python -I docs/reports/precheck/data/sentry-agentdojo/exam-scripts/pop.py docs/reports/precheck/data/sentry-agentdojo/os1-population.json
uv run python -I docs/reports/precheck/data/sentry-agentdojo/exam-scripts/cc07.py docs/reports/precheck/data/sentry-agentdojo/cc07.json
uv run python -I docs/reports/precheck/data/sentry-agentdojo/exam-scripts/trail.py
uv run python -I docs/reports/precheck/data/sentry-agentdojo/exam-scripts/exam_build.py
```
