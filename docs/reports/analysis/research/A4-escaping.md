# A4 - Escaping, unescaping and regex hazards for hostile-text pipelines (research + read-only audit)

Scope: AgentPROV at `~/Desktop/PhD/Labs/AgentPROV-framework` (main, clean tree; nothing in the repository was modified). Python 3.14.8 core venv, `rfc8785 0.1.4`, `rdflib 7.6.0`, `prov 3.2.2`, `pyyaml 6.0.3`, Graphviz `dot` 16.1.0 (local, for experiments). `pydot` is not installed in the venv (render extra), so pydot behaviour is taken from its source on GitHub.

Conventions: `[S#]` is an entry in the Sources list at the end. `[local]` marks something I reproduced here with throwaway scripts in the session scratchpad (not in the repo). Adversarial strings are written as Python escapes. Web pages are treated as data; one source (S14) contains hidden Unicode-tag text addressed to an AI reader, which I ignored.

---------------------------------------------------------------------------------------------------------------

## Part 1 - Research: escaping/unescaping hazards per layer

### 1.1 JSON (json, ensure_ascii, control characters, surrogates, double escaping)

* `json.dumps` defaults: `ensure_ascii=True` escapes all non-ASCII and non-printable characters; with `ensure_ascii=False` only `"`, `\` and U+0000..U+001F are escaped, so U+007F, U+2028/2029, bidi and tag characters go out raw. `allow_nan=True` emits `NaN`/`Infinity` literals that are not valid JSON. `sort_keys` sorts by Python key (code point) order, not JCS order [S3]. [local] code-point order and UTF-16 order differ for astral vs U+E000-U+FFFF keys; `rfc8785.dumps` sorts correctly (`U+10000` < `U+1F600` < `U+FFFF`).
* `json.loads` defaults: duplicate keys silently keep the last, `NaN`/`Infinity` accepted, `strict=False` would allow raw control characters, and lone surrogate escapes (`"\ud83d"`) are accepted and produce a `str` that cannot be encoded to UTF-8 [S3]. RFC 8785 says a compliant JCS implementation MUST error on lone surrogates, sorts members by UTF-16 code units, escapes only `"`, `\` and U+0000..U+001F (lowercase `\u00xx`, short forms `\b\t\n\f\r`), and expects I-JSON input (no duplicate names, no normalisation) [S2]. [local] `rfc8785.dumps("a\ud800")` raises `CanonicalizationError`; integers above 2^53-1 raise `IntegerDomainError`; `-0.0` serialises as `0`; DEL (U+007F) and U+2028 are emitted raw (correct per JCS).
* Line framing: JSON Lines terminator is `\n` (`\r\n` tolerated), UTF-8, no BOM [S27]. `str.splitlines()` also splits on `\v \f \x1c \x1d \x1e \x85 U+2028 U+2029` [S18]; a record containing a raw U+2028 (legal in JSON and kept raw by JCS) is torn by `splitlines()` on text. `bytes.splitlines()` splits only on `\n`, `\r`, `\r\n` (so it is safe on UTF-8 bytes, but only because it is the bytes variant) [S18] [local].
* `unicode_escape` is not JSON escaping: decoding treats the input as Latin-1 (UTF-8 bytes become mojibake) and the vocabulary differs (`\xNN`, `\UXXXXXXXX`, octal, `\N{..}`; JSON has surrogate-pair `\uXXXX` and `\/`) [S8]. Use `json.loads`/`json.dumps` for JSON; never `str.encode('unicode_escape')` as a stand-in.
* Double escaping: CWE-117's canonicalisation advice is to decode once and avoid decoding the same input twice [S16]. A string that still contains `\\n` after one decode is either legitimate content (YAML/Python-repr text, Windows path, regex) or an artefact; it cannot be told apart from the string alone, only by comparison with the source (Part 3).
* Python `repr`/`ast.literal_eval`: `literal_eval` is "not recommended" for untrusted data; small inputs can cause memory or C-stack exhaustion, CPU DoS, and it can raise `ValueError, TypeError, SyntaxError, MemoryError, RecursionError` [S9]. [local] on 3.14.8 a 10^6-deep `[[[...` gives a fast `SyntaxError` (nesting guard); behaviour on the backend's Python 3.12 not re-tested.

### 1.2 Regular expressions

