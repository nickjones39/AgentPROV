# Pre-registration: `kavach-agentdojo`

| | |
|---|---|
| Corpus | `kavach-agentdojo` (family `agentdojo`, profile `kavach-agentdojo` v1, dialect/mapper `agentdojo.tracelogger`, variants `v1.k14` and `v1.k14.incomplete`, SEM `agentdojo.suites@2`, identity table `kavach_run_dirs`) |
| Parts (snapshots, import order) | `main`: GitHub `Ishani018/Kavach` @ `53df95452fb5fb207a0c3b5127e84e925e71fbf4` (2026-08-30). `nav-fixer2` @ `f2dd7efa01aed5a4d92e86e9d2ead5f19a326ab7` (2026-07-21). `rearch-forcedformat-fix` @ `6b31a5546b152c93435772bb4f3521dd78ee3446` (2026-07-17). One corpus with three snapshots: 2,625 distinct executions (D-95, D-202, D-253) |
| Wave | 7. Full pre-check. The corpus was not examined in FA or E2, so there is no delta since E2 |
| Code commit | `065b0d36` or later on branch `precheck-corpora` (written at `6b76c15e`) |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Inputs: our own reports (phase-10j census §5 and trials §1, phase-10d deferred, shortlist row 10), the profile, the identity table, the registry, `artefacts.toml` and DECISIONS. Also desk research (`data/kavach-agentdojo/research.json`): GitHub API metadata (branches, commits, trees with blob ids and sizes) and documentation files. No log was read and nothing was computed from log bytes |
| Method | [`../README.md`](../README.md) |

## 1. Sources (details and URLs in `research.json`)

- **Repository.** <https://github.com/Ishani018/Kavach> (MIT; created 2026-05-25). It has 9 issues (3 open) and 2 open PRs, none about these logs (**corrected by fact-check**; was "0 issues and 5 open PRs": GitHub's open count of 5 is 3 issues + 2 PRs). It has 9 branches, and all three pins are still branch heads.
  - The six unpinned branches hold exactly `main`'s 223 log blobs (same paths, same ids). No run-bearing branch is missed (this confirms D-95).
  - `main`'s README lists `nav-fixer2` and `rearch-forcedformat-fix` as archived branches that were never merged.
- **When the run directories were added** (commits API, filtered by path):

| Directory (under `benchmarks/`) | Added | Commit (author) | Note |
|---|---|---|---|
| `results_v2/agentdojo_slack_gemma_dell/` | 2026-07-06T07:52Z | `8b2498ad` (Ms-riya) | Marked invalid at merge `9e00ac41` (`INVALID_README.md`) |
| `agentdojo_live/banking_qwen25_7b/` | 2026-07-15 | `de8e8c55` (Ishani) | The commit message describes a preliminary qwen2.5:7b loop in which user_task_0 errored |
| `results_v2/agentdojo_dell/`, `agentdojo_llama3.1/`, `agentdojo_forced_llama3.1/` | 2026-07-16T07:07Z | `cff1fb54` (Parv) | The same commit adds `--force-format` (constrained tool-call decoding through Ollama) |
| `results_v2/agentdojo_workspace_forced/`, `agentdojo_workspace_forced2/` | 2026-07-16T07:30Z | `5f73faa7` (Ms-riya) | The merge base of the two branches |
| rearch: `agentdojo_workspace_not_forced/`, `_not_forced2/` | 2026-07-16T10:03Z | `3ad86ecd` (Ms-riya) | Deletes `workspace_forced` and **git-renames 42 of its files into `not_forced`**, including the summary, which becomes `agentdojo_summary1.json` |
| nav: `results_v2/logs/local/` | 2026-07-21 | `f2dd7efa` (Parv) | 84 logs |

