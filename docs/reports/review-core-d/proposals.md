# Core review D (review-fix-core-d): proposals for the user

These findings were reproduced (see `findings.md` and `repro/`) and are not plain class-0 bug fixes: each one either
moves a stored code digest (byte class 1) or is new behaviour. Numbers come from `tools/reserve_id.py`: regen-batch
items 43-56, decisions D-480..D-481, routing ids RD-1..RD-3.

**User decisions 2026-10-14.** The orchestrator relayed them, and the user then confirmed them directly in this session:
D-480 and D-481 are approved and built on `review-fix-core-d`. Regen items 43-56 are approved for the round. RD-3 is
assigned to this session, on the held branch, to start only after regen-items-2-12 and pipeline-perf's D-414 land.

**Status 2026-10-15.**
- `review-fix-core-d` (CD-1, CD-2, D-480, D-481 and these reports): full suite green on `3ac26acf`; on main at `7bd6bccb`.
- Regen items 43-56: every item is built, one commit per item with a failing-first test, on two held branches that are
  not pushed before the round. `review-core-d-regen` holds items 43-49 and 55 (agentdojo, foobench).
  `review-core-d-regen-dtap` holds items 50-54 and 56 (dtap); dtap's new-family guard allows one family per branch.
  Commits and byte effects are in `docs/reports/analysis/regen-batch.md` (section "Items 43–56").
- One part is still open: the capture half of CD-13, which item 47 was to carry, waits for RD-1's `mapper.py`
  block-shape rule so the two paths stay identical.
- D-31: item 55 (new `foobench` issue code) changes in place at version 1 (D-31 owner ruling 2026-10-14: in place, no
  corpus records v1; core review B deleted its two foobench scratch corpora to meet that condition).
- D-31, item 54 (`dtap.tools` semantics; updated 2026-10-21): `@2` version-gated, `@1` restored (D-31 owner ruling 2026-10-21; D-607, item 143). Scratch corpora record `dtap.tools@1` again, so
  item 54 applies from `dtap.tools@2` only, and `@1` keeps its behaviour from before item 54. The gate
  (`ITEM_54_SINCE`) lives on `bugpass-regen-dtap-sec`, which owns `dtap/semantics/tools.py` from now on.
  `review-core-d-regen-dtap` lands with that gated form.
- Registry caveats (orchestrator request, class 0): stale dtap, OpenHands and SEAgent caveats corrected; full suite
  green on `d6af9e18`; on main at `7c11d4ce`.
- RD-3 still waits for D-414.

## Decisions (built)

- **D-480 (CD-3; invariant 5).** The generic `[import] variant_labels` check in `adapters/profiles.py` exempted the
  literal DRIFT variant `drift.k18.conversations` for every family. New rule: a label may name a variant that
  `[import] variants` does not declare only when the label is not one of the profile's own parts. Byte class 0, no
  profile bytes change. Commit 9ecadedd; DECISIONS.md and D.6.12 item 12.
- **D-481 (CD-4; NC-AUTO-01).** `coverage_phrase()` no longer counts a registration through a part with `via` set.
  AutoDojo's `rope-slice` is counted under ROPE. **Moves a manuscript number:** "demonstrated on 6 sources in 3
  formats" (was 7). Byte class 0. Commit 74f6102e; DECISIONS.md and I.5.6 rule 2.

## Regen-batch item proposals (byte class 1, approved for the round)

Each item changes a file under an adapter code digest. That moves the family's `adapter_code_sha256` recorded by every
stored corpus of that family. The SEM `engine_code_sha256` moves too, because it hashes the family directories. Stored
AER bytes change only for inputs that trigger the defect. Every item is latent according to its verifier: the
triggering shape was not found in the pinned or staged data checked.

