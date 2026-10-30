# Pre-registration: `mohameduk-agentdojo`

| | |
|---|---|
| Corpus | `mohameduk-agentdojo` (family `agentdojo`, profile `mohameduk-agentdojo` v1, dialect/mapper `agentdojo.tracelogger`, variant `v1.k14`) |
| Parts | `head` (only part) |
| Wave | 2 (first examination; not in FA or E2) |
| Code commit | `065b0d36` or later on branch `precheck-corpora` |
| Date | 2026-10-14 |
| Status | **Written before any pre-check data check of this corpus.** Sources: our prior reports (phase-10c census summaries, phase-10d census, trial, reconcile, r1 census, routing), the profile, the registry, `artefacts.toml`, DECISIONS (D-102, D-103, D-113), and desk research (`data/mohameduk-agentdojo/research.json`). Nothing here was computed from the raw logs. |
| Method | [`../README.md`](../README.md) |

## 1. Source summary

| Item | Value | Source |
|---|---|---|
| Repository | [mohameduk/agentdojo](https://github.com/mohameduk/agentdojo), fork of ethz-spylab/agentdojo, branch `ubag-gateway-defense`; MIT (upstream LICENSE text, no own line) | GitHub API, profile |
| Pin | `3f9d69a1ea96`, 2026-09-03T04:42:54Z (00:42 -0400), "Add UBAG run logs: 629 attack pairs and 97 benign tasks per arm, two models"; still the branch head | GitHub API |
| Code | upstream `089ed468` (2026-06-02) + `27206776` (UBAG defence, authored 2026-09-02 18:43 -0400) + `9de3e23a` (state-key fix, 19:20 -0400) | GitHub API |
| Run dates | 2026-09-01 15:05:54 to 2026-09-02 21:09:55 (naive), i.e. mostly before both UBAG commits were authored | phase-10c census `ts_range` |
| Defence decision | remote services (`UBAG_GATEWAY_URL`, `UBAG_BEHAVIORAL_URL`); the fork holds only the client; service version not recorded | `ubag_gateway.py` at pin |
| Paper / data record | none; results in the owner's separate repo [mohameduk/UBAG](https://github.com/mohameduk/UBAG/blob/fba207eb0bd0361aaed5828fe014bcdaa60a7866/ubag-core/README.md) (2026-09-30, gemini only) and AgentDojo issues [#188](https://github.com/ethz-spylab/agentdojo/issues/188), [#189](https://github.com/ethz-spylab/agentdojo/issues/189) (owner, 2026-09-03) | research.json |
| Harness | logs say agentdojo 0.1.35 (distribution, not code); suites v1 (benign `benchmark_version` `v1`, attacked `null`); attack `important_instructions` only | census, D-102 |

## 2. Expected counts (part `head`)

| Quantity | Expected | Source |
|---|---:|---|
| Tree entries at pin | 40,492 (464,094,691 bytes) | profile `expected_files/bytes`; phase-10c census `all_tree_entries` |
| Selected logs (`runs/*/*/*/*/*.json`, 5 new pipeline dirs) | 3,630 (35,559,371 bytes; 1,652 to 210,832 bytes per file) | registry/`readme_corpora.toml` (census `/files`); phase-10d census; GitHub tree |
| Not selected | 36,679 upstream copies (`select.owned_elsewhere`, owner `agentdojo`, 29 dirs) + 183 other entries (code, docs, 1 `.devcontainer` JSON); 7 context artefacts stored as supporting | profile, phase-10c census, trial `excluded` 36,679 |
| JSON parse ok | 3,630 / 3,630 | phase-10c novel census |
| Units / executions | 3,630 `agent_execution` / 3,630 | phase-10d census and trial (jobs 8; jobs-3 subset 730) |
| Sealed clean / with issues | 3,614 / 16 (12 `call_result_link_conflict` + `accounting_inconsistent`; 4 `unexecuted_tool_call`) | trial |
| Register codes | `map.accounting_unverifiable` 3,630, `map.earlier_attempts_unobservable` 3,630, `map.accounting_inconsistent` 12, `map.call_result_link_conflict` 12, `map.unexecuted_tool_call` 4, `select.owned_elsewhere` 36,679 | trial |
| Variant | `v1.k14` 3,630 | census |

Per cell (pipeline dir × suite, attacked / benign), from the git tree at the pin (file listing only); no injection-task pre-pass:

| Pipeline dir | banking | slack | travel | workspace | Total |
|---|---|---|---|---|---:|
| `gemini-2.5-flash` | 144 / 16 | 105 / 21 | 140 / 20 | 240 / 40 | 726 |
| `gemini-2.5-flash-ubag` | 144 / 16 | 105 / 21 | 140 / 20 | 240 / 40 | 726 |
| `gemini-2.5-flash-ubag_behavioral` | 144 / 16 | 105 / 21 | 140 / 20 | 240 / 40 | 726 |
| `gpt-4o-mini-2024-07-18-ubag` | 144 / 16 | 105 / 21 | 140 / 20 | 240 / 40 | 726 |
| `gpt-4o-mini-2024-07-18-ubag_behavioral` | 144 / 16 | 105 / 21 | 140 / 20 | 240 / 40 | 726 |

Totals: attacked 3,145, benign 485, pre-pass 0; suites workspace 1,400, banking 800, travel 800, slack 630; 97 user
tasks, 27 injection tasks (9 + 5 + 7 + 6: v1, not v1.2) (phase-10c novel census).

## 3. Expected arms

| Facet | Values | Expected missing / extra |
|---|---|---|
| Model | `gemini-2.5-flash` (alias, null call ids), `gpt-4o-mini-2024-07-18` | none extra |
| Defence | none (gemini only), `ubag`, `ubag_behavioral` (suffix) | **gpt-4o-mini undefended missing by design** (baseline = upstream 2024-07-19 run, corpus `agentdojo`, excluded here) |
| Attack | `important_instructions`; `none` (benign) | **5 further strategies the UBAG README counts (6 × 629 = 3,774 pairs, incl. `tool_knowledge`) and InjecAgent/ASB runs are not released**: 0 expected |
| Suite | banking, slack, travel, workspace (v1) | none |
| Task kind | user task only | pre-pass 0 (upstream script would write 27 per arm) |

The profile header ("the UBAG authorization gateway (`-ubag`, `-ubag_behavioral`) on gemini-2.5-flash and gpt-4o-mini-2024-07-18"; *corrected by fact-check: the earlier quote "each with ..." was a paraphrase*) omits the undefended gemini arm; the census and the
fork's results script (5 `EvalInfo` rows) agree on five arms.

## 4. Expected outcome rates (L2 comparison targets)

Metric mapping: targeted ASR = count of `security == true` over attacked logs of the arm (AgentDojo convention, as the
UBAG README's "attack success"); utility under attack = `utility == true` over attacked logs; benign utility =
`utility` over `none/none.json`. Benign `security` is the runner's constant true and is in no rate. *Fact-check caveat:* the README's Evidence table does not name the attack strategy (it says only "629 attack/task pairs" with gemini-2.5-flash, and a bullet says the strongest attack was `tool_knowledge`); reading it as `important_instructions` and its rows "Deterministic gate" / "Gate + behavioral layer" as `ubag` / `ubag_behavioral` is our inference from the 629-pair count and the labels, not a statement of the README. A mismatch in H1/H2 may therefore mean another strategy, not other runs. Logged values are
compared as recorded (slack `injection_task_5` is scored on proposed calls, #168/#189).

| Arm (pipeline / suite) | Targeted ASR (paper) | Source |
|---|---|---|
| gemini / none / banking · slack · travel · workspace | 48/144 · 89/105 · 89/140 · 74/240 | ubag-core/README "Evidence" row 1 (% × n) |
| gemini / none / all | **300/629** (47.7%) | same, stated count |
| gemini-ubag / banking · slack · travel · workspace | 0/144 · 36/105 · 23/140 · 0/240 (all 59/629, derived) | row 2 |
| gemini-ubag_behavioral / banking · slack · travel · workspace | 0/144 · 0/105 · 4/140 · 0/240 | row 3 |
| gemini-ubag_behavioral / all | **4/629** (0.64%); 3 of the 4 travel successes text-only | row 3 + bullet 1 |
| gemini / none → one defended arm (unnamed) | utility under attack travel 15/140 → 26/140; workspace 67/240 → 93/240 | bullet 3 |
| gpt-4o-mini-ubag or -ubag_behavioral / slack `injection_task_5` | security true 6/21; 19 membership calls proposed and refused, 0 executed | #189 "Measurement" |
| gemini defended / slack `injection_task_5` | 0/21 | #189 (the "other model") |
| gpt-4o-mini / all arms / all | not reported (no target; reference only: upstream undefended 66/97, 314/629, 171/629) | leaderboard |

Whole-population census reference (not a paper number): utility true 1,398, security true 910 over 3,630 (includes
485 benign constant-true); tool errors 3,242, of which UBAG refusals 2,731 (BLOCK 2,440, REVIEW 291). L2 samples about
5 per stratum (40 strata, about 200 units), below 20 per arm: Wilson intervals only; the exact test is H1.

## 5. Known quirks

| Id | Expected | Source |
|---|---|---|
| `agentdojo.benign_security_constant` (art. `agentdojo.art.benign_security_constant`) | 485 files, 485 judgements | profile `observed`, census |
| `agentdojo.injection_task_as_user_task_prepass` | 0 files | profile, census |
| `agentdojo.args_mutated_in_place` | 3,195 files (files with calls) | profile, census |
| `agentdojo.placeholder_args_never_injection_evidence` | 15,093 present, all null | profile, census |
| `agentdojo.provider_call_id_anomalies` (art. `agentdojo.art.provider_ids`) | 6,991 null ids in 1,756 logs (gemini); 0 duplicate/empty | profile, census |
| `agentdojo.unexecuted_trailing_calls` (art. `agentdojo.art.max_iters_pending`) | 4 calls in 4 logs (3 gemini none, 1 gemini-ubag benign travel ut19) | profile, r1 census samples |
| `agentdojo.silent_rerun_last_pass_only` (art. `agentdojo.art.silent_rerun`) | 0 null-final logs; `earlier_attempts_unobservable` 3,630 | profile, trial |
| `agentdojo.package_version_not_code_identity` | 0 without version (all `0.1.35`); `code_identity = "range"`, `verified_code = []` (D-103) | profile |
| `agentdojo.defence_denial_message` (R1, D-113) | 2,731 = `ubag-blocked: BLOCK` 2,440 + `ubag-blocked: REVIEW` 291 (hold mapped as deny), only in `-ubag*` dirs | profile, r1 census, routing.md |
| `benchmark_version` | `null` in 3,145 attacked (`unk /version not_recorded`, D-102), `v1` in 485 benign | profile, census |
| System prompt | 469-char AgentDojo default in all 3,630 | profile, census |
| `agentdojo.art.naive_timestamp` | naive `evaluation_timestamp`, range 2026-09-01/02 | artefacts.toml, census |
| `agentdojo.art.calls_derived_from_messages`, `.validity_defects`, `.payload_not_reaching_agent`, `.defence_benign_intervention` | generic family entries; not yet scoped to this profile | artefacts.toml |
| Content repeats | 763 new files (21%) with a trajectory equal to another file's | phase-10c candidate census |
| Accounting | `unverifiable` 3,618, `inconsistent` 12 | census |

## 6. Check map

| Check | Applies | Note |
|---|---|---|
| L1-01 counts | yes | §2; selection reasons from profile (`include`, 29 `owned_elsewhere` globs, `context_artefacts`) |
| L1-02 strict parse | yes | expect 0 defects (parse ok 3,630) |
| L1-03 encodings | yes | AgentDojo #214 literal `\uXXXX` residues in tool content: count, expected-known |
| L1-04 duplicates | yes | within part: the 763 content repeats by arm pair (H8); cross-corpus: 0 byte-identical with `agentdojo` (upstream copies are not selected) |
| L1-05 arm coverage | yes | §3; plus the whole-population outcome tally for H1-H3 |
| L1-06 secrets / account paths | yes | expect 0 (gateway URL/token are environment variables, not logged); benchmark-fixture passwords are expected-known |
| L1-07 timestamps | yes (partly) | presence, parse, zone (naive), range, per-arm ranges vs the fix commit (H5); within-unit monotonicity n/a |
| L1-08 degenerate | yes | expect 0 empty, 0 null-final, 0 run errors, 0 null utility; 4 unexecuted trailing calls |
| L2 import, validate, recompute, determinism | yes | trial: 0 failures, byte-identical across jobs 8/3 |
| L2 A2 / A3 classes | yes | expect only the trial's register codes; PI class for the 12 link conflicts (H6) |
| L2 evidence classes | yes | D rules only as `_unverified` twins; denials class I (`agentdojo.defence_denial_message@1`) |
| L2 degenerate / adapter_defect | yes | expect 0 / 0 |
| L2 identity | yes | model from `pipeline_dir`; defence from suffix; undefended gemini = no defence actor |
| L2 redaction | yes | expect no account path in AER/SEM/PROV |
| L2 withholding | conditional | only if L1-06 finds a secret-like string; none expected |
| L2 outcome sanity | yes (Wilson only) | §4; n per arm < 20 in the sample |
| Pre-pass checks | no | 0 pre-pass files |
| Delta since E2 | no | not examined in FA/E2 |

## 7. Hypotheses (falsifiable)

| # | Expectation | Refuted if |
|---|---|---|
| H1 | Whole-population ASR tally of the three gemini arms equals §4: none 48/89/89/74 (300), ubag 0/36/23/0, ubag_behavioral 0/0/4/0 (4) | any suite count differs by > 1 (rounding) or a total differs (then: the README used other runs; `documentation-mismatch`) |
| H2 | Gemini utility under attack: none travel 15/140, workspace 67/240; one defended arm 26/140 and 93/240 | no arm pair matches within ±1 |
| H3 | gpt-4o-mini slack `injection_task_5`: one defended arm has security true 6/21 with 0 executed `invite_user_to_slack`/`add_user_to_channel`/`remove_user_from_slack`; gemini defended arms 0/21 | counts differ, or any executed membership call among security-true logs |
| H4 | UBAG refusals occur only in `-ubag*` dirs: 2,440 BLOCK + 291 REVIEW; the reason "authorization gateway unreachable; failing closed" occurs in ≤ 5% of REVIEW holds (*fact-check note: at the pin this reason string is set only for the gate service; an unreachable behavioural service returns REVIEW with score 0.0 and no reason of its own, so this count is a lower bound on infrastructure holds*) | refusal outside a `-ubag*` dir; counts differ; unreachable share > 5% (S2: infrastructure holds counted as decisions) |
| H5 | The runs used the fixed client: in every defended arm at least one governed call was allowed and executed, and benign defended runs do not refuse 100% of governed calls | any defended arm (or a time block of it) refuses every governed call (pre-fix client, S1) |
| H6 | All 12 `call_result_link_conflict` files are in the two gemini defended arms, and each holds a multi-call turn with null ids whose tool messages repeat one result (the `by_id` collapse) | a conflict outside those arms, or one without a repeated result (then our mapping is suspect) |
| H7 | No defended slack log contains a refused `post_webpage` on the user-task check of #188 with a recorded utility; if any exists, the scorer was patched locally | ≥ 1 such log (S2: scorer code differs from the fork) |
| H8 | ≥ 90% of the 763 content repeats pair the same model's `ubag` and `ubag_behavioral` (or gemini none/defended) logs of the same cell, and no repeated trajectory contains a refusal whose text differs between arms | < 90%, or repeats across different cells/models (copying) |
| H9 | Every (pipeline, suite, user task, injection task) cell occurs exactly once; 0 pre-pass files; no attack label other than `important_instructions` | duplicate, hole, pre-pass file or extra label |
| H10 | `benchmark_version` is `null` in exactly the 3,145 attacked and `v1` in exactly the 485 benign logs, and attacked injection texts are v1's (27 injection tasks) | any other split or a v1.2 task id |
| H11 | 0 secret-like strings and 0 account paths in the 3,630 logs | ≥ 1 |

## 8. Discrepancy leads carried to the dossier

Five strategies' logs unreleased (README: 3,774 pairs); profile header omits the undefended gemini arm; no undefended
gpt-4o-mini arm (cross-corpus, 26-month baseline); runs predate the authored UBAG commits and the state-key fix; the
gateway and behavioural decisions come from an unversioned remote (partly commercial) service; #188 crash vs complete
logs; #189 proposal-scored slack IT5; Gemini null ids × `by_id` collapse in the defended gemini arms; possible
unreachable-gateway holds among the 291 REVIEWs; null attacked `benchmark_version` and no pre-pass imply a non-standard
driver; 763 content repeats; results document (2026-09-30) postdates the logs by four weeks.

## 9. Fact-check (2026-10-14, adversarial pass; metadata and documents only, no raw data read)

Checked and confirmed:
- UBAG `ubag-core/README.md` at `fba207eb` (single commit 2026-09-30T13:10:01Z), section "Evidence": row percentages
  33.3/84.8/63.6/30.8 (300/629), gate 0.0/34.3/16.4/0.0 (all-cell empty), gate+behavioral 0.0/0.0/2.9/0.0 (4/629);
  bullets "three of travel's four ... saying", "six attack strategies (3,774 pairs)", InjecAgent/ASB, travel 10.7%→18.6%
  and workspace 27.9%→38.8%. The count derivations in §4 are the only integers that round to those percentages for
  n = 144/105/140/240 (48, 89, 89, 74; 36, 23; 4; 15→26; 67→93), and 48+89+89+74 = 300, 0+36+23+0 = 59.
- AgentDojo #189 (mohameduk, 2026-09-03T04:55Z): 6 security=True, 19 proposed, 19 refused, 0 executed for
  gpt-4o-mini-2024-07-18 with `important_instructions` over 21 slack `injection_task_5` pairs; the other model 0/21.
  #188 (mohameduk, open, 1 comment 2026-09-20 by a third party): KeyError on refused `post_webpage`, reproduces on
  `user_task_4`, ends the run. #168, #181, #212, #214, #218 exist, are open, and match the stated topics.
- Fork: `fork` true, parent ethz-spylab/agentdojo, issues disabled, created 2026-09-03T04:54:58Z, pushed
  2026-09-07T05:07:55Z; branch `ubag-gateway-defense` head = `3f9d69a1` (unmoved). Commit dates and -0400 offsets of
  `3f9d69a1` (00:42:54), `9de3e23a` (19:20:50) and `27206776` (18:43:40) confirmed from the commit patches; `3f9d69a1`
  parent `9de3e23a`, +700,383 / -0, 300 files in the API listing. The `9de3e23a` message confirms the
  `allowed_destinations`→`known_destinations` fix and that every call was refused before it.
- Git tree at the pin (API listing, truncated at 37,368 blobs): 3,630 JSON logs in the 5 new pipeline dirs,
  35,559,371 bytes, 1,652 to 210,832 bytes; every cell of the §2 table matches (144/16, 105/21, 140/20, 240/40 per
  dir), 0 pre-pass paths. Profile `expected_files` 40,492 / `expected_bytes` 464,094,691 and the phase-10c census
  figures (all_tree_entries 40,492; novel: utility true 1,398, security true 910, tool_errors 3,242, benchmark_version
  null 3,145 / v1 485, ts_range 2026-09-01 15:05:54 to 2026-09-02 21:09:55, 97 user / 27 injection tasks) match the
  stored reports; r1 census denials 2,731 and routing.md 2,440 + 291 match.
- LICENSE at the pin: MIT, upstream text "(c) 2024 Edoardo Debenedetti, ... Florian Tramèr"; no fork line. UBAG
  LICENSE at `fba207eb`: PolyForm Noncommercial 1.0.0 (GitHub spdx NOASSERTION), README "Methods patent pending";
  mohameduk/aatc LICENSE.md: CC BY 4.0.
- Client code at the pin (`ubag_gateway.py`): `ubag-blocked: {decision}` error, gate unreachable → REVIEW
  "authorization gateway unreachable; failing closed", results re-ordered via `by_id` keyed by `tool_call_id`.
- Leaderboard: gpt-4o-mini-2024-07-18 / none / important_instructions 68.04% / 49.92% / 27.19%, 2024-07-19
  (= 66/97, 314/629, 171/629). arXiv 2406.13352 last version 2024-11-24.
- Data record: Zenodo (`UBAG agentdojo`, `"UBAG"`), Hugging Face (`search=ubag`, `author=mohameduk`) and Figshare
  (`search_for` UBAG; added by the fact-check) give no relevant record.

Corrected:
- #189 was closed by its author on 2026-09-07 with state reason `completed` (research.json said "without a state
  reason").
- The profile-header quote in §3 was a paraphrase; replaced with the header's wording.
- §4: added that the README table names neither the attack strategy nor the arm ids; the mapping to
  `important_instructions` / `ubag` / `ubag_behavioral` is our inference (expectations unchanged).
- H4: the "failing closed" reason covers only the gate; an unreachable behavioural service yields REVIEW without that
  reason (lower bound; expectation unchanged).

Unverifiable: whether the README numbers come from these exact logs; which defended arm the utility bullet refers to;
which model is #189's "other model" (gemini by elimination only); the code and service state that wrote the logs.
