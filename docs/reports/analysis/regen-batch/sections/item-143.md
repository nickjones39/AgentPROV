## Item 143 (D-607, bug pass bugpass-perf-10, pre-check PC-dtap-bench-01; user decision 2026-10-21: approved, labels allowlist; held branch `bugpass-regen-dtap-sec`)

**Depends on `review-core-d-regen-dtap`** (items 50–54 and 56, held, `0fca4253`). This branch is built on that one
merged with origin/main, so it lands after it or together with it. The two branches share `dtap/mapper.py`, the
golden digest files and, through item 54, the behaviour of `dtap.tools@1`.

**What changes.** The `dtap` family redacts the five PC-01 harness-host accounts over every AER string
(`adapters/dtap/redact.py`; profile table `[[family.dtap.redact]]`). Only accounts whose salted label is listed are
redacted, and the repository holds no name. D.16.19 and DECISIONS D-607 have the details.

| what moves | before | after |
|---|---|---|
| profile `dtap-bench` | 1 (`04d7c3275399`, recorded by the scratch corpora; archived) | 2 |
| catalogue `dtap` | 1 (`b4df2cb43941`, recorded; archived) | 2 (+ `dtap.value_redacted@1`, issue `value_redacted`) |
| semantics | `dtap.tools@1` (`dec908044648`, unchanged) | `dtap.tools@2` (same tables on catalogue 2; registry selects it) |
| `dtap` `adapter_code_sha256` | — | moves (`redact.py`, `mapper.py`) |
| AER of every DTap execution | header `dtap-bench@1`, `dtap` 1 | header `dtap-bench@2`, `dtap` 2 |
| AER of the 1,094 affected executions | five account names verbatim | 41,312 spans redacted at 17,075 pointers; `ext.dtap.redacted`; info issue `dtap.value_redacted` |
| SEM and PROV of every DTap execution | — | move with the AER digest; the affected ones lose the names |
| goldens | — | all 24 `aer_digests.json` entries and all `sem_prov_digests.json` entries |

**Census (real pinned snapshot, counts only).**
- Mapped: 1,140 executions (every directory with a target); 1,094 with a redaction.
- Redacted per account #1–#5: 3,310 / 8,976 / 21,649 / 6,346 / 1,031.
- Residue: 0 in the AER (path forms, bare words in any letter case, `src`); 0 in SEM and PROV (stride sample of 120).
- Collateral: 0 (no label of the 133 other names is listed; the other accounts are unchanged).
- Withholding: none. Raw ships as pinned (D-186 (c)), disclosed by the datasheet statement
  `dtap-host-accounts-redacted`. Raw path forms are D-457 `account-path` findings with an accepted triage value
  (built by the orchestrator in `tools/` and `release/`).
- The token rules and the case-variant label were kept by the user on 2026-10-21 (label-gated, 0 collateral).

**Merge notes.**
- `review-core-a-regen` also edits `tests/adapters/dtap/golden/sem_prov_digests.json`. Whichever lands second
  regenerates it (`AGENTPROV_REGEN_DTAP_GOLDEN=1`).
- `tests/unit/test_d31_bumps.py` gains `dtap` and `dtap-bench` rows, and other D-60x branches add rows there too: a
  trivial merge.
- The committed fixture F16 holds account #2 once, as a bare token in a tool result. Its AER is redacted now. The
  fixture goes to its owner, who replaces it with history kept (user decision 2026-10-21); this branch does not touch
  it.
- D-31 for item 54: item 54 version-gated under dtap.tools@2 (D-31 owner ruling 2026-10-21). `@1` behaves exactly as on main before item 54 (the scratch corpora of 2026-10-16 and the
  phase-10i remap partials record `@1`), and `@2` carries item 54. **`review-core-d-regen-dtap` must land with this
  gated form**, and this branch is now the only owner of `dtap/semantics/tools.py`. The superseded recorded digests
  are never sealed.

