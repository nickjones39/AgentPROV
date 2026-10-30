# Pre-check dossier: `drift1-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `drift1-agentdojo` (licence: MIT by the inherited README badge only, D-93; no top-level LICENSE; `ASB_DRIFT/LICENSE` covers that subtree only) |
| Parts | `drift1-agentdojo · drift` (1 part) |
| Family / profile | `agentdojo` / `drift1-agentdojo@1` (sha256 `3df46db9ad3d`; dialect `agentdojo.tracelogger`, variant `drift.k18.conversations`; semantics `agentdojo.suites@2`) |
| Pin | git `CGboom-git/drift-1` @ `0e28729b` (= HEAD of the only branch), `runs/` tree `cb44a83f` |
| Code commit | `d97d3a57` (L1 and L2, batch `wave7`, all six steps rc 0; tracked changes true, PC-07) |
| Kind | wave 7, first examination (not in FA/E2), no stored corpus; baseline = phase-10j trial (10J-T) |
| Date | 2026-10-15 (prereg, research, batch), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), examiner (this dossier); adversarial verifier (7/7 confirmed, 0 refuted) |
| Data | [`data/drift1-agentdojo/`](data/drift1-agentdojo/): `research.json`, `l1-drift.json`, `l1-10-drift.json`, `l2-sample-drift.json`, `l2-drift.json`, `code-drift.json`, `exam.json`, `findings.json`, `pop-census.json`, `stamps.json`, `traj.json`, `os1-population.json`, `os2-sample.json`, `l2-exam.json`, `basediff.json`, `exam-scripts/` |

- Code identity, part `drift` ([`code-drift.json`](data/drift1-agentdojo/code-drift.json)): commit `d97d3a57` (tracked_changes true); engine aer `856b7a09e0cf`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `agentdojo.tracelogger@0.1.0` `03d8bc6d30df`; profile `3df46db9ad3d`; rules aer 1 / agentdojo 2 / drift 1; semantics `agentdojo.suites@2` `92f6a626a1cc`; lockfile `b0455f1058c8`; limits `5d6dbb210259`. Same digests as the other wave-7 parts.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Data repository | https://github.com/CGboom-git/drift-1 @ `0e28729b` (0 tags/releases/issues/forks; GitHub fork = false) | the 626 logs (616 `runs/gpt-4o-mini`, 10 `runs/pact-gpt-4o-mini-banking10`) |
| Parent | https://github.com/SaFo-Lab/DRIFT (history to `70d59166` copied) | 1,569 head copies owned by part `drift` |
| Paper (reference only) | arXiv:2506.12104v3 (DRIFT), Tables 6-8 | PAP v3 targets; no paper for drift-1 |
| PACT concept | arXiv:2605.11039 | not cited by drift-1; no numbers |
| Harness | `agentdojo==0.1.35`, label `v1.2`, seed 98 | producer and checker |
| Upstream issues | ethz-spylab/agentdojo #146, #161, #168, #181, #189 | checker defects (CC-07, CC-10) |

Data-versus-paper notes: the README is DRIFT's byte for byte and states no drift-1 results; the 616 were committed with DRIFT `70d59166` code and the PACT runs with PACT code that precedes them; the code at the pin produced neither (research.json). The 616 are a third-party re-run on the undated alias `gpt-4o-mini` (served model unrecorded).

## 3. Expectations

Pre-registration: [`prereg/drift1-agentdojo.md`](prereg/drift1-agentdojo.md), committed in `eb7151ee` (2026-10-15), before any data check. Amendment 5 (README section 8) fixes the stratum key `model_dir × suite × attack_dir` (prereg open question 1: answered, 9 strata, 45 units).

