# Direct Anthropic endpoint (D-656): design note

Status: **proposal, no code yet** (2026-10-22). Branch `anthropic-endpoint` from the pre-round integration head
`341bc0a7`. No real API call has been made; nothing here was measured against the live API. Facts about the Anthropic
SDK and AgentDojo come from the installed, locked packages (`anthropic` 1.11.0, `httpx2` 2.13.1, `agentdojo` 0.1.35 in
`~/.agentprov/envs/autodojo-aa458794`, whose `anthropic_llm.py` is byte-identical to the stock 0.1.35 wheel in the uv
cache). Facts about the Messages API (stop reasons, thinking display, sampling limits on current models) come from the
current API reference. Each one is marked *to confirm* where a scripted test cannot settle it.

**Short answer.** `capture/0.1` can hold a Messages exchange faithfully: no `capture/0.2` is needed. The harness work
(element, transport, recorder, scripted transport, endpoint entry) is all in `backends/shared` and `capture/` endpoint
data, and is class 0 for stored corpora. The capture mapper must learn the Messages wire form to get context membership,
reply agreement and discarded replies right. That part is class 1 (the aer stage code digest moves). AER bytes of every
stored corpus stay the same, unless the new rules go into the shared `agentdojo` catalogue (§3.6).

Decisions for the user are collected in §8.

---

## 0. What exists, and one correction to the brief

* The recording transport (`backends/shared/.../transport.py`) is **not** a stdlib HTTP client. It is an
  `httpx2.BaseTransport` placed under the **SDK client** of AgentDojo's stock LLM element. `_http.py` only finds which
  httpx-family module that SDK uses. The design rule it implements (AD-09, K.8.1, D.10.10 item 2) is that the recorded
  wire bytes are genuine output of the **unmodified stock element**. A bounded stdlib client in `_http.py` would mean
  writing our own Messages client and bypassing AgentDojo's element, which breaks that rule. This note therefore keeps
  the SDK, as the OpenAI path does.
* **The SDK is already locked. Nothing new is downloaded for the backend environments.** `anthropic` 1.11.0 is a
  dependency of `agentdojo==0.1.35`, and it is in both `backends/agentdojo/uv.lock` and `backends/autodojo/uv.lock`
  (wheel sha256 `52f97b2c…ee21`, inside `exclude-newer = 2026-10-07`). The core never sees it.
* AgentDojo 0.1.35 ships a stock Claude element, `agentdojo.agent_pipeline.llms.anthropic_llm.AnthropicLLM`. It is the
  Messages-format counterpart of the stock `OpenAILLM` that `native` runs today. What it does matters for recording:
  * it is **async**. It needs an `AsyncAnthropic` client and calls `asyncio.run(...)` once per query. Given a sync
    `Anthropic` client, it builds a new `AsyncAnthropic` from `api_key`/`base_url`/`timeout`/`max_retries` only, which
    **drops a custom `http_client`**. So the harness must pass an `AsyncAnthropic` that already carries an *async*
    recording transport. Otherwise exchanges would go out unrecorded;
  * it **streams** (`client.messages.stream(...)` → `get_final_message()`), so the response entity is
    `text/event-stream`;
  * it sends `temperature` whenever it is not `None` (default `0.0`). That differs from the OpenAI path, where
    `temperature or NOT_GIVEN` drops a zero. Its default `max_tokens` is 1024. Thinking is
    `{"type": "enabled", "budget_tokens": n}` only when `thinking_budget_tokens` is set. It has no effort setting;
  * it lifts the first system message into the top-level `system` string. It renders tool messages as `tool_result`
    blocks (`is_error`, with the error text substituted when there is an error). It **merges consecutive user/tool
    messages into one user turn**, keeps thinking and redacted-thinking blocks (with `signature`) in the AgentDojo
    message and sends them back, parses tool calls only when `stop_reason == "tool_use"`, and deletes tool calls whose
    names fail `^[a-zA-Z0-9_-]{1,64}$`;
  * it retries with tenacity (3 attempts, not on `BadRequestError`) on top of the SDK's own retries (default 2).

## 1. Wire format: how one Messages exchange is recorded

The recording follows the existing `llm.request`/`llm.response` contract (C.13.3). Each wire exchange is recorded,
SDK retries included.

