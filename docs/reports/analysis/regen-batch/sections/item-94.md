## Item 94 (D-550, session prov-perf, branch `prov-perf`; push approved by the user 2026-10-14): the tier-4 round-trip cache

**What moves.**
- `validate/cache.py` (new) and `validate/prov.py` (the `fidelity` keyword of `validate_prov`) are inside the
  validation stage's `engine_code_sha256`, so that digest and the stage's `fn_digest` move for every corpus at its
  next import, derive or recompute.
- Prediction: `sha256:d3f9995f…dd372c52` (origin/main `763ddfbe`) → `sha256:a10ee3c1…7b2fd4771` (prov-perf `59023536`).
  Any later commit to `validate/`, `aer/validate.py`, `aer/accounting.py` or `sem/validate.py` on either side moves it
  again.
- `corpus/validation.py`, `corpus/validation_job.py` and `cli/checks.py` are in no stage digest.
- **Later, same item:** the `derive`/`recompute`/`verify --level rederive` call sites (`corpus/derive.py`, class 0)
  come after derive-bugpass lands. The `prov` job and importer call sites (`adapters/runner/provjob.py`, `importer.py`)
  come after D-414 lands; they move the AER stage's `engine_code_sha256` (`adapters/runner`), like item 42.

**No AER, SEM, PROV or validation-row bytes change.** The cache returns the outcome the round trip computed, and the
report bytes are identical with the cache off, cold and warm (`docs/reports/prov-perf/cache-design.md` §6). `recompute`
reports the move as a code-digest-only change, which is not a declared version (H.8.4).

**Expected after it lands (orchestrator note, 2026-10-15).** `recompute` reports validation-stage digest drift for every
stored corpus: the recorded `engine_code_sha256` is the old one. That is expected and harmless, because the outputs are
identical. The prediction holds at origin/main `1fa3f080` (no `validate/` change on main since `763ddfbe`).

**Follow-up push (call sites; branch `prov-perf-runner`).**
- `adapters/runner/provjob.py` (hint input and fidelity frame) and `adapters/runner/importer.py` (stores the frames)
  move the AER stage's `engine_code_sha256` (`adapters/runner` + `aer`). Prediction:
  `sha256:27732f7d…a26f0bdc` (origin/main `fddf6ab1`, after items 102 and D-554) → `sha256:46b11fb4…69289087` (`prov-perf-runner`
  merged with it). Every other importer branch that lands first moves both sides again.
- The validation digest stays `a10ee3c1…`.
- `corpus/derive.py`, `corpus/verify.py`, `cli/derive.py`, `cli/verify.py` and `cli/import_.py` are in no stage digest.
- No AER, SEM, PROV or row bytes change: `tests/corpus/test_validate_cache_import.py` compares whole corpus trees
  with and without the cache.

