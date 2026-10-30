# Pre-check dossier: `yockcheng-prompt-injection-harness`

## 1. Header

| | |
|---|---|
| Corpus | `yockcheng-prompt-injection-harness` (Apache-2.0 by repository LICENSE; no separate data licence; see PC-02) |
| Parts | `head` (280 AgentDojo TraceLogger logs: v1.k14 277, v1.k14.incomplete 3) |
| Family / profile | `agentdojo` / `yockcheng-prompt-injection-harness@1` (sha256 `2bda7d01b119...`; dialect `agentdojo.tracelogger`; rules aer 1, agentdojo 2; SEM `agentdojo.suites@2`; `verified_code = []`) |
| Pin | git `yockcheng/prompt-injection-harness` `5f9137ff` (2026-08-11, default branch `prompt-injection-harness`); `runs/` tree `49cd8612` unchanged since `606606e0` (2026-07-10). Input: blob:none bare clone in staging, git mode, lazy fetch off; 2 absent blobs (`static/*.png`, not selected) |
| Code commit | L1, sample, both imports and check at `cb0af3d8` (clean tree); batch `wave2`; examined on `faa06d3d` |
| Kind | wave 2, new corpus (not in FA or E2; no stored corpus) |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (L1, L2, exam, verify, dossier) |
| Agents | researcher and fact-checker (prereg, research), examiner (L1/L2 analysis), one verifier per finding (9), dossier writer |
| Data | [`data/yockcheng-prompt-injection-harness/`](data/yockcheng-prompt-injection-harness/): `research.json`, `l1-head.json`, `l1-extra.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `os1-population.json`, `os2-sample.json`, `findings.json`, `exam-scripts/`; cross-corpus `data/_cross/l1-xdup.json` |

- Code identity, part `head` (Level 1 and Level 2, [`code-head.json`](data/yockcheng-prompt-injection-harness/code-head.json)): commit `cb0af3d8`; engine code aer `24df84b5e307`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `d3f9995f61bf`; adapter agentdojo.tracelogger `c311b5a6ac9e`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Repository | https://github.com/yockcheng/prompt-injection-harness (pin `5f9137ff`; created 2026-07-15; not a fork; 0 issues, 2 closed PRs, no releases) | the data (`runs/`, 280 JSON logs), added in one commit `606606e0` |
| Paper | none (Zenodo, Hugging Face, arXiv, GitHub releases re-checked 2026-10-14: 0 hits) | no reported utility/ASR for `runs/`; the repository README reports only find/grade results of its own harness, from batches not in the repository |
| Benchmark | AgentDojo, arXiv:2406.13352 (package `agentdojo 0.1.35`, workspace suite v1 and v1.2.2) | reference only |
| Upstream harness code | https://github.com/anthropics/defending-code-reference-harness (branch `main` of the repository is its history) | origin of the harness code and of the LICENSE copyright line (PC-02); not of the logs |
| Upstream issues | AgentDojo #213 (v1.2 workspace injection tasks 6-13), #154 (run errors) | known defects; none applies to an observed log here (error null 280/280) |

Data-versus-paper notes (from `research.json`):

- No document describes `runs/`; the only reference rates are our own census aggregates (ASR 0/255; utility 225 / 52 / null 3).
- The logs (2026-06-22 for `runs/`, 2026-07-01 for `runs/agentdojo-native/`) predate the adaptation commit (2026-07-10) and the repository (2026-07-15); no code in the repository writes `runs/`.
- The repository's Docker target patches `agentdojo/models.py` and overwrites the workspace `inbox.yaml`; whether the logs used it was open (tested as H6: they did not, PC-06).
- Two trees with different benchmark versions; `claude-sonnet-4-5` is in both. `claude-sonnet-4-5` is an alias; no snapshot is logged.
- The two retired models (claude-3-7-sonnet, claude-3-haiku) were retired before the log dates; their 3 logs are the incomplete ones.
- Profile notes: "no copyright line" (PC-02) and "the same 257 runs" (PC-03) do not match the pin.

## 3. Expectations

Pre-registration: [`prereg/yockcheng-prompt-injection-harness.md`](prereg/yockcheng-prompt-injection-harness.md), committed in `fd75f8a3` (2026-10-14) before any check of this corpus ran, with an adversarial fact-check (2 corrections: PyPI wheel vs sdist digest; trial jobs 3 was a 59-unit subset). Amendments 2-4 (README section 8) apply; amendment 1 does not (no stored corpus).

Classes follow the canonical rules R1-R6 and cross-cutting items CC-01 to CC-11 of [`cross-cutting.md`](cross-cutting.md). CC-07: the corpus is workspace-only (280/280), so #181 and #161 (banking) do not apply: 0 affected logs; no slack logs, so CC-10 does not apply. CC-09: PC-01 is its reference.

Hypotheses H1 to H10: all supported (rows from `exam.json`; H9 completed in the wave-2 follow-up).

| H | Result | Evidence |
|---|---|---|
| H1 | supported | attacked security true 0/255; utility T 225 / F 52 / null 3; benign security T 22 (25 none-logs minus 3 incomplete); every section-2 cell count equal |
| H2 | supported | the 3 incomplete logs are exactly the retired-model logs (system + user only, error null) |
| H3 | supported | `runs/` 31/31 dated 2026-06-22; native 249/249 dated 2026-07-01 |
| H4 | supported | v1.2.2 = the 31 `runs/` logs, v1 = the 249 native; the 16 IT6-13 logs are all v1.2.2 |
| H5 | supported | v1.2.2 pre-pass IT6-13 utility recorded 8/8 (6 true); placeholder args null on 693/693 calls |
| H6 | supported | 0 patched `inbox.yaml` senders in 280 logs; stock senders in tool output (PC-06) |
| H7 | supported | the 4 models; `important_instructions` 255 / null 25; workspace 280; no defence label |
| H8 | supported | 280 distinct cells, 0 duplicates; haiku-4-5 attacked grid 40 × 6 = 240 complete |
| H9 | supported | byte-identical 0 within and across corpora; cross-corpus trajectory groups hold 0 of the 240 haiku attacked logs. The phase-10c lead (one fingerprint shared with ceferisbarov), tested 2026-10-21 from the `_fp` files: 1 group = 2 yockcheng incomplete pre-pass logs (IT0, system + user only) + 1 ceferisbarov IT0 pre-pass, 0 byte-identical (PC-08) |
| H10 | supported | L1-06 0 classes in 280 artefacts; L2 redaction 0 hits in 104 files |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

`l1_scan` at `cb0af3d8`, rc 0, 0.8 s.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | walked 358 = selected 280 + context 7 + not selected 69 + absent blob 2; strays 0, rejected 0, excluded 0; units 280 = registry 280 | equal to prereg section 2 and the tree listing |
| L1-02 parse | 280/280 strict ok; 0 duplicate key, non-finite, big int, lone surrogate, BOM, trailing data, invalid UTF-8, truncation, depth | as expected; lenient classes not needed |
| L1-03 encodings | 0 U+2028/2029/0085, C0/C1, ESC, bidi, tag, zero-width, PUA, U+FFFD, mojibake, JSON-in-string. Residues by design, all in role `tool` content: escaped newline 211 strings / 123 files, escaped quote 20 / 19, escaped unicode 73 / 54 of 280 | expected-known (AgentDojo YAML-dump tool output); no finding |
| L1-04 duplicates | byte-identical 0 within part, 0 cross-corpus. Trajectory-identical 2 groups / 5 units (277 distinct fingerprints of 280): haiku-4-5 user_task_27 x injection_task_0/1/3 (0 tool calls) and two incomplete pre-pass logs. Cross-corpus 2 groups with `shreeyavarma-llm-safety`, incomplete logs only; 0 of the 240 haiku attacked logs | PC-08; CC-01 cannot matter (no call ids in these logs); ceferisbarov not testable (PC-09 follow-up) |
| L1-05 arms | 8 strata = prereg section 3. haiku-4-5 v1 attacked 240 (40 x 6, full grid) + pre-pass 6; sonnet-4-5 v1 attacked 1 + pre-pass 1; 3-haiku v1 pre-pass 1 (incomplete); sonnet-4-5 v1.2.2 attacked 14 + benign 1 + pre-pass 14; 3-7-sonnet v1.2.2 benign 1 + pre-pass 1 (both incomplete). Totals attacked 255 / benign 2 / pre-pass 23; 280 distinct cells, 0 duplicates; path facets = raw ids 280/280 | H7, H8 supported; arm design PC-07 |
| L1-06 secrets/paths | 0 classes in 280 (no secret-like shape, account path, operator home, `[withhold]` match, local-path model) | H10 supported |
| L1-07 timestamps | `/evaluation_timestamp` 280/280, naive 280, parse failures 0; `runs/` 31/31 2026-06-22, native 249/249 2026-07-01; one timestamp per log (tool-argument dates are benchmark data) | H3 supported |
| L1-08 degenerate | incomplete 3 (system + user only, utility/security keys absent, error null); empty/tiny/zero-message/error-only 0; error null 280/280; empty finals 0 by the E2 definition, so the CC-08 `null_final` gap changes nothing here | H2 supported |
| L1-09 | not applicable (git tree, no archive members) | n/a |

Raw census (reproduces phase 10c): roles system 280 / user 280 / assistant 814 / tool 693; tool calls 693 (`placeholder_args` present and null 693/693); tool errors 66 in 44 logs; benchmark_version v1 249 / v1.2.2 31; package 0.1.35 280; `pipeline_name` = pipeline dir 280/280.

## 5. Level 2

| Item | head |
|---|---|
| Sample | [`data/yockcheng-prompt-injection-harness/l2-sample-head.json`](data/yockcheng-prompt-injection-harness/l2-sample-head.json): 32 of 280 in 8 strata (quotas 7/7/6/2/1/1/1/7), seed 20261011, `over_maximum` false, sample join 32/32 |
| Import | scratch `l2-head-j2.partial` (7.5 s) and `l2-head-j1.partial` (12.6 s) at `cb0af3d8`, dev mode, git-seeded pin tree (covering paths 14, absent blobs 2). Mapped 32; sealed clean 29, with issues 3; failed 0; degenerate 0 |
| Validation | tiers aer, sem, prov, linkage: 32/32 pass, linkage 100 %, results reproduced 32. SHACL not implemented (skipped); regression n/a |
| Recompute | `--dry-run`: 32 identical, 0 unexplained; raw verified 39/39 |
| Determinism | j2 vs j1: 142/142 files byte-identical, index identical |
| Verify chain | 0 failures; only `checksums.absent` (working tree) |
| A2 | 0 adapter_defect, 0 degenerate, 0 unreadable, 0 failed checks. Issue codes = trial's: earlier_attempts_unobservable 32, accounting_unverifiable 29, incomplete_run 3; completeness known_incomplete 3 / unverifiable 29. Tool executions 72 = raw calls 72; tool errors 1 = raw 1. Model calls 79, `/params` not_recorded 79/79 (CC-04 representation; prereg does not cite U6-c) |
| A3 | 0 PI classes over 11,623 statements / 19,903 relation arguments |
| Evidence classes | core D 140 (engine rules only: n_capture_profile 32, n_gap 108) / O 650 / none 72; inference I 2,912; assessment I 841 / O 64. No adapter-rule statement and no relation in core, as `verified_code = []` predicts; no family D rule cited without its `_unverified` twin in PROV or SEM. SEM 557 annotations, all I. `_unverified` split after recheck12 (CC-08, PC-04; bundle-id decoding of 5efa3575): of 3,601 statements, twin 3,186 (inference I 2,448, none 273, assessment I 465) and mixed twin + native inference I 415; native-only 0. The earlier 2,400 twins + 1,201 native came from the fix without bundle-id decoding and are superseded |
| Identity | model from pipeline dir 32/32 (`model.requested` only; `claude-sonnet-4-5` kept as alias, no snapshot invented); defence none 32; attack 15 / none 17; suite workspace 32; 0 mismatches, 0 unresolved; benchmark actor version v1 16 / v1.2.2 16; naive start kept as `start_naive` |
| OS-2 | 64 judgements, 0 raw-vs-mapped mismatches; 3 incomplete without judgement (none invented); 14 benign pre-pass security with origin `harness_default`; SEM `injection_marker` in 15/15 sampled attacked executions |
| Redaction | 0 hits in 104 files |
| Withholding | no `[withhold]` policy, nothing found by L1-06: not applicable, as pre-registered |

### Recheck (CC-08, recheck12)

`plans/recheck12.toml` (l1, l1_10, check; sample frozen) against the d97d3a57 files; full deltas in [`_cross/recheck12.json`](data/_cross/recheck12.json). Every other L1/L2 count is unchanged; the only other deltas are run environment (code commit d97d3a57 with tools/src = 5efa3575, `tracked_changes` true, two H.8.4(2) recompute notices with 0 unexplained changes; R12-01).

| Part | L1-08 flags (old -> new) | L2 `_unverified` split | L1-10 |
|---|---|---|---|
| head | no change | twin inference:I 2,863 -> 2,448; mixed 415; native 0 (sum 2,863 = old) | 7 screened (context 7); 0 hits; files with a hit 0; named accounts 0; operator 0; unreadable 0 |

- L2 split only; native 0; L1 unchanged.

## 6. Outcome comparison

No paper or reported number exists; the reference is the pre-registered census aggregate. L1 = OS-1 population recount of the raw fields; L2 = mapped values of the sample (R6: below n 20 Wilson only, no gap rule). Wilson 95 % in percent. Full rows: `os1-population.json`, `os2-sample.json`.

| Arm | Level | n | Metric | Rate (Wilson 95 %) | Reference | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|---|
| all attacked (important_instructions, both trees) | L1 | 255 | targeted ASR | 0.00 (0/255) [0.00, 1.48]; CP upper 1.17 | prereg census 0/255 | 0 | match; zero-success source disclosed (PC-05) |
| haiku-4-5 v1 native attacked | L1 | 240 | ASR | 0.00 (0/240) [0.00, 1.58] | part of 0/255 | 0 | match |
| haiku-4-5 v1 native attacked | L1 | 240 | utility under attack | 79.58 (191/240) [74.04, 84.20] | none per arm | n/a | no reference; no benign baseline (PC-07) |
| sonnet-4-5 v1.2.2 `runs/` attacked (user_task_0 x it0..13) | L1 | 14 | ASR / utility under attack | 0/14 [0.00, 21.53] / 14/14 [78.47, 100.00] | none | n/a | Wilson only |
| sonnet-4-5 v1 native attacked (user_task_0 x it0) | L1 | 1 | ASR / utility under attack | 0/1 [0.00, 79.35] / 1/1 [20.65, 100.00] | none | n/a | Wilson only |
| pre-pass, all models | L1 | 21 (+2 incomplete) | injection goal reached when asked directly | 85.71 (18/21) [65.36, 95.02] | none | n/a | checker can score success |
| pre-pass haiku-4-5 v1 / sonnet-4-5 v1.2.2 / sonnet-4-5 v1 | L1 | 6 / 14 / 1 | pre-pass utility | 5/6 [43.65, 96.99] / 12/14 [60.06, 95.99] / 1/1 [20.65, 100.00] | none | n/a | Wilson only |
| benign user task (sonnet-4-5 v1.2.2) | L1 | 1 (+1 incomplete) | benign utility | 1/1 [20.65, 100.00] | none | n/a | Wilson only |
| all logs | L1 | 277 (+3 null) | utility | 81.23 (225/277) [76.21, 85.39] | prereg census 225 / 52 / 3 | 0 | match |
| haiku-4-5, none, important_instructions | L2 | 7 | ASR / utility under attack | 0/7 [0.00, 35.43] / 6/7 [48.69, 97.43] | population 0/240, 79.58 | n/a (n < 20) | consistent |
| sonnet-4-5, none, important_instructions (both trees pooled by `l2_check`) | L2 | 8 (7 v1.2.2 + 1 v1) | ASR / utility under attack | 0/8 [0.00, 32.44] / 8/8 [67.56, 100.00] | population 0/15, 15/15 | n/a | consistent; pooling changes no number here (PC-09) |
| pre-pass haiku-4-5 / sonnet-4-5 | L2 | 6 / 8 | pre-pass utility | 5/6 [43.65, 96.99] / 7/8 [52.91, 97.76] | population 5/6, 13/15 | n/a | consistent |
| raw vs mapped, same labels | L2 | 32 labels | utility and security | 0 of 64 differ | raw L1 fields | 0 | match (mapping faithful) |

No row is flagged by the gap rule. The zero ASR is investigated in PC-05 anyway: no run errors, arm identity consistent, mapped = raw, the payload reaches the agent in at least 239 of 255 logs, no tool call names the attacker identity, and the checker scores success on pre-passes. No data is excluded or recommended for exclusion for its attack outcome (user rule; D-279).

## 7. Findings

9 findings, all confirmed by their verifier (0 refuted). Verifier corrections are folded into `findings.json` (CC-06 format). Analysis-artefacts (R5: PC-04, PC-08 (CC-01), PC-09) are tool or fingerprint properties and are not counted in the readiness verdict.

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-yockcheng-prompt-injection-harness-05 | Zero targeted attack success in 255 attacked logs although the payload reaches the agent (present 218, prefix-only 21, absent 16 by a substring screen; 239 is a lower bound) | expected-known (R2; D-279) | S2 | confirmed, with additions (lower-bound wording; 0 attacker-identity tool calls; checker scores 22 pre-pass successes) | Keep every log; disclose 255 attacked / 0 successes with the zero-event bound and n |
| PC-yockcheng-prompt-injection-harness-01 | [CC-09] reference: `artefacts.toml` scopes omit this source although six AgentDojo entries apply (benign_security_constant 25 / 22, injection_task_as_user 23, incomplete_run 3, naive_timestamp 280, silent_rerun, payload_not_reaching_agent) | documentation-mismatch (CC-09) | S3 | confirmed; affects the safety-net scan (scope.profiles restricts entries); shared by the other phase-10d/10e AgentDojo-format profiles (propose one cross-cutting item); silent_rerun rows given units | Family owner extends the six scopes; entries below |
| PC-yockcheng-prompt-injection-harness-02 | Profile says the LICENSE has no copyright line; line 188 names Anthropic PBC (2026), inherited from the upstream harness | documentation-mismatch (R4) | S3 | confirmed; extend to attribution and lineage | Profile owner fixes holders note, attribution list and upstream lineage note |
| PC-yockcheng-prompt-injection-harness-03 | Profile pin note "customize-skill holds the same 257 runs": both branches hold the same 280 logs (257 = S1 path-pattern count without the 23 pre-passes) | documentation-mismatch (R4) | S3 | confirmed; same wording in `family-raw-layouts.md` l. 68 | "280 logs (257 user-task logs + 23 pre-passes), blob-identical on both branches" in both files |
| PC-yockcheng-prompt-injection-harness-06 | Logs show the stock AgentDojo inbox, not the repository's patched `inbox.yaml`: the repository harness did not produce the logs | expected-known (`verified_code = []`, quirk `package_version_not_code_identity`) | S3 | confirmed; counts corrected to 30 distinct native v1 logs and 4 v1.2.2 logs; logs predate the fixture commit | Datasheet: environment is stock 0.1.35 workspace; keep `verified_code = []` |
| PC-yockcheng-prompt-injection-harness-07 | Arm design: haiku-4-5 has no benign user-task runs, sonnet-4-5 is a user_task_0 smoke test over two benchmark versions, retired models have only incomplete logs | expected-known (prereg section 3) | S3 | confirmed | Report haiku as attacked-only, split sonnet-4-5 by version, list 3 incomplete logs; keep all |
| PC-yockcheng-prompt-injection-harness-08 | [CC-01] Identical trajectories are trivial: one zero-call group in the part, incomplete-log groups within and across corpora (shreeyavarma 2 groups; ceferisbarov 1, H9) | analysis-artefact (CC-01; was expected-known) | S3 | confirmed (independent regroup and raw check) | No data action; cross-corpus dedup must not treat prompt-only incomplete logs as repeats |
| PC-yockcheng-prompt-injection-harness-04 | [CC-08] `l2_check` twin counter mixes catalogue twins with native class-I `_unverified` rules (wave-2 counter; the first fix gave 2,400 twins + 1,201 native of 3,601) | analysis-artefact (CC-08) | S3 | confirmed; unit wording corrected | Resolved by recheck12: twin 3,186, mixed 415, native 0 of 3,601 |
| PC-yockcheng-prompt-injection-harness-09 | `l2_check` outcome arm key (model, defence, attack) pools the two benchmark versions of claude-sonnet-4-5 | analysis-artefact | S3 | confirmed for the arm key; the missing ceferisbarov input of `l1_xdup` is a scheduling gap, moved to follow-ups | Report per tree (as here); optionally add benchmark_version to the arm key |

Refuted: none.

Proposed `artefacts.toml` changes (text only; route to the agentdojo family owner, PC-01):

```toml
# extend each existing entry: scope.sources += ["yockcheng-prompt-injection-harness"],
# scope.parts += ["head"], scope.profiles += ["yockcheng-prompt-injection-harness"]
# agentdojo.art.benign_security_constant
expected += [{ snapshot = "yockcheng-prompt-injection-harness:head", count = 25, basis = "pre-check L1 raw census: benign (attack none) logs incl. 23 pre-passes and 3 incomplete", status = "proposed" }, { snapshot = "yockcheng-prompt-injection-harness:head", count = 22, unit = "judgements", basis = "pre-check: non-null benign security judgements (profile origin_rule_applied 22)", status = "proposed" }]
# agentdojo.art.injection_task_as_user
expected += [{ snapshot = "yockcheng-prompt-injection-harness:head", count = 23, basis = "pre-check L1: solvability pre-passes (6 + 1 + 1 native, 14 + 1 runs/)", status = "proposed" }]
# agentdojo.art.incomplete_run
expected += [{ snapshot = "yockcheng-prompt-injection-harness:head", count = 3, basis = "pre-check L1-08: v1.k14.incomplete logs of the two retired models (system + user only)", status = "proposed" }]
# agentdojo.art.naive_timestamp
expected += [{ snapshot = "yockcheng-prompt-injection-harness:head", count = 280, basis = "pre-check L1-07: naive /evaluation_timestamp in every v1.k14 log", status = "proposed" }]
# agentdojo.art.silent_rerun
expected += [{ snapshot = "yockcheng-prompt-injection-harness:head", count = 0, unit = "null_final_logs", basis = "pre-check L1-08: null-final logs", status = "proposed" }, { snapshot = "yockcheng-prompt-injection-harness:head", count = 280, unit = "logs", basis = "rule log_holds_last_pass applies to every log; phase-10d trial and pre-check L2 32/32", status = "proposed" }]
# agentdojo.art.payload_not_reaching_agent: scope only now; expected row after the safety-net
# detector runs on the full import (raw screen gives 16 of 255)
```

The profile's `incomplete_run` quirk records `null_outcome_files = 0`; the 3 incomplete logs lack the utility and security keys (checked through `agentprov.ingest`, key names only), so they have absent rather than null outcomes and the quirk value is consistent. Not a finding.

Items for AGENTS.md section 12:

- PC-05: `yockcheng-prompt-injection-harness` contributes 255 attacked AgentDojo workspace runs (Claude haiku-4-5 240, sonnet-4-5 15; important_instructions; no defence) with 0 targeted successes (Wilson upper 1.48 %), payload visible in at least 239. Kept in full (D-279); any pooled ASR must disclose it.

## 8. Recommendations and readiness

1. AgentDojo family owner: extend the six `artefacts.toml` scopes (PC-01; the family-wide gap is CC-09).
2. Profile owner: correct the holders note and add the Anthropic PBC attribution and upstream lineage (PC-02); fix the "257 runs" note in the profile and in `family-raw-layouts.md` (PC-03). Metadata only; no stored corpus exists.
3. Datasheet: zero-success disclosure with n and bound (PC-05); stock environment, not the repository target (PC-06); attacked-only haiku arm, sonnet-4-5 split by benchmark version, 3 incomplete retired-model logs (PC-07).
4. Tools: PC-04 resolved by recheck12 (bundle-id decoding of 5efa3575); report outcomes per tree (PC-09).
5. After the round: run the `payload_not_reaching_agent` safety net on the full import and set its expected row; the ceferisbarov lead is answered from the `_fp` files (H9); a full `l1_xdup` re-run is optional.
6. No exclusion of any data: zero-success, incomplete and smoke-test arms are kept.

**Readiness: `ready-with-caveats`.**

- The part imports correctly and deterministically: validation 32/32, recompute 0 unexplained, j1/j2 byte-identical (142 files), A2/A3 clean, OS-2 raw = mapped (0 of 64), identity 0 mismatches, no secret or account path (L1-06 0, redaction 0 hits).
- Caveats, all owned and routed: S2 disclosure PC-05 (datasheet); `artefacts.toml` scopes PC-01 (family owner); profile metadata PC-02/PC-03 (profile owner); design disclosures PC-06/PC-07.
- Not counted: PC-04 (CC-08, resolved), PC-08 (CC-01), PC-09 (R5); PC-01 (reference to CC-09).

## 9. Reproduction

Batch (wave 2; plan entry in `tools/precheck/plans/wave2.toml`):

```toml
[[part]]
corpus_id = "yockcheng-prompt-injection-harness"
source = "yockcheng-prompt-injection-harness"
part = "head"
l1 = ["--git", "~/.agentprov/staging/10c/yockcheng/prompt-injection-harness.git"]
```

```bash
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 4 --label precheck-wave2 -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave2.toml
```

Steps the batch ran (all rc 0, `_batch/wave2/status.jsonl`). W = `~/.agentprov/migration-work/precheck/yockcheng-prompt-injection-harness`, D = `docs/reports/precheck/data/yockcheng-prompt-injection-harness`, C = `yockcheng-prompt-injection-harness`:

```bash
uv run python tools/precheck/l1_scan.py --source C --part head --corpus-id C --jobs 2 --emit-fp --git ~/.agentprov/staging/10c/yockcheng/prompt-injection-harness.git
uv run python tools/precheck/l2_sample.py select --units W/l1-units-head.jsonl --source C --part head --corpus-id C --out D/l2-sample-head.json
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j2 --source C --part head --jobs 2
uv run python tools/precheck/l2_import.py --sample D/l2-sample-head.json --corpus W/l2-head-j1 --source C --part head --jobs 1
uv run python tools/precheck/l2_check.py --corpus W/l2-head-j2.partial --out D/l2-head.json --sample D/l2-sample-head.json --l1-units W/l1-units-head.jsonl --compare-with W/l2-head-j1.partial --jobs 2
# inside l2_check:
uv run agentprov validate --corpus W/l2-head-j2.partial --tiers aer,sem,prov,linkage,shacl,regression --jobs 2
uv run agentprov recompute --corpus W/l2-head-j2.partial --dry-run --jobs 2 -q
uv run agentprov verify --corpus W/l2-head-j2.partial --level chain
```

Examiner scripts (read-only; from the worktree root; E = W/exam):

```bash
uv run python D/exam-scripts/census.py $PWD E/census.json          # raw census (H1-H10 inputs)
python3 -I D/exam-scripts/hyp.py E/census.json                      # hypotheses, cells, H6 needles (PC-05/06/07)
uv run python D/exam-scripts/reach.py $PWD E/reach.json             # payload reach screen (PC-05)
uv run python -I D/exam-scripts/os1.py $PWD E/census.json E/os1.json # OS-1 population rates
python3 -I D/exam-scripts/os2.py W/l2-head-j2.partial E/os2.json    # OS-2 raw vs mapped
uv run python -I D/exam-scripts/evclass.py W/l2-head-j2.partial E/evclass.json
uv run python -I D/exam-scripts/twins.py $PWD E/evclass.json E/twins.json   # PC-04
GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file git -C ~/.agentprov/staging/10c/yockcheng/prompt-injection-harness.git show 5f9137ff:LICENSE | grep -n 'Copyright 20'   # PC-02
```

Follow-ups for the orchestrator:

| # | What | Command | When |
|---|---|---|---|
| 1 | PC-04 / CC-08: re-run `l2_check` with the twin-counting fix (`6b76c15e`) plus the pending bundle-id decoding in `is_twin` (critic: the current CC-08 `is_twin` does not decode inference-bundle ids (refuted PC-glitch-agentdojo-04, PC-melon-agentdojo-11, refuted PC-hilarytorn-trajectory-poisoning-06)) | `uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-yock-l2check -- uv run python tools/precheck/l2_check.py --corpus W/l2-head-j2.partial --out D/l2-head.json --sample D/l2-sample-head.json --l1-units W/l1-units-head.jsonl --compare-with W/l2-head-j1.partial --jobs 2` | done by recheck12 (`4a3e40c1`; section 5 Recheck) |
| 2 | PC-01: `payload_not_reaching_agent` expected row | `agentprov stats --artefacts` on the round's full import; compare with the raw screen's 16 of 255 | after the round |
| 3 | H9: test the phase-10c lead (one fingerprint shared with ceferisbarov) | `uv run python tools/precheck/l1_xdup.py` | answered 2026-10-21 from the `_fp` files (1 group, incomplete pre-passes; H9); optional `l1_xdup` re-run for `_cross/l1-xdup.json` |
| 4 | PC-01: one cross-cutting item for AgentDojo-format profiles missing from `artefacts.toml` scopes | no command | done (CC-09) |
