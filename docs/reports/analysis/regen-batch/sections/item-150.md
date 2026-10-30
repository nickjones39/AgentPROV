## Item 150: D-610, an import that stops early is recorded incomplete (user decision 2026-10-21, option 2, relayed by the orchestrator; branch `integration-incomplete-mark`; held, lands before the round)

**What changes.**
- A run that stops before it ran to the end marks its snapshot `incomplete: {"reason": "drained" | "interrupted"}`
  and the corpus `partial`. `drained` is a D-394 drain; `interrupted` means `run` raised: a first SIGINT, SIGTERM or
  SIGHUP, `stop`, or any error. A drain that NF-36's cumulative cap describes (with a clean tail: its last mapped
  candidate ended in a counted unit) is not marked; an interrupt always is; an earlier mark is never hidden by a later
  cap (review amendment, NF pass, 2026-10-21).
- A later run of the snapshot that ran to the end with nothing left to map clears the mark. It must have mapped and
  had no `--limit`, or found fewer units than its limit.
- `package` refuses a marked corpus (`package.refused.incomplete`), and `derive`/`recompute` refuse it as their
  source (`corpus.derive.incomplete`). NF-36's caps are unchanged.

**What moves.** `adapters/runner/importer.py` is in the `aer` stage's code digest, so the `aer` `engine_code_sha256`
moves for imports made afterwards (class 1; item 130 moves the same digest; corpora imported before see it as code
drift, D-430). `corpus/runstate.py` (new), `corpus/package.py`, `corpus/derive.py` and `cli/import_.py` are class 0.

**No AER, SEM or PROV byte changes.** A corpus no run stopped carries no mark. Only a working manifest a stopped
run left gains the snapshot member.

**Tests.** `tests/adapters/runner/test_incomplete_mark.py`.

**Pre-round review fixes (2026-10-22, branch `integration-fix-cli`; ride items 150, 102 and 128, class 1 through
`importer.py`).**
- PR-6: a re-map never drains (`import_source(..., drain=True)` from `import` only).
- PR-9: a sample's pass 1 lists a multi-execution file sealed whole elsewhere without collapsing it; the D-202 collapse
  (or resume) is applied only when the draw chose its `label#` key.
- PR-11 #3: pass 1 lists a file whose rows are refused (D-321) as one `label#` unit, as pass 2 seals it, so a resumed
  random or spread sample draws over the same keys.
- PR-11 #6: a write-gate rejection after the last counted item breaks D-610's clean tail.
- PR-7 (class 0, `corpus/derive.py`): `--skip-prov-conformance` is part of a recompute's resume identity and reuse key.
- No AER, SEM or PROV byte of an unsampled, unstopped import changes. A sampled corpus no longer lists a sampled-out file
  under the sampled snapshot (PR-9).
- PR-6 and #6 stay riders of item 150 (D-610 addendum). PR-7, PR-9 and #3 have their own rows: items 152–154 below
  (pre-round re-check RC-4).

