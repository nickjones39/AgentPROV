# Pre-registration: `drift1-agentdojo`

| | |
|---|---|
| Corpus | `drift1-agentdojo` (source `drift1-agentdojo`, family `agentdojo`, profile `drift1-agentdojo` version 1, sha256 `3df46db9…`; dialect/mapper `agentdojo.tracelogger` through the DRIFT build, variant `drift.k18.conversations`; identity table `drift1_model_dirs` `dc5b3c42…`) |
| Parts | `drift`: 626 logs at `CGboom-git/drift-1@0e28729b4d9a6f466ba4803ccdc18a842c50cd20`, `runs/` tree `cb44a83f…`; 1,569 DRIFT head copies are `select.owned_elsewhere` (owner `drift`) |
| Wave / mode | wave 7 (phase-10j parts, pending recipes). **Full checks.** Not examined in FA or E2 and no stored corpus, so there is no E2 delta. The baseline is the phase-10j trial (2026-10-14) |
| Code | `065b0d36` or later on `precheck-corpora` (written at `6b76c15e`; the examiner records the exact commit) |
| Date | 2026-10-14 (GitHub, arXiv, PyPI metadata queried 2026-10-15) |
| Status | **Written before any pre-check data check of this corpus.** Nothing here was computed from the raw data. Every number comes from a cited earlier report, the profile, the registry, GitHub tree metadata (paths, blob ids, sizes) or the paper. Rates and "Δ" counts are arithmetic on those figures |
| Desk research | [`../data/drift1-agentdojo/research.json`](../data/drift1-agentdojo/research.json) |

Sources: profile (P); identity table (T); registry and `tools/readme_corpora.toml` (REG); phase-10j census §7 and `census.json`
`/sources/drift-1` (10J-C); phase-10j trials batch A (10J-T) and the trial summary
`~/.agentprov/migration-work/phase10j/trials/drift1-agentdojo.summary.json`; the profile census
`~/.agentprov/migration-work/phase10j/profiles/drift1.drift.json` (10J-PC, outside Git); phase-10l census and trials (10L-C, 10L-T);
`investigation/verify/drift.md` §7 (VER); DECISIONS D-93, D-256, D-257, D-272..D-279 (DEC); the `drift` pre-registration (DPR);
GitHub API on 2026-10-15 (GH); DRIFT paper arXiv:2506.12104v3 (PAP).

**Δ** = the drift-1 figure in 10L-C or 10J-C (2,195 files, copies included) minus the DRIFT head figure (1,569). The two are
byte-identical (10L-C §1.1; GH: subtree `4c005882` equals DRIFT head's), so Δ is the figure for the 626.

## 1. Desk research in brief

- **The pin is still HEAD.** `main`, the only branch, is at `0e28729b` (2026-06-27T09:26:55Z). The repository was created on 2026-06-23
  and has 0 tags, releases, issues, PRs or forks, and licence `null`. GitHub records it as **not a fork**: it is a copy that
  holds DRIFT's history up to `70d59166` (2026-04-19) plus 16 commits of its own, and it never got DRIFT's `6fd3df47` LICENSE commit.
  The staged bare clone's `runs/` tree `cb44a83f` equals GitHub's.
- **When the runs were committed.** `dad26506` (2026-06-23T10:02Z) added 97 benign runs. `d2c374f8` (2026-06-24T03:01Z) added
  519 attacked runs and 7 cpython-311 `.pyc` files. `79f58f09` (2026-06-25T06:21Z) added the 10 PACT runs. No later commit touches `runs/`.
- **Code.** At `d2c374f8` every source file has DRIFT `70d59166`'s blob id. The 616 were therefore committed with DRIFT's code, which is
  later than the code behind DRIFT head's own runs. The PACT code (`f2d0c5c0`, `bd2df9fd`, `a5c391f7`, `3dd04ed7`) precedes
  the PACT runs. Every later commit (`0fa427a2`, the first IFC commit `09282de4` [corrected by fact-check: was `6bf961c1`], and `6bf961c1`..`0e28729b`) follows them, so the code at the pin produced neither set.
- **No paper and no record.** The README is DRIFT's, byte for byte (blob `34603827`). PACT (arXiv:2605.11039) appears to be the
  concept behind the extension, but drift-1 does not cite it and it reports no numbers for these runs. PAP v3 (unchanged since 2026-03-26) is the
  only reference for the 616.
- **Harness.** `agentdojo==0.1.35` (still the latest on PyPI), Python 3.11, label `v1.2`, `--seed 98`. For `gpt-` models the attack
  pipeline name is hard-coded to `gpt-4o-2024-05-13`. Known checker issues for these cells: agentdojo PR #146 (workspace u13 is
  pre-v1.1.2), #161 (banking UserTask5 utility can be true without the payment), #168/#189 (traces count proposed calls).
