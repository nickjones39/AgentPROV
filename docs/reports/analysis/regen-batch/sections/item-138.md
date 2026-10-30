## Item 138 (D-605, bug pass bugpass-perf-10, pre-check PC-01; user decision 2026-10-21: apply D-604; held with `bugpass-regen-credleak`, branch `bugpass-regen-credleak-sec`): credleak account paths in tool output

**Change (class 1).** The credleak mapper redacts third-party account paths in tool output before encoding.
- The profile's new `[[family.credleak.redact]]` rule `account_path` (scope `tool_output`, replacement
  `acct-{span12}`) and `adapters/credleak/redact.py`; rule `credleak.value_redacted@1`, issue `credleak.value_redacted`.
- Model-authored text stays verbatim (D-604). Spec D.19.15.
- D-31: profile `credleak-p15b` 1 → 2 (v1 `1dce158a57ad…` archived), catalogue `credleak` 1 → 2 (v1 `d355a2725e17…`
  archived), semantics `credleak.tools@2` (version 1's tables on catalogue 2; v1 `721620e801f2…` unchanged).
- Part 2 (user decision 2026-10-21): two labelled rules `ls_long_owner` and `ls_long_group` redact account #1's
  `ls -l` owner and group columns in tool output. They are structural patterns that act only when the column's salted
  label is in `labels`; the label was computed out of band, and no name is written.
- Part 1 (user decision 2026-10-21): `[withhold]` rules `account-path-home` and `account-path-users`, generic
  structural patterns (the name class without `-`, so the labels never match), object scope, reason `personal_data`.

**Byte impact.**

| Output | Moves? | Why |
|---|---|---|
| credleak AER (every run) | yes | header `profile` (version 2, new sha256) and `rules.credleak` 2 |
| credleak AER (316 runs with the path in tool output; 4,353 runs with account #1's `ls -l` columns) | yes, content | tool-result label, `evf` `D`, scoped rule, `ext.credleak.redacted`, issue `credleak.value_redacted` |
| sealed corpus (withholding) | yes | 7 more executions and 21 more raw cells withheld (`personal_data`), on top of the 5,422 executions and 325 cells the canary and key rules withhold |
| credleak SEM | yes | `credleak.tools@2`, rules `{credleak: 2}`; annotations unchanged |
| credleak PROV | yes | embeds the AER and SEM digests and the catalogue version |
| `map` stage code digest (credleak) | yes | `adapters/credleak/mapper.py`, `redact.py` |
| other families | no | family-local change; the registry line changes the credleak part only |
| stored corpora | none | no stored corpus records credleak. 14 scratch corpora and the gui-build sealed copy record profile v1, and none is to be deposited (D-605) |

**Census** (pinned v3 zip, in memory, counts only): 382 pointers redacted in 316 runs. **Residue for account #1 in
tool results: 0 runs.** 19 runs in 8 cells keep it in model-authored fields (args 39 pointers, both in the message and
in `tool_execution`, plus 4 in assistant text; PROV `apv:args` in all 19), and 17 of them are already withheld by the
canary and key rules.
- **`ls -l` (part 2):** 22,986 owner and 22,985 group columns of account #1 in 4,353 runs are redacted. **Residue 0;
  collateral 0** (5,757 lines of other owners kept). Runs with the bare token in tool output go from 4,432 to 29, which
  hold it in 30 lines that are not `ls -l` lines (not covered).
- **Withholding (part 1),** with the shipped policy over every raw cell and over the AER, SEM and PROV of all 2,740 runs
  of the 80 cells that can hit the rules: **7 executions newly withheld** (2 of account #1's model-authored residue, 3
  with another non-generic path in model-authored text, **2 with a generic-name path only: a known collateral cost the
  user accepted**). **21 raw cells newly withheld** (18 holding account #1, 3 other). 0 primary runs are withheld beyond
  these 7.

**Decided (user, 2026-10-21).**
- The 92 released raw cells holding the bare token in raw `ls -l` output, and the 30 non-`ls -l` lines, ship as pinned
  (D-186 (c)). They are disclosed by the datasheet statement `credleak-workstation-account-in-raw-tool-output`
  (`known_issues`, figures 92 and 30, source D-605). The release scan gets an accepted triage value (class 0, the
  coordinator's branch).
- The committed fixtures (`tests/fixtures/credleak/`) hold the bare name in the `ls -l` output of 12 of their 124 runs.
  The fixture owner replaces them, with the history kept; this branch does not touch them.
- The release scan's finding of the `acct-<12 hex>` labels is class 0 and handled on a separate branch.

**Tests.**
- `tests/adapters/credleak/test_redact.py` (new). The regression test fails on the old mapper, which copied the name
  verbatim, as the archived profile 1 still does. It also covers the labelled `ls -l` rules, collateral 0, and the
  withhold rules never matching a label.
- `test_withhold_e2e.py::test_a_tool_output_account_path_is_redacted_and_the_model_authored_one_is_withheld`: import,
  seal, then `verify --level chain --release`. Both raw cells are withheld `personal_data` and the model-command run is
  withheld; the tool-output run is released with only the label.
- Golden AER pins regenerated: all 124 fixture runs move in the header, and 12 move in content (`ls -l`).
- `tests/unit/test_d31_bumps.py` (v1 pins).

