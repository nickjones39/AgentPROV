# Phase-10 corpora, examination 2: research-based data-quality checks

Date: 2026-10-11. Analyst: Claude (worktree session, read-only on the corpora and on `main`). Code: `main` @ `cc1aa51`
(the corpora were derived on `afe7038`; no file under `src/` differs in a way that affects derivation, and no file
under `src/` was changed by this examination). Inputs: the four research briefs, copied unchanged to
`docs/reports/analysis/research/` (A1 methodology, A2 GenAI error classes, A3 W3C PROV issue classes, A4 escaping
audit), the first analysis `phase10-corpus-analysis.md` (cited as "first analysis", its sections as FA §n) and the C5
side note (`research/C5-identical-trajectories.md`).

This report does not repeat the first analysis. It adds the checks the first analysis did not run, extends the checks it
ran on five corpora to all eight, and resolves the piguard / prompt_guard_2 question left open by C5.

Sections 1 and 2 were written and committed **before** any new check was run (pre-registration, A1 §3 P0 and §6.4).
Results begin in section 3.

---

## 0. Summary (written after the checks; sections 1 and 2 are the pre-registration)

**Nothing is malformed, and nothing the research briefs warned about is live in the data.** Over all eight corpora
(126,351 executions; 4.46 million AER records, 5.21 million SEM records, 126,351 PROV documents, 0.64 million index,
register and origin lines; about 34 GB), census results:

- an independent strict parser rejects nothing (no duplicate key, `NaN`/`Infinity`, overflowing float, integer beyond
  I-JSON outside six `$int` wrappers, lone surrogate, BOM or trailing data), and a second JCS implementation (own
  ECMAScript number formatting, own UTF-16 key order) reproduces every canonical line and document byte for byte;
- every AER record validates against the published JSON Schema with an independent engine (`jsonschema`);
- the PROV-CONSTRAINTS checks the validator does not run all pass: no strict-order (Constraint 42) or other event cycle
  in 1.78 million views, no dependency/communication/derivation/specialisation cycle, no C51 or C26 violation, no
  entity with two generators even after the normal-form expansion, no dangling reference in the application views
  (36.5 million inference-bundle arguments re-resolved), and every shared `raw:`/`sw:`/`rules:` statement is identical
  across the documents of a corpus;
- SEM and PROV re-derived from the AER under six environment configurations (time zones, locales incl. `tr_TR`,
  hash seeds, UTF-8 mode, 1 vs 4 workers) are byte-identical in 1,305 of 1,305 sampled executions each (95 % upper
  bound 0.23 %), tiers 3-4 reproduce, and re-mapping the raw object reproduces the AER in 350 of 350;
- the F-01 (`$utf16` in a string position), F-04 (non-ASCII pointer digits) and F-02 (DOT entities) populations are
  0, 0 and 3 literals; no damaged Windows path, U+2028/2029, bidi or tag character is stored; no machine-specific path
  is in any corpus file;
- the three corpora not in the first analysis pass every first-analysis check (integrity chain, register, AER-vs-raw
  fidelity for 2024-06: 0 mismatches in 18,241), and their phase-9 → phase-10 differences are exactly the expected
  ones.

**What is new.** (1) The **AgentDyn gemini-2.5-flash identity** (C5 item 9) is neither duplicated files nor a defence
that never acted: the three PI-detector arms were generated under conditions in which the model answered identical
context identically (divergence only where the detectors decided differently; 174 of the 425 identical
piguard/prompt_guard_2 pairs have identical redactions), while the undefended arm of the same model differs from every
detector arm at the first reply in 648 of 648 cells. Detector-versus-undefended comparisons for this model mix the defence
effect with an unrecorded generation-condition effect (§8). (2) **14,182 executions are in both agentdojo-2024-06 and
agentdojo-head** under the same id with different AER/PROV (origin revision): pooled analyses must deduplicate (§7.3).
(3) Models write **escaped newlines into tool arguments** (head 436 executions; Gemini 1.x, Llama-3.3, SecAlign-70B),
judged 20/20 genuine (§4.1). (4) The B1 miss is confined to ROPE's AutoDojo arm and is larger than first measured:
1,235 executions by an exact whole-payload census (§4.2). (5) The SEM marker's broad normaliser is justified: every
`present` marker the literal readings cannot explain is explained by a repr/double-repr/`''`-undoubling reading, 17 of 17
judged true (§4.2).

**Proposed fixes, ranked** (none applied; details §9.1):

| # | Fix | Digest / corpus impact |
|---|---|---|
| b1 | Validator: event-ordering check (Constraint 42), C51, C26 and cycle lints; correct "not instantiable" in `validate/constraints.py:17` and EF E.1.4 | validation rows (`digests.validation`) of every corpus; no AER/SEM/PROV change |
| b2 | `missing_tool_result` is a declared loss: add to `_LOSS_CODES` (`adapters/runner/importer.py:128`) | index/`corpus.json` only: 4 AgentHarm rows `verified_complete` → `known_incomplete` |
| b3 | Inspect: associate run/step scopes with the harness (D rule), or document the isolation | AER/SEM/PROV of AgentHarm (1,056) |
| b4 | Shared ASCII index-token helper at seven `isdigit()` sites (F-04) | none (0 affected strings) |
| b5 | Catalogue entries for 156 unclassified safety-net findings (AgentHarm 35, adprov-v1 121) | none (catalogue only) |
| b6 | F-01: accept `$utf16` in string-typed AER positions (format decision, `aer/0.1` frozen) | none today (0 affected) |
| b7 | DOT `&` escaping (F-02) | none (render only) |

**New manuscript artefacts** (§10): N1 cross-corpus duplicates; N2 double-escaped tool arguments; N3 the gemini-2.5-flash
generation-condition split; N4 empty assistant turns (AgentDyn 4,631 runs end with an empty reply); N5 dropped high
bytes in model text; N6 model-confounded completeness in adprov-v1 (all deepseek-chat `unverifiable`); N7 PROV times only
in two sources; N8 model type errors in arguments; plus the first-analysis rows extended with 2024-06, adprov-v1 and
AgentHarm counts.

**Not done**: SEM JSON-Schema validation (no SEM schema); an external PROV-CONSTRAINTS oracle (ProvToolbox/`prov-check`
not installed, no network); MinHash near duplicates; a double-annotated label audit; D02 for AgentHarm (container
dialect not replayed); a second full run for byte-identical result files (Q-071).

---

## 1. Method

### 1.1 Scope and population

| Corpus (`~/.agentprov/corpora/…`) | Source · part | Profile | Executions | In first analysis |
|---|---|---|---:|---|
| `rope-p10.partial` | ROPE · head | `rope@1` | 10,791 | yes |
| `agentdyn-a-p10.partial` | AgentDyn · a | `agentdyn@1` | 38,281 | yes |
| `agentdojo-upstream-head-p10.partial` | AgentDojo HEAD | `agentdojo-upstream@1` | 36,679 | yes |
| `mandate-agentdojo-eval-p10.partial` | Mandate | `mandate-agentdojo-eval@1` | 396 | yes |
| `ast-survey-agentdojo-p10.partial` | survey · agentdojo-runs | `survey-runs@1` | 3,243 | yes |
| `agentdojo-upstream-2024-06-p10.partial` | AgentDojo 2024-06 | `agentdojo-upstream@1` | 18,241 | **no** |
| `adprov-v1-release-p10.partial` | AgentDojo-PROV v1 release (transcript/v1) | `adprov-v1@1` | 17,664 | **no** |
| `ast-survey-agentharm-p10.partial` | survey · AgentHarm (Inspect) | `survey-agentharm@1` | 1,056 | **no** |
| **Total** | | | **126,351** | |

Population statement (A1 P0): the corpora are a census of what was imported, not a sample of agent executions in
general. Every corpus-level number below is a census count with its denominator and needs no interval. Intervals are
given only for the sampled checks of 1.4, and only as statements about the corpus they were drawn from.

Units: execution (one `executions.jsonl` row), record (one AER/SEM JSONL line), document (one PROV-JSON file),
statement (one PROV relation or element), string (one decoded JSON string value or object key). Each table names its
unit.

Read-only discipline: corpora are opened only for reading. Re-derivation (D01, D02) runs in memory or in a temporary
directory in the session scratchpad and compares digests; nothing is written into a corpus or the raw store. Corpus
content is untrusted data (deliberate injection payloads): no source text is printed; where an excerpt is needed it is
short and passed through `agentprov.ingest.quote.escape_untrusted`. Outputs hold counts, normalised JSON pointers,
execution ids and truncated SHA-256 digests only.

### 1.2 Phases (A1 §3, adapted)

| Phase | Here |
|---|---|
| P0 scoping and freeze | versions, commits, corpus digests recorded in §9; this pre-registration |
| P1 profiling | reused from the first analysis for five corpora (FA §2–§4); run on the three new corpora (R01–R07) |
| P2 structural validity | X01–X05 (independent strict parse and second JCS implementation), census |
| P3 semantic consistency | U01–U14 (string content), A01–A05 (AER semantics), census |
| P4 integrity and determinism | reused chain checks (FA §2) on the new corpora; D01–D02 metamorphic re-derivation, sampled |
| P5 graph quality | P01–P11 (PROV-CONSTRAINTS checks the validator does not run, graph metrics), census |
| P6 source artefacts | the three new corpora; S01 (piguard / prompt_guard_2) |
| P7 reporting | §4–§8 with the first analysis' classification (a)–(d) |

### 1.3 Finding classes (A1 §7.1, first analysis §0)

- **(a)** source-data property, faithfully represented and disclosed (no fix);
- **(b)** processing defect or improvement (fix proposed with file:line, rule/spec section, expected effect on digests
  and corpora, risk; **not applied**; ranked by impact);
- **(c)** question for the user;
- **(d)** analysis artefact (introduced by an audit tool; the audit is corrected, nothing is reported as a corpus property).

Attribution order (A1 §7.1): present in the raw bytes and faithfully represented → (a); present in raw but lost,
invented or distorted downstream → (b); only in an analysis output → (d); raw unavailable or ambiguous →
"undetermined", listed with the evidence needed.

### 1.4 Census and sampling plan (fixed before running)

**Census (no interval; "0 of N" when nothing is found):** every check of section 2 except D01 and D02, and the
judgement steps listed below.

**Sampled:**

| Check | Frame | Stratification | n | Seed | Interval |
|---|---|---|---:|---|---|
| D01 SEM+PROV re-derivation under an environment matrix | all executions with `stages.prov = ok` | corpus × profile × {issues present, absent} × completeness, proportional with a minimum of 10 per stratum, total 150 per corpus | 1,200 | 20261011 | zero-event: one-sided 95% Clopper-Pearson upper bound (n = 1,200 gives 0.25%); otherwise Wilson 95% |
| D02 AER re-mapping from the raw store | whole-file executions of the seven TraceLogger/transcript corpora | corpus × status | 350 (50 per corpus) | 20261011 | as D01 |
| Judgement of string-content hits (U06, U07, U08, U09) | executions with a hit, per pattern and pointer class | pattern × pointer class | up to 20 per cell, reviewed as escaped excerpts | 20261011 | descriptive (precision of the screen reported with Wilson 95%) |

