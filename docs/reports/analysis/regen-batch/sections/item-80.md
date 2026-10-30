## Item 80 (implemented 2026-10-14; R-10p-7, routed from phase 10p; user-approved for the round; branch `r10p7-sandbox-output`): Inspect sandbox events without an output

**Status: lands on main alone** (user decision 2026-10-14, relayed by the orchestrator), ahead of the round, so that
phase 10p can seal. The `map` stage code digest moves for every Inspect corpus (`adapters/inspect/mapper.py`). The
corpora are re-derived in the regeneration round, and no stored AER, SEM or PROV bytes move.

**Defect.** `InspectEvalMapper._sandbox` emitted an `inspect:sandbox_output` artefact (`ev = "O"`, `by = "source"`) for
every top-level `sandbox` event. When the event holds no `output` string (`write_file`, or an `exec` whose output is
null) the artefact's only asserted fields are D (`/type`, `/generated_by`) and its content is `unk`. So the writer refuses
the record set (AER-V12 `by_without_bare_O`) and the runner seals the sample degenerate (`map.adapter_defect`,
`aer.write.invalid`). Phase 10p's trial t1 had 5,522 of 5,522 control-arena executions affected.

**Choice (this session's call, as routed).** No artefact when the event records no output string. An empty string
is still an output and keeps its artefact. The source records no generated entity, so none is claimed (invariant 2).

*Rejected:* keeping the artefact without `by = source` or bare-O evidence, which would be a placeholder entity with
unknown content that no field of the source attests.

The activity record (`inspect:sandbox_<action>`, status, `ext` fields, times) is unchanged. The catalogue rule
`inspect.sandbox_activity@1` ("whose output is an artefact") still holds, so there is no catalogue or profile change
and no bump. D.9 mapping row amended.

**Predicted.** The `map` stage code digest moves (`adapters/inspect/mapper.py`) for every Inspect corpus. No AER, SEM or
PROV bytes move in any stored corpus: the old path could only produce a refused record set, so any affected sample
was already degenerate, and stored Inspect corpora hold no `adapter_defect`. Control-arena (not stored; phase 10p) goes
from degenerate to mapped samples.

**Measured.**
- `ast-survey-agentharm-p10.partial`: 1,056 AERs, 0 sandbox activities, 0 `sandbox_output` artefacts, 0 `adapter_defect`.
  Byte-neutral.
- There is no stored whistlebench corpus.
- `tools/regen_pins.py --check`: every family is current.
- `tests/adapters/inspect/test_r10p7_sandbox.py`: 3 no-output cases fail on the old mapper and pass on the fix, and
  2 output cases pass on both.
- Phase 10p's strict xfail `test_a_sandbox_write_without_output_maps_to_valid_aer` (on `phase-10p-holds` bfd0e7d7)
  stays failing on the fix, for a second reason in its synthetic event: `completed=s.tick(0.1)` is evaluated before
  `event()` ticks the clock for the event's own timestamp, so the event ends before it starts (AER-V19
  `aer.order.time` `start_after_end`, `adapter_defect` again). With the times in order, the same event maps cleanly
  (the `write-null` case here). Phase 10p fixes its fixture and drops the marker.

