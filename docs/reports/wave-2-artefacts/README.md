# Wave-2 artefact scope: census before and after (D-950)

**Date:** 2026-10-29. **Decision:** D-950 (DECISIONS.md); spec D.15.8 item 14. **Data** (outside the repo, ids and counts
only): before, `~/.agentprov/migration-work/wave-2/artefacts/<tree>.json` and `census-summary.json` (wave-2 session);
after, `~/.agentprov/migration-work/wave-2/artefacts/after/<tree>.json` and `after/census-summary.json`.

## 1. Method

- **Read-only, through the queue.** `agentprov stats --artefacts --format json` per tree (`--class import`),
  the command the before census used, against the `.partial` working trees. No corpus tree was written.
- **Detail census.** A scratch script ran the shared layer's `run_detectors` and claim logic over every execution and
  kept, per finding group, the profile, detector, variant, cited rules, seal-issue codes and the entries that would
  claim it if their scope admitted the profile. A structure-only co-occurrence pass checked which findings share
  executions. It recorded record kinds and counts, never content.
- **Rule for a claim.** An entry takes a profile only when the profile's hits cite the entry's rule (directly or through
  its `_unverified` twin) and the profile declares the quirk. Otherwise a source-specific entry cites the rule that
  raises the finding and the profile comment, pre-check dossier or decision that explains it. A finding with no
  documented mechanism stays unclassified (section 3). The pre-check had recommended the same widening (CC-09).
- **Byte class 1** (not 0). The catalogues are inside each family's `adapter_code_sha256`, but no stored corpus
  byte changes and no sealed corpus changes classification (D-950).

## 2. Per tree

Counts are classes (artefact ids) per tree. "Unclassified after" lists the remaining classes with their executions.
Trees imported after the main pass (agentdyn-b, mcphunt-w2b, redcode-exec-openhands) were censused in a second
run. DTap was censused last (section 2.1).

| Tree | Before: classified / unclassified classes | After: classified / unclassified classes | Unclassified after (executions) |
|---|---|---|---|
| `agentdyn-b-w2` | 7 / 0 | 7 / 0 | none |
| `agentdyn-c-w2` | 5 / 2 | 10 / 0 | none |
| `agentops-bench-w2` | 15 / 0 | 15 / 0 | none |
| `aiauthz-agentdojo-w2` | 0 / 5 | 5 / 0 | none |
| `atia-benchmark-w2` | 0 / 2 | 3 / 0 | none |
| `authority-caps-agentdojo-w2` | 0 / 7 | 9 / 0 | none |
| `autogen-guard-placement-w2` | 10 / 0 | 10 / 0 | none |
| `bookkeeper-agentdojo-w2` | 0 / 6 | 6 / 0 | none |
| `ceferisbarov-agentdojo-w2` | 0 / 10 | 10 / 1 | `text_encoded_call` 47 |
| `code-agent-misalignment-w2` | 10 / 1 | 10 / 1 | `text_encoded_call` 23 |
| `controlarena-persistent-w2b` | 0 / 6 | 8 / 2 | `provider_id_anomaly` 459; `unexecuted_call` 3,169 |
| `craibench-agentdojo-w2` | 0 / 6 | 6 / 0 | none |
| `credleak-p15b-w2b` | 3 / 6 | 8 / 1 | `text_encoded_call` 16 |
| `dca-agentdojo-w2b` | 0 / 9 | 14 / 1 | `seal_issue` 4,255 |
| `drift-head-w2` | 0 / 7 | 9 / 0 | none |
| `drift1-agentdojo-w2` | 0 / 7 | 11 / 0 | none |
| `dtap-bench-w2c` | 22 / 3 | 25 / 0 | none |
| `fragfuse-agentharm-w2` | 0 / 4 | 7 / 0 | none |
| `gate-agentdojo-w2` | 0 / 10 | 12 / 0 | none |
| `geryon-agentdojo-w2` | 0 / 8 | 7 / 1 | `text_encoded_call` 1 |
| `glitch-agentdojo-w2` | 0 / 6 | 6 / 0 | none |
| `hilarytorn-trajectory-poisoning-w2` | 0 / 5 | 5 / 0 | none |
| `interbolt-agentdojo-w2` | 0 / 6 | 6 / 0 | none |
| `ipi-defenses-agentdojo-w2` | 0 / 6 | 6 / 0 | none |
| `kavach-agentdojo-w2` | 0 / 9 | 9 / 1 | `text_encoded_call` 7 |
| `kexin-xu-01-agentharm-w2` | 0 / 4 | 7 / 0 | none |
| `kongminos-agentdojo-w2` | 1 / 8 | 9 / 0 | none |
| `linyxus-agentdojo-w2` | 0 / 8 | 11 / 0 | none |
| `llm-lock-agentdojo-w2` | 0 / 8 | 11 / 0 | none |
| `mcphunt-w2b` | 7 / 0 | 7 / 0 | none |
| `melon-agentdojo-w2` | 0 / 6 | 6 / 0 | none |
| `memo-ozdincer-agentdojo-w2` | 0 / 10 | 14 / 0 | none |
| `menelaus29-ipi-multidomain-w2` | 0 / 8 | 9 / 1 | `text_encoded_call` 2 |
| `mohameduk-agentdojo-w2` | 0 / 8 | 8 / 0 | none |
| `openagentsafety-w2` | 8 / 3 | 9 / 1 | `text_encoded_call` 5 |
| `redcode-exec-openhands-w2` | 3 / 2 | 5 / 0 | none |
| `redcode-exec-qwencode-w2` | 7 / 1 | 7 / 1 | `text_encoded_call` 6 |
| `seagent-agentdojo-w2` | 1 / 7 | 9 / 0 | none |
| `sentry-agentdojo-w2` | 0 / 7 | 8 / 0 | none |
| `shreeyavarma-llm-safety-w2` | 0 / 7 | 8 / 0 | none |
| `tacit-agentdojo-w2` | 1 / 9 | 10 / 0 | none |
| `what-surrounds-w2` | 7 / 0 | 7 / 0 | none |
| `whistlebench-w2` | 0 / 7 | 8 / 3 | `seal_issue` 3; `text_encoded_call` 1,515; `unexecuted_call` 10 |
| `yockcheng-prompt-injection-harness-w2` | 0 / 6 | 6 / 0 | none |

