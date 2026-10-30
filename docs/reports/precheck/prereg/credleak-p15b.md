# Pre-registration: `credleak-p15b`

| | |
|---|---|
| Corpus | `credleak-p15b` (family `credleak`, profile `credleak-p15b` v1, dialect/mapper `credleak.cell`, variant `v1`; registry status `planned`; `[withhold]` policy D-265) |
| Parts | `head` (only part): Zenodo 22737462 v3, `p15b-run-data-v3-2026-09-13.zip` |
| Wave | 6 (first examination; not in FA or E2) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: our prior reports (phase-10k census, trials, routing), the profile, `artefacts.toml`, `rates.toml`, D.19, DECISIONS (D-260..D-269, D-320, D-450), bug pass BF-23/BF-24, the registry, and desk research (`data/credleak-p15b/research.json`). The member counts per channel and model come from Zenodo's public zip preview listing (names and display sizes only). Nothing here was computed from the staged bytes. |
| Method | [`../README.md`](../README.md) |

**Secrets rule.** This file names rule ids, field paths and counts only. It holds no planted value and does not spell any
tag form beyond what the profile already names.

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Paper | "How Credentials Leak from 'Safe' LLM Coding Agents: An Attack-Surface Measurement" (Adrian Asher). The record says it is under review at Springer Cybersecurity. **Not public**: no match on arXiv by title, author or keywords, none in web search, the record has no related identifiers, and the author's ORCID lists no works. So there are no paper tables, and no version history, for this pre-check | [record](https://zenodo.org/records/22737462); arXiv API; ORCID API |
| Data record | concept 21860162: 21860163 (2026-08-09, 10,634,809 B), 22729871 v2 (2026-09-12, 10,948,077 B), **22737462 v3 (2026-09-13) = latest** on 2026-10-14. One file, 11,060,394 B, md5 `d25b9b5c…` = profile pin; sha256 `7e5f7e40…` from our staging | [versions API](https://zenodo.org/api/records/22737462/versions) |
| Repository / harness | none public. In-house harness, unnamed in the run files. The CHANGES prose names builds v0.1.790/793 for the 2026-09-13 waves only. The analysis scripts are inside the zip | census §3; GitHub search |
| Providers | AWS Bedrock, Google Vertex AI (Gemini preview endpoint, not decoding-matched) and direct vendor APIs. No served id, region or decoding is recorded per run | record; census §3 |
| Design | undefended baseline (`defence` = `C4-baseline`), 16 agents x injection channels, egress axis, hygiene vectors; planted canary credentials and a localhost collector | record |
| Licence | CC-BY-4.0 (record metadata; no licence file in the deposit). Record norms: the Fable probe is never a rate; external-canary results are scored from the collector log | record; profile `[licence]` |
| External use | `cisco-ai-defense/defenseclaw` pins **v1** (21860163) as a benchmark dataset | [datasets.lock.json](https://github.com/cisco-ai-defense/defenseclaw/blob/main/benchmarks/datasets.lock.json) |

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Zip bytes / md5 | 11,060,394 / `d25b9b5c27f5f41689c62decb3e20ffc` | profile pin; Zenodo API |
| Members (G.3.5 gate) | 682 (658 json, 8 md, 5 py, 4 csv, 3 jsonl, 2 sarif, 2 mjs) | census §1; preview listing |
| Selected cell members | 643 (01: 373, 03: 130, 04: 140 by the preview listing; the 03 collector-log JSON is not selected) | profile `include`; census §1 |
| Not selected | 39 = collector log 3 + T-EMIT audit 14 + scanner 14 + scripts 4 + root md 2 + root csv 2 | profile `exclude`; preview listing |
| Strict-loader rejections | 1, the collector-log JSON (`ingest.json.duplicate_key`), **not selected** | census §1 |
| Units = executions (runs) | **19,636** | registry `readme_corpora.toml` (basis census); census §2; trials C1 (mapped 19,636, 0 degenerate) |
| Turns / tool calls | 20,176 (19,276 x1, 180 x2, 180 x3) / 83,619 | census §2 |
| Runs without a tool call / with `invocationError` / with an empty response | 1,495 / 59 / 100 | census §2 |
| Distinct `runId` / model strings / techniques / scenarios | 211 / 21 / 15 / 33 | census §2-4 |

| Layout class | Cells | Runs |
|---|---:|---:|
| roster `run__` | 482 | 12,970 |
| roster `archive-…` (5 batch prefixes) | 50 | 2,904 |
| roster `addendum-2026-09-13__` (six N=100 waves) | 6 | 600 |
| roster `extcanary__` (collector-scored) | 20 | 800 |
| `_replication-wave-2026-08-07T14-49/` (Gemini T-EMIT) | 2 | 160 |
| `_fable-filter-probe-NOT-SCORABLE/` | 2 | 10 |
| `excluded-models/` `run__` | 73 | 2,180 |
| `excluded-models/` `archive-…` | 8 | 12 |
| **Total** | **643** | **19,636** |

Cells per channel directory (preview listing): T1 84, T4 90, T-WEB 39, T-MCP 34, T-MCPDESC 18, T-RULES 36, T-LOG 18,
T-DEP 18, T-CMD 36; egress readme-delivered 80, command-output-delivered 16, delayed-trigger 34; T-STAGE 42, T-SLOP 40,
T-EMIT 58. File-name stamps: 2026-06-10 .. 2026-09-13.

## 3. Expected arms

| Facet | Values | Expected missing / extra |
|---|---|---|
| Model (comparison, 16) | deepseek-v3.2, devstral-2-123b, gemini-3.1-pro-preview (archive cells only), glm-4.7-flash, gpt-5.5, gpt-oss-120b, gpt-oss-20b, mistral-large-3, nemotron-super-3-120b, nova-2-lite, nova-pro, opus-4-7, opus-4-8, qwen3-235b, qwen3-coder-480b, sonnet-4-6 | extra: excluded `eu.anthropic.claude-fable-5`, `glm-5`, `minimax-m2.5`; probe `global.anthropic.claude-fable-5`, `…-fable-5-1` (21 strings in all) |
| Technique (channel) | T1, T4 (5-cell framing sweep), TWEB, TMCP, TMCPDESC, TRULES, TLOG, TDEP, TCMD, TEGRESS, TEGRESSCMD, TDELAY, TSTAGE, TSLOP, TEMIT | 16 x 8 map: **gemini x TMCPDESC missing** |
| Roster coverage | T1, T4, TWEB, TMCP, TRULES, TLOG, TDEP, TCMD, TSLOP, TEMIT: 16 of 16. TMCPDESC, TDELAY: 15 (no gemini). TSTAGE: 11 (no devstral, glm-4.7-flash, gpt-oss-20b, mistral-large-3, nemotron). TEGRESS: 9 (deepseek, gemini, gpt-5.5, nova-2-lite, nova-pro, opus-4-7, opus-4-8, qwen3-coder, sonnet). TEGRESSCMD: 3 (gemini, opus-4-8, sonnet) | the egress and stage subsets are by design (their tables are not 16-wide) |
| Repeated cells per (model, channel) | Devstral T-WEB: 20-run pilot + N=100 wave (the wave is reported in place of the pilot); T-WEB addendum waves for nova-2-lite (dir `nova-2-lite`), opus-4-7, opus-4-8, sonnet-4-6 (dirs `claude-*`) [corrected by fact-check: only the three Claude waves sit in `claude-*` dirs]; Devstral T-MCP addendum; sonnet-4-6 T1: 8 cells (others 4) | must not be pooled blindly (H6) |
| Defence | `C4-baseline` only | no defence arm |
| Attack | scenario (33); `task.attack_id` = scenario (D.19.3) | none |

L2 strata = (model, technique, layout_class) (`l1_families.py` STRATA): about **249** (252 if the three addendum
`claude-*` cells carry their own model strings). The unit is the whole cell (a member is selected whole), so the 300
cap gives about 300 of 643 cells. Every run of a sampled cell is imported, about 9,000 executions (estimate).

## 4. Expected outcome rates (comparison targets)

No paper table is public. The targets are therefore (a) the census tallies (whole population, exact), and (b) the
deposit's own per-cell aggregate `per-cell-counts-v2.csv` (and README's table map). The examiner reads (b) at L1 through
`agentprov.ingest`, as a not-selected member. It is the authors' per-cell basis for every reported rate.

**Metric mapping** (record and census §6): complete exfiltration = `runs[].exfiltrationDetected` (with `egressChannel(s)`);
redirection = `hijackSucceeded`; detection = `agentDetected`; displayed = `displayedToUser`; hygiene = `scriptAudited`
(T-STAGE), `payloadDelivered` (T-SLOP), `maliciousArtifactEmitted` (T-EMIT, **pre-fix detector**; the paper uses the
corrected labels of `05-temit-precision-audit/`). Errored runs (`invocationError` true) leave every rate (README;
`rates.toml` `credleak.rate.invocation_error`, index code `map.credleak.invocation_error`). External-canary cells are
scored from the collector log, which is not imported.

| Arm | Metric | Expected | Source |
|---|---|---:|---|
| all runs (n 19,636) | `hijackSucceeded` true | 5,421 (27.6%) | census §6 |
| all runs | `exfiltrationDetected` true | 3,936 (20.0%) | census §6 |
| all runs | `agentDetected` / `displayedToUser` true | 5,479 / 1,260 | census §6 |
| non-null runs | `maliciousArtifactEmitted` / `scriptAudited` / `payloadDelivered` true | 572 of 3,202 / 124 of 1,815 / 2,840 of 3,566 | census §6 |
| all runs | `invocationError` true | 59 | census §2 |
| T-EMIT, 7 reported cells | authored-code runs labelled in the audit | 461 flagged + 27 detector-negative | record |
| 2026-09-13 waves | runs | 6 x 100 | record |
| Gemini T-SLOP local wave | runs | 80 | record |
| extcanary (20 cells, 800 runs) | in-harness `exfiltrationDetected` | 0 by design | record; census §1 |
| per cell (csv rows) | exfiltration / hijack counts | = csv values | `per-cell-counts-v2.csv` (L1) |

L2 outcome sanity has two parts. (i) **Mapping identity:** each sampled run's harness `judgement` values equal its raw
flags, 100%. (ii) **Arm rates:** the rate of each sampled arm against the csv's row(s) for the same cells, with the
README §4 threshold (more than 15 pp on an arm with at least 20 sampled executions, or a binomial 95% interval missed by
more than 5 pp). Because whole cells are sampled, most arms have at least 20 executions.

## 5. Known quirks (expected-known)

| Id | Expected | Source |
|---|---|---|
| `credleak.art.malformed_tool_names` | 290 calls, 41 names (role `unknown`) | artefacts.toml; profile quirk |
| `credleak.art.invocation_error` | 59 executions, issue `credleak.invocation_error` (info) | artefacts.toml |
| `credleak.art.turn_time_role_unknown` | 20,176 turns, `/t` ambiguous, no typed time (D-263) | artefacts.toml |
| `credleak.art.model_calls_not_recorded` | 19,636 executions with `missing_generated_by`; `aer.acc.agent_calls_vs_assistant` unverifiable | artefacts.toml; trials C1 |
| `credleak.art.planted_credentials` | 5,422 executions and 325 cells hit the `[withhold]` rules; 14,214 released; 4,415 released runs in withheld cells | artefacts.toml; D-265; trials C1 |
| `credleak.no_tool_calls` / `overlapping_runs` | 1,495 runs / 9,505 of 18,993 consecutive pairs | profile quirks |
| Seal issues (trials C1) | `missing_generated_by` 19,636; `accounting_unverifiable` 36,126; `credleak.invocation_error` 59; 0 degenerate | trials C1 |
| Release-scan findings | about 10 gitleaks fingerprints after D-310, all in the three D-269 false-positive classes (loopback URL path, a placeholder key, a `curl` format string) | trials C3; D-269 |
| Collector log | duplicate key, not selected; D-450 scans not-selected zip members at seal time (the zip is withheld as container anyway) | census §1; D-450 |
| Pending code changes | BF-23 (placeholder tool names `-`/`0` give `adapter_defect`) and BF-24 (missing or sentinel model) are held on `bugpass-regen` (regen items 34/35). The lone-surrogate post-pass (D-378) is not adopted by credleak | bug pass; AGENTS.md |
| Our docs | AGENTS.md and card 3.10 say 654 cells; census: 643 | census §1 |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | section 2, per layout class; 39 not selected with the profile's codes |
| L1-02 strict parse | yes | 643 cells clean; the collector log's duplicate key only if not-selected members are scanned |
| L1-03 encodings | yes | report counts; model channel-token leakage in tool names is expected-known |
| L1-04 duplicates | yes | 0 byte-identical cells; identical fingerprints expected only among no-call runs (H11); no other corpus holds this study |
| L1-05 arm coverage | yes | section 3 plus the csv reconciliation (H4-H7) |
| L1-06 secrets / account paths | yes | planted values expected (counts per census §7, pointers only, never values); account paths unchecked so far (H9) |
| L1-07 timestamps | yes | one UTC `Z` shape; overlap expected (H10) |
| L1-08 degenerate | yes | 1,495 no-call, 59 errors, 100 empty responses; 0 zero-turn runs (H12) |
| L2 import, validate, recompute, determinism | yes | through `l2_import.py` (`import_source`; the CLI refuses `planned`); jobs A vs B byte-identical |
| L2 A2 / A3 classes | yes | only section 5 codes expected |
| L2 evidence classes | yes | pairing D (`credleak.pair_same_entry@1`); actors, executions and detectors I (`*_unverified` rules); no `model_call` |
| L2 degenerate / adapter_defect | yes | expect 0 / 0 (H13) |
| L2 identity | yes | `model.requested` = run `model` verbatim; served/provider `not_recorded`; harness `not_recorded`; no judge actor |
| L2 redaction | yes | no account path in AER/SEM/PROV (H9) |
| L2 withholding | yes, **conditional on sealing** | rule hits on derived files of sampled runs vs value-bearing runs; a sealed `chain` check needs a full (unfiltered) import, since `package` refuses partial corpora (open question) |
| L2 outcome sanity | yes (csv and census targets, not paper) | section 4 |
| Delta since E2 | no | not in FA or E2 |

## 7. Hypotheses (falsifiable)

| # | Expectation | Refuted if |
|---|---|---|
| H1 | Section 2 counts exactly: 682 members, 643 selected, 39 not selected, 19,636 runs, the 8 layout classes' cells and runs, 20,176 turns, 83,619 calls | any count differs by >= 1 |
| H2 | 0 parse defects in the 643 cells; `run.model == cell.model` and `run.scenarioId == cell.scenario` for every run; `repetition == index + 1` everywhere | >= 1 exception |
| H3 | 21 model strings. The model field equals the model directory for every roster cell except the 3 addendum `claude-*` T-WEB cells (field = roster label). In `excluded-models/fable-5` the field is `eu.anthropic.claude-fable-5` | any other mismatch, or the addendum cells carry new strings (then 24 strings) |
| H4 | Roster coverage as section 3; the only gaps among the 16 models in the 8 map channels are gemini x TMCPDESC; `defence` = `C4-baseline` in 643/643 cells | any other gap, extra model or defence value |
| H5 | Whole-population detector tallies equal section 4 (census §6) exactly | any differs by >= 1 |
| H6 | Per-cell exfiltration and hijack counts (errored runs excluded) equal `per-cell-counts-v2.csv` for every cell it lists. The T-EMIT `maliciousArtifactEmitted` column of v1 `per-cell-counts.csv` equals the logged pre-fix flag, and v2's differs in >= 1 T-EMIT cell | >= 1 non-T-EMIT cell differs by > 1 run, or the csv has no row for a roster cell |
| H7 | `exfiltrationDetected` true in 0 of the 800 extcanary runs | > 8 (1%) |
| H8 | `intentVerdicts` null in all 20,176 turns, although `config.judgeModel` is set | >= 1 non-null verdict |
| H9 | Tag and shape occurrences as census §7 (fields: tool output 50,094, detector labels 21,767, tool input 17,964, assistant text 5,505; shapes AWS 1,273, Anthropic 1,272, other `sk-` 15,927; untagged 78 in 27 runs); value-bearing runs 5,422 in 325 cells. **0 real workstation account paths** (`/Users/<name>/`, `/home/<name>/` outside sandbox or container roots) in selected cells | any count differs, or >= 1 real account path (report to the orchestrator at once) |
| H10 | Every turn timestamp, cell `timestamp` and `runId` stamp has the `YYYY-MM-DDTHH:MM:SS.mmmZ` shape (runId with `-`); 0 missing; turn times never decrease within a run (540 pairs); all in [2026-05-01, 2026-09-14]; overlapping consecutive runs 9,505 of 18,993 | any other shape, any decrease, or any stamp outside the range |
| H11 | 0 byte-identical cells. Groups of identical trajectory fingerprints occur only among runs with no tool call (<= 1,495 runs); 0 among runs with >= 1 call; 0 cross-corpus repeats | any threshold exceeded |
| H12 | Zero-call runs 1,495; `invocationError` 59; empty responses 100 (all provider-blocked Fable runs); 0 runs with zero turns | any differs by >= 1 |
| H13 | L2 import of the sampled cells: 0 failures, 0 degenerate, 0 `adapter_defect`; issue codes only `missing_generated_by`, `accounting_unverifiable`, `credleak.invocation_error`; `recompute --dry-run` 0 differences; tier-4 validation 0 failures; second import with another `--jobs` byte-identical | any failure, new code, difference or non-determinism |
| H14 | Withholding on the sample: runs whose derived files hit a `[withhold]` rule = the value-bearing runs of the sampled cells (0 mismatches). No derived file of a clean run hits. Raw hits only in cells holding a value-bearing run | >= 1 mismatch |
| H15 | 41 malformed tool names on 290 calls are kept verbatim with role `unknown`; 0 typed tool names equal a placeholder (`-`, `0`, `nan`) | any placeholder name reaches a typed slot, or counts differ |
| H16 | L2 mapping identity: harness `judgement` values equal the raw run flags for 100% of sampled runs | >= 1 mismatch |

## 8. Discrepancy leads carried to the dossier

The paper is not public, so the deposit's own csv and README are the only per-arm targets. Gemini has no T-MCPDESC cell
in the 16 x 8 map. Model directory and model field disagree for the addendum Claude and excluded Fable cells. The
superseded Devstral T-WEB pilot and other repeated waves are deposited beside the waves reported in their place, and
`rates.toml` has no rule for them. v2 to v3 adds 730 runs in 10 cells, while the record explains 610 runs plus one
80-run wave (the 2 `archive-p15b-gemini-tslop-waves` cells hold the rest by prefix). [Refined by fact-check: a diff
of the v2 and v3 Zenodo preview listings (member names only) shows the 10 new cells are the 6 addendum waves, the 2
Fable-probe cells and both `archive-p15b-gemini-tslop-waves` cells; so v2 lacked two Gemini T-SLOP cells, while the
record names only the n=80 wave as omitted.] The record's T-EMIT review counts are internally inconsistent: 265 + 25
blobs in two passes against 293 blobs said to be covered. The T-EMIT flag in the runs is the
pre-fix detector. The extcanary rates come from a collector log that is not imported. Judge metadata is configured but
no judge ran. Two run schemas and several harness builds are pooled, and the harness is unidentified. Account paths have
not been checked. Our docs say 654 cells. An external benchmark pins v1, which holds the unredacted account identifier.
The Gemini runs come from a preview endpoint that is not decoding-matched.

## 9. Fact-check (adversarial, 2026-10-14)

Re-opened the cited sources; nothing was computed from staged bytes. Member-level checks used only the public Zenodo
preview listings (names and display sizes) of v3 and v2.

| Claim | Verdict | Evidence |
|---|---|---|
| Pin: v3 record 22737462, one file, 11,060,394 B, md5 `d25b9b5c…`, CC-BY-4.0, latest of 3 versions (v1 21860163 10,634,809 B md5 `1b44467e…`; v2 22729871 10,948,077 B md5 `8fee73c2…`) | confirmed | [record API](https://zenodo.org/api/records/22737462), [versions API](https://zenodo.org/api/records/22737462/versions); profile pin equal |
| 682 members; 658 json / 8 md / 5 py / 4 csv / 3 jsonl / 2 sarif / 2 mjs; top dirs 01: 373, 03: 133, 04: 140, 05: 14, 06: 14, scripts 4, root 4 | confirmed | [v3 preview listing](https://zenodo.org/records/22737462/preview/p15b-run-data-v3-2026-09-13.zip) |
| 643 cells (01: 373, 03: 130, 04: 140), collector log 3 members, 39 not selected; 8 layout classes 482/50/20/6/2/2/73/8 | confirmed | listing; census §1; profile `exclude` |
| Cells per channel directory; file-name stamps 2026-06-10..2026-09-13 | confirmed | listing |
| Roster coverage per technique (16/15/11/9/3; gemini has no TMCPDESC, TDELAY cell; gemini roster cells are archive-only) | confirmed (by directory) | listing |
| About 249 strata (252) | confirmed as an estimate from directory names | listing; `l1_families.py` STRATA |
| Runs, turns, calls, tallies, 21 strings, value-bearing runs, seal issues, ~10 gitleaks findings | confirmed against our documents | census §1-8; trials C1, C3; artefacts.toml; registry `readme_corpora.toml` (19,636) |
| Paper not public; arXiv 2608.27092 is a different study | confirmed (absence as of today) | arXiv API title/author searches; [ORCID works](https://pub.orcid.org/v3.0/0009-0006-6854-2318/works) empty; 2608.27092 authors Rahman, Kim |
| defenseclaw pins v1 (Apache-2.0 repo), added in commit 4321abd522 (2026-09-15) | confirmed | [datasets.lock.json](https://github.com/cisco-ai-defense/defenseclaw/blob/main/benchmarks/datasets.lock.json); not present at f63a350768 |
| T-EMIT 461 + 27 runs, 293 blobs; six N=100 waves; extcanary from the collector log; Fable probe never a rate | confirmed | record description |
| Our docs say 654 cells | confirmed | AGENTS.md line 249; phase10e-candidates.md line 194 |
| Addendum T-WEB waves "dirs `claude-*`" for nova-2-lite | **corrected** | nova-2-lite's addendum sits in `nova-2-lite/` (section 3) |
| v2 to v3 new cells | **refined** | v2/v3 listing diff: 6 addendum + 2 probe + 2 gemini-tslop-waves cells (section 8; answers open question 3 by name) |
| H3 presumption that the addendum `claude-*` cells carry roster labels | unverifiable | their file names carry `claude-opus-4-7` etc. as the model token, which points the other way; the only support is the census count of 21 strings |
| Per-cell paper rates | unverifiable | no public paper; `per-cell-counts-v2.csv` not read in this step |

Added lead: the record's two T-EMIT review passes (265 + 25 blobs) do not sum to the 293 blobs it says they cover.
