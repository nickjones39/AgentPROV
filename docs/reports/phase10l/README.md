# Phase 10l: the `drift.k18` dialect and mapper (D-96)

Branch `phase-10l-drift`. Decisions D-270..D-279 (proposals for the user until approved).

| Part | State | Where |
|---|---|---|
| A. Census and AER mapping | done; D-270..D-279 user-approved 2026-10-13 | [`census.md`](census.md), [`aer-mapping.md`](aer-mapping.md) |
| B. DRIFT build, `drift` catalogue and profile, census hooks, tests, fixtures | done (user-approved implementation; regen-batch item 21) | spec D.6.19; [`trials.md`](trials.md) |
| C. Registry and trials | `drift` registered (`planned`); scratch mapping trials of every DRIFT source done; product-path imports wait for RT-1 | [`trials.md`](trials.md), [`routing.md`](routing.md) |

Scripts and census outputs (outside Git): `~/.agentprov/migration-work/phase10l/{scripts,census}/`. One fetch, user-approved:
the 1,046 DRIFT history blobs (R-1, 13.2 MB, logged in `acquisitions.jsonl`).
