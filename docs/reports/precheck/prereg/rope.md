# Pre-registration: `rope`

| | |
|---|---|
| Corpus | `rope` (family `agentdojo`, profile `rope@2`, rules `aer 1 / agentdojo 2 / autodojo 1 / rope 2`, SEM `agentdojo.suites@2`) |
| Parts | `rope` · `head`: 10,791 TraceLogger logs under `runs/` at `xhOwenMa/ROPE@64495e16e640d687e06e6b1b6cee6dccc5b9b7cb` (git); includes `autodojo` · `rope-slice` (`via = "rope"`, profile `autodojo-via-rope@1`): the 2,847 `runs/<model>/<suite>/user_task_*/autodojo/*.json` logs |
| Code commit | `065b0d36` (branch `precheck-corpora`) or later |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Wave 1, delta corpus (imported in full at `afe7038`, examined in E2 without network); this pre-check examines the **delta since E2** |
| Desk research | `../data/rope/research.json` (all URLs there) |

Sources: **P** = `src/agentprov/adapters/agentdojo/profiles/rope.profile.toml` (and `autodojo-via-rope.profile.toml`); **I** =
`docs/reports/rope/import-cli-rope.json` and `docs/reports/rope/README.md`; **Q8** = `docs/reports/rope/rope-q8.json`; **S**/**V** =
investigation `sources/rope.md` / `verify/rope.md`; **SA**/**VA** = `sources/autodojo.md` / `verify/autodojo.md`; **G** = GitHub API
2026-10-14; **A** = `src/agentprov/adapters/agentdojo/artefacts.toml`; **E2** / **FA** = examination 2 / first analysis; **RB** =
`docs/reports/analysis/regen-batch.md`; **RP** / **AP** = ROPE paper arXiv:2608.27496v1 / AutoDojo paper arXiv:2606.15057v3.

## 1. Desk research summary

- **Paper:** ROPE arXiv:2608.27496 has **v1 only** (2026-08-27), so no result table changed. AutoDojo arXiv:2606.15057 latest is v3
  (2026-09-28); titles differ by version; cite v3. AgentLAB arXiv:2602.16901 v1 only.
- **Repository unchanged since the pin** (G): `main` = `64495e16` (only branch), 3 commits, last push 2026-08-31; 0 tags, releases,
  issues, PRs, forks. Tree `c4df12c3`, 24,909 blobs, 265,463,047 B; `runs/` `6a8c86f2` 10,805 blobs; equal to P's pin.
- **No data record** (HF, Zenodo, HF paper repos: none). The git tree is the record.
- **Harness:** AgentDojo 0.1.35 fork at unreleased code states (vendored AutoDojo ≈ `bf2e4cb3`..`abbcbd8d`; AgentDyn-style system
  prompt; tags not producible by the shipped `run_eval.py`). Relevant upstream bugs: AgentDojo #168/#189 (slack IT5 scores proposed
  calls; = ROPE's correction), #218 (utility counterpart), #181 (banking IT0/1/3 subject check dead), #188 (slack utility KeyError when
  `post_webpage` is blocked), #214 (`\uXXXX` in tool results), #212/#177 (`--max-workers` argument order); AgentDyn #8 (github
  user_task_5/7/8/11 can never reach utility True at `5353cf76`), #6 (github IT1 false positive, fixed before `5353cf76`).
- **Licence:** MIT (ROPE LICENSE, Ma, Xiao, Yeoh, Zhang, Vorobeychik 2026), no data licence, no use clause; papers CC BY 4.0.
- **Two published metrics on the same logs:** RP uses effect-corrected `security` (3 injection tasks re-scored) and the
  **unweighted mean of three suites**; AP uses **raw** `security`, **micro-averaged**. Long-horizon (RP Table 3) pools per matched
  cell (`runs/lh_cells.json`).

## 2. Expected counts

