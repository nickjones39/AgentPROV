## Item 28 ((i) implemented, 2026-10-13; user-approved; routed from phase 10n, R-10n-2): Inspect strings over 1 MiB

**Finding.** ATIA (phase 10n, inspect_ai 0.3.112) has 42 strings whose UTF-8 encoding exceeds 1 MiB:
- 20 image `data:` URIs and 4 video values in message parts;
- 18 Gemini `inlineData` copies in `model_call.params.transmitted`.

C.2.1(6) requires such a string to be stored as a blob and referenced. They pass validation today because the AER
validator and writer do not check C.2.1(6) (question (iii) below).

**Constraints** (deferrals session, 2026-10-13):
- `$blob` is a reserved Json form, valid in every Json position in aer/0.1 and unchanged in aer/0.2. That includes
  `model_call.params`, so `params.transmitted` qualifies.
- `$blob` is not valid in typed string fields: `parts[k].uri` and `text` are plain strings. Widening `uri` is outside
  what the user approved for aer/0.2.
- A `$blob` must name a raw-store object listed in `seal.blobs`. Imports store only whole raw files (D-203), so nothing
  can store a string carved out of a source JSON yet.

**(i) Proposed now (Inspect mapper; new rule `inspect.content_not_inlined@1`, class D; issue
`inspect.content_not_inlined`, severity info).** This follows the OpenHands precedent
(`openhands.content_not_inlined@1`, phase 10g).
- A `data:` URI over 1 MiB in a message part becomes a `blob` part (`{"t": "blob", "media": <the URI's media type>}`,
  C.3.4.1), with `/parts/k/data` declared `not_captured`.
  - The URI's digest and size go in `ext.inspect.part_extra[k].not_inlined`, as `{sha256, bytes, media}` of the URI
    string's UTF-8 bytes.
  - The locator names the source position.
  - With (ii), the same part later gains `data` as a `$blob` of the decoded payload. A plain URL over 1 MiB (none
    observed) would stay a `uri` part with `/parts/k/uri` declared `not_captured` and the same digest in ext.
- A string over 1 MiB in a Json position (`params.transmitted`, tool args, `other.value`) is replaced in place by
  `{"not_inlined": {sha256, bytes, media?}}`, the OpenHands form.
- Honest but lossy: the content stays in the raw store and out of the AER, and its digest ties it to the raw bytes.

**(ii) Separate decision (runner, raw origins, C.11.5; the deferrals session's capability): carved blobs.**
- The mapper returns the carved bytes with a locator into the source artefact.
- The runner stores them under a new origin kind, e.g. `{kind: "carved", from: <source sha256>, pointer}`.
- `verify` and `recompute` re-carve and compare.
- No AER schema change is needed. It would serve ATIA's 42 strings and OpenHands' not-inlined content alike. When it
  lands, (i)'s declarations become `$blob` references.

**(iii) Separate question (core, `aer/validate.py`): enforce C.2.1(6).**
- A release-mode check of string sizes would have caught these 42 strings.
- Scanned 2026-10-13: 0 lines over 1 MiB in the 126,747 AERs of the nine current stored corpora, so no stored AER would fail.
- It is a core change (invariant 5 record).

**Prediction for (i).**
- No stored AER byte: the scan above found no line over 1 MiB, so no stored string reaches the threshold.
- The `adapters/inspect` code and catalogue digests move.
- ATIA (not stored): 24 parts and 18 `params.transmitted` values are declared not inlined, and the AER shrinks by
  their size.

**Implemented (i), with one change of form.** aer/0.1 makes a `blob` part's `data` strictly required, and a declared
unknown may stand beside a value only as `ambiguous` (AER-V16). So a blob part "declared `not_captured`" and a null
`text` "declared `not_captured`" do not validate. Instead, every oversized string takes a Json position:
- an `image`, `audio`, `video`, `text` or `reasoning` item becomes `{"t": "other", "type": <the Inspect type>,
  "value": {"not_inlined": {sha256, bytes, media?}}}`, with the item's other fields in `part_extra` as before;
- a tool message's string content becomes the `tool_result`'s `value`;
- strings in Json positions (`params.configured`/`transmitted`, call `args`, `other` values, list-content results,
  events kept in `ext`) are replaced in place.

Every replacement is tagged D under `inspect.content_not_inlined@1` scoped to its pointer. One info issue,
`inspect.content_not_inlined`, lists the records. `media` comes from a `data:` URI. The threshold is C.2.1(6): UTF-8
bytes over 1 MiB, so exactly 1 MiB stays inline. With (ii), the `other` parts become `blob` parts with a `$blob`, and
the Json replacements become `$blob` references.

Checked:
- Re-mapped AER bodies are byte-identical to item 25's: AgentHarm 1,056 of 1,056, scratch WhistleBench 9,200 of 9,200.
- `tests/adapters/inspect/test_item28.py` (5): a data URI image; a tool output; text and reasoning items; a
  transmitted string; the exact-1-MiB boundary. Each case passes tier 4.

