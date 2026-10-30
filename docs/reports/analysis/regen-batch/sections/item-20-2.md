## Item 20 (2026-10-12; D-210..D-212) — prediction
Implemented on branch `deferrals-c` (deferrals part C). Measured on the committed golden set, not on a corpus:
- **AER:** every record file changes in exactly two places, the header's `"aer": "0.1"` → `"0.2"` and the seal (its
  digests cover the header). `tests/unit/aer/test_seal.py` checks this on the four C.16 vectors (resealed copies under
  `docs/architecture/examples/C/aer-0.2/`). Record content, ids and evidence are unchanged.
- **SEM, PROV:** every digest moves, because each embeds the AER digest; `tests/golden/prov_digests.json` and
  `gate_d_digests.json` are re-pinned (all entries move, as predicted). The PROV statements are otherwise unchanged
  (`agentprov-prov/0.1` unchanged; on the combined tree the vocabulary is apv 0.2.0 from items 85/86, D-500/D-501, and
  the views and compat moved by items 72/77, not by item 20); `apv:aerVersion` reads `aer/0.2`.
- **Views and compat:** the transcript/v1 view and the compat graphs do not move (gates A1, A2, B pass).
- **Corpus layer:** `corpus.json` `format`/`formats.corpus` `agentprov-corpus/0.2`, `formats.aer` `aer/0.2`,
  `schemas/aer-0.2.schema.json` + `corpus-0.2.schema.json` in place of the 0.1 pair, and the corpus SemVer gets a minor
  bump. `recompute --stages aer` of a 0.1 corpus classifies every execution `changed_explained` (the `aer` stage's
  declared `format` changed).
- **Corpora affected:** all of them (AgentDojo 2024-06 and head, ROPE, AgentDyn, the survey's AgentDojo runs and
  AgentHarm, Mandate, adprov-v1 release, and every later import). The round re-maps them anyway for items 3, 13, 14
  and 17, so this item adds no regeneration of its own.