| Quantity | Expected | Source |
|---|---:|---|
| Files / bytes at the pin | 24,909 / 265,463,047 | P; G; I |
| Selected logs (`runs/**/*.json` minus `runs/lh_cells.json`) / bytes | 10,791 / 175,263,358 | P; G; I `candidates` |
| of which AutoDojo slice / bytes | 2,847 / 48,275,981 | G; VA #5; Q8 |
| Context artefacts (verified, not mapped) | 35 (`lh_cells.json`, 13 `runs/*.py`, 18 `src/rope/scopes/**`, 3 routed `injections.json`) | P; I (10,826 verified = 10,791 + 35); G |
| Selection exclusions | 14,066 = `select.owned_elsewhere` 13,765 (`agentlab/**`, owner `ext:agentlab`; 13,525 of them `agentlab/res/**`) + `select.not_execution_artefact` 301 | I; D-33 (now `selection_excluded`, not candidates) |
| Archive members | 0 | P |
| Units: `agent_execution` / `outcome_only` | 10,789 / 2 | I |
| Variants `v1.k14` / `v1.k14.incomplete` | 10,789 / 2 | I; P |
| Executions (registry) | 10,791 (`rope`·`head`); slice 2,847 counted under `rope` | `tools/readme_corpora.toml` |
| Messages / assistant / tool calls / null-id calls / tool results | 187,255 / 83,068 / 83,362 / 8,707 / 82,609 | S §4.1; V §6 |
| Guard denials (`None` / query variant) / other tool errors | 12,657 (9,424 / 3,233) / 2,524 | P quirk; V §6 |
| `attack_type` II / autodojo / long_horizon / null | 6,436 / 2,847 / 760 / 748 | S §3.3; V §6 |
| `benchmark_version` v1.2.2 / v1.2.1 | 10,031 / 760 | S §3.3 |
| `agentdojo_package_version` `unknown` | 2,268 (all `qwen3-235b`) | P quirk |
| Null-final logs / unexecuted trailing calls (logs, calls) | 322 / 675, 753 | P quirks |
| Clean logs (benign `security` constant) | 748 | P; A |
| Recorded `security` true: II / autodojo / long_horizon | 444 / 88 / 0 of 758 | S §3.6; V §6 |
| AutoDojo payload slots linked (exact / wrapped) | 5,775 (5,772 / 3) | P; Q8; VA #16 |
| AER records at E2 | 505,333 (expected after item 5: +1 activity per attacked execution, see §6) | I |

## 3. Expected arms (L1-05)

Facets: tree/model × attack dir × suite (defence is ROPE in every arm; the ablation/router trees vary the ROPE policy or router).
Counts from the pin listing (G), equal to S §4.2.

| Tree / model | `none` | `important_instructions` | `autodojo` | `agentlab_longhorizon` (v1.2.1) | Total |
|---|---|---|---|---|---:|
| `gpt-4o-mini` | 117 (16/21/20/20/20/20) | 949 (144/105/140/180/180/200) | 949 (same) | 253 (144/85/24) | 2,268 |
| `gpt-4o` | 117 | 949 | — | — | 1,066 |
| `gemini-2.5-flash` | 117 | 949 | 949 | 254 (144/85/25) | 2,269 |
| `qwen3-235b` | 117 | 949 | 949 | 253 (144/85/24) | 2,268 |
| `ablation/always-fully-specified`, `ablation/always-action-open` | 60 each (AgentDyn 20/20/20) | 560 each (180/180/200) | — | — | 1,240 |
| `router/gemini-3-flash`, `router/gpt-oss-20b` | 60 each | 560 each | — | — | 1,240 |
| `router/gemini-3-flash-clamp`, `router/gpt-oss-20b-clamp` | 20 each (dailylife) | 200 each (dailylife) | — | — | 440 |

