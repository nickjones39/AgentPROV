# Phase 10m: two wire-log and MCP-trace families (census and proposals)

Branch `phase-10m-readers`, 2026-10-13. Ranks 9 and 7 of the phase-10e ranking (D-145): part A is Zenodo 21944598
(Bedrock Converse wire logs), part B is Hugging Face `lihaonan0716/mcphunt-agent-traces` (waits for the ingest-formats
merge, D-242). Decisions D-280–D-289 are **proposals for the user**. Census data:
[`zenodo-21944598.census.json`](zenodo-21944598.census.json) (counts only: no prompt, payload, output or address is
quoted). Scripts and intermediate output: `~/.agentprov/migration-work/phase10m/` (outside Git). Everything in the deposit
is untrusted data: it was read in memory through `agentprov.ingest` and never run, installed, extracted or followed.

**Status: part A done** (census, D-280–D-285 decided on the user's delegation 2026-10-13 with the recommended options,
the D-281 addendum, the `wirelog` family, spec §D.20, scratch trial imports; §A.7, §A.8). Part B: census done, D-286–D-289
user-approved 2026-10-13 (the recommended options); the `mcphunt` family is built (spec §D.21; §B.7). The routed needs
have landed and are used (2026-10-15, §B.6): one execution per streamed trace and the 64 MiB limit in `[import] limits`
(D-323), the canary-flagged issue rule (D-311), and tool results over 1 MiB carved by the trace's byte range (RB-3,
D-218). Imports wait for the regeneration round and the user's approval.

## Part A: Zenodo 21944598, "What surrounds an injection decides whether it works"

### A.1 Source and acquisition

