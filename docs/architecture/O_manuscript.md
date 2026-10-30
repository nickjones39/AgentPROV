Revision: 2026-10-07 r2 — review resolutions and Addendum B applied.

# O. Manuscript migration

Section O of the AgentPROV v0.1 architecture and implementation specification.
Status: DRAFT-FOR-REVIEW, 2026-10-07 (r2). Binding input, in order of precedence: `investigation/DECISIONS.md`
**Addendum B** (architect rulings on the review), then **Addendum A**, then D0–D12; and
`investigation/spec/review/RESOLUTIONS.md`, whose §3 canonical naming table this section follows except where
Addendum B deviates from it (AD-08 nuance, AD-10 `stats`/`render` kept, AD-15 generic kinds, AD-16 interpreter).
The key words MUST, MUST NOT, SHOULD, SHOULD NOT and MAY are used as in RFC 2119/RFC 8174.

**Changes after review (2026-10-07).** R ids applied: R-01 (paper interpreter, no `[analysis]` extra), R-04 and
R-26 (C2 "from the AER alone", v2.3 checksum lists), R-05 (released v1 context INFERRED), R-07 and R-28 (C-O1
resolved: Inspect AgentHarm is the structurally different source; STAC is a scenario population; `unit`), R-15
(registry statuses), R-27 (claims; AD-08 as ruled), R-33 (`tab:semdiff` from gate E), R-34 and R-45 (scope; AD-10
as ruled keeps `agentprov stats` and `agentprov render`), R-35/R-36 (generic `activity` and `artefact` kinds, AD-15
as ruled), R-57 (field-group coverage headline; `not_applicable`), R-58 (README-facing wording), R-61 (AER name),
R-62 (survey pin), R-63, R-64 (frames, `ValueBasis`, validation read from the corpus). Both challenges of r1
(C-O1, C-O2) are ruled and replaced by "Resolved" notes. The r2 consistency sweep (2026-10-08,
`spec/review/SWEEP_r2.md` EV-1, AD-SW18) settled the 26,645 / 23,449 pair, which is not recomputed: both readings
are correct and identical by construction, with evidence in `landscape/prov_semantics_evidence/inference6_scan.json`
and `audit/provenance_evidence/evidence_stats.json` (F4, OM-4). It also fixed `fig:example` panel (a) to
`agentprov_paper.render.figures` (F6).

