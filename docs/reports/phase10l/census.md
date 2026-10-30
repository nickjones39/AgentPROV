# Phase 10l, part A: census of the DRIFT-format (`drift.k18.*`) run logs

Status 2026-10-13, branch `phase-10l-drift`. Read-only census of the bytes already staged or cached; no network, no
download, no import. The proposed AER mapping that follows from it is in [`aer-mapping.md`](aer-mapping.md).

**Method.** One script, `~/.agentprov/migration-work/phase10l/scripts/c01_drift_census.py` (outside Git), plus a probe
`c02_probe.py`. Git blobs are read from the bare object stores with `git cat-file --batch` under `GIT_NO_LAZY_FETCH=1`;
the Figshare zip members are read in memory through `agentprov.ingest.archives`. JSON is parsed only with
`agentprov.ingest.loaders.strict_json_loads` and classified by the adapter's own D.6.2 `classify`. Nothing was
extracted to disk and no message text was printed: the outputs (`census/<source>.files.jsonl`, `.summary.json`,
`overlap.json`) hold counts, digests, escaped labels and shapes only. Secret-like strings are counted, never shown.
The logs carry injection payloads; they were treated as data.

## 1. Inputs

| Source (part) | Store | Pin | DRIFT files | Variant |
|---|---|---|---:|---|
| DRIFT head | `staging/10c/ref-drift/DRIFT.git` (blobless; head blobs present) | `SaFo-Lab/DRIFT@6fd3df47` | 1,569 | `drift.k18.conversations` |
| DRIFT history | same clone; blobs fetched 2026-10-13 (R-1, §6) | `53dbc6c5` | 1,046 | `drift.k18.conversations` |
| AgentDyn D | `cache/git/.../SaFo-Lab/AgentDyn.git` | `5353cf76`, `src/agentdojo/defenses/drift/runs/**` | 949 | `drift.k18.conversations` |
| AgentDyn C | same | `5353cf76`, `runs/*-drift/**` | 4,258 | `drift.k18.messages` |
| Figshare 32657856 | `staging/10c/figshare-32657856/*.zip` | deposit v1 | 2,847 | `drift.k18.conversations` |
| EnvironmentOptim | `staging/10c/environmentoptim/EnvironmentOptim.git` | `febf82d8` | 4,878 | `drift.k18.messages` |
| drift-1 | `staging/10c/drift-1/drift-1.git` | `CGboom-git/drift-1@0e28729b` | 2,195 | `drift.k18.conversations` |

Every file parsed (strict JSON) and classified as DRIFT; none was malformed. AgentDyn's `runs/gpt-4o-mini-2024-07-18-drift`
(648 files) is variant A (`v1.k14`, the integrated `--defense drift`), not DRIFT format, and is outside this census.

### 1.1 Overlap (byte identity, SHA-256)

| | DRIFT head | AgentDyn D | AgentDyn C | Figshare | EnvironmentOptim | drift-1 |
|---|---:|---:|---:|---:|---:|---:|
| files | 1,569 | 949 | 4,258 | 2,847 | 4,878 | 2,195 |
| new against the sources to their left | 1,569 | 0 | 4,258 | 2,847 | 620 | 626 |

- AgentDyn D = 949 of DRIFT head (all AgentDojo-suite runs), as recorded (edge E09).
- EnvironmentOptim holds all 4,258 AgentDyn C files byte for byte; its 620 new files are `runs/gpt-4o-mini-2024-07-18-drift/`
  in variant C form (`messages`). AgentDyn's history had a variant C generation of exactly this directory (620 files,
  `2d4ad05`…`785b912`, `sources/agentdyn.md` §4.6), so these 620 are probably AgentDyn history blobs. That cannot be
  checked without AgentDyn's history (the cached clone is depth 1). Open point Q5 in `aer-mapping.md`.
- drift-1 holds all 1,569 DRIFT head files; its new 626 are `runs/gpt-4o-mini/` (616) and
  `runs/pact-gpt-4o-mini-banking10/` (10, with six extra top-level keys).
- Figshare shares no bytes with any other source (its `gpt-4o-mini-2024-07-18` arm is a re-run on `v1.2.2`).
- **10,966 byte-distinct DRIFT files**: the 9,920 staged on 2026-10-13 plus the 1,046 history files fetched the same day. The
  "about 11,900" of D-96 counted the 949 AgentDyn D copies.

