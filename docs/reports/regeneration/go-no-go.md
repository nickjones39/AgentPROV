# Regeneration round: go/no-go on `f24ee223` (2026-10-22)

Prepared for the user's decision in the orchestrator's window. Nothing was started. Plan:
[`plan.md`](plan.md) (method, checks, rehearsal record, D-350..D-358). This page is the decision summary on `origin/main`
`f24ee223`: the pre-round integration (`32c89f96`, verified READY), the rebuild window (`6d789d59`, review rounds 1-3
READY; every stage code digest moved once) and the shared-docs split.

## Verdict

**Code: ready. Round: not yet a GO.**
- Every regen-batch item meant for the round is on `main`. Nothing held is required.
- Two things stand before a GO:
  1. **The re-rehearsal at `f24ee223` (P-8).** My rehearsals ran at `6421c05` (re-map) and `c4fd0dc2` (fresh import),
     both before aer/0.2, corpus/0.2, D-31, D-372, D-410, D-413, D-220 and the rebuild window's digest moves. Route (a)
     has not run on the code the round will use.
  2. **The user's scope and CPU decisions (§5).**
- With P-8 clean and those decisions taken, the round is ready to start on the user's yes.

## 1. The regen-batch list against `main` (read-only audit)

Every item was checked by commit ancestry (`merge-base --is-ancestor`), and held branches by their refs or cited
hashes.

| Class | Items |
|---|---|
| On `main`, meant for the round | 165 numbered items (1-30, 32-151, 153-164, 166, 167 part 1, 168, 169), with all the unnumbered bundles (phase-12b expand, ingest-formats 1-3, D-461, the cli-robustness entry, pre-check wave 1). Every held branch (`regen-held-*`, `bugpass-regen-*`, `review-core-{a,b,d}-regen*`, `phase-10i-context`, `phase-10p-redact`, the artefact-catalogue fixes, `integration/pre-round-2026-10-21`) is in `main` |
| Held but required | **none** |
| After the round, by decision | 165 (carried-over `statement_collision`; before any family adopts `apv:EnvironmentCarriedOver`); 167 rest (`defence-backends-core`); 170 (`inspect-harness-core`); the AgentDyn live core (`agentdyn-backend-core`); the live-pilot B4 status change (`live-pilot-core`); D-219's mapped-task carry-over; land-gate residuals W-1..W-6 (no stored bytes) |
| No corpus effect | 152 (class 0); the "not in the batch" list |
| Never assigned | 31 |

**Loose ends, none blocking:**
- Stale wording for the regen-batch owner: rows U6-a/b/c and 17 still say "proposed"; the phase-12a "proposed, not
  applied" list (F-08 shipped as D-59, the degenerate-header fallback as D-219).
- Missing records for the orchestrator and owners: item 170 has no row on `main`; D-720..D-728 (B4) are not landed;
  D-684 does not say "after the round".
- Three decisions never taken, each defaulting to "not in this round":
  - item 28(ii): carved blobs for ATIA's 42 strings (ATIA is not in scope A);
  - item 26: a quirk citing the AgentDyn nondeterministic-tools artefact (would move AgentDyn AERs);
  - the U6 note: AgentHarm `payload` as `not_applicable`.

## 2. Scope

**Option A (recommended; D-351).** The eight stored corpora: Mandate, AgentHarm, survey AgentDojo, adprov-v1, AgentDojo
2024-06, ROPE (with its AutoDojo slice), AgentDojo head, AgentDyn a. That is 126,351 executions. All eight parts are
`supported`, so `agentprov import` admits them.

**Option B (not recommended for this round).** Option A plus first imports of `planned` sources. The pre-check examined
48 corpora: 40 `ready-with-caveats` and 8 `blocked` (dated 2026-10-21 or earlier).
- The import CLI refuses a `planned` part (exit 5, `cli/import_.py`), so each needs a registry status change first.
- Of the 8 blocked, the security blockers are resolved on `main` for agentops-bench (D-608), autogen (D-603), credleak
  (D-605), dtap (D-607), fragfuse (item 107, D-604) and whistlebench (D-601).
- Still open:
  - redcode-exec-openhands: no archive context tree for `supp`; the withhold rule cannot act yet;
  - mcphunt: PC-01's lineage and disclosure for the 532 copied M0 records; Level 2 never run;
  - whistlebench: D-155 trial-only;
  - several ready-with-caveats parts carry seal-time preconditions or never-seal lists.
- Recommendation: run A, then the planned sources in later waves, each with its registry change, a trial and the
  pre-check's post-check.

## 3. The exact plan (Option A)

### 3.1 Before the round (P-8, on clones and scratch only, `f24ee223`)

One `--class import` / `--class rehearsal` job at a time:
1. **Mandate:** `import --fetch` (D-220, offline). Pass: `git` snapshot origin, `acquisitions.jsonl` unchanged,
   `agentprov-corpus/0.2` and `aer/0.2`. Then `compare.py` against the stored corpus with an expectation file;
   `recompute --dry-run --jobs 2` identical; full strict `validate --corpus --jobs 2` (D-413); `verify --level chain`.
2. **ROPE:** the same through `compare.py`, the dry-run, full strict validate and chain. The 322 retry rows must read
   `unverifiable` (D-372) and B1 must show (`suites@2`).
3. **AgentHarm:** an import with the parent's RSS measured (the spool fix, P-10).
4. `agentprov migrate gate-d --scope golden` at `f24ee223`.

Estimated cost at `--cpu 2`: about 4-5 h, mostly ROPE.

### 3.2 The round

Order, one at a time, each through `tools/suite_queue.py --class import --cpu N --label regen-<id>` (`--jobs N`):

