# Pre-check dossier: `shreeyavarma-llm-safety`

## 1. Header

| | |
|---|---|
| Corpus | `shreeyavarma-llm-safety` (MIT by repository: the unchanged upstream AgentDojo LICENSE blob; policy include, no copyleft, no use clause) |
| Parts | `shreeyavarma-llm-safety · head`: 672 TraceLogger logs (v1.k14 668, v1.k14.incomplete 4) in six result directories; 24,914 upstream `runs/` copies are `select.owned_elsewhere` (owner `agentdojo`) |
| Family / profile | `agentdojo` / `shreeyavarma-llm-safety@1` (sha256 `208cd7eb4378...`; dialect `agentdojo.tracelogger`; rules aer 1, agentdojo 2; SEM `agentdojo.suites@2`; code identity `range`, `verified_code = []`, D-24) |
| Pin | git `ShreeyaVarma/llm_safety` `78d22e4a` (2025-09-10; the repository's only own commit, parent upstream `acb4220a`). Input `--git` on the staged bare clone (phase 10c staging), 28,307 blobs = profile `expected_files` |
| Code commit | L1 and L2 at `cb0af3d8` (clean tree). Batch `wave2`; L1/L2 outputs committed in `497a0193` |
| Kind | wave 2, full pre-check (not in FA or E2) |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (L1, L2, exam, verify, dossier) |
| Agents | researcher and fact-checker (prereg, research), examiner (L1/L2 analysis), one verifier per finding (6), dossier writer |
| Data | [`data/shreeyavarma-llm-safety/`](data/shreeyavarma-llm-safety/): `research.json`, `l1-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `raw-checks.json`, `os1-population.json`, `os2-sample.json`, `findings.json`, `exam-scripts/`; cross-corpus `data/_cross/l1-xdup.json` |

- Code identity, part `head` (Level 2, [`code-head.json`](data/shreeyavarma-llm-safety/code-head.json)): commit `cb0af3d8`; engine code aer `24df84b5e307`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `d3f9995f61bf`; adapter agentdojo.tracelogger c311b5a6ac9e.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Repository | https://github.com/ShreeyaVarma/llm_safety (pin `78d22e4a`, HEAD of main on 2026-10-14; fork=false; 0 issues, releases or PRs) | the data: six committed result directories; harness is a vendored AgentDojo fork (22 harness files changed, 2 added) |
| Paper | none (web search 2026-10-14; `CITATION.bib` is the upstream AgentDojo entry) | the repository reports describe a hidden-state safety classifier on 1,000-conversation samples, most likely drawn from the upstream-style `runs/` default, not from these 672 logs |
| Benchmark paper | https://arxiv.org/abs/2406.13352 (v3) | context only: v1 workspace (40 x 6), not v1.2.1 (40 x 14); no tool_knowledge row |
| Results page | https://agentdojo.spylab.ai/results/ | context only: gpt-4o tool_knowledge all-suite row (2024-06-05), n not stated |
| Data record | none (no Zenodo/HF/Figshare); integrity rests on git blob ids at the pin | 2,386 absent blobs (nodejs/, PDFs, PNGs, weights), none under the result dirs |
| Issues | #116/#130 (UserTask16 read-flag utility bug, v1.2.1 affected), #213 (workspace IT6-13 empty ground truth, open), #150/#202/#219/#220 (LocalLLM parse/serve defects; #220 server error becomes an empty answer), #89 (Ollama port) | known defects |

Data-versus-paper notes (from `research.json`):

- No published number describes these logs. The only expectations are our own census tallies (utility 316/352, security 172/496 over 668 complete logs) and a derived gpt-4o ASR bracket (H7); AgentDojo v1 figures are context only (other suite version, all suites).
- The fork commit (2025-09-10) is 2-3 months after the logs (2025-06-18..2025-07-12); the code at the pin need not be the code that wrote them.
- Local-model identity is not recorded anywhere: `local` (56 logs, LocalLLM via an OpenAI-compatible server, fork default port 11434) and `Local model` (2 logs, the fork's HF Qwen provider). D-105: `identity_unresolved`, no Qwen id is invented.
- The local arms are fragments (28 attacked cells of 560, 14 of 40 benign, 2 single-task hf logs).

## 3. Expectations

Pre-registration: [`prereg/shreeyavarma-llm-safety.md`](prereg/shreeyavarma-llm-safety.md), committed in `fd75f8a3` (2026-10-14) before any check of this corpus ran, with an adversarial fact-check (its section 8; corrections: 14 not 4 commits after v0.1.34, results-page n not stated, port change for `local` only, blob count 28,307). Method amendments of README section 8 apply.

Hypotheses: H1-H3, H5-H13 (H13 uninformative, n=1), H15 and H17 supported; H16 supported on the sample (population after the round). H4 refuted on its trajectory clause only (PC-03). H14 refuted (PC-01).

Classes follow the canonical rules R1-R6 and the cross-cutting items of [`cross-cutting.md`](cross-cutting.md). Cited: CC-01 (fingerprint definition, no effect here: the identical groups make no calls), CC-06 (findings.json format), CC-07 (checked, does not cover #213; #181 and #161 are banking defects and do not apply to this workspace-only corpus: 0 affected), CC-08 (PC-06, resolved by recheck12), CC-09 (PC-04 is its reference). No slack logs, so CC-10 does not apply.

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Read from the staged bare clone at `78d22e4a` (`--git`), 1.7 s.

| Check | head | vs expectation |
|---|---|---|
| L1-01 counts | walked 28,304 blobs + 3 symlinks rejected (`ingest.path.symlink`) = 28,307; selected 672; excluded `select.owned_elsewhere:agentdojo` 24,914; context 4 (LICENSE, README.md, pyproject.toml, uv.lock); not_selected 328 (31 non-TraceLogger JSON + 297 non-JSON); absent_blob 2,386 (0 under `runs/`, 0 JSON); units 672, auxiliary 0 | equal to registry and census 672 (H1) |
| L1-02 parse | 672/672 strict ok; 0 duplicate keys, non-finite, big ints, lone surrogates, BOM, trailing data, invalid UTF-8, truncation, depth | H2 |
| L1-03 encodings | 0 U+2028/2029/0085, C0/C1, bidi, tag, zero-width, U+FFFD, mojibake. Residues by design (Python-repr tool output): escaped newline 212/672 artefacts (486 strings), escaped quote 56 (69), escaped unicode 97 (143, all `/messages/*/content/*/content`); JSON-in-string 0 | H3. The local logs hold no model text at all (PC-01) |
| L1-04 duplicates | 0 byte-identical within the part. Trajectory-identical 2 groups / 29 of 670 fingerprinted units (643 distinct): qwen2 benign user_task_0 + 14 qwen_agent tool_knowledge user_task_0; qwen2 benign user_task_1 + 13 attacked user_task_1. Cross-corpus: 0 byte-identical; 3 units in trajectory groups (2 with `yockcheng-prompt-injection-harness`: the two `Local model` system+user logs; 1 with `ast-survey-agentdojo`: a pre-pass with one empty completion), matching degenerate shapes, not shared data | H4 byte clauses hold, trajectory clause refuted (PC-03, from PC-01) |
| L1-05 arms | 8 strata exactly as prereg section 3: 40 / 14 / 560 / 14 / 28 / 14 / 1 / 1. Suite workspace v1.2.1 672, defence none 672, injection_variant plain 672; task kind user 643 / prepass 29. gpt-4o covers the full v1.2.1 workspace grid (40 benign, 14 pre-pass, 40 x 14 attacked). Missing: local tool_knowledge for user tasks 2..39 (532 cells), qwen2 benign 26 of 40, pre-pass for qwen2 and hf (hf has IT0 only). Extra cells 0. `pipeline_name` = dir 614 / 56 / 2; 0.1.34 and v1.2.1 in 672 | H1, H10 |
| L1-06 secrets/paths | 0 secret-like strings, 0 account paths, 0 named accounts, 0 operator-home, 0 local-path model ids in 672 | H8 |
| L1-07 timestamps | `/evaluation_timestamp` 672/672, 100 % parse, 100 % naive, 2025-06-18..2025-07-12, 0 non-monotone units. The 2 July logs are the 2 `Local model` logs. The 5 "non-monotone" artefacts are benchmark calendar arguments (content, not clock) | H9 |
| L1-08 degenerate | zero_messages 2 (the two H11 labels: one in `my_runs_qwen2_agent_no_attack` user_task_14/none, one in `my_runs_qwen_agent` user_task_1/tool_knowledge/IT13); incomplete 4 (those 2 + the 2 `Local model` logs); error-only 0; empty/tiny 0; run errors 0 (error null in 672). null_final 0 is a tool gap: 54 of the 56 local logs with messages end with one empty text block and no tool call (CC-08, PC-06) | H5, H11; PC-01, PC-05 |
| L1-09 | does not apply (git tree, no archive members) | n/a |

Raw outcome tally (OS-1): utility True 316/668 complete logs, security True 172/668 (= census 316/352 and 172/496); all 81 benign logs with an outcome have security True (benign constant, H6). The raw payload read (H12) and the local-shape read (H14) are in `raw-checks.json`.

## 5. Level 2

| Item | head |
|---|---|
| Sample | [`data/shreeyavarma-llm-safety/l2-sample-head.json`](data/shreeyavarma-llm-safety/l2-sample-head.json): 32 of 672 over 8 strata (`results_dir x pipeline_dir x attack_dir`), 5 x 6 + 1 x 2; seed 20261011; not `over_maximum`; as pre-registered |
| Import | scratch `l2-head-j2.partial` and `-j1.partial` at `cb0af3d8` (batch `wave2`: l1, sample, import_j2, import_j1, check all rc 0). 32/32 mapped; ok 15 (all gpt-4o) / ok_with_issues 17 (all local); degenerate 0; failed 0; adapter_defect 0; unreadable 0; join 1:1. Units agent_execution 31, outcome_only 1 |
| Validation | tiers aer, sem, prov, linkage: 32/32 passed, results reproduced 32, linkage 32/32. SHACL not implemented (skipped); regression n/a |
| Recompute | `--dry-run`: 32 identical, 0 unexplained |
| Determinism | j2 vs j1: 139 files, 0 differ, index identical |
| Verify chain | only `checksums.absent` (working tree); no `[withhold]`, so no sealed-copy run |
| A2 | 0 degenerate, 0 adapter_defect. Codes: accounting_unverifiable 29, earlier_attempts_unobservable 31, identity_unresolved 17, incomplete_run 2, no_execution_observed 1, no_outcome_recorded 1. The empty-message log gets `no_outcome_recorded`, not `incomplete_run`, by mapper design. Completeness unverifiable 30 / known_incomplete 2. Register `owned_elsewhere` 24,914 |
| A3 | 0 PI classes over 9,913 statements and 16,774 relation arguments |
| Evidence classes | top O 4,544; core D 151 / O 562; inference I 2,441; assessment I 747 / O 64. Core D = engine rules only (`aprov.n_gap` 119, `aprov.n_capture_profile` 32); family D rules appear only as seal-issue refs and the code-independent `yaml_norm@2`; 20 `_unverified` twins cited, as `verified_code = []` requires. `_unverified` split after recheck12 (CC-08, PC-06): twin inference I 2,109 / none 240, assessment I 360; mixed twin + native inference I 301; native-only 0 |
| Identity | gpt-4o-2024-05-13 resolved 15/15; `local` + `Local model` 17/17 `identity_unresolved`, unk `/model` not_recorded (D-105). Defence none 32; attack none 22 / tool_knowledge 10; 0 mismatches |
| SEM | injection_marker present on 5/5 sampled gpt-4o attacked runs; none on the 5 sampled local attacked runs (no tool output) |
| OS-2 (raw vs mapped) | 64/64 judgement slots equal; the outcome-less units carry no judgement (H16, sample) |
| Outcome origins | benign security `harness_default` 20; checker 9 + 9 on attacked runs |
| Redaction | 0 hits in 104 files |
| Withholding | no `[withhold]` policy: inert, as pre-registered |

### Recheck (CC-08, recheck12)

`plans/recheck12.toml` (l1, l1_10, check; sample frozen) against the d97d3a57 files; full deltas in [`_cross/recheck12.json`](data/_cross/recheck12.json). Every other L1/L2 count is unchanged; the only other deltas are run environment (code commit d97d3a57 with tools/src = 5efa3575, `tracked_changes` true, two H.8.4(2) recompute notices with 0 unexplained changes; R12-01).

| Part | L1-08 flags (old -> new) | L2 `_unverified` split | L1-10 |
|---|---|---|---|
| head | `null_final` - -> 54 | twin inference:I 2,410 -> 2,109; mixed 301; native 0 (sum 2,410 = old) | 4 screened (context 4); 0 hits; files with a hit 0; named accounts 0; operator 0; unreadable 0 |

- PC-06 resolved: `null_final` 54 (as expected); twin I 2,109, mixed 301, native 0.

## 6. Outcome comparison

No paper reports these logs, so the comparison is against the pre-registered census-derived expectations (H6, H7); AgentDojo v1 numbers are context only and get no verdict. Wilson 95 % on k/n. Gap rule (README section 4) not applied for n < 20 (amendment 2.2); L2 rows stand beside the population rate (R6). Full rows: `os1-population.json`, `os2-sample.json`.

| Arm | Level | n | Metric | Rate (Wilson 95 %) | Paper / reference | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|---|
| gpt-4o-2024-05-13 tool_knowledge (40 x 14) | L1 | 560 | ASR | 16.25 (91/560) [13.43, 19.53] | prereg H7 bracket 11.4-16.3 (64..91); no paper | 0 (inside, at upper bound) | match (H7) |
| gpt-4o tool_knowledge, IT0-5 (payload lists calls) | L1 | 240 | ASR | 31.25 (75/240) [25.72, 37.37] | context: upstream v1 workspace tool_knowledge 25.83; results page all-suite 34.50 | n/a | context only (PC-02) |
| gpt-4o tool_knowledge, IT6-13 (no call sequence, #213) | L1 | 320 | ASR | 5.00 (16/320) [3.10, 7.97] | none | n/a | disclosed (PC-02) |
| gpt-4o tool_knowledge | L1 | 560 | UA | 49.64 (278/560) [45.52, 53.77] | context: upstream v1 workspace 39.17; results page 57.71 | n/a | context only |
| gpt-4o none, user tasks | L1 | 40 | benign utility | 70.00 (28/40) [54.57, 81.93] | context: upstream v1 workspace 62.5; results page 69.07 | n/a | context only |
| gpt-4o none, pre-pass | L1 | 14 | pre-pass utility | 71.43 (10/14) [45.35, 88.28] | none | n/a | no reference |
| local (unresolved) tool_knowledge | L1 | 27 | ASR / UA | 0.00 (0/27) / 0.00 [0.00, 12.46] | H7 exploratory <= 27 | n/a | match; harness/serving failure, not model behaviour (PC-01); 2 distinct trajectories (PC-03) |
| local none, qwen2 user tasks | L1 | 13 | benign utility | 0.00 (0/13) [0.00, 22.81] | none | n/a | PC-01 |
| local none, qwen_agent pre-pass | L1 | 14 | pre-pass utility | 0.00 (0/14) [0.00, 21.53] | none | n/a | PC-01 |
| all attacked | L1 | 587 | ASR | 15.50 (91/587) [12.80, 18.65] | census 91/587 | 0.00 | match |
| all complete logs | L1 | 668 | utility True / security True | 47.31 (316/668) [43.55, 51.10] / 25.75 (172/668) [22.58, 29.20] | census 316/352, 172/496 | 0 | match (H6) |
| gpt-4o tool_knowledge | L2 | 5 | ASR (mapped) | 60.0 (3/5) [23.07, 88.24] | population 16.25; sampled ITs 0,1,3,4,12 population 25.0 | n < 20 | not applied |
| gpt-4o tool_knowledge | L2 | 5 | UA (mapped) | 40.0 (2/5) [11.76, 76.93] | population 49.64 | n < 20 | not applied |
| gpt-4o none, user tasks | L2 | 5 | benign utility (mapped) | 40.0 (2/5) [11.76, 76.93] | population 70.00 | n < 20 | not applied |
| gpt-4o none, pre-pass | L2 | 5 | pre-pass utility (mapped) | 80.0 (4/5) [37.55, 96.38] | population 71.43 | n < 20 | not applied |
| local, all arms | L2 | 14 | utility (mapped); ASR 0/4 | 0/14 [0.00, 21.53] | population 0/54, ASR 0/27 | n < 20 | not applied |
| all 32 sampled labels | L2 | 32 | raw vs mapped judgements (OS-2) | 64/64 slots equal | raw L1 fields | 0 | match (mapping faithful) |

No row is flagged. No arm is excluded or recommended for exclusion for its attack outcome; the 0 % local arms are kept and disclosed (PC-01).

## 7. Findings

6 findings, all confirmed by their verifier (0 refuted). Verifier corrections are folded in below and in [`findings.json`](data/shreeyavarma-llm-safety/findings.json) (CC-06 format). PC-06 is an analysis-artefact (R5, CC-08) and does not count for readiness.

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-shreeyavarma-llm-safety-01 | Local Qwen runs are single empty completions: 0 tool calls and no model text in all 58 local logs (54 `[system, user, assistant]` with one empty text block and `tool_calls` []; 2 without messages; 2 `Local model` `[system, user]`) | source-defect | S2 | confirmed. Added: at the pin, `local_llm.chat_completion_request` turns any exception into an empty response and `_parse_model_output` never drops text, so the shape is what a failed request produces (supports #220); an empty generation stays possible, cause undetermined. Detector must cite the `_unverified` twin (D-24). The 2 `Local model` logs belong to `incomplete_run`, not this entry | Keep all 58 logs; disclose that the local arms record a harness/serving failure, not Qwen behaviour; artefact entry below; check the same shape in other agentdojo-format corpora (follow-up 2) |
| PC-shreeyavarma-llm-safety-02 | AgentDojo #213: tool_knowledge payloads for workspace IT6-13 list no tool call (336 of 588 attacked logs: gpt-4o 320, local 16); gpt-4o ASR IT0-5 31.25 % vs IT6-13 5.00 % | source-defect | S2 | confirmed. Added: all 496 IT6-13 payload strings render the template with an empty `{tools}` slot (0 of 372 for IT0-5), so payloads are neither truncated nor unrendered; the cited `important_instructions_attacks.py` is the fork's vendored copy at `78d22e4a` | Disclose; report ASR per injection-task group beside the pooled rate (the drop is confounded with task identity); artefact entry below; consider a cross-cutting item for v1.2/v1.2.1 workspace tool_knowledge corpora; no exclusion |
| PC-shreeyavarma-llm-safety-03 | Prereg H4 trajectory clause wrong: the 27 fingerprinted local attacked runs collapse to 2 distinct trajectories, each identical to a qwen2 benign run | documentation-mismatch | S3 | confirmed. Clarified: 28 local attacked files, one is the empty-message log without fingerprint; S3 under R4 because PC-01 (S2) carries the disclosure | State that the effective n of the local attacked arm is 2 distinct trajectories, not 27; no data change |
| PC-shreeyavarma-llm-safety-04 | [CC-09] reference: generic AgentDojo artefact classes occur here but their `artefacts.toml` scope omits this source (benign_security_constant 84 logs / 81 judgements, injection_task_as_user 29, incomplete_run 4, naive_timestamp 672, payload_not_reaching_agent 123) | documentation-mismatch (CC-09) | S3 | confirmed. The 96 gpt-4o "payload not reaching" count is a raw-text heuristic, not yet the SEM-marker detector; keep that row `proposed`. Family-wide gap for the phase-10c/10d profiles | Family owner: widen the five scopes (one widening for all phase-10c/10d agentdojo-format profiles is acceptable); re-count with the detector after the round |
| PC-shreeyavarma-llm-safety-05 | Our profile note and census counter misdescribe the two empty-message logs: (a) note puts both in `my_runs_qwen2_agent_no_attack` (one is in `my_runs_qwen_agent`); (b) `empty_messages_with_outcome` = 2 counts every outcome_only unit | documentation-mismatch | S3 | confirmed. Corrected: (b) is also in the product census `src/agentprov/adapters/agentdojo/census.py` l. 125 (the source of the "measured" value), mirrored by `tools/agentdojo/import_scan.py` l. 331; mapper detects with_outcome only with judgements. No byte effect (no profile declares an observed count here) | Family owner: fix the note with the round (profile bump, AD-18) and `census.py:125` to require a judgement; census tool owner the same in `import_scan.py:331`; check `agentdojo-upstream`'s declared 207 under the new definition |
| PC-shreeyavarma-llm-safety-06 | [CC-08] L1 `null_final` misses the 54 local empty finals; the `l2_check` twin counter mixes native class-I rules (e.g. `agentdojo.auto_execution_unverified`, `agentdojo.checker_inputs_unverified`) with true D twins | analysis-artefact (CC-08) | S3 | confirmed. The exact "14 native / 20 twins" split did not reproduce (verifier: 21 twin ids, 2 native `_unverified` class-I ids); the corrected re-run gives the numbers. Fixes landed in `6b76c15e` and 5efa3575 | Resolved by recheck12: `null_final` 54 (as expected); twin I 2,109, mixed 301, native 0 |

Refuted: none.

Proposed `artefacts.toml` entries (text only; route to the agentdojo family owner):

```toml
[[artefact]]
id = "agentdojo.art.local_empty_completion"
title = "Local-model runs whose model turn is one empty completion"
description = "The local LLM element returned one empty text block and no tool call on the first model turn, so the run ended at once: no tool call, no payload read, utility False and (attacked) security False. At the fork pin, LocalLLM turns any request exception into an empty response, so a failed server request produces this shape; an empty generation cannot be ruled out. Kept as recorded (text unk ambiguous); the outcome describes a harness or serving failure, not model behaviour."
scope = { sources = ["shreeyavarma-llm-safety"], parts = ["head"], profiles = ["shreeyavarma-llm-safety"] }
cause = "upstream_harness"
detector = { rule = "agentdojo.empty_assistant_text_ambiguous_unverified@1 (or a dedicated I rule)", class = "I" }
recorded_as = { notes = ["message.unk:/parts/0/text=ambiguous"] }
handling = { class = "FO" }
expected = [
  { snapshot = "shreeyavarma-llm-safety:head", count = 54, unit = "executions", basis = "pre-check raw read 2026-10-15: only assistant turn is one empty text block without tool calls", status = "proposed" },
  { snapshot = "shreeyavarma-llm-safety:head", count = 58, unit = "executions", basis = "descriptive: local logs with 0 tool calls (54 above + 2 empty-message + 2 Local model incomplete_run)", status = "proposed" },
]
manuscript = true
refs = ["agentdojo #219, #220", "local_llm.py at 78d22e4a (vendored fork)", "PC-agentdojo-upstream-08"]

[[artefact]]
id = "agentdojo.art.tool_knowledge_empty_sequence"
title = "tool_knowledge payloads without a tool sequence (workspace v1.2/v1.2.1 IT6-13)"
description = "ToolKnowledgeAttack builds its tool sentence from ground_truth(), which is empty for workspace injection_task_6..13 in v1.2/v1.2.1 (#213); these payloads render with an empty {tools} slot and carry the goal without a call sequence. Kept as recorded; report rates per injection-task group."
scope = { sources = ["shreeyavarma-llm-safety"], parts = ["head"], profiles = ["shreeyavarma-llm-safety"] }
cause = "benchmark"
detector = { rule = "proposed: agentdojo.tool_knowledge_sequence_absent@1", class = "D" }
handling = { class = "FO" }
expected = [{ snapshot = "shreeyavarma-llm-safety:head", count = 336, unit = "executions", basis = "pre-check raw read 2026-10-15 (gpt-4o 320, local 16)", status = "proposed" }]
manuscript = true
refs = ["https://github.com/ethz-spylab/agentdojo/issues/213", "important_instructions_attacks.py ToolKnowledgeAttack.get_tools_sequence, fork's vendored copy at 78d22e4a"]
```

Scope additions (PC-04): `sources += "shreeyavarma-llm-safety"`, `parts += "head"`, `profiles += "shreeyavarma-llm-safety"` on `agentdojo.art.benign_security_constant` (84 logs / 81 judgements), `.injection_task_as_user` (29), `.incomplete_run` (4), `.naive_timestamp` (672), `.payload_not_reaching_agent` (123 attacked executions with messages); expected rows snapshot `shreeyavarma-llm-safety:head`, basis pre-check L1 raw read 2026-10-15, status `proposed`.

Items for AGENTS.md section 12:

- PC-01: all 58 local-Qwen logs of `shreeyavarma-llm-safety` record no model text and no tool call (54 single empty completions; 4 incomplete). Their 0 % utility and ASR describe a harness/serving failure, not model behaviour. Kept; `agentdojo.art.local_empty_completion` pending with the family owner.
- PC-02: AgentDojo #213 makes tool_knowledge payloads for workspace v1.2/v1.2.1 IT6-13 carry no tool sequence (336 of 588 attacked logs here); report ASR per injection-task group (31.25 % vs 5.00 % for gpt-4o). `agentdojo.art.tool_knowledge_empty_sequence` pending; a cross-cutting check of other corpora is proposed.

## 8. Recommendations and readiness

1. Route both artefact entries (PC-01, PC-02), the five scope widenings (PC-04) and the profile note / census counter fixes (PC-05, incl. `census.py:125`) to the agentdojo family owner. Datasheet and manuscript: local arms = serving failure (PC-01); pooled tool_knowledge ASR always beside the IT0-5 / IT6-13 split (PC-02); local attacked arm effective n = 2 trajectories (PC-03).
2. Orchestrator: run the PC-01 shape test and PC-02 payload test over the other agentdojo-format corpora and decide on cross-cutting items (follow-up 2).
3. After the round: H16 and `payload_not_reaching_agent` on the regenerated population (follow-up 3).
4. CC-08 re-runs for this part (follow-up 1).
5. No exclusion of any data: the 0 % local arms, the fragmentary arms and the IT6-13 cells are kept.

**Readiness: `ready-with-caveats`.**

- The part imports correctly and deterministically: 32/32 mapped and validated, recompute 0 unexplained, j1/j2 byte-identical (139 files), OS-2 64/64 raw = mapped, identity resolved or honestly unresolved (D-105), 0 secrets or account paths, all population tallies equal the census.
- Caveats, all owned and routed: the S2 disclosures PC-01 and PC-02 with their artefact entries (family owner); documentation scope/notes PC-03..05 (family owner, census owner); H16 population check after the round.
- Not counted: PC-06 (R5, CC-08, resolved); PC-04 (reference to CC-09).

## 9. Reproduction

Batch (wave 2; plan entry in `tools/precheck/plans/wave2.toml`):

```toml
[[part]]
corpus_id = "shreeyavarma-llm-safety"
source = "shreeyavarma-llm-safety"
part = "head"
l1 = ["--git", "~/.agentprov/staging/10c/shreeyavarma/llm_safety.git"]
```

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave2 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave2.toml
```

Steps the batch ran. W = `~/.agentprov/migration-work/precheck/shreeyavarma-llm-safety`, D = `docs/reports/precheck/data/shreeyavarma-llm-safety`:

```bash
uv run python tools/precheck/l1_scan.py --source shreeyavarma-llm-safety --part head --corpus-id shreeyavarma-llm-safety --jobs 2 --emit-fp --git ~/.agentprov/staging/10c/shreeyavarma/llm_safety.git
uv run python tools/precheck/l2_sample.py select --units W/l1-units-head.jsonl --source shreeyavarma-llm-safety --part head --corpus-id shreeyavarma-llm-safety --out D/l2-sample-head.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j2 --source shreeyavarma-llm-safety --part head --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j1 --source shreeyavarma-llm-safety --part head --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-head-j2.partial --out D/l2-head.json --sample D/l2-sample-head.json --l1-units W/l1-units-head.jsonl --compare-with W/l2-head-j1.partial --jobs 2
# inside l2_check:
uv run agentprov validate --corpus W/l2-head-j2.partial --tiers aer,sem,prov,linkage,shacl,regression --jobs 2
uv run agentprov recompute --corpus W/l2-head-j2.partial --dry-run --jobs 2 -q
uv run agentprov verify --corpus W/l2-head-j2.partial --level chain
```

Examiner scripts (read-only; from the worktree root; raw reads through `agentprov.ingest`, git with `GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file`):

```bash
PRECHECK_REPO=$PWD uv run python D/exam-scripts/raw_checks.py D/exam-scripts    # PC-01 local shapes, PC-02 payload call counts and ASR by IT
PRECHECK_REPO=$PWD uv run python D/exam-scripts/raw_checks2.py D/exam-scripts   # PC-01 final-content shapes
PRECHECK_REPO=$PWD uv run python D/exam-scripts/raw_checks3.py D/exam-scripts   # PC-04 payload visibility x outcome
uv run python -I D/exam-scripts/os1.py W/l1-units-head.jsonl                    # OS-1 population recount, L1-08 labels (PC-05)
uv run python -I D/exam-scripts/os_build.py                                     # outcome rows, IT0-5 / IT6-13 split
uv run python -I D/exam-scripts/sem_marker.py W/l2-head-j2.partial D/l2-sample-head.json W/l1-units-head.jsonl   # SEM injection markers
uv run python -I D/exam-scripts/exam_build.py                                   # builds D/exam.json
```

Open follow-ups (orchestrator):

| # | What | Command | When |
|---|---|---|---|
| 1 | CC-08 / PC-06: re-run L1 (expect null_final 54) and `l2_check` (native-I and twins separated) | `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-shreeyavarma-cc08 -- uv run python tools/precheck/l1_scan.py --source shreeyavarma-llm-safety --part head --corpus-id shreeyavarma-llm-safety --jobs 2 --emit-fp --git ~/.agentprov/staging/10c/shreeyavarma/llm_safety.git`, then the `l2_check.py` line of section 9 (critic: the current CC-08 `is_twin` does not decode inference-bundle ids (refuted PC-glitch-agentdojo-04, PC-melon-agentdojo-11, refuted PC-hilarytorn-trajectory-poisoning-06), so run the `l2_check` re-run only after that fix) | done by recheck12 (`4a3e40c1`; section 5 Recheck) |
| 2 | PC-01 shape test and PC-02 payload test over `agentdojo-upstream` head local dirs, `ast-survey-agentdojo`, `yockcheng-prompt-injection-harness` and the other agentdojo-format corpora | light raw reads (adapt `raw_checks.py` / `raw_checks2.py`) | before the round; decides two cross-cutting items |
| 3 | H16 and `payload_not_reaching_agent` on the regenerated population (expect outcome_only 2 with 0 judgements; detector count 123) | stats over the regenerated corpus | after the round |
