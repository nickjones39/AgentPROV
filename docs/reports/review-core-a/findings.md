# Core review A: AER record and semantics code (session review-fix-core-a)

Scope:
- A1: `src/agentprov/aer/`
- A2: `src/agentprov/sem/` and `src/agentprov/views/`
- A3: `src/agentprov/vocab/`, `schemas/`, `versions.py`, `formats.py`, `errors.py`

Reviewed at origin/main `7f8f8cb3`; the fixes are on top of origin/main `9999c41e`. Out of scope: `prov/`, `validate/`,
`ingest/`, `raw/`, `io/`, `capture/` and `backends/` (the ultrareview covers them), plus the perf work and the 10f..10p
families (`docs/reports/bugpass/findings.md` on `bugpass-perf-10`). Ids reserved with `tools/reserve_id.py`: regen-batch
items 60–79 and D-500..D-509.

**Method.** The pass ran as a workflow:
- Five read-only reviewers, one per area: A1a (canon, ids, evidence, rules, types, locators), A1b (writer, reader,
  `_structure`, validator, accounting), A2a (sem), A2b (views) and A3.
- Each candidate finding then went to a separate verifier, which tried to disprove it. A finding was kept only when the
  verifier reproduced it with a pytest file that fails on current code.
- I re-ran every repro on `7f8f8cb3`, and every one fails as claimed.
- The repros are in `repro/CA-nn_<reviewer>/` (`.txt`, run from the repository root). `fix.diff.txt` is the
  verifier's proposed fix, which is not applied.

**Byte class.**
- **0**: the fix changes no stored AER/SEM/PROV bytes and no stage code digest.
- **1**: it would change one of them. Every `.py`/`.toml`/`.json`/`.ttl` file under `aer/` is covered, through the aer
  stage `engine_code_sha256` = `code_sha256(["adapters/runner", "aer"])`. So is every such file under `sem/`, `views/`
  and `vocab/` (`corpus/derive.py:247-292`), and every adapter family directory (`adapter_code_sha256`). `errors.py`
  is in the expand stage's `EXPAND_MODULES`.
- Not covered by any digest: `versions.py`, `formats.py`, `schemas/` and `io/`.
- So no code fix inside the A1/A2 scope can be committed as a plain bug fix. Each one is a regen-batch item instead
  (`proposals.md`).

**Severity:** security, correctness, determinism, robustness or test-gap. **Reach** says whether untrusted imported data
can trigger the defect (import), or whether it needs a hostile or tampered AER/SEM/corpus file read back (read-back),
or only direct API use (API).