| # | Corpus | Command (all with `--release --jobs N --summary-json <log>`) |
|---|---|---|
| 1 | Mandate | `agentprov import mandate-agentdojo-eval --snapshot head --fetch --corpus ~/.agentprov/corpora/mandate-agentdojo-eval-rg1` |
| 2 | AgentHarm | `agentprov import agent-security-tools-survey --snapshot agentharm --fetch --corpus …/ast-survey-agentharm-rg1` |
| 3 | survey | `agentprov import agent-security-tools-survey --snapshot agentdojo-runs --fetch --corpus …/ast-survey-agentdojo-rg1` |
| 4 | adprov-v1 | `agentprov import adprov-v1 --snapshot release --input ~/.agentprov/migration-work/deferrals/baseline-pristine/corpus/corpus-prov --verify-against-pin --corpus …/adprov-v1-release-rg1` (never the working checkout) |
| 5 | 2024-06 | `agentprov import agentdojo --snapshot 2024-06 --fetch --corpus …/agentdojo-upstream-2024-06-rg1` |
| — | gates | `agentprov migrate gate D --scope full --release` (both trees: 4 and 5), then gate E |
| 6 | ROPE | `agentprov import rope --snapshot head --fetch --corpus …/rope-rg1` |
| 7 | head | `agentprov import agentdojo --snapshot head --fetch --corpus …/agentdojo-upstream-head-rg1` |
| 8 | AgentDyn | `agentprov import agentdyn --snapshot a --fetch --corpus …/agentdyn-a-rg1` |

**Checks after each corpus** (plan §3.3; a failure stops that corpus, keeps its new tree, and does not rename the old):
1. the import summary;
2. `recompute --dry-run --jobs 2` identical (two builds, two worker counts);
3. full strict validation, `validate --corpus --strict --tiers aer,sem,prov,linkage` (plus `regression` for adprov-v1)
   with D-413 workers;
4. `verify --level chain` (only `checksums.absent` allowed on a working tree);
5. `tools/regen/compare.py` against the old corpus with the §2.2 expectations;
6. CORPUS-CHECK-PROTOCOL and the pre-check post-check comparison;
7. for AgentHarm and AgentDyn, re-measuring item 22's classification (plan §7b item 5).

Then rename each old `<id>-p10.partial` to `<id>-p10.pre-regen.partial` (never delete). Sealing is a separate step.

### 3.3 Time, disk, memory (M2 Max, 32 GiB, 369 GiB free on 2026-10-22)

From pipeline-perf's profile (22 CPU-h of import for the eight, nearly all post-AER at about 2.7 us per byte of PROV),
the D-413 validation estimate (about 20 CPU-h) and my rehearsal timings:

| Work | CPU-h | Wall at `--cpu 2` | Wall at `--cpu 6-8`, machine otherwise idle |
|---|---:|---:|---:|
| 8 imports | ~22 | ~11-13 h | ~3-6 h |
| 8 dry-runs | ~22 | ~11-13 h | ~3-6 h |
| full strict validation | ~20 | ~10-11 h | ~3-4 h |
| chain, comparator, gates D/E | ~5 (I/O-bound) | ~4-5 h | ~3-4 h |
| **Total** | **~69** | **~37-45 h** | **~12-20 h** |

- **Disk:** about 44 GB for the eight new corpora (+13 % over today's 38.9 GB, as measured on ROPE), plus a dry-run
  temporary tree of at most ~17 GB at a time. Ample.
- **Memory:** peak tree RSS 1.1 GiB (Mandate) to 2.3 GiB (ROPE) at 8 workers; per-job `prov` cap 4 GiB (D-55). Well
  within 32 GiB.

## 4. D-358: old corpora at their building commit (`afe7038`)

- **Reproduced byte for byte, all eight** (2026-10-23; records in [`d358/`](d358/README.md)). In Mandate, AgentHarm,
  survey, adprov-v1, ROPE, head and AgentDyn, only the input path in `corpus.json` differs. 2024-06, run with its
  original `--fetch --allow-network`, is identical in every file, and nothing was fetched.
- **Cost:** about 5.3 h at 10 workers by the original wall times; roughly 3x that at `--cpu 2`.
- **Not a gate for the round's new corpora:** the old corpora are kept, renamed, and their inputs stay cached, so D-358
  can run before or after the round. It is history, not input to the round.

## 5. Preconditions and decisions

| # | Item | State |
|---|---|---|
| P-1..P-5, P-10..P-13 | merge queue, D-31 bumps + notice-only limits, items 2/4-12 + U6, D-182, spool fix, offline `--fetch`, D-413, F-8/D-430 | **on `main`** |
| P-4 | decided semantics versions (`suites@2`, AgentDyn `@3`, `agentharm@2`) reached by route (a) | decided; checked in P-8 |
| P-7 | no paused import anywhere | check at start |
| P-8 | re-rehearsal at `f24ee223` (§3.1) | **open (blocking)** |
| P-9 | the user's yes for the round | open |

**Decisions for the user:**
1. **Scope:** A (the eight stored corpora; recommended) or B (A plus registry changes and first imports of planned
   sources).
2. **CPU:** the queue default `--cpu 2` (~37-45 h) or `--cpu 6-8` while no other heavy job runs (~12-20 h).
3. **D-358's remaining four:** before or after the round (recommended: after, or interleaved between corpora as the
   queue allows).
4. **The open plan proposals:** D-351 (scope), D-352 (entry gate), D-355 (order), D-356 (failure handling), D-357
   (records under `docs/reports/regeneration/round/`).
5. **The three never-taken item decisions** (item 28(ii), item 26, the U6 `payload`): confirm "not in this round".
6. **Before sealing, not before the round:** adprov-v1's `local` listing-pin origin (its release tree is gitignored at
   `579a908`): keep, or pin a Zenodo deposit of the baseline release.
