## Item 103 (D-80 (d) addendum; user decision 2026-10-15; held branch `regen-held-3`): the trailing-call issues cite the resolved rule

Under `verified_code = []` (24 AgentDojo-family profiles), `unexecuted_tool_call` and `missing_tool_result` cite
`agentdojo.unexecuted_trailing_calls_unverified@1` (class I, new), through `self.cite.cite`, in `mapper.py` and
`drift_mapper.py`.
- The twin is added to `agentdojo` catalogue v2 **in place**, per the D-31 owner's ruling: no corpus records v2, so
  there is no v3, no profile cascade and no new suites version (D-31 addendum).
- Tests: `tests/adapters/agentdojo/test_d80d.py` (3): the twin on both issues under the survey profile; no proven loss;
  the D rule kept under agentdojo-upstream's verified code. `test_code_verification.py` gains `ITEM103_TWINS`.

**Predicted and measured.**
- The `agentdojo` catalogue digest moves for every corpus that cites it, and with it every PROV document. Re-pinned:
  all 19 golden PROV digests and 28 of the 56 gate-D digests (its PROV ones; the 28 SEM digests are unchanged).
- AER bytes move only for executions with either issue under unverified code. Pinned fixtures: 7 phase-10d, 1 ROPE and
  1 survey AER digest re-pinned (`regen_pins --write`).
- Completeness: under unverified code `missing_tool_result` no longer proves loss. Where the accounting checks already
  read `inconsistent` (calls not handled once), the completeness value does not change.
- Stored corpora (catalogue v1) are unaffected until the round re-imports them.
- Must land on main before any import the round keeps (D-460).

