# Phase 10m: needs routed to the orchestrator (2026-10-13)

**Status 2026-10-15: all four closed.** RB-1 and RB-2 landed as D-323 and RW-1 as D-311; the family now uses them, and
RB-3 is done in the family by D-218 carving over the trace's byte range (branch `phase-10m-d323`; spec D.21.2, D.21.3,
D.21.8; `tests/adapters/mcphunt/test_streaming_import.py`).

Phase 10m owns `adapters/wirelog/` and `adapters/mcphunt/` (new files, append-only registry entries). These needs sit in
folders it does not own. None is needed for the `wirelog` family (Zenodo 21944598), whose scratch trial import passed
every check (README §A.8). All three block an import of MCPHunt (D-286–D-289); its traces were mapped in memory instead.

| # | Need | Owner | Why |
|---|---|---|---|
| RB-1 | A whole-file dialect may yield **one execution per element of a streamed array**: the map job opens its primary with `JobContext.open_input` (never `read_input`) and calls the reader's `parse_stream(handle, artefact, limits=...)`, mapping each located item (`/traces/<i>`) as its own unit; registers and seals per item. Today `map_artefact`/`map_artefact_total` read the primary whole and require exactly one item per file. | deferrals session (runner) | D-286; MCPHunt holds up to 723 traces and 111 MB per document. RI-4 of ingest-formats names the reader side, which `McpHuntReader.parse_stream` implements. Execution ids follow C.4.1 from the document digest and the locator, so no `aer/` change. |
| RB-2 | Honour a **profile-declared `max_json_element_bytes`** (`[family.mcphunt] max_json_element_bytes` = 64 MiB), recorded in `corpus.json` with the other effective limits, or a raised default. | deferrals session (runner) with ingest-formats (limits) | D-288; four traces of 20.5–46.9 MB; under the default the streaming reader refuses their four documents whole (1,977 traces). |
| RW-1 | A **withholding rule that selects executions by a seal issue**: `[[withhold.rules]] {id = "canary-flagged", issue = "mcphunt.canary_flagged"}` withholds every execution whose AER seal lists that issue (one per flagged trace, ids = the flagged tool executions, detail a count), with its derived files, keeping the raw documents private. Taken by the release-scan session (D-311–D-319); the trigger was chosen by the user there. | orchestrator (`corpus/withhold.py`; core change, user-approved as part of D-289 option (c)) | D-289; 4,595 traces have a canary-flagged event, 2,601 of them with canaries of no recognisable shape, so byte patterns cannot find them, and an object-scope pattern hit would withhold whole 723-trace documents. If RW-1 is refused, option (a) applies (the profile's pattern policy alone). |
| RB-3 | **Resolved by D-218 (carved blobs, on main), as a follow-up after D-323.** One MCPHunt trace (`mitigation/minimax_m3_rv1.json` `/traces/106`, 46.9 MB) has a tool result too large for a 16 MiB AER line. A carve's `utf8` transform is a string of the stored artefact (re-derived by verify and recompute), not mapper-derived content, so D-203's limit does not apply: the mapper writes the result as `ctx.carve(loc, "utf8")` in the `tool_result` part's `value` (a JSON position; `text` is typed) or in the execution's `returned`. Plan: carve every tool result over 1 MiB (which also keeps the AERs clean of D-216's 1 MiB inline-string refusal in `aer/0.2`), with the trace's own byte range as the locator. It needs RB-1's per-item map job to pass `map_unit` a lazy reader of the stored primary (deferrals informs the runner session), so it is implemented after D-323. | deferrals (answer), runner session (lazy reader) | 1 of 6,786 traces today; the raw store grows by about 47 MB for it (raw_policy include). |

Not routed (decided in-family): the D.20/D.21 spec numbering (D.19 is phase 10k's credleak; phase 10n may need D.22).

## Follow-ups agreed with the orchestrator (2026-10-13)

- **D-323** (user-approved in the orchestrator session; built by the R-10k-1 runner session) covers RB-1 (the runner's
  streaming parse) and RB-2 option A (generic per-source parse limits). When it lands **and** its 64 MiB calibration
  passes: move `[family.mcphunt] max_json_element_bytes` to the generic, raise-only `[import] limits` key (allowlisted in
  `ingest/limits.py`, validated at profile load; the core cannot read a family table); a lower ceiling applies if the
  calibration fails. The profile's bytes change, so record under D-31 whether it takes a version bump or stays v1 (no
  corpus yet). Then drop the RB-1/RB-2 strict xfails.
- `McpHuntReader.parse(bytes)` stays a thin wrapper over `parse_stream`, so the two paths cannot drift.
- After RW-1 merges: add `[[withhold.rules]] {id = "canary-flagged", issue = "mcphunt.canary_flagged"}` to the profile
  and drop the RW-1 strict xfail.

## D-323 calibration on the MCPHunt files (runner session, branch `d323-stream`, 2026-10-14)

Read-only, on the staged pin (`docs/reports/r10k1/d323-calibration.md` there): 26 documents, 6,786 traces, 4 traces above
16 MiB. **RB-2 passes at 64 MiB** (a synthetic 64 MiB element peaks at 1,197 MiB in the worker, under the 2 GiB cap); the
`[import] limits` ceiling is the calibrated 64 MiB, so MCPHunt's `max_json_element_bytes` stays 64 MiB. **Consequence for
RB-3:** in the product path the mapper's copy of a very large tool result exceeds the worker's 16 MiB output-frame cap
(`worker.limit.output`), so until the carving follow-up lands, the documents holding the 44.8 MiB and both 24.4 MiB traces
seal as **one degenerate AER per document**, not per trace (the 19.5 MiB trace's document maps fully). The fix is the
carving of every tool result over 1 MiB (D-218), with the item's byte-range locator and the lazy source
`_input_reader(ctx, 0)`, never a raised frame cap. Parent RSS reached 982 MiB on the 105.7 MiB document (144 MiB of
frames).

Constraint from deferrals' review of D-323 (2026-10-14): RB-3 never carves with a whole-document locator (`{"p": …}` over
the whole MCPHunt document parses up to 111 MB per unit, uncalibrated, possibly over the 2 GiB map cap). It uses the
item's byte range `{"bytes": [start, end], "p": …}` with absolute offsets in the stored object, and is built only after
the runner session's offset reporting in `parse_stream` lands (D-323 or its follow-up).

Interface for the RB-3 follow-up (D-323 at `d323-stream` 0e2c37ab, landing after RW-1): `JsonStreamItem` gains `end`, with
`source[offset:end]` exactly the element's JSON text (absolute offsets in a stored object opened at 0). The reader passes
`Locator(p="/traces/<i>", bytes=(element.offset, element.end))` (`bytes` never enters the source key when `p` is present,
C.4.1); the mapper carves with `{"bytes": [s, e], "p": "/<path inside the trace>"}`, so only that element is parsed.
