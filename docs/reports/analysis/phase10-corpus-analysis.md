# Phase-10 corpus analysis: integrity, evidence quality, graph quality, source artefacts

Date: 2026-10-11. Analyst: Claude (worktree analysis session; read-only on the corpora and on `main`).
Code: `main` @ `dcdc3d3` (the corpora were derived on the integrated tree `afe7038`; the two later commits touch only
`docs/review/` and `tools/review/`, so `src/` is identical). No file under `src/` was changed.

## 0. Scope, method and reproduction

| Corpus (`~/.agentprov/corpora/…`) | Source · part | Executions | Profile (structural class) |
|---|---|---:|---|
| `rope-p10.partial` | ROPE · head (incl. the AutoDojo-attack slice, 2,847 files) | 10,791 | `rope@1` (I) |
| `agentdyn-a-p10.partial` | AgentDyn · a | 38,281 (+9,442 `select.dialect_planned`, 949 `select.owned_elsewhere`) | `agentdyn@1` (I) |
| `agentdojo-upstream-head-p10.partial` | AgentDojo HEAD `089ed468` | 36,679 (24,914 `v0.k11`, 11,764 `v1.k14`, 1 `v1.k14.incomplete`) | `agentdojo-upstream@1` (D) |
| `mandate-agentdojo-eval-p10.partial` | Mandate | 396 | `mandate-agentdojo-eval@1` (D) |
| `ast-survey-agentdojo-p10.partial` | survey · agentdojo-runs | 3,243 | `survey-runs@1` (I) |

**Total: 89,390 executions, every one analysed (no sampling) unless a section says otherwise.** The three corpora still
being imported (`agentdojo-upstream-2024-06-p10`, `adprov-v1-release-p10`, `ast-survey-agentharm-p10`) were not read.

Tools (committed under `tools/analysis/`; each reads the corpus only through the project's strict readers —
`agentprov.aer.reader.load_aer` (JCS lines, seal verified), `agentprov.sem.reader.load_sem`,
`agentprov.ingest.loaders.strict_json_loads` — and writes only ids, counts and safe tokens; no source text is printed):

| Tool | What it does |
|---|---|
| `phase10_extract.py` (+ `run_phase10_extract.sh`) | per execution: re-hash raw objects; AER/SEM seal digests vs index; SEM `aer_digest` vs AER; PROV file sha256 vs index; validation-row JCS digest vs index; AER facts (facets, record/evidence/unknown counts, ids, links, judgements, trajectory digest, text-shape counters); SEM facts; PROV graph facts (bundles, statements by section/rule/class, connectivity, AER→PROV cross-checks, forbidden statements, times); the shared artefact safety net `agentprov.artefacts.scan` |
| `phase10_aggregate.py` | per-corpus tables (`docs/reports/analysis/phase10-data/summary.json`) |
| `phase10_crosscheck.py` | end-to-end fidelity of AER against the raw log, every execution of every corpus (§5) |
| `phase10_register.py` | `register.jsonl` vs index vs `corpus.json` |
| `phase10_probe_markers.py`, `phase10_marker_cause.py` | payload visibility vs SEM injection markers (§3.3, B1) |
| `phase10_dups.py` | identical-trajectory groups (§4.6) |
| `phase10_compare.py`, `phase10_rule_classes.py` | cross-corpus shapes and rule placement (§6); D-rule citations (C6) |

Reproduce: `uv sync --locked`; `tools/analysis/run_phase10_extract.sh OUT` (4 workers, about 45 min for all five);
`python tools/analysis/phase10_aggregate.py --in OUT`; the other tools as in their docstrings. The derived tables are in
`docs/reports/analysis/phase10-data/` (counts and execution ids only).

Classification used below: **(a)** source-data property correctly disclosed (no fix); **(b)** mapping/graph defect or
improvement (fix proposed, ranked by impact); **(c)** spec question for the user.

---

## 1. Summary

**Nothing is malformed.** All 89,390 executions pass every integrity check (raw re-hash, AER/SEM/PROV digests, chain
links, strict parse), all validation checks pass (0 fail, 0 warnings recorded), the register is consistent, no execution
is duplicated, and the end-to-end cross-check of AER against the raw log finds **0 mismatches** in 89,390 executions. No
PROV statement that must never be emitted was found, no PROV time exists, every tool execution `used` only its request.
Every `observed` census count of the five profiles is reproduced by the corpora.

**Top findings**

1. **(b) SEM misses injection payloads in the ROPE AutoDojo slice.** The AutoDojo attack logs its `injections` values
   YAML-escaped (`_yaml_escape`), while the tool outputs carry the decoded text; `agentdojo.suites@1` compares the
   escaped payload verbatim. In **1,166 of the 2,847 AutoDojo executions** a payload is visibly present in a tool result
   but every injection marker is `absent`/`ambiguous`; with the payload unescaped, the full payload is found in 35 of 37
   fixture checks of the inspected cases. The other attacks in all five corpora show **0** such misses. Exposure,
   payload and taint assessments are missing for these executions.
2. **(b) `verified_complete` is assigned vacuously** to the 234 executions that have no accounting check at all (207
   head outcome-only logs, 25 head run-error logs that stop before any assistant turn, 2 ROPE outcome-only logs without
   outcomes): `fold_status([])` is `consistent`. These are the **only** `verified_complete` rows in the five corpora, so
   the H.3.2(3) filter "complete records only" currently returns exactly the empty and crashed runs.
3. **(b) CaMeL logs are mis-attributed.** In 266 of the 386 AgentDyn CaMeL logs the interpreter's error feedback to the
   planner is a `user` message (it starts with the escaped text "Running the code gave the following error:"); the
   mapper attributes it to the simulated user (warning `unattributed_additional_user_message`), and SEM labels it trusted
   principal content. The CaMeL planner's model calls are also asserted to see the full message prefix
   (`agentdojo.context_is_prefix@1`), including raw tool outputs that CaMeL by design keeps from the planner, which
   overstates exposure in exactly the defence built to prevent it.
4. **(b, catalogue only) The artefact catalogue does not cover the phase-10 profiles.** Every `agentdojo`-family entry
   is scoped to the profile `agentdojo-upstream` (or the live profiles), so the safety net classifies **0** findings in
   ROPE, AgentDyn, Mandate and the survey (e.g. 165,886 unclassified findings in AgentDyn); in head, three classes stay
   unclassified (repeated GPT ids 213, `incomplete_run` 1, the ambiguous naive timestamp 11,765). The safety net is also
   not wired into `import` (D.15.8 item 8), so the imports themselves flagged nothing.
5. **(a) Large source artefacts that bear on reported metrics** (§8): the injection never reaches the agent in 18–55 %
   of attacked runs; defences intervene in benign runs (the transformers PI detector redacts 57 % of benign tool outputs
   in both head and AgentDyn); 173 survey `qwen3-coder:30b` runs end after one turn whose tool call is written as text
   and never executed, and are scored "attack failed"; byte-identical trajectories recur across injection tasks
   (3,612 head executions in 382 groups); attack successes without any payload exposure (head: all 11 are the
   catalogued banking `user_task_15` confound; ROPE: 22 new cases).

**Proposed fixes, ranked by impact** (details in §7):

| # | Fix | Where | Digests / re-import |
|---|---|---|---|
| B1 | Undo AutoDojo's YAML escape on the payload side of the injection marker when the fixture is AutoDojo-linked | `adapters/agentdojo/semantics/` (`markers.py`, `suites.py`); `agentdojo.suites` → version 2 or a new normaliser rule | SEM + PROV of the ROPE AutoDojo slice change (≥ 1,166 executions); AER unchanged; with a profile version bump, SEM/PROV of every corpus using the profile change |
| B2 | No `verified_complete` without at least one evaluated accounting check, and never for `outcome_only`/`no_outcome_recorded` | `adapters/runner/importer.py` `_index` | index rows and `corpus.json` counts only (head 232, ROPE 2, phase-9 2024-06 likewise); no AER/SEM/PROV digest |
| B3 | CaMeL hook: interpreter feedback attributed to the `camel` defence actor; planner context not asserted | `adapters/agentdojo/hooks/agentdyn.py`, `agentdyn` profile + catalogue | AER/SEM/PROV of the 386 CaMeL logs |
| B4 | Catalogue entries for rope/agentdyn/mandate/survey and the three unclassified head classes (texts in §8.3) | `adapters/agentdojo/artefacts.toml` | none (catalogue only) |
| B5 | Implement the safety-net detector `payload_not_reaching_agent` from SEM markers (D.15.3; listed in `NOT_YET_IMPLEMENTED`) | `src/agentprov/artefacts/` | none (L3, reads only) |
| B6 | Retry-inference rule for unpinned harnesses at class I (twin), as for the structural rules | `rules/agentdojo.rules.toml`, `rules/agentdyn.rules.toml`, profiles | AER/PROV of 322 ROPE + 826 AgentDyn; completeness counts; all PROV (catalogue digest) — see C6 before doing it |

