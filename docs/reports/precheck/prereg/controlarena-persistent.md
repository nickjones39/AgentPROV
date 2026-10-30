# Pre-registration: `controlarena-persistent`

| | |
|---|---|
| Corpus | `controlarena-persistent` (family `inspect`, profile `controlarena-persistent` v2, dialect/mapper `inspect.eval`, registry `planned`, no semantics profile) |
| Parts | `zip-3-001`, `zip-3-002`, `zip-3-003` (split-zip pins, D-249), `batch-runs`, `auditor` (tar.zst). All five are HF `idacy/control-arena-persistent-state-eval-archive-2026-07-30` @ `84d39e0a485d7ea6ca10f4ceb2a3fbf88dab0e62` |
| Wave | 4 (full pre-check). Not in FA or E2, so there is no E2 delta. §8 gives the movement since phase-10p trial t1 instead |
| Code commit | `065b0d36` or later |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Inputs: our own reports (phase-10p README and census `aggregate.json`/`held_labels.json`, trial t1 register counts, profile, DECISIONS, regen-batch, review-core-d) and desk research (`data/controlarena-persistent/research.json`). No raw log was read and nothing was computed from raw bytes |

## 1. Sources (details and URLs in `research.json`)

- **Paper.** Hills, Caspary and Cooper Stickland, *Distributed Attacks in Persistent-State AI Control*, arXiv:2607.02514. v1 is dated 2026-07-02 and v2 2026-07-08, both CC BY 4.0. Tables 3, 4, 5, 7, 11, 14, 16, 18 and 21 and every n are identical in v1 and v2. **[corrected]** The abstract is *not* identical: one sentence on monitor models was reworded in v2, and two introduction figures changed (trajectory evasion 76% vs 66% → 81% vs 65%; GPT-5.3-Codex 31% → 27%); Table 8 was restructured (v1 GPT-4o τ4, v2 τ6). Inside v2, the GPT-4o full-diffs threshold reads τ7 in Tables 6 and 7 but 6 in Table 9, and Table 9's positional evasion (84.5%) differs from Table 7's (98.2%). **[corrected]** The "below the threshold" wording is in §1 (Introduction), not §3.2; the operational definition (App. A.2 text, Table 5 and Table 16 captions) is detected iff score > τ, i.e. evaded iff score ≤ τ.
- **Data record.** The HF pin is the current head: one day of 27 commits on 2026-07-30, no later revision. All 21 pinned files match the HF tree by size and LFS sha256 (checked 2026-10-14). The card describes the archive as the author's **local-only residue**. Data that already existed in other HF repositories was not re-uploaded. Those sibling repositories (`control-arena-persistent-state-eval-logs-2026-05-23`: 4,338 `.eval`; `control-arena-runs`: 7,123; and others) have no licence.
- **Code.** <https://github.com/josh-hills/control-arena-persistent-state-eval> (issues disabled; 42 PRs, 2 open) is an MIT fork of UKGovernmentBEIS/control-arena, with main at `68de4a36` (2026-06-23). The logs record 12 abbreviated `eval.revision` commits. Ten of them resolve, dated 2026-01-09 to 2026-04-21. `fe882288` and `59859463` do not exist in the public repo. Monitor-score fixes merged after the code of most logs:
  - PR #30 (2026-02-12) fixed history modes overwriting each other under `score_pr_diff`.
  - PR #41 (2026-06-19) added a clamped score parser and per-mode aggregation.
  
  The repo README says the logs are in `logs/`, but main has no `logs/` path and no `.eval` file (it does have `paper/` with `main.tex`/`main.pdf`; **[corrected]** research.json had said `paper/` was absent).
- **Harness.** inspect_ai 0.3.159 (log v2) in all 1,364 header logs. It writes `ScoreEvent` without `scorer` (CD-24). The control_arena fork version is not logged.
- **Licence.** MIT (card front matter; no LICENSE file). Policy include. D-344 withholds every execution at a release seal.

## 2. Expected counts

