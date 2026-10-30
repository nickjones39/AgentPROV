# R-10k-1 follow-ups (ii) and (iii): design notes (no code)

Status: (ii) built as D-321 (D.2.9 note item 13, `tests/adapters/runner/test_rejected_rows.py`); (iii) agreed as D-322 and
not built. Originally a design for review (2026-10-13). Branch `r10k1-followups-design`, stacked on `bb938a6`
(`r10k1-multi-execution`: D-320, `f852d27` + `bb938a6`). The orchestrator relays these notes to the deferrals session
(the runner owner) for review, and the R5 question in §1.4 to the user. No code is written until both answer.
Follow-up (i), `parse_stream` for MCPHunt RB-1/RB-2, waits for ingest-formats-2 and is not covered here.

Decision numbers, if adopted: D-321 for (ii), D-322 for (iii), from the orchestrator's D-320..D-329 range.

## 0. Where D-320 leaves things

- A `multi_execution` whole-file reader is mapped one unit per located item (`per_item` frames). Each execution is
  resumed and collapsed by its source key, and a file sealed whole is resumed whole by its document-root key.
- **Rows that are not executions have no path today.**
  - A file of the dialect with zero items is one `select.not_execution_artefact` entry.
  - A file that sniffs as valid input of another kind is one `select.not_execution_artefact` entry with the reader's
    register detail.
  - Rows that `parse` skips inside a file with executions leave **no trace**. This is a silent drop under H.6.1 R1 once
    the candidates are rows.
- **Container mode is keyed by member digest.** `map_containers` calls `_seen_before(member_sha)` per planned unit. Two
  units of one member would make the second look already seen. Today's only container dialect (Inspect `.eval`) plans
  one unit per sample member, always with locator `{"p": ""}`, so it never hits this.

## 1. (ii) Per-item register rows for rejected items

### 1.1 Consumer

Phase 10n R-10n-3 (D-300, D-301): AutoGen `runs.jsonl` members of a Zenodo zip (D-200).
- 1,080 run rows are executions (`{"line": n}`).
- 150 phase-7 rail-probe rows are `select.not_execution_artefact` (detail `autogen.rail_probe_no_agent`).
- 40 phase-8/9 rows are `select.out_of_scope` (detail `autogen.partial_trajectory`).
- D-300 asks for one register row per rejected row, "never dropped". It rejected "a file-level register only".
- The 190 rows sit in the 3 files that hold **no** run row. These files sniff as not-of-dialect today, so the hook must
  also serve files with no execution.
- The reader already has `row_reason(row)`.

### 1.2 Reader hook

An optional method on a `multi_execution` reader:

```python
def rejected(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[Rejected]: ...

@dataclass(frozen=True, slots=True)
class Rejected:            # adapters/types.py, next to LocatedItem
    locator: Locator       # the row's key locator ({"line": n} or {"p": "/<i>"})
    code: str              # a select.* code of the closed H.6.3 set: select.not_execution_artefact | select.out_of_scope
    detail: str            # the reader's register detail (generated text, never source content; <= 200 chars)
```

- **Totality.** The rows `parse` yields and the rows `rejected` yields partition the file's rows: each row is in
  exactly one. The family's tests assert this on every fixture, which states R1 at row level.
- **No error path.** The hook never raises for content. A row the strict loader refuses makes the whole file fail the
  loader, so it is one degenerate AER (D-320) and no row is rejected individually.
- **Code check.** The runner refuses a code outside `select.not_execution_artefact` and `select.out_of_scope` as an
  adapter defect (`map.adapter_defect`). Adapters cannot invent register semantics (invariant 1).

### 1.3 Job frames and importer

**Map job** (`total` + `per_item`), only when the reader defines `rejected`:
1. **Rejected rows.** It first emits one `{"register": {"code", "detail", "loc"}}` frame per rejected row, in locator
   order. `split_unit_frames` already returns register frames apart from units.
2. **Executions.** Then it emits the unit frames as today.
3. **Files with no execution.** A file that fails `sniff` with a non-loader reason, or yields no item, is passed to
   `rejected` too. If it yields rows, those frames **replace** the single `not_dialect` / `NoExecution` frame, so the
   file is accounted for by its rows. If it yields none, the file-level entry stays as today.

**Importer.** Each register frame becomes a register entry with:
- subject `{"source_key": source_key(sha, loc)}`;
- stage `select`, severity `info`, disposition `not_imported`, detail as given;
- the counter `registered`.

