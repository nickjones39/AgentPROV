# Phase 10e: verification of the remaining pending sources

Status: **verification only** (2026-10-12). Nothing was imported and no profile, adapter or `src/` code was written.
The user approved decisions D-140 to D-148 in section 5 on 2026-10-12 (D-149 is reserved). Phase 10e verified the 66 sources that were
`pending-verification` after phase 10c (59 listing only, 3 strand conflicts, 3 licence unresolved, 1 gated), with the
method of phase 10c: licence read at a pin, the pin recorded, runs counted, format family and adapter need, overlap
with included sources, decision with code.

**Evidence.** Every call is in `../data/V10e-verification/` (log, call lists, raw manifest, staged-file hashes). The
records carry the evidence in their `runs_basis`, `licence_source` and `notes` fields (`../records-merged.jsonl`). Census
scripts and outputs are in `~/.agentprov/migration-work/phase10e/`, and staged data is in `~/.agentprov/staging/10e/`.
The user approved the metadata reads, the sample downloads (about 510 MB) and the reading of section 5 (D-140) in
chat on 2026-10-12.

## 1. Summary

- **15 sources included, 51 excluded, none pending.** The screening now stands at 756 distinct sources: **48
  included** (6 current corpora + 42 candidates), **708 excluded**, 0 pending (`../prisma.md`).
