# Pre-check dossier: `ast-survey-agentharm`

## 1. Header

| | |
|---|---|
| Corpus | `ast-survey-agentharm` (restricted-use class: CC-BY-4.0 plus the AgentHarm use clause) |
| Parts | `agent-security-tools-survey · agentharm` (1 part) |
| Family / profile | `inspect` / `survey-agentharm@1` (semantics `inspect.agentharm@2`, dialect `inspect.eval` v2) |
| Pin | git `Forever-CodingNoob/agent-security-tools-survey` @ `89c4db2c`, tree `agentharm/results` |
| Code commit | `a871e2d7` (L1 and L2, batch `wave1`, no tracked changes) |
| Kind | wave 1, delta since E2 (`../analysis/phase10-examination-2.md`) |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (L1, L2, verify, dossier) |
| Agents | researcher and fact-checker (prereg, research), examiner (L1/L2 analysis), one verifier per finding (6), dossier writer |
| Data | [`data/ast-survey-agentharm/`](data/ast-survey-agentharm/): `research.json`, `l1-agentharm.json`, `l2-sample-agentharm.json`, `l2-agentharm.json`, `exam.json`, `raw-hypotheses.json`, `aer-pass.json`, `outcomes.json`, `dl1-delta.json`, `findings.json`, `exam-scripts/` |

