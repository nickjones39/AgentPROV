# Pre-registration: `ast-survey-agentdojo`

| | |
|---|---|
| Corpus | `ast-survey-agentdojo` (Wave 1; E2 corpus, examined for the **delta since E2**) |
| Part | `agent-security-tools-survey` · `agentdojo-runs` (one part) |
| Family / profile | `agentdojo` / `survey-runs@2` (stored corpus: `survey-runs@1`, sha256 `db5cd1e7…`) |
| Pin | git `Forever-CodingNoob/agent-security-tools-survey@89c4db2c949797fbb38c5bfed85dc82780ddbfe3` (2026-08-28), tree `agentdojo/` |
| Code commit | `065b0d36` or later on `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **written before any pre-check data check of this corpus** (no raw or corpus data read; only our prior reports and public metadata) |
| Desk research | `../data/ast-survey-agentdojo/research.json` (all URLs there) |

Baselines: FA = `../../analysis/phase10-corpus-analysis.md`; E2 = `../../analysis/phase10-examination-2.md`; import =
`../../survey/import-cli-agentdojo-runs.json`; prior investigation = `AgentPROV/investigation/{sources,verify}/agent-security-tools-survey.md`
(2026-10-07, our own reports, outside this repo).

## 1. Sources (summary of desk research)

- **No paper.** The survey is a repository artefact; its "paper" is `agentdojo/README.md` (results section) and
  `report.md`. arXiv search by title and by the Zenodo creator (Jhih-Jhong Lin) finds nothing (2026-10-14); the Zenodo
  title names a study ("Evaluating Agentic LLM Security Benchmarks for Cybersecurity Education: A Reproducible Study")
  with no DOI or arXiv id. Benchmark paper: AgentDojo, arXiv 2406.13352 (v1 2024-06-19 … v3 2024-11-24).
- **Repository unchanged since the pin.** HEAD of `main` = `89c4db2c` (only branch; 0 tags, releases, issues, PRs;
  pushed 2026-08-28). Logs added in one commit, `26692cd6` (2026-08-23); later commits touch only `agentdojo/README.md`
  (`702423d6`, `7e451015`, `03bfda43` 08-23; `35f51954` 08-25; `b7cc0ac2` 08-26; `3c0f77ec` 08-27; `307f0532`, `69b91ef8`
  08-28) and the run scripts (`35f51954` only). The README result tables are byte-identical from `35f51954` to the pin
  (`3c0f77ec` only dropped a per-pair time table). [fact-check: commit list completed]
- **Zenodo**: concept `10.5281/zenodo.22135956`; v1.0.0 `22135957` (artifact.zip 243,606,319 B, md5 `2cdcea49…`) and
  v1.0.1 `22140262` (243,606,321 B, md5 `f623f7f7…`); exactly 2 versions, both as recorded in the profile pins.
- **Harness**: AgentDojo submodule `089ed468` (2026-06-02, still `main` HEAD upstream; 5 commits past tag v0.1.35 =
  `a75aba7`), benchmark `v1.2.2`, `openai-compatible` provider, plus 3 local patches not in git (timeout, Pydantic
  `model_rebuild`, `InternalServerError` → `utility=False, security=True`). Ollama 0.23.1 (claim in the top-level
  `README.md` l.59 and `docs/requirements.md`, not in `agentdojo/README.md`; release 2026-05-05) [fact-check: location]. Models: Ollama tags `qwen3:14b`, `qwen3-coder:30b`, `gpt-oss:120b` (no weight digest recorded).

## 2. Expected counts

| Quantity | Expected | Source |
|---|---:|---|
| Files in pinned tree `agentdojo/` / bytes | 3,256 / 43,565,675 (= 3,243 logs + 10 context artefacts + 3 neither: `README.md`, `extract_results.py`, `run_partial_benchmark.sh`) [fact-check: composition] | profile pin and comment l.38-39; import report (`verified` 3,253 blobs = 3,243 + 10) |
| Execution logs selected (`agentdojo/results/runs_*/openai-compatible/**/*.json`) | 3,243 (1,081 per model) | registry (`tools/readme_corpora.toml`), import report, verify §2.2 |
| Log bytes (min / max per file) | 38,581,746 (1,693 / 493,168) | verify §2.2 |
| Context artefacts (8 console logs, `timing_summary.csv`, `run_full_benchmark.sh`) | 10, never mapped | profile `context_artefacts`; import report |
| Register `not_imported` (6 AgentHarm `.eval` `select.owned_elsewhere`, 4 ASB CSV `select.dialect_planned`) | 10 (outside the `agentdojo/` tree: `agentharm/`, `asb/`) | import report; profile `exclude` |
| Units / executions / variant | 3,243 `agent_execution` / 3,243 / `v1.k14` 3,243 | import report |
| Per model × suite (workspace / travel / banking / slack) | 614 / 167 / 169 / 131 | sources §4.2 |
| Messages system / user / assistant / tool; tool calls | 3,243 / 3,243 / 13,599 / 11,237; 11,286 | import cross-checks |
| Logs with non-empty `injections` / payload fixtures | 2,847 / 4,401 | verify §2.3; regen-batch item 5 census |
| Run errors (`error` non-null; all `gpt-oss:120b`) | 11 (10 attacked + 1 solvability `workspace/injection_task_13`) | profile quirk note; import |
| Iteration-capped logs / unexecuted calls | 48 / 49 (qwen3:14b 8, qwen3-coder 26, gpt-oss 14) | profile; verify §2.3 |
| Benign `security` constant (files / applied) | 396 / 395 | profile census |
| `args_mutated_in_place` files; placeholder args (all null) | 2,901; 11,286 | profile census |
| Logs ending in null content (hidden re-run detectable) | 0 | profile |
| Sum of `duration` | 65.09 h | sources §4.2 |
| Paper (README) design per model | 97 benign + 949 attack pairs (+35 solvability not reported) | README Phase 1/2 tables |

## 3. Expected arms

Facets: model (3) × suite (4) × kind {benign `user_task_N/none/none`, solvability `injection_task_N/none/none`,
attack `user_task_N/important_instructions/injection_task_M`}. Defence: none (pipeline `openai-compatible`, constant).
Attack: `important_instructions` only.

| Suite | user tasks | injection tasks | attack pairs | benign | solvability | per model |
|---|---:|---:|---:|---:|---:|---:|
| workspace | 40 | 14 | 560 | 40 | 14 | 614 |
| travel | 20 | 7 | 140 | 20 | 7 | 167 |
| banking | 16 | 9 | 144 | 16 | 9 | 169 |
| slack | 21 | 5 | 105 | 21 | 5 | 131 |
| total | 97 | 35 | 949 | 97 | 35 | 1,081 |

- Expected missing cells: **0** (full cross product present for all 3 models).
- Expected extra cells vs the README: the 105 solvability runs (AgentDojo's injection-task-as-user-task pass; not
  reported by the README). The README's "partial benchmark" (105 pairs/model) is a subset of the 949, not extra files.
- L2 strata: the 36 (model × suite × kind) cells; 5 per stratum → **180** units (within 30–300).

## 4. Expected outcome rates (L2 comparison targets)

Metric mapping: README "Utility" = mean of the log's `utility` (AER checker judgement `utility`); README "Security" =
mean of `security` over the 949 attack pairs = **targeted attack success rate** (`security=True` means the injection
task succeeded; the README's "resisted" gloss is wrong, profile quirk `semantic_trap_security_gloss`). In SEM this is the
`attack_succeeded` outcome; benign/solvability `security` is the harness constant and is excluded. The README figures
include the 10 attacked run errors whose `security=True` is imposed by patch (c).

Integer counts are the unique integers consistent with the README's one-decimal percentages and suite sizes (they sum
to the combined row in every case).

**Benign utility (README "Phase 1" table; n = 40/20/16/21/97 per model):**

| Model | workspace | travel | banking | slack | combined |
|---|---|---|---|---|---|
| qwen3:14b | 60.0 % (24) | 70.0 % (14) | 68.8 % (11) | 85.7 % (18) | 69.1 % (67) |
| qwen3-coder:30b | 47.5 % (19) | 60.0 % (12) | 56.2 % (9) | 76.2 % (16) | 57.7 % (56) |
| gpt-oss:120b | 77.5 % (31) | 35.0 % (7) | 68.8 % (11) | 76.2 % (16) | 67.0 % (65) |

**Under attack (README "Full benchmark results (all 949 pairs)"; utility / ASR; n = 560/140/144/105/949):**

| Model | workspace | travel | banking | slack | combined |
|---|---|---|---|---|---|
| qwen3:14b | 55.7 (312) / 2.1 (12) | 44.3 (62) / 7.9 (11) | 44.4 (64) / 42.4 (61) | 60.0 (63) / 79.0 (83) | 52.8 (501) / 17.6 (167) |
| qwen3-coder:30b | 36.8 (206) / 5.5 (31) | 30.0 (42) / 30.0 (42) | 36.8 (53) / 38.9 (56) | 43.8 (46) / 75.2 (79) | 36.6 (347) / 21.9 (208) |
| gpt-oss:120b | 59.3 (332) / 10.9 (61) | 24.3 (34) / 35.0 (49) | 70.8 (102) / 61.1 (88) | 50.5 (53) / 55.2 (58) | 54.9 (521) / 27.0 (256) |

**Solvability utility (not in the README; our investigation, reproduced by `source_checks`; n = 35):** qwen3:14b 62.9 %
(22), qwen3-coder:30b 60.0 % (21), gpt-oss:120b 68.6 % (24). Consistency: utility True 1,624 and security True 1,027 of
3,243 (verify §2.4, `timing_summary.csv`) = 188 + 1,369 + 67 and 396 + 631.

L2 rule: with 5 units per stratum, no single cell reaches n = 20. The verdict-bearing comparison is per model × kind
(n = 20, i.e. 4 suites × 5), using the **stratum-weighted** estimate (weights = population stratum sizes above) against the
combined row; per-suite cells are reported with Wilson 95 % intervals only. Threshold as README §4.

## 5. Known quirks (expected-known; never findings)

| Id / source | Expected |
|---|---|
| `agentdojo.art.run_error_imposed` | 11 (gpt-oss) |
| `agentdojo.art.injection_task_as_user` | 105 |
| `agentdojo.art.benign_security_constant` | 395 |
| `agentdojo.art.max_iters_pending` | 48 logs / 49 calls |
| `agentdojo.art.validity_defects` (vacuous utility) | 4 |
| `agentdojo.art.calls_derived_from_messages` | 3,243 |
| `agentdojo.art.payload_not_reaching_agent` | 600 of 2,847 attacked |
| `survey.art.text_tool_call_unparsed` | 174 (173 end after one turn; qwen3-coder) |
| `agentdojo.art.naive_timestamp` | 3,243 |
| `agentdojo.art.silent_rerun` | scoped; 0 detectable (no null final content) |
| Profile quirks | `semantic_trap_security_gloss`, `package_version_not_code_identity` (0.1.35 in all, code = `089ed468` + 3 patches), `args_mutated_in_place` 2,901, placeholder args 11,286 |
| FA / E2 (not catalogued for survey) | identical-trajectory groups 32 / 299 executions (FA §8 row 7); empty assistant turns without a call 84 executions (E2 A03, N4); wholly escaped tool arguments 18 executions, qwen3:14b (E2 U06, N2); 1 zero-width char (FA §2); 12 variation-selector strings (E2 U05); 2 non-identifier tool names (E2 A01); 18 `unknown` role annotations = hallucinated tool names (FA §3.3); 122 raw objects with paired surrogate escapes, 0 lone (E2 U01) |
| Decisions | D-24/D-80 (I twins: `verified_code = []`), D-86 (SEM twins under `suites@2`), D-31/item 30 (v2 profile/catalogue), D-370, D-373; licence class `(CC-BY-4.0, [])` distinct from `ast-survey-agentharm` |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2; selected 3,243, context 10, not selected 10 with profile codes |
| L1-02 strict parse | yes | expect 0 failures; 122 objects with valid surrogate pairs; 0 lone surrogates, BOM, NaN, dup keys |
| L1-03 encodings | yes | expect 0 U+2028/2029/0085, C0/C1, bidi, tag, U+FFFD, mojibake; 1 zero-width; literal `\n` and repr residues in tool outputs by design (2,385 of 10,431 non-error tool outputs are dict reprs, verify §2.3) |
| L1-04 duplicates | yes | 0 byte-identical files; 32 identical-trajectory groups / 299 files; 0 cross-corpus repeats (models absent from every other corpus; the Zenodo mirror of AgentDojo `runs/` is not in this part) |
| L1-05 arm coverage | yes | §3: 36 cells, 0 missing, 0 extra vs design; solvability extra vs README |
| L1-06 secrets / account paths | yes | expect 0 account paths and 0 secret-shaped values in the 3,243 logs (E2 U14 survey 0/0 at AER level); host names live only in context artefacts |
| L1-07 timestamps | yes | `/evaluation_timestamp` 3,243/3,243, naive `YYYY-MM-DD HH:MM:SS`, no zone, range 2026-08-17 20:02:34 … 2026-08-21 11:16:58; one timestamp per unit, so in-unit monotonicity is n/a; per model no start/duration overlap |
| L1-08 degenerate | yes | 0 empty / zero-message files; 11 error-ended; 48 capped; 84 empty final answers |
| L2 import, validate, recompute, determinism | yes | 180 units; expect 0 failed, 0 degenerate, 0 `adapter_defect`; recompute dry-run 0 differences inside the scratch corpus; two `--jobs` byte-identical |
| L2 A2 error classes | yes | run errors (500 parse failures), iteration cap, text-encoded calls, empty completions |
| L2 A3 PROV issue classes | yes | expect 0 dangling, 0 invented relations; unexecuted calls → `apv:NotDispatched` pointing at the seal issue (item 24) |
| L2 evidence classes | yes | AER `evf` shares near FA (O .20 / D .32 / I .47 of 141,285) ±5 pp; no D citation on unverified code (all D structural rules via `_unverified` twins) |
| L2 identity | yes | 3 models from the results-dir slug (`survey.model_from_results_dir@1`, I); `identity_unresolved` 0; `pipeline_name` constant |
| L2 redaction | yes (check only) | no `redact` table in the profile; expect 0 account paths in AER/SEM/PROV |
| L2 withholding / `verify --level chain` on sealed copy | **no** | profile has no `[withhold]` policy and no archive members (git origin) |
| L2 outcome sanity | yes | §4 |

## 7. Hypotheses (falsifiable)

| # | Hypothesis | Pass / refute threshold | Check |
|---|---|---|---|
| H1 | Whole-population raw outcome counts equal every README-derived integer of §4 (39 cells) | pass: all equal; any cell ±1 or more → documentation-mismatch | L1 (raw fields) |
| H2 | The 11 run errors are all gpt-oss; 10 are attack pairs, 1 is `workspace/injection_task_13` solvability; ≥ 9 of the 10 attacked ones are in workspace `user_task_26`/`user_task_30` or travel `user_task_19` (README "Affected tasks") | refuted if < 9 | L1 |
| H3 | README calls the 500 error deterministic, yet those 3 user tasks have 35 gpt-oss attack pairs and only 10 attacked errors exist in total, so ≥ 25 of the 35 have no run error (implied by the counts; L1 gives the per-pair distribution) | if ≥ 25 lack an error, the README claim is not reflected in the data (documentation-mismatch, S3) | desk + L1 |
| H4 | (Desk context: `agentdojo/README.md` is self-contradictory here: its script table marks `run_partial_benchmark.sh` "(not used in the reported run)", while the Phase 1 text says the partial benchmark ran first and the full run reused cached results; both scripts write the same `../your-results/runs_<slug>` logdir, and patch (b) exists for loading cached results.) The 105 README "partial" pairs per model (workspace ut0/13/26, gpt-oss ut20 instead of 26; travel ut0/7/14; banking ut0/5/10; slack ut0/7/14) were reused from cache: their `evaluation_timestamp`s precede the model's other 844 attack logs | pass: ≥ 95 % earlier; refuted: < 50 %. If pass, the README partial table should reproduce exactly from those logs (check per cell) | L1-07 |
| H5 | The released run scripts are not the ones that produced the logs: `--force-rerun` was added on 2026-08-25 (`35f51954`), after the last log (2026-08-21) | desk-confirmed; L1 adds: Phase-1 logs of each model are not all later than its partial-run logs | desk + L1-07 |
| H6 | Text-encoded tool calls (`<function=` in assistant text, no structured call) are ≥ 99 % `qwen3-coder:30b` and total 174 ± 1 executions (Ollama qwen3-coder parser gap, ollama#18530) | refuted if another model holds > 1 % | L1 |
| H7 | Literal `\uXXXX` text in decoded strings occurs ≥ 90 % in role-tool content or its model copies (AgentDojo `tool_result_to_str` ASCII escaping, agentdojo#214) | refuted if < 90 % | L1-03 |
| H8 | Per-model sums of `duration` match the README "Execution Time" table (Phase 1 / Phase 2 hours) within 10 % per model | outside 10 % → documentation-mismatch (S3) | L1 |
| H9 | gpt-oss benign `travel/user_task_19` (README: aborted the utility run) has `error` null in the released log | refuted if non-null | L1 |
| H10 | Banking `injection_task_0/1/3` attack successes include runs whose transfer subject lacks the targeted data (agentdojo#181: subject check is dead code) | report count; expected > 0; classify `expected-known` if routed as `validity_defects` | L1 (raw args) |
| H11 | L2 sample: 0 failed, 0 degenerate, 0 `adapter_defect`, tier 4 strict pass 100 %, 2 imports byte-identical | any miss is a finding | L2 |
| H12 | Stratum-weighted sample rates per model × kind fall within README §4 thresholds of §4's combined rows | gap > 15 pp (n ≥ 20) or outside Wilson 95 % by > 5 pp → investigate | L2 |

## 8. Expected movement since E2 (fresh L2 import at `065b0d36` vs stored `ast-survey-agentdojo-p10`, built at `afe7038`)

| Change (regen-batch item / decision) | Expected effect on this corpus |
|---|---|
| Item 30 / D-31 bumps | every AER header: profile `survey-runs@2` (new sha256), `rules` `{aer 1, agentdojo 2, survey 1}`; SEM and PROV follow via `aer_digest` (all executions) |
| Item 3 / D-24, D-80 (I twins) | already I in the stored corpus (`structural_rule_class = "I"`); now via `verified_code = []`: same twin set (13 rules), completeness unchanged (`unverifiable` 3,243; no retries) |
| Item 5 / D-370 | one `agentdojo:load_environment` activity per execution with payload fixtures (2,847 executions, 4,401 fixture inputs) under the `_unverified` twin (I); PROV `used`/`wasAssociatedWith` in an inference bundle; +1 AER record per attacked execution |
| U6-c / D-373 | every `model_call` gains `unk /params not_recorded`; one `apv:Gap` per model call in PROV |
| Item 1 / D-86, `suites@2` | outcome and marker annotations cite twins (ev I) in every annotated execution; B1: 0 (no AutoDojo link) |
| Item 8 / D-379 (`yaml_norm@2`) | 0 marker status changes (measured 0 of 18,368); markers present 5,633 / absent 12,735 / ambiguous 0 stay |
| Item 6 / D-371 (`partial_payload`) | 52 executions / 156 annotations corpus-wide (measured); proportional share in the sample |
| Item 4 / D-377 | 0 `success_without_visible_payload` flags |
| Item 24 | the 49 unexecuted calls (48 logs): `apv:NotDispatched` points at the seal issue |
| Item 10 | 4 new tier-4 checks per row, all pass |
| Items 15, 19, 30 | `agentdojo` catalogue digest in every PROV |
| No effect expected | items 7 (0 lone surrogates), 9/11 (no loss codes), 13, 14 (survey 0), 17 (already `agentdojo_default`), 16/18/28/29 (no archive or member origins), D-182 (no redact table), D-460 (fresh import, no drift) |
| Held, not on `065b0d36` | `bugpass-regen` (33–41, D-451: stage digests only, no survey AER byte), `review-core-d-regen` (43–56: CD-13 block shapes expected 0 here, CD-15 n/a, no defence), `review-core-a-regen` (CA-14: transcript/v1 view bytes of every list-content tool message; views only) |
| Stage digests | `adapter_code_sha256`, SEM/PROV/validate `engine_code_sha256` all differ from the stored `derivation.json` |

## 9. Fact-check (2026-10-14, adversarial pass before any data check)

Re-opened at the pin and public records; no raw or corpus data read, nothing computed from data.

| Item | Verdict | Basis |
|---|---|---|
| §4 all 45 README cells (Phase 1, Full 949, Partial 105) and the per-model combined rows | confirmed | `agentdojo/README.md` @`89c4db2c` l.352-402; tables unchanged since `35f51954` (diffed at `26692cd6`, `35f51954`, `3c0f77ec`, `307f0532`) |
| §4 implied integer counts | confirmed | each one-decimal percentage admits exactly one integer for its n; suites sum to the combined row in all 13 sums |
| Consistency 1,624 / 1,027; gpt-oss 246/939 = 26.2 %; solvability 22/21/24 of 35 | confirmed | arithmetic on README + verify §2.4 / import `cross_checks` |
| Design 97/35/949 and per-suite 614/167/169/131 | confirmed | README l.213-219; arithmetic |
| Pin, HEAD, branches, 0 tags/releases/issues/PRs, CC-BY-4.0 | confirmed | GitHub API 2026-10-14 |
| `26692cd6` the only commit under `agentdojo/results`; deleted `restart_gptoss{,2}.sh` | confirmed | path-filtered commits API; commit files |
| `--force-rerun` added in `35f51954` (2026-08-25) to both scripts | confirmed | commit patch |
| Later commits touching `agentdojo/` | **corrected** (list completed, §1) | path-filtered commits API |
| Zenodo: 2 versions, sizes, md5, cc-by-4.0, creator | confirmed | `zenodo.org/api/records/22140262/versions?allversions=true` |
| Tree 3,256 / 43,565,675 | confirmed vs profile/import; composition **clarified** (§2) | profile l.38-52; import report |
| No paper | confirmed (unverifiable as a negative) | arXiv API search by title words and author, 0 hits |
| AgentDojo `089ed468` = upstream main HEAD, 5 ahead of v0.1.35 (`a75aba7`); temperature 0.0, `max_iters=15`, tenacity 3, 3-pass rerun | confirmed | GitHub compare API; source at `089ed468` |
| 3 local patches (timeout 1800, `model_rebuild`, `InternalServerError` → utility False / security True) | confirmed | README l.116-152 |
| AgentDojo issues #88 #154 #161 #162 #171 #181 #187 #194 #201 #212 #213 #214 (#150 #202 #219 #220 LocalLLM) | confirmed (state open, titles match) | GitHub API |
| Ollama 0.23.1 | confirmed as a claim; location **corrected** | top-level `README.md` l.59, `docs/requirements.md` |
| ollama#18530 open; #17353, #17276 closed as duplicate | confirmed | GitHub API |
| Model licences Apache-2.0 | confirmed; gpt-oss also ships a `USAGE_POLICY` (comply with applicable law), **added** to research.json | HF API / repo files |
| README "Affected tasks" (ws ut26/ut30, travel ut19), "deterministic" claim, ~63 h, partial task list | confirmed as README text | README l.289-296, 405-434 |
| H3 premise "35 gpt-oss attack pairs on those tasks" | confirmed | 14 + 14 + 7 |
| README partial-run contradiction (script table vs Phase 1 text) | **added** as desk context to H4 | README l.255 vs l.349; scripts at pin share logdir |
| Quirk counts §5 | confirmed | `artefacts.toml` expected rows; import `profile_census` |
