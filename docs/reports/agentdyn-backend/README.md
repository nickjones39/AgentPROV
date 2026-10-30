# AgentDyn live backend: report

Session "AgentDyn backend" (2026-10-22). Design: [design.md](design.md). Spec: D.11.10. Decisions: D-680..D-688
(DECISIONS.md). Scripted transport only: no key, no real model call, `.env` never read.

## 1. What was built

| Branch / commit | Content | Class |
|---|---|---|
| `agentdyn-backend` `bae32cca` | `backends/shared`: `AgentDynBackend` (identity pinned by PEP 610, `gateway_compat` and every defence refused, five `agentdyn.*@1` items), `AGENTDYN_GUARDED_NAMES`, `select_backend`; `cli/live/envs.py` and the run refusals; spec, DECISIONS, AGENTS.md | 0 |
| `agentdyn-backend` `266444d8` | `backends/agentdyn`: project, lock, 22 backend tests; the supply-chain and boundary tests list it | 0 |
| `agentdyn-backend-core` (held) | `BACKENDS["agentdyn"]` with the CLI `backends build agentdyn` choice (they ride together for the GUI's parity test); the capability `agentdyn · live` (`planned`); profile `agentdyn-live` v1; artefact entries; README blocks; `tests/integration/test_run_live_agentdyn.py` | 1 |

## 2. Download (the user's typed yes, 2026-10-22)

- **What was fetched:** `https://github.com/SaFo-Lab/AgentDyn` at `5353cf76`, fetched by uv into its git cache: one
  pack of 97.45 MiB (89,788 objects; uv fetched full history, not a shallow clone). It was under the 500 MB cap. The
  uv lock itself read AgentDyn's metadata through uv's GitHub fast path, without a clone. No PyPI package was
  downloaded.
- **Process note.** My cap watch measured the growth of uv's git cache on disk, not the transfer. It stopped uv
  while uv was checking out the 598 MB `runs/` tree, after the fetch had completed. I removed the incomplete checkout
  that run left (its index had not been written) and re-synced with `--offline`. Every later step ran offline.

## 3. Verification

**Environment.**

- `direct_url.json` is `{url: https://github.com/SaFo-Lab/AgentDyn, vcs: git, commit_id: 5353cf76…}`, with no
  subdirectory.
- None of the seven overridden packages is installed.
- `agentprov backends build agentdyn` (offline, scratch home `~/.agentprov/migration-work/agentdyn-backend/home`):
  - environment `agentdyn-5353cf76`, Python 3.12.14;
  - RECORD `793b6813…`, lock `7ef22ee1…`, 1,478 files verified;
  - the sandbox-exec probe passed;
  - `--offline-check` passes.

**`run agentdyn --catalogue`:** 7 suites, which are workspace 40/14, travel 20/7, banking 16/9, slack 21/5,
shopping 20/9, github 20/9 and dailylife 20/10 user/injection tasks (157/63 in total). 17 attacks, 5 of them DoS.

**Backend tests (`backends/agentdyn`, 22).** All pass, with no network attempt and no import of an overridden package
or of `agentdojo.defenses`. They cover:

- identity: PEP 610, the guarded names, and the system prompt `21a1c00d…`;
- the catalogue;
- the four scripted cells;
- the worker over a subprocess, with a fake key that never reaches a file;
- the offline import audit.

**Executed comparison with AutoDojo** (the same script run in `agentdyn-5353cf76` and `autodojo-aa458794`):

| | AgentDyn | AutoDojo |
|---|---|---|
| tool definitions, shopping | `8e03e0b0…` | `8e03e0b0…` |
| tool definitions, github | `acf1c252…` | `acf1c252…` |
| tool definitions, dailylife | `64a41c73…` | `64a41c73…` |
| default system prompt | `21a1c00d…` (auto-complete line) | `a021a92b…` (AgentDojo default) |
| shopping injection ground truths | 9 × `send_money` stub | the attacker's actions (`input_to_webpage`, `browse_webpage`, cart/checkout/verify, `send_email`, `update_shopping_account_password`, …) |

**Scripted sessions S1–S4 through the CLI.** They ran through `tools/suite_queue.py --class import --cpu 2` into
scratch corpora under `~/.agentprov/migration-work/agentdyn-backend/`, which are `test_only` and never sealed for
release. Each campaign has its own corpus, because the campaign is part of the corpus id.

| Session | Cell | Row | `task.benchmark` | Issues | validate | recompute --dry-run |
|---|---|---|---|---|---|---|
| S1 | shopping user_task_0, benign | ok | agentdyn | none | 4 tiers pass | identical |
| S2 | github user_task_0 × important_instructions / injection_task_0 | ok | agentdyn | none | pass | identical |
| S3 | workspace user_task_0, benign | ok | agentdojo | none | pass | identical |
| S4 | dailylife user_task_0, one tool call with non-JSON arguments | ok_with_issues | agentdyn | `agentdojo.capture_reply_mismatch`, `missing_generated_by`, `accounting_inconsistent` | pass | identical |

All five corpora (S1, the refused first S2, S2b, S3, S4) are SEM `agentdojo.suites@3` ok and PROV ok. The first S2
attempt omitted `--model-display-name`. `important_instructions` names the model, so the worker correctly refused the
cell at setup and sealed the session `errored`. It was re-run as S2b with the option. Scratch size: 137 MB, kept until
told otherwise.

## 4. Findings (design §3.3)

| Id | Finding | Where it is recorded |
|---|---|---|
| F-1 | AutoDojo sends AgentDojo's default system prompt for AgentDyn's suites; AgentDyn sends its own, which adds the auto-complete line | `agentdyn.art.system_prompt_backend_dependent` (FO, manuscript) |
| F-2 | AutoDojo rewrote the 9 shopping ground truths, so `tool_knowledge` payloads differ between the backends | `agentdyn.art.shopping_ground_truth_backend_dependent` (FO, manuscript); pinned by a backend test |
| F-3 | The three AgentDyn suites are otherwise identical (blobs, and tool definitions by execution) | this report §3 |
| F-4 | A stray `shopping/environment——.yaml` is in AgentDyn's tree and wheel; it is never loaded | design §3.2 |
| F-5 | AgentDyn drops a tool call whose arguments do not decode to an argument object | `agentdyn.art.malformed_tool_call_dropped` (FO); D-685 |
| F-6 | **autodojo-live:** AutoDojo edits three AgentDojo workspace injection checkers (v1_2 `InjectionTask10.security`; v1_2_1 `InjectionTask11/12.security`), which filter non-string attachments; AgentDyn and stock 0.1.35 leave them unchanged | on the orchestrator's profile-edit list for the regeneration round (an `autodojo-live` caveat); not an entry here |
| F-7 | AgentDyn's own `uv.lock` is stale (it lacks 7 of 21 declared dependencies) | D-681 |
| F-8 | The wheel ships `defenses/`, including 949 vendored DRIFT run logs; none is imported or ingested | design §3.3 |

R-9b-1 (nondeterministic tools) now covers `agentdyn · live`: the backend runs the same tool modules.

## 5. D-685 (b): proposal for the orchestrator

**What S4 shows under (a).** The model call `mc0` is kept. The assistant message `m2` ("Checking.") is recorded, but
it has **no `generated_by`** link to `mc0`, and accounting is marked `inconsistent`
(`aer.acc.agent_calls_vs_assistant@1`). All the evidence for the link is in the capture:

- the wire reply's text equals `m2`'s;
- the only difference is the call that AgentDyn's `_openai_to_tool_call` could not convert. That function calls
  `json.loads(arguments)` and then validates `FunctionCall`, so a call is dropped exactly when its arguments do not
  decode to a JSON object.

**Proposal (b).** A profile-gated recognition in `adapters/agentdojo/capture_mapper.py`. When the live profile
declares the quirk `agentdyn.malformed_tool_call_dropped`:

- `_reply_agrees` first removes the wire calls whose `function.arguments` do not decode to a JSON object (or that
  have no `function`), then compares names as today;
- the reply links to its message with `generated_by` as usual;
- each removed call is listed in `ext.agentdojo.dropped_calls`, with a pointer into the response blob and evidence
  class D under a new rule `agentdyn.malformed_tool_call_dropped@1`. It is never dispatched (as C.12.2's
  listed-not-dispatched calls), so no tool execution and no provenance edge comes from it.

The change needs:

- catalogue `agentdyn` v3, with v2 archived;
- `agentdyn-live` pinning `agentdyn = 3`. The import profile `agentdyn` keeps v2, because imported logs carry no wire
  reply and the drop is not observable there.

**Effects.**

- Class 1: the agentdojo family's `adapter_code_sha256` moves, which this branch already moves.
- No stored corpus byte changes. No live AgentDyn corpus exists, and the stock and AutoDojo profiles do not declare
  the quirk.
- The capture fixtures and golden PROV of `agentdojo-live` and `autodojo-live` are unchanged, because the
  recognition runs only under the quirk.
- The S4 integration test changes from pinning the mismatch to pinning the link and the listed dropped call.

**Rejected.** Ungated recognition for every backend: stock and AutoDojo never drop calls silently, so there an unmatched
reply is a real capture defect and must stay reported. Leaving (a) permanently: it names the wrong cause, and it drops a
generation link the evidence supports.

## 6. Open

- D-685 (b): the orchestrator's decision (§5).
- The registered environment `~/.agentprov/envs/agentdyn-5353cf76` is built from the main checkout after
  integration (memory rule: the PEP 610 path of `agentprov-backend` would otherwise name this worktree).
- The defence session registers AgentDyn's defence ids equal to the upstream `PipelineConfig.defense` strings (its
  D-670/D-671). This backend keeps refusing every defence until its registry names `agentdyn`.

