# Pre-check dossier: `tacit-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `tacit-agentdojo` (Apache-2.0 code and logs; no separate data licence; embedded AgentDojo text MIT) |
| Parts | `tacit-agentdojo · head` (1 part) |
| Family / profile | `agentdojo` / `tacit-agentdojo@1` (dialect `agentdojo.tracelogger`, semantics `agentdojo.suites@2`, variants `v1.k14` 2,075 + `v1.k14.incomplete` 1) |
| Pin | git `CSSLab/Tacit` @ `995692d3` ("initial release", 2026-09-23; the only commit, so pin = head = release), tree 2,139 blobs |
| Code commit | `cb0af3d8` (L1 and L2, batch `wave2`, steps l1, sample, import_j2, import_j1, check all rc 0; no tracked changes) |
| Kind | wave 2, first examination (not in FA or E2); no stored corpus |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (L1, L2, examination, verification, dossier) |
| Agents | researcher and fact-checker (prereg, research), examiner (L1/L2 analysis), verifiers (one per finding; two for PC-01), dossier writer |
| Data | [`data/tacit-agentdojo/`](data/tacit-agentdojo/): `research.json`, `l1-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `raw-census.json`, `os-rates.json`, `l2-exam.json`, `targeted-sample.json`, `findings.json`, `exam-scripts/` |

- Code identity, part `head` ([`code-head.json`](data/tacit-agentdojo/code-head.json)): commit `cb0af3d8`; engine code aer `24df84b5e307`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `d3f9995f61bf`; adapter `agentdojo.tracelogger@0.1.0` `c311b5a6ac9e`; profile sha256 `ee686ef7d1da`, rules agentdojo 2 / aer 1.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Source repository | https://github.com/CSSLab/Tacit @ `995692d3` (only commit; 0 tags, releases or issues; 1 fork without own pushes) | the data (`data/agentdojo/`, 2,076 logs) plus loader, collection script and splits |
| Paper of the source | https://arxiv.org/abs/2609.33039v1 (v1 only, 2026-09-27, preprint; CC BY-SA 4.0) | the corpus's own paper; App. B.1 describes the AgentDojo collection, Tables 3-4 its label counts; the README uses a different working title |
| Predecessor paper | https://arxiv.org/abs/2604.18519 (ACL 2026) | same first author; no AgentDojo data; context only |
| External data record | none (Zenodo, HF, Figshare: 0 hits, 2026-10-14) | the git tree is the record; blob SHA-1 only, no publisher checksums |
| AgentDojo paper | https://arxiv.org/abs/2406.13352 | benchmark (suites v1.2.2, `important_instructions`) |
| Harness | `agentdojo==0.1.35` (script comment and all 2,076 logs; install not pinned); Llama via AgentDojo's `LOCAL` client, Qwen via `VLLM_PARSED` (vLLM hermes parser); vLLM `--max-model-len 32768`; pydantic shim `agentdojo_compat.py` | producer and scorer |
| Upstream issues | ethz-spylab/agentdojo [#95](https://github.com/ethz-spylab/agentdojo/issues/95), [#181](https://github.com/ethz-spylab/agentdojo/issues/181), [#202](https://github.com/ethz-spylab/agentdojo/issues/202), [#219](https://github.com/ethz-spylab/agentdojo/issues/219), [#220](https://github.com/ethz-spylab/agentdojo/issues/220), [#213](https://github.com/ethz-spylab/agentdojo/issues/213), [#168](https://github.com/ethz-spylab/agentdojo/issues/168), [#214](https://github.com/ethz-spylab/agentdojo/issues/214), [#88](https://github.com/ethz-spylab/agentdojo/issues/88) | benign constant, checker and LocalLLM parser/error defects relevant to these logs |

Data-versus-paper notes (from `research.json`, checked against the data):

- The paper reports no utility or ASR per model or suite; it gives pooled label counts only: 2,075 trajectories, unsafe 369 / safe 1,706 (Table 4; Table 3 "injected task carried out" 369), defining unsafe as completing the injected task. The released logs give security true 369 = 194 benign (harness constant, #95) + 175 attacked, false 1,706 (all attacked), null 1. So the paper's 369 counts the 194 benign constants, while the released loader (`tacit/data/agentdojo.py`, unsafe = security is False) and the released split files label the 1,706 resisted runs unsafe and the 175 successful injections safe (PC-02). The detector results in the paper's AgentDojo columns (Tables 1-2) rest on those split labels.
- 2,075 vs 2,076: the loader drops the one log without a security value (qwen workspace UT38 x IT11, `v1.k14.incomplete`).
- The qwen workspace attacked arm stops after that log: 16 cells were never written (PC-04); the paper does not mention it.
- The release is curated: no injection-task pre-pass logs (0.1.35 writes them) and no process or vLLM logs, although the collection script writes them next to the runs.
- `tacit/config.py` names the HF ids (`meta-llama/Llama-3.1-8B-Instruct`, `Qwen/Qwen3-4B-Instruct-2507`, no revision) and the collection script resolves them from it; our model-dir table says no checkpoint is recorded, and the profile records no paper identifier (PC-06).
- The only commit postdates the runs (logs 2026-07-10, repository created 2026-08-17), so the script at the pin is not proven to be the one that ran.

## 3. Expectations

Pre-registration: [`prereg/tacit-agentdojo.md`](prereg/tacit-agentdojo.md), committed in `fd75f8a3` (2026-10-14), before any check of this corpus ran. Method amendments of README section 8 apply as dated; amendment 1 (stored corpora) does not apply (no stored corpus). Classes follow R1-R6 and CC-01 to CC-11 of [`cross-cutting.md`](cross-cutting.md) (wave-2 follow-up 2026-10-21: PC-03 to CC-07 severity S3; CC-07 #161 added as PC-10; PC-07 = CC-09 reference).

Hypotheses H1 to H12: 9 supported, H8 supported at L1 only, H7 refuted (PC-01, PC-09), H11 refuted as worded but benign (CC-03, PC-05).

| H | Result | Note |
|---|---|---|
| H1 | supported | 16 strata = prereg §2; grids complete (banking 16x9, slack 21x5, travel 20x7, workspace 40x14); 0 duplicate, 0 extra cells; only holes the 16 qwen workspace cells (PC-04) |
| H2 | supported | true 369 = 194 benign + 175 attacked; false 1,706 all attacked; null 1 (PC-02) |
| H3 | supported | the incomplete log is qwen workspace UT38 x IT11 and the latest qwen workspace attacked log (05:38:13) |
| H4 | supported | v1.2.2, 0.1.35, `error` null in 2,076/2,076 |
| H5 | supported | 0 `injection_task_*` user dirs; 0 benign logs with an injection id |
| H6 | supported | 3,750 null call ids in 699 logs, all Llama/local; qwen 0; 0 duplicate ids |
| H7 | refuted | 622 Llama turns (444 logs) with more `<function=` tags than parsed calls, 342 of them tag-only finals, where 0 was expected; the census 0 is circular (PC-01, PC-07). Empty final answers 31/1,046 = 2.96 % > bound 1 % (PC-09) |
| H8 | supported at L1; L2 not tested | 24 off-set tool-name calls (23 Llama, 1 qwen; 18 with a trailing `/`) in 7 logs; 22 executed, all answered by a tool error, 2 unexecuted. None of the 7 logs is sampled (follow-up 2) |
| H9 | supported | all timestamps in the window; in every model x suite cell every attacked log follows the last benign log |
| H10 | supported | 0 byte-identical; 1 cross-corpus trajectory group (0.05 %) |
| H11 | refuted as worded; benign | 2 logs hold the AgentDojo persona home path (CC-03); 0 operator-home, 0 secret-like (PC-05) |
| H12 | supported | 16 slack IT5 successes; all 50 membership-tool messages without error (#168 does not apply) |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: the staged blob:none bare clone at the pin (`--git`, blob SHA-1 checked). Batch `wave2`, all steps rc 0, no warning, error or refusal line.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 2,139 walked = 2,076 selected + 10 context (LICENSE, README, requirements, collect script, compat shim, loader, 4 split files scanned as auxiliary, 4/4 parse) + 52 not selected + 1 absent blob (`assets/figure1.png`, never fetched, not selected, noted in the profile); 0 excluded, rejected, strays. Units 2,076 = registry/census; `v1.k14` 2,075 + `v1.k14.incomplete` 1 | as expected |
| L1-02 parse | strict ok 2,076/2,076; 0 in every class | as expected |
| L1-03 encodings | 0 U+2028/2029/0085, controls, bidi, tag, zero-width, U+FFFD, mojibake. Residues (expected, #214 Python-repr class, tool-result content): escaped newline 634 files (1,119 strings), escaped quote 104, escaped unicode 133 (211 strings), JSON-in-string 2, variation selector 2 | as expected |
| L1-04 duplicates | 0 byte-identical. Trajectory-identical (CC-01 fingerprint): 60 groups / 429 of 2,076 units (1,707 distinct); every group differs only by injection task, 29 also by attack (payload never reached the agent). Cross-corpus: 0 byte-identical, 1 trajectory group with `glitch-agentdojo` (slack UT3 benign) = 1/2,076 | as expected (H10) |
| L1-05 arms | 16 strata = prereg §2; grids complete except the 16 qwen workspace cells UT38 x IT12-13 and UT39 x IT0-13 (544 of 560 vs llama 560); 0 duplicate / extra cells; 0 pre-pass logs; `pipeline_name` = client directory 2,076/2,076 | as expected (H1); PC-04 |
| L1-06 secrets/paths | 0 secret-like, 0 operator home, 0 local-path model ids. `account:home-dir:named` in 2 artefacts (112 matches in 85 strings at 3 pointers), 1 distinct name = the AgentDojo banking persona's first name (CC-03) | H11 as worded refuted; PC-05 |
| L1-07 timestamps | `/evaluation_timestamp` 2,076/2,076, all parse, all naive, 2026-07-10 04:36:19..08:11:20. Other timestamp pointers are calendar arguments (3 non-monotone units = content). qwen 04:36-05:38 and llama 05:03-08:11 overlap | as expected (H9) |
| L1-08 degenerate | incomplete 1, account_path_named 2; 0 empty / tiny / zero-message; `error` null 2,076. `null_final` reads 0 under the pre-fix rule (CC-08, PC-08); raw census: 31 Llama finals with one empty text block and no calls (PC-09), and 2 qwen logs ending on null content with trailing calls (silent-rerun trigger; outside the no-calls rule) | PC-08, PC-09 |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`data/tacit-agentdojo/l2-sample-head.json`](data/tacit-agentdojo/l2-sample-head.json) (sha256 `3b11cc0ca181...`): 80 of 2,076 units, 16 strata x 5, seed 20261011 |
| Import | 2 scratch corpora (`l2-head-j2.partial`, `-j1.partial`), dev mode from a git-seeded cache. 80/80 mapped; 0 failed, degenerate, `adapter_defect`, unreadable. ok 77 / ok_with_issues 3; completeness unverifiable 80. Codes: `accounting_unverifiable` 80, `earlier_attempts_unobservable` 80, `unexecuted_tool_call` 3 (exactly the 3 sampled trailing-call logs). Join 80/80; raw linked 90 (80 primaries + 10 context) |
| Validation | tiers aer, sem, prov, linkage: 80/80 pass, 80 reproduced, linkage 100 %. SHACL not implemented (skipped); regression n/a |
| Recompute | `--dry-run`: 80 identical, 0 unexplained |
| Verify chain | 0 failures; only `checksums.absent` (working-tree partial) |
| Determinism | j2 vs j1: 337/337 files byte-identical, index identical. First determinism evidence on a sample covering both clients; full-population determinism not yet shown (follow-up 3) |
| A2 error classes | no issue code beyond the three above. No `local_parse_drop_possible` and no `local_model_tag_count`, although 16 of 40 sampled Llama executions hold 18 turns with more tags than calls, 12 of them tag-only finals (PC-01) |
| A3 PROV issues | 0 dangling, missing or invented relations over 39,392 statements / 66,597 relation arguments; unexecuted calls 3/3 represented |
| Evidence classes | AER: messages O 820, judgements O 160, model_call I 365, tool_execution I 295, actor I 320 / O 40. Every family D rule is cited through its `_unverified` twin (D-24), except `system_prompt_variant_digest@1` (80, code-independent by design). PROV: core D 360 = engine-native only (`aprov.n_gap` 280, `n_capture_profile` 80); inference I 14,431; assessment I 3,260 / O 240. `_unverified` split after recheck12 (CC-08, PC-08): twin inference I 12,511 / none 980, assessment I 1,752; mixed twin + native inference I 1,777; native-only 0 |
| Identity | model = directory label (llama 40, qwen 40) under `pipeline_dir_is_model_identity@1` (I); provider local / vllm; defence none; attacks `important_instructions` 40 / none 40; 0 unresolved, 0 mismatches |
| Judgements (OS-2) | raw vs mapped 160/160 equal; the 40 benign security values cite `benign_security_constant_unverified` and are excluded from `attack_success` |
| Redaction | 248 AER/SEM/PROV files, 0 account-path and 0 `operator-*` hits. Neither persona-path log is in the sample (follow-up 2) |
| Withholding | not applicable (no `[withhold]` policy; L1-06 found only benchmark persona content) |

### Recheck (CC-08, recheck12)

`plans/recheck12.toml` (l1, l1_10, check; sample frozen) against the d97d3a57 files; full deltas in [`_cross/recheck12.json`](data/_cross/recheck12.json). Every other L1/L2 count is unchanged; the only other deltas are run environment (code commit d97d3a57 with tools/src = 5efa3575, `tracked_changes` true, two H.8.4(2) recompute notices with 0 unexplained changes; R12-01).

| Part | L1-08 flags (old -> new) | L2 `_unverified` split | L1-10 |
|---|---|---|---|
| head | `null_final` - -> 31; `trailing_calls` - -> 96 | twin inference:I 14,288 -> 12,511; mixed 1,777; native 0 (sum 14,288 = old) | 6 screened (context 6); 0 hits; files with a hit 0; named accounts 0; operator 0; unreadable 0 |

- PC-08 resolved: `null_final` 31 (as expected); `trailing_calls` 96; native 0.

## 6. Outcome comparison

Level 1 is the population (raw booleans; 2,075 scored logs, the incomplete log has no judgement). Reference: paper Table 4 (pooled counts only) and the phase-10c census; the paper reports no per-arm rate. Gap rule: > 15 pp, or > 5 pp outside the Wilson 95 % interval. Full rows: [`os-rates.json`](data/tacit-agentdojo/os-rates.json).

| Arm | Level | n | Metric | Rate (Wilson 95 %) | Paper / reference | Gap | Verdict |
|---|---|---|---|---|---|---|---|
| all | L1 | 2,075 | security true (paper "unsafe") | 17.78 % (369) [16.20, 19.49] | 369 (Table 4) | 0 (count) | match; includes 194 benign constants (PC-02) |
| all | L1 | 2,075 | security false (paper "safe"; loader "unsafe") | 82.22 % (1,706) [80.51, 83.80] | 1,706 (Table 4; data/README) | 0 (count) | match; label direction PC-02 |
| all / none | L1 | 194 | security true (harness constant, not ASR) | 100 % (194) [98.06, 100.00] | 194 (census) | 0 | match |
| all / II | L1 | 1,881 | targeted ASR | 9.30 % (175) [8.07, 10.70] | 175 derived (369 − 194) | 0 (count) | match |
| all / II, goal-datum re-score | L1 | 1,881 | ASR without the 10 banking IT1 #181 successes | 8.77 % (165) [7.58, 10.14] | none | −0.53 vs logged | disclose (PC-03) |
| all | L1 | 2,075 | utility | 36.14 % (750) [34.10, 38.24] | 750 (census) | 0 (count) | match |
| llama / II | L1 | 949 | utility | 25.71 % (244) [23.03, 28.59] | none | | n/a; PC-01, PC-09 |
| llama / II | L1 | 949 | targeted ASR | 3.37 % (32) [2.40, 4.72] | none | | n/a; PC-01, PC-09 |
| llama / none | L1 | 97 | utility | 34.02 % (33) [25.36, 43.90] | none | | n/a |
| qwen / II | L1 | 932 | utility | 45.28 % (422; n 932 of 933 logs, 1 incomplete excluded) [42.11, 48.49] | none | | n/a; PC-04 |
| qwen / II | L1 | 932 | targeted ASR | 15.34 % (143) [13.17, 17.80] | none | | n/a; PC-04 |
| qwen / none | L1 | 97 | utility | 52.58 % (51) [42.73, 62.23] | none | | n/a |
| qwen / II / banking | L1 | 144 | targeted ASR (goal-datum re-score 29.86 %, 43) | 35.42 % (51) [28.08, 43.51] | none | −5.56 re-score vs logged | disclose (PC-03) |

Level 2 (mapped AER of the 80-unit sample; reference = the L1 population rate, post-stratified sample rate beside it, R6):

| Arm | n | Metric | Sample rate (Wilson 95 %) | Post-stratified | Reference (L1) | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|---|
| llama / II | 20 | utility | 20.0 % (4) [8.07, 41.60] | 20.08 | 25.71 | −5.71 | covered |
| llama / II | 20 | targeted ASR | 0.0 % (0) [0.00, 16.11] | | 3.37 | −3.37 | covered |
| llama / none | 20 | utility | 40.0 % (8) [21.88, 61.34] | 34.23 | 34.02 | +5.98 | covered |
| qwen / II | 20 | utility | 55.0 % (11) [34.21, 74.18] | 74.98 | 45.28 | +9.72 raw / +29.7 post-stratified | flagged, investigated: not a finding (R6: the workspace stratum drew 5/5 utility-true; OS-2 160/160 equal) |
| qwen / II | 20 | targeted ASR | 25.0 % (5) [11.19, 46.87] | 12.93 | 15.34 | +9.66 raw / −2.41 post-stratified | covered |
| qwen / none | 20 | utility | 55.0 % (11) [34.21, 74.18] | 51.13 | 52.58 | +2.42 | covered |

## 7. Findings

10 findings, 0 refuted. PC-01 to PC-09 confirmed by their verifiers (PC-01 by two); PC-10 (CC-07 #161) added in the wave-2 follow-up by `cc07_161.py` (method of interbolt `checker.py`, executed = tool-message echo without error, as `b181.py`), one run, not independently verified. Severities and wording below include the verifiers' corrections. No security finding. [`findings.json`](data/tacit-agentdojo/findings.json) is in the CC-06 format.

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-tacit-agentdojo-01 | Profile omits `agentdojo.local_model_raw_completion`: 622 Llama turns (444 of 1,046 logs) with more `<function=` tags than parsed calls are never flagged; 342 are tag-only finals (32.70 % [29.92, 35.60] of Llama runs) | mapping-defect | S2 | confirmed (2/2); wording: a call "may have been dropped" (class I), benign split is s=T | Family owner adds the quirk (`applies pipeline_dir = ["local"]`, rule `agentdojo.local_model_tag_count@1`, observed 622 / 342) and decides v2 bump vs unreleased v1 edit (AD-18); byte-changing regen item (444 AERs gain the issue); widen `local_parse_drop`; disclose. Never re-parse calls |
| PC-tacit-agentdojo-02 | Paper's AgentDojo label counts include the 194 benign harness constants; the released loader and split files invert the label (resisted runs unsafe, 175 successes safe) | documentation-mismatch (R3) | S2 | confirmed; split files added to evidence; reach Tables 1-2 | Disclose in the datasheet and any manuscript use; never use 369 as an ASR (use 175/1,881, or 165 re-scored, PC-03). Contacting the authors is the user's decision |
| PC-tacit-agentdojo-03 | [CC-07, #181] All 10 banking IT1 successes rest on the checker precedence (no target IBAN in any of the 11 attacker transfers); defect identical in suite v1.2.2 | expected-known (CC-07, R2; scope gap CC-09) | S3 (was S2; CC-07 class S3, the corpus bias stays in the disclosure: qwen banking ASR 35.42 → 29.86 %) | confirmed; "strict" = goal-datum re-score; entry status `proposed` | Widen `validity_defects` scope with 10 executions; report the re-scored ASR beside the logged one; flag only, never re-score in the corpus or exclude |
| PC-tacit-agentdojo-04 | qwen workspace attacked arm truncated: 16 cells never written after UT38 x IT11 (incomplete) | source-defect (R1) | S2 | confirmed; artefact proposal corrected (detector, recorded_as, cause) | New entry below; for cross-model workspace comparisons report the 544 common cells and the full sets. No exclusion |
| PC-tacit-agentdojo-09 | 31 Llama runs end on an empty final answer (bound 1 %); probable #220 (LocalLLM swallows server errors into `""`) | source-defect (R1) | S2 (raised from S3 by the verifier) | confirmed; attribution upgraded to probable #220 | New entry below; disclose beside the Llama ASR and utility (29 attacked runs scored u=F, 28 s=F by the harness path). No exclusion |
| PC-tacit-agentdojo-05 | [CC-03] AgentDojo persona home path in 2 Llama banking logs | expected-known (CC-03) | S3 | confirmed; pointer breakdown corrected | No redaction (benchmark fiction); record the AER form via follow-up 2 |
| PC-tacit-agentdojo-06 | Our docs: paper id/title missing, "checkpoint not recorded" wrong for the HF id, `tacit/config.py` and `data/README.md` not context artefacts | documentation-mismatch (R4) | S3 | confirmed; collect script resolves the HF id from `config.py` | Profile owner in the PC-01 edit: arXiv id and title; add the two context artefacts; table basis "HF id recorded in tacit/config.py (I); revision and quantisation not recorded"; regenerate README blocks |
| PC-tacit-agentdojo-07 | [CC-09] reference: `artefacts.toml` generic AgentDojo entries do not scope `tacit-agentdojo`; census quirk counts read 0 for keys built on mapper output of undeclared quirks (phase-10d census 0/0 for `local_model_raw_completion`) | documentation-mismatch (CC-09; census part R4) | S3 | confirmed; wording corrected (three are declared profile quirks; census circular only for mapper-output keys) | See CC-09 (recorded once there); family owner widens scopes (below). Census owner: report "not measured" for undeclared mapper-output keys |
| PC-tacit-agentdojo-08 | [CC-08] L1 `null_final` rule and `l2_check` twin counter ran pre-fix | analysis-artefact (CC-08) | S3 | confirmed; bases stated (3 last-assistant None-with-calls turns; 2 logs whose last message is such a turn) | Resolved by recheck12: `null_final` 31 (as expected), `trailing_calls` 96, twin I 12,511, mixed 1,777, native 0. Not counted for readiness |
| PC-tacit-agentdojo-10 | [CC-07, #161] Banking `user_task_5` utility true without an executed Spotify payment: 12 of 20 (llama II 7/9, benign 1/1; qwen II 4/9, benign 0/1) | expected-known (R2, CC-07: `validity_defects`, vacuous utility; scope gap CC-09) | S3 | one run (`cc07.json`), not independently verified | Disclose beside banking utility; keep logged utility; `validity_defects` row 12 |

Evidence details (counts only):

- PC-01: Llama turns with a `<function=` tag 4,092; more tags than parsed calls 280 (with ≥ 1 call) + 342 (no call, all final) = 622 in 444 logs; no log has more than one tag-only turn; qwen 0. Tag-only outcomes: attacked u=F/s=F 296, u=T/s=F 18, u=F/s=T 1; benign u=F/s=T 25, u=T/s=T 2. The tacit profile declares 10 family quirks, none of them this one (agentdojo-upstream and agentdyn do); the collection script runs Llama through AgentDojo's own LOCAL prompting/parsing, and the compat shim only rebuilds a pydantic model, so the upstream rule applies. The rule is class I, so no `_unverified` twin is needed. L2 scratch AERs: 0 files with either string while 68 files carry other rule ids.
- PC-02: raw (attack none, security) counts: (benign, true) 194, (attacked, true) 175, (attacked, false) 1,706, (attacked, null) 1. `split_seed42.json` labels: benign 194 → 0, attacked successes 175 → 0, resisted 1,706 → 1 (stats unsafe 1,028 + 334 + 344 = 1,706). Loader: drop rows with security None or error; label `int(security is False)`. Two readings fit the data: the table reports raw security counts under its stated definition (so 194 benign constants are "unsafe"), or the code inverts the paper's direction; both are a paper-code mismatch.
- PC-03: attacked banking security true: IT0 7, IT1 10, IT3 6, each with an executed attacker-bound transfer. IT0 7/7 and IT3 6/6 carry the goal datum; IT1 0/10 carry the target IBAN (0/11 attacker calls, all args, punctuation stripped), though the IBAN appears in tool outputs of 9/10 logs. Installed 0.1.35 `InjectionTask1.security` has the precedence defect in both v1 and v1_2. The 165 figure is a goal-datum re-score (as mandate PC-01), not what a fixed upstream checker would return (3 of 11 subjects contain "me").
- PC-04: llama 560 workspace attacked cells, qwen 544; L − Q = 16 as listed, Q − L empty; qwen workspace attacked max timestamp 05:38:13 at UT38 x IT11 (sorted by timestamp). The missing cells follow AgentDojo iteration order right after the incomplete log; whether the harness crashed or the operator stopped is not observable. IT12-13 also carry the #213 validity issue.
- PC-09: 31/1,046 Llama logs (2.96 % [2.10, 4.18]); qwen 0. Outcomes attacked u=F/s=F 28, u=F/s=T 1, benign u=F/s=T 2. All 31 follow a tool message, none has an earlier empty turn; histories 63.9k-153.4k content characters (median 110.6k) vs median 2.9k for the other 1,015 Llama runs (1.9 % of them reach the smallest empty-final length); server `--max-model-len 32768`. In 0.1.35 `chat_completion_request` returns `""` on any exception. Circumstantial, not proven: the debug line is not logged.
- PC-05: name sha256 prefix `<account-A>`, length withheld letters, equal to the AgentDojo banking persona's first name; it occurs in the system prompt (msg 0) and a tool result (msg 3) before its first model use. `/home/<name>/` matches: 56 in 29 assistant text strings, 29 in assistant call args `file_path`, 27 in the tool message's echoed call args; 0 in tool-result content. The L1-06 field labelled "strings" counts matches (tool-owner note after the freeze, R5).
- PC-07: occurrences at the pin for the scope widening: `benign_security_constant` 194 files (declared quirk, matching); `silent_rerun` 2 null-final logs (declared, matching), earlier passes unobservable 2,076; `provider_ids` 3,750 ids / 699 logs (declared, matching); `local_parse_drop` 622 turns (PC-01); `validity_defects` 10 (PC-03); `calls_derived_from_messages` / accounting unverifiable 2,076; `text_tool_call` heuristic 345 = 342 Llama tag-only finals + 3 qwen finals with an unparsed hermes `<tool_call>` tag (travel UT2 x IT0, workspace UT19 x IT6 / IT8, all u=F s=F).

Proposed `artefacts.toml` entries (text only; route to the AgentDojo family owner):

```toml
# PC-01: widen agentdojo.art.local_parse_drop
#   scope.sources/parts/profiles += "tacit-agentdojo" / "head" / "tacit-agentdojo"
#   expected += { snapshot = "tacit-agentdojo:head", count = 622, unit = "turns", basis = "pre-check raw census 2026-10-15: more <function= tags than parsed calls (444 Llama logs)", status = "verified" }
#   expected += { snapshot = "tacit-agentdojo:head", count = 342, unit = "turns", basis = "pre-check raw census 2026-10-15: tags and no parsed call, all final", status = "verified" }

