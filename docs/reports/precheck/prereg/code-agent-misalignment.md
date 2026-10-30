# Pre-registration: `code-agent-misalignment`

| | |
|---|---|
| Corpus | `code-agent-misalignment` (family `geminicli`, dialect/mapper `geminicli.stream_json` variant `v1`, profile `code-agent-misalignment-geminicli@1`, catalogue `geminicli` v1, SEM `geminicli.tools@1`) |
| Parts | `code-agent-misalignment-geminicli` · `results-raw`: 2,182 non-empty `gemini_stream.jsonl` members of `RESULTS_raw.tar.zst` (Zenodo 20404563), with per-rollout sidecars |
| Code commit | `065b0d36` (branch `precheck-corpora`) or later |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Wave 6. Not a delta corpus: registry status `planned`, never imported, absent from FA and E2 |
| Desk research | `../data/code-agent-misalignment/research.json` (all URLs there) |

Sources: **P** = `src/agentprov/adapters/geminicli/profiles/code-agent-misalignment-geminicli.profile.toml`; **A** =
`src/agentprov/adapters/geminicli/artefacts.toml`; **C** = `docs/reports/phase10o/README.md` (census §3-§6, map census §9,
trial §10-§11); **L** = `tools/readme_corpora.toml`; **D** = `docs/architecture/DECISIONS.md` (D-143, D-330..D-337, D-372);
**Z** = Zenodo API record 20404563; **G** = GitHub `warmjademe/code_agent_agentic_misalignment` @ `1dec4f17` (tier-1
`RESULTS/`, code); **GM**/**GS**/**GD** = G's `RESULTS/manifest.csv` / `cell_summary.csv` / `diff_filter_stats.csv`.

## 1. Desk research summary

- **No public paper.** The study is an anonymous JSS submission under review ("Probing Agentic Misalignment Propensity in
  Code Agents"). arXiv and web searches found no preprint. The only author numbers are the deposit's `cell_summary.csv`
  (copied verbatim to G), the total in G's `ZENODO_UPLOAD.md` (1,787 of 10,000) and the README design (5 models × 4
  frameworks × 500 mutations).
- **Data record:** Zenodo has one version, 20404563, published 2026-05-27 under CC-BY-4.0. `RESULTS_raw.tar.zst` is
  207,950,011 B with md5 `c8f46f1e…`, and its `.sha256` file gives `f7186010…`. Both **equal P's pin**. No newer version.
- **Repository:** 3 commits. The head `1dec4f17` (2026-05-27T02:15:00Z) is P's cited commit and only adds the DOI to
  `RESULTS/README.md`. The tier-1 data came in with `a1289574` (01:41Z). There are no issues. `scripts/build_results.py`
  builds tier-1 from the raw bundle: it copies `verdict.json`, `manifest.csv`, `cell_summary.csv` and `README.md`
  verbatim, and it filters and redacts the diffs, recording `raw_bytes` per rollout in GD.
- **Harness (read for this step; D-334 kept the product at class I):** the entrypoint runs
  `timeout --preserve-status -k 5 240 gemini --yolo -m $OE_MODEL -o stream-json`, so a CLI killed at 240 s exits 143.
  The entrypoint ends with `exit 0` whatever the CLI returned (it exits non-zero only if the task file is missing, exit 2,
  or a post-run step fails under `set -e`; corrected in the fact-check). `verdict.exit_code` is the `docker run` return code, and `timed_out` is an outer
  timeout of 300 s. `elicited` is the mutation's detector on the **workspace diff only**: the transcript passed is empty,
  and an exception counts as false. Runner logs keep their last 50,000 characters.
- **gemini-cli:** the configs say "Gemini CLI 0.14". The Docker base image is unpinned (`:latest`). The stream-json schema
  of v0.11-v0.21 equals the census vocabulary. v0.22 added `stats.cached` and `stats.input`.
- **Routing:** every gemini_cli config sets `OE_MODEL "gemini-2.5-pro"`, which is why `init.model` is the same in every
  cell. gemini-2.5-pro goes direct to Google. Sonnet goes through a hand-written sidecar to the "simpleai" relay, gpt-5.3-codex
  through a sidecar to the "shqbb" relay, and MiniMax-M2 through a **stock LiteLLM Gemini-surface bridge** (corrected:
  `configs/sut/gemini_cli_minimax.yaml` points at `127.0.0.1:4000`, while `litellm/minimax_gemini.yaml` describes itself
  as the :4006 bridge, so the port actually used is not settled). The authors' own config comments name :4006 among the
  bridges whose LiteLLM back-translation strips tool-call args. No gemini_cli GLM-4.7 config is published:
  the glm5 configs route to glm-5.1. A registry comment says the gpt relay answered with gpt-5.4.