| H | Result | Note |
|---|---|---|
| H-01 | supported | 626 files, 6,693,705 bytes (1,876..48,278), 1,569 `owned_elsewhere`; 9 cells as section 3 |
| H-02 | supported | workspace attacked u0-u3, u5-u9 × i0-i13, u10 × i0-i3; u4 benign only |
| H-03 | supported | strict ok 626/626; 18 keys × 616, 24 × 10; `pipeline_name` `gpt-4o-mini` 626; `v1.2` 626; flags T/T/T/F 626; `pact_drift_enabled` true 10, absent 616 |
| H-04 | supported | every tested Δ count exact (L1 row below); isolation-frame positions (481/12) and provider-id anomalies not re-tested |
| H-05 | supported | utility 351/626; security 114 = 97 benign + 17 attacked (banking 16, travel 1, PACT 0) |
| H-06 | supported | all PAP cells within the rule (section 6); workspace UA vs the full grid is the pre-registered subset caveat |
| H-07 | **refuted** | banking ASR 16 vs head 7 on the same 144 cells (+6.25 pp > 5); other suites within (PC-03) |
| H-08 | supported | 9/9 unrecognised CALL ERRORs (4 PACT files, 0 elsewhere) carry the provenance-contract refusal; matched against `DRIFTLLM.py` at the pin because the `79f58f09` blob is absent from the partial clone |
| H-09 | supported | benign stamps 2026-06-23 16:18..17:29, attacked 2026-06-24 03:51..09:42, PACT none; none before 2026-04-19 |
| H-10 | supported | L1-06 0/626; PACT contract path relative 10/10; L1-10 2 context files, 0 hits |
| H-11 | supported | 0 byte- or trajectory-identical groups within the part or with any other part |
| H-12 | supported | 45/45 valid, deterministic; codes as 10J-PC; PACT-only codes only in PACT units; no new code |
| H-13 | supported | decisions = batches + CALL ERRORs in 45/45 (180); population 2,071 + 266 = 2,337 |
| H-14 | supported | 20/20 benign `security` origin `harness_default`, rule `drift.benign_security_constant_unverified@1` (class-I twin of the pre-registered id) |
| H-15 | supported | 0 AER records or fields at class D |
| H-16 | supported | `user_task_5` utility true 11/11 (6 vacuous, PC-02) |
| H-17 | supported (vacuous) | 0 slack i5 successes of 21; 4 executed a membership call and scored false |
| H-18 | supported | unknown-tool label 1/168 sampled tool messages (0.6 %) |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: bare clone `~/.agentprov/staging/10c/drift-1/drift-1.git` at `0e28729b` (`--git`), `l1_scan` at `d97d3a57`, 0.7 s. Examiner recounts: [`pop-census.json`](data/drift1-agentdojo/pop-census.json), [`stamps.json`](data/drift1-agentdojo/stamps.json), [`traj.json`](data/drift1-agentdojo/traj.json).

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 2,535 walked = 626 selected + 1,569 `owned_elsewhere:drift` + 290 not selected + 44 absent blobs + 4 strays + 2 context (340 outside = prereg). Units 626 = registry | as expected |
| L1-02 parse | ok 626/626; 0 duplicate keys, non-finite, big ints, lone surrogates, BOM, trailing data, truncation | as expected |
| L1-03 encodings | escaped newline 303 files / 539 strings (`/conversations/*/content`, CALL ERROR `repr` residue); JSON-in-string 338 (`/initial_checklist`); escaped unicode 18 / 26; escaped quote 11; 0 controls, bidi, zero-width, U+FFFD | known residue |
| L1-04 duplicates | 0 byte-identical, 0 trajectory-identical (626 distinct fp); `_cross/l1-xdup.json`: 0 groups with any part | as expected (CC-01 n/a) |
| L1-05 arms | 9 strata: banking 144/16, slack 105/21, travel 140/20, workspace 130/40, PACT banking 10 (u0-u9 × i0); 0 extra; `model_dir` = `pipeline_name` in 616, PACT 10 differ (own row) | as expected |
| L1-05 quirk counts | messages 6,061 (892/2,963/2,206); CALL ERROR 266 msgs / 173 files (59/198/9); reserialised/raw 2,617/346; calls 2,206 = tool msgs; batches 2,071; tool errors 179 (20/37/122); final text calls 78 (all reserialised); 15 runs without tool execution; checklist 624 strings (338 parse as JSON text) / 2 None; trajectory covers 441 / not 170 / none 15 | = prereg Δ |
| L1-06 secrets/paths | 0/626; L1-10 2 context files, 0 hits, 0 operator | as expected |
| L1-07 timestamps | 0 structured time fields. Date-shaped tool-call args 67 files (benchmark content, naive, 2023-10-15..2025-01-02). Content stamps 20 runs (benign 9, attacked 11) | as expected |
| L1-08 degenerate | flags {} over 626; last role assistant 626; messages 2..22 (median 8) | as expected |