Suite order banking/slack/travel/github/shopping/dailylife. Expected **missing** cells: travel long-horizon `user_task_0` ×
`injection_task_2` for `gpt-4o-mini` and `qwen3-235b` (V §6); every undefended and baseline-defence arm (RP Tables 2, 3, 11-14:
11 baselines × 4 models); `gpt-4o` autodojo and long-horizon; ablation/router on AgentDojo suites; clamp arms for github/shopping
and any Opus clamp arm (RP Table 5 reports them, see H-07); AP's ROPE rows for GPT-5.4-mini, DeepSeek-v4-Flash, Claude-Haiku-4.5.
Expected **extra** cells: `gpt-4o` AgentDojo-suite logs (389 attacked + 57 clean; in no reported table, `runs/_scope.py`); the 2
aborted long-horizon logs (travel `user_task_2` × `injection_task_2`, gpt-4o-mini and qwen3-235b). Path components equal in-file
fields (`path_must_agree`) in 10,791 / 10,791 (E2 import: 0 `path_field_mismatch`).

## 4. Expected outcome rates

**Mapping.** `security == true` = injection task succeeded (AgentDojo); on clean logs it is the runner constant
(`agentdojo.benign_security_constant@1`, excluded from ASR). AER: `utility`/`security` judgements, origin
`agentdojo.checker_outcome` (via its `_unverified` twin, class I, after item 3); the corrected value is a separate `recomputed`
judgement that `revises` the recorded one (`rope.security_correction@1`, D) for slack IT5, dailylife IT7, github IT1 only.
CU = utility on `none`; UA = utility on attacked; ASR (RP) = corrected security on attacked, unweighted mean of a benchmark's three
suites; ASR (AP) = raw security, micro-averaged. Per-suite counts below are **derived** from the published percentages and n (exact
where the percentage determines a unique integer; "derived†" = split inferred from RP Table 6 + Table 13).

| Model | Suite (n clean / attacked) | CU | II ASR raw → corrected | AutoDojo ASR raw → corrected | Source |
|---|---|---|---|---|---|
| gpt-4o-mini | banking (16/144) | 8/16 = 50.0 | 0 → 0 | 0 → 0 | AP T6; RP T13, T14 |
| | slack (21/105) | 14/21 = 66.7 | 16 (15.2) → 5 (4.8) | 12 (11.4) → 5 (4.8) | AP T6; RP T13, T14; VA #15 |
| | travel (20/140) | 12/20 = 60.0 | 9 (6.4) → 9 | 5 (3.6) → 5 | AP T6; RP T13, T14 |
| | github (20/180) | 12/20 = 60.0 | 1 (0.6) → 0 | 0 → 0 | AP T9; RP T2 |
| | shopping (20/180) | 7/20 = 35.0 | 8 (4.4) → 8 | 8 (4.4) → 8 | AP T9; RP T2 |
| | dailylife (20/200) | 7/20 = 35.0 | 3 (1.5) → 2 (1.0) | 8 (4.0) → 1 (0.5) | AP T9; RP T2 |
| gemini-2.5-flash | banking / slack / travel | 8/16, 18/21, 8/20 | 0, 7 (6.7), 6 (4.3); unchanged | 0, 6 (5.7), 9 (6.4); unchanged | AP T6; RP T13, T14 |
| | github / shopping / dailylife | 4/20, 3/20, 8/20 | 0, 7 (3.9), 2 (1.0); unchanged | 0, 4 (2.2), 0 | AP T9; RP T2 |
| qwen3-235b | AgentDojo macro | CU 67.9 | corrected 0 / 7 / 10 (derived†); mean 4.6 | raw 0 / 8 / 13 → 0 / 6 / 13; mean 5.0 | RP T13, T14, T6; VA #15 |
| | AgentDyn macro | CU 53.3 (32/60) | corrected 0 / 13 (7.2) / 1 (0.5); mean 2.6 | raw 1 / 13 / 1 → 0 / 13 / 1 | RP T2, T11; VA #15 |
| gpt-4o | AgentDyn macro | CU 53.3 (32/60) | corrected 0 / 11 / 2 (derived from T6); mean 2.4 | — | RP T11, T6 |

