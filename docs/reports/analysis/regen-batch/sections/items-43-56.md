## Items 43–56 (core review D, `review-fix-core-d`; user-approved 2026-10-14; held, not pushed)

Findings, repros and the fix rationale are in `docs/reports/review-core-d/` (findings CD-15, CD-17..CD-22, CD-28..CD-34).
Two held branches, because the dtap new-family guard (`tests/adapters/dtap/test_new_family_no_core_change.py`) allows one
family per branch: `review-core-d-regen` (agentdojo, foobench) and `review-core-d-regen-dtap` (dtap), both on `3ac26acf`.
Every item moves its family's `adapter_code_sha256` and the SEM stage `engine_code_sha256`. Every verifier found the
triggering shape absent from the pinned or staged data, so no pinned corpus changes bytes beyond the code digests.

| item | finding | branch | commit | stored bytes beyond the code digests |
|---|---|---|---|---|
| 43 | CD-15: `detector_abort` ignores a recorded run error | regen | `2b83a8b6` | llm-lock logs ending at a tool output with `error` set lose a class-I terminate decision |
| 44 | CD-17: capture decisions outside a pass dropped | regen | `800c2bb6` | capture sessions with such decisions |
| 45 | CD-18: rejected redact/modify decision as generator | regen | `9b168818` | sessions with such a decision (was `adapter_defect`) |
| 46 | CD-19: unchecked `{at}` decision subject | regen | `dc49557a` | sessions with such subjects (was `adapter_defect`) |
| 47 | CD-20: discarded reply's list content dropped | regen | `98d9e9ac` | discarded replies with non-string content. **The capture half of CD-13** (`_content` block shapes) waits for RD-1's `mapper.py` rule, so both paths stay identical |
| 48 | CD-21: tool-call arguments through `strict_json_loads` | regen | `27941e8e` | argument strings that are deep, non-strict or duplicate-keyed |
| 49 | CD-22: no fabricated `capture.attempt = 0` | regen | `f0b7d9bf` | sessions with a malformed attempt: no AER (`map.adapter_defect`) instead of a degenerate one |
| 50 | CD-28: conflicted meta batch result | dtap | `3189bda2` | such batches (was `adapter_defect`) |
| 51 | CD-29: unreadable re-run sibling bars co-location | dtap | `e90f18d1`, `17925067` | directories with such siblings: link `unresolved`, no judgements |
| 52 | CD-30: judge key check in `_load_judge` | dtap | `deda303c` | judges missing a key: malformed-judge path |
| 53 | CD-31: judge-only status only for `judge_result.json` | dtap | `8e776404` | judge-shaped files under other names: mapping failure |
| 54 | CD-32: no placeholder vector, no D-tagged null content | dtap | `fd222340`, `0fca4253` | payloads of steps without the field or content member; the `dtap.tools` half is `@2` version-gated, `@1` restored (D-31 owner ruling 2026-10-21; D-607, item 143) |
| 55 | CD-33: FooBench hand-off limit and cycle reported | regen | `af2eb040` | FooBench traces nested deeper than 4 or cyclic; new code `foobench.handoff_not_expanded` |
| 56 | CD-34: bounded digit run in `task_id_relation` | dtap | `0c40feba` | task ids with digit runs over 18 digits (was `adapter_defect` above 4,300) |

**D-31 (owner ruling 2026-10-14: in place, no corpus records v1).** Item 55 adds an issue code to the `foobench`
catalogue and stays at version 1. To meet the ruling's condition, core review B deleted its two foobench scratch
corpora. No profile bytes change in item 55.

**Item 54: `@2` version-gated, `@1` restored (D-31 owner ruling 2026-10-21; D-607, item 143).** The 2026-10-14 ruling first let item 54 change `dtap.tools@1` in place, after the user deleted the
three phase-10b DTap sample-check corpora. The pre-check scratch corpora (2026-10-16) and the phase-10i remap partials
record `@1` again. So item 54's `dtap.tools` half applies only under `dtap.tools@2` (`ITEM_54_SINCE`), and `@1`
behaves as on main before item 54. Its mapper half is unchanged. `review-core-d-regen-dtap` lands with this gated form
(on `bugpass-regen-dtap-sec`, which owns `dtap/semantics/tools.py`).


