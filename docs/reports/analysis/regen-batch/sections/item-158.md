## Item 158 (D-621 and its amendment; tier-4 binding checks and the area-E minors of the pre-round review; branch `integration-fix-ultra-validate` from `c4d7b785`)

**What moves.** Predictions are against `c4d7b785` and taken from the live stage definitions (D-451 closures).

| Axis | `c4d7b785` | this branch | Cause |
|---|---|---|---|
| validation `engine_code_sha256` | `a230d7b3…fd98b9008` | `6026f1f1…3c402a977e` | E-1..E-3, #23-#26 (`validate/`) |
| prov `engine_code_sha256` | `b6a4b387…780dcfd0b` | `42eb5529…0e1a0829` | #15, #16, #17, #18 (`prov/rules`, `prov/engine.py`), the catalogue and its archive |
| prov `rules_sha256` = aprov catalogue | v1-slot `b1dab835…5bb9e0b8` (in-place edits on integration) | **v2** `99b6511a…1d99dbe73` | `aprov.n_message@2`; catalogue version 2 |
| compat `engine_code_sha256` | `09204d7b…aea55c53da` | `130e9456…baefb84d6` | `prov/compat/semdiff-map.toml` targets `aprov.n_message@2` (data; the frozen oracle `adprov_v2_3/` is untouched) |

**Output bytes.**
- **Every PROV document** moves:
  - the aprov catalogue digest enters every bundle dk, so every bundle IRI and statement name moves;
  - every message node gains `apv:partOf` or `apv:thread` (with its `/scope` pointer) and cites `aprov.n_message@2` (#17);
  - attributions, AutoExecution starts and delegations that rested on an unknown generator or authorisation disappear
    (#15): the foobench trace's `m5`, `m6`, and live captures with `missing_generated_by`.
  - #16 and #18 move no stored bytes: no stored AER has item-level `unk` on `/input`/`/inputs`, nor duplicate artifact
    digests.
- **Validation rows:**
  - one new check key `pv.linkage.aer_binding` in every row;
  - no valid document fails: 480 documents from the 8 stored corpora, stored and fresh, pass with no new finding.
- **Compat (adprov-v2.3-compat) graphs:** unchanged. **AER bytes:** unchanged. **SEM:** unchanged.
- **Pins:** regenerated with `tools/regen_pins.py --write` (commit `02f1196a`): `tests/golden/prov_digests.json`,
  `tests/golden/gate_d_digests.json`, `tests/adapters/dtap/golden/sem_prov_digests.json`, and
  `docs/compat/semantic-diff.md`. Every other family is unchanged.
- **The D-550 cache:** every entry misses once (the package digest is in its key). The cached round trip is unchanged.
- **D-31:** aprov v1→v2 with v1 archived (`prov/catalogue/archive/agentprov-prov-0.1.v1.toml`, `79b0a1e78dc7…`).
  Stored corpora remain verifiable at v1.

