# Pre-registration: `dca-agentdojo`

| | |
|---|---|
| Corpus | `dca-agentdojo` (source `dca-agentdojo`, family `agentdojo`, profile `dca-agentdojo` version 1, dialect/mapper `agentdojo.tracelogger`; the `drift` part goes through the DRIFT build) |
| Parts | `v1`: 13,374 `v1.k14` logs. `drift`: 2,847 `drift.k18.conversations` logs. Both come from one `url` pin: Figshare file 65496114, `DCA_AgentDojo_artifact_v1_20260612.zip`, 54,196,099 B, MD5 `26a3a972…`, SHA-256 `ed500ca3…`. Parts are selected by `variant_labels` |
| Wave / mode | wave 7 (phase-10j parts, pending recipes). **Level 1 now. Level 2 is deferred to the post-check**, because the import waits for D-455 (`url` pins as archive inputs). D-455 is held on `bugpass-regen-d455` (regen item 101) and lands in the round |
| Code | `065b0d36` or later on `precheck-corpora` (written at `6b76c15e`; the examiner records the exact commit) |
| Date | 2026-10-14 (desk research run 2026-10-15) |
| Status | **Written before any pre-check data check of this corpus.** Nothing here was computed from the raw data in this step. Every number comes from a cited earlier report, the profile, the registry, Figshare/GitHub/PyPI metadata or decisions. Rates are arithmetic on those counts |
| Desk research | [`../data/dca-agentdojo/research.json`](../data/dca-agentdojo/research.json) |

Source keys used in the tables:
- P: profile `src/agentprov/adapters/agentdojo/profiles/dca-agentdojo.profile.toml`
- T: identity table `tables/dca_run_dirs.toml`
- REG: `tools/readme_corpora.toml`
- 10J-C: `docs/reports/phase10j/census.md` §4 and `census.json` `/sources/figshare-32657856`
- 10J-R: `docs/reports/phase10j/routing.md` R-10j-3/4/5
- 10J-T: `docs/reports/phase10j/trials.md` §3
- 10L-C: `docs/reports/phase10l/census.md`
- DEC: DECISIONS D-252, D-257 and the D-279 addendum
- FS: Figshare API `https://api.figshare.com/v2/articles/32657856`
- AD#n: an ethz-spylab/agentdojo issue or PR

## 1. Desk research in brief

- **No public paper.** The record and the deposit README name *Decision-Space Counterfactual Auditing for Prompt
  Injection Defense in Tool-Using LLM Agents*. None of these finds a paper with that title:
  - arXiv (title, abstract and author queries);
  - Crossref;
  - OpenAlex (it lists only the Figshare software record);
  - ORCID `0009-0008-7008-5763` (it lists only the Figshare item);
  - Zenodo;
  - web search.

  The paper's tables are therefore not available. The record says the deposit maps paper table rows to log directories
  and ships table-generation scripts, so the only reported numbers are **inside the pin**.
- **Data record.** Figshare article 32657856 has **v1 only** (the versions endpoint lists one). It was published
  2026-06-12T09:36:06Z, as software, under MIT, by one author. It holds one file, and the file's size and MD5 (supplied =
  computed) equal our pin. Figshare publishes no SHA-256; ours was verified at acquisition (2026-10-11T09:46:41Z,
  phase 10c). The pin is current. The record's own claims are:
  - 949 attacked `important_instructions` runs and 97 clean tasks;
  - direct, DCA, CaMeL, CaMeL+secpol and DRIFT rows;
  - keys, model weights, local paths and incomplete smoke tests are excluded.
- **Repository.** None is public; the code is in the zip (`code/dca_core`, `camel_runner`, `drift_runner`).
  `AnbiGuo/agentdojo-custom-defense` is a possible precursor, but the link is unverified:
  - no licence;
  - 11 commits, 2026-03-24..04-02;
  - requires `agentdojo>=0.1.35`;
  - registers its defence through `sitecustomize.py` (under the names `causal` and `my_defense`, not `causal_budgeted`:
    *fact-check addition*, which weakens the link further);
  - no logs.

  It is not a source.