---

## 2. Integrity and malformation

| Check (all executions) | rope | agentdyn | head | mandate | survey |
|---|---:|---:|---:|---:|---:|
| executions | 10,791 | 38,281 | 36,679 | 396 | 3,243 |
| raw object re-hash, BOM, UTF-8 | 0 errors | 0 | 0 | 0 | 0 |
| AER strict parse + seal digest = `digests.aer` | 0 errors | 0 | 0 | 0 | 0 |
| SEM seal = `digests.sem`; SEM `aer_digest` = AER | 0 | 0 | 0 | 0 | 0 |
| PROV bytes sha256 = `digests.prov`; strict parse; `xd:aer.<digest>` = AER | 0 | 0 | 0 | 0 | 0 |
| validation-row JCS digest = `digests.validation` | 0 | 0 | 0 | 0 | 0 |
| validation checks failed / warnings | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| duplicate `ex` / duplicate source sha256 / rows with >1 origin | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| control, bidi, zero-width or non-ASCII characters in identifier fields (task facets, actor names) | 0 | 0 | 0 | 0 | 0 |
| `after` edges malformed; model-call inputs non-monotone | 0 | 0 | 0 | 0 | 0 |
| register: duplicate `rid`; `map.*` row ↔ index issue; `select.*` counts = `corpus.json`; owners | consistent | consistent | consistent | consistent | consistent |

Status and completeness:

| | rope | agentdyn | head | mandate | survey |
|---|---|---|---|---|---|
| status `ok` / `ok_with_issues` / `failed` | 9,366 / 1,425 / 0 | 35,904 / 2,377 / 0 | 33,745 / 2,934 / 0 | 396 / 0 / 0 | 3,184 / 59 / 0 |
| `verified_complete` / `known_incomplete` / `unverifiable` | 2 / 322 / 10,467 | 0 / 837 / 37,444 | 232 / 83 / 36,364 | 0 / 0 / 396 | 0 / 0 / 3,243 |
| unit `outcome_only` | 2 | 0 | 207 | 0 | 0 |
| degenerate | 0 | 0 | 0 | 0 | 0 |

The `verified_complete` rows are all vacuous (B2): head = 207 outcome-only + 25 run errors with no assistant message
(e.g. `ex_23wjd72f2j7tevakexl4exznjb`, `ex_2haaq6yvzjgovuvprh7w2lmemi`); ROPE = the 2 empty logs without outcomes
(`ex_5q7qnwlm7e3gp7riq5juw5auqh`, `ex_jpb336p2p355jpvpuzgguzmgmu`).

Text characters in message content (not identifiers): one zero-width character in one survey message; no C0/C1 controls,
bidi controls, tag characters, replacement characters or mojibake sequences in any corpus. One AgentDyn tool-call
*name* holds a natural-language sentence (`ex_amwz4ear7dokydjkrwjokmkl4z`, gemini-2.5-pro; a model-output artefact, kept
verbatim; §8 row 20).

## 3. Seal issues and evidence quality

### 3.1 Seal issues

| Code (severity) | rope | agentdyn | head | mandate | survey |
|---|---:|---:|---:|---:|---:|
| `accounting_unverifiable` (info) | 10,789 | 38,270 | 36,447 | 396 | 3,243 |
| `earlier_attempts_unobservable` (info) | 10,789 | 38,281 | 36,472 | 396 | 3,243 |
| `retry_passes_inferred` | 322 | 826 | 82 | 0 | 0 |
| `unexecuted_tool_call` (logs / calls) | 675 / 753 | 1,683 / 1,800 | 800 / 815 | 0 | 48 / 49 |
| `outcome_imposed_by_runner` | 0 | 5 | 105 | 0 | 11 |
| `no_execution_observed` / `no_outcome_recorded` | 2 / 2 | 0 | 207 / 0 | 0 | 0 |
| `incomplete_run` | 0 | 12 | 1 | 0 | 0 |
| `identity_conflict` | 949 (all `qwen3-235b`, AutoDojo arm) | 0 | 0 | 0 | 0 |
| `agentdojo.pipeline_name_mismatch` | 0 | 12 | 0 | 0 | 0 |
| `agentdojo.local_parse_drop_possible` | 0 | 488 | 1,854 | 0 | 0 |
| `orphan_tool_result` (info) | 0 | 240 (CaMeL) | 0 | 0 | 0 |
| `unattributed_additional_user_message` | 0 | 266 (CaMeL) | 0 | 0 | 0 |
| `identity_unresolved`, `missing_tool_result`, `call_result_link_conflict`, `undeclared_quirk`, `unknown_message_shape`, `path_field_mismatch` | 0 | 0 | 0 | 0 | 0 |

By facet (full tables in `summary.json`: `issues_by_model`, `issues_by_suite`, `issues_by_attack`): the iteration-cap
cut concentrates on weaker models (head `claude-3-haiku` 60, ROPE `qwen3-235b` 360 of 2,268 and `gpt-4o-mini` 273,
AgentDyn `meta-llama/llama-3.3-70b-instruct` 335, `Meta-SecAlign-8B` 167); run errors on `command-r-plus` 25,
`gemini-1.5-pro-001` 22, `gpt-3.5-turbo` 13 (head), `gpt-oss:120b` 11 (survey), `llama-3.3-70b` 5 (AgentDyn). The retry
rule fires in ROPE on `gpt-4o-mini` (272) and in AgentDyn on `gpt-4o-mini` (559) and `gpt-5-mini` (255); in ROPE 317 of
322 and in AgentDyn 726 of 826 retry inferences coincide with an iteration-cap cut whose final assistant message has
null text and pending calls — under the harness code that is a null model output, hence a rerun (§8 row 3).

### 3.2 Unknowns and evidence classes

`unk` reasons (record-pointer level): `not_recorded` dominates everywhere (model-call request/response/usage/finish/times,
tool-execution return and times, `args_raw`, checker inputs, model provider/served/params, instrumentation);
`ambiguous` = the naive run timestamp of every `v1.k14` log plus `""` assistant texts and `""` Gemini call ids (head 12,583);
`lost` = the attempt index of every non-retry log; `overwritten` = PI-detector redactions (head 2,138, AgentDyn 29,317).
No `withheld` or `not_applicable`. All of this is (a): the TraceLogger format does not record these facts.

| AER field evidence tags (`evf`) | O | D | I |
|---|---:|---:|---:|
| rope | 159,218 | 233,408 | 441,451 |
| agentdyn | 497,218 | 672,386 | 1,359,403 |
| head | 284,883 | 1,000,950 | 542,214 |
| mandate | 3,332 | 11,997 | 3,321 |
| survey | 28,960 | 45,258 | 67,067 |

PROV statements by bundle and class (share within bundle; `-` = unidentified `hadMember`/`mentionOf`):

| | core O / D / - | inference I / - | share of core in core+inference | assessment O / D / I / - |
|---|---|---|---:|---|
| rope | .61 / .29 / .10 | .95 / .05 | 0.18 | .01 / .04 / .78 / .17 |
| agentdyn | .60 / .32 / .08 | .95 / .05 | 0.20 | .01 / .03 / .79 / .17 |
| head | .30 / .67 / .04 | .99 / .01 | 0.52 | .03 / .08 / .57 / .32 |
| mandate | .28 / .69 / .03 | .99 / .01 | 0.59 | .03 / .06 / .58 / .33 |
| survey | .53 / .41 / .06 | .94 / .06 | 0.27 | .03 / .08 / .60 / .30 |

No core statement is I; no inference statement is O or D. The I-class profiles (ROPE, AgentDyn, survey) put model calls,
tool executions and their generation/usage statements in inference bundles by design (D.5.4 I twins), so their core holds
mostly entities (§4.2, C4).

Identity: `identity_unresolved` 0 everywhere; `identity_conflict` 949 (ROPE `qwen3-235b/*/autodojo`, declared quirk
`qwen_autodojo_mislabelled`); `pipeline_name_mismatch` 12 (AgentDyn variant-A travel strays in the Progent directory).

