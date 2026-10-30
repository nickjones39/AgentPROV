# Phase 10i: AgentOps-Bench census (part A) and the `agentops` family (part B)

Branch `phase-10i-agentops`, 2026-10-12. Rank 8 of the phase-10e ranking (D-145), counted on its in-scope part (D-143).
Decisions D-190–D-199 were **approved by the user on 2026-10-12**, with the core register code `select.out_of_scope`
(`docs/architecture/DECISIONS.md`; implementation notes on D-193, D-196, D-197). Census data:
[`agentops-bench.census.json`](agentops-bench.census.json) (counts only: no task text, payload, output or account name).
Scripts and intermediate output: `~/.agentprov/migration-work/phase10i/` (outside Git). Everything in the deposit is
untrusted data. It was read in memory and never run, installed or followed. Adversarial-condition results carry
injection payloads; none is quoted here.

**Part B is done** (§8, §9): the family `agentops`, spec §D.18. Sections 1–7 are the part-A census and proposals as
reviewed; §4 describes the mapping as proposed, and §8 lists where the implementation had to differ in form.

## 1. Source and acquisition

| | Runs | Tasks and harness code |
|---|---|---|
| Zenodo 19875693 file | `agentops-bench-v1.0-pilot-traces.tar.gz` | `kunwarshivam/agentops-bench-v1.0.zip` |
| Bytes | 14,819,650 | 2,449,857 |
| md5 (= record) | `413c6123d376c3a8f29ad8b7195cd267` | `71ad345da90595fe85456d0a9a1e47f2` |
| sha256 | `e185bfd0…7a85f` | `852a372d…c1fed` |
| How obtained | phase-10e download, cloned locally into `~/.agentprov/staging/10i/` (no network) | downloaded 2026-10-12 with the user's yes in this session |

Both acquisitions are logged in `~/.agentprov/cache/acquisitions.jsonl`. Licence: Apache-2.0 (record and `LICENSE`).
Concept DOI 10.5281/zenodo.19875456. The zip is the GitHub snapshot `kunwarshivam-agentops-bench-9153772` (short commit
only); the later version 19875603 holds code only (phase 10e).

## 2. How the archive was read (and why not through the product reader)

- `ingest` on main defers every top-level gzip stream (`ingest.stream.codec`). Phase 12b's bounded tar reader
  (`OpenedTar`, D-57, branch `phase-12b` at `6d95d6e`, not merged) reads a gzip tar only **inside a zip** (depth ≥ 2), and
  it **rejects this whole archive**, because the archive carries 7,270 pax `x` extended headers (macOS bsdtar: keys
  `mtime`, `LIBARCHIVE.xattr.com.apple.provenance`, `SCHILY.xattr.com.apple.provenance`).
- The census therefore used a **scratch walker** (`scripts/tarwalk.py`, not product code). It sits on 12b's
  `iter_gzip_bounded` (size, ratio and trailer bounds) and checks every header as `OpenedTar` does (checksum, `ustar`
  magic, octal sizes, end blocks). Pax records are parsed as data and never applied to a filesystem. Links are recorded,
  never followed. Nothing was extracted.
- JSON went through `strict_json_loads`, the zip through `ingest.archives.open_zip` (main; 962 members, 0 rejected) and
  the task YAML through `ingest.yamlsafe.safe_load`. Parse errors: 0.
- Routed (D-192): top-level `tar.gz` deposits and pax `x` headers are ingest work for phase 12, in addition to D-156.

## 3. Census

### 3.1 Archive members

| Entries | Count |
|---|---|
| tar entries | 14,540: 14,486 regular, 47 directories, 7 symlinks |
| AppleDouble `._*` (magic `00051607`) | 7,270. They are already strays in the runner (`_is_stray`) |
| run traces `pilot_v1_seeded/<agent_dir>/<provider_model>/<condition>/<domain>_<NNN>_run<k>.json` | 7,202 (47,885,463 B; 1,538–181,353 B each) |
| side files | 8 per-model `*_report.json`, `opus_4_7_part2/_partial_provenance.json`, `_combined/` (analysis CSV, three `.md` rollups, one real report copy and 7 symlinks to the per-model reports) |

### 3.2 The 7,200 runs and the in-scope 3,360

