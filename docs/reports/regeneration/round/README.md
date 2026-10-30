# Regeneration round records (D-357)

The round ran on 2026-10-22, after the user's yes (D-350..D-358). It used scope A, the eight stored corpora, through
route (a): fresh pinned imports at **5b1f6fdf**, the `regen-round` worktree, with a clean tree checked before each
run. One queued job ran at a time (`--cpu 8`). The driver is `tools/regen/round/run_round.sh`, with
`tools/regen/round/run_gates.sh` for the gate re-run. The checks follow D-354 and its addendum of 2026-10-22.
Every corpus passed and the gate chain passed. Nothing was sealed, deposited or published. Each old corpus was renamed
`<id>-p10.pre-regen.partial`, never deleted. The new corpora are working trees `<id>-rg1.partial`.

These records hold counts, digests and statuses only:

- The CLI summaries are reduced to their counters, issue codes and exit status. `source_sha256` is the digest of the
  full summary.
- The compare reports drop the keyed multisets that carry annotation arguments (`sem_annotations_net`,
  `prov_attributes_net`, `aer_pointers`). Their sizes and the full report's digest are kept. Counts derived from them
  without any annotation argument are also kept: SEM annotations by kind and class, injection markers by status and
  class, and the `apv:afterCausal` attribute moves. `regen-batch.md` cites these as each item's round outcome.
- In the gate reports, the member-name lists (`*_listed`) are replaced by a count and a digest. Gate D's
  per-execution rows are kept as a line count and a digest.

The timing rows are from `tools/regen/measure.py`. `started` is the machine's local time; the times in this page
are UTC.

## Corpora

| Corpus | Executions | Sealed clean / with issues | Dry run identical (`--jobs 3`) | Strict validation passed | Verify chain | Completeness changes (old → new) | Wall min (import, dry run, validate, verify, compare) | Total min | Peak RSS GiB |
|---|---|---|---|---|---|---|---|---|---|
| mandate-agentdojo-eval | 396 | 396 / 0 | 396 | 396 | ok | none | 0.7, 0.3, 0.2, 0.1, 0.0 | 1.3 | 1.1 |
| ast-survey-agentharm | 1,056 | 1,052 / 4 | 1,056 | 1,056 | ok | verified_complete → known_incomplete 4 (item 11) | 1.6, 1.3, 0.6, 0.2, 0.1 | 3.8 | 1.0 |
| ast-survey-agentdojo | 3,243 | 3,184 / 59 | 3,243 | 3,243 | ok | none | 4.4, 2.5, 1.3, 0.6, 0.1 | 9.0 | 1.3 |
| adprov-v1-release | 17,664 | 17,584 / 80 | 17,664 | 17,664 (4 tiers, see below) | ok | none | 22.5, 12.9, 6.6 (+5-tier run), 3.2, 0.6 | 52.4 | 1.5 |
| agentdojo-upstream-2024-06 | 18,241 | 17,747 / 494 | 18,241 | 18,241 | ok | verified_complete → unverifiable 232 (item 9) | 19.8, 13.1, 7.3, 3.1, 0.5 | 43.8 | 1.3 |
| rope | 10,791 | 9,366 / 1,425 | 10,791 | 10,791 | ok | known_incomplete → unverifiable 322 (D-372), verified_complete → unverifiable 2 (item 9) | 30.7, 13.2, 6.2, 4.1, 0.6 | 54.8 | 1.8 |
| agentdojo-upstream-head | 36,679 | 33,745 / 2,934 | 36,679 | 36,679 | ok | known_incomplete → unverifiable 36 (D-372), verified_complete → unverifiable 232 (item 9) | 47.4, 27.0, 13.9, 6.6, 1.1 | 96.0 | 2.1 |
| agentdyn-a | 38,281 | 36,070 / 2,211 | 38,281 | 38,281 | ok | known_incomplete → unverifiable 825 | 74.1, 38.8, 18.6, 10.7, 1.8 | 144.1 | 2.7 |

The table has 126,351 executions in all.

- **Import:** every import mapped every execution, with 0 failed and 0 degenerate.
- **Dry run:** every dry run had 0 changed, 0 unexplained, 0 failed and 0 unverified.
- **Validation:** every validation (`--strict --tiers aer,sem,prov,linkage`) had 0 failed and 0 checks skipped, with
  linkage resolved for every execution.
- **Verify:** each verify reported only `checksums.absent`, as expected on a working tree.
- **Compare:** each compare against the old corpus had equal execution ids, 0 mismatches and 0 errors, and AER, SEM
  and PROV changed for every execution.