- **Licence:** the data is CC-BY-4.0 and the code MIT. The README's "raw transcripts on request" contradicts the open deposit (S3).

## 2. Expected counts

| Quantity | Expected | Source |
|---|---:|---|
| Pinned file | 207,950,011 B, md5 `c8f46f1eae55897fe55955f368d5da77`, sha256 `f7186010…3cf`; 1 zstd frame, 1,464,483,840 B decompressed | P; Z; C §1 |
| Archive members | 63,384 regular, 12,193 dirs, 1,642 GNU long names, 0 pax | C §3 |
| Rollouts (all / gemini_cli) | 10,000 / 2,500 (one `verdict.json` each) | C §3; Z; GM |
| `gemini_stream.jsonl` files / non-empty / empty / absent | 2,357 / **2,182** / 175 / 143 | C §3; L (2,182) |
| Non-empty per cell (sonnet / gpt / glm / gemini / MiniMax) | 460 / 461 / 457 / 420 / 384 | C §3 |
| Units = executions | 2,182 `agent_execution` (one per non-empty stream) | L; D-330/331 |
| Events | 107,006 (init 2,182, message 34,804, tool_use 34,281, tool_result 34,208, error 68, result 1,463) | C §4 |
| Sidecars | `gemini_meta.json` 2,357; `atoms.flat` 757; `events.jsonl` non-empty beside a stream 2,179 (A) + 141 in no-stream rollouts | C §3, §6; A |
| `final_diff.patch` (gemini_cli) | 2,500; 1,073 zero-byte; 14 > 1 MiB (all gemini-2.5-pro, max 32,723,159 B); total 319,646,502 B | C §3; GD |
| Register (trial) | `select.out_of_scope` 7,500; `geminicli.no_stream` 143 (+890 siblings); `geminicli.empty_stream` 1 (+9); `dedup.collapsed` 174 | C §10 |
| Map census (phase 10o code) | 2,182 mapped, 0 degenerate; run status ok 968 / error 495 / aborted 719; 22,893 model calls, 34,208 tool executions, 59,283 messages | C §9 |
| Withheld | 1 execution (the `AIza…` key shape), 2,181 releasable | P `[withhold]`; A; D-336 |

## 3. Expected arms (L1-05)

Facets: model (5) × skeleton (51) × mutation. There is no defence or attack facet (`not_recorded`, D-330). The L2 strata
are `(model, skeleton)`: 255 strata.

| Model (cell label) | rollouts | non-empty streams | empty | no stream | route (G configs) |
|---|---:|---:|---:|---:|---|
| claude-sonnet-4-6 | 500 | 460 | 40 | 0 | sidecar → simpleai relay |
| gpt-5.3-codex | 500 | 461 | 39 | 0 | sidecar → shqbb relay |
| glm-4.7-probe | 500 | 457 | 43 | 0 | **not published** (only glm5 → glm-5.1) |
| gemini-2.5-pro | 500 | 420 | 34 | 46 | Google direct |
| MiniMax-M2 | 500 | 384 | 19 | 97 | stock LiteLLM Gemini bridge (SUT config :4000; LiteLLM yaml :4006) |

- Each cell has the same 500 mutation ids (GM): 41 skeletons with `m01`-`m10` and 10 with 9. The missing pool slots are
  ASSERTWEAKEN m01, AUDITDEL m01, CACHESTALE m04, COOKIEFLAGS m03, CORSWIDE m01, DELETE m03, DEPDOWN m04, DIVZERO m01,
  FAILOPEN m05 and FKDROP m02 (a 510-slot pool less 10; the 510 is inferred from 51 × m01-m10 and the orchestrator's
  default `--target-n 510`, while the README states a pool of |V| = 500). Expect 0 extra and 0 duplicate rollout directories.
- Missing cells in the corpus: the 318 rollouts without a stream, excluded by format and never by outcome.
- Out of scope: 15 cells (claude_code, codex_cli, openhands), registered `select.out_of_scope` (D-143).

## 4. Expected outcome rates

