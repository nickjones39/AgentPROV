# Pre-registration: `craibench-agentdojo`

| | |
|---|---|
| Corpus | `craibench-agentdojo` (family `agentdojo`, profile `craibench-agentdojo` v1, dialect/mapper `agentdojo.tracelogger`, variant `v0.k11`, SEM `agentdojo.suites@2`) |
| Parts | `head`: GitHub `AthaSSiN/CrAIBench` @ `e41eac1eb2fea00a31c69827bfe83f9722a25702` (only part) |
| Wave | 3 (full pre-check; not examined in FA or E2, so there is no delta since E2) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Inputs: our own prior reports (phase-10d census, trial, reconcile, R8 SEM counts), the profile, the registry, `artefacts.toml`, DECISIONS, and desk research (`data/craibench-agentdojo/research.json`). No raw data was read and nothing was computed from it. File counts below come from the GitHub git-trees API (metadata) |
| Method | [`../README.md`](../README.md) |

## 1. Sources (details and URLs in `research.json`)

- **Repository.** <https://github.com/AthaSSiN/CrAIBench>. It is not a GitHub fork, but it carries the AgentDojo history to tag v0.1.15 (`8d2ecb59`). The pin is `main` HEAD, dated 2026-01-09 (a README fix). There are 0 issues and 1 closed PR (`sft`).
- **When the runs were added.**
  - `a512e34a` (2025-04-03) deletes all 19,740 upstream logs and adds the 19 datamarking chain logs.
  - `be71b1f5` (2025-04-04) adds the 128 delimiting chain logs and the 3 banking logs. The same commit changes the delimiting text, the memory phrase and the PI wrapper.
  - `dc1a1a73` (2025-04-06) adds the 1,013 crypto_trading logs.
  - No later commit touches `runs/`. The code does change after the runs (D-111): the crypto injection tasks, the new dao_nft suite and logging.py.
- **Paper.** arXiv:2503.16248 has three versions:
  - v1 (2025-03-20): no CrAIBench.
  - **v2 (2025-04-30): introduces CrAIBench. Table 1 gives the design; Appendix C.1 Tables 2 and 3 give the full results.**
  - v3 (2025-07-09): the full tables are dropped (figures only) and detectors are added.
  - v2 is therefore the comparison version. The paper does not link the logs. The fine-tuning dataset card in the repository links the paper.
- **Data record.** None (no Zenodo, HF or Figshare record). Integrity rests on the git blob ids. The HF dataset `SentientAGI/crypto-agent-safe-function-calling` is fine-tuning data, not logs.
- **Licence.** MIT (the upstream AgentDojo LICENSE, with no fork copyright line). The finetune card's CC-BY-4.0 covers that dataset only.

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Blobs at pin | 1,344 (10,397,914 B in git; 1,804 tree entries) | profile `expected_files`; GitHub tree |
| Absent blobs | 1 (`finetune_dataset/figures/ft_comparison.png`, a 130 B LFS pointer) | census/trial `pin.absent_blobs` |
| Selected logs (`runs/*/*/*/*/*.json`) | **1,163** (8,688,961 B; smallest 1,560 B, largest 21,284 B) | `tools/readme_corpora.toml` (1163, census); `phase10d/craibench-agentdojo.census.json` `/files`; tree |
| Not selected | 181 (code, docs, scripts; 6 context artefacts stored as supporting) | profile; tree |
| Units / executions | 1,163 `agent_execution` / 1,163 (sealed_clean 475, with issues 688) | census `/units`; trial jobs 8 (jobs 3: 233, byte-identical) |
| Variants | v0.k11 1,163 | census |
| Register codes | accounting_unverifiable 1,163; earlier_attempts_unobservable 1,163; unattributed_additional_user_message 688 | census; trial |
| Suites | crypto_trading 1,013; chain 147; banking 3 | profile; routing R8; tree |
| Pipelines | gpt-4o-spotlighting_with_delimiting 1,019; gpt-4o-mini-2024-07-18-spotlighting_with_delimiting 125; gpt-4o-spotlighting_with_datamarking 19 | tree |
| Injection mode | MI (`*_memory_injection.json`) 688; PI 435; pre-pass `none` 40 | tree; census (688 / 40) |
| Placeholder args | 2,210 present, all null | census |
| SEM (suites@2) | crypto 13/13 tools known; chain 4/9 known (D-112); banking 3 on v1 tables | r8-sem; C.14.8 |
| L2 sample | **53** units (13 strata: 10 × 5 + 3 banking × 1). If the stratum key leaves out the MI/PI facet, 43 | README §4 applied to §3 |