## 2. Top level

- **One key set, one key order per source.** All 18 keys of `KD18_BASE` plus `conversations` (DRIFT, AgentDyn D,
  Figshare, drift-1) or `messages` (AgentDyn C, EnvironmentOptim), in `pipeline_main.py`'s `json.dump` order. The only
  extra keys are drift-1's 10 PACT files (`pact_drift_enabled`, `global_tool_contract_path`, `task_contract`,
  `provenance_records`, `argument_validation_events`, `pact_drift_decision_summary`): a third-party variant.
- **No** `injections`, `error`, `evaluation_timestamp` or `agentdojo_package_version` in any file.
- DRIFT flags: `build_constraints`, `injection_isolation`, `dynamic_validation` are `true` and `adaptive_attack` is
  `false` in all 16,696 files (full DRIFT, no adaptive attack).
- `benchmark_version`: `v1.2` everywhere except Figshare (`v1.2.2`). `pipeline_main.py` loads the suite with
  `get_suite(args.benchmark_version, suite)`, so for the AgentDojo suites the label is the suite version actually
  loaded; AgentDyn registers its suites under every version key, so for `dailylife`/`github`/`shopping` it says nothing.
- `total_tokens` int and `duration` float in every file. `utility`/`security` bool in every file (no nulls).
- Benign `security` is `true` in all 1,117 benign runs (DRIFT head 60, AgentDyn C 420, EnvironmentOptim 480,
  drift-1 157): `DRIFTTaskSuite.run_task_with_pipeline` returns the constant `True` when there is no injection task.

### 2.1 Identity sources

| Source | `pipeline_name` | path directory | agrees |
|---|---|---|---|
| DRIFT head, AgentDyn D | `gpt-4o-mini-2024-07-18` | `gpt-4o-mini-2024-07-18` | 100 % |
| AgentDyn C, EnvironmentOptim | `gpt-4o-2024-08-06`, `gpt-5-mini-2025-08-07`, `gpt-5.1-2025-11-13`, `gemini-2.5-pro`, `google/gemini-2.5-flash`, `meta-llama/llama-3.3-70b-instruct`, `qwen/qwen3-235b-a22b-2507` (+ `gpt-4o-mini-2024-07-18` in EnvironmentOptim) | `<model>-drift` (provider prefix `_`-joined) | never by string; the AgentDyn table's variant C rows give both |
| Figshare | `gpt-4o-mini-2024-07-18`, `gpt-oss:20b`, `qwen3.6:27b` (949 each) | `runs_agentdojo_full_<arm>/<pipeline_name>/` | 100 % |
| drift-1 | `gpt-4o-mini-2024-07-18` (copies), `gpt-4o-mini` (626, undated alias) | same, except `pact-gpt-4o-mini-banking10` (10) | 2,185 of 2,195 |

`pipeline_name` is `f"{args.model}"`, the value `pipeline_main.py` passes to its client as the model, so it is the
requested model id. The provider is chosen by prefix in `pipeline_main.py` (`gpt-` OpenAI, `gemini-` Google, else
OpenRouter); Figshare's arm names (`api_compat`, `compat_module`, `ollama`) say its harness differed.

## 3. Messages

