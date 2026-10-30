# Pre-check dossier: `craibench-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `craibench-agentdojo` (MIT, the upstream AgentDojo LICENSE; the finetune card's CC-BY-4.0 covers that dataset only) |
| Parts | `craibench-agentdojo · head` (1 part) |
| Family / profile | `agentdojo` / `craibench-agentdojo@1` (dialect `agentdojo.tracelogger`, variant v0.k11, semantics `agentdojo.suites@2`) |
| Pin | git `AthaSSiN/CrAIBench` @ `e41eac1e` (2026-01-09), 1,344 blobs, 1 absent (130 B LFS pointer) |
| Code commit | `d97d3a57` (L1 and L2, batch `wave3`, all 6 steps rc 0, tracked_changes false, after the CC-08 fix `5efa3575`) |
| Kind | wave 3, first examination (not in FA or E2); no stored corpus |
| Date | 2026-10-14 (prereg), 2026-10-15 (L1, L2 batch), 2026-10-21 (examination) |
| Agents | researcher and fact-checker (prereg), examiner (this dossier); adversarial verifier (2026-10-21: 10 confirmed, 0 refuted, PC-04 S2 -> S3) |
| Data | [`data/craibench-agentdojo/`](data/craibench-agentdojo/): `research.json`, `l1-head.json`, `l1-10-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `findings.json`, `os1-population.json`, `os1-gap.json`, `os2-sample.json`, `raw-census*.json`, `cc07.json`, `xpipe.json`, `exam-scripts/` |

- Code identity, part `head` ([`code-head.json`](data/craibench-agentdojo/code-head.json)): commit `d97d3a57` (tracked_changes false); engine code aer `856b7a09e0cf`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `agentdojo.tracelogger@0.1.0` `03d8bc6d30df`; profile sha256 `77787056ba3e`, rules agentdojo 2 / aer 1; lockfile `b0455f1058c8`, limits `5d6dbb210259`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Repository | https://github.com/AthaSSiN/CrAIBench @ `e41eac1e` | the data. Runs come from `a512e34a` (19 datamarking), `be71b1f5` (128 delimiting chain + 3 banking) and `dc1a1a73` (1,013 crypto). No later commit touches `runs/` |
| Paper | arXiv 2503.16248 **v2** (2025-04-30), https://arxiv.org/abs/2503.16248v2 | Table 1 gives the design; Tables 2 and 3 give the full results. v3 drops the full tables |
| Data record | none | integrity rests on the git blob ids |
| Upstream issues | ethz-spylab/agentdojo #181, #161 | CC-07 |

Data-versus-paper notes (checked against the data):

- The MI cells reproduce v2 Secure, which ties the release to the paper. Crypto MI multi ASR is 307/413 exactly. The T3 row labelled DAO/NFT matches crypto MI single for gpt-4o exactly (14 / 44 of 80), which supports the T1/T3 label swap.
- The PI cells do not reproduce. Crypto ASR is 3.65% against 21.88%, and chain ASR is 34% against 54% (PC-01, PC-02). No T2 prompt condition matches them.
- Prompt condition: 1,114 logs carry a `default_defended`-containing prompt (Secure). There are 27 crypto extra-injection logs with a Default-type prompt inside the Secure cells (PC-04).
- The paper's signed PI wrapper (Fig. 15) is present in 340 of the 384 crypto PI logs. Chain PI is unsigned (PC-05).

## 3. Expectations

The pre-registration is [`prereg/craibench-agentdojo.md`](prereg/craibench-agentdojo.md), committed in `fd75f8a3` (2026-10-14) before any check of this corpus ran. Amendments 2–5 apply where relevant; amendment 1 does not (there is no stored corpus).

| H | Result | Note |
|---|---|---|
| H1 | supported | 1,163 selected = MI 688 + PI 435 + prepass 40; every §3 cell count is exact |
| H2 | supported | strict parse ok 1,163/1,163 |
| H3 | supported | 0 U+FFFD, 0 mojibake. `^` joining appears in 13 of the 19 datamarking logs and in 0 delimiting logs |
| H4 | refuted as worded | 2 cross-pipeline trajectory-identical pairs. Their call ids and durations differ, so they are distinct runs (CC-01, PC-08). Byte-identical 0; cross-corpus 0 |
| H5 | refuted | 4 variants as profiled, but a Default-type prompt appears in 27 logs of the Secure crypto group (PC-04) |
| H6 | refuted | crypto PI: 340 signed, 30 unsigned, 14 with neither form; chain 50 unsigned; `<data>` in 2 of the 3 banking logs (PC-05) |
| H7 | refuted | PI: utility 311 vs 243 and ASR 14 vs 84 (PC-01). MI: ASR 307 is exact; utility is 150 vs 140 (PC-03) |
| H8 | refuted for PI and MI multi | PI 24 / 17 vs 13 / 27; MI multi 0 / 49 vs 0 / 45; MI single 1 / 14 is exact (PC-02) |
| H9 | gpt-4o supported; mini refuted | gpt-4o 14 / 44 exact. mini 34 / 70 vs 34 / 80; all 10 failures are injection_task_4 (PC-03) |
| H10 | supported | 688 MI logs with 2 user messages; 475 others with 1 |
| H11 | supported | `gpt-4o` resolves to the alias verbatim (43 sampled units); there is no dated snapshot |
| H12 | supported | L1-06: 0 of 1,163; L1-10: 0 hits in 6 context files |
| H13 | supported | 0 timestamp pointers; L1-08 flags {} |
| H14 | supported | `siphon` 144, `secure_funds` 0 |
| H15 | supported | 53/53 ok, 0 failing checks, recompute 0 differences, determinism 225/225 files, identity 100% |
| H16 | not tested | no paper-comparable L2 cell reaches n ≥ 20 (R6) |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: the staged bare clone at `e41eac1e` (`--git`), tool `l1_scan` at `d97d3a57`.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 1,344 walked = 1,163 selected + 174 not selected + 6 context + 1 absent blob. Units 1,163 = registry = census | as expected |
| L1-02 parse | ok 1,163/1,163; 0 of every class | as expected |
| L1-03 encodings | escaped-newline residues: 15 strings at `/messages/*/content`. No other class | as expected |
| L1-04 duplicates | byte-identical 0. Trajectory-identical 7 groups / 17 units (1,153 distinct fingerprints); 2 of the groups span pipeline dirs (PC-08). `_cross/l1-xdup.json`: 0 cross-corpus groups | CC-01 |
| L1-05 arms | 13 strata (pipeline_dir × suite × attack_dir × memory/plain), all counts as in prereg §3. Missing and extra cells as pre-registered (PC-10) | as expected |
| L1-06 secrets/paths | 0 of 1,163; auxiliary 0 | as expected |
| L1-07 timestamps | 0 pointers (v0.k11) | as expected |
| L1-08 degenerate | flags {} over 1,163; `error` null 1,163 | as expected |
| L1-09 | n/a | – |
| L1-10 | 6 context files screened, 0 hits, 0 operator | as expected |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`l2-sample-head.json`](data/craibench-agentdojo/l2-sample-head.json) (sha256 `a4d972af6528…`): 53 units, 13 strata (10 × 5 + 3 banking × 1), seed 20261011 |
| Import | 2 scratch corpora (`-j2`, `-j1`). 53/53 mapped (ok 32, ok_with_issues 21); 0 degenerate, 0 `adapter_defect`; 53 labels joined to 53 executions 1:1 |
| Validation | aer, sem, prov and linkage: 53/53 pass, 53 reproduced, linkage 100%. SHACL skipped (not implemented); regression n/a |
| Recompute | `--dry-run`: 53 identical, 0 unexplained |
| Verify chain | 0 failures; only `checksums.absent` (working tree) |
| Determinism | 225/225 files byte-identical; index identical |
| A2 codes | `map.accounting_unverifiable` 53, `map.earlier_attempts_unobservable` 53, `map.unattributed_additional_user_message` 21 (= the 21 sampled MI units) |
| A3 PROV | 0 issues over 17,999 statements and 30,613 relation arguments; 206 messages with generated_by; 122 model calls with input; 84 tool executions with call |
| Evidence classes | core D 244 come from engine rules only (`aprov.n_gap` 191, `aprov.n_capture_profile` 53). Agentdojo D rules are cited through `_unverified` twins only: twin 4,706, native 0, mixed 599 (inference I) |
| Identity | model `gpt-4o` 43 and `gpt-4o-mini-2024-07-18` 10; defence `spotlighting_with_delimiting` 43 and `_with_datamarking` 10; attack `important_instructions` 32 and none 21; 0 mismatches |
| Judgements | raw vs mapped equal on all 6 arms ([`os2-sample.json`](data/craibench-agentdojo/os2-sample.json)); 21 harness-default prepass judgements excluded from ASR |
| Redaction | 167 files, 0 hits |
| Withholding | no policy (inert) |

## 6. Outcome comparison

Level 1 is the population tally of the raw booleans, compared with v2 Secure. The gap rule is > 15 pp on n ≥ 20, or > 5 pp outside the Wilson 95% interval. Extra-injection logs are kept in the denominators, as `count_true_values.py` does. Full rows: [`os1-gap.json`](data/craibench-agentdojo/os1-gap.json).

| Arm (pipeline · suite · mode · class) | n | Metric | Rate (Wilson 95%) | Paper | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|
| gpt-4o delim · crypto · PI · multi | 384 | utility | 80.99 (311) [76.77, 84.60] | 63.28 (243) | +17.71 | **fires** (PC-01) |
| gpt-4o delim · crypto · PI · multi | 384 | ASR | 3.65 (14) [2.18, 6.03] | 21.88 (84) | −18.23 | **fires** (PC-01) |
| gpt-4o delim · crypto · MI · multi | 413 | utility | 36.32 (150) [31.83, 41.06] | 33.90 (140) | +2.42 | ok (count +10, PC-03) |
| gpt-4o delim · crypto · MI · multi | 413 | ASR | 74.33 (307) [69.91, 78.31] | 74.33 (307) | 0.00 | match |
| gpt-4o delim · chain · PI · multi | 50 | utility | 48.00 (24) [34.80, 61.49] | 26.00 (13) | +22.00 | **fires** (PC-02) |
| gpt-4o delim · chain · PI · multi | 50 | ASR | 34.00 (17) [22.44, 47.85] | 54.00 (27) | −20.00 | **fires** (PC-02) |
| gpt-4o delim · chain · MI · multi | 50 | utility | 0.00 (0) [0, 7.13] | 0.00 | 0.00 | match |
| gpt-4o delim · chain · MI · multi | 50 | ASR | 98.00 (49) [89.50, 99.65] | 90.00 (45) | +8.00 | ok (count +4, PC-02) |
| gpt-4o delim · chain · MI · single | 14 | utility / ASR | 7.14 (1) / 100 (14) | 7.14 / 100 | 0 / 0 | match |
| gpt-4o delim · crypto · MI · single | 80 | utility / ASR | 17.50 (14) / 55.00 (44) | 17.50 / 55.00 (T3 "DAO/NFT") | 0 / 0 | match |
| mini delim · crypto · MI · single | 80 | utility | 42.50 (34) [32.26, 53.43] | 42.50 | 0.00 | match |
| mini delim · crypto · MI · single | 80 | ASR | 87.50 (70) [78.50, 93.07] | 100.00 | −12.50 | **fires** (PC-03; all misses are inj 4) |
| mini delim · crypto · MI · multi | 40 | ASR | 60.00 (24) [44.60, 73.65] | 93.59 (of 390) | −33.59 | fires, not comparable (40 of 390 released; PC-10) |
| datamarking, banking, prepass | 1–19 | – | Wilson only ([`os1-population.json`](data/craibench-agentdojo/os1-population.json)) | none | – | – |

Investigation of the flagged gaps:

- Mapping is ruled out: the comparison uses raw booleans, and L2 raw equals mapped.
- Prompt condition does not explain the PI gaps. 375/384 crypto PI logs and 50/50 chain PI logs carry the Secure prompt, and no Default or Confirmation row matches both metrics.
- The paper's PI cells most plausibly come from unreleased runs (the `default_defended_es` directory in `count_true_values.py`). The cause is undetermined.
- The mini injection_task_4 gap coincides with crypto injection-task changes made after the runs (D-111).
- CC-07 (#181 and #161, AgentDojo checker defects): see PC-06. Banking ASR is 1/2 as logged and 0/2 re-scored.

Level 2: the 6 mapped arms pool suites and modes, so no paper-comparable cell exists. The only n ≥ 20 arm is gpt-4o delim II, with ASR 12/22 = 54.55% [34.66, 73.08]; it has no paper counterpart, so no verdict is given (R6).

## 7. Findings

| Id | Title | Class | Sev. | Verifier |
|---|---|---|---|---|
| PC-craibench-agentdojo-01 | Crypto PI multi: utility 311 and ASR 14 of 384, vs Secure 243 and 84; no T2 condition matches | documentation-mismatch (R3) | S2 | confirmed |
| PC-craibench-agentdojo-02 | Chain PI multi 24 / 17 of 50 vs 13 / 27; MI multi ASR 49 vs 45 | documentation-mismatch (R3) | S2 | confirmed |
| PC-craibench-agentdojo-03 | Count-level differences: crypto MI utility 150 vs 140; mini MI single ASR 70/80 vs 80/80 (inj 4: 6/16) | documentation-mismatch (R3) | S3 | confirmed |
| PC-craibench-agentdojo-04 | 27 extra-injection crypto logs with a Default-type prompt inside the Secure cells (MI 12, PI 9, prepass 6) | documentation-mismatch | S3 (was S2) | confirmed |
| PC-craibench-agentdojo-05 | PI wrapper and delimiter forms differ from the prereg premise (crypto 340 signed / 30 unsigned / 14 neither; chain unsigned; banking `<data>` 2/3) | documentation-mismatch (R4) | S3 | confirmed |
| PC-craibench-agentdojo-06 | [CC-07] #181 1 of 1 banking success, re-scored 0/2; #161 0/0 | expected-known (R2, CC-07; scope gap CC-09) | S3 | confirmed |
| PC-craibench-agentdojo-07 | [CC-09] no artefacts.toml scope; quirk counts verified | documentation-mismatch (CC-09) | S3 | confirmed |
| PC-craibench-agentdojo-08 | [CC-01] 2 cross-pipeline trajectory-identical pairs are distinct runs | analysis-artefact (R5) | S3 | confirmed |
| PC-craibench-agentdojo-09 | Profile `[source] paper = "none found"` vs arXiv 2503.16248 | documentation-mismatch (R4) | S3 | confirmed |
| PC-craibench-agentdojo-10 | Released subset of the v2 design; mini MI multi is 40 of 390 runs | documentation-mismatch (R3) | S3 | confirmed |

Proposed `artefacts.toml` entry (PC-04, text only):

- Id: `agentdojo.art.craibench_mixed_system_prompt`.
- Scope: profile `craibench-agentdojo`.
- Selector: prompt sha256 prefix `5d66eb347e` under `runs/gpt-4o-spotlighting_with_delimiting/crypto_trading/**`.
- Count: 27 logs (6 prepass, 9 PI, 12 MI; injection ids 5..9 and 11).
- Effect: these logs ran under a Default-type prompt within the Secure condition. The entry is for disclosure only.

Verifier (2026-10-21):

- All 8 exam scripts were re-run at the pin. Each output is byte-identical to the committed JSON.
- The v2 Table 2 values were re-read from arXiv html: Trading Secure PI 243 / 21.87% / 390, MI 140 / 74.33%; Chain Secure PI 13 / 54%, MI 0 / 90%. 21.87% = 84/384, truncated. The printed utility 243 over the printed Total 390 is 62.31%, not 63.28%. The gap still fires (+18.68 pp).
- No other Table 2 row (Default, Confirmation, or GPT-4o-mini) matches the PI cells.
- #181: confirmed in the vendored v1 banking `injection_tasks.py` at the pin (`service or "" in subject`).
- PC-04 is lowered to S3. All 27 logs are extra injection ids outside the paper design, and they move no reported rate by more than 0.51 pp.
- PC-03 cause is still undetermined. The crypto `injection_tasks.py` blobs at `dc1a1a73` and `ac6c9490` are absent from the partial clone (not fetched).

AGENTS.md §12 item: CrAIBench's released PI logs do not reproduce arXiv 2503.16248v2 T2 Secure PI (crypto ASR 3.65% vs 21.88%; chain 34% vs 54%), while the MI cells do.

Security: no security findings. L1-06 is 0, L1-10 is 0, and redaction is 0.

## 8. Recommendations and readiness

- **Readiness: `ready-with-caveats`.** The mapping is clean, deterministic and identity-correct (H15), and has no security hits. The caveats are disclosures about the source:
  - The PI cells do not reproduce the paper (PC-01, PC-02).
  - 27 logs carry a Default-type prompt (PC-04, S3 after verification).
  - #181 applies to 1 banking success (PC-06).
- Report the logged outcomes. Exclude nothing, neither the PI cells nor any zero-success arm.
- Owners:
  - Family owner: add the scope for `validity_defects` (#181 1/1, #161 0/0) and the PC-04 entry. Check the `spotlighting_delimiters` wording for the 3 banking logs.
  - Profile owner: record the paper as v2 (PC-09).
- Verifier follow-ups: done (2026-10-21). The PC-03 diff is not possible offline because the `dc1a1a73` blob `5de46c89` is absent. It needs a blob fetch, which is a follow-up for the owner, not run here.

## 9. Reproduction

```bash
cd <worktree>
S=docs/reports/precheck/data/craibench-agentdojo/exam-scripts
uv run python -I $S/pop.py   > docs/reports/precheck/data/craibench-agentdojo/os1-population.json
uv run python -I $S/gap.py   > docs/reports/precheck/data/craibench-agentdojo/os1-gap.json
uv run python -I $S/os2.py   > docs/reports/precheck/data/craibench-agentdojo/os2-sample.json
uv run python -I $S/inv.py   > docs/reports/precheck/data/craibench-agentdojo/raw-census.json
uv run python -I $S/inv2.py  > docs/reports/precheck/data/craibench-agentdojo/raw-census-2.json
uv run python -I $S/inv3.py  > docs/reports/precheck/data/craibench-agentdojo/raw-census-3.json
uv run python -I $S/cc07.py  > docs/reports/precheck/data/craibench-agentdojo/cc07.json
uv run python -I $S/xpipe.py > docs/reports/precheck/data/craibench-agentdojo/xpipe.json
# L1/L2 mechanical steps: tools/precheck/run_batch.py --plan tools/precheck/plans/wave3.toml (already run, rc 0)
```

The scripts read the staged bare clone at `~/.agentprov/staging/10c/craibench/CrAIBench.git`, pin `e41eac1e`, with git blob SHA-1 checked and parsed through `agentprov.ingest`. They never fetch.
