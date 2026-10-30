# Ingest formats 3: container members of archive inputs and bounded nested-archive reads (design)

Date: 2026-10-13. Branch `ingest-formats-3` (from origin/main `2f4c12b`). Status: **built** (2026-10-13). D-380–D-387
were user-approved on 2026-10-13 with the deferrals session's review changes, and D-381 is option (a). The decisions as
built are in `docs/architecture/DECISIONS.md` and the calibration in `nested-calibration.md`. §12 lists where the build
differs from this design.
Routed needs: R-10p-1 (nested zips, phase 10p §7) and R-10p-6 (archive inputs of a container dialect, added by the
orchestrator on 2026-10-13). Review path: the deferrals session (runner owner), then the user. Decisions D-380 to D-389 are
**proposals** until the user approves them. Pattern followed: D-57/D-58 (bounded nested reads), D-200/D-249 (archive
inputs), D-243/D-244 (split zips), D-60/D-245 (calibration).

Inputs read: AGENTS.md §0 and §4; DECISIONS D-57–D-60, D-200–D-204, D-218 (branch `deferrals-carved`), D-240–D-249,
D-320, D-323 (`r10k1-followups-design` §3) and D-360 (branch `fixture-cap`); `design.md`, `followup-design.md` and
`calibration.md` in this directory; phase 10p's README at `e898057` (§3, §7). The staged control-arena archive was read
only through `agentprov.ingest`, and only counts, sizes, methods, offsets and timings were recorded. No member name or
content was printed (scripts and outputs: `~/.agentprov/migration-work/ingest/nested-probe/`).

## 1. What has to be read

### 1.1 Two gaps, one mechanism

