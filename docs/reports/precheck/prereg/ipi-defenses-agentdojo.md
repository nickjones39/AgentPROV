# Pre-registration: `ipi-defenses-agentdojo`

| | |
|---|---|
| Corpus | `ipi-defenses-agentdojo` (family `agentdojo`, profile `ipi-defenses-agentdojo` v1, dialect/mapper `agentdojo.tracelogger`, variant `v1.k14`, identity table `tables/ipi_defenses_run_dirs.toml`, 19 rows) |
| Parts | `head`: Zenodo 22011266 (v4.0.0, concept 20731176), `AgentSecurity-IPIDefenses-v4.0.zip`, 3,305,018 B, md5 `1d61c6bd…`, sha256 `c2370724…`; three declared nested `tar.gz` (D-57) |
| Wave | 7 (phase-10j part; full pre-check; not examined in FA or E2, so there is no delta since E2) |
| Code commit | `065b0d36` or later (written on `precheck-corpora` at `6b76c15e`) |
| Date | 2026-10-14 (desk research retrieved 2026-10-15) |
| Status | **Written before any pre-check data check of this corpus.** Inputs: our own prior reports (phase-10j census, trials, routing; D-90 report; profile; registry; DECISIONS D-250..D-258) and desk research (`data/ipi-defenses-agentdojo/research.json`). No raw byte was read and nothing was computed from the data |

## 1. Sources (details and URLs in `research.json`)

- **Paper.** Khan, AlKhanbashi and Mohamed, *Computers* 2026, 15(9), 570, doi:10.3390/computers15090570. It was received on 21 July 2026, revised on 21 August, accepted on 28 August and published on 31 August 2026. There is one version of record, CC BY 4.0, and no correction. Its data statement cites the concept DOI 10.5281/zenodo.20731176. The profile's `[source].paper` still names the revised manuscript `computers-4482974`, which is stale.
- **Data record.** Concept 20731176 has four versions: 20731177 (aggregate files only), 21361725 (`v2`, a 170 B zip), 21418519 (`3.0.0`, now marked superseded for a trace-logging defect in the GPT-5.4-mini attack counts) and **22011266** (`4.0.0`, 2026-08-19, the latest and our pin). Zenodo's size and md5 equal our pin. The staged copy has the same size. The v4 record description is stale: it says "version 3" and lists the v3 file set.
- **Code.** There is no repository. The runner is `code/agentdojo_banking.py` inside the deposit (LOGDIR-patched; not verified, D-24). The harness is `agentdojo==0.1.35` (tag `a75aba76`, 2025-10-27). Relevant open AgentDojo issues are #209 (tool_filter gives zero tool calls; reported for a local model), #133 (an open question whether the detector runs after tool execution; not a confirmed defect), #192 (the detector works only in message mode) and #212 (`benchmark_version` is not passed on).
- **Licence.** Data and documentation are CC BY 4.0 and code is MIT (deposit README, recorded in the census). The record and the article are also CC BY 4.0. The embedded AgentDojo text is MIT. No use restriction was found.

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Zip files (level 1) | 26 (3 nested containers + 23 others: 2× README, 2× RUN_MAP, 4 CSV, 6 code, CHANGES ×2, MANIFEST.sha256, reconcile_tables.py, 5 figures) | census `gate` (d1:selected 26, d1:nested_container 3); Zenodo preview listing |
| Members in all | 3,234 | census `/sources/zenodo-22011266/members` |
| Tar regular files run1_mini_pdef / frontier_verify / run2_mini_rerun | 845 / 1,521 / 845 | D-90 report §2; profile `nested` notes |
| Tar directories; GNU `L` headers | 346/618/346; 967/1,450/802 (pax, links, devices 0) | D-90 report §2 |
| Selected logs = units = executions | **3,211** | registry and `tools/readme_corpora.toml` (3211, executions); census `byte_distinct`; trial |
| Not selected | 23 level-1 files (`select.not_execution_artefact` or not matched by the include glob); 5 stored as context artefacts | profile `include`, `context_artefacts` |
| Byte-distinct / content-distinct | 3,211 / 3,171 (37 content groups, 77 files) | census |
| Variants | `v1.k14` 3,211; `.incomplete` 0 | census |
| Header fields | `agentdojo_package_version` 0.1.35 ×3,211; `benchmark_version` null ×3,211; `error` null ×3,211; suite banking ×3,211 | census |
| `attack_type` | important_instructions 2,736 (19×144); null 475 (19×25) | census |
| Pre-pass logs (`injection_task_*`, attack none) | 171 (19×9) | profile quirk `observed` |
| System prompts | default `a021a92b…` (469 chars) 2,535; spotlighting variant `2954962b…` (642 chars) 676 | census; profile |
| Timestamp months | 2026-06: 845 (run 1 mini); 2026-07: 2,366 | census `ts_month` |
| Outcomes (all logs) | utility True 1,616 / False 1,595; security True 502 / False 2,709 | census |
| Trial | 3,209 ok, 2 ok with issues, 0 failed checks; chain: 3,219 members, 3,220 raw objects | `phase10j/trials.md` |
| Paper design | 14 configurations × 2 runs × (144 attacked + 16 benign) = 4,480 evaluations (*our arithmetic; the paper does not state the total*); **the deposit holds 19 of the 28 configuration-runs** | paper §4.8.2, Table 3 |
| L2 sample | about 190 units (38 strata × 5; see §6, open item) | README §4 rule |

