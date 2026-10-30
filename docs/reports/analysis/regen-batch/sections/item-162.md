## Item 162: pre-round review area F, AER validation and transcript/v1 (D-224; user decision 2026-10-22; branch `integration-fix-ultra-aer`)

**What changes.** F-1: AER-V14 checks a scoped rule's own pointer (a D value on an I-only rule is refused), and the
adapters' C.6.5 weakening (`weaken_to_rule_class`) marks such a pointer `I`. F-2:
transcript/v1 refuses a degenerate AER (view and compat registered failed). #28: under aer/0.2, `$utf16`/`$lit` are
accepted only in their C.11.3 shape. #30: the 1 MiB inline limit covers an aer/0.2 seal. #35: a withheld reasoning or
refusal part renders null. #27: a seal's `accounting_<verdict>` issue must mirror a check (AER-V25). #34: SEM-V11 bounds
an annotation with no premises by its rule (an `O` one is refused). #31: the aer/0.2 schema names D-219. RC-15: a
context tree's `verification.kind` is `download` or `blob` (the seal refuses any other). RC-18: a refusal's reason lines (stderr, notice,
`summary.refusal`) are kept in full or with an overflow count, format and vocabulary drift first. RC-19: D.10.4a item 23
states the `tool_result` exception (docs and a test only).

**What moves.** Stage code digests (class 1; corrected after the pre-round verification V-5, file by file in D-224):
`aer` of every family, `sem` of all 12 families with semantics, `prov` and `validation` (`aer/validate.py`,
`aer/_structure.py`, with `sem/validate.py` for `sem` and `validation`); the views and compat engine digests and
adprov's `aer` (`views/transcript_v1.py`; outputs move, class 2, only for corpora with degenerate units, after item 151,
or withheld reasoning/refusal parts); agentdojo's `adapter_code_sha256` (`capture_mapper.py`, a comment). The shipped
schemas
`aer-0.2.schema.json` (`99b39bd6…` → `4a101e50…`) and `corpus-0.2.schema.json` (`28d85d71…` → `8711e44d…` from D-224 alone; `13e7233f…` on the integration branch with D-623), re-pinned
in `tests/unit/test_format_freeze.py`; every `agentprov-corpus/0.2` corpus carries them (none is stored yet). Counts on
the eight current stored corpora (126,351 AERs): 0 D-scoped I rules (F-1), 0 degenerate executions with a view or compat
output (F-2), 0 `$utf16`/`$lit` forms at all (#28), 0 accounting mirrors without their check (#27), 0 SEM annotations
with no premises (#34). No stored AER, SEM, PROV or view byte moves. Pre-round verification V-7 (D-224): the shipped
schemas move again, `aer-0.2.schema.json` → `42e7046c…` (#28, #31 constraints) and `corpus-0.2.schema.json` →
`735207ed…` (a validation stage's optional `skipped`); no 0.2 corpus is stored.

**Tests.** `tests/unit/aer/test_envelope.py` (`..._f1`, `..._27`), `tests/unit/aer/test_reserved_forms_28.py`,
`tests/unit/aer/test_aer_02.py` (`..._inline_limit_to_the_seal_too`), `tests/unit/views/test_transcript_v1_view.py`
(`..._f2`, `..._35`), `tests/unit/sem/test_validator.py` (`..._34`), `tests/adapters/test_code_verification.py` (`..._f1`), `tests/cli/test_refusal_lines_rc18.py`,
`tests/unit/corpus/test_derive_drift.py` (`..._rc18`), `tests/adapters/agentdojo/test_capture_mapper.py` (`..._rc1`,
RC-19), `tests/unit/corpus/test_package.py` (`..._rc15`), `tests/unit/test_format_freeze.py` (the two schema pins).