- **Expectations:** each corpus's prediction file is in `tools/regen/round/expect/`, and `compare.py` checks the keys
  a file names. The 232 item-9 transitions on 2024-06 and head are the plan's §1 counts. They were not in those two
  prediction files.
- **Fetch cache:** `acquisitions.jsonl` was unchanged throughout (56 lines, sha256 `928c84d6…fa95f44`), so no import
  fetched anything.

## Gates

| Commit | G0 | A | B | D | E |
|---|---|---|---|---|---|
| 5b1f6fdf (round commit) | pass 12/12 (second run) | pass 8/8, 12.5 min | pass 12/12, 11.7 min | **fail** 34/36, 36.0 min | not run |
| f0410684 (gate-D fix; stage digests equal 5b1f6fdf) | pass 12/12 | pass 8/8, 10.2 min | pass 12/12, 10.7 min | pass 38/38, 29.4 min | pass 108/108, 22.1 min |

Gate D ran at full scope on `agentdojo-upstream-2024-06-rg1` (native, 18,241) and `adprov-v1-release-rg1` (release,
17,664). The 35,905 per-execution rows are digested in `gates/*/D.executions.digest.json`. The two commits' row files
differ, because the fix adds the environment-load metrics to each row.

## Stops and how they were resolved

1. **adprov-v1 validation exited 1.** `validate --corpus` has no `regression` tier, and strict mode counts the skip
   as a failure: all 17,664 executions passed the four tiers that ran (`validate.with-regression.json`). It was
   re-run with the four tiers under the D-354 addendum, with the user's OK, and passed. Gates A and B cover the
   regression round trip.
2. **Gate G0 at 5b1f6fdf first failed** on a missing `environment.baseline_wheel`. The driver now exports
   `AGENTPROV_BASELINE_WHEEL`, and the second run passed. That report overwrote the first under the same name, so the
   failure is recorded here and in the round log only.
3. **Gate D at 5b1f6fdf failed** on two checks:
   - `crosscount.native.activity_records` observed 16,003 against 0 in J.3.5. These are item 5's environment-load
     activities, a stale gate expectation.
   - `inputs.converted.present` failed because the converted tree has no stored AERs (D-49). It is now passed with
     `--accept-gap converted`.

   All 35,905 executions passed the D8 tiers. The user approved fixing it in a separate commit, f0410684 (branch
   `gate-d-item5-crosscount`, with tests). That commit adds `crosscount.{tree}.environment_load_activities`, which is
   observed 16,003 and derived 16,003 on the native tree, 0 and 0 on release. After the last corpus the chain G0 → A
   → B → D → E was re-run at f0410684 and passed. The failing report is kept in `gates/5b1f6fdf/`.

## Re-import after the round: `ast-survey-agentdojo-rg2` (D-771, 2026-10-23)

Post-check finding PC-ast-survey-agentdojo-13 led to D-771 (user decision, option (a)): `survey-runs@3` withholds the
five console logs that hold a third-party home path, at seal and at object scope. The profile was bumped under D-31,
because rg1 recorded v2.

**The run.**
- The user's go was relayed by the orchestrator on 2026-10-23.
- The corpus was re-imported at **d93aa261** (train10, which holds D-771). It ran from a new clean worktree with its own
  `uv sync --locked`, using `tools/regen/round/run_rg2.sh` (the round driver pinned to d93aa261) at `--cpu 6` through
  the queue.
- The checks were the round's (D-354 and its addendum), with the closed-world expectations of D-359:
  `tools/regen/round/expect/survey-rg2.json`.
- **No rename:** `ast-survey-agentdojo-rg1` stays as the evidence copy. It recorded v2, which has no withhold policy,
  so it is never sealed or deposited.

| Check | Result |
|---|---|
| Import | 3,243 mapped: 3,184 clean, 59 with issues, 0 degenerate, 0 failed |
| Dry run (`--jobs 3`) | 3,243 identical |
| Strict validation (4 tiers) | 3,243 passed, 0 skipped, linkage resolved 3,243 |
| Verify chain | only `checksums.absent` (a working tree) |
| Compare against rg1 | ids equal; 0 mismatches, 0 errors; `executions_changed` aer/sem/prov 3,243 |

**Changes against rg1, all as predicted.**
- The AER pointers that changed are only `execution:/profile/sha256`, `execution:/profile/version` and
  `seal:/records_sha256`.
