# Pre-check dossier: `openagentsafety`

## 1. Header

| | |
|---|---|
| Corpus | `openagentsafety` (MIT, LICENSE at the pin; HF task definitions CC-BY-4.0) |
| Parts | `head` (1 part, single stratum key `model`) |
| Family / profile | `openhands` / `openagentsafety@1` (dialect and mapper `openhands.events`, variant `oas-0.28`, semantics `openhands.tools@1`) |
| Pin | git `sani903/OpenAgentSafety` @ `857798ff` (2026-08-10T05:38:08Z), 14,887 blobs (7,822 PNG absent) |
| Code commit | `d97d3a57` (L1 and L2, batch `wave5`, all steps rc 0, tracked changes false); examination at `34fd4cbc` |
| Kind | wave 5, first examination (not in FA or E2); no stored corpus |
| Date | 2026-10-14 (prereg), 2026-10-16 (L1, L2), 2026-10-21 (examination) |
| Agents | researcher and fact-checker (prereg), examiner (this dossier); adversarial verifier 2026-10-21 (10/10 confirmed, PC-07 counts corrected) |
| Data | [`data/openagentsafety/`](data/openagentsafety/): `research.json`, `l1-head.json`, `l1-10-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `findings.json`, `os1-population.json`, `os2-sample.json`, `l1-06-accounts.json`, `exam-scripts/` |

- Code identity, part `head` ([`code-head.json`](data/openagentsafety/code-head.json)): commit `d97d3a57` (tracked_changes false); engine code aer `856b7a09e0cf`, sem `6016a8ab0faa`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `openhands.events@0.1.0` `bf187e8841a3`; profile sha256 `b5be1d99df75`, rules aer 1 / openhands 1; lockfile `b0455f1058c8`, limits `5d6dbb210259`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Repository | https://github.com/sani903/OpenAgentSafety @ `857798ff` | the data (`evaluation/<model>/{traj,eval,state}_*.json`, judge summaries) |
| Paper | arXiv [2507.06134](https://arxiv.org/abs/2507.06134) v1/v2 (ICLR 2026) | outcome reference: v1 Tables 4/6 (= v2 Tables 3/5) |
| Maintained copy | https://github.com/Open-Agent-Safety/OpenAgentSafety | same 1,560 trajectory blobs; 81 evaluators fixed (PR #4) |
| Issues | sani903/OpenAgentSafety [#5](https://github.com/sani903/OpenAgentSafety/issues/5) | evaluator defects at the pin |
| Harness | OpenHands fork `adityasoni9998/OpenHands@5a13eacf` (openhands-ai 0.28.1) | producer; mocked function calling for models outside its support list |

Data-versus-paper notes:

- For gpt-4o, deepseek_v3 and deepseek_r1 the judge summaries reproduce every paper cell (H2). Claude and o3-mini do not: the Claude summary has 165 entries where the paper's N is 347, and o3-mini has no summary (PC-03).
- The paper's denominators are the state-file population. The 145 state-only runs (no trajectory) are all in their summaries with `Label: -1` (H4). Over the 1,560 released trajectories, the vulnerable-state rates therefore equal the paper's and only the failure rate is lower (section 6).
- The rule-based scores come from the pre-fix evaluators (issue #5): 176 eval files with 0/0, and 8 evaluators with no aggregator (PC-02).
- `max_iterations=100` (132 runs) and the deepseek `toolu_NN` call ids show harness behaviour that the pinned scripts do not document (PC-06, PC-05).

## 3. Expectations

Pre-registration: [`prereg/openagentsafety.md`](prereg/openagentsafety.md), committed in `fd75f8a3` before any data check. Amendments 2.2 (two-level outcome sanity) and 2.4 (one stratum, 30 units) apply. Classes follow R1-R6 and CC-01..CC-11 of [`cross-cutting.md`](cross-cutting.md). CC-07 (#181/#161) does **not** apply: this is not an AgentDojo-format corpus.

| H | Result | Note |
|---|---|---|
| H1 | supported | 1,560 = 289/316/322/321/312; 352 tasks; coverage 211×5, 101×4, 25×3, 11×2, 4×1 (missing 63/36/30/31/40) |
| H2 | supported | gpt-4o / v3 / r1: entries 351/350/352, -1 158/162/172, 0 66/71/67, unsafe 127/117/113, rule 1 63/61/59, disagree 11/13/12 |
| H3 | supported | Claude summary 165 entries; no o3-mini summary (PC-03) |
| H4 | supported | state-only runs r1 36, v3 28, gpt-4o 30: 100 % in the summary with rule -1; Claude 4 of 14 in its summary (all rule -1) |
| H5 | refuted | Claude 5/165 entries disagree with the eval-file mapping (PC-04); r1, v3, gpt-4o 100 %; gpt-4o tallies -1 91 / 0 152 / 1 108 as census |
| H6 | partly refuted | (a) 176 0/0 files on 44 tasks, all-or-nothing (proxy, supported); (b) 8 evaluators without `grade_checkpoints`, 26/26 runs without eval (proxy, supported); (c) refuted: bug-reports 4/5 1/1, logs 0/2; (d) not tested (issue lists not recorded) (PC-02) |
| H7 | supported | `max_iterations` 100: gpt-4o 130, claude 2 (100 % in 2 dirs) (PC-06) |
| H8 | supported (sample) | `toolu_NN` ids deepseek 145/145, others 0/600; population not tested (follow-up) (PC-05) |
| H9 | supported | 45,832 naive timestamps, 0 non-monotone runs, dates 2025-05-05..05-10; sample latest per model within the bounds |
| H10 | supported where tested | 0 empty or zero-event files; sample: first event user message 30/30, finish 19/30, notice last 3; population 418/168/2 not re-tested |
| H11 | refuted | 15 named account paths (0 operator) in 18 trajectories (PC-01); the secret total is not comparable (pattern sets differ) (PC-07) |
| H12 | supported | 0 byte-identical, 0 trajectory-identical, 0 cross-corpus overlaps |
| H13 | supported | 89/89 AER judgement values equal their source pointer; served ids equal the dir's id 30/30 |
| H14 | supported | every population register rate lies inside the sample's Wilson 95 % interval (PC-08) |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

| Check | Result (denominator) |
|---|---|
| L1-01 | walked 14,887: selected 1,560, auxiliary 4,284 (3,228 JSON scanned), not selected 1,218, absent PNG 7,822, stray 3; units 1,560 = registry 1,560 |
| L1-02 | strict ok 1,560/1,560 trajectories, 3,228/3,228 auxiliary |
| L1-03 | browser and tool text: mojibake 272, bidi 17, zero-width 2, C0 1, ANSI/ESC 4, PUA 1, variation selectors 21 artefacts; `json_in_string` 1,560 (tool-call `arguments`, by design) |
| L1-04 | byte-identical 0, trajectory-identical 0 (1,560 distinct fingerprints); `_cross/l1-xdup.json`: 0 groups with openagentsafety |
| L1-05 | 5 strata (one per model dir); 352 tasks; no defence or attack facet (D-171) |
| L1-06 | secret-like 301 artefacts; named account paths 18 (home-dir 11, users-dir 3, tilde 1 distinct), generic 2; aux JSON (state files) 303 + 75 + 3 named strings. Classified in `l1-06-accounts.json` (PC-01) |
| L1-07 | `/*/timestamp` 45,832 naive, `created` 39,368 epoch; 0 parse failures, 0 non-monotone |
| L1-08 | 0 empty, 0 zero-event, 0 unit flags beyond L1-06 |
| L1-09 | not applicable (no archives) |
| L1-10 | 1,056 non-JSON task files: 9 with a hit, 2 named home-dir digests (both benchmark text: a task.md path and an evaluator.py regex), operator 0 |

## 5. Level 2

- Sample: [`l2-sample-head.json`](data/openagentsafety/l2-sample-head.json), 30 labels (6 per model), sha256 `65c2c366…`. All 30 imported (1 execution per label).
- Validate (aer, sem, prov, linkage): 30/30 passed; shacl not implemented (skipped); regression n/a; linkage 100 %. Recompute dry run: 30 identical, 0 unexplained. Determinism: j1 vs j2, 273/273 files byte-identical, index identical. Verify chain: ok, apart from `checksums.absent` (an unsealed working tree, expected).
- Status: ok 26, ok_with_issues 4; adapter_defect 0, degenerate 0. Register codes: filtered_events 30, task_text_not_seen 25, content_not_inlined 7, eval_missing 4, summary_entry_missing 3, not_executed_notice 3, unexecuted_tool_call 3, no_outcome_recorded 1. Only catalogued codes appear; no PI classes.
- A3: 3 unexecuted call parts, represented; 80,821 statements and 122,039 relation arguments checked.
- Evidence (statements): core D 5,686 / O 2,641 / none 363; inference I 32,885 (native `_unverified` 32,833 + 100 none); assessment I 30,516 (41 native) / O 60; top O 6,737. Twin 0, mixed 0, native 32,974.
- Identity: claude-sonnet → `claude-3-7-sonnet-20250219`, deepseek_r1 → `deepseek-reasoner`, deepseek_v3 → `deepseek-chat`, gpt-4o → `gpt-4o-2024-08-06`, o3-mini → `o3-mini-2025-01-31` (6 each, 0 mismatches). Defence and attack are none. Suite is unresolved in 30 (the design has no suite facet). Judge actors are `oas_checker` (evaluator.py) and `oas_llm_judge` (llm_as_judge.py, model not recorded).
- H8: the deepseek agent messages and model calls are class O with args D (D-173), but their tool calls carry `toolu_NN` ids minted by the fork's converter (PC-05).
- Redaction: AER has 10 account-path strings in 1 execution (safety-api-in-codebase, gpt-4o; third-party web content, PC-01). Openai-style secret shapes appear in AER (93 strings, 2 executions) and PROV `apv:args` (20, 1 execution), as D-179 option A allows (PC-07). Operator hits: 0.
- Withholding: no policy, nothing withheld (as expected).

## 6. Outcome comparison

Population (L1, judge summaries; the paper's denominators: unsafe / rule / disagree over label ≠ -1, failure over all judged runs). Wilson 95 %.

| Model | Metric | n | Release | Paper | Gap (pp) | Verdict |
|---|---|---:|---|---:|---:|---|
| gpt-4o | judge unsafe | 193 | 65.80 [58.86, 72.13] | 65.80 | 0.00 | reproduces |
| gpt-4o | rule unsafe / disagree / failure | 193/193/351 | 32.64 / 5.70 / 45.01 | 32.64 / 5.69 / 45.00 | ≤0.01 | reproduces (truncation) |
| deepseek_v3 | judge / rule / disagree / failure | 188/188/188/350 | 62.23 / 32.45 / 6.91 / 46.29 | 62.23 / 32.44 / 6.91 / 46.30 | ≤0.01 | reproduces |
| deepseek_r1 | judge / rule / disagree / failure | 180/180/180/352 | 62.78 / 32.78 / 6.67 / 48.86 | 62.78 / 32.78 / 6.67 / 48.90 | ≤0.04 | reproduces |
| claude-sonnet | judge unsafe | 99 | 44.44 [35.05, 54.26] | 51.20 (N 347) | -6.76 | not flagged (interval includes); denominator mismatch PC-03 |
| claude-sonnet | rule / disagree / failure | 99/99/165 | 35.35 / 13.13 / 40.00 | 32.85 / 9.17 / 40.30 | +2.50 / +3.96 / -0.30 | not flagged |
| o3-mini | all judge metrics | 0 | no summary | 72.73 / 32.32 / 6.57 / 43.30 | — | not testable (PC-03) |

Over the released trajectories (1,560 frame; R6, not findings), the vulnerable-state rates are identical to the table above, because every state-only run is `Label: -1`. Failure rates are gpt-4o 39.88 [34.67, 45.32], v3 41.61 [36.36, 47.07], r1 43.04 [37.69, 48.55] and Claude 38.51. The gap rule is not met: the r1 interval excludes 48.90 by 0.35 points, below the 5-point threshold.

Sample (L2, mapped AER values; n = 6 per model, below 20, so Wilson only, never a verdict): judge unsafe claude 1/2, r1 1/2, v3 4/4 [51.0, 100], gpt-4o 5/6 [43.7, 97.0]. Failure: gpt-4o 0/6 [0, 39.0] against the paper's 45.0. o3-mini has no judge values. Rule checkpoints: final 1/1 11, 0/1 10, 0/0 5 of 26 with eval. Mapping check: 89/89 judgement values equal the raw source (H13).

## 7. Findings

| Id | Title (short) | Class | Sev | Sec | Verdict |
|---|---|---|---|---|---|
| PC-openagentsafety-01 | Third-party named account paths in 18 trajectories (AER) and their state files; 0 operator (CC-03/CC-11) | source-defect (CC-12b) | S2 | **yes** | confirmed |
| PC-openagentsafety-02 | Pre-fix evaluators (issue #5): 176 0/0 eval files on 44 tasks, 8 evaluators with no aggregator | source-defect | S2 | no | confirmed |
| PC-openagentsafety-03 | Paper's Claude / o3-mini judge numbers not reproducible from the release | documentation-mismatch | S2 | no | confirmed |
| PC-openagentsafety-04 | Claude summary: 5 rule scores inconsistent with the eval files | source-defect | S3 | no | confirmed |
| PC-openagentsafety-05 | DeepSeek mocked function calling (`toolu_NN`), recorded as O (D-173 question) | source-defect | S3 | no | confirmed |
| PC-openagentsafety-06 | `max_iterations=100` in 132 runs, not producible by the pinned harness | documentation-mismatch | S3 | no | confirmed |
| PC-openagentsafety-07 | Secret-like benchmark strings in AER/PROV (D-179) | expected-known (D-179, CC-13 fixture: openai-style shapes in PROV `apv:args`; reclassified 2026-10-21 from S3, no) | S2 | **yes** | confirmed |
| PC-openagentsafety-08 | Catalogued register codes consistent with the population (R2) | expected-known | S3 | no | confirmed |
| PC-openagentsafety-09 | Census and prereg label text "Label: Label" is really "Label: Label: 2" (R4) | documentation-mismatch | S3 | no | confirmed |
| PC-openagentsafety-10 | No openhands outcome hook in L1 / l2_check (R5) | analysis-artefact | S3 | no | confirmed |

Evidence, reproduction and recommendations: [`findings.json`](data/openagentsafety/findings.json). PC-01 is security-relevant and goes to the orchestrator at once. It is proposed as S2, following the CC-11 precedent: the paths are public third-party content inside the benchmark environment (OpenHands tracebacks, bustub build logs, forum pages), not the operator's account or the harness host. Verifier ruling: CC-11 governs, S2 stands. The state files' 16 account digests are a subset of the trajectory set (0 new), and every third-party digest sits in browse/run observation content or one model message, never in harness metadata, so none is the operator's or this harness host's account. They are still real third-party developer names (one a macOS `/Users` path in a 2024-09-30 OpenHands debug log), which is why the decision goes to the orchestrator (CC-11 precedent: withhold raw-store files). CC-12 (b) (adopted 2026-10-21) settles the class: developer paths inside public third-party content the agent fetched are source-defect S2, security, with a disclosure and an owner check by digest.

Proposed `artefacts.toml` entries (text only, to the openhands family owner):

```toml
# [[artefact]] id = "openhands.art.third_party_account_paths"   # PC-01: 18 executions (15 named digests, 0 operator)
# [[artefact]] id = "openhands.art.oas_evaluator_defects"       # PC-02: 176 eval files 0/0 (44 tasks) + 26 runs on 8 tasks without aggregator; refs #5, PR #4
# [[artefact]] id = "openhands.art.judge_eval_inconsistent"     # PC-04: 5 executions (claude-sonnet)
# [[family.openhands.quirk]] id = "openhands.mocked_fn_calling"  # PC-05: deepseek_r1 + deepseek_v3, 638 runs; sample 145/145 toolu ids
```

AGENTS.md section 12 items: PC-01 (redaction decision pending), PC-05 (D-173 class question), PC-07 (CC-13: D-179 fixture shapes in PROV `apv:args`, S2 security; `release_scan` allowlist entries by digest before sealing).

## 8. Recommendations and readiness

**ready-with-caveats** (verifier: confirmed). L2 is clean: validation, recompute and determinism pass, 0 adapter defects, and the mapping check is 89/89. Three of the five models reproduce the paper exactly at the population level.

Caveats:
1. PC-01 needs an orchestrator decision (disclose, redact or withhold) before sealing.
2. Disclose PC-02 and PC-03 in the datasheet: the rule scores come from pre-fix evaluators, and the Claude and o3-mini rates cannot be reproduced.
3. PC-05 is an owner decision on the evidence class of the deepseek tool calls. It changes AER/PROV digests for 638 runs if accepted.

No data is excluded, including on outcome grounds.

Follow-ups (heavy, not run):
- Population trajectory scan for H8/H10: `toolu` ids in 638 deepseek runs, finish 418, notices 168, uncaused errors 2. A new exam script over 1,377 MB, run through `tools/suite_queue.py --class import --cpu 2 --label precheck-openagentsafety`.
- Full import in the round, to confirm the trial's register counts.
- Record the issue #5 task lists in `research.json` to finish H6(a)/(d).

## 9. Reproduction

```bash
cd docs/reports/precheck/data/openagentsafety
W=~/.agentprov/migration-work/precheck/openagentsafety
uv run python -I exam-scripts/pop.py $W/exam/pop.json            # OS-1, H2-H7 (eval/state/summary/evaluator blobs at 857798ff)
uv run python -I exam-scripts/h5claude.py                         # PC-04
uv run python -I exam-scripts/acct.py $W/l1-units-head.jsonl $W/exam/acct.json   # PC-01 classification (digests only)
uv run python -I exam-scripts/acctctx.py $W/l1-units-head.jsonl <digest ...>     # masked context, examiner only, not stored
uv run python -I exam-scripts/acctaux.py <account-B> <account-J>                # L1-10 digests
uv run python -I exam-scripts/sample.py $W/l2-head-j2.partial $W/exam/sample.json # OS-2, H8, H13
uv run python -I exam-scripts/write_findings.py                   # findings.json, exam.json
# L1/L2 steps: tools/precheck/run_batch.py --plan tools/precheck/plans/wave5.toml (logs in $W/../_batch/wave5/)
```

All git reads go through `exam-scripts/rawread.py` on the bare `~/.agentprov/staging/10g/openagentsafety.git` (`GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file`, no fetch, blob sha1 checked, strict parse via `agentprov.ingest`).
