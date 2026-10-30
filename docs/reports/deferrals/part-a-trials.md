# Deferrals part A: acceptance trials (2026-10-12)

Scratch corpora only, under `~/.agentprov/migration-work/deferrals/` (never a real corpus). No network: the SEAgent zip
was staged by phase 10f (fetched with consent 2026-10-12); both AgentDojo pins were read from the local fetch cache
through a `Fetcher(allow_network=False)`. The machine was shared with other sessions' test runs (load average about 120),
so the times are upper bounds.

## 1. A two-snapshot AgentDojo corpus (D-202)

One working corpus `agentdojo-upstream` with snapshot `2024-06` (pin `c2748856`) imported first and `head` (pin
`089ed468`) second, release mode, 8 workers, filtered to `runs/command-r/*` (a partial corpus by design: the full pins
hold 18,241 and 36,679 logs; the subset is the one model whose 586 logs are byte-identical at both pins, plus 167 logs
only at head and 167 only at 2024-06). Driver: a library call of `import_source` per snapshot with `GitPinTree`.

| Step | Result |
|---|---|
| import `2024-06` | 753 seen, 753 mapped, 0 degenerate, 0 failed (252 s) |
| import `head` | 753 seen: **586 `dedup.collapsed`** (exactly the byte-identical count computed offline from the two tree listings), 167 mapped, 0 failed (89 s) |
| index | 920 rows: 586 list `["2024-06", "head"]` with `n_origins` 2, 167 + 167 list one snapshot with `n_origins` 1 |
| manifest | `parts` `["2024-06", "head"]`; snapshots in import order, each with its `part`, its pin and its own counts (753 = 753 + 0 each) |
| `verify --level chain` | exit 0: 920 executions and 920 raw objects re-hashed; one `unverified` finding, `checksums.absent` (a working corpus has no `checksums.sha256` until sealed) (37 s) |
| `validate --corpus` | exit 0: 920/920 pass, tiers 1-4, linkage 920/920 (1,002 s) |
| `derive --out` | exit 0: 920 identical, 0 unexplained (28 s) |
| `recompute --dry-run` (re-map from stored raw, both snapshots replayed in import order) | exit 0: **920/920 identical**, 0 unexplained, 0 corpus-file changes (333 s) |

## 2. SEAgent from its Zenodo deposit (D-200, D-201)

`agentprov import seagent-agentdojo --input <staging>/seagent-acsac2026-ae-v2.zip --verify-against-pin --release --jobs 8`
in a **scratch worktree** holding this branch, phase 10f's profile and two scratch-only edits that are not committed
anywhere: the D-204 mapper line (`adapters/agentdojo/mapper.py`: a `member` origin's layout locator is `/label`, routed to
the regen-batch session as DF-1) and the registry part flipped from `planned` to `partial` so the CLI's status gate admits
it.

| Step | Result |
|---|---|
| pin check | name, size 237,707,785 B, MD5 and SHA-256 `e15a8f0f…` all equal the pin; snapshot `pin` recorded with `record` 23218779 (derived from the DOI) |
| expand | 26,033 members: 5,379 selected (the 5,342 logs and the profile's context artefacts), 20,654 `not_selected` (never decompressed), 0 rejected |
| import | 5,342 seen, 5,342 mapped, annotated, derived and validated, **0 degenerate** (1,860 s). 94 executions count as failed because the mapper raises `missing_tool_result` at error severity: a disclosed source fact. **Every issue count equals the phase-10f census:** `missing_tool_result` 94, `orphan_tool_result` 541, `agentdojo.unknown_message_shape` 541, `unattributed_additional_user_message` 863, `unexecuted_tool_call` 317 |
| `verify --level chain` | exit 0: 5,342 executions, 5,379 members, 5,380 raw objects re-hashed; one `unverified` finding, `checksums.absent` (as above) (253 s) |
| `validate --corpus` | exit 0: 5,342/5,342 pass, tiers 1-4, linkage 5,342/5,342 (7,439 s single process, under load) |
| `derive --out` | exit 0: 5,342 identical, 0 unexplained (242 s) |
| `recompute --dry-run` (re-map from stored raw: the stored zip is expanded again) | exit 0: **5,342/5,342 identical**, 0 unexplained, 0 corpus-file changes (2,990 s) |

Without the D-204 mapper line every SEAgent log fails AER-V21 (`aer.locator.dangling`), as phase 10f's
`test_a_member_origin_does_not_seal_yet_d156` pins; the runner side needs no change when the mapper changes.

Both trials pass every acceptance check of the brief (derive, validate, recompute, verify chain).
