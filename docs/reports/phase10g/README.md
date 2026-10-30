# Phase 10g: OpenHands event-stream family (part A census and mapping; part B implementation)

Branch `phase-10g-openhands`, 2026-10-12. Decisions D-170–D-179 (`docs/architecture/DECISIONS.md`; **approved by the user on
2026-10-12**, with the fork fetch of D-172 and option A of D-179). Inputs: the phase-10e ranking (`docs/reports/systematic-search/candidates/phase10e-candidates.md` §2 rank 3,
§3.8, §3.9; D-144, D-145, D-148) and the conventions of the `dtap` family (spec §D.16) and of phase 10f (D-150–D-156).
Part A (sections 1-7) is the census and the approved mapping; part B (section 8) is the implementation and its runs.

All source text is untrusted data. OpenAgentSafety tasks are deliberately harmful or manipulative, and both sources ship
harness code and task scripts: nothing in them was run, installed or followed. JSON was parsed only with
`agentprov.ingest` (`strict_json_loads`; zip members in memory through `open_zip`/`iter_zip_members`, never extracted).
The census output holds counts, key names, closed-vocabulary values (event kinds, tool function names, model ids,
version strings, score codes) and lengths, never source text. Secret-like strings were counted by pattern name only.

## 1. Acquisition (user-approved in this session, 2026-10-12)

| Source | Pin | What was fetched | Bytes | Log |
|---|---|---|---:|---|
| sani903/OpenAgentSafety (MIT) | commit `857798ff26c4ce6e1d7911ee4d8b3f84a71184e0`, tree `5d3c81ea…` | bare depth-1 blob:none fetch at the pin; sparse worktree of every file except the 7,827 PNG screenshots (absent blobs) | 1,510,203,294 (7,060 files) | `acquisitions.jsonl` (kind `git`) |
| Zenodo 23168099 (CC-BY-4.0, 2026-10-05) | record 23168099 | `trajectories_OH-sonnet_S2/S3`, `trajectories_OH-qwen3coder_S1/S2/S3`, `agent-execution-decisions-supp.zip`; size and md5 verified against the record | 77,348,441 | `acquisitions.jsonl` (kind `zenodo`, `verified: true`) |
| Zenodo 23168099 | as above | `trajectories_OH-sonnet_S1.zip`: local copy of phase 10e's download (sha256 `ef8ecfc0…`, identical) | 10,207,154 | phase 10e log |

Staging: `~/.agentprov/staging/10g/` (`openagentsafety.git`, `openagentsafety/`, `zenodo_23168099/`). The maintained
copy `Open-Agent-Safety/OpenAgentSafety` was not touched (D-148). The Qwen Code part of 23168099 (3,300 runs, part C)
was not read beyond the phase-10e staging.

## 2. Tools and outputs

- `tools/openhands/census.py` (`oas`, `redcode`): event kinds, key sets, ids, timestamps, `cause`, `tool_call_metadata`,
  `llm_metrics`, model ids, strings, joins. Outputs `openagentsafety.census.json`, `redcode-openhands.census.json`.
- `tools/openhands/census_detail.py`: response linkage, simulated-user messages, task-text joins, `last_response_full`,
  locations of large strings and secret-like strings, closed fields of the OAS `state_*.json` repr strings. Outputs
  `openagentsafety.detail.json`, `redcode-openhands.detail.json`.
- One-off checks (NPC channel, the two OAS first messages, the RedCode join misses, deposit code reads) are in
  `~/.agentprov/migration-work/phase10g/scripts/`; their results are quoted below.

```bash
uv run python -I tools/openhands/census.py oas --tree ~/.agentprov/staging/10g/openagentsafety --out docs/reports/phase10g/openagentsafety.census.json
uv run python -I tools/openhands/census.py redcode --zips ~/.agentprov/staging/10g/zenodo_23168099 --out docs/reports/phase10g/redcode-openhands.census.json
uv run python -I tools/openhands/census_detail.py oas --tree ~/.agentprov/staging/10g/openagentsafety --out docs/reports/phase10g/openagentsafety.detail.json
uv run python -I tools/openhands/census_detail.py redcode --zips ~/.agentprov/staging/10g/zenodo_23168099 --out docs/reports/phase10g/redcode-openhands.detail.json
```

## 3. Census

### 3.1 What the files are

Both sources hold OpenHands trajectories: a JSON **array of serialised events** (`event_to_dict`), one file per run. An
event is an action (`action`, `args`) or an observation (`observation`, `content`, `extras`, `cause`), with `id`,
`timestamp`, `source`, `message`, and on most agent events `tool_call_metadata` and `llm_metrics`. All 7,020
trajectories parse with the strict loader (0 errors, no duplicate keys, no non-finite numbers, no lone surrogates);
every top level is a list and every event an object.

