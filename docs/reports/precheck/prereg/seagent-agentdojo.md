# Pre-registration: `seagent-agentdojo`

| | |
|---|---|
| Corpus | `seagent-agentdojo` (family `agentdojo`, profile `seagent-agentdojo` v1, dialect/mapper `agentdojo.tracelogger`, variant `v1.k14`) |
| Parts | `head`: Zenodo 10.5281/zenodo.23218779, `seagent-acsac2026-ae-v2.zip` (237,707,785 B, md5 `37d4b444…`, sha256 `e15a8f0f…764bd`) |
| Wave | 5 (full pre-check; not examined in FA or E2, so there is no delta since E2) |
| Code commit | `065b0d36` or later |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Inputs: our own prior reports (phase 10e §3.1, `docs/reports/phase10f/`, `docs/reports/deferrals/part-a-trials.md`, profile, run-dir table, DECISIONS) and desk research (`data/seagent-agentdojo/research.json`). No run log was read and nothing was computed from the logs. Desk research read Zenodo metadata, the zip central directories (names, CRC32, sizes) of all four record versions by HTTP range, and six documentation members (README, CHANGELOG, LICENSES, EVALUATION, `aggregate-results/agentdojo-provenance/*`, `paper.pdf`) |

## 1. Sources (details and URLs in `research.json`)

- **Accepted paper.** SEAgent (ACSAC 2026), shipped as `seagent-ae/paper.pdf` in the deposit. Table 2 gives macro ASR and UUA, and Table 3 gives per-suite ASR and UUA, for Vanilla, AgentSpec-LLM, PVAgent, SEAgent and SEAgent-RF. The agent is DeepSeek-V3.
- **Preprint.** arXiv:2509.22256 ("CSAgent"), versions v1 (2025-09-26) to v4 (2026-01-14). It has no AgentSpec arm. Travel used 140 attacks in v1 and 120 from v3. The v3/v4 Table 4 CSAgent cells for banking, slack and workspace are stale v1 values.
- **Authors' provenance note.** In the deposit, `aggregate-results/agentdojo-provenance/` (README, workbook `agentdojo-final-results.xlsx`, `vanilla-security-summary.csv`) states three things:
  - The paper's Vanilla row comes from an original summary whose episodes are unavailable.
  - The deposited December 2025 baseline run gives 47.18% ASR and 52.09% UUA.
  - SEAgent workspace UUA is 55.71% (312/560). The paper's 50.71% is an error.
- **Data record.** The concept record has 4 versions. Our pin is the latest. The 5,342 logs are CRC-identical in v2 and v4. In v1 (2026-03-26) the refined-policy runs were labelled `seagent`, and the 1,081 initial-policy logs were absent.
- **Licence.** Data CC-BY-4.0 and code Apache-2.0 (deposit `LICENSES.md`). The AgentDojo text is MIT. `paper.pdf` is not relicensed. There is no use restriction beyond attribution.

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Zip members | 26,033 | central directory (2026-10-14); part-A trial `expand` |
| Selected logs (units) | **5,342** | `tools/readme_corpora.toml` (5342, census); census `/units/agent_execution`, `/gate/selected` |
| Context artefacts | 37 (3 docs, 10 `benchmark_results.csv`, 24 `*.log`; largest log 152,139,448 B) | part-A trial (5,379 selected − 5,342); central directory |
| Not selected | 20,654 (importer) / 20,691 (census gate, which counts the context artefacts as not selected) | part-A trial; census `/gate` |
| Executions | 5,342; 0 degenerate; 94 counted as failed (`missing_tool_result` at error severity) | census `status.mapped`; part-A trial |
| Variants | `v1.k14` 5,342 | census |
| Path classes | 4,685 `injection_task_*/important_instructions/*.json`; 657 `none.json` (172 injection-task pre-passes, 485 perf benign) | phase 10e §3.1; census quirks |
| Package / benchmark | `agentdojo_package_version` 0.1.34 and `benchmark_version` v1.2.1 | phase-10e single-log read; census `files_without_package_version` 0 |
| Pipeline names | `deepseek-v3-250324-seagent_mcp` 2,996; `deepseek-v3-seagent_mcp` 226; `deepseek-v3-250324-agentspec` 1,060; `deepseek-v3-250324` 950; `deepseek-v3` 110 | `phase10f/seagent-agentdojo.run-dirs.json` (sums) |
| Census issue files | earlier_attempts_unobservable 5,342; unattributed_additional_user_message 863; agentdojo.unknown_message_shape 541; orphan_tool_result 541; unexecuted_tool_call 317; missing_tool_result 94 | census `/files_by_issue_code` (part-A trial: equal) |
| Quirks | benign_security_constant 657; injection_task_as_user_task_prepass 172; args_mutated_in_place 5,135; placeholder args 15,902 (all null); unexecuted_trailing_calls 392 calls / 317 logs; null_final 0; incomplete_run 0; empty messages 0 | census `/declared`, `/measured`; profile `observed` |
| L2 sample | **200** (40 strata, kind × arm × suite, each with ≥ 16 units, × 5) | README §4 with `l1_families.STRATA["seagent-agentdojo"]` |