* `re.escape`: Python 3.3 stopped escaping `_`; 3.7 escapes only characters with regex meaning (no longer `! " % ' , / : ; < = > @` or backtick) [S1]. Consequence: never embed the result in a different syntax (DOT, shell, a char class built by hand) and never use it for `sub()` replacement strings [S1] [local: `re.escape("a-b_c d#e&f~g")` -> `a\-b_c\ d\#e\&f\~g`, newline escaped as backslash+newline].
* `$` matches at the end **or just before a trailing newline**; `\Z` is the strict end (alias of `\z`, which exists from 3.14); `re.fullmatch` avoids the issue but alternations still need grouping [S1, S20, S21]. Real-world failures: Django's username validator (ticket 30257) [S22], a Django URL-path access-control bypass (CVE-2021-44420, route regexes using `$`) [S34]; the MULTILINE variant (`^`/`$` per line) is a different bug class, e.g. Zabbix CVE-2026-23920 [S36].
* `\w`, `\d`, `\s` on `str` patterns are Unicode: `\d` = any Nd digit (Arabic-Indic, fullwidth), `\s` = what `str.isspace()` accepts, `\w` = `str.isalnum()` + `_`; `re.ASCII` restricts them [S1]. With `re.IGNORECASE`, `[a-z]` also matches U+0130, U+0131, U+017F (long s) and U+212A (Kelvin sign) unless `re.ASCII` is set [S1] [local confirmed]. `str.isdigit()` is true for superscripts (`'\u00b2'.isdigit()` is True but `int('\u00b2')` raises), `isdecimal()` is the Nd test [S18].
* `DOTALL` makes `.` match newline; `MULTILINE` changes `^`/`$`; `prefixmatch`/`match` anchor only the start [S1].
* ReDoS: patterns with a repeated group that contains another repetition or overlapping alternation (`(a+)+$`, `(a|aa)+$`) go exponential on crafted input [S19]; Python's own `difflib.IS_LINE_JUNK` and `poplib` regexes were CVE-2018-1061/1060 [S23]. Python `re` has no timeout; possessive quantifiers (3.11+) and atomic groups are the in-engine mitigation [S1]. Polynomial (not exponential) blow-ups matter too: [local] `glob.translate('**/*a*a*a*a*a*b*.json')` (3.13+) takes ~3 s on a 100-character name and >20 s at 200, whereas `fnmatch.fnmatchcase('*a*a*a*a*a*b*')` stays at 0.0 s.
* Patterns built from data: `re.escape` every literal; never build from untrusted pattern text; anchor with `fullmatch`/`\A..\Z`; bound input length.

### 1.3 YAML

* YAML 1.2 double-quoted escapes: `\0 \a \b \t \n \v \f \r \e \<space> \" \/ \\ \N \_ \L \P \xNN \uNNNN \UNNNNNNNN`; escapes only apply in double-quoted scalars; a backslash before a line break folds; quoted scalars may span lines [S7]. YAML 1.1 treated U+0085/U+2028/U+2029 as line breaks, 1.2 does not [S7].
* PyYAML implements YAML 1.1 implicit typing ("Norway problem": `NO`, `yes`, `on`, `0777`, sexagesimal, dates) and never adopted the 1.2 schema [S32, S33]. Consequence for a "decode and search" normaliser: parsed non-strings (bool/int/date) vanish from a "join all strings" walk.
* Use `SafeLoader` only; `FullLoader`/`load` have had code-execution CVEs (CVE-2020-14343) [S31]. Aliases ("billion laughs") need an explicit guard.
* The AutoDojo-style `_yaml_escape` is a four-character escape (`\`, `"`, LF, TAB) that is not a full YAML encoder (no `\r`, no other C0, no `\u` forms); its inverse must therefore be a superset (all YAML escapes) and tolerant, which makes inverse+compare lenient by construction.

### 1.4 shlex / argv / paths / file names

* `shlex.quote` is POSIX-shell only and "not guaranteed" on Windows shells; prefer argv lists with `shell=False` [S10].
* Windows names: forbidden `< > : " / \ | ? *`, NUL, 1-31; reserved `CON PRN AUX NUL COM1-9 LPT1-9` plus the superscript-digit forms `COM¹ COM² COM³ LPT¹..` and with any extension (`NUL.txt`); no trailing space or period [S28].
* Unicode normalisation: validate before normalising is a known failure shape - `urlsplit` NFKC (CVE-2019-9636) [S25]; `unicodedata.normalize()` quadratic time on long combining runs (CVE-2026-3276; fixed in 3.14.6+) [S26]. Case-insensitive/normalisation-insensitive filesystems make NFC/NFD and case variants collide [S2 says JCS itself does no normalisation].

### 1.5 CSV, Markdown, HTML

* CSV: open with `newline=''`; the writer quotes `delimiter/quotechar/\r/\n` only [S38]. Spreadsheet formula injection triggers on `= + - @ TAB CR LF` (and fullwidth `＝ ＋`); filtering only the first character is insufficient [S17].
* HTML: `html.escape(s, quote=True)` converts `& < > " '`; `html.unescape` decodes named/numeric references with HTML5 rules [S37]. Graphviz HTML-like strings must be well-formed XML [S4].
* Markdown (CommonMark): any ASCII punctuation can be backslash-escaped; backslash escapes do not work in code spans, autolinks or raw HTML; entity/numeric references decode everywhere except code; raw HTML blocks pass through unescaped [S39]. A report generator must escape data or fence it as code.

### 1.6 Graphviz DOT

* In a double-quoted DOT string the only escape the *lexer* processes is `\"`; other backslash sequences are passed on; backslash+newline continues the string; strings can be concatenated with `+` [S4]. The layout engine then interprets `escString` escapes: `\N \G \E \T \H \L` substitutions and `\n \l \r` line breaks; "a backslash before any other character is ignored"; `\\` yields one backslash [S5].
* **HTML entities are translated to characters during label evaluation** [S4]. [local, Graphviz 16.1.0] `label="x&#x202E;y &lt;U+0041&gt;"` renders a raw U+202E in the SVG and `<U+0041>` for the entity text; `&#27;` emits a raw ESC into the SVG, which then **fails XML parsing**; `&#xE0041;` produced "Invalid UTF-8" warnings and U+DCxx garbage; `&amp;#x202E;` renders literally as `&#x202E;`. So `&` must be escaped (`&amp;`) in addition to `\` and `"`.
* Quoted strings are never HTML-like (only unquoted `<...>` is); `charset` only selects the input encoding (UTF-8 default) [S6]. `#` starts a comment only outside quoted strings [S4].
* pydot: stores values as given and quotes on output; an ID/attribute already matching `^".*"$` is left as is, `^<.*>$` is treated as an HTML label and emitted raw, non-ASCII/NUL strings are quoted; a node name containing `:` is split into name+port, and pydot historically mishandled colons [S29, S30, S41]. Callers should pass pre-quoted strings (as AgentPROV does) and never data-derived node names.

### 1.7 Terminals and logs

* Terminal escape injection: ANSI/OSC sequences in untrusted output can restyle text, change window titles, hide lines; historic title-handling code-execution bugs (2003) and CVE-2015-8971 [S15]; reported 2026 advisories of the same class (e.g. GuardDog default renderer; unverified by me) [S40]. Fix: escape or strip C0/C1/ESC before display; use structured output for machines [S15, S40].
* Log forging (CWE-117): untrusted text with CR/LF creates fake entries; encode output and canonicalise once [S16].
* Trojan Source: bidi controls (and homoglyph identifiers) change displayed order without changing logic; the guidance is to make them visible/reject unterminated ones (CVE-2021-42574, CVE-2021-42694) [S13]. Unicode Tags (U+E0000-E007F) hide ASCII text from humans but LLMs read it ("ASCII smuggling"); filter at prompt and response time [S14]. UTS #39 gives confusable skeletons, restriction levels, Default_Ignorable handling [S24].

### 1.8 RDF, Turtle/TriG, PROV-N, QNames

* Turtle: string escapes `\t \b \n \r \f \" \' \\` + `\uXXXX \UXXXXXXXX`; short strings may not contain raw `"`, `\`, LF, CR; control characters are otherwise legal; IRIREF forbids U+0000-U+0020 and `<>"{}|^`\`; local names cannot end in `.` and need `\`-escapes for reserved characters (`+`, `,`, `;`, ...) [S11]. PROV-N QNames use a PN_LOCAL with PN_CHARS_OTHERS and backslash escapes, no trailing dot, `prov`/`xsd` prefixes cannot be declared [S12].
* Serialiser bugs are a recurring class: Purtle emitted C-style escapes invalid in Turtle (`\a`) [S35]; rdflib once mis-escaped a long string needing an escaped quote [S42]. [local, rdflib 7.6.0 + prov 3.2.2] a PROV-JSON string literal containing NUL, BEL, FF, ESC, DEL, U+2028, tag and bidi characters serialised to TriG with those characters **raw** and re-parsed to the identical value (round trip exact); only `"`, `\`, CR (short form) and LF (long-string form) were escaped. The TriG is legal but not terminal-safe.

---------------------------------------------------------------------------------------------------------------

## Part 2 - Read-only audit of AgentPROV (file:line, hazard, input, effect, severity, tests)

Method: grep of all `re.*` call sites (213 in `src`, `capture/src`, `backends/shared/src`, `tools`), every `json.dumps`, `splitlines`, `isdigit`, `eval`-family and print/log site, then reading the high-risk files, then local experiments (scripts in the session scratchpad, run with the repo venv, `-I -B`, nothing written to the repo).

Severity scale: High (silent wrong science or security), Medium (wrong/lost data or injection into an output artefact, reachable by hostile input), Low (needs unusual input or only degrades diagnostics), Info (hardening / documentation).

### Findings

**F-01 (Medium) - An escaped lone surrogate in message text or a tool result turns the whole execution into a degenerate `adapter_defect` AER.**
* Where: `src/agentprov/aer/_structure.py:158-161` (`s_any_string` accepts only `str`) and `:516,523,527,546` (`text` is `text_or_null`), versus `src/agentprov/aer/canon.py:164-170` (`encode_value` turns such a string into `{"$utf16": ...}`), `:176-181` (a lone surrogate in an object **key** raises `CanonError`), `src/agentprov/aer/writer.py:90` (`AerWriteError: record N is invalid: aer.schema.pattern`), `src/agentprov/adapters/runner/__init__.py:239-240,256-261` (any exception / write error -> `_degenerate(..., "adapter_defect", "aer.write.invalid")`). The adapters do call `encode_value` (e.g. `adapters/agentdojo/mapper.py:178`), so the `$utf16` object is produced and then rejected by the typed `text` field.
* Input (as it appears in a TraceLogger file written with `json.dumps(ensure_ascii=True)`): final assistant `content` = `"cut mid-emoji \ud83d"` (a model output truncated inside a surrogate pair is realistic). Tool-argument key `"k\ud800"` is the key variant.
* Effect [local reproduction with `tests/adapters/agentdojo/agentdojo_support.py::map_log`]: `final_text` and `tool_result` cases raise `AerWriteError(... aer.schema.pattern)`; the `tool_arg_key` case maps with issue `adapter_defect`. In production the unit is replaced by a degenerate AER, i.e. the execution is kept as a stub and its content, SEM and PROV are lost, contrary to the documented policy "an escaped lone surrogate is a finding, encoded `$utf16`" (docs `G_security.md` rule 8; `K_testing.md` 582). `$utf16` in `Json`-typed positions (fixture `content`, `args`) is accepted (`tests/unit/aer/aer_support.py:363`), so the defect is specific to string-typed positions. On the PROV side `src/agentprov/prov/rules/nodes.py:305-313` has no `else` for a non-`str` `text` (it would silently omit `apv:contentSha256` and `apv:contentLength`), but the validator currently prevents that state from being reached.
* Existing tests: `tests/security/test_encoding.py::test_sec01_escaped_lone_surrogate_is_a_finding_and_the_code_units_are_recoverable` covers only the JSON loader. No mapper-level, writer-level or validator-level test of `$utf16` in a text position; no PROV test (`grep utf16 tests/prov tests/unit/prov` is empty).
* Fix direction: either allow `{"$utf16"}` wherever a string is typed (validator, JSON Schema, PROV, SEM readers all decode through `decode_value`) or make the mapper emit a typed issue plus a `unk`/placeholder and keep the rest of the execution. Add a corpus-level count (Part 3, P-SURR).

**F-02 (Medium) - DOT quoting does not escape `&`; Graphviz decodes HTML entities in quoted labels, bypassing `escape_untrusted` (only with `--show-content`).**
* Where: `src/agentprov/render/style.py:103-110` (`dot_quote`: escapes `\`, `"`, CR, LF only), `:113-117` (`display_text`), used at `src/agentprov/render/dot.py:93,99,115`. Default labels (no `--show-content`) are built from grammar-checked tokens (`style.py:54-57`, `token()` uses `fullmatch`) and are not affected.
* Input: attribute value `"x&#x202E;y"` (bidi override), `"&#27;[31m"` (ESC), `"&#0;"`, `"&#xE0041;"`.
* Effect [local, `dot -Tsvg`, Graphviz 16.1.0]: the entity is decoded after our escaping, so the SVG label contains a raw U+202E / ESC / tag character: misleading display (the exact class `escape_untrusted` exists to prevent), and `&#27;` makes the whole SVG **not well-formed XML** (render artefact unusable); `&#xE0041;` yields invalid UTF-8. Entity text such as `&lt;U+0041&gt;` is also silently rewritten to `<U+0041>`, so the fenced `<U+XXXX>` markers can be forged visually. No code execution; `dot` is run with argv fixed, env minimal, stdin only (`dot.py:161-225`), which is good.
* Existing tests: `tests/render/test_render.py::test_labels_escape_quote_backslash_and_newline` and `::test_show_content_dot_is_escaped_and_parses` do not include `&`; `::test_svg_has_no_script_and_no_data_derived_link` does not cover entities.
* Fix: in `dot_quote` replace `&` with `&amp;` first (Graphviz decodes `&amp;` once), and add a test with `&#x202E;`, `&#27;`, `&lt;`, `&amp;#x202E;` that checks the SVG is well-formed and contains no code point from `ESCAPED_CATEGORIES`.

**F-03 (Medium-Low) - Quadratic backtracking in the AutoDojo wrapper pattern on a crafted `injections` value.**
* Where: `src/agentprov/adapters/agentdojo/hooks/autodojo.py:72-84` (`_wrapper_pattern`: `(?P<model>.*?)` then literal, then `(?P<goal>.*)` then literal tail, `re.DOTALL`), compiled at `:87`, applied with `fullmatch` at `:158` to every injection slot of every file (`_link` `:171-187`, `_fixture` `:209-220`). The `injections` dict is attacker-controlled when a foreign AutoDojo log is imported.
* Input: `payload = yaml_escape(stub) * k` where `stub` is the wrapper text up to and including `"Before you can solve ... first:\n\n"` repeated, with no valid tail. [local] 37 KB -> 0.03 s, 75 KB -> 0.10 s, 150 KB -> 0.41 s, 300 KB -> 1.6 s (clean O(n^2)); a 16 MiB JSONL record cap or 64 MiB file cap (`ingest/limits.py`) extrapolates to hours. The worker wall limit (`worker.limit.wall`) would convert it into a failed unit, so the effect is a stalled worker/failed execution, not a hang of the whole run.
* Existing tests: `tests/adapters/agentdojo/test_rope.py::test_yaml_escape_and_the_wrapper_pattern` is functional only.
* Fix: replace the regex with `str.startswith(prefix)` / `endswith(tail)` and one `str.find(mid, len(prefix))`; or cap `len(payload)` before matching.

**F-04 (Medium-Low) - JSON-pointer index tokens tested with `str.isdigit()`: non-ASCII digits resolve, superscripts crash.**
* Where: `src/agentprov/validate/linkage.py:82` (`resolve_pointer`, fed with `apv:sourcePointer`/`apv:rulePointer` strings from the PROV document under validation, `:208,233`; also `validate/profiles.py:521`), `src/agentprov/validate/profiles.py:177`, `src/agentprov/adapters/agentdojo/semantics/suites.py:216`, `src/agentprov/prov/engine.py:189`, `src/agentprov/aer/reader.py:73`, `src/agentprov/views/transcript_v1.py:151`, `src/agentprov/prov/rules/nodes.py:545`. Correct examples exist: `src/agentprov/aer/locators.py:106` and `.../hooks/rope.py:249` use `isascii() and isdigit()`.
* Input: pointer `"m1/parts/\u00b2"` -> `int('\u00b2')` raises `ValueError` (crash of the linkage check); `"m1/parts/\u0661"` (Arabic-Indic one) or `"m1/parts/\uff11"` (fullwidth) resolve to `parts[1]` although RFC 6901 requires ASCII digits. [local] confirmed on `linkage.resolve_pointer`.
* Effect: a downloaded corpus can crash `agentprov validate` for that execution, or have non-canonical aliases accepted as valid evidence pointers (two spellings for one location). Pointers produced by our own rules are ASCII, so this is a validation-side robustness/strictness gap, not a derivation bug.
* Existing tests: `tests/unit/validate/test_evidence_linkage.py::test_resolve_pointer` covers `00`, `x`, missing; no non-ASCII digit case.
* Fix: one shared helper `index_token(token) -> int | None` using `re.fullmatch(r"0|[1-9][0-9]*", token)` and use it at all seven sites.

**F-05 (Low) - TOML plan writer uses JSON string escaping, which is invalid TOML for non-BMP characters.**
* Where: `src/agentprov/cli/run.py:479-488` (`_toml_value`, `json.dumps(value, ensure_ascii=True)`), keys at `:501,504,509`.
* Input: any plan string containing an astral character, e.g. `"model \U0001f600"` -> JSON writes the surrogate pair `\ud83d\ude00`; [local] `tomllib.loads` raises "Escaped character is not a Unicode scalar value". TOML requires `\UXXXXXXXX`. Also a JSON escape set that happens to be TOML-valid for BMP data hides the problem.
* Effect: `agentprov run --plan` round trip fails for such values (operator-supplied, hence Low). Test `tests/cli/test_live_units.py::test_toml_writer_round_trips_a_plan` uses BMP-only data.
* Fix: `json.dumps(value, ensure_ascii=False)` and escape only `\ " ` and C0/DEL by `\uXXXX`, or reject non-BMP; add an astral case to the test.

**F-06 (Low) - Schema `pattern`s use `^...$` with `re.search`: a trailing newline passes.**
* Where: `src/agentprov/io/jsonschema_subset.py:110-112` and `src/agentprov/adapters/agentdojo/profile.py:112` (`re.search(schema["pattern"], value)`); patterns in `adapters/agentdojo/ext.schema.json:20,28,35,36,64,66,67` and `family.schema.json:10,30,32,39,40,89,95,96,126,129,144,182,191,192,202,211,213,228-231` end in `$`. The capture schema already knows the trap and writes `$(?!\n)` (`src/agentprov/schemas/capture-0.1.schema.json:58,151,172,197,369,391,...`).
* Input: `"m12\n"` against `^m[0-9]+$` passes (JSON Schema/ECMA-262 semantics would reject; Python `$` accepts) [S1, S20]. Reachable where SEM values are checked against trusted shipped schemas (`sem/validate.py:540`); profile TOML is trusted, so impact is small.
* Fix: use `re.fullmatch` after stripping the author-supplied `^`/`$`, or rewrite the shipped patterns to `$(?!\n)` as the capture schema does; add one trailing-newline test per schema family.

**F-07 (Low) - Two ad-hoc escapers disagree with `escape_untrusted`; one stderr path is unescaped.**
* `backends/shared/src/agentprov_backend/_jsonval.py:109-119` (`escape_text`) is used for the `error.exception.message` stored in capture events (`session.py:265-267`). It escapes C0/C1, DEL, U+2028/2029, U+FEFF, U+200B-200F, U+202A-202E and surrogates as `\uXXXX`, but **not** U+2060-2064, U+2066-2069 (bidi isolates), U+061C, U+00AD, U+180E, Unicode tags U+E0000-E007F or variation selectors; and `\uXXXX` is ambiguous with literal backslash-u text (no `<`-style disambiguation, unlike `quote.py`). Test `backends/shared/tests/test_units.py:40` covers only a small case. Prefer a call into the `escape_untrusted` algorithm (capture is stdlib-only, so a vendored copy with a shared test vector).
* `backends/shared/src/agentprov_backend/_llm.py:314-315` prints `failure` to stderr raw via `_diag` (`:57-60`); `failure` can embed provider-controlled text (`upstream_failure`, `:109-114`: `f"no choices returned: {error}"` where `error` comes from `model_extra["error"]`). If `error` is a `str` (not a dict) control characters/ESC reach the terminal and `self.upstream_errors`. Dict `repr` is safe (repr escapes), a bare string is not.

**F-08 (Low) - `glob.translate` patterns can blow up polynomially; fnmatch and glob are used interchangeably.**
* `src/agentprov/raw/members.py:156-160` compiles include/nested profile globs with `glob.translate(..., recursive=True, include_hidden=True, seps="/")` joined into one DOTALL alternation, matched at `:427,430`. [local] a segment with several `*` separated by literals (`*a*a*a*a*a*b*`) is super-linear on a 100-300 character label (3 s -> >20 s), while `fnmatch.fnmatchcase` (used by the dialect matchers `adapters/*/dialect.py`, `adapters/runner/importer.py:194-200`, `adapters/agentdojo/profile.py:147`, `identity.py:99`) stays instant. Shipped patterns have at most one `*` per segment (`runs/**/*.json`, `**/._*`, `*-mandate_*`) and labels are capped at 1,024 bytes (`ingest/limits.py`), so this is a latent profile-authoring hazard, not live.
* Semantic divergence: fnmatch `*` crosses `/`, `glob.translate` `*` does not (`'dir/*'` vs `'dir/sub/x'`: fnmatch True, glob False) [local]. Pick one matcher, or add a test that all shipped patterns agree.

**F-09 (Info) - `quote_untrusted` documentation and dead code; residual display gaps.**
* `src/agentprov/ingest/quote.py:11-12` says the body cannot contain `<<`. It can: `"<\x00"` -> `"<<U+0000>"`; [local] 553 of 20,000 random strings over a small hostile alphabet contain `<<`. This cannot forge a fence line (a fence needs `<<UNTRUSTED`/`<<END` at line start, and the second `<` is always followed by `U+`), round trip stays exact (0 failures in 20,000), and the existing test acknowledges it (`tests/security/test_quote_untrusted.py::test_sec12_the_body_can_never_contain_a_double_angle_bracket` strips `<<U+` first). The third clause `(out and out[-1].endswith("<"))` at `:64` is dead (a literal `<` is only kept when the next character is not `<`). Correct the docstring/spec wording.
* Not escaped (display-only, by design): Zs spaces other than U+0020/U+00A0 (U+1680, U+2000-200A, U+202F, U+205F, U+3000), Mn/Me combining marks (1,776 code points: Zalgo; also U+180B-180D, U+180F Mongolian free variation selectors; U+20D0..), and any confusable/homoglyph text [S24]. Acceptable, but mention in the datasheet; Cn depends on the interpreter's Unicode version (documented in the module).

**F-10 (Info) - SEM marker normaliser is deliberately lenient; no false negative found, over-matching possible.**
* `src/agentprov/adapters/agentdojo/semantics/markers.py:53-67` (`_ESCAPE`/`_unescape`) is a port of the v2.3 unescape: `\u12` (short) drops the backslash (`u12`), `\ ` and `\/` and unknown escapes lose the backslash, `\N \_ \L \P` produce U+0085/U+00A0/U+2028/U+2029 (so Windows-path fragments such as `C:\Not\Lost` decode to control/separator characters), and `content_forms` (`:86-89`) decodes **twice** (`levels=2`) plus keeps the raw form. [local] `"see C:\\new folder"` matches payload `"C: ew folder"` as `present`. Since the raw form is always included, a true present is never lost, but a decoded form can create a false `present` for payloads that differ only in an escapable character. `_WS = \s+` (`:55`) and `norm_payload` (`:79-81`) collapse Unicode whitespace (NBSP, U+2028, `\x1c-\x1f`, `\x85`) identically on both sides, which is consistent. Round trip of `yaml_escape` -> `_unescape` is exact (0 mismatches in 20,000 random strings incl. `\r`, NUL, U+2028) [local].
* `payload_span` (`:211-228`) builds `\s+`-joined `re.escape`d tokens: correctly escaped; linear in practice [local: 2,000-token payload over 400 KB, 0.00 s].
* Recommendation: record in the datasheet that marker `present` means "present in at least one of {raw, 1x-unescaped, 2x-unescaped, YAML-parsed, repr, JSON} readings", and report per-reading counts (Part 3, P-MARK).

**F-11 (Info) - Profile regexes are linear and anchored by their callers; one lookalike gap.**
* `profiles/agentdyn.profile.toml:221` and `rope.profile.toml:127` (`^...The tool '[^']*' is not allowed\.\.`), used with `re.search` (`hooks/agentdyn.py:45,53-54`) and `.match` (`hooks/rope.py:63-65,74`): linear, start-anchored. A tool name containing `'` would not match `'[^']*'`, but unknown tool names are rejected earlier by the executor ("Invalid tool ... provided"), so unreachable in practice. `mandate-agentdojo-eval.profile.toml:88` `-(mandate_(?:envelope|scoped|intent))$` is safe because `identity.py:123-127` also requires `found.end() == len(pipeline_name)` (explicitly defeating the `$`-before-newline case). No ReDoS shape found in any TOML regex.