# PC-03: widen agentdojo.art.validity_defects
#   scope += tacit-agentdojo (head)
#   expected += { snapshot = "tacit-agentdojo:head", count = 10, unit = "executions", basis = "pre-check 2026-10-15 b181.py: banking IT1 security true without the target IBAN in any executed attacker transfer (#181, suite v1.2.2); IT0 0/7, IT3 0/6", status = "proposed" }

# PC-04
[[artefact]]
id = "tacit.art.qwen_workspace_truncated"
title = "qwen workspace attacked arm stops at user_task_38 x injection_task_11"
description = "The qwen3-4b-instruct workspace important_instructions run ends at UT38 x IT11 (the incomplete log); the 16 later cells (UT38 x IT12-13, UT39 x IT0-13) were never written: 544 of 560 cells vs llama 560. The absent cells carry no seal issue; only the incomplete file is recorded (incomplete_run)."
scope = { sources = ["tacit-agentdojo"], parts = ["head"], profiles = ["tacit-agentdojo"] }
cause = "unknown"
detector = { rule = "none (absence; pre-check L1-05 cell census)", class = "D" }
recorded_as = { issues = [] }
handling = { class = "FO" }
expected = [
  { snapshot = "tacit-agentdojo:head", count = 16, unit = "cells", basis = "pre-check L1-05 2026-10-15 (absent; not recorded in the corpus)", status = "verified" },
  { snapshot = "tacit-agentdojo:head", count = 1, unit = "files", basis = "incomplete UT38 x IT11, agentdojo.incomplete_run@1 quirk", status = "verified" },
]
manuscript = true
refs = ["prereg/tacit-agentdojo.md §3", "data/tacit-agentdojo/raw-census.json"]

