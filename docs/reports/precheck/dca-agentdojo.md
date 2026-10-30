# Pre-check dossier: `dca-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `dca-agentdojo` (Figshare 32657856 v1, MIT; no separate data licence) |
| Parts | `v1` (13,374 `v1.k14` logs), `drift` (2,847 `drift.k18.conversations` logs); one url pin, parts picked by `variant_labels` |
| Family / profile | `agentdojo` / `dca-agentdojo@1` (sha256 `ef434291…`), dialect `agentdojo.tracelogger`, semantics `agentdojo.suites@2` |
| Pin | url `ndownloader.figshare.com/files/65496114`, `DCA_AgentDojo_artifact_v1_20260612.zip`, 54,196,099 B, sha256 `ed500ca3…` (verified by L1 and by `zipread.py`) |
| Code commit | L1 `d97d3a57` (batch `wave7`; l1, l1_09, l1_10 rc 0 for both parts); examiner scripts run at `34fd4cbc` |
| Kind | wave 7, first examination, **Level 1 only**. The import is held until D-455 (a url pin as an archive input, regen item 101). No stored corpus |
| Date | 2026-10-15 (prereg, L1), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg), examiner (this file); adversarial verifier 2026-10-21 (all 10 confirmed; PC-07 reclassified) |
| Data | [`data/dca-agentdojo/`](data/dca-agentdojo/): `research.json`, `l1-{v1,drift}.json`, `l1-09-*.json`, `l1-10-*.json`, `exam.json`, `findings.json`, `os1-population.json`, `checker.json`, `extra.json`, `toolmsgs.json`, `dup-groups.json`, `h12.json`, `nonlog-scan.json`, `exam-scripts/` |

- Code identity, part `v1`: no `code-v1.json`, because L2 has not run. L1 ran at commit `d97d3a57` with profile `dca-agentdojo@1` `ef434291…`.
- Code identity, part `drift`: no `code-drift.json`, for the same reason. L1 ran at commit `d97d3a57` with the same profile.

## 2. Sources and links

