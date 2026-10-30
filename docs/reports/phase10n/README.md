# Phase 10n: the last two small sources of the phase-10e ranking

Branch `phase-10n-small`, started 2026-10-13 from origin/main `52c0974`. Ranks 11 and 12 of the phase-10e ranking
(D-145): (A) Zenodo 23025259, AutoGen guard placement, a new adapter family; (B) `mattngyn/atia_benchmark`, a profile in
the existing `inspect` family. Decisions D-300–D-309 were **approved by the user on 2026-10-13** (recorded in
`docs/architecture/DECISIONS.md`); §4 is the mapping as proposed and §7 where the implementation had to differ.

Everything in both sources is untrusted data. The deposit's code was read as data and never run, installed or followed.
Probe documents carry injection passages and canaries; none is quoted here (counts and field names only). Scripts and
intermediate output: `~/.agentprov/migration-work/phase10n/` (outside Git).

**Status (2026-10-13):** A: the `autogen` family is built (spec §D.22). With the runner's multi-execution support on
main (R-10k-1, D-320; R-10n-3 closed) the reader declares `multi_execution` and the pinned deposit imports through the
product path: a scratch trial of all 1,080 run rows is clean and byte-identical at 8 and 3 workers (§8). B: profile,
registry part, tests and scratch trials done (§5); with regen-batch item 25 on main the trials are clean; the import waits
for item 28 (media strings over 1 MiB, D-308). Both registry parts stay `planned` until a recorded full import. Routing:
`routing.md`.

## 1. Part A: source and acquisition

| | |
|---|---|
| Record | Zenodo 23025259, v1.0 (concept 23025258); CC-BY-4.0 data (`LICENSE-DATA`), MIT code (`LICENSE`); AgentDojo templates and InjecAgent cases MIT (`LICENSE-THIRD-PARTY`) |
| File | `autogen-guard-placement-data-code-v1.0.zip`, 4,978,620 B, sha256 `af2f519347c9554ba0857cc4ca989c17e45588bc421b1af990971540bd9f7b63` |
| How obtained | the phase-10e download (`~/.agentprov/staging/10e/zenodo_23025259/`, user-approved 2026-10-12, logged in `data/V10e-verification/V10e-calls-downloads.jsonl`); digest re-checked here; **no network in this session** |
| Read with | `ingest.archives.open_zip` / `iter_zip_members` (109 members, 109 selected, 0 rejected), `strict_json_loads` per JSONL line (0 failures); nothing extracted |

## 2. Part A: census

### 2.1 Members and run rows

- 14 `results/**/runs.jsonl` files, 1,270 rows: **1,080 rows with `messages`** in 11 files (phases 2, 3, 4, 5, 10, 12, 13
  and `phase6/{bus,model,none,tool}`), and **190 rows without** in 3 files. This reproduces phase 10e (1,080 counted,
  190 not counted). `run_id` is unique across the 1,080 (1,080 distinct).
