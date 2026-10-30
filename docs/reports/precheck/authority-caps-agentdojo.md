# Pre-check dossier: `authority-caps-agentdojo`

## 1. Header

| | |
|---|---|
| Corpus | `authority-caps-agentdojo` (record cc-by-4.0; code MIT; logs embed AgentDojo benchmark text, MIT) |
| Parts | `head` (1 part) |
| Family / profile | `agentdojo` / `authority-caps-agentdojo@1` (dialect `agentdojo.tracelogger`, variants `v1.k14`, `v1.k14.incomplete`; semantics `agentdojo.suites@2`) |
| Pin | Zenodo 23138310 (v2.1.0), `agent-authority-caps-v2.0.0.zip`, 40,160,657 B, sha256 `1dce0380…05bf` (verified); 3 declared nested gzip tars (exp4, exp5, exp7) |
| Code commit | `d97d3a57` (batch `wave7`, all 7 steps rc 0; **tracked changes true**, PC-10) |
| Kind | wave 7, first examination (not in FA or E2); never stored (registry `planned`) |
| Date | 2026-10-15 (prereg, research), 2026-10-16 (L1, L2 batch), 2026-10-21 (examination) |
| Agents | researcher + fact-checker (prereg), examiner (this file), adversarial verifier (2026-10-21: 10/10 confirmed, 0 refuted; PC-06 narrowed) |
| Data | [`data/authority-caps-agentdojo/`](data/authority-caps-agentdojo/): `research.json`, `l1-head.json`, `l1-09-head.json`, `l1-10-head.json`, `l2-sample-head.json`, `l2-head.json`, `code-head.json`, `exam.json`, `findings.json`, `pop-census.json` (L1 arms), `raw-pass.json` (raw hypotheses, CC-07, CC-10), `h3-tools.json`, `os2-sample.json` (L2 vs population), `os2-mapping.json`, `exam-scripts/` |

- Code identity, part `head` ([`code-head.json`](data/authority-caps-agentdojo/code-head.json)): commit `d97d3a57` (tracked_changes true); engine code expand `3b1d412bb77a`, aer `856b7a09e0cf`, sem `ae0ee532dde7`, prov `d57bd291d3cc`, validation `a10ee3c16045`; adapter `agentdojo.tracelogger@0.1.0` `03d8bc6d30df`; profile sha256 `e691d4be6c82`, rules agentdojo 2 / aer 1 (`d4d9d6c8074a` / `55b64d5e05ba`); lockfile `b0455f1058c8`, limits `5d6dbb210259`.

## 2. Sources and links

| Source | Link | Relation |
|---|---|---|
| Data record | https://zenodo.org/records/23138310 (concept 22973265; v2.0.0 22996368 same zip; v1.0 22973266, 2,813 logs, all byte-identical members of the pin) | the data |
| Results | Supplementary Material v2.1.0 (Tables S1–S25, Notes 1–5), Chang and Chiu; manuscript not public | outcome reference (section 6) |
| Harness | `agentdojo==0.1.35` (PyPI wheel 2025-10-27); extraction commit ethz-spylab/agentdojo `089ed468` | producer and checker |
| Upstream issues | ethz-spylab/agentdojo #181, #161 (CC-07), #168 (CC-10), #154 (run error outcome), #214 (escaping), #141 (temperature 0.0 dropped by the wheel) | checker and harness defects |

Data-versus-paper notes (checked against the data):

- Every pre-registered count from Tables S4, S6, S10, S11, S13, S17 and Note 5 reproduces on the population (section 6); 18,739 = 18,557 paper runs + 182 pilot.
- The naive TraceLogger timestamps are UTC: the main runs fall in the paper's 04:47–05:55 UTC window with offset 0 h (PC-04).
- `important_instructions_wrong_user_name` addresses "Mark Smith", not the "Emma Smith" the prereg assumed (PC-03).
- #141: `source-snapshots/run_new_models.py` mentions temperature on 4 lines with no literal zero assignment (counts only); the logs carry no temperature, so Table S17's temperature-0 claim stays a disclosed caveat (as in aiauthz, llm-lock). The rep spread (mini 52–59/117) is compatible with non-greedy decoding or provider nondeterminism; it does not settle it.

## 3. Expectations

