# Pre-registration: `tacit-agentdojo`

| | |
|---|---|
| Corpus | `tacit-agentdojo` (family `agentdojo`, profile `tacit-agentdojo` v1, dialect/mapper `agentdojo.tracelogger`, variants `v1.k14`, `v1.k14.incomplete`) |
| Parts | `head` (only part) |
| Wave | 2 (first examination; not in FA or E2) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: our prior reports (phase-10c census summaries, phase-10d census, trial and reconcile), the profile and identity table, the registry, `artefacts.toml`, DECISIONS, and desk research (`data/tacit-agentdojo/research.json`). Per-cell counts come from the GitHub trees API listing of the pin (paths and sizes only). Nothing here was computed from the raw logs. |
| Method | [`../README.md`](../README.md) |

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Repository | [CSSLab/Tacit](https://github.com/CSSLab/Tacit), Apache-2.0 (no copyright line, no NOTICE) | LICENSE at pin; GitHub API |
| Pin | `995692d3cd42c32e08cf0db8a5fae55fec272f1a` "initial release", 2026-09-23T18:31:25Z; the **only** commit and head of `main` on 2026-10-14; no tags, releases or issues | GitHub API |
| Paper | [arXiv:2609.33039v1](https://arxiv.org/abs/2609.33039v1), *Agent Safety From Within: Detecting Harmful Trajectories from LLM Internal States* (Jiao, Anderson; 2026-09-27; v1 only; under review). Our profile/README record the repository's working title and "no identifier" | arXiv API |
| Data record | none (Zenodo 0 hits, HF 0 hits); the Git repository is the only release | research.json |
| Harness | AgentDojo 0.1.35 (script comment + logs), `--benchmark-version v1.2.2`, attack `important_instructions`, no defence; pydantic shim `agentdojo_compat` loaded; install not pinned | `scripts/data/collect_agentdojo.sh`; phase-10c census |
| Clients | Llama: AgentDojo `LOCAL` (own prompting/parsing; pipeline_name `local`); Qwen: `VLLM_PARSED` (vLLM hermes parser; `vllm_parsed`) | collect script; census |
| Checkpoints | `meta-llama/Llama-3.1-8B-Instruct`, `Qwen/Qwen3-4B-Instruct-2507` via `tacit/config.py`; no revision | config.py at pin |
| Run window | 2026-07-10 04:36:19 to 08:11:20 (naive), before the repository existed (2026-08-17) | phase-10c census `ts_range` |
| Purpose | training/evaluation data of a trajectory-safety detector; agent outcomes are not the paper's object | paper App. B.1 |

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Tree blobs at pin | 2,139 (34,387,446 bytes; 34,094,608 without `assets/figure1.png`) | profile `expected_files`; GitHub tree |
| Selected logs (`data/agentdojo/*/*/*/*/*/*.json`) | 2,076 (32,102,611 bytes) | registry/`readme_corpora.toml` (census `/files`); phase-10d census; GitHub tree |
| Not selected | 63 (59 code/doc + 4 `data/splits/*.json`); context artefacts stored as supporting: LICENSE, README.md, requirements.txt, collect script, compat shim, `tacit/data/agentdojo.py`, 4 split files | profile; tree |
| JSON parse ok | 2,076 / 2,076 (2,080 incl. splits) | phase-10c census |
| Units / executions | 2,076 `agent_execution` / 2,076 | phase-10d census; trial import with jobs 8 (2,076). **[corrected]** The jobs-3 re-import covered a 416-execution subset only (compare mode `subset`, 0 differ), not all 2,076 |
| Variants | `v1.k14` 2,075, `v1.k14.incomplete` 1 | census |
| Sealed clean / with issues | 1,979 / 97 (`unexecuted_tool_call` 96, `incomplete_run` 1, `retry_passes_inferred` 2) | trial |
| Paper / loader n | 2,075 (the loader drops the log without `security`) | Table 4; data/README.md |

Per cell (model dir / client × suite; attacked / benign), git tree at the pin:

| Model dir / client | banking | slack | travel | workspace | Total |
|---|---|---|---|---|---:|
| `llama3.1-8b-instruct` / `local` | 144 / 16 | 105 / 21 | 140 / 20 | 560 / 40 | 1,046 |
| `qwen3-4b-instruct` / `vllm_parsed` | 144 / 16 | 105 / 21 | 140 / 20 | **544** / 40 | 1,030 |

Suites: workspace 1,184, banking 320, travel 320, slack 252; attacked 1,882, benign 194 (census). Injection tasks:
banking 0-8, slack 1-5, travel 0-6, workspace 0-13 (v1.2.2); user tasks 16/21/20/40.

## 3. Expected arms

| Facet | Values | Expected missing / extra |
|---|---|---|
| Model | `llama3.1-8b-instruct`, `qwen3-4b-instruct` (labels verbatim, D-105; client label never a model, D-106) | none extra |
| Defence | none | none |
| Attack | `important_instructions`; `none` (benign) | none extra |
| Suite | workspace, banking, travel, slack (v1.2.2) | none missing |
| Cells | 2 × (144 + 105 + 140 + 560) attacked, 2 × 97 benign | qwen workspace: 16 attacked cells missing (UT38 × IT12-13; UT39 × IT0-13); UT38 × IT11 present but incomplete |
| Pre-pass | AgentDojo 0.1.35 would write 35 injection-task-as-user-task logs per model in an attacked run | 70 absent (census prepass 0); process and `vllm_server.log` files absent |

L2 strata: model × suite × attack = 16; about 5 per stratum, ~80 units.

## 4. Expected outcome rates (L2 comparison targets)

The paper reports **no** utility or ASR per model or suite. Its only outcome-derived numbers are pooled label counts.
Metric mapping: AgentDojo `security == true` = injection goal reached on attacked runs; constant `true` on benign runs
(maintainer, [#95](https://github.com/ethz-spylab/agentdojo/issues/95); quirk `benign_security_constant`). Paper
"unsafe" = agent completes the injected task (App. B.1). Released loader: unsafe = `security is False`, rows with
`security` None or `error` set dropped.

| Target | Value | Source |
|---|---|---|
| Rows with a `security` value | 2,075 | Table 4; data/README.md; census (`None` 1) |
| `security == true` | 369 (paper "unsafe", Tables 3-4) | census 369; paper |
| `security == false` | 1,706 (paper "safe"; loader "unsafe") | census 1,706; Table 4; data/README.md |
| Benign `security == true` | 194 of 194 | census `benign_security_constant` |
| Attacked `security == true` (targeted ASR, pooled) | 175 / 1,881 = 9.3% (derived 369 − 194) | derived from census |
| `utility` true / false / None | 750 / 1,325 / 1 (pooled; no per-arm split published) | phase-10c census |
| Detector macro-F1 (AgentDojo column) | Table 1, 2, 5: not comparable to logged fields | paper |

Per-arm L2 rates: Wilson intervals only, no paper target; the pooled numbers are tested on the whole population (H2).

## 5. Known quirks

| Id | Expected | Source |
|---|---|---|
| `agentdojo.benign_security_constant` | 194 files, 194 judgements | profile `observed`, census |
| `agentdojo.injection_task_as_user_task_prepass` | 0 files | profile, census |
| `agentdojo.args_mutated_in_place` | 1,695 files | profile, census |
| `agentdojo.placeholder_args_never_injection_evidence` | 7,504 present, all null | profile, census |
| `agentdojo.unexecuted_trailing_calls` | 96 calls in 96 logs | profile, census, trial |
| `agentdojo.silent_rerun_last_pass_only` | 2 null-final logs (3 incl. the incomplete one, reconcile); `earlier_attempts_unobservable` on 2,076 | profile, reconcile, trial |
| `agentdojo.incomplete_run` | 1 file (qwen workspace UT38 × IT11), `missing:security`, `missing:utility` | profile, census |
| `agentdojo.provider_call_id_anomalies` | 3,750 null ids in 699 logs; 0 duplicates | profile, census |
| `agentdojo.package_version_not_code_identity` | 0 files without version (all `0.1.35`) | profile |
| System prompt | 469-char AgentDojo default in 2,076 | profile, census |
| Tool errors | 953 tool messages with an error | phase-10c census |
| Unregistered tool names | ~24 calls (18 with a trailing `/`) | phase-10c census tool tally |
| Accounting | `unverifiable` 2,076 | census, trial |
| Evidence | `verified_code = []`: every D rule cited through its `_unverified` twin (D-24) | profile |
| `artefacts.toml` | no entry scopes `tacit-agentdojo`; the generic entries matching the profile quirks (benign_security_constant, silent_rerun, max_iters_pending, provider_ids, validity_defects, local_parse_drop, naive timestamps) are expected-known by analogy only | artefacts.toml |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2; selection from `include` glob and `context_artefacts` |
| L1-02 strict parse | yes | expect 0 defects |
| L1-03 encodings | yes | #214 may leave `\uXXXX` residues in tool content: count, expected-known |
| L1-04 duplicates | yes | within part (two models: expect 0) and cross-corpus (no other corpus with these checkpoints on v1.2.2 known) |
| L1-05 arm coverage | yes | §3, plus the whole-population tally for H2 |
| L1-06 secrets / account paths | yes | expect 0 |
| L1-07 timestamps | yes (partly) | presence, parse, naive zone, range 2026-07-10; within-unit monotonicity n/a |
| L1-08 degenerate | yes | expect 0 empty, 1 incomplete, 2 null-final, 0 run errors |
| L2 import, validate, recompute, determinism | yes | trial: 0 failures; byte-identical across jobs on the 416-execution jobs-3 subset only **[corrected]**: full-population determinism has not been shown |
| L2 A2 / A3 classes | yes | expect only the trial's register codes |
| L2 evidence classes | yes | D rules only as `_unverified` twins |
| L2 degenerate / adapter_defect | yes | expect 0 / 0, including the unregistered tool names |
| L2 identity | yes | model = directory label, class I (`agentdojo.pipeline_dir_is_model_identity@1`); provider `local`/`vllm`; defence none |
| L2 redaction | yes | expect no account path in AER/SEM/PROV |
| L2 withholding | conditional | only if L1-06 finds anything |
| L2 outcome sanity | Wilson only | no per-arm paper rate (§4) |
| Delta since E2 | no | not examined in FA/E2 |

## 7. Hypotheses (falsifiable)

| # | Expectation | Refuted if |
|---|---|---|
| H1 | Cell counts equal §2 table; every (model, suite, UT, IT) cell occurs once; the only holes are the 16 qwen workspace cells | any count differs by ≥ 1, a duplicate, or another hole |
| H2 | `security`: true 369 = 194 benign + 175 attacked; false 1,706, all attacked; missing 1. The paper's "unsafe 369" therefore includes the 194 benign runs, or its labels are swapped against the loader (source documentation-mismatch, S2) | any count differs by ≥ 1 |
| H3 | The one log without `security`/`utility` is qwen workspace UT38 × IT11 and has the latest timestamp of the qwen workspace attacked logs | another file, or a later qwen workspace log |
| H4 | `benchmark_version` v1.2.2 and package 0.1.35 in 2,076; `error` null in 2,076 | any other value |
| H5 | 0 logs under `injection_task_*` and 0 with `attack_type` none and a non-null `injection_task_id` | ≥ 1 |
| H6 | All 3,750 null call ids are in `llama3.1-8b-instruct/local` logs | ≥ 1 null id in a qwen log |
| H7 | Llama `local` turns whose text holds a `<function=` tag but no parsed call = 0 (census); llama final answers that are an empty string ≤ 1% of 1,046 (#220) | > 0 tag-only turns (then check the census detector's scope), or > 10 empty finals |
| H8 | Calls with a tool name outside the v1.2.2 suite tool set ≈ 24 (± 3), every one answered by a tool error, none mapped as `adapter_defect` | outside the band, a non-error result, or an adapter_defect |
| H9 | Timestamps all within 2026-07-10 04:36:19..08:11:20; per model and suite, every attacked log is later than the last benign log (script runs `none` first) | any outside, or an attacked log before a benign one (report; S3) |
| H10 | Byte-identical files = 0; identical trajectory fingerprints across corpora ≤ 1% of 2,076 | above either |
| H11 | 0 secret-like strings and 0 account paths | ≥ 1 |
| H12 | Among slack IT5 attacked successes, every membership call (`invite_user_to_slack`, `add_user_to_channel`, `remove_user_from_slack`) executed without error (#168) | ≥ 1 success resting on a failed call (S2) |

## 8. Discrepancy leads carried to the dossier

Paper label direction vs loader vs AgentDojo semantics (H2); paper n 2,075 vs 2,076 released (H3); truncated qwen
workspace arm (H1); curated release without pre-pass or process logs (H5); `tacit_model_dirs.toml` says no checkpoint is
recorded but `tacit/config.py` names the HF ids (no revision), and neither `tacit/config.py` nor `data/README.md` is a
context artefact (S3, documentation-mismatch in our docs); paper identifier missing from profile/README/registry
(arXiv:2609.33039, different title); the only commit postdates the runs, so the harness that wrote them is unverified;
LocalLLM defects #150/#202/#219/#220 on the 1,046 Llama logs (H7); benchmark validity defects #213 (workspace IT6-13),
#181 (banking IT0/1/3), #168 (slack IT5) bear on the 175 successes; `artefacts.toml` scopes omit this source.

## 9. Fact-check (2026-10-14, adversarial pass before commit)

Re-opened every cited source; nothing below was computed from the raw logs (paths and sizes from the GitHub trees API only).

| Claim | Verdict | Evidence |
|---|---|---|
| Table 4: AgentDojo 2,075 / unsafe 369 / safe 1,706 / test 421 | confirmed | arXiv:2609.33039v1 App. B.1, Table 4; Table 3 "AgentDojo injected task carried out (369)"; Table 4 total unsafe 3,996 includes 369 |
| Table 1 and Table 2 AgentDojo macro-F1 values (all nine per table) | confirmed | Tables 1-2 of v1 (only version, arXiv API 2026-10-14) |
| Paper defines unsafe as the agent completing the injected task; runs both with no attack and under important_instructions | confirmed | App. B.1 |
| Footnote 1 links CSSLab/Tacit; paper is v1 only, "Preprint. Under review.", CC BY-SA 4.0 | confirmed | abs page and PDF |
| Loader: unsafe = `security is False`; drops `security` None or `error` set; data/README.md expects `agentdojo n=2075 unsafe=1706` | confirmed | `tacit/data/agentdojo.py`, `data/README.md` at the pin |
| Label-direction lead | confirmed as a lead (doc-level) | Extra doc-only support: for the other five benchmarks the data/README.md `unsafe` counts equal Table 4's Unsafe column (301, 1,080, 497, 806+409=1,215, 534); AgentDojo is the only one where the README figure (1,706) equals Table 4's Safe column instead |
| AgentDojo `security` semantics (true = attack succeeded; always true without attack) | confirmed | maintainer comment, [#95](https://github.com/ethz-spylab/agentdojo/issues/95) |
| 0.1.35 pre-pass (injection tasks run as user tasks for non-DoS attacks) and utility False / security True on context-length and server errors | confirmed | `src/agentdojo/benchmark.py` at tag v0.1.35 (`a75aba76`); `--benchmark-version` default v1.2.2 |
| Pin `995692d3` is the only commit, head of `main`; no tags, releases, issues; 1 fork; repo created 2026-08-17 | confirmed | GitHub API |
| Tree: 2,139 blobs / 34,387,446 bytes; PNG 292,838; 2,076 logs / 32,102,611 bytes; 63 others incl. 4 splits; per-cell table of §2 incl. qwen workspace 544 and the missing UT38 × IT12-13, UT39 × IT0-13 | confirmed | trees API listing at the pin |
| `.gitignore` excludes only `runs/`, `data/raw/` and caches; the script writes `vllm_server.log` and `<attack>_<suite>.log` into `data/agentdojo/<model>/` | confirmed | `.gitignore`, `scripts/data/collect_agentdojo.sh` at the pin |
| `tacit/config.py` names both HF ids without revision; HF heads `0e9e39f2` (2024-09-25, gated, llama3.1) and `cdbee75f` (2025-09-17, apache-2.0) | confirmed | config.py at the pin; HF model API |
| Licence: Apache-2.0 template text, copyright line left as the `[yyyy] [name of copyright owner]` placeholder; AgentDojo MIT | confirmed | LICENSE at the pin; AgentDojo LICENSE at v0.1.35 |
| No data record (Zenodo, HF, Figshare) | confirmed | Zenodo API 0 hits (repo name and title); HF datasets search and author queries empty; Figshare search empty |
| Issue titles and content of #88, #150, #168, #181, #188, #201, #202, #213, #214, #219, #220 | confirmed (titles; whether each defect occurs in these logs is for L1/L2) | GitHub API |
| Census figures (security 369/1,706/1; utility 750/1,325/1; 949/933 attacked; 3,750 null ids in 699 logs; 953 tool errors; 24 off-set tool names, 18 with `/`; ts range) | confirmed against our reports | phase-10c census summaries; `docs/reports/phase10d/tacit-agentdojo.census.json` |
| Trial "jobs 8 and 3" over 2,076 | **corrected** | `docs/reports/phase10d/tacit-agentdojo.trial.json`: jobs 8 imported 2,076; jobs 3 imported 416 (subset compare, 0 differ) |
| arXiv:2604.18519 described as "same first author" | corrected (detail) | 7 authors; journal ref ACL 2026 long paper, DOI 10.18653/v1/2026.acl-long.1844 (arXiv API) |
| D-105 / D-106 cited for Tacit | confirmed | DECISIONS.md; note D-105 keeps the label verbatim "when no checkpoint is recorded", a premise the IDENTITY lead contests |
| 175 attacked successes / 1,881 | derived, unverified until H2 | 369 − 194 assumes every benign log has `security` true, which AgentDojo 0.1.35 code guarantees but no report has counted |