**Mapping.** Each run has one judgement from `verdict.json` (`elicited`, `n_misaligned`; actor `detector`, origin
`checker`, class I `geminicli.detector_recorded_unverified@1`). The SEM outcome `geminicli.misalignment_elicited` holds
iff `elicited`. The author metric is `n_elicited / n` per cell over all 500 rollouts (GS). The corpus denominator is
the non-empty streams. All 175 empty-stream rollouts are `elicited: false`, and 19 of the 143 no-stream rollouts are
elicited (C §6). The corpus rates therefore differ from the paper's by construction:

| Arm (model) | paper n_elicited/n (GS) | paper rate | expected corpus rate (all non-empty streams) | L2 sample (≈) |
|---|---:|---:|---:|---:|
| claude-sonnet-4-6 | 59/500 | 11.8 % | 59/460 = **12.83 %** | ~63 |
| gpt-5.3-codex | 68/500 | 13.6 % | 68/461 = **14.75 %** | ~63 |
| glm-4.7-probe | 107/500 | 21.4 % | 107/457 = **23.41 %** | ~63 |
| gemini-2.5-pro | 120/500 | 24.0 % | [101, 120]/420 = **24.05-28.57 %** | ~58 |
| MiniMax-M2 | 28/500 | 5.6 % | [9, 28]/384 = **2.34-7.29 %** | ~53 |
| all gemini_cli | 382/2,500 | 15.28 % | 363/2,182 = **16.64 %** | ~300 |

The gemini-2.5-pro and MiniMax-M2 counts sum to 129, and the 19 excluded elicited rollouts are split between those two
cells. The L1 whole-population recount fixes the split. The L2 outcome check (README §4) compares each model's sample rate
with the exact corpus rate from L1, and with the paper rate only as context. Threshold: a gap > 15 pp on an arm with ≥ 20
sampled units, or a Wilson 95% interval that excludes the corpus rate by > 5 pp. There is no utility or ASR metric.

## 5. Known quirks (already declared)

| Id | Expected | Where |
|---|---|---|
| `geminicli.art.out_of_scope_scaffolds` | 7,500 rollouts | A; D-143, D-331 |
| `geminicli.art.rollouts_without_stream` (`empty_stream` 175, `no_stream` 143; 19 elicited) | 318 | A; P quirks |
| `geminicli.art.leaked_credential` / `[withhold]` `google-api-key-shape` | 1 execution | A; P; D-336 |
| `geminicli.art.no_result_event` (exit 143) | 719 (last event tool_result 623, tool_use 73, message 23) | A; D-335 |
| `geminicli.art.cli_error_result` | 495 | A |
| `geminicli.art.unanswered_last_call` | 73 calls | A |
| `geminicli.art.cli_model_alias` | 1,762 (every cell but gemini-2.5-pro) | A; D-333 |
| `geminicli.art.verdict_meta_disagree` | 1,214 | A; D-335 |
| `geminicli.art.subagent_internals` | A's count: 73 tool executions (76 calls in 29 streams, 3 unanswered); counter differs in 20 | A; C §9 |
| `geminicli.art.cli_notice` | 68 warning events | A |
| `geminicli.art.result_without_output` | 3,313 | A |
| `geminicli.art.hidden_retries` | 793 stderr retry lines (MiniMax-M2 718) | A |
| `geminicli.art.derived_harness_atoms` | 2,179 `events.jsonl` | A; D-330 |
| `geminicli.art.missing_route_config` | 457 (glm cell) | A |
| `geminicli.art.cli_call_ids` / `emission_times` / `derived_model_calls` | 34,281 calls; all times ambiguous; model calls class I | A |
| `label_field_mismatch`, `manifest_differs`, `sidecar_problem`, `unmapped_event`, `events_after_result` | 0 each | A |
| Completeness of aborted runs (D-372) | on HEAD (`b7b7d5bf`): the 646 `index.completeness` chain failures of the phase-10o trial should not recur | C §10; D-372 |
| Secret-like strings (counts only) | 1 `AIza` value; 53 distinct key/secret/password/token assignments; 154 e-mails; 16 private IPv4; 1 PEM header and 1 JWT (both in `final_diff.patch` only); `/home/ubuntu/` 1,393, `/home/user/` 1 | C §6 item 6 |

## 6. Expected movement since E2

Not applicable: the corpus was never imported, so it has no FA or E2 baseline. The reference is the phase-10o map census
and trial (C §9-§11, phase-10o code). At `065b0d36`, counts should be unchanged (H-19). Digests may move with later core
version bumps; that is expected and is not a finding.

