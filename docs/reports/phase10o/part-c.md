# Phase 10o part C: Qwen Code runs of RedCode-Exec (Zenodo 23168099), census and proposed mapping

Status: **census done, 2026-10-15; D-570–D-578 user-approved 2026-10-15 (D-577 option (b); D-579 reserved); part C-B in progress.** Branch
`phase-10o-qwencode` from origin/main `3a7896d4`. Part C was phase 10g's held part C, reassigned here (orchestrator relay
of the user's release, 2026-10-15). No `src/` code yet.

Everything in the deposit is untrusted data: RedCode-Exec prompts ask agents to run risky code, and outputs echo it.
Counts, key paths and closed identity values only; the deposit's harness code was read as data, never run, with any
credential-like line withheld.

## 1. Source and pins

- Record 23168099, "Which Orders Count? A Behavioral Study of Execution Decisions in Autonomous Coding Agents"
  (replication package), CC-BY-4.0, 2026-10-05. Its OpenHands part is the `redcode-exec-openhands` profile (phase 10g).
- **Runs:** `trajectories_Qwen-qwen3coder.zip`, 9,402,535 B, md5 `e34b6014…` (equals the record), sha256 `2fd0cada…347dc`.
  **No new download:** phase 10e fetched it with the user's approval (`migration-work/phase10e/calls.jsonl`); read in place
  from `~/.agentprov/staging/10e/zenodo_23168099/`.
- **Context:** `agent-execution-decisions-supp.zip` (10,130,955 B), already pinned by `redcode-exec-openhands` (role
  `supp`) and staged by phase 10g: the Qwen scores, the RedCode dataset and generated prompts, the execution rules, and the
  harness code `Qwen_evaluation/` (read, never run).

## 2. Layout (in memory through `agentprov.ingest`; nothing extracted)

`results/Qwen/qwen3-coder-30b-a3b-instruct/<S1|S2|S3>/<python|bash>/trajectory/`: 3,305 members, all `.json`.

| Group | runs |
|---|---:|
| S1 python / S2 python / S3 python | 720 / 720 / 720 |
| S1 bash / S2 bash | 570 / 570 |
| **total** | **3,300** |

Run label `qwen_<scenario>_<payload>[_py|_sh]_S<n>.json` (3,300/3,300 match; the target segment and suffix agree with the
path). Plus five `_full_api_request_sample.json`, one per group (§5).

## 3. The format: not gemini-cli's

The harness runs `qwen --yolo --output-format json --auth-type openai -m <model>` (Qwen Code **0.21.0**, recorded in every
run) and saves the CLI's stdout verbatim per case (`Qwen_evaluation/Qwen.py` `run_eval`). The file is **one JSON array** in
the Claude-Code SDK message shape, not gemini-cli's line-delimited flat events:

| `type` | count | shape |
|---|---:|---|
| `system` | 3,299 | `subtype` `init` (3,295: `session_id`, `cwd` `/app`, `model`, `permission_mode` `yolo`, `qwen_code_version` `0.21.0`, `tools`, `mcp_servers` `[]`, `slash_commands`, `agents`) and 4 sub-agent `task_started`/`task_notification` |
| `assistant` | 17,013 | `message {id, type, role, model, content[], stop_reason, usage{input_tokens, output_tokens}}`; content blocks `text` 10,053, `tool_use {id, name, input}` 6,966 |
| `user` | 6,970 | `message.content[]` blocks `tool_result {tool_use_id, is_error, content}` 6,966; `text` 4 (2 of a sub-agent) |
| `result` | 3,295 | `subtype` `success`, `is_error` false, `num_turns`, `duration_ms`, `duration_api_ms`, `usage`, `permission_denials` `[]`, `result` text, `stats` (per-model `api`/`tokens` and per-source `bySource` counts, per-tool `byName` counts, `files`, `skills`; in all 3,295, added to this census by the bug pass bugpass-new-families, NF-16), `session_id`, `uuid` |

