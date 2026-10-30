## Item 148 (D-601 addendum 2; user decision 2026-10-21; held branch `bugpass-regen-d601-sem2`, child of `bugpass-regen-d601-sem`): `inspect.whistlebench@2` from the scorer and task code

- **Change:**
  - New semantics profile version `inspect.whistlebench@2` (D.9.14). It holds a tool table (15 tools) and a C/I
    scorer table (refusal, deliberation_analysis, test_awareness.*, the snitching scorers), read from the pinned
    `highagency/` code. Every entry cites a path, a git blob id and lines; class I.
  - Kept fail-closed: `email_whistleblowing.*` (the scorer is not in the release), `score.*`, unlisted tools and other
    values.
  - The registry part selects `@2`. `@1` stays shipped unchanged.
  - Rules `inspect.tool_table@1`, `inspect.unknown_tool@1` and `inspect.scorer_letter_table@1` are appended to inspect
    v2 in place, under the D-31 addendum with its conditions (a) and (b) (item 133 merge order, `regen_pins --check`).
  - The code fetch: acquisition record `~/.agentprov/migration-work/bugpass/acquisitions.jsonl` (user-approved
    2026-10-21).

| Output | Moves | Count (population) |
|---|---|---|
| SEM of `whistlebench` (`inspect.whistlebench@2` replaces `@1`) | yes: role, integrity and outcome annotations | 9,200 executions |
| PROV (derived with the SEM) | yes | 9,200 |
| index rows (SEM stage, digests) | yes | 9,200 |
| inspect catalogue digest | yes (three rules appended) | every Inspect corpus regenerated afterwards |
| AgentHarm SEM data, other catalogues and profiles, `inspect.whistlebench@1` | no | 0 |
| golden pins | no (`tests/golden`, the Inspect AER pins and tests/repo pass) | 0 |

