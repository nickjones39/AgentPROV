# Phase 10d: AgentDojo-format source profiles and trial imports

Branch `phase-10d`, 2026-10-12. Decisions D-100–D-109 (`docs/architecture/DECISIONS.md`); spec §D.6.17. Inputs: the
phase-10c shortlist (`docs/reports/systematic-search/candidates/agentdojo-format-shortlist.md`, D-90–D-96), the
investigation and verification reports (`AgentPROV/investigation/{sources,verify}/agentdojo-format-candidates.md`), the
phase-10c census (`~/.agentprov/migration-work/phase10c/`) and the pinned staging clones (`~/.agentprov/staging/10c/`;
untrusted data, nothing in them was run).

## What was done

- **19 profiles** (`src/agentprov/adapters/agentdojo/profiles/<id>.profile.toml`; llm-lock added after R4, D-114),
  **12 identity tables**
  (`tables/`), one **`planned` registry part** each (`adapters/registry`, `_phase10d`), one corpus per source (D-94).
  No hook, mapper or core file changed: every profile cites the generic `agentdojo` catalogue (D-101). Routing R8 later
  added `agentdojo.suites@2` and two generic catalogue rules (D-110..D-112; section R8 below).
- **Census** of every full pinned snapshot (all selected logs mapped and sealed;
  `tools/agentdojo/phase10d_trial.py census`), written into each profile's `observed` table and **reconciled with the
  phase-10c census** (`<profile>.census.json`, `<profile>.reconcile.json`; every difference has an explanation).
- **Fixtures**: byte-identical pinned logs chosen by shape (`tools/agentdojo/phase10d_fixtures.py`), with the licence
  texts in `tests/fixtures/LICENSES/`; copyleft sources 2-3 logs with `licence_class = "restricted"` (user-approved).
  Never a log with a secret-like string or a path with whitespace. Tests: `tests/adapters/agentdojo/test_phase10d_sources.py`
  (per source: pin and licence, registry part, closed schema both checkers, quirk rules and census functions, no
  verified code, identity resolution, a synthetic log and every real fixture mapped and validated in release mode with
  **only `_unverified` twins cited for family D rules** (D-24), AER bytes pinned in `phase10d_aer_digests.json`).
- **Trial imports** (D-100): offline, from scratch fetch caches packed from the staging objects (lazy fetch and https
  blocked), through `import_source` in release mode to validation, into scratch corpora (never `~/.agentprov/corpora/`),
  from a snapshot worktree of this branch; a second import at another worker count (the whole tree, or a stratified sample
  whose objects must be byte-identical in the first); `<profile>.trial.json`.

## Results

