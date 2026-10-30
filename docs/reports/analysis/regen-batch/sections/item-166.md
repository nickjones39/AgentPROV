## Item 166 (D-656 core: the Anthropic Messages wire in `agentdojo.capture`; branch `anthropic-endpoint-core`; orchestrator ruling 2026-10-22: option A, lands before the round)

**What changes.**
- New: `ingest/sse.py` (bounded event-stream reader), `adapters/agentdojo/messages_wire.py`, the catalogue
  `anthropic_messages` v1 (`sent_form`, `discarded_reply`, `thinking_omitted`) with its `CATALOGUE_HOMES` line in
  `aer/rules.py`, and the provider-`anthropic` branch of `capture_mapper.py` (D.10.4a item 34).
- `agentdojo-live` and `autodojo-live` go to v2; v1 ships under `profiles/archive/` (D-31; the agentdojo-env scratch
  corpus records agentdojo-live@1 = `388950f3…`).
- `stage_scopes.py` pins `ingest/sse.py` in the agentdojo aer closure.

**What moves** (measured before the integration merge, harness head `630b6ad0` → core `de31ac8d`; the integration's own moves, such as item 164's validation digest, come on top):
- Code digests only. `aer/rules.py` is an aer seed and is in the SEM, PROV and VALIDATION closures, so every family's
  aer engine digest moves (agentdojo `53249fed…` → `b9d06688…`, inspect `9e4ce27e…` → `11402136…`, adprov
  `907b488d…` → `62a3d493…`, wirelog `520b996f…` → `c051cee5…`, openhands `09476c04…` → `2eb6f896…`, and the
  rest), as do sem (agentdojo semantics `18e65983…` → `517fe699…`), prov (`6d9cae35…` → `39c3152c…`) and validation
  (`cea157c5…` → `bdcc94d4…`). The agentdojo adapter digest moves (`5a322774…` → `efc8bbae…`).
- No AER, SEM, PROV or validation-row byte moves for any stored corpus. OpenAI-format and import sessions never cite
  the new catalogue, and no stored corpus holds a provider-`anthropic` session.
- Landing before the round makes the digest move free: the round records fresh digests. It lands in the same rebuild
  window as item 167 part 1 (the `defence` home), so every family's aer digest moves once for both. Option B (the
  rules in `cap` v2, moving only the agentdojo digests) was rejected: the `defence` home moves them anyway, and A keeps
  the rules where they belong.

**Rebuild-window review round 1 (R1-1..R1-5, the minors and nits; fixes on top of the window, same item).**
- The SSE readers (core `ingest/sse.py` and the harness `parse_sse`) dispatch only what the pinned SDK dispatches: an
  event ended by a single line terminator, or text after the last terminator, is torn, not dispatched; a BOM is kept;
  a per-line bound. Differential tests: 2,000 streams against the SDK algorithm (core), 20,000 against the real
  `SSEDecoder` (backend).
- The stream rebuild is strict and linear (keyed by event name; `message_start` first, ordered indices, typed deltas,
  nothing after `message_stop`); an inconsistent stream is `anthropic_messages.stream_inconsistent` and nothing is
  claimed from it; an incomplete or torn one is `anthropic_messages.stream_incomplete` (rule
  `anthropic_messages.stream_read@1`; catalogue v1 amended in place, cited by nothing yet).
- `redacted_thinking` agrees with the stock dump; a redacted place of a discarded reply is withheld; `sent_form`
  includes the stock chain-of-thought prefix and refuses an unaccounted `system`; a JSON body must be a `Message`.
- Capture redaction refuses an event-stream blob whose joined delta text holds a secret the bytes do not
  (`cap.redact.split`, fail-closed; class 0, the capture distribution).
- The provider-anthropic fixtures join the generic live gates (K.9.1 with the declared thinking exception).
- **Fixture regeneration:** the capture fixtures are regenerated because the window's guarded-sources commit (D-656,
  `a5c8a8ea`) changes the `identity_digests` note's `guarded_sources`, the only projection difference
  (`make_capture_fixtures.py --check` was stale on the window before these fixes): 17 fixtures moved bytes, 16 of them
  with the new identity (round 3 counted them); `autodojo_aborted_kill` had been regenerated with the stale installed
  harness (its kill path runs `-I`) and is regenerated again in round 3 (below).
- **Digest moves of the round-1 fixes** (review round 3, measured): `aer:agentdojo` `edbd908c…` → `6b332eab…`
  (`ingest/sse.py`) and `adapter:agentdojo` `a432f954…` → `6cd1bcef…`; the other 40 digests are unchanged. No stored
  corpus byte moves.

**Rebuild-window review round 3 (R3-1..R3-6; on top of window `1cac458d`, same item).**
- R3-1: an empty text in a discarded reply (Messages: a stream cut after `content_block_start`, an empty delta, a JSON
  empty text block; OpenAI: content `""`) is declared ambiguous as in `_assistant_message`, so mapping no longer aborts
  on `aer.sentinel` (pre-existing on the OpenAI path).
- R3-2: an event-stream body with no `message_start` (garbage, empty, pings only) is inconsistent
  (`no_message_start`): a discarded reply yields no message, `capture_error`.
- R3-3: both fixture generators refuse to run when the installed `agentprov_backend`/`agentprov_capture` differ from
  the checkout's source (the AutoDojo kill path imports the installed copy under `-I`); `autodojo_aborted_kill` is
  regenerated with the source harness (26 guarded sources, 8 `anthropic_llm`). Both `--check` runs are clean after
  `uv sync --offline --reinstall-package agentprov-backend --reinstall-package agentprov-capture`.
- R3-4: a start block's `input_json` no longer seeds a tool input (core and harness), and the event names the SDK
  forwards besides the six make a stream inconsistent (`stream_read@1` amended in place; nothing cites it).
- R3-5: the split-secret scan reads lines at CR/LF/CRLF only (not U+2028/U+2029/U+0085) and joins multi-line
  `data:` (class 0, capture).
- R2b-1 (review round 2b): the closed `ext.schema.json` (`$defs/message`) declares `thinking_omitted`, `wire_parts`
  and `dropped_calls` (D-685) with exact shapes; `anthropic_benign_banking` had 2 records violating it.
  `test_ext_agentdojo_follows_the_closed_schema` now maps every frozen capture fixture too. `ext.schema.json` is in the
  agentdojo adapter digest (class 1); no AER byte moves.

