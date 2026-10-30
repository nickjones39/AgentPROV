# Pre-check dossier: `mcphunt`

## 1. Header

| | |
|---|---|
| Corpus | `mcphunt` (data CC BY 4.0; code MIT with dataset and responsible-use notices) |
| Parts | `mcphunt · head` (1 part; the splits main, mitigation, live_guard_defense and browser_replication are per-execution facets, D-286) |
| Family / profile | `mcphunt` / `mcphunt@1` (dialect `mcphunt.traces`, mapper `mcphunt.trace`, variant `v2.0.0`; registry `planned`); profile sha256 `543563db87e2` |
| Pin | HF `lihaonan0716/mcphunt-agent-traces` @ `c4c69322bf9e` (2026-07-30, = HEAD); staged locally, 32 files |
| Code commit | L1 `d97d3a574a4e` (batch `wave6`, l1 rc 0 in 54.6 s, l1_09 skipped, l1_10 rc 0); examination scripts at `34fd4cbc` |
| Kind | wave 6, first examination (not in FA or E2); never imported; **Level 1 only** (L2 blocked until the D-323 follow-up and the LFS gap fix D-530 land, README section 8 amendments 2.3 and 3) |
| Date | 2026-10-14 (prereg, research), 2026-10-16 (L1), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), batch runner (L1), examiner (this dossier), adversarial verifier (2026-10-21; `exam-scripts/verify/`) |
| Data | [`data/mcphunt/`](data/mcphunt/): `research.json`, `l1-head.json`, `l1-09-head.json`, `l1-10-head.json`, `exam.json`, `findings.json`, `population.json`, `outcomes.json`, `duplicates.json`, `encodings-fffd.json`, `l1-06-classification.json`, `exam-scripts/` |

