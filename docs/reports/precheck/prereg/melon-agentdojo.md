# Pre-registration: `melon-agentdojo`

| | |
|---|---|
| Corpus | `melon-agentdojo` (family `agentdojo`, profile `melon-agentdojo` v1, dialect/mapper `agentdojo.tracelogger`) |
| Parts | `head`: GitHub `xwsdid/MELON` @ `71d99dfff5ef98ffb25bac451909f3e10af9e27f` |
| Wave | 2 (full pre-check; not examined in FA or E2, so there is no delta since E2) |
| Code commit | `065b0d36` or later |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Inputs: our own prior reports and desk research only (`data/melon-agentdojo/research.json`). No raw data was read and nothing was computed from it |

## 1. Sources (details and URLs in `research.json`)

- **Repository.** <https://github.com/xwsdid/MELON>. A course project. It is not a GitHub fork, but it carries the AgentDojo history up to `18b501a6` (2026-03-30). The pin is HEAD; there have been no commits since 2026-06-17. It has two commits of its own. `605d9999` adds the runs, the report and the README. `71d99dff` changes only `pi_detector.py`: comments are translated to Chinese, and behaviour is unchanged. **[Corrected by fact-check]** The committed code is nevertheless not the run code for every arm: the `melon_r_prompt` system text (92 chars, sha256 82ce7af3…) is exactly the first five of the six lines of the RECOVERY text at the pin, so the melon_r runs used an earlier, uncommitted `pi_detector.py`; melon_rp needs a `MELONRP` class that the pin lacks (imported by `tests/test_melonrp_probe_small.py`); and the committed `tests/run_small_compare_melon.py` lists task pairs 11..20, while the melon_rp logs are the diagonal pairs 1..8.
- **Results.** The only description of the runs is the fork's README "experiment results" tables and `report/MELON_SATM_AT_补充内容.md` (sections 6.2, 6.3 and the summary). They give GPT-4o banking results for 3 attacks. The underlying paper is MELON (arXiv:2502.05174, ICML 2025, v1 to v4). It reports all-suite AgentDojo v1 numbers for other models. Those numbers serve as context only, never as a comparison target.
- **Data record.** There is no Zenodo, HF or Figshare record. Integrity rests on the git blob ids at the pin.
- **Licence.** MIT (the upstream AgentDojo LICENSE, with no fork copyright line). The MELON detector code derives from `kaijiezhu11/MELON`, which has no licence.

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Tree entries at pin | 38,780 | profile `expected_files`; phase-10c census `all_tree_entries` |
| JSON blobs | 38,592 | phase-10c census `files.json_blobs` |
| Absent blobs (report PDF ×2, DOCX) | 3 | census/trial `pin.absent_blobs` |
| Selected logs (units) | **1,911** | `tools/readme_corpora.toml` (count 1911, census); `docs/reports/phase10d/melon-agentdojo.census.json` `/files`; GitHub tree at pin |
| `select.owned_elsewhere` (owner agentdojo) | 36,679 | profile; trial `counters.excluded` |
| Non-TraceLogger JSON | 2 (`.devcontainer/devcontainer.json`, `runs/detection_stats.json`) | phase-10c census `non_tl_dirs` |
| Executions | 1,911 (sealed_clean 1,905, with issues 6) | `melon-agentdojo.trial.json` (jobs 8 and 3, byte-identical) |
| Variants | v1.k14 1,905; v1.k14.incomplete 6 | census `variants` |
| Register codes | accounting_unverifiable 1,909; earlier_attempts_unobservable 1,911; incomplete_run 6 | trial `register_codes` |
| Suites | banking 1,894; travel 17 | phase-10c novel census |
| Attacks | ignore_previous 864; direct 671; important_instructions 288; none 88 | phase-10c novel census |
| `benchmark_version` / package | v1.2.2 / 0.1.35 in all 1,911 | phase-10c novel census |
| Timestamp range (naive) | 2026-05-24 20:27:41 .. 2026-06-16 16:48:15 (May 125, June 1,786) | phase-10c novel census |
| Outcome fields (complete logs) | utility True 904 / False 1,001; security True 125 / False 1,780; 6 without either key | phase-10c novel census |
| L2 sample | ≈134 units (26 strata × 5, plus the 3 strata with fewer than 5 units: 1 + 1 + 2) | README §4 rule applied to the strata below |

