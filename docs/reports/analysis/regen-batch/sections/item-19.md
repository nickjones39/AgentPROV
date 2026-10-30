## Item 19 (implemented, 2026-10-12; gate C3 of the deferrals part-D split; user-approved): the v2.3 scoring rules as versioned rule sets

Routed by the orchestrator (the user agreed the C3 split in the orchestrator's session). This session's part is the new
side; the deferrals session builds the old-side probe `c3`, the comparer, the register entries and the C3 report, and
reports the new side as missing until this item lands.

- **Code.** `adapters/agentdojo/semantics/scoring.py` (B_audit LEG-12):
  `score(rec, row, *, run_error: bool, rule_set: Literal["agentdojo.scoring@1", "agentdojo.scoring@2"]) -> Verdict`.
  `Verdict` is a frozen dataclass `(scored, attack_success, unscored_reason, rerun)` with `as_dict()` giving the
  baseline's dict `{"scored", "attack_success", "unscored_reason", "rerun"}` key for key, which is what C3 compares.
  `rec` and `row` keep the baseline's shapes (`stats.trace_record` fields; an `outcome_replay.json` row or `None`).
  - `@1` is `score_trace` of the baseline (`agentdojo_prov/scoring.py`, 98 lines at `579a908`, tag
    `agentprov-baseline-2026-10-07`, read only) verbatim in its logic: `untargeted`, `MARKER_ON_UNTRUSTED`, the four
    reasons in the same order. The only differences are the signature above and the return type.
  - `@2` is `@1` plus F-60 (legacy §9 S1): `unwinnable` and `rerun_not_reproduced` fire for targeted injections only,
    not for DoS (`@1` gates them on `inj`, which includes DoS, at l. 79-80 and in the reason loop, l. 90). `abandoned`
    and `account` are unchanged.
- **Catalogue (`agentdojo.rules.toml`).** `agentdojo.scoring` (D), `agentdojo.account_confound` (D) and
  `agentdojo.unwinnable_cell` (I) move from `reserved` to `active`, with statements that say what each rule now does
  instead of "Reserved for …". "Active" for the last two means citable by a verdict's `unscored_reason` (`account`,
  `unwinnable`), which `score()` produces; nothing emits them as SEM annotations. `agentdojo.text_tool_call` stays
  `reserved`: `score_trace` never reads it. `agentdojo.scoring@2` is a new entry beside `@1`
  (D-31: a changed behaviour mints a new rule version; `@1` stays active and verbatim). `injection_marker_yaml` is
  already active (item 1). The catalogue's integer version follows the batch's D-31 bump, as for items 3, 13 and 15.
- **Tests.** `tests/adapters/agentdojo/test_scoring_rules.py`: the baseline's `tests/test_scoring.py` cases (J.4's row `(9, 78)`)
  ported against `@1` with the same expected verdicts, plus the F-60 cases for `@2` (a DoS trace
  that is unwinnable or a non-reproduced re-run stays scored under `@2` and is unscored under `@1`), and the activated
  rules leaving `test_reserved_rules_cannot_be_cited`'s list.

**Digest prediction.**
- **If `score()` stays a library function** (called by the C3 comparer, not by `derive`): no AER and no SEM changes.
  The `agentdojo` catalogue digest moves, so the PROV of every corpus that embeds the catalogue changes in one
  `apv:sha256` attribute (the AgentDojo family and adprov-v1, as for item 15). It rides the same regeneration.
- **Not in this item, and needing their own predictions if wanted:** SEM emission of the D.15.5 annotations
  (`account_confound`, `text_tool_call`, `unwinnable_cell`) (D.15.5 names them as SEM annotations; emitting them changes SEM on
  the corpora where they fire), and a scored/unscored verdict in the assessment bundle (D.15.5 `RJ`). The replay-based
  inputs of `score` (`row`) exist only in the baseline environment until outcome replay returns (AD-10 row 2), so
  `derive` could not apply `unwinnable` or the re-run rule anyway.

**Agreed with the deferrals session (plan owner; `docs/reports/deferrals/part-d-plan.md` on branch `deferrals`, "The
split to agree"):** the interface and return shape above; `@2` as read above; verdicts only, no SEM emission;
`text_tool_call` stays reserved. The new side's `rec` is built from AgentPROV records (AER and SEM: judgements, attack
id with null as `benign` as the converter did, re-run from the retry issues, `marker_status` from the SEM
injection-marker annotation, `n_turns`, the two account flags from the replay row) by the deferrals session's comparer
in `migration/`, beside the gate code it belongs to; `score()` takes that `rec` unchanged.

**Implemented (2026-10-12, branch `claude/item-19-scoring`, after items 17 and 18).** `semantics/scoring.py` as above;
the catalogue entries as above (`scoring@2` a new entry); D-18 addendum; D.15 artefact-catalogue text. Tests:
`test_scoring_rules.py`, 27 tests: the baseline's nine cases under both rule sets; F-60 for each DoS family; `@1` equal
to the baseline `score_trace` on 151,632 input combinations (the oracle is the baseline's l. 31-98, embedded verbatim
and, locally, checked byte for byte against `579a908`); `@2` differs from `@1` only on DoS traces `@1` unscored as
`unwinnable` or `rerun_not_reproduced`. Pins regenerated: the `agentdojo` catalogue digest in the golden PROV and gate D
pins.

