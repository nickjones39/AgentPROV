# Phase 10o: gemini-cli event streams of Zenodo 20404563 (census and proposed AER mapping)

Status: **part A (census) done, 2026-10-13; D-330–D-337 user-approved 2026-10-13 (D-334 at class I, no code fetched); part B in progress.** No
`src/` code, profile, fixture or import exists yet. Branch `phase-10o-geminicli` (from origin/main `d67ce49`, after
ingest-formats-2).

Everything in the deposit is untrusted data. The runs are agentic-misalignment elicitations: task files, prompts, tool
outputs and agent text contain adversarial and manipulative content. Nothing was followed, run or extracted; this report
gives counts, key paths and value types only, plus a closed set of identity values (event types, tool names, statuses,
model labels).

## 1. Source and pin

- Record **20404563** (concept 20404562), "RESULTS_raw: Raw rollout bundle for code-agent agentic misalignment benchmark
  (10,000 rollouts, 20 cells)", published 2026-05-27, CC-BY-4.0, `isSupplementTo`
  `github.com/warmjademe/code_agent_agentic_misalignment` (MIT, head `1dec4f17e85c`, 2026-05-27).
- File `RESULTS_raw.tar.zst`, 207,950,011 B, sha256 `f7186010db235cbff10f40c3c2d98208328c6836792973621382b981d0acc3cf`
  (equals the record's `.sha256` file; md5 `c8f46f1e…` as listed). One zstd frame, window 8 MiB, content checksum,
  1,464,483,840 B decompressed (ingest-formats calibration).
- **No new retrieval.** The census read the phase-10e copy in place
  (`~/.agentprov/staging/10e/zenodo_20404563/`, downloaded 2026-10-12 with the user's approval; logged in
  `migration-work/phase10e/calls.jsonl`). The code repository was not fetched: only phase 10e's tree listing (paths,
  sizes, blob ids) was read.

## 2. Method

Five scripts (`~/.agentprov/migration-work/phase10o/scripts/c1`–`c8`, to be moved to `tools/geminicli/` with the family)
read the archive **in memory** through `agentprov.ingest.archives.open_archive` (zstd tar, D-240) and
`agentprov.ingest.loaders.scan_jsonl` / `strict_json_loads` under default `IngestLimits`. Nothing was written to disk
except count tables under `~/.agentprov/migration-work/phase10o/census/`. Secret-like values were matched by pattern and
reported as counts, field paths and sha256 prefixes only.

## 3. Archive layout (63,384 regular members, 12,193 directories, 1,642 GNU long names, no pax header, no finding)

`RESULTS_build/{README.md, cell_summary.csv, manifest.csv}` and `RESULTS_build/cells/<scaffold>__<model>/<mutation>/…`:
20 cells × 500 rollouts; `<mutation>` = `SK-<SKELETON>__m<NN>` (51 skeletons). 10,000 `verdict.json`, one per rollout.

The gemini_cli part (5 cells, 2,500 rollouts):

| Cell | rollouts | `gemini_stream.jsonl` | empty | **non-empty** | no stream file |
|---|---:|---:|---:|---:|---:|
| `gemini_cli__claude-sonnet-4-6` | 500 | 500 | 40 | **460** | 0 |
| `gemini_cli__gpt-5.3-codex` | 500 | 500 | 39 | **461** | 0 |
| `gemini_cli__glm-4.7-probe` | 500 | 500 | 43 | **457** | 0 |
| `gemini_cli__gemini-2.5-pro` | 500 | 454 | 34 | **420** | 46 |
| `gemini_cli__MiniMax-M2` | 500 | 403 | 19 | **384** | 97 |
| **total** | 2,500 | 2,357 | 175 | **2,182** | 143 |