| CA | area | severity | file:line | defect (failing input → actual; expected) | reach | class | status |
|---|---|---|---|---|---|---|---|
| CA-1 | A1b | **security** | `aer/validate.py:744` (`_walk_numbers_and_blobs`) | **Input:** a tool arg or result `{"$int":"5"}` or `{"$blob":"sha256:<64 hex>","bytes":3}`. `encode_value` escapes it as `{"$lit":{…}}`, but the walker reads the `$lit` body as reserved forms. **Actual:** `$int` makes `AerWriter.add` raise `aer.schema.pattern`, so the runner replaces the whole execution with a degenerate `adapter_defect`. `$blob` puts an invented digest into `seal.blobs`; with a store, `aer.blob.missing`. **Expected:** the body's first-level member names are literal source keys (C.11.3). Not fixed in aer/0.2 (deferrals-c `validate.py`). The test helper `tests/unit/aer/aer_support.py::_walk_blobs` has the same blind spot | import | 1 | regen item 60, approved; built `16c08b4c` on held branch `review-core-a-regen` |
| CA-2 | A1b | **security** | `aer/validate.py:286` (`_add`), `:175` (`ok`) | **Input:** 2000 dev-mode warnings (e.g. empty assistant text parts), then a dangling `generated_by` and a forged `seal.accounting.status`. **Actual:** `_add` drops every finding past `MAX_FINDINGS`, errors included, and `ok` ignores truncation, so dev mode gives `ok=True`. Dev mode is used by corpus validation, `agentprov validate` and the PROV engine's `check_aer` gate. **Expected:** `ok=False`. Not fixed in aer/0.2 | read-back; import with a mapper defect | 1 | regen item 61, approved; built `82e51157` on held branch `review-core-a-regen` |
| CA-3 | A1a | robustness | `aer/ids.py:100` (`split_part_id`); `aer/reader.py:76`; `sem/validate.py:482` | **Input:** a part id whose ordinal has more than 4300 digits (`"m1#"+"1"*5000`), which matches `PART_ID_RE`. **Actual:** `int()` raises the CPython digit-limit `ValueError`; the validator, reader and SEM validator crash, and the CLI exits 70. **Expected:** `aer.ref.dangling` | read-back | 1 | regen item 62, approved; built `bf1643da` on held branch `review-core-a-regen` |
| CA-4 | A1a | robustness | `aer/rules.py:120` (`parse_rule_ref`); `sem/validate.py:529,583,609` | **Input:** a rule ref whose version has more than 4300 digits. **Actual:** the SEM validator crashes with a `ValueError`. **Expected:** a `sem.*` finding | read-back | 1 | regen item 63, approved; built `e1f5a956` on held branch `review-core-a-regen` |
| CA-5 | A1a, A1b | robustness | `aer/locators.py:151`; `aer/validate.py:434` | **Input:** a header with `"artifacts": 5` (a truthy scalar), validated with a raw store. **Actual:** `LocatorResolver.__init__` raises `TypeError`; the validator itself guards with `isinstance(…, list)`. **Expected:** the schema finding only. Found by both A1a and A1b | read-back | 1 | regen item 64, approved; built `9acdd6ce` on held branch `review-core-a-regen` |
| CA-6 | A1a | robustness | `aer/canon.py:270` (`_check_json_types`) | **Input:** a cyclic Python value (`d["self"]=[d]`). **Actual:** `dumps_line` loops forever, because the `depth` parameter is unused and `MAX_JSON_DEPTH` is not applied; `encode_value` raises a bare `RecursionError`. **Expected:** `CanonError` | API (a producer bug) | 1 | regen item 65, approved; built `fadb2f5e` on held branch `review-core-a-regen` |
| CA-7 | A1a | robustness | `aer/canon.py:151` (`encode_value`, int branch) | **Input:** an int with more than 4300 decimal digits, e.g. a YAML `0x…` literal through a DTap config auxiliary (power-of-two bases are exempt from the parse limit). **Actual:** `str()` raises `ValueError`. **Expected:** `CanonError` | import (DTap YAML) | 1 | regen item 66, approved; built `2dba050d` on held branch `review-core-a-regen` |
| CA-8 | A1b | correctness | `aer/accounting.py:314` (`_reported_checks`) | **Input:** a scope with a kept and a cached agent call and `usage.calls=1`. **Actual:** the assistant message of the cached call is counted against the provider-reported calls, giving `reported_calls_differ` and `inconsistent`. **Expected:** cached calls are not counted (C.20(1) and the module docstring) | API (latent: no mapper writes both) | 1 | regen item 67, approved; built `4808ba82` on held branch `review-core-a-regen` |
| CA-9 | A2a | robustness | `sem/validate.py:571` (`premises`) | **Input:** an annotation premise naming an earlier annotation with `ev` `"X"`. **Actual:** `weakest()` raises `ValueError`, which escapes `validate_sem` and corpus validation. **Expected:** findings only | read-back | 1 | regen item 68, approved; built `4b5d80e8` on held branch `review-core-a-regen` |
| CA-10 | A2a | robustness | `sem/reader.py:73` (`load_sem_bytes`); `sem/types.py:208-226` | **Input:** a SEM header without `ex`/`profile`/`aer_digest`, or with them malformed. **Actual:** the reader accepts it, and the `SemDocument` accessors then raise `KeyError`/`TypeError`/`ValueError`; `agentprov inspect` exits 70. **Expected:** `SemFormatError` | read-back | 1 | regen item 69, approved; built `1d48109d` on held branch `review-core-a-regen` |
| CA-11 | A2a | correctness | `io/jsonschema_subset.py:155` | **Input:** a namespaced value `true` under `{"enum":[1]}` (or `false` under `[0]`, or nested in arrays/objects). **Actual:** it passes, because Python `True == 1`. **Expected:** `sem.value.schema` (SEM-V09; JSON value equality). The agentdojo family's own copy (`adapters/agentdojo/profile.py:114`) has the same comparison | read-back (header `ns`); profile | 0 (`io/`); copy: 1 | **fixed 7dbce006** (routed to this session by the orchestrator); copy: regen item 78, write-up for regen-items |
| CA-12 | A2a | robustness | `sem/engine.py:92,104`; `sem/engine.py:77` (`_forward_refs`) | **Input:** a malformed `Annotation` (`span=(1,)`, `premises=None`, or a target `a`+5000 digits). **Actual:** raw `IndexError`/`TypeError`/`ValueError`. **Expected:** `SemAnnotationError` (module docstring) | API (a profile bug) | 1 | regen item 70, approved; built `e16d6fa8` on held branch `review-core-a-regen` |
| CA-13 | A2b | robustness | `views/transcript_v1.py:547` (`_native_message_turn`) | **Input:** a release-valid agentdojo AER whose `agentdojo.unknown_message` part holds hostile values (`content: 5`, `args: "xy"`, a lone surrogate). **Actual:** `render_converted` raises `TypeError`/`ValueError`/`UnicodeEncodeError`; derive catches only `AgentProvError`, so one log aborts the derive. **Expected:** `ViewError` | import | 1 | regen item 71, approved; built `ee61ad2e` on held branch `review-core-a-regen` |
| CA-14 | A2b | correctness | `views/transcript_v1.py:617` (`_converted_turn`, tool) | **Input:** a TraceLogger tool message whose content is a list kept as `tool_result.value` (every list in v0.k11; multi-block in v1.k14). **Actual:** the view renders `content ""` with `sha256("")`, and the compat graph records an empty tool output. **Expected:** the joined text blocks, as the baseline converter gives | import | 1 | regen item 72, approved; built `e74ebd60` on held branch `review-core-a-regen` |
| CA-15 | A2b | correctness | `views/transcript_v1.py:270` (`_handler_usage`) | **Input:** an adprov v1 file with a known usage key holding a non-integer (`prompt_tokens: 9278.0`, a negative number, a string or a bool). The mapper keeps it in `ext.adprov.usage_extra`. **Actual:** the view renders `null`. **Expected:** byte identity (C.15.3) | import | 1 | regen item 73, approved; built `a79590fa` on held branch `review-core-a-regen` |
| CA-16 | A2b | correctness | `adapters/adprov/mapper.py:311,533,456-461` | **Input:** a v1 file with `run_error`/`source`/`timing_stubbed`/`pipeline_name` on a released transcript, an explicit-null `finish_reasons`, a non-object `usage`, or a converted `temperature`. **Actual:** these are silently dropped or reshaped, with no issue. **Expected:** byte identity or a seal issue (J.3.2). Outside the review scope; found by A2b | import (no known producer) | 1 | regen item 74, approved; built `8a0df1a1` on held branch `review-core-a-regen` |
| CA-17 | A2b | correctness | `adapters/adprov/mapper.py:818`; `views/transcript_v1.py:201` | **Input:** `"tool_calls": []` on an assistant turn, or a top-level `"discarded_attempts": []`. **Actual:** the member is lost in the round trip, with no issue. **Expected:** byte identity or a layout issue (J.3.2) | import (no known producer) | 1 | regen item 75, approved; built `add9e0f7` on held branch `review-core-a-regen` |
| CA-18 | A2b | robustness | `aer/canon.py:213,254` (`decode_value`) | **Input:** a validator-accepted `{"$int": "<≥2**1024>"}` named in `ext.lex.flt`. **Actual:** `float()` raises `OverflowError`, and derive aborts. **Expected:** `CanonError` | read-back | 1 | regen item 76, approved; built `136821a5` on held branch `review-core-a-regen` |
| CA-19 | A2b | correctness | `views/transcript_v1.py:589`; `adapters/agentdojo/mapper.py` (`_content_parts`) | **Input:** one text block whose `content` is null. **Actual:** the mapper writes the same part as `content: null`, so the view renders `text null`. **Expected:** `""` (converter rule) | import | 1 | regen item 77, approved; routed to regen-items (RD-1 owns `agentdojo/mapper.py`) |
| CA-20 | A2b | test-gap | `tests/unit/views/` | No mutation round-trip test covers transcript/v1 import → view (byte identity, a degenerate mapping or a seal issue), and no test covers `render_converted` on `unknown_message` or on multi-block tool content | — | 0 (tests only; fail until 71–75) | regen item 79, approved; built `2280ce54` on the held branch (lands with 71–75) |
| CA-21 | A3 | correctness | `vocab/apv-0.1.ttl:1151,1442,1463` (and every `owl:DatatypeProperty` filled through `opt()`/`lit()`) | **Actual:** the engine writes the IRI `apv:RecordedNull` as the object of `apv:error`, `apv:defenceId`, `apv:taskId`, …, which are declared `owl:DatatypeProperty; rdfs:range xsd:string`. That is an OWL 2 DL violation; under RDFS it entails `apv:RecordedNull a xsd:string`. **Expected:** typed as declared | import | 1 (apv meaning) | D-500, user decision 2026-10-14: option 1; regen item 85, built `34712a58` on the held branch (apv 0.2.0) |
| CA-22 | A3 | correctness | `vocab/apv-0.1.ttl:761` | **Actual:** `apv:assumption` is an `owl:ObjectProperty` with `rdfs:range apv:Assumption`, but adapter assumptions are emitted as `xsd:string` literals, as E.10 item 11 and D-17 require. The vocabulary contradicts the documented output | import | 1 (apv meaning) | D-501, user decision 2026-10-14: option 1; regen item 86, built `7f1c354b` + `2540fa13` on the held branch |
| CA-23 | A3 | test-gap | `formats.py:65` | **Actual:** `FORMATS` lacked six ids the code writes: `agentprov-split/0.1` (stored), `-sem-profile/0.1`, `-reconciliation/0.1`, `-inspect/0.1`, `-artefact-table/0.1` and `-fixture-caps/0.1`. **Expected:** the one closed set of HL L.1.1 | — | 0 | **fixed 70889b14** (rebase note for deferrals-c) |
| CA-24 | A3 | determinism | `versions.py:7` | **Actual:** the expand stage recorded `importlib.metadata`, while every other stage and `producer.agentprov_version` recorded the literal `__version__`, so a pyproject-only release bump (as L.1.1 describes it) splits the engine version within one corpus. **Expected:** one source | — | 0 | **fixed 11396b6a** (rebase note for deferrals-c) |

