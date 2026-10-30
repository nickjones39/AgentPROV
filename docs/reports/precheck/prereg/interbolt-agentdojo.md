# Pre-registration: `interbolt-agentdojo`

| Field | Value |
|---|---|
| Corpus | `interbolt-agentdojo` (family `agentdojo`, profile `interbolt-agentdojo` v1, dialect/mapper `agentdojo.tracelogger`, variant `v1.k14`) |
| Parts | `head` (only part) |
| Pin | GitHub `deconvolute-labs/interbolt-agentdojo` @ `43e2b5fa3e7b41b7e26f7c04cc8f371ab98aa875` (2026-08-19), still repo head on 2026-10-14 |
| Code commit | `065b0d36` (or later on `precheck-corpora`) |
| Date | 2026-10-14 |
| Wave | 2 (full pre-check; not in FA or E2) |
| Status | **Written before any pre-check data check of this corpus.** Inputs: desk research (`../data/interbolt-agentdojo/research.json`), the profile, the identity table `interbolt_pipeline_dirs.toml`, the registry row, phase-10c/10d census, trial and reconcile reports, routing R1 / D-113, `artefacts.toml`. No raw data was read for this file. |

## 1. Expected counts

| Quantity | Expected | Source |
|---|---:|---|
| Tree blobs / bytes at the pin | 2,254 / 39,836,058 | profile `[[source.pins]]`; phase-10c `m01_tree_meta.json`; GitHub trees API 2026-10-14 (identical) |
| Selected logs (include glob) | 2,016 (25,632,780 bytes) | `tools/readme_corpora.toml` (census, `/files`); `phase10d/interbolt-agentdojo.census.json`; phase-10c census; pin listing |
| Not selected (tree minus logs) | 238, of which 131 context artefacts (LICENSE, README, pyproject, uv.lock, 13 `src/*.py`, 9 policy YAML, `results.csv`, 24 `run_manifest.json`, 80 jsonl) and 107 other (analysis code, notebooks outputs, tests, scripts) | profile `[import] context_artefacts`; pin listing |
| Units / executions | 2,016 `agent_execution`, 1 execution per log | phase-10d census `units`; trial (`executions` 2,016, `ok` 2,015, `ok_with_issues` 1) |
| Variant | `v1.k14` 2,016 | census |
| Suites | banking 1,014, travel 1,002 | phase-10c census |
| Pipeline dirs | strict 672, targeted 672, allow_all 600, bare model 72 | phase-10c census; identity table |
| Kinds | attacked (`important_instructions`) 1,704; benign user task 216; injection-task prepass 96 | phase-10c census `model_attack`; profile quirk `injection_task_as_user_task_prepass` (96) |
| Paper (README) | 2 suites x 2 tiers x 2 repeats; 144 banking / 140 travel attacked cases per repeat; 16 / 20 benign | README Results; blog |

Per run directory (`runs/published/<suite>/<experiment>/repeat_<n>/`, 24 dirs):

| Experiment (pipeline dir) | banking per repeat | travel per repeat | Total (x2 repeats, both suites) |
|---|---:|---:|---:|
| A_ceiling (`gpt-4o-mini-2024-07-18`, no attack) | 16 | 20 | 72 |
| B_asr_model (`…-interbolt-allow_all-enforce`) | 144 + 9 prepass | 140 + 7 prepass | 600 |
| C_utility_strict (`…-interbolt-strict-enforce`, no attack) | 16 | 20 | 72 |
| C_utility_targeted (`…-interbolt-targeted-enforce`, no attack) | 16 | 20 | 72 |
| D_asr_system_strict (`…-interbolt-strict-enforce`) | 144 + 9 | 140 + 7 | 600 |
| D_asr_system_targeted (`…-interbolt-targeted-enforce`) | 144 + 9 | 140 + 7 | 600 |

## 2. Expected arms

Facets: model (`gpt-4o-mini-2024-07-18`, 1) x defence (`none`, `interbolt-allow_all-enforce`, `interbolt-strict-enforce`,
`interbolt-targeted-enforce`) x attack (`none`, `important_instructions`) x suite (banking v1.2.2: 16 UT x 9 IT; travel
v1.2.2: 20 UT x 7 IT) x repeat (0, 1). Grid cells per (suite, experiment, repeat): every UT x IT pair once.

| Expected | Cells |
|---|---|
| Present | the full README design: A (benign, no defence), B (attacked, allow_all), C (benign, strict/targeted), D (attacked, strict/targeted); every UT x IT cell, both repeats |
| Missing by design (not a defect) | attacked runs with defence `none`; benign user-task runs under allow_all; prepass in A and C |
| Extra by design | 96 prepass logs (`injection_task_*` as user task, attack `none`) in B and D dirs; the B prepass logs per repeat appear 3 times (B, D strict, D targeted) |
| Expected extra (none) | 0 logs of the superseded 2026-07-22/28 batch (`runs/published/*-gpt-4o-mini/`, git history only); 0 workspace logs (only demo policies added in `43e2b5fa`) |