| What | How it is recorded |
|---|---|
| Request | `POST <base>/v1/messages`. The exact body bytes the SDK built go into the `request` blob (`application/json`). `endpoint {host: "api.anthropic.com", path: "/v1/messages"}`. `params.transmitted` = the decoded body minus `model`, `messages`, `tools` **and `system`** (system is content, not a parameter), so it holds `max_tokens`, `stream`, `temperature`, `thinking`, `output_config`, … exactly as sent. `params.configured` is the plan's params, as today. |
| Streaming | The stock element always streams. The response blob is the **whole SSE entity as received** (`text/event-stream`, after content decoding, as for JSON today). The transport reads the stream to its end before handing it to the SDK. The SDK sees the same bytes, and the stock element waits for `get_final_message()` anyway, so the pipeline sees no difference (§1.2). Per-event arrival times are not recorded (§2). |
| Non-streaming | When an element sends no `stream: true` (the opt-in element of §4.2 can), the blob is the JSON `Message`. The same fact extractor handles both forms. |
| `tool_use` / `tool_result` | They live in the bodies: `tool_use {id, name, input}` in the response, and `tool_result {tool_use_id, content, is_error}` in the next request. In a stream, `input` arrives as `input_json_delta.partial_json` pieces. Their concatenation is the model's lexical arguments, and the mapper uses it as `args_raw` (§3.3). |
| Thinking | `thinking {thinking, signature}` and `redacted_thinking {data}` blocks stay verbatim in the blob (`thinking_delta` and `signature_delta` in a stream). With display `omitted`, the default on current models, `thinking` is `""` and only the signature is present. That is recorded as it is; the AER treatment is §3.4. |
| Cache control and usage | The stock element sends no `cache_control`. `usage` is extracted as the provider reports it: `input_tokens`→`input_tokens`, `output_tokens`→`output_tokens`, `cache_read_input_tokens`→`cache_read_tokens`, `cache_creation_input_tokens`→`cache_write_tokens`. This is the D-283 `anthropic-messages` mapping. There is **no `total_tokens`** (not reported, never computed) and **no `reasoning_tokens`** (thinking tokens are counted inside `output_tokens`, not reported separately). In a stream, each key takes the value from the last event that reports it (`message_delta.usage` over `message_start.message.usage`), which is what the SDK's final message carries. The 5m/1h cache-write split, `service_tier`, `inference_geo`, `server_tool_use` and `speed` stay in the blob only (the capture `usage` shape is closed). |
| Stop reason | `stop_reason` → `finish_reason`, verbatim: `end_turn`, `tool_use`, `max_tokens`, `stop_sequence`, `pause_turn`, `refusal`. `stop_sequence` and `stop_details` (refusal category) stay in the blob. |
| Other facts | `message.id` → `response_id` and `message.model` → `served_model`. Both are taken from `message_start` in a stream. |
| Errors | A non-2xx reply (400/401/403/404/413/429/500/529, Anthropic error JSON `{"type":"error","error":{type,message},"request_id"}`) is `status: error`, `reason: http_<n>`, as today. **New:** a 2xx stream carrying an `error` event (for example `overloaded_error` mid-stream) is `status: error`, `reason: stream_error:<type>`, `http_status: 200`. It is not a model reply, and it is the Messages analogue of OpenRouter's 2xx error object. A stream that ends without `message_stop` keeps the status the element's fate decides (as today) and gets a note `agentdojo/stream_incomplete`. |
| Retries | The SDK retries (408/409/429/5xx and connection errors, honouring `retry-after`/`x-should-retry`) and tenacity retries are separate wire exchanges, chained by `retry_of`, with the earlier reply `discarded` (`superseded_by_retry`), exactly as for OpenAI. |
| Headers | `note agentdojo/wire_headers`, as today, with endpoint allowlists (§4.3). |

### 1.1 `input_at` on the Messages wire

`WireRecorder` records `input_at` only when the decoded request carries exactly `n_messages` messages. On the Messages
wire that test always fails, because the system message is lifted out and user/tool runs are merged. The check becomes
format-aware. The expected wire count is computed from the span's message roles under the stock rendering: drop a
leading system message, then count assistant messages plus maximal runs of non-assistant messages. The recorder also
checks that `system` is present exactly when a leading system message is. If both hold, `input_at = [0..n-1]` is
recorded (the stock element sends every message it is given, as OpenAILLM does). If not, it falls back to
`input_at_unverified`, as today.