| Gap | Shape | Today | Samples |
|---|---|---|---|
| **R-10p-6 (depth 2)** | an Inspect `.eval` (a container dialect) that is a member of an archive input: a split zip (D-249) or a `tar.zst` (D-247) | the runner refuses it (`adapter.archive_input`, exit 5, `_Pipeline.__init__`; D-200's documented refusal, MN N.2.2) | the 2,267 samples (436 logs) that phase 10p calls "readable" |
| **R-10p-1 (depth 3)** | an `.eval` inside a zip inside the split zip (5 nested zips), or inside a zip inside a `tar.zst` | the nested zip is over `max_member_bytes` (4 of 5), or its `.eval` sits at depth 3 > `max_archive_depth` 2 (all 5) | 3,475 (928 logs) |

Depth counts from the pinned input: the archive input is level 1, a zip member of it is level 2, an `.eval` inside that
zip is level 3. The `.eval`'s own members (`header.json`, `samples/*.json`) are leaves.

### 1.2 What the staged bytes are (probe of 2026-10-13, counts only)

| Container | Nested archives | Method in the parent | Uncompressed sizes (B) | Inside |
|---|---|---|---|---|
| split zip 3-001 | 4 zips | **deflate (8)**, flags `0x808` (data descriptor, UTF-8); csize/usize ≈ 1.0001 | 549,930,938; 312,462,190; 907,073,041; 2,913,118 | 1,380 entries, all deflate; 420 `.eval` (max 16,500,834 B) |
| split zip 3-002 | 1 zip | deflate, `0x808` | **2,091,106,621** (56,377,027 B under 2 GiB) | 2,069 entries, all deflate; 535 `.eval` (max 7,883,494 B); CD 529,789 B |
| split zip 3-003 | none | | | |
| `apr2026_backup…tar.zst` (not pinned, D-342) | 4 zips | tar member | 153,159; 146,697,367; 151,021,027; 157,316,895 | byte duplicates or empty logs only (phase 10p §3.2) |
| `logs_batch_runs…tar.zst` | none (110 `.eval` at level 2) | tar member | `.eval` max 12,990,070 | |

So:
- the nested zips inside the split zips hold **955 `.eval`**: 928 original, 20 byte duplicates and 7 without a header.
  Phase 10p's 3,475 samples are in them. None is empty and none holds a deeper zip;
- every nested zip is **deflated**, never stored. A plain byte-range view over the parent cannot read it, so random
  access needs either the inflated bytes or a seekable inflate (§2);
- every nested zip fits under `max_artefact_bytes` (2 GiB), so it can be stored as one raw object;
- the `tar.zst`-nested zips are all under `max_member_bytes`. They need only the depth allowance, and none is pinned
  today.

## 2. How an inner archive is read without extraction (D-381: the user's choice)

The `expand` stage already handles a nested archive at level 2 for small members (`Selection.nested`): the member is
stored as its own raw object, with a `member` origin, and a fresh T1 job opens that object by digest (G.4.5) at level 2.
That path fails here for two reasons. The job reads a selected member whole before it sends the header (D-58), which
caps the member at `max_member_bytes` and, at 2 GB, would exceed the 2 GiB worker RSS cap. And level 3 is refused.
There are two bounded ways to read the inner zip.

### Option (a), recommended: store the inner archive as its member object, streamed with commit-on-verify

- **Worker (`job_expand`).** A selected member that matches a declared nested-archive pattern (§3) and whose declared
  size is above the global `max_member_bytes` is **streamed**. The job emits its `$member` header with
  `"streamed": true`, then `DATA` frames of at most 1 MiB as `ZipFile.open` inflates it. It ends with one JSON frame:
  `{"end": {"index": i}}` once `zipfile` has checked the CRC-32 and the byte count equals the declared size, or
  `{"abort": {"index": i, "code": "ingest.…", "reason": …}}` on any member-level defect (CRC, size, decoder). Members at
  or below the global bound keep today's read-whole-then-send path, byte for byte.
- **Parent (`_consume`).** A streamed member counts only with its `end` frame. Its bytes are then stored through
  `RawObjectStore.put_chunks(expected_size=, expected_crc32=)`, which computes the size and CRC-32 again and publishes
  nothing on a difference (`ObjectMismatchError`). With `abort`, or with no closing frame, the spool is discarded and
  the member gets a `rejected` row with the code. **No partial object is ever published**, which is what D-58's rule
  protects. The frame protocol of `io/workers.py` is unchanged: any JSON frame closes the open member, and the per-member
  cap of `_collect` comes from the job limits, which are raised for this job to the pattern's raise (§3).
- **Then** the stored inner zip is expanded as a level-2 container: the same G.3.5 sequence on a seekable store handle,
  re-hashed at open. Each `.eval` it selects is stored and expanded at level 3 by the container path (§4).
- **Memory (expected; to be calibrated, §7).** Worker: the split-zip job baseline (D-245: 223 MiB peak for 2.95 GB
  selected) plus one 1 MiB chunk and `zipfile`'s inflate buffers, flat in the member size. Parent: the
  `SpooledTemporaryFile` spills to disk after 8 MiB. Its directory becomes the store's `tmp_dir` (same filesystem, no
  cross-device copy; an `io/workers.py` constructor argument). Transient disk is at most one member (2.09 GB). No buffer
  grows with the member.
- **Cost.** The raw store grows by the inner zips: **3.86 GB** for control-arena, on top of the 5.08 GB of parts. Every
  level is then a stored, content-addressed object with a `member` origin. Every later re-read (the level-2 job,
  `verify`, `recompute`) is an ordinary read of a stored object.

### Option (b): a seekable inflate view over the parent member, with no intermediate object

- `ingest/seekable.py`, stdlib only: one pass inflates the member's raw-deflate range of the parent handle with
  `zlib.decompressobj(-15)` and saves a `Decompress.copy()` every 8 MiB of output, with its input offset. The same pass
  checks the CRC-32, the declared size, the end of the deflate stream and that no input is left over. Then
  `zipfile.ZipFile` opens a read-only view whose reads resume from the nearest checkpoint (forward reads continue the
  current decoder). A stored (method 0) member is a plain range view. A zstd member (93) is refused: its decoder has no
  copy.
- **Measured on the staged bytes** (prototype, in process, `open_zip` over the view, every `.eval` streamed with its
  CRC): the 2,091,106,621 B member was indexed in **1.0 s** wall (0.7 s CPU) with 242 checkpoints (about 9 MiB of
  decoder copies). Its 535 `.eval` streamed in 10.0 s wall (5.0 s CPU) with 6 restarts and 4.21 GB inflated (2.0×).
  **Peak RSS of the whole process was 61 MiB** over all five nested zips. All five CRCs matched.
