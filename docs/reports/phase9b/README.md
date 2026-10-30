# Phase 9b: live-capture harness gaps (2026-10-13)

Branch `phase-9b-harness` (own worktree, from origin/main `52c0974`). Closes the open test and robustness gaps of the
live harness from phases 8 and 9 (AGENTS.md "Phase-8 follow-ups" and "Phase-9 follow-ups"). **No model was called**:
every run uses `agentprov_backend.testing.ScriptedTransport`. **No network was used**: the AgentDojo and AutoDojo
backend environments were built offline from the local uv cache (`agentprov backends build`, the test fixtures'
default; `uv sync --offline` for the in-project harness environments). Decisions D-290 to D-293 were approved by the
user on 2026-10-13 (DECISIONS.md).

## 1. Items

| # | Item | Outcome | Decision |
|---|---|---|---|
| 1 | Poisoned-log path has no harness test | **Fixed and tested.** End to end through the real worker, a real redaction failure is quarantined and never reaches the corpus. The test also showed that the quarantine happened only by coincidence: AgentDojo's unredacted native temporary log held the secret. T0 now quarantines any session whose log carries the `capture.redact` error | D-290 |
| 2 | Preflight treats any 2xx as "roles accepted" | **Fixed.** `runner.roles_verdict` decides from the recorded reply body: accepted / refused / unconfirmed / unknown, with a reason. T0 refuses refused and unconfirmed (exit 4) | D-291 |
| 3 | Executor guard AST digest is CPython-3.12-specific | **Fixed.** Digest table keyed by interpreter; any other interpreter raises the typed `MirrorUnverifiable` | D-292 |
| 4a | Live manifests have `index_status: null` | **Confirmed and fixed** (the writer queues rows until a flush). First a campaign-side flush, retired once R-9b-3 fixed `ingest` at the root (`41d7a2f`); the tests stay | D-293 |
| 4b | A future `recompute` must take the cache origin from `raw/origins.jsonl` | **Confirmed, no change needed.** `recompute` refuses to re-map a live corpus (D-43, `corpus.derive.live_remap`, exit 5) and re-derives only the layers above the stored AER. The stored AER's cache origin is one that `raw/origins.jsonl` records for that object (tested) | none |
| 5 | AgentDyn and `banking_v2_*`/`travel_v2_*` live sessions | **Done.** Scripted `shopping`, `banking_v2_0` and `travel_v2_0` cells map through the AutoDojo backend (AER/SEM/PROV/validation ok). AgentDyn's clock use is shown by two runs (D.15 candidate, routed) | none |
| 6 | CI `backend-autodojo` does not run `test_run_live_autodojo.py` | **Applied** on the branch (user-allowed 2026-10-13; the patch is kept as `ci-backend-autodojo.patch`). The branch merges after deferrals part D | none |

## 2. Evidence

### Item 1 (poisoned log)
- `tests/integration/test_run_live_agentdojo.py::test_a_poisoned_capture_log_from_the_real_worker_never_reaches_the_corpus`
  (real AgentDojo worker). A test seam adds a sentinel to T2's environment. The scripted reply's tool-call argument keys
  are the sentinel and the redaction marker. The response blob is redacted, but the `tool.dispatch` event's keys would
  collide once redacted, so the scan fails (`cap.redact.failed`). The log ends `error{where: capture.redact}` plus
  `session.end{errored}`, has no `tool.dispatch` event and holds no sentinel. The session is quarantined, nothing is
  stored, and the sentinel appears in no stdout, stderr or corpus byte.