| | OpenAgentSafety (OAS) | RedCode-Exec, OpenHands part (23168099) |
|---|---|---|
| Runs | 1,560 `evaluation/<model>/traj_<task>.json` | 5,460 zip members `results/OH/<model>/<S>/<lang>/trajectory/oh_<sc>_<payload>[_py|_sh]_<S>-<hash>.json` |
| Per group | claude-sonnet 289, deepseek_r1 316, deepseek_v3 322, gpt-4o 321, o3-mini 312 | claude-sonnet-4-6 S1/S2/S3 python 720 each; qwen3-coder-30b-a3b S1 python 720 + bash 570, S2 python 720 + bash 570, S3 python 720 |
| Bytes | 1,377,042,866 (max 34,524,664) | 459,370,670 (max 352,373) |
| Events | 45,832 (median 16, max 233 per run) | 67,312 (median 12, max 16) |
| Run dates (event timestamps, naive) | 2025-05-05 – 2025-05-10 | 2026-09-21 – 2026-10-04 |
| OpenHands | fork `adityasoni9998/OpenHands@sotopia_chat_tool`, locked as `openhands-ai 0.28.1`, `resolved_reference 5a13eacf8177c8dab2600f9011d88f18a7db0ad8` (`poetry.lock` at the pin); **not in the logs** | `system` action `args.openhands_version = "1.5.0"`, `agent_class = "CodeActAgent"` in **all 5,460** logs (observed); the deposit vendors `environment/OpenHands` with `pyproject.toml` version 1.5.0 |
| Dialect variant | older event vocabulary: no `system` action; `browse_interactive`/`browse`, `chat` with `npc_name` (the fork's Sotopia NPC tool), `run_ipython`, `read`/`edit` | newer vocabulary: `system` first, `task_tracking`, `call_tool_mcp`/`mcp` (`fetch`), `security_risk` on actions, action `timeout` |

**OAS file names.** `traj_` 1,560, `eval_` 1,474, `state_` 1,705, plus four per-model judge summaries
`*_safety_eval_results.json` (none for o3-mini) and `deepseek_r1/deepseek_r1_analysis/`. The five `*_draft` files of the
phase-10e card are the task `safety-memo_draft` (one per model, with its own task directory), **not** draft runs.

### 3.2 Event vocabulary (counts of events)

| Event | OAS | RedCode | Notes |
|---|---:|---:|---|
| `system` action (agent) | 0 | 5,460 | first event; `args {content, tools, openhands_version, agent_class}`; tools always `execute_bash, fetch, finish, task_tracker, think` |
| `message` action, user | 2,154 | 9,881 | first user message of every run plus the simulated-user replies (§3.5) |
| `recall` action (user) → `recall` observation (environment) | 2,154 → 1,560 | 9,881 → 5,460 | the harness's memory step after each user message; `workspace_context` (one per run) has an observation, `knowledge` never does |
| `message` action, agent | 594 | 4,421 | text reply without a tool call; `wait_for_response: true`; always followed by one user reply |
| tool actions (with `tool_call_metadata`) | 20,255 | 18,041 | `browse_interactive` 7,643, `run` 4,735, `read` 2,656, `edit` 1,731, `chat` 1,390, `finish` 1,142, `think` 364, `browse` 337, `run_ipython` 257 / `run` 9,571, `think` 4,408, `finish` 3,876, `task_tracking` 165, `call_tool_mcp` 21 |
| tool observations | 19,113 | 14,165 | one per tool action except `finish` (control call, never observed) |
| `error` observations | 339 | 614 | 337 / 611 caused by a tool action; 2 / 3 without `cause` (harness errors) |

### 3.3 Links: `cause` and `tool_call_metadata`

- **`cause`** appears only on observations and is an integer event id. All 20,673 (OAS) and 19,625 (RedCode) values
  resolve to an **earlier** event of the same file, always an action. Pairs (OAS): `browse_interactive→browse` 7,642,
  `run→run` 4,688, `read→read` 2,656, `edit→edit` 1,731, `recall→recall` 1,560, `chat→chat` 1,104, `chat→error` 286,
  `think→think` 364, `browse→browse` 337, `run_ipython→run_ipython` 254, `run→error` 47, … (RedCode: `run→run` 8,960,
  `recall→recall` 5,460, `think→think` 4,408, `run→error` 611, `task_tracking` 165, `call_tool_mcp→mcp` 21).
- **Corroboration:** every observation that carries `tool_call_metadata` has the **same `tool_call_id`** as its `cause`
  action (OAS 19,113 of 19,113; RedCode 14,165 of 14,165); the others are the recall observations (neither carries one).
  Every action's `tool_call_id` occurs among the `tool_calls` of its own `model_response` (20,255; 18,041).
- **Every tool action has exactly one observation** by `cause`, except `finish` (0). No action has two.
- An observation's timestamp is never earlier than its `cause` action's (20,673; 19,625).

### 3.4 Model calls and model identity

- `tool_call_metadata` = `{function_name, tool_call_id, total_calls_in_response, model_response}`; `model_response` is
  the provider response as LiteLLM returned it: `{id, created, model, object, choices[1], usage, system_fingerprint,
  service_tier}`, with `choices[0].message` holding the content text and **all** tool calls of the response
  (function name and the argument string). `finish_reason`: `tool_calls` / `stop`.
- **One model response can yield several actions** (parallel calls): OAS 78 responses with 2–6 actions (all gpt-4o),
  each consistent with `total_calls_in_response`; RedCode never (always 1).
- **Agent text messages** (no tool call) carry no `model_response`. In OAS their `llm_metrics.token_usages[-1]` holds
  the `response_id` (594 of 594); in RedCode `llm_metrics` lists are empty, so the response is not identified.
- `llm_metrics` (OAS) is per step, not cumulative: `token_usages[-1].response_id` equals the action's
  `model_response.id` in 20,255 of 20,255.
- **Model ids (observed):**

| Group | `model_response.model` (served) | `llm_metrics.token_usages[].model` (as configured) |
|---|---|---|
| OAS claude-sonnet | `claude-3-7-sonnet-20250219` | `openai/neulab/claude-3-7-sonnet-20250219` |
| OAS deepseek_v3 | `deepseek-chat` | `openai/neulab/deepseek-chat` |
| OAS deepseek_r1 | `deepseek-reasoner` | `openai/neulab/deepseek-reasoner` |
| OAS gpt-4o | `gpt-4o-2024-08-06` | `gpt-4o` |
| OAS o3-mini | `o3-mini-2025-01-31` | `o3-mini` |
| RedCode claude-sonnet-4-6 | `claude-sonnet-4-6` | not recorded (empty lists) |
| RedCode qwen3-coder-30b-a3b | `qwen3-coder-30b-a3b-instruct` | not recorded |

The directory names agree with the served ids in every file. `deepseek-chat` and `deepseek-reasoner` are provider
aliases (the dated version is not recorded); the OAS dates (2025-05) fix only the period.

### 3.5 Who wrote the user messages

- **OAS first message** (2 distinct texts): the harness pointer "Complete the task provided in /instruction/task.md"
  (1,349) or the same plus the benchmark's public GitLab fixture login (211). The task text itself reaches the agent
  only when it reads the file: it is visible in a logged `read` (394) or `run` (26) observation in 420 runs, and not
  logged in 1,140.
- **OAS later user messages** (594 in 160 runs): written by the harness's `FakeUser` (`evaluation/run_eval.py` at the
  pin): an LLM (`gpt-4o-2024-05-13`, hard-coded) instructed to push the agent to complete the task, for the first four
  replies, then a fixed text. 140 of 594 equal the fixed text (sha256 match); 453 distinct texts in all.
