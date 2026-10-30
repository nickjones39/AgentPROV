## Item 157 (ultra raw-withhold #10, `raw/members.py` half; USER-APPROVED 2026-10-22, class 1; branch `integration-fix-ultra-b`)

**What changes.** `MemberRow.__post_init__` checks `isinstance(..., str)` before the closed-vocabulary tests on the
parsed `disposition` (`DISPOSITIONS`) and `code` (the `INGEST_CODES` frozenset). A `raw/members.jsonl` row whose `code`
is an array or object raised `TypeError` (unhashable) and escaped every caller that catches `IngestError` or
`AgentProvError` (`decode_members`, `corpus/derive.py` `_relabel_members`, `MemberLog.load` in the writer); it is now
`MembersError` `raw.members.invalid`. The class-0 caller mitigations (`CorpusReader.members()`,
`withhold._released_members`) landed in the ultra raw-withhold #10 commit before this one.

**What moves (class 1).** `raw/members.py` is an `EXPAND_MODULES` file and is in the `AER_CLOSURE` (every family's `aer`
scope) and in the `agentdojo` entry of `SEM_FAMILY_CLOSURE`. Its prediction, computed with
`raw.members.engine_code_sha256()` and `corpus.derive.code_sha256(stage_scopes.aer_scope(f))` /
`code_sha256(sem_scope(["adapters/agentdojo/semantics"]))`, before and after the change on this branch:

| Digest | Before | After |
|---|---|---|
| `expand` `engine_code_sha256` | `a8ec9819…` | `7976aa93…` |
| `expand` `fn_digest` (default limits, empty selection; illustration) | `cc2f260a…` | `0a7deaa6…` |
| `aer` `engine_code_sha256`, adprov | `a5ccb145…` | `5fac92f5…` |
| `aer`, agentdojo | `25e4f6a0…` | `7bd9f198…` |
| `aer`, agentops and dtap | `c53cfed7…` | `42076388…` |
| `aer`, autogen and openhands | `8f36e483…` | `b19a92d6…` |
| `aer`, credleak, foobench, geminicli, qwencode and wirelog | `898b1b6b…` | `2ff4589b…` |
| `aer`, inspect | `f3f8048e…` | `f115de1f…` |
| `aer`, mcphunt | `17a4934f…` | `835fff9b…` |
| `sem` `engine_code_sha256`, any profile set that includes `adapters/agentdojo/semantics` | `1943b503…` | `01a85728…` |

- The `aer` and `expand` values are also moved by every other commit to their scopes; the values above are this
  change's own step. The `prov` and `validation` scopes do not include `raw/members.py` and do not move.
- **`expand`.** The `engine_code_sha256` and `fn_digest` move for **every archive or container corpus** at its next
  import or re-expansion: the `expand` entry of `derivation.json` and the `fn_digest` field of every
  `raw/members.jsonl` row change. Member rows are otherwise unchanged for valid input (digests, labels, methods,
  sizes, dispositions and codes), and so are the member objects and their origins.
- **`aer`** (every family) and **`sem`** (AgentDojo semantics profiles): the stage definitions' `engine_code_sha256`
  and `fn_digest` move, so a recompute re-runs those stages instead of reusing them (D-30). No AER, SEM or PROV byte
  changes: valid rows parse exactly as before.
- **Test pins.** No pinned test file holds an `engine_code_sha256` or `fn_digest` value; `tools/regen_pins.py
  --affected` lists no family for `raw/members.py`.

