# Pre-check dossier: `environmentoptim-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `environmentoptim-agentdojo` (MIT, LICENSE at the pin; no data licence) |
| Parts | `head` (1 part). The frame excludes the 6,016 `select.redaction_pending` Qwen3.5 logs (D-255, R-10j-1; amendment 5) |
| Family / profile | `agentdojo` / `environmentoptim-agentdojo@1` (dialect `agentdojo.tracelogger`, variant `v1.k14`, semantics `agentdojo.suites@3`) |
| Pin | git `omseeth/EnvironmentOptim` @ `febf82d8` (2026-07-18T11:07:08Z, branch head) |
| Code commit | `d97d3a57` (L1, sample, both imports, check; batch `wave7`, all steps rc 0; tracked changes true, PC-08) |
| Kind | wave 7, first examination (not in FA or E2); no stored corpus |
| Date | 2026-10-14 (prereg, research), 2026-10-16 (batch), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), examiner (this dossier), adversarial verifier (2026-10-21: 8/8 confirmed, 0 refuted) |
| Data | [`data/environmentoptim-agentdojo/`](data/environmentoptim-agentdojo/): `research.json`, `l1-head.json`, `l1-10-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `pop-census.json`, `os2-sample.json`, `exam.json`, `findings.json`, `exam-scripts/` (`pop.py`, `os2.py`) |

- Code identity, part `head` ([`code-head.json`](data/environmentoptim-agentdojo/code-head.json)): commit `d97d3a57` (tracked_changes true; descendant of the CC-08 fix 5efa3575); engine code aer `856b7a09e0cf`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `agentdojo.tracelogger@0.1.0` `03d8bc6d30df`; profile sha256 `f55a44bd89b2`, rules agentdojo 2 / aer 1; lockfile `b0455f1058c8`, limits `5d6dbb210259`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Repository | https://github.com/omseeth/EnvironmentOptim @ `febf82d8` (456 commits, 0 tags/releases/issues) | the data; mapped dir `runs/gpt-5.4-2026-03-05/` added in `7b684d0d` (2026-05-27T17:09:58Z), unchanged since |
| Study | Master thesis (M. Seeth, LMU/TUM), no public PDF/DOI; `optimization/analysis/report_results.log` | no rate for the mapped arm |
| Benchmarks | AgentDojo https://arxiv.org/abs/2406.13352; AgentDyn https://arxiv.org/abs/2602.03117 | 4 + 3 suites |
| Harness | AgentDyn fork vendored in `src/agentdojo` (AgentDyn@`bd3fc6bc` + `bfdd3ec7`), `agentdojo 0.1.35` | profile `code_identity = "unpinned"` |
| Upstream issues | SaFo-Lab/AgentDyn [#8](https://github.com/SaFo-Lab/AgentDyn/issues/8) (open); ethz-spylab/agentdojo #161, #181 | PC-01, PC-02 |
| Data record | none (Zenodo/HF/Figshare 0) | git blob ids only |

Data-versus-paper notes: the gpt-5.4 runs are train-split data-collection (SFT teacher) runs; no thesis number reads them (PC-06). Every log has `benchmark_version` v1.2.2 and package 0.1.35; the scoring code is the AgentDyn fork, not AgentDyn@`5353cf76`.

## 3. Expectations

Pre-registration: [`prereg/environmentoptim-agentdojo.md`](prereg/environmentoptim-agentdojo.md), committed in `eb7151ee` (2026-10-15), before any data check of this corpus. Amendments 2, 3 and 5 apply. Classes follow R1-R6 and CC-01..CC-11 of [`cross-cutting.md`](cross-cutting.md).

| H | Result | Note |
|---|---|---|
| H1 | supported | 104 selected (11/13/13/13/14/13/27), ids `user_task_0..N-1`; owned_elsewhere 84,360 (36,679 + 47,681); redaction_pending 6,016; 90,480 logs; 93,042 present blobs (94,764 walked − 1,722 absent) |
| H2 | supported | strict ok 104/104 |
| H3 | supported | 0 controls, bidi, tag, surrogate, U+FFFD |
| H4 | supported | 0 byte-identical, 0 fingerprint groups (104 distinct); 0 cross-corpus groups in `_cross/l1-xdup.json` |
| H5 | supported | `pipeline_name`, attack null, injection null, suite/task = path: 104/104 each |
| H6 | refuted as worded | 0 account paths, but 15 logs with credential-shaped benchmark strings (PC-03) |
| H7 | supported | 104/104 naive, 2026-05-27 17:33:02..18:00:16, inside the bounds; zone note PC-04 |
| H8 | supported | 0 empty/zero-message/null-final/trailing/error-only; `error` null 104 |
| H9 | supported | security true 104/104; github UT5/7/8/11 utility false 4/4 (PC-01) |
| H10 | supported | benign_security_constant 104; placeholder args 584/584 null; 0 prepass, null-final, trailing calls, call-id anomalies; system prompt `21a1c00db164`/543 × 104 |
| H11 | supported | v1.2.2 × 104; 0.1.35 × 104; one top-level key set (14 keys) |
| H12 | supported | L2 35/35 ok, 0 failures, recompute 0 diff, j1 = j2, identity 35/35 |
| H13 | reported | section 6 |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: staged bare clone at `febf82d8` (`--git`), `l1_scan` at `d97d3a57`, 2.2 s.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 94,764 walked: 104 selected, 36,679 owned_elsewhere (agentdojo-upstream), 47,681 owned_elsewhere (agentdyn incl. 620 DRIFT), 6,016 redaction_pending, 5 context, 2,557 not selected, 1,722 absent blobs (none a log). Units 104 = registry | exact |
| L1-02 parse | ok 104/104; 0 of every defect class; auxiliary 0 | as expected |
| L1-03 encodings | escape residues in tool outputs only (`/messages/*/content/*/content`): `\n` 40 files / 55 strings, `\"` 3/3, `\uXXXX` 14/18; 0 controls, bidi, tag, zero-width, U+FFFD | as expected |
| L1-04 duplicates | 0 byte-identical, 0 trajectory groups (CC-01 definition); cross-corpus 0 | as expected |
| L1-05 arms | 7 strata = 7 cells (gpt-5.4 × none × none × 7 suites); 0 missing, 0 extra; test-split tasks absent by design | as expected |
| L1-06 secrets/paths | `generic-credential-assignment` 15/104 logs (dailylife 9, github 5, shopping 1), 1 pointer; exam: 33 matches, all `password`, all role `tool`, 3 distinct values; 0 private-key headers (CC-02 not instantiated); 0 account paths incl. `_ceph_ssd_students_`; 0 operator hits | PC-03 |
| L1-07 timestamps | `/evaluation_timestamp` 104/104 naive, 0 parse fail, one 27-minute window on 2026-05-27; other timestamp pointers are benchmark calendar args | PC-04 |
| L1-08 degenerate | only flag `secret_like` (15); 0 empty, tiny, zero-message, error-only, incomplete, null-final, trailing calls | as expected |
| L1-09 | not run for this part (include holds only the 104 logs; auxiliary 0) | n/a |
| L1-10 context | 5 context files screened, 0 hits, 0 operator | as expected |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`l2-sample-head.json`](data/environmentoptim-agentdojo/l2-sample-head.json) (sha256 `c8ed04331f64…`): 35 of 104, 7 strata × 5, seed 20261011, frame without redaction_pending |
| Import | `l2-head-j2.partial`, `-j1.partial`; 35/35 ok, 0 degenerate, 0 `adapter_defect`; join 35 → 35 (1:1) |
| Validation | aer, sem, prov, linkage: 35/35 pass, 35 reproduced, linkage 100 %; SHACL skipped (not implemented); regression n/a |
| Recompute | `--dry-run`: 35 identical, 0 unexplained |
| Verify chain | 0 failures; only `checksums.absent` (working tree) |
| Determinism | j2 vs j1: 152/152 files identical, index identical |
| A2 | `map.accounting_unverifiable` 35, `map.earlier_attempts_unobservable` 35 (index and seal); completeness unverifiable 35 |
| A3 | 0 issues over 20,418 statements / 33,391 relation arguments; 375 messages with `generated_by`, 176 model calls with input, 199 tool executions with call |
| Evidence classes | AER: agentdojo D rules only via `_unverified` twins (`verified_code = []`). PROV: core D 140 / O 1,229; inference I 7,255; assessment I 2,985 / O 70; top O 6,020. Twin/native/mixed split (post-CC-08 counter): twin 7,905 (inference I 6,412, inference none 515, assessment I 978), native 0, mixed 808 (inference I) |
| Judgements | utility `checker` 35; security `harness_default` 35 (benign constant). OS-2 raw vs mapped: 0 of 70 differ |
| Identity | model `gpt-5.4-2026-03-05` 35/35; defence `none` (from pipeline_dir); attack none; suites 7 × 5; 0 unresolved, 0 mismatches |
| Redaction | 113 files scanned, 0 hits; 5 sampled logs carry the PC-03 fixture strings verbatim (benchmark fiction) |
| Withholding | no policy (D-257); not needed (0 account paths) |