Environment matrix for D01 (A2 P0-2, C3): `TZ` ∈ {UTC, Pacific/Auckland, America/St_Johns}; `LC_ALL`/`LANG` ∈ {C,
tr_TR.UTF-8 (if installed, else de_DE.UTF-8), en_US.UTF-8}; `PYTHONHASHSEED` ∈ {0, 1, random}; `PYTHONUTF8` ∈ {0, 1};
worker count 1 versus 4 (the same sample split over four processes). Pass criterion: SEM and PROV bytes equal to the
corpus files (index digests) in every configuration; any difference is a finding.

Thresholds (pre-registered): every structural check (X, P01–P06, P10, P11, U02) is zero-tolerance: one occurrence is a
finding. Content screens (U03–U14, A01–A03) are descriptive: a hit is a screen, classified only after attribution.
Outlier screens use the IQR fence (Q3 + 3·IQR) within a corpus. No threshold is tuned on the data.

Multiple comparisons (A1 §6.4): no confirmatory hypothesis is tested; all content screens are exploratory and are
reported as counts, not as significant differences. Mechanical checks are not hypothesis tests.

Calibration (A1 §8, fault injection): before the census, the scanner is run on mutated copies (in the scratchpad) of a
few corpus files: duplicate key, `NaN`, non-canonical whitespace, a reordered key, a `1.0` number, a lone-surrogate
escape, a `wasDerivedFrom` cycle, a `wasDerivedFrom` with usage but no activity, a duplicate `wasStartedBy`, a dangling
argument. Each mutation must be detected by its check; the detection table is reported in §3.0.

### 1.5 Threats to validity (planned mitigations; results in §11)

- *Circularity*: the project validates its own output. Mitigations: an independent strict parser (stdlib hooks, not
  `strict_json_loads`), an independent JCS implementation (own number formatting and key ordering, not `rfc8785`),
  independent PROV graph code (not `agentprov.validate`), and metamorphic re-derivation. Independence is partial:
  same analyst family and same specifications.
- *Construct*: structural validity is not truth; completeness is relative to the AER and the rule catalogues.
- *Instrument*: regex screens have unknown precision; precision is estimated on the judged samples of 1.4.
- *External*: results describe these eight corpora on this code; nothing generalises to other benchmarks.

---

## 2. Check map

Origin: A1/A2/A3/A4 = research brief (item ids), FA-gap = a gap the first analysis left, new = proposed here. Status:
**new**; **reused** (first-analysis tool, cited); **extended** (first-analysis check widened in scope or depth).
Scope: "all 8" or the listed corpora.

