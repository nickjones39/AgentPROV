## Items 13 and 14 (2026-10-12; D-84, D-87) — predictions

From a read-only scan of every stored AER (the item-3 resolver gives the post-item-3 classes; ancestry of each
introducing commit from the cached full history of `ethz-spylab/agentdojo`).

**Item 13 (D-84).** Head `v0.k11`: 14,182 logs introduced at or before `c274885` (the 2024-06 overlap; unchanged) and
10,732 introduced after it. Those 10,732 newly cite twins: `agentdojo.benchmark_from_dialect`, `log_holds_last_pass`,
`messages_append_ordered`, `system_prompt_from_harness`, `user_is_simulated` 10,732; `assistant_msg_has_one_call` 10,731;
`checker_outcome` 10,679; `tool_msg_is_one_execution`, `tool_status_from_error` 9,713; `call_id_unique_match` 6,609;
`tools_executed_sequentially` 3,073; `benign_security_constant` 1,387; `injection_task_as_user_task` 357;
`dos_placeholder_injection_task`, `dos_security_rule` 60; `run_error_imposed_outcome` 53;
`null_final_implies_three_passes` 36. Completeness: 36 head retries move from `known_incomplete` to `unverifiable`; the
other 46 of the 82 head retries stay `known_incomplete`. 2024-06: all 18,241 at or before `c274885`, no change.

**Item 14 (D-87).** Tool executions whose call link is INFERRED while their causal `after` is D:
2024-06 8,925 executions of tools in 2,799 executions (positional links); head 5,340 in 2,135 executions after item 13
(17,251 in 5,239 without it); adprov-v1 64,781 in 16,247 executions (the twinned `adprov.call_id_unique_match`, i.e.
every execution with a linked call); ROPE, AgentDyn, survey and Mandate 0 (their tool executions are already I). In PROV
the `apv:afterCausal` attribute of those executions moves to the inference bundle (D-81 routing).

Both items need the full-derive sample check (item 3's, 300 per corpus) before the regeneration.

**Implemented (2026-10-12, branch `claude/items-13-14`; D-84 and D-87 addenda).**
- **Item 13:** the facet `introduced_under` from the history table (format 2). Re-counted with the implemented
  facet on the stored AER headers: head 10,732 `v0.k11` logs cite the twins, 14,182 stay D, 0 unknown; 2024-06 all
  18,241 D, as predicted. The `agentdojo-upstream` profile digest changes (new table), so every agentdojo-upstream
  AER changes.
- **Item 14:** the causal `after` of an execution is weakened with its `call` link in the shared post-mapping pass.

**Round outcome (2026-10-22, regeneration round; measured, `docs/reports/regeneration/round/`).**
- **Item 13:** on head, `log_holds_last_pass` moves to its twin in exactly 10,732 executions. So do
  `call_id_unique_match` 6,609, `tools_executed_sequentially` 3,073, `injection_task_as_user_task` 357, the two DoS
  rules 60, `run_error_imposed_outcome` 53 and `null_final_implies_three_passes` 36. 36 retries move
  `known_incomplete` → `unverifiable` and 47 stay. 2024-06 shows none of item 13's twins.
- **Item 14:** `apv:afterCausal` moves from core to inference:
  - 2024-06: 8,925 tool executions (`agentdojo-positional_match`);
  - head: 5,340 (positional);
  - adprov-v1: 64,781 (`adprov-call_id_unique_match_unverified` + `tool_turn_is_one_execution_unverified`).

