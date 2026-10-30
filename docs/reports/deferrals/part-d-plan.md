# Deferrals part D: phase-13 gates (plan, 2026-10-12)

Inputs: J_migration.md J.3 (gate C, C2/C3/C5/C6), J.4 (R3, the reconciliation report), J.5 (gate E); K_testing.md; D-18,
D-21; AGENTS.md "Known follow-ups" and §8 "Manual CI runs"; `docs/reports/phase13/figure-inventory.md` (read only).

## What exists and what is missing

| Gate | Status before part D | What part D builds |
|---|---|---|
| C6 | passes 14/14 (phase 8, D-21); `tools/migration/baseline_probe.py c6`, `migration/c6.py` | re-run on the final commit only when the brief's K.19.1 points require it |
| C2 | not built (D-18) | probe sub-command `c2` (old `validate_prov_document` + `ProvValidator`, 5 checks, on the J.3 sample, the 13 mutation variants and probes a, b, c, e); comparer in `migration/gate_c.py`; register entries `XD-C2-*` |
| C3 | not built (D-18) | probe sub-command `c3` (old `stats.trace_record` + `scoring.score_trace` over all 35,691 traces with the 23 `outcome_replay.json` files); comparer; needs the new rule set `agentdojo.scoring@1/@2` |
| C5 | not built | probe sub-command `c5` (old `convert_run` on the six upstream samples) against the native importer + `render_converted` |
| R3 | not built | `migration/reconcile.py`: `project()` of native vs v1 AERs, per-field classes of J.4.4, lineage records, `ReconciliationReport`; `agentprov migrate reconcile` |
| E full | code exists (`gate_e_semdiff`, `test_semdiff_all`); never run full | run after G0/A/B/D full in `--release` at one clean commit; `tools/gen_semdiff_tables.py` |

## The baseline

The frozen baseline environment already exists locally: `~/.agentprov/baseline/venv-579a908` (Python 3.12.14, wheel
sha256 `3dcf0ed0…` as `migration/baseline.lock.json` pins, built offline from the uv cache). The baseline checkout
`../AgentDojo-PROV-framework` is read, never modified. **No network is needed for C2, C3, C5, R3 or E.** The manual CI
dispatch `old-vs-new` (§8) proves the environment rebuilds from the network; the user triggers it, and its new probe
steps are added to `.github/workflows/ci.yml` by this part.

## The split to agree (through the orchestrator)

`agentdojo.scoring@1/@2` are SEM rules of the `agentdojo` family (B_audit LEG-12, I-40, F-60), so their code is in
`adapters/agentdojo/semantics/scoring.py` and their catalogue entries (`scoring`, `account_confound`, `text_tool_call`,
`unwinnable_cell`, all `reserved` today) in `adapters/agentdojo/rules/agentdojo.rules.toml`: the regen-batch session's
files. Proposed split:

1. **regen-batch session:** `scoring.py` with `score(rec, row, *, run_error, rule_set)`, the catalogue entries moved
   from `reserved` to `active` (version bump per D-31; byte prediction in `regen-batch.md`), and
   `tests/adapters/agentdojo/test_scoring_rules.py`. `@1` is the baseline's `score_trace` verbatim (98 lines,
   `agentdojo_prov/scoring.py` at `579a908`); `@2` adds F-60's DoS gating.
2. **deferrals session:** the probe sub-commands, `migration/gate_c.py`, `migration/reconcile.py`, the CLI
   (`migrate gate-c`, `migrate reconcile`), the register entries, the CI step, the full runs and the reports under
   `docs/reports/migration/`.

Until (1) lands, C3 runs against the baseline only and reports "new side missing"; C2, C5, R3 and E do not depend on it.

## Order

R3 and C5 first (no other session's file), then C2, then C3 when the scoring rules land, then the full release-mode
chain G0 → A → B → D → E at one clean commit (several hours of CPU; scratch outputs under
`~/.agentprov/migration-work/deferrals/`, reports in `docs/reports/migration/`).
