# Pre-registration: `ceferisbarov-agentdojo`

| | |
|---|---|
| Corpus | `ceferisbarov-agentdojo` (family `agentdojo`, profile `ceferisbarov-agentdojo` v1, dialect/mapper `agentdojo.tracelogger`, variants `v1.k14`, `v1.k14.incomplete`) |
| Parts | `head` (only part) |
| Wave | 3 (first examination; not in FA or E2) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: our prior reports (phase-10d census, reconcile, trial), the profile, the registry, `readme_corpora.toml`, `artefacts.toml`, `routing.md` R5, DECISIONS D-100..D-109, the S1 search records, and desk research (`data/ceferisbarov-agentdojo/research.json`). The per-cell counts come from the GitHub git-trees listing of `reruns/` at the pin (names, sizes, blob ids only). Nothing here was computed from log contents. |
| Method | [`../README.md`](../README.md) |

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Repository | [ceferisbarov/agentdojo](https://github.com/ceferisbarov/agentdojo), a fork of ethz-spylab/agentdojo (merge base `5cea5891`, 2025-10-27, v0.1.35). Owner Jafar Isbarov (Virginia Tech). Issues disabled, 0 forks | GitHub API |
| Pin | `2273e1cd`, 2026-02-11T16:52Z = **current head** of `main`, the only branch | GitHub API |
| Logs added by | 9 commits, 2025-11-16 .. 2026-02-11 (`ec9a4ff0`, `9415100a` removes 1, `b0f0df0c`, `95caf2db`, `0acca7ac`, `1e17ef6f`, `f79eb6be`, `b01d454a`, `5cec9793`). No log blob changed afterwards. `runs/` was not touched after the merge base | commits API `?path=reruns` |
| Paper | **arXiv:2602.05066**, *Bypassing AI Control Protocols via Agent-as-a-Proxy Attacks* (Isbarov, Kantarcioglu). v1 2026-02-04, v2 2026-02-25 (tables unchanged; v2 adds the code link). CC BY 4.0. **The profile says "none found"** (lead L1) | [arXiv](https://arxiv.org/abs/2602.05066) |
| Paper code | [dspl-lab/agent-as-a-proxy-attack](https://github.com/dspl-lab/agent-as-a-proxy-attack) (no licence). Submodule `externals/agentdojo` = this fork **at `2273e1cd`**. Its README names `reruns/original` and `reruns/optim_str` as the uploaded baseline results. Monitor logs are not uploaded, and the optimised strings were removed from that repository | GitHub API, README |
| Data record | none (no Zenodo, HF or Figshare record); the fork is the release | research.json |
| Harness | Vendored AgentDojo 0.1.35 with fork additions: `--provider`, `--adapted` (goal replaced by `ADAPTED_GOAL` with an `OPTIM_STR` placeholder, paper Table 1), `--optim-str`. Benchmark v1.2.1. Attack `important_instructions` only. No defence in the pipeline (the paper's monitors run post hoc elsewhere). gpt-4o went through OpenRouter (`agentdojo.sh`), and the provider is not logged | fork commits, paper §4 |
| Code after the runs | 12 `src/` commits after the first rerun commit. `c1cbb712` (16:50, 2 min after the last log commit): pydantic `ValidationError` and `JSONDecodeError` now impose utility False / security True. `2273e1cd`: four banking injection vectors become YAML block scalars, and every injection is escaped before `str.format`: a bare `"` becomes `\"`, and an already backslashed `\?`, `\<`, `\{`, `\}`, `\(` gets a second backslash (bare `?`, `<`, `{`, `}`, `(` are not touched) [corrected: fact-check] | commit patches |
| Licence | MIT. The LICENSE blob `006aed0b` is identical to upstream's; there is no data licence and no use clause | LICENSE at pin |

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Pinned repository | 55,302 files / 615,555,549 bytes | profile `expected_files/bytes` (not re-derived; tree API truncates) |
| Selected logs (`reruns/*/*/*/*/*/*.json`) | **18,442** (187,036,960 bytes; 981..363,780 bytes each) | registry (`readme_corpora.toml`, census `/files`); census; reruns tree |
| Attacked / pre-pass / benign user task | 17,426 (181,058,935 B) / 1,016 (5,978,025 B) / **0** | tree path kinds; census `injection_task_as_user_task_prepass` 1,016 |
| Not selected | 36,679 `runs/` files (`select.owned_elsewhere`, owner `agentdojo`) plus code and docs. Context: LICENSE, README.md, pyproject.toml, CITATION.bib | profile; trial `excluded` 36,679 |
| Units | 18,437 `agent_execution` + 5 `outcome_only` | census |
| Variants | `v1.k14` 18,403, `v1.k14.incomplete` 39 | census |
| Byte-identical blobs inside `reruns/` | 0 (18,442 distinct blob SHAs) | tree |
| S1 "novel run files" 17,426 | = the attacked logs; the 1,016 gap is the pre-pass logs, not duplicates | S1-forks.jsonl; tree |
| Trial (phase 10d, stratified samples) | 4,660 executions (4,625 ok, 35 ok_with_issues) at jobs 8; 993 at jobs 3; subset byte-identical | trial.json |
| Cells (arm × pipeline × suite) | 161 = 130 full grids + 15 partial + 16 pre-pass-only (28 logs) | tree |

Grids per suite (benchmark v1.2.1): banking 16 UT × 9 IT = 144 (+9 pre-pass), slack 21 × 5 = 105 (+5), travel 20 × 7 = 140
(+7), workspace 40 × 14 = 560 (+14). Every full and partial cell has its complete pre-pass set.

## 3. Expected arms

| Facet | Values | Expected missing / extra |
|---|---|---|
| Arm (first dir; R5: path only) | 61: `original` (2,632 logs), `optim_str` (2,383), `1_parallel_*`/`1_nonparallel_*` (6 arms, 1,138), `llama_k_*` (**16** arms [corrected from 18], 2,808), `mistral_k_*` (15, 2,619), `qwen_k*` (**22** arms incl. `qwen_k1` [corrected from 21], 6,862), of which 17 are `*_fixed` | the literal `{optim_str}` directory (10 pre-pass logs, `1e17ef6f`) is absent at the pin |
| Model (pipeline dir, verbatim) | 21 dirs. With attacked logs (11): gpt-4o-2024-05-13 11,214 attacked; gpt-4o-mini 1,389; google_gemini-2.5-pro 1,338; openai_gpt-oss-20b 1,058; Qwen_Qwen2.5-7B-Instruct-Turbo 669; google_gemma-3-27b-it 525; meta-llama_Llama-3.1-70B-Instruct 498; command-r-plus-08-2024, google_gemini-3-pro-preview, x-ai_grok-4.1-fast 210 each; gpt-5-2025-08-07 105 | 10 pre-pass-only dirs (1-7 logs each), including three command-r-plus spellings |
| Defence | none | — |
| Attack | `important_instructions` (all 17,426 attacked); `none` (pre-pass) | no other label |
| Suite | slack 8,154 attacked; banking 7,120; workspace 1,680 (original × gpt-4o, gemini-2.5-pro; optim_str × gpt-4o); travel 472 (original × gpt-4o (partial), gemini-2.5-pro; optim_str × gpt-4o, gemini-2.5-pro) | — |
| Partial cells (15) | llama_k_1_19 bank 121; llama_k_1_2 bank 138; llama_k_1_3 bank 26; llama_k_4_12 bank 1, slack 1; mistral_k_1_1 bank 31; mistral_k_1_2(_fixed) bank 5/5; mistral_k_1_3(_fixed) bank 1/1; mistral_k_4_4 gpt-4o slack 1; optim_str gpt-oss-20b slack 8; original gpt-4o travel 52; qwen_k_1_2_fixed bank 23, slack 59 | aborted runs released with full grids |
| Paper vs logs | the paper's grids are slack 20 × 5 and banking 15 × 8; the logs have 21 × 5 and 16 × 9 | extra UT per suite, extra banking IT (L2) |

## 4. Expected outcome rates (comparison targets)

The paper's metrics are **monitor-bypass ASRs** (Tables 2-6). They need monitor verdicts, and the logs do not contain
any. The only agent-level numbers are the **kept-trace counts**: traces in which the injection deceived the agent. These
map to AgentDojo `security == true` (attack success; #95) over attacked logs. The paper reports no utility. Run-error
logs carry an imposed `security = true` (`agentdojo.run_error_imposes_outcome`, 65), so rates are reported with and
without them.

| Arm | Metric | Paper value (n) | Where | Comparison |
|---|---|---|---|---|
| optim_str × gpt-4o × slack | security true | 89/100 = 89.0% | §4.1/§5.1 | whole-population tally over 105 (H9) |
| optim_str × gpt-4o × banking [corrected: the paper names neither the agent nor the arm for §5.5; gpt-4o and optim_str are our assumption] | security true | 96/120 = 80.0% (120 = 15 × 8 × 1, the paper's formula) | §5.5 | weak, over 144 (H9b) |
| optim_str × {gpt-4o-mini, Llama-3.1-70B} × {slack, banking} | security true | 161/220 = 73.2% (pooled or per agent not stated) | §5.4 | weak (H9c) |
| monitor families on gpt-4o slack | E2E ASR (monitor) | Mistral 50.0, Qwen 17.5, Llama 54.6 | Table 3 | upper-bound consistency only (H10) |
| Tables 2, 4, 5, 6 | monitor ASR | see research.json | — | not testable (no verdicts) |

L2 sample: 161 strata against a 300 cap gives about 1.9 per stratum, so no arm reaches 20 sampled executions. L2 reports
Wilson intervals only. The verdicts come from the whole-population L1-05 tally (H9, H10).

## 5. Known quirks

| Id | Expected (head) | Source |
|---|---|---|
| `agentdojo.benign_security_constant` (art. `benign_security_constant`) | 1,016 files, origin rule applied 993 | profile, census |
| `agentdojo.injection_task_as_user_task_prepass` (art. `injection_task_as_user`) | 1,016 | profile, census |
| `agentdojo.silent_rerun_last_pass_only` | 0 null-final logs; `earlier_attempts_unobservable` on all 18,437 executions | profile, census |
| `agentdojo.unexecuted_trailing_calls` (art. `max_iters_pending`) | 58 calls in 53 logs (samples in mistral_k_16_0 × gpt-oss-20b) | profile, census |
| `agentdojo.args_mutated_in_place` | 17,387 files | profile, census |
| `agentdojo.placeholder_args_never_injection_evidence` | 84,028 present, all null | profile, census |
| `agentdojo.incomplete_run` (art. `incomplete_run`) | 39 files, 0 null-outcome | profile, census |
| `agentdojo.provider_call_id_anomalies` (art. `provider_ids`) | 877 null ids in 220 logs; 0 duplicate or empty | profile, census |
| `agentdojo.run_error_imposes_outcome` (art. `run_error_imposed`) | 65 files (samples in optim_str × Llama-3.1-70B) | profile, census |
| `agentdojo.empty_messages_without_outcome` | 5 files (`no_execution_observed`); the census also prints `empty_messages_with_outcome` 5 for them (S3 labelling) | profile, census |
| `agentdojo.package_version_not_code_identity` | 0 files without a version; 0.1.35, 742 logs at 0.1.34 | profile |
| Identity | `model_from = pipeline_dir`, `verbatim_unreliable_when_differs`; 0 unresolved | profile, phase10d README |
| Evidence (D-101, D-103, D-24) | `verified_code = []`: D rules only through `_unverified` twins | profile |
| Arm (R5) | in the origin path only; no AER field | routing.md R5 |
| System prompt | 469-char AgentDojo default (`agentdojo_default`) in every log with a system message | profile |
| Accounting | consistent 49, unverifiable 18,393 | census |
| artefacts.toml | no entry scopes `ceferisbarov-agentdojo`. Applicable by analogy: `run_error_imposed`, `benign_security_constant`, `injection_task_as_user`, `silent_rerun`, `max_iters_pending`, `provider_ids`, `incomplete_run`, `naive_timestamp`, `banking_ut15_confound`, `validity_defects`, `payload_not_reaching_agent`, `injection_yaml_folding`, `empty_log` | artefacts.toml |
| Phase-10c shortlist | 65 run errors; 2 files with secret-like patterns | agentdojo-format-shortlist.md row 1 |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2: 18,442 per cell (§3); selection by the `include` glob; 36,679 owned elsewhere |
| L1-02 strict parse | yes | expect 0 defects (census, trial 0 failures) |
| L1-03 encodings | yes | GCG strings: unusual Unicode expected (H14); escape residues from the pin's escaping (H13); #214 `\uXXXX` |
| L1-04 duplicates | yes | 0 byte-identical (tree); pre-pass trajectory repeats across arms (H12); cross-corpus 0 (S1: 0 blobs shared with upstream) |
| L1-05 arm coverage | yes | §3 cells; plus the outcome tally (H9, H10) |
| L1-06 secrets / account paths | yes | ≤ 5 secret-like files (benchmark text), 0 account paths (H15) |
| L1-07 timestamps | yes | `evaluation_timestamp` (v1.k14), naive; range and commit order (H16); within-unit monotonicity n/a |
| L1-08 degenerate | yes | 5 empty, 39 incomplete, 0 null-final, 53 unexecuted-call logs (H3-H5) |
| L2 import, validate, recompute, determinism | yes | trial: 0 failures, byte-identical across jobs 8 and 3 |
| L2 A2 / A3 classes | yes | expect only the trial's register codes |
| L2 evidence classes | yes | D rules only as `_unverified` twins |
| L2 degenerate / adapter_defect | yes | expect 0 / 0 |
| L2 identity | yes | 21 models from the pipeline dir; arm not in AER (R5); provider not recorded (H18) |
| L2 redaction | yes | expect no account path |
| L2 withholding | conditional | only if L1-06 finds a real secret value |
| L2 outcome sanity | yes (Wilson only) | §4 |
| Monitor-level outcomes (Tables 2-6) | no | no monitor verdict in the logs |
| Utility comparison | no | the paper reports no utility; no benign user-task logs |
| Delta since E2 | no | not in FA/E2 |

## 7. Hypotheses (falsifiable)

| # | Expectation | Refuted if |
|---|---|---|
| H1 | 18,442 logs = 17,426 attacked + 1,016 pre-pass, in exactly the 161 cells and counts of §3; 0 benign user-task logs | any cell differs by ≥ 1 |
| H2 | 0 strict-parse defects; 0 byte-identical files inside the part; 0 byte-identical with any other corpus | any |
| H3 | Quirk counts of §5 reproduce exactly (1,016/993; 1,016; 0; 58/53; 17,387; 84,028; 39/0; 877/220; 65; 5) | any differs |
| H4 | The 5 empty, no-outcome logs are the only attacked logs of the five 1-attacked-log cells (llama_k_4_12 banking and slack, mistral_k_1_3 banking, mistral_k_1_3_fixed banking, mistral_k_4_4 × gpt-4o slack) | any lies elsewhere |
| H5 | ≥ 90% of the 39 incomplete logs lie in partial or pre-pass-only cells | < 90% |
| H6 | The 742 logs with package version 0.1.34 are original × gpt-4o × {travel, workspace} (632, `ec9a4ff0`) plus optim_str × gpt-4o × slack (110, `b0f0df0c`); every other log reports 0.1.35 | the sets differ by > 5 files |
| H7 | `benchmark_version` = `v1.2.1` in ≥ 99% of logs | < 99% |
| H8 | The `injections` values contain the literal `{optim_str}` in ≥ 99% of optim_str attacked logs, in 0 original logs, and in ≤ 1% of the k- and `1_*` arms (those carry an optimised string) | any bound fails |
| H9 | security-true rate (attacked, incl. imposed): (a) optim_str × gpt-4o × slack in [74%, 100%]; (b) optim_str × gpt-4o × banking in [65%, 95%] (weak: the paper does not name the §5.5 agent or arm); (c) optim_str × {gpt-4o-mini, Llama-3.1-70B} × {slack, banking} pooled in [58%, 88%] (weak: denominator unclear) | a rate outside its band (the paper's value ± 15 points) |
| H10 | For each monitor family (mistral_k, qwen_k, llama_k), at least one gpt-4o slack arm has a security-true rate ≥ its Table 3 E2E ASR (50.0 / 17.5 / 54.6) | every arm of a family lies below |
| H11 | The 65 imposed-outcome logs all have a non-null `error`, utility false and security true; ≥ 50% are outside the OpenAI-model pipelines (gpt-4o, gpt-4o-mini, gpt-5) | any lacks an error, or < 50% |
| H12 | Pre-pass logs (same goal in every arm): ≥ 25% of gpt-4o pre-pass logs share a trajectory fingerprint with a pre-pass log of the same suite and IT in another arm. Attacked logs: 0 shared fingerprints across arms | < 25%, or ≥ 1 attacked repeat |
| H13 | Escape residues in tool outputs [corrected: the pin escapes only a bare `"` (to `\"`) and doubles the backslash of `\?`, `\<`, `\{`, `\}`, `\(`; bare braces and parentheses are not escaped]: `\"` where the logged injection has a bare `"`, or `\\?`, `\\<`, `\\{`, `\\}`, `\\(` where it has the single-backslash form, occur in banking logs, and ≥ 80% of such logs are in `*_fixed` arms | residues mostly outside `*_fixed`, or none at all (then the pin's fix was not used: report) |
| H14 | ≥ 1 log in the optimised arms has bidi, zero-width, tag, C1 or U+FFFD characters in `injections`; 0 in `original` | 0 in optimised arms, or ≥ 1 in original |
| H15 | ≤ 5 files with secret-like strings, all benchmark text; 0 account paths | > 5, a real credential, or ≥ 1 account path |
| H16 | `evaluation_timestamp` present in every log with an outcome, naive, within 2025-11-01 .. 2026-02-12, and each log no later than its adding commit (+1 day zone tolerance) | any outside, or later than its commit |
| H17 | The 220 logs with null call ids are all outside the OpenAI-model pipelines | ≥ 1 in gpt-4o, gpt-4o-mini or gpt-5 |
| H18 | Identity resolves to 21 distinct models with 0 unresolved, and `command-r-plus`, `command-r-plus-04-2024` and `cohere_command-r-plus-08-2024` stay distinct; no AER field names the provider | unresolved > 0, or a provider recorded |

## 8. Discrepancy leads carried to the dossier

1. The profile's `paper = "none found"` is wrong: arXiv:2602.05066 and its code repository (submodule pinned at
   `2273e1cd`) document these logs (S3, documentation-mismatch).
2. The paper's grids are 100/120 pairs; the logged grids are 105/144.
3. The paper's headline numbers are monitor-level and not recomputable from the logs.
4. Arms and models absent from the paper: gemini-2.5-pro, gemini-3-pro-preview, grok-4.1-fast, gpt-5, command-r-plus,
   gemma-3-27b, Qwen2.5-7B, gpt-oss-20b. The arm labels are defined nowhere public.
5. 15 partial and 16 pre-pass-only cells.
6. `5cec9793` postdates paper v1.
7. 742 logs record 0.1.34 on a 0.1.35 base.
8. The run-error policy and the injection escaping were committed after the logs, so the code identity of each arm is
   unrecorded. The escaping can make the payload the agent read differ from the logged `injections`.
9. The provider is not logged; gpt-4o ran through OpenRouter.
10. Pre-pass repeats across arms (C5).
11. The census labels the 5 empty logs under two quirks.
12. No `artefacts.toml` entry scopes this corpus, and the arm is not an AER field (R5).

## 9. Fact-check (adversarial, 2026-10-14, before any data check)

Re-opened from the cited sources only (paper HTML v1 and v2, arXiv API, GitHub API at the pin, the attack repository,
upstream issues, our census/trial/profile/registry/shortlist/artefacts.toml). Nothing was computed from log contents;
the `reruns/` tree (`841892195ade`, `truncated: false`) was re-listed for names, sizes and blob ids only.

Confirmed:
- Paper arXiv:2602.05066 (Isbarov, Kantarcioglu), v1 2026-02-04, v2 2026-02-25, 762 KB each, CC BY 4.0; v2 differs from
  v1 only by the code link. Tables 2, 3, 4 and 5 and the counts 89 (of 20 × 5 × 1 = 100), 96 (of 15 × 8 × 1 = 120) and
  161 (of 220) are identical in both versions ([v1](https://arxiv.org/html/2602.05066v1), [v2](https://arxiv.org/html/2602.05066v2)).
- §4.3: the 100 slack traces were run with gpt-4o-05-13 and contain `{optim_str}` instances, which supports the
  `optim_str` arm for H9a.
- Attack repository: submodule `externals/agentdojo` = this fork at `2273e1cd`; README names `reruns/original` and
  `reruns/optim_str`; licence null; 3 commits (`d4364d4b` authored 2025-11-16, committed 2026-02-21).
- Fork: parent ethz-spylab/agentdojo, only branch `main` at `2273e1cd` (2026-02-11T16:52:19Z), issues disabled, 0 forks,
  diverged ahead 23 / behind 4, merge base `5cea5891` (2025-10-27). The 9 `reruns/` commits and the 12 later non-log
  commits are as listed. `runs/` last touched 2025-07-25 (before the merge base). README blob = upstream's at the merge base.
  `pyproject.toml` version 0.1.35.
- LICENSE at the pin: blob `006aed0b` = upstream's, MIT, (c) 2024 Debenedetti et al.
- `reruns/` tree: 18,442 blobs, 187,036,960 bytes, 18,442 distinct SHAs, sizes 981..363,780; 17,426 attacked
  (181,058,935 B) + 1,016 pre-pass (5,978,025 B); 61 arms, 17 `*_fixed`; 21 pipeline dirs with the stated per-dir counts;
  per-suite attacked counts; 161 cells = 130 + 15 + 16 (28 logs); the 15 partial cells; complete pre-pass sets;
  `ec9a4ff0` added 59 + 574, `9415100a` removed 1 travel log, `b0f0df0c` added 110 (so H6's 632 + 110 arithmetic holds);
  `1e17ef6f` added 10 files under a literal `{optim_str}` arm, absent at the pin.
- Census, trial, registry (`readme_corpora.toml` 18,442, basis census `/files`), S1 `novel_agentdojo_run_files`
  17,426, profile `paper = "none found (phase 10c)"`, all 13 `agentdojo.art.*` ids exist and none scopes this corpus.
- Upstream issues #95, #154, #168, #181, #201, #213, #214 match their descriptions (#201 concerns v1.2.2; this corpus
  runs v1.2.1, so it is context only).

Corrected:
- Arm counts per family: `llama_k_*` has **16** arms (not 18) and `qwen_k*` **22** incl. `qwen_k1` (not 21); the
  stated 6 + 18 + 15 + 21 + 2 = 62 did not sum to 61. Log totals per family were right.
- The pin's escaping (`2273e1cd`, `task_suite.py`): only a bare `"` is escaped; `\?`, `\<`, `\{`, `\}`, `\(` (already
  backslashed) get a second backslash; bare `{`, `}`, `(` are untouched. §1 and H13 are reworded accordingly.
- §5.5 (96/120): the paper names neither the agent nor the arm; "optim_str × gpt-4o" is our assumption, so H9b is weak.

Not verifiable from public sources (left as open questions): the arm-name semantics; whether §5.4's 220 is per agent or
pooled; that Table 3 is gpt-4o × slack (supported only by the paper's "Slack suite throughout" default); providers for
gpt-4o-mini and Llama-3.1-70B.

New documentation lead (not a data expectation): the attack repository's `bash_scripts/agentdojo.sh` writes **both**
runs (`--adapted False` and `--adapted True --optim_str "{optim_str}"`) to `--logdir externals/agentdojo/reruns/original`,
while its README places them in `reruns/original` and `reruns/optim_str` respectively
([script](https://github.com/dspl-lab/agent-as-a-proxy-attack/blob/master/bash_scripts/agentdojo.sh)). The arm directory
is therefore not documented consistently; this bears on the open question of which arm produced 89/100.

Method note (no change made): H10 treats Table 3's E2E monitor ASR as a lower bound for the agent-level security-true
rate; this holds only if the paper's ASR denominator includes traces where the agent was not deceived, which the paper
does not state.
