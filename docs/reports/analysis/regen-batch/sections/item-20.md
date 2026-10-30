## Item 20 (built 2026-10-22 on the pre-round integration branch (ac7526c4), with item 151; rides with the aer/0.2 merge, D-210..D-213): capture-mapper declarations aer/0.1 cannot express

Two edits in `adapters/agentdojo/capture_mapper.py` (`agentdojo.capture`), possible only under aer/0.2 (deferrals part
C, branch `deferrals-c`), so they land with or right after that merge, never before:
1. **A live header cut before `instrumentation`** (D.10.4a item 5 as revised on `deferrals-c`; C.21, D-210): the
   member is omitted with `unk {"/instrumentation": "not_captured"}`, instead of today's `"instrumentation": []` with
   `unk ambiguous` (l. 282-286 and the prefix branch at l. 549, which aer/0.1 forces to keep the member).
2. **A redacted required part member** (`text`/`args`/`value`; D.10.4a item 23 on `deferrals-c`): the member is omitted
   with `unk withheld`, instead of keeping the redaction placeholder. Not a `tool_result` part, which keeps text xor
   value under aer/0.2 too (D-211, design §1.2): a redacted tool output keeps its redacted value (re-check RC-1).

**Built** (2026-10-22, with item 151, under the user's part C yes): `test_capture_mapper.py` `..._d210`, `..._d211`,
`..._rc1`. **Digest prediction:** the agentdojo `adapter_code_sha256` moves (class 1, together with item 151's edits);
AER bytes change only for capture AERs with a cut header or a redacted message part, and no committed fixture or vector
has one (no pin moves).

**Checked, not an item (2026-10-12):** `dtap.tools@1`'s `configured_only` exposure annotation cites
`Premise("exec", "/ext/dtap/join")`, which fails SEM-V06 when the profile is run on non-DTap AERs (the C.16 vectors).
The DTap mapper writes `ext.dtap.join` on every mapped AER (`adapters/dtap/mapper.py` l. 573-577, both branches); over
the 500-AER phase-10b DTap sample, `dtap.tools@1` gives 97 `configured_only` annotations and 0 SEM errors. So it is
out of scope (a DTap semantics profile on non-DTap records), not a DTap defect; no regeneration item.

Built 2026-10-22 with the aer/0.2 merge (item 151's section has the details; the user's part C yes covers it).