- Code identity, part `agentharm` (Level 2, [`code-agentharm.json`](data/ast-survey-agentharm/code-agentharm.json)): commit `a871e2d7`; engine code aer `24df84b5e307`, sem `a8141c23af13`, prov `d57bd291d3cc`, validation `d3f9995f61bf`; adapter inspect.eval 1867569d63c9.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Survey repository | https://github.com/Forever-CodingNoob/agent-security-tools-survey (pin `89c4db2c`, HEAD of main on 2026-10-14; 0 issues, PRs, releases) | the data; `agentharm/README.md` "Our Results" table is the only outcome reference |
| Zenodo record | https://doi.org/10.5281/zenodo.22140262 (concept 22135956; v1.0.0 and v1.0.1, cc-by-4.0) | alternative origin; same `agentharm/results` sizes |
| Survey paper | none found (arXiv and web search, 2026-10-14) | n/a |
| AgentHarm paper | https://arxiv.org/abs/2410.09024v3 (ICLR 2025) | benchmark definition; evaluates none of the three Ollama models |
| AgentHarm data | HF `ai-safety-institute/AgentHarm` @ `e23b3fe6` (revision code-inferred, not in the header) | task data, MIT plus a use-restriction clause |
| Harness | inspect_ai `0.3.247.dev69+g53c1fa98b`; inspect_evals @ `2dd469ac`, AgentHarm task version 2-B | producer and scorer |
| Upstream issues | inspect_evals [#2439](https://github.com/UKGovernmentBEIS/inspect_evals/issues/2439) (fix PR [#2455](https://github.com/UKGovernmentBEIS/inspect_evals/pull/2455) open), #2107, #2108, #2101, #2146 (fixed by #2154), #2212, #2312 | scoring and tool-environment defects at 2-B |

Data-versus-paper notes (from `research.json`):

- No paper reports these runs. The survey README table equals the log headers. Reference values are given to 3 decimals.
- The producer is a dev build 132 commits before the 0.3.247 release that the README names (L-01, cosmetic).
- Scoring is 2-B. Fixes 3-B to 8-B and #2146 came later, so the numbers are not comparable with 6-B or later (L-02).
- The paper's Table 1 gives a public test set of 264 behaviours. The released `test_public` has 176 harmful and 176 benign rows, and the corpus follows the released split (L-15). The paper reports 11 categories overall; the data holds 8 (L1-05).
- The header's dataset location is an account path (L-12). It does not reach any derived output (L1-06, L2 redaction).
- Judge model events carry no seed and no max_tokens. The agent runs at temperature 0, seed 0, max_tokens 4096 (L-13, H-13).
- #2439 (L-07) is confirmed in the data: PC-01 (source-defect under R1).

## 3. Expectations

Pre-registration: [`prereg/ast-survey-agentharm.md`](prereg/ast-survey-agentharm.md), committed in `fd75f8a3` (2026-10-14), before any check of this corpus ran. Method amendments 1 to 3 (README section 8) apply. Amendment 1 covers the stored corpus's expected `validate.results.differ`.

Hypotheses H-01 to H-18: 17 supported. H-12 is refuted, and the cause is expected-known (PC-04). H-17 is supported within the part and across wave-1 parts; the cross-corpus test is pending wave 4 (see the refuted PC-06 and section 10).

Classes follow the canonical rules R1-R6 and the cross-cutting items CC-01 to CC-08 of [`cross-cutting.md`](cross-cutting.md) (harmonisation pass 2026-10-15).

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Run at `a871e2d7`, `--use-pin`, 6.5 s, jobs 2.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 7 blobs: 6 `.eval` selected, 1 `timing_summary.csv` not selected (context); 0 excluded or stray. Units 1,056 = 6 × 176 = registry. Members 1,691 (229/247/272/286/317/340) = 1,062 selected (6 headers + 1,056 samples) + 629 not selected (617 `_journal`, 6 summaries, 6 reductions). Central directory = `members.jsonl` in 6/6 logs | as expected; L-10 resolved (PC-03). L1-09 does not apply (git tree) |
| L1-02 parse | strict class ok 6/6 artefacts. Only class: `big_int`, 10 strings at 5 `post_id` pointers in 1/6 (coder_benign) → 6 `$int` wrappers in 1 AER | as expected (10) |
| L1-03 encodings | 6/6 artefacts. Literal escapes 1,532 (newline 1,008, quote 120, unicode 404); E2 AER count 1,492. `json_in_string` 7,285 (tool-call arguments, attachments). Variation selectors 351; E2 AER count 260. 0 bidi, tag, zero-width, C0/C1, PUA, U+FFFD, mojibake | as expected. The prereg row on Windows paths is not testable: L1-03 has no such class |
| L1-04 duplicates | within part: 0 byte-identical groups, 0 trajectory groups (1,056 distinct fingerprints, 1 `fp_fallback`; member sha256 1,056 distinct). Cross-part (`_cross/l1-xdup.json`, wave 1): 0 groups | as expected; cross-corpus check with the other AgentHarm corpora after wave 4 |
| L1-05 arms | model × split = 3 × 2 cells, 1 log and 176 units each; 0 missing, 0 extra. Header status success 6/6, one producer. 8 categories (Copyright 144, Cybercrime 120, Disinformation 120, Drugs 120, Fraud 144, Harassment 144, Hate 120, Sexual 144) | as expected |
| L1-06 secrets/paths | Content pointers only. Named home-dir 2,958 strings in 6/6 (8 distinct segments; benchmark fiction or model text). Generic home-dir 91 in 4/6. Windows-users: named 36 in 2/6, generic 34 in 1/6. Generic credential assignment 21 in 3/6. The header dataset location is an account path in 6/6 logs (1 distinct segment); that segment occurs 0 times in sample content, AER/SEM/PROV/validation/index (scratch and stored) and these reports, against a positive control of 4,324 prefix hits in the scratch AER. The operator's home appears 0 times | as expected (L-12); CC-03: benchmark or model content, 0 operator hits |
| L1-07 timestamps | 18 timestamp pointers, 0 parse failures. All UTC (45,131 event, 9,425 completed). Range 2026-08-21T21:23:06.99Z to 2026-08-22T13:23:22.73Z. Event order is non-monotone in 766/1,056 units (= exactly the samples with at least 1 tool event) and `working_start` in 1,056/1,056 (artefact count 1,056). No overlap across logs; `total_time` within 0.6 % of the README minutes | as expected |
| L1-08 degenerate | 0 empty, zero-message, error-only or unterminated. 0 sample errors. `sample_limit` 54 (9/33/6/6) | as expected |

Duplicate group counts in this table are the per-part L1 summary (`l1-agentharm.json`), and this dossier uses it. `data/_cross/l1-xdup.json` counts a group under `within_part` only when all its members are in one part and moves groups that span parts or corpora to `cross_part` or `cross_corpus`; for this part both give 0 groups. A comparison with the post-check must use the same basis.

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`data/ast-survey-agentharm/l2-sample-agentharm.json`](data/ast-survey-agentharm/l2-sample-agentharm.json): 6 of 6 containers (6 strata `results_dir` × 1). The part has fewer than 30 units, so it is imported whole (amendment 2.3): 1,056 of 1,056 executions |
| Import | 2 scratch corpora (`l2-agentharm-j2.partial`, `-j1.partial`). Sample join: 6/6 labels, 176 executions each, 0 without execution. Executions 1,056: status ok 1,052 / ok_with_issues 4; all stages ok; degenerate 0; `adapter_defect` 0. Completeness: verified_complete 1,052, known_incomplete 4 (as regen items 9/11 predict). Register codes: `inspect.sample_limit` 54, `missing_tool_result` 4, `dangling_source_ref` 4 |
| Validation | all tiers: 1,056 passed, 0 failed, results reproduced 1,056, linkage 100 %. SHACL is not implemented (skipped); regression does not apply |
| Recompute | `--dry-run`: 1,056 identical, 0 failed, 0 unexplained |
| Verify chain | 0 failed. `checksums.absent` reported as unverified: expected for a working tree |
| Determinism | j2 vs j1: 4,243 files each, 0 differ, index identical |
| A2 error classes | from the examiner script, because `l2_check` has no A2 section (PC-05). Agent model calls 3,660 (stop 979, tool_calls 2,658, max_tokens 23); judge calls 1,601. Tool executions: ok 3,931, error 84 (all `read_file` file_not_found, PC-01), invalid 149. Empty assistant text declared ambiguous 2,345. `/params/transmitted` lost 630. Seal issues: sample_limit 54; missing_tool_result 16 and dangling_source_ref 16 in 4 executions |
| A3 PROV issues | over 366,830 statements, 0 each of dangling, missing_generation, missing_use, invented, forbidden, time_inferred and unexecuted. `time_not_run_scope` 23,093 (informational) |
| Evidence classes | core D 126,531 / O 100,305 / none 4,164 (hadMember). Inference I 1,056. Assessment D 46,462 / I 18,752 / O 2,112 / none 10,424. Top O 53,856 / none 3,168. `_unverified` twins 0 |
| Safety net | `abnormal_finish#max_tokens` 23 and `text_encoded_call#marker` 12 unclassified (PC-02). Other net rows are classified |
| Identity | 3 agent models, 352 executions each, 0 mismatches (`results_dir` → model 6/6 consistent). Judge `qwen3:14b` in 1,012 executions. Benchmark `agentharm` version "2", commit ambiguous. Env actor in 766 executions. Suites `agentharm` 528 + `agentharm_benign` 528. Defence and attack none (by design) |
| Redaction | 0 operator-home and 0 dataset-location segment hits in AER/SEM/PROV. The account-path screen hits (`l2_check`: 3,176 files; AER 1,626 pointer hits in 95 executions, PROV 221 in 71; class account-path only) are all content (benchmark fiction or model text, H-15; CC-03, 0 operator-* hits). 0 secret shapes in AER (H-18) |
| Withholding | the profile has no withhold table; nothing is withheld (policy null), as expected |
| DL-1 (stored `-p10` vs scratch) | same 1,056 ids. AER, SEM, PROV and validation digests differ in 1,056/1,056; register identical; member rows identical except `fn_digest`. Every differing pointer is attributed to item 30, item 12 c3/c4, U6-a, U6-b, items 9/11 or the expand bundles: 0 unexplained (`dl1-delta.json`). Stored `validate.results.differ` is expected-known (amendment 1; PC-07, CC-05) and was not re-run |

