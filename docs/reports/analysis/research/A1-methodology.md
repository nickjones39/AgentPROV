# A1. Methodology for examining the data quality of the AgentPROV corpora

Research brief, 2026-10-11. Web research only; the repository was read for context and not modified.
Scope: 8 corpora, about 126,000 executions, 10^6 to 10^7 records; artefacts raw -> AER (`aer/0.1`, JCS JSONL, sha256
chains) -> SEM (JSONL) -> PROV-JSON bundles (core / inference / assessment) -> validation results -> hash-chained
corpus (`executions.jsonl`, `register.jsonl`, manifest, `checksums.sha256`).

Conventions. Citations are bracketed source ids, e.g. [S12]; full URLs are in section 9. Each source carries a
verification status: F = page fetched and read in this session; S = only search-result abstract or snippet seen;
K = cited from background knowledge, URL not opened. Treat S and K entries as "confirm before quoting numbers".
Items marked "(synthesis)" are my own methodological proposals, not claims from a source. Web pages were treated as
data; nothing in them was followed as an instruction.

Relation to existing work. The repository already has `docs/reports/analysis/phase10-corpus-analysis.md`
(integrity, seal issues and evidence quality, graph quality, end-to-end fidelity, cross-source consistency,
classified findings, source-artefact table). This brief supplies the methodological frame and citations for that
kind of analysis, and proposes check IDs that can be mapped onto it.

---

## 1. Summary of the approach

1. Do a **census, not a sample**, for everything that can be computed mechanically over the 126k executions
   (structure, digests, constraints, graph metrics). Sample only for judgement-based questions (is this label
   right? is this mapping faithful?), and then use stratified, pre-registered samples with exact or Wilson
   intervals (section 6).
2. Organise checks by **named data-quality dimensions** so that findings are comparable with the literature
   (ISO/IEC 25012 / 25024, Wang and Strong, DAMA six dimensions) [S1][S2][S3][S4][S5], and add the dimensions
   that are specific to provenance (correctness, completeness, relevance of provenance, per Cheah and Plale) [S30].
3. Separate **"is the data well-formed?" from "is the data true?"**. Validity (conforms to schema and rules) is not
   accuracy (matches the world) [S5][S6]. Most of what a software pipeline can verify is validity, consistency,
   uniqueness and integrity. Accuracy of the *source* (was the benchmark label right, did the harness score
   correctly) can only be bounded, using audits and cross-evidence, never established by the pipeline alone [S19][S20][S21].
4. Make every finding **attributable**: source-data property (present in the raw bytes), processing defect
   (introduced by a reader, mapper, derivation or validator), analysis artefact (introduced by the audit tool),
   or undetermined. Attribution is done by differential and metamorphic tests plus tracing to raw bytes
   (section 3, P6; section 7).
5. Report as a **reproducible audit**: pinned versions, deterministic scripts, recorded commands, result digests,
   explicit denominators, threats to validity [S33][S34][S35].

---

## 2. Data-quality frameworks and how they map to these corpora

### 2.1 Frameworks (what each contributes)

| Framework | What it gives | Use here |
|---|---|---|
| ISO/IEC 25012:2008 data quality model [S1] | 15 characteristics, in "inherent" (accuracy, completeness, consistency, credibility, currentness), "system dependent" (availability, portability, recoverability) and both (accessibility, compliance, confidentiality, efficiency, precision, traceability, understandability) views. The grouping is as summarised by secondary sources; confirm against the standard's table [S1]. | Vocabulary for dimensions. Traceability and compliance are directly relevant to a provenance corpus. |
| ISO/IEC 25024:2015 [S2] | Quality *measures* for each 25012 characteristic, built from "measure elements" (counts of records, data items, values); defines no pass thresholds, which each system sets from its context [S2]. Example measure: number of outlier values divided by number of values considered. | Justifies reporting every metric as a ratio with explicit numerator and denominator, and setting thresholds per corpus in advance. |
| Wang and Strong 1996 [S3] | Consumer-derived hierarchy: intrinsic, contextual, representational, accessibility categories (15 dimensions). | The "fitness for use by researchers" lens: a corpus is good relative to the research question (thesis claims), not in the abstract. |
| DAMA UK six dimensions, 2013 [S4]; UK Government Data Quality Framework [S5] | Completeness, uniqueness, timeliness, validity, accuracy, consistency, each with a typical test. Secondary sources stress validity (format/rule conformance) differs from accuracy (real-world correctness), and consistency does not imply accuracy. | The primary operational grid for the checklist (section 4). |
| Pipino, Lee and Wang 2002 [S6] | Combines subjective and objective assessment; objective metrics as simple ratios and as min/max aggregations over variables. I could confirm only the citation, not the formulas [S6]. | Pattern for reporting: ratio metrics per dimension, aggregation by "weakest link" (min) rather than averaging. |
| Linked-data quality survey (Zaveri et al. 2016) [S7]; SHACL-based quality measurement [S8] | 18 dimensions and 69 metrics for RDF/linked data; a 2025 arXiv paper expresses those 69 metrics as SHACL shapes. | Source of graph-level metric names; precedent for expressing quality checks declaratively. |
| Provenance quality (Cheah and Plale 2012) [S30]; Hartig and Zhao 2009 [S31] | Provenance quality as correctness, completeness and relevance at node/edge, graph and multi-graph levels (as summarised in the search abstract). Provenance can be used to assess data quality and must cope with missing provenance [S31]. | Dimensions for the PROV layer; "provenance of provenance" (evidence classes, seal issues) fits Hartig and Zhao's "handle missing provenance". |
| FAIR principles [S9] | Findable, Accessible, Interoperable, Reusable. Not a quality framework as such. | Frame for the release/package layer (manifest, identifiers, licences), not for record-level quality. |
| Datasheets for Datasets [S10]; Dataset Nutrition Label [S11]; Data Statements [S12] | Documentation of motivation, composition, collection, preprocessing, uses, maintenance. | The reporting skeleton for per-corpus summaries (section 7). AgentPROV already ships a datasheet generator. |
| Data cascades (Sambasivan et al. 2021) [S13] | Interviews with 53 practitioners; reports data problems cascade downstream and are often invisible and delayed. | Motivation: record-level defects propagate AER -> SEM -> PROV -> statistics; check at each stage and propagate defect flags downstream. |
| ML data validation (Breck et al. 2019, TFX) [S14]; Deequ (Schelter et al. 2018) [S15] | Schema-based anomaly detection per batch, data "unit tests", constraint suggestion, incremental metric computation. | Design pattern: declare constraints once, compute metrics in one scan, store metrics per run so drift is comparable across corpora and across re-imports. |

### 2.2 Dimension -> operationalisation for these corpora

(synthesis; the dimension names come from [S1]-[S5], the operationalisations are mine.)