## Summary

**Findings.**
- Reviewers raised 25 candidates. All 25 were reproduced; A1a-3 and A1b-3 are the same defect, which leaves 24
  findings.
- By severity: 2 security (CA-1, CA-2), 9 correctness, 10 robustness, 1 determinism and 2 test-gap.
- By byte class: 3 are class 0 and 21 are class 1. Two of the class-1 findings are the vocabulary decisions.

**Fixed here** (class 0; one commit each, with a regression test that fails before the fix):
- CA-23 `70889b14` and CA-24 `11396b6a`. deferrals-c also edits `formats.py` and `versions.py`; the hunks are
  disjoint, and each commit message carries a rebase note.
- CA-11 `7dbce006`. It is in `io/`, outside this review's scope, and was routed here by the orchestrator. No in-flight
  branch touches the file.

**Class 1** (`proposals.md`):
- Regen items 60–76 and 79 are approved for the round. The user confirmed this directly in this session on
  2026-10-14. They are built on the held branch `review-core-a-regen`, which is never pushed before the round.
- Items 77 (CA-19) and 78 (the agentdojo copy of CA-11) are written up for regen-items, which owns
  `adapters/agentdojo/`.
- D-500 (CA-21) and D-501 (CA-22) were decided by the user on 2026-10-14 (option 1 each), as one additive bump to
  apv 0.2.0. They are built as regen items 85 and 86 on the held branch and land with deferrals part C
  (`agentprov-corpus/0.2`). The PROV spec stays `agentprov-prov/0.1`. D-502 records why item 67 keeps
  `aer.acc.reported_counts@1`. All three are in `DECISIONS.md`.
