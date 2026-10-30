# Pre-registration: `redcode-exec-openhands`

| | |
|---|---|
| Corpus | `redcode-exec-openhands` (family `openhands`, dialect/mapper `openhands.events` variant `oh-1.5`, profile `redcode-exec-openhands@1`, catalogue `openhands` v1, SEM `openhands.tools@1`) |
| Parts | `redcode-exec-openhands` · `head`: 5,460 OpenHands 1.5.0 trajectories, members of six Zenodo 23168099 zips, plus the context zip `agent-execution-decisions-supp.zip` (scores, prompts, dataset) |
| Code commit | `065b0d36` (branch `precheck-corpora`) or later |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Wave 5. Not a delta corpus: registry status `planned`, never imported, absent from FA and E2 |
| Desk research | `../data/redcode-exec-openhands/research.json` (all URLs there) |

Sources: **P** = `src/agentprov/adapters/openhands/profiles/redcode-exec-openhands.profile.toml`; **A** =
`src/agentprov/adapters/openhands/artefacts.toml`; **C** = `docs/reports/phase10g/redcode-openhands.census.json`; **CD** =
`redcode-openhands.detail.json`; **R10g** = `docs/reports/phase10g/README.md`; **Z** = Zenodo API/record 23168099 and its file
previews (2026-10-14); **RC** = AI-secure/RedCode on GitHub; **L** = `tools/readme_corpora.toml`; **D** = DECISIONS.

## 1. Desk research summary

- **No paper is public.** "Which Orders Count?" exists only as the anonymous replication package (Z). arXiv title search: 0
  hits. Web and GitHub search found no preprint and no repository. The only author-reported numbers are the deposit's own
  aggregates: `<S>_<lang>_per_scenario.csv`, `summary/<S>_summary.json`, `scenario_<n>_summary.json` and
  `results_summary.xlsx` (outcome and flip metrics, RQ1-RQ4). They are listed in the supp-zip preview and **were not read**
  here. The L1 examiner reads them as the reference (H-05).
- **Data record:** concept 23107343 has 2 versions. 23107344 (2026-10-02) is a 7-byte README placeholder. 23168099
  (2026-10-05, latest, CC-BY-4.0, 8 files) is the only one with data. The size and md5 of all 7 pinned files equal P. Zenodo
  publishes no sha256, so P's sha256 values come from our own download.
- **Record description vs record:** the description says the trajectories ship as one `trajectories.zip`. The record holds
  seven trajectory zips (H-19). It also calls the Bash runs "preliminary" (threats to validity).
- **Harness:** OpenHands 1.5.0 (`a77b0550`, tag 2026-03-10), CodeActAgent, driven by the deposit's `OH_evaluation/OH.py`.
  Relevant OpenHands issues: #12228 (security_risk with small models) was closed before 1.5.0. No issue was found on event
  filtering or naive timestamps.
- **Benchmark:** RedCode-Exec (arXiv:2411.07781, v1 only). Upstream has 27 python and 20 bash dataset files. The deposit
  has 24 python (no scenario 12, 26 or 27) and 19 bash scenarios.
- **Licence:** data CC-BY-4.0. Vendored OpenHands MIT **[corrected in fact-check: MIT except `enterprise/`, which is PolyForm Free Trial 1.0.0 at tag 1.5.0; whether the deposit's `environment/` copy includes `enterprise/` was not checked]**. The RedCode dataset is CC BY 4.0 (`dataset/LICENSE` added
  2026-08-19) and the RedCode code MIT. This resolves P's `unassessed` RedCode item. No use clause.
- **Models:** `claude-sonnet-4-6` (Anthropic-style usage fields, so probably the Anthropic API through LiteLLM) and
  `qwen3-coder-30b-a3b-instruct` (provider not recorded). Run timestamps are 2026-09-21 to 2026-10-04 (naive).

## 2. Expected counts

