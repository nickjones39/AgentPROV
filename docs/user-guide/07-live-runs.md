# 7. Live runs

A **live run** executes a benchmark against a model, records what happened as raw evidence, and turns that evidence into
the same AER, SEM and PROV as an imported log. This chapter explains how to plan a run, what a run refuses and why, what
it records, and what to do afterwards. It is written so that you can follow every step without running a model:
**every transcript here comes from the scripted transport or from a dry run.** For the shape of a real run it cites the
live pilot's report.

> **Status on this build.** `agentprov info` lists five live parts:
>
> | Part | Live status | Real-model runs so far (from its caveat) |
> |---|---|---|
> | `agentdojo · live` | `partial` | local, OpenRouter and Anthropic (the 2026-10-22 pilot) |
> | `autodojo · live` | `partial` | local |
> | `agentdyn · live` | `partial` | local |
> | `agentharm · live` | `partial` | OpenRouter, a 4-sample probe (2026-10-23) |
> | `rope · head` (live) | `planned` | none; no backend in this build (`agentprov run rope` exits 5) |
>
> There is no `gated` status word: **`partial`** means that real-model runs are admitted for a stated subset (below), and
> the caveat records which endpoint classes have actually been run. A `planned` part admits scripted runs only (exit 5
> for a real model). **Live corpora cannot be sealed in this build**, so no live corpus supports a "Live Capture" claim
> ([After a run](#after-a-run)).

## What a live run is, and what it records

A backend is a separate uv project on Python 3.12 that never installs `agentprov` ([Backends](#backends-and-their-environments)).
`agentprov run` plays three parts:

- **T0**, the `agentprov` process you started. It reads the plan, checks the backend's identity against its marker,
  decides consent and caps, starts the worker, and ingests what the worker wrote.
- **T2**, the worker: pinned third-party benchmark code, running as you, with a private `HOME`, the staging directory as
  its working directory, no secrets in its environment except the one endpoint key, and (for a real model) a sandbox or
  a declared containment.
- **The model endpoint**, a local server or an API.

For AgentDojo, AutoDojo and AgentDyn, the worker writes a **`capture/0.1`** log (a hash-chained event stream: the wire
requests and responses of every model call, tool results, environment digests, declared instrumentation) plus the
benchmark's own native log. T0 stores both as raw evidence and maps them with the shared capture mapper
(`agentdojo.capture`) into an AER of mode `live`, then derives SEM, PROV and validation exactly as for an import. The
live-versus-native check compares the two views of every session. The Inspect harness differs: it runs `inspect eval`
first and imports the `.eval` log it writes through the unchanged `inspect.eval` mapper, so its evidence is Inspect's own
record of the run (`by: source`), not captured wire bytes ([Inspect tasks](#inspect-tasks)).

Besides the sessions, a live corpus's manifest records what was configured and observed:

| Recorded | What it holds |
|---|---|
| plan digest, configuration digest | the cells, the agent configuration (model, endpoint, parameters, element, local-model identity) and the backend's identity; a different configuration is refused unless you allow mixing |
| backend identity | environment id, RECORD digests of the installed packages, the pinned fork or dataset |
| declared instrumentation | every way the harness could have affected the run, in the AER header (for example, `http_backoff@1 policy: stock_sdk`); a request-modifying element is flagged |
| `producer.sandbox` | the containment you declared and who vouches for it ([Containment](#containment)) |
| `live.caps` | `--max-calls`, `--max-cost-usd`, the prices, the cell bound used, billed calls and the **spend upper bound** |
| `live.egress` | what the egress proxy allowed and refused ([Containment](#containment)) |
| `live.quality` | the quality report: counts per model of calls, retries, abnormal finishes, served models, drift |
| `live.endpoint_class` | `local` or `api` |

**Why every real run declares its containment.** The worker runs pinned third-party code as you, with network access
and, for an API model, a provider key. A compromised backend is a compromise of your account
([threat model](https://github.com/nickjones39/AgentPROV/blob/main/docs/threat-model.md), section 2). Containment limits
what that code can reach, so a real-model run refuses to start without `--containment`, and the corpus records what you
declared. Scripted runs record no containment (`producer.sandbox` is null), are marked `test_only`, and their corpus is
synthetic and never released. A scripted and a real session never share a corpus.

## Backends and their environments

| Source | Backend project | What it runs | Notes |
|---|---|---|---|
| `agentdojo` | `backends/agentdojo/` (`agentdojo==0.1.35` from PyPI) | AgentDojo's 4 suites, the stock LLM element with a recording transport | the only backend that takes `--defence` |
| `autodojo` | `backends/autodojo/` (the AutoDojo fork at `aa458794`) | AutoDojo's 17 suites and its cached attacks | AgentDyn's three suites also run here |
| `agentdyn` | `backends/agentdyn/` (`SaFo-Lab/AgentDyn` at `5353cf76`) | AgentDyn's 7 suites on AgentDyn's own code | |
| `agentharm` | `backends/inspect/envs/agentharm/` | Inspect's AgentHarm tasks | a different harness; see [Inspect tasks](#inspect-tasks) |

### Registered environments

`agentprov backends build BACKEND` builds an environment under `$AGENTPROV_HOME/envs/` (offline from the uv cache unless
you add `--allow-network`) and writes a marker, `AGENTPROV_ENV.json`, recording its identity. For example, on one
development machine these environments are registered, read from their markers (digests cut to 8 hex digits; this guide
builds nothing and read no environment's code):

| Environment id | Built (UTC) | Holds | Notes |
|---|---|---|---|
| `agentdojo-db3901f1` | 2026-10-28 10:23 | AgentDojo 0.1.35 (PyPI), 4 suites | built with the `defences` group and the **defence assets**: Mandate (3), MELON (3), and the weights of the PI detector |
| `autodojo-aa458794` | 2026-10-28 10:23 | the AutoDojo fork at commit `aa458794`, 17 suites | NLTK `punkt_tab` provisioned from the verified cache (needed only by the refused filter defences) |
| `agentdyn-5353cf76` | 2026-10-28 10:23 | AgentDyn at commit `5353cf76`, 7 suites | built with the sandbox fix below |
| `inspect-agentharm-e3a9a78c` | 2026-10-28 10:23 | `inspect-ai` 0.3.263, `inspect-evals` 0.20.0, the pinned AgentHarm dataset | no benchmark suites; 196 task files hashed |

All four markers record the same sandbox probe result (`passed`, profile digest `34018a40…`): the profile allowed
writing the staging directory and the worker's private home and the egress ports, and denied reading the repository, `.env`
and credential files, writing anywhere else, and connecting to any other loopback port or a remote host.

### What an environment id means

The id is `<backend>-<8 hex digits>`:

- for a backend pinned to a **git commit** (`autodojo`, `agentdyn`), the digits are the first 8 of the fork's commit, so
  `autodojo-aa458794` is the fork at `aa458794`;
- for a backend pinned by **version** (`agentdojo`, and the Inspect harness, which has no fork), they are the first 8
  digits of the sha256 of the backend project's `uv.lock`. A PyPI wheel has no commit; the lock pins every wheel by hash,
  so one lock digest names exactly one resolved environment.

So **the id changes when the lock changes**, deliberately: a re-lock is a change of what runs, and gets a new directory
rather than silently altering the old one. This happened once on the way to this build: adding the `defences` group to
`backends/agentdojo` re-locked it, and `agentdojo-79922295` became `agentdojo-db3901f1`. A git-pinned backend keeps its id
when its lock changes, and `--offline-check` fails instead ("the marker's `lock_sha256` differs from
`backends/<b>/uv.lock`"), which tells you to rebuild.

### Building and checking (described, not run)

`agentprov backends build BACKEND` runs `uv sync --locked --no-config --no-dev --link-mode copy --offline` with
`--exclude-newer` and the project's no-build list, then records the T0 identity, a `hello` from the worker, the
`sandbox-exec` feasibility probe (macOS) and the marker. `--dry-run` prints that plan and writes nothing:

```text
$ agentprov backends build agentdojo --dry-run
backend agentdojo: environment …/envs/agentdojo-db3901f1
  commit8 db3901f1 (from lock_sha256); lock sha256 db3901f1ac714a41…
  would run: uv sync --locked --no-config --no-dev --link-mode copy --offline --exclude-newer 2026-10-07T00:00:00Z --no-build-package …
  UV_PROJECT_ENVIRONMENT=…/envs/agentdojo-db3901f1; every other UV_* variable is dropped except …
  network: none (uv --offline: the build uses the uv cache only)
  then: T0 identity, hello identity, sandbox-exec feasibility probe, marker AGENTPROV_ENV.json
```

`--offline-check` verifies an existing build and writes nothing but scratch files. It recomputes the environment's
identity from its files without importing anything from it (marker status, lock digest, each watched package's RECORD
digest and every installed file, the guarded modules, the NLTK, dataset and defence-asset digests), then asks the worker
for one `hello` with the network blocked and compares it with the build-time answer:

```text
$ agentprov backends build agentdojo --offline-check
agentprov backends build --offline-check: agentdojo-db3901f1 verified (marker, lock, RECORD, guarded files, hello identity)
```

| Option | Use |
|---|---|
| `--allow-network` | let uv download packages (otherwise `--offline`) |
| `--defence-assets ID[,ID…]` | also provision these registry defences' pinned code and weights from the fetch cache into the environment (`agentdojo` only) |
| `--defence-source DIR` | read the defences' pinned code from a local tree instead; every file must match its pinned sha256 and git blob id; no network |
| `--env-file PATH` | an `.env` for builds that need one (the AgentDojo build does not read it) |

A build or a check holds the environment's lock, so it is refused while a run uses that environment, and the other way
round. An environment is never edited by hand: every installed file is hashed.

## Planning a run

### Cells

A cell is one execution to run: a suite, a user task and, for an attacked cell, an attack and an injection task. The
plan expands in this order: per suite, benign cells, then per attack, user task and injection task (a DoS attack takes
one cell per user task). Options:

| Option | Use |
|---|---|
| `--suite S[,S…]`, `--benchmark-version V` | suites (default: the backend's) and benchmark version |
| `--user-tasks SPEC`, `--injection-tasks SPEC` | `all`, ids, or index ranges over the tasks sorted by number, such as `0-2,5` |
| `--attack A[,A…]` | attacks; none means benign cells only |
| `--benign include\|exclude\|only` | whether benign (unattacked) cells are included |
| `--repeats N` | independent repeats per cell |
| `--defence NAME` | one defence for the whole plan ([Defences](#defences)) |
| `--plan PLAN.toml` | a committed plan (format `agentprov-run-plan/0.1`) instead of the cell options |
| `--catalogue` | print the backend's suites, tasks, attacks and defences as one JSON document; no model call, nothing written |

A catalogue lists, per suite, its user and injection tasks and the size of its tool definitions, and per attack whether it
is a DoS attack, whether the backend refuses it, and which options it needs. On this build the registered environments
offer (counted from `agentprov run SOURCE --catalogue`; AgentDojo's lists the benchmark versions `v1` to `v1.2.2` and ten
defences, three of them MELON entries with the provider `port`):

| Backend | Suites | User / injection tasks | Attacks |
|---|---|---|---|
| `agentdojo` | 4 | 97 / 35 | 17 (5 DoS) |
| `autodojo` | 17 | 337 / 143 | 20 (5 DoS); `ours` refused; `autodojo` needs a cache |
| `agentdyn` | 7 | 157 / 63 | 17 (5 DoS) |

### Dry runs and plan documents

`--dry-run` starts the worker for `hello` and `plan` only, with no keys and no network, and prints the plan without
running a cell or writing anything:

```text
$ agentprov run agentdojo --dry-run --corpus $CORPORA/live-demo --campaign demo --suite banking --user-tasks 0-1 \
    --attack important_instructions --injection-tasks 0 --llm-script $SCRIPT
agentprov: finished in 3.3s (exit 0)
plan 85f16c3571896382...: 4 cell(s) x 1 repeat(s); corpus agentdojo-live-demo; backend agentdojo-db3901f1
  config digest sha256:847324326cf51a84...; 0 unit(s) already settled; up to 12 attempt(s) due (--max-attempts 3)
  cell banking/user_task_0/none/none
  cell banking/user_task_1/none/none
  cell banking/user_task_0/important_instructions/injection_task_0
  cell banking/user_task_1/important_instructions/injection_task_0
```

- The corpus id is `<source>-live-<campaign>`; `--corpus DIR` names the directory (outside the repository), written as
  `DIR.partial` while it is a working corpus.
- The **plan digest** hashes the expanded cells, the agent configuration and the backend configuration; the
  **configuration digest** adds the backend's identity. They decide what counts as "the same run" when you resume.
- 4 cells at `--max-attempts 3` means up to 12 attempts are *due*; attempts are counted across invocations.
- `$CORPORA` stands for a directory outside the repository, and `$SCRIPT` for a scripted-transport file (a JSON list of
  replies). A real run never takes `--llm-script`.

`--plan-json` (with `--dry-run`) also prints the plan as one JSON document on stdout, one row per cell, names and counts
only (the human lines go to stderr):

```json
{
 "attempts_due": 12, "backend": "agentdojo", "benchmark_version": "v1.2.2",
 "cells": [
  {"attack": null, "cell_key": "banking/user_task_0/none/none", "injection_task_id": null,
   "kind": "user_task", "settled": 0, "suite": "banking", "user_task_id": "user_task_0"},
  …
 ],
 "config_digest": "sha256:84732432…", "corpus_id": "agentdojo-live-demo", "format": "agentprov-run-dry-plan/0.1",
 "max_attempts": 3, "plan_sha256": "85f16c35…", "repeats": 1, "settled": 0, "units": 4
}
```

A dry run of a **real** model needs everything a real run needs up to the consent step: containment, caps, the key, and
(for a local model) a listing of the server. A dry run against a local endpoint therefore **contacts your local server on
loopback** (to list models), though it makes no model call.

### Estimates and prices

`agentprov estimate SOURCE <the same options as run>` gives the cost and time before you start, at p50 and p90, without a
model call. It takes cell statistics from the corpora you name with `--stats-corpus` (counts only; at most 16), else from
shipped priors, else from a conservative default. Without a key option it plans with a scripted stand-in, and says so.

```text
$ agentprov estimate agentdojo --corpus $CORPORA/e --campaign e --suite banking --user-tasks 0-1 \
    --attack important_instructions --injection-tasks 0 --model openrouter --model-id example-model \
    --max-calls 80 --max-cost-usd 1.00 --price-in 0.15 --price-out 0.60
≈ $0.0029 (p90 $0.0058) for 4 cell run(s), prices as of 2026-10-28 (your override (agentprov prices set)) Time ≈ 54 s (p90 6 m) at --jobs 1.
Plan 85f16c3571896382…: 4 cells × 1 repeat(s) = 4 units; 0 already settled; up to 12 attempts due (--max-attempts 3).
Cost: p50 $0.0029, p90 $0.0058, worst case (every due attempt at p90) $0.0199; model calls p50 13, p90 19.

By suite:
  banking                                        4 units  p50 $0.0027  p90 $0.0055  [priors]

By attack:
  (benign)                                       2 units  p50 $0.0013  p90 $0.0023  [priors]
  important_instructions                         2 units  p50 $0.0014  p90 $0.0033  [priors]

Sources of the cell statistics: priors 4 units
Warning: Planned with a scripted stand-in (no key, no network): … so this estimate is high.
```

(`example-model` is a placeholder; its price was set for the example with `agentprov prices set openrouter example-model
--input 0.15 --output 0.60 --as-of 2026-10-28`.) Without a price the estimate says "no price for this model" and gives
no cost.

**Time for a local model** (D-826). A calibrated preset can hold measured seconds per cell for a local endpoint. When the
preset (the setting `compute.preset`, else `m5ultra`) is calibrated for this host and that endpoint, `agentprov estimate`
takes the run's time from those rows instead, chosen by the model's active parameters (its
[Local Models](08-desktop-app.md#settings) setting, `local_models.<endpoint>.<model id>.active_params_b`), else the last
row. When the last row has a bound, a model above it (or of unknown size) keeps the priors' time. The estimate says so
in a warning and in each group's basis; calls and tokens still come from the priors or your corpora. `m5ultra`
version 2 has one row, for models up to 15 B active parameters: 14.3 s per cell at p50 and 27.4 s at p90, at 4 jobs.

**The shipped priors** are counts from the eight corpora of the regeneration round (126,351 executions; 509 rows by
benchmark, suite, attack and model family, with coarser rows to fall back on), each recorded with the commit that
built it. Per cell they give the model calls, the input and output tokens and the duration recorded in the AER, at p50
and p90. Two things in them changed
with the round's corpora:

- **AgentDyn:** the input tokens of 10 rows (the `dailylife`, `github` and `shopping` suites) are lower: the AER now
  records the input of the CaMeL runs' agent calls as not recorded, so it is no longer counted. The same plan on AgentDyn's `shopping`
  suite:

  ```text
  $ agentprov estimate agentdyn --corpus $CORPORA/dy --campaign dy --suite shopping --user-tasks 0-1 \
      --attack important_instructions --injection-tasks 0 --model openrouter --model-id example-model \
      --max-calls 80 --max-cost-usd 1.00 --price-in 0.15 --price-out 0.60
  ≈ $0.0159 (p90 $0.0539) for 4 cell run(s), prices as of 2026-10-28 (your override (agentprov prices set)) Time ≈ 42 s (p90 3 m) at --jobs 1.
  Plan eaf89d8d0af40a94…: 4 cells × 1 repeat(s) = 4 units; 0 already settled; up to 12 attempts due (--max-attempts 3).
  Cost: p50 $0.0159, p90 $0.0539, worst case (every due attempt at p90) $0.1750; model calls p50 19, p90 53.
  …
  ```

- **AgentHarm:** the agent's calls and the judges' calls are separate columns (D-770), so the judges are priced at
  their own model. For two samples with the D-740 limits:

  ```text
  $ agentprov estimate agentharm --corpus $CORPORA/ah --campaign ah --task inspect_evals/agentharm \
      --samples limit:2 --message-limit 10 --token-limit 20000 --time-limit 600 \
      --judge refusal_judge=example-model --judge semantic_judge=example-model --cell-size 1 \
      --model openrouter --model-id example-model --max-calls 100 --max-cost-usd 1.00 --price-in 0.15 --price-out 0.60
  ≈ $0.0017 (p90 $0.0102) for 2 cell run(s), prices as of 2026-10-28 (your override (agentprov prices set)) Time ≈ 1 m (p90 3 m) at --jobs 1.
  Plan b0c3d4cf7d1cd1c0…: 2 cells × 1 repeat(s) = 2 units; 0 already settled; up to 6 attempts due (--max-attempts 3).
  Inspect inspect_evals/agentharm: 2 sample(s) × 1 epoch(s), 4 at a time; judges (priced at their model, at the agent's endpoint): refusal_judge example-model, semantic_judge example-model; at most 42 billed calls per sample (D-740).
  Cost: p50 $0.0017, p90 $0.0102, worst case (every due attempt at p90) $0.0343; model calls p50 7, p90 15.
  …
  ```

The AgentDojo rows did not change. A prior's duration is the time the recorded run took on the machine that produced
the log, so the time figures are a guide, not a promise for your machine; `--stats-corpus` with your own corpora is
closer.

**Prices** come from a dated table shipped with AgentPROV (394 prices as of 2026-10-21), overridden per model with
`agentprov prices set ENDPOINT MODEL --input … --output …`, and optionally refreshed from OpenRouter's public model list
with `agentprov prices refresh --allow-network` (a network call, never automatic). `agentprov prices list` shows what is
priced; a local endpoint has no per-token cost. `--price-in` and `--price-out` on `run` are different: they price the
**caps**, not the estimate ([Consent, caps and what they refuse](#consent-caps-and-what-they-refuse)).

`estimate --format json` prints one `agentprov-estimate/0.1` document: units, attempts due, calls, cost and time at p50
and p90 and as a worst case, the breakdown by suite and attack, the price used and its date, and warnings. Judge calls of
an Inspect plan are counted and priced separately (D-770).

## Models, endpoints and keys

`--model SHORTHAND` names an endpoint of `endpoints.toml`; `--endpoint NAME --model-id ID` names an endpoint and a model
explicitly. **There are no default model ids.** The two are exclusive with each other and with `--llm-script`.

| Class | Endpoints |
|---|---|
| API | `openrouter`, `anthropic`, `openai`, `deepseek`, `gemini`, `llama`, `qwen`, `glm` |
| local server (`local = true`) | `ollama`, `omlx`, `lmstudio`, `mlx_lm`, `llamacpp`, `vllm` (`--endpoint local` is `ollama`) |

An endpoint's **class** is decided before consent and recorded: `local` only for a `local = true` entry whose resolved
base URL is on loopback (`127.0.0.1`, `::1`, `localhost`); everything else is `api`.

### Local models

A local server must run on this machine, on loopback, and be the kind `endpoints.toml` says it is (a different server
kind on the port is refused, exit 4: several defaults share ports 8000 and 8080). `agentprov models --endpoint lmstudio`
asks a running server what it serves (read-only, no inference, loopback only; **not shown here**, because it contacts a
server), and `--model-id ID` adds the model's **observed identity record**, which a run records and re-checks. Without
`--model-id`, a terminal offers a numbered pick; otherwise the run exits 3 and lists the served ids.

The identity record (`agentprov-local-model/0.2`) holds the server (kind, version when it exposes one, a fingerprint),
the listing entry, the server-side identity, the model's weight files with their sha256 (weights are hashed by default,
with a digest cache in `$AGENTPROV_HOME/cache/model-digests.jsonl`; `--no-hash-weights` records sizes only,
`--model-dir PATH` names a directory the server does not name), and its own digest. Load and serving state (loaded
instances, context length, slots) is recorded as `observed_state` outside the digest. The record becomes part of the
configuration digest, so **another model is another configuration**. Three checks use it:

| Check | What it does | Refusal or stop |
|---|---|---|
| **A12**, served model | every reply's `served_model` must equal the requested model, or the campaign stops after the canary | accept a served id with `--accept-served-model ID` (repeatable, recorded) |
| **A13**, benchmark validity | not a local-model check: it flags benchmark defects (vacuous utility, payload never reached the agent); the replay-based probes are deferred | — |
| **A14**, drift | T0 re-observes the server before **every** cell; the session's `agentdojo/local_model` note says whether it still matches the plan, and a mismatch is a canary condition | re-run once the cause is fixed or the new model accepted as a new configuration |

An LM Studio model served **without native tool use** is refused (exit 4, `cli.refused.local_tool_prompt`): the server
adds its own tool-use system prompt, which the wire capture cannot see. `--allow-text-tool-calls` accepts it, recorded.

**What the app knows about a model.** The preset's concurrency plan needs the weight size, the active parameters and the
KV cache per trace. `--model-dir` reads them from the model's folder (`config.json`, and the `*.safetensors` sizes, or
the `*.gguf` shards when there are none, including oMLX's `split/` folder); the `--model-size-gb`, `--active-params-b`,
`--context-tokens` and `--kv-gb-per-trace` flags give them directly. To keep them per model, store them as settings
(D-828): `agentprov settings set local_models.omlx.<model id>.active_params_b 13`, or in the GUI, Settings › Local
Models. A run uses the flag first, then the setting, then the folder, then the preset, and says which (`source=settings`
in the dry run). `agentprov models --endpoint omlx --model-id ID --find-folders` lists the folders on this machine that
may hold the model (names only; no server contacted).

**A server with an API key.** oMLX can be set up with one, so `omlx` names an optional key variable, `OMLX_API_KEY`
(D-827). Store it with `agentprov keys set OMLX_API_KEY` (or in the GUI, Settings › Keys), or put it in `.env`. It is
read as other keys are (the keychain first, then `.env`) and sent to the loopback server only, never to a LAN address.
Without it, nothing is sent; a server that wants a key then refuses the listing (exit 3, `run.local.unauthorized`).
A key that is set is recorded by its variable name only (never its value) in the configuration digest; without one the
digest is that of a keyless run. A key is never sent to a LAN address: a set key with a LAN base URL is refused (exit 4,
`cli.refused.lan_key`).

**oMLX's model variable.** `omlx` also reads `OMLX_MODEL` (D-827), the served model id to use when `--model-id` is not
given. It is oMLX's own id, as `agentprov models --endpoint omlx` lists it (for example `Qwen3.5-4B-MLX-4bit`), not a
Hugging Face repo id. `--keychain` reads only the key, so `OMLX_MODEL` comes from `.env`, `--env-file` or
`--env-stdin`. (The `ollama` entry reads `LOCAL_MODEL_ID` the same way.)

Other refusals, all before consent: server unreachable (exit 3, `run.local.unreachable`); not an OpenAI-style listing
(exit 3, `run.local.bad_listing`); the model is not served (exit 3, `run.local.model_not_served`, naming the served ids);
the wrong server kind (exit 4, `run.local.wrong_server`); a `remote` model, such as an Ollama cloud model (exit 4,
`run.local.remote_model`). `--base-url URL` overrides the endpoint's base URL (precedence: the flag, then `.env`, then the
setting `endpoints.<name>.base_url`, then the registry), and only for local endpoints.

**The concurrency sweep** (`--tune-jobs`, D-820..D-823) measures how many traces to run at once on a local server:

```
agentprov run agentdojo --m5ultra --tune-jobs 1,2,4,6,8,12 --model omlx --model-id ID \
  --model-display-name "Local model" --containment sandbox-exec --i-consent-to-local-run
```

- **The sample.** Without a plan or cell options it is 24 cells: four suites, user tasks 0–2, benign and attacked.
- **The arms.** After one unmeasured warm-up cell, each value runs the same cells into its own working corpus under
  `--tune-out` (default `$AGENTPROV_HOME/calibration/tune-jobs-<time>/`).
- **The report.** `tune-jobs.json` and `tune-jobs.md` recommend the smallest value within 90 % of the best traces per
  hour, with no timeouts or failed cells.
- **Skipped arms.** An arm the model's memory cannot hold is skipped, and so are the arms after one with timeouts.
- **Resume.** A re-run of the same command reuses finished arms.
- **Plan first.** `--dry-run` shows the arms and a rough time.

**Calibrated presets** (D-822, D-823). A preset (`--m5ultra`, or `--preset NAME`) plans a local run's concurrency from
the host and the model's facts. Only a preset marked `calibrated = true` runs live: it names the committed sweep report
it was built from, says for each compute row whether it is `measured` or `provisional`, and runs with its plan's
`--jobs`, start stagger and request timeout. An uncalibrated preset is refused outside `--dry-run` and `--tune-jobs`
(exit 5). The shipped `m5ultra` preset is calibrated from version 2 (2026-10-28): 4 jobs for every model size. The
≤ 15 B row is measured; the larger rows are provisional, capped at the measured value. The report is
`docs/reports/mac-studio-calibration/README.md`. A preset run records the preset in the working corpus's producer
block.

**The request timeout.** A preset run sends the preset's request timeout with every model call: it goes into
`agent.params.timeout_s`, so it is part of the configuration digest. The stock LLM element ignores that value, so a
preset run (and the sweep) defaults to `--llm-element gateway_compat`, and an explicit `--llm-element native` with a
preset is refused (exit 2). Runs without a preset are unchanged.

**Scope of `gateway_compat`** (D-829). AgentDojo's live part declares its subset "with the native LLM element only";
D-829 also admits `gateway_compat` for runs against a local model server. AutoDojo and AgentDyn are unchanged: `run`
refuses `gateway_compat` for them before anything starts. `gateway_compat` is the AgentDojo-PROV baseline's request
path; it differs from the stock element in its retries (connection and timeout errors are asked again after 10–20 s, up
to 8 attempts) and in its role rewrite, and the corpus records the element used (`live.llm_element`).

**A server on another machine** needs `--allow-lan-endpoint`: a literal private address (10/8, 172.16/12, 192.168/16,
100.64/10, fc00::/7; no host names, no IPv6 zone ids), plain `http`, keyless, recorded as given, with `files` null
(there is no local file to hash; `--model-dir` names a shared copy). Prompts and replies then leave this machine. As
built, a LAN endpoint is class `api` ([Consent](#consent-caps-and-what-they-refuse)).

### API endpoints and keys

A key is read in this order, and **never printed, logged or recorded** (recorded wire requests keep allowlisted headers
only):

1. the **OS keychain** (`agentprov keys set NAME` stores it, prompting without echo, or one line on stdin with
   `--stdin`; `agentprov keys status` and `list` show names only);
2. a **`.env`** file (`--env-file PATH`; it needs the `live` extra, `uv sync --frozen --group docs --extra live`).

`--keychain` reads only the keychain; `--env-file` only the file; `--env-stdin` takes one JSON object of variables on
stdin (for the desktop app); the three are exclusive with each other and with `--llm-script`. A missing key exits 3
(`cli.environment.credential`). The base URL must be `https` (loopback excepted) and on the endpoint's registered host,
unless you pass `--allow-custom-endpoint` (recorded); user names, queries and fragments in a URL are always refused
(exit 4, `cli.refused.endpoint`).

`agentprov models --endpoint openrouter` shows the provider's model list from a dated cache without any network access;
`--allow-network` fetches it (list calls only, no tokens, no cost); a model that is absent from a cached list is a
warning, never a refusal. Other model options: `--max-tokens N|harness-default` (required on Anthropic endpoints, where
AgentDojo's own 1,024 is never used silently; refused on OpenAI-style endpoints), `--reasoning-effort LEVEL` (not on
Anthropic), `--temperature-policy as-benchmark` (see below) and `--model-display-name NAME`.

**The display name.** Attacks such as `important_instructions` address the model by name. A model id with no stock name
needs `--model-display-name`. Without one, the run prints a hint before consent, and the first attacked cell's setup
refuses; the run then stops after that cell (a *config stop*) instead of failing every cell. The scripted run in
[After a run](#after-a-run) hit exactly this:

```text
$ agentprov run agentdojo --corpus $CORPORA/live-demo --campaign demo --suite banking --user-tasks 0-1 \
    --attack important_instructions --injection-tasks 0 --llm-script $SCRIPT
agentprov run agentdojo: units=4 plan=4 unit(s) workers=1
run: finished in 12.6s (exit 1)
  units    3 of 4: sealed 2, failed 1
  issues   map.capture_error x1, map.no_execution_observed x1
agentprov run: a cell's setup refused this configuration, so no further cell was started (every one would fail the same way); fix the option the refusal names and re-run the same command
…
notice: setup refusal: banking/user_task_0/important_instructions/injection_task_0: attack 'important_instructions' names the model, and the pipeline name has no stock MODEL_NAMES entry: attack_params.model_display_name (--model-display-name) is required
```

Re-running the same command with `--model-display-name "Scripted Model"` resumed the run (exit 0, "2 of 4 unit(s) done
before"). For a local server, stock AgentDojo's own display name is "Local model".

## Consent, caps and what they refuse

Exit codes (specification N.1.3): **0** ok, **1** failures, **2** usage, **3** environment, **4** refused by a guard,
**5** unsupported, **70** internal, **130** interrupted. What a real run needs depends on its transport:

| | Scripted (`--llm-script`) | Local server | API endpoint |
|---|---|---|---|
| Key | none (`--keychain`, `--env-stdin` refused, exit 2) | none | required (exit 3 if missing) |
| `--containment` | not used | required | required |
| Consent | none | `--i-consent-to-local-run` or `--i-consent-to-api-costs`, or the prompt | `--i-consent-to-api-costs` or the prompt |
| Caps | optional | optional | `--max-calls`, `--max-cost-usd`, `--price-in`, `--price-out` all required |
| Live status | admitted even if `planned` | `partial` or better | `partial` or better |

| Option | What it does | What it refuses, and the exit code |
|---|---|---|
| `--i-consent-to-api-costs` | consent to billed calls (it also satisfies a local run) | |
| `--i-consent-to-local-run` | consent for a local server only; no provider bills these calls | on an API endpoint: `cli.refused.consent`, **4** |
| no consent flag | on a terminal only, a prompt `Continue? [y/N]` | otherwise `cli.refused.consent`, **4** ("a real-model run needs consent …") |
| `--max-calls N` | at most N billed calls for the whole corpus, probes and resumed attempts included; a cell starts only if its worst case fits | an API run without it: `cli.refused.api_caps`, **4** |
| `--max-cost-usd USD` | at most this spend, as an **upper bound** priced from `--price-in` and `--price-out` (USD per million tokens) | without both prices: usage, **2**; prices without it: usage, **2**; an API run without it: `cli.refused.api_caps`, **4** |
| `--containment` | `sandbox-exec`, `dedicated-user` or `vm` ([Containment](#containment)) | missing, or `sandbox-exec` without a passed probe: `cli.refused.containment`, **4** |
| `--preflight-only` | run only the endpoint probe and exit; needs consent, takes no caps | with caps: usage, **2** |
| `--allow-lan-endpoint`, `--allow-custom-endpoint`, `--base-url` | see [Models](#models-endpoints-and-keys) | `cli.refused.endpoint`, **4**; on a non-local endpoint, usage, **2** |
| `--allow-text-tool-calls`, `--accept-served-model` | lift the tool-call and served-model refusals, recorded | |
| `--temperature-policy as-benchmark` | accepts stock AgentDojo's behaviour for a configured parameter it does not transmit (recorded); without it that is a usage refusal (**2**). `inject` is **5**: not available | |
| `--max-attempts N` (3), `--retry-inconsistent`, `--allow-mixed-config` | resume rules ([Quality checks](#quality-checks-retries-and-run-states)) | a different configuration digest: `cli.refused.mixed_config`, **4** |
| `--canary N` (10), `--cell-timeout S` (1800), `--jobs N`, `--start-stagger S`, `--keep-staging` | campaign control; `--jobs` above the host's maximum is refused, never clamped | usage, **2** |

**The order of the checks** matters, because it tells you what a refusal has *not* yet touched:

1. **Usage** (exit 2): incompatible options, missing cell or model options, caps option combinations.
2. **Live status gate** (exit 5), then **backend and defence refusals** (exit 5) and the environment (exit 3, "run
   `agentprov backends build X`").
3. **API caps** (exit 4), *before any key is read*; then the **key** (exit 3), the endpoint and its URL (exit 4) and the
   **containment** (exit 4).
4. For a local server, T0 **lists and fingerprints it** (exit 3 or 4, above) and observes the model's identity.
5. Identity checks of the environment, the attack cache and the dataset (exit 3), the egress proxy and sandbox wrap.
6. The **plan**; `--dry-run` stops here.
7. **Consent** (exit 4), then the **preflight probe**, then the campaign.

**What the caps count.** Every billed call is charged to the caps: each cell's calls, each probe call, a billed reply
with no usage (charged at the bound), a parent-ended attempt (one extra call at the bound) and a missing log (a whole
cell). T0 starts a cell only if the spend so far, the worst case of every cell in flight and the worst case of the new
cell all fit both caps. The worst case of an AgentDojo-family cell is **48 billed calls** (`3 × (1 + 15)`: up to three
passes of one call plus a tool loop of at most 15), each at the per-call bound of 32,000 input tokens (or the largest
seen) and the transmitted `max_tokens` (or 4,096, or the largest seen). All input-side tokens (input, cache read and
cache write) are priced at `--price-in`. At `--price-in 0.15 --price-out 0.60` that is about `$0.0073` per call and
about `$0.348` per cell. A cell that bills more than its bound stops the campaign (`cap_bound_exceeded`); a cap that
cannot fit the next cell stops it with `cap_reached`, and re-running with a higher cap resumes. The recorded **spend
upper bound** is a ceiling, not a bill: the pilot's OpenRouter run had a bound of $0.011 against recorded usage of about
$0.0035. The provider's own key limit remains the hard backstop; set one.

**The preflight probe.** Before the first cell of a real run, T0 sends the endpoint a small request through the same
recording transport, to check that it answers, that the stock message roles reach the model (A9), that tool calls come
back structured (A4) and that configured parameters are transmitted (A3). It makes **up to three calls**, only while the
verdict is still "unconfirmed", stopping at the first reply that clearly follows the instruction; **each call is charged to
the caps**, and the consent text names the bound ("up to 3 preflight probe call(s), then up to N cell attempt(s)"). A
refusal of the roles, or no evidence after three calls, exits 4 (`cli.refused.preflight`); an unreachable endpoint
exits 3 (`cli.environment.preflight`). `--preflight-only` runs just the probe. For an Inspect backend the probe runs
through Inspect's own model ([Inspect tasks](#inspect-tasks)).

Refusals up to the caps, as they look (none reached a key, a server or the network):

```text
$ agentprov run agentdojo … --model openrouter --model-id example-model --containment vm
agentprov: error [cli.refused.api_caps]: an API endpoint run needs its caps (the endpoint entry is not local): give --max-calls, --max-cost-usd (D-725; the provider's own key limit is the backstop)
[exit 4]
$ agentprov run agentdojo … --model openrouter --model-id example-model --containment vm --max-calls 80 --max-cost-usd 1.00
agentprov run: --max-cost-usd needs --price-in and --price-out (USD per million tokens)
[exit 2]
$ agentprov run agentdojo --preflight-only --model openrouter --model-id example-model --max-calls 5
agentprov run: --preflight-only is one model call; the caps belong to a campaign
[exit 2]
$ agentprov run agentdojo … --llm-script $SCRIPT --keychain
agentprov run: --keychain reads the key of a real endpoint; a scripted run needs none
[exit 2]
```

The consent, key, endpoint and containment refusals come after these and need a key or a server to reach, so they are
**not shown here**; their texts are in the table above and in [Troubleshooting](10-troubleshooting.md#live-runs).

## Containment

| `--containment` | Platforms | Recorded as | What it means |
|---|---|---|---|
| `sandbox-exec` | **macOS only** | `sandbox_exec`, `declared_by: probe`, with the profile digest | **Enforced.** Accepted only when `agentprov backends build` recorded a passed probe of this exact profile |
| `dedicated-user` | any | `dedicated_user`, `declared_by: operator` | **Declared, not enforced:** your statement that the run executes as a dedicated operating-system user. Recorded, not checked |
| `vm` | any | `vm`, `declared_by: operator` | **Declared, not enforced:** your statement that the run executes inside a virtual machine. Recorded, not checked |

On Linux and Windows `sandbox-exec` is refused (exit 4), because its probe is "not applicable" there; use a declaration. The
desktop app offers only the choices that apply on its machine.

**What `sandbox-exec` enforces.** The worker may import the backend, write its staging directory and its private home,
and connect to two loopback ports only. It may not read the repository, `~/.ssh`, `~/.aws`, `~/.config/gh`, any `.env` or
`.env.*`, the keychain directory and the other credential directories, nor write anywhere else. The build's probe has 11
checks (6 denials, 5 allowances); `--offline-check` reports the recorded result and does not re-run it.

**The egress proxy (D-664).** Because the sandbox forbids all other outbound connections, T0 starts a small proxy for a
run to a non-loopback endpoint. It tunnels TLS, undecrypted, with `CONNECT` to the **exact `host:port` pair** of the
agent's endpoint (plus a defence endpoint, if any) and refuses everything else (403 for another target, 405 for another
method). A loopback endpoint is reached directly. Judges of an Inspect plan share the agent's endpoint, so the allowlist
is still one pair. For a LAN endpoint the proxy has a plain-`http` forward mode to that one literal address: it rewrites
the request, allows only `GET`, `POST`, `HEAD` and `OPTIONS`, and handles one request per connection. What the proxy
allowed and refused is recorded as `live.egress` (allowed pairs, tunnels, forwards, refusals by kind). The pilot's API
runs allowed exactly `openrouter.ai:443` or `api.anthropic.com:443`, with an empty refusal list.

**What containment does not cover.** It confines T0's worker, not your model server (a local server runs outside it), and
it does not make a malicious backend safe: the worker is still pinned third-party code run as you.

## Quality checks, retries and run states

**During the run.** A **canary** looks at the first `--canary N` cells (10 by default; `0` disables). If a condition
appears and cells remain, the campaign stops; if every cell had already run, the condition is only a notice. Conditions:

| Check | Condition |
|---|---|
| A3 | a configured parameter (temperature, reasoning effort, top_p, seed, max_tokens) was not transmitted |
| A4 | a text-encoded tool call is suspected |
| **A6** | **abnormal finish reasons** in more than 20 % of kept calls. It is **provider-aware**: `stop` and `tool_calls` are normal for OpenAI-style endpoints; `end_turn`, `tool_use` and `stop_sequence` (and `stop`) for Anthropic |
| A11 | an attempt errored, aborted or was left unsealed |
| A12 | a reply's served model is absent or differs from the request (not accepted) |
| A14 | the local model changed since the plan |

(A9 is judged once, by the preflight probe; A13 is the benchmark-validity flag described above.) A stop exits 1 with "the
canary found a misconfiguration; the campaign stopped after the canary cells (re-run the same command to resume once the
cause is fixed or accepted)".

**Retries.** Stock AgentDojo nests the SDK's two retries inside tenacity's three attempts, so one element call can make
up to **nine wire attempts**; each is its own recorded request linked to the first, and the harness changes nothing
(`http_backoff@1 policy: stock_sdk` is declared). A real HTTP 400 is not retried. Failed attempts that never reached the
wire are not billed. `gateway_compat` (a port of the older generator's element) retries differently, is opt-in, and is
refused on AutoDojo and AgentDyn. Separately, a cell that ends inconclusive is **re-attempted** up to `--max-attempts`
(3) times across invocations.

**Session and run states.** There is no `stopped` status. A session ends `complete`, `incomplete` (the cell completed but
the native log is missing or damaged), `errored` (an exception, or a failed redaction scan) or `aborted`; when the
parent ends a session (a timeout or a dead worker), it appends the `aborted` end itself and notes why. A session whose
staged files hold a secret is **quarantined**: nothing is stored, the staging directory is kept, and the register code is
`capture.quarantined`. A run stops in one of these ways:

| Stop | Why | Exit | Resume |
|---|---|---|---|
| canary stop | a canary condition ([above](#quality-checks-retries-and-run-states)) | 1 | re-run the same command after the cause is fixed or accepted |
| cap stop | `cap_reached` or `cap_bound_exceeded` | 1 | raise the cap and re-run |
| config stop | a cell's setup refused the configuration (for example the display name) | 1 | fix the option the refusal names and re-run |
| drain | `--control-file` asked it to finish what is in flight | 0 | re-run |
| interrupt | Ctrl-C, SIGTERM or SIGHUP: in-flight sessions are sealed `aborted` and the ledger is written | 130 | re-run; a **second** signal exits at once and leaves sessions in staging, unledgered |

There is no `--resume` flag: **re-running the same command resumes.** A unit is *conclusive* when its session is
`complete` and its accounting `consistent` or `unverifiable`; a ledger entry counts only if its capture log is still in
the raw store. The corpus manifest has `partial: true` when you used `--limit` or the run stopped by canary, cap or
configuration. The exit code is 1 when any cell was inconclusive, inconsistent, failed or quarantined, or the run
stopped early; otherwise 0. A run prints a per-model quality line, then:

```text
agentprov run: 2 attempt(s); 2 conclusive, 0 inconsistent, 0 inconclusive; 2 derived, 0 failed; 2 of 4 unit(s) done before
```

## Defences

`--defence NAME` runs one defence for the whole plan (`--defence none`, the default, is undefended). The defences are
data in a registry (`backends/shared/src/agentprov_backend/defences.toml`), and only the **`agentdojo` backend** builds
them; the live profile `agentdojo-live@3` allows them.

| `--defence` | What it is | Needs |
|---|---|---|
| `repeat_user_prompt` | AgentDojo built-in: repeats the user prompt after every tool batch | nothing |
| `spotlighting_with_delimiting` | AgentDojo built-in: delimiters around tool outputs plus a system-prompt warning | nothing |
| `tool_filter` | AgentDojo built-in: an LLM pre-filter of the tool list, one extra call per pass | the agent's own model; an OpenAI-style element |
| `transformers_pi_detector` | AgentDojo built-in: a prompt-injection classifier that redacts flagged tool outputs (the **PI detector**) | `--defence-assets transformers_pi_detector` (the `defences` group and about 737 MB of weights, loaded offline) |
| `mandate_envelope`, `mandate_scoped`, `mandate_intent` | Mandate: a counterparty and cap gate on money tools; plus purpose-scoped authority; plus an intent-coherence check | `--defence-assets`; **banking suite only** |
| `melon`, `melon_sm`, `melon_at` | MELON (a port): masked re-execution with a tool-call embedding comparison; with a semantic mask; with an adaptive threshold | `--defence-assets melon`, and `--defence-endpoint NAME` for its embeddings (an extra model endpoint, whose key alone enters the worker) |

The Mandate entries are recorded with their licence as "MIT, publisher unverified". `progent`, `drift`, `camel` and
`camel_nopolicy` replace pipeline components and are refused on every backend. A defence is checked by T0 before any
worker starts, and every refusal exits 5 ("Nothing was started and nothing was written"):

```text
$ agentprov run autodojo --dry-run … --defence melon
agentprov: cannot run 'autodojo': defence melon for the autodojo backend.
  The registry builds it on: agentdojo.
$ agentprov run agentdojo --dry-run … --defence progent
agentprov: cannot run 'agentdojo': defence progent replaces pipeline components.
  DRIFT, Progent and CaMeL need defence-specific capture (D.11.6).
$ agentprov run agentdojo --dry-run … --suite workspace --defence mandate_scoped
agentprov: cannot run 'agentdojo': defence mandate_scoped on workspace.
  It runs on banking only.
$ agentprov run agentdojo --dry-run … --defence not_a_defence
agentprov: cannot run 'agentdojo': defence not_a_defence.
  It is not in the defence registry (…). The agentdojo backend builds: mandate_envelope, mandate_intent, mandate_scoped, melon, melon_at, melon_sm, repeat_user_prompt, spotlighting_with_delimiting, tool_filter, transformers_pi_detector (D-670, D-671).
```

A defence that needs assets fails with "its pinned file … is not provisioned (`agentprov backends build … --defence-assets
ID`)", and an environment whose defence registry differs from the repository's is refused (exit 3): rebuild it.

**How a defended session is recorded.** The defence is the experimental treatment, so it is *not* declared as
instrumentation. The AER records `task.defense_id` (observed), an actor of kind `defense`, notes with the code, weights
and parameter digests, the defence's own model calls as `auxiliary` requests under that actor, and its interventions as
decisions and denied tool results. The harness's own effects are declared, as `defence_pipeline_rewrite`,
`defence_recorder`, `defence_aux_span`, `defence_code_provisioned`, `defence_weights_offline` and, for MELON,
`defence_port@1`. A session with the port item must never be presented as the authors' released implementation.

**A worked plan.** The plan file selects the defence, like the flag does; both give the same plan digest:

```toml
# banking-spotlighting.toml
[plan]
format = "agentprov-run-plan/0.1"
backend = "agentdojo"
suites = ["banking"]
user_tasks = "0-1"
injection_tasks = "0"
attacks = ["important_instructions"]
benign = "include"
defence = "spotlighting_with_delimiting"
```

```text
$ agentprov run agentdojo --dry-run --plan banking-spotlighting.toml --corpus $CORPORA/g --campaign g --llm-script $SCRIPT
agentprov: finished in 3.6s (exit 0)
plan d2c0b6ecb87c0a42...: 4 cell(s) x 1 repeat(s); corpus agentdojo-live-g; backend agentdojo-db3901f1
  config digest sha256:847324326cf51a84...; 0 unit(s) already settled; up to 12 attempt(s) due (--max-attempts 3)
  cell banking/user_task_0/none/none
  …
```

The same cells without the defence have the plan digest `85f16c35…`; the defence changes the plan, so the two are
different runs. A defence in a plan file that the profile refuses (`defence = "progent"`) exits 5 as well. **Not shown
here:** a real-model run with a defence. The pilot's real-model runs all used `--defence none`.

## AutoDojo and AgentDyn

### AutoDojo

`agentprov run autodojo` runs the fork's 17 suites (the four stock ones, `banking_v2_0` to `_4`, `travel_v2_0` to `_4`,
and shopping, github and dailylife) and 20 attacks, 5 of them DoS attacks. The **`autodojo` attack** replays an attack
cache that the optimiser produced. It needs two options, and the pair applies to the whole plan, so it cannot be mixed with
other attacks:

| Option | Use |
|---|---|
| `--autodojo-cache PATH` | a copy of a cache file from the fork (strict JSON: `injection_tasks` → vector → variants) |
| `--autodojo-variant K` | the variant index (an integer ≥ 0); vectors that cannot serve it fall back to the injection task's goal, and the run says how many |
| `--allow-network` | lets T0 fetch the pinned fork commit into the fetch cache to verify the file (never on a dry run) |

Before anything is staged or spawned, T0 hashes the file, finds its git blob id in the tree of the pinned fork commit
(`aa458794`, from the fetch cache, with `git ls-tree` and `git cat-file` only: no checkout), re-reads that blob and compares
sha256. It stores the file with a git origin and prints "attack cache verified: blob … is … of …@aa458794". A file that
matches no blob in the pinned tree exits 3 (`cli.environment.autodojo_cache_blob`); a commit that is not cached exits 3
(`cli.environment.autodojo_cache_commit`); a malformed file or a bad variant exits 2.

**A worked plan** (a dry run; the benign cells and one attacked cell, with no cache needed for `important_instructions`):

```text
$ agentprov run autodojo --dry-run --corpus $CORPORA/au --campaign au --suite banking --user-tasks 1 \
    --attack important_instructions --injection-tasks 0 --llm-script $SCRIPT
plan dd3a178219f9b70f...: 2 cell(s) x 1 repeat(s); corpus autodojo-live-au; backend autodojo-aa458794
  config digest sha256:7837fce0b8143dbf...; 0 unit(s) already settled; up to 6 attempt(s) due (--max-attempts 3)
  cell banking/user_task_1/none/none
  cell banking/user_task_1/important_instructions/injection_task_0
```

```text
$ agentprov run autodojo --dry-run … --attack autodojo
agentprov run: --attack autodojo needs --autodojo-cache and --autodojo-variant
[exit 2]
```

Refused on AutoDojo (exit 5): `--llm-element gateway_compat` (the port binds to private helpers whose versions differ in
the fork), the `ours` and `variant_generation` attacks, and every defence. ROPE-hosted AutoDojo runs cannot be
reproduced (the harness revision was never released), so a live AutoDojo run is a new execution.

### AgentDyn

`agentprov run agentdyn` runs AgentDyn's **own pinned code** (`SaFo-Lab/AgentDyn` at `5353cf76`) in its own environment,
with 7 suites (the four stock ones plus shopping, github and dailylife), 157 user and 63 injection tasks and 17 attacks. It
has no attack cache. AgentDyn and AutoDojo both report themselves as `agentdojo 0.1.35`, so sessions record the backend id
`agentdyn` and the pinned repository and commit.

```text
$ agentprov run agentdyn --dry-run --corpus $CORPORA/dy --campaign dy --suite shopping --user-tasks 0 \
    --attack important_instructions --injection-tasks 0 --llm-script $SCRIPT
plan cbb87a9a29cbcb26...: 2 cell(s) x 1 repeat(s); corpus agentdyn-live-dy; backend agentdyn-5353cf76
  config digest sha256:85ae78b777a37d30...; 0 unit(s) already settled; up to 6 attempt(s) due (--max-attempts 3)
  cell shopping/user_task_0/none/none
  cell shopping/user_task_0/important_instructions/injection_task_0
```

- **Every defence and `gateway_compat` are refused** (exit 5); the declared instrumentation is AgentDyn's own set
  (`agentdyn.temperature_transmitted@1`, `malformed_tool_calls_dropped@1`, and others).
- **AgentDyn's tools read the clock and the random generator**, so **a re-run is not a reproduction**
  (`agentdyn.art.nondeterministic_tools`): two runs of the same cell end in different environment states, and the captured
  values are the only evidence. This also holds for AgentDyn's suites run through AutoDojo.
- AgentDyn's default system prompt differs from AgentDojo's, which AutoDojo sends for the same suites; compare AgentDyn
  results across the two backends with that in mind.
- The code is MIT; AgentDyn's own suites and logs carry no licence statement, so releasing a live AgentDyn corpus is a
  decision for the project owner (it is "MIT as declared; not legally settled").
- If a hello fails under the sandbox with a `PermissionError` on a `.env.example` file, rebuild the environment: the
  identity check used to stat every file RECORD lists, which the sandbox profile forbids for `.env*` names; it now reads
  RECORD's own text, with the same digest.

## Inspect tasks

The Inspect harness runs one benchmark task through `inspect eval` in `inspect-agentharm-e3a9a78c` (`inspect-ai`
0.3.263, `inspect-evals` 0.20.0, the AgentHarm dataset pinned at revision `e23b3fe6` and checked by sha256, never
downloaded at run time). `agentprov run agentharm` selects it. A plan expands into **cells** of at most `--cell-size`
samples; each cell is one `inspect_ai.eval()` call, whose `.eval` log is mapped by the unchanged `inspect.eval` reader and
mapper (AER mode `import`, evidence **by source**: Inspect's own record). The wire log is stored beside it, not mapped.
Judge calls appear as `model_call` records under actors `judge0` and `judge1`. A sample that errors in the harness is kept
and imported, and **makes its cell `incomplete`** (the run exits 1; D-743).

**Tasks.** The catalogue offers two, both from `inspect_evals`: `inspect_evals/agentharm` and
`inspect_evals/agentharm_benign`. Each has two splits, `test_public` (176 samples) and `val` (32). Their parameters are
`split`, `agent` (`default` or `refusal`), `detailed_behaviors`, `hint_included`, `n_irrelevant_tools` (0 to 64),
`tool_choice` and `prompt_technique`; `max_messages`, `max_tokens`, `temperature` and `seed` are fixed by the task and only
reported. **WhistleBench and ATIA have no live backend on this build**: they are import-only parts, `supported` and
sealed in wave 2 (`whistlebench` and `atia-benchmark`, both 0.1.0; [chapter 14](14-corpora.md)). The task data is
harmful by design: this guide names the
tasks and counts samples, and quotes none of their text.

| Option | Meaning |
|---|---|
| `--task NAME` | a catalogue task (required with `--samples`) |
| `--task-param KEY=VALUE` | a declared parameter, repeatable; a TOML scalar or a string, no floats |
| `--samples limit:N` or `ID,ID…` | the first N of the split in dataset order, or explicit ids (**mandatory**) |
| `--epochs N` | epochs per sample (1 to 10; default 1) |
| `--message-limit N`, `--token-limit N`, `--time-limit SECONDS` | per-sample caps, **all three mandatory** (D-667): 1 to 500 messages, up to 10,000,000 tokens, up to 86,400 s |
| `--max-connections N` | concurrent model calls inside one cell (default 4, 1 to 64) |
| `--cell-size N` | samples per cell (default **25**, or **1** when `--max-calls` or `--max-cost-usd` is given; 1 to 500) |
| `--judge ROLE=MODEL` | the model of a scorer role, repeatable; **every role is required**: `refusal_judge` and `semantic_judge` |

Judges use the agent's endpoint and key. **Under caps, every judge must use the agent's model** (otherwise
`cli.refused.api_caps`, exit 4), and the endpoint must speak the OpenAI chat format (an Anthropic-format endpoint is
refused before consent). Inspect's own retries are fixed at one per model call.

**The cell bound.** Under caps a cell must have a worst case that fits, so the harness bounds the billed calls of a cell
(D-740). With `n` samples per cell, `E` epochs, message limit `M`, `a` judge calls per agent call, `j` judge calls per
sample and `K` retries per call:

```text
billed calls per cell  ≤  n × E × ((M − 1) × (1 + a) + j) × (1 + K)
```

For AgentHarm `a = 1` (the refusal judge reads each assistant message), `j = 3` (at most three semantic-judge calls per
grading function, none in a loop) and `K = 1`; the bound is valid for the task files recorded in the environment's
identity. Agent calls are at most `M − 1`, since Inspect refuses a generation at the message limit. The worked figures of
the D-740 note, for `E = 1`, a per-call bound of $0.00726 (32,000 input and 4,096 output tokens at $0.15 and $0.60 per
million) and `K = 1`:

| `M` | `n = 1`: calls, USD | `n = 4`: calls, USD |
|---|---|---|
| 20 | 82, $0.595 | 328, $2.380 |
| **10** | **42, $0.305** | 168, $1.219 |

The approved defaults (`--cell-size 1`, `--message-limit 10`, `K = 1`) reserve **42 calls, about $0.305, per cell**. The
bound enters the caps instead of AgentDojo's 48-call constant, and `agentprov estimate` prints it ("at most 42 billed
calls per sample (D-740)"):

```text
$ agentprov run agentharm --dry-run --corpus $CORPORA/ah --campaign ah --task inspect_evals/agentharm \
    --samples limit:2 --message-limit 10 --token-limit 20000 --time-limit 600 \
    --judge refusal_judge=example-model --judge semantic_judge=example-model --cell-size 1 --llm-script $SCRIPT
agentprov: finished in 2.3s (exit 0)
plan b0c3d4cf7d1cd1c0...: 2 cell(s) x 1 repeat(s); corpus agentharm-live-ah; backend inspect-agentharm-e3a9a78c
  config digest sha256:17c659c5549b7b64...; 0 unit(s) already settled; up to 6 attempt(s) due (--max-attempts 3)
  cell e53071bf326f947e
  cell 70cf3e8fc8b963ae

$ agentprov run agentharm --dry-run … # the same plan, without a message limit
agentprov run: the backend refused the plan: [inspect].limits: missing key(s) message_limit
[exit 2]
```

Without caps, the same two samples are one cell of two (`--cell-size` 25). **Judge pricing (D-770):** judge calls are
counted and priced apart from the agent's, at the agent's endpoint; roles on different models are priced at the dearest,
with a warning, and a judge model with no price makes the cost unknown.

**Preflight.** Inspect's cells transmit none of the agent's sampling parameters, and the probe runs through Inspect's own
model in its own capture session (D-742); the rules above (up to three calls, charged to the caps) apply.

**Restricted and private.** AgentHarm's data is MIT with an additional clause (use only to improve AI safety and
security), and a live AgentHarm AER holds harmful prompts and any compliant completions verbatim. The live corpus is its
own **restricted-use corpus, private**: it stays under `$AGENTPROV_HOME`, is never deposited, and needs a separate
decision of the project owner before any release. Corpus ids are `agentharm-live-<campaign>`.

## The shape of a real run

The live pilot's report (`docs/reports/live-pilot/README.md`; the probe's is
`docs/reports/inspect-harness/probe-d667.md`) records what real runs looked like on 2026-10-22 and 2026-10-23. Only counts
and statuses are quoted here. All corpora are working corpora: not sealed, not released.

| Run | Endpoint class | Cells | Calls | Cost bound against recorded use | `validate --strict` | `recompute --dry-run` | `verify` chain |
|---|---|---|---|---|---|---|---|
| AgentDojo | local | 8 | 25 kept | $0 | 8 of 8 | 8 identical | 8 of 8 |
| AutoDojo (`autodojo` attack, variant 0) | local | 2 | 4 kept | $0 | 2 of 2 | 2 identical | 2 of 2 |
| AgentDyn | local | 2 | 15 kept | $0 | 2 of 2 | 2 identical | 2 of 2 |
| AgentDojo | API (OpenRouter) | 4 | 15 billed of a cap of 80 | bound **$0.011**, recorded use ≈ **$0.0035** | 4 of 4 | 4 identical | 4 of 4 |
| AgentDojo | API (Anthropic) | 4 | 10 billed of 80 | bound **$0.009**, recorded use ≈ **$0.0035** | 4 of 4 | 4 identical | 4 of 4 |
| AgentHarm probe (D-744) | API (OpenRouter) | 4 (1 sample each) | 25 billed (24 in cells, 1 preflight) of 168 | bound **$0.182** under a cap of $0.50; recorded use ≈ **$0.003** | 4 of 4 | 4 identical | chain passed |

In every run the live-versus-native check agreed, no key-shaped string appeared in any output or corpus, and the egress
proxy's refusal list was empty. The pilot also stopped runs, and the reasons are the refusals in this chapter: a
configured temperature that the stock element does not transmit (A3, exit 2); a single probe reply that did not evidence
the instruction (A9, exit 4, which is why the probe may now make up to three calls); an attack that names the model with
no display name (12 attempts, 8 failed, the case that became the fail-fast); and a worker that failed its start under the
sandbox (the `.env.example` stat, no model call). The verdicts of an eight-cell run say nothing about attack success.

## After a run

A run leaves a **working corpus** (`DIR.partial`). Everything in chapters 4 and 6 applies, with these differences. These
commands ran on the scripted corpus above (5 executions: four conclusive, one failed in the config stop):

```text
$ agentprov validate --corpus $CORPORA/live-demo --strict
validated 5 execution(s) of agentdojo-live-demo (working) in release mode, tiers aer,sem,prov,linkage: 5 passed, 0 failed; linkage resolved 5/5 (100.00%); stored results reproduced 0, differ 0
$ agentprov recompute --corpus $CORPORA/live-demo --dry-run
agentprov recompute: units=5 plan=sem,prov,validation workers=0
agentprov recompute: would derive 5 execution(s); recomputed stages: sem,prov,validation; 5 identical, 0 changed (explained), 0 unexplained, 0 failed, 0 unverified; 0 index row(s) refreshed
$ agentprov verify --corpus $CORPORA/live-demo
agentprov verify: level chain: passed with unverified checks; 0 failed, 1 unverified or tombstoned
  unverified: checksums.absent at checksums.sha256: a working tree has no checksums.sha256 (it is written at sealing)
$ agentprov stats --corpus $CORPORA/live-demo --tables counts
…
source_id  profile           registry_parts  …  records  n_executions  …  status_ok  status_ok_with_issues  status_failed …
agentdojo  agentdojo-live@3  live            …  5        4             …  4          0                      1 …
```

- **`recompute` re-derives from the stored AER** (the stages `sem`, `prov`, `validation` above); a live corpus cannot be
  re-mapped from its raw evidence, and that is refused with exit 5 (D-43). `0 differences` means what it means for an
  import.
- **A failed attempt stays.** The attempt that hit the display-name refusal is in the corpus as a failed execution with
  `map.capture_error`, next to the attempts that succeeded: failing executions are kept, never discarded.
- `validate --release` cannot pass (its SHACL tier does not exist), so use `--strict`, as in [chapter 4](04-derive-recompute-validate-verify.md#validate).
- `verify` always passes "with unverified checks" on a working tree: nothing is sealed.
- `--skip-prov-conformance` skips tier 4 for each session; the corpus is then marked unvalidated until a full
  `recompute --out`.

**Live corpora are not sealed in this build (U-18).** `package` refuses them, whatever else is right:

```text
$ agentprov package --corpus $CORPORA/live-demo --corpus-version 0.1.0 --spec …/corpus-spec.toml --licence-file LICENSE=…
agentprov: error [package.unsupported.live]: sealing a live corpus is not supported in this build
[exit 5]
```

(Without `--spec`, `package` exits 2 first, asking for one.) Sealing live corpora is planned for v0.2
([roadmap](https://github.com/nickjones39/AgentPROV/blob/main/docs/roadmap.md#planned-for-v02)): it needs a new corpus
format, `agentprov-corpus/0.3`, with a closed live block, because the sealed `agentprov-corpus/0.2` schema cannot carry
the facts a working live corpus records. A live corpus records what *one* run did with one model and a nondeterministic
provider; no live result is claimed in v0.1, and the project does not claim "Live Capture" for any corpus until an
approved, sealed, non-test live corpus exists. Until then, a live corpus is a working corpus: keep it under
`$AGENTPROV_HOME`, never in the repository, never in a deposit, and treat a scripted corpus as synthetic. This is also
why the pilot's corpora carry the words "not sealed".

## Checking the machinery without a model: local CI jobs (D-723)

The evidence that the live parts work without a model is the local CI (`uv run python tools/ci_local.py`, D-462):

| Job | What it does | Network |
|---|---|---|
| `backend-agentdojo` | a locked sync on Python 3.12, confirms `agentdojo==0.1.35`, runs the backend's tests | no |
| `live-run` | builds the AgentDojo backend in a temporary home, `--offline-check`, a scripted `run`, then the mapping, differential and end-to-end tests | yes, after the project owner's yes |
| `backend-autodojo` | builds the AutoDojo backend, `--offline-check`, the harness tests, the fixture check | yes; dispatch-only |

There is no CI job for the AgentDyn or Inspect backends; their checks were run by hand. A network job is skipped without
`--allow-network`. Not run for this guide.

## Common refusals and their fixes

| You see | Because | Fix |
|---|---|---|
| `cannot run 'X': no live capability` or `live status planned` (5) | the source has no live backend (`rope`), or its live part is `planned` | none in this build; a `planned` part with a backend admits scripted runs only |
| `cli.refused.api_caps` (4) | an API endpoint without its caps | give `--max-calls`, `--max-cost-usd`, `--price-in`, `--price-out` |
| `--max-cost-usd needs --price-in and --price-out` (2) | the caps price needs prices | add both |
| `cli.refused.consent` (4) | no consent flag and no terminal | `--i-consent-to-local-run` (local) or `--i-consent-to-api-costs` |
| `cli.refused.containment` (4) | no `--containment`, or `sandbox-exec` off macOS or without a passed probe | declare `dedicated-user` or `vm` truthfully, or build the environment on macOS |
| `cli.environment.credential` (3) | no key in the keychain or `.env` | `agentprov keys set NAME`, or `--env-file` |
| `run.local.unreachable` / `model_not_served` (3) | the local server is down, or does not serve that id | start the server; use a served id |
| `cli.refused.local_tool_prompt` (4) | LM Studio serves the model without native tool use | `--allow-text-tool-calls` if you accept it |
| `cannot run 'X': defence … for the Y backend` (5) | a defence on a backend that does not build it, a replacing defence, or the wrong suite | use `agentdojo`, a registry defence, or the right suite |
| `--attack autodojo needs --autodojo-cache and --autodojo-variant` (2) | the cache pair is incomplete | give both, with a file from the pinned fork |
| `[inspect].limits: missing key(s) message_limit` (2) | an Inspect plan needs all three limits | add `--message-limit`, `--token-limit`, `--time-limit` |
| the run stops: "a cell's setup refused this configuration" (1) | for example, no `--model-display-name` | fix the option the notice names, re-run the same command |
| the run stops: "the canary found a misconfiguration" (1) | A3, A4, A6, A11, A12 or A14 | read the canary line, fix or accept, re-run |
| the run stops: `cap_reached` (1) | the next cell's worst case does not fit | raise the cap, re-run |
| `package.unsupported.live` (5) | live corpora cannot be sealed | none in this build |

More, with the exact messages, in [Troubleshooting](10-troubleshooting.md#live-runs).

## Further reading

- [`docs/reports/live-pilot/README.md`](https://github.com/nickjones39/AgentPROV/blob/main/docs/reports/live-pilot/README.md):
  the pilot, with its findings.
- [`docs/reports/inspect-harness/`](https://github.com/nickjones39/AgentPROV/tree/main/docs/reports/inspect-harness): the
  Inspect harness design, the cell bound and the probe.
- [`docs/reports/backends/agentdojo-env.md`](https://github.com/nickjones39/AgentPROV/blob/main/docs/reports/backends/agentdojo-env.md)
  and [`docs/reports/agentdyn-backend/README.md`](https://github.com/nickjones39/AgentPROV/blob/main/docs/reports/agentdyn-backend/README.md):
  how the environments were built and checked.
- [`docs/reports/local-llm/design.md`](https://github.com/nickjones39/AgentPROV/blob/main/docs/reports/local-llm/design.md):
  local servers, identity and drift.
- [`docs/reports/defence-backends/design.md`](https://github.com/nickjones39/AgentPROV/blob/main/docs/reports/defence-backends/design.md):
  the defences.
