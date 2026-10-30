## Item 168 (D-710, RH-1: non-finite numbers in source JSON; branch `inspect-rh1` from `a3851cc5`, round-2a follow-up on the window; orchestrator ruling 2026-10-22: lands before the round)

**What moves.**
- Files:
  - `aer/locators.py` (default loads: the `python-json` profile);
  - `ingest/loaders.py` (the additive `nonfinite_objects` option, round 2a R2-3);
  - `adapters/inspect/{dialect,mapper}.py`;
  - `rules/inspect.rules.toml` (issue code `header_nonfinite`, in place at version 2).
- Stage code digests: `stage_definitions.code_sha256` over the D-451 scopes. The value before is `a3851cc5`. The value
  after is `a3851cc5` with exactly these files (D-710 and round 2a), because the window carries other sessions' core
  changes too.
  - aer: every family moves. For example inspect `c416a0b7…2fd95edd` → `fb7b12bb…18e6a090`, agentdojo
    `a9da615b…38fe1ad2` → `361fd4cc…cbd0edbe`.
  - sem: every family moves (`SEM_CLOSURE` includes `aer/locators.py`; R2-2). For example inspect
    `efd8756e…6f755a69` → `bceadd0d…fa361b8d`, agentdojo `57de491c…638e74b8` → `848ad141…1fee9e84`.
  - prov: `6d9cae35…200eac18` → `927ab476…7b9f1804`.
  - validation: `7a465893…5d3074ac` → `f425da8f…00f797fe`.
  - Together: 27 of 27 measured stage digests move.
- The `inspect` catalogue sha moves (the added issue code); its version stays 2.
- **No stored log re-maps differently.**
  - Every stored Inspect header parses strictly, and the `python-json` profile gives the same value for such a document
    (tested).
  - No `register.jsonl` under `~/.agentprov/{corpora,migration-work}` (54 files) records `ingest.number.nonfinite`.
  - The pre-round review (round 2a) resolved 118,135 stored locators identically and re-mapped 352 AgentHarm units
    byte-identically.
  - No AER, SEM, PROV or validation-row bytes change.
- Pins: `tools/regen_pins.py --check` is clean.