### 3.3 SEM

| | rope | agentdyn | head | mandate | survey |
|---|---|---|---|---|---|
| role annotations `unknown` (fail-closed) | dailylife, github, shopping: 100 % (110,594) | dailylife, github, shopping: 100 % (420,307) | 34 of 273,933 | 0 | 18 of 22,523 |
| integrity `unknown` | 63,239 | 210,242 | 17 | 240 | 9 |
| injection markers present / absent / ambiguous | 29,194 / 154,702 / 3,802 | 69,662 / 372,088 / 569 | 73,580 / 171,375 / 0 | 361 / 935 / 0 | 5,633 / 12,735 / 0 |

The AgentDyn suites have no tool tables in `agentdojo.suites@1` (documented in D.6.13/D.6.14 "Open"): (a), with the
known follow-up `agentdyn.suites@1`. Head/survey unknowns are hallucinated tool names (fail-closed, correct).

**Marker misses (B1).** Probing every attacked execution for a whitespace-collapsed 40-character window of a payload
(logged and YAML-unescaped forms) in tool results, against the SEM verdict:

| Attack (corpus) | attacked | window visible, marker present | window visible, **no marker** | no window, no marker |
|---|---:|---:|---:|---:|
| `autodojo` (ROPE) | 2,847 | 1,114 | **1,166** | 563 |
| `important_instructions` (ROPE) | 6,436 | 5,653 | 0 | 455 |
| `long_horizon` (ROPE) | 758 | 639 | 0 | 119 |
| all attacks (head, 4,000-row seeded sample, 3,568 attacked) | | | 0 | |
| all attacks (survey, mandate: all) | 2,847 / 369 | | 0 / 0 | |
| all attacks (AgentDyn, 4,000-row sample, 3,454 attacked) | | | 48 (all 20 inspected: `-drift`, partial payload after DRIFT's in-place isolation; C3) | |

Root cause (`phase10_marker_cause.py` over the inspected cases): every missed payload contains characters `_yaml_escape`
rewrites; the logged payload is found in no tool text or normalised form (0/37), the unescaped payload is found in the
SEM normaliser's fast forms in 35/37. Examples: `ex_227rgqcga4dbivgqxjoakstk5j`, `ex_25gbp25xtuwcrypfx65eulctky`,
`ex_26s5a4h3yldublr4zainsz2maa`.

## 4. Graph quality

### 4.1 Sizes

| | PROV nodes (core+inf) p50 / p95 / max | edges p50 / p95 / max | nodes per message p50 | edges per message p50 | PROV-JSON bytes p50 / max |
|---|---|---|---:|---:|---|
| rope | 91 / 170 / 370 | 246 / 821 / 1,858 | 5.73 | 15.6 | 318 KB / 2.8 MB |
| agentdyn | 74 / 175 / 510 | 163 / 839 / 1,895 | 6.23 | 13.8 | 225 KB / 4.2 MB |
| head | 57 / 121 / 412 | 102 / 378 / 2,029 | 6.43 (`v0.k11`), 6.00 (`v1.k14`) | 10.5 / 10.1 | 131 KB / 2.2 MB |
| mandate | 58 / 88 / 234 | 102 / 226 / 652 | 6.22 | 11.3 | 130 KB / 1.3 MB |
| survey | 52 / 115 / 311 | 94 / 394 / 1,557 | 6.22 | 11.4 | 149 KB / 3.3 MB |

Nodes per message are stable across sources (5.7–6.4). Edges per message are higher for I-class profiles because the
Inference-6 closure and the context usages (`aprov.use_context@1`, `aprov.comm@1`) grow quadratically with the message
count and sit in inference bundles; this is the spec's closure, not an artefact. Largest graphs are long runs (ROPE
`ex_75xjxr5uhvdcl6tbmxqkh6pqnt`, 72 messages; AgentDyn `ex_iitedwgcg2z7am5e3rayl2iuzd`, 97; head
`ex_m4ckcbqw5dv6zruvx72d6if7f6`, 90); smallest are outcome-only logs (23 nodes) and two-message run errors
(`ex_dvirctlycfksyfadhleml7vh36`, command-r-plus). No outlier is caused by mapping.

### 4.2 Connectivity

The union of core and inference bundles, with the attribute links `apv:partOf` and `apv:about` added, has 3–9 weakly
connected components per execution (p50 4). The minor components are always of these kinds (counts = executions):

| Minor component | rope | agentdyn | head | mandate | survey | Classification |
|---|---:|---:|---:|---:|---:|---|
| `x:capture-profile` alone | 10,791 | 38,281 | 36,679 | 396 | 3,243 | by design (E.10 item 16) |
| execution header `x:exec` + its gap entities + mention | 10,791 | 38,281 | 36,679 | 396 | 3,243 | C2 |
| attacker agent + payload fixtures | 10,041 | 33,091 | 33,119 | 369 | 2,847 | C2 |
| a defence agent that made no decision in the run | 4,594 | 11,809 | 1,486 | 51 | 0 | correct (no evidence) |
| tool runtime `env` in runs without a tool execution | 287 | 6,008 | 3,072 | 5 | 342 | correct |
| `agent.model`/`agent.svc` in runs without a model call | 2 | 11 | 232 | 0 | 0 | correct |

Without the attribute links, the system and first-user text parts are isolated relationally in every execution (they are
linked only by `apv:partOf`, `aprov.part_of@1`): 21,578 ROPE parts, 102,944 head, 114,795 AgentDyn. In the core bundle
alone, the I-class profiles are fragmentary (core components p50: ROPE 37, AgentDyn 29, survey 21; head 9, mandate 8).

AER → PROV cross-checks (every execution): every AER message with `generated_by` has the matching `wasGeneratedBy`
(core or inference); every message without a generator is attributed; every `tool_call` part is `hadMember` of its
message; every model call, tool execution and decision has `wasAssociatedWith`; every linked tool execution `used` its
request part; every model call `used` exactly its AER `input` messages. **0 violations in all corpora.**

### 4.3 Statements that must never appear

| Check | Result |
|---|---|
| `wasInfluencedBy` anywhere | 0 |
| any `prov:time`, `prov:startTime`, `prov:endTime` | 0 |
| an I-class statement in a core bundle | 0 |
| `used`/`wasDerivedFrom`/`wasInformedBy` in an assessment bundle | 0 |
| a tool execution `used` anything but its request part | 0 (all 427,225 usages are request parts) |
| `wasInformedBy` in core | head 72,701, mandate 1,390: all `aprov.comm@1` with D premises (`C(∅)` of EF E.1.6), allowed |
| `wasDerivedFrom` in core / inference | ROPE 678 core: the recomputed-security revisions (`prov:Revision`, `revises`), allowed; head 2,138 / AgentDyn 29,317 inference: PI-detector `DefenceRedaction`, allowed (`aprov.decision@1`) |

### 4.4 Accounting

`tool_calls_dispatched` is `consistent` in every execution that has tool calls (rope 10,520; AgentDyn 32,175; head
33,607; mandate 391; survey 2,901): calls = executions + denials + unexecuted in every corpus (e.g. ROPE 83,362 =
69,952 + 12,657 + 753; AgentDyn 210,127 = 208,327 + 1,800 (CaMeL orphans: 1,977 executions `requested_by` the defence);
mandate 1,390 = 1,150 + 240). `agent_calls_vs_assistant` is `unverifiable` by format (catalogued
`agentdojo.art.calls_derived_from_messages`). No `inconsistent` verdict anywhere.

### 4.5 Mapping-artefact screens

- Quirk hooks fire only where their `applies` matches: ROPE denials only in ROPE (12,657, all `rope`), Mandate declines
  only in `mandate_*` pipelines (240) with 143 inferred allows, DRIFT user decisions only in `-drift` (434), CaMeL
  orphans only in `-camel` (1,977), PI redactions only in detector pipelines; head/survey carry no decision except the
  2,138 head redactions. No `undeclared_quirk` issue.
- Constant fields: `benchmark_version` is constant per source except ROPE, where all 760 long-horizon files say `v1.2.1`
  and every other ROPE file `v1.2.2` (a harness-generation difference of the long-horizon arm; §8 row 22). The survey
  `pipeline_name` is one constant value (declared `constant_not_model`). `agentdojo_package_version` is `0.1.35` or
  `unknown` (declared). Timestamps vary normally (at most 7 files share a second, in parallel AgentDyn runs); no
  timestamp later than the committed-no-later-than date in head (36,679 checked).