## 3. Expected arms (L1-05 facets: model × defence × suite × attack)

All 29 strata come from the GitHub tree at the pin and agree with the phase-10c `model_attack` counts. "none" means the injection-task pre-pass (injection tasks run as user tasks), with 9 per complete banking arm.

| Pipeline dir | banking direct | banking ignore | banking important | banking none | travel direct | travel none | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| gpt-4o-2024-05-13-melon | 65 | – | – | 9 | – | – | 74 |
| gpt-4o-2024-05-13-melon_at | 144 | 144 | 144 | 9 | – | – | 441 |
| gpt-4o-2024-05-13-melon_sm | 144 | 144 | 144 | 9 | – | – | 441 |
| gpt-4o-2024-05-13-melon_r | 13 | – | – | 9 | 8 | 5 | 35 |
| gpt-4o-2024-05-13-melon_rp | 8 | – | – | 8 | – | – | 16 |
| gpt-4o-mini-2024-07-18-melon | – | 144 | – | 9 | – | 1 | 154 |
| gpt-4o-mini-2024-07-18-melon_at | 144 | 144 | – | 9 | – | – | 297 |
| gpt-4o-mini-2024-07-18-melon_sm | 144 | 144 | – | 9 | – | – | 297 |
| gpt-4o-mini-2024-07-18-melon_r | – | 144 | – | 9 | 1 | 2 | 156 |
| **Total** | 662 | 864 | 288 | 80 | 9 | 8 | **1,911** |

- **Design (README).** GPT-4o on banking: 4 defences (melon, melon_r, melon_sm, melon_at) × 3 attacks, 144 runs per cell (**[fact-check]** 144 is implied by the percentages and the banking task counts, 16 × 9; the README does not state n). Report 6.2.1 says the No Defense, MELON and MELON-R rows continue the docx report's Table 1 (an absent blob).
- **Missing cells.** gpt-4o melon important/ignore and melon_r important/ignore have 0 logs. gpt-4o melon direct is partial (65 of 144) and melon_r direct is partial (13 of 144). There is no undefended arm, although the README reports a "No Defense" row. There are no benign user-task runs.
- **Extra cells.** Every gpt-4o-mini arm, melon_rp (which is not a registered defence at the pin), and the 17 travel logs. None of them has a reported number. They are not excluded on that ground, nor for having zero successes (user rule; D-279 addendum in DECISIONS: zero-success MELON arms stay in).

## 4. Expected outcome rates (L2 outcome sanity; also the population tally H6/H7)

The metrics map to logged fields as follows (AgentDojo):

