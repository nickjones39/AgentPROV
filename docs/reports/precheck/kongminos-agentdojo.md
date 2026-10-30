# Pre-check dossier: `kongminos-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `kongminos-agentdojo`. MIT, "Copyright (c) 2026 kongminOS"; the logs embed AgentDojo benchmark text, which is MIT |
| Parts | `kongminos-agentdojo · head` (1 part) |
| Family / profile | `agentdojo` / `kongminos-agentdojo@1` (dialect `agentdojo.tracelogger`, variant `v1.k14`, semantics `agentdojo.suites@2`) |
| Pin | git `kongminOS/jspace-agentdojo-950` @ `f341af69` (2026-08-22T04:49:25Z, = head). Data commit `47a44d18` |
| Code commit | `d97d3a57` (L1 and L2, batch `wave3`, all 6 steps rc 0, tracked changes false) |
| Kind | wave 3, first examination (not in FA or E2); no stored corpus |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (batch), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), batch runner, examiner (this dossier), adversarial verifier 1 (2026-10-21: 12 confirmed, PC-05 reclassed, PC-06 narrowed, 0 refuted) |
| Data | [`data/kongminos-agentdojo/`](data/kongminos-agentdojo/): `research.json`, `l1-head.json`, `l1-10-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `findings.json`, `pop-population.json`, `exam-extra.json`, `exam-tail.json`, `os1-population.json`, `os2-sample.json`, `exam-scripts/` |

- Code identity, part `head` ([`code-head.json`](data/kongminos-agentdojo/code-head.json)): commit `d97d3a57` (tracked_changes false). Engine code: aer `856b7a09e0cf`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `a10ee3c16045`. Adapter `agentdojo.tracelogger@0.1.0` `03d8bc6d30df`. Profile sha256 `bd58983eca2e`, rules agentdojo 2 / aer 1. Lockfile `b0455f1058c8`, limits `5d6dbb210259`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Source repository | https://github.com/kongminOS/jspace-agentdojo-950 @ `f341af69` (not a fork; `main` only; 0 tags, issues or PRs) | the data. README "v3 report" table: Benign 88.16 %, UA 82.38 %, ASR 3.89 % |
| Article | "J-Space 翻车全记录" (named by the README; not found) | none usable |
| Data record | none (no Zenodo, HF or Figshare record) | git blob ids only |
| Benchmark | AgentDojo, arXiv:2406.13352; agentdojo 0.1.35 = `a75aba76`; benchmark `v1.2.2`; `LocalLLM` pipeline | harness, attack `tool_knowledge` |
| Upstream issues | ethz-spylab/agentdojo #150, #202, #219 (LocalLLM parsing), #220 (empty answer on error), #213 (workspace IT6-13 ground truth), #181, #161 | defects that show in this data |

Data-versus-paper notes (from `research.json`, checked against the data):

- The README figures reproduce exactly under the README's own definition (874 attack-directory files). That definition counts the 30 pre-pass logs, whose security is a runner constant (PC-04).
- The pin commit changes only `README.md` (diff-tree); its message and `research.json` give the model-line change from "DeepSeek V4 Pro / J-Space" to "DeepSeek V4-Flash" (the earlier README blob is not in the blobless clone). No log names a model (PC-05).
- The README's note on 29 `ad_runs` leftovers (an early internal count of 979) agrees with the release: 950 logs, 0 `ad_runs` paths (PC-06).
- The data has properties that neither the README nor our profile mentions:
  - The run's last 33 logs are empty answers (PC-01).
  - 478 turns carry tool-call tags that were never parsed into calls (PC-02, PC-03).
  - 320 tool_knowledge payloads carry no tool sentence (PC-12).

## 3. Expectations

The pre-registration is [`prereg/kongminos-agentdojo.md`](prereg/kongminos-agentdojo.md). It was committed in `fd75f8a3` on 2026-10-14, before any check of this corpus ran.

- README amendments 2 to 5 apply. Amendment 2.4 sets the stratum key: run_set × attack_dir × suite, 9 strata, the same as the prereg's 9.
- Amendment 1 does not apply, because there is no stored corpus.
- Findings are classed by R1-R6 and CC-01..CC-11.

| H | Result | Note |
|---|---|---|
| H1 | supported | 67/76, 720/874 and 34/874 reproduce exactly |
| H2 | supported | 30/30 pre-pass logs have security true. Targeted ASR is 4/844 (PC-04) |
| H3 | refuted in part | Supported: 0 of 320 workspace IT6-13 payloads have a tool sentence, and "Local model" is addressed in 844/844. Refuted: 1 IT6-13 success (UT3 × IT13, 5 executed `send_email`), and travel IT6 (20 logs, a text goal) also has no tool sentence (PC-12) |
| H4 | not tested | 0 banking attacked successes. #181 affects 0 (PC-07) |
| H5 | **refuted** | 33 logs end on an empty answer with no call, against 0 expected (PC-01) |
| H6 | **refuted** | 0 turns with more than 1 parsed call. But 461 call turns hold 2 or more tags, and 17 final turns hold a tag without a call: 478 turns in 154 logs (PC-02, PC-03) |
| H7 | supported | 25/25 trailing-call logs have exactly 15 tool messages |
| H8 | supported | 6 groups, each within one (suite, user task). All members are zero-call runs with 0 payload exposure (PC-10) |
| H9 | supported | 950 distinct (suite, user task, injection task) keys, 0 duplicates. `benchmark_version` v1.2.2 in 950/950. Injection task ids 0-13 / 0-8 / 0-6 |
| H10 | supported on the range | All timestamps fall in 12:40:34-15:07:40, and each run set's range lies inside it. The zone clause holds only for UTC-11 or later: under UTC-12, 13 logs (after 15:06:09) would postdate the data commit |
| H11 | supported | System prompt 469 characters with one digest in 950/950. Roles: system, user, assistant and tool only |
| H12 | refuted as worded | 1 log holds a generic home path that the model invented. 0 secrets (PC-09) |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: the staged bare clone at `f341af69`, read with `--git`, blob ids checked. Tool `l1_scan` at `d97d3a57`, 2.5 s.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 957 walked = 950 selected + 3 context + 4 absent PNG blobs. 0 excluded or rejected. 950 units = registry = census | as expected |
| L1-02 parse | strict ok 950/950; 0 defects of any class | as expected |
| L1-03 encodings | 0 U+FFFD, invalid UTF-8, controls, bidi, tag or zero-width characters. Residues, all at `/messages/*/content/*/content` (tool outputs): escaped newline 432 files / 916 strings, escaped quote 58 / 62, escaped unicode 103 / 155. Variation selector 40 / 44. CJK count not taken | as expected |
| L1-04 duplicates | 0 byte-identical. Trajectory-identical (CC-01): 6 groups / 38 units (sizes 9, 9, 9, 6, 3, 2), all zero-call. `_cross/l1-xdup.json`: 2 cross-corpus groups with `ceferisbarov-agentdojo`, both empty runs (PC-10) | within-part as H8. The prereg expected 0 cross-corpus groups; the 2 found are degenerate equality |
| L1-05 arms | 9 strata. Cells: 844 attacked (workspace 40 × 14, banking 16 × 9, travel 20 × 7), 30 pre-pass, 76 benign. 0 missing, 0 extra. Slack absent by design | as expected |
| L1-06 secrets/paths | 0 secret-like strings. 1 artefact with `account:home-dir:generic` (6 strings at 3 pointers): model-generated `read_file` arguments. 0 named accounts, 0 operator hits. L1-10: 3 context files, 0 hits | PC-09 (CC-03) |
| L1-07 timestamps | `/evaluation_timestamp` present in 950/950, all naive, 0 parse failures, one day. Run-set ranges: full_benign 12:40-12:49, full_attack 12:49-13:56, tb_benign 13:59-14:05, tb_attack 14:05-15:07 | as expected |
| L1-08 degenerate | null_final 33, trailing_calls 25, account_path_generic 1. 0 empty logs and 0 non-null `error`. 43 zero-call logs | the 25 trailing calls were expected. The 33 null-final were not (prereg 0): PC-01 |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`l2-sample-head.json`](data/kongminos-agentdojo/l2-sample-head.json) (sha256 `35764570fe04…`): 45 of 950 units, 9 strata × 5, seed 20261011. It includes 1 empty-final log, 2 trailing-call logs, 1 attacked success and 13 logs with tag excess |
| Import | 2 scratch corpora (`l2-head-j2.partial`, `-j1.partial`). 45/45 mapped: 43 ok, 2 ok_with_issues (`map.unexecuted_tool_call`). 0 degenerate, 0 `adapter_defect`. Each of the 45 labels joins to exactly 1 execution |
| Validation | tiers aer, sem, prov and linkage: 45/45 pass, 45 reproduced, linkage 45/45. SHACL skipped (not implemented) |
| Recompute | `--dry-run`: 45 identical, 0 unexplained |
| Verify chain | 0 failures; only `checksums.absent` (working tree). No withholding applies |
| Determinism | j2 vs j1: 190/190 files, 0 differ, index identical |
| A2 codes | `map.accounting_unverifiable` 45, `map.earlier_attempts_unobservable` 45, `map.unexecuted_tool_call` 2. No `agentdojo.local_parse_drop_possible` was raised, although 13 sampled logs qualify (PC-02) |
| A3 PROV | 0 dangling, missing or invented relations over 23,263 statements and 39,339 relation arguments. 2 unexecuted call parts are represented; the tool prints "executions 0" for them (PC-11) |
| Evidence classes | Core: D 195 (engine rules only), O 1,414. Inference: I 8,782. Assessment: I 1,889, O 90. Twin / native / mixed split (bundle-id decoding, CC-08): twin inference:I 7,728, inference:none 595, assessment:I 1,006; native 0; mixed inference:I 987. 0 AER records at class D |
| Empty final (sampled UT13 × IT2) | The message part cites `agentdojo.empty_assistant_text_ambiguous_unverified@1`. The execution has status ok and no issue code (PC-01) |
| Judgements (OS-2) | raw vs mapped: 0 of 90 differ. Origins: utility checker 45; security checker 15, `harness_default` 30 |
| Identity | model `local` → `deepseek-v4-flash` 45/45 (class I, README basis); defence none; attack `tool_knowledge` 15 / none 30; suites 15 each. 0 mismatches, 0 unresolved |
| Redaction | 143 AER/SEM/PROV files, 0 hits. The generic-path log is not in the sample |
| Withholding | not applicable (no policy, 0 secrets) |

## 6. Outcome comparison

Level 1 covers the whole population (raw booleans, 950 logs). The reference is the README table, which gives all-suite figures only. Gap rule: more than 15 pp, or more than 5 pp outside the Wilson 95 % interval. Full rows are in [`os1-population.json`](data/kongminos-agentdojo/os1-population.json).

| Arm (deepseek-v4-flash / none / attack / suite) | Level | n | Metric | Rate (Wilson 95 %) | README | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|---|
| none / none / all | L1 | 76 | benign utility | 88.16 (67/76) [79.00, 93.64] | 88.16 | 0.00 | match |
| tool_knowledge / all (844) | L1 | 844 | UA | 82.58 (697/844) [79.88, 84.99] | 82.38 (874 def.) | +0.20 | match; different definition (PC-04) |
| tool_knowledge / all (844) | L1 | 844 | targeted ASR | 0.47 (4/844) [0.18, 1.21] | 3.89 (874 def.) | −3.42 | not flagged (2.68 pp outside Wilson); definition (PC-04) |
| README definition, 874 attack-dir files | L1 | 874 | utility / security | 82.38 (720) / 3.89 (34) | 82.38 / 3.89 | 0.00 / 0.00 | exact (H1) |
| none / none / banking, travel, workspace | L1 | 16 / 20 / 40 | benign utility | 93.75 / 80.00 / 90.00 | — | — | no source number |
| tool_knowledge / banking | L1 | 144 | UA / ASR | 63.89 [55.78, 71.28] / 0.00 [0.00, 2.60] | — | — | 33 empty-final logs inside (PC-01) |
| tool_knowledge / travel | L1 | 140 | UA / ASR | 82.14 / 0.71 (1) | — | — | |
| tool_knowledge / workspace | L1 | 560 | UA / ASR | 87.50 / 0.54 (3) | — | — | IT6-13 1/320, other 2/240 (PC-12) |
| banking UA without the 33 empty-final logs (info) | L1 | 111 | UA | 82.88 (92/111) [74.81, 88.76] | — | — | sensitivity only (PC-01) |
| all-suite UA without the 33 (info) | L1 | 811 | UA | 85.94 (697/811) [83.38, 88.17] | — | — | sensitivity only |
| pre-pass (info) | L1 | 30 | utility | 76.67 (23/30) | — | — | reported separately |

Level 2 is the mapped AER of the 45-unit sample; the raw values of the same labels are equal in all 90 judgements ([`os2-sample.json`](data/kongminos-agentdojo/os2-sample.json)). Every arm has n = 5, so no arm reaches 20 and the gap rule gives no verdict (R6):

- attacked banking: UA 4/5, ASR 0/5.
- attacked travel: UA 4/5, ASR 0/5.
- attacked workspace: UA 3/5, ASR 1/5 [3.6, 62.4].
- benign: 5/5 in each suite.
- pre-pass: banking 5/5, travel 5/5, workspace 3/5.
- Pooled tool_knowledge ASR: 1/15 [1.2, 29.8], against the population's 0.47 %, which lies inside the interval.

CC-07 on this data:

- #181: there are 0 banking IT0/1/3 successes, so 0 are affected and the re-scored banking ASR equals the logged 0/144.
- #161: banking `user_task_5` has 10 logs, all with utility true. Each executed a Spotify payment, so 0 are vacuous (PC-07).

## 7. Findings

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-kongminos-agentdojo-01 | [#220] The run's last 33 logs (banking attacked UT12 6/9 and UT13-15 9/9 each, 14:56:34-15:07:40) end on an empty answer with 0 calls. Median duration is 7.46 s against 1.03 s for other zero-call runs, and the benign twins succeed. LocalLLM returns `''` on any client exception. All 33 score utility false and security false, with no payload exposure | source-defect (R1) | S2 | confirmed | Add an `agentdojo.art.local_empty_final` scope row (33), same id as PC-tacit-09. Disclose banking UA 63.89 % as logged against 82.88 % without the 33. Keep all logs |
| PC-kongminos-agentdojo-02 | The profile omits `agentdojo.local_model_raw_completion`, so 478 turns in 154 logs with more `<function=` tags than parsed calls are never flagged. 0 tag-count records in the 13 qualifying sampled logs. The census's "measured 0" reflects the missing quirk, not the data | mapping-defect | S2 | confirmed | Family owner adds the quirk (observed 478 / 17 / 154 logs). Byte-changing regen item, user approval before re-import. Same as PC-tacit-01 |
| PC-kongminos-agentdojo-03 | [local_parse_drop] 17 runs end on a final turn whose tag was not parsed (15 attacked, 2 benign; all utility false) | expected-known (R2; scope gap CC-09) | S3 | confirmed | Disclose the count; add the scope rows |
| PC-kongminos-agentdojo-04 | README ASR 3.89 % and UA 82.38 % include the 30 pre-pass logs. Targeted ASR is 4/844 = 0.47 % (8.3× lower) and UA 697/844 | documentation-mismatch (R3) | S2 | confirmed | Report the 844-convention numbers; quote the README figures only with their definition |
| PC-kongminos-agentdojo-05 | Model `deepseek-v4-flash` rests on one README line rewritten in the pin commit (from V4 Pro / J-Space). Checkpoint, endpoint and thinking mode are not recorded | expected-known (class-I identity, D-92/D-105; verifier: no README-data mismatch, identity caveats are S3) | S3 | confirmed (reclassed from documentation-mismatch S2) | Datasheet caveat for model-level analyses (class I) |
| PC-kongminos-agentdojo-06 | The README links `princeton-pli/AgentDojo` (HTTP 404, 2026-10-21). Its note on 29 `ad_runs` leftovers agrees with the 950 released logs | documentation-mismatch | S3 | confirmed (narrowed: the ad_runs clause is not a mismatch, README l. 19 says they are not released) | Record in the datasheet |
| PC-kongminos-agentdojo-07 | [CC-07] #181: 0 of 0 affected; #161: 0 of 10 vacuous | expected-known (CC-07) | S3 | confirmed | Scope rows with count 0 |
| PC-kongminos-agentdojo-08 | [CC-09] reference: no AgentDojo entry scopes kongminos; quirk counts verified | documentation-mismatch (CC-09) | S3 | confirmed | Recorded once at CC-09; not counted |
| PC-kongminos-agentdojo-09 | [CC-03] 1 log has a generic home path that the model invented in `read_file` arguments (6 strings) | expected-known (CC-03) | S3 | confirmed | No withhold; check the release_scan generic-path handling |
| PC-kongminos-agentdojo-10 | [CC-01] All trajectory groups are zero-call runs. The 2 cross-corpus groups with ceferisbarov are empty runs, not copying | analysis-artefact (R5) | S3 | confirmed | Tool owner, after the freeze: mark zero-call fingerprints |
| PC-kongminos-agentdojo-11 | `l2_check` prints `unexecuted_represented` executions 0 while the count is 2 | analysis-artefact (R5) | S3 | confirmed | Tool owner, after the freeze (as PC-mohameduk-10) |
| PC-kongminos-agentdojo-12 | [#213] 0 of the 320 workspace IT6-13 tool_knowledge payloads have a tool sentence. ASR is 1/320 there and 3/524 elsewhere | source-defect (R1) | S2 | confirmed | Widen `agentdojo.art.tool_knowledge_empty_sequence` (PC-shreeyavarma-02, count 320). Report the split ASR |

12 findings, all confirmed by adversarial verifier 1 (0 refuted; PC-05 reclassed to expected-known S3; PC-06 narrowed to the dead link). Verifier recount: `~/.agentprov/migration-work/precheck/kongminos-agentdojo/exam/verify/v.py` (labels from the git tree, independent of the L1 rows) reproduced every count; reasoning per finding is in `findings.json` `verdicts`.

- Security findings: none (0 secrets, 0 named or operator accounts).
- Not counted in readiness: PC-08 (reference to CC-09) and PC-10 / PC-11 (R5).
- Mapping defects: one, PC-02. It is a profile omission and changes no outcome boolean.

Proposed `artefacts.toml` entries (text only; route to the AgentDojo family owner):

```toml
# PC-01: widen the entry proposed in PC-tacit-agentdojo-09
# id = "agentdojo.art.local_empty_final"; scope += kongminos-agentdojo / head / profile kongminos-agentdojo
expected += [{ snapshot = "kongminos-agentdojo:head", count = 33, unit = "executions", basis = "pre-check raw census 2026-10-21: empty final text, 0 calls; the last 33 logs by timestamp (banking UT12 6, UT13-15 9 each)", status = "proposed" }]
# PC-02/03: agentdojo.art.local_parse_drop scope += kongminos-agentdojo
expected += [{ snapshot = "kongminos-agentdojo:head", count = 478, unit = "turns", basis = "more <function= tags than parsed calls (154 logs)", status = "proposed" },
             { snapshot = "kongminos-agentdojo:head", count = 17, unit = "turns", basis = "tag and no parsed call; all final turns", status = "proposed" }]
