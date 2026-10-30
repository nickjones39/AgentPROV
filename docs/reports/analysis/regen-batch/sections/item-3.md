## Item 3 implemented (2026-10-12; D-80, D-81) — digest prediction

**What changed.** D.5.4 "Citation of D rules": a D rule is cited at D only for a record whose producing code its `code`
list cites (profile `verified_code`), else through its `_unverified` twin at class I; 31 twins added (agentdojo 18,
agentdyn 3, rope 3, adprov 7, the nine c6 rules among them); records weakened to their rules' class (C.6.5 rule 1); a
loss proven only by a D rule (B6); the engine routes an attribute naming an INFERRED node out of the core (D-81).
Versions: catalogues `agentdojo`, `agentdyn`, `rope`, `adprov` and profiles `agentdojo-upstream`, `rope`, `agentdyn`,
`survey-runs`, `mandate-agentdojo-eval`, `adprov-v1`, `agentdojo-live`, `autodojo-live` change bytes at the same integer
version (nothing is released, as in every earlier phase); `aer/0.1`, `sem/0.1`, `agentprov-prov/0.1` unchanged.

**Prediction per corpus**, from a read-only scan of every stored AER with the new resolver (scripts kept with the session;
counts are executions). Every AER of a changed profile changes (its header carries the profile digest), so every SEM
(`aer_digest`), PROV (catalogue digests, statements) and validation digest of those corpora changes too.