## 7. Hello under the real-model sandbox (2026-10-23, the L-DY blocker)

The live gates pilot's first L-DY dry run under `--containment sandbox-exec` stopped at hello with a fatal
`PermissionError` on `agentdojo/defenses/camel/.env.example` in the registered `agentdyn-5353cf76`. No model was
called. The CaMeL module was not imported. The cause was `identity.record_digest`: it took RECORD's path from
`importlib.metadata.Distribution.files`, which in Python 3.12 stats every file RECORD lists (`skip_missing_files`).
The real-model profile denies even a stat of `.env`/`.env.*` (D-664), and AgentDyn's package ships that file. Stock
AgentDojo and AutoDojo ship no such file, and the build's own probe runs its own script, so neither showed it.

The fix (class 0, `backends/shared`) reads RECORD's own path from RECORD. The digest is byte-identical in all three
registered environments (`793b6813…`, `c83122dd…`, `7fbe5758…`), so markers and T0's cross-check are unchanged. The
sandbox deny and `PROFILE_SHA256` are unchanged, as ruled. Tests: a unit test (`record_digest` with stats of `.env*`
denied) and `test_hello_and_catalogue_run_under_the_real_model_sandbox` (the real worker under the real-model profile,
macOS). `agentdyn-5353cf76` is rebuilt from the same lock once this lands.