## 3. Expected outcome rates (L2 comparison and the full tally)

Metric mapping: AgentDojo TraceLogger `utility` (user task solved) and `security` (`True` = injection goal achieved =
attack success) per log. README "Ceiling" = A `utility`; "With policy" = C `utility`; "ASR undefended" = B `security` on
attacked logs (the B arm is Interbolt `allow_all` in enforce mode, identity `interbolt-allow_all-enforce`, **not** defence
`none`); "ASR defended" = D `security` on attacked logs. Benign `security` is the runner constant `True` and is never
compared. Prepass logs are not in the README numbers. Block rate, refusals and coverage come from Interbolt's own
records, not the TraceLogger fields, and are not compared at L2.

| Arm (suite, experiment) | rep0 | rep1 | pooled n | Paper rate | Ref |
|---|---:|---:|---:|---:|---|
| banking A utility | 9/16 | 9/16 | 32 | 56.3% | README Results |
| travel A utility | 13/20 | 10/20 | 40 | 57.5% | README Results |
| banking C strict utility | 6/16 | 6/16 | 32 | 37.5% | README Results |
| banking C targeted utility | 7/16 | 6/16 | 32 | 40.6% | README Results |
| travel C strict utility | 7/20 | 8/20 | 40 | 37.5% | README Results |
| travel C targeted utility | 6/20 | 7/20 | 40 | 32.5% | README Results |
| banking B ASR | 71/144 | 70/144 | 288 | 49.0% | README; blog 0.49 |
| travel B ASR | 39/140 | 42/140 | 280 | 28.9% | README; blog 0.29 |
| banking D strict ASR | 0/144 | 0/144 | 288 | 0.0% | README |
| banking D targeted ASR | 0/144 | 0/144 | 288 | 0.0% | README |
| travel D strict ASR | 9/140 | 10/140 | 280 | 6.8% | README; blog (all IT6) |
| travel D targeted ASR | 11/140 | 11/140 | 280 | 7.9% | README; blog (all IT6) |

Blog repeats "1/2" = repository `repeat_0/repeat_1`. Utility under attack is not reported. At ~5 units per stratum no L2
arm reaches 20 sampled executions per repeat-stratum; pooled arms are reported with Wilson 95% intervals; the README
threshold (gap > 15 pp on n >= 20, or a binomial 95% interval excluding the paper by > 5 pp) applies where n allows.

## 4. Known quirks (already recorded)

| Id | Expected | Source |
|---|---:|---|
| `agentdojo.benign_security_constant` | 312 files | profile observed; census |
| `agentdojo.injection_task_as_user_task_prepass` | 96 files | profile; census |
| `agentdojo.silent_rerun_last_pass_only` | 1 null-final log (the same file as the trailing-calls log: travel D strict rep0 UT12/IT3) | profile; census; r1 census `issue_samples`; register `map.retry_passes_inferred` 1 |
| `agentdojo.unexecuted_trailing_calls` | 3 calls in 1 log | profile; census; `map.unexecuted_tool_call` 1 |
| `agentdojo.args_mutated_in_place` | 1,997 files with calls | profile; census |
| `agentdojo.package_version_not_code_identity` | 0 files without package version (all `0.1.35`) | profile; census |
| `agentdojo.placeholder_args_never_injection_evidence` | 12,730 present, all null | profile; census |
| `agentdojo.defence_denial_message` | 1,879 denials, text exactly `Blocked by security policy.`, strict/targeted only, 0 under allow_all | profile; routing R1; D-113 |
| Accounting | `unverifiable` 2,016; `map.accounting_unverifiable`, `map.earlier_attempts_unobservable` on all | census; trial |
| Harness identity | `code_identity = range`, `verified_code = []` (D-103): every family D rule cited by its `_unverified` twin (class I) | profile; D-24, D-103 |
| System prompt | 1 variant, 469 chars, sha256 `a021a92b…1837` (AgentDojo default) in all 2,016 | profile; phase-10c census |
| Timestamps | naive local, 2026-07-31 17:50:39 to 22:44:10, all 2,016 | phase-10c census `ts_range` |
| Tool messages vs calls | 12,727 tool messages, 12,730 calls (3 unexecuted); 2,362 tool errors incl. denials | phase-10c census |
| artefacts.toml | entries `agentdojo.art.benign_security_constant`, `.injection_task_as_user`, `.silent_rerun`, `.max_iters_pending`, `.naive_timestamp`, `.defence_benign_intervention`, `.payload_not_reaching_agent`, `.banking_ut15_confound` describe this source's behaviour but their `scope` does not list `interbolt-agentdojo` | `src/agentprov/adapters/agentdojo/artefacts.toml` |

