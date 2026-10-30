# Defence backends: which methods to run live, and how `--defence` works (design note)

Status: **approved and built** (2026-10-22; the user approved every recommendation of §5 the same day, recorded as
D-670–D-679 in DECISIONS.md with a build amendment; the spec is D.10.11). As built, the registry lives in the harness
(`backends/shared/src/agentprov_backend/defences.toml`, class 0) rather than under `adapters/agentdojo/tables/`, MELON's
`melon_r` is not built, and D-672's download is done. The sections below are the design as approved. Branch `claude/agentprov-defence-backends-538dc2` from the pre-round
integration head `3dfaa19b`. Decision numbers D-670–D-679 (ledger rid `5633ded8…`).

**How this was checked.** Nothing was fetched, built or run. Facts come from:

- the 36 profiles under `src/agentprov/adapters/agentdojo/profiles/` and their identity tables;
- the staging clones and deposits under `~/.agentprov/staging/` and the bare caches under `~/.agentprov/cache/git/`
  (every git read with `GIT_NO_LAZY_FETCH=1`; zips read by member, never extracted);
- the installed files of the two registered environments, `~/.agentprov/envs/agentdojo-79922295` (stock agentdojo
  0.1.35) and `~/.agentprov/envs/autodojo-aa458794` (AutoDojo fork);
- the spec (C.3.7, C.13, D.10, D.11, N.2.1b), `backends/shared` and the core capture mapper.

Third-party repository text was read as data only. "Not verified" marks anything that was read but not run.

**Short answer.**

1. **Recommended first set:**
   - the four defences that ship with stock AgentDojo 0.1.35 (`repeat_user_prompt`, `spotlighting_with_delimiting`,
     `tool_filter`, `transformers_pi_detector`);
   - the Mandate action gate;
   - the MELON detector.

   All are MIT-licensed, all run on the existing `agentdojo` backend, and none needs a new fork or a GPU. Together they
   cover the three ways a defence acts on a run, so the recording code built for them serves most later picks:
   - it changes what the model is sent;
   - it blocks tool calls;
   - it makes its own model calls.
2. **No `capture/0.2` is needed for the first or second set.** `capture/0.1` already has defence actors, auxiliary model
   calls, `decision` events and denied tool results, and the core capture mapper already maps them (§3.5). What is
   missing is in the harness: it refuses every defence, has no hook that emits a `decision`, and cannot bracket a
   defence's own model calls.
3. **The work splits into two branches:**
   - a harness branch (`backends/shared`, `cli/`, backend locks): byte class 0;
   - a core branch (the live defence table and profiles, the capture mapper, rules): byte class 1, held, landed by the
     orchestrator.
4. **Downloads:**
   - `transformers_pi_detector`: `torch` and `transformers` wheels plus one pinned classifier (about 0.75 GB);
   - MELON: one `numpy` wheel. It also needs an OpenAI key for embeddings at run time (a cost, not a download);
   - the other picks: none.
5. **Not runnable live** without missing code, weights or services (§2.3): Progent, CaMeL, TACIT (linyxus), llm-lock,
   UBAG, Interbolt, the memo-ozdincer circuit breakers and EnvironmentOptim.

Decisions for the user are in §5.

---

## 0. What exists today

- **Refusal points.** Live runs accept only `--defence none`. A defence is refused in four places:
  - the CLI (`src/agentprov/cli/run.py:1061-1098`), with exit 5;
  - plan expansion (`backends/shared/.../runner.py:243`, `:329`). The worker answers `plan_refused`, which the CLI
    turns into exit **2** (an inconsistency, D-679);
  - `AutoDojoBackend.check_cell`, which gives a sealed `errored` session;
  - `build_instrumented_pipeline` (`runner.py:525`).

  Both live profiles say `refuse = ["defense!=null", …]` (autodojo: the four replacing defences).
- **What the harness builds.** It assembles the undefended pipeline by hand:
  `PassRecorder(AgentPipeline([SystemMessage, InitQuery, SpannedLLM(llm), ToolsExecutionLoop([MirrorToolsExecutor,
  SpannedLLM(llm)])]))`. `pipeline.name` is the model id, not stock's `<model>-<defence>`.
- **What `capture/0.1` can hold (C.13.3):**
  - `session.start.actors {tag: {kind, name?, role?, model?}}`, which accepts `kind: defense`;
  - `llm.request.role ∈ {agent, auxiliary}`, with the envelope `actor`;
  - `decision {actor, subject {occ}|{at}|{call}, verdict, reason?, original?, replacement?, subtype?}`;
  - `tool.result.status = denied` with `decided_by`;
  - namespaced `note` events.

  The writer accepts `decision` (`capture/src/agentprov_capture/events.py:90`).
- **What the core mapper already does** (`adapters/agentdojo/capture_mapper.py`):
  - maps `decision` events (`_decision_event`, `:1724`) and denied results (`_denial`, `:1703`) into AER `decision`
    records (RF-3: no `tool_execution`);
  - maps auxiliary calls as `model_call`s that are not reconciled with assistant messages (D.10.3);
  - copies `cell.defense_id` into `task.defense_id` (`:543`).
- **What the harness lacks:**
  - a `decision()` hook (`CaptureHooks` has none);
  - a span for defence model calls. A request made outside a span is recorded with role `auxiliary` and `actor: null`
    (`gateway.py:219-231`), and the mapper rejects such a request as malformed (`capture_mapper.py:430`).
- **Environments.** Neither registered environment has `torch` or `transformers` installed. The AutoDojo lock lists them
  under an optional `filters` group that was never installed. `jsonschema`, `z3` and the CaMeL extras are absent too.
  So today every classifier defence, Progent and CaMeL would fail at construction.
- **Identity guards.** No defence code is guarded: `identity.GUARDED_NAMES` covers the executor, the runner, the logger
  and the OpenAI helpers only.
- **Built-in defences per environment:**
  - stock 0.1.35 `DEFENSES` (`agent_pipeline.py:43-48`): `tool_filter`, `transformers_pi_detector`,
    `spotlighting_with_delimiting`, `repeat_user_prompt`;
  - the AutoDojo fork adds `reminder`, `sandwich`, `promptguard`, `piguard`, `protectai`, `datafilter`, `drift`,
    `progent`, `camel`, `camel_nopolicy`, and renames spotlighting to `spotlighting`.

  Stock names every defended pipeline `f"{llm_name}-{defense}"`; the fork uses `/`.

## 1. Inventory of the AgentDojo-format sources

Shape key:

- **(a)** a pipeline element that plugs into stock 0.1.35's `AgentPipeline`: a `BasePipelineElement`, a `ToolsExecutor`
  subclass, a formatter;
- **(b)** needs a fork, because it changes suites, the runner, the task loop or the logger;
- **(c)** an external agent, framework or offline analysis.

"Local" means the method code is readable without a fetch:

- **st:** a staging working tree or deposit;
- **bc:** a local blob in a bare cache;
- **env:** installed in a registered environment.

Licence is code / data (SPDX; "none" = no separate data licence). All profiles have policy `include`, copyleft ones as
their own corpus (D-94).

