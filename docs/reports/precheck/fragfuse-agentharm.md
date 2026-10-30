# Pre-check dossier: `fragfuse-agentharm`

## 1. Header

| | |
|---|---|
| Corpus | `fragfuse-agentharm` (restricted-use class: MIT plus the AgentHarm use clause, LIC 3, D-144) |
| Parts | `fragfuse-agentharm · logs` (1 part; registry `planned`) |
| Family / profile | `inspect` / `fragfuse-agentharm@1` (semantics `inspect.agentharm@2`, dialect `inspect.eval` v2) |
| Pin | git `zixin22/fragfuse_agentharm` @ `24cc8aea` (HEAD 2026-10-14), 3,847 blobs / 318,827,530 B |
| Code commit | `d97d3a57` (L1 and L2, batch `wave4`, all steps rc 0, no tracked changes) |
| Kind | wave 4, first examination (not in FA or E2); no stored corpus |
| Date | 2026-10-14 (prereg, research), 2026-10-15 (batch), 2026-10-21 (examination, dossier) |
| Agents | researcher and fact-checker (prereg, research), examiner (this file); adversarial verifier 2026-10-21 (all 8 confirmed, PC-03 and PC-07 counts corrected) |
| Data | [`data/fragfuse-agentharm/`](data/fragfuse-agentharm/): `research.json`, `l1-logs.json`, `l1-10-logs.json`, `l2-sample-logs.json`, `l2-logs.json`, `code-logs.json`, `exam.json`, `findings.json`, `os1-population.json`, `os2-sample.json`, `aer-pass.json`, `h19.json`, `exam-scripts/` |

