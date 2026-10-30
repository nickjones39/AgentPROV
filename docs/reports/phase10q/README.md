# Phase 10q: census of memo-ozdincer/agentdojo and the results-container dialect (part A)

Status: part A (census) done; D-470–D-479 and D-510 **approved by the user 2026-10-14** (DECISIONS.md); part B built (§8);
part C scratch trial §9.
Rank 6 of the phase-10e ranking (`../systematic-search/candidates/phase10e-candidates.md` §2, §3.7): 13,264 AgentDojo runs
of circuit-breaker (LoRRA) and baseline defences on Llama-3.3-70B and Qwen2.5-7B, held inside `results/*.json` containers
with attack and model at container level (D-146). Decisions D-470–D-479 and routings R-10q-1–R-10q-4 are reserved
(`tools/reserve_id.py`). Every decision below is a **proposal for the user**.

## 1. Acquisition

- Pin: `memo-ozdincer/agentdojo` commit `7c331d978acca38534a3d42951f28a25ba26901b` (branch `main`, 2026-04-25; phase 10e).
- Fetched on 2026-10-14 with the user's yes through the pinned-fetch path (`agentprov fetch --profile … --pin head
  --allow-network`, a pin-only draft profile that is not committed): 38,403 blobs and 1,001,834,260 bytes, each verified by its git
  blob id, in the bare cache `~/.agentprov/cache/git/github.com/memo-ozdincer/agentdojo.git`. Seven gitlinks
  (`reference/*` submodules: AgentAlign, HarmBench, Meta_SecAlign, ToolSword, AgentHarm, circuit-breakers, inspect_evals)
  are not fetched and hold no runs of this source.
- Licence: MIT (`LICENSE` at the pin, upstream text; phase 10e). Corpus: own permissive (D-144).
- Census scripts and outputs: `~/.agentprov/migration-work/phase10q/census/` (`census1.py`–`census5.py`, `pass1.jsonl`,
  `containers.jsonl`, `run_hashes.json`). Blobs are read with `git cat-file --batch` from the bare cache and parsed with
  `agentprov.ingest.loaders.strict_json_loads`. Nothing is extracted to disk.

## 2. What the pin holds

| Tree part | Files | Status |
|---|---:|---|
| `results/{api_evals, baseline_defenses, baseline_defenses/defenses, comprehensive_eval, full_eval, full_eval/multiturn_eval, multiturn_eval, tokenless_battery}/*.json` and `runs/results/qwen2_5_7b_instruct_eval/*.json` | 156 | **results containers** (`n_results` + `results[]`): the source's runs |
| `results/agentharm_eval/*.json` | 9 | AgentHarm result containers (`task`, `prompt`, `messages`, `tool_trace`, `score`; 201 rows): another format, **lead** (§6, D-477) |
| `results/pre_abstract/**` | 63 | LoRRA training configs, histories and per-sample completion evals (`clean`/`injected`): not agent executions (phase 10e) |
| top-level `traces_*.json`, `qwen_shards/` | 29 | LoRRA training traces (good/bad trace pairs): not executions (phase 10e) |
| `runs/<upstream pipeline>/**` | ~37,000 | byte-identical upstream AgentDojo logs, owned by `agentdojo` (outside the selection) |
| `runs/lorra/`, `.runs_b200/`, `*.md`, `scripts/`, … | | adapter weights, vLLM logs, notes and code: context only |

### 2.1 Containers

- **156 containers, 139 distinct blobs.** `n_results == len(results)` in all 156. Seventeen files under
  `results/full_eval/multiturn_eval/` are byte-identical copies of `results/full_eval/*` (1,558 runs). They share a source
  key with their twins and collapse under H.7.2 (`dedup.collapsed`) with no profile rule.
- **13,264 runs** in the 139 distinct blobs, as phase 10e counted. 13,070 are distinct by JCS. The other 194 are the two
  rollups `results/api_evals/together_benign_benign_combined.json` and `together_melon_benign_benign_combined.json`
  (97 rows each). Every row of each rollup is JCS-identical to a row of its four per-suite files (16 + 21 + 20 + 40).
- **Container keys** (no container holds more than these): `label`, `suite`, `model`, `n_results`, `results`,
  `aggregate`, and the optional `adapter`, `defense`, `attack`, `mode`, `base_url`, `port`, `elapsed_seconds`.
  `aggregate` is a summary the script computes from `results`. No container holds a timestamp, a code version or a
  benchmark version.
- **Writers**, identified by key set against the scripts at the pin (§3):

| Key set beyond `label, model, n_results, results, aggregate` | Runs | Writer |
|---|---:|---|
| `adapter, attack, base_url, defense, port, suite` | 6,279 | `scripts/eval_lorra_multiturn.py` `main()` as at the pin |
| `attack, defense, mode, suite` | 2,191 | `scripts/eval_benign_utility.py` `main()` as at the pin |
| `defense, mode, suite` (benign, no `attack`) | 194 | an earlier `eval_benign_utility.py` |
| `adapter, defense, elapsed_seconds, port, suite` | 2,832 | `scripts/eval_baseline_defenses.py` as at the pin |
| `port, suite` / `adapter, port, suite` / `adapter, defense, port, suite` | 789 / 140 / 629 | earlier `eval_lorra_multiturn.py` (before the `attack` key) |
| `mode` (smoke) | 16 | `eval_benign_utility.py` `run_smoke_test` |

  At least four writer versions are therefore present, and the pin's code is not the code that wrote every container.

### 2.2 Rows

| Row key set | Rows | Producer |
|---|---:|---|
| `user_task_id, injection_task_id, utility, security, duration, classification, messages` | 10,669 | `run_eval` (`eval_lorra_multiturn.py`) |
| the above + `mode, failure_mode, n_assistant_turns, n_total_tool_calls, any_garbled, turns` (attack mode) | 1,900 | `_run_one_attack` (`eval_benign_utility.py`) |
| the same without `classification` (benign mode; `injection_task_id` null) | 679 | `_run_one_benign` |
| the benign set + `suite` (smoke) | 16 | `run_smoke_test` |

- `utility` and `security` are booleans in every row. `injection_task_id` is null in 695 rows (benign mode).
- `turns` holds the script's per-turn summary: `content_preview` (truncated text), `content_length`, `garbling`,
  `n_tool_calls`, `tool_names`, `turn_index`. `classification` is the script's own marker-string heuristic: `label`,
  `is_harmful`, `is_refusal`, `has_attack_initiation`, `tool_calls`, `n_tool_calls`. Both are derived from `messages`.
- **Empty `messages`: 1,038 rows** (974 single-turn, 64 multi-turn), all with `utility = false` and `security = true`. In
  every writer, the only path that yields `messages == []` is the exception handler of `run_single_task`
  (`utility, security, messages = False, True, []`; `eval_lorra_multiturn.py` lines 1453–1455 and 1486–1488,
  `eval_benign_utility.py` lines 378–380 and 486–488). Those outcomes are defaults, not measurements. 134 of the 135
  `melon_aug` rows are such rows. `results/full_eval/FULL_EVAL_RESULTS.md` itself calls one container "broken (…empty
  messages)".

### 2.3 Messages (12,032 rows with messages; the 2 rollups left out)

- Roles `system`, `user`, `assistant`, `tool`. Every non-empty row starts `system, user` and ends with `assistant`.
- `content` is a **string in every message**, and `serialize_messages` maps a null content to `""`. The 282 assistant
  messages with `""` are therefore ambiguous: they may have been null or empty.
- Assistant `tool_calls` entries are `{function, args}` (**no call id**; 68,218 calls), and the key is absent when there
  were no calls. Tool messages are `{role, content, tool_call: {function, args}, error}`; 3,357 also have `raw_output`
  (the tool's return value before formatting, or its `str()` when it is not JSON-serialisable). There is no
  `tool_call_id`.
- **Pairing:** all 34,529 call batches that have tool messages pair positionally. Each result's `tool_call` equals its
  call by function and JCS args, with no mismatches and no count mismatches. 1,920 batches contain two identical calls.
  143 final batches have calls and no tool messages (unexecuted trailing calls). There are no orphan tool messages.
- Tool errors in 4,096 tool messages: AgentDojo runtime texts (`ValueError: …`, `ValidationError: …`,
  `Invalid tool … provided.`).
- System prompts: the script's per-suite `SUITE_CONFIG` prompts, not AgentDojo's default (10,592 "personal
  assistant" and 1,440 "bank assistant"). Spotlighting appends its delimiter sentence.
- **Defence footprints**:
  - 583 MELON blocks (an assistant message with the fixed text `Potential prompt injection detected, stopping
    execution.` and no calls, written by the `MELONDetector` element instead of the model's turn);
  - 4,461 user messages equal to the first (`repeat_user_prompt` 352 and `secalign_sandwich` 4,109, `InitQuery`);
  - 394 tool outputs wrapped `<<…>>` (spotlighting).
- 15,864 assistant texts contain `<function…` tags, the raw completions of the prompting LLM elements
  (`VLLMPromptingLLM`, `LocalLLM`).
- No timestamps anywhere. No injection map: payloads appear only inside tool outputs.

### 2.4 Arms (13,070 runs, rollups excluded)

| Model label (container `model`) | Arms (`defense`; LoRA adapter as model) | Runs |
|---|---|---:|
| local Llama-70B checkpoint on a cluster (path holds an account) | no defence (attacks: absent, `direct`, `ignore_previous`, `important_instructions`, `system_message`, `tool_knowledge`); `secalign`, `secalign_sandwich` (764 each); `melon`, `melon_aug`, `repeat_user_prompt`, `spotlighting_with_delimiting` (135 each) | 5,369 |
| local Qwen2.5-7B-Instruct checkpoints (paths hold an account) | no defence, `tool_knowledge`, `training_format` (benign) | 1,646 |
| `/workspace/models/llama-70b` (no account) | no defence; tokenless attacks `fake_monologue`, `implicit_socratic`, `system_error_trap`, `tk_descriptive`, `tk_no_wrapper` | 720 |
| `meta-llama/Llama-3.3-70B-Instruct-Turbo` (Together API) | no defence (5 AgentDojo attacks, `training_format`, benign); `melon` (`training_format`, benign) | 2,077 |
| LoRA adapters served by name: `cb` (adapter `combined4_mse`), `cb_banking`, `cb_slack`, `cb_workspace`, `mse`, `mse4`, `triplet`, `triplet_v4a` | circuit-breaker/LoRRA arms; attacks `tool_knowledge`, `training_format`, `important_instructions`, the 5 tokenless attacks, absent | 3,258 |

### 2.5 Identity

- **AgentDojo code:** the fork vendors AgentDojo (`pyproject.toml` version `0.1.35`) and changes it (e.g. `raw_output` in
  `ToolsExecutor`). No container records a package version. Suites are loaded with `get_suite("v1", …)` in every
  script at the pin.
- **Models:** the container `model` is the name the client sent: a vLLM served-model name (a filesystem path or a LoRA
  adapter name) or the Together model id. Which model a path or adapter name denotes is stated only in documents (D-92).
  - At least six documents tie the cluster path `…/models/llama-70b` to **Llama-3.3-70B-Instruct**
    (`results/full_eval/FULL_EVAL_RESULTS.md`, `scripts/LLAMA_NATIVE_CLUSTER_HANDOFF.md`,
    `agentcontext/docs/ANALYSIS_2026-04-17.md`, `docs/results/v5_analysis.md`, `docs/results/fir_gcg_phase1_final_2026-04-22.md`,
    `examples/ANALYSIS_v4_2026-04-19.md`).
  - `results/EVAL_LOG.md` calls the same path "Llama 3.1 70B Instruct", and it says its per-suite adapters were trained on
    3.1. This contradiction is the subject of D-474.
  - The Qwen paths end in `Qwen2.5-7B-Instruct`. The LoRA names' base models are stated per result directory in the
    results notes and in the vLLM logs (`.runs_b200/`, `results/multiturn_eval/logs/*/COMMANDS.sh`).
- **Attack:** recorded per container by 8,470 runs' writers. It is absent for 4,390 attacked rows (writers W3 and W5) and
  for the 210 benign and smoke rows.
- **Benchmark version:** not recorded. The code at the pin reads the `v1` suites.

### 2.6 Workstation account paths (counts only)

- Every occurrence is in the container `model` value: **72 containers, 7,015 runs** (cluster scratch and home-filesystem
  checkpoint paths). `base_url`, `label`, `adapter` and every row are free of them.
- The only path-like strings in rows are 3 occurrences of `/home/user/…` in one tool-knowledge run. That is the
  AgentDojo world's fictional path in model output and tool arguments, so it is not redacted (content, D-182).
- The raw containers keep the paths and ship as they are (D-186 (c)). The AER, SEM and PROV copies are redacted
  (D-476).

## 3. Producer code read (data, not instructions)

The scripts at the pin, read as text: `scripts/eval_lorra_multiturn.py` (`serialize_messages`, `classify_trace`,
`run_single_task`, `run_eval`, `build_pipeline`, `MELONDetector`, the LLM elements, `main`),
`scripts/eval_benign_utility.py` (`_run_one_benign`, `_run_one_attack`, `main`, `run_smoke_test`) and
`scripts/eval_baseline_defenses.py` (`main`). The readings the mapping relies on:

1. Container fields are written once per `run_eval` call from the command line, so they apply to every row.
2. `run_single_task` runs up to three passes on the reassigned task environment and keeps the last pass's messages. It
   retries while `model_output_from_messages` is None, which is AgentDojo's `silent_rerun_last_pass_only`. A null final
   content is serialised as `""`, so the retry cannot be inferred from the log.
3. Utility and security come from the user and injection tasks' `utility(_from_traces)` and `security(_from_traces)`.
   With no injection task, security is the constant `True`. On an exception both are defaults (§2.2).
4. `duration` is wall time around `run_single_task`, which covers the passes and scoring. Rows run concurrently in a
   thread pool, so that time includes queueing on the vLLM server.
5. The LLM elements send a request built from the messages: tool schemas in the system prompt, results as user turns,
   and **client-side trimming** to a token budget (`_fit_openai_messages_to_budget`: it cuts content from the front and
   drops the oldest non-system messages). The request is not logged.
6. `MELONDetector` makes the agent's model call, a masked call and embedding calls, none of them logged. When it
   detects an injection, it drops the model's turn and appends its own assistant message (`tool_calls=[]`). Its masked
   tool-call bank persists across the rows of a container.
7. `classify_trace` and `analyze_turns`/`classify_failure_mode` are heuristics over the messages.

## 4. Proposed AER mapping

One AER per row: the located item `/results/<i>` of a whole-file `multi_execution` reader (D-320). The source key is
`{sha256 of the container, {"p": "/results/<i>"}}`. Everything follows D.6.5/D.6.6 except where this table says
otherwise.

| Element | Mapping | Evidence |
|---|---|---|
| header `task` | `suite` (container), `task_id` = `user_task_id`, `attack_target_id` = `injection_task_id`, `attack_id` = container `attack` when the row has an injection task (O); else per D-474; `defense_id` from identity | O / I (identity table) |
| `bench` actor | `name: agentdojo`, `version: "v1"` (I, `get_suite("v1")` at the pin, unverified twin), `unk {"/code": "not_recorded"}`; the system message's supplier is the eval script (I) | I |
| `agent` actor | `model.requested` = the container `model` (O; redacted per D-476); resolved model from the identity table (I, D-92) or `unk not_recorded`; `unk /model/served, /params` | O / I |
| defence actors | `defense` value (O by config); a LoRA adapter served as the model becomes a defence actor named by the adapter (I, identity table) | O / I |
| `run` scope | `t.dur_s` = `duration` (O) under a new duration-scope rule; `unk /t/start, /t/end not_recorded`; container `label`, `adapter`, `base_url`, `port`, `elapsed_seconds`, `mode` in `ext.rescont.container` | O |
| `att0` | `unk {"/index": "lost"}` (`agentdojo.log_holds_last_pass@1`); retry never inferred (§3 item 2) | |
| fixtures | none (no injection map); info issue `rescont.injection_map_not_recorded` | |
| system/user messages | as D.6.6; system actor `bench` under `rescont.system_prompt_from_eval_script@1`; prompt variants pinned by sha256 in the profile | O / I |
| repeated first user message | defence actor (`repeat_user_prompt`, `secalign_sandwich`, `melon_aug`), `copy_of` (`agentdojo.repeat_user_prompt_copy@1`) | I |
| assistant (model) | `mc` + message as D.6.6; `input` = earlier messages at I under a new rule that states the request is built from them, possibly trimmed client-side (§3 item 5); `""` text gets `unk ambiguous`; `<function` tags counted (`local_model_raw_completion`) | I |
| MELON block | `dc` (actor `melon`/`melon_aug`, verdict `terminate`, subject the last `te` or the request message, `unk {"/original": "overwritten", "/reason": "not_recorded"}`), then the message generated by it, actor the defence. The discarded model turn, masked call and embedding calls get no records (one info issue each per file) | I (pattern rule) |
| tool calls/results | `tool_call` parts without `provider_call_id` (`unk not_recorded`); results linked positionally (`agentdojo.positional_match@1`, I; 0 conflicts in the census); `te` status from `error` as D.6.6; `te.returned` = `raw_output` when it is a JSON structure (O), else `unk ambiguous` (it may be a `str()`) | O / I |
| unexecuted trailing calls | issue `unexecuted_tool_call` (143) | D.6.6 |
| judgements | `j0` utility, `j1` security (O, `checker`); benign security `harness_default`; empty-message rows: both `harness_default` (D-475) | O |
| script heuristics | `classification`, `turns`, `failure_mode`, `any_garbled`, `n_assistant_turns`, `n_total_tool_calls` verbatim in `ext.rescont.derived` with their meaning rules cited unscoped. They are not judgements (they are re-derivable and revise nothing) | O |
| empty `messages` | `unit: "outcome_only"`, no `att0`, issue `no_execution_observed` (as D.6.6's `messages == []` row) | |

## 5. Decisions (proposals; D-470–D-479)

- **D-470 (the dialect and reader).** A new dialect `agentdojo.results_container` with a new reader
  `ResultsContainerReader` in a new module `adapters/agentdojo/results_reader.py`. It sets `multi_execution = True`
  (D-320), yields one located item per `/results/<i>` whose value is the whole parsed container (the locator selects the
  row; `ext.rescont.container` keeps the top-level keys except `results` and `aggregate`; D-470 addendum), and checks `n_results` against the list length (an issue on disagreement; 0 observed). Variants by
  row key set:
  - `rc.k7` (the `run_eval` rows);
  - `rc.k12` (the `eval_benign_utility` rows, with or without `classification`, plus `suite` in smoke rows).

  A container that sniffs as the dialect but has an unknown row key set is degenerate (`unsupported_variant`), never
  dropped. Parsing goes through `strict_json_loads`. The largest container is 4.5 MB, so streaming (D-323) is not
  needed.
  - *Rejected:* a TraceLogger variant (the file is not a TraceLogger object, and a whole-file variant cannot yield
    several executions); container mode (D-320 rejected it for whole files).
- **D-471 (one mapper, entered by dispatch).** The rows are mapped by a new build in a new module
  `adapters/agentdojo/results_mapper.py`. It is entered from `TraceLoggerMapper.map` by a dispatch on the item's
  dialect and `accepts` gains the new (dialect, variant) pairs, so the adapter id, version and execution-id prefix stay
  the family's (D.6.5), as for DRIFT (D-270). The two lines in `mapper.py` are a routed edit (R-10q-1, owner: the
  regen-items session, scheduled by the orchestrator after regen-items lands). The registry gains the reader and the
  source registration in this branch.
  - *Rejected:* subclassing `_Build` (owned elsewhere; nearly every step differs); converting rows into TraceLogger
    dicts for `_Build` (the locators would be wrong and absent fields such as `injections`, `error` and
    `pipeline_name` would be asserted).
  - *Alternative for the user:* a separate mapper id `agentdojo.results_container` registered on its own. That needs
    no edit to `mapper.py`, but it departs from the family's single mapper id.
- **D-472 (rules).** A new catalogue `adapters/agentdojo/rules/rescont.rules.toml` (namespace `rescont`, version 1).
  Each rule that reads the fork's scripts is class D, cites `7c331d97`, and has an `_unverified` twin. The profile has
  `verified_code = []` (§2.1: several writer versions, none recorded), so every harness reading is class I and logged
  values stay O. Generic `agentdojo` rules are reused with their twins, and the `agentdojo` catalogue gets no entry. Two
  routed one-line edits:
  - R-10q-2: `citation.NAMESPACES` gains `rescont` (`citation.py`, regen-items);
  - R-10q-3: `aer/rules.py` `CATALOGUE_HOMES` gains `"rescont": "agentprov.adapters.agentdojo"`, a core table that lists
    exactly such out-of-package homes. This is recorded under invariant 5 in AGENTS.md.
  - *Rejected:* new entries in `agentdojo.rules.toml` (they would bump the catalogue version every agentdojo corpus
    cites; the bump belongs to the D-31 branch).
- **D-473 (selection).** One part `head`, one git pin. The include list is the 9 container directories (§2). The two
  rollups `*_combined.json` are `select.not_execution_artefact` with a note (D-191 precedent; all 194 rows are
  JCS-identical to per-suite rows). The 17 byte-identical copies collapse by source key (H.7.2). `results/agentharm_eval/*.json` is
  included and excluded as `select.dialect_planned` (note: AgentHarm containers, another format; lead R-10q, §6), so its
  201 rows are visible in the register. Training traces, LoRRA evals and upstream `runs/` copies are outside the
  include list (not executions; upstream copies owned by `agentdojo`). Context artefacts: `LICENSE`, `README.md`,
  `pyproject.toml`, the three scripts and the results notes cited by the identity table.
  - *Result:* 137 containers, 13,070 executions.
- **D-474 (identity and arms).** An identity table (`tables/memo_ozdincer_containers.toml`) keyed by container label
  (path), never by model id (D-182: a table keyed by the original id would put it into Git). Each row gives:
  - the resolved model and, for LoRA names, the adapter as a defence, each with the document that states it (D-92,
    class I);
  - the attack for containers that do not record one, **only where a document states it** for that container (a code
    default such as `TrainingFormatAttack` is never enough; D-92). Otherwise `task.attack_id` is unrecorded and the
    row keeps `injection_task_id`.

  On the Llama version, the user decides:
  - (a) **recommended:** Llama-3.3-70B-Instruct (six documents), with `results/EVAL_LOG.md`'s "3.1" kept in the row
    note and an info issue `identity_conflict` on the affected runs;
  - (b) `unk ambiguous` for every run on that path (5,369 runs).
- **D-475 (empty `messages`).** The 1,038 exception rows are executions with `unit: "outcome_only"`, as D.6.6 maps
  AgentDojo's empty logs. Both judgements are `harness_default` under `rescont.exception_imposes_outcome@1` (I twin),
  with the issues `outcome_imposed_by_runner` and `no_execution_observed`. Profile quirk
  `rescont.exception_row_defaults` (observed 1,038).
  - *Rejected:* D-321 rejected rows (a run was attempted and has a duration; the family maps such logs); `checker`
    outcomes (the values are defaults, and `security = true` would count as attack success).
- **D-476 (redaction, D-146/D-182 pattern).** A closed `[[family.agentdojo.redact]]` table with the D-182 keys and
  template grammar (`{span12}`, `{leaf}`) and scope `model_id` only. A new module `adapters/agentdojo/redact.py`
  mirrors the D-182 `Redactor`, including BF-21:
  - object keys and JSON-Pointer-escaped forms are covered (`evf`/`unk` keys, scoped rule citations, `ext.lex` key-order
    pointers);
  - it applies wherever the AER holds the container model string.

  Rule `rescont.value_redacted@1` (D); `ext.rescont.redacted` lists `{p, rule}`; one info issue
  `rescont.value_redacted`. The patterns describe structure only (`^/scratch/[^/]+/.*`, `^/mfs1/u/[^/]+/.*`), never an
  account name. The template keeps the checkpoint leaf (e.g. `local:{span12}/llama-70b`). `/workspace/models/llama-70b`
  holds no account and is kept. Raw bytes are untouched and ship as they are (D-186 (c)). `family.schema.json` gains
  the table. Tests assert that no synthetic account token appears in the AER, SEM or PROV bytes in any form (plain,
  pointer-escaped, as a key).
  - *Rejected:* importing `adapters/inspect/redact.py` across families; withholding the 72 containers' executions.
- **D-477 (leads).** The 9 AgentHarm containers (201 rows of `messages` + `tool_trace` on the same models) are outside
  D-144's 13,264 and need another reader. They are recorded here and by `select.dialect_planned`, not screened anew.
- **D-478 (fixtures, 512 KiB budget).** Two real MIT containers without account paths:
  - `results/api_evals/together_test.json` (42,501 B, 9 `rc.k7` rows);
  - `results/comprehensive_eval/smoke_mse4.json` (45,113 B, 8 `rc.k12` rows).

  Neither holds an account path or a secret-like token (scanned). The other cases are built in code with a made-up
  account (D-185 pattern): the redaction, empty rows, MELON blocks, repeated prompts, spotlighting, `raw_output` and
  the rollup exclusion.
- **D-479 (regen-batch entry; digest prediction).** The new modules, the registry entry and R-10q-1/2 move the
  agentdojo family's code digest, and with it the `aer` stage identity (`derivation.json`) of every agentdojo-family
  import made afterwards. They move no AER, SEM or PROV byte of any stored corpus: the dispatch touches only the new
  dialect, and no existing profile declares `redact`. Proof at build time: every agentdojo golden and digest file
  re-maps byte-identically. R-10q-3 moves the `aer` package's code identity in the same way. Entry R-10q-4 in
  `regen-batch.md`, implemented only after the user approves.

## 6. Routed (through the orchestrator)

| Id | What | File (owner) | When |
|---|---|---|---|
| R-10q-1 | `TraceLoggerMapper.accepts` + `map` dispatch to `results_mapper` | `adapters/agentdojo/mapper.py` (regen-items) | after regen-items lands |
| R-10q-2 | `NAMESPACES` gains `rescont` | `adapters/agentdojo/citation.py` (regen-items) | with R-10q-1 |
| R-10q-3 | `CATALOGUE_HOMES["rescont"]` | `aer/rules.py` (core; orchestrator) | with R-10q-1 |
| R-10q-4 | regen-batch entry with the digest prediction (D-479) | `docs/reports/analysis/regen-batch.md` (regen-batch owner) | on the user's yes |

Lead (not routed): an AgentHarm-results reader for `results/agentharm_eval` (D-477).

## 7. Next (part B, after the user's review)

Reader, build, catalogue, redaction, profile with census-backed quirk counts, identity table, registry entry, fixtures,
tests and a D_adapters.md subsection D.6.20, in this branch. Then the routed edits are applied in memory for the scratch
trial (part C) under `~/.agentprov/migration-work/phase10q/` through `tools/suite_queue.py --class import`.

## 8. Part B (built 2026-10-14)

- **Code (new modules in `adapters/agentdojo/`).**
  - `results_reader.py` (D-470) and `results_mapper.py` (`ResultsBuild`, D-471).
  - `redact.py`: the shared family redaction, scopes `model_id` and `pipeline_name` (D-476, D-510).
  - `rules/rescont.rules.toml` (D-472; 38 rules: 18 D rules with their twins, 3 I rules, `value_redacted`).
  - `tables/memo_ozdincer_containers.toml` (D-474; 15 rows).
  - The profile `memo-ozdincer-agentdojo` and the registry source (planned).
- **Edits to existing files.**
  - `mapper.py`: the dispatch (R-10q-1).
  - `citation.py`: `NAMESPACES` (R-10q-2).
  - `aer/rules.py`: `CATALOGUE_HOMES` (R-10q-3).
  - `family.schema.json`: `redact`, plus `container_table` under `identity`.
  - `tests/unit/adapters/test_discovery.py`.
  - The full-corpus census test, which skips this dialect; the dialect has its own.
  - Routing: `routing.md`.
- **Tests and fixtures.** `tests/adapters/agentdojo/test_rescont.py`: 36 tests plus one full-corpus test. Fixtures:
  `tests/fixtures/memo-ozdincer/` (D-478).
- **Census of the pinned snapshot** (`tools/agentdojo/phase10q_trial.py census`; byte-identical copies counted once):

| Measure | Value |
|---|---:|
| containers mapped / rows sealed / degenerate / crashes | 137 / 13,070 / 0 / 0 |
| variants `rc.k7` / `rc.k12` | 10,669 / 2,401 |
| `agent_execution` / `outcome_only` | 12,032 / 1,038 |
| outcomes: utility `checker` / `harness_default`; security `checker` / `harness_default` | 12,032 / 1,038; 11,539 / 1,531 |
| `identity_conflict` (Llama 3.3 vs 3.1, D-474 (a)) | 6,306 |
| `identity_unresolved` (tokenless battery 1,440, `smoke_test.json` 9) | 1,449 |
| attacked rows with an attack from a document (`training_format`) / recorded | all attacked rows; no `rescont.attack_unrecorded` |
| rows redacted / sealed AERs still holding an account path (any form) | 7,015 / 0 |
| MELON blocks; repeated prompts; spotlighted outputs; `raw_output` messages | 583; 4,461; 394; 3,357 |
| unexecuted trailing calls (rows) | 143 |
| system prompts recognised (9 pinned variants) | all |

- **Finding.** `results/MULTITURN_RESULTS.md` l.4 also says "Llama 3.1 70B Instruct". The user's D-474 (a) is
  implemented with both 3.1 notes cited in the table.
- **No document states the version of the vast.ai checkpoint `/workspace/models/llama-70b`.** Its 1,440
  tokenless-battery rows keep the model unrecorded (D-92).

## 9. Part C: scratch trial import (2026-10-15)

- **Run.** `tools/agentdojo/phase10q_trial.py import` (the registry part is `planned`, so the CLI refuses it): the full
  pinned snapshot through `import_source` in release mode up to validation, 4 workers, through `tools/suite_queue.py
  --class import`. The scratch corpus is `~/.agentprov/migration-work/phase10q/trial/corpus.partial` (3.9 GB; never
  under `~/.agentprov/corpora`, never committed).
- **Result.** Exit 0 in 40 minutes. 154 files seen. 13,070 rows mapped, annotated, PROV-derived and validated:
  10,443 sealed clean and 2,627 with issues; 0 degenerate and 0 failed.
- **Selection.** 17 byte-identical copies collapsed (`dedup.collapsed`). 11 files excluded: 9 AgentHarm containers
  `select.dialect_planned` and 2 rollups `select.not_execution_artefact`.
- **Issue counts** equal the census (§8): `identity_conflict` 6,306, `identity_unresolved` 1,449,
  `outcome_imposed_by_runner` 1,038, `rescont.value_redacted` 7,015, `unexecuted_tool_call` 143, and so on.
- **Account-path scan** (`phase10q_trial.py scan`, all 39,372 files of the scratch corpus): 0 derived files (AER, SEM,
  PROV, index) hold an account path in any form; 80 raw-level files do, as D-186 (c) and D-510 allow.
- **`verify --level chain`:** ok. 13,070 of 13,070 executions checked and 154 raw objects re-hashed; 0 failed. The one
  finding is `checksums.absent`, expected for an unsealed working tree.
- **`recompute --dry-run`** (2 workers, 1 h 19 min): 13,070 recomputed and 13,070 identical; 0 changed, 0 unexplained,
  0 failed (deterministic across worker counts: the import used 4 workers).
