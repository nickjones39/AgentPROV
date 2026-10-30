# Pre-check dossier: `autogen-guard-placement`

## 1. Header

| | |
|---|---|
| Corpus | `autogen-guard-placement` (own corpus; data CC-BY-4.0, code MIT) |
| Parts | `autogen-guard-placement · v1.0` (1 part; 14 `runs.jsonl` members imported whole) |
| Family / profile | `autogen` / `autogen-guard-placement@1` (dialect `autogen.runs`, variants team/condition/defense/injecagent; semantics `autogen.tools@1`) |
| Pin | Zenodo 23025259 v1.0, `autogen-guard-placement-data-code-v1.0.zip`, 4,978,620 B, sha256 `af2f5193…7b63` (verified) |
| Code commit | `d97d3a57` (L1 and L2, batch `wave6`, all steps rc 0, tracked_changes false) |
| Kind | wave 6, first examination; never stored |
| Date | 2026-10-14 (prereg, research), 2026-10-16 (batch), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), examiner (this dossier), adversarial verifier (2026-10-21: 8 confirmed, 0 refuted, PC-08 added) |
| Data | [`data/autogen-guard-placement/`](data/autogen-guard-placement/): `research.json`, `l1-v1.0.json`, `l1-09/10-v1.0.json`, `l2-sample-v1.0.json`, `l2-v1.0.json`, `code-v1.0.json`, `exam.json`, `findings.json`, `raw-census.json`, `l2-outcomes.json`, `outcomes.json`, `dup-groups.json`, `acct-screen.json`, `sk-shape.json`, `exam-scripts/` |

- Code identity, part `v1.0` ([`code-v1.0.json`](data/autogen-guard-placement/code-v1.0.json)): commit `d97d3a57` (tracked_changes false); engine code expand `3b1d412bb77a`, aer `856b7a09e0cf`, sem `7cc76710f35d`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `autogen.runs@0.1.0` `a50ea9d58039`; profile sha256 `1a7573f4e88a`; rules aer 1 / autogen 1 (`55b64d5e05ba` / `2b7fb400c09b`); sem profile `autogen.tools@1` `1191cf5531c9`; prov rules `79b0a1e78dc7`; lockfile `b0455f1058c8`; limits `5d6dbb210259`; Python 3.14.8.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Data record | https://zenodo.org/records/23025259 (concept 23025258; 1 version; md5 only) | the pin |
| Repository | https://github.com/rezaduty/autogen-guard-placement (2 commits; HEAD `1da92ac7`; 0 issues/tags) | paper LaTeX, `src/analyze.py` (metric), `macros.tex` (reference numbers) |
| Paper | LaTeX in the repository only; no arXiv/DOI listing found | outcome reference (`M:` macros, `T:` tables) |
| Harness | AutoGen 0.7.5 (`microsoft/autogen` python-v0.7.5 = `83afbf58`) | producer (D-303) |

Data-versus-paper notes (checked against the data): the deposit has 220 off-test phase-2 rows the paper's tables filter out and 240 phase-2 rows from an earlier harness revision (no `stop_reason`), one time block (PC-05); every paper cell reproduces from the raw rows (section 6); all message times fall after the phase-0 capture (L-05 resolved, 0 before).

## 3. Expectations

Pre-registration: [`prereg/autogen-guard-placement.md`](prereg/autogen-guard-placement.md) (2026-10-14, before any data check). Amendments 2 and 4 apply (whole part imported; D-529 not used). Classes follow R1-R6 and CC-01..CC-11 of [`cross-cutting.md`](cross-cutting.md).

