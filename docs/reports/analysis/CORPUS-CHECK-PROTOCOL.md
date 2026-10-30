# Corpus check protocol: a reusable data-quality runbook for AgentPROV corpora

Version 1, 2026-10-11. Owner: the user (PhD research software). Written from the two phase-10 analyses so that the same
checks can be re-run, and compared, on every new or regenerated corpus.

**Version 2, 2026-10-15** (corpus pre-check before the regeneration round, branch `precheck-corpora`): adds section 8,
raw Level-1 checks over the whole population of every source part (`L1-nn`), a deterministic stratified Level-2 sample
through the pipeline, outcome sanity against the papers, and the batch execution used on the shared machine. Sections
1-7 are unchanged.

Baselines ("phase-10 baseline" below) are the results of:

- **FA**: `phase10-corpus-analysis.md` (first analysis; five corpora, 89,390 executions; code `dcdc3d3`, corpora derived on `afe7038`);
- **E2**: `phase10-examination-2.md` (examination 2; eight corpora, 126,351 executions; code `cc1aa51`);
- research briefs in `research/`: **A1** methodology, **A2** GenAI error classes, **A3** W3C PROV issue classes (ids
  `PI-nn`), **A4** escaping audit (findings `F-nn`), **C5** identical trajectories. Brief item ids are cited as in the
  reports (for example A1 Q-045, A3 PI-04, A4 F-02).

This protocol adds no result of its own. It was assembled from the reports and the scripts; command lines were
checked against each script's argparse (see section 4.2 for the unverified ones). Documentation only: no tool, `src/`
or test was changed.

---

## 1. Purpose, scope, approvals

AgentPROV corpora are census-style, hash-chained research datasets. A corpus check answers four questions: is it
well-formed, does it say only what the raw logs say, is it deterministic, and which source-data artefacts must the
manuscript disclose? It is read-only on corpora.

### 1.1 When to run

| Trigger | What to run | Extra |
|---|---|---|
| A new corpus (after its import, before packaging, datasheet or any figure) | everything in section 4 that applies to its family | first run of a new adapter family: adapt the tools first (section 5) |
| A regenerated corpus (re-import, PROV-only `derive`, re-index) | everything, plus G01 against the previous copy | compare with the corpus's own previous report first, then with the phase-10 baselines; expected movement is in 4.4 |
| Before any manuscript figure, table or number that reads corpora | R01 (aggregate), A05, SA01-SA09 for the corpora used | regenerate every number by script and diff against the manuscript (A2 P0 item 5) |
| After a version bump (profile, rule or artefact catalogue, SEM or PROV engine, validator, `aer/0.1` consumer) | all checks; the bump says which layers move (4.4) | a bump with no expected movement that moves a check is a finding |
| Before a release package or Zenodo deposit | all checks, plus the datasheet checklist | nothing is uploaded or published by this protocol |

### 1.2 Who approves what

| Action | Who | Rule |
|---|---|---|
| Running the checks, writing the report and data files | the analyst (a session or the user) | corpora, raw stores and `.env` are not modified or read; no network; no downloads |
| Pre-registered plan (report sections 1-2) | the analyst; the user reads it | committed before any result is computed |
| A proposed fix that changes AER, SEM, PROV, index, validation or `corpus.json` bytes | the **user** | standing rule: record every proposed fix (what, why, evidence, digest and corpus impact, risk) and get approval **before any corpus is regenerated** |
| Regeneration itself | the **user** approves the final batch list in `regen-batch.md`; the implementer states the expected digest changes before applying | one regeneration for the whole batch, after phase 11's PROV-only `derive` |
| A fix that changes no corpus bytes (catalogue entries, read-only detectors, render, robustness with 0 affected strings) | the user | precedent, 2026-10-11 (FA 9): "just fix the issues that require no corpus change and record the others". Ask whether the same policy applies before applying anything on a new analysis |
| Questions of class (c) | the **user** decides; the decision and its date go into the report, `regen-batch.md` or `datasheet-items.md` | |
| Datasheet statements, manuscript wording | the **user** | proposed wording is text only in the report |

Findings that change corpus bytes go to `regen-batch.md`. Datasheet statements go to `datasheet-items.md`. Source
artefacts go to the report's manuscript table and to `artefacts.toml` proposals (6.3).

---

## 2. Method

### 2.1 Phases (A1 sections 3 and 6; E2 section 1.2)

| Step | A1 phase | What is done | Output |
|---|---|---|---|
| 1 Pre-register | P0 | Freeze: code commit, versions, tool versions, corpus ids and digests, lockfile. Fix the population statement ("a census of what was imported, not a sample of agent executions in general"), the unit of every metric, the check map (each check new, reused or extended, with scope), thresholds, the census-versus-sample plan and the seeds. Commit this **before** any new check runs | report sections 1-2 |
| 2 Calibrate | (A1 section 8) | Fault-inject the scanner on mutated in-memory copies of one execution: every check must fire (C00, X04). A scanner that cannot detect a defect cannot certify its absence | `selftest.json` |
| 3 Census | P1-P5 | Mechanical checks over **every** execution and record: profile, structure, strings, AER semantics, integrity chain, PROV constraints and graph quality | scan, feature and report files |
| 4 Sample | P4, P6 | Only for expensive or judgement questions: determinism re-derivation (D01, D02) and string-hit judgement | sample files with ids |
| 5 Classify | P6, section 7.1 | Attribute every finding (2.2) and attach a disposition. A screen hit is not a defect until attributed | findings tables |
| 6 Report | P7 | Report skeleton of section 6 plus a delta table against the baselines | report, data directory |

### 2.2 Finding classes

| Class | Meaning | Disposition |
|---|---|---|
| (a) correct and disclosed | a source-data property, represented faithfully | no fix; disclosure wording; may enter `artefacts.toml` and the datasheet |
| (b) defect or improvement | something lost, invented or distorted by a reader, mapper, SEM, PROV engine, validator or corpus assembly | fix **proposed** with file:line, spec section, expected digest and corpus impact, risk; ranked by impact |
| (c) question for the user | a semantic or policy choice the evidence cannot settle | decision recorded with date |
| (d) analysis artefact | introduced by an audit tool (parsing assumption, key, scope) | fix the tool; never report as a corpus property |

Attribution order (A1 7.1): present in the raw bytes and represented faithfully -> (a); present in raw but lost,
invented or distorted downstream -> (b), located by diffing the stages raw -> AER -> SEM -> PROV; only in an analysis
output -> (d); raw unavailable or ambiguous -> "undetermined", with the evidence needed. A1 also proposes severities
S0-S3 (S0 blocks release, S1 changes a headline number, S2 biases a secondary statistic or must be disclosed, S3
cosmetic); phase 10 did not use them, ranking by impact instead. Handling classes for source artefacts are D.15.1:
CR correct representation, DR derived reconstruction, RJ recomputed judgement, FO flag only, NR not recoverable.

### 2.3 Census versus sampling

| Rule | Value used in phase 10 |
|---|---|
| Census | every mechanical check (parse, canonical form, schema, digests, referential integrity, PROV constraints, graph metrics, string screens, duplicates). Report "0 of N", never an interval. A structural check is zero-tolerance: one occurrence is a finding |
| Descriptive screens | U03-U14, A01-A03 and the SA rows: counts with denominators, no pass/fail until attributed. Outlier screens: IQR fence Q3 + 3*IQR within a corpus, no threshold tuned on the data |
| Sample, determinism (D01) | stratum = (profile, any non-ubiquitous issue present, completeness, status) over executions with `stages.aer = ok`; per stratum `k = max(min(10, size), round(150 * size / total))`, so at least 10 per stratum and about 150 per corpus; 1,305 executions over eight corpora |
| Sample, re-mapping (D02) | 50 executions per corpus from `unit = agent_execution`; seven whole-file corpora gave 350 |
| Sample, judgement | up to 20 per (pattern, pointer class) cell, shown only as `escape_untrusted` excerpts of at most 120 characters |
| Systematic sample | `exam2_schema.py --every N` only if throughput forbids a census (state it). Phase 10 ran the census |
| Seed | 20261011 for every sample; sort execution ids before drawing; per-corpus stream `random.Random(f"{seed}:{corpus}")`; the sampled ids are committed |
| Zero events in n | one-sided exact 95% upper bound `1 - 0.05^(1/n)` (`exam2_lib.cp_upper_zero`; rule of three: about 3/n). n = 300: 0.99%; 350: 0.85%; 1,000: 0.30%; 1,305: 0.23%; 3,000: 0.10% |
| Some events | Wilson 95% interval, z = 1.959964 (`exam2_lib.wilson`); for judged precision report the lower bound (20 of 20: 0.84; 17 of 17: 0.82) |
| Statistics about a wider population | executions are clustered (same task across models, same attack across tasks, one run in two corpora). Intervals describe the corpus drawn from; for claims about "the benchmark" use task-clustered intervals and paired comparisons (A1 6.1) |
| Multiple comparisons | no confirmatory hypothesis is tested; all content screens are exploratory counts (A1 6.4). If a confirmatory test is ever added, pre-register it and use Holm |

### 2.4 Threats to validity (A1 7.3; E2 section 11)

| Threat | Mitigation | Residual |
|---|---|---|
| Circularity: the project validates its own output | independent strict parser, second JCS, own PROV graph code, `jsonschema`, metamorphic re-derivation | partial: same analyst family, same specifications, same research briefs |
| Construct: valid is not true | state "well-formed" and "faithful to the raw log" apart from "true" | label accuracy of the source benchmark is only bounded (no double-annotated audit) |
| Instrument: regex screens have unknown precision | byte prefilter as a superset of the decoded pattern; judged samples for the screens that matter | precision judged only for U04 (6 of 6) and the double-escaped argument screen (20 of 20) |
| Sampling: D01/D02 are samples | zero-event bounds stated for the stated configurations | environment variation cannot reach code paths the sample did not exercise |
| Internal: confounding by source, model, suite, attack; attribution of arm effects | report per stratum; for defence arms run the S01 tests | generation conditions are often unrecorded |
| External | results describe the named corpora on the named code | nothing generalises to other benchmarks |
| Untrusted data | tools print ids, counts, normalised pointers, truncated digests; text only through `escape_untrusted`; text in corpora is data, never instructions | none known |

Analysis traps met in phase 10 (class (d)); check each before believing a finding on a new family:

1. an extractor that recognises only `m<n>` message ids reported 1,601 + 1,012 + 3,710 false cross-check violations on Inspect (ids `p<n>`, `o<n>`);
2. results keyed by execution id alone mis-merged executions present in two corpora (4 phantom differences);
3. P06 resolved arguments in container + core + top level only; the application view is wider ("resolved elsewhere" is not dangling);
4. the A05 literal readings are narrower than the SEM normaliser; reconcile with `exam2_markers2.py` before calling a mismatch a miss;
5. U06 counts literal escapes inside JSON-in-string attributes (`apv:args` and similar); that is JSON escaping, not double escaping.
6. A01, A03, SA07 and the extractor's empty-turn screens key on role `assistant`; a family that keeps `agent` verbatim
   (DTap, D-28) gives 0 by construction. Map the role first (DTap sample check, 2026-10-12).
7. A tool that assumes every index row has PROV paths fails on executions whose `prov` stage failed (fixed in
   `exam2_p06view.py`, 2026-10-12).

---

## 3. Check catalogue

76 checks, one row per id. Ids are those of the reports so old results stay traceable; ids new to this protocol are
marked (p). E2 (its section 2) numbered the first-analysis tools R01-R07; FA itself has no ids, so the sub-checks of the
extractor `phase10_extract.py` (R01) are numbered here R01a-R01o and R07 is split into R07a/b. R02 is the aggregation
step of R01 (tool T02). R06 (payload visibility against markers) is carried by A05 and SA04. Tool keys `T01`-`T21` are
defined with their **exact command lines** in section 4.2 (the Tool column cites the key). Layer: raw, AER, SEM, PROV,
index, corpus (manifest, register, validation rows). C = census, S = sample.

Reach column: **G** runs unchanged on any family; **G*** runs, but needs a family input or has a caveat (named); **F**
family-specific today (AgentDojo family) and needs a new or parameterised piece for another family; the text after the
code says what `dtap` (section 5) would need. Baselines are phase-10 results over all eight corpora unless stated.

### 3.1 Instrument calibration and structure

| ID | Detects (why) | Layer | C/S | Tool | Reach; what dtap needs | Phase-10 baseline |
|---|---|---|---|---|---|---|
| C00 | the scanner finds injected faults: duplicate key, `NaN`, `1e400`, whitespace, reordered key, `1.0`, escaped lone surrogate, upper-case escape, BOM, trailing data, big integer; PROV: derivation cycle, C51, duplicate start, dangling argument, self-loop (A1 s8) | AER, PROV | S (1 execution) | T14 | G*: needs a first-by-id execution whose core has an activity and `used`; run on a D-class corpus (Mandate), once per scanner version | 15 of 15 detected; unmutated document: no finding |
| X04 | second JCS equals `rfc8785` on RFC vectors (27 edge numbers, 200,000 random doubles, key order incl. astral vs U+E000, C0, DEL, U+2028/9, U+0085); both reject 2^53 and a lone surrogate (A2 C1, D2) | none | C | T14 | G | 0 differences |
| X01 | independent strict re-parse: UTF-8, BOM, duplicate keys, `NaN`/`Infinity`, `1e400`, integers beyond +-(2^53-1), lone surrogates in strings and keys, trailing data; AER, SEM, PROV and the corpus-level files (A1 Q-020; A2 D1) | AER, SEM, PROV, corpus | C | T06, T09 | G | 0 failures in 8 corpora; 6 `$int` wrappers (AgentHarm, from 10 raw big integers) |
| X02 | a second JCS implementation (own ECMAScript number formatting, own UTF-16 key order) reproduces every canonical line and document byte for byte (A1 Q-022; A2 C1) | AER, SEM, PROV, corpus | C | T06, T09 | G | 0 mismatches |
| X03 | number-form and key-order census: integral floats, `$int`/`$float`, objects whose UTF-16 and code-point key orders differ, exponent forms (A2 C1, A7, A9) | AER, SEM, PROV | C | T06 | G | integral floats in trees 0; key-order differences 0; `ext.lex` float pointers 42,990 |
| X05 | JSONL framing: LF only, no CR, no blank line, final LF present; raw U+2028/U+2029/U+0085 that `splitlines()` would split on (A2 D3; A4 1.1) | AER, SEM, index | C | T06, T09 | G | 0 |
| X06 | every AER record validates against `aer-0.1.schema.json` with `jsonschema` `iter_errors`, an engine independent of the typed validator (A1 Q-021) | AER | C (`--every N` allowed, stated) | T07 | G (AER schema only; **no SEM schema exists**) | 4,461,513 records, 0 with an error |

### 3.2 String content (hazard screens; A2 A, E; A4 part 3)