## 3. Expected arms (L1-05: kind × arm × suite; attack inside security dirs)

Security directories: attacked (`important_instructions`) / pre-pass (`none`). Perf directories: benign user tasks.

| Arm (dir) | Paper name | Defence id (D.6.18) | banking | slack | travel | workspace | Perf (b/s/t/w) | Total |
|---|---|---|---:|---:|---:|---:|---|---:|
| `baseline` | (Vanilla, different run) | none | 144/9 | 105/5 | 120/6 | 560/14 | 16/21/20/40 | 1,060 |
| `agentspec` | AgentSpec-LLM | agentspec | 144/9 | 105/5 | 120/6 | 560/14 | 16/21/20/40 | 1,060 |
| `pvagent` | PVAgent | pvagent | 144/9 | 105/5 | **140/7** | 560/14 | 16/21/20/40 | 1,081 |
| `seagent` | SEAgent | seagent-initial | 144/9 | 105/5 | **140/7** | 560/14 | 16/21/20/40 | 1,081 |
| `seagent-RF` / `seagent-rf` | SEAgent-RF | seagent-refined | 144/9 | 105/5 | 120/6 | 560/14 | 16/21/20/40 | 1,060 |

- **Design.** AgentDojo v1.2.1 has 16, 21, 20 and 40 user tasks and 9, 5, 7 and 14 injection tasks, which gives 144, 105, 140 and 560 pairs. The paper drops one travel attack, upstream travel `InjectionTask6` (model-output content), so it counts 929 attacked runs per arm.
- **Missing.** The three 126-log travel directories lack injection_task_6. The paper's Vanilla security episodes and the July Vanilla perf episodes are not deposited. Neither are the AgentDojo episode logs of the Table 7 sensitivity runs (**corrected:** their generated policies and some Gemini generation logs are deposited under `artifact/results/model_sensitivity/`, outside the include glob) or the arXiv "agent reflection" variant.
- **Extra.** injection_task_6 appears in pvagent and seagent travel (20 attacked and 1 pre-pass each). The December baseline run is extra relative to the paper's Vanilla row.
- **Identity.** Pipeline names do not identify the defence, because three arms log `*-seagent_mcp`. The defence comes from the run-directory table (D-152). 336 logs carry the model id `deepseek-v3` without a date.

## 4. Expected outcome rates (comparators)

Metric mapping (EVALUATION.md, paper §7.1; `security = true` means attack success):

- **ASR** = `security == true` / attacked logs.
- **UUA** = `utility == true` / the same logs.
- Travel is restricted to injection tasks 0–5 for every arm.
- Pre-pass logs (`injection_task_*/none`) are in neither metric.
- **Benign utility** = the mean over the 4 suites of `utility == true` / perf logs.
- Macro = the unweighted mean of the 4 suites.