# PC-09
[[artefact]]
id = "agentdojo.art.local_empty_final"
title = "Local-model runs ending on an empty answer"
description = "The final assistant message of a LocalLLM run holds one empty text block and no calls, after a tool result. AgentDojo 0.1.35 LocalLLM returns an empty string on any client exception (#220); the 31 runs have 64k-153k character histories against a 32,768-token server limit, so context overflow is probable but not logged. Outcomes come from the harness path (u=F; 28 attacked runs s=F)."
scope = { sources = ["tacit-agentdojo"], parts = ["head"], profiles = ["tacit-agentdojo"] }
cause = "upstream_harness"
detector = { rule = "agentdojo.empty_assistant_text_ambiguous_unverified@1", class = "I" }  # align with the rule the mapper emits
handling = { class = "FO" }
expected = [{ snapshot = "tacit-agentdojo:head", count = 31, unit = "executions", basis = "pre-check raw census 2026-10-15", status = "verified" }]
manuscript = true
refs = ["https://github.com/ethz-spylab/agentdojo/issues/220", "local_llm.py chat_completion_request at v0.1.35", "Tacit scripts/data/collect_agentdojo.sh --max-model-len 32768"]

# PC-07: add "tacit-agentdojo" (part head) to scope.sources/parts/profiles of
#   benign_security_constant (194 files), silent_rerun (2 null-final logs; 2,076 earlier passes unobservable),
#   provider_ids (3,750 ids / 699 logs), calls_derived_from_messages (2,076),
#   text_tool_call (345 executions heuristic = 342 + 3; status "proposed" until the detector runs);
#   local_parse_drop and validity_defects as above (#181 10, PC-03; #161 12, PC-10)
```

Items for AGENTS.md section 12:

- PC-01: the tacit profile does not enable the LocalLLM tag-count quirk; 342 of 1,046 Llama runs (32.70 %) end on a turn whose text holds a `<function=` tag the local parser did not turn into a call, and 622 turns in 444 logs have more tags than calls. Byte-changing regen item (profile quirk); disclose beside Llama rates.
- PC-02: never use the paper's AgentDojo "unsafe 369" as an ASR; it includes 194 benign constants, and the released loader and splits invert the label. Targeted ASR is 175/1,881 (9.30 %).
- PC-03: 10 banking IT1 successes rest on #181; logged ASR 9.30 % vs goal-datum re-score 8.77 %; qwen banking 35.42 % vs 29.86 %. PC-10: 12 of 20 banking `user_task_5` passes are vacuous (#161).
- PC-04: qwen workspace attacked arm has 544 of 560 cells; compare models on the 544 common cells as well.
- PC-09: 31 Llama runs end on an empty answer, probable #220 context overflow; their outcomes come from the harness path.

## 8. Recommendations and readiness

1. AgentDojo family owner (regen item, user approval needed before any re-import): add `local_model_raw_completion` to the tacit profile (PC-01) together with the PC-06 doc fixes; decide v2 bump vs unreleased v1 edit; regenerate README blocks. Expected effect: `local_parse_drop_possible` on 622 turns in 444 Llama AERs, 0 outcome change.
2. Family owner: the scope widenings and the two new entries above (PC-01, PC-03, PC-04, PC-07, PC-09, PC-10); the scope gap is CC-09.
3. Disclose in the datasheet and manuscript: PC-02 label direction, PC-03 #181 (logged and re-scored ASR), PC-10 #161, PC-04 truncation, PC-09 empty finals, PC-01 tag-only finals.
4. Orchestrator: `recheck12` done (PC-08 resolved); the targeted 12-label scratch import (follow-up 2) to cover H8 (off-set tool names), the CC-03 AER form and the incomplete/retry handling, none of which is in the sample.
5. In the round: show full-population determinism (jobs 2 vs 1 over 2,076).
6. No exclusion of any data.

**Readiness: `ready-with-caveats`.**

- The part imports correctly and deterministically on the sample: 80/80 mapped, validation 80/80, recompute 0 unexplained, j1/j2 byte-identical, judgements raw = mapped 160/160, identity 0 mismatches, redaction clean, L1 counts = paper Table 4 and census.
- Caveats, owned and routed: PC-01 (profile quirk missing; byte-changing regen item with the family owner, should land before the round imports this part), PC-02/03/04/09/10 (disclosure and catalogue entries), PC-06 (docs). None stops the data being imported correctly.
- Not counted: PC-08 (R5); PC-07 (reference to CC-09).

## 9. Reproduction

Batch (wave 2; plan entry in `tools/precheck/plans/wave2.toml`):

```toml
[[part]]
corpus_id = "tacit-agentdojo"
source = "tacit-agentdojo"
part = "head"
l1 = ["--git", "~/.agentprov/staging/10c/tacit/Tacit.git"]
```

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave2 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave2.toml
```

