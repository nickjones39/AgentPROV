## Items 22 and 23 (implemented 2026-10-13; user-approved): the routed DRIFT edits

Both depend on phase 10l's new files (`drift_mapper.py` with the hook guard of 1e10f18, the `drift` catalogue),
so they are implemented on main after the phase-10l merge, from the TOML and code in `docs/reports/phase10l/routing.md`
at 1e10f18.

**Item 22 (RT-1, RT-2, RT-4, RT-5).**
- **Change:**
  - RT-1: `TraceLoggerMapper.accepts`/`map` route `drift.k18.messages` and `drift.k18.conversations` to `DriftBuild`
    (lazy import), and `dialect.py`'s status column says so. `DriftBuild` runs none of `_Build`'s hook points; a
    matching quirk hook raises `drift.quirk_hook_not_applied` instead of being skipped (the review of D-116's
    `log_end`, done on 1e10f18).
  - RT-2: in `agentdyn.profile.toml`, `rules` gains `drift = 1` and `args_mutated_in_place` also applies to
    `drift.k18.messages`. Six DRIFT quirks are added for that variant. `drift_integrated_user_error_key` is narrowed to
    `variant = ["v1.k14", "v1.k14.incomplete"]`; all 434 of its messages are in the variant A directory, and without the
    narrowing the RT-1 guard would flag every variant C log.
  - RT-4: `ext.schema.json` `execution.required` drops `error`. DRIFT logs have no run-error field.
  - RT-5: `profile.py` drops the refusal of `retry_semantics = "agentdojo.single_pass"`.
    `test_profile_machinery.py::test_selector_facets_must_be_layout_components` loses that case.
- **Prediction:**
  - The AgentDyn profile digest moves. At its next re-map, every AgentDyn AER changes in `profile.sha256` only: the
    38,281 of `agentdyn-a-p10`, and SEM and PROV after it through `aer_digest`. The re-map is a corpus regeneration and
    needs its own yes.
  - No other AgentDyn field moves:
    - the narrowed hook still applies to every message it applied to (all are variant A);
    - the new quirks apply only to `drift.k18.messages`, which no stored corpus selects;
    - an AER header's `rules` lists only cited namespaces, so `drift` does not appear in part `a`'s AERs.
  - In the `aer` stage definition of AgentDyn corpora, `rules`/`rules_sha256` gain `drift`, which moves its `fn_digest`.
  - The `adapters/agentdojo` code digest moves for every AgentDojo-family corpus, as item 21's does. No other profile's
    bytes change.
  - Registry: AgentDyn part `c` goes from `planned` to `partial`.
  - Tests that change:
    - AgentDyn's profile-digest pins;
    - the reader/import tests that expect DRIFT files to seal `unsupported_variant`;
    - the RT-5 case above.
  - Checked at implementation: a re-map of the stored `agentdyn-a-p10` AERs differs only in `profile.sha256`.

**Item 23 (RT-3).**
- **Change:** `_tool_of`: a `decision` with `verdict: other` and `subtype: drift.isolation_pass` whose subject is a
  `tool_execution` with a `name` gives that name, with premises on the execution's `/name` and the decision's
  `/subject`, and without `R_REDACTED`. The output may or may not have been edited. Without this change, every DRIFT
  tool output gets integrity `unknown` (fail closed).
- **Prediction:**
  - The SEM stage `engine_code_sha256` moves for every corpus with an `agentdojo` semantics profile, since it covers
    `adapters/agentdojo/semantics`.
  - No stored annotation changes: no stored AER has a `drift.isolation_pass` decision. This is checked by a scan of
    the stored corpora at implementation.
  - DRIFT executions gain tool labels instead of `unknown`.
  - Golden SEM and PROV pins are unchanged.

**Implemented (2026-10-13; on the phase-10l branch at 6c5d4a4, then merged with main after the 10l merge).** The change
is as proposed, from routing.md at 6c5d4a4.
- Registry: AgentDyn part `c` is `partial`. It is mapped by the DRIFT build, its tool outputs are DRIFT's isolated
  copies, and the full snapshot is not yet imported. All seven of its directories are in (RT-6 withdrawn; the user's
  2026-10-13 ruling includes data with no successful attacks).

Checked:
- AgentDyn's 14 part-a fixture AERs and 600 evenly spaced stored `agentdyn-a-p10` executions, re-mapped from raw
  with the old (6c5d4a4) and new code, are identical once the `agentdyn` profile digest and the seal's
  `records_sha256` are masked.
- The AgentDyn fixture pins are regenerated, and the variant C fixture is now mapped and pinned.
- 0 stored AERs carry `drift.isolation_pass`, so item 23 changes no stored annotation.

Tests:
- `tests/adapters/agentdojo/test_items_22_23.py`: every DRIFT fixture through `TraceLoggerMapper` is byte-identical to
  `DriftMapper`; isolated outputs are labelled without `R_REDACTED`. Both fail without the change.
- `test_agentdyn.py`: C maps, with no `drift.quirk_hook_not_applied`.
- `test_profile_machinery.py`: `single_pass` is accepted.

**Not done here:** the re-map of the stored `agentdyn-a-p10` (38,281 AERs, `profile.sha256` only) is a corpus
regeneration and needs its own yes.

