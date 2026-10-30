- **D-281 addendum (2026-10-13, phase 10m implementation): the primary artefact is the response log.** The first scratch
  import with `request.json` as primary collapsed 71 runs as duplicates: request logs repeat byte for byte across
  trials whose requests were the same (1,263 distinct in 1,334: single-request runs of one arm and model). The execution
  id is content-addressed by the primary (C.4.1), so the response log `response_raw.json` (1,334 distinct, the
  provider's own output, never rewritten) is the primary and the request log an auxiliary. Re-imported: 1,334 mapped,
  0 duplicates.
  - **Rejected:** `meta.json` as primary (unique by its run id, but rewritten after the run in 358 runs and not
    carrying the wire variant).