- **Paper.** None is published: there is no arXiv entry and no DOI.
  - The in-repo drafts (`paper/FULL_PAPER_DRAFT.tex`) leave Kavach's AgentDojo ASR as `[TBD]`.
  - The `main` draft's AgentDojo numbers replay AgentDojo's own gpt-4o `runs/` through the server. They are not these logs.
  - The **reference for outcomes is therefore the harness-written run summaries** (`agentdojo_summary*.json`, four directories).
- **Data record.** None (no Zenodo, HF or Figshare record). Integrity rests on the git blob ids. The staging is `~/.agentprov/staging/10c/kavach` (listed, not read).
- **Harness.** AgentDojo 0.1.35, per the logs.
  - No `requirements.txt` at any pin names agentdojo. The profile note "agentdojo per requirements.txt" is wrong (H18).
  - The runner is `benchmarks/run_agentdojo_kavach.py`. It differs between `main` (`fc032d71`) and the branches (`0ea5e4d4`). Its defaults are `--model-id gemma4:26b`, `--benchmark-version v1.2`, `--out …/agentdojo_dell` and `llm_name "local"`.
  - The authors document four harness bugs: the empty-action bug #1 (old results deleted); the Gemma `role=tool` echo (fixed 2026-07-06); the benign-pass crash (fixed 2026-07-11); and `run_fully_defended: false`, meaning calls were not screened.
  - Upstream LocalLLM issues: #150, #202, #219 and #220 (parser and server errors), and #154 (imposed outcomes). Kavach overrides `LocalLLM.query`, so it inherits these only in part.
- **Licence.** MIT ("Copyright (c) 2026 Kavach Team — PES University"). The LICENSE is byte-identical at the three pins. There is no data licence and no use clause. Model-output terms are unassessed (profile).

## 2. Expected counts

| Quantity | `main` | `nav-fixer2` | `rearch-forcedformat-fix` | Source |
|---|---:|---:|---:|---|
| Blobs at pin (present + absent) | 867 (859 + 8) | 1,913 (1,905 + 8) | 1,892 (1,884 + 8) | census `gate`; git trees API |
| Absent blobs | 8 (figures/documents, never logs) | 8 | 8 | census §1 |
| JSON files parsed (census) | 364 ok | 1,629 ok | 1,625 ok | census `parse` |
| Selected logs (3 include globs) | **223** (1,047,737 B; 1,293..15,686 B) | **1,518** (7,090,910 B; max 67,317 B) | **1,518** (7,237,494 B) | census `tracelogger_members`; trees |
| Byte-distinct in pin | 223 | 1,477 (41 in-pin copies) | 1,518 | census; `tools/readme_corpora.toml` (223 / 1,477 / 1,518) |
| Distinct by content (`fp_run`) | 166 (57 groups, 114 files) | 884 (590 groups, 1,183 files) | 956 (561 groups, 1,123 files) | census |
| Variants | v1.k14 222, .incomplete 1 | 1,472 / 5 | 1,513 / 5 | census |
| New executions when imported in order | 223 | 1,254 (264 collapsed: 223 from main, 41 in pin) | 1,148 (370 collapsed: 223 + 147) | trials §1 |
| **Corpus total** | | | **2,625** executions; 634 `dedup.collapsed`; 2,515 ok + 110 ok with issues; 0 failed checks; 109 `identity_unresolved` | trials §1, D-253 |
| Header fields | `attack_type` none 13 / ii 210; `benchmark_version` null 220 / v1.2.2 3 | 84 / 1,393; null 1,474 / 3 | 98 / 1,420; null 1,515 / 3 | census |
| Outcome fields (byte-distinct) | utility T 8 / F 214 / absent 1; security T 12 / F 210 / absent 1 | 47 / 1,425 / 5; 87 / 1,385 / 5 | 63 / 1,450 / 5; 111 / 1,402 / 5 | census |
| System prompt | kavach_runner `2e867516` 220; default `a021a92b` 3 | 1,474 / 3 | 1,515 / 3 | census; profile |
| `error` | null 223 | null 1,477 | null 1,518 | census |
| Timestamps (month) | 2026-07: 223 | 2026-07: 1,477 | 2026-07: 1,518 | census |
| L2 sample (proposed key, §6) | **31** (5 strata; k raised to 9) | **83** (17 strata × 5, banking 3) | **83** (17 strata) | README §4 and amendment 2.1 |

