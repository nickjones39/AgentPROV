## Corpus pre-check wave 1, findings routed to the AgentDojo family owner (2026-10-15; held branch `regen-held-3`)

Routed by the orchestrator from `docs/reports/precheck/` (pre-check branch). The artefact-catalogue entries (14 rows,
`validity_defects` scopes, two new art codes) and ROPE's three stale `manuscript` entries went to a separate session.
- **CC-02 / PC-agentdyn-13** (user decision 2026-10-15, in this window): keep the executions.
  - The AgentDyn suites' private-key-shaped fixture string is benchmark data.
  - Release-scan findings are triaged `synthetic-benchmark` at release (`tools/release_scan.py` triage).
  - No `[withhold]` rule and no profile change. RT-10 is widened to every AgentDyn-suite part: AgentDyn a, b, c,
    ROPE's AgentDyn suites and DRIFT.
  - Datasheet: `datasheet-items.md` row 19, statement `agentdyn-suite-fixture-key`.
- **CC-04 / PC-agentdojo-upstream-04 and -06:** the item-1 table row and the U6-c PROV line above are corrected in
  place, marked *Corrected 2026-10-15*.
- **PC-agentdyn-03** (user decision 2026-10-15): datasheet item for the undefended `gemini-2.5-pro` arm (logged UA
  47.43 vs the paper's 56.95, AgentDyn issue #7). `datasheet-items.md` row 18, statement
  `agentdyn-gemini-2-5-pro-undefended`. Disclosure only; byte-neutral.
- **D-80(d)** (user decision 2026-10-15): its own entry below.