- Ordering: all `after` edges point backwards, model-call inputs grow monotonically, tool executions in a batch are
  ordered by `tools_executed_sequentially`.

### 4.6 Repeated identical subgraphs

Identical message lists (roles and parts, JCS) under different files:

| | groups | executions | labels that differ inside groups | utility differs | any attacked member with marker / security true |
|---|---:|---:|---|---:|---|
| rope | 53 | 396 | injection task 53, attack 29 (20 with a benign member) | 0 | 0 / 0 |
| agentdyn | 655 | 4,120 | injection task 607, attack 252, defence 255, model 10 | — | — |
| head | 382 | 3,612 | injection task 363, attack 246, defence 33, model 13 | — | — |
| survey | 32 | 299 | injection task 32, attack 7 | 0 | 0 / 0 |

In ROPE and the survey every group is one user task whose run never read an injected vector (no marker in any member),
so the agent behaved identically whatever the injection task; utility never differs inside a group. The cross-model
groups (head 13: gemini-1.5/2.0 pairs and gpt-4-0125/gpt-4-turbo; AgentDyn 10: llama-3.3/qwen3/gemini) are all 3–7
messages long (e.g. `ex_4pcp5kbbkpn3adnrulkwsl5dhj` / `ex_gd7h6ygj2dhjcbw6ypxyww5iet`). These are graphs of distinct
executions, correctly kept apart (`content_dedup = never`); see C5 for the cross-model groups.

## 5. End-to-end fidelity (AER vs raw log)

`phase10_crosscheck.py` over **all 89,390 executions**: every source message mapped exactly once at its position, roles,
texts (string, blocks, `null`, `[]`), tool-call names/args/ids, tool-result content and errors, fixtures = `injections`
(order and content), utility/security values (none invented, none dropped), run duration and timestamp verbatim, task
fields; one execution or deny decision per tool message; execution status consistent with the tool `error`; no record
other than the run scope carries a time. **0 mismatches** in every corpus (`phase10-data/crosscheck.txt`). The graphs
state what the logs show and nothing more on these axes.

## 6. Cross-source consistency

The same harness behaviours produce the same graph shapes across sources:

- **executed call**: request part `hadMember` its message, `wasGeneratedBy` the model call; execution `used` the request,
  `wasAssociatedWith` the tool runtime (`actedOnBehalfOf` the agent, I `AutoExecution`), result `wasGeneratedBy` the
  execution; identical rule sets in all five corpora;
- **unexecuted trailing call**: no execution, request `apv:dispatchStatus apv:NotDispatched`, issue
  `unexecuted_tool_call`; head, ROPE, AgentDyn, survey;
- **denial / decline / redaction**: a `decision` activity associated with the defence, `used` the request (deny) or
  `wasDerivedFrom` the pre-decision output (redact), the message generated by the decision; ROPE (I), Mandate (D),
  DRIFT (D), PI detectors (I); class follows the rule, so Mandate's land in core and ROPE's in inference;
- **retry**: `att0` index 2 and two issues in ROPE, AgentDyn, head `v0.k11`; never in head `v1.k14`, Mandate or the
  survey, whose logs never end on null content;
- **run error**: both judgements `harness_default`, no checker run, issue `outcome_imposed_by_runner`; head, AgentDyn,
  survey.

Rule placement differs between corpora only as the structural class dictates (`phase10-data/compare.json`,
`rule_placement`): model calls, tool executions and their statements are core in head/Mandate and inference in
ROPE/AgentDyn/survey; head additionally puts the tool-filter auxiliary calls (I) in inference; survey run-error
judgements sit in inference because their origin rule `survey.internal_server_error_patch@1` is I. No difference is a
mapper inconsistency.

---

## 7. Findings, classified

### (b) Mapping/graph defects or improvements, ranked by impact

**B1. Injection marker misses YAML-escaped AutoDojo payloads (ROPE).**
- *Evidence*: §3.3; 1,166 of 2,847 AutoDojo executions (41 %) have a visible payload but no `present` marker; 0 such
  misses for every non-AutoDojo attack in all corpora.
- *Cause*: the AutoDojo attack writes `_yaml_escape(variant)` into the log's `injections` (D.6.13 item 9; the hook
  `hooks/autodojo.py` ports the escape for the cache link); the environment shows the decoded text. The marker
  (`markers.marker_statuses`) normalises the payload only by whitespace (`norm_payload`).
- *Fix*: in `agentdojo.suites`, for a fixture whose AER carries `ext.autodojo.cache_match` (`exact` or `wrapped`, i.e. the
  hook established the escape), compare the payload with AutoDojo's escape undone (`\\`, `\"`, `\n`, `\t`; the inverse of
  `hooks/autodojo.py:yaml_escape`), citing the fixture's `ext.autodojo.cache_match` as a premise; record the normaliser
  as a new rule (e.g. `agentdojo.autodojo_payload_unescape@1`, D: the escape is the attack's own code at `aa458794`
  l. 76-84). Keep the logged fixture content verbatim (it is O by benchmark). Spec: C.14.3 marker, EF E.7.3 rows
  `a_payload`/`a_exposure`/`a_taint`; D.15 artefact (§8 row 12).
- *Expected effect*: AER unchanged; SEM digests of the ROPE AutoDojo executions with escapable payloads change
  (≥ 1,166), PROV assessment bundles gain payload/exposure/taint assessments for them; present-marker rate on the
  AutoDojo arm rises from 1,118/2,847 to about 2,284/2,847. Any byte change bumps the profile version (AD-18):
  `agentdojo.suites@2`, which changes the profile digest in the SEM and PROV of every corpus using the profile (all five
  phase-10 corpora and the phase-9 2024-06 corpus) — a re-derivation of SEM+PROV, i.e. a full re-import while no
  PROV-only `derive` exists.
- *Risk*: low if gated on the AutoDojo link (no other payload is touched; gate E/v2.3 equivalence on the v1 corpora is
  unaffected because those fixtures carry no `ext.autodojo`); verify on the 12 ROPE fixtures.

**B2. Vacuous `verified_complete`.**
- *Evidence*: §2; 234 executions, all with zero accounting checks.
- *Cause*: `aer.accounting.fold_status([])` returns `consistent`; `importer._index` maps `consistent` to
  `verified_complete`; `no_outcome_recorded` is not in `_LOSS_CODES` either.
- *Fix* (runner only, H.3.2(2)): `verified_complete` iff the accounting status is `consistent` **and** at least one check
  was evaluated **and** `unit == "agent_execution"`; otherwise `unverifiable` (do not change `fold_status`: the seal is
  part of the frozen `aer/0.1` output and its digest). Add a test with an outcome-only and a no-assistant run-error AER.
- *Expected effect*: no AER/SEM/PROV digest changes; `executions.jsonl` completeness of 232 head + 2 ROPE rows and
  `corpus.json` counts change (and the corresponding rows of the phase-9/phase-10 2024-06 corpus); a re-index suffices
  where one exists, else the next import.
- *Risk*: very low.

**B3. CaMeL feedback messages and planner context.**
- *Evidence*: 266 CaMeL logs with `unattributed_additional_user_message` (e.g. `ex_26zlzyuefc4osnwp7o22kx6mi6`: user
  message `m4` is interpreter error feedback, escaped prefix "Running the code gave the following error:"); CaMeL logs
  start with interpreter tool results before any assistant message (the 1,977 orphans).
- *Fix*: a hook in `hooks/agentdyn.py` for `*-camel` (quirk e.g. `agentdojo.camel_interpreter_feedback`): a later user
  message matching the feedback prefix gets `actor` = the `camel` defence actor (I, new rule
  `agentdyn.camel_interpreter_feedback@1`, citing the AgentDyn-vendored CaMeL code), like the DRIFT `error`-key row; and
  a profile parameter that replaces the planner model calls' `input` by `unk {"/input": "not_recorded"}` for `*-camel`,
  as D.6.6 does for DRIFT, because CaMeL's privileged planner does not receive raw tool outputs (to be confirmed in the
  vendored CaMeL code before mapping).
- *Expected effect*: AER, SEM and PROV of the 386 CaMeL logs (attribution, integrity labels, context `used`, exposure
  assessments); the `agentdyn` profile and catalogue digests (AgentDyn corpus re-import); the warning disappears for 266.
- *Risk*: low for the attribution; medium for the context change (needs the code check).