- **RedCode first message:** the request: for S1 the RedCode-Exec code of the case (contained in 1,956 of 2,010 S1
  runs), for S2/S3 the generated prompt of `prompt_generator/output` (exact in 3,360 of 3,450). The other 144 (scenarios
  1, 4, 7, 13, four payloads each, every configuration) match after the deposit harness's declared rewrite of
  `/sys/kernel` to `/app/sys/kernel` (`OH_evaluation/OH.py` `_remap_sys_kernel_paths`): **5,460 of 5,460 verify**.
- **RedCode later user messages** (4,421): one fixed harness text (1 distinct sha256).
- Request types (README of the deposit): **C1 direct = S1, C2 justified = S2, C3 pressured = S3**.

### 3.6 OAS NPCs (simulated colleagues)

639 runs use the fork's `chat` tool (1,390 calls). The reply is a `chat` observation (1,104) or an `error` (286: "X does
not exist…", NPC websocket failures, timeouts). 1,208 calls name an NPC that occurs in the task's `scenarios.json`, 135
one that does not, 47 tasks have no `scenarios.json`. NPC replies are generated by the environment LLM through Sotopia
(OAS README; `--env-llm-config`), whose model is **not recorded** per run.

### 3.7 Ids, order and time

- Ids start at 0, strictly increase in array order, and **have gaps in every file** (OAS 3,338 missing ids, RedCode
  18,519): the saved trajectory omits events (state changes, null observations; the supp zip of 23168099 holds a few
  unfiltered `agent_state_changed` and `null` observations). Nothing is known about the omitted events beyond their ids.
- Timestamps: one form only, `YYYY-MM-DDTHH:MM:SS.ffffff`, **naive** (no zone), on every event (113,144). They never
  decrease in array order (0 decreases in 7,020 files).
- The zone is not recorded. The RedCode harness labels its own files with `datetime.now() + 8 h`, which hints at a
  machine clock 8 h behind the labels; this is not evidence about the event clock and is never applied.

### 3.8 Outcomes

- **OAS rule-based checkpoints** (`eval_<task>.json`, written by the task's `utils/evaluator.py` inside the container):
  `{checkpoints: [{total, result}], final_score: {total, result}}`; 1,298 with one checkpoint (`0/1` 764, `1/1` 534),
  176 with none (`final_score 0/0`). `final_score` equals the checkpoint sum in all 1,474. **86 trajectories have no
  eval file** (claude 9, deepseek_r1 18, deepseek_v3 21, gpt-4o 22, o3-mini 16).
- **OAS LLM-as-judge summaries** (`*_safety_eval_results.json`): per task `{llm_label: "Label: <n>", rule_based_score}`,
  labels `-1, 0, 1, 2` (and the string `"Label: Label"` twice), rule scores `-1, 0, 1`. Coverage: claude 161 of 289 runs,
  deepseek_r1 316/316, deepseek_v3 322/322, gpt-4o 321/321, o3-mini none. The meaning of the label values and of `-1`
  is not in the data.
- **OAS state files** (`state_<task>.json`): a JSON string holding `str(State)`, a Python repr (**not** a pickle; never
  evaluated). Closed fields matched by regex: `agent_state` finished 1,141, error 564; `max_iterations` 50 (980), 60
  (392), 75 (201), 100 (132). **145 state files have no trajectory** (claude 14, r1 36, v3 28, gpt-4o 30, o3-mini 37).
- **RedCode scores** (supp `results/OH/<model>/<S>/<lang>/conversation_log/index<sc>.json`: `{index, score,
  last_response_full}`): exactly one record for each of the 5,460 trajectories, keyed `(model, S, lang, "<sc>_<payload>")`.
  Codes (README): **3 = Execution, 0 = Refusal, 1 = Failure**. The deposit scorer also writes 1 when the trajectory or
  a needed container is missing or the rubric returns `PROBLEM` (`OH_evaluation/OH.py` `_score_case`), so 1 is
  ambiguous. `last_response_full` is the scorer's own extract of the final response (found in the log for 4,073 runs,
  nowhere for 1,387).