- Code identity, part `head`: **no `code-head.json`**. L2 did not run, so the batch recorded no engine, adapter or lockfile digests. L1 ran at `d97d3a574a4e` with profile sha256 `543563db87e2`. The post-check records code identity when L2 first runs.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Paper | arXiv [2604.27819v1](https://arxiv.org/abs/2604.27819v1) (only version) | main 3,615 + mitigation 2,706 = 6,321 traces; the guard figures there come from a post-hoc simulation |
| Data record | [HF dataset](https://huggingface.co/datasets/lihaonan0716/mcphunt-agent-traces) @ `c4c69322` | the data. `f793a397` added live_guard (387) and browser (78); the pin rewrote 9 trace documents |
| Code | [lihaonan0716/MCPHunt](https://github.com/lihaonan0716/MCPHunt) HEAD `6b2f4e5` | harness and labeling (`compute_outcome`, `risk_signals`); envelope commit `1e188b8` is not in public history |

Data versus paper: every table cell checked reproduces exactly (section 6). The paper's 6,321 traces contain 532 M0-mitigation records that are verbatim copies of main records (PC-01, verifier recount; 5,789 distinct). 465 traces (live_guard, browser) come after the paper.

## 3. Expectations

[`prereg/mcphunt.md`](prereg/mcphunt.md) (H1-H20, section 4 targets; written before any data check). The prereg itself sets the check map: L2 blocked; outcome sanity is done on the whole-population L1 tally. Per-hypothesis table added by the completeness critic (2026-10-21) from the examiner's record.

| H | Verdict and evidence (from `data/mcphunt/exam.json`) |
|---|---|
| H1 | supported: 32 walked / 20 selected / 12 not selected; 6,786 traces; per-document counts exactly as tabled (L1-01, population.json docs) |
| H2 | supported: 4 envelopes; pipeline_git_commit main x5 + mitigation x12 = 1e188b8 (not public), live_guard 1b7e3c2, browser baseline ffd333b, browser defense 4b85018; sch... |
| H3 | supported: models 2253/723/1776/723/1311, 0 other strings |
| H4 | supported: main per model 147/120/120/147/135/27/27; risky = 9 mech x 39 + 36 benign_control (12 per risky env); 10 risk_mechanism values |
| H5 | supported: GPT-5.4 mitigation denominators equal Table 20 (M0 browser 36; M1 browser 36, git 36; M2 browser 36, git 38, file_to_file 37; M3 browser 36); deepseek/minim... |
| H6 | supported: mitigation_level none 4,758 / 675 / 675 / 678 (sum 6,786); defense 6,360 / 426. Census 5,466 is our error (PC-04) |
| H7 | supported: @modelcontextprotocol/server-memory 465 (live_guard 387 + browser 78); mcp-server-memory 6,321 |
| H8 | supported: 20/20 Table 6/15 cells exact (outcomes.json) |
| H9 | supported: Tables 3/14: 8 env rows and 16 quadrant cells exact; Table 16: 45/45 exact |
| H10 | supported: Table 19 12/12, Table 20 36/36, Table 7 12/12 exact (Table 7 risk tasks = risky_v1 minus 12 benign_control minus 27 task ids prefixed hn_) |
| H11 | supported: Table 17 45/45 exact from labeling.risk_signals |
| H12 | supported: outcome = compute_outcome(artifact_verified, any_risk) 6,786/6,786; benign 735: 0 any_risk, 0 unsafe_* |
| H13 | refuted: memory-server events succeed in the paper traces: main 1,185 ok / 11 fail, mitigation 953 / 6 (PC-05) |
| H14 | not refuted; 1 hit undetermined: 0 /Users/<x>/, 0 Administrator-anchored; named classes: appuser, build (model-authored), Windows Public (generic) and 1 undetermined 4... |
| H15 | supported (bearer tokens not separately tested): 0 anthropic/google/hf/jwt shapes; the 1 openai-key L1 hit = 2 lower-case hyphenated path names (no digits/upper) in th... |
| H16 | supported: collection_timestamp Z 6,786; main 2026-04-25..04-29, mitigation 04-26..04-29, live_guard 07-25, browser 07-27; event window ok 6,786/6,786 |
| H17 | supported: 0 zero-message; finish stop 6,241 / tool_calls 488 (all 30 turns, truncated) / length 10 / error 47; main mean duration_s 59.62 (sum 59.87 h); tokens 218.89... |
| H18 | supported: temperature 0.0 in 6,786; generation_max_tokens 2048 in 6,786 (8192 never logged) |
| H19 | refuted: 1,137 traces in 549 identical-trajectory groups (16.8%); 1,090 cross-document; 515 pairs (1,030 records) are copies (same collection_timestamp and event-times... |
| H20 | supported (concentration reported): U+FFFD traces: earlier 9/6,321 (0.14%); live_guard 53/387 (13.7%), browser 1/78; mojibake 0 (PC-06) |


## 4. Level 1 (whole population, raw through `agentprov.ingest`)

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 | 32 walked, 20 selected, 12 not selected; 6,786 units | = registry 6,786; H1 supported |
| L1-02 | 20/20 strict ok at a 64 MiB element limit (4 elements > 16 MiB parsed) | 0 findings, as expected |
| L1-03 | U+FFFD in 63/6,786 traces: main 7, mitigation 2, **live_guard 53/387**, browser 1. Mojibake 0. ANSI 8, ESC 11, C0 6, PUA 48 and zero-width 35 strings | H20 supported; the Windows-arm concentration is PC-06 |
| L1-04 | 0 byte-identical documents. 549 identical-trajectory groups (1,137 traces, 1,090 of them cross-document); 515 groups classed as copies by the examiner; **verifier recount: 532 M0 records equal a main record in messages, events and timestamps** (17 more than the examiner; most likely pairs whose fingerprint group also holds a third, distinct-run trace, not traced); 2 groups with different labels. Cross-part 0, cross-corpus 0 (`_cross/l1-xdup.json`). CC-01: this format has no provider call ids | H19 refuted, PC-01 |
| L1-05 | split 4, model 5, env_type 7, risk_mechanism 10, mitigation_level 4, defense 2. 0 missing cells vs the paper; 465 extra (post-paper arms) | H3-H6 supported; census `none 5,466` wrong (PC-04) |
| L1-06 | Secret shapes: canary families only (stripe 20 docs, aws 12, slack 12, github 4, private-key header 1, generic assignment 20). The 1 `openai-api-key` hit is a false positive. Named accounts: appuser (6 traces), build (1), Windows `Public` (12): all generic. The length withheld `/home/<x>/.ssh` in 2 unflagged traces is a distribution-default account name inside vulnerability-advisory text (verifier; PC-02 refuted). Operator home 0. Placeholders present: `/mcphunt/`, `/home/user/`, `<redacted>`, `<HOME>`, `MCPHUNT-HOST`, `<internal-gateway>` | H14 supported after verification (PC-02 refuted, CC-03); H15 supported; PC-03 (R5) |
| L1-07 | collection_timestamp `Z` 6,786/6,786. 129,175 epoch event times, 0 non-monotone. Main 04-25..04-29, mitigation 04-26..04-29, live_guard 07-25, browser 07-27. Event window ok 6,786/6,786 | H16 supported |
| L1-08 | 0 zero-message traces. Finish reasons: stop 6,241, tool_calls 488 (all 30 turns, truncated), length 10, error 47. Canary-flagged 4,595, unflagged 2,191 | H17 supported |
| L1-09 / L1-10 | no metadata include rule; 0 non-JSON context files in the selected tree (the 12 non-selected members were not screened) | n/a |

Other figures, all equal to the census and catalogue: messages 6,786 / 6,786 / 80,472 / 129,175; events = tool calls = 129,175; canary events 14,143 in results, 2,172 in args, 15,953 either; `sanitized_args` 245; turn_log = assistant + 1 in 6,105 traces. Temperature 0.0 and max tokens 2048 in all 6,786 traces (H18). Main mean `duration_s` 59.62 s (59.87 h in total). Tokens 218.89M + 9.55M (+0.28% against the paper). Mean turns 12.09. Memory package `@modelcontextprotocol/server-memory` in the 465 later traces only (H7). Memory events succeed in the paper traces (H13 refuted, PC-05).

## 5. Level 2

**Not run (blocked).** Blockers: the D-323 follow-up (RB-1 streaming runner, RB-2 `[import]` limits, RB-3 carving of `minimax_m3_rv1 #/traces/106`) and D-530 (LFS gap). No sample file, scratch corpora or `code-head.json` exist. As a result validate, recompute, determinism, A2/A3, evidence classes (twin/native/mixed), degenerate rates and issue codes, identity, redaction and withholding are **not tested**. The prereg expects, when L2 runs: section-5 issue codes only, 1 degenerate execution (RB-3), and 4,595 executions withheld (D-289). PC-02 was refuted by the verifier (third-party advisory text, CC-03), so no extra withhold is needed for its 2 unflagged traces. D-529 `--sample` does not support `mcphunt.traces`, so no supplementary check is possible either.

## 6. Outcome comparison (L1 population vs paper; [`outcomes.json`](data/mcphunt/outcomes.json))

45 tabled rows, 0 gaps. Beyond those rows, recounts of Table 16 (45 cells), Table 17 (45), Table 20 (36) and Table 14 quadrants (16) are all exact. R6 does not apply (census, not a sample).

| Arm (main, risky v1-v3) | n | Propagation (Wilson 95%) | Paper | Utility | Paper | Policy-viol. /288 | CRS /63 | Verdict |
|---|---:|---|---:|---:|---:|---:|---:|---|
| gpt-5.4 | 387 | 90 = 23.3% [19.3, 27.7] | 90 | 305 | 305 | 39 | 51 | match |
| gpt-5.2 | 387 | 78 = 20.2% [16.5, 24.4] | 78 | 330 | 330 | 33 | 45 | match |
| deepseek-v4-flash | 387 | 158 = 40.8% [36.0, 45.8] | 158 | 275 | 275 | 105 | 53 | match |
| gemini-3.1-pro-preview | 387 | 141 = 36.4% [31.8, 41.3] | 141 | 301 | 301 | 78 | 63 | match |
| MiniMax-M2.7 | 387 | 175 = 45.2% [40.3, 50.2] | 175 | 357 | 357 | 119 | 56 | match |

| Arm | Population | Paper | Verdict |
|---|---|---|---|
| gpt-5.4 main risky_v1 / v2 / v3 / benign / hard-neg | 28/147, 32/120, 30/120, 0/147, 22/189 | same | match |
| gpt54 M0..M3 propagation; utility | 88/384, 64/381, 18/381, 9/384; 305, 302, 301, 309 | same | match |
| gpt54 M0..M3 policy-violating | 40/288, 23/285, 4/286, 1/288 (13.9, 8.1, 1.4, 0.3%) | 13.9, 8.1, 1.4, 0.3% | match |
| Table 7 risky_v1 risk tasks (108; gpt 107) M0..M3 | gpt 26, 21, 5, 2; deepseek 51, 51, 27, 13; minimax 55, 52, 33, 29 | 24.3/19.6/4.7/1.9; 47.2/47.2/25.0/12.0; 50.9/48.1/30.6/26.9% | match (risk tasks = risky_v1 minus 12 benign_control minus 27 `hn_` task ids) |
| live_guard; browser baseline; browser defense | 157/387; 31/39; 35/39 | no paper number | reported only |

Benign: 0 of 735 traces with `any_risk` set (forced by code). `outcome` equals `compute_outcome(artifact_verified, any_risk)` in 6,786/6,786 (H12). Not tested: CC-07 (#181/#161), because mcphunt is not AgentDojo-format. No data is excluded or proposed for exclusion on outcome grounds.

## 7. Findings ([`findings.json`](data/mcphunt/findings.json); verified 2026-10-21, adversarial verifier)

| Id | Title | Class | Sev. | Verdict | Recommendation |
|---|---|---|---|---|---|
| PC-mcphunt-01 | 532 mitigation-M0 records are verbatim copies of main records (messages, events, collection_timestamp equal; only `model_label` differs): gpt54_m0 238/384, deepseek_m0_rv1 147/147, minimax_m0_rv1 147/147. 6,786 records = 6,254 distinct executions (paper set 5,789) | source-defect (R1) | S2 | confirmed, count corrected from 515 (examiner's `dups.py` classification of fingerprint groups missed 17; cause most likely groups with a third trace, not traced) | keep all; add lineage `duplicate_of` links; disclose; pool on distinct executions |
| PC-mcphunt-03 | L1-06 over-reports: appuser, build, Windows `Public` and Linux-distribution default names are generic; the openai-key hit is two `sk-<word>-<word>` path names in the RB-3 trace | analysis-artefact (R5) | S3 | confirmed (extended) | later tool version |
| PC-mcphunt-04 | Census `mitigation_level none 5,466` (sum 7,494); recount 4,758 (= 3,615 + 387 + 78 + 678 M0) | documentation-mismatch (R4) | S3 | confirmed | correct the phase-10m census |
| PC-mcphunt-05 | Prereg lead refuted: the memory server worked in the paper traces (main 1,185/1,196 events ok) | documentation-mismatch (R4) | S3 | confirmed | note only (prereg frozen) |
| PC-mcphunt-06 | U+FFFD in 53/387 live_guard traces (13.7%) vs 9/6,321 earlier; Windows paths in all live_guard and browser traces only | source-defect (R1) | S3 | confirmed | disclose; proposed quirk |
| PC-mcphunt-07 | Catalogued quirks reproduce exactly (canary 4,595 / 15,953; run_not_ok 545; sanitized 245; oversized 4; non-trace 12; event times 6,786) | expected-known (R2) | S3 | confirmed | mark the `unverified` census counts as L1-verified |

Refuted (moved to `refuted` in findings.json):

| Id | Title | Verifier reasoning |
|---|---|---|
| PC-mcphunt-02 | Named length withheld `/home/<x>/.ssh` in 2 unflagged traces (was source-defect S2, security) | The name (digest `fc5669b5`) is a Linux-distribution default account; its one line sits inside a JSON advisory string (key beginning `advis`) of a package database the agent grepped, beside 2 other advisory home names, with no key material. Third-party content, not the collector's account: CC-03 expected-known S3; no withhold, no security flag |

Proposed `artefacts.toml` entries (text only; route to the mcphunt family owner):

```toml
# [[artefact]] id = "mcphunt.art.m0_copies_main"   (PC-01)
#   expected = [{ snapshot = "mcphunt:head", count = 532, unit = "record pairs", status = "proposed",
#                 basis = "pre-check PC-mcphunt-01 (verifier): gpt54_m0 238, deepseek_m0_rv1 147, minimax_m0_rv1 147" }]
# [[artefact]] id = "mcphunt.art.replacement_chars"  (PC-06)
#   expected = [{ snapshot = "mcphunt:head", count = 63, unit = "traces", status = "proposed",
#                 basis = "pre-check PC-mcphunt-06: live_guard 53, main 7, mitigation 2, browser 1" }]
```

Items for AGENTS.md section 12: PC-01 (6,786 records = 6,254 distinct executions; the M0 column re-uses main runs verbatim).

## 8. Recommendations and readiness

1. PC-01: add the lineage links (532 pairs) and the disclosure; no exclusion.
2. Run L2 once D-323's follow-up and D-530 land (follow-up command in `exam.json`). Then confirm the L2-only catalogue counts (`args_unparsed` 2,392, `result_truncated_in_message` 669, `result_differs` 410, `unknown_server` 11) and 4,595 withheld executions.
3. PC-04: fix the census. PC-03: add distribution-default names, `public`, `appuser`, `build` to the generic list in a later tool version.
4. PC-02 needs no action (refuted; no security flag).

**Readiness: `blocked`.** Level 2 has never run: the import path waits on the D-323 follow-up and D-530, so mapping, validation, determinism, redaction and withholding are untested. Level 1 is clean and verified: every count and all 45 outcome rows reproduce exactly; the only S2 is PC-01 (copied M0 records, a disclosure and lineage item). No security finding stands.

## 9. Reproduction

```bash
# L1 (batch wave6): tools/precheck/l1_scan.py via tools/precheck/run_batch.py --plan tools/precheck/plans/wave6.toml
S=~/.agentprov/staging/10m/hf_mcphunt; W=~/.agentprov/migration-work/precheck/mcphunt/exam; X=docs/reports/precheck/data/mcphunt/exam-scripts
uv run python -I $X/pop.py $S $W/pop.json                 # H1-H18 tallies (about 3.5 min)
uv run python -I $X/rv1.py $S $W/rv1.json                 # Table 7 risk-task split
python3 -I $X/outcomes.py $W/pop.json $W/rv1.json docs/reports/precheck/data/mcphunt/outcomes.json
uv run python -I $X/dups.py $S ~/.agentprov/migration-work/precheck/_fp/mcphunt.head.jsonl $W/dups.json   # PC-01
uv run python -I $X/acct.py $S $W/pop.json $W/acct.json; uv run python -I $X/acct2.py $S $W/acct2.json; uv run python -I $X/shape.py $S $W/shape.json   # PC-02/03
uv run python -I $X/fffd.py $S $W/fffd.json               # PC-06
# verifier (2026-10-21): uv run python -I $X/verify/v_pc01.py $S; v_pc02.py, v_pc02b-d.py $S (booleans/digests only); v_misc.py $S
```
