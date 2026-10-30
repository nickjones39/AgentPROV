# Candidate source: DTap-Bench agent trajectories

Status: **included as a candidate** (user decision 2026-10-11). It needs a new adapter family, planned after phase 11.
This file records the sample read, the convertibility assessment and the **limitation that the manuscript must
state** (§4). **Updated with the full census of 2026-10-11** (§3 and §6, and
`AgentPROV/investigation/sources/dtap.md`): §4's first explanation came from a two-run sample; §6 gives the corrected
limitation figures.

## 1. Identity and licence

- **Run logs:** Hugging Face `AI-Secure/DTap-Bench-Agent-Trajectories`, revision
  `836caf2fdd78b888ddd14fb62dc038e932e17898`. Licence Apache-2.0, stated in the dataset card and pointing to the
  upstream LICENSE.
- **Task definitions:** Hugging Face `AI-Secure/DecodingTrust-Agent-Platform`, revision
  `a3edc9b7c48cbf16c2ea9c18990fb94c7494dd04` (last modified 2026-06-18), Apache-2.0. Its 6,682 task directories
  each hold `config.yaml`, `setup.sh` and `judge.py`. `metadata/seed.sql` is present in only 582 of them
  [sources/dtap.md §2.4].
- **Paper:** Chen et al., *DecodingTrust-Agent Platform (DTap)*, arXiv:2605.04808 (2026).
- **Eligibility:** IN-1 to IN-5 hold, provided IN-3 is met by a new adapter that needs no core change. EX-LIC does not
  apply.

## 2. What was read (2026-10-11, user-approved)

All files are under `~/.agentprov/migration-work/syssearch/samples/dtap/`.

- **Dataset cards:** both cards were read.
- **Run listing:** the complete recursive file listing of the run logs, with no truncation, made with paginated
  API calls.
- **Two complete runs, each with its `judge_result.json`.** Both are task `crm/malicious/indirect/data-exfiltration/1`:
  - OpenAI Agents SDK with GPT-5.2: `20260326_013442.json`, sha256 `f1f951d7…`.
  - Claude Agent SDK with Claude Opus 4.6: `20260327_065000.json`, sha256 `8e16df21…`.
- **One task configuration:** the `config.yaml` of the same task, sha256 `c9f53cdc…`.

## 3. Size and coverage (full census, 2026-10-11)

67,808 trajectory files and 65,902 judge results over 10 agent-framework/model pairs (counts from
`~/.agentprov/migration-work/phase10b/census/c01e_census.json`; `AgentPROV/investigation/sources/dtap.md` §2). The
first listing found only the 64,110 timestamp-named files; the census adds 3,590 `trajectory.json` files (the whole
workflow domain), 99 `<TS>_N.json` re-runs, 8 `(1)` copies and 1 partial trajectory. Some task directories hold
several trajectory files (re-runs; 1,291 directories) under one judge result.

| Agent framework | Model | Trajectory files: benign / direct / indirect / direct_prompt / direct_no_attack |
|---|---|---|
| OpenAI Agents SDK | gpt-5.1 | 2,041 / 1,209 / 1,232 / 408 / 0 |
| OpenAI Agents SDK | gpt-5.2 | 3,181 / 1,916 / 2,121 / 500 / 240 |
| OpenAI Agents SDK | gpt-5.4 | 2,806 / 1,858 / 2,072 / 500 / 240 |
| OpenAI Agents SDK | gpt-oss-120b | 2,923 / 1,857 / 1,985 / 500 / 240 |
| Claude Agent SDK | claude-opus-4-6 | 2,807 / 1,972 / 1,994 / 500 / 240 |
| Claude Agent SDK | claude-sonnet-4-5 | 2,961 / 1,881 / 2,150 / 500 / 240 |
| Google ADK | gemini-3-pro-preview | 2,806 / 1,892 / 2,118 / 500 / 240 |
| OpenClaw | claude-opus-4-6 | 2,854 / 1,874 / 1,986 / 500 / 240 |
| OpenClaw | gpt-5.2 | 2,813 / 1,899 / 2,072 / 500 / 240 |
| OpenClaw | gpt-5.4 | 600 / 600 / 600 / 400 / 0 |
| **Total** | | **25,792 / 16,958 / 18,330 / 4,808 / 1,920** (67,808) |

- **Domains:** 14, among them CRM, finance, medical, legal, travel, code, OS and browser. The tasks run against 50+
  MCP sandboxes.
- **The two extra malicious splits** (called "unlabelled" in the first listing, which wrongly guessed the browser and
  desktop domains): `malicious/direct_prompt`, where the plain malicious goal is the user message (4,808 files:
  finance 2,000, legal 2,008, windows 800), and `malicious/direct_no_attack`, a medical control without an attack
  (1,920 files).