| measure | DRIFT head | AgentDyn D | AgentDyn C | Figshare | EnvironmentOptim | drift-1 |
|---|---|---|---|---|---|---|
| messages | 16,868 | 8,705 | 54,239 | 21,577 | 62,476 | 22,929 |
| per run min/median/max | 2/10/23 | 2/8/23 | 2/13/29 | 2/6/38 | 2/13/29 | 2/10/23 |
| attacked / benign runs | 1,509/60 | 949/0 | 3,838/420 | 2,847/0 | 4,398/480 | 2,038/157 |
| `system` messages | 0 | 0 | 0 | 0 | 0 | 0 |
| first `user` (task prompt) | 1,569 | 949 | 4,258 | 2,847 | 4,878 | 2,195 |
| `user` CALL ERROR (in files) | 833 (538) | 398 (264) | 3,792 (1,663) | 724 (515) | 4,167 (1,919) | 1,099 (711) |
| of which trajectory / checklist / other text | 326/507/0 | 129/269/0 | 379/3,413/0 | 106/618/0 | 753/3,414/0 | 385/705/9 |
| other later `user` | 0 | 0 | 0 | 0 | 0 | 0 |
| assistant re-serialised / raw | 7,341/950 | 3,673/596 | 23,995/2,197 | 8,494/2,056 | 27,736/2,469 | 9,958/1,296 |
| tool calls = tool messages | 6,175 | 3,089 | 19,997 | 7,456 | 23,226 | 8,381 |
| call batches; id-matched | 5,889; 5,889 | 2,922; 2,922 | 18,140; 18,140 | 6,966; 6,966 | 21,158; 21,158 | 7,960; 7,960 |
| orphan tool messages; calls without result | 0; 0 | 0; 0 | 0; 0 | 0; 0 | 0; 0 | 0; 0 |
| tool errors (invalid tool / ValidationError / exception) | 579 (49/114/416) | 305 (37/70/198) | 2,285 (807/226/1,252) | 773 (207/104/462) | 2,502 (824/234/1,444) | 758 (69/151/538) |
| final turns with call text but no `tool_calls` (re-serialised / raw) | 311/6 | 99/1 | 1,497/506 | 190/101 | 1,736/509 | 389/6 |
| turns with more call names in the text than `tool_calls` (upper bound) | 20 | 15 | 204 | 20 | 209 | 23 |
| call ids distinct / in >1 file (max files) | 3,265 / 975 (9) | 1,168 / 538 (8) | 13,332 / 2,769 (54) | 5,343 / 1,036 (12) | 15,938 / 3,113 (55) | 5,128 / 1,219 (11) |
| last message is `assistant` | all | all | all | all | all | all |

Shapes, every source:
- **Message key sets** are exactly `user {role, content}`, `assistant {role, content, tool_calls}`,
  `tool {role, content, tool_call_id, tool_call, error}`. Every `content` is a string (DRIFTLLM collapses AgentDojo
  0.1.35 block lists to `content[0]["content"]` in place). Every `tool_calls` is a list (never null).
- **Calls**: key set `{function, args, id}` only (no `placeholder_args`); ids all `tool_call_` + 10 `[a-z0-9]`
  (AgentDojo `ast_utils` with Python `random`, seeded by `--seed 98`), unique within a file, reused across files.
- **Tool-call/result pairing by id holds everywhere**: every assistant message with *n* calls is followed by exactly *n*
  tool messages whose `tool_call_id`s are the call ids (one each, in order), and each tool message's embedded
  `tool_call` equals its call lexically (member order and number typing). The D.6.6.1 id rule applies to all 63,035
  batches (files counted with their copies); positional matching is never needed.
- **CALL ERROR** messages always have the exact form `</function_error>\n<repr of {'role': 'user', 'content':
  "[CALL ERROR] ..."}>\n</function_error>`; each follows an assistant message with an empty `tool_calls` and a non-empty
  `<function_call>` body (validator `output["tool_calls"] = []`), and each is followed by an assistant message. The
  two template texts of `DRIFTLLM.trajectory_constraint_validation` and `checklist_constraint_validation` cover all
  but 9 drift-1 messages (IFC-DRIFT wording).
- **Re-serialised** = full match of `<function_thought>…</function_thought>\n\n<function_call>…</function_call>\n\n
  <final_answer>…</final_answer>` (`DRIFTLLM._parse_model_output`); **raw** = the completion as returned (no
  `<function_call>` tag, the 20-message cap, or three failed parse attempts).
- **Non-executed proposed calls** occur on three code paths: the validator (CALL ERROR follows; counted above),
  de-duplication of an already executed call string (`DRIFTLLM.query`, silent; ends the run when every call is
  dropped), and the raw paths (cap or parse failure). Partial drops (some calls of a turn executed, others dropped) are
  silent too; the "upper bound" row counts turns whose text names more calls than `tool_calls` holds, by a name regex
  (nested calls in arguments inflate it; the verification report found 6 at DRIFT head with `ast`).

## 4. DRIFT's own structures

