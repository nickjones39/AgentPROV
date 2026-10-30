## Items 111 and 112: tacit and geryon profile fixes from the pre-check, wave 2 (2026-10-21; D-587, D-588; user-approved; held branch `claude/artefact-catalogues-family-fixes-6451d3`)

- **Item 111 (D-587):** `tacit-agentdojo@2` declares `agentdojo.local_model_raw_completion` for `pipeline_dir = local`.
  - **Moves:** the AER of every tacit execution (the profile header). In the 1,046 Llama executions, the turns with more
    `<function=` tags than parsed calls gain `ext.agentdojo.local_model_tag_count`, and 444 of those executions gain the
    seal issue `agentdojo.local_parse_drop_possible` (622 issues, pre-check count; the census check is recorded below).
    Then the SEM and PROV of all of them.
  - **Stored corpora:** none.
  - **Fixture pins:** 5 tacit rows of `tests/adapters/agentdojo/phase10d_aer_digests.json`.
- **Item 112 (D-588):** `geryon-agentdojo@2` pins a table whose 14 recorded condition-B rows carry `defence_model`.
  - **Moves:** the AER of every geryon execution (the profile header). In the condition-B executions outside
    `runs-claude-policy`, the `progent` actor gains `model.requested` (class I, the identity rule scoped to `/model`).
    Then the SEM and PROV of all of them.
  - **Stored corpora:** none.
  - **Fixture pins:** 5 geryon rows of the same file.
  - **Code:** `profile.py` admits the row key, and `mapper.py` writes it in `_defence_model`. Profiles without the key
    are byte-neutral.
- **Both:** the `adapters/agentdojo` code digest moves (as item 109). The pre-check scratch corpora record version 1
  (archived, D-31). No `[withhold]` or redaction is added, so those corpora may still be sealed as they are.