## 6. Outcome comparison

No published rate exists for this arm, so the gap rule cannot fire; rates are descriptive (R6). L1 = population raw booleans; L2 = mapped AER of the sample (= raw for the same labels).

| Arm (gpt-5.4 / none / none) | L1 n | L1 utility (Wilson 95 %) | L2 n | L2 utility (Wilson 95 %) | Paper | Verdict |
|---|---|---|---|---|---|---|
| banking | 11 | 81.82 (9/11) [52.30, 94.86] | 5 | 100.0 (5/5) [56.55, 100] | none | descriptive |
| dailylife | 13 | 84.62 (11/13) [57.77, 95.67] | 5 | 80.0 (4/5) [37.55, 96.38] | none | descriptive |
| github | 13 | 69.23 (9/13) [42.37, 87.32] | 5 | 80.0 (4/5) [37.55, 96.38] | none | 4 structural false (PC-01) |
| shopping | 13 | 53.85 (7/13) [29.14, 76.79] | 5 | 60.0 (3/5) [23.07, 88.24] | none | descriptive |
| slack | 14 | 100.0 (14/14) [78.47, 100] | 5 | 100.0 (5/5) [56.55, 100] | none | descriptive |
| travel | 13 | 84.62 (11/13) [57.77, 95.67] | 5 | 100.0 (5/5) [56.55, 100] | none | descriptive |
| workspace | 27 | 100.0 (27/27) [87.54, 100] | 5 | 100.0 (5/5) [56.55, 100] | none | descriptive |
| pooled | 104 | 84.62 (88/104) [76.46, 90.30] | 35 | 88.57 (31/35) [74.05, 95.46] | none | descriptive |
| github without UT5/7/8/11 (info) | 9 | 100.0 (9/9) | | | | not the logged metric |
| pooled without UT5/7/8/11 (info) | 100 | 88.00 (88/100) | | | | not the logged metric |