**F-12 (Info) - `\d` in timestamp grammars and `\d+` before `int()`.**
* `src/agentprov/prov/serialise/time.py:17-19` (`RFC3339_RE` with `\d`, `fullmatch`) accepts Arabic-Indic digits at the regex stage; `datetime.fromisoformat` rejects them, so `prov_time` returns `None` and the value is stored lexically [local confirmed: `'٢٠٢٤-01-01T00:00:00Z'` -> `None`; trailing newline -> `None`]. Prefer `[0-9]` for defence in depth. `src/agentprov/io/atomic.py:55,377` (`\.tmp-(\d+)$` then `int()`) can raise on a 4,301-digit name (local directory only). The frozen oracle `prov/compat/adprov_v2_3/build_prov.py:83,105` uses `^...\d...$` with `.match` (accepts a trailing newline); do not change (invariant 8), but do not copy the idiom.

**F-13 (Info) - Raw control characters in derived TriG; `tools/` baseline-parity path helper.**
* `agentprov derive --trig` / the tier-4 round trip writes literals with raw NUL/ESC/BEL/FF/DEL/U+2028 [local, S11 says legal]; `cat`-ing such a file is a terminal-injection vector. Document it, or post-process with `\uXXXX` escapes for C0/DEL/C1/bidi.
* `tools/agentdojo/import_scan.py:96` (`pipeline_folder`) keeps `.` so a pipeline name `".."` yields a `..` path component (baseline parity, comparison tool only; do not reuse for writes).