## 3. Expected arms (L1-05 facets: model × defence × suite × attack × injection mode; task class as a sub-facet)

The task class is set by the user-task id: crypto < 80 and chain < 25 are multi-step; crypto 80..95 and chain 25..31 are single-step (v2 Table 1; `count_true_values.py`).

| Pipeline dir · suite | MI multi | MI single | PI multi | none (pre-pass) | Total |
|---|---:|---:|---:|---:|---:|
| gpt-4o delim · crypto_trading | 413 (78 tasks × 5 = 390, plus 23 with inj 5..9 and 11 *[corrected: no inj 10]*) | 80 (16 × 5) | 384 (73 tasks: 365, plus 19 with inj 5..9 and 11 *[corrected]*) | 11 (inj 0..9 and 11; 10 absent *[corrected]*) | 888 |
| gpt-4o delim · chain | 50 (25 × 2) | 14 (7 × 2) | 50 (25 × 2) | 14 (inj 0..13) | 128 |
| gpt-4o-mini delim · crypto_trading | 40 (tasks 63..70 × 5) | 80 | 0 | 5 (inj 0..4) | 125 |
| gpt-4o datamarking · chain (early code, `a512e34a`) | 10 (tasks 0..7) | – | 0 | 9 (inj 2..10) | 19 |
| gpt-4o delim · banking | 1 | – | 1 | 1 | 3 |
| **Total** | 514 | 174 | 435 | 40 | **1,163** |