| Quantity | Expected | Source |
|---|---:|---|
| Pinned files (size = Z = P; sha256 = P) | 6 trajectory zips + 1 supp zip; bytes 10,207,154 / 10,756,810 / 10,825,922 / 17,624,490 / 17,966,428 / 10,043,836 / 10,130,955 | P; Z |
| Trajectory members selected (`results/OH/*/S*/*/trajectory/*.json`) | **5,460** | L (basis census); C `/totals/files/n`; P |
| per zip: sonnet S1 / S2 / S3; qwen S1 / S2 / S3 | 720 / 720 / 720; 1,290 (py 720 + sh 570) / 1,290 (py 720 + sh 570) / 720 | P notes; C `by_group`; Z previews (four complete listings of 720; qwen S1/S2 previews truncated at 999) |
| Units / executions | 5,460 `agent_execution` (one per member) | L; R10g §8.3 |
| Uncompressed trajectory bytes | 459,370,670 (min 52,075, median 82,508, max 352,373) | C `numbers.bytes` |
| Events | 67,312 (min 5, median 12, max 16 per run) | C `numbers.events` |
| Score records (`conversation_log/index<sc>.json`) | 5,460 entries in 182 files (6 × 24 + 2 × 19); 1 per trajectory; 0 orphans either way | C `score_*`, `traj_with_score` |
| Prompt records (`prompt_generator/output`) | 2,010 (python S2 720, python S3 720, bash S2 570), all `quality_passed` | C |
| Dataset files (`dataset/RedCode-Exec`) | 43 (py 24, bash 19) | C `supp_members`; Z preview |
| Request join | 5,460 verify: S1 contained 1,956 + 54 after rewrite; S2 exact 1,956 + 54; S3 exact 1,404 + 36; 144 after the declared `/sys/kernel` rewrite (18 per arm) | CD `task_join`; A `join_after_rewrite` |
| Whole-population mapping (R10g §8.3, phase-10g code) | 5,460 mapped, 0 crash, 0 degenerate; messages O 46,508; model calls O 18,041 + I 4,421; tool executions D 14,165; task-prompt fixtures D 5,460; outcome 3,803 true / 1,520 false; `non_informative` 137 | R10g §8.3 |

## 3. Expected arms (L1-05)

Facets: model × request type (target `S1`/`S2`/`S3` = C1 direct / C2 justified / C3 pressured, deposit README per R10g
§3.5) × language. No defence facet: `defense_id` is `unk`.

| Model | S1 python | S1 bash | S2 python | S2 bash | S3 python | S3 bash |
|---|---:|---:|---:|---:|---:|---:|
| claude-sonnet-4-6 | 720 | **missing** | 720 | **missing** | 720 | **missing** |
| qwen3-coder-30b-a3b | 720 | 570 | 720 | 570 | 720 | **missing** |

- 8 of 12 cells are present. The 4 missing cells are consistent with the bash runs being "preliminary" (Z). There are no
  extra cells.
- Each python cell is 24 scenarios (1-25 without 12) × 30 payloads. Each bash cell is 19 scenarios (1-9, 13-16, 18, 20-23,
  25) × 30. Expected: 0 missing and 0 duplicate (scenario, payload) cells.
- Member-name grammar: S1 `oh_<sc>_<payload>_(py|sh)_S1-<hash>.json`; S2/S3 `oh_<sc>_<payload>_S<n>-<hash>.json` with no
  language tag (C `name_ltag`; Z). The language comes from the directory. The target in the name equals the directory in
  5,460 of 5,460 (C `name_target_agrees`).
- The case hash is a case key, not a run id: 2,160 hash values occur twice (sonnet and qwen, same target and python case).
  The 1,140 bash hashes are unique.

## 4. Expected outcome rates

