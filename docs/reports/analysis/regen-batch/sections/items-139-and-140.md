## Items 139 and 140 (built 2026-10-21; D-602, D-606, pre-check PC-redcode-exec-openhands-01/-04, PC-openagentsafety-01/-07; user decisions 2026-10-21; held branch `bugpass-regen-openhands-sec`, on `bugpass-regen-openhands`)

- **Item 139 (D-602):** `redcode-exec-openhands` declares `[withhold]` (reason `secret`, pattern rule `hf-token-shape`,
  scope `object`): the supp zip, whose unselected shell history holds a real-format token, is withheld at object level
  by the decoded scan, 0 executions. Census: 2 matches in 1 unselected member of the supp zip, 0 in stored bytes, 0 of
  5,460 primary logs. Takes effect once the archive context tree stores the supp zip (one archive input per snapshot
  today). D-31: no corpus records the profile, so it stays at version 1, edited in place.
- **Item 140 (D-606):** tool-output redaction of third-party account segments (`adapters/openhands/redact.py`, scope
  `tool_output`; `openhands.value_redacted@1`, issue `openhands.value_redacted`); `openagentsafety` rules `account_home`
  and `account_tilde`. Census (1,560 runs): 78 texts in 9 executions, 83 path strings of 10 accounts (the 8 CC-12 (b)
  accounts and 2 task-text names), residue 0; model-authored occurrences kept (22 strings in 2 executions). PC-07: the
  8 secret-shaped values are CC-13 fixtures (D-179 option A); their 49 objects are listed by object digest in
  `docs/reports/bugpass/d606-oas-secret-objects.json`. D-31: catalogue `openhands` and profile `openagentsafety` at
  version 2 (version 1 archived: `9bc984f73823…`, `b5be1d99df75…`, recorded by seven scratch corpora);
  `openhands.tools@2` reads catalogue 2 and both profiles select it.

| stored bytes | |
|---|---|
| AER | every openhands-family AER header: `rules.openhands` 2; `openagentsafety` profile version 2 and its digest; RedCode's profile digest (version 1, in place); the tool messages of 9 OpenAgentSafety executions (`/parts/0/text` labels, `evf` D, the rule citation, `ext.openhands.redacted`) and their seal's info issue; SEM and PROV follow through `aer_digest` |
| SEM | the profile `openhands.tools@2` (digest `946b8e68f427…`; `@1` unchanged at `f7988322c1bd…`) |
| WITHHELD.json, sidecar | a sealed RedCode corpus that stores the supp zip withholds it (object level, 0 executions) |
| stored corpora | none records either profile; the seven scratch corpora at `openagentsafety@1` must never be sealed (no redaction) |
| pins and goldens | no golden, compat or C.16 pin of this family; the family tests re-pinned to version 2 |

