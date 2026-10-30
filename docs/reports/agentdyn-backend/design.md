# AgentDyn live backend (`backends/agentdyn`): design note

Session: AgentDyn backend (worktree `agentdyn-live-backend-354f92`), base: integration head `3f204611`
(`integration/pre-round-2026-10-21`). Date: 2026-10-22. Status: **design only, for decision; no code yet.**
Decisions reserved: **D-680..D-689** (`tools/reserve_id.py`). Orchestrator: "Phase 8 setup".

The goal (user decision, 2026-10-22) is to run AgentDyn live from its own pinned code, as a third execution backend
`agentdyn` next to `agentdojo` and `autodojo`. It answers `hello`, `plan` and `catalogue` like the others, so the GUI's
Backend picker (D-652) can offer it.

How the facts below were obtained. Everything was read offline, with no network access:

- AgentDyn's source at `5353cf76` came from the verified bare fetch cache
  (`$AGENTPROV_HOME/cache/git/github.com/SaFo-Lab/AgentDyn.git`, acquired 2026-10-08, authenticated by the commit id).
- AgentDyn's commit history came from the blob:none history clone `staging/10j/agentdyn-history` (fetched 2026-10-14),
  read with `GIT_NO_LAZY_FETCH=1` and trees only.
- The AutoDojo fork `aa458794` and stock `agentdojo` 0.1.35 were read from the installed files of the two built
  environments (`envs/autodojo-aa458794`, `envs/agentdojo-79922295`).
- The comparisons use git blob SHA-1 per file and an AST digest per top-level function, class or method. Nothing from
  AgentDyn's repository was executed, and its README, CLAUDE.md and other docs were treated as data.
- One `uv lock --offline` trial ran in the session scratchpad. It built AgentDyn's metadata with the cached
  `hatchling`; AgentDyn declares no build hooks.

---

## 1. The pin and the install (D-680, D-681)

### 1.1 Which commit: `5353cf7615b135cace8d07c8f12dac53a16b6db3` (recommended)

- It is the source profile's pin (`agentdyn.profile.toml`, part `a`). Live sessions and the imported `agentdyn`
  corpus would then name the same upstream commit. The system-prompt digests the profile verified at this commit
  (`auto_complete_line` `21a1c00d…`, `auto_complete_line_spotlighting` `1f396c99…`) apply unchanged.
- It is the newest commit we know of. In the 2026-10-14 history fetch, `refs/heads/main` was `5353cf76`
  (2026-05-19, "update README.md"). It changes only `README.md` relative to its parent `2c99edcb`. The last code
  change is the GitHub injection-task fix for upstream issue #6 (`ae6513a8`, `1a6d11d5`, `2c99edcb`, all 2026-05-02),
  which touches only `default_suites/v1/github/injection_tasks.py`. The pin therefore carries the fixed GitHub IT1
  checker (PC-05, `agentdyn.art.github_it1_checker_prefix`).
- The repository has no tags or releases.
- **Optional check (needs a yes):** a `git ls-remote https://github.com/SaFo-Lab/AgentDyn` (a few KB) would show
  whether `main` has moved since 2026-10-14. If it has, I would report the new commits and their paths before
  anything changes. The pin stays `5353cf76` unless the user decides otherwise.

### 1.2 How it installs

`backends/agentdyn/` is a separate uv project, a copy of the `backends/autodojo` pattern (D.11.2):