## 3. Expected arms (L1-05 facets: run set × defence × model × attack)

Every cell has 169 logs: 144 `important_instructions` (16 user tasks × 9 injection tasks), 16 benign user tasks and 9 injection-task pre-passes.

| Run set (tar) | Paper run | Model | Defences (cells) | Logs |
|---|---|---|---|---:|
| `agentdojo_banking_pdef` (traces_run1_mini_pdef) | run 1 | gpt-5.4-mini-2026-03-17 | none, spotlighting_with_delimiting, repeat_user_prompt, transformers_pi_detector, tool_filter (5) | 845 |
| `mini_rerun` (traces_run2_mini_rerun) | run 2 | gpt-5.4-mini-2026-03-17 | same 5 | 845 |
| `verify_2026-07` (traces_frontier_verify) | run 2 | gpt-5.4-2026-03-05 | same 5 | 845 |
| `verify_2026-07` | run 2 | claude-sonnet-4-6 | none, spotlighting, repeat_user_prompt, transformers_pi_detector (4) | 676 |
| **Total** | | | **19** | **3,211** |

- **Missing, expected (README limitation 1; D-251).** The 9 frontier run-1 cells are missing, 1,521 logs at 169 per cell. The paper uses them as summary-only numbers.
- **Missing, contrary to the paper.** Two of those run-1 cells are frontier `repeat_user_prompt` (GPT-5.4 and Claude). The paper says it recovered them "through trace fingerprinting" and counts them as trace-backed (Table 5 "Both runs", denominators 96 and 32). See H5.
- **Missing by design.** Claude × tool_filter.
- **Extra relative to the paper's denominators.** The 171 pre-pass logs, which are not in BU (n = 16 per run).

## 4. Expected outcome rates (L1 population tally; L2 sample with Wilson 95%)

The paper's metrics map to logged fields as follows:

- **ASR** is the mean of `security` over the 144 attacked logs of a cell (`attack_type` important_instructions; `security` True means the injection task succeeded).
- **UUA** is the mean of `utility` over the same logs.
- **BU** is the mean of `utility` over the 16 `user_task_*` logs with attack none.
- The 9 `injection_task_*` pre-passes enter no paper rate. Their `security` is the benign constant True (quirk `benign_security_constant`).

The paper says its counts were verified from the per-instance traces, so the cells of the deposit should match **exactly**.