Aggregates to compare at pooled levels (macro, RP): UA II AgentDyn 36.6 / 45.0 / 20.9 / 46.3 (gpt-4o-mini / gpt-4o / gemini /
qwen), UA adaptive AgentDyn 34.3 / — / 12.5 / 39.1; AgentDojo UA II 45.6 / 51.7 / 57.6 (gpt-4o-mini / gemini / qwen), adaptive
50.2 / 52.2 / 58.5. AP micro (raw): AgentDojo II 6.4 (UA 45.5) and AutoDojo 4.4 (49.6) for gpt-4o-mini, 3.3 (51.7) and 3.9 (50.6)
for gemini; AgentDyn 2.1 (36.1) / 2.9 (33.6) and 1.6 (20.9) / 0.7 (12.3). Totals: II corrected successes in RP's paper cells = **90**
(travel IT6 23, slack IT1 19, travel IT5 2, shopping IT2+IT5 39, dailylife IT6 7; = 24 + 22 + 31 + 13 by model); AutoDojo arm raw
88 → corrected 71 (33→19, 19→19, 36→33). Long-horizon: recorded `security` true 0 in every arm (RP T3: 0.0 everywhere); LH CU
25/38, 26/38, 27/38 (gpt-4o-mini, gemini, qwen; pooled over 38 user tasks). Ablation (RP T4, gpt-4o-mini, github/shopping/dailylife):
always-fully-specified CU 40.0/20.0/20.0, ASR 0.0/5.0/0.5; always-action-open CU 65.0/30.0/35.0, ASR 35.0/28.9/68.0. Router (RP T5,
unclamped CU/ASR): Gemini-3-Flash github 55.0/1.7, shopping 35.0/5.0, dailylife 30.0/6.0 (+clamp 0.0); gpt-oss-20b 40.0/1.1,
40.0/7.2, 35.0/0.5 (+clamp 0.5).

**L2 use.** The arm key has 103 strata (75 main, 12 ablation, 12 router, 4 clamp), so the 300-unit cap gives about 3 units per
stratum: no single (model, attack, suite) arm reaches 20 sampled executions. Per (model, attack, benchmark) the sample is about 9:
Wilson intervals only, no verdict. The README threshold (>15 pp with n ≥ 20, or a binomial 95 % interval excluding the expected
rate by >5 pp) is applied to pooled arms (attack × benchmark over models; and the AutoDojo slice per benchmark), with the expected
rate computed as the sample-weighted mean of the per-(model, suite) rates above (raw for the recorded judgement, corrected for the
`recomputed` one). Any whole-corpus recount of the recorded outcome fields against the exact integers above is a stronger test and
is welcome as an L1 extension.

## 5. Known quirks (already declared)

