# Pre-check dossier: `whistlebench`

## 1. Header

| | |
|---|---|
| Corpus | `whistlebench` (MIT by repository scope; no separate data licence) |
| Parts | `whistlebench · final-runs` (1 part) |
| Family / profile | `inspect` / `whistlebench@1` (dialect `inspect.eval`, v2, `no_attack`, D-147); SEM skipped (no semantics profile) |
| Pin | git `legobridge/whistlebench` @ `9c27637c` (= head), `final_runs/` 223 blobs / 523,183,391 B |
| Code commit | `d97d3a57` (L1, sample, both imports, check; batch `wave4`, all steps rc 0; tracked_changes false) |
| Kind | wave 4, first examination (not in FA or E2); no stored corpus |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (L1, L2), 2026-10-21 (examination, dossier) |
| Agents | researcher + fact-checker (prereg), batch runner (L1/L2), examiner (this dossier); adversarial verifier 2026-10-21 (10/10 confirmed, 0 refuted) |
| Data | [`data/whistlebench/`](data/whistlebench/): `research.json`, `l1-final-runs.json`, `l1-10-final-runs.json`, `l2-sample-final-runs.json`, `l2-final-runs.json`, `code-final-runs.json`, `exam.json`, `findings.json`, `raw-census.json`, `os1-population.json`, `os2-sample.json`, `aer-pass.json`, `context-scan.json`, `exam-scripts/` |

- Code identity, part `final-runs` ([`code-final-runs.json`](data/whistlebench/code-final-runs.json)): commit `d97d3a57` (tracked_changes false); engine code expand `3b1d412bb77a`, aer `856b7a09e0cf`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `inspect.eval@0.1.0` `1867569d63c9`; profile sha256 `2275688dea24`, rules aer 1 / inspect 2; lockfile `b0455f1058c8`, limits `5d6dbb210259`.

**Security: two S0 findings (PC-01 token, PC-02 real account path), both in AER. Report them to the orchestrator now.**

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Repository | https://github.com/legobridge/whistlebench @ `9c27637c` (4 commits, logs added in `71688cd9`) | the data |
| Paper | https://arxiv.org/abs/2511.17085 (v1-v3; figure SVGs byte-identical) | outcome reference (Figs 2-7, bar geometry) |
| Harness | Inspect AI 0.3.130 / 0.3.134.dev31+geb46eef8 | producer |
| Data record | none outside git | n/a |

Data-versus-paper notes (checked against the data):

- Every paper count reproduces exactly from the raw scores: 128 of 128 cells (section 6).
- **Judge.** The logs record the judge per experiment, and the judge model events confirm it: `openai/gpt-5` in 0_baseline and 1-5_* (108 logs), `openai/gpt-4.1` in 0_baseline_gpt_4.1_grader, **all_models** (Fig 2/3) and habench (68), and `anthropic/claude-sonnet-4-20250514` in SnitchBench (8). The paper's headline Fig 2/3 bars therefore rest on a GPT-4.1 judge (PC-03).
- In all_models, Grok 4 has two mining logs and no medical_devices log. The Fig 2/3 Grok bars pool these 4 logs (PC-04).
- Fig 7's "Claude Opus 4.1" bars are the `claude-opus-4-20250514` logs (H7).
- The git remote origin of the 28 awareness_blackbox logs embeds a GitHub-token-shaped credential (PC-01).

## 3. Expectations

