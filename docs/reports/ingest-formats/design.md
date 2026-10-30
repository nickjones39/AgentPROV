# Ingest formats for the phase-10e sources: `.tar.zst`, large JSON, split zips (design)

Date: 2026-10-12. Branch `ingest-formats`. Status: **implemented on the branch** (2026-10-13). The user chose option (a)
for the split-zip identity and approved the calibration read of the staged `RESULTS_raw.tar.zst` (§8, 2026-10-13);
D-240–D-246 user-approved 2026-10-13, with the merge. Results: `calibration.md`; routed needs: `routing.md`. Sources: `docs/reports/systematic-search/candidates/phase10e-candidates.md` §2 ranks 7, 10 and 13, cards
§3.6, §3.11 and §3.13; D-146 routed the first two to phase 12. Pattern followed: phase 12b's D-57 (bounded nested tar),
D-58 (streaming `expand`) and D-60 (calibrated budgets).

## 1. What the sources need (from the phase-10e metadata; nothing downloaded or profiled here)

| Source | Shape | Size facts (HF tree / Zenodo record, read in phase 10e) |
|---|---|---|
| Zenodo 20404563 `RESULTS_raw.tar.zst` (rank 10) | top-level zstd-compressed tar; 10,000 rollout directories, 2,182 gemini-cli event streams in scope (D-143) | 207,950,011 B compressed (sha256 `f7186010…`, matches the record). Decompressed size unknown. Already staged by phase 10e. |
| HF `idacy/control-arena-…-2026-07-30` @ `84d39e0a485d` (rank 13) | (a) three zips stored as byte parts `logs-20260610T154758Z-3-00{1,2,3}.zip.part-000k`; (b) `logs_batch_runs-20260730.tar.zst` with Inspect `.eval` members (a zip at depth 2) | (a) 8 + 8 + 3 parts of 268,435,456 B (last parts smaller); logical zips 2,147,474,457, 2,147,478,676 and 781,063,343 B: the first two within 9,191 B of `max_artefact_bytes` (2 GiB). (b) 885,551,965 B compressed. |
| HF `lihaonan0716/mcphunt-agent-traces` @ `c4c69322bf9e` (rank 7) | per-model JSON documents with `messages` and `events` arrays | 18 files from 6.6 to **110,851,232 B** (`main/deepseek_v4_flash.json`); 9 files exceed `max_json_bytes` (64 MiB) or approach it. |

The split-zip parts are a plain byte split of an ordinary zip (`split -b 256M`; the phase-10e census read the
central directories by range across the parts), **not** a PKWARE multi-disk archive (`.z01` with disk numbers), which
`zip_precheck` keeps refusing.

## 2. Streaming `.tar.zst` (D-240, D-241)

**Reader.** `ingest/streams.py` gains `iter_zstd_bounded(source, limits, *, max_bytes, chunk)`, the zstd sibling of
D-57's `iter_gzip_bounded`, and both tar codecs share one framing reader: `ingest/archives.py`'s `_walk_tar` and
`OpenedTar` take the codec instead of calling the gzip decoder directly. Everything D-57 checks at the tar level is
unchanged (two passes, own 512-byte header parser, no `tarfile`, the obs-G1 long-name bound, regular files only, the same
member gate).

**zstd frames.** Each frame header is parsed with `struct` **before** the decoder sees it (RFC 8878 §3.1.1):

| Check | Code |
|---|---|
| Magic `28 B5 2F FD`; anything else where a frame must start (including bytes after the last frame) | `ingest.archive.format` |
| Skippable frame (magic `0x184D2A5?`) | `ingest.stream.codec` (refused: its payload is unverifiable and no observed writer of a `tar.zst` emits one; `pzstd` does) |
| Dictionary id present and non-zero | `ingest.stream.codec` (no dictionary is ever supplied; a frame that needs one cannot be verified) |
| Reserved descriptor bit set | `ingest.archive.format` |
| Window size (`Window_Descriptor`, or the content size for a single-segment frame, as libzstd computes it) above `2**zstd_window_log_max` (27, 128 MiB) | `ingest.stream.memory`, before any allocation |
| Declared `Frame_Content_Size` above the stream cap | `ingest.stream.size`, before decoding |
| More than `max_zstd_frames` frames | `ingest.stream.codec` |

Decoding: a fresh `compression.zstd.ZstdDecompressor(options={window_log_max: zstd_window_log_max})` per frame (never
reused after an error or across frames), `decompress(feed, max_length=chunk)` with the `needs_input` protocol, output
bounded by the stream cap and by `max_ratio` past `ratio_floor_bytes`, checked as it grows. Input exhausted before a
frame ends: `ingest.stream.truncated`; corrupt block: `ingest.archive.format`; content checksum mismatch (when the
frame carries one): `ingest.archive.crc`; any other `ZstdError`: `ingest.archive.format`. The window limit is passed to
libzstd as well (defence in depth for a header our parser mis-reads).

