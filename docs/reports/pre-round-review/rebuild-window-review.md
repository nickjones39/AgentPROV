# Rebuild-window review (pre-round class-1 pieces)

Date: 2026-10-22. Branch `rebuild-window-2026-10-22`, reviewed against main 32c89f96.

## Round 1: a5f47998 (D-656 core b89f69a5; defence catalogue home cb744d37)

**Method:**
- Workflow `wf_a652bede-a3b`, 45 agents, five finders:
  - `ingest/sse.py`;
  - `messages_wire`;
  - the `capture_mapper` Anthropic dispatch and its catalogue;
  - D-31 and byte neutrality;
  - everything else in the window.
- Every finding had two adversarial verifiers. pytest was serialised machine-wide; the corpus header scan and
  `regen_pins --check` went through main's queue.
- **Data:** `~/.agentprov/review/pre-round/rw1-result.json`. Probes: `~/.agentprov/review/pre-round/probes-rw/`.

### Verdict

**No Important finding, and the window is byte-neutral for stored corpora and existing fixtures.** The D-656 Anthropic
path has a set of Minor defects in stream handling and evidence. They affect only future Anthropic live captures, but
fixing them moves the agentdojo aer digest again, so fix them in the window before the round. The `defence` home needs
its records (R1-6) before the round.

### Byte neutrality and D-31 (checked, sound)

- **Existing fixtures:** all 12 existing OpenAI-format and AutoDojo live capture fixtures were mapped at main and at
  a5f47998. The only AER differences are `profile.version` 1→2, `profile.sha256`
  (agentdojo-live `388950f3`→`b99530f2`, autodojo-live `5d75391f`→`d8f948…`) and the seal digest.
- **v1 profiles:** with the archived v1 forced, the output is byte-identical. The archived v1 profiles are byte-identical
  to main's (`388950f3…`, `5d75391f…`). The v2 diffs are limited to the provider-anthropic additions, and the moves are
  recorded (D-31 addendum, item 166).
- **New catalogues:** `anthropic_messages` v1 and `defence` v1. No committed fixture, golden, gate-D or C.16 vector
  cites either. A queued scan of 392,835 AER headers in 55 stored and scratch corpora found 0 citations, and no
  `corpus.json` or `derivation.json` mentions them.
- **Catalogue digests and lookup:** all 22 existing catalogue files load with identical digests. `CATALOGUE_HOMES` is an
  exact-key lookup, so the new entries cannot shadow anything.
- **Stage digests:** `aer/rules.py` is in every stage scope, so the aer, sem, prov and validation digests of every
  family move (class 1). `ingest/sse.py` joins the agentdojo aer family closure.
- **Tests and pins:** 539 targeted tests pass (golden, gate-D, compat, capture fixtures, stage scopes, D-31, discovery,
  SSE). `regen_pins --check` reports all 17 families current.
- **Outside the pieces:** everything else in the window lies outside every stage closure (class 0). That covers D-664
  egress and sandbox, the AgentDyn backend, the Anthropic endpoint backends and transport, capture endpoints,
  `cli/run`, `formats.py` and GUI G3-G5. The consent and containment gates are unchanged.

### Findings

All are CONFIRMED by both verifiers unless marked. **Stored bytes:** none move. Class 2 means AER bytes of future
Anthropic captures only; no kept corpus holds capture sessions.

**D-656 stream handling** (owner: anthropic-endpoint-core):
- **R1-1 [minor, class 1]: a final SSE event ended by a single line terminator is dispatched with `torn=False`.**
  - `sse.py:56` treats the empty remainder after `split('\n')` as a blank line, so `b'data: x\n'`, `\r` and `\r\n`
    each yield an event.
  - The pinned SDK (anthropic 1.11.0 `SSEDecoder`, differential fuzz of 20,000 streams) never dispatches it, and the
    docstring claims WHATWG behaviour.
  - The harness `parse_sse` (`backends/shared/messages.py:104-122`) has the same bug. So a stream cut at that boundary
    gets a delta the agent never saw, and the capture-time `stream_incomplete` note is omitted (raw evidence that cannot
    be recomputed).
  - **Fix:** pop the split's tail as unterminated in both parsers, and add the three EOL cases to the tests.