| Dimension | Operational question for AgentPROV | Typical measurable |
|---|---|---|
| Validity (syntactic and schema) | Does every artefact parse strictly and conform to its declared format? | Share of lines that fail strict JSON; share of records failing the closed `aer/0.1` / `sem/0.1` schemas; JCS idempotence rate. |
| Completeness | Is every required value present, and is every source fact accounted for? | Required-field null/absent rate by record kind; AER accounting residual (raw facts not mapped / mapped not in raw); share of statements with rule+evidence pointer. Completeness is relative to a stated scope and closed-world assumption [S8][S32]. |
| Consistency | Do records agree with each other and with the rules? | Intra-record invariants; cross-record referential integrity; cross-bundle (core vs inference vs assessment) separation; cross-source agreement on shared tasks. |
| Uniqueness | Is each execution counted once? | Exact-duplicate rate (content digest), near-duplicate rate (shingle/MinHash), duplicate IDs, cross-corpus overlap. |
| Accuracy | Does the representation match what happened? | AER vs raw end-to-end fidelity (a *processing* accuracy); source accuracy (labels, scores, timestamps) is only bounded, by audit samples and cross-evidence. |
| Timeliness / currentness | Are time values present, real and in the right order, and are versions current? | Share of executions with real timestamps; naive vs zoned timestamps; monotonicity violations; upstream commit pinned vs observed. Note: no invented timestamps is a project invariant. |
| Traceability / provenance quality | Can each statement be traced to evidence and rule? | Evidence-class distribution; share of `observed` values with source locators; share of `inferred` statements confined to inference bundles. |
| Integrity (system-dependent) | Is the stored data exactly what was sealed? | Digest-chain recomputation pass rate; manifest/checksum agreement; orphan and missing files. Fixity guidance treats generating, logging and *auditing* checksums as separate obligations [S28]. |
| Credibility / believability | Can the content be believed? | Benchmark validity (section 3, P6): known scoring and harness defects in the upstream benchmark [S19][S20][S21]. |

---

## 3. Phased methodology

Every phase produces (a) a metrics table with denominators, (b) a finding list with attribution class (section 7),
(c) a machine-readable result file whose digest is recorded. All phases are read-only against the corpus.

### P0. Scoping and freeze

- Record: corpus ids and versions, `corpus.json` digests, `checksums.sha256` digest, software version axes
  (`agentprov`, `aer/0.1`, `sem/0.1`, `agentprov-prov/0.1`, adapter versions), upstream benchmark commits, tool
  versions, Python version, analysis-code git commit, hardware/OS. This follows the reproducibility rules to record
  how each result was produced, archive exact versions, set and record seeds, and keep raw data behind summaries [S33].
- Declare the **unit of analysis** (execution, record, statement, graph) for every metric, and the denominator.
- Pre-register (in the repo notes, before looking at results) the checks, thresholds and the sampling plan for judgement
  checks. This guards against forking paths (section 6.4).
- Define the **population statement**: the corpora are a census of what was imported, not a random sample of "agent
  executions in general". Statistical inference beyond the corpora needs a stated superpopulation (for example "all
  runs of this benchmark version") [S36].

### P1. Profiling (census, descriptive, no pass/fail yet)

Aim: learn what is actually in the data before writing rules. Profiling output is also the baseline for drift
comparison between corpora and between re-imports [S14][S15].

- Inventory: files, bytes, lines, records per kind, executions per corpus/source/model/suite/attack; reconcile with
  `executions.jsonl` and `register.jsonl` counts.
- **Key-set census** per record kind: the frequency table of distinct key sets (and nested key paths). Rare key
  sets are the most informative anomalies. Parametric schema inference for JSON collections is the established
  technique: infer a type per record, merge equivalent types, and choose precision/conciseness [S16]. For a closed schema
  such as `aer/0.1` the expected result is exactly the declared set; any extra or missing key is a finding.
- **Type census** per field path: JSON type distribution, null / absent / empty string / empty array rates,
  numeric ranges, string length distribution, encoding properties.
- **Cardinality** per field: distinct count, top-k values, singleton share; identifier fields must be unique within
  their scope. High-cardinality alerts are standard in profilers [S18].
- **Enumeration domains**: observed value sets for closed enums (record kinds, evidence classes, rule refs, seal
  issue codes, SEM labels). Values outside the pinned vocabulary are findings; rare in-vocabulary values are screens.
- **Size and shape distributions**: records per execution, bytes per execution, messages, tool calls, statements and
  nodes per graph, token counts, durations. Use robust statistics (median, IQR, MAD, quantiles) and log scales;
  flag by robust z-score or IQR fences, then explain by source/model/suite stratum before calling anything an
  outlier (an outlier is a screen, not a defect) [S2][S19 on inspecting outliers].
- Tooling for P1: DuckDB can read newline-delimited JSON directly and auto-detect types, with `format`,
  `maximum_depth`, `union_by_name` and sample-size controls, which makes census queries one-line SQL [S17].
  Note auto-detection samples records; for the key-set census set it to scan everything, or write the census as a streaming
  pass so no sampling is involved.

### P2. Structural validity (census, pass/fail)

- **Strict parse** of every line: valid UTF-8, valid JSON, no duplicate object keys, no `NaN`/`Infinity`, no lone
  surrogates, number ranges safe for I-JSON; this is the input class JCS requires (JCS builds on I-JSON, RFC 7493, and
  ECMAScript number serialisation) [S27].
- **Schema validation** of AER and SEM records against their JSON Schemas (Draft 2020-12 is the current JSON Schema
  version [S25]); use `iter_errors` to collect *all* errors per record, not the first [S26]. Run an **independent
  validator** in addition to the project's own reader (an N-version or differential check; see P3.5).
- **Canonical form**: re-canonicalise each line with JCS and compare bytes (idempotence); any difference is either a
  writer defect or a hand-edited file [S27].
- **PROV-JSON structure**: prefixes declared, QNames resolvable, statement types known, bundle containment correct,
  identifiers unique within bundle. PROV-JSON is a W3C Member Submission, not a Recommendation, so there is no
  normative conformance suite; use the PROV-DM Recommendation for model semantics [S22][S23].
- **PROV-CONSTRAINTS per bundle**: normalise (definitions, inferences, uniqueness) and check the event-ordering,
  impossibility and typing constraints. The specification names 40+ constraints, from key-object and
  unique-generation through generation-precedes-usage to impossible-specialization-reflexive and
  entity-activity-disjoint. Validity is closer to logical *consistency* than to "truth"; applications MUST check
  all section-6 constraints on the normal form, and SHOULD produce valid provenance [S24]. Report per-constraint
  violation counts, and run each bundle type (core, inference, assessment) separately because assessment/inference
  bundles legitimately contain claims that a combined document would contradict.

### P3. Semantic consistency (census; some checks need rules)

P3.1 Intra-record invariants: end >= start; counts non-negative; role/kind compatibility; evidence class
consistent with the presence of a source locator (observed => locator; derived => rule ref and inputs;
inferred => rule ref and basis).

P3.2 Cross-record referential integrity within and across files: every reference (message, tool call, model call,
blob, defence, fixture) resolves to a record of the right kind in the same execution; no dangling or cyclic
references; ordering fields strictly monotone where specified. In SQL terms: anti-joins on id columns (DuckDB,
or a sort-merge streaming join for 10^7 rows) [S17].

P3.3 Accounting identities: sums that must balance, e.g. tool calls = tool results + declared unmatched; token
totals = sum of per-call usage where both are observed; raw message count = AER message-bearing records + declared
discards. Residuals are findings with a named cause.

P3.4 Time: share of records with real time values; time zone state; monotonicity; plausibility range per source
(future dates, epoch zero, durations beyond a bound); agreement between execution start and first record time.
Never fill gaps; count them.

P3.5 **Differential and metamorphic testing** (attribution tools):
- *Differential*: an independent minimal re-reader of the raw bytes extracts a small set of facts (message count,
  tool-call names/args digest, final answer, utility/security labels); compare with the AER/SEM/PROV values. N-version
  comparison is the standard technique when no oracle exists [S37].
- *Metamorphic*: define relations that must hold without a ground truth, e.g. re-import yields identical bytes;
  1 worker vs N workers identical; permuting archive member order identical; re-deriving PROV from AER identical;
  adding an irrelevant field to raw is ignored or flagged [S38].

