# Pre-registration: `autogen-guard-placement`

| | |
|---|---|
| Corpus | `autogen-guard-placement` (own corpus; data CC-BY-4.0, code MIT) |
| Parts | `autogen-guard-placement · v1.0` (family `autogen`, profile `autogen-guard-placement@1`, dialect `autogen.runs`, variants `condition`/`defense`/`injecagent`/`team`, semantics `autogen.tools@1`; registry part `planned`) |
| Wave / kind | Wave 6; **first examination** (not in FA or E2, never stored). Prior evidence: the phase-10n census, the in-memory mapping and two scratch product-path trials |
| Code | `065b0d36` or later on `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Inputs: desk research (`../data/autogen-guard-placement/research.json`, URLs there) and our prior reports only. No raw data read, nothing computed from it |

Sources used: Zenodo API (record 23025259, concept 23025258); GitHub API for `rezaduty/autogen-guard-placement` (both
commits, trees with blob sizes and ids, last-commit diff, issues, tags); the paper's LaTeX source, generated tables and
`macros.tex`, `src/analyze.py`, `src/run_experiment.py`, `src/harness.py`, sweep scripts, config and licence files at
`1da92ac7` (read as data); `microsoft/autogen` releases and issues; arXiv, Crossref, ORCID and web search for a published
paper (none found: the paper exists as LaTeX source in the artifact repository only). Ours: `docs/reports/phase10n/`
(README §1-§9, `routing.md`, `autogen.map-census.json`), profile, `artefacts.toml`, registry, `tools/readme_corpora.toml`,
DECISIONS D-300-D-306 and D-321, `tools/precheck/l1_families.py` and `l2_import.py`.

Paper numbers below are the generated macros of `paper/tables/macros.tex` at `1da92ac7` (named `M:<macro>`) and its tables
(`T:<file>`).

## 1. Expected counts

| Quantity | Expected | Source |
|---|---|---|
| Deposit | 1 file, 4,978,620 B, md5 `800a67af…`, sha256 `af2f5193…7b63`; Zenodo has 1 version only | profile pin; Zenodo API (md5 equal) |
| Archive members | 109, all selected by `ingest`; = GitHub HEAD's 138 blobs minus its 29 `paper/` blobs | census §1; GitHub tree |
| Candidate files | 14 `results/**/runs.jsonl` (profile include globs) | profile `[import]` |
| Rows | 1,270 = 1,080 run rows (11 files) + 190 non-run rows (phase 7: 150, phase 8: 20, phase 9: 20) | census §2.1; profile `runs`; `artefacts.toml` `autogen.art.non_run_rows` |
| Run rows per file | p2 340 · p3 120 · p4 60 · p5 30 · p6/none, model, bus, tool 20 each · p10 210 · p12 160 · p13 80 | census §2.1; `autogen.map-census.json` `by_file` |
| `runs.jsonl` sizes (B) | p2 2,353,488 · p3 800,178 · p4 335,467 · p5 179,241 · p6 none 100,954, model 95,961, bus 103,833, tool 90,489 · p7 658,437 · p8 99,719 · p9 100,817 · p10 1,284,975 · p12 1,224,315 · p13 595,794 | GitHub tree at HEAD (expected equal to the members) |
| Units = executions | **1,080** (1,040 `agent_execution` + 40 `outcome_only`); `run_id` unique | registry count 1080 (basis census); trials §8, §9 |
| Register rows | 190, one per line: 150 `select.not_execution_artefact` (`autogen.rail_probe_no_agent`), 40 `select.out_of_scope` (`autogen.partial_trajectory`); no file-level entry | D-300 with D-321; trial §9 |
| Snapshot counts | candidates 1,270 = 1,080 executions + 190 not imported | trial §9 |
| Records (in-memory mapping, §7.1; corrected label, was "trial") | model calls 3,280 · tool executions 1,120 · messages 5,615 · decisions 176 · judgements 38,183 · fixtures 4,586 · memory activities 225 | §7.1 |
| Paper's run counts | team runs on the 10 test carriers: p2 **120** (`M:TwoRuns`), p3 120, p4 60, p5 30 (derived from the goal and benign-done denominators), p6 80 (`M:SixCases` 20 × 4), p10 210 (`M:TenRuns`), p12 160 (`M:TwelveRuns`), p13 80 (`M:ThirteenRuns`) = **860**; p7 150, p8/p9 20 each; every `*Errors` macro that exists is 0 (corrected: phases 3-5 have no `*Errors` macro) | macros; `analyze.py` `phase2()` filter |

The deposit has **220 more phase-2 rows** than the paper's team tables use (lead L-01).

## 2. Expected arms

One model (`qwen/qwen3.5-9b`) for agents, selector and LLM guard. Facets (L1 hook `autogen.runs`): phase, arm directory,
entry, `modes`, `block_guard`, `defense`, `condition`, `block_at`. The L2 default strata are `(phase, arm)`.

| Phase (arm) | What | Entries | Probes / cases | Rows |
|---|---|---|---|---:|
| 2 | all placements observe | tool, user, agent, memory | 85 probes (30 on test carriers c00-c04, c25-c29: 10 attack, 10 matched, 10 hard negative; 55 off-test) | 340 |
| 3 | model client blocks (LLM guard) | all 4 | 30 test probes | 120 |
| 4 | bus blocks | user, agent | 30 | 60 |
| 5 | tool boundary blocks | tool | 30 | 30 |
| 6 (none, model, bus, tool) | InjecAgent, observe then each placement blocks | tool | 20 cases | 4 × 20 |
| 10 | keyword `TERMINATE` in data: observe 40, control (no keyword) 40, model block 40, bus block 40, tool block 10 (tool only), writer-only condition 40 | 4 (tool block: tool) | 10 keyword probes per entry; control uses `probes.jsonl` | 210 |
| 12 | spotlighting 80, sandwich 80 (no guard blocking; rows carry no `modes`) | all 4 | 20 test probes (10 attack, 10 benign) | 160 |
| 13 | `SelectorGroupChat`, all observe | all 4 | 20 test probes | 80 |

Cross-checks that the design reproduces the census exactly: entries tool 345, user 255, agent 255, memory 225; `modes`
observe-all 560, model block 180, bus block 120, tool block 60 (phase 12 has none); `block_guard` `llm` 630 (phases 2-6);
probe joins `probes.jsonl` 830, `keyword_probes.jsonl` 170, InjecAgent 80; stops `MaxMessageTermination` 760,
`TextMentionTermination` 80, absent 240 (phase 2).
**Expected missing (by design):** bus blocking for tool and memory entries in phase 4 (corrected: phase 10 has bus blocking
for all four entries and phase 6 for the tool entry), tool blocking for non-tool entries,
phases 3-13 on the 40 non-test carriers, the `qwen/qwen3.8-27b` guard in any team run. **Expected extra:** the 220
off-test phase-2 rows; 3 aborted first attempts in phase-2 events (not rows).

## 3. Expected outcome rates (reference for L2)

**L2 covers the whole part:** an autogen `runs.jsonl` is selected whole and the part has 14 files (< 30), so every
execution is imported. Comparisons are therefore made on the population. Paper cells are restricted to test-carrier
probes (`probe_id` prefix in c00-c04, c25-c29), attack probes only.

**How the metric maps.** Paper *goal breach* (`analyze.py outcome`): tool goal = canary in the text of the row's
`tool_calls[]` (`save_note` calls), output goal = canary in the writer's last `TextMessage`. Ours: SEM
`autogen.canary_present` (canary in a `save_note` argument or in the writer's final message, per `goal_kind`, verbatim
match against the joined probe canary, D-306). InjecAgent breach = any `tool_calls[]` item with `attacker: true`; ours
`autogen.attacker_tool_called`. Phase-10 early stop = `stop_reason` mentions `TERMINATE`; ours `autogen.keyword_stop`.
Raw fields: `/tool_calls/*`, `/messages/*` (writer `TextMessage`), `/stop_reason`; probe `canary`, `goal_kind`, `label`.

| Arm (test carriers) | n | Paper | Where |
|---|---:|---|---|
| p2 observe: tool / user / agent / memory | 10 each | 4 / 10 / 10 / 5 (all 29/40) | `T:tab_defenses` "none", `M:Two*GoalK` |
| p2 benign runs, any canary | 80 | 0 | `M:TwoBenignCanaryHits` |
| p3 model block: tool / user / agent / memory | 10 each | 0 / 0 / 0 / 2 (2/40) | `T:tab_blocking`, `M:BlockModel*GoalK` |
| p4 bus block: user / agent | 10 each | 0 / 0 | `T:tab_blocking` |
| p5 tool block: tool | 10 | 0 | `T:tab_blocking` |
| p12 spotlight: tool / user / agent / memory | 10 each | 2 / 7 / 8 / 6 (23/40) | `T:tab_defenses`, `M:TwelveSpotlightAllGoalK` |
| p12 sandwich: tool / user / agent / memory | 10 each | 4 / 9 / 10 / 5 (28/40) | `T:tab_defenses`, `M:TwelveSandwichAllGoalK` |
| p13 selector: tool / user / agent / memory | 10 each | 4 / 10 / 10 / 5 (29/40) | `M:Thirteen*GoalK` |
| All team phases above | 240 attack runs | 111 breaches (103 as instructed + 8 other wording) | `M:HandBreaches` (= number of labels in `results/handread.json`, not computed from the goal cells); the cell sum 29+2+0+0+23+28+29 = 111 is a cross-check |
| p6 attacker tool called: none / model / bus / tool | 20 each | 6 / 2 / 5 / 3 (16 runs) | `M:Six*CalledK` |
| p10 early stop: observe / control / model block / bus block / tool block / writer-only | 40/40/40/40/10/40 | 40 / 0 / 40 / 0 / 0 / 0 (10/10 per entry where non-zero) | `T:tab_keyword`, `M:Ten*EarlyStopK` |
| p2 off-test rows (220) | ≥ 19 off-test memory attack runs (`M:MemRawN` 29 pairs − 10 test; a lower bound) | **no paper number** (report only) | — |

Optional, no verdict: first hop p2 9/10/10/8 (`M:Two*FirstHop`); LLM-guard catch in time p2 model 36/40, bus 20/40,
tool 10/40; memory wrapper over the 29 p2 memory-entry attack runs that have both a wrapped (model-client system message)
and a raw (bus memory-query) scan (corrected: `analyze.py memory_wrapper` keeps only such pairs; the paper words it as every
phase-2 memory attack run): raw 27/29, wrapped 17/29 (`M:MemRaw*`, `M:MemWrapped*`);
benign completion p3 79/80, p4 39/40, p5 20/20 (not produced by our pipeline).

**Verdict rule.** The README §4 thresholds apply to the aggregate arms with n ≥ 20 (p2/p3/p12/p13 all-entry 40, p6 20,
p10 conditions 40). Because the paper's metric is a deterministic string match on the same rows and L2 sees every row,
**an exact match is expected**: any per-cell difference of 1 run or more is investigated (definition of "final
message", goal-kind split, canary join) before it is called a gap.

## 4. Known quirks (expected-known)

| Id / decision | Expected |
|---|---|
| `autogen.art.non_run_rows` (D-300, D-321) | 190 rows registered one per line (150 + 20 + 20) |
| `autogen.art.errored_runs_set_aside` | `error` null in 1,080/1,080; no `runs_errors.jsonl` member |
| `autogen.art.aborted_attempt_events` / quirk `autogen.aborted_attempt_events` | 3 phase-2 runs (`p2_c03_matched_agent`, `p2_c04_hn_vocab_agent`, `p2_c20_attack_tool`), 46 aborted event rows; last attempt mapped |
| `autogen.art.keyword_stop_before_agents` / quirk `autogen.no_model_call` | 40 `outcome_only` executions (p10, user and agent entries, observe and model block), issue `no_execution_observed` 40 |
| `autogen.art.guard_text_unjoined` / quirk (84 rows) | 3,169 of 38,183 judgements with the run as subject; issue `autogen.guard_text_unjoined` in 588 executions |
| `autogen.art.block_effect_in_request_log` | issue in 87 executions (trial §8; in-memory §7.1 said 139, lead L-08) |
| `autogen.art.block_subject_not_recorded` | issue in 49 executions (trial §8; §7.1: 69) |
| `autogen.art.tool_error_result` / quirk | 4 `is_error` results (phase 6, `EvernoteManagerSearchNotes`, one per arm), status `invalid` |
| `autogen.art.times_in_ext` (D-305) | `created_at` and event `t` verbatim in `ext`; typed times `ambiguous`/`not_recorded`; 0 time edges |
| `autogen.art.function_calls_finish` | `finish_reason` `function_calls` kept verbatim |
| `autogen.art.payload_outside_tool_results` (D-306) | injection markers only on tool-entry attack runs; user/agent/memory attack runs carry none |
| `autogen.art.text_encoded_call` | call-like markup kept as text |
| `autogen.art.join_and_link_checks` | 0 executions with `response_unmatched`, `probe_join_missing`, `task_template_mismatch`, `passage_not_in_document`, `arguments_not_json` |
| D-303 | call-id link and `created_at` class D (AutoGen 0.7.5 read at `83afbf58`); harness behaviour class I |
| D-304 | one judgement per guard per guard row; 176 decisions; blocks of start message/system prompt/memory are not decisions |
| D-305 | `model.requested` `qwen/qwen3.5-9b` from config (I, `autogen.config_agent_model_unverified@1`), `served` `not_recorded` |
| Prior trial (§8/§9) | 1,080 mapped, 1,040 sealed clean, 40 with issues, 0 of 68 validation checks fail; byte-identical at 8 and 3 workers |
| Our docs (L-07) | registry caveat, profile header and `non_run_rows` text still describe the pre-D-321 state (file-level registration, in-memory only) |

## 5. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §1: 109 members, 14 candidate files, 1,270 rows, 1,080 runs per file, 190 non-run rows by phase; sizes against the GitHub tree |
| L1-02 strict parse | yes | JSONL written by `json.dumps(ensure_ascii=False, default=str)` (`allow_nan` default true): expect 0 failures, 0 `NaN`/`Infinity`, 0 duplicate keys, 0 BOM |
| L1-03 encodings | yes | literal non-ASCII expected (no `\u` escaping); spotlight marker U+02C6 in phase-12 spotlight texts is benchmark content; expect 0 bidi/tag/zero-width/C1 in harness fields; probe passages are AgentDojo templates (counted, not defects) |
| L1-04 duplicates | yes, within part | 0 byte-identical candidate files; identical trajectory fingerprints expected only between paired arms of the same probe × entry (e.g. p10 observe vs model block for user/agent: task-only runs; p2 vs p3-5 where no block fired); cross-corpus: none expected |
| L1-05 arm coverage | yes | §2 design; missing/extra cells as listed |
| L1-06 secrets / account paths | yes | counts and pointers only; canaries (`RX-` + 6 hex) are harmless goal tokens, not secrets; endpoints 127.0.0.1; expect 0 secrets and 0 account paths in run rows |
| L1-07 timestamps | yes | message `created_at` ISO 8601 UTC `Z` with microseconds, non-decreasing within each run (1,080/1,080); range inside the study window (H-12) |
| L1-08 degenerate | yes | 0 empty files, 0 zero-message runs, `error` null 1,080; 40 runs with no agent turn are valid `outcome_only` (not degenerate); 190 non-run rows counted separately |
| L2 sample | whole part | files are selected whole, 14 < 30: all 1,080 executions + 190 register rows |
| L2 A2 error classes | yes | expect only the issue codes of §4 |
| L2 A3 PROV classes | yes | 0 dangling/missing results (1,120 calls ↔ 1,120 results), 0 time edges (by design), no invented relation for the 84 unjoined guard rows |
| L2 evidence classes | yes | D for call-id links, `generated_by`, guard digest joins; `_unverified` twins (I) for task template, request log as model input, memory query, ingest agent, config model, block replacement |
| L2 degenerate / `adapter_defect` | yes | expect 0 / 0 |
| L2 identity | yes | actors researcher, writer, selector (p13), ingest, harness, env, guards `guard_deberta` (revision `90c9989b…`), `guard_llm`, `guard_keyword` (p10); model `qwen/qwen3.5-9b` requested, served `not_recorded` |
| L2 redaction | check only | no `[redact]` table; expect 0 account segments in AER/SEM/PROV |
| L2 withholding | check only | no `[withhold]` table; expect 0 withheld executions |
| L2 SEM | yes | `autogen.tools@1`: `canary_present`, `attacker_tool_called` (28 calls), `keyword_stop` (210), injection markers (512) |
| L2 outcome sanity | yes | §3 on the test-carrier cells; off-test p2 rows reported without a verdict |
| L2 determinism | yes | second import with another `--jobs`, byte-identical; `recompute --dry-run` 0 differences; `verify --level chain` on a sealed copy |

## 6. Hypotheses (falsifiable, thresholds)

| Id | Lead | Expectation | Fails if |
|---|---|---|---|
| H-01 | L-06 | 109 members; member paths (prefix `autogen-guard-placement/` removed) = HEAD blob paths minus `paper/`; git-blob id of every `results/**` member equals its HEAD blob id | any path or id differs |
| H-02 | — | 14 run files, 1,270 rows, run rows per file as §1, 190 non-run rows (150/20/20); `run_id` unique over 1,080 | any count differs |
| H-03 | L-01 | phase 2 = 85 distinct `probe_id` × 4 entries; exactly 120 rows on test carriers (30 probes) and 220 off-test; every other team phase has 0 off-test rows | otherwise |
| H-04 | L-02, L-05 | the 240 rows without `stop_reason` are all phase 2 and form one time block that ends before the first phase-2 row with `stop_reason` begins | rows interleave in time, or any non-phase-2 row lacks it |
| H-05 | L-05 | every message `created_at` lies in [2026-09-20T00:00Z, 2026-09-25T14:28:00Z] (before the first commit); report how many precede the phase-0 capture 2026-09-24T13:12:38Z (expected 0) | any outside the window; > 0 before the capture is reported as an identity caveat |
| H-06 | L-03 | 0 `runs_errors.jsonl` members; `error` null in 1,080/1,080 | any errors file or non-null error |
| H-07 | L-04 | 267 ThoughtEvents (writer 229, researcher 38); report by phase | count differs (the phase split is descriptive) |
| H-08 | L-09 | phase-12 rows have no `modes`; phases 10/12/13 have no `block_guard`; phases 2-6 `block_guard` `llm` (630) | otherwise |
| H-09 | — | entries 345/255/255/225; `modes` 560/180/120/60; stops 760/80/240; probe joins 830/170/80 | any differs |
| H-10 | L-10 | phase 6: runs with ≥ 1 attacker call = 6/2/5/3 (none/model/bus/tool), 28 attacker calls in total | otherwise |
| H-11 | — | p2/p3/p4/p5/p12/p13 test-carrier goal breaches equal §3 cell by cell (total 111) | any cell differs by ≥ 1 → investigate; ≥ 15 points on a 40-run aggregate → finding |
| H-12 | — | p10 early stops 40/0/40/0/0/0 by condition; 40 runs without a model call = user + agent entries of observe and model block (the condition split is inferred from the paper's early-stop cells; the census names only phase 10, entries user and agent) | otherwise |
| H-13 | — | 0 canary hits in any benign run (all phases) | ≥ 1 |
| H-14 | — | L2: 0 failures, 0 degenerate, 0 `adapter_defect`; issue codes and counts as §4 (588/87/49/40/4/3) | any other code, or a count differs (L-08 decides which unit) |
| H-15 | — | 1,120 tool calls ↔ 1,120 results, 0 orphans; 4 `invalid` executions | otherwise |
| H-16 | — | 0 account paths and 0 secret-shaped strings in raw run rows and in AER/SEM/PROV | ≥ 1 (security report at once) |
| H-17 | — | 0 byte-identical candidate files; identical trajectory fingerprints occur only within one probe × entry across paired arms | a repeat across different probes or entries |
| H-18 | — | determinism: two imports with different `--jobs` byte-identical; `recompute --dry-run` 0 differences; chain verify 0 failed | any difference |
| H-19 | L-07 | the L2 register has 190 line-level rows and no file-level entry (contradicting the stale registry/profile/artefact text) | file-level entries appear |

## 7. Expected movement (no E2 baseline; against the phase-10n trial at `3015cf7a`)

| Change since the trial (on `065b0d36`) | Expected on this corpus |
|---|---|
| D-323 (streamed multi-execution, profile limits; `658a5c18`..`24d27c27`) | no AER body change (files ≤ 2.4 MB, under default limits); runner/ingest code digests move |
| Regen items 9/11 (D-372 completeness rule) and ingest-formats-3 (D-380..D-387) | stage identities and code digests move; no AER/SEM/PROV body change expected |
| D-31 / D-460 (rules versions, `aer.rules.drift`) | AER `rules` declarations at current versions; digests differ from the 10n trial |
| Item 7 (lone surrogates) | not adopted by the autogen mapper (regen-batch "not covered"); no change |
| Counts | identical to §8/§9: 1,080 executions, 190 register rows, same issue counts |

## 8. Fact-check (adversarial, 2026-10-14)

Re-opened at the cited sources (desk only; no raw data read, nothing computed from it). Repository files read as data at
`1da92ac7`; Zenodo and GitHub through their APIs.

**Confirmed.**
- Pin: Zenodo 23025259 is the only version of concept 23025258 (versions query: 1 hit), v1.0, created 2026-09-28T22:42:41Z,
  published 2026-09-29, licence `cc-by-4.0`, one file `autogen-guard-placement-data-code-v1.0.zip`, 4,978,620 B,
  md5 `800a67afee7bef77cdbea9df9920b33c`. This equals the profile's `[[source.pins]]` size and md5. The sha256 cannot be
  checked against Zenodo, which publishes md5 only (https://zenodo.org/api/records/23025259).
- Repository: created 2026-09-25T14:24:04Z, MIT, 0 issues, 0 tags, 0 releases. It has two commits, `a6675f8f` with 143
  blobs (33 under `paper/`) and `1da92ac7` with 138 blobs (29 under `paper/`). 138 − 29 = 109. The 14 `runs.jsonl`
  blob sizes match §1 exactly, and HEAD has no `runs_errors.jsonl`.
- Every §3 paper cell matches its source: `tab_defenses.tex`, `tab_blocking.tex`, `tab_keyword.tex` and `macros.tex`
  (Two*/BlockModel*/BlockBus*/BlockTool*/TwelveSpotlight*/TwelveSandwich*/Thirteen*/Six*Called*/Ten*EarlyStop*/
  HandBreaches 111/HandObeyed 103/HandOtherWording 8/MemRaw 27/29/MemWrapped 17/29/TwoBenignCanaryHits 0/TwoRuns 120/
  TenRuns 210/TwelveRuns 160/ThirteenRuns 80/SixCases 20). The optional cells match too: first hop, LLM-guard catch,
  benign done, and Six prevented/induced.
