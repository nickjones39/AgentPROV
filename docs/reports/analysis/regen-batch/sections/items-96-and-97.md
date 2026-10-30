## Items 96 and 97 (R-10j-4, R-10j-5, routed from phase 10j; approved for the round; held branch `regen-held-rd`)

Spec: D.6.22 items 8 and 9. Tests: `tests/adapters/agentdojo/test_r10j45.py` (7 tests; 6 fail on the unfixed mappers).
- **96 (R-10j-4).** A negative logged `duration` is kept verbatim in `t.raw.dur`, declared `ambiguous`, instead of a
  `dur_s` the schema refuses. `run_duration` is shared by both builds. `_run_start_v1` merges into `t.raw`; this is
  byte-neutral because `raw` was absent before.
  - Not done as routed: an info issue `agentdojo.negative_duration`. It would mean an `agentdojo` catalogue bump (D-31)
    for a note the `unk` declaration already carries.
- **97 (R-10j-5).** The DRIFT build calls item 87's `_ambiguous_tool_names` (CD-10).

**Predicted.**
- The `agentdojo` family code digest moves.
- No stored AER byte moves: a negative duration or a deny-listed tool name could only fail the seal, and stored corpora
  hold no `adapter_defect`.
- Phase 10j's two Figshare CaMeL logs and one Figshare DRIFT log seal at their import.

Also noted: phase 10j widened a stale pin in `test_defence_denial.py` (shipped-profile list 7 → 10, any part names);
it arrives with the next main merge.