- 8 models × 100 tasks (5 domains × 20: `code`, `data_analysis`, `research`, `safety`, `tool_use`) × 3 conditions
  (`clean`, `noisy`, `adversarial`) × 3 runs = 7,200 unique cells. Every model has 900 cells.
- Opus 4.7 ran in two directories (`opus_4_7` 452 files, `opus_4_7_part2` 450). The 2 extra files are
  `clean/research_011_run1` and `_run2` of part 1. The deposit's own `scripts/merge_opus_parts.py` dropped them as a
  "partial task" and kept part 2's runs, and the merged report agrees (part 2's trace is byte-equal, part 1's differs). So
  there are 7,202 files and 7,200 cells.
- **In scope (D-143): 3,360 = 2,400 (`adversarial`) + 1,440 (`safety`, all conditions) − 480 (`adversarial` ∩ `safety`).**
  By file: 2,400 adversarial + 480 clean-safety + 480 noisy-safety, 420 per model. Out of scope: 3,840 cells, 3,842
  files (adding the 2 superseded part-1 copies, both clean/research).
- Every label agrees with its path: `condition` (7,202/7,202), `run_number` (7,202), `agent_id` with the model directory
  (7,202), and `task_id` = `<domain>/<NNN>` (7,202).

### 3.3 Trace shape (one variant)

Every trace has the same shape. The harness's pydantic models (`schema.py` at 9153772) describe it exactly:

```
{task_id, agent_id, condition, run_number,
 trace: {task_id, agent_id, condition, completed, error, final_output, total_input_tokens, total_output_tokens,
         total_cost_usd, wall_time_seconds,
         steps: [{step_number, llm_input_tokens, llm_output_tokens, reasoning,
                  tool_calls:   [{tool_name, arguments, timestamp}],
                  tool_results: [{tool_name, result, latency_ms, injected_failure, injected_payload}]}]},
 scores: {completion, cost{…, step_breakdown[]}, cost_normalized_accuracy, efficiency{…}, safety{…}}}
```

- **Steps:** 18,889 in 7,040 runs. 162 runs have no step. `step_number` is gapless from 1 (100 %). By code, one step is one
  model call: one response, its usage (`llm_input_tokens`/`llm_output_tokens`), its text (`reasoning`) and its tool-use
  blocks. A step without calls occurs only as the last step (0 elsewhere). 4,625 steps have calls but no text
  (`reasoning: null`).
- **Pairing:** `len(tool_calls) == len(tool_results)` in 18,889/18,889 steps. `tool_calls[i].tool_name ==
  tool_results[i].tool_name` in 14,328/14,328 pairs. There are **no call ids**: the provider's `tool_use_id`/`tool_call_id`
  are used in the conversation but not written to the trace. 1,543 steps hold several calls, and 1,391 of them repeat a
  tool name, so the name alone cannot pair. By code, the adapters run the calls in order and append call *i* and then its
  result (`step.tool_calls.append(call)`, then `step.tool_results.append(await tool_server.handle_call(...))`), so index
  *i* pairs call and result. Two observations support this: array position within a step, and name equality at every
  index. The pairing still rests on code, so it is a rule, not order alone (D-193).
- **Tools:** 10 known tools (query_database, web_search, calculate, run_python, get_weather, write_file,
  get_stock_price, read_file, get_current_time; send_email offered once, never called). 6 calls name an unknown tool: 5
  `example_function_name`, and 1 whose "name" is a 3,327-character JSON search result. The tool server answers both with
  `Error: Unknown tool`. Every call to a known tool is inside the task's `tools_available` whitelist (14,322). The server
  does not enforce the whitelist.
- **Results:** dict 10,627, str 2,806, null 895. 391 results are dispatch errors (`Error: …`): no fixture for a
  `web_search` query (~200; `AGENTOPS_LIVE=0`, so fixture-only replay), path escapes the workdir (157), missing
  arguments (18), and directory errors (5).
- **Injected failures** (`injected_failure`; 2,093; in scope 715): `http_500` 456, `timeout` 453, `empty_response` 442,
  `malformed_json` 404, `rate_limit` 338. By code, the server **fabricates** these results and the tool is **not run**.
  `latency_ms` is a constant (30000, 250, 100, 50, 10), not a measurement.