```toml
[project]
name = "agentprov-backend-agentdyn"
requires-python = "==3.12.*"
dependencies = ["agentprov-capture", "agentprov-backend", "agentdojo"]   # agentdojo = AgentDyn, from git below

[tool.uv]
package = false
required-version = ">=0.12.22"
exclude-newer = "2026-10-07T00:00:00Z"        # the same fixed timestamp as the other two backends (G.7.1(4))
environments = ["sys_platform == 'darwin'", "sys_platform == 'linux'"]
override-dependencies = [                     # D-681(c): declared but imported by no module outside defenses/
  "cyclopts; sys_platform == 'never'", "pydantic-ai; sys_platform == 'never'", "tiktoken; sys_platform == 'never'",
  "vertexai; sys_platform == 'never'", "jsonref; sys_platform == 'never'", "openapi-pydantic; sys_platform == 'never'",
  "json-repair; sys_platform == 'never'",
]
no-build-package = [ …every registry package in the lock… ]   # wheels only; agentdojo itself is built from git

[tool.uv.sources]
agentprov-capture = { path = "../../capture" }
agentprov-backend = { path = "../shared" }
agentdojo = { git = "https://github.com/SaFo-Lab/AgentDyn", rev = "5353cf7615b135cace8d07c8f12dac53a16b6db3" }
```

- **(a) Git source.** The source is the canonical URL with the full 40-hex rev and no `subdirectory`: AgentDyn's
  `pyproject.toml` is at the repository root and builds `src/agentdojo` with `hatchling`. The build backend runs no
  upstream code, because the repository declares no hatch build hooks. `hatchling` 1.32.x is already in the uv cache.
  The environment is `agentdyn-5353cf76`; `commit8` comes from the fork commit, as for AutoDojo.
- **(b) Python 3.12.** The same as the other backends. AgentDyn asks for at least 3.10, and its pyright target is
  3.10. `agentprov-capture` needs at least 3.12.
- **(c) Dependency set and lock.** The project has its own `uv.lock`. AgentDyn's own `uv.lock` is **stale** (finding
  F-7). It locks only the 14 dependencies inherited from AgentDojo 0.1.35, and it lacks the 7 that AgentDyn's
  `pyproject.toml` adds: `cyclopts`, `pydantic-ai`, `tiktoken`, `vertexai`, `jsonref`, `openapi-pydantic` and
  `json_repair`. A static import scan of `src/agentdojo/**` at the pin (outside `defenses/`) finds none of the 7
  imported. Only the refused CaMeL defence uses some of them. I therefore propose to override them out, with
  `environments` keeping the impossible-marker override resolvable.
  - **Offline trial result:** with this configuration, `uv lock --offline` resolves 75 packages **entirely from the
    uv cache**. The third-party versions equal those of `backends/agentdojo/uv.lock` (openai 3.26.0, anthropic
    1.11.0, google-genai 2.28.0, deepdiff 9.1.0, …); only the dev group and two platform-marker packages differ. The
    recording transport is therefore exercised against the same SDK stack as in the two existing environments.
  - **Alternative:** install the full declared set. Six of the seven packages are not in the uv cache, and
    `vertexai` and `pydantic-ai` pull large trees (estimated 80–200 MB of wheels; the exact figure is known only after
    an online `uv lock`). That would add packages no recorded code path imports.
  - **To verify at build time:** that `uv sync --locked --no-config` still honours `override-dependencies` and
    `environments`, which are workspace fields. If it does not, `envs.uv_sync_argv` passes them explicitly, as it
    already does for `exclude-newer` (M.1.7 note).
- **(d) No-build list.** `no-build-package` is derived from the lock (every registry package; G.7.1(5)), as in
  `backends/agentdojo`. `agentdojo` is the only source build. `tests/security/test_supply_chain.py` gains the
  project.

### 1.3 What has to be downloaded (the user's yes, with the size)