- **Licence.** There is no top-level LICENSE file [corrected by fact-check: `ASB_DRIFT/LICENSE` (MIT, (c) 2024 AGI Research) exists at the pin, inherited with DRIFT's ASB subtree; it covers that subtree only and not `runs/`]. The MIT badge is the upstream README's, inherited and not stated by the drift-1 contributors.
  DRIFT's MIT LICENSE (Hao Li) was added on 2026-07-16, after drift-1's last push. Policy `include` (D-93, D-256).

## 2. Expected counts (part `drift`)

| Measure | Expected | Source |
|---|---:|---|
| Files selected (= units = executions) | 626 (616 `runs/gpt-4o-mini` + 10 `runs/pact-gpt-4o-mini-banking10`) | REG 626; 10J-C §7; 10J-T; GH tree |
| Bytes selected; size min / max | 6,693,705 (6,492,493 + 201,212); 1,876 / 48,278 | GH tree (P has no `expected_bytes`) |
| Excluded `select.owned_elsewhere` (owner `drift`) | 1,569 | P; 10J-T summary |
| Other blobs at the pin outside `include = runs/**/*.json` | 340 (2,535 − 2,195), including 4 `runs/**/*.log` (4,319,452 bytes) | GH tree |
| Attacked / benign | 529 / 97 | 10J-PC (`injection_map_not_recorded` 529; `benign_security_constant` 97); Δ 10L-C §3 |
| Messages (user / assistant / tool) | 6,061 (892 / 2,963 / 2,206) | Δ 10L-C §3; 10L-T |
| CALL ERROR `user` messages (files; trajectory / checklist / other) | 266 (173; 59 / 198 / 9) | P quirk; Δ 10L-C §3 |
| Assistant re-serialised / raw | 2,617 / 346 | P quirk |
| Tool calls = tool messages; call batches | 2,206; 2,071 | P quirk; Δ 10L-C |
| Tool errors (invalid tool / ValidationError / exception) | 179 (20 / 37 / 122) | Δ 10L-C §3 |
| Final turns with call text and empty `tool_calls` (re-serialised / raw) | 78 (78 / 0); partial-drop upper bound 3 | P quirk; Δ 10L-C |
| Runs without a tool execution; files with a call | 15; 611 | Δ 10L-C §4; P `args_mutated_in_place` |
| `initial_checklist` raw / JSON / `None` | 624 / 0 / 2 | Δ 10L-C §4 |
| `initial_trajectory` covers executed functions: yes / no / no executions | 441 / 170 / 15 | Δ 10L-C §4 |
| Runs with run-time stamps in tool outputs | 20 | Δ 10L-C §5 (391 − 371) |
| Isolation frames: excised in last position / intact in non-last positions | 481 / 12 | Δ 10L-C §5 |
| Outcomes: `utility = true`; `security = true` (benign constant + attacked) | 351; 114 (97 + 17) | Δ 10J-C `census.json` (992 − 641; 209 − 95, head counts from DPR §4) |
| AER (10L-T): valid; decisions (isolation + CALL ERROR); tool executions; model calls | 626; 2,337 (2,071 + 266); 2,206; 2,963 | 10L-T |
| Issue files (10J-PC, 10J-T) | `accounting_unverifiable` 626; `drift.agent_prompt_not_recorded` 626; `drift.injection_map_not_recorded` 529; `drift.calls_in_text_not_executed` 78; `agentdojo.unknown_top_level_key` 10; `drift.call_error_unrecognised` 4 (9 messages) | 10J-PC; 10J-T |
| Trial status | 546 ok / 80 ok with issues; 0 failed checks (68); byte-identical across `--jobs` 4/2 (2,513 files) | 10J-T |
| L2 sample | 45 (9 strata × 5; PACT stratum 5 of 10), if the stratum key includes `model_dir` (open question 1); otherwise 40 (8 × 5) | README §4 |

## 3. Expected arms

There is one model, `gpt-4o-mini`: the undated alias, equal to `pipeline_name` in 626 of 626 and to the directory in 616. OpenAI lists only
`gpt-4o-mini-2024-07-18` for it, and the served model is not recorded. There are two defence rows (T, 10J-PC): `drift` (616) and `drift+pact_drift` (10).
DRIFT flags are T/T/T/F (no adaptive attack). Suites are the AgentDojo four only.

| Arm (model_dir) | Suite | `important_instructions` | `none` | Grid (v1.2) | Notes |
|---|---|---:|---:|---|---|
| `gpt-4o-mini` | banking | 144 | 16 | 16 u × 9 i, full | includes u5 (#161) |
| `gpt-4o-mini` | slack | 105 | 21 | 21 × 5, full | includes i5 (#168) |
| `gpt-4o-mini` | travel | 140 | 20 | 20 × 7, full | |
| `gpt-4o-mini` | workspace | **130** | 40 | 40 × 14 = 560 | **partial:** u0-u3 and u5-u9 × 14, u10 × i0-i3, **u4 absent**; benign 40 includes u13 (PR #146) |
| `pact-gpt-4o-mini-banking10` | banking | 10 | 0 | u0-u9 × i0 | six PACT keys; 9 PACT refusals |

- **Expected missing cells:** 430 workspace attacked cells (u4 × 14, u10 × i4-i13, u11-u39 × 14). Also missing: AgentDyn suites,
  other models, the adaptive attack, other attacks, ASB, and PACT benign runs or other suites.
- **Expected extra cells:** none. A ninth cell, or a `none` file in the PACT directory, is a finding.

## 4. Expected outcome rates and the mapping

**Mapping** (as for DRIFT, DPR §4). `utility` is the checker result. `security = true` means the injection succeeded (ASR). On benign runs
it is the constant `true` (`drift.benign_security_constant@1`, D-278). UA is the share of attacked files with `utility = true`, ASR is the share
with `security = true`, and BU is the share of `none` files with `utility = true`. The paper's overall is the unweighted mean of the suite rates.

**Targets.** There is no paper for drift-1. The 616 are compared with PAP v3 (a third-party re-run on the alias, with later DRIFT code).
They are also compared, pair by pair, with DRIFT head on the same (suite, user, injection) cells (519 attacked cells, all present in head).
The PACT arm has no target.

| Cell (616 arm) | n | PAP v3 (k) | DRIFT head, same cells (k) | Paper source |
|---|---:|---|---|---|
| banking UA / ASR | 144 | 40.97 (59) / 4.86 (7) | 59 / 7 | Tables 7, 8 |
| slack UA / ASR | 105 | 49.52 (52) / 0.00 (0) | 55 / 1 | same |
| travel UA / ASR | 140 | 53.57 (75) / 0.00 (0) | 75 / 0 | same |
| workspace UA / ASR | 130 (subset of 560) | 59.64 / 0.54 (full grid; ≈ 77.5 / 0.7 expected *counts* k on 130 [clarified by fact-check]) | not in reports (L1 computes it on the 130 pairs) | same; **subset caveat** |
| banking / slack / travel / workspace BU | 16 / 21 / 20 / 40 | 50.00 (8) / 66.67 (14) / 55.00 (11) / 57.50 (23) | n/a (head has no benign AgentDojo runs) | Table 6 |
| AgentDojo overall BU / UA / ASR (macro) | 97 / 519 here; paper 97 / 949 [clarified by fact-check] | 57.29 / 50.93 / 1.35 | — | Tables 1, 2, 6-8 |
| Pooled, 616 arm: utility | 616 | ≈ 319.5 (51.9%) implied | — | arithmetic |
| PACT arm UA / ASR | 10 | none | head u0-u9 × i0 (L1 computes) | report only, Wilson 95% |

Population bounds from §2 (PACT outcomes unknown, 0-10): the 616 have 341-351 `utility = true` (55.4-57.0%, which is +3.5 to +5.1 pp
over the paper-implied pooled figure). Attacked successes are 7-17 of 519 (1.3-3.3% against ≈ 1.5% implied). **Rule (README §4,
amendment 2.2):** at L1 a gap is a finding when it exceeds 15 pp on a cell with n ≥ 20, or when the binomial 95% interval excludes the
paper by more than 5 pp. The workspace UA and ASR verdicts come from the paired head comparison only. The PACT arm (n = 10) is reported
with Wilson intervals and gets no verdict. At L2 there are 5 per stratum, so the sample gives no verdict.

## 5. Known quirks (do not report as new)

| Id / source | What | Expected (626) |
|---|---|---|
| P `drift_tool_output_post_isolation` (D-274, BF-28) | one isolation decision on the last tool message of each batch | 2,071 / 2,206 |
| P `drift_assistant_reserialised` | template text, not the raw completion | 2,617 / 346 |
| P `drift_call_error_as_user` (D-273) | validator refusal logged as `user` | 266 messages, 173 files (59 / 198 / 9) |
| P `drift_calls_in_text_not_executed` (D-277) | proposed calls not executed | 78 final turns (re-serialised) |
| P `drift_no_system_no_injections` | no system message, no payload map | 0 / 0 |
| P `drift_plan_fields_by_commit` (D-276) | `initial_plan` | 626 / 0 contradicted |
| P `benign_security_constant` | benign `security` constant true | 97 files |
| P `args_mutated_in_place` | 0.1.35 `ToolsExecutor` | 611 files |
| P `provider_call_id_anomalies` | seeded ids reused across files | 0 null ids, 0 in-file duplicates |
| D-256, D-279, 10J-PC | PACT: six extra keys (`agentdojo.unknown_top_level_key`, generic `extra`); 9 CALL ERRORs matching neither DRIFT check (`drift.call_error_unrecognised`) | 10 files; 4 files / 9 messages |
| T, D-256 | PACT directory differs from `pipeline_name`: its own row, defence `pact_drift` beside `drift` | 10 |
| D-272 | `code_identity = unpinned`, `verified_code = []`: every harness rule is cited at class I | every AER |
| D-93 | licence MIT by README badge only | — |
| D-257, 10J-C §7 | no `[withhold]`; the one `hf_` shape is in a non-log file, not selected | 0 in selected |
| 10L-C §5 | content stamps are content, not AER time (D.6.8) | 20 runs |
| artefacts.toml | **no entry scoped to `drift1-agentdojo`** (the `agentdyn.art.drift_*` entries are AgentDyn's) | report as a documentation gap (S3) |

## 6. Check map

| Check | Applies | Expected / why |
|---|---|---|
| L1-01 counts | yes | §2-§3. Read from the bare clone (`--git ~/.agentprov/staging/10c/drift-1/drift-1.git`, as 10J-C did), not from the checkout directory beside it. Selected 626, excluded 1,569 `owned_elsewhere`; `.DS_Store`/`._*` outside `runs/` are not selected |
| L1-02 strict parse | yes | 0 failures. Key sets: 616 × 18 keys (KD18 + `conversations`) and 10 × 24 (+6 PACT keys) in the `json.dump` order of `pipeline_main.py`. `pipeline_name` `gpt-4o-mini` in 626; `benchmark_version` `v1.2`; flags T/T/T/F; `pact_drift_enabled` true in 10, absent in 616 |
| L1-03 encodings | yes | no prior count; `ensure_ascii` escapes. CALL ERROR `repr` wrappers are a known literal-escape residue (266 messages) |
| L1-04 duplicates | yes | 0 byte-identical pairs among the 626; 0 overlap with every in-scope part (10L-C §1.1: new against DRIFT head, AgentDyn C/D, Figshare, EnvironmentOptim). The 1,569 excluded files equal drift head (subtree id). Identical-trajectory groups: report only |
| L1-05 arm coverage | yes | 9 cells, §3; workspace partial as listed; L1-05b outcome recount §4 |
| L1-06 secrets, account paths | yes | 0 secret-like strings and 0 account paths in the 626 (counts and pointers only). Watch `/global_tool_contract_path` in the 10 PACT files (default relative) |
| L1-07 timestamps | presence only | 0 structured time fields (also none expected inside the PACT keys). Content stamps: 20 runs |
| L1-08 degenerate | yes | 0 empty files; ≤ 15 runs without a tool execution; every run ends with an assistant message; messages per run within 2..23 |
| L2 import, validate (all tiers), `recompute --dry-run` | yes | first run at current code (10J-T was pre-merge). Registry `planned`: run through `l2_import.py` |
| L2 determinism | yes | byte-identical (10J-T: 2,513 / 2,513) |
| L2 A2/A3 classes | yes | 0 `adapter_defect`, 0 degenerate, 0 `drift.plan_semantics_contradicted`; `drift.call_error_unrecognised` only in PACT files |
| L2 evidence classes | yes | 0 class-D citations (twins only); logged values O |
| L2 identity | yes | model `gpt-4o-mini` in every sampled AER; defences `drift` or `drift`+`pact_drift` per T; 0 `identity_unresolved`, 0 `pipeline_name_mismatch` |
| L2 redaction | yes | no `redact` table; no account path in AER/SEM/PROV |
| L2 withholding / sealed chain | chain only | no `[withhold]` (D-257); `verify --level chain` runs |
| L2 outcome sanity | report only | n = 5 per stratum |
| AgentDyn-specific (AD#6, AD#8, label semantics) | no | no AgentDyn suites |
| E2 delta | no | not in FA/E2; §8 lists the expected movement since 10J-T |

## 7. Hypotheses (falsifiable)

| Id | Expectation | Refuted if | Level |
|---|---|---|---|
| H-01 | 626 files, 6,693,705 bytes, 1,569 excluded; cells exactly as in §3 | any difference | L1-01/05 |
| H-02 | workspace attacked = u0-u3 and u5-u9 × i0-i13, plus u10 × i0-i3; u4 has only `none` | any other set | L1-05 |
| H-03 | parse and key sets as in the L1-02 row; `pipeline_name` `gpt-4o-mini` 626/626 | any exception | L1-02 |
| H-04 | message, call, batch, error, checklist and stamp counts equal §2's Δ figures exactly | any count differs (then 10L-C or the head counts are wrong: analysis-artefact or documentation) | L1 |
| H-05 | `utility = true` 351/626; `security = true` 114 = 97 benign (all) + 17 attacked | any differs | L1-05b |
| H-06 | 616 arm vs PAP v3 per suite (banking, slack, travel UA/ASR; all four BU): every gap within the §4 rule (≤ 15 pp, and the 95% interval does not exclude the paper by more than 5 pp) | any cell breaks the rule (finding: re-run divergence, not a mapping defect, unless L2 mapping disagrees with raw) | L1-05b |
| H-07 | paired with DRIFT head on the 519 attacked cells: per-suite UA within 15 pp and ASR within 5 pp of head on the same cells; concordance reported | any suite outside | L1 (cross-part) |
| H-08 | the 9 unrecognised CALL ERRORs (4 PACT files) all begin with PACT's provenance-contract refusal (DRIFTLLM at `79f58f09`), not IFC text | any other form (then the PACT runs used uncommitted or IFC code) | L1 (prefix class only) |
| H-09 | content stamps: 97 benign runs ≤ 2026-06-24T00:02, 519 attacked ≤ 2026-06-24T17:01, PACT ≤ 2026-06-25T20:21 (commit time + 14 h for the unknown zone), and none before 2026-04-19 (DRIFT `70d59166`) | any stamp outside | L1-07 |
| H-10 | 0 secret-like strings, 0 account paths; PACT `global_tool_contract_path` relative (no home path) | any (security-relevant: report to the orchestrator at once; needs a D-182-style redaction) | L1-06 |
| H-11 | 0 byte-identical pairs among the 626 and 0 overlap with any in-scope part | any | L1-04 |
| H-12 | L2: every sampled execution valid in every tier; determinism byte-identical; issue-code rates as in 10J-PC (`calls_in_text_not_executed` ≈ 12%, PACT-only codes only in PACT units); no new code | any validation error, nondeterminism or new code | L2 |
| H-13 | decisions per execution = call batches + CALL ERROR messages; population total 2,337 | any execution differs | L2 |
| H-14 | every benign sampled AER records its `security` origin as `harness_default` under `drift.benign_security_constant@1` (10J-PC shows `origin_rule_applied` 0) | 0 citations (mapping or documentation finding) | L2 |
| H-15 | 0 class-D rule citations (D-272) | any | L2 |
| H-16 | banking u5 (#161): `utility = true` in all 11 u5 files (1 benign, 9 attacked, 1 PACT), if the v1 checker is in force at `v1.2` | any `false` (documentation note on #161's reach) | L1-05b |
| H-17 | every slack i5 `security = true` file holds an executed membership tool call (#168/#189 do not inflate DRIFT, which drops refused calls) | a success without an executed membership call | L1 (call names) |
| H-18 | SEM `agentdojo.suites@2`: ≤ 5% of sampled tool outputs carry the unknown-tool label (AgentDojo suites only; invalid-tool share 20 of 2,206) | > 5% | L2 |

Rule: no cell is excluded or proposed for exclusion because no attack succeeded (slack and travel ASR are expected to be near 0).

## 8. Expected movement (no E2; baseline = phase-10j trial, 2026-10-14, profile sha `3df46db9…`)

The 10J-T corpus and the 10J-PC digest-of-digests `4197a967…` (and 10L-T `54fd812a…`) are **not** expected to reproduce. The
phase-10j branch was cut before these changes, which reached it only through the `9566a207` merge (2026-10-15):

| Change | Expected in L2 |
|---|---|
| `d12b973b` U6-c (D-373) | every `model_call` has `unk /params not_recorded` |
| `446e9f13` BF-28 | isolation on the last tool message of a batch by role; byte-neutral on well-formed batches (0 orphan tool messages): 2,071 decisions stay |
| `9410c7d3` item 7 (D-378) | lone surrogates mapped with a disclosure; expect 0 (L1-02 reports) |
| `98476de3` items 4/6/8 (suites@2) | SEM labels can move; AER bytes do not |
| `2fcc66d5` item 5 (D-370) | TraceLogger-only per its message: the examiner records whether DRIFT AERs gain the `load_environment` activity (a gain is a finding to classify) |
| `219afba5` items 22/23 | product-path dispatch to `DriftBuild`; tool label through `drift.isolation_pass` |
| unchanged | executions 626; message, tool-execution, model-call and decision counts per execution; issue codes and counts of §2 |

Any other difference per execution against the 10J-T corpus (`~/.agentprov/migration-work/phase10j/trials/drift1-agentdojo-j4.partial`) is a finding.

## 9. Open questions (for the orchestrator before the wave-7 batch)

1. Stratum key: the family default (`_prefix`, `pipeline_dir`, `suite`, `attack_dir`) has no `model_dir` facet for this layout, so the PACT arm would merge into banking attacked. Should a `STRATA['drift1-agentdojo'] = ('model_dir', 'suite', 'attack_dir')` entry be added before the batch? That is a tool change, not a re-key.
2. The four unselected `runs/**/*.log` files probably record the workspace interruption and the commands. Reading them is a payload read and needs a yes.
3. Licence owner: does the inherited README badge cover the drift-1 contributors' own runs (D-93 records "badge only")?
4. Should the profile header's "a fork of SaFo-Lab/DRIFT" read "a copy with DRIFT history to `70d59166` (not a GitHub fork)" (S3)?

## 10. Not in scope

The 1,569 DRIFT head copies (owned by `drift`, counted there), the launch/experiment logs, `contracts/` and `ASB_DRIFT/`, and the sibling
repositories `drift-clean` and `drift-new`. Per GH, `drift-new` holds head copies and 3 other JSON files and none of the 626.

## Fact-check (2026-10-15, adversarial, desk only)

Re-opened: arXiv:2506.12104v3 HTML Tables 6, 7, 8 (GPT-4o-mini DRIFT rows) and the arXiv API (versions of 2506.12104 and
2605.11039); GitHub API for `CGboom-git/drift-1` (repo, branches, tags, releases, compare `70d59166...0e28729b`, commit file
lists of `dad26506`/`d2c374f8`/`79f58f09`, recursive tree at the pin, `README.md`, `ASB_DRIFT/LICENSE`, `pipeline_main.py`,
`utils.py`, `DRIFTLLM.py` at `79f58f09`); `SaFo-Lab/DRIFT` (`70d59166`, `6fd3df47` LICENSE, README history, `runs/` subtree);
the sibling repos' trees on every branch; agentdojo #146/#161/#168/#189; PyPI agentdojo JSON; OpenAI's gpt-4o-mini page;
our phase-10j census.json and trials, phase-10l census §1-§5 and trials, the profile, `tools/readme_corpora.toml`,
`tools/precheck/l1_families.py` and DECISIONS D-93/D-256/D-257.

Confirmed: every paper value in §4 (Table 6 BU 50.00/66.67/55.00/57.50, overall 57.29; Table 7 UA 40.97/49.52/53.57/59.64,
overall 50.93; Table 8 ASR 4.86/0.00/0.00/0.54, overall 1.35; k values fit n 144/105/140/560; the paper names
gpt-4o-mini-2024-07-18); v3 (2026-03-26) is still the latest. Pin = HEAD of the only branch, fork false, licence null,
0 tags/releases; 16 ahead / 0 behind `70d59166`. Tree: 2,535 blobs, not truncated; `runs/` `cb44a83f`; DRIFT subtree
`4c005882` = DRIFT `6fd3df47`'s; 626 selected = 6,693,705 bytes (6,492,493 + 201,212), 1,876..48,278; four logs 4,319,452;
the nine cells and the workspace subset (u0-u3, u5-u9 × 14, u10 × i0-i3) exactly as §3; per-commit additions as §1; at
`d2c374f8` the top-level tree equals DRIFT `70d59166` except `runs/` and `__pycache__`; no commit after `79f58f09` touches
`runs/`. PACT: six keys in `pact_result_fields`, default relative contract path, the provenance-contract refusal in
`DRIFTLLM.pact_argument_constraint_validation`; seed 98, label v1.2, hard-coded `gpt-4o-2024-05-13`. README blob
`34603827` and requirements `f322210b` equal DRIFT's; the badge came with DRIFT `840c24db`. #146 (PR), #161, #168 open,
#189 closed 2026-09-07; agentdojo 0.1.35 is the latest on PyPI. Every Δ figure in §2 recomputes from phase-10l census §3-§5
and phase-10j census.json (e.g. 22,929 − 16,868 = 6,061; 992 − 641 = 351; 209 − 95 = 114). 18/24 key counts match the
code (`KD18_BASE` has 17 keys + `conversations`). The stratum claim holds: the profile's layout binds `model_dir`, so the
family default (`_prefix`, `pipeline_dir`, …) gives 8 strata. 0 of the 626 blob ids occur in drift-clean or drift-new.

Corrected: the first IFC commit is `09282de4` (2026-06-25T15:26Z), not `6bf961c1` (conclusion unchanged); the pin holds
`ASB_DRIFT/LICENSE` (subtree only), so "no LICENSE file" now reads "no top-level LICENSE file"; research.json commit count
42 (26 from DRIFT), not 43 (27). Clarified: the "≈ 77.5 / 0.7 on 130" figures are expected counts, and the paper's overall
n is 97 / 949. Not re-checked: DRIFT head's run-code range `763a7d65..336dca9e` (from the `drift` pre-registration) and the
10J-PC/10J-T issue counts beyond what the stored census file and trials report state.