| # | Source (profile) | Type | Method code (repo@commit: path) | Local? | Licence | Shape | Extra dependencies | Live verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | agentdojo-upstream | baseline + 4 built-in defences | ethz-spylab/agentdojo@a75aba76 (v0.1.35): `agent_pipeline/{agent_pipeline,pi_detector}.py`, `llms/openai_llm.py` (`OpenAILLMToolFilter`) | env, upstream clone | MIT / none | a | `tool_filter`: +1 call/pass, same model, OpenAI-class LLM only. PI detector: torch, transformers, `protectai/deberta-v3-base-prompt-injection-v2` (CPU is fine) | **First set** (§2) |
| 2 | ipi-defenses-agentdojo | evaluation of the 4 built-ins (banking) | Zenodo 22011266: `code/agentdojo_banking.py` (stock `PipelineConfig(defense=…)`) | st | MIT code (README), CC-BY-4.0 / CC-BY-4.0 | a | as row 1; its detector revision was not pinned | covered by row 1 (live comparison corpus) |
| 3 | agentdyn | benchmark (shopping, github, dailylife) + multi-defence evaluation | SaFo-Lab/AgentDyn@5353cf76: `agent_pipeline/{agent_pipeline,pi_detector}.py`, `defenses/{camel,drift,progent}` | bc | MIT (+CaMeL Apache-2.0) / none | b (elements a, CaMeL c) | HF detectors (PIGuard, gated Prompt-Guard-2), Progent policy LLM, DRIFT calls, local SecAlign (GPU) | through the AgentDyn and AutoDojo backends; same defences as rows 1, 20, 21 |
| 4 | aiauthz-agentdojo | defence: deterministic authorisation gate | Sports-Vision-Inc/aiAuthZ@6eaac86a: `experiments/agentdojo/aiauthz_defense.py` (`AiAuthzToolsExecutor`) + `aiauthz/policy/` | st | **AGPL-3.0** (-only vs -or-later, PC-05) / none | a | `aiauthz` package (probably only `policy`; not verified); no LLM | feasible; copyleft (D-676) |
| 5 | authority-caps-agentdojo | defence (tool caps) + attack (`authority_notice`) | Zenodo 23138310: `source-snapshots/run_new_models.py` (`AuthorityCap`, `NoEgress`, `AutoConfirm`), `novel_attacks.py`, codebook CSVs | st (zip) | MIT / CC-BY-4.0 | a | none; no LLM | **Second set** |
| 6 | autodojo-via-rope | attack (optimised injections, cache replay) | xhOwenMa/AutoDojo@aa458794: `attacks/autodojo_attack.py` | env, bc | MIT / none | attack | the cache only | already live as `--attack autodojo`; not a defence |
| 7 | bookkeeper-agentdojo | defence: money gate (Munim) | sricursion/bookkeeper@0fe09bb6: `eval/agentdojo/munim_defense.py` (`GatedToolsExecutor`) + `munim/` | st | **GPL-3.0-or-later** / none | a | none (stdlib) | feasible; copyleft (D-676) |
| 8 | ceferisbarov-agentdojo | attack (monitor-adapted optimised strings) | ceferisbarov/agentdojo@2273e1cd: `benchmark.py`, `default_suites/v1/*/injection_tasks.py`; optimiser not local | st (fork) | MIT / none | b | GPU + white-box monitors to re-optimise | not a defence |
| 9 | craibench-agentdojo | benchmark + memory-injection attack + spotlighting variants | AthaSSiN/CrAIBench@e41eac1e (fork of 0.1.15): `basic_elements.py`, `task_suite.py`, new suites | st | MIT (+CC-BY-4.0 data) / none | b | none | would be its own backend (0.1.15 fork); low priority |
| 10 | dca-agentdojo | defence: counterfactual plan audit (+ CaMeL, DRIFT comparators) | Figshare 32657856: `code/dca_core/src/agentdojo_custom_defense/defenses/counterfactual.py`, `sitecustomize.py` (patches `from_config`) | st (CaMeL src missing) | MIT (CaMeL Apache-2.0) / none | a | budgeted replays with the agent model; Ollama arms (GPU) | third set; no paper yet |
| 11 | drift | defence: DRIFT (constraints, judge, isolation) | SaFo-Lab/DRIFT@6fd3df47: `DRIFTLLM.py`, `DRIFTTaskSuite.py`, `DRIFTToolsExecutionLoop.py`; also in the AutoDojo env (`agent_pipeline/drift_defense/`) | st, env | MIT (history: reference) / none | b/c (replaces the agent and the suite class) | many calls per step to a separate defence model | third set: own increment (§2.2) |
| 12 | drift1-agentdojo | DRIFT re-run + PACT-DRIFT | CGboom-git/drift-1@0e28729b: `pact_drift/*` | st (not the producing state) | MIT by README badge only (D-93) / none | b/c | as DRIFT + LLM contracts | no: code is not the producing state; licence weak |
| 13 | environmentoptim-agentdojo | agent design (environment nudges) | omseeth/EnvironmentOptim@febf82d8: `optimization/*.py` | st; **trained weights absent** | MIT / none | b/c | local Qwen3.5-9B, GPU | no: artefacts missing; not a defence |
| 14 | gate-agentdojo | defence: string-provenance gate (+ gatellm) | dafarusd/gate@925b9926: `src/defenses/policy_gate.py` (`PolicyGate`), `src/gatellm_gate.py`, `gatellml/lang/` | st | **AGPL-3.0-only** / none | a | none; Ollama/Venice agents | feasible; copyleft (D-676) |
| 15 | geryon-agentdojo | evaluation of Progent | luiacuaniello/geryon@905aae02: `scripts/run_condition.py`; Progent at an unrecorded HEAD (not local) | st (harness) | Apache-2.0 / none | b | policy LLM, Amazon Bedrock | no: Progent version unknown |
| 16 | glitch-agentdojo | defence: closed-world tool gateway | zanethomas1430-code/Glitch@713bb296: `17_agentdojo/{dojo_gateway,pipeline}.py` (`GlitchToolsExecutor`) | st | MIT / none | a | none; it also monkey-patches SDK retries (must not be applied, §4.6) | **Second set** |
| 17 | hilarytorn-trajectory-poisoning | attack on monitors (TAP/PAIR) | HilaryTorn/in-context-trajectory-poisoning@d71ab8bc: `src/*.py` | st | MIT / none | b-light + c (monitor post hoc) | LlamaFirewall, hosted monitor models, attacker LLM | not a defence |
| 18 | interbolt-agentdojo | defence: CEL policy gate | deconvolute-labs/interbolt-agentdojo@43e2b5fa: `executor.py` (`InterboltToolsExecutor`); **`interbolt` engine not local** | st (harness) | Apache-2.0 (engine unassessed) / none | a | `interbolt` 0.2/0.3 (version unclear), cel-python | no until the engine version is identified |
| 19 | kavach-agentdojo | defence: tool-call parliament (BLOCK/ESCALATE/ALLOW) | Ishani018/Kavach@53df9545 (+f2dd7efa, 6b31a554): `benchmarks/kavach_agentdojo_defense.py` (`KavachDefense`), `parliament/` service | st | MIT / none | a + local HTTP service | FastAPI service, BGE-base, chromadb, rank-bm25, optional Ollama tiebreaker; fails open | defer: service and fail-open |
| 20 | kongminos-agentdojo | baseline (DeepSeek V4-Flash) | kongminOS/jspace-agentdojo-950@f341af69 (recompute script only) | st | MIT / none | — | local endpoint | nothing to run beyond undefended live runs |
| 21 | linyxus-agentdojo | defence / agent design (TACIT Scala REPL) | Linyxus/agentdojo@698d7ff2: `tacit.py`, `task_suite.py`; **TACIT.jar absent** | st | MIT (jar unknown) / none | b + JVM | Java, TACIT jars, MCP, OpenRouter aux LLM | no: jar missing |
| 22 | llm-lock-agentdojo | defence: tool-output detectors (9 arms) | Wakeful-Cloud/llm-lock@7bb9915b: `agentdojo/*_defense.py`; **joblib classifiers absent** | st | **GPL-3.0** / none | a | HF classifiers, MiniLM, Qwen3-8B judge (Ollama), GPU | no: trained classifiers missing; copyleft |
| 23 | mandate-agentdojo-eval | defence: deterministic action gate (`envelope`, `scoped`, `intent`) | jwilliamsc/mandate-agentdojo-eval@fa62a977: `agentdojo_mandate_eval.py` (`_make_mandate_executor`, `gate_decision`) | bc (blob present) | MIT ("Mandate Labs", publisher unverified) / none | a (`ToolsExecutor` subclass) | none; banking only | **First set** |
| 24 | melon-agentdojo | defence: MELON masked re-execution (`melon`, `melon_at`, `melon_sm`, `melon_r`, `melon_rp`) | xwsdid/MELON@71d99dff: `src/agentdojo/agent_pipeline/pi_detector.py` (`MELON` :516, `MELONR` :1117, `MELONSM` :1587, `MELONAT` :1591); `melon_rp` **absent** at the pin | st | MIT (upstream text; fork adds none) / none | a in a fork (needs a port, §4.3) | a masked re-run per tool output with the agent model; OpenAI `text-embedding-3-large` | **First set** (4 variants) |
| 25 | memo-ozdincer-agentdojo | defence: circuit-breaker LoRA adapters (+ baselines) | memo-ozdincer/agentdojo@7c331d97: `scripts/lorra_train.py`, `eval_lorra_multiturn.py`; **Llama-70B adapters absent** | bc | MIT / none | a as a model swap; b as run | vLLM, Llama-3.3-70B TP4, Meta-SecAlign (gated) | no: weights missing, multi-GPU |
| 26 | menelaus29-ipi-multidomain | defence (`my_spotlighting`) + attacks (corpus, adaptive) | Menelaus29/ipi-multidomain-agent-study@ec9c9287: `src/defenses/my_spotlighting.py` (`MySpotlightingLLM`), `src/experiments/run_baseline.py` | st | MIT / none | a | Google GenAI for its models; adaptive loop: proposer LLM | optional add-on (prompt wrapper) |
| 27 | mohameduk-agentdojo | defence: UBAG authorisation gateway | mohameduk/agentdojo@3f9d69a1: `agent_pipeline/ubag_gateway.py`; **gateway service absent** | st (client) | MIT / none | a client + external service | UBAG service and tokens | no: service missing |
| 28 | rope | defence: routed origin-policy enforcement | xhOwenMa/ROPE@64495e16: `src/rope/{pipeline,router,policy_synthesis,enforce,origin,clamp}.py`; cached router scopes | bc | MIT / none | a on the AutoDojo fork (its vendored revision differs) | router LLM (cached: deterministic), OpenRouter agents | **Second set** (AutoDojo or own backend, D-677) |
| 29 | seagent-agentdojo | defence: intent-aware access control (+ AgentSpec, PVAgent) | Zenodo 23218779: `artifact/agentdojo/.../seagent_defense.py` (`SeagentDefense`), `artifact/seagent/src/`; AgentSpec/PVAgent not redistributed | st (zip) | Apache-2.0 / CC-BY-4.0 | a in a 0.1.34 fork | `deepseek-reasoner` policy LLM, `deepseek-v3`, ARK | third set |
| 30 | sentry-agentdojo | analysis: post-hoc action monitor | vinhqdang/SENTRY-…@938e8be7: `sentry/` | st | **AGPL-3.0-only** / none | c | judge LLM | not a defence in the loop |
| 31 | shreeyavarma-llm-safety | analysis: trajectory classifier | ShreeyaVarma/llm_safety@78d22e4a | st | MIT / none | c | sklearn, Qwen weights | not a defence |
| 32 | survey-runs | baseline (Ollama models) | Forever-CodingNoob/agent-security-tools-survey@89c4db2c; **3 patches only in an unfetched Zenodo zip** | bc | CC-BY-4.0 / CC-BY-4.0 | — | Ollama, gpt-oss:120b | nothing to run |
| 33 | tacit-agentdojo | analysis: activation probes (CSSLab) | CSSLab/Tacit@995692d3: `tacit/`, `scripts/data/collect_agentdojo.sh` | st | Apache-2.0 / none | c (collection is stock) | vLLM, Qwen3-4B / Llama-3.1-8B, GPU | not a defence |
| 34 | yockcheng-prompt-injection-harness | attack: autonomous red-team | yockcheng/prompt-injection-harness@5f9137ff: `harness/`, `targets/agentdojo-workspace/server.py` | st | Apache-2.0 / none | c | Claude Code CLI in Docker, gVisor | not a defence |