**Mapping.** Each run has one `score` judgement (`by: benchmark`, actor `redcode_scorer`, origin `checker`), joined by key
(D, 5,460 of 5,460). In SEM, 3 maps to `executed` (`attack_succeeded` true), 0 to `refused` (false), and 1 to
`failed_or_harness_default` (`openhands.non_informative`; A `score_one_ambiguous`; D-177). The deposit's metric is the
share of each code per arm (Execution/Refusal/Failure).

**No author numbers are available for this step.** The figures below are census counts from the per-record scores (C
`score_values_joined`). They are what the deposit's summaries should equal (H-05) and the reference for any outcome check.

| Arm (model / C / lang) | n | score 3 (execution %) | score 0 (refusal %) | score 1 (%) |
|---|---:|---:|---:|---:|
| sonnet / C1 / py | 720 | 537 (74.58) | 181 (25.14) | 2 (0.28) |
| sonnet / C2 / py | 720 | 395 (54.86) | 322 (44.72) | 3 (0.42) |
| sonnet / C3 / py | 720 | 369 (51.25) | 338 (46.94) | 13 (1.81) |
| qwen / C1 / py | 720 | 521 (72.36) | 192 (26.67) | 7 (0.97) |
| qwen / C1 / sh | 570 | 381 (66.84) | 133 (23.33) | 56 (9.82) |
| qwen / C2 / py | 720 | 588 (81.67) | 123 (17.08) | 9 (1.25) |
| qwen / C2 / sh | 570 | 468 (82.11) | 65 (11.40) | 37 (6.49) |
| qwen / C3 / py | 720 | 544 (75.56) | 166 (23.06) | 10 (1.39) |
| **Total** | 5,460 | 3,803 | 1,520 | 137 |

L2 sampling is blocked (§7). Outcome sanity is therefore a whole-population recount at L1 against this table and the
deposit's summaries, with tolerance 0. A mapped-annotation recount (map-census substitute) must give 3,803 / 1,520 / 137.

## 5. Known quirks (already declared)

| Id | Expected | Where |
|---|---|---|
| `openhands.filtered_events` / `openhands.art.filtered_events` | id gaps in 5,460 of 5,460 files, 18,519 missing ids | P quirk; A; R10g §3.7 |
| `openhands.harness_error` / `openhands.art.harness_error` | 3 uncaused error observations | P; A |
| `openhands.join_after_rewrite` / `openhands.art.join_after_rewrite` | 144 runs (scenarios 1, 4, 7, 13) | P; A; D-178 |
| `openhands.score_one` / `openhands.art.score_one_ambiguous` | 137 runs | P; A; D-177 |
| Fixed harness reply | 4,421 later user messages, 1 distinct sha256 = P `fixed_replies` | P; CD |
| Not-executed notices | 0 (none occurs) | P; R10g |
| `finish` control call | 3,876 runs with `finish`; 1,584 without (last event: run obs 1,300, think obs 127, pending recall 102, task_tracking obs 42, error obs 13) | C `has_finish`, `last_event` |
| Text replies without a response id | 4,421 agent `message` actions; `llm_metrics.token_usages` empty in all 22,462 | C; R10g §3.4 |
| `last_response_full` not in the log | 1,387 runs | R10g §3.8 |
| Run-observation metadata | `extras.metadata {exit_code, hostname, pid, prefix, py_interpreter_path, suffix, username, working_dir}` on 8,960 events | C `run_meta_keys` |
| Scenario-summary key-set variants | 115 / 46 / 21 (three shapes) | C `summary_stats` |
| Lone-surrogate post-pass | not run by this mapper (D-378); census: 0 lone surrogates | AGENTS.md; R10g §3.1 |
| Archive inputs | D-200 landed (download-pin archives). The supp-zip auxiliaries are still unreachable by the runner (`tools/precheck/l2_import.py` BLOCKED) | D-156, D-200; l2_import |

## 6. Expected movement since E2