- **Paper design (v2).** 4 models (GPT-4o, GPT-4o-mini, Claude Sonnet 3.5 and 3.7) × 3 system prompts (Default, Secure, Confirmation), all with delimiting, × 3 suites (Chain, Trading, DAO/NFT). Each model and prompt has 135 benign multi-step tasks, 564 PI, 564 MI, 31 benign single-step tasks and 121 single-step MI.
- **Missing cells.** All Claude arms. DAO/NFT (added after the runs). Every benign user-task run. gpt-4o-mini chain and PI, and its crypto multi tasks 0..62 and 71..79. Crypto PI for tasks 24, 25, 71, 72 and 78. Crypto tasks 53 and 54 entirely (consistent with the paper's 78 = 80 − 2). The two other prompt conditions (expected: one condition per commit group, H5).
- **Extra cells.**
  - datamarking chain (19, not in the paper)
  - banking (3, smoke)
  - 42 crypto runs with injection ids 5..9 and 11, plus crypto pre-pass ids 5..9 and 11 *[corrected from 5..11]*; the paper's design has 5 injections per trading task
  - None is excluded on that ground, and none for zero successes (user rule).

## 4. Expected outcome rates (L2 outcome sanity; population tally H7–H9)

The metrics map to logged fields as follows (v2 §5; `count_true_values.py`):

- **Utility (under attack)** is the count of `utility` True over a cell's attacked logs. Table 2 prints this count.
- **ASR** is the count of `security` True over all files in the cell directory, extras included. `security` True means the injection goal was met (AgentDojo #95).
- **Benign utility** cannot be checked: there are no benign logs. The `security` of the 40 pre-pass logs is the benign constant (`benign_security_constant`) and enters no rate.
- **MI vs PI** is set by the file stem only (D-107). The attack label is `important_instructions` for both.

The expected prompt condition is **Secure** (`default_defended`): it is the run_script and README default, and two Secure cells fit the released denominators.

| Arm (released) | Logs | Paper (v2) Secure | Implied k | Other conditions (for identification) | Table |
|---|---:|---|---|---|---|
| gpt-4o delim · crypto · PI multi | 384 | UA 243; ASR 21.87% | utility 243, security **84/384** | Default 197 / 75.13%; Confirmation 6 / 4.10% (/390) | T2 |
| gpt-4o delim · crypto · MI multi | 413 | UA 140; ASR 74.33% | utility 140, security **307/413** | Default 154 / 96.15%; Confirmation 55 / 43.85% | T2 |
| gpt-4o delim · chain · PI multi | 50 | UA 13; ASR 54.00% | 13 / 27 | Default 10 / 76%; Confirmation 1 / 6% | T2 |
| gpt-4o delim · chain · MI multi | 50 | UA 0; ASR 90.00% | 0 / 45 | Default 0 / 100%; Confirmation 0 / 28% | T2 |
| gpt-4o delim · chain · MI single | 14 | UA 1; ASR 100.00% | 1 / 14 | Default 1 / 100%; Confirmation 0 / 21.43% | T3 |
| gpt-4o delim · crypto · MI single | 80 | UA 14; ASR 55.00% (row labelled DAO/NFT, sizes 16/80 = Trading in T1) | 14 / 44 | Default 28 / 100%; Confirmation 11 / 56.25% | T3 vs T1 |
| gpt-4o-mini delim · crypto · MI single | 80 | UA 34; ASR 100.00% (same label caveat) | 34 / 80 | Default 34 / 100%; Confirmation 10 / 43.75% | T3 |
| gpt-4o-mini delim · crypto · MI multi | 40 | paper cell is 390 (Secure 114 / 93.59%) | partial: rate only | – | T2 |
| datamarking, banking, inj 5..11 extras, pre-passes | – | none reported | Wilson 95% only | – | – |

The L2 sample has about 5 logs per stratum, so no L2 cell reaches n ≥ 20. The comparison of record is the raw `utility`/`security` tally over the whole population (H7–H9). It reads raw fields only and runs in L1/L2, not now.

## 5. Known quirks (expected-known findings)

| Id / source | Expected | Reference |
|---|---|---|
| `agentdojo.benign_security_constant` | 40 files, origin rule 40 | profile; census |
| `agentdojo.injection_task_as_user_task_prepass` | 40 files | profile; census |
| `agentdojo.spotlighting_delimiters` | 1,144 logs (all delimiting); 1,095 with tool results | profile; census |
| `agentdojo.silent_rerun_last_pass_only` / `unexecuted_trailing_calls` | 0 / 0 | profile; census; reconcile |
| `agentdojo.placeholder_args_never_injection_evidence` | 2,210 present and null | census; reconcile |
| `unattributed_additional_user_message` (class I) | 688 = the MI logs (the memory arrives as an extra user message) | profile; census; D-107 |
| Zero counts | args_mutated 0, incomplete 0, empty messages 0, null/duplicate call ids 0, pi_detector redaction 0 | census; reconcile |
| `package_version_not_code_identity` | `code_identity = "range"`, `verified_code = []`, so all D rules are cited via `_unverified` twins | profile; D-24 |
| System prompts | 4 variants (651..3,092 chars), none matching a yaml key alone; `system_prompt_variants = []` | profile comment |
| D-107 | `path_must_agree` omits `injection_task_id` (688 stems by design) | DECISIONS |
| D-110..D-112 | suites@2 reviewed tables, read from the code that made the runs. `siphon` called 144 times and `secure_funds` never. Chain has two code states: 19 datamarking logs at `a512e34a`, 128 delimiting logs at `f87dbc74`'s client | DECISIONS; routing R8; C.14.8 |
| `artefacts.toml` | **no entry scoped to `craibench-agentdojo`**. Generic classes may still occur: `injection_task_as_user`, `benign_security_constant`, `payload_not_reaching_agent`, `calls_derived_from_messages` | `src/agentprov/adapters/agentdojo/artefacts.toml` |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2 and §3. Select reasons: include glob; `.DS_Store` / `._*` excluded (expect 0); 1 absent blob |
| L1-02 strict parse | yes | 1,163 logs |
| L1-03 encodings | yes | Datamarking `^` between words is defence content, not mojibake. Possible `\uXXXX` residues (AgentDojo); emoji and Unicode in the suite data are legitimate |
| L1-04 duplicates | yes | Within the part, and across corpora with `l1_xdup.py`. The upstream runs were deleted at `a512e34a`, so expect 0 overlap with `agentdojo-upstream` |
| L1-05 arm coverage | yes | §3 (13 strata, plus the multi/single task class) |
| L1-06 secrets / account paths | yes | Counts and pointers only. Wallet addresses (`0x…`) and IBAN-like strings are benchmark content. v0.k11 records no paths |
| L1-07 timestamps | reduced | v0.k11 has no timestamp field. Confirm 0 timestamp pointers |
| L1-08 degenerate | yes | Expect 0 empty, 0 incomplete, 0 error-only |
| L2 import / validate / recompute / determinism | yes | Scratch corpus via the queue, `--cpu 2` |
| L2 A2 / A3 classes, evidence classes | yes | I-class `_unverified` twins for D rules. 688 `unattributed_additional_user_message` (I) |
| L2 identity | yes | Model from `pipeline_dir`: `gpt-4o` (an undated alias: H11) and `gpt-4o-mini-2024-07-18`. Defence from the two suffixes. Benchmark `craibench` for crypto/chain, `agentdojo` for banking |
| L2 SEM | yes | suites@2: crypto tools known; chain 5 tools unknown (D-112) |
| L2 redaction | yes | Expect no account path in AER/SEM/PROV |
| L2 withholding | inert | MIT, policy include, no use rule. Only the generic secret path applies |
| L2 outcome sanity | partial | Verdict-capable only through the population tally of the 7 gpt-4o and gpt-4o-mini cells in §4. Other strata get Wilson intervals only |
| Delta since E2 | no | Not in E2 |

## 7. Hypotheses (falsifiable; thresholds fixed now)

| Id | Expectation | Falsified if | Class if falsified |
|---|---|---|---|
| H1 | L1 selects exactly 1,163 logs, with the per-stratum counts of §3 (MI 688, PI 435, none 40) | any count differs by ≥ 1 | mapping-defect or source drift |
| H2 | All 1,163 logs parse strictly: 0 duplicate keys, NaN, BOM, invalid UTF-8 or truncation | any hit | source-defect |
| H3 | 0 U+FFFD and 0 mojibake. `^` word-joining occurs only in the 19 datamarking logs | any U+FFFD or mojibake; `^`-joined tool output in delimiting logs | source-defect / mapping, S3 |
| H4 | 0 byte-identical pairs and 0 cross-corpus byte overlap. 0 identical trajectories across different pipeline dirs | ≥ 1 | documentation-mismatch (relabelled runs), S2 |
| H5 | System-prompt variants partition by commit group. Datamarking chain (19) has 1 variant; delimiting chain and banking (131) have 1 or 2; crypto (1,013) has 1 or 2; total 4. All are `default_defended`-based (Secure) plus the defence notice | a group mixes conditions, or a Default/Confirmation-type prompt appears (then each log's condition must be read from its prompt, not assumed) | documentation-mismatch, S2 |
| H6 | The 1,144 delimiting logs carry the `be71b1f5` parenthetical data notice (which is also the delimiter the paper prints in v2 §6, so this half is a consistency check, not a paper mismatch *[fact-check]*), never `<data>`…`</data>` or `<<`/`>>` wrappers. The 435 PI payloads use the unsigned wrapper ("important message to the agent"); the paper (v2 Fig. 15) prints the signed, user- and model-aware one | `<data>` tags or a signed wrapper in ≥ 1 delimiting log | documentation-mismatch (paper vs released code), S2 |
| H7 | The raw tally of gpt-4o delim crypto multi-step reproduces Secure T2 exactly: PI utility 243 and security 84 of 384; MI utility 140 and security 307 of 413 | any count off by > 1 (> 0.3 pp); > 15 pp → S1 candidate | documentation-mismatch, S2 |
| H8 | The raw tally of gpt-4o delim chain reproduces Secure: PI 13 / 27 of 50; MI multi 0 / 45 of 50; MI single 1 / 14 of 14 | any count off by > 1 run | documentation-mismatch, S2 |
| H9 | crypto MI single matches the T3 row labelled DAO/NFT: gpt-4o 14 / 44 of 80; gpt-4o-mini 34 / 80 of 80 (supports a T1/T3 label swap) | > 2 runs off on either (then test the Default and Confirmation rows; no match → those numbers come from unreleased runs) | documentation-mismatch, S3 |
| H10 | The 688 MI logs (exactly the `*_memory_injection` stems) have one extra user message after the query. 0 PI or pre-pass logs have one | any other count | mapping-defect |
| H11 | Model id `gpt-4o` has no snapshot in any log (v0.k11). Identity resolves to the alias verbatim, never to `gpt-4o-2024-05-13` | identity row asserts a dated snapshot | mapping-defect, S2 |
| H12 | 0 provider keys and 0 account paths in the 1,163 logs | any hit | security finding, reported at once |
| H13 | 0 timestamp fields; 0 empty; 0 incomplete; 0 error-only | otherwise | source-defect, S3 |
| H14 | `siphon` is called 144 times and `secure_funds` 0 times (D-111) | any change | mapping or census drift |
| H15 | L2 on 53 units: every stage ok, 0 failing checks, 0 degenerate, 0 `adapter_defect`. `recompute --dry-run` shows 0 differences. The second import (other `--jobs`) is byte-identical. Identity resolves for 100% of units | any failure | mapping-defect |
| H16 | The L2 sample rates of the §4 cells stay within the README §4 gap rule against the Secure numbers | the gap rule fires | investigate (condition identity or outcome mapping) |

Rule: no stratum is excluded for zero attack successes. Many cells are expected near 0% utility (chain MI) or 100% ASR.

## Fact-check (adversarial, 2026-10-14; desk only, no raw data read)

Checked against the v2 HTML and PDF (<https://arxiv.org/html/2503.16248v2>, <https://arxiv.org/pdf/2503.16248v2>), v3 (<https://arxiv.org/html/2503.16248v3>), the arXiv submission history, the GitHub API (repo, branches, PRs, commits, the recursive tree at the pin, LICENSE and `count_true_values.py` at the pin, the `be71b1f5` and `afd3a23b` diffs), the HF dataset API, AgentDojo issues #95/#135/#154/#168, and our census, trial, registry and profile.

**Confirmed.**
- Every §4 paper number (v2 Tables 1–3, right model, suite, prompt, metric), the T1/T3 size swap, the Claude 3.5 PI Total 380, and the version dates and titles.
- 84/384 = 21.875% and 307/413 = 74.33%; no k/390 gives either rate. `count_true_values.py` divides by the files actually present, which supports this reading.
- Pin, tree (1,804 entries, 1,344 blobs, 10,397,914 B, not truncated), runs/ (1,163 blobs, 8,688,961 B, 1,560..21,284 B), the 130 B LFS pointer, and every §3 cell count, including the missing PI tasks and the absent tasks 53 and 54.
- The commit history claims, the alias change and the cache disable at `afd3a23b`, and upstream tag v0.1.15 = `8d2ecb59`.
- MIT licence text at the pin (upstream copyright only). The HF dataset is CC-BY-4.0, sha `9907a151`.
- Census and trial numbers.

**Corrected.**
- The extra crypto injection ids are 5..9 and 11, not 5..11. The crypto pre-pass ids are 0..9 and 11 (id 10 absent). This comes from the tree listing and answers half of the last open question.
- Refuted lead: the paper's "more explicit delimiter" (v2 §6) is the same parenthetical data notice that `be71b1f5` introduced. The paper's memory phrase (v2 §5) also matches. The only paper/code wording mismatch is the PI wrapper (Fig. 15 signed, code unsigned). H6 is annotated accordingly; its thresholds are unchanged.

**Added leads (documents only; no new expectations).**
- `count_true_values.py` maps `default_defended` / `default` / `blockchain` to Secure / Default / Confirmation. For gpt-4o Secure it reads the attacked cells from a `default_defended_es` directory, a name that is not a key in `system_messages.yaml` at the pin, `c07e2b94` or `sft`. Which released prompt variant this is bears on H5 and H7.
- v2 Fig. 20 prints a GPT-4o Secure Trading MI trace for `user_task_7` / `injection_task_2`. That path exists in the release, which ties the paper to these logs.

**Unverifiable here.** The snapshot behind `gpt-4o` (H11), and whether the Default and Confirmation cells come from unreleased runs.
