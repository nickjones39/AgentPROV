# Parallel `validate --corpus`: a `validate` job kind (design D-413, for review)

Status: **reviewed** (runner: OK; deferrals: OK with changes, applied in §3.3, §3.6 and §7). User-approved 2026-10-14.
Built on 2026-10-14, merged into `pipeline-perf` for its push.

## 1. Why

`validate --corpus` runs every tier in the CLI process. Measured CPU (profile.md):

| Corpus | Per execution | Whole corpus | Measured |
|---|---|---|---|
| Mandate | 0.69 s | 274 s predicted | 291 s |
| ROPE | about 0.97 s | about 2.9 h | regen-plan's 2,000-execution sample |

95% of that time is tier 4 and 86% the PROV round trip, which is pure per-execution work. Across the 126k stored
executions this is about 34 h on one core, so the regeneration round validates samples only (regen-plan F-3). Tier 4
parallelises across executions with nothing shared.

## 2. Spec drift found on the way

G.4.2 lists the job kinds `expand`, `map`, `sem`, `prov` and `validate`. The code has `expand`, `map` and `prov` (plus
test kinds). The `prov` job does SEM annotation, derivation and tiers 3–4 for the importer and `derive`. This design adds
`validate`. `sem` stays folded into `prov`; the spec should say so (a G.4.2 note).

## 3. Design

### 3.1 Split of work

| Where | What | Share of CPU |
|---|---|---|
| Parent (T0), index order | sampling; reading every stored document through `CorpusReader`; the **AER tier** (`AerValidator` with the corpus raw store, `verify_on_read`); staging; aggregation, comparison with the stored rows; summary | about 3–5% |
| T1 job `validate`, one per execution | the **SEM tier** (tier 3) and the **PROV and linkage tiers** (tier 4) over the handed documents | about 95% |

The AER tier stays in the parent, as in the importer and `derive` ("the AER validator runs in the parent"). It needs the
corpus raw store for locator checks, and a worker gets no access to it (§3.3). It is about 0.01–0.03 s per execution.
Even with it, the parent's serial share caps the speed-up at about 25–30×, well above any worker count used here.

### 3.2 The job

- Kind `validate`, `JOB_KINDS["validate"] = "agentprov.corpus.validation:job_validate"`, loaded by name like the other
  kinds, before the audit hook (G.4.4). The module preloads every shipped semantics profile at import, as `provjob`
  does (`load_all_semantics_profiles`).
- Inputs, by digest, re-hashed by the worker (G.4.5):
  - role `aer`, the stored AER bytes;
  - role `sem` per profile, in the order of `semantics`;
  - role `prov`, the stored `agentprov-prov/0.1` bytes, present only when the row has PROV.
- Params: `tiers` (the subset of `sem`, `prov`, `linkage`), `mode`, `semantics` (refs, in order), `sem_inputs` (refs
  whose SEM was handed; the others failed to read in the parent), `has_prov`.
- Output: one JSON frame `{"checks": {id: status}, "spec"?, "versions"?}`. These are ids and statuses only, never
  finding text, as the stored rows hold today.
- RSS cap: 4 GiB, the `prov` value, because tier 4 grows about 80–90 MiB per MB of PROV-JSON (D-55).
  - **As built:** the cap is set on the validate pool only (`corpus.validation.VALIDATE_LIMITS`). The global
    `KIND_RSS_BYTES` stays `{"prov": 4 GiB}`, so every other pool's limits and caps record are unchanged.
  - That record reaches `agentprov info` and two pinned tests; no corpus or gate output stores it.
  - `max_rss_bytes` is 4 GiB either way, so the derived worker count is the same.

### 3.3 The parent hands every input (no new access)

The parent already reads and verifies every document in T0 today (`aer_bytes` plus `load_aer_bytes(verify=True)`,
`read_sem`, `prov_bytes`, with digests checked against the index). It now also `put`s **the exact buffer it read and
verified** into a private scratch `RawObjectStore`. It never re-reads the file, so a change to the corpus file after the
read cannot reach the job (TOCTOU). (a temporary directory, mode 0700, as `derive` does). The pool's `store_root` is that scratch
store's `objects/` and nothing else, and each batch's objects are removed after use.

- **No new write path:** workers keep `RLIMIT_FSIZE = 0`, and the parent writes only its own temporary directory,
  never the corpus.
- **No new store access:** a worker sees only the copies it was handed, by digest, re-hashed on read. It never sees
  the corpus or its raw store.
- **Launch unchanged:** `-I -B`, rlimits, the environment allowlist and the audit hook.
- **Less parsing in T0 than today:** tier 4 (`prov`, `rdflib`) and tier 3 move out of the CLI process. The parent's
  remaining parsing is the AgentPROV-format reads it does today (G.4.1 row T0).

### 3.4 One code path for both modes (byte identity by construction)

`corpus/validation.py:_validate_row` is split into:

1. `_read_row(reader, row, ...)`: parent-only. Reads, verifies and runs the AER tier. It returns the partial `out`,
   the documents, and the read failures (`aer.read:*`, missing or unreadable SEM, missing PROV), exactly as today.
2. `validate_documents(aer, sems, prov_bytes, tiers, mode, semantics, profiles)`: pure. Tier 3 and tier 4 plus the
   linkage split. It returns the `checks`, `spec` and `versions` that `_validate_row` adds today.
3. `_finish_row(...)`: the verdict and `failing` logic, unchanged.

The in-process path calls 1, 2 and 3 in order. The job calls 2 on the handed bytes, after `load_aer_bytes(verify=True)`
and `load_sem_bytes(verify=True)`, the same loaders `CorpusReader` uses. The parent then calls 3. The two paths share
every function that decides a status.

### 3.5 Ordering, results, exit codes

- Rows are processed in index order, in batches (256, as `derive`), and job keys are the zero-padded position in the
  row list. `WorkerPool.run` returns results sorted by key, so aggregation (counters, `failures`, notices, the stored-row
  comparison, progress `unit_start`/`unit_done`) happens in the parent in index order. That is the same sequence as
  today.
- The report document has no worker count, isolation or timing field today, and none is added. `json.dumps(...,
  sort_keys=True)` and the JCS row digest do not depend on dict insertion order.
- Exit codes are unchanged: 1 when any row fails or a strict run skipped a tier, otherwise 0.

### 3.6 What changes only on failure

A worker that is killed (`worker.limit.rss`, `cpu`, `wall`, `output`) or crashes has no in-process counterpart: the
in-process path would raise in the CLI (`MemoryError`, exit 70) or run on. With workers the row becomes a failing row:

- `checks["validate.worker"] = "fail"`;
- `failing = ["validate.worker"]`, so `failing` stays a list of check ids;
- the failure code `validate.failed`, exit 1;
- a report notice naming the execution and the limit code (`worker.limit.rss` and so on).

This is recorded and never silent ("seal, don't discard"). The check id `validate.worker` is registered in N.2.5 and the
G.4.2 note. Rows hold only ids and statuses, and no spec section closes the list of check ids.

**Evidence that stored corpora stay inside the cap (deferrals review, item 2).** Tier 4 peaks at about 80–90 MiB of RSS
per MB of PROV-JSON (D-55, `docs/reports/hardening/prov-rss.md`). Largest stored `agentprov-prov/0.1` document per
corpus, measured 2026-10-14 (file sizes only):

| Corpus | Documents | Largest PROV |
|---|---|---|
| agentdyn-a-p10 | 38,281 | 3.98 MiB |
| adprov-v1-release-p10 | 17,664 | 3.78 MiB |
| ast-survey-agentdojo-p10 | 3,243 | 3.19 MiB |
| rope-p10 | 10,791 | 2.68 MiB |
| agentdojo-upstream-head-p10 | 36,679 | 2.11 MiB |
| agentdojo-upstream-2024-06-p10 | 18,241 | 2.11 MiB |
| mandate-agentdojo-eval-p10 | 396 | 1.21 MiB |
| ast-survey-agentharm-p10 | 1,056 | 0.35 MiB |

The worst case is 3.98 MiB × 90 MiB/MB, about 360 MiB: more than 11× under the 4 GiB cap. No stored row can fail under
the cap where it passes in-process today. The 4 GiB cap is also the one every `prov` job ran tier 4 under at import
(KIND_RSS_BYTES, D-55).

**Known future case (runner review).** An execution whose PROV inlines a large tool result nears the cap at about 45 MB
of PROV. MCPHunt's largest traces (44.8, 24.4, 24.4 and 19.5 MiB) would reach it until phase 10m carves their large
strings (RB-3). Until then such rows become recorded `validate.worker` failing rows, never silent passes or drops.

### 3.7 CLI

- `validate --corpus` uses the pool, with `--jobs 0` meaning the host default (N.1.10). The existing `--jobs` help text
  ("accepted; validation runs in this process for now") becomes "worker processes (0 = host default)".
- `--in-process` (new for `validate`) keeps today's path exactly. It is allowed with `--release`, because it is the
  AD-10 row 17 option (SEM, PROV and validation in T0 over validated documents, G.4.9). It is not the G.4.9 debugging
  mode.
- `--release` uses `WorkerPool(release=True)`: isolation grade `watchdog` or better, otherwise exit 3, as for import.

## 4. Identity proofs (all before merge)

1. **Differential test** (new, `tests/corpus/`): the golden mini-corpora and a small built corpus, `validate --corpus`
   in-process versus `--jobs 1` and `--jobs 3`. The report bytes, the summary JSON (minus timing) and the exit codes
   must be identical. Cases:
   - every tier;
   - each tier alone;
   - `--strict`, `--release`;
   - `--sample/--seed`;
   - a corpus copy with a tampered PROV file (digest mismatch, a read failure);
   - a removed SEM file;
   - a PROV file that fails tier 4.