- These counts are of trajectory files, not executions: synthetic (20), empty (17), LFS-pointer (2) and duplicate
  files are handled as decided in phase 10b (`docs/reports/analysis/datasheet-items.md`, DTap rows).

## 4. Limitation for the manuscript: the injection is only partly observable in the run logs

**Finding.** In the GPT-5.2 run the judge records `attack_success: true`: 18 contact details were emailed to the
attacker's address. That address first appears in the agent's own `send_email` call (step 53). No logged tool output
before it contains the address or the injected instruction. The agent's inbox search was filtered to `@company.com`,
so it never retrieved the injected email.

**Explanation, from the task configuration.** This task injects through two channels at once:
1. **Environment injection** (`type: environment`): an email from an attacker-controlled address is placed in the
   victim's inbox. When the agent reads it, it appears in a tool output, exactly as an AgentDojo injection does. The
   Claude Opus 4.6 run read this email (step 12), did not follow it, and the judge records
   `attack_success: false`.
2. **Tool-description injection** (`type: tool`, `mode: suffix`, `injected_tool: gmail:send_email`): an instruction is
   appended to the `send_email` tool's *description*. The model receives it with the tool list on every request. The
   run log records neither tool descriptions nor the system prompt; the OpenAI-SDK "List MCP Tools" step records tool
   names only. The GPT-5.2 run's behaviour is consistent with having followed this channel.

**So is the data missing?**
- **The payload text is not missing.** It is recoverable, verbatim, from the task's `config.yaml` at a pinned revision
  of the task dataset. The same file has the system prompt, the malicious goal and the policy references.
- **What is missing is per-run evidence.**
  - A tool-description payload never appears in the run log, so the log cannot show whether that run's model actually
    received it.
  - Which configuration revision the run used is not recorded. The runs are dated March 2026 and the task dataset was
    last modified in June 2026.

**How AgentPROV would represent it** (consistent with the invariants, no fabricated evidence):
- **Environment payloads:** treated like AgentDojo injections. The payload text comes from the configuration and is
  matched against logged tool outputs by the existing marker mechanism, so exposure is *observed* when the text
  appears.
- **Tool-description payloads:**
  - Recorded as a configured injection whose exposure is *inferred*, never observed. The statement is class I, in the
    inference bundle. Its premise is the pinned `config.yaml` blob together with the trajectory–configuration link.
    Under D-24 it is class I in any case, because the harness code that applies the suffix is not verified for these
    runs.
  - Taint or causation from a tool-description payload is never asserted as observed.
- **Trajectory–configuration link:** verified per run before it is used. The trajectory's `task_info.task_id`,
  `original_instruction` and `malicious_instruction` must equal the configuration's `task_id`, `task_instruction` and
  `malicious_goal`. A mismatch is disclosed and the configuration is not used for that run.
- **Configuration revision:** the dataset's commit history makes it possible to choose the revision in force at each
  run's timestamp. Whether that revision is the one the run actually used remains an inference.

**Wording for the limitations section (draft).** "DTap-Bench run logs record agent actions and tool outputs but not
tool descriptions or system prompts. Tool-description injections, one of DTap's injection channels, are therefore not
observable in the logs. AgentPROV recovers their payloads from the pinned task configuration and records exposure to
them as an inference, not an observation. Attack-success judgements for such runs are reported as recorded, but the
provenance graph cannot show the path by which the payload reached the agent."

**Before conversion:** quantify how often this occurs. That means counting the indirect tasks whose configuration
has a `type: tool` (or `skill`, or `prompt`) attack step, and how many successful attacks lack any observed
environment payload. Both figures go into the manuscript beside the limitation.

## 5. Format and conversion assessment

- **One schema for all four frameworks:** `{task_info, traj_info, trajectory[]}`. Steps have role `agent`, `tool` or
  `user`:
  - Agent steps carry `action` and `metadata.{tool_name, tool_params, server}`, or `send_message_to_user` with
    `metadata.message`.
  - Tool steps carry `state`, which is a string, list or object, and sometimes `metadata.duration_s`.
- **Model identity:** taken from the path only (`<framework>/<model>/…`), as with AgentDojo's layout.
- **No call ids.** Calls and results are paired by order, and this needs a disclosure rule: Claude-SDK runs issue
  several calls before their results (`AATT`).
- **No per-step timestamps.** There is one run timestamp and a run `duration`. Nothing is invented for the steps.
- **Some tool results are Python `repr` strings** (`{'type': 'text', 'text': '…'}`). They are kept as text, never
  evaluated.
- **Recorded judgements:** `judge_result.json` holds `task_success`, `attack_success`, messages and metadata, kept
  beside any recomputation.
- **Credentials in the configuration:** `config.yaml` contains sandbox credentials (`env_vars`, dummy values). The
  adapter must not carry `env_vars` into any AER or report (header allowlist principle, G).