**F-14 (Info) - `literal_eval` on model-generated arguments in the live backend (upstream parity).**
* `backends/shared/src/agentprov_backend/executor_mirror.py:165-167` mirrors AgentDojo 0.1.35 `ToolsExecutor.query` (source-hash pinned, `:45-48`), so it must not be edited. `is_string_list` pre-checks, but `literal_eval` runs on model output; per S9 deep nesting can raise `MemoryError`/`RecursionError`, which are not caught here. [local] 3.14.8 raises a fast `SyntaxError` for 10^6 nesting. Re-test under the backend's Python 3.12 and record it in the backend quality notes.

### Hazards checked and found sound (what is done well)

* `escape_untrusted`/`quote_untrusted` (`ingest/quote.py`): escapes Cc, Cf, Cs, Co, Cn, Zl, Zp plus NBSP, CGJ, Hangul/Braille fillers, Mongolian vowel separator, FE00-FE0F, E0100-E01EF; `<U+` ambiguity resolved; hash binds content; locator escaped completely. Property tests (`tests/security/test_quote_untrusted.py`, Hypothesis 2,000 + 500 examples) check fence integrity and exact round trip; my 20,000-case fuzz also found 0 round-trip failures. ESC, C1, bidi (incl. isolates), zero-width, tags, surrogates: all verified escaped [local].
* Logging (`cli/common.py:143-153,420-472`): every formatter field goes through `safe_text` (escape, LF/TAB written as `<U+000A>/<U+0009>`, secrets, then home/host), JSON log lines are JCS; `format_exception_safe` escapes every exception argument; `argparse` errors and usage go through `safe_text`; CLI error paths (`cli/main.py:101-112,174,241`) are uniformly wrapped (CWE-117 pattern absent).
* Strict ingest: `strict_json_loads` (`ingest/loaders.py`) takes bytes, rejects BOM/UTF-16 sniff/dup keys/NaN/overflow, iterative depth pre-scan with an unrolled string regex (`:44`, linear [local reasoning]), lone-surrogate finding; JSONL split on LF only (`iter_jsonl`), CR/NUL/blank handled; `capture/verify.py:127` has the same rule. Bytes `splitlines()` at `raw/history.py:265`, `adapters/runner/importer.py:775`, `migration/c6.py:211` is safe only because it is the bytes method.
* JCS: single `rfc8785` import (`io/canonical.py`), `$int/$float/$utf16/$lit` wrappers and UTF-16 key order helper (`aer/canon.py:76-78,133-188`), validator re-serialises each line and requires byte equality; pointer escaping order correct (`~` before `/`; reverse order on decode, `canon.py:61-68`, `prov/engine.py:179`). No manual JSON string building anywhere (`grep` clean).
* Regexes from data all use `re.escape`: `capture/redact.py:340-395,475-478`, `cli/common.py:119-127`, `raw/origins.py:117`, `artefacts/detectors.py:330` (tool names pre-validated by `_TOOL_NAME.fullmatch`, 256-name cap, 100k-char scan cap), `hooks/autodojo.py:77,83`, `markers.py:227`. Layout templates are parsed with string operations, not regex (`adapters/agentdojo/layout.py`). The secret scanner matches plain, every JSON spelling (literal / `\uXXXX` any case / surrogate pairs / short escapes) and percent-encoded forms, and fails closed in a final scan.
* Anchors: all grammar regexes are applied with `fullmatch` (checked every module-level `*_RE`); `$`-style exceptions are guarded (`identity.py:123-127`; `names.py` rejects control characters before its `^..$` match; capture schema uses `$(?!\n)`).
* Names (`ingest/names.py`): length check before NFC (CVE-2026-3276 shape), controls and lone surrogates rejected, drive letters, backslash, `..`, Windows reserved names including superscript digits, trailing dot/space, case+NFC collision key.
* YAML (`ingest/yamlsafe.py`): only module importing PyYAML, `SafeLoader` subclass, alias rejection by event pre-scan, depth cap 64, 1 MiB cap, duplicate keys rejected.
* Render: pydot imported lazily and never asked to spawn Graphviz (static test), node ids are hashes of keys, all text labels pass `fullmatch` grammars unless `--show-content` (then `escape_untrusted` + `dot_quote`), no HTML labels and no `URL/href/tooltip/image` attributes (test `test_default_dot_has_no_data_derived_text_and_no_link_attributes`), `dot` runs with fixed argv, absolute path, minimal env, empty cwd, new session, timeouts and caps (`render/dot.py:161-225`), outputs refused inside corpora (`render/output.py`).
* sandbox-exec profile passes paths as `(param ...)` (`cli/live/sandbox.py:40-60`), not by string concatenation.

