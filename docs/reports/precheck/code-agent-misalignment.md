# Pre-check dossier: `code-agent-misalignment`

## 1. Header

| | |
|---|---|
| Corpus | `code-agent-misalignment` (wave 6; not a delta corpus: never imported, no FA/E2 baseline) |
| Part | `code-agent-misalignment-geminicli` · `results-raw` (`RESULTS_raw.tar.zst`, Zenodo 20404563) |
| Family / profile | `geminicli`, dialect `geminicli.stream_json` v1, profile `code-agent-misalignment-geminicli@1` (sha256 `965b84dc…`), SEM `geminicli.tools@1` |
| Code commit | `d97d3a57` (L1, L2; clean tree) |
| Code identity | adapter `geminicli.stream_json@0.1.0` `18e29966…`; engines expand `3b1d412b…`, aer `856b7a09…`, sem `bbc77e81…`, prov `d57bd291…`, validate `a10ee3c1…`; rules aer `55b64d5e…`, geminicli `96dda696…`, prov `79b0a1e7…`; limits `5d6dbb21…`; lock `b0455f10…`; CPython 3.14.8 (`data/code-agent-misalignment/code-results-raw.json`) |
| Date / agents | 2026-10-21; examiner agent (wave 6); one adversarial verifier (2026-10-21). Verdicts: 8 confirmed, 0 refuted (PC-02 reclassified) |

## 2. Sources

- Data: Zenodo 10.5281/zenodo.20404563 (one version, CC-BY-4.0). Code: https://github.com/warmjademe/code_agent_agentic_misalignment @ `1dec4f17` (MIT; tier-1 `RESULTS/` copies of the verdicts and CSVs). No public paper: the author numbers are `cell_summary.csv` (GS). All URLs are in `data/code-agent-misalignment/research.json`.
- Data versus documentation: the deposit's open raw transcripts contradict the README's "on request" line. The census has 51 skeletons where the README says 50 seeds. The tier-1 diffs are filtered and redacted (`build_results.py`), but the raw bundle's diffs are not: see PC-01.

## 3. Expectations

[`prereg/code-agent-misalignment.md`](prereg/code-agent-misalignment.md) (commit `fd75f8a3`), hypotheses H-01..H-22.

## 4. Level 1 (whole population)

**Reconciling 2,182 with 2,500.** L1 has one unit per gemini_cli rollout: the stream when there is one, else `verdict.json`. That gives 2,500 units:

| Units | 2,182 non-empty streams | 175 empty streams | 143 no stream (verdict only) |
|---|---:|---:|---:|
| registry/corpus | executions | `select.not_execution_artefact` (`geminicli.empty_stream`) + `dedup.collapsed` | `select.not_execution_artefact` (`geminicli.no_stream`) |

The registry figure (2,182 streams) is therefore the execution count. Both figures are correct.

| Check | Result (denominator) | vs prereg |
|---|---|---|
| L1-01 | 63,384 members walked: selected 2,500, auxiliary 22,829, `select.out_of_scope` 7,500, `not_execution_artefact` 2, not selected 30,553 | = |
| L1-02 | 2,500/2,500 ok; 12,214/12,214 aux ok | = |
| L1-03 | escape residues in code arguments and outputs (96 artefacts); `json_in_string` 18; 1 variation selector in `/content`; 0 bidi/tag/zero-width | = (descriptive) |
| L1-04 | byte-identical: 1 group of 175 (the empty streams; the cross-corpus match with controlarena-persistent is the empty file, which is trivial). Trajectory-identical: 27 groups / 86 units | groups ≠ 0 → PC-06 (CC-01) |
| L1-05 | 255 strata (5 models × 51 skeletons); 500 per model; mutations m01 235, m02 250, m03 245, m04 245, m05 250, m06–m10 255; 0 missing, 0 extra | = (H-03) |
| L1-06 | generic home paths in 149 artefacts (1,394 strings); generic credential assignments 44 (85); `AIza` shape 1 (withhold rule 1); **stripe `sk_live_` shape 14 artefacts (35)**; named accounts 0 | stripe not pre-registered → PC-02 |
| L1-07 | 107,006 `Z` stamps: 0 parse failures, 0 non-monotone, all on 2026-05-25; 318 units without timestamps | = (H-16) |
| L1-08 | empty 175, no_stream 143, unterminated 719, zero_messages 175 | = |
| L1-09 | 0 metadata members | n/a |
| L1-10 | 10,615 files, 367 with a hit: named home-dir accounts in 272 files (2 digests); Windows `foo` in 12; PEM 2, JWT 2 and stripe 2 files; operator 0 | **PC-01** (security) |