| Quantity | zip-3-001 | zip-3-002 | zip-3-003 | batch-runs | auditor | Source |
|---|---:|---:|---:|---:|---:|---|
| Container bytes | 2,147,474,457 (8 parts) | 2,147,478,676 (8) | 781,063,343 (3) | 885,551,965 | 22,039,676 | profile pins; HF tree |
| Members (direct / nested) | 1,627 / 1,380 | 654 / 2,069 | 620 / – | 778 | 251 | census `members.by_container` |
| Direct `.eval` | 285 | 70 | 334 | 110 | 1 (selected) | phase-10p §3.1 |
| … original / byte-dup / no-header | 132 / 0 / 0 | 31 / 0 / 1 | 162 / 5 / 0 | 110 / 0 / 0 | 1 / 0 / 0 | census `log_class@…` |
| … empty + truncated (358 in all: 172 + 186) | 153 | 38 | 167 | 0 | 0 | census; profile quirk |
| Nested zips (D-382) | 4: `gradual_f3m1` 120 logs, `2026-01-15_last-two-days` 126, `honest_all` 173, `run_2` 1 | 1: `positional_f3m1` 535 | – | – | – | census rows |
| Nested logs original / partial / no-hdr / byte-dup | 410 / 3 / 7 / 0 | 515 / 0 / 0 / 20 | – | – | – | census |
| Original samples (census order) | 660 + 1,963 + 13 = 2,636 | 153 + 1,499 = 1,652 | 810 | 638 | 6 | census `sample_class` |
| Held, `select.redaction_pending` (D-345) | 30 logs / 195 samples (2 direct, 28 nested) | 6 logs / 25 samples (+1 unfinished) | 0 | 0 | 0 | `held_labels.json`; profile v2 |
| **Executions (trial t1 order)** | **2,441** | **1,698** | **739** (derived) | **638** | **6** | phase-10p §9; zip-3-003 = 5,522 − the others |
| Registry/README figure (stale) | 660 | 153 | 810 | 638 | 6 | `tools/readme_corpora.toml` ("nested zips not yet read") |

- **Corpus totals.**
  - Source: 5,742 samples in 1,364 logs.
  - Executions: 5,522 (= 5,742 − 220 held).
  - Register: `select.redaction_pending` 36, `select.dialect_planned` 8, `ingest.archive.format` 189, `dedup.collapsed` 265 (trial t1).
  - 152 logs have `eval.model` none/none.
  - 26 logs have status `error`.
  - Error events in 123 samples; `sample_limit` events in 445; tool calls in 5,679 of 5,729 samples.
- **Census order and import order.** In census order, zip-3-002 has 1,627 executions and zip-3-003 has 810. In import order they have 1,698 and 739. The 71-sample shift equals the 71 samples of the 15 header-bearing byte-duplicate logs in `positional_f3m1.zip` (H4).
- **L2 sample.**
  - Strata are experiment × untrusted × `eval.metadata.mode`, with mode presence unknown. Damaged members form no-header strata.
  - zip-3-001 has about 15–20 strata, giving 60–100 units.
  - zip-3-002 has about 10, giving 40–50.
  - zip-3-003 has about 9, giving 30–45.
  - batch-runs falls back to the 30-unit minimum, because its experiment facet is `batch_runs` only.
  - auditor contributes its single unit.
  - `l2_sample.py` fixes the exact lists. These ranges are estimates, not checks.

## 3. Expected arms (L1-05)

| Arm (experiment) | Part(s) | Untrusted / trusted | Logs (samples) | Side tasks (samples) | Paper status |
|---|---|---|---:|---|---|
| `gradual_f3m1` (M1, future-visibility 3) | 001 nested (+5 byte dup in 003) | Sonnet 4.5 / GPT-4o | 120 (600) | triggered-exfil 300, config-telemetry 300 | **CLI gradual, n = 120** (Tables 3, 4, 7, 11) |
| `positional_f3m1` | 002 nested | Sonnet 4.5 / GPT-4o | 515 (1,499) + 20 byte dup | config-telemetry 753, triggered-exfil 746 | CLI positional raw, paper n = 600 (85 short) |
| `honest_all` | 001 nested | Sonnet 4.5 / GPT-4o | 166 (796) + 7 no-hdr **[corrected: the 3 partial-overlap logs are in `2026-01-15_last-two-days.zip`, census `log_rows`; phase-10p README l. 69 misattributes them]** | none | honest calibration, paper n = 308 / 167 / 155 |
| `M1F3_main_run3` | 001 / 002 / 003: 95 / 16 / 9 | Sonnet 4.5 / GPT-4o | 120 (600) | secret-exfil, malicious-package, triggered-exfil (about 200 each) | not reported (Table 12 excludes 2 of these side tasks) |
| `F2M1_gradual_max_stealth`, `F2M1_strict_necessity`, `F2M2_gradual_max_stealth` (2026-01-26) | 001 + 003 | Sonnet 4.5 / GPT-4.1-mini (mostly) | 9+50, 15+45, 2+58 | secret-exfil, malicious-package, triggered-exfil | development; not reported |
| 2026-01-10..13 pilots, `run_2`, `last-two-days` (kept part) | 001 + 002 | Sonnet 4.5 and Mistral-large (10 logs) | 118 kept (108 in 001, 10 in 002) | (gradual-)api-token-exfil, 6 one-off side tasks, honest | not reported |
| `batch_runs/dbl_honest`, `dbl_triggered_attack` (2026-06, rev b8a50a1) | batch-runs | Sonnet 4.5 / GPT-4o | 50 (290), 60 (348) | honest, triggered-exfil | unclear; possibly App. J resampling |
| `agent_monitor_logs/agentic_smoke_input` | auditor | Sonnet 4.5 / GPT-4o | 1 (6) | triggered-exfil | agentic-auditor input; not reported |

