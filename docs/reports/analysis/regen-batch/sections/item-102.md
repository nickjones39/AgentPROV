## Item 102: D-529 `import --sample` (2026-10-15; user decisions 2026-10-14/15; branch `d529-sample`; lands alone, before the round)

**What moves.**
- `adapters/runner/importer.py` and `adapters/runner/__init__.py` (the `plan_only` and `units` container-job params)
  are in the `aer` stage's code digest, so the `aer` `engine_code_sha256` moves for imports made afterwards. Corpora
  imported before see it as code drift (D-430).
- The `sample_stratum` hooks land as three family-only branches after this one. Each moves its family's
  `adapter_code_sha256` (`inspect`, `autogen`, `credleak`).

**No AER, SEM or PROV byte changes.** An unsampled import passes no new job param and writes no new manifest key or
counter. A sampled unit is mapped by the same job as in a full import.