Exam census (`exam-census.json`, `exam-context.json`):

- Event, exit and stream counts reproduce C §4 and §9: run status ok 968, error 495, aborted 719; last event `tool_use` in 73 streams.
- `final_diff.patch` aggregates equal GD.
- `manifest.csv`, `cell_summary.csv` and README digests equal G.
- The runner logs are never cut at 50,000 characters.
- The 143 no-stream rollouts lack `gemini_meta.json` (143/143), and their median `elapsed_sec` is 55.4 s.

## 5. Level 2 (sample)

| Item | Result |
|---|---|
| Sample | [`l2-sample-results-raw.json`](data/code-agent-misalignment/l2-sample-results-raw.json): 300 labels / 255 strata. 251 executions; 49 labels have no execution (25 no-stream, 24 empty-stream). MiniMax-M2 has 96 labels because of the remainder rule (PC-07, R6) |
| Validate | 251/251 passed; linkage 100%; shacl skipped; regression n/a |
| Recompute `--dry-run` | 251 identical, 0 unexplained (first run for this corpus) |
| Determinism | j1 = j2: 19,871 files, index identical |
| Verify chain | 0 failures. The only issue is `checksums.absent` (an unsealed working tree); 0 `index.completeness` failures (D-372, H-21) |
| A2 / A3 | 0 degenerate, 0 `adapter_defect`, 0 crashes; A3 none |
| Status / completeness | ok 96, ok_with_issues 155; `known_incomplete` 82, `unverifiable` 169 |
| Issue codes | `cli_model_alias` 211, `verdict_meta_disagree` 155, `incomplete_run` 155, `cli_error_result` 79, `no_result_event` 76, `subagent_internals_unobserved` 7, `cli_notice` 5, `missing_tool_result` 3, `accounting_inconsistent` 3, `accounting_unverifiable` 238 |
| Evidence classes | core D 1,757 / O 16,338; inference I 174,909; assessment I 178,130 / O 502. Twin 0, mixed 0. Every class-I statement comes from a native `_unverified` rule (inference I 174,909, assessment I 12,543) |
| Identity | model 251/251 equals the cell label, 0 mismatches; `cli_model_alias` on 211/211 non-gemini-2.5-pro executions |
| Judgement mapping | mapped `elicited` equals the raw verdict per model (5/5/8/9/6) |
| Redaction | home paths in AER/PROV in 10 executions, all generic; 0 named accounts, 0 `jss_agent_work`, 0 `/Users/`. The stripe fixture appears in 10 AER and 5 PROV `apv:args` hits (PC-02) |
| Withholding | the key-bearing stream (gemini-2.5-pro SK-DELETE m07) is not in the sample. 2 objects are withheld (profile rule 1, container 1) and 0 executions. The `[withhold]` scope covers executions only, not context artefacts (PC-01) |

## 6. Outcome comparison (`elicited`; `exam-outcomes.json`)

| Arm (model) | L1 corpus k/n, rate [Wilson 95] | paper (GS, /500) | gap pp | L2 sample k/n, rate [Wilson 95] | verdict |
|---|---|---:|---:|---|---|
| MiniMax-M2 | 22/384, 5.73% [3.81, 8.52] | 5.6% | +0.13 | 5/72, 6.94% [3.00, 15.25] | no gap |
| claude-sonnet-4-6 | 59/460, 12.83% [10.08, 16.19] | 11.8% | +1.03 | 5/46, 10.87% [4.73, 23.04] | no gap |
| gemini-2.5-pro | 107/420, 25.48% [21.54, 29.85] | 24.0% | +1.48 | 8/40, 20.00% [10.50, 34.76] | no gap |
| glm-4.7-probe | 107/457, 23.41% [19.76, 27.51] | 21.4% | +2.01 | 9/47, 19.15% [10.42, 32.54] | no gap |
| gpt-5.3-codex | 68/461, 14.75% [11.81, 18.28] | 13.6% | +1.15 | 6/46, 13.04% [6.12, 25.67] | no gap |
| all | 363/2,182, 16.64% [15.13, 18.26] | 15.28% | +1.36 | 33/251, 13.15%; post-stratified 14.13% | R6 |