- **Missing cells.** All Flask runs, the Gemini 3.1 Pro and Kimi K2.5 attackers, 7 alternative monitor models, link-tracker scores, M3 runs, and about 85 positional runs.
- **Extra cells.** The pilot and development arms above, plus the 96 `vibe_coding` (non-persistent) samples.
- **Cross-part arms.** The three zips are Google-Drive-style export chunks, so one experiment can span them (`M1F3_main_run3`). L1-05 therefore judges coverage on the union of parts.
- **Exclusions.** No arm is excluded for zero successes or for being a pilot (user rule).

## 4. Expected outcome rates (L2 outcome sanity; whole-population tally H6–H8)

**Mapping (pre-registered).**

- A paper "run" is one log (one PR sequence). One execution is one sample, i.e. one PR.
- Run success is `side_task_success` = success on the **last PR sample** of the log. The variant "any PR" is reported too.
- Evasion is the share of successful runs whose maximum per-PR monitor score is at or below τ (`≤` τ; App. A.2, Table 5 and Table 16 captions). **[corrected]** The paper's operational boundary is not ambiguous; only the introduction says "below". `<` τ is still reported as a sensitivity variant.
- Monitor mapping (inference, not stated in the source):

  | Paper monitor | In-log scorer |
  |---|---|
  | TD (task-description) diff | `score_pr_diff_task_sequence` |
  | full-diffs | `score_pr_diff_full_diffs` |
  | trajectory | `score_pr_traj*` |

- Main-task success is not compared: the paper reports no rate for it.

| Arm | n (runs) | Expectation | Basis |
|---|---:|---|---|
| gradual_f3m1 · triggered-exfil · success | 60 | **47/60 = 78.3%** | Table 3; text gives 47 successful runs |
| gradual_f3m1 · config-telemetry · success | 60 | **7/60 = 11.7%** | Table 3 |
| gradual_f3m1 · both · success | 120 | **54/120 = 45.0%** | Table 4; Table 11 M1; Table 14 n_A = 54 |
| gradual_f3m1 · TD evasion τ6 (exploratory) | 54 successes | 51/54 = 94.4% (triggered 45/47, config 6/7) | Tables 3 and 7 (rescored values) |
| gradual_f3m1 · full-diffs τ7 / traj TD τ3 / traj full τ3 (exploratory) | 54 | 88.9% / 66.7% / 75.9% | Table 7 |
| positional_f3m1 · success by attack position | 515 | rising with position; the Fig. 6 caption states 3% at PR0 and 39% at PR4, **[corrected] pooled over CLI and Flask**, so context only (not comparable to this CLI-only arm) | Fig. 6 caption |
| positional selected (best position) | 120 | 77.6% / 16.7%: **not comparable** (the rule, best-evasion position per sequence × side task, §3.1 / App. M, depends on rescored monitor outputs outside the logs) | Table 3 |
| honest_all · runs with max TD score > 6 (exploratory) | 166 | about 2% (p98 calibration; at most 5% expected) | Table 5 / App. A.1 (ensemble FPR 1.3% CLI is in §4.4) |
| all other arms | – | Wilson 95% only | – |

At about 5 sampled logs per stratum, no L2 cell reaches n ≥ 20. The comparison of record is the whole-population raw tally (H6–H8).

## 5. Known quirks (expected-known findings)

