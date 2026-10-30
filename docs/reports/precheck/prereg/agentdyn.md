# Pre-registration: `agentdyn` (parts a, b, c)

| | |
|---|---|
| Corpus | `agentdyn` (source `agentdyn`, family `agentdojo`, profile `agentdyn` version 2) |
| Parts | `a` (`v1.k14` + `v1.k14.incomplete`, 38,281), `b` (`v0.k11`, Progent, 5,184), `c` (`drift.k18.messages`, 4,258); all from the one pin `5353cf7615b135cace8d07c8f12dac53a16b6db3`, `runs/` tree `90d6d50d…` |
| Wave / mode | wave 1. Part `a` was examined in E2 (`../../analysis/phase10-examination-2.md`): **delta checks** for `a`. Parts `b` and `c` were never imported into a stored corpus: **full checks** |
| Code | `065b0d36` or later on `precheck-corpora` (the examiner records the exact commit) |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Nothing in this file was computed from the raw data in this step; every number comes from a cited earlier report, the profile, the registry or the paper |
| Desk research | [`../data/agentdyn/research.json`](../data/agentdyn/research.json) (sources, versions, issues, licence, all paper values with per-suite splits) |

Sources of the expectations: profile `src/agentprov/adapters/agentdojo/profiles/agentdyn.profile.toml` (P); identity table
`tables/agentdyn_pipeline_dirs.toml` (T, 76 rows); registry `adapters/registry/__init__.py` and `tools/readme_corpora.toml`
(REG); import report `docs/reports/agentdyn/import-cli-agentdyn.json` (IMP, 2026-10-11); E2; phase-10l census and trials
(`docs/reports/phase10l/census.md`, `trials.md`: 10L); investigation `AgentPROV/investigation/sources/agentdyn.md` (INV)
and `verify/agentdyn.md` (VER); `artefacts.toml` (ART); `regen-batch.md` (RB); paper arXiv:2602.03117v3 (PAP).

## 1. Desk research in brief

- **Pin is still HEAD.** `main` = `5353cf76` (2026-05-19), no push since; `runs/` tree sha checked through the GitHub API on
  2026-10-14 (76 entries). No tags, releases, Zenodo, Figshare or HF execution record. HF `agentdyn-dataset/agentdyn` holds
  task definitions only, without licence (unchanged since 2026-05-06).
- **Paper versions.** v1 2026-02-03, v2 2026-02-06 (tables identical to v1), v3 2026-05-07 (new title, 17 tables). v3 adds
  rows for four models with no logs (Claude-Sonnet-3.5, Claude-Sonnet-4.5, Qwen3-Coder, Kimi-K2.5) and Table 8 (other
  attacks). Of the rows present in both versions, only GPT-4o mini x DRIFT changed (v1 28.33/22.05/2.72, v3
  18.33/19.31/3.39). That change matches the 2026-04-19 integrated rerun (`a4eb0787`).
- **New since the 2026-10-07 investigation.** Issue #8 (2026-10-12, open): four github user tasks can never reach
  utility true, with 0 true outcomes across `runs/`. PR #9 is the unmerged fix. Issue #7 (2026-09-23, open): the released
  Gemini-2.5-Pro undefended logs give UA 47.43, the paper 56.95.