| What | From | Size | Needed for |
|---|---|---|---|
| AgentDyn repository at `5353cf76` (uv's own git fetch into the uv cache) | `https://github.com/SaFo-Lab/AgentDyn` | **about 70 MB** if uv fetches depth 1 (measured: our depth-1 copy of the same commit is 72 MB, `runs/` being 598 MB unpacked). It can be more if uv fetches history (19 commits, with `runs/` rewritten several times). I will watch the transfer and stop at 500 MB if it goes beyond that. | `uv lock` and `backends build agentdyn` |
| PyPI packages | — | **none** with the D-681(c) override (offline trial above); 80–200 MB (estimate) without it | — |
| `git ls-remote` (optional, §1.1) | GitHub | a few KB | only to check that the pin is still the head |

**Offline alternative (no GitHub transfer):** serve uv's fetch from the verified local bare cache through a scratch
`GIT_CONFIG_GLOBAL` with `url.<file copy>.insteadOf = https://github.com/SaFo-Lab/AgentDyn`. The bytes are
authenticated by the same commit id, and PEP 610 still records the canonical URL. I do not recommend it: the recorded
URL would then not be where the bytes came from, and the build would depend on a git configuration trick that
`backends build` does not otherwise use. If the user prefers zero network access, the marker can record it.

After the one consented fetch, everything later (the lock, `backends build agentdyn`, `--offline-check`, tests) runs
offline from the uv cache.

---

## 2. Identity (D-682)

AgentDyn calls itself **`agentdojo` 0.1.35**, as AutoDojo and PyPI do. Identity therefore never comes from the
version string; it always comes from the observed commit and the digests:

- **PEP 610.** T0 requires the installed `agentdojo` dist-info `direct_url.json` to be `{"kind": "git", "repo":
  "https://github.com/SaFo-Lab/AgentDyn", "commit": "5353cf76…"}`, with no subdirectory (`envs.pinned_source`,
  unchanged code: the subdirectory is already optional). Any other source is `IdentityMismatch` (exit 3), at build,
  at `--offline-check` and at every run.
- **RECORD and guarded files.** T0 verifies the full RECORD, as for every backend. Guarded names: the base
  `GUARDED_NAMES` all exist in AgentDyn. `ToolsExecutor.query`, `TraceLogger.log/save`,
  `FunctionsRuntime.run_function` and `TaskSuite.run_task_with_pipeline` are **AST-identical to stock 0.1.35**, so
  the executor-mirror AST guard passes. The extra list `AGENTDYN_GUARDED_NAMES` adds the code that differs from stock
  and bears on the recording:
  - `openai_llm._supports_temperature`;
  - `agent_pipeline.AgentPipeline.from_config`;
  - `agent_pipeline.load_system_message`.

  `FORK_GUARDED_MODULES["agentdyn"]` adds `agentdojo.agent_pipeline.agent_pipeline`.
  `openai_llm._message_to_openai`, `_openai_to_assistant_message`, `chat_completion_request`, `benchmark.run_task_*`
  and `task_suite.model_output_from_messages` differ from stock but are already in the base list.
- **`hello` identity.** The expected values are confirmed at build and pinned by test:
  - `default_system_prompt_sha256 = 21a1c00db164a6d5d9d456be30eea3ed23bc11e6a89af0f56b8098d1f9ee3e36` (AgentDyn's
    default, i.e. AgentDojo's plus "Complete all tasks automatically without requesting user confirmation.").
    AutoDojo reports `a021a92b…` (AgentDojo's default; F-1).
  - `benchmark_version` `v1.2.2`; `suite_set` the 7 suites (§3).
  - `tool_definitions_sha256` over all 7 suites.
- **Sessions.**
  - `session.start.backend.id = "agentdyn"`.
  - `identity.benchmark = {name: "agentdojo", dist: "agentdojo", dist_version: "0.1.35", repo:
    "https://github.com/SaFo-Lab/AgentDyn", commit: "5353cf76…", system_prompt_sha256, tool_definitions_sha256}`.
  - The mapper's `agentdojo.capture_backend_identity@1` checks `repo` and `commit` against the `agentdyn-live`
    profile pin. A session never reads as "agentdojo 0.1.35" alone, because the backend id, the repository and the
    commit are all recorded.
- **Backend selection.** `runner.select_backend` picks `AgentDynBackend` when the installed source's repo is
  AgentDyn's URL (the AutoDojo case unchanged). `AgentDynBackend.identity()` refuses any other commit.
- **Refusals (worker and T0).**
  - `llm_element = gateway_compat` is refused: the port binds to private helpers whose AgentDyn versions differ (as
    for AutoDojo, AD-09).
  - Every defence is refused (`defended pipelines are refused in v0.1`, unchanged). This covers AgentDyn's own
    `camel`, `drift`, `progent`, `piguard_detector` and `prompt_guard_2_detector`, which replace pipeline
    components, add `sys.path` entries or need GPU weights.

---

## 3. Suites and attacks: AgentDyn at `5353cf76` against AutoDojo's copy (D-687 findings)

### 3.1 What the AgentDyn catalogue will report (static count, confirmed by the worker's `catalogue` at build)

At `v1.2.2`, AgentDyn registers 7 suites:

- the 4 AgentDojo suites: 97 user and 35 injection tasks. Every file is a byte-identical blob of stock 0.1.35;
- `shopping`: 20 user and 9 injection tasks;
- `github`: 20 user and 9 injection tasks;
- `dailylife`: 20 user and 10 injection tasks.

That is **7 suites, 157 user and 63 injection tasks**. Two injection tasks in `shopping`, three in `github` and one
user task in `github` are commented out upstream. Like AutoDojo, AgentDyn registers its three suites under every
version key from `v1` to `v1.2.2`. **Attacks: the stock 17 (5 DoS).** `attacks/*.py` is identical to stock;
AutoDojo has 20.

### 3.2 Comparison by digest (AgentDyn `5353cf76` against AutoDojo `aa458794`)

| Part | Files | Identical blobs | Difference |
|---|---|---|---|
| `shopping` code (`__init__`, `task_suite`, `user_tasks`, `injection_tasks`) | 4 | 3 | `injection_tasks.py`: **all 9 `ground_truth()` rewritten by AutoDojo** (2026-06-14 note); `GOAL` and `security()` AST-identical (F-2) |
| `github` code | 4 | 4 | none (both carry the #6 IT1 fix) |
| `dailylife` code | 4 | 4 | none |
| suite data `data/suites/{shopping,github,dailylife}/**` | 28 | 27 | one AgentDyn-only stray file `shopping/environment——.yaml` (em dashes), never loaded (`TaskSuite` reads `environment.yaml`) (F-4) |
| tool clients `default_suites/v1/tools/**` | 20 | 20 | none (as regen item 27 found for its tables) |
| AgentDojo suites (workspace, travel, banking, slack) | — | — | AutoDojo edits three workspace injection checkers (v1_2 IT10, v1_2_1 IT11 and IT12: non-string attachments filtered) that AgentDyn and stock leave unchanged (F-6; this concerns `autodojo · live`, not AgentDyn) |

Tool definitions follow from the identical tool modules. As an executed check, the `catalogue`/`hello` tests compute
per-suite tool-definition digests in both built environments, so the identity is shown by execution too, not only
by blob (§6, T5).

### 3.3 Findings (each to be recorded; D.15 entries proposed in §4.4)

- **F-1 System prompt.** AgentDyn's default system message is AgentDojo's plus "Complete all tasks automatically
  without requesting user confirmation." (`21a1c00d…`; 32,063 of the imported variant-A logs carry it). AutoDojo
  sends AgentDojo's default (`a021a92b…`). **AgentDyn suites run through AutoDojo are therefore not AgentDyn's
  configuration.** Any comparison of AutoDojo-run AgentDyn cells with AgentDyn's published numbers must say so. This
  is the strongest reason for this backend.
- **F-2 `shopping` ground truths.** AutoDojo replaced the 9 `send_money(recipient="")` stubs with the real attacker
  actions. `ToolKnowledgeAttack` builds its payload from `injection_task.ground_truth()`, so **`tool_knowledge` payloads
  on `shopping` differ between the two backends**. The checkers do not differ. Other attacks are unaffected.
- **F-3 The three suites are otherwise identical** in code, data and tools (table above).
- **F-4** A stray `shopping/environment——.yaml` is in AgentDyn's tree and wheel. It is inert.
- **F-5 Harness differences** (code, not suites; each one is visible in a capture):

  | Behaviour | stock 0.1.35 | AutoDojo `aa458794` | AgentDyn `5353cf76` |
  |---|---|---|---|
  | temperature 0.0 | not sent (`or NOT_GIVEN`) | sent | sent, except for models starting `o1`/`o3`/`o4`/`gpt-5` (not sent) |
  | system role | `developer` | `system` | `developer`, except `system` for model `qwen3-max` |
  | tool-call arguments that are not JSON | exception | re-request, up to 3 (`_request_and_parse`) | **the call is silently dropped from the assistant message** (`_openai_to_assistant_message` swallows the error) |
  | `JSONDecodeError` in a task | escapes | `error_type`, security False | caught: utility False, security True, logged as `error` |
  | run error security | True | False (+ `error_type` key) | True (no extra key) |
  | `model_output_from_messages` | last message must be the assistant's | as stock | the last assistant message anywhere |
  | `ToolsExecutionLoop.max_input_tokens` | — | present | — (stock) |
  | suites at v1.2.2 | 4 | 17 | 7 |
  | attacks | 17 | 20 | 17 |
- **F-6** AutoDojo's workspace checker edits (table above). These are routed to the `autodojo-live` artefact
  catalogue, not to this backend.
- **F-7 Upstream lock stale** (§1.2(c)). `uv sync --locked` on AgentDyn's own project cannot reproduce its declared
  environment.
- **F-8 Wheel content.** The built wheel carries `defenses/`:
  - CaMeL;
  - DRIFT with its **949 vendored DRIFT run logs** (owned by `drift`, E09);
  - Progent with a vendored AgentDojo 0.1.29;
  - 8 committed `cpython-311` `.pyc` files, inert on 3.12.

  None of them is imported for an undefended cell (shown by a `sys.modules` audit in T4). The DRIFT logs inside the
  environment are never evidence and never ingested.

---

## 4. Mapping, registry, profile and caveats (D-683, D-684, D-685)

### 4.1 The shared `agentdojo.capture` mapper maps these sessions without code change, with one exception

- **Profile choice.** It comes from `session.start.backend.id` through `registry.BACKENDS` (data).
- **Identity check.** It is profile pins (data).
- **Benchmark labels.** `shopping`, `github` and `dailylife` → `agentdyn` come from the profile's suite map
  (`agentdyn.suite_benchmark@1`, regen item 27(a), on main); the AgentDojo suites map to `agentdojo`. With
  `agentdojo.suites@3`, AgentDyn's tools are labelled (item 27(b)), so **R-9b-2 is already resolved** and simply
  applies to `agentdyn-live`.
- **Instrumentation ids** are profile data (`instrumentation_accepted`/`_extra`), not rules.
- **Run-error outcome.** It is the profile quirk params `utility = false, security = true`, with no `extra_key`
  (AgentDyn's TraceLogger is stock), as the `agentdyn` import profile has them.
- **Retry semantics.** `agentdyn.last_assistant_content_none_max3` applies (already supported by the TraceLogger
  mapper for the native log, live-versus-native).
- **Exception: dropped malformed tool calls (F-5, D-685).** If the model returns a tool call whose arguments are not
  JSON, the wire reply lists it and the pass recorder's message does not. `_reply_agrees` then fails, and the mapper
  reports `agentdojo.capture_reply_mismatch` (the reply is appended unmatched). That is reported, not silent, but it
  names the wrong cause: a harness behaviour reads as a capture defect. Options:
  - (a) accept it in v0.1, add a scripted test that pins the issue, and add a D.15 entry;
  - (b) a profile-gated recognition in `capture_mapper.py`: when the profile declares the quirk
    `agentdyn.malformed_tool_call_dropped`, wire calls whose arguments do not parse are listed as not dispatched, and
    the rest are matched. This needs a new rule `agentdyn.malformed_tool_call_dropped@1`, catalogue `agentdyn` v3 (v2
    archived).

  **Recommended:** (a) now and (b) on the held class-1 branch, decided after the scripted session S4 (§6) shows the
  actual mapper output. (b) is class 1 and does not touch `aer/`, `prov/`, `validate/` or `corpus/` (invariant 5
  holds).

### 4.2 Backend-side instrumentation (class 0, `backends/shared`)

`AgentDynBackend` drops `agentdojo.temperature_not_transmitted@1` and `agentdojo.http_backoff@1`'s AutoDojo wording, and
declares the stock behaviour of AgentDyn's harness:

- `agentdyn.temperature_transmitted@1`, with the model-prefix exception in `params`;
- `agentdyn.system_role_for_qwen3_max@1`, only when the requested model is `qwen3-max`;
- `agentdyn.malformed_tool_calls_dropped@1`;
- `agentdyn.json_decode_error_imposes_outcome@1`;
- `agentdyn.model_output_last_assistant@1`.

All are `harness_policy`, as for AutoDojo's `autodojo.fork_*`. `declared_semantics.run_error` names the JSONDecodeError
case. There is no attack-cache or NLTK machinery: AgentDyn has neither.

### 4.3 Registry and profile (all class 1, held branch)

`adapters/registry/__init__.py` is in the AER closure (`stage_scopes`), and any `.toml`/`.py`/`.json` under
`adapters/agentdojo/` moves the family's `adapter_code_sha256`. So every core-side piece below is **class 1**. It goes
on a held branch, and the orchestrator decides when it lands; no stored corpus byte changes, only the recorded code
digests. Invariant 5 holds (no `aer/`, `prov/`, `validate/` or `corpus/` edit).

- `BACKENDS["agentdyn"] = BackendDescriptor(project="backends/agentdyn", capture_mapper="agentdojo.capture",
  profile="agentdyn-live")`.
- A `Capability(part="live", live_status="planned", backend="agentdyn", profile="agentdyn-live",
  requires=("backend:agentdyn",), semantics=("agentdojo.suites@3",))` on source `agentdyn`. Its caveat states
  "scripted (fake-client) tested; no real-model run".
  - **Status:** the vocabulary is closed (D.3.2), so there is no "scripted-tested" value. `agentdojo · live` and
    `autodojo · live` are still `planned` although their scripted gates pass. I propose the same `planned` with the
    caveat; a later move to `supported` should be decided for all three live parts together (it needs the D.3.2 live
    gate: CI driving a real task end to end, scripted allowed).
  - The user then runs it as `agentprov run agentdyn`, the existing source id.
- Profile `agentdyn-live.profile.toml` v1 (data, modelled on `autodojo-live`):
  - pins `{repo, commit}` with no subdirectory;
  - suite map with AgentDyn suites → `agentdyn` and the 4 others → `agentdojo`;
  - `semantics_profile agentdojo.suites@3`;
  - `retry_semantics agentdyn.last_assistant_content_none_max3`;
  - `system_prompt_variants` with `auto_complete_line` (`21a1c00d…`, source line at `5353cf76`);
  - `verified_code` = the pin;
  - the run-error quirk params above;
  - `refuse` covering every defence, and `instrumentation_extra` listing §4.2;
  - `[licence]` per D-686.
- `cli/run.py` `BACKEND_REFUSALS["agentdyn"]` (gateway_compat) is class 0.

### 4.4 Caveats (R-9b-1, R-9b-2) and D.15 entries

- **R-9b-1.** AgentDyn's tools draw OTPs and order ids from `random` and stamp `datetime.now()`/`date.today()`. The
  tool modules are identical blobs in both backends, so the nondeterminism is identical. Extend
  `agentdyn.art.nondeterministic_tools` to profile `agentdyn-live`, part `live` (class 1, same branch). Any claim about
  re-running cells must say a re-run is not a reproduction.
- **R-9b-2.** Resolved (regen item 27, implemented 2026-10-13); it carries over through the suite map.
- **New D.15 entries proposed** (`adapters/agentdojo/artefacts.toml`, class 1):
  - `agentdyn.art.malformed_tool_call_dropped` (F-5);
  - `agentdyn.art.system_prompt_auto_complete` (F-1, scope `autodojo-live` and `agentdyn-live`: which prompt the
    backend sent);
  - `autodojo.art.shopping_ground_truth_rewritten` (F-2, `tool_knowledge`);
  - `autodojo.art.workspace_checker_edits` (F-6).

  Each entry is routed to its owner before it is written (F-6 belongs with `autodojo-live`).

---

## 5. Licence of corpora captured from AgentDyn's suites (D-686: user decision)

**Facts.**

- The repository's only licence is `LICENSE`: MIT, "Copyright (c) 2024 Edoardo Debenedetti, Jie Zhang, Mislav
  Balunovic, Luca Beurer-Kellner, Marc Fischer, and Florian Tramèr". AgentDyn adds no copyright line of its own.
- AgentDyn's own suites (task text, environment data, injection goals) and its logs carry no separate licence
  statement.
- The source profile records `data_licence = "none"`, `policy = "include"` and `basis = "MIT as declared; not legally
  settled"`.

A captured session contains:

1. AgentDyn suite content: the task prompts and the environment data are in every model input;
2. model outputs, under provider terms;
3. the user's own execution.

**Options.**

- **A. include, as the existing `agentdyn` import corpus (recommended).** The MIT grant covers the repository's
  "software and associated documentation files", which ships the suites in the same tree and wheel. The imported
  `agentdyn` corpus (38,281 logs of the same suites) is already `include` on the same basis, and `autodojo · live`
  runs these same suite files under `include`. Attribution: the LICENSE notice plus arXiv:2602.03117. Keep the same
  `unassessed` items. The datasheet states the basis verbatim.
- **B. include, released only after the AgentDyn authors confirm** the licence of their suites and data. Corpora are
  captured and sealed, but the deposit waits for the answer.
- **C. reference only.** Captured corpora stay private (research use); nothing is deposited.

This is not the systematic-search "no licence → exclude" case, since there is a LICENSE. But because "not legally
settled" is recorded, it is the user's call. Whatever is chosen should apply equally to AgentDyn cells captured
through AutoDojo, so the two backends do not diverge in releasability.

---

## 6. Tests and the scripted run (D-688)

Scripted transport (`--llm-script`) only: no keys, no real model call, and `.env` is never read.

- **T1 `backends/agentdyn/tests`** (`backend_agentdyn` marker; copies of the AutoDojo backend's
  `test_identity`/`test_worker_protocol`/`test_offline`/`test_rpr10`/`test_executor_mirror`):
  - PEP 610 equals the pin;
  - the guarded names resolve;
  - the executor-mirror AST guard passes;
  - `hello` reports `21a1c00d…` and the 7 suites;
  - the network guard is on.
- **T2 `catalogue`:**
  - `run agentdyn --catalogue` gives 7 suites, 157/63 tasks and 17 attacks (5 DoS), with every refusal named;
  - `tests/integration/test_catalogue_backend_env.py` against `agentdyn-5353cf76` (`AGENTPROV_TEST_BACKEND_PYTHON`).
- **T3 `backends build agentdyn`:**
  - offline from the uv cache after the one consented fetch;
  - `--offline-check`;
  - the sandbox-exec probe;
  - `--dry-run` text.
- **T4 import audit:** after a scripted cell, `sys.modules` holds none of the overridden packages and nothing under
  `agentdojo.defenses`.
- **T5 suite identity, executed:**
  - per-suite tool-definition digests for `shopping`/`github`/`dailylife` equal in `agentdyn-5353cf76` and
    `autodojo-aa458794`;
  - the `shopping` `tool_knowledge` payload differs (F-2), as a pinned expectation.
- **Scripted scratch run** (through `tools/suite_queue.py --class import`, ≤2 CPU), 4 cells into
  `~/.agentprov/migration-work/agentdyn-backend/` (never sealed for release), then `validate` and
  `recompute --dry-run` (expect 0 differences):
  - S1 `shopping` benign user task;
  - S2 `github` user task × `important_instructions`;
  - S3 `workspace` benign task (AgentDojo suite on the AgentDyn harness: the system prompt differs from
    `agentdojo · live`);
  - S4 `dailylife` with a scripted reply carrying one tool call with non-JSON arguments (F-5, decides D-685).

  The mapping needs the class-1 branch, so this run happens on it.
- **T6 import boundary:** `tests/test_import_boundaries.py` already forbids `agentdojo`, which is the module name
  AgentDyn installs. Add `agentdyn` to the forbidden names in case a future package uses it (class 0).
- **Gates:** one pytest at a time, `-n 2` at most. The full suite goes through the queue before each hash is sent.

---

## 7. Work split and ownership

| Branch | Content | Class |
|---|---|---|
| `agentdyn-backend` (this worktree) | `backends/agentdyn/` (new), `backends/shared` (`agentdyn.py` with `AgentDynBackend` and its `catalogue`, `identity.AGENTDYN_GUARDED_NAMES`, `select_backend`, worker docstring), `cli/backends.py` choices, `cli/live/envs.py` `BACKEND_IDS`/`FORK_GUARDED_MODULES`, `cli/run.py` refusals and help, tests T1–T4, T6, spec D.11.x/N.2.10, report | 0 |
| `agentdyn-backend-core` (held, stacked) | `BACKENDS` entry, `agentdyn · live` capability, `agentdyn-live` profile, artefacts entries, optional D-685(b) mapper rule plus catalogue `agentdyn` v3, tests T5 and the scripted run | 1 |

`backends/shared` is coordinated with the GUI session, which owns D-652 there: `AgentDynBackend.catalogue` calls
D-652's `runner.catalogue()`, which is on `gui-g3` and not yet in `3f204611`.

---

## 8. Decisions requested (D-680..D-689)

| Id | Decision | Recommendation | Who |
|---|---|---|---|
| D-680 | Pin | `5353cf76` (the profile's pin, the head as of 2026-10-14, includes the #6 fix); optional `ls-remote` check | user |
| D-681 | Install | uv git source (canonical URL, full rev), Python 3.12, own lock, `exclude-newer` 2026-10-07, `environments` darwin+linux, the 7 unused declared dependencies overridden out (lock offline-resolvable) | user (the dependency deviation) |
| — | Download | the AgentDyn repository via uv, ~70 MB (stop at 500 MB); no PyPI download; optional `ls-remote` | user's yes, typed in this window |
| D-682 | Identity and refusals | §2 | orchestrator |
| D-683 | Backend instrumentation ids | §4.2 | orchestrator |
| D-684 | Registry `agentdyn · live` `planned` plus caveat, profile `agentdyn-live`, held class-1 branch | as §4.3; landing time is the orchestrator's | orchestrator / user |
| D-685 | Dropped malformed tool calls in the mapper | (a) now, (b) on the held branch after S4 | orchestrator |
| D-686 | Licence of captured corpora | A (include, as the import corpus) | **user** |
| D-687 | Record findings F-1..F-8 (report plus D.15 entries routed to owners) | yes | orchestrator |
| D-688 | Test plan | §6 | orchestrator |
| D-689 | spare | — | — |