- **Bound needed.** A hostile central directory in non-offset order makes every member read restart at a checkpoint.
  The view therefore needs an inflate budget (for example 3 × usize + one checkpoint interval per member) with a new
  code `ingest.archive.seek`. Benign writers read in offset order (6 restarts above).
- **Cost.** There is no raw-store growth, but the inner zip is never a stored object. Its members' `member` origins
  would name a container that `verify --level chain` cannot find (D-244 states the same problem for split zips). It
  needs a stored **nested descriptor** (`{"format": "agentprov-nested/0.1", "container", "label", "method", "crc32",
  "size", "sha256"}`) and a new origin kind. `raw/origins.py`, `corpus/rawtree.py`, `corpus/verify.py`,
  `corpus/withhold.py` and C.3.12/H.1.4/H.2.3 would change, and every re-read re-inflates the parent member. A
  `tar.zst` parent cannot use it (no zstd decoder copy), so tar-nested archives would need option (a) anyway.

### Option (c): depth only

Allow level 3 under a declared pattern, but leave members above `max_member_bytes` refused. Only the 2.9 MB nested zip
opens: 1 log, 5 samples.

**Recommendation: (a).** It adds no origin kind, descriptor or `verify` logic. Each level is the D-200/D-204 data model
that every level-2 container already uses, so recompute, `rederive`, `chain`, withholding and purge need no new case.
It also works for a tar parent. Its cost is 3.86 GB of local raw store. D-57 rejected a stored intermediate `.tar` for
two reasons: the duplication, and the lack of an origin kind for a decompressed tar. The second does not hold here,
because a zip member already has the `member` kind. (b) is the better choice if store size matters more than core
changes; the prototype shows it is cheap and bounded.

### 2.1 Checks at every level (option (a))

| Level | Object | Checks |
|---|---|---|
| 0 | each byte part | pinned sha256 and size (D-249); the descriptor digest is computed from them (D-244) |
| 1 | split zip (logical) | declaration gate, then G.3.5 unchanged: EOCD/CD size pre-check, `zipfile` with warnings as errors, member count, prefix, overlap, member gate |
| 1→2 | the nested zip as a member | gate with the pattern's raised size/ratio (§3); inflate CRC-32 and size in the worker (`zipfile`); size and CRC-32 again in the parent before publishing; stored by sha256 |
| 2 | nested zip (stored) | re-hashed at open (G.4.5); G.3.5 unchanged; depth allowance from the pattern |
| 2→3 | each `.eval` | member gate (global limits); CRC-32 and size (worker and parent); stored by sha256 |
| 3 | `.eval` (container dialect) | re-hashed at open; G.3.5; members gated with the reader's member patterns |
| 4 | samples, header | CRC-32 and size; stored by sha256; parsed by the Inspect reader through the strict loaders |
| any | every member object | `verify --level chain`: CRC-32 and size against its `raw/members.jsonl` row (existing) |

## 3. Gating: `[import] nested` (D-382)

