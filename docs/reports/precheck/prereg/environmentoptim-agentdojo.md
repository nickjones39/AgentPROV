# Pre-registration: `environmentoptim-agentdojo`

| | |
|---|---|
| Corpus | `environmentoptim-agentdojo` (family `agentdojo`, profile `environmentoptim-agentdojo` v1, dialect/mapper `agentdojo.tracelogger`, variant `v1.k14`, identity table `environmentoptim_run_dirs.toml` (1 row), semantics `agentdojo.suites@3`) |
| Parts | `head`: GitHub `omseeth/EnvironmentOptim` branch `main` @ `febf82d8d1d8344d6c19e9fd172b51e52d68416a` (2026-07-18T11:07:08Z; still branch HEAD on 2026-10-14). Mapped: 104 gpt-5.4 logs. The 6,016 local Qwen3.5 logs are `select.redaction_pending` (D-255, R-10j-1) and are counted at L1-01 only |
| Wave | 7. Full pre-check. Not examined in FA or E2, so there is no delta since E2 |
| Code commit | `065b0d36` or later on branch `precheck-corpora` (branch head at writing: `6b76c15e`) |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: the phase-10j census (`census.md` §6, §12, `census.json`), trial (`trials.md` §1, §3) and routing (R-10j-1, R-10j-2), the profile and identity table, the registry, `artefacts.toml`, DECISIONS (D-254, D-255, D-257), and desk research (`data/environmentoptim-agentdojo/research.json`). Per-suite counts come from the GitHub git-trees API listing of the pin (paths, blob ids, sizes only). Nothing was tallied from raw data. The account segment of the cluster path is never written (shown as `<account>`) |
| Method | [`../README.md`](../README.md) (with amendments 2 and 3) |

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Repository | [omseeth/EnvironmentOptim](https://github.com/omseeth/EnvironmentOptim). Not a GitHub fork object, but its history holds SaFo-Lab/AgentDyn's commits up to `bd3fc6bc` (2026-03-04). Own work runs 2026-03-20 to 2026-07-18. 456 commits, 1 branch, no tags/releases, 0 issues/PRs ever | GitHub API |
| Study | Master thesis "Optimizing Environments to Improve Agent Performance" (M. Seeth, LMU/TUM). **No public PDF, arXiv id or DOI** (checked 2026-10-14). The README and `optimization/analysis/report_results.log` are the only result statements | README at pin; [report_results.log](https://github.com/omseeth/EnvironmentOptim/blob/febf82d8d1d8344d6c19e9fd172b51e52d68416a/optimization/analysis/report_results.log) |
| Benchmarks | AgentDojo ([2406.13352](https://arxiv.org/abs/2406.13352)) banking/slack/travel/workspace; AgentDyn ([2602.03117](https://arxiv.org/abs/2602.03117), v1 2026-02-03, v2 02-06, v3 05-07 with a new title) dailylife/github/shopping | arXiv |
| Mapped part | `runs/gpt-5.4-2026-03-05/`: 104 logs added in **one commit** `7b684d0d` (2026-05-27T17:09:58Z) and unchanged since (path history has 1 commit). Same commit adds the 104-task Qwen `baseline_train` runs and `training_data_<suite>_gpt54.json` for the 4 AgentDojo suites (these were removed on 2026-05-28) | commits API |
| Role of the gpt-5.4 runs | **Train-split data-collection runs.** They cover exactly the 104 train tasks (= `qwen3_5-9B_baseline_train`) and none of the 53 test tasks. `collect_data.py` keeps their `utility == True` conversations as SFT data. No thesis result reads them (`report_results.sh`) | git tree; scripts at pin |
| Harness | AgentDyn's agentdojo fork vendored in `src/agentdojo`, pyproject `agentdojo 0.1.35`. Code = AgentDyn@`bd3fc6bc` + `bfdd3ec7` (2026-04-30, adds `GPT_5_4_2026_03_05`, provider openai). It differs from AgentDyn@`5353cf76` in 6 files, including `task_suite.py` and `scripts/benchmark.py`. `system_messages.yaml` is the same blob (`a01968f3`) at both. Profile: `code_identity = "unpinned"`, `verified_code = []` | git trees of both pins |
| Known harness bugs | AgentDyn [#8](https://github.com/SaFo-Lab/AgentDyn/issues/8) (open): github user_task_5, 7, 8 and 11 can never reach utility True. All 4 are in this train split. #2–#4 (temperature 0.0 ignored, OpenAI) was fixed before the fork. #6 (github injection false positive) concerns attacked runs only | AgentDyn issues |
| Data record | None (Zenodo 0, HF 0, Figshare 0). The git repository is the only release | research.json |
| Licence | MIT. LICENSE blob `006aed0b` is identical to AgentDojo's and AgentDyn's. The README puts the fork's code under the same licence. No data licence, no use clause | LICENSE at pin |

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Blobs at pin / TraceLogger logs | 93,042 / 90,480 (all byte-distinct; 1,722 absent blobs in the partial clone, none a log) | census §1, §6, `census.json` |
| Selected logs (units) = executions | **104** (1,195,917 bytes; 2,874–57,574 bytes each) | `tools/readme_corpora.toml` (104, trial import); trial §1; git tree |
| Per suite | banking 11, dailylife 13, github 13, shopping 13, slack 14, travel 13, workspace 27 | git tree (7b684d0d file list = pin tree) |
| Task ids | `user_task_0..N-1` per suite (N as above), all `none/none.json` | git tree |
| Not selected: `select.owned_elsewhere` | 84,360 = 36,679 `runs/dojo_*` (agentdojo-upstream) + 47,061 AgentDyn copies (incl. 4,258 DRIFT) + 620 `gpt-4o-mini-2024-07-18-drift` (agentdyn history, R-10j-2) | trial §1; census §6, §12 |
| Not selected: `select.redaction_pending` | 6,016 (5,910 `…_qwen3_5`, 53 `-2B`, 53 `-4B` pipeline_name shapes) | trial §1; routing R-10j-1 |
| Check of the sum | 104 + 84,360 + 6,016 = 90,480 | arithmetic |
| Non-log files under `runs/` in the include set | 0 (no blob directly under `runs/`; the gpt-5.4 dir holds only the 104 logs) | git tree |
| Trial | 104 ok, 0 failed checks, 428/428 files identical across `--jobs 4/2` | trials.md §1 |
| L2 sample | **35 units**: 7 strata (default key `_prefix|pipeline_dir|suite|attack_dir`, one dir, attack none) × k = 5; no reduction | README §4 + amendment 2 applied to the git-tree strata |

## 3. Expected arms (L1-05; L2 strata)

| Model | Defence | Attack | Suites | Cells | Paper number |
|---|---|---|---|---|---|
| gpt-5.4-2026-03-05 (OpenAI API, class I from the dir = logged `pipeline_name`) | none | none (benign) | 7 (4 AgentDojo + 3 AgentDyn), train split | 7 (11/13/13/13/14/13/27) | none |

- **Missing by design:** the 53 test-split tasks for gpt-5.4 (5/7/7/7/7/7/13), and every attacked or pre-pass cell. There are no repetitions.
- **Extra:** none.
- **Held (not this part):** about 140 Qwen3.5 arm directories (benign images by checkpoint and size, controls, soft image and language prompts by seed, tokens, position and RLVR rollout, text prompts, 2B/4B/9B baselines, 9B train baseline). They are counted at L1-01 only.
- No stratum is excluded for zero successes (user rule).

## 4. Expected outcome rates

**Metric mapping.** The thesis reports `utility` (a boolean in each log), micro- and macro-averaged per suite. Here `utility` maps to the AER judgement `utility` (origin `agentdojo.checker_outcome@1`). `security` in benign logs is the runner's constant True, so it maps under `agentdojo.benign_security_constant@1` and is not an observation.

| Arm | Expected | Basis | Use |
|---|---|---|---|
| gpt-5.4, all 104 | utility: **no published rate** | no thesis/README/AgentDyn table uses it | Wilson 95% only, per suite (n 11–27) and pooled |
| gpt-5.4, github user_task_5, 7, 8, 11 | utility False 4/4 | AgentDyn #8 (structural checker bug) | falsifiable (H9) |
| gpt-5.4, all 104 | security True 104/104 (constant) | profile `observed` origin_rule_applied 104 | falsifiable (H9) |
| Qwen3.5-9B baseline test split (held) | 41.5% (22/53): banking 4/5, dailylife 2/7, github 1/7, shopping 1/7, slack 3/7, travel 4/7, workspace 7/13 (k back-computed) | report_results.log "Results from baseline" | context for the post-R-10j-1 import only |

The README §4 gap rule cannot fire: there is no paper rate, and no stratum reaches n ≥ 20 in the sample (the population cells are 11–27). Outcomes are reported, never given a verdict.

## 5. Known quirks (expected-known)

| Id / source | Expected in the 104 | Reference |
|---|---|---|
| `agentdojo.benign_security_constant` | 104 files, origin rule applied 104 | profile `observed` |
| `agentdojo.args_mutated_in_place` | 104 files | profile |
| `agentdojo.placeholder_args_never_injection_evidence` | 584 present, 584 null | profile |
| `agentdojo.injection_task_as_user_task_prepass` | 0 | profile |
| `agentdojo.silent_rerun_last_pass_only` | 0 null-final logs | profile |
| `agentdojo.unexecuted_trailing_calls` | 0 calls / 0 logs | profile |
| `agentdojo.provider_call_id_anomalies` | 0 null, 0 repeated, 0 duplicate | profile |
| `agentdojo.package_version_not_code_identity` | 0 without `agentdojo_package_version` (0.1.35) | profile; D-24 |
| System prompt | all 104 `21a1c00d…` (543 chars, AgentDyn default + auto-complete line) | profile `system_prompt_variants` |
| `agentdojo.art.naive_timestamp` | applies by analogy (naive `evaluation_timestamp`) | `artefacts.toml` (scope omits this source) |
| `artefacts.toml` | **No entry scopes `environmentoptim-agentdojo`.** Generic entries apply by analogy only: benign_security_constant, naive_timestamp, incomplete_run, package_version_unknown | `artefacts.toml` |
| Decisions | D-254 (identity; checkpoints are payload conditions), D-255 (redaction pending), D-257 (no `[withhold]`; EnvironmentOptim's only key-header match was a DRIFT log, now AgentDyn's), D-24 (unverified twins) | DECISIONS |
| Secrets (census) | 0 new-log matches outside the 620 DRIFT logs, so 0 expected in the 104 | census §6, §8 |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2. Report selected 104 and not-selected by code, with the profile's reason |
| L1-02 strict parse | yes | 104 logs (census parse ok over all 90,512 JSON) |
| L1-03 encodings | yes | Non-ASCII benchmark text is legitimate. Count escape residues and controls |
| L1-04 duplicates | yes | Within part (expect 0); cross-corpus with `l1_xdup.py` (census novelty: all 104 new; AgentDyn has no gpt-5.4 dir) |
| L1-05 arm coverage | yes | §3, 7 cells, plus task-id coverage per suite |
| L1-06 secrets / account paths | yes | Counts and pointers only. Include `_ceph_ssd_students_` as an account-path pattern |
| L1-07 timestamps | partly | Presence, parse, naive zone, range. Within-unit monotonicity n/a (one timestamp per log) |
| L1-08 degenerate | yes | Expect 0 of each class |
| L1-09 metadata in include | yes | Expect 0 |
| L2 import / validate / recompute / determinism | yes | 35 units; queue, `--cpu 2`, two `--jobs` values |
| L2 A2 / A3 classes | yes | Expect the trial's register only (104 ok, no "with issues") |
| L2 evidence classes | yes | D rules via `_unverified` twins only (`verified_code = []`) |
| L2 degenerate / adapter_defect | yes | Expect 0 |
| L2 identity | yes | Model `gpt-5.4-2026-03-05`, defence `none` (class I, table row); suites resolve to benchmark agentdojo vs agentdyn per the profile map |
| L2 redaction | yes | Trivial here: no account path is expected in the raw 104 |
| L2 withholding | conditional | No `[withhold]` (D-257). Applies only if L1-06 hits |
| L2 outcome sanity | Wilson only | No paper rate; structural H9 only |
| Delta since E2 | no | Not in FA/E2 |

## 7. Hypotheses (falsifiable; thresholds fixed now)

| Id | Expectation | Falsified if | Class if falsified |
|---|---|---|---|
| H1 | L1 selects exactly 104 logs with the per-suite counts and task ids of §2; not selected 84,360 owned_elsewhere + 6,016 redaction_pending; 90,480 logs, 93,042 blobs | any count off by ≥ 1 | mapping-defect (profile) or source-defect |
| H2 | 0 strict-parse defects in the 104 | any | source-defect |
| H3 | 0 C0/C1 controls (outside `\t\n\r`), bidi, tag, lone-surrogate or U+FFFD characters in the 104 | any hit | source-defect, S3 |
| H4 | 0 byte-identical and 0 identical-fingerprint pairs within the 104; 0 cross-corpus repeats | any | documentation-mismatch, S2 |
| H5 | Every log has `pipeline_name` = `gpt-5.4-2026-03-05`, `attack_type` null, `injection_task_id` null, and `suite_name`/`user_task_id` equal to the path (0 `path_disagrees`, 0 `pipeline_name_mismatch`) | any | source-defect, S3 |
| H6 | 0 secret-like strings; 0 account paths (`/Users/`, `/home/`, `C:\Users\`, `_ceph_ssd_students_`) in the 104 | any hit | security finding: report to the orchestrator at once |
| H7 | `evaluation_timestamp` present and parseable in 104, naive, all within 2026-04-29T16:00 .. 2026-05-28T07:10 (the enum commit 2026-04-30T06:01Z and the adding commit 2026-05-27T17:10Z, ±14 h for the unknown zone) | any outside, absent or zoned | source-defect, S3 (*fact-check note:* a value before the lower bound alone is an observation, not a defect, because the runs may have used the enum before it was committed) |
| H8 | 0 empty, 0 zero-message, 0 incomplete, 0 null-final, 0 error-only logs; `error` null in 104 | any | source-defect, S3 |
| H9 | `security` True in 104/104; `utility` False in github user_task_5, 7, 8, 11 (4/4) | security False in any log; utility True in any of the 4 | mapping-defect (security) or documentation-mismatch (harness differs from AgentDyn #8), S2 |
| H10 | Profile `observed` counts reproduce exactly (§5: 104, 104, 584/584, 0, 0, 0, 0) and one system-prompt digest (`21a1c00d…`) in 104 | any differs | mapping-defect (profile), S3 |
| H11 | One `benchmark_version` value in 104 (expected `v1.2.2`); `agentdojo_package_version` 0.1.35 in 104; 0 extra top-level keys | > 1 value, or another value | documentation-mismatch, S3 |
| H12 | L2 on 35 units: every stage ok; 0 failing checks; 0 adapter_defect; `recompute --dry-run` 0 differences; second import byte-identical; identity resolved 35/35 | any failure | mapping-defect |
| H13 | (exploratory) utility per suite and pooled with Wilson 95% intervals; no threshold (no paper rate) | none | none |

## 8. Discrepancy leads carried to the dossier

1. **Role of the mapped part.** The profile and identity table call the gpt-5.4 runs "benign utility reference runs". They are train-split data-collection (teacher) runs that only `collect_data.py` reads, and no thesis number uses them. Proposed route (text only, via the orchestrator to the agentdojo family owner): reword the `basis` text in the identity-table row and the profile header.
2. **No published rate** for the only mapped arm. The comparison of record is therefore descriptive. The thesis has no public text to check the held arms against beyond `report_results.log`.
3. **Harness identity.** The code is AgentDyn@`bd3fc6bc` + `bfdd3ec7`, not AgentDyn@`5353cf76`. The prompt source the profile cites is unaffected (same blob). The scoring code differs. Record the fork point in the dossier; `code_identity = "unpinned"` stands.
4. **Structural zero.** The github tasks 5/7/8/11 (AgentDyn #8) are a harness defect inside this split (H9). The dossier should disclose them as such, never as a model property.
5. **Held part (for the post-redaction import).** `bd21722b` (2026-07-17) removed 18 train-split logs (15 workspace `user_task_22..26` + 3 slack `user_task_13`; *corrected in the fact-check*) from test directories of `text_prompt` one day before the pin. Arm counts there are post-correction.
6. **Our documentation (security-relevant).** Three tracked files carry the unmasked account segment that D-255/R-10j-1 mask: `docs/reports/phase10d/deferred.md`, `docs/reports/systematic-search/data/S1-code/S1-dependents.jsonl` and `S1-records.jsonl`. The value is public upstream in directory names. The pre-check rule still routes it to the orchestrator now. The value is not repeated here.
7. **Title drift.** The README cites AgentDyn's v1/v2 title; v3 renamed the paper. This is documentation only.

## Fact-check (adversarial pass, 2026-10-15)

Re-checked against the GitHub API (repo, branches, commits, git trees, issues), the files at the pin (README, LICENSE,
`report_results.log`, `report_results.sh`, `collect_data.py`), arXiv and the Zenodo/HF/Figshare APIs. Our own reports
used: census §1, §6, §12 and `census.json`, trials §1, routing R-10j-1, the profile, the identity table, the registry,
the agentdojo `artefacts.toml`. No raw corpus data was read.

| Claim | Verdict |
|---|---|
| Pin `febf82d8` = `main` HEAD, 2026-07-18T11:07:08Z, README-only; 456 commits; 0 tags, releases, issues/PRs; MIT; not a fork | confirmed |
| `runs/gpt-5.4-2026-03-05`: 104 blobs (not truncated), 1,195,917 bytes, 2,874–57,574; per suite 11/13/13/13/14/13/27; ids `user_task_0..N-1`; all `none/none.json`; path history only `7b684d0d` | confirmed |
| Same 104 task ids as `qwen3_5-9B_baseline_train`; 53 disjoint ids in `qwen3_5-9B_baseline` (5/7/7/7/7/7/13) | confirmed (tree listing, counts only) |
| `7b684d0d` adds 104 gpt-5.4 + 104 Qwen logs + 4 `training_data_*_gpt54.json`; `bc51205c` (2026-05-28) removes the 4 files | confirmed |
| `bd21722b` removes 18 train-split logs from `text_prompt` | **corrected**: 15 workspace (`user_task_22..26`) + 3 slack (`user_task_13`), not 18 workspace |
| Harness = AgentDyn@`bd3fc6bc` + `bfdd3ec7`; only `src/` commit after the fork; 6 files differ from AgentDyn@`5353cf76`; `system_messages.yaml` `a01968f3` at both; camel/progent/drift absent | confirmed (161/161 blobs equal to `bd3fc6bc` except `models.py`) |
| AgentDyn #8: open, github tasks 5/7/8/11 never utility True, 749/749 and 740/740 traces; PR #9 open | confirmed. #8 was tested at `5353cf7`; the files it blames are the same blobs at this pin |
| #2–#4 temperature fix before the fork; #6 attacked-only, fix not vendored | confirmed |
| `report_results.sh` never reads the gpt-5.4 tree; `collect_data.py` keeps `utility == True` | confirmed |
| Baseline 41.5% (22/53), per-suite rates, MACRO 41.6%; infix 200 tokens 62/51/38, best 69.8%, 50.3±10.0%, LOO 67.9% | confirmed (k recomputes to 22) |
| No published gpt-5.4 rate (no thesis PDF, arXiv or Crossref record) | confirmed as far as searchable; thesis may exist offline (unverifiable) |
| AgentDyn arXiv v1 02-03, v2 02-06 (old title, the README's), v3 05-07 (new title, 26 pages, 17 tables) | confirmed |
| LICENSE blob `006aed0b` = AgentDojo's and AgentDyn's; README puts fork code under MIT; no data licence | confirmed. OpenAI output terms stay unassessed |
| Counts 84,360 = 36,679 + 47,061 + 620; 104 + 84,360 + 6,016 = 90,480; 93,042 blobs; 1,722 absent; 5,910/53/53 | confirmed (census, trials, routing) |
| ts_month 2026-05 2,496 + 2026-06 3,624 = 6,120 | confirmed in `census.json` (all logs: these two months sum to the new-log count) |
| No `artefacts.toml` entry scopes this source; system prompt `21a1c00d…`, 543 chars | confirmed (`census.json` key `system_prompt_sha256_len`, value 21a1c00db164 with length 543) |
| Three tracked docs carry the unmasked account segment | confirmed (1 line each; value not repeated) |
| `gpt-5.4-2026-03-05` is an OpenAI snapshot | unverifiable here (no OpenAI primary page checked); the vendored `models.py` maps it to provider `openai` |

Changes made: the `bd21722b` composition in §8 and `research.json`, and a note on the H7 lower bound. No expectation was
added or changed from data.