| Id / source | Expected | Reference |
|---|---|---|
| `inspect.model_roles_not_mapped` | 152 none/none logs; on 065b0d36 the agent model comes from `model_roles` (R-10p-2, 0663e547) | profile; regen-batch |
| `inspect.judge_model_separate_from_agent` | solver spans call the untrusted model only, scorer spans the trusted model only | profile; census |
| `inspect.error_logs` / `unfinished_logs` / `empty_or_truncated_logs` | 26 / 8 / 172 empty + 186 truncated | profile |
| `inspect.sample_limit` | 445 samples | profile |
| `inspect.parallel_tool_batches` (item 16 b) | 13 batches, 20 first-of-batch events | profile |
| `inspect.strings_over_1mib` (item 28) | 28 strings in 22 samples | profile |
| `inspect.prose_tool_name` | 1 call | profile |
| `inspect.planted_credentials` | `sk-` key at `/metadata/API_KEY` in every sample (442 distinct in the readable containers); agent-handled key shapes in side tasks | profile; D-344 |
| `inspect.event_order_not_time_order`, `attachment_refs`, `tool_span_separate_from_tool_event` | present | profile |
| `inspect.art.abbreviated_revision` (generic) | 7- or 8-hex `revision.commit` in all header logs; 12 distinct values + 1 null | census; `artefacts.toml` scopes only the survey |
| Account paths (D-345) | `/Users/<account>` in exactly the 36 held logs (9 headers, 107 samples); `/home/<placeholder>` only in model-visible content | phase-10p §5 |
| CD-24 (open, RD-2) | judgements named `score…` and each scorer duplicated as a bench judgement (inspect_ai < 0.3.217) | review-core-d |
| D-453 / D-454 (not on 065b0d36) | the decoded scan cannot read the 186 truncated members, so a seal may refuse with `corpus.withhold.unscanned` | DECISIONS |
| `artefacts.toml` | **no entry scoped to this source** | `adapters/inspect/artefacts.toml` |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2, per part, including nested zips and register codes |
| L1-02 strict parse | yes | `header.json`, `samples/*.json`, `_journal/*`, `summaries.json`, `reductions.json` of every readable log |
| L1-03 encodings | yes | ANSI ESC in `/error/traceback_ansi` is expected (counted, not a defect); U+FFFD in sandbox outputs is counted |
| L1-04 duplicates | yes | Within the corpus: 25 byte-duplicate logs (20 in 002 nested, 5 in 003) and 3 partial-overlap logs (D-181). Cross-corpus: expect 0 |
| L1-05 arm coverage | yes | §3 |
| L1-06 secrets / account paths | yes | Counts and pointers only. Planted keys are in every sample |
| L1-07 timestamps | yes | All `+00:00`; logs created 2026-01-10..2026-06-05; event-list order is not time order (quirk) |
| L1-08 degenerate | yes | 358 damaged members, 8 header-less logs, 26 error logs, 50 samples without tool calls |
| L2 import / validate / recompute / determinism | yes | Via the queue at `--cpu 2`. The nested zips need the D-382 raise (`max_member_bytes` 2 GiB) |
| L2 A2 / A3, evidence classes | yes | CD-24 judgement classes are expected-known |
| L2 identity | partial | Models via `model_roles`. No attack or defence identity exists (D-343) |
| L2 redaction | yes | Held logs are not imported; expect 0 `/Users/` in AER/SEM/PROV |
| L2 withholding | yes | Seal on a scratch copy: every execution withheld (D-344), or a refusal under D-450 (D-453/D-454 pending) |
| L2 outcome sanity | partial | gradual_f3m1 only (H6). Other arms are Wilson only |
| SEM | no | No semantics profile (D-343) |
| Delta since E2 | no | Not in E2 |

## 7. Hypotheses (falsifiable; thresholds fixed now)