- **Injected payloads** (`injected_payload`; 2,011 results in 1,373 adversarial runs, all in scope): 15 distinct payloads,
  101–273 characters, 108–160 occurrences each. In 2,011/2,011 cases the result is a string that ends with `"\n\n" +
  payload`: the tool ran, and the server appended the payload (`inject_payload`). `scores.safety.injections_present`
  equals the payload count in every run. 110 payload occurrences contain format characters (zero-width), present in the
  JSON bytes only as `\u` escapes. Payloads occur only in `adversarial`. The 15 catalogue entries are in `injection.py`
  (implicit string concatenation, so they do not match the source text byte for byte).
- **Time:** the only clock values are `tool_calls[].timestamp` (14,328): ISO 8601 with microseconds and `Z`,
  non-decreasing within each of the 5,924 runs that have calls. By code it is the pydantic default `datetime.now(utc)`,
  set when the adapter builds the call record, immediately before `handle_call`. Steps, results and runs carry no time.
  `wall_time_seconds` and `latency_ms` are `time.monotonic()` differences (code). Member mtimes (2026-04-27/28) are
  archive metadata and are never used.
- **Identity:** `agent_id` `<provider>/<model>` or `openrouter/<vendor>/<model>`, written by the adapter (8 values). The
  served model, request parameters and system prompt are not logged. `scores.cost.pricing_model` is the pricing-table
  key (Opus 902 because of the 2 extra files).
- **Run end states:** completed 6,985; API error before or during the loop 186 (181 rate-limit, all qwen3-max; 5
  provider errors); `Loop stuck: stop_reason='refusal'` 25 (Anthropic adapter); timeout 5; max iterations (25 steps,
  neither completed nor error) 1. `final_output` equals the last step's text in 6,985/6,985 runs where it is present.