### Recheck (CC-08, recheck12)

`plans/recheck12.toml` (l1, l1_10, check; sample frozen) against the d97d3a57 files; full deltas in [`_cross/recheck12.json`](data/_cross/recheck12.json). Every other L1/L2 count is unchanged; the only other deltas are run environment (code commit d97d3a57 with tools/src = 5efa3575, `tracked_changes` true, two H.8.4(2) recompute notices with 0 unexplained changes; R12-01).

| Part | L1-08 flags (old -> new) | L2 `_unverified` split | L1-10 |
|---|---|---|---|
| agentharm | no change | twin/native/mixed keys added, all 0 (no `_unverified` refs) | 0 screened (-); 0 hits; files with a hit 0; named accounts 0; operator 0; unreadable 0 |

- No `_unverified` refs: split keys present and empty. L1 unchanged. L1-10: 0 context files.

## 6. Outcome comparison

Level 1 is the population: the raw score and refusal fields of all 176 units per arm. The reference is the survey README, which equals the headers; no paper evaluates these models. Gap rule (section 4): more than 15 pp, or more than 5 pp outside the Wilson 95 % interval.

| Arm | Level | n | Refusal rate (Wilson 95 %) | README | Full-score share (Wilson 95 %) | README | Mean score | README | Max gap (pp) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| coder_harmful | L1 | 176 | 0.619 [0.546, 0.688] | 0.619 | 0.205 [0.152, 0.270] | 0.205 | 0.394 | 0.394 | 0.05 | match |
| coder_benign | L1 | 176 | 0.199 [0.147, 0.264] | 0.199 | 0.540 [0.466, 0.612] | 0.540 | 0.791 | 0.791 | 0.02 | match |
| gptoss_harmful | L1 | 176 | 0.915 [0.864, 0.948] | 0.915 | 0.108 [0.070, 0.162] | 0.108 | 0.131 | 0.131 | 0.05 | match |
| gptoss_benign | L1 | 176 | 0.528 [0.455, 0.601] | 0.528 | 0.432 [0.361, 0.506] | 0.432 | 0.640 | 0.640 | 0.04 | match |
| qwen14_harmful | L1 | 176 | 0.290 [0.228, 0.361] | 0.290 | 0.199 [0.147, 0.264] | 0.199 | 0.495 | 0.495 | 0.03 | match |
| qwen14_benign | L1 | 176 | 0.063 [0.035, 0.108] | 0.063 | 0.284 [0.223, 0.355] | 0.284 | 0.607 | 0.607 | 0.05 | match |
| all 6 arms | L2 (sample = population) | 1,056 | AER judgement distribution = raw (OS-2 mapping) in 6/6 arms | as L1 | same | as L1 | same | as L1 | as L1 | match |