- **R1-2 [minor, class 2]: `_assemble` (`messages_wire.py:100-145`) accepts inconsistent or incomplete streams, and the
  discarded path emits them as observed replies.**
  - The accepted cases: non-JSON events skipped, a duplicate block index overwriting, deltas applied regardless of block
    type, events after `message_stop` applied, no `message_start` required, and `kind` taken from the payload rather
    than the SSE event name.
  - **Effect:** a discarded call cut after one `text_delta` maps to an O-class message "Partial ans" with no `unk` and
    no issue. A non-SSE body under the SSE media type gives an observed message with null text.
  - **Fix:** refuse an inconsistent stream (error → `capture_error`), and declare an incomplete reply (`complete=False`)
    with an issue or `unk`.
- **R1-3 [minor, class 1]: an incomplete or torn reply stream is not disclosed in the AER.** The harness
  `stream_incomplete` note and `WireReply.complete` are ignored by the mapper.
- **R1-4 [minor, class 1-2]: a reply with a `redacted_thinking` block never agrees with the stock dump.** So a faithful
  kept reply is reported as `capture_reply_mismatch` and loses `generated_by`.
- **R1-5 [minor, class 1]: the redacted text of a discarded Messages reply is kept as observed text instead of being
  declared withheld** (D-211: text of a text part).
- **Minor and nit, same owner:**
  - quadratic delta concatenation in `_assemble`: minutes of CPU on a 64 MiB hostile stream (minor);
  - SSE memory is 15-18× the body, and there is no per-line bound and no property or fuzz tests, though the design note
    promises them (minor);
  - the `sent_form` rule omits the stock COT system-prompt prefix and does not report an unaccounted request `system`
    member (minor);
  - `match_inputs` and a request `system` member with no system native (PLAUSIBLE, minor);
  - `decode_reply` treats any JSON object as a reply and ignores `message_start`'s `stop_reason` and content (nit);
  - the stream rebuild keys on the payload type and strips a BOM, unlike the SDK (nit);
  - the Anthropic capture fixtures are outside the generic live gates (SEM, PROV, tier 4, live vs native) in CI; a probe
    showed they pass (nit).
- **PLAUSIBLE [minor, class 0]:** a secret split across SSE deltas evades capture redaction, and `decode_reply`
  reassembles it. One verifier refuted it.

**Defence catalogue home** (owner: defence-backends / DECISIONS):
- **R1-6 [minor, class 0, records; land before the round]: the home lands with none of its records.**
  - `aer/rules.py:75` cites D-670 and D-677 and "invariant-5 note in AGENTS.md". None of D-670..D-679 is in
    DECISIONS.md at a5f47998, and AGENTS.md has no `defence` invariant-5 note.
  - `defence.rules.toml` cites a spec section (D.10.11), a design note, tests (`test_capture_defence.py`) and a harness
    file (`defences.py`) that do not exist at this commit. They live on the unmerged 073640af and f360a740.
  - Since every family's stage digests now include this core edit, the round's corpora would name a commit whose core
    change has no recorded reason.
  - **Fix:** land the D-670..D-679 records and the AGENTS.md note with it. Either mark the catalogue's forward references
    as pending or land them together.
- **Records [nits]:**
  - D-656 and item 167 name only the aer digest, while every family's aer, sem, prov and validation digests move (via
    `aer/rules.py`), and the live profile digests are recorded only in the D-31 addendum.
  - The D-31 addendum says no derivation records autodojo-live v1, but a scratch corpus created after the addendum does.

**Outside the pieces:**
- **R1-7 [minor (PLAUSIBLE, filed as Important), class 0; owner D-664 live egress]: the egress proxy records
  T2-chosen CONNECT targets verbatim in `corpus.json`.**
  - Path: `egress.py:244-245`, `_label` `:92-93` (accepts `[A-Za-z0-9._:-[]]{≤255}`), then `summary()['refused']`,
    then the manifest live block (`run.py:1666`).
  - No Redactor or secret scan is applied on that path. So code in a contained T2 can write a key-shaped string, for
    example its own API key as a CONNECT target, into the working manifest, bypassing T0's fail-closed scan. The probe
    reproduced it.
  - One verifier rated it Minor and outside the pieces.
  - **Fix:** record only a digest or a count for non-allowlisted targets, or pass the labels through the secret scan.
    Do this before real-model runs with containment.

