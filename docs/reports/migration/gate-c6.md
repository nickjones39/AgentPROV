# Gate C6: old versus new live capture with a scripted client

Gate C6 (docs/architecture J.3.4, K.9.2) runs scripted AgentDojo cells through two harnesses. The **old side** is the
frozen baseline generator, `agentdojo-prov` 1.0.0 at `579a908`. The **new side** is the AgentPROV backend with the
`gateway_compat` element, which ports `_CompatLLM`. The gate compares the outputs. It is a port-fidelity diagnostic
(role `diagnostic`, AD-07), not a release gate. This file records the second local run, made after the findings of the
first run were fixed or registered. The machine-readable rows are in `C6.json`, which holds scenario ids, check names,
counts, XD ids and JSON Pointers only, with no scenario text.

**Verdict: pass (14 of 14 scenarios).**

- The wire requests are identical in all 14 scenarios: the request counts are equal and the decoded bodies are equal
  as JCS values per index. The `gateway_compat` port shows no fidelity defect.
- Every remaining difference is absorbed by exactly the XD entries its scenario declares, and none goes over its
  bound.
- Leaving out the registered members:
  - the six C6(a) v1 views are byte-equal to the old transcripts after the time mask;
  - the six C6(a) compat graphs are byte-equal after the mask, with no registered member removed;
  - the seven C6(b) projections with an old transcript are equal;
  - the 400 cell is compared by its deviations, because the baseline wrote no transcript for it.

## Run

| | |
|---|---|
| Date (UTC) | 2026-10-08 |
| AgentPROV commit | `fb30a59` (stream E branch, on main `897085a`) |
| Core interpreter | CPython 3.14.8; macOS 27.0.1 arm64, 12 cores |
| New side | CPython 3.12.14, `backends/agentdojo` env (`uv sync --locked`): agentdojo 0.1.35, openai 3.26.0 (httpx2), agentprov-backend 0.1.0, agentprov-capture 0.1.0 |
| Old side | CPython 3.12.14, `$AGENTPROV_HOME/baseline/venv-579a908`: agentdojo-prov 1.0.0, agentdojo 0.1.35, openai 3.25.0, httpx2 2.13.1, pydantic 2.13.5 |
| Baseline commit | `579a908354b93361efe0905ffb7623256aa96a06` (read-only; `git status --porcelain` empty before and after) |
| Network | none. Everything was installed from the uv cache with `--offline`; both sides ran with sockets blocked |

### How the baseline environment was built (J.1.6)

`tools/migration/build_baseline_env.py --offline` runs these steps:

1. `uv venv --python 3.12.14`.
2. `uv pip install --require-hashes --no-deps -r migration/baseline-requirements.txt`. That file has 101 pins and
   sha256 `f9201270…f13e`. It is `investigation/baseline/pip_freeze.txt` minus its `-e` line. The freeze's sha256,
   `0f566a95…`, is checked against the lock's `environment.pip_freeze_sha256`. The hashes come from
   `uv pip compile --no-deps --universal --generate-hashes`, which read the index metadata from the uv cache.
3. Build a wheel from `git archive 579a908 agentdojo_prov pyproject.toml README.md`, unpacked into a temporary
   directory outside the old repository, with `SOURCE_DATE_EPOCH` set to the commit time (1791252288). Two builds gave
   the same wheel, sha256 `3dcf0ed0…7b53`.
4. Install the wheel non-editable with `--no-deps`.

There is one deviation from R-49. The build backend (`setuptools>=68`, resolved from the cache to 84.0.0) is not pinned
by the freeze. It is recorded in the wheel's `WHEEL` file and in `AGENTPROV_BASELINE.json`. The lock's
`requirements_lock_sha256` and `baseline_wheel_sha256` are still `null`: the lock is frozen and is regenerated only
deliberately (open item).

### How it ran

Each step has a fixed command:

- **Producer** (backend project, markers `backend_agentdojo` + `old_package`): `backends/agentdojo/tests/test_c6_old_vs_new.py`.
  It writes, under `$AGENTPROV_C6_WORK/<scenario>/`:
  - the scenario bundle;
  - the new side's sealed capture session;
  - the outputs of `tools/migration/baseline_probe.py c6`, run under `$AGENTPROV_BASELINE_PYTHON` with `-I -B`, a
    scrubbed environment and the scenario directory as working directory.
- **Old side.** The probe calls `generate._run_one_benign` or `_run_one_injection`. Every baseline step runs as it
  did in v2.3 generation: the model shorthand builder, `make_instrumented_pipeline`, `_CompatLLM`, the `MODEL_NAMES`
  registration, and the transcript and graph writers. The responses are served at the wire level: an `httpx2.MockTransport`
  on the baseline's own SDK client serves exactly the bytes that the new side's `ScriptedTransport` serves
  (`render_response`). The baseline `_FakeClient` returned parsed objects and raised a generic `APIStatusError`, an
  artefact of that test harness (D.10.10 item 18). Serving the wire bytes avoids it. The renderer is a no-op.
- **New side.** `AgentDojoBackend.execute` runs with `gateway_compat`, the scripted transport and the baseline's
  pipeline name `<shorthand>/<model id>+prov`. Attacked cells use `attack_params.model_display_name_preset =
  "adprov-v2.3-title-case"`.
- **Comparer** (core, marker `old_package`): `tests/migration/test_c6_old_vs_new.py` calls
  `agentprov.migration.c6.compare_work`, which reads `migration/expected_differences.toml`.

## Scenarios and verdicts

All scenarios run on `banking/user_task_1` (benchmark v1.2.2). The response sequences come from the baseline's
`tests/test_attempts.py`. "Wire" gives the request counts (old = new), and in every row the bodies are equal. "Equal"
means equal after the time mask, with the registered members left out.

The XD entries are abbreviated:

| Abbreviation | Entry |
|---|---|
| D.7.3 | `XD-C6-D73-capture-verdict` |
| D.10.5 | `XD-C6-D105-benign-security` |
| C.15.3 | `XD-C6-C153-generator-meta` |
| F-02 | `XD-C6-F02-discarded-model-calls` |
| F-05 | `XD-C6-F05-failed-cell-kept` |
| F-13 | `XD-C6-F13-display-name-preset` |

| Scenario | Cat. | Wire | Compared | XD hits | Verdict |
|---|---|---|---|---|---|
| `single_pass` | a | 2 = 2 | v1 and graph equal | D.7.3, D.10.5, C.15.3 | pass |
| `no_usage` | a | 2 = 2 | v1 and graph equal | D.7.3, D.10.5, C.15.3 | pass |
| `partial_usage` | a | 2 = 2 | v1 and graph equal | D.7.3, D.10.5, C.15.3 | pass |
| `provider_fields` | a | 2 = 2 | v1 and graph equal | D.7.3, D.10.5, C.15.3 | pass |
| `reasoning_single_pass` | a | 2 = 2 | v1 and graph equal | D.7.3, D.10.5, C.15.3 | pass |
| `tool_errors` | a | 2 = 2 | v1 and graph equal | D.7.3, D.10.5, C.15.3 | pass |
| `rerun_two_passes` | b | 4 = 4 | projection equal | D.7.3, D.10.5 | pass |
| `rerun_env_change` | b | 4 = 4 | projection equal | D.7.3, D.10.5 | pass |
| `refusal_rerun` | b | 3 = 3 | projection equal | D.7.3, D.10.5 | pass |
| `malformed_args_resample` | b | 3 = 3 | projection equal | F-02 ×1, D.7.3, D.10.5 | pass |
| `upstream_failures_retried` | b | 4 = 4 | projection equal | F-02 ×2, D.7.3, D.10.5 | pass |
| `server_5xx_retried` | b | 6 = 6 | projection equal | F-02 ×4, D.7.3, D.10.5 | pass |
| `http_400_refused` | b | 1 = 1 | old wrote nothing | F-02 ×1, F-05 | pass |
| `injection_important_instructions` | b | 2 = 2 | projection equal (no mask needed) | F-13, D.7.3 | pass |

