## Item 163 (D-640; the `aprov` version in the prov stage definition; branch `integration-fix-aprov-version`, merged with `58952d8b`)

**What moves.**
- The `prov` stage definition gains `rules: {"aprov": 2}`. Its `fn_digest` moves from `sha256:1c17b49d…8a2d9c3c`
  (`58952d8b`) to `sha256:634047bd…052b6fb48` (this branch), in `derivation.json` of every corpus derived or imported
  after it lands.
- No stage `engine_code_sha256` moves: `stage_definitions.py`, `corpus/{derive,authority,manifest}.py` and the corpus
  schema are in no stage closure. The prov code digest stays `sha256:6d9cae35…200eac18` (as at `58952d8b`).
- No AER, SEM, PROV or validation-row bytes change.
- The corpus/0.2 schema pin moves (`13e7233f…`, D-623 + D-224 at `58952d8b`, → `a49367d5…`, D-640, user-approved).
- recompute/verify of a stored corpus now report its aprov v1 as version drift, not `rules.mismatch`, except for the
  three older stored corpora that record the unarchived aprov digest `000598fd…` (`adprov-v1-release`,
  `agentdojo-upstream-2024-06`, `ast-survey-agentharm`; their `-p10` successors record v1): they still report
  `rules.mismatch`, as before (pre-round verification V-5; not a regression).
- It lands with or after item 158 (aprov v2) and before the round's first kept import, so round corpora record the
  version.

