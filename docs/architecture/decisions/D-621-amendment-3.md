- **D-621 amendment 3 (2026-10-22, a carried-over state binds to its predecessor; requested by the orchestrator after
  amendment 2; same branch from `122fade2`; regen item 164, amended).**
  - **Defect (test first, confirmed).** Under `apv:EnvironmentCarriedOver` the engine takes a state change's initial
    state from the predecessor it chooses along the AER `after` edges (R-54). It cites the carried state change's own
    fields (`/cause` or `/scope`, `/before_sha256`, `/after`, and the citing record). The statement's endpoints are the
    activity and the predecessor's state entity, so tier 4 failed `pv.linkage.pointer_unbound` on the engine's output:
    - the `env_call`/`env_pass` usage of the predecessor state, and its invalidation;
    - a checker's post-state usage (`outcome`, `apv:CheckerUsesPostState`) of an unchanged carried state, whose
      current state is its predecessor's.
  - **Real-corpus exposure: none today.** No adapter catalogue declares `apv:EnvironmentCarriedOver` (only the
    `aprov` catalogue and the vocabulary name it), so no stored or round corpus can carry over. A family that adopts
    it would have failed tier 4 on every carried-over state change.
  - **Fix.** A new link kind in `PREMISE_LINKS`, `("after", "state_change", "after", …)`: the pointed state change binds
    when a bound state-change record lies in its transitive `after` closure, following the edges the engine follows
    (not ones declared `unk`). It applies to `env_call` and `env_pass` (any pointer of the carried state change) and
    to `outcome` (the record pointer only). An unrelated state change still fails.
  - **Rejected.**
    - Exempting carried-over statements from the binding: it would accept any record as their premise.
    - Binding through `/cause` or `/scope` alone: they name the activity, not the predecessor state that the
      carry-over rests on.
  - **Found, then fixed (regen item 165; held branch `prov-item165-apv-note`, 2026-10-23).** Two carried, unchanged
    state changes with the same cause both stated `used(cause, predecessor state)`, and the derivation was refused
    with `prov.statement_collision`. This was a refusal, not a false tier-4 result, and had no real-corpus exposure
    for the same reason as above. The same refusal hit a chain whose first carried link is unchanged and whose second
    changes, and a fork (two carried state changes after one predecessor, same cause), where both changed ones also
    stated `wasInvalidatedBy(predecessor state, cause)`.
    - **Fix.** Each such fact is stated once. `Ctx.rel(..., merge=True)` adds a repeat on the same rule, section,
      arguments, path, attributes and discriminator to the first statement's fields and citations. `_state_change`
      uses it for the carried-over `used` and `wasInvalidatedBy` only. The statement cites every state change that
      supports it, so tier 4 binds each through the `after` link above. No relation is added: each was already
      stated by the engine for one of the records.
    - **Rejected.** A per-state-change discriminator (two statements with the same endpoints): for the invalidation
      it gives one entity two invalidations by one activity under different identifiers, which PROV-CONSTRAINTS
      unique-invalidation forbids, and for the usage it would assert two usage events that no record shows to be
      distinct. Keeping only the first statement (`once=True`): it would drop the second record's citation.
    - **Class 1 (prov):** the prov `engine_code_sha256` moves (`prov/engine.py`, `prov/rules/edges.py`), in one move
      with the apv 0.2.0 note fix (`vocab/`). The validation digest does not move. No stored bytes change: no adapter
      catalogue declares `apv:EnvironmentCarriedOver`.
    - **Test.** `tests/unit/prov/test_tier4_bindings.py::test_carried_over_state_changes_with_one_cause_share_one_statement`
      (chain and fork, unchanged and changed); it failed with `prov.statement_collision` before the fix.
  - **Class 1:** the validation `engine_code_sha256` moves again (`validate/linkage.py`). No validation row changes,
    since the link only binds pointers that failed before.
