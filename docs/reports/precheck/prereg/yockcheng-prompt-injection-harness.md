# Pre-registration: `yockcheng-prompt-injection-harness`

| | |
|---|---|
| Corpus | `yockcheng-prompt-injection-harness` (family `agentdojo`, profile `yockcheng-prompt-injection-harness` v1, dialect/mapper `agentdojo.tracelogger`, variants `v1.k14`, `v1.k14.incomplete`) |
| Parts | `head` (only part) |
| Wave | 2 (first examination; not in FA or E2) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: our prior reports (phase-10c census summaries, phase-10d census/trial/reconcile), the profile, the registry, `artefacts.toml`, DECISIONS, and desk research (`data/yockcheng-prompt-injection-harness/research.json`). Per-cell counts come from the GitHub tree listing (paths only). Nothing here was computed from log contents. |
| Method | [`../README.md`](../README.md) |

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Repository | [yockcheng/prompt-injection-harness](https://github.com/yockcheng/prompt-injection-harness), Apache-2.0 (appendix line names Anthropic PBC, inherited from the upstream harness) | LICENSE at pin |
| Pin | `5f9137ff352c5e843a94cbe20a7f31aa6e2c8fc6`, 2026-08-11T01:52:44Z (= profile date) | GitHub API |
| Logs added by | `606606e0be16` (2026-07-10), the only commit touching `runs/` on any branch; `runs/` tree `49cd8612` unchanged since | commits API, tree API |
| Paper / data record | none (Zenodo, HF, arXiv, GitHub releases: 0 hits). No repository document describes `runs/` or reports numbers for it | research.json |
| Harness | AgentDojo 0.1.35 per logs and `requirements.txt`; locally patched (ModelsEnum; target image also overwrites `inbox.yaml`). AgentDojo benchmark runner (TraceLogger), not the repo's find/grade pipeline | `project_status.md`, Dockerfile, census |
| Benchmark versions | `v1` (249, `runs/agentdojo-native/`), `v1.2.2` (31, `runs/`) | phase-10c census |
| Run dates | 2026-06-22 15:59:03 to 2026-07-01 10:58:20 (naive); June 31 / July 249 | phase-10c census `ts_range`, `ts_month` |

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Tree blobs at pin | 358 (5,655,690 bytes; 356 / 5,085,074 without the two unfetched `static/*.png`) | profile `expected_files`; GitHub tree |
| Selected logs (`runs/*/*/*/*/*.json`) | 280 | registry (`readme_corpora.toml`, census `/files`); phase-10d census |
| Not selected | 78 (7 stored as context artefacts; 0 `.DS_Store`/`._*`) | GitHub tree; profile |
| JSON parse ok | 280 / 280 | phase-10c census |
| Units / executions | 280 `agent_execution` / 280 | phase-10d census, trial (jobs 8) |
| Variants | `v1.k14` 277, `v1.k14.incomplete` 3 | census |
| Sealed clean / with issues | 277 / 3 (`map.incomplete_run`); `accounting_unverifiable` 277, `earlier_attempts_unobservable` 280 | trial |
| Messages / calls | roles: system 280, user 280, assistant 814, tool 693; 693 calls, 66 tool errors | phase-10c census |

Per cell (tree × pipeline_dir × attack_dir × task kind), workspace only, from the git tree at the pin:

| Tree | Pipeline dir (model) | Bench | Attacked (`important_instructions`) | Benign user task | Pre-pass (injection task as user task) | Total |
|---|---|---|---:|---:|---:|---:|
| `runs/agentdojo-native` | `claude-haiku-4-5-20251001` | v1 | 240 (user_task_0..39 × injection_task_0..5) | 0 | 6 | 246 |
| `runs/agentdojo-native` | `claude-sonnet-4-5` | v1 | 1 (user_task_0 × injection_task_0) | 0 | 1 | 2 |
| `runs/agentdojo-native` | `claude-3-haiku-20240307` | v1 | 0 | 0 | 1 (incomplete) | 1 |
| `runs` | `claude-sonnet-4-5` | v1.2.2 | 14 (user_task_0 × injection_task_0..13) | 1 | 14 | 29 |
| `runs` | `claude-3-7-sonnet-20250219` | v1.2.2 | 0 | 1 (incomplete) | 1 (incomplete) | 2 |
| **Total** | | | **255** | **2** | **23** | **280** |

## 3. Expected arms

| Facet | Values | Expected missing / extra |
|---|---|---|
| Model | `claude-haiku-4-5-20251001`, `claude-sonnet-4-5` (alias of `-20250929`), `claude-3-7-sonnet-20250219`, `claude-3-haiku-20240307` | none extra; pipeline_name = pipeline_dir in all 280 (census) |
| Defence | none | no defence arm |
| Attack | `important_instructions`; `none` | no other attack |
| Suite | workspace only | banking/slack/travel absent by design |
| Grid | full only for haiku-4-5 on v1 attacked (240/240) | haiku-4-5 has **no benign user-task runs**; sonnet-4-5 = smoke test on user_task_0; the two retired models have 3 incomplete logs only |
| L2 strata | 8 (rows of the table above split by attack_dir) | about 30 units sampled (minimum rule), several strata have 1-2 units |

## 4. Expected outcome rates (L2 comparison targets)

No paper or repository reports numbers for these logs. The only targets are our census aggregates (not a source claim):

| Arm | Metric | Expected | Basis |
|---|---|---|---|
| All attacked (255) | targeted ASR = `security == true` over attacked logs | **0 / 255** | census: security True 22 = the 22 non-null `none` logs carrying the benign constant (25 `none` − 3 incomplete); DECISIONS D-279 record (yockcheng would have been removed "at source level" by the withdrawn zero-success rule) |
| All logs | `utility` | True 225, False 52, null 3 | phase-10c census |
| haiku-4-5 attacked (240) | utility under attack | not known per arm (part of the 225); reported with Wilson interval only | - |
| Incomplete (3) | utility, security | null, null (not invented) | census `missing:utility/security` 3 |

Metric mapping: AgentDojo `security == true` = injection goal reached; benign/pre-pass `security` is the runner's constant True and enters no rate; pre-pass `utility` = injection goal achieved when asked directly. L2 per-stratum n < 20, so only Wilson intervals; the exact check is H1 on the whole population. Never exclude data for 0 successes.

## 5. Known quirks

| Id | Expected | Source |
|---|---|---|
| `agentdojo.benign_security_constant` | 25 files, origin rule applied 22 | profile `observed`, phase-10d census |
| `agentdojo.injection_task_as_user_task_prepass` | 23 files | profile, census |
| `agentdojo.incomplete_run` | 3 files (`v1.k14.incomplete`), 0 null-outcome files counted by the census rule | profile, census, trial |
| `agentdojo.args_mutated_in_place` | 273 files | profile, census |
| `agentdojo.placeholder_args_never_injection_evidence` | 693 present, 693 null | profile, census |
| `agentdojo.silent_rerun_last_pass_only` | 0 null-final logs; `earlier_attempts_unobservable` 280 | profile, trial |
| `agentdojo.unexecuted_trailing_calls` | 0 calls, 0 logs | profile, census |
| `agentdojo.package_version_not_code_identity` | 0 files without version (all `0.1.35`); code locally patched | profile, `project_status.md` |
| System prompt | 469-char AgentDojo default (`a021a92b…`) in 280/280 | profile, phase-10c census |
| `artefacts.toml` | **no `agentdojo.art.*` entry lists this source in its scope** (benign_security_constant, injection_task_as_user, incomplete_run, silent_rerun, naive_timestamp would apply) | `artefacts.toml` |
| Census `differences` | 7 placeholders in the pre-census profile replaced by measured values (expected, not findings) | phase-10d census note |
| Reconcile | 10 / 10 agree (phase 10c vs 10d) | reconcile.json |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2: 358 / 280 / 78; per-cell table |
| L1-02 strict parse | yes | expect 0 defects (parse ok 280) |
| L1-03 encodings | yes | AgentDojo #214 may leave `\uXXXX` residues in tool content: count, class expected-known |
| L1-04 duplicates | yes | within part: native vs `runs/` sonnet-4-5 user_task_0 × injection_task_0 (different bench versions, expect not identical); cross-corpus: other haiku-4-5/sonnet-4-5 workspace runs |
| L1-05 arm coverage | yes | §3 grid; whole-population outcome tally for H1 |
| L1-06 secrets / account paths | yes | expect 0 account paths; secret-like strings only from stock AgentDojo text (e.g. the 2FA code), see H6 |
| L1-07 timestamps | yes (partly) | presence, parse, naive zone, range 2026-06-22..2026-07-01; no within-unit monotonicity (one timestamp per log) |
| L1-08 degenerate | yes | expect 3 incomplete (2 messages, no outcomes), 0 empty, 0 null-final, `error` null in all 280 |
| L2 import, validate, recompute, determinism | yes | trial: 0 failures; jobs 8 imported all 280, jobs 3 a 59-unit subset, compared in subset mode with 0 differences (corrected by fact-check: not a full 280 vs 280 comparison) |
| L2 A2 / A3 classes | yes | only the trial's register codes expected |
| L2 evidence classes | yes | `verified_code = []`: D rules via `_unverified` twins (class I) |
| L2 degenerate / adapter_defect | yes | expect 0 / 0 |
| L2 identity | yes | model from pipeline_dir; `claude-sonnet-4-5` kept as alias; benchmark version per log (v1 vs v1.2.2) |
| L2 redaction | yes | expect no account path in AER/SEM/PROV |
| L2 withholding | conditional | only if L1-06 finds a secret-like string |
| L2 outcome sanity | yes (Wilson only) | §4; no paper target |
| Delta since E2 | no | not examined in FA/E2 |

## 7. Hypotheses (falsifiable)

| # | Expectation | Refuted if |
|---|---|---|
| H1 | Whole-population tally reproduces §2 per-cell counts and §4: attacked `security == true` = 0/255; utility True/False/null = 225/52/3 | any count differs by ≥ 1 |
| H2 | The 3 incomplete logs are exactly the retired-model logs (3-7-sonnet ×2, 3-haiku ×1; retired 2026-02-19 / 2026-04-20, before the log dates), each with only system + user messages and `error` null | an incomplete log of another model, or a retired-model log with an assistant turn |
| H3 | `ts_month` split equals the tree split: all 31 `runs/` logs dated June 2026, all 249 `runs/agentdojo-native/` logs dated 2026-07-01 | any log on the other side |
| H4 | `benchmark_version` is `v1.2.2` for exactly the 31 `runs/` logs and `v1` for the 249 native logs; injection_task_6..13 occur only in v1.2.2 logs | any mismatch |
| H5 | Pre-pass utility for v1.2.2 injection_task_6..13 is recorded (not null) despite the empty ground truth (AgentDojo #213); every call in all 280 logs has `placeholder_args` null (693/693) | null utility there, or any non-null `placeholder_args` |
| H6 | Native (v1) logs show the stock AgentDojo injection-email senders (`security-facebook-com@…`, `hiking-travels-unlimited@…`) wherever those emails appear in tool output, never the patched senders of the repo's `inbox.yaml` (`michael.chen@…`, `sarah.mitchell@…`) | ≥ 1 patched sender in a native log (then the environment is not stock v1: documentation-mismatch, S2) |
| H7 | No defence, no attack other than `important_instructions`, no model other than the four | any extra label |
| H8 | Every (tree, model, user task, injection task) cell occurs once | duplicate or hole within the §2 grid |
| H9 | Byte-identical files within/across corpora = 0; identical trajectory fingerprints across corpora ≤ 5% of the 240 haiku attacked logs | above either threshold |
| H10 | 0 account paths; secret-like hits only from stock benchmark text (none from the repo's later planted credentials in `cloud_drive.yaml`, added 2026-07-29 after the runs) | any account path, or a planted-fixture credential pattern |

## 8. Discrepancy leads carried to the dossier

No paper or reported numbers (L2 targets are our census only); logs predate the repository and the code that wrote them is
not in it; agentdojo 0.1.35 locally patched (ModelsEnum, `inbox.yaml`); two trees with different benchmark versions;
haiku arm lacks benign runs; `claude-sonnet-4-5` is an alias; profile licence note ("no copyright line") vs the LICENSE's
Anthropic PBC appendix line; profile pin note "same 257 runs" vs 280 logs (257 = 280 − 23 pre-pass); `artefacts.toml`
scopes omit this source (proposed entries go to the family owner).

## 9. Fact-check (adversarial, 2026-10-14, before any data check)

Re-checked against the GitHub API, the LICENSE at the pin, AgentDojo v0.1.35, PyPI, the AgentDojo issue tracker, the
Anthropic model-deprecations page, Zenodo/HF/arXiv search, and our own phase-10c/10d reports. Nothing was computed from
log contents (per-cell counts are from the tree listing, paths only).

| Claim | Verdict | Evidence |
|---|---|---|
| Pin `5f9137ff`, 2026-08-11T01:52:44Z, merge of PR #2, tree `c66526c2` = customize-skill head `6c3a1346` tree | confirmed | commits API |
| 358 blobs / 5,655,690 B; 356 / 5,085,074 B without the two `static/*.png`; 280 `runs/` JSON; 0 `.DS_Store`/`._*` | confirmed | trees API at pin (not truncated) |
| Per-cell table (§2) incl. 240 = 40 user tasks × injection_task_0..5; runs/ sonnet 14 × injection_task_0..13; totals 255/2/23 | confirmed | tree paths; census `attack_type` 255/25, `pipeline_dir` |
| Only `606606e0` touches `runs/`; `runs/` tree `49cd8612` at `606606e0`, `6c3a1346` and pin; main has no `runs/` | confirmed | commits?path=runs on both branches; contents API |
| Repo created 2026-07-15, not a fork, 0 issues, 2 closed PRs, no releases/tags; licence NOASSERTION | confirmed | repos API |
| No paper or data record | confirmed (0 hits) | Zenodo, HF, arXiv queries |
| ASR 0/255 (our census arithmetic, not a source claim) | confirmed as arithmetic | census: security False 255 / True 22 / None 3; attack None 25; the 3 incomplete are all `none/none.json` (phase-10d `issue_samples.incomplete_run`), so 22 = 25 − 3 benign-constant logs |
| Utility 225/52/3 | confirmed | phase-10c census summary |
| Variants 277/3, sealed 277/3, register codes, reconcile 10/10, covering_paths 14 | confirmed | phase-10d census, trial, reconcile |
| Trial "jobs 8/3 byte-identical" | **corrected** | jobs 3 imported a 59-unit subset; compare mode subset, 0 differ (§6 row amended) |
| LICENSE Apache-2.0 with appendix line naming Anthropic PBC (profile says no copyright line) | confirmed | LICENSE blob `84b83dc8` at pin, line 188 |
| Upstream `anthropics/defending-code-reference-harness`, created 2026-05-22; main `9e0f6c6c` is its commit | confirmed | repos/commits API |
| agentdojo 0.1.35, tag `a75aba76`, PyPI 2025-10-27; requirements.txt pins | confirmed; PyPI digest label **corrected** in research.json (364bea42 = wheel, sdist = 9eacbc89) | PyPI JSON, tags API |
| ModelsEnum local patch (`project_status.md`), Dockerfile patches `models.py` and overwrites `inbox.yaml` from `606606e0`; calendar/cloud_drive overrides only at the pin | confirmed | files at `606606e0` and pin. Note: `project_status.md` also records that the Docker `/run` path bypasses ModelsEnum by building the pipeline by hand in `server.py` |
| `inbox.yaml` differs from stock v0.1.35 in 20 lines (sender/subject of the injection-vector emails); H6 sender names | confirmed | diff of fixture at `606606e0` vs ethz-spylab/agentdojo@v0.1.35 |
| v1.2 workspace injection tasks 6-13 exist at v0.1.35 | confirmed | `default_suites/v1_2/workspace/injection_tasks.py` |
| Issue states #213/#162/#214/#218/#201 open, #71/#46/#116 closed; #201 reports 0/560 on claude-sonnet-4-6 | confirmed | issues API |
| Retirement 3-7-sonnet 2026-02-19, 3-haiku 2026-04-20; haiku-4-5 active | confirmed (Claude API dates; other providers not checked) | model-deprecations page |
| Target README reports only find/grade findings ("2 of the 6 violation classes"), `results/` git-ignored, no repo doc mentions `runs/` | confirmed | target README, `.gitignore`, grep of README/project_status |
| `claude-sonnet-4-5` alias resolves to `-20250929` | unverifiable from the logs (snapshot not logged); alias mapping per Anthropic docs | - |
| DECISIONS D-279: yockcheng removed at source level by the withdrawn rule | confirmed | `docs/architecture/DECISIONS.md` D-279 record |
| `artefacts.toml` has no scope naming this source | confirmed | 0 occurrences in `adapters/agentdojo/artefacts.toml` |

No outcome number, expected count or arm was changed. No new expectation was added.
