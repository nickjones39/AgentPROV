# Pre-registration: `mandate-agentdojo-eval`

| | |
|---|---|
| Corpus | `mandate-agentdojo-eval` (family `agentdojo`, profile `mandate-agentdojo-eval@2`, rules `aer 1 / agentdojo 2 / mandate 1`, SEM `agentdojo.suites@2`) |
| Parts | `head`: 396 TraceLogger logs at `fa62a977584962f7b4b24a40772a83345fd920d4` (git, `jwilliamsc/mandate-agentdojo-eval`) |
| Code commit | `065b0d36` (branch `precheck-corpora`) or later |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Wave 1, delta corpus (examined in E2, `docs/reports/analysis/phase10-examination-2.md`) |
| Desk research | `../data/mandate-agentdojo-eval/research.json` (URLs there) |

Sources of the figures below: **P** = profile `src/agentprov/adapters/agentdojo/profiles/mandate-agentdojo-eval.profile.toml`;
**I** = `docs/reports/mandate/import-cli-mandate.json` (p10, `afe7038`); **V** = investigation `verify/mandate-agentdojo-eval.md`
(§ given); **S** = investigation `sources/mandate-agentdojo-eval.md`; **R** = upstream README at the pin; **G** = GitHub API
2026-10-14; **A** = `src/agentprov/adapters/agentdojo/artefacts.toml`; **E2** / **FA** = examination 2 / first analysis;
**RB** = `docs/reports/analysis/regen-batch.md`.

## 1. Desk research summary

- **No paper of its own.** The repository README is the only description (one commit, 2026-08-17; no tags, releases,
  issues, PRs, forks; nothing pushed since; G). No Zenodo/HF/Figshare record: the git tree is the record.
- **Pin agrees with upstream today** (G): main = `fa62a977`; `runs/` tree `11b6d0e4`, 396 blobs, 3,103,968 B, not truncated;
  root blob SHA-1s equal V §1.
- **Harness:** `agentdojo==0.1.35` (PyPI wheel `364bea42…`, uploaded 2025-10-27, still the latest; equals P), banking suite
  `v1.2.1` (not v1.2.2), model `gpt-4o-2024-05-13` (OpenAI), temperature not sent (inferred), up to 3 passes, last logged.
- **Benchmark issues that touch this data** (ethz-spylab/agentdojo): #181 banking InjectionTask0/1/3 subject check is
  dead code (security biased upward); #161/#159/#138 banking UserTask5 utility vacuous; #110 UserTask6 checker fixed only
  in v1.2.2; #189/#168/#218 trace-based scoring of proposed calls (slack only, banking unaffected); #194 truthiness guards
  in `update_scheduled_transaction`/`update_user_info`.
- **Licence:** MIT (`Copyright (c) 2026 Mandate Labs`), no data licence, AgentDojo text MIT; publisher unverified; model
  output terms unassessed.

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Files at the pin (listing) / bytes | 401 / 3,137,054 | P `[[source.pins]]`; G |
| Selected logs (`runs/**/*.json`) / bytes | 396 / 3,103,968 | P; G; I `candidates` |
| Context artefacts stored (not mapped) | 4 (`agentdojo_mandate_eval.py`, `README.md`, `requirements.txt`, `LICENSE`) | P `context_artefacts`; I (400 verified) |
| Not selected | 1 (`.gitignore`, outside include) | P; G |
| Archive members | 0 (plain git tree) | P |
| Units / variant | 396 `agent_execution` / `v1.k14` 396 | I |
| Executions | 396 | `tools/readme_corpora.toml` (full import); I; R totals (144+144+27+27+27+3×9) |
| Corpus digest (runs/) | `a8f4a9d7…` (recipe in P) | P; V §1 |
| Messages system / user / assistant / tool | 396 / 396 / 1,621 / 1,390 | V §2; I cross-checks |
| Tool calls (ids unique) / parallel turns / tool-free runs | 1,390 / 103 / 5 | V §2 |
| Messages per file | 3–47 (mean 9.60) | V §2 |
| `MANDATE_DECLINE` tool messages / inferred allows | 240 (env 49, intent 191) / 143 (6 + 137) | V §3.4; P quirk; A `mandate.art.*` |
| Injection dicts with 1 entry / empty | 369 / 27 | V §2 |
| Vector ids incoming_transaction / landloard_notice / bill_text / address_change | 243 / 63 / 45 / 18 | V §2 |
| `ValueError` tool errors (baseline only) | 4 | V §3.4 |
| `benchmark_version` v1.2.1 / `agentdojo_package_version` 0.1.35 / run `error` null | 396 / 396 / 396 | V §2; P quirk |
| `placeholder_args` present and null | 1,390 | P quirk |
| Null final assistant content / unexecuted trailing calls | 0 / 0 | P quirks |
| Payload-unreachable (vector, run) pairs | 23 | A `agentdojo.art.payload_not_reaching_agent`; V §3.5 |