Security 104/104 true is the runner's constant (`benign_security_constant`), not an observation. CC-07: #161 banking UT5 1 log, utility true with an executed 5.00 payment to the Spotify fixture IBAN (no tool error): 0 of 1 vacuous, banking re-scored 9/11 unchanged; #181: 0 attacked logs, n/a.

## 7. Findings

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-environmentoptim-agentdojo-01 | AgentDyn #8: github UT5/7/8/11 utility false 4/4 (unreachable); github 9/13 logged, 9/9 reachable | source-defect (R1; no `artefacts.toml` entry) | S2 | confirmed | Disclose; keep booleans; new entry below (also covers agentdyn, rope, drift) |
| PC-environmentoptim-agentdojo-02 | [CC-07] #161 0/1 vacuous (payment executed); #181 n/a (0 attacked) | expected-known (R2, CC-07; scope CC-09) | S3 | confirmed | Add scope with count 0 |
| PC-environmentoptim-agentdojo-03 | Credential-shaped AgentDyn fixture strings in 15 logs (33 matches, 3 distinct, all `password`, tool outputs); H6 refuted as worded | source-defect (CC-13 fixture, uncatalogued: R1, PC-rope-07 entry `agentdojo.art.fixture_secret_shapes` proposed; reclassified 2026-10-21 from expected-known) | S3 | confirmed | Add snapshot count; census §8 note (R4) |
| PC-environmentoptim-agentdojo-04 | Naive timestamps 17:33–18:00 vs commit 17:09:58Z: clock ≥ UTC+00:51 (CEST likely) | expected-known (`naive_timestamp`; scope CC-09) | S3 | confirmed | Datasheet note; no zone in PROV |
| PC-environmentoptim-agentdojo-05 | [CC-09] reference: no entry scopes this source; profile observed counts reproduce | documentation-mismatch (CC-09) | S3 | confirmed | Not counted separately |
| PC-environmentoptim-agentdojo-06 | Profile/identity-table call the part "benign utility reference runs"; they are train-split teacher runs no thesis number uses | documentation-mismatch (R4) | S3 | confirmed | Reword basis text (family owner) |
| PC-environmentoptim-agentdojo-07 | Three tracked docs carry the unmasked cluster account segment D-255 masks (1 line each) | documentation-mismatch (R4); **security** | S2 | confirmed | Report to orchestrator now; mask per D-255 |
| PC-environmentoptim-agentdojo-08 | Batch code identity `tracked_changes = true` | analysis-artefact (R5) | S3 | confirmed | Compare digests |

Verifier (2026-10-21): 8/8 confirmed, 0 refuted, no class or severity change. Checks: `pop.py` and `os2.py` re-run byte-equal to the committed JSON; PC-01 vendored github `user_tasks.py` blob = AgentDyn `5353cf76`/`bd3fc6bc`, suite data and tools trees identical, no `v1_2*` github override, `unwinnable_cell` covers upstream injection cells only; PC-03 the 3 distinct values occur verbatim in the vendored suite YAML; PC-04 commit zone +02:00 (CEST supported); PC-07 tracked-file grep gives the 3 files (one segment) plus a test with synthetic values only (not a hit), S2 per the CC-11 ruling; PC-08 code digests equal 12 clean-tree parts at `d97d3a57`. Reasoning per finding in `findings.json` `verdicts`.

