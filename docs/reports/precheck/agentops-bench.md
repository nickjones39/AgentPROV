# Pre-check dossier: `agentops-bench`

## 1. Header

| | |
|---|---|
| Corpus | `agentops-bench` (Apache-2.0; registry status `planned`, no stored corpus) |
| Parts | `agentops-bench · pilot-v1-seeded` (1 part; 3,360 in-scope runs of 7,202 files) |
| Family / profile | `agentops` / `agentops-bench-pilot@1` (dialect and mapper `agentops.trace` v1, semantics `agentops.tools@1`) |
| Pin | Zenodo 10.5281/zenodo.19875693, `agentops-bench-v1.0-pilot-traces.tar.gz`, sha256 `e185bfd0…7a85f` (verified) |
| Code commit | L1 `d97d3a57` (batch `wave6`, l1 and l1_10 rc 0); examination scripts at worktree head `34fd4cbc` |
| Kind | wave 6, first examination (not in FA or E2); **Level 1 only** (amendment 2.3: L2 blocked by the p20 context tree, D-530) |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (L1), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), examiner (L1 analysis, this dossier); adversarial verifier 2026-10-21 (all 10 findings confirmed, 4 rescoped) |
| Data | [`data/agentops-bench/`](data/agentops-bench/): `research.json`, `l1-pilot-v1-seeded.json`, `l1-09-…`, `l1-10-…`, `exam.json`, `findings.json`, `raw-census.json`, `dup-groups.json`, `empty-answer.json`, `exam-scripts/` |

- Code identity, part `pilot-v1-seeded`: no `code-pilot-v1-seeded.json` (no L2 run). L1 at commit `d97d3a57`, profile sha256 `6e109f28477a`, dialect `agentops.trace`; engine and adapter digests not recorded because no mapping ran.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Data record | https://doi.org/10.5281/zenodo.19875693 (concept 19875456; latest version) | the pinned traces tarball and code zip |
| Repository | https://github.com/kunwarshivam/agentops-bench, tag `v1.0` = tag object `91537725` -> commit `c7b29be6` | harness, scorers, paper source |
| Paper | `paper/body.tex` at `c7b29be6` (no arXiv id or DOI) | outcome reference (tab:per-condition, tab:per-domain, tab:headline) |

Data-versus-paper notes (research.json, checked here where the data allow): the paper's CNA formula changed after the runs (PC-03); Opus ran in two parts with 2 superseded copies (PC-08); class counts 12/13/15 (PC-09); our docs mislabel Zenodo versions and the licence holder (PC-10).

## 3. Expectations

[`prereg/agentops-bench.md`](prereg/agentops-bench.md), committed at `fd75f8a3` before any data check.

## 4. Level 1 results (denominator 3,360 in-scope runs unless stated)

| Check | Result | vs expectation |
|---|---|---|
| L1-01 | walked 14,493 (14,486 regular + 7 links; 47 dirs not emitted); selected 3,360; `select.out_of_scope` 3,842; `select.not_execution_artefact` 34 (14 side files + 20 AppleDouble); AppleDouble stray 2,400; not selected 4,850; `ingest.archive.link` 7 | as expected (H1) |
| L1-02 | 3,360/3,360 ok | as expected |
| L1-03 | zero-width 119 (payload 110, web snippets/title 15); variation selector 157 (model text); bidi 1, C0 2, C1 1, NEL 1, PUA 2 (web snippets, model text); escaped `\u` 304, JSON-in-string 279 (payloads) | payload zero-width as expected; the rest is fixture or model content |
| L1-04 | byte-identical 0; trajectory groups 227 (1,245 units), 59 span agents; cross-part 0, cross-corpus 0 (`_cross/l1-xdup.json`) | H9 refuted as worded, explained by fingerprint granularity (PC-05) |
| L1-05 | 56 strata x 60; 420 per model; Opus 150 + 270; 0 missing, 0 extra | as expected (H2) |
| L1-06 | 0 secret-like; named `/Users/` account in 13 runs (1 name; 42 raw-store files in all: 36 run + 6 side, verifier); `/home/<name>` in 4 runs (2 slash-terminated names, 3 name-shaped segments, web_search); 0 identity-field hits | H12 holds; PC-01 security, PC-02 |
| L1-07 | 5,651 call timestamps, all `Z`, 0 non-monotone runs (2,650 with, 710 without); plus 240 tool-output time values (asof_utc 196, unix_timestamp 22, utc 22; 8 runs non-monotone in asof_utc) | H10 partly refuted (PC-04) |
| L1-08 | zero-step 101 (all with error); errors 133 = API/other 113, loop stuck 19, timeout 1; plus 122 empty-answer runs: Llama 119 (zero-token completion, no error, not flagged), Opus 3 (error runs, inside the 133) | H8 holds; PC-06 extra |
| L1-09 | AppleDouble 7,270; 2,400 match include globs (stray, 391,200 B) | expected-known (PC-07) |
| L1-10 | 0 files screened (archive input, no context files in the part) | n/a |