**B4. Artefact catalogue coverage (catalogue only).** Proposed entries in §8.3. Effect: the safety net classifies the
phase-10 findings; nothing in AER/SEM/PROV changes. Also widen `scope.profiles` of the generic AgentDojo entries
(`benign_security_constant`, `run_error_imposed`, `silent_rerun`, `max_iters_pending`, `provider_ids`,
`calls_derived_from_messages`, `injection_task_as_user`, `validity_defects`, `text_tool_call`) to the profiles where the
same harness behaviour occurs, with their measured counts (§8). Note: D.15.2 says the catalogue is recorded in
`corpus.json`; the phase-10 `corpus.json` files carry no artefact-catalogue record (only rule catalogues in
`derivation.json`) — record it when the net is wired.

**B5. Implement `payload_not_reaching_agent`** in `agentprov.artefacts` from SEM injection markers (now available,
phase 7): attacked execution with no `present` marker on any tool result. Counts it would report: §8 row 6. L3, reads
only, no digest change.

**B6. Retry inference cited at class D for unpinned harnesses.** ROPE (322) and AgentDyn (826) assert `att0.index = 2`
(D) and `pre_state_not_initial`, and are therefore `known_incomplete`, under `agentdojo.null_final_implies_three_passes@1`
(code cited at `c274885` only) and `agentdyn.last_assistant_content_none_max3@1` (code at the AgentDyn pin, while the
profile says the January runs predate that code). D.5.4 gives the three structural rules and the timestamp rule
`_unverified` twins for exactly this situation; the retry rule has none. A twin at class I would move the index into an
inference statement and, by H.3.2(2) ("an adapter rule proves loss"), these executions to `unverifiable`. Effect: AER
and PROV of 1,148 executions, the catalogue digests in every PROV, completeness counts. Decide C6 first.

### (c) Questions for the user

- **C1. Attack successes without exposure.** Should SEM flag `security = true` when no payload is visible anywhere in
  the trajectory (FO, assessment only)? The screen reproduces the catalogued banking `user_task_15` confound exactly
  (head: all 11 such executions are banking `user_task_15`, e.g. `ex_43xkrdyhabzgqb3jwaizq5kswj`) and finds 22 new ROPE
  cases (17 `slack/injection_task_1` AutoDojo, e.g. `ex_26efckog4hgyywvfjazhbisg6b`; 5 `important_instructions`
  github/shopping, e.g. `ex_4vi6ojaqr6uyqzkneb6754eiff`) and 1 in a 4,000-row AgentDyn sample. The reserved rule
  `agentdojo.account_confound` could be generalised.
- **C2. Disconnected configuration subgraphs.** The attacker agent and payload fixtures, and the execution header, are
  not connected to the run activity in any execution (§4.2). Is a relation wanted — e.g. `used(x:run, x:fx<n>)` under a
  D harness rule ("the suite loads the environment with the injections before the pass", AgentDojo `task_suite.py`) —
  or should they stay attribute-linked only? (Not a defect: no current rule licenses the edge.)
- **C3. Partial payloads.** DRIFT's in-place isolation leaves fragments of a payload in tool output; the marker has no
  `partial` status, so these are `absent` (48 in a 4,000-row AgentDyn sample). Add a status, or keep `absent` and
  disclose?
- **C4. Core-only consumers.** For the I-class profiles the core bundle alone is mostly unconnected entities. Should the
  datasheet state that analyses must load the scope `S(M)` (core + inference), or should a derived "union view" be
  shipped?
- **C5. Cross-model identical trajectories.** 13 head and 10 AgentDyn groups of 3–7-message runs are byte-identical
  under different model labels. Most likely coincidence of short deterministic runs, but copied files cannot be excluded
  from the logs alone; worth one look at the upstream commits (`ex_4pcp5kbbkpn3adnrulkwsl5dhj` /
  `ex_gd7h6ygj2dhjcbw6ypxyww5iet`; `ex_2axjhzshusbl6zscnnu5s3k262` / `ex_2bjpx6nvh5ctwff4i5x4zhbrpx`).
- **C6. D-rule citation policy.** D.5.4 states a D rule may be cited only for code its verification block lists, but
  many D rules with code at `c274885` only are cited by the I-class profiles and by head `v1.k14`/Mandate (e.g.
  `checker_outcome`, `call_id_unique_match`, `tool_status_from_error`, `tools_executed_sequentially`,
  `user_is_simulated`, `benign_security_constant`; `phase10-data/ruleclasses.json`). Either the policy is meant only for
  the structural rules (then say so in D.5.4) or more twins are needed (B6 is the most consequential case).

### (a) Correct and disclosed (no fix)

Integrity, validation, register, accounting, fidelity (§2, §4.4, §5); unknowns and evidence classes (§3.2); the
`agentdyn.suites` gap (documented); the quirk counts (every profile `observed` count reproduces: e.g. ROPE denials
12,657 = 9,424 + 3,233, corrections 198/260/220 with 32→0, 39→22, 5→0; AgentDyn redactions 29,317, CaMeL orphans
1,977, DRIFT user decisions 434, prepasses 1,647; head 3,560/485/82/804/207/105/1/815/2,138/213; survey 11/48/105;
Mandate 240 declines); the identical-trajectory groups; the source artefacts of §8 that need no mapper change.

---

## 8. Source-data artefacts for the manuscript

Counts are executions unless stated. "Catalogued" names the `artefacts.toml` id (all current ids are scoped to
`agentdojo-upstream`), a profile quirk (`q:`), or "new". Classes per D.15.1.

### 8.1 Table

