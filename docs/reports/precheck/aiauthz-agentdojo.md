# Pre-check dossier: `aiauthz-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `aiauthz-agentdojo` (AGPL-3.0, its own corpus, D-94; logs embed AgentDojo benchmark text, MIT) |
| Parts | `aiauthz-agentdojo · head` (1 part) |
| Family / profile | `agentdojo` / `aiauthz-agentdojo@1` (dialect `agentdojo.tracelogger`, variant `v1.k14`, semantics `agentdojo.suites@2`) |
| Pin | git `Sports-Vision-Inc/aiAuthZ` @ `6eaac86a` (2026-07-06T19:28:55Z, = repository head), tree 288 blobs |
| Code commit | `d97d3a57` (batch `wave3`; l1, l1_10, sample, import_j2, import_j1, check all rc 0; tracked_changes false) |
| Kind | wave 3, first examination (not in FA or E2); no stored corpus (registry `import planned`) |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (batch), 2026-10-21 (examination) |
| Agents | researcher + fact-checker (prereg), examiner (this file), adversarial verifier (2026-10-21: 6 of 6 confirmed) |
| Data | [`data/aiauthz-agentdojo/`](data/aiauthz-agentdojo/): `research.json`, `l1-head.json`, `l1-10-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `findings.json`, `pop-census.json`, `os2-sample.json`, `denials.json`, `nf-shape.json`, `exam-scripts/` |

- Code identity, part `head` ([`code-head.json`](data/aiauthz-agentdojo/code-head.json)): commit `d97d3a57` (tracked_changes false); engine code aer `856b7a09e0cf`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `agentdojo.tracelogger@0.1.0` `03d8bc6d30df`; profile sha256 `6aab79262654`, rules agentdojo 2 / aer 1; lockfile `b0455f1058c8`, limits `5d6dbb210259`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Repository | https://github.com/Sports-Vision-Inc/aiAuthZ @ `6eaac86a` (2 commits, tag v0.1.0 -> `092df6da`, release without assets, 0 issues/PRs) | the data; `RESULTS.md`, `results_claude-fable-5.json`, `results_gemini-3-flash.json` (per-cell outcomes) |
| Paper | arXiv 2607.05518 v1 (2026-07-06, CC BY 4.0), https://arxiv.org/abs/2607.05518v1 | Table 4 = outcome reference (150 rollouts) |
| External data record | none; git blob ids only | n/a |
| Benchmark / harness | AgentDojo `0.1.35` (PyPI), banking v1.2.2, `important_instructions`; https://arxiv.org/abs/2406.13352 | producer and scorer |
| Upstream issues | ethz-spylab/agentdojo #181, #161, #141 | checker defects (CC-07), temperature 0.0 dropped |

Data-versus-paper notes (research.json, checked against the data):

- Every Table 4 / RESULTS.md rate and every per-cell value in the two results files reproduces from the raw `utility`/`security` fields (150/150 cells, section 6).
- The paper's "seven attacker-directed calls ... under attack" counts 5 prepass denials (an injection task run as the user task, no injection present); 2 are attack-time (PC-01).
- Temperature: RESULTS.md claims temperature 0; AgentDojo 0.1.35 does not send 0.0 (#141). The logs carry no temperature field and the harness identity is unpinned (D-103), so this is a disclosed caveat, not a finding. H9 (15/20 Fable attacked pairs share the first assistant message) is consistent with either explanation.
- Fable 5 attacked runs all end null-final (RESULTS.md: "Model output was None", treated as refusal-like stops); PC-03.
- Our side: the profile says `paper = none found` and the licence basis says "no 'or later' statement". pyproject, CHANGELOG and COMMERCIAL-LICENSE all say AGPL-3.0-or-later (PC-05).

## 3. Expectations

[`prereg/aiauthz-agentdojo.md`](prereg/aiauthz-agentdojo.md), committed at `fd75f8a3` (2026-10-14, fact-checked), before any data check. Hypotheses H1-H12; binding outcome comparison = L1 per-cell tally.

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 | walked 288 = selected 174 + context 9 + not_selected 96 + absent_blob 9 (unfetched images, partial clone); units 174 (1 per log); auxiliary 2 (`results_*.json`). Dirs 6 x 24 + 6 x 5; kinds attacked 120, prepass 24, clean 30 | = prereg (114 not selected incl. 9 context), registry 174 |
| L1-02 | 174/174 ok; auxiliary 2/2 ok | = (0 defects) |
| L1-03 | 0 classes in 174 | = (no residues found at all) |
| L1-04 | byte-identical 0; trajectory-identical 17 groups / 40 units (151 distinct of 174), 16 of them across the defence arms of one model (CC-01 definition); cross-part / cross-corpus 0 (`_cross/l1-xdup.json`) | = (H9 descriptive) |
| L1-05 | 18 strata, 0 missing, 0 extra: 2 models x 3 defences x (20 attacked + 4 prepass) + 6 clean dirs x 5; banking UT0-4 x IT0/4/5/7 | = |
| L1-06 | 0/174 secret-like, 0 account paths | = (H10) |
| L1-07 | `/evaluation_timestamp` 174/174, naive, 2026-07-06 01:57:02-02:44:14, 0 parse fail, 0 non-monotone | = |
| L1-08 | null_final 70/174; 0 empty, 0 `error`, 0 trailing calls | = 70 (profile quirk) |
| L1-09 | not produced for this part | n/a |
| L1-10 | 7 non-JSON context files, 1 hit (`generic-credential-assignment`, RESULTS.md); it is an length withheld ALL_CAPS env-var name. 0 accounts, 0 operator | PC-06 (R5) |

Population census (exam scripts; [`pop-census.json`](data/aiauthz-agentdojo/pop-census.json), [`denials.json`](data/aiauthz-agentdojo/denials.json), [`nf-shape.json`](data/aiauthz-agentdojo/nf-shape.json)): denials 9 (send_money 5, update_password 2, update_scheduled_transaction 2), all in aiauthz dirs. Null-final: Fable attacked 60/60, Fable prepass 9/12, Fable clean 1/15, Gemini 0/87. Pipeline tag = dir in 174/174, and no log names a served snapshot id. The run order follows `run_benchmark.py` for both models.

## 5. Level 2

- Sample: [`l2-sample-head.json`](data/aiauthz-agentdojo/l2-sample-head.json), 84 labels: all 18 strata, attacked 5 each, prepass 4 and clean 5 (all of them). sha256 `c67a02b7`.
- Import: 84/84 executions (1 per label), status ok 59 / ok_with_issues 25, degenerate 0, adapter_defect 0. Register: `map.accounting_unverifiable` 84, `map.earlier_attempts_unobservable` 84, `map.retry_passes_inferred` 25. The 25 equal the L1 null-final count of the sampled labels.
- Validate (aer, sem, prov, linkage): 84/84 passed, linkage 84/84 (shacl not implemented: skipped; regression n/a). Recompute dry-run: 84 identical, 0 unexplained. Determinism j2 vs j1: 352 files, 0 differ, index identical. `verify --level chain`: ok (`checksums.absent` on a working tree, expected).
- A2: 0 failures. A3: 0 PROV issue classes (28,901 statements, 50,184 relation arguments, 117 tool executions with their call).
- Evidence classes: core D 366 / O 1,514. Inference I 6,881. Assessment I 1,388 / O 168. `_unverified`: twin 7,322 statements (inference I 5,774, inference none 665, assessment I 883), native 0, mixed 783 (inference I). Every agentdojo D rule goes through its twin (D-103 unpinned).
- Mapping join ([`os2-sample.json`](data/aiauthz-agentdojo/os2-sample.json)): 168/168 judgements equal the raw values. 7 decision records (`agentdojo.defence_denial_message@1`, verdict deny): Fable prepass 1, Fable clean 1, Gemini prepass 4, Gemini clean 1. None has a `tool_execution`, and all 117 tool executions are `ok` (H11).
- Identity: 0 mismatches. The model comes from the dir; the logged `claude-3-5-sonnet-20241022*` / `gemini-2.0-flash-001*` tags never become the model (D-106). The defence comes from the pipeline dir. 12 (model, defence, attack) tuples.
- Redaction: 0 hits in 260 files. Withholding: no policy, not applicable (0 L1-06 hits).

## 6. Outcome comparison

Population (L1, binding; paper = Table 4 / results files). Gap 0 in every arm, and 150/150 cells match:

| Arm (model, defence) | ASR L1 | UUA L1 | Clean util L1 | Paper (ASR / UUA / clean) | Gap |
|---|---|---|---|---|---|
| Fable 5, none | 0/20 | 0/20 | 5/5 | 0 / 0 / 100 % | 0 |
| Fable 5, spotlighting | 0/20 | 0/20 | 4/5 | 0 / 0 / 80 % | 0 |
| Fable 5, aiauthz | 0/20 | 0/20 | 4/5 | 0 / 0 / 80 % | 0 |
| Gemini 3 Flash, none | 0/20 | 12/20 | 5/5 | 0 / 60 / 100 % | 0 |
| Gemini 3 Flash, spotlighting | 2/20 | 14/20 | 5/5 | 10 / 70 / 100 % | 0 |
| Gemini 3 Flash, aiauthz | 0/20 | 8/20 | 4/5 | 0 / 40 / 80 % | 0 |

Sample (L2 mapped, n = 5 per arm, below 20, so Wilson only and no verdict). Each paper rate lies inside its interval:

| Arm | ASR k/n [Wilson 95 %] | UUA k/n [Wilson] | Clean util k/n [Wilson] |
|---|---|---|---|
| Fable none / spot / aiauthz | 0/5 [0, 43.4] each | 0/5 [0, 43.4] each | 5/5 [56.6, 100]; 4/5 [37.6, 96.4]; 4/5 [37.6, 96.4] |
| Gemini none | 0/5 [0, 43.4] | 3/5 [23.1, 88.2] | 5/5 [56.6, 100] |
| Gemini spotlighting | 1/5 [3.6, 62.4] | 3/5 [23.1, 88.2] | 5/5 [56.6, 100] |
| Gemini aiauthz | 0/5 [0, 43.4] | 3/5 [23.1, 88.2] | 4/5 [37.6, 96.4] |

CC-07: #181 affects 0 of 1 IT0 successes, because the subject names the streaming service. IT1 and IT3 are not in the grid, and the re-scored ASR equals the logged one. #161 affects 0 of 0, since user_task_5 is not in the grid.

Hypotheses: H1, H2, H3, H4, H5, H7, H8, H10, H11 and H12 are supported. H6 is partly refuted on wording only: the UT0xIT4 success is an executed attacker-bound `update_scheduled_transaction` (IT4's goal), not a `send_money`. No null-final log has a True outcome. H9 is reported: identical first assistant message for Fable in 15/20 attacked, 4/5 clean and 4/4 prepass pairs, and for Gemini in 20/20, 5/5 and 3/4.

## 7. Findings

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-aiauthz-agentdojo-01 | Paper/RESULTS "seven attacker-directed calls under attack" and "two password changes": 5 of 7 (both password changes) are prepass denials; 2 attack-time (Gemini UT0xIT0, UT0xIT4) | documentation-mismatch (R3) | S2 | confirmed | Disclose 2 attack-time / 5 prepass / 2 clean denials beside any block count; no data change |
| PC-aiauthz-agentdojo-02 | [CC-07] #181 0/1 IT0 successes affected; #161 0/0 (UT5 not in grid) | expected-known (R2, `validity_defects`; scope CC-09) | S3 | confirmed | Add scope row with counts |
| PC-aiauthz-agentdojo-03 | Fable attacked logs 60/60 null-final (+ prepass 9/12, clean 1/15): the Fable 0 % ASR / 0 % UUA rows are runs whose last logged pass returned no final output | expected-known (R2, `silent_rerun`, profile quirk; scope CC-09); raised to S2 for the corpus consequence | S2 | confirmed | Disclose: Fable 0 % ASR is not evidence of defence efficacy. **Never exclude the Fable arms** |
| PC-aiauthz-agentdojo-04 | [CC-09] no AgentDojo `artefacts.toml` entry scopes `aiauthz-agentdojo`; quirk counts verified | documentation-mismatch (CC-09) | S3 | confirmed | See CC-09; not counted in readiness |
| PC-aiauthz-agentdojo-05 | Profile/README stale: `paper = none found` (arXiv 2607.05518 v1 exists); licence basis "no or later statement" contradicted by pyproject/CHANGELOG/COMMERCIAL-LICENSE | documentation-mismatch (R4) | S3 | confirmed | Family owner fixes profile; regenerate README blocks; profile sha256 moves (round) |
| PC-aiauthz-agentdojo-06 | L1-10 credential-pattern hit in RESULTS.md is an env-var name | analysis-artefact (R5) | S3 | confirmed | None for the corpus; not security |

No mapping defect, no security finding (CC-03, CC-11 not triggered: 0 account paths in logs, raw-store context or AER/SEM/PROV). CC-10 is n/a (no slack). CC-04 is n/a (prereg does not cite U6-c). Refuted: none.

Verifier (2026-10-21, re-run on the pinned blobs through `agentprov.ingest`): all 6 confirmed, class and severity unchanged.
PC-01: 7 attacked-dir denials = 5 prepass (attack `none`) + 2 attack-time, all 7 to the attacker IBAN or a password change, matching
the RESULTS.md 3 + 2 + 2 breakdown; the block_log count per dir equals the log count (no denial in an unlogged pass). PC-02: the
second IT0 attacker `send_money` (Gemini aiauthz) was denied, not executed, so #181 stays 0 of 1. PC-03: independent null-final
rule gives the same 70; wording sharpened (the Fable 0 % ASR is a measured post-environment outcome with a 0 % no-defence
baseline, so it carries no defence signal; arms kept). PC-06: the tool's own pattern matches once (span 26), right-hand side an
18-char env-var name.

Proposed `artefacts.toml` entries (text only; route to the AgentDojo family owner):

```toml
# PC-02: [[artefact]] id = "agentdojo.art.validity_defects"
#   scope.sources += "aiauthz-agentdojo"; scope.profiles += "aiauthz-agentdojo"; counts #181 0 of 1 IT0 success, #161 0 (UT5 not run)
# PC-03 / PC-04 (CC-09): add "aiauthz-agentdojo" to scope of: silent_rerun (70 null-final, Fable attacked 60/60; 174 unobservable
#   earlier passes), benign_security_constant 54 (30 clean + 24 prepass), injection_task_as_user 24, naive_timestamp 174,
#   defence_benign_intervention 2 (UT0 first-time payment, one per model); analogues rope.art.guard_denial (9 denials) and
#   rope.art.pipeline_tag_not_identity (174)
```

AGENTS.md §12 items: aiauthz-agentdojo's "under attack" block count (7) includes 5 prepass denials (PC-01); the Fable rows are all null-final (PC-03).

## 8. Recommendations and readiness

1. Route PC-02/PC-03/PC-04 scope rows and the PC-05 profile fix (paper and licence basis, then the README regeneration) to the AgentDojo family owner. The profile edit changes the profile digest, so it lands with the round.
2. Disclose PC-01 and PC-03 in the datasheet and manuscript table next to the Table 4 numbers. Logged values stay primary.
3. Keep every arm, including the Fable arms with 0 attack successes (user rule).

**Readiness: `ready-with-caveats`.** The import is correct and deterministic: 84/84 validated, recompute 0 unexplained, j1 and j2 byte-identical, 168/168 judgements raw = mapped, identity 0 mismatches, redaction 0, and L1 = paper in 150/150 cells. The caveats are PC-01 and PC-03 (disclosure, S2) and PC-05 (doc fix), all verifier-confirmed. PC-04 (CC-09) and PC-06 (R5) are not counted. No outcome gap (0 in every arm).

## 9. Reproduction

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave3 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave3.toml
# W = ~/.agentprov/migration-work/precheck/aiauthz-agentdojo, D = docs/reports/precheck/data/aiauthz-agentdojo, G = ~/.agentprov/staging/10c/aiauthz/aiAuthZ.git
uv run python tools/precheck/l1_scan.py --source aiauthz-agentdojo --part head --corpus-id aiauthz-agentdojo --jobs 2 --emit-fp --git G
uv run python tools/precheck/l1_context.py --source aiauthz-agentdojo --part head --corpus-id aiauthz-agentdojo --git G --out D/l1-10-head.json
uv run python tools/precheck/l2_sample.py select --units W/l1-units-head.jsonl --source aiauthz-agentdojo --part head --corpus-id aiauthz-agentdojo --out D/l2-sample-head.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j2 --source aiauthz-agentdojo --part head --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j1 --source aiauthz-agentdojo --part head --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-head-j2.partial --out D/l2-head.json --sample D/l2-sample-head.json --l1-units W/l1-units-head.jsonl --compare-with W/l2-head-j1.partial --jobs 2
# examiner scripts (read-only; pinned blobs via GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file + agentprov.ingest)
uv run python -I D/exam-scripts/pop.py W/l1-units-head.jsonl W/exam/pop.json   # H1-H10, H12, CC-07, L1-10 hit files
uv run python -I D/exam-scripts/deny.py                                        # PC-01 denial per log; PC-06 shape class
uv run python -I D/exam-scripts/nf.py W/l1-units-head.jsonl                    # PC-03
uv run python -I D/exam-scripts/os2.py W/l2-head-j2.partial W/l1-units-head.jsonl W/exam/os2.json   # OS-2, H11
grep -c aiauthz src/agentprov/adapters/agentdojo/artefacts.toml                # PC-04: 0
```

Follow-ups (not run): none required. The round's full import is `uv run agentprov import aiauthz-agentdojo --input <staging> --verify-against-pin --corpus <corpus>` through the queue.