| item | CD | file | change | AER bytes |
|---|---|---|---|---|
| 43 | CD-15 | `adapters/agentdojo/hooks/detector_abort.py:43` | `_abort` returns no decision when the log records a run error (`view.doc["error"] is not None`). `AbortAgentError` leaves `error` null, so a recorded error is another cause, and `outcome_imposed_by_runner` already states it. Code only: the rule text of `agentdojo.detector_abort_after_output@1` stays unchanged, since `agentdojo.rules.toml` is on regen-items-2-12 and rewording it would be a D-31 bump | only llm-lock logs that end at a tool output with an error |
| 44 | CD-17 | `adapters/agentdojo/capture_mapper.py:895-901, :1778` | The redact/modify generator override requires the decision's own pass to be this pass. `_outside_passes` emits decisions whose pass is null or has no boundary in the run scope, as its docstring says, so the dc numbering has no gap | only capture sessions with such decision events |
| 45 | CD-18 | `capture_mapper.py:895-901, :1559` | A tool message falls back to its pre-override generator when the decision was not emitted (`gen[0] not in self._emitted`), so a malformed decision no longer leaves a dangling `generated_by` that turns the session into an `adapter_defect` | only sessions with a rejected redact/modify decision |
| 46 | CD-19 | `capture_mapper.py:1700-1706` | The `{at: {message, call}}` subject resolves only to a dict assistant message that has tool call `call`, using the `_link_tools` offset. Otherwise the decision is malformed (the existing `capture_error` warning), not a dangling part or an `AttributeError` | only sessions with such subjects |
| 47 | CD-20 (+ the capture half of CD-13) | `capture_mapper.py:1336-1338, :1419-1434` | `_discarded_message`: list content becomes text parts (`{type: text, text}`), and any other block or value becomes an `other` part with `agentdojo.unknown_message_shape`, never a silent `parts: []`. `_content`: the same block-shape rule as RD-1's `_content_parts` fix for CD-13 (thinking `id` becomes `signature`; extra keys or non-str content become `other`), so the two paths stay identical | only discarded replies with non-string content; thinking blocks with an id |
| 48 | CD-21 | `capture_mapper.py:1345, :1057` | Tool-call `arguments` strings are decoded with `agentprov.ingest` `strict_json_loads` under the session's limits (depth 256), not stdlib `json.loads`. A decode error, NaN/Infinity or duplicate keys takes the existing ambiguous path (`args_raw` kept, unk `ambiguous`). This fixes the `RecursionError` that turned the session into an `adapter_defect`, and the NaN/duplicate-key values that were recorded as O | only argument strings that are deep, non-strict or duplicate-keyed |
| 49 | CD-22 | `capture_mapper.py:281` | `degenerate_header` writes `capture.attempt` only when the observed value is an int ≥ 0. Otherwise the member is left out and the unit takes the documented `map.adapter_defect` path, with no fabricated `attempt = 0` | only sessions with a malformed `attempt` |
| 50 | CD-28 | `adapters/dtap/mapper.py:790` | `_tool_target` uses `pairing.links` only, the same predicate as `_steps`. A result in a name-conflicted batch becomes an unlinked execution (D.16.7: unk `/call` ambiguous). The env actor is emitted and the te numbering of `_step_issues` agrees | only openaisdk/openclaw/googleadk runs with a conflicted meta batch |
| 51 | CD-29 | `dtap/mapper.py:443-453` | A re-run sibling skipped as unreadable (LFS pointer, strict-JSON failure, non-list trajectory, synthetic) is recorded and cited as supporting, and it blocks colocation rule 2 (`unresolved`, the existing `dtap.judge_attempt_unresolved`). Only byte-identical copies are still skipped silently | only directories with such siblings |
| 52 | CD-30 | `dtap/mapper.py:419-430` | `_load_judge` applies the sniff's key check (`{task_success, attack_success}` ⊆ keys ⊆ `JUDGE_KEYS`). Otherwise `MalformedArtefact` takes the existing malformed-judge path, and no null judgement is cited to a pointer that does not exist | only judges missing a key |
| 53 | CD-31 | `dtap/mapper.py` (`_Build.__init__`), `dtap/dialect.py:334` | Judge-only mapping requires the file class `judge` (`judge_result.json`). A judge-shaped JSON under another name gets a mapping-failure register entry, not an `outcome_only` unit citing `dtap.judge_without_trajectory@1` at D whose premise is false. The D.16.2 table gains a row for `other_json` | only judge-shaped files under other names |
| 54 | CD-32 | `dtap/mapper.py:762-778`, `dtap/semantics/tools.py` (`_prepare`, `_exposures`) | `_payloads`: the vector is `<channel>:<field value>` and tagged D only when the field is a string. Otherwise the vector is left out with unk `/vector` `not_recorded`. A step without its content member gets no `content` and unk `/content` `not_recorded`; an explicit null stays an observed value. The AER refuses a value together with an unk (`aer.unk.conflict`), so the member is left out. `dtap.tools` (`@2` version-gated, `@1` restored (D-31 owner ruling 2026-10-21; D-607, item 143)): under `@2` the `dtap.exposure` annotation cites `/kind` where the fixture has no `/content` or `/vector`, and a payload with no vector takes its channel from the configured step type. Without this, PROV derivation failed with `prov.unresolved_pointer`; the repro is `$AGENTPROV_HOME/migration-work/review-core-d/repro/item54-core-gap/repro.py`. This is a family fix, not a core gap | only configs with incomplete attack steps (none of the 6,892 pinned steps) |
| 55 | CD-33 | `adapters/foobench/mapper.py:78, :840`, `foobench/rules/foobench.rules.toml`, `foobench/profiles/foobench.profile.toml` | `on_handoff` tracks the hand-off chain. When the nesting limit (4) is reached, or a cycle is found, it raises the new warning `foobench.handoff_not_expanded` (detail: the limit or the cycle) and still cites the sub-file artefact. The reference family then no longer teaches a silent truncation. **New catalogue code, in place at version 1 (D-31 owner ruling 2026-10-14: in place, no corpus records v1; the profile is unchanged).** The adapter guide documents the limit | only FooBench traces nested deeper than 4, or cyclic |
| 56 | CD-34 | `adapters/dtap/join.py:56, :131-134` | `task_id_relation` converts a digit group to `int` only when it has at most 18 digits. Otherwise it falls through to `differs` (or the reformat check), so a ValueError above CPython's 4,300-digit limit no longer turns the run into an `adapter_defect` | only task ids with very long digit runs |