- **UA** is the mean of `utility` over attacked logs of the cell (attack ≠ none).
- **ASR** is the mean of `security` over the same logs, where `security` True means the injection task succeeded.
- **BU** (the report's sense) is the mean of `utility` over the 9 `injection_task_*` pre-pass logs (attack none). Their `security` is the benign constant (quirk `benign_security_constant`) and enters no rate.
- Incomplete logs (no outcome keys) are excluded from the denominators and are reported separately.

| Arm (banking) | Logs | Paper UA | Paper ASR | Implied k/144 | Table |
|---|---:|---:|---:|---|---|
| gpt-4o melon_sm · direct | 144 | 52.08% | 0.00% | 75 / 0 | README; report 6.2.1 |
| gpt-4o melon_sm · important_instructions | 144 | 33.33% | 2.08% | 48 / 3 | README; report 6.2.1 |
| gpt-4o melon_sm · ignore_previous | 144 | 52.78% | 0.00% | 76 / 0 | README; report 6.2.1 |
| gpt-4o melon_sm · none (BU) | 9 | 88.89% | – | 8/9 | report 6.2.1 |
| gpt-4o melon_at · direct | 144 | 62.50% | 0.00% | 90 / 0 | README; report 6.3.1 |
| gpt-4o melon_at · important_instructions | 144 | 43.06% | 13.19% | 62 / 19 | README; report 6.3.1 |
| gpt-4o melon_at · ignore_previous | 144 | 60.42% | 0.00% | 87 / 0 | README; report 6.3.1 |
| gpt-4o melon_at · none (BU) | 9 | 100.00% | – | 9/9 | report 6.3.1 |
| gpt-4o melon · direct | **65** | 38.19% | 0.00% | 55 / 0 (of 144) | README (partial arm: rate comparison only) |
| gpt-4o melon_r · direct | **13** | 45.83% | 2.08% | 66 / 3 (of 144) | README (13 logs: no comparison) |
| gpt-4o melon / melon_r · important, ignore | **0** | 29.86–44.44% | 0.00–8.33% | – | README (unbacked) |
| gpt-4o-mini all arms, melon_rp, travel | – | – | – | – | none reported: rates with Wilson 95% only |

At about 5 sampled logs per cell, no L2 cell reaches the n ≥ 20 verdict threshold. The L2 comparison is therefore reported with Wilson intervals. The comparison of record is the raw `utility`/`security` tally over the whole population (H6, H7), which reads raw fields and needs no mapping.

## 5. Known quirks (expected-known findings)

| Id / source | Expected | Reference |
|---|---|---|
| `agentdojo.args_mutated_in_place` | 1,855 files | profile quirk `observed`; census |
| `agentdojo.benign_security_constant` | 88 files, origin rule applied 87 | profile; census |
| `agentdojo.injection_task_as_user_task_prepass` | 88 files | profile; census |
| `agentdojo.placeholder_args_never_injection_evidence` | 3,397 present and null | profile; census |
| `agentdojo.incomplete_run` | 6 files, 0 null-outcome (keys absent); 4 end on a tool message | profile; census; reconcile |
| `agentdojo.pi_detector_redaction` | 910 logs, 910 redactions (melon dirs only) | profile; census |
| `agentdojo.silent_rerun_last_pass_only` / `unexecuted_trailing_calls` | 0 / 0 | profile; reconcile explains the 4 null-final logs (10c) vs 0 (10d) |
| `package_version_not_code_identity` | 0 without package version; `code_identity = "range"`, `verified_code = []` → D rules cited via `_unverified` twins | profile; D-24 |
| System-prompt variants | default (sha256 a021a92b…, 469 chars) 1,819; `melon_r_prompt` (82ce7af3…, 92 chars) 92 | profile; phase-10c census |
| Base-MELON stop message **[added by fact-check, from the pinned code]** | defence-authored assistant message `The tool outputs contain potential prompt injection, stopping execution.` (`tool_calls` null) replacing the model's message after a detection, possible in every melon/melon_sm/melon_at dir; no count pre-registered | `pi_detector.py` at the pin (MELON.query); same in kaijiezhu11/MELON |
| MELON-R SANITIZE text `[已移除潜在注入内容]` | 7 tool messages, gpt-4o-mini melon_r; kept as tool output | `docs/reports/phase10d/routing.md` R3 |
| Upstream copies | 36,679 byte-identical to `agentdojo · head` (`select.owned_elsewhere`) | profile `lineage.duplicates` |
| `artefacts.toml` | **no entry is scoped to `melon-agentdojo`**. Generic classes still occur: `agentdojo.art.incomplete_run`, `.naive_timestamp`, `.benign_security_constant`, `.injection_task_as_user`, `.defence_benign_intervention`, `.payload_not_reaching_agent`, `.banking_ut15_confound` | `src/agentprov/adapters/agentdojo/artefacts.toml` |
| Census accounting | `accounting_unverifiable` 1,909 (2 consistent) | census |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2. Selection reason codes: owned_elsewhere 36,679; not_execution_artefact for non-TL files; 3 absent blobs |
| L1-02 strict parse | yes | 1,911 logs plus the 2 non-TL JSON files |
| L1-03 encodings | yes | Legitimate CJK text (MELON-R RECOVERY/BLOCK/SANITIZE) must not be counted as mojibake. Windows origin: check CRLF and cp936 residues. Possible `\uXXXX` residues (AgentDojo #214) |
| L1-04 duplicates | yes | Within the part, and across corpora with `l1_xdup.py`. Expect 0 overlap except the excluded upstream copies |
| L1-05 arm coverage | yes | §3 (29 strata) |
| L1-06 secrets / account paths | yes | Counts and pointers only. The banking benchmark passwords (`update_password` args) are benchmark content |
| L1-07 timestamps | yes | Naive `evaluation_timestamp`; no per-call times; range in §2 |
| L1-08 degenerate | yes | 6 incomplete; expect 0 empty and 0 error-only |
| L2 import / validate / recompute / determinism | yes | Scratch corpus via the queue, `--cpu 2` |
| L2 A2 / A3 classes, evidence classes | yes | Expect I-class `_unverified` citations only for family D rules |
| L2 identity | yes | Model from `pipeline_dir`. Defence from the suffixes (5); `melon_rp` resolves by suffix although it is not a registered defence |
| L2 redaction | yes | Expect no account path in AER/SEM/PROV |
| L2 withholding | inert | MIT, policy include, no copyleft or use rule. Only the generic secret path applies |
| L2 outcome sanity | partial | Verdict-capable only for gpt-4o melon_sm and melon_at (via the H6 population tally); other strata get Wilson intervals only |
| Delta since E2 | no | Not in E2 |

## 7. Hypotheses (falsifiable; each threshold fixed now)

| Id | Expectation | Falsified if | Class if falsified |
|---|---|---|---|
| H1 | L1 selects exactly 1,911 logs, with the per-directory and per-stratum counts of §3 | any count differs by ≥ 1 | source-defect or mapping-defect |
| H2 | All 1,911 logs parse strictly: 0 duplicate keys, NaN, BOM, invalid UTF-8 or truncation | any hit | source-defect |
| H3 | U+FFFD 0 and mojibake 0. CJK appears only in `*-melon_r*` logs | any U+FFFD or mojibake; CJK in other dirs (report count) | source-defect, S3 |
| H4 | 0 byte-identical pairs among the 1,911; 0 cross-corpus byte overlap; identical attacked trajectories across different pipeline dirs = 0 | ≥ 1 pair | documentation-mismatch (copied or relabelled runs), S2 |
| H5 | The README cells missing or partial as in §3 (4 absent, 2 partial) | a missing cell turns up | – (refutes the lead) |
| H6 | The raw tally reproduces the README gpt-4o melon_sm and melon_at cells (6 UA, 6 ASR, 2 BU) to within ±1 run per cell | any cell off by > 1 run (> 0.7 pp); > 15 pp → S1 candidate | documentation-mismatch, S2 |
| H7 | The README MELON and MELON-R ignore_previous rows are **not** reproduced by gpt-4o-mini: melon ignore ≠ 54/0 of 144, or melon_r ignore ≠ 62/4 | both match to within ±1 run (the rows are then mislabelled gpt-4o-mini) | documentation-mismatch, S2 |
| H8 | 0 provider keys (`sk-`, bearer tokens) and 0 account paths (`C:\Users\`, `/Users/`, `/home/`) in the 1,911 | any hit | security finding, reported at once |
| H9 | 1,911 naive timestamps, all within 2026-05-24..2026-06-16 and none after the pin commit (2026-06-17T12:13Z). `duration` absent in 3 | out of range or after the pin | source-defect, S3 |
| H10 | Exactly 6 incomplete logs (outcome keys absent), 0 empty, 0 error-only | other counts | source-defect, S3 |
| H11 | **[Corrected by fact-check]** Chinese defence-authored messages occur only in `*-melon_r` / `*-melon_rp` dirs: BLOCK assistant messages with one of the two fixed Chinese texts (final-route BLOCK replaces the last message; pre-route BLOCK appends) and `tool_calls` null. English base-MELON stop messages (§5) may occur in any melon dir and are counted and reported, not a falsifier; the 113 extra system messages (2,024 − 1,911) are RECOVERY inserts. The 92 `melon_r_prompt` logs each have the default prompt as a later system message | any Chinese defence message outside those dirs; or the 92 logs lack the default prompt | mapping-defect if L2 maps BLOCK or base-MELON stop text as model output or the RECOVERY insert as the system prompt (S2; cf. D-113) |
| H12 | Sentinel redactions number 910 across 910 logs, all in melon dirs. Redactions in the 88 pre-passes are counted and reported | count ≠ 910 | mapping-defect or census drift; pre-pass hits > 0 → propose a scope extension of `defence_benign_intervention` |
| H13 | `[已移除潜在注入内容]` appears in exactly 7 tool messages, all in gpt-4o-mini melon_r | other count or location | documentation-mismatch, S3 |
| H14 | L2 on about 134 units: every stage ok, 0 failing checks, 0 degenerate, 0 `adapter_defect`. `recompute --dry-run` reports 0 differences. A second import with different `--jobs` is byte-identical. Identity resolves for 100% of units | any failure | mapping-defect |
| H15 | (exploratory) `runs/detection_stats.json` agrees with the report: 86 events; 57/0/16/13 (SM) and 55/0/16/15 (AT) | disagreement | documentation-mismatch, S3 |
| H16 | The L2 sample rates of the gpt-4o melon_sm and melon_at cells lie inside the README §4 gap rule (≤ 15 pp, or not excluded by Wilson 95% + 5 pp) | gap rule fires | investigate (identity or outcome mapping) |

Rule: no stratum is excluded for zero attack successes. Many cells are expected to show an ASR of 0%.

## Fact-check (2026-10-14, adversarial desk check; no raw data read)

Checked against the cited sources (URLs in `research.json` → `fact_check`):

- **Pin and repository** (GitHub API): fork=false, created 2026-06-17, HEAD = pin, 1 branch, 0 releases/issues/PRs/forks, licence MIT. Both own commits and the comment-only diff of `71d99dff` (+42/−46) confirmed. All 29 upstream `runs/` subtrees have the same tree SHA at `18b501a6` and at the pin, so no undefended fork run exists. Confirmed.
- **Counts**: non-truncated subtree listings give 1,911 melon blobs with the §3 per-directory and per-stratum counts (29 cells, all equal). The phase-10c census (38,780 / 38,592, suites, attacks, outcomes, timestamps, system digests, 2,024 system messages), the phase-10d census, trial and reconcile, routing R3 (7) and the registry (1911) match §2 and §5. Confirmed.
- **Reported numbers**: every README and report value in §4 (UA/ASR, BU 8/9 and 9/9, TP/FP/TN/FN, 86 events) matches the files at the pin; the k/144 conversions and the non-k/144 No Defense ASRs were recomputed. Report note 3 and the "about 0.2" threshold claim were confirmed, as were the [0.5, 0.95] clamp and sensitivity 0.5 in the code. Confirmed.
- **Paper**: arXiv:2502.05174 v1–v4 dates, ICML 2025, CC BY 4.0. Table 1 GPT-4o MELON values are the same in v1 and v4. In v4 only the LLM Detector rows change, Tables 2–4 are unchanged and Table 5 is new. The relation `builds_on` (context only) is correct. Confirmed.
- **AgentDojo issues** #181, #161, #214 and #212 are open; #139, #110 and #189 are closed. Titles match. kaijiezhu11/MELON has no licence. Confirmed.
- **Corrected**: (1) the claim that the run code is the pin except for melon_rp, because the melon_r RECOVERY text in the logs is an earlier five-line version (§1); (2) the claim that the small-run script is consistent with the partial arms, because its task pairs do not match (§1); (3) H11, because base MELON also writes a defence-authored English assistant message in every MELON dir and MELON-R has two BLOCK texts and paths (§5, §7); (4) "144 per cell" is implied, not stated (§3).
- **Unverifiable here**: the origin of the README MELON, MELON-R and No Defense rows (the docx Table 1 is an absent blob), the content of `runs/detection_stats.json` (L1), and model-provider terms.