CC-07 on this corpus (population, raw):

| Defect | Affected / denominator | Logged → re-scored |
|---|---|---|
| #181 banking IT0/1/3 precedence | 5 of 11 successes lack the checker datum (it0 0/2, it1 3/6, it3 2/3); all 11 executed an attacker-bound `send_money` | banking ASR 16/144 = 11.11 % → 11/144 = 7.64 % |
| #161 `user_task_5` | 6 of 11 utility-true files without an executed Spotify payment (attacked 5/9, PACT 1/1, benign 0/1) | banking UA 66/144 = 45.83 % → 61/144 = 42.36 %; PACT 4/10 → 3/10 |
| #168 slack i5 (CC-10) | 0 successes of 21 | not applicable |
| #146 workspace u13 | 1 benign file, utility false | report only |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`l2-sample-drift.json`](data/drift1-agentdojo/l2-sample-drift.json) (sha256 `a7b09dc00da3`, units `e193e574d9aa`): 45 of 626, 9 strata × 5, seed 20261011 |
| Import | `l2-drift-j2.partial` / `-j1.partial` at `d97d3a57`: 45/45 mapped (ok 36, ok_with_issues 9), 0 degenerate, 0 `adapter_defect`, 0 failed; 45 labels → 45 executions |
| Validation | aer, sem, prov, linkage: 45/45 pass, 45 reproduced, linkage 100 %; SHACL not implemented; regression n/a |
| Recompute | `--dry-run`: 45 identical, 0 unexplained |
| Verify chain | 0 failures (`checksums.absent`, working tree); no `[withhold]` |
| Determinism | j2 vs j1: 189/189 files identical, index identical |
| A2 / issue codes | `accounting_unverifiable` 45, `drift.agent_prompt_not_recorded` 45, `drift.injection_map_not_recorded` 25 (attacked + PACT), `drift.calls_in_text_not_executed` 9 (PACT 4/5, others 5/40 = 12.5 % = population 78/626), `agentdojo.unknown_top_level_key` 5 (PACT only), `drift.call_error_unrecognised` 1 (PACT only) |
| A3 PROV | 0 issues over 20,465 statements / 33,433 relation arguments; 419 messages with `generated_by`, 168 tool executions with call |
| Records | 464 messages, 225 model calls, 168 tool executions, 180 decisions (154 `drift.isolation_pass` + 26 CALL ERROR) = batches + CALL ERRORs in 45/45 |
| Evidence classes | AER: 0 records/fields at D. PROV: core D 210 / O 1,301; inference I 6,416; assessment I 1,277 / O 90. `_unverified` split: twin 6,705 (assessment 884, inference 5,267 + 554), native 0, mixed 974 (inference) |
| Judgements | raw = mapped 90/90; security origin: checker 25 (attacked + PACT), `harness_default` 20 (benign) |
| Identity | model `gpt-4o-mini` 45/45 (PACT dir → alias); defence `drift` 40, `drift` + `pact_drift` 5 (`task.defense_id` `ambiguous`); attack `important_instructions` 25 / none 20; 0 unresolved, 0 mismatches. The tool's tuple shows PACT as `none` (PC-06, R5) |
| Movement vs 10J-T | record-kind counts equal 45/45; differing fields only `model_call /unk/params` (225, U6-c, `not_recorded`; cf. CC-04) and seal `records_sha256` (45); `load_environment` in 0 AERs (D-370 does not touch DRIFT); BF-28 byte-neutral |
| Redaction | 143 derived files, 0 hits |
| Withholding | no policy (D-257) |

## 6. Outcome comparison

Level 1 population, raw booleans. Gap rule: > 15 pp on n ≥ 20, or the paper > 5 pp outside the Wilson 95 % interval. Full rows: [`os1-population.json`](data/drift1-agentdojo/os1-population.json).