## 3. Expected arms (facets: run directory, the identity key × suite × `attack_dir` × arm `local`/`local-kavach`)

Pair = `user_task_*/important_instructions/injection_task_*.json`. Pre-pass = `injection_task_*/none/none.json`. The counts come from the git trees API at the pins.

| Run directory (`benchmarks/…`) | Suite | Model (identity row) | Defence | `main` | `nav-fixer2` | `rearch` |
|---|---|---|---|---|---|---|
| `agentdojo_live/banking_qwen25_7b/local` | banking | unresolved | none | benign 3 (UT 0–2; 1 incomplete) | 3 (same blobs) | 3 (same) |
| `results_v2/agentdojo_slack_gemma_dell/logs/local` | slack | gemma4:26b | none | pre 5 + pairs 105 (21 UT × IT 1–5) | same blobs | same |
| `…/agentdojo_slack_gemma_dell/logs/local-kavach` | slack | gemma4:26b | kavach | pre 5 + pairs 105 | same | same |
| `results_v2/agentdojo_dell/logs/local` | workspace | unresolved | none | – | pre 14 + pairs 13 (UT 0 only) (1 incomplete) | same blobs |
| `results_v2/agentdojo_forced_llama3.1/logs/local` | workspace | unresolved | none | – | pre 14 + pairs 7 (UT 0) (1 incomplete) | same |
| `results_v2/agentdojo_llama3.1/logs/local` | workspace | unresolved | none | – | pre 7 (1 incomplete) | same |
| `results_v2/agentdojo_workspace_forced2/logs/local` | workspace | unresolved | none | – | pre 8 (1 incomplete) | same |
| `results_v2/agentdojo_workspace_forced/logs/local` | workspace | gemma4:26b | none | – | pre 14 + pairs 560 (40 UT × 14 IT) | absent |
| `…/agentdojo_workspace_forced/logs/local-kavach` | workspace | gemma4:26b | kavach | – | pre 14 + pairs 560 | absent |
| `results_v2/logs/local` | workspace | unresolved | none | – | pre 14 + pairs 70 (UT 0,1,2,3,5 × 14) | absent |
| `results_v2/agentdojo_workspace_not_forced/logs/local` | workspace | gemma4:26b (from a copied summary) | none | – | absent | pre 14 + pairs 70: **the same 84 blobs as nav's `results_v2/logs/local`** |
| `results_v2/agentdojo_workspace_not_forced2/logs/local` | workspace | gemma4:26b | none | – | absent | pre 14 + pairs 560 |
| `…/agentdojo_workspace_not_forced2/logs/local-kavach` | workspace | gemma4:26b | kavach | – | absent | pre 14 + pairs 560 |

- **Totals after collapse.** gemma4:26b: 2,516 executions (220 + 1,148 + 1,148). Unresolved: 109 (3 + 27 + 21 + 7 + 8 + 43). Defence kavach: 1,258; none: 1,367.
- **Missing cells.** No travel suite. No benign (`--benign`) pass anywhere (`benign_utility` is null in every summary). The corrected Slack run (`_fix2`) was never committed. Banking has no attack. Kavach arms are absent for dell, llama, forced2, logs and not_forced.
- **Partial cells.** dell, forced_llama3.1, llama3.1 and forced2 are aborted or chunked runs.
- **Extra cells.** None beyond the census. Nothing is excluded for zero successes (user rule).

## 4. Expected outcome rates (L1 population tally; L2 mapping check)

Mapping (run guide; summary fields):
- `utility_under_attack` = mean(`utility`) over a directory's pair logs.
- `attack_success_rate` = mean(`security`) over the same logs, where `security` True means the injection goal was met.
- Pre-passes enter neither rate; their `security` is the benign constant.
- The reference is the harness summary. It is not a paper, and the Slack summary is source-declared invalid.

