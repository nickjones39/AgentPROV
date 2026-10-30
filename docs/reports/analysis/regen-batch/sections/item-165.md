## Item 165 (post-round known issue; D-621 amendment 3; recorded 2026-10-22 on the orchestrator's ruling: not fixed before the round; built 2026-10-23 on the held branch `prov-item165-apv-note` together with the apv 0.2.0 note, one prov digest move by user decision 2026-10-22)

| # | Item | Source | Changes | Notes |
|---|---|---|---|---|
| 165 | Two carried-over, unchanged state changes (`apv:EnvironmentCarriedOver`) with the same cause both state `used(cause, predecessor state)` under `aprov.env_call@1`/`aprov.env_pass@1`, so `derive` refuses with `prov.statement_collision` (`prov/rules/edges.py` `_state_change`; found by the D-621 amendment 3 chain test). **Fix before any family adopts `apv:EnvironmentCarriedOver`** | DECISIONS D-621 amendment 3 | prov `engine_code_sha256` when fixed; no stored bytes, since no adapter catalogue declares the assumption | **Built 2026-10-23 (held, class 1).** Fails closed before the fix (a refusal, not a false tier-4 result) |

**The fix.** Each fact is stated once, citing every carried-over state change that supports it. `Ctx.rel(..., merge=True)`
adds a repeat (same rule, section, arguments, path, attributes and discriminator) to the first statement's fields and
citations. `_state_change` uses it for the carried-over `used` and `wasInvalidatedBy` only, so a chain whose first
carried link is unchanged and a fork with the same cause derive too. No relation is added. Rejected alternatives are in
D-621 amendment 3. Regression test:
`tests/unit/prov/test_tier4_bindings.py::test_carried_over_state_changes_with_one_cause_share_one_statement` (4 cases,
all failing with `prov.statement_collision` before the fix, all passing tier 4 after it).

**Same move: the apv 0.2.0 note.** `vocab/apv-0.2.ttl` kept the 0.1.0 `skos:note` saying the w3id registration was
pending. It now says the namespace is registered (perma-id/w3id.org pull request 6836, merged 2026-10-09), and
`dcterms:modified` is 2026-10-23. The same stale sentence in `vocab/apv-adprov-map-0.1.ttl` is fixed too.
`docs/ns/apv-0.2.ttl` follows (`tools/sync_ns.py`). `docs/ns/apv-0.1.ttl` (published 0.1.0) is unchanged.
`prov/vocab.py` needs no regeneration (`tools/gen_vocab_py.py --check` passes): no term changed. Spec E.4.1 and E.4.6 no
longer call the namespace a placeholder (user-guide finding F-5), and C.4.3 (with C.18 item 6) no longer calls the
`w3id.org` base one. This unblocks the apv 0.2.0 publication to `agentprov-ns` from the main that carries this branch.

**What moves.**
- `prov/engine.py`, `prov/rules/edges.py` and both `vocab/*.ttl` files are in the prov stage's `engine_code_sha256`
  (`stage_scopes.PROV_SEEDS`), so it and the prov `fn_digest` move for every corpus at its next derive or recompute.
- Prediction: `sha256:e15f9d9d…6298f0f6` (origin/main `b19897ed`) → `sha256:e4e74db9…9d4fe774` (this branch). Any later
  commit to `prov/` or `vocab/` on either side moves it again.
- The validation digest (`sha256:9baae9be…79e5f913`) and the compat digest do not move: neither scope includes the
  changed files.
- **No AER, SEM, PROV or validation-row bytes change.** `tools/regen_pins.py --check` reports every pin family current
  (golden-prov, gate-d, vocab and ns included). `recompute` reports the move as a code-digest-only change.

**Docs nit, deferred to the next AER-scope change.** The `aer/ids.py` `instance_iri` docstring still says the `w3id.org`
base is a placeholder until the registration is merged. Fixing it moves the AER stage's `engine_code_sha256` (`aer/` is
in `AER_SEEDS`), so it is left for the next change that moves that digest anyway (orchestrator ruling 2026-10-23).
