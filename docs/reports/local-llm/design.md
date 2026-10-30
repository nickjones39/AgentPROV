# Local LLM endpoints: design note (D-690..D-699)

Session "local LLM endpoints" (2026-10-22), branch `claude/agentprov-local-endpoints-ea6a44` on integration
`d53faa60`. Orchestrator: "Phase 8 setup". Status: **proposed, nothing built**. The user decisions are in §9.

Goal (user, 2026-10-22): live runs can use models served on this Mac. In both the CLI and the GUI, the user sees and
picks the exact model that will run (orchestrator addition: with the same capabilities in both). The GUI calls the
CLI and has no discovery code of its own.

## 1. What exists today (checked at d53faa60)

| Piece | State |
|---|---|
| `endpoints.toml` | `ollama` (`127.0.0.1:11434/v1`, `LOCAL_LLM_BASE_URL`, `LOCAL_MODEL_ID`) and `omlx` (`127.0.0.1:8000/v1`, `server_max_concurrency = 8`, no env names). Both `local = true` with no key. |
| `check_base_url` | Compares the host only, not the port. `.env.example` sets `LOCAL_LLM_BASE_URL=http://localhost:11434/v1`, which fails the `127.0.0.1` host check unless `--allow-custom-endpoint` is given. |
| `run --endpoint` | Fixed choices `deepseek, openai, openrouter, local`; `local` maps to `ollama` (`run.py:46`, `:495`). Local servers are otherwise reached with `--model <shorthand> --model-id ID`. |
| Server preflight N.2.1a(1) | `presets.preflight_local_server` does a loopback `GET <base>/models`: peer address checked, no redirect, 8 MiB bound, strict JSON, model listed. **Not wired into `run`**; only unit tests call it. |
| `--preset` / `--m5ultra` | Dry run only. A real run with a preset exits 5 until the `--tune-jobs` calibration. |
| Served model | Already recorded per call: `llm.response.served_model` (`gateway.response_facts`) reaches AER `model_call.served_model` and PROV `apv:servedModel`. **Nothing compares it with the requested model.** |
| Model identity | `identity.agent` has `model_requested`, `provider`, `endpoint_host` and `sdk` (closed payload). No note records which weights served the run. |
| Notes | D-19: namespaced `note` events hold live facts that the frozen payloads lack. The AgentDojo capture mapper ignores note kinds it does not know (`capture_mapper.py:473`), so a new note changes no AER, SEM or PROV bytes. |
| Containment (D-664, held `c7fba04e`) | The profile allows exactly two loopback ports. For a loopback endpoint `endpoint_target(base_url)` passes the base URL's port as the allowed port and sets no proxy. |
| GUI (gui-g3, not merged) | `prices.py` already prices local endpoints at $0 ("time only"), but from a hard-coded `("ollama", "omlx")`, not the TOML `local` flag. The model field is an editable combo box filled from the price book. The D-654 parity test fails on any `run` option that has no GUI control. |
| This Mac | **LM Studio 0.4.23** (`lms`), with three MLX models in `~/.lmstudio/models` (Qwen3-8B mxfp4 4.1 GB, Qwen3-14B 6-bit 12 GB, Qwen3.6-35B-A3B 4-bit 23 GB). Ollama, oMLX, mlx-lm, llama.cpp and vLLM are **not installed**. No server was listening on 11434, 8000, 8080, 1234, 8081 or 10240 at 2026-10-22. |

## 2. Servers (D-690)

New registry entries (data in `endpoints.toml`), all `local = true`, no key, http on `127.0.0.1`.