## 7. Check map

| Check | Applies | How / note |
|---|---|---|
| L1-01 counts | yes | §2: 2,500 gemini_cli rollouts → 2,182 units; per-cell table §3; profile selection (`include`/`exclude`, auxiliaries) |
| L1-02 strict parse | yes | streams (JSONL, LF-terminated) plus `verdict.json`/`gemini_meta.json`/`fs_*.json`; expect 0 findings of any class (C §4) |
| L1-03 encodings/escaping | yes | expect 0 bidi/tag/zero-width outside agent-written code; escape residues expected inside code (descriptive) |
| L1-04 duplicates | yes | 175 zero-byte streams byte-identical (174 collapsed, expected-known); user prompt identical per mutation across the 5 models (500/500, expected); 0 fingerprint duplicates among non-empty streams; 0 cross-corpus overlap (no other registered part holds this deposit) |
| L1-05 arm coverage | yes | §3 grid: 5 × 500 rollouts, same 500 mutations per cell, 10 pool slots absent everywhere, 0 extra |
| L1-06 secrets/paths | yes | §5 counts by pointer only; the key is withheld (D-336); classify `/home/ubuntu/` by member role (H-17) |
| L1-07 timestamps | yes | 107,006 UTC `Z` ms values, non-decreasing per stream, 1,714 streams with repeats (C §4); range per H-16 |
| L1-08 degenerate | yes | 175 empty (`zero_messages` flag); 719 `unterminated`; 0 non-empty streams without init and user message |
| L2 selection/import | yes | `l2_import.py` ARCHIVE pin `10e/zenodo_20404563` (not in BLOCKED); strata `(model, skeleton)` = 255 → 300 units, ≥ 1 per stratum |
| L2 validate / recompute / determinism | yes | all tiers; `recompute --dry-run` 0 differences (it was stopped in phase 10o, so this is its first run); two `--jobs` byte-identical |
| L2 verify chain | yes | sealed scratch copy with withholding; expect 0 `index.completeness` failures (D-372 on HEAD) |
| L2 A2/A3, evidence classes | yes | 0 crash/degenerate/`adapter_defect`; class-I heavy by design (model calls, tool link, requested model, judgements, aborted status); no invented relation for the sidecar artefacts (`fs_after`, diff, logs: no PROV relation) |
| L2 identity | yes | `model.requested` = cell label (I), `served` `not_recorded`, `ext.geminicli.cli_model` = `gemini-2.5-pro` everywhere; `cli_model_alias` on every non-gemini-2.5-pro sampled run |
| L2 redaction | yes | 0 host account paths in AER/SEM/PROV (H-17) |
| L2 withholding | yes | if the key-bearing execution is sampled, it and its stream are withheld and no released byte matches `AIza[0-9A-Za-z_-]{35}`; if it is not sampled, assert 0 matches in released bytes |
| L2 outcome sanity | yes | §4, per model, against the L1 exact corpus rate |

## 8. Hypotheses (falsifiable)

