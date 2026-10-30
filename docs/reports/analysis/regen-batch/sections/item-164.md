## Item 164 (D-621 amendment 2; pre-round verification V-2, V-3, V-6; branch `integration-fix-verify-tier4` from `8af8adc3`)

**What moves.**
- The validation `engine_code_sha256` moves from `sha256:cea157c5…b05682d3` (`8af8adc3`) to `sha256:b4c5b404…a0dd1c5`
  (this branch): `validate/linkage.py` (V-3, per-rule premise links) and `validate/profiles.py` (V-2, PV-NE-20 over the
  `prov_primary` set of identical-byte twins). Every validation row's stage definition records it.
- No other stage digest moves: prov stays `sha256:6d9cae35…200eac18`; AER, SEM and compat are untouched.
- No AER, SEM, PROV or compat bytes change. No validation row's checks or findings change: 480 documents from the 8
  stored corpora, stored and fresh, pass with no finding (the same sample as item 158).
- The D-550 tier-4 cache: every entry misses once (the package digest is in its key).
- Pins: `tools/regen_pins.py --check` is clean (no pinned digest covers `validate/`).
- **Amended (D-621 amendment 3, from `122fade2`).** The carried-over state binding moves the validation
  `engine_code_sha256` again, to `sha256:7a465893…5d3074ac`. As before, no other stage digest, output byte or
  validation row changes: no adapter declares `apv:EnvironmentCarriedOver`.