| Shorthand | Server | Default base URL | `base_url_env` | `server_max_concurrency` | Tool calls (verified per model by preflight A4) |
|---|---|---|---|---|---|
| `ollama` (exists) | Ollama | `:11434/v1` | `LOCAL_LLM_BASE_URL` | unset (`OLLAMA_NUM_PARALLEL` depends on the version; observed values are not exposed) | Structured `tool_calls` when the model's capabilities include `tools`; otherwise HTTP 400. |
| `omlx` (exists) | oMLX | `:8000/v1` | add `OMLX_BASE_URL` | 8 | Structured, through oMLX's parser. |
| `lmstudio` | LM Studio server | `:1234/v1` | `LMSTUDIO_BASE_URL` | unset (observed: `loaded_instances[].config.parallel`) | Native for models with `trained_for_tool_use`. Other models use LM Studio's **default tool-use mode, which adds a server-side system prompt** that the wire capture cannot see (§5.4). |
| `mlx_lm` | `mlx_lm.server` (MLX LM) | `:8080/v1` | `MLX_LM_BASE_URL` | 1 (sequential by default) | Depends on the mlx-lm version and the model's chat template. Text-encoded calls are likely, so `--allow-text-tool-calls` is often needed. |
| `llamacpp` | `llama-server` (llama.cpp) | `:8080/v1` | `LLAMACPP_BASE_URL` | unset (observed: `/props` `total_slots`) | Structured only when started with `--jinja`; otherwise text. |
| `vllm` | vLLM OpenAI server | `:8000/v1` | `VLLM_BASE_URL` | unset (`--max-num-seqs`; no observable default) | Structured only with `--enable-auto-tool-choice --tool-call-parser <p>`. |

* The registry gains one key, `server` (one of `ollama, omlx, lmstudio, mlx_lm, llamacpp, vllm`). It is required when
  `local = true`, and it selects the discovery and fingerprint probes of §3. `parse_registry` rejects an unknown value.
* Two defaults collide: 8080 (`mlx_lm`, `llamacpp`) and 8000 (`omlx`, `vllm`). This is resolved by fingerprinting
  (§3.2): the server answering must be the kind the shorthand names, or the run is refused (exit 4) and the refusal
  names the kind that answered.
* Concurrency values are the servers' documented defaults only where they are stable. Where a server reports its
  real value (LM Studio, llama.cpp), the observed value wins and is recorded, and `--server-max-concurrency`
  overrides both.
