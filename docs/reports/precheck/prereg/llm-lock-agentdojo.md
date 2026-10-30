# Pre-registration: `llm-lock-agentdojo`

| | |
|---|---|
| Corpus | `llm-lock-agentdojo` (family `agentdojo`, profile `llm-lock-agentdojo` v1, dialect/mapper `agentdojo.tracelogger`, variant `v1.k14`; identity table `tables/llmlock_defence_arms.toml`) |
| Parts | `head` (only part; GPL-3.0, own corpus, D-94) |
| Wave | 3 (first examination; not in FA or E2) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: our prior reports (phase-10c census summary `~/.agentprov/migration-work/phase10c/census/llm-lock@7bb9915b57e0.novel.summary.json`, phase-10d census, `r1/` census, reconcile, trial), the profile, the arm table, the registry, `artefacts.toml`, DECISIONS (D-92, D-94, D-114, D-116), review-core-d CD-15, and desk research (`data/llm-lock-agentdojo/research.json`). Path counts come from the GitHub git-trees listing (names, sizes, blob ids); outcome targets come from the author's nine `results.json` summaries. Nothing here was computed from log contents. |
| Method | [`../README.md`](../README.md) |

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Repository | [Wakeful-Cloud/llm-lock](https://github.com/Wakeful-Cloud/llm-lock) ("CS562 Final Project", UIUC); GPL-3.0 | GitHub API |
| Pin | `7bb9915b57e087536b6bdeae0066adb0d8999958`, 2025-12-15T08:35:36Z, the **only commit** (= head; 0 issues, 0 forks, no tags) | GitHub API |
| Paper / data record | **none** (arXiv, web, Zenodo, HF: 0 hits). Results = per-arm `data/agentdojo/<arm>/results.json` (author `compute-results`), run READMEs; `results-analysis.ipynb` outputs cleared | research.json |
| Harness | AgentDojo **0.1.35**, benchmark **v1.2.2** (both logged in all logs); dependency `Wakeful-Cloud/agentdojo@6ebf27e7` = upstream `5cea5891` (v0.1.35) + 2 crash fixes (`4069297e`, `6ebf27e7`; upstreamed as [PR #136](https://github.com/ethz-spylab/agentdojo/pull/136)) | pyproject.toml, fork history |
| Agent | `PromptingLLM` over Ollama (OpenAI-compatible); model **not recorded** (D-92). Code default `hf.co/unsloth/Llama-4-Scout-17B-16E-Instruct-GGUF:Q3_K_XL`; PR #136 (same author) names "Ollama + Llama 4" as the crash setting | main.py l. 199-202, PR #136 |
| Sampling | temperature 0.0 is never sent at 0.1.35 ([PR #141](https://github.com/ethz-spylab/agentdojo/pull/141), fixed 2026-02-03): server-default sampling | openai_llm.py at `6ebf27e7` l. 162 |
| Hardware / runs | 1x A100 80 GB (ICRN; multiclass partly on Campus Cluster); interrupted and resumed (`force_rerun=False`) | run READMEs |
| Run dates | 2025-11-18 07:05:17 .. 2025-12-15 06:06:22 (naive; Nov 14,490, Dec 38,817) | phase-10c census |

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Tree blobs at pin | 70,075 | profile `expected_files`; git trees API (53,325 + 16,374 + 349 + 8 + 7 + 3 + 9) |
| Selected logs | 53,307 (875,116,320 bytes; 1,629 .. 147,547 bytes each) | registry (`readme_corpora.toml` → census `/files`); phase-10c and r1 census; tree |
| Units / executions | 53,307 `agent_execution` / 53,307 | r1 census (sealed 53,307); trial (5,337 + 1,071 sampled, all stages ok) |
| Per arm | 5,923 × 9 arms | tree; results.json (5,923 overheads per arm) |
| Per arm by suite | banking 905, slack 677, travel 887, workspace 3,454 | tree |
| Per arm by kind | benign 97, pre-pass 35, attacked 6 × 949 = 5,694, dos 97 | tree; results.json denominators |
| Context artefacts | 9 README.md + 9 results.json + LICENSE, README.md, pyproject.toml, uv.lock, 7 `agentdojo/*.py`, `scripts/run.sh` | profile `context_artefacts` |
| Not selected | synthetic dataset 16,374, notebooks 357, other code/config | tree; profile |
| Byte-identical logs | 0 (53,307 distinct blob ids) | tree |
| Variant | `v1.k14` 53,307 | censuses |

## 3. Expected arms

| Facet | Values | Expected missing / extra |
|---|---|---|
| Defence arm (path) | `none`, `data-delimiter` (= `spotlighting_with_delimiting`, D-114), `embedding`, `llm`, `multiclass`, `transformer/protectai-…`, `transformer/qualifire-…`, `hybrid/protectai-…`, `hybrid/qualifire-…` | none; identical label sets in all 9 arms |
| Model | one unrecorded agent (`unk /model not_recorded`) | no model facet |
| Suite | banking (16 UT / 9 IT), slack (21/5), travel (20/7), workspace (40/14) | none |
| Attack | `direct`, `ignore_previous`, `important_instructions`, `injecagent`, `system_message`, `tool_knowledge` (949 pairs each); `dos` (97, placeholder `injection_task_0`); `none` (97 benign, 35 pre-pass) | not run by design: `*_dos` variants, `manual`, `important_instructions_*` variants. The `none` README's "half-complete attacks": expected **0** logs (no extra attack type in the phase-10c census) |
| pipeline_name | `local` 52,722; **`transformer` 585** (transformer/qualifire; direct/ignore_previous/injecagent/system_message × 144 + 9 pre-pass; *banking inferred from these counts, not recorded by suite in the census* [fact-check]) | profile says constant `local` (undocumented exception) |

## 4. Expected outcome rates (comparison targets)

Metric mapping (`agentdojo/main.py` `compute_results`, l. 501-990): benign utility = `utility` over
`user_task_*/none/none.json`; injection-task utility = `utility` over `injection_task_*/none/none.json`; targeted ASR =
`security == true` over **all** attacked logs **including dos** (5,791 per arm); the author's "utility under attack" =
`utility and not security` over the same logs (not AgentDojo's UuA). DoS logs: `security = not utility`
(`dos_security_not_utility`). Values below are the author's whole-population numbers (`results.json`); they are exact
targets for the L1-05 tally and Wilson references for L2.

| Arm | Benign utility | Inj.-task utility | ASR incl. dos | ASR excl. dos | dos ASR | Author UuA | ASR per attack: direct / ign. / imp. / injecagent / sys. / tool_kn. (of 949) |
|---|---|---|---|---|---|---|---|
| none | 19/97 (19.6%) | 16/35 | 440/5791 (7.6%) | 357/5694 (6.3%) | 83/97 | 664/5791 | 25 / 79 / 141 / 33 / 12 / 67 |
| data-delimiter | 16/97 (16.5%) | 18/35 | 405/5791 (7.0%) | 324/5694 (5.7%) | 81/97 | 637/5791 | 12 / 62 / 116 / 36 / 16 / 82 |
| embedding | 13/97 (13.4%) | 12/35 | 256/5791 (4.4%) | 173/5694 (3.0%) | 83/97 | 650/5791 | 7 / 27 / 71 / 11 / 4 / 53 |
| llm | 13/97 (13.4%) | 9/35 | 129/5791 (2.2%) | 44/5694 (0.8%) | 85/97 | 767/5791 | 0 / 14 / 22 / 4 / 0 / 4 |
| multiclass | 11/97 (11.3%) | 7/35 | 127/5791 (2.2%) | 41/5694 (0.7%) | 86/97 | 734/5791 | 1 / 7 / 12 / 4 / 2 / 15 |
| transformer/protectai | 16/97 (16.5%) | 10/35 | 165/5791 (2.8%) | 74/5694 (1.3%) | 91/97 | 581/5791 | 4 / 0 / 24 / 1 / 5 / 40 |
| transformer/qualifire | 18/97 (18.6%) | 15/35 | 143/5791 (2.5%) | 56/5694 (1.0%) | 87/97 | 553/5791 | 7 / 11 / 13 / 2 / 2 / 21 |
| hybrid/protectai | 13/97 (13.4%) | 13/35 | 202/5791 (3.5%) | 114/5694 (2.0%) | 88/97 | 670/5791 | 7 / 9 / 36 / 6 / 1 / 55 |
| hybrid/qualifire | 14/97 (14.4%) | 15/35 | 150/5791 (2.6%) | 63/5694 (1.1%) | 87/97 | 568/5791 | 2 / 14 / 19 / 3 / 3 / 22 |

Per suite (ASR incl. dos; benign utility), from `results.json /pipelines/local/suites/<suite>/statistics`:

| Arm | banking | slack | travel | workspace |
|---|---|---|---|---|
| none | 187/880; 9/16 | 151/651; 8/21 | 20/860; 0/20 | 82/3400; 2/40 |
| data-delimiter | 167/880; 7/16 | 129/651; 6/21 | 20/860; 0/20 | 89/3400; 3/40 |
| embedding | 118/880; 7/16 | 48/651; 3/21 | 20/860; 0/20 | 70/3400; 3/40 |
| llm | 28/880; 5/16 | 38/651; 2/21 | 20/860; 0/20 | 43/3400; 6/40 |
| multiclass | 27/880; 6/16 | 29/651; 2/21 | 20/860; 0/20 | 51/3400; 3/40 |
| transformer/protectai | 37/880; 8/16 | 50/651; 4/21 | 20/860; 0/20 | 58/3400; 4/40 |
| transformer/qualifire | 30/880; 9/16 | 19/651; 7/21 | 20/860; 0/20 | 74/3400; 2/40 |
| hybrid/protectai | 53/880; 8/16 | 44/651; 3/21 | 20/860; 0/20 | 85/3400; 2/40 |
| hybrid/qualifire | 31/880; 8/16 | 18/651; 3/21 | 20/860; 1/20 | 81/3400; 2/40 |

Cross-check already in our reports: security true over all logs = 2,017 (sum of ASR numerators) + 1,188 benign/pre-pass
constants = **3,205** = phase-10c census `security.True`; utility true = **6,371** (census), of which 133 benign + 115
pre-pass + 5,824 utility-and-not-security, leaving **299** attacked logs with utility and security both true.

L2: ~300 sampled units over 9 arms gives ≈ 33 per arm (≥ 20), so the 15-point rule applies per arm on a stratum-weighted
rate (the sample over-represents benign, pre-pass and dos strata; compare per stratum or re-weight to the population
shares). Per arm × attack cells (≈ 3-4 units) are Wilson-only. The exact comparison is H3 on the whole population.

## 5. Known quirks

| Id | Expected (r1 census) | Source |
|---|---|---|
| `agentdojo.benign_security_constant` (art. `agentdojo.art.benign_security_constant`) | 1,188 files, 1,188 origin rule (132 per arm) | profile, r1 census |
| `agentdojo.injection_task_as_user_task_prepass` (art. `.injection_task_as_user`) | 315 (35 per arm) | profile, r1 census |
| `agentdojo.dos_security_not_utility` (art. `.dos_polarity`) | 873 (97 per arm) | r1 census |
| `agentdojo.unexecuted_trailing_calls` (art. `.max_iters_pending`) | 1,699 calls in 1,697 logs | profile, r1 census |
| `agentdojo.silent_rerun_last_pass_only` | 0 null-final logs; `earlier_attempts_unobservable` on 53,307 | profile, census |
| `agentdojo.args_mutated_in_place` | 48,942 files with calls | profile, census |
| `agentdojo.placeholder_args_never_injection_evidence` | 196,848 present, all null | profile, census |
| `agentdojo.spotlighting_delimiters` | data-delimiter: 5,923 logs, 5,393 with tool results | profile, r1 census |
| `agentdojo.pi_detector_redaction` | 13,857 redactions in 5,376 logs (both transformer arms, hybrid/qualifire) | profile, r1 census |
| `agentdojo.detector_abort` (D-116, R10) | 11,505 aborts: embedding 1,281, hybrid/protectai 1,694, llm 4,278, multiclass 4,252; 1,341 `detector_abort_output_unrecorded` | profile, r1 census, routing R10 |
| `agentdojo.unknown_top_level_key` | 35,928 files (detector keys kept in `ext.agentdojo.extra`) | r1 census |
| Tool errors | 88,197, none a denial (no R1 quirk) | profile, D-114 |
| Identity | 9 table rows, defence only; `identity_unresolved` + `unk /model not_recorded` on all 53,307 (D-92, D-114) | table, profile |
| Evidence | `verified_code = []`: every D rule via its `_unverified` twin (class I) | profile, D-115 |
| System prompt | `llmlock_default` 47,384; `llmlock_data_delimiter` 5,923 | profile, phase-10c census |
| Secrets | 1 file (hybrid/qualifire, workspace `user_task_19`), 2 secret-like strings (`openai_sk` pattern) | profile, phase-10c census |
| CD-15 | detector_abort ignores a recorded run error; latent here (0 error logs) | review-core-d, regen item 43 |
| Profile drift | profile digest now `3a35e8…` (D-31: `agentdojo` rule catalogue 1 → 2, `c17ba983`); trial ran `679bcb…`; registry evidence cites the draft census (`4cacc6…`) | git, census files |
| artefacts.toml | **no entry scoped to `llm-lock-agentdojo`**; generic classes expected: benign_security_constant, injection_task_as_user, dos_polarity, max_iters_pending, naive_timestamp, defence_benign_intervention, payload_not_reaching_agent, validity_defects, banking_ut15_confound | `artefacts.toml` |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2; per arm × suite × kind; selection by the two `include` globs |
| L1-02 strict parse | yes | expect 0 defects in logs (phase-10c: 4 non-finite numbers and 1 oversized file are outside the logs) |
| L1-03 encodings | yes | count only; AgentDojo escape residues possible (expected-known) |
| L1-04 duplicates | yes | 0 byte-identical (tree); trajectory repeats across arms: H14; cross-corpus: none expected |
| L1-05 arm coverage | yes | §3 full factorial + whole-population outcome tally against §4 (H3) |
| L1-06 secrets / account paths | yes | 1 file / 2 strings; 0 account paths |
| L1-07 timestamps | partly | one naive `evaluation_timestamp` per log; parse, zone, range apply; within-unit monotonicity not applicable |
| L1-08 degenerate | yes | 0 empty, 0 null-final, 0 error logs; travel degeneracy (H12) |
| L2 import, validate, recompute, determinism | yes | trial: 0 failures; jobs 8 vs 3 byte-identical on the overlapping subset (4,314 objects, `n_differ` 0) [fact-check] |
| L2 A2 / A3 classes | yes | expect only the trial's register codes (accounting_unverifiable, earlier_attempts_unobservable, identity_unresolved on all; unknown_top_level_key ≈ 67%; unexecuted_tool_call ≈ 3%; detector_abort_output_unrecorded ≈ 2.5%) |
| L2 evidence classes | yes | D rules only as `_unverified` twins; abort and redact decisions class I |
| L2 degenerate / adapter_defect | yes | expect 0 / 0 |
| L2 identity | yes | model `not_recorded` on all; defence per table; the 585 `transformer` logs resolve like the rest |
| L2 redaction | yes | no account path |
| L2 withholding | conditional | only for the secret-like file (if sampled or withheld) |
| L2 outcome sanity | yes | per arm (≥ 20 sampled), Wilson per cell; §4 |
| Delta since E2 | no | not in FA/E2 |

## 7. Hypotheses (falsifiable)

| # | Expectation | Refuted if |
|---|---|---|
| H1 | 53,307 logs; 5,923 per arm; per arm 905/677/887/3,454 by suite; 97 benign, 35 pre-pass, 949 per attack, 97 dos | any cell off by ≥ 1 |
| H2 | Identical label sets in all 9 arms; 0 attack types outside the 7 + `none`; 0 byte-identical files | any extra or missing label |
| H3 | Whole-population tally reproduces `results.json` exactly per arm × suite × attack: `security` true counts, benign and pre-pass `utility`, `utility and not security`; totals 3,205 security true, 6,371 utility true | any cell off by ≥ 1 |
| H4 | Quirk counts of §5 reproduce exactly, incl. per-arm aborts 1,281 / 1,694 / 4,278 / 4,252 and 13,857 redactions in 5,376 logs | any differs |
| H5 | Sentinel text appears only in the 3 redacting arms; logs ending at a tool message occur only in the 4 aborting arms | ≥ 1 sentinel or tool-ending log elsewhere |
| H6 | `pipeline_name` = `transformer` in exactly 585 logs, all transformer/qualifire banking {direct, ignore_previous, injecagent, system_message} + 9 pre-pass; `local` elsewhere | any other location or count |
| H7 | Embedding arm (pinned code: abort when p_benign ≥ 0.5): ≥ 95% of the 1,281 aborts end at a check with logged p_mal ≤ 0.5, and ≥ 95% of checks in non-aborted runs have p_mal > 0.5 | < 95% on either (then the pinned code did not run; if the opposite pattern holds ≥ 95%, the code at the pin is not the producing code: documentation finding) |
| H8 | Transformer arms: in ≥ 95% of logs with detector keys, the number of logged `classification_malicious_probability` ≥ 0.5 equals the number of sentinel redactions (post-hoc "fix" consistent with run-time decisions) | < 95%; if instead the count of values < 0.5 matches in ≥ 95%, run-time decisions were inverted (S1 for those two arms) |
| H9 | Detector extra keys occur only in the 7 detector arms (35,928 files); 0 in `none` and `data-delimiter` | ≥ 1 in those two |
| H10 | 53,307 naive timestamps, 100% parse, 0 zoned, range 2025-11-18 07:05:17 .. 2025-12-15 06:06:22; ≥ 1 log before 2025-11-21 00:57 (pre-fix code) | absent, zoned, out of range, or none pre-fix |
| H11 | Secret-like strings: 1 file, 2 matches; account paths 0 | other counts |
| H12 | Travel: non-DoS `security` true = 0 of 840 in every arm; benign utility 0/20 in 8 arms (1/20 hybrid/qualifire) | any travel non-DoS success, or other benign counts |
| H13 | L2 per-arm stratum-weighted ASR and benign utility within 15 points of §4 (arms with ≥ 20 sampled) | gap > 15 points or outside the Wilson rule of README §4 |
| H14 | Identical trajectory fingerprints across arms ≤ 5% of logs (sampled agent, temperature not sent); cross-corpus 0 | above either |
| H15 | L2: 0 adapter_defect, 0 degenerate, `identity_unresolved` on 100%, 0 failing validation checks, byte-identical second import | any deviation |

## 8. Discrepancy leads carried to the dossier

585 `transformer` pipeline names contradict the profile's constant `local` (mixed code state in one arm, undocumented);
the pinned `embedding_defense.detect` returns `is_benign` as the detection flag (inverted decision if that code ran);
the transformer arms' probabilities were edited after the run (README); three arms redact with code that is not at the
pin (dead `transform`), so the two hybrid arms are different mechanisms; `hybrid/protectai` is launched with Sentinel in
`run.sh`; the `none` README's half-complete attacks are absent from the tree, though our profile repeats the claim;
temperature never sent (upstream #141) and runs split across two clusters (multiclass); earliest logs predate the fork
fixes; travel is degenerate in the author's own numbers; the author's UuA and ASR definitions differ from AgentDojo's;
PR #136 names "Llama 4" (a D-92 review item for the orchestrator, not a mapping change); the registry cites the draft
census; profile digest changed since the trial (D-31); no `artefacts.toml` entry scopes this corpus.

## 9. Fact-check (2026-10-14, adversarial, desk only)

Re-checked against the GitHub API at the pin, the nine `results.json` files (context artefacts, not logs), the fork and
upstream AgentDojo history, the LICENSE file and our own prior reports. No raw log was read. Details and URLs:
`data/llm-lock-agentdojo/research.json` `/fact_check`.

**Confirmed.**
- Pin and repository: a single signed commit. Tree walked in full: 70,075 blobs, broken down as in §2. Logs: 53,307
  logs, 875,116,320 bytes, 0 byte-identical; 5,923 per arm, 905/677/887/3,454 per suite, 97/35/6×949/97 per kind,
  identical label sets in all 9 arms.
- Outcome targets: every number in the §4 tables was recomputed from the nine `results.json` files and matches,
  including travel non-DoS 0/840 and the 2,017/133/115/5,824 sums. Metric definitions confirmed in `compute_results`.
- Licence: LICENSE is byte-identical to gnu.org GPL-3.0 (sha256 `3972dc97…`).
- Upstream: PR #136 (author, dates, "Ollama + Llama 4") and PR #141 (temperature) as stated.
- Fork history: fork created 2025-11-20, fixes dated 2025-11-21 and 2025-11-24.
- Pinned code: raise at l. 132 before transform at l. 139; embedding `detect` returns `is_benign` at l. 80;
  `hybrid/protectai` is launched with Sentinel in `run.sh`.
- Our reports: census, r1 and trial figures and profile digests as cited. No `artefacts.toml` scope names this corpus.
  No paper or data record exists.

**Corrected.**
1. Only the `none` run README links the two crash-fix commits; the run READMEs as a group do not.
2. `5cea5891` is a changelog-only commit one after tag v0.1.35 (`a75aba76`), not PR #130.
3. The location of the 585 `transformer` logs in banking is inferred from the counts. Our census has no suite ×
   pipeline_name cross-tab. H6 stays as written, but "banking" is an expectation, not a prior measurement.
4. Time-zone wording: the latest log comes before the commit only if the clock was at UTC−2 or east of it.
5. The trial's determinism check covered only the overlapping subset (4,314 objects); it was not two full imports.

**Unverifiable.**
- The qualifire Sentinel `id2label`: the HF model is gated (now `rogue-security/…`).
- Whether the run-time detector decisions were inverted. This stays H7/H8.