| Arm | banking ASR / UUA | slack ASR / UUA | travel ASR / UUA (of 120) | workspace ASR / UUA | macro | Source |
|---|---|---|---|---|---|---|
| agentspec | 6 / 58 of 144 | 43 / 19 of 105 | 41 / 29 | 20 / 311 of 560 | 20.72 / 34.52 | paper T3, workbook |
| pvagent | 0 / 53 | 0 / 5 | 19 / 48 | 4 / 283 | 4.14 / 33.03 | paper T3, workbook |
| seagent | 0 / 65 | 0 / 26 | 0 / 49 | 0 / **312** (paper prints 284 = 50.71%) | 0 / 41.61 | workbook, provenance README |
| seagent-RF | 0 / 81 | 0 / 40 | 0 / 65 | 0 / 383 | 0 / 54.23 | paper T3, workbook |
| baseline (deposited) | – | – | – | – | 47.18 / 52.09 | provenance README (macro only) |
| (paper Vanilla, not deposited) | 65 / 86 | 90 / 68 | 59 / 35 | 36 / 355 | 46.61 / 54.26 | context only |
| pvagent travel of 140 | | | 26 / 57 | | | arXiv v1 T4 |
| Benign utility (perf, macro %) | baseline 75.12; pvagent 34.0025; seagent 47.1425; seagent-rf 70.045 | | | | | `artifact/results/final_res_perf/AgentDojo*.txt` |
| Latency (perf, macro s) | baseline 10.7525; pvagent 19.225; seagent 11.27; seagent-rf 10.81 | | | | | same; workbook sheet 2 |

## 5. Known quirks and decisions

