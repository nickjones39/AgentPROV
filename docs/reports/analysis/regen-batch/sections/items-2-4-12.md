## Items 2, 4–12 and U6-a/b/c (session `regen-items-2-12`, started 2026-10-13; D-370..D-379)

Approved for implementation: items 2 and 4–12 on 2026-10-11, U6-a/b/c on 2026-10-13 (regen-plan F-2). Each item's
prediction is written here before its code; the outcome follows it. Catalogue and profile version integers and
`rules/archive/` are left to the D-31 bump branch of the regen-batch owner; nothing here bumps a version. No stored
corpus is touched: checks run on scratch clones under `~/.agentprov/migration-work/regen-items-2-12/`.

### Item 10 (E2-b1): event ordering, C51, C26 and cycle checks in tier 4

**Prediction (written before the code).**
- **Change:** `validate/constraints.py` gains four checks, run on the views it already uses (top, each bundle, each
  inference bundle's application view) and on the assessment bundle's application view:
  `pv.constraints.ordering` (the PROV-CONSTRAINTS event graph built from the relations, Inferences 9 and 11 and the
  ordering constraints whose events the relations name; a strongly connected component holding a strict edge, i.e. the
  Constraint 42 `wasDerivedFrom` generation order, fails), `pv.constraints.derivation_parts` (C51: a derivation naming a
  generation or usage without an activity), `pv.constraints.unique_start` (C26: two `wasStartedBy` of one activity by one
  starter under different identifiers) and `pv.constraints.cycles` (profile lints: a used/generated dependency cycle, a
  `wasInformedBy` cycle, a `specializationOf` ∪ `mentionOf` cycle, which C52's transitivity makes reflexive). The
  docstring's "not instantiable" (l. 17) and EF E.1.4's preamble bullet and its `C47 (no times: not applicable)` cell
  are corrected; K.10 already says Constraint 42 is checked.
- **Digests:** no AER, SEM or PROV byte. Every tier-4 row gains four check ids, so the validation row and its digest
  (`digests.validation`, the validation counts of `corpus.json`) change for every execution of every corpus at its next
  validate or derive; the `validate` stage `engine_code_sha256` and `fn_digest` move. Golden PROV, gate D, C.16 and the
  compat gate are unchanged. `docs/reports/migration/release-chain-2026-10-13/D.json` lists check ids and is a dated
  record; it is not regenerated.
- **Expected verdicts:** pass everywhere. Examination 2 (P01–P04) found no strict or non-strict cycle, no C51 and no
  C26 case in 1.78 million views of the eight corpora, over views (core ∪ all inference bundles, core ∪ assessment)
  that contain every view checked here. To be confirmed on a sample of each stored corpus after the change.

### Items 9 and 11 (B2 refresh; E2-b2): one completeness rule for import, derive and recompute (D-372)

**Finding (2026-10-13).** The importer applies H.3.2(2) as D-24/B6 amended it: a loss issue proves loss only when its
rule is class D (`proven_loss_codes`). `derive` and `recompute`, including the round's re-map (whose importer rows
`corpus/derive.py` replaces), compute the row with `corpus/facets.py` `completeness_of`, which does not. So the round
would have written ROPE 322, AgentDyn 825 and head 36 retries `known_incomplete`, not the `unverifiable` that items 3
and 13 predicted. The user approved fixing it in `corpus/facets.py` (2026-10-13, D-372).

**Prediction (written before the code).**
- **Change:** one function (`corpus/facets.py` `proven_loss_codes`), used by `completeness_of` and by the importer. A
  loss code counts only when an issue with that code cites a class-D rule, read from the catalogue at the version the
  AER header declares. `missing_tool_result` joins the loss codes (item 11), except a *declared removal*: an issue whose
  every listed execution generated an artefact keeps the result, so it proves no loss (item 16's react `submit` removal
  is the only such case; the user's choice "a declaration is not a loss", implemented on what the AER records, since a
  seal issue carries no severity).
- **No AER, SEM or PROV byte.** Index rows (`completeness`) and `corpus.json` `by_completeness` change at the next
  import, derive or recompute. The `adapters/runner` code digest (the `aer` stage `engine_code_sha256`) moves.
- **Per stored corpus** (census of every stored seal, 2026-10-13; counts are executions):
  - `ast-survey-agentharm`: 4 `missing_tool_result` (`inspect.tool_event_is_execution@1`, D), today
    `verified_complete` → `known_incomplete` (item 11, as examination 2 predicted).
  - ROPE 322, AgentDyn 826 and head 82 retries, and the 2024-06 47: the stored seals cite the D rules, so a re-derive
    from the stored AERs keeps `known_incomplete`; after the round's re-map they cite the twins where items 3/13 say
    so, and this fix makes them `unverifiable` exactly as predicted there (ROPE 322, AgentDyn 825, head 36). The
    `incomplete_run` executions (AgentDyn 12, head 1, 2024-06 4) cite `agentdojo.incomplete_run@1` (D) and stay.
  - No other stored seal holds `missing_tool_result`; item 9's B2 rows (head 232, ROPE 2, 2024-06) are refreshed by
    the same function at the re-map.
  - WhistleBench (trial only): its 9,195 declared submit removals stay `verified_complete`; its 18 genuine missing
    results become `known_incomplete`.

### U6-c: `/params` of TraceLogger model calls declared `not_recorded` (D-373)

**Finding.** The TraceLogger and DRIFT builds write no `params` and no `unk` for it on any model call
(`_MODEL_CALL_UNKNOWN` lacks `/params`), so the gap is in every AgentDojo-family corpus, not only Mandate's 396 calls (the
U6 smoke run looked at Mandate and AgentHarm only). The transcript/v1 mapper (`adprov`) already declares it. The user
chose to declare it on every TraceLogger model call (2026-10-13), since every AgentDojo-family AER changes in the round
anyway (profile digests, items 3, 13, 17, 22).