The 36 profiles also include the two live profiles, `agentdojo-live` and `autodojo-live`, which are not sources of
methods.

**Counts.**

- **19 sources bring their own in-loop defence:** rows 4, 5, 7, 10, 11, 12, 14, 16, 18, 19, 21–29. Five more ran
  other people's defences: rows 1, 2, 3, 9 and 15.
- **Code is missing for 8 of them:** linyxus, llm-lock, mohameduk, memo-ozdincer, interbolt, geryon (Progent),
  environmentoptim, and the `melon_rp` variant.
- **Copyleft (5):** aiauthz, bookkeeper, gate, llm-lock, sentry.
- **Built on other AgentDojo versions:** seagent (0.1.34), craibench (0.1.15), hilarytorn (0.1.29 pinned).

**Not verified by running.** No defence was imported or run against an environment. Shapes come from class hierarchies
and imports. Mandate's `scoped` arm is in the code; whether it appears in the logs was not checked.

## 2. Ranking

**Criteria, scored 1–3 each:**

- **Research value:** the method is published or widely used; its mechanism is distinct; an imported corpus with the same
  arm exists for a live-versus-imported comparison.
- **Feasibility:** the code is local and pinned; it is a pipeline element on stock 0.1.35; no artefact is missing.
- **Licence:** permissive scores 3; copyleft is runnable but needs D-676.
- **Cost:** extra model calls, GPU or downloads per cell.

The full AgentDojo v1.2.2 run per defence arm is 629 attacked cells (`important_instructions`) plus 97 benign cells.
Banking alone is 144 + 16.

### 2.1 Recommended first set (one build, three recording patterns)