**Where it is accepted.** A zstd stream whose first decompressed block is a `ustar` header is opened as a tar at depth 1
(top level, both sources) and at depth 2 (a member of a zip). Unchanged: an uncompressed tar is refused, a gzip tar is
read only at depth ≥ 2 (D-57; no source needs a top-level `tar.gz`), and a zstd or gzip stream that is not a tar stays
deferred (`ingest.stream.codec`). A tar member that is itself an archive (control-arena's `.eval`) is expanded at depth
2 by the existing nested path, so `max_archive_depth` 2 suffices.

**Stream cap (D-241).** A tar stream must be decompressed whole (twice: structure pass and member pass), including the
members the profile does not select, so `max_total_bytes` (selected members) does not bound it. D-57 used
`max_stream_bytes` (1 GiB, sized on a CIAware `.jsonl.gz`). `RESULTS_raw.tar.zst` is 208 MB of compressed JSON text
(typically 5–15× under zstd) and the control-arena batch tar is 886 MB of mostly incompressible `.eval` zips, so 1 GiB
is likely too small for both. Proposal: a separate field **`max_tar_stream_bytes`**, used by both tar codecs (D-57's
path included; it only loosens there, and no corpus holds a nested `tar.gz`), provisional **16 GiB**, calibrated in §6.
`max_stream_bytes` keeps its meaning for single streams, which stay deferred.

**Memory.** At most one 128 MiB zstd window, one output chunk (1 MiB, as D-57; G.3.4's 64 KiB per call is kept for
single streams, see D-241), one held long name, and one selected member (≤ `max_member_bytes`, read whole before its
header is sent, D-58). CVE-2026-15310 (pre-allocation from a declared size) is covered twice: the declared content
size is checked against the cap before decoding, and `max_length` bounds every call; a security test measures RSS on a
frame that declares 1 GiB and carries 1 KiB.

## 3. JSON documents larger than `max_json_bytes` (D-242)

**Choice: a bounded incremental reader that yields the elements of declared arrays**
(`ingest/jsonstream.py`, `open_json_stream(source, limits, *, arrays, profile)`).

- The caller (an adapter's reader, through its profile) declares the arrays to stream as JSON Pointers made of object
  member names only, for example `("/messages", "/events")`, or `("",)` for a top-level array. At most 16, none a prefix
  of another. Nothing is streamed implicitly.
- A byte-level scanner (one regex over 1 MiB chunks; strings are skipped by the regex, so brackets and commas inside
  strings never count) tracks the object keys along the path, finds each declared array, and cuts it into **element
  slices** at its top-level commas. It never builds a value.
- **Each element slice is parsed by `strict_json_loads`** itself (the same function, hooks and codes), with the depth
  limit reduced by the array's own depth and the size bound `max_json_element_bytes`. Everything outside the streamed
  arrays, the **envelope**, is parsed by `strict_json_loads` with each streamed array replaced by `[]`. So the
  duplicate-key, number, `NaN`, depth, encoding and lone-surrogate rules are not re-implemented; they are the same code.
- Whole-document rules: the BOM and UTF-16/32 checks run on the first bytes, as in `strict_json_loads`; UTF-8
  validity is preserved by the cut (slices end at ASCII structural bytes, which never occur inside a multi-byte
  sequence); an empty slice (`[,1]`, `[1,]`, `[1,,2]`) is `ingest.json.syntax`; error offsets are absolute.
- **Two passes, fail closed (as D-57's tar).** Pass 1 validates the whole document (every element parsed and dropped,
  the envelope parsed, counts taken); only then does `iter()` re-read the source and yield
  `(pointer, index, offset, value)`. A defect anywhere means nothing is yielded, so a mapper never emits a partial
  execution from a bad file (the degenerate-AER rule of D.2.8 still applies). The source is `bytes` or a seekable
  binary handle (`JobContext.open_input`), never read whole.
- **Equivalence (the property test).** For every input, the stream reader accepts exactly when `strict_json_loads`
  accepts the same bytes (under equal depth, number and size settings), and the reassembled value equals its result.
  Argument: the document is the envelope text with `[e1,…,en]` in place of `[]`; it is valid JSON exactly when the
  envelope is valid and every `ei` is one valid value; the scanner tokenises strings exactly as JSON does, so the
  substitution point is a value position whenever the envelope parses.

**New limits:** `max_json_stream_bytes` (one streamed document; 1 GiB, 9.7× the largest observed 110.9 MB),
`max_json_element_bytes` (one element, and the envelope; 16 MiB, the JSONL record bound: at the 24× worst
amplification of G.3.2 at most 2 × 384 MiB is held, under the 2 GiB map-job cap), `max_json_elements` (1,000,000 per
document). Codes: the existing `ingest.size.file` (document), `ingest.size.record` (element or envelope),
`ingest.json.*`, `ingest.number.*`; one new code `ingest.json.elements` for the count.

**Rejected:**
- *A per-profile raise of `max_json_bytes`* (for example 128 MiB): `strict_json_loads` holds the whole tree, about
  24× the bytes (2.6 GB for 110.9 MB), above the 2 GiB parse-job cap that G.3.2 sizes 64 MiB against; it would need a
  larger memory cap for a parser of untrusted bytes, which D-55 refused to grant ("weakens the containment of
  parsers").
- *A third-party streaming parser* (ijson and similar): `agentprov.ingest` is stdlib-only.
- *`JSONDecoder.raw_decode` retried on a growing buffer*: a truncated element and a malformed one raise the same
  error, so the retry logic guesses; it needs decoded text, so byte offsets are lost; worst case quadratic.
- *Re-encoding the document as JSONL at fetch time*: edits raw bytes (invariant 3), and the derived object would need
  an origin kind `aer/0.1` does not have.
- *A general event (SAX) parser*: a full JSON grammar re-implemented in Python would duplicate exactly the rules this
  task says must stay identical, and it is slow; streaming only the declared arrays keeps all value-level rules in
  `strict_json_loads`.

## 4. A zip stored as byte parts (D-243, D-244)

**Reader.** `ingest/parts.py`: `PartsView`, a read-only, seekable binary view over the parts' handles in the
**declared order**, each with its declared size; `open_split_zip(handles, sizes, limits, *, release)` checks the
declaration (count ≤ `max_split_parts`, every part non-empty, each handle's actual size equal to its declared size,
logical size ≤ `max_split_bytes`) and then runs the **unchanged** G.3.5 sequence on the logical bytes: size pre-check,
`zipfile` open with warnings as errors, member count, prefix, overlap, member gate, CRC-checked streaming. A member
that crosses a part boundary is read through the view like any other. Order and identity never come from names: the
profile (or pin) declares the parts as `(sha256, size)` in order, and the worker opens each part **by digest**
(`JobContext.open_input`, re-hashed, G.4.5). A reordered, missing, duplicated-by-mistake or truncated part breaks the
zip structure (`ingest.archive.format`, `.cd`, `.overlap`, `.prefix`) and, separately, gives another container
identity (below). PKWARE multi-disk zips stay refused.

**New limits and code:** `max_split_parts` (64; the largest observed is 8), `max_split_bytes` (8 GiB logical; the
observed maximum is 2 GiB, which `max_artefact_bytes` would admit only by 9 KiB); code `ingest.archive.parts` (count,
empty part, size mismatch with the declaration). Parts themselves stay bounded by `max_artefact_bytes` at storage.

**Identity of the logical zip (D-244, needs the user).** Member rows and `member` origins name one `container`
digest, and `verify --level chain` requires that container to be a stored object. Proposal: the container is a small
**split descriptor**, the JCS bytes of
`{"archive": "zip", "format": "agentprov-split/0.1", "parts": [{"sha256": "sha256:<hex>", "size": n}, …]}`, stored
as a raw object; its digest identifies the concatenation exactly (order and every part's bytes). `expand` takes such a
container (`ContainerSpec.parts`), checks in T0 that the descriptor digest equals the digest of the declared parts
(computed, not parsed), and runs one job with the parts as inputs. `rederive` reads the descriptor back with the strict
loader (an AgentPROV format, like `raw/origins.jsonl`). Member CRC re-checks in `verify` read member objects only, so
they need no reassembly. What is **not** mine and is routed: the descriptor's own origin needs a new origin kind (for
example `split {"archive": "zip", "parts": [...]}`) in `raw/origins.py` and C.3.12/H.2.3, accepted by
`corpus/manifest.py` (snapshot origin kinds) and `corpus/rawtree.py` (re-mapping); an AER never cites the descriptor
(it is never a mapped artefact), so `aer/0.1` is untouched. Alternatives in the question to the user (§8).

## 5. Limits added to `IngestLimits` (G.3.2 rows) and codes (G.3.9)

| Field | Default (provisional until §6) | Code | Basis |
|---|---|---|---|
| `max_tar_stream_bytes` | 16 GiB | `ingest.stream.size` | §2; tar streams are decompressed whole, twice |
| `max_zstd_frames` | 1,024 | `ingest.stream.codec` | `zstd`/`tar --zstd` write one frame |
| `zstd_window_log_max` (existing) | 27 (128 MiB) | `ingest.stream.memory` | now active for zstd streams |
| `max_json_stream_bytes` | 1 GiB | `ingest.size.file` | largest observed 110.9 MB |
| `max_json_element_bytes` | 16 MiB | `ingest.size.record` | = JSONL record; 2 × 384 MiB worst case held |
| `max_json_elements` | 1,000,000 | `ingest.json.elements` (new) | count bound per document |
| `max_split_parts` | 64 | `ingest.archive.parts` (new) | largest observed 8 |
| `max_split_bytes` | 8 GiB | `ingest.archive.parts` | largest observed 2 GiB |

## 6. Calibration (D-245, as D-60)

Synthetic, seeded, generated at run time under `~/.agentprov/migration-work/ingest/`: a `tar.zst` with a 4 GiB stream
of mixed text and random members (levels 3 and 19, `--long=27`), the same as `tar.gz` for D-57's path, a 2 GiB split zip
in 8 parts, and a 128 MB JSON document of `messages`/`events` shape. Measured per case in a fresh T1 worker: worker
CPU, job wall, peak RSS, against the budgets of G.4.3 (`with_expand_scaling`, map-job defaults). The expand budget
scales with `max_total_bytes` only, so the projection to the full `max_tar_stream_bytes` is checked explicitly; if it
does not fit with ≥ 10× headroom, the scaling gains a tar-stream term (an `io/workers.py` change, recorded). Optional
(needs the user's yes, §8): the decompressed size and frame parameters of the already-staged `RESULTS_raw.tar.zst`,
read in memory only, no download.

## 7. Downstream effects (regen-batch bundle "ingest-formats")

- `EXPAND_MODULES` files change (`errors.py`, `ingest/archives.py`, `ingest/limits.py`, `ingest/streams.py`,
  `raw/members.py`) and gain `ingest/parts.py`: `raw.members.engine_code_sha256`, hence the `expand` stage's
  `fn_digest` (in `derivation.json` and on every `raw/members.jsonl` row), moves. Only the four `ast-survey-agentharm*`
  corpora hold member rows; their member digests, labels and dispositions do not change.
- New `IngestLimits` fields change `limits.to_json()`, hence `limits_sha256` in the `expand` **and the `aer`** stage of
  `derivation.json` and the `limits.effective` record of `corpus.json`, for **every** corpus at its next import or
  re-map. No AER, SEM or PROV byte changes; no golden or gate-D digest moves. A paused import cannot resume across the
  change (its G4 identity check compares both), so this merges only when no import is paused. Every corpus is
  regenerated in the `aer/0.2` round anyway.
- `ingest/jsonstream.py` is not an expand module and no code digest hashes `ingest/`, so it moves nothing by itself.
- `io/workers.py` budget changes, if any, change which jobs time out, not bytes.

## 8. Questions for the user

1. **Split-zip identity (D-244):** (a) descriptor object + a new origin kind routed to the orchestrator
   (recommended; no duplicated bytes); (b) store the concatenated zip as one raw object (about 5 GB duplicated for
   control-arena; `expand` unchanged, still a new origin kind); (c) ship the reader only and leave split zips
   unimportable until the corpus layer decides.
2. **Calibration on staged bytes:** may the calibration read the already-staged `RESULTS_raw.tar.zst`
   (207,950,011 B, `~/.agentprov/staging/10e/zenodo_20404563/`, phase-10e download) in memory, frame headers and a full
   decode count only (no member content printed, nothing extracted)? No download is involved.

## 9. Proposed decisions (D-240–D-249)

- **D-240** streaming `tar.zst` through a shared bounded tar framing reader; zstd frame pre-parse (skippable and
  dictionary frames refused, window and content size checked before decoding); top-level and level-2 `tar.zst` accepted.
- **D-241** `max_tar_stream_bytes` bounds both tar codecs' decompressed stream; `max_zstd_frames`; 1 MiB output chunks.
- **D-242** large JSON by declared-array streaming with element slices parsed by `strict_json_loads` (two passes;
  rejected alternatives in §3); three new limits and `ingest.json.elements`.
- **D-243** split zips as a declared, digest-pinned ordered part list read through a seekable view, G.3.5 unchanged;
  two new limits and `ingest.archive.parts`.
- **D-244** split-zip container identity (the user's choice in §8 q1).
- **D-245** calibrated budgets and limit values (after §6).
- **D-246** the regen-batch "ingest-formats" bundle and its merge condition (§7).
- D-247–D-249 reserved.