| Corpus | AERs | AER changes | Twinned D citations (executions) | Completeness |
|---|---|---|---|---|
| agentdojo-upstream-2024-06 | 18,241 | all (profile digest); statements in all | `functions_runtime` 18,241; `committed_no_later_than` 18,241; `empty_assistant_text_ambiguous` 788 | unchanged (the 47 retries are `v0.k11`, verified: stay D, `known_incomplete`) |
| agentdojo-upstream-head | 36,679 | all; statements in all | the two above 36,679 and 2,049; the `v1.k14` logs (11,765): `assistant_msg_has_one_call`, `messages_append_ordered`, `benchmark_from_dialect`, `system_prompt_from_harness`, `user_is_simulated` 11,765, `checker_outcome` 11,764, `tool_msg_is_one_execution`, `tool_status_from_error` 10,595, `benign_security_constant` 528, `injection_task_as_user_task` 140 | unchanged (all 82 retries are `v0.k11`) |
| mandate-agentdojo-eval | 396 | all; statements in all | 13 rules, as R07 listed (e.g. `checker_outcome` 396, `tool_msg_is_one_execution` 391); `args_are_effective`, `log_holds_last_pass`, `naive_local_timestamp`, `system_prompt_variant_digest`, `mandate.decline_prefix` stay D | unchanged |
| rope | 10,791 | all; statements in all | 15 rules (all of R07's list except `system_prompt_variant_digest`, `rope.security_correction`), incl. `null_final_implies_three_passes` 322, `rope.denial_query_echo_variant` 6,197, `rope.tree_arm_config` 2,920 | **322 `known_incomplete` → `unverifiable`** (B6) |
| agentdyn-a | 38,281 | all; statements in all | 16 rules, incl. `last_assistant_content_none_max3` 826, `drift_user_error_key` 274, `json_decode_error_imposed` 5 | **825 `known_incomplete` → `unverifiable`**; the 826th retry log is `v1.k14.incomplete` and stays `known_incomplete` (its `incomplete_run` is observed) |
| ast-survey-agentdojo | 3,243 | all; statements in all | 13 rules (R07's list less `system_prompt_variant_digest`) | unchanged (no retry) |
| adprov-v1-release | 17,664 | all; statements in all | the six c6 adprov rules (`assistant_turn_one_call` 17,664 … `lost_calls_from_count` 121) and five agentdojo rules (`functions_runtime`, `messages_append_ordered`, `system_prompt_from_harness`, `user_is_simulated` 17,664; `tool_status_from_error` 16,247) | unchanged (its `known_incomplete` rows come from accounting) |
| ast-survey-agentharm | 1,056 | **none** | none | unchanged; SEM and PROV re-derived byte-identical for all 1,056 |

R07b after regeneration: 0 D citations on unverified code (the new test `tests/adapters/test_code_verification.py`
checks it on every real fixture). Statement placement on the 19 golden adprov pairs (PROV, before → after): model
invocations, assistant-message and part generation, model use and association, tool-result generation and request use,
and the tool runtime's association move from core D to inference I (D-27 c6); the released tree's passes and their
`apv:partOf` go to inference. `docs/compat/semantic-diff.md` regenerated from the updated map (gate E passes).

**Open, for the user (answered 2026-10-12: (1) D-84, item 13; (2) D-85, datasheet item 13; (3) D-86, within item 1; (4) D-87, item 14; (5) D-88, stays rejected; (6) D-82):** (1) head's `v0.k11` logs introduced after `c274885` (about 10,700 of 24,914)
are treated as June-2024 code, as the analysis did; (2) `adprov-v1` treats `579a908` as the released writer although the
capture-code version is not recorded per trace; (3) SEM rules (`agentdojo.security_polarity`, `utility_meaning`,
`injection_marker_yaml`, code at `c274885`) are cited for unverified harnesses: item 1's `agentdojo.suites@2` bump is the
place to decide twins for them; (4) a positional or twinned call link leaves the execution's causal `after` at D in both
mappers (pre-existing; C.6.5 rule 1 says I); (5) the full rule-4 cap for O/D targets (D-81 rejected alternative); (6) after the
merge of phase 10b: DTap raises `incomplete_run` for its one partial trajectory under the I rule
`dtap.partial_file_name@1`, so under the clarified H.3.2(2) that run is `unverifiable`, not the `known_incomplete` that
§D.16 stated. **Decided (D-82, 2026-10-12, delegated by the user):** `unverifiable` stands; §D.16 updated. No DTap corpus
existed, so no byte changes.

**Item 3, full-derive check (2026-10-12, after D-83).** The prediction above scanned rule citations only, and missed
the regression D-83 fixes (SEM annotations INFERRED by propagation failed PROV derivation). A sample of 300 executions
per affected corpus was therefore re-mapped from each corpus's raw store with the fixed code and run through SEM
(`agentdojo.suites@1`), PROV and tier 4 (release). Half of each sample has a retry, run error, incomplete run,
unexecuted, missing or orphan call, link conflict, identity conflict or decision. All 2,100 pass: 2024-06, head, ROPE,
AgentDyn, survey, Mandate and adprov-v1, 300/300 each.

**Round outcome (2026-10-22, regeneration round at 5b1f6fdf; measured, `docs/reports/regeneration/round/``README.md` and each corpus's
`compare.json`).** Every AER, SEM and PROV of the eight corpora changed; AgentHarm cites no twin. The named counts match:
- 2024-06: `functions_runtime` and `committed_no_later_than` 18,241, `empty_assistant_text_ambiguous` 788;
  completeness unchanged by item 3.
- head: the two above 36,679 and `empty_assistant_text_ambiguous` 2,049. Every count also holds item 13's 10,732
  `v0.k11` logs: `assistant_msg_has_one_call` 22,496, `checker_outcome` 22,443, `tool_msg_is_one_execution` and
  `tool_status_from_error` 20,308, `benign_security_constant` 1,915 (528 + 1,387). The five rules every `v1.k14`
  log cites move 22,497, which is 11,765 + 10,732.
- ROPE: `null_final_implies_three_passes` 322, `rope.denial_query_echo_variant` 6,197, `rope.tree_arm_config` 2,920;
  322 `known_incomplete` → `unverifiable`.
- AgentDyn: `last_assistant_content_none_max3` 826, `drift_user_error_key` 274, `json_decode_error_imposed` 5;
  825 `known_incomplete` → `unverifiable`, 12 stay `known_incomplete`.
- Mandate: `checker_outcome` 396, `tool_msg_is_one_execution` 391.
- adprov-v1: the six c6 rules (`assistant_turn_one_call` 17,664 … `lost_calls_from_count` 121) and the five
  agentdojo rules (17,664, `tool_status_from_error` 16,247); completeness unchanged.
- **Rule-pair counts (explained, D-359):** the number of rule pairs that move to a twin differs by one from the
  counts above. Both causes are counting differences; nothing is missing:
  - **ROPE 16 against 15, AgentDyn 17 against 16, survey 14 against 13.** The prediction's source scan
    (`phase10-data/ruleclasses.json`, `tools/analysis/phase10_extract.py`) reads records' `rule` lists, not the seal's
    `issues[].rule`. So it misses `agentdojo.unexecuted_trailing_calls@1` (D, code `c2748856` only), which is cited
    only as the rule of `unexecuted_tool_call` seal issues. It moves to its twin in ROPE 675, AgentDyn 1,683, survey 48
    and head 672 executions.
  - **Mandate 12 against 13.** Item 1 restored `injection_task_as_user_task` to D (its code list gained
    `089ed468`/`a75aba7`; the 27 executions "cite D again"), so it no longer moves.

