## `cli-robustness` GUI-prerequisite pipeline entry (2026-10-14; D-525; branch `cli-robustness`; built: premerge b1ef4098 in the pre-round integration)

The class-1 remainder of the GUI core prerequisites. The user decided on 2026-10-14 that everything outside
`adapters/runner/` is built now (byte class 0, on `cli-robustness`). The pieces below are built once their files are free:
`adapters/runner/importer.py` and `session.py` after `pipeline-perf` (D-414), and `corpus/derive.py`, `validation.py`
and `verify.py` with `cli/checks.py` after `claude/rules-drift` (D-460). They land **before the regeneration round**.

**The pieces.**
- **D-393, import.** `stage` begin/end events for plan, store, expand, map, seal, sem, prov, validate and index, with
  done/total/failed. `unit_done` gains `unit_kind` (`container`/`execution`), so container totals no longer exceed
  100 %. `step` per stage per unit. `session` events from the live session pipeline.
- **D-393, T1 pool.** `progress` passed to `WorkerPool.run`, so `_report_job` emits `worker` spawn/exit (pid, slot,
  tier `t1`, rss peak). Callers: importer, `corpus/derive.py`, `corpus/validation.py`.
- **D-393, verify.** Per-level `stage` events with files/executions done and total (`corpus/verify.py`).
- **D-394, drain.** `control.drain_supported()` and a `control.draining()` check at the unit boundaries of
  `import` (importer loop), `derive`/`recompute` (`corpus/derive.py`) and `run` (`cli/live/campaign.py`, after the
  core-review-C stop flag lands). A true drain exits 0 with outcome `drained`. Until then a drain degrades to a stop
  (built).
- **G2c-5, `--skip-prov-conformance`.**
  - The option: for `import`, `derive`, `recompute` and `run`. It is refused with `--release` (exit 2) and in the
    regeneration round.
  - The import validate stage, `corpus/validation.py` and the live session pipeline skip tier 4 only.
  - The working manifest records `validation.prov_conformance: "skipped"`, written only then.
  - A full `recompute --out NEW --stages sem,prov,validation` writes NEW without the mark (built). `validate` stays
    read-only, and a derive never carries a skipped validation layer (user decision 2026-10-15).
  - Built already: the reader `corpus/conformance.py`, the seal refusal and the verify failure.
  - **Per command and step** (user requirement 2026-10-14: converted and generated corpora alike):
    - `import`: the import validate stage (`importer.py`);
    - `run`, live capture: the validate step of `LiveSessionPipeline` (`session.py`), with the flag parsed in
      `cli/run.py`;
    - `derive` and `recompute --out`: the tier-4 calls in `corpus/validation.py`, from `corpus/derive.py`;
    - `validate --corpus` takes no flag and stays read-only; a full recompute clears the mark.
  - **Refusals:** `--release` (exit 2) on all four commands, `package` seal (built), `verify` (built), and an explicit
    re-check by the `package --deposit` builder, although sealed inputs cannot carry the mark.
  - **The tier-4 validation cache** of the "PROV performance" session sits inside the round-trip branch of
    `validate_prov`. A skipped run never reaches it, so nothing is looked up or written.

- **D-529, `import --sample N --sample-mode first|spread|random --seed S`** (user-approved 2026-10-14). The
  plan stage selects once from the full sorted candidate list, independent of batching (with the CD-7 fix). Each
  family supplies a `sample_stratum` reader hook for `spread`. The working manifest gets `selection.sample`, written
  only when used.

**What moves.**
- `adapters/runner/` is in the `aer` stage's code digest (`code_sha256(["adapters/runner", "aer"])`), so the `aer`
  `engine_code_sha256` moves for imports made afterwards (a `derivation.json` change, as D-321's did).
- If the tier-4 switch lives in `validate/`, the validation stage's `engine_code_sha256` moves too. Prefer a parameter
  of the caller (`corpus/validation.py` and the runner), so that `validate/` is untouched.
- `corpus/derive.py`, `corpus/validation.py`, `corpus/verify.py`, `io/workers.py`, `cli/` and `progress.py` are in no
  stage digest.

**No AER, SEM or PROV byte changes.** Progress events never enter a corpus (D-8 F1). A skipped tier 4 changes no
output byte, only the validation results that are not produced and the mark. For corpora imported before the
entry, `recompute` sees the `aer` stage's `engine_code_sha256` change as code drift, as it did for D-321 (D-430).