**Prediction (written before the code).**
- **Change:** `/params` joins `_MODEL_CALL_UNKNOWN` in `adapters/agentdojo/mapper.py` and `drift_mapper.py`. No rule: the
  absence is the format's (TraceLogger logs no request), as for the other members of that list. No observed value is
  added.
- **AER:** every `model_call` of every TraceLogger AER gains `"/params": "not_recorded"` in `unk`: all AERs of
  `agentdojo-upstream-2024-06` (18,241), `-head` (36,679), ROPE (10,791), AgentDyn (38,281), survey (3,243) and
  Mandate (396), except AERs without a model call (outcome-only and empty logs). adprov-v1 and the capture mapper are
  unchanged (they declare or record `params`).
- **SEM:** through `aer_digest` only. **PROV:** ~~one `apv:Gap` per model call for the declared pointer~~. *Corrected
  2026-10-15 (corpus pre-check CC-04, PC-agentdojo-upstream-06):* the engine records `apv:paramsStatus apv:NotRecorded` on
  every model call of a TraceLogger execution and adds no new `apv:Gap`.
- **stats:** the `sampling` cell of these corpora moves from undeclared `not_recorded` to declared `unk:not_recorded`.
- **Pins:** the AgentDojo-family AER digest pins, the C.16.1 vector, golden and gate-D PROV of TraceLogger fixtures.

**Implemented (2026-10-13).** Mandate rehearsal: `/params` `not_recorded` on 1,621 of 1,621 model calls; tier 4 passes.

### Item 12 (E2-b3, c3/c4) with U6-a and U6-b: the Inspect harness, input authorship, checker and transmitted parameters (D-374, D-375)

**Evidence.** The AgentHarm producer is inspect_ai `0.3.247.dev69+g53c1fa98b`; commit `53c1fa98baedd64c…` is in the
full-blob store `~/.agentprov/cache/git/github.com/UKGovernmentBEIS/inspect_ai.git` (D.9.5, `acquisitions.jsonl`), and
every passage below was read there:
- `_eval/task/run.py`: `task_run_sample` (l. 1059) runs the sample; it opens `span("init", type="init")` (l. 1289),
  `span("solvers")` (l. 1367), `span(name="scorers")` (l. 1545) and one `span(name=scorer_name, type="scorer")` per
  scorer (l. 1559-1561); an untyped span takes its name as type (`util/_span.py` l. 55-106). `create_eval_sample`
  (l. 1844) writes the sample's `started_at`/`completed_at`/`total_time`, the AER run scope.
- `model/_call_tools.py` l. 624, 670, 677: each tool call runs in `span(name=call.function, type="tool")`.
- `_eval/task/util.py` l. 22-29 `sample_messages`: `Sample.input` becomes the state's messages with `source="input"`;
  `solver/_prompt.py` l. 17-42 `prompt_template` rewrites that message in place (id and source kept).
