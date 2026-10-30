## Item 167, part 1 (pre-round, rebuild window 2026-10-22; D-670, D-677): the `defence` catalogue's home

Option taken (orchestrator, 2026-10-22): the one `CATALOGUE_HOMES` line in `aer/rules.py` and the catalogue file
`adapters/agentdojo/rules/defence.rules.toml` (v1) land **before** the round, in the rebuild window with D-656's home and
the Inspect RH-1 change, so every family's `aer` stage code digest moves once, pre-round. Byte-neutral: nothing cites
the catalogue until defended live sessions exist (`tests/unit/test_defence_catalogue_home.py`). The rest of item 167
(live profiles v2, the capture-mapper additions; held branch `defence-backends-core`) lands after the round. **What
moves:** the `aer` engine_code_sha256 of every family (the `aer` seed) and the agentdojo-family code digest (the new
file under `adapters/agentdojo/`); no AER, SEM, PROV or validation bytes. **R1-6 (window review, 2026-10-22):** the
file's citations now name only what the window holds (DECISIONS D-670..D-679 and the design note; the spec section and
the mapper tests land post-round, so `tests = []`); its rules are unchanged. Its sha256 moves `43357925ea97baf7…` →
`6811f03adf2075d3…`.


## Item 167, part 2 (post-round; D-670, D-677; branch `defence-backends-core`): live defended pipelines, the core part

Lands **after** the regeneration round as a deliberate, recorded bump (D-677). The class-0 part (harness, CLI, registry,
fixtures) is on main since `5b1f6fdf`. Until this part lands, every defended live run is refused, because no live
profile on main lists a defence (exit 5).

**What it changes.**
- `agentdojo-live` 2 -> 3 and `autodojo-live` 2 -> 3. It is v3, not v2 edited in place, because scratch corpora record
  D-656's v2 (D-31 addendum, 2026-10-23).
  - `agentdojo-live` v3 adds the allow-list `defences` (the ten first-set ids of D-671), `refuse = "defense not in
    defences"`, and the six `agentdojo.defence_*@1` items in `instrumentation_accepted`.
  - `autodojo-live` v3 adds the same six items, so the two accepted lists stay equal, and has no allow-list.
  - Version 2 of each ships byte for byte under `profiles/archive/`: `agentdojo-live` `b99530f2…` and `autodojo-live`
    `d8f9486d…`, the digests the scratch corpora record. Both are pinned with the v1 archives in
    `test_capture_defence.py::test_the_archives_are_pinned`. The v3 sha256 are `29a4d916…` and `c0c47580…`.
- `family.schema.json`: the `defences` property of `[family.agentdojo.live]`.
- The catalogue `defence` v1 (`adapters/agentdojo/rules/defence.rules.toml`). Its home and first two rules landed
  pre-round (part 1).
  - This part adds `defence.detached_input@1`, `defence.reply_replaced@1` and `defence.sent_before_decision@1` (MELON,
    all D) in place; nothing records the catalogue before this part lands.
  - It fills in the rules' `tests` and cites D.10.11, which is on main.
  - Its sha256 moves `6811f03a…` → `5bf96e6b…`.
- `capture_mapper.py` additions:
  - defence-authored messages: `defence_message` notes; a defence's auxiliary call generates the assistant message it
    names;
  - MELON's detached masked run and its embeddings (input `[]`);
  - an agent reply a defence replaced: the call is discarded `replaced_by_defence`, and the stop message is generated
    by the `modify` decision;
  - a call sent before a later redaction (`sent_before_decision`);
  - the denial reason, and the class-D attribution by declared text;
  - no decision time for a gate decision recorded after the fact (`unk /t not_captured`);
  - the live-versus-native check without native executions of denied calls;
  - `ext.agentdojo.defence` from the `defence_identity` note.

  These sit beside D-656's Messages reading and D-685's dropped calls. The three meet in one `if/elif` arm; each
  branch is exclusive.

**What moves.**
- **AER bytes of live sessions only.**
  - A defended session now maps; before, it was refused.
  - Every live session's header names `agentdojo-live@3` or `autodojo-live@3` (profile digest). Undefended live
    sessions map byte-identically otherwise.
  - No stored corpus is live and sealed. The scratch corpora keep v1 or v2, and `recompute` at main reports their
    profile drift (F-8 ruling).
- **`agentdojo` family code digest** (`adapters/agentdojo/`): the mapper, the two profiles, two new archive files, the
  schema and the catalogue move it for every agentdojo-family corpus. It is the code digest only: imported AER bytes
  are unchanged (D-677: the shared `agentdojo` catalogue is untouched).
- **`aer` stage code digest**: unchanged by this part (part 1 moved it pre-round; `aer/` is not touched).
- **PROV**: none for imports. Defended live sessions cite the `defence` catalogue in the header `rules` map.