Refuted: none. No mapping defect. Security: PC-07 (our docs, not the corpus; 0 hits in AER/SEM/PROV or the 104 raw logs).

Proposed `artefacts.toml` entries (text only; to the AgentDojo family owner):

```toml
# PC-01 (new)
# [[artefact]] id = "agentdyn.art.github_ut_unreachable_utility"; cause = "harness"
#   refs = ["https://github.com/SaFo-Lab/AgentDyn/issues/8"]
expected += [{ snapshot = "environmentoptim-agentdojo:head", count = 4, unit = "executions", basis = "pre-check PC-environmentoptim-agentdojo-01: github user_task_5/7/8/11 utility false 4/4", status = "proposed" }]
# PC-02 -> agentdojo.art.validity_defects: { snapshot = "environmentoptim-agentdojo:head", count = 0, unit = "executions", basis = "#161 banking UT5 1/1 with executed payment; #181 n/a", status = "proposed" }
# PC-03 -> agentdojo.art.fixture_secret_shapes (PC-rope-07): { snapshot = "environmentoptim-agentdojo:head", count = 15, unit = "logs", basis = "L1-06 generic-credential-assignment (AgentDyn fixtures)", status = "proposed" }
# PC-04/05 (CC-09): scope environmentoptim-agentdojo in benign_security_constant 104, naive_timestamp 104, package_version_unknown 0
```

Items for AGENTS.md §12:

- PC-01: EnvironmentOptim gpt-5.4 github utility 9/13 as logged; 4 tasks cannot pass (AgentDyn #8). Pooled 88/104 (84.62 %), 88/100 on reachable tasks. A harness defect, never a model property.
- PC-07: three tracked docs held the unmasked cluster account segment of the held Qwen logs (pending mask per D-255).

## 8. Recommendations and readiness

1. PC-07 to the orchestrator at once (security rule); doc owners mask the segment.
2. Verifier pass done (8/8 confirmed).
3. Route PC-01 (new entry), PC-02/03/04 scope rows and PC-06 rewording to the AgentDojo family owner (CC-07, CC-09).
4. Disclose github utility with the AgentDyn #8 note next to any utility figure from this part.
5. The 6,016 held logs stay out until D-255 / R-10j-1 lands; then a separate pre-check of that part.
6. No exclusion of any data.

**Readiness: `ready-with-caveats`** (confirmed by the verifier; no outcome gap, no paper rate). The part maps cleanly and deterministically (35/35 ok, validate 35/35, recompute 0, j1 = j2 152 files, OS-2 0/70, identity 0 mismatches, redaction 0). L1 counts match the prereg exactly. Caveats: PC-01 disclosure (S2), PC-07 (our docs, security). Not counted: PC-05 (CC-09 reference), PC-08 (R5).

## 9. Reproduction

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave7 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave7.toml
```

Steps (W = `~/.agentprov/migration-work/precheck/environmentoptim-agentdojo`, D = `docs/reports/precheck/data/environmentoptim-agentdojo`):

```bash
uv run python tools/precheck/l1_scan.py --source environmentoptim-agentdojo --part head --corpus-id environmentoptim-agentdojo --jobs 2 --emit-fp --git ~/.agentprov/staging/10c/environmentoptim/EnvironmentOptim.git
uv run python tools/precheck/l2_sample.py select --units W/l1-units-head.jsonl --source environmentoptim-agentdojo --part head --corpus-id environmentoptim-agentdojo --exclude-profile-code select.redaction_pending --out D/l2-sample-head.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j2 --source environmentoptim-agentdojo --part head --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j1 --source environmentoptim-agentdojo --part head --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-head-j2.partial --out D/l2-head.json --sample D/l2-sample-head.json --l1-units W/l1-units-head.jsonl --compare-with W/l2-head-j1.partial --jobs 2
# examiner (read-only)
uv run python -I D/exam-scripts/pop.py W/exam/pop.json            # H1-H11, PC-01..05 (copied to D/pop-census.json)
python3 -I D/exam-scripts/os2.py W/l2-head-j2.partial W/l1-units-head.jsonl W/exam/os2.json   # OS-2, L2 rates (D/os2-sample.json)
grep -c environmentoptim src/agentprov/adapters/agentdojo/artefacts.toml   # PC-05: 0
```

Follow-ups (not run): none heavy for this part. After D-255 / R-10j-1: pre-check of the 6,016 held logs (new prereg part, then `run_batch.py` with a plan entry for it).