**Refuted:** the defence "nothing cites it" test only matching rule-id strings (it also checks rules maps).

## Round 2a: inspect-rh1 at f0ec8754 (branch b31514be; D-710, RH-1)

**Method:** workflow `wf_f822ebf4-376`, 16 agents: two finders (D-710 locators; Inspect non-finite header), with two
adversarial verifiers per finding. Data: `~/.agentprov/review/pre-round/rw2a-result.json`.

### Verdict

**Byte-neutral for stored corpora, and no Important finding.** One Minor crash (R2-1) should be fixed in the window,
since its fix is class 1. The rest are records and nits.

**Checked and sound:**
- **The D-710 profile change:** python-json differs from the strict profile only in `parse_constant` (NaN, Infinity and
  -Infinity become `{"$float": …}`). Every document that parses strictly gets the same value. Every other strictness rule
  is unchanged: byte cap, BOM, UTF sniff, duplicate keys, digit cap, overflow, depth with the +1 for `$float`, lone
  surrogates. Memory stays within the bounds the strict profile already allows.
- **Neutrality on stored corpora:**
  - A queued, read-only resolution of 118,135 evidence locators from 2,192 executions in the 8 stored p10 corpora gives
    byte-identical results at a5f47998 and f0ec8754.
  - All 126,351 stored validation rows have 0 dangling locators, so no stored verdict can flip.
  - An in-process re-map of 352 AgentHarm units gives identical AER bytes, validation and register rows. The new
    `inspect.header_nonfinite` issue fires 0 times.
- **The value is kept, and its scope is narrow:** a non-finite constant is kept as `$float` and never mapped, since
  `/results` and `/stats` are not read by the mapper. A non-finite number in any other member still keeps the log
  planned (`ingest.number.nonfinite`).
- **D-31:** inspect v2 is edited in place, which is allowed: only the four ast-survey-agentharm corpora cite inspect,
  all at v1 (archived and untouched), and none is sealed.
- **Tests and pins:** 317 + 163 targeted tests pass; `regen_pins --check` reports the affected families current.

### Findings

No stored bytes move from any of them.

- **R2-1 [minor, class 1; owner inspect-rh1]: `load_header` (`dialect.py:108-110`) crashes with `IndexError` when
  `header.json` is a bare non-finite constant** (`NaN` at the root).
  - Cause: `_float_pointers` yields the root pointer `""`, and `"".split("/")[1]` raises. That is not an `IngestError`,
    so the reader's plan and the mapper do not catch it.
  - At a5f47998 the same log was `select.dialect_planned`. Untrusted input must produce a typed error.
  - Fix: handle the root pointer (refuse with `ingest.number.nonfinite`), and add the case to `test_rh1_nonfinite_header`.
- **R2-2 [minor, records]: D-710 Downstream and item 168 leave out the SEM digest move.** `SEM_CLOSURE` includes
  `aer/locators.py`, so the sem engine digest of every family moves too. The values were measured from a3851cc5.
- **R2-3 [nit, class 2 for future logs only]: `_float_pointers` also counts literal one-key `{"$float": str}` objects
  from the source.** So the issue count can overstate, and a literal `$float`-shaped object under a mapped member could
  refuse a valid log.
- **R2-4 [nit]:** the resolver accepts a pointer into the parse-made `$float` object, and the C.9.2 amendment calls the
  resolved values C.11.3. No stored locator is affected.
- **Refuted:** "the D-710 strictness test covers only three properties".

## Round 3: re-check of the R1 and R2 fixes (bcfbd634, b9e171f4)

**Fixes checked:**
- R1-7: 596743a6;
- R1-6: e7ceb502;
- D-656 R1-1..R1-5 with the minors and nits: ca54fe23, all on bcfbd634;
- R2-1..R2-4: e90d35e7, merged at b9e171f4.

**Method:**
- Workflow `wf_418c9147-e04`, 37 agents, three groups (D-656; fixtures; R1-6, R1-7 and cross), with two adversarial
  verifiers per residual. Each fix test was run against the pre-fix code at f0ec8754, and the round-1 probes were re-run.
