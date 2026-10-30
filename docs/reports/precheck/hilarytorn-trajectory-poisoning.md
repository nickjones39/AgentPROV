# Pre-check dossier: `hilarytorn-trajectory-poisoning`

## 1. Header

| | |
|---|---|
| Corpus | `hilarytorn-trajectory-poisoning` (MIT, LICENSE at the pin) |
| Parts | `hilarytorn-trajectory-poisoning · head` (990 TraceLogger logs, variant v1.k14) |
| Family / profile | `agentdojo` / `hilarytorn-trajectory-poisoning@1` (sha256 `eadaf8892409...`; dialect `agentdojo.tracelogger`; rules aer 1, agentdojo 2; SEM `agentdojo.suites@2`) |
| Pin | git `HilaryTorn/in-context-trajectory-poisoning` `d71ab8bc` (= main HEAD on 2026-10-14); tree 1,294 blobs, 18 PNG charts absent in the staging clone (none under `data/traces`). Input: staged bare clone (`--git`, blob:none) |
| Code commit | L1 and L2 at `cb0af3d8` (clean tree). Batch `wave2` (`tools/precheck/plans/wave2.toml`) |
| Kind | wave 2. No stored corpus; the phase-10d trial imported all 990 with 0 failures |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (L1, L2, exam, verify, dossier) |
| Agents | researcher and fact-checker (prereg, research), examiner (L1/L2 analysis), one verifier per finding (8), dossier writer |
| Data | [`data/hilarytorn-trajectory-poisoning/`](data/hilarytorn-trajectory-poisoning/): `research.json`, `l1-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `os-population.json`, `findings.json`, `exam-scripts/` (path-cleaned copies added by the wave-2 completeness critic); cross-corpus `data/_cross/l1-xdup.json` |

- Code identity, part `head` (Level 2, [`code-head.json`](data/hilarytorn-trajectory-poisoning/code-head.json)): commit `cb0af3d8`; engine code aer `24df84b5e307`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `d3f9995f61bf`; adapter agentdojo.tracelogger `c311b5a6ac9e`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Repository | https://github.com/HilaryTorn/in-context-trajectory-poisoning (pin `d71ab8bc`, 2026-05-26, README-only commit; 28 commits, 0 issues/PRs, no tags) | the data: 990 logs under `data/traces/` (base 110 + 8 `e2e/<condition>` dirs x 110) |
| README + `data/results/e2e-evals.md` at the pin | https://github.com/HilaryTorn/in-context-trajectory-poisoning/blob/d71ab8bc2aa9db35ff443cc81e475e70ee8da215/README.md | base 96/105 (Methodology step 1); per-run, per-condition injection rates with n (e2e-evals.md, `e2e_eval/*/summary.json`) |
| Write-up | https://hilarytorn.com/projects/in-context-trajectory-poisoning/ (2026-04-12, updated 2026-04-18) | TAP / PAIR / seeded-PAIR and e2e results; states the e2e agent ran at T=1.0 |
| Hackathon report | https://apartresearch.com/project/incontext-trajectory-poisoning-blackbox-natural-language-attacks-on-llm-agent-monitors-d3gz (2026-03-22) | first write-up; predates 880 of the 990 logs; monitor-level numbers only |
| Harness | AgentDojo, arXiv:2406.13352 (logs: package 0.1.35, benchmark v1.2.1, slack) | issues #168/#189/#218/#188/#214/#194 screened |
| Monitor | LlamaFirewall AlignmentCheck, arXiv:2505.03574 | monitor decisions are not in the selected logs |
| Data record | none (no Zenodo, HF or Figshare record; 2026-10-14) | git blob SHAs are the only digests |

Data-versus-paper notes (from `research.json`):

- The directory-to-run mapping is not stated by the author; commit history implies `e2e/tap`, `e2e/seeded_pair` = run 3, `*_run1` = run 1, `*_run2` = run 2 (0 blobs shared between runs). Tested as H1/H3/H4: supported.
- `requirements.txt` pins agentdojo 0.1.29; logs and e2e manifests record 0.1.35; the manifests record dirty working trees for runs 1 and 2 (PC-07).
- Agent temperature: no script sets one, and AgentDojo 0.1.35 drops 0.0, so the provider default applies; the README's "temperature 0" remark is contradicted by the code and the write-up (fact-check).
- No benign user-task runs: the 45 `none` logs are injection-task pre-passes (security constant true). Benign utility is not measurable.
- The e2e attack labels hide the run (`e2e_tap_injection_task_k` covers 3 dirs); the arm is only the `{arm?}` path component (PC-01).
- The headline numbers (monitor ASR, e2e ASR on the 96-subset) are monitor-level and not testable from the logs; only injection success (`security`) is.

## 3. Expectations

Pre-registration: [`prereg/hilarytorn-trajectory-poisoning.md`](prereg/hilarytorn-trajectory-poisoning.md), committed in `fd75f8a3` (2026-10-14) before any check of this corpus ran, with an adversarial desk fact-check (its last section: agent temperature, the backup-race blob resolved at git level). Method amendments of README section 8 apply (2.4: stratum key = family hook arm key; 4: D-529 sampling only as a supplementary check).

Classes follow R1-R6 and CC-01 to CC-11 of [`cross-cutting.md`](cross-cutting.md). CC-07: the corpus is slack-only (990/990), so #181 and #161 (banking) do not apply: 0 affected logs. CC-10 (#168): 0 of 173 IT5 successes affected (H8). CC-09: PC-03 is its reference.

Hypotheses H1 to H10: all supported (rows from `exam.json`).

| H | Result | Evidence |
|---|---|---|
| H1 | supported | 9 per-dir attacked security tallies (96/97/77/86/83/92/80/91/81) and all 40 per-IT counts equal the author's under the inferred run mapping (tap/seeded_pair = run 3, `*_run1` = run 1, `*_run2` = run 2) |
| H2 | supported | attacked security true 783/945; pre-pass security 45/45; utility 690/990 |
| H3 | supported | 0 of 990 logs outside the manifest run windows |
| H4 | supported | exactly 2 `e2e/baseline` logs before 06:36:04 (the smoke run); `tap_run1` IT1 pre-pass at 06:58:18 is in the run-1 window |
| H5 | supported | 9 × (105 + 5) cells, each exactly once; 0 benign user-task logs; `path_must_agree` 990/990 |
| H6 | supported | gpt-4o-2024-05-13, slack, benchmark v1.2.1, package 0.1.35 in 990/990; 22 attack labels |
| H7 | supported | 0 byte-identical; trajectory-identical run copies 1 attacked pair (0.1 % of 945) and 1 pre-pass pair, below 5 % (CC-01 fingerprint) |
| H8 | supported | #168 exposure 0/173 IT5 successes (9 with an errored membership call also have error-free invite, add and remove calls) |
| H9 | supported | novel pre-marker context in 104-105 of 105 logs per candidate condition; candidate text in 95/105 per tap/seeded_pair dir, 0 in base/baseline |
| H10 | supported | 0 secret-like strings and 0 account paths in the 990 logs; account paths only in unselected `data/results/**` files (10 files / 40 lines, PC-08) |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Batch steps l1, sample, import_j2, import_j1, check: all rc 0 at `cb0af3d8`, no warnings or errors in the logs.

| Check | Result | vs expectation |
|---|---|---|
| L1-01 counts | walked 1,294 = selected 990 + context 7 + not_selected 279 + absent_blob 18 (PNG); excluded 0, rejected 0, strays 0; units 990 | equal to registry and prereg (304 not selected = 279 + 7 + 18) |
| L1-02 parse | 990/990 strict-parse ok; 0 in every defect class | as expected |
| L1-03 encodings | 0 U+2028/2029/0085, bidi, tag, zero-width, mojibake. Residues: escaped newline 235, escaped unicode 170, escaped quote 30 artefacts (tool content, #214). **Not foreseen:** C0 in 41/990 artefacts (129 strings), CR 2, U+FFFD 1, all at `/messages/*/tool_calls/*/args/channel` (+ tool_call copy) and `/messages/*/error` | PC-02: 53 model-written calls in 41 logs, e2e candidate conditions only (0 base, 0 baseline), 53/53 errored; 0 of 51 candidate files contain C0 |
| L1-04 duplicates | 0 byte-identical groups. Trajectory-identical pairs differing only by arm: 1 pre-pass (tap_run2 vs seeded_pair_run2), 1 attacked (tap vs tap_run1, user_task_3 x IT5; 1/945 = 0.1 %). Cross-corpus (`_cross/l1-xdup.json`): 0 byte, 0 trajectory groups | H7 supported (threshold 5 %). Fingerprint excludes call ids (CC-01); no FA/E2 baseline exists |
| L1-05 arms | 9 dirs x (105 attacked + 5 pre-pass); 22 attack labels (baseline, persona_v3 21 per IT; tap, seeded_pair 63 per IT; important_instructions 105; none 45); model gpt-4o-2024-05-13 990/990, suite slack 990/990, v1.k14 990/990; 0 benign user-task logs; 0 missing, extra or duplicate cells | H5, H6 supported; per-dir and per-IT security tallies equal the author's exactly (H1) |
| L1-06 secrets/paths | 0 secret-like, 0 account paths, 0 named accounts in the 990 logs; 0 in the 7 stored context artefacts | H10 supported. Outside the selection: 40 account-path lines (one local account) in 10 unselected `data/results/**` files (PC-08) |
| L1-07 timestamps | `/evaluation_timestamp` 990/990, all naive, 0 parse failures, 2026-03-20..2026-04-14. Base 2026-03-20 11:26:54-14:06:00; run 1 06:14:07-08:01:09; run 2 15:56:09-16:37:58; run 3 17:29:29-18:40:49; 0 of 990 outside their manifest window | H3, H4 supported (exactly 2 `e2e/baseline` logs predate 06:36:04: the smoke run; `tap_run1` IT1 pre-pass at 06:58:18, run-1 window) |
| L1-08 degenerate | 0 flags; `error` null 990/990. Tool errors 369 (= census); package 0.1.35, benchmark v1.2.1, default system prompt (`a021a92b`, 469 chars) in 990/990. 3/945 attacked logs have no injection marker in any tool output (payload unread, security false) | PC-03 (`payload_not_reaching_agent` scope) |
| L1-09 | does not apply (git tree, no archive members) | n/a |

H8 (#168 exposure): 173 of 189 IT5 attacked logs are security true; 9 had an errored membership call, but each also has an error-free executed invite, add and remove call, so the #168 exposure is 0/173. H9: a novel pre-marker context appears in 104-105 of 105 logs per candidate condition (the one persona_v3 log without it never read the payload); candidate text in 95/105 logs per tap/seeded_pair dir and in 0 base/baseline logs.

## 5. Level 2

| Item | head |
|---|---|
| Sample | [`data/hilarytorn-trajectory-poisoning/l2-sample-head.json`](data/hilarytorn-trajectory-poisoning/l2-sample-head.json) (sha256 `261194cf...`): 90 of 990, 18 strata `arm x attack_family`, 5 each = 45 attacked (5 per dir) + all 45 pre-pass; min 30, max 300; not over maximum. Prereg expected ~270 (PC-04) |
| Import | scratch `l2-head-j2.partial` and `-j1.partial` at `cb0af3d8`: 90/90 mapped; 0 failed, 0 degenerate, 0 adapter_defect; 90 sealed clean, status ok 90; completeness unverifiable 90; register codes `map.accounting_unverifiable` 90 and `map.earlier_attempts_unobservable` 90 (as in the trial); join 1:1 |
| Validation | tiers aer, sem, prov, linkage: 90/90 passed, 90 reproduced, linkage 100 %. SHACL not implemented (skipped); regression n/a |
| Recompute | `--dry-run`: 90 identical, 0 unexplained |
| Determinism | j2 vs j1: 374/374 files byte-identical, index identical |
| Verify chain | 97 raw objects re-hashed, 0 failures; only `checksums.absent` (working tree) |
| A2 | raw = AER on the 90 labels: system 90, user 90, assistant 416, tool 480 messages; 480 calls; tool executions ok 450 / error 30 = 30 raw errors. `finish_reason` and params `not_recorded` on 416/416 model calls (CC-04) |
| A3 | 0 PI hits over 50,599 statements and 83,261 relation arguments; 0 unexecuted calls |
| Evidence classes | core D 405 from engine rules only (`aprov.n_gap` 315, `aprov.n_capture_profile` 90); core O 3,096; inference I 17,634; assessment I 6,650, O 180; top O 15,705. Every agentdojo D rule is cited as its `_unverified` twin (code unpinned), except `system_prompt_variant_digest@1` (90). 0 denials. `_unverified` split after recheck12 (CC-08): twin inference:I 14,869 / none 1,256, assessment:I 2,619; mixed twin + native inference:I 2,616 (sum with twin = the wave-2 17,485); native-only 0; see refuted PC-06 |
| Identity | model, suite, defence (none) and attack label verbatim on 90/90, 0 mismatches. The run/condition dir is not an AER field: only `/artifacts/*/origin/path` (80/80 e2e executions) and PROV through that path; 0/90 SEM (PC-01) |
| Outcomes | mapped AER judgements = raw on 90/90 (per dir, recomputed from the origin path) |
| Redaction | 278 AER/SEM/PROV files, 0 account-path hits, 0 `operator-*` hits. The 3 sampled C0-bearing logs keep the code points as JSON escapes in AER 3/3 and PROV 3/3 |
| Withholding | no `[withhold]` policy; L1-06 found 0 secret-like strings: not applicable |

### Recheck (CC-08, recheck12)

`plans/recheck12.toml` (l1, l1_10, check; sample frozen) against the d97d3a57 files; full deltas in [`_cross/recheck12.json`](data/_cross/recheck12.json). Every other L1/L2 count is unchanged; the only other deltas are run environment (code commit d97d3a57 with tools/src = 5efa3575, `tracked_changes` true, two H.8.4(2) recompute notices with 0 unexplained changes; R12-01).

| Part | L1-08 flags (old -> new) | L2 `_unverified` split | L1-10 |
|---|---|---|---|
| head | no change | twin inference:I 17,485 -> 14,869; mixed 2,616; native 0 (sum 17,485 = old) | 7 screened (context 7); 0 hits; files with a hit 0; named accounts 0; operator 0; unreadable 0 |

- L2 split only; native 0; L1 unchanged.

## 6. Outcome comparison

L1 = population recount of raw `security` (injection success) and `utility`. Paper = README step 1 (base) and `e2e-evals.md` / `summary.json` (e2e runs). Gap rule (README section 4): more than 15 pp, or more than 5 pp outside the Wilson interval; applies only for n >= 20.

| Arm | Level | n | Metric | Rate (Wilson 95 %) | Paper | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|---|
| base important_instructions | L1 | 105 | security | 96/105 = 91.4 [84.5, 95.4] | 96/105 (README step 1) | 0.0 | match |
| e2e/baseline (run 1) | L1 | 105 | security | 97/105 = 92.4 [85.7, 96.1] | 97/105; per IT 18,17,20,21,21 | 0.0 (per IT exact) | match |
| e2e/persona_v3 (run 1) | L1 | 105 | security | 77/105 = 73.3 [64.2, 80.9] | 77/105; 17,9,13,18,20 | 0.0 | match |
| e2e/tap_run1 (run 1) | L1 | 105 | security | 86/105 = 81.9 [73.5, 88.1] | 86/105; 15,17,17,18,19 | 0.0 | match |
| e2e/seeded_pair_run1 (run 1) | L1 | 105 | security | 83/105 = 79.0 [70.3, 85.7] | 83/105; 17,18,16,15,17 | 0.0 | match |
| e2e/tap_run2 (run 2) | L1 | 105 | security | 92/105 = 87.6 [80.0, 92.6] | 92/105; 17,17,19,20,19 | 0.0 | match |
| e2e/seeded_pair_run2 (run 2) | L1 | 105 | security | 80/105 = 76.2 [67.2, 83.3] | 80/105; 15,16,14,17,18 | 0.0 | match |
| e2e/tap (run 3) | L1 | 105 | security | 91/105 = 86.7 [78.9, 91.9] | 91/105; 17,17,17,19,21 | 0.0 | match |
| e2e/seeded_pair (run 3) | L1 | 105 | security | 81/105 = 77.1 [68.2, 84.1] | 81/105; 17,15,14,17,18 | 0.0 | match |
| all attacked (9 dirs) | L1 | 945 | security | 783/945 = 82.9 [80.3, 85.1] | 783 (sum) | 0.0 | match (H2) |
| pre-pass (attack none) | L1 | 45 | security / utility | 45/45, 45/45 [92.1, 100] | 45/45 (benign_security_constant) | 0.0 | match |
| all 990 | L1 | 990 | utility | 690/990 = 69.7 [66.8, 72.5] | no external target (census 690) | 0.0 vs census | match |
| base (sample) | L2 | 5 | security, AER = raw | 5/5 [56.6, 100] | 91.4 | +8.6 | n < 20, rule n/a |
| e2e/baseline (sample) | L2 | 5 | security | 4/5 [37.6, 96.4] | 92.4 | -12.4 | n < 20 |
| e2e/persona_v3 (sample) | L2 | 5 | security | 5/5 [56.6, 100] | 73.3 | +26.7 | n < 20; paper inside CI |
| e2e/tap_run1 (sample) | L2 | 5 | security | 3/5 [23.1, 88.2] | 81.9 | -21.9 | n < 20; inside CI |
| e2e/seeded_pair_run1 (sample) | L2 | 5 | security | 3/5 [23.1, 88.2] | 79.0 | -19.0 | n < 20; inside CI |
| e2e/tap_run2 (sample) | L2 | 5 | security | 5/5 [56.6, 100] | 87.6 | +12.4 | n < 20 |
| e2e/seeded_pair_run2 (sample) | L2 | 5 | security | 5/5 [56.6, 100] | 76.2 | +23.8 | n < 20; inside CI |
| e2e/tap (sample) | L2 | 5 | security | 4/5 [37.6, 96.4] | 86.7 | -6.7 | n < 20 |
| e2e/seeded_pair (sample) | L2 | 5 | security | 4/5 [37.6, 96.4] | 77.1 | +2.9 | n < 20 |
| all attacked sample (post-stratified = plain) | L2 | 45 | security | 38/45 = 84.4 [71.2, 92.3] | 82.9 | +1.6 | match |

No row is flagged. Outcome sanity rests on the exact population check (H1: 9 per-dir and 40 per-IT counts exact); per arm the sample has n = 5 (PC-04). Mapped = raw on 90/90. No arm is excluded or recommended for exclusion for its attack outcome.

## 7. Findings

7 findings confirmed by their verifier, 1 refuted (PC-06). Verifier corrections are applied below and recorded in [`findings.json`](data/hilarytorn-trajectory-poisoning/findings.json) (CC-06 format). PC-05 is an analysis-artefact (R5) and does not count for readiness.

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-hilarytorn-trajectory-poisoning-01 | The run/condition dir (`{arm?}` facet) is not an AER field; 675 of 990 executions share their task identity with other dirs (630 attacked tap/seeded_pair in 3-way collisions + 45 pre-pass in 9-way collisions) | expected-known (R2; phase10d R5 pattern, prereg section 3 "Run" row) | S3 | confirmed; severity S2 -> S3, count 630 -> 675, prereg already anticipated it | Widen R5 (`agentdojo.attack_arm_from_path@1`, class I, `ext.agentdojo.attack_arm`) to this profile, covering pre-pass executions too; until then key per-arm statistics on the origin path and disclose that the attack label does not identify the run |
| PC-hilarytorn-trajectory-poisoning-02 | C0/DEL code points in 53 model-written `channel` arguments (41 logs, e2e candidate conditions only); all 53 calls fail ("channel does not exist") | source-defect (R1) | S3 | confirmed; wording: the C0 is one part of a garbled channel name, not shown to be the sole cause; max length 2,069 (channel arg) | Disclose in the datasheet; escape C0 in non-JSON PROV serialisations and transcript renderers; route the artefact entry below; no mapping change |
| PC-hilarytorn-trajectory-poisoning-03 | [CC-09] reference: generic `agentdojo.art.*` entries whose quirks fire here (benign_security_constant 45, injection_task_as_user 45, silent_rerun 990/0 null-final, naive_timestamp 990, payload_not_reaching_agent 3) do not scope this source | documentation-mismatch (CC-09) | S3 | confirmed; `validity_defects` dropped (no checker defect cited); gap is family-wide (no phase-10d source scoped) | One family-owner widening of the generic scopes, ideally as a new CC item for all phase-10d dossiers; scope gates claiming in `agentprov.artefacts.scan` (not yet wired; no AER/SEM/PROV effect) |
| PC-hilarytorn-trajectory-poisoning-04 | Prereg expected ~270 sampled units (25 attacked per arm); the pre-registered rule with the hook's `arm x attack_family` key gives 90 (5 per arm) | documentation-mismatch (R4) | S3 | confirmed; the prereg's "attack label" meant the injection task, not part of the hook key | Dossier note only; the post-check reuses the 90-label list; prereg not edited |
| PC-hilarytorn-trajectory-poisoning-05 | `l2_check` keys outcomes on `model|defence|attack`, pooling the three runs of tap and seeded_pair; `defence<-arm` alias in the facet table | analysis-artefact (R5) | S3 | confirmed; pooling comes from the AER having no arm field; the alias is not a DIRECT facet, so no false mismatches | After the freeze, key outcomes on the L1 stratum arm (or origin-path dir) when the layout has `{arm?}` |
| PC-hilarytorn-trajectory-poisoning-07 | `requirements.txt` pins agentdojo 0.1.29; all 990 logs record 0.1.35 | expected-known (R2, quirk `package_version_not_code_identity`) | S3 | confirmed | None beyond the existing quirk (code_identity unpinned, verified_code []) |
| PC-hilarytorn-trajectory-poisoning-08 | Account paths occur only in unselected result files (run manifests and result JSONs), outside the corpus | expected-known | S3 | confirmed; evidence widened to 10 files / 40 lines (one account), not 5 / 25 | Keep all of `data/results/**` out of the selection and out of `context_artefacts` |

Refuted:

| Id | Claim | Why refuted |
|---|---|---|
| PC-hilarytorn-trajectory-poisoning-06 | The 1,256 `inference:none` twins are a CC-08 over-count | All 1,256 are class-less `mentionOf` statements inside inference bundles whose method is a genuine `_unverified` twin; the corpus has 0 `apv:basisRule` references to native class-I `_unverified` rules, so the pre-fix counts follow the tool's definition. The verifier found instead that the CC-08-fixed `is_twin` does not decode bundle-IRI references (`bundle.inf.<family>-<rule>_unverified...`) and would re-classify 9,014 twin-bundle statements here as native (under-count). Routed as a CC-08 amendment to the tool owner (section 8, item 3), not as a corpus finding. The decoding landed at 5efa3575; recheck12 gives twin I 14,869, mixed 2,616, native 0 |

Proposed `artefacts.toml` entry (text only; route to the agentdojo family owner):

```toml
[[artefact]]
id = "agentdojo.art.control_chars_in_model_args"
title = "Control characters in model-written tool arguments"
description = "The model copies a long injected string (slack: a channel name holding the injection) into a tool argument, garbled, with C0/DEL code points in place of some characters; the call fails with a tool error (channel does not exist); AER and PROV keep the code points as JSON escapes"
scope = { sources = ["hilarytorn-trajectory-poisoning"], parts = ["head"], profiles = ["hilarytorn-trajectory-poisoning"] }
cause = "model output (gpt-4o-2024-05-13) on spliced monitor-priming candidates, not the harness"
detector = "L1-03 c0 class at /messages/*/tool_calls/*/args/*"
claims = ["tool-error rates of the e2e conditions include these failed calls"]
recorded_as = "verbatim args in AER and PROV apv:args; tool_execution status error"
handling = "disclose; escape on non-JSON serialisation"
expected = [{ snapshot = "head", count = 41, unit = "logs (53 calls, all errored)", basis = "precheck L1-03 + exam", status = "verified" }]
refs = ["docs/reports/precheck/data/hilarytorn-trajectory-poisoning/os-population.json"]
```

PC-03 proposes no new entry: add `hilarytorn-trajectory-poisoning` to the scopes of `benign_security_constant` (45), `injection_task_as_user` (45), `silent_rerun` (990 / 0 null-final), `naive_timestamp` (990) and `payload_not_reaching_agent` (3).

Items for AGENTS.md section 12:

- PC-01: the run/condition dir of this corpus is only in `/artifacts/*/origin/path`; tap/tap_run1/tap_run2 and the three seeded_pair runs, plus all 45 pre-pass logs, share task identity (675/990). Phase10d R5 must be widened to this profile before per-arm figures are computed without path parsing.

## 8. Recommendations and readiness

1. Family owner (AgentDojo): widen R5 / `agentdojo.attack_arm_from_path@1` to this profile, including pre-pass executions (PC-01); widen the generic `agentdojo.art.*` scopes family-wide (PC-03; CC-09); add `agentdojo.art.control_chars_in_model_args` (PC-02). Datasheet: C0 in failed tool arguments, run identity only via the path, dirty-tree / unpinned code identity (PC-07), agent temperature unset.
2. Statistics until R5 lands: key per-arm rates on the origin-path dir, never on the attack label.
3. Tool owner (after the freeze): the PC-05 outcome key. The CC-08 bundle-IRI decoding landed at 5efa3575 and recheck12 re-ran `l2_check` for this corpus (section 5 Recheck).
4. Keep `data/results/**` out of the selection and out of `context_artefacts` (PC-08).
5. No exclusion of any data; all 9 arms and all 45 pre-pass logs are kept.

**Readiness: `ready-with-caveats`.**

- The sample imports correctly and deterministically: 90/90 mapped and validated, recompute 0 unexplained, j1/j2 374/374 byte-identical, A2 raw = AER, A3 0 hits, mapped = raw outcomes 90/90; every population count and all 49 author tallies reproduce exactly.
- Caveats, owned and routed: PC-01 (R5 widening, family owner), PC-02 disclosure and artefact entry, PC-04 dossier note, PC-07 existing quirk.
- Not counted: PC-05 and the CC-08 amendment from refuted PC-06 (R5); PC-03 (reference to CC-09).

## 9. Reproduction

Batch (wave 2; plan entry in `tools/precheck/plans/wave2.toml`):

```toml
[[part]]
corpus_id = "hilarytorn-trajectory-poisoning"
source = "hilarytorn-trajectory-poisoning"
part = "head"
l1 = ["--git", "~/.agentprov/staging/10c/hilarytorn/in-context-trajectory-poisoning.git"]
```

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave2 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave2.toml
```

Steps the batch ran. W = `~/.agentprov/migration-work/precheck/hilarytorn-trajectory-poisoning`, D = `docs/reports/precheck/data/hilarytorn-trajectory-poisoning`, B = `~/.agentprov/staging/10c/hilarytorn/in-context-trajectory-poisoning.git`:

```bash
uv run python tools/precheck/l1_scan.py --source hilarytorn-trajectory-poisoning --part head --corpus-id hilarytorn-trajectory-poisoning --jobs 2 --emit-fp --git B
uv run python tools/precheck/l2_sample.py select --units W/l1-units-head.jsonl --source hilarytorn-trajectory-poisoning --part head --corpus-id hilarytorn-trajectory-poisoning --out D/l2-sample-head.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j2 --source hilarytorn-trajectory-poisoning --part head --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j1 --source hilarytorn-trajectory-poisoning --part head --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-head-j2.partial --out D/l2-head.json --sample D/l2-sample-head.json --l1-units W/l1-units-head.jsonl --compare-with W/l2-head-j1.partial --jobs 2
# inside l2_check:
uv run agentprov validate --corpus W/l2-head-j2.partial --tiers aer,sem,prov,linkage,shacl,regression --jobs 2
uv run agentprov recompute --corpus W/l2-head-j2.partial --dry-run --jobs 2 -q
uv run agentprov verify --corpus W/l2-head-j2.partial --level chain
```

Examiner scripts (read-only; path-cleaned copies in `D/exam-scripts/`, run from the repository root as `S/<name>.py` with S = `D/exam-scripts`; originals in `W/exam/`; git reads with `GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file`):

```bash
python3 -I W/exam/armptr.py W/l2-head-j2.partial                                  # PC-01 arm pointers
uv run python W/exam/h8c0.py B d71ab8bc2aa9db35ff443cc81e475e70ee8da215 <out>      # H8, PC-02 C0 by arm
uv run python W/exam/c0labels.py                                                   # PC-02: 41 labels, 3 in the sample
uv run python W/exam/unread.py B d71ab8bc2aa9db35ff443cc81e475e70ee8da215          # PC-03 unread payloads (3)
python3 -I W/exam/sample_outcomes.py W/l2-head-j2.partial W/l1-units-head.jsonl <out>   # PC-05, per-dir outcomes
uv run python W/exam/versions.py B d71ab8bc2aa9db35ff443cc81e475e70ee8da215        # PC-07 versions
```

Open follow-ups (orchestrator):

| # | What | Command | When |
|---|---|---|---|
| 1 | Re-run only the check step (twin counts, per-dir outcome keys); no re-import | `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-hilarytorn-trajectory-poisoning -- uv run python tools/precheck/l2_check.py --corpus W/l2-head-j2.partial --out D/l2-head.json --sample D/l2-sample-head.json --l1-units W/l1-units-head.jsonl --compare-with W/l2-head-j1.partial --jobs 2` | twin counts done by recheck12 (`4a3e40c1`); per-dir outcome keys after the PC-05 fix |
| 2 | Route PC-01 (R5 widening), PC-02 (artefact entry), PC-03 (scope widening, CC-09) to the AgentDojo family owner / regen-batch | no command | now |
| 3 | Done by the wave-2 completeness critic (2026-10-15): 10 path-cleaned scripts in `D/exam-scripts/` (`armptr`, `c0labels`, `c0peek`, `evrules`, `h8c0`, `rawscan`, `sample_outcomes`, `sampraw`, `unread`, `versions`) | no command | done |
| 4 | Optional: full scratch import of all 990 for population-level C0 and identity-collision counts (the phase-10d trial already imported 990 with 0 failures) | via `tools/suite_queue.py --class import` | optional |