| Arm (gpt-4o-mini / defence / suite) | n | Metric | Rate (Wilson 95 %) | Reference | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|
| drift / banking | 144 | UA | 45.83 (66) [37.91, 53.97] | PAP 40.97 | +4.86 | within |
| drift / banking | 144 | ASR | 11.11 (16) [6.96, 17.29] | PAP 4.86 | +6.25 | within (outside by 2.10); #181 (PC-01) |
| drift / slack | 105 | UA | 50.48 (53) [41.07, 59.85] | PAP 49.52 | +0.96 | within |
| drift / slack | 105 | ASR | 0.00 (0) [0.00, 3.53] | PAP 0.00 | 0.00 | within |
| drift / travel | 140 | UA | 50.71 (71) [42.53, 58.87] | PAP 53.57 | −2.86 | within |
| drift / travel | 140 | ASR | 0.71 (1) [0.13, 3.93] | PAP 0.00 | +0.71 | within |
| drift / workspace (130 of 560) | 130 | UA | 78.46 (102) [70.63, 84.66] | PAP 59.64 (full grid) | +18.82 | subset caveat; judged by the paired row |
| drift / workspace (130 of 560) | 130 | ASR | 0.00 (0) [0.00, 2.87] | PAP 0.54 | −0.54 | within |
| drift / banking benign | 16 | BU | 50.00 (8) [28.00, 72.00] | PAP 50.00 | 0.00 | n < 20 |
| drift / slack benign | 21 | BU | 57.14 (12) [36.55, 75.53] | PAP 66.67 | −9.53 | within |
| drift / travel benign | 20 | BU | 50.00 (10) [29.93, 70.07] | PAP 55.00 | −5.00 | within |
| drift / workspace benign | 40 | BU | 62.50 (25) [47.03, 75.78] | PAP 57.50 | +5.00 | within |
| banking, paired with DRIFT head | 144 | UA / ASR | 66 / 16 | head 59 / 7 | +4.86 / **+6.25** | ASR breaks H-07 (5 pp); concordance 85.4 / 89.6 % (PC-03) |
| slack, paired | 105 | UA / ASR | 53 / 0 | 55 / 1 | −1.90 / −0.95 | within |
| travel, paired | 140 | UA / ASR | 71 / 1 | 75 / 0 | −2.86 / +0.71 | within |
| workspace, paired | 130 | UA / ASR | 102 / 0 | 96 / 3 | +4.62 / −2.31 | within |
| drift + pact_drift / banking | 10 | UA / ASR | 40.0 [16.8, 68.7] / 0.0 [0.0, 27.8] | none (head same cells 3 / 0) | — | no target |

Macro over the four suites (616 arm): BU 54.91 (paper 57.29), UA 56.37 (50.93; workspace subset), ASR 2.96 (1.35). Pooled 616 utility 347/616 = 56.33 %, inside the pre-registered bound 341-351. Zero-success cells (slack, workspace ASR) are kept.

Level 2 ([`os2-sample.json`](data/drift1-agentdojo/os2-sample.json)): 9 strata × 5, mapped = raw in 90/90 judgements; no arm reaches 20, so no verdict (amendment 2.2, R6). Sample utility k/5: banking att 1, benign 3; slack 3 / 2; travel 5 / 4; workspace 4 / 1; PACT 2. Security on attacked: banking 1/5, all others 0/5.