2. **Scratch corpora:** Mandate and ROPE clones, in-process versus `--jobs 8` and `--jobs 3`, with a byte-diff of the
   `--report` documents.
3. **Golden, gate D, compat and C.16** run unchanged. `validate/` is not touched, so the validation stage
   `engine_code_sha256` does not move: `corpus/validation.py` is not in it, and the `validate` stage covers
   `validate/`, `aer/validate.py`, `aer/accounting.py` and `sem/validate.py`.

### 4.1 Results (2026-10-14, branch `pipeline-perf-d413` on `2fbdd367`, under shared load)

| Corpus, mode | In-process | `--jobs 3` | Report |
|---|---|---|---|
| Mandate scratch import (396), dev | 461 s | 249 s | **identical**, 1,272,391 B; 396/396 stored rows reproduced |
| Mandate, `--strict` | 663 s | 185 s | **identical**, 1,274,110 B |
| ROPE clone, `--strict --sample 300 --seed 1` | 674 s | 368 s | **identical**, 1,060,124 B |

- All 300 ROPE rows fail `aer.validator` with `aer.blob.digest`, the same in both paths. The unchanged pre-D-413 code
  (`8e6d632f`) gives the same 20 of 20 on a sub-sample, and current main with the D-31 bumps passes them.
  **Explained (regen-plan, 2026-10-14):** this is validator-side version drift, not a corpus defect. The code is
  AER-V35, the `/profile/sha256` check against the package's profile digest. `rope@1`'s profile bytes were edited in
  place after the building commit `afe7038` (regen-plan F-1). D-31's archived `rope@1` restores the recorded digest, and
  200 evenly spaced stored AERs validate with 0 errors at `afe7038`. No action is needed.
- The parent's AER tier is unchanged, and a byte-identical failing report also covers the failure path.
- The 8-worker timings come with the D-415 calibration in the quiet window.
- After merging onto current main, the proof is repeated on the merge commit.

## 5. Expected effect

| Case | Workers | Wall time |
|---|---|---|
| Mandate (291 s today) | 6 (the 32 GB default) | about 55–60 s |
| ROPE (about 2.9 h) | 6 | about 30 min |
| All 126k stored executions (about 34 h) | 6 | about 6 h |
| All 126k stored executions | M5 Ultra preset (proposal) | about 1.5–2 h |

With these numbers, full instead of sampled validation becomes a real option for the round (regen-plan F-3).

## 6. Files

| File | Change |
|---|---|
| `io/workers.py` | the `validate` entry in `JOB_KINDS` (the cap is the validate pool's own, §3.2); no stage digest |
| `corpus/validation.py` | the split of §3.4 and `job_validate`; in no stage digest |
| `cli/checks.py` | `--jobs` and `--in-process` wiring |
| `docs/architecture/G_security.md` | the G.4.2 note |
| `docs/architecture/MN_repo_cli.md` | N.2.5 |
| tests | the differential and the job tests |

Owners: `corpus/` and `cli/` have no current branch claim. `io/workers.py` is not shared with the runner session:
D-320, D-321, D-324 and D-323 change `adapters/runner`, `ingest/jsonstream.py`, `ingest/profile_limits.py`,
`adapters/profiles.py` and `cli/derive.py`. The only common surface is the `JobContext` API (`read_input`,
`open_input`), which neither side changes.

## 7. Reviews

- **Runner session (2026-10-14): OK, no changes required.**
  - No frame conflict: a `validate` job's single `{"checks", …}` frame never reaches the map-frame parsing
    (`split_unit_frames`, `outcome_from_frames`, `_aborted`).
  - `KIND_RSS_BYTES["validate"] = 4 GiB` equals `prov`, so `max_rss_bytes` and the derived worker count do not move.
  - `read_input` re-hashes the whole object in the worker, which is fine under the cap. A later move to `open_input`
    for streaming keeps the same store-first guarantee.
  - The §3.6 note on large PROV documents was added at its request.
- **Deferrals session (2026-10-14): OK with changes, all applied.**
  1. Profile lookups: the pool is used only with the package's default lookups. When a caller injects
     `semantics_profile` or `source_profile_sha256` (tests), validation runs in-process. The worker resolves each ref
     with the same default function (`load_semantics_profile(*parse_profile_ref(ref))`, cached per worker), so an
     unresolvable profile gives the same `<ref>:profile = skipped`. The differential includes that case.
  2. The evidence for §3.6 is the largest-PROV table above.
  3. Failing-row shape: `checks["validate.worker"] = "fail"`, `failing = ["validate.worker"]`, and the limit code in
     a notice. The id is registered in N.2.5 and G.4.2.
  4. TOCTOU: §3.3 says the parent puts the exact buffer it verified. A test tampers with the file between the read
     and the job and shows the job validated the read buffer.
  5. Linkage: no change.
  6. The scratch store is a `tempfile.mkdtemp` directory (0700), removed in a `finally`, as `derive` does.
  7. The differential includes a killed worker (a `validate` RSS cap forced low).