- **Empty traces:** 162 (in scope 101). The first model call failed (API error); no step and no tool call.
- **Scores:** `completion` combines a deterministic match with an **LLM judge** (`claude-sonnet-4-20250514` in the
  code; the judge's calls are not logged). `safety` is a regex heuristic over the agent's text (compliance, detection
  and exfiltration patterns). `cost` comes from tokens and a price table, `efficiency` from step counts. Per-run files
  are written **before** `reliability` and `recovery` are computed. Those two appear only in the per-model reports,
  whose `results[]` otherwise repeat the per-run files: every report entry's trace equals exactly one run file after
  canonical JSON, and the common scores are equal (the 2 superseded part-1 copies are in no report).
- **Secrets and personal data:** 0 secret-like strings (Anthropic, OpenAI, OpenRouter, Tavily, AWS, GitHub, bearer
  patterns). An operator's workstation account path appears in `run_python` tracebacks in 36 runs (13 in scope); other
  `/Users/` and `/home/` paths occur inside public web-search snippets in 11 runs. Not printed anywhere.

### 3.4 Task definitions (the join)

100 YAML files `tasks/<domain>/<NNN>_<slug>.yaml`. Every `id` equals `<domain>/<NNN>` and every `domain` matches its
directory. Keys: `id, domain, description, difficulty, optimal_steps, tags, tools_available`, plus `expected_output` (96)
and `context` (7). **7,202/7,202 runs join by `task_id` = YAML `id`**, which equals the path facets. The prompt the agent
saw is `description` (+ `"\n\nContext:\n" + context`), built by the adapter (code). The system prompt is a constant in
the code. Neither prompt is logged in the run.

### 3.5 Code identity: why the harness code is not "verified"

The zip holds the code snapshot, but nothing in the traces names a commit, and three things contradict "the traces came
from 9153772":
1. `CHANGELOG.md` 1.0.0 describes a different pilot (`results/pilot_v2/`, 1,080 runs, six agents, 20 tasks). It says that
   pilot was produced **before** the per-cell RNG seeding fix.
2. `scripts/run_pilot_v1_seeded.sh` would write to directories named after the agent alias (`claude-opus-4-7`, …), but
   the deposit has `opus_4_7`, `gpt55`, `deepseek_v32`, … directories.
3. The Opus runs were merged after the fact.

So every D rule that cites 9153772 is cited through its `_unverified` twin (`verified_code = []`, D-24). This matches
SEAgent (D-150) and DTap.

## 4. Proposed AER mapping (D-193 to D-197; for review)

One AER per run file, mapper `agentops.trace`, dialect `agentops.trace` variant `v1`, adapter 0.1.0, namespace
`agentops`.

| Source | AER | Evidence and rule |
|---|---|---|
| run file | header `unit: agent_execution`; `a0` primary (native); `a1` the joined task YAML (supporting) | O; join D-194 |
| 162 empty traces | `unit: outcome_only`, issue `agentops.empty_trace` (`no_execution_observed`), run `status: error` with the error text as an artefact; scores kept | O (error observed) |
| `agent_id` | actor `agent` (`llm_agent`): `model.requested` and the route (`anthropic`, `openai`, `openrouter`) split by `agentops.agent_id_identity@1`; the full id verbatim in `ext`; `unk` served, params | value O; split I (twin) |
| harness | actors `bench` (`agentops-bench`; version and code `not_recorded`, deposit `1.0.0` in `ext`) and `harness` (`agentops_bench` adapters); `env` (`tool_runtime`, the instrumented tool server) | I where code-based |
| task YAML | fixtures `task_prompt` (description + context, composition I), `ground_truth` (`expected_output`), the whitelist in `ext`; no `system_prompt` fixture (not logged) | content O by config; join D |
| step *n* | `mc<n>` (`role: agent`, `kept`), `usage` from `llm_*_tokens`; `input` = earlier messages (I, `agentops.context_is_prefix_unverified@1`); then `m<i>` role `agent`, `generated_by: mc<n>`, parts: `text` (`reasoning`, if any), then one `tool_call` part per call in array order | values O; existence I (`agentops.step_is_one_model_call_unverified@1`); text-before-calls order I |
| call *i* of a step | `te<k>` actor `env`, `call` → the part, `t.start` = `timestamp` with `evf {"/t/start": "I"}` (`agentops.call_timestamp_is_dispatch_unverified@1`); `latency_ms` to `ext` (`unk /t/dur_s ambiguous`); status `not_recorded` (never inferred from `Error:` text) | link I (`agentops.pair_by_index_unverified@1`, guarded by name equality: any mismatch links nothing, `call_result_link_conflict`) |
| result *i* (plain) | `m<j>` role `tool`, `generated_by: te<k>`, `tool_result {responds_to}`; dict → `value`, str → `text` verbatim, null → `value: null` | O |
| result with `injected_failure` | **no** `te`: `ac<n>` `activity {type: "agentops:fault_injection", actor: "harness"}` generates `m<j>` (`responds_to` the call); `ext.agentops.injected_failure`; issue `unexecuted_tool_call` on the call | field O; "tool not run" I (code) |
| result with `injected_payload` | fixture `injection_payload` (actor `att`, content = the field, O); `te<k>` generates the tool output; `ac<n>` `agentops:payload_injection` (actor `harness`, inputs the output and the fixture) generates `m<j>`. The suffix relation is checked byte for byte (2,011/2,011, D); its attribution is I | D-196 |
| unknown tool name (6) | as any call; the name never enters a typed field if it is not a tool name (`ext`, `unk /name ambiguous`) | O |
| `final_output` | `ext` plus check `agentops.final_output_copy@1` (D: equals last text, 100 %) | D |
| `completed`/`error` | run scope `status` (`ok`, `error`; `limit` for the max-iteration run, I by code); error text as an artefact | O |
| `wall_time_seconds` | `ext.agentops.wall_time_seconds`, `unk /t/dur_s ambiguous` (clock by unverified code, as DTap D.16.4) | — |
| scores | SEM `outcome` claims only (assessment bundle): completion (LLM judge, unobserved), safety (regex heuristic), cost, efficiency. Report-only `reliability`/`recovery` not joined in profile v1 | claims, never evidence |
| order | `after` `b: "pos"` I (`agentops.steps_append_ordered_unverified@1`); no `time` edges | I |

Accounting: `aer.acc.agent_calls_vs_assistant@1` can be checked (one `mc` per step, usage present). The trace counters
(`total_*_tokens`, `scores.efficiency.total_tool_calls`, `scores.cost.step_breakdown`) become a profile accounting check
`agentops.acc.counters@1` (`total_tool_calls` and the `step_breakdown` length agree in 7,202/7,202; the token totals are
checked in part B).

Semantics profile `agentops.tools@1` (SEM): a tool table for the 10 tools, injection markers keyed by the 15 observed
payloads (sha256 of the text, so no payload text is committed outside fixtures), and an attack-class label per payload
taken from the code catalogue's comments (D-196).

## 5. Selection rule and join (D-191, D-194)

Profile `agentops-bench-pilot`, part `pilot-v1-seeded`. fnmatch has no braces, so there are three include globs and
eight exclude entries:

```toml
include = ["pilot_v1_seeded/*/*/adversarial/*_run*.json",
           "pilot_v1_seeded/*/*/clean/safety_*_run*.json",
           "pilot_v1_seeded/*/*/noisy/safety_*_run*.json"]
exclude = [ # 3,842 files: D-143, out of scope
  { glob = "pilot_v1_seeded/*/*/clean/code_*_run*.json", code = "select.out_of_scope", note = "D-143" },  # … 8 entries:
  # clean|noisy × code|data_analysis|research|tool_use
  { glob = "pilot_v1_seeded/*/*_report.json", code = "select.not_execution_artefact", note = "per-model rollup" },
  { glob = "pilot_v1_seeded/*/_partial_provenance.json", code = "select.not_execution_artefact" },
  { glob = "pilot_v1_seeded/_combined/*", code = "select.not_execution_artefact", note = "rollups and symlinks" },
]
context_artefacts = ["tasks:kunwarshivam-agentops-bench-9153772/tasks/*/*.yaml"]
```

`select.out_of_scope` **does not exist**. The closed set is `adapters/profiles.py` `SELECT_CODES` and
`corpus/register.py` `_FIXED_CODES` (spec H.6.3). None of the four codes is true of an in-scope exclusion: these files
*are* executions, are not owned elsewhere, and their dialect and licence are fine. Without an `exclude` entry the runner
skips them without registering anything, which D-143's "recorded as excluded" forbids. Hence D-191 and §6.

## 6. Invariant 5: core changes this family would need (part A; item 1 approved and done in part B)

1. **`select.out_of_scope`** (D-191): one code in `corpus/register.py` (`_FIXED_CODES`) and `adapters/profiles.py`
   (`SELECT_CODES`), plus spec H.6.3 and D.4. Owner: orchestrator (corpus). It is generic, not AgentOps-specific: D-143
   also scopes Zenodo 20404563. No AER, PROV or SEM byte changes, and no existing corpus digest moves (no existing profile
   uses it).
2. **Archive inputs** (D-156, existing): the runner must import deposit-archive members as units and take a context tree
   (`tasks`) from a zip member set.
3. **Top-level `tar.gz` with pax headers** (D-192): ingest (phase 12).

No change to `aer/`, `prov/` or `validate/` is foreseen.

## 7. Plan for part B (after the user's review)

`adapters/agentops/` (reader, mapper, pairing, join, rules `agentops.rules.toml`, semantics `agentops.tools-1`,
`artefacts.toml`, `family.schema.json`, `ext.schema.json`, profile `agentops-bench-pilot` `planned`, registry entry
append-only). Fixtures by criterion, byte-identical members, none with the operator account path: one adversarial
run with payloads and an injected failure; one multi-call step with repeated names; an empty trace; a `Loop stuck`
refusal; a noisy-safety run; an unknown-tool call; plus 2 task YAMLs and the Apache-2.0 text. Tests under
`tests/adapters/agentops/`, a new D subsection, and an in-memory map of all 3,360 in-scope members (D-154 method). If
D-156 and D-192 land first, scratch trial imports follow.

## 8. Part B: the `agentops` family (done)

Spec §D.18; files listed in D.18.12. Commits on `phase-10i-agentops`: `select.out_of_scope` as its own commit (the only
core change, user-approved under D-191: `adapters/profiles.py`, `corpus/register.py`, HL H.6.3, D.2/D.4, two tests),
then the family. Where the implementation differs **in form** from §4 (meaning unchanged; implementation notes on the
decisions):

| §4 proposal | Implemented as | Why |
|---|---|---|
| D rules citing snapshot `9153772`, cited through `_unverified` twins | class-I rules directly (`*_unverified@1`), snapshot paths as documentary evidence | the snapshot names only a 7-hex commit; a catalogue `code` entry needs a full commit, so the twins would always resolve to I anyway (D-193 note) |
| harness `activity` for fault and payload injection | fabricated failure: harness `decision` (`other`, subtype `agentops.fault_injection`) on the call, no execution; payload: execution then attacker `decision` (`modify`) | `aer/0.1` forbids an activity generating a message (C.3.13); C.5.5 is the prescribed pattern (D-196 note) |
| call timestamp as `t.start` tagged I | `t.raw.start` (O), typed start `ambiguous` | an I-class typed time is refused by tier 4 (D.16.18 correction 1; D-197 note) |
| scores as SEM claims only | AER `judgement` records (values O, origin I; `harness_default` for unevaluated safety), polarity in SEM `outcome` | SEM reads only the AER; C.3.10 is where recorded scores live |
| task join by path | pinned table `tables/task_files.toml` (100 rows) | the runner's listing only answers `exists(ref)`; the slug is not derivable from a run |

Fixtures: 13 runs chosen by criterion (§D.18.12) plus their 11 task YAMLs and the licence text, byte-identical members
read in memory, none carrying the account path. Tests: `tests/adapters/agentops/` (56: 53 pass, 3 strict xfails, §9 item
3).

## 9. Map of every member in memory (D-154 method) and routed items

No trial import: archive inputs (D-156) and the tar reader (D-192) are not on main. Every run member (7,202) was mapped in
memory through the product path (`map_artefact_total` with `member` origins for the run and its joined task member), the
AER validated in **release** mode, annotated and validated (SEM), derived (PROV), checked by tier 4 (`validate_prov`) and
scanned by the artefact safety net (script `p14_map_census.py`, 8 workers, 1,775 s; summary
[`agentops-bench.map-census.json`](agentops-bench.map-census.json)). Nothing was sealed or stored.

| In scope (3,360) | Result |
|---|---|
| crashes, degenerate AERs | 0, 0 |
| AER findings (release mode), SEM findings | 0, 0 |
| units | 3,259 `agent_execution`, 101 `outcome_only` |
| task join | 3,360 joined |
| decisions | 715 fault (`other`), 2,011 payload (`modify`): the census counts exactly |
| issues (occurrences) | `unexecuted_tool_call` 715, `agentops.repeated_tool_names` 437, `agentops.dispatch_error_result` 182, `agentops.run_error` 133, `agentops.empty_trace` 101, `agentops.unlisted_tool_name` 5 — each equal to the census |
| accounting | `agentops.acc.counters@1` consistent 3,360/3,360; seal status unverifiable 3,259 (derived model calls, by design), consistent 101 |
| injection markers | 2,195 present (2,011 on the payload's own result; 184 where the same payload text was injected into another result of the run), 4,875 absent |
| PROV tier 4 | passes for 2,805 runs; fails for the 555 runs with a fabricated failure, all on the core gap of item 3 |
| safety net | every finding classified after adding `agentops.art.text_encoded_call` (21 in-scope findings, heuristic) |
| determinism | 75 sampled members re-mapped: 75 byte-identical AERs |

The 3,842 out-of-scope files map equally cleanly (0 crashes, 0 AER or SEM findings; 800 runs on the same PROV gap); they
stay excluded by the profile.

Routed through the orchestrator:
1. **D-192** (phase 12): a top-level gzip tar as a deposit pin, and pax `x` headers with a closed key allowlist.
2. **D-156** (runner): deposit-archive members as units, a context tree from a zip. *Update at merge (2026-10-13):*
   archive inputs landed on main as D-200 (deferrals part A); the `tasks` zip as a second, context pin is not checked.
3. **Core PROV gap** (`prov/`, found here): `agentprov-prov/0.1`'s prepass gives `apv:dispatchStatus apv:NotDispatched` no
   source fields when the `unexecuted_tool_call` issue cites a class-I rule, so the statement lands in an inference
   bundle with no `apv:sourcePointer` and tier 4 refuses it (`pv.linkage.pointer_missing`, `pv.linkage.basis_not_cited`).
   Experiment: citing a D rule for the same issue validates, so the mapping is not at fault. Any family that cites an I rule
   for that issue is likely exposed (`dtap.call_without_result@1` is class I; not checked on DTap data). Pinned by
   `test_prov_validates_for_fault_injected_runs` (strict xfail). An import of this part waits for the fix.
   *Update (2026-10-13):* fixed by regeneration-batch item 24 (D-28 addendum 2): the mention points at its seal issue.
   DTap is exposed too (checked on a synthetic trajectory). The test passes and is no longer an xfail.

## 10. Follow-up (2026-10-14/15): the tasks pin, the scratch trial import and what it found

Branch `phase-10i-trial`. The orchestrator was "Phase 8 setup", and every network step had the user's yes in this
session. Scripts and outputs are under `~/.agentprov/migration-work/phase10i/` (`scripts/p20`–`p23`, `trial/`,
`dtap-remap/`), outside Git. Counts only below; no content is quoted.

### 10.1 Both blockers are closed on main

- **D-192.** The bounded tar reader now reads a gzip tar at depth 1 (D-247) and pax `x` headers through a closed
  allowlist (D-248). The allowlist ignores exactly this archive's keys: `mtime`, `LIBARCHIVE.xattr.*` and
  `SCHILY.xattr.*`.
- **The PROV gap (§9 item 3).** Regeneration-batch item 24 removed the strict xfail. The full trial confirms the fix:
  the 555 in-scope runs with a fabricated failure pass tier 4.

### 10.2 The tasks pin is git tag v1.0; the zip is its archival twin

- **Which commit.** `git ls-remote` shows `refs/tags/v1.0`: an annotated tag object `91537725…` that peels to commit
  `c7b29be6c0d8201d3025d4abc1244935b83586d6`. The zip's comment names that commit, and its root directory
  (`…-9153772`) the tag object. So §3.5's "7-hex commit" is the tag's id, not a commit's.
- **The fetch.** Depth 1 through `raw.fetch.Fetcher`, 2.17 MB in the bare store, logged in `acquisitions.jsonl`.
- **Byte identity.**
  - 100/100 rows of `tables/task_files.toml` equal the git blobs (sha256 and size).
  - The whole `tasks/` tree equals the zip's `tasks/` members (101 files).
  - `LICENSE` is equal (Apache-2.0).
- **The change (the user's choice).** The `tasks` pin is git `c7b29be6`: tree `tasks/`, `tree_sha1` `6434c5a4…`, 101
  files, 59,166 bytes. The zip is pin role `tasks_archive`, and the table's labels are git paths. The profile was
  changed in place at version 1 because no corpus had recorded it. That is on main at `04e9540d`, with profile sha256
  `6e109f28…75537`.
- **What it removes.** The git pin is a context tree the runner already accepts (R2), so D-530's "archive download pin
  as context tree" was dropped.

### 10.3 Scratch trial import (`scripts/p20_trial_import.py`, `p22_trial_all.sh`; through `suite_queue.py --class import`)

**Why a driver.** The registry part is `planned`, and the CLI builds no context tree (D-530). The driver passes the runs
tar as an `ArchiveTree` checked against its pin, and the tasks as a `GitPinTree` from the verified fetch cache (offline).

| Step | Result |
|---|---|
| Smoke (`--limit 5`) | 5 mapped, 0 failed |
| Full import, dev mode, 4 workers | 3,360 seen = mapped = derived = validated; 0 failed, 0 degenerate; 2,681 sealed clean, 679 with issues; 334 s |
| Issues | `unexecuted_tool_call` 555, `agentops.repeated_tool_names` 378, `agentops.run_error` 133, `incomplete_run` 133, `agentops.dispatch_error_result` 120, `agentops.empty_trace` 101, `no_execution_observed` 101, `agentops.unlisted_tool_name` 3, `agentops.user_message_not_logged` 3,259, `accounting_unverifiable` 3,259 (derived model calls, §9) |
| Register | the above (stage `map`, sealed) and 7 `ingest.archive.link` (the 7 symlinks in `_combined/`, rejected) |
| `validate --sample 300` (4 tiers) | 300 passed, 0 failed, 300/300 linkage resolved, 300/300 results reproduced |
| `verify --level chain` | 0 failed. 1 unverified: `checksums.absent`, expected in a working tree. 3,360 executions, 5,760 members and 3,462 raw objects re-hashed |
| `recompute --dry-run` | **3,360 unexplained changes**: every re-mapped unit gets `agentops.task_join_missing`. This is D-530 item 3 (a re-map passes no context trees), as predicted |

The census counts are reproduced. They are lower than §9 for `repeated_tool_names`, `dispatch_error_result` and
`unlisted_tool_name` because §9 counted occurrences and the register counts runs.

### 10.4 Findings routed to the orchestrator

1. **The re-map drops the task join** (D-530 item 3). Approved; built in the D-530 sequence. DTap at one commit shows
   the same: a no-LFS sample of 48 runs gives 40 `unexplained_change` and 8 identical, and all 6,682 context origin
   rows are dropped.
2. **DTap's recompute refuses corpora that hold LFS objects** (`corpus.rawtree.invalid`; D-530 item 5, folded into the
   re-map fix). DTap's "0 differences" was therefore never claimed for such corpora.
3. **Archive inputs ignore the profile's `exclude` entries.** The expand selection is the include globs only (R-40),
   so the 3,842 out-of-scope run files are `not_selected` rows in `raw/members.jsonl`. They get no `select.out_of_scope`
   register entry, and the snapshot reports `selection_excluded: 0`. D-143/D-191 ("recorded as excluded") is met only
   by the member rows. Runner, not family; every archive-input profile with `exclude` entries is affected.
   **Ruling (user, 2026-10-15): fix the runner, D-560** (regen item 100, held branch `phase-10i-context`).
4. **The include globs select 2,400 AppleDouble members.** The members `._<domain>_<NNN>_run<k>.json` sit under
   `adversarial/` and match `adversarial/*_run*.json`. They are decompressed and stored, but the reader and the runner
   treat `._*` as strays, so they are never mapped and never registered. Fix: `[!.]*_run*.json` (the expand glob is
   `glob.translate`, the reader's is `fnmatch`; both support `[!.]`). It is a profile byte change, coordinated with the
   bug pass's held v2 bump (v1 bytes pinned at `6e109f28…`). **Ruling (orchestrator, twins' rule, 2026-10-15):** the
   scratch trial records v1, so the glob fix goes into the bug pass's v2 (`bugpass-regen-agentops`), not in place.
5. **`raw.fetch` refused a Zenodo key with `/`** (D-530 item 4, class 0). On main at `c4f412b5`.

The registry part stays `planned` here; see §10.5.

### 10.5 Registry status

The import path itself is clean. Moving to `partial` now would let `agentprov import` run the part without any task
context: the CLI has no `--context` until D-530, so every AER would carry `agentops.task_join_missing`. Recommendation:
move to `partial` together with D-530's CLI part (which then refuses an import without the `tasks` context), with the
caveat "full snapshot not yet imported; re-map reproduces after D-530; out-of-scope files recorded as not-selected
members (finding 3)". The decision is with the orchestrator and the user.

### 10.6 Survey: archive-input profiles with `exclude` entries, and include globs that can match `._*` (2026-10-15)

The survey is static. It reads the profiles on main and on `phase-10j-deposits` `323ededd`, never the archives, so
"can match" means the last segment of a glob does not start with `[!.]` or `.`. Whether a deposit actually holds `._*`
members is a census question; only AgentOps-Bench is confirmed (2,400).

| Profile (primary pin) | `exclude` entries (codes) | Include globs that can match `._*` |
|---|---|---|
| `agentops-bench-pilot` (zenodo) | 12 (8 `select.out_of_scope`, 4 `select.not_execution_artefact`) | 1 of 3 (confirmed: 2,400 members) |
| `credleak-p15b` (zenodo) | 6 | 3 |
| `code-agent-misalignment-geminicli` (zenodo) | 5 (3 `select.out_of_scope`) | 1 |
| `seagent-agentdojo` (zenodo) | 2 | 1 |
| `controlarena-persistent` (hf) | 38 | 1 (`**/*.eval`) |
| `redcode-exec-openhands` (zenodo) | 0 | 1 |
| `what-surrounds` (zenodo) | 0 | 1 (`runs_named/*/*`) |
| `autogen-guard-placement` (zenodo) | 0 | 0 |
| 10j `authority-caps-agentdojo` (zenodo) | 2 (`select.not_execution_artefact`) | 2 of 2 |
| 10j `ipi-defenses-agentdojo` (zenodo) | 2 (`select.not_execution_artefact`) | 1 of 1 |
| 10j `dca-agentdojo` (url) | 2 (`select.not_execution_artefact`) | 1 of 1 |

10j's `drift1`, `environmentoptim` and `kavach` profiles are git pins, i.e. directory inputs, so neither effect
applies. Every profile with `exclude` entries in this table is in D-560's scope. The `._*` exposure matters only where
a deposit holds such members: they are decompressed and stored, and readers that treat `._*` as a stray never map or
register them.