- **Harness.** PyPI `agentdojo` 0.1.35 (tag `a75aba76`, 2025-10-27, the latest release) runs benchmark v1.2.2. The
  following fixes and open issues matter for these logs:
  - temperature 0.0 is never sent (AD#141, fixed on main 2026-02-03, after 0.1.35). **Corrected (fact-check):** the bug is in
    `OpenAILLM` only (`temperature or NOT_GIVEN`). In 0.1.35 `LocalLLM` passes `temperature` explicitly, so the 3 `local`
    arms are not affected. 0.1.35 also has no `openrouter` provider, and the CaMeL and DRIFT runners use their own code. So
    the bug applies to the direct and DCA arms only if they go through `OpenAILLM`, which is unverified (deposit code
    not read);
  - the empty-tool-call crash (AD#136, fixed later);
  - LocalLLM keeps only the first call, drops malformed calls and turns server errors into empty answers (AD#150, #202,
    #219, #220). This applies to the 3 `local` arms;
  - run errors impose utility false and security true (AD#154);
  - `security_from_traces` scores proposed calls, not executed ones (AD#168, #189);
  - workspace injection tasks 6..13 have no ground truth (AD#213).

  Other runners: the CaMeL runner is built on google-research/camel-prompt-injection (Apache-2.0, `f083b6b3`). The DRIFT
  runner is a "compat" module. Upstream DRIFT main was at `70d59166` (2026-04-19) before the deposit, and its LICENSE file
  dates from 2026-07-16 (after the deposit).
- **Models** (T, from the README, D-92):
  - gpt-4o-mini-2024-07-18 through OpenAI;
  - openai/gpt-oss-20b through OpenRouter. The DRIFT arm instead logs the Ollama tag `gpt-oss:20b`, so its route is
    unrecorded;
  - Qwen3.6-27B: the attacked rows run through Ollama, the clean rows through OpenRouter;
  - Qwen2-7B through Ollama, in the direct attacked arm only.

  All four models exist upstream (HF, OpenRouter and Ollama listings, research.json). Quantisation is not recorded.
- **Licence.** MIT (FS). `third_party_licenses/` carries AgentDojo (MIT), CaMeL (Apache-2.0) and DRIFT/ASB (MIT). There is
  no data licence. Model-provider output terms are unassessed. Profile policy: `include`.

## 2. Expected counts

| Measure | Expected | Source |
|---|---:|---|
| Zip members (all at level 1; gate `d1:selected`) | 16,346 | 10J-C (`members`, `gate`) |
| TraceLogger logs = files = units = executions | 16,221 (v1 13,374 + drift 2,847) | 10J-C; REG (13374, 2847, basis census); P header |
| Non-log members (README, docs, code, licences, usage traces, tables) | 125 | 16,346 − 16,221 |
| Strict parse ok; byte-identical extra copies | 16,221; 0 | 10J-C (`parse.ok`, `byte_identical_extra_copies` {}) |
| v1 directories | 19 = 13 attacked × 984 + 6 clean × 97 = 12,792 + 582 | 10J-C `run_dirs_byte_distinct`; T |
| Per attacked v1 arm: attacked + injection-task pre-pass | 949 + 35 = 984 (banking 144+9, slack 105+5, travel 140+7, workspace 560+14) | v1.2.2 grid; 10J-C |
| Per clean arm (benign `user_task_N/none/none`) | 97 (16 / 21 / 20 / 40) | FS description; 10J-C |
| v1 attacked / pre-pass / benign | 12,337 / 455 / 582 (attack_type `None` 1,037) | arithmetic; DEC D-279 addendum (12,337); 10J-C (`attack_type.None` 1,037) |
| drift directories | 3 × 949 (144 / 105 / 140 / 560), 0 benign, 0 pre-pass | 10J-C; 10L-C §3 |
| Suites over both parts: banking / slack / travel / workspace | 2,517 / 1,871 / 2,451 / 9,382 | 10J-C `suite_name` (reproduced by the per-arm grid) |
| Labels with `:` | 3,866 (v1 1,968 = 2 × 984 Qwen3.6 CaMeL dirs; drift 1,898) | 10J-C; D-56 |
| Content-distinct (fp_run); repeat groups / files in groups | 15,196; 1,022 / 2,047 (1,025 repeats: 765 CaMeL vs CaMeL+secpol, 243 direct Qwen3.6 vs DCA, ~17 other) | 10J-C |
| `benchmark_version` | `v1.2.2` in 16,221 | 10J-C |
| `agentdojo_package_version` | `0.1.35` in 13,374; absent in 2,847 | 10J-C |
| `error` string / null / absent | 4 / 13,370 / 2,847 | 10J-C; P `run_error_imposes_outcome` (4) |
| No system message | 8,751 (5,904 CaMeL = 6 × 984; 2,847 drift); default prompt (sha `a021a92b`, 469 chars) in 7,470 | 10J-C |
| Last assistant content null | 4,274 over all 16,221 logs, both parts (P `null_final_logs` 4,269 is v1 only, over sealed logs; *fact-check clarification: the denominators differ*) | 10J-C; P |
| `utility` true / `security` true (raw fields, all logs) | 6,826 / 1,809 | 10J-C |
| drift messages; tool calls (batches); CALL ERROR user messages (files) | 21,577; 7,456 (6,966); 724 (515) | 10L-C §3 (P counts 7,455 / 6,965 over 2,846 sealed) |
| Sealed in the phase-10j census mapping | v1 13,372 / 13,374; drift 2,846 / 2,847 | 10J-T §3; 10J-R R-10j-4 (2 negative durations), R-10j-5 (1 tool `none`) |
| Secret-like strings; account paths | 0; 0 expected | 10J-C `secret_like` {}; FS ("local machine paths" excluded) |
| L2 sample (post-check), key `(model_dir, suite, attack_dir)` | v1: 128 strata, about 300 units (5 per stratum is 640 > 300, so proportional reduction with at least 1 each); drift: 12 strata × 5 = 60 | README §4 rule; §6 below |

## 3. Expected arms

The identity key is `<group>/<run dir>/<pipeline dir>` (T, D-104). Every v1 arm covers the same four suites (*fact-check: wording corrected*).

| Model (route) | none (direct) | causal_budgeted (DCA) | camel | camel_secpol | drift |
|---|---|---|---|---|---|
| gpt-4o-mini-2024-07-18 (OpenAI) | 984 attacked + 97 clean | 984 + 97 | 984 | 984 | 949 |
| openai/gpt-oss-20b (OpenRouter; drift arm `gpt-oss:20b`, route unrecorded) | 984 + 97 | 984 + 97 | 984 | 984 | 949 |
| Qwen3.6-27B (attacked through Ollama, clean through OpenRouter) | 984 (`local`) + 97 (`qwen_qwen3.6-27b`) | 984 (`local-causal_budgeted`) + 97 (OpenRouter) | 984 | 984 | 949 |
| Qwen2-7B (Ollama) | 984 (`local`) | — | — | — | — |

- **Expected missing cells:**
  - clean runs for CaMeL, CaMeL+secpol and DRIFT (9 model × defence cells);
  - Qwen2-7B except direct attacked;
  - every attack other than `important_instructions`;
  - DRIFT pre-pass runs.
- **Expected extra cells:** none. Any directory outside the 22 rows of T is a finding.
- **Route split** (expected-known, T basis): Qwen3.6-27B attacked and clean rows come from different serving stacks.

## 4. Expected outcome rates and the mapping

**Mapping (logged fields to metrics).** The 35 pre-pass logs per arm (`injection_task_N/none/none`) enter no rate.
- `utility` is the user task's checker result.
- `security = true` means the injection task succeeded.
- On `none` runs `security` is the constant `true` (`agentdojo.benign_security_constant@1`).
- Run-error logs carry utility false and security true (`run_error_imposed_outcome@1`, 4 logs). They are reported
  separately and kept in the denominators.
- **UA** = utility true / 949 attacked. **ASR** = security true / 949 attacked. **Clean utility** = utility true / 97.
- Pooled over 949 is primary (the record says "over 949 attacked runs"). The macro mean over suites is reported beside it.

**Targets.** No public paper exists, so there is no paper table. The targets are:

| Arm | n | Target | Basis |
|---|---:|---|---|
| v1, 13 attacked arms pooled, ASR | 12,337 | 772 (6.26 %), exact | DEC D-279 addendum (phase-10c count) |
| drift, each arm and pooled, ASR | 949 each; 2,847 | 0 (0.00 %), exact | DEC; 10J-C; 10L-C §5 |
| All logs, raw `utility` true / `security` true | 16,221 | 6,826 / 1,809, exact | 10J-C |
| v1 benign + pre-pass, `security` true (constant) | 1,037 | 1,037 (100 %) | 1,809 − 772; benign constant |
| Per-arm UA / ASR / clean utility (19 + 3 arms) | 949 / 97 | **the deposit's own tables** (see the rule below) | FS: README maps table rows to directories |
| Context only, not a target: gpt-4o-mini × DRIFT | 949 | DRIFT paper v3 50.93 / 1.35 (macro; other run set, other harness) | arXiv:2506.12104v3 Tables 7-8 |

**Rule for the per-arm targets** (fixed now, before any rate):
1. At L1 the examiner reads the deposit's `README.md` and `docs/*.md` (profile `context_artefacts`) through
   `agentprov.ingest`, with `quote_untrusted`.
2. The examiner transcribes the table values per directory and commits them as an amendment to this file **before**
   computing any population rate.
3. The README §4 gap rule then applies to the L1 population rates: more than 15 pp, or more than 5 pp outside a Wilson
   95 % interval.

If the tables give only rounded percentages, a gap within the rounding (±0.05 pp × n) is not a finding. A missing table
for an arm is reported as a documentation gap (S3). **L2:** no sample rate is computed until the post-check import.

## 5. Known quirks (do not report as new)

| Id / source | What | Expected |
|---|---|---|
| P `benign_security_constant` | benign `security` constant true | v1 1,036 files sealed (1,037 by arithmetic) |
| P `injection_task_as_user_task_prepass` | pre-pass runs under `none` | v1 454 sealed (455 by arithmetic; the unsealed one is the negative-duration pre-pass log); drift 0 |
| P `silent_rerun_last_pass_only` | null final means up to 3 passes, only the last logged | 4,269 null-final logs |
| P `unexecuted_trailing_calls` | proposed calls that were never executed | 187 calls in 161 logs |
| P `args_mutated_in_place` | 0.1.35 `ToolsExecutor` | v1 11,209; drift 2,677 files |
| P `placeholder_args_never_injection_evidence` | `placeholder_args` present and null | 31,997 |
| P `provider_call_id_anomalies` | null call ids | 10,631 ids in 3,853 logs; 0 duplicates |
| P `run_error_imposes_outcome` | error string means utility false, security true | 4 logs |
| P drift quirks (D-273..D-277) | post-isolation outputs 6,965 / 7,455; re-serialised 8,493 / raw 2,055; CALL ERROR 724 msgs / 515 files; calls in text not executed 291 turns; no system message, no injection map; plan semantics `initial_plan` 2,846 | P observed |
| 10J-R R-10j-4 | negative `duration` (−0.2246 s, −0.6300 s), CaMeL gpt-oss and Qwen3.6 secpol | 2 logs; fix in regen item 96 (held) |
| 10J-R R-10j-5 | a tool named `none` (drift gpt-oss slack UT10 / IT2) | 1 log; fix in regen item 97 (held) |
| D-252 | content repeats kept; `gpt-oss:20b` route unrecorded; `local` rows from the README | 1,025; 949 |
| D-56 | `:` in labels | 3,866 |
| D-257 | no `[withhold]` table | — |
| 10L-C §5 | drift injection header visible in 123 / 2,847 runs; 165 frames, all in non-last positions; 0 successes (datasheet context, never an exclusion) | as stated |
| artefacts.toml | **no entry is scoped to `dca-agentdojo`** (`adapters/agentdojo/artefacts.toml` has no DCA/Figshare id) | documentation gap (S3), not a corpus property |

## 6. Check map

| Check | Applies | Expected / why |
|---|---|---|
| L1-01 counts | yes | section 2. Any difference from 16,346 / 16,221 / 13,374 / 2,847, or from the per-directory grid (984 / 97 / 949), is a finding. The 125 non-log members are not selected (`include` depth) |
| L1-02 strict parse | yes | 0 failures (10J-C `parse.ok` 16,221). Key sets: v1.k14 in 13,374; KD18 + `conversations` in 2,847 |
| L1-03 encodings | yes | no prior count. Report per pointer. The DRIFT CALL ERROR `repr` wrapper is a known literal-escape residue (724 messages) |
| L1-04 duplicates | yes | 0 byte-identical within the pin. Content repeats 1,025 (groups as in section 2). 0 byte overlap with drift head, AgentDyn c/d, EnvironmentOptim and drift-1 (10L-C §1.1). 0 against other v1.k14 sources (10J-C `novel_vs_phase10c_known`); `l1_xdup.py` confirms |
| L1-05 arm coverage | yes | 22 directories, cells as in section 3. **Precondition:** `tools/precheck/l1_families.py` `STRATA` gains `"dca-agentdojo": ("model_dir", "suite", "attack_dir")`. The family default would leave `pipeline_dir` unset under this layout and merge the arms. L1-05b: population outcome recount against section 4 |
| L1-06 secrets, account paths | yes | 0 secret-like strings (10J-C); 0 account paths (FS; the `local` pipeline names hold none). Counts and pointers only |
| L1-07 timestamps | v1 yes; drift presence only | v1: `evaluation_timestamp` in 13,374 (2026-05: 5,075; 2026-06: 8,299). drift: no time field. Content stamps in 292 runs, 2026-05-19..06-03 (10L-C §5). Negative `duration` 2 |
| L1-08 degenerate | yes | 0 empty files. 4 error-string runs. 4,274 null last assistant. 8,751 without a system message. drift messages per run min/median/max 2/6/38 (10L-C §3); every drift run ends with an assistant message |
| L2 sample list | yes (drawn now, committed) | section 2 strata. The post-check reuses it unchanged |
| L2 import, validate, recompute, determinism, chain | **deferred to the post-check** | needs D-455 (held, regen item 101). The phase-10j census mapping (`tools/agentdojo/phase10j_profiles.py census`, release-mode seal) is the only prior mapping, and it is not the product path |
| L2 A2/A3 classes, evidence classes | deferred | prior: every D rule goes through its `_unverified` twin (`code_identity = unpinned`, `verified_code = []`) |
| L2 identity | deferred | 22 rows of T; `pipeline_name` verbatim when it differs |
| L2 redaction | deferred | no account path expected |
| L2 withholding | n/a | no `[withhold]` table (D-257) |
| E2 delta | n/a | not in FA or E2; no stored corpus |

## 7. Hypotheses (falsifiable; threshold in brackets)

| # | Expectation | Refuted if |
|---|---|---|
| H1 | Counts and grid as in section 2 | any count differs [0 tolerance] |
| H2 | 13 attacked v1 arms hold 949 attacked + 35 pre-pass each; 6 clean arms hold 97; drift arms hold 949 attacked only | any arm deviates by ≥ 1 log |
| H3 | drift ASR = 0 in each arm | any `security = true` among the 2,847 |
| H4 | v1 attacked ASR pooled = 772 / 12,337; benign + pre-pass `security` true = 1,037 / 1,037 | either count differs by ≥ 1 |
| H5 | per-arm population UA / ASR / clean utility equal the deposit's own tables | a gap over the README §4 threshold (15 pp, or 5 pp outside Wilson 95 %) on any arm with n ≥ 20 |
| H6 | every v1 `evaluation_timestamp` parses and lies in [2026-05-01, 2026-06-12T09:36:06Z] | any unparseable value, or any value outside that range |
| H7 | the 3 `local` arms (LocalLLM; AD#150/#202/#219/#220) show a higher share of attacked runs whose final assistant turn has call-like text but no `tool_calls` than the same models' OpenRouter/OpenAI arms | `local` share ≤ API share + 1 pp |
| H8 | CaMeL vs CaMeL+secpol repeats = 765 groups' worth and direct-vs-DCA Qwen3.6 = 243; other repeats ≤ 20 | other repeats > 20, or the two pairs differ from 765 / 243 by > 5 |
| H9 | v1 attacked runs with `security = true` whose injection-task call was proposed but not executed (AD#168) are ≤ 161 logs, all in DCA or CaMeL arms | > 161, or any in a direct arm (*fact-check note: no prior report breaks the 161 logs down by arm, so the "DCA or CaMeL only" part is an assumption, not a prior count*) |
| H10 | drift: injection header in 123 runs; 165 visible frames, all in non-last batch positions | either count differs by > 0 |
| H11 | 0 secret-like strings, 0 account paths | any hit |
| H12 | exactly 3 unsealable logs under current code (2 negative durations, 1 tool `none`); 0 once regen items 96/97 land | any other log fails to seal |

## 8. Movement since E2

None: not a delta corpus. Code movement since the phase-10j census that touches these bytes:
- D-455 (held; the import path; `retrieved_at` from the acquisition record, commit `ba0b2ded`);
- regen items 96/97 (held);
- the shared agentdojo-family items already on main for every TraceLogger source (item 3 twins, D-86).

The post-check compares the round's import with this L1 population and the committed sample list.

## 9. Fact-check (adversarial, 2026-10-15)

This section was written before any data check. It used only cited documents and public metadata, and no new
expectation was derived from the data.

**Checked and confirmed**
- *Pin and record.* [Figshare API](https://api.figshare.com/v2/articles/32657856): version 1 only
  ([versions](https://api.figshare.com/v2/articles/32657856/versions)), software, MIT (licence id 3), one author, ORCID
  `0009-0008-7008-5763`, no related materials. Published 2026-06-12T09:36:06Z, modified 09:42:06Z. One file: 65496114,
  54,196,099 B, supplied MD5 = computed MD5 `26a3a972…`. All of these equal P `[[source.pins]]` (url, sha256, md5, size).
  The record title ends with "Code and Evaluation Artifacts".
- *No public paper.* arXiv API (title, all-fields, author and abstract queries), Crossref, OpenAlex (only W7164512430,
  the software record), the ORCID works list (only the Figshare item) and a web search turned up nothing. The author's
  only arXiv paper, 2510.00529, is unrelated.
- *Counts* re-derived from 10J-C `census.json` (no raw data):
  - 16,346 members; 16,221 logs; parse ok; 0 byte copies;
  - 19 + 3 directories with 984 / 97 / 949 logs, which equals the 22 rows of T;
  - attack_type `None` 1,037 and `important_instructions` 15,184 (= 12,337 + 2,847);
  - suites 2,517 / 1,871 / 2,451 / 9,382, which the per-arm grid reproduces exactly;
  - colon labels 3,866; content-distinct 15,196 (2,047 − 1,022 = 1,025 repeats);
  - system-prompt split 8,751 / 7,470; error 4 / 13,370 / 2,847; ts_month 5,075 / 8,299; utility true 6,826, security
    true 1,809.
- *DECISIONS.* The D-279 addendum (l. 2831-2834) gives 772 / 12,337 and 0 / 2,847. 10L-C §3 and §5 give the DRIFT
  counts as stated (21,577; 7,456 / 6,966; 724 / 515; 2/6/38; 292 stamps; 123 / 2,847 against 1,270 / 1,509; 165 frames
  "in earlier positions").
- *Unsealable logs.* 10J-T §3 and 10J-R give 13,372 / 2,846 sealed. The negative-duration pre-pass log is the CaMeL
  gpt-oss `travel/injection_task_3/none/none.json`, which accounts for 454 and 1,036.
- *Held commits.* `4a5fe7fb` (items 96/97), `f04dd434` and `ba0b2ded` (D-455, item 101) are not on this branch or on
  `origin/main`.
- *Strata.* The `{model_dir?}` layout gives a full-path `model_dir`, so v1 has 13 × 4 × 2 + 6 × 4 = 128 strata and drift
  has 12. `l1_families.py` has no `dca-agentdojo` key, and the family default (`_prefix`, `pipeline_dir`, …) leaves both
  unset under this layout.
- *Context target.* [DRIFT v3](https://arxiv.org/html/2506.12104v3) Tables 7 and 8 give GPT-4o-mini DRIFT UA 50.93 and
  ASR 1.35. Both equal the unweighted mean of the 4 suite values (macro). The version dates are v1 2025-06-13, v2
  2025-10-24 and v3 2026-03-26.
- *Harness.* PyPI's latest release is 0.1.35 (2025-10-27), at tag `a75aba76`. AD#141 was merged 2026-02-03 and AD#136
  2026-03-30 (empty-tool-call and ellipsis-argument crashes). The states and titles of #150, #154, #161, #168, #181,
  #189 (closed 2026-09-07), #201, #202, #213, #219 and #220 are as cited. #154 is the context-length branch of
  `benchmark.py`, which sets utility false and security true.
- *Upstream code.* The last DRIFT commit before the deposit is `70d59166` (2026-04-19). DRIFT's LICENSE was first added
  in `6fd3df47` (2026-07-16, MIT). CaMeL HEAD is `f083b6b3` (2025-06-20, Apache-2.0, requires `agentdojo>=0.1.34`). The
  precursor repo has no licence, 11 commits (2026-03-24..04-02), HEAD `c3492a89`, 71 tree entries, 0 `.json` files, and
  requires `agentdojo>=0.1.35`.
- *Models.* The Hugging Face cards for Qwen3.6-27B (created 2026-04-21), Qwen2-7B(-Instruct) and gpt-oss-20b all say
  Apache-2.0. OpenRouter lists `qwen/qwen3.6-27b` and `openai/gpt-oss-20b`. The Ollama tags `qwen3.6:27b` and
  `gpt-oss:20b` exist. `local` is 0.1.35's `ModelsEnum.LOCAL`, which maps to `LocalLLM`.

**Corrected**
- AD#141 scope (§1): the bug is not general to this harness. It applies only to `OpenAILLM`. `LocalLLM` sends
  temperature 0.0 explicitly, so the `local` arms are not affected, and the CaMeL, DRIFT and OpenRouter routes are
  custom code that was not verified.
- Null-final denominators (§2): 4,274 is counted over both parts and 4,269 over sealed v1 logs only.
- §3 wording, and the H9 note: no prior report gives the 161 logs' distribution by arm.
- research.json cited the context target as "Tables 2, 7, 8". It is Tables 7-8; Table 2 is the adaptive-attack table.

**Unverifiable at P0**
- Anything inside the pin: the README's table rows, the third-party licence texts, and the runner code.
- Whether the precursor repo is the DCA code. Its `sitecustomize.py` registers `causal` and `my_defense`, not
  `causal_budgeted`.
- Whether the record's "over 949 attacked runs" means pooled rates.

**Documentation note (ours, S3)**
- P's pin note still cites D-580 for `retrieved`. Commit `18e121a2` (id ledger) records D-580 as voided and superseded by
  D-455.
