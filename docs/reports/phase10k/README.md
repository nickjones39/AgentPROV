# Phase 10k: the credential-leak family (`credleak`, Zenodo 22737462)

Branch `phase-10k-credleak` (from origin/main 733a78f). Decisions D-260..D-268 were proposed in `census.md` §9. On
2026-10-13 the user delegated them to the session ("make the decisions for me"), and the session took them as proposed;
the user then approved them as suggested the same day (recorded in `docs/architecture/DECISIONS.md`). The user approved the v1/v2 download in chat. Specification: `docs/architecture/D_adapters.md`
§D.19.

| Part | Status | Where |
|---|---|---|
| A. Census | done | `census.md` (counts and field paths only) |
| B. Family | done, `planned` | `src/agentprov/adapters/credleak/`, `tests/adapters/credleak/`, `tests/fixtures/credleak/`, `tools/credleak/` |
| B. D-234 end-to-end test | done (single-run cells) | `tests/adapters/credleak/test_withhold_e2e.py` |
| C. Trials | done (C1 exact; C2 re-run to a scratch deposit, limited by R-10k-1; C3 full-size scan estimate: about 15 findings, all read as false positives) | `trials.md`, scratch under `~/.agentprov/migration-work/phase10k/` |
| Routed | R-10k-1 (runner: multi-execution whole-file artefacts; **resolved** by D-320, merged right after phase 10k); R-10k-2 (release-scan allowlist vs gitleaks fragment cuts; **resolved** by D-310, `0b663f3`) | `routing.md` |

**Secrets.** No planted value appears in any committed file, report, test name or commit message. The census process
note in `census.md` records the one transcript slip.