On resume, the same entry collapses by `rid` in `register.jsonl` (H.6.2: equal `(subject, code, stage)` keep one
entry), so the file's bytes do not change. To keep the report honest, `_known_artefacts` also loads the
`(source_key, code)` pairs of the existing register. A pair already present counts as `skipped_resume`, not
`registered`.

**Unchanged.**
- The whole-file rule: a file sealed whole as one degenerate AER emits no rejected rows, before or after resume.
- `--limit`: it counts written executions only, so register rows are never limited.
- Byte identity for every reader without `rejected`: no frame, parameter or entry changes.

### 1.4 The open question for the user: does a rejected row count as a candidate (H.6.1 R1, R5)?

**Ruling (2026-10-13): option A**, chosen by the user in the orchestrator's session and confirmed in this session. The
deferrals session approved (ii) and (iii), with build points for (ii): validation in the runner parent, canonical
locator order, re-derivation on a re-map, the hook only in T1, and a pinned `corpus.manifest.unattributed` test.

**Background.**
- R5 requires `candidates == executions + not_imported` per snapshot. The manifest recomputes it from the index and
  the register (`corpus/manifest.snapshot_counts`). With D-320, `executions` already counts each run of a cell, so
  `candidates` already means *units*, not files, for `multi_execution` sources.
- R1's text still says "every candidate matched by a snapshot's include globs", which is a file.
- `snapshot_counts` attributes a `not_imported` entry to a snapshot through its subject (`_entry_snapshot`). A
  `{source_key}` subject is attributed only in a single-snapshot corpus. In a multi-snapshot corpus it raises
  `corpus.manifest.unattributed`, and the manifest cannot be written.

**Options.**

| | What a rejected row is | Subject | Counts | Core change | Multi-snapshot |
|---|---|---|---|---|---|
| **A (recommended)** | a candidate with disposition `not_imported` | `{source_key}` | +1 `not_imported`, +1 `candidate` in its snapshot | none (runner only) | refused loudly (`corpus.manifest.unattributed`) until B is built |
| B | as A | `{source_key}` | in **every** snapshot whose pin vouched for the file (via `raw/origins.jsonl`, and via `raw/members.jsonl` for members), the way a collapsed execution counts once in each snapshot | `corpus/manifest.py` (`_entry_snapshot` → a set of snapshots) and `corpus/verify.py` (the same attribution in `chain`); H.6.1/H.6.2 text | supported |
| C | not a candidate: one file-level entry for a file with no execution (today) | `{snapshot_id, path}` | +1 per such file | none | supported |
| D | a candidate | `{snapshot_id, path: "<label>#line=<n>"}` | +1 per row per snapshot | H.6.2 text only | supported |

- **Recommendation: A now, B when needed.** Count each rejected row as a candidate: it makes R1 hold at the
  granularity D-320 already uses for executions, and it is what D-300 asked for.
  - AutoGen (one Zenodo version) and credleak (only v3 pinned, D-268) are single-snapshot, so A needs no
    `corpus/` change.
  - A multi-snapshot corpus of such a source fails at manifest write, never silently. B is built when the first one
    is planned. Its design is in the table, and it needs the `corpus/` owner's review.
  - Spec change with A: H.6.1 R1 gains "for a `multi_execution` file the candidates are its located items and its
    rejected rows (D-320, D-321)".
- **Rejected: C** keeps today's behaviour, which D-300 rejected. It also leaves rows of a file *with* executions
  untraced.
- **Rejected: D** puts a locator inside `path`, which H.6.2 defines as an origin-relative path. A `#` is a legal label
  character, so it would be ambiguous. It also re-registers the same row once per snapshot under a different subject.

### 1.5 Tests (when built)

- **Runner (test reader, as in `test_multi_execution_lines.py`).**
  - A file with 2 runs and 1 rejected row gives 2 executions, 1 `{source_key}` entry and `candidates = 3`, and passes
    `verify --level chain`.
  - A file with only rejected rows gives N row entries and no file-level entry.
  - A resume re-registers nothing new (`skipped_resume`) and leaves `register.jsonl` byte-identical.
  - A code outside the two allowed codes gives `map.adapter_defect`.
  - A multi-snapshot import with a rejected row fails with `corpus.manifest.unattributed` (pinned until B).