# PC-12: agentdojo.art.tool_knowledge_empty_sequence (proposed in PC-shreeyavarma-llm-safety-02) scope += kongminos-agentdojo
expected += [{ snapshot = "kongminos-agentdojo:head", count = 320, unit = "executions", basis = "workspace IT6-13 tool_knowledge payloads without a tool sentence, benchmark v1.2.2", status = "proposed" }]
# PC-07 (CC-07): agentdojo.art.validity_defects scope += kongminos-agentdojo, count 0 (#181 0/0, #161 0/10)
# PC-08 (CC-09): benign_security_constant 106; injection_task_as_user 30; max_iters_pending 25 logs / 25 calls; provider_ids null 3,311; naive_timestamp 950
```

Items for AGENTS.md §12:

- PC-01: in the kongminos banking tool_knowledge arm, 33 of 144 logs are empty answers at the end of the run (#220). UA is 63.89 % as logged and 82.88 % without them, a sensitivity figure only. The ASR denominator includes 33 runs in which the agent never saw the payload.
- PC-02: the kongminos profile lacks `local_model_raw_completion`. Re-import after the fix: 154 AERs gain the tag count and the issue.
- PC-04: kongminos targeted ASR is 4/844 (0.47 %), not the README's 3.89 %.
- PC-12: 320 of 844 attacked logs carry #213 tool-free payloads.

## 8. Recommendations and readiness

1. PC-02 to the family owner: add the quirk. This is a byte-changing regen item and needs the user's approval before any re-import (memory rule: list fixes before regeneration).
2. Route the scope rows of PC-01, PC-03, PC-07, PC-08 and PC-12 to the AgentDojo family owner under CC-07 and CC-09. PC-01 and PC-12 widen entries already proposed by tacit and shreeyavarma; the orchestrator may raise each to a cross-cutting item.
3. Datasheet disclosures:
   - PC-01: empty-final tail, with the sensitivity column labelled.
   - PC-03: 17 dropped final calls.
   - PC-04: 844 convention against the README's 874.
   - PC-05: class-I model (S3).
   - PC-12: split ASR.
4. Exclude no data. The 33 empty-final logs and every zero-success arm stay in the corpus.

**Readiness: `ready-with-caveats`.**

- The part imports correctly and deterministically: 45/45 mapped, validation 45/45, recompute 0 unexplained, j1/j2 byte-identical (190 files), judgements raw = mapped in 90/90, identity 0 mismatches, redaction 0 hits. The README tallies reproduce exactly.
- Caveats:
  - PC-02 is a profile omission. It does not block the import, but the fix should land before the round's import of this part, or the 154 logs miss the flag.
  - PC-01, PC-04 and PC-12 are S2 disclosures (verified). PC-05 (class-I model) is an S3 disclosure after reclassing.

## 9. Reproduction

Batch: wave 3, plan `tools/precheck/plans/wave3.toml`, entry `kongminos-agentdojo` / `head`, `--git ~/.agentprov/staging/10c/kongminos/jspace-agentdojo-950.git`.

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave3 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave3.toml
# steps: l1_scan.py (--git, --emit-fp), l1_10, l2_sample.py select, l2_import.py --jobs 2 / --jobs 1, l2_check.py --compare-with
```