### 1.2 Async recording transport

The new `AsyncRecordingTransport` (`httpx2.AsyncBaseTransport`) is the async twin of `RecordingTransport`: the same
observer and the same guarantees (it never modifies a request or a response, and a request whose observer raises is not
sent). The observer runs synchronously inside the event loop. Each `asyncio.run` gets the same recorder and capture
session.

**Risk R-1, to confirm.** The stock element keeps one `AsyncAnthropic` (one connection pool) across `asyncio.run`
calls, so a keep-alive connection opened in one event loop may be reused in the next, after that loop has closed. That
is stock AgentDojo behaviour, and the recording sees whatever happens (a transport error, then an SDK retry). A scripted
transport has no pool, so it cannot show the effect. Two options:
(a) leave it stock, and confirm with one capped probe (§8 Q6);
(b) give the inner transport `max_keepalive_connections=0` and declare it as a `harness_policy` item. I recommend (a)
first, and (b) only if the probe shows failures.

## 2. Can `capture/0.1` hold it? Yes; no `capture/0.2`

Checked against the frozen shapes (`events.DATA_MEMBERS`, `capture-0.1.schema.json`):

* `request`/`response` are blob references with a free `media`, so SSE bytes and JSON bytes both fit, verbatim.
* `llm.response.usage` is the closed AER `Usage`, which already has `cache_read_tokens` and `cache_write_tokens`.
  `finish_reason`, `served_model` and `response_id` are free strings. `status` already has `error`.
* `identity.agent.provider` and `actors.*.model.provider` are free strings, so `"anthropic"` fits.
* Headers already go through `note` (`wire_headers`), and new harness facts (`stream_incomplete`) through `note`.

What `capture/0.1` cannot hold, and why that is acceptable:

1. **Per-event stream timing** (time to first token, chunk arrival). There is no event type for it, and a `note` per
   chunk would be noise. The transport also buffers the stream, so the times would describe our buffering rather than
   the model. AgentDojo's semantics do not use them. If the research ever needs time to first token, that is a
   `capture/0.2` event type (or a summary `note`), proposed then.
2. **Usage members beyond the closed set** (5m/1h cache split, server tool counts, service tier, geography). They
   stay in the response blob, which is the evidence. Nothing is lost; it is just not lifted into structured fields.

So the recommendation is **no `capture/0.2`**. capture/0.1 is not edited; the additions are harness behaviour inside
its contract (C.13.10-style resolutions) and endpoint data. This is still a user decision (§8 Q1), because the brief
asked for one.

## 3. AER mapping (capture mapper, class 1)

The mapper keeps its structure. Messages-specific decoding goes into a new module
`src/agentprov/adapters/agentdojo/messages_wire.py`, and SSE decoding into a bounded stdlib parser
`src/agentprov/ingest/sse.py`. Untrusted bytes are parsed only through `agentprov.ingest`: line, event and total limits
come from `IngestLimits`, and each `data:` payload goes through the strict loader. The mapper switches on a recorded
fact, `identity.agent.provider == "anthropic"` (O by capture). A request blob that does not decode as Messages under
that declaration raises an issue, and no Messages claim is made.

### 3.1 Context (`model_call.input`)

* With `input_at` recorded (§1.1), membership is `O`, as today.
* **Sent form.** The native dump is matched to the wire by *units*, not by wire messages. A system message
  corresponds to `system`. A user message with k content blocks corresponds to the next k text blocks of the current
  user turn. A tool message corresponds to the next `tool_result` block. An assistant message corresponds to the next
  assistant message. The stock rendering is not a transform: the system lift, the merging, `tool_result` with
  `is_error`, `input` as an object, thinking blocks with `signature`, and members the SDK adds when it serialises
  AgentDojo's `TextBlock` (for example `citations: null`; the exact set is pinned by the scripted tests on genuine SDK
  output). `error_substitution` keeps its meaning for a tool message sent as its error text. `sent_sha256` is the JCS
  digest of the unit, as a slice of blocks. A new rule `agentdojo.capture_messages_form@1` (class D) states this. It
  cites `anthropic_llm.py` `_conversation_to_anthropic`/`_merge_tool_result_messages`/`_message_to_anthropic` at the
  pinned AgentDojo commit.