P3.6 Cross-source and cross-corpus consistency: the same upstream task id, suite and benchmark version appears
with the same metadata (task text hash, tool list) across sources and dialects; shared executions in two corpora
have identical canonical content or an explained difference.

P3.7 Semantic plausibility of SEM labels: distribution per source/model; agreement between SEM labels and raw
indicators (e.g. injection marker vs the injected task text appearing in tool output); rule-citation validity (each
cited rule exists in the pinned catalogue version).

### P4. Cross-artefact integrity and uniqueness

- **Digest chain**: recompute sha256 at every link (raw -> AER -> SEM -> PROV -> validation results -> index ->
  manifest -> `checksums.sha256`); pass rate must be exactly 100%, with the failure list kept if not. This is
  the fixity audit: generation of checksums is not sufficient, they must be used in scheduled audits against stored
  objects [S28].
- **Set agreement**: index, register, manifest, checksum list and directory listing describe the same set of
  executions (two-way anti-joins; counts by status); orphan files and missing files.
- **Determinism**: recompute from AER (`recompute --check`) and compare bytes; repeat with different worker counts
  and in a fresh process; zero differences expected unless a version was bumped.
- **End-to-end fidelity**: raw -> AER -> raw-derived view comparison on a census of cheap facts and on a stratified
  sample of full content (P3.5). Report separately *loss* (in raw, not in AER), *invention* (in AER, not in raw
  and not derivable by a cited rule), and *distortion* (present in both but different).
- **Uniqueness** (DAMA uniqueness [S4]):
  - exact duplicates: group by digest of the canonical execution content after removing identifier and timestamp fields;
  - duplicate identifiers: same execution id with different content, or same content under different ids;
  - near duplicates: shingle the normalised message/tool sequence and use MinHash with LSH to estimate Jaccard
    similarity (resemblance) [S39]; this is the same family as the near-duplicate pass used by Lee et al. for
    training-text deduplication, which pairs exact substring matching with MinHash document matching [S40];
  - for agent logs, "duplicate" has two meanings that must not be conflated: (i) the same *run* ingested twice
    (processing/curation defect), and (ii) repeated *runs* of the same task with the same model that legitimately
    produce identical transcripts (source property; relevant to statistics because it breaks independence, and
    LLM outputs are non-deterministic even at temperature 0, so exact repeats are informative) [S41];
  - cross-corpus overlap: shared digests between corpora, so pooled statistics do not double count.

### P5. Graph quality

Graph profiling has no single standard; the following combines generic graph statistics with the provenance-quality
dimensions of [S30] and knowledge-graph quality surveys [S7][S8][S32]. (synthesis for the specific metrics)

- **Size and type distributions**: nodes and edges by PROV type (entity / activity / agent; used / wasGeneratedBy
  / wasDerivedFrom / wasAssociatedWith / ...), by bundle, by source, by model. Compare with the expected count
  implied by the AER (each record kind -> expected statements per the rule catalogue). Discrepancy = either
  rule-catalogue gap or mapper defect.
- **Connectivity**: weakly connected components per core bundle (expect 1 per execution, or a small explained set
  such as environment fixtures); isolated nodes; size of largest component; for components > 1 list which record
  kinds are disconnected and why. Huynh et al. show that network metrics of PROV graphs carry information on
  graph properties and data quality, so unusual metric values are legitimate screens [S29].
- **Degree distributions**: in/out degree by node type; hubs (e.g. one agent or model entity linked to everything);
  zero-in or zero-out-degree where the model requires at least one.
- **Structure constraints beyond PROV-CONSTRAINTS**: DAG property for derivation and informed-by; temporal
  precedence along edges when timestamps exist; no `used` whose object is an activity; no relation inferred from
  temporal order, shared context or policy taint (project invariant: such statements must never appear, so
  count = 0 is the pass criterion).
