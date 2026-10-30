## Item 25 (implemented, 2026-10-13; user-approved; routed from phase 10n, ATIA; D-155 addendum 2): Inspect tool events without `message_id`, audio and video

**Evidence.** The producer code was read at tags 0.3.112..0.3.130 (fetched 2026-10-13 with the user's yes;
`acquisitions.jsonl`).
- At 0.3.112 `ToolEvent` has no `message_id`. `execute_tools` builds every event with `id=call.id` and every result
  message with `tool_call_id=call.id`, on the normal, cancelled and handoff paths.
- `message_id` first appears at 0.3.113, already written as `result_messages[0].id` with `result_messages` built
  outside the per-call loop. Item 16's first-of-batch defect therefore starts at **0.3.113**. Item 16 said "from at
  least 0.3.130"; its rule text and code list gain 0.3.113 when this item lands.
- From 0.3.113 on, logs are written with `exclude_none=True` (`log/_file.py`, `_recorders/eval.py`). An event with no
  result message (`message_id=None`) is therefore also written without the key. "Key absent" does not identify
  0.3.112 by itself.

**Measured (phase 10n, ATIA: 5 logs, inspect_ai 0.3.112, 123 samples).**
- 81 of 81 tool events have no `message_id`. 81 of 81 tool messages carry the matching `tool_call_id`, and the event
  `id` equals the call id in 81 of 81.
- Today, all 81 calls seal `missing_tool_result` + `dangling_source_ref`, also after item 16, whose fallback runs only
  when `message_id` names another call's result.
- 59 `audio`/`video` content items fall to `inspect.unknown_content_type`. They are kept verbatim as `other` parts.

**Proposed change** (`adapters/inspect/mapper.py`, `rules/inspect.rules.toml`):
- (a) New rule `inspect.tool_event_no_message_id@1` (class D, code list at 0.3.112).
  - When the producer is inspect_ai < 0.3.113 (the header's `eval.packages.inspect_ai`, parsed as a version), link a
    tool event to the one tool message whose `tool_call_id` equals the event `id`. Two or more such messages, or none,
    stay unlinked (fail-closed).
  - At ≥ 0.3.113 an absent key keeps today's handling: the result was never created.
  - An unparsable producer version keeps today's handling.
- (b) `audio` and `video` items map like `image`: a `uri` part from `audio`/`video` (a path, URL or `data:` URL;
  `attachment://` resolved as today), with `format` kept in the part's `ext`. They no longer raise
  `inspect.unknown_content_type`.

**Prediction.**
- No stored AER, SEM or PROV byte: no stored or profiled Inspect source is below 0.3.113 or carries `audio`/`video`.
  Goldens and gate D are unchanged; this is checked by re-mapping the stored AgentHarm and the WhistleBench scratch
  members.
- The `adapters/inspect` code digest and the `inspect` catalogue digest move, so the `aer` stage `fn_digest` of
  Inspect corpora moves at their next import or re-map.
- ATIA (not yet stored): 81 calls linked, 0 `missing_tool_result`/`dangling_source_ref` from this cause, and 59 media
  parts as `uri`. To be confirmed on 10n's corpus.

**Implemented.** The change is as proposed:
- `without_message_id` is the version gate: a release `X.Y.Z`, optionally `.devN` and `+local`, up to 0.3.112.
- `_by_call` serves rules (a) and item 16 (b).
- The new rule's code list is at 0.3.112 and 0.3.113. The first-of-batch rule gains the 0.3.113 citation, and
  `inspect.message_content_parts@1` names audio and video.

Checked:
- AER bodies re-mapped from stored members are byte-identical to item 16's: AgentHarm 1,056 of 1,056, scratch
  WhistleBench 9,200 of 9,200. Issue counts are unchanged.
- ATIA on bfa1951, before this item (phase 10n): `missing_tool_result` 81, `dangling_source_ref` 81,
  `inspect.unknown_content_type` 59 (49 audio, 10 video; the 39 images were already `uri`). The same counts on
  52c0974, so item 16 does not touch ATIA.

Tests:
- `tests/adapters/inspect/test_item25.py`: the version gate (13 cases); linking before 0.3.113; not linking from
  0.3.113; audio and video as `uri`, with `format` in `part_extra`.
- `test_mapping_rows.py::test_row_message_parts`: audio is now a `uri`, and a synthetic unknown type keeps the
  `unknown_content_type` path.
- Phase 10n's strict xfail `test_atia.py::test_the_execution_generates_its_result_without_message_id` XPASSes once this
  lands, and 10n flips it.

**Not in this item:** 42 strings over 1 MiB in ATIA (C.2.1(6); R-10n-2): 20 image data URIs and 4 video values in
message parts, and 18 Gemini `inlineData` copies in `model_call.params.transmitted`. They need their own item.