- The R2 fix was checked by hand: a probe at bcfbd634 and b9e171f4, with the new tests run against the old code.
- Data: `~/.agentprov/review/pre-round/rw3-result.json`.

### Verdict

**The R1 and R2 fixes hold, and nothing stored moves.** Three new Minor residuals: fix R3-1 and R3-2 in the window
(class 1, agentdojo adapter digest); fix R3-3 (test data) before the round. The rest are nits and records.

### Fixed (test fails before, passes after, unless noted)

- **R1-1:** a final event ended by one EOL is no longer dispatched, in both readers. A differential fuzz of 20,000
  bodies against the pinned anthropic 1.11.0 SDK decoder, in random network chunks, gives 0 mismatches. f0ec8754 had
  2,922.
- **R1-2:** inconsistent streams are refused (all nine round-1 forms) and incomplete replies are declared. Partly: see
  R3-2.
- **R1-3:** `stream_incomplete` and `stream_inconsistent` issues come from the blob, so they can be recomputed.
  `anthropic_messages` v1 is edited in place, which D-31 allows: a queued scan of 392,835 headers in 55 corpora found 0
  citations, and no golden cites it.
- **R1-4:** a reply with `redacted_thinking` keeps `generated_by`.
- **R1-5:** a discarded reply's redacted text is withheld, matching the OpenAI twin.
- **Minors and nits:** the linear joins (its test also passes before, so it is a coverage test), the per-line bound and
  the fuzz tests, the COT prefix, the unaccounted `system` member, `decode_reply` strictness, and event-name keying with
  the BOM. The split-secret scan works, with residual R3-5.
- **R1-6:** D-670..D-679, the AGENTS.md note and the design note exist, and every catalogue citation resolves.
  `defence` v1 is edited in place (`43357925`→`6811f03a`), which is allowed since nothing cites it.
- **R1-7:** the egress summary records no worker-chosen string (the synthetic key was verbatim at f0ec8754 and is absent
  at bcfbd634). The BLAKE2b key stays in memory.
- **R2-1..R2-4:**
  - a bare NaN header now gets a typed refusal;
  - only parse-made `$float` objects are counted, by identity;
  - the legitimate `/results` and `/stats` cases and deep nesting are unchanged;
  - 5 new tests fail on bcfbd634 and pass on b9e171f4, and 385 targeted tests pass;
  - item 168 now records the SEM move and the `loaders.py` edit, and the C.9.2 wording is fixed.
- **Fixtures:**
  - **What changed:** of the 17 capture fixtures, 16 changed only `guarded_sources` in their identity note (the 8
    `anthropic_llm` entries added), plus declared time, id and path noise.
  - **Determinism:** `make_capture_fixtures --check` passes.
  - **Verification:** `capture/0.1 verify` seals all 17.
  - **AER output:** for the 12 non-Anthropic fixtures, the old and new mapper code give byte-identical AER. Only
    `anthropic_torn_stream` gains its `stream_incomplete` issue.
  - **Pins:** current for 18 families.
- **Byte moves:**
  - the R1 fixes move only `aer:agentdojo` (`edbd908c`→`6b332eab`, `ingest/sse.py`) and `adapter:agentdojo`
    (`a432f954`→`6cd1bcef`);
  - the R2 fix moves the stages that include `ingest/loaders.py` and `adapters/inspect`;
  - no stored corpus byte moves.

### Findings

- **R3-1 [minor; one verifier rated it Important; class 1 (AER of future captures); owner D-656, and the OpenAI path's
  owner]: a discarded reply with an empty text block makes the whole capture session fail to map.**
  - Cause: `_messages_discarded` (`capture_mapper.py:1557`) and `_discarded_message` (`:1490`, `:1495`) write
    `{t: text, text: ''}` without the `unk ambiguous` that `_assistant_message` adds. The release-only validator check
    `aer/validate.py:835` then raises `aer.sentinel`, and `AerWriteError` aborts `map_session`.
  - Triggers: a stream cut right after `content_block_start`, an empty `text_delta`, a JSON message with an empty text
    block, or an OpenAI discarded reply whose content is `''`.
  - This predates the window (f0ec8754 behaves the same).
  - Fix: tag `''` as `ambiguous` in both builders, with a test per path.