| Arm | Pairs | Reference utility | Reference ASR | Expected raw tally | Source |
|---|---:|---|---|---|---|
| slack · local (gemma4:26b) | 105 | 0.0476 | 0.0 | utility 5, security 0 | `agentdojo_slack_gemma_dell/agentdojo_summary.json` (INVALID) |
| slack · local-kavach | 105 | 0.0 | 0.0 | 0 / 0; Kavach 108 calls, 40 blocks | same |
| workspace_forced · local (nav) | 560 | 0.0482 | 0.0 | 27 / 0 | nav `agentdojo_workspace_forced/agentdojo_summary.json` |
| workspace_forced · local-kavach (nav) | 560 | 0.0 | 0.0 | 0 / 0; **0 calls screened**, `run_fully_defended` false | same |
| workspace_not_forced2 · local (rearch) | 560 | 0.0196 | 0.0179 | 11 / 10 | rearch `agentdojo_workspace_not_forced2/agentdojo_summary.json` |
| workspace_not_forced2 · local-kavach (rearch) | 560 | 0.0 | 0.0 | 0 / 0; 0 calls screened | same |
| not_forced (rearch, 70 pairs), dell, llama, logs, banking | – | none (`summary1` is a copy of the forced summary, n 560) | – | Wilson 95% only | – |

- **Census consistency check (no new data).** `main` attacked security True = 0 (12 True = the benign constant). The census totals are consistent with the three branch rows: attacked security True is 6 in nav and 16 in rearch (10 + 6).
- **Sample size.** The L2 sample has about 5 per stratum, so no L2 cell reaches n ≥ 20. The verdict comes from the L1 tally.

## 5. Known quirks (expected-known)

| Id / source | Expected (main / nav / rearch) | Reference |
|---|---|---|
| `benign_security_constant` | files 13 / 98 / 98; origin rule 12 / 95 / 95 | profile |
| `injection_task_as_user_task_prepass` | 10 / 95 / 95 | profile |
| `silent_rerun_last_pass_only` | null-final logs 0 / 0 / 0 | profile |
| `unexecuted_trailing_calls` | 0 / 7 / 6 logs | profile |
| `args_mutated_in_place` | 221 / 380 / 430 files | profile |
| `placeholder_args_never_injection_evidence` | 249 / 749 / 832, all null | profile |
| `incomplete_run` | 1 / 5 / 5 (null outcome 0) | profile |
| `provider_call_id_anomalies` | null ids 249 / 680 / 763 in 221 / 357 / 407 logs; 0 repeated or duplicate | profile |
| `defence_denial_message` (D-113) | `[KAVACH BLOCK` denials **45 / 45 / 45** | profile |
| Invalid directory | 220 slack logs included and disclosed (D-253 Q3) | INVALID_README; D-253 |
| Identity | `pipeline_name` is `local` / `local-kavach` only. Model rows only from run summaries; six directories unresolved (D-92, D-105, D-253) | table; D-253 |
| Content repeats | 650 groups (2,318 files) disclosed, `content_dedup = never` | D-253 |
| Secrets | none in the logs; hits only in unselected files (VAULT patterns, test descriptions); no `[withhold]` (D-257) | census §5, §8 |
| `artefacts.toml` | no entry scoped to `kavach-agentdojo`. Generic classes that may occur: `injection_task_as_user`, `benign_security_constant`, `text_tool_call`, `provider_ids`, `validity_defects` | `adapters/agentdojo/artefacts.toml` |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2 and §3 per pin. Excludes `.DS_Store` / `._*` (expect 0). 8 absent blobs per pin, none selected |
| L1-02 strict parse | yes | 223 / 1,518 / 1,518 |
| L1-03 encodings | yes | The em dash in `[KAVACH BLOCK — decided_by=…]` and the literal `<|tool_response>` token are content, not mojibake |
| L1-04 duplicates | yes | Within a pin (41 in nav), across pins (223, 147, and the 84 = 84 of §3), content groups, and cross-corpus via `l1_xdup.py` (expect 0: census `known_elsewhere` 0) |
| L1-05 arm coverage | yes | §3. Proposed stratum key `("model_dir", "suite", "attack_dir")`, with `model_dir` = the identity key. Not yet in `l1_families.STRATA` (the wave-7 recipe is pending) |
| L1-06 secrets / account paths | yes | Counts and pointers only. The runs were on Windows (PowerShell guide), so watch for `C:\Users\…` in error text |
| L1-07 timestamps | yes | `evaluation_timestamp` (v1.k14). The range and order are in H12 |
| L1-08 degenerate | yes | Slack degeneration (H7). 5 incomplete per branch. Zero-call Kavach arms (H6) |
| L2 import / validate / recompute / determinism | yes | Via the queue, `--cpu 2`. One scratch corpus with the three snapshots in order, so cross-snapshot collapse is exercised. A second import uses another `--jobs` |
| L2 A2 / A3, evidence classes | yes | Code identity `unpinned`, so D rules appear as `_unverified` twins. Denials are mapped by D-113 |
| L2 identity | yes | H10 and H11 |
| L2 SEM | yes | `agentdojo.suites@2`: banking, slack, workspace |
| L2 redaction | yes | Expect no account path in AER/SEM/PROV. The D-255 `pipeline_name` redaction is not triggered (`local`, `local-kavach`) |
| L2 withholding | inert | D-257: no table, MIT, include |
| L2 outcome sanity | yes (L1 population) | §4. 6 reference arms from the summaries; other strata get Wilson intervals only |
| Delta since E2 | no | Not in FA or E2 |