| Cell (run set / defence / model) | Paper ASR k/144 | Paper BU k/16 | Paper UUA | Table |
|---|---:|---:|---|---|
| pdef / none / mini | 5 | 12 | pooled with mini_rerun: 168/288 | 10; 9 |
| pdef / spotlighting / mini | 6 | 10 | pooled 168/288 | 10; 9 |
| pdef / pi_detector / mini | 1 | 6 | pooled 88/288 | 10; 9 |
| pdef / tool_filter / mini | 0 | 4 | pooled 91/288 | 10; 9 |
| pdef / repeat_user_prompt / mini | 1 | 13 | pooled 170/288 | 10; 9 |
| mini_rerun / none / mini | 6 | 12 | (pooled above) | 10, 11 |
| mini_rerun / spotlighting / mini | 3 | 9 | | 10 |
| mini_rerun / pi_detector / mini | 1 | 6 | | 10 |
| mini_rerun / tool_filter / mini | 0 | 4 | | 10 |
| mini_rerun / repeat_user_prompt / mini | 4 | 13 | | 10 |
| verify / none / gpt-5.4 | 0 | 9 | run 2 ∈ [17, 144] (pooled 161/288) | 10; 9 |
| verify / spotlighting / gpt-5.4 | 0 | 8 | ∈ [16, 144] (160) | 10; 9 |
| verify / pi_detector / gpt-5.4 | 0 | 5 | ∈ [0, 86] (86) | 10; 9 |
| verify / tool_filter / gpt-5.4 | 0 | 10 | ∈ [0, 114] (114) | 10; 9 |
| verify / repeat_user_prompt / gpt-5.4 | 0 | 8 | ∈ [15, 144] (159) | 10; 9 |
| verify / none / claude | 0 | 13 | ∈ [62, 144] (206) | 10; 9 |
| verify / spotlighting / claude | 0 | 12 | ∈ [81, 144] (225) | 10; 9 |
| verify / pi_detector / claude | 0 | 6 | ∈ [0, 86] (86) | 10; 9 |
| verify / repeat_user_prompt / claude | 0 | 14 | ∈ [62, 144] (206) | 10; 9 |

**Population checks against our census.** These are not new computations.

- Attacked successes: 502 − 475 = **27**. The paper's per-cell counts give 13 (mini run 1) + 14 (mini run 2) + 0 (frontier run 2) = **27**.
- BU successes should be 174 of 304.
- Mini UUA should be 685 of 1,440.
- That leaves 1,616 − 174 − 685 = **757** for frontier run-2 UUA plus pre-pass utility. So frontier run-2 UUA lies in **[586, 757]**.

**Further tables.**

- **Table 11** (mini run 2, each defence against none, paired by user task × injection task; fixed/caused): spotlighting 4/1, pi_detector 6/1, tool_filter 6/0, repeat_user_prompt 4/2.
- **Table 12** (attacked logs; frontier run 2 n = 144, mini n = 288). The paper reports rates (5.6%, 20.1%, ...); the zero-tool-call counts below are *derived* by us from those rates and n (fact-check note):

| Model | Defence | Zero-tool-call logs | Median tool calls | Median duration (s) |
|---|---|---|---:|---:|
| GPT-5.4 | none | 8/144 | 1 | 4.29 |
| GPT-5.4 | spotlighting | 29/144 | 1 | 3.74 |
| GPT-5.4 | pi_detector | 6/144 | 1 | 4.71 |
| GPT-5.4 | tool_filter | 82/144 | 0 | 3.78 |
| GPT-5.4 | repeat_user_prompt | 3/144 | 1 | 4.04 |
| GPT-5.4-mini | none | 1/288 | 2 | 3.91 |
| GPT-5.4-mini | spotlighting | 1/288 | 2 | 3.78 |
| GPT-5.4-mini | pi_detector | 0/288 | 3 | 5.37 |
| GPT-5.4-mini | tool_filter | 249/288 | 0 | 2.00 |
| GPT-5.4-mini | repeat_user_prompt | 3/288 | 2 | 3.69 |
| Claude | all four | 0/144 | 2 | 12.35, 11.98, 9.79, 11.10 (none, spot, pi, rup) |

**Sample.** At about 5 attacked units per cell, no L2 arm reaches n ≥ 20. The L2 rates are therefore reported with Wilson intervals only, and the comparison of record is the L1 tally (H3, H4).

## 5. Known quirks (expected-known findings)