- `sem_ev_transitions` and `rule_twin_pairs` are `{}`.
- Completeness and status are unchanged.
- No issue codes, rule citations, SEM annotations or PROV statements changed in count.
- `acquisitions.jsonl` is unchanged (`928c84d6…`).
- The five withheld objects appear only when the corpus is packaged at seal, which is not part of this run.
- **Stage code also differs.** rg2 was built at d93aa261 and rg1 at 5b1f6fdf, so `derivation.json` records other aer
  adapter and engine digests (`runner/session.py`, `defence.rules.toml`) and another prov engine digest (regen item
  165's `prov/engine.py` and `rules/edges.py`, `ccf2648f`, and the vocab notes). SEM and validation digests are equal.
  The compare shows equal PROV statement counts per bundle kind and type and equal attribute-name counts, so item 165
  collapses no statement here. Value-level PROV equality, with digests masked, is left to the post-check's recompute
  at d93aa261.

**Timing.** Wall times: import 7.4 min (under outside load), dry run 2.7, validate 1.3, verify 0.6, compare 0.1. The
peak RSS was 1.06 GiB.

**Memory reservation.** The first client asked for 18 GiB (3 GiB per CPU) and waited about 30 minutes on the 24 GiB
budget. It was stopped before any job ran and before any tree was written. With the orchestrator's OK it was restarted
with each step's reservation capped at 6 GiB. The run itself was unchanged.

## Re-import after the round: `ast-survey-agentharm-rg2` (D-811, 2026-10-24)

A post-check finding on `ast-survey-agentharm` (S2) led to D-811 (user decision, option (a)). Each of the six `.eval`
headers records Inspect's dataset location under a third-party account's home directory, and only raw holds it.
`survey-agentharm@2` therefore withholds those headers at seal, under object scope, with kexin's rule
`dataset-location-home`. The profile was bumped under D-31, because rg1 recorded v1.

**The run.**
- The user's go was relayed by the orchestrator on 2026-10-24.
- The corpus was re-imported at **5fc39c16** (branch `agentharm-withhold-location`, on train 18's `785c6c28`). It ran
  from a clean worktree with its own `uv sync --locked`, using `tools/regen/round/run_agentharm_rg2.sh` at `--cpu 4`
  through the queue.
- The checks were the round's, with the closed-world expectations `tools/regen/round/expect/agentharm-rg2.json`.
- **No rename:** `ast-survey-agentharm-rg1` stays as the evidence copy. It recorded v1, which has no withhold policy, so
  it is never sealed or deposited.

| Check | Result |
|---|---|
| Import | 1,056 mapped: 1,052 clean, 4 with issues, 0 degenerate, 0 failed |
| Dry run (`--jobs 3`) | 1,056 identical |
| Strict validation (4 tiers) | 1,056 passed, 0 skipped, linkage resolved 1,056 |
| Verify chain | only `checksums.absent` (a working tree) |
| Compare against rg1 | ids equal; 0 mismatches, 0 errors; `executions_changed` aer/sem/prov 1,056 |

**Changes against rg1, all as predicted.**
- The AER pointers that changed are only `execution:/profile/sha256`, `execution:/profile/version` and
  `seal:/records_sha256`.
- `sem_ev_transitions` and `rule_twin_pairs` are `{}`.
- Completeness and status are unchanged.
- No issue codes, rule citations, SEM annotations or PROV statements changed in count.
- `acquisitions.jsonl` is unchanged (`928c84d6…`).

**The withholding forecast (nothing sealed).** `package --dry-run` at 5fc39c16 writes nothing. With its plan captured
in-process (`withhold-forecast.json`), it would withhold **12 raw objects and 0 executions**, all with reason
`personal_data`:
- the six `header.json` members, basis `profile_rule`, rule `survey-agentharm@2:dataset-location-home`;
- their six `.eval` archives, basis `container`.

These are exactly the digests pinned by the census test. The six `_journal/start.json` members also hold the value, but
they are not stored as objects; they leave with their `.eval`.

**Account forecast** (`account-forecast.json`, counts only). Every file of the working tree outside those 12 objects
was searched for the account name (taken in memory from a header, never recorded) and for its `/home/` forms. The
search covered 4,232 files: AER, SEM, PROV, validation, raw and the root files. It found 0 hits, and no stored archive
lies outside the 12. The release scan itself (`tools/release_scan.py`) runs on a sealed corpus only. It waits for the
pre-release step and the user's yes to seal.

**Timing.** Wall times: import 2.3 min, dry run 1.3, validate 0.7, verify 0.2, compare under 0.1. The peak RSS was 0.9 GiB.