- **Harness bugs that touch the logs.** The OpenAI-compatible client of the January code drops `temperature=0.0` (#2/#4,
  fixed 2026-03-04 after the runs), while the Google client sends 0.0. The AgentDojo 0.1.35 LocalLLM (SecAlign arms)
  turns server errors into empty answers and drops some calls (agentdojo #219, #220, #202). The GitHub IT1 checker was
  replaced on 2026-05-02 without rescoring (#6). TraceLogger keeps only the last of up to 3 passes.
- **Licence.** Repository MIT, whose only copyright line is the AgentDojo authors' (c) 2024. There is no data licence
  (policy `include`, "MIT as declared; not legally settled"). The paper is under arXiv's non-exclusive licence.

## 2. Expected counts per part

| Measure | a | b | c | Source |
|---|---:|---:|---:|---|
| Files selected (= units = executions) | 38,281 | 5,184 | 4,258 | P pin + `variant_labels`; REG (a full import, b spec, c census); INV §3.1, VER §3 |
| of which variant | `v1.k14` 38,269, `.incomplete` 12 | `v0.k11` 5,184 | `drift.k18.messages` 4,258 | IMP; VER §3 |
| Other `runs/` files, `select.dialect_planned` | 9,442 | 42,539 (corrected; was 43,465) | 43,465 (corrected; was 43,539) | 47,723 minus own part (IMP for a) |
| `src/…/drift/runs/**`, `select.owned_elsewhere` (owner `drift`) | 949 | 949 | 949 | P exclude; IMP (only if the input root contains `src/`) |
| Bytes | 479,526,175 | 53,706,779 | 65,093,661 | INV §4.1 (A native 471,333,341 + CaMeL 8,192,834); sum 598,326,615 = P |
| Messages | 557,485 | 61,779 | 54,239 | INV §4.1 (a = 550,448 + 7,037); 10L for c |
| Tool calls / tool messages | 210,127 / 210,304 | 24,510 / 24,413 | 19,997 / 19,997 | INV §4.1 |
| Tool errors | 15,061 | 6,589 | 2,285 | INV §4.1 |
| Runs without a tool call | 6,106 | 879 | 677 | INV §4.1 |
| Attacked / benign (incl. pre-pass) / `direct` | 32,800 / 5,190 / 291 | 4,480 / 704 / 0 | 3,838 / 420 / 0 | INV §4.5, P quirk `benign_security_constant` (a 5,190); 10L |
| Injection-task-as-user pre-pass files | 1,647 | 224 | 0 | P quirk; 8 x 28 for b; 10L |
| Records (AER, part a, E2 code) | 1,552,020 | n/a | n/a | IMP (moves with the regen items, section 8) |

Per-directory files (T, INV §4.2): nominal cell 648 = 60 benign + 28 pre-pass + 560 attacked (shopping 20x9, github 20x9,
dailylife 20x10). Exceptions: part a `gpt-5-mini-2025-08-07-tool_filter` 6, `gpt-5.1-2025-11-13` 939 (648 + 291 `direct`:
shopping 180, github 111), `gpt-4o-mini-2024-07-18-camel` 386 (dailylife attacked 0/200, dailylife benign 8/20, dailylife pre-pass 0/10, shopping attacked 140/180; benign and pre-pass detail corrected, INV §4.2),
14 travel strays (12 variant-A files in the `gpt-5-mini-2025-08-07-progent` directory, 2 in
`qwen_qwen-2.5-72b-instruct-progent`); part c: 620 per directory (no pre-pass), `gpt-5.1-2025-11-13-drift` 538 (github
attacked 98/180).

## 3. Expected arms

Arm key (stratum for L2) = **pipeline directory** (model x defence; T, class I, publisher-asserted label). Attack
(`important_instructions` / benign / pre-pass / `direct`) and suite are L1-05 facets, not strata. A finer stratum
(directory x suite x attack class, about 500 strata) would exceed the 300 cap at one unit per stratum. Strata: a 62 (the
61 variant-A directories of T plus `gpt-5-mini-2025-08-07-progent`, which holds 12 part-a travel strays beside its 648
part-b files), b 8, c 7. At about 5 units each the sample sizes are a 300 (307 drawn, reduced as README section 4
prescribes), b 40, c 35.

| Facet | a | b | c |
|---|---|---|---|
| Models | 8 base (gpt-4o-mini, gpt-4o, gpt-5-mini, gpt-5.1, gemini-2.5-pro, gemini-2.5-flash, llama-3.3-70b, qwen3-235b) + Meta-SecAlign-70B/8B + qwen-2.5-72b (strays) | the 8 base | the 8 base minus gpt-4o-mini (7) |
| Defences | none, repeat_user_prompt, spotlighting_with_delimiting, transformers_pi_detector, piguard_detector, prompt_guard_2_detector, tool_filter (x 8 models = 56 dirs); drift (integrated, gpt-4o-mini); camel (gpt-4o-mini); SecAlign (as model, defence none) | progent | drift (original code) |
| Provider (T, class I) | OpenAI for gpt-*, OpenRouter for llama/qwen and for gemini except the three gemini-2.5-flash detector arms (Google API); local for SecAlign | as a (no Google arm) | not recorded (DRIFT ids) |
| Suites | shopping, github, dailylife; travel 14 strays | 3 | 3 |

Expected **missing** cells against the paper design (PAP Tables 9-17): CaMeL for 7 of 8 models; gpt-5-mini x tool_filter
(6 aborted logs); camel dailylife attacked (200), shopping attacked (40), dailylife benign (12 of 20) and dailylife pre-pass (10) (corrected); gpt-5.1 x DRIFT github attacked (82); every
row of Claude-Sonnet-3.5, Claude-Sonnet-4.5, Qwen3-Coder and Kimi-K2.5; Table 8 attacks Ignore, Completion and Adaptive.
Expected **extra** cells: gpt-5.1 `direct` (291), the 14 travel strays, `qwen_qwen-2.5-72b-instruct-progent`, and the
injection-task-as-user pre-pass files (in no paper metric).

## 4. Expected outcome rates (paper) and the mapping

**Mapping.** `utility` and `security` are the logged booleans (`security = true` means the attacker goal was met;
constant `true` on benign runs). PAP metrics, verified on the tables:
- benign utility (BU) = the share of `user_task_*/none/none` files with `utility = true`, per suite (n = 20);
- utility under attack (UA) and ASR = the shares of `important_instructions` files with `utility = true` and
  `security = true`, per suite (n = 180/180/200);
- **overall = unweighted mean of the three suite rates.** Check: GPT-4o None UA is 55.52 by the mean and 55.36 pooled;
  the paper prints 55.52.

Pre-pass, `direct` and travel files are in no metric. Imposed outcomes (5 JSONDecodeError runs, all llama-3.3 none) count
as logged. Files without outcome keys (12) are excluded from the denominators and reported. Per-suite paper values for
every row are in `research.json` `reported_results`.

| Part | Directory | Files | Paper row (defence · model) | BU | UA | ASR | Note |
|---|---|---:|---|---:|---:|---:|---|
| a | `meta_secalign-70B` | 648 | Meta-SecAlign · Meta-SecAlign 70B | 55.00 | 53.35 | 8.98 |  |
| a | `meta_secalign-8B` | 648 | Meta-SecAlign · Meta-SecAlign 8B | 5.00 | 7.22 | 5.26 |  |
| a | `google_gemini-2.5-flash` | 648 | None · Gemini-2.5 Flash | 30.00 | 24.29 | 37.61 |  |
| a | `google_gemini-2.5-flash-piguard_detector` | 648 | PIGuard · Gemini-2.5 Flash | 8.33 | 1.83 | 2.00 |  |
| a | `google_gemini-2.5-flash-prompt_guard_2_detector` | 648 | PromptGuard2 · Gemini-2.5 Flash | 26.67 | 11.19 | 23.87 |  |
| a | `google_gemini-2.5-flash-repeat_user_prompt` | 648 | Prompt Sandwiching · Gemini-2.5 Flash | 16.67 | 14.33 | 18.22 |  |
| a | `google_gemini-2.5-flash-spotlighting_with_delimiting` | 648 | Spotlighting · Gemini-2.5 Flash | 13.33 | 12.50 | 17.74 |  |
| a | `google_gemini-2.5-flash-tool_filter` | 648 | Tool Filter · Gemini-2.5 Flash | 0.00 | 0.00 | 0.00 |  |
| a | `google_gemini-2.5-flash-transformers_pi_detector` | 648 | ProtectAI · Gemini-2.5 Flash | 1.67 | 0.19 | 1.04 |  |
| a | `google_gemini-2.5-pro` | 648 | None · Gemini-2.5 Pro | 51.67 | 56.95 | 20.61 |  |
| a | `google_gemini-2.5-pro-piguard_detector` | 648 | PIGuard · Gemini-2.5 Pro | 11.67 | 2.17 | 1.83 |  |
| a | `google_gemini-2.5-pro-prompt_guard_2_detector` | 648 | PromptGuard2 · Gemini-2.5 Pro | 58.33 | 17.18 | 14.50 |  |
| a | `google_gemini-2.5-pro-repeat_user_prompt` | 648 | Prompt Sandwiching · Gemini-2.5 Pro | 51.67 | 49.08 | 23.94 |  |
| a | `google_gemini-2.5-pro-spotlighting_with_delimiting` | 648 | Spotlighting · Gemini-2.5 Pro | 58.33 | 52.61 | 16.87 |  |
| a | `google_gemini-2.5-pro-tool_filter` | 648 | Tool Filter · Gemini-2.5 Pro | 1.67 | 0.93 | 0.00 |  |
| a | `google_gemini-2.5-pro-transformers_pi_detector` | 648 | ProtectAI · Gemini-2.5 Pro | 1.67 | 0.74 | 0.69 |  |
| a | `gpt-4o-2024-08-06` | 648 | None · GPT-4o | 53.33 | 55.52 | 37.80 |  |
| a | `gpt-4o-2024-08-06-piguard_detector` | 648 | PIGuard · GPT-4o | 10.00 | 1.46 | 1.67 |  |
| a | `gpt-4o-2024-08-06-prompt_guard_2_detector` | 648 | PromptGuard2 · GPT-4o | 60.00 | 20.80 | 27.15 |  |
| a | `gpt-4o-2024-08-06-repeat_user_prompt` | 648 | Prompt Sandwiching · GPT-4o | 63.33 | 56.13 | 31.17 |  |
| a | `gpt-4o-2024-08-06-spotlighting_with_delimiting` | 648 | Spotlighting · GPT-4o | 55.00 | 52.24 | 27.61 |  |
| a | `gpt-4o-2024-08-06-tool_filter` | 648 | Tool Filter · GPT-4o | 8.33 | 4.91 | 4.22 |  |
| a | `gpt-4o-2024-08-06-transformers_pi_detector` | 648 | ProtectAI · GPT-4o | 0.00 | 0.56 | 0.85 |  |
| a | `gpt-4o-mini-2024-07-18-camel` | 386 | CaMeL · GPT-4o mini | 0.00 | 0.00 | 0.00 | 386 files (dailylife attacked 0/200, dailylife benign 8/20, shopping attacked 140/180) |
| a | `gpt-4o-mini-2024-07-18-drift` | 648 | DRIFT · GPT-4o mini | 18.33 | 19.31 | 3.39 | integrated --defense drift rerun 2026-04-19; v3 row (v1 row differed) |
| a | `gpt-4o-mini-2024-07-18` | 648 | None · GPT-4o mini | 46.67 | 35.69 | 50.00 |  |
| a | `gpt-4o-mini-2024-07-18-piguard_detector` | 648 | PIGuard · GPT-4o mini | 16.67 | 3.26 | 1.33 |  |
| a | `gpt-4o-mini-2024-07-18-prompt_guard_2_detector` | 648 | PromptGuard2 · GPT-4o mini | 30.00 | 13.70 | 28.54 |  |
| a | `gpt-4o-mini-2024-07-18-repeat_user_prompt` | 648 | Prompt Sandwiching · GPT-4o mini | 43.33 | 37.78 | 33.80 |  |
| a | `gpt-4o-mini-2024-07-18-spotlighting_with_delimiting` | 648 | Spotlighting · GPT-4o mini | 38.33 | 35.78 | 47.33 |  |
| a | `gpt-4o-mini-2024-07-18-tool_filter` | 648 | Tool Filter · GPT-4o mini | 6.67 | 4.80 | 6.15 |  |
| a | `gpt-4o-mini-2024-07-18-transformers_pi_detector` | 648 | ProtectAI · GPT-4o mini | 1.67 | 0.93 | 1.37 |  |
| a | `gpt-5-mini-2025-08-07` | 648 | None · GPT-5-mini | 65.00 | 64.76 | 0.37 |  |
| a | `gpt-5-mini-2025-08-07-piguard_detector` | 648 | PIGuard · GPT-5-mini | 18.33 | 7.35 | 0.00 |  |
| a | `gpt-5-mini-2025-08-07-prompt_guard_2_detector` | 648 | PromptGuard2 · GPT-5-mini | 65.00 | 33.92 | 0.00 |  |
| a | `gpt-5-mini-2025-08-07-repeat_user_prompt` | 648 | Prompt Sandwiching · GPT-5-mini | 73.33 | 65.22 | 0.37 |  |
| a | `gpt-5-mini-2025-08-07-spotlighting_with_delimiting` | 648 | Spotlighting · GPT-5-mini | 68.33 | 61.13 | 0.56 |  |
| a | `gpt-5-mini-2025-08-07-tool_filter` | 6 | Tool Filter · GPT-5-mini | 0.00 | 0.00 | 0.00 | 6 aborted files, no outcome keys: paper zeros have no log support |
| a | `gpt-5-mini-2025-08-07-transformers_pi_detector` | 648 | ProtectAI · GPT-5-mini | 1.67 | 0.93 | 0.00 |  |
| a | `gpt-5.1-2025-11-13` | 648 | None · GPT-5.1 | 61.67 | 50.04 | 4.96 | +291 `direct` files (no paper column) |
| a | `gpt-5.1-2025-11-13-piguard_detector` | 648 | PIGuard · GPT-5.1 | 11.67 | 2.72 | 1.17 |  |
| a | `gpt-5.1-2025-11-13-prompt_guard_2_detector` | 648 | PromptGuard2 · GPT-5.1 | 55.00 | 22.26 | 3.71 |  |
| a | `gpt-5.1-2025-11-13-repeat_user_prompt` | 648 | Prompt Sandwiching · GPT-5.1 | 58.33 | 53.78 | 1.20 |  |
| a | `gpt-5.1-2025-11-13-spotlighting_with_delimiting` | 648 | Spotlighting · GPT-5.1 | 56.67 | 50.06 | 3.43 |  |
| a | `gpt-5.1-2025-11-13-tool_filter` | 648 | Tool Filter · GPT-5.1 | 1.67 | 3.67 | 0.00 |  |
| a | `gpt-5.1-2025-11-13-transformers_pi_detector` | 648 | ProtectAI · GPT-5.1 | 1.67 | 0.56 | 0.00 |  |
| a | `meta-llama_llama-3.3-70b-instruct` | 648 | None · Llama 3.3 70B | 10.00 | 6.15 | 11.91 |  |
| a | `meta-llama_llama-3.3-70b-instruct-piguard_detector` | 648 | PIGuard · Llama 3.3 70B | 3.33 | 0.00 | 0.67 |  |
| a | `meta-llama_llama-3.3-70b-instruct-prompt_guard_2_detector` | 648 | PromptGuard2 · Llama 3.3 70B | 8.33 | 6.44 | 11.07 |  |
| a | `meta-llama_llama-3.3-70b-instruct-repeat_user_prompt` | 648 | Prompt Sandwiching · Llama 3.3 70B | 5.00 | 7.35 | 9.96 |  |
| a | `meta-llama_llama-3.3-70b-instruct-spotlighting_with_delimiting` | 648 | Spotlighting · Llama 3.3 70B | 10.00 | 6.78 | 14.85 |  |
| a | `meta-llama_llama-3.3-70b-instruct-tool_filter` | 648 | Tool Filter · Llama 3.3 70B | 5.00 | 4.65 | 2.52 |  |
| a | `meta-llama_llama-3.3-70b-instruct-transformers_pi_detector` | 648 | ProtectAI · Llama 3.3 70B | 1.67 | 1.11 | 0.56 |  |
| a | `qwen_qwen-2.5-72b-instruct-progent` | 2 | Progent · - | n/a | n/a | n/a | 2 travel strays; no paper row |
| a | `qwen_qwen3-235b-a22b-2507` | 648 | None · Qwen3 235B-A22B | 23.33 | 10.74 | 22.67 |  |
| a | `qwen_qwen3-235b-a22b-2507-piguard_detector` | 648 | PIGuard · Qwen3 235B-A22B | 1.67 | 0.70 | 1.83 |  |
| a | `qwen_qwen3-235b-a22b-2507-prompt_guard_2_detector` | 648 | PromptGuard2 · Qwen3 235B-A22B | 15.00 | 10.50 | 22.00 |  |
| a | `qwen_qwen3-235b-a22b-2507-repeat_user_prompt` | 648 | Prompt Sandwiching · Qwen3 235B-A22B | 16.67 | 14.82 | 25.70 |  |
| a | `qwen_qwen3-235b-a22b-2507-spotlighting_with_delimiting` | 648 | Spotlighting · Qwen3 235B-A22B | 20.00 | 13.02 | 27.72 |  |
| a | `qwen_qwen3-235b-a22b-2507-tool_filter` | 648 | Tool Filter · Qwen3 235B-A22B | 0.00 | 0.33 | 0.33 |  |
| a | `qwen_qwen3-235b-a22b-2507-transformers_pi_detector` | 648 | ProtectAI · Qwen3 235B-A22B | 0.00 | 0.74 | 1.07 |  |
| b | `google_gemini-2.5-flash-progent` | 648 | Progent · Gemini-2.5 Flash | 1.67 | 2.04 | 2.24 |  |
| b | `google_gemini-2.5-pro-progent` | 648 | Progent · Gemini-2.5 Pro | 25.00 | 16.06 | 1.59 |  |
| b | `gpt-4o-2024-08-06-progent` | 648 | Progent · GPT-4o | 6.67 | 5.83 | 1.69 |  |
| b | `gpt-4o-mini-2024-07-18-progent` | 648 | Progent · GPT-4o mini | 6.67 | 3.83 | 10.33 |  |
| b | `gpt-5-mini-2025-08-07-progent` | 648 | Progent · GPT-5-mini | 23.33 | 17.63 | 0.00 | +12 variant-A travel strays (part a) |
| b | `gpt-5.1-2025-11-13-progent` | 648 | Progent · GPT-5.1 | 15.00 | 14.98 | 1.22 |  |
| b | `meta-llama_llama-3.3-70b-instruct-progent` | 648 | Progent · Llama 3.3 70B | 3.33 | 2.28 | 0.52 |  |
| b | `qwen_qwen3-235b-a22b-2507-progent` | 648 | Progent · Qwen3 235B-A22B | 8.33 | 2.19 | 13.59 |  |
| c | `google_gemini-2.5-flash-drift` | 620 | DRIFT · Gemini-2.5 Flash | 18.33 | 12.41 | 2.82 | no injection-task-as-user pre-pass files |
| c | `google_gemini-2.5-pro-drift` | 620 | DRIFT · Gemini-2.5 Pro | 36.67 | 33.04 | 1.09 | no injection-task-as-user pre-pass files |
| c | `gpt-4o-2024-08-06-drift` | 620 | DRIFT · GPT-4o | 30.00 | 27.09 | 0.83 | no injection-task-as-user pre-pass files |
| c | `gpt-5-mini-2025-08-07-drift` | 620 | DRIFT · GPT-5-mini | 10.00 | 17.17 | 0.00 | no injection-task-as-user pre-pass files |
| c | `gpt-5.1-2025-11-13-drift` | 538 | DRIFT · GPT-5.1 | 1.67 | 6.12 | 0.00 | github attacked 98/180; paper github UA 12.24 = 12/98 |
| c | `meta-llama_llama-3.3-70b-instruct-drift` | 620 | DRIFT · Llama 3.3 70B | 11.67 | 8.96 | 5.89 | no injection-task-as-user pre-pass files |
| c | `qwen_qwen3-235b-a22b-2507-drift` | 620 | DRIFT · Qwen3 235B-A22B | 36.67 | 33.19 | 9.07 | no injection-task-as-user pre-pass files |

Rows from v3 Tables 9-17 (https://arxiv.org/html/2602.03117v3#A7.T9). Table 3 repeats the overall values. Two paper
values are already known to differ from the released logs: Gemini-2.5 Pro None (issue #7: logs 53.33/47.43/21.43) and,
in v1 only, GPT-4o mini DRIFT (section 1).

**Comparisons.**
- **L2** (README section 4): per-directory sample rates with Wilson 95% intervals. With about 5 units per arm, no arm
  reaches n = 20, so no verdict is drawn per arm.
- **L1-05b (proposed addition; open question 2):** a whole-population recount of the raw outcome fields per arm under the
  mapping above. This is the comparison with power (H-04 to H-11).

## 5. Known quirks (do not report as new)

| Id / source | What | Expected count (part) |
|---|---|---|
| ART `agentdojo.art.benign_security_constant` | benign `security = true` | a 5,176 with origin rule (5,190 files), b 704, c 420 (10L) |
| ART `agentdojo.art.run_error_imposed` | JSONDecodeError → utility false, security true | a 5 (llama-3.3) |
| ART `agentdojo.art.injection_task_as_user` | pre-pass files | a 1,647 |
| ART `agentdojo.art.silent_rerun` | null-final logs, last pass only | a 826 |
| ART `agentdojo.art.incomplete_run` | outcome keys absent (not null) | a 12 (6 gpt-5-mini tool_filter, 3 CaMeL, 2 progent-travel, 1 gpt-4o repeat_user_prompt) |
| ART `agentdojo.art.max_iters_pending` | unexecuted trailing calls | a 1,683 logs / 1,800 calls |
| ART `agentdojo.art.provider_ids` | null call ids | a 15,306 calls in 3,062 logs (Google detector arms, SecAlign, CaMeL) |
| ART `agentdojo.art.context_taint_used` / P `pi_detector_redaction` | detector sentinel replaces the output | a 29,317 tool messages |
| ART `agentdojo.art.defence_benign_intervention` | benign runs with a redaction | a 938 (transformers PI 546, PIGuard 389, PromptGuard 2 3) |
| ART `agentdojo.art.text_tool_call`, `payload_not_reaching_agent`, `calls_derived_from_messages`, `validity_defects` | text-encoded calls; payload never in the agent's context; accounting unverifiable; vacuous utility | a 1,002; 18,368; 38,270; 2 |
| ART `agentdojo.art.local_parse_drop` | SecAlign tag/call mismatch | a 488 executions |
| ART `agentdojo.art.naive_timestamp` | naive local `evaluation_timestamp` | a 38,281 |
| ART `agentdyn.art.camel_feedback_as_user` / `camel_orphan_results` | CaMeL feedback as `user`; orphan results | a 266 logs, 1,674 messages; 1,977 results in 240 logs |
| ART `agentdyn.art.drift_user_decision` | integrated DRIFT `user` + `error` key | a 434 messages |
| ART `agentdyn.art.progent_directory_strays` | `pipeline_name_mismatch` | a 12 |
| ART `agentdyn.art.nondeterministic_tools` | OTPs, order ids and clock in tools | a, c (no count) |
| P quirks, part c (RT-2) | isolation 18,140 decisions / 19,997 tool messages; reserialised 23,995 / raw 2,197; CALL ERROR 3,792 in 1,663 files; calls in text not executed 2,004; 0 system, 0 `injections`; plan fields `final_plan_state` 4,258 | c |
| P other quirks | args mutated 32,273 files; tool filter 4,542 logs; repeat prompt 5,184; spotlighting 5,184; SecAlign tags 1,465 / 179 turns; placeholder args 210,127; Progent denials 0 in a | a |
| INV/VER | 390 groups of distinct runs with identical `messages` (> 3 messages); 16 logs not ending in an assistant message; 3,626 a-files whose directory ≠ `pipeline_name`, plus all of b and c | a, b, c |
| E2 N2-N5, N8, S01 | escaped newlines 25 executions; empty final replies 4,631 executions (738 entirely empty); dropped high byte 12 strings; argument type errors; gemini-2.5-flash generation-condition split (425/357/275 identical cells between detector pairs, 0/648 vs undefended) | a |
| DECISIONS D-27 c1, D-279, D-376, D-372 | datasheet flag for the gemini-2.5-flash baseline; zero-success arms stay in (gpt-5-mini-drift, gpt-5.1-drift); CaMeL attribution; completeness rule | a, c |
| 10L RT-10 | private-key headers in 4 part-c files; no `[withhold]` table in the profile | c |

## 6. Check map

| Check | a | b | c | Why / expected |
|---|---|---|---|---|
| L1-01 counts | delta | yes | yes | section 2; any difference from 38,281 / 5,184 / 4,258 / 949 is a finding |
| L1-02 strict parse | delta | yes | yes | expect 0 failures. E2 and 10L parsed every file; 1 raw object in a has paired surrogate escapes (valid) |
| L1-03 encodings | delta | yes | yes | expect a: C0/C1 in 12 strings (3 CR), 5 variation selectors, 0 bidi/tag/zero-width/U+2028/U+FFFD/mojibake (E2 U03-U05, measured on AER strings); b, c: no prior count |
| L1-04 duplicates | delta | yes | yes | 0 byte-identical files within the pin (VER §7); about 390 identical-message groups; S01 pairs (H-12); 0 byte overlap with every other corpus of the population (VER §7: AgentDojo, ROPE, adprov, Inspect mirror; 10L: c vs DRIFT head 0) |
| L1-05 arm coverage | delta | yes | yes | section 3 grid, missing and extra cells as listed; L1-05b outcome recount (proposed) |
| L1-06 secrets, account paths | delta | yes | yes | counts and pointers only. a: 376 secret-shaped, 2,956 absolute-path-like strings, all benchmark content (E2 U14); c: 4 files with private-key headers (10L); b: unknown; 0 publisher account paths expected |
| L1-07 timestamps | delta | presence only | presence only | a: 38,281 present, naive, 2026-01-21 00:15:59 to 2026-04-19 18:23:02; by day 01-21 2,179, 01-22 7,927, 01-23 6,414, 01-24 17,247, 01-25 3,204, 01-26 648, 04-09 14, 04-19 648 (VER §9). b, c: 0 timestamp fields; c has run-time stamps in tool outputs (1,531 runs, 2026-01-25 20:40 to 01-28 01:35), which are content |
| L1-08 degenerate | delta | yes | yes | a: 12 without outcome keys, 6 [system, user]-only, 16 not ending in assistant, 5 run errors, 826 null-final; b: 879 without a tool call; c: 564 [user, assistant]-only (gpt-5.1 359, gemini-flash 119, gpt-4o 52, gemini-pro 22, gpt-5-mini 8, llama 4), 677 without a tool call; 0 empty files |
| L2 import, validate (all tiers), recompute `--dry-run` | yes | conditional | yes | b is `planned`: the CLI gate refuses it. Run only via `l2_import.py` and label the result a trial. c has never been through the product path (10L ran mapper-level trials only) |
| L2 determinism (second import, other `--jobs`) | yes | conditional | yes | new evidence for a (E2/IMP: `second_import = not_run`) |
| L2 A2 error classes, A3 PROV issue classes | yes | conditional | yes | expect 0 degenerate and 0 `adapter_defect` (IMP a; 10L c 4,258/4,258 valid) |
| L2 evidence classes | yes | conditional | yes | no `verified_code`: every D rule cited through its `_unverified` twin (I); R07b: 0 D citations on unverified code |
| L2 identity | yes | conditional | yes | 76-row table; 0 `identity_unresolved`; a `pipeline_name_mismatch` 12; b 0 (table rows carry the bare model); c by table rows |
| L2 redaction | yes | conditional | yes | no account path in AER/SEM/PROV (no `redact` table declared) |
| L2 withholding / `verify --level chain` sealed | n/a | n/a | n/a | no `[withhold]` table (RT-10 open). The chain check runs, the withholding check does not apply |
| L2 outcome sanity | report only | report only | report only | n < 20 per arm; see section 4 |

## 7. Hypotheses (falsifiable)

| Id | Expectation | Threshold (refuted if) | Level |
|---|---|---|---|
| H-01 | per-part and per-directory file counts as in sections 2 and 3 | any difference | L1-01/05 |
| H-02 | github user_task_5, 7 have 0 `utility = true` in a, b, c; user_task_8, 11 have 0 in a and c (issue #8) | any `true` (b: tasks 8 and 11 reported, no verdict) | L1-05b |
| H-03 | in github/user_task_2/important_instructions/injection_task_1 files with `security = true`, ≥ 50% hold no executed `git_delete_repo` call (pre-fix IT1 checker, issue #6) | < 50% | L1 (raw call names) |
| H-04 | macro recount reproduces ≥ 90% of the 222 comparable (directory, metric) paper values within 0.05 pp | < 90%; each value off by > 5 pp is a finding | L1-05b |
| H-05 | `google_gemini-2.5-pro` (none): UA(logs) − UA(paper) ≤ −5 pp (expected about −9.5); BU and ASR within 2 pp | gap < 5 pp, or BU/ASR off by > 2 pp | L1-05b |
| H-06 | `google_gemini-2.5-flash` (none): at least one of BU/UA/ASR off by ≥ 5 pp from 30.00/24.29/37.61 (same directory history as gemini-2.5-pro; corrected wording) | all three within 2 pp | L1-05b |
| H-07 | `google_gemini-2.5-pro-drift` (c) = paper 36.67/33.04/1.09 exactly | any > 0.05 pp | L1-05b |
| H-08 | `gpt-4o-mini-2024-07-18-drift` (a) = v3 18.33/19.31/3.39 (per suite BU 10/35/10, UA 12.22/32.22/13.50, ASR 1.11/0.56/8.50); BU ≠ v1 28.33 | > 0.05 pp from v3 | L1-05b |
| H-09 | `gpt-5.1-2025-11-13-drift` (c): 98 github attacked files, 12 with `utility = true` | other counts | L1-05b |
| H-10 | CaMeL: 0 `utility = true`, 0 attacked `security = true`, 3 files without outcome keys | any | L1-05b |
| H-11 | gpt-5-mini tool_filter: 6 files, each [system, user] only, no outcome keys | any difference | L1-08 |
| H-12 | identical-trajectory cells ≥ 40% for each pair of Google-client gemini-2.5-flash detector arms; ≤ 2% for every pair of arms that both use the OpenAI-compatible client, excluding cells where both runs end in an empty reply (temperature 0.0 sent vs dropped) | any Google pair < 40% or any OpenAI-compatible pair > 2% | L1-04 |
| H-13 | empty final reply without a tool call: SecAlign arms ≥ 2x the pooled OpenAI/OpenRouter rate of part a (LocalLLM #220) | < 2x | L1-08 |
| H-14 | 0 files of Claude, Kimi or Qwen3-Coder at the pin | any | L1-05 |
| H-15 | b: 5,184 of 5,184 without the auto-complete line (system sha256 `a021a92b…`), without `evaluation_timestamp` or `agentdojo_package_version`, with `pipeline_name` = bare model | any exception | L1-01/07 |
| H-16 | a timestamp range and day histogram as in section 6 | any difference | L1-07 |
| H-17 | c: private-key header strings in exactly 4 files; no publisher account path in a, b or c | other count; any account path | L1-06 |
| H-18 | benign files with outcomes: `security = true` in all (a 5,180 of 5,190; b 704; c 420) | any `false` | L1-05b |
| H-24 | gpt-5.1 `direct`: 291 files (shopping 180, github 111, dailylife 0) | other counts | L1-05 |

Rule: no directory is excluded or proposed for exclusion because no attack succeeded (gpt-5-mini-drift, gpt-5.1-drift, the
detector and tool-filter arms).

## 8. Expected movement since E2 (part a; code `afe7038` → `065b0d36`)

The stored corpus `agentdyn-a-p10.partial` does not move (no regeneration yet). The L2 scratch imports run the current
code, so their AER/SEM/PROV must differ from the stored corpus exactly as follows (RB), and in no other way:

| Item (RB) | Expected in the L2 sample of part a |
|---|---|
| 30 (D-31) | header: profile `agentdyn` version 2, rules `aer` 1, `agentdojo` 2, `agentdyn` 2, `drift` 1; SEM profile `agentdojo.suites@3` (stored: @1) |
| 3, 13 (D-80/81, D-84) | every D rule cited through its `_unverified` twin (class I); records weakened to their rule's class |
| 9, 11 (D-372) | completeness: `known_incomplete` only where `incomplete_run` (12 of 38,281); the 825 retry-only executions become `unverifiable`. Full-population expectation: `unverifiable` 38,269, `known_incomplete` 12 (stored: 37,444 / 837) |
| 2 (D-376) | CaMeL: feedback messages authored by `def<camel>` (I); 0 `unattributed_additional_user_message` (stored 266); planner calls `unk /input not_recorded` (2,342 corpus-wide) |
| 5 (D-370) | activity `ac0` `agentdojo:load_environment` (class I twin) in executions with payload fixtures: 33,091 of 38,281 (86.4%) |
| U6-c (D-373) | every `model_call` has `unk /params not_recorded` |
| 27 (b), 30 (suites@3) | reviewed tool labels for shopping/github/dailylife. `agentdojo.unknown_tool@1` remains only for tool names absent from the suite tables (hallucinated tools). Expect < 25% of sampled executions with any such annotation (E2: 84.3%, 32,262 of 38,281) |
| 1 (D-86, `@2/@3`) | outcome and marker annotations cite twins (ev I) |
| 6 (D-371) | `agentdojo.partial_payload`: rare (38 of a 4,000 sample, 37 in `gpt-4o-mini-2024-07-18-drift`); 0-3 in the sample |
| 4 (D-377) | `agentdojo.success_without_visible_payload`: about 0 (0 in a 4,000 sample) |
| 8 (D-379) | `yaml_norm@2`: 0 marker changes (46,586 markers sampled) |
| 7 (D-378), 14 (D-87), 24 | 0 affected executions (AgentDyn) |
| 10 | validation gains the ordering, C51, C26 and cycle checks: all pass |
| 15, 22, 23, 26 | catalogue, profile and code digests only; no other AER field (re-map checked on 600 stored executions, RB item 22) |
| unchanged | seal-issue rates from raw: `unexecuted_tool_call` 4.4%, `retry_passes_inferred` 2.2%, `local_parse_drop_possible` 1.3%, `orphan_tool_result` 0.6%, `incomplete_run`/`pipeline_name_mismatch` 0.03% each, `outcome_imposed_by_runner` 0.01% (IMP) |

Any other difference between an L2 AER of part a and a fresh re-map of the same raw object by the stored corpus's
recorded versions is a finding.

Parts b and c have no E2 baseline. The c baseline is the 10L mapper trial: 4,258 of 4,258 valid; decisions 21,932
(18,140 isolation + 3,792 CALL ERROR); messages 54,239; tool executions 19,997; model calls 26,192; seal issues
`accounting_unverifiable` and `drift.agent_prompt_not_recorded` on every file, `drift.injection_map_not_recorded` on 3,838,
`drift.calls_in_text_not_executed` on 2,004. The AER-set digest `4579512d…` is not expected to reproduce, because U6-c
and the profile bumps came later.

## 9. Not in scope

The `history` part (16,175 executions, incl. Claude Haiku/Sonnet 4.5 and the Google-API Gemini base runs that probably
underlie the paper's Gemini None rows), part `d` (owned by `drift`), EnvironmentOptim's copies of part c, and any re-run
of the benchmark (non-deterministic tools; issue #8 fix not merged).

## 10. Fact-check (2026-10-14, adversarial, before any data check)

Checked against the sources, using metadata only (GitHub API trees, commits and issues, arXiv HTML, HF and Zenodo APIs).
No payload was downloaded and no raw file content was read.

- **Paper values (sections 4 and 7).** All 225 BU/UA/ASR values in the section 4 table match the v3 appendix Tables 9-17
  (https://arxiv.org/html/2602.03117v3#A7.T9), with the right table, defence, model and metric. All 225 per-suite
  values in `research.json` also match. The v1 to v3 diff over all 246 v1 cells shows that only GPT-4o mini x DRIFT
  changed (v1 28.33/22.05/2.72), so the v3 values are the right reference. Other checks:
  - v1 and v2 tables are identical.
  - Table 8 values, the Table 3 swap (Qwen3 to Claude-Sonnet-3.5, Tool Filter moved to System) and the Kimi-K2.5 = Claude-Sonnet-4.5 Table 9 row are confirmed.
  - The derived values are confirmed: GPT-4o None UA 55.52 by mean and 55.36 pooled; gpt-5.1 drift github 12/98 = 12.24.
  - Versions, titles, page and table counts and the arXiv licence are confirmed (https://arxiv.org/abs/2602.03117v3).
- **Pin and record.** Confirmed:
  - `5353cf76` is HEAD; `pushed_at` is 2026-05-19; 26 commits; 0 tags and 0 releases.
  - The `runs/` tree is `90d6d50d…` with 76 entries. Summed per subtree, it holds 47,723 blobs and 598,326,615 bytes, equal to the profile.
  - Directory counts (648, 620, 538, 939, 386, 6, 660, 2) are confirmed. Bytes per part are confirmed: c 65,093,661 = sum of the 7 c directories; b 53,706,779 = progent directories minus the 12 travel strays (131,166 B); a follows.
  - From the tree listing: gpt-5.1 `direct` is shopping 180 and github 111. Pre-pass paths in part a: 1,647.
  - The HF dataset (sha `f599709d…`, 10 parquet configs, no licence) and the single unrelated Zenodo hit are confirmed.
- **Corrected.**
  1. `select.dialect_planned`: b is 42,539 (was 43,465) and c is 43,465 (was 43,539). Both are 47,723 minus the part's own files.
  2. CaMeL coverage. The directory also lacks dailylife benign `user_task_8..19` (only 8 of 20 present) and all 10 dailylife pre-pass files, as INV §4.2 already says. The missing-cell list and the notes are amended. The paper's CaMeL dailylife BU therefore has at most 8 logged files behind it.
  3. Commit history of the Gemini base runs:
     - The OpenRouter directories `google_gemini-2.5-pro` and `google_gemini-2.5-flash` were added in `73ee3416` (2026-02-03 19:22 UTC, after v1, before v2). Their trees have been unchanged since then.
     - `2d4ad05a` (2026-02-14) only removed the Google-API directories `gemini-2.5-pro` and `gemini-2.5-flash` (plus two pro detector directories) and `runs/DRIFT`.
     - "Replaced in 2d4ad05a" is therefore reworded (H-05/H-06 cause text, `research.json`). The thresholds are unchanged.
  4. The issue #5 maintainer's dailylife ASR for DRIFT-original gpt-4o-mini is 7.00 (was recorded as truncated).
  5. Vendored licences. `defenses/progent/agentdojo/LICENSE` exists (AgentDojo's MIT). Progent itself has no licence file in the repository (upstream sunblaze-ucb/progent is MIT). The DRIFT copy has none.
  6. Harness wording:
     - agentdojo #212 reports a crash and #177 corrupted results.
     - #209 concerns a local model only.
- **Confirmed (harness and issues).**
  - Issues #1-#9: states, dates and content as stated. #7's table gives `runs/` None 53.33/47.43/21.43 and DRIFT = paper. #8 gives 0 of 749/749/749/740. #6 was closed after the checker fix.
  - Temperature code: `openai_llm.py` l. 179/247 and `google_llm.py` l. 285 at `de473e58`; the fix is PR #4 (`bd3fc6bc`, 2026-03-04).
  - The LocalLLM random seed is in agentdojo v0.1.35 `local_llm.py` l. 63. agentdojo issues #202/#219/#220/#214 are open as described. v0.1.35 = `a75aba76` (2025-10-27).
  - DRIFT `1af2672c` (2026-02-04) and LICENSE `6fd3df47` (2026-07-16) are confirmed.
  - `a4eb0787` touched 648 files of `gpt-4o-mini-2024-07-18-drift`. The 2026-04-09 commits added the 12 + 2 travel strays.
  - The README states that the paper's results are the `runs/` logs and lists the Google-provider Gemini enums.
- **Unverifiable here (need the data step).** These are the counts sourced from INV/VER/IMP/10L that the tree cannot show: messages, tool calls, outcome keys, timestamps, secret counts and identical-trajectory groups. They were checked against the cited reports only, and they match (INV §4.1 rows: a = native + CaMeL).
  - Unverified: that part c is DRIFT-original output (maintainer statement only) and that the CaMeL logs date from 2026-01-22.
