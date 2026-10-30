# Pre-check dossier: `ipi-defenses-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `ipi-defenses-agentdojo` (data and docs CC BY 4.0, code MIT; embedded AgentDojo text MIT) |
| Parts | `ipi-defenses-agentdojo · head` (1 part) |
| Family / profile | `agentdojo` / `ipi-defenses-agentdojo@1` (dialect `agentdojo.tracelogger` v1.k14, semantics `agentdojo.suites@2`, identity table `ipi_defenses_run_dirs.toml`, 19 rows) |
| Pin | Zenodo 22011266 (v4.0.0), `AgentSecurity-IPIDefenses-v4.0.zip`, sha256 `c2370724…`, verified; 3 nested `tar.gz` (D-57, D-382) |
| Code commit | `d97d3a57` (L1 and L2, batch `wave7`, all steps rc 0; tracked changes true) |
| Kind | wave 7, first examination (not in FA or E2); no stored corpus |
| Date | 2026-10-14/15 (prereg, research), 2026-10-16 (batch), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), batch runner, examiner (this dossier); adversarial verifier 2026-10-21 (verdicts in `findings.json`; recount in `verify-recount.json`, scripts `exam-scripts/verify_*.py`) |
| Data | [`data/ipi-defenses-agentdojo/`](data/ipi-defenses-agentdojo/): `research.json`, `l1-head.json`, `l1-09-head.json`, `l1-10-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `findings.json`, `os1-population.json`, `os2-sample.json`, `rawpass.json`, `dup-groups.json`, `manifest-check.json`, `ctx-hit.json`, `ctx-hit2.json`, `exam-scripts/` |

- Code identity, part `head` ([`code-head.json`](data/ipi-defenses-agentdojo/code-head.json)): commit `d97d3a57` (tracked_changes true); engine code expand `3b1d412bb770`, aer `856b7a09e0cf`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `agentdojo.tracelogger@0.1.0` `03d8bc6d30df`; profile sha256 `904eb7c38357`, rules agentdojo 2 / aer 1; lockfile `b0455f1058c8`, limits `5d6dbb210259`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Paper | Khan, AlKhanbashi, Mohamed, *Computers* 2026, 15(9), 570, https://doi.org/10.3390/computers15090570 | Tables 9-12 = outcome reference |
| Data record | https://doi.org/10.5281/zenodo.22011266 (concept 20731176, 4 versions; v3 superseded for a GPT-5.4-mini trace-logging defect) | the pin |
| Harness | `agentdojo==0.1.35` (tag `a75aba76`), runner `code/agentdojo_banking.py` in the deposit (not verified, D-24) | producer |
| Upstream issues | ethz-spylab/agentdojo #181, #161 (CC-07), #209, #133, #192, #212 | checker and harness |

Data-versus-paper notes (from `research.json`, checked against the data):

- Every Table 10 per-cell ASR and BU count, the mini pooled UUA of Table 9, the Table 11 discordant pairs (on `mini_rerun`) and every Table 12 row reproduce exactly from the raw fields.
- The frontier run-1 traces are absent (D-251). The two run-1 RUP frontier cells that the paper calls trace-backed are not in the deposit either (PC-07).
- The Zenodo v4 description and the profile's `[source].paper` are stale (PC-08). The deposit's `docs/MANIFEST.sha256` matches all 25 listed files.

## 3. Expectations

Pre-registration: [`prereg/ipi-defenses-agentdojo.md`](prereg/ipi-defenses-agentdojo.md), committed in `eb7151ee`, before any check of this corpus ran. Amendments 2 and 5 (README section 8) apply. Amendment 5 sets the stratum key `container × model_dir × attack_dir` (38 strata). Classes follow R1-R6 and CC-01..CC-11.

| H | Result | Note |
|---|---|---|
| H1 | supported | 3,211 logs in 19 cells × 169 (144/16/9) |
| H2 | supported | strict parse ok 3,211; 0 incomplete, empty or error-only (the 143 null_final are PC-05) |
| H3 | supported | 19/19 cells reproduce Table 10 ASR k/144 and BU k/16 exactly |
| H4 | supported | mini UUA pooled 168/168/88/91/170; 9/9 frontier cells within bounds; frontier run-2 UUA 697 ∈ [586, 757] (697 + 60 pre-pass utility = 757) |
| H5 | supported | `verify_2026-07` is run 2 (all discriminators match); no run-1 frontier cell (PC-07) |
| H6 | supported | `mini_rerun` Table 11 fixed/caused 4/1, 6/1, 6/0, 4/2 exactly; `pdef` gives 4/5, 5/1, 5/0, 5/1 |
| H7 | supported | attacked security true 27 (13 + 14 + 0); 475/475 attack-none security true |
| H8 | supported | Table 12 exact on all 14 rows (zero-tool counts, median calls, median duration at 2 dp); both counting rules agree |
| H9 | supported (verifier) | logs: 0/0. Context: 0 account paths; the 1 secret-shaped match in `CHANGES.md` is a documented benchmark canary (PC-01 refuted, PC-10) |
| H10 | supported | `pdef` 845 in 2026-06 (last 06-17); rerun and frontier in 2026-07 (last 07-14 and 07-16) |
| H11 | supported | MANIFEST.sha256: 25/25 match, including the 3 tars |
| H12 | refuted | 77 groups / 349 units vs 37 / 77; 2 cross-model groups. Explained by the fingerprint (CC-01) and injection-independent tool_filter trajectories; 0 byte copies (PC-06) |
| H13 | supported | sentinel in 1,169 tool messages of 608 logs, all pi_detector; spotlighting prompt 676/676 |
| H14 | supported, partly not tested | L2 all ok (§5); the 2 trailing-call logs were not sampled |
| H15 | partly refuted | pre-pass utility goals: mini run 1 7 ✓, mini run 2 **6** (expected 7), GPT-5.4 {4,5,7} ✓, Claude {7} ✓ (exploratory) |
| H16 | supported | 42 sample rows, 0 references outside the Wilson 95% interval |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: the staged zip (archive mode, pin verified, nested tars read in memory). Tool `l1_scan` at `d97d3a57`, 1.5 s.

| Check | Denominator | Result |
|---|---|---|
| L1-01 | 3,237 walked (26 level-1 + 3,211 tar members) | selected 3,211 = registry 3,211; context 5, nested 3, not selected 18 |
| L1-02 | 3,211 | ok 3,211 |
| L1-03 | 3,211 | variation selectors: 252 strings in 217 logs at `/messages/*/content/*/content` (benchmark text). No other class |
| L1-04 | 3,211 | byte groups 0. Trajectory groups 77 / 349 units (tool_filter 53, pi_detector 18). 1 cross-corpus group with authority-caps (one IT7 pre-pass). PC-06 |
| L1-05 | 3,211 | 19 cells × 169; mini 1,690, GPT-5.4 845, Claude 676; attacked 2,736, none 475 (pre-pass 171) |
| L1-06 | 3,211 | 0 secret-like strings, 0 account paths |
| L1-07 | 3,211 | `/evaluation_timestamp` naive 3,211, 0 parse failures, 0 non-monotone, 2026-06-17..2026-07-16 |
| L1-08 | 3,211 | null_final 143 (all mini tool_filter; PC-05), trailing_calls 2 (Claude RUP). 0 empty, zero-message, error-only or incomplete |
| L1-09 | 3,237 | 0 metadata members |
| L1-10 | 5 context files | 1 file with `secret:generic-credential-assignment` (1 match: a documented benchmark canary, PC-10; PC-01 refuted), 0 account paths, 0 operator |

## 5. Level 2

- Sample: [`l2-sample-head.json`](data/ipi-defenses-agentdojo/l2-sample-head.json), 190 units in 38 strata (5 each), sha256 `4cf2722c…`.
- Import: j2 and j1 scratch corpora; 190/190 stages ok at raw, aer, sem, prov and validation.
- Validate (aer, sem, prov, linkage): 190 passed, 0 failed, linkage 100%. SHACL is not implemented. Regression does not apply.
- `recompute --dry-run`: 190 identical, 0 unexplained.
- Determinism: j2 against j1 gives 3,797 files, 0 differ, index identical.
- `verify --level chain`: ok. The only finding is `checksums.absent`, which is expected on a working tree.
- A2 classes: none. A3 classes: none (65,087 statements checked).
- Degenerate 0, `adapter_defect` 0.
- Register codes: `map.accounting_unverifiable` 190 and `map.earlier_attempts_unobservable` 190. No `retry_passes_inferred`, including on the 11 sampled empty-text finals.
- Evidence classes: core D 855, O 3,924; inference I 17,981; assessment I 3,642, O 380.
- `_unverified` split: twin assessment:I 2,282, inference:I 14,409 and inference:none 1,675; native 0; mixed inference:I 2,180. Code identity is `unpinned`, so the D rules appear as twins (D-24).
- Identity: model, defence, attack and suite resolve for 190/190, with 0 mismatches and 0 unresolved.
- Mapping check: in all 28 arms the mapped outcomes equal the raw L1 values.
- Redaction: 578 files, 0 hits. Withholding: inert (no `[withhold]`, D-257).

## 6. Outcome comparison

**Population (L1, every log; paper Table 10)**

ASR is k/144 attacked logs and BU is k/16 benign user tasks. The Wilson 95% interval is in brackets. Gap is 0 in every cell, so the gap rule does not fire.

| Cell (run set / defence / model) | n | ASR k (% [Wilson]) | paper | gap pp | n | BU k (Wilson %) | paper | UUA k/144 | verdict |
|---|---:|---|---:|---:|---:|---|---:|---:|---|
| pdef / none / mini | 144 | 5 (3.47 [1.49, 7.87]) | 5 | 0.00 | 16 | 12 (50.5, 89.8) | 12 | 85 | match |
| pdef / rup / mini | 144 | 1 (0.69 [0.12, 3.83]) | 1 | 0.00 | 16 | 13 (57.0, 93.4) | 13 | 89 | match |
| pdef / spot / mini | 144 | 6 (4.17 [1.92, 8.79]) | 6 | 0.00 | 16 | 10 (38.6, 81.5) | 10 | 85 | match |
| pdef / tool_filter / mini | 144 | 0 (0.00 [0.00, 2.60]) | 0 | 0.00 | 16 | 4 (10.2, 49.5) | 4 | 48 | match |
| pdef / pi_det / mini | 144 | 1 (0.69 [0.12, 3.83]) | 1 | 0.00 | 16 | 6 (18.5, 61.4) | 6 | 42 | match |
| rerun / none / mini | 144 | 6 (4.17 [1.92, 8.79]) | 6 | 0.00 | 16 | 12 (50.5, 89.8) | 12 | 83 | match |
| rerun / rup / mini | 144 | 4 (2.78 [1.09, 6.92]) | 4 | 0.00 | 16 | 13 (57.0, 93.4) | 13 | 81 | match |
| rerun / spot / mini | 144 | 3 (2.08 [0.71, 5.95]) | 3 | 0.00 | 16 | 9 (33.2, 76.9) | 9 | 83 | match |
| rerun / tool_filter / mini | 144 | 0 (0.00 [0.00, 2.60]) | 0 | 0.00 | 16 | 4 (10.2, 49.5) | 4 | 43 | match |
| rerun / pi_det / mini | 144 | 1 (0.69 [0.12, 3.83]) | 1 | 0.00 | 16 | 6 (18.5, 61.4) | 6 | 46 | match |
| verify / none / claude | 144 | 0 (0.00 [0.00, 2.60]) | 0 | 0.00 | 16 | 13 (57.0, 93.4) | 13 | 100 | match |
| verify / none / gpt-5.4 | 144 | 0 (0.00 [0.00, 2.60]) | 0 | 0.00 | 16 | 9 (33.2, 76.9) | 9 | 80 | match |
| verify / rup / claude | 144 | 0 (0.00 [0.00, 2.60]) | 0 | 0.00 | 16 | 14 (64.0, 96.5) | 14 | 100 | match |
| verify / rup / gpt-5.4 | 144 | 0 (0.00 [0.00, 2.60]) | 0 | 0.00 | 16 | 8 (28.0, 72.0) | 8 | 75 | match |
| verify / spot / claude | 144 | 0 (0.00 [0.00, 2.60]) | 0 | 0.00 | 16 | 12 (50.5, 89.8) | 12 | 113 | match |
| verify / spot / gpt-5.4 | 144 | 0 (0.00 [0.00, 2.60]) | 0 | 0.00 | 16 | 8 (28.0, 72.0) | 8 | 83 | match |
| verify / tool_filter / gpt-5.4 | 144 | 0 (0.00 [0.00, 2.60]) | 0 | 0.00 | 16 | 10 (38.6, 81.5) | 10 | 59 | match |
| verify / pi_det / claude | 144 | 0 (0.00 [0.00, 2.60]) | 0 | 0.00 | 16 | 6 (18.5, 61.4) | 6 | 43 | match |
| verify / pi_det / gpt-5.4 | 144 | 0 (0.00 [0.00, 2.60]) | 0 | 0.00 | 16 | 5 (14.2, 55.6) | 5 | 44 | match |

- Frontier UUA bounds hold for every cell (H4). Every zero-success cell is kept; no data is excluded for having no successful attack.
- **CC-07 on this data.**
  - #181 (PC-02): 4 of the 11 IT0/1/3 successes lack the GOAL datum, so ASR goes from 27 to 23 of 2,736. Mini pooled ASR falls from 1.88% to 1.60%. Both pi_detector mini successes (1/144 per run) are affected; re-scored, those cells are 0/144.
  - #161 (PC-03): 106 of 190 UT5 utility passes are vacuous (attacked 95/171, benign 11/19). In 11 of the 19 cells, BU contains one vacuous pass (6.25 pp).
  - Zero-tool vacuous utility (PC-04): 127 logs, 102 of them under tool_filter.
- **Sample (L2, mapped)** ([`os2-sample.json`](data/ipi-defenses-agentdojo/os2-sample.json)): 42 rows (ASR, UUA and BU per model × defence). Each arm has n = 5-10, so the rates are reported with Wilson intervals only, never as a verdict (R6). In 0 rows does the paper or population reference fall outside the interval. The sample contains 1 attacked success in 95 attacked units (mini none).

## 7. Findings

| Id | Finding | Class | Sev | Security | Verdict |
|---|---|---|---|---|---|
| PC-ipi-defenses-agentdojo-02 | [CC-07, #181] 4 of 11 IT0/1/3 successes have no GOAL datum (3 with the precedence fix only); ASR 27 → 23 | expected-known (R2; scope gap CC-09) | S3 | no | confirmed |
| PC-ipi-defenses-agentdojo-03 | [CC-07, #161] UT5 utility is true in 190/190 logs; 106 of these have no executed payment to the Spotify IBAN | expected-known (R2; CC-09) | S3 | no | confirmed |
| PC-ipi-defenses-agentdojo-04 | [CC-07, vacuous utility] 127 non-pre-pass logs score utility true with zero tool executions (tool_filter 102; UT10 44, UT9 38, UT5 26, UT8 19) | expected-known (R2; CC-09) | S3 | no | confirmed |
| PC-ipi-defenses-agentdojo-05 | 143 mini tool_filter logs end with an empty-text final answer (54 of them utility true). The content is not None, so silent_rerun correctly does not apply. The profile records only `null_final_logs = 0` and has no note for this shape; the prereg does not record it | documentation-mismatch (R4) | S3 | no | confirmed |
| PC-ipi-defenses-agentdojo-06 | L1-04: 77 groups / 349 units vs the census's 37 / 77; 2 cross-model tool_filter groups; 0 byte copies | analysis-artefact (R5, CC-01) | S3 | no | confirmed |
| PC-ipi-defenses-agentdojo-07 | No frontier run-1 cell is present, including the 2 RUP cells the paper calls trace-backed | documentation-mismatch (R3; absence itself D-251) | S3 | no | confirmed |
| PC-ipi-defenses-agentdojo-08 | Stale metadata: the profile `[source].paper` and the Zenodo v4 description | documentation-mismatch (R4/R3) | S3 | no | confirmed |
| PC-ipi-defenses-agentdojo-09 | Known artefacts as expected: benign constant 475, pre-pass 171, naive timestamps 3,211, trailing calls 2, `benchmark_version` null, detector sentinel 1,169/608, spotlighting prompt 676. No catalogue entry is scoped to this profile | expected-known (CC-09) | S3 | no | confirmed |
| PC-ipi-defenses-agentdojo-10 | [verifier] `CHANGES.md` line 267 is a documented benchmark canary (a reproducibility-checklist item "Secret asset", beside a reserved `.test` attacker address). `release_scan` will flag it at seal, so it needs a digest allowlist entry | source-defect (CC-13 fixture, uncatalogued: R1, `agentdojo.art.fixture_secret_shapes` proposed; reaches no statement; reclassified 2026-10-21 from expected-known) | S3 | no | confirmed |

Refuted:

| Id | Finding | Original class / sev | Why refuted |
|---|---|---|---|
| PC-ipi-defenses-agentdojo-01 | `CHANGES.md` secret-shaped match, status undetermined, security | source-defect S2, security | The masked line is a reproducibility-checklist item naming a "Secret asset" next to `attacker@evil.test`. The token is `Secret=` followed by a 16-char lowercase string made of a short token and two dictionary words. It occurs in 0 of 3,211 logs, and no log contains `evil.test` or "Secret asset". It is a benchmark canary, not a credential. The examiner's "mixed-case, length withheld, 4.18 bit/char" came from `ctxhit.py` counting the key word as part of the value (analysis-artefact). Residual: PC-10 |

CC items not applicable: CC-02 (no AgentDyn suite), CC-03 (0 account paths anywhere), CC-04 (the prereg does not cite U6-c), CC-05 (no stored corpus), CC-10 (banking only, no slack).

Proposed `artefacts.toml` rows (text only; to the AgentDojo family owner):

```toml
# agentdojo.art.validity_defects expected +=
{ snapshot = "ipi-defenses-agentdojo:head", count = 4,   unit = "executions", basis = "pre-check PC-ipi-defenses-agentdojo-02: banking IT0/1/3 successes without the GOAL datum (#181); precedence-only 3", status = "proposed" },
{ snapshot = "ipi-defenses-agentdojo:head", count = 106, unit = "executions", basis = "pre-check PC-ipi-defenses-agentdojo-03: UT5 utility true without an executed Spotify payment (#161): attacked 95, benign 11", status = "proposed" },
{ snapshot = "ipi-defenses-agentdojo:head", count = 127, unit = "executions", basis = "pre-check PC-ipi-defenses-agentdojo-04: vacuous utility, zero tool executions, pre-passes excluded", status = "proposed" },
```

Proposed AGENTS.md §12 item: none. The examiner's PC-01 item was withdrawn after verification: the match is a benchmark canary, D-257 stands.

## 8. Recommendations and readiness

1. **PC-10 (release owner):** add a `release_scan` allowlist entry, by digest, for the benchmark canary in `docs/CHANGES.md` line 267. No withhold. D-257 stands. No execution is affected. (The verifier refuted PC-01.)
2. Disclose PC-02..04 next to Tables 9-10. pi_detector mini ASR is 0/144 per run under the GOAL-datum re-score, and tool_filter and pi_detector utility include vacuous passes. Keep the logged booleans. Route the scope rows to the family owner (CC-07, CC-09).
3. Profile owner, at the next bump: add an `observed` note for the tool_filter empty-text finals (PC-05) and the paper DOI (PC-08).
4. Datasheet: state that the frontier run-1 values and the 2 "recovered" RUP cells are not trace-backed in the deposit (PC-07, D-251).

**Readiness: `ready-with-caveats`.**

- The data are internally consistent and reproduce every published per-cell count exactly.
- L2 is clean, deterministic and identity-complete.
- Caveats, all S3: the CC-07 disclosures (PC-02..04) and the `release_scan` allowlist entry for the canary (PC-10) before seal. No S0-S2 finding remains after verification.

## 9. Reproduction

```bash
# L1, sample, imports, check (already run; batch wave7, status.jsonl rc 0)
uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave7.toml   # through tools/suite_queue.py --class import --cpu 2
# examination (repo root; W = ~/.agentprov/migration-work/precheck/ipi-defenses-agentdojo)
python3 -I docs/reports/precheck/data/ipi-defenses-agentdojo/exam-scripts/os1_population.py $W/l1-units-head.jsonl > docs/reports/precheck/data/ipi-defenses-agentdojo/os1-population.json
uv run python -I docs/reports/precheck/data/ipi-defenses-agentdojo/exam-scripts/rawpass.py $W/exam/rawpass.json
python3 -I docs/reports/precheck/data/ipi-defenses-agentdojo/exam-scripts/dups.py docs/reports/precheck/data/ipi-defenses-agentdojo/dup-groups.json
python3 -I docs/reports/precheck/data/ipi-defenses-agentdojo/exam-scripts/os2.py docs/reports/precheck/data/ipi-defenses-agentdojo/os2-sample.json
uv run python -I docs/reports/precheck/data/ipi-defenses-agentdojo/exam-scripts/manifest.py
uv run python -I docs/reports/precheck/data/ipi-defenses-agentdojo/exam-scripts/ctxhit.py
uv run python -I docs/reports/precheck/data/ipi-defenses-agentdojo/exam-scripts/ctxhit2.py
```

Follow-up (not run): L2 coverage of the 2 trailing-call logs through `tools/suite_queue.py --class import --cpu 2 --label precheck-ipi-defenses-agentdojo`, using `l2_import.py` with those 2 labels, into a new scratch corpus.
