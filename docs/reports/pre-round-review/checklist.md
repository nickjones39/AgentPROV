# Pre-round integration review: interaction checklist (draft)

Status: **draft, prepared read-only while parked** (2026-10-15). Main at `3a7896d4`. To be re-based on the
orchestrator's integration branch and merge order when they arrive; the branch heads below are the ones seen today.

## Held branches seen today and the focus files they touch

| Branch | Head | Focus files touched | Item / decision |
|---|---|---|---|
| `d529-sample` (+ `d529-hook-inspect`, `-autogen`, `-credleak`) | `ec77695a` (+ `6bd54076`, `ca52b694`, `3f2f88ce`) | runner `importer.py` (+241), runner `__init__.py` | D-529, item 102 |
| `prov-perf-runner` | `4381f3f0` | `importer.py`, `provjob.py`, `corpus/derive.py`, `validation.py`, `validation_job.py`, `verify.py` | D-550 (cache), D-554 profile |
| `bugpass-regen-d451` | `a8e7da89` | `importer.py`, `corpus/derive.py` (scope constants) | D-451 |
| `bugpass-regen-d455` | `f04dd434` | `importer.py`, `corpus/rawtree.py`, `corpus/manifest.py` | D-455, item 101 |
| `review-core-b-regen` | `78cd88a7` | `importer.py`, `corpus/writer.py`, `corpus/manifest.py` | items 57–59 (CB-4, CB-20, CB-22) |
| `review-core-d-rd3` | `e2c237c4` | `importer.py`, `corpus/writer.py`, `corpus/register.py` | RD-3 (CD-5..CD-9) |
| `regen-held-2` | `6ac6b604` | runner `__init__.py` | R-10j-2, item 95, agentdyn@3 |
| `review-core-a-regen` | `373c6099` | `versions.py` | items 60–79, 85, 86 (apv 0.2.0) |
| `bugpass-regen`, `-core`, `-agentops`, `-mcphunt`, `-credleak`, `-openhands`, `regen-held-rd`, `regen-plan`, `review-core-d-regen*`, `review-core-d-c-decisions` | various | adapter families, docs | D-31 bumps, items 33–56 |
| Not yet built or not yet seen: D-530 re-map/CLI (main has the write-up only), D-560, `cli-robustness-pipeline` (D-525 deferred part), `phase-10m-d323`, `phase-10q-ozdincer`, `phase-10o-qwencode` (part C), aer/0.2 | | | |

## 1. `adapters/runner/importer.py` and `runner/__init__.py`

- [ ] **D-529 × D-560**: is `_plan_sample` run before or after exclusions/withholding? A withheld or excluded unit
      must not be counted in `candidates`, take a sample slot, or be re-admitted by pass 2. Check
      `selection.sample.candidates/selected` against the register.
- [ ] **D-529 × D-530**: pass 2 of a container maps "every member as input"; with `--context ROLE=PATH`, are context
      trees passed in pass 1 (`plan_only`) and pass 2 both? Does a context role's object ever become a sample key?
      `StoredRawTree` must exclude R2/R3 objects from primary labels in the sample key set as well (D-530 fold-in).
- [ ] **D-529 × D-455**: a `url` download pin is an archive input; sample keys are `label!/member`. Does `_pin_record`
      / `retrieved_at` survive the sampled pass-2 path (no second fetch, no import-time timestamp)?
- [ ] **D-529 × D-218 / D-414 / D-321 / D-323**: carved blobs and the two-pass result read. Is the D-218 order
      (carve before seal) kept when pass 2 maps only `units`? Spool budget per batch with re-mapped multi-execution
      files; `summarise_unit_frames` heads vs. D-414's pass-1 fate summary.
- [ ] **D-529 × RD-3**: CD-7 (`--limit` takes a multi-execution candidate alone) vs. `--sample` (exclusive with
      `--limit`, but the shared candidate code path); CD-5 collapse of identical members before sampling (sample
      keys of collapsed duplicates); CD-6 disposition for a container with no execution when sampled out; CD-9 resume
      dropping stale map-failure entries with a partial selection.