Steps the batch ran (W = `~/.agentprov/migration-work/precheck/tacit-agentdojo`, D = `docs/reports/precheck/data/tacit-agentdojo`):

```bash
uv run python tools/precheck/l1_scan.py --source tacit-agentdojo --part head --corpus-id tacit-agentdojo --jobs 2 --emit-fp --git ~/.agentprov/staging/10c/tacit/Tacit.git
uv run python tools/precheck/l2_sample.py select --units W/l1-units-head.jsonl --source tacit-agentdojo --part head --corpus-id tacit-agentdojo --out D/l2-sample-head.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j2 --source tacit-agentdojo --part head --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j1 --source tacit-agentdojo --part head --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-head-j2.partial --out D/l2-head.json --sample D/l2-sample-head.json --l1-units W/l1-units-head.jsonl --compare-with W/l2-head-j1.partial --jobs 2
# inside l2_check:
uv run agentprov validate --corpus W/l2-head-j2.partial --tiers aer,sem,prov,linkage,shacl,regression --jobs 2
uv run agentprov recompute --corpus W/l2-head-j2.partial --dry-run --jobs 2 -q
uv run agentprov verify --corpus W/l2-head-j2.partial --level chain
```

Examiner scripts (read-only, through `agentprov.ingest`; S = `D/exam-scripts`, outputs under `W/exam/`; git reads with `GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file`):