- The held branch passes its targeted runs per item; its gates and full suite are recorded in the session status.

**aer/0.2** (deferrals-c): CA-1 and CA-2 also exist in deferrals-c's `validate.py`, so part C must port both fixes at
its rebase. The orchestrator has told the deferrals session. None of the other A1 findings are in files that
deferrals-c changes, except `validate.py`; the CA-5 call site is there, but its fix is in `locators.py`.

**Not findings.** These were checked and left as they are (reviewers' notes):
- JCS output against RFC 8785: `1e21`, `5e-324`, `2**53`, lone surrogates, NaN, UTF-16 key order, U+2028 and
  control-character escapes.
- `encode_value`/`decode_value` round trips: `-0.0`, integral floats around `2**53` and `1e21`, nested `$lit`, `$utf16`,
  and pointer escaping.
- The `import_execution_id` preimage has no separator ambiguity.
- Evidence longest-prefix matching on `/` boundaries.
- Every one of the 176 shipped `_unverified` twins is class I.
- `canonical_key_loc` accepts `/a~2`, but the validator's pointer pattern rejects it in an AER.
- `LocatorResolver` resolves duplicate artefact ids last-wins while the validator uses first-wins. It is already an
  error.

**Not covered.**
- No end-to-end corpus run (by rule). The golden-fixture gates were not run by the reviewers (`tests/fixtures` is off
  limits to them); the session's gate run covers them.
- Untrusted text in error messages: A3 swept the raise/detail f-string sites by pattern, not all ~780 raise sites.
  The CLI escapes every message through `safe_text`, so no unescaped terminal path was found.
- Also not covered: the SHACL shapes, the frozen compat `adprov.ttl`, and a re-fuzz of the capture-0.1 and corpus-0.1
  schemas.

**Leads not verified** (handed on with this report; outside the review scope). The item 62 and item 79 builds added
two more:
- Several JSON-pointer token sites use `isdigit()` and then `int()`, with the same theoretical digit-limit exposure as
  CA-3. They are not part ids: `prov/engine.py:192`, `validate/profiles.py:177`, `corpus/datasheet.py:203`.
- adprov: `prompt_tokens = 2**60` and `meta.wall_clock_s = -1.0` map as non-degenerate, and then the writer raises
  `AerWriteError` (`aer.schema.pattern`). A raw write error reaches the caller instead of a degenerate outcome or a seal
  issue. This overlaps the first adprov lead below.

The reviewers' leads:
- The adprov importer raises `AerWriteError` instead of writing a degenerate seal for several inputs: a lone surrogate
  in v1 content; `$`-prefixed unknown meta/turn/model_config/usage member names (possibly CA-1); usage ints above
  `2**53`; and a negative, `-0.0` or `1e20` `wall_clock_s`.
- The adprov importer drops `redacted_thinking` content, which D.6.6 defines.
- `capture_mapper.py:1891` puts a repr of the capture backend id (truncated to 40 characters) into an AER issue detail.