## 3. Expected arms (L1-05)

Facets: model × pipeline (defence) × attack × suite. One model, one suite (banking v1.2.1).

| Pipeline dir | Defence | important_instructions | tool_knowledge | none (injection-task pre-pass) |
|---|---|---:|---:|---:|
| `gpt-4o-2024-05-13` | none | 144 (user_task_0..15 × injection_task_0..8) | 27 (user_task_0..2) | 9 (injection_task_0..8) |
| `gpt-4o-2024-05-13-mandate_envelope` | mandate_envelope | 27 (user_task_0..2) | **0** | 9 |
| `gpt-4o-2024-05-13-mandate_intent` | mandate_intent | 144 | 27 (user_task_0..2) | 9 |
| `…-mandate_scoped` | mandate_scoped | **0** | **0** | **0** |

Expected missing cells (not a defect of our import): scoped (in code and in R's commands, never released); envelope/TK;
TK and envelope-II for user_task_3..15; benign `user_task_*/none` runs (the runner makes none); the unreleased runs of §6
lead 1. Expected extra cells: none. Path components equal in-file fields in 396/396 (V §2).

## 4. Expected outcome rates (L2 outcome sanity; L1-05 raw census)

Metric mapping: ASR = share of attacked runs (`attack_type` non-null) with logged `security == true` (AgentDojo: injection
goal achieved); utility under attack = share with `utility == true`. In the AER these are the `security`/`utility`
judgements (origin rule `agentdojo.checker_outcome`, twin under item 3); pre-pass `security` is the runner constant
(`agentdojo.benign_security_constant`, origin harness default) and is excluded from ASR; pre-pass `utility` means "the
injection goal is solvable as a user task".

| Arm (pipeline / attack) | n | ASR expected | Utility expected | Declines | Source |
|---|---:|---:|---:|---:|---|
| baseline / II | 144 | 75.0% (108) | 81.9% (118) | 0 | R headline table; V §3.4 |
| baseline / TK | 27 | 70.4% (19) | 66.7% (18) | 0 | V §3.4 (not in R) |
| baseline / none | 9 | constant | 9/9 | 0 | V §3.4 |
| envelope / II | 27 | 11.1% (3; user_task_0/1/2 × injection_task_7) | 29.6% (8) | 39 | R (ASR); V §3.4 |
| envelope / none | 9 | constant | 1/9 | 10 | V §3.4 |
| intent / II | 144 | 1.4% (2; user_task_13/15 × injection_task_7) | 68.8% (99) | 144 | R headline table; V §3.4 |
| intent / TK | 27 | 0/27 | 33.3% (9) | 38 | R (ASR); V §3.4 |
| intent / none | 9 | constant | 9/9 | 9 | V §3.4 |

Not comparable with this corpus (no logs): R's comparator rows (AgentDojo arXiv v1 Table 5, all suites) and the baseline
range 75.0–88.9%.

Thresholds: **L1 raw census** of the logged booleans per arm: zero tolerance (any count different from the table is a
finding). **L2 sample**: about 5 per stratum, so no arm reaches 20 sampled executions; the 15 pp rule cannot fire; the
sample rate is reported with a Wilson 95% interval and flagged only if that interval excludes the table rate by more than
5 points. Additionally, every sampled AER judgement must equal its raw boolean (zero tolerance).

## 5. Known quirks (expected-known findings)

| Id / item | Expected | Source |
|---|---|---|
| `agentdojo.art.injection_task_as_user` / quirk `injection_task_as_user_task_prepass` | 27 files | A; P |
| `agentdojo.art.benign_security_constant` | 27 | A; P |
| `agentdojo.art.calls_derived_from_messages` (accounting unverifiable) | 396 | A; I |
| `agentdojo.art.naive_timestamp` | 396 | A |
| `agentdojo.art.payload_not_reaching_agent` | 23 | A |
| `agentdojo.art.defence_benign_intervention` (envelope declines in 8 of 9 pre-passes) | 8 | A; FA §8 row 10 |
| `agentdojo.art.silent_rerun` | 0 null-final logs (earlier passes unobservable) | A; P |
| `mandate.art.gate_decline` / `mandate.art.allow_inferred` | 240 tool messages / 143 decisions | A |
| quirk `args_mutated_in_place` | 391 (= 396 − 5 tool-free) | P |
| quirk `package_version_not_code_identity` | 0 files without version | P |
| Seal issues | `accounting_unverifiable` 396, `earlier_attempts_unobservable` 396, nothing else | I; FA §3.1 |
| Completeness / status | `unverifiable` 396 / `ok` 396 | I |
| Identity | model `gpt-4o-2024-05-13` (rule `mandate.model_from_pipeline_name@1`, I), defence `mandate_envelope`/`mandate_intent`; 0 `identity_unresolved`; pipeline-name collision with AgentDojo upstream handled by source-qualified ids | P; FA |
| Empty-recipient declines | 35 (`update_scheduled_transaction` without `recipient`) + 1 literal `"null"` | V §3.4 |
| Cross-corpus | 0 raw objects or `ex` shared with any other stored corpus; 180 baseline cells overlap agentdojo head cells, 0 identical | `dtap-sample-check-data/g02-overlap.json`; V §3.3 |
| Registry claims | must not claim `paper_reproduction`, `llm_params`, `timezone` (NC-MAN-01/03) | `registry/claims.py` |

## 6. Check map

| Check | Applies | Expectation / reason |
|---|---|---|
| L1-01 counts | yes | §2: 401 listed, 396 selected, 4 context, 1 not selected; 0 archives |
| L1-02 strict parse | yes | 0 failures of every class (E2: all raw objects strict-parse; floats present, 0 integers beyond I-JSON) |
| L1-03 encodings/escaping | yes | 0 U+2028/2029/0085, C0/C1, bidi, tag, zero-width, U+FFFD, mojibake (E2 U03–U05 Mandate 0); literal-escape residues limited to YAML/repr tool outputs and payloads (E2 U06 Mandate 16 literal / 11 wholly escaped strings, derived files) |
| L1-04 duplicates | yes | 0 byte-identical files; 0 identical trajectories within the part (396 distinct timestamps, 1,390 unique call ids); 0 cross-part/cross-corpus raw repeats |
| L1-05 arm coverage | yes | §3 cells exactly; outcome booleans per arm equal §4 (zero tolerance) |
| L1-06 secrets/account paths | yes | 0 real secrets, 0 account paths (E2 U14 Mandate 0/0); benchmark-synthetic credentials (e.g. `update_password` arguments) are fixture data, counted, never printed |
| L1-07 timestamps | yes (per unit only) | `evaluation_timestamp` 396/396, format `%Y-%m-%d %H:%M:%S`, naive (no zone), 396 distinct, range 2026-08-16 17:16:05 → 2026-08-17 ≈10:45 local; durations 0.85–33.48 s; within-unit monotonicity not applicable (one timestamp per log) |
| L1-08 degenerate | yes | 0 empty/tiny files, 0 zero-message logs, 0 run errors, 0 null final contents, 5 tool-free runs (expected, not degenerate) |
| L2 selection | yes | stratum = `pipeline_dir × attack_dir` (8 strata, §3); 5 per stratum → **40 units** (≥ 30 minimum) |
| L2 import / validate all tiers / recompute dry-run | yes | 40 mapped, 0 failed, 0 degenerate; tiers pass incl. item-10 ordering/C51/C26 checks; recompute 0 differences on the scratch corpus |
| L2 determinism (second import, other `--jobs`) | yes | byte-identical trees |
| L2 `verify --level chain` | yes | passes on a sealed scratch copy |
| L2 A2 error classes | yes | finish reasons `not_recorded`; 0 empty assistant turns (E2 A03 Mandate 0); 4 tool `ValueError`s in baseline only |
| L2 A3 PROV issue classes | yes | 0 dangling/missing relations; no PROV time (TraceLogger); 0 unexecuted calls; declined calls have **no** tool execution and the decline message is generated by the gate decision |
| L2 evidence classes | yes | see §7 delta (D share falls, I twins appear) |
| L2 identity | yes | §5 identity row |
| L2 redaction | yes | no account path in AER/SEM/PROV in any form (Inspect redaction tables D-182 not applicable to this family) |
| L2 withholding | **no** | profile has no `[withhold]`; nothing withheld at p10 |
| L2 outcome sanity | yes (descriptive) | §4 thresholds |

## 7. Expected movement since E2 (p10 corpus, `afe7038`, profile @1, `suites@1`)

| Change (RB item / decision) | Expected effect on Mandate at re-import on current code |
|---|---|
| Raw (same pin) | raw objects and origins byte-identical to p10 (400 objects; 0 changes) |
| Item 30 / D-31 bumps | every AER header changes: profile v2 (+ sha256), `rules` agentdojo 2; SEM/PROV follow through `aer_digest` (396/396) |
| Item 3 (D-80) + item 1 (D-86 addendum) | AER cites `_unverified` twins (I) for rules whose code is only at `c274885` (e.g. `checker_outcome` 396, `tool_msg_is_one_execution` 391, `benchmark_from_dialect`, `user_is_simulated`, `system_prompt_from_harness`, `messages_append_ordered`, `assistant_msg_has_one_call`, `tool_status_from_error`, `call_id_unique_match`, `benign_security_constant`); stay D: `dos_security_rule`/`injection_task_as_user_task` (27), `args_are_effective`, `log_holds_last_pass`, `naive_local_timestamp`, `system_prompt_variant_digest`, `environment_loaded_with_injections`, `mandate.decline_prefix`. R07b: 0 D citations on unverified code. Completeness unchanged (396 `unverifiable`) |
| Same | evidence shift vs FA (AER `evf` O 3,332 / D 11,997 / I 3,321; PROV core share 0.59): D count falls, I rises, core share falls; no core statement I |
| Item 5 (D-370) | 369 `agentdojo:load_environment` activities (one per attacked log, one fixture each), class D; PROV `used(ac0, fx)` 369 + association with `bench` |
| U6-c (D-373) | `/params` `not_recorded` on 1,621/1,621 model calls; +1,621 `apv:Gap` (E2: 5,552); stats `sampling` undeclared 396 → 0 |
| Items 4/6/8 (`suites@2`) | 1,296 markers: present 361 / absent 935 / ambiguous 0 unchanged; `partial_payload` 0; `success_without_visible_payload` 0 (RB measured on the whole corpus); SEM rules stay D |
| Item 14 (D-87), item 1 B1, items 2/12/16/25/28, D-182, BF-21/22/28 | 0 Mandate executions affected |
| Item 10 | new tier-4 ordering/C51/C26/cycle checks: 0 failures (E2 P01–P04 Mandate 0) |
| Item 15, item 1 catalogue | `agentdojo` catalogue digest moves in every PROV |
| D-410 (perf) | no output bytes (only stage code digests) |
| CD-23 (held, regen 43-56) | 0 effect expected: every tool message follows its assistant call (1,225/1,225 turns, V §2) |
| D-430 | stored p10 corpus cannot recompute at main (drift report); the pre-check uses fresh scratch imports |

## 8. Hypotheses (falsifiable, with thresholds)

| # | Hypothesis | Fails if |
|---|---|---|
| H1 | Raw counts and digest equal §2 | any count differs or `corpus_digest` ≠ `a8f4a9d7…` |
| H2 | Arm cells and per-arm outcome counts from raw equal §3/§4 | any cell count or boolean count differs by ≥ 1 |
| H3 | Unreleased runs (R: "every reported run") are absent: 0 scoped files, 0 envelope/TK files, exactly one file per (pipeline, user task, attack, injection task) | any scoped/extra file, or any duplicate cell |
| H4 | Banking security is state-based (#189 not applicable): every attacked log with `security == true` has ≥ 1 executed (non-declined) consequential call; 0 such logs where all consequential calls were declined | ≥ 1 counter-example |
| H5 | #181 bias is measurable: among baseline attacked logs on injection_task_0/1/3 with `security == true`, count those whose attacker-bound transfer subject lacks the target datum | reported as a count; any count > 0 is an S2 disclosure (source-defect, upstream) |
| H6 | #161: user_task_5 utility is true in logs where no new Spotify payment executed | reported as a count; > 0 is an S2 disclosure |
| H7 | Timeline: 396 distinct naive timestamps forming 5 non-overlapping blocks on 2026-08-16/17, all before the commit (16:22:22Z) under UTC−5 | any overlap, tie, zone marker or value after the commit under UTC−5 |
| H8 | 0 identical trajectory fingerprints within the part and 0 across corpora (agentdojo head overlap: 0 identical of 180 cells) | ≥ 1 identical pair |
| H9 | L2: 40/40 mapped, 0 degenerate, seal issues exactly the two info codes, 240-decline facts hold on sampled logs (deny decision citing `mandate.decline_prefix@1`, no execution for the call) | any other issue code, any declined call with an execution |
| H10 | L2 delta: §7 rows hold on the sample (header versions, twins as listed, `/params` unk on every model call, `load_environment` on every attacked sampled log, markers unchanged) | any sampled execution deviating |
| H11 | L2 determinism and recompute: 0 byte differences; 0 account paths; 0 secret values in AER/SEM/PROV | ≥ 1 |

Rule reminder: no exclusion or recommendation to exclude any arm for having no successful attack (intent/TK 0/27 stays).

## Fact-check (2026-10-14, desk only, no raw data read)

Checked against primary sources (GitHub API, the pinned README/LICENSE/harness/requirements, PyPI JSON, AgentDojo
v0.1.35 source and issue tracker, arXiv 2406.13352 v1/v2/v3 HTML, the AgentDojo leaderboard) and our own reports
(profile, corpus-spec, `import-cli-mandate.json`, E2, verify §2–§3.6):

- **Confirmed:** pin `fa62a977` is the only commit (author time 11:22:22 −0500), main = pin, 0 tags/releases/issues/PRs/
  forks, owner a User account created 2026-05-19; listing 401 files / 3,137,054 B, `runs/` tree `11b6d0e4` 396 blobs /
  3,103,968 B, not truncated; §3 cells and user-task sets equal the tree listing; LICENSE MIT (Mandate Labs, 2026),
  AgentDojo MIT; wheel sha256 `364bea42…` (uploaded 2025-10-27T18:11:04, 0.1.35 still latest, requires `openai>=1.59.7`);
  temperature 0.0 is sent as `temperature or NOT_GIVEN` (so not sent); `force_rerun=True` and fixed logdir; harness
  docstring "81.5% -> 11.1%"; README headline numbers (75.0/81.9, 1.4/68.8, TK 0/27, envelope pilot 11.1%); AgentDojo
  issue states and subjects for #110/#130/#138/#139/#159/#161/#168/#181/#189/#194/#218; the #181 precedence pattern is
  present in both v1 and v1_2 banking InjectionTask0/1/3 at v0.1.35; v1.2.1 banking = `get_new_version((1,2,0))`;
  §4 outcome table equals verify §3.4 and the import report's cross-checks (declines 240 = 49 + 191, allows 143);
  E2 records 11,728 / 11,390 / 396 and markers 361 / 935; executions 396 = 144+144+27+27+27+27.
- **Corrected:** arXiv 2406.13352 **v2** (2024-07-18) already carries the leaderboard/v3 Table 5 values; only **v1**
  equals the README comparators (research.json papers and discrepancy lead). Added: Table 5 no-defence targeted ASR
  53.10% (v1) / 57.69% (v2, v3) next to the leaderboard's 47.69%; the README's "~33%" matches none and stays unverified.
- **Unverifiable here:** publisher identity (two GitHub organisations named Mandate Labs exist, unlinked to `jwilliamsc`);
  that the missing pilot/variant runs were overwritten rather than never copied (inferred); the served model snapshot.
- No expectation in §2–§8 changed; no new expectation was derived from data.
