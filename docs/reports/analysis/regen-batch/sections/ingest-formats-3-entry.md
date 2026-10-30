## `ingest-formats-3` entry (2026-10-13; D-380–D-387 user-approved 2026-10-13; branch `ingest-formats-3`; design `docs/reports/ingest-formats/nested-design.md`)

**What moves.**
1. `raw/members.py`, `ingest/archives.py` and `ingest/limits.py` are `EXPAND_MODULES`, so the `expand`
   `engine_code_sha256` and `fn_digest` move for **every archive or container corpus** at its next import or
   re-expansion. That covers every Inspect `.eval` corpus (the survey and AgentHarm corpora), every archive input (zip,
   split zip, `tar.zst`, `tar.gz`) and every nested archive. In each, the `expand` entry of `derivation.json` and the
   `fn_digest` field of every `raw/members.jsonl` row change; member digests, labels and dispositions do not. The
   nested-raise validation (`nested_raises`, the `NESTED_*` ceilings) stays in `ingest/limits.py` on purpose:
   `depth_limit` and the raised gate decide what `expand` opens and stores, so they belong to the hashed expand
   function (H.8.2). Moving them out would not keep the digest either, because `raw/members.py` and
   `ingest/archives.py` change too. D-323's profile-wide allowlist is in `ingest/profile_limits.py`, outside the hash:
   its effect reaches `limits_sha256` through the `IngestLimits` values instead.
2. `adapters/runner/importer.py` moves the `aer` stage's `engine_code_sha256` and `fn_digest` for every corpus at its
   next import or re-map.
3. `limits_sha256` does **not** move: no new `IngestLimits` field, because the nested ceilings are constants.
4. `selection_sha256` does **not** move for any selection without declared nested archives.
5. `corpus/stages.py`, `corpus/derive.py`, `corpus/verify.py`, `corpus/rawtree.py`, `corpus/authority.py`,
   `adapters/profiles.py`, `io/workers.py` and `io/worker_testjobs.py` are in no stage digest.

**No AER, SEM or PROV byte of a stored corpus changes.** This was checked on a copy of `ast-survey-agentharm-p10`
with `recompute --out`, run with origin/main `2f4c12b` and with this branch: only `derivation.json` code digests and the
`fn_digest` field of the 1,691 member rows differ (`docs/reports/ingest-formats/nested-calibration.md`). No stored
corpus has an archive input, so the new subject rule for archive members (D-384) moves no register byte.

Merge only when no import is paused (G4), rebased onto origin/main (D-321 and D-323 are in), after the deferrals
session's review of the runner and importer diff (done 2026-10-14). D-323 landed first with D.2.9 note 14, so this
branch's note is item 15 (reserved in the id ledger).

**Contents:**
- archive inputs of container dialects at level 2 (D-380, R-10p-6);
- `[import] nested` with raise-only per-pattern ceilings (D-382);
- inner archives stored as member objects, streamed with commit-on-verify (D-381 (a), D-383);
- chain labels and one subject rule (D-384);
- duplicates (D-385);
- several `expand` entries keyed by `(stage, fn_digest)` (F-2);
- the re-map selection guard;
- a per-job T0 spool-memory bound (calibration finding; per job, not per batch; pipeline-perf's D-414 makes it
  pool-wide).

**Consumer:** phase 10p's control-arena profile adopts `[import] nested` after this merges (3,475 nested-only
samples, plus the 2,267 direct ones that R-10p-6 unblocks).

