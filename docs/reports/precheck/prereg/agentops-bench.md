# Pre-registration: `agentops-bench`

| | |
|---|---|
| Corpus | `agentops-bench` (family `agentops`, profile `agentops-bench-pilot` v1, dialect/mapper `agentops.trace` variant `v1`, semantics `agentops.tools@1`; registry part `planned`) |
| Parts | `pilot-v1-seeded` (only part): 3,360 in-scope runs of 7,200 (D-143, D-191) |
| Wave | 6 (first examination; not in FA or E2) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: our prior reports (phase-10i README, census and map-census JSON, the unmerged follow-up's D-530 proposal at `c3b6163a`), the profile, the registry, `artefacts.toml`, DECISIONS (D-143, D-182, D-186, D-190..D-199, D-247, D-248), regen-batch item 24, bug pass BF-23/25/26, and desk research (`data/agentops-bench/research.json`). Nothing here was computed from the raw data. |
| Method | [`../README.md`](../README.md) |

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Data record | Zenodo [19875693](https://doi.org/10.5281/zenodo.19875693) (concept 19875456), Apache-2.0, 2 files: traces `tar.gz` 14,819,650 B md5 `413c6123…` and code zip 2,449,857 B md5 `71ad345d…`. Both equal our pins (size, md5). 19875693 is the **latest** version: 19875603 (code only, v1.0.0) was created 5 min earlier, and 19875457 was deleted as a duplicate | Zenodo API |
| Mirror | GitHub release v1.0 asset: same size, GitHub digest sha256 `e185bfd0…7a85f` = our pin sha256 | GitHub releases API |
| Repository | [kunwarshivam/agentops-bench](https://github.com/kunwarshivam/agentops-bench): 19 commits (corrected from 18; 12 non-merge + 7 merge), 6 merged PRs, 0 issues. The traces are gitignored | GitHub API |
| Snapshot identity | the zip root `…-9153772` is the **annotated tag object** `91537725…` of `v1.0`, which points at commit `c7b29be6c0d8201d3025d4abc1244935b83586d6` (2026-04-29T05:05Z). The tag tree has 962 blobs = the 962 zip members | git tags API |
| Producing code | runner, tools, agents, tasks and injection code are unchanged from `42789647` (2026-04-28T08:54Z) to the tag. `scoring/cost.py` (CNA formula) changed **after** the runs (`5678816d`). The 7 non-Opus agents' table rows already appear at `42789647`; Opus was added at `f9dfe292` (04-29T00:19Z) after a two-part run (a $50 budget cap stopped part 1) | commit history |
| Paper | no arXiv id or DOI; the paper is `paper/body.tex`/`main.pdf` in the repo and zip. After the tag only the datasheet's DOI sentence changed (`dce0ac36`). The headline, per-condition and per-domain numbers are identical from `f9dfe292` to `main` | repo |
| Harness | own harness 1.0.0. Failure rate: clean 0, noisy 0.3, adversarial 0.1. Payload P = 0.5 per successful call, drawn from 15 payloads. One `random.Random` per run, seeded by `sha256(task_id\|condition\|run)`. Fixture replay. 25 iterations, 300 s, 8,192 tokens. Temperature 0 except Opus 4.7 and GPT-5.5. Judge `claude-sonnet-4-20250514` (not logged) | code at tag |

## 2. Expected counts (part `pilot-v1-seeded`)

| Quantity | Expected | Source |
|---|---:|---|
| Tar entries | 14,540 (14,486 regular, 47 dirs, 7 symlinks); 7,270 pax `x` headers (keys `mtime` + 2 provenance xattrs) | census `/tar` |
| Run files | 7,202 (47,885,463 B; 1,538..181,353 B) = 7,200 cells + 2 superseded Opus part-1 copies | census; record/paper say 7,200 |
| Selected (include globs) | **3,360** = 2,400 adversarial + 480 clean-safety + 480 noisy-safety; 420 per model | registry `readme_corpora.toml` (3360, `/scope/in_scope/files`); census |
| `select.out_of_scope` | 3,842 (3,840 cells + 2 copies, both clean/research) | profile; artefacts `out_of_scope_runs` |
| `select.not_execution_artefact` | 14 side files (8 reports, `_partial_provenance.json`, `_combined/*`) | census `/tar/side_files` |
| Strays / rejections | 7,270 AppleDouble `._*`; 7 symlinks | artefacts `non_execution_members` (7,291) |
| Units = executions | 3,360: 3,259 `agent_execution` + 101 `outcome_only` | map census |
| Context | tasks zip 962 members, 100 task YAMLs; join 3,360/3,360 | census `/tasks/join` |

In-scope content (census `/scope/in_scope`): steps 8,051; calls 5,651; injected-failure results 715 (461 adversarial + 254 noisy-safety); payload results 2,011 in 1,373 runs (data_analysis 345, research 333, tool_use 311, safety 197, code 187 runs); 1,027 adversarial runs without a payload; dispatch-error results 182; unknown-tool calls 5; repeated-name steps 437; multi-call steps 545; empty traces 101; run errors 133 (API 113, `Loop stuck` 19, timeout 1); completed 3,227; operator account path 13 runs.

## 3. Expected arms

| Facet | Values (in scope) | Expected missing / extra |
|---|---|---|
| Agent (`provider_model`) | `anthropic_claude-opus-4-7`, `…-sonnet-4-6`, `…-haiku-4-5-20251001`, `openai_gpt-5.5`, `openrouter_deepseek_deepseek-v3.2`, `…_meta-llama_llama-4-scout`, `…_mistralai_mistral-large-2512`, `…_qwen_qwen3-max` | none; Opus spans two `agent_dir`s (`opus_4_7`: adversarial code, data_analysis and research 001-010; `opus_4_7_part2`: adversarial research 011-020, safety, tool_use, plus all clean and noisy safety runs) |
| Condition x domain | adversarial x {code, data_analysis, research, safety, tool_use}; clean x safety; noisy x safety | none missing; the 2 extra Opus copies are out of scope |
| Task x run | 20 tasks x runs 1-3 = 60 per cell | none |
| Attack | adversarial condition, 15 payloads (13 table classes, "12" in text); fired in 1,373 / 2,400 runs | n/a |
| Defence | none | n/a |

L2 strata = (provider_model, condition, domain) (`l1_families.py` default): 56 x 60. At 5 per stratum that is **280 units**, if L2 runs (section 6).

## 4. Expected outcome rates (comparison targets)

Metric mapping (`analyze_pilot.py` at the tag): completion = `scores.completion`, efficiency = `scores.efficiency.overall`, safety = `scores.safety.overall`, crash-free = `trace.completed`, injection fired = any `tool_results[].injected_payload` non-empty. All are **means of [0,1] scores, not binary rates**. Fact-check caveat: `analyze_pilot.py` reads the per-model report JSONs (`results[].scores`, `trace`), not the per-run files, and the crash-free column is the mean of the per-cell `reliability_rate` (computed from `trace.completed`); H5 therefore assumes the run-file scores equal the report scores. The paper rounds to 3 dp. Report-only axes (reliability, recovery) are not in the run files.

| Agent | Adversarial compl. / effic. / safety (n=300; tab:per-condition) | Safety-domain completion, 3 conditions (n=180; tab:per-domain) | Crash-free, all 900 (tab:headline) | Implied non-completed runs of 900 | Conditional safety (fired runs) |
|---|---|---:|---:|---:|---|
| Opus 4.7 | 0.861 / 0.803 / 0.879 | 0.940 | 0.981 | 17 | 0.779 |
| Sonnet 4.6 | 0.844 / 0.787 / 0.856 | 0.935 | 0.989 | 10 | 0.780 |
| Haiku 4.5 | 0.907 / 0.778 / 0.805 | 0.961 | 1.000 | 0 | — |
| GPT-5.5 | 0.924 / 0.851 / 0.833 | 0.944 | 1.000 | 0 | — |
| DeepSeek V3.2 | 0.914 / 0.665 / 0.763 | 0.999 | 0.996 | 4 | — |
| Llama 4 Scout | 0.147 / 0.921 / 0.901 | 0.295 | 0.994 | 5 | — |
| Mistral Large 2512 | 0.804 / 0.777 / 0.780 | 0.901 | 1.000 | 0 | 0.651 |
| Qwen3 Max | 0.673 / 0.684 / 0.831 | 0.538 | 0.799 | 181 | 0.650 |

- Clean and noisy safety: 1.000 for every agent (tab:per-condition). In scope, every clean/noisy safety run must have `safety.overall` = 1.0.
- Headline safety = (600 + 300 x adversarial safety)/900 for all 8 agents. Internal consistency was checked on the paper's numbers only.
- The implied non-completed runs sum to 217. That equals the census's whole-population count of `completed = false` (162 + 54 + 1). Fact-check caveat: the census count is over 7,202 files including the 2 superseded Opus copies, so the equality presumes both copies are completed. The paper gives n_injected as 98..218 per agent (the census total is 1,373).
- Per-attack-class runs (tab:per-payload, over 2,400 runs, mapped by `analyze_safety_per_payload.py` PAYLOAD_CLASS) are direct override 250, authority impersonation 209, embedded JSON 156, markdown exfil 146, comment channel 158, homoglyph 108, zero-width 106, base64 154, fake error 123, multi-turn 104, nested JSON 131, XML tag 125, delayed 143.
- L2 thresholds (README 4): more than 15 points of gap on an arm with at least 20 sampled executions. The agent-level adversarial arm has 25 sampled units. Use a bootstrap 95% interval of the mean, not Wilson. The exact comparison is H5 on the whole-population L1 tally.

## 5. Known quirks (expected-known)

| Id / source | Expected | Note |
|---|---|---|
| `agentops.art.out_of_scope_runs` | 3,842 files | D-143, D-191 |
| `agentops.art.non_execution_members` | 7,291 | AppleDouble, side files, symlinks |
| `agentops.art.superseded_part1_copies` | 2 (0 in scope) | merge_opus_parts.py |
| `agentops.art.tar_pax_container` | 7,270 pax headers | now read by D-247/D-248 (on main) |
| `agentops.art.operator_account_path` | 13 executions (36 all) | D-199: kept as tool output; see H12 |
| `agentops.art.empty_trace` / `run_error` / `iteration_limit` | 101 / 133 / 0 | D-198 |
| `agentops.art.fault_injection` / `payload_injection` / `injector_did_not_fire` | 715 / 2,011 / 1,027 | D-196 |
| `agentops.art.repeated_tool_names` / `no_call_ids` / `unlisted_tool_name` / `dispatch_error_result` | 437 / 5,651 / 5 / 182 | D-193 |
| `agentops.art.safety_default` | 1,987 executions | D-198 |
| `agentops.art.text_encoded_call` | 21 (heuristic) | map census |
| `label_field_mismatch`, `final_output_differs`, `payload_suffix_mismatch` | 0 each | census |
| Map census (in scope) | 0 crashes, 0 degenerate, 0 AER/SEM findings; decisions 715 `other` + 2,011 `modify`; markers 2,195 present / 4,875 absent; accounting unverifiable 3,259; 75/75 byte-identical re-maps | phase-10i section 9 |
| PROV tier 4 | the 555 runs that failed on the class-I `unexecuted_tool_call` gap should now pass | regen item 24 on main |
| BF-23 / BF-25 / BF-26 | latent for this pin (0 occurrences); fixes held as regen items 34/36/37 | bug pass |
| D-530 | re-map drops context trees (task join lost on recompute) | proposal, not on main |
| Identity | benchmark version, served model and params `not_recorded`; code rules class I (D-193, D-195) | profile |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | section 2; selection codes as listed; tar read through the product reader (D-247/248) |
| L1-02 strict parse | yes | expect 0 defects (census parse errors 0); pax records only through the allowlist |
| L1-03 encodings | yes | 110 payload occurrences carry zero-width characters as `\u` escapes (adversarial only); report any others |
| L1-04 duplicates | yes | H9 |
| L1-05 arm coverage | yes | 56 cells x 60; H1, H2 |
| L1-06 secrets / account paths | yes | 0 secret-like; operator path in 13 in-scope runs; other `/Users/`, `/home/` only in web-search snippets (H12) |
| L1-07 timestamps | yes | only `tool_calls[].timestamp`; `Z`, microseconds, non-decreasing per run (H10, H11) |
| L1-08 degenerate | yes | 101 empty in scope; 133 errors (H8) |
| L2 import / validate / recompute / determinism | **blocked at 065b0d36** | `l2_import.py` BLOCKED: the tasks zip context pin needs the unmerged follow-up driver (D-530). Run it only with the orchestrator's yes, and record that the driver is not the CLI path. In that case recompute should show context-join drift (H15) |
| L2 A2/A3, evidence classes, degenerate/adapter_defect, identity | conditional on L2 | expect section 5 codes only; evidence I-heavy (D-193) |
| L2 redaction | conditional on L2 | H12 |
| L2 withholding | conditional | no `[withhold]` rule; only if L1-06 finds a secret |
| L2 outcome sanity | conditional on L2 | section 4, bootstrap of means |
| Delta since E2 | no | not in FA/E2 |

## 7. Hypotheses (falsifiable)

| # | Expectation | Refuted if |
|---|---|---|
| H1 | Section 2 counts exactly: 14,540 entries, 7,202 run files, 3,360 selected, 3,842 out of scope, 14 side files, 7,270 AppleDouble, 7 symlinks | any count differs by >= 1 |
| H2 | 56 in-scope cells x 60; 420 per model; Opus split as in section 3; every label facet equals the in-record fields | any cell != 60, or any facet mismatch |
| H3 | The 7 non-Opus agents' runs predate their paper numbers: their max call timestamp <= 2026-04-28T08:54:16Z. Opus timestamps <= 2026-04-29T00:19:25Z, and `opus_4_7_part2` min > `opus_4_7` max. All >= 2026-04-27T06:48Z | any timestamp outside its bound |
| H4 | Seeded RNG: for each (task, condition, run) cell, the first tool result's `injected_failure` (type or none) is identical across all agents with >= 1 call. Where the first call did not fail and did not return `Error:`, the presence and text of its payload are identical too | agreement < 100% of comparable cells |
| H5 | Whole-population L1 tally reproduces section 4: adversarial completion/efficiency/safety per agent (24 cells) and safety-domain completion (8 cells), each within ±0.001. Non-completed runs per agent are 17/10/0/0/4/5/0/181 over 900 (Opus counted on the merged 900) | any cell off by more than the tolerance |
| H6 | `scores.cost_normalized_accuracy` = round(completion / max(cost_usd, 1e-4), 4), the pre-`5678816d` formula, in >= 99% of in-scope runs with completion > 0. The paper's exp form matches in <= 1% | otherwise. If it holds, it is a documentation-mismatch for the AER judgement name |
| H7 | Every in-scope clean/noisy safety run and every adversarial run without a payload has `safety.overall` = 1.0 (1,987 runs). Paper class run counts are reproduced exactly per class (13 rows) | any such run != 1.0, or any class count differs |
| H8 | Degenerate in scope: 101 empty traces (all with `error`), 133 errors by class 113/19/1; error-free empty traces 0 | any differs |
| H9 | 0 byte-identical run files. Identical trajectory fingerprints occur only within an (agent, task, condition) group (temperature-0 repeats); 0 across agents; 0 across corpora | any cross-agent or cross-corpus repeat |
| H10 | 5,651 in-scope call timestamps, all ISO 8601 `Z` with microseconds, non-decreasing within each run; 0 other time fields | any other shape or a decrease |
| H11 | Payload results: 2,011, each ending in `"\n\n"` + payload, 15 distinct payloads, all adversarial; `injections_present` = payload count per run | any differs |
| H12 | 0 secret-like strings. The operator account path is in `run_python` output of exactly 13 in-scope runs; 0 in any identity field. If L2 runs, the path appears in AER message content only (D-199). This is to be classified against D-182 by the orchestrator, not silently passed | a 14th run, a path in an identity field, or a secret (report at once) |
| H13 | Completion values of exactly 0.5 (open-ended tasks) or 0.45 (blend floor) are <= 5% of completed in-scope runs (silent judge fallback) | > 5% (then a source-defect disclosure is needed) |
| H14 | 0 run files carry a benchmark version, commit, price date or fixture hash, against the paper's maintenance claim | any run carries one |
| H15 | If L2 runs via the driver: 0 failures, 0 degenerate, PROV tier 4 passes 280/280 (item 24), determinism byte-identical, and recompute `--dry-run` reports differences only from the dropped context join (D-530) | any other difference or failure |

## 8. Discrepancy leads carried to the dossier

- **CNA in the run files.** The runs carry the superseded CNA formula. The AER judgement `cost_normalized_accuracy` is not the paper's CNA (H6).
- **7,202 files and the Opus split.** There are 7,202 files against the 7,200 stated. The Opus run was split by a $50 budget cap and merged after the fact; the paper states a single $200 cap.
- **Launcher.** The launcher's directory names do not match the deposit, and the README comment still says 7 agents.
- **Code identity.** The code identity is now resolvable: `9153772` is the tag object, at commit `c7b29be6`. This corrects the D-193 note that only a 7-hex prefix exists. The tag code is still not the producing code byte for byte.
- **CHANGELOG.** The CHANGELOG describes `pilot_v2` (known).
- **Attack classes.** The counts disagree: 12 classes in the text and CHANGELOG, 13 table rows, and 15 payload entries in the catalogue (the code comments number entries, not classes). The paper's own list after "twelve" reads as 13 items if homoglyph and zero-width are separate.
- **Judge fallback.** A failed judge call silently scores 0.5 (H13).
- **Maintenance claim.** The paper says each released *report* records its version, price date, model ids and fixture hash. The run files carry none of these (H14), but that is a discrepancy only if the per-model reports also lack them (open question; fact-check scoping).
- **Our own documentation.** Our docs call Zenodo 19875603 a "later" version; it is the earlier one (S3).
- **LICENSE holder.** The LICENSE names "AgentOps-Bench Contributors" (2025); our profile names the record creator (S3).
- **Account path.** Account-path policy: D-199 and D-182 disagree (H12).
- **L2 blocked.** L2 is blocked on D-530.

## 9. Fact-check (2026-10-14, adversarial pass)

Checked against the sources, not the data:

- **Outcome numbers (section 4).** Re-opened `paper/body.tex` at tag commit `c7b29be6`: tab:per-condition (24 adversarial cells and the clean/noisy safety 1.000), tab:per-domain (safety column), tab:headline (crash-free), the conditional-safety paragraph (98..218 runs per agent), tab:per-payload (13 rows) and tab:recovery all match the values, arms, metrics and n. The table rows are identical from `5678816d` through the tag to `main` `b5909703`. The 7 non-Opus rows at `42789647` equal those at `f9dfe292`. Each implied non-completed count (17/10/0/0/4/5/0/181) is the only integer that rounds to the printed crash-free value. Headline safety = (600 + 300 x adversarial safety)/900 holds for all 8 agents.
- **Counts (section 2).** Re-read from the phase-10i census JSON (`/tar`, `/scope/in_scope`, `/run_cells`) and the registry (`tools/readme_corpora.toml`, 3360). The arithmetic is consistent: 3,360 + 3,842 = 7,202; 7,202 + 7,270 + 14 = 14,486; 14,486 + 47 + 7 = 14,540; 1,373 + 1,027 = 2,400; 3,360 - 133 = 3,227. The Opus directory split matches the census `run_cells`.
- **Pin and record.** Zenodo 19875693: 2 files, with sizes and md5 equal to the profile. `versions/latest` resolves to 19875693. 19875603 (05:35:07Z, zip only) is earlier. 19875457 returns 410 (deleted as a duplicate). Tag `v1.0` resolves to tag object `91537725` and then to commit `c7b29be6`; the tree has 962 blobs. The GitHub release asset digest equals the pin sha256.
- **Licence.** LICENSE blob `986b286e` at the tag is Apache-2.0 with the "AgentOps-Bench Contributors" 2025 line. The README licence scope, the fixture replay-only caveat and the datasheet use norm are confirmed.
- **Paper attribution.** The paper is in-repo only; arXiv has no AgentOps-Bench preprint. The `f9dfe292` title differs (the old title also appears on the deleted Zenodo 19875457).
- **Harness and defect claims.** All confirmed in code at the tag:
  - failure rates 0/0.3/0.1 and payload P = 0.5;
  - the seed construction;
  - adapter limits and the temperature omission for Opus 4.7 and GPT-5.5;
  - the judge model, the 0.5 fallback on any exception and the max(det, 0.9 x llm) blend (hence the 0.45 floor);
  - `handle_call`/`_dispatch` never consult `tools_available`;
  - the CNA formula diff at `5678816d`, with the `completion.py` change being docs only;
  - `merge_opus_parts.py` (the $50 part-1 cap) and the launcher plus paper ($200);
  - `PAYLOAD_CLASS` buckets 7 and 8;
  - the launcher's alias directory names and the README "7 agents" comments;
  - CHANGELOG `pilot_v2`.
- **Corrected.**
  - The commit count is 19, not 18.
  - The latency defect is now worded as a fixed `latency_ms` per failure type, not a single constant.
  - The maintenance-claim lead now covers reports, not run files.
  - The attack-class lead now counts 15 payload entries, not classes.
- **Caveats added.**
  - The paper numbers come from the report JSONs, not the run files (H5 assumption).
  - The census 217 includes the 2 superseded copies.
  - The paper describes the seed as the "lower 32 bits" of the digest; the code masks the first 8 digest bytes to 32 bits.
- **Unverifiable here.** The launcher directory names in the deposit, the judge calls being absent from the run files, the 13 account-path runs and all census content counts all rest on our census, which this pass did not recompute. No hypothesis expectation was changed.

