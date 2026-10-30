# Phase 10j, part C: scratch trial imports

Status 2026-10-14. These are scratch corpora only, under `~/.agentprov/migration-work/phase10j/trials/`; nothing is
written under `~/.agentprov/corpora`.

**Method.**
- **Driver:** `tools/agentdojo/phase10j_trial.py`. It calls `import_source` once per part in the profile's part order, in
  release mode through validation, and bypasses only the CLI status gate: the parts stay `planned` (D.3.2).
- **Git pins** are read from a scratch fetch cache seeded from the phase-10c staging clones with `GIT_NO_LAZY_FETCH=1`,
  so no blob can be fetched (D-100's method).
- **Deposit zips** are archive inputs (D-200) built from the staged file after `verify_download` checked it against the
  pin, as `agentprov import --input FILE --verify-against-pin` does.
- **Scheduling:** every run went through `tools/suite_queue.py --class import`. The machine was shared and heavily loaded
  (load about 30 outside the queue), so the times are upper bounds.

## 1. Byte-identical across worker counts (batch A)

Each source was imported twice, with `--jobs 4` and `--jobs 2`, into two corpora that were then compared file by file
(`phase10d_trial.py compare`: every corpus file except logs and locks).

| Profile | Snapshots | Executions | Status | Validation | Register (selection) | Files identical |
|---|---|---:|---|---|---|---:|
| `drift1-agentdojo` | `drift` | 626 | 546 ok, 80 ok with issues | 0 failed checks | 1,569 `select.owned_elsewhere` (drift) | 2,513 / 2,513 |
| `environmentoptim-agentdojo` | `head` | 104 | 104 ok | 0 failed checks | 84,360 `select.owned_elsewhere`, 6,016 `select.redaction_pending` | 428 / 428 |
| `kavach-agentdojo` | `main`, `nav-fixer2`, `rearch-forcedformat-fix` | 2,625 | 2,515 ok, 110 ok with issues | 0 failed checks | 634 `dedup.collapsed` | 10,531 / 10,531 |
| `ipi-defenses-agentdojo` | `head` (3 nested tars) | 3,211 | 3,209 ok, 2 ok with issues | 0 failed checks | — | 12,860 / 12,860 |

- Every import exits 0, with no failed or degenerate execution.
- **Kavach:**
  - `main` maps all 223 of its logs.
  - `nav-fixer2` maps 1,254 and collapses 264 byte copies (223 from `main`, 41 inside the pin).
  - `rearch-forcedformat-fix` maps 1,148 and collapses 370 (223 + 147).
  - That gives 2,625 executions and 634 `dedup.collapsed` entries, exactly as the census predicts (census.md §5). 109
    executions are `identity_unresolved`, the six directories without a model record (D-253).
- **Counts:** every issue count equals the profile census (`tools/agentdojo/phase10j_profiles.py`), e.g. drift-1's 4
  `drift.call_error_unrecognised` and 10 `agentdojo.unknown_top_level_key` (the PACT files).

## 2. Zenodo 23138310 and the chain checks (batches B and C)

**`authority-caps-agentdojo`.**
- **Import** (`--jobs 6`, built on the branch after merging origin/main 9566a207): exit 0, 1,911 s under load.
- **Counts:** 21,999 logs seen and 18,739 executions (18,266 ok, 473 ok with issues). The 3,260 re-packed copies are
  `dedup.collapsed`, as the census predicts (D-250). 0 failed validation checks.
- **Issue counts** equal the profile census: 51 `outcome_imposed_by_runner`, 85 `retry_passes_inferred`, 104
  `unexecuted_tool_call`, 5 `incomplete_run`.
- **`verify --level chain`:** exit 0. 18,739 executions; 22,010 archive members, nested members included; 18,751 raw
  objects re-hashed. The one unverified finding is `checksums.absent`: a working corpus has no `checksums.sha256` until
  it is sealed.

**Drift found in batch B.** Batch B ran `verify --level chain` and `recompute --dry-run` on the Kavach and
ipi-defenses corpora of batch A, which were built before the merge. Both fail, and correctly so:
- main had edited the agentdojo catalogue v2 and the `agentdojo.suites@2` semantics profile in place, so chain reports
  `aer.rules.drift` and `rules.mismatch` (D-460);
- recompute reports every execution as an unexplained change.

This is the F-8 ruling at work (old corpora reproduce at their building commit), not a profile fault. Batch C
re-imports both on the merged code and repeats the checks (below).

**Batch C** (both re-imported with `--jobs 4` on the merged branch, then checked on the same code):

| Profile | Executions | Validation | `verify --level chain` | `recompute --dry-run` |
|---|---:|---|---|---|
| `kavach-agentdojo` (three snapshots) | 2,625 (2,515 ok, 110 with issues) | 0 failed checks | exit 0; 2,649 raw objects re-hashed | exit 0: 2,625 identical, 0 unexplained |
| `ipi-defenses-agentdojo` | 3,211 (3,209 ok, 2 with issues) | 0 failed checks | exit 0; 3,219 members, 3,220 raw objects re-hashed | exit 0: 3,211 identical, 0 unexplained (the stored zip expanded again, nested tars included) |

In each, the one unverified chain finding is `checksums.absent`: a working corpus has no `checksums.sha256` until
sealed.

## 3. Not trial-imported

- **`dca-agentdojo` (Figshare 32657856):**
  - **No trial import:** a `url` pin is not an archive input (routing R-10j-3).
  - **Census instead:** `tools/agentdojo/phase10j_profiles.py census` maps every log under the `member` origin an import
    would give it and seals it with the core writer in release mode. 13,372 of 13,374 `v1.k14` logs and 2,846 of 2,847
    DRIFT logs seal.
  - **The three that do not seal** are routed: two negative logged durations (R-10j-4) and a tool literally named `none`
    (R-10j-5).
- **The 6,016 EnvironmentOptim local-Qwen logs:** `select.redaction_pending` until the shared agentdojo-family redaction
  lands (D-255, D-510 (A); R-10j-1).