- **No timestamps anywhere.** No user prompt either: the harness sends it on stdin, and the CLI does not echo it.
- **Pairing by provider id:** every `tool_result.tool_use_id` names an earlier `tool_use.id` (0 orphans, 0 duplicates, 0
  unanswered calls; 6,958 results directly follow their call's event).
- **Turns:** each `assistant` event has its own `message.id` (17,013 distinct). Consecutive assistant events between
  results form a block, and `result.num_turns` equals the block count in **3,295/3,295** runs.
- `result.result` equals the last assistant text in 3,295/3,295. `result.usage` equals the summed message usage in 2,444
  runs and exceeds it in 851 (calls the stream does not show; 2 of them with a sub-agent).
- Tools: `run_shell_command` 4,951, `write_file` 1,503, `read_file` 262, `edit` 103, `list_directory` 56, `glob` 55,
  `todo_write` 30, `grep_search` 4, `agent` 2 (a sub-agent). `tool_result.is_error` true 1,495.
- Model: `qwen3-coder-30b-a3b-instruct` in every `init` and message (an OpenAI-compatible endpoint configured by the
  harness's `models.json`; which provider served a run is not recorded).
- Oddity: `init.tools` lists 26 tools plus 35 `computer_use__*` entries (the API sample sends 13), and `agents` lists `general-purpose`,
  `Explore`, `statusline-setup`; only the nine tools above are called.

**Not parseable (5):**
- **4 truncated runs, each exactly 65,536 B** (S1 bash 1, S2 bash 3). The harness's own scorer says its capture
  pipeline cuts output at 64 KiB, and scores those runs on the complete events before the cut.
- **1 empty file** (0 B), whose score record says `timed_out: true` (the harness kills `qwen` after 300 s).

## 4. Scores, prompts and context (supplementary zip)

- `results/Qwen/<model>/<S>/<lang>/conversation_log/index<scenario>.json`: 110 lists of 30 entries
  `{index, last_response_full, score, step_count, exceeded_soft_iteration_cap, used_write_tool, timed_out}`; **joined
  3,300/3,300** by (target, language, `<scenario>_<payload>`). Scores 3: 2,690, 0: 516, 1: 94 (the RedCode scale of the
  OpenHands part); `exceeded_soft_iteration_cap` 942 (a recorded soft cap of 5, not enforced); `timed_out` 1.
- Prompts: S1 from `dataset/RedCode-Exec/*_dataset_json/index<sc>_30_codes_full[_upd].json`, S2/S3 from
  `prompt_generator/output/`, each through the same `/sys/kernel` → `/app/sys/kernel` rewrite as the OpenHands part.
- `OH_evaluation/execution_rules.md` is copied into the container as `/app/QWEN.md`, Qwen Code's project context file.

## 5. Secrets, account paths and the API samples

- No value of a key or token shape in either zip. Run content holds 19 distinct e-mail addresses and 12 key/secret
  assignments (RedCode payload code; kept as published, D-179 option A).
- Account paths: the Qwen part holds no operator account. Its home paths are the generic `/home/user/` (10, in 5
  runs), the container user `/home/node/` (11, in 7 runs) and one eight-character name from the RedCode payload (58,
  in 5 runs; the deposit's RedCode-Exec dataset holds it as a `/home/` path too, 74 times across the supplementary
  zip). Corrected by the new-families bug pass (NF-22); the first census counted only `/home/user/`. The OpenHands part (phase 10g's
  `redcode-exec-openhands`) was checked on the orchestrator's request: apart from the container users `openhands`
  (11) and `user` (1), two names occur, and **neither is an operator account**, so no redact rule is proposed:
  - `username` (a placeholder): 4 times in the `finish` action of one qwen3-coder S2 trajectory (`args.thought`,
    `message`, the model response's `content`) and once in that run's score record `last_response_full`; it would
    reach that execution's AER (assistant text, `ext.openhands.judge`);
  - a five-letter name: once in an agent `run` command of one qwen3-coder S3 trajectory; the same path is in the
    deposit's vendored OpenHands frontend source (`environment/OpenHands/frontend/...`, 4 files), so it comes from
    OpenHands' own code, not from the depositor's machine.
- `_full_api_request_sample.json` (5): a request the harness captured once per group with a fixed dummy prompt and the
  settings file moved aside, to record the system prompt and tool list. Keys `max_tokens, messages (system, user), model,
  stream, stream_options, tools (13)`; no header, no credential.

**Incident (2026-10-15):** while tracing the five-letter name, this session ran `git grep` on phase 10g's blob:none
partial clone of OpenHands 1.5.0 (`staging/10g/openhands-upstream.git`), which lazily fetched 451 blobs (1,182,083 B)
from GitHub without the user's consent before it was stopped. Logged in `~/.agentprov/cache/acquisitions.jsonl`
(consent: none, incident), reported to the user, and not used; the conclusion above rests on the deposit's own files.

## 6. Pins and the import path (routed)

Scores and prompts come from a second pin. Two gaps outside the family: nothing outside `adapters/runner/importer.py` builds
a `ContextTree`, so the CLI never wires a profile's context pins; and a context tree must be a local or git tree, so a
Zenodo zip cannot be one. Routed to the orchestrator 2026-10-15 (it also affects `redcode-exec-openhands`): assigned to the 10i session's D-530
work (branch `phase-10i-context`: an archive download pin as a context tree, and the CLI wiring a profile's context pins).
**The product import of this part depends on D-530.** Until then a family-local, clearly marked trial driver reads the
supplementary zip's members through `agentprov.ingest` (trial and census only, never product code; orchestrator's ruling). The primary pin
is a single file, so the six-same-role-pins limit of the OpenHands part does not apply.

## 7. Proposed decisions (D-570–D-578; for the user)

- **D-570 Placement: a sibling family `qwencode`** (`adapters/qwencode/`, dialect `qwencode.json`, variant `v0.21`).
  The format shares nothing structural with gemini-cli stream-json: one array instead of JSONL, nested provider messages
  instead of flat events, provider tool ids instead of CLI ids, no timestamps, a different `result`.
  *Rejected:* a variant inside `geminicli` (a second reader and mapper under a misleading family name).
- **D-571 Identity and corpus.** Source and profile `redcode-exec-qwencode`, part `qwen3coder`, pin `runs` = the Qwen
  zip, context pin `supp` = the supplementary zip. Corpus `redcode-exec`, shared with the OpenHands part: one corpus per
  source, D-144. Run label facets: target, language, scenario, payload, suffix. Task header: benchmark `redcode-exec`,
  suite = language, `task_id` = `<scenario>_<payload>`, `attack_id` = request type C1/C2/C3 of the target, as for the
  OpenHands part.
- **D-572 Mapping.**
  - `init`: header `ext` (session, cwd, tools, agents, permission mode). Harness actor `qwen-code`, version `0.21.0` (O).
  - A block of assistant events: one `model_call` (I; `num_turns` equals the block count, checked by a profile rule).
  - Each assistant event: one assistant message part sequence. `text` → text part. `tool_use` → tool_call part with
    `provider_call_id` = `id` (O) and args = `input` (O). `message.id`, `stop_reason` and usage → `ext`, with usage also
    on the block's model call (D).
  - Each `tool_result`: a `tool_execution` (actor `env`; status `error` iff `is_error`) and a tool message whose result
    answers the call by `tool_use_id` (link I unless D-574).
  - Sub-agent `system` events: harness activities. The 2 non-sub-agent user `text` events: user messages with
    `unattributed_additional_user_message`.
  - `result`: run status `ok` (D), plus `ext` and the profile checks (final text, turns, usage; the 851 usage excesses
    unverifiable).
  - Times: `not_recorded` everywhere; `duration_ms` in `ext` with the duration slot `ambiguous`.
- **D-573 Prompt, rules and samples.** The joined prompt becomes a `task_prompt` fixture: content O, class I,
  because the trajectory never shows what was sent. `execution_rules.md` becomes an `other` fixture (`/app/QWEN.md`,
  I). The group's API sample is a supporting artefact named by role, with no fixture and no PROV relation: it was captured
  with a different prompt and settings, so it is not this run's request. A `qwencode.user_message_not_logged` issue on
  every run.
- **D-574 Code verification.** The CLI version is recorded (0.21.0). Proposed: class I `_unverified` rules now. A later
  fetch of the `QwenLM/qwen-code` 0.21.0 sources for the JSON output writer could raise the id link and block reading to
  D, as in D-172; that is a download and needs the user's own yes. The harness code in the deposit is documentary evidence
  (agentops D-193 policy).
- **D-575 Model identity.** `model.requested` = `init.model` (O); served `not_recorded`; `message.model` kept in `ext`.
- **D-576 Outcomes.** One judgement per score record: `score` (actor `redcode_qwen_scorer`, origin checker I; a score
  of 1 is `ambiguous`, as for the OpenHands part). `step_count`, `exceeded_soft_iteration_cap`, `used_write_tool`,
  `timed_out` and `last_response_full` go in `ext`. SEM reads score 3 as the attack executed, 0 as not, and 1 as not
  informative (as `openhands.tools@1`).
- **D-577 The six non-runs.**
  - **The 4 truncated runs (option b recommended):**
    - (a) a degenerate AER with `unparseable_artefact` (the runner's default; no new code);
    - (b) map the complete events before the 64 KiB cut through `agentprov.ingest.jsonstream` (declared-array streaming),
      with `qwencode.truncated_capture` and `incomplete_run`. The bytes stay as published; no parser beyond
      `agentprov.ingest` is used.
  - **The empty file:** registered `select.not_execution_artefact` (detail `qwencode.empty_output`; its score says
    timed out).
  - **The 5 API samples:** stored as supporting artefacts, not executions.
- **D-578 Secrets.** No `[withhold]` table: no credential-shaped value. Payload e-mails and keys are kept as published
  (D-179 option A). The fixtures are byte-identical members chosen by criterion, none holding a home path.
- **D-579:** reserved.

## 8. Downstream effects (CLAUDE.md rule 10)

New files and append-only registry entries only (invariant 5). No existing corpus byte moves. The `redcode-exec` corpus
gains a second profile when it is imported (regeneration round). The product import of this part waits for the routed
context-pin fix (§6); until then, scratch trials use a family-local member tree over the supplementary zip.

## 9. Part C-B: the family (2026-10-15)

D-570–D-578 user-approved 2026-10-15 (D-577 option (b)). Built on `phase-10o-qwencode`; spec §D.24 (the ledger tracks
numbered items, not top-level sections, so D.24 was checked free on main rather than reserved).

- `src/agentprov/adapters/qwencode/`: reader `QwenJsonReader` (with the strict-loader salvage of D-577), mapper
  `QwenJsonMapper`, catalogue `qwencode` v1 (35 rules), semantics `qwencode.tools@1`, profile `redcode-exec-qwencode`,
  `artefacts.toml` (16 entries), `family.schema.json`, `ext.schema.json`; registry part `planned` (append only); README
  tables regenerated (`tools/readme_corpora.toml` entry: 3,300 runs).
- **D-577 implementation note.** `agentprov.ingest.jsonstream` is fail-closed (a defective document yields nothing), so it
  cannot salvage a cut array. The reader instead parses `prefix + "]"` with `strict_json_loads` for each candidate `}`
  from the end, at most 4,096 tries; only a prefix ending on a complete top-level element can parse. Recorded in
  DECISIONS D-577. *Amended by regen items 120-121 (bug pass bugpass-new-families, NF-14/NF-15):* only a capture cut
  (exactly 65,536 bytes, strict error `ingest.json.syntax` at the end of the input) is salvaged, every other rejection
  is a degenerate AER, and the boundaries come from one forward pass plus one strict parse of the kept prefix (D.24.2).
- **D-571 amended (user decision 2026-10-15, relayed by the orchestrator):** separate corpora per agent,
  `redcode-exec-qwencode` beside `redcode-exec-openhands`; cross-agent comparison is an analysis step.
- **Fixtures:** 7 runs and the 12 supplementary files they need (19 byte-identical members, 782,631 B), chosen by a
  cost-aware set cover over 15 criteria. Each run needs its scenario's score file and RedCode request file (24–270 KB), so
  the source has a recorded D-360 exception of 800 KiB in `tests/FIXTURES.json`.
- **In-memory mapping of all 3,300 outputs** (`tools/qwencode/map_census.py`, product path, member origins, the
  supplementary zip under `supp:` references): 3,299 mapped, 0 degenerate, 0 writer errors; 1 `qwencode.empty_output`.
  Every run's plan names its score, request, rules and API sample (S1 1,290, S2/S3 2,010). Run status `ok` 3,295, not
  recorded 4 (the salvaged outputs: `qwencode.truncated_capture`, `qwencode.no_result_message`, `incomplete_run`,
  `missing_tool_result` 4 each). Checks: turns consistent 3,295; usage consistent 2,444, unverifiable 851 (calls not
  logged). Sub-agent messages in 6 records of 2 runs. Records: 10,266 model calls, 6,971 tool executions, 17,241
  messages, 6,598 fixtures, 3,299 judgements. A 1-in-20 sample (164 runs) validated in dev and release mode, with SEM and
  PROV tier 4.
- Tests `tests/adapters/qwencode/` (44, with the locator-resolution test of §10); the two runner family-list tests
  name the family; the pre-check's recipe test lists the part as awaiting its recipe (D-530).

## 10. Scratch trial import (2026-10-15)

`tools/qwencode/trial_import.py` (trial only) through `tools/suite_queue.py --class import --cpu 2`, release mode through
validation, both zips checked against the profile's pins, the supplementary zip as the `supp` context tree (§6). Profile
`redcode-exec-qwencode` v1. The corpus is scratch only (`~/.agentprov/migration-work/phase10o/partc/trial/`), never a
real corpus; reports hold counts and codes only.

- **First run (`qwen-j2`, 2 workers, 789 s): exit 1.** 3,300 seen, 3,299 mapped, 3,295 validated; the 4 salvaged outputs
  failed validation with `aer.locator.dangling` in the evidence-linkage tier. A salvaged file is not valid JSON as a
  whole, so an array pointer into it cannot be resolved against the stored bytes.
- **Fix (57288413):** a salvaged output's messages are cited by byte-range locators (`{"a", "bytes": [start, end], "p"}`,
  C.9.1), each span checked to parse strictly to its message (recorded in D-577); a test resolves every locator of every
  fixture run against the stored bytes.
- **Re-run (`qwen-j2b`, 2 workers, 1,090 s): exit 0.**

| Counter | Value |
|---|---:|
| seen | 3,300 |
| mapped, annotated, derived, validated | 3,299 |
| failed, degenerate, excluded, duplicates | 0 |
| sealed clean | 3,295 |
| sealed with issues | 4 |
| not an execution (`select.not_execution_artefact`, the empty output) | 1 |

  - Validation: 72 checks, 0 failed; every execution `raw`, `aer`, `sem`, `prov` and `validation` ok.
  - Status `ok` 3,295 and `ok_with_issues` 4; completeness `unverifiable` 3,295 and `known_incomplete` 4.
  - Issues: `qwencode.user_message_not_logged` and `accounting_unverifiable` 3,299 each (by design: stdin and per-call
    accounting are not logged); the 4 salvaged outputs carry `qwencode.truncated_capture`, `qwencode.no_result_message`,
    `incomplete_run`, `missing_tool_result` and `accounting_inconsistent`; `qwencode.subagent_event` and
    `unattributed_additional_user_message` 2 each.
- **Not done here:** sealing, chain verification and `recompute --dry-run` on a real corpus wait for the product import,
  which depends on D-530 (context pins). No data was excluded for its outcome.
