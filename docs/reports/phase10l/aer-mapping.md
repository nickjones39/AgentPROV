# Phase 10l, part A: proposed AER mapping of `drift.k18.*` (D-270..D-279, proposals)

Status 2026-10-13: **user-approved** (D-270..D-279 in DECISIONS.md), implemented on `phase-10l-drift` (spec D.6.19).
One refinement from the code, applied in the implementation: the isolation decision of D-274 goes on the **last** tool
message of each call batch only (`census.md` §5). Evidence: [`census.md`](census.md), the DRIFT
code at `SaFo-Lab/DRIFT@6fd3df47` (read as data), `investigation/sources/drift.md` and `verify/drift.md`, spec D.6.4–D.6.8,
C.3.7 and C.5.5. Part B starts only after these are decided, and its code lands only after the regeneration-batch entry
(§8) is approved.

## 1. Summary

- One DRIFT build module in the agentdojo family maps both variants (`drift.k18.conversations`, `drift.k18.messages`)
  for every source. The adapter id stays `agentdojo.tracelogger`, so execution ids, headers and the AgentDyn profile
  work as the spec already says (D.6.5); the entry needs a three-line dispatch in the existing `mapper.py` (routed).
- New rules go in a new `drift` catalogue file (`rules/drift.rules.toml`; the namespace is already homed in the core).
  Generic AgentDojo-harness rules are reused with their existing `_unverified` twins.
- No DRIFT log records the code that wrote it, and every producer ran before or beside the code at its pin, so every
  shipped DRIFT profile has `verified_code = []`: **each statement that rests on reading DRIFT or AgentDojo code is
  class I** (through a twin). What stays O: the logged values. What stays D: nothing harness-dependent.
- Defence-authored structures: the CALL ERROR `user` messages (a validator `deny`), the isolation pass over every tool
  output, the plan and privilege map. The defence's own LLM calls are **not** invented as records.
- Nothing needs `aer/`, `prov/`, `validate/`, `corpus/`, `runner/`, `raw/` or `ingest/` (invariant 5).

## 2. Where the code goes

**D-270. A new build module behind the existing mapper (recommended).** `adapters/agentdojo/drift_mapper.py` (new) holds a
self-contained build for the DRIFT variants. It reuses the family's public machinery (profile `FamilyTable`,
`identity.resolve`, `layout`, `citation.citations`, `history_table`, the quirk-hook API, `aer.canon` lexical hints) and the
small helpers of `mapper.py`. `TraceLoggerMapper.map` hands `drift.k18.*` items to it, and `accepts`/`MAPPED_VARIANTS`
list the two variants. **Routed edit** (owner: the regeneration-batch session, via the orchestrator): `mapper.py`
(dispatch in `map`, `accepts`), `dialect.py` (`MAPPED_VARIANTS`, the module table). Byte-neutral for every other variant.
- *Rejected:* (a) a separate mapper id `agentdojo.drift`: the adapter id and the execution-id prefix would depart from
  D.6.5, and AgentDyn part `c` would need a second profile in the `agentdyn` corpus; (b) subclassing the private
  `_Build`: it would couple to about 1,400 lines another session owns, and DRIFT differs in almost every step (message
  key, no `injections`/`error`, no fixtures, single pass, the user rows, the isolation step); (c) a hook-only
  implementation: hooks cannot change the structural reads that make `_Build` refuse DRIFT files.