Not applicable: this corpus was never imported, so there is no E2 or FA baseline. The only earlier whole-population
evidence is the phase-10g map census (R10g §8.3, at the phase-10g code). Re-running it at `065b0d36` should give the same
counts (H-16). AER/PROV digests may differ because of core version bumps since then (D-31 rules headers and later regen
items). That is expected and is not a finding.

## 7. Check map

| Check | Applies | How / note |
|---|---|---|
| L1-01 counts | yes | §2: 5,460 members (720/720/720/1,290/1,290/720); supp-zip context selected by P `auxiliary`; other supp members `not_selected` (environment/ 2,626, Qwen_evaluation, OH_evaluation code) |
| L1-02 strict parse | yes | expect 0 failures of every class (census: 5,460 parse, top level list, no duplicate keys, non-finite numbers or lone surrogates); score/prompt/dataset JSON too |
| L1-03 encodings/escaping | yes | expect 0 bidi, tag or zero-width characters and 0 U+2028/2029/0085. Literal `\n` and `\uXXXX` residues are expected inside RedCode code payloads (descriptive only). Longest string 30,047 chars |
| L1-04 duplicates | yes (within part) | 0 byte-identical members; case-hash sharing as §3; trajectory-fingerprint duplicates expected rare (H-15); no cross-corpus overlap expected (part C Qwen Code is not registered) |
| L1-05 arm coverage | yes | §3 grid; 4 missing cells; complete scenario × payload grids |
| L1-06 secrets/paths | yes | census: 0 secret-like strings. Account-like fields: `extras.metadata.username/hostname/py_interpreter_path/working_dir` and recall `working_dir`/`repo_directory`; counts and pointers only (H-10) |
| L1-07 timestamps | yes | 67,312 values, one form `YYYY-MM-DDTHH:MM:SS.ffffff`, naive; first 2026-09-21T10:11:30.593950, last 2026-10-04T18:27:24.480387; monotone in 5,460 files; run span max 5,825.6 s |
| L1-08 degenerate | yes | 0 empty or tiny files (min 52,075 B); min 5 events; 1,102 runs with 0 agent text messages (not degenerate); 13 runs ending in an error observation; 1,584 without `finish` |
| L2 selection/import | **blocked** | `l2_import.py` BLOCKED: the supp-zip auxiliaries (scores, prompts, dataset) are unreachable by `auxiliary_for`, so every unit would lack its score. Proposed substitute (needs the orchestrator's OK): `tools/openhands/map_census.py redcode` over all 5,460 members at `065b0d36` (map, seal, annotate, derive and tier-4 validate in memory) |
| L2 validate / recompute / determinism / verify chain | substitute only | map census gives tier-4 validation and a digest comparison across worker counts (8 vs 3: identical at phase 10g). `recompute --dry-run` and `verify --level chain` need a corpus: not applicable until the runner path exists |
| L2 A2/A3 classes, evidence classes | via substitute | expect 0 crash/degenerate/`adapter_defect`; no dangling `cause`; executions D (verified 1.5.0), text-reply model calls I; no I statements in core |
| L2 identity | via substitute | models from `model_response.model` (2 ids), harness version 1.5.0 from the log; 0 unresolved |
| L2 redaction | yes (reduced) | no redact table; expect 0 host account paths in AER/SEM/PROV |
| L2 withholding | **no** | no `[withhold]` table and 0 secret-like strings |
| L2 outcome sanity | yes (whole population, L1) | §4 table, tolerance 0 |

## 8. Hypotheses (falsifiable)

| Id | Expectation | Falsified if |
|---|---|---|
| H-01 | The 7 staged files equal P's size, md5 and sha256 and Z's size and md5 | any difference |
| H-02 | 5,460 members with per-zip counts as §2; per-arm grids complete (python 24 × 30, bash 19 × 30) | any count ≠ (tolerance 0) or any missing or duplicate (scenario, payload) |
| H-03 | Name grammar: S1 has `_py`/`_sh`, S2/S3 none. The precheck L1 hook (`l1_families.py` `_RC`) needs the language tag, so if unfixed it flags the 3,450 S2/S3 members `layout_mismatch` | L1 reports `layout_mismatch` on any S1 member (a real finding); S2/S3 flags are an analysis artefact to fix before reporting |
| H-04 | Score join 5,460 / 5,460, one entry per key; per-arm counts exactly as §4 | any difference |
| H-05 | The deposit's own aggregates (`*_per_scenario.csv`, `<S>_summary.json`, scenario summaries, `results_summary.xlsx` outcome counts) equal the per-record counts of §4 per arm and scenario | any difference (`documentation-mismatch`; S1 if it moves an arm's execution rate by > 1 pp) |
| H-06 | Score 1: 137 runs, 93 in the two bash arms; ambiguity (Failure vs harness default) cannot be resolved from the logs | a score-1 run with a recorded cause in the score file |
| H-07 | Served model ids: `claude-sonnet-4-6` only in sonnet dirs (11,789 entries), `qwen3-coder-30b-a3b-instruct` only in qwen dirs (20,417); no other id | any other id or a directory disagreement |
| H-08 | `openhands_version` 1.5.0 and `CodeActAgent` in 5,460; tool set fixed (5 tools) | any other value |
| H-09 | Timestamps as §7 L1-07 (naive, range, monotone, 0 decreases) | any unparseable, zoned, out-of-range or decreasing value |
| H-10 | 0 secret-like strings. `username`/`hostname`/paths in run metadata are container-internal: 0 host account paths (`/Users/<name>`, `/home/<name>` other than a sandbox user) | any host account name or path (S2; redaction needed) |
| H-11 | Ids: first 0, strictly increasing, gaps in 5,460 files, 18,519 missing ids; `cause` 19,625 resolved and earlier; 3 uncaused errors | any difference |
| H-12 | Run ends: `finish` 3,876; others as §5; max 16 events | different counts, or > 16 events in any run |
| H-13 | 4,421 later user messages, 1 distinct sha256 = P `fixed_replies[0]` | ≠ 1 distinct or a different digest |
| H-14 | Request join: 5,460 verify; 144 after the declared rewrite (54 / 54 / 36) | any unjoined run or a different split |
| H-15 | 0 byte-identical members; 2,160 case hashes each shared by exactly one sonnet and one qwen run; trajectory-fingerprint duplicates < 1 % (55 files) | byte duplicates > 0, a hash shared otherwise, or ≥ 55 fingerprint duplicates |
| H-16 | Map census at `065b0d36` reproduces R10g §8.3 counts: 5,460 mapped, 0 crash, 0 degenerate; issues 5,460 / 144 / 3; records and annotations as §2 | any count differs (mapping-defect unless a documented version change explains it) |
| H-17 | A's `expected` counts for this source (5,460 / 3 / 137 / 144) are confirmed | any differs |
| H-18 | The scenario-summary key-set variants (115 / 46 / 21) align with scenario groups rather than being random, which suggests partial reruns or re-summaries | variants spread with no group structure (then not a lead) |
| H-19 | Z's description (one `trajectories.zip`) disagrees with the record (7 zips) | n/a (desk-confirmed; S3 documentation-mismatch to record) |

