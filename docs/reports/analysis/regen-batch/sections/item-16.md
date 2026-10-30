## Item 16 (implemented 2026-10-13, user-approved with the fetch extension; revised 2026-10-12 after the Inspect fetch; phase 10f F3, D-155): Inspect message copies, tool-event message ids, and the react `submit` result (WhistleBench)

**Evidence.** The user approved fetching the producer code (2026-10-12): `UKGovernmentBEIS/inspect_ai` tags `0.3.130`
(`de88fe0b`) and `0.3.133`/`0.3.134`, blobless, depth 150, at `$AGENTPROV_HOME/upstream/github.com/UKGovernmentBEIS/inspect_ai.git`
(logged in `acquisitions.jsonl`). The WhistleBench harness actors record `inspect_ai` `0.3.130` (8,050 samples) and
`0.3.134.dev31+geb46eef8` (1,150); `eb46eef8` is exactly 31 commits after tag `0.3.133` and an ancestor of `0.3.134`, so
both producer commits are pinned. The code cited below is the same at both (between them `_react.py` changes only in
typing, `_model.py` only in hooks and cache-usage reporting). WhistleBench itself (`legobridge/whistlebench@9c27637`, the
profile's pin, cached in staging) calls `react(name="Agent", submit=AgentSubmit(name="Submit", ...))`
(`highagency/whistlebench/tasks.py` l. 74-87; snitchbench uses the default name `submit`), with `keep_in_messages` at its
default `False` (`agent/_types.py` l. 127). Every count below is from the scratch corpus, read through the AERs and the
stored sample bytes (strict JSON loader), counts only.

**(a) One message, several stored forms: explained by code, so class D.** Every copy is a pydantic `model_copy`, which
keeps the message `id` and its `tool_calls`; only `content` (and, for submit, `tool_calls`) changes:
- `_remove_submit_tool` (`agent/_react.py` l. 483-525, called at l. 292 once the agent completes) rewrites the assistant
  message in `messages` without the submit call and without its last `reasoning` item. Shape counts: 9,190 message-id
  groups whose output-choice copy holds a submit call that the `messages` copy lacks (2,909 of them also lose the
  reasoning item); every non-submit call identical across the copies.
- `resolve_reasoning_history` (`model/_model.py` l. 1146-1231 at `0.3.130`, l. 1164-1249 at `eb46eef8`, applied at
  l. 575/589 before the `ModelEvent` records `input`) drops or `<think>`-emulates reasoning in the history re-sent to
  the model. 2,836 groups: `messages` copy with reasoning, replayed `input` copy without.
- 0 groups whose non-submit calls differ. The 11 duplicates across different message ids stay ambiguous.

**(b) The tool event's `message_id` is the first result message of its batch: an Inspect defect, class D.** In
`execute_tools` (`model/_call_tools.py`), `result_messages` is created once per assistant message (l. 251), outside the
per-call loop (l. 253), and each `ToolEvent` gets `message_id=result_messages[0].id` (l. 321). So for the second and
later calls of a parallel batch, `message_id` names the *first* call's result message. Effects in the scratch corpus:
6,826 tool-result messages have no generating execution (the mapper links an execution to its result through
`message_id` and never overwrites a link, so no execution is linked to a wrong result, but the later results are
orphaned); 795 submit events "find" another tool's result message. AgentHarm (stored): 0 orphaned results, 4,148 links
all matching the answered call; nothing there moves.

*Range (phase 10h's measurement, relayed 2026-10-12; `~/.agentprov/migration-work/phase10h/scripts/parallel_calls.py`,
recorded there as R-H4):* fragfuse logs at `inspect_ai` `0.3.154.dev37+g1289c1ad` (802 parallel batches in 620 samples;
1,617 of 5,078 tool events name another call's result) and `0.3.159.dev20+g3ddd7997` (87 batches in 73 samples; 155 of
567) show the same defect, and those 693 samples are exactly the fragfuse trial's 693 `accounting_inconsistent`
(`aer.acc.executions_have_results@1`) samples; `0.3.158` had no parallel batches; kexin at `0.3.263` (1,551 batches) has
every present `message_id` agreeing with its call, so the defect is fixed by then. So it is observed from `0.3.130` to at
least `0.3.159.dev20`. The code is cited (D) at the two WhistleBench commits only; fragfuse's commits `1289c1ad` and
`3ddd7997` are not in the fetched history, so for them the fallback link is I unless the same fetch is extended to those
two commits (a separate yes).

**(c) The submit result is recorded in the tool event; only its message was removed.** All 9,201 submit tool events
carry `result` (a string; 56 empty). For 8,404 of them the result message is absent from `messages`, removed by
`_remove_submit_tool` (it drops every tool message of the submit function). The other 797 are the (b) cases. So the
item's earlier reading ("not recorded") is wrong: the value is observed; what is missing is the message, by the
harness's design.

**Proposal.**
1. *(a)* When every part holding a `ToolCall.id` belongs to messages of one Inspect message id and the calls are
   byte-identical, the call is one call: `call` and `responds_to` resolve to the copy the call was produced in (the
   model output choice, else the `messages` copy, never a replayed input). New rule
   `inspect.message_copies_share_calls@1`, **class D**, citing `_react.py` l. 483-525 and `_model.py`
   `resolve_reasoning_history` at both commits. Message records stay separate; no content is merged.
2. *(b)* A tool event's result message is found by `tool_call_id` equal to the event's `id` (the call id); `message_id`
   is used only where it agrees. The rule is version-independent in what it does (it trusts the call id, which every
   version writes correctly), so it applies to every Inspect profile; its class follows the citation policy (D where
   the producing commit's code is cited, otherwise an `_unverified` twin, I). New rule `inspect.tool_event_message_id_first_of_batch@1`, **class D**, citing
   `_call_tools.py` l. 251-321 at both commits, on the links made by the fallback. Where `message_id` agrees (every
   AgentHarm link, every first call of a batch), the existing citations stay, so AgentHarm's bytes do not move.
3. *(c)* For an execution of the profile's declared submit tool whose result message was removed: the result is mapped
   from the event's `result` as an artefact `generated_by` the execution (`inspect:tool_result`, located at
   `/events/<k>/result`, O), no result message is invented, and the absent message is declared, not raised as
   `missing_tool_result`/`dangling_source_ref`. New rule `inspect.react_submit_message_removed@1`, **class D**, citing
   `_react.py` l. 292 and 483-525 and WhistleBench `tasks.py` l. 74-87. Profile key: `[family.inspect]`
   `submit_tools = ["Submit", "submit"]` in `whistlebench.profile.toml`.

**Digest prediction.**
- **Stored corpora:** no AER changes (AgentHarm: 0 orphaned results, 0 call-link conflicts, its 4 missing results are
  not submit; the new rules fire nowhere there). The `inspect` catalogue and adapter code digests move, so the PROV of
  `ast-survey-agentharm` changes in its catalogue attribute only.
- **fragfuse** (phase 10h, scratch only; no fragfuse corpus exists outside scratch): AER bytes change in the 693
  affected samples; their `accounting_inconsistent` should clear. Measured on the 10h scratch import after
  implementation.
- **WhistleBench** (trial only, D-155): about 3,440 of 3,452 samples lose `call_result_link_conflict`; 6,826 orphaned
  results gain their generating execution; 8,404 `missing_tool_result`/`dangling_source_ref` pairs become declared
  removals with the result kept as an artefact; `accounting_inconsistent` falls with them. To be measured on the
  scratch corpus after implementation, before WhistleBench is imported.

**Rejected:** merging the copies (loses what the model was re-sent); matching by call id alone without the
same-message-id condition (hides the 11 genuine cross-message duplicates); trusting `message_id` (wrong for every later
call of a batch at these versions); inventing a result message for submit (the model never saw one); class I (the
behaviour is read from the pinned producer code at both versions).

**Implemented (2026-10-13, branch `claude/item-16-inspect`; D-155 addendum).** The user approved item 16 and the fetch
extension to fragfuse's commits: `1289c1ad` is 37 commits after tag 0.3.153 and `3ddd7997` 20 after 0.3.158 (fetched as
tags 0.3.153/0.3.154/0.3.158/0.3.159 into the same blobless store, logged). The cited code is the same at all four
producer commits, so all three rules are class D with `code` lists at each. Two refinements found while implementing:
- **(b) is narrowed to the defect's signature:** the call-id fallback applies only where `message_id` names a tool
  message that answers another call. A `message_id` naming no message stays unlinked with `missing_tool_result`
  (`test_mapping_rows.py::test_dangling_tool_message_gives_missing_tool_result` keeps its meaning), so AgentHarm's 16
  missing results are unchanged.