| | |
|---|---|
| Record | 21944598 (concept 21944597), version `1.0.0`, published 2026-08-15; the only version in the concept |
| File | `prompt-injection-study.zip`, 6,354,708 B |
| md5 | `a5ce4a134c610e493e95096abb69f8b3` (equals the record's checksum) |
| sha256 | `08e60afd5ba0c0c044afd005c015cbc539428255240f1ea2a555feb800079454` |
| How obtained | the phase-10e download (user-approved 2026-10-12, logged in phase 10e's `calls.jsonl`), copied locally into `~/.agentprov/staging/10m/zenodo_21944598/`; no network in this phase |
| Licence | record `cc-by-4.0`; `LICENSE-DATA`: CC-BY-4.0 for `runs_named/`, `results.csv`, `attacks.json` and `PAPER.md`; code MIT (`LICENSE`) |

The local copy is logged in `~/.agentprov/cache/acquisitions.jsonl` as a no-retrieval row.

### A.2 How the archive was read

`ingest.archives.open_zip` (release `False`, default limits) and `iter_zip_members`: 10,744 members, all `selected` by the
member gate, 0 rejected, 0 findings. JSON through `strict_json_loads` (0 errors). The deposit's Python files were read as
text to learn the record layout; none was run.

### A.3 Census

**Members.** 22 top-level files (paper, README, CITATION, licences, `attacks.json`, `results.csv`, the harness
`run_channels.py`, `run_trials.py`, six `driver_*.py`, scoring scripts, `credentials.py`, `.env.example`) and 10,722
members under `runs_named/<model>__<arm>__<NNNN>/`.

**Runs.** 1,334 run directories, equal to the card. Run numbers 1–1,334 are contiguous and unique, and `meta.run_id`
equals the directory name in 1,334/1,334. Two producer generations:

| Batch | Runs | `meta.json` keys | Files |
|---|---|---|---|
| first batch (`run_trials.py`, five "variants" of a poisoned ticket: `clean`, `soft`, `imperative`, `urgent_authority`, `operator_spoof`) | 358 | `run, run_id, source_dir, model, variant, task_prompt, timestamp` (+ tokens in 204) | 154 have no `final_user_text.txt`/`final_reasoning.txt`; 358 have `outcome_v2.txt` (reclassification) |
| named attacks (`run_channels.py` and the drivers: MCPTox P1/P2/P3 and their channel and system-prompt arms) | 976 | `run_id, model, attack, channel, paradigm, source_quote, …, fired_attacker, timestamp, tokens` | 8 files |

Seven models (Bedrock ids as recorded): `us.anthropic.claude-sonnet-4-6` 420, `us.anthropic.claude-haiku-4-5-20251001-v1:0`
299, `amazon.nova-micro-v1:0` 141, `qwen.qwen3-32b-v1:0` 141, `mistral.ministral-3-8b-instruct` 111, `amazon.nova-lite-v1:0`
111, `amazon.nova-pro-v1:0` 111.

**Wire shape.** `request.json` is the list of request bodies the harness sent, in order (`{"model": …, **payload}`: the
`model` key is the harness's addition, the URL carries it on the wire); `response_raw.json` is the list of decoded
responses. Requests and responses pair by position (1,334/1,334 equal lengths: 79 runs with 1 call, 662 with 2, 584 with
3, 9 with 4; 3,191 model calls). Converse requests carry `messages`, `toolConfig`, `inferenceConfig {maxTokens: 1024}` and,
in 778, `system`; responses carry `output.message`, `stopReason`, `usage` and `metrics.latencyMs`. **Every later request
repeats the earlier one's messages, then the previous response's message, then one user message** (1,857/1,857 by JCS
equality), so each request's context is recorded in full. `stopReason` is `tool_use` 1,857 and `end_turn` 1,334; every run
ends with `end_turn` (no call is left without a result). The `toolConfig` is identical across a run's requests (3,191);
the system prompt likewise. No reasoning blocks; the longest string literal is 2,863 B; the JSON was written with CRLF line
ends (Windows), which is whitespace only.

**One run in another wire format.** Run 0001 (`claude-sonnet-4-6__soft__0001`, first batch) holds Anthropic Messages
bodies (`max_tokens`, `tools[].input_schema`, string user content; responses with `id`, `model`, `stop_reason`,
`content[]` blocks `text`/`tool_use`). Its one call pairs by `tool_use.id` = `tool_result.tool_use_id`, its prefix property
holds, and its dispatcher log matches. No shipped script produces this body (A.3.5).

**Tool calls and pairing.** Two tools are offered (`read_file`, `send_email`), defined inline in `toolConfig` (4 distinct
tool configurations). There is **no MCP server**: the paper's framing is MCP tool poisoning (MCPTox paradigms), but the
tools are Converse `toolSpec`s with no server identity, so the multi-server question does not arise. 2,001 calls;
responses hold 0 (1,333), 1 (1,715), 2 (138) or 3 (3) calls, and 5 responses repeat a tool name. **Pairing by
`toolUseId`:** every call's id occurs on exactly one `toolResult` in the next request (2,001/2,001), ids are unique,
and the result order also equals the call order (1,857/1,857), which is never used as evidence. A response's results come
back as **one user message with one `toolResult` block per call** (1,715 one-block, 138 two-block, 3 three-block messages).
Results: `read_file` document text 1,245, the literal `Email sent.` 756; the harness's `[no such file: …]` and
`Unknown tool.` branches never occur. `tools_called.txt` (the dispatcher's own log, one line `name {sorted JSON input}`
per call, CRLF) equals the logged calls in 1,334/1,334 runs.

**Synthetic tools (recorded as observed, never as real tool behaviour).** By the deposit's README and harness code,
`read_file` returns a fixed string from the harness's own table (the poisoned ticket of the arm), whatever path is asked
(first batch) or by base name (named attacks), and `send_email` sends nothing and returns `Email sent.`. The data agree
(every result is one of those). No tool touched a file system or a mail server.

**Joins.**
- `results.csv` (12 columns: `run_id, model, arm, paradigm, channel, context_condition, hijack, exfiltration, silent,
  call_order, input_tokens, output_tokens`): 1,334 rows, every run joins by `run_id`; model 1,334 and arm 1,334 agree
  with `meta.json`, channel 976/976 where `meta` has one. `hijack` equals "a logged `send_email` call whose `to` holds the
  attacker address" in 1,334/1,334 (recomputable, D). Token cells are empty for the 154 earliest runs (the README says
  so; the counts are in `response_raw.json`), and otherwise equal the usage sums (1,180/1,180), as do `meta`'s.
- `attacks.json` (payloads "as used"): for the named attacks, the retargeted payload is found verbatim where the channel
  says: in the `toolConfig` for `tool_description` (586) and `param_description` (60), and in a tool result for
  `tool_result` (329; 1 run never called `read_file`, so the payload was not delivered). The first batch's five ticket
  variants are **not** in `attacks.json`; they exist only as constants in `run_trials.py` and as the observed results.
- `meta.fired_attacker` equals the recomputed attacker send in 976/976.

**Time.** The only clock value is `meta.timestamp` (1,334; ISO 8601 with microseconds and `+00:00`), written by the
harness's `save()` after the run (`datetime.now(timezone.utc)`), non-decreasing by run number (1,334). No request,
response or tool call has a time; `metrics.latencyMs` (3,189) is a provider duration without a stated clock.

**Identity.** `meta.model` equals every request's `model` (3,191/3,191). Converse responses name no served model; run
0001's response does (`model`). The `us.` prefix is a cross-region inference profile; the region is an environment
variable that is not recorded. No code commit, harness version or request id is logged (run 0001 has a response `id`).

**Secrets and personal data.** 0 secret-like strings in all 10,744 members (AWS access-key ids, secret-key assignments,
ARNs with account ids, 12-digit numbers, session or bearer tokens, `sk-` keys); `credentials.py` reads a credential from
outside the tree and `.env.example` holds no key. 0 workstation account paths (the 916 `/home/` hits are the MCPTox quote
`/home/.ssh/…` inside `meta.source_quote`). Five distinct e-mail addresses, all reserved or fictional (`.example`,
`example.com`, an MCPTox quote, one model-invented address); the ticket's customer is invented (README §Ethics). **No
withholding policy is needed** (D-234 not triggered).

#### A.3.5 Code identity: the shipped scripts are documentary, not verified producers

The deposit holds the harness (`run_channels.py`, `run_trials.py`, drivers) without a commit, and three observations
show that the data were not all produced by these files as shipped:
1. `run_trials.py` writes `runs/run_NNNN/` with `meta.run_id` = `run_NNNN`; the deposit has `runs_named/<model>__<variant>__<NNNN>/`
   with `run_id` equal to the new name and a `source_dir` key the script never writes. The 358 first-batch `meta.json`
   files were rewritten after the runs (`source_dir` = `run_<meta.run>` in 358/358).
2. The shipped `run_trials.py` writes `final_user_text.txt` and `final_reasoning.txt`; 154 first-batch runs lack both, so
   they came from an earlier version of the script.
3. No shipped script sends the Anthropic Messages body of run 0001.

So, as for AgentOps-Bench (D-193), every rule about harness behaviour is class I, citing the deposit's script paths as
documentary evidence; D rules are kept for deterministic checks over the logged bytes (id equality, request echo, usage
sums, the hijack recomputation).

### A.4 Proposed AER mapping (D-281; for review)

One AER per run directory. Primary artefact `request.json` (`a0`, native); `response_raw.json` (`a1`), `meta.json`
(`a2`), `tools_called.txt` (`a3`) and the outcome and final-text files as supporting siblings; the `results.csv` row and
the `attacks.json` entry as joined context artefacts.

| Source | AER | Evidence and rule |
|---|---|---|
| header | `task {benchmark: "what-surrounds", task_id, environment, attack_id}`: `task_id` from a profile table of the 3 task prompts (D, exact text match); `environment` = `context_condition` (csv); `attack_id` = arm (`null` for `clean`); `defense_id` `null` | arm and condition O (csv, meta); task id D |
| `meta.model` = request `model` | actor `agent` (`llm_agent`), `model.requested` | O (harness record), equality D; provider `aws-bedrock` I (code: the runtime URL); served `not_recorded` (run 0001: `served_model` per call, O) |
| harness, deposit | actors `bench` (`what-surrounds`, version `1.0.0` from the record, code `not_recorded`), `harness`, `user` (`simulated_user`), `env` (`tool_runtime`, the harness's synthetic dispatcher, `ext.wirelog.synthetic: true`), `att` (attack arms), `judge` (the deposit's scoring) | I (`*_unverified@1`, documentary paths) |
| request `system` | one message role `system`, actor `harness`, before the user task | content O; actor I |
| `toolConfig` | fixture `tool_definitions` (content O); every `mc.tools` = it | O per request; identity across requests D (`wirelog.tool_config_stable@1`) |
| first user message | `m` role `user`, actor `user`, text part | content O; actor I |
| request *i* / response *i* | `mc<i>` (`role: agent`, scope `att0`), `input` = the message ids of request *i* in recorded order, `params.transmitted` = `inferenceConfig`, `finish_reason` = `stopReason`, `usage`, `latencyMs` to `ext` (`/t/dur_s` `ambiguous`), `request`/`response` blobs `unk not_captured` (re-serialised JSON, not the wire bytes), `t` `not_recorded`; status `kept` | input O (the request records it); id resolution D (`wirelog.request_prefix@1`: each item equals one earlier record by JCS); status D where the response is echoed in the next request, I for the last |
| response *i* `output.message` | `m` role `assistant`, actor `agent`, `generated_by: mc<i>`, parts in block order (`text`, `tool_call {name, args, provider_call_id: toolUseId}`) | O (provider), `src` in `a1`; its echo in request *i+1* checked equal (D) |
| each `toolUse` | `te<k>`: actor `env`, `call` = the part, `name`, `args`, status `not_recorded`, `t` `not_recorded` | existence O (dispatcher log line, matched by content, D); `call` D (`wirelog.call_id_unique_match@1`) |
| each `toolResult` block | **one message per block**: `m` role `user` (verbatim), actor `env`, `generated_by: te<k>`, `tool_result {responds_to, text}`; `ext.wirelog.wire_message {request, index, block}` keeps the grouping | content O; links D (id); the split D (`wirelog.result_block_message@1`) |
| `meta.timestamp` | run scope `t.raw.end` (O), typed end `ambiguous` | `wirelog.save_timestamp_unverified@1` (I by code; D-197 pattern) |
| `results.csv` row | judgements `hijack`, `exfiltration`, `silent`, `call_order` (`by: benchmark`, values O, origin `checker` I); `hijack` also recomputed (`wirelog.hijack_recomputed@1`, D, 1,334/1,334) | csv O; origin I |
| `outcome.txt`, `outcome_v2.txt` | judgements `outcome`, `outcome_v2` (verbatim labels, origin `harness_rule` I) | O |
| `attacks.json` entry (named attacks) | fixture `injection_payload` (actor `att`), content verbatim; `ext` offset where it is found in the toolConfig or result | content O (deposit data); join D (attack name); "as used" I |
| first-batch variants | no payload fixture (the text is not data); the observed result is the evidence; SEM marks it from a profile table of the 5 variant results' sha256 | D (digest) |
| `meta` extras | `sent_recipients`, `fired_attacker`, `disclosed_send`, `silent`, `source_quote`, `paradigm`, `source_dir` to `ext`; checks `wirelog.acc.fired_attacker@1`, `wirelog.acc.tokens@1` | D |

Order: every edge is causal and evidenced by ids or by the request echo (D); no position-only or time edge. Accounting:
`aer.acc.agent_calls_vs_assistant@1` is checkable (calls observed). Expected issues: `wirelog.payload_not_delivered` (1),
`wirelog.final_texts_not_logged` (154), info `wirelog.meta_rewritten` (358).

### A.5 Proposed decisions (D-280–D-285)

- **D-280: family and dialect.** A new family `wirelog` (`adapters/wirelog/`, namespace `wirelog`) for logs of successive
  full-context LLM API requests and responses; dialect `wirelog.request_response` with variant `bedrock-converse` (1,333
  runs), mapper `wirelog.run_dir`. The study-specific files (`meta.json`, `tools_called.txt`, `results.csv`,
  `attacks.json`) are read under the profile `what-surrounds` (part `runs-named`), so the reader stays reusable for a
  later wire-log source. *Alternative:* a source-specific family (`whatsurrounds`): simpler names, no reuse.
- **D-281: the mapping of §A.4**, in particular: (a) a request's context is **observed** (O), because the harness logged
  the body it sent, and resolving its items to earlier records is D by JCS equality; (b) calls and results pair by
  `toolUseId` (D), never by order; (c) a multi-result user message becomes one AER message per `toolResult` block (a
  message has one generator, C.3.4), with the wire grouping kept in `ext` (141 messages); (d) the system prompt is a
  `system` message (it is an input of every call), the tool configuration a `tool_definitions` fixture.
  *Alternatives for (c):* one message with N parts and only the first generator (loses N−1 links); a harness decision
  generating the message (wrong: the tools did run).
- **D-282: code identity.** The shipped scripts are documentary, not verified producers (A.3.5): harness-behaviour rules
  are class I directly (as D-193), D rules only over logged bytes.
- **D-283: run 0001.** Map it with a second variant `anthropic-messages` of the same dialect (same AER shape; its
  `tool_use.id` pairing is D; served model and response id O). *Alternative:* exclude it as `select.dialect_planned` (the
  paper counts it; the corpus would hold 1,333).
- **D-284: synthetic tools.** The tool runtime is recorded as the harness's synthetic dispatcher (`env`, `ext.wirelog.synthetic`,
  I by README and code); the profile quirk and the datasheet say that `read_file` returns harness text and `send_email`
  sends nothing. SEM: `read_file` output `untrusted`, `send_email` a sink with no external effect. The data never say
  that a real file was read or a mail sent.
- **D-285: scope and counts.** All 1,334 runs are in scope as `agent_execution` (79 runs where the model called no tool are
  still executions with tools offered); the 22 top-level files are `select.not_execution_artefact` except `results.csv` and
  `attacks.json` (context artefacts). No withholding policy. One corpus `what-surrounds` (CC-BY-4.0; D-144).

### A.6 Invariant 5 and routing

No change to `aer/`, `prov/`, `validate/` or `corpus/` is foreseen. Runner questions to check in part B (not changes yet):
whether an archive input's sibling members can be a unit's auxiliary artefacts (the DTap pattern `auxiliary_for` over a
listing of selected members), and whether top-level `results.csv`/`attacks.json` can be context artefacts of the same
archive input. If not, they are routed to the orchestrator (the deferrals session owns the runner).

### A.7 Part A implementation: the `wirelog` family (spec §D.20)

Built as §A.4 proposed, with these differences in form (meaning unchanged):

| §A.4 proposal | Implemented as | Why |
|---|---|---|
| primary artefact `request.json` | primary `response_raw.json`, request log an auxiliary (D-281 addendum) | the first scratch import collapsed 71 runs: request logs repeat byte for byte across trials (1,263 distinct in 1,334); response logs are distinct (1,334) and never rewritten |
| top-level files `select.not_execution_artefact` | outside the include globs: `not_selected` members, never decompressed (`wirelog.non_run_member@1`, reserved) | an exclude entry registers only selected members; selecting code to exclude it would decompress it |
| `task.environment` = `context_condition` | `none` is `unk not_applicable` (kept verbatim in `ext.wirelog.results_row`) | `none` is a sentinel value (C.7.3) |
| first-batch payloads by a profile table | `code_only_payload_arms`: no payload fixture; SEM recognises the four attacked documents by digest (`documents.toml`) | the texts are harness constants, not deposit data |
| — | byte-identical auxiliaries (an unchanged `outcome_v2.txt`, a final text without reasoning) share one raw artefact, `ext.wirelog.same_bytes` | two artefacts with one digest collide in the PROV top level |

In-memory map of every run (D-154 method, `scripts/m1_map_census.py`, 6 workers, 268 s): 1,334/1,334 mapped, 0 crashes,
0 degenerate, 0 AER findings (release mode), 0 SEM findings, PROV tier 4 clean for all, every safety-net finding
classified, 26/26 sampled re-maps byte-identical. Records: 3,191 model calls, 2,001 tool executions, 6,856 messages, 2,310
fixtures (1,334 tool configurations, 976 payloads), 7,028 judgements. Issues: `wirelog.meta_rewritten` 358,
`wirelog.final_texts_not_logged` 154, `wirelog.payload_not_delivered` 1, `accounting_unverifiable` 154 (usage totals
not in the earliest `meta.json`). Checks: dispatcher log, recorded hijack and final text consistent 1,334/1,334; usage
totals consistent 1,180, unverifiable 154 — each equal to the census.

Fixtures: 12 run directories chosen by criterion (`tests/fixtures/wirelog/CRITERIA.json`: the Anthropic run, a clean and
an early attacked first-batch run, a tool-description hijack, multi-result and three-result messages, the parameter arm,
an explicit-distrust system prompt, the user-prefix arm, a run without calls, the undelivered payload, a four-request run)
plus `results.csv` and `attacks.json`, byte-identical; tests `tests/adapters/wirelog/` (49 pass).

### A.8 Scratch trial imports (`~/.agentprov/migration-work/phase10m/trial/`)

The CLI refuses a `planned` source, so `scripts/t1_import.py` runs what `agentprov import --input FILE
--verify-against-pin` runs (offline pin check, `ArchiveTree`, `import_source`, release mode), as phase 10k did.

| Step | Result |
|---|---|
| import, 8 workers | 1,334 seen, 1,334 mapped, annotated, derived and validated, 0 degenerate, 0 failed, 0 duplicates |
| import, 3 workers | identical counters; AER, SEM, PROV, raw, validation, `executions.jsonl` and register byte-identical to 8 workers |
| `verify --level chain` | exit 0: 1,334 executions, 10,724 members, 5,963 raw objects re-hashed; one `unverified` (`checksums.absent`, a working tree) |
| `derive --out` | exit 0: 1,334 identical, 0 unexplained |
| `validate --corpus` | exit 0: 1,334/1,334 pass, tiers 1-4, linkage 1,334/1,334 |
| `recompute --dry-run` | exit 0: 1,334/1,334 identical (re-mapped from the stored zip, all five stages), 0 unexplained |

## Part B: Hugging Face `lihaonan0716/mcphunt-agent-traces`

Census data: [`mcphunt.census.json`](mcphunt.census.json) (counts, classes and field paths only; no canary value, no
fragment or hash of one, is printed or written). **Status: census done; D-286–D-289 user-approved 2026-10-13 (the
recommended options).** Two runner needs are routed before any import (§B.6).

### B.1 Source and acquisition

Revision `c4c69322bf9ed7690f5265577365709dad5dd454`, CC-BY-4.0 (card). All 32 files (593,477,795 B; 15 LFS objects)
downloaded on 2026-10-13 with the user's yes into `~/.agentprov/staging/10m/hf_mcphunt/`; every file verified against
phase 10e's cached tree listing (LFS sha256 = oid, git blob sha1 = oid, sizes equal) and logged in `acquisitions.jsonl`.

### B.2 How the files were read

`agentprov.ingest.jsonstream.open_json_stream(fp, limits, arrays=("/traces",))` (origin/main `ebef6c7`, run from a
read-only export, since this branch predates the merge): 20 trace files, 0 findings. Each file is
`{schema_version, pipeline_git_commit (7 hex), task_taxonomy_version, labeling_rules_version, traces: [...]}` (4
distinct envelopes). **Four traces exceed the 16 MiB element limit** (20.5, 25.6, 25.6 and 46.9 MB; in
`main/deepseek_v4_flash.json`, `main/gpt_5_4.json`, `mitigation/gpt54_m0.json`, `mitigation/minimax_m3_rv1.json`); the
census raised `max_json_element_bytes` to 256 MiB in its own process only. Under the default, each of those four files is
refused whole (the reader fails closed).

### B.3 Census

- **Traces: 6,786**, equal to the card: main 3,615 (5 models × 723), mitigation 2,706 (M0–M3 prompts; GPT-5.4 1,530,
  DeepSeek-V4-Flash 588, MiniMax-M2.7 588), live-guard 387 and browser replication 78 (39 + 39; DeepSeek-V4-Flash,
  `defense` `none` or `taint_tracking`). No trace is byte-identical to another in another split. `trace_id` names a
  task-environment cell, not a trace (723 distinct in main's 3,615): identity is the file and the array index.
- **Per trace:** `task_id`, `task_prompt`, `env_type` (benign, risky_v1–v3, hard_neg_v1–v3), `risk_mechanism` (10),
  `model`, `defense`, `mitigation_level`, `messages`, `events`, `turn_log`, `labeling` (12 risk signals, taint flows,
  outcome), `measurement` (tokens, temperature, max turns, `mcp_versions`, `servers_available`, `tool_set`, retries),
  `env_snapshot` (workspace files, DB table counts, `canary_count`), `final_message`, `duration_s`,
  `collection_timestamp`.
- **Messages** (OpenAI chat shape): `system` then `user` in all 6,786; assistant 80,472; tool 129,175.
- **Calls and events:** tool calls = tool messages = events = 129,175, equal in every trace; call ids unique in every
  trace; every tool message answers a call by `tool_call_id`. Events carry **no call id**: event *i* names call *i*'s tool
  in 129,175/129,175, with equal arguments in 126,783 (2,392 differ: harness-normalised or sanitised arguments). The tool
  message equals the event's `result_full` in 128,096; in 669 the message is a truncated prefix (`result_truncated`), in
  410 it differs.
- **Model calls:** `turn_log` has one entry per model call (finish reason, prompt and completion tokens). In 6,105 traces it
  has one entry more than the assistant messages: the last call's answer is `final_message`, not a message.
- **MCP servers:** each event names its `server` (filesystem, shell, sqlite, git, memory, time, fetch, browser) and tool;
  each trace records the eight server packages' versions (`measurement.mcp_versions`) and the servers and tools offered.
- **Time:** event timestamps are epoch seconds (float), non-decreasing in every trace; `collection_timestamp` (ISO, `Z`)
  and `duration_s` per trace.
- **Defence:** 245 events in the taint-tracking arms carry `sanitized_args` (the guard's rewrite of the arguments).
- **Canaries (planted credentials).** The environments plant fake credentials (labels such as Stripe, AWS, Slack,
  GitHub and deploy tokens, DB, SMTP and payroll passwords, SSNs, AES and JWT secrets, OAuth client secrets). Event flags:
  `canary_in_result` 14,143 events, `canary_in_args` 2,172; **4,595 traces** have a flagged event. Only **1,995 traces**
  contain a recognisable credential shape (Stripe-like 11,589, AWS-like 629, Slack-like 1,954, GitHub-like 14 tokens,
  2 private-key headers); **2,601 flagged traces contain canaries of no recognisable shape** (passwords, SSNs, keys in
  plain hex). The values are synthetic by design, but they are credential-shaped and a release secret scan flags them.

### B.4 Proposed AER mapping (D-287; for review)

One AER per trace (primary = the file, locator `/traces/<i>`).

| Source | AER | Evidence |
|---|---|---|
| `system`, `user`, `assistant`, `tool` messages | messages in order, verbatim roles; actors harness, simulated user, agent, the event's server runtime | content O; actors I |
| `turn_log[k]` | `mc<k>` (`finish_reason`, `usage`; `input` = the messages before assistant *k*) | existence O; input I (`*_context_is_prefix_unverified`) |
| assistant *k* / `final_message` | generated by `mc<k>` (the last call's output is `final_message`) | link I (position) |
| tool call ↔ tool message | `responds_to` by `tool_call_id` | D |
| event *i* | `te<i>` (actor `srv_<server>`, `name`, `args`, `returned` = `result_full`, `status` from `success`/`error`, `t.raw.start` = timestamp, typed start ambiguous), call = call *i* | event O; pairing I, guarded by the tool name (`mcphunt.event_pairs_call_unverified@1`) |
| MCP servers | one `tool_runtime` actor per server used, `code {dist, dist_version}` from `mcp_versions` | versions O; label→package by a profile table I |
| `sanitized_args` | a defence `decision` (`modify`) on the call, `te.args_effective` | O; actor I |
| `env_snapshot`, `task_prompt` | fixtures `environment_seed`, `task_prompt` (check: equals the user message) | O |
| `labeling`, `outcome`, `task_completed`, `completion_checks` | judgements (origin `checker`, I); SEM outcomes | values O |
| canary flags | `ext`; SEM integrity of the flagged results | O |

### B.5 Proposed decisions (D-286–D-289)

- **D-286: family.** A new family `mcphunt` (dialect `mcphunt.traces`, mapper `mcphunt.trace`), one execution per element
  of `/traces`, read only through `open_json_stream` on a seekable handle (RI-4). One corpus `mcphunt`, four parts (`main`,
  `mitigation`, `live-guard`, `browser-replication`); the defence arms are in scope (the brief), disclosed as excluded by
  the paper's 6,321.
- **D-287: the mapping of §B.4**, in particular: tool messages pair with calls by id (D); events pair with calls by
  position, guarded by the name (I); `result_full` is the execution's `returned` value and the (possibly truncated) tool
  message what the model saw; one runtime actor per MCP server.
- **D-288: element limit.** The profile declares `max_json_element_bytes` = 64 MiB for this source (the 4 traces of 20–47
  MB), recorded in `corpus.json`; the alternative (default limit) refuses four whole files (1,977 traces).
- **D-289: canaries and withholding (the decision that matters).** Three options:
  - **(a) a `[withhold]` profile policy (D-234)** of bounded patterns for the recognisable shapes. It misses the 2,601
    traces whose canaries have no shape, and, because a raw object holds up to 723 traces, a hit withholds the whole
    file: in practice all 20 trace files and at least 1,995 executions leave a public release;
  - **(b) include, as DTap (D.16.13, option A):** the credentials are synthetic and already public under CC-BY; disclosed
    in the datasheet; the release secret scan needs a source-level allowlist;
  - **(c) execution-level withholding from the source's own flags** (withhold an execution whose events are canary-flagged,
    4,595, and its derived files, while keeping the raw files private), which needs a rule kind `corpus/withhold.py` does
    not have (routed; core change).
  **Recommended: (c)**, with (a)'s shape patterns as the backstop scan, because it follows the source's own record
  of which traces expose a canary and keeps the 2,191 unflagged traces releasable. If the core change is refused, (a).

### B.7 Part B implementation: the `mcphunt` family (spec §D.21)

Built as §B.4 proposed (D-286–D-289 user-approved; D-289 option (c) with the seal-issue trigger `mcphunt.canary_flagged`,
one issue per flagged trace). Differences in form: the four splits are recorded per execution (`ext.mcphunt.split`,
`task.defense_id`), not as profile parts, because one pin serves them all; an all-zero `usage` of an errored turn is a
placeholder (C.7.3), kept in `ext`; the answer recorded after an errored last call (`final_message`) is kept on the run
scope, not attributed to the call.

**In-memory map of every trace** (D-154 method; `scripts/m2_mcphunt_map.py` on a frozen snapshot of the branch, 4 workers,
9,245 s; the reader's `parse_stream` builds one unit per trace, as the runner will under RB-1; summary
[`mcphunt.map-census.json`](mcphunt.map-census.json)):

| Result | Count |
|---|---|
| traces mapped | 6,785 of 6,786; **1 not representable in `aer/0.1`** (below) |
| AER findings (release mode), SEM findings, PROV tier-4 failures | 0, 0, 0 |
| accounting | 6,785 consistent (`mcphunt.acc.counters@1` and the core checks) |
| issues (traces / occurrences) | `mcphunt.canary_flagged` 4,595 / 4,595; `incomplete_run` 545; `mcphunt.args_unparsed` 429 / 2,392; `mcphunt.result_truncated_in_message` 381 / 668; `mcphunt.result_differs` 42 / 410; `mcphunt.unknown_server` 3 / 11 — each equal to the census (the failed trace holds the 669th truncation) |
| records | 86,562 model calls, 129,148 tool executions, 229,233 messages, 245 guard decisions, 47,495 judgements |
| safety net | every finding classified |

The one failure, `mitigation/minimax_m3_rv1.json` `/traces/106` (the 46.9 MB trace): one record exceeds the 16 MiB AER
line limit (`ingest.jsonl.line_too_long`) because a single tool result is that large. `aer/0.1` cannot move derived
content into a blob (D-203: a mapper-derived blob needs an origin kind only `aer/0.2` designs), routed as RB-3, and the
deferrals session's answer resolves it with D-218 carved blobs (a string of the stored artefact, not derived content):
the mapper carves tool results over 1 MiB once D-323 gives the per-trace job the document's bytes (follow-up).

Fixtures: 11 traces, the smallest qualifying canary-free trace per criterion (484 KiB, within D-360's budget). Tests
`tests/adapters/mcphunt/` (37 pass; 2 strict xfails pinned RB-1 and RB-2 until D-323; since 2026-10-15
`test_streaming_import.py` tests RB-1..RB-3 through the product path instead).

### B.6 Routed needs (orchestrator)

- **RB-1 (runner):** a whole-file dialect may yield one execution per element of a streamed array: the map job opens its
  primary with `JobContext.open_input` (never `read_input`) and the reader yields one located item per element
  (locator `/traces/<i>`, or the C.9.1 byte-range form). Today `map_artefact` reads the primary whole and requires exactly
  one item per file.
- **RB-2 (profiles/ingest):** a profile-declared `max_json_element_bytes` (D-288), or a raised default.
- **Closed 2026-10-15:** RB-1 and RB-2 landed as D-323 (`parse_stream` per item, `[import] limits` up to the calibrated
  64 MiB). The reader now declares `multi_execution`, each item carries its element's byte range, and the profile's
  raise sits in `[import] limits`. RB-3 is done in the family: a string over 1 MiB in an event's `result_full` or a tool
  message's `content` is carved (D-218) with `{"bytes": [start, end], "p": …}` over that trace alone.
  Census (2026-10-15, `mcphunt.big-strings.json`): 15 strings over 1 MiB, all in `events/*/result_full`, in 8 traces of
  7 documents, the largest 43.6 MB; no tool message `content` (the message copy is truncated) and no other field.
- **Regen-batch item 114 (held, branch `phase-10m-lfs-pointer` on the bug pass's `bugpass-regen-mcphunt`):** the
  reader registers a Git LFS pointer (`mcphunt.lfs_pointer`, rule `mcphunt.lfs_pointer@1` in catalogue v2) instead of
  sealing it as a degenerate execution beside its R3 pinned object (found by the phase-10i R3 fix, 2026-10-21). It
  changes the register rows and the execution count of an import from a checkout (one degenerate AER fewer per LFS
  document); no mapped AER changes.
- **Regen-batch item 149 (held, child of item 114 on `bugpass-regen-mcphunt`):** record locators in the C.9.1 byte-range
  form, so documents over `max_json_bytes` (64 MiB) resolve. Found by the real-data trial of 2026-10-21 on the phase-10i
  R3 fix (7 LFS documents, release mode): 2,756 executions mapped per trace, 2,025 written, 8 carved blobs, the 64 MiB
  override recorded; `main/deepseek_v4_flash.json` (105.7 MiB) mapped 723 traces whose AERs all failed validation
  (`aer.locator.dangling`: a document pointer parses the whole document), and `mitigation/minimax_m3_rv1.json` was
  stopped at the 2 GiB map cap while carving its 43.6 MB result (routed to the deferrals session, D-218 owner). Item
  149 changes every MCPHunt AER's locators (no corpus yet).
- **RW-1 (corpus):** a withholding rule that selects executions by a seal issue code (`mcphunt.canary_flagged`, one per
  flagged trace; D-289 option (c), seal-issue trigger, user-approved). **Landed (D-311);** the profile carries the rule.

No change to `aer/`, `prov/` or `validate/` is foreseen.