## 7. Hypotheses (falsifiable; thresholds fixed now)

| Id | Expectation | Falsified if | Class if falsified |
|---|---|---|---|
| H1 | L1 selects 223 / 1,518 / 1,518 logs with the §3 cell counts. Byte-distinct 223 / 1,477 / 1,518; union 2,625 | any count differs by ≥ 1 | mapping-defect or source drift |
| H2 | 0 strict-parse failures (no duplicate keys, NaN, BOM, invalid UTF-8 or truncation) | ≥ 1 | source-defect |
| H3 | 0 U+FFFD, 0 mojibake, 0 lone surrogates | ≥ 1 | source-defect, S3 |
| H4 | nav's 41 in-pin byte copies all pair `workspace_forced/logs/local` with `results_v2/logs/local`. rearch's 84 `not_forced` logs equal nav's 84 `results_v2/logs/local` exactly. **41 logs carry both the forced (nav) and the not_forced (rearch) label** | any other pairing, or the 41 overlap is absent | analysis-artefact if absent. If present: documentation-mismatch, S2 (condition label conflict); routed as an identity/condition note |
| H5 | All 45 denials per part are in `slack_gemma_dell/logs/local-kavach`. 40 are in pair logs and 5 in pre-pass logs (summary: 40 blocks). 0 in any workspace `local-kavach` log | the split differs, or ≥ 1 workspace denial | documentation-mismatch, S3 |
| H6 | Workspace `local-kavach` arms (1,148 per branch): the summaries record 0 screened calls. Report the share of logs with ≥ 1 executed tool call | that share is > 50% (calls ran unscreened, so "defence kavach" is nominal) | documentation-mismatch, S2 (disclose the arm as unscreened) |
| H7 | The last assistant message holds the literal `<|tool_response>` in 93 ± 2 of 105 slack `local` and 90 ± 2 of 105 `local-kavach` pair logs (INVALID_README). In the workspace gemma4:26b directories (committed after the 07-06 fix) it occurs in ≤ 2% | slack counts outside ± 2; workspace > 10% | slack: documentation-mismatch, S3. Workspace: source-defect, S2 (the HANDOFF's warning applies; disclose like slack) |
| H8 | The raw tallies equal the summaries exactly: slack local 5/105 utility, 0/105 security; forced local 27/560 and 0/560; not_forced2 local 11/560 and 10/560; every Kavach arm 0/560 (or 0/105) and 0 | any cell differs by > 1 log | documentation-mismatch, S2. > 15 pp: an S1 candidate (not expected at these rates) |
| H9 | The census outcome totals of §2 reproduce per part (T/F/absent) | any count off | analysis-artefact or source drift |
| H10 | Identity after the three-snapshot import: gemma4:26b 2,516, unresolved 109 (of which 43 are the `results_v2/logs/local` origins), defence kavach 1,258. `pipeline_name` values are `local` and `local-kavach` only | any count off | mapping-defect |
| H11 | The 84 `results_v2/logs/local` executions keep the nav origin (unresolved), with `n_origins` 2 for the 84 rearch copies. The identity of the collapsed execution comes from the first snapshot | identity taken from a later origin | mapping-defect, S2 |
| H12 | Every timestamp is in 2026-06-15..2026-07-21. No log is later than its introducing commit plus 5 h 30 m (IST; the Dell may log local time): slack ≤ 07-06T13:22Z, banking ≤ 07-15T13:57Z, dell/llama ≤ 07-16T12:38Z, forced/forced2 ≤ 07-16T13:01Z, not_forced* ≤ 07-16T15:34Z, logs ≤ 07-21T19:19Z. Monotone within a log | ≥ 1 outside | source-defect, S3 (time zone or clock) |
| H13 | 0 provider keys and 0 account paths (incl. `C:\Users\…`, `/home/…`) in the selected logs | any hit | security finding, reported at once |
| H14 | `incomplete` = 1 / 5 / 5, one per partial directory (banking, dell, forced_llama3.1, llama3.1, forced2). `error` is null in all. The banking user_task_0 log (the commit says it errored) is the incomplete one or has the error only in messages | otherwise | documentation-mismatch, S3 |
| H15 | The kavach_runner prompt digest `2e867516` is in all 220 / 1,474 / 1,515 runner logs, and `a021a92b` in the 3 banking logs, which alone record `benchmark_version` v1.2.2 | any other digest | mapping or profile defect, S3 |
| H16 | Slack pairs = 21 user tasks × injection tasks 1–5 = 105 (the draft paper says 20 × 5) | logs show 20 user tasks | if 21: documentation-mismatch (draft vs data), S3 |
| H17 | L2 (31 + 83 + 83 units): every stage ok, 0 failing checks, 0 degenerate, 0 `adapter_defect`. `recompute --dry-run` shows 0 differences. The second import is byte-identical. Mapped utility/security equal the raw values of the same labels in 100% of units | any failure | mapping-defect |
| H18 | Profile `[source].package` says "agentdojo per requirements.txt", but no requirements.txt at the pins names agentdojo (desk fact) | – (already observed) | documentation-mismatch in our profile, S3. Text fix routed to the family owner |
| H19 | The within-part content-repeat groups (57 / 590 / 561) mostly pair a `local` log with the `local-kavach` log of the same pair in the same directory (≥ 80%). In such pairs, utility and security agree in ≥ 99% | < 80%, or > 1% of identical-message pairs with different outcomes | < 80%: report only. Outcome disagreement: source-defect, S2 (bears on the 27/560 vs 0/560 contrast) |

Rule: no stratum or directory is excluded for zero attack successes or for the authors' invalid note. Every Kavach arm is expected at 0% ASR and most baselines near 0%.

## Fact-check (2026-10-15, desk only; no log read, nothing computed from log bytes)

Checked against the GitHub API at the three pins (recursive trees, commits, compare, contents), the arXiv, Zenodo, HF and Ollama metadata, and the upstream AgentDojo tracker:

- **Pins and trees.** All three pins are branch heads (9 branches). The trees are not truncated: 867 / 1,913 / 1,892 blobs. With the profile's three include globs they select 223 / 1,518 / 1,518 logs (1,047,737 / 7,090,910 / 7,237,494 B), 223 / 1,477 / 1,518 distinct blob ids, union 2,625 (223 in all, 147 branches only, 1,107 nav-only, 1,148 rearch-only). The six other branches select exactly `main`'s 223 (path, blob) pairs. Confirmed. The 8 absent blobs are a staging fact and cannot be checked from the API.
- **§3 cells.** Every directory × `attack_dir` count in §3 equals the tree listing. Also confirmed: slack has 21 user tasks × 5 injection tasks, workspace_forced 40 × 14, `results_v2/logs/local` UT {0,1,2,3,5} × 14, and dell and forced_llama3.1 UT 0 only. nav's 41 in-pin copies are exactly `workspace_forced/logs/local` ∩ `results_v2/logs/local`. rearch's `not_forced` blob set equals nav's `results_v2/logs/local`.
- **Commits.** The dates, authors and messages of 8b2498ad, 9e00ac41 (adds INVALID_README and the HANDOFF), de8e8c55, cff1fb54, 5f73faa7, 3ad86ecd and f2dd7efa match. 3ad86ecd has 1,193 added, 1,108 removed and 42 renamed files, including `workspace_forced/agentdojo_summary.json` → `workspace_not_forced/agentdojo_summary1.json`. Both branches are 4 ahead and 113 behind (merge base 189b8258). The branches' own merge base is 5f73faa7. Confirmed.
- **Reference outcomes (§4).** I reopened the four summaries at their pins. The numbers match: 0.0476 / 0.0 and Kavach 108 calls, 40 blocks, 68 allows; 0.0482 / 0.0; 0.0196 / 0.0179; the Kavach arms 0.0 / 0.0 with 0 calls; `run_fully_defended` false (workspace) and true (slack). The implied counts 5/105, 27/560, 11/560 and 10/560 are the only integers that round to these values. Note: the workspace summaries also hold `with_kavach.kavach.fully_defended: true`, which conflicts with the top-level false and 0 calls. H6 is unchanged.
- **Documents.** Confirmed: INVALID_README (93/105 and 90/105 `<|tool_response>`; the fix2 run not completed); the HANDOFF warning about other gemma4:26b suites already collected; the branch draft (slack "20 user tasks × 5", Kavach AgentDojo cells `[TBD]`); the main draft (629 gpt-4o `runs/` replay); README (branches archived, unmerged); REPRODUCIBILITY ("Gemma4 27B"); the run guide (bug #1, old results deleted); and runner defaults (gemma4:26b, v1.2, `agentdojo_dell`, `llm_name "local"`, `tool_delimiter="user"` on the branches). Ollama lists 26b, 26b-a4b and 31b but no 27b.
- **Harness.** No `requirements.txt`, `pyproject` or lock file at the pins names agentdojo (H18 confirmed). Upstream #150, #154, #202, #219 and #220 are all open. #154 is specifically about context-length errors scored as security True.
- **Licence.** The LICENSE (MIT, Kavach Team, PES University) is the same blob at all three pins, with no use clause. Confirmed. **Corrected:** the blob id is `01b2613e`, not `3cf00271` (research.json).
- **Paper and data record.** arXiv `ti:Kavach` returns no entries. Zenodo 19643499 is unrelated (other authors, CC-BY-NC-ND-4.0, one 4,042 B zip). The HF hits are unrelated. Confirmed.
- **Census and trial figures (§2, §3 totals).** These were re-read from `phase10j/census.json`, `census.md` §5 and `trials.md` §1, and they match. The derived totals add up: gemma4:26b 2,516, unresolved 109, kavach 1,258, and L2 31 / 83 / 83.
- **Corrected:** repository issues. There are 9 issues (3 open: #6–#8) and 2 open PRs (#127, #128), not "0 issues and 5 open PRs". None concerns these logs.
- **Unverifiable here:** the 8 absent blobs; quirk counts in §5 (they come from the profile and census, not re-derived); the Ollama digest of the July `gemma4:26b`.