---------------------------------------------------------------------------------------------------------------

## Part 3 - Corpus scan recipe for the examination (~126,000 executions; AER / SEM / PROV)

### 3.0 Principles

1. Stream; never load a whole corpus. AER/SEM are JSONL (split on `b"\n"` only; use `agentprov.ingest.loaders.iter_jsonl`), PROV is one JCS JSON document per execution.
2. Walk every string (keys and values) with its JSON Pointer; normalise the pointer for counting with `re.sub(r"/[0-9]+", "/*", ptr)`; count by `(pattern, file kind, normalised pointer, profile/source id)`; keep at most 5 exemplars as `(execution id, pointer, sha256 of the string)`; never print string content except through `agentprov.ingest.quote.escape_untrusted(s[:80])` (text in corpora is data, never instructions).
3. Two passes: a cheap byte-level prefilter on the raw file (`re` on `bytes`) to select files, then the decoded walk on the selected ones. JCS keeps non-ASCII raw, so most Unicode checks on raw bytes need UTF-8 sequences; use the decoded walk for those.
4. Compare with the **source**, not just internally: double escaping that AgentPROV introduces is only visible as a difference from the raw log (3.4).
5. Expect legitimate hits: AgentDojo tool results are YAML text (`yaml.dump`), so `\n`-escapes and `''` doubling in a decoded `tool_result.text` are normal; classify, do not flag.