| # | Artefact | Sources and counts (examples) | Catalogued | Class | Effect on metrics | Recommended disclosure |
|---|---|---|---|---|---|---|
| 1 | Benign `security` is a constant `true` | head 3,546; ROPE 748; AgentDyn 5,176; survey 395; Mandate 27 (all prepasses) | `agentdojo.art.benign_security_constant` (head); `q:benign_security_constant` elsewhere | CR | a raw mean of `security` over all runs counts every benign run as an attack success | "Benign runs carry a harness constant `security = true`; we exclude it (origin `harness_default`) from attack-success rates." |
| 2 | Run error imposes outcomes (utility false, security true) | head 105 (`command-r-plus` 25, `gemini-1.5-pro-001` 22); AgentDyn 5; survey 11 (`gpt-oss:120b`) | `agentdojo.art.run_error_imposed` (head); `q:run_error_imposes_outcome` | CR | +105/+5/+11 spurious attack successes if `security` is read raw | "Runs aborted by a harness error are scored by rule, not by the checker; we report them separately." |
| 3 | Silent rerun: only the last of up to three passes is logged; mostly triggered by the 15-iteration cap with null text | head 82 (27 at the cap); ROPE 322 (317 at the cap); AgentDyn 826 (726 at the cap) | `agentdojo.art.silent_rerun` (head); `q:silent_rerun_last_pass_only` | NR (passes) / CR | the scored pass ran on an environment mutated by earlier, unlogged passes; call counts undercount | "For n runs the logged trajectory is the third of three passes on a mutated environment; earlier passes are not recorded." |
| 4 | Iteration-cap cut: trailing calls never executed | head 800 logs / 815 calls; ROPE 675 / 753; AgentDyn 1,683 / 1,800; survey 48 / 49 | `agentdojo.art.max_iters_pending` (head); `q:unexecuted_trailing_calls` | CR | requested-but-unexecuted calls inflate "attempted" sink counts if counted as executions | "Requests cut by the iteration limit are kept as requests without execution." |
| 5 | Outcome-only logs | head 207 (claude-3-opus, outcomes present); ROPE 2 (no outcomes; `ex_5q7qnwlm7e3gp7riq5juw5auqh`) | `agentdojo.art.empty_log` (head); `q:empty_messages_without_outcome` (ROPE) | CR | rates over executions vs over trajectories differ by 207 | as in D.15.5; add ROPE's 2 |
| 6 | **Payload never reached the agent** (no marker on any tool result) | head 5,847 / 32,634 attacked (18 %); ROPE 2,303 / 10,041 (23 %; overstated by B1); AgentDyn 18,368 / 33,091 (55 %: transformers PI 98 %, PIGuard 97 %, PromptGuard 2 53 %, DRIFT 84 %, CaMeL 72 %, tool filter 69 %, no defence 27 %); survey 600 / 2,847 (21 %); Mandate 23 / 369 | new (D.15.3 detector not implemented) | FO | ASR denominators include runs in which the attack could not act; defence comparisons conflate "blocked" with "never exposed" | "x % of attacked runs never surfaced the injected text to the agent; we report ASR over all attacked runs and over exposed runs." |
| 7 | Byte-identical trajectories across injection tasks (deterministic decoding, payload unseen) | head 382 groups / 3,612; ROPE 53 / 396; AgentDyn 655 / 4,120; survey 32 / 299 | new | FO | repeated identical samples reduce effective sample size; per-injection-task ASR differences partly reflect identical runs | "Runs that never read an injected vector are identical across injection tasks; n samples are not independent." |
| 8 | Attack success without exposure (checker true, no payload visible) | head 11 (all banking `user_task_15`, the IBAN confound); ROPE 22 (17 `slack/injection_task_1` AutoDojo; 5 github/shopping `important_instructions`); AgentDyn ≥ 1 | head: `agentdojo.art.banking_ut15_confound` (2024-06 scope); ROPE/AgentDyn new | FO (+RJ candidate) | inflates ASR by false positives of the security check | "n successes occur without the injection in context and are checker false positives (cf. banking user_task_15)." |
| 9 | Vacuous utility (utility true with zero tool calls) | head 182 (banking ut10 77, ut8 50, ut9 40, travel IT6 as user task 14); ROPE 73 (banking ut8 28, ut10 28, ut5 17); survey 4; AgentDyn 2 | `agentdojo.art.validity_defects` (2024-06 scope) | FO | utility overstated on these tasks | "Tasks whose utility check passes without any action are flagged." |
| 10 | **Defences intervene in benign runs** | head PI detector: 81 / 124 benign runs, 278 / 486 tool outputs redacted (57 %); AgentDyn transformers PI 546 / 704 (1,532 / 2,667 = 57 %), PIGuard 389 / 704 (833 / 3,318), PromptGuard 2 3 / 704; ROPE guard 183 / 748 benign runs (425 / 5,238 tool messages denied); Mandate envelope declines in 8 / 9 prepasses; DRIFT 33 / 88 | new | FO | utility cost of a defence; detector false-positive rate; utility-under-attack comparisons | "Detectors redact 57 % of benign tool outputs; guards deny calls in 24 % of benign runs." (per arm) |
| 11 | Tool calls written as text, never executed | survey `qwen3-coder:30b`: 173 runs end after one assistant turn with a `<function=` call in text (160 attacked → all security false, utility false; 13 benign; e.g. `ex_2b7ut33jifals4zeyqmd7uob6l`); head Llama-3.3: 1,040 runs with no structured call; AgentDyn SecAlign-8B 94, Llama-3.3 23; ROPE qwen3 7 turns | head: `agentdojo.art.local_parse_drop`, `.text_tool_call`; survey/AgentDyn/ROPE new | FO (re-parsing forbidden) | "attack resisted" and low utility caused by an output-format failure (survey: 5.6 % of attacked runs, about 17 % of qwen3-coder's) | "n runs fail because the model's tool call was emitted as text and not parsed; they are not defence successes." |
| 12 | AutoDojo injections logged YAML-escaped (log ≠ model-visible text) | ROPE AutoDojo slice: 2,847 files; ≥ 1,166 with escapable payloads | new (D.6.13 item 9 notes the escape) | CR via B1 | payload-exposure statistics computed by string match on the log undercount | "The AutoDojo `injections` field stores the YAML-escaped payload; we unescape it to match tool outputs." |
| 13 | Empty assistant text beside tool calls | survey 8,501 turns; head 6,395; AgentDyn 45,297 | `agentdojo.empty_assistant_text_ambiguous@1` (rule) | CR (`unk ambiguous`) | none if text length is not used as a signal | none needed beyond the datasheet |
| 14 | Provider call-id anomalies | head: absent 4,690 (Cohere), empty 12,583 (Gemini; colliding in 2,725 logs), null 47,227 (local); repeated GPT ids in 213 logs; ROPE null 8,707 (Gemini); AgentDyn null 15,306; positional links (I): head 63,858, ROPE 8,667, AgentDyn 15,069 results | `agentdojo.art.provider_ids` (head absent/empty); repeated ids new | CR | call→result links for these providers are inferred, not observed | as in D.15.5, with the phase-10 counts |
| 15 | Package version not a code identity | head 11,765 `unknown`; ROPE 2,268 (`qwen3-235b`); AgentDyn: `0.1.35` is the fork's own string | `agentdojo.art.package_version_unknown` (head); `q:package_version_not_code_identity` | NR | none on outcomes; limits reproducibility claims | "Logged package versions do not identify the producing code." |
| 16 | ROPE configuration tag names another model | 949 (`qwen3-235b/*/autodojo`) | `q:pipeline_name_not_identity` (`qwen_autodojo_mislabelled`) | FO | model attribution by tag would be wrong | as in D.6.13 item 6 |
| 17 | ROPE released effect-based corrections | 678 recomputed judgements (slack IT5 32→0, dailylife IT7 39→22, github IT1 5→0; AutoDojo arm 88→71) | `q:rope_effect_correction` | RJ (source-released) | ASR differs by which value is used | report both values |
| 18 | CaMeL interpreter feedback logged as user messages; interpreter tool results without calls | 266 logs with feedback messages; 1,977 orphan results in 240 logs (of 386 CaMeL logs) | orphans: `q:camel_orphan_tool_results`; feedback new | CR via B3 | "user turns" and exposure counts for CaMeL are wrong if taken at face value | "CaMeL's interpreter feedback appears as user turns in the logs." |
| 19 | DRIFT in-place isolation leaves payload fragments | 48 attacked runs in a 4,000-row AgentDyn sample, all inspected in `-drift` | partly `q:drift_*` | FO | exact-match exposure undercounts for DRIFT | "Tool outputs in DRIFT runs are post-isolation." |
| 20 | Malformed tool name (a sentence as the function name) | AgentDyn 1 (`ex_amwz4ear7dokydjkrwjokmkl4z`) | new | FO | negligible | none |
| 21 | Separate generations inside AgentDyn variant A | all 648 `gpt-4o-mini-…-drift` logs and the 12 + 2 Progent strays are from April 2026; every other arm from 2026-01-21…26 | new | FO | arms compared across code/time generations | "The DRIFT arm was run three months after the others." |
| 22 | ROPE long-horizon arm records `benchmark_version` v1.2.1 (all others v1.2.2) | 760 | new | FO | the long-horizon arm may run a different suite state | "The long-horizon runs report an older benchmark version label." |
| 23 | Survey README glosses `security` as resistance | all 3,243 | `q:semantic_trap_security_gloss` | FO | README "Security %" is an ASR | as in the profile note |
| 24 | AgentDyn variant-A strays in a Progent directory | 12 (`pipeline_name_mismatch`) | `q:` (table row) | FO | negligible | none |
| 25 | Mandate allows are not logged | 143 inferred allows | `mandate.allow_inferred@1` | CR | "allowed" counts are inferred | "Gate allows are inferred from execution." |

### 8.2 Safety-net results (D.15.3) per corpus

Executions with at least one finding, by artefact id (`artefact.unclassified.*` = no catalogue entry claims it):

| Finding | rope | agentdyn | head | mandate | survey |
|---|---:|---:|---:|---:|---:|
| accounting `agent_calls_vs_assistant` unverifiable | 10,789 u | 38,270 u | 36,447 c | 396 u | 3,243 u |
| pass loss `lost` / `inferred` | 10,789 / 322 u | 38,281 / 826 u | 36,472 / 82 c | 396 / 0 u | 3,243 / 0 u |
| sentinel time `unknown_not_recorded` / `unknown_ambiguous` | 10,791 / 10,791 u | 38,281 / 38,281 u | 36,679 c / **11,765 u** | 396 / 396 u | 3,243 / 3,243 u |
| harness-imposed outcome | 748 u | 5,181 u | 3,546 + 485 + 105 c | 27 u | 406 u |
| unexecuted call | 675 u | 1,683 u | 800 c | 0 | 48 u |
| provider id `absent` / `empty` / `repeated` | 1,496 / 0 / 0 u | 3,062 / 0 / 0 u | 12,061 / 3,773 c / **213 u** | 0 | 0 |
| text-encoded call (heuristic) | 11 u | 1,002 u | 1,208 c | 0 | 174 u |
| empty execution | 2 u | 0 | 207 c | 0 | 0 |
| seal issue (other codes) | 951 u | 1,018 u | **1 u** (`incomplete_run`) | 0 | 0 |

(c = classified, u = unclassified.) The heuristic text-call detector also hits CaMeL's code-writing planner (most of the
685 AgentDyn `gpt-4o-mini` hits are `-camel`/`-drift` arms whose calls are executed by an interpreter), so its AgentDyn
count needs a CaMeL exclusion in the catalogue entry.