| Rank | Pick | Research | Feasibility | Licence | Cost | Why, in plain words |
|---|---|---|---|---|---|---|
| 1 | **AgentDojo's four built-in defences** on the `agentdojo` backend | 3 | 3 | 3 | 3 (PI detector: 2) | They are the reference arms that every paper compares against. Four imported corpora carry the same arms (agentdojo-upstream 36,679 logs, ipi-defenses 3,211, AgentDyn, and memo-ozdincer's baselines), so live runs can be checked against imported ones. No fork is needed: the installed package builds them. Three need nothing new. The PI detector needs `torch`, `transformers` and one pinned classifier, and runs on CPU |
| 2 | **Mandate** (`mandate_envelope`, `mandate_scoped`, `mandate_intent`) | 2–3 | 3 | 3 | 3 | The cleanest example of the "deterministic action gate" family, which also includes Glitch, Munim, aiAuthZ, Interbolt and UBAG: no model, no randomness, one file, MIT. Its authors report a large effect (81.5% → 11.1% ASR on banking). It makes us build the gate recorder once, which the rest of that family reuses. Banking only, so it is cheap |
| 3 | **MELON** (`melon`, `melon_at`, `melon_sm`, `melon_r`) | 3 | 2 | 3 | 1–2 | A published defence of the "detector with its own model calls" kind: it re-runs the agent with the user task masked and compares tool calls by embedding. 1,911 imported MELON logs plus memo-ozdincer's MELON arms allow comparison. It needs a small declared port (§4.3): the fork hard-codes its own OpenAI client with a fixed proxy, and the detector element is also the agent's model step. Cost is roughly twice the agent calls plus embeddings (estimate, not measured). `melon_rp` cannot be built because it is absent at the pin |

**Why these three together.** Each needs a different recorder:

- the built-ins change the prompt, the tool list and tool outputs, and the PI detector redacts;
- Mandate denies tool calls;
- MELON makes auxiliary model calls and redacts.

Building the three recorders (§3.4) unlocks most of the second set at little extra cost. Rank 1 can ship in two steps:
first the three built-ins that need no download, then the PI detector after D-672.

### 2.2 Second set (reuses the first set's machinery)

| Rank | Pick | Notes |
|---|---|---|
| 4 | AutoDojo fork built-ins on the `autodojo` backend (`reminder`, `sandwich`, `spotlighting`, `repeat_user_prompt`, `tool_filter`) | Almost free once the built-in path exists. The fork's names differ from stock (`spotlighting`), and its `tool_filter` adds an OpenRouter `extra_body`. Comparable with the AgentDyn arms |
| 5 | Authority caps (`capA3`, `capA4`, `noegress`, `autoconfirm`) | MIT, about ten lines per element, no model. Same tool-list recorder as `tool_filter`. 21,999 imported logs. Its `authority_notice` attack would need an `--attack` registry, which is out of scope here |
| 6 | ROPE | Recent and distinctive (a router-derived origin policy), MIT, 10,791 imported logs, deterministic with the cached router. But its code is at unreleased states (`code_identity = unpinned`), it was run on a vendored AutoDojo revision other than `aa458794`, and its packages (`jsonschema`, `google-genai`) are not installed. Either a provisioned add-on to the AutoDojo backend or its own fork-pinned backend (D-677, after checking ROPE's imports). Coordinate with the AgentDyn backend session |
| 7 | Glitch | MIT gate; gate recorder reuse. Its SDK retry monkey-patches must **not** be applied: they would change the harness's model calls |
| 8 | Classifier filters on AutoDojo: `protectai` first; `promptguard` (Llama-Prompt-Guard-2, gated); `piguard` (`trust_remote_code=True`, refused, D-678) | Same weights pattern as the PI detector; NLTK is already pinned |

### 2.3 Third set and not now

- **Third set (own design increments):**
  - **DRIFT.** Installed in the AutoDojo environment. It replaces the agent and the suite class and calls a separate
    defence model many times per step: a new "agent-replacing" recorder plus a defence endpoint.
  - **SEAgent.** A 0.1.34 fork, a DeepSeek policy model, Apache-2.0: its own backend.
  - **DCA.** Replays through the agent model; no paper yet.
  - **Kavach.** A local service, and it fails open.
  - **`my_spotlighting`** (menelaus29). A trivial add-on whenever wanted.
- **Copyleft but feasible (D-676):** aiAuthZ (AGPL), Munim/bookkeeper (GPL-3.0+), gate (AGPL). Each is an (a)-shape
  element that the first set's gate recorder would handle.
- **Not runnable without new artefacts:**
  - Progent: `jsonschema` and `z3` are not installed, a policy model is needed, and Geryon's version is unknown;
  - CaMeL: its extras are not installed. Its interpreter issues tool calls that no assistant message requested, which
    would probably need span events (a `capture/0.2` question, §3.5);
  - TACIT (jar missing), llm-lock (classifiers missing), UBAG (service missing), Interbolt (engine version unknown),
    memo-ozdincer (70B adapters missing, multi-GPU), EnvironmentOptim (weights missing).
- **Not defences** (attacks, analyses, baselines): rows 6, 8, 9 (attack part), 17, 20, 30–34. Attacks would need an
  `--attack` registry analogous to §3.2, which is out of scope.

## 3. `--defence` design

### 3.1 Naming

- **A defence id is the arm name the method's own code uses.** Examples: `tool_filter`, `transformers_pi_detector`,
  `melon_at`; Mandate's own names are prefixed as `mandate_envelope`. Using the method's names keeps live
  `task.defense_id` equal to the imported corpora's defence-suffix values, so arms can be pooled or compared by id.
- Where a fork renames a defence, the registry keeps both names. For example, AutoDojo's `spotlighting` is stock's
  `spotlighting_with_delimiting`, recorded as `benchmark_name = "spotlighting"`.
- **A variant with different parameters is a different id** only when the source names it as an arm. Otherwise
  parameters go in `defence_params`, which is recorded and digested (§3.3) and refused unless the registry declares
  the parameter.
- `pipeline.name` becomes stock's `f"{model}-{defence}"`, so native logs land where stock writes them and look like the
  imported ones.
- **One defence per plan in v0.1.** A multi-arm study is several campaigns, one corpus each; the GUI can queue them.
  This avoids changing `cell_key` and the logical key (H.7.4). `--defence a,b` is a later option.

### 3.2 The defence registry (data, in the core)

The registry is one table, `src/agentprov/adapters/agentdojo/tables/live_defences.toml`. Each live profile pins it by
`{path, sha256}`, like the identity tables, so its digest is covered by the profile digest. Each live profile lists
the ids it allows. T0 reads the table, as N.2.1b already promises ("must be allowed by the live profile"). The worker
receives only the resolved entry, inside `backend_config.defence`, which `config_sha256` covers.

Sketch:

```toml
[[defence]]
id = "transformers_pi_detector"
backends = ["agentdojo"]
provider = "builtin"            # builtin | provisioned | port | fork  (§3.3)
benchmark_name = "transformers_pi_detector"
licence = { spdx = "MIT", basis = "agentdojo 0.1.35 LICENSE" }
guarded = ["agentdojo.agent_pipeline.pi_detector.TransformersBasedPIDetector.detect",
           "agentdojo.agent_pipeline.pi_detector.PromptInjectionDetector.query",
           "agentdojo.agent_pipeline.agent_pipeline.AgentPipeline.from_config"]
weights = [{ hub = "huggingface", repo = "protectai/deberta-v3-base-prompt-injection-v2", revision = "<40-hex>",
             files = [{ name = "model.safetensors", sha256 = "<64-hex>" }], licence = "<SPDX, checked at fetch>" }]
extras = ["transformers"]       # backend-project dependency group
device = "cpu"                  # recorded; MPS/CUDA only by explicit choice
actors = [{ tag = "def0", kind = "defense", name = "transformers_pi_detector" }]
elements = [{ class = "agentdojo.agent_pipeline.pi_detector.TransformersBasedPIDetector", recorder = "output_filter",
              verdicts = ["allow", "redact"], observe = "detect" }]
aux_llm = "none"                # none | agent_endpoint | defence_endpoint
suites = ["*"]
cost = { extra_calls_per_step = 0 }   # declared prior for the GUI estimate, never a measured claim

[[defence]]
id = "mandate_intent"
backends = ["agentdojo"]
provider = "provisioned"
code = { repo = "https://github.com/jwilliamsc/mandate-agentdojo-eval", commit = "fa62a977…",
         files = [{ path = "agentdojo_mandate_eval.py", blob_sha1 = "…", sha256 = "…" }],
         entry = "agentdojo_mandate_eval:_make_mandate_executor", params = { mode = "intent" } }
licence = { spdx = "MIT", basis = "LICENSE at the pin; publisher unverified" }
elements = [{ replaces = "ToolsExecutor", recorder = "executor_gate" }]
denials = [{ error_prefix = "…the gate's text…" }]   # same matcher schema as hooks/defence_denial.py
suites = ["banking"]
```

The provider kinds:

- **`builtin`:** the installed benchmark builds it (`AgentPipeline.from_config(defense=…)`). Its code identity is the
  environment's existing one (RECORD digest, or the fork's PEP 610 pin) plus the new guarded names.