All gaps are at most 0.05 pp, which is rounding. Refusal counts are 109/35/161/93/51/11, total 460 = E2. Wilson intervals do not apply to means. The README numbers carry 2-B semantics (L-02). Part of the scores rests on the broken file tools in 63 samples (PC-01), and the effect on the score depends on the arm.

## 7. Findings

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-ast-survey-agentharm-01 | Bundled-content file tools fail with file-not-found in 63/1,056 samples (benign 40/528, harmful 23/528), inspect_evals #2439 in the data | source-defect (R1: no `artefacts.toml` entry covers #2439; was documentation-mismatch) | S2 | confirmed (1/1), with corrections | Disclose in the dossier, datasheet and manuscript; keep all data; route the artefact entry below to the inspect family owner (new detector) |
| PC-ast-survey-agentharm-02 | E2-b5 still open: `max_tokens` 23 and text-encoded calls 12 unclassified by the safety net | expected-known | S3 | confirmed (1/1) | Family owner adds the two entries from E2 section 10.2 (basis 12 samples / 13 messages, all qwen3-coder; max_tokens gpt-oss 2 + qwen3:14b 21) |
| PC-ast-survey-agentharm-03 | Verify report's 6 × 286 members is one log's count (gptoss_benign); there is no 25-member gap | documentation-mismatch | S3 | confirmed (1/1) | Correct `verify/agent-security-tools-survey.md` section 2.3 with per-log counts. No corpus change |
| PC-ast-survey-agentharm-04 | 3 of 54 limit-stopped samples hold fewer than 20 messages (18, 16, 16): the harness leaves out a whole parallel tool-result batch that would exceed the limit | expected-known | S3 | confirmed (1/1), rewording | Add one sentence to the `sample_limit` and `tool_result_lost_at_limit` descriptions (the verifier's wording). No mapping change |
| PC-ast-survey-agentharm-05 | `l2_check`: empty Inspect outcome arms (bool-only judgements, suite-blind arm key) and no A2 section | analysis-artefact | S3 | confirmed (1/1), scope widened | After the batches: numeric-judgement path, suite in the arm key, and an A2 section. The A2 gap is tool-wide (no wave-1 L2 report has it); route to the orchestrator |
| PC-ast-survey-agentharm-07 | [CC-05] Stored corpus `ast-survey-agentharm-p10.partial` gives `validate.results.differ` (rows predate regen item 10's `pv.constraints.*` checks) | expected-known (CC-05) | S3 | added in the harmonisation pass; evidence is the amendment-1 proof, not re-run here | None before the round; compare like with like after re-validation (amendment 1) |

6 findings: PC-01 to PC-05 confirmed by their verifier, PC-07 the numbered CC-05 finding added in the harmonisation pass; 1 refuted (PC-06, now in the `refuted` list of `findings.json`, CC-06 format). PC-05 is an analysis-artefact (R5) and is not counted in the readiness verdict. PC-01 follows R1: an upstream harness defect visible in the data that no `artefacts.toml` entry or profile quirk covers is a `source-defect`, with the proposed entry below.

Corrections the verifiers asked for, applied in `findings.json`:

- PC-01: 84 of 84 `read_file` calls that named a bundled file failed, and no read in the corpus succeeded. The other 9 calls are model misses: 7 invalid names, 2 directories.
- PC-01: 62 of 63 `convert_pdf_to_text` calls are the defect. The 63rd, in gptoss_harmful, is a model miss with an unmatched path.
- PC-01: `harmful_tools` share the defect. #2439 names only the benign tools.
- PC-01: the score effect depends on the arm. gptoss_benign is lower (0.378 vs 0.664, n 15) and gptoss_harmful is higher (0.643 vs 0.126, n 2); elsewhere the difference is small.

Refuted (not a finding):

- **PC-ast-survey-agentharm-06**: the claim was that `l1_xdup` does not compare Inspect sample members and lacks the other AgentHarm corpora. The verifier refuted it.
  - The per-input `artefacts` value of 0 is a display counter of rows without a unit.
  - The comparison itself uses all 1,056 rows: the 6 distinct `.eval` sha256 enter the byte-identity map (totals 134,743 = inputs 134,737 + 6), and 1,056 distinct trajectory fingerprints enter the trajectory map. That is the comparison the prereg asks for.
  - `kexin-xu-01-agentharm` and `fragfuse-agentharm` are wave-4 parts. Their absence from the post-wave-1 snapshot is timing, and the planned re-run after wave 4 covers them.
  - What remains is a cosmetic S4 note about the per-input label.

Proposed `artefacts.toml` entry for PC-01 (R1; text only; route to the inspect family owner):

```toml
[[artefact]]
id = "inspect.art.bundled_file_not_found"
title = "Bundled-content file tools fail with file not found"
description = "AgentHarm's read_file and convert_pdf_to_text (benign_tools and harmful_tools alike) resolve bundled files relative to the process working directory; the survey ran the benchmark from the inspect_evals checkout root (inferred), so every call naming a bundled file failed: read_file with error type file_not_found, convert_pdf_to_text with a 'File not found at benchmark/...' result. Scores of the affected samples rest on a broken tool environment (inspect_evals #2439, which names the benign tools only)."
scope = { sources = ["agent-security-tools-survey"], parts = ["agentharm"], profiles = ["survey-agentharm"] }
cause = "upstream_harness"
detector = { rule = "<new: inspect.file_tool_not_found@1: read_file tool_execution error type file_not_found, or the convert_pdf_to_text result marker 'PDF content from ...: Error: File not found at benchmark/'>", class = "O" }
recorded_as = {}
handling = { class = "FO" }
expected = [
  { snapshot = "git:89c4db2c949797fbb38c5bfed85dc82780ddbfe3", count = 63, basis = "samples with >= 1 harness-failed call: coder_benign 13, coder_harmful 9, gptoss_benign 15, gptoss_harmful 2, qwen14_benign 12, qwen14_harmful 12 (benign 40, harmful 23); calls: read_file 84 of 84 allowlisted (93 total; 7 invalid names, 2 directories), convert_pdf_to_text 62 of 63 (1 unmatched path), edit_txt 0 of 2" },
]
manuscript = true
refs = ["https://github.com/UKGovernmentBEIS/inspect_evals/issues/2439", "https://github.com/UKGovernmentBEIS/inspect_evals/pull/2455"]
```

PC-02 uses the two entries already drafted in E2 section 10.2 (`inspect.art.abnormal_finish_max_tokens` 23, `inspect.art.text_tool_call` 12).

Items for AGENTS.md section 12:

- PC-01: the survey AgentHarm scores (2-B) partly rest on a broken file-tool environment in 63/1,056 samples (inspect_evals #2439, both tool modules). Disclose this in the datasheet and manuscript. All data is kept. The `inspect.art.bundled_file_not_found` entry is pending with the inspect family owner.

## 8. Recommendations and readiness

1. Route the PC-01 artefact entry and detector to the inspect family owner, and add the disclosure to the datasheet. State that the scores carry 2-B semantics (research open question 2).
2. Route the E2-b5 entries (PC-02) to the family owner. They change no corpus bytes.
3. Correct verify report section 2.3 (PC-03), and reword the two limit artefact descriptions (PC-04).
4. Tools, after the batches: `l2_check` numeric outcomes, suite in the arm key, and an A2 section for every corpus (PC-05). Re-run `l1_xdup` after wave 4 (section 10).
5. No exclusion of any data.

**Readiness: `ready-with-caveats`.**

- The part imports whole, deterministically and without unexplained changes:
  - validation 1,056/1,056
  - recompute 0 unexplained
  - j1/j2 byte-identical
  - DL-1 0 unexplained
  - redaction clean
  - outcomes equal to the README in 6/6 arms
- Caveats, all owned and routed. None blocks the regeneration:
  - PC-01 (source-defect S2 under R1: disclosure, plus a new artefact entry for the inspect family owner)
  - PC-02 (E2-b5 catalogue entries, family owner)
  - stored-corpus `validate.results.differ`, expected-known under amendment 1, until the round re-validates (PC-07, CC-05)
  - H-17 cross-corpus duplicate check after wave 4 (section 10)
- Not counted (R5, analysis-artefacts): PC-05.

## 9. Reproduction

Batch (wave 1; plan entry in `tools/precheck/plans/wave1.toml`):

```toml
[[part]]
corpus_id = "ast-survey-agentharm"
source = "agent-security-tools-survey"
part = "agentharm"
l1 = ["--use-pin"]
```

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave1 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave1.toml
```

Steps the batch ran (W = `~/.agentprov/migration-work/precheck/ast-survey-agentharm`, D = `docs/reports/precheck/data/ast-survey-agentharm`):

```bash
uv run python tools/precheck/l1_scan.py --source agent-security-tools-survey --part agentharm --corpus-id ast-survey-agentharm --jobs 2 --emit-fp --use-pin
uv run python tools/precheck/l2_sample.py select --units W/l1-units-agentharm.jsonl --source agent-security-tools-survey --part agentharm --corpus-id ast-survey-agentharm --out D/l2-sample-agentharm.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-agentharm.json --corpus W/l2-agentharm-j2 --source agent-security-tools-survey --part agentharm --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-agentharm.json --corpus W/l2-agentharm-j1 --source agent-security-tools-survey --part agentharm --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-agentharm-j2.partial --out D/l2-agentharm.json --sample D/l2-sample-agentharm.json --l1-units W/l1-units-agentharm.jsonl --compare-with W/l2-agentharm-j1.partial --jobs 2
# inside l2_check:
uv run agentprov validate --corpus W/l2-agentharm-j2.partial --tiers aer,sem,prov,linkage,shacl,regression --jobs 2
uv run agentprov recompute --corpus W/l2-agentharm-j2.partial --dry-run --jobs 2 -q
uv run agentprov verify --corpus W/l2-agentharm-j2.partial --level chain
```

Examiner and verifier scripts (read-only, through `agentprov.ingest`):

```bash
uv run --offline python -I D/exam-scripts/toolerr.py W/l2-agentharm-j2.partial         # PC-01
uv run --offline python -I D/exam-scripts/aer_pass.py W/l2-agentharm-j2.partial <out>  # PC-02, A2, evidence classes
uv run --offline python -I D/exam-scripts/raw_checks.py W/l2-agentharm-j2.partial <out> # PC-03 (members)
uv run --offline python -I D/exam-scripts/raw_checks2.py W/l2-agentharm-j2.partial <out> # PC-04 (limit samples)
uv run --offline python -I D/exam-scripts/dl1_diff.py ~/.agentprov/corpora/ast-survey-agentharm-p10.partial W/l2-agentharm-j2.partial tools/analysis2 D/dl1-delta.json  # DL-1
uv run --offline python -I D/exam-scripts/tz.py W/l2-agentharm-j2.partial                # L1-07 time zones
```

Follow-ups for the orchestrator: section 10.

## 10. Open follow-ups

Not run in the harmonisation pass. W and D as in section 9.

| # | What | Command | When |
|---|---|---|---|
| 1 | H-17 cross-corpus duplicates with `kexin-xu-01-agentharm` and `fragfuse-agentharm` (the refuted PC-06 confirmed this is timing, not a tool gap) | `uv run python tools/precheck/l1_xdup.py` | after wave 4 L1 |
| 2 | PC-05: extend `tools/precheck/l2_check.py` (Inspect numeric outcomes, suite in the arm key, an A2 section), then re-run its `check` step | `uv run python tools/precheck/l2_check.py --corpus W/l2-agentharm-j2.partial --out D/l2-agentharm.json --sample D/l2-sample-agentharm.json --l1-units W/l1-units-agentharm.jsonl --compare-with W/l2-agentharm-j1.partial --jobs 2` | after the tool freeze |
| 3 | CC-05 / PC-07, optional: confirm amendment 1 on a copy of the stored corpus (never in place) | `uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-ast-survey-agentharm -- uv run agentprov validate --corpus <copy of ~/.agentprov/corpora/ast-survey-agentharm-p10.partial> --jobs 2` (expect exit 1, `validate.results.differ`) | optional |
