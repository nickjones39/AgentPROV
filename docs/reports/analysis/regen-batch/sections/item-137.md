## Item 137 (implemented, held; 2026-10-21; D-608, bug pass bugpass-perf-10, pre-check PC-agentops-bench-01; user decision 2026-10-21: approved, D-604): agentops tool-output redaction and object-scope withholding

Held branch `bugpass-regen-agentops-sec` (from the held `bugpass-regen-agentops`, items 34, 36, 37). The change is
folded into that branch's unreleased version 2 of profile `agentops-bench-pilot` and catalogue `agentops`: no stored
or scratch corpus records version 2 (the only records are the phase-10i scratch trial's, at version 1, profile
`6e109f28477a`, catalogue `5a9e6a03bf42`; both archives are unchanged and pinned by `tests/adapters/agentops/test_d31_bump.py`).

**What it does.** `adapters/agentops/redact.py` (the D-476 grammar, scope `tool_output`) rewrites `/Users/<account>`
in the values of tool messages to `acct-{span12}`, as a mapper post-pass; the profile's `[withhold]` rule
`account-path` (`personal_data`, scope `object`) withholds the raw objects that hold the path at sealing.

**Census (pinned tar `e185bfd0…`, every member read in memory; counts only).**

| Members | Count | Matching `/Users/[A-Za-z0-9._\-]{1,64}/` |
|---|---|---|
| selected in-scope run files | 3,360 | 13 |
| out-of-scope run files (`select.out_of_scope` globs) | 3,842 | 23 |
| per-model rollups (`*_report.json`) | 9 | 6 |
| other side files | 5 | 0 |
| AppleDouble `._*` | 7,270 | 0 |
| **all** | 14,486 | **42** (one account; escaped `\/Users\/` form: 0) |

**Redaction census (D-154 method: the 13 path-bearing in-scope runs mapped in memory through the product path with
their task YAMLs, then SEM `agentops.tools@2` and PROV `agentprov-prov/0.1`; counts only).**

| Measure | Count |
|---|---|
| in-scope runs mapped, degenerate | 13, 0 |
| raw tool results holding the account (result text 12, `stdout` 13, `stderr` 1) | 26 |
| redacted pointers (`ext.agentops.redacted`), executions with the info issue | 26, 13 |
| raw assistant text, call arguments or `final_output` holding the account | 0 |
| AER, SEM, PROV documents of these runs holding the account or matching the withhold pattern (residue) | **0, 0, 0** |
| task YAMLs (101) matching the withhold pattern | 0 |

The other 3,347 in-scope runs hold no `/Users/<name>/` path in their raw bytes, and the joined task YAMLs hold none, so
no AER, SEM or PROV statement of the full import can hold the account: residue 0 for account #1 (resolves
PC-agentops-bench-01). Withholding at sealing, by the rule over these counts: the 13 selected run objects
(`profile_rule`, `personal_data`, scope `object`) and the tar (container of a withheld member; the decoded scan's hits
in the 23 out-of-scope runs and 6 rollups); 0 executions withheld; 3,360 released. The mechanism is the one
`tests/adapters/agentops/test_withhold_e2e.py` seals end to end. The in-memory census on the real tar settles the
residue (0) and the 0-execution result. The seal-count confirmation on real data (13 run objects and the tar
withheld, 0 of 3,360 executions) is deferred to the round's real seal: the scratch import and seal ticket
(`d608-agentops-census-2`) was cancelled on 2026-10-21 at the orchestrator's request (import lane congested) before it
started, so no scratch corpus was written.

**Byte impact.**

| Artefact | Change |
|---|---|
| AER of the 13 path-bearing in-scope runs | tool-message values redacted; `evf` `D`, rule `agentops.value_redacted@1`, `ext.agentops.redacted`, info issue `agentops.value_redacted` |
| AER of the other 3,347 in-scope runs | the header's `profile.sha256` only (the v2 profile bytes; `rules` records versions, still `agentops` 2) |
| SEM, PROV of every agentops execution | the AER digest they derive from and the `agentops` v2 catalogue digest where they cite it; the semantics profile `agentops.tools@2` is unchanged |
| raw store | unchanged (raw bytes are never edited); the 13 run objects and the tar are withheld at sealing |
| stored corpora | none (the registry part is `planned`) |