## 5. Level 2

Blocked: the tasks-zip context tree needs the unmerged phase-10i p20 driver (D-530; README amendment 2.3). No sample, import, validate, recompute, determinism, A2/A3, evidence-class, identity, redaction or withholding result exists. H15 not tested. CC-07 (#181/#161) does not apply: not an AgentDojo-format corpus.

## 6. Outcome comparison (L1 whole population; means of [0,1] scores, so Wilson intervals do not apply)

| Agent | Adv. completion | Adv. efficiency | Adv. safety | Safety-domain completion (n 180) | Not completed / 900 |
|---|---|---|---|---|---|
| Opus 4.7 | 0.8611 / 0.861 | 0.8029 / 0.803 | 0.8787 / 0.879 | 0.9403 / 0.940 | 17 / 17 (902 files) |
| Sonnet 4.6 | 0.8444 / 0.844 | 0.7867 / 0.787 | 0.8565 / 0.856 | 0.9349 / 0.935 | 10 / 10 |
| Haiku 4.5 | 0.9066 / 0.907 | 0.7778 / 0.778 | 0.8054 / 0.805 | 0.9612 / 0.961 | 0 / 0 |
| GPT-5.5 | 0.9235 / 0.924 | 0.8510 / 0.851 | 0.8330 / 0.833 | 0.9439 / 0.944 | 0 / 0 |
| DeepSeek V3.2 | 0.9142 / 0.914 | 0.6650 / 0.665 | 0.7632 / 0.763 | 0.9991 / 0.999 | 4 / 4 |
| Llama 4 Scout | 0.1466 / 0.147 | 0.9213 / 0.921 | 0.9010 / 0.901 | 0.2953 / 0.295 | 5 / 5 |
| Mistral Large | 0.8042 / 0.804 | 0.7770 / 0.777 | 0.7804 / 0.780 | 0.9007 / 0.901 | 0 / 0 |
| Qwen3 Max | 0.6733 / 0.673 | 0.6835 / 0.684 | 0.8309 / 0.831 | 0.5385 / 0.538 | 181 / 181 |

Cells are population / paper; adversarial n = 300 per agent. Every gap is at most 0.0005, below the ±0.001 tolerance, and no arm is flagged by the gap rule (H5 supported). Clean/noisy safety and no-payload adversarial runs score safety 1.0 in 1,987/1,987 (H7). The 122 empty-answer runs (PC-06) are part of these numbers. Verifier: raw.py re-run gives a byte-identical census, so the table stands; no outcome gap.

## 7. Findings (adversarial verifier 2026-10-21: all confirmed, none refuted; reasoning in `findings.json` `verdicts`)

| Id | Title (short) | Class | Sev | Sec | CC |
|---|---|---|---|---|---|
| PC-agentops-bench-01 | Named third-party `/Users/` account path in run_python output (result, stdout, stderr) of 13 in-scope run files; 42 raw-store files in all (36 run + 6 side); not the operator; D-199 would map it into AER | source-defect | S2 | **yes** | CC-11, CC-03 |
| PC-agentops-bench-02 | `/home/<name>` in 4 web_search fixture results (2 slash-terminated names, 3 name-shaped segments) | expected-known | S3 | no | CC-03 |
| PC-agentops-bench-03 | Run files carry the pre-`5678816d` CNA formula (2,881/2,881) | documentation-mismatch | S3 | no | R3/R4 |
| PC-agentops-bench-04 | 240 tool-output time values besides call timestamps | documentation-mismatch | S3 | no | R4 |
| PC-agentops-bench-05 | 59 cross-agent fingerprint groups (fingerprint granularity) | analysis-artefact | S3 | no | CC-01, R5 |
| PC-agentops-bench-06 | 119 Llama 4 Scout runs end on a zero-token completion accepted as completed (no error), completion 0; task-dependent (all 60 adversarial code runs); model vs provider undetermined; 3 Opus empty runs are error runs already in L1-08 | source-defect | S2 | no | R1 |
| PC-agentops-bench-07 | AppleDouble 7,270 (2,400 stray), 7 symlinks | expected-known | S3 | no | R2 |
| PC-agentops-bench-08 | Two-part Opus run, 2 superseded copies | documentation-mismatch | S3 | no | R3 (`superseded_part1_copies`) |
| PC-agentops-bench-09 | Paper internal: 12 classes in the text vs 13 rows in tab:per-payload (the data's 15 payloads match the text) | documentation-mismatch | S3 | no | R3 |
| PC-agentops-bench-10 | Our docs: Zenodo version order, licence holder | documentation-mismatch | S3 | no | R4 |

Proposed `artefacts.toml` entries (text only, to the agentops family owner via the orchestrator):
- update `agentops.art.operator_account_path`: security true, CC-11 route, redaction required before import (D-182 supersedes D-199);
- `agentops.art.cna_superseded_formula` (2,881 in-scope runs);
- `agentops.art.empty_answer` (119 in scope, Llama 4 Scout: zero-token completion accepted as final; the 3 Opus empty runs are error runs).

AGENTS.md §12 item: the D-199 versus D-182 account-path conflict for agentops-bench needs a decision before the first import.

Hypotheses: supported H1-H6, H8, H11-H14; partly H7 (per-class counts not tested), H10 (PC-04); refuted as worded H9 (PC-05); not tested H15.

## 8. Recommendations and readiness

- **Readiness: `blocked`** (confirmed by the verifier). L2 cannot run until D-530 lands, and the PC-01 account path needs a redaction or withholding decision before any import. The raw data agree with the paper to within 0.001 on all 32 outcome cells.
- Report PC-01 to the orchestrator now (security). The redaction or withhold must cover all 42 raw-store files (36 run + 6 side files) and stdout as well as tracebacks.
- PC-06 (verifier): a harness parse loss is ruled out (0 output tokens recorded); the harness accepted zero-token completions as final answers. Whether the model or OpenRouter produced them is not determinable from the logs. The runs and their scores stay in.
- Once L2 can run, check the following. H15. That PC-01 is redacted in AER/SEM/PROV. That the PC-04 values never become event times. That the PC-06 runs map as non-degenerate.

## 9. Reproduction

```bash
W=~/.agentprov/migration-work/precheck/agentops-bench
T=~/.agentprov/staging/10i/zenodo_19875693/agentops-bench-v1.0-pilot-traces.tar.gz
S=docs/reports/precheck/data/agentops-bench/exam-scripts
uv run python -I $S/raw.py $T $W/exam/raw-census.json            # H3-H8, H11-H14, outcome table
uv run python -I $S/dupgrp.py $W/l1-units-pilot-v1-seeded.jsonl $T docs/reports/precheck/data/agentops-bench/dup-groups.json
uv run python -I $S/degen.py $T docs/reports/precheck/data/agentops-bench/empty-answer.json
uv run python -I $S/verify_scan.py $T; uv run python -I $S/verify_shapes.py $T   # verifier: full-record account scan, PC-06 tokens/domains
# L1 (already run, wave6): tools/precheck/run_batch.py --plan tools/precheck/plans/wave6.toml (agentops-bench entry)
# Follow-up after D-530 (not run): l2_sample.py, then l2_import.py j2 and j1, then l2_check.py,
#   each through tools/suite_queue.py --class import --cpu 2 --label precheck-agentops-bench
```
