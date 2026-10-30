## Item 24 (implemented, 2026-10-13; user-approved; D-28 addendum 2): a class-I `unexecuted_tool_call` is pointed at

- **Defect:** the `unexecuted_tool_call` prepass gave `apv:dispatchStatus apv:NotDispatched` no premise field. Under a
  class-I rule the attribute is split into an inference-bundle mention that carries `apv:basisRule` but no
  `apv:sourcePointer`, and tier 4 refuses it (`pv.linkage.pointer_missing`, `pv.linkage.basis_not_cited`).
  - Of the rules cited on that issue, two are class I: `dtap.call_without_result@1` and
    `agentops.fault_injection_unverified@1`. A synthetic DTap trajectory with one unanswered call fails. Phase 10i's
    three fault fixtures fail too, and 555 in-scope AgentOps runs are blocked.
  - The D rules are unaffected: `agentdojo.unexecuted_trailing_calls`, `agentdojo.capture_discarded_reply`,
    `inspect.tool_event_is_execution`, `inspect.message_copies_share_calls`, `openhands.cause_link`.
- **Change:**
  - `prov/engine.py`: the issue `seal/issues/<i>` is the attribute's premise field. Its class and method come from the
    issue's rule (`Ctx.seal_premise`). `_evidence` points at it, and the rule is already the basis through `cited`.
  - `validate/linkage.py`: a pointer into the seal that resolves to an issue counts that issue's `rule` as cited.
  - Spec: E.10 item 23 is amended (a seal issue is addressable), and so is the `apv:sourcePointer` row of E.1.5.
- **Prediction, checked:**
  - Byte-neutral for D rules. The D attribute stays in the core bundle, where statements carry no pointer, and its
    class is unchanged.
  - The golden PROV pins, the gate-D digests, the C.16 vectors and the compat gate pass unchanged.
  - No stored corpus cites a class-I rule on this issue: the stored corpora are AgentDojo-family and AgentHarm.
  - The `prov` and `validate` engine code digests move for every corpus.
- **Tests:**
  - `tests/adapters/dtap/test_mapper.py::test_unanswered_call_is_not_dispatched_with_its_seal_issue_as_premise`: one
    mention with pointer `seal/issues/<i>`, basis `dtap.call_without_result@1`, tier 4 passes.
  - `tests/adapters/agentops/test_mapper.py::test_prov_validates_for_fault_injected_runs`: the strict xfail is removed,
    and all three fault fixtures pass tier 4.