* **Without `input_at`**, there is no alignment fallback in the first version. `input` is `unk ambiguous` with the
  existing issue, which is honest. `cap.context_alignment@1` speaks of messages matched one to one, and stretching it
  to units would be a rule change. It can be added later as its own rule if a case appears.

### 3.2 Output link and reply agreement

`_reply_agrees` decodes the reply as a Messages `Message` (JSON or a rebuilt SSE). It compares the native text blocks
with the wire `text` blocks, and the tool-call names with the `tool_use` names **only when `stop_reason ==
"tool_use"`**, mirroring `_anthropic_to_assistant_message`. Stock-filtered names (invalid tool names) are expected
absences: the dump lacks them and the wire has them. They are reported as `unexecuted_tool_call` on the wire part, as
for a rejected reply, and never as a mismatch.

### 3.3 Discarded replies

A discarded reply becomes a message `generated_by` its call, as today, with parts from the Messages blocks: `text` →
text, `thinking` → reasoning (with `signature`), `redacted_thinking` → reasoning `redacted`, `tool_use` → tool_call.
For a tool_call, `args` = `input`. `args_raw` is set to the concatenated `partial_json` when the reply was streamed.
When that raw text is not valid JSON, `args` is `unk ambiguous`, as for malformed OpenAI arguments. `src` points into
the response blob (`/content/<i>` for JSON; for SSE, the event index; the exact locator is fixed in §3.5).

### 3.4 Reasoning shown as empty