- Before D-290, the experiment showed the quarantine came from the literal scan hitting
  `raw/native-tmp/.../none.json` (AgentDojo's own unredacted log) and the parent's script file.
  `tests/integration/test_run_spawn.py::test_a_poisoned_capture_log_quarantines_the_session_and_never_reaches_the_corpus`
  (fake worker, new mode `poisoned`) covers a poisoned log whose siblings hold nothing T0 knows. That session would
  otherwise have been stored; it is now quarantined. Unit test of the untrusted-log check: `tests/cli/test_live_units.py`.
- A deeply nested tool argument is **not** a redaction failure: the capture model's own depth check
  (`CaptureWriteError`, "event nesting is too deep") refuses the event without poisoning the log. The session is then
  stored as an errored execution. This is correct and is not changed here.

### Item 2 (preflight)
- `backends/shared/tests/test_preflight_roles.py` (22 cases, no benchmark package), covering:
  - accepted: a structured call with the key, or the key in text;
  - refused: 400/422/500; a 2xx with an `error` object; a 2xx whose text or `refusal` names a role refusal;
  - unconfirmed (silently ignored roles): the tool called with another key, the user message answered, the tool named
    without the key, a model refusal;
  - no choices, `finish_reason: error`, a non-JSON body; no reply.
- `backends/agentdojo/tests/test_probe.py` runs these through `run_probe` and the recording transport. It also checks
  headers: `set-cookie`, `x-api-key`, `openai-organization` and `x-request-id` are dropped by name, and their values
  (plus a key sentinel) appear in no probe-session file.
- `tests/integration/test_run_live_agentdojo.py`: through the real worker, both a `2xx + error object` reply and an
  "ignored roles" reply exit 4 with the reason in the message.

### Item 3 (guard)
`backends/agentdojo/tests/test_executor_mirror.py`:
- On the running interpreter (CPython 3.12.14), the key is `cpython-3.12` and the recorded digest equals the installed
  method's.
- `cpython-3.13`, `cpython-3.14`, `pypy-3.12` and `cpython-3.11` raise `MirrorUnverifiable` (code
  `backend.mirror.interpreter`).

### Items 4 and 5
`tests/integration/test_run_live_autodojo.py`:
- The cache test now also checks that the ledger's `index_status` equals the row status, that the AER's cache origin
  is one of the object's origins in `raw/origins.jsonl`, that `recompute --stages aer` exits 5, and that
  `recompute --dry-run` passes.
- New tests: an AgentDyn `shopping` cell run twice, and `banking_v2_0` / `travel_v2_0` cells.
- `index_status` is also asserted in `test_run_spawn.py` and `test_run_live_agentdojo.py`.

### Test runs (local, M2 Max)
| Suite | Result |
|---|---|
| `backends/shared` + `capture` (Python 3.12, as CI) | 344 passed |
| `backends/agentdojo` (`backend_agentdojo and not old_package`) | 93 passed |
| `backends/autodojo` (`backend_autodojo`) | 63 passed |
| fixture `--check`, both backends | current |
| `tests/integration/test_run_live_agentdojo.py` | 7 passed |
| `tests/integration/test_run_live_autodojo.py` | 7 passed |
| `tests/integration/test_run_spawn.py` | 22 passed |

| full core `pytest` | 6,468 passed, 124 skipped, 5 xfailed (all pre-existing); after the rebase on `41d7a2f`: 6,632 passed, 124 skipped, 2 xfailed |

`ruff check .`, `mypy` and `tools/check_unicode.py` are clean.

## 3. Routed to the orchestrator (not this session's folders)

- **R-9b-1 (D.15 artefact candidate; `adapters/agentdojo/artefacts.toml`, regen-batch session).** AgentDyn's tool
  clients in the AutoDojo fork (`aa458794`) read the clock and `random` inside tool calls:
  - `shopping_client.py`: `random.choices` OTP l.150; `random.randint` order ids l.818; `date.today()` l.646 and l.798;
  - `github_client.py`: OTP l.119; `datetime.now()` in comments l.517;
  - `dynamic_banking_client.py`: OTP l.48;
  - `dynamic_email_client.py`: `datetime.now()` l.39 and l.70;
  - `cloud_drive_client.py`: l.41 and l.62.

  Some of these are in stock AgentDojo too (`email_client.py` l.95), but AgentDyn's OTP flows put random values into
  tool *results*. Effect: a re-run of the same cell never reproduces the environment state or OTP-bearing outputs.
  Evidence is the captured value only (two scripted `shopping` runs: identical `pass.start` state digests, different
  `pass.end` ones). Proposed entry:
  - id `agentdyn.art.nondeterministic_tools`, cause `upstream_benchmark`, handling class "recorded as observed" (no
    rule);
  - scope: sources `agentdyn` and `autodojo` (live), profiles `agentdyn`, `autodojo-live`;
  - `manuscript = true` (reproducibility caveat for AgentDyn cells);
  - the detector is the test above, or a census rule over tool names, at that session's choice.

  This moves the `adapters/agentdojo` code digest (manifests only), so it goes through `regen-batch.md`.
- **R-9b-2 (SEM labels for AgentDyn tools in live AutoDojo sessions; regen-batch session).** In a live AutoDojo session
  the AER says `task.benchmark = "agentdojo"`, `suite = "shopping"`. `agentdojo.suites@1` has no table for that pair,
  so every AgentDyn tool is labelled `unknown` (`agentdojo.unknown_tool@1`), as the phase-9 follow-up predicted (the
  `agentdyn` profile labels its suites `agentdyn`). This is a fail-closed label and validation passes, but taint and
  role facts are missing. A live-cell-to-AgentDyn-table mapping (keyed by the fork's identity, not the version string)
  is needed before any AgentDyn live campaign.
- **R-9b-3 (`adapters/runner/session.py`, deferrals session; done on origin/main `fda8cec`, the campaign workaround retired).** `LiveSessionPipeline.ingest` returns
  `SessionOutcome.status = None` for every stored execution: `corpus.has_execution` does not see queued rows. The
  campaign now works around it (D-293); the clean fix is for `ingest` to flush or to read the queued row.

## 4. Item 6: the CI step

`backend-autodojo` (dispatch only) gains one step after the core build test:
`uv run pytest tests/integration/test_run_live_autodojo.py` with `AGENTPROV_TEST_BUILD_NETWORK=1`. The test builds its
own environment into a temporary home, so a runner without the uv cache needs the network, as the rest of the job does.
The user allowed the edit on 2026-10-13 and it is committed on the branch; `ci-backend-autodojo.patch` keeps the diff.
Part D's diff (`deferrals-d`) touches only the `old-vs-new` job, so the two do not overlap. By the orchestrator's push
order, this branch merges after part D: after the rebase, `ci.yml` must hold both jobs' edits (part D's C2/C5 steps
included).