| Id | Expectation | Falsified if |
|---|---|---|
| H-01 | Staged file = P = Z (size, md5) = `.sha256` (sha256) | any difference |
| H-02 | Counts as §2 and §3 (members, rollouts, streams per cell, events by type) | any count ≠ (tolerance 0) |
| H-03 | Every gemini_cli cell holds exactly the 500 mutation ids of GM; the 10 slots of §3 absent in all 5 | any extra, missing or duplicate directory |
| H-04 | The 2,500 gemini_cli `verdict.json` are byte-identical to G's tier-1 copies (git blob ids at `1dec4f17`; `build_results.py` copies verbatim) | any blob id differs (S2 documentation-mismatch: a different snapshot) |
| H-05 | `RESULTS_build/manifest.csv` sha256 = `35344806…8577` and `cell_summary.csv` = `7c962212…3c39` (GM, GS); `README.md` git blob = `c2fbaab8` (G at `a1289574`) | any differs |
| H-06 | Each gemini_cli `final_diff.patch` size = GD `raw_bytes` (2,500/2,500; 1,073 zero; 14 > 1 MiB) | any mismatch |
| H-07 | Verdict `elicited` per cell = GS (28/107/120/68/59 = 382); 363 among the 2,182 streams, 19 among the 143 no-stream, 0 among the 175 empty | any count differs |
| H-08 | Verdict `exit_code` 0 and `timed_out` false in 2,500; ≥ 95% of the 894 `gemini_meta` exit-143 rollouts have meta `elapsed_sec` in [240, 246]; verdict `elapsed_sec` ≥ 240 per cell = GM (21/172/258/80/389 = 920) | < 95%, or a per-cell count ≠ GM |
| H-09 | Stream schema = gemini-cli v0.11-v0.21 `stream-json`: 0 `result.stats` with keys beyond the five (no `cached`/`input`), 0 event keys outside the schema | any extra key (the version claim "0.14" is then wrong) |
| H-10 | `init.model` = `gemini-2.5-pro` in 2,182/2,182 (`OE_MODEL` in every config) | any other value |
| H-11 | MiniMax-M2 ran on an args-stripping bridge: the share of `tool_use` with `parameters == {}` is ≥ 10% in that cell and ≥ 10 × the largest share among the other four cells | MiniMax share < 10%, or < 3 × the others (then the low rate is not this artefact) |
| H-12 | MiniMax-M2 cell degraded by the provider: its share of streams ending in `result` error or with 0 `tool_use` is > 2 × the median of the other cells | ≤ 2 × |
| H-13 | The 143 no-stream rollouts are a packaging loss: 143/143 also lack `gemini_meta.json`, 141 have `events.jsonl` with `tool_use` atoms, and the median verdict `elapsed_sec` is > 30 s | median ≤ 10 s (a failed start, not a loss) or `gemini_meta.json` present |
| H-14 | 0 `file_after.json` and 0 `transcript_tail.txt` members in gemini_cli rollouts (the entrypoint writes the former; ZENODO_UPLOAD promises the latter) | either present (then the census missed a sibling role) |
| H-15 | Every `runner_stdout.log`/`runner_stderr.log` has ≤ 50,000 characters (tail kept by the runner); report how many have exactly 50,000 (truncated, contradicting Z's "untruncated") | any > 50,000 |
| H-16 | Timestamps in [2025-11-12 (gemini-cli 0.14), 2026-05-27T02:15Z (deposit)]; the sonnet cell ≥ 2026-02-17 and the gpt-5.3-codex cell ≥ 2026-02-05 (model releases) | any outside |
| H-17 | `/home/ubuntu/` occurrences are container paths (streams, tool outputs, fs maps); 0 occurrences of `jss_agent_work` or another host work root in any member | any host path (S2: redaction needed before release) |
| H-18 | `codebase_investigator` 76 calls in 29 streams; `stats.tool_calls` differs in exactly 20, all with that tool | different counts |
| H-19 | The map census at `065b0d36` reproduces C §9 (2,182 mapped, 0 degenerate, issue counts of §5) | any count differs (mapping-defect unless a documented version change explains it) |
| H-20 | A's 20 `expected` counts (7,500 / 318 / 1 / 793 / 2,179 / 457 / 719 / 495 / 73 / 1,762 / 1,214 / 73 / 68 / 34,281 / 3,313 / 0 × 5) are confirmed | any differs |
| H-21 | Sample `verify --level chain` gives 0 `index.completeness` failures (D-372) and `recompute --dry-run` gives 0 differences | any failure |
| H-22 | Documentation mismatches (desk-confirmed, S3): 50 seeds vs 51 skeletons; "in-house probe" vs claude_code; on-request transcripts vs open deposit; `RESULTS_build/` vs `RESULTS_raw/`; ~1.6 GB vs 1.46 GB | n/a (record) |

Never exclude data because a cell has few or no elicitations (user rule). The MiniMax-M2 cell stays in the corpus whatever
H-11/H-12 show. A confirmed H-11 is disclosed as a harness artefact of that cell.

## 9. Fact-check (adversarial, 2026-10-14)

An adversarial fact-check re-opened every cited source. It read only metadata and aggregate tables, not the pinned archive.

**Confirmed:**
- **Zenodo API record 20404563.** It is the only version of concept 20404562. It was created 2026-05-27T02:15:34Z under
  CC-BY-4.0, and the creator is "Anonymous". It holds two files:
  - `RESULTS_raw.tar.zst`: 207,950,011 B, md5 `c8f46f1e…`.
  - `.sha256`: 96 B.
- **The description's sha256 equals P's pin.** P's size and md5 equal Z.
- **GitHub repository.**
  - It has 3 commits: `82ca4554`, `a1289574` (01:41:14Z) and `1dec4f17` (02:15:00Z), and the head commit only adds 8
    lines to `RESULTS/README.md`.
  - It has 0 issues and an MIT LICENSE, "Copyright (c) 2026 The Authors".
- **`RESULTS/cell_summary.csv` at `1dec4f17`.**
  - Its sha256 is `7c962212…3c39`.
  - The gemini_cli rows are 28/107/120/68/59 of 500, which is 382, with `n_timed_out` 0.
  - The scaffold sums are 590/301/382/514, which is 1,787 and matches ZENODO_UPLOAD.md.
- **`manifest.csv` (sha256 `35344806…8577`).** Its gemini_cli rows give:
  - per-cell `elapsed_sec ≥ 240`: 21/172/258/80/389, which is 920;
  - `exit_code` 0 and `timed_out` 0 in 2,500 rows;
  - the same 500 mutation ids in all 5 cells, with 41 skeletons × 10 and 10 × 9, and exactly the 10 missing slots of §3.
- **`diff_filter_stats.csv` (sha256 `8ae168fb…`).**
  - Zero-byte diffs: 459/265/129/120/100, which is 1,073.
  - 14 diffs are over 1 MiB, all gemini-2.5-pro, with a maximum of 32,723,159 B.
  - The total is 319,646,502 B.
  - `raw_bytes` is `len(read_bytes())`, so it is a byte count, which suits H-06.
- **Harness code at `1dec4f17`.**
  - `run_mutation_agent.py`:
    - The outer timeout is `OE_RUN_TIMEOUT` + 60, which is 300 s with the published configs.
    - `exit_code` is the `docker run` return code.
    - The detector gets an empty transcript, and an exception counts as False.
    - The logs are cut to their last 50,000 characters.
  - Entrypoint: `timeout --preserve-status -k 5 240`, `gemini_meta.json`, `file_after.json`.
  - Dockerfile: `FROM overeager-bench/gemini-cli:latest`.
  - Orchestrator: a threshold of ≥ 510.
  - `build_results.py`: copies verdict, manifest, cell_summary and README verbatim.
  - Registry comment: the relay answered gpt-5.4.
  - Every gemini_cli config sets `OE_MODEL "gemini-2.5-pro"`, and there is no glm47 config.
- **gemini-cli.**
  - The `output/types.ts` blob `04483542` is the same in v0.11.0–v0.20.0.
  - v0.21.0 keeps the 5-key StreamStats, and v0.22.0 adds `cached`/`input`.
  - v0.14.0 was published 2025-11-12.
  - Issue #20183 was filed 2026-02-24 and closed 2026-05-19.
- **Model releases.** claude-sonnet-4-6 was released 2026-02-17, and GPT-5.3-Codex was announced 2026-02-05
  (https://en.wikipedia.org/wiki/GPT-5.3-Codex).
- **No preprint.** Searches found none: arXiv API and web search for the exact title, 2026-10-14.
- **Census and registry figures in §2-§4** match C (§3-§6, §9-§10) and L. The 20 expected counts of A are exactly H-20's
  list. The expected corpus rates recompute from the cited figures.

**Corrected:**
1. **MiniMax-M2 route.** The cell's SUT config points the CLI at `127.0.0.1:4000`, while `litellm/minimax_gemini.yaml`
   calls itself the :4006 bridge. That yaml uses LiteLLM's `minimax/MiniMax-M2` provider, not `hosted_vllm`. The cell
   ran on a stock LiteLLM Gemini-surface bridge either way, but the published code does not establish ":4006". H-11
   still tests the effect.
2. **Entrypoint exit status.** The entrypoint ends with `exit 0` but is not unconditional: a missing task file gives
   exit 2, and a failing post-run step under `set -e` gives a non-zero exit. The verdicts show 0 in all 2,500 rows.
3. **`codebase-investigator.ts`** is already present in gemini-cli v0.10.0, not only "from v0.11.0". This is research.json
   only.
4. **`subagent_internals`.** A's expected count is 73 tool executions (76 calls, 3 unanswered), not 76.
5. **The "510-slot pool" is an inference.** The README states a mutation pool of |V| = 500. The 510 comes from 51
   skeletons × m01-m10 and the orchestrator default.

**Unverifiable from public sources:**
- the served models of the glm-4.7-probe and gpt-5.3-codex cells;
- whether the archive's README is the `a1289574` blob (H-05 tests it);
- whether `/home/ubuntu/` in the data is a host path (H-17).
