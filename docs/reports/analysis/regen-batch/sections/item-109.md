## Item 109: artefact catalogues, corpus pre-check wave 1 (2026-10-21; D-581..D-585; user-approved; held branch `claude/artefact-catalogues-family-fixes-6451d3`)

- **What:** `adapters/agentdojo/artefacts.toml` gains 5 entries and changes 5 (the three ROPE entries, `validity_defects`,
  `defence_benign_intervention`); `adapters/inspect/artefacts.toml` gains 3 entries. Both stay at version 1 (D-585, D-31
  owner ruling 2026-10-21). Spec D.15.8 item 13.
- **Prediction (written before the scan):**
  - **Moves:** the aer-stage `adapter_code_sha256` and `fn_digest`, and the manifest `code_sha256`, of every corpus mapped
    by the `agentdojo` family (stored: agentdojo-upstream head and 2024-06, agentdyn-a, rope, mandate-agentdojo-eval,
    ast-survey-agentdojo) and by the `inspect` family (ast-survey-agentharm). `recompute` reports it as a code-digest
    notice. Under D-546's BF-33 stop-gap the aer reuse cache is off for corpora built before it, so they get a full
    recompute.
  - **Does not move:** any AER, SEM, PROV, index or validation byte. The catalogue is read only by
    `agentprov.artefacts` (`stats --artefacts`, `import --dry-run --artefacts`).
  - **`stats --artefacts` tables:** the new documentation entries claim no finding. `inspect.art.abnormal_finish_max_tokens`
    and `inspect.art.text_tool_call` claim the generic `abnormal_finish#max_tokens` and `text_encoded_call#marker` findings
    of survey AgentHarm, which were unclassified before. `rope.art.security_without_exposure` claims nothing new: its
    detector is a SEM rule and the net reads no SEM rule references.
- **Also in this item (D-589):** three wave-2 codes, `agentdojo.art.defence_authored_message`,
  `agentdojo.art.reported_rows_unbacked` and `geryon.art.author_declared_unusable_arm`, and the namespace `geryon`. As
  with the rest of the item, only the code digest moves.
- **Outcome (differential `stats --artefacts` scan, 2026-10-21):**
  - **Corpora:** the j1 scratch corpora of the ten wave-1 parts (`~/.agentprov/migration-work/artefact-catalogues/scan/`),
    before (the catalogues of `37be83cd`) and after (`013b6e3b`).
  - **Survey AgentHarm,** the only part that changes:
    - 23 `artefact.unclassified.abnormal_finish` findings (`max_tokens`; gpt-oss 2, qwen3:14b 21) are now
      `inspect.art.abnormal_finish_max_tokens`;
    - 12 `artefact.unclassified.text_encoded_call` findings (qwen3-coder) are now `inspect.art.text_tool_call`.

    Both equal the entries' expected counts (the scratch part is the whole 1,056-sample part).
  - **The other nine parts:** identical tables. The documentation entries claim no finding, as predicted.