- **`provisioned`:** third-party code pinned to `repo@commit` and file blob SHA-1s, copied at **build** time from the
  bare fetch cache (no network when cached; otherwise only under `--allow-network` with the user's yes) into
  `<env>/agentprov_defences/<id>/`. Its sha256s are recorded in `AGENTPROV_ENV.json`. T0 re-hashes them before every
  spawn, as it does for NLTK. Nothing is copied into the Git repository (invariant 6), which also keeps copyleft code
  out of the repo.
- **`port`:** a provisioned defence plus an AgentPROV patch file, `backends/defences/<id>.patch`, applied at build.
  Both pre- and post-patch digests are recorded. The patch is declared as instrumentation (§3.3) and carries a
  must-not-claim item (D-674). A port is allowed only to make recording possible or to fix an environment coupling
  (a hard-coded client, proxy or path), never to change the decision logic.
- **`fork`:** a whole fork-pinned backend like `autodojo`. Used when the method changes suites, the runner or the
  logger: DRIFT standalone, SEAgent's 0.1.34, CrAIBench's 0.1.15.

### 3.3 Pinning, identity and what counts as instrumentation

**Identity (T0, before spawn, D.10.6 extended).**

- `hello.expect` gains:
  - the defence's guarded names;
  - for provisioned and port defences, the file sha256s;
  - for weights, the file sha256s.
- The worker reports `inspect.getsource` digests of the guarded names, as today. Any mismatch is `IdentityMismatch`
  (exit 3) and nothing runs.
- `--offline-check` re-verifies provisioned code and weights.
- The defence entry, its parameters and its digests go into `config_sha256`, and also into a
  `note agentdojo/defence_identity` event, mapped to `ext.agentdojo.defence` in the AER header (O by capture).

**Where the defence appears in the capture.**

| Item | Where | Evidence |
|---|---|---|
| Which defence | `session.start.cell.defense_id` → `task.defense_id` | O (configuration ground truth; better than the imports' class-I suffix inference) |
| Who | `session.start.actors.def0 {kind: "defense", name, model?}` → AER actor `def0` | O |
| Code, weights, params | `note agentdojo/defence_identity` → `ext.agentdojo.defence` | O |
| Its model calls | `llm.request role: auxiliary`, envelope `actor: def0` | O |
| Its interventions | `decision` events and `tool.result status: denied, decided_by: def0` | O, or D where attribution needs a declared text match (§3.6) |
| Messages it inserts | `note agentdojo/defence_message {pass, at, actor}` | O |

**What is instrumentation and what is not.**

- **The defence's own effect on requests is not instrumentation.** Instrumentation (D.10.7) is the harness's observer
  effect. A defence that rewrites tool outputs or adds a user message is the experimental treatment, and it is recorded
  as the defence's own actions in the table above.
- Declaring the treatment as `request_modifying` would make every defended session fail NC-LIVE-01 ("stock
  behaviour"). It would also blur observer and treatment, which is the distinction the claims library needs.
- **What the harness itself adds is instrumentation,** under these new D.10.7 items:

| id | kind | recorded | Note |
|---|---|---|---|
| `agentdojo.defence_pipeline_rewrite@1` | behaviour_preserving | full | the stock-built defended pipeline with the recording substitutions of §3.4; `params {defence, substitutions}`; verified by the differential test |
| `agentdojo.defence_recorder@1` | behaviour_preserving | full | wraps defence elements to observe verdicts; `params {elements, recorders}` |
| `agentdojo.defence_aux_span@1` | behaviour_preserving | full | brackets the defence's model calls as `def<n>`; no request change |
| `agentdojo.defence_code_provisioned@1` | behaviour_preserving | full | third-party code from pinned blobs; `params {repo, commit, files}` |
| `agentdojo.defence_weights_offline@1` | behaviour_preserving | full | weights provisioned at build, `HF_HUB_OFFLINE=1` at run; `params {repo, revision, sha256s, device}` |
| `agentdojo.defence_port@1` | `harness_policy`, or `request_modifying` if the patch changes any wire request | full | `params {patch_sha256, changes}`. `behaviour_preserving` only when a differential test against the unpatched code passes (D-674) |

### 3.4 How the defended pipeline is built (harness, class 0)

The harness does not hand-assemble each defended pipeline. It lets the benchmark (or the provisioned code) build the
pipeline, then **rewrites the element tree:**

1. `AgentPipeline.from_config(PipelineConfig(llm=<the recorded native element>, defense=benchmark_name, …))`, or the
   provisioned entry point. The native element is already on the recording transport (`build_llm`), so a defence that
   reuses `llm.client` (as stock `tool_filter` does) is recorded at the wire automatically.
2. Walk the tree and substitute:
   - stock `ToolsExecutor(fmt)` → `MirrorToolsExecutor(fmt)`, keeping the formatter, so spotlighting's `<<…>>` is kept;
   - each agent LLM element → `SpannedLLM(llm, role agent)`;
   - each declared defence element → the recorder it names;
   - the whole pipeline → `PassRecorder`.
3. Check the result structurally against the unrewritten pipeline (same element types and order modulo the declared
   substitutions). Refuse on any undeclared element.

There are five recorders. All are wrappers that delegate, and none changes inputs or outputs:

| Recorder | For | What it emits |
|---|---|---|
| `prompt_wrapper` | `spotlighting*`, `repeat_user_prompt`, `reminder`, `sandwich`, `my_spotlighting` | `defence_message` notes for messages the element appended (diff before and after its `query`). Formatter changes are already in `tool.result.rendered` vs `returned`, as imports treat spotlighting (post-defence content, no decision) |
| `tool_list_filter` | `tool_filter`, authority caps | opens an auxiliary span (`def0`) around the element; a note `agentdojo/defence_tools {before, after}` (tool names); `defence_message` notes for the filter prompt and reply. **No decision**, because a tool list is not an AER subject |
| `output_filter` | PI detector, the AutoDojo classifier filters, MELON's redaction, DRIFT isolation (later) | snapshots each new tool message **before** the element runs, then for each changed one emits `decision {verdict: redact\|modify, subject {occ}, original: <blob>}`. This recovers the original text that stock's in-place overwrite destroys (imports can only say `unk /original: overwritten`). Where the element exposes its verdict function (`detect`), the recorder wraps it and records the label and score as `reason`; `allow` decisions are recorded only then (D-673). `AbortAgentError` gives `verdict: terminate` and the existing aborted `pass.end` |
| `executor_gate` | Mandate, Glitch, Munim, aiAuthZ, Interbolt, Progent's executor | runs the defence's **own** executor unmodified. Dispatch and results are observed through `RecordingFunctionsRuntime` (which sees what actually ran) and the new tool messages. A call that did not reach the runtime and whose error matches the entry's `denials` matcher becomes `tool.result {status: denied, decided_by: def0}` with the text as reason. Stock invalid-call texts stay `invalid`. Anything else is a note `agentdojo/defence_unclassified_non_execution`: no decision is invented |
| `aux_llm` | MELON's masked run; later DRIFT, Progent, DCA | gives the defence an LLM element or client built by `build_llm` on the recording transport, bracketed `role: auxiliary, actor: def<n>`. A defence that builds its own client needs a port (MELON) |

`CaptureHooks` gains `decision(actor, subject, verdict, reason=None, original=None, subtype=None)`, a thin wrapper over
`emit("decision", …)`. This is a harness change only: the capture format is unchanged.

### 3.5 The capture: `capture/0.1` unchanged

Everything in §3.3–§3.4 uses existing event types and members. Embedding requests (MELON) are ordinary
`llm.request`/`llm.response` exchanges with `endpoint.path = /v1/embeddings` and `role: auxiliary`. The wire is
recorded as for chat; only the mapper must learn the form (§3.6).

**When `capture/0.2` would be needed.** Only for defences whose actions have no event type:

- **CaMeL:** an interpreter issues tool calls that no assistant message asked for, under capability labels;
- possibly DRIFT's memory isolation, if its ordering must be shown as a step.

These are third-set items, and a `capture/0.2` would be a user decision then (as in D-656, it is not proposed now).

### 3.6 Mapping and the evidence rules (core, class 1)

The existing machinery covers most of it: decisions, denials, auxiliary calls, defence actors, `task.defense_id`. The
capture mapper needs four additions:

1. **Defence-authored messages.** A `defence_message` note sets the message's actor to `def0`, for example
   `repeat_user_prompt`'s repeated user turn or `tool_filter`'s prompt and reply. *As built:* rule
   `defence.message_by_defence@1` (class D) in the `defence` catalogue. Role stays verbatim
   (C.3.4: role is not authorship). Without the note, these messages would be attributed to the user (prompt) or the
   agent (filter reply).
2. **Embedding exchanges.** An `llm.request` to an embeddings path becomes a `model_call` by `def0` whose input is not a
   message list. Its `input` is empty, and the request and response blobs are kept. It is never reconciled with
   assistant messages. *As built:* the request records `n_messages: 0` and `input_at: []`; MELON's masked re-run, built
   from its own conversation, cites `defence.detached_input@1`.
3. **Denial by declared text** (executor gates): new rule `defence.denial_declared_text@1`, class **D**, in the
   `defence` catalogue (D-677). The non-execution is observed (O); attributing it to the defence rests on the
   registry-declared text (`denials`), the same
   evidence as the import hook `defence_denial_message@1` (class I there, because imports do not observe
   non-execution).
4. **`allow` decisions with reasons** (if D-673 is accepted): mapped as observed verdicts, never inferred from unchanged
   content.

**Evidence rules kept:**

- **No relation from order or shared context.** A decision links to its subject by `occ`, never by position alone.
- **No invented allow decisions.** Allow is recorded only where the verdict function was observed.
- **No invented timestamps.** Decision `t` comes from the recorder's clock around the observed call.
- **Aborted and denied runs are sealed and kept,** and failed executions are never filtered out of rates.
- **No new PROV statements outside the engine catalogue.** Decisions, defence actors and auxiliary calls already have
  PROV rules (import precedents: MELON, SEAgent, ROPE). The new rules (item 3, and the `defence_message` and embeddings
  shapes if they need rule ids) go into a catalogue (D-677).
- **No change to `aer/`, `prov/`, `validate/` or `corpus/`** is expected (invariant 5). If a catalogue home outside the
  default needs a `CATALOGUE_HOMES` line, that is the one-line exception precedent of D-472, recorded in AGENTS.md.
- **The live-versus-native check is unaffected.** The native log and the capture `pass.end` dump both hold the
  post-defence messages. MELON's masked runs are not in either message list; they are auxiliary.
- **SEM:** the injection-reached-agent marker reads model-visible content, which is post-decision, so a redacted
  injection correctly does not count as reaching the agent. To confirm with a fixture.

### 3.7 CLI, plan, refusals, preflight

- **`run`.** `--defence NAME` is checked by T0 against the registry and the live profile **before** spawn:
  - unknown name: exit 2;
  - known but refused (not allowed by the profile, unsupported suite, not provisioned, missing defence endpoint key,
    copyleft not enabled, `trust_remote_code`): exit 5, with the reason;
  - digest mismatch: exit 3.

  A `[plan] defence = …` goes through the same check, so a plan refusal is exit 5 too, not exit 2 (D-679).
- **`--defence-param K=V`** is allowed only for parameters the entry declares.
- **`--defence-endpoint NAME`** (D-675) is for defences with `aux_llm = "defence_endpoint"`: MELON's embeddings
  (OpenAI) now; DRIFT and Progent later. The worker environment allowlist (G.6.3) gains only that endpoint's key
  variable. Its preflight probes run as for the agent endpoint.
- **`backends build agentdojo --defence-assets ID[,ID…]`** provisions code and weights:
  - offline from the caches when present, else only with `--allow-network` and the user's yes;
  - hashes are recorded in the marker;
  - the run uses `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, and the T2 socket guard stays on.
- **Preflight.** A defence probe:
  - for classifiers, two canned strings (one benign, one an obvious injection) must give the expected labels offline;
  - for provisioned code, an import plus the structural check.
- **Canary.** An exception inside a defence element counts as an errored attempt.
- **`agentprov info --source agentdojo`** prints the allowed and refused defences with reasons, as N.2.9 already says.
- **Security.**
  - `trust_remote_code` is refused (PIGuard, the fork's detector call);
  - a Hugging Face token is used only at build time for gated weights, never passed to T2;
  - `AGENTDOJO_DEFENSE_PLUGINS` stays out of the worker environment (it already does);
  - third-party defence code runs in T2 under the existing containment.

### 3.8 GUI: the Backend picker and the catalogue

- **The catalogue** (D-652, `agentprov-backend-catalogue/0.1`) gains a `defences` array beside `attacks`:

  ```json
  {"name": "transformers_pi_detector", "provider": "builtin", "licence": "MIT",
   "refused": null | "reason", "needs": ["--defence-assets transformers_pi_detector"],
   "suites": ["*"], "aux_llm": "none", "cost": {"extra_calls_per_step": 0}}
  ```

  The worker reports what the installed environment can build (importable, assets present). T0 merges this with the
  registry's allowed and refused list, so the GUI never offers a defence that T0 would refuse. The format id gains a
  member, so it becomes `/0.2` or the member is optional (GUI session's call).
- **The Run-live form, step 3** (GUI design §8.1).
  - "Defence" becomes a picker filled from the catalogue. Each entry shows its provider (built-in, provisioned code,
    port), its licence, and what it needs: assets, a defence endpoint key, suites.
  - Refused entries are shown disabled with the reason, as attacks are today.
  - A port shows a "ported" badge with the must-not-claim text.
  - A copyleft entry shows its licence and is enabled only when D-676 allows it.
- **Environment status, step 1.** Shows the defence assets each environment has. "Build environment" can add
  `--defence-assets` as an R2 job that asks for the download yes.
- **Estimate (§8.3).** Uses the entry's declared `cost` prior, for example MELON as about 2× agent calls plus embedding
  calls. It is labelled as a prior until stored corpora give measured counts.
- **Viewer.** A defence actor's decisions and auxiliary calls are already AER records, so they show in the step list.
  The `original` blob of a redaction can be shown on demand (content hidden by default, as for other corpus text).

The GUI parts are the GUI session's to build (class 0). This note only fixes the catalogue member and the CLI options
the parity test will see.

### 3.9 Tests (all scripted, offline)

For each defence in the first set:

1. **Structural:** the rewritten pipeline equals the stock (or provisioned) pipeline modulo the declared substitutions.
2. **Behavioural differential** (backend project, Python 3.12, `ScriptedTransport`): the stock defended pipeline and the
   instrumented one give equal native message lists, environments and outcomes, as JCS. For Mandate, against the
   authors' `build_pipeline`. For MELON, against the unpatched element with a scripted client injected by the test.
3. **Capture → AER:** fixtures under `tests/fixtures/capture/defence/` map, validate in release mode, agree live versus
   native, and re-map byte-identically.
4. **Evidence:**
   - a redaction has its `original` blob and the right subject;
   - a denial has a decision and no `tool_execution`;
   - auxiliary and embedding calls are not reconciled;
   - defence-authored messages carry `def0`.
5. **Offline and identity:**
   - the PI detector loads under the socket guard with the offline variables;
   - a changed weights or provisioned-file digest gives exit 3.
6. **Refusals:** exits 2, 5 and 3 as in §3.7, from both the flag and a plan.
7. **Secrets:** the embeddings key never appears in any artefact.
8. **GUI parity:** the new options appear in the option table.

## 4. Build plans

**Byte classes** (memory note stage-digest-scopes, to re-check after D-451):

- **Class 0, outside every stored stage digest:** `backends/`, `capture/` (format unchanged), `cli/`, `gui/`, `tools/`,
  `tests/`.
- **Class 1:** any file under `src/agentprov/adapters/agentdojo/`, including profiles, tables, the capture mapper and
  rules. This moves the agentdojo-family aer and manifest code digests of every agentdojo-family corpus, not only live
  ones. It is therefore held and landed by the orchestrator, ideally before the regeneration round, so the round
  carries it (D-677).

### 4.1 WP-0: shared machinery (needed by every pick)

| Part | Files | Class | Downloads |
|---|---|---|---|
| Harness | `backends/shared/.../{runner,defences,recorders,session,identity,worker}.py`: `build_defended_pipeline`, tree rewrite, the 5 recorders, `CaptureHooks.decision`, catalogue `defences[]`, guarded-name extension, preflight probe | 0 | none |
| Backend tests | `backends/agentdojo/tests/test_defended_*.py` (structural and differential), `backends/autodojo/tests/…` | 0 | none |
| CLI | `cli/run.py` (registry check, exits, `--defence-param`, `--defence-endpoint`), `cli/backends.py` + `cli/live/envs.py` (`--defence-assets`, marker, `--offline-check`), `cli/info.py` | 0 | none |
| Core (held) | `tables/live_defences.toml`; `agentdojo-live` v2 and `autodojo-live` v2 (profile `refuse` and allow lists; v1 archived, because scratch corpora recorded it, per the D-31 criterion); `capture_mapper.py` items 1–4 of §3.6; rules; fixtures; tests | **1** | none |
| Spec | D.10.11 "Defended pipelines" (reserve the section), D.10.7 items, N.2.1b, N.2.10, I.4 NC-LIVE-03 (D-674), K test rows, GUI design §8.1 | 0 | none |

### 4.2 WP-1: AgentDojo built-ins (`agentdojo` backend, provider `builtin`)

- **`repeat_user_prompt`, `spotlighting_with_delimiting`.** `prompt_wrapper`. Spotlighting changes the system message,
  so the system text actually sent is recorded through the wire and a `note` digest. `identity.default_system_prompt_sha256`
  stays the benchmark default. No downloads.
- **`tool_filter`.** `tool_list_filter`. It is refused on a non-OpenAI-class element: stock raises, and under D-656's
  direct Anthropic endpoint the profile marks it refused. No downloads.
- **`transformers_pi_detector`.** `output_filter`, wrapping `detect` to observe score and label. Device CPU (recorded).
  It never aborts as stock configures it (`raise_on_injection=False`); the abort path is still recorded if a later
  entry sets it. Downloads (D-672):
  - a new dependency group `defences = ["agentdojo[transformers]"]` in `backends/agentdojo/pyproject.toml`; a lock
    change, so a new environment name `agentdojo-<lock8>` with an offline rebuild once the wheels are cached;
  - `torch` (macOS arm64 wheel, about 70–80 MB) and `transformers` (about 10 MB) plus their small dependencies;
  - `protectai/deberta-v3-base-prompt-injection-v2` at a pinned revision: `model.safetensors` (about 0.74 GB) and the
    tokenizer and config files, each pinned by sha256. Sizes are approximate, to confirm at fetch, and the model
    card's licence is to be recorded then (expected Apache-2.0, not verified offline).

### 4.3 WP-2: MELON (`agentdojo` backend, provider `port`)

- **Code.** Provision `src/agentdojo/agent_pipeline/pi_detector.py` from the MELON pin `71d99dff` (local in staging; the
  blob SHA-1 and sha256 are recorded). Its imports are public AgentDojo modules (`base_pipeline_element`, `errors`,
  `functions_runtime`, `types`) plus `numpy`, `openai` and `httpx` (checked by reading; not yet imported against stock
  0.1.35).
- **Port patch** (small, MIT, declared as `agentdojo.defence_port@1`):
  1. replace the hard-coded `OpenAI(api_key=os.environ["OPENAI_API_KEY"], http_client=…proxy="http://127.0.0.1:7890"…)`
     with a client built by the harness on the recording transport for the defence endpoint;
  2. route the masked re-run (`self.llm.query` at `:770` and its variants) through an `aux_llm` handle (role
     `auxiliary`, `def0`). The real step (`:685`) stays the agent call: MELON is the agent's model step in its tool
     loop.

  With a differential test against the unpatched element (scripted clients), the port is `behaviour_preserving`
  (D-674).
- **Arms:** `melon`, `melon_at`, `melon_sm`, `melon_r`. Refused: `melon_rp` (absent at the pin).
- **Recorders:** `output_filter` for the sentinel replacement; `aux_llm` for the masked runs and embeddings. MELON-R's
  sanitising rewrites become `modify` decisions with `original`, so the live corpus records what the imported one
  cannot (precheck PC-melon-03/04).
- **Needs:**
  - `--defence-endpoint openai` (embeddings; `OPENAI_API_KEY`), even when the agent runs elsewhere (D-675);
  - core mapper item 2 (embeddings).

  One small download: `numpy` is imported by the file and is **not** installed in `agentdojo-79922295` (checked).
  It goes into the same `defences` dependency group as D-672, a wheel of a few MB.
- **Cost:** about two agent-model calls per tool step plus one to two embedding calls (estimate). Banking, as the
  imported runs, keeps it cheap: 160 cells per arm.

### 4.4 WP-3: Mandate (`agentdojo` backend, provider `provisioned`)

- **Code.** Provision `agentdojo_mandate_eval.py` from the bare cache (`jwilliamsc/mandate-agentdojo-eval@fa62a977`,
  blob present). Use its `_make_mandate_executor(cap_floor, cap_factor, mode)`, not its `build_pipeline`, which builds
  its own LLM clients. The harness assembles the same structure; the differential test compares it with the authors'
  `build_pipeline` under a scripted LLM.
- **Arms:** `mandate_envelope`, `mandate_scoped`, `mandate_intent`. `cap_floor` and `cap_factor` are the script's
  defaults, recorded as `defence_params`.
- **Recorder:** `executor_gate`, with `denials` matchers taken from `gate_decision`'s reason strings (a class-D rule).
  Banking only; other suites are refused.
- No downloads, no extra model calls.

### 4.5 Second-set notes

- **AutoDojo built-ins.** The same `builtin` path on `autodojo`. The registry maps the fork names. The fork's
  `TransformersBasedPIDetector` passes `trust_remote_code=True` for every model, so on the fork even `protectai` must
  use an entry that constructs the classifier without it, or stay refused (D-678).
- **Authority caps.** Provision `run_new_models.py` and the codebook CSVs from the Zenodo zip in staging. The raw
  member's digest is recorded; nothing is extracted to disk outside the provisioning copy. `tool_list_filter`.
  `autoconfirm` is a `prompt_wrapper` if it only appends text (to check).
- **Glitch.** Provisioned `GlitchToolsExecutor`; `executor_gate`. Its `_patch_anthropic_call` and `_patch_openai_retry`
  are not applied. A differential test shows they do not affect gate decisions.
- **ROPE.** First read `src/rope/*` imports (bare cache, offline). If it needs only the AutoDojo fork at `aa458794`, it
  is a provisioned add-on to `autodojo` with a lock change (`jsonschema`, `google-genai`: downloads). If it needs its
  vendored AutoDojo revision, it becomes its own fork-pinned backend `rope`. The cached router scopes are provisioned
  as data. Coordinate suite registration with the AgentDyn backend session.

### 4.6 What is *not* changed

- `capture/0.1`, `aer/0.1` and the frozen `prov/compat/adprov_v2_3/` are not changed.
- Import-side profiles and hooks are not changed: imported defence arms keep their class-I suffix inference.
- The core never imports `agentdojo` or defence code (invariant 7). Recorders live in `agentprov_backend`.

## 5. Decisions (D-670–D-679; all recommendations approved by the user 2026-10-22, except D-677's timing: the class-1
core part lands **after** the regeneration round as a recorded version bump)

| id | Decision | Recommendation |
|---|---|---|
| D-670 | Adopt the `--defence` architecture: a registry table pinned by the live profiles; provider kinds builtin, provisioned, port and fork; tree rewrite plus five recorders; one defence per plan; `capture/0.1` unchanged | yes |
| D-671 | First build set | the 4 AgentDojo built-ins (3 with no download first, the PI detector after D-672), Mandate (3 arms), MELON (4 arms). Alternatives: (i) built-ins only; (ii) add authority caps now (cheap) |
| D-672 | Downloads: `torch`, `transformers` (PI detector) and `numpy` (MELON) wheels into a new `defences` group of the `agentdojo` backend lock, plus the pinned `protectai/deberta-v3-base-prompt-injection-v2` revision (about 0.75 GB), provisioned at build, offline at run, CPU | yes (one consented fetch; logged in `acquisitions.jsonl`) |
| D-673 | Record `allow` verdicts with label and score where the defence's verdict function is observed (every classifier check), not only deny, redact and terminate | yes: needed for false-negative and threshold analysis; more records, all observed |
| D-674 | Ported defences: allowed only for recording or environment coupling, never for decision logic; declared `agentdojo.defence_port@1`; new must-not-claim **NC-LIVE-03** ("the authors' released implementation as run", for any session with a port item) | yes; MELON is the first port |
| D-675 | Defence endpoints: `--defence-endpoint NAME` with its key added to the T2 allowlist only when configured | yes; needed for MELON (OpenAI embeddings), later DRIFT and Progent |
| D-676 | Copyleft defences (aiAuthZ, Munim, gate, later llm-lock): run them only from provisioned pins in the environment, never copied into the repo; live corpora licensed as the user decides (U-03). Or exclude them from live runs | defer; not in the first set. Decide before the second set |
| D-677 | Core placement and timing: the new rules go in a **new small catalogue** (`defence`, home under `adapters/agentdojo/rules/`) rather than the shared `agentdojo` catalogue, so imported corpora's catalogue digests do not move. The class-1 core branch is held; the orchestrator decides whether it lands before the round (preferred, so the round's regeneration carries the code-digest move) or after it with a planned bump. ROPE: AutoDojo add-on versus own backend, after the import check | yes |
| D-678 | Weights policy: refuse `trust_remote_code` (PIGuard, the fork detector's call). Gated weights (Llama-Prompt-Guard-2) need the user's acceptance of the model licence and an HF token at build only | yes; affects the second set only |
| D-679 | Align exit codes: a plan whose defence is refused exits 5 (T0 checks before spawn), not 2 (`plan_refused`) | yes (class 0) |

**GPU and local models.** The first set needs **no GPU and no local model server:**

- the PI detector runs on CPU, with the device recorded;
- MPS or CUDA only by explicit choice, because accelerator kernels can change scores between runs.

Later picks that need GPUs or local servers: AutoDojo's `datafilter` (a CUDA causal LM), DCA's and gate's Ollama arms,
memo-ozdincer (multi-GPU 70B), EnvironmentOptim, Tacit collection. None is recommended now.

**Licences of the first set.** All MIT:

- AgentDojo: (c) 2024 Debenedetti et al.
- Mandate: "Mandate Labs"; the publisher is unverified, which the profile already notes.
- MELON: the repository carries the upstream MIT text and no line of its own. Attribution goes to the fork owner and
  to the MELON paper, as in the import profile.

The classifier's model-card licence is checked at fetch (D-672). Model-provider terms on redistributing outputs stay
unassessed, as for every live corpus.

## 6. Downstream effects (CLAUDE.md rule 10)

- **AER digests:** none for stored corpora from the harness branch. The core branch moves the agentdojo-family aer and
  manifest code digests (class 1, D-677). AER bytes of imported corpora are unchanged if the rules go into the new
  catalogue. Live scratch corpora recorded with `agentdojo-live` v1 keep it (archived).
- **PROV output:** unchanged for imports. Golden live fixtures gain defended scenarios; the undefended ones are
  unchanged unless the shared catalogue is used.
- **Compat gate (`adprov_v2_3`):** untouched.
- **Corpus manifests:** live manifests carry `defense_id` and the new instrumentation items; nothing else changes.
- **Environments:** `agentdojo-79922295` stays valid for undefended runs. Adding the `defences` group makes a new
  locked environment. Both can be registered.
- **Manuscript:** live defended runs become possible claims only after U-10 real-model consent and NC-LIVE-02. Ported
  defences carry NC-LIVE-03. The datasheet states provider kind, pins and weights digests per defence.
- **Other sessions:**
  - **GUI** (catalogue member, picker, options);
  - **AgentDyn backend** (its fork's defences use the same registry: builtin entries on that backend);
  - **D-656** (`tool_filter` refusal on the Anthropic element);
  - **regen-plan** (timing of the class-1 branch).