- `log/_transcript.py` l. 617-637 with `_util/constants.py` l. 46: with `log_model_api` unset (the default; the AgentHarm
  header has no such key), a `ModelEvent`'s `call` (the request) is kept for the first 5 non-error calls per model per
  sample and set to `None` afterwards.
- `log/_log.py` l. 943: `task_version: int | str = Field(default=0)`.
The inspect_evals task definition at `2dd469a` (AgentHarm's) is not local; the logged plan names its solvers
(`inspect_evals/system_prompt_based_on_model`, `prompt_template {"template": "\n\n{prompt}"}`, ...).

**User decisions (2026-10-13).** c4 as planned (m1 D on inspect_ai code, m0 class I, judge prompts unattributed);
U6-b `lost` under a D rule; U6-a: map `task_version` as the bench actor's `/version`.

**Prediction (written before the code).**
- **Rules** (`inspect` catalogue, version integer left to the D-31 branch): `inspect.sample_run_by_harness@1` (D),
  `inspect.tool_span_by_runtime@1` (D), `inspect.sample_input_from_benchmark@1` (D), `inspect.model_api_call_retention@1`
  (D), each with an `_unverified` class-I twin cited when the producer's `+g<commit>` is not in the rule's code list
  (D-24; the Inspect family had no twins, so the check is local to these rules); `inspect.system_message_from_task_plan@1`
  (I); `inspect.task_version_label@1` (D, independent of the producer: it reads the header's typed field).
- **c3:** the run scope gets `actor: harness`; span scopes of the run's own spans (`init`, `solvers`, `scorers`,
  `scorer`) get `harness`, tool spans `env`. AgentHarm: 1,056 run activities and all 8,388 step activities (4,164 tool,
  4 × 1,056 run spans) gain `wasAssociatedWith` (core, D). The execution description `x:exec` stays attribute-linked
  (no rule names a relation for it; documented in D.9).
- **c4:** the run-scope user message with `source: "input"` (m1) gets `actor: bench` (D, 1,056); the run-scope system
  message inserted by the plan (m0) gets `actor: bench` (I, 1,056; inference bundle). The 1,598 judge-prompt user
  messages keep `unk /actor not_recorded`. PROV: `wasAttributedTo(m, bench)` for 2,112 messages.
- **U6-a:** judge actors gain `unk {"/code": "not_recorded", "/version": "not_recorded"}` (1,012 executions); the bench
  actor's `/version` becomes `"2"` (D, `task_version_label`), moved out of `ext.inspect.task_version` (1,056). A
  `task_version` of `0` (the producer's default) is no label (C.7.3): `/version` is declared `not_recorded` and the value
  stays in `ext`.
- **U6-b:** a non-error, non-cached agent or judge call without `call`, after 5 kept calls of its model in the sample,
  gets `unk {"/params/transmitted": "lost"}` under `model_api_call_retention` (489 calls in 200 executions); any other
  absent `call` gets `not_recorded`.
- **Digests:** every `ast-survey-agentharm` AER (1,056), so its SEM and PROV; the `inspect` catalogue and adapter code
  digests. WhistleBench, fragfuse and kexin (trial or profile only) change too: their producers are not verified, so
  the twins apply there. Pins: Inspect goldens and expected AERs.

**Implemented (2026-10-13; spec D.9.11).** As predicted, with one count corrected. Rehearsal: `recompute --out` (re-map,
8 workers) of a clone of `ast-survey-agentharm-p10` under `~/.agentprov/migration-work/regen-items-2-12/`: 1,056
`changed_explained`, 0 failed, 4 `index_refreshed` (item 11), every tier-4 row `pass` (including item 10's checks).
Counted in the new AERs:
- run scopes `actor: harness` D 1,056; span scopes `init`, `solvers`, `scorers`, `scorer` → `harness` D 1,056 each;
  `tool` → `env` D 4,164; `solver` keeps `agent` 5,280;
- run-scope `user` (input) → `bench` D 1,056; run-scope `system` → `bench` I 1,056; 1,598 judge prompts unattributed;
- judge actors with the two `unk` 1,012; bench `version: "2"` 1,056;
- `/params/transmitted` `lost` on **630** calls in 266 executions: the predicted 489 agent calls in 200 executions plus
  141 judge calls in the two logs whose judge uses the agent's model string (the producer counts per model string, so
  the same policy drops them); 0 `not_recorded`;
- completeness: 4 `known_incomplete`, 1,052 `verified_complete`.
Tests: `tests/adapters/inspect/test_item12.py` (9: the twin choice, the associations in PROV, the twins for an
unverified producer, both input attributions, the unattributed system message without a plan, U6-a, the default
task version, U6-b). Pins regenerated: the three Inspect expected AERs.

### Item 2 (B3): CaMeL interpreter feedback and the planner's input (D-376)

**Confirmed in the vendored CaMeL code** (AgentDyn pin `5353cf76`, `src/agentdojo/defenses/camel/src/camel/`, read in the
bare store `~/.agentprov/cache/git/github.com/SaFo-Lab/AgentDyn.git`):
- `pipeline_elements/privileged_llm.py` l. 114-134 `make_error_messages`: on an interpreter error the element appends an
  assistant message (the code) and a `user` message beginning "Running the code gave the following error:" (the
  formatted exception, redacted when it came from an untrusted source, l. 86-111); l. 372-375 append that pair both to
  the outer `messages` (what `AgentPipeline.query` logs after each element, `agent_pipeline/agent_pipeline.py`
  l. 531-533) and to the planner's private list. The feedback is the interpreter's, not the simulated user's.
- l. 306-321: the planner (P-LLM) is queried with its own list, `[system(generated prompt), user(query)]` plus earlier
  (code, feedback) pairs, with a dummy runtime. Tool results never enter it, and its system prompt is not logged. The
  logged prefix is therefore not what the planner saw; its input is not recorded.
- The CaMeL logs (2026-01-22) predate the repository's CaMeL code (2026-04-09; identity table), and `agentdyn` has no
  `verified_code`, so the new D rules are cited through their `_unverified` twins (I).

**Prediction (written before the code).**
- **Change:** two new optional hook points in `quirks.py` (byte-neutral where no hook uses them): `later_user_message`
  (a later plain `user` message, before the unattributed fallback) returning a defence author, and `agent_input`
  (each agent model call) declaring its input not recorded. The AgentDyn hook `agentdojo.camel_interpreter_feedback`
  (profile quirk, `applies` `*-camel`) uses both, under `agentdyn.camel_interpreter_feedback@1` and
  `agentdyn.camel_planner_input_not_logged@1` (D, with twins). The mapper's existing hook point `user_message` fires
  only for unknown key sets, which the feedback (plain `{role, content}`) is not.
- **AER (agentdyn-a, 386 CaMeL logs):** 1,674 feedback messages in 266 logs get `actor: def<camel>` (`evf /actor I`,
  the twin), and those 266 logs lose `unattributed_additional_user_message`; every agent model call (2,342) drops
  `input` (31,030 references) for `unk {"/input": "not_recorded"}` with the twin cited, and no longer cites
  `agentdojo.context_is_prefix@1`. Every AgentDyn AER also changes through the profile digest (already the case, item
  22). No other profile moves (the hook applies only to `*-camel`).
- **SEM:** the feedback messages' integrity follows their author (a defence is not a trusted principal: `unknown`).
- **PROV:** `wasAttributedTo(feedback, def<camel>)` (inference bundle); the planner calls' `used` context statements
  (`aprov.use_context@1`, inference) and the exposure assessments premised on them are gone for these 2,342 calls.
- **Not in this item (finding):** CaMeL's synthetic assistant messages (the success summary of printed output, l.
  385-389, and the trailing `content: None` message, l. 478-481, 100 logs) still get agent model calls, and the
  failed-attempt tool results precede the code that issued them, so `messages_append_ordered` places those executions
  before their cause. Both are mapping questions for the AgentDyn owner (§12).

**Implemented (2026-10-13; spec D.6.14 item 8).** Checked: all 386 stored CaMeL logs re-mapped in memory from their raw
objects with this branch: 386 valid in release mode; 1,674 feedback messages in 266 logs authored by the camel defence
(twin, I); 0 `unattributed_additional_user_message`; 2,342 planner calls with `unk /input not_recorded`; PROV of all 386
passes tier 4 (with item 10's checks). They also carry item 5's activity (320 logs with injections). Tests:
`tests/adapters/agentdojo/test_item2_camel.py` (4).

### Item 5 (C2): the run used the injected environment (D-370)

**Evidence.** `TaskSuite.run_task_with_pipeline` calls `load_and_inject_default_environment(injections)` once, before
the passes, with the injections the log records: `c274885` `src/function_calling_pi/task_suites/task_suite.py`
l. 134-135, 237-248; `089ed468` `src/agentdojo/task_suite/task_suite.py` l. 139-140, 339-366; the 0.1.35 wheel
(`a75aba7`) holds a byte-identical file (compared with the installed wheel of the agentdojo backend).

**Prediction (written before the tests).**
- **Change (user's choice: adapter-only):** the TraceLogger mapper writes, for every execution with
  payload fixtures, one `activity` `ac0` (`type: agentdojo:load_environment`, declared in the `agentdojo` catalogue's
  `types`; `scope: run`, `actor: bench`, `inputs` the payload fixtures, `unk /t not_recorded`) under the new rule
  `agentdojo.environment_loaded_with_injections@1` (D; `_unverified` twin I where the producing code is not verified:
  ROPE, AgentDyn, survey, head `v0.k11` after `c274885` and `v1.k14`/Mandate where only `c274885` would apply).
- **AER** (executions with payload fixtures, stored corpora; census 2026-10-13): 2024-06 16,210 (25,440 fixtures),
  head 33,119 (51,714), ROPE 10,043 (22,307), AgentDyn 33,091 (75,141), survey 2,847 (4,401), Mandate 369 (369).
  AgentHarm and every non-AgentDojo family: none. **adprov-v1 (17,082 executions with 26,406 fixtures): not changed.**
  The transcript/v1 mapper was first given the same record, but gate D requires 0 generic records in migration AERs
  (J; `pv.profiles.migration_generic` failed on golden pair R02); the user chose TraceLogger only (2026-10-13), so
  adprov's fixtures stay attribute-linked.
- **PROV:** per such execution `used(x:ac0, x:fx<i>)` for each fixture (`aprov.g_use@1`), `wasAssociatedWith(x:ac0,
  x:bench)` (`aprov.g_assoc@1`), the activity node with `apv:partOf x:run`; in the core bundle where the rule is D, in
  an inference bundle through the twin. The configuration subgraph (attacker, fixtures) joins the run's component
  through `bench`. SEM unchanged except through `aer_digest`.
- **Pins:** every AgentDojo-family AER pin with fixtures, the C.16.1 vector, gate-D digests of the native TraceLogger
  logs. adprov pins, the C.16.2 vector and the compat gate are unchanged by this item.

**Gate D (2026-10-13).** The full suite showed gate D's never-emit check (`never_emit.native`: 7 of the 9 native
June-2024 goldens with fixtures) and reconcile R3 (`native_only:activity[*]/…` unexplained) refusing the activity: gate D
counts the native TraceLogger goldens as migration AERs too. The user chose to exempt exactly this activity type in gate
D (`migration/gate_d_worker.py` `EXEMPT_ACTIVITY_TYPES`, its G-ACT/G-USE/G-ASSOC statements with it) and to explain its
fields in R3 (`migration/reconcile.py`); J amended. Gate D and R3 pass again; the stored gate-D reports
(`docs/reports/migration/`) are dated records and are not regenerated.

**Gate D cross count (2026-10-22, regeneration round).** The round's full-scope gate D on the regenerated 2024-06 and
adprov-v1 corpora passed all 35,905 executions in every D8 tier but failed `crosscount.native.activity_records`
(16,003 observed, 0 in J.3.5): the exemption above covered the never-emit check, not the J.3.5 cross count. Fixed on
branch `gate-d-item5-crosscount` (class 0; `migration/` is in no stage scope): `activity_records` counts only the
non-exempt activities, and a new check compares the exempt loads with a count derived from each AER (one per
TraceLogger execution with injection payload fixtures), per execution (`xc.environment_load`) and per tree
(`crosscount.<tree>.environment_load_activities`); J.3.5 states it. The 16,003 are the matched subset of the 16,210
predicted above (Mixtral and outcome-only executions are reported separately).

**Implemented (2026-10-13; spec D.6.5 step 4; TraceLogger only).** Rehearsal: `recompute --out` of a clone of
`mandate-agentdojo-eval-p10`: 396 `changed_explained`, 0 failed; 369 activities, one per execution with fixtures, each
with its one fixture as input, class D (Mandate's code is verified); 396/396 tier-4 rows pass. AgentDyn's CaMeL
re-map (item 2) carries 320 activities at class I (twin). Tests: `tests/adapters/agentdojo/test_item5_environment.py`
(the record, the twin, `used(x:ac0, x:fx<i>)` and the association in PROV, tier 4).

### Items 4 (C1), 6 (C3) and 8 (F-10): the semantics profile `agentdojo.suites@2` (D-371, D-377, D-379)

All three change the same code (`semantics/markers.py`, `suites.py`) and only at version 2 (and versions built on it,
such as item 27's `@3`): version 1 is the v2.3 port, frozen as gate D's oracle. So, as for item 1, **no stored SEM byte
moves unless a corpus is derived with `@2`/`@3`** (regen-plan D-353, the user's choice per corpus).

**Prediction (written before the code).**
- **Item 8 (F-10):** a new normaliser rule `agentdojo.yaml_norm@2` (D-31: a changed behaviour mints a new rule version)
  reads only YAML's escapes and Python's `\'` (the readings serve Python reprs too): any other escape (`\q`, a short `\u12`) keeps its backslash instead of decoding to its
  letter. Valid escapes, including `\N`, `\_`, `\L`, `\P` and `\/`, are read as before (YAML defines them; the
  Windows-path case of F-10 is a valid escape and stays readable, disclosed in the datasheet as F-10 recommends). The
  `@2` profile's `[marker] normalisers` names `@2`. Expected effect on stored data: examination 2 (A05) found every
  `present` marker explained by a reading and no F-10 over-match (17 of 17 judged true), so few or no markers should
  move; measured on a sample of every AgentDojo-family corpus after the code.
- **Item 6 (C3):** an `absent` payload whose run of at least 40 characters (`PREFIX_CHARS`) occurs in the output gets
  `agentdojo.partial_payload` `{fixture, chars}` on the tool result (rule `agentdojo.partial_payload@1`, D,
  code-independent like the normalisers). The marker status stays `absent`. Expected: the 48 DRIFT cases of the
  4,000-row AgentDyn sample (analysis §3.3) and fewer elsewhere; PROV: one assessment-bundle mention per annotation
  (`aprov.a_label@1`, `apv:annotationType`).
- **Item 4 (C1):** a `security` judgement with value `true` that carries an `attack_succeeded` outcome (a targeted,
  checker-scored injection) and no payload visible in any message part (no `present`/`ambiguous` reading, no partial
  run; any tool result without text blocks the flag, fail-closed) gets `agentdojo.success_without_visible_payload`
  `{fixtures}` (rule `agentdojo.success_without_visible_payload@1`, D, code-independent); assessment bundle only.
  Expected (analysis C1 screen, with the `@2` readings): head 11 (all banking `user_task_15`), ROPE 22 (fewer after B1's
  unescape, which makes AutoDojo payloads visible), AgentDyn about 1 per 4,000; measured after the code.
- **Digests:** the `@2` profile digest (its `profile.toml` and the header `ns` of every `@2` SEM document), the
  `agentdojo` catalogue digest (three new rules) in every PROV that embeds it; SEM/PROV of corpora derived with
  `@2`/`@3`.

**Implemented (2026-10-13; spec C.14.8 items 8-10).** Two corrections came from the stored-corpus sample, before any
corpus is derived with `@2`:
- *Item 8:* reading only YAML's escapes turned 166 AgentDyn and 194 ROPE sampled markers from `present` to `ambiguous`,
  every one behind a Python repr's escaped apostrophe `\'` (examination 2: the readings serve reprs). `yaml_norm@2`
  now reads YAML's escapes plus `\'`; any other escape keeps its backslash.
- *Item 4:* the first version flagged outcome-only logs (empty `messages`: AgentDojo's 207 claude-3-opus logs), where
  "not visible" is vacuous; the flag now needs a trajectory.

Measured with `@2` on the stored AERs (read-only; samples of 4,000 executions per corpus, Mandate whole):

| Corpus | Markers sampled | Item 8: markers changed | Item 6: executions with a partial run (annotations) | Item 4: flags |
|---|---|---|---|---|
| agentdyn-a | 46,586 | 0 | 38 (161); 37 in `gpt-4o-mini-2024-07-18-drift` | 0 in the sample |
| ROPE | 69,995 | 0 | 308 (918) | **5 in the whole corpus**: github `user_task_7` (2), `9`, `11`, shopping `user_task_10`, all `important_instructions` |
| head | 27,145 | 0 | 50 (174) | **11 in the whole corpus, all banking `user_task_15` `important_instructions`**: the C1 screen exactly |
| 2024-06 | 26,292 | 0 | 52 (100) | **9 in the whole corpus**, all banking `user_task_15` |
| survey | 18,368 | 0 | 52 (156) | 0 |
| Mandate | 1,296 | 0 | 0 | 0 |

The C1 screen's 22 ROPE cases were 17 AutoDojo `slack/injection_task_1` and 5 `important_instructions`: with item 1's
unescape (B1, `@2`) the 17 AutoDojo payloads are visible and not flagged; the 5 remain. Tests:
`tests/adapters/agentdojo/test_items_4_6_8.py` (21, including tiers 3 and 4 with the annotations in the assessment
bundle).

### Item 7 (F-01): lone surrogates mapped with a disclosure (D-23, D-378)

**Prediction (written before the tests).**
- **Change (adapter layer only; aer/0.1 frozen):** `adapters/surrogates.py` and a post-pass in the TraceLogger, DRIFT,
  transcript/v1 and Inspect mappers. A lone surrogate in a typed string position (a `$utf16` value outside a `Json`
  field, or a plain string) and in any object key is replaced by U+FFFD; the pointer is tagged `D` (never above the
  record's class) and cites `<ns>.lone_surrogate_replaced@1` (`agentdojo`, `adprov`, `inspect`; D, code-independent);
  an info issue `<ns>.lone_surrogate_replaced` lists the records (and `exec` when a source key was replaced: keys are
  scrubbed on the parsed source before mapping, so their AER position is disclosed by the replacement character only).
  A `$utf16` value in a `Json` field (`args`, `value`, `content`, `params`, `ext`, ...) is kept: it is lossless there.
- **No stored AER byte** from the replacement itself: 0 degenerate units and 0 `$utf16` in typed positions in the
  current corpora (A4 and D-23). The three catalogue digests move (new rule and issue code each), so the PROV of every
  corpus embedding the `agentdojo`, `adprov` or `inspect` catalogue changes in its catalogue attribute (as for every
  catalogue item of the batch); the adapter code digests move.
- **Not covered:** the other families' mappers (DTap, OpenHands, AgentOps, credleak, autogen, foobench, capture) keep
  today's behaviour; they can adopt the shared post-pass with their own rule (routed in AGENTS.md §12).

**Implemented (2026-10-13).** As predicted. Tests: `tests/adapters/test_item7_surrogates.py` (a TraceLogger log with
lone surrogates in an assistant text, a tool output and an argument key maps, validates in release mode and holds no
lone surrogate; an Inspect sample likewise; `$utf16` in `Json` fields kept).

### R-10p-2 (routed from phase 10p, user-confirmed 2026-10-13): the agent's model from `eval.model_roles`

**Evidence.** control-arena (phase 10p README §5, §7 at `e898057`): 152 original logs set `eval.model = "none/none"` and
`eval.model_roles`; their solver spans call only the `untrusted` role's model (17,762 real calls), scorer spans only the
`trusted` one. inspect_ai at `53c1fa98`: `ModelEvent.role` (`event/_model.py` l. 63-64), `EvalSpec.model_roles`
(`log/_log.py` l. 994), `get_model(role=...)` returns the role's model (`model/_model.py` l. 1815-1830).

**Prediction (written before the code).**
- **Change:** when every agent model event of a sample carries one `role` R and `eval.model_roles[R].model` is a
  string, the agent actor's `model.requested` is that model (O by config, locator `a1:/eval/model_roles/R/model`) and its
  `params` the role's `config` when present, under the new rule `inspect.agent_model_from_role@1` (D; its
  `_unverified` twin for producers whose `+g<commit>` is not cited, as for item 12's rules). Otherwise unchanged
  (`eval.model`).
- **Stored corpora:** none moves: `ast-survey-agentharm`'s 5,261 model calls carry no role (0 `ext.inspect.model_role`).
  The `inspect` catalogue and adapter code digests move (with the batch's other Inspect items). control-arena (not
  stored): the 152 `none/none` logs get the untrusted model as the agent's requested model.
- **Note (item 28):** phase 10p found 28 more strings over 1 MiB in 22 control-arena samples; item 28 (i) already
  handles them (no change).

**Implemented (2026-10-13; spec D.9.11 item 5).** Tests: `tests/adapters/inspect/test_r10p.py` (the role's model and
config at D; without a role, `eval.model` as before).

### D-182 with R-10p-3 (user-approved 2026-10-13): redaction of workstation account paths in Inspect AERs

**Prediction (written before the code; design `docs/reports/phase10h/redaction-design.md`).**
- **Change:** `[[family.inspect.redact]]` in `family.schema.json`; `adapters/inspect/redact.py`; a post-pass in the
  Inspect mapper; rule `inspect.value_redacted@1` (D) and issue `inspect.value_redacted` (info); `ext.inspect.redacted`
  in `ext.schema.json`. Scopes `model_id` (whole observed model ids, wherever copied) and `harness_text` (the run
  scope's sample `error` with `traceback`/`traceback_ansi`, kept events including their `error`, `sample_metadata`,
  `task_args`, `revision`, the agent's `params`, and header `eval.metadata` (R-10p-3's
  `micro_protocol.prompt_file`; not copied into the AER today)).
- **Stored corpora:** none moves. Only a profile with a `redact` table redacts; the shipped `survey-agentharm` profile
  needs none: a scan of every stored AgentHarm AER finds no account path in a harness field (its 85 non-placeholder
  `/Users/<x>/` or `/home/<x>/` strings are model output, tool arguments and state patches of messages, which are never
  redacted). The `inspect` catalogue and adapter code digests move. The kexin, fragfuse and control-arena profile
  owners add their tables after this lands (not this branch).

**Implemented (2026-10-13; spec D.9.12).** Tests: `tests/adapters/inspect/test_r10p.py` (a checkpoint model id redacted
everywhere it is copied, a traceback and `sample_metadata` account segment redacted, model output kept verbatim, the
label stable across logs, `ext.inspect.redacted`, the info issue, tier 4; malformed rules refused).

**Checked for R-10p-2, D-182 and item 7 together (2026-10-13, after the merge with main's items 22-29):** a second
`recompute --out` of the AgentHarm clone on the branch's final code gives AER files byte-identical to item 12's
rehearsal in 1,056 of 1,056 executions; 0 failed, the same 4 index rows refreshed (item 11).

**Round outcome (2026-10-22, regeneration round at 5b1f6fdf; measured, `docs/reports/regeneration/round/``README.md` and each corpus's
`compare.json`).**
- **Items 9, 11 and D-372 (completeness):**
  - ROPE: 322 `known_incomplete` → `unverifiable`, 2 `verified_complete` → `unverifiable`;
  - AgentDyn: 825 `known_incomplete` → `unverifiable`, 12 stay;
  - head: 36 `known_incomplete` → `unverifiable` and 232 `verified_complete` → `unverifiable`, 47 stay;
  - 2024-06: 232 `verified_complete` → `unverifiable`;
  - AgentHarm: 4 `verified_complete` → `known_incomplete`;
  - Mandate, survey and adprov-v1: unchanged.
- **Item 10:** strict validation (`aer,sem,prov,linkage`, tier 4 with item 10's checks) passed every execution of
  the eight corpora, with 0 checks skipped.
- **Item 12 with U6-a/b (AgentHarm 1,056):**
  - `sample_run_by_harness` 1,056 executions (5,280 citations);
  - `sample_input_from_benchmark`, `system_message_from_task_plan` and `task_version_label` 1,056 each;
  - `tool_span_by_runtime` 766 (4,164);
  - `model_api_call_retention` 266 (630 calls), as the implementation recorded.
- **Item 2 (AgentDyn CaMeL):**
  - `camel_interpreter_feedback` twin: 266 executions (1,674 citations);
  - `camel_planner_input_not_logged` twin: 384 executions (2,342);
  - `context_is_prefix` dropped in 384 (2,342);
  - `unattributed_additional_user_message` gone from 266.
- **Item 5:** environment-load activities added in executions with injections:
  - 2024-06: 16,210, D;
  - head: 33,119 (23,782 D, 9,337 I);
  - ROPE: 10,043, I;
  - AgentDyn: 33,091, I;
  - survey: 2,847, I;
  - Mandate: 369, D;
  - AgentHarm and adprov-v1: 0.
  Gate D's `crosscount.native.environment_load_activities` at f0410684: 16,003 observed = 16,003 derived.
- **Item 4:** `success_without_visible_payload` annotations in the whole corpora:
  - head 11, 2024-06 9 and ROPE 5, as predicted;
  - AgentDyn 10;
  - survey, Mandate, adprov-v1 and AgentHarm 0.
- **Item 6:** `partial_payload` annotations in the whole corpora (annotations, not executions):
  - AgentDyn 1,020, ROPE 2,659, head 784;
  - 2024-06 537, adprov-v1 787;
  - survey 156 (equal to the whole-corpus sample), Mandate 0.
- **Item 8:** no marker changes status outside ROPE's B1 (item 1).
- **Not separately counted in the round's records:** item 7, U6-c, R-10p-2 and D-182. Their effects are inside the
  per-execution AER changes, which every compare reports for all executions.