The stock element puts thinking blocks into the AgentDojo message, so they are already `reasoning` parts in the dump
(`content_block_parts`, with `signature`). Under the current models' default display `omitted`, their text is `""`.
That is the provider **withholding** the reasoning (C.7 `withheld`: "hidden reasoning"), not a model that reasoned
nothing. Writing `text: ""` as an observed fact would invite exactly that misreading in SEM.
**Proposal (§8 Q4).** Under `aer/0.2` (D-210..D-213: a part's `text` may be absent and declared `withheld`), a
reasoning part whose wire block has `thinking == ""` and a non-empty `signature` gets its text withheld under a new D
rule `agentdojo.capture_thinking_omitted@1`. Under `aer/0.1`, it stays `""` as recorded, and the seal carries an issue.
This also touches the shared `content_block_parts` (the TraceLogger mapper reads the same dump), so the K.9.1
live-versus-native projection must treat both sides alike.

### 3.5 Other fields and evidence rules

* `usage`, `finish_reason`, `served_model` and `response_id` are `O:provider`, copied from the `llm.response` event as
  today. Nothing is filled in: a missing key stays absent, and there is no `total_tokens`.
* **Semantic note for the spec and for consumers.** The AER `Usage` does not say whether `input_tokens` includes cached
  tokens. OpenAI's `prompt_tokens` includes them; Anthropic's `input_tokens` excludes both cache reads and cache
  writes. The fields are recorded as observed, with `model.provider` alongside. Stats and the GUI estimate must not add
  them across providers naively. The C.3.12 `Usage` line gets one sentence saying so. This is documentation only, with
  no byte effect.
* No relation comes from timing. Times are the `llm.request`/`llm.response` event times, never stream times, and no
  timestamp is filled in.
* Refusals: `finish_reason: "refusal"` (O:provider). There is no refusal text part, because the Messages API sends
  none. `_wire_reply_fields` adds nothing on this path (the reasoning is already in the dump).
* **SSE locators.** For a part read from a stream, `src` is the blob plus a pointer of the form `/events/<k>` into the
  parsed event list. The parsed event list is a deterministic function of the blob (`ingest/sse.py`). The locator
  grammar (C.11) already allows a blob pointer, and the pointer target is defined by the parser version, which is
  pinned in the rule.

### 3.6 Byte class and digests

| Change | Where | Class |
|---|---|---|
| `messages_wire.py`, `ingest/sse.py`, mapper dispatch | aer stage closure (D-451) | **1**: the aer stage code digest moves. AER bytes are unchanged for every stored corpus: no kept corpus holds `agentdojo.capture` sessions (checked `~/.agentprov/corpora/*/corpus.json`), and OpenAI-format sessions take unchanged code paths. Gates: the golden and compat gates byte-identical, and `recompute --dry-run` 0 byte differences on the capture fixtures |
| New rules `agentdojo.capture_messages_form@1` (+ `capture_thinking_omitted@1`) | a rule catalogue | **Depends on placement (§8 Q5).** In the shared `agentdojo` catalogue, it needs a version bump (D-31: it has kept imports), and the capture header cites `rules.agentdojo` at the shipped version, so every AgentDojo-family AER header changes: a byte change for all those corpora, free only if it lands before the round. In a **new small catalogue cited only by Anthropic sessions**, there is no byte change anywhere |
| `content_block_parts` withheld branch (§3.4) | TraceLogger and capture mappers | 1, with no byte change for stored corpora (no stored dump holds an empty-text thinking block with a signature; to be verified by a scan before landing) |
| SEM | agentdojo semantics | none expected: model calls and tool events are format-agnostic |
| PROV | `agentprov-prov/0.1` | none: same AER record kinds; withheld parts already have PROV rules |

## 4. The LLM element, the endpoint and the headers (class 0)

### 4.1 `native` under provider `anthropic`: the stock `AnthropicLLM`, unchanged

`build_llm` for `agent.provider == "anthropic"` builds:

```
AsyncAnthropic(api_key=<from api_key_env>, base_url=<registry or validated custom>,
               http_client=anthropic.DefaultAsyncHttpxClient(transport=AsyncRecordingTransport(inner, recorder)))
AnthropicLLM(client, model, temperature=<configured>, max_tokens=<configured>, thinking_budget_tokens=<configured>)
```

* Only the constructor's own parameters are used. Nothing is patched.
* **Temperature.** On the current models (Opus 4.7 and later, Sonnet 5.x, Haiku 5.5, Fable), sampling parameters are
  removed or must stay at their defaults (a 400 otherwise, *to confirm per model by the preflight*). The stock default
  `0.0` would therefore be refused. Proposal: for provider `anthropic`, `temperature` defaults to **null**
  (not transmitted), and that is declared with the existing `agentdojo.temperature_not_transmitted@1` item. A plan may
  still set a value; the preflight then shows whether the model accepts it.
* **`max_tokens`**: §8 Q3. The stock 1024 is too small for models whose adaptive thinking cannot be turned off
  (Opus 5.5, Fable, Sonnet 5.5). Thinking counts against `max_tokens`, and the stock element drops tool calls unless
  `stop_reason == "tool_use"`, so a low cap silently changes agent behaviour.
* **`thinking_budget_tokens`** is legacy only (`budget_tokens` is a 400 on current models). It is refused by
  `check_agent` for models that reject it, *to confirm against the model list*, rather than allowed to fail per call.
* **No server-side refusal fallbacks**, deliberately. A fallback would answer with a different model mid-run and
  contaminate the model under test. Refusals are recorded as `finish_reason: "refusal"`.
* The SDK's own credential sources (`ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_PROFILE`, `~/.config/anthropic`, the
  workload-identity variables) never reach the worker. The worker environment is the explicit G.6.3 set with a
  redirected `HOME`, plus only the registry key variable. A test asserts that the wire request carries `x-api-key` and
  no `authorization` header, and `build_llm` refuses if any of those variables is present.
* **Instrumentation items:** `agentdojo.recording_transport@1` with params
  `{sdk: "anthropic", sdk_version, http_module: "httpx2", mode: "async"}` (a new item id only if D.10.7 wants one per
  mode), `agentdojo.http_backoff@1` `{policy: "stock_sdk"}` with the detail "SDK max_retries=2 + agentdojo tenacity 3
  attempts", and `agentdojo.temperature_not_transmitted@1` when applicable. The identity records
  `sdk {name: "anthropic", version}`.
* **Preflight (D.10.9).** `roles_verdict` learns the Messages reply: `tool_use` `get_probe_value` with
  `input.key == PROBE_KEY` means accepted; an `error` event or object means refused. The `not_transmitted` keys add
  `max_tokens`, `thinking` and `output_config`.

### 4.2 Optional opt-in element for effort and thinking display (§8 Q2)