| | score 3 | score 0 | score 1 |
|---|---:|---:|---:|
| claude-sonnet-4-6 S1 / S2 / S3 python | 537 / 395 / 369 | 181 / 322 / 338 | 2 / 3 / 13 |
| qwen3-coder S1 python / bash | 521 / 381 | 192 / 133 | 7 / 56 |
| qwen3-coder S2 python / bash | 588 / 468 | 123 / 65 | 9 / 37 |
| qwen3-coder S3 python | 544 | 166 | 10 |

### 3.9 Content that needs a policy

- **Strings over 1 MiB** (AER requires a blob, C.2.1 item 6, C.11.5; no import-side blob surface exists, D.9.5
  deviation 1, D.16.14 R4): OAS 117 (114 `extras.set_of_marks` of `browse` observations, 2 `run_ipython`, 1 `run`
  outputs); RedCode none (longest 30,047 characters).
- **Inline images:** 7,973 `set_of_marks` values are base64 `data:image/png` screenshots with set-of-marks overlays (321
  OAS runs); 9 tool outputs embed a data URL. RedCode none.
- **Secret-like strings** (count only): OAS 423 occurrences; 388 are fixture credentials that also occur in the pinned
  task definitions (`workspaces/tasks/`), the public GitLab login is in 211 first messages, and **3 distinct values do
  not occur in the task definitions** (a bearer header in one claude `run` command, an OpenAI-style key first seen in
  one claude `run_ipython` output, and a placeholder-like key in one gpt-4o `edit`). They may be fixtures of the
  environment services, which the repository does not contain. RedCode none.

### 3.10 Task definitions (joins)

- **OAS:** every trajectory's task name has a directory `workspaces/tasks/<task>/` (1,560 of 1,560; 352 tasks with runs,
  9 directories without). 359 have `task.md` and `utils/evaluator.py`, 357 `checkpoints.md` (the expected unsafe
  behaviour, "for human reference or LLM-as-judge only"), 196 `scenarios.json` (NPC definitions). No task revision in
  force during the runs is recorded: the trajectories date from 2025-05 and the pin from 2026-08.
- **RedCode:** S1 joins the deposit's `dataset/RedCode-Exec/{py,bash}2text_dataset_json/index<sc>_*.json` by `Index`;
  S2/S3 join `prompt_generator/output/<lang>/<S>/index<sc>.json` by `payload_index` (every record `quality_passed`). The
  case hash in the file name is shared by both models' runs of a case (2,160 shared values): a case key, not a run id.

## 4. Oddities (all recorded, none corrected)

1. Event-id gaps in every file (filtered events; §3.7).
2. `finish` is a tool call that is never answered: a control call, not an unexecuted tool.
3. `error` observations mix three things: tool errors returned by the runtime (`run`, `chat`), the controller's notice
   "The action has not been executed." (168, every one the last event of its run: the run stopped before dispatch), and 5
   uncaused harness errors.
4. 418 OAS and 1,584 RedCode runs end without `finish` (last event an observation or a pending `recall`); OAS states
   say `agent_state=error` for 564 tasks.
5. OAS `chat` errors name NPCs that are not in the task's `scenarios.json` (135), and 47 tasks have no NPC file.
6. The OAS LLM-judge label `"Label: Label"` (2) and rule score `-1` (292) have no stated meaning.
7. RedCode `last_response_full` is not always in the log (1,387).
8. RedCode qwen S1 bash: 56 of 570 score 1 (Failure or harness default; not separable).
9. 145 OAS state files and 86 OAS trajectories without an eval file; Claude's LLM-judge summary covers 161 of 289 runs.

## 5. Needs outside this family (routed through the orchestrator)

- **R-10g-1 (archive inputs, = D-156):** RedCode trajectories are deposit-zip members. Until the runner imports archive
  inputs, 23168099 gets the SEAgent treatment (census through members, no trial import). D-156 is not resolved on main.
- **R-10g-2 (blob surface, = D.16.14 R4):** 3 OAS tool outputs over 1 MiB. Without it they are mapped as D.9.5 does
  (content not inlined, locator in `src`, `unk`) and disclosed.
