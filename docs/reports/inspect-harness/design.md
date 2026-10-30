# Live Inspect harness (`backends/inspect/`): design note

Status: **D-660–D-669 approved by the user as recommended (2026-10-22; DECISIONS.md)**; no code yet. Branch `claude/inspect-harness-agentprov-087ae8`, based on the
pre-round integration head `3dfaa19b`. Decisions are reserved as D-660–D-669 (§11). Nothing was downloaded and no model
was called. Benchmark code that is not in the repo or the fetch cache (WhistleBench's `highagency/`, ATIA's task code,
the control-arena fork) has not been read, so every statement about it is marked *to confirm after the code fetch*.

**Short answer.**

* One harness, built as one family of backend environments, one environment per benchmark. Inspect versions differ
  between the benchmarks, and the importer accepts only exact producer versions (D.9.0).
* AgentHarm is the pilot. ControlArena stays out of v0.1, because it needs Docker and real-effect tools (G.6.3).
* "Run, then import" gives an AER with `mode: import` and `by: source` evidence. Those are Inspect's own records of the
  run, held in a separate live corpus. I recommend also recording the wire bytes from the start, stored but not
  mapped, so that a later class-1 step can raise model-call evidence to `O:capture`.
* Everything under `backends/inspect/`, the CLI and the env/identity code is class 0. Two parts are class 1 and go on
  a held branch: the new live profiles (files in `adapters/inspect/`), and a native-log variant of the live session
  pipeline in `adapters/runner/session.py`. Today's pipeline does not expand an `.eval`, assumes one execution per
  session and writes `mode: live` index rows (§5 item 3).

---

## 0. What exists today, and what the brief assumes

| Assumption | What the code and spec say |
|---|---|
| "The registry already lists a live AgentHarm part as planned" | Only as `agent-security-tools-survey` · `agentharm` with `live_status="planned"` and **no `backend`** (registry l.671–686). `run` refuses it ("no live capability", `cli/run.py` `_live_capability`). That part is the survey's third-party log deposit; the user's own runs are not that source's data. §5 proposes new `live` parts. |
| sandbox-exec makes the model call the only network access | **Not in v0.1.** G.4.10 and `cli/live/sandbox.py:12` say the profile "allows network; v0.1 does not restrict the host". The only host limit is `check_base_url` against `endpoints.toml`, which is configuration, not containment. §3.2 proposes a way to enforce it. |
| The `.eval` "goes through the existing importer unchanged" | The reader accepts a log only if `eval.packages.inspect_ai` **exactly** equals a string in the profile's `producer_band` (`dialect.py:216–225`). Otherwise the whole container becomes one `select.dialect_planned` row. So a live corpus needs a profile whose band names the pinned version. A new profile is a file in `adapters/inspect/`, which moves the inspect adapter digest: **class 1**. |
| The D-652 catalogue can carry the Inspect tasks | `agentprov-backend-catalogue/0.1` (branch `gui-g3`, 264db810) is AgentDojo-shaped: suites, user/injection tasks, attacks. `checked_catalogue` rejects any other format. Inspect needs tasks, task parameters, solvers, scorers and judge roles (§2.6). This needs agreement with the GUI session. |
| The live path can be reused as it is | `agentprov run` → `Campaign._ingest` → `LiveSessionPipeline` expects a `capture/0.1` log in every session. It checks the `agentdojo/identity_digests` note and maps through the profile's capture mapper (`staging.py:251–290`, `adapters/runner/session.py`). T0 identity (`cli/live/envs.py`) hard-codes the distribution `agentdojo` in `WATCHED_DISTRIBUTIONS`, `expect()`, `check_hello` and the build output line. The backend id lists in `backends.py:78`, `envs.py:71`, the GUI and CI name only `agentdojo` and `autodojo`. |

Other facts that shape the design:

* **H.1.1(2):** live and imported executions must not share a corpus, because their attesting parties differ. A
  run-then-import corpus is its own corpus, separate from the imported AgentHarm corpora.
* **D.9.5 deviation 1:** the Inspect mapper emits no `model_call.request`/`response`. Inspect's `ModelEvent.call` is
  the provider SDK's condensed request, not the wire bytes.
* **D.9.11 item 4:** without `log_model_api=True`, Inspect keeps `call` only for the first few calls per model, and
  the mapper declares `/params/transmitted` lost. A live run controls this setting, so it should set it.
* **G.6.3 (spec text):** "Any future backend whose tools have real effects (shell, browser, file system) MUST run
  inside a container or VM sandbox. This is out of v0.1 scope."
* The uv cache holds **no** `inspect_ai`, `inspect_evals` or `control-arena` wheel. Every environment below needs a
  download. The local clone `AgentPROV-upstream/inspect_ai` is at `5d97e38` (2026-10-06), shallow, blob-limited, and
  has none of the producer commits. The fetch cache holds `inspect_ai@53c1fa98` (bare, depth 1) and only the LICENSE of
  `ai-safety-institute/AgentHarm@e23b3fe6`.

---

## 1. Scope, order and version pins (D-660, D-661)

### 1.1 Order

| # | Benchmark | Why at this position | Needs Docker? | Tools with real effects? |
|---|---|---|---|---|
| 1 | **AgentHarm** (`inspect_evals/agentharm`, `agentharm_benign`) | Three imported sources, the smallest tool surface (pure-Python simulated tools), dataset on HF, known judge, token priors from stored corpora (§6) | no | no (simulated tools; the bundled-file tools read packaged files) |
| 2 | **WhistleBench** (`legobridge/whistlebench` `highagency/`) | One imported source (9,200 samples), simulated corporate tools, LLM-graded | *to confirm* (tool code not fetched) | *to confirm*; the tool names in the logs (`write_file`, e-mail tools) suggest simulated tools |
| 3 | **ATIA** (`mattngyn/atia_benchmark`) | Small (123 samples), but multimodal: its only producer used `google/gemini-2.0-flash`, which needs a Google endpoint (not in `endpoints.toml`) or an OpenRouter route that accepts audio and video | *to confirm* | *to confirm* |
| — | **ControlArena** (`control_arena`, setting `vibe_coding_persistent`) | **Out of v0.1** (proposal). The coding setting runs agent shell and file tools inside Docker sandboxes, which G.6.3 places out of v0.1 scope. Docker is a containment boundary of its own (§3.3). | yes | yes |