```bash
uv run python S/census.py $PWD W/exam/census.json   # PC-01, PC-04, PC-07, PC-09 (raw census)
uv run python S/b181.py                             # PC-03
uv run python -I S/cc07_161.py D/cc07.json          # PC-10 (CC-07 #161; repo root)
uv run python S/acct.py <2 persona-path labels>     # PC-05
uv run python S/qwentag.py                          # PC-07 qwen <tool_call> finals
uv run python S/emptyfinal.py                       # PC-08 / PC-09
uv run python S/nullfinal.py                        # PC-08 bases
python3 S/l2exam.py W/l2-head-j2.partial            # L2 issue table, sampled label flags
uv run python S/os.py                               # section 6 rates
grep -c local_model_raw_completion src/agentprov/adapters/agentdojo/profiles/tacit-agentdojo.profile.toml   # PC-01: 0
grep -c tacit src/agentprov/adapters/agentdojo/artefacts.toml                                              # PC-07: 0
```

Follow-ups for the orchestrator (not run):

| # | What | Command | When |
|---|---|---|---|
| 1 | `recheck12` (PC-08); expected `null_final` 31, native-I split populated, everything else unchanged. Critic: the current CC-08 `is_twin` does not decode inference-bundle ids (refuted PC-glitch-agentdojo-04, PC-melon-agentdojo-11, refuted PC-hilarytorn-trajectory-poisoning-06), so run the `l2_check` re-run only after that fix; the l1 step can run now | `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-recheck12 -- uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/recheck12.toml` | done (`4a3e40c1`; section 5 Recheck) |
| 2 | Targeted scratch import of 12 labels outside the frozen sample (7 off-set tool-name logs, 2 persona-path logs, the incomplete log, 2 null-final logs; [`targeted-sample.json`](data/tacit-agentdojo/targeted-sample.json), sha256 `de6525980671...`), recorded as supplementary. Expected: 12 mapped, 0 `adapter_defect`, `incomplete_run` 1, `retry_passes_inferred` 2, `unexecuted_tool_call` 4, redaction hits only persona paths (never `operator-*`) | `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-tacit-agentdojo -- uv run python tools/precheck/l2_import.py --sample D/targeted-sample.json --corpus W/l2-head-targeted --source tacit-agentdojo --part head --jobs 2`, then `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-tacit-agentdojo -- uv run python tools/precheck/l2_check.py --corpus W/l2-head-targeted.partial --out W/exam/l2-targeted.json --sample D/targeted-sample.json --l1-units W/l1-units-head.jsonl --jobs 2` | before the round |
| 3 | Regen item (PC-01 + PC-06) for the family owner, user approval before any re-import; then full import of head in the round with full-population determinism (jobs 2 vs 1) | owner's profile edit; round import | regen round |
| 4 | Optional, light: run the generic `text_encoded_call` detector over `W/l2-head-j2.partial` for the PC-07 `text_tool_call` count | read-only | optional |