The stock element cannot set `output_config.effort` or `thinking.display`. Effort matters for research on current
models (defaults: Opus 5.5 `medium`, Sonnet 5.5 `high`, Haiku 5.5 `medium`). If wanted, `llm_element =
"messages_compat"` would be a port of `AnthropicLLM.query` that adds exactly `output_config: {effort}` and
`thinking: {type: "adaptive", display}`. Everything else would stay the stock code path: conversion, merging, the
tool-name filter, tenacity and streaming. It would be declared as a `request_modifying` item
`agentdojo.anthropic_output_config@1`, so NC-LIVE-01 applies, as with `gateway_compat`. Without this element, the
effort in force is the model's default. It is not transmitted and is recorded as such: the AER does not claim a value.

### 4.3 Endpoint registry and header allowlist

New `endpoints.toml` entry (capture data; class 0). Model ids are the bare API ids that the GUI price table uses under
provider `anthropic` (`claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`, `claude-fable-5-1`, …; no date
suffixes):

```toml
[endpoints.anthropic]
base_url = "https://api.anthropic.com"     # the SDK appends /v1/messages
base_url_env = "ANTHROPIC_BASE_URL"
api_key_env = "ANTHROPIC_API_KEY"
model_env = "ANTHROPIC_MODEL"
local = false
api = "anthropic_messages"                  # new optional key; default "openai_chat"
request_headers = ["anthropic-beta", "anthropic-version"]
response_headers = ["request-id", "retry-after", "x-should-retry"]
```

* `api` is the only new registry key (`endpoints._ENTRY_KEYS`). The CLI sets `agent.provider` from it
  (`anthropic_messages` → `"anthropic"`, else `"openai_compatible"`). No `AgentConfig` field is added, so the
  `config_sha256` of existing configurations does not change. `AgentConfig.from_json` accepts `provider: "anthropic"`.
* `--env-stdin` accepts the three new variable names automatically (it reads the registry).
  `secrets_from_environ` already excludes `*_BASE_URL` and `*_MODEL`, and scans `ANTHROPIC_API_KEY`.
* **Redaction:** `x-api-key` is on the hard denylist. The literal key value is scanned everywhere (fail-closed), and
  `sk-ant-…` keys already match the `openai_sk` pattern (`\bsk-[A-Za-z0-9][A-Za-z0-9_-]{15,}`). A test pins this.
  `anthropic-organization-id` (an account identifier) and `anthropic-ratelimit-*` keep their names only. The
  allowlist adds just the version and beta headers, the request id and the two retry headers that explain SDK retries.

## 5. Dependencies

* No new package in core. The import-boundary test (`tests/boundary/test_import_boundary.py`) adds `anthropic` and
  `httpx2` to `BENCHMARK_PACKAGES`.
* The backend environments already hold `anthropic` 1.11.0, so there is **no download for them**.
* `backends/shared` has its own lock (`openai`, `httpx`). Two options (§8 Q7):
  (a) add `anthropic` to its dependencies and re-lock with the same `exclude-newer`. The shared environment then needs
  `anthropic` and its few dependencies, probably served from the local uv cache with `--offline`, but that is still a
  sync that needs your yes;
  (b) keep it out of shared's dependencies, import it lazily (as `gateway.py` does for AgentDojo classes), and run the
  Anthropic element tests only in the `backends/agentdojo` and `backends/autodojo` environments.
  I recommend (b): no download at all.
* No stdlib HTTP client is written (§0).

## 6. Tests (all scripted; no network, no key)

**ScriptedTransport, Messages mode** (`agentprov_backend.testing`): `MessagesReply.text|tool_use|thinking|refusal|
max_tokens`, `MessagesFail.http(n)` (Anthropic error JSON; 429 with `retry-after`, 529 overloaded), `stream_error`,
`truncated_stream`, `connection`. It is rendered as SSE when the request asks to stream, else as JSON, with
deterministic ids (`msg_scripted_<n>`, `toolu_scripted_<n>_<i>`) and usage. The script JSON form is
`{"api": "anthropic_messages", "steps": [...]}`. It is synthetic and written by me, with no captured API bytes. The
`httpx2.MockTransport` serves both sync and async clients, so the stock async element runs on its normal code path.