- **Profile.** `seagent-agentdojo` v1: `verified_code = []`, so every family D rule cites its `_unverified` twin (D-24, D-150). The quirk counts are in §2. Identity comes from the table `tables/seagent_run_dirs.toml` (40 rows, keyed by run directory; D-104, D-152).
- **D-153.** The 960 SEAgent guard warnings are user-role messages after a tool result (863 logs) and stay `unattributed_additional_user_message`. The 740 PVAgent assistant messages without `tool_calls` (541 logs) leave orphan tool results.
- **D-154/D-156.** The census ran under a dev `local` origin. Two fixes have since landed: archive inputs (D-200) and the member-origin layout locator (regen item 18; `test_member_origins_seal_and_validate_in_release_mode_d156`). The part-A trial (scratch) imported, validated, derived, recomputed and chain-verified all 5,342 logs.
- **Registry.** The part is still `planned` (deferrals DF-3). The part-A trial had to flip it in a scratch worktree.
- **`artefacts.toml`.** It has no entry scoped to this source. Generic AgentDojo artefacts apply in kind and are tracked by profile quirks.
- **Known AgentDojo 0.1.34 / v1.2.1 issues.**
  - #189/#168: slack injection_task_5 is scored from proposed calls.
  - #181: banking injection tasks 0/1/3.
  - #161: banking user_task_5.
  - #110 (banking user_task_6) and #128 (workspace user_task_16; **corrected:** #128 is an unmerged PR whose fix landed via PR #130) are fixed only in the v1.2.2 tasks (agentdojo 0.1.35).
  - #121: tool docstrings were truncated before 0.1.35.
  - #214: `\uXXXX` escapes.

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2: members, 5,342 selected, 37 context, per-dir counts (§3) |
| L1-02 strict parse | yes | Every log. The census mapped all 5,342 without a crash |
| L1-03 encodings | yes | Count `\uXXXX` residues (#214). CJK is possible in DeepSeek output; report it, it is not a defect |
| L1-04 duplicates | yes | Within the part and across corpora (`l1_xdup.py`). The pipeline names occur in no other source (phase 10e) |
| L1-05 arm coverage | yes | §3 (40 dirs; travel IT6 presence) |
| L1-06 secrets / account paths | yes | The 5,342 logs **and** the 24 `.log` + 10 csv context artefacts, which are stored raw. Counts and pointers only. Count placeholder tokens (the deposit README says paths were replaced by placeholders) |
| L1-07 timestamps | yes | `evaluation_timestamp` (naive) against the run-directory dates. `duration` feeds the latency comparison |
| L1-08 degenerate | yes | Expect 0 empty, 0 incomplete, 0 error-only, 0 null-final |
| L2 import / validate / recompute / determinism | yes | Archive input through `l2_import.py` (staging `10f/seagent-zenodo-23218779`), queue `--cpu 2` |
| L2 A2 / A3 classes, evidence classes | yes | Family D rules only as `_unverified` twins; issue codes as in the census |
| L2 identity | yes | Model and defence from the table; 336 date-less ids kept |
| L2 redaction | yes (generic) | No profile rules; expect 0 account paths in AER/SEM/PROV |
| L2 withholding | inert | CC-BY-4.0, policy include; only the generic secret path |
| L2 outcome sanity | partial | With 5 units per stratum, 20 security units per arm, so **at most** 20 attacked runs per arm (about 19 expected after pre-pass draws; **corrected** from "about 18"). The arm is verdict-capable under README §4 only if all 20 are attacked; otherwise Wilson intervals only. Verdicts come from the population tallies H7–H10 |
| Delta since E2 | no | Not in E2 |

## 7. Hypotheses (falsifiable; thresholds fixed now)

| Id | Expectation | Falsified if | Class if falsified |
|---|---|---|---|
| H1 | L1 selects 5,342 logs and 37 context artefacts out of 26,033 members, with the per-directory and per-attack counts of §3 | any count differs by ≥ 1 | mapping-defect or census drift |
| H2 | All 5,342 parse strictly: 0 duplicate keys, NaN, BOM, invalid UTF-8, truncation or I-JSON overflow | any hit | source-defect |
| H3 | U+FFFD 0, mojibake 0, bidi/tag characters 0 | any hit | source-defect, S3 |
| H4 | 0 byte-identical pairs among the 5,342; 0 cross-corpus overlap; 0 identical attacked trajectories across arms | ≥ 1 | documentation-mismatch (copied or relabelled runs), S2 |
| H5 | `agentdojo_package_version` 0.1.34 and `benchmark_version` v1.2.1 in all 5,342 | any other value | documentation-mismatch, S3 |
| H6 | The 126-log travel dirs (agentspec, baseline, seagent-RF) contain no `injection_task_6`. The 147-log dirs (pvagent, seagent) contain exactly 20 attacked and 1 pre-pass of it | otherwise | documentation-mismatch, S2 |
| H7 | A population tally (travel IT0–5) reproduces every agentspec, pvagent, seagent and seagent-RF cell of §4 to within ±1 run, including seagent workspace UUA 312 (not 284) | any cell off by > 1 run; > 15 pp makes it an S1 candidate | documentation-mismatch, S2 (or mapping/identity error) |
| H8 | The deposited baseline gives macro ASR 47.18 ± 0.10 and UUA 52.09 ± 0.10, i.e. it does **not** reproduce the paper's 46.61 / 54.26 | macro outside the band | documentation-mismatch, S2 |
| H9 | pvagent travel on all 140 attacked logs gives ASR 26 and UUA 57 (± 1), i.e. arXiv v1 used the deposited July run; the IT6 subset is then 7 / 9 of 20 | off by > 1 | documentation-mismatch, S3 |
| H10 | Benign utility macro (perf) is baseline 75.12, pvagent 34.00, seagent 47.14 and seagent-rf 70.05, each ± 0.05 pp | outside | documentation-mismatch, S2 |
| H11 | (exploratory) The perf `duration` macro is baseline 10.75 s, pvagent 19.23 s, seagent 11.27 s and seagent-rf 10.81 s (± 0.05 s), if `duration` is the source | outside (report the source used) | documentation-mismatch, S3 |
| H12 | `evaluation_timestamp` is present in 5,342. Per arm it falls within ±2 days of the run-directory dates (pvagent 2025-07-29/30; seagent 2025-12-12/13 and 2025-12-29; seagent-RF 2025-12-18..29; baseline 2025-12-08..29; agentspec 2026-03-24..26), and none is after 2026-03-26T14:20Z (record v1) | any outside | source-defect, S3 |
| H13 | 0 provider keys or bearer tokens and 0 account paths (`/Users/`, `/home/`, `C:\Users\`) in the 5,342 logs and the 34 stored text context artefacts | any hit | security finding, reported at once |
| H14 | 0 empty, 0 incomplete (outcome keys absent), 0 error-only, 0 null-final logs | any | source-defect, S3 |
| H15 | The 960 extra user-role messages (863 logs) occur only in `seagent` and `seagent-RF/rf` dirs. The 740 call-less assistant messages (541 logs) occur only in `pvagent` dirs | any outside, or other totals | mapping-defect or census drift |
| H16 | (exploratory, #189) Count the slack `injection_task_5` attacked logs with `security == true` per blocking arm in which a success-defining call has no tool result | – (reported; > 0 means the arm's slack ASR includes blocked proposals) | expected-known upstream defect, S2 disclosure |
| H17 | L2 on 200 units: every stage ok, 0 degenerate, 0 `adapter_defect`. `failed` equals the sampled units among the 94 `missing_tool_result` logs. `recompute --dry-run` reports 0 differences, and a second import with a different `--jobs` is byte-identical. Identity resolves for 100% (5 defences, 2 model ids). 0 agentdojo-family D citations lack `_unverified`. 0 account paths in AER/SEM/PROV | any failure | mapping-defect (or analysis-artefact if the planned status blocks `l2_import`) |
| H18 | The L2 sample rates per arm lie within the README §4 gap rule against §4 (Wilson intervals; not verdict-capable below 20 attacked runs per arm, which at most 20 can reach) | gap rule fires | investigate (identity or outcome mapping) |

Rule: no arm or stratum is excluded for zero attack successes. Ten arm-suite cells are expected at 0% ASR: all of seagent and seagent-RF, and pvagent banking and slack. The baseline arm stays in the corpus although it is not the paper's Vanilla run; this is disclosed, not excluded.

## Fact-check (2026-10-14, adversarial pass before any data check)

Method: Zenodo API (`https://zenodo.org/api/records/23218779/versions`); zip central directories of record versions 19236299, 22771109 and 23218779 read by HTTP range (names, CRC32, sizes only); documentation members fetched by range and CRC-checked (`paper.pdf`, `LICENSES.md`, `README.md`, `CHANGELOG.md`, `EVALUATION.md`, `aggregate-results/agentdojo-provenance/{README.md, agentdojo-final-results.xlsx, vanilla-security-summary.csv}`, `artifact/results/final_res_perf/AgentDojo*.txt`, `artifact/agentdojo/{LICENSE, pyproject.toml}`, `artifact/agentspec/README.txt`); arXiv abs and HTML v1/v4; GitHub API for ethz-spylab/agentdojo (tag, issues, PRs, files at v0.1.34) and haoyuwang99/AgentSpec. No run log was opened; counts below come from member names only.

Confirmed:
- **Outcome comparators (§4).** Accepted-paper Table 2 (macro) and Table 3 (per suite) print every Vanilla, AgentSpec-LLM, PVAgent, SEAgent and SEAgent-RF cell as given, including SEAgent workspace UUA 50.71%. The workbook sheet "AgentDojo security" has the same cells except SEAgent workspace 55.71 (note: "consistent with 312/560"), and its formula macros give 46.6125/54.26, 20.715/34.5225, 4.135/33.0275, 0/41.61, 0/54.2275. The paper's own macro 41.61 is consistent with 55.71, not 50.71. All count conversions (×144/105/120/560) are integral. arXiv v1 Table 4 PVAgent travel 18.57/40.71 (26/57 of 140) and v4 Table 4 (stale CSAgent banking/slack/workspace UUA 40.97/18.10/50.71, which average to 37.65 with travel 40.83, not 41.61) confirmed. Provenance README states the December baseline gives 47.18/52.09 and that the paper's Vanilla episodes are unavailable.
- **Perf / latency.** `AgentDojo.txt`: Vanilla 75.12 / 10.7525 s, PVAgent 34.0025 / 19.225 s, SEAgent 47.1425 / 11.27 s; `AgentDojo-refined.txt`: SEAgent 70.045 / 10.81 s. Utility drops 37.24% and 6.76% follow from these; PVAgent 54.7% relative drop against the paper's "30.31%" (the paper sentence is ambiguous in scope). Workbook latency sheet: overhead 78.80% (December Vanilla) and 103.98% (July Vanilla 9.425 s).
- **Counts (§2, §3) from the v4 central directory:** 26,033 members; 5,342 members match the include glob; 37 context artefacts (3 md, 10 csv, 24 log; largest 152,139,448 B); 4,685 attacked and 657 `none.json`; 40 run directories with exactly the per-directory attacked/pre-pass/perf counts of §3; arm totals 1,060/1,060/1,081/1,081/1,060; IT6 20 attacked + 1 pre-pass in pvagent and seagent travel only; pipeline-directory sums 2,996/226/1,060/950/110; the 336 date-less `deepseek-v3` logs are exactly security/baseline slack 110, security/seagent-RF travel 126, perf seagent workspace 40, perf seagent-rf travel 20 and workspace 40; run-directory dates as in H12. Census gate 5,342 + 20,691 = 26,033 and part-A 5,379 + 20,654 = 26,033. Census issue and quirk counts and registry `planned` status equal our own reports.
- **Data record.** Four versions, dates, file names, sizes and md5 as stated; v3 reuses the v2 zip (same md5) plus the 5,412,352 B supplement; v1 creator Anonymous. v2 and v4 logs CRC+size identical (5,342); v1's 4,261 logs are identical to v4 after renaming `seagent` to `seagent-RF`/`seagent-rf`; v4 adds 1,081 logs (security/seagent 984, perf/seagent 97). v4 changes only README, EVALUATION and MANIFEST.json among v2 members and adds 128 members. The sha256 pin was not recomputed here (no payload download); it rests on the part-A trial pin check.
- **Licence.** All four versions cc-by-4.0; `LICENSES.md` terms as summarised; vendored AgentDojo LICENSE is MIT; AgentSpec revision e6fa3902e2cf matches the deposit README.txt and the upstream repository has no licence.
- **Harness.** Vendored `pyproject.toml` version 0.1.34; upstream tag v0.1.34 = 928bbae8 (2025-06-02T13:47Z), `--benchmark-version` default v1.2.1; travel InjectionTask6 (model-output content, empty ground truth) is not overridden in v1.2; at v0.1.34 only slack InjectionTask5 defines `security_from_traces`. Issue states: #189 closed 2026-09-07, #168/#181/#161/#214 open, #121 fixed by PR #129 and #110 via PR #130 (both merged 2025-10-27, released in 0.1.35), #139 closed 2026-04-02.
- **Paper attribution.** The deposit README and Zenodo description name the ACSAC 2026 paper; the arXiv preprint has the same four authors. arXiv metadata title omits "Framework", which the paper body title keeps (as in `tools/readme_corpora.toml`).

Corrected (in this file and `research.json`):
- Table 7 sensitivity: only its AgentDojo episode logs are absent; policies and some generation logs are deposited.
- #128 is a PR that was closed unmerged; the fix shipped via PR #130.
- L2 per-arm attacked count: at most 20 (about 19 expected), not "about 18"; a verdict is possible only if all 20 security draws are attacked.

Notes (no new expectation):
- The authors' macro ASR for the December baseline (47.18%) equals the arXiv v1 Vanilla macro ASR (47.18%, travel of 140, UUA 53.75%). This may be a coincidence; H8 decides it.
- `artifact/evidence/ae-validation/agentdojo/` holds 9 AgentDojo-format episode logs of the 2026-09 AE validation (attack `important_instructions_no_model_name`). The include glob does not select them, so they count as not selected.
- Unverifiable here: model provider of `deepseek-v3-250324`; the per-suite December baseline; whether guards leave blocked calls in `tool_calls`; scope of the 30.31% and 23.32% drops.
