# Pre-registration: `agentdojo-upstream`

| | |
|---|---|
| Corpus | `agentdojo-upstream` (family `agentdojo`, profile `agentdojo-upstream@2`, rules `aer 1 / agentdojo 2`, SEM `agentdojo.suites@2`) |
| Parts | `agentdojo` · `head`: 36,679 TraceLogger logs under `runs/` at `ethz-spylab/agentdojo@089ed468cf3ed0322acc66b0211f26d9d90dbf60` (git, `runs` tree `472cbb2e…`); `agentdojo` · `2024-06`: 18,241 logs at `@c274885610efaaafec38b6d3eb07152ba7ff3f94` (`runs` tree `1227480d…`) |
| Code commit | `065b0d36` (branch `precheck-corpora`) or later |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Wave 1, delta corpus (imported in full at `afe7038`, examined in E2 without network); this pre-check examines the **delta since E2** and adds the desk research E2 lacked |
| Desk research | `../data/agentdojo-upstream/research.json` (all URLs there) |

Sources: **P** = `src/agentprov/adapters/agentdojo/profiles/agentdojo-upstream.profile.toml`; **C-h** / **C-06** =
`docs/reports/agentdojo/census-head.json` / `census-2024-06.json`; **I-h** / **I-06** = `import-cli-head.json` / `import-cli-2024-06.json`;
**R** = `tools/readme_corpora.toml` and the registry; **A** = `src/agentprov/adapters/agentdojo/artefacts.toml`; **E2** / **FA** = examination 2 /
first analysis (`phase10-corpus-analysis.md`); **U6** = `phase10-examination-2-data/u06-bymodel.json` (executions per model); **RB** =
`docs/reports/analysis/regen-batch.md`; **G** = GitHub API 2026-10-14; **P1** / **P3** = AgentDojo paper arXiv:2406.13352 v1 / v3 (v2 = v3
numbers); **W** = upstream results page (`util_scripts/create_results_table.py` at the head pin); **SA1** / **SA2** = Meta SecAlign
arXiv:2507.02735 v1 / v2 (v3, v4 repeat v2's AgentDojo numbers, as v3 Tables 5/10 and v4 Tables 4/8; v4 is retitled "Meta-SecAlign: Training LLMs against Prompt Injection for Robust Agents") [fact-check: table numbers per version added].

## 1. Desk research summary

- **Paper versions.** v1 2024-06-19 (preprint), v2 2024-07-18 (after the travel-suite and Llama re-runs, adds Claude 3.5 Sonnet), v3
  2024-11-24 (NeurIPS 2024 D&B; the arXiv comment names the Llama fix and the travel update; numbers equal v2). No `runs/` commit lies
  between the 2024-06 pin (2024-06-05) and 2024-06-20, so **P1 describes the `2024-06` part and P3 the `head` part** for the 2024 models.
  Most Table 2-5 numbers moved between v1 and v2 (UA and ASR of every Table 3 model except Command-R+ ASR; unchanged: some benign
  utilities, the PI-detector arm's benign and ASR, and the TODO/ignore/InjecAgent targeted ASR).
- **Repository unchanged since the pin** (G): `089ed468` is still `main`'s HEAD (pushed 2026-06-02); the last `runs/` commit is
  `9272bf1e` (2025-07-25, Llama-3.3 and Meta-SecAlign-70B, PR #96); the 29 commits after it (GitHub compare `9272bf1e...089ed468`, incl. the PR #96/#97 merges) touch no file under `runs/` [fact-check: was "22 later commits"]. Release tag `v0.1.35` (`a75aba76`)
  has the same `runs/`. History around the pins: Mixtral removed 2024-07-15 (`15de4430`); travel re-runs and Llama update 2024-07-16/17.
- **Data record.** The git tree is the release. Zenodo concept `10.5281/zenodo.12528188` = 36 software-release zips (md5 per zip; declared licence **CC-BY-4.0 on the 21 records v0.1.7..v0.1.22 (2024-06-25..2024-11-19), MIT on the 15 from 'v1.1.23' (2025-01-15) on** [fact-check: was "MIT"]):
  `17458493` (v0.1.35, 106,596,113 B) and `12742856` (v0.1.8, 52,728,653 B) are P's alternative origins; per-file comparison with our git
  pins is not possible from Zenodo metadata. No official HF dataset.
- **Harness.** 2024-06: `function-calling-pi` 0.1.0, no versioned suites. Head: v0.k11 logs from 50 introducing commits; 11,765 v1.k14
  logs from the 0.1.30+ code with a local vLLM pipeline (PR #97). Suites: v1/v1.1.x 97 user × 27 injection tasks (629 pairs);
  v1.2.x 35 injection tasks (949 pairs). Relevant bugs: run errors set `security = true` (#154); LocalLLM drops calls and turns server
  errors into empty answers (#150, #202, #219, #220); checker fixes in 0.1.15 (workspace IT4/IT5) and 0.1.21; banking IT0/1/3 (#181) and
  UT5 (#161) still wrong; slack IT5 scores proposed calls (#168). The PI-detector loop bug (#117, fixed #125) is absent at `c2748856`.
- **Semantics** (maintainer, #95, #119): `security = true` means the injection task succeeded; on benign runs it is always true.
- **Licence.** MIT (2024, Debenedetti et al.), added 2024-06-10, so **absent at the 2024-06 pin**; no data licence or use clause;
  the Zenodo deposits declare CC-BY-4.0 up to v0.1.22 (incl. P's v0.1.8 origin) and MIT from 2025-01 [fact-check];
  Llama 3 / 3.3 Community Licence on the local models' outputs (unassessed, as P says).

## 2. Expected counts

| Quantity | head | 2024-06 | Source |
|---|---:|---:|---|
| Files / bytes at the pin (`runs/`) | 36,679 / 426,293,413 | 18,241 / 188,873,874 | P pins; I-h, I-06 |
| Selected (`runs/**/*.json`) / selection exclusions | 36,679 / 0 | 18,241 / 0 | P; I-06 (excluded 0, filtered 0) |
| Archive members | 0 | 0 | P (git tree) |
| Units `agent_execution` / `outcome_only` | 36,472 / 207 | 18,034 / 207 | C-h, C-06 |
| Variants | v0.k11 24,914, v1.k14 11,764, v1.k14.incomplete 1 | v0.k11 18,241 | C-h, C-06 |
| Executions (registry) | 36,679 | 18,241 | R |
| Shared blobs between parts / part-only | 14,182 / 22,497 | 14,182 / 4,059 (4,052 superseded + 7 Mixtral) | E2 §7.3; P note |
| AER records at E2 | 1,153,595 | 553,182 | I-h, I-06 |
| Status ok / ok_with_issues at E2 | 33,745 / 2,934 | 17,747 / 494 | I-h; E2 §7.1 |
| Completeness at E2 (verified / known_incomplete / unverifiable) | 232 / 83 / 36,364 | 232 / 51 / 17,958 | I-h; E2 §7.1 |
| Paper design per model (v1.1 / v1.2) | 97 benign + 27 / 35 pre-passes + 629 / 949 per attack; DoS 97 per attack | same (v1 only) | P1/P3 Table 1; SA1 §4; G (PR #96) |

## 3. Expected arms (L1-05)

Facets: `pipeline_dir` (model, defence suffix) × `attack_dir` × `suite`. Per-directory counts are **derived** (marked d) from C-h/C-06,
U6 and the quirk counts; their sums equal the census totals exactly (head 36,679, of which the four local dirs = 11,765 v1.k14; 2024-06
18,241). `none` = 97 benign user tasks + pre-passes (27 or 35); suite split per attack: workspace/slack/travel/banking 240/105/140/144
(v1.1) or 560/105/140/144 (v1.2); benign 40/21/20/16; pre-passes 6/5/7/9 (v1.2: 14/5/7/9).

| Directory | head | 2024-06 | Attack dirs |
|---|---:|---:|---|
| `gpt-4o-2024-05-13` | 6,899 d | 6,899 d | `none` 124; 629 each: `important_instructions`, `ignore_previous`, `direct`, `injecagent`, `tool_knowledge`, `important_instructions_{no_names,no_model_name,no_user_name,wrong_model_name,wrong_user_name}`; 97 each: `dos`, `captcha_dos`, `felony_dos`, `offensive_email_dos`, `swearwords_dos` (485, C) |
| `gpt-4o-2024-05-13-{repeat_user_prompt,spotlighting_with_delimiting,tool_filter,transformers_pi_detector}` | 753 each d | 753 each d | `none` 124, `important_instructions` 629 |
| `claude-3-haiku-20240307`, `claude-3-opus-20240229`, `claude-3-sonnet-20240229`, `command-r`, `command-r-plus`, `gemini-1.5-flash-001`, `gemini-1.5-pro-001`, `gpt-3.5-turbo-0125`, `gpt-4-0125-preview`, `gpt-4-turbo-2024-04-09`, `meta-llama_Llama-3-70b-chat-hf` | 753 each | 753 each | as above |
| `claude-3-sonnet-20240229-repeat_user_prompt` | 40 d | 40 d | `none` only (derived from the benign census count; suite workspace expected) |
| `mistralai_Mixtral-8x7B-Instruct-v0.1` | — | 7 d | `none` only (derived) |
| `claude-3-5-sonnet-20240620`, `claude-3-5-sonnet-20241022`, `gemini-1.5-flash-002`, `gemini-1.5-pro-002`, `gemini-2.0-flash-exp`, `gpt-4o-mini-2024-07-18` | 753 each | — | `none` 124, `important_instructions` 629 |
| `claude-3-7-sonnet-20250219`, `gemini-2.0-flash-001` | 1,081 each | — | `none` 132, `important_instructions` 949 |
| `Meta-SecAlign-70B`, `Meta-SecAlign-70B-repeat_user_prompt`, `meta-llama_Llama-3.3-70B-Instruct` | 2,979 each d | — | `none` 132; 949 each: `direct`, `ignore_previous`, `important_instructions` |
| `meta-llama_Llama-3.3-70B-Instruct-repeat_user_prompt` | 2,828 d | — | as above, **151 attacked cells missing** (pre-passes and benign complete) |

Outcome-only: the 207 `claude-3-opus-20240229` workspace `important_instructions` logs (both parts, the same blobs). **Expected missing
cells** against the design: Llama-3.3-repeat 151 attacked; Mixtral 746 of 753; claude-3-sonnet-repeat 713 of 753. **Expected extra
(unpublished) arms:** Mixtral, claude-3-sonnet-repeat, gpt-4o DoS (P3 Figure 20 has no numbers), Llama-3.3 and SecAlign `direct` and
`ignore_previous`; claude-3-haiku, command-r, gpt-4-0125, gpt-4o-mini, the 002/2.0 Geminis, claude-3.5-sonnet-20241022 and 3.7 appear
only on W. `path_must_agree` (suite, user task, attack, injection task): 0 mismatches expected (I-h, I-06).

## 4. Expected outcome rates

**Mapping.** Utility = `utility` of `none`-attack `user_task_*` logs (pre-passes `injection_task_*` excluded); utility under attack (UA)
= `utility` over an attack's (user, injection) logs; targeted ASR = `security` over the same logs (`true` = attack succeeded). Benign
`security` is the runner constant (`agentdojo.benign_security_constant@1`, never an ASR input); run errors impose `utility = false,
security = true` (`agentdojo.run_error_imposed_outcome@1`, origin `harness_default`); DoS: `security = not utility`. In the AER these
are `utility`/`security` judgements whose origin rule distinguishes checker from harness. Denominators: W uses k/97 (utility) and k/629
(UA, ASR; v1.1.2 task set, also for the v1.2 models) over the raw fields, run errors included. The paper's benign utility is k/629 (each
user task's benign result weighted by its suite's injection-task count; inferred, H-09); its UA and ASR are k/629. SA uses k/97 and k/949.

| Arm (dir / attack) | 2024-06 expected (P1) U / UA / ASR | head expected (P3) U / UA / ASR | head W U / UA / ASR |
|---|---|---|---|
| gpt-4o / important_instructions | 69.00 (T3; T5 69.07) / 44.99 / 53.10 | 69.00 / 50.08 (T5 50.01) / 47.69 (T5 57.69) | 69.07 / 50.08 / 47.69 |
| claude-3-opus | 64.39 / 49.60 / 12.89 | 66.61 / 52.46 / 11.29 | 68.04 / 52.46 / 11.29 |
| claude-3-sonnet | 53.10 / 30.05 / 30.52 | 53.10 / 33.23 / 26.71 | 53.61 / 33.23 / 26.71 |
| command-r-plus | 27.78 / 25.60 / 0.95 | 25.44 / 25.12 / 0.95 | 24.74 / 25.12 / **4.45** |
| gpt-3.5-turbo-0125 | 34.98 / 34.82 / 8.90 | 33.86 / 34.66 / 8.43 | 35.05 / 34.66 / **10.33** |
| gpt-4-turbo-2024-04-09 | 58.98 / 51.67 / 31.96 | 63.43 / 54.05 / 28.62 | 64.95 / 54.05 / 28.62 |
| gemini-1.5-flash-001 | 36.09 / 34.02 / 13.35 | 36.09 / 34.18 / 12.24 | 38.14 / 34.18 / 12.24 |
| gemini-1.5-pro-001 | 42.29 / 29.61 / 27.50 | 45.63 / 28.93 / 25.60 | 46.39 / 28.93 / **28.62** |
| Llama-3-70b | 31.16 / 19.39 / 15.10 | 34.50 / 18.28 / 20.03 | 34.02 / 18.28 / **25.60** |
| claude-3-5-sonnet-20240620 | — | 78.22 / 51.19 / 33.86 | 79.38 / 51.19 / 33.86 |
| gpt-4o-…-spotlighting_with_delimiting | 72.66 / 50.24 / 46.26 | 72.66 / 55.64 / 41.65 | 72.16 / 55.64 / 41.65 |
| gpt-4o-…-transformers_pi_detector | 41.49 / 20.67 / 7.95 | 41.49 / 21.14 / 7.95 | 41.24 / 21.14 / 7.95 |
| gpt-4o-…-repeat_user_prompt | 73.13 (sic; = tool filter) / 65.66 / 30.84 | 85.53 / 67.25 / 27.82 | 84.54 / 67.25 / 27.82 |
| gpt-4o-…-tool_filter | 73.13 / 53.26 / 7.47 | 73.13 / 56.28 / 6.84 | 72.16 / 56.28 / 6.84 |
| gpt-4o / `direct`, `ignore_previous`, `injecagent` (ASR) | 3.66, 5.41, 5.72 (T4) | 3.66, 5.41, 5.72 | 3.66, 5.41, 5.72 (UA 67.25, 66.77, 68.52) |
| gpt-4o / `tool_knowledge` | — | — | 69.07 / 57.71 / 34.50 |
| gpt-4o ablation ASR: `_no_names`, `_wrong_user_name`, `_wrong_model_name`, `_no_model_name`, `_no_user_name` | 45.8, 23.2, 25.1, 49.8, 44.4 (T2) | 45.8, 23.2, 23.7, 46.1, 44.8 | — |
| claude-3-haiku / command-r / gpt-4-0125 | — | — | 39.18/33.39/9.06; 26.80/30.84/3.34; 65.98/40.70/56.28 |
| gpt-4o-mini; gemini-1.5-flash-002; -pro-002; claude-3-5-sonnet-20241022 | — | — | 68.04/49.92/27.19; 38.14/32.43/3.50; 61.86/47.06/17.01; 79.38/72.50/1.11 |
| gemini-2.0-flash-exp; gemini-2.0-flash-001; claude-3-7-sonnet (629 subset) | — | — | 46.39/39.90/17.01; 43.30/39.75/20.83; 88.66/77.27/7.31 |
| Llama-3.3-repeat / important_instructions (n 97 / 949) | — | SA1 56.7 / 39.0 / 14.1; SA2 59.8 / 43.4 / 14.7 | — |
| Meta-SecAlign-70B-repeat / important_instructions | — | SA1 77.3 / 72.3 / 2.1; SA2 84.5 / 79.5 / 1.9 | — |
| Llama-3.3 (no sandwich) / important_instructions | — | SA1 55.7 / 37.4 / 22.6; SA2 62.9 / 41.9 / 23.0 | — |
| Meta-SecAlign-70B (no sandwich) / important_instructions | — | SA1 75.3 / 72.7 / 2.3; SA2 79.4 / 77.1 / 2.3 | — |

P1 = v1 Tables 2-5; P3 = v3 Tables 2-5 (Table 3 for models, 5 for defences, 4 for attacks, 2 for the ablation); W rows from
`https://agentdojo.spylab.ai/results/`; SA tables: SA1 Table 3 and 8, SA2 Table III and IX. Bold: W disagrees with P3 (L-01).

**L2 use.** About 310 head strata and 190 2024-06 strata (arm key = dir × attack × suite) against the 300-unit cap give 1-2 units per
stratum, so no (model, attack, suite) arm reaches 20 sampled executions: Wilson intervals only. The README threshold (>15 pp with
n >= 20, or a 95 % interval excluding the expected rate by >5 pp) is applied to pooled arms only: `important_instructions` over all
753-type dirs per part (expected = sample-weighted mean of the per-dir W or P values), and the gpt-4o base dir over its attacks. The
decisive outcome test is the **whole-population recount of the raw fields** (H-08..H-14, an L1-05 extension; counts only).

## 5. Known quirks (already declared)

| Id | head | 2024-06 | Where |
|---|---:|---:|---|
| `agentdojo.benign_security_constant` (files / judgements under the rule) | 3,560 / 3,546 | 2,031 / 2,014 | P; A |
| `agentdojo.dos_security_not_utility` / `.art.dos_polarity` | 485 | 485 | P; A |
| `agentdojo.silent_rerun_last_pass_only` (null-final) | 82 | 47 | P; A |
| `agentdojo.injection_task_as_user_task_prepass` | 804 | 432 | P; A |
| `agentdojo.empty_messages_with_outcome` / `.art.empty_log` | 207 | 207 | P; A |
| `agentdojo.run_error_imposes_outcome` | 105 (command-r-plus 25, gemini-1.5-pro-001 22; FA §8 row 2) | 106 | P; A; FA |
| `agentdojo.incomplete_run` | 1 (v1.k14.incomplete) | 4 | P; A |
| `agentdojo.provider_call_id_anomalies` (absent / empty / null calls; logs with absent or empty; colliding empty; repeated) | 4,690 / 12,583 / 47,227; 5,239; 2,725; 213 | 4,413 / 4,522 / 0; 2,799; 965; 189 | P; C |
| `agentdojo.args_mutated_in_place` | 10,595 | 0 | P |
| `agentdojo.package_version_not_code_identity` | 11,765 | 0 | P; A |
| `agentdojo.unexecuted_trailing_calls` (logs / calls) | 800 / 815 | 145 / 153 | P; A |
| `agentdojo.pi_detector_redaction` (logs / redactions) | 622 / 2,138 | 624 / 2,154 | P; A |
| `agentdojo.tool_filter_aux_llm`, `spotlighting_delimiters` | 753 / 753; 753 / 744 | 753 / 753; 753 / 745 | P |
| `agentdojo.repeat_user_prompt_reinsertion` (logs / with copies) | 6,600 / 5,998 | 793 / 774 | P |
| `agentdojo.local_model_raw_completion` (turns > calls / tags, no call) | 2,996 / 1,192 (1,854 logs, `local_parse_drop_possible`) | 0 | P; A; C-h (`files_by_issue_code`; FA §5) [fact-check: the 1,854 is in C-h, not I-h] |
| `agentdojo.placeholder_args_never_injection_evidence` | 61,461 present and null | 0 | P |
| `agentdojo.art.banking_ut15_confound` | 11 | 9 (RB item 4; A still says 200, seed) | A; RB |
| `agentdojo.art.validity_defects` (vacuous utility) | 182 | 81 | A; E2 §10 |
| `agentdojo.art.payload_not_reaching_agent` | 5,895 | 2,921 of 15,725 attacked | A; E2 §10 |
| `agentdojo.art.defence_benign_intervention` | 81 benign PI runs | 81 | A; E2 |
| `agentdojo.art.checker_era`, `.unwinnable_cell`, `.failed_sink`, `.replay_dispute` (seed counts) | — | 1,931 / 434 / 628 / 8 (unverified seeds) | A |
| E2 N1 cross-part duplicates | 14,182 | 14,182 | E2 §7.3 |
| E2 N2 wholly escaped tool arguments (executions) | 436 | 117 | E2 §4.1 |
| E2 N4 empty assistant turns without calls (executions) | 343 | 48 | E2 §4.2 |
| FA identical-trajectory groups / executions | 382 / 3,612 | 150 / 816 | FA §4.6; E2 §7.1 |
| E2 raw: paired surrogate escapes (objects); lone surrogates; dup keys; NaN | 4; 0; 0; 0 | 6; 0; 0; 0 | E2 §4.1, A04 |
| History fields (era from introducing commit) | pre_versioning 14,182; v1->v1.1 4,470; v1.1->v1.1.1 1,088; v1.1.1->v1.1.2 2,259; v1.2->v1.2.1 2,915 (v0.k11); 50 commits 2024-06-02..2025-07-25 | all at or before `c2748856` | I-h |
| System-prompt variants (D-207) | `agentdojo_default` 23,954 v0.k11 + 11,765 v1.k14; `…_spotlighting_2024_06` 606; `…_spotlighting` 147; none 207 | default 17,281; `…_2024_06` 753; none 207 | RB item 17 |

## 6. Expected movement since E2 (stored `*-p10.partial` at `afe7038` → scratch import at `065b0d36`)

Nothing upstream moved (G), so **every L1 count equals the census** (§2, §5). Movement is in the derived files only:

| Change (decision) | head | 2024-06 |
|---|---|---|
| D-31 bumps (item 30) | every AER header: `rules` agentdojo 2, profile v2 (new sha); SEM `suites@2` (was @1) | same |
| Items 3, 13 (D-80, D-84) | 22,497 executions cite `_unverified` twins (I): the 10,732 v0.k11 logs introduced after `c2748856` and the 11,765 v1.k14 logs; the 14,182 shared logs stay D. Equivalently: twins iff head-only (H-15) | 0 twins except the code-independent/c6 rules (`functions_runtime`, `committed_no_later_than` 18,241; `empty_assistant_text_ambiguous` 788) |
| Items 9, 11 (D-372) with 13 | completeness 232 / **47** / **36,400** (36 retries known_incomplete → unverifiable) | 232 / 51 / 17,958 (unchanged) |
| Item 14 (D-87) | causal `after` weakened to I for 5,340 tool executions in 2,135 executions | 8,925 tool executions in 2,799 executions |
| Item 17 (D-207) | `ext.agentdojo.system_prompt_variant` added to 24,707 v0.k11 AERs (§5 split); 0 `system_prompt_unrecognised`; no PROV statement added | 18,034 AERs |
| Item 5 (D-370) | one `agentdojo:load_environment` activity per execution with payload fixtures: 33,119 (51,714 fixture inputs); D for shared logs, twin I elsewhere; AER records 1,153,595 → 1,186,714 if nothing else moves | 16,210 (25,440); 553,182 → 569,392 |
| U6-c (D-373) | `unk /params = not_recorded` on every model call; one `apv:Gap` per model call; none on the 207 outcome-only logs | same |
| Items 4, 6, 8 in `suites@2` (D-377, D-371, D-379) | `success_without_visible_payload` 11 in the whole corpus (banking `user_task_15`, `important_instructions`); `partial_payload` in ≈ 1.25 % of executions (50 / 4,000); 0 markers changed by `yaml_norm@2` | 9; ≈ 1.3 % (52 / 4,000); 0 |
| Item 1 / D-86 | outcome and marker annotations stay D (verified harness), only the catalogue digest moves | same |
| Item 10 | tier 4 gains ordering / C51 / C26 / cycle checks: all pass | same |
| Items 7, 15, 21-25, 28, 29, 32; D-460 | code or catalogue digests only; 0 lone surrogates to map; D-460 not triggered by a fresh import | same |
| Not on main (held branches; must **not** appear) | items 33-41, 43-56, 60-79, D-451, RD-1 (CD-10..16, 23), item 77 (`null_text_blocks`) | same |
| Not expected to move | unit and variant counts, judgement values, seal issue counts by code (I-h list; `retry_passes_inferred` 82, `outcome_imposed_by_runner` 105, `unexecuted_tool_call` 800; `local_parse_drop_possible` 1,854 from C-h, not in I-h's `seal_issues_by_code`), identity (models, defences, attacks) | (47, 106, 145, 0) |

## 7. Check map

| Check | Applies | How / note |
|---|---|---|
| L1-01 counts | yes | §2; per-directory §3; 0 exclusions; blob ids equal the pinned trees |
| L1-02 strict parse | yes | 0 failures of every class; paired surrogate escapes in 4 (head) / 6 (2024-06) objects |
| L1-03 encodings/escaping | yes | 0 U+2028/2029/0085, bidi, tag, C0/C1 (other than TAB/LF/CR), U+FFFD, mojibake; literal-escape residues by design (Python-repr tool outputs); wholly escaped tool arguments ≈ N2 |
| L1-04 duplicates | yes | 0 byte-identical files within a part; identical trajectories ≈ FA; cross-part 14,182 identical blobs; cross-corpus: `adprov-v1` converted-legacy is a derived conversion (not byte-identical), survey `zenodo-bundled-runs` and `agentdojo-inspect` are declared mirrors (P `[lineage]`), compared only if staged |
| L1-05 arm coverage | yes | §3 grid, missing/extra cells as listed; plus the raw-field recount (H-08..H-14) |
| L1-06 secrets/paths | yes | counts and pointers only; E2: 0 secret-shaped, 0 account paths in AER; raw hits, if any, are benchmark fixtures (fictional codes, IBANs, e-mails) |
| L1-07 timestamps | partly | only v1.k14 has `evaluation_timestamp` (11,765 head, 0 in 2024-06); naive (no zone) in 100 %; no per-message time, so no within-unit monotonicity |
| L1-08 degenerate | yes | 207 empty-message logs with outcomes; 0 empty files; incomplete 1 / 4; run errors 105 / 106; null-final 82 / 47 |
| L2 selection/import | yes | strata dir × attack × suite; `l2_import.py` with the CLI tree class (git pin) |
| L2 validate / recompute --dry-run / determinism | yes | all tiers pass; recompute 0 differences on the scratch corpus; second import with another `--jobs` byte-identical (**first determinism evidence for head**: I-h `second_import = not_run`; 2024-06 shown in phase 6) |
| L2 verify --level chain | yes | on a sealed scratch copy (no withheld object) |
| L2 A2 error classes, A3 PI-nn | yes | 0 degenerate, 0 `adapter_defect`; no dangling or invented relations; I statements only in inference bundles |
| L2 evidence classes | yes | 2024-06 sample all D except the c6 twins; head D/I split by shared vs head-only (H-15) |
| L2 identity | yes | 22 models (head) / 13 (2024-06) per U6; defences none / repeat_user_prompt / spotlighting_with_delimiting / tool_filter / transformers_pi_detector; 0 `identity_unresolved`, 0 `pipeline_name_mismatch` (local dirs are table rows) |
| L2 redaction | reduced | no redact table; 0 account paths in AER/SEM/PROV |
| L2 withholding | **no** | no `[withhold]` table and no real credential expected; L1-06 stands in |
| L2 outcome sanity | pooled only | §4 |

## 8. Hypotheses (falsifiable)

| Id | Expectation | Falsified if |
|---|---|---|
| H-01 | Staged snapshots equal the pins (§2 files, bytes, tree ids) and the census counts (§5) | any difference |
| H-02 | Directory grid exactly as §3 (29 head dirs, 18 2024-06 dirs, derived counts) | any directory count differs by ≥ 1 |
| H-03 | `meta-llama_Llama-3.3-70B-Instruct-repeat_user_prompt` has 2,828 logs: `none` 132 complete, attacked 2,696 of 2,847 | count ≠ 2,828, or any missing cell under `none` |
| H-04 | `claude-3-sonnet-20240229-repeat_user_prompt` (40) and Mixtral (7) hold `none`-attack logs only; the 40 are workspace benign user tasks | any attacked log, or the 40 span another suite |
| H-05 | Workspace `injection_task_6`..`13` occur only in the six v1.2 dirs (claude-3-7, gemini-2.0-flash-001, four local); `gemini-2.0-flash-exp` has the 27-task shape though its era label is v1.2->v1.2.1 (L-07) | any v1.2 task id in another dir, or flash-exp with 35 injection tasks |
| H-06 | Of the 4,059 2024-06-only blobs, ≥ 95 % are travel-suite, Llama-3-70b or Mixtral logs (July 2024 re-runs, L-09) | < 95 % |
| H-07 | Every `transformers_pi_detector` log was introduced on or before 2024-07-17 (code before the #117 bug) | any later introducing commit |
| H-08 | Raw-field recount at head reproduces all 28 W rows (k/97 utility; k/629 UA and ASR on the v1.1.2 task ids) | any row differs by ≥ 1 cell |
| H-09 | Paper benign utility = Σ (benign success × suite injection-task count) / 629: reproduces P3 Table 3/5 at head and P1 at 2024-06 within 0.1 pp for ≥ 80 % of rows | < 80 % |
| H-10 | Paper UA (k/629) reproduces exactly: P1 vs 2024-06 and P3 vs head, all 10 models and 5 defence arms (the GPT-4o row: 50.08) | any row differs by ≥ 1 cell (except the documented T3/T5 conflicts) |
| H-11 | Where W and P3 ASR disagree (Command-R+, Gemini-1.5-pro-001, GPT-3.5, Llama-3-70b), the raw recount equals W, and the excess over P3 (22, 19, 12, 35 cells) equals that dir's `important_instructions` logs with a run error | raw ≠ W, or the excess differs from the run-error count by > 2 cells |
| H-12 | GPT-4o head `important_instructions` ASR = 300 / 629 (47.69 %), not 57.69 % (L-03); 2024-06 = 334 / 629 (53.10 %) | either count differs by ≥ 1 |
| H-13 | 2024-06 gpt-4o-repeat benign utility (paper weighting) ≠ 73.13 by > 2 pp (v1 copy error, L-04) | within 2 pp of 73.13 |
| H-14 | The local dirs' `important_instructions` rates match one SA version (SA1 or SA2) within 1.0 pp on all three metrics for all four arms; Llama-3.3-repeat with n < 949 attacked logs | no version matches; record which one does |
| H-15 | An execution cites `_unverified` twins (beyond the c6 rules) iff its blob is head-only: 22,497 of 36,679 at head, 0 at 2024-06 | any execution violates the equivalence |
| H-16 | All run-error logs (105 / 106) have `utility = false`, `security = true`; every benign log has `security = true` (head 3,560 files; 14 of them run errors) | any exception |
| H-17 | v1.k14 timestamps: 11,765 present, 100 % parse, 0 with a zone, all between 2024-12-06 (Llama-3.3 release) and 2025-07-26 (commit `9272bf1e` + 1 day) | any absent, unparseable, zoned or out of range |
| H-18 | Empty assistant turns without calls (N4, 343 head executions): ≥ 50 % in the four local dirs (#220 server errors → empty answers) | < 50 % |
| H-19 | L2: §6 movements exactly; none of the held-branch changes; 0 `adapter_defect`, determinism byte-identical | any unexpected digest class, a held change present, or a byte difference |
| H-20 | Pooled L2 outcome rates (sample) within the README threshold of the pooled §4 expectation per part | gap beyond the threshold |

Never exclude data for zero attack successes (user rule): arms with ASR 0 (e.g. Command-R+ in P3, SecAlign near 0) are kept and
reported.

## 9. Discrepancy leads to test (from desk research; details in `research.json`)

L-01 W vs P3 ASR for four models (run-error scoring, H-11); L-02 benign-utility denominator (H-09); L-03 GPT-4o 47.69 vs 57.69 (H-12);
L-04 v1 repeat-prompt benign copy error (H-13); L-05 Llama-3.3-repeat 151 cells short (H-03); L-06 Meta SecAlign v1 vs v2 numbers
(H-14); L-07 era label of gemini-2.0-flash-exp (H-05); L-08 partial dirs Mixtral and claude-3-sonnet-repeat (H-04); L-09 2024-06 →
head changes confined to travel and Llama (H-06); L-10 single run per experiment (#62), identical trajectories; L-11 checker eras and
current checker defects (#181, #161, #168: reported, not re-scored); L-12 LocalLLM defects (#150, #202, #219, #220; H-18).
Licence note for the dossier: the 2024-06 pin has no LICENSE file (added 2024-06-10); include under MIT by later trees (the
Zenodo v0.1.8 record declares CC-BY-4.0, not MIT, although its zip post-dates the MIT LICENSE [fact-check: was "and Zenodo v0.1.8"])
(`documentation-mismatch` candidate for P's `basis`, S3).

## 10. Fact-check (adversarial, 2026-10-14)

Checked against the cited documents and metadata only (no raw data read, no payload downloaded). Sources: arXiv PDFs
2406.13352 v1/v2/v3 and 2507.02735 v1/v2/v3/v4 (text extraction of the tables); arXiv abstract pages; GitHub API
(`repos/ethz-spylab/agentdojo`: commits, trees, compare, tags, pulls #96/#97, issues); `https://agentdojo.spylab.ai/results/`;
`util_scripts/create_results_table.py` at the head pin; Zenodo API (concept 12528188, records 17458493, 12742856); our
`census-*.json`, `import-cli-*.json`, FA, E2.

**Confirmed.** Every P1 number (v1 Tables 2-5) and P3 number (v3 Tables 2-5; v2 identical) in §4, including the Table 3 / Table
4 / Table 5 GPT-4o conflict (47.69 vs 57.7 / 57.69; UA 50.08 vs 50.01), the v1 Table 5 69.07 and the v1 repeat-prompt 73.13 equal
to tool filter; the v1 Table 2 ablation order (baseline = `no_names`, + wrong user, + wrong model, + correct user = `no_model_name`,
+ correct model = `no_user_name`, both). All 28 W rows. SA1 Table 3 / Table 8 and SA2 Table III / Table IX values; v3 (Tables 5,
10) and v4 (Tables 4, 8) repeat SA2's numbers; SA v4 states n = 97 and 949. arXiv dates v1 2024-06-19, v2 2024-07-18, v3
2024-11-24 and the v3 comment (Llama bug, travel suite). Head pin = `main` HEAD (2026-06-02T09:59:58Z, #147, src only), runs
tree `472cbb2e…` = 36,679 blobs / 426,293,413 B; 2024-06 pin 2024-06-05T11:21:57Z, runs tree `1227480d…` = 18,241 blobs /
188,873,874 B, no LICENSE, `function-calling-pi` 0.1.0; tag `v0.1.35` = `a75aba76` with the same runs tree; 60 commits touch
`runs/` and the history listed in research.json; LICENSE added `bd533515` 2024-06-10, edited `9b6708b0` 2024-06-12, MIT text and
holders as quoted; PRs #96 / #97 by an SA author, merged 2025-07-26. Per-directory counts of §3 (29 / 18 dirs, attack dirs and
their sizes) match the GitHub tree listings exactly; 14,182 (path, blob) pairs are shared, the 4,059 2024-06-only blobs are 4,052
same-path replacements plus the 7 Mixtral paths. Zenodo: 36 versions, the duplicate deposits, sizes and md5 of 17458493 and
12742856. Issues #3, #62, #86, #95, #117, #119, #125, #138, #150, #154, #159, #161, #168, #181, #189, #202, #213, #219, #220 exist
with the stated subjects (#62: run once; #95: `security` true = attack succeeded, always true without attack); #117 is absent at
`c2748856` (the detector loop reads each message's own content); changelog 0.1.15 (workspace IT4/IT5) and 0.1.21 (task checks).
L-01 cell gaps (22, 19, 12, 35) and L-02 fractions (419/629, 434/629, 66/97, 67/97) recompute from the printed percentages. Our
census/import figures in §2 (files, units, variants, completeness at E2, status, AER records) match C-h, C-06, I-h, I-06.

**Corrected.** (1) Zenodo licence: the records declare CC-BY-4.0 for v0.1.7..v0.1.22 (21 records, incl. the v0.1.8 origin
12742856) and MIT only from 'v1.1.23' (2025-01-15) on, not MIT throughout (§1, §9; research.json `data_record`, `licence`).
(2) Commits after `9272bf1e`: GitHub compare reports 29 (none touching `runs/`), not 22. (3) Source of the 1,854
`local_parse_drop_possible` figure is C-h (and FA), not I-h. (4) SA table numbering per version and the v4 title.

**Observation from the upstream file listing (metadata, not a new expectation).** The 151 missing cells of
`meta-llama_Llama-3.3-70B-Instruct-repeat_user_prompt` are all under `important_instructions` (798 of 949; `direct` and
`ignore_previous` complete), i.e. exactly in the arm SA reports with n = 949 (bears on L-05, H-03, H-14; L1-05 must still
confirm it from the staged snapshot). The listing also shows the 40 `claude-3-sonnet-…-repeat_user_prompt` logs under workspace
`none` and the 7 Mixtral logs as `none` user-task logs spread over all four suites, consistent with H-04.

**Unverifiable here.** Whether the live results page was built from the head tree (its numbers match, its build commit is not
shown); the paper's benign-utility weighting and run-error handling (inferred, H-09/H-11); which SA version the logs back
(H-14); all E2-derived quirk counts in §5-§6 other than those cross-read above.