Examiner scripts. They are read-only and read pinned blobs through `agentprov.ingest` strict JSON. S = `docs/reports/precheck/data/kongminos-agentdojo/exam-scripts`, W = `~/.agentprov/migration-work/precheck/kongminos-agentdojo`.

```bash
export GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file
uv run python -I S/pop.py W/exam/pop.json            # outcomes, H1-H12, CC-07, empty-final, trailing, H8 groups, L1-06 locator
uv run python -I S/extra.py W/exam/pop.json docs/reports/precheck/data/kongminos-agentdojo/l2-sample-head.json W/exam/extra.json  # H3 by (suite, IT), exposure, durations, tag excess
uv run python -I S/tail.py W/exam/tail.json           # empty-final time window, dropped final calls
uv run python -I S/os.py W/exam/pop.json W/exam/extra.json D/os1-population.json D/os2-sample.json   # OS-1, OS-2, H8 exposure, H10
git --git-dir ~/.agentprov/upstream/github.com/ethz-spylab/agentdojo.git cat-file -p a75aba76:src/agentdojo/agent_pipeline/llms/local_llm.py | sed -n 58,73p   # PC-01
grep -c local_model_raw_completion src/agentprov/adapters/agentdojo/profiles/kongminos-agentdojo.profile.toml   # PC-02: 0
grep -c kongminos src/agentprov/adapters/agentdojo/artefacts.toml   # PC-08: 0
```

Note: in `pop.py`, `h3.payload_in_tool_result` (a 60-character prefix match) reads 0 and is superseded by `extra.py`'s `<INFORMATION>` marker. This is an examiner-script property only.

Follow-ups for the orchestrator (not run):

| # | What | Command | When |
|---|---|---|---|
| 1 | PC-02 profile fix, then a re-import of the 154 affected logs as part of the round | family owner edits the profile; round import `uv run agentprov import kongminos-agentdojo --input <bare clone> --verify-against-pin --corpus <corpus>` through `tools/suite_queue.py --class import --cpu 2` | before the round, with the user's approval |
| 2 | Verifier pass on the 12 findings (adversarial) | done 2026-10-21: `uv run python -I ~/.agentprov/migration-work/precheck/kongminos-agentdojo/exam/verify/v.py $PWD <out.json>` | done |
| 3 | Route the scope rows (PC-01/03/07/08/12) and consider cross-cutting items for #220 and #213 (tacit, shreeyavarma, kongminos) | no command | before the round |