A new key in the closed `[import]` set (`adapters/profiles.py` `_IMPORT_KEYS`, beside `blobs` and D-323's `limits`),
validated at profile load:

```toml
[[import.nested]]
id = "logs-zips"                       # unique within the profile; children name their parent by it
pattern = "logs/*.zip"                 # a member of the archive input (or of `under`) that is itself an archive
under = ""                             # "" = the archive input; otherwise the id of another [[import.nested]] entry
max_member_bytes = 2_147_483_648       # optional raise: the nested archive's own size as a member of its parent
max_ratio = 200                        # optional raise of the same member's compression ratio
max_depth = 3                          # optional raise: the deepest archive level opened at or below this archive
note = "five zips of whole run directories inside the split zip (phase 10p §3.2)"
```

- **What is selected inside** is the profile's ordinary archive selection (`include`, `blobs`, context globs), matched
  against the inner labels, plus the nested entries whose `under` names this one. A nested archive is stored and
  expanded, never mapped. A member that matches both a nested pattern and `include` is refused at load (ambiguous).
- **Raise-only, with fixed ceilings.** Only the three keys above can be raised. Each must be at least the global
  default (a lower value is refused: it would be a narrowing the gate does not implement) and at most a constant in
  `ingest/limits.py`. A validating function `nested_raises(table) -> NestedRaises` lives there too, so `adapters/` holds
  no limit logic (D-323's condition 2):

| Constant | Value | Basis |
|---|---|---|
| `NESTED_MAX_DEPTH` | 3 | the deepest observed shape (`tar.zst` or split zip → zip → `.eval`); a deeper source needs a decision |
| `NESTED_MAX_MEMBER_BYTES` | 2 GiB | `max_artefact_bytes`: under option (a) the inner archive becomes one raw object; the largest observed is 2,091,106,621 B |
| `NESTED_MAX_RATIO` | 1,000 | deflate's limit is about 1,032; the observed ratio is about 1.0, so control-arena needs no ratio raise |

- **The global limits never change.** The raises are not `IngestLimits` fields. They travel in the expand selection
  (`Selection.children`, §5.1) to the job of the parent container, and only for labels that match the pattern. So
  `limits.to_json()`, `limits_sha256` and `corpus.json` `limits` are unchanged, and the raises are committed to through
  `selection_sha256` (expand) and `profile_sha256` (aer). D-323's `[import] limits` allowlist must never contain
  `max_member_bytes`, `max_ratio` or `max_archive_depth` (§6.1).
- **Load-time refusals** (`ProfileError`): an unknown key; a pattern that fails `Selection`'s rules (at most two `*` per
  segment, F-08); a duplicate `id`; an unknown `under`; a cycle; a raise below the default or above its ceiling; a
  `max_depth` that the entry's own level already exceeds; and `nested` in a profile whose import is not an archive
  input (a git-tree container dialect keeps today's container path, D.2.9 note item 5).
- **Under a tar parent**, a selected member is read whole in pass 2 (D-57), so a size raise above the global bound is
  not streamed. Such a member is rejected `ingest.archive.size` (with its `limit_field`), not silently capped. No
  observed source needs it.

## 4. Container members of an archive input (R-10p-6, D-380), and the depth-3 case on the same path

1. **Expand the archive input** (D-200/D-249) with the selection tree: the root is the archive selection plus the
   top-level `[import] nested` entries. A nested archive is stored and expanded with its child selection, recursively,
   inside the same `expand_containers` call, at its absolute level. The call returns, for every container, its **chain
   label**: its labels from the input down, joined with `!/` (`corpus.rawtree.MEMBER_SEPARATOR`).
2. **Candidates** are the selected leaf rows of every container in the tree (not the nested archives themselves). Each
   carries its chain label (for example `<zip label>!/<eval label>`; a direct member keeps its plain label), its
   `member` origin (container = its immediate parent; label = its own label only), its absolute level and the depth
   allowance of its chain (the largest `max_depth` on it, else the global 2). `_MemberTree` is keyed by chain label, so
   a truncated direct `x.eval` and a complete nested `x.eval` never collide.
3. **The container dialect.** The refusal in `_Pipeline.__init__` is removed. `map_containers` runs as it does for a git
   tree (the same batching, `_store` collapse and resume checks, and `plan`), with one difference: its `ContainerSpec`
   carries `depth` (the candidate's level + 1) and `max_depth` (the chain's allowance). `expand_containers` starts each
   spec at its own level, and the job passes `max_depth` to `open_archive`, which refuses a level above
   `min(max_depth, NESTED_MAX_DEPTH)` and above the global limit when no allowance is given. So a direct `.eval` opens at
   level 2 (no raise needed), and a nested one at level 3 only under a declared `max_depth = 3`.
4. **Map.** Unchanged: one container-mode map job per `.eval`, with `header.json` as the auxiliary artefact.

The `.eval`'s own expansion uses only the reader's member patterns, and neither the level nor the allowance enters its
`fn_digest`. So an `.eval` gives the **same member rows, objects and AERs** whether it was found in a git tree, directly
in an archive, or nested. Only its own `member` origin row and its register subject differ.

The archive-level `include` for a container dialect is the profile's `include`, or the reader's default (`**/*.eval`
for Inspect, as `InspectEvalReader` already uses) when the profile declares none.

## 5. Naming, origins, register, recompute and verify (D-384)

### 5.1 Labels and identities

- **Labels stay labels.** Every level's member name goes through `logical_name` as today. A chain label is a register
  and display key, never a path. A member whose label contains `!/` cannot sit in a chain at level 2 or below (a nested
  archive, or a candidate under one): it is rejected `ingest.name.invalid` with the reason "label contains the member
  separator". Level-1 behaviour is unchanged, so no existing corpus moves. The calibration counts such labels in
  control-arena (expected 0).
- **`Selection`** gains `children: tuple[(pattern, Selection, NestedRaises), …]`. `digest()` adds a `children` member
  **only when it is non-empty**, so every existing `selection_sha256` is unchanged. Rows carry the `fn_digest` of the
  node that expanded their container (as `selection_at(d)` already does per level today).
- **`derivation.json`** gets one `expand` entry per distinct node `fn_digest` used, in tree order. For control-arena that
  is the archive's tree and the `.eval` member patterns. The frozen derivation shape (an array of tagged stages) already
  admits this. But `corpus/derive.py` `_stages_of` keys stages by name, so a second `expand` entry would be dropped
  there (finding F-2, §8).

### 5.2 Origin chain (option (a))

| Object | Origin (`raw/origins.jsonl`) |
|---|---|
| byte part | `hf {repo, revision, path: <part file>}` (D-249) |
| split descriptor | `split {archive: zip, label: <logical file>, parts: [...]}` |
| nested zip | `member {container: <descriptor>, label: <zip label>, method: 8, crc32, size}` |
| `.eval` | `member {container: <nested zip sha>, label: <eval label>, method, crc32, size}` |
| sample / header | `member {container: <.eval sha>, label: samples/…, …}`: the origin the AER cites (D-204) |

Every link is a stored object, and a re-read never parses in T0. An `.eval` found at two places has two `member`
origin rows. No origin kind and no AER field is added (`aer/0.1` is untouched).

### 5.3 Register subjects

`{snapshot_id, path}` with `path` = `<input label>!/<chain label>[!/<member>]`. A rejected nested member gets
`…!/<zip label>!/<member>`, or `#<index>` for a rejected name. A container plan row gets
`…!/<chain>!/<member>`. A collapsed duplicate gets its own chain subject.

### 5.4 Recompute and `verify`

- **`recompute` / `verify --level rederive`.** `StoredRawTree` replays the archive input (`input.kind = archive`, with
  `parts`). The importer re-expands the descriptor with the selection tree rebuilt from the profile at its recorded
  version. Every nested object is re-derived by digest (`put` is idempotent), and every row and origin comes out the
  same (expansion is ordered by job key, not by worker count). Nothing reads the old member objects as inputs.
- **`verify --level chain`.** No new check. Every `raw/members.jsonl` row at every level has its member object's CRC-32
  and size checked (the nested zips included: 3.86 GB read once). The "outermost container" walk (`_containers`)
  already climbs several levels. Two cases need a test (F-3): a member object listed under two containers (a byte
  duplicate nested and direct), and that its snapshot set is the union.

## 6. Interactions (D-385, D-387)

### 6.1 D-323 (`[import] limits`, `parse_stream`)

D-323 raises chosen **global** `IngestLimits` fields for the whole import. Its allowlist and ceilings are in
`ingest/limits.py`, it is recorded in `corpus.json` `limits`, and it moves `limits_sha256`. D-382's raises are **scoped
to a pattern**, travel in the selection and never touch `IngestLimits`. The two key sets stay disjoint: `nested_raises`
refuses a field in D-323's allowlist, and D-323's allowlist must not admit `max_member_bytes`, `max_ratio` or
`max_archive_depth` (the brief's "global limits never change"). `parse_stream` (RB-1) reads a stored primary by digest,
so a whole-file member found at level 2 or 3 is streamed exactly like a top-level file. The leaf bound stays the global
`max_member_bytes`: a nested raise applies to archives, never to leaves.

**File overlap with the runner session.** Both designs edit `adapters/runner/importer.py` (D-380 here, D-321/D-323 and
R-10p-5 there). This session does not touch `runner/__init__.py` or its frames. The proposed merge order is the runner
session's D-321/D-323 first, then this branch rebased onto them, with the deferrals session reviewing both diffs.

### 6.2 D-218 (carved blobs)

A carve takes a primary input of the map job, which here is a sample member object, never a container. So carving is
the same at any level. `rawtree`, `withhold` and `derive` already treat a carved object and a member object alike, as
derived objects.

### 6.3 D-320 (multi-execution) and collapse (H.7.2, D-202)

Source keys are `sha256 + loc` of the primary member object, and an `.eval`'s member objects do not depend on where it
was found (§4). So:
- **A byte duplicate in the same snapshot** (one `.eval` digest, nested and direct in one split zip): the second
  candidate collapses in `_store` (`this_run`): `dedup.collapsed` "already selected in this snapshot", with its own
  `member` origin row. The `.eval` is expanded and mapped once. Candidates go in chain-label byte order, so the result
  is deterministic; the AER bytes do not depend on which copy is first.
- **Across snapshots** (for example a nested copy in 3-001 and a direct one in 3-002): D-202's collapse
  (`_seen_before`), unchanged.
- **The 199 nested byte duplicates:** 179 are in the apr2026 backup, which is not pinned (D-342). The other 20 collapse
  as above.
- **The 279 truncated or empty direct `.eval` with a complete nested copy** are different bytes. The direct file is a
  candidate whose level-2 expansion fails (`ingest.archive.format`: no end record, or zero bytes) and is registered
  `not_imported`. The nested copy is imported. **No relation between them is recorded or inferred** from the shared
  file name (invariant 2), and they are never conflated. Accounting stays `candidates = executions + not_imported`.
  Phase 10p may describe the pattern in the profile's note and its report.
- **Withholding (D-344 (a)).** `corpus/withhold.py` already withholds a container transitively when a member is withheld
  (`containers()` loops). So each nested zip and `.eval` object that holds a withheld sample is withheld. **But the byte
  parts of a split archive are not linked to their descriptor there** (finding F-1, §8), and that predates this design.

## 7. Calibration and tests (D-386)

**Calibration** (the D-60/D-245 method; a fresh T1 worker, `workers=1`, default limits plus the declared raises;
synthetic, seeded inputs under `~/.agentprov/migration-work/ingest/calib-nested/`):

1. **The largest shape.** A 2.0 GiB split zip (8 parts) holding one deflated inner zip of 1.95 GiB (500 small
   `.eval`-shaped zips, half random and half text) plus 50 direct `.eval`. For each job (outer streaming, level-2,
   one level-3) measure worker CPU, wall and peak RSS, parent RSS, spool disk and store write time, against G.4.3's
   budgets (540 s CPU and 1,080 s wall at `with_expand_scaling(max_total_bytes)`). Pass: at least 10× headroom and an
   RSS that stays flat as the inner size doubles (1 GiB vs 2 GiB).
2. **Option (b)** if the user picks it: the same inputs through the view, adding the hostile central-directory-order
   case against the inflate budget.
3. **Real bytes (needs the user's yes):** an `expand` of the staged split zip 3-002 (largest inner member,
   2,091,106,621 B) into a scratch store, recording counts and timings only, nothing printed. Its parts are already
   staged, so nothing is downloaded.

**Tests** (synthetic, built at test time in `tmp_path` within D-360's caps; nothing under `tests/fixtures/`). Streaming
is forced by a test `IngestLimits(max_member_bytes=64 KiB)` with a 1 MiB pattern raise, so archives stay at tens of KiB.

| Test | What it shows |
|---|---|
| Differential | One `.eval` placed (i) in a git-tree import, (ii) directly in a split zip, (iii) in a deflated zip in a split zip, (iv) in a zip in a `tar.zst` gives identical `.eval` member rows, objects, `fn_digest` and AER/SEM/PROV bytes. Only the `.eval` origin row and the register subjects differ. Streamed vs non-streamed transfer of one inner zip gives the same stored object |
| Depth bomb | Self-similar `**/*.zip` nesting with `max_depth = 3`: level 4 is `ingest.archive.depth` and never opened; `max_depth = 4` is a `ProfileError` at load; a zip that contains itself by digest is expanded once (`done`) |
| Ratio and size bombs | Above the pattern's ratio: rejected before decoding. A central directory that understates the size: `zipfile` stops at the declared size (`ingest.archive.size`/`.crc`). A streamed member above the job cap: `worker.limit.output`. Raises at ceiling − 1, ceiling and ceiling + 1 (K.5.6) |
| CRC at an inner level | A flipped byte inside a stored deflate block of the inner zip's stream: `abort`, `ingest.archive.crc`, nothing published, siblings kept. The same at level 3 (one `.eval`) and level 4 (one sample) rejects only that member |
| Protocol | A streamed member with no `end`, with `end` for the wrong index, or with extra `DATA` after `end`: `expand.protocol`, nothing published |
| Tamper | A changed, replaced or missing nested-zip or `.eval` object fails `verify --level chain` (`raw.member.crc32`/`.size`, missing object); `rederive` on a fresh store reproduces the digests |
| Resume | An import stopped after the outer expansion and one batch of `.eval` resumes to the same bytes as an uninterrupted one (`skipped_resume`); `--limit` counts samples across levels |
| Determinism | `--in-process`, 1 and 3 workers, batch sizes 1 and 256: byte-identical corpora |
| Duplicates | Nested + direct in one snapshot: one execution and one `dedup.collapsed`; across two snapshots: D-202's collapse; truncated direct + complete nested: one `not_imported` plus one execution, no relation |
| Profile validation | Every load-time refusal of §3 |
| Labels | `!/` in a chain label is rejected; a nested `x.eval` and a direct `x.eval` stay distinct candidates |
| Phase 10p | Its strict xfail (a synthetic split zip of a synthetic `.eval`) flips when D-380 lands |

## 8. Findings outside this session's files (routed through the orchestrator)

- **F-1 (corpus/withhold.py, medium; before any control-arena release).** Withholding propagates from a member to its
  containers, but a split descriptor's **byte parts** hold the member bytes and are not linked. A release that withholds
  every control-arena execution (D-344 (a)) would still ship the parts, with the planted keys inside deflated streams
  that text scanners miss. The parts of a descriptor whose member is withheld should be withheld too (and `verify`'s
  `withheld.present` should check them).
- **F-2 (corpus/derive.py, low).** `_stages_of` keys `derivation.json` stages by name, so a corpus with two `expand`
  entries (§5.1) would compare only the last. Needed before D-380 lands, or a single combined entry instead (the
  alternative in §9).
- **F-3 (corpus/verify.py, test).** A member object listed under two containers (nested and direct duplicate) needs a
  `chain` test for the snapshot union and the "outermost container" walk.

## 9. Downstream effects (regen-batch entry `ingest-formats-3`, recorded with the build)

| What changes | Digest that moves | Corpora affected |
|---|---|---|
| `raw/members.py`, `ingest/archives.py` (`max_depth`), `ingest/limits.py` (constants, `nested_raises`) are `EXPAND_MODULES` | `raw.members.engine_code_sha256`, hence every `expand` `fn_digest` at the next import or re-expansion | the four `ast-survey-agentharm*` corpora's member rows (`fn_digest` field only; digests, labels and dispositions unchanged) |
| `adapters/runner/importer.py` (D-380) | the `aer` stage `engine_code_sha256` | every corpus at its next import or re-map, as every runner change |
| `adapters/profiles.py` (`nested` key) | none (in no stage digest) | — |
| `io/workers.py` (spool directory argument) | none | — |
| `selection_sha256` | unchanged without `children` | — |
| `limits_sha256` | unchanged (no new `IngestLimits` field) | — |

No AER, SEM or PROV byte of a stored corpus changes: none has an archive input of a container dialect or a nested
pattern. Merge only when no import is paused (the G4 identity check compares both stage identities). The raw store of
a control-arena corpus would be about 8.9 GB under option (a), or 5.1 GB under (b), plus member objects in both cases.

**Alternative for F-2:** one `expand` entry whose `selection_sha256` is the root tree's digest, with the `.eval` member
patterns as a node of that tree. Its cost: an `.eval`'s rows would then carry the tree's `fn_digest`, so they would
differ between a git-tree import and an archive import (a `raw.members.conflict` if one corpus held both), and §4's
location independence would be lost. Not recommended.

## 10. Proposed decisions (D-380–D-389; proposals for the user)

- **D-380** Archive inputs of a container dialect (R-10p-6): absolute levels from the pinned input, chain-labelled
  candidates, `ContainerSpec.depth`/`max_depth`, and the `.eval` expansion independent of its location (§4). This
  removes D-200's exit-5 refusal; MN N.2.2 and the D.2.9 notes (items 5 and 10) are updated.
- **D-381** Inner archive access, **the user's choice** (§2): (a) stored intermediate member object, streamed with
  commit-on-verify (recommended); (b) checkpointed inflate view plus a nested descriptor and origin kind; (c) depth
  only.
- **D-382** `[import] nested`: closed keys, load-time validation, raise-only per pattern, `NESTED_MAX_DEPTH` 3,
  `NESTED_MAX_MEMBER_BYTES` 2 GiB, `NESTED_MAX_RATIO` 1,000 in `ingest/limits.py`; global limits unchanged (§3).
- **D-383** (if (a)) The streamed-member transfer: `"streamed"` header, `end`/`abort` frames, publish only after both
  the worker's and the parent's CRC/size checks; the spool goes in the store's `tmp_dir` (§2).
- **D-384** Labels, `!/` refused in chain labels at level 2 and below, origin chain, register subjects,
  `Selection.children` digest rule, one `derivation.json` `expand` entry per node `fn_digest` (§5).
- **D-385** Duplicates: collapse by object digest, location-independent AERs, no relation inferred between truncated
  and complete copies (§6.3).
- **D-386** Calibration and tests (§7), and the regen-batch entry with the predictions of §9.
- **D-387** Interactions: the `[import] limits` (D-323) and `[import] nested` key sets are disjoint; nested raises
  never reach leaves; carving is unchanged; the merge order is after the runner session's D-321/D-323 (§6).
- D-388–D-389 are reserved.

## 11. Questions for the user (after the deferrals review)

1. **D-381:** option (a), (b) or (c)? (Recommended: (a). Its cost is 3.86 GB of local raw store; (b) saves that but adds
   an origin kind, a descriptor and changes to `verify` and `withhold`.)
2. **Calibration on staged bytes:** may the calibration expand the already-staged split zip 3-002 (8 parts,
   2,147,478,676 B logical) into a scratch store under `~/.agentprov/migration-work/ingest/calib-nested/`, recording
   counts and timings only? No download is involved, and the scratch store is removed afterwards with your yes
   (inspect-before-delete).

## 12. As built: differences from this design (2026-10-13)

1. **No reader default include.** An archive input of a container dialect must declare `[import] include`: there is no
   reader accessor for the Inspect default `**/*.eval`, and adding one would be an adapter change.
2. **Globs match each member's own label.** The reader's include, exclude, context and blob globs are matched against
   a member's own label, the label `expand` matched at its level, not against its chain label (§4 item 2). Otherwise a
   nested member would need globs that know the archive structure.
3. **The re-map guard compares selections.** It does not compare profile digests (review item 4). A re-map refuses
   when the archive selection rebuilt from the shipped profile is not among the source's recorded `expand` selections.
   A profile change that keeps the selection still re-maps, as the 41d7a2f fix intends for the regeneration round.
4. **No load-time overlap check.** Glob intersection is not decidable in general, so a load-time check for "matches
   both include and a nested pattern" (§3) is replaced by precedence: a child pattern wins. `nested` in a profile
   whose input is not an archive is refused at import (exit 5), because the input kind is not known at profile load.
5. **Size raises under a tar parent** are refused at the member gate (`ingest.archive.size`), as §3 says. This is
   tested at the unit level only; no observed source needs it.
6. **`package._stage`** is never called with `expand` and is unchanged. Stage maps in the importer, `derive` and
   `verify` use `corpus/stages.py`.
7. **One addition from the calibration:** `io/workers.py` caps the returned members one job holds in T0 memory
   (`SPOOL_MEMORY_PER_JOB`, 64 MiB; a per-job bound, not a parent-wide one: a batch of results can hold one budget per
   job, and pipeline-perf's D-414 makes it pool-wide). Without it, the real level-2 job made the importer peak at
   2,114 MiB. This
   predates this branch and does not move any bytes.