- **R3-2 [minor; class 1; owner D-656]: R1-2 residue.** A discarded event-stream body with no accumulated event
  (garbage, empty or ping-only) still yields an observed message `generated_by` the call, with `{t: text, text: null}`,
  ev O and no `unk`; only `stream_incomplete` is added. The pinned SDK never had a message there, because
  `get_final_message` asserts on `message_start`. Fix: no message (`capture_error`), or declare the text `unk`.
- **R3-3 [minor; class 0, test data; owner the fixture generator]: `autodojo_aborted_kill` was regenerated with the
  stale installed harness.**
  - Its `guarded_sources` has 18 entries and no `anthropic_llm`, where the other AutoDojo fixtures have 26.
  - Cause: `_kill()` starts the worker with `-I`, which drops the `PYTHONPATH` to the worktree's
    `backends/shared/src`, so the environment's non-editable pre-D-656 `agentprov_backend` ran. `--check` passes because
    it uses the same stale install.
  - Fix: regenerate the fixture from the current source, and pass `sys.path` or reinstall.
  - **Operational:** `~/.agentprov/envs/autodojo-aa458794` and `agentdojo-79922295` still hold the pre-D-656 harness, so
    live runs need the planned environment rebuild.
- **R3-4 [nit]:** `stream_read@1` differs from the SDK on two hostile-only inputs (a start block carrying
  `input_json`, and one other).
- **R3-5 [nit]:** the split-secret scan misses splits where a piece holds a raw U+2028, U+2029 or U+0085, or the data
  spans several `data:` lines. The cause is `str.splitlines()` and single-line `data:` only.
- **R3-6 [records, nits]:**
  - item 166 does not record the R1 fixes' `aer:agentdojo` and `adapter:agentdojo` moves, and miscounts the regenerated
    fixtures (17 moved bytes; 16 changed identity);
  - af64fb20 (GUI) cites D-725 and D-726, which are not in DECISIONS.md;
  - the defence design note still names the old rule id;
  - the egress manifest shape (R1-7) has no D-664 decision record (PLAUSIBLE);
  - no test keeps the defence catalogue's citations resolving.

## Round 2b: agentdyn-quirk-pre at 1cac458d (51125a03; D-685 (b))

**Method:** the piece is small (about 70 lines in `capture_mapper.py`, one rule, records), so it was reviewed directly,
with deterministic probes instead of a workflow:
- all 17 committed capture fixtures were mapped at 1cac458d^1 (b9e171f4) and at 1cac458d;
- the AERs' `ext.agentdojo` was validated against the closed ext schema;
- the stored AgentDyn headers were scanned read-only;
- 163 targeted tests went through the lock wrapper, and `regen_pins --check` went through the queue.

Probes: `~/.agentprov/review/pre-round/probes-rw5/`.

### Verdict

**Byte-neutral, and the D-31 owner condition is met.** One Minor finding (R2b-1, a closed-schema gap that also covers a
D-656 field already in the window) and one test gap (R2b-2).

**Checked and sound:**
- **Gating:** the recognition runs only under a profile declaring `agentdojo.malformed_tool_call_dropped`, and not for
  the Messages API (`not self.messages_api`). No profile in the window declares it: only `agentdojo-live` and
  `autodojo-live` exist, and the test pins `declaring <= {"agentdyn-live"}`. So the path is inert for every stock and
  AutoDojo session, and the `agentdyn` catalogue is added to the header only under the quirk.
- **Stock and AutoDojo bytes:** all 17 fixtures map to byte-identical AER records before and after, with the same issue
  codes.
- **D-31:** `agentdyn` v2 is edited in place before the first kept import. The stored AgentDyn corpora (`agentdyn-a-p10`
  and its pre-integration copy) record `agentdyn` v1 in every sampled header, and v1 is archived. `regen_pins --check`
  reports all 18 families current.