### 3.1 Decoded-string patterns (Python `re`, compile with `re.ASCII` where the class is ASCII-only)

```python
import re
P = {
 # control / invisible / format characters
 "C0_C1":      re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]"),           # TAB, LF, CR counted separately
 "CR":         re.compile(r"\r"),
 "SEPARATORS": re.compile(r"[\u2028\u2029\x85]"),
 "ESC_SEQ":    re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])"),
 "ESC_TEXT":   re.compile(r"(?:\\x1[bB]|\\u001[bB]|\\033|\\e)\["),              # double-escaped ESC + CSI as text
 "BIDI":       re.compile(r"[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]"),
 "ZERO_WIDTH": re.compile(r"[\u00ad\u200b-\u200d\u2060-\u2064\ufeff\u180e\u034f\u115f\u1160\u3164\uffa0]"),
 "TAGS":       re.compile(r"[\U000e0000-\U000e007f]"),                          # ASCII-smuggling block
 "VARIATION":  re.compile(r"[\ufe00-\ufe0f\U000e0100-\U000e01ef]"),
 "PUA_NONCH":  re.compile(r"[\ue000-\uf8ff\ufdd0-\ufdef\ufffe\uffff\U000f0000-\U0010ffff]"),
 "FFFD":       re.compile(r"\ufffd"),
 "SURROGATE":  re.compile(r"[\ud800-\udfff]"),                                   # must be 0 in valid decoded text
 "MOJIBAKE":   re.compile(r"(?:\u00c3[\u0080-\u00bf]|\u00c2[\u00a0-\u00bf]|\u00e2\u20ac[\u2122\u0153\u201c\u201d\u2013\u2014\u00a6]|\u00f0\u0178)"),
 # double escaping and escaped-form residues (literal backslash sequences in decoded text)
 "LIT_ESC":    re.compile(r"\\(?:[nrtbfv0\"'/\\]|x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8})"),
 "LIT_ESC_2X": re.compile(r"\\\\(?:[nrt\"'\\]|x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4})"),  # backslash-backslash-n: two levels
 "LIT_U_SURR": re.compile(r"\\u[dD][89a-fA-F][0-9a-fA-F]{2}"),                    # a surrogate escape as literal text
 "YAML_DQ_ESC":re.compile(r"\\[\_NLP0aeEv ]"),                                      # YAML-only escapes (\_ \N \L \P ...)
 "ANGLE_U":    re.compile(r"<U\+[0-9A-Fa-f]{4,6}>"),                                # collides with escape_untrusted markers
 "ENTITY":     re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9A-Fa-f]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});"),  # Graphviz/HTML decode
 "PCT_ENC":    re.compile(r"%[0-9A-Fa-f]{2}"),
 # Windows paths damaged by a YAML/Python unescape: drive letter + colon + control/separator char + word char
 "WINPATH_CTRL": re.compile(r"(?i)(?<![a-z0-9])[a-z]:(?:[\x07-\x0d]|[\x85\xa0\u2028\u2029])[a-z0-9_.-]"),
 "WINPATH_OK":   re.compile(r"(?i)(?<![a-z0-9])[a-z]:\\[^\s\"'<>|?*]+"),             # calibration: intact paths
 # python-literal residues (repr of dict/list/object leaked into a text field)
 "PY_REPR_HEAD": re.compile(r"\A\s*[\[{(]\s*[ubrUBR]?'[^'\n]{0,80}'\s*[:,\]})]"),
 "PY_CONST":     re.compile(r"(?<![\w\"'])(?:None|True|False)(?![\w\"'])"),
 "PY_OBJ":       re.compile(r"<[A-Za-z_][\w.]*(?: object)? at 0x[0-9a-f]+>|<class '[\w.]+'>"),
 "PY_CALLS":     re.compile(r"\b(?:datetime\.(?:datetime|date|timedelta)|Decimal|UUID)\('?\d?"),
 "PY_BYTES":     re.compile(r"\bb'(?:[^'\\]|\\.){0,200}'"),
 # trailing newline smuggled into an identifier-like field (check on short strings of id-like fields only)
 "ID_TRAIL_NL":  re.compile(r"\A[A-Za-z0-9_#.:@+/-]{1,200}\n\Z"),
}
```

Interpretation of the counts:

* `SURROGATE` > 0 in a decoded string = a bug (decoded text must be scalar values); check separately that every `{"$utf16": ...}` object decodes to a string whose `SURROGATE` is non-empty.
* `LIT_U_SURR`, `ESC_TEXT`, `LIT_ESC_2X` in `tool_result.text` / `fixture.content`: report the ratio to the count of strings with a real LF; a string with `\\n` and no LF at all (`"\\n" in s and "\n" not in s`) is "wholly escaped".
* `WINPATH_CTRL` > 0 is the signature of `C:\new\table` -> `C:<LF>ew<TAB>able`; `WINPATH_OK` shows how many intact Windows paths exist so the ratio is meaningful. `\N \L \P \_` (YAML) turn `\Not`, `\Lost`, `\Program`, `\_x` into U+0085/2028/2029/00A0; the marker normaliser does this on purpose in its search forms only, so any such character **stored** in AER/SEM/PROV text is a finding.
* `ENTITY` hits in any string that reaches `prov:label`, `apv:*` literals or SEM values are the population exposed to F-02 if rendered with `--show-content`.

### 3.2 Raw-byte patterns (prefilter; canonical files)

```python
B = {
 # JCS output only uses \" \\ \b \t \n \f \r and lowercase \u00xx for the other C0 characters; anything else is non-canonical
 "NONCANON_ESC": re.compile(rb'(?<!\\)(?:\\\\)*\\(?:/|U|u(?![0-9a-f]{4})|u00[0-9a-f]{2}(?<!\\u001[0-9a-f])(?<!\\u000[0-7bBeE]))'),
 "ESC_SURR":     re.compile(rb'(?<!\\)(?:\\\\)*\\u[dD][89a-fA-F][0-9a-fA-F]{2}'),   # must be 0 in JCS bytes
 "NUL_ESC":      re.compile(rb'(?<!\\)(?:\\\\)*\\u0000'),                           # NUL inside a string
 "UTF16_WRAP":   re.compile(rb'\{"\$utf16":'),                                       # escaped lone surrogates (AER only)
 "LIT_WRAP":     re.compile(rb'\{"\$lit":'), "INT_WRAP": re.compile(rb'\{"\$int":'), "FLOAT_WRAP": re.compile(rb'\{"\$float":'),
 "ID_NL_RAW":    re.compile(rb'"[A-Za-z0-9_#.:@+/-]{1,200}\\n"'),                  # id-like value ending in an escaped LF
 "LEX_HINTS":    re.compile(rb'"lex":\{'),
}
```

Expected: `NONCANON_ESC`, `ESC_SURR` and `ID_NL_RAW` are 0 in AER/SEM/PROV (the validators already require byte equality with `jcs_bytes`, so a non-zero count means a writer bug or a tampered file). Cross-check by re-canonicalising: for every line/document `jcs_bytes(strict_json_loads(x)) + (b"\n" if line else b"") == x`.

### 3.3 Structural checks over the decoded trees