## 5. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | 2,254 blobs, 2,016 selected; 131 context artefacts; per-dir counts of §1 |
| L1-02 strict parse | yes | expect 0 defects (phase-10c: 2,040/2,040 JSON parse ok); also the 80 jsonl context files; no archives |
| L1-03 encodings | yes | expect literal `\uXXXX`/`\x` escape residues in tool outputs (AgentDojo #214, harness property); 0 bidi/tag/C0 |
| L1-04 duplicates | yes | 0 byte-identical files expected; identical trajectories expected (B prepass x3 dirs, temperature-0 repeats, refusals identical across B/D); cross-corpus with other gpt-4o-mini-2024-07-18 v1.2.2 banking/travel runs possible |
| L1-05 arm coverage | yes | grid of §2; plus the full-population tally of `utility`/`security` per arm against §3 |
| L1-06 secrets / account paths | yes | expect 0 in the 2,016 logs; check the 24 `run_manifest.json` (`command`, `platform` keys) as context artefacts |
| L1-07 timestamps | yes | naive local, one day, monotone within a log; manifests' `run_started_at`/`run_finished_at` bracket each dir |
| L1-08 truncation / degenerate | yes | 0 empty, 0 `error` non-null, 1 null-final, 1 trailing-calls log |
| L2 import / validate / recompute / determinism | yes | trial: 2,016 ok, 0 failing checks, byte-identical at 8 vs 3 workers (phase-10d) |
| L2 A2 / A3 classes | yes | expect only the trial's register codes; PI checks on denial decisions (no `tool_execution` for denied calls) |
| L2 evidence classes | yes | expect no agentdojo D-class rule without `_unverified` twin |
| L2 identity | yes | 4 pipeline dirs -> model `gpt-4o-mini-2024-07-18`, defence per table; dir = logged `pipeline_name` in all |
| L2 redaction | yes | 0 account paths in AER/SEM/PROV |
| L2 withholding / `verify --level chain` sealed | conditional | only if L1-06 finds hits in selected units (expected not) |
| L2 outcome sanity | yes | §3 table |
| E2 delta | no | not examined in FA or E2 |
| Data-record checksum | no | no Zenodo/HF/Figshare record; git blob ids only |

## 6. Hypotheses (falsifiable)

| # | Expectation | Threshold (falsified if) |
|---|---|---|
| H1 | Full-population tallies equal the README per (suite, experiment, repeat): the 24 counts of §3 | any cell differs by >= 1 |
| H2 | Attacked `security=True` total 263 = B 222 + D strict 19 + D targeted 22; benign user-task `utility=True` total 94 (A 41, C strict 27, C targeted 26) | either total differs |
| H3 | All 41 D-arm attack successes are travel `injection_task_6`; banking D = 0 | any D success outside travel IT6 |
| H4 | travel `injection_task_1` and banking `injection_task_8` have 0 attack successes in every arm (blog: cannot succeed as posed) | >= 1 success |
| H5 | `Blocked by security policy.` denials: 0 under allow_all and A; 1,879 in strict+targeted; C-arm denials per (tier, repeat), both suites combined, close to the blog's benign refusals strict 19/21, targeted 11/14 (the blog does not name the suite scope of these counts) | allow_all > 0, total != 1,879, or any C cell outside [blog - 3, blog] |
| H6 | Exactly 1 log ends with unexecuted trailing calls, and it is the 1 null-final log: travel `D_asr_system_strict/repeat_0` `user_task_12` / `injection_task_3` (phase-10d r1 census `issue_samples`). **[corrected by fact-check]** The original wording ("if any, it is banking `user_task_3`", from the blog's iteration-cap remark) was already contradicted by that prior report; the blog's banking `user_task_3` cap claim is kept as a documentation lead (no visible trace expected in last-pass-only logs) | != 1 such log, or it is not that file |
| H7 | All 24 `run_manifest.json` record agentdojo 0.1.35 and interbolt 0.2.0 from the registry (not editable, not dirty) | any manifest with another version, editable or dirty install |
| H8 | No log of the superseded batch or of the workspace suite is selected | >= 1 |
| H9 | 0 account paths / secret-like strings in the 2,016 logs; any in manifests stay in raw only | >= 1 in a log, or any reaching AER/SEM/PROV |
| H10 | Every pipeline dir equals the logged `pipeline_name`, and every log is in the window 2026-07-31 17:50:39 to 22:44:10 | any mismatch or out-of-window log |
| H11 | L2 sample: 0 failures, 0 degenerate, register codes only the trial's four | any other code |

Recommended L2 strata: suite x experiment x repeat x kind (benign | attacked | prepass): 36 strata, about 5 each (~180
units; prepass strata hold 9 or 7 logs).

## 7. Expected movement since E2

Not applicable: the corpus has never been stored (registry `import planned`); the last runs are the phase-10d trials on
snapshots `4b79955`/`637ec55`. Bytes may differ from those trials only through code changes made since (regen items,
bug passes); counts and outcomes must not.

## 8. Fact-check (2026-10-14, adversarial, no raw data read)

Re-opened: GitHub API (repo, branches, tags, releases, issues/PRs, commits, recursive trees at `80db31a8`, `496754e9`,
`43e2b5fa`, `a74272bf`), README.md at `496754e9`, `e12b48e1` and the pin, pyproject.toml and uv.lock at the three
commits, LICENSE at the pin, PyPI JSON for `interbolt` and `agentdojo` 0.1.35, the Interbolt CHANGELOG, the blog post,
AgentDojo issues #161/#181/#194/#212/#214, arXiv 2406.13352, our phase-10c census summary, phase-10d census, r1 census
and trial, the profile, the identity table and `artefacts.toml`.

Confirmed:
- Pin `43e2b5fa` = head of `main` (2026-08-19T07:59:57Z); 1 branch, 0 tags, 0 releases, 0 issues, 6 merged PRs.
- Tree 2,254 blobs / 39,836,058 bytes (not truncated); include-shaped logs 2,016 / 25,632,780 bytes; all 24 per-dir
  counts of §1; banking 1,014 / travel 1,002; 131 context artefacts (profile globs, `*` crossing `/`) and 107 other;
  0 workspace logs; the `runs/` subtree is identical at `496754e9` and the pin; the earlier `*-gpt-4o-mini` batch
  (repeat_0 only) is in history only.
- All 24 README per-repeat counts and the 8 block rates in §3 (README Results table at the pin, unchanged since
  `496754e9`); pooled rates recomputed. README: run B is `allow_all` in enforce mode ("the undefended baseline");
  Interbolt 0.2.0; both packages used unmodified.
- Blog (D. Kirchhoff, 2026-08-03): 0.49 / 0.29 / 0.00 / 0.07; model_refused 68/63, 34/30; benign refusals 19/21 and
  11/14; 1 policy error in 8,669 decisions (travel targeted, repeat 2); travel IT1 and banking IT8 cannot succeed;
  travel residual = IT6; banking UT3 iteration cap; banking runs on a modified checkout (0.57) not used; caption
  8/6 vs text 9/7; repeats numbered 1/2.
- uv.lock at `80db31a8` and `496754e9`: interbolt 0.2.0 and agentdojo 0.1.35 from the PyPI registry; at the pin
  `interbolt==0.3.0` with `{ editable = "../interbolt" }`. Wheel sha256 `364bea42…affd` (2025-10-27). PyPI interbolt
  0.2.0 2026-07-26, 0.3.0 2026-08-05; CHANGELOG items (0.2.0 bare `check()` fail-open fix; 0.3.0 event schema 9 -> 11,
  policy documents 2.0).
- LICENSE at the pin: blob `261eeb9e`, 11,357 bytes, Apache-2.0 text with no filled copyright line; API spdx Apache-2.0.
- Census figures used in §4 and H2 (575 = 312 + 263, 1,879, 12,730 / 12,727, 2,362, 1,997, 469-char prompt, time range)
  match our own phase-10c / phase-10d reports. `artefacts.toml`: the eight named entries omit `interbolt-agentdojo`.

Corrected:
- `src/` **did** change between `80db31a8` and `496754e9`: the run-path modules (executor, pipeline, run_benchmark,
  manifest, record_corpus, models_ext) have identical blob ids, but `compute_results.py` grew from 24,640 to 41,874
  bytes and two compare scripts moved into `src/`. The script that produced the README table is therefore not the
  80db31a8 one (relevant to the open question on `compute_results` filters). Fixed in `research.json`.
- `43e2b5fa` does not touch README.md; the README at the pin equals `e12b48e1`. Fixed in `research.json`.
- H6 and the silent-rerun row: the single trailing-calls log is also the single null-final log, and our r1 census names
  it (travel D strict repeat_0 UT12 / IT3), so the original H6 (banking UT3) was already contradicted. H6 restated.
- H5: the blog does not state the suite scope of the benign-refusal counts; marked as read for both suites combined.

Unverifiable here: the time zone of the naive timestamps (the UTC+2 reading is an inference); whether B prepass logs
are trajectory-identical across B / D dirs (D runs enforce a policy); OpenAI output terms. Minor: the README header
link to the blog (`deconvoluteai.com/blog/provenance-agentdojo-benchmark`) redirects to a 404; the body link works.