| Id | Expected | Where |
|---|---|---|
| `agentdojo.rope_guard_denial` / `rope.art.guard_denial` | 12,657 denials (9,424 / 3,233) | P; A |
| `agentdojo.rope_release_tree` | ablation 1,240, router 1,680 (of which clamp 440; **corrected** in fact-check: the 440 are inside the 1,680, total 2,920) | P |
| `agentdojo.silent_rerun_last_pass_only` / `agentdojo.art.silent_rerun` | 322 null-final | P; A |
| `agentdojo.pipeline_name_not_identity` / `rope.art.pipeline_tag_not_identity` | 949 (`identity_conflict`, qwen3-235b autodojo) | P; A |
| `agentdojo.empty_messages_without_outcome`, `agentdojo.incomplete_run` / `agentdojo.art.empty_log` | 2 | P; A |
| `agentdojo.unexecuted_trailing_calls` / `agentdojo.art.max_iters_pending` | 675 logs, 753 calls | P; A |
| `agentdojo.provider_call_id_anomalies` / `agentdojo.art.provider_ids` | 8,707 null ids in 1,496 logs | P; A |
| `agentdojo.benign_security_constant` | 748 | P; A |
| `agentdojo.args_mutated_in_place` | 10,520 | P |
| `agentdojo.package_version_not_code_identity` | 2,268 | P |
| `agentdojo.placeholder_args_never_injection_evidence` | 83,362 present and null | P |
| `agentdojo.benchmark_version_label_not_suite_version` | github/shopping/dailylife logs | P |
| `agentdojo.rope_effect_correction` / `rope.art.security_correction` | 678 recomputed (198 / 260 / 220); recorded true 32 / 39 / 5 → 0 / 22 / 0; autodojo 88 → 71 | P; A; Q8 |
| `agentdojo.autodojo_payload_cache_link` | 5,775 slots; ambiguity-set files 1,824 / 228 / 28 / 30 / 2 / 315 / 420 (sizes 1/8/16/20/38/40/50) | P; Q8 |
| `rope.art.autodojo_payload_escaped` | A says 1,166 and "unescape not applied"; E2 census 1,235 executions / 1,840 markers; B1 now implemented (see H-15) | A; E2 §4.2; RB item 1 |
| `rope.art.security_without_exposure` | A says 22; under `suites@2` 5 (see H-13) | A; RB items 1, 4 |
| `agentdojo.art.validity_defects` (vacuous utility) | 73 (banking ut8 28, ut10 28, ut5 17) | A; FA §8 row 9 |
| `agentdojo.art.text_tool_call` | 11 executions (heuristic) | A |
| Census findings | 52 identical post-prompt groups / 396 files (V; FA counts 53); 0 byte-identical files; 9 logs content-identical to AgentDyn baseline logs (ids ignored), 0 with ids; 33 Gemini empty final turns (28 `[]`, 5 `None`); 123 long-horizon logs per model (gpt-4o-mini, qwen) with an unresolved `<agent_model_name>` token | S §4; V §6-§8 |
| E2 string screens (AER level) | variation selectors 12, double-escaped arguments 12 executions (N2), JSON-like unparsed 74 (72 AutoDojo payloads), list-as-string args 13, absolute-path-like 27 and secret-shaped 233 (benchmark fixtures), machine paths 0; raw: 0 lone surrogates, 3 objects with paired surrogate escapes | E2 §3.1, §4.1 |

## 6. Expected movement since E2 (stored `rope-p10.partial` at `afe7038` → scratch import at `065b0d36`)

| Change | Expected for ROPE |
|---|---|
| D-31 bumps (item 30) | every AER header: `rules` aer 1 / agentdojo 2 / autodojo 1 / rope 2, profile `rope` v2 (new sha); SEM `agentdojo.suites@2` (was @1) |
| Item 3 (B6/C6 twins) | 15 D rules cited through `_unverified` twins (class I), incl. `null_final_implies_three_passes` 322, `rope.denial_query_echo_variant` 6,197, `rope.tree_arm_config` 2,920; `system_prompt_variant_digest`, `rope.security_correction` stay D |
| Items 9/11 (B2, D-372) | completeness: `known_incomplete` 322 → `unverifiable`; `verified_complete` 2 → 0 (the 2 empty logs: `known_incomplete` via `agentdojo.incomplete_run@1`, class D, no twin; else `unverifiable`); expected 10,789 `unverifiable` + 2 `known_incomplete` |
| Item 1 (B1 + D-86) | AutoDojo-linked markers: 3,344 markers in 1,877 executions become `present` (absent → present 2,739, ambiguous → present 605); AutoDojo executions with ≥1 `present` marker 1,118 → 2,528 of 2,847 (39.3 % → 88.8 %); 10 long-horizon `ambiguous` markers unchanged; outcome and marker annotations cite twins (I) in all 10,791 |
| Item 4 (C1) | `agentdojo.success_without_visible_payload` on 5 executions in the whole corpus (II: github `user_task_7` ×2, `user_task_9`, `user_task_11`, shopping `user_task_10`); 0 in the AutoDojo arm (its 17 slack IT1 cases become visible through B1) |
| Item 5 (C2, D-370) | one `agentdojo:load_environment` activity per attacked execution (10,043; 22,307 fixture inputs) under the twin (I) → `used(ac0, fx)` and association in an inference bundle; 0 on the 748 clean logs; AER records +10,043 (505,333 → 515,376) if nothing else moves |
| Item 6 (C3) | `agentdojo.partial_payload` on ≈ 7.7 % of executions (308 of a 4,000 sample, 918 annotations); marker status stays `absent` |
| Item 8 (F-10, `yaml_norm@2`) | 0 markers changed (0 of 69,995 sampled) |
| U6-c (D-373) | `unk /params = not_recorded` on every model call (83,068); one `apv:Gap` per model call in PROV; none on the 2 empty logs |
| Item 10 | tier 4 gains `pv.constraints.ordering`, `derivation_parts`, `unique_start`, `cycles`: all pass |
| Items 7, 14, 21-23, 24, 32; F-03 (`8909f4bc`) | 0 ROPE records change (code digests only); the linear-time wrapper match still finds the 3 wrapped slots |
| D-33 | manifest: `selection_excluded` 14,066, `candidates = executions + not_imported` |
| D-481 | registry coverage phrase counts 6 sources (the slice is not a distinct source) |
| Not expected to move | seal issue counts (accounting_unverifiable 10,789, earlier_attempts_unobservable 10,789, unexecuted_tool_call 675, identity_conflict 949, retry_passes_inferred 322, no_execution_observed 2, no_outcome_recorded 2); quirk observed counts; SEM fail-closed on AgentDyn suites (still @2, see H-16) |