| Layer | Tests |
|---|---|
| `backends/shared` | SSE fact extraction (usage merge, stop reason, id, model, `error` event → `stream_error`, truncated stream, `ping`, unknown events kept); async recording transport (every exchange recorded, SDK retries recorded with `retry_of`, a raising observer stops the send); format-aware `input_at`; `transmitted` excludes `system`; header note (allowlist, denylist wins, `x-api-key` never kept, no `authorization`); credential-variable guard |
| `backends/agentdojo` (K.8.1 rows under provider `anthropic`) | one benign cell per v1.2.2 suite with the stock `AnthropicLLM`; an injection cell (payload fidelity SEC-14: wire, capture, native, AER); the 3-pass silent re-run; 429/529/5xx retried, 400 not retried; stream error mid-reply; refusal; `max_tokens` with a partial `tool_use` (stock drops the calls; core reports them unexecuted); thinking blocks echoed with their signature on the next request (`expect` predicate); invalid tool name filtered; `max_iters` cut; the preflight roles verdict |
| core | `ingest/sse.py` unit, property and fuzz tests (bounds, strict JSON, CRLF/LF, multi-line `data`); a frozen synthetic Anthropic session under `tests/fixtures/capture/` → golden AER, byte-exact, and re-mapping gives the same bytes; SEM and PROV derive; accounting `consistent`; context membership `O`; the K.9.1 live-versus-native differential on it; every existing golden and the compat gate unchanged; `recompute --dry-run` 0 differences |
| boundary | the core never imports `anthropic`, `httpx2`, `openai` or `agentdojo` |

Load rule: one pytest at a time, `-n 2` at most; full suites only through `tools/suite_queue.py`.

## 7. Work plan and branches

1. **Harness, class 0** (`backends/shared`, `capture/` endpoint data, `cli/run.py`, backend tests): this branch,
   committed in units. It is usable on its own for scripted runs. The resulting AER is degraded but honest without
   part 2 (`input` ambiguous, issues), so it should not be used for kept runs before part 2.
2. **Core, class 1** (`messages_wire.py`, `ingest/sse.py`, mapper dispatch, rules, fixtures and goldens): on a held
   branch `anthropic-endpoint-core`. The orchestrator decides whether it lands before or after the regeneration round.
   I never merge it.
3. Records: DECISIONS D-656 (+ ids reserved with `tools/reserve_id.py` for separately decided parts), the spec
   (C.13.10 resolutions, D.10.5/D.10.7/D.10.9, G.6.4/G.9.2, K.8.1 rows, N.2.1), and the AGENTS.md session line.
   Spec items are reserved before they are written.

## 8. Decisions needed (for the orchestrator to take to the user)

* **Q1. capture/0.2?** Recommendation: **no**. capture/0.1 holds the exchange faithfully (§2). The only losses are
  stream chunk timing and the usage members outside the closed set, and both stay in, or are irrelevant to, the
  evidence.
* **Q2. Elements.** (a) The stock `AnthropicLLM` as `native` only, with the model's default effort. Or (b) also the
  opt-in `messages_compat` element for effort and thinking display, declared `request_modifying`. Recommendation:
  build (a) now, and (b) if effort control matters for the planned Claude runs.
* **Q3. `max_tokens` for provider `anthropic`.** The stock default is 1024. Recommendation: no hidden default; the plan
  or CLI must state it, and the GUI suggests 16,000. Alternative: default 16,000, declared as a `harness_policy` item.
* **Q4. Empty thinking under display `omitted`.** Recommendation: withhold the part text under `aer/0.2` with a D rule
  (§3.4). Alternative: keep `""` as recorded, with an issue. This decides whether the core part waits for part C
  (`aer/0.2`).
* **Q5. Rule placement.** Recommendation: a new small catalogue (for example `agentdojo_messages`) cited only by
  Anthropic sessions, with no byte change anywhere. Alternative: the shared `agentdojo` catalogue, which needs a bump
  and moves every AgentDojo-family header; that is acceptable only if the core part lands before the round.
* **Q6. One capped real probe** (needs your typed yes in my window): `agentprov run --preflight-only --model anthropic
  --model-id claude-haiku-5-5`, at most 3 calls, under $0.01, to confirm R-1 (event-loop pool reuse), the SDK's exact
  serialisation of AgentDojo's blocks, and the current-model 400s on `temperature`. Without it, the design rests on
  scripted tests and documentation.