* **JSON-in-string fields that fail to parse.** For each string `s` (length >= 2) where `s.lstrip()[:1] in '{["'` and `s.rstrip()[-1:] in '}]"'`, try in order `strict_json_loads(s.encode())` (class `json_ok`), `ast.literal_eval` guarded by `len(s) <= 100_000` and a try/except for `ValueError, SyntaxError, MemoryError, RecursionError` (class `python_repr`), `ingest.yamlsafe.safe_load` (class `yaml_ok`), else `unparsed`; report `unparsed` split by "ends mid-token" (truncation) vs "bad escape". Apply to: `/parts/*/args_raw`, `/parts/*/text` of tool results, fixture `content`, `tool_execution` `error`/`result`, `apv:args`, `apv:error`. For `args_raw`: also check `jcs_bytes(json.loads(args_raw)) == jcs_bytes(args)` when both exist.
* **Identifiers.** In PROV: every key of every section and every `{"$":..., "type":"prov:QUALIFIED_NAME"}` value must fullmatch `agentprov.validate.prov_structure.NODE_NAME_RE | TOP_ELEMENT_RE | STATEMENT_RE`; separately count characters outside `[A-Za-z0-9_.:\-]` with `re.compile(r"[^A-Za-z0-9_.:\-]")` and DOT-special characters with `re.compile(r'["\\<>{}|&\s;=\[\]#]')`; count local names equal (case-insensitively) to `node|edge|graph|digraph|subgraph|strict` (legal after a prefix, but they would be a problem if ids were ever unprefixed). AER ids must fullmatch `aer.ids.LOCAL_ID_RE` / `PART_ID_RE`.
* **Digits.** For every JSON-pointer-like string (`/...` or `m1/parts/0`), flag any token with `not token.isascii() and token.isdigit()` (F-04 population) and `token != str(int(token))` for numeric tokens (leading zeros).
* **Unicode form.** `unicodedata.normalize("NFC", s) != s` and `.isascii()` False on names/labels (`/model/requested`, `/model/served`, `/parts/*/name`, `task_id`, `pipeline` names, origin labels); mixed-script tokens: `len({unicodedata.name(c, "?").split()[0] for c in tok if c.isalpha()}) > 1` for tool names and model ids (UTS #39 flavour [S24]).
* **Lone surrogate census.** Count `UTF16_WRAP` per file and per profile; count degenerate AERs: header/issue code `adapter_defect` with detail `aer.write.invalid`, and `ingest.json.lone_surrogate` findings in the import register (rows for F-01). Every such execution is a lost execution.
* **SEM marker forms (mixed escaped/decoded payloads).** For each `injection_marker` annotation record `(status, normaliser)`; for each fixture payload `p` and its message text `t`, compute which forms of `p` occur in `t` and histogram them per source/profile:

```python
import json
from agentprov.adapters.agentdojo.hooks.autodojo import yaml_escape
def forms(p: str) -> dict[str, str]:
    return {"verbatim": p, "yaml_escape": yaml_escape(p), "json_ascii": json.dumps(p)[1:-1],
            "json_utf8": json.dumps(p, ensure_ascii=False)[1:-1], "py_repr": repr(p)[1:-1],
            "json_json": json.dumps(json.dumps(p)[1:-1])[1:-1]}          # double-escaped
def found(t: str, p: str) -> list[str]:
    return [name for name, f in forms(p).items() if f and f in t]
```

  Report: `present` by normaliser (`yaml_norm` vs `pyrepr_norm`/`json_norm` fallback), `ambiguous` counts, payloads containing any of `\\ " \n \t \r` (escapable) that are `present` only through an unescaped reading, and any `present` where `found(t, p)` is empty (a match that exists only in a decoded or whitespace-collapsed reading - the over-matching class of F-10). Keep a 200-execution manual review sample drawn from `found == ['json_json']` and from the Windows-path payloads.
* **PROV literals.** Count PROV string attributes containing `C0_C1`, `BIDI`, `TAGS`, `ENTITY`, `ANGLE_U` (population for DOT `--show-content` and for TriG terminal safety); verify no attribute value is a `{"$utf16": ...}` wrapper dict and that every `apv:contentSha256` equals `sha256(text.encode("utf-8"))` of the AER part it points to (spot-check 5,000).

### 3.4 Differential checks against the source (the only way to detect AgentPROV-introduced double escaping)

1. Stratified sample: every execution flagged by any 3.1/3.3 pattern (capped) plus 1,000 random per source family. For each: read the raw artefact from the raw store (`agentprov.raw`), `strict_json_loads`, run the adapter mapper in-process, and require (a) AER bytes identical to the corpus AER (determinism), (b) for each message part `parts[k].text` / `content` string equality with the source string at the mapped pointer (not modulo whitespace), (c) tool-call `args` equal to the source `args` via `jcs_bytes`, (d) fixture `content` equal to the `injections` value.
2. Run the existing integrity commands unchanged: `agentprov validate --corpus C`, `agentprov recompute --corpus C --check` (expect 0 differences), `agentprov verify --corpus C --level chain`; add the new scans as a read-only report under `docs/reports/analysis` tooling (e.g. next to `tools/analysis/phase10_probe_markers.py`) rather than in the corpus.
3. Re-run `tools/analysis/phase10_marker_cause.py`-style classification on the `ambiguous`/fallback markers with the six forms above to quantify YAML-rejected outputs (PyYAML rejects non-printable characters and implicit keys > 1,024 characters, so such tool outputs fall through to the fallback readings).

### 3.5 Scanner skeleton (read-only; pointer-aware; shards by file)

```python
import concurrent.futures as cf, collections, hashlib, json, re
from agentprov.ingest.loaders import iter_jsonl, strict_json_loads
from agentprov.ingest.quote import escape_untrusted

def walk(node, ptr=""):
    stack = [(node, ptr)]
    while stack:
        n, p = stack.pop()
        if isinstance(n, str):
            yield p, n
        elif isinstance(n, dict):
            for k, v in n.items():
                kp = p + "/" + k.replace("~", "~0").replace("/", "~1")
                yield kp + "#key", k                      # keys are data too
                stack.append((v, kp))
        elif isinstance(n, list):
            stack.extend((v, f"{p}/{i}") for i, v in enumerate(n))

def scan_file(path):                                     # returns Counter + exemplars, no raw content
    counts, ex = collections.Counter(), collections.defaultdict(list)
    kind = "prov" if path.endswith(".prov.json") else ("sem" if ".sem." in path else "aer")
    with open(path, "rb") as fh:
        docs = ([(0, 0, strict_json_loads(fh.read()))] if kind == "prov" else iter_jsonl(fh, issues=[]))
        for _line, _off, doc in docs:
            for ptr, s in walk(doc):
                npn = re.sub(r"/[0-9]+", "/*", ptr)
                for name, rx in P.items():
                    if rx.search(s):
                        counts[(name, kind, npn)] += 1
                        if len(ex[(name, kind, npn)]) < 5:
                            ex[(name, kind, npn)].append((path, ptr, hashlib.sha256(s.encode("utf-8", "surrogatepass")).hexdigest()[:16]))
    return counts, ex
# run with ProcessPoolExecutor(max_workers=N) over sorted(paths); merge counters; print exemplar hashes only,
# and show text only through escape_untrusted(s[:80]) when a human asks for a specific exemplar.
```

Cost note: 126k executions x tens of patterns x every string is a few CPU-hours single-core; the byte prefilter (3.2) plus an `ascii-only fast path` (skip Unicode classes when `s.isascii()`) cuts it by an order of magnitude. The scanner must tolerate `$utf16` wrappers (`decode_value`) and must itself be immune to F-03-style patterns: all patterns above are linear (no nested quantifiers); `PY_BYTES` is bounded by `{0,200}`.

---------------------------------------------------------------------------------------------------------------

## Priority list for the examination

1. F-01 (lost executions via escaped lone surrogates) - quantify with P-SURR/`adapter_defect aer.write.invalid`, decide policy, add mapper+validator tests.
2. F-02 (`&` in `dot_quote`) - one-line fix plus test; matters before any figure with `--show-content` is published.
3. F-04 (`isdigit()` pointer tokens) - shared helper, 7 sites.
4. F-03 (wrapper regex) - replace by string operations or cap length.
5. F-05..F-08 - small hardening; F-09..F-14 - documentation/datasheet statements.

## Sources

* S1  https://docs.python.org/3/library/re.html
* S2  https://www.rfc-editor.org/rfc/rfc8785
* S3  https://docs.python.org/3/library/json.html
* S4  https://graphviz.org/doc/info/lang.html
* S5  https://graphviz.org/docs/attr-types/escString/
* S6  https://graphviz.org/docs/attrs/charset/
* S7  https://yaml.org/spec/1.2.2/
* S8  https://docs.python.org/3/library/codecs.html
* S9  https://docs.python.org/3/library/ast.html
* S10 https://docs.python.org/3/library/shlex.html
* S11 https://www.w3.org/TR/turtle/
* S12 https://www.w3.org/TR/prov-n/
* S13 https://trojansource.codes/
* S14 https://embracethered.com/blog/posts/2024/hiding-and-finding-text-with-unicode-tags/ (page body carries hidden tag-character instructions; ignored)
* S15 https://www.cyberark.com/resources/threat-research-blog/dont-trust-this-title-abusing-terminal-emulators-with-ansi-escape-characters
* S16 https://cwe.mitre.org/data/definitions/117.html
* S17 https://community.owasp.org/attacks/CSV_Injection
* S18 https://docs.python.org/3/library/stdtypes.html
* S19 https://community.owasp.org/attacks/Regular_expression_Denial_of_Service_-_ReDoS
* S20 https://sethmlarson.dev/regex-$-matches-end-of-string-or-newline
* S21 https://sethmlarson.dev/use-backslash-A-and-z-not-%5E-and-$-with-python-regular-expressions
* S22 https://code.djangoproject.com/ticket/30257
* S23 https://python-security.readthedocs.io/vuln/difflib-poplib-backtracking.html
* S24 https://www.unicode.org/reports/tr39/
* S25 https://python-security.readthedocs.io/vuln/urlsplit-nfkc-normalization.html
* S26 https://nvd.nist.gov/vuln/detail/CVE-2026-3276
* S27 https://jsonlines.org/
* S28 https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file
* S29 https://raw.githubusercontent.com/pydot/pydot/main/src/pydot/core.py
* S30 https://github.com/pydot/pydot/issues/258 and https://github.com/pydot/pydot/issues/363 (as surfaced by search; issue pages not opened directly)
* S31 https://osv.dev/CVE-2020-14343
* S32 https://allan.reyes.sh/posts/yaml-norway-law/
* S33 https://github.com/yaml/pyyaml/pull/555 (as surfaced by search)
* S34 https://cvefeed.io/vuln/detail/CVE-2021-44420
* S35 https://phabricator.wikimedia.org/T145757
* S36 https://nvd.nist.gov/vuln/detail/CVE-2026-23920
* S37 https://docs.python.org/3/library/html.html
* S38 https://docs.python.org/3/library/csv.html
* S39 https://spec.commonmark.org/0.31.2/
* S40 https://www.sentinelone.com/vulnerability-database/cve-2026-44972/ (search-result summary only; not independently verified)
* S41 https://lightrun.com/answers/pydot-pydot-colon-in-node-names-and-edges
* S42 https://lists.w3.org/Archives/Public/public-rdf-comments/2012Mar/0003.html (search-result snippet only)
