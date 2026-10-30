# Pre-check dossier: `credleak-p15b`

## 1. Header

| | |
|---|---|
| Corpus | `credleak-p15b` (CC-BY-4.0 by the record's metadata; no licence file in the deposit) |
| Parts | `credleak-p15b · head` (1 part): Zenodo 22737462 v3, `p15b-run-data-v3-2026-09-13.zip`, sha256 `7e5f7e40…` (pin verified) |
| Family / profile | `credleak` / `credleak-p15b@1` (dialect and mapper `credleak.cell`, semantics `credleak.tools@1`, `[withhold]` D-265); registry status `planned` |
| Code commit | `d97d3a57` (L1 and L2, batch `wave6`, steps l1, l1_10, sample, import_j2, import_j1, check all rc 0; l1_09 skipped, no metadata members) |
| Kind | wave 6, first examination (not in FA or E2); no stored corpus |
| Date | 2026-10-14 (prereg, research), 2026-10-16 (batch), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), examiner (this file); adversarial verifier 2026-10-21 (all 8 findings confirmed, verdicts in `findings.json`) |
| Data | [`data/credleak-p15b/`](data/credleak-p15b/): `research.json`, `l1-head.json`, `l1-09-head.json`, `l1-10-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `findings.json`, `raw-census.json`, `os-sample.json`, `coverage-rates.json`, `accounts.json`, `duplicates.json`, `extcanary-overlap.json`, `exam-scripts/` |

- Code identity, part `head` ([`code-head.json`](data/credleak-p15b/code-head.json)): commit `d97d3a57` (tracked_changes false); engine code expand `3b1d412bb77a`, aer `856b7a09e0cf`, sem `e2c07f9a74f4`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `credleak.cell@0.1.0` `75805eeca07b`; profile sha256 `1dce158a57ad`, rules aer 1 / credleak 1, semantics `credleak.tools@1` `721620e801f2`; lockfile `b0455f1058c8`, limits `5d6dbb210259`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Data record | https://zenodo.org/records/22737462 (concept 21860162; v1 21860163, v2 22729871, v3 22737462 = latest) | the data; README, CHANGES and the per-cell csv files are the only outcome references |
| Paper | not public (record: under review, Springer Cybersecurity); no arXiv or ORCID entry | no paper tables |
| Harness | in-house, unnamed; CHANGES names builds v0.1.790/793 for the 2026-09-13 waves only | producer |
| External use | `cisco-ai-defense/defenseclaw` `benchmarks/datasets.lock.json` pins v1 | lineage (v1 holds the AWS account identifier v2 redacted) |

Data-versus-documentation notes (checked against the data):

- The deposit's `per-cell-counts.csv` (v1) and `-v2.csv` reproduce the logged `exfiltrationDetected` count exactly in all 494 keys whose run count matches, but do not cover the v3 additions (addendum waves, two Gemini T-SLOP cells) and differ for Fable T1 (PC-04).
- Census and record say the extcanary cells' in-harness counts read 0. In the data, 71 of the 640 TEGRESS extcanary runs have `exfiltrationDetected` true (PC-03).
- The record says identifiers were redacted (v2: one AWS account id, a SARIF working-directory path). One named home-directory account remains in environment tool output of 313 runs (PC-01, undetermined whether a person's).
- `intentVerdicts` is empty in all 19,636 runs although `config.judgeModel` is set in all 643 cells: no judge ran.

## 3. Expectations

Pre-registration: [`prereg/credleak-p15b.md`](prereg/credleak-p15b.md), committed in `fd75f8a3` (2026-10-14), before any check of this corpus. Amendments 2 and 4 (README section 8) apply; amendment 1 does not (no stored corpus). The sample is the pre-registered file-level (cell) sample; no D-529 supplementary sample was run.

| H | Result | Note |
|---|---|---|
| H1 | supported | 682 / 643 / 39; 19,636 runs; the 8 layout classes' cells and runs exact; 20,176 turns; 83,619 calls |
| H2 | supported | 643/643 parse ok; run model, scenario and `repetition == index + 1`: 0 exceptions |
| H3 | refuted as worded | 21 strings as expected, but field ≠ directory in 195 cells: 147 roster Claude cells by the `claude-` prefix only, 44 excluded Fable, 4 underscore dirs; the 3 addendum cells (in `claude-*` dirs) are equal. Mapping uses the field verbatim (0 mismatches) (PC-06) |
| H4 | supported | roster coverage exactly as section 3; the only 16-model gaps are Gemini × TMCPDESC and × TDELAY; `C4-baseline` 643/643 |
| H5 | supported | every tally exact (hijack 5,421; exfil 3,936; detected 5,479; displayed 1,260; 572/3,202; 124/1,815; 2,840/3,566; errors 59) |
| H6 | refuted | v2 has no row for roster sonnet-4-6 TSTAGE.2; v2's `maliciousArtifactEmitted` column equals the logged pre-fix flag in every T-EMIT key; exfil 0 differences on N-matched keys (PC-04) |
| H7 | refuted | 71 of 800 extcanary runs (all TEGRESS: 71/640) have in-harness `exfiltrationDetected` true (PC-03) |
| H8 | supported | 0 non-null `intentVerdicts` |
| H9 | refuted (account clause) | tag fields 50,094 / 21,767 / 17,964 / 5,505, AWS 1,273, other `sk-` 15,927, untagged 78 in 27 runs, 5,422 value-bearing runs in 325 cells: exact; Anthropic 1,271 / 1,273 by pattern vs 1,272. One named non-generic home path in 313 runs (PC-01), 5 model-authored one-cell paths (PC-02) |
| H10 | supported except the overlap count | shapes, 0 missing, 0 decreases (540 pairs), range 2026-06-10..2026-09-13; overlap 9,545 / 18,993 under the exam's reading vs 9,505 (PC-06) |
| H11 | refuted | 308 identical-trajectory groups hold tool-call runs (1,614 runs); none share timestamps across cells (PC-05) |
| H12 | supported (counts) | 1,495 / 59 / 100 / 0; the 100 empty responses are 98 Fable + 1 devstral + 1 mistral (PC-06) |
| H13 | supported | 0 failures, 0 degenerate, 0 `adapter_defect`; codes only `missing_generated_by`, `accounting_unverifiable`, `credleak.invocation_error`; recompute 9,058 identical; validate 9,058 passed; jobs 2 vs 1 byte-identical |
| H14 | supported (count level) | 2,391 raw value-bearing sampled runs = 2,391 derived-file hits = 2,391 withheld; 0 released executions with a secret pattern (PC-07) |
| H15 | refuted (count) | 282 calls (not 290), 41 names; the one empty-name call's cell is not sampled, so the typed-slot clause is not tested at L2 |
| H16 | supported | 289 arms × 4 metrics: 1,156/1,156 AER = raw |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: the staged zip (archive mode, pin verified), `l1_scan` at `d97d3a57`, 8.9 s. Exam scripts read the same zip through `agentprov.ingest` (`exam-scripts/rawlib.py`).

| Check | Denominator | Result |
|---|---|---|
| L1-01 | 682 members | 643 selected cells; 38 not selected + 1 excluded (collector log), all `select.not_execution_artefact`; 19,636 runs = registry figure |
| L1-02 | 643 | 643 ok |
| L1-03 | 643 | JSON-in-string 344, escaped newline 278, variation selector 206, CR 127, U+FFFD 18, C0 3, zero-width 3, NEL 2, PUA 2, C1 1: model and tool text; no lone surrogate, bidi or tag character |
| L1-04 | 643 cells / 19,636 runs | 0 byte-identical; 362 trajectory groups, 2,560 runs (PC-05); cross-part 0, cross-corpus 0 (`_cross/l1-xdup.json`) |
| L1-05 | 643 | 250 strata (prereg 249-252); defence `C4-baseline` only; coverage as H4 |
| L1-06 | 643 | withhold rules in 325 cells; secret-like 326 cells; named account paths 72 cells (6 distinct names by digest, 0 operator) (PC-01, PC-02); not-selected members: 0 account paths |
| L1-07 | 20,176 turn stamps | one `Z` shape; 0 missing, 0 decreases; 75 naive dates inside tool output (text, not run time) |
| L1-08 | 19,636 | zero-call 1,495; `invocationError` 59; empty response 100; zero-turn 0 |
| L1-09 | 682 | not applicable (0 metadata members) |
| L1-10 | 0 files | archive mode has no context tree; exam `ctx.py` screened the 39 not-selected members: 0 hits (PC-08) |

## 5. Level 2

- Sample: [`l2-sample-head.json`](data/credleak-p15b/l2-sample-head.json): 300 cells over 250 strata (cap applied, not over maximum), 9,058 executions, 0 labels without an execution.
- Import (`l2_import.py`, jobs 2 and 1): 9,058 executions, all stages ok; 0 degenerate, 0 `adapter_defect`.
- Validation (tiers aer, sem, prov, linkage; shacl not implemented, regression not applicable): 9,058 passed, linkage 100%. `recompute --dry-run`: 9,058 identical. Determinism: 27,826 files, 0 differ, index identical. `verify --level chain` on the working tree: ok, only `checksums.absent` (not sealed).
- A2/A3: no failure class; A3 `{}` (0 PI-nn).
- Issue codes: index `map.accounting_unverifiable` 9,058, `map.missing_generated_by` 9,058, `map.credleak.invocation_error` 3 (= 3 raw errors in the sample); seal `accounting_unverifiable` 16,892, `missing_generated_by` 9,058, `credleak.invocation_error` 3. All expected-known.
- Evidence classes: core D 247,424 / O 361,846; inference I 890,312 (890,309 by a native `_unverified` rule); assessment I 194,537 / O 18,116 (native `_unverified` 84,770). Twin 0, mixed 0.
- Identity: `model.requested` = run model verbatim (21 strings); `C4-baseline` 9,058; 0 direct mismatches; Fable directory maps to 2 strings and underscore dirs to 3, as expected.
- Redaction: 2,378 executions hold a secret pattern, 0 of them released (all withheld). 168 hold a named non-generic account path in AER/SEM/PROV (164 the PC-01 digest; AER message text 214, message args 26, tool_execution args 26 pointers; PROV `apv:args` 26), 72 of the 168 not withheld (70-72 of them PC-01; the script does not split released by digest). 0 operator hits.
- Withholding (`plan_withholding`): 2,391 executions; 327 objects = 325 value-bearing cells + the stored collector-log member (D-450) by profile rule + the zip (container). A sealed chain check needs a full import (follow-up).
- CC-07 (#181/#161): not applicable. This is the credleak format, not AgentDojo (0 AgentDojo suites).

## 6. Outcome comparison

No paper is public, so the targets are the census (population) and the deposit's per-cell csv. Gap rule as in README section 4 and amendment 2.

| Arm | n | Rate (Wilson 95%) | Target | Gap | Verdict |
|---|---:|---|---|---|---|
| all runs, population, 7 detector tallies | 19,636 | e.g. exfil 20.04%, hijack 27.61% | census section 6 | 0 | reproduced exactly |
| per-cell csv v1, exfil (errored excluded) | 494 keys | — | csv | 0 differences | reproduced; 5 keys differ in N (PC-04) |
| sample vs raw of the same cells (mapping) | 9,058 | 1,156 arm-metrics | raw | 0 | identity holds |
| sample arms ≥ 20 runs vs population | 220 arms | — | L1 population | 3 flagged | explained (R6), below |
| gemini TSLOP.1 exfil | 80 | 100% (95.4-100) | pop 50% (n 160) | +50 pp | R6: sampled cell is the v3 wave (80/80); the 2 other cells 0/80 |
| nova-pro TSLOP.1 exfil | 80 | 85% (75.6-91.2) | pop 60% (n 130) | +25 pp | R6: unsampled extcanary cell (0/40 in-harness) |
| deepseek TMCP.1 displayed | 20 | 5% (0.9-23.6) | pop 22% (n 100) | −17 pp | R6: 20-run cell vs the 80-run cell |
| per technique, hijack / exfil | 200-1,340 | [`coverage-rates.json`](data/credleak-p15b/coverage-rates.json) | pop | up to 13 pp (TSTAGE exfil 51.7 vs 38.9) | R6: whole-cell draw, unequal cell sizes; not a finding |
| extcanary TEGRESS in-harness exfil | 640 | 11.1% | 0 by design | +11.1 pp | PC-03 |

## 7. Findings

| Id | Title | Class | Sev | Sec | CC | Verdict |
|---|---|---|---|---|---|---|
| PC-01 | Named home-dir account in environment output of 313 runs / 67 cells, in AER and PROV; 137 runs and 18 raw cells released at seal | source-defect (S0 if a person's account; else expected-known S3) | S0 | yes | CC-12a (provisional), CC-03, CC-11 | confirmed (classification pending a person) |
| PC-02 | 5 one-cell model-authored account paths | expected-known | S3 | no | CC-03 | confirmed |
| PC-03 | extcanary in-harness exfil 71/640, not 0 | documentation-mismatch | S2 | no | R3/R4 | confirmed |
| PC-04 | per-cell csv omits v3 additions; Fable T1 N 23 vs 20; v2 missing a roster row; `errored` definition not reproduced | documentation-mismatch | S3 | no | R3 | confirmed |
| PC-05 | identical trajectories with calls, 1,614 runs (re-runs, not double deposits) | documentation-mismatch | S3 | no | R4 | confirmed |
| PC-06 | our docs: malformed 282 not 290; dir/field prefix; empty responses; overlap; 654 cells | documentation-mismatch | S3 | no | R4 | confirmed |
| PC-07 | planted credentials and `[withhold]` as designed | expected-known | S2 | yes | R2 (`credleak.art.planted_credentials`), CC-13 fixture: provider-prefixed shapes reach PROV `apv:args` (reclassified 2026-10-21 from S3, no) | confirmed |
| PC-08 | L1-10 screens 0 files in archive mode; `executions_hit` mixes rules | analysis-artefact | S3 | no | R5 | confirmed |

Verifier notes (2026-10-21; reproductions re-run: `accpop.py`, `pop.py` (output identical to `raw-census.json`), `aerscan.py`, plus two count-only verifier scripts under `~/.agentprov/migration-work/precheck/credleak-p15b/exam/verify/`):

- PC-01: 421 strings / 67 cells, all `/home/`, all inside `runs[].turns[]` (tool output 395, tool-input command 24, file_path 1, assistant text 1), 0 in cell config or prompts, so it is not a planted scenario value. 18 of the 67 cells hold no `[withhold]` hit, so those raw cell objects are released too. A container or sandbox login user is consistent with the data and cannot be ruled out name-blind. The verifier did not compare the name with the record's creator, because that is the authorised person's step. S0 stays until that person classifies the name.
- PC-03: the gap is wider. `rates.toml` holds only `credleak.rate.invocation_error`, so all four D-260 rate exclusions are missing (excluded models, probe, replication wave, extcanary).
- PC-04: `errored` equals `invocationError` on 450 of the 494 matched v1 keys (449 of 493 in v2), not 450 of 498.
- PC-06: AGENTS.md line 357 says 654 cell files. The `artefacts.toml` 290 is marked `unverified`, and the census says "about 290".
- PC-07: the 326 rule objects cover all 325 value-bearing cells, but only 300 cells were imported, so `plan_withholding` scans every staged member.

Proposed `artefacts.toml` entries (text only; route to the credleak family owner):

```toml
# PC-01 (pending the person/sandbox decision)
# [[artefact]] id = "credleak.art.harness_home_path"; expected count 313 executions (snapshot credleak-p15b:head), status "proposed"
# PC-03
# [[artefact]] id = "credleak.art.extcanary_inharness_flags"; 71 of 640 TEGRESS extcanary runs exfiltrationDetected true; status "proposed"
# PC-04
# [[artefact]] id = "credleak.art.repeated_waves"; addendum 6 cells / 600 runs, Gemini T-SLOP v3 2 / 120, replication 2 / 160; status "proposed"
# PC-06: credleak.art.malformed_tool_names expected count 290 -> 282 (name not listed exactly in credleak.tools@1), 41 names
```

AGENTS.md section 12 items: PC-01 (account decision before the round); extcanary needs a rates.toml rule (PC-03); repeated-wave rules (PC-04); artefacts.toml count 282 and AGENTS.md 643 cells (PC-06); PC-07 (CC-13: planted provider-prefixed shapes in PROV `apv:args`, S2 security; withheld at seal by the `[withhold]` rules, needs `release_scan` allowlist entries by digest).

## 8. Recommendations and readiness

- **Blocked** for the round until PC-01 is decided (verifier: confirmed; 313 runs, 137 released runs plus 18 released raw cells). A person authorised by the user reads the name in a controlled session (it is not recorded here) and decides whether it is a person's account or a sandbox user. If it is a person's account, add a redaction or `[withhold]` rule (313 runs) before import and re-run the release scan. If it is a sandbox user, document it and close the item as CC-03 S3.
- Before release: add the four D-260 rate exclusions to rates.toml, the extcanary cells (PC-03) among them, plus rules for the repeated waves (PC-04). Correct the artefacts.toml count and our docs (PC-06).
- Everything else is ready. The mapping is exact (H16), the pipeline is deterministic, and withholding matches the value-bearing runs. No data is excluded for its outcomes.

## 9. Reproduction

```bash
# from the worktree root; scripts read the pinned zip via agentprov.ingest (exam-scripts/rawlib.py)
X=docs/reports/precheck/data/credleak-p15b/exam-scripts
.venv/bin/python -I $X/pop.py $X . raw-census.json      # H1-H3, H5-H12, H15, accounts, csv
.venv/bin/python -I $X/extra.py $X . extra.json         # extcanary, overlap, account first-seen, fingerprints
.venv/bin/python -I $X/dup.py $X dup.json ; .venv/bin/python -I $X/dupts.py $X
.venv/bin/python -I $X/accpop.py $X ; .venv/bin/python -I $X/ctx.py $X . ctx.json ; .venv/bin/python -I $X/redmark.py $X
.venv/bin/python -I $X/os.py $X os-sample.json          # mapping identity, gap rule, csv detail
.venv/bin/python -I $X/cov.py coverage-rates.json
.venv/bin/python -I $X/aerscan.py $X aerscan.json       # scratch corpus l2-head-j2.partial
.venv/bin/python -I $X/emptyname.py $X
# batch (already run): tools/precheck/run_batch.py --plan tools/precheck/plans/wave6.toml
```

Follow-ups (not run; heavy, through `tools/suite_queue.py --class import --cpu 2 --label precheck-credleak-p15b`):

1. A full (unfiltered) scratch import, then `agentprov package` and `agentprov verify --level chain` on the sealed copy, to check the expected 5,422 withheld executions and 14,214 released, plus the release scan (PC-01, PC-07): `uv run python tools/precheck/l2_import.py --source credleak-p15b --part head --sample <a sample file in the l2-sample format listing all 643 cell labels> --corpus ~/.agentprov/migration-work/precheck/credleak-p15b/full --until validation` (the CLI refuses `planned`).
2. A supplementary L2 import of the one cell with an empty tool name (H15 typed-slot clause): `l2_import.py --source credleak-p15b --part head --sample <one-label sample file: p15b-run-data/01-injection-map/T1-file-document/mistral-large-3/run__T1__mistral-large-3__T1.4__2026-06-10T15-20-00-406Z.json> --corpus ~/.agentprov/migration-work/precheck/credleak-p15b/l2-emptyname`.