- **78,001 counted runs** in the 15 new sources (one is a lower bound): 33,303 in the existing AgentDojo and Inspect
  families (13,264 of them, memo-ozdincer's, need a new results-container dialect) and 44,698 that need a new adapter
  family. Every new-family source has at least 1,000 runs and every existing-family source at least 100.
- **Exclusions of the 51:** EX-NOLOG 34 (generated or synthetic trajectories, definitions, outcome-only records,
  executions without tool use), EX-LIC-1 5, EX-FMT 5 (partial trajectories), EX-SIZE-2 5, EX-SIZE-1 1, EX-SCOPE 1.
- **Strand conflicts resolved:** AgentDrift (synthetic, README) and ATBench (planner-synthesised, paper) go to S1's
  reading; TELOS (digests and verdicts only, record description) goes to S3's. All three are EX-NOLOG.
- **New formats, not new semantics.** No source needs a change to `aer/`, `prov/`, `validate/` or `corpus/` on the
  evidence seen (invariant 5). The new families read event streams that record tool calls and their results
  explicitly. The OpenHands stream even records `cause` links from each observation to its action.
- **Ingest needs** (phase 12): a zip stored as byte parts and tar.zst members (control-arena), tar.zst and tar.gz
  members (Zenodo 20404563, 19875693). A results-container reader is needed in the agentdojo family (memo-ozdincer,
  regen-batch owner).

| # | Source (pin) | Runs | Licence -> corpus | Adapter | Profile effort |
|---|---|---:|---|---|---|
| 1 | Zenodo 23218779 SEAgent artefact | 5,342 | CC-BY-4.0 -> own permissive | agentdojo (zip members) | Low |
| 2 | legobridge/whistlebench (`9c27637c`) | 9,200 | MIT -> own permissive | inspect | Low |
| 3 | kexin-xu-01/agentharm (`859c34f4`) | 2,825 | MIT + AgentHarm clause -> restricted-use | inspect | Low/Medium |
| 4 | zixin22/fragfuse_agentharm (`24cc8aea`) | 1,747 | MIT + AgentHarm clause -> restricted-use | inspect | Low/Medium |
| 5 | mattngyn/atia_benchmark (`cc71caf5`) | 123 | MIT -> own permissive | inspect | Low |
| 6 | HF idacy/control-arena-persistent-state-eval-archive (`84d39e0a`) | >=802 | MIT -> own permissive | inspect | High (ingest) |
| 7 | memo-ozdincer/agentdojo (`7c331d97`) | 13,264 | MIT -> own permissive | agentdojo + results-container dialect | Medium |
| 8 | sani903/OpenAgentSafety (`857798ff`) | 1,560 | MIT -> own permissive | new: OpenHands event stream | Medium (new family) |
| 9 | Zenodo 23168099 RedCode-Exec agents | 8,760 | CC-BY-4.0 -> own permissive | new: OpenHands + Qwen Code stream-json | Medium (shares #8) |
| 10 | Zenodo 22737462 credential-leak study (v3) | 19,636 | CC-BY-4.0 -> own permissive | new: cell JSON | Medium (secrets policy) |
| 11 | HF lihaonan0716/mcphunt-agent-traces (`c4c69322`) | 6,786 | CC-BY-4.0 -> own permissive | new: MCPHunt trace JSON | Medium |
| 12 | Zenodo 19875693 AgentOps-Bench | 3,360 of 7,200 | Apache-2.0 -> own permissive | new: AgentOps trace JSON | Medium (D-143 approved) |
| 13 | Zenodo 20404563 code-agent misalignment | 2,182 of 10,000 | CC-BY-4.0 -> own permissive | new: gemini-cli stream-json | Medium (tar.zst) |
| 14 | Zenodo 21944598 tool-metadata injection | 1,334 | CC-BY-4.0 -> own permissive | new: Bedrock Converse logs | Medium |
| 15 | Zenodo 23025259 AutoGen guard placement | 1,080 | CC-BY-4.0 -> own permissive | new: AutoGen event stream | Medium |

## 2. Ranked recommendation: what to profile or build next

The ranking weighs runs readable with the least work, what is new for the corpus (models, attacks, frameworks), risk
(identity, ingest blockers, licence, scope) and effort. Effort is **Low** for a profile and a pin, **Medium** for an
extra layout or identity table or a new reader, and **High** for a blocker outside the adapter.

1. **SEAgent (Zenodo 23218779), agentdojo profile. Low effort.** 5,342 AgentDojo runs of deepseek-v3 under five
   defence arms (baseline, AgentSpec, PVAgent, SEAgent, SEAgent-RF), as direct zip members: readable today. This is
   phase-10d work: pipeline-name suffix, `evaluation_timestamp`, agentdojo 0.1.34 with benchmark v1.2.1.
2. **whistlebench, inspect profile. Low effort.** 9,200 samples of tool-using agents, many models, Inspect 0.3.130. It
   has the scope ruling D-147 (approved 2026-10-12).
3. **OpenHands event-stream family. Medium effort, one adapter for two sources.** OpenAgentSafety (1,560) plus the
   OpenHands part of Zenodo 23168099 (5,460) give 7,020 runs. Explicit observation-to-action `cause` links,
   `tool_call_metadata` and timestamps make it the cleanest new format seen. The Qwen Code stream-json of 23168099
   (3,300 runs) is a second, small reader.
4. **kexin-xu-01/agentharm and fragfuse_agentharm, inspect profiles. Low/Medium effort.** 4,572 AgentHarm samples on new
   models and attacks (carrier injection, memory retrieval). Restricted-use corpora (LIC 3). Model ids of local
   checkpoints carry workstation account paths that must be redacted in the profile.
5. **Zenodo 22737462, new reader. Medium effort.** The largest new-family source: 19,636 coding-agent runs over 21
   models and many injection channels, with tool inputs and outputs per turn. It needs a withholding policy for its
   planted canary credentials before any import (as for DTap `env_vars`).
6. **memo-ozdincer, agentdojo results-container dialect. Medium effort** (reader change, regen-batch owner). 13,264 runs
   of circuit-breaker and LoRRA defences on Llama-3.3-70B and Qwen2.5-7B, with AgentDojo message lists.
7. **MCPHunt, new reader. Medium effort.** 6,786 traces of multi-server MCP agents with per-call results and canary
   flags.
8. **AgentOps-Bench, new reader. Medium effort.** 3,360 in-scope runs on eight 2026 models; first needs the scope
   ruling D-143 (approved 2026-10-12).
9. **Zenodo 21944598, Bedrock Converse logs. Medium effort.** 1,334 runs of seven production models. The format is a
   wire log (successive API requests and responses), so a reader could share code with the capture/0.1 wire model.
10. **Zenodo 20404563, gemini-cli stream-json. Medium effort.** 2,182 structured runs; needs tar.zst member streaming.
    The other 7,818 rollouts are not readable faithfully.
11. **Zenodo 23025259, AutoGen event stream. Medium effort.** 1,080 runs (8% above the threshold) on local models;
    lowest value per effort.
12. **ATIA, inspect profile. Low effort but small** (123 samples, one suite, multimodal inputs).
13. **Control-arena archive, inspect. High effort.** At least 802 logs of AI-control runs, blocked on ingest (a zip in
    256 MB parts; tar.zst). Route to phase 12 first.

## 3. Cards

Each card gives the licence, pin, census, format and adapter needs, overlap, and limitations. Counts are from the
bytes, zip central directories or container headers at the pin, as each card states.

### 3.1 Zenodo 23218779: SEAgent artefact (ACSAC 2026)
- **Licence:** CC-BY-4.0 (deposit metadata).
- **Pin:** record 23218779 (2026-10-07), file `seagent-acsac2026-ae-v2.zip` (237,707,785 bytes). This is the latest of
  four versions (19236299, 22771109, 23209025, 23218779).
- **Census:** 5,342 AgentDojo TraceLogger runs under `results/raw_data/agentdojo/{security,perf}/<arm>/`: 4,685
  `injection_task_*.json` and 657 `none.json`. Counted from the zip central directory, read by HTTP range. One run was
  read: v1 keys plus `evaluation_timestamp`, `agentdojo_package_version` 0.1.34, `benchmark_version` v1.2.1. The
  directory also holds 12 cost summaries (not runs) and 12 AgentBench and AndroidWorld records.
- **Adapter:** agentdojo family. The profile needs the arm in the path, a `-seagent_mcp` / `-agentspec` pipeline suffix
  and `version_when_absent` checks.
- **Overlap:** pipeline names `deepseek-v3-250324*` occur in no converted source, so no file is byte-identical to a
  known run.
- **Limitations:** single model; harness code in the deposit is not verified.

### 3.2 legobridge/whistlebench
- **Licence:** MIT (LICENSE at `9c27637c`, sha256 a435c9f3...).
- **Pin:** commit `9c27637c3cf6` (2025-11-27).
- **Census:** 9,200 samples in 184 Inspect `.eval` files (central directories by range; no log without samples). One
  log was read: tool calls present, `inspect_ai` 0.3.130.
- **Adapter:** inspect family; profile needed.
- **Overlap:** own runs.
- **Limitations:** the scope reading for unsanctioned whistleblowing is D-147 (approved).

### 3.3 kexin-xu-01/agentharm
- **Licence:** MIT (LICENSE at `859c34f4`). AgentHarm prompts carry MIT plus an AI-safety use clause, so this goes to a
  restricted-use corpus (LIC 3).
- **Pin:** commit `859c34f411fd`.
- **Census:** 2,825 samples in 68 `.eval` (all read in memory). All 2,825 message lists are distinct, so the
  patched-judge directories hold distinct runs; 2,043 samples have tool calls.
- **Adapter:** inspect.
- **Overlap:** none with the survey's AgentHarm samples (different models and messages).
- **Limitations:** local model ids contain workstation paths with account names (redact). It is a personal working
  copy.

### 3.4 zixin22/fragfuse_agentharm
- **Licence:** MIT; restricted-use corpus (LIC 3).
- **Pin:** commit `24cc8aea1b99`.
- **Census:** 1,747 real-model samples in 168 `.eval` (12 samples with model `none/none` not counted). 149 logs hold
  one sample; nine hold the full 176-sample set.
- **Adapter:** inspect.
- **Limitations:** logs sit inside an `inspect_evals` fork, spread over task output folders.

### 3.5 mattngyn/atia_benchmark
- **Licence:** MIT.
- **Pin:** commit `cc71caf55c6f`.
- **Census:** 123 samples in 5 `.eval` (central directories by range). One sample was read: tool call present; model
  `google/gemini-2.0-flash`.
- **Adapter:** inspect.
- **Limitations:** only the account-takeover suite has logs. Inputs include audio, image and video, which the
  semantics tables do not yet cover.

### 3.6 HF idacy/control-arena-persistent-state-eval-archive-2026-07-30
- **Licence:** MIT (card).
- **Pin:** revision `84d39e0a485d`.
- **Census:** lower bound of 802 Inspect logs: 689 in three zips stored as 256 MB parts (central directories read by
  range across the parts), 110 in `logs_batch_runs-20260730.tar.zst` (sibling manifest), 2 loose and 1 auditor. The
  two loose logs were read: 4 samples each, with tool calls.
- **Adapter:** inspect.
- **Ingest:** the split zip must be concatenated and tar.zst members streamed (phase 12).
- **Limitations:** a working-directory archive that mixes runs, rescorings and analysis. A sample-level census must
  follow before import. The earlier archive (`...-vast-backup-20260423-archives`) is a lead.

### 3.7 memo-ozdincer/agentdojo
- **Licence:** MIT.
- **Pin:** commit `7c331d978acc`.
- **Census:** 13,264 runs from the `n_results` headers of 139 distinct-blob results containers (first 4 KB read by
  range). One container was read in full: `n_results` 144 equals 144 results, each with an AgentDojo message list
  (system, user, assistant `tool_calls`, tool with `tool_call`). `runs/` is byte-identical to upstream except 15
  files.
- **Adapter:** agentdojo family plus a results-container dialect (no per-run file; attack and model at container
  level). The 1,000-run tier is applied because the reader is new.
- **Not counted:** `qwen_shards/` (LoRRA training traces), and `results/agentharm_eval` and `pre_abstract` (33 files
  without `n_results`).
- **Limitations:** model paths contain workstation account names (redact). No injection strings at run level.

### 3.8 sani903/OpenAgentSafety
- **Licence:** MIT.
- **Pin:** commit `857798ff26c4`.
- **Census:** 1,560 `traj_*.json` (all byte-distinct; 5 named `*_draft`) over claude-sonnet (3.7), deepseek-r1,
  deepseek-v3, gpt-4o and o3-mini. S1's ~2,400 counted `eval_` and `state_` files.
- **Format:** OpenHands event stream with `action` / `observation`, `tool_call_metadata`, `cause`, timestamps; judge
  checkpoints in `eval_*.json`.
- **Adapter:** new family (OpenHands).
- **Limitations:** the maintained copy moved to `Open-Agent-Safety/OpenAgentSafety` (lead); `workspaces/` holds the
  task definitions (join like DTap's task configs).

### 3.9 Zenodo 23168099: "Which Orders Count?" (RedCode-Exec)
- **Licence:** CC-BY-4.0.
- **Pin:** record 23168099 (2026-10-05).
- **Census:** 8,760 trajectories:
  - OpenHands with claude-sonnet-4-6: S1 to S3, 3 x 720.
  - OpenHands with qwen3-coder-30b-a3b: S1 1,290, S2 1,290, S3 720.
  - Qwen Code: 3,300.
  - Counted from previews and central directories; two zips were read.
- **Format:** OpenHands event stream (as 3.8) and Qwen Code stream-json.
- **Adapters:** new OpenHands family plus a Qwen Code reader.
- **Limitations:** outcomes come from sandbox execution; the request types C1 to C3 are in the file names.

### 3.10 Zenodo 22737462: "How Credentials Leak from 'Safe' LLM Coding Agents"
- **Licence:** CC-BY-4.0.
- **Pin:** record 22737462, v3 (latest of three).
- **Census:** 19,636 runs in `runs[]` of 654 cell files, all content-distinct (2,916 in `archive-*` cells). Each run
  has `turns` with user message, assistant response, `toolCalls` (tool, input, output) and timestamp.
- **Adapter:** new reader.
- **Limitations:** planted canary credentials (17,479 OpenAI-like, 1,355 AWS-like, 1,354 Anthropic-like strings,
  counts only) need a withholding policy. Earlier versions v1 and v2 were not checked for runs missing from v3.

### 3.11 HF lihaonan0716/mcphunt-agent-traces
- **Licence:** CC-BY-4.0.
- **Pin:** revision `c4c69322bf9e`.
- **Census:** 6,786 traces, from card counts (3,615 main, 2,706 mitigation, 387 live-guard, 78 browser replication).
  The browser-replication sample holds the stated 39.
- **Format:** per-model JSON: `messages`, plus `events` with tool, args, server, full result, timestamp, turn, and
  canary flags.
- **Adapter:** new reader.
- **Limitations:** the main files are large (up to 111 MB), so a streaming JSON read is needed. The paper's 6,321
  excludes the defence arms.

### 3.12 Zenodo 19875693: AgentOps-Bench
- **Licence:** Apache-2.0.
- **Pin:** record 19875693, the version with the pilot traces. A later version in the concept, 19875603, holds code
  only.
- **Census:** 7,200 runs (100 tasks x 3 conditions x 3 runs x 8 agents, read in memory from the tar.gz). In scope:
  adversarial condition 2,400 + safety domain 1,440 - overlap 480 = **3,360**.
- **Format:** per-run trace with steps (reasoning, `tool_calls`, `tool_results`); tasks in the code zip.
- **Adapter:** new reader.
- **Limitations:** a mixed-scope benchmark (D-143, approved); macOS AppleDouble members (`._*`) to skip.

### 3.13 Zenodo 20404563: RESULTS_raw (code-agent agentic misalignment)
- **Licence:** CC-BY-4.0.
- **Pin:** record 20404563; sha256 of `RESULTS_raw.tar.zst` matches the record (f7186010...).
- **Census:** 10,000 rollouts (10,000 `verdict.json` in the archive and at `warmjademe/code_agent_agentic_misalignment`
  `1dec4f17`). Structured transcripts: **2,182** non-empty gemini_cli event streams (`tool_use` / `tool_result`).
  Not readable faithfully:
  - claude_code: 2,073 transcripts whose messages are plain strings.
  - codex_cli: 1,588 non-empty plain-text streams.
  - openhands: 2,000 transcript tails.
- **Adapter:** new gemini-cli stream-json reader; tar.zst ingest.
- **Limitations:** only one scaffold of four is convertible (D-143, approved).

### 3.14 Zenodo 21944598: "What surrounds an injection decides whether it works"
- **Licence:** CC-BY-4.0 for `runs_named/` (LICENSE-DATA in the zip); code MIT.
- **Pin:** record 21944598, v1.0.0.
- **Census:** 1,334 run directories (as stated).
- **Format:** `request.json` holds the successive Bedrock Converse requests (toolUse / toolResult turns) and
  `response_raw.json` the responses.
- **Adapter:** new reader (wire log).
- **Limitations:** tool results are synthetic by design (file tool returns synthetic text; the email tool sends
  nothing).

### 3.15 Zenodo 23025259: AutoGen guard placement
- **Licence:** CC-BY-4.0 (data); MIT (code).
- **Pin:** record 23025259, v1.0.
- **Census:** 1,080 runs with messages in `results/*/runs.jsonl`. 190 rows without messages are not counted. The count
  is within 10% of the threshold, so it was counted exactly.
- **Format:** AutoGen event stream (`ToolCallRequestEvent` / `ToolCallExecutionEvent`).
- **Adapter:** new reader.
- **Limitations:** local models; `events.jsonl` stores text hashes only.

## 4. Excluded: notable cases (full list in `../included-excluded.md` section 7)

- **Good sources excluded only by licence:**
  - `aisa-group/instrumental-choices-agent-traces`: 1,680 Inspect samples, in scope.
  - `stewy33/oai-hf-incident-replication`: 1,100 `.eval`.
  - Both would enter with a licence.
- **EX-FMT** (records keep only part of the trajectory):
  - MRT (ScaleAI; tool calls by name only, at least 1,271 runs).
  - agent-attack-atlas (no tool results).
  - agent-firewall (no tool outputs).
  - consciouslab (prompt modifications only).
  - Zenodo 22674365 (results cut at 243 characters).
- **EX-NOLOG by the tool-less reading (D-140):**
  - ConVerse (5,531) and firewall-agentic-networks (9,960, including ConVerse's 5,531 byte-identically).
  - adaptive-adversaries (945 + 111,713 battles).
  - logjack, ptf-id-bench, mega-security, seal, factor-ut, tool-output-spoofing-lab.

## 5. Decisions (D-140 to D-149; approved by the user 2026-10-12)

- **D-140** (applied with the user's approval of 2026-10-12): executions without tool use fail IN-1 and are coded
  EX-NOLOG. This covers chat-only probes, single text responses, tool-less pipelines, conversations between agents
  without tools, and harnesses that script the tool call so the model only answers.
- **D-141** (**approved by the user, 2026-10-12**): boundary between EX-NOLOG and EX-FMT.
  - Records with outcomes only (labels, a final response, hashes, tool names) are EX-NOLOG, as for saber in phase 10c.
  - Per-run records with a partial trajectory (tool calls without arguments, without results, or without inputs; tool
    results truncated) are EX-FMT.
- **D-142** (**approved by the user, 2026-10-12**): counting rules used and their disclosure.
  - Inspect samples are counted from zip central directories.
  - Containers are counted from their headers.
  - A verified lower bound passes when it is at least 10% above the threshold; it is shown as `>=N` (`<=N` for an
    upper bound below it).
  - Mock-model samples are not counted.
  - A run re-released byte-identically in another repository counts once (ConVerse in firewall).
  - Normalized re-releases of another source's runs count only executions not in an included source
    (chenjing-2024).
- **D-143** (**approved by the user, 2026-10-12**): a source with a faithful or in-scope part is included and counted on that part
  only:
  - Zenodo 20404563: 2,182 gemini_cli rollouts of 10,000.
  - AgentOps-Bench: 3,360 runs (adversarial condition and safety tasks) of 7,200.
  - The alternative is to exclude both (EX-FMT and EX-SCOPE as their first codes) and lose 5,542 runs.
- **D-144** (**approved by the user, 2026-10-12**): include the 15 sources of section 1, one corpus each.
  - kexin-xu-01 and fragfuse are restricted-use corpora (LIC 3).
  - None is copyleft or NC; MRT, the only NC source, is excluded.
- **D-145** (**approved by the user, 2026-10-12**): adapter and profile order as ranked in section 2. A shared OpenHands family comes before any
  single-source reader.
- **D-146** (**approved by the user, 2026-10-12**): needs routed before import.
  - To phase 12: split-zip reassembly and tar.zst members; tar.gz members for 19875693.
  - To the agentdojo owner: the memo-ozdincer results-container dialect.
  - In each profile: model-id redaction (kexin-xu-01, memo-ozdincer) and a canary withholding policy (22737462).
- **D-147** (**approved by the user, 2026-10-12**): whistlebench's unsanctioned whistleblowing by tool-using agents is read as
  unauthorised agent action (in scope). The alternative is EX-SCOPE, which would remove 9,200 samples.
- **D-148** (**approved by the user, 2026-10-12**): leads found during verification (Agent3Sigma Stage and Canary, Open-Agent-Safety, the earlier
  control-arena archive) stay outside the closed search. They are listed in the verification log, not screened.
- **D-149:** reserved.