- [ ] **D-529 × item 58 (CB-20)**: the archive input is stored only if it hashes to its verified pin; pass 1 keeps
      stored files for pass 2, so the check must not run twice or be skipped on pass 2.
- [ ] **D-550 import cache hooks × D-529 / D-560**: is the tier-4 round-trip cache filled for sampled-out or withheld
      units? Is the cache key independent of selection?
- [ ] **D-451** closure constant shared by `corpus/derive.py` and `importer.py`: after all merges, does the pinned
      closure list still equal the ast-recomputed closure (new modules: `stage_scopes`, `validate/cache.py`, any
      D-529/D-530 helper, D-455 manifest code)?
- [ ] **D-525 deferred pipeline** (stage/unit_kind events, drain): events emitted for sampled-out units? Drain between
      pass 1 and pass 2 of a sample (resume must pick the same set).
- [ ] `runner/__init__.py` edits from D-529 and R-10j-2 (`agentdyn@3` corpus spec): textual merge conflict and order.
- [ ] Ordinary (unsampled) imports byte-identical to main apart from the `aer` stage digests (D-529 claim).

## 2. Derive chain: `corpus/derive.py`, `verify.py`, `validation.py`, `rawtree.py`, `writer.py`

- [ ] derive-bugpass (main) × D-550 cache × D-451 scopes: does a cache hit bypass the reuse check that D-451 tightens?
      Is the cache keyed on the D-451 `validation` stage digest?
- [ ] cli-robustness G2c-5 skip (`validation.prov_conformance: "skipped"`) × D-550 cache: a skipped validation must
      not seed the cache; a cached result must not clear a recorded skip.
- [ ] D-530 re-map rebuilds context trees from `snapshot.context[]`; check derive of `expand`/`aer`, `recompute`, and
      `verify --level rederive` all take the same path; `rawtree.py` edits from D-455 and D-530 together.
- [ ] `writer.py`: CB-20/CB-22 (item 58/59) and RD-3 CD-* edits; `manifest.py`: CB-4 counts, D-455 `url` snapshot,
      D-529 `partial`/`selection.sample`, D-530 `snapshot.context[]`, apv 0.2.0 ontology version. Key order and JCS.
- [ ] `verify --level chain` with D-372 class-D loss proof × RD-3 dispositions × D-560 exclusions.

## 3. Versions and digests

- [ ] D-31 bumps: agentops v2, mcphunt v2, agentdyn v3, inspect, foobench (in place). Each catalogue/profile version
      recorded once; corpus specs name the bumped versions (`agentdyn@3` in `regen-held-2`).
- [ ] D-451 closure scopes cover every module edited by a held item (list per item vs. `stage_scopes`).
- [ ] apv 0.2.0 (items 85/86) lands immediately before part C; `corpus.json` ontology version matches `versions.py`.
- [ ] aer/0.2 (part C) on top: every reader of `aer/0.1` paths, golden/gate-D/compat updates confined to part C.

## 4. Digest predictions

- [ ] For each held item in `regen-batch.md` (items 1–102 plus D-ids), compare the predicted byte scope with the
      re-map proof on the integrated tree; flag predictions made against a pre-merge base whose other branches change
      the same digest (e.g. several items each claiming "only the `aer` stage digest moves").

## 5. Redaction and withholding end to end

- [ ] D-182 / D-476 / D-510 redaction: one scratch import per family; no account path in AER, SEM, PROV, register,
      manifest, cache files, event stream or spool.
- [ ] D-450..D-454, D-560 withholding: withheld units leave no AER, no cache entry, no sample slot; `chain
      withheld.unscanned` after rules drift.

## Proofs (after the signal; scratch only, queue at small reservations)

- Every git read of a clone under `~/.agentprov/staging` (blob:none partial clones) uses `GIT_NO_LAZY_FETCH=1`;
  every subagent prompt states it (a missing blob is otherwise fetched from GitHub: network without a yes).

- Re-map a sample per stored corpus on the integrated tree and on main; explain every byte change by an item.
- `recompute --dry-run`; `verify --level chain`.