## 7. Findings

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-drift1-agentdojo-01 | [CC-07, #181] banking IT0/1/3: 5 of 11 successes without the checker datum | expected-known (R2, CC-07; scope gap CC-09) | S3 | confirmed | disclose (11.11 → 7.64 % precedence-only; 5.56 % with the it1 GOAL datum); keep logged values |
| PC-drift1-agentdojo-02 | [CC-07, #161] `user_task_5` utility 11/11, 6 without payment | expected-known (R2, CC-07) | S3 | confirmed | disclose (45.83 → 42.36 %; PACT 4 → 3 of 10) |
| PC-drift1-agentdojo-03 | H-07 refuted: banking ASR 16 vs head 7 on the same cells; README is DRIFT's | documentation-mismatch (R3) | S3 | confirmed | present drift-1 as an independent re-run; no exclusion |
| PC-drift1-agentdojo-04 | [CC-09] no `artefacts.toml` entry scopes drift1; quirk counts verified | documentation-mismatch (CC-09) | S3 | confirmed | reference only; family owner widens scopes |
| PC-drift1-agentdojo-05 | profile calls drift-1 a "fork"; GitHub: not a fork | documentation-mismatch (R4) | S3 | confirmed | reword at the next profile bump |
| PC-drift1-agentdojo-06 | `l2_check` prints the PACT defence as `none` (ambiguous `defense_id`) | analysis-artefact (R5) | S3 | confirmed | tool fix; mapping correct |
| PC-drift1-agentdojo-07 | code identity `tracked_changes` true (all wave-7 parts, same digests) | analysis-artefact (R5) | S3 | confirmed | compare digests, not commits |

PC-03 detail: 15 discordant banking cells (12 drift-1-only, 3 head-only successes, 4 in both). After the #181 datum re-score on both sides the gap is 11 vs 5 (+4.17 pp). The L2 judgements match raw, so this is a source property of a re-run (later DRIFT code, alias model), not a mapping defect.

No security finding. No mapping defect. PC-04 is a reference to CC-09; PC-06 and PC-07 are R5. `findings.json` holds evidence and reproduction per finding; refuted: none.

Verifier (adversarial pass): all 7 confirmed, class and severity unchanged. `pop.py` re-run reproduces `exam/pop.json` byte for byte. PC-01: an independent recount finds 0 scheduled attacker transfers among the 11, and normalising case and separators changes nothing. The it1 datum `me` is the 0.1.35 checker's, so 7.64 % is the precedence-only re-score. Under the GOAL datum (the companion IBAN in the subject), 0 of the 6 it1 subjects hold it, which leaves 8 of 11 without a datum (8/144 = 5.56 %). Disclose both. PC-03: S3 rather than S2, because the PAP v3 banking ASR stays inside the gap rule. The class is borderline: this is a source property of an independent re-run, and it is kept as documentation because the action is framing. PC-05: the profile's "fork" is imprecise rather than false, because drift-1 does carry DRIFT history.

Proposed `artefacts.toml` entries (text only; to the AgentDojo family owner):

```toml
# agentdojo.art.validity_defects: scope.sources += "drift1-agentdojo"; scope.profiles += "drift1-agentdojo"
expected += [
  { snapshot = "drift1-agentdojo:drift", count = 5, unit = "executions", basis = "pre-check PC-drift1-agentdojo-01: banking IT0/1/3 security true without the checker datum in an executed attacker-bound subject (it0 0/2, it1 3/6, it3 2/3) of 11 (#181)", status = "proposed" },
  { snapshot = "drift1-agentdojo:drift", count = 6, unit = "executions", basis = "pre-check PC-drift1-agentdojo-02: banking user_task_5 utility true without an executed Spotify payment: attacked 5/9, PACT 1/1, benign 0/1 (#161)", status = "proposed" },
]
# PC-04 (CC-09): add drift1-agentdojo to the generic DRIFT entries with the counts of section 4 (post-isolation 2,071/2,206;
#   reserialised 2,617/346; call_error_as_user 266/173; calls_in_text 78; benign_security_constant 97; content stamps 20 runs)
```

Items for AGENTS.md section 12:

- PC-01/02 (CC-07): drift-1 banking ASR 16/144 includes 5 #181 passes (re-scored 7.64 %); banking UA 66/144 includes 5 vacuous `user_task_5` passes (42.36 % without).
- PC-03: drift-1 is an independent re-run of 519 DRIFT head cells, not a copy: banking ASR 16 vs 7 on the same cells.

## 8. Recommendations and readiness

1. Verifier pass done: 7/7 confirmed, none refuted.
2. Route the PC-01/02 `validity_defects` rows and the PC-04 scope widening to the AgentDojo family owner (CC-07, CC-09); PC-05 to the profile owner (no byte effect beyond the profile digest); PC-06 to the pre-check tool owner.
3. Disclose PC-01/02 next to drift-1's banking figures and present drift-1 as an independent re-run (PC-03). Logged booleans stay primary.
4. Prereg open questions 2 (reading the four `.log` files) and 3 (licence owner) stay with the orchestrator; neither blocks the import.
5. No exclusion of any data (slack and workspace ASR 0 are kept).

**Readiness: `ready-with-caveats`.** Imports correctly and deterministically (45/45 valid, recompute 0 unexplained, j1/j2 identical, raw = mapped 90/90, identity 0 mismatches, redaction 0 hits); L1 reproduces every pre-registered count exactly. Caveats (verifier-confirmed): CC-07 disclosures (PC-01, with the precedence-only 7.64 % and GOAL-datum 5.56 % re-scores; PC-02) and the re-run framing (PC-03). Not counted: PC-04 (CC-09 reference), PC-06/07 (R5).

## 9. Reproduction

Batch (wave 7): `uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave7 -- uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave7.toml` (steps l1, l1_10, sample, import_j2, import_j1, check; logs `~/.agentprov/migration-work/precheck/_batch/wave7/drift1-agentdojo.drift.*.log`).

```bash
uv run python tools/precheck/l1_scan.py --source drift1-agentdojo --part drift --corpus-id drift1-agentdojo --jobs 2 --emit-fp --git ~/.agentprov/staging/10c/drift-1/drift-1.git
uv run python tools/precheck/l2_sample.py select --units W/l1-units-drift.jsonl --source drift1-agentdojo --part drift --corpus-id drift1-agentdojo --out D/l2-sample-drift.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-drift.json --corpus W/l2-drift-j2 --source drift1-agentdojo --part drift --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-drift.json --corpus W/l2-drift-j1 --source drift1-agentdojo --part drift --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-drift-j2.partial --out D/l2-drift.json --sample D/l2-sample-drift.json --l1-units W/l1-units-drift.jsonl --compare-with W/l2-drift-j1.partial --jobs 2
```

Examiner scripts (read-only; pinned blobs through `agentprov.ingest`, blob SHA-1 checked; S = `D/exam-scripts`, W = `~/.agentprov/migration-work/precheck/drift1-agentdojo`, D = `docs/reports/precheck/data/drift1-agentdojo`):

```bash
uv run python -I S/pop.py W/l1-units-drift.jsonl ~/.agentprov/migration-work/precheck/drift/l1-units-head.jsonl W/exam/pop.json   # H-01..H-05, H-08, H-16, H-17, CC-07, pairing
uv run python -I S/stamps.py W/l1-units-drift.jsonl          # H-09 content stamps
uv run python -I S/traj.py W/l1-units-drift.jsonl            # H-04 trajectory coverage definitions
uv run python -I S/outcomes.py W/exam/pop.json D/l2-sample-drift.json W/l1-units-drift.jsonl D/os1-population.json D/os2-sample.json
uv run python -I S/l2exam.py W/l2-drift-j2.partial ~/.agentprov/migration-work/phase10j/trials/drift1-agentdojo-j4.partial W/exam/l2-exam.json   # H-12..H-15, H-18, section 8
uv run python -I S/basediff.py W/l2-drift-j2.partial ~/.agentprov/migration-work/phase10j/trials/drift1-agentdojo-j4.partial   # fields differing from 10J-T
grep -c drift1 src/agentprov/adapters/agentdojo/artefacts.toml                                  # PC-04: 0
grep -n -i fork src/agentprov/adapters/agentdojo/profiles/drift1-agentdojo.profile.toml          # PC-05
```

Follow-ups (not run):

| # | What | Command | When |
|---|---|---|---|
| 1 | Verifier pass on `findings.json` | done (7/7 confirmed) | — |
| 2 | Isolation-frame position recount (481/12) not re-tested | phase-10l probe `c03_isolation_position.py` restricted to the 626 labels | optional |
| 3 | Route PC-01/02/04 rows (CC-07, CC-09), PC-05, PC-06 | no command | before the round |