Never exclude data because an arm has no or few executions or refusals (user rule). The missing bash cells are a design
property of the deposit, not a defect.

## 9. Fact-check (adversarial, 2026-10-14)

Re-opened every source cited above; nothing was computed from raw data.

| Claim | Verdict | Evidence |
|---|---|---|
| Zenodo 23168099: latest, created 2026-10-05, CC-BY-4.0, anonymous creators, revision 4, concept 23107343 | confirmed | https://zenodo.org/api/records/23168099 |
| Concept has 2 versions; 23107344 (2026-10-02) holds only a 7-byte README.md | confirmed | https://zenodo.org/api/records/23168099/versions?allversions=true |
| Sizes and md5 of the 7 pinned files (and the 8th, part C) | confirmed; equal P's `size`/`md5` for all 7 | Zenodo API `files`; P lines 37-117 |
| Description says one `trajectories.zip`; record has 7 trajectory zips (H-19) | confirmed | Zenodo API description and file list |
| Bash runs called "preliminary"; 720 samples / 24 scenarios; C1/C2/C3 | confirmed | Zenodo description |
| Previews: sonnet S1/S2/S3 and qwen S3 list 720 trajectory members; qwen S1 preview truncated (999 names); supp preview 43 dataset files | confirmed | https://zenodo.org/records/23168099/preview/<file> |
| No paper: arXiv title search 0 hits | confirmed (arXiv API totalResults 0); web/GitHub search not repeated | https://export.arxiv.org/api/query?search_query=ti:%22Which%20Orders%20Count%22 |
| RedCode arXiv:2411.07781 v1 only, 2024-11-12, NeurIPS 2024 D&B | confirmed | https://export.arxiv.org/api/query?id_list=2411.07781 |
| RedCode issue #2: score 3 = successful attack | confirmed; upstream `evaluation.py` also sets 1 as a fallback ("No score added"), so score 1 is ambiguous upstream too | https://github.com/AI-secure/RedCode/issues/2 ; evaluation/RedCode_Exec/evaluation.py at c84b6db88fd8 |
| RedCode head c84b6db88fd8 (2026-08-19); `dataset/LICENSE` CC BY 4.0 added in cdc3a1e94b64; code MIT; 5 issues all closed | confirmed | GitHub API (commits, contents, license, issues) |
| Upstream has 27 python and 20 bash dataset files; deposit lacks scenario 12 (both) and python 26/27 | confirmed (upstream bash: 1-9, 12-16, 18, 20-23, 25) | GitHub tree c84b6db88fd8 |
| OpenHands tag 1.5.0 = a77b05509ec010d44d1e274b0f8daace0f89ea8f, 2026-03-10; = P `verified_code` | confirmed | GitHub API ref/tags/1.5.0; P line 148 |
| Vendored OpenHands licence MIT | **corrected**: MIT except `enterprise/` (PolyForm Free Trial 1.0.0) at 1.5.0 | https://github.com/OpenHands/OpenHands/blob/1.5.0/LICENSE |
| OpenHands issues #12228 (closed 2025-12-31) and #14807 (closed 2026-06-15) | confirmed | GitHub API |
| §4 outcome table (all 24 counts, percentages, totals 3,803 / 1,520 / 137; 93 score-1 in bash) | confirmed against C `score_values_joined` and R10g §3.8; arithmetic re-done | census JSON; R10g lines 174-177 |
| §2 counts (5,460; bytes 459,370,670; events 67,312, 5/12/16; 182 score files; 2,010 prompts; 43 dataset files; 3,450 S2/S3 without tag; 1,584 without finish) | confirmed against C and L | census JSON; `tools/readme_corpora.toml` |
| §2 map-census line (46,508; 18,041 + 4,421; 14,165; 3,803 / 1,520; 137) | confirmed | R10g §8.3 |
| H-03 `_RC` needs `_(py|sh)`; non-match flags `layout_mismatch` | confirmed | `tools/precheck/l1_families.py` line 534 ff. |
| L2 BLOCKED for this part | confirmed | `tools/precheck/l2_import.py` `BLOCKED` |
| A `expected` 137 and 144 | confirmed (status `unverified`) | A |
| OH.py `_remap_sys_kernel_paths`, `_score_case` default 1 | unverifiable here (rests on R10g §3.4/§3.8 reading of the deposit code; not re-read) | R10g |
| Claude model served via Anthropic API through LiteLLM; qwen provider | unverifiable (inference only, labelled "probably") | census usage keys |

Corrections applied: the OpenHands licence line (§1). No expectation was added or changed.
