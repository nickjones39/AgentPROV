# Phase 10l, parts B and C: scratch mapping trials

Status 2026-10-13, branch `phase-10l-drift`. Every DRIFT-format file of every in-scope source was mapped through the
DRIFT build (`DriftMapper`), sealed, and validated by the AER validator in **release** mode; the profile census was
recomputed from the sealed AERs and compared with the declared `observed` counts. Script:
`~/.agentprov/migration-work/phase10l/scripts/m01_map_snapshot.py` (outside Git); results in
`~/.agentprov/migration-work/phase10l/mapping/`. No corpus was written: these are mapper-level trials. Product-path
imports (`agentprov import`, derive, validate tiers) wait for the routed dispatch RT-1 (`routing.md`), because until then
the importer's `TraceLoggerMapper` still seals DRIFT files as `unsupported_variant`.

| Source (profile) | Files | Mapped | Valid | Decisions | Messages | Tool executions | Model calls | Census | AER-set digest |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| DRIFT head (`drift` · `head`) | 1,569 | 1,569 | 1,569 | 6,722 | 16,868 | 6,175 | 8,291 | all declared counts reproduced | `0a1f921aef407494…` |
| DRIFT history (`drift` · `history`) | 1,046 | 1,046 | 1,046 | 3,243 | 9,057 | 3,580 | 4,289 | all reproduced | `eda6bdc0f06d4c86…` |
| AgentDyn C (`agentdyn` · `c`, RT-2 applied in memory) | 4,258 | 4,258 | 4,258 | 21,932 | 54,239 | 19,997 | 26,192 | all reproduced | `4579512d8327a92b…` |
| EnvironmentOptim, new 620 (stand-in: the RT-2 AgentDyn profile) | 620 | 620 | 620 | 3,393 | 8,237 | 3,229 | 4,013 | — | `36fa22127d0825a7…` |
| drift-1, new 626 (stand-in: the `drift` profile, `initial_plan`) | 626 | 626 | 626 | 2,337 | 6,061 | 2,206 | 2,963 | — | `54fd812acbb9b857…` |

- **Decisions** = isolation passes (one per call batch) + CALL ERROR denials: head 5,889 + 833, history 3,101 + 142,
  AgentDyn C 18,140 + 3,792. Messages, tool executions and model calls equal the census's message, tool-message and
  assistant counts exactly.
- **Determinism:** the AER-set digest of DRIFT head is identical with 10 and with 3 worker processes.
- **Seal issues** (per file): `accounting_unverifiable` everywhere (model calls are derived from messages, D.6.9);
  `drift.agent_prompt_not_recorded` (info) everywhere; `drift.injection_map_not_recorded` (info) on every attacked run;
  `drift.calls_in_text_not_executed` head 317, history 84, AgentDyn C 2,004, EnvironmentOptim 242, drift-1 78. The
  stand-in trials add what their real profiles must settle: `agentdojo.pipeline_name_mismatch` (EnvironmentOptim's
  directory has a variant-A identity row; drift-1's PACT directory), drift-1's 10 `agentdojo.unknown_top_level_key` (PACT
  keys) and 9 `drift.call_error_unrecognised`.
- **Not run:** AgentDyn D (byte copies of DRIFT head, owned by `drift`); Figshare's DRIFT part (excluded by the user:
  no attack succeeded, D-279 addendum).
- **Tests:** `tests/adapters/agentdojo/test_drift.py` (18 tests over nine MIT fixtures from DRIFT head, golden AER digests
  in `drift_aer_digests.json`, regenerate with `AGENTPROV_REGEN_DRIFT_AER=1`).