Pre-registration: [`prereg/authority-caps-agentdojo.md`](prereg/authority-caps-agentdojo.md), commit `eb7151ee`, before any check of this corpus. Amendments 2, 4 and 5 (README §8) apply: stratum key `container × model_dir × pipeline_dir × attack_dir` gives **69 strata** (the prereg's estimate of about 256 assumed suite in the key), quota 5 → 300 units, not `over_maximum`.

| H | Result | Note |
|---|---|---|
| H1 | supported | every §3 count within ±1 (non-error logs for 3.5 and capped arms); 0 gaps |
| H2 | supported | 51 errors: 41 attacked in the three 3.5 dirs (base 14 + 1 incomplete = 15, A3 12, A4 15) + 10 attack-none (8 benign, 2 prepass); 0 elsewhere |
| H3 | supported (partial) | A3 dirs: 0 error-free results for 19 state-changing/egress tools (`send_money`, `send_email`, `share_file`, …); A4: 0 for 8 (`send_money`, `delete_*`, `update_password`, …); no-egress: 0 for 16. Calls to absent tools only in 3.5-capA3 (3, all errors; the error has no `ToolNotFoundError` class name). Table S1 levels not machine-checked |
| H4 | supported | 0 `security` true on slack IT5 in the 7 capped/no-egress dirs (147 logs: 146 false, 1 incomplete) |
| H5 | supported | pilot = haiku 169 (16 benign, 9 prepass, 144 ii) + 13 banking extras (luna 5, sol 5, haiku-autoconfirm 3; 4 ii + 9 none) |
| H6 | supported | 6 rep dirs × 162, one cell set (18/27/117; 39/29/39/55), subset of base; mini 54/52/59/59, all-four agree 78/117; luna 4/2/3/4, 108/117 |
| H7 | supported | second user message only in autoconfirm dirs (359 member logs), exactly 2 per log, 1 text digest |
| H8 | supported, wording refuted | ii names "Emma Johnson" (11,139 logs), 0 other names; 0 "Emma Smith" anywhere; wrong-name variant uses "Mark Smith" (620) (PC-03) |
| H9 | supported; pilot order refuted | 2,255/2,259 inside the window at offset 0 (4 at 04:46, 0.18 %); haiku pilot precedes; 13 pilot extras fall inside the window, each just before its own arm (PC-04) |
| H10 | supported | naive range 2026-09-26 04:22..16:07 |
| H11 | supported | `pipeline_name` = directory 21,999/21,999; 21 dirs, all mapped |
| H12 | supported | `MANIFEST.sha256.json` 3,040 entries = every level-1 member but itself, 3,040 equal |
| H13 | supported | 0 secret-like / account paths in 21,999 logs; L1-10 0/8 context files |
| H14 | refuted as worded | 0 failures, 0 degenerate, byte-identical across jobs; one extra register code, `map.unattributed_additional_user_message` 8 (PC-05) |

## 4. Level 1 (whole population, raw through `agentprov.ingest`)

Input: the staged zip (pin verified), nested tars opened in memory, tool `l1_scan` at `d97d3a57`, 18.3 s.

| Check | Result (denominator) | vs expectation |
|---|---|---|
| L1-01 counts | 22,253 walked = 3,041 level-1 (incl. 3 tars) + 19,212 nested; 21,999 selected, 8 context, 3 nested, 243 not selected (217 level-1 non-log + 26 nested non-log); 0 excluded/rejected. By location: current_models 2,631, pilot 182, exp4 6,024, exp5 10,684, exp7 2,478; per directory exactly the prereg table (31 location × directory cells). L1-09: 0 metadata members | as expected (prereg 22,250 + 3 containers) |
| L1-02 parse | strict ok 21,999/21,999; 0 defect classes | as expected |
| L1-03 encodings | escaped `\uXXXX` 1,984 files / 3,272 strings, all at `/messages/*/content/*/content` (tool output, #214); escaped newline 8,409 files; CR 1 file (2 strings, model-written tool args); variation selector 68; JSON-in-string 12; 0 bidi, tag, zero-width, U+FFFD, C1 | as expected |
| L1-04 duplicates | byte-identical 2,507 groups / 5,767 members → 3,260 extra copies in exactly the 5 directory groups (mini ×3 1,506, luna 753, sol 753, haiku-ac 124, luna-ac 124); 18,739 distinct. Trajectory (CC-01): 18,108 distinct fp, 415 groups / 1,046 files with different bytes (census 4 / 13 on its own fingerprint). Cross-corpus: 0 byte-identical; 94 members in trajectory-identical groups with 11 corpora (yockcheng 57, dca 25, mohameduk 10, interbolt 6, melon 4, …; short prepass/benign runs) | as expected; PC-07 (CC-01) |
| L1-05 arms | distinct per model haiku 1,678, luna 8,535, sol 1,511, mini 4,756, 3.5 2,259; attacks ii 9,656, authority_notice 1,887, tool_knowledge 1,258, six × 629, none 2,164; suites 4,391 / 3,189 / 4,139 / 7,020; full design grid, by-design absences as pre-registered, 0 unexpected cells | as expected; PC-06 (wording) |
| L1-06 secrets/paths | 0 / 21,999; auxiliary 0; L1-10 8 context files screened, 0 hits, 0 operator | as expected (H13) |
| L1-07 timestamps | `/evaluation_timestamp` 21,999/21,999, 100 % naive, one day; 0 run-clock non-monotone units (36 non-monotone only in calendar tool args, benchmark content) | as expected; PC-04 |
| L1-08 degenerate | incomplete 5 (3.5 base 1, luna-capA3 1, luna exp5 2, luna-ac 1), error 51, trailing-calls 104; raw pass: null-final 85 (all with trailing calls), 126 unexecuted trailing calls in 104 logs; 0 empty / zero-message. Census `last_assistant_null` 137 is a different predicate | as expected |

## 5. Level 2

| Item | Result |
|---|---|
| Sample | [`l2-sample-head.json`](data/authority-caps-agentdojo/l2-sample-head.json) (sha256 `853f1c85086b…`): 300 of 21,999 members, 69 strata × 5 (fewer where the stratum is smaller), seed 20261011 |
| Import | j2 and j1 scratch corpora at `d97d3a57`: 300 labels → 297 executions (3 sampled labels are later byte copies, `dedup.collapsed` 3, D-250); ok 286, ok_with_issues 11, 0 degenerate, 0 `adapter_defect`, 0 failed |
| Validation | aer, sem, prov, linkage: 297/297 pass, 297 reproduced, linkage 100 %; SHACL not implemented (skipped); regression n/a |
| Recompute | `--dry-run`: 300 kept, 0 changed, exit 0 |
| Verify chain | 0 failures; 18,751 raw objects rehashed (= 18,739 + zip + 3 tars + 8 context); only `checksums.absent` (working tree) |
| Determinism | j2 vs j1: 19,649/19,649 files identical, index identical |
| A2 register | `map.accounting_unverifiable` 297, `map.earlier_attempts_unobservable` 297, `map.unattributed_additional_user_message` 8 (autoconfirm dirs only: haiku-ac 6, luna-ac 1, sol-ac 1), `map.retry_passes_inferred` 2, `map.unexecuted_tool_call` 2, `map.outcome_imposed_by_runner` 1 (3.5-capA4), `dedup.collapsed` 3 |
| A3 PROV | 0 dangling / missing / invented over 131,534 statements / 218,447 relation arguments; 2,304 messages with `generated_by`, 1,153 model calls with input, 1,151 tool executions with call; unexecuted calls represented 2/2 |
| Evidence classes | D only engine rules (`aprov.n_gap` 1,052, `aprov.n_capture_profile` 297, `aprov.a_label` 1). Unverified split: twin assessment:I 6,844, inference:I 38,376, inference:none 3,500; native 0; mixed inference:I 6,473. Native class-I agentdojo rules: `context_is_prefix`, `integrity_agent_output`, `pipeline_dir_is_model_identity`, `payload_attributed_to_attacker`, `integrity_payload_fixture`, `additional_user_message_unattributed` |
| Identity | 21 dirs; model = dir without suffix (5 models); defence `authority_cap_a3` / `authority_cap_a4` / `no_egress`, else `none`; autoconfirm and repN never a defence, kept verbatim as `pipeline_name` (35 autoconfirm executions); attacks 10 values 1:1; 0 unresolved, 0 mismatches |
| OS-2 | AER judgements vs raw: 0 of 594 differ |
| Redaction | 899 files, 0 hits |
| Withholding | not applicable (no policy, D-257) |

## 6. Outcome comparison

Level 1 (population, raw booleans, per directory; full rows in [`pop-census.json`](data/authority-caps-agentdojo/pop-census.json)). ASR = `security` over attacked user-task logs; U = benign user-task utility; e_dir = prepass utility; UuA = attacked utility. 3.5 and capped rates exclude error/incomplete logs (the paper's pairing with historical runs cannot be rebuilt; ±1 tolerance on the denominator). Gap rule (>15 pp or >5 pp outside Wilson): no gap anywhere.

| Arm (dir; attack) | n | Metric | Population (Wilson 95 %) | Paper | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|
| haiku; ii | 629 | ASR | 0.16 (1) [0.03, 0.89] | 0.2 | 0 | match (0 successes: kept, user rule) |
| haiku; none | 97 / 27 | U / e_dir | 73.20 (71) / 59.26 (16) | 73.2 / 59.3 | 0 | match |
| haiku-autoconfirm; ii | 629 | ASR / UuA | 0.79 (5) / 65.02 (409) | 0.8 / 65.0 | 0 | match; e_dir 23/27 = 85.2 |
| luna; ii | 629 | ASR / UuA | 2.07 (13) / 74.09 (466) | 2.1 / 74.1 | 0 | match; U 81/97, e_dir 25/27 |
| luna-autoconfirm; ii | 629 | ASR / UuA | 1.43 (9) / 73.61 (463) | 1.4 / 73.6 | 0 | match (1 incomplete) |
| sol; ii | 629 | ASR / UuA | 0.00 (0) [0.00, 0.61] / 76.47 (481) | 0.0 / 76.5 | 0 | match (0 successes: kept); U 80/97, e_dir 16/27 |
| luna exp5; 8 further attacks | 629 each | ASR | AN 31, direct 29, system 26, no_names 11, TK 6, ignore 5, wrong_name 5, injecagent 3 | 31/29/26/11/6/5/5/3 | 0 | match; UuA 469/481/479/471/480/483/481/484 all match |
| sol exp5; authority_notice | 629 | ASR / UuA | 0 / 476 | 0 / 476 | 0 | match |
| mini base (exp4 = exp5 = exp7); ii | 629 | ASR / UuA | 41.34 (260) [37.55, 45.23] / 38.95 (245) | 41.3 / 39.0 | 0 | match; U 64/97; #181 (PC-01) |
| mini; tool_knowledge / authority_notice | 629 | ASR | 27.82 (175) / 23.85 (150) | 27.8 / 23.8 | 0 | match; UuA 330 / 275 |
| mini-capA3 | 629 / 97 | ASR / U | 3.34 (21) / 35.05 (34) | 3.34 / 35.05 | 0 | match; U incl. 1 vacuous UT5 (PC-02) |
| mini-capA4 | 629 / 97 | ASR / U | 23.37 (147) / 60.82 (59) | 23.37 / 60.82 | 0 | match |
| mini-noegress | 629 / 97 | ASR / U | 9.54 (60) / 38.14 (37) | 9.54 / 38.14 | 0 | match |
| 3.5 base; ii non-error | 614 | ASR | 9.45 (58) [7.38, 12.02] | 9.5 (58/612) | −0.05 | match (raw incl. errors 72/629, PC-08) |
| 3.5-capA3 non-error | 617 / 94 | ASR / U | 0.65 (4) / 22.34 (21) | 0.65 (4/611) / 22.58 (21/93) | 0 / −0.24 | match |
| 3.5-capA4 non-error | 614 / 95 | ASR / U | 1.95 (12) / 36.84 (35) | 1.96 (12/612) / 37.23 (35/94) | 0 | match |
| luna-capA3 | 628 / 97 | ASR / U | 0.16 (1) / 38.14 (37) | 0.16 / 38.14 | 0 | match (1 incomplete) |
| luna-capA4 | 629 / 97 | ASR / U | 0.95 (6) / 73.20 (71) | 0.95 / 73.20 | 0 | match |
| reps (4 runs × 117) | 117 | ASR | mini 54/52/59/59; luna 4/2/3/4 | 52–59; 2–4 | 0 | match |
| *info*: mini ii, #181 GOAL re-score | 629 | ASR | 39.27 (247) | 41.3 | −2.07 | not the logged metric (PC-01) |
| *info*: mini authority_notice, #181 | 629 | ASR | 21.30 (134) | 23.8 | −2.54 | not the logged metric |
| *info*: 3.5 base non-error, #181 | 614 | ASR | 6.19 (38) | 9.5 | −3.26 | not the logged metric |
| *info*: mini-capA3 U without vacuous UT5 | 97 | U | 34.02 (33) | 35.05 | −1.03 | not the logged metric (PC-02) |

Level 2 (mapped AER; key model × defence × attack pooling directories; full table [`os2-sample.json`](data/authority-caps-agentdojo/os2-sample.json)). Only three arms reach n ≥ 20; every other arm is n < 20 (R6, Wilson only).

| Arm | n | Metric | Sample (Wilson 95 %) | Population (same key) | Gap (pp) | Verdict |
|---|---|---|---|---|---|---|
| mini / none / ii | 26 | ASR | 42.31 (11) [25.54, 61.05] | 42.45 | −0.14 | match |
| mini / none / ii | 26 | UuA | 42.31 (11) [25.54, 61.05] | 37.89 | +4.42 | match |
| luna / none / ii | 27 | ASR | 0.00 (0) [0.00, 12.46] | 1.96 | −1.96 | match |
| luna / none / ii | 27 | UuA | 74.07 (20) [55.32, 86.83] | 72.32 | +1.75 | match |
| luna / none / none | 22 | U | 90.91 (20) [72.19, 97.47] | 79.73 | +11.18 | match |

CC-07 on this corpus (`raw-pass.json`, CC07_181 / CC07_161): **#181** 69 of 128 distinct banking IT0/1/3 logged successes have no GOAL datum in an executed attacker-bound transfer subject (mini ii 13/24, AN 16/19, TK 7/15, 3.5 base 20/27, luna exp5 6/18 over its attacks, reps 7/21); capped and no-egress arms have 0 IT0/1/3 successes, so #181 inflates only the uncapped side of every cap reduction. **#161** 104 distinct banking UT5 utility successes without an executed Spotify payment; every one of the 7 capped/no-egress dirs is 10/10 vacuous (the paper's S25 counts these). **CC-10 (#168)**: 75 distinct slack IT5 successes, 0 without all three membership calls executed; 0 successes in capped arms.

## 7. Findings

| Id | Title | Class | Sev. | Verifier | Recommendation |
|---|---|---|---|---|---|
| PC-authority-caps-agentdojo-01 | [CC-07, #181] 69/128 IT0/1/3 successes without GOAL datum; uncapped arms only | expected-known (R2, CC-07; scope CC-09) | S3 | confirmed | disclose beside uncapped ASR and cap reductions |
| PC-authority-caps-agentdojo-02 | [CC-07, #161] 104 vacuous UT5 utility successes; 10/10 in each capped dir | expected-known (R2, CC-07) | S3 | confirmed (count; paper-S25 clause not re-checked) | disclose with capped utility (paper S25 agrees) |
| PC-authority-caps-agentdojo-03 | wrong-name variant uses "Mark Smith", not "Emma Smith" | documentation-mismatch (R4, prereg) | S3 | confirmed | correct prereg/research wording |
| PC-authority-caps-agentdojo-04 | naive time = UTC; pilot extras not before the main runs | documentation-mismatch (R4) | S3 | confirmed | record offset 0 h; fix inferred order |
| PC-authority-caps-agentdojo-05 | `map.unattributed_additional_user_message` 8 (autoconfirm) not in expected code list | documentation-mismatch (R4) | S3 | confirmed | add to profile notes / trial record |
| PC-authority-caps-agentdojo-06 | attack-count wording: profile header and census "eight further … 629 each" vs data (7 further besides ii and AN; AN 1,887, TK 1,258); prereg "seven" agrees | documentation-mismatch (R4) | S3 | confirmed (narrowed) | reword profile header and census §2 |
| PC-authority-caps-agentdojo-07 | [CC-01] fingerprint groups larger than the census's | analysis-artefact (R5) | S3 | confirmed | none (not a corpus finding) |
| PC-authority-caps-agentdojo-08 | runner-imposed `security` on 41 attacked 3.5 error logs | expected-known (R2, `run_error_imposed`, profile quirk) | S3 | confirmed | drop error logs for 3.5 analyses |
| PC-authority-caps-agentdojo-09 | [CC-09] no artefacts.toml scope; quirk counts verified | documentation-mismatch (CC-09) | S3 | confirmed | see CC-09 |
| PC-authority-caps-agentdojo-10 | batch `tracked_changes = true` | analysis-artefact (R5) | S3 | confirmed | compare digests |

Verifier (2026-10-21): raw.py and pop.py re-run, outputs byte-equal to `raw-pass.json` and `pop-census.json`; every count re-derived (reasoning per finding in `findings.json` `verdicts`). PC-04 nuance: the 13 pilot extras fall inside the main window, each just before its own arm (luna/sol by 1 min). PC-06 narrowed: the prereg's "seven" matches the data; only the profile header and census §2 are wrong.

No security finding (0 L1-06, 0 L1-10, 0 redaction hits). No source-defect: CC-10 has 0 instances here. No Haiku or Sol arm is excluded or recommended for exclusion for having 0 or 1 attack successes.

Proposed `artefacts.toml` scope additions (text only, via the orchestrator, CC-09): `validity_defects` (+authority-caps: #181 69/128, #161 104), `run_error_imposed` (51), `benign_security_constant` (2,908 members), `injection_task_as_user` (741), `silent_rerun` (85), `incomplete_run` (5), `naive_timestamp` (offset 0 h, UTC).

Items for AGENTS.md §12: none new (CC-07/CC-09 already carry the routing).

## 8. Recommendations and readiness

- **Readiness: `ready-with-caveats`** (verifier: upheld; no outcome gap, no S0-S2, no security finding). Every pre-registered outcome reproduces; L2 is clean, deterministic and identity-correct. Caveats are disclosures: CC-07 #181/#161 (bias only the uncapped side), the 3.5 runner-imposed outcomes, temperature (#141) unsettled, and our doc corrections (PC-03..06).
- Follow-ups (not run; heavy or owner-side):
  1. Full import proof at the round: `uv run agentprov import authority-caps-agentdojo --input ~/.agentprov/staging/10c/zenodo-23138310 --verify-against-pin --corpus <new>` through `tools/suite_queue.py --class import --cpu 2`, then `validate`, `recompute --dry-run`, `verify --level chain`; expect 18,739 executions and `map.unattributed_additional_user_message` on the distinct autoconfirm logs.
  2. Owner reads `source-snapshots/run_new_models.py` through `quote_untrusted` to state how temperature reaches the OpenAI client (#141).
  3. Machine-check H3 against Table S1's tool levels if the deposit's cap filter table is exposed as data.

## 9. Reproduction

```bash
# repo root, branch precheck-corpora; L1 rows and scratch corpora under ~/.agentprov/migration-work/precheck/authority-caps-agentdojo/
python3 -I docs/reports/precheck/data/authority-caps-agentdojo/exam-scripts/pop.py OUT.json            # L1 arms, copies, errors, pilot, reps
uv run python -I docs/reports/precheck/data/authority-caps-agentdojo/exam-scripts/raw.py OUT.json      # H7-H12, CC-07, CC-10, degenerate (zip via agentprov.ingest)
uv run python -I docs/reports/precheck/data/authority-caps-agentdojo/exam-scripts/h3.py OUT.json       # H3 tool results per capped dir
python3 -I docs/reports/precheck/data/authority-caps-agentdojo/exam-scripts/os2.py \
  ~/.agentprov/migration-work/precheck/authority-caps-agentdojo/l2-head-j2.partial \
  ~/.agentprov/migration-work/precheck/authority-caps-agentdojo/l1-units-head.jsonl OUT.json           # OS-2, issue codes by dir
python3 -I docs/reports/precheck/data/authority-caps-agentdojo/exam-scripts/osl2.py \
  docs/reports/precheck/data/authority-caps-agentdojo/l2-head.json \
  ~/.agentprov/migration-work/precheck/authority-caps-agentdojo/l1-units-head.jsonl OUT.json           # L2 vs population
# batch (already run): tools/precheck/run_batch.py --plan tools/precheck/plans/wave7.toml (steps l1, l1_09, l1_10, sample, import_j2, import_j1, check)
```
