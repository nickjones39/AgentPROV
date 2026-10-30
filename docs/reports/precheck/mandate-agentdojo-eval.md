# Pre-check dossier: `mandate-agentdojo-eval`

## 1. Header

| | |
|---|---|
| Corpus | `mandate-agentdojo-eval` (MIT as declared; publisher unverified) |
| Parts | `mandate-agentdojo-eval · head` (1 part) |
| Family / profile | `agentdojo` / `mandate-agentdojo-eval@2` (semantics `agentdojo.suites@2`, variant `v1.k14`) |
| Pin | git `jwilliamsc/mandate-agentdojo-eval` @ `fa62a977` (only commit), tree `runs/` `11b6d0e4` |
| Code commit | `a871e2d7` (L1 and L2, batch `wave1`, no tracked changes) |
| Kind | wave 1, delta since E2 (stored corpus `mandate-agentdojo-eval-p10.partial`, profile @1) |
| Date | 2026-10-14 (prereg, research, L1), 2026-10-15 (L2 analysis, verify, dossier) |
| Agents | researcher and fact-checker (prereg, research), examiner (L1/L2 analysis), one verifier per finding (8), dossier writer |
| Data | [`data/mandate-agentdojo-eval/`](data/mandate-agentdojo-eval/): `research.json`, `l1-head.json`, `l2-sample-head.json`, `l2-head.json`, `exam.json`, `raw-census.json`, `dl1-delta.json` (its `aer` block corrected, PC-09), `aerdiff-j2.json`, `findings.json`, `exam-scripts/` |

