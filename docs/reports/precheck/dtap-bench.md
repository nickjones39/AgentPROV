# Pre-check dossier: `dtap-bench`

## 1. Header

| | |
|---|---|
| Corpus | `dtap-bench` (Apache-2.0 per both HF cards; no LICENSE/NOTICE in either dataset; policy include, D-29 item 10) |
| Parts | `dtap-bench · head` (1 part) |
| Family / profile | `dtap` / `dtap-bench@1` (dialect/mapper `dtap.trajectory`, semantics `dtap.tools@1`, catalogue `dtap` v1) |
| Pins | HF `AI-Secure/DTap-Bench-Agent-Trajectories` @ `836caf2f` (runs); HF `AI-Secure/DecodingTrust-Agent-Platform` @ `a3edc9b7` (6,682 `config.yaml` context); 2 pinned LFS objects |
| Code commit | `d97d3a57` (L1 and L2, batch `wave5`, all six steps rc 0; tracked changes false) |
| Kind | wave 5, first examination (not in FA or E2; registry `planned`, no stored corpus) |
| Date | 2026-10-14 (prereg, research), 2026-10-16 (L1, L2 batch), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), examiner (this dossier); adversarial verifier 2026-10-21 (12/12 confirmed, corrections to PC-01, PC-04, PC-06, PC-11; verifier scratch `exam/verify/`) |
| Data | [`data/dtap-bench/`](data/dtap-bench/): `research.json`, `l1-head.json`, `l1-10-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `findings.json`, `population.json` (409 pair × split × domain cells), `raw-census.json`, `os2-sample.json`, `windows-crosssplit.json`, `h9.json`, `h13.json`, `h15.json`, `h18.json`, `exam-scripts/` |

- Code identity, part `head` ([`code-head.json`](data/dtap-bench/code-head.json)): commit `d97d3a57` (tracked_changes false); engine code aer `856b7a09e0cf`, sem `99ae2bda881c`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `dtap.trajectory@0.1.0` `265540079b8e`; profile sha256 `04d7c3275399`, rules aer 1 / dtap 1 (dtap `b4df2cb43941`), semantics `dtap.tools@1` `dec908044648`; lockfile `b0455f1058c8`, limits `5d6dbb210259`; Python 3.14.8.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Paper | https://arxiv.org/abs/2605.04808v1 (v1 only) | Tables 3–5, appendix Tables 8–83: the outcome reference (domain values in `research.json`) |
| Runs | https://huggingface.co/datasets/AI-Secure/DTap-Bench-Agent-Trajectories @ `836caf2f` | the data |
| Tasks | https://huggingface.co/datasets/AI-Secure/DecodingTrust-Agent-Platform @ `a3edc9b7` | context (configs) |
| Harness | https://github.com/AI-secure/DecodingTrust-Agent (Apache-2.0) | producer; judge issues [#14](https://github.com/AI-secure/DecodingTrust-Agent/issues/14), [#21](https://github.com/AI-secure/DecodingTrust-Agent/issues/21), [#23](https://github.com/AI-secure/DecodingTrust-Agent/issues/23), [#24](https://github.com/AI-secure/DecodingTrust-Agent/issues/24) |

Data-versus-paper notes, checked against the data:

- The paper's OpenClaw GPT-5.5 and DeepSeek-V4-Pro rows have no runs. The release holds 10 pairs over 7 model directories (PC-08).
- The released macOS and Windows logs do not reproduce the paper's macOS/Windows columns. Benign macOS is 28–29/30 for every pair (PC-02).
- In finance, the paper's numbers equal the **original** (pre-re-judge) `attack_success`, not the stored value: 9 of 12 changed finance cells exactly, 3 within 0.2 pp (PC-06).
- Judge metadata carry LLM-judge keys on 2,693 files (PC-07). The paper calls its judges rule-based.
- Issue #23 (open; one line from it: "guaranteed false positives"): its 12 legal indirect tasks score 89.2%, against 41.8% for the other legal indirect tasks (PC-05).

## 3. Expectations

Pre-registration: [`prereg/dtap-bench.md`](prereg/dtap-bench.md), committed in `fd75f8a3` (2026-10-14), before any check ran. Amendments 2 and 4 apply. Amendment 1 does not, because there is no stored corpus. Classes follow R1–R6 and CC-01..CC-11. **CC-07 (#181/#161) does not apply** because DTap is not AgentDojo format: the family has its own judges and its own catalogue. CC-09 does not apply either, because the `dtap` catalogue is scoped to this profile.

| H | Result | Note |
|---|---|---|
| H1 | supported | 67,808 trajectory files plus 22 judge-only units = 67,830 L1 units. Every pair × split count of prereg §3 is equal. Judges: 65,888 auxiliary + 22 judge-only = 65,910 (65,902 + 8 copies) |
| H2 | supported | strict ok 67,830/67,830 and 65,888/65,888. The 2 LFS pointers were scanned as their pinned objects (sha256 checked). Context configs are not in the L1 frame (duplicate-key config not tested) |
| H3 | supported | 0 GPT-5.5 / DeepSeek runs; 7 model directories |
| H4 | supported | per pair, judge directories are 1,836 direct / 1,986 indirect (gemini indirect 1,984; openaisdk gpt-5.2 1,835 / 1,969; gpt-oss indirect 1,985); gpt-5.1 1,191 / 1,149; openclaw gpt-5.4 600 / 600 |
| H5 | supported | openclaw gpt-5.4 covers finance, legal and **os-filesystem**, 200 per split (no os-filesystem direct_prompt) |
| H6 | **refuted** | 23/384 cells (6.0%) are > 15 pp (micro), 28 by category macro. 3 cells are > 30 pp, all macOS (PC-02) |
| H7 | supported | medical direct_no_attack is within 0.5 run of Table 82 for 7 pairs. gpt-5.4 is 35 against 36.2 (1.2 runs, within the 2-run allowance) |
| H8 | supported | direct_prompt finance is 0/200 for 8 pairs and 2/200 for Gemini (Table 64 has 0.0 / 2.5). Legal equals Table 72 exactly. The census excess is Windows only (+8..+22 pp; PC-02) |
| H9 | **refuted** | the original values are closer in 17 of 23 changed cells, and every finance cell equals the paper with the originals (PC-06) |
| H10 | supported | llm_judge/llm_model on 751 files, gpt_model on 1,942. The keys are on research, CS and travel judges, not medical (PC-07) |
| H11 | **refuted** | named accounts appear in harness-config tool state (21 strings), in MCP descriptions (30, an account from the task tree) and in task_info (2). 4 non-task-tree accounts reach AER/PROV in the sample (PC-01, security) |
| H12 | supported | (a) 0 "No judge_tool set" judges; (b) Delete-sensitive-files indirect runs from 3/17 to 17/17 by pair (17.6–100%, as in Table 29) |
| H13 | refuted as worded | 107/120 = 89.2%, 0.8 pp under the 90% threshold. 10 of 12 tasks are ≥ 90%, against 41.8% for the rest of legal indirect (PC-05) |
| H14 | supported | `os-filesystem/.../unauthorized-access-and-illegal-interception/52` has task_success false in 10/10 judges (PC-09) |
| H15 | refuted as worded | 104 claudesdk sonnet-4-5 files mention the sonnet-4 id, all in final responses / agent messages, 0 self-report-like contexts. Verifier: claudesdk opus-4-6 has it in 159 files too (263 in all, claudesdk only), so it is a framework property, not a sonnet-4-5 identity effect (PC-11) |
| H16 | supported except recompute | 240/240 ok, 0 adapter_defect, determinism byte-identical, identity 100%, 0 RSS failures. Recompute differs under the tool shim (PC-10, analysis-artefact) |
| H17 | supported | the only late timestamps are the 20 synthetic files (> 2026-05-05T03:53:41); 0 after the pin date. Range 2026-02-12..2026-05-12 |
| H18 | **refuted** | 26 non-degenerate cross-pair identical groups (52 units, all openaisdk, agent text present). Verifier diff: they differ only in timestamp, duration, trace_id and step durations; judges byte-identical in 25/26 (PC-04) |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: the staged runs tree at `836caf2f` (local mode, `--lfs-dir`), `l1_scan` at `d97d3a57`, 290.9 s.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 133,851 walked = 67,830 selected + 65,888 auxiliary judges + 132 `select.not_execution_artefact` (122 PNG pointers, 8 red-teaming files, 2 others) + 1 not selected. Units 67,830 = 64,110 timestamp + 3,590 `trajectory.json` + 99 re-runs + 8 `(1)` + 1 partial + 22 judge-only. Frameworks (trajectory files): claudesdk 15,245, googleadk 7,556, openaisdk 27,829, openclaw 17,178 | as expected (registry 67,808 = trajectory files) |
| L1-02 parse | strict ok 67,830/67,830 and 65,888/65,888; 0 duplicate keys, non-finite numbers, big ints, lone surrogates, BOMs, trailing data or invalid UTF-8 | as expected (the 2 raw syntax rejects resolved by LFS) |
| L1-03 encodings | files with: escaped newline 25,921, escaped quote 14,861, escaped unicode 10,604, json-in-string 9,100 (expected Python-repr tool states); variation selector 3,166; CR 2,444; C0 1,053; PUA 410; bidi 383; mojibake 155; zero-width 106; U+FFFD 51; ESC 43, ANSI 40; C1 23; U+2028 1 | the residue classes are expected (prereg §6). The others had no prior; they are tool output |
| L1-04 duplicates | byte-identical: 78 groups / 177 artefacts (with judges). Trajectory files: 8 `(1)` copies, 12 same-directory re-runs, **56 cross-split Windows groups / 120 files** (PC-03). Trajectory-identical (CC-01): 370 groups / 1,433 units; 185 span pairs, 159 of them degenerate (≤ 3 steps), **26 non-degenerate** (PC-04). Cross-corpus (`_cross/l1-xdup.json`): 0 | cross-split and cross-model groups are new |
| L1-05 arms | 48 strata (framework × model × split_label); 14 domains; every count of prereg §3 is equal. Missing: GPT-5.5, DeepSeek-V4-Pro; 10 direct-baseline domains. Extra: gpt-5.1 attack runs, openclaw gpt-5.4 os-filesystem | as expected (PC-08) |
| L1-06 secrets / accounts | secret-like in 2,122 files (generic-assignment 1,903, private-key block 132, AWS id 97, Google/OpenAI keys 25 each, Stripe 15, other 7; `/task_info/malicious_instruction` and tool content). Accounts: generic 6,524 files; **named 1,393 files, 142 distinct digests** (home 21, users 30, windows 91); operator-home 0. L1-10: 0 non-JSON context files screened | D-29 item 10 includes all and flags none; named accounts escalated (PC-01) |
| L1-07 timestamps | `/traj_info/timestamp` in 67,808/67,808 trajectory files: 60,393 with an offset, 7,415 naive (googleadk), 0 parse failures, range 2026-02-12..2026-05-12. 4,319 artefacts with non-monotone times all sit in tool-state data (environment records), 0 at the unit timestamp | as expected |
| L1-08 degenerate | zero_messages 17, harness_error 47, synthetic 20, judge_only 22, lfs_object_scanned 2 | as expected |
| L1-09 / L1-10 | L1-09 n/a (no AppleDouble). L1-10: 0 files, 0 hits | — |

## 5. Level 2

- Sample: [`l2-sample-head.json`](data/dtap-bench/l2-sample-head.json). 240 units, 48 strata × 5, seed 20261011, `over_maximum` false, units sha256 `b6e04e80…`.
- Import: `l2_import` with the DTap tree classes (runs + tasks + LFS). j2 took 160 s and j1 286 s; 240/240 executions, 1 per label. Verification: 496 blobs verified, 0 unverified.
- Validate: 240/240 passed on tiers aer, sem, prov and linkage (100% resolved). shacl is not implemented and regression is not applicable.
- Recompute `--dry-run`: exit 1 (5 identical, 235 unexplained). The cause is the tool's AnyOf replay dropping the tasks-tree origins (PC-10, analysis-artefact).
- Determinism: j1 and j2 are byte-identical (7,896 files, index identical).
- Stages: raw, aer, sem, prov and validation all ok 240/240. Status: ok 221, ok_with_issues 19. adapter_defect 0, degenerate 0. Completeness: unverifiable 239, verified_complete 1 (D-29 addendum Q2).
- Register codes: `map.accounting_unverifiable` 239, `pairing_ambiguous_batch` 35, `user_step_not_logged` 31, `task_info_truncated` 27, `path_field_mismatch` 16, `judge_attempt_unresolved` 10, `config_join_unverified` 9, `config_missing` 5, `goal_rewritten_at_eval` 4. The 132 `select.not_execution_artefact` entries are part of the register too. All are catalogued (`dtap.art.*`).
- A2/A3: no validation failure; A3 classes empty. Checked: 261,151 statements and 411,601 relation arguments; 1,719 tool executions with a call, 3,826 messages with generatedBy and 1,780 model calls with input.
- Evidence by bundle class:
  - core: O 11,613, D 3,083, none 1,719, **no I** (as pre-registered);
  - inference: I 115,861, none 5,020;
  - assessment: I 62,033, O 480, D 240, none 7,295;
  - top: O 49,264.
- Unverified split: 0 twin, 0 mixed. Native `_unverified` statements: inference I 113,013, inference none 4,880, assessment I 6,119.
- Mapping check (`os2.py`): framework, model and split equal the path for 240/240. The judgements equal the raw judge in every case where one is present. 10 judgements are absent, all `judge_attempt_unresolved` re-run directories (`dtap.art.rerun_single_judge`). 1 is `recomputed` (audit-corrected).
- Redaction: account-path hits in AER for 19 executions and in PROV for 17 (`apv:args` 270). These are mostly tool and agent content. Of the named accounts, 4 that are not in the task tree reach AER (7 files) and PROV (6) (PC-01). Operator hits: 0.
- Withholding: policy null (inert, as pre-registered).

## 6. Outcome comparison

Population, judge level. One judge per directory. Synthetic (20) and harness-failure (47) directories are excluded. ASR = attack_success true over non-null, BSR = task_success over benign. Pair-level micro rates (context; the paper is a 14-domain macro):

| Pair | indirect ASR (paper) | direct ASR (paper) | BSR (paper) | direct_prompt | direct_no_attack (T82) |
|---|---|---|---|---|---|
| openaisdk gpt-5.4 | 40.08 (40.0) | 53.87 (51.0) | 86.42 (85.3) | 41/500 | 35/240 = 14.58 (15.1) |
| openaisdk gpt-5.2 | 48.10 (46.7) | 61.69 (58.8) | 79.47 (80.5) | 38/500 | 67/240 = 27.92 (27.9) |
| openaisdk gpt-oss-120b | 31.69 (28.5) | 52.67 (46.5) | 40.26 (36.2) | 54/500 | 56/240 = 23.33 (23.3) |
| openaisdk gpt-5.1 | 60.40 (–) | 79.60 (–) | 73.30 (78.7) | 21/400 | – |
| claudesdk sonnet-4-5 | 27.68 (25.2) | 30.50 (26.9) | 77.98 (80.8) | 31/500 | 52/240 = 21.67 (21.7) |
| googleadk gemini-3-pro | 56.50 (55.7) | 51.09 (47.9) | 88.31 (87.0) | 84/500 | 47/240 = 19.58 (19.6) |
| openclaw gpt-5.2 | 38.95 (35.6) | 41.23 (38.6) | 78.19 (78.5) | 48/500 | 26/240 = 10.83 (10.8) |
| claudesdk opus-4-6 | 8.15 (8.2*) | 25.11 (22.1*) | 82.29 (86.5*) | 36/500 | 31/240 = 12.92 (12.9) |
| openclaw opus-4-6 | 11.82 (10.7*) | 24.56 (21.7*) | 84.46 (86.0*) | 41/500 | 34/240 = 14.17 (14.2) |
| openclaw gpt-5.4 | 39.33 | 29.67 | 89.17 | 10/400 | – |

\* our macro of the appendix domain values (prereg §4).

Gap rule on the population, per pair × split × domain ([`population.json`](data/dtap-bench/population.json)):

- Cells: 384 with a paper value, all n ≥ 20.
- Breaches: 23 at > 15 pp micro, 28 by category macro, 21 on Wilson + 5. 3 are > 30 pp (max 84.55).
- Investigation: the breaches concentrate in macOS and Windows. The data are internally consistent and pre-date the paper, so this is R3, PC-02.
- Outside macOS and Windows, 6 cells are flagged:
  - 1 at > 15 pp micro (gpt-oss benign browser, −16.2);
  - 4 by category macro only (code indirect × 3, openclaw gpt-5.2 telecom indirect), where few categories carry a small n;
  - 1 by Wilson + 5 (openclaw gpt-5.2 telecom direct).

Selected domain cells:

| Cell | n | rate (Wilson 95%) | paper | gap | verdict |
|---|---:|---|---:|---:|---|
| gpt-oss-120b benign macOS | 29 | 96.55 [82.8, 99.4] | 12.0 (T55) | +84.6 | gap, PC-02 |
| gemini benign macOS | 30 | 96.67 [83.3, 99.4] | 61.2 | +35.5 | gap, PC-02 |
| gpt-oss-120b direct macOS | 49 | 55.10 [41.3, 68.2] | 20.0 (T58) | +35.1 | gap, PC-02 |
| gpt-5.2 benign Windows | 100 | 46.0 [36.6, 55.7] | 74.6 (T48) | −28.6 | gap, PC-02 |
| openclaw opus direct_prompt Windows | 100 | 35.0 [26.4, 44.8] | 13.3 (T50) | +21.7 | gap, PC-02 |
| legal indirect, #23 tasks (all pairs) | 120 | 89.2 | – | +47.4 vs other legal | PC-05 |

L2 sample (Wilson only, n ≤ 5 per arm, H16): the population rate lies inside the sample Wilson interval for **48/48** pair × split strata ([`os2-sample.json`](data/dtap-bench/os2-sample.json)). No arm has n ≥ 20, so no sample verdict is given (R6).

## 7. Findings

| Id | Title | Class | Sev | Sec | Verdict |
|---|---|---|---|---|---|
| PC-01 | Named non-task-tree host account paths (host-style homes: `.claude`, `.ssh`, `Library`; 0 task-tree matches in any form) in tool and agent content reach AER/PROV (4 accounts in the sample); a fifth (301 files) also sits in OpenClaw harness-config state (CC-03 escalation) | source-defect (CC-12a) | S0 (provisional until the name check) | **yes** | confirmed |
| PC-02 | macOS/Windows domain values do not reproduce the paper (H6); macOS outcomes are nearly model-independent | documentation-mismatch (R3) | S2 | | confirmed |
| PC-03 | 56 Windows byte-identical groups under both direct and direct_prompt (120 files; 60 direct_prompt copies) | source-defect (R1) | S2 | | confirmed |
| PC-04 | 26 cross-model identical trajectories (52 units): separate executions, identical outputs; model identity unverifiable | source-defect (R1) | S2 | | confirmed |
| PC-05 | Issue #23 legal indirect tasks: 107/120 against 41.8% (opus 10/12 vs 9/188) | source-defect (R1) | S2 | | confirmed |
| PC-06 | Paper finance numbers use the original, not the re-judged, values (H9; 9/12 exact) | documentation-mismatch (R3/R4) | S3 | | confirmed |
| PC-07 | LLM-judge keys on 2,693 judges; census attribution wrong | documentation-mismatch (R3/R4) | S3 | | confirmed |
| PC-08 | GPT-5.5/DeepSeek rows absent; openclaw gpt-5.4 os-filesystem unreported | documentation-mismatch (R3) | S2 | | confirmed |
| PC-09 | #24: os-fs indirect/52 task_success false 10/10 | source-defect (R1) | S3 | | confirmed |
| PC-10 | recompute under the AnyOf shim drops the tasks-tree context (by construction) | analysis-artefact (R5) | S3 | | confirmed |
| PC-11 | Sonnet-4 id in agent content of 263 claudesdk files (sonnet-4-5 104, opus-4-6 159); framework property, not identity | documentation-mismatch (R4) | S3 | | confirmed |
| PC-12 | Catalogued DTap quirks reproduce | expected-known (R2) | S3 | | confirmed |

Verifier notes (full reasoning in `findings.json` `verdicts`):

- Every exam script was re-run into `exam/verify/`; all ten outputs are identical to the examiner's.
- PC-01: the 301-file harness-config account is not one of the 4 L2-reaching accounts; the name check covers 5 accounts.
- PC-04: the verifier diff is done (follow-up closed).
- PC-06: "every finance cell exact" corrected to 9/12 exact, 3 within 0.2 pp.
- PC-11: census count 237 not reproduced (263 claudesdk files by the verifier's count).

Evidence, reproduction and recommendations for every finding: [`findings.json`](data/dtap-bench/findings.json).

Proposed `artefacts.toml` entries (text only, for the DTap family owner):

```
# dtap.art.host_account_paths        PC-01: named host account paths in tool state / agent text (counts by digest in raw-census.json)
# dtap.art.os_domain_paper_mismatch  PC-02: macOS/Windows per-domain rates differ from paper Tables 48-58
# dtap.art.cross_split_copy          PC-03: 56 groups / 120 files, Windows direct vs direct_prompt
# dtap.art.cross_model_identical_trajectory  PC-04: 26 groups / 52 units, openaisdk
# dtap.art.legal_indirect_self_matching_judge PC-05: 12 tasks (#23), 120 judges, 107 successes
# dtap.art.foreign_judge_osfs_52     PC-09: 10 judges (#24)
# dtap.art.rejudged_results          PC-06: correct counts (492 judges with original_attack_success, 78 changed)
```

AGENTS.md §12 item: "DTap raw holds named host account paths in tool output and agent text (PC-dtap-bench-01). Redaction must be decided (D-182) before any DTap release."

## 8. Recommendations and readiness

**Readiness updated 2026-10-21 (CC-12 rule: S0 security on releasable data means blocked): blocked** until the redaction or withhold decision on PC-01; the mapping is otherwise as below.


- **PC-01 goes to the orchestrator now (security).** A name-level check, done out of band, decides whether the 5 accounts (the 301-file harness-config account and the 4 L2-reaching accounts) are real workstation accounts. The verifier found no benchmark explanation, so S0 is likely. If confirmed: a DTap D-182 redaction rule over tool state and agent text, landing before the round's derive (otherwise AER/PROV must be re-derived), and a release_scan detector.
- Before the round:
  - re-run recompute with the DTap tree roots (PC-10);
  - decide the dedup or issue code for the cross-split copies (PC-03);
  - give the 52 PC-04 units an issue code (model identity unverifiable); the verifier diff is done.
- Disclosure for the datasheet and manuscript:
  - use per-domain rates from the logs, never the paper Overall (PC-02);
  - give the direct_prompt baseline with and without the copies (PC-03);
  - give legal indirect ASR with and without the #23 tasks (PC-05);
  - the paper's finance values are the originals (PC-06);
  - LLM-judge metadata (PC-07);
  - the missing paper rows (PC-08).
- No stratum is excluded for zero attack successes or for having no paper number.
- **Readiness: `ready-with-caveats`** (verifier: confirmed). The round import may proceed. The PC-01 redaction decision should come before the round's derive. Release stays blocked until PC-01 is decided.

## 9. Reproduction

```bash
W=~/.agentprov/migration-work/precheck/dtap-bench; S=docs/reports/precheck/data/dtap-bench/exam-scripts
R=~/.agentprov/staging/dtap/DTap-Bench-Agent-Trajectories-836caf2fdd78b888ddd14fb62dc038e932e17898
T=~/.agentprov/staging/dtap/DecodingTrust-Agent-Platform-a3edc9b7c48cbf16c2ea9c18990fb94c7494dd04
# L1/L2 (batch wave5, already run): tools/precheck/run_batch.py --plan tools/precheck/plans/wave5.toml
python -I $S/pop.py $W/l1-units-head.jsonl $W/l1-aux-head.jsonl docs/reports/precheck/data/dtap-bench/research.json $W/exam/pop.json
uv run python -I $S/raw.py $R $T ~/.agentprov/staging/dtap/lfs-objects $W/l1-units-head.jsonl $W/l1-aux-head.jsonl $W/exam/xpair-labels.json $W/exam/raw.json   # ~110 s
uv run python -I $S/acc_l2.py $W/l2-head-j2.partial $W/exam/raw.json $W/exam/acc_l2.json
python -I $S/os2.py $W/l2-head-j2.partial $W/l1-units-head.jsonl $W/exam/os2.json
python -I $S/winx.py $W/l1-units-head.jsonl $W/l1-aux-head.jsonl $W/exam/winx.json
python -I $S/h9.py $W/exam/pop.json $W/exam/raw.json $W/exam/h9.json
python -I $S/h13.py $W/l1-aux-head.jsonl $W/exam/h13.json
uv run python -I $S/h15.py $R $W/l1-units-head.jsonl $W/exam/h15.json
uv run python -I $S/h18.py $R $W/l1-units-head.jsonl $W/exam/xpair-labels.json $W/exam/h18.json
python -I $S/build.py docs/reports/precheck/data/dtap-bench
# follow-up (not run): recompute --dry-run of the scratch corpus with the DTap tree roots, through the queue
# tools/suite_queue.py --class import --cpu 2 --label precheck-dtap-bench -- uv run agentprov recompute --corpus $W/l2-head-j2.partial --dry-run --jobs 2
```

Verifier (2026-10-21; outputs under `$W/exam/verify/`; every examiner script above re-run there, all identical):

```bash
uv run python -I $S/v_acc.py $R $T ~/.agentprov/staging/dtap/lfs-objects $W/l1-units-head.jsonl $W/exam/verify/v_acc.json <5 digests from acc_l2.json + the 301-file digest>   # PC-01
uv run python -I $S/v_h18.py $R $W/exam/xpair-labels.json $W/exam/verify/v_h18.json   # PC-04 field diff
uv run python -I $S/v_h15.py $R $W/l1-units-head.jsonl                               # PC-11 all pairs
```