Trees with no unclassified class: before 5, after 33. Unclassified classes summed over trees: before 240, after 14.

### 2.1 DTap

- **Before.** `agentprov stats --artefacts --tables counts` with main's catalogue (no before census existed), in
  `after/before/dtap-bench-w2b.json`. Of 67,711 executions, 22 classes were classified and 3 were not:
  `empty_execution#no_messages` 18, `unexecuted_call` 2 (`dtap.call_without_result@1`), and `seal_issue`
  `dtap.content_not_inlined` 1.
- **Basis tree.** The catalogue's `expected` rows name `dtap-bench-w2b`, the tree they were counted on. Its recompute
  version, `dtap-bench-w2c`, supersedes it with identical executions, and the after census confirms the same counts.
- **Entries.** `dtap.art.tool_listing_only` covers the 18 openaisdk trajectories whose only steps are `List MCP
  Tools` meta-steps (record kinds counted: every activity is `dtap:list_mcp_tools`, no message, no user step).
  `dtap.art.call_never_answered` covers D.16.7's 2 claudesdk calls, and `dtap.art.content_not_inlined` covers D-934's
  string. Re-applying the claim logic to the detail census leaves 0 unclassified groups.
- **After.** `agentprov stats --artefacts --tables counts` on `dtap-bench-w2c`, the passed tree: a `recompute --out` of
  w2b at its building commit after ex_suw7, the 210-call run that had failed on the CPU budget, was retried. It has the
  same 67,711 executions and a corrected register (D-981). Written to `after/dtap-bench-w2c.json`. The 3 unclassified
  classes are gone: `tool_listing_only` 18, `call_never_answered` 2 and `content_not_inlined` 1 execution. The one
  other change is `payload_not_observed`, 33,417 to 33,418 executions: ex_suw7 now has SEM, and
  `payload_not_reaching_agent` is the only detector that reads SEM. This matches the prediction before the run.
- **Overlaps already on main.** `dtap.art.harness_default_outcome` and `dtap.art.direct_prompt_constant_task_success`
  both claim the direct_prompt task_success default (5,461 hits). `dtap.art.judge_only_directory` also claims 4 of
  them. The descriptions name the same harness default, so this is one mechanism read at two levels, and the
  catalogue is unchanged there.

## 3. Left unclassified by decision (v0.2)

No source documents the mechanism behind these 14 classes, so no entry claims them. The user decided on 2026-10-29
(relayed by the orchestrator: "go with your recommendation i agree") that they stay unclassified for v0.1. They are
labelled `artefact.unclassified.*`, never filtered out, and listed in chapter 15 and the datasheets. Classifying them
is planned for v0.2 (`docs/roadmap.md`). Each needs evidence from the source or its code, never from the corpus text.

| Tree | Class | Executions | Why it stays unclassified |
|---|---|---|---|
| ceferisbarov, kavach, geryon, menelaus29 (AgentDojo forks) | `text_encoded_call` | 47, 7, 1, 2 | Heuristic detector; these profiles document no text-parsing call path, so `agentdojo.art.text_tool_call` (cause: the prompting parser) is not claimed for them |
| whistlebench, kexin-xu-01 (Inspect) | `text_encoded_call` (named, json; kexin's marker hits are classified) | 1,515; 3 | Heuristic; the named-call variant matches a tool name followed by a parenthesis, often prose |
| credleak-p15b, openagentsafety, code-agent-misalignment, redcode-exec-qwencode | `text_encoded_call` | 16, 5, 23, 6 | Heuristic; no documented call path writes calls as text in these harnesses |
| dca-agentdojo-w2b | `seal_issue` `unattributed_additional_user_message` | 4,255 | Probably CaMeL interpreter feedback, as in AgentDyn (`agentdyn.art.camel_feedback_as_user`), but the DCA profile declares no CaMeL quirk (pre-check PC-dca-agentdojo-07) |
| controlarena-persistent-w2b | `unexecuted_call` (`inspect.tool_event_is_execution@1`) | 3,169 | Calls with no tool event and no denial that are not message copies. The protocol may resample or defer untrusted calls; nothing documents that |
| controlarena-persistent-w2b | `provider_id_anomaly#repeated` | 459 | The 95 message-copy executions do not account for them; the cause is not established |
| whistlebench-w2 | `seal_issue` (dangling, missing result) and `unexecuted_call` (tool event) | 3 and 10 | They co-occur with link conflicts or sample limits; the census cannot separate the two causes |

## 4. Overlaps the descriptions disclose

A round-1 entry's generic `claims` item can also count another mechanism's findings in a mixed profile:

- `agentdojo.art.silent_rerun` counts dca's DRIFT-part single pass (also `drift.art.single_pass`);
- `agentdojo.art.max_iters_pending` counts mohameduk's 12 link-conflict calls and seagent's guard-dropped calls.

Variant qualifiers on those claims would change the sealed round-1 tables, so they were not added.