- Code identity, part `logs` ([`code-logs.json`](data/fragfuse-agentharm/code-logs.json)): commit `d97d3a57` (tracked_changes false); engine code aer `856b7a09e0cf`, sem `a8141c23af13`, prov `d57bd291d3cc`, validation `a10ee3c16045`, expand `3b1d412bb77a`; adapter `inspect.eval@0.1.0` `1867569d63c9`; profile sha256 `1943f6f39974`, rules aer 1 / inspect 2; lockfile `b0455f1058c8`, limits `5d6dbb210259`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Data repository | https://github.com/zixin22/fragfuse_agentharm @ `24cc8aea` (2 commits, 0 tags, 10 dependabot issues) | the data |
| FragFuse paper | https://arxiv.org/abs/2606.15609 (v1, USENIX Security 2026) | Table 1/18 InspAgent rows; TSR 38.6 % GPT-4o direct |
| AgentHarm paper | https://arxiv.org/abs/2410.09024v3 | Table 9 GPT-4o 48.4 / 48.9 / 90.1, benign 89.9 (264-behaviour public test) |
| Zenodo | https://zenodo.org/api/records/20337560, https://zenodo.org/api/records/20387340 (CC-BY-4.0) | artefact records of the paper (software type) |
| Harness | inspect_ai 0.3.154.dev37 / 0.3.158 / 0.3.159.dev20; inspect_evals `d9787f49`, AgentHarm task version 1.0.0 | producer and scorer (before #2107, #2101, #2146 fixes; #2108 open) |

Data-versus-paper notes: no logged arm is a paper arm (no access-control arm, no GPT-5.1/Gemini); the 176-task attack runs exist only as `iteration_4/*.json` outputs; the logged split is the 176-sample inspect_evals split, not the paper's 264.

## 3. Expectations

Pre-registration: [`prereg/fragfuse-agentharm.md`](prereg/fragfuse-agentharm.md), committed in `fd75f8a3`, before any check of this corpus. Amendments 1-5 (README section 8) apply; none changes this part. Classes follow R1-R6 and CC-01..CC-11 ([`cross-cutting.md`](cross-cutting.md)).

Hypotheses H-01..H-19: 11 supported, 5 partly supported (H-02, H-06, H-07 count part, H-16, H-17), 2 not tested (H-03, H-13), 1 refuted (H-19, PC-04). Table in section 5.

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Run at `d97d3a57`, `--use-pin`, 15.0 s, jobs 2.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 3,847 walked; 164 selected, 4 excluded (`select.not_execution_artefact`, mock none/none), 3,679 not selected; 0 strays; units 1,747 = registry | as expected (H-01). Tree: 168 `.eval` / 49,874,989 B; 3 `inspect_logs_spot/*.json` / 56,448,377 B not selected (H-03 not tested) |
| L1-02 parse | strict class ok 164/164 | as expected (H-04) |
| L1-03 encodings | ANSI/ESC 16/164 (error tracebacks of the 16 error logs); C0 1/164 (10 strings in tool-call `body` args); variation selectors 9/164 (373); literal escapes in 11-12/164; `json_in_string` 15,317 (tool-call arguments); 0 bidi, tag, zero-width, U+FFFD, mojibake | as expected |
| L1-04 duplicates | byte-identical 0; trajectory groups 186 (464 units; 1,469 distinct fp of 1,747; differing facets producer 60, model 3, dir 1). Cross-corpus (`_cross/l1-xdup.json`): kexin 49 groups, survey 0, byte-identical 0 | as expected (H-16 part, H-18); CC-01 definition |
| L1-05 arms | 7 strata = prereg section 2 exactly: gpt-4o harmful 7 logs/1,059, benign 4/354; gpt-5-nano benign 7/184; claude-opus harmful 3/5, benign 3/5; retrieve 136/136; carrier 4/4. Producers dev37 21, 0.3.158 136, dev20 7. Categories 8 + none 136 | as expected; missing vs paper: GPT-5.1, Gemini 2.5 Flash, all LLM-AC / ShieldAgent arms; extra: gpt-5-nano, claude-opus, router plans, retrieve, carrier |
| L1-06 secrets/paths | users-dir named 3,414 strings in 164/164, 2 distinct accounts (tracebacks, plan `memory_bank_path` 136, dataset location 24, `carrier_query_path` 4): PC-02. home-dir named 7,869 in 34/164, 6 distinct: benchmark content (CC-03). Key-shaped: anthropic 7 and openai 7 in 1/164 each; generic credential 79 in 5/164; 0 in headers: PC-03. Operator 0 | H-08 raw part supported; H-17 partly |
| L1-07 timestamps | 0 parse failures; all ISO forms carry an offset; range 2025-12-25..2026-04-20; event timestamps non-monotone in 1,064 units (quirk `event_order_not_time_order`) | as expected |
| L1-08 degenerate | sample_error 22 units (all in the 16 status-error logs), sample_limit 74 | as expected (H-14, quirk 74) |
| L1-10 context | 0 files screened (no auxiliary artefacts declared) | n/a |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`l2-sample-logs.json`](data/fragfuse-agentharm/l2-sample-logs.json): 32 files over 7 strata (quotas 4/3/3/6/4/6/6), 1,265 executions (7 files x 176, 2 x 3, 4 x 2, 19 x 1). All 16 error logs and all 4 carrier logs are in it |
| Import | j2 and j1 scratch corpora, 0 failed, 0 degenerate, 0 `adapter_defect`; raw objects 1,329 = 32 containers + 32 headers + 1,265 members |
| Validation | 1,265 passed, linkage 100 %; shacl not in this build |
| Recompute | `--dry-run` 1,265 identical, 0 unexplained |
| Determinism | j2 vs j1: 5,131 files each, 0 differ, index identical |
| Verify chain | 0 failed (`checksums.absent`: working tree) |
| Status / completeness | ok 1,247 / ok_with_issues 18; verified_complete 1,247, known_incomplete 15 (missing_tool_result, regen item 11: PC-06), unverifiable 3 (`no_execution_observed`, enCup error log) |
| A2 / issues | index codes: sample_limit 40, unmapped_event 22, missing_tool_result 15, dangling_source_ref 15, no_execution_observed 3; seal entries dangling 68, missing_tool_result 68, unmapped_event 26. 22 errored samples (provider/limit errors) each map to an execution |
| A3 PROV | 424,729 statements; 0 dangling, invented or unexecuted classes; `time_not_run_scope` 25,928 (informational) |
| Evidence classes | core D 130,094 / O 106,800 / none 3,959; inference I 13,116 (twins 11,499; native 0; mixed 0); assessment D 44,962 / I 18,242 / O 2,530 / none 10,324. `_unverified` twins in 1,265/1,265 PROV files (H-15). Item-16 rule cited in 518 executions, 1,266 messages, all evf D |
| Safety net | 6 rows, all UNCLASSIFIED (no `inspect.art.*` scoped here): PC-05 |
| Identity | gpt-4o 1,247, gpt-5-nano 8, claude-opus 10; L1-to-AER 0 mismatches; suites as L1; `attack_id` None in 1,265 (D-184); judgements 2 per value (CD-24, PC-07). Raw = mapped outcomes in 32/32 labels |
| Redaction | users-dir named in AER 25 executions (2 distinct, ext tracebacks + `carrier_query_path` only), SEM 0, PROV 0: PC-01. home-dir named (3 distinct, disjoint from users-dir) in AER 138 / PROV 123 executions: benchmark content (CC-03). Operator 0. AER secret shapes: 48 generic-credential substrings, 0 whole |
| Withholding | policy null; nothing withheld (D-186 (c)) |
| CC-07 | not applicable (Inspect AgentHarm, no AgentDojo checker; #181/#161: 0 of 0) |

| Hyp | Status | Evidence (short) |
|---|---|---|
| H-01 | supported | all counts as section 2 |
| H-02 | partly | tree counts yes; `effd5de` not in the depth-1 cache |
| H-03 | not tested | spot JSON logs not read (follow-up) |
| H-04 | supported | 164/164 ok |
| H-05 | supported (sample) | AER offsets Z 61,779, +00:00 944, other 0 |
| H-06 | partly | 0 `accounting_inconsistent`; item-16 in 518 sampled |
| H-07 | supported (count) | 4 judgements per AgentHarm sample, 2 per retrieve |
| H-08 | supported | 25 AER executions, ext only, 0 SEM/PROV |
| H-09 | supported | 136 x 1, score `C` 136/136 |
| H-10 | supported | refusal 42.0-44.9 %, harm 47.1-50.4 % |
| H-11 | supported | full share 39.2 % (j8Rs), 36.9 % (W6Si) |
| H-12 | supported | router refusal 83.5 % vs 43.6 % (+39.9 pp) |
| H-13 | not tested | 6PzM not sampled |
| H-14 | supported | 22 errors in 16 error logs; claude 0 tool calls |
| H-15 | supported | twins only, item-16 at D |
| H-16 | partly | 0 byte-identical; uuids not tested |
| H-17 | partly | PC-03 (verifier: 14 key shapes in 6PzM only, delimited, not real formats) |
| H-18 | supported | kexin 49, survey 0 |
| H-19 | refuted | PC-04 |

## 6. Outcome comparison

Gap rule: more than 15 pp, or a 95 % interval that excludes the reference by more than 5 pp. Every reference is loose (prereg section 3): the logs use a different split and scorer version.

| Arm | Level | n | Metric | Rate (95 %) | Reference | Gap (pp) | Verdict |
|---|---|---:|---|---|---|---:|---|
| gpt-4o harmful default (4 logs) | L1 | 704 | refusal | 0.436 [0.400, 0.473] | 0.489 AgentHarm T9 | -5.3 | within |
| gpt-4o harmful default | L1 | 704 | full-score share | 0.365 [0.330, 0.401] | 0.386 FragFuse TSR | -2.1 | within |
| gpt-4o harmful default | L1 | 704 | harm score | 0.487 | 0.484 | +0.3 | within |
| gpt-4o harmful default (3 sampled logs) | L2 | 300 | non-refusal harm | 0.822 [0.788, 0.855] | 0.901 | -7.9 | within (excludes by 4.6) |
| gpt-4o benign default | L1 = L2 | 176 | benign score | 0.810 [0.770, 0.850] | 0.899 | -8.9 | within (excludes by 4.9, borderline) |
| gpt-4o harmful router (2 logs) | L1 | 352 | refusal | 0.835 [0.793, 0.870] | none | - | no reference |
| gpt-5-nano benign (1 full log) | L1 | 176 | score / refusal | 0.672 / 0.045 | none | - | no reference |

0 flagged gaps. Mean-score intervals are normal-approximation; rates are Wilson.

## 7. Findings

| Id | Class | Sev | Sec | Title | Verdict |
|---|---|---|---|---|---|
| PC-01 | source-defect (CC-12a, reclassified 2026-10-21 from mapping-defect: no D-182 table was declared, so no declared rule missed it; CC-03, D-182) | S0 | yes | third-party /Users path in AER ext of 25 executions; no D-182 redact table | confirmed (independent regex pass: AER 25 / 2 named / 0 operator, SEM 0, PROV 0; profile has no `redact` at HEAD or origin/main; `HARNESS_POINTERS` covers every pointer) |
| PC-02 | source-defect (CC-11) | S2 | yes | third-party /Users path in 164/164 raw logs; D-186 (c) predates the 2026-10-15 decision | confirmed (164/164; execution raw, not context; D-186 (c) names fragfuse and stands unless the user rules otherwise; same question as kexin PC-01) |
| PC-03 | expected-known (CC-13 fixture, D-188; security kept until the 6PzM import shows whether PROV `apv:args` holds the shapes) | S3 | yes | API-key-shaped strings (1 distinct value per shape) in 1 unsampled artefact (6PzM) | confirmed, corrected (raw check via `agentprov.ingest`: 14 in 6PzM, 0 in W6Si; delimited, length withheld match no real key format; benchmark tool content) |
| PC-04 | documentation-mismatch | S3 | no | run1/logs.json lists 4 logs absent from the tree | confirmed (h19 re-run; ids searched tree-wide) |
| PC-05 | documentation-mismatch (CC-09 analogue) | S3 | no | no `inspect.art.*` scoped to this profile | confirmed |
| PC-06 | expected-known (regen item 11) | S3 | no | 15 known_incomplete; R-H4 figure stale | confirmed (item 11 in `LOSS_CODES`; population 23 is a projection) |
| PC-07 | expected-known (CD-24) | S3 | no | duplicate judgements, 1,237 executions | confirmed, corrected (1,237 not 1,243) |
| PC-08 | analysis-artefact (R5) | S3 | no | l2_check: no Inspect outcomes, no account-kind split | confirmed |

Proposed `artefacts.toml` entry (PC-04): `inspect.art.eval_set_listing_missing_logs`, scope `fragfuse-agentharm`, 4 listed logs absent, S3, disclosure only. PC-05: widen `inspect.art.sample_limit` (74), error logs (20), missing_tool_result (23) to this profile.

AGENTS.md section 12: PC-01 (AER carries a third-party path until the profile's D-182 table exists); PC-02 (decision D-186 (c) vs CC-11).

## 8. Recommendations and readiness

**Readiness: `blocked`.** PC-01 is S0 and security-relevant: report it to the orchestrator now. Two things unblock the part: (1) declare the D-182 redact table in `fragfuse-agentharm@1` (error tracebacks in scope and event ext, `sample_metadata.carrier_query_path`), then confirm with a scratch L2 redaction re-check that AER holds 0 users-dir paths; (2) a user decision on PC-02, because withholding under CC-11 would remove every log. After that the part is ready-with-caveats (PC-03 release-scan triage, PC-04..PC-07 disclosures). Verifier (2026-10-21): readiness `blocked` confirmed; PC-01 is the known D-182 gap (fragfuse owner to add its table), still S0 until it lands; PC-02 defaults to D-186 (c) unless the user rules that the 2026-10-15 raw-store decision covers execution raw; PC-03 is benchmark content (no escalation); 0 outcome gaps re-checked (benign 0.850 upper bound vs 0.899: excludes by 4.9 pp, below 5). No data is to be excluded because of its outcomes.

## 9. Reproduction

```bash
W=~/.agentprov/migration-work/precheck/fragfuse-agentharm; S=docs/reports/precheck/data/fragfuse-agentharm/exam-scripts
uv run python -I $S/aer_pass.py $W/l2-logs-j2.partial $W/exam/aer-pass.json
uv run python -I $S/item16.py $W/l2-logs-j2.partial
python3 -I $S/os1.py $W/l1-units-logs.jsonl docs/reports/precheck/data/fragfuse-agentharm/os1-population.json
python3 -I $S/os2.py $W/exam/aer-pass.json $W/l1-units-logs.jsonl docs/reports/precheck/data/fragfuse-agentharm/os2-sample.json
uv run python -I $S/h19.py ~/.agentprov/cache/git/github.com/zixin22/fragfuse_agentharm.git 24cc8aea1b9906bee20fb585007410a5d885933a
(cd docs/reports/precheck/data/fragfuse-agentharm && python3 -I exam-scripts/build_exam.py)
# verifier (2026-10-21)
python3 -I $S/verify_acct.py $W/l2-logs-j2.partial      # PC-01: aer 25 / 2 distinct / operator 0; sem 0; prov 0
GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file uv run python -I $S/verify_keys.py ~/.agentprov/cache/git/github.com/zixin22/fragfuse_agentharm.git 24cc8aea1b9906bee20fb585007410a5d885933a 6PzMcRjszwr8LhgRycCoUx W6SirB9eRkhSi8ivuCAbwf   # PC-03
# follow-ups (not run; heavy, through the queue)
# PC-03 (verifier, done at raw level; W6Si holds no key shape): optional scratch import of 6PzM only, then aer_pass:
#   uv run python tools/suite_queue.py --class import --cpu 2 --label precheck-fragfuse-agentharm -- uv run python tools/precheck/l2_import.py --source fragfuse-agentharm --part logs --labels <the 2 labels> --out $W/pc03.partial
# H-03: agentprov inspect --view detect on the 3 inspect_logs_spot JSON logs (sample counts)
```