**D-271. Rule home: a new `drift` catalogue.** `rules/drift.rules.toml` (new file; version 1). `drift` is already in the
core's `CATALOGUE_HOMES` (`aer/rules.py`) and in `citation.NAMESPACES`, and D.5.4 lists `drift.*` rule ids. The
`agentdojo` catalogue gets **no** new entry: every generic rule the mapping needs exists with its twin (§4.1).
- *Alternative* (the brief's wording, "rules in the agentdojo catalogue"): put the same rules in `agentdojo.rules.toml`
  as `agentdojo.drift_*`. Rejected because it departs from D.5.4's ids and makes every non-DRIFT PROV carry them in the
  `agentdojo` catalogue digest (which would move anyway, but for unrelated rules).

## 3. Record-by-record mapping

Pointers below are into the source object; `M` is `conversations` or `messages` (the mapper's source locators use the
variant's key, never a hard-coded `/messages`). "I (twin)" = a D rule cited through its `_unverified` twin (D-24).

| AER | Content | Class | Rule(s) |
|---|---|---|---|
| `execution.dialect` | `{agentdojo.tracelogger, drift.k18.<key>}` | — | — |
| `execution.unit` | `agent_execution` (no empty message list exists; min 2) | — | — |
| `task.benchmark` | from the profile's suite table (`banking/slack/travel/workspace` → `agentdojo`; `dailylife/github/shopping` → `agentdyn`) | I (twin) | `agentdojo.benchmark_from_dialect@1` |
| `task.suite/task_id/attack_id/attack_target_id` | `suite_name`, `user_task_id`, `attack_type`, `injection_task_id` | O config | — |
| `task.defense_id` | `drift` | I | `drift.defence_from_keyset@1` (twin); AgentDyn C: the table row (`agentdyn.pipeline_dir_registry@1`) |
| `ext.drift.config` | the four flags verbatim | O source | — |
| `ext.drift.tool_permission` | the map verbatim | O source | unscoped `drift.tool_permission_per_process@1` (twin): LLM-assigned once per process, not per run |
| `ext.drift.plan` | `{trajectory, checklist}` verbatim | O source | — |
| `ext.drift.plan_semantics` | `initial_plan` or `final_plan_state` (D-276) | I (twin) | `drift.plan_fields_semantics@1` |
| `ext.drift.total_tokens` | verbatim | O source | unscoped `drift.total_tokens_scope@1` (twin): every DRIFT LLM call of the run |
| `ext.agentdojo.pipeline_name`, `extra` | as the generic mapper (drift-1's PACT keys land in `extra` with the info issue) | O | `agentdojo.tracelogger_record_shape@1` |
| `instrumentation` | `unk not_recorded` | — | — |
| actor `bench` | `version` = `benchmark_version` (O); `ext.agentdojo.version_label_semantics` per suite (D-278); `unk /code` | O / I | `agentdojo.version_label_semantics@1` |
| actor `user` | `simulated_user` | I (twin) | `agentdojo.user_is_simulated@1` |
| actor `agent` | `model.requested` from identity (D-278); `unk /model/served, /model/provider, /params` | I | identity rule |
| actor `env` | `agentdojo.FunctionsRuntime` (AgentDojo 0.1.35 `ToolsExecutor`) | I (twin) | `agentdojo.functions_runtime@1` |
| actor `att` | iff `attack_type` non-null | O config | — |
| actor `def0` `drift` | `kind: defense`; `unk /model, /version not_recorded` | I | as `task.defense_id` |
| scope `run` | `t.dur_s` = `duration`, `dur_clock: wall`; `unk /t/start, /t/end, /status` | O source | unscoped `drift.duration_scope@1` (twin; not `agentdojo.duration_scope@1`, which cites AgentDojo's logger) |
| scope `att0` | `index: 0`, `scored: true`; **no** earlier-attempt issue | I (twin) | `drift.single_pass@1` |
| fixtures | **none**; info issue `drift.injection_map_not_recorded` | — | `drift.no_injection_map@1` (twin) |
| `m0` first `user` | actor `user` | I (twin) | `agentdojo.user_is_simulated@1` |
| CALL ERROR `user` `m<i>` | D-273: `dc<n>` (actor `def0`, verdict `deny`, subject = the preceding assistant message, `reason` = the content verbatim, `ext.drift.check` ∈ `trajectory`/`checklist`), then `m<i>` role `user` kept, actor `def0`, `generated_by: dc<n>` | I (twin) | `drift.call_error_user_is_validator@1`, `drift.call_error_check@1` |
| any other later `user` | generic row (actor `user`, I, issue `unattributed_additional_user_message`); 0 observed | I | `agentdojo.additional_user_message_unattributed@1` |
| `system` | generic row; 0 observed; `drift.no_system_message@1` cited on the header (twin) | — | — |
| assistant `mc<n>` | actor `agent`, `role: agent`, `status: kept`, **`unk /input not_recorded`** (DRIFT's prompt and plan state are not logged) plus `/request…/usage` as usual; info issue `drift.agent_prompt_not_recorded` once per file | I (twin) | `agentdojo.assistant_msg_has_one_call@1` |
| assistant `m<i>` | text part O; `ext.drift.text_form` ∈ `reserialised`/`raw` (template full match) | O; I (twin) | `drift.assistant_reserialised@1` |
| `tool_call` parts | `name`, `args`, `provider_call_id` verbatim; `unk /args_raw`; unscoped `agentdojo.args_are_effective@1` (twin; 0.1.35 mutates args in place) | O | as generic |
| final assistant with call text and empty `tool_calls` | issue `drift.calls_in_text_not_executed` (detail `reserialised` or `raw`), no parts (D-277) | I (twin) | `drift.calls_in_text_not_executed@1` |
| tool `te<k>` | actor `env`, `call` = the part by id, `name`, `args`, `args_effective` = args, `status` from `error` (`invalid` for `Invalid tool`/`ValidationError`, else `error`), `unk /returned not_recorded, /t` | I (twin) | `agentdojo.tool_msg_is_one_execution@1`, `agentdojo.tool_status_from_error@1`, `agentdojo.call_id_unique_match@1` |
| isolation `dc<n>` | D-274: per tool message, actor `def0`, subject `te<k>`, verdict `other` + subtype `drift.isolation_pass`, `unk /original ambiguous, /reason not_recorded` | I (twin) | `drift.tool_output_post_isolation@1` |
| tool `m<i>` | role `tool`, part `tool_result` (`responds_to` the call by id, `text`, `error`), `generated_by: dc<n>`, actor `def0` | I | as above |
| `after` edges | generic: `pos` between messages, `causal` to the generator | I (twin) | `agentdojo.messages_append_ordered@1`, `aer.output_after_generator@1` |
| `j0`/`j1` | `utility`/`security` O benchmark, origin `checker` (`unk /inputs`); benign `security` origin `harness_default` | I (twin) | `agentdojo.checker_outcome@1`; benign: `drift.benign_security_constant@1` |
| times | none (D.6.8). Run-time stamps in tool outputs stay content | — | — |

## 4. Rules

### 4.1 Generic rules reused (all exist, all with twins where class D)

`agentdojo.benchmark_from_dialect`, `user_is_simulated`, `functions_runtime`, `messages_append_ordered`,
`assistant_msg_has_one_call`, `tool_msg_is_one_execution`, `call_id_unique_match`, `tool_status_from_error`,
`args_are_effective`, `checker_outcome`, `empty_assistant_text_ambiguous` (D with twins); `version_label_semantics`,
`pipeline_dir_is_model_identity`, `context_is_prefix` (not cited: `/input` is `unk`), `additional_user_message_unattributed`
(I); `agentdojo.tracelogger_record_shape@1`, `unexecuted_trailing_calls@1`, `log_path_layout@1` (cited by issues only, as
now); `agentdyn.variant_c_rekey@1`, `agentdyn.pipeline_dir_registry@1` (I) for AgentDyn C.

Not cited for DRIFT: `log_holds_last_pass`, `null_final_implies_three_passes`, `agentdyn.last_assistant_content_none_max3`
(single pass), `benign_security_constant` and `duration_scope` of `agentdojo` (they cite AgentDojo's own suite and logger
code, which DRIFT replaces), `naive_local_timestamp` (no timestamp), `payload_attributed_to_attacker` (no fixtures).

### 4.2 New `drift` catalogue

| Rule | Class | Twin | Statement (short) | Code cited (DRIFT `6fd3df47` unless stated) |
|---|---|---|---|---|
| `drift.defence_from_keyset` | D | yes | a file with the DRIFT key set was written by DRIFT's `pipeline_main.py`, so DRIFT was the defence | `pipeline_main.py` (`json.dump`) |
| `drift.single_pass` | D | yes | one pass: `model_output_from_messages` never returns `None` | `DRIFTTaskSuite.py` |
| `drift.duration_scope` | D | yes | `duration` = wall time around `run_task_with_pipeline` (environment load, the pass, the checker) | `pipeline_main.py` |
| `drift.total_tokens_scope` | D | yes | `total_tokens` = all DRIFT LLM calls of the run, not the agent's | `pipeline_main.py`, `client.py` |
| `drift.tool_permission_per_process` | D | yes | LLM-assigned once per process (suite invocation) | `DRIFTLLM.query`, `function_privilege_assignment` |
| `drift.plan_fields_semantics` | D | yes | the plan fields hold the initial plan (`initial_*`, from `1af2672`/`5f7c1a9`) or the end-of-run state (before) | `pipeline_main.py` at `53dbc6c5` and `6fd3df47` |
| `drift.no_system_message`, `drift.no_injection_map` | D | yes | the pipeline has no `SystemMessage`; no `injections` are written | `pipeline_main.py` |
| `drift.call_error_user_is_validator` | D | yes | a `user` message in the `</function_error>` wrapper holding `[CALL ERROR]` is the validator's refusal of the preceding turn's calls, which were not executed | `DRIFTLLM.trajectory_constraint_validation`, `checklist_constraint_validation` |
| `drift.call_error_check` | D | yes | the two refusal texts name the failed check (trajectory or checklist) | same |
| `drift.assistant_reserialised` | D | yes | text matching the exact template is the re-serialisation of the parsed completion; text outside the tags was dropped | `DRIFTLLM._parse_model_output` |
| `drift.calls_in_text_not_executed` | D | yes | a final assistant turn whose call text is non-empty and whose `tool_calls` is empty proposed calls that were not executed (de-duplicated, cut by the cap, or unparsed) | `DRIFTLLM.query` |
| `drift.tool_output_post_isolation` | D | yes | every tool output passed DRIFT's isolation step before the next agent call, which may have deleted text in place | `DRIFTLLM.query`, `injection_isolate` |
| `drift.benign_security_constant` | D | yes | without an injection task `security` is the constant `True` | `DRIFTTaskSuite.run_task_with_pipeline` |
| `drift.proposed_calls_reparsed` | — | — | **reserved** (re-parsing proposed calls; D.6.6 row, AD-10) | — |

Issue codes (in the `drift` catalogue): `drift.injection_map_not_recorded` (info), `drift.agent_prompt_not_recorded`
(info), `drift.calls_in_text_not_executed` (warning), `drift.plan_semantics_contradicted` (warning, D-276),
`drift.call_error_unrecognised` (warning: a CALL ERROR whose text matches neither check; 9 drift-1 messages).
Subtype `drift.isolation_pass` (for `verdict: other`, D-274).

Code citations: the AgentDyn-vendored copies are byte-identical for `pipeline_main.py`, `DRIFTTaskSuite.py`, `client.py`
(verified by blob id in `verify/drift.md` §7), and differ for `DRIFTLLM.py`; each rule cites the files it reads at the
commits where the cited behaviour is present.

## 5. Decisions D-272..D-279

**D-272. Evidence classes.** Every rule of §4.2 is class D citing DRIFT code, with an `_unverified` class-I twin; every
DRIFT-format profile sets `verified_code = []` (`code_identity = "range"` for DRIFT head and history: the runs predate
or sit between the pinned commits; `"unpinned"` for AgentDyn C, Figshare, EnvironmentOptim and drift-1, whose
producing code is not released at a matching state). Consequence: all harness readings above are class I and go to the
inference bundles; the O values (texts, calls, args, ids, flags, plan, map, tokens, duration, outcomes) stay O.
- *Why:* D-24; no record names its code, and the census dates AgentDyn C before DRIFT's `1af2672`.
- *Rejected:* declaring DRIFT head `verified` at `6fd3df47` (the head runs were committed on 2026-02-14 and 2026-04-18;
  the stamps put the AgentDojo-suite runs between `763a7d6` and `336dca9`, `verify/drift.md` §3).

**D-273. CALL ERROR as a validator denial.** For each CALL ERROR `user` message: a `decision` `dc<n>` (actor `def0`
`drift`, verdict `deny`, subject = the preceding assistant message, `reason` = the message content verbatim with its
locator, `ext.drift.check` from the template), then the message itself (role `user` kept, actor `def0`,
`generated_by: dc<n>`), as the D.6.6 row already says. The subject is the message, never a part: the refused calls
exist only as text (the validator empties `tool_calls`, 11,013 of 11,013). No `tool_execution` is emitted for them.
- *Rejected:* subject `unk` (the refused turn is known); parsing the text into `tool_call` parts first (D-277).

**D-274. The isolation step: one decision per tool output (recommended).** C.5.5 names DRIFT isolation as "executed,
output replaced in place". The logs cannot say which outputs were edited, so per tool message: the `tool_execution`,
then `dc<n>` (actor `def0`, subject the execution, verdict `other` with subtype `drift.isolation_pass`, `unk
{"/original": "ambiguous", "/reason": "not_recorded"}`), then the tool message `generated_by: dc<n>`. `ambiguous`
because the original is either the recorded text or overwritten, and nothing tells which.
- **Downstream:** SEM `agentdojo.suites` keeps a tool's integrity label only for a message generated by a `redact`
  decision; with `other` it falls back to `unknown` for every DRIFT tool output. A small SEM change (treat
  `drift.isolation_pass` like `redact` for the tool label) is **routed** to the regeneration-batch session (owner of
  `semantics/suites.py`). DRIFT logs have no payload fixtures, so no injection marker is computed either way.
- *Alternative (b):* no decision; the message stays `generated_by` the execution and carries
  `ext.drift.content_state = "post_isolation"` (I). Simpler and SEM-neutral, but it leaves a possibly edited output
  attributed to the environment alone, against C.5.5.
- *Rejected:* `verdict: redact` or `modify` on every output (asserts edits that mostly did not happen); a heuristic
  `redact` where an `important_instructions` frame lost its GOAL (attack-template specific; belongs to SEM,
  regeneration-batch item 6).

**D-275. What DRIFT does not log stays unknown.** The agent's model call gets `unk /input not_recorded` (DRIFT's tool
prompt, guidelines and plan state are not in the record; the `conversations` list is not the prompt). The defence's
own LLM calls (planner, detector, judge, formatter, privilege assignment, parse retries) get **no** records: their
number per run is not recoverable (the detector loops, retries are conditional), and `total_tokens` covers them only as
a sum. The assistant text form is stated (`ext.drift.text_form`), and the raw completion of a re-serialised turn is not
claimed (`mc /response` is `not_recorded` already). Accounting `agent_calls_vs_assistant` stays `unverifiable`.
- *Rejected:* one placeholder `model_call` per sub-call kind (would invent counts and order).

**D-276. Plan fields: semantics per part, checked per file.** The profile declares `drift_plan_fields_by_commit` with a
`params.semantics` per part or selector: `initial_plan` for DRIFT head, AgentDyn D, Figshare, drift-1's new runs;
`final_plan_state` for DRIFT history and AgentDyn C (and its EnvironmentOptim copies). The mapper writes
`ext.drift.plan_semantics` from it and checks each file where the data can contradict it: raw planner text (a checklist
that starts with the planner's newline) under `final_plan_state` raises `drift.plan_semantics_contradicted` and writes
no `plan_semantics` (never "fixed"). The check is one-directional: under `initial_plan` the raw planner text may itself
be JSON (22 Figshare files) and an initial plan may cover every executed call, so the data cannot refute it. The census
shows 0 contradictions with this split. Staleness across tasks (§5.4 of the source card) is a
datasheet statement, not a field.

**D-277. Proposed but not executed calls.** v0.1 does not re-parse call text into `tool_call` parts (the rule stays
reserved; it needs a stdlib port of AgentDojo's `ast_utils` grammar). Final turns with non-empty call text and empty
`tool_calls` get the issue `drift.calls_in_text_not_executed` (detail `reserialised`: de-duplication; `raw`: the
20-message cap or a failed parse). CALL ERROR turns are covered by D-273. Partial drops inside an executed turn are
**not** flagged in v0.1 (counting them needs the same parser; the name-regex upper bound is 15–209 turns per source):
a datasheet limitation.

**D-278. Identity, benchmark label, outcomes.**
- Identity: DRIFT head/history, Figshare and drift-1: `model_from = "model_dir"` (the directory equals `pipeline_name`,
  the requested model passed to DRIFT's client), `pipeline_name_policy = "verbatim_unreliable_when_differs"`, rule
  `agentdojo.pipeline_dir_is_model_identity@1` (I); drift-1's `gpt-4o-mini` stays the undated alias as logged.
  AgentDyn C and EnvironmentOptim copies: the existing AgentDyn table rows (variant C). The `drift` defence actor is
  added by the DRIFT build from the key set (merged with a table row's `drift`, never doubled). Provider: `unk`.
- `benchmark_version`: for the AgentDojo suites the label is the suite version DRIFT loaded
  (`get_suite(args.benchmark_version, …)`), so `version_label_semantics` is `suite_version`; for the AgentDyn suites it
  is `label_not_suite_version` (AgentDyn registers each suite under every version). This departs from the D.4.4 sketch
  (`cli_default_not_suite_version` for all) and makes Figshare's `v1.2.2` meaningful.
- Outcomes: `checker` origin; benign `security` is `harness_default` under `drift.benign_security_constant@1` (DRIFT's
  suite, not AgentDojo's).

**D-279. Sources, parts and ownership.**

| Source | Part (registry) | Files mapped | Owner of the profile | Status after part B |
|---|---|---:|---|---|
| `drift` (new registration) | `head` | 1,569 | this phase (`drift.profile.toml`) | `partial` (golden fixtures pass; full import in the regeneration round) |
| `drift` | `history` (`53dbc6c5`) | 1,046 | this phase | `planned`; licence policy `reference` (pre-licence blobs, R-2) |
| `agentdyn` | `c` | 4,258 | regeneration-batch session (existing `agentdyn.profile.toml`: DRIFT quirks for `variant = drift.k18.messages`) | `planned` → `partial` |
| `agentdyn` | `d` | 949 | — | stays `owned_elsewhere` (owner `drift`), byte-identical to `drift` head |
| Figshare 32657856 | DRIFT part | 2,847 | phase 10j (its profile; layout `runs_agentdojo_full_<arm>/<model>/`) | `select.dialect_planned` → `planned` |
| EnvironmentOptim | DRIFT part | 620 new + 4,258 copies (`select.owned_elsewhere`, owner `agentdyn`) | whoever profiles EnvironmentOptim (deferred in 10d) | `planned`; Q5 |
| drift-1 | DRIFT part | 626 new + 1,569 copies (`select.owned_elsewhere`, owner `drift`) | to be assigned (D-93 licence) | `planned` |

Each profile declares the `drift_*` quirks (ids `agentdojo.drift_*`, R-38) with its census counts as `observed`, and the
census functions reproduce them (hooks' `census` contract). The registry switch of part C (`select.dialect_planned` →
`planned`) is coordinated through the orchestrator for the parts other sessions own.

## 6. Requests that need the user's yes

- **R-1 (fetch): the 1,046 DRIFT history blobs.** Fetch the `runs/` blobs of `SaFo-Lab/DRIFT@53dbc6c58d5d1f044f3a68636be30b060bb86d34`
  from `https://github.com/SaFo-Lab/DRIFT` into the existing blobless clone `~/.agentprov/staging/10c/ref-drift/DRIFT.git`,
  as one batched object request (no checkout, no other paths), logged in `acquisitions.jsonl`. Estimated size:
  about 14 MB uncompressed (the 949 head AgentDojo-suite files are 12.9 MB), a few MB packed. Needed for the history
  census, its golden fixtures and a scratch trial. Without it the `history` part stays `planned` with numbers from
  `verify/drift.md` only.
- **R-2 (licence): the history part's policy.** The history blobs were committed (2026-01-31) and deleted (2026-02-14)
  before any licence statement (README badge 2026-04-19, LICENSE 2026-07-16). Recommendation: policy `reference`
  (registered, census and trial only, never in a released corpus), as the D.4.4 sketch says; alternative: treat the
  repository-wide MIT as covering history (include).
- **R-3 (optional fetch, Q5):** AgentDyn's history for `runs/gpt-4o-mini-2024-07-18-drift/` (blob ids only, metadata
  first) to test whether EnvironmentOptim's 620 new DRIFT runs are AgentDyn's superseded variant C generation. If they
  are, they belong to `agentdyn` · `history`, not to EnvironmentOptim.

## 7. Open questions

- Q1 (D-274): decision per tool output (a) or `content_state` only (b)?
- Q2 (D-271): `drift` catalogue (recommended) or `agentdojo.drift_*` entries?
- Q3 (D-278): accept `suite_version` for the AgentDojo suites' `benchmark_version`, against the D.4.4 sketch?
- Q4: drift-1 has 10 PACT files (`pact-gpt-4o-mini-banking10`) with six extra keys and a different defence
  (IFC/PACT-DRIFT). Map them as DRIFT with `extra` (generic) or exclude them as another producer?
- Q5: EnvironmentOptim's 620 (R-3).
- Q6: Figshare's DRIFT arms show an injection header in 123 of 2,847 attacked runs and no attack success. Report only
  (datasheet), or ask phase 10j to look at the deposit's harness before profiling?

## 8. Downstream effects (CLAUDE.md rule 10)

- **Family code digest:** new files in `adapters/agentdojo/` move `adapter_code_sha256` in the manifest of every
  AgentDojo-family corpus at its next import or regeneration. No existing AER byte moves: today every `drift.k18.*` file
  is unselected: a scan of the 24 stored corpora (2026-10-13) finds no `drift.k18` AER, and the AgentDyn corpus
  registers its DRIFT files as `select.dialect_planned` (4,258) and `select.owned_elsewhere` (949).
- **Catalogue digests:** a new `drift` catalogue appears only in PROV that cites it (DRIFT corpora). The `agentdojo`
  catalogue is unchanged (D-271).
- **Routed edits:** `mapper.py`/`dialect.py` dispatch (D-270), the AgentDyn profile's DRIFT quirks (D-279), the SEM tool
  label for `drift.isolation_pass` (D-274a). The routed SEM change moves the `agentdojo.suites` profile digest, so it
  reaches the SEM/PROV of every corpus using that profile: a separate regen-batch entry.
- **Goldens:** new golden AERs for DRIFT fixtures only; existing goldens, the compat gate and gate D unchanged.
- **Manuscript numbers:** about 10,966 more executions once imported; DRIFT's limits (post-isolation outputs, no
  sub-LLM calls, no payload map, no time) go to `datasheet-items.md`.
