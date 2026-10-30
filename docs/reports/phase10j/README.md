# Phase 10j: AgentDojo-format deposits and repositories deferred by phase 10d

Branch `phase-10j-deposits`, decisions D-250–D-258 (user-approved 2026-10-14; DECISIONS.md), spec §D.6.21.

| File | What |
|---|---|
| [`census.md`](census.md), [`census.json`](census.json) | Part A: per-source census (counts, variants, identity, licence, secret-like counts), the decisions and the outcome of the approved network checks |
| [`routing.md`](routing.md) | R-10j-1 (agentdojo `pipeline_name` redaction), R-10j-2 (AgentDyn history part), R-10j-3 (`url` archive inputs), R-10j-4 (negative duration), R-10j-5 (a tool named `none`) |
| [`trials.md`](trials.md) | Part C: scratch trial imports, byte identity across worker counts, chain checks |

Tools: `tools/agentdojo/phase10j_census.py` (byte census), `phase10j_profiles.py` (profile census, `observed` writer,
fixtures), `phase10j_trial.py` (trial imports). Profiles: `authority-caps-agentdojo`, `ipi-defenses-agentdojo`,
`dca-agentdojo`, `kavach-agentdojo`, `environmentoptim-agentdojo`, `drift1-agentdojo`.