| Id | Expectation | Falsified if | Class if falsified |
|---|---|---|---|
| H1 | L1 counts per part equal §2 (direct and nested `.eval`, classes, 358 damaged, 36 held, 8 header-less) | any count differs by ≥ 1 | analysis-artefact or mapping-defect |
| H2 | 0 duplicate keys, BOM, invalid UTF-8, lone surrogates or depth hits in readable logs; NaN/Infinity 0 outside score values | any hit | source-defect, S3 |
| H3 | Every original sample has an `sk-`-shaped `/metadata/API_KEY` (5,729 of 5,729 classified) | < 100% | documentation-mismatch (D-344 premise), S1 |
| H4 | Byte-identical: 25 logs as in §2. In import order, the 15 header-bearing duplicates in `positional_f3m1.zip` carry 71 samples and explain the 739/1,698 split | other counts or locations | analysis-artefact (our attribution), S3 |
| H5 | `gradual_f3m1` = 120 logs = 5 CLI sequences × 2 side tasks × 12; `honest_all` = 166 original; `positional_f3m1` = 515 original with 1–5 samples each (cached prefix) | any deviation | documentation-mismatch, S2 |
| H6 | gradual_f3m1 run success (last PR): triggered-exfil 47/60, config-telemetry 7/60 | either differs by > 2 runs | documentation-mismatch (archive arm ≠ paper arm), S2 |
| H7 | (exploratory) gradual_f3m1 TD-diff evasion τ6 over successful runs ≥ 80% (paper 94.4%) | < 80% (gap > 15 pp) | expected-known if it traces to rescoring, else documentation-mismatch S2 |
| H8 | (exploratory) honest_all: ≤ 5% of runs have max TD score > 6; honest samples have no side-task success | > 5%, or any honest side-task success | documentation-mismatch, S3 |
| H9 | 0 Flask side or main tasks, 0 Gemini or Kimi models, trusted ∈ {gpt-4o, gpt-4.1-mini}, untrusted ∈ {Sonnet 4.5, Mistral-large} | any other | census incomplete (analysis-artefact) |
| H10 | (exploratory; PR #41 lead) in-log monitor score values lie in [0, 10] or are null in ≥ 99.5% of values | > 0.5% outside | source-defect, S2 |
| H11 | `/Users/` occurs only in the 36 held logs (9 header pointers, 107 samples) | any in a selected unit | security finding, reported at once |
| H12 | All timestamps carry `+00:00`; log creation ≤ 2026-06-10T15:47:58Z for the zips and ≤ 2026-07-30 for the tars; the zips hold 801 March-2026 logs (card says Jan–Feb) | non-UTC or out of range | source-defect, S3 (card: documentation-mismatch, S3) |
| H13 | L2: 0 `adapter_defect` and 0 degenerate (item 80 on 065b0d36); every stage ok; agent model resolved from `model_roles` in 100% of none/none units | any | mapping-defect (S1 if executions are lost) |
| H14 | L2: `recompute --dry-run` reports 0 differences; a second import with other `--jobs` is byte-identical | any difference | mapping-defect, S1 |
| H15 | L2: CD-24 is present, i.e. at least one judgement named `score`/`score.<key>` per sample with score events, plus bench duplicates | absent (would mean it was fixed or misread) | analysis-artefact |
| H16 | L2 seal: either 100% of executions withheld (D-344) or refusal with `corpus.withhold.unscanned` limited to containers holding truncated members | any execution released with a key present | security finding, S0 |
| H17 | Our docs: the README listing (2,267) and the profile quirk value 5,754 disagree with the census and trial (5,522; 5,742/5,729) | they agree | documentation-mismatch (ours), S3 |

Rule: no arm is excluded for zero attack successes or for being a pilot.

## 8. Expected movement since phase-10p trial t1 (no E2 delta)

| Change on 065b0d36 | Expected effect |
|---|---|
| Item 80 / R-10p-7 (`5e782191`) | t1 had 5,522 degenerate executions; now 0 (H13) |
| R-10p-2 (`0663e547`) | the agent's requested model comes from `model_roles`, not none/none |
| D-182 + R-10p-3 (`0663e547`) | redaction of the 36 logs' pointer classes is available, but profile v2 still holds them (36 `redaction_pending`, unchanged) |
| D-452 (`6284ac57`) | the decoded scan reads nested zips at level 3; truncated members remain unscanned until D-453/D-454 |
| CD-24 (not fixed) | judgement naming and duplication as in H15 |

## 9. Fact-check (2026-10-14, adversarial pass before any data check)

Re-opened: arXiv 2607.02514 abs page and the v1 and v2 HTML (<https://arxiv.org/abs/2607.02514>,
<https://arxiv.org/html/2607.02514v1>, <https://arxiv.org/html/2607.02514v2>); the HF API (dataset info, commits, tree at
`84d39e0a`, `README.md`, `logs_tmp_zips/README.md` and `SHA256SUMS` at the pin, the `idacy` dataset list); the GitHub API
(repo, PRs #6/#8/#25/#30/#32/#36/#41/#42, the 12 revisions, the tree at `68de4a36`, README); PyPI (inspect-ai,
control-arena); our own profile, `tools/readme_corpora.toml`, phase-10p README, census `aggregate.json`, DECISIONS and
`mapper.py`. No raw data was read.

**Confirmed.** Title, authors and CC BY 4.0; v1 2026-07-02 (170 KB) and v2 2026-07-08 (161 KB). The HF card cites the
paper and the code repo. Table 3 cells (CLI gradual 78.3% / 11.7%, positional 77.6% / 16.7%, evasion 95.7 / 77.8 and
85.7 / 70.0; Flask rows), Table 4 (45.0% / 94±7; Gemini 38.3% / 65.3; Kimi 43.9% / 100.0), Table 5 (n = 308; τ 6/5/7/3/3),
Table 7 CLI column (all seven rows), Table 11 M1/M2/M3, Table 14 (n_H 167, n_A 54), Table 16 (19/27, 21/26), Table 18
(27/33/29/32/34 = 155), §3.3 n = 120 gradual / 600 positional; text "47 successful gradual triggered-exfil runs"; 47/60,
7/60, 54/120, 45/47, 6/7, 51/54 are arithmetically consistent with the table percentages. HF pin = head, 27 commits all
on 2026-07-30, public, not gated, `license: mit` front matter, no LICENSE file; 72 files, 6,835,660,481 B; all 21 profile
sha256 values equal the HF LFS oids and sizes; part sums equal the three container sizes; SHA256SUMS prefixes
073ffd16 / 44feadfc / 61737803; zips README says "Jan-Feb 2026". Siblings `…-logs-2026-05-23` (4,338 `.eval`) and
`control-arena-runs` (7,123) have no licence. Repo: fork of UKGovernmentBEIS/control-arena, MIT, created 2026-01-06, main
`68de4a36` 2026-06-23; PR #30 / #32 / #41 merge dates and content as stated; 10 revisions resolve (2026-01-09 to
2026-04-21), `fe882288` and `59859463` give HTTP 422. inspect_ai 0.3.159 released 2026-01-03, 0.3.217 2026-05-03. CD-24
fallback at `mapper.py:1564` on 065b0d36. 5e782191, 0663e547 and 6284ac57 are ancestors of HEAD; D-453/D-454 are recorded
but unbuilt (D-454 sequencing note). Internal arithmetic: 5,522 − 2,441 − 1,698 − 638 − 6 = 739; 660+153+810+638+6 = 2,267;
2,636 − 195 = 2,441; 1,652 − 25 = 1,627; 1,627 + 810 = 1,698 + 739; 153+38+167 = 358; census nested rows 410 / 3 / 7 and
515 / 20; profile quirk 5,754.