- **Family (AutoGen, on phase 10n's side).** Every fixture partitions into `parse` ∪ `rejected`, and the 150/40 counts
  are reproduced.

### 1.6 Downstream effects

- `adapters/runner/` again moves the `aer` stage's `engine_code_sha256`, for future imports only. `adapters/types.py`
  gains `Rejected`.
- No existing corpus changes: no shipped reader defines `rejected` yet.
- H.6.1 R1 and D.2.9 item 12 need text changes.

## 2. (iii) Source keys on the container path

### 2.1 Change

Only for a container dialect that also declares `multi_execution`; Inspect `.eval` does not, and keeps today's code
path byte for byte:
- `_job_map_container` adds `"loc": unit.primary.locator.key()` to each `{"unit": …}` frame. Frames are transient job
  output: no digest covers them, and the parent and the job run the same code.
- **Resume and collapse.** `map_containers` resumes and collapses each unit by `source_key(member_sha, loc)`
  (`_seen_before(..., key=…)`), with the `{source_key}` collapse subject of D-320.
- **Whole-member rule.** Before a member's units are sealed, the member's document-root key
  `source_key(member_sha, {"p": ""})` is checked. If it is indexed (a member sealed whole as one degenerate unit), all
  that member's units are `skipped_resume` (or collapsed) together. This mirrors D-320's whole-file rule, so a member
  is never present both whole and as items.
- **Fallback units.** These come from `Locator.from_key(loc)`, as in `_seal_items`.
- **Unchanged.** `--limit` (already per unit) and the container-level failure path (one `map.adapter_defect` for a
  failed plan job, no AER).
- The `self.multi = … and not self.container` guard in `_Pipeline.__init__` becomes a separate `self.multi_members`
  flag for the container path.

### 2.2 Why gate it

For Inspect the two keyings are equal, so the gate could be dropped: each unit is a distinct sample member with
`{"p": ""}`, so source-key resume reduces to digest resume, and the D-202 collapse is already per member digest.
Gating anyway keeps the Inspect register subjects (`{snapshot_id, path}` for `dedup.collapsed`) and the importer's
behaviour exactly as they are. Dropping the gate would move those subjects for every future Inspect multi-snapshot
import.

### 2.3 Consumer: none known yet

- memo-ozdincer's "results containers" (D-146) are **whole JSON files** holding many runs (`results/*.json`, attack
  and model at container level). That is a `multi_execution` whole-file reader, which D-320 already supports with
  `{"p": "/<i>"}` locators. It needs no container-path change.
- No shipped or planned container dialect (a reader with `plan` over expanded members) has more than one unit per
  member.
- **Recommendation: keep (iii) as an agreed design and build it only when a container dialect with several units per
  member is planned.** Until then, its test would pin a path no family uses.

### 2.4 Tests (when built)

A test container reader (registry-patched, in process) whose `plan` yields two units per member:
- two executions per member;
- an interrupt between them resumes only the second;
- a crashed whole member resumes whole;
- a second snapshot collapses both units;
- Inspect's existing container tests, unchanged, as the regression gate.

### 2.5 Downstream effects

- The `aer` stage identity moves (runner code).
- No existing corpus or Inspect register subject moves.

## 3. (i) Streamed elements: `parse_stream` (RB-1) and a profile-raised element limit (RB-2)

Status: built as D-323 (2026-10-14; D.2.9 note item 14), with the review changes. The calibrated element ceiling is 64 MiB, not
the 256 MiB proposed below (`d323-calibration.md`). Originally a design for review (2026-10-13), proposed as D-323. It is not built yet because RB-2 changes the effective import
limits, which `ingest/` owns. The deferrals session's four conditions are restated where each applies.

### 3.1 Consumer

Phase 10m MCPHunt: HF `lihaonan0716/mcphunt-agent-traces`, 6,786 traces in per-model documents of up to 111 MB.
`McpHuntReader` on `phase-10m-readers` already has:
- `sniff_stream(handle, *, limits)`;
- `parse_stream(handle, artefact, *, limits)`, one item per `/traces/<i>`, through `ingest.jsonstream.open_json_stream`,
  which validates the whole document in pass 1 before it yields anything;
- `parse(bytes)` as a wrapper.

Its profile declares `[family.mcphunt] max_json_element_bytes = 67108864`. Four traces of 20.5 to 46.9 MB exceed the
16 MiB default. Without the raise, the four documents holding them (1,977 traces) are refused whole.

### 3.2 RB-1: the streaming per-item job (runner only)

- **Which readers.** A `multi_execution` reader that defines both `sniff_stream` and `parse_stream`. Only such a reader
  takes the streaming path (condition 4); every other reader keeps the byte path of D-320 unchanged.