XD totals: D.7.3 13, D.10.5 12, C.15.3 6, F-02 8, F-05 1, F-13 1.

The D.7.3 detector also checks that the two records agree. Old `meta.capture.complete` is true and the new seal's
accounting is `consistent`, and the pass counts equal the number of attempt scopes. They agree in all 13 scenarios
with a transcript.

## Findings of the first run and their resolution

The first run, on commit `69c87f0`, failed 12 of 14 scenarios on six differences outside the port.

| # | Finding | Resolution |
|---|---|---|
| 1 | Benign `security`: null (old) versus `true` with origin `harness_default` (new) | Registered as `XD-C6-D105-benign-security`. It is a deliberate D5 deviation: the stock `run_task_without_injection_tasks` returns a constant `true` (D.10.5, D.6.7). The detector is narrow: a benign cell, old null, new `true` with origin `harness_default` |
| 2 | Versions rendered null because the identity sat on a second actor `bench0` | Mapper fix: the identity merges into the declared `bench` actor (D.10.4a item 28) |
| 3 | Reasoning and refusal text that only the wire carries were not mapped | Mapper fix: the text becomes parts of the generated message, `O:provider`, with `src` in the response blob. These parts are left out of the live-versus-native projection (item 29). The projection lists tool-call parts last (item 31), and the view renders wire reasoning in the baseline's log order (item 32) |
| 4 | `tool_execution.args` lost member order and integral floats | Mapper fix: the lexical form comes from the dump's linked call (`ext.lex`), and the value is unchanged (item 30) |
| 5 | The v1 view rendered replies of discarded calls | View fix: these messages are excluded (C.13.7, D.10.4). A1, A2 and B are unchanged on the 19 golden pairs |
| 6 | `meta.model` / `meta.model_config` absent from the live view | Registered as `XD-C6-C153-generator-meta`. No live rule was added, because not every value is an `O` fact of a live AER: no shorthand is recorded; the configured params are `{}` and the element's default temperature 0.0 is not recorded; `provider_default` is a generator label. The detector is narrow: the old values are present and the view renders neither |

A confirmed detector stands for its own difference keys only:
- D.10.5: `v1:/meta/security`, and the security judgement's value in the projection;
- C.15.3: `v1:/meta/model` and `v1:/meta/model_config`.

Any other difference at any pointer stays unlisted and fails the gate.

The mapper fix of item 29 adds the rule `agentdojo.capture_reply_wire_fields@1`. That changes the `agentdojo`
catalogue digest, so the golden PROV and gate-D digests were regenerated with `AGENTPROV_REGEN_PROV_DIGESTS=1` and
`AGENTPROV_REGEN_GATE_D_DIGESTS=1`. Only `prov` digests changed (19 in PROV, 28 in gate D); no SEM or AER digest changed.

## Resolutions recorded with the gate

These are recorded in J.3.4, under "Implementation resolutions (phase 8, gate C6)", items 1 to 9.

- The register sits at the repository root, `migration/expected_differences.toml`.
- **D.7.3 in C6(a).** C6(a) compares the views without `meta.n_attempts` and `meta.capture`, which hit the D.7.3
  entry exactly once.
- **F-02.** F-02 counts error replies as well as discarded ones.
- **F-05.** F-05 is observed when the baseline wrote no pair and the new session is sealed `errored`.
- **Display name.** The display-name preset `adprov-v2.3-title-case` replaces the `MODEL_NAMES` mutation (F-13).

## Open items

- The lock's `requirements_lock_sha256` and `baseline_wheel_sha256` stay null. Filling them needs a deliberate
  regeneration of the frozen lock.
- The `old-vs-new` CI job assumes that commit `579a908` is fetchable from the public `nickjones39/agentdojo-prov`.
  This has not been verified in CI.
- The lexical form of `tool_execution.args` is not restored when the stock `literal_eval` changed the dump. A source
  for that case would be the raw `arguments` string in the response blob.
- C2, C3 and C5 stay deferred (D-18).