- **Pattern / motif checks**: for each rule in the catalogue, the expected local subgraph (for example "tool call
  activity has used-entity for arguments, wasGeneratedBy result entity, wasAssociatedWith agent"). Count executions
  where an expected motif is partially present. This is the closed-world completeness test *relative to the
  declared scope*; the provenance-capture literature notes there is no accepted absolute measure of completeness
  and stresses that missing edges can arise from bugs, misconfiguration, silent failure or inherent limits of the
  recorder, so causes must be separated [S32]. Declare the scope ("completeness relative to AER records and rule
  catalogue vX") rather than claiming absolute completeness.
- **Bundle discipline**: inferred statements only in inference bundles; policy claims only in the assessment bundle;
  cross-bundle references resolve; core bundle contains only observed or derived statements.
- **Evidence linkage coverage**: share of statements with a rule citation and a resolvable source pointer; share of
  AER `observed` values that appear in the graph; unreferenced AER records (declared "no statement" vs silent drops).
- **Repeated identical subgraphs**: canonical-hash subgraphs by record kind; high-frequency identical subgraphs are
  expected for templated harness steps, so report them as a property, and flag unexpected repetition.
- **Reference-based comparison** where a ground truth exists: the frozen compat oracle (`adprov_v2_3`) provides
  a reference graph set; use vertex/edge overlap (precision/recall/F1) on the mapped subset, as in reference-graph
  comparisons of provenance [S29b]; ProvMark-style black-box expressiveness testing is the established analogue
  for capture tools [S32].

### P6. Source-artefact discovery

Goal: find properties of the *upstream data* that a downstream reader must know (and that may bias statistics),
distinct from defects of the pipeline.

Detector families (all census, then a judged sample):

1. **Harness artefacts** (patterns generated by the evaluation harness, not by the agent): denial-style error
   strings, empty or truncated model outputs, retry/timeout markers, context-limit stops, invalid format/action
   stops, step-limit stops. AgentBench's own failure taxonomy (completed, context limit exceeded, invalid format,
   invalid action, task limit exceeded) is a ready-made category scheme for termination reasons [S42].
2. **Benchmark validity / scoring errors**: the Agentic Benchmark Checklist structures this as task validity
   (e.g. verify ground-truth annotation, isolate agent from ground truth, clean state between tasks), outcome validity
   (ground-truth states cover all successful outcomes, state space complex enough that trivial changes do not
   pass) and reporting items (statistical significance, interpretation guidance, baselines); audits of 10 benchmarks
   found outcome-validity problems in 7, task-validity problems in 7, and reporting limitations in all 10 [S19]. A
   separate audit of SWE-bench found 32.67% of "successful" patches involved solution leakage and 31.08% were suspicious because of weak tests, and
   removing them cut one agent's resolution rate from 12.47% to 3.97% [S20]; UTBoost reported 345 erroneous patches
   labelled as passed [S20b]. Tool-calling benchmarks showed an 18.5% evaluator-human misalignment rate in one
   validity audit [S21]. A 2026 preprint proposes reporting evidence-supported score bounds, labelling each run
   Evidence Pass / Fail / Unknown and bounding the success rate, and includes AgentDojo among five audited
   benchmarks [S43]. Apply the same discipline: for utility and security labels, check whether the AER carries the
   evidence (final state, tool effects) that would let a reader verify the label, and count "label present but
   evidence absent" separately from "label contradicted by evidence". I found no published audit that gives AgentDojo-specific
   ground-truth error rates; the NIST/CAISI work reports fixing unspecified bugs, adding asynchronous execution and
   Inspect integration, and shows that aggregate rates hide per-task variation and that attack success rises with
   adaptive attacks and repeated attempts [S44]. AgentDojo's design uses formal utility checks over environment
   state rather than an LLM simulator [S45], which makes the "evidence present" test feasible.
3. **Label noise**: confident-learning style screens plus human review; in standard ML test sets the average label
   error rate was at least 3.3% (6% for ImageNet validation) and rankings can flip when corrected [S46]. For agent
   logs a label-noise screen is "label disagrees with independent indicators" (e.g. the success label vs. the
   presence of the required tool effect).
4. **Duplicated or repeated runs** (P4), **non-determinism** (repeated runs at "deterministic" settings differ; report
   run-level variance, do not treat one run as a ground truth) [S41].
5. **Contamination / leakage** (task text appears in model training data, the injection payload text appears in
   the benchmark's public repository, trajectories contain the solution): contamination surveys list detection
   methods (perplexity/n-gram checks, guessing masked answers) [S47]. For a provenance corpus this is mostly a
   *documentation* item: record which benchmark versions are public and since when, and which models predate them.
6. **Version drift**: observed upstream commits vs the pinned commit; benchmark versions mixing within a corpus
   (AgentDojo task suites changed across versions [S45]); same benchmark name with different content.
7. **Time artefacts**: naive local timestamps, missing zones, timestamps rewritten by tooling, clustering at
   round values.
8. **Stratified outlier explanation**: for each size / count / duration outlier screen, check source, model, suite,
   attack, defence strata; many "outliers" are stratum properties.
9. **Trace-annotation precedent**: failure taxonomies for agent traces were built by expert annotation of 150
   traces with Cohen's kappa 0.88 (MAST), and a trace-level error benchmark has 148 annotated traces with 841 errors
   (TRAIL). Both are precedents for a double-annotated sample audit and a taxonomy-first approach [S48][S49].

For each artefact class record: detector id and version, count and rate with denominator, strata affected, example
execution ids (never raw payload text; use the project's quote function for untrusted text), and the proposed
disclosure entry. Source text is untrusted data.

### P7. Reporting

See sections 7 and 8.

---

## 4. Checklist

Pass criterion "= 0" means any occurrence is a finding. "Screen" means a candidate list to be explained, not by itself
a defect. Tool names are suggestions; the project's own validators remain the system under test, and an independent
implementation is used wherever stated.

| ID | Dimension | What is measured | How (tool / technique) | Pass criterion / what counts as a finding | Source |
|---|---|---|---|---|---|
| Q-001 | Scope | Versions, digests, tool versions recorded; run is read-only | Environment capture script; `git rev-parse`, `uv pip freeze`, digest of corpus files | All fields present; analysis code at a clean commit | [S33] |
| Q-010 | Profiling | Records per kind per execution; file/line/byte inventory | Streaming pass or DuckDB `read_json(format='newline_delimited')` | Totals reconcile exactly with `executions.jsonl`/`register.jsonl`; mismatch = finding | [S17][S15] |
| Q-011 | Profiling / validity | Key-set census per record kind and per nested path | Streaming count of sorted-key tuples; parametric schema inference for cross-check | Key sets equal the declared closed schema; unseen key set = finding; rare key set (<0.1%) = screen | [S16] |
| Q-012 | Profiling / validity | Type distribution per field; null / absent / empty rates | Same pass; per-path counters | Types equal schema; null rate on required field = finding | [S16][S14] |
| Q-013 | Uniqueness / profiling | Cardinality and uniqueness of id fields | Hash set or DuckDB `count(distinct)`; per-scope | Duplicate ids within scope = finding | [S4][S18] |
| Q-014 | Validity | Enum domains observed vs pinned vocabulary | Distinct-value census | Value outside vocabulary = finding | [S2] |
| Q-015 | Accuracy (plausibility) | Distribution/outlier screens for sizes, counts, durations, token counts | Robust z-score / IQR fences within strata | Screen; explained or classed as artefact; ISO 25024 outlier ratio reported | [S2] |
| Q-020 | Validity | Strict parse (UTF-8, JSON, duplicate keys, NaN/Inf, surrogates) | Strict stdlib parser plus independent parser (e.g. `orjson`/`simdjson`) as differential | Fail count = 0 for generated artefacts; for raw inputs count and classify | [S27] |
| Q-021 | Validity | AER/SEM schema conformance, all errors per record | `jsonschema` `Draft202012Validator.iter_errors` against the published JSON Schemas, independent of project validator | Violations = 0; disagreement between independent and project validator = finding on one of them | [S25][S26] |
| Q-022 | Validity / integrity | JCS idempotence | Re-canonicalise every line (second JCS implementation) and compare bytes | Differences = 0 | [S27] |
| Q-023 | Validity | PROV-JSON structural conformance, prefixes, QNames, bundle containment | Independent loader (e.g. ProvToolbox / `prov` Python) plus project check | Load errors = 0 | [S22][S23] |
| Q-024 | Consistency | PROV-CONSTRAINTS on normal form, per bundle and per constraint | Project tier-4 validator and an independent validator (ProvValidator / ProvToolbox) on a census, or at least on a large stratified sample if the independent tool is slow | Violations = 0 per constraint; report counts per constraint id | [S24] |
| Q-030 | Consistency | Intra-record invariants (time order, evidence class vs locator, counts >= 0) | Rule list evaluated per record | Violations = 0 | [S4] |
| Q-031 | Consistency | Referential integrity within execution | Anti-join on reference fields | Dangling refs = 0 (declared absent blobs are disclosed, not a seal issue, per project decision) | [S4] |
| Q-032 | Consistency | Accounting identities (calls vs results, tokens, messages) | Arithmetic per execution | Residual explained by a named cause; unexplained residual = finding | [S2] |
| Q-033 | Timeliness | Time value presence, zone state, monotonicity, plausible range | Per-source counters; range assertions | Invented/placeholder time = 0; others reported as source properties | [S4][S31] |
| Q-034 | Consistency | Differential re-read of raw facts vs AER/SEM/PROV | Independent minimal reader on census of cheap facts, stratified sample of full | Loss/invention/distortion counts; invention without rule = finding | [S37] |
| Q-035 | Consistency | Metamorphic relations (reorder, worker count, re-run, re-derive) | Re-run pipeline variants; byte compare | Differences = 0 | [S38] |
| Q-036 | Consistency | Cross-source / cross-corpus agreement for same task, suite, version | Join on upstream ids; compare metadata hashes | Unexplained disagreement = finding | [S4] |
| Q-037 | Accuracy | SEM label vs raw indicators; rule citations valid | Join SEM labels with raw-derived indicators; check rule ids in catalogue | Invalid citation = 0; label/indicator disagreement rate with CI | [S2][S6] |
| Q-040 | Integrity | Digest chain recomputation raw -> AER -> SEM -> PROV -> index -> manifest | `agentprov verify --level chain` plus independent `sha256sum -c` / own script | 100% match | [S28] |
| Q-041 | Integrity | Set agreement among index, register, manifest, checksums, directory | Two-way anti-joins | Orphans = 0, missing = 0 | [S28] |
| Q-042 | Integrity | Determinism of recompute | `agentprov recompute --check` in fresh process, 1 vs N workers | 0 differences unless version bumped | [S33] |
| Q-043 | Uniqueness | Exact duplicate executions | Digest of canonical content with id and time removed; group | Same-run-ingested-twice = 0; repeated legitimate runs reported as source property | [S4] |
| Q-044 | Uniqueness | Near duplicates | Shingled message/tool sequence + MinHash/LSH, Jaccard threshold chosen on a labelled pilot | Screen; verify sample by hand; report threshold and precision of the sample | [S39][S40] |
| Q-045 | Uniqueness | Cross-corpus overlap | Digest join across corpora | Overlap reported; pooled statistics deduplicated | [S4] |
| Q-050 | Provenance completeness | Statements with rule + resolvable evidence pointer | Count per statement type | 100% of non-trivial statements; exceptions = finding | [S30] |
| Q-051 | Provenance completeness | AER record -> expected statements (accounting) | Compare catalogue-implied counts with graph counts; list unmapped record kinds | Unmapped records must be declared "no statement" in the catalogue; silent drops = finding | [S32][S30] |
| Q-052 | Provenance consistency | Bundle discipline (inference/assessment separation) | Statement-origin audit | Inferred or policy statements in core = 0 | project invariant |
| Q-053 | Provenance consistency | Forbidden statements (temporal-order-only relations, `used` on activity) | Pattern search | = 0 | project invariant, [S24] |
| Q-054 | Graph quality | Weakly connected components, isolated nodes, largest component share | Union-find over edges (NetworkX / `igraph` / DuckDB recursive CTE) | Components > expected set = screen; each explained | [S29] |
| Q-055 | Graph quality | Degree distributions, hubs, zero-degree nodes by type | Streaming degree counts | Zero in/out degree where the model requires at least one = finding; hubs = screen | [S29] |
| Q-056 | Graph quality | DAG property of derivation / informed-by; temporal order along edges | Topological sort; compare timestamps where present | Cycles = 0; backwards edges with real times = finding | [S24] |
| Q-057 | Graph quality | Motif completeness per rule | Subgraph pattern counts per executions | Partial motifs = finding unless record kind declares absence | [S32] |
| Q-058 | Graph quality | Repeated identical subgraphs | Canonical subgraph hash | Report; unexpected repetition = screen | (synthesis) |
| Q-059 | Graph quality | Reference-graph overlap (compat oracle, golden set) | Vertex/edge precision, recall, F1 on mapped subset | Meets pre-registered threshold; differences classified by semdiff map | [S29b] |
| Q-060 | Source artefact | Termination reason distribution; harness-error patterns; empty/truncated outputs | Pattern detectors with versions; AgentBench-style categories | Report rate with denominator; classify per detector | [S42] |
| Q-061 | Source artefact | Utility/security label evidence available in AER | Check final-state/tool-effect evidence vs label | Count: evidence-supports / contradicts / absent (Unknown); report bounds on success rates | [S43][S19] |
| Q-062 | Source artefact | Label noise estimate | Double-annotated stratified sample; Cohen kappa / Krippendorff alpha | Estimate with CI; agreement reported with label prevalence (kappa paradox) | [S46][S50] |
| Q-063 | Source artefact | Run-level non-determinism / repeated runs | Group by (task, model, config); variance of outcomes | Report; do not treat repeats as independent | [S41][S52] |
| Q-064 | Source artefact | Version drift / mixed versions | Compare observed commit and benchmark version fields | Mixed versions inside one corpus = disclosed property | [S45] |
| Q-065 | Source artefact | Contamination / public availability | Document dates of public release vs model cut-offs | Documentation item; no pass/fail | [S47] |
| Q-066 | Source artefact | Time artefacts (naive, rounded, rewritten) | Histograms of minutes/seconds/millis; zone state | Report | [S31] |
| Q-070 | Reporting | Every finding classed and attributed; denominators stated | Template (section 7) | 100% of findings carry class, attribution, count, denominator, example ids | [S10][S34] |
| Q-071 | Reproducibility | Re-running the audit reproduces the result files bit for bit | Run audit twice in clean env; compare digests | Identical | [S33] |

---

## 5. Tools: what each does and its relevance

| Tool | What it checks | Relevance here | Source |
|---|---|---|---|
| `jsonschema` (Python) | Schema validation, Draft 2020-12, collects all errors | Primary tool for Q-021; use as an independent check beside the project validator | [S25][S26] |
| DuckDB | SQL over NDJSON with type auto-detection and sampling controls; anti-joins, group-bys, quantiles | Best fit for census-scale profiling and referential-integrity queries on 10^6-10^7 rows without a cluster; set detection to full scan or declare types explicitly | [S17] |
| Great Expectations | Declarative "expectations", suites, validation results, human-readable Data Docs | Useful as a reporting format and for dataframe-level expectations; heavier than needed for closed-schema JSONL; reasonable for tabular exports (index, register) | [S51] |
| Deequ / PyDeequ | Constraints and metrics (completeness, uniqueness, compliance) computed as Spark aggregation; incremental metrics; constraint suggestion; anomaly detection on metric time series | Design reference (metrics-first, store metrics per run); Spark is probably not warranted at 126k executions | [S15] |
| pandera | Library-level dataframe schema, column and dataframe-wide checks, joint uniqueness | Good for validating derived tables (per-execution metric frames) inside tests; not a JSON validator | [S53] |
| TFX Data Validation | Schema inference, drift/skew detection from statistics | Conceptual precedent for schema + statistics + anomaly flow [S14]; skip as a dependency | [S14] |
| ydata-profiling | Automatic profile and alerts (high cardinality, duplicates, correlations) | Quick exploratory look at tabular extracts only; alerts are suggestions needing domain validation | [S18] |
| `jq` / `grep` / `sort | uniq -c` | Ad hoc census on JSONL | Fine for spot checks; not for the recorded audit (not versioned, hard to make deterministic) | (K) |
| ProvToolbox, `prov` (Python), ProvValidator | PROV-JSON/N load, PROV-CONSTRAINTS validation | Independent validators for Q-023/Q-024; check current maintenance and constraint coverage before relying on them | [S22][S24] |
| ProvMark | Black-box expressiveness benchmarking of provenance capture | Method precedent for testing the capture/mapping layer with known activities [S32] | [S32] |
| Datasketch / own MinHash | MinHash + LSH near-duplicate detection | Q-044 | [S39] |

---

## 6. Sampling and statistics guidance

### 6.1 Census versus sample

- **Census (all 126k executions, all records)** whenever the check is mechanical and linear in data size:
  parse, schema, canonical form, digests, referential integrity, PROV-CONSTRAINTS, graph metrics, duplicate
  hashing. A census has no sampling error; report exact counts and rates, no confidence intervals for the
  *corpus-level* descriptive statistics. Intervals are needed only if the statement is about a larger
  population (e.g. "the benchmark in general") [S36].
- **Sample** only when each unit needs human or expensive judgement: label correctness, mapping faithfulness of
  full content, near-duplicate verification, harness-artefact precision, SEM label accuracy. Stratify by
  corpus x source/dialect x model (or model family) x suite/task type x outcome (success/failure, with/without
  attack, with/without seal issues) so that rare strata are not drowned. Allocate with Neyman (proportional to
  stratum size x variability) when variances are roughly known from a pilot, else proportional with a minimum
  per stratum [S54].
- **Independence caveat**: executions are clustered (same task across models, same attack across tasks, same
  upstream run in two corpora). Simple-random-sample formulas understate uncertainty. Treat the task (or task
  family) as the cluster for intervals, using cluster-robust standard errors or a cluster bootstrap; evaluation
  literature recommends clustered standard errors and paired comparisons for exactly this reason [S36].
- Always keep the **denominator visible** and say what unit it is (executions, records, statements).

### 6.2 Proportions and sample sizes

- Default interval for a proportion: **Wilson** (score) interval, or Jeffreys, for small n; Agresti-Coull for larger n;
  avoid the Wald interval, whose coverage is erratic [S55][S56]. Clopper-Pearson is guaranteed to cover but conservative;
  use it when a conservative statement is wanted (for example "defect rate below X"), accepting wider intervals [S55][S56].
- Sample size for estimating a proportion to margin of error e at 95% confidence, worst case p = 0.5:
  n = z^2 p(1-p)/e^2 gives 385 for +/-5 points, 1,068 for +/-3, 2,401 for +/-2, 9,604 for +/-1 [S54]. The finite
  population correction is negligible at N = 126,000 for these n (385 -> 384). If you expect a small p (a defect rate
  of ~1%), plan for the *absolute* precision you need at that p, not at p = 0.5, and use a Wilson interval on
  the result.
- **Zero-event results** ("we found no violations in n inspected"): the "rule of three" gives an approximate
  95% upper bound of 3/n on the rate, from P(0 events) = (1-p)^n = 0.05 [S57]. Exact one-sided 95% upper bounds,
  which I computed here: n=50: 5.8%; n=100: 3.0%; n=300: 0.99%; n=1,000: 0.30%; n=3,000: 0.10%; n=10,000: 0.03%
  (two-sided Clopper-Pearson upper limits are slightly larger: 3.6%, 1.2%, 0.37%, 0.12%, 0.04% for n = 100, 300,
  1,000, 3,000, 10,000). So **a sample of ~300 with zero defects supports "defect rate below 1% with 95% confidence"**, and a sample of
  3,000 supports "below 0.1%". If the check is a census and finds zero, say "0 of N", not an interval.
- When judging with several raters, report **inter-annotator agreement** with the coefficient, n items, number of
  categories and label prevalence. Cohen's kappa suits two raters with nominal labels; Krippendorff's alpha handles more raters,
  ordinal scales and missing judgments; kappa behaves badly with very imbalanced categories; verbal bands (Landis and Koch) are conventions,
  not pass/fail tests [S50]. Measure agreement on an overlap subset (for example 10-20% of the sample double annotated) and
  adjudicate disagreements.
- Audit precedent: Kreutzer et al. audited at most 100 sentences per corpus, across 205 corpora, with a primary annotator and repeated
  annotation for agreement [S58]. This is a practical precedent for small per-stratum audits, but 100 per stratum
  gives about +/-10 points at p = 0.5; state the resulting precision.

### 6.3 Comparing groups and rates

- Compare rates between corpora/models with the effect size (difference or ratio with CI) first, tests second.
  For paired settings (same tasks across models) use paired analyses, which reduce variance [S36].
- Evaluation results are experimental data with sampling uncertainty over questions; a 500-question benchmark at
  a 50% baseline needs roughly a 9-point gap to detect at 80% power (reported by a third-party package built on
  the cited paper; treat as indicative) [S36][S36b].

### 6.4 Multiple comparisons and forking paths

- The audit will compute hundreds of checks and per-stratum rates. Distinguish **confirmatory** hypotheses
  (pre-registered, few; control family-wise error with Holm, which is valid under any dependence) [S59] from
  **exploratory screens** (many; control the false discovery rate with Benjamini-Hochberg, valid for independent
  or positively dependent statistics) [S60]. Say which applies to each finding.
- Mechanical zero-tolerance checks (Q-020...Q-042) are not hypothesis tests; no correction applies, one failure is a finding.
- Pre-register thresholds for outlier screens and near-duplicate similarity; if tuned on the data, tune on a pilot
  split and evaluate on a disjoint split.
- Do not describe a screen hit as a defect until it is attributed (section 7).

### 6.5 Reproducibility of the statistics

- Fix random seeds for any sampling and bootstrap; store the sampled id lists; store the code and the tool
  versions (these are standard reproducibility rules: track how every result was produced, avoid manual
  manipulation, archive exact versions, record seeds, keep raw data behind plots) [S33]. Deterministic ordering of
  inputs (sorted ids) before sampling.
- Prefer the **deterministic** parts (counts, digests) as primary evidence; sampling results as secondary with
  intervals.

---

## 7. Classifying and reporting findings

### 7.1 Classification scheme

(synthesis; fits the structure already used in the phase-10 report: correct-and-disclosed, defect, question)

For each finding record: id, check id, dimension, affected unit and count, denominator, rate (+ interval if sampled),
strata, example ids, **attribution**, **disposition**, **impact**, evidence.

Attribution (decided by this procedure, in order):
1. Does the property appear in the raw bytes (found by the independent minimal re-reader, Q-034)? If yes and the
   AER/PROV represents it faithfully -> **SRC: source-data property** (disclose; may be a benchmark or harness artefact,
   or a model behaviour).
2. If it appears in raw but is lost, invented or distorted downstream -> **PRC: processing defect**, subclassed by stage
   (reader / mapper / SEM / PROV engine / validator / corpus assembly / packaging). Locate the stage by diffing
   the stage outputs (raw -> AER -> SEM -> PROV).
3. If it appears only in some analysis output (tool, sampling, join, threshold) -> **ANA: analysis artefact**; fix
   the audit and do not report as a corpus property.
4. If raw is unavailable or ambiguous -> **UND: undetermined**; list the evidence needed.

Disposition: correct and disclosed (no fix) / fix required (needs user approval before corpus regeneration, per
repo rule) / disclosure to add (artefact catalogue) / question for the user.

Impact: how it affects the thesis claims (which statistics, which corpora, which conclusions) and its direction of
bias where known; downstream propagation (AER digest, PROV output, compat gate, manifests, manuscript numbers).
This echoes data-cascade findings: problems compound downstream and are hard to see [S13].

Severity (proposal): S0 integrity/validity failure that blocks release; S1 changes a headline number or invalidates a
claim; S2 biases a secondary statistic or must be disclosed; S3 cosmetic or documentation.

### 7.2 Structure of the audit chapter / report

1. Purpose and research questions (what claims need which quality properties; fitness for use [S3]).
2. Corpora and provenance of the data (sources, pinned commits, versions, counts), datasheet-style composition [S10].
3. Quality model: dimensions, measures, thresholds (ISO 25012/25024 and DAMA vocabulary) [S1][S2][S4].
4. Method: phases P0-P7, tools and versions, census-vs-sample decisions, sampling plan, statistical procedures.
5. Results by phase with tables of numerator/denominator/rate; one summary table per corpus (a "quality label" in
   the spirit of dataset nutrition labels [S11]) and a cross-corpus comparison.
6. Findings catalogue (classified; section 7.1), with the disclosed source artefacts feeding the corpus datasheet.
7. Impact on analyses (sensitivity: rerun key statistics with and without flagged executions; report both).
8. Threats to validity (7.3).
9. Reproducibility statement (7.4).
10. Limitations and future work.

What to quantify: counts and rates with denominators for every check; distributions (not only means);
residuals of every accounting identity; seal issue distribution by code and source; evidence class mix;
graph size/connectivity distributions; duplicate and overlap rates; label-evidence availability (pass / fail /
unknown) with score bounds [S43]; inter-rater agreement; sensitivity of headline statistics to exclusions.

### 7.3 Threats to validity (use Wohlin-style categories, adapted)

Categories as used in software engineering research: conclusion validity (statistical inference sound),
internal (alternative explanations, confounding by stratum), construct (do the measures capture the intended
quality), external (generalisation beyond the corpora) [S61][S62]. For this audit:

- **Construct**: structural validity is not truth; "no violations" shows the pipeline is self-consistent, not that
  the benchmark label is right [S5][S19]. Completeness is relative to a declared scope [S32]. Evidence classes
  are the project's own taxonomy.
- **Circularity / independence**: the pipeline validating its own output is weak evidence. Mitigate by independent
  validators, the minimal raw re-reader, and metamorphic tests [S37][S38]. Say where independence is only partial
  (same author, same spec).
- **Internal**: confounding between source, model, suite and attack; execution clustering; survivorship (executions
  that failed import are sealed with issues, not discarded, so keep them in the denominator).
- **Conclusion**: multiple comparisons, small strata, threshold tuning on the data [S59][S60].
- **External**: corpora are census of imported logs, not representative of agent behaviour in general; benchmark
  versions change over time [S45]; models and harness versions differ [S36].
- **Instrument**: auto-detection sampling in tools; differences between parser strictness; detectors' own
  precision (report detector precision from a judged sample).
- **Reviewer**: single judge for manual labels; mitigate with double annotation and agreement statistics [S50].
- **Untrusted data**: corpora deliberately contain injection payloads; the audit tooling must not interpret
  contents (project security rule).

### 7.4 Reproducibility statement (template)

"All audit results were produced by script `<path>` at commit `<sha>`, run with Python `<ver>`, `<tool>`=`<ver>`...
on `<os/hardware>`, over corpus versions `<ids + manifest digests>`. Sampling used seed `<n>` over sorted
execution ids; the sampled ids and annotations are in `<file>` (digest `<sha256>`). Result files are listed with
sha256 digests; re-running the scripts reproduces them byte for byte (checked on `<date>`, check Q-071). Corpora and raw stores
are not included in the repository; they are obtainable from `<DOI>` / pinned origins." This applies the standard
rules on tracking provenance of results, archiving versions, recording seeds and publishing scripts [S33] and the
ACM-style distinction between sharing artefacts and reproducing results (K, not opened).

---

## 8. Honest gaps and cautions

- **No standard provenance-graph quality metric set exists.** The provenance-capture literature explicitly says
  measuring completeness is open and "quality" is hard to evaluate; the best-supported tools are
  reference-based comparison, expressiveness benchmarking, fault injection and scope-relative completeness [S32][S30].
  Therefore define metrics, declare the scope, and report them as such.
- **Fault injection** (synthesis, from Cheah and Plale's use of injected faults, e.g. dropped provenance [S30]): to calibrate the checklist, mutate a small sample
  of valid artefacts (drop a record, swap an id, break a digest, reorder timestamps, delete an edge) and
  confirm the relevant check fires. Report the detection rate per check. This is the cheapest way to defend
  "the audit can detect defects of kind X".
- Several benchmark-audit sources are 2026 arXiv preprints [S19b][S43] or conference slides; confirm they have been
  published or revised before quoting numbers. AgentDojo-specific ground-truth error rates were not found in
  published audits.
- The ISO standards are paywalled; I could only read summaries [S1][S2]. Cite them for vocabulary and the
  measure-element idea, not for specific formulas, unless you obtain the text.
- Some tool documentation was seen through search summaries only (Great Expectations, pandera, ydata-profiling,
  Deequ) [S15][S18][S51][S53]; check current versions before describing features in the thesis.

---

## 9. Sources

Status: F = fetched and read; S = search result/abstract only; K = background knowledge, not opened.

Frameworks and data quality
- [S1] (S) ISO/IEC 25012:2008 Data quality model. https://webstore.iec.ch/publication/11246 ; summary https://quality.arc42.org/standards/iso-iec-25012 ; survey https://arxiv.org/pdf/2507.17507
- [S2] (S) ISO/IEC 25024:2015 Measurement of data quality. https://webstore.iec.ch/en/publication/23610 ; summary https://quality.arc42.org/standards/iso-25024
- [S3] (S) Wang and Strong 1996, Beyond Accuracy, JMIS 12(4). https://web.mit.edu/tdqm/www/tdqmpub/beyondaccuracy_files/beyondaccuracy.html
- [S4] (S) DAMA UK Working Group, The Six Primary Dimensions for Data Quality Assessment, 2013 (third-party mirror). https://joelbth.codeberg.page/community-notices/dama-quality-dimensions.pdf ; summary https://www.tmap.net/node/760
- [S5] (S) UK Government Data Quality Framework / dimensions. https://www.gov.uk/government/news/meet-the-data-quality-dimensions
- [S6] (S) Pipino, Lee, Wang 2002, Data quality assessment, CACM 45(4). https://dl.acm.org/doi/10.1145/505248.506010
- [S7] (S) Zaveri et al. 2016, Quality assessment for Linked Data: a survey, Semantic Web 7(1). https://semantic-web-journal.net/node/773
- [S8] (S) SHACL shapes for the 69 Zaveri metrics (arXiv 2025). https://arxiv.org/pdf/2507.22305
- [S9] (S) Wilkinson et al. 2016, FAIR Guiding Principles, Scientific Data 3:160018. https://doi.org/10.1038/sdata.2016.18
- [S10] (S) Gebru et al., Datasheets for Datasets. https://arxiv.org/abs/1803.09010
- [S11] (S) Holland et al., Dataset Nutrition Label. https://arxiv.org/abs/1805.03677
- [S12] (S) Bender and Friedman, Data Statements. https://techpolicylab.uw.edu/data-statements/
- [S13] (S) Sambasivan et al. 2021, Data Cascades, CHI. https://research.google/pubs/pub49953/
- [S14] (S) Breck et al. 2019, Data validation for machine learning, SysML. https://research.google/pubs/data-validation-for-machine-learning/ ; TFDV https://www.tensorflow.org/tfx/data_validation
- [S15] (S) Schelter et al. 2018, Automating large-scale data quality verification, PVLDB 11(12). https://www.vldb.org/pvldb/vol11/p1781-schelter.pdf
- [S16] (S) Baazizi, Colazzo, Ghelli, Sartiani 2019, Parametric schema inference for massive JSON datasets, VLDB J. 28(4). https://researchportal.ip-paris.fr/en/publications/parametric-schema-inference-for-massive-json-datasets/ ; EDBT 2017 version https://hal.sorbonne-universite.fr/hal-01491765/document
- [S17] (S) DuckDB, Loading JSON. https://duckdb.org/docs/current/data/json/loading_json
- [S18] (S) ydata-profiling concepts (alerts). https://docs.profiling.ydata.ai/4.8/getting-started/concepts
- [S25] (S) JSON Schema specification (2020-12). https://json-schema.org/specification
- [S26] (S) python-jsonschema documentation. https://python-jsonschema.readthedocs.io/
- [S27] (S) RFC 8785, JSON Canonicalization Scheme. https://www.rfc-editor.org/rfc/rfc8785
- [S28] (S) NDSA Fixity Guidance Report. https://www.digitalpreservation.gov/ndsa/working_groups/documents/NDSA-Fixity-Guidance-Report-final100214.pdf
- [S51] (S) Great Expectations documentation. https://docs.greatexpectations.io/ (concepts: https://docs.greatexpectations.io/docs/terms/data_docs)
- [S53] (S) pandera DataFrameSchema reference. https://pandera.readthedocs.io/en/stable/reference/generated/pandera.api.dataframe.container.DataFrameSchema.html

Provenance and graph quality
- [S22] (S) W3C PROV-JSON Member Submission. https://www.w3.org/submissions/prov-json/
- [S23] (K) W3C PROV-DM Recommendation (2013). https://www.w3.org/TR/prov-dm/
- [S24] (F) W3C PROV-CONSTRAINTS Recommendation. https://www.w3.org/TR/prov-constraints/
- [S29] (S) Huynh et al. 2018, Provenance network analytics, Data Mining and Knowledge Discovery 32(3). https://link.springer.com/article/10.1007/s10618-017-0549-3
- [S29b] (S) Reference-graph vertex/edge overlap F1 for provenance graph comparison (2026 preprint, GaussTrace; method idea only). https://arxiv.org/pdf/2606.10612
- [S30] (F for abstract) Cheah and Plale 2012, Provenance Analysis: Towards Quality Provenance. https://scholarworks.iu.edu/dspace/items/c10f0714-ed86-405e-b542-351534335bfe ; dissertation https://scholarworks.iu.edu/dspace/items/c46b205b-bdd5-470e-92e7-2a3f2a57daac
- [S31] (S) Hartig and Zhao 2009, Using Web Data Provenance for Quality Assessment. https://ceur-ws.org/Vol-538/ldow2009_paper18.pdf
- [S32] (S) ProvMark: provenance expressiveness benchmarking. https://arxiv.org/pdf/1909.11187 ; Practical whole-system provenance capture https://arxiv.org/pdf/1711.05296 ; knowledge graph completeness review https://cris.maastrichtuniversity.nl/en/publications/knowledge-graph-completeness-a-systematic-literature-review/
- [S19x] (S) Herschel et al. 2017, A survey on provenance: What for? What form? What from?, VLDB J. 26(6). https://www.ipvs.uni-stuttgart.de/departments/de/resources/papers/provenance_survey_online.pdf

Agent and LLM benchmark data quality
- [S19] (F) Zhu et al., Establishing Best Practices for Building Rigorous Agentic Benchmarks (ABC), NeurIPS 2025 D&B. https://arxiv.org/html/2507.02825v5
- [S19b] (F) Tu et al., BenchGuard: Who Guards the Benchmarks? (arXiv 2604.24955, COLM 2026). https://arxiv.org/abs/2604.24955
- [S20] (S) SWE-Bench+ (solution leakage and weak tests). https://arxiv.org/pdf/2410.06992v1
- [S20b] (S) UTBoost, ACL 2025. https://arxiv.org/pdf/2506.09289
- [S21] (S) Agent/tool-calling benchmark validity audit (BFCL, tau2-Bench, LiveMCPBench, MCP-Atlas; 18.5% misalignment). https://huggingface.co/papers/2607.02577 ; related ICML 2026 AgentSuite https://proceedings.mlr.press/v306/suh26a.html
- [S36] (S) Miller 2024, Adding Error Bars to Evals. https://arxiv.org/abs/2411.00640
- [S36b] (S) errorbars package (power example). https://pypi.org/project/errorbars/
- [S41] (S) Atil et al., Non-Determinism of "Deterministic" LLM Settings. https://arxiv.org/abs/2408.04667
- [S42] (S) Liu et al. 2023, AgentBench. https://arxiv.org/pdf/2308.03688
- [S43] (F) Gao and Zhou 2026, Can Agent Benchmarks Support Their Scores? Evidence-Supported Bounds (includes AgentDojo). https://arxiv.org/abs/2605.10448
- [S44] (F) NIST CAISI, Strengthening AI Agent Hijacking Evaluations (Jan 2025). https://www.nist.gov/news-events/news/2025/01/technical-blog-strengthening-ai-agent-hijacking-evaluations
- [S45] (S) Debenedetti et al. 2024, AgentDojo. https://arxiv.org/abs/2406.13352
- [S46] (S) Northcutt et al. 2021, Pervasive Label Errors in Test Sets, NeurIPS D&B. https://arxiv.org/abs/2103.14749
- [S47] (S) Benchmark data contamination surveys. https://arxiv.org/pdf/2406.04244 ; https://aclanthology.org/2024.acl-long.86
- [S48] (S) Cemri et al., Why Do Multi-Agent LLM Systems Fail? (MAST). https://arxiv.org/abs/2503.13657
- [S49] (S) TRAIL: Trace Reasoning and Agentic Issue Localization. https://arxiv.org/abs/2505.08638
- [S52] (S) Biderman et al. 2024, Lessons from the Trenches on Reproducible Evaluation of Language Models. https://arxiv.org/abs/2405.14782
- [S58] (S) Kreutzer et al. 2022, Quality at a Glance: An Audit of Web-Crawled Multilingual Datasets, TACL 10. https://arxiv.org/abs/2103.12028
- Other agent benchmarks referenced only for context: InjecAgent https://arxiv.org/abs/2403.02691 (S); Inspect log format https://inspect.aisi.org.uk/eval-logs.html (S).

Duplicates, differential testing
- [S39] (S) Broder 1997, On the resemblance and containment of documents. https://www.cs.princeton.edu/courses/archive/spring13/cos598C/broder97resemblance.pdf
- [S40] (S) Lee et al. 2022, Deduplicating Training Data Makes Language Models Better, ACL. https://arxiv.org/abs/2107.06499
- [S37] (S) McKeeman 1998, Differential testing for software, Digital Technical Journal 10(1) (title varies between sources; paper itself not retrieved). https://dblp.org/pid/40/4856
- [S38] (S) Chen et al. 2018, Metamorphic testing: a review of challenges and opportunities, ACM Computing Surveys 51(1). https://eprints.nottingham.ac.uk/51607

Statistics
- [S54] (S) Cochran's formula and Neyman allocation. https://cran.nics.utk.edu/cran/web/packages/cochranSize/vignettes/introduction.Rmd ; https://en.wikipedia.org/wiki/Neyman_allocation (Cochran 1977 not opened)
- [S55] (S) Brown, Cai, DasGupta 2001, Interval estimation for a binomial proportion, Statistical Science. https://projecteuclid.org/euclid.ss/1009213286
- [S56] (S) Agresti and Coull 1998, Approximate is better than "exact", The American Statistician. https://users.stat.ufl.edu/~aa/articles/agresti_coull_1998.pdf
- [S57] (S) Hanley and Lippman-Hand 1983, If nothing goes wrong, is everything all right?, JAMA 249. https://jamanetwork.com/journals/jama/article-abstract/389714
- [S59] (S) Holm 1979, A simple sequentially rejective multiple test procedure, Scand. J. Stat. 6. https://data.gesis.org/gesiskg/resource/zis-Holm1979A
- [S60] (S) Benjamini and Hochberg 1995, Controlling the false discovery rate, JRSS B 57. https://www.dcscience.net/Benjamini-Hochberg-1995-FDR.pdf
- [S50] (S) Artstein and Poesio inter-coder agreement survey; Landis and Koch bands (secondary). https://www.cl.cam.ac.uk/teaching/1516/R216/Artstein.pdf

Reporting and validity
- [S33] (S) Sandve et al. 2013, Ten Simple Rules for Reproducible Computational Research. https://pmc.ncbi.nlm.nih.gov/articles/PMC3812051/
- [S34] (S) Gebru et al. (datasheets) as reporting template, see [S10]; Dataset Nutrition Label [S11].
- [S35] (S) Runeson and Host 2009, Guidelines for conducting and reporting case study research in software engineering, Empir. Softw. Eng. 14. https://www.cse.chalmers.se/~feldt/advice/runeson_2009_emse_case_study_guidelines.pdf
- [S61] (S) Wohlin et al., Experimentation in Software Engineering (validity classes as applied in secondary papers; book not opened). https://doi.org/10.1007/978-3-642-29044-2
- [S62] see [S35].