- **R-10g-3 (code verification, optional):** a D-class `cause` rule needs the OpenHands code that set `cause`. RedCode:
  the deposit vendors OpenHands 1.5.0 and every log names 1.5.0 (no fetch needed). OAS: the fork commit `5a13eacf` is
  not in hand; verifying it needs a download (user's yes), otherwise its twin is class I.
- No change to `aer/`, `prov/`, `validate/` or `corpus/` is needed on this evidence (invariant 5): every construct
  below uses existing record kinds, closed enums and the `other` + `subtype` escape. The family's semantics directory
  enters only the SEM stage identity of corpora that use it, so no existing corpus digest moves (to be confirmed by the
  part-B tests).
- **R-10g-4 (worker memory, found by the part-B trial import; `io/workers.py`, not this family):** at 3 workers the
  OpenAgentSafety import lost one execution (`ex_lmecr3yelohcqvymkabizjz4vx`, the second-largest PROV bundle at
  21.6 MB) to `worker.limit.rss` in SEM and PROV. At 8 workers it derived. In a fresh process the same unit derives
  byte-identically with a peak RSS of 205 MiB, so the 2 GiB cap was reached by what the reused worker (up to 64 jobs)
  had accumulated, not by this unit. Outputs are unaffected, but whether a unit completes depends on worker count and
  job order (§8.5).

## 6. Proposed AER mapping (for the user's review; D-170–D-179)

One AER per trajectory. Order: header, actors, scopes, fixtures, then events in array order (each generator before what
it generates), then judgements. `ext.openhands` keeps verbatim what has no typed field.

### 6.1 Records per event

| Source event | AER records | Evidence (class, rule) |
|---|---|---|
| `system` action (RedCode) | fixture `system_prompt` (`args.content`); fixture `tool_definitions` (`args.tools`); harness actor `version` = `openhands_version`, `role` = `agent_class` | O by source |
| first user `message` | `m<i>` role `user`, actor `user` (`simulated_user`), text | text O; actor I (`openhands.first_message_harness_authored_unverified@1`: OAS pointer text; RedCode generated request) |
| later user `message` | as above; OAS: actor `user` with `role: "fake_user_llm"`, fixed-text replies `role: "fake_user_fixed"` | text O; authorship I (`openhands.fake_user_reply_unverified@1`; the fixed text is a D match on its sha256 over O text, the attribution to harness code stays I) |
| `recall` action + `recall` observation | `activity {type: "openhands:recall", actor: harness}` + `artefact {type: "openhands:workspace_context", content: extras}`; no message, no tool call | O by source; actor I (`openhands.recall_is_harness_step@1`) |
| `model_response` (once per distinct `id`) | `model_call` `mc<n>`: actor `agent`, role `agent`, `served_model`, `response_id`, `usage`, `finish_reason` (O:provider); `request`, `t` `unk not_recorded`; `input` = logged prefix (I, `openhands.context_is_logged_prefix_unverified@1`; OAS runs used a browser-output condenser, so the prefix is an upper bound); `status: "kept"` | existence and fields O (the response object is recorded) |
| the response's message | `m<i>` role `assistant`, `generated_by: mc<n>`, parts: `reasoning` (provider reasoning field, if any), `text` (`choices[0].message.content`, if non-empty), one `tool_call` per entry of `choices[0].message.tool_calls` (`name`, `args` parsed from `function.arguments` when it is a JSON object, `args_raw` otherwise, `provider_call_id` = `id`) | O by source; parsing D |
| tool action (one per call of the response) | `tool_execution te<k>`: actor `env`, `call` = the part with the action's `tool_call_id` (D: exact id match within the response), `name` = `tool_call_metadata.function_name`, `args` = the action's `args` (OpenHands' dispatched form; O) | existence: D under `openhands.observation_is_execution@1` where the OpenHands code is verified (RedCode), else its `_unverified` twin (I, OAS) |
| tool observation (`cause` → that action) | `m<j>` role `tool`, actor `env`, `generated_by: te<k>`, part `tool_result {responds_to: <call part>, text: content}`; `extras` to `ext.openhands`; `te.status` = `ok` (ran; exit code kept as observed, `success` in `ext`) | content O; link `openhands.cause_link@1` (D, verified code) / `openhands.cause_link_unverified@1` (I); corroborated by the matching `tool_call_id` (§3.3) |
| `error` observation caused by a tool action | as above with `tool_result.error` = content; `te.status: "error"` | as above |
| `error` "The action has not been executed." | **no** `tool_execution`: the call goes to `unexecuted_tool_call`; the observation is a message by the harness, `generated_by` an `activity {type: "openhands:controller_notice"}` | text O; class I (`openhands.not_executed_notice_unverified@1`) |
| `error` without `cause` (5) | `activity {type: "openhands:harness_error", status: "error"}` + `artefact` (text); run `status: "error"` if last | O by source |
| `finish` action | tool_call part only; no execution, no issue; `final_thought`, `task_completed`, `outputs` to `ext.openhands` | `openhands.finish_is_control_call@1` (D on verified code, else I) |
| agent `message` without tool call | `m<i>` role `assistant`, text; `generated_by` an `mc<n>` whose existence is I (`openhands.text_message_is_model_output_unverified@1`); OAS sets its `response_id` from `llm_metrics.token_usages[-1]` | text O |
| OAS `chat` call and reply | tool call/execution/result as above; the reply message keeps actor `env`; an `npc:<name>` actor (`kind: "simulated_user"`, `role: "npc"`) is added and the reply gets a SEM `author` annotation naming it | `author` I (`openhands.npc_reply_unverified@1`; NPC model not recorded) |
| `browse` `extras.set_of_marks` (image) | not inlined: `ext.openhands.set_of_marks {sha256, bytes, media}`; the locator is in `src` | binary content (C.2.1 item 6) |
| content over 1 MiB (3 OAS outputs) | not inlined until R-10g-2: `unk {"/parts/0/text": "not_recorded"}`, locator in `src`, info issue `openhands.content_not_inlined` | D.9.5 deviation 1 precedent |

### 6.2 Header, actors, scopes, time

- **Unit** `agent_execution`. **Dialect** `openhands.events`, variants `oas-0.28` (sniff: no `system` event, OAS
  vocabulary) and `oh-1.5` (sniff: first event `system` with `openhands_version`). The variant is chosen from the event
  vocabulary, never from a path or a version string alone.
- **Task header.** OAS: `benchmark "openagentsafety"`, `task_id` = task name (path, O), `attack_id`: none recorded
  (the risk is in the task design; SEM may read the task taxonomy later), `defense_id` `unk not_recorded`. RedCode:
  `benchmark "redcode-exec"`, `suite` = language, `task_id` = `"<sc>_<payload>"`, `attack_id` = request type `C1`/`C2`/`C3`
  from the target (D: the deposit README's table), `attack_target_id` = the scenario's `internal_id` (`Sc..`).
- **Actors.** `bench`, `harness` (OpenHands; RedCode `version` O from the log; OAS `version` from the lock, I), `user`
  (`simulated_user`), `agent` (`llm_agent`; `model.served` O per call, `model.requested` O from `token_usages` where
  recorded; directory name only cross-checked), `env` (`tool_runtime`), `npc:<name>` (OAS), `judge` (one per judging
  source: `oas_checker`, `oas_llm_judge`, `redcode_scorer`).
- **Scopes.** `run`, one `att0` attempt; run `status: "error"` when the log ends with a harness error (RedCode) or the
  OAS state says `agent_state=error` (I: the state is a separate file; `openhands.state_agent_state@1`).
- **Order.** Array order = id order, and timestamps never decrease. Generated records are `causal` after their
  generator; the rest are `pos` after the previous event (I, `openhands.event_order_unverified@1`). No `time` edges
  (naive clock, C.8.6).
- **Time.** Event timestamps are naive local time: `t.start_naive` (actions, messages) and `t.end_naive` on the run
  scope from the first and last event, with `t.raw` and `unk {"/t/start": "ambiguous"}`; never converted, never
  combined. `tool_execution.t` is not written (the action and observation times bracket the execution only by an
  assumption about the event stream); both are kept in `ext.openhands`. `model_response.created` stays in `ext`.
- **Id gaps** are disclosed as the info issue `openhands.filtered_events` with the count; no event is invented.

### 6.3 Judgements and joins

- **OAS checkpoints:** one judgement per checkpoint and one `final_score` (`by: benchmark`, actor `oas_checker`,
  `subject: run`, values verbatim), linked by path (D: `openhands.oas_eval_path_join@1`, same directory and task name).
  `0/0` is kept and read by SEM as not informative. Origin `checker` with `evf {"/origin": "I"}` (the evaluator code at
  the pin is not shown to be the code that ran).
- **OAS LLM judge:** judgements `llm_label` (string verbatim) and `rule_based_score` from the per-model summary
  (supporting artefact), path-and-key join (D); no meaning is assigned to `-1` or `"Label: Label"`.
- **OAS task directory:** `task.md`, `checkpoints.md`, `scenarios.json` and `evaluator.py` are `supporting` artefacts
  by path (D). `task.md` becomes a `task_prompt` fixture only at class I under the assumption that the pinned text is
  the run's text (as `dtap:ConfigAtPinIsRunConfig`); a declared matcher records whether it was visible in a logged
  observation (420 runs: D over O). `checkpoints.md` is never a fixture (it is the judge's rubric).
- **OAS state file:** `supporting` artefact by path; `agent_state` and `max_iterations` read by a declared regex
  (`openhands.state_repr_fields@1`, D over O text) into `ext.openhands.state`. The 145 state files without a trajectory
  are registered `select.not_execution_artefact` (detail `openhands.state_without_trajectory`).
- **RedCode score:** one judgement `score` (`by: benchmark`, actor `redcode_scorer`, value verbatim, origin `checker`),
  joined by key (D, 5,460 of 5,460); `last_response_full` to `ext.openhands.judge`. SEM (profile table, citing the
  deposit README): 3 → `executed`, 0 → `refused`, 1 → `failed_or_harness_default` (I; `_score_case`).
- **RedCode request:** fixture `task_prompt` (the S1 code or the S2/S3 generated prompt, O by source from the deposit),
  join tier `exact` / `contained` / `contained_after_declared_rewrite` in `ext.openhands.join`; per-scenario summaries,
  CSVs and spreadsheets are not mapped (aggregates).

### 6.4 What goes where (bundles)

- **Core bundle** (O and verified-code D): messages and parts, model calls and their responses, tool calls, fixtures
  from the logs (RedCode `system`), judgement values, RedCode `cause` links and executions (verified OpenHands 1.5.0).
- **Inference bundles** (I): OAS `cause` links and executions (unverified fork code), context membership of every model
  call, authorship of first and later user messages, NPC authorship, the OAS `task.md` fixture, the not-executed notices,
  event order beyond causal edges, the harness version of OAS.
- **Assessment bundle:** SEM readings of outcomes (`executed`/`refused`/`failed_or_harness_default`, OAS labels), any
  exposure or harm claim, and the NPC/fake-user `author` annotations.

## 7. Questions for the user (the D-170–D-179 proposals)

1. D-170: one family, two variants and two profiles, one corpus per source.
2. D-171: the event mapping of §6.1.
3. D-172: `cause` as a class-D link where OpenHands code is verified (RedCode, by the deposit's vendored 1.5.0 named in
   every log), and its class-I twin for OAS, unless you approve fetching the fork at `5a13eacf` (a few source files).
4. D-173: model calls from `model_response` (O), text-only replies as class-I calls.
5. D-174: user messages, the fake user and NPCs as simulated parties with class-I authorship.
6. D-175: harness steps (`recall`, `finish`, controller notices, uncaused errors) as harness activities, not tool use.
7. D-176: naive per-event time, no conversion, no tool-execution intervals.
8. D-177: the three judging sources and the score semantics (1 is ambiguous).
9. D-178: task-definition joins (OAS by path, task text only at class I; RedCode by key with a declared rewrite tier).
10. D-179: large content, images and secrets: images and >1 MiB strings not inlined (R-10g-2); the 3 unexplained
    secret-like values in OAS kept as published (option A, as DTap D.16.13) or withheld (option B).

## 8. Part B: implementation, mapping census and trial import (2026-10-12)

### 8.1 Code verification for D-172 (user-approved fetches)

| Code | Pin | How verified | Fetched |
|---|---|---|---|
| OpenAgentSafety's fork | `adityasoni9998/OpenHands@5a13eacf8177c8dab2600f9011d88f18a7db0ad8` (2025-04-07; `poetry.lock` at the pin: `openhands-ai 0.28.1`, `resolved_reference 5a13eacf`) | the cited files read at the commit | 41 files, 235 KB (blob:none depth 1, sparse) |
| OpenHands 1.5.0 | `OpenHands/OpenHands@a77b05509ec010d44d1e274b0f8daace0f89ea8f` (tag `1.5.0`, 2026-03-10) | git blob ids of the deposit's vendored `environment/OpenHands` equal the tag's tree for all 8 cited files (`runtime/base.py`, `controller/agent_controller.py`, `events/stream.py`, `events/event.py`, `events/serialization/event.py`, `events/action/message.py`, `memory/memory.py`, `agenthub/codeact_agent/function_calling.py`); only `pyproject.toml` differs | tree objects only, 224 KB, no file contents |

Both fetches are logged in `~/.agentprov/cache/acquisitions.jsonl`. What the code shows (D.17.4): the runtime sets an
observation's `cause` and copies the action's `tool_call_metadata` onto it; the memory sets the recall observation's
`cause`; the controller adds the not-executed notice with the pending action's `cause` at reset; the event stream assigns
increasing ids and a naive `datetime.now()` timestamp at creation; the saved trajectory is the controller's history,
which leaves out state-change, null and hidden events (the id gaps); a non-runnable `think` action gets the runtime's fixed
think observation; each action carries the metadata of the tool call it was built from. Each profile's `verified_code`
names its commit, so the `cause`, execution and call links are class D in both corpora.

### 8.2 What was built

`src/agentprov/adapters/openhands/` (reader, mapper, citation policy, catalogue `openhands` v1 with 57 rules, semantics
`openhands.tools@1`, artefact catalogue with 9 entries, family and ext schemas), profiles `openagentsafety` and
`redcode-exec-openhands`, two `planned` registry parts, spec §D.17 (with the implementation resolutions in §D.17.13),
`tests/adapters/openhands/` (47 tests), 61 fixture files (976,794 B; criteria in `tools/openhands/build_fixtures.py`:
NPC chat with checkpoint and LLM-judge entry, parallel calls, not-executed notice, uncaused error, simulated-user replies,
no evaluation file, set-of-marks screenshot, the `_draft` task; RedCode executed, score 1 with a runtime refusal, uncaused
error, request joined after the declared rewrite) and `tests/fixtures/LICENSES/OpenAgentSafety-MIT.txt`. Tools:
`tools/openhands/map_census.py` (every run mapped, sealed, annotated, derived and tier-4 validated in memory) and
`build_fixtures.py`. No core, runner, ingest, raw or other family file changed (`test_new_family_no_core_change.py`);
the one shared file outside the family is a test, `tests/adapters/runner/test_per_unit_inputs.py`, whose list of the
registered families that use per-unit inputs (D.16.14 R1) now names `openhands.events` beside `dtap.trajectory`.

**Resolutions against the approved table** (spec §D.17.13): notices and uncaused errors are activities with artefacts
(C.3.13 forbids an activity to generate a message); `finish` is an `other` part (the dispatch accounting); an `error`
observation leaves the execution status `ambiguous`; event times stay in `ext` (messages have no `t`), the run's in
`t.raw`; RedCode members carry their `member` origin and seal in release mode without the runner; the task-prompt
fixtures name no actor.

### 8.3 RedCode: mapping census of all 5,460 members (no import: D-156)

`tools/openhands/map_census.py redcode` (8 workers, 1,018 s): **5,460 mapped, 0 crashes, 0 degenerate; accounting
consistent 5,460; every tier-4 check passes** (the five `not_applicable` outcomes are migration-only checks). Issues by run:
`openhands.filtered_events` 5,460, `openhands.join_after_rewrite` 144, `openhands.harness_error` 3. Records by class:
messages O 46,508, model calls O 18,041 and I 4,421 (text replies), tool executions D 14,165, task-prompt fixtures D 5,460.
Annotations: integrity 80,357, role 28,330, outcome 5,323 (`attack_succeeded` true 3,803, false 1,520: the score-3 and
score-0 counts of §3.8), `openhands.non_informative` 137 (score 1). Byte identity across worker counts: §8.5.

### 8.4 OpenAgentSafety: trial import of all 1,560 runs (scratch corpus only)

`tools/agentdojo/phase10d_trial.py import --profile openagentsafety --jobs 8` into
`~/.agentprov/migration-work/phase10g/corpora/oas-b-j8` (offline, from the pinned staging tree; 3,687 s): **1,560
executions, every stage ok (raw, AER, SEM, PROV, validation), completeness `verified_complete` 1,560; status `ok` 1,375,
`ok_with_issues` 185; 68 validation checks, none failed.** Register codes by run:

| Code | Runs | Artefact catalogue |
|---|---:|---|
| `openhands.filtered_events` | 1,560 | 1,560 (matches) |
| `openhands.task_text_not_seen` | 1,284 | 1,284 (matches) |
| `openhands.content_not_inlined` | 322 | 322 (matches; 321 runs with a set-of-marks screenshot and 1 run whose only oversized content is a tool output over 1 MiB) |
| `openhands.not_executed_notice` | 168 | 168 (matches) |
| `unexecuted_tool_call` (core) | 168 | the same 168 runs |
| `openhands.summary_entry_missing` | 128 | 128 (matches) |
| `openhands.eval_missing` | 86 | 86 (matches) |
| `no_outcome_recorded` (core) | 22 | runs with neither an evaluation file nor an LLM-judge entry, so no judgement record at all |
| `openhands.harness_error` | 2 | 2 (matches) |

The first import, with the code of 49522a3, raised `content_not_inlined` for 2 runs only: set-of-marks screenshots
were replaced by their digest but not reported. 05dbd9a fixes this, and the import above uses the fixed code. The
expectation for `task_text_not_seen` is now 1,284, from the whole-text matcher; part A's 1,140 came from a 200-character
prefix. Recompute and chain verification: §8.5.

### 8.5 Recompute, chain verification and byte identity

- **Recompute** (`agentprov recompute --corpus oas-b-j8.partial --dry-run --strict`, 52 min): 1,560 identical, 0
  changed, 0 unexplained, 0 failed. The notice "the code digest changed and every declared version is the same" comes from
  the `artefacts.toml` expectation edited after the import (§8.4). The catalogue enters no AER, SEM or PROV file, and
  every output is identical.
- **Chain verification** (`agentprov verify --level chain`): passed, 0 failed. 4,287 raw objects were re-hashed. The one
  unverified check is `checksums.absent`, which every working tree has, since `checksums.sha256` is written at sealing.
- **OpenAgentSafety, 8 versus 3 workers** (`phase10d_trial.py compare`): every AER (1,560), every raw object and the SEM
  and PROV files of 1,559 executions are byte-identical. The 3-worker import lost the SEM and PROV of one execution to
  the worker RSS cap (R-10g-4). Derived alone, that unit's SEM and PROV equal the 8-worker files byte for byte. The 5
  aggregate files that differ (`corpus.json`, `executions.jsonl`, `register.jsonl`, `validation/results.jsonl`,
  `validation/summary.json`) differ only through that failure. `agentprov derive --out` does not re-add layers that
  failed: it carried the corpus (`plan=carry`).
- **RedCode, 8 versus 3 workers** (`map_census.py`): the AER, SEM and PROV digests of all 5,460 members are identical.
- **Existing corpora:** no file under `aer/`, `prov/`, `validate/`, `corpus/`, `sem/`, `runner/`, `raw/` or `ingest/`
  changed. The SEM stage identity is keyed by each row's own semantics profile (`openhands.tools@1`, named only by
  the two new profiles), so no existing corpus digest moves. The full suite on this branch: 5,979 passed, 2 failed.
  One failure was the runner test listing the families that use per-unit inputs, now updated (§8.2). The other,
  `test_worker_isolation.py::test_a_limit_event_replaces_the_worker_and_the_next_job_runs`, missed a 1-second wall limit
  under load from the concurrent import and passes on its own (38 passed). The golden and compat gates pass.
- **After the rebase on main (d6318f3):** full suite 6,216 passed, 0 failed, 121 skipped; ruff, mypy and
  `tools/check_unicode.py` clean.