## 7. Check map

| Check | Applies | How / note |
|---|---|---|
| L1-01 counts | yes | §2: selected 10,791, context 35, exclusions 14,066, per-arm §3; slice 2,847 |
| L1-02 strict parse | yes | expect 0 failures of every class (E2 raw: 0 lone surrogates; 3 paired-escape objects) |
| L1-03 encodings/escaping | yes | expect no U+2028/2029/0085, bidi, tag, C0/C1 in logs; literal-escape residues present by design (YAML-escaped AutoDojo payloads ≈ 3,824 wholly escaped; Python-repr tool outputs; #214 `\uXXXX`) |
| L1-04 duplicates | yes | 0 byte-identical; 52 (or 53) identical-trajectory groups / 396 files; cross-part: 0 with `agentdyn` · `a` byte-identical, 9 content-identical (ids ignored); `agentlab/res/**` is AgentLAB's (excluded) |
| L1-05 arm coverage | yes | §3 grid; missing/extra cells as listed |
| L1-06 secrets/paths | yes | counts and pointers only; expected secret-shaped strings = benchmark fixtures (fake keys in github/dailylife); 0 machine-specific paths |
| L1-07 timestamps | partly | presence/format/zone/range only: 10,791 naive `YYYY-MM-DD HH:MM:SS`, 2026-06-16 00:03:06 .. 2026-08-12 23:58:05; no per-step time, so no within-unit monotonicity |
| L1-08 degenerate | yes | 2 empty-message logs (2-3 ms), 0 `error` non-null, 322 null-final, 675 unexecuted-tail logs, min file 1,751 B |
| L2 selection/import | yes | 103 strata, cap 300; `l2_import.py` with the CLI's tree class |
| L2 validate / recompute --dry-run / determinism | yes | all tiers pass; recompute 0 differences on the scratch corpus; second import with a different `--jobs` byte-identical (first determinism evidence for ROPE: I says `second_import = not_run`) |
| L2 verify --level chain | yes | on a sealed scratch copy |
| L2 A2 error classes, A3 PI-nn | yes | expect 0 degenerate, 0 `adapter_defect`, no dangling/invented relations; I-class statements only in inference bundles |
| L2 evidence classes | yes | FA baseline core O .61 / D .29; after item 3 and D-86 more statements move to inference (I); 0 core I |
| L2 identity | yes | models from directory; ablation/router → gpt-4o-mini; 0 `identity_unresolved`; `identity_conflict` only on qwen3-235b autodojo |
| L2 redaction | yes (reduced) | no redact table; 0 account paths in AER/SEM/PROV |
| L2 withholding | **no** | no `[withhold]` table and no real credential expected; L1-06 counts stand in |
| L2 outcome sanity | yes (pooled) | §4 |

## 8. Hypotheses (falsifiable)

| Id | Expectation | Threshold / falsified if |
|---|---|---|
| H-01 | Staged snapshot equals the pin: 24,909 files, 265,463,047 B, tree `c4df12c3`; 10,791 logs, 175,263,358 B | any difference |
| H-02 | Arm grid exactly as §3, missing/extra cells exactly as listed | any count ≠ (tolerance 0) |
| H-03 | Recorded outcomes reproduce AP Tables 6/9 for gpt-4o-mini and gemini (36 per-suite figures) and RP's corrected values (§4 integers) | any per-suite count differs (census); in L2, a pooled gap beyond the README threshold |
| H-04 | Corrections: slack IT5 32 → 0, dailylife IT7 39 → 22, github IT1 5 → 0; AutoDojo 88 → 71 | any count differs |
| H-05 | II corrected successes in RP paper cells = 90 with the Table 6 split | ≠ 90 or a different split |
| H-06 | AgentDyn #8: github `user_task_5/7/8/11` have `utility` false in every ROPE github log (all trees and attacks) | any true |
| H-07 | Released clamp logs exist only for router `*-clamp/dailylife` (440); none for github/shopping or Opus, so 7 of RP Table 5's 9 per-suite clamp cells and all 3 clamp overall values are not reproducible from the release | clamp logs found elsewhere |
| H-08 | gpt-4o-mini main-tree tags: iter4 1,774, iter2 178 (06-16), final-opus 63 (08-12); no log names the Opus router otherwise | different counts |
| H-09 | Denial variants 9,424 / 3,233, both only on 2026-06-29; gpt-4o II 261 / 239 | different counts or dates |
| H-10 | Long-horizon: 760 logs `v1.2.1`, recorded security true 0 of 758; `lh_cells.json` travel sets = logs minus the empty `user_task_2`×`injection_task_2` log for gpt-4o-mini and qwen3-235b | any success or other difference |
| H-11 | #188: slack logs with a denied `post_webpage` exist and all carry `utility`; 0 non-null `error` in 10,791 | a slack log without outcome other than the 2 LH empties |
| H-12 | Completeness at the scratch import: `verified_complete` 0; 322 null-final `unverifiable`; 2 empty `known_incomplete` (or `unverifiable`) | any `verified_complete`, or 322 still `known_incomplete` |
| H-13 | `success_without_visible_payload`: only the 5 named II executions; 0 in the AutoDojo arm | a flag on any other sampled execution |
| H-14 | Item 5: exactly 1 `load_environment` activity (class I) per sampled attacked execution, 0 per clean; inputs = the execution's fixtures | any deviation |
| H-15 | B1: AutoDojo executions with a `present` marker ≈ 88.8 % (2,528 / 2,847) | sample Wilson 95 % interval excludes 88.8 % by > 5 pp, or includes the E2 value 39.3 % |
| H-16 | SEM under `suites@2`: tools of github/shopping/dailylife logs annotated `agentdojo.unknown_tool@1` (fail-closed) in 100 %; AgentDojo-suite unknowns present but rare (E2: 3,820 of 655,557 annotations) | AgentDyn-suite tools labelled under @2, or AgentDojo-suite unknown share > 2 % of their annotations |
| H-17 | U6-c: every model call has `/params` `not_recorded` | any model call without it |
| H-18 | Identity: 0 unresolved; 949 conflicts all `qwen3-235b/*/autodojo`; 2,920 ablation/router logs resolve to gpt-4o-mini | any other |
| H-19 | Determinism: scratch import A vs B (different `--jobs`) byte-identical | any byte difference |
| H-20 | Duplicates as §5 census row (0 byte-identical, 52-53 groups / 396 files, 9 AgentDyn content twins) | 0 byte-identical violated, or groups outside 52-53 |
| H-21 | Timestamps: all 10,791 parse, naive, range as §7; qwen autodojo all 2026-06-30 | any unparseable or out-of-range value |
| H-22 | artefacts.toml stale entries (`rope.art.autodojo_payload_escaped` 1,166 / "unescape not applied"; `rope.art.security_without_exposure` 22; `rope.art.pipeline_tag_not_identity` wording) disagree with the code and data | they agree (then no finding) |
| H-23 | AgentDojo #181: recorded banking `security` true = 0 in II and autodojo arms (RP/AP banking ASR 0.0) | any true |

Never exclude data because an arm has no attack success (user rule). The long-horizon arm's zero successes are a result, not a defect.

## Fact-check (2026-10-14, adversarial, public sources only)

Re-checked without downloading any data payload or computing anything from the raw logs (details and URLs in
`../data/rope/research.json` → `fact_check`).

- **Pin and record (confirmed):** `64495e16` is HEAD of `main` (only branch), tree `c4df12c3`, 3 commits, last push
  2026-08-31, 0 tags/releases/issues/PRs/forks. Recursive tree listing (not truncated): 24,909 blobs / 265,463,047 B;
  `runs/` `6a8c86f2` 10,805; 10,791 logs / 175,263,358 B; AutoDojo slice 2,847 / 48,275,981 B; 103 strata with exactly the
  §3 per-cell counts (incl. LH travel 24/25/24). No HF/Zenodo record.
- **Licence (confirmed):** MIT at the pin with the five named holders; vendored `autodojo/LICENSE` AgentDojo MIT;
  `agentlab/LICENSE` MIT, no holder; upstream AutoDojo MIT; papers CC BY 4.0; no use-restriction clause.
- **Papers (confirmed):** ROPE arXiv 2608.27496 v1 only, abstract names the repository; AutoDojo 2606.15057 v1/v2/v3 dates and
  v1 title. Every ROPE value cited from RP Tables 2, 3, 4, 5, 6, 11, 13, 14 and AP v3 Tables 5, 6, 8, 9 re-read: all equal.
  RP defines Overall as the unweighted suite mean and re-scores three injection tasks by effect (A.5); A.4 temperature 0.
- **§4 integers (confirmed):** recomputed from the published percentages and n; consistent with every macro value; 90 =
  24 + 22 + 31 + 13 and the Table 6 split; AutoDojo 88 → 71; LH CU 25/38, 26/38, 27/38.
- **Harness/bug claims (confirmed as cited):** AgentDyn #6 closed 2026-05-02 before `5353cf76`, #8 open; AgentDojo #138, #139,
  #161, #168, #177 (a PR), #181, #188, #189, #212, #214, #218 titles match; PyPI latest 0.1.35. README OpenRouter claim and
  `router.py` "--" / `_scope.py` gpt-4o scope confirmed in the code at the pin (L-01 arithmetic: 9 per-suite clamp cells, 2
  reproducible). Upstream HEADs `aa458794`, `36f58e60`, `5353cf76` unchanged.
- **Corrected:** (1) research.json `expected_counts`: `select.not_execution_artefact` 301 is `autodojo/**` (304) minus the
  3 routed caches; `runs/lh_cells.json` is a context artefact, not one of the 301. (2) §5 `rope_release_tree`: the 440 clamp
  files are part of router 1,680.
- **Notes for the verifier:** pin accounting 24,909 = 10,791 + 35 + 14,066 + 17 files outside every glob. RP Table 6 has no
  dailylife IT7 row, so the 22 corrected dailylife IT7 successes (Q8, all `important_instructions`) should lie outside the
  paper cells (ablation/router trees); flagged, not added as a hypothesis.
- **Unverifiable here** (rest on our own census/verify reports): L-02 tag counts, L-03 dates and 261/239, L-04, L-05, the log-side
  evidence of L-06, message/call counts and E2 annotation counts.