| H | Result | Note |
|---|---|---|
| H-01 | partial | 109 members, 0 `paper/`, 0 `runs_errors`; 14 `runs.jsonl` sizes = HEAD tree; blob ids computed, not compared (follow-up 1) |
| H-02 | supported | 14 files, 1,270 rows, per-file run rows as expected, 190 non-run (150/20/20), `run_id` unique 1,080 |
| H-03 | supported | p2 = 85 probes × 4 entries; 120 test, 220 off-test; 0 off-test in other phases |
| H-04 | supported | 240 rows without `stop_reason`, all p2, 2026-09-24 13:31:35-17:23:33Z; first row with it starts 17:23:47 |
| H-05 | supported | 6,107 timestamps in [09-24T13:31:35, 09-25T12:36:20]; 0 before the capture, 0 outside the window |
| H-06 | supported | 0 errors file; `error` null 1,080/1,080 |
| H-07 | supported | 267 ThoughtEvents (writer 229, researcher 38); p2 99, p3 30, p4 8, p5 4, p6 16, p10 44, p12 36, p13 30 |
| H-08 | supported | p12 no `modes` (160); no `block_guard` in p10/12/13; `llm` 630 |
| H-09 | supported | entries 345/255/255/225; modes 560/180/120/60; stops 760/80/240; joins 830/170/80 |
| H-10 | supported | 6/2/5/3 runs with an attacker call; 28 calls (9/4/10/5) |
| H-11 | supported | 23/23 cells exact, 111/230 (prereg says 240, PC-08; PC-03 for the unfiltered SEM count) |
| H-12 | supported | p10 early stop 40/0/40/0/0/0; 40 `outcome_only` = user + agent × observe + model block |
| H-13 | supported | 0 canary hits in 694 benign runs |
| H-14 | supported | 0 failures, 0 degenerate, 0 `adapter_defect`; 588/87/49/40/4/3 (executions; occurrences 139/69, PC-07) |
| H-15 | supported | 1,120 tool executions, all with a call; 4 `invalid` |
| H-16 | refuted (raw store) | 0 account paths in all 109 members; 0 secrets in rows and AER/SEM/PROV; 2 sk-shaped strings in a not-selected raw-store member: 1 synthetic, 1 real-format Langfuse key (PC-01) |
| H-17 | refuted as worded | 1 group spans 11 probes (p4 bus-block replacement), by design (PC-06) |
| H-18 | supported | 3,291/3,291 files identical; recompute 1,080 identical; chain 0 failed |
| H-19 | supported | 190 line-level register rows, 0 file-level (docs stale, PC-04) |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: the staged zip (pin verified), `l1_scan` at `d97d3a57`, 2.9 s.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 109 walked = 14 selected + 27 auxiliary + 2 context + 66 not selected; 0 excluded/rejected; units 1,080 = registry = census; 190 non-run rows (p7 150, p8 20, p9 20) | as expected |
| L1-02 parse | strict ok 14/14 run files, 29/29 auxiliary | as expected |
| L1-03 encodings | 0 bidi, tag, zero-width, C1, U+FFFD, mojibake; `json_in_string` 2,296 strings (tool-call arguments 1,120, texts 1,148, results 28); `escaped_newline` 2 strings / 1 file; auxiliary variation selector 36 (benchmark text) | as expected |
| L1-04 duplicates | byte-identical 0; trajectory-identical (CC-01) 55 groups / 149 units, 54 within one probe × entry (31 across phases), 1 across 11 probes (PC-06); cross-part and cross-corpus 0 (`_cross/l1-xdup.json`) | H-17 refuted as worded |
| L1-05 arms | 14 strata (phase × arm); all design cells present; absences as prereg §2 (bus block only user/agent in p4; tool block only tool entry; p3-13 only on test carriers); extras: 220 off-test p2 rows | as expected |
| L1-06 secrets/paths | 0 of 14 run files and 29 auxiliary. Full screen of all 109 members (`acct.py`): 0 account paths; 2 sk-shaped strings in `results/phase7/capture.json` (not selected) | PC-01, PC-02 |
| L1-07 timestamps | `/messages/*/raw/created_at` 6,107, all `Z`, 1,080 units, 0 non-monotone, 09-24..09-25; `/events/*/timestamp` 602 naive (phase-7 rows) | as expected |
| L1-08 degenerate | flags {} over 14 files and 1,080 units; 40 runs with no agent turn are p10 `outcome_only` by design | as expected |
| L1-09 / L1-10 | L1-09 skipped (no metadata members); L1-10 0 non-JSON context files | n/a |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`l2-sample-v1.0.json`](data/autogen-guard-placement/l2-sample-v1.0.json): whole part, 14 files (phases 7-9 have no executions) |
| Import | j2 (389 s) and j1 (619 s) at `d97d3a57`; 1,080 executions (1,040 `agent_execution`, 40 `outcome_only`); ok 1,040, ok_with_issues 40; 0 degenerate, 0 `adapter_defect`, 0 unreadable; register 190 line-level rows |
| Validation | tiers aer, sem, prov, linkage: 1,080/1,080 pass, reproduced 1,080, linkage 100 %; SHACL not implemented; regression n/a |
| Recompute | `--dry-run` 1,080 identical, 0 unexplained |
| Verify chain | 0 failed; only `checksums.absent` (partial working tree); no withholding, so no sealed copy needed |
| Determinism | j2 vs j1: 3,291/3,291 files identical, index identical |
| A2 classes | executions: `guard_text_unjoined` 588, `block_effect_in_request_log` 87, `block_subject_not_recorded` 49, `no_execution_observed` 40, `tool_error_result` 4, `aborted_attempt_events` 3 (seal occurrences 139 / 69 for the two block codes) |
| A3 PROV | 0 issues over 653,223 statements / 915,647 relation arguments; 4,280 messages with `generated_by`, 3,149 model calls with input, 1,120 tool executions with call |
| Records | model calls 3,280, tool executions 1,120 (4 `invalid`), messages 5,615, decisions 176 (I), judgements 38,183 (O), fixtures 4,586, activities 225: equal to the in-memory §7.1 |
| Evidence classes | AER actor D 737 / I 5,831 / O 2,120; fixture D 1,466 / I 1,080 / O 2,040. PROV core D 64,916 / O 64,943; inference I 193,570; assessment D 546 / I 16,383 / O 2,160. Twin / native / mixed `_unverified` statements: 0 / 230,290 / 0 (every `_unverified` rule is native: config model, harness, request log, task template) |
| SEM | `canary_present` 250 (D), `attacker_tool_called` 28 (D), `keyword_stop` 210 (I; holds 80), `injection_marker` 512 (D) |
| Identity | actors researcher 1,040, writer 1,000, selector 80, ingest 255, harness `autogen-agentchat`, guards `deberta`/`llm` 870 each, `keyword` 210; model `qwen/qwen3.5-9b` for 1,040, unresolved 40 (the `outcome_only` runs, no model call); served `not_recorded`; defence ids from settings (I): none 560, `prompt:spotlight`/`sandwich` 80 each, block placements as designed; 0 direct mismatches |
| Raw vs mapped | 1,080/1,080 joined by member sha256 + line; any-canary 0 mismatches; attacker calls 28 = 28; keyword stop 0 differ |
| Redaction | 3,248 AER/SEM/PROV files, 0 hits |
| Withholding | no policy in the profile |