| Id / source | Expected | Reference |
|---|---|---|
| `agentdojo.benign_security_constant` | 475 files, origin rule applied to 475 | profile `observed` |
| `agentdojo.injection_task_as_user_task_prepass` | 171 files | profile |
| `agentdojo.silent_rerun_last_pass_only` | 0 null-final logs | profile; census `last_assistant_null` False ×3,211 |
| `agentdojo.unexecuted_trailing_calls` | 2 calls in 2 logs (the trial's 2 "ok with issues") | profile; trials |
| `agentdojo.args_mutated_in_place` | 2,751 files | profile |
| `agentdojo.placeholder_args_never_injection_evidence` | 6,049 present, 6,049 null | profile |
| `agentdojo.provider_call_id_anomalies` | 0 null, repeated or duplicate ids | profile |
| `agentdojo.pi_detector_redaction` | 608 logs with 1,169 sentinel redactions, all in `*/transformers_pi_detector/*` (676 logs) | profile |
| `agentdojo.tool_filter_aux_llm` | 507/507 tool_filter logs carry filter messages | profile |
| `agentdojo.repeat_user_prompt_reinsertion` | 665 of 676 logs with copies | profile |
| `agentdojo.spotlighting_delimiters` | 635 of 676 logs with tool results | profile |
| `package_version_not_code_identity` | 0 logs without a package version; `code_identity = "unpinned"`, `verified_code = []` → D rules through `_unverified` twins | profile; D-24 |
| `benchmark_version` | null ×3,211 → `not_recorded` (D-102) | D-251 |
| README limitations | (1) lost first-run traces; (2) unpinned detector revision; (3) runs 1 and 2 re-evaluate the same instances | profile header; registry caveat; D-251 |
| `artefacts.toml` | **no entry scoped to this profile**. Generic classes still expected: `agentdojo.art.injection_task_as_user`, `.benign_security_constant`, `.silent_rerun`, `.max_iters_pending`, `.payload_not_reaching_agent` (detector redactions), `.defence_benign_intervention` (detector redactions in benign runs), `.banking_ut15_confound` (banking user_task_15) | `src/agentprov/adapters/agentdojo/artefacts.toml` |
| Withholding | none (D-257); census 0 secret-like strings | census §8 |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2. Also: `docs/MANIFEST.sha256` against the members (H11) |
| L1-02 strict parse | yes | 3,211 logs (census: parse ok ×3,211) |
| L1-03 encodings | yes | English benchmark text. The spotlighting delimiters and the detector sentinel are expected literals, not residues |
| L1-04 duplicates | yes | Within the part (0 byte pairs; 37 content groups) and across corpora with `l1_xdup.py` (expect 0) |
| L1-05 arm coverage | yes | §3: 19 cells × 169 |
| L1-06 secrets / account paths | yes | Counts and pointers only. Banking benchmark passwords and IBANs are benchmark content |
| L1-07 timestamps | yes | `evaluation_timestamp` per log; range June to July 2026 |
| L1-08 degenerate | yes | Expect 0 empty, 0 error-only, 0 incomplete. tool_filter zero-tool-call logs are expected behaviour (Table 12), not degenerate |
| L2 import / validate / recompute / determinism | yes | Archive input with nested tars. Recipe pending (wave 7, `WAVE7_PENDING`). Through the queue at `--cpu 2` |
| L2 A2 / A3 classes, evidence classes | yes | I-class identity (`pipeline_dir_is_model_identity@1`); D rules as `_unverified` twins |
| L2 identity | yes | 19 table rows. Model = logged `pipeline_name` = model directory. Defence from the directory above it (D-104) |
| L2 redaction | yes | Expect no account path in AER/SEM/PROV |
| L2 withholding | inert | No `[withhold]` (D-257) |
| L2 outcome sanity | partial | Population tally (L1) per cell is verdict-capable. The sample uses Wilson intervals only |
| Delta since E2 | no | Not in FA or E2 |

**Open item before L2.** `l1_families.STRATA` has no entry for this profile. The family default (`_prefix`, `pipeline_dir`, `suite`, `attack_dir`) gives only 2 strata here, because the layout has `{model_dir?}` and no `pipeline_dir`. The **pre-registered stratum key is (`model_dir`, `attack_dir`)**: 38 strata and about 190 units. If the L1 hook sees the chained label (`<zip member>!/runs/...`), expect `layout_mismatch` on every unit and the container path inside `model_dir`. That is an analysis-artefact, to be fixed in the tool, never a corpus finding.

## 7. Hypotheses (falsifiable; each threshold fixed now)

| Id | Expectation | Falsified if | Class if falsified |
|---|---|---|---|
| H1 | L1 selects exactly 3,211 logs in the 19 cells of §3, 169 each (144 / 16 / 9) | any count off by ≥ 1 | source-defect or mapping-defect |
| H2 | All 3,211 parse strictly: 0 duplicate keys, NaN, BOM, invalid UTF-8 or truncation; 0 incomplete, 0 empty, 0 error-only | any hit | source-defect, S3 |
| H3 | Every cell reproduces Table 10 exactly: ASR k/144 and BU k/16 (§4) | any cell off by ≥ 1 run → documentation-mismatch S2; off by > 15 pp → S1 candidate | documentation-mismatch |
| H4 | Mini UUA pooled per defence = 168, 168, 88, 91, 170 of 288. Each frontier run-2 cell lies within its §4 bound. The frontier run-2 UUA sum lies in [586, 757] | any value outside | documentation-mismatch, S2 |
| H5 | The `verify_2026-07` cells are run 2. Discriminators: Claude none 0/144 and 13/16 (run 1: 1/144 and 14/16); Claude repeat_user_prompt BU 14/16 (run 1: 15); GPT-5.4 tool_filter BU 10/16 (run 1: 7). The deposit holds no frontier run-1 cell, so the two recovered run-1 RUP cells are absent | any discriminator matches the run-1 value, or a run-1 frontier cell is found | documentation-mismatch, S2 (the deposit lacks traces the paper calls trace-backed: recorded, never an exclusion) |
| H6 | `mini_rerun` is run 2 and `agentdojo_banking_pdef` is run 1, as the profile and tar names say. Test: Table 10 per-run values, and Table 11 fixed/caused 4/1, 6/1, 6/0, 4/2 on `mini_rerun` | values match the other run set (labels swapped) or the pairs differ by ≥ 1 | documentation-mismatch, S3 (pooled numbers unaffected) |
| H7 | Attacked `security` True = 27 in total (mini 13 + 14, frontier 0). All 475 attack-none logs have `security` True | other totals | documentation-mismatch (S2) or mapping-defect |
| H8 | Exploratory. Table 12 is reproducible from the attacked logs: zero-tool-call counts within ±1 log per row, median tool calls exact, median `duration` within ±0.05 s (n = run 2 for frontier, both runs for mini) | larger gaps | documentation-mismatch, S3 (the definition of "tool call" is not stated: report both counting rules) |
| H9 | 0 provider keys or tokens and 0 account paths (`/Users/`, `/home/`, `C:\Users\`) in the 3,211 logs and the 5 context artefacts | any hit | security finding, reported at once |
| H10 | Timestamps: all 845 `pdef` logs in 2026-06. All 2,366 others in 2026-07, none after 2026-07-17 (the v3 deposit date, which already held both run-2 tars), with ±1 day allowed for an unstated time zone | out of range | source-defect, S3 |
| H11 | Every member listed in `docs/MANIFEST.sha256` exists and matches. The three tars match their listed digests | any mismatch or a missing member | source-defect, S2 |
| H12 | Content repeats: 37 ± 5 groups covering 77 ± 10 files (L1 fingerprint). No group spans two models. Groups spanning run sets are mainly tool_filter (> 50% of groups) | a cross-model group, or counts outside the bands | documentation-mismatch (copied runs), S2; band miss alone → note on the fingerprint definition |
| H13 | Detector sentinel: 1,169 redactions in 608 logs, all under `*/transformers_pi_detector/*`. Spotlighting prompt digest only in the 676 spotlighting logs. Filter messages only in the 507 tool_filter logs | any count or location differs | mapping-defect or census drift, S3 |
| H14 | L2 (about 190 units): every stage ok, 0 failing checks, 0 degenerate, 0 `adapter_defect`. Only the 2 known `unexecuted_tool_call` issues if they are sampled. `recompute --dry-run` reports 0 differences. A second import at another `--jobs` is byte-identical. Identity resolves for 100% of units: model and defence equal the table row | any failure | mapping-defect |
| H15 | Exploratory. If the pre-passes are the paper's matched canaries, the attack-none `injection_task_*` logs with `utility` True in the none-defence cells cover 7 goals in each mini run, 3 goals for GPT-5.4 (within {4, 5, 7}) and 1 goal for Claude (within {4, 7}). No trace-backed attack success targets a goal outside that set | different sets | none (refutes the canary = pre-pass reading only; report) |
| H16 | The L2 sample rates per cell lie inside the README §4 gap rule against §4 (Wilson 95% + 5 pp) | gap rule fires | investigate (identity or outcome mapping) |

Rule: no cell is excluded for zero attack successes. Every GPT-5.4 and Claude cell is expected to show 0/144.

## Fact-check (2026-10-15, adversarial; no data read)

Checked against the sources, not against the data:

- **Paper tables.** Tables 4, 5 (with its caption's 224/48/96/16/32 denominators), 6, 7, 9, 10, 11 and 12 were re-read from the HTML article (https://www.mdpi.com/2073-431X/15/9/570). Every value used in §4, H3 to H8 and H15 matches, including the run-1/run-2 discriminators of H5 (Claude none 1|0 and 14|13; Claude RUP BU 15|14; GPT-5.4 tool_filter BU 7|10). The publication history (21 July, 21 August, 28 August, 31 August 2026) matches. Crossref shows a CC BY 4.0 version of record with no correction (https://api.crossref.org/works/10.3390/computers15090570). The Data Availability Statement cites concept 10.5281/zenodo.20731176, so this is the paper behind these logs.
- **Discrepancy leads in the paper text.** Confirmed: two first-run RUP frontier configurations were "recovered through trace fingerprinting" (§4.8.1). The Table 12 caption repeats this, while the Table 5 trace basis says "Both runs". The detector-revision contradiction is also confirmed: the fourth limitation says the revision was fixed, while §4.5 and the sixth limitation say it was not pinned.
- **Data record.** Zenodo API (https://zenodo.org/api/records/22011266/versions) shows 4 versions. Their dates, sizes and md5 values are as stated, all are cc-by-4.0, and v4 is at revision 3. The v4 description is stale (it still says version 3). The v3 superseded note and the run-label inconsistency (`agentdojo_results_mini_rerun.csv` described as run 1) are confirmed. The Zenodo preview lists 26 files with the listed sizes.
- **Harness.** Tag v0.1.35 is `a75aba76…`, and the PyPI upload was 2025-10-27. At that tag, the `benchmark.py` default is `v1.2.2` and tool_filter is OpenAI-only (`agent_pipeline.py`). Issues #133, #158, #192, #209, #211 and #212 are open as described.
- **Census and arithmetic.** The census figures in `phase10j/census.json` match (3,234 members; gate 26/3/3,211; utility 1,616; security 502; 475/2,736; 845/2,366; 19 × 169). So do 27 = 13 + 14, 174/304, 685, [586, 757] (757 minus 171 pre-pass logs) and the per-cell UUA bounds.

Corrected:

- **4,480 evaluations.** This total is our arithmetic, not a figure in the paper (marked in §2).
- **Table 12 zero-tool-call counts.** These are derived from the paper's percentages (marked in §4).
- **AgentDojo issues.** #133 is an open user question, not a confirmed defect. #209 was reported for a local model, so the link to the Table 12 rates is only an analogy (§1).
- **Model snapshot (`research.json`).** OpenAI's model page does name `gpt-5.4-2026-03-05` (https://developers.openai.com/api/docs/models/gpt-5.4). This corrects "no public page names this snapshot".

Unverifiable here:

- The deposit README's licence wording is inside the payload. It is taken from census §3.
- Whether the LOGDIR-patched runner matches the runs is not verified (D-24).