| Profile | Logs mapped | Variants | Crashes | Census differences (before fill) | Reconciled with 10c | Identity unresolved | Trial import |
|---|---:|---|---:|---:|---|---:|---|
| `aiauthz-agentdojo` | 174 | v1.k14 174 | 0 | 9 | 10 agree, 0 explained | 0 | 174 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |
| `bookkeeper-agentdojo` | 570 | v1.k14 566, v1.k14.incomplete 4 | 0 | 10 | 9 agree, 1 explained | 0 | 570 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |
| `ceferisbarov-agentdojo` | 18442 | v1.k14 18403, v1.k14.incomplete 39 | 0 | 13 | 10 agree, 0 explained | 0 | 4660 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |
| `craibench-agentdojo` | 1163 | v0.k11 1163 | 0 | 5 | 10 agree, 0 explained | 0 | 1163 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |
| `gate-agentdojo` | 3872 | v1.k14 3869, v1.k14.incomplete 3 | 0 | 11 | 6 agree, 4 explained | 217 | 3870 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |
| `geryon-agentdojo` | 3179 | v0.k11 3179 | 0 | 6 | 10 agree, 0 explained | 0 | 3179 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |
| `glitch-agentdojo` | 1844 | v1.k14 1844 | 0 | 8 | 10 agree, 0 explained | 0 | 1844 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |
| `hilarytorn-trajectory-poisoning` | 990 | v1.k14 990 | 0 | 6 | 10 agree, 0 explained | 0 | 990 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |
| `interbolt-agentdojo` | 2016 | v1.k14 2016 | 0 | 9 | 10 agree, 0 explained | 0 | 2016 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |
| `kongminos-agentdojo` | 950 | v1.k14 950 | 0 | 10 | 10 agree, 0 explained | 0 | 950 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |
| `linyxus-agentdojo` | 9068 | v1.k14 9053, v1.k14.incomplete 15 | 0 | 11 | 9 agree, 1 explained | 0 | 4540 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |
| `llm-lock-agentdojo` | 53307 | v1.k14 53307 | 0 | 8 | 10 agree, 0 explained | 53307 | 5337 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |
| `melon-agentdojo` | 1911 | v1.k14 1905, v1.k14.incomplete 6 | 0 | 9 | 9 agree, 1 explained | 0 | 1911 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |
| `menelaus29-ipi-multidomain` | 858 | v1.k14 857, v1.k14.incomplete 1 | 0 | 9 | 10 agree, 0 explained | 1 | 858 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |
| `mohameduk-agentdojo` | 3630 | v1.k14 3630 | 0 | 9 | 10 agree, 0 explained | 0 | 3630 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |
| `sentry-agentdojo` | 674 | v1.k14 670, v1.k14.incomplete 4 | 0 | 9 | 9 agree, 1 explained | 72 | 674 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |
| `shreeyavarma-llm-safety` | 672 | v1.k14 668, v1.k14.incomplete 4 | 0 | 7 | 10 agree, 0 explained | 58 | 672 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |
| `tacit-agentdojo` | 2076 | v1.k14 2075, v1.k14.incomplete 1 | 0 | 11 | 9 agree, 1 explained | 0 | 2076 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |
| `yockcheng-prompt-injection-harness` | 280 | v1.k14 277, v1.k14.incomplete 3 | 0 | 7 | 10 agree, 0 explained | 0 | 280 executions; stages ok; 0 failing checks; jobs 8/3: byte-identical |

Column notes: *Trial import* gives the executions of the first trial corpus (8 workers) and the comparison with the
second (3 workers). Interbolt and MELON were imported whole twice and every corpus file compared (8,202 and 7,656 files,
locks, logs and `derivation.json` excepted). For the other sources the second import is a stratified sample (every 5th log
per pipeline directory) whose AER, SEM, PROV and raw objects must all be byte-identical in the first (`compare --subset`);
Linyxus, ceferisbarov and llm-lock are sampled in both imports (every 2nd and 10th, every 4th and 20th, every 10th and
50th log). 39,394 executions in all, every stage `ok`, 0 failing validation checks, 0 failures, 0 degenerate. gate's 3,872 files hold 3,870 distinct logs
(two byte-identical copies are stored once). *Census differences* counts the placeholders the census replaced in the first profile draft (the
`observed` tables now hold the measured values). *Identity unresolved* counts logs whose model is recorded nowhere
(D-105), sealed `identity_unresolved` with `unk /model not_recorded`.

## R1: defence denials as decisions (2026-10-12; D-113)

Seven profiles declare the generic quirk `agentdojo.defence_denial_message` (`routing.md` R1): 7,204 tool messages are
now deny decisions by their defence, not executed calls (interbolt 1,879, glitch 531, mohameduk 2,731, geryon 773, gate
1,101, bookkeeper 180, aiAuthZ 9). Their censuses over the pinned snapshots reconcile (`r1/<profile>.census.json`), and
their trials were re-run on snapshot `637ec55` (the table rows above): every stage ok, 0 failing checks, byte-identical
between the two worker counts (interbolt again imported whole twice; geryon re-run on `bd35a6f` after its regex was
anchored explicitly, SEC-21, with the same census).

## R9 and R10: `agentdojo.suites@2` for all 19, detector aborts (2026-10-12; D-115, D-116)