[`prereg/whistlebench.md`](prereg/whistlebench.md), commit `fd75f8a3`. Hypotheses H1-H16 (completeness critic 2026-10-21: per-hypothesis table added from the examiner's record).

| H | Verdict and evidence (from `data/whistlebench/exam.json`) |
|---|---|
| H1 | supported (223/184/39; 9,200; 50 per log; per-experiment counts) |
| H2 | supported (161/8,050 at 0.3.130; 23/1,150 at 0.3.134.dev31; 184 success, v2) |
| H3 | supported (11 models, 0 unresolved, 0 opus-4-1 in awareness_blackbox) |
| H4 | supported (params per log match; 1_responsibility 12 pii + 12 ediscovery; all_models boldness high, distractor docs off; 0 translation, 0 harmful tools) |
| H5 | refuted (all_models 36 and habench 20 logs grader gpt-4.1, not gpt-5; SnitchBench claude-sonnet-4; PC-03) |
| H6 | supported (128/128 cells exact: Fig 2/3 54, Figs 4-6/A.2 54, Fig 7 20) |
| H7 | supported (Fig 7 'Opus 4.1' bars = claude-opus-4-20250514 logs exactly) |
| H8 | supported (habench 4 models x 5 storylines incl. pharma; Fig 7 uses the 4 paper storylines) |
| H9 | supported (8 logs; models as listed; dataset name not checked) |
| H10 | supported (email_whistleblowing in 8,800 high_agency samples; 0 'whistleblowing' key) |
| H11 | not tested (judge-call short-circuit; follow-up) |
| H12 | refuted (real workstation account in tracebacks PC-02; GitHub token PC-01; 7 model-written names) |
| H13 | supported (0 byte-identical, 0 identical fingerprints of 9,200, 0 cross-corpus) |
| H14 | supported at label and form level (offsets -05:00 / -04:00 1_responsibility 12 logs / -07:00 awareness only; 0 Z; 2025-09-28..2025-10-24); per-event offsets not split |
| H15 | refuted (0 empty, 0 errors, 12 limits as expected; error_retries in 260 samples = 2.83% > 1%; PC-07) |
| H16 | supported with caveat (154 units not 210, PC-09; 0 failures, 0 degenerate, determinism identical 23,415 files, only section-5 codes) |


## 4. Level 1 (whole population, raw through `agentprov.ingest`)

| Check | Result (denominator) |
|---|---|
| L1-01 | 223 walked, 184 selected, 39 not selected (19 csv, 11 json, 9 `.eval-set-id`); 9,200 units = registry 9,200 |
| L1-02 | 184/184 `ok` |
| L1-03 | model/tool text only: ansi/esc in 36 artefacts (361 `error_retries/*/traceback_ansi`), bidi 1, c0 2, cr 1, variation selector 17; JSON-in-string 177 (expected) |
| L1-04 | 0 byte-identical; 9,200 of 9,200 trajectory fingerprints distinct; 0 cross-part/corpus (`_cross/l1-xdup.json`) |
| L1-05 | 10 experiments, 11 models, 42 (experiment × model) strata, as pre-registered; params per log as the scripts (H4); Grok 4 storyline gap (PC-04); grader facet (PC-03) |
| L1-06 | `secret:github-token` 28 artefacts / 56 strings at `/eval/revision/origin` (PC-01). Account names (by digest): 1 scenario user (input of all 8,800 high_agency samples), **1 real workstation account in `error_retries` tracebacks, 36 logs / 260 samples (PC-02)**, 7 model-written names (1-3 samples each), 1 Windows-style scenario path, 1 `/home/<named>` (model text) |
| L1-07 | all `offset` forms, 0 parse failures, 2025-09-28..2025-10-24; label offsets -05:00, -04:00 (12 logs of 1_responsibility), -07:00 (awareness only); 0 `Z`; event order non-monotone in 9,196 units (known quirk) |
| L1-08 | 0 empty or zero-message samples; 12 `sample_limit`; 260 samples with `error_retries` (2.83%, PC-07) |
| L1-09 | n/a for this part |
| L1-10 | the tool screened 0 files (git mode, PC-10). The examiner's screen of the 39 context files found 18 token occurrences in the json files and 0 account names |

## 5. Level 2

- Sample: [`l2-sample-final-runs.json`](data/whistlebench/l2-sample-final-runs.json), 154 logs = 7,700 executions. 34 strata are taken whole; 1_responsibility and 2_boldness are drawn 5 of 8/12 (PC-09).
- Import j2/j1 rc 0. validate: 7,700 passed, 0 failed (shacl skipped, regression n/a, linkage 100%). recompute --dry-run: 7,700 identical. Determinism: 23,415 files each, 0 differ. verify chain: 0 failed (only `checksums.absent`, working tree).
- Degenerate 0, adapter_defect 0. Completeness: verified_complete 7,688, known_incomplete 12.
- Issue codes (index), all in prereg section 5: missing_tool_result 7,695, unexecuted_tool_call 2,862, inspect.unmapped_event 112, sample_limit 12, accounting_inconsistent 10, call_result_link_conflict 10, dangling_source_ref 3.
- A3: 5,356 unexecuted call parts represented. No other PI class.
- Evidence: core D 976,672 / O 781,028 / none 28,869; inference I 100,538, of which 92,838 are `_unverified` twins; native 0, mixed 0 (D-24/D-375 as expected).
- Identity: 11 models map 1:1, 0 unresolved. Judges per experiment as in PC-03. Mapped judgement tallies equal the raw tallies for 154/154 logs. CD-24 duplicate `score.<key>` judgements are present (PC-08).
- Redaction (no redact rules in the profile):

  | Value | AER | PROV |
  |---|---|---|
  | GitHub token (PC-01) | 2,800 strings in 1,400 executions, at actor `bench` `/code/repo` and `/ext/inspect/revision/origin` | 0 |
  | Real account (PC-02) | 15,360 strings in 184 executions, at scope `/ext/inspect/error_retries/*/traceback(_ansi)` | 0 |
  | Scenario user | 7,300 executions | 7,300 executions |
  | Model-written names | 1-2 executions each | 1-2 executions each |
  | Operator hits | 0 | 0 |

- Withholding: policy null. It is now required (PC-01, PC-02).

## 6. Outcome comparison

Population (L1, raw): 128/128 cells equal the paper's counts exactly (gap 0; [`os1-population.json`](data/whistlebench/os1-population.json)). No gap was flagged.

| Figure | Cells | n per cell | Exact |
|---|---:|---:|---:|
| Fig 2/3 (all_models, 9 models × gov/media/internal/refusal/eval-aware/hypothetical) | 54 | 200 | 54 |
| Figs 4-6/A.2 (9 arms × 3 models × gov/internal) | 54 | 200 | 54 |
| Fig 7 (4 models × 4 storylines + SnitchBench, deliberation) | 20 | 50 | 20 |

Representative cells, Fig 2/3 government whistleblowing, population rate with Wilson 95%, against the paper:

| Model | n | Rate [Wilson 95%] | Paper | Gap |
|---|---:|---|---:|---:|
| Claude Opus 4 | 200 | 23.5 [18.2, 29.8] | 23.5 | 0 |
| Claude Opus 4.1 | 200 | 58.0 [51.1, 64.6] | 58.0 | 0 |
| Claude Sonnet 4.5 | 200 | 68.5 [61.8, 74.5] | 68.5 | 0 |
| Gemini 2.5 Pro | 200 | 54.0 [47.1, 60.8] | 54.0 | 0 |
| Grok 4 | 200 | 100.0 [98.1, 100.0] | 100.0 | 0 |
| GPT-4.1, GPT-5, Llama 4 Maverick | 200 each | 0.0 [0.0, 1.9] | 0.0 | 0 |

Sample (L2): the all_models and habench strata are whole, so their sample rates equal the population rates. Across 34 (experiment × model) strata, the population government rate lies inside the sample's Wilson interval in 31. The 3 outside (1_responsibility Grok 4, 2_boldness Gemini and Grok 4) come from the draw mixing conditions inside one stratum (R6), so they are not findings. Arms of the zero-success models are kept (no exclusion).

CC-07 (#181/#161) does not apply: this is Inspect format, not AgentDojo.

## 7. Findings

| Id | Title | Class | Sev | Sec | CC | Verdict |
|---|---|---|---|---|---|---|
| PC-01 | GitHub-token-shaped credential in `/eval/revision/origin` of 28 logs reaches AER (1,400 executions) and raw-store context json | source-defect | S0 | yes | CC-13 real, CC-03/CC-11 | confirmed |
| PC-02 | Real workstation account in `error_retries` tracebacks (36 logs, 260 samples) reaches AER scope ext | source-defect | S0 | yes | CC-12a, CC-03/CC-11 | confirmed |
| PC-03 | Fig 2/3 and habench graded by GPT-4.1, SnitchBench by Claude Sonnet 4; the paper says GPT-5 | documentation-mismatch | S2 | no | R3 | confirmed |
| PC-04 | Grok 4 in all_models: mining ×2, no medical_devices | documentation-mismatch | S3 | no | R3 | confirmed |
| PC-05 | Scenario and model-written account paths in AER/PROV | expected-known | S3 | no | CC-03 | confirmed |
| PC-06 | Census "0 secret-like" is wrong | documentation-mismatch | S3 | no | R4 | confirmed |
| PC-07 | `error_retries` in 2.83% of samples; no profile quirk | documentation-mismatch | S3 | no | R4 | confirmed |
| PC-08 | CD-24 duplicate score judgements | expected-known | S3 | no | R2 | confirmed |
| PC-09 | Prereg sample size 210 vs 154 drawn | analysis-artefact | S3 | no | R5 | confirmed |
| PC-10 | L1-10 screened 0 context files in git mode | analysis-artefact | S3 | no | R5 | confirmed |

Proposed `artefacts.toml` entry (text only; route to the inspect family owner):

```
# [[artefact]] id = "inspect.art.credential_in_revision_origin" (proposed)
#   scope.sources = ["whistlebench"]; pointer /eval/revision/origin (URL userinfo)
#   counts: 28 logs / 1,400 samples (awareness_blackbox); 11 context json (18 occurrences)
#   disposition: redact userinfo at mapping or withhold at seal
# profile quirk (proposed) inspect.error_retries: 260 samples / 36 logs; tracebacks hold the run machine's home path (PC-02)
```

Verifier (2026-10-21, [`exam-scripts/verify_recount.py`](data/whistlebench/exam-scripts/verify_recount.py)): all 10 confirmed, 0 refuted, classes and severities unchanged. PC-01: a different detector (any URL userinfo) finds the same 28 logs and one value (digest8 `<secret-A>`); its shape is a classic `ghp_` personal access token (length withheld, long-lived), not an ephemeral installation token. PC-02: 260/260 `error_retries` samples (36 logs, 21,660 strings) and nowhere else; not the operator (different digest, 0 operator hits); 0 in task input. PC-03: paper 3.4 names GPT-5 as judge, and the pinned code default is GPT-5, yet the all_models logs and their judge events are GPT-4.1 (1,800/1,800). Side note (R4, no new finding): the profile's `judge_model_separate_from_agent` note omits the Claude Sonnet 4 judge.

AGENTS.md §12 items: (1) whistlebench token in AER, redact or withhold before release; (2) upstream author's home path in `error_retries` tracebacks reaches AER.

## 8. Recommendations and readiness

**Readiness: `blocked`** (confirmed by the verifier). The block is PC-01 and PC-02: a credential and a real third-party account path reach AER, and nothing redacts or withholds them. Mapping, validation, determinism and outcomes are otherwise clean (128/128 exact, 0 degenerate).

1. Orchestrator, now: security report for PC-01 and PC-02. The user decides whether the upstream owner is told about the token.
2. Profile owner (inspect): strip URL userinfo from `/eval/revision/origin`, and redact account segments in `error_retries` tracebacks (D-182 table). Alternatively, `[withhold]` the affected AER fields and context json at seal. Then add a credential-in-URL detector to release_scan, next to the CC-11 home-path detector.
3. Datasheet: judge per experiment (PC-03), the Grok storyline gap (PC-04), the error_retries quirk (PC-07).
4. Follow-ups, not run: H11 judge short-circuit test; L1-10 git-mode support; a scratch re-import of the affected 64 logs after the profile change (through `tools/suite_queue.py --class import --cpu 2`).

## 9. Reproduction

```bash
W=~/.agentprov/migration-work/precheck/whistlebench
X=docs/reports/precheck/data/whistlebench/exam-scripts
cd $W/exam
uv run python -I $X/raw.py raw.json                       # params, origin shapes, account digests, scores (9 min)
uv run python -I $X/compare.py raw.json outcomes.json     # 128 cells vs the paper
uv run python -I $X/aer_pass.py $W/l2-final-runs-j2.partial $W/l1-units-final-runs.jsonl aer.json
uv run python -I $X/ctx.py context-scan.json              # 39 context files
uv run python -I $X/verify_recount.py $X verify/v.json   # verifier: origin userinfo + error_retries recount (9 min)
# L1/L2 batch (already run): tools/precheck/run_batch.py --plan tools/precheck/plans/wave4.toml
```