- Metric definitions in `src/analyze.py` behave as §3 describes. The tool goal is the canary in `tool_calls[].text`;
  the harness appends only `save_note` (and phase-6 attacker calls) to that list. The output goal is the canary in the
  writer's last `TextMessage`. Early stop is the text `'TERMINATE' mentioned` in `stop_reason`. `phase2()` filters to
  `test_carriers`.
- The paper is the source of these logs. `Paper.tex` has the same title as the Zenodo record and the same author ORCID
  (0009-0003-7136-7168), and LICENSE-DATA names the paper and the artifact as the attribution. No arXiv, Crossref or
  ORCID listing was found.
- Licence: LICENSE-DATA (CC BY 4.0, (c) 2026 Mohammadreza Rashidi, covering data/ and results/), LICENSE (MIT),
  LICENSE-THIRD-PARTY (AgentDojo @089ed468 MIT, InjecAgent @f19c9f2c MIT, NotInject MIT) and the Zenodo licence all
  agree. Nothing restricts use beyond attribution.
- Harness and versions: `requirements.txt` and `env_listing.json` give AutoGen 0.7.5, Python 3.11.16, openai 3.19.2 and
  `echo_reasoning_chars` 0. The python-v0.7.5 tag is commit `83afbf58`, released 2025-09-30. AutoGen issues #8282,
  #8293 and #8277 exist, are open and have the titles summarised. `harness.py` always writes `stop_reason` (L-02).
  `config_listing.json` lacks `llm27`, `test_carriers`, `panel` and `gateway_*` (L-11).