| ID | Detects (why) | Layer | C/S | Tool | Reach; what dtap needs | Phase-10 baseline |
|---|---|---|---|---|---|---|
| U01 | `$utf16`, `$lit`, `$int`, `$float` wrappers by pointer; F-01 population (A4 F-01) | AER | C | T06 | G | `$utf16` 0, `$lit` 0, `$float` 0; `$int` 6 (AgentHarm) |
| U02 | **lone surrogates**, escaped in bytes and decoded (must be 0 outside `$utf16`); F-01 loses the whole execution (A2 A8; A4 3.1) | AER, SEM, PROV | C | T06 | G; also read the raw store (X01/A04) | 0 escaped, 0 decoded; raw: no lone surrogate in 135,821 objects (1,143 objects hold valid pairs) |
| U03 | **U+2028, U+2029, U+0085** in strings (A2 D3; A4 3.1) | all | C | T06 | G | 0 |
| U04 | C0/C1 controls (TAB and LF apart), CR, NUL, ESC and ANSI/OSC sequences, escaped ESC as text (A2 E2) | all | C | T06 | G | 6 distinct model-written argument values (AgentDyn 4, adprov-v1 2; 17 strings), CR in 10 strings; NUL 0; ESC 0. Cause: dropped high byte (U+0019 for U+2019) |
| U05 | **bidi and tag characters**, zero-width, variation selectors, PUA and non-characters, U+FFFD, mojibake (A2 A8; A4 3.1) | all | C | T06 | G | bidi 0, tags 0, PUA 0, U+FFFD 0; zero-width 2 strings; mojibake 3 (adprov-v1); variation selectors 808 strings (emoji) |
| U06 | **double escaping** residues in decoded text: literal `\n`, `\\n`, `\uXXXX`, escaped surrogates, YAML-only escapes, wholly escaped strings (A2 A3; A4 3.1) | all | C | T06, T20 | G; expect Python-repr tool results to hold literal escapes by design: classify by pointer | model artefact "tool arguments with literal `\n`": head 436 executions, 2024-06 117, adprov-v1 104, AgentDyn 25, survey 18, ROPE 12, AgentHarm 2 (judged 20 of 20, Wilson lower 0.84); escaped-surrogate text 0; ESC as text 0 |
| U07 | Windows paths damaged by an unescape (drive + colon + control or separator) against intact paths (A2 A2; A4 3.1) | all | C | T06 | G | damaged 0; intact 16 (AgentDyn), 110 (AgentHarm) |
| U08 | JSON-in-string fields: strict JSON, Python repr, YAML or unparsed (truncated vs bad escape) (A2 A2; A4 3.3) | all | C | T06, T19 | G | 185 fail every reading, all model output (AgentDyn 91, ROPE 74, adprov-v1 20); strings holding lists: adprov-v1 235, AgentDyn 112, ROPE 13 |
| U09 | Python-repr residues: dict/list heads, object reprs, `datetime(`/`Decimal(`/`UUID(`, `b'...'` (A4 3.1) | all | C | T06 | G; DTap tool states are Python-repr strings: expect large repr-head counts, never evaluate | object reprs 127 occurrences (13 AgentDyn argument values); constructors 16; bytes 9 |
| U10 | **HTML entities**, `![`, `<script`, `<U+XXXX>` look-alikes in strings that reach PROV literals (population exposed to DOT `--show-content`, F-02) (A4 F-02, 3.3) | all, PROV | C | T06 | G | PROV strings: entities 1, markup 2, `<U+XXXX>` 0 (F-02 population 3); all strings: entities 125 |
| U11 | identifier grammar: AER ids, PROV keys and QName values; id-like strings ending in LF; DOT keywords (A4 3.3; A3 PI-15) | AER, PROV | C | T06 | G | unusual-character keys 0; 16 id-like strings ending in LF are model answers |
| U12 | pointer tokens with **non-ASCII digits** and leading zeros (F-04) (A4 F-04) | AER, SEM, PROV | C | T06 | G | 0 in 108,044,302 pointer strings |
| U13 | NFC, non-ASCII and mixed-script names: model ids, tool names, task ids (A2 A8; A4 3.3) | AER | C | T06 | G | 0, except 2 tool names with whitespace (AgentDyn sentence-as-name) |
| U14 | absolute paths, machine-specific strings (importer's home, corpus home, temp, worktree), secret-shaped strings (A2 C7, P1-15) | all except raw | C | T06, T10 | G; for dtap add DT01 (sandbox `env_vars` values) | machine-specific 0 in all corpora; benchmark `/Users`, `/home` paths and fake-key fixtures only (ROPE 233, AgentDyn 376 secret-shaped); no real credential |

### 3.3 AER semantics

| ID | Detects (why) | Layer | C/S | Tool | Reach; what dtap needs | Phase-10 baseline |
|---|---|---|---|---|---|---|
| A01 | tool-call argument census: types, double-encoded arguments, key-set and type drift per tool (A2 A2, A6) | AER | C | T06 | G | all 581,326 structured calls have object arguments; `args_raw` never present; 11 non-identifier tool names |
| A02 | stop/finish-reason census, truncation (A2 A1, A4) | AER | C | T06 | G; dtap logs may not record finish reasons: expect `not_recorded` | recorded only in adprov-v1 (`tool_calls` 39,841, `stop` 14,597, `error` 3, `length` 1) and AgentHarm (`max_tokens` 23) |
| A03 | empty assistant turns without any call; empty final answers (A2 A4) | AER | C | T06 | G | AgentDyn 4,632 turns in 4,631 executions (738 entirely empty), head 343, survey 84, 2024-06 48, ROPE 33, adprov-v1 1; AgentHarm and Mandate 0 |
| A04 | degenerate executions (`adapter_defect`, `aer.write.invalid`, `unparseable_artefact`); raw-side population: duplicate keys, non-finite numbers, big integers, lone surrogates in the raw objects (A4 F-01; A2 D1) | index, raw | C | T09 | G | 0 degenerate; 135,821 raw JSON objects parse strictly; 10 integers beyond I-JSON (AgentHarm) |
| A05 | payload spelling (verbatim, YAML-escaped, JSON, repr, double JSON, whitespace-collapsed, YAML-decoded) against the SEM `injection_marker` status, every attacked execution; finds markers missed (class B1) or over-matched (F-10) (A4 3.3, F-10) | SEM, AER | C | T06, T16 | **F**: the scanner imports AutoDojo's `yaml_escape`; dtap needs spellings for MCP result wrappers and repr states, and channel awareness (A05 applies to environment payloads only) | misses: only ROPE, 1,850 markers in 1,245 executions (AutoDojo arm 1,840 markers in 1,235 executions; plus 10 `ambiguous` long-horizon markers); other 6 corpora 0. All `present` markers explained by a SEM reading (17 of 17 judged true; Wilson lower 0.82) |

### 3.4 Integrity chain, index, accounting (FA 2-4; extractor R01)

| ID | Detects (why) | Layer | C/S | Tool | Reach; what dtap needs | Phase-10 baseline |
|---|---|---|---|---|---|---|
| R01a | the digest chain: raw objects re-hash to their name; AER seal = `digests.aer`; SEM seal = `digests.sem` and SEM `aer_digest` = AER; PROV sha256 = `digests.prov`, strict parse, `xd:aer.<digest>` = AER; validation-row JCS digest = `digests.validation` (A1 Q-040, Q-041) | raw, AER, SEM, PROV, index | C | T01 | G | 0 errors in 126,351 (FA 89,390; E2 the other 36,961) |
| R01b | validation outcomes: checks failed, warnings recorded | index | C | T01 | G | 0 failed, 0 warnings, 8 corpora |
| R01c | uniqueness: duplicate `ex`, duplicate source sha256, rows with more than one origin | index | C | T01 | G | 0 / 0 / 0 |
| R01d | identifier-field characters: control, bidi, zero-width, non-ASCII in task facets and actor names | AER | C | T01 | G*: facet names are read from `task.suite`, `task_id`, `attack_id`, `attack_target_id`, `defense_id`; dtap facets (domain, threat model, channel, attack category) must be added | 0 |
| R01e | `after` edges malformed (all point backwards); model-call inputs non-monotone; tool executions in a batch ordered | AER | C | T01 | G*: message ids are recognised as `m<n>` only (trap 1); verify the dtap mapper uses that id scheme or generalise | 0 in the five FA corpora |
| R01f | status and completeness census: ok / ok_with_issues / failed; verified_complete / known_incomplete / unverifiable; unit `outcome_only`; degenerate (HL H.3.2) | index | C | T01 | G | failed 0 in all; before fix B2, `verified_complete` was vacuous on 234 rows (head 232, ROPE 2; 2024-06 232 likewise), AgentHarm 4 rows with a declared loss; adprov-v1 deepseek-chat 2,944 all `unverifiable` (N6) |
| R01g | seal-issue census by code and by model, suite and attack (A1 Q-060) | AER | C | T01, T02 | G (codes are family vocabulary) | `retry_passes_inferred` ROPE 322, AgentDyn 826, head 82; `unexecuted_tool_call` logs ROPE 675, AgentDyn 1,683, head 800, survey 48; `identity_conflict` 949; `identity_unresolved`, `missing_tool_result`, `undeclared_quirk`, `unknown_message_shape` 0 (except AgentHarm `missing_tool_result` 4); full tables in `phase10-data/summary.json` |
| R01h | unknown reasons and evidence classes: `unk` reasons, `evf` tags O/D/I, PROV statements by bundle and class; no I-class statement in core (A1 Q-050, Q-052) | AER, PROV | C | T01, T02 | G | `not_recorded` dominates; no `withheld`, no `not_applicable`; no core statement is I, no inference statement is O or D |
| R01i | SEM census: annotation types and values, fail-closed `unknown` roles/integrity, injection-marker statuses (A1 Q-037) | SEM | C | T01, T02 | G*: unknown-tool rule ref is `agentdojo.unknown_tool*`; dtap needs its suite/tool tables or documents the gap | AgentDyn dailylife/github/shopping 100% `unknown` (documented gap); markers present / absent / ambiguous: ROPE 29,194 / 154,702 / 3,802, head 73,580 / 171,375 / 0 |
| R01j | graph size: nodes, edges, bytes, nodes and edges per message; outliers by long runs | PROV | C | T01, T02 | G | nodes per message stable 5.7-6.4; edges per message 10-16 (I-class higher: closure grows quadratically); no outlier caused by mapping |
| R01k | AER -> PROV cross-checks: every message with a generator has its `wasGeneratedBy`; every message without one is attributed; tool_call parts `hadMember`; model calls, executions and decisions associated; linked executions `used` their request; model calls `used` exactly their AER `input` (A1 Q-051) | AER, PROV | C | T01 | G*: `m<n>` ids (trap 1) | 0 violations in the five FA corpora and 2024-06, adprov-v1; AgentHarm hits are class (d) |
| R01l | statements that must never appear: `wasInfluencedBy`; relation `prov:time`; an I-class statement in core; `used`/`wasDerivedFrom`/`wasInformedBy` in assessment; a tool execution `used` anything but its request (A1 Q-052, Q-053) | PROV | C | T01 | G | 0 each. Activity `prov:startTime` exists only in adprov-v1 (82,444 of 202,263 core activities) and AgentHarm (24,149 of 24,149) |
| R01m | accounting identities: calls = executions + denials + unexecuted; `agent_calls_vs_assistant` (A1 Q-032) | AER | C | T01 | G* (check names); dtap pairs calls to results by order | `tool_calls_dispatched` consistent wherever calls exist; `agent_calls_vs_assistant` `unverifiable` by format; no `inconsistent` verdict |
| R01n | mapping-artefact screens: quirk hooks fire only where `applies` matches; profile `observed` counts reproduced; constant fields (benchmark version, pipeline name); timestamps | AER | C | T01 | **F**: quirk names are AgentDojo-family; dtap needs its own quirk list and `observed` table | every profile `observed` count reproduced (ROPE denials 12,657; AgentDyn redactions 29,317, CaMeL orphans 1,977; head 3,560/485/82/804/207/105/1/815/2,138/213; Mandate declines 240); no `undeclared_quirk` |
| R01o | artefact safety net (`agentprov.artefacts.scan`) with the shipped catalogues: findings and classified vs unclassified (D.15.3) | AER (SEM) | C | T01 | G*: the family needs an `artefacts.toml`; **the extractor calls `scan` without SEM records**, so the `payload_not_reaching_agent` detector is not run by it (FA 9.1, B5) | after B4: unclassified findings 156 (AgentHarm 35, adprov-v1 121); the E2 proposals b5 close them |
| R04 | `register.jsonl` against `executions.jsonl` and `corpus.json`: unique `rid`, `map.*` rows <-> index issues, `select.*` counts = `not_imported_by_code`, owners only for `select.owned_elsewhere`, severities (A1 Q-041) | index, corpus | C | T05 | G | consistent in 8 corpora; every JSONL corpus file parses strictly and is JCS line by line (0 mismatches, 0.64 million lines) |
| R05 | identical-trajectory groups (identical message lists) across files: what differs inside groups, whether utility differs for the same user task (A1 Q-043, Q-058; FA 4.6) | AER | C | T17 | G*: label keys (`model`, `attack`, `target`, `task_id`, `suite`, `defence`, `rope_arm`) and judgement names (`utility`, `security`) are AgentDojo's; dtap needs framework, domain, channel, re-run keys | head 382 groups / 3,612 executions; ROPE 53 / 396; AgentDyn 655 / 4,120; survey 32 / 299; 2024-06 150 / 816; adprov-v1 112 / 431; AgentHarm 0; utility differs inside a group: 0 |
| R07a | rule placement across corpora: where each rule's statements land (core vs inference) per structural class (FA 6) | PROV | C | T03 | G | differences only as the structural class dictates; no mapper inconsistency |
| R07b | D-class rule citations against the code each rule lists (D.5.4, C6, D-24) | PROV | C | T04 | G* (reads every family's rule catalogue; the original reads agentdojo only) | unverified-code D citations in ROPE, AgentDyn, head `v1.k14`, Mandate; 9 code-less D rules in 2024-06/adprov-v1 (decided c6: class-I twins, regen batch item 3) |

### 3.5 PROV constraints and graph quality (A3)

| ID | Detects (why) | Layer | C/S | Tool | Reach; what dtap needs | Phase-10 baseline |
|---|---|---|---|---|---|---|
| P01 | **event-ordering validity without times**: strict-order cycles (**Constraint 42**) and non-strict event cycles, per container, core + inference view, core + assessment view (A3 PI-04, PI-05; A1 Q-056) | PROV | C | T06 | G | 1.78 million views: 0 strict, 0 non-strict cycles (the validator does not run this; regen item 10) |
| P02 | cycles: used/generated dependency, `wasInformedBy`, `wasDerivedFrom`, `specializationOf` + `mentionOf` (A3 PI-08, PI-24) | PROV | C | T06 | G | 0 in all views (4.65 million `wasDerivedFrom`) |
| P03 | **Constraint 51**: `wasDerivedFrom` with generation or usage but no activity (A3 PI-07) | PROV | C | T06 | G | 0 (4,653,844 derivations) |
| P04 | **Constraint 26** duplicate start events; **Constraint 24** duplicate generations (A3 PI-02) | PROV | C | T06 | G | 0 / 0 |
| P05 | normal-form expansion (Inferences 9/10, 11, 13, 14): single generator after expansion; trigger generator = starter; attribution and delegation lints (A3 PI-11, PI-12, PI-31) | PROV | C | T06 | G | no entity with two generators, explicit or expanded; 560,647 starts all consistent; attribution generator implied only for 543,132 `wasAttributedTo`; delegations with implied responsible-agent association 562,624 (datasheet item 4) |
| P06 | dangling references, independently resolved in the container + core + top level, then in the **application view** (EF E.1.6 item 1) (A3 PI-26) | PROV | C | T06, T08 | G | 0 unresolved among 36.5 million inference-bundle node arguments; method set in every bundle IRI = `apv:method` in all 1,057,148 bundles |
| P07 | **shared statements**: top-level `raw:`/`sw:`/`rules:` statements identical across the documents of a corpus and across corpora (A3 PI-30) | PROV | C | T06 + T06b | G; cross-corpus part needs other corpora's scan files (not committed; see gaps) | 126,416 keys, 0 variants within corpora; the only cross-corpus variants are 14,182 `raw:` entities (2024-06 vs head, `apv:originRevision`) |
| P08 | `mentionOf` census and resolution (PROV-LINKS Note; not PROV-JSON) (A3 PI-17) | PROV | C | T06 | G | 4.12 million, all general entities in the named bundle, all specific entities declared |
| P09 | graph metrics: weak components (core; core + inference; plus attribute links), orphan classes, `apv:Gap` share, degree distributions, start-time coverage (A3 PI-25, PI-27; A1 Q-054, Q-055) | PROV | C | T06, T01 | G | components core + inference + attribute links p50 4 (3-9; AgentHarm 7); Gap share 0.156-0.325; orphans by design: Gap, CaptureProfile, MessagePart (system and first user), idle defence and tool runtime; AgentHarm only: run activity, harness, 7,946 of 8,388 steps (b3) |
| P10 | PN_LOCAL trailing `.`; namespace IRIs not ending in `#` or `/` (A3 PI-15) | PROV | C | T06 | G | 0 |
| P11 | multi-valued statement keys (arrays under one id) (A3 PI-01) | PROV | C | T06 | G | 0 |

### 3.6 Determinism, fidelity, import-time checks

| ID | Detects (why) | Layer | C/S | Tool | Reach; what dtap needs | Phase-10 baseline |
|---|---|---|---|---|---|---|
| D01 | **determinism**: SEM and PROV re-derived from the stored AER under an environment matrix (TZ, locale incl. `tr_TR`, `PYTHONHASHSEED`, `PYTHONUTF8`, worker count 1 vs 4) are byte-identical to the corpus files; tiers 3-4 statuses equal the stored validation rows (A1 Q-035, Q-042; A2 C3, P0-2) | SEM, PROV, index | S (about 150 per corpus) | T13 | G*: needs the family's SEM profile registered in `provjob.PROFILES`; strata do not include the framework: for dtap add (framework x model) | 1,305 executions x 6 configurations = 7,830 re-derivations, 0 differences; bound 0.23% |
| D02 | **determinism of mapping**: the raw primary object (and context artefacts) re-mapped reproduces the AER bytes (A1 Q-035) | AER | S (50 per corpus) | T13 | G*: needs context artefacts (the dtap task-config join) rebuildable from `raw/origins.jsonl` and the profile's `context_artefacts` globs; skips Inspect units by profile prefix | 350 of 350 equal (7 whole-file corpora); bound 0.85%; AgentHarm skipped (container dialect) |
| R03 | **fidelity**: AER states what the raw log shows and nothing more: each source message mapped once at its position; roles, texts, call names, arguments, ids; results and errors; fixtures = `injections`; utility/security values none invented or dropped; run duration and timestamp verbatim; no record other than the run scope carries a time (invariant 2) | raw, AER | C | T15 | **F**: written for the TraceLogger log; dtap needs its own cross-check | 0 mismatches in 89,390 (FA) + 18,241 (2024-06) executions |
| IM01 | the import-time recompute: PROV re-derived from AER + SEM in a fresh process equals the stored bytes; units, dialect variants, accounting verdicts, issue codes, statements by rule | AER, PROV | C | T21 | G (needs the import's `--summary-json`) | per-source reports `docs/reports/<source>/import-cli-*.json` |
| IM02 | SEM stage report: stage states per profile, SEM set digest, tier-3 states, assessment-bundle content by claim | SEM, PROV | C | T21 | G | `docs/reports/sem/import-*.json` |
| IM03 | profile census: every `observed` count of the profile recomputed from the pinned source (via the fetch cache) and compared | raw, AER | C | T21 | **F**: `tools/agentdojo/profile_census.py` uses AgentDojo-family quirk hooks; dtap needs its own census and `observed` table | all `observed` counts reproduced for the five FA profiles |
| IM04 | source cross-checks: figures measured from the AERs against the figures the investigation derived from the raw logs by independent scripts | AER | C | T21 | **F**: `tools/agentdojo/source_checks.py` knows `mandate` and `survey` only; dtap would reconcile with its source card (64,110 trajectories, 65,902 judge results) | Mandate and survey figures agree |

### 3.7 Cross-corpus, regeneration, defence arms

| ID | Detects (why) | Layer | C/S | Tool | Reach; what dtap needs | Phase-10 baseline |
|---|---|---|---|---|---|---|
| G01 (p) | old-versus-new comparison of a re-derived corpus: per artefact kind, the normalised JSON pointers that differ, with counts and ids; ids present in one corpus only (E2 7.1) | AER, SEM, PROV | C | T12 | G | 2024-06: AER history fields + profile digest (all 18,241), PROV catalogue digest and derivation keys only; adprov-v1: PROV catalogue digest only; AgentHarm: byte-identical |
| G02 (p) | cross-corpus overlap of raw objects and execution ids; which attributes of a shared `raw:` entity differ; same-id signature on a seeded sample (A1 Q-045) | corpus | C (+ S 200 for the signature) | T11 | G (corpora must sit in one directory) | 14,182 executions in both 2024-06 and head (same bytes and id; AER/PROV differ in origin revision); no other pair |
| G03 (p) | manual upstream check of identical cross-model trajectories: byte-identical files, git blob ids, durations, timestamps, introducing commits (C5, FA C5) | raw | S (manual) | git on the history store | **F**: needs the upstream history; DTap logs come from a dataset revision, not a git history of models | 23 groups (13 head, 10 AgentDyn): all coincidence of short deterministic runs |
| S01 | defence arms of one model: identical message lists across arms, timestamps/durations/blobs, divergence point (model-side or defence-side), outcomes where the defence did not act (C5 item 9) | AER, PROV | C | T18 | **F**: AgentDyn arm names and cell key (suite, user task, attack, injection task); run only if a corpus has arms of one model | gemini-2.5-flash: piguard / prompt_guard_2 identical in 425 of 648 cells, undefended differs from every detector arm at the first reply in 648 of 648 (artefact N3) |

### 3.8 Source-artefact screens (FA 8, E2 10; feed the manuscript table)

These are derived from the extractor rows (T01/T02) and, where noted, from the safety net and the SEM markers. Counts
are executions.

| ID | Detects (why) | Layer | C/S | Tool | Reach; what dtap needs | Phase-10 baseline |
|---|---|---|---|---|---|---|
| SA01 (p) | harness constants and imposed outcomes: benign `security` constant true; run error imposes outcomes; outcome-only logs (FA rows 1, 2, 5) | AER | C | T01, T02 | **F**: AgentDojo harness; for dtap read `judge_result.json` semantics first | benign constant: head 3,546, AgentDyn 5,176, ROPE 748, survey 395, Mandate 27, 2024-06 2,014; run error imposed: head 105, AgentDyn 5, survey 11, 2024-06 106; outcome-only: head 207, ROPE 2 |
| SA02 (p) | pass loss and iteration-cap cut: silent rerun (only the last pass logged), unexecuted trailing calls (FA rows 3, 4) | AER | C | T01, T02 | **F** | silent rerun: head 82, ROPE 322, AgentDyn 826, 2024-06 47; cap cut: head 800, ROPE 675, AgentDyn 1,683, survey 48 |
| SA03 (p) | **payload never reached the agent**: attacked runs with no `present` marker on any tool result (FA row 6; D.15.3 detector `payload_not_reaching_agent`) | SEM | C | T01 (+ safety net with SEM records) | G*: needs fixtures and markers; **three-way for dtap**: observed, absent, and unobservable channel (tool, skill, prompt injection) | head 5,847 of 32,634 attacked (18%), ROPE 2,303 of 10,041 (23%, overstated by B1), AgentDyn 18,368 of 33,091 (55%), survey 600 of 2,847 (21%), Mandate 23 of 369, 2024-06 2,921 of 15,725, adprov-v1 3,034 of 17,082; safety-net run gives head 5,895 |
| SA04 (p) | attack success without exposure: checker true, no payload visible (FA row 8; C1) | SEM | C | T16 | G*: needs judgement names and markers | head 11 (all banking `user_task_15`), ROPE 22 (17 AutoDojo slack IT1, 5 `important_instructions`), AgentDyn at least 1, 2024-06 9, adprov-v1 0 |
| SA05 (p) | vacuous utility (utility true with zero tool calls) (FA row 9) | AER | C | T01 | **F**: needs the family's outcome names | head 182, ROPE 73, survey 4, AgentDyn 2, 2024-06 81, adprov-v1 151 |
| SA06 (p) | defences intervening in benign runs (redactions, denials, declines) (FA row 10) | PROV | C | T01 | G*: from `decision` records; dtap has no defences in the sampled logs (verify) | head PI detector 81 of 124 benign runs (278 of 486 outputs, 57%); AgentDyn transformers PI 546 of 704 runs; ROPE guard 183 of 748; Mandate 8 of 9 prepasses; DRIFT 33 of 88 |
| SA07 (p) | text-encoded tool calls and empty assistant turns (FA rows 11, 13; A03) | AER | C | T01 (safety net) | G (heuristic detector; needs exclusion lists per family) | survey qwen3-coder 173 runs; head Llama-3.3 1,040; AgentDyn SecAlign-8B 94; adprov-v1 135; AgentHarm 12; empty turns in A03 |
| SA08 (p) | provider call-id anomalies: absent, empty, null, repeated; positional links (FA row 14) | AER | C | T01 (safety net) | G*: **dtap has no call ids**: all call-result links are positional (class I); report the share paired by order and the `AATT` batches | head absent 4,690 (Cohere), empty 12,583 (Gemini), null 47,227, repeated 213 logs; ROPE null 8,707; AgentDyn null 15,306; 2024-06 absent 1,469, empty 1,330, repeated 189 |
| SA09 (p) | version and generation drift: package version not a code identity; constant-field screens per source; timestamp windows per arm (FA rows 15, 21, 22; E2 S01 timing) | AER | C | T01 | G* (group by arm; dtap: run timestamp and path-derived model) | head 11,765 and ROPE 2,268 `unknown` package versions; ROPE long-horizon `v1.2.1` against `v1.2.2` (760); AgentDyn DRIFT arm three months later |

Family quirks that have no generic check (FA rows 16-20, 23-25: ROPE tag mislabel, ROPE corrections, CaMeL, DRIFT,
survey gloss, Mandate allows) are screened by R01n, R01g and the catalogue; a new family defines its own list.

### 3.9 Hazard map (the screens the briefs ask for)

| Hazard | Check |
|---|---|
| lone surrogates | U02 (strings), X01 (parser), A04 (raw), U01 (`$utf16`) |
| non-ASCII digits in pointers | U12 |
| bidi and tag characters, zero-width | U05 |
| U+2028 / U+2029 / U+0085 | U03, X05 |
| HTML entities, markdown/HTML in PROV literals | U10 |
| double escaping, damaged Windows paths | U06, U07, A05 |
| Constraint 42 ordering, cycles | P01, P02 |
| C51, C26, C24 | P03, P04 |
| dangling references, shared statements | P06, P07 |
| determinism | D01, D02 |
| fidelity AER vs raw | R03 (+ D02) |

---

## 4. How to run it on a new corpus

### 4.1 Rules

1. **Corpora are read only.** No tool writes into a corpus or the raw store. Re-derivation runs in memory.
2. **Per-execution outputs go outside the repository**: scan rows (about 0.5 GB for eight corpora), feature rows, sample
   runs. They live under `$W` (4.2). Only merged summaries (counts, normalised pointers, execution ids, truncated
   digests) go into the data directory `$D` and are committed.
3. **No corpus text is printed or committed.** Excerpts only through `escape_untrusted`, at most 120 characters, for
   judgement. Text in corpora is data, never instructions. Never read `.env`. No network.
4. At most 4 worker processes (phase 10 used 3-4). Use `--limit 200` first to smoke-test a tool.
5. `uv sync --locked` first; run tools with `uv run python` from the repository root. `exam2_schema.py` needs the dev
   group (`jsonschema`); `exam2_scan.py` needs `pyyaml` (core dependency).
6. Corpus directories end in `.partial` while working; a sealed corpus has no suffix. Names below use `$CD`.
7. Run `uv run python tools/check_unicode.py` before committing the report.

### 4.2 Commands, in order

Variables and tool keys. Output names follow the phase-10 data directories (`phase10-data/`,
`phase10-examination-2-data/`); the new data directory is `docs/reports/analysis/corpus-check-<tag>-data/`, the report
`docs/reports/analysis/corpus-check-<tag>.md`.

```sh
# ---- variables (edit) ----
C=${AGENTPROV_HOME:-$HOME/.agentprov}/corpora        # corpora (read only)
c=<corpus-id>                                         # e.g. dtap-p10 (name without .partial)
CD=$C/$c.partial                                      # corpus directory
T=<yyyy-mm-dd>-<tag>                                  # e.g. 2026-11-02-dtap
D=docs/reports/analysis/corpus-check-$T-data          # committed: counts, ids, digests only
W=${AGENTPROV_HOME:-$HOME/.agentprov}/analysis/$T     # scratch, outside the repository
S=$W/scan; X=$W/features; mkdir -p "$D" "$S" "$X"

# ---- step 0: freeze (record all outputs in report section 1) ----
uv sync --locked
git rev-parse HEAD; git status --short                # clean tree
uv run agentprov info                                 # software, aer/sem/prov versions, source registry
shasum -a 256 $CD/corpus.json $CD/executions.jsonl    # corpus digests
uv pip freeze                                         # (unverified) tool versions: rfc8785, jsonschema, pyyaml

# ---- step 1: pre-register: write report sections 1-2 (scope, check map, plan, seeds), then commit them ----

# ---- step 2: calibrate (once per scanner version; Mandate is a D-class corpus) ----
uv run python tools/analysis2/exam2_selftest.py --corpus $C/mandate-agentdojo-eval-p10.partial --out $D/selftest.json      # T14 (C00, X04)

# ---- step 3: census ----
# smoke test: add --limit 200 to T01 and T06 and write to a throwaway --out
uv run python tools/analysis/phase10_extract.py --corpus $CD --out $X/$c.jsonl --jobs 4                                      # T01 (R01a-R01o)
uv run python tools/analysis2/exam2_reuse.py aggregate $X $c                                                               # T02 (R02; writes $X/summary.json)
uv run python tools/analysis2/exam2_reuse.py compare $X $c > $D/compare.json                                                # T03 (R07a)
uv run python tools/analysis2/exam2_reuse.py rules $X $c > $D/ruleclasses.json                                              # T04 (R07b)
uv run python tools/analysis/phase10_register.py $CD > $D/register-$c.txt                                                   # T05 (R04)
uv run python tools/analysis2/exam2_scan.py --corpus $CD --out $S/$c.jsonl --jobs 4                                          # T06 (X01-X03, X05, U01-U14, A01-A03, A05, P01-P11)
uv run python tools/analysis2/exam2_merge.py --scan-dir $S --out-dir $D $c                                                   # T06b (scan-$c.json, p07-shared-statements.json)
uv run python tools/analysis2/exam2_peek.py $S/$c.jsonl                                                                      # quick counts (optional)
uv run python tools/analysis2/exam2_schema.py --corpus $CD --out $D/x06-schema-$c.json --jobs 4                              # T07 (X06; add --every N only if stated)
uv run python tools/analysis2/exam2_p06view.py --corpus $CD --out $D/p06-view-$c.json --jobs 4                               # T08 (P06)
uv run python tools/analysis2/exam2_corpusfiles.py --corpus $CD --out $D/corpusfiles.json                                    # T09 (X01, X02, X05 corpus files; A04)
uv run python tools/analysis2/exam2_pathgrep.py --out $D/u14-machine-paths.json $CD                                          # T10 (U14)
uv run python tools/analysis2/exam2_overlap.py --out $D/q045-overlap.json $CD <other corpus dirs in the same directory>       # T11 (G02)
uv run python tools/analysis2/exam2_pairdiff.py --a <dirA> --b <dirB> --n 200 --out $D/q045-pairdiff.json                    # T11b (G02, only if overlap is non-empty)
uv run python tools/analysis/phase10_crosscheck.py --corpus $CD --sample 0 --jobs 4 > $D/crosscheck-$c.json                  # T15 (R03; TraceLogger family only)
uv run python tools/analysis/phase10_probe_markers.py --corpus $CD --features $X/$c.jsonl --limit 100000 > $D/probe-$c.json  # T16 (SA04: attack successes with no present marker; --limit above the number selected)
uv run python tools/analysis/phase10_probe_markers.py --corpus $CD --features $X/$c.jsonl --all-attacked > $D/probe-all-$c.json  # T16 (A05: every attacked execution, summary)
uv run python tools/analysis/phase10_marker_cause.py --corpus $CD --from-probe $D/probe-all-$c.json                           # T16b (A05 cause; AutoDojo escape)
uv run python tools/analysis2/exam2_b1check.py --corpus $CD --out $D/a05-b1-$c.json --jobs 4                                 # T16c (A05)
uv run python tools/analysis2/exam2_markers2.py --corpus $CD --scan $S/$c.jsonl --out $D/a05-attribution-$c.json            # T16d (A05; add --show N for escaped excerpts)
uv run python tools/analysis/phase10_dups.py $X/$c.jsonl > $D/dups-$c.json                                                   # T17 (R05)
uv run python tools/analysis2/exam2_dups_utility.py $X/$c.jsonl > $D/r05-dups-utility-$c.json                                # T17b (R05)
uv run python tools/analysis2/exam2_piguard.py --corpus $CD --out $D/s01-piguard.json --jobs 4                               # T18 (S01; only with defence arms)
uv run python tools/analysis2/exam2_bymodel.py $S/$c.jsonl > $D/u06-bymodel.json                                             # T20 (U06 by model)

# ---- step 4: samples ----
uv run python tools/analysis2/exam2_determinism.py sample --corpora $CD --out $D/d01-sample.json                              # T13 (default: 150 and 50 per corpus, seed 20261011)
uv run python tools/analysis2/exam2_determinism.py run --sample $D/d01-sample.json --outdir $S/d01                            # T13: six configurations, then the D02 re-map
uv run python tools/analysis2/exam2_detsum.py $S/d01 > $D/d01-d02-determinism.json                                           # T13: summary with bounds
uv run python tools/analysis2/exam2_judge.py --corpus $CD --scan $S/$c.jsonl --key '<PATTERN|kind|pointer>' --n 20 --field args  # T19 (judgement sample; prints escaped excerpts)

# ---- step 5: regenerated corpora only ----
uv run python tools/analysis2/exam2_p9diff.py --old <previous corpus dir> --new $CD --out $D/p9diff-$c.json --jobs 4          # T12 (G01)

# ---- import-time reports (normally produced by the import session; docs/reports/<source>/) ----
uv run python tools/import_report.py --corpus $CD --summary <import summary.json> --out docs/reports/<source>/import-cli-<name>.json   # T21 (IM01; summary from `agentprov import --summary-json`)
uv run python tools/sem/sem_import_report.py --corpus $CD --out docs/reports/sem/import-<name>.json                          # T21 (IM02; optional --compare <corpus>)
uv run python tools/agentdojo/profile_census.py --profile <profile> --part <part> --out <report.json>                        # T21 (IM03; needs the pinned fetch cache, AgentDojo family)
uv run python tools/agentdojo/source_checks.py --source mandate --corpus $CD --out <checks.json>                             # T21 (IM04; also --source survey)
uv run python tools/agentdojo/sem_unknown_tools.py --corpus $CD --out <report.json>                                           # R01i (AgentDyn suites gap)
uv run python tools/agentdojo/rope_report.py --corpus $CD --out <report.json>                                                 # R01n (ROPE only)

# ---- step 8: finish ----
uv run python tools/check_unicode.py
git add docs/reports/analysis/corpus-check-$T.md $D && git status --short && git commit    # no scratch outputs
```

`exam2_determinism.py` starts its children with only `PATH`, `HOME` and `AGENTPROV_HOME` inherited, plus the matrix
values of 4.3.

Verification of this block: seven tools were checked with `--help` (`phase10_extract`, `phase10_crosscheck`,
`exam2_scan`, `exam2_determinism`, `import_report`, `source_checks`, `sem_import_report`) and the rest by reading their
argument handling (argparse blocks or `sys.argv` use); none was run against a corpus. Marked "(unverified)": `uv pip
freeze`. The D01 frame in the code is executions with `stages.aer = ok` (the pre-registration text said
`stages.prov`); the code governs.

Commands that the CLAUDE.md pipeline lists but this tree does not provide yet (phase 11): `agentprov derive`,
`agentprov recompute --check`, `agentprov verify --level chain`, `agentprov package`, and `agentprov validate --corpus`
(`validate --help` says "not implemented in this build"). Until they merge, R01a stands in for `verify --level chain`
and D01 for `recompute --check`. Add them to step 3 when available (unverified).

Expected runtime, as recorded: T01 about 45 minutes for the five FA corpora (89,390 executions, 4 workers each,
sequentially). A4 estimated "a few CPU-hours single-core" for a 126,000-execution string scan (an estimate, not a
measurement). No other runtime was recorded in the reports; time the first run and add it here.
Recorded 2026-10-12 (`dtap-sample-check.md`, a shared M2 Max): DTap sample of 501 executions, import 897 s with 4
workers, D01 over all 499 executions with PROV 688 s; every other tool under a few minutes.

### 4.3 Environment matrix of D01 (fixed by `exam2_determinism.py`)

| Config | TZ | locale | PYTHONHASHSEED | PYTHONUTF8 | workers |
|---|---|---|---|---|---:|
| c0 | UTC | C.UTF-8 | 0 | 1 | 1 |
| c1 | Pacific/Auckland | en_US.UTF-8 | 1 | 1 | 1 |
| c2 | America/St_Johns | tr_TR.UTF-8 | random | 0 | 1 |
| c3 | Asia/Kolkata | de_DE.UTF-8 | 12345 | 0 | 1 |
| c4 | Europe/London | C | random | 1 | 1 |
| c5 | Australia/Eucla | en_US.UTF-8 | random | 1 | 4 (+ tiers 3-4 re-run) |

D02 (re-map) runs in c0 after the matrix.

### 4.4 Comparing with the baselines

1. **Zero-tolerance checks** (X01-X06, U02, U03, U12, P01-P11, R01a-R01c, R01l, D01, D02, R03): the new corpus must give
   0. A non-zero count is a finding, not a baseline difference.
2. **Descriptive census counts**: compare **rates with denominators** (per execution, per tool result, per attacked
   execution), not absolute counts; the corpora differ in size. Cross-family comparison is descriptive only.
3. **Regenerated corpora**: compare the corpus with its own previous report first (counts must be equal unless the
   batch predicts movement, table below), then run G01 against the previous copy, then compare with the phase-10 rates.
4. **Sampled checks**: report n and the zero-event bound; a smaller n than the baseline (1,305 / 350) weakens the
   statement and must be said.
5. Baseline files to diff (`python -m json.tool --sort-keys` on both, then `diff`):

| Tool | Baseline file(s) in `docs/reports/analysis/` |
|---|---|
| T01/T02/T03/T04 | `phase10-data/summary.json`, `compare.json`, `ruleclasses.json` (5 corpora); `phase10-examination-2-data/reuse-summary-new-corpora.json`, `r07-rule-classes-new-corpora.json`, `reuse-register-new-corpora.json` |
| T06/T06b | `phase10-examination-2-data/scan-<corpus>.json`, `p07-shared-statements.json` |
| T07, T08, T09, T10 | `x06-schema-<corpus>.json`, `p06-view-<corpus>.json`, `corpusfiles.json`, `u14-machine-paths.json` |
| T11, T12 | `q045-overlap.json`, `q045-pairdiff-2024-06-vs-head.json`, `p9diff-<corpus>.json` |
| T13, T14 | `d01-sample.json`, `d01-d02-determinism.json`, `selftest.json` |
| T15, T16 | `phase10-data/crosscheck.txt`, `probe-<corpus>.json`; `r03-crosscheck-2024-06.json`, `a05-b1-<corpus>.json`, `a05-attribution-<corpus>.json` |
| T17, T18 | `r05-dups-utility-new-corpora.json`; `s01-*.json` |

6. **Expected movement under the pending regeneration batch** (`regen-batch.md`; compare before and after):

| Batch item | Checks expected to move |
|---|---|
| 1 (B1 AutoDojo unescape; with 6, 8) | A05 miss class 1,235 executions -> at most the 10 non-AutoDojo long-horizon markers; SA03 ROPE falls; SEM and PROV digests of the ROPE AutoDojo slice; profile digest in every corpus using the profile (G01) |
| 2 (B3 CaMeL) | R01g `unattributed_additional_user_message` 266 -> 0; AgentDyn CaMeL AER/SEM/PROV |
| 3 (B6, C6 twins) | R01f ROPE 322 and AgentDyn 826 `known_incomplete` -> `unverifiable`; R07b D citations on unverified code -> 0; the catalogue digest in every PROV (P07) |
| 4, 5, 6 (C1, C2, C3) | assessment claims (SA04); P09 components with attribute links drop by the connected configuration subgraph; A05 gains `partial` status |
| 7 (F-01) | catalogue digest only; U01/U02 stay 0 |
| 9, 11 (index refresh, `missing_tool_result`) | R01f: 232 + 2 vacuous `verified_complete` -> 0; AgentHarm 4 -> `known_incomplete` |
| 10 (validator ordering, C51, C26, cycles) | validation digests of every corpus; P01-P04 now also run by the validator and must agree with the scan (0) |
| 12 (Inspect b3, c3, c4) | P09 AgentHarm orphans (run 1,056, harness 1,056, steps 7,946) fall; 3,710 unattributed parts attributed |

---

## 5. Adapting to a new adapter family (worked example: `dtap`)

### 5.1 What runs unchanged, and what does not

| Group | Checks | Unchanged on a new family? |
|---|---|---|
| Instrument | C00, X04 | yes (point C00 at Mandate) |
| Structure and strings | X01-X03, X05, X06, U01-U14, A01-A04, P01-P11 | yes; they read AER, SEM and PROV only |
| Chain and index | R01a-R01c, R01f, R01g, R01h, R01j, R01l, R04, D01 | yes, if the SEM profile is registered |
| With a caveat | R01d, R01e, R01i, R01k, R01m, R01o, R05, R07b, D02, SA03, SA04, SA06, SA08, SA09 | run, but read the caveat in section 3 (facet names, `m<n>` ids, catalogue, context artefacts, markers and fixtures) |
| Family-specific | A05, R01n, R03, IM03, IM04, S01, G03, SA01, SA02, SA05 | need a new or parameterised piece |
| Cross-corpus | G01, G02, P07 | yes |

Before pre-registering for a family, run a **P1 profile** (A1 P1) on a stratified sample: key-set census per record
kind, type census, cardinality, enumeration domains, size distributions, per source variant (for dtap: per framework).
Rare key sets are the best anomaly detector, and the profile tells you which facets and quirks exist.

### 5.2 DTap-Bench (`dtap` family, phase 10b, D-26)

Facts from the source card (`systematic-search/candidates/dtap-bench.md`): 64,110 trajectory files and 65,902 judge
results over 10 framework/model pairs (benign 23,447 / direct 16,327 / indirect 17,616 / unlabelled 6,720); schema
`{task_info, traj_info, trajectory[]}`; no call ids; no per-step timestamps; tool states may be Python-repr strings;
task configurations are joined per run.

| DTap property | Consequence for the checks | What to write or parameterise (not written now) |
|---|---|---|
| **No call ids; calls and results paired by order** (Claude-SDK runs issue several calls before their results, pattern `AATT`) | link evidence is class I; R01m accounting, R01k cross-checks and SA08 change meaning; R03 must verify the pairing rule, not equality of ids | (1) a `dtap` cross-check (R03 analogue) that re-pairs from the raw steps and compares with the AER links; (2) SA08 reported as "share of links paired by order", counted per framework; (3) check that no result is paired to a call from a later batch |
| **Tool-description injections are unobservable** in the logs (logs hold neither tool descriptions nor system prompts) | A05 and SA03 cannot treat "no marker" as "never reached the agent"; exposure to tool-channel payloads is a class-I inference, never observed | (4) a **channel census**: per execution, the configured injection channels (`environment`, `tool`, `skill`, `prompt`; direct or indirect) from the joined config, and the three-way SA03 (observed / absent / unobservable channel); (5) the two figures the card requires before conversion: indirect tasks with a `type: tool` (or skill, prompt) step, and successful attacks with no observed environment payload; (6) SA04 restricted to executions whose only channels are observable |
| **Payloads are joined from task configs** (pinned `DecodingTrust-Agent-Platform` revision) | fixtures come from the config, not the log; the join must be verified per run (task id, original instruction, malicious instruction against `task_id`, `task_instruction`, `malicious_goal`); a mismatch is disclosed and the config unused | (7) a join check: census of join status, mismatches by framework, and the revision in force at the run timestamp (a stated inference); (8) D02 re-map must rebuild the config blob from `raw/origins.jsonl` (`context_artefacts` globs) or `_remap` must be extended; (9) a config-revision sensitivity table (E2 style) if the history makes it possible |
| **Python-repr tool results** (`{'type': 'text', 'text': '...'}`) | U06, U08, U09 will report very many repr strings and literal escapes: expected, classify by pointer; the A05 literal spellings must include the repr form | (10) add the repr and MCP-wrapper spellings to the A05 `forms()` of the scanner and drop the AutoDojo `yaml_escape` import; (11) the adapter keeps the strings as text and never evaluates them (the scanner's U08 classification parses them in a guarded way, `ast.literal_eval` limited by length, in the analysis only) |
| **Sandbox `env_vars` in task configs must never reach an AER or report** | not covered by U14's secret-shape screen | (12) **DT01 (p)**: take the `env_vars` values of the pinned configs, search every corpus file and every report/data file for them (counts only; values are never printed); expected 0 |
| **Several trajectory files per task (re-runs); judge results without trajectories** | R05 groups are not duplicates if timestamps differ; R04 must account for judge-only files | (13) parameterise R05 labels (framework, model, domain, task path, re-run index); (14) reconcile executions + `select.*` rows with the card's 64,110 and 65,902 (IM04 analogue); (15) A1 Q-063 run-level non-determinism: variance of outcomes over re-runs of one task/model, never treated as independent samples |
| **Model identity from the path only; four frameworks** | D01/D02 strata (profile, issues, completeness, status) do not separate frameworks | (16) add (framework x model) to the stratum key, or run `--per-corpus` large enough for at least 10 per pair; (17) identity check: path-derived model against the card's table |
| **No per-step timestamps; one run timestamp and `duration`** | nothing may be invented | R03 "no record other than the run scope carries a time" and P09 time coverage must be 0 for steps; keep both in the dtap cross-check |
| **Unlabelled runs (6,720; probably browser and desktop domains)** | outcome and exposure notions may not apply | classify in the P1 profile before pre-registering SA rows |

Tools and files to write or parameterise (none exists yet):

| # | Piece | Work |
|---|---|---|
| 1 | `tools/analysis/phase10_extract.py` | make facet extraction table-driven (family facet map); accept non-`m<n>` ids; call the safety net with SEM records (`scan(..., sem_records=)`) |
| 2 | `tools/dtap/dtap_crosscheck.py` | R03 for DTap raw logs: step -> message mapping, role mapping (agent, tool, user), tool name and parameters, state text (string, list or object kept as text), order pairing, `send_message_to_user`, recorded judgements beside, run timestamp and duration verbatim |
| 3 | `tools/dtap/config_join_check.py` | join verification, channel census, config-revision selection, `env_vars` leak (DT01) |
| 4 | `tools/dtap/profile_census.py`, `source_checks.py` | `observed` table of the profile and reconciliation with the card, modelled on the AgentDojo versions |
| 5 | `tools/analysis2/exam2_scan.py` | A05 spellings and channel awareness; remove the hard dependency on the AutoDojo hook |
| 6 | `tools/analysis2/exam2_determinism.py` | stratum key option; context-artefact rebuild for the join |
| 7 | `tools/analysis/phase10_dups.py`, `exam2_dups_utility.py` | label keys and judgement names as arguments |
| 8 | `tools/analysis2/exam2_tables.py` | corpus list from arguments (now a hard-coded list of eight) |
| 9 | `src/agentprov/adapters/dtap/artefacts.toml` | catalogue entries for the dtap findings (proposal text first, 6.3) |

Written 2026-10-12 for the DTap sample check (`dtap-sample-check.md`): `tools/dtap/dtap_check.py` (DT01-DT13: the R03
analogue, pairing, join, quality decisions, markers and exposure, time, semantics, `env_vars`, inventory; items 2, 3 and
4's applies-check), `tools/dtap/dtap_remap.py` (D02 for DTap: item 6's re-map part), `tools/dtap/dtap_calibrate.py`
(fault injection for the DT checks). Items 1, 5, 7 and 8 stay open (the DT checks read DTap directly).

---

## 6. Reporting template

### 6.1 Report skeleton (`corpus-check-<tag>.md`)

Sections 1 and 2 are committed **before** any new check runs.

| Section | Content |
|---|---|
| header | date, analyst, code commit(s), "no file under `src/` changed", corpora derived on which commit |
| 0 Summary | written last: what is clean, what is new, proposed fixes ranked, new manuscript artefacts, not done |
| 1 Method | 1.1 scope and population (table of corpora: source, part, profile, executions, new or in a previous report); units; read-only discipline. 1.2 phases. 1.3 finding classes. 1.4 census and sampling plan (table with n, seed, interval), thresholds, environment matrix, calibration plan. 1.5 threats to validity |
| 2 Check map | the checks run, with id, origin, status (new, reused, extended), scope; checks not run, with the reason |
| 3 Structural validity | X01-X06 with the calibration result (C00, X04) first |
| 4 String content and AER semantics | U01-U14, A01-A05 with attribution of every hit |
| 5 Integrity, index and accounting | R01a-R01o, R04, R05, R07 |
| 6 PROV | P01-P11 per corpus; orphan and degree tables |
| 7 Determinism and fidelity | D01, D02, R03 |
| 8 Cross-corpus and regeneration | G01, G02, G03, S01 |
| 9 Findings, classified | 9.1 (b) table: `# / Finding / Where (file:line) / Proposed fix / Spec / Digest and corpus impact / Risk`, ranked by impact; 9.2 (c) questions with the evidence and a recommendation; 9.3 (d) analysis artefacts; 9.4 (a) correct and disclosed |
| 10 Manuscript artefacts | 10.1 table (6.2); 10.2 proposed `artefacts.toml` entries (text only) |
| 11 Delta against baselines | table: check id / baseline value / now / explained by (a regen item, a corpus difference, a finding) |
| 12 Threats to validity and reproducibility | environment (CPython, OS, `uv.lock` hash, `rfc8785`, `jsonschema`, `pyyaml`), seeds, the full command list, which result files are committed, what was not re-run (Q-071) |

### 6.2 Manuscript-artefact table (same columns as FA 8.1)

| # | Artefact | Sources and counts (examples) | Catalogued | Class | Effect on metrics | Recommended disclosure |
|---|---|---|---|---|---|---|
| n | short name | per corpus count with a few example execution ids | `artefacts.toml` id, a profile quirk (`q:...`), or "new" | CR, DR, RJ, FO or NR (D.15.1; NR as in "not recoverable") | which statistic is biased and in which direction | the sentence for the datasheet or manuscript |

Rows are executions unless a column says otherwise; a row also names its denominator. First-analysis rows 1-25 and
E2 rows N1-N8 are the numbering to continue (a new row is the next free `N<k>`; extended rows are listed after the
table, as E2 does).

### 6.3 Where findings go

| Finding | Goes to | Format |
|---|---|---|
| (b) that changes AER, SEM, PROV, index, validation or manifest bytes | `regen-batch.md`, appended as a numbered row; applied only after the user approves the list | `\| # \| Item \| Source \| Changes \| Notes \|` (Changes = which digests and how many executions) |
| (b) that changes no corpus bytes | the report (9.1); applied on a branch only with the user's go-ahead (1.2); then marked "Done" with the commit | |
| (c) decided by the user | the report 9.2 with date; consequences into `regen-batch.md` or `datasheet-items.md` | |
| Datasheet statement | `datasheet-items.md` | `\| # \| Item \| Corpus \| Decided \| Source \|` |
| (a) source artefact for the manuscript | report 10.1; an `artefacts.toml` proposal in report 10.2 (`[[artefact]]` with `id` `<ns>.art.<name>`, `title`, `description`, `scope`, `cause`, `detector`, `claims`, `recorded_as`, `handling` (class and rule), `expected` with counts and `status = "verified"`, `manuscript`, `refs`) | proposals are text only; the file in `src/agentprov/adapters/<family>/artefacts.toml` is edited after approval; entries change no AER/SEM/PROV/`corpus.json` byte |
| (d) analysis artefact | the report 9.3, and the tool is fixed (a note in section 2.4 if it is a trap other analysts could hit) | |
| Decision with a rejected alternative | AGENTS.md and `docs/architecture/DECISIONS.md` (D-nn) | |

---

## 7. Known gaps

### 7.1 Not done in the phase-10 analyses (E2 "Not done")

| Gap | Why | What closes it |
|---|---|---|
| SEM JSON-Schema validation | no published SEM schema | publish `sem-0.1.schema.json`, then add an X06 analogue |
| external PROV-CONSTRAINTS validator (A1 Q-024; A3 s3) | ProvToolbox / `prov-check` not installed, no network | run ProvToolbox on a stratified sample and the 280 W3C test cases; vendor the `ordering-*` cases as fixtures |
| MinHash near-duplicates (A1 Q-044) | exact duplicates only (R05) | shingled message/tool sequence + MinHash/LSH with a threshold set on a labelled pilot |
| double-annotated label audit (A1 Q-062) | single analyst | second rater on a stratified overlap (10-20%), kappa or alpha with prevalence |
| D02 for AgentHarm (and other container-dialect units) | Inspect `.eval` units come from a container plan the tool does not replay | a replay path for container units |
| a second full run for byte-identical result files (A1 Q-071) | not re-run within the session | run the tools twice in clean environments and compare digests of the result files |

### 7.2 Further gaps found while writing this protocol

| Gap | Note |
|---|---|
| raw -> AER -> regenerated source view (A2 P0 item 1) | D02 covers raw -> AER and R03 covers messages; no census regenerates the `transcript/v1` view from the AER and compares it with the source bytes (byte-exactness is gated by the golden tests, per CLAUDE.md) |
| Q-051 provenance completeness per AER record kind | R01k checks messages, parts, model calls, tool executions and decisions as reported; there is no census that every other record kind maps to a statement or is declared "no statement" |
| P07 across corpora | the per-execution scan files that carry the shared-statement digests (about 0.5 GB) are not committed, so a new corpus can be compared with the phase-10 corpora only by re-scanning them |
| A2 part C code audits (silent-failure grep, locale/encoding grep, test-oracle audit, mutation score) | code audits, not corpus checks; not part of this protocol |
| `agentprov verify`, `recompute`, `derive`, `package`, `validate --corpus` | phase 11; until then R01a and D01 stand in |
| ~~the extractor does not run the `payload_not_reaching_agent` detector~~ **fixed 2026-10-11** | `phase10_extract.py` now passes the execution's verified SEM records to `scan` (field `artefacts_sem_used`); the detector fires on every attacked run whose markers are all `absent` (checked on 400 ROPE executions: 57 of 57) |
| `run_phase10_extract.sh` | fixed to five corpus ids; call T01 directly |
| analysis-time knowledge | the C5 manual check (G03) and the judgement of string hits are manual and cannot be re-run unattended |

### 7.3 Tools hard-coded to the phase-10 corpora or to one family

| Tool | Hard-coded | Workaround now |
|---|---|---|
| `phase10_aggregate.py`, `phase10_compare.py`, `phase10_rule_classes.py` | module constant `CORPORA` (five corpus ids); `phase10_rule_classes.py` reads only `adapters/agentdojo/rules/` | `exam2_reuse.py aggregate\|compare\|rules` replaces the constant; its `rules` mode reads every family |
| `run_phase10_extract.sh` | five corpus ids | call `phase10_extract.py` |
| `exam2_tables.py` | list of eight corpus names and short names | edit the list, or read the `scan-<corpus>.json` files directly |
| `phase10_extract.py` | AgentDojo/ROPE/AutoDojo facets (`ext.agentdojo`, `ext.rope`, `ext.autodojo`); `m<n>` message ids; safety net without SEM records | see 5.2 (1) |
| `phase10_crosscheck.py` | the TraceLogger raw format | write a family cross-check |
| `phase10_probe_markers.py`, `phase10_marker_cause.py`, `exam2_b1check.py` | AutoDojo `_yaml_escape` and the AgentDojo marker module | AutoDojo/ROPE only |
| `exam2_scan.py` | A05 imports the AutoDojo `yaml_escape`; otherwise AER/SEM/PROV generic | see 5.2 (5) |
| `exam2_piguard*.py` | AgentDyn arm names (`DETECTORS` in `exam2_piguard4.py`) and the cell key | defence-arm corpora of the same benchmark only |
| `phase10_dups.py`, `exam2_dups_utility.py` | label keys and the judgement names `utility`, `security` | see 5.2 (7) |
| `exam2_determinism.py` | skips profiles starting `survey-agentharm` in D02; strata key; ubiquitous-issue set | see 5.2 (6) |
| `exam2_overlap.py` | corpora in one parent directory | keep them together |
| `exam2_pathgrep.py` | the current account's home and temp prefixes | run on the machine that imported |
| `tools/agentdojo/{profile_census,source_checks,rope_report,sem_unknown_tools}.py` | AgentDojo family, ROPE, Mandate, survey, AgentDyn suites | a per-family counterpart |

---

## 8. Version 2: the pre-check checks (L1, L2, outcome sanity)

Method and pre-registration: `docs/reports/precheck/README.md` (sections 1-8, with dated amendments). Per corpus:
pre-registration `docs/reports/precheck/prereg/<corpus_id>.md`, desk research `data/<corpus_id>/research.json`, dossier
`docs/reports/precheck/<corpus_id>.md`; all corpora: `summary.md`, `summary.json`. Tools: `tools/precheck/` (tests in
`tests/unit/precheck/`, incl. the 45-class fault-injection calibration `test_l1_calibration.py`).

### 8.1 Checks added

| ID | Detects | Layer | C/S | Tool |
|---|---|---|---|---|
| L1-01 | files, members and units against the census and the registry; selected / not selected by the profile (reason) / owned elsewhere / other variant part | raw | C | `l1_scan.py` |
| L1-02 | strict parse through `agentprov.ingest`: duplicate key, non-finite, big int, lone surrogate, BOM, trailing data, invalid UTF-8, truncated, too deep, too large, empty (every class only with `--lenient-classes`, opt-in) | raw | C | `l1_scan.py` |
| L1-03 | encodings and escaping in decoded strings (A4): U+2028/2029/0085, C0/C1, ESC, bidi, tag, zero-width, variation selectors, PUA, U+FFFD, mojibake, literal escape residues, JSON-in-string | raw | C | `l1_scan.py` |
| L1-04 | byte-identical files and identical trajectories (family fingerprint over the normalised message/step list), within a part, across parts and across corpora (C5) | raw | C | `l1_scan.py --emit-fp`, `l1_xdup.py` |
| L1-05 | arm coverage (family facets) against the paper's design: missing and extra cells | raw | C | `l1_scan.py` summary `strata` |
| L1-06 | secret-like shapes, account paths (named, generic), operator home, `[withhold]` rule matches, local-path model ids: counts and normalised pointers only | raw | C | `l1_scan.py` |
| L1-07 | timestamps by pointer: presence, parse failures, time-zone forms, monotonicity within a unit, range (dates only) | raw | C | `l1_scan.py` |
| L1-08 | degenerate artefacts: empty, zero messages, error-only, unterminated, tiny | raw | C | `l1_scan.py` |
| L1-09 | OS-metadata members of the raw input (orchestrator request 2026-10-15): AppleDouble `._*` basenames, `__MACOSX/` segments, `.DS_Store`, other OS files; per class walked / include-glob match (expanded and stored by an import although never mapped) / not selected / rejected, and the importer's final disposition (`stray`) | raw | C | `l1_appledouble.py` (plan key `l1_09 = true`) |
| L2-S | deterministic stratified sample (seed 20261011, about 5 per stratum, 30-300; more than 300 strata: 1 each) | raw | S | `l2_sample.py` |
| L2-I | scratch import of exactly the sampled labels at `--jobs 2` and `--jobs 1` (selection guard: exit 3 unless the kept candidates equal the sample) | AER, SEM, PROV | S | `l2_import.py` |
| L2-C | validate (all tiers), `recompute --dry-run` (under the selection shim), determinism j2 vs j1 (bytes, index), A2 classes, A3 PI classes, evidence classes (D/I/O, `_unverified`), degenerate and `adapter_defect`, issue codes, identity vs L1 facets, redaction (account paths and secret shapes in AER/SEM/PROV/index), withholding plan | AER, SEM, PROV, index | S | `l2_check.py` |
| OS-1 | outcome sanity, population: raw outcome fields per arm (L1 rows) against the paper (gap rule of README section 4) | raw | C | dossier (examiner) |
| OS-2 | outcome sanity, sample: mapped AER outcomes against the raw values of the same labels (mapping) and the paper | AER | S | dossier (examiner) |
| DL-1 | delta of an already-imported part: fresh scratch import at current `main` against the stored corpus on the same execution ids, every differing pointer attributed to a regen item, decision or bump | AER, SEM, PROV | S | examiner (+ `exam2_p9diff.py` where it fits) |

### 8.2 Commands

`W=~/.agentprov/migration-work/precheck`, `C` corpus id, `S` source, `P` part; inputs per part are in
`tools/precheck/plans/wave<n>.toml` (the exact `l1` arguments: `--use-pin`, `--git <staging bare clone>`, or `--input
<staged tree or archive>`, plus `--lfs-dir`, `--nested-cap`, `--pin-check` where needed).

```sh
# one queued job per wave runs every step below for every part of the plan (resumable; logs in $W/_batch/wave<n>/)
uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib <4|6|8> --label precheck-wave<n> -- \
    uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/wave<n>.toml
# the steps it runs, per part
uv run python tools/precheck/l1_scan.py --source S --part P --corpus-id C --jobs 2 --emit-fp <l1 args>
uv run python tools/precheck/l2_sample.py select --units $W/C/l1-units-P.jsonl --source S --part P --corpus-id C \
    --out docs/reports/precheck/data/C/l2-sample-P.json [<sample args>]
uv run python tools/precheck/l2_import.py --sample docs/reports/precheck/data/C/l2-sample-P.json --corpus $W/C/l2-P-j2 \
    --source S --part P --jobs 2 [<import args>]
uv run python tools/precheck/l2_import.py --sample ... --corpus $W/C/l2-P-j1 --source S --part P --jobs 1
uv run python tools/precheck/l2_check.py --corpus $W/C/l2-P-j2.partial --out docs/reports/precheck/data/C/l2-P.json \
    --sample docs/reports/precheck/data/C/l2-sample-P.json --l1-units $W/C/l1-units-P.jsonl --compare-with $W/C/l2-P-j1.partial --jobs 2
uv run python tools/precheck/l1_appledouble.py --source S --part P --corpus-id C <l1 args>   # L1-09, archive inputs
# after the L1 of every part
uv run python tools/precheck/l1_xdup.py            # docs/reports/precheck/data/_cross/l1-xdup.json
# sealed-copy withholding (git/local trees with [withhold] only; needs a clean committed producer tree)
uv run python tools/precheck/l2_import.py --sample ... --corpus $W/C/l2-P-prune --source S --part P --jobs 2 --strategy prune --mode release
uv run python tools/precheck/l2_check.py --corpus $W/C/l2-P-prune.partial --out $W/C/l2-P-seal.json --sample ... --seal
```

The **post-check reuses the committed sample files unchanged** (`l2-sample-<part>.json`); it never re-draws (the draw
depends on the Python version's `random.sample`).

### 8.3 Comparing the post-check with the pre-check

1. L1 is on raw bytes: every L1 count must be identical after the round (the raw does not change). A difference is an
   analysis-artefact (tool change) or a staging change; it is never explained by the round.
2. L2: compare per part `l2-<part>.json` before and after; expected movement is the regen batch's (section 4.4 item 6
   and `regen-batch.md`). Findings marked `mapping-defect` in the pre-check must have moved as their fix predicts.
3. **Stored corpora and `validate --corpus`:** before the round, the 8 stored corpora give `validate.results.differ`
   because their validation rows predate the four `pv.constraints.*` checks of regen item 10 (every row passes them).
   Compare a re-validated stored corpus with a fresh scratch import, never a pre-item-10 stored row with a fresh one.
4. Outcome rates (OS-1) are raw-level and must not move; OS-2 may move only where a mapping defect was fixed.

### 8.3a Post-check commands (2026-10-23; docs/reports/postcheck/)

```bash
uv run python tools/precheck/run_postcheck.py --list                              # every step's command
uv run python tools/suite_queue.py --class import --cpu 4 --mem-gib 8 --run-timeout 0 --label postcheck-round1 -- \
    uv run python tools/precheck/run_postcheck.py                                # rg1 against p10, 8 corpora
uv run python tools/precheck/run_postcheck.py --variant ID:NEW:OLD --steps raw,ids,seal,l2_rg1,sample_rg1,verify,dryrun,validate,scan,tie,dispatch
uv run python tools/precheck/post_check.py triage --corpus C --suites DIR --gitleaks $(which gitleaks) --out O
uv run python tools/precheck/post_check.py oracle --corpus C --release <AgentDojo-PROV release tree> --out O
uv run python tools/precheck/postcheck_compare.py --all [--variant ID:NEW:OLD]   # data/<tree>/exam.json
uv run python tools/precheck/postcheck_report.py [--check]                       # dossiers, findings.json, summary
```

Read-only on every corpus: `post_check.py` refuses any other input and any output inside `corpora/`. The seal forecast
calls `package`'s own pre-seal checks and writes nothing. Traps found by the post-check:

- `l2_check`'s A3 `unexecuted` class reads the core bundle only. After D-80 addendum (d) (item 103), `NotDispatched` sits
  in an inference-bundle mention. Use `post_check.py dispatch`.
- Inspect `.eval` headers are raw JSON inside archives. Screen `eval.dataset.location`.
- A tie re-import must use the tree's import mode.
- A fetched git-pin tree registers only files inside the pin's subtree, while an `--input` clone registers excludes
  anywhere (POST-agentdyn-a-01).
- Run long batches with `--run-timeout 0`.

### 8.4 Analysis traps (version 2)

8. `ImportFilters.include_paths` ANDs its globs (`importer.py`, `discover`): a list of sampled labels selects nothing.
   `l2_import.py` passes one any-of glob through a process-local shim of `importer._match` and guards the kept set;
   a plain `agentprov recompute` or `verify --level rederive` of such a scratch corpus therefore selects nothing
   (`l2_check.py` runs `recompute --dry-run` under the shim; `rederive` is not wrapped). D-529 `import --sample` removes this.
9. Sealed copies: `agentprov package` refuses a partial corpus, a dev-mode validation and a dirty producer tree, so the
   withholding check on archive inputs is a plan only (prune works on git and local trees). `--strategy prune` repeats
   until the reader's candidates are exactly the sample (DTap promotes a directory's judge file once its trajectories are
   dropped; one round kept 66,026 candidates for a 5-label sample) and stops before mapping when a sampled unit's own
   inputs (`auxiliary_for`) would change. Then use `any-glob`, which cannot be sealed. `--seal` takes the scratch spec's
   snapshot origins from the product's pin derivation (D-33; `package.snapshot_pin_object_origins`, PR-2's exclusion of
   the recorded pinned objects included) and writes a card that passes the card lint (H.9(3), H.9(5)). It then runs
   `verify --release` with the root digest `package` prints on stderr. Prune passes on only the sampled labels' R3
   pinned objects, and the DTap tasks context tree records its pin (D-530).
   The kexin local-path-model guard applies only while the resolved profile redacts no model id (profile v1). Profile v2
   (item 107 with D-604) skips it, and the import summary records the redaction rule ids.
10. Multi-execution artefacts (Inspect `.eval`, credleak cells, AutoGen `runs.jsonl`, MCPHunt documents): the sample unit
    is the file or member until D-529; a part with fewer than 30 such units is imported whole.
11. Scenario fiction (e.g. `/home/user`, `/home/ubuntu` in sandboxes, a fictional `/Users/<name>` in a benchmark scenario)
    matches the account-path screen: read the pointer before calling it a leak; the operator's own home path is a
    separate class (`operator_home`).

### 8.5 Added after wave 2 (2026-10-15)

| ID | Detects | Layer | C/S | Tool |
|---|---|---|---|---|
| L1-10 | secret shapes, account paths (named vs generic, distinct accounts as digests) and the operator's home in the raw-store files L1-06 does not scan: context, blob and auxiliary files that are not JSON/JSONL (READMEs, scripts, configs, manifests) | raw | C | `l1_context.py` (batch step `l1_10`) |
| L1-08b | `trailing_calls`: the log ends on an assistant turn whose tool calls have no result | raw | C | `l1_families.py` flag |

The `l2_check` `_unverified` split is statement level (CC-08): an `apv:basisRule` ref, else the decoded inference-bundle
method set (`xd:bundle.inf.<ns>-<name>-v<n>[--...].<hash>`); twin = restates a catalogued D rule; native = class-I rule
whose id ends in `_unverified`; mixed = both. Counters: `unverified_twin_by_bundle_class`,
`native_unverified_rule_by_bundle_class`, `mixed_twin_and_native_by_bundle_class`.
