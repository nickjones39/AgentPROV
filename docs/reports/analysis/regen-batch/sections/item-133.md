## Item 133 (pre-check PC-04, control-arena; user decision 2026-10-21: split per scope; held branch `regen-held-5`): a cached scorer call's output is its scope's own message

- **Finding (10p t2, ids only).** In every one of the 910 several-result calls in 364 executions:
  - the second scorer's model call is a cache hit (`status cached`);
  - an activity in its scope re-runs the sandbox commands at its own times.

  The merge by Inspect message id made those results a second result of the first scorer's call. That gave
  `aer.acc.tool_results_linked@1` `call_has_several_results`, `map.accounting_inconsistent` and `known_incomplete`,
  though nothing is lost.
- **Choice.** The user first chose an expected-known quirk. Told that it leaves the executions `known_incomplete`,
  they chose to split per scope (2026-10-21). Rejected: linking the results as copies, an expected-known quirk, and a
  core accounting exemption.
- **Change (Inspect mapper only).**
  - `_register` gives a cache hit's output its own message when another scope produced the message.
  - Later holders in that scope, including pooled `input_refs`, resolve to that copy.
  - Its tool calls are indexed per scope (`split_calls`). `call_part` (tool events, approvals) and `_link_result`
    resolve them by scope.
  - New class D rule `inspect.cached_output_own_message@1` (`inspect_ai` `_model.py` at 0.3.130, 0.3.134.dev31,
    0.3.154.dev37 and 0.3.159.dev20). It is cited on the copy's `generated_by`, the result's `responds_to` and the
    tool execution's `call`.
- **D-31 (owner ruling 2026-10-21).** inspect v2 is edited in place before the round
  (`inspect.cached_output_own_message@1`, item 133, PC-04). No kept corpus records inspect v2. The rule is appended
  after D-601's four rules, in landing order, with no twin (as `inspect.message_copies_share_calls@1`). Condition: this must land
  on main before the round's first kept import of an inspect-family corpus; after that, an inspect change needs v3.
  Scratch corpora recording inspect v2 (10p t1/t2, r107, the 10h and pre-check inspect trials) will report
  `aer.rules.drift` (D-460).
- **Tests.** `tests/adapters/inspect/test_item133_cached_outputs.py` (2; synthetic):
  - a replay in a second scorer scope gets its own message, calls, executions and results, with accounting
    consistent (this test fails on the unfixed mapper);
  - a cache hit in the producing scope keeps one message.

  `regen_pins --write` (inspect, golden-prov, gate-d) left every pin unchanged. `tests/adapters/inspect`, `tests/unit`
  and `tests/golden`: 4,223 passed.
- **Measured impact.**
  - Stored corpus `ast-survey-agentharm-p10` (1,056 executions) has 0 cross-scope cached outputs, so it is unchanged.
  - In the t2 trial, 378 executions hold 985 cross-scope cached outputs (text-only ones included). Their AERs change
    at the round.
  - Re-mapping t2 is for the 10p trial owner. control-arena has no kept corpus.