| measure | DRIFT head | AgentDyn D | AgentDyn C | Figshare | EnvironmentOptim | drift-1 |
|---|---|---|---|---|---|---|
| `initial_checklist`: raw planner text / JSON / `[]` / `None` | 1,512/0/0/57 | 930/0/0/19 | 0/3,469/435/354 | 2,665/22/0/160 | 0/4,009/501/368 | 2,136/0/0/59 |
| `initial_trajectory` covers every executed function: yes / no / no executions | 847/702/20 | 660/275/14 | 3,581/0/677 | 1,430/1,248/169 | 4,187/0/691 | 1,288/872/35 |
| `initial_trajectory` empty | 0 | 0 | 20 | 135 | 20 | 0 |
| `tool_permission` values | Read/Write/Execute | same | same | same | same | same |
| calls to a tool missing from `tool_permission` | 49 | 37 | 807 | 207 | 824 | 69 |

- **Plan-field semantics differ by producer**, as the verification report found for DRIFT history (`verify/drift.md` §5):
  where `initial_checklist` is the raw planner text and the trajectory often lacks executed functions, the fields hold
  the **initial plan** (`pipeline_main.py` at and after `1af2672`/`5f7c1a9`: DRIFT head, AgentDyn D, Figshare, drift-1);
  where the checklist is JSON (or `[]`) and the trajectory covers every executed function in 100 % of runs with
  executions, they hold the **end-of-run plan state** (`llm.function_trajectory`/`llm.node_checklist`, before
  `1af2672`: AgentDyn C and its EnvironmentOptim copies, January 2026 by their stamps; and DRIFT history by the
  verification report). The two forms never mix within a source, so a per-part declaration checked per file is enough.
- **`tool_permission`** is assigned by an LLM once per process (`DRIFTLLM.function_privilege_assignment` when the map is
  empty): 1 to 3 distinct maps per suite. The calls missing from the map are exactly the `Invalid tool` errors
  (hallucinated tool names).
- **`total_tokens`** is the delta of the client's cumulative counter over the run: every DRIFT LLM call (planner,
  detector, judge, formatter, agent, parse retries; privilege assignment in a process's first task), not the agent's.