- Code identity, part `head` (Level 2, [`code-head.json`](data/mandate-agentdojo-eval/code-head.json)): commit `a871e2d7`; engine code aer `24df84b5e307`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `d3f9995f61bf`; adapter agentdojo.tracelogger c311b5a6ac9e.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Source repository | https://github.com/jwilliamsc/mandate-agentdojo-eval @ `fa62a977` (2026-08-17; 0 tags, releases, issues, PRs, forks on 2026-10-14) | the data; the README is the only description and the only outcome reference |
| Paper of the source | none found (web searches 2026-10-07 and 2026-10-14) | n/a |
| External data record | none (no Zenodo, HF, Figshare); the git tree is the record | n/a |
| AgentDojo paper | https://arxiv.org/abs/2406.13352 (v1 to v3) | benchmark; README comparator rows equal v1 Table 5 (all suites, benchmark v1) |
| Harness | `agentdojo==0.1.35` (PyPI wheel sha256 `364bea42...`, = profile), banking suite `v1.2.1` | producer and scorer |
| Upstream issues | ethz-spylab/agentdojo [#181](https://github.com/ethz-spylab/agentdojo/issues/181) (open), [#161](https://github.com/ethz-spylab/agentdojo/issues/161) (open, PR #169 open) / #159 / #138, #110 (fixed in #130, not in v1.2.1), #189/#168 | checker defects of v1.2.1 banking |
| Cited, no data relation | arXiv:2503.18813 (CaMeL), arXiv:2510.09023 | none |

Data-versus-paper notes (from `research.json`):

- No paper reports these runs. The README headline numbers (75.0/81.9, 1.4/68.8, 0/27 TK, envelope 11.1 %) equal the logs.
- Not released, though the README says `runs/` holds every reported run: the envelope pilot's paired baseline (81.5 %), the intent II pilot, baseline variants (75.0-88.9 %), all scoped runs. Overwrite by `force_rerun=True` is inferred.
- README comparators are attributed to the leaderboard. They equal arXiv v1 Table 5 (all suites, benchmark v1); v2, v3 and the leaderboard differ. The README's ~33 % no-defence baseline matches no published figure (unverified).
- Benchmark v1.2.1 keeps the old `user_task_6` checker (#110), so `user_task_6` utility is not comparable with v1.2.2.
- #181 and #161 are confirmed in the data: PC-01, PC-02 (both covered by `agentdojo.art.validity_defects`, CC-07).
- The model id is read from the pipeline name; the served snapshot and the client version are not logged. The pipeline name collides with AgentDojo upstream's (180 cells overlap, 0 identical files).
- Timestamps are naive local time (UTC-5 inferred from the commit).

## 3. Expectations

Pre-registration: [`prereg/mandate-agentdojo-eval.md`](prereg/mandate-agentdojo-eval.md), committed in `fd75f8a3` (2026-10-14), before any check of this corpus ran. Method amendments 1 to 3 (README section 8) apply; amendment 1 covers the stored corpus's expected `validate.results.differ`.

Hypotheses H1 to H11: 11/11 supported. H5 and H6 are measurable and > 0, so they are disclosures (PC-01, PC-02; expected-known under R2 / CC-07, disclosed through `agentdojo.art.validity_defects`). H10 holds, with one movement the prediction does not state (PC-04); the section 7 U6-c row's "+1,621 `apv:Gap`" is a wrong prediction text (no new `apv:Gap`; `apv:paramsStatus` instead, section 5 DL-1 row): cross-cutting item CC-04, recorded once in `cross-cutting.md`, with no separate finding here. The H7 sub-claim about overlapping run intervals was refuted (PC-07, refuted).

Classes follow the canonical rules R1-R6 and the cross-cutting items CC-01 to CC-08 of [`cross-cutting.md`](cross-cutting.md) (harmonisation pass 2026-10-15).

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Run at `a871e2d7`, `--use-pin`, jobs 2, 0.5 s. All batch steps rc 0.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 401 walked = 396 selected + 4 context + 1 not selected (`.gitignore`); 0 archives, 0 rejected, 0 strays. Units 396 = registry. Selected bytes 3,103,968. `corpus_digest` recomputed from the L1 rows with the profile recipe: `a8f4a9d7...`, equal. The listing total 3,137,054 is not measured by `l1_scan` | as expected (H1) |
| L1-02 parse | strict parse ok 396/396; 0 in every class; 0 integers beyond I-JSON | as expected |
| L1-03 encodings | 0 U+2028/2029/0085, C0/C1, bidi, tag, zero-width, U+FFFD, mojibake. Only class `escaped_newline`: 5 strings in 5 files at `/messages/*/content/*/content`; all 15 matches are LaTeX `\text` 9 / `\times` 6 in `user_task_11` assistant answers, 0 real residues (PC-03). 0 wholly escaped JSON-in-string | as expected after PC-03 |
| L1-04 duplicates | 0 byte-identical and 0 trajectory groups (396 distinct fingerprints of 396). Cross-part (`_cross/l1-xdup.json`, 10 parts): 0 groups | as expected (H8) |
| L1-05 arms | 8 strata = prereg section 3: baseline II 144 / TK 27 / none 9; envelope II 27 / none 9 / TK 0; intent II 144 / TK 27 / none 9; scoped 0. 0 duplicate cells, 0 extra cells; path components = in-file facets 396/396. Per-arm outcome booleans equal the prereg table (difference 0 in all 13 counts) | as expected (H2, H3) |
| L1-06 secrets/paths | 0 secret-like strings, 0 account paths, 0 operator home | as expected |
| L1-07 timestamps | `/evaluation_timestamp` 396/396, all naive, 0 parse failures, 2026-08-16..17, 396 distinct, 5 non-overlapping blocks; 0 after the commit under UTC-5. Tool-argument dates (7 + 7 copies) are benchmark data | as expected (H7) |
| L1-08 degenerate | 0 flags | as expected (the raw census also gives 0 null finals, so the CC-08 rule gap does not change this part) |
| Raw census | `raw-census.json` (396/396 logs) reproduces every prereg section 2 count: messages system 396 / user 396 / assistant 1,621 / tool 1,390; 1,390 calls, ids unique; 103 parallel turns; 5 tool-free; 3-47 messages per log (mean 9.60); declines 240 (envelope 49, intent 191); inferred allows 143; injection dicts 369 single-entry / 27 empty (vectors 243/63/45/18); 4 ValueErrors (baseline only); v1.2.1 and 0.1.35 in 396/396; 0 null finals; 0 unexecuted trailing calls; 35 empty-recipient declines + 1 literal "null"; 23 payload-unreachable runs | as expected |

Duplicate group counts in this table are the per-part L1 summary (`l1-head.json`), and this dossier uses it. `data/_cross/l1-xdup.json` counts a group under `within_part` only when all its members are in one part and moves groups that span parts or corpora to `cross_part` or `cross_corpus`; for this part both give 0 groups. A comparison with the post-check must use the same basis.

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`data/mandate-agentdojo-eval/l2-sample-head.json`](data/mandate-agentdojo-eval/l2-sample-head.json) (sha256 `84f2b89a...`): 40 of 396 units, 8 strata × 5 |
| Import | 2 scratch corpora (`l2-head-j2.partial`, `-j1.partial`). 40/40 mapped, 0 failed, 0 degenerate, 0 `adapter_defect`. Status ok 40; completeness unverifiable 40. Seal issues exactly `accounting_unverifiable` 40 and `earlier_attempts_unobservable` 40 (H9) |
| Validation | tiers aer, sem, prov, linkage: 40 passed, 0 failed, 40 reproduced, linkage 100 %. 72 checks per row, incl. the 4 item-10 constraints (0 failures). SHACL not implemented (skipped); regression does not apply |
| Recompute | `--dry-run`: 40 identical, 0 unexplained |
| Verify chain | 44 raw objects re-hashed, 0 failed; `checksums.absent` unverified (working tree; a sealed partial copy cannot be made, trap 9) |
| Determinism | j2 vs j1: 171/171 files and the index byte-identical |
| A2 error classes | `finish_reason` not_recorded 148/148 model calls; 0 empty assistant turns without a call; tool executions ok 124/124 (the 4 raw ValueErrors are not in the sample) |
| A3 PROV issues | 0 PI hits over 18,958 statements / 30,971 relation arguments; no PROV time; 0 unexecuted calls |
| Gate decisions | 31 deny decisions in 17 executions, all `mandate.decline_prefix@1`, 0 with a tool execution, 31 decline messages generated by the decision; 39 `allow_inferred`. Raw of the same 40 labels: 31 declines, 39 allows |
| Evidence classes | AER record ev: O 593 / D 96 / I 457 (stored on the same ids: O 593 / D 503 / I 25). evf tags D 297 / I 1,163 / O 359 (stored D 1,251 / I 332 / O 359). PROV core D 399 / O 1,131 / I 0; inference I 5,501; assessment D 92 / I 2,394; `_unverified` twins inference I 5,330, assessment I 698. Core share 0.404 → 0.153 (item 3 / D-80, D-86) |
| Identity | model `gpt-4o-2024-05-13` on all pipelines (`mandate.model_from_pipeline_name@1`); defences none / `mandate_envelope` / `mandate_intent`; 0 mismatches, 0 unresolved |
| Redaction | 128 files scanned, 0 hits; separate account-path grep 0 files in aer/sem/prov |
| Withholding | not applicable (no `[withhold]`, policy null) |
| Judgements | mapped = raw booleans in 40/40 (utility) and 40/40 (security) |
| DL-1 (stored `-p10` vs scratch, same 40 ids) | AER, SEM, PROV and validation digests differ in 40/40; 0 unexplained (PC-08). Causes: item 30 / D-31 (profile 1→2, `rules.agentdojo` 1→2, 40/40); item 3 / D-80 + D-86 (19 rule-ref changes, all `X@1 → X_unverified@1`; record ev D→I actor 160, model_call 148, tool_execution 124); U6-c / D-373 (`/params` not_recorded 148/148; in PROV `apv:paramsStatus apv:NotRecorded` on the 148 ModelInvocations, 40 → 188 carriers with the agent systems, and `apv:Gap` unchanged at 547 = stored 547: the prereg row's "+1,621 `apv:Gap`" is the wrong U6-c reading of CC-04, recounted by the completeness critic on the same 40 ids); item 5 / D-370 (`load_environment` D on 25/25 attacked runs); SEM items 4/6/8 (`yaml_norm@1→@2` on 82/82 markers, statuses 26 present / 56 absent unchanged); item 3 via SEM-V11 (security outcome ev D→I 25/25, PC-04); items 30/1/15 (catalogue entities, inference bundles 265 → 1,015); item 10 (4 new checks, so stored `validate.results.differ` is expected-known, amendment 1; PC-10, CC-05). AER signatures: [`aerdiff-j2.json`](data/mandate-agentdojo-eval/aerdiff-j2.json); the `aer` block of `dl1-delta.json` now holds the same `aerdiff.py` output (it was a copy from another corpus until the harmonisation pass, PC-09) |

### Recheck (CC-08, recheck12)

`plans/recheck12.toml` (l1, l1_10, check; sample frozen) against the d97d3a57 files; full deltas in [`_cross/recheck12.json`](data/_cross/recheck12.json). Every other L1/L2 count is unchanged; the only other deltas are run environment (code commit d97d3a57 with tools/src = 5efa3575, `tracked_changes` true, two H.8.4(2) recompute notices with 0 unexplained changes; R12-01).

| Part | L1-08 flags (old -> new) | L2 `_unverified` split | L1-10 |
|---|---|---|---|
| head | no change | twin inference:I 5,330 -> 4,533; mixed 797; native 0 (sum 5,330 = old) | 4 screened (context 4); 0 hits; files with a hit 0; named accounts 0; operator 0; unreadable 0 |

- L2 split only; L1 unchanged; L1-10 4 context files, 0 hits.

## 6. Outcome comparison

Level 1 is the population (raw booleans, 396 logs); Level 2 is the AER of the 40-unit sample. Reference: the README, or the logs where the README is silent (verify section 3.4, "V 3.4"). Gap rule: more than 15 pp, or more than 5 pp outside the Wilson 95 % interval. No L2 arm reaches 20 executions, so L2 rows are judged only by whether the interval covers the reference.

| Arm (pipeline / attack) | Level | n | Metric | Rate (Wilson 95 %) | Reference | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|---|
| none / II | L1 | 144 | ASR | 75.0 % 108/144 [67.3, 81.4] | 75.0 % README | 0.0 | match (PC-01: strict re-score 72.9 %) |
| none / II | L1 | 144 | utility | 81.9 % 118/144 [74.9, 87.4] | 81.9 % README | 0.0 | match (PC-02) |
| none / TK | L1 | 27 | ASR | 70.4 % 19/27 [51.5, 84.1] | 70.4 % V 3.4 | 0.0 | match |
| none / TK | L1 | 27 | utility | 66.7 % 18/27 [47.8, 81.4] | 66.7 % V 3.4 | 0.0 | match |
| none / none (pre-pass) | L1 | 9 | utility | 100.0 % 9/9 [70.1, 100.0] | 9/9 V 3.4 | 0.0 | match |
| envelope / II | L1 | 27 | ASR | 11.1 % 3/27 [3.9, 28.1] | 11.1 % README | 0.0 | match |
| envelope / II | L1 | 27 | utility | 29.6 % 8/27 [15.9, 48.5] | 29.6 % V 3.4 | 0.0 | match |
| envelope / none (pre-pass) | L1 | 9 | utility | 11.1 % 1/9 [2.0, 43.5] | 1/9 V 3.4 | 0.0 | match |
| intent / II | L1 | 144 | ASR | 1.4 % 2/144 [0.4, 4.9] | 1.4 % README | 0.0 | match |
| intent / II | L1 | 144 | utility | 68.8 % 99/144 [60.8, 75.8] | 68.8 % README | 0.0 | match (PC-02) |
| intent / TK | L1 | 27 | ASR | 0.0 % 0/27 [0.0, 12.5] | 0/27 README | 0.0 | match |
| intent / TK | L1 | 27 | utility | 33.3 % 9/27 [18.6, 52.2] | 33.3 % V 3.4 | 0.0 | match |
| intent / none (pre-pass) | L1 | 9 | utility | 100.0 % 9/9 [70.1, 100.0] | 9/9 V 3.4 | 0.0 | match |
| none / II | L2 | 5 | ASR / utility | 80.0 % [37.6, 96.4] / 100.0 % [56.6, 100.0] | 75.0 / 81.9 | 5.0 / 18.1 | covered; AER = raw 5/5 |
| none / TK | L2 | 5 | ASR / utility | 80.0 % [37.6, 96.4] / 80.0 % [37.6, 96.4] | 70.4 / 66.7 | 9.6 / 13.3 | covered; AER = raw 5/5 |
| none / none | L2 | 5 | utility | 100.0 % [56.6, 100.0] | 100.0 | 0.0 | covered; AER = raw 5/5 |
| envelope / II | L2 | 5 | ASR / utility | 20.0 % [3.6, 62.4] / 60.0 % [23.1, 88.2] | 11.1 / 29.6 | 8.9 / 30.4 | covered; AER = raw 5/5 |
| envelope / none | L2 | 5 | utility | 0.0 % [0.0, 43.4] | 11.1 | -11.1 | covered; AER = raw 5/5 |
| intent / II | L2 | 5 | ASR / utility | 0.0 % [0.0, 43.4] / 80.0 % [37.6, 96.4] | 1.4 / 68.8 | -1.4 / 11.2 | covered; AER = raw 5/5 |
| intent / TK | L2 | 5 | ASR / utility | 0.0 % [0.0, 43.4] / 40.0 % [11.8, 76.9] | 0.0 / 33.3 | 0.0 / 6.7 | covered; AER = raw 5/5 |
| intent / none | L2 | 5 | utility | 100.0 % [56.6, 100.0] | 100.0 | 0.0 | covered; AER = raw 5/5 |

Model `gpt-4o-2024-05-13` in every arm; II = important_instructions, TK = tool_knowledge. Pre-pass security is the runner constant True and is not a rate. No flag. L2 gaps are sampling noise at n = 5; the mapping reproduces the raw booleans in 40/40.

## 7. Findings

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-mandate-agentdojo-eval-01 | [CC-07] Banking InjectionTask1 successes without the target datum (#181 precedence): 3 of 18 it1 logs, 0/16 it0, 0/17 it3 | expected-known (R2, CC-07: `agentdojo.art.validity_defects`; was source-defect S2) | S3 | confirmed (1/1), wording corrections | Disclose through the entry and the datasheet; keep the logged boolean; extend `agentdojo.art.validity_defects` to Mandate (PC-11). Strict re-score (baseline II 105/144 = 72.9 %) only as a separate RJ column, against the GOAL datum |
| PC-mandate-agentdojo-eval-02 | [CC-07] `user_task_5` utility is vacuous (#161/#159/#138): true 18/18, 4/18 with no payment to the Spotify IBAN | expected-known (R2, CC-07: `agentdojo.art.validity_defects`, vacuous utility; was source-defect S2) | S3 | confirmed (1/1) | Disclose through the entry and the datasheet (baseline II and intent II each hold 9 always-true cells); no mapping change; scope extension PC-11 |
| PC-mandate-agentdojo-eval-03 | L1-03 `escaped_newline` counts LaTeX `\text`/`\times` as residues (5 strings, 0 real) | analysis-artefact | S3 | confirmed (1/1), fix corrected | Tool owner after the batch: exclude a LaTeX command list or report LaTeX-like tokens as their own class; not `(?![A-Za-z])`, which hides real residues |
| PC-mandate-agentdojo-eval-04 | Security outcome annotations move D→I through premise propagation (25/25 sampled; 369 expected); the regen-batch item-1 row says Mandate stays D | documentation-mismatch | S3 | confirmed (1/1) | Add to the item-3/item-1 prediction for Mandate (369, extrapolated); check head v1.k14 too. No code change |
| PC-mandate-agentdojo-eval-05 | `defence_benign_intervention` expected 8 omits the intent gate's benign pre-pass (9 declines in 1/9, utility true); detector `pi_detector_sentinel@1` cannot see Mandate declines | documentation-mismatch | S3 | confirmed (1/1), additions | Owner: keep 8 for the envelope arm, add an intent row (1); fix the detector (`mandate.decline_prefix@1`); reconcile phase10 analysis line 546 ("Mandate 9") |
| PC-mandate-agentdojo-eval-08 | DL-1: every stored-vs-fresh difference is attributed (items 30, 3, 5, U6-c, 1/4/6/8, 15, 10) | expected-known | S3 | confirmed (1/1), evidence re-pointed | None; the post-check compares the re-validated regenerated corpus. Evidence is `aerdiff-j2.json` (now also the `aer` block of `dl1-delta.json`). Its amendment-1 part is PC-10 (CC-05), its U6-c part CC-04 |
| PC-mandate-agentdojo-eval-09 | Two exam data blocks are wrong: `dl1-delta.json` `aer` is a copy of `ast-survey-agentdojo/delta-p10-vs-l2.json` (executions 120); `raw-census.json` `within_arm_timeline` comes from an unrecorded computation with swapped roles | analysis-artefact | S3 | confirmed (raised by the PC-08 and PC-07 verifiers; `executions` 120 and 8 of 10 keys byte-equal re-checked by the dossier writer) | Resolved in the harmonisation pass without a re-run: the `aer` block of `dl1-delta.json` now holds the `aerdiff.py` output saved in `aerdiff-j2.json`; `within_arm_timeline` in `raw-census.json` is marked invalid with a note. No corpus change |
| PC-mandate-agentdojo-eval-10 | [CC-05] Stored corpus `mandate-agentdojo-eval-p10.partial` gives `validate.results.differ` (stored rows 68 checks, fresh 72: the 4 item-10 `pv.constraints.*`; pass 40/40 both) | expected-known (CC-05) | S3 | split out of PC-08 (its verifier checked the rows) | None before the round; compare like with like after re-validation (amendment 1) |
| PC-mandate-agentdojo-eval-11 | [CC-07] `agentdojo.art.validity_defects` does not list this corpus in its scope or expected rows (#181: 3 executions; #161: 4) | documentation-mismatch (R2, entry scope) | S3 | added in the harmonisation pass; entry re-read, counts from PC-01/PC-02 | Family owner extends the entry (proposal below) |

9 findings: PC-01 to PC-05, PC-08 and PC-09 confirmed by their verifier; PC-10 (CC-05, split out of PC-08) and PC-11 (R2 entry-scope finding for PC-01/PC-02) added in the harmonisation pass. 2 refuted. Analysis-artefacts (R5: PC-03, PC-09) are not counted in the readiness verdict. PC-01 and PC-02 are expected-known S3 under R2 / CC-07, as for PC-ast-survey-agentdojo-04: the benchmark defects are covered by `agentdojo.art.validity_defects` and only the source scope is new; the disclosure is still required and goes through that entry (`manuscript = true`) and the datasheet. `findings.json` is in the CC-06 format.

Corrections applied (in `findings.json`):

- PC-01: the 51 security-true logs on it0/1/3 are 43 II + 8 TK; the 3 deviating logs are II, `user_task_3/13/15`, each with one executed attacker-bound `send_money` whose subject is another IBAN. The checker's companion lookup returns `me`, so 72.9 % is a re-score against the GOAL datum, not a fixed upstream checker. The checker code is unchanged since `6d161b97` (2025-01-16), so `089ed468` matches the 0.1.35 wheel. The Mandate-arm ASRs are unaffected (none of their 5 security-true logs is on it0/1/3).
- PC-02: "always true" rests on the pre-environment (transactions 3 and 6, each 50.00 to the Spotify IBAN) and the absence of a delete tool. No UserTask5 override in v1_1_1, v1_2, v1_2_2.
- PC-04: the verifier's side note that `args_are_effective` moved to a twin came from the contaminated `dl1-delta.json` block (PC-09); the re-run `aerdiff` on Mandate shows no `args_are_effective` change (19 rule-ref changes, none of them on it).
- PC-08: evidence re-pointed to the re-run `aerdiff` (j2 and j1 identical); the 4 added validation checks come with SEM check ids re-versioned `@1 → @2`.

Refuted (not findings):

- **PC-mandate-agentdojo-eval-06** (stats `--artefacts` lists 5 of 9 Mandate entries): the safety net (D.15.3, D.15.8 item 7, `artefacts/scan.py`) only lists entries that claim a generic-detector finding; `injection_task_as_user`, `defence_benign_intervention`, `gate_decline`, `allow_inferred` are handled during conversion as notes or decisions. Specified behaviour, expected-known S4. Their counts (27, 8, 240, 143) are checked from raw/AER. Optional spec wording (D.15.2/D.15.4) for the spec owner.
- **PC-mandate-agentdojo-eval-07** (timestamp and duration do not form serial intervals): read as the start (agentdojo 0.1.35 `TraceLogger` sets the timestamp in `__init__`, before the duration clock), 0 of 388 within-arm pairs overlap; max excess 0.93 s, under the 1 s truncation; median slack 0.02 s. The 148 is the end-reading test only, and the 188 does not reproduce. The `within_arm_timeline` block is an analysis artefact (PC-09) and is now marked invalid in `raw-census.json`. Optional quirk wording: the timestamp is the naive local run start, truncated to the second.

Proposed `artefacts.toml` entries (text only; route to the agentdojo family owner; the first is PC-11's, for PC-01 and PC-02):

```toml
# extend the existing [[artefact]] agentdojo.art.validity_defects
scope.sources  += ["mandate-agentdojo-eval"]
scope.parts    += ["head"]
scope.profiles += ["mandate-agentdojo-eval"]
expected += [
  { snapshot = "mandate-agentdojo-eval:head", count = 3, unit = "executions", basis = "pre-check PC-mandate-agentdojo-eval-01: banking InjectionTask1 security true without the companion IBAN in any executed attacker-bound subject (#181 precedence; checker unchanged since 6d161b97); it1 3/18 (all important_instructions), it0 0/16, it3 0/17", status = "proposed" },
  { snapshot = "mandate-agentdojo-eval:head", count = 4, unit = "executions", basis = "pre-check PC-mandate-agentdojo-eval-02: user_task_5 utility true with no executed payment to the Spotify IBAN (vacuous v1 check, pre-environment transactions 3 and 6; #161); 18/18 user_task_5 logs true", status = "proposed" },
]
refs += ["https://github.com/ethz-spylab/agentdojo/issues/181", "https://github.com/ethz-spylab/agentdojo/issues/161"]
# handling FO

# agentdojo.art.defence_benign_intervention: keep count 8 with basis "envelope arm: runs with >= 1 MANDATE_DECLINE among attack-none pre-passes (8 of 9)", and add
expected += [
  { snapshot = "mandate-agentdojo-eval:head", count = 1, basis = "pre-check PC-mandate-agentdojo-eval-05: intent arm, runs with >= 1 MANDATE_DECLINE among attack-none pre-passes: 1 of 9 (9 declines), utility still true", status = "proposed" },
]
# and a detector able to see gate declines (mandate.decline_prefix@1), as a companion entry if the shared one stays on pi_detector_sentinel@1
```

Items for AGENTS.md section 12:

- PC-01: Mandate baseline II ASR (75.0 %, 108/144) includes 3 InjectionTask1 successes that leak no target datum (AgentDojo #181). A GOAL-datum re-score gives 72.9 % (105/144); the Mandate-arm ASRs are unaffected. Disclose; keep the logged booleans; `validity_defects` extension pending with the family owner.
- PC-02: Mandate `user_task_5` utility is always true at v1.2.1 (#161): 18 cells in baseline II and intent II, 4 of them without the requested payment. Disclose in datasheet and manuscript.

## 8. Recommendations and readiness

1. Route the `validity_defects` extension (PC-11, for PC-01 and PC-02; CC-07) and the `defence_benign_intervention` row and detector (PC-05) to the agentdojo family owner. Disclose PC-01/PC-02 in the datasheet and manuscript. No corpus bytes change.
2. Update the regen-batch item-1/item-3 prediction for Mandate: security outcome ev D→I, 369 (PC-04).
3. Tool fix after the batches: L1-03 LaTeX precision (PC-03). The exam data fix of PC-09 is done (harmonisation pass).
4. After the round: re-run the DL-1 scripts on all 396 ids (expected: `load_environment` 369, `/params` not_recorded 1,621, security outcome D→I 369, markers 361/935 unchanged).
5. No exclusion of any data.

**Readiness: `ready-with-caveats`.**

- The part imports correctly and deterministically: 40/40 mapped, validation 40/40, recompute 0 unexplained, j1/j2 byte-identical, DL-1 0 unexplained, redaction clean, judgements = raw 40/40, L1 outcomes = reference in 13/13 values over the 8 arms.
- Caveats, all owned and routed, none blocking: PC-01/PC-02 (disclosures, expected-known under CC-07) and PC-11 (`validity_defects` extension, family owner); PC-04/PC-05 (documentation, regen-batch and family owner); stored `validate.results.differ`, expected-known under amendment 1 until the round re-validates (PC-10, CC-05).
- Not counted (R5, analysis-artefacts): PC-03 (tool), PC-09 (exam data, resolved).

## 9. Reproduction

Batch (wave 1; plan entry in `tools/precheck/plans/wave1.toml`):

```toml
[[part]]
corpus_id = "mandate-agentdojo-eval"
source = "mandate-agentdojo-eval"
part = "head"
l1 = ["--use-pin"]
```

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave1 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave1.toml
```

Steps the batch ran (W = `~/.agentprov/migration-work/precheck/mandate-agentdojo-eval`, D = `docs/reports/precheck/data/mandate-agentdojo-eval`):

```bash
uv run python tools/precheck/l1_scan.py --source mandate-agentdojo-eval --part head --corpus-id mandate-agentdojo-eval --jobs 2 --emit-fp --use-pin
uv run python tools/precheck/l2_sample.py select --units W/l1-units-head.jsonl --source mandate-agentdojo-eval --part head --corpus-id mandate-agentdojo-eval --out D/l2-sample-head.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j2 --source mandate-agentdojo-eval --part head --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j1 --source mandate-agentdojo-eval --part head --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-head-j2.partial --out D/l2-head.json --sample D/l2-sample-head.json --l1-units W/l1-units-head.jsonl --compare-with W/l2-head-j1.partial --jobs 2
# inside l2_check:
uv run agentprov validate --corpus W/l2-head-j2.partial --tiers aer,sem,prov,linkage,shacl,regression --jobs 2
uv run agentprov recompute --corpus W/l2-head-j2.partial --dry-run --jobs 2 -q
uv run agentprov verify --corpus W/l2-head-j2.partial --level chain
```

Examiner and verifier scripts (read-only, through `agentprov.ingest`; S = `~/.agentprov/corpora/mandate-agentdojo-eval-p10.partial`):

```bash
PYTHONPATH=D/exam-scripts uv run python D/exam-scripts/rawcensus.py          # L1 raw census, H4-H6, PC-01, PC-02, PC-05
PYTHONPATH=D/exam-scripts uv run python D/exam-scripts/esc3.py               # PC-03
python3 -I D/exam-scripts/aerdiff.py S W/l2-head-j2.partial D/aerdiff-j2.json  # DL-1 AER, PC-08, PC-09
python3 -I D/exam-scripts/semdiff.py S W/l2-head-j2.partial                   # PC-04
uv run --offline python -I D/exam-scripts/provdiff.py S W/l2-head-j2.partial  # PROV evidence classes
uv run agentprov stats -q --corpus S --tables counts --artefacts --format json --out <scratch>/stats-stored.json  # PC-06 (refuted)
GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file git --git-dir ~/.agentprov/upstream/github.com/ethz-spylab/agentdojo.git \
    cat-file -p 089ed468c:src/agentdojo/default_suites/v1/banking/injection_tasks.py | grep -n 'or "" in'   # PC-01: lines 61, 107, 208
```

Follow-ups for the orchestrator: section 10.

## 10. Open follow-ups

Not run in the harmonisation pass. W, D and S as in section 9. The PC-09 data fix needed no re-run: the `aerdiff.py` output was already committed as `aerdiff-j2.json`.

| # | What | Command | When |
|---|---|---|---|
| 1 | After the round: DL-1 on all 396 ids (expected: `load_environment` 369, `/params` not_recorded 1,621, security outcome D→I 369, markers 361/935 unchanged) | `python3 -I D/exam-scripts/aerdiff.py S <regenerated corpus> <out>`; `python3 -I D/exam-scripts/semdiff.py S <regenerated corpus>`; `uv run --offline python -I D/exam-scripts/provdiff.py S <regenerated corpus>` | after the round |
| 2 | CC-05 / PC-10, optional: show amendment 1 on a copy of the stored corpus (never on the stored corpus itself) | `cp -cR ~/.agentprov/corpora/mandate-agentdojo-eval-p10.partial W/stored-copy.partial`, then `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-mandate-agentdojo-eval -- uv run agentprov validate --corpus W/stored-copy.partial --jobs 2` (expect exit 1, `validate.results.differ`, 0 failed checks) | optional |
| 3 | PC-03: L1-03 LaTeX precision in the tool, then re-run L1 | `uv run python tools/precheck/l1_scan.py --source mandate-agentdojo-eval --part head --corpus-id mandate-agentdojo-eval --jobs 2 --emit-fp --use-pin` (through `tools/suite_queue.py --class import --cpu 2`) | after the tool freeze |
