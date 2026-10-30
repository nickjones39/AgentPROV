## Item 30 (implemented, 2026-10-13; D-31 addendum; user decisions, option B): strict integer bumps and the limits digest as a notice

- **Scan:** every stored corpus's `derivation.json` against the package. Changed at an unchanged integer version:
  - catalogues `adprov`, `agentdojo`, `agentdyn`, `inspect`, `rope`;
  - profiles `adprov-v1`, `agentdojo-upstream`, `agentdyn`, `mandate-agentdojo-eval`, `rope`, `survey-runs`.

  Unchanged: `aer`, `autodojo`, `mandate`, `survey`, `survey-agentharm`, `agentdojo.suites@1`, `inspect.agentharm@1`.
  Each recorded digest matches exactly one commit's file. Those bytes are the archived version 1.
- **Change:**
  - The eleven files are at version 2, with `rules/archive/` and `profiles/archive/` holding version 1.
  - `load_profile(id, version)` reads the archive. The corpus lookups pass the recorded version.
  - Current profiles declare the bumped catalogues at 2.
  - `agentdojo.suites`: `CATALOGUE_OF = {1: 1, 2: 2, 3: 2}`. @1 keeps the archived catalogue and its digest
    `2193df73…`. @2 and @3 declare catalogue 2 in place.
  - `inspect.agentharm@2` is @1 on catalogue 2.
  - Option B (user decisions, 2026-10-13): registry parts, profiles and corpus specs that selected `suites@1` /
    `inspect.agentharm@1` select `suites@2` (AgentDyn `@3`) / `inspect.agentharm@2`. So regenerated corpora get item 1
    (B1, the D-86 twins) as approved.
    - Option A was dropped because `package` refused it under H.2.5 (one catalogue version per corpus).
    - A `@1`-equivalent `suites@4` was dropped because it would have left item 1 out.
  - `declared_identity` drops `limits_sha256`, and recompute notes its change.
  - Spec defect fixed (found by workflow-tools): 7279b284 added item 3's I-twins to the C.16.4 (ROPE) block in
    `C_data_model.md`, on `env` and `j0`, without resealing it or updating the vector.
    - The vector, the block and `gen_examples.py` now carry the twins as the mapper writes them, on `env` and on both
      checker judgements `j0` and `j1`.
    - The seal is now `d4654a93…` (was `1d6d2c59…`), and the vector validates.
    - `tests/unit/aer/test_c16_spec_blocks.py` checks that every C.16 block equals its vector and its seal holds.
- **Prediction, checked:**
  - Nothing stored moves before a re-map.
  - At the regeneration's re-map, every AER of the nine stored corpora changes in its header: the `rules` versions and,
    for six sources, `profile.version`/`sha256`. Their SEM and PROV follow through `aer_digest`. The SEM *profiles* of
    stored corpora do not change.
  - `recompute` classes those changes `changed_explained`. Stored Mandate (dry run, `--stages aer`) gives 396
    `changed_explained` with the bumps. With the limits notice but no bumps it gives `rules.mismatch` and 396 `failed`
    (exit 1).
  - Goldens: gate-D, prov and C.16 pins and AER digest pins that re-map with current code move (header versions) and
    are regenerated. The compat gate is unchanged.
- **Tests:** `tests/unit/test_d31_bumps.py` (16):
  - every archived version loads with the recorded digest;
  - versioned profile loading, and an unshipped version refused;
  - option B's declarations;
  - a stored AER and `suites@1` SEM pair (`tests/fixtures/d31`, golden pair R01 from `adprov-v1-release-p10`) rebuilds
    byte for byte;
  - no registry part selects a version-1 SEM profile, and an AER and `suites@2` SEM on catalogue 2 pass tier 4;
  - `limits_sha256` is not a declared version.

### Bug-pass fixes in this branch's code (BF-21, BF-22, BF-28; bug pass `bugpass-perf-10` @ e433967c, 2026-10-14)

Routed by the orchestrator as class 1 (they ride with the items above):
- **BF-21 (security, D-182):** the redaction walked string values only, so a checkpoint model id used as an object key
  (`ext.inspect.model_usage`, copied verbatim) reached the AER unredacted. Keys now go through the same model-id and
  harness rules, the id's JSON-Pointer-escaped form is replaced too (`ext.lex` key-order pointers), and `evf`/`unk`
  keys and scoped rule citations follow a renamed key. Tests: `test_r10p.py::test_a_model_id_as_an_object_key_is_redacted_bf21`
  and `::test_model_usage_keys_are_redacted_end_to_end_bf21` (no plain or escaped path anywhere in the AER).
- **BF-22:** an Inspect tool whose real name is on the C.7.3 deny-list (`none`, `-`, `unknown`) failed AER-V17 and the
  sample became an `adapter_defect` AER. The name is kept verbatim and declared `unk ambiguous` (C.7.2(2)). Test:
  `tests/adapters/inspect/test_bugpass_bf22.py`.
- **BF-28 (D-274):** the DRIFT build gave an isolation decision to every orphan tool message and to the last
  well-formed message before a malformed one inside a batch. "Last of the batch" is now read by role, as DRIFT's
  `injection_isolate` sees `messages[-1]`. Test: `tests/adapters/agentdojo/test_bugpass_bf28.py`.
- **Digests:** none of a stored corpus (no stored Inspect AER has a redact table, a deny-listed tool name, or a DRIFT
  AER); the `adapters/inspect` and `adapters/agentdojo` code digests move with the batch's other changes.