## 6. Outcome comparison

Population = whole part (L1 raw and L2 mapped are the same 1,080 runs). Paper = `macros.tex`/tables at `1da92ac7`. Gap rule: > 15 pp on n ≥ 20, or the paper outside the Wilson 95 % interval by > 5 pp. Full rows: [`outcomes.json`](data/autogen-guard-placement/outcomes.json). Mapped column = SEM `canary_present` filtered by the fixture's goal kind (output: the last writer text).

| Arm (test carriers, attack) | n | Raw rate (Wilson 95 %) | Mapped | Paper | Gap (pp) | Verdict |
|---|---:|---|---:|---:|---:|---|
| p2 observe, all entries (t/u/a/m 4/10/10/5) | 40 | 72.50 [57.17, 83.89] | 29 | 29 (72.50) | 0.00 | match, 4/4 cells |
| p3 model block (0/0/0/2) | 40 | 5.00 [1.38, 16.50] | 2 | 2 | 0.00 | match |
| p4 bus block user/agent (0/0) | 20 | 0.00 [0, 16.11] | 0 | 0 | 0.00 | match |
| p5 tool block (0) | 10 | 0.00 [0, 27.75] | 0 | 0 | 0.00 | match (n < 20) |
| p12 spotlight (2/7/8/6) | 40 | 57.50 [42.20, 71.49] | 23 | 23 | 0.00 | match |
| p12 sandwich (4/9/10/5) | 40 | 70.00 [54.57, 81.93] | 28 | 28 | 0.00 | match |
| p13 selector (4/10/10/5) | 40 | 72.50 [57.17, 83.89] | 29 | 29 | 0.00 | match |
| Team total | 230 | 111 (48.26) | 111 | 111 (`HandBreaches`) | 0 | match (n is 230, not the prereg's 240: PC-08) |
| p6 attacker tool: none / model / bus / tool | 20 each | 30.0 / 10.0 / 25.0 / 15.0 | 6/2/5/3 | 6/2/5/3 | 0.00 | match |
| p10 early stop: observe / control / model / bus / tool / writer-only | 40/40/40/40/10/40 | 100 / 0 / 100 / 0 / 0 / 0 | same | 40/0/40/0/0/0 | 0.00 | match |
| p2 benign, any canary | 224 (80 test) | 0.00 [0, 1.69] | 0 | 0 | 0.00 | match |
| info: SEM any `canary_present` (unfiltered) p2 / p12 spot / p12 sand / p13 | 40 each | 30 / 26 / 29 / 31 | — | 29 / 23 / 28 / 29 | +2.5 / +7.5 / +2.5 / +5.0 | not the paper metric (PC-03); no flag |
| info: p2 off-test attack t/u/a/m | 19 each | 11 / 19 / 19 / 6 | same | no paper number | — | report only |

0 flagged gaps. The prereg's exact-match rule holds in every cell; the one difference investigated (7 test-carrier runs under an unfiltered SEM count) is a metric-definition issue, PC-03.

CC-07 (#181/#161): not applicable. This is not an AgentDojo-format corpus: the outcome is the deposit's canary and attacker-tool match, and no AgentDojo suite checker runs (0 banking or `user_task_5` executions, so the count is 0/0 for both).

## 7. Findings

Verifier pass 2026-10-21 (adversarial): every reproduction re-run or recounted (raw.py and dupgrp.py outputs byte-identical to the committed JSON; masked context of the PC-01 strings read through `quote_untrusted`, values never printed). 8 confirmed, 0 refuted; PC-01 reworded, PC-07 recommendation corrected, PC-08 added.

| Id | Title | Class | Sev. | Sec. | Verifier | Recommendation |
|---|---|---|---|---|---|---|
| PC-01 | 2 sk-shaped strings in raw-store member `results/phase7/capture.json` `/input_rail_yaml`: `<account-A>` is synthetic (canned `secret_leak` response, impossible key length); `<secret-A>` is a real-format Langfuse secret key (`sk-lf-` + UUIDv4, paired `pk-lf` `a41d85a7`, `observability.langfuse`, localhost:3300, disabled), synthetic not established; not selected; 0 in AER/SEM/PROV | source-defect (CC-13 real-format secret of the source's own infrastructure; CC-11 analogue; reclassified 2026-10-21 from S2) | S0 | yes | confirmed (reworded: not both OpenAI-shaped) | orchestrator now; allowlist `<account-A>` by digest; user decision for the Langfuse pair (withhold the member at seal with digests kept, or allowlist with a localhost-only rationale) |
| PC-02 | L1-06/L1-10 skip not-selected archive members though the raw store keeps the whole zip (66/109) | analysis-artefact (R5) | S3 | no | confirmed | raw-store-wide screen for archive-mode parts |
| PC-03 | SEM `canary_present` is a location claim (matches spec D.22.6) and ignores goal kind; unfiltered 118/230 vs 111; filtered = 111 exactly | documentation-mismatch (R4) | S3 | no | confirmed | state the consumer rule in D-306/D.22.6 or a run-level claim later; manuscript uses 111/230 |
| PC-04 | Registry caveat, profile header and `non_run_rows` text describe the pre-D-321 state (L-07); still so at `34fd4cbc` | documentation-mismatch (R4) | S3 | no | confirmed | family owner, with the registry status change; regenerate README |
| PC-05 | 220 off-test p2 rows and 240 earlier-harness rows (one time block), not in the paper's tables | documentation-mismatch (R3) | S3 | no | confirmed | disclose; filter to test carriers when comparing; no exclusion |
| PC-06 | 1 trajectory group spans 11 probes (p4 bus-block replacement) | expected-known (D-304) | S3 | no | confirmed | no action; dedup must not merge |
| PC-07 | Catalogued quirks reproduce; L-08: index counts executions (87/49), seal counts occurrences (139/69) | expected-known (R2) | S3 | no | confirmed (recommendation corrected) | the two block entries have no expected count; fix the unit in `docs/reports/phase10n/README.md` line 351 |
| PC-08 | Team attack denominator is 230 (23 cells), not 240 (prereg §3 line 89, `os.py` constant); the paper states no denominator | documentation-mismatch (R4) | S3 | no | added by verifier | use 111/230 (48.3 %) in datasheet and manuscript |

Proposed `artefacts.toml` entries (text only, to the autogen family owner): `autogen.art.rail_config_key_shapes` (PC-01) and `autogen.art.offtest_phase2_rows` (PC-05); wording in `findings.json`. AGENTS.md §12: raw-store screens must cover not-selected archive members (PC-01/PC-02); PC-01 is S0 security under CC-13 (the Langfuse key pair is a real-format secret of the source's own infrastructure, not a fixture): withhold-or-allowlist decision before any seal.

## 8. Recommendations and readiness

1. PC-01 goes to the orchestrator at once (security, user rule of 2026-10-15; S0 under CC-13 since 2026-10-21). One string is synthetic; the other is a real-format Langfuse key pair for a localhost instance and needs a user decision (withhold the member at seal or allowlist). It does not affect the import: no AER/SEM/PROV statement holds the strings. It does affect the deposit at seal.
2. PC-03/PC-08: datasheet and manuscript breach rates from SEM must filter by goal kind and use the final writer message, over 230 test-carrier attack runs (111/230). The family owner documents this rule.
3. PC-04/PC-07: docs and catalogue counts go to the family owner together with the registry status change at the round.
4. PC-05: disclose. Nothing is excluded: the off-test and earlier-harness rows stay in, and so do the arms with zero breaches.

**Readiness: `blocked`** until the PC-01 withhold-or-allowlist decision (changed 2026-10-21: CC-13 classes the Langfuse key pair as a real-format secret of the source's own infrastructure, S0 security, and the member sits in the raw store that a deposit would release). The import itself is not affected. The import is complete, faithful and deterministic: 1,080/1,080 mapped, validation passes, recompute finds 0 differences, j1 and j2 are byte-identical, and every paper cell reproduces exactly (raw and mapped). The caveats were PC-01 (security, verified, now the S0 block above: one real-format Langfuse key pair awaits a withhold-or-allowlist decision; it touches the raw store and the deposit, not the import) and the S3 doc items, including the 230 denominator (PC-08). PC-02 is not counted (R5). Verifier: readiness `ready-with-caveats` confirmed before the CC-13 reclassification; 0 outcome gaps.

## 9. Reproduction

W = `~/.agentprov/migration-work/precheck/autogen-guard-placement`, D = `docs/reports/precheck/data/autogen-guard-placement`, Z = `~/.agentprov/staging/10e/zenodo_23025259/autogen-guard-placement-data-code-v1.0.zip`.

```bash
# batch wave 6 (as run): l1, l1_09, l1_10, sample, import_j2, import_j1, check
uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-wave6 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave6.toml
# examiner (read-only)
uv run python -I D/exam-scripts/raw.py Z W/exam/raw.json W/exam/rows.jsonl     # -> D/raw-census.json
uv run python -I D/exam-scripts/dupgrp.py Z W/exam/dupgrp.json                  # -> D/dup-groups.json
uv run python -I D/exam-scripts/acct.py Z W/l2-v1.0-j2.partial W/exam/acct.json # -> D/acct-screen.json
uv run python -I D/exam-scripts/skshape.py Z W/exam/skshape.json                # -> D/sk-shape.json
python3 -I D/exam-scripts/sem.py W/l2-v1.0-j2.partial W/exam/rows.jsonl W/exam/sem.json  # -> D/l2-outcomes.json
python3 -I D/exam-scripts/os.py W/exam/raw.json W/exam/sem.json D/outcomes.json
```

Follow-ups (not run): (1) H-01 blob ids: `gh api 'repos/rezaduty/autogen-guard-placement/git/trees/1da92ac7?recursive=1' --jq '.tree[]|select(.path|startswith("results/"))|[.path,.sha]'` compared with `raw-census.json` `git_blob_12`; (2) a raw-store-wide secret and account screen of every archive member for all archive-mode parts (tool change, heavy); (3) PC-01 user decision on the Langfuse pair (verifier done); (4) optionally, `uv run agentprov verify --corpus <sealed copy> --level chain`.
