## Item 147 (D-307 addendum; orchestrator request 2026-10-21, fail-closed like D-601's `inspect.whistlebench@1`; held branch `bugpass-regen-atia-sem`, child of `bugpass-regen-d601-sem`): the ATIA semantics profile

- **Change:**
  - New semantics profile `inspect.atia@1` (D.9.15; `semantics/inspect.atia-1/tables.toml`, `semantics/atia.py`,
    dispatch in `semantics/__init__.py`). Every tool is fail-closed and no judgement gets an outcome; it cites
    `inspect@2` and reuses `inspect.untabulated_tool@1` (item 146). No rule is added, so the catalogue bytes do not
    change.
  - The registry part `atia-benchmark · logs` names the profile (semantics and caveat). The source profile
    `atia-benchmark@1` is unchanged (digest `e610a5bc0949`), so D-31 bumps nothing.
  - Tests: `tests/adapters/inspect/test_atia_semantics.py` (tiers 3 and 4 on synthetic AERs and, when cached, the
    smallest pinned log), `tests/adapters/inspect/test_atia_seal_e2e.py` (release import, seal, chain verify).
- **Census** (counts only): 7 scratch corpora record `atia-benchmark@1`. The 5 phase-10n trials declare inspect 1 and
  the 2 pre-check L2 corpora declare inspect 2. None is kept. On the smallest pinned log (19 executions, fetch cache),
  the SEM validates in release mode and PROV passes tier 4 for every execution.
- **Order:** it lands after item 146 (it needs `inspect.untabulated_tool@1` in inspect v2), so it inherits item 146's
  condition (a): on main before the round's first kept Inspect import.

| Output | Moves | Count (population) |
|---|---|---|
| SEM (`sem/inspect.atia-1/`) | new | 123 executions |
| PROV (derived with the SEM) | yes | 123 |
| index rows (SEM stage, digests) | yes | 123 |
| SEM stage code digest (`adapters/inspect/semantics`) | yes | every Inspect corpus with a SEM stage (code drift, D-430) |
| inspect catalogue, source profiles, other semantics profiles | no | 0 |
| AER | no | 0 |
| golden pins | no | 0 |