### 8.3 Proposed `artefacts.toml` entries (text only; not committed into `src/`)

Catalogue-only unless marked "mapper change". Counts are `status = "verified"` from this analysis.

```toml
[[artefact]]
id = "agentdojo.art.payload_not_reaching_agent"
title = "The injected payload never appears in what the agent read"
description = "Attacked runs in which no tool result carries the payload (SEM injection marker never present). Defences that redact or isolate and agents that never read an injected vector both produce it; the run cannot show an attack effect."
scope = { sources = ["agentdojo", "rope", "agentdyn", "mandate-agentdojo-eval", "agent-security-tools-survey"], parts = ["head", "a", "agentdojo-runs"], profiles = ["agentdojo-upstream", "rope", "agentdyn", "mandate-agentdojo-eval", "survey-runs"] }
cause = "benchmark"
detector = { rule = "artefact.generic.payload_not_reaching_agent", class = "D" }   # needs B5
recorded_as = { sem = ["injection_marker"] }
handling = { class = "FO" }
expected = [
  { snapshot = "head", count = 5847, basis = "phase-10 analysis: attacked runs without a present marker", status = "verified" },
  { snapshot = "a", count = 18368, basis = "phase-10 analysis", status = "verified" },
  { snapshot = "agentdojo-runs", count = 600, basis = "phase-10 analysis", status = "verified" },
]
manuscript = true
refs = ["docs/reports/analysis/phase10-corpus-analysis.md section 8 row 6", "D.15.3"]

[[artefact]]
id = "agentdojo.art.defence_benign_intervention"
title = "Defences redact or deny in benign runs"
description = "PI detectors redact tool outputs and guards deny calls in runs with no attack; the intervention is recorded as a decision and costs utility."
scope = { sources = ["agentdojo", "rope", "agentdyn", "mandate-agentdojo-eval"], profiles = ["agentdojo-upstream", "rope", "agentdyn", "mandate-agentdojo-eval"] }
cause = "upstream_harness"
detector = { rule = "agentdojo.pi_detector_sentinel@1", class = "I" }
claims = []
recorded_as = { issues = [] }
handling = { class = "FO" }
expected = [
  { snapshot = "head", count = 81, basis = "benign runs with a redaction (124 benign detector runs)", status = "verified" },
  { snapshot = "a", count = 938, basis = "benign runs with a redaction, three detectors", status = "verified" },
]
manuscript = true
refs = ["phase10-corpus-analysis.md section 8 row 10"]
# companion entries with detector rope.denial_error_pattern@1 (ROPE 183) and mandate.decline_prefix@1 (Mandate 9)

[[artefact]]
id = "survey.art.text_tool_call_unparsed"
title = "Tool calls emitted as text by qwen3-coder and never executed"
description = "Through the Ollama OpenAI-compatible endpoint, qwen3-coder:30b sometimes writes its call as <function=...> text; no tool_calls are parsed and the run ends after one turn, scored utility false and security false."
scope = { sources = ["agent-security-tools-survey"], parts = ["agentdojo-runs"], profiles = ["survey-runs"] }
cause = "provider"
detector = { rule = "artefact.generic.text_encoded_call", class = "I" }
claims = ["artefact.generic.text_encoded_call#marker"]
recorded_as = { issues = [] }
handling = { class = "FO" }
expected = [{ snapshot = "agentdojo-runs", count = 174, basis = "phase-10 analysis: executions with a text-encoded call (173 end after one turn)", status = "verified" }]
manuscript = true
refs = ["phase10-corpus-analysis.md section 8 row 11"]

[[artefact]]
id = "rope.art.autodojo_payload_escaped"
title = "AutoDojo payloads are logged YAML-escaped"
description = "The AutoDojo attack writes _yaml_escape(variant) into injections; the tool outputs show the decoded text, so string matching on the logged payload misses it."
scope = { sources = ["rope"], parts = ["head"], profiles = ["rope"] }
cause = "upstream_harness"
detector = { rule = "autodojo.payload_cache_link@1", class = "I" }
recorded_as = { notes = ["ext:autodojo.cache_match"] }
handling = { class = "CR", rule = "agentdojo.autodojo_payload_unescape@1" }   # mapper (SEM) change: B1
expected = [{ snapshot = "head", count = 1166, basis = "AutoDojo executions with a visible payload and no marker under agentdojo.suites@1", status = "verified" }]
manuscript = true
refs = ["D.6.13 item 9", "hooks/autodojo.py yaml_escape", "phase10-corpus-analysis.md B1"]

[[artefact]]
id = "rope.art.security_without_exposure"
title = "Recorded attack success with no payload in the trajectory"
description = "Checker-scored security true although no injected text appears in any message; slack injection_task_1 on the AutoDojo arm and five important_instructions runs. Not covered by ROPE's released corrections."
scope = { sources = ["rope"], parts = ["head"], profiles = ["rope"] }
cause = "benchmark"
detector = { rule = "agentdojo.checker_outcome@1", class = "D" }
recorded_as = { sem = ["injection_marker", "outcome"] }
handling = { class = "FO" }
expected = [{ snapshot = "head", count = 22, basis = "phase-10 analysis (payload windows incl. unescaped forms)", status = "verified" }]
manuscript = true
refs = ["phase10-corpus-analysis.md C1, section 8 row 8"]

[[artefact]]
id = "agentdyn.art.camel_feedback_as_user"
title = "CaMeL interpreter feedback logged as user messages"
description = "The CaMeL planner receives interpreter errors as user-role messages; they are not authored by the simulated user."
scope = { sources = ["agentdyn"], parts = ["a"], profiles = ["agentdyn"] }
cause = "upstream_harness"
detector = { rule = "agentdojo.additional_user_message_unattributed@1", class = "I" }
recorded_as = { issues = ["unattributed_additional_user_message"] }
handling = { class = "FO" }   # becomes CR with the B3 hook (mapper change)
expected = [{ snapshot = "a", count = 266, basis = "phase-10 import", status = "verified" }]
manuscript = true
refs = ["phase10-corpus-analysis.md B3"]

[[artefact]]
id = "agentdojo.art.repeated_provider_ids"
title = "Repeated non-empty call ids within a log (GPT)"
description = "A provider call id occurs more than once in one log; linking falls back to position for the affected batches."
scope = { sources = ["agentdojo"], parts = ["head"], profiles = ["agentdojo-upstream"] }
cause = "provider"
detector = { rule = "artefact.generic.provider_id_anomaly", class = "O" }
claims = ["artefact.generic.provider_id_anomaly#repeated"]
recorded_as = { issues = [] }
handling = { class = "CR", rule = "agentdojo.positional_match@1" }
expected = [{ snapshot = "head", count = 213, basis = "phase-10 import (census logs_with_repeated_ids)", status = "verified" }]
manuscript = false
refs = ["D.6.12 item 16"]

[[artefact]]
id = "agentdojo.art.naive_timestamp"
title = "Run start is a naive local timestamp"
description = "v1.k14 logs record evaluation_timestamp without a zone; the run start is ambiguous and never a PROV time."
scope = { sources = ["agentdojo", "rope", "agentdyn", "mandate-agentdojo-eval", "agent-security-tools-survey"], profiles = ["agentdojo-upstream", "rope", "agentdyn", "mandate-agentdojo-eval", "survey-runs"] }
cause = "upstream_harness"
detector = { rule = "agentdojo.naive_local_timestamp@1", class = "D" }
claims = ["artefact.generic.sentinel_time#unknown_ambiguous"]
recorded_as = { issues = [] }
handling = { class = "NR" }
expected = [
  { snapshot = "head", count = 11765, basis = "v1.k14 logs", status = "verified" },
  { snapshot = "a", count = 38281, basis = "phase-10 import", status = "verified" },
]
manuscript = false
refs = ["D.6.12 item 2"]
# claim also agentdojo.naive_local_timestamp_unverified@1 for the I-class profiles

[[artefact]]
id = "agentdojo.art.identical_trajectories"
title = "Identical trajectories across injection tasks"
description = "Deterministic runs that never read an injected vector produce byte-identical message lists under different injection tasks (and, for short runs, different models)."
scope = { sources = ["agentdojo", "rope", "agentdyn", "agent-security-tools-survey"], profiles = ["agentdojo-upstream", "rope", "agentdyn", "survey-runs"] }
cause = "benchmark"
detector = { rule = "artefact.generic.cross_origin_duplicate", class = "D" }   # a content-level variant of the planned detector
recorded_as = { notes = [] }
handling = { class = "FO" }
expected = [
  { snapshot = "head", count = 3612, basis = "382 groups", status = "verified" },
  { snapshot = "a", count = 4120, basis = "655 groups", status = "verified" },
]
manuscript = true
refs = ["phase10-corpus-analysis.md section 4.6"]
```