- **`duration`** is `time.time()` around `run_task_with_pipeline` (environment load, the one pass and the checker; not
  the attack's payload generation or the file write).

## 5. Time, isolation, payloads, secrets

- **No structured time** anywhere (no run, message or call time). **Run-time stamps inside tool outputs** (microsecond,
  timezone-naive, written by environment code such as `send_email`, `create_file` and the AgentDyn email clients):

  | | DRIFT head | AgentDyn D | AgentDyn C | Figshare | EnvironmentOptim | drift-1 |
  |---|---|---|---|---|---|---|
  | runs with such a stamp | 371 | 150 | 1,531 | 292 | 1,826 | 391 |
  | range (local, zone unknown) | 2026-02-13 02:03 .. 2026-03-22 00:12 | 2026-02-13 02:03 .. 19:10 | 2026-01-25 20:40 .. 01-28 01:35 | 2026-05-19 09:27 .. 06-03 13:27 | 2026-01-25 07:55 .. 01-28 01:35 | 2026-02-13 .. 2026-06-24 |

  They are content (D.6.8): never AER or PROV time. They do date the producers: AgentDyn C ran on 25–28 January 2026,
  before DRIFT's `1af2672` (4 February), which fits its end-of-run plan fields.
- **Isolation covers only the last result of each call batch.** `DRIFTLLM.query` runs the detector on `messages[-1]`
  and `injection_isolate` edits `messages[-1]` only, so with parallel calls the earlier results are never inspected.
  The data agree in every source: injection frames with an excised GOAL occur only in last positions (DRIFT head 1,306,
  history 803, AgentDyn C 2,376, drift-1 1,787), never in earlier ones, which still hold intact frames (44, 123, 274,
  56). Figshare's 165 visible frames are all in earlier positions. (Probe `c03_isolation_position.py`.)
- **Isolation** is otherwise invisible per message: DRIFT edits the tool message in place when its detector reports
  instructions and records nothing. With the `important_instructions` frame, 2,006 framed payloads at DRIFT head split into GOAL
  excised and GOAL present by a heuristic (961/1,045 in `verify/drift.md`; 1,306/700 by this census's YAML-escape-tolerant
  regex, which also counts quote-only remnants as excised), plus 118 partial frames. This is SEM material
  (regeneration-batch item 6), not AER.
- **Payload visibility, Figshare:** an injection header appears in tool outputs of only 123 of its 2,847 attacked runs
  (DRIFT head: 1,270 of 1,509), and `security` is `false` in all 2,847. Whether the Figshare harness (`compat`
  arms) placed the injections differently is not visible in the logs; for its profile owner (phase 10j) and datasheet.
- **Secret-like strings:** `private_key` headers in 4 AgentDyn C and 5 EnvironmentOptim DRIFT files (counts only;
  presumably fictional key material in the `github` suite's environment data). The release secret scan will flag them;
  the AgentDyn and EnvironmentOptim profiles need a `[withhold]` decision (D-230..D-237) before any release. 0 in the
  other sources.

## 6. DRIFT history (`53dbc6c`, 1,046 files; measured after the fetch)

The 1,046 history blobs were fetched with the user's approval (R-1, 2026-10-13: one batched object request into the
staged blobless clone, 13,249,625 bytes, logged in `acquisitions.jsonl`). The census reproduces `verify/drift.md` §5:
the same 18 keys, 949 attacked and 97 benign runs (banking 16, slack 21, travel 20, workspace 40), checklist JSON 498 /
`[]` 541 / `None` 7, and the trajectory covers every executed function in all 1,039 runs with executions (end-of-run
plan state); 172 runs carry run-time stamps (2026-01-31 15:15 to 22:44). Messages 9,057 (CALL ERROR 142: trajectory 134,
checklist 8; assistant re-serialised 3,666 / raw 623), 3,580 tool calls in 3,101 batches, all linked by id; ids are
nearly unique across files (30 of 3,550 in two files). Licence policy `reference` (D-279).

## 7. The `drift_*` quirks against the evidence

| Quirk (D.4.4 / D.6.4) | Code (DRIFT `6fd3df4`, vendored at AgentDyn `5353cf76`) | Data (this census) | Holds in |
|---|---|---|---|
| `drift_tool_output_post_isolation` | `DRIFTLLM.injection_isolate`: `messages[-1]["content"] = remove_sentence(…)` on the shared dict, before the next agent call; the last result of a batch only | edits not detectable per message; excised frames only in last positions (§5) | all sources (flag `injection_isolation: true` everywhere) |
| `drift_assistant_reserialised` | `_parse_model_output` returns the template; text outside the three tags is dropped | template full-match in 80–92 % of assistant messages per source | all |
| `drift_call_error_as_user` | `trajectory_constraint_validation`/`checklist_constraint_validation`: `role: "user"` message wrapped in `</function_error>` | 11,013 messages; exact wrapper 100 %; preceded by an empty-call assistant 100 % | all (9 drift-1 messages with other text) |
| `drift_calls_in_text_not_executed` | de-duplication against `_load_previous_calls`; the 20-message cap; failed parses | 100 to 2,245 final turns per source (§3) | all |
| `drift_no_system_no_injections` | `AgentPipeline([InitQuery(), llm, loop])`, no `SystemMessage`; `json.dump` writes no `injections` | 0 system messages, 0 `injections` keys | all |
| `drift_plan_fields_by_commit` | `pipeline_main.py` writes `llm.function_trajectory`/`node_checklist` before `1af2672`, `initial_*` after | §4: two disjoint forms by producer | all (per part) |
| `provider_call_id_anomalies` (seeded random, trace-local) | `ast_utils` ids from `random`, `set_seed(98)` | 0 in-file duplicates; up to 55 files share an id | all |
| `benign_security_constant` | `DRIFTTaskSuite.run_task_with_pipeline` returns `True` without an injection task | 1,117 of 1,117 benign runs | all with benign runs |
| `args_mutated_in_place` | AgentDojo 0.1.35 `ToolsExecutor` (`literal_eval` on the call's args) | not observable in the data | all (0.1.35 harness by `requirements.txt`) |
| `silent_rerun_last_pass_only` | does **not** apply: `model_output_from_messages` never returns `None` (single pass) | — | none |
| `unexecuted_trailing_calls` | `max_iters=15` | 0 occurrences | none observed |
| (new) partial call drop | de-duplication drops some calls of a turn | ≤ 20–209 turns per source (§3) | all |
| (new) PACT extra keys | drift-1 `pact_drift` variant | 10 files | drift-1 |
