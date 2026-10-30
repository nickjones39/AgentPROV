# Ingest formats, follow-up: split archive inputs, top-level `tar.gz`, pax headers (design)

Date: 2026-10-13. Branch `ingest-formats-2` (from origin/main `ebef6c7`). Decisions D-247–D-249 (user-approved 2026-10-13). Scope set
by the orchestrator: RI-1 and RI-5 (this session's), RI-2 and RI-3 (importer wiring; the deferrals session agreed, with
five review points, and reviews the diff before the merge), and phase 10i's D-192 (AgentOps-Bench: a top-level `tar.gz`
with 7,270 pax `x` headers).

## 1. Split archive inputs (D-249; RI-1, RI-2, RI-5)

**Pin.** A download pin (Zenodo or Hugging Face) whose file is cut into byte parts declares the parts in order and pins
each one; `file` names the logical archive (its label), which exists upstream only as the parts:

```toml
[[source.pins]]
role = "logs-001"
kind = "hf"
dataset = "idacy/control-arena-persistent-state-eval-archive-2026-07-30"
revision = "84d39e0a485d7ea6ca10f4ceb2a3fbf88dab0e62"
file = "logs_tmp_zips/logs-20260610T154758Z-3-001.zip"
archive = "split-zip"
parts = [
  { file = "logs_tmp_zips/logs-20260610T154758Z-3-001.zip.part-0000", bytes = 268435456, sha256 = "…" },
  # … in order; a Zenodo part may add md5
]
```

`raw.fetch.part_recipes(pin)` gives one recipe per part (the pin's kind, deposit and revision, the part's file, size and
digests). `--input DIR --verify-against-pin` finds each part by its pinned file name in `DIR` and checks it offline
(`verify_download` per part: name, size, MD5 when pinned, SHA-256); `--fetch` fetches each part, and the U-07
large-download consent is required when the **total** of the parts reaches `LARGE_DOWNLOAD_BYTES` (deferrals point 4).
The order is the pin's; file names only locate local copies, which are then verified by digest.

**Import (deferrals point 1: the D-200 path, not a parallel one).** `ArchiveTree` gains a split mode. In
`_Pipeline.archive_members`, each part is stored with its own pinned origin (`hf {repo, revision, path: <part>}` or
`zenodo {doi, file: <part>}`), then the split descriptor (D-244) is stored with a new origin kind
`split {"archive": "zip", "label": <logical file>, "parts": ["sha256:<hex>", …]}`, and the one `ContainerSpec` is the
descriptor with `parts`. Everything after that is D-200 unchanged: member subjects `<label>!/<member>`, `member` origins
(container = the descriptor digest), and the snapshot record `input {kind: archive, label, sha256: <descriptor>, bytes:
<logical size>, parts: [{file, sha256, bytes}, …]}`.

**Replay (point 2).** `StoredRawTree` reads `input.parts`: the descriptor is the one candidate (`label_for` of a `split`
origin is its `label`), `archive_parts` hands the parts to the importer, and the parts must be stored objects whose
origins the pin vouched for. `recompute --check` and `verify --level rederive` re-expand through the same descriptor;
a test in `tests/adapters/runner/` mirrors part A's archive recompute test.

**Several snapshots (point 3).** The members are the primaries and the descriptor digest is the container key, so a
second snapshot with the same parts collapses its members (`dedup.collapsed`) and records no second expansion
(`MemberLog.add_container` is idempotent for identical rows). The parts are never primaries.

**Origins and sealing (RI-1).** `raw/origins.py`: kind `split` (C.3.12 addendum; it appears only in
`raw/origins.jsonl`, never in an AER artefact, so `aer/0.1` is untouched). `origin_matches_pin`: a `split` origin
matches a pin whose `parts` list the same digests in the same order; a part's `hf`/`zenodo` origin matches when its
file is one of the pin's parts. Sealing (`snapshot_origin_from_pin`), within the frozen `corpus-0.1` schema (D-163; adding a `parts` member
would change the published schema bytes, as the first test run showed): an HF archive input seals as `{kind: hf, dataset,
revision, gated, path}`, where `gated` must be recorded in the pin; for a split one `path` is the directory holding the
parts, which are named by their object origins in `raw/origins.jsonl`. A Zenodo split snapshot is refused at sealing
until a schema version adds `parts` (routed; no Zenodo split source exists). RI-5: H.1.4 notes that a `container` may be a descriptor.

## 2. Top-level `tar.gz` and `tar.zst` archive inputs (D-247; RI-3; D-192 part 1)

`open_archive` opens a gzip stream whose first block is a `ustar` header at depth 1 too (D-57 allowed depth ≥ 2 only); a
gzip that is not a tar stays deferred. An archive input is always a declared download pin (D-200), so nothing else
reaches `expand` at depth 1. A top-level `tar.zst` already opens since D-240; the importer needs no change beyond tests
(point 5): the same `IngestLimits` fields gate a tar as a zip (`max_members`, `max_member_bytes`, `max_total_bytes`,
`max_archive_depth`, names and collisions), and the ratio is bounded on the stream (`max_ratio` against the compressed
size, as it grows) where a zip bounds it per member.

## 3. pax `x` extended headers (D-248; D-192 part 2)

`_walk_tar` reads a typeflag `x` header's records as data, bounded by a new declared limit `max_pax_header_bytes`
(64 KiB; a larger header refuses the archive, nothing is buffered beyond it). Records are `"<len> <key>=<value>\n"`,
parsed strictly (decimal length that matches, `=` present, LF at the end, no duplicate key; any defect refuses the
archive). Closed allowlist:

| Key | Effect |
|---|---|
| `path` | the next entry's name (UTF-8), through `logical_name` like any name; longer than `max_name_bytes`: that entry is rejected `ingest.name.invalid` |
| `size` | the next entry's size (decimal digits only, at most 20); the member gate applies |
| `mtime`, `atime`, `ctime`, `uid`, `gid`, `uname`, `gname` | ignored |
| `SCHILY.xattr.*`, `LIBARCHIVE.xattr.*` | ignored (extended attributes such as `com.apple.provenance`) |
| anything else (`linkpath`, `hdrcharset`, `GNU.sparse.*`, …) | refuses the archive (`ingest.archive.format`) |

A pax `g` (global) header, two `x` headers in a row, an `x` header followed by a GNU `L` header (or the reverse), and an
`x` header followed by the end of the archive still refuse it. `tarfile` stays unused (obs-G1).

## 4. Downstream effects (regen-batch entry `ingest-formats-2`)

- `ingest/archives.py` and `ingest/limits.py` are `EXPAND_MODULES`: the `expand` `fn_digest` moves again. The new
  field `max_pax_header_bytes` moves `limits_sha256` (expand and `aer` stages) like the first bundle.
- `adapters/runner/importer.py` is hashed into the `aer` stage's `engine_code_sha256` (with `aer/`): it moves for every
  corpus at its next import, as every runner change does.
- `raw/origins.py`, `raw/fetch.py`, `corpus/manifest.py`, `corpus/rawtree.py` and `cli/import_.py` are in no stage digest.
- No AER, SEM or PROV byte of an existing corpus changes: no stored corpus has a split input, a top-level tar or a pax
  header. Merge only when no import is paused.