* `--endpoint` accepts every `local = true` shorthand besides `local` (the orchestrator's `--endpoint <local>
  --model-id <name>` form). `--model <shorthand>` keeps working. `ENDPOINT_NAMES` is computed from the registry.
* `.env.example` changes to `127.0.0.1`. The code is not loosened, because `localhost` can resolve to `::1`, which
  the D-664 probe does not test (§7).

## 3. Discovery: `agentprov models` (D-691)

### 3.1 CLI shape

The recommendation is a new command, `agentprov models`. Listing is not about a source, so `run SOURCE
--list-models` would need a meaningless SOURCE. The `run --catalogue` precedent (D-652) fits because a catalogue
depends on the backend; a model listing does not.

```
agentprov models                               # every local endpoint: up/down, server kind and version, model count
agentprov models --endpoint lmstudio           # that server's models, one row each
agentprov models --base-url http://127.0.0.1:1235/v1   # any loopback URL; the server kind is fingerprinted
agentprov models --endpoint lmstudio --model-id qwen3-8b-abliterated-v2-mxfp4   # the full identity record (§4)
agentprov models ... --format json             # the agentprov-local-models/0.1 document on stdout (as info --format)
```

`run` gains:

* `--base-url URL` (loopback only; a non-loopback URL is refused with exit 4 and its value is never printed). It
  overrides the endpoint's `base_url_env`. A port other than the registry's is recorded, the same as
  `--allow-custom-endpoint`.
* Model selection by name: a missing or unlisted `--model-id` for a local endpoint is refused before anything
  starts (exit 3, as N.2.1a(1) already specifies), and the refusal lists the served ids with close matches. On a
  terminal, `run` offers a numbered pick instead. A non-terminal never prompts.
* The N.2.1a(1) preflight (`GET /models`, id listed) is wired into `run`, before consent and before the plan worker.

The GUI's Run live form calls `agentprov models --endpoint X --format json` to fill its picker (a combo box showing
display name, id, quantisation, size and a loaded marker). It calls `--model-id` for the identity panel. Both are the
same code as the CLI.

### 3.2 What is queried (read-only, loopback, no inference, no model load)

| Server | Fingerprint | Listing | Identity for one model |
|---|---|---|---|
| Ollama | `GET /api/version` | `GET /api/tags`: name, digest (manifest sha256), size, `details{format, family, parameter_size, quantization_level}`; cloud entries are flagged remote | `POST /api/show {model}`: capabilities, `model_info` (architecture, parameter_count, context_length), and digests of template, parameters and modelfile |
| LM Studio | `GET /api/v1/models` answers in its shape | `GET /api/v1/models`: key, publisher, architecture, `quantization{name, bits_per_weight}`, size_bytes, params_string, format (`mlx`/`gguf`), loaded_instances (context_length, parallel), `capabilities.trained_for_tool_use`; plus `GET /v1/models` (the ids the run route serves) | model directory files (§4.2) |
| mlx_lm | `GET /v1/models` shape (HF-repo or path ids) | `GET /v1/models` | HF cache snapshot (§4.2) |
| oMLX | `GET /v1/models` (`owned_by`) | `GET /v1/models` | `--model-dir PATH` given by the operator (§4.2) |
| llama.cpp | `GET /props` | `GET /v1/models` (`meta`: n_params, size, n_ctx_train) | `/props`: model_path basename, total_slots, chat-template digest, build_info; GGUF file digest (§4.2) |
| vLLM | `GET /version` | `GET /v1/models` (`root`, `max_model_len`) | HF cache snapshot when `root` is a repo id |

Rules, one implementation in `src/agentprov/cli/live/localmodels.py` (class 0):

* Loopback hosts only, checked before connecting. The connected peer address must be loopback (the
  `preflight_local_server` method). `http.client` is used, never `urllib`, which honours `HTTP_PROXY` and could carry
  a loopback request to a remote proxy. No redirect is followed, no credential is sent, and timeouts are 5 s.
* Each response is at most 8 MiB, parsed with `agentprov.ingest` `strict_json_loads` under `IngestLimits`, and
  validated field by field. Unknown members are dropped. Strings are bounded and shown through `quote_untrusted`.
  Ids are labels, never paths.
* Every response's sha256 is kept, and the identity record cites it.
* `/api/show` (Ollama) is the only POST. It reads metadata and does not load the model.
* Model rows that the server marks as remote (Ollama cloud models: `remote_host`, `-cloud` names) are listed with
  `remote: true` and refused by `run` (exit 4). A local server that forwards inference off the machine would defeat
  the containment of §7.

## 4. The identity of the model that will run (D-692, D-693)

### 4.1 The record (`agentprov-local-model/0.1`)

These are observed facts only. Each fact names where it came from (a response digest and a pointer, or a file
digest). Missing facts are `null` with a reason, never guessed.

```
{format, observed_at (T0 UTC clock), endpoint, base_url, server{kind, version, fingerprint_sha256},
 model_id (requested), listing{path, sha256, entry (the served entry, bounded)},
 server_identity{...per server: ollama digest/family/parameter_size/quantization_level/format/capabilities,
                 show_sha256, template_sha256; lmstudio key/publisher/architecture/quantization/format/params/
                 trained_for_tool_use/parallel; llamacpp total_slots/chat_template_sha256/build ...},
 files{method: hf_cache | lmstudio_dir | operator_dir | null, label (repo id or dir name; never an absolute path),
       snapshot_commit, files[{name, size, sha256, sha256_source: computed | hf_blob_name}], weights_hashed},
 identity_sha256 (JCS digest of the server_identity and files parts)}
```

Absolute paths are never recorded, because they hold the account name (the account-path rule). Directories are
recorded relative to the models root, for example `mlx-community/Qwen3-8B-abliterated-v2-mxfp4`.

### 4.2 File digests (MLX and GGUF servers)

* **HF cache** (`mlx_lm`, `vllm`; also any id that is a repo id): `models--org--name/refs/<rev>` gives the snapshot
  commit. LFS files (weights) are symlinks to `blobs/<sha256>`, so **weight digests come from the blob names**. The
  name is checked to be 64 hex characters and the target is checked to stay inside the repository directory; no
  hashing is needed. Small files are hashed.
* **LM Studio**: the models root is `downloadsFolder` in `~/.lmstudio/settings.json` (strict, bounded parse), with
  `~/.lmstudio/models` as the fallback. The directory is matched to the served key by exact, case-insensitive name
  under `<publisher>/`. It must match exactly one directory, or `files` is `null` with reason `ambiguous` or
  `not_found`.
* **oMLX, llama.cpp**: no API names the directory or file, so `--model-dir PATH` (today a preset-only flag, which
  becomes a run and models flag) names it. The record says `operator_dir`. For llama.cpp the `/props` model_path
  basename must equal the given file's name.
* Always hashed: `config.json`, `generation_config.json`, `tokenizer*.json`, `chat_template*`, `*.index.json` and
  `params`/`template` files. These are small, and their bytes are hashed, not parsed.
* **Weights** (`*.safetensors`, `*.gguf`, `*.npz`): hashed with `hashlib.file_digest` and kept in a digest cache
  (`$AGENTPROV_HOME/cache/model-digests.jsonl`, keyed by device, inode, size and mtime_ns). Hashing the 23 GB model
  once takes about 10–20 s on the M2 Max, and runs after that are instant. Default on (Q3), with `--no-hash-weights`
  recorded as `weights_hashed: false`.
* Walking the directory: depth ≤ 3, ≤ 512 entries, regular files only, symlinks resolved and required to stay inside
  the model or cache root. No file is opened for writing, and no archive is involved.

### 4.3 Where it is shown and recorded

* **Before Start**: `run --dry-run` prints a "model" block: endpoint, base URL, server kind and version, model id,
  display name, family, size, quantisation, the digests (short), `identity_sha256`, and the estimate line (§6). The
  consent text for a local endpoint says "local server: no provider billing; the run loads this machine heavily"
  instead of "may be billed". `--plan-json` (D-651) gains a `model` member with the same record (coordinated with
  the GUI session).
* **In the configuration**: the T0 agent dict gains `local_model` (the record without `observed_at`). It enters
  `plan_sha256` and `config_digest`. A different model (other weights, other quantisation) is therefore a different
  configuration, and the existing G5 rule refuses to mix it into a working corpus without `--allow-mixed-config`.
  Remote endpoints' digests do not change, because the member is only present for local endpoints.
* **In every session**: T0 re-observes the server-side identity (no file hashing; files are rechecked by stat
  against the cache) just before each cell, and passes it in `run_cell`. The worker writes it as header note
  `agentdojo/local_model` (`ns` follows the backend id, as the other header notes do). Its payload is the record
  plus `matches_plan: bool`. capture/0.1 is unchanged (D-19 notes).
* **Drift**: a session whose re-observation differs from the plan's identity (for example a model re-pulled under
  the same tag mid-campaign) gets `matches_plan: false`. The quality report counts it, and it is a canary condition
  (§5.2; A14).

## 5. Served model and findings (D-694, D-695)

### 5.1 Served model check

`quality.py` already parses each `llm.response`. It gains, per session, a `served_models` counter (the
`served_model` values) and a `served_model_mismatch` count: kept or discarded responses whose `served_model` is
absent or differs from the request body's `model`. Each report row gains `served_models` and
`served_model_mismatch`, plus `local_model_drift` (§4.3). These are all integers or names, so H.1.4(3) holds.

### 5.2 Canary and refusal

* **A12 served model differs from requested**: a canary condition, so the campaign stops after the canary cells
  ("never silently accepted").
* `--accept-served-model ID` (repeatable, recorded in `live`) names the served ids the operator accepts. Remote
  providers often serve a dated snapshot for an alias (`gpt-4o` → `gpt-4o-2024-08-06`), and that operator decision
  then appears in the manifest.
* **A14 local model identity drift** (A13 is taken in D.10.9): a canary condition on any `matches_plan: false`.

### 5.3 Effect on remote runs

A12 also applies to remote endpoints (Q4). The alternative is local-only, with remote mismatches reported but not
stopped.

### 5.4 LM Studio default tool use

For a model without `trained_for_tool_use`, LM Studio adds its own tool-use system prompt on the server, so the
request the model sees differs from the recorded wire request. Recommendation (Q5): refuse such a model unless
`--allow-text-tool-calls` is given. The `server_identity` records `trained_for_tool_use: false`, and the dry run
warns.

## 6. Estimate (D-696; with the GUI session)

* Cost: local endpoints are $0. The GUI's `prices.py` should read the registry `local` flag instead of its
  hard-coded `("ollama", "omlx")` list (a GUI-session change).
* Time: there is no measured throughput yet. The CLI dry run prints `cost $0.00 (local endpoint); time: needs a
  measured throughput (--tune-jobs, N.2.1a(4))`, unless the GUI session's estimator has a time basis we agree on. The
  question is open with the GUI session. Calls per cell come from the D-653 priors, and seconds per call would need a
  measurement; no inference happens without the user's yes.
* `--plan-json` carries `estimate{cost_usd: "0", time: null|{p50,p90,basis}}` so the GUI shows the same numbers as
  the CLI.

## 7. Containment (D-697; with the Inspect harness session)

* D-664's `endpoint_target(base_url)` already returns the base URL's port for a loopback endpoint, which becomes
  `LOOPBACK_PORT`, with no proxy. Every new entry has an explicit port, so nothing in D-664 needs to change. One
  allowed port is enough, because every per-session observation of §4.3 is made by T0, not by the worker.
* Asks for the Inspect harness session:
  1. The sync `default_inner_transport()` proxy half must set no proxy when `AGENTPROV_EGRESS_PROXY` is absent (the
     loopback case).
  2. The profile's `localhost:PORT` rule should be probed on `::1` too, or local base URLs should be pinned to
     `127.0.0.1`. The proposal pins them (§2) and refuses `localhost` for `--base-url` unless the probe covers
     `::1`.
* Discovery runs in T0 only. It uses `http.client` against a loopback peer, never goes through a proxy, and never
  reaches a non-loopback host (§3.2). Remote-flagged models are refused (§3.2).
* Limit, stated in the spec: our containment covers our processes (T0, T2). It does not cover the user's server
  process. A server set up to forward inference off the machine is only detected when it says so.

## 8. Commits, classes and downstream effects

| Commit | Content | Class | Effects |
|---|---|---|---|
| A (separate, rebuild window) | `endpoints.toml` entries and `server` key, `endpoints.py` validation | 0 | Capture package bytes, so every built environment's identity changes (env rebuild window with D-652/D-656/D-664). |
| B (separate, rebuild window) | `backends/shared`: `AgentConfig.local_model`, the `run_cell` field, the `local_model` header note | 0 | Environment identity. New local sessions carry one more note. No AER/SEM/PROV bytes (the mapper ignores the note). |
| C | `cli/live/localmodels.py`, `cli/models.py`, `run.py` (preflight wiring, `--base-url`, `--accept-served-model`, `--model-dir` for local, dry-run model block, `--plan-json` `model`), `quality.py` (A12/A14) | 0 | `live` manifest block gains `quality.models.*.served_*`, `accepted_served_models`. `config_digest` changes for local runs only. **Conflicts:** `run.py` is also edited by gui-g3 (D-651/D-652) and D-664. New code goes in new functions to keep merges mechanical, and it rebases onto whichever lands first. |
| D | Spec: N.2 (the `models` command; COMMANDS 15→16), N.2.1, N.2.1a(1), N.2.1b, D.10.9 (A12 extended, A14), G.4.10/G.6.3 (the limit of §7), M.1.10 (the `server` key); DECISIONS D-690..D-697; AGENTS.md entry; `.env.example` | 0 | Docs only. |

**Class-1 follow-up (offered, not built):** map the `local_model` note into the AER actor identity (AgentDojo capture
mapper) on a held branch, so PROV can carry the weight digest. Until then the identity is in raw evidence and the
manifest only.

**Tests:** a stdlib `http.server` stub on an ephemeral loopback port serves synthetic Ollama, LM Studio, mlx_lm,
llama.cpp and vLLM shapes, including hostile ones: oversize, duplicate keys, NaN, wrong kind on the port, redirect,
remote-flagged model, path-like ids. A temporary HF-cache and LM Studio tree is used too. The tests cover `models`
(text and JSON), the `run --dry-run` model block, the preflight refusal and pick, the A12/A14 quality counts on
synthetic capture logs, and a scripted run whose script serves a mismatching `model`. The GUI side runs the D-654
parity test once its controls land. No real model is needed.

## 9. User decisions

* **Q1 servers.** Add `lmstudio`, `mlx_lm`, `llamacpp` and `vllm`, all as data (recommended). Only LM Studio is
  installed here; the others are tested against stubs. Alternative: `lmstudio` and `mlx_lm` only.
* **Q2 CLI.** Add the new `agentprov models` command (recommended), or `run SOURCE --list-models`.
* **Q3 weight hashing.** On by default with the digest cache (recommended; about 10–20 s once per model), or opt-in.
* **Q4 served-model mismatch.** A canary stop for every endpoint, with `--accept-served-model` (recommended), or for
  local endpoints only.
* **Q5 LM Studio models without native tool use.** Refuse unless `--allow-text-tool-calls` (recommended), or allow
  with a warning.
* **Q6 per-cell re-observation by T0** (recommended), or once per campaign.
* **Q7 permission (typed yes)**:
  * (a) start LM Studio's server (`lms server start`; no download) so that discovery can be checked against the
    real API shapes. This is listing only, and no model is loaded;
  * (b) separately, one preflight probe (a single inference call) on `mlx-community/Qwen3-8B-abliterated-v2-mxfp4`
    (4.1 GB, the smallest installed model).

  Nothing is downloaded or installed in either case.

## 10. User decisions and the check against a real server (2026-10-22)

**Decisions** (relayed by the orchestrator, then "yes to all" in this window):

* Q1: all four servers.
* Q2: `agentprov models`.
* Q3: weight hashing on, with a cache.
* Q4–Q6: as recommended.
* Q7 (a) and (b): yes.
* The LAN design that was put to the user (an opt-in `--allow-lan-endpoint`, numeric private addresses, a T0 relay, http allowed, recorded) is approved, with these choices:
  * the private ranges include 100.64.0.0/10;
  * the address is recorded as-is (re-asked and confirmed by the user on 2026-10-22: the full address, not `lan` plus the port).
* Also required:
  * cross-platform paths;
  * host and port set through `agentprov settings` (`endpoints.<name>.base_url`; the GUI session's D-703 module `agentprov.settings`), with precedence `--base-url` > `.env` > settings > registry.

**Discovery against LM Studio 0.4.23** (`lms server start`, listing only). Three findings changed the code:

1. LM Studio's model key is not the directory name. For example, key `qwen3-8b-abliterated-v2` belongs to `mlx-community/Qwen3-8B-abliterated-v2-mxfp4`. The directory is now matched by name prefix and **the exact `size_bytes` the server reports** (`match: name_and_size`). An ambiguous match records no directory.
2. Unknown routes (`/api/version`, `/props`, `/version`, `/api/tags`) answer **HTTP 200 with an error object**. The fingerprint already checks each route's shape, so nothing was misidentified. The stub now behaves the same way.
3. `/v1/models` also lists the embedding model. Ids that the native listing types as non-chat are now left out of the rows.

Other facts observed:

* `/api/v1/models` matches the documented shape.
* The `loaded_instances[].config.parallel` of a loaded model was 4, with context length 40960.
* `system_fingerprint` in a reply is the model key.
* `models --endpoint lmstudio --model-id qwen3-8b-abliterated-v2` hashed 7 files (4.35 GB) in about 8 s (cold cache).

**One inference call (Q7 b).** The CLI's `run agentdojo --preflight-only --model lmstudio ...` exits 5, because AgentDojo's live status is still `planned` (only scripted runs are allowed until its gates pass). That gate was not bypassed. The probe request of D.10.9 was sent directly instead: the `developer`-role instruction, the two probe tools and `tool_choice: auto`, with model `qwen3-8b-abliterated-v2`. The results:

* HTTP 200 in 23.9 s, including the model load (JIT);
* the served `model` equals the requested one, so A12 holds;
* `finish_reason: tool_calls`, with a structured call `get_probe_value({"key": "q7f3-probe"})`, so A4 is `structured` and A9 `accepted` (the instruction was followed);
* `reasoning_content` was returned, and 137 of the 166 completion tokens were reasoning tokens;
* response sha256 `f4d2678d…a3df`.

The model was unloaded afterwards (`lms unload --all`), and LM Studio's server was left running. No capture session was written, so this is a check of the server, not evidence.

## 11. API providers' model lists (D-730..D-739; user requirement 2026-10-22)

The picker should always offer a working list, so `agentprov models` also covers the API providers.

* **Sources.** Each provider's own list endpoint:
  * OpenRouter `/api/v1/models` (public);
  * Anthropic `/v1/models` (paged);
  * OpenAI `/v1/models`;
  * DeepSeek `/models`.

  gemini, llama, qwen and glm are OpenRouter's list filtered by vendor prefix. These are list calls only, with no
  tokens and no cost.
* **When the network is used.** Only with `--allow-network` (R2), or with `--refresh-if-stale` when the user has
  switched on `models.auto_refresh`. Switching it on is the user's standing consent for these free list calls, at most
  once a day per provider. Otherwise the command reads a dated cache in `$AGENTPROV_HOME/models-cache/`, marked stale
  after 24 h.
* **Data rules.** Registry host only, TLS verified, no proxy or redirect, strict bounded JSON, ids as labels. Keys come
  only from the keychain, `--env-stdin` or `--env-file`, and travel only in their header.
* **Prices.** Each model's `price_status` comes from the D-701 price table; priced models the provider no longer lists
  are shown as `not_listed`.
* **Run.** A model missing from the cached list is a warning before the run, never a refusal; A12 still compares the
  served model.

Verification against the real providers is pending the first real refresh. The Anthropic shape follows its published
reference; DeepSeek's auth header and OpenRouter's public access are taken from their documentation and third-party
notes.

## 12. Load state is not identity (D-736; live pilot Part L, 2026-10-22)

The pilot found that LM Studio's identity digest changed when the model was loaded: `671beca3…` unloaded, `95d6f4a5…`
loaded, with the same files. A run started cold and resumed warm would have been refused as mixed configuration.

Load and serving state now lives in `observed_state`, outside every digest:
* LM Studio: `loaded_instances`, `parallel`, and the loaded instance's `context_length`;
* llama.cpp: `total_slots`.

Each server's version is recorded with its source. LM Studio exposes none over HTTP, so its version is `null` with
"not exposed by the server"; its `/lmstudio-greeting` joins the fingerprint. The record format is now
`agentprov-local-model/0.2`.

On the user's LM Studio, with the model loaded, the record keeps `{loaded_instances: 1, parallel: 4,
context_length: 40960}` under `observed_state`, and the identity holds only the model's facts.