* **Q7. Shared-environment dependency.** (b) lazy import, with Anthropic tests in the backend environments and no
  download (recommended), or (a) add `anthropic` to `backends/shared` and sync it, which needs your yes.

## 9. Downstream effects (CLAUDE.md rule 10)

* **AER digests:** the aer stage code digest moves (class 1); stored AER bytes are unchanged, given Q5 as recommended.
* **PROV output:** unchanged. **Compat gate:** unchanged (`prov/compat` untouched).
* **Corpus manifests:** none for stored corpora. New live corpora record `provider: anthropic` and the SDK identity.
* **Manuscript numbers:** none (no stored data changes).
* **GUI:** it can switch Claude from `openrouter` to `anthropic` once part 1 lands. Its cost estimate must treat
  Anthropic `input_tokens` as uncached input, with cache reads and writes priced separately (§3.5).

## Addendum (2026-10-22): decisions and findings after the note

* **User decisions.** Q1-Q7 as recommended ("approve all decisions", in the D-656 window). Q3 amended through the
  orchestrator: both modes, in the CLI and the GUI (`--max-tokens N`, or `--max-tokens harness-default` = 16000
  declared as `agentdojo.anthropic_max_tokens@1`; neither is refused). Q5 and Q7 were taken by the orchestrator as
  recommended.
* **The stock element cannot send on the locked SDK.** `anthropic` 1.11.0 has no `temperature`, `top_p` or `top_k`
  on `messages.create`/`stream`, and AgentDojo's `chat_completion_request` always passes `temperature=`, so it
  raises `TypeError` before any request. The user chose a **declared port** (`agentprov_backend._anthropic_llm`,
  item `agentdojo.anthropic_element_port@1`, `behaviour_preserving`) over pinning `anthropic<1`: `temperature` goes
  through `extra_body` when set; `query` and the request function equal the stock source by AST except that keyword.
  §4.1's "stock `AnthropicLLM`, unchanged" therefore reads "the declared port".
* **No silent re-run on this path.** AgentDojo re-runs a pass only when the final content is `None`; the Anthropic
  element returns a list (possibly empty), so the 3-pass re-run of the OpenAI path does not occur.
* **Guarded sources.** The port's stock dependencies join D.10.6 on the separate branch `anthropic-endpoint-guarded`,
  merged in the env rebuild window; an env built under another guarded list is refused with a rebuild instruction.
  The live profile's `guarded_sources` and `instrumentation_accepted` entries are class 1 and go with the core part.
* **Probe (Q6).** It needs a registered env built from a checkout with this branch, so it runs after the rebuild,
  with the user's typed yes.

## Real-API confirmation (Q6 probe, 2026-10-22)

The capped preflight probe the user approved in the D-656 window ran once:
`agentprov run agentdojo --preflight-only --model anthropic --model-id claude-haiku-5-5 --max-tokens 1024 --containment sandbox-exec --env-file <repo>/.env --i-consent-to-api-costs`.

- **Where:** a local branch at `live-pilot-core` `f23074f3` (main `f24ee223` plus the live gates pilot's B1–B4; on main
  itself the run exits 5 because `agentdojo · live` was `planned`, and that gate was not bypassed). The registered
  env `agentdojo-79922295` was rebuilt from main with this harness; its sandbox probe passed under profile
  `34018a40…`.
- **Result:** exit 0 in 4.6 s. `reachable=True`, `roles=accepted (instruction_followed)`, `http_status=200`,
  `tool_calls=structured`, `not_transmitted=none`, model `claude-haiku-5-5` at `https://api.anthropic.com`.
- **What it confirms:** the real API accepts the request the declared port builds (streaming, `max_tokens` 1024, no
  temperature); the event stream is read; the model follows the system message through a `tool_use` block; every
  configured parameter is transmitted.
- **What it leaves open:** by design the CLI removes a probe session after the T0 secret scan, which passed (D.10.9),
  so no wire or AER evidence and no token count remain. Risk R-1 (connection-pool reuse across `asyncio.run` loops)
  needs two calls on one client and is not exercised by a one-call probe. The live pilot's Part B campaign (4 banking
  cells on claude-haiku-5-5) provides that evidence; its AER and wire are checked against D-656 when it exists.
