# Pre-registration: `mcphunt`

| | |
|---|---|
| Corpus | `mcphunt` (family `mcphunt`, profile `mcphunt` v1, dialect `mcphunt.traces`, mapper `mcphunt.trace`, variant `v2.0.0`; registry `planned`) |
| Parts | `head` (only part; the four splits `main`, `mitigation`, `live_guard_defense`, `browser_replication` are per-execution facets, D-286 as built) |
| Wave | 6 (first examination; not in FA or E2; never imported) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: our prior reports (phase-10m part B census, map census, routing, D-323 calibration), the profile, the registry, `artefacts.toml`, DECISIONS (D-286..D-289, D-311, D-323), bug pass BF-27..BF-31, `tools/precheck/`, and desk research (`data/mcphunt/research.json`). Nothing here was computed from trace contents; the staged `meta/` aggregates were not read. |
| Method | [`../README.md`](../README.md) |

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Paper | arXiv [2604.27819](https://arxiv.org/abs/2604.27819v1) (Li, Sun, Wang, Zhang), **v1 only** (2026-04-30), CC BY 4.0. Covers main (3,615) and mitigation (2,706) = 6,321; the taint guard there is a post-hoc simulation | arXiv API, abs, HTML |
| Data record | HF `lihaonan0716/mcphunt-agent-traces` @ `c4c69322bf9e` (2026-07-30T16:43:28Z) = current HEAD = our pin. 32 files, 593,477,795 B, 15 LFS objects: all 15 LFS sha256/sizes equal the profile pins | HF tree and commits API |
| Release history | paper-time release `b361c58d` (2026-05-01): main + mitigation only. `f793a397` (2026-07-28) adds live_guard (387) and browser_replication (78) and rewrites every trace file. Pin `c4c69322` rewrites **9** trace documents again: main x5 and `gpt54_m0` (+0.32..1.17 MB each) **and also** `live_guard_defense` (+0.68 MB) and both `browser_replication` files (+54 KB, +58 KB) [corrected by fact-check; was "main x5 and gpt54_m0"]. Croissant v1.1.0 | HF commits, trees at 3 revisions |
| Code | [lihaonan0716/MCPHunt](https://github.com/lihaonan0716/MCPHunt) (MIT + dataset and responsible-use notices), HEAD `6b2f4e5` (2026-07-30); 0 issues, PRs, tags or releases. Envelope pipeline commits `ffd333b`, `4b85018`, `1b7e3c2` (2026-07-24..27); `1e188b8` not in public history | GitHub API |
| Harness | own OpenAI-compatible loop over 8 MCP servers; MAX_TURNS 30, temperature 0.0, max tokens 2048 (8192 thinking), 3 API retries, tool message truncated at 12,000 chars (result_full kept); labels by `labeling.compute_risk_labels`, `outcome = compute_outcome(artifact_verified, any_risk)` | `config.py`, `agent_loop.py`, `labeling.py` at HEAD |
| Known harness bugs | memory server: `mcp-server-memory` resolved to a PyPI placeholder before 2026-05-09 (`6b15fff`); Windows runtime fixes "found during trace collection" (`1e33199`); benign aggregate risk forced to False by code | commits |
| Scope | non-adversarial: canary (synthetic credential) propagation during benign tasks; no attacker. Canary-flagged executions withheld (D-289, RW-1/D-311) | DECISIONS |

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Files at the pin | 32 (593,477,795 B), 15 LFS | profile pin; HF tree |
| Selected trace documents | 20 (include globs `main/`, `mitigation/`, `live_guard_defense/`, `browser_replication/`) | profile `[import] include` |
| Not selected | 12 (`.gitattributes`, README, croissant, `crs_audit/` x3, `meta/` x5, `recall_evaluation/` x1) | `mcphunt.art.non_trace_members` (12) |
| Units = executions | **6,786** traces (`/traces/<i>`) | registry `readme_corpora.toml` 6786; census `/traces/total`; HF card |
| Paper population | 6,321 (main + mitigation); +465 post-paper | paper §6; HF card |
| Envelopes | 4 distinct (`schema_version`, `pipeline_git_commit`, `task_taxonomy_version`, `labeling_rules_version`, `traces`) | census |
| Elements > 16 MiB | 4 (in `main/deepseek_v4_flash`, `main/gpt_5_4`, `mitigation/gpt54_m0`, `mitigation/minimax_m3_rv1`; max 46,937,185 B) | census; `mcphunt.art.oversized_traces` |

| Document | Traces | Model | Env / condition | Source |
|---|---:|---|---|---|
| `main/{gpt_5_4, gpt_5_2, deepseek_v4_flash, gemini_3_1_pro_preview, MiniMax_M2_7}.json` | 723 each (3,615) | 5 models | 7 envs, mitigation none, defense none | paper §4.1; census |
| `mitigation/gpt54_m0..m3.json` | 384 / 381 / 381 / 384 (1,530) | gpt-5.4 | risky_v1-v3; none/generic/moderate/detailed | Table 19; census |
| `mitigation/deepseek_m0..m3_rv1.json` | 147 each (588) | deepseek-v4-flash | risky_v1 | Table 7; `ff36a09` |
| `mitigation/minimax_m0..m3_rv1.json` | 147 each (588) | MiniMax-M2.7 | risky_v1 | Table 7; `ff36a09` |
| `live_guard_defense/deepseek_v4_flash.json` | 387 | deepseek-v4-flash | risky_v1-v3, defense taint_tracking | HF card; `5ad11d1` |
| `browser_replication/deepseek_v4_flash_{baseline,defense}.json` | 39 + 39 | deepseek-v4-flash | browser_to_local, defense none / taint_tracking | HF card |

Census totals to reproduce: messages system 6,786, user 6,786, assistant 80,472, tool 129,175; tool calls = tool messages = events = 129,175; last finish reason stop 6,241 / tool_calls 488 / length 10 / error 47.

## 3. Expected arms

| Facet | Values | Expected missing / extra |
|---|---|---|
| Split (document dir) | main, mitigation, live_guard_defense, browser_replication | extra vs paper: live_guard, browser (465) |
| Model | gpt-5.4 2,253; gpt-5.2 723; deepseek-v4-flash 1,776; gemini-3.1-pro-preview 723; MiniMax-M2.7 1,311 | none |
| env_type (main, per model) | risky_v1 147, risky_v2 120, risky_v3 120, benign 147, hard_neg_v1 135, hard_neg_v2 27, hard_neg_v3 27 | none |
| risk_mechanism | 9 families + `benign_control` = 10; risky per model = 9 x 39 + 36 | none |
| mitigation_level | none **4,758**, generic 675, moderate 675, detailed 678 | census says none 5,466 (sum 7,494 != 6,786): H6 |
| defense | none 6,360, taint_tracking 426 (387 + 39) | none |
| GPT-5.4 mitigation cells (vs 387) | M0 -3 browser_to_local; M1 -3 browser_to_local, -3 git_history_leak; M2 -3 browser_to_local, -1 git_history_leak, -2 file_to_file; M3 -3 browser_to_local | as stated (Table 20 denominators) |
| Attack | none (non-adversarial) | n/a |

L1 strata (`l1_families.py` default for `mcphunt.traces`): (split, document) = 20 strata. L1-05 also tallies model x mitigation_level x defense x env_type x risk_mechanism.

## 4. Expected outcome rates (comparison targets)

Metric mapping (pinned harness code, paper §3.3): **propagation** = `outcome` in {`unsafe_success`, `unsafe_failure`} (equal to `labeling.any_risk`; the paper says Tier-2 never fires without Tier-1); **utility** = `outcome` in {`safe_success`, `unsafe_success`} (= `completion_checks.artifact_verified`; **not** `task_completed`, which the L1 hook also extracts); **policy-violating** = propagation among risky traces with `risk_mechanism != benign_control` and `labeling.completion_requires_secret` false (n = 288 per model); **CRS** = the same with `completion_requires_secret` true (n = 63). Counts below are derived from the paper's percentages and n; each is consistent to 0.1 pp.

**Main, risky pooled (v1-v3), n = 387 per model (Tables 6 and 15)**

| Model | Propagation | Utility | Policy-viol. (of 288) | CRS (of 63) |
|---|---:|---:|---:|---:|
| gpt-5.4 | 90 (23.3%) | 305 (78.8%) | 39 (13.5%) | 51 (81.0%) |
| gpt-5.2 | 78 (20.2%) | 330 (85.3%) | 33 (11.5%) | 45 (71.4%) |
| deepseek-v4-flash | 158 (40.8%) | 275 (71.1%) | 105 (36.5%) | 53 (84.1%) |
| gemini-3.1-pro-preview | 141 (36.4%) | 301 (77.8%) | 78 (27.1%) | 63 (100%) |
| MiniMax-M2.7 | 175 (45.2%) | 357 (92.2%) | 119 (41.3%) | 56 (88.9%) |

**GPT-5.4 main by environment (Tables 3, 14)**: risky_v1 28/147, risky_v2 32/120, risky_v3 30/120; benign 0/147 (utility 123); hard-neg pooled 22/189 (risk tasks 22/108, HN-specific 0/81). Quadrants safe_success / unsafe_success / safe_failure / unsafe_failure: risky 228/77/69/13, benign 123/0/24/0, hard-neg 128/19/39/3, all 479/96/132/16.

**Main risky, propagated of 39 per mechanism (Table 16; gpt-5.4 · gpt-5.2 · deepseek · gemini · minimax)**

| Mechanism | Counts | Mechanism | Counts |
|---|---|---|---|
| browser_to_local | 29 · 26 · 32 · 36 · 33 | sensitive_to_shell | 5 · 6 · 16 · 9 · 16 |
| forced_multi_hop | 18 · 13 · 26 · 25 · 23 | file_to_doc | 1 · 2 · 4 · 9 · 14 |
| file_to_file | 12 · 12 · 24 · 25 · 30 | config_to_script | 8 · 1 · 13 · 10 · 12 |
| db_to_artifact | 11 · 11 · 24 · 15 · 16 | indirect_exposure | 0 · 1 · 1 · 0 · 2 |
| git_history_leak | 6 · 6 · 18 · 12 · 29 | | |

Signal counts (Table 17, risky, traces with the signal; 5 models in the same order): data_flow 80/66/152/130/167; cross_boundary_flow 51/41/71/83/86; sensitive_schema_flow 17/12/54/29/29; opaque_transfer 9/12/3/11/7; secret_in_executable 5/0/10/5/11; secret_in_command 6/2/5/5/1; partial_leak 0/0/6/0/5; semantic_leak 2/0/6/0/6; external_after_sensitive 2/1/3/1/1.

**Mitigation, GPT-5.4 risky_v1-v3 (Tables 19, 20)**: M0 88/384 (22.9%), utility 305, policy-viol. 13.9%; M1 64/381 (16.8%), 302, 8.1%; M2 18/381 (4.7%), 301, 1.4%; M3 9/384 (2.3%), 309, 0.3%. Per mechanism (None, L1, L2, L3): browser_to_local 29/36, 14/36, 7/36, 2/36; forced_multi_hop 19/39, 11/39, 1/39, 0/39; file_to_file 10/39, 11/39, 8/37, 6/39; db_to_artifact 8/39, 10/39, 2/39, 1/39; git_history_leak 6/39, 5/36, 0/38, 0/39; sensitive_to_shell 6/39, 3/39, 0, 0; file_to_doc 1/39, 1/39, 0, 0; config_to_script 9/39, 9/39, 0, 0; indirect_exposure 0 throughout.

**Mitigation, risky_v1 risk tasks only (about 108 per cell; Table 7)**: gpt-5.4 24.3 / 19.6 / 4.7 / 1.9%; deepseek-v4-flash 47.2 / 47.2 / 25.0 / 12.0%; MiniMax-M2.7 50.9 / 48.1 / 30.6 / 26.9% (M0..M3). Risk tasks = risky_v1 traces minus 12 benign_control and 27 hard-negative-specific tasks.

**No paper number:** live_guard_defense and browser_replication (the paper's guard figures, 85-96% blocked, are a simulation on the main traces). **Costs (App. K, main):** 59.6 s/trace, which App. K derives from 59.8 h of total wall-clock over 3,615 traces, so it is not necessarily the mean of the logged `duration_s` [clarified by fact-check]; 218.2M prompt + 9.5M completion tokens; 12.1 turns per trace; GPT-5.4 10.0 h and 29.9M tokens.

## 5. Known quirks (expected-known)

| Id | Expected | Source |
|---|---|---|
| `mcphunt.art.non_trace_members` | 12 files not selected | artefacts.toml |
| `mcphunt.art.oversized_traces` | 4 traces > 16 MiB (D-288: profile 64 MiB, RB-2) | artefacts.toml, census |
| `mcphunt.art.canary_exposure` / `mcphunt.canary_flagged` | 4,595 traces; events in_result 14,143, in_args 2,172 (15,953 flagged events) | artefacts.toml, census, profile quirk |
| `mcphunt.art.run_not_ok` / `incomplete_run` | 545 (tool_calls 488 + length 10 + error 47) | artefacts.toml, map census |
| `mcphunt.art.args_unparsed` | 2,392 events in 429 traces | artefacts.toml, map census |
| `mcphunt.art.result_truncated_in_message` | 669 events (668 + 1 in the unmappable trace), 381 traces | artefacts.toml, map census |
| `mcphunt.art.result_differs` | 410 events in 42 traces | artefacts.toml, map census |
| `mcphunt.art.unknown_server` | 11 events in 3 traces | artefacts.toml, map census |
| `mcphunt.art.turn_misaligned` | 0 | artefacts.toml |
| `mcphunt.art.event_times_ambiguous` | all 6,786 (epoch floats; start/end not recorded) | artefacts.toml |
| `mcphunt.guard_rewrite` | 245 events with `sanitized_args` | profile quirk, census |
| turn_log vs assistant | turn_log = assistant + 1 in 6,105 traces (`final_message`), equal in 681 | census |
| server package names | memory `mcp-server-memory` 6,321, `@modelcontextprotocol/server-memory` 465 | profile comment |
| RB-3 | `minimax_m3_rv1` `/traces/106` (46.9 MB) unmappable in aer/0.1; three documents seal as one degenerate AER each in the product path until carving | map census, D-323 calibration |
| BF-27..BF-31 | latent mapper defects, fixes held as regen items 38-41 (`bugpass-regen`); none triggers on the pin per the bug pass | bugpass findings |
| D-289 / RW-1 | canary-flagged executions withheld; 2,191 unflagged releasable | DECISIONS, profile |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | section 2 per document; 12 not selected; 20 trace documents via `l1_scan.py` jsonstream path. The scan must raise the element limit to 64 MiB in its own process (as the census did) or report the 4 documents refused |
| L1-02 strict parse | yes | census: 0 findings at 256 MiB; expect 0 duplicate keys, NaN, lone surrogates, BOM, trailing data |
| L1-03 encodings | yes | expect model and tool text only; watch U+FFFD / mojibake from Windows git-bash output in the 465 later traces (H15) |
| L1-04 duplicates | yes | 0 byte-identical documents; 0 identical traces across splits (census); `trace_id` is a cell id shared across models, not a duplicate key |
| L1-05 arm coverage | yes | section 3, plus the whole-population outcome tally against section 4 (H8-H12) |
| L1-06 secrets / account paths | yes, **high priority** | canaries are synthetic but credential-shaped (1,995 traces with a recognisable shape); sanitizer placeholders expected; any non-canary provider key or real account path is reported at once (H13, H14) |
| L1-07 timestamps | yes | event epoch floats non-decreasing in 6,786 (census); `collection_timestamp` ISO `Z`; ranges H16 |
| L1-08 degenerate | yes | 0 zero-message traces; 545 abnormal ends; 47 error ends (H17) |
| L2 import, validate, recompute, determinism, chain verify | **no (blocked)** | `tools/precheck/l2_import.py` BLOCKED: RB-1 (reader not `multi_execution`), RB-2 (64 MiB limit not in `[import] limits`), RB-3 (no carving), no offline LFS pin vouching. Latest full-mapping evidence: phase-10m map census (6,785/6,786, 0 AER/SEM/PROV findings). Open question to the orchestrator |
| L2 A2/A3, evidence classes, degenerate rates, identity, redaction | no (blocked) | as above; expected values when unblocked: section 5 issue codes only, 0 degenerate except RB-3 documents |
| L2 withholding | no (blocked) | D-289 rule tested in unit tests only; expected 4,595 withheld when imported |
| L2 outcome sanity | no | replaced by the whole-population L1 tally (exact counts, section 4) |
| Delta since E2 | no | not in FA/E2 |

## 7. Hypotheses (falsifiable)

| # | Expectation | Refuted if |
|---|---|---|
| H1 | Section 2 counts exactly: 32/20/12 files; 6,786 traces; per-document counts as tabled | any count differs by >= 1 |
| H2 | 4 envelopes; `pipeline_git_commit` in {ffd333b, 4b85018, 1b7e3c2, 1e188b8}; the 5 main documents and `gpt54_m0` (rewritten in the pin commit; the pin commit also rewrote `live_guard_defense` and both `browser_replication` files [fact-check]) share one envelope commit | another value, or main documents with differing commits |
| H3 | Models per document as section 2; 0 other model strings; totals 2,253/723/1,776/723/1,311 | any differs |
| H4 | Main env_type per model 147/120/120/147/135/27/27; risky = 9 mechanisms x 39 + 36 benign_control; risk_mechanism has exactly 10 values | any cell differs |
| H5 | GPT-5.4 mitigation deficits exactly as section 3; deepseek/minimax mitigation all `risky_v1`; live_guard 147/120/120 risky; browser 39 + 39 all `browser_to_local` | any differs |
| H6 | mitigation_level none 4,758 / generic 675 / moderate 675 / detailed 678; defense none 6,360 / taint_tracking 426 | other values (if the recount equals the census's 5,466, the source has a mislabelled level) |
| H7 | memory package `@modelcontextprotocol/server-memory` in exactly the 465 live_guard + browser traces, `mcp-server-memory` in the other 6,321 | any other split |
| H8 | Main risky tallies reproduce Tables 6/15 (propagation, utility, policy-viol., CRS; 20 cells) | any cell off by > 1 trace (then labels were recomputed after the paper: documentation-mismatch) |
| H9 | GPT-5.4 Tables 3 and 14 (8 env rows, 16 quadrant cells) and Table 16 (45 mechanism x model cells) reproduce | any cell off by > 1 |
| H10 | Mitigation Table 19 (4 levels x 3 metrics), Table 20 (36 cells) and Table 7 (12 cells, within 1 trace of each %) reproduce | any cell off by > 1 trace |
| H11 | Table 17 signal counts reproduce from `labeling.risk_signals` (45 cells) | any cell off by > 1 |
| H12 | Benign: 0 traces with `any_risk` true or `outcome` unsafe_* in 735 benign traces (forced by code); `outcome` equals `compute_outcome(artifact_verified, any_risk)` in 6,786/6,786 | any benign unsafe trace, or any outcome inconsistent with its two fields |
| H13 | Memory server functional? In the 6,321 earlier traces, memory-server events are absent or all errors; in the 465 later traces >= 1 successful memory event | memory events succeed in the 6,321 (then the placeholder commit does not describe the collection) |
| H14 | Account paths: 0 `/Users/<x>/`, 0 Administrator-anchored Windows paths, 0 collector username; sanitizer placeholders (`/home/user/`, `/mcphunt/`, `<HOME>`, `MCPHUNT-HOST`, `<redacted>`, `<internal-gateway>`) present and classified as placeholders | any real account path (report at once) |
| H15 | Secrets: every credential-shaped string belongs to the canary families of the census (Stripe-, AWS-, Slack-, GitHub-like, private-key header, password/secret assignments); 0 provider API keys (Anthropic/OpenAI/Google/HF shapes) or bearer tokens from environment dumps | >= 1 such string (security finding, report at once) |
| H16 | `collection_timestamp`: main and mitigation <= 2026-04-30T13:01Z; live_guard and browser >= 2026-05-09; all `Z`, format `YYYY-MM-DDTHH:MM:SSZ`; first event >= collection_timestamp - duration_s - 5 s and last event <= collection_timestamp + 5 s in >= 99% of traces | any main/mitigation trace after the paper, any later-arm trace before 2026-05-09, or the event window fails in > 1% |
| H17 | 0 empty or zero-message traces; 488 traces end on `tool_calls` with 30 turns (`truncated` true), 10 on `length`, 47 on `error`; mean `duration_s` over main 59.6 s (+-1 s; the paper's figure is wall-clock/trace, so a miss here alone is weak evidence [fact-check]); main prompt + completion tokens 227.8M (+-1%); mean turns 12.1 (+-0.2) | any threshold missed |
| H18 | `measurement.generation_temperature` 0.0 in all 6,786; max tokens 2048 or 8192 | any other value |
| H19 | Duplicates: 0 byte-identical documents; identical message-list fingerprints across documents <= 1% of traces (in particular `gpt54_m0` vs `main/gpt_5_4` risky, and browser baseline vs main deepseek browser_to_local: separate runs) | above threshold |
| H20 | Encodings: U+FFFD or mojibake in <= 1% of the 6,321 earlier traces; any concentration in the 465 Windows-collected traces is reported as a source property | above threshold in the earlier traces |

## 8. Discrepancy leads carried to the dossier

Every trace document was rewritten after the paper, nine of them twice (sanitization, "paired provenance"; corrected by fact-check from "two"), and the
envelope commits post-date the paper. One envelope commit (`1e188b8`) is not public. 465 traces (live_guard,
browser_replication) are not in the paper, which only simulated a guard. The memory server was a placeholder package
before 2026-05-09, so it may not have run for the 6,321 paper traces. Benign 0% is forced by code, not measured. The
mitigation count was once given as 2,885 (corrected to 2,706). GPT-5.4 mitigation lacks 3-6 cells per level. Our census's
mitigation_level split sums to 7,494. The later arms were collected on Windows through a private gateway, with
environment dumps that a sanitizer only partly covers. The models are requested names only. The CRS kappa was
retracted and replaced (0.89 to 0.71; labels unchanged). The Croissant collection timeframe (Q1-Q2) may exclude the July
arms. One 46.9 MB trace. Our profile records pin date 2026-10-12, but the revision's commit date is 2026-07-30 (S3).

## 9. Fact-check (2026-10-14, adversarial, desk only)

Re-opened the sources; no raw data read, no new expectation derived from data.

| Checked | Verdict |
|---|---|
| Paper identity and version: arXiv 2604.27819 v1 only (2026-04-30T13:01Z, cs.AI); 6,321 = 3,615 + 2,706; guard is a post-hoc simulation (85-96%) ([API](https://export.arxiv.org/api/query?id_list=2604.27819), [HTML](https://arxiv.org/html/2604.27819v1)) | confirmed |
| Section 4 numbers against Tables 3, 4, 5, 6, 7, 14, 15, 16, 17, 19, 20 (right table, arm, metric). Derived counts recomputed from % x n: all unique at 0.1 pp; Table 16 columns sum to the Table 6 propagation counts; Table 20 numerators sum to 88/64/18/9, and its denominators + 36 benign_control give 384/381/381/384 | confirmed |
| App. K: 218.2M + 9.5M tokens, 12.1 turns, GPT-5.4 10.0 h / 29.9M (main) | confirmed; **59.6 s is 59.8 h wall-clock / 3,615, not stated as mean `duration_s`** (wording in section 4 and H17 clarified) |
| HF pin `c4c69322` = HEAD, 32 files / 593,477,795 B / 15 LFS; all 15 LFS oid+size equal the profile pins ([tree](https://huggingface.co/api/datasets/lihaonan0716/mcphunt-agent-traces/tree/c4c69322bf9ed7690f5265577365709dad5dd454?recursive=true)) | confirmed |
| Release history: `b361c58d` 22 files (main + mitigation); `f793a397` changed all 20 trace documents | confirmed |
| "Pin rewrites main x5 and `gpt54_m0`" | **corrected**: the pin commit rewrote 9 trace documents (also `live_guard_defense` +0.68 MB and both `browser_replication` files); sections 1, 7 (H2 note) and 8 updated |
| Licence: card and Croissant CC BY 4.0; LICENSE (unchanged since `4362d6f`) MIT + dataset notice + Responsible Use Notice ([LICENSE](https://github.com/lihaonan0716/MCPHunt/blob/main/LICENSE)) | confirmed |
| Commits `6b15fff` (placeholder memory package), `1e33199` (Windows fixes during collection), `76884ee` (benign 0% policy-forced by `_is_benign_env`), `ff36a09` (2,885 to 2,706), `fe1bfcd` (0.89 retracted, audit 0.71, labels unchanged), `5ad11d1` (6,786, v1.1.0); `1e188b8` returns 422 | confirmed |
| `1b7e3c2` "labeling refactor" | **clarified** (research.json): it adds the actual-sink metric and an `is_network_command` helper and says no reported number moves |
| Harness constants at `6b2f4e5` and benign forcing present since `4362d6f` | confirmed |
| Census / artefacts.toml / registry figures quoted (6,786; mitigation_level 5,466, sum 7,494; finish reasons; canary event sums; 545, 2,392, 669, 410, 245; 1,977 traces in the 4 oversized documents) | confirmed against our reports |
| Benign "no canary markers" (paper §3.1) vs README `sk_test_*` registered canaries | confirmed as a documentation discrepancy |

Notes for the examiner (not new expectations): `configs/api_keys.yaml.example` names gpt-5.4 with a third-party OpenAI-compatible base URL, which supports the requested-names-only lead. H16's 2026-05-09 bound is the date of the Windows fix, whose message says the issues were found during collection, so earlier Windows traces are possible. The logged `generation_max_tokens` at HEAD code is always 2048. The HF bibtex says cs.CR, while arXiv lists cs.AI. Our census's shape split (1,995 + 2,601 = 4,596) is one more than its 4,595 flagged traces.
