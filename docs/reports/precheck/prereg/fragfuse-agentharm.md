# Pre-registration: `fragfuse-agentharm`

| | |
|---|---|
| Corpus | `fragfuse-agentharm` (restricted-use class: MIT + AgentHarm use clause, LIC 3, D-144) |
| Parts | `fragfuse-agentharm · logs` (family `inspect`, profile `fragfuse-agentharm@1`, semantics `inspect.agentharm@2`, dialect `inspect.eval` v2; registry `planned`) |
| Wave / kind | Wave 4; **first examination** (not in FA or E2; only phase-10h scratch trial imports exist) |
| Code | `065b0d36` or later on `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Inputs: desk research (`../data/fragfuse-agentharm/research.json`, URLs there) and our prior reports only. No raw data read, nothing computed from it |

Sources used: GitHub API (repo, 2 commits, compare `effd5de..24cc8aea`, recursive tree at the pin, issues); `tasks10/readme.txt`
and two author summary JSONs at the pin; arXiv 2606.15609 v1 (FragFuse) and 2410.09024 v3 (AgentHarm) HTML; Zenodo API
(concept 20337559, records 20337560 and 20387340, zip listings); inspect_ai / inspect_evals commits and the AgentHarm changelog;
`docs/reports/phase10h/` (README, routing, redaction-design); `~/.agentprov/migration-work/phase10h/census/` (census.json,
map-census*.json: our prior census, read as a report); DECISIONS D-180..D-188, D-186 decision (c); regen-batch items 12, 16, 25;
review-core-d CD-24/CD-25; profile, registry, `artefacts.toml`, `tools/readme_corpora.toml`, `tools/precheck/l1_families.py`.

## 1. Expected counts

| Quantity | Expected | Source |
|---|---|---|
| Pin | `zixin22/fragfuse_agentharm@24cc8aea` (2026-05-24, HEAD on 2026-10-14), 3,847 blobs, 318,827,530 B | profile pin; GitHub tree API (not truncated) |
| `.eval` files | 168, 49,874,989 B: `logs_archive/` 26 + `logs_archive/agentharm_2025-12-30_run1/` 2, `retrieve_test_logs_memory/task_<id>/` 136, `carrier_inject_eval/task_[test_]1-1/` 4 | tree API; census.json |
| Selected / excluded | 168 match `include`; 4 `none/none` logs excluded by exact path, `select.not_execution_artefact` (12 samples, D-183) → **164 imported** | profile `[import]`; trial |
| Not selected (outside `include`) | everything else, notably **3 Inspect JSON-format logs** `inspect_logs_spot/*_agentharm_*.json` (56,448,377 B) and `run_spot_terminal.txt`; eval-set listings `logs.json`, `eval-set.json`, `.eval-set-id`; declared but inert context artefacts: 136 `bank_records/*.jsonl` (106,216,807 B), 136 `guardrail_decision.json` | tree API; profile; R-H3 |
| Header status | 148 success, 20 error (16 real-model error logs, 24 samples) | census |
| Samples (units) | 1,759 in all; **1,747 real-model = registry count** (basis census); `epoch` 1 only | `tools/readme_corpora.toml`; census; D-181 |
| Raw objects / members | 2,075 raw objects = 164 containers + 164 `header.json` + 1,747 sample members (1,911 members) | phase-10h trial `verify --level chain` |
| Executions (AER) | **1,747**; failed 0; degenerate 0 | trial; item-16 re-measurement |
| Status / completeness (current code) | ok 1,721 / ok_with_issues 26; verified_complete 1,744 / unverifiable 3 (`no_execution_observed`) | routing R-H4 (item 16 scratch import at `bfa1951`) |
| Seal issues (current code) | `accounting_inconsistent` 0 (was 693); `inspect.sample_limit` 74; `missing_tool_result` 23; `dangling_source_ref` 23; `inspect.unmapped_event` 24 (logger 7 events, error events); `no_execution_observed` 3 | routing R-H4 |
| Tool use | 1,064 real samples with a tool call; 5,645 calls of 80 tools | census |
| Sample errors | 34 incl. 12 `none/none` → 22 real | map-census (run_status `error` 34) |
| Category facet (all 1,759) | Copyright 216, Cybercrime 180, Disinformation 210, Drugs 182, Fraud 219, Harassment 217, Hate 181, Sexual 218, none 136 (retrieve) | census `counts.category` |
| Text-equal message lists | 186 groups within fragfuse; 1,469 distinct message digests among 1,747; 49 cross-source groups with kexin; 0 with the survey | census; D-181 |
| Secret-like strings (raw) | 166, all inside longer tokens (terminal tool 2; gpt-5-nano encrypted `reasoning` 25 in messages, rest event copies), none in a header | D-188 |
| Account paths in AER (current code, no `redact` table) | 25 AER files: `ext` tracebacks (22 samples) + `carrier_query_path` (4), one sample both; 0 in SEM/PROV/index/register | phase-10h trial scan |

## 2. Expected arms

Facets (L1/L2 strata, `l1_families.py`): experiment × model × task; also split, solver plan and producer. No attack id and no
defence are declared (D-184).

| Experiment | Model (agent) | Task / split | Logs | Samples | Notes |
|---|---|---|---:|---:|---|
| logs_archive | gpt-4o-2024-08-06 | `agentharm` harmful | 7 | 1,059 | 6 full logs: default plan ×4 (3 at 0.3.154.dev37, 1 at 0.3.159.dev20 / revision `<account-D>`), `mode_router`/`save_router` ×1, `pre_router`/`post_router` ×1; + 1 error log of 3 |
| logs_archive | gpt-4o-2024-08-06 | `agentharm_benign` | 4 | 354 | 2 full (default, `mode_router`); 2 error logs of 1 (dev20, `pre_router`) |
| logs_archive | gpt-5-nano | `agentharm_benign` | 7 | 184 | 1 full + 6 error logs (8) |
| logs_archive | claude-opus-4-1-20250805 | harmful / benign | 3 / 3 | 5 / 5 | all error logs; 2 of them in `run1` |
| logs_archive | none/none | harmful / benign | 2 / 2 | 6 / 6 | **excluded** (D-183) |
| retrieve | gpt-4o-2024-08-06 | `tasks10_retrieve_test` (memory-bank injection) | 136 | 136 | one sample per task id; scorer `always_ok`; 0.3.158 |
| carrier | gpt-4o-2024-08-06 | `task` (carrier injection) | 4 | 4 | task 1-1 ×2, test 1-1 ×2; 1 error; 0.3.159.dev20 |

Judge: openai/gpt-4o-2024-08-06 (refusal + semantic) in the 32 AgentHarm/carrier logs (= agent model, separated by spans);
none in the retrieve logs. Task version `1.0.0` (inspect_evals `d9787f49`, 2025-12-16) in the 32; `0` in the 136.

**Expected missing (vs the FragFuse paper):** GPT-5.1 and Gemini 2.5 Flash; every access-control arm (LLM-AC, ShieldAgent;
baseline and FragFuse) and the 176-task attack runs of Table 1 (present only as `iteration_4/*.json` outputs, not Inspect
logs); 40 of the 176 task ids in the retrieve experiment (136 passed the first guardrail). Also missing within the
logs: gpt-5-nano harmful, any finished claude-opus run. **Expected extra:** gpt-5-nano, claude-opus-4-1, the memory-agent
router variants, the retrieve and carrier tests, eval-set retries (same eval id at two times), and possibly the
`inspect_logs_spot` JSON logs (not selected).

L2 strata (7): carrier 4 (all) + 6 strata × 5 → **34 sampled executions** (`allocate`; the excluded none/none stratum is
not drawn).

## 3. Expected outcome rates (reference for L2)

No logged arm is a paper arm, so every comparison is a loose reference; with ≤ 5 per stratum, Wilson intervals only and no
verdict (README §4: no arm reaches 20).

| Arm (logged) | Reference | Value | Where |
|---|---|---|---|
| gpt-4o harmful, default plan | AgentHarm GPT-4o, no attack: harm score / refusals / non-refusal harm | 48.4 % / 48.9 % / 90.1 % | AgentHarm v3 Table 9 (paper's 264-behaviour public test, not the 176-sample split logged here; corrected caveat) |
| gpt-4o harmful, default plan | FragFuse InspAgent, GPT-4o direct querying, no access control: TSR | 38.6 % (= 68/176) | FragFuse Table 1, Table 18 |
| gpt-4o benign, default plan | AgentHarm GPT-4o benign non-refusal score | 89.9 % | AgentHarm v3 Table 9 |
| gpt-4o harmful/benign, router variants | none | — | — |
| gpt-5-nano benign; claude-opus | none (not in either paper) | — | — |
| retrieve (136) | no outcome in the log (`always_ok`); author's guardrail on the retrieved instruction: 77 allowed / 59 blocked-or-error; retrieval exact match 77/77 | — | `tasks10_outputs/retrieve_guardrail_summary.json`, `retrieve_rate_summary.json` |
| carrier (4) | none | — | — |

Not comparable: FragFuse BSR/TSR/E2E-SR under LLM-AC or ShieldAgent (Table 1/18: e.g. GPT-4o LLM-AC + FragFuse 45.5/25.0,
ShieldAgent + FragFuse 82.4/17.2) — no access-control arm is logged.

**Metric mapping.** `scores.combined_scorer.value.score` → judgement `combined_scorer.score` → SEM `inspect.harmful_task_score`
/ `inspect.benign_task_score`; `.refusal` → `inspect.refusal`. Harm score = mean score; refusals = mean refusal; non-refusal
harm = mean score where refusal = 0. FragFuse TSR is a GPT-4o-judged success share whose mapping to the AgentHarm score is not
stated ("standard scoring-to-metric mapping"); candidate: share with score = 1.0 (`avg_full_score`). All logged scores are
inspect_evals 1.0.0 semantics (before the #2107, #2101, #2146 fixes and changelog 7-B for #2108, which is still open upstream; corrected). At `065b0d36` CD-24 duplicates each judgement (see §4);
L2 reads the `combined_scorer.*` values once per sample.

## 4. Known quirks (expected-known)

| Id / decision | Expected |
|---|---|
| profile quirk `inspect.mock_model_runs` / D-183 | 4 logs, 12 samples excluded |
| profile quirk `inspect.error_logs` | 20 error logs (incl. the 4 mock); finished samples kept |
| profile quirk `inspect.sample_limit` (`inspect.art.sample_limit` scope is the survey only) | 74 samples |
| profile quirks `event_order_not_time_order`, `attachment_refs`, `tool_span_separate_from_tool_event`, `judge_model_separate_from_agent` | present (counts not catalogued for this profile) |
| `artefacts.toml` | the 9 `inspect.art.*` ids are scoped to `survey-agentharm`; **none is scoped to this profile** (expected counts here are not catalogue gates) |
| D-184 / R-H3 | `task.attack_id` unrecorded for all 1,747; arm only in `eval.task`, plan and `ext.inspect.sample_metadata`; context artefacts not stored |
| Item 16 (`inspect.tool_event_message_id_first_of_batch@1`, D at `1289c1ad`/`3ddd7997`) | 693 samples (620 + 73) linked by call id; `accounting_inconsistent` 0 |
| Item 12 / U6 (D-374/D-375) | producer not `53c1fa98` → `_unverified` twins (I) in all 1,747 |
| CD-24 (RD-2, open) | ScoreEvents without `scorer`: judgement named `score` + a second bench-attributed judgement per value (2 per value) |
| CD-25 (RD-2, open) | fires only for non-UTC offsets (expected none here) |
| D-182 (implemented; profile table absent) | account paths copied into AER `ext` for 25 executions (security-relevant, known) |
| D-186 decision (c) | raw with account paths ships as is; no `[withhold]` |
| D-188 | 166 secret-like substrings, none whole |
| R-H2 | n/a here (no unfinished logs) |

## 5. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §1; selected 164 / excluded 4 / outside include incl. `inspect_logs_spot` (H-03) |
| L1-02 strict parse | yes | all `header.json` and sample members of the 168 logs |
| L1-03 encodings | yes | Chinese text possible in harness/attack material; expect 0 bidi/tag/U+FFFD/mojibake |
| L1-04 duplicates | yes | within part (186 text-equal groups, 0 byte-identical expected), cross-corpus with kexin and survey |
| L1-05 arm coverage | yes (experiment × model × task × split, plan variant) | §2; defence facet n/a |
| L1-06 secrets/paths | yes | counts and pointers only (H-08, H-17) |
| L1-07 timestamps | yes | H-05 |
| L1-08 degenerate | yes | error-only samples (H-14) |
| L2 A2 error classes | yes | provider errors, message limits |
| L2 A3 PROV classes | yes | item-16 links, CD-24 duplicates, unexecuted calls |
| L2 evidence classes | yes | H-15 |
| L2 degenerate / `adapter_defect` | yes | expect 0 |
| L2 identity | yes | 3 agent models + judge; bench `agentharm` task version 1.0.0; attack id unrecorded (known) |
| L2 redaction | yes | **expected to show account paths in AER `ext`** for sampled error/carrier samples (H-08) |
| L2 withholding | no | no `[withhold]` table (D-186 (c)); check nothing is withheld |
| L2 outcome sanity | Wilson only | §3; no verdicts |
| L2 determinism | yes | second import with other `--jobs`, byte-identical |
| Delta since E2 | no | not an E2 corpus; §7 states movement against the phase-10h trial |

## 6. Hypotheses (falsifiable, thresholds)

| Id | Lead | Expectation | Fails if |
|---|---|---|---|
| H-01 | — | 168 `.eval`; 164 selected + 4 excluded; 1,747 + 12 samples; 148 success / 20 error headers; per-arm logs/samples exactly as §2 | any count differs |
| H-02 | — | pin tree 3,847 blobs / 318,827,530 B; 164 `.eval` blobs identical to commit `effd5de` and 4 carrier logs new at the pin | otherwise |
| H-03 | L-02 | the 3 `inspect_logs_spot/*.json` are Inspect JSON-format logs with ≥ 1 sample each, are not selected, and are not counted in 1,747 → finding (documentation-mismatch, S2: undisclosed executions; scope decision) | they are not Inspect logs or hold 0 samples (then no finding) |
| H-04 | — | strict parse: 0 failures of any class | ≥ 1 |
| H-05 | L-08 | every event/sample timestamp is `Z` or `+00:00` (producers ≥ 0.3.151) | any other offset (→ CD-25 applies; mapping-defect, known) |
| H-06 | L-06 | parallel batches: 620 samples / 1,617 of 5,078 events (0.3.154.dev37), 73 / 155 of 567 (0.3.159.dev20), 0 (0.3.158); AER: 0 `accounting_inconsistent` | any count differs or ≥ 1 inconsistent |
| H-07 | L-07 | 0 ScoreEvents with a `scorer` key; AER judgements per sample = 2 × score values (CD-24) | a `scorer` key present, or judgement count ≠ 2× |
| H-08 | L-09 | raw: account path in `dataset.location` 28 logs, memory-bank solver param 136 logs, tracebacks 34 samples (22 real), `carrier_query_path` 4; AER: 25 executions, `ext` pointers only; 0 in SEM/PROV | any account segment in another AER pointer class or in SEM/PROV (→ S1 security finding, report at once) |
| H-09 | L-04 | 136 retrieve logs, 1 sample each, 136 distinct task ids, every score the constant `always_ok` value | any differs |
| H-10 | L-03 | the 4 default-plan gpt-4o harmful logs: header refusal rate within ±15 pp of 48.9 % and harm score within ±15 pp of 48.4 % | outside (S2 documentation note, not a verdict: different prompt/version) |
| H-11 | L-03 | one header metric of a default-plan gpt-4o harmful log (`avg_full_score` first) is within ±2 pp of 38.6 % (FragFuse TSR) | none within (then the paper's TSR is not reproducible from the logs; S3 note) |
| H-12 | L-05 | router-variant logs: refusal rate ≥ 20 pp above the default-plan mean (census: 31 and 28 tool-using samples of 176 vs 117-122) | < 20 pp |
| H-13 | L-10 | gpt-5-nano: assistant messages with reasoning parts > 0 and refusal explanations never quote reasoning (#2107); benign `grade_setup_meeting_location` score 1.0 in 0 samples (#2101) | otherwise |
| H-14 | L-15 | 22 real samples with a sample error, all in the 16 error logs; claude-opus 10/10 errored before a tool call; each maps to an execution, 0 degenerate | otherwise |
| H-15 | L-11 | item-12/U6 rules cited only through `_unverified` twins in 1,747/1,747; item-16 rule at D in the 693 affected samples | any D citation of an item-12 rule |
| H-16 | L-12 | sample uuids distinct across all 168 logs; 0 byte-identical sample members; retried eval ids (4 pairs) hold different samples | ≥ 1 identical |
| H-17 | L-14 | 166 secret-like substrings, 0 whole tokens, 0 in headers; 0 secret-shaped whole tokens in AER | otherwise |
| H-18 | — | 0 sample message lists equal to the survey's 1,056; 49 text-equal groups with kexin (short refusals / errors), none byte-identical | otherwise |
| H-19 | L-12 | every log named in `logs_archive/logs.json` and `run1/logs.json` exists in the tree | a listed log missing (S3: partial upload) |

## 7. Expected movement (not a delta corpus)

No FA/E2 baseline. Against the phase-10h trial (`fragfuse-j8`, pre-item-16) the current code is expected to differ by:
item 16 (693 executions: AER/SEM change, `accounting_inconsistent` → 0, `known_incomplete` → `verified_complete`);
items 12/U6 (harness/runtime actors and attributions via `_unverified` twins, every AER); D-31 catalogue bumps and
adapter-code digest (every AER/PROV); D-182 code present but inactive (no profile table); CD-24 and CD-25 **not** yet
applied. Expected unchanged: counts in §1, the 74/23/23/24/3 issue counts, raw member digests (only `fn_digest`/`limits_sha256`
move).

## Fact-check (2026-10-14, adversarial, desk only)

Re-opened every cited source; no payload downloaded, no raw data read, nothing computed from the data.

| Checked | Verdict |
|---|---|
| FragFuse arXiv 2606.15609: v1 only (2026-06-14, 3,561 KB), USENIX Security 2026; Open Science cites `zixin22/Fragfuse` and Zenodo 20337559 | confirmed |
| FragFuse Table 1 / Table 18 InspAgent rows (direct TSR 38.6/13.6/22.7; LLM-AC, ShieldAgent, + FragFuse BSR/TSR/E2E-SR) and Table 9 (32.0 vs 34.5) | confirmed (all values) |
| AgentHarm v3 Table 9 GPT-4o 48.4 / 48.9 / 90.1, benign 89.9 | confirmed; **caveat added**: computed on the paper's 264-behaviour public test, while the logs use the 176-sample inspect_evals split |
| Pin `24cc8aea` = HEAD, 2 commits; tree 3,847 blobs / 318,827,530 B; 168 `.eval` / 49,874,989 B; `inspect_logs_spot` 3 JSON / 56,448,377 B | confirmed (GitHub tree API, not truncated) |
| `effd5de..24cc8aea`: 4 carrier `.eval` added, 164 unchanged | confirmed; **corrected** in research.json: 5 files removed (also `step1_terms_calculation.txt`), not 4 |
| Licences at the pin (MIT UK AISI 1,081 B; AgentHarm MIT + safety-use clause 1,239 B) | confirmed |
| Zenodo 20337560 / 20387340 sizes, md5, dates, CC-BY-4.0; 124/125 overlapping paths equal in size | confirmed; resource type is software (computational notebook) |
| inspect_ai producer commits/dates, 0.3.217 `scorer` on ScoreEvent, 0.3.151 naive datetimes; inspect_evals `d9787f49` 2025-12-16 and changelog 1.0.1..8-B | confirmed; **corrected**: #2108 is still open upstream (7-B carries the fix) |
| Repo issues (10 dependabot), no tags/releases; `Fragfuse` unlicensed; co-author repo 404 | confirmed |
| Author summaries 77/59 of 136, retrieval 77/77 | confirmed |
| §1/§2 counts against phase-10h README/routing, census, `readme_corpora.toml`, profile | confirmed (arm sums: 1,759 samples, 20 error logs, 24 error-log samples) |
| Parallel-batch defect range 0.3.113..0.3.263; per-log task version / account-path counts; FragFuse TSR ↔ header metric | unverifiable here (our reports only / not stated in the paper) |

No hypothesis threshold was changed and no expectation was added from data.