- Our own documents: the census figures (phase10n README §2), the §7.1/§8 issue counts (139/69 against 87/49, L-08)
  and the stale registry caveat and `non_run_rows` text (L-07) are as quoted.

**Corrected.**
1. The arXiv title search for "Guard Placement" returns 2 unrelated hits (wireless localization, 2006/2007), not 0. The
   conclusion that the paper is not on arXiv stands. *(research.json)*
2. Commit `1da92ac7` changed more than research.json said. Besides the diagram PDFs, the figure checker and
   NBreakTests 33→34, it changed README.md, .gitignore, build.sh, `results/check_tests.json`, `results/macros.json`
   (NBreakTests only) and `src/test_checks.py`. It removed four `paper/figures/*.html` and `src/make_studio_figure.py`
   (hence 143→138 blobs). No `results/phase*` file and no result macro changed. *(research.json)*
3. "Missing by design: bus blocking for tool and memory entries" holds for phase 4 only. Phase 10 has bus blocking for
   all four entries, and phase 6 has it for the tool entry. *(§2)*
4. `MemRawN` 29 counts the memory attack runs that have both a wrapped and a raw guard scan (`memory_wrapper` keeps
   pairs only). The paper says "every phase-2 memory run on an attack probe". The off-test figure is therefore a lower
   bound: at least 19 off-test memory attack runs. *(§3, research.json)*
5. `M:HandBreaches` is the number of labels in `results/handread.json`, not a sum of goal cells. That 111 equals the cell
   sum is a cross-check, not a definition. *(§3)*
6. Phases 3-5 have no `*Errors` macro. The statement "every `*Errors` macro 0" covers only the macros that exist.
   *(§1)*
7. The "Records" row in §1 comes from the in-memory mapping (§7.1), not a trial. *(§1)*
8. H-12's split of the 40 runs without a model call (observe plus model block) is inferred from the paper's cells. The
   census names only phase 10, entries user and agent. *(§6)*

**Added context (from documents, no new data expectation).** The paper says that phases 2 to 6 and 8 to 10 use the 10
test carriers (Limitations; Results). It also says the memory comparison uses every phase-2 memory attack run. Both
statements together support L-01. `analyze.py load_phase` keeps the last attempt of an interrupted run that was re-run
under the same id, which is relevant to L-03 and the aborted-attempt question.

**Unverifiable here.** The zip's sha256 and its member list against HEAD blob ids (H-01, left for L1). Whether the 240
`stop_reason`-less rows predate the published harness (L-02/L-05, left for L1).