- No arm is flagged by the gap rule.
- The rollout-level recount (382/2,500) equals GS exactly. The corpus/paper difference is the 19 elicited stream-less rollouts (PC-05).
- MiniMax-M2's low rate comes with 351/384 CLI-error runs (PC-03). It is disclosed and never excluded.

## 7. Findings

| Id | Title | Class (CC) | Sev | Sec | Verdict |
|---|---|---|---|---|---|
| PC-code-agent-misalignment-01 | Host work-root path `/home/<named>/jss_agent_work/` in 272 raw-store `final_diff.patch` files (836 matches, diff header lines, 1 named length withheld account; verifier re-counted 272 objects in the scratch raw store, 0 in AER/SEM/PROV). The "second account" in 11 patches is a length withheld placeholder in agent-written lines (resolved, not CC-11); PEM/JWT shapes in 2 patches are agent-written | source-defect (CC-11) | S2 | yes | confirmed |
| PC-code-agent-misalignment-02 | `sk_live_` Stripe shape: 1 distinct SK-SECRETLOG fixture value (same value in gemini-2.5-pro and gpt-5.3-codex runs, in `old_string`, placeholder-shaped) in 14 streams + 14 events.jsonl + 2 patches. Reaches AER (10) / PROV args (5); uncatalogued | source-defect (CC-13 fixture: uncatalogued, provider-live-prefixed shape in PROV `apv:args`; reclassified 2026-10-21 from the verifier's expected-known, security no→yes) | S2 | yes | confirmed |
| PC-code-agent-misalignment-03 | MiniMax-M2: 351/384 CLI error results (meta exit 244). 0 empty tool parameters in any cell (H-11 refuted) | expected-known (`cli_error_result`) | S2 | no | confirmed |
| PC-code-agent-misalignment-04 | `subagent_internals`: 76 calls in 72 streams, not 29 | documentation-mismatch (R4) | S3 | no | confirmed |
| PC-code-agent-misalignment-05 | Corpus vs paper denominators (318 stream-less rollouts, 19 elicited) | expected-known (`rollouts_without_stream`) | S3 | no | confirmed |
| PC-code-agent-misalignment-06 | 27 trajectory-identical groups (short runs) | analysis-artefact (CC-01, R5) | S3 | no | confirmed |
| PC-code-agent-misalignment-07 | Sample remainder skew (MiniMax-M2 96/300); 49 labels with no execution; `foo` not in `GENERIC_ACCOUNTS` | analysis-artefact (R5/R6) | S3 | no | confirmed |
| PC-code-agent-misalignment-08 | Deposit documentation mismatches (H-22, desk; the size item, ~1.6 GB vs 1.46 GB, is plausibly block allocation: undetermined) | documentation-mismatch (R3) | S3 | no | confirmed |

CC-07 (#181/#161) does not apply: this is a gemini-cli corpus, not an AgentDojo-format corpus. CC-05 and CC-09 do not apply either.

Hypotheses:

- **Supported:** H-01, H-02, H-03, H-05, H-06 (aggregate), H-07, H-08, H-09, H-10, H-12, H-13, H-14, H-15, H-16 and H-21.
- **Supported at the raw level and on the sample:** H-19. The population map census was not re-run.
- **Partly tested:** H-20 (14/20 confirmed, 6 not tested).
- **Refuted:** H-11, H-17, and H-18 in part (streams).
- **Not tested:** H-04 (no clone).
- **Recorded:** H-22.

Proposed `artefacts.toml` entries (text only; for the geminicli family owner):

```toml
# PC-01
# id = "geminicli.art.host_path_in_diff"; count 272 final_diff.patch (836 matches, 1 named account, next segment jss_agent_work); context artefacts only; handling: withhold at seal (proposed, user decision under CC-11)
# PC-02
# id = "geminicli.art.fixture_secret_shapes"; 1 sk_live_-prefixed value, 14 SK-SECRETLOG streams (35 matches) + their events.jsonl; reaches AER/PROV apv:args; release_scan allowlist by digest or [withhold] (owner)
# PC-03: geminicli.art.cli_error_result per-cell split MiniMax-M2 351, gemini-2.5-pro 88, glm-4.7-probe 33, gpt-5.3-codex 20, claude-sonnet-4-6 3
# PC-04: geminicli.art.subagent_internals description "76 calls in 72 streams"
```

AGENTS.md §12 items:

1. PC-01: 272 raw-store patches hold a third-party host work-root path. Withhold or redact them before the seal (CC-11).
2. PC-03: the MiniMax-M2 rate is a degraded-run rate; disclose it.
3. PC-02 (CC-13): an uncatalogued `sk_live_` fixture shape reaches PROV `apv:args`, S2 security; catalogue it (`geminicli.art.fixture_secret_shapes`) and add a `release_scan` allowlist entry by digest or a `[withhold]` before the seal.

## 8. Recommendations and readiness

1. **PC-01 goes to the orchestrator now (security).** The user decides between two options:
   - withhold the 272 patches at seal with their digests kept (the D-345/CC-11 precedent);
   - redact them in the profile.

   Two related changes go with either option: the `[withhold]` scope must reach context artefacts, and the `release_scan` third-party home-path detector must cover `final_diff.patch`. The verifier resolved the 11 second-account patches: a length withheld placeholder name, not a CC-11 account.
2. PC-02 (CC-13 fixture; S2 security because the `sk_live_` shape reaches PROV `apv:args`): the family owner catalogues the fixture value and decides a `[withhold]` or a `release_scan` allowlist entry before the release scan.
3. PC-03 and PC-05: disclose both in the datasheet next to the per-cell rates. No exclusion of any data, MiniMax-M2 included.
4. PC-04: correct the documentation.

**Readiness: `ready-with-caveats`.**

- The mapping is sound: 251/251 validate, recompute 0 differences, j1 = j2, 0 degenerate, mapped judgements equal the raw values, identity has 0 mismatches, and L1 outcomes equal GS in 5/5 cells.
- The caveat is PC-01 (security, CC-11): its withhold or redaction must be decided before the seal. PC-02 is a CC-02-class fixture disclosure that still needs a catalogue entry and a release_scan allowlist or withhold. Both affect the deposit, not the import.
- Verifier (2026-10-21): all 8 findings confirmed; PC-02 reclassified to expected-known, security no; readiness unchanged. No outcome gap.

## 9. Reproduction

Batch: `tools/precheck/plans/wave6.toml` (entry `code-agent-misalignment`, `l1 = ["--input", "~/.agentprov/staging/10e/zenodo_20404563/RESULTS_raw.tar.zst"]`), run through `tools/suite_queue.py --class import --cpu 2 --label precheck-wave6 -- uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave6.toml`. Steps are as in the interbolt dossier §9, with `--source code-agent-misalignment-geminicli --part results-raw`.

Examiner scripts. They are read-only and stream through `l1_scan.ArchiveSource` (`agentprov.ingest`). Here S = `docs/reports/precheck/data/code-agent-misalignment/exam-scripts`, W = `~/.agentprov/migration-work/precheck/code-agent-misalignment`, and D = the data directory.

```bash
uv run python -I S/census.py W/exam/census.json       # H-02..H-18, PC-02..PC-05 (copied to D/exam-census.json)
uv run python -I S/patches.py W/exam/patches.json     # PC-01, L1-10 roles/digests (D/exam-context.json)
python3 -I S/outcomes.py D > D/exam-outcomes.json     # section 6
python3 -I S/build_findings.py D                      # findings.json
```

Follow-ups (not run):

| # | What | Command |
|---|---|---|
| 1 | H-04: compare the 2,500 verdict blob ids with G's tier-1 copies (needs a staged clone; user yes for the fetch) | `GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file git --git-dir <clone> ls-tree -r 1dec4f17 RESULTS/` vs the archive digests |
| 2 | H-19/H-20 rest: population map census at the round's code (793, 2,179, 1,214, 3,313, 73) | full import through the queue: `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-cam -- uv run agentprov import code-agent-misalignment-geminicli --input ~/.agentprov/staging/10e/zenodo_20404563 --corpus <scratch>` |
| 3 | PC-01: a sealed scratch copy with the decided withhold, then `verify --level chain` and `release_scan` | after the user decision |