| Id | Check | Origin | Status | Scope |
|---|---|---|---|---|
| R01 | Integrity chain, AER/SEM/PROV facts, safety net (`tools/analysis/phase10_extract.py`) | FA §2–§4 | reused | 3 new |
| R02 | Per-corpus tables (`phase10_aggregate.py`) | FA §2–§4 | reused | 3 new |
| R03 | AER vs raw end-to-end fidelity (`phase10_crosscheck.py`, TraceLogger only) | FA §5 | reused | 2024-06 |
| R04 | Register vs index vs manifest (`phase10_register.py`) | FA §2 | reused | 3 new |
| R05 | Identical-trajectory groups (`phase10_dups.py`) | FA §4.6 | reused | 3 new |
| R06 | Payload visibility vs injection markers (FA `phase10_probe_markers.py`; superseded by the A05 census and `exam2_b1check.py`, exact whole-payload) | FA §3.3 | extended | 7 agentdojo-family |
| R07 | Rule placement and D-rule citations (`phase10_rule_classes.py`) | FA §6, C6 | reused | 3 new |
| X01 | Independent strict re-parse: strict UTF-8, BOM, duplicate keys, `NaN`/`Infinity`, float overflow (`1e400`), integers beyond ±(2^53−1), lone surrogates in strings and keys, trailing data; AER, SEM, PROV, `executions.jsonl`, `register.jsonl`, `validation/results.jsonl`, `raw/origins.jsonl`, `raw/members.jsonl`, `corpus.json`, `derivation.json`, `validation/summary.json` | A1 Q-020; A2 D1, P0-3 | extended (FA used the project's loader on AER/SEM/PROV) | all 8 |
| X02 | Second JCS implementation (own number formatting per ECMAScript, own UTF-16 key order, own string escaping) compared byte for byte with every canonical line/document | A1 Q-022; A2 C1, D2, P0-4 | new | all 8 |
| X03 | Number-form and key-order census: integral floats (`ext.lex.flt`), `$int`/`$float`, objects whose UTF-16 and code-point key orders differ, exponent forms | A2 C1, A7, A9 | new | all 8 |
| X04 | RFC 8785 vectors and edge numbers on both canonicalisers (calibration) | A2 C1 | new | — |
| X05 | JSONL framing: LF-only, no CR, no blank line; raw characters that would split a line under `str.splitlines()` | A2 D3; A4 1.1 | new | all 8 |
| X06 | Every AER record validated against the published `aer-0.1.schema.json` with `jsonschema` `Draft202012Validator.iter_errors` (an engine independent of the project's typed validator) | A1 Q-021 | new | all 8 (census; if throughput forbids, a seeded systematic 1-in-10 sample of executions, stated in §3) |
| U01 | `$utf16`, `$lit`, `$int`, `$float` wrappers by pointer | A4 F-01, 3.2 | new | all 8 |
| U02 | Lone surrogates, escaped (bytes) and decoded (must be 0 outside `$utf16`) | A2 A8; A4 3.1 | new | all 8 |
| U03 | U+2028, U+2029, U+0085 | A2 D3; A4 3.1 | new | all 8 |
| U04 | C0/C1 controls (TAB, LF counted apart), CR, NUL, ESC and ANSI/OSC sequences, escaped ESC as text | A2 E2; A4 3.1 | extended (FA: message text, 5 corpora) | all 8 |
| U05 | Bidi, zero-width, tag characters, variation selectors, PUA/non-characters, U+FFFD, mojibake | A2 A8; A4 3.1 | extended | all 8 |
| U06 | Double-escaping residues in decoded text (literal `\n`, `\\n`, `\uXXXX`, escaped surrogates, YAML-only escapes; wholly-escaped strings) | A2 A3; A4 3.1 | new | all 8 |
| U07 | Windows paths damaged by unescaping (drive + colon + control/separator) vs intact paths | A2 A2; A4 3.1 | new | all 8 |
| U08 | JSON-in-string fields: strict JSON / Python repr / YAML / unparsed (truncated vs bad escape) | A2 A2; A4 3.3 | new | all 8 |
| U09 | Python-repr residues (dict/list heads, object reprs, `datetime(`/`Decimal(`/`UUID(`, `b'…'`) | A4 3.1 | new | all 8 |
| U10 | Marker and render exposure in PROV literals (`<U+XXXX>`, HTML entities, `![`, `<script`) | A4 F-02, 3.3 | new | all 8 |
| U11 | Identifier grammar: AER ids, PROV keys and QName values; id-like strings ending in LF | A4 3.3; A3 PI-15 | new | all 8 |
| U12 | Pointer tokens with non-ASCII digits (F-04) and leading zeros | A4 F-04 | new | all 8 |
| U13 | NFC and mixed-script names (model ids, tool names, task ids) | A2 A8; A4 3.3 | new | all 8 |
| U14 | Absolute paths, user names, secret-shaped strings in AER/SEM/PROV/index/manifests | A2 C7, P1-15 | new | all 8 |
| A01 | Tool-call argument census: types, double-encoded arguments, key-set and type drift per tool | A2 A2, A6 | new | all 8 |
| A02 | Stop/finish-reason census | A2 A1, A4 | new | all 8 |
| A03 | Empty assistant turns without tool calls; empty final answers | A2 A4 | extended (FA §8 row 13) | all 8 |
| A04 | Degenerate executions (`adapter_defect`, `aer.write.invalid`, `unparseable_artefact`), and the source-side population: escaped lone surrogates, duplicate keys, non-finite numbers and big integers in the raw JSON objects | A4 F-01; A2 D1 | new | all 8 |
| A05 | Payload-form histogram (verbatim, YAML-escaped, JSON-escaped, repr, double JSON) against SEM marker status, every attacked execution | A4 3.3, F-10 | extended (FA B1: ROPE AutoDojo, samples elsewhere) | 7 agentdojo-family |
| P01 | Event-ordering validity without times: strict-order cycles (Constraint 42) in the event graph, per container, per core ∪ inference view, per core ∪ assessment view | A3 PI-04, PI-05 | new | all 8 |
| P02 | Cycles: used/generated dependency, `wasInformedBy`, `wasDerivedFrom`, `specializationOf` ∪ `mentionOf` | A3 PI-08, PI-24 | new | all 8 |
| P03 | Constraint 51: `wasDerivedFrom` with generation or usage but no activity | A3 PI-07 | new | all 8 |
| P04 | Constraint 26: duplicate start events; Constraint 24 re-checked independently | A3 PI-02 | new | all 8 |
| P05 | Normal-form expansion (Inferences 9/10, 11, 13, 14) and the single-generator rule on the expanded view; attribution and delegation lints | A3 PI-11, PI-12, PI-31 | new | all 8 |
| P06 | Dangling references, independent resolution | A3 PI-26 | extended (validator `pv.prov_structure.references`) | all 8 |
| P07 | Cross-document consistency of shared `raw:`/`sw:`/`rules:` top-level statements and prefixes, within each corpus and across the eight | A3 PI-30 | new | all 8 |
| P08 | `mentionOf` census and resolution | A3 PI-17 | new | all 8 |
| P09 | Graph metrics: degree distributions, weak components (core; core ∪ inference; plus attribute links), `apv:Gap` share, start-time coverage, orphan classes | A3 PI-25, PI-27; A1 Q-054, Q-055 | extended (FA §4.1–4.2: 5 corpora, components only) | all 8 |
| P10 | PN_LOCAL trailing `.`, namespace IRIs ending in `#` or `/` | A3 PI-15 | new | all 8 |
| P11 | Multi-valued statement keys (arrays under one id) | A3 PI-01 | new | all 8 |
| D01 | Determinism of SEM+PROV re-derivation under TZ, locale, hash seed, UTF-8 mode, worker count | A1 Q-035, Q-042; A2 C3, P0-2 | new | sample, all 8 |
| D02 | Determinism of AER re-mapping from raw (re-import yields identical bytes) | A1 Q-035 | new | sample, 7 whole-file corpora |
| S01 | piguard vs prompt_guard_2 identical trajectories (AgentDyn gemini-2.5-flash) | C5 item 9 | new | agentdyn |
| C00 | Fault-injection calibration of the scanner | A1 §8 | new | — |

Not run, with reason: JSON-Schema validation of SEM (no published SEM schema file); Q-024 external PROV-CONSTRAINTS oracle
(ProvToolbox/`prov-check` not installed and no network); Q-044 MinHash near-duplicates (exact duplicates are covered by
FA §4.6 and R05; near duplicates are out of scope); Q-062 double-annotated label audit (single analyst).

---

## 3. Structural validity (X01–X06) and calibration (C00, X04)

### 3.0 Calibration

Fault injection on one Mandate execution (`selftest.json`; mutated copies in memory only): every mutation was detected by
its check — duplicate key, `NaN`, `1e400`, BOM and trailing data by X01; inserted whitespace, a reordered key, `1.0`, an
upper-case `\u001F` escape by X02; an escaped lone surrogate by X02 (`lone_surrogate`); an integer of 2^53+1 by the X01
flag; a two-statement `wasDerivedFrom` cycle by P01 (strict cycle) and P02 in every view; a `wasDerivedFrom` with
`prov:generation` and no activity by P03; a duplicate `wasStartedBy` by P04; a dangling `used` argument by P06; a
used/generated self-loop by P02. Detection 15 of 15. The unmutated document gives no finding.

X04: the second canonicaliser equals `rfc8785` (the code under test) on 27 edge numbers (`-0.0`, `1e21`, `1e-7`,
`5e-324`, `1.7976931348623157e308`, `2^53−1`, …), on 200,000 seeded random doubles (0 differences), on a key set mixing
ASCII, U+00E9, U+E000, U+FFFF, U+10000 and U+1F600 (UTF-16 order: astral keys before U+E000), and on all C0
characters, `"`, `\`, U+007F, U+2028, U+2029, U+0085. Both reject 2^53 and a lone surrogate.

### 3.1 Census results

Unit: AER and SEM records (JSONL lines), PROV documents, strings (decoded values and keys). Source:
`phase10-examination-2-data/scan-<corpus>.json` (tool `exam2_scan.py`, merged by `exam2_merge.py`, tables by
`exam2_tables.py`).

| Check | rope | agentdyn | head | mandate | survey | 2024-06 | adprov-v1 | agentharm |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| executions | 10,791 | 38,281 | 36,679 | 396 | 3,243 | 18,241 | 17,664 | 1,056 |
| analysis errors | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| AER records / SEM records / PROV docs | 505,333 / 677,139 / 10,791 | 1,552,020 / 1,849,022 / 38,281 | 1,153,595 / 1,307,491 / 36,679 | 11,728 / 11,390 / 396 | 95,836 / 105,131 / 3,243 | 553,182 / 641,590 / 18,241 | 534,987 / 605,191 / 17,664 | 54,832 / 16,700 / 1,056 |
| bytes AER+SEM+PROV (GB) | 4.9 | 14.17 | 7.2 | 0.07 | 0.7 | 3.37 | 3.11 | 0.23 |
| X01 strict-parse failures (all classes) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| X01 integers beyond I-JSON / -0 tokens | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| X02 second-JCS mismatches / errors | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| X05 framing (no final LF, CR, blank line) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| X05 raw U+2028/2029/U+0085 in lines | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| non-canonical escapes (bytes) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| X03 floats in trees / integral floats in trees | 12,558 / 0 | 47,566 / 0 | 37,828 / 0 | 491 / 0 | 3,357 / 0 | 18,670 / 0 | 17,769 / 0 | 28,431 / 0 |
| X03 objects whose UTF-16 and code-point key order differ | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| X03 ext.lex flt pointers / ord objects | 1,111 / 45,468 | 2,747 / 149,677 | 8,094 / 66,230 | 594 / 1,311 | 0 / 7,186 | 3,367 / 26,003 | 15,369 / 27,128 | 11,708 / 0 |
| U01 $utf16 / $lit / $int / $float wrappers | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 6 / 0 |
| U02 escaped surrogates (bytes) / decoded surrogates | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| U03 U+2028/2029/0085 strings | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| U04 C0/C1 strings / NUL / CR / ESC sequences | 0 / 0 / 0 / 0 | 12 / 0 / 3 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 5 / 0 / 7 / 0 | 0 / 0 / 0 / 0 |
| U05 bidi / zero-width / tags / variation sel. / PUA / U+FFFD / mojibake | 0 / 0 / 0 / 12 / 0 / 0 / 0 | 0 / 0 / 0 / 5 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 / 0 / 0 | 0 / 1 / 0 / 12 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 / 0 / 0 | 0 / 1 / 0 / 519 / 0 / 0 / 3 | 0 / 0 / 0 / 260 / 0 / 0 / 0 |
| U06 literal escapes / double / wholly escaped / escaped surrogate text / YAML-only | 14756 / 1219 / 10007 / 0 / 4206 | 18371 / 2196 / 8287 / 0 / 9348 | 29939 / 1694 / 15279 / 0 / 10078 | 16 / 0 / 11 / 0 / 0 | 2786 / 41 / 1590 / 0 / 1155 | 13244 / 570 / 8281 / 0 / 4102 | 13647 / 199 / 7111 / 0 / 6160 | 1492 / 6 / 609 / 0 / 64 |
| U06 ESC as text | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| U07 damaged / intact Windows paths | 0 / 0 | 0 / 16 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 110 |
| U08 JSON-like strings: json / repr / yaml / unparsed | 95002 / 13871 / 52 / 74 | 255562 / 19293 / 528 / 91 | 177930 / 31611 / 12 / 0 | 1786 / 450 / 0 / 0 | 14767 / 2386 / 3 / 0 | 88767 / 17894 / 8 / 0 | 86517 / 12854 / 507 / 20 | 20484 / 1583 / 0 / 0 |
| U09 repr heads / object reprs / constructor calls / bytes literals | 12440 / 0 / 0 / 0 | 15116 / 127 / 2 / 0 | 31478 / 0 / 1 / 2 | 450 / 0 / 0 / 0 | 2385 / 0 / 0 / 0 | 17807 / 0 / 1 / 0 | 12803 / 0 / 12 / 7 | 935 / 0 / 0 / 0 |
| U10 <U+XXXX> / entities / render markup (all strings) | 0 / 12 / 36 | 0 / 0 / 0 | 0 / 1 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 1 / 0 | 0 / 3 / 5 | 0 / 108 / 54 |
| U10 same, PROV strings only | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 1 / 1 | 0 / 0 / 1 |
| U11 id-like strings ending in LF | 0 | 15 | 1 | 0 | 0 | 0 | 0 | 0 |
| U11 PROV keys with unusual chars / DOT keywords | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| U12 pointer tokens: non-ASCII digit / leading zero / non-ASCII | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| U12 pointer strings checked | 14,600,355 | 41,567,862 | 25,183,984 | 240,019 | 2,154,568 | 11,807,052 | 11,757,548 | 732,914 |
| U13 names: non-ASCII / not NFC / mixed script / ws-or-control | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 2 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| U14 absolute-path-like strings / secret-shaped strings | 27 / 233 | 2956 / 376 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 18 / 0 | 4408 / 0 |

Corpus-level files (`exam2_corpusfiles.py`, `corpusfiles.json`): every JSONL file (`executions.jsonl`, `register.jsonl`, `validation/results.jsonl`, `raw/origins.jsonl`, `raw/members.jsonl`; 0.64 million lines) parses strictly and is JCS line by line (0 mismatches); `corpus.json`, `derivation.json` and `validation/summary.json` re-serialise byte-identically under their declared rule (H.1.4(2): sorted keys, 2-space indent, `ensure_ascii=False`), hold no float and no non-ASCII key (so the code-point `sort_keys` of `corpus/writer.py:377` coincides with UTF-16 order); 0 lone surrogates; 0 absolute-path strings.

X06, JSON Schema (`x06-schema-<corpus>.json`): all **4,461,513 AER records** of the eight corpora validate against `aer-0.1.schema.json` with `jsonschema` 4.26.0 `Draft202012Validator` (census; 0 records with an error). The published schema and the project's typed validator agree on every record.

**Result: nothing is malformed.** In 126,351 executions — 4.46 million AER records, 5.21 million SEM records, 126,351
PROV documents, about 34 GB — the independent strict parser rejects nothing (no duplicate key, no `NaN`/`Infinity`, no
overflowing float, no integer beyond I-JSON outside the six `$int` wrappers of AgentHarm, no lone surrogate, no BOM, no
trailing data), the second JCS implementation reproduces every line and document byte for byte, no JSONL file has a CR,
a blank line or a missing final LF, and no line holds a raw U+2028/U+2029/U+0085 that a text-mode `splitlines()` would
split on. No object anywhere has keys whose UTF-16 and code-point orders differ, so the A2 C1 hazard (Python
`sort_keys` vs JCS) is latent, not live; no integral float survives in any tree (integral floats are carried by
`ext.lex.flt`, 42,990 pointers, as C.11.4 specifies), so the `1.0`/`1` collision of A2 cannot occur in these corpora.

---

## 4. String content (U01–U14) and AER semantics (A01–A05)

### 4.1 Census

The string screens of §3.1's table (rows U01–U14) are counts of *strings* with at least one hit. Every hit was located by
normalised pointer (`scan-<corpus>.json`, `hits` and `hit_exemplars`); the attribution below follows A1 §7.1.

- **U01/U02 (F-01 population): zero.** No `$utf16` wrapper, no escaped or decoded lone surrogate, in any AER, SEM or PROV
  file of any corpus; no degenerate execution in any corpus (index, register), and in the raw stores (upstream data) no JSON object decodes to a lone surrogate (strict stdlib parse of 135,821 raw JSON objects; paired `\uD8xx\uDCxx` escapes, which decode to valid astral characters, occur in 1,143 objects: adprov-v1 1,007, survey 122, 2024-06 6, head 4, ROPE 3, AgentDyn 1). The defect F-01 (a
  lone surrogate in a string-typed AER position turns the execution into a degenerate `adapter_defect` AER) is
  therefore **latent**: it would lose an execution, but no current source triggers it.
- **U03, ESC sequences, bidi, tag characters, PUA, U+FFFD: zero** in all corpora. The one zero-width character of the
  first analysis (survey) is reproduced, plus one in adprov-v1 (model text).
- **U04 control characters: 6 distinct model-written argument values** (AgentDyn 4, adprov-v1 2; 17 string
  occurrences with their tool-execution and PROV copies), and CR in 10 strings of model text and arguments. The
  judged sample (6 of 6) shows a recurring corruption: U+0019, U+0002, U+0001 where the text needs U+2019 (right
  quote), U+2002/U+2001 (spaces) — the high byte of a U+20xx character was dropped before the log was written — and
  in adprov-v1 the mojibake `â€œ…â€` of a double-encoded quotation mark. Faithfully kept (a).
- **U05 variation selectors**: emoji in model text and arguments (adprov-v1 519 strings, mostly deepseek-chat 365
  executions and glm-4.6 66; AgentHarm 260; ROPE 12; AgentDyn 5; survey 12). (a), no effect beyond display.
- **U06 literal escapes in decoded text** are common and almost all expected: Python-repr tool outputs (AgentDojo
  tools return `repr`-like text with `\n` escapes; 12,000–31,000 tool texts per AgentDojo-family corpus parse as a
  Python literal, U08), JSON-in-string attributes (`apv:args`, `apv:profileOptions`, `apv:paramsTransmitted`, which
  are JSON texts by design), and AutoDojo's YAML-escaped fixture payloads (ROPE: 3,824 wholly escaped payloads, the
  B1 population). **One class is a model artefact: tool-call arguments written with literal `\n` instead of line
  breaks** (wholly escaped argument strings): head 436 executions (Gemini-1.5-pro-002 89 of 753, pro-001 68, flash-001
  28, 2.0-flash-exp 39, Meta-SecAlign-70B 97 of 5,958, Llama-3.3-70B 78 of 5,807, gpt-4o 17 of 9,911), 2024-06 117,
  adprov-v1 104 (gpt-5-nano 41, llama-3.3 43, qwen-2.5 14), AgentDyn 25, survey 18 (qwen3:14b), ROPE 12, AgentHarm 2. Judged
  sample 20 of 20 genuine double escaping (file contents, e-mail bodies, web posts; some copy YAML's `''` doubling or
  the YAML-escaped channel name of an injection), Wilson 95 % lower bound 0.84. The environment receives the literal
  backslash sequence, so these runs write malformed content; utility checks that compare text can pass or fail on it
  (new artefact N2, §10).
- **U07 Windows paths: no damaged path anywhere** (`[A-Z]:` followed by a control or separator character: 0); intact
  paths 16 (AgentDyn) and 110 (AgentHarm). The YAML/Python unescape damage A4 warns about does not occur in stored
  text.
- **U08 JSON-like strings that fail every reading: 185**, all model output: AgentDyn 91 (tool-call argument values that
  are truncated or invalid JSON/Python lists, 1 truncated), ROPE 74 (72 AutoDojo payloads that look like JSON but are
  YAML-escaped, 2 tool texts), adprov-v1 20 (argument values). Argument values that are *strings holding a list*
  (`"['a', 'b']"` where the tool expects a list): adprov-v1 235, AgentDyn 110 + 2, ROPE 13 — a model type error kept
  verbatim (a).
- **U09 Python-repr residues**: repr heads are the tool-output format (above); object reprs `<… object at 0x…>` in 13
  AgentDyn tool-call argument values (127 occurrences with their copies; a model passing an object repr as a value), `datetime(`/`Decimal(` calls 16,
  `b'…'` 9, all in model text. (a).
- **U10 render exposure in PROV literals** (A4 F-02 population: what `render --show-content` would put into a DOT label):
  HTML entities 1 (adprov-v1), markdown/HTML markup 2 (adprov-v1, AgentHarm), `<U+XXXX>` look-alikes 0. F-02 stays a
  latent rendering defect with a population of three literals.
- **U11 identifiers**: no PROV key or QName value outside `[A-Za-z0-9_.:-]`, none ending in `.` (P10), no DOT keyword;
  the 16 id-like strings ending in LF are model answers (AgentDyn 15, head 1), not identifiers.
- **U12 pointer tokens (A4 F-04 population): zero** non-ASCII-digit tokens, zero leading-zero index tokens and zero
  non-ASCII tokens in 108 million pointer strings (PROV `apv:sourcePointer`/`apv:rulePointer`, AER `unk`/`evf` keys,
  `src[].p`, `ext.lex`, SEM premises and `at`). F-04 is a validator robustness gap with no population.
- **U13 names**: no non-ASCII, non-NFC or mixed-script model id, tool name, task facet or actor name; 2 tool names with
  whitespace (the AgentDyn sentence-as-function-name of first analysis row 20).
- **U14 paths and secrets**: no machine-specific string (the importing account's home directory, the corpus home,
  temporary directories, worktree paths) in any AER, SEM, PROV, index, register, manifest, origins or validation file
  of any corpus (`u14-machine-paths.json`; raw objects excluded as upstream data). The `/Users/…` and `/home/…` paths
  found (AgentDyn 2,956 strings, AgentHarm 4,408, ROPE 27, adprov-v1 18) are benchmark content (fictional
  `/home/emma…`, `/Users/user/…` in tasks, arguments and tool outputs). Secret-shaped strings (ROPE 233, AgentDyn 376)
  are benchmark fixtures (fake keys in the github/dailylife suites) and model copies of them. No real credential was
  identified; none is printed here.

### 4.2 AER semantics

- **A01 tool-call arguments**: every structured call has an object argument (`args_type` dict for all 581,326 calls);
  no `$lit`/`$utf16` argument; 11 tool names that are not identifiers (head 5, survey 2, adprov-v1 2, 2024-06 1,
  AgentDyn 1). Key-set drift is optional parameters (e.g. `search_product` 93 key sets in AgentDyn, all subsets of the
  tool's schema) and type unions are optional parameters given `null` or a model's string-for-list/int-for-string
  substitution (`scan-<corpus>.json` `tools`). `args_raw` is never present (TraceLogger and transcript/v1 do not keep it).
- **A02 finish reasons** are recorded only by adprov-v1 (`tool_calls` 39,841, `stop` 14,597, `error` 3, `length` 1;
  `not_recorded` 12,700, `ambiguous` 145) and AgentHarm (`tool_calls` 2,658, `stop` 2,580, `max_tokens` 23). The 23
  `max_tokens` stops are not classified by the safety net (catalogue gap, finding b5); the TraceLogger corpora do not
  record finish reasons (`not_recorded` everywhere), so truncation cannot be detected there except through its effects.
- **A03 empty assistant turns without any tool call**: AgentDyn 4,632 turns in 4,631 executions (738 executions in which
  every assistant turn is empty), head 343, ROPE 33, survey 84, 2024-06 48, adprov-v1 1, AgentHarm and Mandate 0. These
  are the empty completions of C5 (llama-3.3, qwen3, gemini-2.5 endpoints) and extend first-analysis row 13 (empty text
  *beside* calls) to empty turns. The final answer is empty in all but one of them: a utility check on the final answer
  necessarily fails (new artefact N4).
- **A04 degenerate executions: 0** in all corpora (`corpusfiles.json`, index and register). Source-side population:
  the 135,821 raw JSON objects parse strictly (no duplicate key, no `NaN`/`Infinity`, no overflowing float, no BOM, valid UTF-8); 10 integers beyond I-JSON in AgentHarm raw objects (the source of the six `$int` wrappers); no lone surrogate. Nothing in the sources would trigger F-01 today.
- **A05 payload forms vs SEM markers** (every marker on every attacked execution; `scan-<corpus>.json` `a05|…`):

| Markers (unit: marker) | rope | agentdyn | head | mandate | survey | 2024-06 | adprov-v1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| present, payload verbatim or in an escaped spelling in the text | 2,483 | 805 | 8,545 | 0 | 0 | 2,684 | 9,405 |
| present, whitespace-collapsed match | 15,214 | 46,693 | 21,257 | 250 | 2,345 | 7,511 | 11,728 |
| present, in the YAML-parsed strings | 7,506 | 7,611 | 40,333 | 111 | 3,026 | 23,572 | 14,047 |
| present, only in an unescape/repr/`''`-undoubling reading of SEM | 3,991 | 14,553 | 3,445 | 0 | 262 | 2,656 | 492 |
| absent | 154,702 | 372,088 | 171,375 | 935 | 12,735 | 91,517 | 83,933 |
| ambiguous | 3,802 | 569 | 0 | 0 | 0 | 0 | 0 |
| not present, but the payload with the AutoDojo escape undone is in the text (B1) | 1,850 | 0 | 0 | 0 | 0 | 0 | 0 |
| executions with such a miss | 1,245 | 0 | 0 | 0 | 0 | 0 | 0 |

  Where SEM says `present` but no literal, whitespace-collapsed or YAML-decoded reading of the scanner finds the payload,
  the deciding reading was recomputed (`exam2_markers2.py`, `a05-attribution-<corpus>.json`): every such marker is found by one of SEM's own readings — one-level unescape with or without the Python-repr reading (AgentDyn 12,501, head 3,021, 2024-06 2,232, ROPE 3,991, adprov-v1 492, survey 262), two-level unescape, or the `''` un-doubling of YAML single-quoted scalars (AgentDyn 2,052, head 424, 2024-06 424) — never by none (`a05-attribution-<corpus>.json`). The judged sample (17 markers from survey, AgentDyn, ROPE and head) is 17 of 17 true presence: tool outputs that are Python reprs (payload newlines written `\n`), reprs of reprs (`\\n`, the AgentDyn github suite) and YAML single-quoted bodies (apostrophes doubled). No over-matching of the F-10 kind was seen (Wilson 95 % lower bound on precision 0.82); the normaliser's breadth is justified by the tool-output formats.
  In the other direction, no marker in any corpus is `absent`/`ambiguous` while the payload occurs verbatim or whitespace-collapsed in the text; the only misses are payloads visible after AutoDojo's YAML escape is undone (`exam2_b1check.py`): ROPE 1,850 markers in 1,245 executions: **the AutoDojo arm 1,840 markers in 1,235 executions** (exact whole-payload census; the first analysis' 40-character windows gave 1,166), and 10 `ambiguous` markers in 10 long-horizon executions whose fixtures are not AutoDojo-linked. All other corpora: 0. The B1 fix (FA §9.2) should be sized on 1,235, and its gate on the AutoDojo link would leave the 10 long-horizon markers (decide whether to include them).

---

## 5. PROV checks (P01–P11) and graph metrics

| PROV check | rope | agentdyn | head | mandate | survey | 2024-06 | adprov-v1 | agentharm |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| P01 views checked | 219,513 | 690,158 | 422,249 | 3,928 | 56,599 | 204,804 | 174,641 | 5,280 |
| P01 strict-order cycles (C42) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P01 non-strict event cycles (simultaneity) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P02 dependency / informed / derivation / specialization cycles | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| P03 wasDerivedFrom / C51 violations | 629,665 / 0 | 1,870,105 / 0 | 1,048,811 / 0 | 10,911 / 0 | 150,339 / 0 | 507,120 / 0 | 417,939 / 0 | 18,954 / 0 |
| P04 C26 duplicate starts / C24 duplicate generations | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| P05 multi-generator entities explicit / after Inf. 9-11 expansion | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| P05 trigger generator = starter / implied only / differs | 69,952 / 0 / 0 | 208,327 / 0 / 0 | 136,559 / 0 / 0 | 1,150 / 0 / 0 | 11,237 / 0 / 0 | 68,641 / 0 / 0 | 64,781 / 0 / 0 | 0 / 0 / 0 |
| P05 attribution supported / generator implied only / generator not associated | 0 / 45,311 / 0 | 0 / 195,122 / 0 | 0 / 158,414 / 0 | 0 / 1,188 / 0 | 0 / 11,304 / 0 | 0 / 67,365 / 0 | 0 / 62,316 / 0 | 0 / 2,112 / 0 |
| P05 delegation: delegate explicit & responsible implied / both explicit / no activity | 69,952 / 0 / 10,791 | 210,304 / 0 / 38,281 | 136,559 / 0 / 36,679 | 1,150 / 0 / 396 | 11,237 / 0 / 3,243 | 68,641 / 0 / 18,241 | 64,781 / 0 / 17,664 | 0 / 0 / 0 |
| P06 unresolved in container+core+top: resolved elsewhere / nowhere | 3,228,377 / 0 | 9,194,786 / 0 | 48,485 / 0 | 0 / 0 | 355,026 / 0 | 21,988 / 0 | 0 / 0 | 0 / 0 |
| P06 generation/usage ids unresolved | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P08 mentionOf (assess / inf) | 397,907 / 199,914 | 1,119,837 / 557,051 | 852,619 / 39,570 | 8,152 / 396 | 69,040 / 31,344 | 408,527 / 21,148 | 385,477 / 17,664 | 10,424 / 0 |
| P08 general not in named bundle / specific undeclared / bundle missing | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| P10 trailing '.' (keys / QName values) / prefix IRI not '#'|'/' | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| P11 multi-valued statement keys | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P09 components core p50 / max | 43 / 159 | 34 / 241 | 22 / 118 | 21 / 47 | 27 / 134 | 22 / 118 | 19 / 73 | 30 / 50 |
| P09 components core+inf p50 / max | 28 / 85 | 23 / 158 | 20 / 103 | 20 / 48 | 17 / 71 | 20 / 103 | 17 / 62 | 30 / 50 |
| P09 components core+inf+attr p50 / min-max | 4 / 3-8 | 4 / 3-9 | 4 / 3-7 | 4 / 3-6 | 4 / 3-5 | 4 / 3-7 | 5 / 4-6 | 7 / 6-7 |
| P09 apv:Gap share of core+inf entities | 0.257 | 0.250 | 0.315 | 0.321 | 0.258 | 0.325 | 0.265 | 0.156 |
| P09 core activities with startTime | 0 / 42,410 | 0 / 148,348 | 0 / 436,118 | 0 / 4,568 | 0 / 12,555 | 0 / 211,986 | 82,444 / 202,263 | 24,149 / 24,149 |
| P09 inference activities with startTime | 0 / 165,677 | 0 / 471,573 | 0 / 2,891 | 0 / 0 | 0 / 24,836 | 0 / 2,907 | 0 / 0 | 0 / 0 |
| P09 relations with prov:time | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P09 shared top-level keys / with variants (within corpus) | 10,803 / 0 | 38,288 / 0 | 36,685 / 0 | 404 / 0 | 3,250 / 0 | 18,247 / 0 | 17,671 / 0 | 1,068 / 0 |

| Orphan class in core ∪ inference (zero relation degree) | rope | agentdyn | head | mandate | survey | 2024-06 | adprov-v1 | agentharm |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| apv:Gap | 251,253/251,253 | 723,151/723,151 | 554,721/554,721 | 5,552/5,552 | 43,877/43,877 | 275,442/275,442 | 190,353/190,353 | 9,992/9,992 |
| apv:MessagePart | 21,578/263,127 | 114,795/763,203 | 102,944/534,438 | 792/5,193 | 6,486/42,608 | 39,699/250,709 | 35,328/229,835 | 3,710/21,166 |
| apv:CaptureProfile | 10,791/10,791 | 38,281/38,281 | 36,679/36,679 | 396/396 | 3,243/3,243 | 18,241/18,241 | 17,664/17,664 | 1,056/1,056 |
| apv:Defence | 4,594/10,791 | 11,809/31,510 | 1,486/8,859 | 51/216 | – | 901/3,052 | – | – |
| apv:Harness | – | – | – | – | – | – | 17,664/17,664 | 1,056/1,056 |
| apv:ToolRuntime | 287/10,791 | 6,008/38,281 | 3,072/36,679 | 5/396 | 342/3,243 | 970/18,241 | 1,417/17,664 | 0/766 |
| apv:Step | – | – | – | – | – | – | – | 7,946/8,388 |
| apv:Model | 2/10,791 | 11/38,281 | 232/36,679 | 0/396 | 0/3,243 | 233/18,241 | 0/17,664 | 2,068/7,329 |
| apv:ExecutionDescription | 0/10,791 | 0/38,281 | 0/36,679 | 0/396 | 0/3,243 | 0/18,241 | 0/17,664 | 1,056/1,056 |
| apv:Run | 0/10,791 | 0/38,281 | 0/36,679 | 0/396 | 0/3,243 | 0/18,241 | 0/17,664 | 1,056/1,056 |
| apv:ModelService | – | 11/38,281 | – | – | – | – | – | 0/2,068 |
| apv:Benchmark | 2/10,791 | 3/38,281 | 0/36,679 | 0/396 | 0/3,243 | 0/18,241 | 0/17,664 | 0/1,056 |

| Degree in core ∪ inference, p50 / p95 / max | rope | agentdyn | head | mandate | survey | 2024-06 | adprov-v1 | agentharm |
|---|---|---|---|---|---|---|---|---|
| apv:ModelInvocation | 31 / 62 / 150 | 30 / 65 / 272 | 21 / 54 / 171 | 19 / 30 / 104 | 20 / 49 / 139 | 20 / 44 / 171 | 19 / 44 / 493 | 17 / 36 / 47 |
| apv:ToolExecution | 12 / 20 / 23 | 11 / 20 / 23 | 10 / 17 / 23 | 10 / 13 / 15 | 10 / 17 / 23 | 10 / 15 / 23 | 10 / 15 / 23 | 7 / 11 / 13 |
| apv:Message | 7 / 15 / 18 | 6 / 15 / 19 | 4 / 11 / 18 | 4 / 7 / 9 | 5 / 11 / 18 | 4 / 9 / 18 | 3 / 8 / 17 | 2 / 7 / 9 |
| apv:MessagePart | 1 / 6 / 6 | 1 / 6 / 6 | 1 / 6 / 6 | 1 / 6 / 6 | 1 / 6 / 6 | 1 / 6 / 6 | 1 / 6 / 6 | 1 / 3 / 3 |
| apv:AgentSystem | 16 / 32 / 73 | 12 / 34 / 98 | 10 / 22 / 76 | 10 / 15 / 39 | 9 / 22 / 64 | 10 / 21 / 76 | 8 / 22 / 172 | 8 / 14 / 14 |
| apv:ToolRuntime | 18 / 42 / 162 | 12 / 45 / 267 | 9 / 30 / 171 | 9 / 18 / 90 | 9 / 30 / 135 | 9 / 30 / 171 | 9 / 33 / 492 | 5 / 10 / 16 |
| apv:Fixture | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 6 / 9 |
| apv:Outcome | 1 / 2 / 2 | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 2 | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 1 |

- **P01 event ordering without times.** The event graph (generation, usage, start and end events of every entity and
  activity; edges of the PROV-CONSTRAINTS ordering rules present in the view, Inferences 9 and 11 included; Constraint 42
  strict) was built for 1.78 million views (each container, the core ∪ all inference bundles view, the core ∪ assessment
  view). **No strict-order cycle and no non-strict cycle** exists in any view: every document is valid under the
  event-ordering constraints. The statement in `validate/constraints.py:17` that these constraints "are not
  instantiable" without times is incorrect (A3 PI-04): they are instantiable and the corpora satisfy them; the
  validator simply does not check them (finding b1).
- **P02**: no used/generated dependency cycle, no `wasInformedBy` cycle, no `wasDerivedFrom` cycle and no
  `specializationOf`/`mentionOf` cycle in any view (4.65 million `wasDerivedFrom` statements, mostly the top-level
  `aprov.t_map`/`t_derive`/`t_annotate` derivations).
- **P03 C51: 0**; **P04 C26 and C24: 0**; **P11: 0**; **P10: 0** (no trailing `.`, every namespace IRI ends in `#` or `/`).
- **P05 normal form.** No entity has two generating activities, neither explicitly nor after expanding Inferences 9
  (start trigger generated by the starter) and 11 (derivation with activity). Every `wasStartedBy` trigger's explicit
  generator is its starter (560,647 starts). Every `wasAttributedTo` (543,132) has **no** explicit generator, so its
  Inference-13 generating activity is existential only; none conflicts with an explicit generator. Every
  `actedOnBehalfOf` with an activity (562,624, `aprov.assoc_tool`) has the delegate's association explicit and the
  responsible agent's association implied only (Inference 14), as EF E.1.4 intends; the 125,295 delegations without an
  activity are `aprov.deleg_user`. Nothing to fix; the implied associations should be stated in the datasheet for
  consumers that do not apply PROV inferences (A3 PI-12).
- **P06 dangling references: 0 unresolved anywhere.** Arguments of inference bundles that are declared not in the core
  but in another inference bundle (ROPE 3.2 M, AgentDyn 9.2 M, survey 355 k, head 48 k, 2024-06 22 k: the I-class
  twins declare model calls and tool executions in inference bundles) were re-resolved in their application view
  (core ∪ bundle ∪ inference bundles of proper method subsets, EF E.1.6 item 1; `p06-view-<corpus>.json`): **0 unresolved** among 36.5 million node arguments of inference bundles in ROPE, AgentDyn, head, 2024-06 and survey (the other three corpora had none outside container ∪ core); the method set read from every inference bundle IRI equals the bundle entity's `apv:method` in all 1,057,148 bundles. The I-class profiles are well-formed provenance only in the application view; a consumer loading one inference bundle with the core alone sees dangling references (first analysis C4, decided: datasheet statement).
- **P07 cross-document consistency.** Within each corpus every shared top-level statement (`raw:`, `sw:`, `rules:`) is
  byte-identical (JCS) in every document that carries it (126,416 keys, 0 variants). Across the eight corpora the
  `sw:` and `rules:` statements agree (one catalogue digest per catalogue version). The only variants are **14,182
  `raw:` entities shared by agentdojo-2024-06 and agentdojo-head**, which differ in `apv:originRevision` (same bytes,
  imported from two upstream commits). Merging the two corpora into one RDF dataset would give these entities two
  revisions (C22/C23 merge: multi-valued, not invalid). See §7.3 for the execution-level consequence.
- **P08 mentionOf**: 4.12 million `mentionOf` statements (assessment 3.25 M, inference 0.87 M), every general entity
  declared in the named bundle, every specific entity declared in the mentioning bundle. PROV-LINKS gives `mentionOf` no
  PROV-JSON form and is a Note (A3 PI-17): consumers other than `prov` may drop it; core bundles never use it.
- **P09 graph metrics.** (i) *Components*: in the core alone the I-class corpora fall apart (ROPE p50 43 components,
  AgentDyn 34, survey 27, against 19–22 for the D-class corpora); with inference bundles 17–30; with the attribute links
  `apv:partOf`/`apv:about` 3–9 (p50 4, AgentHarm 7). (ii) *Orphans* in core ∪ inference: all `apv:Gap` entities (25–33 %
  of entities; 16 % in AgentHarm) and all capture profiles, by design (attribute-linked); system/first-user message parts
  (linked by `apv:partOf` only); defences that made no decision; tool runtimes in runs without a tool call; and, in
  AgentHarm only, **the run activity (1,056/1,056), the execution description, the harness agent and 7,946 of 8,388
  Inspect step activities**, plus 2,068 model entities (finding b3, question c3). (iii) *Degree*: model invocations are
  the hubs of the I-class graphs (p95 62–65 in ROPE/AgentDyn vs 44–54 elsewhere) because the context usages and the
  Inference-6 closure sit with them; the largest degrees (493 in adprov-v1, 272 in AgentDyn) are long runs, not
  mapping artefacts. Fixtures have degree 1 (their `wasAttributedTo`) everywhere except AgentHarm, where the task prompt
  fixture is used by the model calls (p95 6). (iv) *Time coverage*: no relation carries `prov:time` anywhere;
  activities carry `prov:startTime`/`prov:endTime` only in adprov-v1 (82,444 of 202,263 core activities: the
  transcript/v1 timed calls and tool executions) and AgentHarm (24,149 of 24,149). The first analysis' "no PROV time
  exists" holds for its five corpora only.

---

## 6. Determinism (D01, D02)

Sample: 1,305 executions (stratified as pre-registered: 150–179 per corpus, every stratum at least 10; ids in
`d01-sample.json`), and 400 for re-mapping of which the 50 AgentHarm units were skipped because Inspect `.eval` units
come from a container plan the tool does not replay (analysis limitation, not a finding). Results
(`d01-d02-determinism.json`):

| Configuration | TZ | locale | PYTHONHASHSEED | UTF-8 mode | workers | SEM equal | PROV equal | tiers 3–4 statuses equal |
|---|---|---|---|---|---:|---:|---:|---:|
| c0 | UTC | C.UTF-8 | 0 | 1 | 1 | 1,305 / 1,305 | 1,305 / 1,305 | — |
| c1 | Pacific/Auckland | en_US.UTF-8 | 1 | 1 | 1 | 1,305 | 1,305 | — |
| c2 | America/St_Johns | tr_TR.UTF-8 | random | 0 | 1 | 1,305 | 1,305 | — |
| c3 | Asia/Kolkata | de_DE.UTF-8 | 12345 | 0 | 1 | 1,305 | 1,305 | — |
| c4 | Europe/London | C | random | 1 | 1 | 1,305 | 1,305 | — |
| c5 | Australia/Eucla | en_US.UTF-8 | random | 1 | 4 | 1,305 | 1,305 | 1,305 / 1,305 |
| D02 AER re-map from raw | UTC | C.UTF-8 | 0 | 1 | 1 | AER equal 350 / 350 | | |

Zero differences in 7,830 re-derivations and 350 re-mappings. One-sided 95 % Clopper-Pearson upper bound on the
per-execution non-determinism rate: 0.23 % per configuration (n = 1,305), 0.85 % for re-mapping (n = 350). The
re-derived tier-3/4 check statuses equal the stored validation rows in all 1,305. (A first summary reported 4
"differing" executions: those ids are in both agentdojo corpora (§7.3) and were keyed by id alone — an analysis
artefact, corrected.)

---

## 7. The three corpora not covered by the first analysis

### 7.1 First-analysis checks (R01–R07)

`reuse-summary-new-corpora.json` (extractor + aggregator, all executions), `reuse-register-new-corpora.json`,
`r05-dups-utility-new-corpora.json`, `p9diff-<corpus>.json`.

| | agentdojo 2024-06 | adprov-v1 release | survey AgentHarm |
|---|---|---|---|
| executions | 18,241 (18,034 agent executions + 207 outcome-only) | 17,664 (6 models × 2,944) | 1,056 (3 models × 352; harmful 528, benign 528) |
| integrity chain (raw re-hash, AER/SEM/PROV/validation digests, strict parse) | 0 errors | 0 | 0 |
| validation failed / warnings | 0 / 0 | 0 / 0 | 0 / 0 |
| register (duplicate rid, index ↔ register, counts) | consistent | consistent | consistent |
| status ok / ok_with_issues / failed | 17,747 / 494 / 0 | 17,584 / 80 / 0 | 1,052 / 4 / 0 |
| verified_complete / known_incomplete / unverifiable | 232 / 51 / 17,958 | 14,688 / 32 / 2,944 | 1,056 / 0 / 0 |
| AER ↔ PROV cross-checks (FA §4.2) | 0 violations | 0 | see 7.2 (analysis artefacts) |
| statements that must never appear (FA §4.3) | 0 (2,154 inference `wasDerivedFrom` = PI redactions; 59,716 core `wasInformedBy` = D `aprov.comm`) | 0 (64,781 core `wasInformedBy`, D) | 0 (4,170 core `wasDerivedFrom` = state patches, D; 21,372 core `wasInformedBy`, D) |
| identical-trajectory groups | 150 groups / 816 executions (3 cross-model: the gemini-1.5 flash/pro pairs of C5) | 112 / 431 | 0 |
| utility differs inside a group (same user task) | 0 | 0 | — |
| p9 → p10 (AER / SEM / PROV) | AER: the history fields (`introduced_in_commit`, `benchmark_era`, `committed_no_later_than`) and the profile digest, all 18,241; PROV: the `rules:agentdojo.1` digest and derivation keys only | AER and SEM identical; PROV: only the `rules:agentdojo.1` digest | byte-identical to the phase-8 copy |
| AER fidelity vs raw (FA §5 tool, TraceLogger only) | 18,241 executions, **0 mismatches** | n/a (transcript/v1) | n/a (Inspect) |

The p9→p10 differences are exactly those AGENTS.md predicts for the re-derivation; nothing else changed.

### 7.2 Notes and analysis artefacts

- The first-analysis extractor's AgentHarm cross-checks report `model_call_used_ne_input` 1,601,
  `mc_input_nonmonotone` 1,012 and `message_without_generation_or_attribution` 3,710. The first two are **analysis
  artefacts (d)**: the extractor recognises only `m<n>` ids as messages, and the Inspect judge's prompt and output are
  `p<n>`/`o<n>` (checked: judge call `mc6` `used` exactly its AER input `p0`); the judge call's one-message input after
  a long agent call is not a monotonicity violation. The third is real and is a source property: Inspect does not record
  who authored the system and user messages (`unk /actor not_recorded`), so no attribution is asserted (question c4).
- The safety net leaves `adprov.*` `sentinel_time#unknown_lost` (121, adprov-v1) and `abnormal_finish#max_tokens` (23)
  and `text_encoded_call#marker` (12) (AgentHarm) unclassified (finding b5).
- AgentHarm: 4 executions carry a declared lost tool result (`missing_tool_result`, with `dangling_source_ref`, all
  also at the sample limit) and are indexed `verified_complete` (finding b2).
- R07 (`r07-rule-classes-new-corpora.json`, generalised to every family catalogue): the new corpora cite 20 (2024-06), 18 (adprov-v1) and 11 (AgentHarm) class-D rules. As in the first analysis (C6), AgentDojo D rules verified only at `c2748856` are cited for logs produced by other code (adprov-v1 cites five; 2024-06's logs predate it). New: nine cited D rules list **no code at all** (evidence is a document): `adprov.assistant_turn_one_call` (17,664 executions), `call_id_unique_match` (16,247), `tool_turn_is_one_execution` (16,247), `finish_reason_positional` (14,720), `single_attempt_from_call_count` (14,567), `lost_calls_from_count` (121), `agentdojo.functions_runtime`, `committed_no_later_than`, `empty_assistant_text_ambiguous` (question c6). Every cited rule exists in a shipped catalogue.
- adprov-v1: all 2,944 deepseek-chat executions are `unverifiable` because their transcripts carry no usage counts
  (`usage_absent`), the other five models reconcile (`verified_complete` 14,688, `known_incomplete` 32 where the
  reported call count exceeds the trajectory). The completeness label is therefore model-confounded (artefact N6).

### 7.3 Cross-corpus overlap (Q-045)

`q045-overlap.json`, `q045-pairdiff-2024-06-vs-head.json`. **14,182 executions occur in both agentdojo-2024-06 and
agentdojo-head** (same raw bytes, same execution id; 78 % of 2024-06, 39 % of head). No other pair of corpora shares a
raw object or an id. In a 200-execution seeded sample the two AER files differ only in the origin commit (and hence the
seal digest), the SEM only in `aer_digest` and the seal, the PROV only in `apv:originRevision` and the derivation keys.
Consequences: pooled statistics over the two corpora double-count 14,182 executions unless deduplicated by `ex` (or raw
sha256); and the per-execution IRIs (`x:` namespace `…/exec/<ex>#`) of two different documents coincide, so a merged
RDF dataset would merge their nodes (question c2).

---

## 8. S01: AgentDyn gemini-2.5-flash, piguard vs prompt_guard_2 (C5 item 9)

Data: `phase10-examination-2-data/s01-*.json` (tools `exam2_piguard.py`, `exam2_piguard2.py`, `exam2_piguard3.py`,
`exam2_piguard4.py`). Unit: matched cell = (suite, user task, attack, injection task), 648 cells per arm. "Identical" =
message lists equal with provider call ids dropped (roles, text, tool-call names and arguments, tool results, errors).

### 8.1 What is identical, and what is not

| Pair (gemini-2.5-flash) | identical cells | timestamps equal | durations equal | raw object / git blob equal | both arms without a defence decision | both arms with the same redactions |
|---|---:|---:|---:|---:|---:|---:|
| piguard / prompt_guard_2 | 425 / 648 | 2 | 0 | 0 / 0 | 251 | 174 (126 with one, 48 with two) |
| piguard / transformers_pi | 357 / 648 | 2 | 0 | 0 / 0 | 143 | 214 |
| prompt_guard_2 / transformers_pi | 275 / 648 | 0 | 0 | 0 / 0 | 148 | 127 |
| undefended / any detector | 0 / 648 | — | — | — | — | — |

Identical trajectories have 3 to 23 messages (piguard/prompt_guard_2: 119 three-message runs, 173 five-message, 133
longer). All 425 pairs share the origin commit (one pinned clone) but have different git blobs, different raw bytes
(the pipeline name differs), different durations (median ratio later/earlier run 0.98; 1.4 % below 0.5, 0.9 % above
2) and, in 423 of 425, different start timestamps; the two equal timestamps are within-second coincidences of parallel
workers (4,445 timestamps are shared by more than one run across the corpus). They are **not duplicated files**.

They are also **not a defence that never acted**: in 174 of the 425 identical pairs both detectors redacted, and they
redacted the same tool outputs (the redaction replaces the output with a constant text, so the trajectories stay
equal).

### 8.2 Divergence test: the model answered identically to identical context inside the detector arms

For every pair of arms, the first message at which the two runs differ (`s01-divergence-gemini-2.5-flash.json`):

| Pair | identical | first divergence at an assistant message after identical context (model-side) | first divergence at a tool message rewritten on one side only (defence-side) | other tool difference |
|---|---:|---:|---:|---:|
| piguard / prompt_guard_2 | 425 | 1 | 210 | 12 |
| piguard / transformers_pi | 357 | 2 | 289 | 0 |
| prompt_guard_2 / transformers_pi | 275 | 3 | 370 | 0 |
| undefended / each detector | 0 | 648 | 0 | 0 |
| undefended / repeat_user_prompt | 2 | 361 | (285 role mismatch: the defence adds a message) | — |

Inside the three PI-detector arms the model gave a different answer to identical context in at most 3 of 648 cells; every
other divergence starts where exactly one detector rewrote a tool output. Between the undefended arm and any detector arm,
the very first assistant reply differs in all 648 cells, although the recorded inputs are identical (system and first
user message digests equal in 648/648; for 81 three-message runs the reply is the whole trajectory). The other models do
not show the pattern (detector-arm identity 0–11 cells of 648, apart from llama-3.3's empty replies, 78–120).

Timing: the detector arms ran interleaved from 2026-01-24 01:19 to 20:13 (local, naive); the undefended, tool-filter,
spotlighting and repeat-prompt arms ran in one 52-minute window (04:57–05:49) of the same day.

### 8.3 Verdict

Independent executions (distinct timestamps, durations, files), produced in a generation condition in which
gemini-2.5-flash was effectively deterministic given the context, so two detector arms produce the same trajectory
exactly when the detectors take the same decisions. The undefended arm (and the other non-detector arms) of the same model
was generated under a different condition: identical recorded inputs give a different first reply in every cell.
What differs between the two conditions (decoding parameters, seed, model snapshot or serving route, a response
cache) is **not recorded** in the logs (`model_call` request, parameters and served model are `not_recorded`), so it is
undetermined. A response cache cannot be excluded: durations of identical pairs are not shorter for the later run
(median ratio 0.98), but the run time may be dominated by the local detector models.

Consequence for analyses (outcomes in `s01-session-effect-gemini-2.5-flash.json`): for this model, "detector arm minus
undefended arm" mixes the defence effect with a generation-condition effect. In the 445 cells where prompt_guard_2 made
no decision (so the detector did not change any tool output), attack success is 128 of 357 attacked cells in the detector
run against 49 in the undefended run, and utility 85 against 38 of 445. (Conditioning on "no decision" selects on the
detector run's own trajectory, so these numbers illustrate the size of the condition effect rather than estimate it.)
Comparisons among the three detector arms are, by contrast, closely paired: their differences are attributable to the
detectors' decisions.

Classification: **(a)** source-data property, disclosed (new manuscript artefact §10 row N3). No processing defect: AgentPROV
keeps the executions apart (`content_dedup = never`) and records each faithfully.

Suggested wording: "In AgentDyn, the three prompt-injection-detector arms of gemini-2.5-flash were generated under
conditions in which the model answered identical context identically (the arms diverge only where the detectors' decisions
differ; 425 of 648 cells are identical between PIGuard and PromptGuard 2, including 174 where both redacted the same tool
outputs). The undefended arm of the same model differs from every detector arm already at the first reply in all 648
cells despite identical recorded inputs. Detector-versus-undefended differences for this model therefore combine the
defence effect with an unrecorded difference in generation conditions; we report detector-arm comparisons as paired and
flag the undefended baseline."

---

## 9. Findings, classified

### 9.1 (b) Processing defects or improvements, ranked by impact (none applied)

| # | Finding | Where (file:line) | Proposed fix | Spec | Digest / corpus impact | Risk |
|---|---|---|---|---|---|---|
| b1 | **No validator check for event ordering, and a wrong claim that it is not instantiable** (A3 PI-04). P01 shows the corpora are valid, but nothing guards future output | `src/agentprov/validate/constraints.py:17` (docstring), `docs/architecture/EF_provenance.md` E.1.4 preamble and the `C47 (no times: not applicable)` cells (e.g. l. 367) | Add `pv.constraints.ordering`: per container and per application view, build the event graph (Inferences 7/8, 9, 11; the ordering rules present) and fail on an SCC containing a Constraint-42 edge; add the C51 and C26 checks (`pv.constraints.derivation_parts`, `pv.constraints.unique_start`) and cycle lints for used/generated, `wasInformedBy`, `specializationOf`∪`mentionOf`. Correct the docstring and E.1.4 | EF E.1.4, E.1.6; K.10 | New check ids enter every `validation/results.jsonl` row: **validation digests of every corpus change** (index `digests.validation`, `corpus.json`); AER/SEM/PROV unchanged. A re-validation, not a re-derivation | Low (P01–P04 found 0 in 1.78 M views; vendoring the W3C `ordering-*` test cases gives fixtures) |
| b2 | **`verified_complete` despite a declared lost tool result** (4 AgentHarm executions with `missing_tool_result`) | `src/agentprov/adapters/runner/importer.py:128` (`_LOSS_CODES` lacks `missing_tool_result`) | Add `missing_tool_result` (an adapter-declared loss: C.13 `aer.acc.executions_have_results`, D.6 row "non-final message without tool messages") to `_LOSS_CODES`; consider `dangling_source_ref` (Inspect condensed references) after checking that it always implies loss | HL H.3.2(2) ("known_incomplete iff an adapter rule proves loss") | Index rows and `corpus.json` counts only (AgentHarm 4 → `known_incomplete`); no AER/SEM/PROV digest. Applies at the next import or re-index | Very low |
| b3 | **AgentHarm run and step activities, execution description and harness are isolated** (1,056 runs, 7,946 of 8,388 Inspect steps, 1,056 harness agents with no relation) | Inspect mapper (`src/agentprov/adapters/inspect/`), scope records without `actor`; `aprov.assoc_scope` needs an actor | Give the Inspect run scope (and step scopes) the harness actor under a D rule citing Inspect's sample loop (the eval runner executes the sample and its solver steps), so `aprov.assoc_scope` emits `wasAssociatedWith(run, harness)`; or record the isolation as intended in the profile | D.6 (Inspect), EF E.1.4 `assoc_scope` | AER, SEM digests (AER changes) and PROV of the AgentHarm corpus (1,056); `inspect` catalogue digest in every Inspect PROV | Low–medium (needs the Inspect code citation; decide c3 first) |
| b4 | **`isdigit()` pointer tokens** (A4 F-04): 0 occurrences in 108 M pointers, so robustness only | `validate/linkage.py:82`, `validate/profiles.py:177`, `adapters/agentdojo/semantics/suites.py:216`, `prov/engine.py:189`, `aer/reader.py:73`, `views/transcript_v1.py:151`, `prov/rules/nodes.py:545` | One helper `index_token()` with `re.fullmatch(r"0|[1-9][0-9]*")` at the seven sites | RFC 6901; C.11 | None for current corpora (0 affected strings): derivation output unchanged; validation behaviour stricter only on hostile input | Very low |
| b5 | **Safety-net catalogue gaps for the new corpora**: AgentHarm `abnormal_finish#max_tokens` 23 and `text_encoded_call#marker` 12, adprov `sentinel_time#unknown_lost` 121 unclassified | `src/agentprov/adapters/inspect/artefacts.toml`, `src/agentprov/adapters/adprov/artefacts.toml` | Catalogue entries (B4-style; texts in §10.2) | D.15 | None (catalogue only; enters no AER/SEM/PROV/`corpus.json`) | Very low |
| b6 | **F-01, latent**: an escaped lone surrogate in a string-typed AER position still turns the execution into a degenerate AER. Population now 0 (U01/U02, A04) | `aer/_structure.py:158,516-539` vs `aer/canon.py:164-170`; fallback `adapters/runner/__init__.py:260` | As A4 F-01: accept `{"$utf16"}` wherever a string is typed (validator, JSON Schema, PROV `nodes.py:305-313` needs an `else`), with mapper/writer/validator tests | C.11.2; G rule 8 | None for current corpora (no affected execution); `aer/0.1` is frozen, so accepting a new form in typed positions needs a format decision | Medium (format freeze) |
| b7 | **DOT `&` escaping** (A4 F-02): population 3 PROV literals | `render/style.py:103-110` | Escape `&` first in `dot_quote`; test with entities | — | None (render only) | Very low |

Ranking rationale: b1 is the only gap between a W3C constraint the corpora must satisfy and what the validator checks;
b2 mislabels a completeness flag used for filtering; b3 affects one corpus' graph connectivity; b4–b7 have no affected
data today. None of them changes a number in the first analysis' §8 table.

### 9.2 (c) Questions for the user

- **c1. gemini-2.5-flash generation conditions (S01).** Should the AgentDyn datasheet flag the undefended arm of
  gemini-2.5-flash as generated under different conditions from its three PI-detector arms (§8), and should defence
  comparisons for this model be reported only among the detector arms?
- **c2. Execution identity across corpora (§7.3).** 14,182 executions share id and raw bytes between agentdojo-2024-06
  and agentdojo-head but have different AER/PROV (origin revision). Keep the id content-addressed (and document that a
  release combining the corpora must deduplicate), or scope `x:` IRIs by corpus?
- **c3. Inspect scope association (b3).** Is the isolation of the AgentHarm run/step activities intended (no evidence in
  the log of who ran them), or should the harness be associated by a D rule?
- **c4. Inspect input-message authorship.** System and user messages of AgentHarm have `actor` `not_recorded`, so 3,710
  parts are unattributed. AgentDojo attributes the system prompt to the harness and the user prompt to the simulated
  user by D rules; is an analogous Inspect rule (dataset sample input → benchmark) wanted?
- **c5. Implied associations (P05).** State in the datasheet that delegation associations (562,624) and the
  generating activities of attributions (543,132) are implied by PROV Inferences 13/14, not asserted? (Recommended.)

- **c6. Code-less class-D rules (extends first-analysis C6).** Nine D rules cited by the new corpora have no `code` verification entry, only documentary evidence (§7.2). The C6 decision (a D rule may be cited only for code its verification block lists) would make all of them `_unverified` twins at class I, moving their statements into inference bundles for 2024-06 and adprov-v1. Is documentary evidence (the AgentDojo-PROV format notes, C.16) acceptable for class D, or do these join the C6 batch?

### 9.3 (d) Analysis artefacts (corrected, not corpus properties)

1. First-analysis extractor on Inspect: `model_call_used_ne_input`, `mc_input_nonmonotone` (§7.2).
2. D01 summary keyed by id only: 4 apparent differences (§6).
3. Scanner P06 scope (container ∪ core ∪ top) is narrower than the application view: "resolved elsewhere" counts are
   not dangling references (§5 P06).
4. Scanner A05 literal readings miss payloads that are visible only in Python-repr escaped tool outputs (§4.2 A05).
5. `exam2_scan.py` treats LIT_ESC hits in JSON-in-string attributes (`apv:args` etc.) as hits; they are JSON escaping.

### 9.4 (a) Correct and disclosed

Every structural, canonical-form, PROV-constraint, determinism and cross-document check (§3, §5, §6); the string-content
findings of §4.1 that are model output kept verbatim; the p9→p10 differences (§7.1).

---

## 10. Manuscript artefacts (extends first analysis §8)

### 10.1 Table (same columns as FA §8.1; rows N1–N8 are new; first-analysis rows that the new corpora extend are listed after)

| # | Artefact | Sources and counts (examples) | Catalogued | Class | Effect on metrics | Recommended disclosure |
|---|---|---|---|---|---|---|
| N1 | **Cross-corpus duplicate executions** | 14,182 executions in both agentdojo-2024-06 and agentdojo-head (same raw bytes and id; e.g. `ex_225a2d37rqjkhyav722sa3suzs`) | new | FO | pooled rates over the two corpora double-count 14,182 runs | "AgentDojo 2024-06 is largely contained in AgentDojo HEAD (14,182 shared runs); pooled analyses deduplicate by execution id." |
| N2 | **Double-escaped tool arguments** (literal `\n` instead of line breaks in contents and bodies) | head 436 executions (Gemini-1.5-pro-002 89/753, Meta-SecAlign-70B 97/5,958, Llama-3.3-70B 78/5,807), 2024-06 117, adprov-v1 104, AgentDyn 25, survey 18, ROPE 12 (e.g. `ex_li7duf2o6ffuhdjlhrf42e5fqr`) | new | FO | malformed written content; text-comparing utility checks can mis-score; a model-family effect (Gemini 1.x, Llama-3.3) | "Some models emit escaped newlines (`\n`) in tool arguments; the environment receives the literal sequence. We keep it verbatim." |
| N3 | **Generation-condition split in AgentDyn gemini-2.5-flash** (detector arms deterministic given context; undefended arm differs at the first reply in 648/648 cells) | §8; piguard/prompt_guard_2 identical in 425/648 cells (e.g. `ex_w7d2pcyhk5m6ug66prhsnv3sis` / `ex_opyxuc5kvrq25e3pv7ias77fn6`) | new | FO | detector-minus-undefended effects for this model include an unrecorded condition effect; detector arms are paired, not independent | wording in §8.3 |
| N4 | **Empty assistant turns without any call** | AgentDyn 4,631 executions with an empty final answer (738 entirely empty), head 343, survey 84, 2024-06 48, ROPE 33 | partly (`empty_assistant_text_ambiguous` covers empty text beside calls) | CR (`unk ambiguous`) | utility on the final answer fails by construction; refusal/compliance coders must not treat these as refusals | "n runs end with an empty model reply (provider/endpoint failure mode); they are scored as task failures and are not refusals." |
| N5 | **Dropped high byte in model output** (U+0019/U+0002/U+0001 for U+2019/U+2002/U+2001; one mojibake quotation mark) | AgentDyn 12 strings, adprov-v1 5 | new | FO | negligible; display and exact-text comparisons | none beyond the datasheet |
| N6 | **Completeness label is model-confounded in adprov-v1** | deepseek-chat 2,944/2,944 `unverifiable` (no usage counts), other models `verified_complete` (14,688) or `known_incomplete` (32) | `adprov.art.usage_absent`, `reported_calls_exceed` | NR | a "complete records only" filter drops one model entirely | "Filtering on verified completeness removes all deepseek-chat runs of the AgentDojo-PROV release." |
| N7 | **Timed activities only in two sources** | adprov-v1 82,444 activities, AgentHarm 24,149; no relation time anywhere; no time in the TraceLogger corpora | `adprov.art.times_not_recorded` (partial) | NR | any duration/latency analysis on the PROV level covers two sources only | "PROV activity times exist only where the source log records them (AgentDojo-PROV release, AgentHarm)." |
| N8 | **Model type errors in arguments**: strings holding lists, object reprs, invalid JSON as argument values | adprov-v1 235 + 10, AgentDyn 112 + 127 + 28, ROPE 13 (e.g. `ex_2dekpxp76c3lbauojttwzyp2uw`) | new | FO | tool errors and failed tasks caused by argument types | none beyond the datasheet |

First-analysis rows extended by the new corpora (counts from `reuse-summary-new-corpora.json`):

- row 1 benign `security` constant: 2024-06 2,014; adprov-v1 582 (`benign_security_normalised`).
- row 2 run error imposes outcomes: 2024-06 106.
- row 3 silent rerun: 2024-06 47 inferred (18,034 `lost` attempt index); adprov-v1 121 `rerun_passes_lost`.
- row 4 iteration-cap cut: 2024-06 145 logs; adprov-v1 47.
- row 5 outcome-only logs: 2024-06 207 (the same claude-3-opus logs as head; they are among the 14,182 shared).
- row 6 payload never reached the agent: 2024-06 2,921 of 15,725 attacked (18.6 %); adprov-v1 3,034 of 17,082 (17.8 %).
- row 8 attack success without exposure: 2024-06 9 (banking); adprov-v1 0.
- row 9 vacuous utility: 2024-06 81 (banking ut10 41, ut8 20, ut9 10, travel IT6 9); adprov-v1 151 (banking ut10 52,
  ut9 42, ut8 28, ut5 27).
- row 10 defences in benign runs: 2024-06 PI detector redacts in 81 benign runs.
- row 11 tool calls as text: adprov-v1 135 (json 90, named 44, marker 1); AgentHarm 12 (qwen3-coder `<function=` 14
  turns); 2024-06 14.
- row 14 provider ids: 2024-06 absent 1,469, empty 1,330, repeated 189.
- AgentHarm specific: `inspect.sample_limit` 54 (message limit reached: gpt-oss:120b 33), `max_tokens` stops 23,
  refusals 460 of 1,056; the harmful prompt is the user task itself (`payload_in_task_prompt` 1,056), so the AgentDojo
  exposure notion does not apply.

### 10.2 Proposed catalogue entries (text only; not committed into `src/`)

```toml
[[artefact]]
id = "inspect.art.abnormal_finish_max_tokens"
title = "Model turn stopped at max_tokens"
description = "The provider reports finish_reason max_tokens; the turn is truncated (A2 class A1)."
scope = { sources = ["agent-security-tools-survey"], parts = ["agentharm"], profiles = ["survey-agentharm"] }
cause = "provider"
detector = { rule = "artefact.generic.abnormal_finish", class = "O" }
claims = ["artefact.generic.abnormal_finish#max_tokens"]
handling = { class = "FO" }
expected = [{ snapshot = "agentharm", count = 23, basis = "examination 2 (A02)", status = "verified" }]

[[artefact]]
id = "inspect.art.text_tool_call"
title = "Tool call written as text"
scope = { sources = ["agent-security-tools-survey"], parts = ["agentharm"], profiles = ["survey-agentharm"] }
detector = { rule = "artefact.generic.text_encoded_call", class = "I" }
claims = ["artefact.generic.text_encoded_call#marker"]
handling = { class = "FO" }
expected = [{ snapshot = "agentharm", count = 12, basis = "examination 2 safety-net run", status = "verified" }]

[[artefact]]
id = "adprov.art.attempt_index_lost"
title = "Attempt index lost where earlier passes were rerun"
scope = { sources = ["adprov"], profiles = ["adprov-v1"] }
detector = { rule = "artefact.generic.sentinel_time", class = "D" }
claims = ["artefact.generic.sentinel_time#unknown_lost"]
handling = { class = "NR" }
expected = [{ snapshot = "release", count = 121, basis = "examination 2 safety-net run", status = "verified" }]
```

---

## 11. Threats to validity

- **Construct.** Every structural check passing shows self-consistency and conformance to RFC 8785, I-JSON and the
  PROV-CONSTRAINTS subset checked, not that the provenance is true. Graph completeness is relative to the AER and the
  rule catalogues.
- **Independence (partial).** The strict parser, the canonicaliser, the event graph, the cycle checks and the
  resolution code are written independently of `agentprov` (no import of the code under test, except `rfc8785` as the
  comparison side of X04, `jcs_bytes` for trajectory digests, `escape_untrusted` for display, `yamlsafe` for one
  reading, and the project's own derivation functions in D01/D02, which is the point of a metamorphic test). Same
  analyst family, same specifications, same research briefs.
- **Instrument.** String screens are regular expressions with byte prefilters; each prefilter is a superset of its
  decoded pattern (calibrated in §3.0 only for structural checks). Precision was judged only for the double-escaped
  argument screen (20/20) and the control-character screen (6/6); other screens are reported as screens with their
  attribution by pointer. The A05 scanner readings are deliberately narrower than the SEM normaliser (§9.3 item 4).
- **Sampling.** D01/D02 are samples; the zero-event bounds (0.23 %, 0.85 %) are about the sampled corpora and the
  stated configurations. Locale and time-zone variation cannot reach code paths not exercised by the sampled
  executions.
- **Internal.** S01's outcome comparison conditions on the detector run's own decisions (§8.3). The generation
  condition itself is undetermined from the logs.
- **External.** Results describe these eight corpora on `cc1aa51`/`afe7038`.
- **Untrusted data.** Corpus text was read only by programs; the few excerpts read for judgement were escaped and
  short; nothing in them was followed.

## 12. Reproducibility

Analysis code: `tools/analysis2/` at the commit of this report (worktree branch), first-analysis tools
`tools/analysis/` unchanged and reused through `tools/analysis2/exam2_reuse.py`. Environment: CPython 3.14.8, macOS
(Darwin 27.0.0, arm64), `uv sync --locked` (lockfile `sha256:da3cceee…`), `rfc8785` 0.1.4, `jsonschema` 4.26.0,
`pyyaml` 6.0.3. Corpora: `~/.agentprov/corpora/<id>.partial` as listed in §1.1, derived on `afe7038` (read-only). Seed
20261011 for every sample. Commands (4 worker processes at most):

```sh
uv sync --locked
python tools/analysis2/exam2_selftest.py --corpus $C/mandate-agentdojo-eval-p10.partial --out $D/selftest.json
for c in <the eight corpora>; do python tools/analysis2/exam2_scan.py --corpus $C/$c.partial --out $S/$c.jsonl --jobs 4; done
python tools/analysis2/exam2_merge.py --scan-dir $S --out-dir $D <the eight corpora>
python tools/analysis2/exam2_tables.py $D
python tools/analysis2/exam2_determinism.py sample --corpora <the eight corpus dirs> --out $D/d01-sample.json
python tools/analysis2/exam2_determinism.py run --sample $D/d01-sample.json --outdir $S/d01
python tools/analysis2/exam2_detsum.py $S/d01 > $D/d01-d02-determinism.json
python tools/analysis2/exam2_schema.py --corpus $C/$c.partial --out $D/x06-schema-$c.json --jobs 4
python tools/analysis2/exam2_p06view.py --corpus $C/$c.partial --out $D/p06-view-$c.json --jobs 4
python tools/analysis2/exam2_corpusfiles.py --corpus <the eight corpus dirs> --out $D/corpusfiles.json
python tools/analysis2/exam2_pathgrep.py --out $D/u14-machine-paths.json <the eight corpus dirs>
python tools/analysis2/exam2_overlap.py --out $D/q045-overlap.json <the eight corpus dirs>
python tools/analysis2/exam2_pairdiff.py --a $C/agentdojo-upstream-2024-06-p10.partial --b $C/agentdojo-upstream-head-p10.partial --n 200 --out $D/q045-pairdiff-2024-06-vs-head.json
python tools/analysis2/exam2_p9diff.py --old $C/<id>-p9.partial --new $C/<id>-p10.partial --out $D/p9diff-<id>.json   # agentharm: -p8
python tools/analysis2/exam2_markers2.py --corpus $C/$c.partial --scan $S/$c.jsonl --out $D/a05-attribution-$c.json
python tools/analysis2/exam2_b1check.py --corpus $C/$c.partial --out $D/a05-b1-$c.json
python tools/analysis2/exam2_bymodel.py $S/*.jsonl > $D/u06-bymodel.json
python tools/analysis2/exam2_piguard.py --corpus $C/agentdyn-a-p10.partial --out $D/s01-piguard.json
python tools/analysis2/exam2_piguard{2,3,4}.py --corpus $C/agentdyn-a-p10.partial --model gemini-2.5-flash --out $D/s01-….json
python tools/analysis/phase10_extract.py --corpus $C/$c.partial --out $X/$c.jsonl --jobs 3     # R01, the three new corpora
python tools/analysis2/exam2_reuse.py aggregate $X <the three new corpora>                         # R02
python tools/analysis/phase10_register.py <the three new corpus dirs>                              # R04
python tools/analysis2/exam2_dups_utility.py $X/<2024-06>.jsonl $X/<adprov>.jsonl                  # R05
python tools/analysis/phase10_crosscheck.py --corpus $C/agentdojo-upstream-2024-06-p10.partial --sample 0 --jobs 4   # R03
```

(`$C` = `~/.agentprov/corpora`, `$D` = `docs/reports/analysis/phase10-examination-2-data`, `$S`/`$X` = scratch.) The
per-execution scan outputs (about 0.5 GB) are not committed; the merged summaries are. Not re-run for Q-071 (a second
full run for byte-identical result files) within this session.