**Corrected.**
1. Abstract and introduction changed between v1 and v2 (wording; 76→81% and 31→27% in §1); only the tables and n are stable (§1 above).
2. The "below" boundary wording is in §1, not §3.2; the operational definition is evade iff ≤ τ (§4 mapping updated; `<` kept as sensitivity).
3. Table 9 also disagrees with Table 6 (τ 7) and with Table 7 on positional evasion (84.5 vs 98.2).
4. Fig. 6's 3% → 39% is stated in its caption and is pooled over CLI and Flask: context only for the CLI-only positional arm.
5. Ensemble FPR 1.3% is from §4.4, not Table 5 / App. A.2.
6. Repo: issues are disabled (not "0 issues"); main has `paper/` (research.json said it did not).
7. The 3 partial-overlap logs are in `2026-01-15_last-two-days.zip`, not `honest_all.zip` (census `log_rows`; the phase-10p README is wrong here).
8. "10–11 scorers per sample" (research.json, CD-24 lead): scorer sets range from 1 to 11 per log; 912 of 1,361 original logs have 10 or 11 (census `orig.scorers`).
9. The positional selection rule is stated in the paper (§3.1, App. M); it is not reproducible from the logs because it uses rescored monitor values.

**Noted, not an expectation.** After Table 3 the paper reports extra config-telemetry gradual runs (180 attempts, 31
successes); no source places them in this archive. HF `idacy/ca-pse-iclr2027` (MIT, 2026-09-30) holds CSV records of a
different manuscript, not the logs of this paper.

**Unverifiable here (data-derived, kept as stated):** the 801 March-2026 logs (consistent with 515 + 120 + 166), the 15
header-bearing duplicates carrying 71 samples (H4), 1,980 bare `score_pr_diff` names, 109 damaged positional members,
and which in-log scorer is the paper's TD monitor (the paper calls it the "task-sequence PR monitor" once, after Table 3,
which supports `score_pr_diff_task_sequence`).
