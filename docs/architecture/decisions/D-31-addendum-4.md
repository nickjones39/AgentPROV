- **D-31 addendum (2026-10-23, live profiles for defended pipelines; regen-batch item 167, part 2; addendum 3's rule
  applied).** D-656's core took `agentdojo-live` and `autodojo-live` to v2 and landed first. Scratch corpora recorded
  that v2 before the defence core landed. `agentdojo-live@2` (`b99530f2…`) is recorded by:
  - the live-pilot corpora under `migration-work/live-pilot/` (`agentdojo-local`, `agentdojo-anthropic`,
    `agentdojo-openrouter`);
  - the AgentDojo env rebuild corpus `migration-work/agentdojo-env/rebuild-6d789d59`;
  - a `ci-local` live corpus.

  `autodojo-live@2` (`d8f9486d…`) is recorded by `migration-work/live-pilot/autodojo-local`. All of these were checked
  in their `derivation.json` `profile_sha256` on 2026-10-23. So the defence core takes **v3** for both profiles rather
  than editing v2 in place.
  - Both v2 files ship byte for byte under `profiles/archive/` and are pinned in
    `test_capture_defence.py::test_the_archives_are_pinned`, with the v1 pins.
  - `agentdojo-live` v3 adds the `defences` allow-list (the ten ids of D-671's first set, MELON's three arms
    included), `refuse = "defense not in defences"`, and the six `agentdojo.defence_*@1` instrumentation items.
  - `autodojo-live` v3 adds the same six items and no allow-list.