| Item | Value | Note |
|---|---|---|
| Paper | none public (title only, in the record and the deposit) | the targets are the deposit's own tables |
| Data record | [doi:10.6084/m9.figshare.32657856](https://doi.org/10.6084/m9.figshare.32657856), v1 only, 2026-06-12 | size and MD5 equal the pin |
| Deposit tables | `results/paper_tables/main_results_from_results_xlsx.md` (Table 1), the same rows in 3 other files; `docs/TABLE_ROW_TO_LOG_DIR.md` | read through `agentprov.ingest` and `quote_untrusted`; transcribed in `exam-scripts/pop.py` before any rate was computed |
| Harness | AgentDojo 0.1.35, benchmark v1.2.2; CaMeL runner (Apache-2.0), DRIFT compat runner | AD#154, #161, #168, #181 apply (section 7) |

Data versus documentation:
- The deposit's table directory is `results/paper_tables/`, not `README.md` or `docs/*.md` as the prereg's rule assumed (PC-06).
- No file in the pin gives numbers for the clean-utility table or the Qwen2-7B table (PC-05).

## 3. Expectations

[`prereg/dca-agentdojo.md`](prereg/dca-agentdojo.md), committed at `eb7151ee` before any data check. The prereg asked for the deposit table to be added to it as an amendment. Because the examiner does not edit the prereg, the transcription is in `exam.json` (`deposit_table_transcription`) and in `pop.py`. Amendment 5 sets the strata to `model_dir × suite × attack_dir`, which gives v1 128 strata and drift 12. Findings are classed by R1-R6 and CC-01..CC-11.

Per-hypothesis table added by the completeness critic (2026-10-21) from the examiner's record:

| H | Verdict and evidence (from `data/dca-agentdojo/exam.json`) |
|---|---|
| H1 | supported: 16,346 members; 16,221 logs (v1 13,374, drift 2,847); 125 non-log (context 10, not_selected 115); parse ok 16,221; 0 byte-identical |
| H2 | supported: 13 attacked v1 arms 949 + 35; 6 clean arms 97; 3 drift arms 949 |
| H3 | supported: drift security true 0 / 2,847 (never an exclusion reason) |
| H4 | supported: v1 attacked security true 772 / 12,337; benign + pre-pass 1,037 / 1,037 |
| H5 | supported (gap rule), with PC-04: 0 arms flagged; 13/15 Table 1 rows exact; 2 UA cells differ by +2.11 / +1.47 pp; clean and Qwen2-7B: no table (PC-05) |
| H6 | supported: 13,374 naive 'YYYY-MM-DD HH:MM:SS', 2026-05-23 00:33:07 .. 2026-06-12 00:34:11; 0 outside the window (zone unrecorded) |
| H7 | supported (Qwen3.6): final call-like text without tool_calls: Qwen3.6 local direct 225/949, local DCA 244/949 vs Qwen3.6 OpenRouter clean 0/97 and 0/97 (different cond... |
| H8 | supported for the pairs; 'other' not comparable (CC-01): same-cell repeats 765 / 243 exact; other 104 under the L1 fingerprint |
| H9 | refuted (the arm part): proxy security true with trailing unexecuted calls: 6 logs (<= 161), all in direct arms (gpt-4o-mini 1, gpt-oss 4, Qwen2-7B 1); prereg marked t... |
| H10 | not tested (definition): 134 runs / 166 occurrences of '<INFORMATION>' (all fields) vs 123 / 165 visible frames; positional part not computed |
| H11 | refuted literally; benign: 1 secret-like benchmark string (PC-08); 0 account paths in logs and in 111 non-log members |
| H12 | supported at L1 (precursors); sealing not tested: negative duration 2 (CaMeL gpt-oss travel IT3 pre-pass; Qwen3.6 secpol workspace UT11/IT13); tool 'none' 1 (drift gpt... |

## 4. Level 1 (whole population)

| Check | v1 | drift | Expected | Verdict |
|---|---|---|---|---|
| L1-01 counts | 13,374 units. Walk 16,346: selected 16,221, context 10, not selected 115 | 2,847 | 16,346 / 16,221 / 13,374 / 2,847 / 125 | match (H1) |
| L1-01 grid | 13 × (949 + 35) and 6 × 97 | 3 × 949 | as prereg | match (H2) |
| L1-02 strict parse | ok 13,374 | ok 2,847 | 0 failures | match |
| L1-03 encodings | logs with: escaped `\n` 5,338, `\uXXXX` 1,179, `\"` 606, variation selector 15, json-in-string 2, CR 1 | `\n` 1,294, json-in-string 1,994 (`/initial_checklist` 1,993), `\uXXXX` 283, `\"` 198, variation selector 20, zero-width 1 | no prior count | recorded; no defect |
| L1-04 duplicates | 0 byte-identical. 1,016 trajectory groups (4,568 units) | 0 byte. 18 groups (55) | 0 byte; repeats 1,025 | same-cell cross-arm repeats: CaMeL vs secpol **765**, Qwen3.6 direct vs DCA **243** (= prereg); other 104 under the CC-01 fingerprint (PC-10) |
| L1-04 cross | v1 vs drift 0. Across corpora 0 byte-identical; 72 v1 trajectory groups shared with 8 corpora (mohameduk 29, authority-caps 25, melon 17, …) | — | 0 | CC-01 fingerprint (no call ids); not byte copies |
| L1-05 arms | 19 directories / 14 pipelines | 3 | 22 rows of T | match; 0 extra cells |
| L1-06 secrets / accounts | 0 / 0 | 1 secret-like (`/initial_checklist`; benchmark text, PC-08) / 0 | 0 / 0 | H11 refuted literally; benign |
| L1-07 time | `evaluation_timestamp` 13,374, naive, 2026-05-23..2026-06-12 00:34:11; 0 parse failures; tool-argument dates are benchmark content | top-level time field: none; 356 logs have content dates | v1 present; drift none | match (H6) |
| L1-08 degenerate | error string 4; null_final 4,521 (CC-08 rule); trailing calls 161 | null_final 3 | 4 / 4,274 / 161 | match apart from the null_final definition (PC-10) |
| L1-08 shapes | CaMeL: ≥ 2,947 / 5,904 logs have tool results with no proposing call (PC-07). Qwen2-7B 427 / 984 and Qwen3.6 local 157 / 984 logs have no tool call at all | gpt-oss 48, Qwen3.6 121 with none | — | new (PC-07) |
| L1-09 / L1-10 | 0 metadata members; 10 context files, 0 hits; 111 non-log members (`nonlog.py`): 0 account paths, 1 placeholder `api_key` assignment | same | 0 | match |
| H12 precursors | negative duration 2 (the expected cells) | tool `none` 1 (gpt-oss slack UT10 / IT2) | 2 / 1 | match |

## 5. Level 2

**Not run.** The import is held until D-455, and the plan entry is `l2_blocked`. The prereg says the sample list is drawn at P0, but it has not been drawn yet; that is a follow-up (section 9). No validate, recompute, determinism, A2/A3, evidence-class (twin/native/mixed), identity, redaction or withholding result exists. Prior evidence comes only from the phase-10j census mapping: 13,372 / 13,374 and 2,846 / 2,847 logs seal, and every D rule goes through its `_unverified` twin. Withholding does not apply (D-257, no `[withhold]`). The redaction expectation (no account path) is supported at L1.

## 6. Outcome comparison (L1 population vs the deposit's Table 1; n = 949 per attacked arm)

| Arm | UA logged [Wilson 95] | Table | ASR logged [Wilson 95] | Table | Verdict |
|---|---|---|---|---|---|
| gpt-4o-mini direct | 39.83 [36.76, 42.98] | 39.83 | 30.24 [27.40, 33.24] | 30.24 | exact; #181 → 28.77 |
| gpt-4o-mini CaMeL | 20.34 | 20.34 | 0.11 (1) | 0.11 | exact |
| gpt-4o-mini CaMeL+secpol | 15.17 | 15.17 | 0.00 | 0.00 | exact |
| gpt-4o-mini DRIFT | **58.27** [55.11, 61.37] (553) | 56.16 (533) | 0.00 | 0.00 | +2.11 pp, under the gap rule (PC-04) |
| gpt-4o-mini DCA | 66.49 | 66.49 | 0.00 | 0.00 | exact; #161 → 65.54 |
| Qwen3.6 direct (local) | 54.79 | 54.79 | 15.81 | 15.81 | exact; #181 precedence → 15.17 |
| Qwen3.6 DRIFT / CaMeL / secpol / DCA | 59.96 / 28.03 / 26.98 / 49.63 | same | 0 / 0 / 0 / 0 | same | exact |
| gpt-oss direct | 47.10 | 47.10 | 33.83 (321, 1 run error) | 33.83 | exact; #181 → 33.61 / 32.56 |
| gpt-oss DRIFT / CaMeL | 47.00 / 33.83 | same | 0 / 0 | same | exact |
| gpt-oss CaMeL+secpol | **28.45** [25.67, 31.40] (270) | 26.98 (256) | 0.00 | 0.00 | +1.47 pp, under the gap rule; the cell repeats the Qwen3.6 value (PC-04) |
| gpt-oss DCA | 55.43 | 55.43 | 0.32 (3) | 0.32 | exact; **all 3 are run errors (AD#154), 0 by effect** (PC-03) |
| Qwen2-7B direct (local) | 17.81 [15.51, 20.37] | — | 1.05 [0.57, 1.93] | — | no table (PC-05) |
| Clean (n = 97): gpt-4o-mini / DCA; gpt-oss / DCA; Qwen3.6 OR / DCA | 72.16 / 69.07; 62.89 / 55.67; 89.69 / 79.38 | — | (constant true) | — | no table (PC-05) |
| v1 pooled | — | — | 772 / 12,337 = 6.26 | 772 (DEC) | exact (H4) |
| drift pooled | — | — | 0 / 2,847 | 0 | exact (H3); included in full |

Notes on the table:
- Gap rule: 0 arms flagged. 13 of 15 rows match the table exactly, and all 15 ASR cells match.
- CC-07 #181 (banking IT0/1/3): 90 successes, all in the 4 direct arms.
  - 17 lack the GOAL datum; under the precedence-only rule 33 are affected.
  - Pooled v1 ASR re-scores from 772 to 755 (GOAL datum) or 739 (precedence only).
- CC-07 #161 (banking UT5): utility is true in 144 of 144 attacked logs.
  - 42 of the 90 non-CaMeL logs show no executed Spotify payment.
  - The 54 CaMeL logs record no payment, so they cannot be scored (record-limited).
  - Effect: at most 0.95 pp per arm.
- CC-10 (#168, slack IT5): 0 of 49 successes lack an executed membership call.
- Macro (unweighted suite mean) rates are in `os1-population.json`.

## 7. Findings

| Id | Finding | Class (CC) | Sev | Verdict |
|---|---|---|---|---|
| PC-dca-agentdojo-01 | #181: 17 of 90 banking IT0/1/3 successes lack the GOAL datum (33 under the precedence-only rule); all in direct arms | expected-known (R2, CC-07; scope CC-09) | S3 | confirmed |
| PC-dca-agentdojo-02 | #161: UT5 utility is true 144 / 144; no payment in 42 of 90 non-CaMeL logs, 54 CaMeL logs record-limited (verifier: the 18 gpt-4o-mini CaMeL logs are probably real vacuous passes, upper bound 51), 2 of 6 clean | expected-known (R2, CC-07) | S3 | confirmed |
| PC-dca-agentdojo-03 | The deposit's only non-zero DCA ASR (gpt-oss 3/949) is 3 run-error logs (AD#154); by effect 0/949 | expected-known (P `run_error_imposes_outcome`), raised: carries a headline ASR | S2 | confirmed |
| PC-dca-agentdojo-04 | 2 of 15 Table 1 UA cells do not reproduce (DRIFT gpt-4o-mini 533 vs 553; gpt-oss secpol 256 vs 270) | documentation-mismatch (R3) | S2 | confirmed |
| PC-dca-agentdojo-05 | No deposit numbers for the clean-utility or Qwen2-7B tables | documentation-mismatch (R3) | S3 | confirmed |
| PC-dca-agentdojo-06 | Profile `context_artefacts` omit `results/paper_tables/*.md`, `results/paper_tables/*.tex` (3 files, found by the verifier) and `results/summaries/*.md` | documentation-mismatch (R4) | S3 | confirmed |
| PC-dca-agentdojo-07 | CaMeL tool results with no proposing call in ≥ 2,947 / 5,904 logs; the catalogued quirk `agentdojo.camel_orphan_tool_results` (artefact `agentdyn.art.camel_orphan_results`) is not declared for this profile, and its `*-camel` selector misses the `+camel` dirs | expected-known (R2; scope gap CC-09); verifier reclassified from source-defect R1 | S3 | confirmed |
| PC-dca-agentdojo-08 | The drift secret-like hit is benchmark text (token found in 1,735 other logs) | source-defect (CC-13 fixture, uncatalogued: R1, `agentdojo.art.fixture_secret_shapes` proposed, `release_scan` allowlist by digest; reclassified 2026-10-21 from expected-known) | S3 | confirmed |
| PC-dca-agentdojo-09 | No `artefacts.toml` entry scopes this source | documentation-mismatch (CC-09) | S3 | confirmed |
| PC-dca-agentdojo-10 | Tool definitions (null_final, CC-01 repeats, header count) differ from the census | analysis-artefact (R5, CC-01/CC-08) | S3 | confirmed |

Proposed `artefacts.toml` / profile text (routed to the AgentDojo family owner):
```
# PC-01/02: agentdojo.art.validity_defects scope += dca-agentdojo; rows (status proposed):
#   dca-agentdojo:v1 #181 17 executions (precedence-only 33); #161 v1 35 (33 attacked + 2 clean), drift 9; CaMeL 54 record-limited
# PC-03: run-error entry (AD#154) scope += dca-agentdojo:v1, 4 logs (3 DCA gpt-oss travel, 1 direct gpt-oss slack)
# PC-07 (verifier): no new id; declare the existing quirk agentdojo.camel_orphan_tool_results in the DCA profile with a
#   selector matching '*+camel' / '*+camel+secpol'; widen agentdyn.art.camel_orphan_results scope += dca-agentdojo:v1 (>= 2,947 logs)
# PC-06: context_artefacts += results/paper_tables/*.md, results/paper_tables/*.tex, results/summaries/*.md
```
Items for AGENTS.md §12:
- PC-03: the deposit's 3/949 residual DCA ASR for gpt-oss consists of 3 run-error logs; by effect it is 0/949.
- PC-07: the CaMeL arms have tool results without calls (≥ 2,947 logs); the catalogued quirk `agentdojo.camel_orphan_tool_results` is not declared for the DCA profile; L2 must not infer the missing call relation.
- No security finding: no account path anywhere in the pin, and the 2 secret-like hits are benchmark text and a placeholder.

## 8. Recommendations and readiness

1. Disclose PC-01 to PC-04 in the datasheet, next to the logged rates. Keep every logged boolean, and keep the drift part in full: 0 successes is never a reason to exclude it.
2. Route PC-01, PC-02, PC-03, PC-07 and PC-09 to the AgentDojo family owner, and PC-06 to the profile owner.
3. Draw and commit the L2 sample list now. Run L2 at the post-check once D-455 and items 96/97 have landed. Check that run on the CaMeL strata (evidence linkage, dangling relations).

**Readiness: `ready-with-caveats`** (verifier: confirmed, conditional). L1 matches every count expectation, and no finding blocks the round. The caveat is that Level 2 has never run on this corpus (blocked by D-455). Every mapping property (validate, recompute, determinism, A2/A3, evidence classes, identity) is therefore first measured in the round itself, and the post-check must treat it as a first mapping. The verdict is conditional on D-455 (regen item 101) landing in the round; without it the corpus cannot be imported and the verdict becomes `blocked` (as mcphunt, whose L2 is also unrun, is judged). PC-07's quirk declaration should land with the profile changes before the import.

Verifier (2026-10-21): re-ran `pop.py`, `checks.py`, `extra.py`, `dup.py` (outputs byte-equal to the examiner's) and read the deposit tables (5 md, 1 tex) and the raw DRIFT gpt-4o-mini, error-log and CaMeL banking records through `agentprov.ingest`. All 10 findings confirmed; PC-07 reclassified to expected-known (existing quirk, profile gap); PC-02 and PC-06 qualified. Reasoning per finding in `findings.json` `verdicts`.

## 9. Reproduction

```
S=docs/reports/precheck/data/dca-agentdojo/exam-scripts; E=~/.agentprov/migration-work/precheck/dca-agentdojo/exam
uv run python -I $S/pop.py $E/pop.json            # Table 1 comparison: rows_matched 13, flags []
uv run python -I $S/checks.py $E/checks.json      # #181, #161, CC-10, run errors, H6, H7, H9, H10
uv run python -I $S/extra.py $E/extra.json        # UT5 record detail, drift L1-06 hit, H7 clean arms
uv run python -I $S/toolmsgs.py $E/toolmsgs.json  # PC-07
uv run python -I $S/dup.py $E/dup.json            # H8 same-cell repeats 765 / 243
uv run python -I $S/h12.py $E/h12.json            # negative durations 2, tool 'none' 1
uv run python -I $S/nonlog.py $E/nonlog.json      # 111 non-log members: 0 account paths
uv run python -I $S/exam_build.py                 # exam.json, findings.json
# follow-ups (not run):
uv run python tools/precheck/l2_sample.py select --units ~/.agentprov/migration-work/precheck/dca-agentdojo/l1-units-v1.jsonl \
  --source dca-agentdojo --part v1 --corpus-id dca-agentdojo --out docs/reports/precheck/data/dca-agentdojo/l2-sample-v1.json   # and drift
# after D-455 + items 96/97: run_batch.py plan entry (sample, import_j2, import_j1, check) via tools/suite_queue.py --class import --cpu 2
uv run python tools/precheck/code_ident.py --corpus-id dca-agentdojo --part v1   # and drift
```