- Per phase: 2: 340, 10: 210, 12: 160, 3: 120, 13: 80, 4: 60, 5: 30, 6: 4 × 20.
- The 190 rows are not one kind (correcting the phase-10e note "rows without messages"):
  - **phase 7, 150 rows**: the bench's NeMo Guardrails input rail on each probe (`probe_id, response, backend,
    history_id, outcome, events[]`); the events are rail configuration steps. No agent and no tool: not a tool-using
    agent execution (IN-1, as D-140 reads it).
  - **phases 8 and 9, 20 rows each**: the same team rebuilt in LangGraph and CrewAI (`framework, result {final, notes,
    events[]}, returncode, stderr_tail`). `result.events` holds guard verdicts, `tool_call` (tool and arguments) and
    `agent_done` (agent output) records, but **no tool results**: a partial trajectory (EX-FMT by D-141's boundary).
- Other members: per-phase `events.jsonl` (11 phase directories with team runs), `guard_raw.jsonl` (13),
  `workbench_state.json`, `capture.json` (phases 0, 7, 8, 9), standalone guard verdicts (`phase1/`, `phase11/verdicts.jsonl`:
  no agent), probe sets (`data/probes/probes.jsonl` 150, `keyword_probes.jsonl` 50), InjecAgent selection
  (`data/thirdparty/injecagent_dh.jsonl` 60, `injecagent_tools.json`), source snapshot, code (`src/`), analysis outputs.

### 2.2 The 1,080 runs

- **Shape** (one per row): `run_id, phase, probe_id|case_id, entry, modes{model,bus,tool}, block_guard?, defense?,
  condition?, carrier_id?, termination?, keyword?, block_at?, messages[], tool_calls[], stop_reason?, error, wall_s`.
  Four key sets: the team runs (phases 2–5), phase 6 (`case_id`, `block_at`), phases 10/13 (`condition`), phase 12
  (`defense`). `stop_reason` is absent in 240 phase-2 rows. `error` is `null` in 1,080/1,080.
- **Messages** are AutoGen 0.7.5 `TaskResult.messages`, each `{type, source, text, raw}` with `raw` the pydantic dump
  (`id` uuid4, `created_at`, `source`, `models_usage`, `metadata`, `content`, `type`): TextMessage 3,375,
  ToolCallRequestEvent 1,120, ToolCallExecutionEvent 1,120, ThoughtEvent 267 (writer 229, researcher 38),
  MemoryQueryEvent 225. Sources: researcher 2,485, writer 2,287, user 1,080, ingest 255. The first message is the
  user task in 1,080/1,080. Longest message text under 10,000 characters.
- **Entry points** (where the probe document enters): tool 345 (`fetch_document` output), user 255 (inside the task),
  agent 255 (the model-less `ingest` agent's turn), memory 225 (`ListMemory`, a `MemoryQueryEvent`).
- **Tool calls:** 1,120 call items, 1,120 result items. Within a run, every `ToolCallExecutionEvent` item's `call_id`
  equals exactly one `ToolCallRequestEvent` item's `id` (1,080/1,080 runs; no duplicate, no orphan). 737 runs have
  calls (1: 403, 2: 292, 3: 35, 4: 7); **343 have none**. Tools: `save_note` 731, `fetch_document` 265, InjecAgent stub
  tools 124 (32 names). `is_error: true` 4 (all `EvernoteManagerSearchNotes`, phase 6, one per placement arm). The row's
  own `tool_calls[]` lists the `save_note` calls and attacker-tool calls (a harness side list).
- **Stops:** `MaxMessageTermination` 760 (3 or 4 messages), `TextMentionTermination` 80; 40 runs (phase 10, entries user
  and agent) stop before any agent speaks, because the document handed in the task or by the `ingest` agent contains
  the keyword: **no model call** in those 40.
- **Probes and cases** (join by id, 1,080/1,080): `probes.jsonl` 830 runs, `keyword_probes.jsonl` 170, InjecAgent 80.
  Probe label attack 50 / benign 100 (+50 keyword probes); groups `attack`, `matched`, `hn_imperative`, `hn_vocab`,
  `hn_identifier`, `keyword`; attack templates `direct`, `ignore_previous`, `system_message`, `injecagent`,
  `important_instructions` (10 each; passages from `agentdojo@089ed468cf3e`), goal kinds `output` 25 / `tool` 25;
  carriers are NWS alerts and arXiv records. InjecAgent cases: Data Security 22, Physical 20, Financial 18 harm.
- **Guard settings:** `modes` observe-all 560, model block 180, bus block 120, tool block 60; `block_guard` `llm` 630;
  guards scanned per event `{deberta, llm}` in 870 runs, `{keyword}` in 210 (phase 10). Phase 12 prompt defences
  `spotlight` 80, `sandwich` 80. Phase 13 is `SelectorGroupChat` (a `selector` model call per turn).

### 2.3 The event log (`events.jsonl`) and the guard log (`guard_raw.jsonl`)

**Correction to the phase-10e card (§3.15):** `events.jsonl` does not store text hashes only. Only its `guard` rows do.
By kind:

| kind | rows | content |
|---|---:|---|
| `guard` | 20,900 | `placement`, `msg_kind`, `agent`, `text_sha` (the first 16 hex of the text's SHA-256), `chars`, `flags{guard: bool}`, `flag`, `contains_passage`, `contains_canary`, `delivered?`. **No text.** |
| `llm_request` | 3,286 | `agent`, `messages[{type, text, raw}]` as handed to the model client (after any model-placement redaction), `tools` (names logged as `null`) |
| `llm_response` | 3,283 | `agent`, `request_seq`, `content` (text, or function calls `{id, name, arguments}`), `thought`, `finish_reason`, `usage` |
| `tool_call` | 1,118 | `agent`, `tool`, `args` (and `attacker: true` for 28 InjecAgent attacker-tool calls) |

Every row has `run_id`, `seq` (one run-wide counter) and `t` (`time.time()` epoch seconds). `guard_raw.jsonl` holds
each distinct scanned text once per guard and phase, **with** its text and the verdict detail (`label`, `score`, `raw`,
`latency_s`); its `text_sha` equals the recomputed digest of its own text in 7,283/7,283 rows.

- **Events join the runs by `run_id`**: 1,080/1,080 runs have events, and every guard row's `text_sha` is in the same
  phase's `guard_raw.jsonl` (20,900/20,900).
- **Retried runs:** in 3 phase-2 runs the counter restarts (`p2_c03_matched_agent`, `p2_c04_hn_vocab_agent`,
  `p2_c20_attack_tool`): an aborted first attempt (14–16 events, 3 requests without a response) and a complete second.
  The run row belongs to the **last** attempt: its function-call ids equal the row's request ids in 2 of 3 (the third
  has no call) and its response texts equal the row's agent messages in 3 of 3. In every other run `seq` is gapless
  from 1 and `t` is non-decreasing in `seq` order.
- **Model calls ↔ messages** (last attempt): every `llm_response.request_seq` names an `llm_request` of the same agent
  (3,280/3,280); 0 requests without a response. Function-call ids in the responses equal the `ToolCallRequestEvent`
  ids, in order, in 1,080/1,080 runs. Text responses equal an agent `TextMessage` (same agent, same text) in 1,000 runs;
  the other 80 are the phase-13 runs, whose `selector` responses are speaker names, not messages.
- **Harness `tool_call` events ↔ executions:** names agree in order in 1,076 runs. The 4 others are the 4 `is_error`
  results: the stub's argument model rejected the call, so the tool body never ran and wrote no event.
- **Guard rows ↔ recorded texts** (by recomputing `sha256(text)[:16]` of texts that are recorded, never the reverse):
  20,781 of 20,865 last-attempt guard rows match a text in the run row's messages or in an `llm_request` (bus 10,360,
  model 10,101, tool 320); 84 match neither (model 26, bus 21, tool 37). The 37 tool rows are scans of a
  `fetch_document` output that a tool-placement block then replaced.
- **Withheld text** (`[content withheld by guard]`, harness constant): 27 tool results under tool blocking, 11 agent
  `TextMessage`s under bus blocking. Model-placement blocks change only the model's input, which `llm_request` records.

### 2.4 Clocks, identity, versions

- `created_at` on every message: ISO 8601 UTC with microseconds and `Z`, non-decreasing in message order in 1,080/1,080
  runs (AutoGen's default factory at message construction; code not verified here). Event `t`: epoch floats from
  `time.time()` (deposit harness code). Two wall clocks, one host; neither is a dispatch time of a tool.
- **Agent model**: not in any run, message or event. `config.json` requests `qwen/qwen3.5-9b` from a local LM Studio
  server (`reasoning_effort: none`, `temperature: 0`, seed `20260924` in the harness code); `results/phase0/capture.json`
  (2026-09-24T13:12:38Z) records `agent_model_requested` and `agent_model_echoed` both `qwen/qwen3.5-9b` and the served
  model list. Weights, quantisation and LM Studio version are not recorded.
- **Guards**: `deberta` = `protectai/deberta-v3-base-prompt-injection-v2` at a pinned Hub revision (config); `llm` =
  `qwen/qwen3.5-9b` with a fixed system prompt (capture); `keyword` = deterministic test for the termination keyword.
- **Versions**: AutoGen `autogen-agentchat`/`-core`/`-ext` 0.7.5 (`requirements.txt`, phase-0 capture), Python 3.11.16,
  macOS host. The runs name no code commit; the deposit is the code snapshot of v1.0.
- **Secrets and personal data:** the client's `api_key` is the LM Studio placeholder in the code, never in the data;
  endpoints are `127.0.0.1`. No account path seen in run rows (checked again in part B before any fixture).

### 2.5 What blocks import (D-301)

`map_artefact_total` maps exactly one located item per file (`adapters/runner/__init__.py`: more than one item gives a
degenerate AER), and the container mode exists only for zip members expanded by the `expand` stage (Inspect `.eval`).
Here one `runs.jsonl` member holds 20–340 runs, one per line. The runner cannot import them one execution per run
without a new **row-unit** capability: a reader yields several located items per artefact (locator `{"a": "a0", "line":
n}`), each sealed as its own execution, and rows the reader rejects become register rows with a line subject. That is a
change to `adapters/runner/` (and `importer.py`), which this session does not own and which moves the `aer` stage
identity of every corpus (`regen-batch.md`). The same capability is what memo-ozdincer's results containers need (runs
inside `results/*.json`, D-146).

## 3. Part A: counting and scope summary

| Rows | Disposition proposed |
|---:|---|
| 1,080 | in scope, one execution each (D-300) |
| 150 | phase 7: `select.not_execution_artefact`, detail `autogen.rail_probe_no_agent` |
| 40 | phases 8–9: `select.out_of_scope`, detail `autogen.partial_trajectory` (no tool results; D-141/D-143) |
| non-run files | `select.not_execution_artefact` (standalone guard verdicts, captures, analysis, code, data); `events.jsonl` and `guard_raw.jsonl` are per-unit auxiliary inputs, the probe and case files context inputs |

## 4. Part A: AER mapping as proposed (approved; implementation differences in §7)

New family `autogen` (`src/agentprov/adapters/autogen/`), dialect `autogen.runs` (variants by key set: `team`,
`injecagent`, `condition`, `defense`), mapper adapter 0.1.0, namespace `autogen`. One AER per run row; logical identity
`<phase dir>/runs.jsonl` + `run_id` (checked unique). Per-unit auxiliary inputs: the same directory's `events.jsonl`
(rows selected by `run_id`, D) and `guard_raw.jsonl` (rows selected by `(guard, text_sha)`, D after recomputing the row's
own digest); context inputs: probes, keyword probes, InjecAgent cases and tool schemas, `config.json`, phase-0
`capture.json`.

| Source | AER | Evidence |
|---|---|---|
| task `TextMessage` (source `user`) | `message` role `user`, actor `user` (`simulated_user`); the task is the harness's template per entry point | text O; author I (`autogen.task_is_harness_template_unverified@1`) |
| probe / case join | fixtures `document` (the probe text after the phase-12 defence transform), `injection_payload` (the passage; attack probes only), canary in `ext` (never quoted); InjecAgent `task_prompt` (user instruction) and `injection_payload` (attacker instruction) | join D (`autogen.probe_join@1`); "occurs where the entry point delivers it" D (verbatim check, issue when not) |
| `llm_request` + `llm_response` (same `request_seq`) | `model_call` `mc<seq>`: `role: agent`, actor = `agent`, `input` = the logged sent messages, `response`, `finish_reason`, `usage`; `status: kept`; requested model from config | values O; link D (`autogen.request_seq@1`); "input is what the model read" I (`autogen.request_log_is_model_input_unverified@1`) |
| agent `TextMessage` | `message` role `assistant`, actor researcher / writer, `generated_by` the one `llm_response` of that agent with that text | D (`autogen.response_text_equal@1`); no link when 0 or 2+ responses match (issue) |
| `ThoughtEvent` | a `reasoning` part of the message generated by the same call (`llm_response.thought` equal) | D when equal, else I |
| `ToolCallRequestEvent` | `message` role `assistant` with one `tool_call` part per item (`args` decoded strictly, `args_raw` kept), `generated_by` the call whose response holds those ids | D (`autogen.function_call_id@1`) |
| `ToolCallExecutionEvent` item | `tool_execution` (actor `env`) answering the call with `call_id` = its `id`, and a `tool` message with `tool_result {responds_to}`; `is_error: true` → status `error`, issue (tool body not entered: no harness `tool_call` event) | link D if AutoGen code is verified, else I (`autogen.call_id_link_unverified@1`, D-303) |
| `MemoryQueryEvent` | `activity` `autogen:memory_query` (actor `harness`) and `artefact` `autogen:memory_content` | I (`autogen.memory_query_unverified@1`) |
| `ingest` agent `TextMessage` | `message` with the verbatim source as role label `ingest` (C.3: non-core roles kept verbatim), actor `ingest` (a model-less harness agent), no `generated_by`, no model call | text O; actor I (`autogen.ingest_agent_has_no_model_unverified@1`) |
| `selector` calls (phase 13) | `model_call` with actor `selector` (speaker selection), no message generated; the chosen name in `ext` | O; link D (request_seq) |
| guard rows | §4.1 (D-304) | |
| `tool_calls[]` side list | profile check only (equals the `save_note` and attacker-tool calls), never records | D |
| `stop_reason`, `error`, `wall_s` | run `status` `ok`/`limit` (max-message stop is the team's configured limit, I); `wall_s` in `ext` with `unk /t/dur_s ambiguous` | O / I |
| aborted attempts (3 runs) | not mapped; disclosed (`autogen.aborted_attempt_events`) | D (attempt choice by call ids and texts) |

### 4.1 Guards (D-304)

- Every guard row becomes **one `judgement` per guard in `flags`** (actor `guard_deberta`, `guard_llm` or
  `guard_keyword`; value the boolean; `ext` `placement`, `msg_kind`, `delivered`, `contains_passage`,
  `contains_canary`). Its subject is the record whose recorded text has the row's digest (D,
  `autogen.guard_text_digest@1`; 64-bit prefix, collision risk disclosed). For the 84 rows that match no recorded text
  the subject is the run and the digest stays in `ext`: **the hash is never treated as recovered text**.
- The verdict detail (`label`, `score`, `raw` output, `latency_s`) comes from the `guard_raw.jsonl` row with the same
  `(guard, text_sha)` after that row's own text has been re-hashed (D). The guard's input text in `guard_raw` is the
  guard's own record, cited by locator, never copied into the subject.
- A **block** (mode `block`, `flag` true for `block_guard`) is also a `decision` (actor the guard, `verdict: modify`)
  following C.5.5 as AgentOps' payload injection did: tool placement, the decision on the execution generates the
  withheld result; bus placement, on the agent message, generating the withheld copy; model placement, on the model
  call's input (the withheld text is in `llm_request`, O). "Block means replace by the constant" is harness code: I
  (`autogen.block_replaces_text_unverified@1`); the replaced text itself is O.
- Guards that only observed never become decisions.

### 4.2 Identity, time and order (D-305)

- Actors `researcher`, `writer`, `selector` (`llm_agent`): `model.requested` = `qwen/qwen3.5-9b` from `config.json`
  (I, `autogen.config_agent_model_unverified@1`: one config for all phases, run over days); `served` `not_recorded`
  (the phase-0 echo goes to `ext`, I); weights and quantisation `unk not_recorded`. `harness` (AutoGen 0.7.5, from
  `requirements.txt` and the capture, I), `bench`, `env` (`tool_runtime`), `ingest`, and the guards (deberta with its Hub
  revision, I).
- `created_at` and event `t` are kept verbatim (`ext`, `t.raw`) with typed slots `ambiguous`; no time is converted or
  placed and no `time` edge is written. Order: message order (`after` positional, I,
  `autogen.taskresult_order_unverified@1`) and `seq` order for model calls and guard rows (I, deposit code).

### 4.3 Code citation (D-303)

- **AutoGen library behaviour** (`call_id` = the request's `id`; `ToolCallExecutionEvent` written after the tool
  returns; `created_at` set at construction): D only if the AutoGen 0.7.5 source is read at its tag. That is a small
  fetch (a few files of `microsoft/autogen` at `python-v0.7.5`), which needs your yes. Without it the rules cite their
  `_unverified` twins (I), as D-24 does.
- **The deposit's harness** (`src/harness.py`, `run_experiment.py`): cited as documentary evidence with I rules, as
  D-193 did for AgentOps. The runs name no commit and the phases ran over several days, so "this code produced these
  rows" is not verifiable. The logs agree with the code everywhere checked (event kinds and fields, the withheld
  constant, the retried-run pattern of "resume by id").

### 4.4 Semantics and outcomes (D-306)

Semantics profile `autogen.tools@1`: `fetch_document` (`content_source`, output `untrusted`), `save_note` (`write_sink`),
InjecAgent user tools (output `untrusted`, stub replies) and attacker tools (`send_sink`, stubs: they run and record,
nothing else). SEM outcome claims only, never AER judgements: canary in a `save_note` argument or in the writer's final
message (goal kinds `tool`/`output`, verbatim match against the joined canary, D), InjecAgent breach = an attacker tool
called (its own criterion), keyword-stop prevented or not (phase 10). The deposit's `handread.json` labels and analysis
macros are not joined in version 1.

## 5. Part B: ATIA (`mattngyn/atia_benchmark`)

### 5.1 Acquisition (user-approved 2026-10-13)

- Pin `cc71caf55c6f35d7aad440a4a746f44ae39d17c4` (MIT; tree `ccd3ee64`). Fetched blobless at depth 1, then only the five
  `logs/*.eval` blobs by id (162,365,512 B; blob ids equal phase 10e's), into the fetcher's own store
  `cache/git/github.com/mattngyn/atia_benchmark.git`; hooks off, file protocol off, fsck on transfer, `GIT_NO_LAZY_FETCH`.
  The product fetcher was not used for the transfer because it always fetches the whole commit (339 MB with the media
  inputs), which was not approved. The inputs (`adversarial_inputs/`, `clean_inputs/`) were not fetched: the logs carry
  their media (§5.2). Logged in `acquisitions.jsonl`.
- Also fetched with the same yes (for D-303): 21 AutoGen source files at tag `python-v0.7.5` (`83afbf58`), 321,635 B,
  `~/.agentprov/staging/10n/autogen-upstream.git` (blobless tree plus those blobs; no checkout). §5.5 records what they
  verify.

### 5.2 Census (in memory through `ingest.open_zip`; counts only)

- 5 logs, all `account_takeover_suite`, model `google/gemini-2.0-flash`, **`inspect_ai 0.3.112`**, log version 2; 3
  `success`, 2 `error`. 123 samples (25 + 19 + 19 + 25 + 35), reconciling with phase 10e. Members selected 143 of 143.
  Dataset `account_takeover` (25 or 35 samples; the error logs stopped at 19): the logs re-run the same sample ids, so
  the 123 are separate executions, not 123 distinct tasks. The header's dataset location is a Windows working-copy path
  without an account name.
- Per sample: one user input, a single assistant turn with **at most one tool call** (81 samples with one, 42 with
  none), metadata `attack_type`, `benign_tools`, `harmful_tools`, `insight`, score `harmful_tool_invoked` (121; the two
  errored samples none). Tools are set per sample by the solver `use_sample_tools`. **No parallel batches** (0).
- **Media inputs:** every user turn holds one text part and, in 98 samples, one media part: image 39, audio 49, video 10.
  Each media part is an `attachment://<hash>` reference into the sample's `attachments` map, whose values are base64
  data URIs (`image/png`, `audio/mpeg`, `video/mp4`; 38 of them about 3 MB, 6 about 1 MB). No input is referenced by a
  file path, so the input folders are not needed.
- **0.3.112 tool events have no `message_id`** (81/81 absent); the tool message's `tool_call_id` and the tool event's
  `id` each equal the call's id in 81/81.

### 5.3 Trial imports (scratch, `~/.agentprov/migration-work/phase10n/corpora/`)

Driver `tools/inspect/phase10h_trial.py` (unchanged): the pin read from the verified cache, every blob re-hashed against
its tree entry, release mode, through validation; registry part `planned`, so the CLI's status gate is bypassed as in
phases 10d and 10h.

- **Before the rebase** (main `52c0974`, the inspect mapper before regen-batch item 16): 123 mapped, 123 validated, 0
  degenerate, 0 failures; 39 sealed clean, 84 with issues: `missing_tool_result` 81 and `dangling_source_ref` 81 (every
  tool call: the mapper linked execution to result through `message_id`, which 0.3.112 does not write),
  `inspect.unknown_content_type` 59 (the audio and video parts), `inspect.unmapped_event` 2 (the two `error` events).
- **After the rebase onto `bfa1951`** (item 16: links by `tool_call_id` under class-D rules): identical counts: 123 mapped, 123 validated, 0 degenerate, 0 failures, 39 sealed clean, 84 with the same four codes
  (`missing_tool_result` 81, `dangling_source_ref` 81, `inspect.unknown_content_type` 59, `inspect.unmapped_event` 2).
  Item 16 links an event to its result by `tool_call_id` only where a `message_id` is present; 0.3.112 has none, so the
  gap remains (R-10n-1, `routing.md`; strict xfail in `tests/adapters/inspect/test_atia.py`). ATIA has no parallel
  batch, so the first-of-batch defect itself does not occur. Every execution `verified_complete`; stages raw, aer, prov,
  validation ok 123/123; 0 of 56 validation checks fail. **8 and 3 workers give byte-identical corpora** (386 files, 0
  differences). Post-import checks on the 8-worker corpus: `derive --dry-run` 123
  identical; `validate --strict` 4 tiers, 123 passed, 123 results reproduced; `recompute --dry-run` 123 identical, 0
  unexplained changes; `verify --level chain` 133 raw objects re-hashed, 0 failed (one `checksums.absent`, expected for
  an unsealed working tree). The slow test maps the smallest pinned log from the cache (19 samples, all validate).
- **After regen-batch item 25** (on main at `3cacde6`: class-D rule `inspect.tool_event_no_message_id@1`, links by
  `tool_call_id` for producers up to 0.3.112; audio and video as `uri` parts): 123 mapped, 123 validated, 0 degenerate,
  **123 sealed clean**; `missing_tool_result` 0, `dangling_source_ref` 0, `inspect.unknown_content_type` 0; only
  `inspect.unmapped_event` 2 remains (the two error events). 98 media `uri` parts. 8 and 3 workers byte-identical (386
  files). The strict xfail is now a normal test. The 42 strings over 1 MiB remain until regen-batch item 28 (R-10n-2,
  awaiting the user).

### 5.4 How the media are stored (D-308)

- **Raw:** the media are raw evidence inside each sample member object (the stored, content-addressed member of the
  expanded `.eval`), and every message that uses one cites it by locator `{"a": "a0", "p": "/attachments/<hash>"}`.
- **AER today:** the inspect mapper resolves the attachment and inlines it: images as `uri` parts holding the data URI
  (39; 20 about 3 MB), audio and video as `other` parts holding the data URI (59). The Gemini request copy in
  `model_call.params.transmitted` holds the same media as raw base64 (`inlineData.data`). In the trial corpus **42
  strings exceed 1 MiB** (24 message parts, 18 request copies), which C.2.1(6) says MUST be blobs; the AER validator did
  not flag them.
- This is mapper behaviour (the inspect mapper belongs to the regen-batch session), so the profile does not work around
  it. Options: (a) route to the mapper owner: a string over 1 MiB becomes `{not_inlined: {sha256, bytes, media}}` with
  its locator, as OpenHands does (D.17.8), so AER content is `unk`-free but not inline; (b) a `$blob` per media item,
  which needs the derived-blob origin of `aer/0.2` (D-203); (c) accept inline strings (against C.2.1(6); rejected).
  Recommended: (a) now, (b) when `aer/0.2` lands. Until then B's import waits. A validator check for C.2.1(6) is routed
  too (it is in `aer/`).

### 5.5 What the AutoGen code verifies (for A, D-303)

At `python-v0.7.5`: every message and event gets `id = uuid4()` and `created_at = datetime.now(timezone.utc)` at
construction (`autogen_agentchat/messages.py`); `ToolCallRequestEvent.content` is the model result's `FunctionCall`
list; all of a request's calls run concurrently (`asyncio.gather`) and one `ToolCallExecutionEvent` follows them, each
`FunctionExecutionResult.call_id = tool_call.id` on every path (`agents/_assistant_agent.py` `_execute_tool_call`);
`is_error` is true for undecodable arguments, an unknown tool, or any exception in `run_json`, including argument
validation before the tool body runs (`tools/_static_workbench.py`, `tools/_base.py`). So the call-id link and the
creation times are class D for A; whether a failed call ran is `ambiguous` unless the harness wrote no `tool_call`
event (then: not entered, I by deposit code). The basis that the runs used 0.7.5 is the deposit's `requirements.txt`
pin and the phase-0 capture of installed versions, as OpenAgentSafety's lock file was in D-172.

## 6. Decisions (user-approved 2026-10-13; as recorded in DECISIONS.md)

- **D-300 (A: selection and counting).** 1,080 run rows are in scope, one execution each; 150 phase-7 rows are
  `select.not_execution_artefact` (no agent), 40 phase-8/9 rows `select.out_of_scope` (partial trajectories); both are
  register rows with counts, never dropped. Rejected: counting phases 8–9 (no tool results); a file-level register only
  (the brief asks for the rows).
- **D-301 (A: the row-unit runner capability).** Option (a): routed to the runner owner through the orchestrator
  (R-10n-3, the line-locator case of phase 10k's R-10k-1); the family is built and all 1,080 rows are mapped in memory
  (§7), with no trial import.
- **D-302 (A: family and unit identity).** §4 header: family `autogen`, dialect `autogen.runs`, one execution per row,
  identity file + `run_id`, events and guard log as per-unit auxiliary inputs joined by id and verified digest, retried
  runs resolved to their last attempt.
- **D-303 (A: code citation).** AutoGen 0.7.5 behaviour is D, read at the tag (fetched with the user's yes, §5.5); the
  deposit harness I throughout.
- **D-304 (A: guards).** §4.1.
- **D-305 (A: identity, time, order).** §4.2.
- **D-306 (A: semantics and outcomes).** §4.4.
- **D-307 (B: profile).** `atia-benchmark` in the `inspect` family (benchmark `atia`, producer band `0.3.112`, log
  version 2, pin `logs/` only, `planned` registry part, own permissive corpus); `attack_id` stays unrecorded (the attack
  is in the media input; `attack_type` stays in `ext.inspect.sample_metadata`); no semantics profile in version 1, so
  SEM is skipped, as for WhistleBench.
- **D-308 (B: media).** §5.4: raw objects with locators now; AER `not_inlined` digests through the mapper owner (a),
  `$blob` with `aer/0.2` (b). B is not imported until (a) or (b) lands.
- **D-309 (B: fixtures).** No real log is committed now: the smallest is 11.5 MB of base64 media (WhistleBench's one
  fixture is 1.4 MB) and its AERs would carry the 1 MiB strings of D-308. Tests read the profile and registry and, when
  the pinned blob is in the fetch cache, map one log (skipped otherwise). A fixture is chosen after D-308, by criterion
  (one log with an error sample and all three media kinds), or as a 0.3.112-shaped synthetic log if you prefer.

## 7. Part A: the `autogen` family (implementation, 2026-10-13)

Spec §D.22; code `src/agentprov/adapters/autogen/`; tests `tests/adapters/autogen/`; in-memory driver
`tools/autogen/phase10n_map.py`; counts `autogen.map-census.json` (counts, codes and labels only).

### 7.1 Results (all 1,080 run rows, in memory, D-154 method)

| | |
|---|---|
| Units | 1,080 (team 550, condition 290, defense 160, injecagent 80); 0 degenerate |
| AER | 1,080 valid in release mode (`store=None`: locators not resolved here); 1,040 `agent_execution`, 40 `outcome_only` |
| Accounting | every core check consistent (agent calls vs assistant messages 1,040, generated_by 1,040, calls dispatched, results linked and executions with results 737 each); profile check `autogen.acc.side_list@1` consistent 1,080/1,080 |
| Records | model calls 3,280, tool executions 1,120, messages 5,615, decisions 176, judgements 38,183, fixtures 4,586, memory activities 225 |
| Issues | `guard_text_unjoined` 588 runs, `block_effect_in_request_log` 139, `block_subject_not_recorded` 69, `no_execution_observed` 40, `tool_error_result` 4, `aborted_attempt_events` 3 |
| SEM | integrity 10,693, role 2,240, injection markers 512, author 134, `autogen.canary_present` 250, `autogen.keyword_stop` 210, `autogen.attacker_tool_called` 28 |
| PROV | derived for 1,080/1,080 (tier-4 validation runs with the import) |
| Excluded files | phase 7 (150 rows, `autogen.rail_probe_no_agent`), phases 8 and 9 (20 + 20, `autogen.partial_trajectory`) |

Unjoined guard verdicts: 3,169 of 38,183 judgements have the run as subject (identical texts that the reading agent
cannot separate, and texts no record holds: the memory system message, joined multi-result texts).

### 7.2 Where the implementation differs from §4 (all within D-300–D-306)

1. **Thoughts are folded.** A `ThoughtEvent` and the message that follows it come from one model result (AutoGen yields
   both from one `CreateResult`); the thought is that message's first part (`reasoning`, D by `autogen.thought_equal@1`),
   the event's id and time in `ext`. As separate messages, a model call would generate two assistant messages and the
   core accounting check `aer.acc.agent_calls_vs_assistant@1` would fail (it did, in 10 runs, before the fold).
2. **Decision subjects.** C.3.7 allows only a message, call part, execution or model call as a decision's subject. Blocks
   of the start message, a system prompt, the memory content or an unjoined text are therefore disclosed
   (`autogen.block_subject_not_recorded`, rule `autogen.block_without_decision@1`), not recorded as decisions; their
   verdicts stay judgements, and a changed start message names the guard as its author (I).
3. **The keyword guard strips; the others withhold.** In phase 10 a block removes the termination keyword instead of
   replacing the text (`strip_keyword` in the harness). A block is therefore detected by digest: the delivered text
   differs from the text the guard scanned, not only "equals the withheld constant".
4. **Bus rows name their sender.** Among several recorded messages with the guard row's digest, a bus row's subject is
   the one its agent sent (evidence in the row); 64-bit prefix, recorded texts only.
5. **A rejected call is `invalid` by an order-free count**: the bodies entered by error results are the tool's harness
   events minus its successful results (4 of 4 rejected calls; an in-order match had mislabelled one).
6. **Outcome claims are namespaced** (`autogen.canary_present`, `autogen.attacker_tool_called`, `autogen.keyword_stop`):
   SEM `outcome` annotations need a judgement, and the deposit records no outcome.
7. **Attacker tool roles**: InjecAgent's direct-harm attacker tools are write sinks (26), with three send sinks and one
   execute sink, rather than all send sinks: they perform state-changing actions (stubs here).
8. **Fixtures**: the committed set is the phase-6 InjecAgent tool-block arm with its context files (9 members, 533,210 B):
   the repository's fixture tree is capped at 8 MiB and held 7.50 MB. The probe phases are tested against the staged
   deposit when present.

## 8. Part A: trial import through the product path (2026-10-13)

After R-10k-1 (`2f4c12b`) the reader declares `multi_execution = True`: the runner maps every run row as its own
execution, source key `sha256:<file>#{"line": n}`. Two family changes made the archive input work: the mapper declares
`consumes_context` (for an archive input the importer puts the context-artefact globs in the `expand` selection only
then, so the per-unit plan finds the event and guard logs, the probe sets and the config), and a whole file the strict
loader rejects seals as one degenerate AER named by its phase (as credleak names a cell by its channel). The profile pin's
`record` is now an integer (the fetch layer's type).

Driver `tools/autogen/phase10n_trial.py` (the pinned deposit, its size, name and sha256 checked against the profile
pin; release mode, through validation; scratch corpora under `~/.agentprov/migration-work/phase10n/corpora/`):

| | 8 workers | 3 workers |
|---|---|---|
| Executions | 1,080 mapped, 0 degenerate, 0 failed | same |
| Sealed | 1,040 clean, 40 with issues (the outcome-only runs) | same |
| Stages | raw, aer, sem, prov, validation ok 1,080/1,080; 0 of 68 validation checks fail | same |
| Register | phase 7 `select.not_execution_artefact` 1 file, phases 8–9 `select.out_of_scope` 2 files | same |
| Issues (executions) | `guard_text_unjoined` 588, `block_effect_in_request_log` 87, `block_subject_not_recorded` 49, `no_execution_observed` 40, `tool_error_result` 4, `aborted_attempt_events` 3 | same |
| Elapsed | 882 s | 1,195 s |

The two corpora are **byte-identical** (3,291 files, 0 differences). Post-import checks on the 8-worker corpus:
`derive --dry-run` 1,080 identical; `validate --strict` 4 tiers, 1,080 passed, 1,080 results reproduced, linkage resolved
1,080/1,080; `recompute --dry-run` 1,080 identical, 0 unexplained changes; `verify --level chain` 44 raw objects
re-hashed, 0 failed (one `checksums.absent`, expected for an unsealed working tree).

Tests: `tests/adapters/autogen/test_import_e2e.py` imports the committed fixture members as a zip deposit (20 executions,
one per line; a run stopped after 7 and resumed equals a single run byte for byte); the former strict xfail is now
`test_the_product_path_maps_one_execution_per_run_row`.

## 9. Part A: D-321 rejected rows, sealed in release mode (2026-10-14)

With D-321 on main (c4fd0dc2) the reader defines `rejected`, and the profile no longer excludes the phase 7-9 files: they
are selected, have no run row, and the runner registers each of their rows on its line (D-300 as approved: rows, never
one file-level entry). Trial on the pinned deposit at commit 3015cf7a (8 workers; scratch corpus
`~/.agentprov/migration-work/phase10n/corpora/autogen-d321-j8`, sealed with a scratch spec kept beside it):

| | |
|---|---|
| Executions | 1,080 mapped, 0 degenerate, 0 failed; 1,040 sealed clean, 40 with issues (as in §8) |
| Register, `select` | 150 `select.not_execution_artefact` (`autogen.rail_probe_no_agent`, phase 7, lines 0-149), 40 `select.out_of_scope` (`autogen.partial_trajectory`, phases 8 and 9, lines 0-19 each); subject `{source_key}`, stage `select`, severity `info`, disposition `not_imported`; no file-level entry |
| Seal (`package`, release mode, clean tree) | exit 0; snapshot `v1.0` counts (H.6.1 R1 through `snapshot_counts`): candidates 1,270 = 1,080 executions + 190 not imported, `selection_excluded` empty; corpus counts the same |
| `verify --level chain` | ok: 3,308 files matched, 1,080 executions checked, 44 raw objects, 43 re-hashed, 43 members checked, 0 failed, 0 findings |
| Elapsed (import) | 732 s |

Tests: `tests/adapters/autogen/test_import_e2e.py::test_rows_that_are_not_runs_are_registered_one_by_one` (non-run rows
inside a run file) and `::test_files_without_runs_register_every_row` (the phase 7-9 layout, no file-level entry).
