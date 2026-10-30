# Phase 10f routing (D-156, user-approved 2026-10-12)

Three changes outside phase 10f's files block full imports of the two phase-10f sources. Each goes through the
orchestrator to its owner. Phase 10f changed none of these files. Evidence and counts: `README.md` in this folder.

| # | Item | Owner | Blocks | Evidence |
|---|---|---|---|---|
| F1 | **Archive inputs.** The runner imports git trees and Inspect containers, but not a deposit archive whose members are whole run logs (deferred in D_adapters §D.6.15). SEAgent's 5,342 AgentDojo logs are direct members of Zenodo 23218779 `seagent-acsac2026-ae-v2.zip`: no nested archive, no `:` in names, every member passes the G.3.5 gate. | runner (`adapters/runner/importer.py`, `raw/members.py`) | `seagent-agentdojo` trial and full import | census `seagent-agentdojo.census.json` (gate: 5,342 selected, 0 rejected) |
| F2 | **Member origins in the TraceLogger mapper.** The layout locator is `{"a": "a0", "o": "/path"}` (`adapters/agentdojo/mapper.py` l. 159). A `member` origin has `label`, not `path`, so the header fails `aer.locator.dangling` (AER-V21). The mapper should read `/label` for a member origin, `/path` for git and hf. | agentdojo mapper (regen-batch) | `seagent-agentdojo`, and any other zip-held AgentDojo source (Figshare 32657856, Zenodo 22973265) | `tests/adapters/agentdojo/test_phase10f_seagent.py::test_a_member_origin_does_not_seal_yet_d156` (replace it with a release-mode import test when fixed) |
| F3 | **Inspect call identity for `inspect_ai` 0.3.130 and 0.3.134.dev31.** In 3,452 of 9,200 WhistleBench samples one tool-call id maps to two call parts. The mapper sets the execution's `call` and the result's `responds_to` to `ambiguous` (`call_result_link_conflict`, then `unexecuted_tool_call`; `mapper.py` l. 1042 and 1487). Example: a `write_file` call whose id agrees across the assistant message, the model event output and the tool event. Separately, in 8,401 samples the react agent's final `submit` call is a tool event whose message was pruned (`missing_tool_result`, `dangling_source_ref`). | Inspect mapper (regen-batch) | `whistlebench` full import (D-155) | `whistlebench.trial.json`; per-sample breakdown by producer and task in the README |

Status at merge (2026-10-12): F1 is part A of the deferrals session (AGENTS.md §0, "D-156 part 1") and F2 goes through
the regen-batch session ("D-156 part 2"), both already assigned by the orchestrator. F3 is sent to the orchestrator with
this note.

Also open (not blockers): a rule for defence-authored messages (SEAgent guard warnings in the user role; with phase-10d
routing R1; D-153), and a WhistleBench semantics profile (scorer claims, tool table).
