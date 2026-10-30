## Item 146 (D-601 addendum; user decision 2026-10-21; held branch `bugpass-regen-d601-sem`, child of `bugpass-regen-d601`): the WhistleBench semantics profile

- **Change:**
  - New semantics profile `inspect.whistlebench@1` (D.9.14; `semantics/inspect.whistlebench-1/tables.toml`,
    `semantics/whistlebench.py`, dispatch in `semantics/__init__.py`). Every tool is fail-closed and no judgement gets
    an outcome; it cites `inspect@2`.
  - New class-I rule `inspect.untabulated_tool@1`, appended to the inspect catalogue v2 in place: "inspect v2 edited in
    place before the round (inspect.untabulated_tool@1, D-601 semantics)" (D-31 owner ruling 2026-10-21, under item
    133's ruling; DECISIONS D-31 addendum). Conditions:
    - (a) it must land on main before the round's first kept import of any inspect-family corpus; after that, inspect
      changes need v3;
    - (b) item 133 (`regen-held-5` `07b322bc`) appends to the same file: whichever merges second keeps both rules,
      appended in landing order with no other line changing, and re-runs `tools/regen_pins.py --check`.
  - The registry part `whistlebench · final-runs` names the profile.
  - Datasheet statement `whistlebench-retry-traceback-account` (known_issues; figures 260, 722).
  - The D-601 end-to-end test now seals with it.

| Output | Moves | Count (population) |
|---|---|---|
| SEM (`sem/inspect.whistlebench-1/`) | new | 9,200 executions |
| PROV (derived with the SEM) | yes | 9,200 |
| index rows (SEM stage, digests) | yes | 9,200 |
| inspect catalogue digest | yes (one rule appended) | every Inspect corpus regenerated afterwards |
| SEM stage code digest (`adapters/inspect/semantics`) | yes | every Inspect corpus with a SEM stage (code drift, D-430) |
| AgentHarm SEM data, other catalogues and profiles | no | 0 |
| golden pins | no (`tests/golden`, the Inspect AER pins and tests/repo pass) | 0 |
| DATASHEET.md of `whistlebench` | one known_issues statement | 1 |