- **Evidence:** a dropped call is listed under `ext.agentdojo.dropped_calls` (class D, `src` into the response blob, the
  rule scoped to the field), with no tool execution, relation or taint. The decision uses the bounded strict loader,
  never stdlib `json`. Where the strict loader is stricter than AgentDyn's `json.loads`, the call counts as dropped, the
  names disagree and the reply is reported unmatched, so it fails closed. The rule is class D, with its code citation
  pinned to AgentDyn 5353cf76.

### Findings

- **R2b-1 [minor; class 1 (`ext.schema.json` is in the agentdojo adapter digest); owners D-656 and D-685]: the closed
  agentdojo ext schema does not allow three message ext fields the capture mapper writes.**
  - The schema's `$defs/message` is `additionalProperties: false` and lists 8 properties. The mapper also writes:
    - `thinking_omitted` (D-656, `capture_mapper.py:1497`);
    - `dropped_calls` (D-685 (b), `:1815`);
    - `wire_parts` (`:1864`; already absent from main's schema, so pre-existing).
  - Probe `extcheck.py`: the committed fixture `anthropic_benign_banking` already violates the schema (2 records,
    "'thinking_omitted' was unexpected"). `dropped_calls` would do the same once `agentdyn-live` enables the quirk.
  - `test_ext_agentdojo_follows_the_closed_schema` runs only on two synthetic sessions, so it misses all of this. The
    schema is a test-time contract, not enforced at write time, so no AER is refused; but the closed-schema promise of
    D.4 does not hold.
  - Fix: add the three fields to `$defs/message`, and run the closed-schema test over `live_sessions()` too.
  - Rounds 1 and 3 did not catch `thinking_omitted`.
- **R2b-2 [minor, tests; owner D-685]:** the new test covers the drop predicate and the gating, but no session is mapped
  end to end under the quirk. AER validity, the scoped rule, the `src` pointers and the ext schema of `dropped_calls`
  are therefore untested until `agentdyn-live` lands. Add a mapped-session test with a dropped call before that profile
  ships.

## Final re-check: d8e1ec56 (D-656 fix2 8338a155) and the LAN forward mode (d710cb69 at e8d210aa)

### D-656 fix2: all fixed

The round-3 probes were re-run at e8d210aa (before) and d8e1ec56 (after); 299 targeted tests pass, serialised;
`regen_pins --check` reports 18/18 current (queued).

- **R3-1:** an empty discarded text is now `ambiguous` on both the Messages and the OpenAI paths, and the session maps.
  Before, four Messages cases and two OpenAI cases raised `aer.sentinel`.
- **R3-2:** a garbage, empty or ping-only event stream gives no message, plus `stream_inconsistent` and
  `capture_error`. A stream with `message_start` keeps its message, with `stream_incomplete`, as the SDK does.
- **R3-3:** `autodojo_aborted_kill` records 26 guarded sources (8 `anthropic_llm`), like its siblings, and the
  generators refuse a stale installed harness.
- **R3-4:** a start block's `input_json` no longer seeds a tool input, and a `message` event name that disagrees with its
  payload is refused.
- **R3-5:** splits around raw U+2028, U+2029 or U+0085, and multi-line `data:`, are now refused (`cap.redact.split`).
- **R2b-1:** the closed ext schema declares `thinking_omitted`, `wire_parts` and `dropped_calls`, so all 17 fixtures
  validate (2 violations before).
- **Records:** item 166 records the R1-fix digest moves and the fixture regeneration (17 moved, 16 changed identity).
- **Fixture mapping:** 16 of 17 fixtures are byte-identical before and after. Only the regenerated
  `autodojo_aborted_kill` moves, with the same record count and issue codes.

### LAN forward mode (D-698/D-664): reach confirmed; Minor hardening findings, all class 0

**Method:** workflow `wf_7d117f6d-c98`, 30 agents, two finders (the forward mode; wiring and the rest of the window),
with two adversarial verifiers per finding. The probes were loopback-only, with in-process proxies and dummy upstreams.
Data: `~/.agentprov/review/pre-round/lan-result.json`.

**The orchestrator's three questions:**
- **No wider than the single allowlisted pair:**
  - 28 absolute-form variants never reached a second listener (connects: 0): case, trailing dot, IPv4-mapped IPv6,
    decimal, hex, octal and short IPv4, percent-encoding, userinfo, fragment and backslash tricks, explicit or omitted
    ports, `https`/`ftp`/upper-case schemes, CR/LF/VT in the path.
  - The connect always uses the canonical pair from the allowlist (`egress.py:356`).
  - `endpoint_target(allow_lan)` accepts only literal 10/8, 172.16/12, 192.168/16, 100.64/10 and fc00::/7. It refuses
    names, link-local, IPv4-mapped, NAT64 and 6to4 forms, 0.0.0.0, broadcast, multicast, public addresses and 127.0.0.2.
- **Nothing worker-chosen recorded:** `live.egress` holds T0-chosen pair keys (`forwards`) and closed refusal kinds. The
  synthetic key and a hostile Host value are absent from the summary.
  - `Authorization` and `x-api-key` pass through to the LAN server. That is intended: a LAN agent is keyless, since
    `runner.py:203` refuses `allow_lan` together with `api_key_env` and the dummy key is `EMPTY`.
  - `Proxy-Authorization` is dropped.
- **Non-LAN paths unchanged:**
  - the CONNECT differential (18 targets) at 1cac458d and e8d210aa is identical, apart from two nits below;
  - the old egress tests pass unchanged;
  - the sandbox profile is unchanged;
  - c3b24f76 (Inspect harness) is outside every stage closure (class 0), with no key or network regression.

**Findings** (all class 0 since `cli/` is in no stage digest; they neither widen reach nor expose a key; fix before the
first real LAN run):
- **LF-1 [minor]: a bare LF in a header line smuggles a second request** (`egress.py:334-345`). Lines are split on CRLF
  only, and values are forwarded raw. A lenient server (http.server, llama.cpp's httplib) then sees a second request
  with any method, Upgrade and Proxy-* headers, and the proxy's `Connection: close` lands in the smuggled request. The
  probe reproduced it. Fix: refuse header lines containing LF, CR or NUL, and names that are not RFC 9110 tokens.
- **LF-2 [minor]: CONNECT to the forward pair opens a raw tunnel past the forward-mode rules.** `forward ⊆ allow` and
  the CONNECT branch tunnels to any allowed pair. So the method allowlist, header rewriting and one-request rule are not
  a boundary, which the D-664 amendment implies they are. Fix: refuse CONNECT to a forward pair, or document the rules
  as hygiene rather than containment. Related: requests after the first head are piped unchanged.
- **LF-3 [minor]: malformed absolute-form targets raise inside `_forward`.** Two cases: `urlsplit` raises `ValueError`
  on a bad bracketed host (`:319`, outside the `try`), and `origin.encode('ascii')` fails on a byte ≥ 0x80 (`:345`).
  The effect: no reply, no refusal count, and asyncio's "Unhandled exception" logs a traceback holding T2-chosen text
  to T0's stderr (and a `--log-file`), though never into the corpus. Fix: catch both as `malformed`.
- **LF-4 [minor; one verifier rated it a nit]:** `stop()` waits 30 s and leaves a forward or tunnel piping when an
  upstream stays silent. This predates the change for CONNECT.
- **LF-5 [minor, docs]:** G.4.10 and the MN boundary table still describe a CONNECT-only proxy, and D-664's refusal
  sentence is incomplete.
- **Nits:**
  - `allow_pair` strips brackets from any name, so CONNECT to `[localhost]:P` is accepted, though it still goes to the
    pair only;
  - IP literals are now allowed for https custom endpoints (a non-LAN behaviour change, still exact and chosen by the
    operator; PLAUSIBLE);
  - the forward pair is chosen with a case-sensitive `startswith('http://')`, so `HTTP://` fails closed with 405;
  - IPv6 zone ids pass the LAN check;
  - the forward mode passes Host as given (RFC 9112 says to regenerate it; PLAUSIBLE);
  - `provision_dataset` follows symlinks in the dataset directory (T0-only precondition).

### Verdict for the window

**READY to push** once the combined suite is green. The D-656 fix2 items are all fixed, pins are current, and stored
corpora and existing fixtures are byte-neutral. The LAN forward mode's reach and recording guarantees hold. Its Minor
hardening items, LF-1 to LF-5, are class 0 and should land before the first real LAN run.