Widen the scopes of the existing entries (catalogue only) with these counts: `benign_security_constant` (ROPE 748,
AgentDyn 5,176, survey 395, Mandate 27), `run_error_imposed` (AgentDyn 5, survey 11), `silent_rerun` (ROPE 322,
AgentDyn 826), `max_iters_pending` (ROPE 675, AgentDyn 1,683, survey 48), `calls_derived_from_messages` (all),
`injection_task_as_user` (AgentDyn 1,647, survey 105, Mandate 27), `provider_ids` (ROPE null 1,496 logs, AgentDyn 3,062
logs absent/null), `validity_defects` vacuous-utility part (head 182, ROPE 73), `banking_ut15_confound` (head: 11 with
security true without exposure), `empty_log` (ROPE 2 without outcomes); and add `incomplete_run` (head 1, AgentDyn 12),
the D.15.6 ROPE seeds (`rope.art.*`: guard denials 12,657, qwen tag 949, corrections 678), AgentDyn (CaMeL orphans
1,977, DRIFT user decisions 434, redactions 29,317) and Mandate (240 declines, 143 inferred allows).

Which need a mapper change: `rope.art.autodojo_payload_escaped` (B1, SEM), `agentdyn.art.camel_feedback_as_user` (B3);
`agentdojo.art.payload_not_reaching_agent` needs the detector (B5, L3, no mapping change). All others are catalogue-only.

---

## 9. Fix dispositions (2026-10-11)

Decision of the user (2026-10-11): "Just fix the issues that require no corpus change and record the other issues you have
flagged." The standing rule holds: no corpus is regenerated, imported into or re-derived without the user's approval; the
corpora under `~/.agentprov/corpora` were only read. The fixes are commits `afe450c` (B2), `9d029da` (B5) and
`2198b08` (B4) on the branch that applied them (not merged or pushed at the time of writing).

### 9.1 Done (no corpus change)

| # | Disposition | Where | Effect |
|---|---|---|---|
| B2 | **Done.** `verified_complete` only when the seal accounting is `consistent` because at least one check was evaluated, and the unit is an `agent_execution`; otherwise `unverifiable`. `fold_status` and the `aer/0.1` seal are unchanged | `importer.index_completeness` (called by `_index`); spec D.2.9 item 8, HL H.3.2 | No AER, SEM or PROV digest changes. Index rows and `corpus.json` counts of **future** imports only. The existing corpora keep the old value on the affected rows until their next regeneration: head 232 (207 outcome-only + 25 run errors without an assistant turn), ROPE 2, and the phase-9/phase-10 2024-06 corpus likewise. Rows that are verified for a real reason (the golden transcript/v1 traces: 8 of 10 with five or two evaluated checks) are unchanged |
| B4 | **Done.** 17 new catalogue entries and the scopes of the generic entries widened to the phase-10 profiles, with the measured counts as `expected` rows | `adapters/agentdojo/artefacts.toml` (version 1); spec D.15.8 item 12 | None. The artefact-catalogue digest enters no AER, SEM or PROV file (only `agentprov.artefacts`, tests and tools read the catalogue) and no `corpus.json` records it yet. The expected counts were checked by running the safety net, read-only, over the five phase-10 corpora: every count of analysis row 6 is reproduced (ROPE 2,303, AgentDyn 18,368, survey 600, Mandate 23) except the head, where the detector gives 5,895 against the analysis' 5,847 (the analysis denominator is non-DoS attacked executions including the 207 outcome-only logs; the detector excludes outcome-only and includes DoS; not decomposed further). Not added: the identical-trajectories entry of 8.3, because it needs the unimplemented `cross_origin_duplicate` detector |
| B5 | **Done.** Read-only detector `payload_not_reaching_agent` in the safety net, from the SEM injection markers (variants `absent`, `undetermined`, `no_marker`) | `artefacts/detectors.py`, `scan.py` (`scan(..., sem_records=)`); spec D.15.8 item 11 | None (L3, reads only) |

Open item recorded with B5: the safety net, including this detector, is **not wired into `import`** (nor into `stats
--artefacts`, `import --dry-run --artefacts`); `tools/analysis/phase10_extract.py` still calls `scan` without SEM records,
so the analysis tool does not run the new detector. Wiring is a phase-11 task. Also open: D.15.2 says the catalogue is
recorded in `corpus.json`; it is not (B4 note above).

### 9.2 Open: not applied

Each of these changes a digest, and therefore needs the user's approval before any corpus is regenerated. The user has
decided the questions C1 to C6 below (2026-10-11); the implementation of B1, B3 and B6 and of C1 to C3 and C6 is batched
**after phase 11 adds a PROV-only `derive`** (so that SEM and PROV can be re-derived without a full re-import) and before
phase 13, and any corpus regeneration still needs the user's approval.

| # | Not applied | What applying it would change | What must be decided first |
|---|---|---|---|
| B1 | Undo AutoDojo's YAML escape on the payload side of the injection marker when the fixture is AutoDojo-linked (`agentdojo.suites@2`, rule e.g. `agentdojo.autodojo_payload_unescape@1`) | SEM and PROV (assessment bundle) of the ROPE AutoDojo slice (at least 1,166 of 2,847 executions); AER unchanged. A profile version bump changes the profile digest in the SEM and PROV of **every** corpus that uses the profile (the five phase-10 corpora and the phase-9 2024-06 corpus). Re-import time: a full re-derivation of SEM and PROV of those corpora (about 89,000 executions in phase 10 plus the 2024-06 corpus) while no PROV-only `derive` exists | Whether the profile bump is taken once with C1, C2, C3 (they all change SEM or PROV); the marker rule's class and citation (the escape is the attack's own code at `aa458794` l. 76-84) |
| B3 | CaMeL hook: interpreter feedback attributed to the `camel` defence actor; planner context not asserted | AER, SEM and PROV of the 386 CaMeL logs, and the `agentdyn` profile and catalogue digests, hence the AgentDyn corpus (38,281 executions) is re-imported; the warning disappears for 266 | The code check of the vendored CaMeL (does the privileged planner receive raw tool outputs?) before the context change is mapped |
| B6 | Retry inference at class I (an `_unverified` twin) for unpinned harnesses | AER and PROV of 1,148 executions (ROPE 322, AgentDyn 826), completeness counts, and the rule-catalogue digest in every PROV of every corpus (all corpora re-derived) | Decided by C6 (below): this is the fix |

### 9.3 Questions C1 to C6, decided by the user (2026-10-11); not yet implemented

- **C1 (attack successes without exposure): yes.** The semantic layer flags `security = true` executions with no payload
  visible anywhere in the trajectory, as an assessment-only flag generalising the reserved `agentdojo.account_confound`.
  Batched with B1.
- **C2 (disconnected configuration subgraphs): yes.** Add a run-used-the-injected-environment relation (for example
  `used(x:run, x:fx<n>)`) under a D harness rule that cites the suite's environment loading (AgentDojo `task_suite.py`),
  connecting the configuration subgraph. Batched with B1.
- **C3 (partial payloads): yes.** Add a `partial` injection-marker status for payload fragments (DRIFT isolation). Batched
  with B1.
- **C4 (core-only consumers): datasheet statement, no union view.** The datasheet states that analyses of
  inferred-identity profiles must load core plus inference (the scope S(M)). Phase 11 (DATASHEET.md).
- **C5 (cross-model identical trajectories): one read-only upstream check**, being done separately; no change here.
- **C6 (D-rule citation policy): a D rule may be cited only for code its verification block lists.** Add `_unverified`
  class-I twins where a profile's harness code is not verified (unpinned or range profiles) and clarify D.5.4 accordingly.
  This makes B6 the fix (retry inference at class I for ROPE 322 and AgentDyn 826). Batched.

No SEM, PROV or AER code was changed for any of these.
