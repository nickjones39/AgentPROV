# Pre-round land gate (2026-10-22)

The gate record for landing the pre-round integration branch (`integration/pre-round-2026-10-21`) on `main`.

## Verification

- **Pre-round review:** READY on `66513065` after V-1 (see [verify-66513065.md](verify-66513065.md)).
- **Re-check of V-1..V-7:** READY on `0545657c` (the same report, section "Re-check of V-1..V-7").
- **Earlier condition re-checks:** [report.md](report.md), [recheck.md](recheck.md) and [def-review.md](def-review.md).

## Test gates

| Gate | Head | Result |
|---|---|---|
| Core full suite (`tools/suite_queue.py`, `-n 6`, `-k "not new_family_no_core_change"`) | `0545657c` | 10,158 passed, 98 skipped, 0 failed (15 min 55 s) |
| GUI suite (`gui/`, offline, frozen lock) | `a3851cc5` | 545 passed, 2 skipped (the opt-in Cocoa and real-corpus tests) |
| `tests/repo` | `b1e8d96a` | 62 passed |
| `tools/regen_pins.py --check` | `0545657c` | every pin current |

- **Deselected guard tests:** the 8 `test_new_family_no_core_change` guards are left out of every integration run. They diff a branch against its merge base with `main`, so on a combined branch they list the whole integration as the family's change. They pass again once `main` holds the branch.
- **Commits after the core suite:** everything after `0545657c` is docs only:
  - `74880ae0`, the known-issue record and regen item 165;
  - `734d92af`, the re-check report;
  - this file.

## Stored-byte effects of the land

All of these were approved with their decisions:
- **aprov catalogue v2** (D-621, D-31 addendum): every PROV document changes. Message nodes gain `apv:partOf`/`apv:thread`, and unknown-input usage edges are removed.
- **Validation:** every row gains `pv.linkage.aer_binding` (D-621 #26).
- **Zenodo, HF and URL-origin corpora:** the datasheet, checksums and root digest change at their next seal (D-620, item 156). None is stored.
- **Shipped schemas** move (corpus-0.2 `735207ed`, aer-0.2 `42e7046c`; aer-0.1 and corpus-0.1 unchanged). Views change only for degenerate or withheld-reasoning units, of which 0 are stored.
- **Everything else** is a class 1 code-digest move, recorded in `docs/reports/analysis/regen-batch.md`, or class 0.

No stored corpus is rewritten by the land. The regeneration round regenerates them, with its own approval.

## Residuals carried past the round

These are minor findings W-1..W-6 from the re-check. None moves stored bytes:
- **W-1:** the V-4 residual. A pure-Python re-import of `_posixsubprocess` raises no audit event; G.4.4 should name it.
- **W-2:** the geminicli and credleak real-gitleaks e2e tests should share `needs_pinned_gitleaks`.
- **W-3:** `_aer_only` covers AER-only executions only. Executions extended with `--until sem`/`--until prov` can still gain layers on recompute while the dry run says identical.
- **W-4:** the `after` premise link for env_call/env_pass is not gated on `apv:EnvironmentCarriedOver`.
- **W-5:** records. ab342843's class-1 moves are recorded only in commit messages. Regen item 165 needs its mirror and record. The controlarena v4 profile comment goes with the round's profile edits.
- **W-6:** a NUL in an acquisitions row's store raises an uncaught ValueError. There is no general differential test of the aer-0.2 schema against the validator.
- **Known issue (item 165):** a carried-over `statement_collision`. Fix it before any family adopts `apv:EnvironmentCarriedOver`.