The pilot covers AgentHarm end to end (build, scripted tests, a capped real probe after the user's yes). Each later
benchmark adds one environment, one live profile and one catalogue adapter. The harness code is shared.

### 1.2 Version pins: match an imported producer

Each live profile's `producer_band` must name the exact version the environment installs. I propose pinning each
environment to a producer the importer **already maps**, for three reasons:

* the mapper's behaviour at that version has been exercised on real data (trial imports);
* regeneration items 12/16 and U6 verified producer code ranges, recorded in `acquisitions.jsonl`;
* the live corpus stays comparable with the imported one, with the same harness code and log shape.

| Benchmark | `inspect_ai` | Benchmark code | Matches imported producer | Notes |
|---|---|---|---|---|
| AgentHarm | **0.3.263** (PyPI) | **`inspect_evals` 0.20.0** (PyPI; *to confirm it is a published release*) | `kexin-xu-01-agentharm` (band `0.3.263`, `inspect_evals 0.20.0` in its headers, judge `openai/gpt-4o-2024-08-06`) | Rejected: the survey's `0.3.247.dev69+g53c1fa98b`. It is a dev build, not on PyPI. Reproducing its version string from a depth-1 clone would need `SETUPTOOLS_SCM_PRETEND_VERSION`, which writes a producer string we did not observe being built. |
| WhistleBench | **0.3.130** (PyPI) | `legobridge/whistlebench@9c27637c` (the logs' pin), `highagency/` package | `whistlebench` (band `0.3.130`, `0.3.134.dev31+geb46eef8`) | 0.3.134.dev31 is a dev build. 0.3.130 is the release in the band. |
| ATIA | **0.3.112** (PyPI) | `mattngyn/atia_benchmark@cc71caf5` (the logs' pin) | `atia-benchmark` (band `0.3.112`) | The adversarial media inputs are in the repo, outside the logs pin (size *to confirm*). |
| ControlArena (deferred) | 0.3.159 | `josh-hills/control-arena-persistent-state-eval` (commit *to find*) + `control-arena` | `controlarena-persistent` (band `0.3.159`) | Only if the user accepts Docker (§3.3). |

**Transitive dependencies.** Every backend lock shares `exclude-newer = 2026-10-07T00:00:00Z`
(`test_supply_chain.py` enforces this). Under that cutoff, resolution picks 2026 SDKs (for example the `openai` 3.x line
on httpx2), which old Inspect releases were never run with: 0.3.112 is from mid-2025. Each environment therefore gets
upper-bound constraints that match its producer's era: `openai`, `anthropic`, `google-genai`, `pydantic`, `httpx`. The
bounds are chosen from the producer release's own `pyproject.toml` at its verified commit. The global cutoff stays as it
is. If an old producer cannot be locked or imported under these constraints, that benchmark falls back to a newer
release in a new band. That would be a class-1 profile choice, reported before it is made.

**Rejected:** one environment with one modern `inspect_ai` for every benchmark. It is simpler to operate, but:

* the live logs would fall outside every verified producer range;
* benchmark code written against 0.3.112/0.3.130 may not run on it;
* comparisons with the imported corpora would mix harness versions.

---

## 2. The environment (D-662, D-663)

### 2.1 Layout

```
backends/inspect/
  pyproject.toml           # agentprov-backend-inspect: the harness package, no benchmark dependency
  src/agentprov_backend_inspect/
    worker.py              # agentprov-backend/0.1 ops for Inspect (framing reused from agentprov_backend)
    plan.py                # run-plan expansion: task, parameters, models, sample selection, limits
    catalogue.py           # tasks, parameters, solvers, scorers, judge roles (names and counts only)
    identity.py            # task registry digest, dataset digest
    providers.py           # recording http_client injection per provider (openai, anthropic, google)
    benchmarks/{agentharm,whistlebench,atia}.py   # per-benchmark adapters: task names, judge roles, dataset recipe
  envs/
    agentharm/{pyproject.toml, uv.lock, .python-version}     # inspect_ai==0.3.263, inspect_evals==0.20.0
    whistlebench/{pyproject.toml, uv.lock, .python-version}  # inspect_ai==0.3.130, whistlebench @ git commit
    atia/{pyproject.toml, uv.lock, .python-version}          # inspect_ai==0.3.112, atia_benchmark @ git commit
  tests/
```

* One **uv project per benchmark** (`envs/<benchmark>/`). Each has its own committed lock and pins Python 3.12, and
  each depends by path on `agentprov-backend-inspect`, `agentprov-backend` (`backends/shared`) and
  `agentprov-capture`. None of them installs the AgentPROV core (D.11.2, invariant 7).
* `backends/inspect/` itself is the **first backend with its own `src/`**. The AgentDojo shapes in
  `backends/shared/runner.py` (`CellSpec`, `AgentConfig.provider == "openai_compatible"`, `select_backend()` by PEP 610
  of `agentdojo`) do not fit Inspect. Putting Inspect into them would mean editing code that the GUI session (D-652) and
  the AgentDyn backend session also change. The harness reuses `backends/shared` for:
  * worker framing;
  * `ScriptedTransport`;
  * the recording transport and `WireRecorder`;
  * the redactor;
  * `netguard`.

  It needs one small hook there: a worker entry that takes a backend object, so that `worker.Worker` does not call
  `select_backend()` itself. This is a coordination item (§9).
* **Backend ids:** `inspect-agentharm`, `inspect-whistlebench` and `inspect-atia` in `BACKENDS`. Each descriptor sets:
  * `project = "backends/inspect/envs/<benchmark>"`;
  * `worker_module = "agentprov_backend_inspect.worker"`;
  * `profile = "<benchmark>-live"`.

  The GUI groups them under one "Inspect" picker entry. Rejected: a single id `inspect` with a `--benchmark` option.
  `BackendDescriptor` names one profile per backend, and the env name, marker, lock and identity are all per
  environment.
* **Env name:** `inspect-<benchmark>-<sha256(uv.lock)[:8]>`, following the same rule as `agentdojo-79922295`.

### 2.2 `backends build inspect-<benchmark>`

The same steps as N.2.10: `uv sync --locked --no-config --no-dev --link-mode copy [--offline]`, the `UV_*` scrub,
`UV_PROJECT_ENVIRONMENT`, the marker `AGENTPROV_ENV.json` from `building` to `complete`, `hello_once` with
`AGENTPROV_BLOCK_NETWORK=1`, and the sandbox-exec probe. The additions are below.

* **Dataset provisioning (AgentHarm).** `inspect_evals` downloads `ai-safety-institute/AgentHarm` from Hugging Face
  when it runs. At run time the network is the model endpoint only, so the dataset must be provisioned at build time:
  1. a pinned HF snapshot at revision `e23b3fe6…`, fetched once through the AgentPROV fetch layer (pinned, logged in
     `acquisitions.jsonl`; a download, so it needs the user's yes);
  2. copied, not extracted, into `<env>/share/agentprov/hf/`, laid out as a HF cache;
  3. each file's sha256 recorded in the marker (`datasets[]`);
  4. at run time the worker sets `HF_HOME` to that directory, plus `HF_HUB_OFFLINE=1` and `HF_DATASETS_OFFLINE=1`.

  The T2 environment allowlist (G.6.3) gains these three variables. That is a spec amendment and a class-0 change in
  `cli/live/worker.py`.
* **Other runtime fetches**, for example `tiktoken` BPE files used for token counting, or a version check: the build
  probe runs one scripted sample with the network blocked and fails on any attempted connection that `netguard`
  records. Every needed file is provisioned the same way as the dataset, or the code path is shown to be unused.
* **Inspect settings fixed by the harness, never by the user:**
  * `log_model_api=True` (D.9.11 item 4);
  * model cache off;
  * `log_dir` = the session's staging directory;
  * `log_format="eval"`;
  * `display="none"`;
  * `fail_on_error` per the plan;
  * `retry_on_error=0` (a re-run is a new attempt, D5);
  * no `eval-retry`.

  Each one is declared as instrumentation (§4.3).

### 2.3 Identity (T0 and `hello`)

T0 computes the identity before spawn, without importing anything, and checks it against `hello_ok` (D.10.6). The
fields:

| Field | Content |
|---|---|
| `distributions` | `inspect_ai`, the benchmark distribution (`inspect_evals`, or the git package for WhistleBench and ATIA), `agentprov-backend-inspect`, `agentprov-backend`, `agentprov-capture`. For each: the RECORD sha256 with every hashed row re-verified, METADATA `Version`, and the PEP 610 source (`{"kind":"pypi"}` for wheels, `{"kind":"git", repo, commit}` for the git packages, which must equal the profile pin). |
| `task_registry_sha256` | JCS sha256 of `{task name → {module, sha256 of the module file, registered solver and scorer names, default task parameters}}` over the benchmark's task modules. T0 hashes the files; the worker reports the registry it sees after import. This is the Inspect analogue of `guarded_sources`, and it is what tells a patched `inspect_evals` working copy apart from the release, as in kexin and fragfuse. |
| `datasets` | the provisioned snapshot: repo, revision, and the sha256 per file. |
| `lock_sha256`, `python` | as for the other backends. |

The parametrisation needed in `cli/live/envs.py` (class 0) is:

* `WATCHED_DISTRIBUTIONS` and the "primary distribution" become per-backend data;
* the data comes from the `BackendDescriptor` or from the live profile's `[family.inspect.live] pins`;
* `expect()`, `check_hello` and the build output line stop naming `agentdojo`.

The AgentDojo and AutoDojo environments must still pass `--offline-check` byte for byte. The test
`test_backends_cmd.py` pins this.

### 2.4 `hello`

`hello_ok.identity` carries the fields above. `worker` carries the Python version, `agentprov_backend_inspect`, the
`agentprov_backend` and `agentprov_capture` versions, and `inspect_ai`'s `__version__`. T0 refuses the run (exit 3,
`IdentityMismatch`) if `__version__` differs from METADATA or from the profile band. A band mismatch is caught before
any model call, not as a `dialect_planned` row after the run.

### 2.5 `plan`

A run plan, format `agentprov-run-plan/0.1`, with an `[inspect]` table in place of AgentDojo's suites:

```toml
[plan]
backend = "inspect-agentharm"
format = "agentprov-run-plan/0.1"
[inspect]
task = "inspect_evals/agentharm"              # from the catalogue
task_args = { split = "test_public" }          # only parameters the catalogue declares; values checked by type
samples = { ids = ["1-1", "1-2"] }             # or { limit = 4, seed = 0 }; never "all" without an explicit count
epochs = 1
limits = { message_limit = 30, token_limit = 60000, time_limit_s = 600 }  # per sample
max_connections = 4
[agent]   # model + endpoint, as today (key variable name only)
[judges]  # one entry per judge role the catalogue declares, each with model + endpoint (§6)
```

`plan_ok` returns:

* the cells, one per (task, task_args, agent model, judge models), each with its sample id list;
* the `plan_sha256`;
* the **per-cell call bounds** that the consent and the estimate need (§6).

`run_cell` runs one Inspect `eval()` in process. It uses the Python API rather than a subprocess of the `inspect`
CLI, so that the harness can pass the recording `http_client` and the fixed settings. The cell leaves one `.eval` in
the session directory. An Inspect sample is one AER execution, as for the imported sources (D-340).

### 2.6 `catalogue` (with the GUI session, D-652)

The catalogue lists, by name and count only:

* tasks, each with:
  * declared parameters (name, type, default, allowed values when the task code enumerates them);
  * the sample count per split;
  * the default solver and the solvers it offers;
  * scorers, each with its **judge roles** and their default models;
  * the tool-definition size in characters, used by the estimate;
* the provisioned dataset revision.

There is no task text, no behaviour prompt and no target function: AgentHarm's prompts are harmful requests and stay in
the environment. Two options for the format:

* **(a)** A new format, `agentprov-inspect-catalogue/0.1`, that the GUI dispatches on.
* **(b)** A `kind` member and optional `tasks[]` in `agentprov-backend-catalogue/0.1`.

I recommend (a). The 0.1 format is already used by a test against a real environment, and `checked_catalogue` rejects
unknown formats on purpose. Either way, the GUI session owns the parser. I own the worker side and send it the schema.

### 2.7 `probe`

The same canned two-tool request as D.10.9, sent through Inspect's own provider client: the same element the run
uses, in a `probe` session that is never mapped. It is also sent once to **each judge endpoint**, because the judges
are paid calls on what may be a different host.

---

## 3. Containment (D-664)

### 3.1 sandbox-exec, as for the other backends

The worker runs under the G.4.10 profile:

* writes are allowed only in staging, the T2 home and `/dev`;
* reads of the repository, the credential locations and `.env*` are denied;
* the probe must pass before the first real-model run.

Inspect writes its log into `log_dir`, which is staging. It also writes caches under `~/.cache/inspect_ai` and
`~/.inspect`, and `HOME` is the T2 home, so those caches land there. The harness sets `INSPECT_CACHE_DIR` (or its
equivalent at the pinned version, *to confirm*) inside the T2 home.

### 3.2 "The model call is the only network access": not enforced today; a proposal

sandbox-exec cannot filter by host name. It filters by address and port only, and in practice the only useful forms
are `localhost:*` and `*`. Two options:

* **(a) Keep v0.1 as it is.** The host is allowed by configuration (`check_base_url`), and the network is open to the
  T2 process. This is what AgentDojo and AutoDojo do today. It is honest only if the design and the consent say
  "endpoint allowlisted by configuration, not by containment".
* **(b) Enforce it (recommended for Inspect, then for every backend).**
  1. The profile gains `(deny network-outbound)` and `(allow network-outbound (remote ip "localhost:*"))`, plus the
     usual exception for the Unix-socket DNS path.
  2. T0 runs a small **CONNECT-only forwarding proxy** on a loopback port. It accepts `CONNECT host:443` only for the
     hosts of the selected agent and judge endpoints in `endpoints.toml`, tunnels the TLS bytes without decrypting
     them, and logs every refused attempt with host and time, never payload.
  3. The worker gets `HTTPS_PROXY=http://127.0.0.1:<port>`.

  Wire recording (§4) is unaffected: it happens inside the process, before TLS. The probe gains an expectation: a
  direct connection to a non-allowlisted address fails, and a CONNECT to such a host is refused.

  The cost is a proxy in `cli/live/` (stdlib `asyncio`, class 0, about 200 lines plus tests), a new profile digest
  (`PROFILE_SHA256` changes, so every environment re-probes), and a spec change to G.4.10 and G.6.3. Inspect is the
  first backend that runs third-party benchmark code from several upstreams, which makes enforcement worth more here
  than for the stock AgentDojo wheel.

### 3.3 Docker

AgentHarm, and probably WhistleBench and ATIA (*to confirm*), run without an Inspect sandbox. ControlArena's
`vibe_coding_persistent` setting runs the untrusted agent's shell and file tools in Docker containers through Inspect's
`docker` sandbox. Inside sandbox-exec that cannot work without access to the Docker socket. With socket access the
daemon becomes the real boundary, and it runs outside the sandbox with root-equivalent power over the VM.

The options for the user:

1. **Leave ControlArena out of v0.1 (recommended).** The imported 5,742-sample corpus stays its evidence.
2. A later phase with Docker as declared containment. Its parts:
   * `--containment docker`, a new value;
   * images pinned by digest and pulled at build time (a download), with `network_mode: none` for every service;
   * the T2 worker outside sandbox-exec but under a dedicated user;
   * the socket exposure recorded in the manifest;
   * a probe that proves the container has no network.

   This is a G.6.3 amendment and a security review in its own right.
3. Run the setting with Inspect's `local` sandbox inside sandbox-exec. **Rejected:** the agent's shell would run on the
   host under the T2 user, which is exactly what G.6.3 forbids, and it changes the benchmark.

---

## 4. Evidence class and wire recording (D-665)

### 4.1 What "run, then import" yields

The `.eval` passes through the unchanged `inspect.eval` reader and mapper, so the AER is:

* `mode: "import"` (the mapper writes it; AER-V26 requires a `capture` member for `mode: live`, and there is no
  capture log);
* every message, model event and tool event is `O` with `by: source`, which means Inspect's own record;
* `request`/`response` are not emitted (D.9.5 deviation 1).

What differs from an imported third-party log is **around** the AER, not in it:

* **Origins.** The raw objects get `capture` origins (`{"kind":"capture","session":<uuid7>}`), not a pinned git, HF
  or Zenodo origin. The session is ours.
* **Producer identity.** It is **verified**, not claimed: T0 checks the environment (RECORD digests, task registry,
  dataset digests) before the run, and the manifest records it. For an imported log, `eval.packages` is only the log's
  own claim.
* **Configuration.** It is known from the plan (`plan_sha256`, `O:config` where the mapper already uses `config`),
  not reconstructed from the header.

The caveats, each to be stated in the profile, the registry caveat and the datasheet:

1. **The observer is the process under test.** Inspect writes the log inside T2, alongside third-party benchmark code.
   The log is T2 output: untrusted, parsed through `agentprov.ingest`, secret-scanned. A benchmark or a compromised
   dependency could write anything into it. Without wire recording, nothing independent checks what the model was
   actually sent.
2. **Condensed calls.** `ModelEvent.call.request` is the SDK request after Inspect's processing. Attachments are
   deduplicated (`attachment://`), images may be condensed, and the API key is absent. It is close to the wire request
   but not the wire bytes.
3. **Inspect's own retries.** Provider retries inside the SDK or Inspect's retry loop show up only as errors that
   Inspect chose to log. With `retry_on_error=0` the sample-level retry is off, but SDK-level HTTP retries remain
   (`max_retries` per provider).
4. **Timing.** Event timestamps are Inspect's (`timestamp`, `working_start`). Event order is not time order, as for
   every Inspect source (`inspect.no_order_from_event_list@1`).
5. **Judges.** Judge calls are `model_call` records with the actor `judge<n>`, recorded under the scorer span, with the
   same evidence and the same caveats.

### 4.2 Wire recording: recommended, recorded and stored, mapped later

Options:

| | What | Class | Evidence gained |
|---|---|---|---|
| (a) | No wire recording | 0 | none; §4.1 is the whole story |
| **(b)** recommended | Record every exchange of the agent and judge clients with the existing recording transport into a `capture/0.1`-shaped log: `session.start` (backend `inspect-<benchmark>`, identity), `llm.request`/`llm.response` with redacted exact body blobs, `note`s and `session.end`. Store it as a **supporting** raw object of the session, chain-verifiable by `agentprov_capture`. Do not map it. | 0 (harness and staging only) | Independent, digest-chained bytes of what each provider was sent and returned, under T0's redactor and secret scan. Auditable today; the basis for (c). |
| (c) | (b) plus a class-1 mapper step: match each Inspect `ModelEvent` to a wire exchange (request digest, then response id) under a new rule, emit `request`/`response` as `O:capture`, and report mismatches (the live-versus-native check of D.10.4) | 1 (inspect mapper, rule catalogue; maybe `capture/0.2` if the span events matter) | `O:capture` request/response, a check of Inspect's log against the wire |

Notes on (b):

* **Injection.** Inspect's OpenAI-compatible and Anthropic providers accept a caller `http_client` (`model_args`) at
  the current HEAD. Whether they accept it at 0.3.112, 0.3.130 and 0.3.263, how the Google provider takes one, and
  whether a passed client leaks into the header's `model_args`, are all *to confirm on the pinned wheels*. If a
  provider cannot take one, its exchanges are recorded as `not_recorded` with a note, never silently skipped.
* **`capture/0.1` is frozen and AgentDojo-shaped:** passes, cells, a native TraceLogger. A session without
  `pass.start` is valid but carries the seal issue `no_execution_observed`. Because (b) does not map the log, that
  issue never reaches an AER. If (c) is later approved and needs real span events, that is the `capture/0.2` decision
  that is already open with the Anthropic endpoint session (D-656 Q1).
* **Cost:** none in tokens. It adds blob storage of about the size of the `.eval`'s own `call` payloads.

### 4.3 Instrumentation

Declared like D.10.7, in a session note and in the live profile's accepted list:

* `inspect.harness_settings@1` (§2.2's fixed settings, `harness_policy`); `@2` since D-740, which adds
  `max_retries=1` per model call (the `agentharm-live` profile accepts `@2` only);
* `inspect.recording_http_client@1` (`behaviour_preserving`);
* `inspect.transport_scripted@1` (`test_only`);
* `inspect.dataset_offline@1` (`harness_policy`);
* `inspect.preflight_probe@1` (`harness_policy`; the probe session only, D-742);

Every model is a new Inspect `Model` (`get_model(..., memoize=False)`, D-743): Inspect's memo key omits the injected
client. A cell with an errored sample is reported `incomplete`, with the note `inspect/samples_errored` (D-743).
* `inspect.egress_proxy@1` (`harness_policy`, if §3.2 (b) is adopted).

---

## 5. The import path (D-666)

1. **Registry.** New `live` parts, per D.11.8 (`evidence "n/a"`, `import_status None`, `live_status "planned"`,
   `backend`, `profile`, `requires=("backend:inspect-<b>",)`, the benchmark's semantics profile):
   * **`agentharm` · `live`**: a new source `agentharm` (the benchmark: `inspect_evals` agentharm and the HF dataset
     `ai-safety-institute/AgentHarm`). The three existing AgentHarm sources are other people's log deposits.
     `agent-security-tools-survey` · `agentharm` keeps its import part. Its `live_status="planned"` is dropped (set to
     `None`), with a note pointing to the new part. *User decision* (Q5).
   * **`whistlebench` · `live`** and **`atia-benchmark` · `live`**: new parts of the existing sources, whose canonical
     repos are the benchmarks.
2. **Profiles.** `agentharm-live`, `whistlebench-live` and `atia-live` in `adapters/inspect/profiles/`, each with:
   * `[import] dialect = "inspect.eval"` and `mapper = "inspect.eval"`;
   * `producer_band` = exactly the pinned version;
   * the source pins = the benchmark code and dataset pins (the env's identity is checked against them, D.11.9 item 8);
   * `[family.inspect.live]` (backend, pins, accepted instrumentation, refusals);
   * the quirks and redaction rules carried over from the imported profile of the same benchmark.

   `[family.inspect.live]` is a new table, so `family.schema.json` changes. **Class 1:** files in `adapters/inspect/`
   move the inspect adapter digest of every stored Inspect corpus (manifest `code_sha256`). They stay on a held branch
   (`inspect-harness-core`), and the orchestrator decides when they land.
3. **T0 mapping path: needs a runner change, so class 1.** `Campaign._ingest` already checks the staged files
   (discovery like `--input`, re-hash, secret scan, quarantine). `LiveSessionPipeline.ingest`
   (`adapters/runner/session.py:114–190`) is the right base: it stores every staged file with the origin
   `capture {session}` and runs one `container` map job through the profile's reader and mapper. Three of its
   assumptions do not hold for an Inspect session:
   * **No expand stage.** The staged `.eval` is a ZIP. The `inspect.eval` reader plans over *member objects* produced
     by the versioned `expand` stage (AD-12, `raw/members.py`). `ingest` passes the staged files as they are.
   * **One execution per session.** `ingest` returns `units[0]`, and the attempt bookkeeping is per session. An Inspect
     cell holds many samples, so many executions.
   * **Index rows say `mode: live`** with a capture `attempt` (H.3.1). The AER from the Inspect mapper says
     `mode: import`, so the index row and the AER would disagree.

   So the branch is a native-log variant of the pipeline: expand, then map in container mode with many units, then
   write index rows with the AER's mode. The variant is chosen by a `BackendDescriptor` field (`native_log = true`). It
   lives in `adapters/runner/` (aer stage code digest), which makes it **class 1**. It goes on the held branch with the
   profiles. The CLI side (`campaign.py`, choosing the variant and skipping the capture-identity check, which is
   replaced by the env-identity check in the session note) is class 0. Rejected: running `agentprov import --input`
   on the staging directory. The objects would get `local` origins, which the release validator rejects, and the
   secret-scan quarantine would be bypassed.

   *As built (2026-10-22, D-666):* the index rows are `mode: import` with `attempt: null`. A `mode: live` row must name
   the capture log as its primary artefact (`corpus.index.primary_role`), and the primary artefact here is the `.eval`.
   The attempt stays traceable through the `.eval`'s `capture` origin and the campaign ledger.
4. **Corpus.** One live corpus per (benchmark, scripted vs real). N.2.1b item 6 forbids mixing scripted and real-model
   sessions. The corpora are never mixed with the imported corpora (H.1.1(2)). The manifest records:
   * `producer.sandbox`;
   * the environment identity;
   * the plan digests;
   * `synthetic: true` for scripted runs (never released, `package --deposit` refuses them).
5. **Checks after import:** `validate` at every tier; `recompute --dry-run` (a live corpus is never re-mapped, D-43, so
   this re-derives SEM and PROV from the stored AER); and the quality report, adapted. The A3/A4/A6/A11 canaries read
   capture logs, so the Inspect equivalents (sample status, limit hits, judge failures) come from the AER.

---

## 6. Judges, scorers and cost (D-667)

Judge calls are paid calls, so they are part of the plan, the estimate and the consent:

* **Explicit judge roles.** The catalogue declares each scorer's judge roles. AgentHarm has a refusal judge and a
  semantic judge, both defaulting to `openai/gpt-4o-2024-08-06` as in the imported logs. WhistleBench has grader models
  (`gpt-4.1` and `gpt-5` in the sampled logs, *to confirm in code*). ATIA's scorer is *to confirm*.
* **The plan names each judge's model and endpoint.** There are no silent defaults: the plan expands the default into
  explicit values that the user sees. Each judge endpoint must be in `endpoints.toml`, and under §3.2 (b) it joins the
  proxy allowlist.
* **Consent** (N.1.11) lists every endpoint host, model and key *name*: agent and judges. It also lists the sample
  count, epochs, the per-sample `message_limit` and `token_limit`, and the estimate with an upper bound.
* **Caps.** Inspect enforces the per-sample `token_limit` and `message_limit`. The plan refuses any run without an
  explicit sample count. The estimate's upper bound uses the 90th-percentile tokens per sample.

**Priors from the stored corpora.** These are measured from AER usage in `ast-survey-agentharm-p10` (1,056 samples,
three local models; counts only, no text). Per sample:

| Split | Agent calls | Agent input tokens (mean / p90) | Agent output | Judge calls | Judge input | Judge output |
|---|---|---|---|---|---|---|
| harmful (`agentharm`) | 1.7–2.9 | 1.3k–4.6k / 4.4k–11.4k | 0.2k–1.9k | 1.2–1.5 | ~0.4–0.5k | ~0.4–0.5k |
| benign (`agentharm_benign`) | 3.3–6.1 | 4.9k–6.9k / 8.9k–12.5k | 0.5k–2.4k | 1.4–2.0 | ~0.5–0.8k | ~0.4–0.7k |

**Rough cost of one full `test_public` pass** (176 harmful + 176 benign = 352 samples). It uses the mean of the
figures above (agent about 4.4k in and 1.0k out per sample; judges about 0.55k in and 0.5k out) and the GUI price
table (`gui-g3`, as of 2026-10-21, USD per MTok):

| Agent model | Agent | Judges (gpt-4o-2024-08-06) | Total (mean) | Upper bound (×2.5 for p90) |
|---|---|---|---|---|
| openai/gpt-4o-mini | ≈ $0.45 | ≈ $2.2 | ≈ $2.7 | ≈ $7 |
| openai/gpt-4o-2024-08-06 | ≈ $7.5 | ≈ $2.2 | ≈ $10 | ≈ $25 |
| claude-sonnet-5-5 | ≈ $6.7 | ≈ $2.2 | ≈ $9 | ≈ $23 |
| claude-opus-5-5 | ≈ $13.4 | ≈ $2.2 | ≈ $16 | ≈ $40 |

These are planning figures only. The priors come from local open models, and frontier models refuse more harmful
requests, which shortens those samples. `plan` recomputes the estimate per cell from the catalogue's
tool-definition size and the priors table (D-653).

**The first real call** would be a separate capped probe: 4 samples (2 harmful, 2 benign), `gpt-4o-mini` as agent and
judge, `token_limit` 20k, expected under $0.05 and capped at $0.50. It needs the user's own typed yes in this window,
naming that probe. Nothing in this design runs it.

---

## 7. Licence and release (D-668)

| Live corpus | Inputs and their terms | Proposal for release |
|---|---|---|
| `agentharm` · `live` | AgentHarm data: MIT with an AI-safety use clause (HF card at `e23b3fe6`); `inspect_evals` MIT; the outputs are the user's runs, including model completions of harmful requests, and judge verdicts | **Its own restricted-use corpus (LIC 3)**, like the three imported AgentHarm corpora, and never mixed into a permissive deposit. **Private by default. No public release unless the user decides it separately**, because the AER holds the harmful prompts verbatim and any compliant completions. If it is ever released, the AgentHarm clause and its canary (if the dataset defines one, *to confirm*) are carried forward. |
| `whistlebench` · `live` | MIT code (`legobridge/whistlebench`), no separate data licence; outputs are the user's runs | U-03 default (proposal CC-BY-4.0 for the user's own runs), with the caveat "model-provider terms on redistributing model outputs". |
| `atia-benchmark` · `live` | MIT code; the adversarial media's provenance is unassessed (profile `unassessed`) | AER, SEM and PROV under U-03. The media objects are withheld at object scope until their provenance is assessed. |

Every live corpus also carries the provider terms of each agent and judge model in `unassessed`. Scripted corpora
(`synthetic: true`) are never released.

---

## 8. Tests (D-669)

* **Transport.** The **scripted transport through Inspect's real provider client** (`ScriptedTransport` under the
  injected `http_client` of the OpenAI-compatible provider) is the primary path. It exercises the same provider code,
  recording and staging as a real run. Inspect's `mockllm` is the fallback for unit tests of `plan` and `catalogue`
  only, because it bypasses the provider and the wire. Scripted judges use the same transport with a second script.
* **Worker protocol and identity tests** under `backends/inspect/tests/`:
  * hello, plan, catalogue, probe and refusal paths;
  * an identity mismatch (a patched task module changes `task_registry_sha256`);
  * the network blocked during a scripted sample;
  * no task text in the catalogue (a sentinel test with planted prompt text).
* **Core tests** (class 0):
  * `envs.py` parametrisation, with both existing environments unchanged;
  * the `run` status gate for the new parts;
  * the boundary test's backend list (`test_import_boundary.py:129`);
  * the supply-chain lists (`test_supply_chain.py`);
  * the proxy, if §3.2 (b) is adopted.
* **End to end** through the queue (`tools/suite_queue.py --class import`, ≤ 2 CPUs):
  1. `agentprov backends build inspect-agentharm` (offline after the approved downloads);
  2. a scripted 4-sample run (2 harmful, 2 benign; ids chosen by count, never quoted) into a scratch corpus under
     `~/.agentprov/migration-work/inspect-harness/`;
  3. `validate`, then `recompute --dry-run` (0 differences expected), then `verify --level chain`.

  The corpus is never sealed for release and is not under `~/.agentprov/corpora`.
* **Golden check.** The new profiles change no stored AER bytes for the imported corpora (their profile files are
  unchanged), but they move the inspect adapter digest. The held branch records that in the regen batch.

---

## 9. Ownership, coordination and downstream effects

| Change | Where | Class | Owner and coordination |
|---|---|---|---|
| Harness package, per-benchmark projects and locks, tests | `backends/inspect/**` | 0 | this session |
| Worker entry that takes a backend object; maybe a shared `Backend` protocol | `backends/shared/worker.py` | 0 | coordinate with the GUI session (D-652 adds `op_catalogue` there) and the AgentDyn backend session. A small patch, offered to both before I commit it |
| Catalogue format for Inspect | GUI parser; `run --catalogue` | 0 | GUI session owns the parser; I send the schema (§2.6) |
| Backend ids, env identity parametrisation, build output | `cli/backends.py`, `cli/live/envs.py`, `cli/run.py` (`BACKEND_REFUSALS`, the status gate), GUI `commands.py:294` | 0 | minimal; the GUI choice list goes to the GUI session |
| T2 env allowlist (`HF_*`), proxy (if (b)), sandbox profile change | `cli/live/worker.py`, `cli/live/sandbox.py` | 0 | new `PROFILE_SHA256`, so every environment re-probes (AgentDojo and AutoDojo included) |
| `BACKENDS` entries, new `live` parts, the survey part's `live_status` | `adapters/registry/__init__.py` | 0 at today's digest scopes (*to re-check after D-451 widens them to each stage's import closure*) | append-only; README generator re-run |
| Live profiles, `family.schema.json` `[family.inspect.live]` | `adapters/inspect/` | **1** | held branch `inspect-harness-core`; orchestrator lands it; regen-batch entry |
| Native-log variant of the live pipeline (expand, many units, index mode from the AER) | `adapters/runner/session.py` (+ `cli/live/campaign.py`) | **1** (runner) + 0 (CLI) | held branch `inspect-harness-core` with the profiles (§5 item 3) |
| CI matrix, `ci.yml` | `.github/workflows/ci.yml` | 0 | manual dispatch only (D-431) |
| Spec | D.12 or a new D.x section (reserved through `reserve_id.py`), N.2.1/N.2.10 backend lists, G.4.10/G.6.3 (proxy, Docker), C.13 note on live-produced imports | — | this session |

Downstream effects to state before each merge:

* no AER, SEM or PROV byte of a stored corpus changes;
* the inspect adapter `code_sha256` moves when the held branch lands;
* the sandbox profile digest moves if §3.2 (b) is adopted;
* the AgentDojo and AutoDojo environments must re-probe;
* no manuscript number changes.

---

## 10. Downloads this plan needs (each needs the user's typed yes, with size and source stated at the time)

| # | What | Source | Size |
|---|---|---|---|
| 1 | Lock resolution for `envs/agentharm` (index metadata only) | PyPI (`pypi.org/simple`) | small (index pages); a resolution, no wheels |
| 2 | The wheels the lock adds beyond the uv cache: `inspect_ai` 0.3.263, `inspect_evals` 0.20.0, and their missing dependencies | PyPI (`files.pythonhosted.org`) | reported exactly from the lock (count, bytes, sha256) before asking |
| 3 | AgentHarm dataset snapshot at `e23b3fe6…` | HF `ai-safety-institute/AgentHarm` | reported from the HF tree listing before asking (the dataset is JSON; expected to be a few MB) |
| 4 | WhistleBench task code, `highagency/` at `9c27637c` | GitHub `legobridge/whistlebench` (blob:none plus sparse checkout of `highagency/`) | from the tree listing |
| 5 | ATIA task code and inputs at `cc71caf5` | GitHub `mattngyn/atia_benchmark` | from the tree listing (the logs alone were 162 MB) |
| 6 | Steps 1–2 for `envs/whistlebench` and `envs/atia` | PyPI | from their locks |

Each is logged in `acquisitions.jsonl`. Every git read of a blob:none clone runs with `GIT_NO_LAZY_FETCH=1`. Nothing is
extracted to disk.

---

## 11. Decisions for the user (D-660–D-669)

| ID | Question | Recommendation |
|---|---|---|
| **D-660** | Scope and order | AgentHarm pilot, then WhistleBench, then ATIA. ControlArena out of v0.1. |
| **D-661** | Version pins | One environment per benchmark, each pinned to an imported producer: AgentHarm `inspect_ai` 0.3.263 + `inspect_evals` 0.20.0; WhistleBench 0.3.130 + `9c27637c`; ATIA 0.3.112 + `cc71caf5`. Era-matched upper bounds on the SDKs under the global `exclude-newer`. |
| **D-662** | Layout and ids | `backends/inspect/` harness package plus `envs/<benchmark>/` uv projects; backend ids `inspect-<benchmark>`; GUI groups them under "Inspect". |
| **D-663** | Identity and the worker ops | RECORD, PEP 610, `task_registry_sha256` and dataset digests checked by T0; `hello`, `plan`, `catalogue` (new format `agentprov-inspect-catalogue/0.1`, GUI to agree) and `probe` (agent and judge endpoints). |
| **D-664** | Containment | sandbox-exec as today, **plus** egress enforcement through a loopback CONNECT allowlist proxy (§3.2 (b)), for every backend. **No Docker** in v0.1. |
| **D-665** | Evidence and wire recording | Run, then import (`mode: import`, `by: source`, `capture` origins, verified producer identity) with the §4.1 caveats. **Record the wire bytes from the start** (§4.2 (b), stored, not mapped); mapping (c) is a later class-1 decision. |
| **D-666** | Import path and registry | A new source `agentharm` with a `live` part; `live` parts for `whistlebench` and `atia-benchmark`; the survey part's `live_status` dropped; new live profiles held as class 1. |
| **D-667** | Judges and cost | Judges explicit in plan and consent; caps mandatory; estimate from stored priors (§6). The first real call is a separate 4-sample probe with a typed yes. |
| **D-668** | Licence and release | AgentHarm live: restricted-use (LIC 3), private, no public release without a separate decision. WhistleBench: U-03. ATIA: U-03 with the media withheld. |
| **D-669** | Tests | Scripted transport through Inspect's real provider client; `mockllm` only for `plan`/`catalogue` unit tests; a 4-sample scripted run into a scratch corpus, then validate, recompute `--dry-run` and verify chain. |

**Questions that block work, in the order they are needed:**

* **Q1:** download yes for item 1, then item 2 (exact list and bytes reported after resolution) and item 3.
* **Q2:** D-664 (proxy or not; no Docker).
* **Q3:** D-665 (b) or (a).
* **Q4:** D-668.
* **Q5:** the new `agentharm` source and dropping the survey part's `live_status`.

Q2–Q5 can be answered after the pilot build starts. Q1 cannot.

---

## 12. Risks

* **Old producers vs 2026 SDKs.** 0.3.112 and 0.3.130 may not lock or run under `exclude-newer = 2026-10-07` even with
  upper bounds. If so, the fallback is a newer release in a new band, which is a class-1 choice reported before it is
  made.
* **`inspect_evals` 0.20.0 and the bundled-file tools.** The survey's logs show the `read_file` tool failing on every
  allowlisted call (`inspect_evals` #2439, D-582 `inspect.art.bundled_file_not_found`). The build probe runs one
  scripted sample that calls a bundled-file tool, and reports whether 0.20.0 has the defect. A live corpus with a
  known-broken tool needs the artefact catalogue entry, not a silent run.
* **Provider `http_client` at the pinned versions** (§4.2). If injection is not possible for a provider, the plan
  refuses that provider for wire-recorded runs, or records it as `not_recorded` (user's choice at D-665).
* **AgentHarm content in staging and logs.** Prompts are harmful requests. Nothing in this harness prints sample text.
  Reports cite counts and ids only, and any display goes through `quote_untrusted`.