> **Superseded in part (2026-10-28 and 2026-10-29, the user's decisions):** the venue is now **Elsevier
> Knowledge-Based Systems** (KBS), typeset with the Elsevier `cas-dc` class. On 2026-10-28 the user chose IEEE
> Transactions on Artificial Intelligence (IEEE two-column class); on 2026-10-29 the user moved the paper to KBS
> (manuscript commit `72df575`). The manuscript lives in `~/Desktop/PhD/Labs/7. AgentPROV/`, not
> `3. AgentPROV paper/`, with main file `paper/agentprov.tex` (formerly `paper/agentprov_kbs.tex`). KBS review is
> single-anonymised, so author names, affiliations and public links appear. KBS asks for an abstract of at most 250
> words, 1–7 keywords, 3–5 highlights of at most 85 characters in a separate file, numbered references, a CRediT
> statement, a funding statement and a generative-AI declaration. It advises research papers of about 20
> double-spaced pages or fewer. 2–3 research questions and a Broader Impact section are kept from the IEEE TAI brief.
> The claims rules, banned wording and the
> keyed-accessor discipline for numbers below still apply. The IEEE TAI brief
> (`~/.agentprov/handoff/manuscript-agentprov-ieee-tai.md`) is historical.

**Scope.** This section specifies how the new manuscript at
`~/Desktop/PhD/Labs/3. AgentPROV paper/` (main file `paper/agentprov_paper.tex`)
evolves from `~/Desktop/PhD/Labs/3. AgentDojo-PROV/paper/adprov_paper.tex`
(manuscript repository HEAD `24ac03f26e97cec96b5bbb77cd876d671a37c4e4`; baseline framework
`579a908354b93361efe0905ffb7623256aa96a06`). Nothing specified here modifies either old repository
[DECISIONS.md D12: "The old manuscript stays pinned to framework 579a908"].

**Citation shorthand used in this section.**

| Shorthand | Meaning |
|---|---|
| `[PA §n]`, `PA-Dn` | `investigation/manuscript/paper_analysis.md` section n; discrepancy *n* of its §14 (these D-numbers are **not** DECISIONS numbers) |
| `[FP §n]`, `FP-#n` | `investigation/manuscript/figure_pipeline.md` section n; latent defect *n* of its §6 |
| `[RF <id>]` | `investigation/manuscript/review_feedback.md` item (SEM-1, CAP-3, NOV-5, AR-1, …) |
| `[DEC Dn]` | `investigation/DECISIONS.md` decision n |
| `old.tex:N` | `adprov_paper.tex` line N at `24ac03f` (verified by `grep -n` on 2026-10-07) |
| `fw:<path>:N` | baseline framework file at `579a908` |

Every other report is cited by its path under `investigation/`.

---

## O.0 Summary of what this section decides

1. The AgentPROV paper is an **infrastructure-and-method paper**: a specified, versioned,
   evidence-qualified derivation from hash-pinned raw evidence to W3C PROV, shown on structurally different
   sources (the AgentDojo TraceLogger family and the Inspect AI AgentHarm sub-corpus, AD-06) with per-source
   information loss quantified as field-group coverage (R-57). The corpora are a secondary contribution. It is
   not a "first corpus" paper and not a security-results paper [DEC D12; PA §16].
2. The manuscript lives in a new local git repository at `3. AgentPROV paper/` with no remote for now
   [DEC D12], keeps Elsevier `cas-dc` + natbib + `cas-model2-names`, copies `refs.bib` and extends it
   (O.3).
3. Every number in the PDF comes from one typed value registry (`paper/values.json`) and reaches LaTeX
   only through the keyed accessor `\apstat{<scope>}{<name>}` or a generated table. Legacy `\Adp…` names
   exist only as a whitelisted alias layer with an explicit policy per name (O.3.4).
4. The generation pipeline is pin → data → frames → values → render → check → LaTeX, over N per-source
   AgentPROV corpora read through `agentprov.api` only, with caches keyed by corpus-manifest digests, claims that
   fail the build, and byte-deterministic `values.json`, `macros.tex` and tables (O.3.5–O.3.9). The generic
   statistics (counts, statements by evidence class, bundle and rule, unknown reasons, field-group coverage) come
   from the framework's `agentprov stats` (`src/agentprov/stats/`, AD-10 as ruled), not from a paper-side
   re-implementation. PDF byte determinism and the PROV form of the build record are deferred (AD-10 row 20).
5. No figure or table of the old paper is copied as a binary. Survivors are regenerated from AgentPROV
   corpora; six new figures and seven new tables are specified (O.4).
6. The old manuscript's open items (O.6) MUST be resolved or disclosed before any of its text, numbers or
   figures are reused.
7. The two challenges of r1 are ruled: **C-O1** (the paper's structurally different source) is accepted
   (AD-06, R-07, R-28; O.1.7), and **C-O2** (the name "Execution Record") keeps "AER" (AD-22, R-61; O.1.8).

---

## O.1 Contribution framing

### O.1.1 Thesis and paper type

The paper's thesis MUST be stated in the introduction in substance as follows:

> Execution records of LLM-agent security experiments can be turned into W3C PROV by a specified,
> versioned derivation in which every provenance statement states whether it was observed in the source,
> derived from it by a deterministic rule, or inferred under a stated method, cites the rule that produced
> it and points to the record field that justifies it. Policy claims (integrity, roles, taint, payload
> exposure) are kept out of the PROV facts. Applying the derivation to sources in structurally different
> formats shows how much provenance each source can support.

"Live" enters the thesis only after an approved, sealed, non-`test_only` live corpus exists (AD-08 as ruled;
U-10, U-18; NC-LIVE-02). Both live backends were fake-client tested in v0.1 (R-25). A real-model pilot, approved by
the user, ran `agentdojo` · `live`, `autodojo` · `live` and `agentdyn` · `live` on 2026-10-22 (D-722, D-729), but its corpora are working
corpora, not sealed, and live corpora cannot be sealed in this build, so the condition is not met.

> **D-991 (2026-10-29, user decision).** The title and abstract may name live runs as a capability of the framework
> that is tested, not measured. Every live *result* still requires the sealed live corpus above (U-18); the pilot is
> reported only as a test of the software.

The paper MUST NOT be framed as a data paper whose contribution is the number of traces
[PA §16: "Scale (trace counts) as a contribution … is not new data"]. The AgentDojo-PROV corpora and
findings (silent re-runs, checker defects, the entity-granularity limit of taint) are cited as prior work
and as the first source profile [PA §16 bottom line].

### O.1.2 Defensible claims versus novelty inflation

The claims lint (O.3.7) enforces the "Required wording" column. It runs the shared claims/lint library
`agentprov.adapters.registry.claims` (I.5.6), so the I.4 must-not-claim items bind the paper exactly as they bind
the README and the datasheets (R-27, R-45, R-58).

| Claim | Verdict | Evidence or condition | Required wording |
|---|---|---|---|
| Evidence-qualified derivation raw → AER → SEM → PROV with versioned rule ids | **Defensible (core)** | AgentDojo-PROV lacked exactly this: qualification (PA-D1, PA-D19), pinned source evidence (PA-D18) and a complete specification (PA-D4, PA-D20) [PA §16 item 1] | "every statement in the core bundle carries an evidence class, a rule id and a source pointer", i.e. "traceable statement by statement (rule + source pointer)". Only if the evidence-linkage check (D8 tier 4) resolves 100 % (claim `c1-linkage`) |
| Policy overlays kept out of PROV facts | **Defensible** | v2.3 encodes taint as plain `prov:used` (fw:agentdojo_prov/build_prov.py:462-477, both branches call `add_used`); PROV-O qualification cannot hedge [landscape/prov_semantics.md §0 items 2 and 4] | "kept in a separately attributed assessment bundle" |
| Validation stack with stated guarantees | **Defensible** | old §3.5 scoping was "exemplary" [PA §13 Keep]; tiers per D8 | each check named with what it establishes and does not |
| Multi-source normalisation with quantified per-source loss | **Defensible only after** DoD Q.11a passes (all 6 survey AgentHarm logs import, derive and validate end to end), so that the AgentDojo TraceLogger family and the Inspect AgentHarm sub-corpus both carry sealed executions (AD-06; O.1.7) | [PA §16 item 3]; NC-ALL-08 | exactly the registry-generated phrase "adapter-based core; demonstrated on *N* sources in *K* formats (single-agent, tool-calling traces)", emitted from `claims.coverage_phrase()` as the text value `all/coverage_phrase`; *N* and *K* also as `\apstat` values (claim `c3-coverage`) |
| Per-source information loss | **Defensible** | RQ2; R-57 | headline = **field-group coverage** (share of executions per field group that are O or D, against the fixed capability list of O.3.5); the observed share of statements is reported only as composition |
| Byte-identical regeneration of the v2.3 graphs by a compatibility profile | **Defensible** (regression result) if migration gates A1 (JCS), A2 (bytes) and B (compat graph bytes) pass (AD-02, AD-07) and the v2.3 checksum lists ship as raw artefacts or v2.3 is deposited (R-26; U-01; OM-1) | DEC D7 regression gate; J.3 | "regenerates *n* of *n* AgentDojo-PROV v2.3 graphs (commit 579a908 + published checksum lists) byte for byte from the AER alone", through a deterministic transcript/v1 view. "The native re-import supersedes the converted tree" only after a 0-mismatch pass of the full gate R claim gate (AD-07) |
| "Benchmark-agnostic" / "framework-agnostic" | **Inflation** as an empirical claim; allowed only as the core's *architectural design goal* (AD-08 as ruled) | AgentDyn, AutoDojo and ROPE share AgentDojo's task-suite interface or log format [PA §16; RF NOV-5, AR-11]; AgentHarm is itself a single-agent tool-calling loop and the future-framework test is self-authored (AD-08) | in the design sections only (`sec:principles`, `sec:adapters-model`), inside a design-goal block (O.3.7), with no counts or source names; every empirical coverage statement uses the registry-generated phrase of the row above (NC-ALL-08) |
| Extensible to a new framework without core change | **Defensible only as tested** (R-27; AD-15 as ruled) | 13 record kinds incl. the generic `activity` and `artefact` with EF rules G-ACT, G-USE, G-GEN and G-ASSOC (Addendum B B-1, AD-15); the future-framework test (D.12, DoD Q.3) asserts named PROV statements for a planner step, a memory write and read, a screenshot, a hand-off and a human approval; the Inspect importer lands with zero core changes or with the changes listed (DoD Q.3) | "tested on a self-authored toy format and on the Inspect importer (core changes listed)", plus the disclosed `aer/0.1` limits (an `activity` cannot generate a `message`; approvals authorise only tool executions; in-file branches have no encoding) |
| Live capture | **Inflation** without an approved, sealed, non-`test_only` live corpus (AD-08 as ruled; U-10, U-18) | both live backends fake-client tested in v0.1 (R-25); the 2026-10-22 real-model pilot (D-729) ran working corpora, not sealed (NC-LIVE-02); stock behaviour only for sessions whose instrumentation holds no `request_modifying` or `harness_policy` item, i.e. the default `native` LLM element, not `gateway_compat` (AD-09; NC-LIVE-01) | any live result only after U-18; "Live" in the title as a tested capability of the framework (D-991); otherwise the live backends are described as design and tested code |
| Reproducibility and verifiability | **Defensible only in scoped form** (R-26, R-58) | D9 recompute; content-addressed raw store | "derivation-reproducible"; "integrity-verifiable; authenticity rests on pinned origins where they exist (not for `agentdojo-prov-v2` or live campaigns)". Bare "reproducible" and "independently verifiable" are banned |
| "First public PROV corpus / framework" | **Inflation** | Anchor-Level pilot (9 PROV-O graphs), TRACE, PROV-AGENT, NovaFabric and F(AI)²R exist; the 2026-09-30 search excluded software (criterion I4) [RF NOV-1; PA §16] | banned unless the re-run search (app:search, O.6 OM-22) supports a scoped claim |
| "Lossless" for imported logs | **False by construction** | imports are lossy; even live capture omitted tool schemas, wire request and served model [PA §16]; NC-ALL-03 | "source-preserving: raw bytes are retained and hash-pinned, and the record declares what it does not hold"; decoding is "value-preserving under the JSON data model" (R-58) |
| "Ground truth" for the injection marker | **Inflation** | the marker is a derived heuristic (PA-D19) | "derived payload marker (algorithm `<rule id>`)"; the reference is the registered vector → payload map plus the checker outcome. The attack, target and defence ids, payload fixtures and outcomes are configuration provenance in the core (AD-11); core bundles MUST NOT be called a blind input for detectors (NC-PROV-01) |
| "W3C PROV-O conformant" / "PROV-CONSTRAINTS valid" | **Inflation** without scope | conformance = library round-trip + completeness + a constraint subset, no normalisation, no independent implementation [RF SEM-3] | name the exact checks |
| Integrity labels and roles as "security semantics" contribution | **Inflation** | λ/ρ is a tool-name lookup table [PA §16] | the contribution is their separation into SEM and the assessment bundle |
| Detection capability | **Inflation** | the only detector was a reachability floor (F1 0.26 / 0.58) [PA §16] | no detection claims |
| Observed/derived/inferred as a new concept | **Inflation** | PROV-O qualified patterns and `wang2026traces` cover evidence typing [PA §16] | novelty = application to agent-security provenance, validation, measured per-source effects [landscape/prov_semantics.md §6 implication 2] |
| The name "AgentPROV" | Not a contribution | [PA §16] | — |

### O.1.3 Candidate title, short title, keywords

- **Title (recommended; requires DoD Q.11a, AD-06):** *AgentPROV: Evidence-Qualified W3C PROV Provenance
  from Released Logs of LLM-Agent Security Experiments*.
- **Title variant with "Live Capture"** (originally only with an approved, sealed, non-`test_only` live corpus; AD-08
  as ruled, U-10, U-18, NC-LIVE-02; since D-991 "Live" may name the framework's tested capability without one): *AgentPROV: Evidence-Qualified W3C PROV Provenance from Live Capture and
  Released Logs of LLM-Agent Security Experiments*.
- **Title if DoD Q.11a does not pass** (the Inspect AgentHarm source is not sealed): *AgentPROV:
  Evidence-Qualified W3C PROV Provenance for AgentDojo-Family LLM-Agent Executions*.
- `\shorttitle{AgentPROV: Evidence-Qualified Provenance for LLM-Agent Executions}`;
  `\shortauthors{N. Jones et al.}` (authors as in old.tex:68-77; ORCIDs and CRediT still to confirm, O.6
  OM-23).
- Keywords: data provenance; W3C PROV; LLM agents; prompt injection; evidence qualification; execution
  traces; reproducibility.

### O.1.4 Abstract skeleton

The abstract MUST be at most `abstract_max_words` words (default 250; the old abstract was about 264
words against a typical Elsevier cap of about 250 [RF PRS-4]). Every number is a value key. Bracketed
items are conditional on the evaluation outcome; the corresponding claim ids are listed in O.1.6.

```latex
\begin{abstract}
Security research on large language model (LLM) agents produces execution records in benchmark-specific
formats that differ in what they record and say nothing about how certain each recorded fact is.
% gap: no evidence status in existing agent-provenance work [landscape/prov_semantics.md §6]
We present AgentPROV, a specification and reference implementation that derives W3C PROV from
hash-pinned raw evidence through a source-preserving canonical record, the AgentPROV Execution Record.
Every provenance statement carries an evidence class (observed, derived or inferred), the versioned rule
that produced it, and a pointer to the record field that justifies it; policy claims such as integrity
labels and taint are kept out of the provenance facts in a separately attributed assessment bundle.
% claim: c3-coverage   (text = claims.coverage_phrase(); emitted only after DoD Q.11a)
AgentPROV has an \apstat{all}{coverage_phrase}[, including an approved live-capture corpus (U-18)]. We
quantify what each source loses as field-group coverage, the share of executions whose field group is
observed or derived: it ranges from \apstat{all}{fg_coverage_pct_min}\% to
\apstat{all}{fg_coverage_pct_max}\% across sources.
% claim: c4-semdiff-taint   (two trees, never pooled; values from the gate-E reports only)
Re-deriving the \apstat{legacy-compat}{n_total} AgentDojo-PROV v2.3 graphs shows that
\apstat{semdiff-release}{used_policy_pct}\% (generated) and \apstat{semdiff-converted}{used_policy_pct}\%
(converted) of their usage edges were policy assertions encoded as facts;
% used_policy_pct = 100 * R6-only used edges / all used edges, two decimals (gate-E report values; J.3.6)
% claim: c2-compat
a compatibility profile regenerates \apstat{legacy-compat}{n_identical} of them byte for byte from the
record alone (framework commit \apstat{spec}{baseline_commit_short} and its v2.3 checksum lists).
Validation establishes [list]; it does not establish [list]. Code, specifications and per-source corpora
are released under [licences] at [URLs/DOIs].
\end{abstract}
```

Rules for the abstract: no "first", "lossless", "ground truth", bare "reproducible" or "agnostic" (O.1.2; the
design-goal exception of AD-08 does not extend to the abstract); the coverage sentence is the exact
`coverage_phrase()` text (NC-ALL-08); the headline loss metric is field-group coverage, and the observed share
of statements appears only as composition (R-57); no DOI that is not minted for the version described (O.6
OM-1); the C2 sentence requires OM-1 to be cleared (v2.3 checksum lists shipped, R-26, or v2.3 deposited, U-01; the deposit exists since 2026-10-10, D-900);
the validation sentence MUST name the checks.

### O.1.5 Research questions

- **RQ1 — Specification and determinism.** Can executions from released logs of different agent-security
  frameworks (and, after U-18, from live capture) be represented in one source-preserving canonical record
  and mapped to W3C PROV, so that every statement is evidence-qualified, traceable to raw evidence, and
  reproduced bit for bit on re-derivation?
- **RQ2 — Information loss per source.** What provenance does each source support and what does it lose,
  measured as (a) **field-group coverage**, the headline: for each field group of the fixed capability list
  (O.3.5), the share of executions whose group is observed or derived (R-57); (b) for the same groups, the
  share of executions with a declared unknown, by reason (seven reasons, incl. `overwritten`); and (c) as
  composition only, the proportions of observed, derived and inferred statements per bundle?
- **RQ3 — Consequences for existing graphs.** Which statements of the AgentDojo-PROV v2.3 graphs survive
  as provenance facts under evidence qualification, and which become inferences, policy assessments,
  ordering attributes or nothing? All counts and dispositions come from the gate-E reports (J.3.6; R-33).
- **RQ4 (conditional, reduced) — Validity of the derived payload marker.** How does the derived payload marker
  agree with the registered vector → payload map? RQ4 is included only if the SEM marker algorithm is
  specified (O.6 OM-3); otherwise the topic moves to sec:limitations. Logged-versus-replayed outcomes are out
  of scope: outcome replay is deferred (AD-10 row 2; RESOLUTIONS §1.3, O row "RQ4").

These replace the old RQs (old.tex:315-327). The old RQ1 becomes RQ1+RQ2 with evidence qualification
and loss. The old RQ2 ("exact relative to a … policy") is tautological and is replaced by RQ4. The old
RQ3 (exposure across models) is dropped as benchmark-behaviour science [PA §13 Rewrite, §12 row
"Characterisation"].

### O.1.6 Contributions mapped to evidence

Each contribution sentence in sec:intro MUST carry a `% claim:<id>` comment. The listed gate is a
registered claim (O.3.7) that fails the build when the data do not support the sentence.

| C | Contribution (draft wording) | Evidence the framework produces | Value keys (examples) | Gate (build fails unless) |
|---|---|---|---|---|
| C1 | A specification: the canonical record `aer/0.1` (13 record kinds, incl. the generic `activity` and `artefact`, Addendum B B-1), the standoff annotations `sem/0.1`, the provenance specification `agentprov-prov/0.1` with versioned rule catalogues and the `apv` ontology 0.2.0. Every core statement carries evidence class, rule and source pointer; non-PROV claims sit in an attributed assessment bundle [DEC D2, D6, D7; AD-15] | published JSON Schemas (`aer-0.1`, `capture-0.1`, `corpus-0.1`; AD-10 row 13); the rule catalogues as package resources at the version each corpus records (the byte copies in a corpus `rules/` are a record, digest-compared, AD-14); ontology file `vocab/apv-0.2.ttl` | `spec/aer`, `spec/prov_spec`, `spec/n_rules_observed`, `spec/n_rules_derived`, `spec/n_rules_inferred`, `<src>/linkage_resolved_pct` | `c1-linkage`: `linkage_resolved_pct == 100.0` for every corpus (read from the corpus `validation/`); `c1-rules-declared`: every rule id used in any corpus is declared in the catalogue at the recorded version |
| C2 | A reference implementation whose validation tiers state what each establishes; deterministic re-mapping and re-derivation ("derivation-reproducible"); a compatibility profile that regenerates *n* of *n* AgentDojo-PROV v2.3 graphs (commit 579a908 + published checksum lists) byte for byte from the AER alone, through a deterministic transcript/v1 view [DEC D7, D8; AD-02, AD-07; R-04, R-26] | per-tier results per execution (`pass\|fail\|skipped\|not_applicable`, read from the sealed corpus `validation/`, R-64), recompute digests, migration gate reports A1 (JCS), A2 (bytes) and B (compat graph bytes) | `<src>/tier2_aer_pass`, `<src>/tier4_prov_pass`, `<src>/n_skipped_checks`, `<src>/recompute_identical_pct`, `legacy-compat/n_identical`, `legacy-compat/n_total` (from the gate-B report) | `c2-compat`: `n_identical == n_total == legacy-adprov-v23/n_graphs_total` (frozen 35,691 [baseline/BASELINE.md §0]), and the pinned `agentdojo-prov-v2` corpus holds the v2.3 checksum lists as raw objects or v2.3 is deposited (OM-1; R-26; U-01); `c2-recompute`: 100 %; skipped checks are reported and never counted as passes [DEC D8] |
| C3 | Per-source information loss, measured as field-group coverage against a fixed capability list, over the sources of the registry-generated coverage phrase (RQ2; R-57) | `fig:infoloss` (headline), `fig:evidence` (composition), `tab:compat`, `tab:capability`; the framework's `agentprov stats` field-group and unknown-reason tables (AD-10 as ruled) | `all/coverage_phrase` (text), `all/n_sources_with_executions`, `all/n_formats`, `<src>/fg_coverage_pct`, `<src>/fg_<group>_coverage_pct`, `all/fg_coverage_pct_min`, `all/fg_coverage_pct_max`; composition `<src>/core_observed_pct` | `c3-structural`: DoD Q.11a has passed and the corpus `ast-survey-agentharm` (dialect `inspect.eval`, outside the AgentDojo lineage) holds sealed records with `unit == agent_execution ∧ execution_observed` (AD-06); `c3-coverage`: *N* and *K* in `coverage_phrase()` equal the counts computed from the corpora pinned in `paper.toml`. If either fails, the C3 wording MUST switch to the AgentDojo-family scope (O.1.3) |
| C4 | A semantic diff of AgentDojo-PROV v2.3 against `agentprov-prov/0.1` over the frozen baseline (RQ3) [DEC D7 "documented semantic-diff"] | the gate-E reports `migration/semdiff/semdiff-<tree>.json`, generated from `src/agentprov/prov/compat/semdiff-map.toml` (J.3.6; R-33); `tab:semdiff`, `fig:semdiff`, app:semdiff | `semdiff-release/semdiff_used_taint_to_assessment`, `semdiff-release/used_policy_pct`, `semdiff-converted/used_policy_pct` (per tree; never pooled) | `c4-totals`: the report has `unmapped == 0` and every v2.3 class total equals its frozen legacy count (e.g. sink→⊥ taint pairs 41,066 generated [RF SEM-2; J.3.6], `wasInformedBy` 72,633 / 68,212 [PA §15]); numbers and dispositions come only from the gate-E report |
| C5 (secondary) | Versioned, manifest-hashed per-source corpora with lineage and deduplication, raw evidence included or referenced as each licence allows [DEC D3, D9; AD-20] | corpus manifests (`corpus.json`), `raw/origins.jsonl`, the owner declarations in each profile's `[lineage]`, `source_key` deduplication, `fig:lineage`, `tab:versions`, `tab:fair`. Collection manifests are deferred (AD-10 row 6) | `<src>/n_executions` (`unit == agent_execution ∧ execution_observed`), `<src>/n_outcome_only`, `<src>/raw_included`, `lineage/<edge>_n` | `c5-dedup`: overlap counts derived from the manifests and origins equal the investigation's measured overlaps, or a recorded divergence explains each difference (O.4.3 F5) |

RQ ↔ C: RQ1 ↔ C1, C2; RQ2 ↔ C3; RQ3 ↔ C4; RQ4 ↔ app evidence only. C5 supports all.

### O.1.7 Source scope of the paper and the structurally different requirement

The sources the paper may report are exactly those with a sealed corpus at the pinned manifest digests
in `paper.toml` (O.5). Status words in the paper MUST equal the registry `agentprov.adapters.registry`, the sole
status store (two axes per part: evidence availability `yes|partial|no`, and implementation status
`supported|partial|planned|not_possible` with its caveat; I.1.1 replaces the D11 table) [R-15; R-45]. They are
compared against the registry by the `tab:compat` gate (O.4.4), never against D11. A spec status is a v0.1
target; the paper uses the **gated** registry value, and `supported` additionally needs a full pinned-snapshot
import (R-15). Execution counts use only records with `unit == agent_execution ∧ execution_observed`;
outcome-only records and scenarios are reported separately (R-28; NC-ALL-13).

> **Resolved (AD-06 / R-07, R-28; C-O1 accepted):** the paper's structurally different sources are the AgentDojo
> TraceLogger family and the Inspect AI `.eval` AgentHarm sub-corpus of the Agent Security Tools Survey (corpus
> `ast-survey-agentharm`, producer band `inspect_ai 0.3.247.dev69`). The Inspect importer is normative in v0.1
> and, together with the TraceLogger `v0.k11` importer, is the `aer/0.1` + `capture/0.1` freeze gate (phase 6).
> STAC is a separate scenario population (`unit: scenario`; import `planned`), never counted as executions.
> Coverage wording waits for DoD Q.11a; if it does not pass, title, abstract and C3 use the AgentDojo-family
> scope (O.1.3) and "structurally different" MUST NOT appear in the paper.

**Basis of the ruling** (evidence of the r1 challenge, kept):
1. STAC as released is not an execution corpus. In 482 of 483 records the assistant turns are scripted by STAC's
   generator, the last message is an unanswered attack prompt, and no target-agent response, judge score or
   outcome is released. Record 139 holds a 3-turn agent trajectory without model identity. The investigator
   recommends `planned`, and lists "the target-agent execution graph for 482 cases" as not derivable
   [sources/multiturn-agent-attack.md §0; `multiturn-agent-attack.finding.json` fields `recommended_status`,
   `provenance_impossible`]. A6 confirms: scenario records, not executions.
2. Every other v0.1 import source (AgentDojo upstream, ROPE, AgentDyn, DRIFT, Mandate, the survey's AgentDojo
   runs) is AgentDojo TraceLogger JSON [DEC D4]; `transcript/v1` and `capture/0.1` record AgentDojo executions.
   These are dialect differences within one lineage [PA §16].
3. The structurally different source with real executions: the Agent Security Tools Survey's AgentHarm
   sub-corpus, 1,056 Inspect AI samples in six `.eval` logs with per-call raw request and response, generation
   config, reasoning, timestamps, tool events with ids and judge calls [sources/agent-security-tools-survey.md
   §0, §5]. The artefact is CC BY 4.0; AgentHarm data are "MIT with an additional clause" that restricts use to
   improving AI safety or security, and derived records must carry that clause
   [`agent-security-tools-survey.finding.json` fields `license`, `redistribution`]. It is therefore a separate
   restricted-use corpus (U-05; AD-20). Inspect is a fast-changing, framework-internal format
   [landscape/trace_formats.md §0 item 3]; the logs record `inspect_ai 0.3.247.dev69+g53c1fa98b` [survey report
   §5]. The survey's primary origin is git commit `89c4db2c…`; both version DOIs are alternative origins, and
   the concept DOI is cited with the version fetched (R-62).

**Consequences for the paper.**
- RQ2 gets its sharpest contrast: model-input context is OBSERVED for the Inspect source (raw requests), at
  best DERIVED for AgentDojo native imports [landscape/prov_semantics.md §8.2 rule R-USE-CTX], and INFERRED
  (inference bundle) for the released AgentDojo-PROV v1 transcripts unless the user supplies a digest-pinned
  generation-time harness (AD-05; U-01).
- AgentHarm is not a prompt-injection benchmark: the `payload` field group and the injection-related SEM
  annotations are `not_applicable` there (a group that cannot exist for the source, R-57), not missing.
- AgentHarm's judge spans are recorded as `judge` actors with `judgement.generated_by` (R-37); any `activity`
  records the importer emits (e.g. compaction) appear in the paper's generic-kind counts (AD-15).
- A live `capture/0.1` pilot also yields OBSERVED context, but needs the user's keys and consent (U-10) and the
  user's approval of its results (U-18); it is not a substitute for the Inspect source.
- The Inspect importer is the paper's only external evidence for extensibility besides the self-authored toy
  format: the paper lists every core change it required (DoD Q.3; R-17, R-27).

### O.1.8 Terminology and naming

The paper uses these terms consistently; `tab:terms` (hand-written, no numbers) defines them:
execution, raw artefact, source, corpus, adapter (reader + mapper + source profile), record, record kind
(13 kinds, incl. the generic `activity` and `artefact`, AD-15), unit (agent execution, outcome-only record,
scenario; R-28), evidence class (observed, derived, inferred), attesting party (`by`), rule id, unknown reason
(seven, incl. `overwritten`), bundle (core, inference, assessment), semantics profile, compatibility profile,
issue, field group, field-group coverage, poolable.
"Trace" and "transcript" are kept only for AgentDojo-PROV's `transcript/v1` [DEC D1].

The paper's tooling types the *basis of a statistic* (derived, inferred, external, legacy-frozen, spec) as
`ValueBasis`, not `EvidenceLevel`, so that it cannot be confused with the evidence class of a provenance
statement (R-64; O.3.5).

> **Resolved (AD-22 / R-61; C-O2):** keep `aer/0.1` and the name "AgentPROV Execution Record (AER)", always
> expanded; cite `vispute2026aer` (arXiv 2603.21692) at first use and state the difference (typed records with
> evidence classes and raw-evidence locators versus per-step reasoning fields). The name is forwarded to the user
> (U-15) for a final say before the phase-6 freeze; if it changes, it changes before the first corpus is sealed.

Basis: [landscape/prov_semantics.md §6] lists **Agent Execution Record** (Vispute, Kadam; arXiv 2603.21692), a
non-PROV model of reasoning provenance with intent, observation and inference fields per step. Only a
second-hand summary of its abstract was read; the PDF MUST be read before the paper cites it (OM-24).

---

## O.2 Section-by-section mapping

### O.2.1 Label conventions

1. Labels MUST be placed only on sectioning commands, floats and equations. The old paper put
   `sec:priorsearch` and `sec:mlexport` on `\paragraph`, so they resolved to the enclosing section's
   number [PA §2]. The lint (O.3.7) rejects a `\label` that follows `\paragraph`.
2. Prefixes: `sec:`, `app:`, `fig:`, `tab:`, `eq:`. Claim ids (`c1-linkage`, …) live in `% claim:`
   comments, not labels.
3. An old label is reused only when the section keeps its meaning (O.2.2 "Keep" rows). A rewritten
   section with a different meaning gets a new label, so stale cross-references fail instead of resolving
   silently.
4. Claim descriptions and lint messages refer to `\label` keys, never to printed numbers (FP-#6).

### O.2.2 Old → new mapping

"Old lines" are from [PA §2]. Actions: **Keep** (meaning kept, text revised), **Rewrite** (new content
in the same place), **Merge**, **Move**, **Drop**, **Add**.

| Old § (lines) | Old label(s) | Action | New label(s) | Notes |
|---|---|---|---|---|
| Abstract (81-126) | — | Rewrite | — | O.1.4. Remove the v2.2 DOI TODO (old.tex:123-125), "lossless" (old.tex:92), the scale claim |
| 1 Introduction (136) | `sec:intro`, `tab:terms`, `fig:overview` | Rewrite | `sec:intro`, `tab:terms`, `fig:pipeline` | New gap statement, RQ1-RQ4, C1-C5. `fig:overview` (matplotlib boxes with hard-coded "AgentDojo", "transcript/v1" [FP §3.6]) is replaced |
| [P] Roadmap (329) | — | Keep | — | content rewritten |
| 2 Background (369) | `sec:related` | Keep | `sec:related` | restructured into six subsections |
| 2.1 W3C PROV (372) | `fig:provkey` | Keep + extend | `sec:bg-prov`, `fig:provkey` | Add what PROV does and does not license (no transitivity of `wasInformedBy`, Inference 6, qualification cannot hedge, bundles, `mentionOf`) [landscape/prov_semantics.md §0 items 1-2] |
| 2.2 Provenance for security (428) | — | Keep, trim | `sec:bg-secprov` | analogy kept; fix lineage overstatements found by SR-AUD [RF PRS-8] |
| 2.3 LLM agent security benchmarks (445) | — | Rewrite | `sec:bg-benchmarks` | Now "benchmarks and what they release": positions every source of the registry (the row count is a generated value, R-58) by evidence released, with the registry's evidence-availability axis. The ROPE description (old.tex:464-469) is inaccurate about the grid and MUST NOT be reused [sources/rope.md §5.4] |
| [P] Why re-express executions as W3C PROV? (477) | `tab:agentdojo-compare` | Rewrite + Move | paragraph in `sec:bg-formats` | the comparison against AgentDojo logs alone is replaced by `tab:formats` |
| 2.4 Provenance of ML systems and agents (561) | `tab:related` | Rewrite | `sec:bg-agentprov`, `tab:related` | Add PROV-AGENT's invocation/tool split, LLM-inferred dependency graphs (AgentArmor, AuthGraph, ProvenanceGuard), CaMeL by construction, FIDES, context attribution. All summaries are second-hand and MUST be checked against the PDFs [landscape/prov_semantics.md §6, §12 item 6] |
| [P] Provenance of agentic workflows (654) | — | Merge | `sec:bg-agentprov` | |
| [P] Public artefacts near this one (680) | `sec:priorsearch` (on `\paragraph`) | Rewrite | `sec:priorsearch` on a `\subsection` | search re-run, software included (O.6 OM-22) |
| 2.5 What existing agent datasets release (710) | `sec:datasets`, `tab:datasets` | Merge | into `sec:bg-benchmarks`; `tab:datasets` superseded by `tab:compat` | |
| — | — | Add | `sec:bg-formats`, `tab:formats` | trace formats (OTel GenAI, Inspect, AgentDojo native, `transcript/v1`, ATIF, …) from [landscape/trace_formats.md §3.12] |
| 3 The AgentDojo-PROV framework (823) | `sec:framework` | Rewrite, split | `sec:principles`, `sec:aer`, `sec:adapters`, `sec:prov`, `sec:validation` | |
| 3.1 Design principle (826) | `sec:principle` | Keep (generalised) | `sec:principles` | "separate capture from interpretation" becomes "raw evidence is immutable; every derivation is a pure, versioned function" [DEC D0]; add "declare, never invent" [PA §13 Keep] and the untrusted-input stance |
| [P] What the transcript holds (854) | — | Rewrite | `sec:aer-scope` | scoped completeness per source; the tri-state `record_complete` idea generalised [PA §13 Keep] |
| 3.2 Capture layer (883) | `sec:capture`, `fig:capture` | Rewrite | `sec:live`, `fig:capture` | `capture/0.1` written by `agentprov_capture` in a spawned backend worker (AD-01); default LLM element `native` (stock, recorded at the transport level), `gateway_compat` opt-in and declared (AD-09); `ProvObserver` removed; harness deviations recorded as declared instrumentation [DEC D5]. Live results only after U-18. The "none alters what the model sees" passage MUST be rewritten (O.6 OM-5) |
| 3.3 Derived provenance graphs (998) | `sec:derivation`, `tab:mapping` | Rewrite | `sec:prov-model`, `tab:rules` (generated) | decomposed model and bundles [DEC D7]. The hand-written `tab:mapping` (incomplete for attributes, PA-D20) is replaced by a table generated from the rule catalogue |
| [P] Determinism and edge cases (1142) | — | Rewrite | `sec:aer-ids` | positional ids; provider ids are attributes [DEC D2] |
| 3.4 Integrity labels and activity roles (1194) | `sec:labels`, `eq:lambda`, `eq:rho`, `tab:policy`, `tab:audit` | Move | general part to `sec:semantics`; tables to `app:agentdojo-profile` | λ/ρ become SEM annotations: three-valued, fail-closed integrity [DEC D6] |
| [P] Granularity and mixed content (1311); [P] Auditing the assignment (1343) | — | Move | `app:agentdojo-profile` | audit method kept; "closed inventory" and "static coverage" claims dropped (OM-10, OM-11) |
| 3.5 Standards conformance (1394) | `sec:conformance`, `tab:checks` | Rewrite | `sec:validation`, `tab:validation` | the "what it does and does not establish" passage (1461-1521) is kept in substance [PA §13 Keep] |
| 3.6 Converting existing run logs (1523) | `sec:conversion` | Rewrite | `sec:import` | reader + mapper + profile [DEC D4]; "declare, never invent" without sentinels (no `"0"` timings) [DEC D2] |
| 4 The corpora (1553) | `sec:corpus` | Rewrite | `sec:corpora` | per source, layout per DEC D9, poolability rule |
| 4.1 Generation procedure (1561) | `tab:models`, `tab:generation`, `tab:composition`, `fig:composition` | Move | `app:sources` (generated per-source datasheet rows) | AgentDojo-PROV's generated corpus becomes one source among several |
| [P] Suite imbalance; [P] Reproducibility (1673, 1689) | — | Keep (stance only) | `sec:corpora` | "the reproducible object is the corpus, not the generation run" [PA §13 Keep] |
| 4.2 Corpus layout and ground truth (1717) | — | Rewrite | `sec:corpus-layout` | D9 layout; "ground truth" wording removed (OM-3) |
| 4.3 The converted corpus (1743) | `sec:converted`, `tab:corpora`, `fig:coverage` | Rewrite + Move | `app:sources`, `tab:sources` | the AgentDojo native import (corpus `agentdojo-upstream`) pinned to upstream commit `c274885…` (18,241 blobs incl. 7 Mixtral) [DEC D3; R-32]. The converted v2.3 tree is a compatibility oracle read by migration gate R, not a corpus |
| 5 Corpus characterisation (1931) | `sec:characterisation` | Replace | `sec:evaluation` | |
| 5.1 The generated corpus (1937) | `sec:chargenerated`, `tab:graphstats`, `fig:sizes`, `fig:mix`, `fig:roles`, `fig:marker`, `tab:outcomes`, `fig:outcomes`, `tab:graphdist` | Drop (behaviour); generalise (structure) | `fig:sizes`, `tab:graphdist` per source | model rankings and outcomes are AgentDojo results, not provenance results [PA §13 Drop] |
| 5.2 The converted corpus (2241) | `sec:charconverted`, `fig:convoutcomes` | Drop | — | |
| 5.3 Comparing the two corpora (2379) | `sec:comparison`, `tab:comparable`, `fig:cmpsizes`, `fig:cmputility` | Drop; keep the never-pool rule | poolability in `sec:corpora` | |
| 6 Known artefacts (2512) | `sec:artefacts`, `tab:artefacts` | Keep (generalised) | `sec:artefacts`, `tab:issues` | excluded/unscored/flagged taxonomy and the "logged vs replayed" distinction kept as a stance [PA §13 Keep], with no replayed outcomes in v0.1 (AD-10 row 2); counts from `executions.jsonl` status/issues (register codes) [DEC D9]; outcome-only records counted separately (R-28) |
| 7 Downstream baseline (2732) | `sec:baseline`, `tab:baseline`, `tab:ablation`, `tab:blindspots`, `fig:cmpbaseline` | Drop | — | cite AgentDojo-PROV; detection claims banned (O.1.2) |
| 8 Intended uses (2976) | `sec:uses`, `sec:mlexport` (paragraph), `tab:mlsplit` | Rewrite | `sec:uses` | ML export deferred (AD-10 row 1); core bundles carry configuration ground truth and are not a blind input for detectors (AD-11; NC-PROV-01); consumer-safety note added (OM-28) |
| [P] Reusing host-provenance detectors (3094) | — | Keep (short) | `sec:uses` | |
| 9 Broader impact (3113) | `sec:impact` | Keep, update | `sec:impact` | add per-source licences and payload exposure of LLM consumers |
| 10 Limitations (3194) | `sec:limitations`, `tab:limits` | Rewrite | `sec:limitations`, `tab:limits` | |
| 11 Availability and FAIR (3461) | `sec:availability`, `tab:fair` | Rewrite | `sec:availability`, `tab:fair` (generated), `tab:versions` | versions per DEC D9 |
| 12 Answers to the RQs (3597) | `sec:answers` | Rewrite | `sec:answers` | |
| 13 Conclusion (3716) | `sec:conclusion` | Rewrite | `sec:conclusion` | |
| CRediT; competing interests (3794, 3801) | — | Keep | — | confirm (OM-23) |
| App. A Example graph (3835) | `app:example`, `tab:provkey`, `fig:example` | Keep, regenerate | `app:example`, `tab:provkey`, `fig:example` | the same execution in v2.3 and in `agentprov-prov/0.1`: the `agentprov-prov/0.1` panel rendered with the framework's `agentprov render`, the v2.3 panel drawn by `agentprov_paper.render.figures` (AD-10 as ruled; O.4.3 F6) |
| App. B Tool sets (3953) | `app:toolsets`, `tab:toolsets` | Move | `app:agentdojo-profile`, `tab:toolsets` | generated from the semantics profile `agentdojo.suites` (package resources at the version the corpus records, AD-14), not by importing `agentdojo` (removes the build dependency, FP §3.2) |
| App. C Prior-corpus search (3977) | `app:search`, `tab:searchyield`, `tab:searchpatterns`, `tab:searchartefacts` | Keep protocol, re-run | `app:search`, same tables | include software; fix the format row (PA-D21) |
| App. D Converted corpus detail (4125) | `app:converted`, `tab:convattacks`, `tab:convpipelines`, `tab:convbounds`, `tab:convpublished` | Drop, except `tab:convpublished` as an optional import-fidelity check (U-11: keep only with the gap of up to 6 pp disclosed, OM-20) | `app:sources` | published numbers become profile data with citations [FP §7.7 item 5] |
| — | — | Add | `sec:adapters-new`, `app:rules`, `app:semdiff`, `app:sources`, `app:agentdojo-profile`, `app:legacy` | `sec:adapters-new`: the generic `activity`/`artefact` kinds, the future-framework test and the Inspect importer's list of core changes (AD-15; DoD Q.3; R-17, R-27) |

### O.2.3 Target outline of `agentprov_paper.tex`

```
Abstract, keywords
1  Introduction                                         sec:intro          tab:terms, fig:pipeline
2  Background and related work                          sec:related
   2.1 W3C PROV: what it licenses and what it does not  sec:bg-prov        fig:provkey
   2.2 Provenance for security                          sec:bg-secprov
   2.3 Agent-security benchmarks and what they release  sec:bg-benchmarks
   2.4 Execution trace formats                          sec:bg-formats     tab:formats
   2.5 Provenance of agents                             sec:bg-agentprov   tab:related
   2.6 Prior artefacts                                  sec:priorsearch
3  Design principles and threat model                   sec:principles
4  The AgentPROV Execution Record                       sec:aer
   4.1 Records, envelope and evidence classes           sec:aer-records
   4.2 Identity, order and unknowns                     sec:aer-ids
   4.3 What a record holds, per source; units           sec:aer-scope
   4.4 Raw evidence and digests                         sec:aer-raw
5  Adapters                                             sec:adapters       tab:compat
   5.1 Readers, mappers and source profiles             sec:adapters-model
   5.2 Live capture                                     sec:live           [fig:capture, only after U-18]
   5.3 Imports                                          sec:import
   5.4 Adding a framework: generic records and tests    sec:adapters-new
6  Semantics and provenance                             sec:prov
   6.1 Semantic annotations                             sec:semantics
   6.2 Decomposed model, bundles and rules              sec:prov-model     tab:rules
   6.3 The adprov-v2.3 compatibility profile            sec:compat
7  Validation                                           sec:validation     tab:validation
8  Corpora, versions and lineage                        sec:corpora        tab:versions, fig:lineage
   8.1 Layout                                           sec:corpus-layout
9  Evaluation                                           sec:evaluation
   9.1 Specification and determinism (RQ1)              sec:eval-rq1
   9.2 Per-source information loss (RQ2)                sec:eval-rq2       fig:evidence, fig:infoloss, fig:sizes, tab:graphdist
   9.3 Re-deriving AgentDojo-PROV v2.3 (RQ3)            sec:eval-rq3       tab:semdiff, fig:semdiff
   9.4 Derived payload marker (RQ4, conditional)        sec:eval-rq4
10 Known artefacts and issue handling                   sec:artefacts      tab:issues
11 Intended uses                                        sec:uses
12 Broader impact                                       sec:impact
13 Limitations and threats to validity                  sec:limitations    tab:limits
14 Availability and FAIR                                sec:availability   tab:fair
15 Answers to the research questions                    sec:answers
16 Conclusion                                           sec:conclusion
CRediT; Declaration of competing interest
References (\balance)
\onecolumn \appendix
A  Example execution in both semantics                  app:example        fig:example, tab:provkey
B  Rule catalogue                                       app:rules
C  Semantic diff in full                                app:semdiff
D  Sources: profiles and per-source detail              app:sources        tab:sources, tab:capability, [tab:convpublished]
E  The AgentDojo semantics profile                      app:agentdojo-profile  tab:policy, tab:toolsets, tab:audit
F  Prior-artefact search                                app:search         tab:searchyield, tab:searchpatterns, tab:searchartefacts
G  AgentDojo-PROV v2.3 as prior work                    app:legacy
```

Content rules for the sections that Addendum B changes:
- `sec:aer-records` presents the 13 kinds of Addendum B B-1. The generic `activity` (`type` = `<ns>:<name>`,
  `actor`, `scope`, `inputs`, `t`, `status`, `label`) and `artefact` (`type`, `content` | `content_ref`, `sha256`,
  `media`, `generated_by`) are described as the escape for execution facts that no specialised kind fits;
  specialised kinds stay preferred, and adapters MUST NOT use `activity` for something an existing kind
  represents (AD-15 as ruled; C.3.13–C.3.14).
- `sec:prov-model` names the generic rules G-ACT (typed `prov:Activity`), G-USE (`used` per input, at the class
  of the input link), G-GEN (`wasGeneratedBy` from `artefact.generated_by`) and G-ASSOC, and states that they take
  part in the Inference-6 closure over named activities (AD-15; AD-19(c)).
- `sec:adapters-new` reports the future-framework test (D.12; DoD Q.3) as named PROV statements for the planner
  step, the memory write and read, the screenshot, the hand-off and the human approval, or as named, disclosed
  gaps; and lists every core change the Inspect importer needed (or states that there were none). It is a
  design-and-test section: no empirical coverage wording beyond the coverage phrase (NC-ALL-08).
- `sec:live` describes the backends as tested code ("fake-client tested; a real-model pilot run, not sealed") unless an approved,
  sealed, non-`test_only` live corpus exists (U-18); `fig:capture` appears only in that case.
  Since D-991 the section may describe live runs in full as a tested capability (what a run records, backends,
  attacks, defences, endpoints, safeguards, and how the capture path was tested), with no live results.

### O.2.4 Rules for reusing old text

1. A paragraph MAY be copied from `adprov_paper.tex` only if it is entered in the reuse ledger in
   `MAINTAINING.md` (old line range, new label, O.6 items checked, date).
2. A reused paragraph MUST have every number re-bound to a value key. Numbers about AgentDojo-PROV itself
   (prior work) MAY use the legacy alias layer (O.3.4) and MUST then cite `adprov2026corpus` and state
   which corpus state they describe (OM-1).
3. Passages listed in O.6 as "do not reuse" MUST NOT be copied in any form.

---

## O.3 Inherited infrastructure

### O.3.1 Document class and packages

The preamble MUST keep the old class and package set [FP §2.1-§2.2; old.tex:14-41], with three
additions (`xcolor`, `apstatic`, best-effort reproducibility primitives) and one removal
(`tables/search_macros`):

```latex
%% AgentPROV manuscript: Elsevier CAS double-column template (cas-dc).
%% Every number comes from paper/macros.tex (\apstat) or paper/tables/*.tex, all GENERATED
%% by `uv run agentprov-paper build`. Do not type numbers by hand.
\documentclass[a4paper,fleqn]{cas-dc}
\usepackage[numbers]{natbib}
\usepackage{booktabs}
\usepackage{array}
\usepackage{cuted}
\usepackage{graphicx}
\usepackage{amsmath,amssymb}
\usepackage{url}
\usepackage{stfloats}   % figure* at page bottom; replaces dblfloatfix (old.tex:22-25)
\usepackage{float}
\usepackage{caption}
\usepackage{microtype}
\usepackage{xcolor}     % \TODO in draft builds
\usepackage{tikz}
\usetikzlibrary{arrows.meta, positioning, fit, backgrounds, calc}
\input{apstatic}        % hand-written, reviewed: \apdef, \apstat, \TODO, notation
\input{macros}          % GENERATED: \apdef lines, legacy aliases, \apdraft switch
\graphicspath{{figures/}}
\setlength{\emergencystretch}{3em}
\ifdefined\pdftrailerid  % pdfTeX: best-effort PDF reproducibility; not a v0.1 gate (O.3.8)
  \pdftrailerid{}\pdfinfoomitdate=1 \pdfsuppressptexinfo=-1
\fi
```

- The float-placement block after `\begin{document}` (old.tex:47-58) is kept unchanged.
- `hyperref` stays class-loaded; `siunitx` is not used, so numbers stay preformatted strings
  [FP §2.2].
- The body MUST NOT define commands. All custom commands live in `paper/apstatic.tex` (hand-written)
  or `paper/macros.tex` (generated), as in the old paper [FP §2.4].
- The bibliography keeps `\balance`, `\bibliographystyle{cas-model2-names}`, `\bibliography{refs}`, and
  appendices after the references in `\onecolumn` (old.tex:3819-3833).
- The target journal is unknown; `cas-dc` implies an Elsevier CAS journal [FP §2.1, §7.9] (OM-23).

### O.3.2 Build

- `paper/.latexmkrc` (committed; the old repo had none [FP §2.5]):

  ```perl
  $pdf_mode   = 1;
  $bibtex_use = 2;
  @default_files = ('agentprov_paper.tex');
  $pdflatex = 'pdflatex -interaction=nonstopmode -halt-on-error -file-line-error %O %S';
  $ENV{'FORCE_SOURCE_DATE'} = '1';
  # SOURCE_DATE_EPOCH is exported by `make paper` (last commit time); see O.3.8.
  ```

- `make paper` runs, from the repository root:
  `cd paper && SOURCE_DATE_EPOCH=$(git log -1 --format=%ct) latexmk` and then
  `uv run agentprov-paper check-log paper/agentprov_paper.log`. The Makefile MUST quote paths: the
  repository directory name contains spaces.
- `check-log` fails (exit 5) on: `LaTeX Warning: Reference .* undefined`, `Citation .* undefined`,
  `There were undefined references`, `Package agentprov Error`, `Label(s) may have changed` after the
  final pass, and any `??` in the PDF text layer when `pdftotext` is available. Overfull boxes over 5 pt
  are warnings in draft mode and errors in release mode.
- Texpad remains usable; `paper/.texpadtmp/` stays ignored [FP §2.5]. Only `make paper` builds are
  authoritative, because Texpad does not set the determinism environment.

### O.3.3 Bibliography

1. **Copy.** The initial commit copies `paper/refs.bib` verbatim from the old repository at `24ac03f`
   (60 entries, all cited [PA §0]; sha256 `d0f0a5a815de215e451e7a8009fa208abb35413f90188d934d3e1cfb3869dcac`
   of the git blob, computed 2026-10-07). The digest is recorded in `legacy/adprov-v2.3/FROZEN.json`.
2. **Fixes in the first follow-up commit.**
   - `adprov2026corpus`: the entry says `version = {2.3}` with the v2.2 DOI `10.5281/zenodo.21052314`
     [PA §11; RF §0.3]. It MUST cite the deposited version it names, and SHOULD add the concept DOI
     `10.5281/zenodo.20692312` [RF REP-4].
   - Add `@software{adprov2026framework}` for AgentDojo-PROV at commit `579a908…`, not tag
     `corpus-v2.3` (OM-2).
   - `agentdojo2024code`: add the pinned upstream commits used by the AgentDojo import, `c274885…` (June 2024)
     and `089ed468` (HEAD) [DEC D3; A6; RESOLUTIONS §3.5 "Pins"] (OM-6).
   - `deepseekv32`: MUST NOT be cited for the June-2026 `deepseek-chat` runs (OM-7).
   - The comment "The reference list (55 entries)" (old.tex:3818) is stale [PA §2]; do not copy it.
3. **New entries.** Metadata below comes only from the investigation reports. Each new entry MUST be
   verified against the arXiv API, Crossref, DataCite or the repository before it is cited, and MUST carry
   a comment `% verified: <YYYY-MM-DD> <method>`, following the old file's practice (refs.bib comments
   such as "Checked 2026-09-30 against the arXiv API"). Entries whose authors are not in the reports are
   marked "fetch".

   | Proposed key | Work | Identifier | Report | Role in the paper |
   |---|---|---|---|---|
   | `li2025drift` | DRIFT: Dynamic Rule-Based Defense with Injection Isolation for Securing LLM Agents. Hao Li, Xiaogeng Liu, Hung-Chun Chiu, Dianqi Li, Ning Zhang, Chaowei Xiao. Accepted to NeurIPS 2025 | arXiv 2506.12104; DOI 10.48550/arXiv.2506.12104 | sources/drift.md §1 | source (partial) |
   | `li2025stac` | STAC: When Innocent Tools Form Dangerous Chains for LLM Agents (v3 title; v1 "…to Jailbreak LLM Agents"). Jing-Jing Li, Jianfeng He, Chao Shang, Devang Kulshreshtha, Xun Xian, Yi Zhang, Hang Su, Sandesh Swamy, Yanjun Qi | arXiv 2509.25624 | sources/multiturn-agent-attack.md §1 | attack-scenario population (`unit: scenario`; import `planned`; R-28) |
   | `schaeffer2026ciaware` | CIAware-Bench: Benchmarking Control Intervention Awareness Across Frontier LLMs. Joachim Schaeffer, Alexander Panfilov, Thomas Jiralerspong, Guillaume Lajoie, Jonas Geiping, Yoshua Bengio, Roland S. Zimmermann | arXiv 2606.11063 | sources/ciaware-bench.md §1.1 | planned source (AD-21: `hf-gated` evidence partial, import planned; `ciabench` per U-04) |
   | `choi2026adi` | Agent Data Injection Attacks are Realistic Threats to AI Agents. Choi, Kim, Kang, Jeong, Xing, Lee (README key `choi2026adi`) | arXiv 2607.05120 | sources/adi.md §1 | `not_possible` row of `tab:compat` |
   | `jiang2026agentlab` | AgentLAB: Benchmarking LLM Agents against Long-Horizon Attacks. Jiang, Wang, Liang, Wang | arXiv 2602.16901 | sources/rope.md §5.3, §9 | attack provenance of ROPE's long-horizon logs |
   | `agentharm2024` (fetch authors) | AgentHarm | arXiv 2410.09024 | sources/agent-security-tools-survey.md §1 | structurally different source, corpus `ast-survey-agentharm` (AD-06; O.1.7) |
   | `lin2026securityartifact` | Reproduction Artifact for "Evaluating Agentic LLM Security Benchmarks for Cybersecurity Education: A Reproducible Study". Jhih-Jhong Lin. Zenodo v1.0.1, 2026-08-28, CC BY 4.0 | DOI 10.5281/zenodo.22140262 (concept 10.5281/zenodo.22135956); primary origin git `Forever-CodingNoob/agent-security-tools-survey@89c4db2c…` (R-62) | survey report §1 | source; cite the concept DOI with the version fetched (R-62) |
   | `nist2025agentdojoinspect` | AgentDojo-Inspect. Tony Wang, Michael Gerovitch, Benjamin Edelman. NIST PDR v1.0.0 | DOI 10.18434/mds2-3690 | sources/agentdojo-inspect.md §1 | deduplication example (byte-identical mirror) |
   | `mandate2026eval` | mandate-agentdojo-eval (Mandate Labs, MIT); software citation with commit | `github.com/jwilliamsc/mandate-agentdojo-eval` | sources/mandate-agentdojo-eval.md §1 | source |
   | `agentdyn2026code`, `drift2025code`, `autodojo2026code`, `stac2025code` | repositories at the inspected commits: `SaFo-Lab/AgentDyn@5353cf7`, `SaFo-Lab/DRIFT@6fd3df4`, `xhOwenMa/AutoDojo@aa458794`, `amazon-science/MultiTurnAgentAttack@ddeede7a` | git commits | finding JSONs; sources/drift.md, autodojo.md | raw-evidence origin |
   | `vispute2026aer` (fetch title) | Agent Execution Record. Vispute, Kadam | arXiv 2603.21692 | landscape/prov_semantics.md §6 | cited and distinguished at first use of "AER" (AD-22; O.1.8) |
   | `authgraph2026` (fetch) | Aligning Provenance with Authorization (AuthGraph). P. Wang, Y. Li, Y. Tian | arXiv 2605.26497 | prov_semantics §6 | related work |
   | `she2026provenanceguard` (fetch) | ProvenanceGuard. She, Liang, Kang | arXiv 2607.01236; DOI 10.1145/3832783.3837535 | prov_semantics §6 | related work |
   | `costa2025fides` (fetch) | FIDES. Costa et al. | arXiv 2505.23643 | prov_semantics §6 | related work |
   | `contextcite2024`, `tracllm2025`, `attntrace2026` (fetch) | ContextCite; TracLLM (USENIX Security 2025); AttnTrace (IEEE S&P 2026) | arXiv 2409.00729; 2506.04202; 2508.03793 | prov_semantics §6 | inferred-evidence methods |
   | `padovani2025yprov4ml` (fetch) | yProv4ML. Padovani, Anantharaj, Fiore | arXiv 2507.01078 | prov_semantics §6 | related work |
   | `otelgenai2026`, `inspectai2026` | OpenTelemetry GenAI semantic conventions (repo `semantic-conventions-genai` @ `4f85037e`, status Development); Inspect AI (`UKGovernmentBEIS/inspect_ai`) | repositories | landscape/trace_formats.md §0, §3.1-§3.2 | formats |

   Already present and kept (identifiers per the old `refs.bib`): `debenedetti2024agentdojo` (arXiv
   2406.13352 per sources/agentdojo.md §1), `li2026agentdyn` (2602.03117), `ma2026autodojo` (2606.15057),
   `ma2026rope` (2608.27496), `ma2026ropeRuns`, `zhang2025asb` (2410.02644), `provagent2025` (2508.02866),
   `wang2025agentarmor` (2508.01249), `debenedetti2025camel` (2503.18813), `wang2026traces` (2606.04990),
   `zhao2026livepi` (2605.17986). Optional, only if used: Kim et al. SoK (arXiv 2603.11088) and
   BetterBench (arXiv 2411.12990) [survey report §1]; "The Attacker Moves Second" (arXiv 2510.09023)
   [sources/mandate-agentdojo-eval.md §1].
4. **Gate.** `agentprov-paper check-bib` fails if a cited key is missing, an entry added after the
   initial commit lacks a `% verified:` comment, or a DOI or eprint appears twice.

### O.3.4 Macro conventions: keyed accessor and legacy alias layer

**Value keys.** Every value has a key `<scope>/<name>`.
- `scope` matches `^[a-z][a-z0-9-]*$`. Reserved scopes: `spec` (version identifiers), `all` (cross-source
  counts, extrema and the registry-generated `coverage_phrase`), `legacy-adprov-v23` (frozen AgentDojo-PROV
  values), `legacy-compat` (compat regression, from the gate-B report), `semdiff-release` and
  `semdiff-converted` (the gate-E report of each v2.3 tree, J.3.6), `search` (prior-artefact search),
  `lineage`. All other scopes are corpus ids from `paper.toml` (HL H.4.2), for example `agentdojo-upstream`,
  `agentdojo-prov-v2`, `rope`, `ast-survey-agentharm`. The converted v2.3 tree is not a corpus (it is a
  compatibility oracle read by gate R), so its values live only in `legacy-*` and `semdiff-converted`.
- `name` matches `^[a-z][a-z0-9_]*$`.
- Keys may contain digits and hyphens because they are looked up with `\csname`. This removes the
  letters-only restriction and the prefix collisions of `\Adp<Prefix>` [FP §2.4, §3.8, §7.3].

**`paper/apstatic.tex`** (hand-written; normative content):

```latex
\makeatletter
\newif\ifapdraft \apdrafttrue
\newcommand*{\apdef}[3]{%
  \expandafter\ifx\csname ap@#1@#2\endcsname\relax
    \expandafter\def\csname ap@#1@#2\endcsname{#3}%
  \else
    \PackageError{agentprov}{duplicate value #1/#2}{Regenerate macros.tex.}%
  \fi}
\DeclareRobustCommand*{\apstat}[2]{%
  \expandafter\ifx\csname ap@#1@#2\endcsname\relax
    \PackageError{agentprov}{undefined value #1/#2}{Run: uv run agentprov-paper build}%
    \textbf{??}%
  \else
    \csname ap@#1@#2\endcsname
  \fi}
\newcommand{\TODO}[1]{\ifapdraft{\color{red}[TODO: #1]}\else
  \PackageError{agentprov}{TODO left in release mode}{}\fi}
\makeatother
```

`\apstat` is robust so it survives captions and the `.aux` file. It MUST NOT appear in sectioning
titles (lint rule). Percent values carry no `%`; the tex writes `\apstat{rope}{fg_coverage_pct}\%`,
as in the old convention [FP §2.4].

**`paper/macros.tex`** (generated) contains, in this order: a header
`% GENERATED by agentprov-paper <version> from values.json — do not edit`; `\apdraftfalse` in release
mode; one `\apdef{<scope>}{<name>}{<text>}` per value, sorted by key; the legacy alias block.
Carry-forward of old values (the old `_previous_macros`, whose regex truncated six brace-containing
values, FP-#11) MUST NOT be implemented: a missing input fails the build instead.

**Formatting** (`agentprov_paper.render.fmt`), ported from make_figures' formatters [FP §2.4, §3.10]:
- `fmt_int(n: int) -> str` gives `17,664`. A comma thousands separator is used everywhere, including the
  search values (the old search script used `2\,601`).
- `fmt_pct(x: float, dp: int = 1) -> str` gives one decimal and no `%`.
- `fmt_p_upper(p: float) -> str` rounds up at the displayed precision, because p-values are quoted as
  `≤` bounds.
- `fmt_upper(x: float, dp: int) -> str` rounds up "within X" bounds.
- `tex_escape(s: str) -> str` is applied to every text value except the output of whitelisted
  LaTeX-producing formatters (`fmt_tool`, `fmt_attack`).

**Legacy alias layer.** `legacy/aliases.toml` is the only place an `\Adp…` name can be defined. It is a
whitelist; it does **not** reproduce the 1,015 legacy names [FP §3.8]. Each entry has one policy:

| Policy | Emitted LaTeX | Rule |
|---|---|---|
| `frozen` | `\newcommand{\AdpNumTraces}{\apstat{legacy-adprov-v23}{n_traces_generated}}` | value parsed from the frozen copy `legacy/adprov-v2.3/macros.tex` (sha256 `1c5c70ea302696a4bf423700234cd764fe1d9d66384e4763aa22471b543e14b2` at `24ac03f`), value basis `legacy-frozen` (`ValueBasis`, O.3.5), `cite` required. For prior-work statements only |
| `recompute` | same form, key in a corpus scope | value produced by the new pipeline; the build compares it with the frozen value and fails on a difference unless `legacy/divergences.toml` explains it (reason, rule or version change, date) |
| `retired` | `\newcommand{\AdpStealthMaxModel}{\PackageError{agentprov}{retired: <reason>}{}}` | the name exists only to fail with its reason, e.g. a model display name "DeepSeek-V3.2" whose served model is unknown [RF CAP-6] |

The frozen file MUST be parsed with a brace-balanced parser (`agentprov_paper.legacy.parse_frozen_macros`),
not the old regex. The parsed set MUST contain exactly 1,015 names [FP §3.8].

**Usage checks** (`agentprov-paper check-keys`):
1. every `\apstat{s}{n}` in the tex is defined;
2. every `\Adp…` used is in `aliases.toml`;
3. every value used in a hand-written float is reported;
4. defined but unused values are listed as a warning. The old file had 1,015 defined and 602 used
   [FP §3.8]; unused values are allowed only when a claim reads them.

### O.3.5 Generation pipeline over multi-source corpora

```
paper.toml (corpus pins + gate-report pins) ─► data: verify corpus.json digest + checksums.sha256
     ─► frames (cached, keyed by manifest digest; built from agentprov.api, incl. the agentprov.stats tables)
     ─► stats: pure functions → ValueSet
     ─► render: values.json, macros.tex, tables/*.tex (deterministic), figures/*.pdf
     ─► check: claims, keys, prose lint (shared claims library), bib, untrusted-content lint
     ─► latexmk ─► check-log ─► [release] determinism double build of the text outputs ─► BUILD_PROVENANCE.json
```

The paper package MUST NOT import any benchmark package. The old `make_figures.py` imported `agentdojo`
for `get_suites`/`get_suite` [FP §3.2]; the equivalent facts now come from the semantics profile
`agentdojo.suites` at the version the corpus records, loaded from the framework's package resources through
`agentprov.api`; the byte copy in the corpus `rules/` directory is a record that is only digest-compared
(AD-14; [DEC D4, D9]). The paper MUST NOT walk raw artefacts itself: it reads sealed corpora through the
framework's public API `agentprov.api` only (MN M.6). The framework has no `analysis` extra in v0.1 (AD-10 row 1;
R-64): the paper builds its own pandas frames from the stdlib structures the API returns, and owns them.

**Shared statistics (AD-10 as ruled).** The four generic tables of `agentprov stats`, computed by the framework's
`src/agentprov/stats/` (stdlib only), are the single implementation of: counts per source and status (incl.
`unit`, `execution_observed` and `completeness`); PROV statements by evidence class, bundle and rule; unknown-reason
proportions; and the per-source information-loss table by field group. The paper consumes them through
`agentprov.api`, never re-implements them, and checks with claim `c3-stats-agree` that every value it derives
from them equals the value the CLI reports for the same corpus digest. The paper requires the statement counts at
per-execution grain (for F8 and `tab:graphdist`); the CLI tables aggregate that grain.

**Pinned reports.** Besides corpora, `paper.toml` pins by sha256 the migration gate reports the paper quotes: the
gate-B report (`legacy-compat`) and the two gate-E reports `migration/semdiff/semdiff-<tree>.json` (`semdiff-release`,
`semdiff-converted`) [J.3.6]. A report whose digest differs from its pin fails the build like a corpus
(`PinMismatch`, exit 3).

**Modules and signatures** (package `agentprov_paper`, source under `src/`):

```python
# config.py
@dataclass(frozen=True)
class CorpusPin:
    id: str                    # value scope, ^[a-z][a-z0-9-]*$
    root: Path                 # relative to $AGENTPROV_CORPORA
    manifest_sha256: str       # sha256 of corpus.json; the paper is bound to it
    display: str               # key into profiles/display.toml

@dataclass(frozen=True)
class ReportPin:
    id: str                    # value scope: "legacy-compat", "semdiff-release", "semdiff-converted"
    path: Path                 # e.g. migration/semdiff/semdiff-release.json (relative to $AGENTPROV_REPORTS)
    sha256: str                # sha256 of the report file; the paper is bound to it

@dataclass(frozen=True)
class PaperConfig:
    mode: Literal["draft", "release"]
    corpora: tuple[CorpusPin, ...]
    reports: tuple[ReportPin, ...]   # migration gate reports (J.3); empty until gates have run
    legacy: LegacyPin          # manuscript commit, framework commit, macros sha256
    abstract_max_words: int
    framework_commit: str | None

def load_config(path: Path = Path("paper.toml")) -> PaperConfig: ...

# data.py
class PinMismatch(RuntimeError): ...
@dataclass(frozen=True)
class CorpusHandle:
    pin: CorpusPin
    root: Path
    manifest: Mapping[str, Any]
    manifest_sha256: str

def open_corpus(pin: CorpusPin, corpora_root: Path) -> CorpusHandle:
    """Refuse (PinMismatch, exit 3) unless sha256(corpus.json) == pin.manifest_sha256 and every line
    of checksums.sha256 verifies. Release mode verifies all entries; draft mode MAY sample with a
    printed warning and records the sample in BUILD_PROVENANCE.json."""

# frames.py
FRAME_SCHEMA_VERSION: Final[int] = 1
FrameName = Literal["executions", "statements", "field_status", "validation",
                    "semdiff", "lineage", "profiles"]
def get_frame(h: CorpusHandle, name: FrameName, *, offline: bool = False) -> pd.DataFrame: ...

# values.py
# ValueBasis = the basis of a statistic; NOT the evidence class of a PROV statement (R-64; was "EvidenceLevel")
ValueBasis = Literal["derived", "inferred", "external", "legacy-frozen", "spec"]
@dataclass(frozen=True)
class Value:
    scope: str; name: str
    raw: int | float | str | bool | None
    text: str                  # formatted LaTeX-ready string
    fmt: str                   # formatter id
    unit: str | None
    basis: ValueBasis          # "external" = published constants, manual audit numbers (cite required)
    function: str              # "<module>.<qualname>@<sha256 of module source>"
    inputs: tuple[str, ...]    # "sha256:<…>" of frames / manifests / reports read
    tags: tuple[str, ...] = () # claim tags of the I.5.6 vocabulary; checked with claims.check_claim (I.5.6 rule 4)
    cite: str | None = None
class ValueSet:
    def add(self, v: Value) -> None: ...      # rejects bad keys and duplicates
    def __getitem__(self, key: str) -> Value: ...
    def to_json(self) -> bytes: ...           # RFC 8785 (JCS), sorted by key

# stats/*.py — pure: (handles, frames) -> list[Value]; the generic numbers come from agentprov.stats via the API
def structure_values(h, ex, st) -> list[Value]: ...      # stats/structure.py
def evidence_values(h, st) -> list[Value]: ...           # stats/evidence.py   (RQ2c, composition)
def loss_values(h, fs) -> list[Value]: ...               # stats/loss.py       (RQ2a headline, RQ2b)
def semdiff_values(rep, sd) -> list[Value]: ...          # stats/semdiff.py    (RQ3; gate-E report only)
def validation_values(h, va) -> list[Value]: ...         # stats/validation.py (RQ1)
def lineage_values(handles, li) -> list[Value]: ...      # stats/lineage.py    (C5; no collection manifest)
def spec_values(framework_meta) -> list[Value]: ...      # stats/spec.py       (incl. all/coverage_phrase)
# stats/inference.py: wilson(k, n, z=1.959963984540054) -> tuple[float, float];
#                     bounds(k, n, n_unknown) -> tuple[float, float]   (ported from FP §3.10)

# render/: fmt.py, style.py, macros.py, tables.py, figures.py   (pdfnorm.py deferred, AD-10 row 20)
# claims.py, lint.py, legacy.py, cli.py (O.3.7, O.3.4)
```

**Frames.** Required columns. Column names follow the corpus index (HL H.3.1) and MN M.6: `ex` for the
execution id, `defense_id` as the facet identifier, validation results `pass|fail|skipped|not_applicable`
(R-64). The paper owns its frames (MN M.6: "Frame columns are owned by O.3.5"); the producers are framework data
read through `agentprov.api`.

| Frame | Grain | Columns | Producer |
|---|---|---|---|
| `executions` | one row per index row | `source_id, corpus_id, ex, unit (agent_execution/outcome_only/scenario), execution_observed (bool), completeness (verified_complete/known_incomplete/unverifiable), source_key, benchmark, environment, user_task_id, injection_task_id, attack_id, attack_family, model_requested, pipeline_id, defense_id, repeat_index, status (ok/ok_with_issues/failed), issues (list[str]; register codes), aer_sha256, sem_sha256, prov_sha256, n_records_<kind> (13 kinds, incl. activity and artefact), raw_included (bool)` | `executions.jsonl` (HL H.3.1: `ex`, `unit`, `execution_observed`, `completeness`, `status`, `issues`, `digests`, facets per the profile's facet schema) + AER header [DEC D9]; counts per source and status agree with the `agentprov stats` counts table. `n_executions := unit == agent_execution ∧ execution_observed` (R-28); outcome-only records and scenarios are counted separately |
| `statements` | execution × bundle × statement type × evidence class × rule | `ex, bundle (core/inference/assessment/toplevel), stype, evidence (O/D/I), rule, n` | the `agentprov stats` statements table at per-execution grain (AD-10 as ruled), over the `agentprov-prov/0.1` bundles |
| `field_status` | execution × field group | `ex, group, status (O, D, I, unk:<reason>)`, reasons `not_recorded, lost, overwritten, withheld, ambiguous, not_captured, not_applicable` | the `agentprov stats` field-group and unknown-reason tables (from the AER envelope `ev`, `evf`, `unk` [DEC D2]) |
| `validation` | execution × check | `ex, tier (1-7), check, result (pass/fail/skipped/not_applicable), message_code` | the sealed corpus `validation/results.jsonl` and `validation/summary.json` (AD-20); the paper never re-runs the validator (R-64) [DEC D8] |
| `semdiff` | tree × v2.3 element × disposition | `tree (release/converted), v23_element, count, disposition (kept/reclassified/moved/replaced/moved-to-assessment/dropped/new), bundle, evidence_class, rules` | the pinned gate-E reports `migration/semdiff/semdiff-<tree>.json`, generated from `src/agentprov/prov/compat/semdiff-map.toml` [J.3.6; R-33; DEC D7] |
| `lineage` | edge | `from_node, to_node, relation, n, basis` | `corpus.json`, `raw/origins.jsonl`, `source_key` duplicates and the owner declarations in each profile's `[lineage]` [DEC D4, D9]; collection manifests are deferred (AD-10 row 6) |
| `profiles` | source × part | registry fields (source id, part, repo, pinned commits, licence policy `include/reference/nc_partition/forbidden`, raw policy, dialects, live/import, evidence availability, implementation status and caveat, gated) | `agentprov.adapters.registry` through `agentprov.api.source_registry()`; status lives only in the registry (R-38, R-45) [DEC D4] |

**Field groups** for `field_status` are the fixed capability list of the framework's information-loss table,
`src/agentprov/stats/field_groups.toml` (MN; AD-10 as ruled), each group mapped there to AER JSON Pointers of C.3.
This list is the paper's normative requirement on that file; the paper imports the file's groups through
`agentprov.api` and never redefines them, and a difference between the file and this list fails the build
(claim `c3-groups-agree`). The groups encode the reviewers' requirements [RF AR-2..AR-5] and the capability
matrix proposed in [PA §13 Add]:

`ctx` (as-sent model input context), `tooldefs` (tool definitions offered), `model_req` (requested model
id), `model_served` (provider-returned model id), `sampling` (effective sampling parameters), `usage`,
`finish` (finish reason), `reasoning`, `sysprompt`, `t_model` (model-call times), `t_tool` (tool-execution
times), `passes` (all passes held), `env` (environment state digests), `callid` (provider tool-call id),
`link` (how result ↔ call linking was established), `payload` (registered injection payload map),
`outcome_logged`, `checker` (checker identity and version).

`outcome_replayed` is not in the v0.1 list, because outcome replay is deferred (AD-10 row 2); it returns with
replay. **Field-group coverage** of a group in a source (`<src>/fg_<group>_coverage_pct`) is the share of the
source's executions (`unit == agent_execution ∧ execution_observed`) whose status for that group is O or D; the
source-level aggregate `<src>/fg_coverage_pct` is the same share over all (execution, group) cells of the list.
`not_applicable` cells are excluded from both denominators, and `not_applicable` is allowed only for a group that
cannot exist for the source (R-57; e.g. `payload` for AgentHarm). The AgentDyn seed is `not_recorded`, not
`not_applicable` (HL L.2.3).

**Poolability.** Rates MUST NOT be pooled across corpora unless both display profiles declare the same
`pool_group` [FP §7.1 item 3]. Counts with a source-independent definition (executions, statements) MAY be
summed under scope `all`. Min/max over sources MAY be emitted under `all` with the arg-min/arg-max source
as a companion text value. McNemar, cluster permutation and cluster bootstrap [FP §3.10] are NOT ported in
v0.1, because no RQ uses them. Wilson intervals and worst-case bounds are ported with tests.

**Untrusted content.** Corpora contain prompt-injection payloads by design. Paper tooling MUST treat all
corpus text as data. No renderer may place free text from raw artefacts, AER message parts or fixtures
into a figure, table or value. Only identifiers, tool names, record kinds and rule ids are allowed (O.4.5).
Paper tooling MUST NOT send corpus content to any LLM-based tool [PA §10 "missing threats"; RF §6].

### O.3.6 Caches keyed by manifest digests

- Location: `.cache/agentprov-paper/<corpus_id>/<frame>.parquet` (gitignored).
- Key: `sha256(JCS({"corpus_manifest_sha256": …, "agentprov": {"version": …, "commit": …},
  "frame": <name>, "frame_schema": FRAME_SCHEMA_VERSION, "code": sha256(source of the producing
  module)}))`.
- The key is stored in the parquet key-value metadata under `agentprov_paper.cache_key`, not as a column
  (the old `_cache_version` column [FP §3.5]).
- On a mismatch the frame is recomputed. With `--offline` the build refuses (exit 3). The cache is never
  silently reused [FP §3.5: "nothing in any cache records which corpus content it was computed from"].
- Validation results are read from the sealed corpus `validation/` (required in the layout, AD-20), which the
  manifest digest covers; the paper never re-runs the validator (R-64). A cache can therefore no longer predate
  recomputed graphs, unlike the old conformance caches (569 graph files newer than the cache) [FP §3.5].
- Frames built from a pinned migration gate report are keyed by that report's sha256 instead of a manifest
  digest.
- `--conformance-limit`-style sampling MUST NOT write into the cache (FP-#15).
- No cache file is committed. The committed outputs (values, macros, tables, figures, PDF) make the paper
  buildable without corpora. Regeneration needs only the pinned corpora and reports, which are recomputable from
  their deposits once published [DEC D9]; nothing is deposited without the user's instruction (Addendum B B-2;
  U-01, U-02). This fixes "a fresh clone cannot regenerate" [FP §4].

### O.3.7 Claims and prose checks that fail the build

**Registry.** The 46 old prose checks [FP §3.9] become a registry in `src/agentprov_paper/claims.py`:

```python
@dataclass(frozen=True)
class Claim:
    id: str                        # ^[a-z0-9][a-z0-9-]*$
    anchor: str                    # \label key of the enclosing section or float
    keys: tuple[str, ...]          # value keys read
    predicate: Callable[[Mapping[str, Value]], bool]   # operates on Value.raw, never on text
    text: str                      # one-line statement of what the sentence asserts
REGISTRY: Final[tuple[Claim, ...]]
def check_claims(values: ValueSet, tex_files: Sequence[Path]) -> list[ClaimFailure]: ...
```

Rules:
1. A sentence that interprets a number ("none", "every", "more than", "all", "ranges from") MUST be
   preceded on the same or the previous line by `% claim:<id>`.
2. `check` requires a bijection: every claim id in the tex is registered, every registered claim appears
   in the tex, and each claim's `anchor` matches the enclosing `\label`.
3. A missing key is a failure.
4. Any failure exits **2**. The old checker printed a failure and exited 0 (FP-#12). `--allow-failing-claims`
   is accepted only in draft mode and is recorded in `BUILD_PROVENANCE.json`.
5. Investigation cross-checks are claims too. Example: `c5-inspect-mirror` asserts that the
   AgentDojo-Inspect `runs/` contribute 0 new executions, because 21,999 of 21,999 files are byte-identical
   to AgentDojo `runs/` [sources/agentdojo-inspect.md §6]. Their expected values are `external` values
   citing the report.
6. Every generated value carries the claim tags it asserts (`Value.tags`, I.5.6 vocabulary); `check` calls
   `claims.check_claim` on them for the value's sources, so a value that a must-not-claim item forbids for its
   source fails the build (I.5.6 rule 4; DoD Q.11b).

**Prose lint** (`agentprov-paper lint`, exit 4). It first runs the framework's one claims/lint library,
`agentprov.adapters.registry.claims` (I.5.6), through `agentprov.api`: `lint_text` over every `.tex` file (the
I.4 must-not-claim items as claim-tag rules), and `coverage_phrase()` as the only source of empirical coverage
wording (NC-ALL-08) [R-27, R-45, R-58]. The same library also lints the framework's `README.md`, `docs/` and the
datasheet templates, so the paper, README and datasheets share one rule set. Until the framework is pinned in
`paper.toml` (the skeleton of O.5), these checks are reported as *skipped*, which fails release mode [DEC D8].
The paper then adds its own rules:
- **Scoped terms.** A sentence containing `lossless`, `first`, `ground truth`, `faithful`, `conformant`,
  `PROV-CONSTRAINTS valid`, `complete record`, `at scale`, bare `reproducible` or `independently verifiable`
  MUST carry `% scope:<claim-id>` that names a registered claim encoding the scope; the required wordings are
  those of O.1.2 ("derivation-reproducible", "integrity-verifiable", "traceable statement by statement").
  Source: [RF AR-12; PA §16; R-58].
- **Agnosticism terms** (AD-08 as ruled). The bare terms `benchmark-agnostic` and `framework-agnostic` are
  allowed only inside a design-goal block of a design section (`sec:principles`, `sec:adapters-model`), delimited
  by the LaTeX comment form of the I.5.6 marker (`% agentprov:design-goal` … `% agentprov:end-design-goal`);
  such a block MUST NOT contain `\apstat`, digits or source names. Everywhere else, including the title, the
  abstract, `sec:intro`, `sec:evaluation`, `sec:answers` and `sec:conclusion`, they are errors.
- **Title.** "Live Capture" in `\title` is an error unless `paper.toml` pins an approved, sealed live corpus
  without `test_only` instrumentation (U-18; NC-LIVE-02).
- **Retired terms** (reason printed): `DeepSeek-V3.2` [RF CAP-6], `corpus-v2.3` used as a tag reference
  (OM-2), `transcript/v2` [DEC D1], `ProvObserver` outside the history paragraph [DEC D5].
- **Hand-typed numbers.** Digit runs of length ≥ 2 in hand-written prose and floats, outside `\apstat`,
  `\ref`, `\cite`, labels, years in citations, version strings and an allowlist in `lint-allow.toml`
  (each entry justified), are errors in release mode and warnings in draft mode. This makes "no number
  is hand-typed" checkable [FP §7.1 item 1].
- **Structure.** `\label` after `\paragraph`; `\apstat` in a sectioning title; abstract longer than
  `abstract_max_words`; any `\TODO` in release mode.

### O.3.8 Deterministic outputs

Two builds from the same commit, corpora, reports and `uv.lock` MUST produce byte-identical `values.json`,
`macros.tex` and `tables/*.tex`. `make determinism` builds these twice in fresh temporary directories and compares
sha256; release mode requires it to pass (exit 6). Byte determinism of `figures/*` and of `agentprov_paper.pdf`
is **deferred** (AD-10 row 20; R-45): the measures below are kept as best effort (SHOULD) and are not gated in
v0.1. A change in a figure or PDF digest between two builds is reported, not failed.

- **Text outputs** (MUST): `values.json` in JCS; tables and macros sorted by profile order and key; no
  wall-clock timestamps anywhere. Line endings are LF, enforced by `.gitattributes`. The old repo had
  `core.autocrlf = true` and no `.gitattributes` [FP §2.5].
- **Matplotlib** (SHOULD; style from [FP §3.6], `pdf.fonttype = ps.fonttype = 42`): save with
  `metadata={"CreationDate": None}` [FP §7.2 Stage C]. The old figures differed run to run only in
  `/CreationDate` (FP-#13).
- **Graphviz** (SHOULD; lineage and example figures): run `dot` with a fixed node and edge order and record the
  `dot` version in `BUILD_PROVENANCE.json`. Stripping `/CreationDate`, `/ModDate` and `/ID` from PDF outputs
  (the former `render.pdfnorm`) is deferred with PDF byte determinism.
- **pdfTeX** (SHOULD): `SOURCE_DATE_EPOCH` set to the last commit time, `FORCE_SOURCE_DATE=1`, and the preamble
  primitives in O.3.1.

### O.3.9 Build provenance

`paper/BUILD_PROVENANCE.json` (generated, committed) is the plain record of what a build read and which
relaxations it used; it is needed to record draft-mode sampling and `--allow-failing-claims` (O.3.5, O.3.7). Its
PROV form, `paper/BUILD_PROVENANCE.prov.json` (the paper build as a PROV document produced with the framework's
serialiser [FP §7.4]), is **deferred** (AD-10 row 20). The JSON record MUST contain:
- `schema: "agentprov-paper/build/1"`;
- `paper_commit` (or `"dirty"`, which is forbidden in release mode) and `mode`;
- `framework`: `{distribution, version, commit}`. Release mode requires `agentprov` pinned by git
  commit or released version, not an editable path;
- `corpora[]`: `{id, manifest_sha256, checksums_verified: "all"|"sampled"}`;
- `reports[]`: `{id, path, sha256}` of the pinned migration gate reports (O.3.5);
- `legacy`: `{manuscript_commit, framework_commit, macros_sha256}`;
- `inputs` (refs.bib, search results, `aliases.toml`, `divergences.toml` digests);
- `toolchain` (python with its full patch version, `uv.lock` sha256, matplotlib, graphviz `dot`, pdfTeX,
  latexmk, `cas-dc` version from the log);
- `outputs` (sha256 of `values.json`, `macros.tex` and every generated table, which the determinism gate
  checks; figure and PDF digests are recorded for information only);
- `flags` (`--allow-failing-claims`, sampling, skipped shared-library checks).

---

## O.4 Figures and tables

### O.4.1 Disposition of the old figures (15)

Figure inventory from [FP §3.6].

| Old fig. | Label | File | Disposition | Reason |
|---|---|---|---|---|
| 1 | `fig:overview` | `fig_graphical_abstract.pdf/.png` | Replace by `fig:pipeline`; a graphical abstract MAY be derived from it | hard-coded AgentDojo/`transcript/v1` text [FP §3.6] |
| 2 | `fig:provkey` | `fig_prov_starting_points.pdf` (static, no generator) | Regenerate for `apv` | no generator in either repo (FP-#17) |
| 3 | `fig:capture` | TikZ (old.tex:920-984) | Rewrite as AgentDojo live backend (`capture/0.1`), only if an approved live corpus is reported (U-18) | `ProvObserver` removed, deviations declared [DEC D5]; default LLM element `native` (AD-09); went stale before [RF REP-6] |
| 4 | `fig:composition` | `fig_corpus_composition.pdf` | Move to `app:sources` as per-source small multiples | per-corpus facts |
| 5 | `fig:coverage` | `fig_coverage.pdf` | Drop; replaced by `tab:compat` and `fig:infoloss` | two-corpus layout |
| 6 | `fig:sizes` | `fig_graph_sizes.pdf` | Survive, generalised: statements per execution per source (CCDF, log-log), merged with old Fig. 12 | structural and source-independent [FP §5] |
| 7 | `fig:mix` | `fig_node_relation_mix.pdf` | Fold into `fig:evidence` (statement types × bundle) | |
| 8 | `fig:roles` | `fig_integrity_roles.pdf` | Drop (an AgentDojo SEM view MAY appear in `app:agentdojo-profile`) | policy view, not provenance |
| 9 | `fig:marker` | `fig_marker_status.pdf` | Drop from main; RQ4 figure only if RQ4 is included | marker unspecified (OM-3) |
| 10 | `fig:outcomes` | `fig_outcomes.pdf` | Drop | model behaviour [PA §13 Drop] |
| 11 | `fig:convoutcomes` | `fig_conv_outcomes.pdf` | Drop | idem |
| 12 | `fig:cmpsizes` | `fig_cmp_graph_sizes.pdf` | Merged into `fig:sizes` | |
| 13 | `fig:cmputility` | `fig_cmp_utility_asr.pdf` | Drop | idem |
| 14 | `fig:cmpbaseline` | `fig_cmp_baseline.pdf` | Drop | detection out of scope |
| 15 | `fig:example` | `example_graph.pdf` | Survive, regenerated (F6) | |

### O.4.2 Disposition of the old tables (32)

| Old table(s) | Disposition |
|---|---|
| `tab:terms` | Rewrite (hand-written, no numbers; O.1.8) |
| `tab:agentdojo-compare` | Drop; replaced by `tab:formats` (hand-written from [landscape/trace_formats.md §3.12]) |
| `tab:related` | Rewrite (O.2.2 row 2.4) |
| `tab:datasets` | Superseded by `tab:compat` (generated) |
| `tab:mapping` | Replaced by `tab:rules` (generated from the rule catalogue) |
| `tab:policy`, `tab:audit`, `tab:toolsets` | Move to `app:agentdojo-profile`; generated from SEM profile data |
| `tab:checks` | Replaced by `tab:validation` (generated counts; hand-written "establishes / does not establish" text) |
| `tab:models`, `tab:generation`, `tab:composition`, `tab:corpora` | Move to `app:sources` as generated per-source datasheet tables (`tab:sources`) |
| `tab:graphstats`, `tab:graphdist` | `tab:graphdist` survives, per source and per bundle (generated); `tab:graphstats` dropped |
| `tab:outcomes`, `tab:comparable` | Drop |
| `tab:artefacts` | Survive as `tab:issues` (generated, tabular fragment only; the old file was a full float, an exception [FP §2.4]) |
| `tab:baseline`, `tab:ablation`, `tab:blindspots`, `tab:mlsplit` | Drop |
| `tab:limits`, `tab:fair` | Rewrite; `tab:fair` generated from manifests |
| `tab:provkey` | Survive, regenerated for `apv` |
| `tab:searchyield`, `tab:searchpatterns`, `tab:searchartefacts` | Survive after the re-run search; `tab:searchartefacts` format column corrected (PA-D21) |
| `tab:convattacks`, `tab:convpipelines`, `tab:convbounds` | Drop |
| `tab:convpublished` | Optional in `app:sources` as an import-fidelity check: as-logged rates of the AgentDojo native import against AgentDojo's published tables. The published constants become profile data with citations [FP §7.7 item 5]. Kept only with the gap of up to 6 pp disclosed as unexplained (U-11; OM-20) |
| (dead) `tab_conformance.tex` | Not ported (FP-#9) |

### O.4.3 New and regenerated figures

All figure functions live in `agentprov_paper.render.figures`, take frames or values plus an output path,
and return the written path. Every number printed inside a figure is also a `Value`.

**F1 `fig:pipeline`** — `paper/figures/fig_pipeline.tex` (TikZ, `figure*`).
- Content: raw artefacts by dialect (`agentprov.capture/0.1`, `agentdojo.tracelogger` variants `v0.k11`,
  `v1.k14` and others, `adprov.transcript_v1`, `inspect.eval`; `stac.json_array` only as a planned scenario
  source, visually distinct); the `expand` stage that turns archive members into raw objects (AD-12); reader →
  mapper (rule catalogue `@n`) in isolated import workers → AER (13 record kinds, seal, execution digest) → SEM
  (semantics profile) → PROV (core, inference and assessment bundles, top-level conversion provenance);
  validators gating each write; corpus manifest digest chain [DEC D0, D8, D9; A2, A3]. Live capture is drawn
  only after U-18.
- Version strings MUST be `\apstat{spec}{…}` values (`aer`, `sem`, `capture`, `prov_spec`, `apv` = `0.1.0`).
- The lint rejects digits in TikZ node text.

**F2 `fig:evidence`** — `fig_evidence_classes.pdf`, `fig_evidence_classes(st: pd.DataFrame, out: Path)`.
- One horizontal stacked bar per (source, bundle ∈ {core, inference, assessment}). Segments are the
  shares of observed, derived and inferred statements; bars are annotated with the statement count.
- Sources in display-profile order, never pooled. Evidence-class colours are fixed tokens shared by every
  figure, checked for colour-vision safety [FP §3.6].
- Optional second panel: shares by statement type (absorbs old `fig:mix`). Answers RQ2(c): composition only,
  never the headline loss metric (R-57).

**F3 `fig:infoloss`** — `fig_information_loss.pdf`, `fig_information_loss(fs, profiles, out)`. The paper's
headline figure (R-57).
- Heatmap: rows are sources, columns are the field groups of O.3.5 (from `src/agentprov/stats/field_groups.toml`).
- Cell value: field-group coverage, the share of executions where the group is O or D. Cell glyph: the dominant
  status (`O`, `D`, `I`, or the unknown-reason code `NR` not_recorded, `LO` lost, `OW` overwritten, `WH`
  withheld, `AM` ambiguous, `NC` not_captured [DEC D2; R-08]). `not_applicable` cells are hatched and excluded
  from the denominator, and are allowed only where the group cannot exist for the source (R-57).
- A companion claim fails when a profile declares a group "observed" but the measured share is below
  100 % (`c3-declared-vs-measured`). Answers RQ2(a) and, through the glyphs, RQ2(b).

**F4 `fig:semdiff`** — `fig_semantic_diff.pdf`, `fig_semantic_diff(sd, out)`. Data come only from the pinned
gate-E reports (J.3.6; R-33); nothing in the figure is computed by the paper from graphs.
- Two panels, the release (generated) and converted v2.3 trees, never pooled.
- Rows are the report's v2.3 elements: the agent node, the user-query entity, the tool-call activity, the tool
  output, `adprov:defence_omitted`, R1 `wasGeneratedBy` (tool output), R2 `wasAssociatedWith`, R3 `used` of the
  user query (first turn), R4 `used` of earlier tool outputs, R5 `wasInformedBy`, R6 `used` sink taint, and the
  relation times; plus the `new` row for statements with no v2.3 counterpart.
- Stacked by J's closed disposition vocabulary: `kept`, `reclassified`, `moved`, `replaced`,
  `moved-to-assessment`, `dropped`, `new`; each segment also carries the target bundle and evidence class from
  the report. The mapping is `src/agentprov/prov/compat/semdiff-map.toml` with EF catalogue rule ids (the
  prov_semantics names of [landscape/prov_semantics.md §8 and §11] in brackets, e.g. R6 taint `used` →
  `aprov.a_taint@1` [A-TAINT] in the assessment bundle; R3/R4 → `aprov.use_context@1` in the inference bundle
  `inf.adprov-context_is_prefix-v1`, INFERRED per AD-05; R5 → `aprov.comm@1`, the full Inference-6 closure,
  AD-19(c)).
- Claims `c4-totals` check the row totals against frozen legacy counts: sink→⊥ taint pairs 41,066 (generated)
  [RF SEM-2; J.3.6]; `wasInformedBy` 72,633 / 68,212 [PA §15]; and `unmapped == 0`.
- The count of PROV-CONSTRAINTS Inference-6 communications entailed but not asserted by the v2.3 graphs is
  26,645 (in 5,161 of 17,664 generated graphs) and 23,449 (in 5,644 of 18,027 converted graphs): entailed
  99,278 / 91,661 minus asserted 72,633 / 68,212, with no asserted communication unentailed
  [landscape/prov_semantics_evidence/inference6_scan.json (`entailed_not_asserted`); landscape/prov_semantics.md
  §0 item 4]. J.3.6 counts the same pair as the R6 taint-only `used` edges (of 41,066 / 36,687 sink→⊥ taint pairs)
  [audit/provenance_evidence/evidence_stats.json (`sink_taint_only_used_edges`)]. The two readings are one
  quantity counted two ways, identical by construction: each R6 taint-only `used(a_k, e_j)` edge (deduplicated
  against the previous-turn R4 edges) entails, via Inference 6, exactly one `wasInformedBy(a_k, a_j)`, and the
  builder asserts only the previous-turn (R5) edges; the turn-gap breakdowns close on the same totals
  (10,570 + 6,421 + 3,447 + 6,207 = 26,645; 8,748 + 5,690 + 3,458 + 5,553 = 23,449) [EF E.1.6; SWEEP_r2 EV-1].
  The paper MAY cite the pair for either quantity, as `external` values (O.3.5) that cite the evidence file of
  that reading, and both files where it states the identity. The pair is never pooled across the two trees.

**F5 `fig:lineage`** — `fig_corpus_lineage.pdf`, `fig_corpus_lineage(li, profiles, out)`, Graphviz.
- Nodes: one per corpus, plus upstream artefact nodes `repo@commit`.
- Edge types: code lineage (`forked-from`, dashed), byte-identical raw artefacts (solid, labelled with
  the count), re-packaging (`contained-in`), same-cell replicates (dotted, count).
- Data come from the corpus manifests, `raw/origins.jsonl`, `source_key` duplicates and the owner declarations
  in each profile's `[lineage]` only; collection manifests and per-execution lineage documents are deferred
  (AD-10 rows 5–6). Investigation measurements become cross-check claims, each `external`-cited:
  - All 18,234 files of AgentDojo-PROV's legacy `runs/` are present, blob for blob, in upstream `runs/`
    at `c274885…` (which holds 7 further Mixtral files; the `agentdojo-upstream` import uses all 18,241 pinned
    blobs, R-32); versus upstream HEAD, 14,182 are identical and 4,052 are different executions (2024 travel
    and Llama re-runs) [sources/agentdojo.md §5.1; verify/agentdojo.md].
  - AgentDojo-Inspect `runs/`: 21,999 of 21,999 identical to AgentDojo v0.1.25 `runs/`
    [sources/agentdojo-inspect.md §6].
  - The survey's Zenodo zip re-packages 36,679 upstream run files [sources/agent-security-tools-survey.md §0].
  - AgentDyn vendors DRIFT's 949 AgentDojo-suite runs byte-identically [sources/drift.md §6.3]; corpus
    `agentdyn` excludes them with owner `drift` (HL H.4.2). AgentDyn's variant C holds re-keyed copies of
    AgentDyn's own history blobs, not of DRIFT history (R-62).
  - ROPE `agentlab/res/` has 13,525 files byte-identical to AgentLAB, and AutoDojo-attack runs exist only
    in ROPE (2,847) [sources/rope.md §5.4; sources/autodojo.md §0].
  - Mandate: 396 new executions that replicate upstream cells, 0 duplicates
    [sources/mandate-agentdojo-eval.md §7].

**F6 `fig:example`** — `example_execution.pdf`, `fig_example(ex, out)`.
- Golden trace R01 (`prov-deepseek-chat`, benign, `banking_user_task_0_benign`): 4 tool calls over 3
  tool-bearing turns, 10 nodes and 18 relations in v2.3 [baseline/BASELINE.md §7].
- Panel (a): the compat-profile v2.3 graph. Panel (b): the `agentprov-prov/0.1` core bundle with the
  assessment overlay, styled by evidence class.
- Panel (b) uses the framework's renderer, `agentprov render` (the baseline `render_prov_graph` ported to
  `agentprov-prov/0.1` bundles; `render` extra with pydot and the Graphviz `dot` binary; AD-10 as ruled; MN
  N.2.13): the core bundle, and the assessment overlay through `--bundle all`. Panel (a) is drawn by
  `agentprov_paper.render.figures` with the same style tokens as panel (b): `agentprov render` reads only `agentprov-prov/0.1`
  bundles and has no compat input (AD-10 as ruled; SWEEP_r2 AD-SW18). Unknown integrity is never styled as trusted.
- Labels are ids, record kinds and tool names only. The model label is the requested id `deepseek-chat`
  (OM-7). The execution is pinned by its execution id `ex`, not by path; this replaces `EXAMPLE_TRACE`
  [FP §3.6].

**F7 `fig:provkey`** — `fig_notation_key.pdf`, `fig_notation_key(out)`. Generated from the `apv` 0.1.0
vocabulary: `apv:ModelInvocation`, `apv:ToolExecution`, message entities typed `prov:Collection` with their
tool-call request entities as members (`hadMember`, AD-19(a)), the generic `apv:GenericActivity` and artefact
entity of rules G-ACT and G-GEN (AD-15), the agent kinds of D7, the three bundles, evidence-class styles.

**F8 `fig:sizes`** — `fig_statement_ccdf.pdf`. CCDF of statements per execution, per source, core bundle
and total, log-log, never pooled (generalises old Figs. 6 and 12).

**F9 `fig:capture`** — `paper/figures/fig_capture.tex` (TikZ). The AgentDojo live backend as a spawned
worker (`agentprov_backend.worker` in the backend project's own environment, AD-01): the stock (`native`) LLM
element recorded by the recording transport and LLM-span brackets (`input_at`, `n_messages`), the pass
recorder, the `TimingToolsExecutor` mirror, the `capture/0.1` event log written by `agentprov_capture`, the
native TraceLogger file written alongside, and declared instrumentation [DEC D3, D5; AD-09; R-16]. The
opt-in `gateway_compat` element (the `_CompatLLM` port) is drawn only if a reported session used it, labelled as
request-modifying instrumentation (NC-LIVE-01). Only included if an approved, sealed, non-`test_only` live
corpus is reported (U-18; NC-LIVE-02).

### O.4.4 New tables

| Label | File | Generated from | Columns | Gate |
|---|---|---|---|---|
| `tab:compat` | `tables/tab_compat.tex` | `profiles` + `executions` frames | source and part; lineage (fork base or "independent", from the owner profile's `[lineage]`); evidence availability (`yes\|partial\|no`); dialect(s); live / import; implementation status (`supported\|partial\|planned\|not_possible`) with its caveat, per part or worst-case with a `mixed` marker, never best-case; licence policy (`include\|reference\|nc_partition\|forbidden`); sealed executions (`unit == agent_execution ∧ execution_observed`) in the paper's corpora, with outcome-only records and scenarios in separate columns | every status equals the gated registry value (compared, never typed; R-15); status ∈ {`supported`, `partial`} ⇒ sealed executions > 0 or the row says "not in this paper"; `not_possible` ⇒ reason present; live parts show their registry caveat (D.3.2 rule 3's "fake-client tested in v0.1; no real-model run", or the approved pilot's record, D-722) unless U-18 applies |
| `tab:capability` (app) | `tables/tab_capability.tex` | profiles | declared capability per field group | `c3-declared-vs-measured` |
| `tab:rules` | `tables/tab_rules.tex` | rule catalogues from the framework's package resources at the versions the corpora record (the corpus `rules/` copies are digest-compared records, AD-14) | rule id; statement; evidence class; required evidence; emitted count per source (from the `agentprov stats` statements table); the generic rules G-ACT, G-USE, G-GEN and G-ASSOC listed even with a zero count | every emitted rule id declared (`c1-rules-declared`) |
| `tab:validation` | `tables/tab_validation.tex` | `validation` frame (the sealed corpus `validation/`) | tier (D8 1-7) × source: pass / fail / skipped / not_applicable; "establishes" and "does not establish" (hand-written text from a data file) | skips reported separately, never summed into passes [DEC D8] |
| `tab:semdiff` | `tables/tab_semdiff.tex` | `semdiff` frame (the pinned gate-E reports, generated from `semdiff-map.toml`; R-33) | v2.3 element; release / converted count; disposition (J's 7 values); bundle and evidence class; `agentprov-prov/0.1` rule id(s) | `c4-totals`; no cell is edited by hand |
| `tab:versions` | `tables/tab_versions.tex` | manifests + `spec` values | software (`agentprov 0.1.0`), `aer/0.1`, `sem/0.1`, `capture/0.1`, `agentprov-prov/0.1`, `apv 0.2.0`, per-adapter SemVer, source-profile and rule-catalogue versions (integers, AD-18), semantics profile (`agentdojo.suites` version), corpus SemVer and manifest digests [DEC D9] | — |
| `tab:issues` | `tables/tab_issues.tex` | `executions` frame (index `issues`, register codes) | issue code × source counts, using the canonical codes: seal issues as `map.<code>` (e.g. `map.no_execution_observed` for empty logs, `map.aborted_attempt`, `map.incomplete_run`, `map.outcome_imposed_by_runner`, `map.no_outcome_recorded`, `map.unexecuted_tool_call`, `map.accounting_inconsistent`; adapter codes `map.<ns>.<code>`) and other register codes `<stage>.<code>` (e.g. `time.implausible`) | every issue code in the data appears in a row |
| `tab:sources` (app) | `tables/tab_sources.tex` | manifests + profiles | per-source datasheet rows (models requested, attacks, suites, dates as recorded) | — |
| `tab:graphdist` | `tables/tab_graph_dist.tex` | `statements` frame | mean, SD, quartiles, p95, max of statements per execution per source and bundle | — |
| `tab:fair` | `tables/tab_fair.tex` | manifests | FAIR facets per corpus | — |

### O.4.5 Rules for all floats

1. Generated tables are tabular-only fragments. The first line is
   `% GENERATED by agentprov-paper (<function>) — do not edit`. They are `\input` inside a size wrapper in
   the tex, as before [FP §2.4].
2. Every number in a generated table comes from a `Value` passed to the renderer, never directly from a
   frame. Therefore every number in the PDF is in `values.json`.
3. Hand-written floats (`tab:terms`, `tab:formats`, `tab:related`, `tab:limits`, the validation text,
   TikZ figures) are subject to the hand-typed-number lint (O.3.7). They SHOULD be converted to generated
   tables whenever they need numbers. The old macro-heavy hand-written tables (`tab:corpora` 43 macros,
   `tab:audit` 24, `tab:generation` 15, `tab:blindspots` 15) went stale [FP §3.7, §7.8 step 7].
4. Captions use `\apstat` for numbers.
5. No float may contain payload text or free text from raw artefacts or AER content (O.3.5).
   `lint.check_no_payload(outputs, payload_digests)` SHOULD scan generated tables and figure text layers
   for the registered payload strings of every corpus and fail on a match.
6. A figure whose input is missing fails the build. The old pipeline left `example_graph.pdf`,
   `tab_ablation.tex` and `tab_tool_sets.tex` stale with only a warning (FP-#16).

---

## O.5 Initial commit of the manuscript repository

### O.5.1 Repository

- Path: `~/Desktop/PhD/Labs/3. AgentPROV paper/` (did not exist on 2026-10-07; create
  it). `git init -b main`. No remote, as D12 says "repo-less-for-now". A private GitHub remote is added
  only on the user's instruction (user preference: private repositories unless told otherwise).
- Python tooling uses uv (`pyproject.toml` + `uv.lock`), not conda. The old repo used a conda
  environment and `requirements.txt` [FP §0, §2.5].
- The initial commit contains no corpus data, no caches, no `.env` and no secrets.
- Commit message: `Initial skeleton of the AgentPROV manuscript` with a body listing the frozen inputs
  (old manuscript commit, file digests).

### O.5.2 Exact file list

| Path | Tracked | Kind | Content at the initial commit |
|---|---|---|---|
| `.gitignore` | yes | hand | LaTeX artefacts (`paper/*.{aux,abs,bbl,blg,log,out,spl,synctex.gz,fdb_latexmk,fls}`); `paper/.texpadtmp/`; `.cache/`; `__pycache__/`, `*.pyc`, `.venv/`; `.env`, `*.env`; `corpus/`, `corpora/`, `raw/`, `*.aer.jsonl`, `*.parquet`; `pdfs/`, `presentation/`; `.claude/settings.local.json`, `CLAUDE.local.md`; `.DS_Store`, `._*`. Adapted from the old `.gitignore`, but `AGENTS.md` and `CLAUDE.md` are not ignored (O.5.3) |
| `.gitattributes` | yes | hand | `* text=auto eol=lf`; `*.pdf binary`; `*.png binary`; `*.parquet binary` |
| `LICENSE` | yes | hand | MIT, "Copyright (c) 2026 Nicholas Jones", mirroring the old repo's LICENSE. Covers code (U-12); the licence of the manuscript text is a user decision (OM-23; U-11) |
| `README.md` | yes | hand | title; relation to the framework repo (path `../AgentPROV-framework`, not yet created) and to the corpora (no DOIs yet); layout; build commands (`uv sync`, `make skeleton`, `make paper`); the rule "no number is hand-typed" |
| `AGENTS.md`, `CLAUDE.md` | yes | hand | agent guidance (O.5.3): `AGENTS.md` points to `MAINTAINING.md` and states the untrusted-content rule; `CLAUDE.md` points to `AGENTS.md` (R-50 convention) |
| `MAINTAINING.md` | yes | hand | the versioned operating guide, replacing the old gitignored and stale CLAUDE.md (FP-#1-#8). Sections: build and regenerate; value keys and alias policies; claims and lint; adding a source to the paper; reuse ledger (O.2.4, empty table); release checklist = every O.6 item with status; untrusted-content rule |
| `CHANGELOG.md` | yes | hand | `## Unreleased` — skeleton created from AgentDojo-PROV manuscript `24ac03f`; inputs frozen (digests) |
| `pyproject.toml` | yes | hand | `[project] name = "agentprov-paper"`, `version = "0.0.0"`, `requires-python = ">=3.14"` (the core's floor, AD-16 as ruled, so that pinning the framework later needs no interpreter change; R-64), dependencies `matplotlib>=3.8`, `numpy>=1.26`, `pandas>=2.2`, `pyarrow>=16`, `rfc8785` (lower bounds from the old `requirements.txt`); `[project.scripts] agentprov-paper = "agentprov_paper.cli:main"`; `[dependency-groups] dev = ["pytest", "ruff"]`; a commented placeholder `data = ["agentprov"]` (plain core: the `analysis` extra does not exist in v0.1, AD-10; `agentprov[render]` only if `fig:example` is rendered by `agentprov render`, AD-10 as ruled) and `[tool.uv.sources] agentprov = …`, enabled in the commit that first pins a framework commit; `[tool.ruff] line-length = 110, target-version = "py314"` |
| `.python-version` | yes | hand | `3.14` (AD-16). The paper reads sealed corpora and ingests no archives, so the core's release-mode refusal below 3.14.8 does not apply to it; release-mode paper builds record the full interpreter version in `BUILD_PROVENANCE.json` (O.3.9) |
| `uv.lock` | yes | generated | `uv lock` over the dependencies above |
| `Makefile` | yes | hand | targets `skeleton`, `data`, `values`, `render`, `check`, `paper`, `determinism`, `all`, `clean`; all paths quoted; `paper` exports `SOURCE_DATE_EPOCH` (O.3.2) |
| `paper.toml` | yes | hand | `[paper] schema = "agentprov-paper/config/1"`, `mode = "draft"`, `venue = "unknown"`, `abstract_max_words = 250`; `[framework] commit = ""`; no `[[corpus]]` and no `[[report]]` entries; `[legacy] manuscript_commit = "24ac03f26e97cec96b5bbb77cd876d671a37c4e4"`, `framework_commit = "579a908354b93361efe0905ffb7623256aa96a06"`, `macros_sha256 = "1c5c70ea…14b2"` |
| `lint-allow.toml` | yes | hand | empty allowlist with schema header |
| `paper/agentprov_paper.tex` | yes | hand | preamble of O.3.1; front matter with the O.1.3 recommended title (the claim gates of O.1.6 decide the final variant) and authors; abstract stub `\TODO{abstract per spec O.1.4}`; every section and appendix of O.2.3 with its `\label` and one `\TODO{…}` naming the source material (e.g. `\TODO{rewrite from old §3.5 (old.tex:1394-1521); see spec O.2.2}`); no `\apstat` uses; CRediT and competing-interest blocks copied from old.tex:3794-3804 with their TODO; `\balance`, bibliography, `\onecolumn\appendix` |
| `paper/apstatic.tex` | yes | hand | the macros of O.3.4 |
| `paper/macros.tex` | yes | generated | header; `\apdef` lines for the `legacy-adprov-v23` values named in `aliases.toml`; the alias block |
| `paper/values.json` | yes | generated | JCS document `{"schema":"agentprov-paper/values/1","values":[…]}` with the frozen legacy values only |
| `paper/BUILD_PROVENANCE.json` | yes | generated | O.3.9 fields; `corpora: []`; `reports: []`; `framework: null`; the shared claims-library checks recorded as skipped |
| `paper/refs.bib` | yes | copied | byte-identical copy of the old `refs.bib` (60 entries, sha256 `d0f0a5a8…dcac`). The O.3.3 fixes and additions go in the next commit so the diff is reviewable |
| `paper/.latexmkrc` | yes | hand | O.3.2 |
| `paper/tables/.gitkeep`, `paper/figures/.gitkeep` | yes | — | empty |
| `paper/agentprov_paper.pdf` | yes | generated | skeleton PDF from `make paper`, tracked as in the old repo for reviewers without TeX [FP §2.5] |
| `legacy/adprov-v2.3/macros.tex` | yes | copied | byte-identical copy of old `paper/macros.tex` at `24ac03f` (1,015 macros) |
| `legacy/adprov-v2.3/FROZEN.json` | yes | hand | `{"manuscript_repo": "AgentDojo-PROV-manuscript", "commit": "24ac03f…", "framework_commit": "579a908…", "files": {"paper/macros.tex": {"sha256": "1c5c70ea…14b2", "n_macros": 1015}, "paper/refs.bib": {"sha256": "d0f0a5a8…dcac", "n_entries": 60}, "paper/adprov_paper.tex": {"sha256": "4c8dee0a1fcb09cb92ae2711cc190656cd9c9ba910636339211f9eb5d6954c63"}}, "corpus_state": "local v2.3, undeposited; Zenodo latest v2.2 (10.5281/zenodo.21052314)", "frozen_on": "2026-10-07"}` [baseline/BASELINE.md §0, §8 item 1] |
| `legacy/aliases.toml` | yes | hand | `schema = "agentprov-paper/aliases/1"`; three `frozen` entries for prior-work statements: `AdpNumTraces` → `legacy-adprov-v23/n_traces_generated`, `AdpConvNumTraces` → `…/n_traces_converted`, `AdpBothConformanceN` → `…/n_graphs_total`, each with `cite = "adprov2026corpus"`; one `retired` entry `AdpStealthMaxModel` (value "DeepSeek-V3.2"; reason CAP-6) |
| `legacy/divergences.toml` | yes | hand | empty table with schema header |
| `src/agentprov_paper/__init__.py` | yes | code | `__version__ = "0.0.0"` |
| `src/agentprov_paper/{cli,config,values,legacy,claims,lint}.py` | yes | code | implemented for the skeleton: config loading, `Value`/`ValueSet` (with `ValueBasis`), the frozen-macro parser, alias emission, claims registry (empty `REGISTRY`), the paper-specific lint rules (the shared claims-library checks report *skipped* until a framework is pinned), `check-log`, `check-keys`, `check-bib` |
| `src/agentprov_paper/{data,frames}.py` | yes | code | signatures of O.3.5 that raise `NotImplementedError("framework not pinned")` while `paper.toml` has no corpora |
| `src/agentprov_paper/stats/{__init__,inference,spec}.py` | yes | code | `wilson`, `bounds` ported with tests; `spec_values` stub |
| `src/agentprov_paper/render/{__init__,fmt,style,macros,tables,figures}.py` | yes | code | `fmt` and `macros` implemented; `style` holds cas-dc widths `COL_W, FULL_W = 3.45, 7.1` in and the rcParams of [FP §3.1, §3.6]; `tables`/`figures` empty registries. No `pdfnorm` (deferred with PDF byte determinism, AD-10 row 20) |
| `src/agentprov_paper/profiles/display.toml` | yes | data | empty `[source]` table (display names, order, `pool_group`) |
| `tests/test_values.py`, `test_fmt.py`, `test_legacy.py`, `test_aliases.py`, `test_lint.py`, `test_claims.py`, `test_determinism.py` | yes | tests | key grammar and duplicates; `fmt_int(17664) == "17,664"`; p round-up; the frozen parser returns 1,015 names and handles the six brace-containing values (FP-#11); a retired alias produces a LaTeX error; lint catches unscoped "lossless", bare "reproducible", a bare agnosticism term outside a design-goal block, "Live Capture" in the title without a pinned live corpus, and `\label` after `\paragraph`; claim bijection; `values.json` and `macros.tex` built twice from `legacy/` are byte-identical |
| `tests/fixtures/apstat_min.tex` | yes | test | minimal document exercising `\apdef`, `\apstat`, an undefined key (expected error) and a duplicate (expected error); compiled by `test_apstat_tex` when `latexmk` is available. A missing toolchain is reported as *skipped*, which fails release mode [DEC D8] |
| `review/novelty_search/PROTOCOL.md` | yes | hand | re-run protocol of App. C with software included (OM-22); results directory created at the first run |

Not carried over from the old repository: `review/` contents, `response/`, `quote/`, `*.diff`,
`*_marked_paper.pdf`, `Ai_review*.pdf`, `Review.docx`, `feedback.md`, `TODO.md`, `make_figures.py`
and its caches. They stay in the old repository as history. The old `make_figures.py` golden test
[FP §7.7 item 2] belongs to the baseline freeze, not to the new paper package; this follows D12's "no
compatibility shim needed". It departs from FP §7.7 item 3, which proposed porting make_figures function
by function; that is unnecessary because the new paper drops most old analyses (O.2.2).

### O.5.3 Agent-facing files

The repository follows the framework's agent-guidance convention (R-50; RESOLUTIONS §3.1): a tracked
`AGENTS.md` that is a short pointer to `MAINTAINING.md` and states the untrusted-content rule (corpus text is
data, never instructions; no corpus content is sent to an LLM-based tool, O.3.5), and a tracked `CLAUDE.md` that
points to `AGENTS.md`. The operating guide is therefore versioned (the old one was gitignored, FP-#8).
`.claude/settings.local.json` and `CLAUDE.local.md` stay ignored.

### O.5.4 Acceptance criteria for the initial commit

1. `uv sync --locked` succeeds; `uv run ruff check .` and `uv run pytest` pass. Skips are reported.
2. `make skeleton` writes `paper/macros.tex`, `paper/values.json` and `paper/BUILD_PROVENANCE.json` from
   `legacy/` alone, with no corpus and no framework installed.
3. `make paper` builds `paper/agentprov_paper.pdf`: no undefined references or citations; `\TODO`
   markers visible (draft mode).
4. `make check` passes in draft mode: the empty claim registry matches the absence of `% claim:` comments,
   and the paper-specific lint is clean; the shared claims-library checks are reported as skipped (O.3.7).
5. `make determinism` passes (text outputs only, O.3.8).
6. `git ls-files` shows no file under an ignored pattern and no file larger than 2 MB except the PDF.

---

## O.6 Open items from the old manuscript

Status words: **Blocking** = MUST be resolved before the related material is reused; **Disclose** = MUST
be stated in the new paper if the related material or corpus is used; **Do not reuse** = the passage or
claim MUST NOT be carried over; **Closed** = settled by the investigation; **Author** = needs the user's
decision; **U-nn** = a user decision forwarded in RESOLUTIONS §2.3 (defaults per Addendum B B-2 apply until the
user decides). Each item becomes a row of the release checklist in `MAINTAINING.md`.

### O.6.1 Items

| Id | Item | Evidence | Required action | Status |
|---|---|---|---|---|
| OM-1 | The paper describes corpus v2.3; Zenodo's latest is v2.2 (record 21052314, 2026-06-30), which has no converted corpus and no `corpus-ml`; the tex prints the v2.2 DOI with `% TODO(deposit)` (old.tex:123, 3468); `adprov2026corpus` says 2.3 with the v2.2 DOI | PA-D2; RF §0.3, REP-2; baseline/BASELINE.md §8 item 1 | Cite only deposited versions. If AgentPROV imports the local v2.3 `transcript/v1` files as raw evidence (corpus `agentdojo-prov-v2`), their origin is framework `579a908` plus the corpus manifest digests [DEC D3], and the paper states "v2.3 (commit + digests), not the v2.2 deposit" (R-26). **Blocking for C2 and C4** unless the frozen v2.3 checksum evidence (6 release + 17 converted `checksums.sha256` lists and J.1.4's five listing digests) ships as raw artefacts in the deposits (R-26) or v2.3 itself is deposited (U-01) | Blocking (C2, C4) + U-01. **Cleared 2026-10-28 (D-900):** v2.3 was deposited on 2026-10-10 (`10.5281/zenodo.23276620`); cite that record |
| OM-2 | Tag `corpus-v2.3` (`a7002b4`) predates the semantics described: it still draws the predecessor chain and has 3 checks; 26 commits follow | PA-D3 | Cite commit `579a908` (`corpus-v2.3-26-g579a908`), never the tag | Blocking |
| OM-3 | The injection marker is not in the normative spec; its revision history is understated; "one-sided error" is overstated | PA-D4, PA-D5, PA-D6 | Any marker-based number is recomputed under the SEM marker algorithm with its rule version [DEC D6]. Legacy marker numbers appear only as `frozen` aliases with citation. "One-sided" is dropped unless a false-positive rate is measured. No "ground truth" wording. RQ4 is limited to the derived marker versus the registered payload map; there is no outcome replay in v0.1 (AD-10 row 2) | Blocking |
| OM-4 | Policy (taint) edges are plain `prov:used` (fw:agentdojo_prov/build_prov.py:462-477); under Inference 6 the graphs entail communications the builder refuses to draw: 26,645 (released) / 23,449 (converted), identical by construction to the R6 taint-only `used` edges (F4) | PA-D1; landscape/prov_semantics.md §0 item 4; landscape/prov_semantics_evidence/inference6_scan.json; audit/provenance_evidence/evidence_stats.json; SWEEP_r2 EV-1 | "A PROV reasoner is not handed a dependence that does not exist" (old.tex:1049-1050) is not reused. The new paper reports the defect quantitatively: dispositions from the gate-E reports (F4, `tab:semdiff`), and the pair as `external` values for either reading, each citing its evidence file (F4) | Do not reuse + Disclose |
| OM-5 | The LLM client was modified and this was not disclosed: `_CompatLLM` rewrites `developer` → `system` (fw:agentdojo_prov/runtime.py:239-242), adds retries, and later resamples. The generation code is not in version control (framework repo starts 2026-08-09; generation 2026-06-05..27) | PA-D9; PA §1 item 6 | Disclose whenever the generated corpus is used. The AgentPROV import of those executions declares the harness version `unk: not_recorded`, with the deviation as an assumption and not as an observed fact [DEC D5 "observer effects"]; their context membership is INFERRED (inference bundle `inf.adprov-context_is_prefix-v1`) unless the user supplies a digest-pinned generation-time harness (AD-05; U-01). New live sessions default to the stock `native` LLM element; `gateway_compat` (the `_CompatLLM` port) is an opt-in declared as request-modifying instrumentation (AD-09; NC-LIVE-01). The passage "none alters what the model sees" (old.tex:889-891) is not reused | Disclose + Do not reuse |
| OM-6 | The converted corpus's source is unpinned (no commit, path or hash in `meta`) | PA-D18 | The AgentDojo import fetches from a pinned upstream commit [DEC D3: `c274885…`] and imports all 18,241 pinned blobs, incl. the 7 Mixtral files (R-32; RESOLUTIONS §1.3 O row "Upstream file set"). The paper states that the 18,234 baseline blobs are present in several upstream commits (`c2748856`, `9d7d1391`, `7d1de5a1`, `ae8d2c01`, `15de4430` [verify/agentdojo.md]; `6260c31` [verify/agentdojo-inspect.md]), so the commit the original copy came from cannot be decided from the files | Blocking |
| OM-7 | "DeepSeek-V3.2": on the run date `deepseek-chat` reportedly routed to `deepseek-v4-flash`; the served model is unknown | RF CAP-6; TODO #1 | Use the requested id `deepseek-chat`, served model `unk`. The `retired` alias and the lint term enforce this. Do not cite `deepseekv32` for these runs | Blocking |
| OM-8 | False sentence: "none of these models returned reasoning blocks" (old.tex:3278-3280); AgentDojo's converter discarded returned reasoning | RF CAP-3 | Not reused. AgentPROV records the absence as `not_captured` where the capture path discarded it [RF AR-2] | Do not reuse |
| OM-9 | Timing: "every activity carries times" is false (2 untimed generated activities, all 68,620 converted); the run-start fallback is mis-summarised; timing was keyed by a reused id (GLM-4.6 `call_3275`), and that fix is disclosed only in the framework CHANGELOG "by the author's instruction" | PA-D8, PA-D11; RF SEM-9, §6 | No time is stated that is not recorded [DEC D2, D7; NC-ALL-01]. The generated `tab:issues` will count ambiguous timings. Whether the prose discusses the GLM case is the user's decision (U-11); recommended: disclose, consistent with the evidence-only stance | U-11 + Disclose |
| OM-10 | "Closed tool inventory" is false for the observed data: 49 generated and 12 converted out-of-inventory tool names | PA-D10 | Not reused. SEM integrity is three-valued and fail-closed for unknown tools [DEC D6] | Do not reuse |
| OM-11 | The static coverage check mirrors the policy rather than evidencing coverage | PA-D7 | Not presented as evidence | Do not reuse |
| OM-12 | The mapping table is incomplete for attributes; `capture_spec.md` presented as normative carries stale and internal content | PA-D17, PA-D20 | `tab:rules` is generated from the catalogue. `capture_spec.md` is not cited as normative | Do not reuse |
| OM-13 | The write-gate description is inaccurate; `wasInformedBy` is checked against the graph's own attributes, not the transcript | PA-D12, PA-D13 | Not reused. The evidence-linkage tier [DEC D8] replaces the claim | Do not reuse |
| OM-14 | Versioning claims: `adprov.ttl` edited in 5 commits under `owl:versionInfo "1.0"` (fw:docs/ns/adprov.ttl:24); graphs carry no version | PA-D14; RF REP-5 | `adprov:` stays frozen for the compat profile; `apv` is versioned [DEC D7]. Until the w3id registration is submitted with the user's consent (U-02; prepared, not submitted, by default, Addendum B B-2), the paper MUST say the `apv` IRIs do not yet resolve [landscape/prov_semantics.md §12 item 1] | Disclose |
| OM-15 | The portability claim "imports nothing from AgentDojo" is literally true, but the builder hard-codes AgentDojo's YAML, PI-detector string and query convention | PA-D15 | Not reused | Do not reuse |
| OM-16 | Defended configurations cannot be live-captured (`make_instrumented_pipeline` raises) | PA-D16 | The v0.1 AgentDojo live backend keeps this limit as a typed refusal (RESOLUTIONS §1.3, B row "Defended pipelines in live v0.1"); `sec:live` states it | Disclose |
| OM-17 | Smaller over-claims: PROV-CONSTRAINTS pass in the abstract and C2 without the caveat (time constraints vacuous on the converted corpus); `tab:searchartefacts` gives the format "PROV-O (Turtle, JSON-LD)"; "nine mutation tools" includes a read; id-disambiguation wording | PA-D21..PA-D24 | Not reused; the corrected forms are generated | Do not reuse |
| OM-18 | Numbers disagree between the paper's macros and the review documents: ASR "within 6.3 pp" vs "up to 6.2 pp"; benign utility "within 3.6 pp" vs "within 2.7 pp" | PA §9; RF CAP-9, MTH-8 | No number is copied from prose, response letters or reports. Only generated values or the frozen `macros.tex` are used | Blocking (rule) |
| OM-19 | 207 empty Claude 3 Opus logs were excluded; their durations of 0.006-0.047 s with T/F outcomes are implausible for an API round trip | PA §8; verify/agentdojo-inspect.md (gap note) | AgentPROV seals them, with the 2 ROPE logs of the same shape, as `unit: outcome_only` records with `execution_observed = false` and issue `no_execution_observed` ("records with outcomes, no execution observed"; R-28), not as a silent exclusion and not as executions (the D5 principle; status and issues per DEC D9; NC-ALL-13). The paper explains why its execution count differs from the old 18,027: the empty logs are kept as outcome-only records and counted separately, and the import uses the 18,241 pinned blobs (OM-6) | Disclose |
| OM-20 | Converted attack success exceeds AgentDojo's published tables in 12 of 13 pipelines, unexplained | RF CAP-9; TODO #7 | Only relevant if `tab:convpublished` is kept (U-11: keep only with the gap of up to 6 pp disclosed); then the gap is stated as unexplained | Disclose + U-11 |
| OM-21 | Model-behaviour results (RQ3, rankings, name-in-payload confound, one sample per cell, aborted-cell selection) | RF CAP-5, CAP-8, MTH-2 | Not reused. If cited as prior work, their caveats are cited with them | Do not reuse |
| OM-22 | The novelty search is a 2026-09-30 snapshot and excluded software (criterion I4) | RF NOV-1 | Re-run with the App. C protocol, software included, positive control, dated. "First" claims only via a scoped claim (O.1.2) | Blocking |
| OM-23 | Abstract length (~264 words); venue unknown; co-author ORCIDs, affiliations and CRediT TODOs (old.tex:11-13, 67, 3795); licence of the manuscript text | RF PRS-4; FP §2.1, §7.9 | Decide the venue and its limits; confirm authors | U-11 |
| OM-24 | Bibliography housekeeping: stale entry count, `adprov2026corpus` version/DOI mismatch, TraceCaps blocked (ACM DL 403), LivePI cited once, landscape literature only summarised second-hand | PA §2; RF NOV-2; landscape/prov_semantics.md §6, §12 item 6 | O.3.3 fixes; read the PDFs before citing landscape works | Blocking (for those citations) |
| OM-25 | The operating guide (CLAUDE.md) is gitignored and stale (import list, check counts, cache counts, section numbers) | FP-#1..#8 | `MAINTAINING.md` is tracked (O.5) | Closed by O.5 |
| OM-26 | Freshness of the conformance caches: 569 graphs newer than the caches | FP §3.5 | Settled for the baseline: `recompute --dry-run` changed 0 files, and all five checks pass on all 35,691 graphs at `579a908` (2026-10-07) [baseline/BASELINE.md §0, §3, §6] | Closed |
| OM-27 | Review provenance: Round 1 and the CMU reviews were AI-generated, some claims come from lossy PDF parses, and the model-selection rationale is still a placeholder | RF §0.2, §6, MTH-9 | Response letters are not evidence. Rejected review claims (RF §0.2) are not answered again. The model-selection rationale only matters if a live pilot is reported (U-10, U-18) | Author |
| OM-28 | Consumer safety: the corpora contain live injection payloads that can target LLM-based consumers | PA §10 "missing threats" | `sec:uses` and `sec:impact` MUST warn and state the untrusted-input stance | Disclose |
| OM-29 | Licences of the new sources differ: STAC CC BY-NC (licence policy `nc_partition`; STAC is planned, so no `-nc` corpus exists in v0.1); AgentHarm data-use clause (a separate restricted-use corpus, U-05); CIAware-Bench no licence (`reference`; AD-21, U-04); survey CC BY 4.0; ROPE, AgentDyn, DRIFT and Mandate MIT (AgentDyn "MIT as declared; not legally settled", Mandate "publisher unverified", R-14); AgentDojo-Inspect NIST notice plus MIT | finding JSONs; sources/*.md §1; DEC D3; R-14 | `tab:compat` and `sec:availability` state, per source, the licence policy, the licence basis verbatim, and whether raw evidence is included or only referenced; deposits are grouped by licence class (AD-20) | Disclose |
| OM-30 | The old description of ROPE's logs ("about 10,800 … four models … AgentDojo's three suites and AgentDyn's three") implies a crossed grid that does not exist | sources/rope.md §5.4 | Not reused. Counts come from the ROPE corpus | Do not reuse |

### O.6.2 Kept from the old manuscript as method (no open item)

These may be carried over in substance; numbers are rebound:
- the separation of capture from interpretation and the recompute invariant;
- scoped completeness (tri-state `record_complete`);
- "declare, never invent", without sentinels;
- the conformance "does / does not establish" passage;
- the excluded/unscored/flagged taxonomy with worst-case bounds;
- the dated, criteria-based search protocol with a positive control;
- the floor-baseline discipline, cited as prior work.

Source: [PA §13 Keep].

### O.6.3 Author decisions collected

Mapped to the user decisions of RESOLUTIONS §2.3; until the user decides, the defaults of Addendum B B-2 apply
(no Zenodo deposit; no w3id submission; real-model live runs only with the user's keys and consent).
1. Deposit AgentDojo-PROV v2.3 on Zenodo or not, and supply a digest-pinned generation-time harness or not
   (OM-1, OM-5; **U-01**). Recommended: ship the v2.3 checksum lists regardless (R-26); deposit v2.3 before the
   paper cites it. *Done: the user deposited v2.3 on 2026-10-10 (`10.5281/zenodo.23276620`, D-900).*
2. Disclose the GLM-4.6 shared-start timing case in prose (OM-9; **U-11**; recommended: disclose).
3. Venue, word limits, authorship (ORCIDs, CRediT), manuscript-text licence, DeepSeek naming, the reasoning
   sentence, keeping `tab:convpublished` with the gap disclosed, and whether and when to add a private GitHub
   remote for the manuscript repository (OM-7, OM-8, OM-20, OM-23; **U-11**).
4. A real-model live `capture/0.1` pilot with dedicated, spend-capped keys (**U-10**) and approval of its results
   before any "Live Capture" title variant (**U-18**; AD-08 as ruled).
5. The name "AER": kept per AD-22; the user has the final say before the phase-6 freeze (**U-15**).
6. w3id registration of `https://w3id.org/agentprov/` before the first deposit (OM-14; **U-02**).

Closed by the rulings: C-O1 (the Inspect `.eval` importer is in v0.1, AD-06); the upstream file set (the import
uses the 18,241 pinned blobs incl. 7 Mixtral, R-32); the corpus-level validation report (`validation/` is
required in the layout and the paper reads it, AD-20, R-64).

## O.7 Artefact reporting (DECISIONS D-12; D.15)

The paper reports artefacts per source from `agentprov stats --artefacts` and `docs/reports/artefacts/`, through the
O.3.5 pipeline (values → macros). Each source table lists every catalogue entry with `manuscript = true`, giving its
count, proportion, cause and handling class. Totals of `artefact.unclassified.*` are always reported, so the reader
sees what is not yet understood. The artefact catalogue's version is cited with the corpus version.

