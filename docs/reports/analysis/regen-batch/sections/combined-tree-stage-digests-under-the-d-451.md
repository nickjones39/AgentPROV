## Combined-tree stage digests under the D-451 scopes (pre-round review #24; computed at `c4d7b785`)

One table per stage of the code digests a corpus imported from the combined pre-round tree records in
`derivation.json`, so that a prediction can be checked against the scope a file actually falls in, not against the
seed directories. Computed at the integration head `c4d7b785` with the importer's own `code_sha256` and
`agentprov.stage_scopes` (`aer_scope`, `sem_scope`, `prov_scope`, `validation_scope`) and `raw.members.engine_code_sha256`
(first 12 hex digits). The last two columns show whether three files that several predictions left out are in the
stage's scope: `versions.py`, `raw/members.py` and the registry (`adapters/registry/__init__.py`); ✓ in scope, · not.

| Family | `adapter_code_sha256` (`adapters/<family>`) | aer `engine_code_sha256` (`aer_scope`) | sem `engine_code_sha256` (`sem_scope` of the family's semantics) | aer scope: versions.py / raw/members.py / registry | sem scope: same |
|---|---|---|---|---|---|
| `adprov` | `b8e0eac0699e…` | `a5ccb1456589…` | — (no semantics) | ✓ ✓ ✓ | — |
| `agentdojo` | `ff3ffe3cc6e7…` | `25e4f6a083e4…` | `1943b50345fa…` | ✓ ✓ ✓ | ✓ ✓ · |
| `agentops` | `418ac66d29a5…` | `c53cfed72711…` | `2a7a8ebe6753…` | ✓ ✓ ✓ | · · · |
| `autogen` | `1502e44d9462…` | `8f36e48349e7…` | `3a4551568952…` | ✓ ✓ ✓ | · · · |
| `credleak` | `02b232289596…` | `898b1b6b881e…` | `735b17ff89f0…` | ✓ ✓ ✓ | · · · |
| `dtap` | `abe2bbd1364d…` | `c53cfed72711…` | `d0544444d76a…` | ✓ ✓ ✓ | · · · |
| `foobench` | `7275ed9b9002…` | `898b1b6b881e…` | `1336b6dea4d1…` | ✓ ✓ ✓ | · · · |
| `geminicli` | `20f12f509720…` | `898b1b6b881e…` | `9b4e4c135393…` | ✓ ✓ ✓ | · · · |
| `inspect` | `914e1e63ab51…` | `f3f8048e1eb0…` | `8443b9c96b91…` | ✓ ✓ ✓ | · · · |
| `mcphunt` | `0ce4b7e9462c…` | `17a4934fb454…` | `217bb6754781…` | ✓ ✓ ✓ | · · · |
| `openhands` | `bd9fae8e058a…` | `8f36e48349e7…` | `22d6b8005648…` | ✓ ✓ ✓ | · · · |
| `qwencode` | `f9941ac8f64b…` | `898b1b6b881e…` | `911834f55f69…` | ✓ ✓ ✓ | · · · |
| `wirelog` | `de488fd3cc99…` | `898b1b6b881e…` | `ee58fbcee7e7…` | ✓ ✓ ✓ | · · · |

Family-independent: prov `b6a4b387d906…` (scope: · · ·), validation `a230d7b3025f…` (scope: · · ·), expand `a8ec9819b228…` (`EXPAND_MODULES`: ✓ raw/members.py).

Reading it: `versions.py`, `raw/members.py` and the registry are in every family's aer scope, so a change to any of them
moves every family's aer `engine_code_sha256` and `fn_digest`. Of the semantics scopes only `agentdojo`'s holds
`versions.py` and `raw/members.py` (none holds the registry), so the same change moves the sem stage digest of every
corpus with an `agentdojo` semantics profile and of no other. The prov and validation scopes hold none of the three. A
family's aer digest is shared where the families' extra closures are equal (for example `credleak`, `foobench`,
`geminicli`, `qwencode` and `wirelog` at `898b1b6b881e…`). The table is a snapshot of `c4d7b785`: any later change in a
scope moves the listed digest, as `tests/unit/test_stage_scopes.py` pins the closures themselves.

