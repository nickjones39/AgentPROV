# Option B: restoring D for `checker_outcome` (deferred)

**Status:** deferred (user decision, 2026-10-23). It will be reconsidered at the end of the release work, depending on
what the post-check finds in the regenerated corpora. Until then, **Option A (D-359, docs only)** stands: the
regenerated corpora are kept as built.

## What happened

- **The rule:** `agentdojo.checker_outcome@1` lists only AgentDojo commit `c2748856` in its verified code list
  (`task_suite.py` `_check_task_result`, l. 288–308). Logs produced at other AgentDojo commits (`089ed468`, `a75aba7`,
  and Mandate's `fa62a977` harness) therefore cite its unverified twin, `agentdojo.checker_outcome_unverified@1`
  (evidence class I), under item 3 / D-80.
- **The propagation:** D-83 gives a SEM annotation the class of its weakest premise. The security outcome (target
  `j1`, rule `agentdojo.security_polarity@1`) keeps its own D rule, but its `/origin` premise now cites the unverified
  twin, so the outcome becomes **I**.
- **Measured in the regeneration round (built at `5b1f6fdf`):**
  - Mandate: **369** security outcomes D→I. Utility outcomes (`j0`) stay D, 396 of them.
  - AgentDojo head, v1.k14 logs: **11,236** security outcomes D→I. The item-1 correction of 2026-10-15 had predicted
    47.
- **Why it matters:** D-86 rejects twins that "make head and Mandate outcomes I although the code is the same". Item 1
  (D-86 addendum) extended five rules to `089ed468`/`a75aba7`, but not `checker_outcome`. The corpus pre-check had
  already filed this as PC-mandate-agentdojo-eval-04 (documentation mismatch, S3).

The corpora are what the code and the decisions, as built, produce. The I class is conservative, not wrong. Every
check of the round passed, including the byte-identical dry runs at a second worker count.

## Verification already done (read-only, 2026-10-23)

The claim behind `checker_outcome` holds at the other commits:
- **`c2748856`:** `task_suite.py` (blob `bc3eb613`), l. 211–236 `_check_task_result` and l. 288–308.
- **`089ed468`:** `task_suite.py` (blob `da0f3bd1`), the same function at l. 313–338 and l. 400–420. The diff is
  limited to types (content blocks via `get_text_content_as_str`, `FunctionCall`) and the runtime argument; the
  returned value and its flow are the same.
  - `benchmark.py` stores the result along the same path at both commits (`c2748856` l. 110–142, blob `23f4a53c`;
    `089ed468` l. 117–153, blob `162bd6a8`).
- **`a75aba7`:** the AgentDojo 0.1.35 wheel. Its `task_suite.py`, `benchmark.py` and `logging.py` are byte-identical
  to `089ed468`'s and match the wheel's RECORD hashes. The usual a75aba7↔wheel caveat applies.
- **`fa62a977`:** `agentdojo_mandate_eval.py` (blob `9826553a`) calls `benchmark_suite_with_injections` unmodified. It
  subclasses only `ToolsExecutor` and doesn't patch checking or storage.

D-359 records the full evidence.

## What Option B would take (D-31-compliant)

The mapper records the catalogue version it loads, which is always the shipped one, and each profile's
`[import] rules` pin must equal the shipped versions. So a catalogue change reaches every AgentDojo-family import:
1. **Catalogue:** `agentdojo` v3 = v2 plus the code entries for `089ed468`/`a75aba7` on `checker_outcome@1`. v2 is
   archived byte-exact and pinned.
2. **Profiles:** every AgentDojo-family profile declares `agentdojo` 3.
   - **Bumped with archive,** because corpora record them:
     - stored: `adprov-v1` 2→3, `agentdojo-upstream` 2→3, `mandate-agentdojo-eval` 2→3, `rope` 2→3, `survey-runs`
       2→3, `agentdyn` 3→4;
     - scratch: `agentdojo-live` 2→3, `autodojo-live` 2→3, `agentdyn-live` 1→2.
   - **Changed in place:** the roughly 37 profiles that nothing records.
3. **SEM:** `agentdojo.suites@4` (= @2 on catalogue 3) and `@5` (= @3 on catalogue 3). Every registry part moves to
   them.
4. **Re-import:** all 7 AgentDojo-family stored corpora (Mandate, survey, adprov-v1, 2024-06, ROPE, head, AgentDyn),
   then the gate chain G0→A→B→D→E again, because 2024-06 and adprov-v1 are gate inputs.
   - Only Mandate and head v1.k14 change in meaning: the checker `/origin` and the security outcomes go back to D.
   - The other five change in their headers, digests and PROV catalogue attributes only.
   - **Estimate:** about 6.7 h of imports and checks plus about 1.2 h of gates, so roughly **8 h** of machine time at 8
     CPUs, one job at a time.
5. **Checks:** use the round driver with the closed-world expectations (`compare.py` `sem_ev_transitions` and
   `rule_twin_pairs`). Predict every transition first.

The uncommitted Option B work from 2026-10-23 is kept on branch `regen-checker-outcome-b` (`064194ff`, "WIP, NEVER
MERGE"): catalogue v3, the v2 archive and a partial profile cascade. It is a starting point, not a merge candidate.

## Why it was deferred

The post-round class-1 train (item 165 with the apv 0.2.0 note, and the AgentDyn, Inspect and defence cores) moves
the provenance code digest of **every** corpus. After it lands, none of the eight regenerated corpora can be
reproduced from `main`, only at their building commit `5b1f6fdf`: the accepted F-8 / D-430 rule.

So Option B's re-imports are best done **together with** any other re-import that main's reproducibility will need
anyway. That avoids paying the cost twice.

## When to reconsider

Decide at the end of the release work, after:
1. **The post-check** of the eight regenerated corpora (corpus pre-check session) and its readiness verdicts. The
   deciding question is whether the I-classed security outcomes, or anything else it finds, affect the research use of
   Mandate or head, or call for a re-import.
2. **The class-1 train** has landed.

### The options then

- **B with one re-run (preferred if anything calls for a re-import):** land the catalogue v3 cascade, then re-run the
  round for all eight corpora at that main (about 10 h, plus gates). Every stored corpus then matches main, and the
  Mandate/head outcomes are D, as D-86 intends.
- **Keep A:** seal the corpora built at `5b1f6fdf` with the I classes disclosed in the datasheet. They stay
  reproducible at their building commit.
- **B-in-place** (editing `agentdojo` v2 as a D-31 exception) is **not recommended**: it breaks the
  explained/unexplained drift distinction that D-31 protects.

## References

- **Decisions:** D-80 (item 3), D-83, D-86 and its addendum (item 1), D-31, D-354 addendum, D-359, D-430, F-8.
- **Records:**
  - `docs/reports/regeneration/round/` (round outcomes and compare outputs);
  - `docs/reports/analysis/regen-batch/` (items 1 and 3);
  - pre-check finding PC-mandate-agentdojo-eval-04.