All 19 profiles now read `agentdojo.suites@2` (R9): their outcome and marker annotations cite the `_unverified` twins
of regeneration-batch item 1 (class I), tested on every real fixture. llm-lock's detector-aborted runs end with a
`terminate` decision by the detector (R10, new hook point `log_end`): 11,505 runs, of which 1,341 name the request
message because the last turn had several outputs (census `r1/llm-lock-agentdojo.census.json`, no difference). Every
trial was re-run on snapshot `4b79955` (main `45594ae` merged in; the table above): every stage ok, 0 failing checks,
byte-identical between the two worker counts. CrAIBench's R8 counts are unchanged under the extended version 2.

## llm-lock after R4 (2026-10-12; D-114)

`llm-lock-agentdojo` (53,307 logs, GPL-3.0, own corpus): nine defence arms from the path, rows with a defence and no
model (R4), so every log is `identity_unresolved`. The census reconciles with phase 10c (10/10) and, after the draft's
placeholders were filled, with the profile (`r1/llm-lock-agentdojo.census.json`: no difference, no undeclared quirk). The
detector arms either abort the run after a flagged tool output (embedding, hybrid/protectai, llm, multiclass: 11,505
runs, routing R10) or replace that output by AgentDojo's sentinel (both transformer arms, hybrid/qualifire: 13,857
redactions in 5,376 logs, quirk `pi_detector_redaction`); the data-delimiter arm is AgentDojo's
`spotlighting_with_delimiting`. Trial on snapshot `77efc8e`, sampled in both imports (every 10th and 50th log): every
stage ok, 0 failing checks, byte-identical. Three restricted fixtures (user-approved, private repository only).

## R8: CrAIBench on `agentdojo.suites@2` (2026-10-12; D-110..D-112)

`craibench-agentdojo` now reads `agentdojo.suites@2`, whose reviewed tables label the tools of CrAIBench's own suites from
the suite code at the commits that added the runs (spec C.14.8; `routing.md` R8). The trial was re-run on it (the table
row above; snapshot `aabe8e5`): every stage ok, 0 failing checks, the 3-worker sample byte-identical in the 8-worker
import. SEM before and after (`craibench-agentdojo.r8-sem.json`; tool executions by role, tool results by integrity):

| Suite (executions) | Tool executions known (@1 → @2) | Results untrusted / unknown (@2) | Channels (@2) | Taint assessments (@1 → @2) |
|---|---:|---:|---:|---:|
| crypto_trading (1,013) | 0 → 1,994 of 1,994 | 805 / 1,189 | 805 | 1,099 → 1,041 |
| chain (147) | 0 → 105 of 211 | 90 / 121 | 90 | 83 → 82 |
| banking (3, benchmark `agentdojo`) | 5 → 5 (unchanged) | 2 untrusted, 3 trusted (unchanged) | 2 | 2 → 2 |

No result is labelled `trusted` in the new suites. Taint falls slightly because reads such as getTransactions and
read_file are now `content_source` requests instead of `unknown` ones (fail-closed taint subjects); every sink and every
still-unknown chain tool (bridge, stake, airdrop, deploy_token_contract, siphon) remains a subject.

## Not done here

- `docs/reports/phase10d/deferred.md`: EnvironmentOptim (checkpoint identity, training rollouts), Kavach (three branches of one experiment), Figshare (zip input, D-90/D-91); Zenodo deposits and DRIFT runs
  are out of scope.
- `docs/reports/phase10d/routing.md`: R2 `seed_git_cache` lazy fetch, R5 attack-arm field, R6 gate's orphan tool results
  (disclosed), R7 `check_unicode` whitespace (fixed on `main`), R9 the move of the other 18 profiles to
  `agentdojo.suites@2` once item 1 extends it, R10 runs ended by a detector abort (llm-lock). R1, R4 and R8 are done
  (sections above).
- Full imports into `~/.agentprov/corpora/` wait for the regeneration round and the user's approval; the registry parts
  stay `planned` until then (D.3.2).
