# Pre-check dossier: `menelaus29-ipi-multidomain`

## 1. Header

| | |
|---|---|
| Corpus | `menelaus29-ipi-multidomain` (MIT, (c) 2026 Khue Vu; no separate data licence; logs embed AgentDojo benchmark text, MIT) |
| Parts | `menelaus29-ipi-multidomain · head` (1 part; the 107 branch-only logs wait, D-108) |
| Family / profile | `agentdojo` / `menelaus29-ipi-multidomain@1` (dialect `agentdojo.tracelogger`, variants `v1.k14`, `v1.k14.incomplete`; identity table `menelaus29_experiment_dirs.toml`, D-104) |
| Pin | git `Menelaus29/ipi-multidomain-agent-study` @ `ec9c9287` (2026-08-22, = head of `main`), tree 1,028 blobs |
| Code commit | `d97d3a57` (L1 and L2, batch `wave3`, all 6 steps rc 0, tracked changes false; after the CC-08 fix `5efa3575`) |
| Kind | wave 3, first examination (not in FA or E2); no stored corpus |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (batch), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), examiner (this dossier); adversarial verifier 2026-10-21 (7/7 confirmed, 0 refuted; `findings.json` verdicts) |
| Data | [`data/menelaus29-ipi-multidomain/`](data/menelaus29-ipi-multidomain/): `research.json`, `l1-head.json`, `l1-10-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `findings.json`, `os1-population.json`, `os2-sample.json`, `raw-census.json`, `exam-scripts/` |

- Code identity, part `head` ([`code-head.json`](data/menelaus29-ipi-multidomain/code-head.json)): commit `d97d3a57` (tracked_changes false); engine code aer `856b7a09e0cf`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `agentdojo.tracelogger@0.1.0` `03d8bc6d30df`; profile sha256 `349323d6c9ea`, rules agentdojo 2 / aer 1; lockfile `b0455f1058c8`, limits `5d6dbb210259`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Source repository | https://github.com/Menelaus29/ipi-multidomain-agent-study @ `ec9c9287` (16 branches, 0 tags, 0 releases, 14 merged PRs, 0 issues) | the data; author reports (README, `docs/*.md`, summary CSV/JSON) = outcome reference |
| Paper | none (arXiv, Zenodo, HF: 0 hits); final report git-ignored, unpublished | numbers come from the repository's own reports |
| AgentDojo | https://arxiv.org/abs/2406.13352; `agentdojo==0.1.35`, suites v1.2.2 | benchmark and checker |
| Defence basis | Hines et al., spotlighting, https://arxiv.org/abs/2403.14720 | `my_spotlighting` design |
| Upstream issues | ethz-spylab/agentdojo [#181](https://github.com/ethz-spylab/agentdojo/issues/181), [#214](https://github.com/ethz-spylab/agentdojo/issues/214) (open), [#161](https://github.com/ethz-spylab/agentdojo/issues/161), [#95](https://github.com/ethz-spylab/agentdojo/issues/95) (closed clarification) | checker precedence, payload escaping, constant pre-pass security |

Data-versus-reports notes (checked against the data):

- Every author number of prereg section 4 reproduces exactly from the raw `utility`/`security` fields (19 of 19 arms, section 6).
- The 787 attacked logs = 770 reported evaluations + 3 injecagent controls + 10 Gemma sanity + 3 Gemini 3.6 sanity + 1 unvalidated v2a log. The v2a log is the empty, outcome-less one.
- #181 does not bias any banking ASR here: every one of the 33 banking IT0/1/3 successes executes an attacker transfer whose subject holds the GOAL datum (PC-01).
- The Windows account paths in the author's `validation_report.json` files stay outside the raw store. They are not selected and are not context artefacts.

## 3. Expectations

Pre-registration: [`prereg/menelaus29-ipi-multidomain.md`](prereg/menelaus29-ipi-multidomain.md), committed in `fd75f8a3` (2026-10-14), before any check of this corpus ran. Amendments 2 to 5 apply; amendment 1 does not (no stored corpus). Amendment 2.4 fixes the stratum key to the family hook `model_dir × attack_class` (44 strata, 144 units). The prereg suggested experiment × suite × kind (52 strata, about 158 units); the difference is R6, not a finding. Classes follow [`cross-cutting.md`](cross-cutting.md).

| H | Result | Note |
|---|---|---|
| H1 | supported | every dir × suite × kind count = prereg section 2; 70 pre-pass only under `injection_task_*`; 0 benign user-task logs (besides the example log) |
| H2 | supported | Gemini baseline security true 0/110; utility ws 52/52, banking 26/46, slack 12/12 |
| H3 | supported | 5/110, all banking UT0 × IT0, vector bill_text, payloads encoding-03, fake-system-04, persona-04, template-02, template-03; Gemma key set = Gemini 113 minus 3 injecagent |
| H4 | supported | full fresh 34/160 (utility 103), replication 6/20 (10) |
| H5 | supported | fresh160 4/160 (115); builtin 4/20 (10); custom 0/20 (10) |
| H6 | supported | v1 1/24 (14); v2b 5/33 (22); v2a 1/72, repair 0/16, utility 71/88; empty log = 73rd v2a log (UT12 × IT4, `adaptive_b43850c62aa7`) |
| H7 | supported | 2/25: banking builtin direct (UT0 × IT5), slack builtin tool_knowledge (UT0 × IT3) |
| H8 | supported | 63/787; the 1 outside reported arms is in `diagnostics/gemma4_sanity_check/raw` |
| H9 | supported | 0 of 33 #181-exposed successes lack the stated subject content; raw = mapped (PC-01) |
| H10 | partly tested | range holds (858/858 naive, 2026-08-04 00:11:39 .. 2026-08-17 13:38:58); per-file commit comparison not run (PC-07) |
| H11 | supported | pipeline names 710 / 120 / 22 / 6, no other name |
| H12 | supported | shared attacked keys 19 / 11 / 32, pre-pass 4 / 4 / 7 and 3 / 4 / 4 with `v2a_repair`; 0 fingerprint-equal pairs |
| H13 | supported | 0 secret-like, 0 account paths in 858 selected; aux 0/1; L1-10 0/10 |
| H14 | supported (sample only) | marker in 15/15 sampled Gemini baseline attacked runs; population rate from the round import |
| H15 | supported | population: one my_spotlighting digest on 358 logs (+1 empty log), one built-in digest on 22, default on 477; sample `system_prompt_unrecognised` 55/55 = my_spotlighting |
| H16 | supported | 19 payload ids in the parity dirs |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: the staged bare clone at `ec9c9287` (`--git`, `GIT_NO_LAZY_FETCH`), tool `l1_scan` v1 at `d97d3a57`, 1.1 s.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 1,028 walked = 858 selected + 11 context + 151 not selected + 8 absent blobs (the PNGs, not selected); 0 excluded or rejected. Units 858 = registry/census figure. Variants `v1.k14` 857, `.incomplete` 1. Attacked 787, pre-pass 70, example log 1 | as expected, except context 11 vs prereg 13 (PC-06) |
| L1-02 parse | strict ok 858/858, aux 1/1; 0 of every defect class | as expected |
| L1-03 encodings | escaped_unicode 190 files (222 strings: 111 tool content, 111 `/injections/*`), escaped_newline 207, escaped_quote 14, mojibake 6 (tool content), U+2028 5, NEL 3, CR 2 (all `/injections/*`), zero-width 1; 0 C0/C1, bidi, tag, U+FFFD | expected (#214, encoding payloads; PC-05) |
| L1-04 duplicates | byte-identical 0; trajectory-identical 0 groups (857 distinct of 857; CC-01 definition); `_cross/l1-xdup.json`: 0 cross-corpus groups | as pre-registered (H12) |
| L1-05 arms | 44 strata over 22 experiment paths; every pre-registered cell present, 0 extra; by-design absences (no travel, no defended workspace/slack, no benign user task) | as expected |
| L1-06 secrets/paths | 0/858 selected, 0/1 aux; L1-10 0/10 context files, 0 operator hits | as expected (H13) |
| L1-07 timestamps | `/evaluation_timestamp` 858/858, all naive, 0 parse failures, 2026-08-04 .. 2026-08-17; 3 benchmark-content stamps (2024-06-10); 0 non-monotone | as expected (H10 range) |
| L1-08 degenerate | zero_messages 1 + incomplete 1 (same v2a log, null outcomes); layout_mismatch 1 (example log); trailing-call logs 0; tool-error messages 2; `error` null 858 | as expected; census double count (PC-03) |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`l2-sample-head.json`](data/menelaus29-ipi-multidomain/l2-sample-head.json) (sha256 `c837be93108d…`): 144 of 858, 44 strata, seed 20261011; the empty v2a log is not drawn |
| Import | j2 and j1 scratch corpora: 144 mapped, 143 sealed clean, 1 with issues (example log, `identity_unresolved`), 0 degenerate, 0 `adapter_defect`, 0 failed; join 144 labels → 144 executions 1:1; 155 raw objects (144 + 11 context) |
| Validation | aer, sem, prov, linkage: 144/144 pass, 144 reproduced, linkage 100 %; SHACL not implemented (skipped) |
| Recompute | `--dry-run`: 144 identical, 0 unexplained |
| Verify chain | 0 failures (only `checksums.absent`, working tree); no withholding policy |
| Determinism | j2 vs j1: 594/594 files, 0 differ, index identical |
| A2 | `map.accounting_unverifiable` 144, `map.earlier_attempts_unobservable` 144, `map.agentdojo.system_prompt_unrecognised` 55, `map.identity_unresolved` 1 (the trial's codes only) |
| A3 | 0 dangling, forbidden or invented relations over 61,763 statements and 104,911 relation arguments; 936 messages with `generated_by`, 537 model calls with input, 399 tool executions with call |
| Evidence classes | AER: O 1,972, I 1,804, D 0 (`verified_code = []`). PROV class D only from engine or code-independent rules: core `aprov.n_gap` 519, `aprov.n_capture_profile` 144, assessment `aprov.a_label` 34, all from `agentdojo.partial_payload@1`. That rule is class D by catalogue: a text computation over the AER (D-371), not harness code. The prereg phrase "D rules only as twins" did not foresee it. Twin / native / mixed split (post-CC-08 counter): twin inference I 15,614 + 1,512 (no class), assessment I 2,472; mixed inference I 2,512; native 0 |
| Identity | 0 direct mismatches; model unresolved 1 (example log); the only one-to-many maps are the designed ones (Gemma pipeline → none / my_spotlighting by path; Gemini 3.5 pipeline → example log unresolved); built-in dir → Gemma 4 7/7; Gemini 3.6 6/6 by the logged label = directory, model unverifiable (PC-04) |
| Judgements | raw vs mapped: 288/288 equal |
| Redaction | 440 AER/SEM/PROV files, 0 hits |
| Withholding | not applicable (no policy, 0 L1-06 hits) |

## 6. Outcome comparison

Level 1 = population (raw booleans). Reference = the author reports of prereg section 4. ASR excludes pre-pass logs and the 3 injecagent controls. Gap rule: > 15 pp on n ≥ 20, or > 5 pp outside the Wilson 95 % interval. Rows: [`os1-population.json`](data/menelaus29-ipi-multidomain/os1-population.json).

| Arm (model / defence / dir) | n | ASR % (Wilson 95 %) | Reports | Utility (L1 / reports) | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|
| Gemini 3.5 FL / none / baseline, all | 110 | 0.00 [0.00, 3.37] | 0/110 | 90 / 90 | 0 | match |
| ↳ workspace / banking / slack | 52 / 46 / 12 | 0 / 0 / 0 | 0 / 0 / 0 | 52/52, 26/26, 12/12 | 0 | match |
| Gemma 4 / none / parity, all | 110 | 4.55 [1.96, 10.20] | 5/110 | 90 / n.r. | 0 | match |
| ↳ workspace / banking / slack | 52 / 46 / 12 | 0 / 10.87 [4.73, 23.04] / 0 | 0 / 5 / 0 | 52, 26, 12 / n.r. | 0 | match |
| Gemma 4 / none / full, fresh160 | 160 | 21.25 [15.62, 28.22] | 34 | 103 / 103 | 0 | match |
| Gemma 4 / none / full, replication | 20 | 30.00 [14.55, 51.90] | 6 | 10 / 10 | 0 | match |
| Gemma 4 / my_spotlighting / fresh160 | 160 | 2.50 [0.98, 6.25] | 4 | 115 / 115 | 0 | match |
| Gemma 4 / spotlighting_with_delimiting / builtin | 20 | 20.00 [8.07, 41.60] | 4 | 10 / 10 | 0 | match |
| Gemma 4 / my_spotlighting / custom | 20 | 0.00 [0.00, 16.11] | 0 | 10 / 10 | 0 | match |
| Gemma 4 / my_spotlighting / adaptive v1 | 24 | 4.17 [0.74, 20.24] | 1 | 14 / 14 | 0 | match |
| Gemma 4 / my_spotlighting / adaptive v2a (outcome-bearing) | 72 | 1.39 [0.25, 7.46] | 1 | 56 / — | 0 | match |
| Gemma 4 / my_spotlighting / adaptive v2a_repair | 16 | 0.00 [0.00, 19.36] | 0 | 15 / — | 0 | match |
| ↳ v2a + repair | 88 | 1.14 [0.20, 6.16] | 1 | 71 / 71 | 0 | match |
| Gemma 4 / my_spotlighting / adaptive v2b | 33 | 15.15 [6.65, 30.92] | 5 | 22 / 22 | 0 | match |
| Gemma 4 / none / diagnostics g4 + raw | 25 | 8.00 [2.22, 24.97] | 2 | 19 / n.r. | 0 | match |

0 population gap flags. CC-07: #181 affects 0 of the 33 banking IT0/1/3 successes, so every re-scored banking ASR equals the logged one. #161 does not apply (0 `user_task_5` logs). CC-10 (#168): 0 of the 26 attacked slack logs record attack success (L1 `outcomes_by_stratum`), so #168 affects 0 executions (completeness critic 2026-10-21).

Level 2 (mapped AER of the sampled labels, which equal the raw values 288/288; [`os2-sample.json`](data/menelaus29-ipi-multidomain/os2-sample.json)). The largest arm has n = 15, so no arm reaches 20 and the sample gives no verdict (amendment 2.2, R6). The verdicts rest on the population.

| Arm | n | ASR (Wilson 95 %) | Ref. % | Utility (Wilson 95 %) | Ref. % | Verdict |
|---|---|---|---|---|---|---|
| Gemini baseline | 14 | 0/14 [0.0, 21.5] | 0.00 | 14/14 [78.5, 100] | 81.82 | n < 20 |
| Gemma parity | 15 | 1/15 [1.2, 29.8] | 4.55 | 12/15 [54.8, 93.0] | n.r. | n < 20 |
| full fresh160 | 5 | 1/5 [3.6, 62.4] | 21.25 | 4/5 [37.6, 96.4] | 64.38 | n < 20 |
| fresh160 my_spotlighting | 5 | 0/5 [0.0, 43.4] | 2.50 | 2/5 [11.8, 76.9] | 71.88 | n < 20 |
| builtin / custom | 5 / 5 | 0/5, 0/5 [0.0, 43.4] | 20.00 / 0.00 | 3/5, 3/5 | 50.00 | n < 20 |
| adaptive v1 / v2a / repair / v2b | 5 each | 1, 0, 0, 0 of 5 | 4.17 / 1.39 / 0 / 15.15 | 4, 4, 5, 3 of 5 | 58.33 / — / — / 66.67 | n < 20 |
| diagnostics g4 + raw | 6 | 1/6 [3.0, 56.4] | 8.00 | 4/6 | n.r. | n < 20 |
| sanity (no reference) | 9 | 0/9 | — | 6/9 | — | — |

## 7. Findings

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-menelaus29-ipi-multidomain-01 | [CC-07, #181/#161] 0 of 33 banking IT0/1/3 successes lack the GOAL datum in an executed attacker transfer; #161 n/a (0 UT5 logs) | expected-known (R2, CC-07; scope gap CC-09) | S3 | confirmed | `validity_defects` scope row with count 0; no re-score caveat on any banking ASR |
| PC-menelaus29-ipi-multidomain-02 | [CC-09] no `artefacts.toml` entry scopes this source; quirk counts verified | documentation-mismatch (CC-09) | S3 | confirmed | see CC-09; counts below |
| PC-menelaus29-ipi-multidomain-03 | Phase-10d census counts the single zero-message log as both with and without outcome (`incomplete_run.null_outcome_files` 0); its outcomes are null | documentation-mismatch (R4) | S3 | confirmed | route to the phase-10d census owner |
| PC-menelaus29-ipi-multidomain-04 | Identity disclosure: example log unresolved; 6 Gemini 3.6 sanity logs model unverifiable (logged label fixed at construction; run-time fallback possible); 22 built-in logs → Gemma 4 by table (class I) | expected-known (R2: profile line 9, `pipeline_name_policy`, D-104) | S3 | confirmed | disclose in the datasheet |
| PC-menelaus29-ipi-multidomain-05 | L1-03 escape/encoding residues in payload and tool content (#214 class); SEM marker in 85/85 sampled attacked runs; 34 `partial_payload` | expected-known (R2, prereg L1-03 note; scope gap CC-09) | S3 | confirmed | none; H14 population rate from the round |
| PC-menelaus29-ipi-multidomain-06 | Pre-registered context count 13 vs 11 stored (profile globs match 11) | documentation-mismatch (R4) | S3 | confirmed | post-check uses 11 |
| PC-menelaus29-ipi-multidomain-07 | H10 per-file commit-time test not runnable on the blobless clone (history trees absent) | analysis-artefact (R5) | S3 | confirmed | optional follow-up 2 |

No mapping defect, no source defect, no security finding. PC-02 is a reference to CC-09 and PC-07 is R5; neither counts in the readiness verdict. Verifier (2026-10-21): 7/7 confirmed, 0 refuted. Independent raw recount (broader matcher: attacker IBAN anywhere in args, either tool-call id field) gives the same 0/33 for #181 and 0 user_task_5 paths for #161. Corrections: PC-03's cause is the census.py key definitions (`empty_messages_with_outcome` counts every outcome-only unit; `null_outcome_files` cannot fire when a null outcome emits no judgement), so it is routed to the AgentDojo family owner as well, as a report only. PC-04's wording for the 6 Gemini 3.6 logs is now "model unverifiable": their in-log pipeline name equals the directory but cannot show the documented fallback. PC-05: the 34 class-D `aprov.a_label` statements are all `agentdojo.partial_payload@1` (in 10 executions). PC-06: 10 L1-10 context files + 1 L1-06 aux (`corpus.json`) = 11. PC-07: commits are present (80, 2026-07-25 .. 08-22) and the timestamp range lies inside them. Only the per-file test is blocked.

Proposed `artefacts.toml` entries (text only; route to the AgentDojo family owner):

```toml
# PC-01 (CC-07): extend agentdojo.art.validity_defects
#   scope.sources += "menelaus29-ipi-multidomain"; scope.profiles += "menelaus29-ipi-multidomain"
expected += [
  { snapshot = "menelaus29-ipi-multidomain:head", count = 0, unit = "executions", basis = "pre-check PC-menelaus29-ipi-multidomain-01: 33 banking IT0/1/3 security-true logs, all with the GOAL datum in an executed attacker transfer (#181); 0 user_task_5 logs (#161)", status = "proposed" },
]
# PC-02 (CC-09): add the source to the generic entries, rows status "proposed", basis "pre-check PC-menelaus29-ipi-multidomain-02":
#   benign_security_constant 70; injection_task_as_user 70; incomplete_run 1 and empty_log 1 (same v2a log);
#   silent_rerun 0 null-final, 858 with an unobservable earlier pass; naive_timestamp 858; payload escaping (#214) 190 logs
```

Items for AGENTS.md section 12:

- menelaus29 (CC-07): #181 biases none of the 33 banking IT0/1/3 successes (0/33). #161 does not apply (no `user_task_5`). All 19 author-reported arms reproduce exactly from the raw logs.

## 8. Recommendations and readiness

1. Route the PC-01 `validity_defects` row (count 0) and the PC-02 scope widening to the AgentDojo family owner (CC-07, CC-09). Route PC-03 to the phase-10d census owner and, for the `census.py` key definitions, to the AgentDojo family owner (report only).
2. Datasheet: disclose PC-04 (the identities of the 6 sanity logs and the 22 built-in logs rest on directory or table evidence only). Report the empty v2a log as outcome-less, not as a failure.
3. Do not exclude any data. Arms with 0 successes (Gemini baseline, custom, v2a_repair) stay in.

**Readiness: `ready-with-caveats` (verifier: confirmed).** The part imports correctly and deterministically: 144/144 mapped, validation 144/144, recompute 0 unexplained, j1/j2 byte-identical (594 files), judgements raw = mapped 288/288, 0 identity mismatches, 0 redaction hits. L1 outcomes equal the author reports in 19/19 arms. The caveats are disclosure only (PC-01, PC-04, PC-05) and none blocks the round. Not counted: PC-02 (CC-09 reference) and PC-07 (R5).

## 9. Reproduction

Batch: `tools/precheck/plans/wave3.toml` entry `menelaus29-ipi-multidomain` (`l1 = ["--git", "~/.agentprov/staging/10c/menelaus29/ipi-multidomain-agent-study.git"]`).

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave3 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave3.toml
```

Steps the batch ran (W = `~/.agentprov/migration-work/precheck/menelaus29-ipi-multidomain`, D = `docs/reports/precheck/data/menelaus29-ipi-multidomain`): `l1_scan.py --git …`, `l1_10`, `l2_sample.py select`, `l2_import.py --jobs 2` (j2), `--jobs 1` (j1), `l2_check.py --compare-with W/l2-head-j1.partial` (validate, recompute `--dry-run`, verify `--level chain`), as in the interbolt dossier section 9.

Examiner scripts (read-only; S = `D/exam-scripts`, outputs under `W/exam/`, copied to D):

```bash
uv run python -I S/pop.py W/exam/pop.json         # os1-population.json: arms, H1-H8, H12, H16, L1-08 labels
uv run python -I S/checker.py W/exam/checker.json # raw-census.json: CC-07 #181/#161, system-prompt digests (H15), trailing calls
uv run python -I S/os2.py W/exam/os2.json         # os2-sample.json: raw vs mapped, sample arms, H14, H15, class-D rules
grep -c menelaus src/agentprov/adapters/agentdojo/artefacts.toml   # PC-02: 0
```

Follow-ups for the orchestrator (not run):

| # | What | Command | When |
|---|---|---|---|
| 1 | Supplementary L2 (outside the committed sample, recorded as such) of the empty v2a log `data/adaptive/g4/v2a/results/raw/banking/google-gemma-4-26b-a4b-it [gemini-2.5-flash-preview-04-17]/banking/user_task_12/adaptive_b43850c62aa7/injection_task_4.json` (`incomplete`, `no_execution_observed`, `no_outcome_recorded`) | `tools/precheck/l2_import.py --source menelaus29-ipi-multidomain --part head --sample <one-label sample> --corpus W/l2-head-extra --jobs 2` through `tools/suite_queue.py --class import --cpu 2`, then `l2_check` | optional |
| 2 | H10 per-file timestamp vs adding-commit check (PC-07) needs a clone with history trees | network fetch: needs the orchestrator's and the user's yes | optional |
| 3 | H14 population marker rate on the 787 attacked logs | from the round's full import (`agentprov import menelaus29-ipi-multidomain …`) | round |
| 4 | Route PC-01/PC-02 rows (CC-07, CC-09) and PC-03 (census) | no command | before the round |