- **Declarations, not silence:** the core accounting counts a result only through a message's `generated_by` or a listed
  `missing_tool_result`, and a call part only through an execution, a denial or a listed `unexecuted_tool_call`
  (invariant 5: no core change). So the copies' parts are listed `unexecuted_tool_call` citing
  `inspect.message_copies_share_calls@1`, and a removed submit message is listed `missing_tool_result` citing
  `inspect.react_submit_message_removed@1`, with its value kept as the artefact. No `dangling_source_ref` for it.

Code: `adapters/inspect/mapper.py` (`_produced_copy`, `call_part`, `_tool_message`, `_submit_result`, the copy
declarations), `family.schema.json` (`submit_tools`), `whistlebench.profile.toml`, the catalogue (three rules and type
`inspect:tool_result`). Tests: `tests/adapters/inspect/test_item16.py` (5).

**Measured** (re-mapped from the stored member objects, old code = `origin/main` 733a78f, new = this branch):
- `ast-survey-agentharm` (stored): AER bodies identical in 1,056/1,056; only the `inspect` catalogue and code digests move.
- WhistleBench scratch (9,200): accounting consistent 9,190 (old 4,534), inconsistent 10 (old 4,666);
  `call_result_link_conflict` issue entries 48 (old 12,304); tool results without a generator 2 (old 6,826); submit
  results kept as artefacts 9,195, each with a declared `missing_tool_result`; genuine missing results 18 with
  `dangling_source_ref` (old 8,416 of each).
- fragfuse: to be measured on the phase-10h scratch import.

