## Items 26 and 27 (implemented, 2026-10-13; user-approved; routed from phase 9b): AgentDyn's nondeterministic tools and AgentDyn tool labels

**Item 26 (R-9b-1): a D.15 artefact entry.**
- **Finding (phase 9b):** AgentDyn's tool clients in the AutoDojo fork (`aa458794`) call `random` and the clock
  inside tool calls:
  - `shopping_client.py`: OTP l.150, order ids l.818, `date.today()` l.646 and l.798;
  - `github_client.py`: OTP l.119;
  - `dynamic_banking_client.py`: OTP l.48;
  - `dynamic_email_client.py`: l.39 and l.70;
  - `cloud_drive_client.py`: l.41 and l.62.

  OTP flows put random values into tool results. Two scripted live `shopping` runs had identical `pass.start` state
  digests and different `pass.end` ones.
- **Proposed entry** (`adapters/agentdojo/artefacts.toml`):
  - `id = "agentdyn.art.nondeterministic_tools"`, `cause = "benchmark"` (9b proposed `upstream_benchmark`, which
    is not in D.15's cause list);
  - handling class `FO` (flag only: the values are recorded as observed, and nothing is reconstructed);
  - scope: profiles `agentdyn` and `autodojo-live`; `manuscript = true` (a reproducibility caveat for AgentDyn
    cells); `expected = []` until a detector is cited.
  - A `detector.rule` must be a catalogue rule. The proposal is a new class-D rule
    `agentdyn.nondeterministic_tool_state@1`, whose code list is the lines above. It is cited by nothing yet. A later
    quirk could cite it on the listed tools' executions; that would be a separate decision, and it would change
    AgentDyn AERs.
- **Prediction:**
  - The `adapters/agentdojo` code digest moves (manifests).
  - The `agentdyn` catalogue digest moves, which enters the PROV derivation key of every AgentDyn execution (38,281
    in `agentdyn-a-p10`) at its next re-derive. Item 22's AgentDyn re-map (`profile.sha256`) already needs that
    re-derive, so the two can share it.
  - No AER or SEM byte changes, since nothing cites the rule.
  - Rejected: putting the rule in the `autodojo` catalogue (the code is AgentDyn's, and it also produced the stored
    AgentDyn logs); a generic detector (none fits, and none is planned).

**Item 27 (R-9b-2): AgentDyn tools are labelled `unknown`.**
- **Finding:** two gaps, not one.
  - (a) The live capture mapper writes `task.benchmark` verbatim from the cell (`"agentdojo"`, AutoDojo's name for
    everything). The TraceLogger mapper instead takes it from the profile's `[family.agentdojo.benchmark] suites`
    map (D.6.5 step 1). `autodojo-live` already maps `shopping`/`github`/`dailylife` to `agentdyn`, so a live
    AgentDyn cell reads as an AgentDojo suite, and `agentdojo.suites@1` has no table for it.
  - (b) Even with `benchmark = "agentdyn"`, neither `agentdojo.suites@1` nor `@2` has a table for AgentDyn's suites.
    `reviewed_tables.toml` covers only `craibench`. The stored `agentdyn-a-p10` corpus also labels its AgentDyn tools
    `unknown` (fail-closed).
- **Proposed:**
  - (a) The capture mapper takes `task.benchmark` from the profile's suites map when the profile declares one, as
    the TraceLogger mapper does. It keeps the cell's value in `ext.agentdojo.cell_benchmark` (O) only where the two
    differ. The live profile is pinned to the fork (`aa458794`), so the map is keyed by the fork's identity, not by
    a version string.
  - (b) A reviewed AgentDyn table (C.14.8): per (`agentdyn`, suite), the tools of `shopping`, `github` and
    `dailylife` with their roles, integrity and channel. It is read from AgentDyn's tool code at the pinned
    commits. It goes in a new semantics version `agentdojo.suites@3`, so no corpus on `@1`/`@2` changes. The
    AgentDyn and `autodojo-live` profiles would select `@3` by a profile change, which is separate (it moves
    AgentDyn's SEM at its next re-derive).
- **Prediction:**
  - (a) Live AutoDojo AERs of AgentDyn suites change in `task.benchmark` and gain the ext key. No stored corpus is
    affected (none is live AutoDojo). The capture fixtures of AgentDojo suites are byte-identical, since the map
    gives `agentdojo` for them.
  - (b) A new profile version only, with no stored SEM byte. The table needs a review pass of AgentDyn's tool code,
    which is the main cost.

**Implemented (2026-10-13).**
- **Code identity:** AgentDyn's task suites and tool clients at its pin 5353cf76 have the same blob ids as the AutoDojo
  fork's at aa458794. So one code state serves both the stored and the live AgentDyn data.
- **Item 26:**
  - New rule `agentdyn.nondeterministic_tool_state@1` (class D), whose code list is the eleven lines, checked against the
    code.
  - New entry `agentdyn.art.nondeterministic_tools` (`FO`, cause `benchmark`, manuscript). Its scope is `agentdyn` (parts
    `a`, `c`) and `autodojo-live`.
  - The catalogue's artefact count is 45.
- **Item 27 (a):**
  - The capture mapper takes `task.benchmark` from the profile's suites map for an AgentDyn suite: D, under the new rule
    `agentdyn.suite_benchmark@1`. The cell's value goes in `ext.agentdojo.cell_benchmark`. AgentDojo suites are
    unchanged.
  - `autodojo-live` declares the `agentdyn` catalogue. `ext.schema.json` allows `cell_benchmark` and requires nothing on
    the execution.
- **Item 27 (b):**
  - New profile `agentdojo.suites@3`: a byte copy of `@2` plus three reviewed tables, (`agentdyn`, `shopping`/`github`/
    `dailylife`) with 39/34/27 tools. Its code and data are cited per tool.
  - The tables were built from two reviews of the code at the pin, spot-checked against the code: roles from each tool's
    executed function, and content sources from where each suite's environment places its injection vectors.
  - Rulings:
    - reading unread e-mails is not a write;
    - the calendar tools that e-mail are send sinks;
    - a passcode e-mailed to the user's own inbox is a write;
    - exposure through a copy (a download, a clone, a sent e-mail) makes a content source.
  - For live sessions, `autodojo-live` reads the version label as `suite_version_for_agentdojo_suites_only`, as the
    `agentdyn` profile does. The capture mapper records that reading on the benchmark actor, as the TraceLogger mapper
    does. Without it, the recorded `v1.2.2` label would select no reviewed table.
  - `suites@1` and `@2` are unchanged (data and digests).
  - **Selected (user decision, 2026-10-13):** the `agentdyn` profile and its registry parts `a`, `b` and `c`, and
    `autodojo-live` and its registry part `live`, read `agentdojo.suites@3`.
    - The `agentdyn` profile digest moves once more, again only in `profile.sha256`: all 14 fixtures were re-checked
      masked, and the pins regenerated.
    - The stored `agentdyn-a-p10` keeps its `@1` SEM until its next re-derive. That re-derive goes together with item
      22's re-map and needs its own yes. At that point its AgentDyn tools get reviewed labels instead of `unknown`.
- **Checked:**
  - On the AgentDyn fixtures, the tool outputs are `unknown_tool` under `@2` and reviewed labels under `@3`. The one
    remaining unknown is a tool message no execution generated, which fails closed correctly.
  - A live AgentDyn `shopping` cell is unknown under `@2` and labelled under `@3`.
  - Tests: `tests/adapters/agentdojo/test_items_26_27.py` (5).