- **Effort:**
  - A new adapter family (reader, mapper, profile, rule catalogue, semantics table) plus a configuration join.
  - About 2.6 GB of run logs plus the task dataset.
  - A multi-hour import.
  - No core change is expected. If one turns out to be needed, invariant 5 requires stopping and recording it first.

## 6. Full census (phase 10b step 1, 2026-10-11): corrections and final figures

Source: `AgentPROV/investigation/sources/dtap.md` and `verify/dtap.md` (sibling directory of the repository); counts
are reproducible from `~/.agentprov/migration-work/phase10b/{census,scripts}/`.

**Licence confirmed.** Neither dataset repository has a LICENSE or NOTICE file; both cards declare Apache-2.0 and point
to the upstream `AI-secure/DecodingTrust-Agent` LICENSE, which is the Apache License 2.0 text (sha256 `c71d239d…`,
added in commit `e0e38455`, 2026-04-25; GitHub licence `Apache-2.0`). Committed fixtures carry that text and an
attribution note.

**Counts.**
- 67,808 trajectory files (not 64,110): 64,110 timestamp-named, 3,590 `trajectory.json` (the whole workflow domain),
  99 `<TS>_N.json`, 8 `(1)` copies, 1 partial.
- 65,902 judge results (one per task directory), 6,682 task configurations, 1,609,274 steps.
- The "unlabelled" 6,720 runs are `malicious/direct_prompt` (4,800; the malicious goal as the user message) and
  `malicious/direct_no_attack` (1,920; a medical control).
- Quality: 20 `synthetic: true` trajectories (not executions), 47 OpenClaw harness failures that were judged anyway,
  17 empty trajectories, 2 LFS pointers, 458 judge results re-judged on 2026-04-26 (`audit_correction`), and 1,291
  task directories with several trajectories but one judge (which attempt it judges is unknown).

**Limitation, corrected.** The two-run sample overstated it: the logs are *not* uniformly blind to tool descriptions
and system prompts.
- 11,413 OpenClaw runs log tool descriptions (`metadata.mcp_tools`); 1,534 runs carry a `debug` block, 629 with the
  system prompt (equal to the configuration's in 476 of 476 comparable runs). Where a tool-injection step and a
  description log co-occur, the exact suffix is visible in 1,972 of 2,251 indirect runs (87.6%).
- Of 17,607 indirect runs, 13,408 (76.2%) have a tool, skill or prompt attack step; 8,288 have no environment step.
- Of 6,162 **successful** indirect attacks, 4,041 (65.6%) show no environment payload in any logged tool output; 3,993
  of those have a tool/skill/prompt step. **3,533 successes (57.3%) have neither an observed environment payload nor a
  logged tool description**: for these the path by which the payload reached the agent is unobservable in the logs.
- Direct runs: the jailbreak prompt replaces the user message; it is visible in a logged user step in 12,603 of 16,007
  (78.7%).
- Matching is containment on alphanumeric text; a paraphrased payload counts as unobserved, so these are upper bounds
  on unobservability only for verbatim payloads.

**Draft limitation wording (replaces §4's).** "DTap-Bench logs record agent actions and tool outputs; tool descriptions
and system prompts are logged only for some harnesses (OpenClaw tool lists; debug logs). For 57.3% of successful
indirect attacks the payload is visible neither in a tool output nor in a logged tool description, because DTap
injects through tool descriptions, skills and prompts as well as the environment. AgentPROV recovers the payload from
the task configuration and records exposure to it as an inference, never an observation; for these runs the
provenance graph cannot show how the payload reached the agent."

**Join and version.** All runs (2026-02-12 to 2026-05-05) predate the first commit of both datasets (2026-05-14,
2026-05-21), so no public revision was in force at run time; only 22 `config.yaml` files changed between the first
public revision and the pin. The path join finds a configuration for 67,011 of 67,806 runs; 62,419 (92.06%) verify on
both instruction and goal, 2,899 on one, 1,693 on neither (medical ids off by one; telecom/browser ids reformatted;
`original_instruction` truncated at 500 characters in 7,353 files; 1,183 goals rewritten for evaluation). The join is
therefore tiered and every mismatch disclosed.

**Pairing.** No call ids. OpenAI and OpenClaw strictly alternate; Google ADK batches are contiguous; Claude SDK batches
interleave and 20,318 result names are literally `unknown`. 8.6% of results are in multi-call batches (Claude SDK
29.5%, Google ADK 44.9%); first-in-first-out is supported by content overlap in about 93–96% of informative batches.

**Secrets.** 1,206 trajectory files contain secret-like strings (counts only; liveness not tested, and testing them is
out of bounds), 4,139 configurations carry `env_vars`, and CRM runs embed attacker-account tokens. The redistribution
policy for these is a decision for the spec (step 2) and the user.