## Routed (class 1; the owner branch touches the file)

- **RD-1 → regen-items-2-12** (owns `adapters/agentdojo/mapper.py`), after its push:
  - CD-10 and CD-11: a deny-listed tool name or header string makes an `adapter_defect` AER. Use inspect's
    `ambiguous` handling for tool names; a deny-listed header value becomes `MalformedArtefact`, and
    `degenerate_header` uses the same predicate.
  - CD-12: on the id-link path, every unlinked call gets `missing_tool_result`/`unexecuted_tool_call`.
  - CD-13: the block-shape rule for `_content_parts`. Item 47 mirrors it in `capture_mapper.py`.
  - CD-14: type checks for call ids and block content.
  - CD-16: a calendar-valid `evaluation_timestamp`, or no `start_naive`.
  - CD-23: no positional fallback subject for a hook denial (invariant 2).
- **RD-2 → regen-items-2-12** (owns `adapters/inspect/mapper.py`), after its push:
  - **CD-24 (not latent):** a score event without `scorer` takes the name of its enclosing `scorer` span. This needs a
    new or reused rule; a new rule is a D-31 catalogue bump of `inspect`.
  - **CD-25 (not latent):** non-UTC offsets are converted to UTC, with the original kept in `raw` (C.8.3), and no time
    is dropped. Both CD-24 and CD-25 change AER bytes of the staged whistlebench and fragfuse logs.
  - CD-26: a dangling ground-truth attachment gets `dangling_source_ref` and is kept.
  - CD-27: a non-str `tool_call_id` takes the orphan path.
- **RD-3 → this session** (`adapters/runner/importer.py`; also touched by pipeline-perf and deferrals-c), on
  `review-core-d-regen` after regen-items-2-12 and D-414 land:
  - CD-5: identical members in one run collapse (`dedup.collapsed`) instead of crashing at flush.
  - CD-6: an empty or zero-unit container gets `select.not_execution_artefact` (H.6.1 R1).
  - CD-7: with `--limit`, container and multi-execution candidates are taken one at a time.
  - CD-8: the listing pin is checked over the pre-filter candidates.
  - CD-9: a resumed container drops its stale `map` failure entries (`RegisterLog.discard_failure`; also
    `runner/session.py`, `corpus/register.py`, `corpus/writer.py`).
  - Every RD-3 fix moves the aer stage `engine_code_sha256`. None adds a catalogue code.
