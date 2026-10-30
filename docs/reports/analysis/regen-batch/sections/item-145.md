## Item 145 (item-7 follow-up; found by artefact catalogues, routed by the orchestrator 2026-10-21; held branch `regen-held-2`): lone surrogates in digested text

- **Defect.** Three digests encoded source text strictly as UTF-8:
  - `agentdojo/mapper.py` `_prompt_variant`, the D.6.6 system-prompt variant digest;
  - `hooks/autodojo.py` `slot_cells`, the payload and wrapped-goal digests against the ROPE cache table.

  A lone UTF-16 surrogate, which the strict loader keeps (C.11.4, item 7), raised `UnicodeEncodeError`. The whole log
  then mapped as `adapter_defect`, a degenerate AER.
- **Fix.** Both encode with `surrogatepass`.
  - Valid text gives the same bytes and the same digest.
  - Text holding a lone surrogate matches no pinned variant or cache cell. For a prompt variant that gives the info
    issue `agentdojo.system_prompt_unrecognised`; for a payload slot, form `none`.
  - No rule or catalogue change.
- **Tests.** `tests/adapters/agentdojo/test_item145_surrogate_digests.py` (2). Both fail on the unfixed code.
- **Census.** The stored corpora hold 0 `adapter_defect` executions: agentdojo-upstream 2024-06 and head, agentdyn-a,
  ast-survey-agentdojo, mandate and rope, all p10, 148,631 executions in all. So no stored AER, SEM or PROV byte
  moves. The agentdojo adapter code digest moves.