- **Store-first (condition 1).** The `per_item` map job opens its primary with `JobContext.open_input(0)`, never
  `read_input`. That opens the stored object by digest, hashes all of it in 1 MiB chunks, fails the job on a mismatch
  and only then rewinds. Store objects are 0444, and the worker cannot write files (`RLIMIT_FSIZE = 0`), so the bytes
  parsed are the bytes hashed. Nothing parses before the digest matches.
- **Classification.** `sniff_stream` gives the same outcomes as `sniff`:
  - an `ingest.*` reason makes the file one degenerate AER, `{"p": ""}`;
  - another reason means valid input of another kind (`not_dialect`, or rejected rows, D-321);
  - `NotSelected` works as before.
- **Bounded memory.** Each streamed item is mapped and its frames are emitted at once, so the job holds one item's
  outcome at a time (today `map_artefact_units` collects every pair). The parent already consumes frames per unit.
  - Rejected rows (D-321) of a streamed file come from a `rejected_stream(handle, …)` hook, if one is defined. The
    parent orders them canonically anyway, so their place among the frames does not matter (it sorts, D-321).
- **No partial file.** `open_json_stream` refuses an invalid document before the first element. If the stream still
  fails after some units were emitted (an element-count limit, an adapter bug), the job emits a final
  `{"abort": {"code"}}` frame. The parent then discards every unit and row of the file and seals it as one degenerate AER
  (the D-320 whole-file rule), so a file is never half imported.
- **Unchanged.** Resume, collapse, `--limit` and the root-key rule are exactly D-320's.
- **Parent side.** T0 never touches the stream. It still stores the file's bytes as today, within `max_member_bytes`
  (256 MiB) for archive members and `max_artefact_bytes` for files.

### 3.3 RB-2: a profile-raised `max_json_element_bytes` (needs ingest/'s owner)

| | Where it is declared | Who applies it | Recorded |
|---|---|---|---|
| **A (recommended)** | a generic profile key `[import] limits = { max_json_element_bytes = <n> }` | the import CLI and `import_source`, through a function in `ingest/limits.py` (`IngestLimits.with_profile(overrides)`) that accepts only an **allowlist** of raisable fields, each up to a **ceiling** set there (proposed: `max_json_element_bytes` ≤ `max_member_bytes`, 256 MiB) and never below the default | as an override in `corpus.json` `limits`, which `recompute` already replays (`cli/derive._limits`); the `aer` stage's `limits_sha256` moves for that corpus only |
| B | a CLI flag `--max-json-element-bytes` (like `--max-file-bytes`) | the CLI | as A, but nothing ties the value to the source: an import without the flag refuses the four documents |
| C | the family table `[family.mcphunt]` (today's draft) | the runner reading a family key | rejected: adapter-specific logic in the core (invariant 1, CLAUDE.md rule 9) |

- **Limits stay in ingest/ (condition 2).** The allowlist and ceilings live in `ingest/limits.py`, not in a reader, and
  the reader still receives one `IngestLimits`.
- **Memory.** Before the raise is enabled, calibrate a 64 MiB element through `open_json_stream` and a mapper in a T1
  worker under the worker RSS cap (as D-60 did for ingest budgets). A parsed 47 MB trace may take several times its
  size in Python objects.
- **10m-side change.** The MCPHunt profile moves its key from `[family.mcphunt]` to `[import] limits`.

### 3.4 Tests

- **Differential (condition 3).** A runner test reader with both paths: `parse_stream(handle)` and `parse(bytes)` give
  the same items, and the same AER bytes, frames and register, for a multi-element document. MCPHunt's own
  differential test runs on every MCPHunt fixture, on 10m's side.
- **Store-first.** A tampered store object fails with `worker.input.digest_mismatch` before `sniff_stream` is called
  (a spy).
- **Abort.** A forced failure after the first emitted unit leaves one degenerate AER and no unit row.
- **Bounded memory.** A many-element document maps with no `pairs` list (a structural assertion on the job, plus an RSS
  smoke check).
- **Limits (RB-2, after ingest/ agrees).** A profile raise inside the allowlist is applied, recorded and replayed by
  `recompute`. A field outside it, or above its ceiling, is refused at profile load.

### 3.5 Downstream effects

- **RB-1:** none for existing corpora. No shipped reader on main defines `parse_stream`, and the `aer` stage
  identity moves as with any runner change.
- **RB-2:** `ingest/limits.py` changes, but the defaults do not, so no corpus moves. The limit is raised only where a
  profile declares it, which is MCPHunt only.