**2,182 reconciles exactly** with phase 10e (D-143). Per rollout directory: `verdict.json`, `final_diff.patch`
(1,073 empty, 14 over 1 MiB), `fs_before.json` / `fs_after.json` (workspace file maps, all under 1 MiB),
`events.jsonl` (the harness's own atoms), `runner_stdout.log`, `runner_stderr.log`; with a stream also
`gemini_meta.json` and `gemini_stderr.log`; 757 have `atoms.flat`.

## 4. The gemini_cli stream (2,182 files, 107,006 events)

Every file is UTF-8 JSONL ending in LF; 0 rejected lines, 0 strict-loader findings, every line an object with `type`
and `timestamp`. The first two events are always `init`, then the user `message`.

| `type` | count | keys (all present unless noted) |
|---|---:|---|
| `init` | 2,182 | `session_id` (2,182 distinct), `model` |
| `message` | 34,804 | `role`, `content` (never empty); `delta: true` on all 32,622 `assistant` events, absent on the 2,182 `user` events (one per stream, always index 1) |
| `tool_use` | 34,281 | `tool_name`, `tool_id`, `parameters` (object) |
| `tool_result` | 34,208 | `tool_id`, `status` (`success` 33,986, `error` 222); `output` (30,895; absent in 3,313 successes); `error {type, message}` (222) |
| `error` | 68 | `severity` (all `warning`), `message`; always before a `result` |
| `result` | 1,463 | `status` (`success` 968, `error` 495), `stats {total_tokens, input_tokens, output_tokens, duration_ms, tool_calls}`, `error {type, message}` (495) |

- **Tools** (`tool_name`): `read_file` 18,706, `run_shell_command` 9,278, `replace` 2,596, `read_many_files` 1,883,
  `write_file` 842, `list_directory` 387, `glob` 386, `search_file_content` 106, `codebase_investigator` 76,
  `google_web_search` 21.
- **Pairing is by id, never by order.** `tool_id` has the form `<tool_name>-<13-digit epoch ms>-<suffix>`; within a
  stream no id repeats, every `tool_result` names an earlier `tool_use` (0 orphans), and 73 `tool_use` events have no
  result: each is the **last event** of its stream (73 streams). Calls run in batches: up to 8 calls outstanding, results
  1–8 events after their call and not in call order.
- **Turn structure.** Whenever assistant text or a `tool_use` follows a `tool_result`, no call is outstanding
  (20,839/20,839); within a block, text never follows a `tool_use` before the results (0 of 2,182 streams). So a stream
  segments cleanly into blocks of `[assistant deltas…][tool_use…]` → results; no event marks a model request.
- **Timestamps:** all 107,006 are UTC `Z` with millisecond precision and non-decreasing per stream; 1,714 streams repeat a
  value. No timezone or clock doubt, but the time is the CLI's *emission* time.
- **Model:** `init.model` is `"gemini-2.5-pro"` in **all 2,182 streams, in every cell** (see §6).
- **Run end:** 1,463 streams end with `result`; **719 end without one** (last event `tool_result` 623, `tool_use` 73,
  `message` 23).
- **`result.stats.tool_calls`** equals the counted `tool_use` events in 1,443 of 1,463; the 20 that differ (by 7–31)
  all used `codebase_investigator` (a gemini-cli sub-agent tool whose inner calls are not in the stream; 9 other streams
  used it without a difference).

## 5. Sidecar files and joins

- `verdict.json` (2,500, one shape): `mutation_id` (equals the directory name 2,500/2,500), `agent` (`gemini_cli`),
  `model` (the cell's model label), `sut_id` (`gemini_cli_{sonnet,gpt53codex,gemini25pro,glm47,minimax}`), `n` (1),
  `n_misaligned` (0/1), `elicited` (382 true; equals `n_misaligned`), `elapsed_sec`, `exit_code` (0 in all 2,500),
  `timed_out` (false in all 2,500).
- `gemini_meta.json` (2,357): `exit_code` (0: 968, **143: 894**, 244: 365, 1: 93, 147: 35, 246: 2) and `elapsed_sec`
  (240 in 882). On the 2,182 streams, exit 0 ⇔ `result success`; 244/1/147/246 ⇔ `result error`; **143 ⇔ no `result`
  event** (719/719). So the verdict's `exit_code: 0` and `timed_out: false` contradict the CLI's own exit code for
  1,214 of the 2,182 runs; neither is reinterpreted (§7 D-335).
- `RESULTS_build/manifest.csv` (10,000 rows, header `agent,model,mutation_id,elicited,timed_out,n_misaligned,
  elapsed_sec,exit_code,diff_bytes,run_id,source_slug`): 2,500 gemini_cli rows, joined 2,500/2,500 on
  (model, mutation_id); `run_id` empty in all; `elicited` 382 (agrees with the verdicts in count; the per-row check is a
  part-B test).
- The user prompt is identical for a mutation across the five models (500/500 mutations, 1 distinct digest each).
- `events.jsonl` (the harness's `trace_to_atom.py` output) is a **derived view**: it renames tools (`Read`, `Bash`, …),
  has `tool_use`, `say` and `result` atoms but **no tool results**, its `tool_use` count equals the stream's in 2,182/2,182,
  and its clock differs from the stream's (offsets 0–147 s). It is not mapped (§7).
- `gemini_stderr.log`: deprecation warnings, `YOLO mode is enabled`, API error stack traces under
  `/usr/lib/node_modules/@google/gemini-cli/`, and 793 `Attempt N failed with status …` retry lines (MiniMax-M2 cell 718
  at HTTP 500). **No gemini-cli version is written anywhere in the deposit.**

## 6. Oddities

1. **Model identity.** The stream's `init.model` is the CLI's configured model name, `gemini-2.5-pro`, in every cell:
   the harness routes the CLI through a LiteLLM proxy or sidecar (`litellm/`, `configs/sut/` in the code repository) to
   the cell's model. The served model is therefore not in the stream. The cell's model is named only by the harness
   (`verdict.model`, `sut_id`, the directory and the manifest, which agree 2,500/2,500). `configs/sut/` at `1dec4f17` has
   no `gemini_cli_glm47.yaml` (only `glm5` files), so the `glm-4.7-probe` cell's route is not in the published code.
2. **Exit status** (§5): the verdict says exit 0 and no timeout for every run; `gemini_meta.json` says 143 (SIGTERM) for
   894 rollouts, 882 of them at `elapsed_sec` 240.
3. **Rollouts without a structured stream** (318): 175 empty streams (no harness events either; `elicited` false in all)
   and 143 without a stream file (MiniMax-M2 97, gemini-2.5-pro 46). Of those 143, 141 have harness `events.jsonl` atoms
   (tool calls without results: a partial trajectory, D-141) and **19 are `elicited: true`**. They are excluded for their
   format, not their outcome; the datasheet must state the elicitation rate of the excluded rollouts (19/318) beside the
   included ones (363/2,182).
4. **Sub-agent calls** (`codebase_investigator`, 76 calls in 29 streams): inner calls unobserved; the CLI's own counter
   shows them in 20 streams.
5. **Hidden retries:** stderr shows failed API attempts the stream does not; model-call counts are inferred.
6. **Secret-like values** (pattern scan of every gemini_cli member; counts only):
   - **One Google-API-key-shaped value** (`AIza…`, 39 characters) in **one** `tool_result.output` of
     `gemini_cli__gemini-2.5-pro` (a `run_shell_command` whose command reads the environment). The same value occurs
     in three `claude_code` `tension__*.json` files and in **no** task workspace (`fs_before.json`), and it is the only
     such value in the archive. It is most likely a **harness credential leaked by the agent**, not a planted fixture
     (D-336).
   - key/secret/password/token assignments (53 distinct; in agent-written code and task files, none in an environment
     dump), e-mail addresses (154 distinct, in task code), private IPv4 (16), one PEM private-key header and one JWT
     (both only in `final_diff.patch`), home paths `/home/ubuntu/` (1,393) and `/home/user/` (1): container users, no
     operator account path.
7. Agentic-misalignment content: prompts and task files are designed to pressure agents; tool outputs include web search
   results (21 `google_web_search` calls).

## 7. Proposed decisions (D-330–D-337; proposals for the user)

- **D-330 Family and identity.** New family `geminicli` (`adapters/geminicli/`), dialect `geminicli.stream_json`, one
  variant `v1` (the event vocabulary of §4; any other `type` is `geminicli.unmapped_event`). Source and profile
  `code-agent-misalignment-geminicli`, corpus `code-agent-misalignment` (D-144), registry part `planned`, pin = the
  Zenodo file (archive input, D-200; top-level tar.zst, RI-3). One execution per non-empty stream member; logical label
  `RESULTS_build/cells/gemini_cli__<model>/<mutation>/gemini_stream.jsonl`; sibling members are per-unit auxiliary inputs
  by role (`verdict`, `meta`, `fs_before`, `fs_after`, `diff`, `harness_events`, `cli_stderr`, `runner_stdout`,
  `runner_stderr`, `atoms`). Task header: `benchmark "code-agent-misalignment"`, `task_id` = `<mutation>`, `suite` =
  `SK-<SKELETON>`, `attack_id` and `defense_id` `not_recorded` (the pressure is in the task design).
- **D-331 Selection and register (D-143).** `[import] include` = the five `gemini_cli__*` cells' streams. Excluded by
  rule, never dropped: the other 15 cells' members `select.out_of_scope` with note "D-143: claude_code, codex_cli,
  openhands parts not readable faithfully (EX-FMT)" (7,500 rollouts); empty streams `select.not_execution_artefact`
  (detail `geminicli.empty_stream`, 175); sidecar members of rollouts without a stream (143) the same, detail
  `geminicli.no_stream` (the 141 `events.jsonl` with calls but no results are a partial trajectory, D-141). Top-level
  `README.md`, `cell_summary.csv`, `manifest.csv` are context artefacts. *Alternative:* map the 318 as `outcome_only`
  executions from their verdicts (as AgentOps' empty traces); rejected because a 0-byte or absent stream is no artefact
  of the dialect and D-143 counts 2,182.
- **D-332 Mapping.** Records: header, actors, scopes, fixtures, then per block (model call, assistant message, then per
  call the execution and the tool message), CLI notices, judgements. Namespace `geminicli`.
  - `user` message (index 1): `message` role `user`, actor `user` (`simulated_user`; text O; actor I
    `geminicli.prompt_harness_authored_unverified@1`).
  - `fs_before.json` → fixture `environment_seed` (content O; join D by sibling path `geminicli.sibling_join@1`).
  - A block = maximal run of assistant deltas and `tool_use` events between results (§4 turn structure): one
    `model_call` (`role: agent`, `status: kept`, `input` = logged prefix, served/usage/params/t `not_recorded`; existence
    I `geminicli.block_is_model_turn_unverified@1`, because retries and requests are not logged) generating one
    `assistant` message: one `text` part = the deltas concatenated in order (D `geminicli.delta_concat@1`; chunk lengths
    and timestamps in `ext` so nothing is lost), then one `tool_call` part per `tool_use` (`name`, `args` =
    `parameters` O; `tool_id` in `ext.geminicli.tool_id`, it is the CLI's id, not a provider's).
  - `tool_use` + `tool_result` with the same `tool_id`: `tool_execution` (actor `env`, `call` = the part; status
    `success` → `ok`, `error` → `error` with `error.type` in `ext`, both O) and a `tool` message whose `tool_result`
    answers the call (`text` = `output`; an absent `output` stays absent, never `""`). The link class is D-334.
  - unanswered last `tool_use` (73): the part stays, no execution, issue `missing_tool_result` and `incomplete_run`.
  - `codebase_investigator`: an execution like any tool, plus `geminicli.subagent_internals_unobserved` (and the counter
    difference, D-335) — the sub-agent is not invented as a scope.
  - `error` event (warning): `activity` `geminicli:cli_notice` (actor `harness`) and `artefact` `geminicli:notice_text`
    (C.3.13: no generic activity generates a message).
  - Everything else (`fs_after.json`, `final_diff.patch`, `events.jsonl`, stderr/stdout logs): kept as raw objects and
    named in `artifacts[]` by role, **no PROV relation** (no evidence of how or when the harness took them); diffs over
    1 MiB are recorded by digest and size only.
- **D-333 Model identity (option (a) recommended).**
  - (a) actor `agent` (`llm_agent`): `model.requested` = `verdict.model` (the harness's cell label; I,
    `geminicli.cell_model_routed_unverified@1`, corroborated D by the directory, `sut_id` and manifest agreeing);
    `model.served` `not_recorded`; `init.model` kept as `ext.geminicli.cli_model` with issue `geminicli.cli_model_alias`
    when it differs (1,762 runs: every cell but gemini-2.5-pro).
  - (b) `model.requested` = `init.model` (O) and the cell label in `ext` only: faithful to the stream but labels 1,762
    runs of four other models as `gemini-2.5-pro`. Not recommended.
- **D-334 tool_id link class and code verification.** The `tool_id` link and the "deltas compose one message" reading are
  gemini-cli behaviour. The deposit names no gemini-cli version. Proposed: cite them at **I** (`…_unverified@1` twins)
  unless the user approves a small fetch: 33 files (81,150 B) of `warmjademe/code_agent_agentic_misalignment@1dec4f17`
  (`agents/gemini_cli/*`, `configs/sut/gemini_cli_*.yaml`, the `litellm/` configs and sidecars, `scripts/build_results.py`,
  `LICENSE`, `Dockerfile`, `requirements.txt`). If the agent Dockerfile pins a gemini-cli version, a second request
  would fetch that version's stream-json and tool-scheduler sources so the D rules can cite them (as D-172). Config files
  may hold credentials: they would be parsed for route and model fields only, never printed.
- **D-335 Run status, time and sidecar disagreements.** `result.status` `success` → run `ok`, `error` → `error` (O,
  `error.type` in `ext`). No `result` event: run `aborted` (I, `geminicli.exit_143_terminated_unverified@1`, from
  `gemini_meta.exit_code` 143), issue `incomplete_run`. Event timestamps stay verbatim in `ext`; executions get
  `t.raw.start`/`end` from their `tool_use`/`tool_result` events and the run its first and last event times, typed slots
  `ambiguous` (emission times; D.16.18 correction 1). `result.stats` → `ext` plus profile check
  `geminicli.acc.counters@1` (tool calls; differences only with a sub-agent). The verdict's `exit_code`, `timed_out` and
  `elapsed_sec` stay in `ext`, with `geminicli.verdict_meta_disagree` when the verdict and `gemini_meta.json` disagree;
  neither is corrected. The harness `events.jsonl` clock is never used.
- **D-336 Withholding the leaked key (D-234).** The profile declares `[withhold]` with one bounded `pattern` rule for the
  Google API key shape (`AIza[\w\-]{35}`), scope `executions`, reason `credential`: the one execution and its stream
  object are withheld from any release (2,181 released). *Alternatives:* (b) keep as published and disclose (option A
  of D-179) — rejected, since unlike OpenAgentSafety's task credentials this looks like a real harness key; (c) redact
  inside the AER — rejected (AER is a faithful mapping; raw bytes are never edited). Other secret-like strings follow
  D-179 option A (kept, disclosed in the artefact catalogue). The deposit is public; whether to tell the depositors is
  the user's call (nothing was sent anywhere).
- **D-337 Judgements.** From `verdict.json`: `elicited` and `n_misaligned`, actor `detector` (`judge`), origin `checker`
  (I, `geminicli.detector_recorded_unverified@1`); values verbatim; no reading assigned beyond the SEM outcome
  `geminicli.misalignment_elicited` (holds iff `elicited`). The manifest row is a D cross-check
  (`geminicli.manifest_agrees@1`).

Semantics profile `geminicli.tools@1` (proposal): `run_shell_command` `execute_sink`; `write_file`, `replace`
`write_sink`; `read_file`, `read_many_files`, `list_directory`, `glob`, `search_file_content` `content_source`;
`google_web_search` `egress_read`; `codebase_investigator` `unknown`; outputs `untrusted`; unknown names fail closed.

## 8. Downstream effects (CLAUDE.md rule 10)

New files and an append-only registry entry only; no change to `aer/`, `prov/`, `validate/`, `corpus/`, `runner/`,
`raw/`, `ingest/` (invariant 5), assuming the runner's sibling auxiliaries work for archive members (checked first in
part B; routed if not). No existing corpus, AER, SEM or PROV byte moves. aer/0.2 merges later and moves every AER pin of
this family (regenerated, never hand-merged). Fixture budget: at most 512 KiB for the source (streams up to 279 KiB, so
fixtures are chosen small, by criterion; the key-bearing run is never a fixture).

## 9. Part B: the family (2026-10-13)

The user approved D-330–D-337 on 2026-10-13 (D-334 at class I: no code was fetched). Built on `phase-10o-geminicli`:

- `src/agentprov/adapters/geminicli/`: reader `GeminiStreamReader`, mapper `GeminiStreamMapper`, rule catalogue
  `geminicli` v1 (38 rules: 9 D, 23 I, 6 reserved; 12 issue codes), semantics `geminicli.tools@1`, profile
  `code-agent-misalignment-geminicli` with the D-336 `[withhold]` pattern rule, `artefacts.toml` (22 entries),
  `family.schema.json`, `ext.schema.json`; registry part `planned` (append only); spec §D.23 (D.19–D.22 are taken by
  phases 10k, 10m and 10n).
- No runner change. Sibling members reach the reader because the profile's `include` selects them for `expand`; a
  rollout without a stream offers its `verdict.json`, which the reader refuses with `geminicli.no_stream`, so every rollout
  is registered. One line of `tests/adapters/runner/test_per_unit_inputs.py` now names the family (as for 10g and 10i).
- Fixtures: 13 rollout directories without their `.log` files (89 byte-identical members, 75,335 B, under the 512 KiB budget; the repository tracks no `*.log`), chosen by
  criterion by `tools/geminicli/build_fixtures.py`. 410 rollouts holding the key shape or a home path were never
  candidates. Tests: `tests/adapters/geminicli/` (49).
- **In-memory mapping of all 2,500 gemini_cli rollouts** (`tools/geminicli/map_census.py`, the product path under member
  origins): 2,182 mapped, 0 degenerate, 175 `geminicli.empty_stream` and 143 `geminicli.no_stream`. Run status ok 968,
  error 495, aborted 719. Issues: `cli_model_alias` 1,762, `verdict_meta_disagree` 1,214, `incomplete_run` 1,214,
  `no_result_event` 719, `cli_error_result` 495, `missing_tool_result` 73, `cli_notice` 68,
  `subagent_internals_unobserved` 73 (76 sub-agent calls, 3 of them unanswered). `geminicli.acc.counters@1`: consistent
  1,443, unverifiable 20 (sub-agent) and 719 (no result). Records: 22,893 model calls, 34,208 tool executions, 59,283
  messages. Every census count of §4–§6 is reproduced. A 1-in-25 sample validated in dev and release mode, with SEM and
  PROV tier 4, before the full trial import.

## 10. Scratch trial import (2026-10-13/14)

`tools/geminicli/trial_import.py import --jobs 4` into `~/.agentprov/migration-work/phase10o/trial/cam-j4.partial`
(offline, from the pinned file in place; release mode through validation; 5,033 s under a machine load of about 32 from
other sessions). Nothing was imported into a real corpus.

- **Import:** 2,500 rollout primaries seen; 2,182 mapped, annotated, derived and validated; 0 failed, 0 degenerate; sealed
  clean 968, with issues 1,214. Index: status `ok` 968, `ok_with_issues` 1,214; every stage `ok` for all 2,182;
  completeness `known_incomplete` 568, `unverifiable` 1,614; 68 validation checks, none failed.
- **Register:** `select.out_of_scope` 7,500 (one verdict per claude_code, codex_cli and openhands rollout);
  `select.not_execution_artefact` with `geminicli.no_stream` 143 (plus 890 rows for their sibling files) and
  `geminicli.empty_stream` 1 (plus its 9 siblings); `dedup.collapsed` 174 (the other empty streams: 0 bytes each, so one
  raw object); README and cell summary 1 each. The 174 collapsed rollouts are registered through their stream; their
  sibling files are stored members without register rows of their own (no rollout is unaccounted for).
- **Issues by run** match the mapping census (§9; the import counts runs, so 73 sub-agent executions are 69 runs).
- **Validate** (`agentprov validate`, dev mode, tiers aer, sem, prov, linkage; 2 h 52 min on one worker): 2,182 passed,
  0 failed; linkage resolved 2,182/2,182.
- **Chain verification** (`agentprov verify --level chain`): 19,111 raw objects re-hashed, 32,831 members checked;
  646 `index.completeness` failures and the working tree's `checksums.absent`. All 646 are the known core defect fixed
  by D-372 (regen-items-2-12, not yet on main): each is an aborted run whose only loss code, `incomplete_run`, rests on the
  class-I rule `geminicli.exit_143_terminated_unverified@1`; the importer counts only D-proven loss (`unverifiable`) and
  `corpus/facets.completeness_of` counts every code (`known_incomplete`). A scratch verify with regen-items-2-12 merged
  locally (never committed) gives 0 completeness failures. Nothing in the family changes for it.
- **Recompute (`--dry-run`)**: started on 2026-10-14 and stopped by this session when the user made performance work the
  priority (no heavy jobs until the orchestrator says otherwise). It is re-run before the full import, never skipped.

## 11. After the rebase on origin/main 0836c766 (2026-10-14)

- Conflicts only in append-only files (DECISIONS.md, the registry, AGENTS.md, D_adapters.md): every side kept; the
  registry is main's plus this family's three entries, with no line of main removed.
- Fixtures rebuilt without the `.log` siblings (the repository tracks no `*.log`): the same 13 rollouts, 89 members,
  75,335 B; within the D-360 caps (`tests/repo/test_fixture_caps.py` passes, no exception needed).
- The withholding e2e test (D-336) passes with the shipped profile: one execution, its stream and the container
  withheld; `verify --level chain --release` passes; no released byte holds the sentinel; the gitleaks control finds it
  in the sidecar only. **Sealing a real corpus of this source waits for D-372**: on current main a seal refuses itself on
  any aborted run (719 here) because its chain check reads the I-class `incomplete_run` as proven loss.
