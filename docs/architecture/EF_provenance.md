Revision: 2026-10-07 r2 — review resolutions and Addendum B applied.

# E. Provenance model and F. Evidence model (`agentprov-prov/0.1`)

Section of the AgentPROV v0.1 architecture and implementation specification.
Date: 2026-10-07. Status: revised after review (r2).
Binding brief, in order of precedence: `investigation/DECISIONS.md` Addendum B (architect rulings), Addendum A, then
D0–D12; `spec/review/RESOLUTIONS.md` §3 (canonical naming table) and §4.5 (edit list for this section). This section
specifies D7 (provenance engine and specification `agentprov-prov/0.1`). It also specifies the evidence semantics that
D2 (the AER envelope fields `ev`, `by`, `evf`, `rule`, `unk`, `after`), D6 (SEM) and D8 (validation tiers 4 and 6)
rely on. Per MN M.0 this section owns `src/agentprov/prov/`, `src/agentprov/vocab/` and the `apv:` vocabulary; the
AER ("AgentPROV Execution Record", `aer/0.1`) contract is C.3 and `schemas/aer-0.1.schema.json` (owner C), which this
section cites and does not restate.

The keywords MUST, MUST NOT, SHOULD, SHOULD NOT and MAY are used as in RFC 2119 and RFC 8174. Paragraphs
headed *Rationale* or *Evidence* are informative.

**Citations.**
- Investigation reports are cited by path and section, for example `[audit/provenance.md §4.1]`,
  `[landscape/prov_semantics.md §8.2]`.
- Baseline code is cited as `build_prov.py:458`, meaning
  `AgentDojo-PROV-framework/agentdojo_prov/build_prov.py` line 458 at commit `579a908354b93361efe0905ffb7623256aa96a06`.
  `docs/capture_spec.md §n` means the baseline repository's normative capture specification at the same commit.
- New measurements made for this section are cited as `[EF_evidence/<file>]`. The scripts and their outputs
  are in `investigation/spec/EF_evidence/`. They use only the standard library and only read the baseline
  corpora; nothing in the baseline repository was modified.

**Status of `landscape/prov_semantics.md` §13.** The completion review (§13, from line 1074) exists, and Addendum A5
makes its corrections binding. They are applied throughout this section: E1 (requests are `hadMember` of a
`prov:Collection` message), E2 (in-request transforms qualify the usage; defences are their own activity), E3
(mention cardinality), E4 (declared sender, not attribution), E5 (checker inputs), E6 (re-run trigger is `content =
null`), E12 (OTel filtering and stateful chains), E13 (primary source), G1 (`llm → llm` communication), G2
(passed-back reasoning) and G4 (the compat graph is two entities). §0–§12 are used where §13 does not correct them.

**Changes after review (2026-10-07).** Applied: R-01, R-02, R-03, R-04, R-05, R-06, R-07, R-08, R-09, R-10, R-12,
R-16, R-17, R-18, R-20, R-21, R-22, R-23, R-25, R-28, R-30, R-31, R-32, R-33, R-34, R-35, R-36, R-37, R-38, R-45,
R-48, R-50, R-53, R-54, R-55, R-56, R-58, R-59, R-63; AD-02, AD-03, AD-04, AD-05, AD-06, AD-07, AD-09, AD-11, AD-12,
AD-14, AD-18, AD-19; and, as ruled in Addendum B, AD-10 (minimal `stats` and `render` kept), AD-15 (generic
`activity` and `artefact` kinds with rules G-ACT, G-USE, G-GEN and G-ASSOC) and AD-16 (`requires-python =
">=3.14"`). All challenge boxes are resolved (Appendix B). Superseded first-draft names appear below
only where a ruling is recorded.

---

## Summary of positions taken

1. **A pure function.** The engine is `AER × SEM* × agentprov-prov/0.1 × options → PROV document`. The core
   bundle is a function of the AER alone (E.0, E.3). Evidence classes are read from the AER, where the adapter fixed
   them at map time (static model, AD-05); the engine never reads source profiles or assumption statuses to classify.
2. **Evidence on everything.** Every node and every identified relation carries:
   - its evidence class;
   - the engine rule that emitted it;
   - pointers into the AER;
   - the attesting parties;
   - the assumptions it relies on;
   - its premises, where it has any.

   The class of a statement is the weakest class among its premises and the existence classes of its endpoints
   (E.1.5, F.1.4).
3. **`wasInformedBy` is exactly the Inference 6 closure over named activities** (AD-19(c); E.1.6).
   - It is never more: no edge comes from order.
   - It is never less than entailed for named activities: no communication that PROV entails between two named
     activities is left unasserted. In v2.3 that gap was 26,645 released and 23,449 converted edges: the
     26,645 / 23,449 R6 taint-only `used` edges each entail, via Inference 6, exactly one `wasInformedBy` the builder
     never asserts (entailed 99,278 / 91,661 minus asserted 72,633 / 68,212)
     [audit/provenance_evidence/evidence_stats.json; landscape/prov_semantics_evidence/inference6_scan.json].
4. **Requests are members; transforms qualify usages.** Tool-call requests are `hadMember` of their assistant message,
   which is typed `prov:Collection` (A5, AD-19(a)). Transforms applied while a request is built are per-input
   qualifiers of the usage (`apv:sentTransform`, R-06); a defence rewrite is a separate decision activity (A5).
5. **Security interpretation stays in assessment bundles; configuration ground truth stays in the core.** Integrity,
   roles, payload containment, exposure, taint and outcome polarity appear only in assessment bundles, as
   `prov:mentionOf` entities (entities only) and `apv:Assessment` entities. Attack, target and defence ids, payload
   fixtures, attacker attribution and outcome values are configuration provenance and stay in the core (AD-11); core
   bundles are not a blind input for detectors (NC-PROV-01).
6. **A generic extension envelope.** The generic AER kinds `activity` and `artefact` (Addendum B, AD-15) map through
   the generic rules G-ACT, G-USE, G-GEN and G-ASSOC, which take part in the Inference 6 closure. Specialised kinds
   remain preferred whenever they fit.
7. **The compatibility profile reads the AER alone.** `adprov-v2.3-compat` is a verbatim port of the baseline
   builder, run on a transcript/v1 view regenerated from the AER alone through a deterministic view. JCS member order
   and integral-float form are restored from the sparse `ext.lex` hints (AD-02); the view reads nothing from raw.
8. **Outputs.** Bundled canonical PROV-JSON is stored and hashed. TriG is produced on demand. The flattened core and
   per-execution lineage documents are deferred (AD-10).
9. **Challenges.** The four challenge boxes raised by the first draft (1, 2, 3 and 3a) are resolved; Appendix B
   records the rulings.

---

## E.0 Scope, inputs, outputs and module layout

### E.0.1 The engine as a function

1. The provenance engine MUST implement `derive(aer, sems, spec, options) → ProvDerivation`, where:
   - `aer` is one sealed AER execution (`<ex>.aer.jsonl`, D2; contract C.3);
   - `sems` is zero or more SEM documents whose targets are ids in that AER (D6; contract C.14);
   - `spec` is the `agentprov-prov/0.1` specification together with its machine-readable rule catalogue;
   - `options` is the option set of the profile (E.0.3).

   The adapter rule catalogues and the source profile named in the AER header (`rules {<ns>: <int>}`,
   `profile {id, version, sha256}`) are read from package resources at exactly those versions (AD-14, AD-18). They
   are a function of the AER header and are used only to list `apv:assumption` and `apv:adapterAssumption` values
   and capture-profile capabilities; they never change a class.
2. The engine MUST NOT read any of the following:
   - raw artefacts;
   - the network;
   - the clock;
   - environment variables;
   - random sources;
   - any benchmark package (the D10 import boundary).

   Raw evidence is reached only through AER `src` locators, and only the validators resolve them (D8 tier 4,
   "evidence linkage"). The compatibility view reads nothing from raw (AD-02; E.8.2).
3. The core bundle MUST be a function of the AER, `spec` and `options` only. SEM documents affect only
   assessment bundles.
   *Rationale.* The provenance of an execution must not change when a benchmark policy changes. SEM-dependent
   interpretations therefore stay out of the core; configuration ground truth (attack, target and defence ids,
   payload fixtures, attacker attribution, outcome values) is genuine configuration provenance and is in the core
   (AD-11, R-23) [audit/provenance.md §7.1.4, §16 item 3].
4. The engine MUST refuse an AER that has not passed the AER validator (D8 tier 2), and a SEM document that has
   not passed the SEM validator (tier 3).
5. The engine MUST be total. Malformed or unexpected input produces a typed failure, never an uncaught
   exception [audit/validation.md §8 item 2]. Every AER record kind of C.3, including `activity` and `artefact`, and
   every enum value of C.3, including the `other` escapes, has a rule or an explicit no-node entry in E.1.3.

### E.0.2 Outputs

Paths are relative to the corpus root. `<ss>` is the shard `sha256(ex)[:2]` (HL; RESOLUTIONS §3.6).

| File | Content | Stored and hashed? |
|---|---|---|
| `prov/agentprov-prov-0.1/<ss>/<ex>.prov.json` | Canonical bundled PROV-JSON: top-level conversion provenance plus the bundles (E.3) | yes; JCS bytes (E.5.3) |
| `<ex>.prov.trig` | PROV-O TriG: the default graph is the top level, with one named graph per bundle, plus the unqualified-triple layer (E.5.4) | no: produced on demand by `agentprov derive --trig DIR`, outside the sealed tree (AD-10 row 3). The PROV-JSON → PROV-O → PROV-JSON round trip stays a validation check (E.5.5) |
| `prov/adprov-v2.3-compat/<ss>/<ex>.prov.json` | Compatibility graph (E.8), flagged `apv:status apv:RegressionOracle` with profile `adprov-v2.3-compat` in the corpus manifest and index (R-55) | yes; byte gate |
| `<ex>.prov-core.json` | Flattened core (E.3.6) | deferred (AD-10 row 4) |
| `lineage/<ss>/<ex>.lineage.json` | Per-execution lineage document (E.3.5) | deferred (AD-10 row 5) |

### E.0.3 Module layout and signatures

MN M.1.2 (amended by RESOLUTIONS §3.2) is authoritative for names. The layout below is what this section requires.

```
src/agentprov/prov/
  __init__.py                 # derive, ProvOptions, ProvDerivation, AGENTPROV_PROV_0_1
  engine.py                   # rule driver, bundle routing, Inference-6 closure (aprov.comm@1, E.1.6)
  evidence.py                 # EvidenceClass, weakest(), cls(), existence()
  specs.py                    # spec registry: agentprov-prov/0.1 and the frozen adprov-v2.3-compat
  iri.py                      # local names, statement ids, derivation keys (E.4.2)
  vocab.py                    # apv term constants generated from vocab/apv-0.2.ttl
  rules/nodes.py              # aprov.n_* node rules and G-ACT (E.1.3)
  rules/edges.py              # aprov.* edge rules, including G-USE, G-GEN and G-ASSOC (E.1.4)
  rules/assess.py             # aprov.a_* assessment rules (E.7)
  rules/top.py                # aprov.t_* conversion provenance (E.3.3)
  serialise/provjson.py       # canonical PROV-JSON writer (JCS)
  serialise/trig.py           # canonical TriG writer + unqualified layer (on demand)
  serialise/time.py           # the E.5.3 item 7 time predicate, tied to the pinned prov version
  catalogue/agentprov-prov-0.1.toml   # the aprov rule catalogue: the prov:Plan of the derive activity
  compat/adprov_v2_3/         # verbatim port (5 files, AST-equal) + PORT_MANIFEST.json (E.8.1)
  compat/semdiff-map.toml     # machine-readable semantic diff (E.8.4)
  _ir.py                      # internal statement representation (E.10 item 4)
src/agentprov/views/transcript_v1.py    # render(aer) -> dict; render_converted(aer) -> dict; serialise(dict) -> bytes
src/agentprov/vocab/apv-0.2.ttl         # the apv ontology, owl:versionInfo "0.2.0" (E.4); copy in docs/ns/apv-0.2.ttl
src/agentprov/vocab/apv-adprov-map-0.1.ttl
src/agentprov/validate/shapes/          # SHACL shapes for the profile rules (E.4.6 item 3)
```

```python
class EvidenceClass(enum.IntEnum):          # ordered: weaker < stronger
    INFERRED = 0
    DERIVED = 1
    OBSERVED = 2

def weakest(*classes: EvidenceClass) -> EvidenceClass: ...
def cls(record: Mapping[str, Any], pointer: str) -> EvidenceClass: ...      # E.0.4; longest-prefix evf (C.6.3)
def existence(record: Mapping[str, Any]) -> EvidenceClass: ...              # the record's ev (C.6.3, R-22)

@dataclass(frozen=True)
class ProvOptions:
    context_encoding: Literal["members"] = "members"   # E.6; "collection" is deferred (AD-10 row 14)
    emit_content: bool = False          # put message/part text in PROV (default: digests only)

@dataclass(frozen=True)
class ProvDerivation:
    prov_json: bytes                    # canonical JCS bytes (stored)
    bundles: tuple["BundleInfo", ...]   # iri, kind, method set or profile, derivation key, digest, statement counts by class
    digests: Mapping[str, str]          # "prov_json" -> "sha256:<hex>"
    report: "DerivationReport"          # rules fired; statements per (bundle, class, rule); statuses; skipped refs;
                                        # disclosed gaps (read by `agentprov stats`, AD-10 as ruled in Addendum B)

def derive(aer: "AerExecution", sems: Sequence["SemDocument"] = (), *,
           spec: "ProvSpec" = AGENTPROV_PROV_0_1, options: ProvOptions = ProvOptions()) -> ProvDerivation: ...

# agentprov/prov/serialise/trig.py: on demand only (`agentprov derive --trig DIR`); never stored in a corpus
def to_trig(prov_json: bytes) -> bytes: ...
```

The options MUST be recorded in the document as the JCS string `apv:profileOptions` on the derive activity
(E.3.3). They MUST also enter every bundle's derivation key (E.4.2).

Engine-run inference methods (`ProvOptions.engine_methods` in the first draft) and the flattened-core option are
deferred with E.1.7 and E.3.6 (AD-10 rows 4 and 15).

### E.0.4 Notation

- **`L(id)`** is the PROV local name of an AER local id (E.1.2). `x:` is the per-execution instance prefix.
- **`existence(R)`** (written `ex(R)`) is the record's `ev`: its *existence* class, which is also the default for
  its fields (C.6.3, R-22). Adapters do not lower `ev` because one field is weaker; they tag that field in `evf`.
- **`cls(R, p)`** is the evidence class of the field at RFC 6901 pointer `p` of AER record `R`. It is
  `R.evf[q]` for the longest key `q` in `R.evf` that equals `p` or is a token-boundary prefix of `p`; when there
  is no such key, it is `R.ev`. This longest-prefix reading is normative in C.6.3 (AD-03; EF Challenge 2(d)).
  An `evf` value `O:<party>` is OBSERVED with attesting party `<party>`.
- **`weakest(...)`** is the minimum under the order INFERRED < DERIVED < OBSERVED.
- **Statements.** A *statement* is a PROV element declaration or relation emitted by one rule. Its evidence
  attributes are those of E.1.5.

---

## E.1 PROV mapping of the AER

### E.1.1 Activity and entity boundaries (normative definitions)

The rules below depend on where each activity starts and ends. Those boundaries are fixed here.

1. **`apv:ModelInvocation`** (from a `model_call` record whose `status` is `kept`, `discarded` or `error`).
   - It begins when the harness component that calls the model starts building the request from its message
     list. It ends when the response has been received and turned into the recorded output messages, or when
     the call has failed.
   - Transformations that the calling component applies while building the request happen *inside* the
     invocation. Examples:
     - the developer→system role rewrite (`runtime.py:240-243`);
     - reasoning pass-back (`runtime.py:244-259`);
     - substitution of the error string for an errored tool result in agentdojo's OpenAI message converter
       [landscape/prov_semantics.md §4.1 item 1; §13 E2];
     - truncation performed while the request is built (`truncation` applies only here).
   - The invocation therefore *uses the recorded message*. The transformation is declared per input on
     `model_call.input[]` as `{id, sent: [Transform], sent_sha256?}` (C.3; R-06) and is stated as a qualifier of that
     usage (`apv:sentTransform`, `apv:asSentSha256`), never as a separate "as-sent" entity. The wire request blob
     (`model_call.request`) remains the OBSERVED evidence of the sent form.
   - A `model_call` with `status` = `cached` is an `apv:CacheRead` activity, not an invocation: it was served from a
     cache without inference, so it neither uses a model nor is associated with a provider (R-07; PROV-11(a)).
2. **Steps performed by a separate pipeline element are not inside the invocation.** An example is AgentDojo's
   prompt-injection detector, which overwrites tool content in place [landscape/prov_semantics.md §4.1]. Such
   a step is a `decision` record and a separate `apv:Decision` activity (A5; rule `aprov.decision@1`). A defence is
   never a sent transform.
3. **`apv:ToolExecution`** (from a `tool_execution` record; `status` ∈ `ok`, `error`, `invalid`).
   - It begins when the runtime dispatches the request. It ends when the recorded result exists.
   - The harness's rendering of the return value is inside it. For AgentDojo this is `tool_result_to_str`
     with `yaml.safe_dump` [audit/legacy_replay.md §2.2].
   - `invalid` means the runtime rejected the call (unknown tool, empty name, argument validation). The runtime
     acted, so this is still a tool execution, with `apv:execStatus apv:Invalid`, and it generates the error message
     the model was sent (R-21).
   - A tool execution consumes only its request and the environment state it read
     [landscape/prov_semantics.md §4.1 item 2].
   - A call denied by a defence or approver is a `decision` only; it has no `tool_execution` (C.5.5; RF-3).
4. **`apv:Decision`** (from a `decision` record) is the evaluation made by a defence, guard, approver or
   reviewer, together with any replacement content it produced.
5. **Scope activities** (run, pass, agent invocation, sub-agent invocation, other) are containers.
   - Containment of activities is the attribute `apv:partOf`, never a PROV relation. PROV has no activity
     containment [landscape/prov_semantics.md §8.2 R-PART].
   - Tool-call request parts are *members* of their assistant message: `hadMember(message, request)`, with the
     message typed `prov:Collection` (A5; §13 E1; AD-19(a)). Usage of the message does not entail usage of its
     members (§13 G1; NE-8).
6. **Entities are fixed as recorded in the AER.** Their content digest is computed over the recorded value.
   - Content that the source discarded is a *distinct* entity carrying `apv:contentStatus apv:Lost`; content
     destroyed in place by a defence or harness step (in-place redaction by the PI detector, AgentDyn detectors,
     DRIFT isolation) is a distinct entity carrying `apv:contentStatus apv:Overwritten` (AER reason `overwritten`,
     R-08) [landscape/prov_semantics.md §9.2, §9.3 item 3; §13 E2].
   - Such an entity is never dropped, and its content is never invented.
7. **Generic activities and artefacts** (Addendum B, AD-15).
   - An `activity` record is one occurrence that no specialised kind represents: a code planner or router step,
     harness-side retrieval, a memory read or write, code execution outside a tool call, a browser action. It is an
     `apv:GenericActivity` whose boundaries are those the adapter's catalogue entry for its `type` (`<ns>:<name>`)
     states. It consumes exactly its declared `inputs`.
   - An `artefact` record is content produced by an activity, a model call or a tool execution that is not a
     message, part, fixture or state (a memory entry, a plan object, a screenshot saved outside the conversation).
   - Specialised kinds are preferred whenever they fit. An adapter MUST NOT use `activity` for an occurrence an
     existing kind represents (a model call, a tool dispatch, a decision, a checker run), nor `artefact` for a
     message, part or fixture; the engine refuses such records (NE-21).

### E.1.2 Local names (normative; full IRIs in E.4.2)

- **AER ids.** Local ids follow C.4.2: `^[a-z][a-z0-9_]{0,31}$`; part ids are `<local id>#<k>`. `L(id)` is the AER
  local id with `#` replaced by `-`. For example `m2#1` becomes `m2-1` and `mc0` stays `mc0`. The mapping is
  injective because local ids never contain `-` (AD-04; EF Challenge 2(e) is rejected in favour of this argument).
  - Covered id forms: `m<n>`, `m<n>#<k>`, `mc<n>`, `te<n>`, `dc<n>`, `st<n>`, `fx<n>`, `j<n>`, `run`, `att<n>`,
    `thr<n>`, `sc<n>`, `p<n>`, `exec`, `seal`, the actor ids (`agent`, `user`, `env`, `bench`, `harness`, `att`,
    `def<n>` or `def_<name>`, `judge<n>`), and the C.4.2 prefixes of `activity` and `artefact` records.
- **Derived nodes** are `L(id).<q>`, with `q` drawn from the closed set:
  - `model` (model entity, per actor or per call);
  - `svc` (model-service agent);
  - `check` (synthetic checker run);
  - `rule` (harness-rule evaluation);
  - `out` (the pre-decision output of a tool execution; R-21's `x:<te>-out`, written with the derived-node
    separator `.`);
  - `pre` (pre-decision content of a part);
  - `before` and `after` (state snapshots);
  - `ctx` (context window; collection mode, deferred);
  - `gap-<n>`;
  - `mn-<h12>` (mention).
- **Reserved names.** `capture-profile`, `exec`, `as` and `assess.<slug>` are reserved local names; an AER MUST NOT
  use `as` as a local id.
- **Statement ids** are `<rule-name>.<h16>`, for example `use_context.k3m9q2a7b4c5d6e7`. They are defined in
  E.4.2.
- **No collisions.** AER ids contain neither `.` nor `-`. Node names `L(id)` therefore never contain `.`, part names
  carry `-` followed by digits only, derived qualifiers come from a closed set none of which is a 16-character base32
  string, and statement names end in a 16-character base32 hash. Node, derived-node, statement and assessment
  (`as-<h16>`) names cannot collide.

### E.1.3 Node rules

Column notes:
- "Class" is the class of the node's *existence*: `ex(R)` unless stated.
- Attributes whose own class differs from it follow the attribute evidence rule of E.1.5 (rule 5).
- "core or inf" means the core bundle when the class is OBSERVED or DERIVED, and otherwise the inference bundle
  of the method set (E.1.5 rule 4).
- "Required AER evidence" pointers MUST exist in `schemas/aer-0.1.schema.json`; a CI check enforces this (R-02).

| Rule id | AER input (kind, condition) | PROV node(s) | Types (`prov:type`) | Attributes (AER pointer → property) | Class | Bundle |
|---|---|---|---|---|---|---|
| `aprov.n_header@1` | `execution` (always) | entity `x:exec` | `apv:ExecutionDescription` | `/ex`→`apv:executionId`; `/mode`→`apv:mode`; `/unit`→`apv:executionUnit` (`agent_execution`, `outcome_only`, `scenario`; R-28); `/task/benchmark`→`apv:benchmark`; `/task/environment`→`apv:environment`; `/task/task_id`→`apv:taskId`; `/task/attack_id`→`apv:attackId`; `/task/attack_target_id`→`apv:attackTargetId`; `/task/defense_id`→`apv:defenceId` (configuration provenance, AD-11); `/instrumentation[*]/id`→`apv:instrumentation` | `ex(exec)` | core |
| `aprov.n_actor@1` | `actor` | agent `x:L(a)` | by `kind`, plus role classes from `role` (E.4.3 table); `kind` = `other` → `prov:Agent` + `apv:subtype` | `/name`→`apv:name`; `/role`→`apv:actorRole`; `/subtype`→`apv:subtype`; `/version`→`apv:version` | `ex(a)` (existence; a weaker model identity is tagged `evf {"/model": "I"}`, not by lowering `ev`) | core or inf |
| `aprov.n_model@1` | `actor` with `/model`; `model_call` with `/served_model` | entity `x:L(a).model`; entity `x:L(mc).model` iff `/served_model` is present; agent `x:L(a).svc` iff `/model/served` or `/model/provider` is present | `apv:Model`; `prov:SoftwareAgent`+`apv:ModelService` | `/model/requested`→`apv:requestedModel`; `/model/served`→`apv:servedModel`; `/model/provider`→`apv:provider`; per call: `/served_model`→`apv:servedModel` | model entity: DERIVED (definitional: every invocation is served by some model), capped by `ex(a)` or `ex(mc)`; service agent: class of the identifying field | core or inf |
| `aprov.n_scope@1` | `scope` with `kind` in `run`, `attempt`, `agent_invocation`, `subagent`, `other` | activity `x:L(s)` | `apv:Run`, `apv:Pass`, `apv:AgentInvocation`, `apv:SubagentInvocation`; `other` → `apv:Step` + `apv:subtype` | `/t/start`,`/t/end`→`prov:startTime`,`prov:endTime` (E.5.3 item 7); `/t/dur_s`→`apv:durationSeconds`; `/index`→`apv:index`; `/scored`→`apv:scored`; `/status`→`apv:scopeStatus`; `/parent`→`apv:partOf` | `ex(s)` | core or inf |
| (no rule) | `scope` with `kind` = `thread` | no node; member messages carry `apv:thread` | — | — | — | — |
| `aprov.n_message@2` (D-621; `@1`, which stated no scope, stays for the documents that cite it) | `message` | entity `x:L(m)` | `apv:Message` + role class (`apv:SystemMessage`, `apv:UserMessage`, `apv:AssistantMessage`, `apv:ToolMessage`, `apv:DeveloperMessage`, `apv:OtherRoleMessage`); additionally `prov:Collection` iff `m` has at least one `tool_call` part | `/role`→type (+`apv:messageRole` string for other roles); `/scope`→`apv:partOf` (non-thread) or `apv:thread`; `apv:contentSha256` = sha256 of the JCS bytes of `/parts`; `apv:partCount` | `ex(m)` | core or inf |
| `aprov.n_part@1` | each `message.parts[k]` | entity `x:L(m)-k` | `apv:MessagePart` + part class from `parts[k].t`: `apv:TextPart`, `apv:ReasoningPart`, `apv:ToolCallRequest`, `apv:ToolResult`, `apv:BlobPart`, `apv:FilePart`, `apv:UriPart`, `apv:RefusalPart`, `apv:OtherPart` | `apv:partIndex` k; text-bearing parts: `apv:contentSha256` = sha256 of the UTF-8 bytes of `text`, `apv:contentLength` in Unicode scalar values; `text: null` → `apv:contentStatus apv:RecordedNull`; any other asserted `null` → `apv:<p>Status apv:RecordedNull` in place of the data property `<p>` (E.10 item 5); tool_call: `/name`→`apv:toolName`, `/args`→`apv:args` (JCS string), `/provider_call_id`→`apv:providerCallId`, `/args_raw`→`apv:argsRawSha256`; tool_result: `/error`→`apv:error`, `/name`→`apv:toolName`; `other`: `/type`→`apv:subtype`; `emit_content` → `apv:text`. Non-request parts also carry `apv:partOf x:L(m)` (`aprov.part_of@1`) | `weakest(ex(m), cls(m,/parts/k))` | core or inf |
| (part of `aprov.n_part@1`) | `tool_call` part with no `tool_execution`: a `decision` with `verdict` = `deny` has the part as subject, or the seal lists it under `unexecuted_tool_call` | no activity; the request part gets `apv:dispatchStatus` `apv:Denied` or `apv:NotDispatched` | — | — | class of the decision or of the seal issue rule | core or inf |
| `aprov.n_model_call@1` | `model_call` with `status` `kept`, `discarded` or `error` | activity `x:L(mc)` | `apv:ModelInvocation` | `/status`→`apv:callStatus` (`apv:Kept`, `apv:Discarded`, `apv:Error`); `/role`→`apv:callRole`; `/reason`→`apv:reason`; `/retry_of`→`apv:retryOf` (QName; retries are expressed only this way); `/t`→times; `/finish_reason`→`apv:finishReason`; `/usage`→`apv:usage` (JCS string); `/params/configured`,`/params/transmitted`→`apv:paramsConfigured`,`apv:paramsTransmitted` (JCS strings); `/response_id`→`apv:responseId`; `/request`,`/response`→`apv:requestBlob`,`apv:responseBlob` (`sha256:` refs). `error`: an invocation with no output, no model usage and no provider association (R-07) | `ex(mc)` | core or inf |
| (part of `aprov.n_model_call@1`) | `model_call` with `status` = `cached` | activity `x:L(mc)` | `apv:CacheRead` | as above, with `apv:callStatus apv:Cached` | `ex(mc)` | core or inf |
| (part of `aprov.n_model_call@1`; covers prov_semantics N-LLM-LOST) | `model_call` emitted under C.7.4 (lost model calls: `unk` on `/input`, `/t` and `/status`, in a non-scored attempt) | the same activity, with `apv:outputStatus apv:Lost`, and no generation | — | statuses from `aprov.status@1` | `ex(mc)` | core or inf |
| `aprov.n_tool_execution@1` | `tool_execution` (`status` `ok`, `error` or `invalid`) | activity `x:L(te)` | `apv:ToolExecution` | `/name`→`apv:toolName`; `/status`→`apv:execStatus` (`apv:Ok`, `apv:Error`, `apv:Invalid`); `/args_effective`→`apv:argsEffective` (JCS; only when it differs from the request's `args` or those are unknown); `/exception`→`apv:exception` (JCS string); `/t`→times | `ex(te)` | core or inf |
| `aprov.n_decision@1` | `decision` | activity `x:L(dc)` | `apv:Decision` | `/verdict`→`apv:verdict` (`other` → `apv:VerdictOther` + `apv:subtype`); `/reason`→`apv:reason` | `ex(dc)` (INFERRED for decisions recognised from patterns, such as ROPE denials and PI-detector sentinels [landscape/trace_formats.md §6.6]) | core or inf |
| `aprov.n_state@1` | `state_change` with `/before_sha256` or `/after_sha256` | entities `x:L(sc).before` (unless carried over, `aprov.env_pass@1`) and `x:L(sc).after` iff `/after_sha256` ≠ `/before_sha256` | by `target`: `environment`→`apv:EnvironmentState`; `agent_store`→`apv:StoreState`; `sandbox`→`apv:SandboxState`; `other`→`apv:State` + `apv:subtype` | `apv:stateSha256`; `/patch` or `/diff/value`→`apv:patchSha256`; `/diff/truncated`→`apv:truncated` | `ex(sc)` | core or inf |
| (part of `aprov.n_state@1`) | `state_change` with `/patch` and no digests | entity `x:L(sc).after` only, through `aprov.state_patch@1` | as above | `apv:patchSha256` | `ex(sc)` | core or inf |
| `aprov.n_fixture@1` | `fixture` | entity `x:L(fx)` | `apv:Fixture` + kind class: `injection_payload`→`apv:InjectionPayload`; `environment_seed`→`apv:EnvironmentSeed`; `attack_plan`→`apv:AttackPlan` and `prov:Plan`; `task_prompt`→`apv:TaskPrompt`; `system_prompt`→`apv:SystemPrompt`; `tool_definitions`→`apv:ToolDefinitions`; `ground_truth`→`apv:GroundTruth`; `other`→`apv:subtype` only | `/vector`→`apv:vector`; `apv:contentSha256` | `ex(fx)` | core or inf |
| `aprov.n_judgement@1` | `judgement` | entity `x:L(j)`; plus the activity the origin requires (`aprov.outcome@1`) | `apv:Outcome` | `/name`→`apv:outcomeName`; `/value`→`apv:outcomeValue` (typed literal); `/origin`→`apv:outcomeOrigin` (`apv:OriginChecker`, `apv:OriginHarnessDefault`, `apv:OriginHarnessRule`, `apv:OriginRecomputed`). No polarity or meaning: that is a SEM `outcome` annotation (E.7.3) | `ex(j)` | core or inf |
| `aprov.n_artefact@1` | `artefact` (generic kind, AD-15) | entity `x:L(af)` | `apv:GenericArtefact` | `/type`→`apv:artefactType` (`<ns>:<name>`); `/sha256` (or the `content_ref` blob digest, or sha256 of the JCS bytes of `content`)→`apv:contentSha256`; `/media`→`apv:mediaType` | `ex(af)` | core or inf |
| `aprov.g_act@1` [G-ACT] | `activity` (generic kind, AD-15) | activity `x:L(ac)` | `apv:GenericActivity` | `/type`→`apv:activityType` (`<ns>:<name>`); `/label`→`prov:label`; `/status`→`apv:activityStatus`; `/scope`→`apv:partOf`; `/t`→times | `ex(ac)` | core or inf |
| `aprov.n_capture_profile@1` | the source profile at the version and digest in `execution.profile` (package resource, AD-14), plus `seal.accounting` and `seal.issues` | entity `x:capture-profile` | `apv:CaptureProfile` | `apv:provides`, `apv:notProvided`, `apv:notObservable` (capability individuals, E.4.5); `apv:accounting`; `apv:issue` (issue codes) | DERIVED | core |
| `aprov.n_gap@1` | an `unk` pointer of an emitted node that has no fixed status property (E.4.5) | entity `x:L(r).gap-<n>` | `apv:Gap` | `apv:about`, `apv:property` (the pointer), `apv:status`, `apv:sourcePointer` | `weakest(ex(r), DERIVED)` | with its node |
| (top level only) | `seal` | no core node; mapped to the AER entity at top level (E.3.3) | — | — | — | top level |

### E.1.4 Edge rules

Each rule below adapts a rule of [landscape/prov_semantics.md §8.2], as corrected by §13.5 (code in brackets), to the
AER field names of C.3.

How to read the columns:
- "Class and condition" gives the *ceiling* and the premises; the actual class follows E.1.5. Every class formula
  also includes the existence class of every endpoint (`ex(·)`; R-22), even where it is not repeated below.
- "PROV checks" names the PROV-CONSTRAINTS constraints (C) and inferences (Inf.) that the statement makes
  instantiable. The validation section checks them per bundle, and on the union core ∪ inference bundle as an
  application-level view [landscape/prov_semantics.md §7.2 rule 5; audit/validation.md §3.7].
- No relation carries a time (E.5.3 item 7), but every relation names its events, so the event-ordering constraints
  are instantiable from the relations alone (A3 PI-04; examination 2 b1). Tier 4 checks them (`pv.constraints.ordering`:
  the event graph of C33, C36-C38, C40, C42 strict, C44 and C46 with Inferences 9 and 11, failing on a strongly
  connected component that holds a strict edge), with C51 (`pv.constraints.derivation_parts`), C26
  (`pv.constraints.unique_start`) and the profile's cycle lints (`pv.constraints.cycles`), per container and on the
  application views of every inference and assessment bundle (regeneration-batch item 10). Activity *times* stay §6.2
  "MAY flag" diagnostics (A5).

| Rule id [code] | PROV statement | Required AER evidence | Class and condition | Bundle | PROV checks |
|---|---|---|---|---|---|
| `aprov.gen_message@1` [R-GEN-RESP; R-GEN-OUT for tool messages] | `wasGeneratedBy(x:L(m), x:L(g))` | `message/generated_by` = `g`, where `g` is a `model_call`, `tool_execution`, `decision` (or another record kind with an activity node that C.3 admits there) | `weakest(cls(m,/generated_by), ex(g), ex(m))`; OBSERVED only when all are OBSERVED (for example, a capture binds the response to the call) | core or inf | C24 (unique per (e,a)); C39 profile rule: at most one generating activity per entity per bundle; C50 |
| `aprov.gen_part@1` [R-GEN-REQ, generation half; §13 E1] | `wasGeneratedBy(x:L(m)-k, x:L(g))` for every part `k` of `m` except `tool_result` parts | as `aprov.gen_message@1` | as `aprov.gen_message@1` | core or inf | C24, C50 |
| `aprov.gen_result@1` [R-GEN-OUT] | for a `tool_result` part `P` of message `m` with `m.generated_by` = `g`: (i) `g` a `tool_execution` `te`: `wasGeneratedBy(P, x:L(te))`; (ii) `g` a `decision` `dc` whose `subject` is `te` or `P`: `wasGeneratedBy(P, x:L(dc))` and `wasGeneratedBy(S, x:L(te))`, where `S` = `x:L(te).out` (subject `te`) or `x:L(P).pre` (subject `P`) | `message/generated_by`; `P/responds_to` = `te/call` (consistency check); in case (ii), `decision/subject` | `weakest(cls(m,/generated_by), ex(te), ex(P))`, and in case (ii) also `ex(dc)` and `cls(dc,/subject)`: the decision's class is included wherever the target depends on it (R-22) | core or inf | C24, C34 (events), C50 |
| `aprov.member_request@1` [R-GEN-REQ, membership half; §13 E1] | `hadMember(x:L(m), x:L(m)-k)` for every `tool_call` part `k` of `m`; `m` is typed `prov:Collection` (E.1.3) | `message/parts/k/t` = `tool_call` | the class of the part's existence; the relation carries no attributes (E.5.1 item 3) and is placed in the bundle of the part. G1 caveat: `used(a, m)` does not entail `used(a, m-k)` (NE-8) | core or inf | C50 (typing), C56 |
| `aprov.use_context@1` [R-USE-CTX; §13 E2, E12, G2] (members mode, E.6) | for each item `i` of `model_call.input` (an `Id<message>`, or `{id, sent, sent_sha256?}`): `used(x:L(mc), x:L(m_i), [prov:role apv:ContextMessage, apv:contextIndex i, apv:sentTransform …, apv:asSentSha256 …])` | `model_call/input` not in `unk`; every `m_i` resolves backward (for a `cached` call, the usage is the cache lookup's use of the request; no model usage follows) | `weakest(cls(mc,/input/i), ex(mc), ex(m_i))`. **OBSERVED** iff the wire request was captured with recorded context positions (`llm.request` `input_at`, C.13; R-16) or the source records the per-call as-sent input (Inspect `ModelEvent.input` with `ModelEvent.call`; an OTel span only under `apv:InstrumentationUntruncated` established by an OBSERVED premise, §13 E12). **DERIVED** under a named alignment rule (live capture without `input_at`, with an accounting check that fails on misalignment) or under a catalogue rule whose assumption (normally `apv:FullContextResend`) is verified for the identical framework identity; for stateful APIs (`previous_response` chains) the adapter resolves the chain under the provider's documented semantics (§13 E12). **Otherwise INFERRED**, including the released AgentDojo-PROV v1 corpus (`adprov.context_is_prefix@1`, AD-05) unless the user supplies a digest-pinned generation-time harness (U-01). Not emitted when `/input` is unknown: `apv:contextStatus` is set instead (this includes reasoning-returning models in the release, whose passed-back reasoning is not held: `not_captured` or `ambiguous`, §13 G2). A transform tagged weaker than the usage goes to an `apv:SentTransformed` assessment (E.1.5 rule 5) | core (O, D) or inf (I) | C33, C37 (events); C50; supplies Inf. 6 premises |
| `aprov.use_model@1` | `used(x:L(mc), M, [prov:role apv:ModelInput])`, with `M` = `x:L(mc).model` when `/served_model` is present, else `x:L(actor).model` | `model_call/actor` resolves to an actor with `/model`, or `model_call/served_model`; `status` is `kept` or `discarded` | per call: `cls(mc,/served_model)` (OBSERVED by provider); per actor: ceiling D under `apv:SingleModelPerActor`, used only when `/served_model` is absent. Never for `cached` or `error` calls (R-07) | core or inf | C50 |
| `aprov.use_tools@1` | `used(x:L(mc), x:L(fx), [prov:role apv:ToolDefinitionsInput])` | `model_call/tools` (a `fixture` of kind `tool_definitions`) | `cls(mc,/tools)` | core or inf | C50 |
| `aprov.use_request@1` [R-USE-REQ] | `used(x:L(te), x:L(p), [prov:role apv:CallRequestInput])`, `p` = `te.call` | `tool_execution/call` | `weakest(cls(te,/call), ex(te), ex(p))`: OBSERVED when the source links structurally; DERIVED for a unique call-id match; INFERRED for positional pairing [landscape/trace_formats.md §6.5]. **Guard NE-18:** not emitted when a `decision` with `verdict` = `modify` has `p` as subject; `aprov.n_gap@1` then records `/call` with `apv:NotRecorded` (the modified request has no slot in `aer/0.1`) | core or inf | C33, C37, C50 |
| `aprov.start_tool@1` [R-START-TOOL] | `wasStartedBy(x:L(te), x:L(p), x:L(mc))`, where `mc` generated the message containing `p`; the starter is omitted when that message was not generated by an activity | `te/call`; `message/generated_by`; a rule cited by `te` or by `te.actor` whose catalogue entry declares `apv:AutoExecution`; `te/authorised_by` absent | ceiling D; `weakest(premises of aprov.use_request@1, class of the rule that declares the assumption)` | core or inf | Inf. 9 (the trigger is generated by the starter, which holds iff the `aprov.gen_part@1` statement exists); C26; C43; C44 |
| `aprov.authorise@1` [R-36; approval] | `wasStartedBy(x:L(te), -, x:L(dc))` | `tool_execution/authorised_by` = `dc`, a `decision` with `verdict` = `allow` | `weakest(cls(te,/authorised_by), ex(dc), ex(te))`; replaces `aprov.start_tool@1` for that execution (no `apv:AutoExecution` premise) | core or inf | Inf. 9 (existential trigger generated by `dc`); C50 |
| `aprov.assoc_model_call@1` [R-ASSOC-LLM] | `wasAssociatedWith(x:L(mc), x:L(actor), [prov:role apv:AgentSystemRole])`; plus `wasAssociatedWith(x:L(mc), x:L(actor).svc, [prov:role apv:InferenceProvider])` when the service node exists and `status` is `kept` or `discarded` | `model_call/actor`; actor `/model/served` or `/model/provider`, or `model_call/served_model` | first statement: `cls(mc,/actor)`; second: `weakest(cls(mc,/actor), class of the identifying field)`, which is OBSERVED when the provider reports the served model (`by: provider`). No provider association for `cached` or `error` calls (R-07) | core or inf | C47 (agent lifetimes are not modelled: unchecked); C50 |
| `aprov.assoc_tool@1` [R-ASSOC-TOOL] | `wasAssociatedWith(x:L(te), x:L(rt), [prov:role apv:ExecutingRuntime])`, where `rt` = `te.actor`; `actedOnBehalfOf(x:L(rt), x:L(ag), x:L(te))`, where `ag` is the actor of the activity that generated the request's message, or `message.actor` when the message was generated by an actor, or `te.requested_by` when the execution has no request part | `tool_execution/actor`; the request's message provenance or `tool_execution/requested_by`; `apv:AutoExecution` or `/authorised_by` (for the delegation) | association: `cls(te,/actor)`; delegation: ceiling D, with the assumption, or `cls(te,/requested_by)` | core or inf | Inf. 14 entails `wasAssociatedWith(te, ag)`, which is the v2.3 R2 edge, now *derived*; C49; C50 |
| `aprov.assoc_scope@1` | `wasAssociatedWith(x:L(s), x:L(actor))` | `scope/actor` | `cls(s,/actor)` | core or inf | C50 |
| `aprov.deleg_user@1` [R-DELEG-USER, per scope actor] | `actedOnBehalfOf(x:L(a), x:L(u))` (no activity), one statement per actor `a` that is the `actor` of at least one scope and carries `/on_behalf_of` = `u` | `actor/on_behalf_of` (C.3.2), set by the adapter under a rule declaring `apv:AgentActsForUser` | `cls(a,/on_behalf_of)` (ceiling D) | core or inf | C49 |
| `aprov.attr_message@1` [R-ATTR-USER, generalised] | `wasAttributedTo(x:L(m), x:L(actor))` | `message/actor` present, and `message/generated_by` absent or referencing an actor | `cls(m,/actor)`. Examples: a simulated user's message (D, `apv:ScriptedUser`); STAC prefix user turns attributed to the prompt-writer actor (I) [sources/multiturn-agent-attack.md §3.3] | core or inf | Inf. 13 (∃ a generating activity associated with the actor: true of an author); C48 |
| `aprov.attr_fixture@1` [N-PAYLOAD attribution] | `wasAttributedTo(x:L(fx), x:L(actor))` | `fixture/actor` | `cls(fx,/actor)` (configuration provenance in the core, AD-11) | core or inf | Inf. 13; C48 |
| `aprov.decision@1` [R-TRANSFORM for defences; §13 E2] | `wasAssociatedWith(x:L(dc), x:L(actor), [prov:role apv:DefenceRole or apv:DeciderRole])`; `used(x:L(dc), S, [prov:role apv:DecisionSubject])`, where `S` is an *entity*: the subject part `x:L(p)` or message `x:L(m)`; for a subject `tool_execution` `te`, its pre-decision output `x:L(te).out`; for a subject `tool_result` part `P` recorded after an in-place overwrite, `x:L(P).pre`. For `verdict` = `modify` or `redact` with a recorded result `R` (the part generated by `dc` through `aprov.gen_result@1` or `aprov.gen_part@1`): `wasDerivedFrom(R, S, [prov:type apv:DefenceRedaction or apv:DefenceModification])`. A subject that is an activity with no output entity here (a `model_call`) is stated only as the attribute `apv:decisionSubject` (QName); there is no `used` (NE-19). `S` carries `apv:contentSha256` of `decision/original` when recorded, or `apv:contentStatus` from its `unk` (`apv:Overwritten` for an in-place overwrite) | `decision/actor`, `/subject`, `/verdict`, `/original` or its `unk` | `weakest(ex(dc), cls(dc,/subject))` (INFERRED for sentinel-recognised redactions: `agentdojo.pi_detector_sentinel@1` [landscape/trace_formats.md §6.6]) | core or inf | C42 (gen(S) ≺ gen(R)); C24; C50 |
| `aprov.env_pass@1` [R-ENV-PASS] | for a `state_change` `sc` whose scope is a scope activity `s`: `used(x:L(s), B, [prov:role apv:InitialState])`; if changed: `wasGeneratedBy(A, x:L(s))` and `wasDerivedFrom(A, B, [prov:type prov:Revision])`. `B` is the after-state entity of the predecessor `state_change` of the same `target`, chosen along `after` edges (never by file order, never by digest equality alone), whose `after_sha256` equals this `before_sha256`, when a rule cited for `sc` declares `apv:EnvironmentCarriedOver`; otherwise `B` is the new entity `x:L(sc).before` with no link (R-54). `A` = `x:L(sc).after`. Carried-over state changes with the same scope activity and the same `B` state one `used` (and, under `aprov.env_call@1`, one `wasInvalidatedBy`) that cites the fields of each of them, never one statement per state change (regen item 165) | `sc/scope`, `/target`, `/before_sha256`, `/after_sha256`, `/after` | `cls(sc,…)`, normally O (`by: capture`); carry-over ceiling D under `apv:EnvironmentCarriedOver` (digest equality is a consistency check under `apv:EnvironmentDigestCanonical`) | core or inf | C24; C36–C38 (events); C42; Inf. 12 (revision ⇒ alternate) |
| `aprov.env_call@1` [R-ENV-CALL] | as `aprov.env_pass@1`, with the scope a tool execution `te` (`/cause`); if changed, additionally `wasInvalidatedBy(B, x:L(te))` | a `state_change` caused by `te` (per-call capture only) | `ex(sc)`; carry-over as in `aprov.env_pass@1` | core or inf | C25; C36; C38; C42 |
| `aprov.state_patch@1` [R-35; patch chains] | for a `state_change` `sc` with `/patch` (and no digests): entity `x:L(sc).after`; `wasGeneratedBy(x:L(sc).after, x:L(c))` when `/cause` = `c` resolves to an activity (`tool_execution`, `scope`, `decision` or `model_call`); `wasDerivedFrom(x:L(sc).after, P, [prov:type prov:Revision])`, where `P` is the after-state of the nearest predecessor patched `state_change` of the same `target` along `after` edges (never file order); with no such path, a fresh entity with no derivation | `sc/patch`, `/target`, `/cause`, `/after` | `weakest(cls(sc,/patch), cls(sc,/cause), cls(sc,/after))` | core or inf | C24; C42; Inf. 12 |
| `aprov.inj_placement@1` [R-INJ-ENV] | `wasDerivedFrom(E0, x:L(fx), [prov:type apv:InjectionPlacementDerivation])`, where `E0` is the first state entity of the run's first pass | `fixture` of kind `injection_payload` with `/vector`; the first `state_change` `before_sha256`; a rule declaring `apv:InjectionPlacement` | ceiling D. prov_semantics rates this OBSERVED; this section rates it DERIVED, because "the benchmark placed the payload at the vector" is a property of benchmark code and is not recorded (F.1.1 test T-D). Configuration provenance in the core (AD-11) | core or inf | C42 |
| `aprov.rerun@1` [R-RERUN; §13 E6] | `wasStartedBy(x:L(pass_p+1), x:L(m_last), x:L(mc_last))` | consecutive `attempt` scopes with known `/index`; the last message of pass `p`, whose content is null (not empty); a rule declaring `apv:RerunOnEmptyReply` | ceiling D | core or inf | Inf. 9; C43 |
| `aprov.spawn@1` [R-36; hand-offs] | `wasStartedBy(x:L(sub), -, x:L(sp))` | `scope/spawned_by` = `sp` (a `tool_execution` or `model_call`) on a scope of kind `subagent` (or `other`) | `cls(sub,/spawned_by)` | core or inf | Inf. 9 (existential trigger generated by the spawner); C50 |
| `aprov.outcome@1` [R-OUTCOME; §13 E5] | by `judgement.origin` (R-21): **`checker`** with `/generated_by` = `g` (a judge `model_call` or a scorer `scope`): `wasGeneratedBy(x:L(j), x:L(g))`, and each `/inputs[k]` as `used(x:L(g), x:L(i_k), [prov:role apv:CheckedInput])` (R-37). **`checker`** without `/generated_by`: `wasGeneratedBy(x:L(j), x:L(j).check)` (`apv:CheckerRun`); `wasAssociatedWith(x:L(j).check, x:L(j.actor), [prov:role apv:CheckerRole])`; usages from `/inputs` when present, otherwise from the checker-input assumptions declared for the task's checker: the output text (`apv:CheckedOutput`), the pre-state when a state entity exists (`apv:CheckedPreState`), the post-state when one exists (`apv:CheckedState`), and every request part of the scored attempt (`scope.scored` = true; `apv:CheckedCallTrace`). **`harness_default`**: no checker activity; `wasAttributedTo(x:L(j), x:L(j.actor))`. **`harness_rule`**: activity `x:L(j).rule` (`apv:HarnessRuleEvaluation`); `wasGeneratedBy(x:L(j), x:L(j).rule)`; `wasAssociatedWith(x:L(j).rule, x:L(j.actor))`; for each judgement in `/inputs`: `used(x:L(j).rule, x:L(j'), [prov:role apv:RuleInput])` and `wasDerivedFrom(x:L(j), x:L(j'), x:L(j).rule)`. **`recomputed`**: `wasDerivedFrom(x:L(j), x:L(j.revises), [prov:type prov:Revision])` and `wasAttributedTo(x:L(j), x:L(j.actor))` (the correcting party). No replay check is ever invented | `judgement/actor`, `/origin`, `/generated_by`, `/inputs`, `/revises`; the scored attempt and its parts | generation and attribution: `ex(j)` and the class of `/origin` (value OBSERVED with `by: benchmark`; the existence of a synthetic checker run is DERIVED); `/inputs` usages: `cls(j,/inputs/k)`; assumption usages: ceiling D, with the per-task checker-input assumptions (verified only for audited checkers, else INFERRED; AD-05) | core or inf | C24; C42 (revisions); C48; C50 |
| `aprov.g_use@1` [G-USE] | `used(x:L(ac), E_i, [prov:role apv:ActivityInput, apv:inputIndex i])` for each `activity.inputs[i]`, where `E_i` is the entity of the target: a message `x:L(m)`, a part `x:L(m)-k`, a fixture, an artefact, a judgement, or a `state_change`'s current state entity (its `.after`, else its `.before` or carried-over predecessor) | `activity/inputs/i` resolves backward to an entity-like record (C.3) | `weakest(cls(ac,/inputs/i), ex(ac), ex(target))` (the class of the input link; Addendum B); ceiling OBSERVED | core or inf | C33, C37 (events); C50; supplies Inf. 6 premises |
| `aprov.g_gen@1` [G-GEN] | `wasGeneratedBy(x:L(af), x:L(g))` | `artefact/generated_by` = `g`, an `activity`, `model_call` or `tool_execution` | `weakest(cls(af,/generated_by), ex(g), ex(af))`; ceiling OBSERVED | core or inf | C24; C39 profile rule; C50; supplies Inf. 6 premises |
| `aprov.g_assoc@1` [G-ASSOC] | `wasAssociatedWith(x:L(ac), x:L(actor), [prov:role apv:PerformerRole])` | `activity/actor` | `weakest(cls(ac,/actor), ex(ac), ex(actor))`; ceiling OBSERVED | core or inf | C50 |
| `aprov.comm@1` [R-COMM-1, R-COMM-2, R-COMM-3, generalised] | `wasInformedBy(a2, a1, [apv:viaEntity e …, apv:premise u g …])` for exactly the Inference 6 closure over named activities (E.1.6), including the generic usages and generations of G-USE and G-GEN | usage and generation statements of the routing scope | ceiling D; the best witness (E.1.6) | core or inf | C35 (events; MAY-flag on activity times); the Inf. 5 witness is present by construction |
| `aprov.part_of@1` [R-PART] | attribute `apv:partOf` (never a relation): non-`tool_call` part → message; message → scope (non-thread); activity → `scope`; scope → `parent` | the reference fields | class of the reference field (attribute rule) | with its node | — |
| `aprov.after@1` [R-ORDER] | attributes `apv:afterCausal`, `apv:afterTime`, `apv:afterPos`, `apv:afterProto` (QNames of the nodes of the referenced AER ids; references to records without a node are skipped and reported) and `apv:afterEvidenceClass` (the weakest class among the edges kept on the node) | `/after[*]` | per edge: `cls(R,/after)` with the edge's own tag. INFERRED edges are routed out of the core (R-53): on an entity node as a mention in the inference bundle, on an activity node as an `apv:Assessment` with `apv:claim apv:OrderedAfter` | with its node | never a relation; MAY-flags only |
| `aprov.status@1` | status attributes (E.4.5) on emitted nodes for each `unk` pointer that has a fixed property; otherwise `aprov.n_gap@1` | `/unk` | `weakest(ex(R), DERIVED)` | with its node | — |

`aprov.outcome_replay@1` of the first draft is withdrawn: re-execution of recorded calls is deferred (AD-10 row 2),
and a judgement with `by: replay` imported from a source maps through its `origin` like any other (R-21).

### E.1.5 Firing, classification and routing (normative)

1. **Firing.** A rule fires for a tuple of AER records only if every required pointer resolves.
   - If a required pointer is listed in the record's `unk`, the rule MUST NOT fire. The engine MUST then emit
     the status from E.4.5 on the node concerned instead.
   - Sentinel values are already excluded by the AER validator (C.7.3).
2. **Class.** The class of a statement `s` is

   `class(s) = weakest(ceiling(rule(s)), cls(R,p) for every premise field (R,p), ex(n) for every endpoint node n,
   class(q) for every premise statement q)`.

   - **Existence rule (R-22).** `class(s)` never exceeds the existence class of any of its endpoints, and the core
     declares every node it references.
   - Ceilings are listed in the catalogue:
     - OBSERVED for structural restatement rules (`aprov.n_*`, `aprov.gen_*`, `aprov.member_request@1`,
       `aprov.use_request@1`, `aprov.assoc_model_call@1`, and the generic rules `aprov.g_act@1`, `aprov.g_use@1`,
       `aprov.g_gen@1`, `aprov.g_assoc@1`);
     - DERIVED for rules that apply an assumption or a PROV-CONSTRAINTS inference;
     - INFERRED for policy and heuristic rules.
   - The engine MUST NOT raise a class above any premise.
3. **Assumption class: static (AD-05).** The adapter resolved every assumption at map time: a rule whose assumption
   is verified for the identical framework identity is cited at class D, otherwise its I twin is cited (F.1.5). The
   class of the AER field that the rule justifies (`cls(R,p)`, or `ex(R)` for an unscoped citation) therefore already
   includes the assumption. The engine reads classes only. It lists the assumptions of every cited rule, taken from
   the catalogue entry at the version in the AER header: core `apv:` terms as `apv:assumption`, adapter-declared
   `<ns>:<Name>` terms as `apv:adapterAssumption` (E.10 item 11). A change of verification status is a
   new rule id or catalogue version, so it changes the AER digest and every `dk` (E.3.4).
4. **Routing.**
   - A statement of class OBSERVED or DERIVED MUST be placed in the core bundle.
   - A statement of class INFERRED MUST be placed in the inference bundle keyed by its *method set* (R-53): the
     sorted set of every rule id that contributes an INFERRED premise or assumption to it, namely the AER or SEM
     rules cited for its INFERRED premise fields, the engine rules with an INFERRED ceiling it rests on, and the
     method sets of its INFERRED premise statements. An INFERRED AER field always cites a rule (C.6.4), so the
     method set of an INFERRED statement is never empty; if it were, the engine fails with a typed error.
   - A node is declared in the bundle that its existence class routes it to. Bundles reference nodes declared
     in the core by IRI and do not re-declare them.
5. **Attribute evidence rule.** Each attribute value restates one or more AER or SEM fields and so has its own
   class `c_attr`. Let `c` be the class of the element itself: existence for a node, `class(s)` for a relation. An
   attribute whose value names an INFERRED node (an `x:` QName, e.g. `apv:partOf` an inferred attempt scope,
   `apv:afterCausal` an inferred model call) has `c_attr` = INFERRED (C.6.5 rule 4; D-81, regeneration-batch item 3).
   - If `c_attr = c`, the attribute is emitted as is.
   - If `c_attr` = DERIVED and `c` = OBSERVED, the attribute is emitted and its property QName is listed in the
     element's `apv:derivedAttribute`.
   - If `c_attr` = INFERRED and `c` is OBSERVED or DERIVED, the attribute MUST NOT be emitted in the core. It is
     emitted in the inference bundle of its method set:
     - on an **entity** node, as a mention entity `x:L(id).mn-<h12>` with `mentionOf(mention, node, core bundle)`;
     - on an **activity or agent** node, as an `apv:Assessment` whose `apv:subject` is the node and whose `apv:claim`
       is `apv:Labelled` (mentions apply only to entities; R-21, PROV-09);
     - on a **relation** (for example, an INFERRED `apv:sentTransform` on a DERIVED usage), as an `apv:Assessment`
       whose `apv:subject` is the statement IRI and whose `apv:claim` is `apv:SentTransformed`.
6. **Evidence attributes.** Every node and every identified relation in every bundle MUST carry the following
   (E.4.4):

   | Attribute | Cardinality | Value |
   |---|---|---|
   | `apv:evidenceClass` | exactly 1 | `apv:Observed`, `apv:Derived` or `apv:Inferred` |
   | `apv:rule` | exactly 1 | the engine rule id (a reference without `#…`), as an `xsd:string` |
   | `apv:sourcePointer` | ≥ 1 for every statement with AER premises | `"<record id><RFC 6901 pointer>"`, for example `"mc2/input/3"` or `"m3"`, or `"seal/issues/<i>"` for a seal issue premise (E.10 item 23); sorted by AER record position, then by pointer. Every pointer resolves under RFC 6901 (there is no delta-form input in `aer/0.1`) |
   | `apv:basisRule` | 0..n | the AER or SEM rule ids of the premise records (references without `#…`; strings), sorted |
   | `apv:rulePointer` | 0..n | the scoped references (`<rule id>#<pointer>`, C.6.4) behind `apv:basisRule`, when a citation is scoped |
   | `apv:attestedBy` | 0..n | the `by` value (or `O:<party>` party) of every OBSERVED premise field |
   | `apv:assumption` | 0..n | core `apv:` assumption individuals (QNames) |
   | `apv:adapterAssumption` | 0..n | adapter-declared `<ns>:<Name>` assumptions (`xsd:string`; apv 0.2.0, D-501; E.10 item 11) |
   | `apv:premise` | 1..n for `aprov.comm@1` and assessments | statement QNames |
   | `apv:method` | exactly 1 for INFERRED statements | the rule ids of the method set |
   | `apv:confidence`, `apv:threshold` | optional | method outputs (`xsd:double`) |

   Top-level statements (E.3.3) carry `apv:evidenceClass` and `apv:rule` only.
7. **Determinism.** The order in which rules are evaluated MUST NOT affect the output (E.9).

### E.1.6 Communication as the Inference 6 closure (normative)

PROV-CONSTRAINTS makes `wasInformedBy(a2, a1)` equivalent to the existence of an entity that `a1` generated and
`a2` used (Inferences 5 and 6). Communication is not transitive [landscape/prov_semantics.md §3.6, §3.18].
The engine therefore emits communication as follows. This is normative: `wasInformedBy` is **exactly the Inference 6
closure over named activities, each statement with `apv:premise`** (AD-19(c)).

1. **Routing scopes.** For a method set `M` (possibly empty), the scope is `S(M)` = core ∪ every inference bundle
   whose method set is a subset of `M`. `S(∅)` is the core.
2. **Witnesses.** In scope `S`, a witness for the pair `(a2, a1)` is a pair of statements (`u`, `g`) in `S` where
   `u` = `used(a2, e)`, `g` = `wasGeneratedBy(e, a1)`, `a1` ≠ `a2`, and both activities are named nodes. Its method
   set is the union of the method sets of `u` and `g`. A witness whose usage and generation lie in two different
   inference bundles therefore lies in the scope of the union of their method sets.
3. **Placement.** Let `C(M)` be the set of pairs with at least one witness in `S(M)`.
   - The core asserts one `wasInformedBy(a2, a1)` under rule `aprov.comm@1` for every pair in `C(∅)`. Its class is
     the maximum over core witnesses of `weakest(class(u), class(g))`, capped at DERIVED.
   - The inference bundle of method set `M` asserts one statement for every pair in `C(M)` minus `C(M')` for every
     method set `M'` ⊊ `M` that occurs; its class is INFERRED and its `apv:method` is `M`.
   - `apv:viaEntity` lists every witnessing `e`, and `apv:premise` lists every `u` and `g`, of the witnesses that lie
     within the statement's scope and whose class is at least the statement's class (R-53). A core statement
     therefore never cites an INFERRED premise (NE-11).
4. **The validator checks equality, not inclusion.**
   - The asserted core communications MUST equal `C(∅)`.
   - The communications of the inference bundle of `M` MUST equal `C(M)` minus the closures of its proper occurring
     subsets.
5. **What the closure yields with the rules of E.1.4:**

   | Witness entity | Communication | prov_semantics code |
   |---|---|---|
   | request part | `tool_exec_k ← llm_m` | R-COMM-1 |
   | tool message used by any later invocation of the pass | `llm_m' ← tool_exec_k` | R-COMM-2 |
   | assistant message in a later request | `llm_m' ← llm_m` | R-COMM-3 (§13 G1) |
   | carried-over environment state (under `apv:EnvironmentCarriedOver`) | `pass_p+1 ← pass_p` | new; makes cross-pass environment dependence explicit [landscape/prov_semantics.md §5.6 item 4] |
   | pre-decision output and decision result | `decision ← tool_exec`; `llm ← decision` | new (A5: the defence is its own activity) |
   | request part under approval | `decision ← llm` | new |
   | checker inputs (output text, request parts, states) | `checker ← llm`; `checker ← pass` | new (§13 E5) |
   | judgement inputs of a harness rule | `rule ← checker` | new |
   | generic input (G-USE) of an entity generated elsewhere | `activity ← llm`, `activity ← tool_exec`, `activity ← activity` | G-USE/G-GEN (AD-15) |
   | generic artefact (G-GEN) used by a later activity (memory write → memory read) | `read ← write` | G-USE/G-GEN (AD-15) |

6. **No communication between two tool executions** unless they share an entity. In practice that means a
   per-call state snapshot (`aprov.env_call@1`). There is never one between tool executions of the same request.
7. **An activity is never informed by itself.** The validator rejects such a statement.
8. **Scope of the claim.** Inference 13 entails communications with *existential* activities (for example from an
   attribution). Those are not materialised: the wording is "never less than entailed, for named activities" (R-53).

*Evidence.* With this rule, "asserted = entailed for named activities" holds by construction. In v2.3 the two sets
differed by 26,645 released and 23,449 converted communications, and the pair also counts the taint-only `used`
edges of R6 (E.8.4). The two readings are one quantity counted two ways: the 26,645 / 23,449 R6 taint-only `used`
edges each entail, via Inference 6, exactly one `wasInformedBy` the builder never asserts (entailed 99,278 / 91,661
minus asserted 72,633 / 68,212; no asserted edge is unentailed)
[audit/provenance_evidence/evidence_stats.json; landscape/prov_semantics_evidence/inference6_scan.json;
landscape/prov_semantics.md §5.5, §13.2 re-ran `inference6_scan.py`]. Either reading may be cited with its
evidence file.

### E.1.7 Engine-run inference methods (deferred)

Engine-run inference methods are deferred to v0.2 (AD-10 row 15); in v0.1, inference bundles come only from
INFERRED AER and SEM fields cited under adapter I-rules. The design below is kept for when they return. Engine-run
methods produce INFERRED PROV statements in their own inference bundle; they would run only when listed in an option
that enters the derivation key.

| Rule id | Statement | Method | Class |
|---|---|---|---|
| `aprov.i_arg_literal_overlap@1` [I-ARG-SUPPORT] | `wasDerivedFrom(x:L(p), x:L(m_i), [apv:method "aprov.i_arg_literal_overlap@1", apv:matchedArg "<RFC 6901 pointer into args>"])` | For a tool_call part `p` and each context member `m_i` of the invocation that generated `p`: some argument leaf `p` holds (a string, or a number rendered as a string) of at least 5 characters after whitespace collapse occurs literally in the whitespace-collapsed text of `m_i` [audit/provenance.md §4.3] | INFERRED. The fact that the text matches is DERIVED; the derivation claim built on it is INFERRED (F.1.2) |

*Evidence for opt-in.* Only 28.8% of released v2.3 communications have any literal argument support. In 18.1%
of informed calls the only literal support lies in an older output [audit/provenance.md §4.3]. The method is
useful for analysis but too weak to run by default.

Other methods, such as ContextCite, TracLLM, AttnTrace or an LLM judge [landscape/prov_semantics.md §6], MUST be
added as separate rule ids with their own bundles. They MUST NOT be mixed into this one.

> **Resolved (AD-19 / R-20, R-06): Challenge 1 to D7 (six adjustments to the prov_semantics §8 catalogue).**
> (a) *Rejected:* tool-call requests are `hadMember` of a `prov:Collection` message (A5, §13 E1), not carried by
> the containment attribute of the first draft; the quotation of the message by the request stays out (Constraint 42
> would claim a strict order between two generations of one response event). (b) *Accepted (R-06):* the invocation uses the recorded message and the
> usage carries per-input sent transforms; this keeps R-COMM-2 for every errored tool result (6,920 activities carry
> `adprov:error` in the release [audit/provenance.md §6]) and every role-rewritten or reasoning-passback message,
> while defence transforms stay separate activities. (c) *Accepted:* DERIVED context membership needs no capture
> completeness; completeness bounds unrepresented invocations and is reported as accounting (PROV has no closed
> world [landscape/prov_semantics.md §3.18]). (d) *Accepted:* `wasInformedBy` is the full Inference 6 closure over
> named activities. (e) *Accepted:* no relation times. (f) *Accepted:* payload containment and authorship are
> assessments (E.7); a derived-semantic bundle kind is deferred to v0.2.

> **Resolved (AD-03 / R-02, R-06, R-22): Challenge 2 to D2 (AER interface requirements).** (a) *Accepted:*
> `model_call.input` items are `Id<message>` or `{id, sent: [Transform], sent_sha256?}`, with tags and rules; C drops
> its as-sent message copies. (b) *Already in C:* `model_call.tools` names a `fixture` of kind `tool_definitions`.
> (c) *Accepted* as `Artefact.prov_primary ∈ native|byte_derived|secondary|unknown` (E.3.3). (d) *Accepted:*
> longest-prefix `evf` is normative in C.6.3. (e) *Rejected:* C's local-id grammar `^[a-z][a-z0-9_]{0,31}$` stands;
> injectivity comes from mapping `#` to `-` (AD-04; E.4.2). (f) *Already in C:* `execution.instrumentation` with the
> R-2 item shape.

---

## E.2 The "never emit" list (normative)

The engine MUST NOT emit any statement in the list below, in any bundle. Each item has a validator check id
(`PV-NE-n`, run in D8 tier 4) and the evidence that motivates it.

| # | Never emit | Why (evidence) |
|---|---|---|
| NE-1 | `used` or `wasInformedBy` justified by temporal or positional adjacency. AER `after` edges and file order MUST NOT map to any PROV relation; order is carried only by `apv:after*` attributes (`aprov.after@1`) | Order is not communication: 36.2% of the old chain edges joined calls of one turn [manuscript/review_feedback.md SEM-1]; [landscape/trace_formats.md §6.15] |
| NE-2 | `used` by a tool execution of anything other than its own request (`aprov.use_request@1`) or the state it read (`aprov.env_call@1`) | The v2.3 R3–R5 activity conflation [audit/provenance.md §5.3; landscape/prov_semantics.md §5.2] |
| NE-3 | `wasDerivedFrom` (or a subtype) inferred from context membership, or from a `used` and a `wasGeneratedBy` that merely co-occur | PROV has no inference to derivation [landscape/prov_semantics.md §3.18]; R7 was "the strongest content claim on the weakest evidence" [audit/provenance.md §5.5] |
| NE-4 | `wasAttributedTo` of a composite output (a whole tool result, or a whole message) to a channel or "source" agent, or to an author named only by the content (`apv:declaredSender` stays an attribute; §13 E4) | By Inference 13 this asserts that the agent's activity generated the output [landscape/prov_semantics.md §5.1 R8]. 66 of 150 sampled enriched graphs misattributed mutation outputs [audit/provenance.md §5.6] |
| NE-5 | `wasInfluencedBy` in any form | It is not a hedge [landscape/prov_semantics.md §3.13]; PROV-O says not to use it alone |
| NE-6 | Any time value that the AER does not record: fallbacks such as the run start copied to calls or `end := start` (`build_prov.py:393-395, 436-437`), sentinel values, naive local times as `xsd:dateTime`, or relation times in this version | SEM-9 [manuscript/review_feedback.md]; [audit/provenance.md §7.1.2] |
| NE-7 | Composite or transitive communications (`tool_exec_k ← tool_exec_j` through an invocation; `llm ← llm` through two hops), or any `wasInformedBy` outside the Inference 6 closure (E.1.6) | Communication is not transitive [landscape/prov_semantics.md §3.6, §5.3] |
| NE-8 | Usage of a member inferred from usage of a collection: a message's request parts (`hadMember`) or a context dictionary | No such PROV inference [landscape/prov_semantics.md §3.15; §13 G1] |
| NE-9 | Negative facts derived from absence ("did not use", "concurrent", "no reasoning") | PROV has no closed-world reading; an absent `after` edge means unknown order [DECISIONS D2] |
| NE-10 | Policy claims as PROV influence relations: integrity, roles, exposure, taint, payload containment or authorship expressed as `used`, `wasDerivedFrom`, `wasInformedBy`, `wasAttributedTo` or `wasInfluencedBy` | The 26,645 / 23,449 R6 taint-only `used` edges each entail, via Inference 6, exactly one `wasInformedBy` the builder never asserts (entailed 99,278 / 91,661 minus asserted 72,633 / 68,212; E.1.6) [audit/provenance_evidence/evidence_stats.json; landscape/prov_semantics_evidence/inference6_scan.json]; D7 |
| NE-11 | A statement of class INFERRED in the core bundle, or any statement with an INFERRED premise in the core (including an INFERRED `after` attribute, a node whose existence is INFERRED, and a premise list citing an INFERRED witness) | Qualification cannot hedge [landscape/prov_semantics.md §0 item 2] |
| NE-12 | A statement whose required AER field is in `unk`; a node for an occurrence that the AER does not assert (no activity for a tool call that was not dispatched or was denied: a denial is a `decision` only) | "Declared, never invented" [landscape/trace_formats.md §6.7] |
| NE-13 | Attribution of scripted or synthetic turns (for example STAC's scripted assistant tool calls, whose actor is an `attacker` with role `context_fabricator`) to an LLM agent or a model invocation | 775 of 778 STAC tool calls are scripted [sources/multiturn-agent-attack.md §3.2] |
| NE-14 | An activity that stands for two occurrences, for example tool-execution facts on a model invocation or the reverse | The core defect D1 [audit/provenance.md §14] |
| NE-15 | Instance IRIs in the vocabulary namespace, and provider ids or content hashes as node identity | 1,358 tool-node ids recur across released graphs [audit/provenance.md §9]; SEM-10 |
| NE-16 | The converse of Inference 13 (attribution derived from generation plus association) and any other non-PROV inference rule applied as if it were PROV's | [landscape/prov_semantics.md §3.18, §6 (Flowcept's property chain)] |
| NE-17 | SEM-dependent interpretations in the core bundle: payload containment, attack success *interpreted* for security (polarity), labels and the label census. Configuration ground truth (attack, target and defence ids, payload fixtures, attacker attribution, injection placement, raw outcome values) is configuration provenance and stays in the core (AD-11); core bundles are therefore not a blind input for detectors (NC-PROV-01), and a normative blind view arrives with the ML export (deferred, AD-10) | Interpretations depend on SEM policy [audit/provenance.md §7.1.4]; R-23 |
| NE-18 | `used(te, p)` when a `decision` with `verdict` = `modify` has the request part `p` as subject (until `aer/0.2` models the replacement); the gap is recorded as a status instead | The execution consumed the edited request, not the original (EXT-04; R-36) |
| NE-19 | A `used` whose object is an activity, and a `mentionOf` whose supra or infra is not an entity (activities and agents get `apv:Assessment` instead) | PROV-CONSTRAINTS Con. 50 typing and Con. 55 disjointness; PROV-LINKS §2 (R-21; PROV-08(a), PROV-09) |
| NE-20 | `hadPrimarySource` (a `wasDerivedFrom` typed `prov:PrimarySource`) unless the artefact's `prov_primary` ∈ {`native`, `byte_derived`} | §13 E13; R-22 (PROV-06) |
| NE-21 | Generic statements beyond what the AER declares: a G-USE `used` of anything not in the activity's `inputs`; a G-GEN generation of an artefact by anything other than its `generated_by`; a G-ACT node typed with a specialised activity class (`apv:ModelInvocation`, `apv:CacheRead`, `apv:ToolExecution`, `apv:Decision`, `apv:CheckerRun`); and any PROV from an `activity` or `artefact` record that represents an occurrence or content an existing kind represents (the engine refuses the AER with a typed failure) | Addendum B (AD-15): specialised kinds are preferred, and adapters MUST NOT use `activity` for something an existing kind represents |

---

## E.3 Bundles and the provenance of the conversion

### E.3.1 Bundle kinds

| Kind | Contents | Keyed by | Responsibility | Plan of the generating activity | PROV-CONSTRAINTS |
|---|---|---|---|---|---|
| **core** | OBSERVED and DERIVED PROV statements derived from the AER alone (E.1), the capture profile and gap entities. Exactly one per document | — | AgentPROV engine (`sw:agentprov`) | `rules:agentprov-prov.0.1` | validated on its own [landscape/prov_semantics.md §3.16] |
| **inference** | INFERRED PROV statements, INFERRED attribute mentions (entities) and INFERRED attribute, order and transform assessments (activities, agents, relations). One bundle per method set (E.1.5 item 4) | method set (rule ids) | the derive activity, associated with the method's agent in the role `apv:MethodProvider` and with the method's catalogue entry as plan (R-56); never `wasAttributedTo(bundle, adapter)` | the catalogue entry of the method | validated on its own and as core ∪ inference (application view) |
| **assessment** | Non-PROV claims: mention entities (integrity, roles, channel, outcome claims, declared sender, namespaced labels) and `apv:Assessment` entities (payload containment, authorship, exposure, taint, labels of activities) (E.7). One bundle per SEM document | SEM profile id and version | AgentPROV engine together with the SEM profile | `rules:<sem-profile>.<version>` | validated on its own; the validator checks that the bundle uses only the allowed statement forms (E.7.2 item 5) |

A document MUST contain exactly one core bundle. It contains zero or more inference bundles, and one assessment
bundle per SEM document supplied. Empty inference bundles MUST NOT be emitted.

### E.3.2 Document layout

```
document                                   (one per execution × spec version × option set)
  prefix apv, x, xd, raw, sw, rules        (declared once, at document level; bundles declare none)
  // top level: provenance of the conversion (E.3.3)
  raw artefacts, AER entity, SEM entities, plans, software agents, capture/map/annotate/derive activities,
  one entity per bundle [prov:type prov:Bundle + apv:CoreBundle | apv:InferenceBundle | apv:AssessmentBundle]
  bundle xd:bundle.core.<dk>                          … endBundle
  bundle xd:bundle.inf.<method-slug>.<dk>             … endBundle   (0..n)
  bundle xd:bundle.assess.<profile-slug>.<dk>         … endBundle   (0..n)
endDocument
```

Prefixes are declared only at document level. A document whose bundles carry no prefix maps round-trips
PROV-JSON → PROV-O TriG → PROV-JSON with model equality; this was verified on the sample
[landscape/prov_semantics.md §7.3–§7.4; prov_semantics_evidence/evq_sample.json], and the `hadMember` form of §13 E1
was verified the same way [prov_semantics_evidence/review_rt_test4_hadmember.out].

### E.3.3 Top-level statements

All top-level statements are rule-identified (`aprov.t_*@1`). They describe AgentPROV's own processing. They are
OBSERVED, recorded by the pipeline that performed them, except where stated otherwise.

| Rule | Statements | Notes |
|---|---|---|
| `aprov.t_raw@1` | For each `execution.artifacts[i]`: `entity(raw:sha256-<hex>, [prov:type apv:RawSourceArtefact, apv:sha256, apv:bytes, apv:mediaType, apv:artefactRole, apv:provPrimary, apv:originKind, …origin attributes by kind (`git`: repository, revision, path, blob; `member`: container, label, method, crc32, size; …)])` | Content-addressed and shared across executions; for example, one STAC array file holds 483 cases [sources/multiturn-agent-attack.md §0]. Archive members are derived raw objects of the `expand` stage (AD-12). A releaser MAY be stated as `wasAttributedTo(raw, <releaser agent>)` when the source profile names it; that statement is DERIVED from profile data |
| `aprov.t_capture@1` (live mode only) | `activity(xd:capture, [prov:type apv:CaptureSession])`; `wasAssociatedWith(xd:capture, sw:agentprov-capture.<ver>)` and `wasAssociatedWith(xd:capture, sw:agentprov-backend.<ver>)` (the spawned backend worker, AD-01); `wasGeneratedBy(raw_i, xd:capture)` for each capture artefact | OBSERVED: the hash-chained `capture/0.1` log records its own session (D3) |
| `aprov.t_map@1` | `entity(xd:aer.<digest>, [prov:type apv:ExecutionRecord, apv:aerVersion "aer/0.1", apv:sha256 <execution digest>, apv:executionId, apv:sourceKey, apv:accounting, apv:issue …])`; `activity(xd:map.<h16>, [prov:type apv:Mapping])`; `used(xd:map…, raw_i)`; `wasGeneratedBy(xd:aer…, xd:map…)`; `wasAssociatedWith(xd:map…, sw:<adapter-id>.<adapter-version>, rules:<adapter catalogue>)` (plan); `wasDerivedFrom(xd:aer…, raw_i, xd:map…, g, u_i)` (Inference 11 form) | The AER digest is `seal.records_sha256`, the execution digest of D2. `apv:sourceKey` is the string `"sha256:<hex>#" + JCS(loc)` (RESOLUTIONS §3.4). The seal's accounting and issues are carried on the AER entity. "Hashes live outside what they cover" [landscape/prov_semantics.md §10.2 item 5] |
| `aprov.t_annotate@1` | For each SEM document: `entity(xd:sem.<profile-slug>.<digest>, [prov:type apv:SemanticAnnotationSet, apv:semVersion, apv:sha256])`; `activity(xd:annotate.<h16>)`; `used(…, xd:aer…)`; `wasGeneratedBy(sem, annotate)`; `wasAssociatedWith(annotate, sw:agentprov, rules:<sem-profile>.<version>)`; `wasDerivedFrom(sem, aer, annotate, g, u)` | SEM is hashed separately (D6) |
| `aprov.t_derive@1` | `activity(xd:derive.<dk_core>, [prov:type apv:ProvDerivation, apv:contextEncoding, apv:profileOptions, apv:vocabularyVersion "0.2.0"])`; `used(derive, aer)`; `used(derive, sem_j)` for every SEM; `wasAssociatedWith(derive, sw:agentprov, rules:agentprov-prov.0.1)`. For each bundle `b`: an entity with its kind type, `apv:derivationKey`, and `apv:method` or `apv:profile`; `wasGeneratedBy(b, derive)`; `wasDerivedFrom(b, aer, derive, g_b, u_aer)`. For assessment bundles, also `wasDerivedFrom(b, sem_j, derive, g_b, u_sem_j)`. For inference bundles, method responsibility is a qualified association `wasAssociatedWith(derive, <method agent>, rules:<method catalogue>, [prov:role apv:MethodProvider])`, where the method agent is the adapter (for INFERRED AER fields) or the SEM profile's annotator (for INFERRED SEM fields); never `wasAttributedTo(b, <method agent>)` (R-56; PROV-16(a)) | D7: "rule catalogue as `prov:Plan`" |
| `aprov.t_primary@1` | For each bundle `b` and each artefact `raw_i`: `wasDerivedFrom(b, raw_i)` (always); additionally `wasDerivedFrom(b, raw_i, [prov:type prov:PrimarySource])` iff the artefact's `prov_primary` ∈ {`native`, `byte_derived`}. The default `unknown` fails closed: no primary-source link (NE-20) | The harness's native run output is a primary source; re-packaged releases (dataset-hub conversions, aggregated tables, AgentDojo-PROV's converted transcripts) are secondary [landscape/prov_semantics.md §10.2 item 1; §13 E13] |
| `aprov.t_spec@1` | `entity(xd:provenance, [prov:type apv:ExecutionProvenance])`; `specializationOf(b, xd:provenance)` for each bundle | The version-independent "provenance of this execution". Revisions would be linked in the lineage document (E.3.5, deferred) |
| `aprov.t_plans@1` | `entity(rules:agentprov-prov.0.1, [prov:type prov:Plan, prov:type apv:RuleCatalogue, apv:catalogueId "aprov", apv:sha256])`; the same for each adapter catalogue `rules:<ns>.<version>` (integer version, AD-18) and the SEM profile (`apv:SemanticsProfile`) | Each catalogue file's digest is also recorded in the corpus manifest (D9). The corpus `rules/` copy is a record; `rederive` loads catalogues from package resources (AD-14) |
| `aprov.t_agents@1` | `agent(sw:agentprov, [prov:type prov:SoftwareAgent, prov:type apv:ProvEngine, apv:softwareName])` (version-free, DECISIONS D-13: the run's engine version and code digest are in the corpus `derivation.json`, H.8.2); `agent(sw:<adapter-id>.<ver>, [prov:type prov:SoftwareAgent, prov:type apv:Adapter, apv:softwareName, apv:softwareVersion])` | Adapter id and version come from the AER header `adapter {id, version}`. The adapter's code digest is not in the AER (C RF-4) and is therefore not stated by `derive`; the corpus manifest records it, keyed by the same adapter id and version (R-02) |

### E.3.4 Derivation key and bundle identity

A bundle IRI identifies one set of descriptions [landscape/prov_semantics.md §3.16, §10.2 item 4]. Each bundle
therefore carries a derivation key `dk`:

```
dk = base32_lower_nopad( sha256( "aprov-bundle/1\n" + spec_id_at_version + "\n" + catalogue_sha256 + "\n"
                                 + aer_execution_digest + "\n" + (sem_digest or "-") + "\n" + kind + "\n"
                                 + (method_set or profile or "-") + "\n" + JCS(options) ) )[:26]
```

1. Equal inputs MUST give equal keys.
2. Any change to the AER, the SEM, the spec, the catalogue or the options gives a new key, and so a new bundle
   IRI. An edit in place is impossible.
3. Engine code version is deliberately *not* part of `dk`. An engine release that changes output bytes without a
   spec or catalogue version bump is a recompute failure (E.9), not a new bundle.
4. Evidence classes and assumption verification are fixed in the AER at map time (AD-05), and adapter catalogue
   versions are in the AER header, so they are covered by `aer_execution_digest`. No profile or assumption status is
   a hidden input of `derive` (PROV-01).

> **Resolved (EF Ch 3a accepted; AD-10 / R-45, R-55):** `derive` emits only history-free statements, so recompute
> revisions, `alternateOf` links to the compat graph and validation reports do not live in the per-execution
> document. The per-execution lineage document that would carry them (E.3.5) is deferred to v0.2; in v0.1 the compat
> marking lives in the corpus manifest and index.

### E.3.5 Lineage document (deferred)

Per-execution lineage documents are deferred (AD-10 row 5). Until they return, the compat output is marked in the
data: the corpus manifest and index flag it with `apv:status apv:RegressionOracle` and profile `adprov-v2.3-compat`,
and the CLI prints a notice whenever compat output is written or loaded (R-55). The design, kept for when they
return:
- `agentprov.corpus` would write `lineage/<ss>/<ex>.lineage.json` at packaging time, as a single-instance PROV-JSON
  document in canonical form (E.5.3), deterministic given the corpus version history and the digests.
- Entities:
  - every bundle IRI released for `ex` in any corpus version, with `apv:corpusVersion`;
  - **two** compat entities (§13 G4): the released v2.3 file (identified by its hash, generated by AgentDojo-PROV's
    builder at its commit, derived from the transcript) and the regenerated projection (generated by the compat
    profile from the AER), each typed `apv:LegacyProjection` with `apv:profile "adprov-v2.3-compat"` and
    `apv:status apv:RegressionOracle`;
  - the validation report or reports.
- Statements:
  - revisions: `wasDerivedFrom(b_new, b_old, [prov:type prov:Revision])` for the same kind and key family
    (core; `inf.<method>`; `assess.<profile>`) when `b_new` supersedes `b_old`. By Inference 12 a revision also
    implies `alternateOf`;
  - `alternateOf(released file, regenerated projection)` only as justified by the byte-gate report:
    `activity(xd:validate.<h>)`, `used(validate, …)`, `wasGeneratedBy(report, validate)`,
    `wasAssociatedWith(validate, sw:agentprov)` [landscape/prov_semantics.md §10.1; §13 G4].

### E.3.6 Flattened core (deferred)

The flattened core is deferred (AD-10 row 4). When built, its path is `<ex>.prov-core.json`: one PROV-JSON instance
without bundles, holding the top-level statements, the core bundle's statements and the core bundle's entity with
`apv:flattenedFrom` set to the core bundle IRI. It would be validated as its own instance (PROV-CONSTRAINTS on the
union of the top level and the core). Consumers that cannot read bundles read the top level plus the core bundle
(F.1.7).

---

## E.4 Vocabulary (`apv:`) and IRIs

### E.4.1 Namespaces and PROV-JSON prefixes

| Prefix | IRI | Use |
|---|---|---|
| `apv` | `https://w3id.org/agentprov/ns#` | vocabulary terms (TBox and individuals) only, never instances |
| `x` | `https://w3id.org/agentprov/exec/<ex>#` | nodes and statements of execution `<ex>` (D7) |
| `xd` | `https://w3id.org/agentprov/exec/<ex>/` | per-execution documents: AER, SEM, bundles, conversion activities, `provenance` |
| `raw` | `https://w3id.org/agentprov/raw/` | content-addressed raw artefacts: `raw:sha256-<hex64>` |
| `sw` | `https://w3id.org/agentprov/sw/` | software agents: `sw:agentprov` (the engine, version-free, D-13), `sw:agentdojo.tracelogger.0.1.0`, `sw:agentprov-capture.0.1.0`, `sw:agentprov-backend.0.1.0` |
| `rules` | `https://w3id.org/agentprov/rules/` | rule catalogues and profiles as plans: `rules:agentprov-prov.0.1`, `rules:agentdojo.1`, `rules:agentdojo.suites.1` |
| `adprov` | `https://nickjones39.github.io/agentdojo-prov/ns#` | compatibility profile only; frozen (`prov_emit.py:17`; [audit/provenance.md §10]) |

`prov` and `xsd` MUST NOT be declared.
- `prov` is reserved by PROV-JSON, and declaring it is rejected [audit/validation.md §3.4].
- PROV-JSON's default `xsd` prefix shows the erroneous IRI noted in errata dm-1, n-1 and o-1
  [landscape/prov_semantics.md §1.1]. The round-trip tests MUST therefore assert that every datatype in the
  TriG output is under `http://www.w3.org/2001/XMLSchema#`.

The `w3id.org/agentprov` namespace is registered (user decision U-02; `DECISIONS.md` Addendum D-3). It returned 404 on
2026-10-07 [audit/provenance.md §10]; the registration, pull request `perma-id/w3id.org#6836`, was submitted with the
user's consent (D7) and merged on 2026-10-09. The redirects resolve to the `nickjones39/agentprov-ns` pages by content
negotiation (Turtle or HTML). The audit recommends minting the namespace "before any data is emitted"
[audit/provenance.md §1 item 9].
- Corpora with these IRIs MAY be produced and, since the namespace resolves, MAY be deposited (D9; Addendum D-3).
  Instance IRIs (`x`, `xd`) are identifiers and are not individually dereferenceable (`docs/ns/README.md`).
- A deposit still needs the user's explicit instruction.

### E.4.2 Instance identifiers (normative)

The instance IRI of an AER-derived node is `https://w3id.org/agentprov/exec/<ex>#<L(id)>`, where `L` maps `#` to `-`
(owner of the IRI mapping: this section; RESOLUTIONS §3.4). Percent-encoding of `#` is not used.

*Injectivity.* Local ids match `^[a-z][a-z0-9_]{0,31}$` and part ids `<id>#<k>` with decimal `k` (C.4.2), so no local
id contains `-`; the only `-` in `L(id)` is the image of the single `#`, and `L` is inverted by replacing the last
`-` with `#`. Derived names add `.` and a qualifier from a closed set, and statement names end in `.<h16>`; neither
`.` nor these suffixes occur in `L(id)` (E.1.2).

| Thing | Local name | Example IRI |
|---|---|---|
| AER-derived node | `L(id)` (E.1.2) | `https://w3id.org/agentprov/exec/ex_k2…#m3-0` |
| Derived node | `L(id).<q>` | `…#te4.out`, `…#m3-0.pre`, `…#sc1.after`, `…#mc2.model` |
| Statement (identified relation) | `<rule-name>.<h16>`, where `h16` = first 16 characters of lower-case unpadded base32 of `sha256("aprov-stmt/1\n" + dk + "\n" + rule_id + "\n" + "\n".join(argument QNames in PROV argument order) + "\n" + discriminator)` | `…#use_context.q7c2m4k9a1b3d5e6` |
| Unidentified relation (`mentionOf`, `specializationOf`, `hadMember`, `hadDictionaryMember`) | PROV-JSON key `_:<rule-name>.<h16>` (same hash) | — |
| Mention entity | `L(target).mn-<h12>`, where `h12` is the hash of (dk, annotation id or rule id) | `…#m3-0.mn-3kq0x7c2d1ab` |
| Assessment entity | `as-<h16>` (hash of dk, rule id, subject, object, claim) | `…#as-0b7t…` |
| Bundle | `xd:bundle.core.<dk>`, `xd:bundle.inf.<method-slug>.<dk>`, `xd:bundle.assess.<profile-slug>.<dk>` | `https://w3id.org/agentprov/exec/ex_k2…/bundle.core.4mq…` |
| AER, SEM | `xd:aer.<hex64>`, `xd:sem.<profile-slug>.<hex64>` | — |

Rules for these names:
1. **Slugs.** A rule id's slug replaces `.` with `-` and `@` with `-v`. For example
   `adprov.context_is_prefix@1` becomes `adprov-context_is_prefix-v1`. A method set's slug joins the sorted rule
   slugs with `--`, which no rule slug contains. A profile slug is formed the same way from its id and integer
   version (`agentdojo.suites`, 1 → `agentdojo-suites-v1`).
2. **Hash inputs** are UTF-8.
3. **Discriminator.** The discriminator is empty unless one rule emits several statements over the same
   arguments; it is then the role or index (for example `contextIndex=3`). (rule, arguments, discriminator) MUST
   be unique within a bundle, and the engine MUST fail on a collision. The baseline builder silently
   overwrote duplicate ids [audit/provenance.md §7.2].
4. **Nodes are shared, statements are not.** Node IRIs are shared by all bundles and all revisions, because they
   denote the same execution things. Statement IRIs include `dk` and are unique per bundle revision. Merging
   several revisions in one RDF store therefore never conflates two statements, which removes the baseline's
   cross-graph merging defect [audit/validation.md V13].
5. **Rule ids are strings.** `apv:rule` and `apv:basisRule` are `xsd:string` literals equal to the rule id (the
   reference without `#…`); `apv:rulePointer` carries scoped references. This departs from the QName encoding of
   [landscape/prov_semantics.md §7.2]. Rule ids contain `@` and `.`, which PROV-N local names cannot carry
   unescaped, and string equality with the AER `rule` arrays makes evidence linkage mechanical. A rule is
   dereferenced through its catalogue plan entity.

### E.4.3 Classes (outline; all are `rdfs:subClassOf` the PROV class shown)

| PROV superclass | `apv:` classes |
|---|---|
| `prov:Activity` | `ModelInvocation`, `CacheRead`, `ToolExecution`, `Decision`, `Run`, `Pass`, `AgentInvocation`, `SubagentInvocation`, `Step`, `CheckerRun`, `HarnessRuleEvaluation`, `GenericActivity`, `PolicyEvaluation`, `CaptureSession`, `Mapping`, `Annotation`, `ProvDerivation` |
| `prov:Entity` | `ExecutionDescription`; `Message` (`SystemMessage`, `UserMessage`, `AssistantMessage`, `ToolMessage`, `DeveloperMessage`, `OtherRoleMessage`; a message with requests is additionally a `prov:Collection`); `MessagePart` (`TextPart`, `ReasoningPart`, `ToolCallRequest`, `ToolResult`, `BlobPart`, `FilePart`, `UriPart`, `RefusalPart`, `OtherPart`); `Model`; `State` (`EnvironmentState`, `StoreState`, `SandboxState`); `Fixture` (`InjectionPayload`, `EnvironmentSeed`, `TaskPrompt`, `SystemPrompt`, `ToolDefinitions`, `GroundTruth`, `AttackPlan` ⊑ `prov:Plan`); `Outcome`; `GenericArtefact`; `ContextWindow` (⊑ `prov:Dictionary`; collection mode, deferred); `Gap`; `CaptureProfile`; `Assessment`; `RawSourceArtefact`; `ExecutionRecord`; `SemanticAnnotationSet`; `ExecutionProvenance`; `LegacyProjection`; `RuleCatalogue` and `SemanticsProfile` (⊑ `prov:Plan`) |
| `prov:Bundle` | `CoreBundle`, `InferenceBundle`, `AssessmentBundle` |
| `prov:Agent` | `AgentSystem`, `ModelService`, `ToolRuntime`, `EnvironmentActor`, `User`, `SimulatedUser`, `Attacker`, `Judge`, `Defence`, `Harness`, `Benchmark`, `Adapter`, `ProvEngine`; role classes `Planner`, `Generator` |

AER `actor.kind` (closed, with the `other` escape; C.3.2) maps to agent classes as follows. `planner` and `generator`
are not kinds: they are `role` values, which add a role class (R-02).

| `actor.kind` | Agent types |
|---|---|
| `llm_agent` | `apv:AgentSystem` + `prov:SoftwareAgent` |
| `user` | `apv:User` + `prov:Person` |
| `simulated_user` | `apv:SimulatedUser` + `prov:SoftwareAgent` |
| `attacker` | `apv:Attacker` (no PROV subtype: whether it is a person or an organisation is unknown) |
| `defense` | `apv:Defence` + `prov:SoftwareAgent` |
| `judge` | `apv:Judge` + `prov:SoftwareAgent` |
| `tool_runtime` | `apv:ToolRuntime` + `prov:SoftwareAgent` |
| `environment` | `apv:EnvironmentActor` + `prov:SoftwareAgent` |
| `harness` | `apv:Harness` + `prov:SoftwareAgent` |
| `benchmark` | `apv:Benchmark` + `prov:SoftwareAgent` |
| `other` | `prov:Agent` + `apv:subtype "<ns>.<name>"` |

| `actor.role` | Additional type |
|---|---|
| `planner` | `apv:Planner` |
| `generator` | `apv:Generator` |
| any other value | none; the value is kept in `apv:actorRole` |

For alignment, `apv:ModelInvocation` and `apv:ToolExecution` correspond to PROV-AGENT's `AIModelInvocation` and
`AgentTool` respectively.
- The mapping is documented with `skos:closeMatch` in the ontology.
- The Flowcept ontology file MUST NOT be imported: it failed to parse at commit `c000b10e`
  [landscape/prov_semantics.md §6; §13.2].

### E.4.4 Properties (outline)

- **Evidence.** All are used on nodes and on qualified relations (E.1.5 item 6):
  - `apv:evidenceClass`, `apv:rule`, `apv:basisRule`, `apv:rulePointer`, `apv:sourcePointer`, `apv:attestedBy`;
  - `apv:assumption`, `apv:adapterAssumption` (apv 0.2.0, D-501), `apv:premise`, `apv:viaEntity`;
  - `apv:method`, `apv:confidence`, `apv:threshold`;
  - `apv:derivedAttribute`, `apv:afterEvidenceClass`.
- **Status.** Fixed properties on nodes, with values from the status individuals (E.4.5):
  - `apv:startTimeStatus`, `apv:endTimeStatus`, `apv:contextStatus`, `apv:outputStatus`;
  - `apv:requestStatus`, `apv:responseStatus`, `apv:usageStatus`, `apv:paramsStatus`, `apv:finishReasonStatus`;
  - `apv:requestedModelStatus`, `apv:servedModelStatus`;
  - `apv:requestedArgsStatus`, `apv:effectiveArgsStatus`;
  - `apv:contentStatus`, `apv:providerCallIdStatus`, `apv:argsRawStatus`;
  - `apv:indexStatus`, `apv:orderStatus`, `apv:dispatchStatus`.

  `apv:Gap` uses `apv:about`, `apv:property`, `apv:status` and `apv:reason`.
- **Recorded-null status** (apv 0.2.0, D-500). For every data property `<p>` that a node rule fills from an AER field
  (`opt()` in `prov/rules/nodes.py`), the object property `apv:<p>Status` (range `apv:EpistemicStatus`) states an
  asserted JSON `null` as `apv:RecordedNull`, and `<p>` is then omitted (E.10 item 5). Five of them are the `unk`
  status properties above (`apv:finishReasonStatus`, `apv:requestedModelStatus`, `apv:servedModelStatus`,
  `apv:providerCallIdStatus`, `apv:indexStatus`); 0.2.0 adds the other 26:
  - `apv:activityStatusStatus`, `apv:activityTypeStatus`, `apv:actorRoleStatus`, `apv:artefactTypeStatus`;
  - `apv:attackIdStatus`, `apv:attackTargetIdStatus`, `apv:benchmarkStatus`, `apv:callRoleStatus`;
  - `apv:defenceIdStatus`, `apv:environmentStatus`, `apv:errorStatus`, `apv:mediaTypeStatus`;
  - `apv:nameStatus`, `apv:outcomeNameStatus`, `apv:outcomeValueStatus`, `apv:providerStatus`;
  - `apv:reasonStatus`, `apv:responseIdStatus`, `apv:scopeStatusStatus`, `apv:scoredStatus`;
  - `apv:subtypeStatus`, `apv:taskIdStatus`, `apv:toolNameStatus`, `apv:truncatedStatus`;
  - `apv:vectorStatus`, `apv:versionStatus`.
- **Structure and order.**
  - `apv:partOf`, `apv:partIndex`, `apv:partCount`, `apv:thread`, `apv:contextIndex`, `apv:index`, `apv:scored`;
  - `apv:afterCausal`, `apv:afterTime`, `apv:afterPos`, `apv:afterProto`;
  - `apv:durationSeconds`, `apv:startTimeLexical`, `apv:endTimeLexical`.
- **Content and attributes.**
  - Messages and parts: `apv:messageRole`, `apv:contentSha256`, `apv:contentLength` (Unicode scalar values),
    `apv:text` (only with `emit_content`).
  - Tool calls and execution: `apv:toolName`, `apv:args`, `apv:argsEffective`, `apv:argsRawSha256`,
    `apv:providerCallId`, `apv:error`, `apv:exception`, `apv:execStatus`, `apv:dispatchStatus`.
  - Model calls: `apv:callStatus`, `apv:callRole`, `apv:retryOf`, `apv:finishReason`, `apv:usage`,
    `apv:paramsConfigured`, `apv:paramsTransmitted`, `apv:requestBlob`, `apv:responseBlob`, `apv:responseId`,
    `apv:sentTransform`, `apv:asSentSha256`.
  - Decisions: `apv:verdict`, `apv:reason`, `apv:decisionSubject`.
  - State: `apv:stateSha256`, `apv:patchSha256`, `apv:truncated`.
  - Fixtures: `apv:vector`.
  - Outcomes: `apv:outcomeName`, `apv:outcomeValue`, `apv:outcomeOrigin`; in assessment mentions only:
    `apv:outcomeClaim`, `apv:outcomeHolds`, `apv:outcomeScore`, `apv:outcomeScale`.
  - Generic kinds: `apv:activityType`, `apv:activityStatus`, `apv:artefactType`, `apv:inputIndex`; `prov:label`.
  - Models and actors: `apv:requestedModel`, `apv:servedModel`, `apv:provider`, `apv:name`, `apv:actorRole`,
    `apv:version`.
  - Escapes: `apv:subtype` (the `<ns>.<name>` of an `other` enum value, R-38).
  - Execution description: `apv:executionId`, `apv:mode`, `apv:executionUnit`, `apv:benchmark`, `apv:environment`,
    `apv:taskId`, `apv:attackId`, `apv:attackTargetId`, `apv:defenceId`, `apv:instrumentation`.
- **Conversion.**
  - Artefacts: `apv:sha256`, `apv:bytes`, `apv:mediaType`, `apv:artefactRole`, `apv:provPrimary`,
    `apv:originKind`, `apv:originRepository`, `apv:originRevision`, `apv:originPath`, `apv:originBlob`,
    `apv:originContainer`, `apv:originLabel`.
  - Records: `apv:aerVersion`, `apv:semVersion`, `apv:sourceKey`, `apv:accounting`, `apv:issue`.
  - Catalogues and software: `apv:catalogueId`, `apv:softwareName`, `apv:softwareVersion`.
  - Derivation: `apv:derivationKey`, `apv:contextEncoding`, `apv:profileOptions`, `apv:vocabularyVersion`,
    `apv:profile`, `apv:status` (also on compat entities), `apv:flattenedFrom`, `apv:corpusVersion`.
- **Capture profile.** `apv:provides`, `apv:notProvided`, `apv:notObservable`.
- **Assessment.**
  - `apv:subject`, `apv:object`, `apv:claim`, `apv:policy`;
  - `apv:integrity`, `apv:securityRole`, `apv:sourceChannel`, `apv:declaredSender`, `apv:annotationType`,
    `apv:annotationValue`, `apv:markerStatus`;
  - `apv:spanStart`, `apv:spanEnd` (offsets in Unicode scalar values into the part's text, C.14.2);
  - `apv:matchedArg`, `apv:authorName`, `apv:annotationId`.

### E.4.5 Closed individual lists

Each list is closed *per ontology version* (`apv` `0.2.0`; 0.2.0 adds no individual to 0.1.0's lists). A validator checks membership against the version
declared by the document (E.4.6). Assumptions additionally admit adapter-declared `<ns>:<Name>` terms (F.1.5), as
strings on `apv:adapterAssumption`, never as `apv:assumption` values (E.10 item 11).

**Evidence classes.** `apv:Observed`, `apv:Derived`, `apv:Inferred`. These correspond to AER `ev` values `O`,
`D` and `I` (F.1.1).

**Attesting parties (AER `by`, or the party of an `evf` value `O:<party>`).**
- `apv:ByCapture` (`capture`);
- `apv:BySource` (`source`);
- `apv:ByProvider` (`provider`);
- `apv:ByBenchmark` (`benchmark`);
- `apv:ByConfig` (`config`);
- `apv:ByReplay` (`replay`).

These are defined in F.1.3.

**Epistemic statuses.** These are the seven AER `unk` reasons one-to-one, plus two others (R-08). There is no
many-to-one status and no catch-all "unknown" status; a pointer without a fixed property becomes an `apv:Gap`.

| Status | AER `unk` reason | Meaning |
|---|---|---|
| `apv:NotRecorded` | `not_recorded` | the source format or instrumentation has no slot for it |
| `apv:Lost` | `lost` | the source had it but discarded it (earlier passes of last-pass-only logs; discarded-reply content) |
| `apv:Overwritten` | `overwritten` | captured only after an in-place transformation destroyed the original (PI-detector placeholder, DRIFT isolation, AgentDyn detector redactions) |
| `apv:Withheld` | `withheld` | deliberately not exposed (provider-hidden reasoning; secrets redacted by capture) |
| `apv:Ambiguous` | `ambiguous` | a value is present but unusable (`""` call ids, duplicate ids, naive local timestamps) |
| `apv:NotCaptured` | `not_captured` | live capture failed to record something it should have, or the context held content the record does not (§13 G2) |
| `apv:NotApplicable` | `not_applicable` | the property cannot exist for this record |
| `apv:RecordedNull` | — (a source-recorded `null` kept with `ev: O`) | the source positively recorded null or empty; for example assistant `content: null` beside a tool call, which keeps null distinct from `""` [landscape/trace_formats.md §6.3]. It is stated on `apv:contentStatus` or on the `apv:<p>Status` sibling of the data property `<p>`, never as the object of a data property (E.10 item 5) |
| `apv:NotObservable` | — (capture profile only) | not observable by black-box capture in principle; it can only be estimated, and estimates belong in inference bundles |

The fixed status-property map for `unk` pointers (`aprov.status@1`) is as follows. Any other pointer becomes an
`apv:Gap`.

| `unk` pointer | Status property |
|---|---|
| `/t` | `apv:startTimeStatus` and `apv:endTimeStatus` |
| `/t/start` | `apv:startTimeStatus` |
| `/t/end` | `apv:endTimeStatus` |
| `/input` | `apv:contextStatus` |
| `/request` | `apv:requestStatus` |
| `/response` | `apv:responseStatus` |
| `/usage` | `apv:usageStatus` |
| `/params…` | `apv:paramsStatus` |
| `/finish_reason` | `apv:finishReasonStatus` |
| `/model/requested` | `apv:requestedModelStatus` |
| `/model/served`, `/served_model` | `apv:servedModelStatus` |
| `/args` (on `tool_execution`) | `apv:requestedArgsStatus` |
| `/args_effective` | `apv:effectiveArgsStatus` |
| `/parts/<k>/text` and `/parts/<k>/value` | `apv:contentStatus` on the part |
| `/parts/<k>/provider_call_id` | `apv:providerCallIdStatus` |
| `/parts/<k>/args_raw` | `apv:argsRawStatus` |
| `/index` | `apv:indexStatus` |
| `/after` | `apv:orderStatus` |
| `/original` (on `decision`) | `apv:contentStatus` on the `.out` or `.pre` entity |

`apv:outputStatus apv:Lost` is set by `aprov.n_model_call@1` on calls emitted under C.7.4 (there is no output field
in `aer/0.1`: outputs are the messages that name the call in `generated_by`).

**Assumptions (apv core list, unchanged since 0.1.0; each use MUST cite code, F.1.5).** Adapter-declared
`<ns>:<Name>` assumptions with the same verification shape are also admitted (AD-05(b)(i)); they are stated on
`apv:adapterAssumption` (E.10 item 11).

| Individual | Definition | Typical use | Known not to hold for |
|---|---|---|---|
| `apv:FullContextResend` | Every model call of an actor sends the whole current message list of its pass, in order, with no pruning, summarising or re-insertion | adapter rule for `/input` → `aprov.use_context@1` | `tool_filter`, `repeat_user_prompt`, PI detector, DRIFT (no `SystemMessage` element) [landscape/trace_formats.md §4 item 3; audit/capture.md §9.6] |
| `apv:OneCallPerAssistantMessage` | Each assistant message of an actor is the output of exactly one model call of that actor | existence of `model_call` (adapter) | defended pipelines with auxiliary calls; retries (live capture records them) |
| `apv:AutoExecution` | Every dispatched tool call is dispatched by the runtime without confirmation, on behalf of the requester | `aprov.start_tool@1`, `aprov.assoc_tool@1` | approval flows (Inspect `ApprovalEvent`; `tool_execution.authorised_by`, `aprov.authorise@1`) |
| `apv:SequentialToolExecution` | The calls of one request execute in request order on a shared environment | `after` edges with `b: pos` (adapter) | parallel executors |
| `apv:FreshMessagesPerPass` | A new pass starts from fresh messages; the environment carries over | pass scopes; context boundaries | — |
| `apv:RerunOnEmptyReply` | A pass whose final message content is null (an empty string or list does not count) triggers another pass; at most 3 passes in total in agentdojo 0.1.35 (§13 E6) | `aprov.rerun@1` | — |
| `apv:LastPassOnlyLogging` | A log holds only the message list of the final pass of its cell | `agentdojo.log_holds_last_pass@1` (earlier attempts `unk /index lost`; seal issue `earlier_attempts_unobservable`) | live capture; transcript/v1 with `discarded_attempts` |
| `apv:CheckerUsesOutput` | The task's checker reads the final model output text | `aprov.outcome@1` (`apv:CheckedOutput`) | checkers declared otherwise; per task, verified only for audited checkers |
| `apv:CheckerUsesPreState` | The task's checker reads the pre-environment (deep copy taken before the first pass) | `aprov.outcome@1` (`apv:CheckedPreState`) | per task |
| `apv:CheckerUsesPostState` | The task's checker reads the post-environment | `aprov.outcome@1` (`apv:CheckedState`) | per task |
| `apv:CheckerUsesCallTrace` | The task's checker reads the tool calls of the scored attempt only (not those of discarded passes, whose effects reach it only through the post-state) | `aprov.outcome@1` (`apv:CheckedCallTrace`) | per task; checkers that count proposed calls are covered by this assumption, not excluded by it (AgentDojo issues #168, #218 [sources/agentdojo.md §6]) |
| `apv:AgentActsForUser` | The agent system acts on behalf of the (simulated) user | `actor.on_behalf_of` → `aprov.deleg_user@1` | STAC (the "user" turns come from the attacker) |
| `apv:ScriptedUser` | User turns are produced by the benchmark, not by a person | `aprov.attr_message@1` | human-in-the-loop sources |
| `apv:InjectionPlacement` | The benchmark places each registered payload at its vector in the initial environment | `aprov.inj_placement@1` | — |
| `apv:SingleModelPerActor` | All model calls of an actor are served by the actor's configured model | `aprov.use_model@1`, only when `model_call.served_model` is absent | provider routing that changes the served model per call |
| `apv:EnvironmentCarriedOver` | The harness carries the same environment object into the next pass (it does not rebuild an identical one); verified per harness | `aprov.env_pass@1` carry-over | harnesses that rebuild the environment per attempt (PROV-14) |
| `apv:EnvironmentDigestCanonical` | Environment digests are over a canonical serialisation of the whole state, so equal digests mean equal states | the digest consistency check of `aprov.env_pass@1` | — |
| `apv:InstrumentationUntruncated` | An instrumentation that records model input (for example OTel GenAI `gen_ai.input.messages`) neither filters nor truncates it | context membership from such a source (O only when the setting is itself recorded) | instrumentations configured to filter or truncate (§13 E12) |
| `apv:ReplayFaithful` | Replaying recorded calls in a fresh environment reproduces the original environment's behaviour | assessments relating replay outcomes to originals only; never core | logging-era checker drift [audit/legacy_replay.md §1 item 11] |

The four checker-input assumptions replace the single final-state checker assumption of the first draft (R-20,
§13 E5). They are declared per task; agentdojo 0.1.35 passes all four inputs to its checkers
(`task_suite.py` l.281–312, 374, 383, 392, 399) [landscape/prov_semantics.md §13 E5].

**Other closed lists.**

| List | Individuals |
|---|---|
| Roles (`prov:hadRole`) | `apv:ContextMessage`, `apv:ModelInput`, `apv:ToolDefinitionsInput`, `apv:CallRequestInput`, `apv:AgentSystemRole`, `apv:InferenceProvider`, `apv:ExecutingRuntime`, `apv:DefenceRole`, `apv:DeciderRole`, `apv:DecisionSubject`, `apv:InitialState`, `apv:CheckedOutput`, `apv:CheckedPreState`, `apv:CheckedState`, `apv:CheckedCallTrace`, `apv:CheckedInput`, `apv:CheckerRole`, `apv:RuleInput`, `apv:ActivityInput`, `apv:PerformerRole`, `apv:MethodProvider`, `apv:ContextWindowRole` (collection mode, deferred) |
| Sent transforms | `apv:ErrorSubstitution`, `apv:RoleRewrite`, `apv:ReasoningPassback`, `apv:Formatting`, `apv:Truncation` (in-request only), `apv:OtherTransform`. A defence is never a sent transform (A5) |
| Call statuses | `apv:Kept`, `apv:Discarded`, `apv:Error`, `apv:Cached` |
| Execution statuses | `apv:Ok`, `apv:Error`, `apv:Invalid` |
| Dispatch statuses | `apv:NotDispatched`, `apv:Denied` |
| Outcome origins | `apv:OriginChecker`, `apv:OriginHarnessDefault`, `apv:OriginHarnessRule`, `apv:OriginRecomputed` |
| Derivation types | `apv:DefenceRedaction`, `apv:DefenceModification`, `apv:InjectionPlacementDerivation` (with `prov:Revision` for states) |
| Verdicts | `apv:VerdictAllow`, `apv:VerdictDeny`, `apv:VerdictModify`, `apv:VerdictRedact`, `apv:VerdictEscalate`, `apv:VerdictTerminate`, `apv:VerdictOther` (+ `apv:subtype`) |
| Integrity (three-valued, D6) | `apv:Trusted`, `apv:Untrusted`, `apv:IntegrityUnknown` |
| Security roles (multi-class, SEM-7 and AR-6) | `apv:WriteSink`, `apv:SendSink`, `apv:ExecuteSink`, `apv:EgressRead`, `apv:ResponseSink`, `apv:ContentSource`, `apv:Endorser`, `apv:Neutral`, `apv:RoleUnknown` |
| Marker statuses | `apv:Ambiguous` (reuses the epistemic status); `present` gives the claim itself; `absent` and `gap` give no statement (E.7.3) |
| Assessment claims | `apv:ExposedTo`, `apv:PotentiallyInfluencedBy`, `apv:ContainsPayload`, `apv:QuotesAuthoredContent`, `apv:SentTransformed`, `apv:Labelled`, `apv:OrderedAfter` |
| Profile statuses | `apv:RegressionOracle` (the `adprov-v2.3-compat` output) |

**Capability individuals (capture profile).**
- `apv:CapRequestPayload`, `apv:CapToolDefinitions`, `apv:CapServedModel`, `apv:CapParams`, `apv:CapUsage`;
- `apv:CapModelCallTimes`, `apv:CapToolTimes`;
- `apv:CapReasoning`, `apv:CapDiscardedReplies`, `apv:CapEarlierPasses`;
- `apv:CapEnvironmentState`, `apv:CapPerCallState`;
- `apv:CapPreDefenceOutput`, `apv:CapRequestedArgs`;
- `apv:CapOutcome`, `apv:CapSystemPrompt`, `apv:CapAgentIdentity`;
- `apv:CapContextAttribution` (always `apv:notObservable` for black-box capture).

### E.4.6 Ontology versioning and publication

1. **Files and IRIs.**
   - Ontology file: `src/agentprov/vocab/apv-0.2.ttl`; a copy is published as `docs/ns/apv-0.2.ttl`
     (`tools/sync_ns.py`). Earlier releases stay published unchanged beside it: `docs/ns/apv-0.1.ttl` is apv 0.1.0.
   - Ontology IRI: `https://w3id.org/agentprov/ns` (registered at w3id.org, U-02; E.4.1).
   - `owl:versionIRI`: `https://w3id.org/agentprov/ns/0.2.0`; `owl:priorVersion` and `owl:backwardCompatibleWith`
     name `https://w3id.org/agentprov/ns/0.1.0`.
   - `owl:versionInfo`: `"0.2.0"`. The version string is `0.2.0` everywhere; "apv 0.2.0" is the axis label in prose
     (R-10).
   - **0.2.0** (2026-10-14, minor, additive) adds the recorded-null status properties `apv:<p>Status` (D-500, E.4.4)
     and `apv:adapterAssumption` (D-501, E.10 item 11).
     No 0.1.0 term changed meaning or was removed. The `aprov` catalogue's `vocabulary` is `0.2.0`; the PROV spec
     stays `agentprov-prov/0.1`.

   Term IRIs do not embed versions. Every document states the ontology version as `apv:vocabularyVersion` on the
   derive activity.
2. **Semantic versioning.**
   - Patch versions are for documentation only.
   - Minor versions add terms, including new individuals in a closed list.
   - Major versions change meaning or remove terms.

   Once 0.1.0 is released, terms are never deleted; they are marked `owl:deprecated true`. The baseline's
   `adprov.ttl` stayed at `owl:versionInfo "1.0"` through several term additions and had no `owl:versionIRI`
   [audit/provenance.md §9]. That MUST NOT recur.
3. **No instances in the vocabulary.** The vocabulary declares classes, properties and individuals only. SHACL
   shapes for profile rules live in `src/agentprov/validate/shapes/` and MUST be declared there
   [audit/validation.md §3.8] (R-50).
4. **Legacy mapping.** `apv-adprov-map-0.1.ttl` relates `adprov:` terms to `apv:` terms with `skos:closeMatch`
   and an `rdfs:comment` on how the semantics changed (E.8.4). It MUST NOT use `owl:equivalentProperty` or
   `rdfs:subPropertyOf` where the semantics changed. For example, `adprov:integrity` sat on core nodes, while
   `apv:integrity` sits on assessment mentions. The audit's suggestion of equivalence
   [audit/provenance.md §10 item 5] is refined accordingly.

---

## E.5 Encoding: qualified relations, prov-library caveats, deterministic serialisation

### E.5.1 Qualified relations carry the evidence

1. **All influence relations are identified.** Every influence relation the engine emits MUST have an
   identifier (E.4.2). With identifiers, the `prov` library serialises it in qualified form, and its attributes
   become triples on the qualified node: `prov:Usage`, `prov:Generation`, `prov:Communication`,
   `prov:Association`, `prov:Delegation`, `prov:Start`, `prov:Attribution`, `prov:Invalidation`,
   `prov:Derivation` and its subclasses. This was verified with `prov` 3.2.2 and rdflib 7.6.0
   [landscape/prov_semantics.md §7.4 item 2].
2. **Qualification annotates; it does not hedge.** PROV-O tells consumers to treat the qualified form as implying
   the unqualified one [landscape/prov_semantics.md §3.17]. Hence the bundles (E.3).
3. **Non-influence relations carry no attributes.** `specializationOf`, `alternateOf`, `hadMember`,
   `mentionOf` and `hadDictionaryMember` have no id. The engine uses them only where the class of the containing
   bundle is enough:
   - `specializationOf` at the top level;
   - `hadMember` for tool-call requests (`aprov.member_request@1`), placed in the bundle of the request part; the
     evidence lives on the request part [landscape/prov_semantics.md §13 E1];
   - `mentionOf` in inference and assessment bundles (entities only);
   - dictionary membership in collection mode (deferred).

   `mentionOf` round-trips as `prov:mentionOf` plus `prov:asInBundle` [landscape/prov_semantics.md §7.4].

### E.5.2 prov-library caveats and the engineering response

| # | Caveat (prov 3.2.2 and rdflib 7.6.0 unless stated) | Evidence | Response (normative) |
|---|---|---|---|
| C1 | For identified relations, the library writes only the qualified PROV-O form: no `prov:used`, `prov:wasGeneratedBy`, `prov:wasInformedBy`, `prov:wasAssociatedWith`, `prov:wasDerivedFrom`, `prov:wasQuotedFrom` or `prov:hadPrimarySource` triples. Typed derivations become `prov:qualifiedPrimarySource`, `prov:qualifiedQuotation` and similar only | [landscape/prov_semantics.md §7.4 item 3; audit/validation.md §3.9, §6.4] | AgentPROV generates an *unqualified layer* (E.5.4) and adds it to the same named graph, so plain SPARQL consumers see `prov:used` |
| C2 | Re-importing a graph with the unqualified triples materialised creates duplicate unidentified relations: 37 records become 48 and model equality fails | [landscape/prov_semantics.md §7.4 item 4; prov_semantics_evidence/rt_test3.out] | PROV-JSON is canonical. The round-trip check removes exactly the generated unqualified layer before re-import (E.5.5) |
| C3 | Times are written back through `isoformat()`, so only exact `isoformat()` strings survive the round trip; `Z`, `.5` and `.000+00:00` do not | `build_prov.py:86` (`_timestamp`); [audit/provenance.md §7.1.2; docs/capture_spec.md §5.3 item 4] | E.5.3 item 7. The predicate lives in `agentprov.prov.serialise.time` and is tied to the pinned library version [audit/validation.md §9] |
| C4 | Integers become `xsd:int`; rdflib emits a `DeprecationWarning` in the Turtle path (318 in one run) | [audit/validation.md §3.5] | Pin `prov` and `rdflib` in `uv.lock`; record the versions in the manifest and in every validation report; compare typed literals (datatype and lexical form) |
| C5 | The `xsd` namespace erratum | [landscape/prov_semantics.md §1.1] | E.4.1 |
| C6 | `mentionOf` is supported by `prov` 3.2.2, but it is an experimental W3C Note construct; support in other toolchains has not been checked | [landscape/prov_semantics.md §12 item 3; §13.6 item 3] | Used only in inference and assessment bundles, and only on entities; the core never depends on it |
| C7 | PROV-Dictionary statements (`hadDictionaryMember`, `derivedByInsertionFrom`) have not been tested with `prov` 3.2.2 in any report | none | Collection mode is deferred (E.6.2; AD-10 row 14) |
| C9 | On decode, `ProvRDFSerializer` rewrites predicates by *substring* match (`if needle in pred`, `prov/serializers/provrdf.py`): any predicate on a `prov:Delegation` node whose IRI contains `agent` is read as `prov:responsible` (likewise `activity`/`entity` on communications, starts, ends and derivations). Every `apv:` IRI contains `agentprov`, so a qualified delegation carrying an `apv:` attribute cannot be decoded | observed 2026-10-08 on golden C05 (`aprov.deleg_user@1`) | The round trip of E.5.5 runs under a bijective renaming of every declared namespace IRI to a neutral surrogate, which preserves model equality; the completeness check encodes only and uses the real namespaces. The outcome's `reason` records the renaming, and a negative-control test keeps the defect visible. Reporting it upstream is deferred indefinitely (user decision, 2026-10-08) |
| C8 | The library drops some losses identically in both directions, so `round_trip` alone misses them (the `"0"` times passed round-trip on 17,265 graphs) | [docs/capture_spec.md §8; audit/validation.md §3.6] | The typed, bidirectional completeness check is mandatory (E.5.5) |

### E.5.3 Canonical PROV-JSON (normative)

1. **The writer.** The engine builds the document as a Python mapping and writes it with AgentPROV's own writer:
   RFC 8785 JCS bytes, UTF-8, no byte-order mark, no trailing newline, using the `rfc8785` core dependency (D10).
   It MUST NOT be written through `ProvDocument.serialize`. The file digest is the sha256 of these bytes. JCS
   fixes key order (lexicographic), whitespace and number form, so "deterministic key order" (D7) holds by
   construction.
2. **Top-level members.**
   - The only top-level members are `prefix`, element sections, relation sections and `bundle`.
   - Empty sections are omitted, and no non-standard top-level keys are allowed [audit/validation.md §8 item 7].
   - Bundles MUST NOT nest and MUST NOT carry `prefix`.
3. **Attribute value forms.**
   - QName values: `{"$": "<qname>", "type": "prov:QUALIFIED_NAME"}`.
   - `xsd:double`: `{"$": "<shortest round-trip decimal>", "type": "xsd:double"}`.
   - Integers, booleans and strings: native JSON.

   These are the forms verified in `evq_sample.json` [landscape/prov_semantics.md §7.3].
4. **Multi-valued attributes** are JSON arrays sorted by the JCS bytes of each element, with duplicates removed.
   A single value is a scalar, not a one-element array.
5. **Strings** keep their content byte for byte; there is no Unicode normalisation (D2).
6. **Numbers** stay within I-JSON (D2).
7. **Times.** Only activities carry `prov:startTime` and `prov:endTime`, taken from AER `t.start` and `t.end`
   (C.8.3).
   - A time is emitted only when all of the following hold:
     1. it is present and not in `unk`, and its class is O or D: an inferred time is never a PROV time (D-28
        addendum). An I-class `t.start` or `t.end` gives no attribute at all, neither the PROV time nor its lexical
        form, and the derivation report discloses it (`inferred_time_omitted`). The AER keeps the value and its
        reading;
     2. its clock is wall-clock UTC;
     3. it parses as an RFC 3339 value with an offset;
     4. its fraction has at most 6 digits.
   - It is then emitted as `datetime.isoformat()` of the parsed value, with offset `+00:00`. This is a lexical
     change only; the verbatim value stays in AER `t.raw`.
   - A time that fails these conditions is emitted verbatim as `apv:startTimeLexical` or `apv:endTimeLexical`
     (`xsd:string`), and `prov:startTime` or `prov:endTime` is omitted.
   - Naive local times (`t.start_naive`, `t.end_naive`) are never emitted as PROV times. An example is AgentDojo's
     `evaluation_timestamp` [sources/agentdojo.md §7.1; audit/legacy_replay.md §4].
   - Relation times MUST NOT be emitted in `agentprov-prov/0.1` (Challenge 1(e), accepted).

### E.5.4 Canonical TriG and the unqualified layer (normative; produced on demand)

TriG is not stored or hashed per execution in a corpus (AD-10 row 3). It is produced on demand by
`agentprov derive --trig DIR`, outside the sealed tree, by `agentprov.prov.serialise.trig.to_trig`. When produced, it
MUST follow these rules. Its triple set is read through the same encode and parse as the round-trip check of E.5.5:
`agentprov.prov.serialise.nquads` (the `prov` encoder, rdflib's N-Quads writer and parser; D-131), so the path TriG is
produced from is the path tier 4 checks per execution.

1. **The triple set** is the `prov`-library PROV-O image of the canonical PROV-JSON, plus the unqualified layer.
   The unqualified layer has one triple per identified relation, using the *most specific* PROV-O property:

   | Relation (PROV-JSON section and `prov:type`) | Unqualified property |
   |---|---|
   | `used` | `prov:used` |
   | `wasGeneratedBy` | `prov:wasGeneratedBy` |
   | `wasInformedBy` | `prov:wasInformedBy` |
   | `wasAssociatedWith` | `prov:wasAssociatedWith` |
   | `actedOnBehalfOf` | `prov:actedOnBehalfOf` |
   | `wasStartedBy` | `prov:wasStartedBy` |
   | `wasAttributedTo` | `prov:wasAttributedTo` |
   | `wasInvalidatedBy` | `prov:wasInvalidatedBy` |
   | `wasDerivedFrom` with `prov:Revision` | `prov:wasRevisionOf` |
   | `wasDerivedFrom` with `prov:Quotation` | `prov:wasQuotedFrom` |
   | `wasDerivedFrom` with `prov:PrimarySource` | `prov:hadPrimarySource` |
   | any other `wasDerivedFrom` | `prov:wasDerivedFrom` |

   The layer goes into the named graph of the statement's bundle, or the default graph for top-level statements.
2. **Graphs.** The default graph holds the top level. There is one named graph per bundle, named by the bundle
   IRI [landscape/prov_semantics.md §7.4 item 1].
3. **Writer.** AgentPROV's own writer, not rdflib's serialiser:
   - no `@prefix` block, and full IRIs throughout;
   - the default graph first, as `{ … }`, then each named graph as `<G> { … }`, with graphs ordered by IRI;
   - inside each graph, one triple per line in N-Triples term syntax, ordered by the code points of the line;
   - literals use canonical N-Triples escaping;
   - UTF-8, LF line endings, and a final newline.
4. **No blank nodes.** The result MUST contain no blank nodes. If the library emits one, the derivation fails.
   Without blank nodes, sorted lines are a canonical form, and the RDF Dataset Canonicalization (RDFC-1.0)
   algorithm is not needed.
5. **Digest.** When TriG is produced, its digest is reported together with the `prov` and `rdflib` versions; it is
   not part of the corpus digest chain. The rdflib path is N-Quads write and parse (D-131; rdflib's TriG write and
   parse before). The two give the same bytes on every golden and benchmark document; they differ only on an IRI with
   a raw line break, which N-Quads rejects (`prov.trig.invalid`) and the tier-4 structure check rejects first
   (`pv.prov_structure.qname`).

### E.5.5 Round-trip and completeness obligations (for the validation section)

The provenance specification requires D8 tier 4 to implement the following checks over the PROV output.
- **Round trip.** PROV-JSON → `ProvDocument` → PROV-O (N-Quads without the unqualified layer; TriG before D-89
  step 2) → `ProvDocument` gives a model *equal* to the original. Each named graph is isomorphic across two
  serialisations; with no blank nodes this is equality of their N-Quads line sets.
- **Completeness.** The completeness check is *typed* and *bidirectional*, and covers every section and every
  prefix:
  - every `prov:`, `apv:` and other declared-prefix attribute in the JSON appears in the RDF with the same
    datatype and lexical form;
  - every RDF triple about a node or qualified-relation resource is explained by the JSON or by the unqualified
    layer.

  This generalises the baseline check, which was lexical, one-way and blind to unknown sections
  [audit/validation.md §3.6, V2, V3].
- **Unqualified layer.** The layer equals exactly the set regenerated from the qualified nodes.
- **Structural checks (R-21).** No `used` object is an activity; every `mentionOf` supra and infra is declared as an
  entity; the core declares every node it references; every `apv:sourcePointer` resolves under RFC 6901.
- **Skipped checks** count as failures in release mode (D8).
- **Reuse (D-550).** The outcome of the round trip, the completeness check and the datatype check depends only on the
  PROV-JSON bytes, the validator's code, the `prov` and `rdflib` builds, the Python build and the round-trip options.
  A completed outcome may therefore be reused from a local cache keyed by all of them (N.2.5 item 9). Release
  validation recomputes every round trip and compares it with the cache.

---

## E.6 Context encodings and scale

### E.6.1 `members` (the v0.1 encoding)

`aprov.use_context@1` emits one qualified usage per (invocation, context member). This is the only encoding in
which member usage is *asserted*. It is therefore the only encoding in which the `tool_exec → llm`
communications follow by Inference 6. It is the only encoding in v0.1 (AD-10 row 14); the AgentDojo-family profiles
and the Inspect profile use it.

*Evidence: measured volume.* The count assumes `apv:FullContextResend` in every pipeline. The method is
[EF_evidence/ctx_volume.py], which counts, per assistant turn, the earlier messages of its pass.

| Corpus | Invocations (assistant turns) | Context usages | Median per trace | p99 | Max per trace | v2.3 `used` |
|---|---|---|---|---|---|---|
| released (17,664 traces) | 64,897 | 437,732 | 12 | 182 | 435 | 121,496 |
| converted (18,027 traces) | 73,551 | 511,794 | 20 | 240 | 707 | 111,499 |

The v2.3 `used` counts are from [audit/provenance.md §4.1].

*Placement after AD-05.* Released v1 context membership is INFERRED, so the 437,732 released context usages, and the
communications whose witnesses need them, lie in the inference bundle `inf.adprov-context_is_prefix-v1`, not in the
core. With the Inference 6 closure the measured witness counts for a released execution are:
- `llm → tool`: 64,781 (request witnesses; core, DERIVED where the call↔result link is DERIVED);
- `tool → llm`: 176,449 (inference bundle);
- `llm → llm`: 131,489 (inference bundle).

*Estimate of the total.* Add to these:
- about 567,000 usages (context usages, plus one request usage and one model usage per call);
- about 325,000 generations (assistant messages and their parts, tool messages and results);
- about 130,000 associations, about 65,000 delegations and about 65,000 starts;
- attributions and outcome statements.

Core and inference bundle together then hold about 1.6 million identified relations for the released corpus,
against 323,691 in v2.3: about five times as many. The split between core and inference bundle after AD-05:
recompute (phase 13). The baseline's `round_trip` costs about 0.4 ms per relation [audit/validation.md §6.5]. A
full-corpus check therefore costs about five times the baseline's 89 s full pass on 10 workers
[baseline/BASELINE.md §6]. That is minutes, not hours.

This is an order-of-magnitude estimate built from measured components, not a measured total.

### E.6.2 `collection` (deferred)

Collection mode is deferred (AD-10 row 14), together with the AER delta-form input, which `aer/0.1` does not have.
The design is kept for long-horizon sources:

1. **Encoding.**
   - For each invocation, the engine would emit `entity(x:L(mc).ctx, [prov:type prov:Dictionary,
     prov:type apv:ContextWindow])`, with `hadDictionaryMember(ctx, x:L(m_i), i)` for every member, where `i` is a
     0-based `xsd:int` key (a future delta form would use `derivedByInsertionFrom`).
   - Finally `used(x:L(mc), x:L(mc).ctx, [prov:role apv:ContextWindowRole])`, of class `cls(mc,/input)`; the
     dictionary entity carries the same class.
2. **No member usage.** Member usage is *not* asserted (NE-8). As a consequence, no `tool → llm` or `llm → llm`
   communication arises through context: the collection-mode core equals the members-mode core minus the context
   usages and their Inference 6 communications. Exposure assessments (E.7) would still be computed from membership.
3. **Why it is gated.** PROV-Dictionary is a W3C Note [landscape/prov_semantics.md §3.15]. Its round trip with
   the pinned `prov` version is unverified (caveat C7). Collection mode MUST NOT be used for a release until the
   E.5.5 round-trip and completeness tests pass on dictionary statements.
4. **When it would be used.**
   - For a loop with one call per turn and `n` calls, member mode yields about n² context usages: about 10⁶ for
     n = 1,000.
   - The synthetic 1,000-call taint graph (253,499 relations) already took 104 s to round-trip
     [audit/validation.md §6.5]. By extrapolation, member mode at that length costs minutes per trace.
   - The choice would be per profile (D7) and recorded in `apv:contextEncoding` and in `dk`.
5. **Eviction.** Context eviction (truncation or summarisation) is visible in both modes only as a missing
   member of a later input. It MUST NOT be stated as `wasInvalidatedBy` unless the AER records the eviction
   [landscape/prov_semantics.md §3.8, §12 item 5]. Inspect records compaction (`CompactionEvent`: summary, edit and
   trim); a model-generated summary maps to a `model_call` that generates the summary message, and other compaction
   steps map as in F.2.5 (R-07, PROV-11(b)).

---

## E.7 From SEM annotations to assessment-bundle statements

### E.7.1 SEM interface (C.14)

The SEM record is defined by C.14.2 (owner C); this section imports nothing else from it. Each annotation has `id`,
`target` (an AER record id or part id), optionally `at` (a pointer within the target) and `span [start, end]`
(half-open, in Unicode scalar values of the string at `at`), `type`, `value`, `ev`, `rule`, `premises`, and, for
method-based INFERRED annotations, `method` and `confidence` (R-18).

`type` is one of `integrity`, `channel`, `role`, `injection_marker`, `outcome`, `author`, or a namespaced
`<ns>.<name>`. The value sets that C.14.3 imports from this section are:

| SEM `type` | `value` | `apv:` mapping |
|---|---|---|
| `integrity` (any content part kind, or a fixture) | `trusted` \| `untrusted` \| `unknown` (fail-closed) | `apv:Trusted`, `apv:Untrusted`, `apv:IntegrityUnknown` |
| `role` (a `tool_call` part or a `tool_execution`) | array over `write_sink`, `send_sink`, `execute_sink`, `egress_read`, `response_sink`, `content_source`, `endorser`, `neutral`, `unknown` (fail-closed) | `apv:WriteSink`, `apv:SendSink`, `apv:ExecuteSink`, `apv:EgressRead`, `apv:ResponseSink`, `apv:ContentSource`, `apv:Endorser`, `apv:Neutral`, `apv:RoleUnknown` |
| `channel` | profile vocabulary string | `apv:sourceChannel` (string) |
| `injection_marker` | `{fixture, status ∈ present\|absent\|ambiguous\|gap, normaliser}` (a rejected YAML document is `ambiguous`) | E.7.3 |
| `outcome` (a `judgement`) | `{claim, holds?, score?, scale?}` | `apv:outcomeClaim`, `apv:outcomeHolds`, `apv:outcomeScore`, `apv:outcomeScale` |
| `author` (a content part) | an author string parsed from structured content | `apv:declaredSender` |
| `<ns>.<name>` | per the declared namespace schema | `apv:annotationType`, `apv:annotationValue` (JCS string) |

Polarity lives only in the SEM `outcome` annotation, never in the AER judgement (C RF-2).

### E.7.2 Assessment bundle structure

1. **One bundle per SEM document.** Its IRI is `xd:bundle.assess.<profile-slug>.<dk>`.
2. **The evaluation activity.** The bundle declares `activity(x:assess.<profile-slug>, [prov:type
   apv:PolicyEvaluation])` and `wasAssociatedWith(x:assess.<profile-slug>, sw:agentprov,
   rules:<sem-profile>.<version>)`.
3. **Mentions (entities only).** A *label* annotation on an **entity** target becomes a mention entity:
   - `entity(x:L(t).mn-<h12>, [<property> <value>, evidence attributes, apv:annotationId])`;
   - `mentionOf(x:L(t).mn-<h12>, x:L(t), xd:bundle.core.<dk>)`.

   Cardinality (AD-19(b)): each mention entity occurs in exactly one `mentionOf` (PROV-LINKS unique-mention); there
   is one mention per (subject, annotation), so each label carries its own class and rule. The subject is not
   re-declared with attributes in the assessment bundle, because Inference 21 would copy them onto the mention
   [landscape/prov_semantics.md §13 E3].
   *Rationale.* PROV-LINKS' intended use is adding attributes to an entity described in another bundle without
   editing that bundle [landscape/prov_semantics.md §3.16, §7.2 rule 3].
   A label annotation on an **activity** target (a `role` on a `tool_execution`; a namespaced label on an activity)
   becomes an `apv:Assessment` with `apv:claim apv:Labelled` and `apv:subject` the activity (R-21; NE-19).
4. **Assessments.** A *claim* becomes an assessment entity:
   - `entity(x:as-<h16>, [prov:type apv:Assessment, apv:claim, apv:subject, apv:object?, apv:spanStart?,
     apv:spanEnd?, apv:policy?, evidence attributes])`;
   - `wasGeneratedBy(x:as-<h16>, x:assess.<profile-slug>)`.
5. **Allowed forms.** The bundle MUST contain only these statement forms:
   - entity, activity and agent declarations;
   - `wasGeneratedBy` (assessment from the evaluation activity);
   - `wasAssociatedWith` (evaluation activity to the engine);
   - `mentionOf`, whose supra is declared as an entity.

   In particular it MUST NOT contain `used`, `wasDerivedFrom`, `wasInformedBy`, `wasAttributedTo` or
   `wasInfluencedBy` (NE-10).

### E.7.3 Mapping table

| Source | PROV form in the assessment bundle | Class | Rule |
|---|---|---|---|
| SEM `integrity` | mention with `apv:integrity` (`apv:Trusted`, `apv:Untrusted` or `apv:IntegrityUnknown`) on any content part or fixture | from SEM `ev`; INFERRED for tool-name tables (F.1.8) | `aprov.a_label@2` |
| SEM `role` | on a request part: mention with `apv:securityRole` (multi-valued); on a `tool_execution`: `apv:Assessment` (`apv:Labelled`) with `apv:securityRole` | as above | `aprov.a_label@2` |
| SEM `channel` | mention with `apv:sourceChannel` | as above | `aprov.a_label@2` |
| SEM `outcome` | mention of the outcome entity with `apv:outcomeClaim` and, as given, `apv:outcomeHolds`, `apv:outcomeScore`, `apv:outcomeScale` (explicit polarity, e.g. DoS `security = not utility`; graded judge scores). Not emitted when the judgement's `origin` is `harness_default` (C.14.3) | DERIVED (rule from benchmark code) unless SEM says otherwise | `aprov.a_label@2` |
| SEM `injection_marker` (replaces R-INJ-QUOTE, Challenge 1(f)) | `status` = `present`: assessment `apv:claim apv:ContainsPayload`; `apv:subject` = the part; `apv:object` = the payload fixture; `apv:spanStart` and `apv:spanEnd` when SEM gives a span (SEM-5); `apv:method` = the marker rule id and its normaliser. `ambiguous`: the same claim with `apv:markerStatus apv:Ambiguous` and an `apv:assumption`. `absent` and `gap`: no statement; both are counted in the derivation report and the census (item 3) | `present`: DERIVED (deterministic decoding and matching); `ambiguous`: INFERRED [audit/provenance.md §7.1.4] | `aprov.a_payload@2` |
| SEM `author` (replaces R-ATTR-AUTHOR; §13 E4) | mention of the part with `apv:declaredSender` (a parse fact); plus an assessment `apv:claim apv:QuotesAuthoredContent` with `apv:authorName`, span and `apv:premise` = the mention | mention: DERIVED (parser version in the rule); authorship assessment: INFERRED (the field is exactly what an injection forges) | `aprov.a_author@2` |
| SEM `<ns>.<name>` | on an entity: mention with `apv:annotationType` and `apv:annotationValue`; on an activity: `apv:Assessment` (`apv:Labelled`) with the same | from SEM `ev` | `aprov.a_label@2` |
| engine: exposure [A-EXPOSURE] | assessment: `apv:claim apv:ExposedTo`; `apv:subject` = the request part `p`; `apv:object` = a context member `m_i` of the invocation that generated `p`; `apv:premise` = the `aprov.use_context@1` and `aprov.gen_part@1` statements. A `tool_execution` without a request part (`requested_by`) has no generating invocation and therefore no context premise in `aer/0.1`: no exposure is emitted, and the count is reported | `weakest(premises)` (AD-05): OBSERVED or DERIVED premises for live capture; INFERRED for the released v1 corpus and native imports, whose context membership is INFERRED. The claim does not depend on labels | `aprov.a_exposure@1` |
| engine: taint [A-TAINT] | assessment: `apv:claim apv:PotentiallyInfluencedBy`; same subject and object; `apv:policy` = the taint policy id and version from the SEM profile; `apv:premise` = the exposure assessment and the label mentions or assessments | INFERRED (a policy, over-approximate by design) | `aprov.a_taint@1` |
| engine: INFERRED transform | assessment: `apv:claim apv:SentTransformed`; `apv:subject` = the usage statement IRI; `apv:sentTransform` (E.1.5 item 5) | INFERRED | `aprov.a_sent_transform@1` |

1. **Which pairs are materialised.** Exposure is materialised only for subjects whose request has a SEM
   `role` other than `neutral` (`unknown` included: fail-closed), and objects whose integrity is not `trusted`
   (`unknown` included).
   - Selecting pairs by labels does not make the exposure claim depend on labels. The claim states only context
     membership.
2. **Equivalence with v2.3.**
   - The v2.3 sink rule is turn-aware: a sink uses the untrusted outputs returned before the assistant turn that
     issued it, within the same pass [docs/capture_spec.md §5.2]. That set is exactly the context of the
     invocation that generated the request.
   - Under unchanged labels, the taint pairs therefore reproduce the v2.3 R6 pairs: 41,066 released and 36,687
     converted [audit/provenance.md §4.1]. After AD-05 the released and converted pairs rest on INFERRED context
     membership.
   - Fail-closed handling of unknown tools adds pairs for the 49 released and 12 converted tool turns with
     unknown names [audit/provenance.md §1 item 5].
   - The subject is now the *request*. A consumer can therefore tell attempted sinks from effected ones through
     `apv:execStatus` or `apv:dispatchStatus`. In v2.3, 1,748 errored sinks were indistinguishable
     [audit/provenance.md §5.4].
3. **Census.** The exhaustive census of label × payload marker (SEM-6) is a SEM-validator duty. Its result is
   reported in the derivation report, not asserted in PROV.
4. **Premise fields declared unknown (D-930).** A SEM annotation may rest on a field its record declares `unk`
   (SEM-V06). The statements of `aprov.a_label@2`, `aprov.a_payload@2` and `aprov.a_author@2` do not cite such a field
   (E.1.5 item 1, NE-12); each one left out is counted as `premise_field_unknown` in the derivation report. The label
   keeps its SEM class. The @1 rules, which cited every premise field, stay in the catalogue for the documents that
   cite them.

### E.7.4 Consumers

- A security view loads the core bundle plus one assessment bundle (and, for imported corpora, the inference bundle
  that holds context membership; F.1.7).
- A flow projection, generalising the baseline `graph.py`, that turns assessments into typed edges `object →
  subject` labelled with the claim and filters them by `apv:evidenceClass` [audit/provenance.md §7.4], is deferred
  with `analysis/` (AD-10 row 1).

---

## E.8 The `adprov-v2.3-compat` profile

### E.8.1 What it is

1. **A verbatim port.** The oracle is five baseline files at `579a908`, AST-equal to the originals: `build_prov.py`
   (including `payload_marker`, `_timestamp`, `unique_loc`, `_shared_starts`, `_CHANNEL_OF` and
   `PI_DETECTOR_PLACEHOLDER`), `prov_emit.py`, `labeling.py` (the three tables), `validate.py` and `conformance.py`
   (R-31). Import statements are the only change. The local `import yaml` routes to a `safe_load` shim over
   `agentprov.ingest.yamlsafe`, which changes no frozen byte (MR-3); `PORT_MANIFEST.json` records every change.

   It lives in `agentprov.prov.compat.adprov_v2_3` and is run with the default flags (`emit_source_agents` and
   `emit_derived_edges` are kept verbatim, with no CLI exposure). Its output namespace is the frozen `adprov:` IRI
   (`prov_emit.py:17`).
2. **What it is for.** It is a *regression oracle and migration bridge*. It is **not** the recommended
   semantics (D7).
3. **Defects kept on purpose.** It keeps by design:
   - the activity conflation (D1);
   - taint as `prov:used` (D2);
   - the time fallbacks (`build_prov.py:393-395, 436-437`);
   - fail-open labels;
   - the incomplete IRI-character escaping (D11). The B.9 F-26 IRI refusal applies to the new engine only, never to
     the compat port (R-31).

   These are listed in [audit/provenance.md §14]. They MUST NOT be "fixed" in the port; the fixes are what
   `agentprov-prov/0.1` is.
4. **Its own validator.** The ported `validate.py` shape invariants I1–I11, `conformance.py` and
   `injection_reaches_untrusted` are the profile rules of `adprov-v2.3-compat` [audit/validation.md §3.2, §9;
   audit/provenance.md §7.1.5]. They MUST NOT gate `agentprov-prov/0.1` output [audit/validation.md V8]. The new
   generic validators (VAL-05…VAL-12) sit beside them.
5. **Kept apart and marked.** Compat graphs are never placed in `agentprov-prov` bundles. In v0.1 the corpus manifest
   and index flag every compat output with `apv:status apv:RegressionOracle` and profile `adprov-v2.3-compat`, and
   the CLI prints a notice whenever compat output is written or loaded (R-55). When lineage documents return, the
   released file and the regenerated projection are two entities linked only through the gate report (E.3.5;
   §13 G4).

### E.8.2 The transcript/v1 view

`agentprov.views.transcript_v1` provides `render(aer) -> dict`, `render_converted(aer) -> dict` and
`serialise(dict) -> bytes` (RESOLUTIONS §3.2; R-30). The view is regenerated **from the AER alone**: it reads nothing
from raw (AD-02).
- The field placements are those of the single v1 field table `views/transcript_v1_fields.toml` (owner C.15.3,
  generated into C.15.3 and D.7.3).
- The fields that `build_prov` reads are [audit/provenance.md §2]: `meta.injections`, `meta.started_at`, `turns[]`
  of the final pass and `discarded_attempts[].turns` of earlier passes (oldest first), `turn.role`, the content of the
  first user turn of the final pass, and the tool-turn fields `tool_call_id`, `function`, `args`, `content`, `error`,
  `started_at` and `ended_at`.
- Values come from typed AER fields and the verbatim `ext.adprov` fields. JSON member order and the int/float
  distinction are restored from the sparse lexical hints `ext.lex {ord, flt}` (C.11.4), written by the one shared
  helper `agentprov.aer.canon.lex_hints()`. The hints cover every object and number copied from a source, including
  typed fields (`t.dur_s`, `params.*`, `usage.*`), and are mandatory for adapters that declare a byte-exact view
  (`adprov.transcript_v1`, and `agentdojo.tracelogger` while `render_converted` is a gate).
- `render` is order- and type-faithful; round-trip tests compare bytes or JCS, never Python `==` (K.1).
- A converted-transcript `"0"` timing stub is rendered from `t.raw` (C.7.3).

> **Resolved (AD-02 / R-04): Challenge 3 to D7 and D2 is rejected.** The view does not re-read raw values through
> `src` locators: with that remedy Gate B would never exercise AER values, and "regenerated from the AER" would be
> false. One mechanism, C's sparse `ext.lex {ord, flt}`, restores member order and integral-float form instead. The
> measurements that motivated the challenge stand and are the reason `ext.lex` is mandatory for the byte-exact view:
> 12,676 of 64,781 released activities in 8,017 of 17,664 graphs (45%) have `args` keys not in sorted order (12,862
> activities in 8,173 of 18,027 converted graphs) [EF_evidence/args_key_order.py]; 313 released activities in 270
> graphs and 1,681 converted activities in 1,288 graphs carry integral floats [EF_evidence/args_number_form.py].
> The `flt` flag suffices because the v1 files were written by Python `json.dumps(float)` (RESOLUTIONS consolidator
> check 4).

### E.8.3 The byte-identity gate (normative)

1. **The gate.** For a stored graph `G` and its transcript `T`:
   - `T` is ingested as a raw artefact, through the v1 adapter, into an AER;
   - the view `V` = `render(aer)` is built from the AER alone;
   - the gate requires `json.dumps(build_prov(V), indent=2).encode("utf-8") == bytes(G)`, which MUST be checked as
     sha256 equality against the corpus `checksums.sha256`.

   The baseline writes graphs exactly as `json.dumps(doc, indent=2)`, UTF-8 and without a trailing newline
   (`generate.py:468` through `transcript.py:273-283`). For this section, a golden graph was confirmed to
   re-serialise byte-identically under that rule. Because the view reads only the AER, a mapper that corrupts `args`
   fails this gate (AD-02). This is J's Gate B; J's A1 (JCS value identity) and A2 (bytes) gate the view itself.
2. **Bytes, not dicts.** The comparison is of bytes, not parsed dicts. The baseline's `recompute` compares
   `old_doc == new_doc` after `json.loads`, which equates `True` with `1` and `1` with `1.0`, and ignores
   serialiser drift [audit/corpus.md §3.3 R2].
3. **The three tiers.**
   - **G1 (CI, MUST).** The 15 golden transcript–graph pairs in `investigation/baseline/golden/`
     [baseline/BASELINE.md §7], plus the MIG-10 pairs (nested order; integral `wall_clock_s`; R-59, subject to U-06),
     are copied into `tests/fixtures/agentdojo_prov_v1/golden/` and gated on every commit (R-48). The 7 native
     source logs and the 2 native test fixtures stored beside them are G3 inputs.
   - **G2 (local, MUST before any release that claims compatibility).** All 17,664 released and 18,027 converted
     graphs: 0 mismatches. A machine-readable report lists any mismatch with the first differing byte offset.
   - **G3 = J's Gate R (`render_converted`), per AD-07.** native June-2024 log → AER (native adapter) →
     `render_converted` → compat graph, compared byte for byte with the converted graph. R1/R2 on the golden converted
     pairs (C01–C07 plus the MIG-10 converted pairs) block in CI as release gates. The full run over the 18,241 pinned
     blobs (including 7 Mixtral) is a local **claim gate**: only a pass with 0 mismatches licenses "the native
     re-import supersedes the converted tree"; otherwise the converted tree stays a `compat_oracle` part and the
     mismatch report is published. R3–R5 are reported.
4. **The ported tests run too.** The ported baseline tests (`tests/test_prov_builder.py`, and
   `tests/test_communication.py` with its 42 tests) run as the compat profile's regression suite. The tests that import
   `agentdojo` move to the backend project `backends/agentdojo/tests` (R-01) [audit/provenance.md §11].

### E.8.4 Semantic diff: v2.3 → `agentprov-prov/0.1`

The machine-readable source of this table is `src/agentprov/prov/compat/semdiff-map.toml` (R-33): one row per v2.3
element with its count, its disposition in J's closed 7-value vocabulary (`kept`, `reclassified`, `moved`,
`replaced`, `moved-to-assessment`, `dropped`, `new`), its `agentprov-prov/0.1` counterpart as EF catalogue rule ids,
and its class. J's Gate E (J.3.6), the tables below and O's `tab:semdiff` are generated from it. Counts are
"released / converted" from [audit/provenance.md §3, §4.1, §6] unless marked "measured", in which case they come from
[EF_evidence/ctx_volume.py]. Counts whose class changed under AD-05 are recomputed in phase 13.

**Corrections from the map (phase 7).** `semdiff-map.toml` follows the implementation where the tables below differ;
the generated `docs/compat/semantic-diff.md` is current, these tables are the r2 design record:
- R1 on the v1 trees is DERIVED in the core (the mapper cites `adprov.tool_turn_is_one_execution@1`), not OBSERVED;
  PI-detector-redacted outputs of the converted tree are INFERRED;
- `actedOnBehalfOf`: the v1 runtime delegation of `aprov.assoc_tool@1` is INFERRED (E.10 item 21); only
  `aprov.deleg_user@1` is DERIVED;
- the attribute rows add `prov:label` and `adprov:content` (both in audit §6), and the `prov:time` cell "121,493 / 64,779"
  is split into its `used` and `wasGeneratedBy` rows (both release counts);
- node rows are added for the non-LLM actors and the declared unknowns (`apv:Gap`, status properties), and relation rows
  for the policy evaluation (`aprov.a_evaluation@1`) and outcome polarity (`aprov.a_label@1`, DERIVED);
- unexecuted requests are 153 converted (R-33); R7's deferred `aprov.i_arg_literal_overlap@1` is a mention only.

**Relations.**

| v2.3 statement (audit id) | Count | `agentprov-prov/0.1` counterpart | Disposition | Class |
|---|---|---|---|---|
| R1 `wasGeneratedBy(e_k, a_k)` | 64,781 / 68,620 | `aprov.gen_result@1` (tool_result part ← tool execution) + `aprov.gen_message@1` (tool message ← tool execution); the activity is now only the tool execution | kept (re-targeted) | OBSERVED for live capture and v1; native imports: DERIVED iff `agentdojo.tool_msg_is_one_execution@1` is verified over the producing code range, else INFERRED (AD-05) |
| R2 `wasAssociatedWith(a_k, ag_llm)` | 64,781 / 68,620 | `aprov.assoc_tool@1`: `wasAssociatedWith(te, runtime)` + `actedOnBehalfOf(runtime, agent, te)`; the v2.3 edge is *entailed* by Inference 14 | reclassified (asserted → entailed; executing runtime added) | association DERIVED; delegation INFERRED for v1 and native imports (`agentdojo.auto_execution_unverified@1`, bundle `inf.agentdojo-auto_execution_unverified-v1`), DERIVED only with a verified `apv:AutoExecution` (live capture) |
| R3 `used(a_k, e_user_query)` (first turn) | 22,218 / 19,838 | `aprov.use_context@1`: `used(llm_1, user message)`, together with the system message, and in every later invocation of the pass | moved (to the invocation, generalised) | INFERRED for the released v1 corpus and native imports (`inf.adprov-context_is_prefix-v1`, `inf.agentdojo-context_is_prefix-v1`); OBSERVED (with `input_at`) or DERIVED (alignment rule) for live capture |
| R4 `used(a_k, e_j)` exchange (previous turn) | 72,633 / 68,212 | `aprov.use_context@1`: `used(llm_m, tool message j)` for *every* earlier tool message of the pass | moved (the previous-turn window is dropped) | as R3 |
| R5 `wasInformedBy(a_k, a_j)` | 72,633 / 68,212 | not emitted. Replaced, under the full Inference 6 closure (AD-19(c)), by `aprov.comm@1` pairs `tool_exec_j → llm_m` (via message `j`) and `llm_m → tool_exec_k` (via request `k`), plus the `llm → llm`, pass, decision and checker communications of E.1.6. The composite edge survives only as a *projection* in the compat graph | replaced [landscape/prov_semantics.md §5.3] | `llm → tool`: as `aprov.use_request@1`; `tool → llm` and `llm → llm`: as R3 |
| R6 sink `used(a_k, e_j)` (taint-only part) | 26,645 / 23,449 (of 41,066 / 36,687 taint pairs); each entails, via Inference 6, exactly one `wasInformedBy` the builder never asserts (entailed 99,278 / 91,661 minus asserted 72,633 / 68,212; E.1.6) [audit/provenance_evidence/evidence_stats.json; landscape/prov_semantics_evidence/inference6_scan.json] | `aprov.a_exposure@1` + `aprov.a_taint@1`, as `apv:Assessment` over (request `k`, message `j`) | moved-to-assessment | exposure: as R3; taint: INFERRED |
| R7† `wasDerivedFrom(e_k, e_j)` (gated) | 0 / 0 | none. Argument-level evidence would come from `aprov.i_arg_literal_overlap@1` (engine methods deferred, E.1.7) | dropped | — |
| R8† `wasAttributedTo(e_k, ag_src_c)` (gated) | 0 / 0 | none in PROV; `aprov.a_author@1` gives a declared-sender mention and an INFERRED authorship assessment when SEM parses an author | dropped | — |
| `actedOnBehalfOf` (never emitted) | 0 / 0 | `aprov.assoc_tool@1` delegation; `aprov.deleg_user@1` | new | DERIVED |
| — | — | `aprov.use_request@1`, `aprov.start_tool@1`, `aprov.member_request@1`, `aprov.gen_message@1` and `aprov.gen_part@1` for assistant messages and requests, `aprov.assoc_model_call@1`, `aprov.use_model@1`, `aprov.attr_message@1`, `aprov.attr_fixture@1`, `aprov.decision@1`, `aprov.env_*`, `aprov.outcome@1`, `aprov.rerun@1` | new | per rule |

**Nodes.**

| v2.3 node | Count | Counterpart | Disposition |
|---|---|---|---|
| `ag_llm` | 17,664 / 18,027 | `llm_agent` actor → `apv:AgentSystem`; plus `x:L(a).model` (requested and served identity) and `x:L(a).svc` when the served model or provider is known | reclassified (split) |
| `e_user_query` | 17,664 / 18,027 | a message entity (role user) attributed to the simulated user. It covers *every* user message, not only the first of the final pass: 1,527 converted traces have more than one user turn [audit/provenance.md §2] | kept (generalised) |
| `a_k` (tool activity) | 64,781 / 68,620 | `apv:ToolExecution` (re-scoped), plus a separate `apv:ModelInvocation` for each assistant turn (64,897 / 73,551, measured; rows `new`) | reclassified |
| `e_k` (output) | 64,781 / 68,620 | tool_result part + tool message | kept |
| — | — | system and assistant messages and their parts, including reply text (SEM-7); requests (64,829 / 68,773, measured, of which 48 / 153 were never executed, counted positionally [audit/provenance.md §2; R-33]); payload fixtures; outcomes and checker runs; run and pass activities; the capture profile | new |
| `ag_src_*` (gated) | 0 / 0 | none | dropped |

**Attributes.**

| v2.3 attribute | Released count | Counterpart | Disposition |
|---|---|---|---|
| `adprov:integrity` | all entities and agents | `apv:integrity` on assessment mentions; three-valued, fail-closed | moved-to-assessment (INFERRED) |
| `adprov:role` | 64,781 (15,196 sink, 0 endorser) | `apv:securityRole` (multi-class) on assessment mentions or `apv:Labelled` assessments | moved-to-assessment |
| `adprov:source_channel` | 29,661 | `apv:sourceChannel` (assessment) | moved-to-assessment |
| `adprov:contains_injection_marker` | 62,606 | `aprov.a_payload@1` `apv:ContainsPayload` with span | moved-to-assessment (DERIVED) |
| `adprov:defence_omitted` | 0 / 2,154 | `aprov.decision@1` (Decision activity, verdict redact) with a pre-decision entity marked `apv:contentStatus apv:Overwritten` | reclassified (attribute → activity; INFERRED from the sentinel; status Overwritten, R-08) |
| `adprov:step`, `adprov:turn` | 64,781 each | none in PROV; order is carried by `apv:after*` (E.1.4); step and turn remain in the compat graph and the transcript view | dropped (projection) |
| `adprov:attempt` | 0 | `apv:Pass` activity with `apv:index`, plus `apv:partOf` | reclassified |
| `prov:startTime`, `prov:endTime` | 64,779 | the same, on `apv:ToolExecution`, from AER `t` | kept |
| `adprov:args` | 64,781 | `apv:args` (JCS) on the request part; `apv:argsEffective` on the execution when it differs | moved (to the request) |
| `adprov:error` | 6,920 | `apv:error` on the tool_result part; `apv:exception` on the execution when recorded | kept |
| `adprov:content_hash`, `adprov:content_len` | 82,445 each | `apv:contentSha256` (over the UTF-8 bytes of the recorded text; v2.3 hashed decoded text blocks [audit/provenance.md §2]) and `apv:contentLength` (unit stated: Unicode scalar values) | kept (definition tightened) |
| `prov:time` on `used` and `wasGeneratedBy` | 121,493 / 64,779 | none (no relation times) | dropped |
| `adprov:time` on `wasInformedBy` | 72,631 | none | dropped |
| `adprov:agent_kind` | 17,664 | `prov:type` with an `apv:` agent class | reclassified |
| `adprov:placeholder_mismatch` (never emitted) | 0 | none. Arguments changed before dispatch appear as `args` ≠ `args_effective` when both are recorded | dropped |

### E.8.5 What the diff means for consumers

- **Communications.**
  - A detector that walked v2.3 `wasInformedBy` chains reaches the same tool executions through
    `tool → llm → tool` paths. For live capture these paths are in the core. For the released and converted corpora
    and for native imports, the `tool → llm` half rests on INFERRED context membership (AD-05), so the paths exist
    only in core ∪ the context inference bundle (`inf.adprov-context_is_prefix-v1` or
    `inf.agentdojo-context_is_prefix-v1`); a consumer that reads the core alone sees only `llm → tool` (R-05).
  - Communication is not transitive, so the paths are explicit; nothing has to be inferred
    [audit/provenance.md §7.4].
  - The member-mode closure has strictly more paths than v2.3: the full context instead of the previous turn.
- **Sink taint.** A consumer that needs the v2.3 sink-taint semantics reads `apv:PotentiallyInfluencedBy`
  assessments. A consumer that needs v2.3 bytes reads the compat graph, which is marked `apv:RegressionOracle`.

---

## E.9 The recomputation determinism invariant (normative)

1. **Invariant.** For fixed inputs, `derive` returns byte-identical `prov_json` (and, on demand, byte-identical TriG)
   across runs, machines, operating systems, CPython 3.14 patch releases (core `requires-python = ">=3.14"`; AD-16 as
   ruled in Addendum B), `PYTHONHASHSEED`, locale and time zone. The inputs are:
   - the AER execution bytes;
   - the SEM document bytes;
   - the spec version;
   - the catalogue file bytes (the `aprov` catalogue, and the adapter catalogues and profile at the versions the AER
     header names, loaded from package resources; AD-14);
   - `ProvOptions`;
   - for TriG only, the pinned `prov` and `rdflib` versions.

   The AgentPROV software version is not an input: documents name the engine as the version-free `sw:agentprov`
   (DECISIONS D-13), and the version and code digest of each run are recorded in the corpus `derivation.json` (H.8.2).
2. **The digest chain.** The corpus manifest records, per execution:
   - raw sha256;
   - AER execution digest;
   - SEM digests;
   - the PROV-JSON digest (TriG and the flattened core are not stored, AD-10);
   - catalogue digests;
   - library versions.

   Recompute (D9) re-runs map, annotate and derive, and requires identical digests. An *intended* change MUST
   appear as a version bump of the spec, catalogue, adapter or SEM profile. Such a bump changes `dk` and hence
   every affected bundle IRI.
3. **Code discipline in `agentprov.prov`.**
   - No `datetime.now`, `time.time`, `uuid`, `random`, `os.environ` or network access. This is enforced by a
     static ban-list test alongside the D10 import-boundary test.
   - No iteration over sets or dicts without sorting where the order reaches the output.
   - Every multi-valued output is sorted (E.5.3 item 4).
   - Hashing is over explicit UTF-8 encodings.
4. **Tests.**
   1. **Golden digests.** For fixture AERs drawn from every v0.1 source class (AgentDojo TraceLogger, v1
      transcript, `capture/0.1`, Inspect `.eval`, and the generic-kind future-framework fixture of D.12 / F.2.6;
      STAC when it leaves `planned`), committed digests are compared in CI.
   2. **Hypothesis property tests.** Permuting SEM annotation order, AER `ext` member order and option-tuple
      order leaves the output bytes unchanged. Derive twice in fresh processes with different `PYTHONHASHSEED`
      values and compare the bytes.
   3. **Recompute** over the corpus: 0 changed. This is byte comparison, not the baseline's dict equality
      [audit/corpus.md §3.3 R2].
   4. **Compat byte gate** (E.8.3).
5. **Library upgrades.** A `prov` or `rdflib` upgrade that changes on-demand TriG bytes, but not PROV-JSON bytes, is a
   *serialisation* change.
   - It is recorded with the library versions wherever TriG is produced; it changes nothing in a sealed corpus.
   - It does not change `dk`, because the PROV-JSON content and the bundle identity are unchanged.
   - Any change to PROV-JSON bytes without a spec or catalogue bump is a defect.

## E.10 Implementation resolutions (phase 5, 2026-10-08)

The phase-5 engine (`agentprov.prov`: `engine`, `evidence`, `specs`, `iri`, `vocab`, `rules/{nodes,edges,top}`,
`serialise/{provjson,time}`, `catalogue/agentprov-prov-0.1.toml`) derives every golden v1 AER, and the 19 golden
PROV-JSON digests are committed (`tests/golden/prov_digests.json`, E.9 item 4.1). The gaps closed while implementing are
listed below; the code is the reference.

1. **Signature.** `derive(aer: AerDocument, sems=(), *, spec=None, options=None, registry=None, check_aer=True)`.
   `registry` supplies the adapter catalogues named by the AER header (package resources by default). `check_aer` runs
   the tier-2 validator without raw-store checks and refuses an invalid AER (`prov.aer_invalid`, E.0.1 item 4); a
   caller that has just validated the file with its store may pass `False`. Until phase 7, a non-empty `sems` was
   refused (`prov.sem_unsupported`); phase 7 replaced the refusal (E.11 item 1).
2. **Typed failures** (`ProvDerivationError`, E.0.1 item 5): `prov.aer_invalid`, `prov.sem_unsupported`,
   `prov.unsupported_option`, `prov.generic_kind_misuse` (NE-21), `prov.method_set_empty`, `prov.statement_collision`,
   `prov.rule_unknown`, `prov.unresolved_reference`, `prov.unresolved_pointer`, and `prov.unexpected_input` for any
   other malformed shape.
3. **Engine catalogue format** `agentprov-prov-catalogue/0.1`. It differs from the adapter format (D.5.2) because
   engine rules have a *ceiling* (O, D or I), not a class. Per-path caps and assumptions are data:
   `aprov.use_model@1` per-actor path (D, `apv:SingleModelPerActor`), `aprov.assoc_tool@1` delegation (D),
   `aprov.env_pass@1`/`env_call@1` carry-over (D), `aprov.outcome@1` synthetic checker run and assumed inputs (D), and
   `aprov.n_model@1` service agent (O, the class of the identifying field). `aprov.a_sent_transform@1` (ceiling I) is
   in the catalogue because phase 5 already routes INFERRED sent transforms (E.1.5 item 5).
4. **Internal module.** `prov/_ir.py` holds the statement representation (`Stmt`, `Attr`, `Field`); it is not a
   public API. Rules name premises only; classes, routing and names are computed by the engine.
5. **Values.** An asserted JSON `null` is `apv:RecordedNull` (task ids, `error`, outcome values), stated on the status
   sibling: `<p>Status apv:RecordedNull` in place of the data property `<p>`, which is omitted (apv 0.2.0, D-500;
   E.4.4). Before 0.2.0 the QName was the object of `<p>` itself, an IRI on an `owl:DatatypeProperty`. Floats are
   `xsd:double` in shortest round-trip form; objects and arrays are JCS strings (`args`, `usage`, `params`,
   `exception`, object outcome values).
6. **Content digests beyond E.1.3.** A `value`-bearing part (`tool_result.value`, `other.value`) carries
   `apv:contentSha256` over the JCS bytes of the value. A `blob` part carries the blob digest and `apv:mediaType`; a
   `file` part `apv:mediaType`. A fixture's digest is its blob digest, else the SHA-256 of the JCS bytes of `content`.
7. **Values under `unk` are not restated**, including `ambiguous` values that the AER keeps (C.7.2): the status is
   stated instead (E.1.5 item 1).
8. **Status placement** (`aprov.status@1`). `/model/requested` and `/model/served` statuses go on the model entity when
   it exists. `/original` goes on the decision's `.out`/`.pre` entity as `apv:contentStatus`. `/args` on a
   `tool_execution` is `apv:requestedArgsStatus`; any `/params…` pointer is `apv:paramsStatus`. Part pointers map
   `/parts/<k>/{text,value}`, `provider_call_id` and `args_raw` as in E.4.5. Every other pointer is an `apv:Gap`,
   numbered per node (`x:<node>.gap-<n>`). A gap cites its record (`apv:sourcePointer "<id>"`, which resolves) and
   carries the unknown pointer in `apv:property`, since the unknown pointer itself does not resolve. NE-18 gaps carry
   `apv:reason "aprov.use_request@1"`.
9. **Times.** `t.start_naive`/`t.end_naive` are emitted as `apv:startTimeLexical`/`apv:endTimeLexical`. `t.raw` is
   never emitted, so a converted-transcript `"0"` stub never reaches PROV (gate D).
10. **Method sets.** The method rules of an INFERRED field are the I-class rules among its applicable references
    (C.6.4). If there are none (an I tag that arises by propagation), they are the I-class rules the record cites
    elsewhere. If there are still none, the engine fails with `prov.method_set_empty`.
11. **Evidence attributes.** `apv:sourcePointer` lists a statement's premise fields only. A node cites its existence
    (`"<id>"`), a part `"<m>/parts/<k>"`, and a derived node its defining field (`"agent/model"`, `"dc0/subject"`).
    `apv:basisRule` holds the applicable rules of the D and I premise fields plus the rules that declare a cited
    assumption; OBSERVED premises contribute `apv:attestedBy` only. `apv:assumption` holds the assumptions of the basis
    rules and the engine rule's own path assumptions, as core `apv:` QNames. Adapter-declared `<ns>:<Name>` terms are
    strings, because documents declare no adapter prefixes, and so go on the data property `apv:adapterAssumption`
    (`xsd:string`; apv 0.2.0, D-501): before 0.2.0 they were literals of the object property `apv:assumption`, whose
    range is `apv:Assumption`. The linkage validator treats the two alike (F.1.5 item 6).
12. **Split attributes** (E.1.5 item 5). An INFERRED attribute on a stronger element is grouped by (element, attribute
    rule, method set). On an entity it becomes one mention `x:<node>.mn-<h12>`, with `h12` over (dk, rule id), plus a
    `mentionOf` to the core bundle. On an activity or agent it becomes an `apv:Assessment` with claim `apv:Labelled`
    (`apv:OrderedAfter` for `aprov.after@1`). On a relation it becomes an `apv:Assessment` with claim
    `apv:SentTransformed` (or `apv:Labelled`) and `apv:subject` set to the statement IRI. Assessment names are
    `as-<h16>` over (dk, rule id, subject, `-`, claim). `apv:afterEvidenceClass` is the weakest class among the edges
    kept on the node.
13. **Communication closure.** The occurring method sets are those of the inference statements and split attributes,
    plus the minimal witness method sets of every pair not in `C(∅)`. A union bundle therefore appears when a witness
    joins two methods: golden C05 has `inf.adprov-context_is_prefix-v1--agentdojo-pi_detector_sentinel-v1` for
    `llm ← decision` through the redacted tool message.
14. **Names.** A discriminator (`contextIndex=<i>`, `inputIndex=<i>`, `input=<k>`, `primary`) is used only when
    (bundle, rule, section, arguments) repeat. An absent optional argument hashes as `-`. Top-level statement ids are
    `xd:<rule-name>.<h16>`, hashed with the core `dk`.
15. **Top level.** `aprov.t_map@1` states one association with the adapter per catalogue in `execution.rules` (each
    catalogue is a plan the mapping followed). The method-provider association of `aprov.t_derive@1` is made per
    catalogue namespace of the inference bundles' method rules. Origin attributes per origin kind are as in
    `rules/top.py`. `aprov.t_capture@1` omits the capture and backend associations: `aer/0.1` does not record their
    versions, which is disclosed as `capture_software_unversioned`.
16. **Capture profile.** Source profiles declare no capability lists yet, so `x:capture-profile` carries the seal's
    `apv:accounting` and `apv:issue` only. Capability individuals arrive when profiles declare them (phases 6 and 10).
17. **Derived nodes.** The model-service agent exists when the actor's served model or provider is recorded, or when a
    call of the actor records `served_model`; its class is that of the strongest witness. The pre-decision entity
    (`x:<te>.out` or `x:<part>.pre`) has no `prov:type` and is capped by the decision and the execution.
18. **Generators.** A `tool_result` part of a message generated by a decision is generated by the decision whatever
    the decision's subject (denials included). The execution's `.out` is generated only when the subject is that
    execution.
19. **Heuristic anchors.** These are chosen without order claims and are revisited when sources need them. `rerun@1`
    takes the pass's message with the largest `m<n>` ordinal (ids follow source position, C.4.2) and requires a null
    text part and no request part. `inj_placement@1` takes the first state change, in file order, that has a before
    entity. No golden source exercises either rule.
20. **NE-21 refusal.** An `activity` whose type name is in the AER validator's specialised-kind list
    (`aer.activity.shadows_kind`) is refused, and so is an `artefact` typed `message`, `part`, `fixture`, `judgement`
    or `state_change` (`prov.generic_kind_misuse`). The two lists are shared so the tiers cannot diverge.
21. **Assumptions of engine rules on AgentDojo-family sources (resolved in phase 5).** The first cut shipped no adapter
    rule declaring an assumption, so `start_tool@1`, the tool-runtime delegation of `assoc_tool@1` and the assumed
    checker inputs of `outcome@1` never fired on v1 AERs. Two I twins now state the assumptions as asserted:
    `agentdojo.auto_execution_unverified@1`, cited on the `env` actor at `/on_behalf_of` (`evf {"/on_behalf_of": "I"}`),
    and `agentdojo.checker_inputs_unverified@1`, cited on every `origin: checker` judgement at `/inputs`, which is
    declared `unk {"/inputs": "not_recorded"}`. Both are I because no AgentDojo-family source records the producing
    code's commit or wheel hash (AD-05). A pinned live harness cites D twins, and its statements reach the core.
    - The engine takes the citing field as a premise of every statement that rests on the assumption, so it appears in
      `apv:sourcePointer` (`env/on_behalf_of`). A citation scoped to an unknown pointer premises the record itself.
    - On the full local trees, `start_tool@1` fires once per tool execution (64,781 / 68,620), and so does the
      delegation. Every checker judgement gets a checker run with INFERRED usages of the final output and the scored
      calls (`docs/reports/prov/`).
    - `rerun@1` and `inj_placement@1` still never fire on v1 data, and correctly so: no transcript holds more than one
      pass, and none records environment state. No rule is added for them.
    - The C.16.2 vector is regenerated by the shipped mapper, and C.16.1 is patched to cite the same rules for the
      phase-6 native importer. Their digests, and the C.14.5 SEM example that names the C.16.2 digest, are updated
      in C.16.

22. **The engine agent is version-free (resolved, DECISIONS D-13).** E.3.3 first named the engine `sw:agentprov.<ver>`
    with `apv:softwareVersion`. That put the software version into every document, so a release that changes no
    semantics would have changed every PROV-JSON digest, contradicting E.3.4 item 3 and E.9. The engine agent is now
    `sw:agentprov`, with no version in the document. The software version and code digest of each run are recorded in
    the corpus `derivation.json` (H.8.2), which `recompute` compares separately. A semantic change still requires a
    spec or catalogue bump.
23. **Tier-4 validators** (`agentprov.validate`: `tiers`, `prov_structure`, `constraints`, `linkage`, `profiles`,
    `roundtrip`, `prov.validate_prov`). Every golden derivation and the synthetic generic-kind variants pass in
    release mode. The resolutions:
    - Finding codes are `pv.<module>.<check>`, except `prov.link.unresolved`, which K.5 names. Never-emit checks are
      the outcomes `PV-NE-<n>`. PV-NE-9 and PV-NE-16 are `not_applicable`, because they are not decidable from the
      output beyond the rule/section table.
    - `apv:sourcePointer` is exempt from the JCS order of E.5.3 item 4, because E.1.5 item 6 orders it by record
      position, then pointer. `pv.linkage.source_pointer` checks that order.
    - Element declarations count as statements for `apv:premise` (E.0.4). A split-out assessment cites its subject
      element as its premise.
    - `x:capture-profile` (`aprov.n_capture_profile@1`) has no `apv:sourcePointer`. Its premises are seal members,
      and the seal is not an addressable record. It is exempt from the pointer requirement, as is `aprov.comm@1`, whose
      premises are statements.
      **Amended 2026-10-22 (D-621; pre-round review E-2).** The exemption belongs to the node, not to the rule. It holds
      only for the core entity `x:capture-profile` typed `apv:CaptureProfile`, which the rule alone emits. Any other
      statement under `aprov.n_capture_profile@1` fails `pv.linkage.pointer_missing` and `pv.profiles.rule_section`.
    - **Pointers are bound to the statement (D-621; pre-round review E-3; K.10 "that justifies it").** Each
      `apv:sourcePointer` must name a premise of the statement it sits on, or it fails `pv.linkage.pointer_unbound`.
      - In an assessment bundle, the pointer is the target or an AER premise (`{id, p}`) of an annotation named by
        the statement, an endpoint or a premise statement: the fields the engine cites (E.7.3).
      - Elsewhere, the pointer's record is the statement's node, an endpoint, its `apv:subject`, or a premise
        statement's node or endpoint (a part's node names its message record).
      - Seven rules cite further records (`assoc_tool`, `start_tool`, `decision`, `gen_result`, `outcome`, `n_model`,
        `n_part`). For these, a pointed record also counts when it is reached from the anchors (or an already-bound
        record) through one of the rule's premise links: a record kind, the field that links it and, where the
        engine's citations are closed, the pointers the link binds.
        **Amended 2026-10-22 (D-621 amendment 2; pre-round verification V-3).** The links replace the one-hop relation
        (any top-level field naming an anchor), which also bound scope, run and actor records:
        - `assoc_tool`: the message the execution's `call` names (`/generated_by`, `/actor`) and that message's
          generator (`/actor`);
        - `start_tool`: the execution's actor (its AutoExecution citation);
        - `decision`: a decision whose `subject` names the statement's entity (any field);
        - `gen_result`: that decision (`/subject`) and a message it generated (`/generated_by`);
        - `outcome`: the scope a checked message belongs to (`/scored`);
        - `n_model`: a model call of the service's actor (`/served_model`);
        - `n_part`: the decision (`/subject`, `/verdict`) or seal issue (`ids`) about exactly that part.
        Example: `m9/generated_by` names `dc3`, whose `/subject` is the tool execution. Residual: `n_model` covers an
        actor's model node and its service node alike, so a same-actor model call's `/served_model` also binds on the
        model node.
        **Amended 2026-10-22 (D-621 amendment 3).** A carried-over state change (`apv:EnvironmentCarriedOver`) binds when a
        bound state-change record lies in its transitive `after` closure: the predecessor the engine chose (R-54). This
        covers `env_call`/`env_pass` (any of its pointers) and a checker's post-state usage under `outcome` (the record
        pointer). *Resolved 2026-10-23 (regen item 165):* carried-over state changes with the same cause and the same
        predecessor state no longer make the engine refuse the derivation with `prov.statement_collision`; they share
        one statement that cites each of them (E.1.4, `aprov.env_pass@1`).
      - Within an anchor record the binding is per record, not per field: another field of it is not caught here, but
        the EV-5 class check still applies to it.
    - **Unidentified relations are placed (D-621; pre-round review E-1; E.5.1 item 3).** `pv.prov_structure.relations`
      enforces the placement rules:
      - `alternateOf` never appears;
      - `specializationOf` appears only at the top level, exactly once per bundle, as `(<bundle>, xd:provenance)`,
        with the top-level entity `xd:provenance` typed `apv:ExecutionProvenance`;
      - `hadMember` appears only inside a bundle;
      - `mentionOf` appears only inside inference and assessment bundles.
    - **More binding checks (D-621 minors, pre-round review #23-#26).**
      - `pv.linkage.existence` also keeps a statement's class within its rule's ceiling (E.1.5 item 2; a per-path cap
        is never above it), and keeps an AER node's class within its record's existence class.
      - `pv.linkage.premise` keeps assessment statements as premises within their own bundle, and lets an assessment
        statement rest only on the core, the inference bundles and its own bundle.
      - A reflexive `mentionOf` breaks Constraint 52 (`pv.constraints.specialization_reflexive`).
      - The new check `pv.linkage.aer_binding` binds the document to the AER it is validated against: the
        `xd:aer.<records_sha256>` entity, its `apv:sha256` and `apv:executionId`, and every bundle's derivation key,
        recomputed with the `aprov` catalogue digest the document records.
    - **Engine resolutions (D-621; user decisions 2026-10-22).**
      - An `unk` pointer is unknown, not absent: the negative conditions of `aprov.attr_message@1` (no /generated_by),
        of `aprov.start_tool@1` and of the AutoExecution delegation (no /authorised_by), and the message.actor
        requester, do not hold for it (E.1.5 item 1); the gap records it (#15).
      - An item of `/input` or `/inputs` declared `unk` fires no `used` (#16).
      - Message nodes state their `/scope` (`aprov.n_message@2`, E.1.3/E.1.4) (#17).
      - Header artifacts with identical bytes share one `raw:sha256-<hex>` entity whose per-artifact attributes are
        multi-valued and sorted; `t_raw`, `t_map`, `t_primary` and `t_capture` are stated once per digest, and the AER
        header keeps the pairing (#18).
    - **Catalogue version 2 (D-31 owner ruling 2026-10-22).** The `aprov` catalogue is at version 2. Version 1
      (`79b0a1e78dc7…`, which stored corpora record) is archived byte-exact in
      `prov/catalogue/archive/agentprov-prov-0.1.v1.toml`, and `corpus.authority` answers v1 from it.
    - **Catalogue version 3 (D-930, 2026-10-28).** The `aprov` catalogue is at version 3: `aprov.a_label@2`,
      `aprov.a_payload@2` and `aprov.a_author@2` cite no premise field declared unknown (E.7.3 item 4, NE-12). Version 2
      (`99b6511a2d5e…`, which the round-1 seal and the wave-2 corpora built before D-930 record) is archived byte-exact
      in `prov/catalogue/archive/agentprov-prov-0.1.v2.toml`, and `corpus.authority` answers it.
    - **Amended 2026-10-13 (regeneration-batch item 24; D-28 addendum 2).** A seal *issue* is addressable:
      `apv:dispatchStatus apv:NotDispatched` (`aprov.n_part@1`) takes its `unexecuted_tool_call` issue as premise,
      `apv:sourcePointer "seal/issues/<i>"` (position after every record), with the issue's rule as `apv:basisRule`.
      The premise's class is that rule's class. Tier 4 resolves the pointer into the seal and reads the issue's `rule` as
      the citation. Only an inference-bundle mention shows the pointer, so a D-class issue's statement is unchanged.
      `x:capture-profile` keeps its exemption: its premises are whole seal members, not one issue.
    - The model round trip works around caveat C9 (E.5.2). The unqualified-layer check belongs to the on-demand TriG
      writer and is `not_applicable` here.

## E.11 Implementation resolutions (phase 7: the assessment bundle, 2026-10-08)

The assessment bundle (`prov/rules/assess.py`, catalogue rules `aprov.a_*@1`) derives on every golden v1 AER with a
hand-built SEM document and passes every tier-4 check in release mode. The code is the reference; the gaps closed:

1. **Signature.** `derive(aer, sems=(), *, …, sem_profiles=None)`. `sem_profiles` maps `(profile id, version)` to the
   semantics profile; the engine reads only its identity, `sha256` and `taint_policy`, and never discovers profiles
   itself (adapter families are layer L4, `prov` is L2; MN M.5.1). The SEM rule catalogues the SEM header declares are
   looked up in `registry`. Tier 3 is the caller's duty; the engine checks the header and the shapes it reads.
   Typed failures: `prov.sem_stale` (`ex` or `aer_digest` of another AER), `prov.sem_profile_missing`,
   `prov.sem_profile_mismatch`, `prov.sem_duplicate_profile` (two documents of one profile would declare the same
   evaluation activity), `prov.sem_invalid`, plus `prov.method_set_empty`, `prov.unresolved_reference` and
   `prov.unresolved_pointer` for SEM premises. Assessment bundles follow the core and inference bundles, ordered by
   (profile id, version). With no SEM document the output is unchanged; the catalogue's new rules change only its
   digest, hence every `dk` and every PROV-JSON digest (`tests/golden/prov_digests.json` regenerated, verified
   byte-identical under the previous catalogue bytes).
2. **Key and names.** `dk` takes `sem_digest` = the SEM seal digest, `kind` = `assessment` and the profile slug
   (E.3.4). The evaluation activity is `x:assess.<profile-slug>` (`apv:PolicyEvaluation`, OBSERVED), associated with
   `sw:agentprov` and the plan `rules:<id>.<version>` under the new rule `aprov.a_evaluation@1` (E.7.2 item 2 names no
   rule). Mentions are `x:L(t).mn-<h12>` with `h12` over (dk, annotation id); assessments `x:as-<h16>` over (dk, rule,
   subject, object or `-`, claim), plus the discriminator `annotation=<id>` only when those repeat (E.10 item 14).
   Each assessment is generated by the evaluation activity (`wasGeneratedBy`, under the assessment's rule, carrying
   its evidence and `apv:premise` = the assessment). The mention's `prov:bundle` is the bundle that declares the
   subject (the core, or an inference bundle for an INFERRED node).
3. **Classes.** weakest(rule ceiling or path cap, the annotation's `ev`, its AER premise fields, its target field, the
   existence of the nodes named, premise statements). Ceilings: `a_label` O, `a_payload` D (`ambiguous` path I),
   `a_author` D (`authorship` path I), `a_exposure` D (a composition of two statements, like an inference), `a_taint` I.
   The method set of an INFERRED annotation is its I-class rules (looked up in the SEM-declared catalogues); an
   INFERRED engine ceiling adds the engine rule itself (`aprov.a_taint@1`, `aprov.a_author@1`,
   `aprov.a_payload@1`), as for any I-ceiling rule (E.1.5 item 4).
4. **Evidence.** `apv:sourcePointer` = the annotation's target (`<m>/parts/<k>` or `<id>`) and its AER premises (part
   premises render as `<m>/parts/<k><p>`), so they resolve like core pointers. A premise naming an earlier annotation
   becomes `apv:premise` (its statements). `apv:basisRule` adds the rules of a D or I annotation (and a marker's
   normaliser); their catalogues' assumptions are listed. Assessments cite premises: a label assessment its subject
   activity, a payload claim its part and fixture, authorship the mention, exposure the `use_context@1` and
   `gen_part@1` statements, taint the exposure and the role and integrity label statements it was selected by.
   Exposure and taint rest on statements only and carry no `apv:sourcePointer` (like `aprov.comm@1`).
5. **Payload method versus E.1.5 item 6.** E.7.3 asks for `apv:method` = the marker rule and normaliser on the
   DERIVED `present` claim; E.1.5 item 6 allows `apv:method` only on INFERRED statements, and the linkage validator
   enforces it. Resolution: the marker rule and the normaliser are `apv:basisRule`; `ambiguous` is INFERRED with
   `apv:method` from item 3, and its assumption is the one the SEM profile's marker rule or normaliser declares
   in the profile's catalogue (e.g. `agentdojo:…`, a string on `apv:adapterAssumption` like every adapter-declared
   term, item 11). No core term is added: apv 0.1.0 is published and E.4.6 allows no addition within a version
   (D-17). An ambiguous marker whose rules declare no assumption is refused (`prov.sem_invalid`).
6. **Selection (E.7.3 item 1).** A request's roles are the union of the role labels on the part and on the
   executions whose `call` it is; unlabelled is `unknown`. A context member's integrity is the meet (untrusted <
   unknown < trusted) over its parts, each unlabelled part `unknown` (message-level labels apply to unlabelled parts).
   A request not generated by a `model_call`, or whose invocation's input is unknown, has no exposure. A
   `tool_execution` without a request part has no generating invocation, so no exposure (EF over D.12.2 / K.6.4). All
   of these, the non-selected pairs, payload `absent`/`gap` and harness-default outcomes are counted in
   `DerivationReport.assessment[<bundle IRI>]`.
7. **Author value.** C.14.3 gives `author` the value `{"actor": Id}`, E.7.1 an author string. Both are accepted: the
   string (or the actor id) is `apv:declaredSender` and `apv:authorName`; an actor id with a node is also
   `apv:object` of the authorship assessment.
8. **Top level.** `aprov.t_annotate@1` per SEM document (`xd:sem.<slug>.<digest>`, `apv:semVersion "sem/0.1"`;
   `xd:annotate.<h16>` typed `apv:Annotation`, `h16` over `aprov-annotate/1` and the SEM digest); `aprov.t_plans@1` the
   profile as `prov:Plan` + `apv:SemanticsProfile` with its `apv:sha256`; `aprov.t_derive@1` `used(derive, sem)` and
   `wasDerivedFrom(bundle, sem, derive, g, u)`; the bundle entity carries `apv:profile "<id>@<version>"`. Catalogues
   declared only by a SEM header are not stated as plans.
9. **Tier 4.** `validate_prov(…, sems=…)`. Assessment bundles are kind `assessment`; their application view is the core
   and every inference bundle, plus the top-level engine agent and plans. `PV-NE-10` also checks the allowed forms
   (`pv.profiles.assessment_form`) and that no `aprov.a_*` rule, policy claim or SEM label property appears outside an
   assessment bundle (`pv.profiles.assessment_outside`); `pv.profiles.mentions` checks mention cardinality
   (`mention_cardinality`, `mention_bundle`, `mention_duplicate`); `pv.linkage.annotation` matches each bundle with its
   SEM document (`sem_missing`) and each `apv:annotationId` with its target. Linkage accepts SEM-cited basis rules, the
   SEM-declared catalogues, and I-capped `aprov` rules as methods inside assessment bundles.

---

## F.1 The evidence model

### F.1.1 Classes and admission tests (normative)

The three classes are those of [landscape/prov_semantics.md §2] and [audit/provenance.md], adopted unchanged in
meaning. They are encoded as AER `ev` = `O`, `D` or `I` (D2), as SEM `ev`, and as PROV `apv:evidenceClass`. Classes
are resolved by the adapter at map time (static model, AD-05); the tests below are what an adapter rule's class must
satisfy, and what the engine relies on.

| Class | Definition | Admission tests (all must pass) |
|---|---|---|
| **OBSERVED** (`O`, `apv:Observed`) | The value restates a field of an immutable raw artefact or capture event. The mapping is structural under the source format's documented schema | **T-O1:** the `src` locator resolves in a digest-checked raw artefact and yields the value. The value may differ only by a decoding that is value-preserving under the JSON data model (JSON parsing; JCS with the `ext.lex` hints of C.11.4). **T-O2:** nothing beyond the format's schema is needed: no assumption, heuristic, positional pairing or cross-record rule. Live context membership is therefore O only with recorded `input_at` positions (C.13; R-16); otherwise it is D under a named alignment rule. **T-O3:** an attesting party (`by`, or `O:<party>` in `evf`) is named (F.1.3) |
| **DERIVED** (`D`, `apv:Derived`) | A deterministic function of OBSERVED or DERIVED premises under a versioned rule, plus at most documented, code-cited, *verified* framework properties. PROV-CONSTRAINTS inferences over OBSERVED or DERIVED premises are DERIVED | **T-D1:** the rule is deterministic and versioned (`<ns>.<rule>@<n>` in a shipped catalogue). **T-D2:** every premise is an AER or SEM pointer, or a statement. **T-D3:** every assumption is in the core list (E.4.5) or adapter-declared `<ns>:<Name>`, and is `verified` for the identical producing framework identity (F.1.5), as resolved at map time. **T-D4 (counterfactual):** the conclusion cannot be false while *both* the source recorded faithfully *and* the framework behaved as its pinned code specifies |
| **INFERRED** (`I`, `apv:Inferred`) | Everything that fails T-D3 or T-D4: heuristics, policies, tables, models, judges, positional alignment where ids fail, claims supported only by documentation, assumptions merely `asserted`, and unknown code versions | **T-I1:** a rule whose catalogue class is I is cited. **T-I2:** `apv:method` is set, and `apv:confidence` is set when the method produces one. **T-I3:** the statement is never in the core (NE-11) |

```python
def classify(claim) -> EvidenceClass:      # reference procedure for catalogue authors (map time, static; AD-05)
    if claim.restates_raw_field and claim.structural_under_format_schema and claim.attested_by:
        return EvidenceClass.OBSERVED
    if (claim.rule.deterministic and claim.rule.versioned and claim.premises_citable
            and all(a.verified_for(claim.framework_identity) for a in claim.assumptions)
            and not claim.could_fail_under_faithful_source_and_pinned_code):
        return weakest(EvidenceClass.DERIVED, *[p.cls for p in claim.premises])
    return EvidenceClass.INFERRED
```

Two clarifications:
- OBSERVED means "the attesting party recorded this". It does not mean "this is true of the world". A
  provider-reported served model is `O by provider`.
- DERIVED is a promise *conditional on the pinned code*. That is why every DERIVED statement lists its
  assumptions.

### F.1.2 Fact versus interpretation (normative)

The class is that of the *claim asserted*, not of the computation that produced it. A deterministic computation
can support a DERIVED fact and, on top of it, an INFERRED interpretation. They MUST be emitted as different
statements with different classes.

| DERIVED fact | INFERRED interpretation |
|---|---|
| Argument leaf `v` occurs in the text of context message `i` | The argument was derived from message `i` (`aprov.i_arg_literal_overlap@1`, deferred) |
| The payload text occurs in the tool output under normaliser `N` (`apv:ContainsPayload`) | The injection influenced the agent's next call (`apv:PotentiallyInfluencedBy`) |
| Message `i` was in the request of the invocation that emitted request `k` (`apv:ExposedTo`, when membership is DERIVED) | Message `i` influenced request `k`: not observable (`apv:CapContextAttribution`); only estimates are possible |
| Tool `t` is listed in table `X` of profile `P@v` | The output of `t` is untrusted. A table is a policy and can be wrong while the framework behaves as documented: v2.2 labelled 279 entities trusted although they carried the payload [manuscript/review_feedback.md SEM-6] |
| The structured content declares sender `s` (`apv:declaredSender`) | `s` authored the content (`apv:QuotesAuthoredContent`; §13 E4) |
| The benchmark returned `security = true` (OBSERVED by benchmark) | The attack succeeded. This is DERIVED through the polarity rule, carried in the SEM `outcome` annotation, only when `origin` = `checker`; the benign constant and error defaults are not checker observations [audit/legacy_replay.md §1 item 5] |

### F.1.3 Attesting parties (`by`)

`by` (or the party of an `evf` value `O:<party>`) names *who recorded* an OBSERVED fact. It is copied into PROV as
`apv:attestedBy` for every OBSERVED premise of a statement.

| `by` | Who recorded it | What an OBSERVED fact then means | Caveats |
|---|---|---|---|
| `capture` | AgentPROV's live capture: the hash-chained `capture/0.1` log, wire blobs and environment digests (D3) | first-hand record of what crossed the instrumented boundary | subject to the observer effects declared in `execution.instrumentation` (D5). The default live LLM element is the stock (`native`) one recorded at the transport level; `gateway_compat` is an opt-in declared `request_modifying` (AD-09) |
| `source` | the original harness's own log, for example AgentDojo `TraceLogger` JSON | the harness logged it | inherits the logger's semantics: last write wins, arguments mutated in place, last pass only [sources/agentdojo.md §3, §3.5] |
| `provider` | the model API's self-report: served model, usage, finish reason | the provider said so | not checkable by AgentPROV |
| `benchmark` | the benchmark checker's verdict | the checker returned this value | the *meaning* comes from a rule, carried by SEM; runner defaults are not verdicts (`origin` ≠ `checker`) |
| `config` | the harness's input configuration: requested model, configured parameters, registered injections | the value was *configured* | configured is not effective: temperature configured but not transmitted [docs/capture_spec.md §4.1; DECISIONS D5] |
| `replay` | a re-execution of recorded calls (AgentPROV's own replay is deferred, AD-10 row 2; imported replay values keep `by: replay`) | an observation *of the replay*, not of the original | relating it to the original needs `apv:ReplayFaithful` and is assessment-only. Logged and replayed outcomes disagree in golden traces R05, C04 and C06 [baseline/BASELINE.md §7] |

Consumers MAY filter on `apv:attestedBy apv:ByCapture` to obtain first-hand evidence only.

### F.1.4 Propagation (weakest premise)

The class of every node, attribute and statement is computed by E.1.5 item 2: the minimum of the rule ceiling,
the premise field classes (which include their assumptions, AD-05), the existence classes of the endpoints and the
premise statement classes.

- A PROV-CONSTRAINTS inference has ceiling DERIVED even when every premise is OBSERVED
  [landscape/prov_semantics.md §2].
- A rule whose required premise is unknown does not fire, so no class is computed for it.

Worked propagation:

| Case | Premises | Result |
|---|---|---|
| Native AgentDojo log, `tool_exec → llm_m'` | `g`: tool message ← tool execution, DERIVED iff `agentdojo.tool_msg_is_one_execution@1` is verified over the producing code range, else INFERRED; `u`: `used(llm_m', message)`, INFERRED (`agentdojo.context_is_prefix@1`) | INFERRED; inference bundle `inf.agentdojo-context_is_prefix-v1` (or the union method set if `g` is also INFERRED) |
| Released v1 transcript, same edge | `u` INFERRED (`adprov.context_is_prefix@1`): `apv:FullContextResend` cannot be verified, because the request was built by AgentDojo-PROV's unversioned `_CompatLLM` and a version string never suffices (AD-05; R-05) | INFERRED; inference bundle `inf.adprov-context_is_prefix-v1`, unless the user supplies a digest-pinned generation-time harness (U-01) |
| Live capture, same edge | `u` OBSERVED (by capture, with `input_at`) or DERIVED (alignment rule); `g` OBSERVED | DERIVED (the ceiling of the inference); core |
| Taint | exposure (class of the context membership); labels INFERRED; policy INFERRED | INFERRED; assessment |

### F.1.5 Assumptions: static resolution, verification and citation (normative)

1. **Where assumptions live.** On adapter rule-catalogue entries (D.5.2 `assumptions`), never in source profiles
   (R-09). Each entry that relies on an assumption carries its verification in the shape
   `{framework_identity, code_ref, test}` (RESOLUTIONS §3.8; format owned by D.5.2): the framework identity is a
   distribution plus a commit or wheel hash; the code reference is repository, commit, path and lines; the test is a
   test node id or an investigation report section.
2. **Static resolution (AD-05(a)).** The adapter emits each rule at its effective class at map time. A rule whose
   assumption is verified for the identical framework identity is cited at class D; otherwise its I twin is cited
   (D.5.2 item 7). A change of verification status is a new rule id or catalogue version, so it changes the AER
   digest and every `dk`. The engine reads classes only (E.1.5 item 3).
3. **What `verified` requires.** A test or an audit at the *identical* framework identity: the distribution together
   with a commit or wheel hash.
   - Version strings never suffice. AgentDyn and AutoDojo both call themselves `agentdojo 0.1.35` (D9;
     [audit/capture.md §9.6]).
4. **Identity match, enforced by the AER validator (C.17).** A rule cited at class D whose catalogue entry names a
   `verified` assumption MUST name a commit or wheel hash equal to the code identity recorded in the AER (the `code`
   of the `harness` or `benchmark` actor, C.3.2). Otherwise the AER is invalid: the adapter should have cited the I
   twin.
5. **A code range.** For logs produced by a code *range*, an assumption is `verified` only if it was verified at
   every commit in the range that touched the code concerned. The June-2024 AgentDojo logs accumulated across
   revisions under skip-if-exists [audit/legacy_replay.md §2.2], and their profiles record
   `code_identity = "unpinned"` (D.5.3).
6. **Extension assumptions.** An adapter family MAY declare assumptions `<ns>:<Name>` in its catalogue, with the same
   verification shape; the catalogue self-test and the AER validator check them as in items 3–5 (AD-05(b)(i)). Only
   core `apv:` individuals may appear as `apv:assumption` (QNames) and only declared `<ns>:<Name>` terms as
   `apv:adapterAssumption` (strings; E.10 item 11); a validator MUST reject any other. The rule follows the
   document's `apv:vocabularyVersion`: an apv 0.1.0 document carries both forms on `apv:assumption` (D-17) and no
   `apv:adapterAssumption`, and the validator accepts it as such. An absent or unknown version gets the current rule.
7. **No hidden input.** Because classes are fixed in the AER and catalogue versions are in its header, `derive` has
   no profile or assumption status as input, and bundle identity holds (E.3.4 item 4).

### F.1.6 Unknown statuses across AER, SEM and PROV

| Situation | AER | SEM | PROV |
|---|---|---|---|
| The format has no slot (per-call times in native logs; request payloads) | `unk: {"/t": "not_recorded"}` | — | `apv:startTimeStatus` and `apv:endTimeStatus` `apv:NotRecorded`; the capture profile's `apv:notProvided` includes `apv:CapToolTimes` |
| Earlier passes not held | `attempt` scope `unk: {"/index": "lost"}`; seal issue `earlier_attempts_unobservable` (rule `agentdojo.log_holds_last_pass@1`, assumption `apv:LastPassOnlyLogging`) [landscape/trace_formats.md §6.7] | — | `apv:indexStatus apv:Lost`; `apv:issue`; `apv:notProvided apv:CapEarlierPasses` |
| Overwritten in place by a defence | `decision` with `unk: {"/original": "overwritten"}` (C.3.7) | — | `.out` or `.pre` entity with `apv:contentStatus apv:Overwritten`; `aprov.decision@1` |
| Arguments mutated in place before logging | the request part's `args` as logged (rule `agentdojo.args_are_effective@1`) and the `unk` the profile declares on `/parts/<k>/args_raw` (C.3.4.1) | — | `apv:args` as logged; `apv:argsRawStatus` with the declared status |
| Provider withholds reasoning (OpenAI Chat Completions returns a token count only [docs/capture_spec.md §4.1]) | `unk` with reason `withheld` | — | `apv:contentStatus apv:Withheld` (on a reasoning part) or an `apv:Gap` |
| Passed-back reasoning not held (reasoning-returning models in the release; §13 G2) | `unk: {"/input": "not_captured"}` or `"ambiguous"` on those calls | — | `apv:contextStatus apv:NotCaptured` or `apv:Ambiguous`; no context usages |
| Ambiguous value (Gemini `""` ids; naive local timestamp) | `unk` with reason `ambiguous`; for times, `t.raw` keeps the verbatim value | — | `apv:providerCallIdStatus apv:Ambiguous`; `apv:startTimeLexical` + `apv:startTimeStatus apv:Ambiguous` |
| Live capture failed | `not_captured`; accounting `inconsistent` | — | `apv:NotCaptured`; `apv:accounting` on the capture profile; the execution is kept, never dropped (D5) |
| The source recorded null | value `null` with `ev: O` | — | `apv:contentStatus apv:RecordedNull` (part content), else `apv:<p>Status apv:RecordedNull` and no `<p>` (E.10 item 5) |
| Unknown label (unclassified tool) | — | `integrity: unknown` (three-valued, fail-closed) with `ev` and `rule` | mention with `apv:integrity apv:IntegrityUnknown`; taint policy includes it |
| Runner-default outcome | `judgement.origin = "harness_default"` | no `outcome` annotation (C.14.3) | `apv:outcomeOrigin apv:OriginHarnessDefault`; attributed to the harness; no checker run (`aprov.outcome@1`) |
| Order unknown | no `after` edge, or `unk: {"/after": "not_recorded"}` | — | no `apv:after*` value; `apv:orderStatus apv:NotRecorded` when declared. Consumers MUST NOT read concurrency into it (NE-9) |
| Unobservable in principle (which context items caused an argument) | — | — | the capture profile's `apv:notObservable apv:CapContextAttribution`; estimates only in inference bundles |
| A construct `aer/0.1` cannot carry (an in-file branch; the edited request of an approval `modify`) | seal issue (for example `inspect.branch_unsupported`), or `ext` | — | no PROV statement; an `apv:Gap` where a node exists (NE-18); the disclosed gap is counted in the derivation report |

### F.1.7 How consumers filter

1. **Core only (OBSERVED and DERIVED)** is the default reading. Any of the following gives it:
   - the top level plus `bundle["xd:bundle.core.<dk>"]` of the PROV-JSON;
   - the named graph `<core bundle IRI>` of an on-demand TriG;
   - `agentprov render`, which draws the core bundle only unless other bundles are requested (AD-10 as ruled in
     Addendum B; the `render` extra).

   Thanks to the unqualified layer, `GRAPH <core> { ?a prov:used ?e }` works in SPARQL.
2. **OBSERVED only.** Read the core, keep nodes and statements whose `apv:evidenceClass` is `apv:Observed`, and
   drop the attributes listed in `apv:derivedAttribute`. In SPARQL, filter through the qualified node:
   `?a prov:qualifiedUsage ?u . ?u prov:entity ?e ; apv:evidenceClass apv:Observed`.
3. **With inferences.** Add the inference bundles of chosen methods, explicitly. Consumers SHOULD report which
   method sets they accepted. For imported corpora, context membership and the `tool → llm` and `llm → llm`
   communications are in the context inference bundle (AD-05).
4. **Security view.** The core plus one assessment bundle (plus the context inference bundle for imports).
5. **Counts.** `agentprov stats` reports PROV statements by evidence class, bundle and rule from the derivation
   reports (AD-10 as ruled in Addendum B).
6. **No blanket union.** The union of all graphs mixes evidence regimes. It MUST NOT be presented as "the
   provenance" of an execution.

### F.1.8 Reconciliation with earlier classifications

| Claim | Earlier classification | This specification | Why |
|---|---|---|---|
| Context member used by the *invocation* | AR-1 [manuscript/review_feedback.md §5] and [audit/legacy_replay.md §6]: "inferred"; [landscape/prov_semantics.md R-USE-CTX]: DERIVED or OBSERVED | OBSERVED (captured request with `input_at`, or a recorded as-sent input); DERIVED (alignment rule, or assumption verified at the identical framework identity); INFERRED otherwise, including the released v1 corpus and native imports (AD-05) | AR-1 and legacy_replay judged the v2.3 edges. Those attach context to the *tool execution* (the wrong activity) through a previous-turn window. In the decomposed model, membership follows from pinned code (T-D4) where the code is pinned |
| Matching an argument against content | AR-1: "derived"; prov_semantics: INFERRED | the match is DERIVED; the derivation claim is INFERRED | F.1.2 |
| Integrity, role and channel from tool tables | [audit/legacy_replay.md §6]: "derived (AgentDojo policy)"; [landscape/trace_formats.md §6.13]: sink DERIVED; [audit/provenance.md §4.2]: INFERRED | INFERRED | Fails T-D4 (SEM-6) |
| Injection marker | DERIVED [audit/provenance.md §6] | DERIVED as containment, in assessment; ambiguous readings INFERRED | Deterministic matching; Challenge 1(f) |
| Injection placement in the initial environment | prov_semantics R-INJ-ENV: OBSERVED | DERIVED | Placement is benchmark semantics, not recorded (T-O2 fails) |
| Native AgentDojo `model_call.input` | [landscape/trace_formats.md §6.13]: INFERRED; [sources/agentdojo.md §7.1]: derived ("protocol-level") | INFERRED by default; DERIVED iff the catalogue entry verifies `apv:FullContextResend` over the producing code range | The producing version is not recorded: old-format logs have none, and `agentdojo_package_version` is always `"unknown"` in the new format [sources/agentdojo.md §6] |
| `wasGeneratedBy(output, tool execution)` | OBSERVED [audit/provenance.md §4.1] | OBSERVED for capture and v1; for native logs, DERIVED iff verified over the producing code range, else INFERRED | Weakest premise: the execution's existence rests on `agentdojo.tool_msg_is_one_execution@1` |
| Authorship of structured content | prov_semantics R-ATTR-AUTHOR: OBSERVED-from-content | declared sender DERIVED (parse fact); authorship INFERRED | §13 E4: the field an injection forges |

---

## F.2 Worked classification tables

The "Rule" column gives the AER rule id where one applies (adapter rules from D.5.4, D.7, D.8 and D.9), then the
engine rule. "→ inf" marks routing to an inference bundle. Where a native row's class depends on verification over a
code range, the catalogue entry (D.5) must cite that range; until it does, the I twin applies (AD-05).

### F.2.1 AgentDojo native log

The examples are a June-2024 log of the converted corpus, pinned at upstream `c274885…` [audit/legacy_replay.md
§1 item 2], whose profile records `code_identity = "unpinned"`, and a newer upstream log at `089ed468`.

| # | Fact | Class (`by`) | Rule | Justification |
|---|---|---|---|---|
| 1 | Artefact bytes, repo, commit, path, git blob | O (top level) | ingest → `aprov.t_raw@1` (`prov_primary` = `native`) | digest verified at ingest; the blob SHA-1 matched for all 18,234 June logs [audit/legacy_replay.md §1 item 2] |
| 2 | Suite, user task, injection task, attack type | O (source) | → `aprov.n_header@1` | top-level fields [sources/agentdojo.md §3.3] |
| 3 | The 432 "injection task as user task" logs are solvability pre-passes | D | `agentdojo.injection_task_as_user_task@1` → header | `benchmark_suite_with_injections` [audit/legacy_replay.md §1 item 6] |
| 4 | Defence identity (pipeline-name suffix) | I | `agentdojo.defence_suffix@1` (class I unless the profile verifies the naming convention over the producing code range; June-2024 logs are unpinned) → `apv:defenceId` (→ inf mention) | free-text convention; `pipeline_name` is free text in ROPE logs [landscape/trace_formats.md §3.10] (R-09) |
| 5 | Requested model | I | `agentdojo.pipeline_dir_is_model_identity@1` → `apv:requestedModel` on the model entity (→ inf mention); served model `apv:NotRecorded` | [landscape/trace_formats.md §6.6; D.5.4] |
| 6 | Payload per vector | O (source) | → `aprov.n_fixture@1`, `aprov.attr_fixture@1` (configuration provenance, AD-11) | `injections` |
| 7 | System, user, assistant and tool message content | O (source) | → `aprov.n_message@1`, `aprov.n_part@1` | as logged; tool content is *post-defence* [audit/legacy_replay.md §6] |
| 8 | A model call per assistant message | D iff verified over the producing code range, else I | `agentdojo.assistant_msg_has_one_call@1` (or its I twin) → `aprov.n_model_call@1` | undefended pipelines; `tool_filter` needs an auxiliary-call rule [landscape/trace_formats.md §6.6] (R-05) |
| 9 | The invocation input is the message prefix | I | `agentdojo.context_is_prefix@1` → `aprov.use_context@1` (→ inf) | producing code version unknown (F.1.8) |
| 10 | A tool execution per tool message | D iff verified over the producing code range, else I | `agentdojo.tool_msg_is_one_execution@1` (or its I twin) → `aprov.n_tool_execution@1` | `tool_execution.py:58-115` (R-05) |
| 11 | Call↔result link | D (unique id) or I (positional: Gemini `""`, duplicate ids in 213 GPT logs) | `agentdojo.call_id_unique_match@1` or `agentdojo.positional_match@1` → `aprov.use_request@1` | [landscape/trace_formats.md §3.10, §6.5] |
| 12 | Arguments | O (source) as logged, *post-mutation*; the arguments as emitted are not recoverable | `agentdojo.args_are_effective@1` → `apv:args` on the request part; `apv:argsRawStatus` from the declared `unk` | `ToolsExecutor` mutates `args` in place [sources/agentdojo.md §3.5] |
| 13 | Tool error | O (source) | → `apv:error` on the tool_result part | — |
| 14 | Requested but unexecuted calls (815 at HEAD) | D (accounting) | `agentdojo.unexecuted_trailing_calls@1`; seal issue `unexecuted_tool_call` → `apv:dispatchStatus apv:NotDispatched`; no activity (NE-12) | [landscape/trace_formats.md §3.10] |
| 15 | Message order | D iff verified over the producing code range, else I | `agentdojo.messages_append_ordered@1` (`b: pos`) → `apv:afterPos` (INFERRED edges routed out of the core, R-53) | sequential executor (`apv:SequentialToolExecution`, `agentdojo.tools_executed_sequentially@1`) (R-05) |
| 16 | Run duration | O (source) | → `apv:durationSeconds` on `apv:Run` | covers environment load, every pass *and* the checks (`agentdojo.duration_scope@1`) [audit/legacy_replay.md §2.2] |
| 17 | `evaluation_timestamp` (new format) | O lexically; UTC `apv:Ambiguous` | `agentdojo.naive_local_timestamp@1` → `apv:startTimeLexical`, `apv:startTimeStatus apv:Ambiguous` | naive local time [sources/agentdojo.md §6] |
| 18 | Per-call and per-message times | `apv:NotRecorded` | `aprov.status@1` | — |
| 19 | `utility` and `security` values | O (benchmark); `origin` per rule | → `aprov.n_judgement@1`, `aprov.outcome@1` | — |
| 20 | Security polarity (attack succeeded; DoS: `not utility`) | D | `agentdojo.security_polarity@1`, `agentdojo.dos_security_rule@1` → SEM `outcome` → `aprov.a_label@1` | runner code [audit/legacy_replay.md §2.2] |
| 21 | Benign `security = True`; error defaults (`False`, `True`) | O as logged; `origin` = `harness_default` | `agentdojo.benign_security_constant@1`, `agentdojo.run_error_imposed_outcome@1` → no checker run; attributed to the harness | runner defaults [audit/legacy_replay.md §1 item 5] |
| 22 | Earlier passes | `apv:Lost` (in old logs, even their existence cannot be detected) | `agentdojo.log_holds_last_pass@1` (`apv:LastPassOnlyLogging`); seal issue; capture profile | [sources/agentdojo.md §7.2] |
| 23 | PI-detector redaction | I | `agentdojo.pi_detector_sentinel@1` → `aprov.decision@1` (→ inf); pre-decision entity `apv:Overwritten` | sentinel string [landscape/trace_formats.md §6.6] |
| 24 | Environment state; tool definitions offered | `apv:NotRecorded` | no state entities; no `aprov.use_tools@1`; no state usage by the checker | [sources/agentdojo.md §6] |
| 25 | `tool_exec → llm` communications | I | `aprov.comm@1` (→ inf) | inherits row 9 |
| 26 | `llm → tool` communications | D iff rows 8 and 11 are D, else I | `aprov.comm@1` | weakest premise (R-05) |
| 27 | Integrity, role, channel | I | SEM tables → `aprov.a_label@1` | F.1.2 |
| 28 | Payload surfaced in tool output | D | SEM marker with YAML normaliser → `aprov.a_payload@1` | `tool_result_to_str` with `yaml.safe_dump` in both eras [audit/legacy_replay.md §2.2] |
| 29 | Exposure and taint | I and I | `aprov.a_exposure@1` (I, because row 9 is I), `aprov.a_taint@1` | weakest premise |
| 30 | Auto-execution: the tool start by the issuing call, and the runtime acting for the agent | I | `agentdojo.auto_execution_unverified@1` (on `env/on_behalf_of`) → `aprov.start_tool@1`, `aprov.assoc_tool@1` delegation (→ inf) | `ToolsExecutor` dispatches every call; the producing code is not identified (E.10 item 21) |
| 31 | What the checker read (output text, call trace; states where entities exist) | I | `agentdojo.checker_inputs_unverified@1` (on `origin: checker` judgements) → `aprov.outcome@1` usages of the synthetic checker run (→ inf); the run itself is DERIVED, in the core | same (E.10 item 21) |

### F.2.2 AgentDojo-PROV transcript/v1

The example is a released-corpus transcript (agentdojo 0.1.35, live capture of 2026-06). Rows 16–17 cover the
converted legacy transcripts.

| # | Fact | Class (`by`) | Rule | Justification |
|---|---|---|---|---|
| 1 | Transcript artefact and manifest checksum | O | → `aprov.t_raw@1` | — |
| 2 | Requested model (`meta.model_id`) | O (config) | → `apv:requestedModel` | — |
| 3 | Provider-returned model (`model_config.response`), where present | O (provider) | → `x:L(a).svc` | per-model presence not measured in the reports |
| 4 | Message content, including tool content and `content_sha256` | O (capture) | → message and part rules | — |
| 5 | A model call per assistant message | D | `adprov.assistant_turn_one_call@1` + usage-count accounting: 14,567 consistent, 153 re-run, 2,944 unverifiable (DeepSeek) | [docs/capture_spec.md §4.3] |
| 6 | Invocation input = the whole pass | I | `adprov.context_is_prefix@1` → `aprov.use_context@1` (→ inf `inf.adprov-context_is_prefix-v1`). `apv:FullContextResend` is not verified: the request was built by AgentDojo-PROV's own `_CompatLLM.query` (`runtime.py:239`), whose generation-time code is not pinned, and a version string never suffices (AD-05; R-05). DERIVED only if the user supplies a digest-pinned generation-time harness (U-01). For reasoning-returning models, `/input` is `not_captured` or `ambiguous` instead (§13 G2) | [landscape/prov_semantics.md §4.1; O OM-5] |
| 7 | Sent transforms (role rewrite, reasoning pass-back, error substitution) | D iff the producing AgentDojo-PROV commit is identified, else I | → `apv:sentTransform`, or `aprov.a_sent_transform@1` (→ inf) | transcripts record no framework commit [audit/corpus.md §3.3 R6] |
| 8 | Tool start and end times | O (capture) | → `prov:startTime`, `prov:endTime` on the execution | 64,779 of 64,781 timed [audit/provenance.md §6] |
| 9 | Shared start time (GLM-4.6 `call_3275` reuse) | `apv:Ambiguous` | `unk` → `apv:startTimeStatus apv:Ambiguous` (2 activities) | timing keyed by a reused id [docs/capture_spec.md §5.2] |
| 10 | Call↔result link | D | unique id match within the issuing message → `aprov.use_request@1`; the importer verifies `tool_call_id` equals the paired call id (R-30) | — |
| 11 | Reasoning text | I | `adprov.reasoning_log_alignment@1` (native-block versus log-aligned origin undecidable) | absent from every released transcript [landscape/trace_formats.md §3.11; D.7.3] |
| 12 | Earlier passes | `apv:Lost` in the 153 traces flagged as re-run | seal issue | [docs/capture_spec.md §4.2] |
| 13 | Injections | O (config) | → `aprov.n_fixture@1` | — |
| 14 | Outcomes | O (benchmark), `origin` per D.7.3; replayed values carried by a source map by `origin` | `aprov.outcome@1` | F.1.3 |
| 15 | Environment digests | `apv:NotRecorded` (no transcript carries `meta.capture`) | — | [baseline/BASELINE.md §8 item 2] |
| 16 | Converted transcripts: tool times `"0"` with `timing_stubbed` | `apv:NotRecorded`; the sentinel is never emitted as a time | AER `t.raw` verbatim plus `unk` on `/t/start` and `/t/end` (C.7.3) | [audit/legacy_replay.md §1 item 7] |
| 17 | Converted transcripts: primary source | — | the native June-2024 log is the primary source; the converted transcript is a re-generated artefact with `prov_primary` = `secondary`, so no `hadPrimarySource` to it (NE-20) | [audit/legacy_replay.md §1 item 8; §13 E13] |
| 18 | Integrity, marker, exposure, taint | as in F.2.1 rows 27–29: exposure is I because row 6 is I | — | — |
| 19 | Auto-execution; checker inputs | I | as F.2.1 rows 30–31 (the importer cites the same two `agentdojo` rules) | the released transcripts record no harness commit |

### F.2.3 Live capture (`capture/0.1`, AgentDojo backend, D5)

| # | Fact | Class (`by`) | Rule | Justification |
|---|---|---|---|---|
| 1 | Messages in the wire request | O (capture) with recorded `input_at`; otherwise D under the named alignment rule, with an accounting check | `model_call.input` → `aprov.use_context@1` (core) | wire evidence per LLM call [audit/capture.md §9.3]; positions recorded by the LLM-span brackets (C.13; R-16; PROV-03) |
| 2 | Tool definitions in the request | O (capture) | `model_call.tools` → `aprov.use_tools@1` | — |
| 3 | Transmitted versus configured parameters | O (capture) and O (config) | → `apv:paramsTransmitted`, `apv:paramsConfigured` | for example, temperature not transmitted (D5) |
| 4 | Raw responses, including discarded replies and retries | O (capture) | `model_call.status` `discarded`; retries linked by `retry_of` → activities with `apv:retryOf` | resample and retry counts are recorded per execution (AD-09) |
| 5 | Served model | O (provider) | `model_call.served_model` → `x:L(mc).model`; `apv:InferenceProvider` association | — |
| 6 | Model-visible tool text versus raw output | O (capture) | in-request transforms → `apv:sentTransform` (OBSERVED, from the wire request); for defences, `aprov.decision@1` with the captured `decision.original` (no `apv:Overwritten`) | [audit/capture.md §9.3] |
| 7 | Dispatch occurrence id, requested and effective args, dispatch status | O (capture) | → execution; `aprov.use_request@1` OBSERVED (structural occurrence link) | fixes id reuse at the source |
| 8 | Pass boundaries, including aborted passes | O (capture) | → `apv:Pass` | — |
| 9 | Environment digests before and after each pass | O (capture); carry-over D | → `aprov.env_pass@1` under `apv:EnvironmentCarriedOver` (agentdojo 0.1.35 `task_suite.py` l.383–394), predecessor along `after` edges | [docs/capture_spec.md §4.3; §13 E6] |
| 10 | Wall-clock and monotonic times | O (capture) | wall clock → `prov:startTime`, `prov:endTime`; monotonic → AER `t.mono_*` only | — |
| 11 | Declared instrumentation | O (capture) | `execution.instrumentation` → `apv:instrumentation` on `x:exec`. The default LLM element is stock (`native`); `gateway_compat` is an opt-in declared `request_modifying`/`harness_policy`, which triggers NC-LIVE-01 | D5; AD-09 |
| 12 | Accounting result | D | → capture profile `apv:accounting` | [audit/capture.md §9.4] |
| 13 | Auto-execution; checker inputs | auto-execution D (verified against the pinned agentdojo 0.1.35); checker-input assumptions per task: D for audited checkers, else I | `aprov.start_tool@1`, `aprov.assoc_tool@1`, `aprov.outcome@1` | R-05; §13 E5 |
| 14 | Outcome and its polarity | O (benchmark); polarity D in SEM | `aprov.outcome@1`; `aprov.a_label@1` | — |
| 15 | Communications | D (the inference ceiling) | `aprov.comm@1` | F.1.4 |
| 16 | Native `TraceLogger` JSON written alongside | O (source), as a second raw artefact (`native_log`) | not merged into the AER statements; used by the live-versus-native differential test (D3, D8 tier 6) | — |
| 17 | Which context items determined an argument | `apv:NotObservable` | capture profile; estimates only (E.1.7, deferred) | — |

### F.2.4 A STAC case (MultiTurnAgentAttack; design note while STAC is `planned`)

The source is `data/STAC_benchmark_data.json`, 483 records [sources/multiturn-agent-attack.md]. STAC records are
scenario records, not executions (`execution.unit` = `scenario`; rule `stac.case_is_one_scenario@1`; R-28), and the
STAC importer is `planned` (A6). The rows record the intended classification.

| # | Fact | Class (`by`) | Rule | Justification |
|---|---|---|---|---|
| 1 | Record bytes (array file plus element) | O | → `aprov.t_raw@1`; locator `{"p":"/<i>"}` | the file re-serialises byte for byte [§3] |
| 2 | Generator, verifier, prompt-writer and planner model *names* | O (source); served `apv:NotRecorded` | → `attacker` actors with roles `tool_chain_generator`, `tool_chain_verifier`, `prompt_writer`, `attack_planner`, `context_fabricator` (D.8.2), with `apv:requestedModel` | names only; no snapshots [§4] |
| 3 | `attack_plan.verified_tool_chain` | O (source) | → `apv:AttackPlan` (⊑ `prov:Plan`) | — |
| 4 | `environment_changes` | O as text only; **never** a state entity | `ext.stac` | predictions, not observations [§6.2] |
| 5 | Content of the prefix user turns | O (source) | → messages | — |
| 6 | Authorship of the prefix turns (prompt writer) and of the final prompt (planner) | I | `stac.prefix_user_turns_by_prompt_writer@1` → `aprov.attr_message@1` (→ inf) | taken from code; the record does not tag the author [§6.1] |
| 7 | Final user prompt = `planner_history[0].predicted_attack_prompt` | D (string equality, 482 of 483) | `stac.final_prompt_from_planner@1` → `wasQuotedFrom(user message, planner output)`, not `wasGeneratedBy` (R-56; PROV-16(b)); the planner output needs an entity (a planner message or an `artefact`) before this can be emitted | [§3.2] |
| 8 | Scripted assistant tool calls (775) | content O; actor = STAC script (`attacker`, role `context_fabricator`), I | `stac.assistant_turns_scripted@1` → `aprov.attr_message@1` (→ inf); never an LLM (NE-13) | [§3.3] |
| 9 | Decoded arguments | D; raw string O | `stac.double_json_arguments@1` → `apv:args`, `apv:argsRawSha256` | the arguments are double-encoded [§3.2] |
| 10 | Tool results | content O (source); execution existence D | → `aprov.n_tool_execution@1`, `aprov.gen_result@1` | real environment outputs from the step-3 run [§0] |
| 11 | Call↔result link | D | unique 32-hex ids; adjacency holds 778/778 → `aprov.use_request@1` | [§3.2, §7.2] |
| 12 | Message order | D where position equals occurrence; `proto` edges where they diverge | `stac.history_order@1` → `apv:afterPos`, `apv:afterProto`; array order is not generation order | [§3.3; C.8.2] |
| 13 | Planner outputs | content O; planner model call D; input `apv:NotRecorded` | → `aprov.n_model_call@1` (no `aprov.use_context@1`) | — |
| 14 | Target-agent response (482 records) | `apv:NotRecorded`: absent; the target agent is `unk`, not an asserted `llm_agent` | no target model call; capture profile | [§0] |
| 15 | Record 139's real agent turns | content O; model calls I; agent model `apv:NotRecorded` | `stac.call_prefix_ids_are_agent_output@1` → model-call rules | [§3.5] |
| 16 | Outcomes and judge scores | `apv:NotRecorded` (not released) | no judgement; seal issue | [§4] |
| 17 | Times; system prompt | `apv:NotRecorded` | — | [§4] |
| 18 | ASB environment link (only 4 of 93 consistent) | `apv:Ambiguous` | `stac.asb_id_link_check@1` → header environment + status | [§5.3] |
| 19 | The agent acts for the user | not applicable: the user turns are the attacker's | no `on_behalf_of`; `aprov.deleg_user@1` does not fire | [§4] |
| 20 | User turns are attacker-controlled | D (rule in SEM) | → `aprov.a_label@1` | "by construction" [§4] |

### F.2.5 Inspect AI `.eval` (survey AgentHarm; the D.9 gate)

This table is the classification gate of the normative Inspect importer (D.9; AD-06; R-07) for producer band
`inspect_ai 0.3.247.dev69` (survey AgentHarm: 6 logs, 1,056 samples). Adapter rule ids, accounting checks and issue
codes are owned by D.9; the engine rules are those of E.1. The DoD item is "all 6 survey AgentHarm logs import,
derive and validate end to end". The importer needs no EF change beyond those specified in this revision
(`apv:CacheRead`, `aprov.authorise@1`, `aprov.spawn@1`, `aprov.state_patch@1`, judge provenance in
`aprov.outcome@1`, `apv:Truncation`); any further change MUST be listed here (HON-09(3)).

| # | Inspect construct | AER | Class (`by`) | Engine rule | Notes |
|---|---|---|---|---|---|
| 1 | `.eval` archive and its members (zip methods 0, 8, 93) | artefacts: member objects of the `expand` stage, origin kind `member` (AD-12) | O (top level) | `aprov.t_raw@1` | extraction-free ingestion (A2) |
| 2 | `header.eval` (task, model, generate config, packages) | `execution` (`unit` = `agent_execution`), `task`, agent `model.requested`, `params.configured` | O (source, config) | `aprov.n_header@1`, `aprov.n_actor@1`, `aprov.n_model@1` | the producer band is in the profile |
| 3 | sample `id`, `epoch`, `started_at`, `completed_at` | scope `run` with `t` (µs UTC) | O (source) | `aprov.n_scope@1` | — |
| 4 | `input_refs`, `events_data`, `attachment://` references | resolved into message parts and inputs without fabrication; a dangling reference raises an issue and the field is `unk` | O, or status | `aprov.n_part@1`; `aprov.status@1` | D.9.1 |
| 5 | `ModelEvent` (kept) | `model_call` with `input`, output message (`generated_by`), `usage`, request and response blobs | input O when `ModelEvent.call` holds the as-sent request; otherwise D under the D.9 rule that the framework-level input is what was sent (PROV-11(c)) | `aprov.n_model_call@1`, `aprov.use_context@1`, `aprov.gen_message@1`, `aprov.use_model@1`, `aprov.assoc_model_call@1` | — |
| 6 | `ModelEvent` read from cache (`cache == "read"`) | `model_call` `status` = `cached` | O (source) | `apv:CacheRead`: no model usage, no provider association | PROV-11(a) |
| 7 | `ModelEvent` with an error | `model_call` `status` = `error` | O (source) | invocation with no output, no model usage, no provider association | PROV-11(a) |
| 8 | `CompactionEvent` | a model-generated summary: a `model_call` that generates the summary message; edit and trim: an `activity` (`inspect:compaction`) whose `inputs` are the affected messages; otherwise `ext` plus an issue | O (source) | `aprov.gen_message@1`; G-ACT, G-USE | PROV-11(b); E.6.2 item 5 |
| 9 | `ToolEvent` | `tool_execution` (`call` = the part whose `ToolCall.id` equals the event id); result message `generated_by` it | link D; content O | `aprov.n_tool_execution@1`, `aprov.use_request@1`, `aprov.gen_result@1` | — |
| 10 | `ToolEvent.truncated` | a `truncation` sent transform on the later usage when the truncation happens while the request is built; a `decision` when a separate element truncates | O or D | `aprov.use_context@1` qualifier; or `aprov.decision@1` | `apv:Truncation` (PROV-11(c)) |
| 11 | `ApprovalEvent` | `decision` (approve, modify, reject, escalate, terminate → allow, modify, deny, escalate, terminate); `tool_execution.authorised_by` for an approval | O (source) | `aprov.decision@1`; `aprov.authorise@1`; NE-18 for `modify` | PROV-11(d); `apv:AutoExecution` does not fire |
| 12 | `StateEvent`, `StoreEvent` (JSON patches) | `state_change` with `patch` | O (source) | `aprov.n_state@1`, `aprov.state_patch@1` | EXT-03 |
| 13 | judge spans (`scorer:*`) and judge model calls | `judge` actor; judge `model_call`s; `judgement.generated_by` = the judge call or scorer span; `judgement.inputs` | O (source); links D | `aprov.outcome@1` (generated-by path) | R-37 |
| 14 | `ScoreEvent` / `scores` (AgentHarm `score`, `refusal`) | `judgement` with `origin` = `checker` | O (benchmark) | `aprov.n_judgement@1`; polarity and grading in SEM `outcome {claim, score, scale}` | R-18 |
| 15 | sub-agent spans | `scope` of kind `subagent` with `spawned_by` | O or D | `aprov.spawn@1`, `aprov.assoc_scope@1` | PROV-11(e) |
| 16 | `BranchEvent` | seal issue `inspect.branch_unsupported`; no linearisation | — | none (disclosed gap) | in-file branches wait for `aer/0.2` |
| 17 | `sample_limit` | scope `status` `limit`; issue `inspect.sample_limit` | O (source) | `aprov.n_scope@1` | — |
| 18 | reasoning content | `reasoning` parts | O (source) | `aprov.n_part@1` | — |
| 19 | event order | `after` edges with `time` and `proto` (span nesting), never event-list position | D | `aprov.after@1` | C.8.6 |

### F.2.6 Generic kinds and extension constructs (the D.12 future-framework fixture)

Addendum B (AD-15) requires the D.12 / Q.3 future-framework test to produce named PROV statements for the planner
step, memory write and read, screenshot, hand-off and human approval. This table fixes those statements; K owns the
test, D owns the fixture. `<ns>` is the fixture's namespace.

| Construct | AER (C.3) | Named PROV statements | Rules |
|---|---|---|---|
| Planner step (code router) | `activity{type: "<ns>:plan", actor, scope, inputs: [m_k, …]}`; its output `artefact{type: "<ns>:plan", generated_by: <activity>}` | `activity(x:L(ac), [prov:type apv:GenericActivity, apv:activityType "<ns>:plan"])`; `used(x:L(ac), x:L(m_k))`; `wasGeneratedBy(x:L(af), x:L(ac))`; `wasAssociatedWith(x:L(ac), x:L(actor))`; `wasInformedBy(x:L(ac), x:L(mc))` for the model call that generated `m_k` | G-ACT, G-USE, G-GEN, G-ASSOC, `aprov.comm@1` |
| Memory write | `activity{type: "<ns>:memory_write", inputs: [m_k]}` and `artefact{type: "<ns>:memory_entry", generated_by: <write>}`; or `state_change{target: agent_store, patch, cause}` | `used(write, m_k)`; `wasGeneratedBy(entry, write)`; or the patch chain `wasGeneratedBy(x:L(sc).after, cause)` and `wasDerivedFrom(…, prev, [prov:type prov:Revision])` | G-ACT, G-USE, G-GEN; `aprov.state_patch@1` |
| Memory read | `activity{type: "<ns>:memory_read", inputs: [<entry>]}` | `used(read, entry)`; `wasInformedBy(read, write)` via the entry | G-USE, `aprov.comm@1` |
| Screenshot | returned to the model as a tool result: a `blob` part of the tool message (specialised kinds first); saved outside the conversation: `artefact{type: "<ns>:screenshot", content_ref: {"$blob": …}, media: "image/png", generated_by: <te>}` | `wasGeneratedBy(part, te)` (`aprov.gen_result@1`); or `wasGeneratedBy(x:L(af), x:L(te))` | `aprov.gen_result@1` or G-GEN |
| Hand-off to a sub-agent | `scope{kind: subagent, actor, spawned_by: <te_handoff>}`; a second-file sub-agent is a separate execution linked by `related` | `wasStartedBy(x:L(sub), -, x:L(te_handoff))`; `wasAssociatedWith(x:L(sub), x:L(actor))` | `aprov.spawn@1`, `aprov.assoc_scope@1` |
| Human approval (allow) | `decision{actor: user, subject: p, verdict: allow}`; `tool_execution{authorised_by: dc}` | `wasAssociatedWith(x:L(dc), x:L(user), [prov:role apv:DeciderRole])`; `used(x:L(dc), x:L(p))`; `wasStartedBy(x:L(te), -, x:L(dc))`; `wasInformedBy(x:L(dc), x:L(mc))` via `p` | `aprov.decision@1`, `aprov.authorise@1`, `aprov.comm@1` |
| Human approval with edit (`modify`) | `decision{verdict: modify}` | as above, without `used(te, p)` (NE-18); `apv:Gap` on `/call` | named, disclosed gap until `aer/0.2` |
| Text-parsed action | `tool_execution{requested_by: <actor>}` with no request part | `wasAssociatedWith(te, runtime)`; `actedOnBehalfOf(runtime, requester, te)` | `aprov.n_tool_execution@1`, `aprov.assoc_tool@1` |
| Restore or branch | in-file branch: seal issue; replay across artefacts: separate executions with `related: replays` | none in PROV (disclosed gap) | — |
| Unknown event | `ext` only | none; counted as a disclosed gap in the derivation report | — |

---

## F.3 What is not knowable from each source class

A statement absent for one of the reasons below MUST NOT be approximated in the core. Where a method can
*estimate* it, the estimate goes to an inference bundle. The capture profile records each item as `notProvided`
or `notObservable`.

| Source class | Not knowable | Why | Consequence |
|---|---|---|---|
| Aggregate results (paper tables, README success rates; MiDojo summaries truncated to 200 characters) | any per-execution activity; the causal chain from steps to outcome; which step achieved a goal | no execution evidence is released [landscape/trace_formats.md §3.10; I.1.1] | no AER, so no PROV. Aggregates may appear only as entities attributed to their authors, never as primary sources [landscape/prov_semantics.md §10.2 item 1]. MiDojo and ADI are "not possible" |
| Native message-list logs (the AgentDojo family) | per-call times; request payloads, parameters and tool definitions; the served model; earlier passes (undetectable in old logs); environment state; original output under the PI detector; the arguments the model emitted (mutated in place); the exact producing code version (a range at best); reasoning | not logged [sources/agentdojo.md §7.2] | statuses; context membership INFERRED unless verified (F.1.8); no state entities; no state usage by the checker |
| transcript/v1 (released) | request payloads and tool schemas; environment state; earlier passes in 153 traces; DeepSeek completeness; the producing framework commit; passed-back reasoning | the capture of that era did not record them [docs/capture_spec.md §4.2–§4.3; audit/corpus.md §3.3 R6; §13 G2] | statuses; context membership and transforms INFERRED (F.2.2 rows 6–7) |
| Inspect `.eval` (survey AgentHarm) | the as-sent request where `ModelEvent.call` is absent; in-file branch structure; provider-side hidden prompts, routing and truncation | not recorded, or not representable in `aer/0.1` (F.2.5 rows 5, 16) | D context membership under the D.9 rule; seal issue for branches; statuses |
| Live black-box capture | the model's internal use of context (which items causally determined a token or argument); provider-side hidden prompts, routing and truncation; withheld reasoning; environment detail beyond digests and truncated diffs (400 characters and 200 entries per diff) | in principle unobservable, or withheld [landscape/prov_semantics.md §9.2; docs/capture_spec.md §4.3] | `apv:NotObservable`; `apv:Withheld`; only method-qualified estimates |
| Scenario or benchmark-input files (STAC) | target-agent behaviour and outcomes; agent identity; times; system and defence prompts; the agent side of planner turns 2–3 (61 records show those executions took place); the ASB initial state for 89 of 93 cases | not released [sources/multiturn-agent-attack.md §0, §6.2] | a scenario record (`unit` = `scenario`), not an execution of the target agent; import `planned` (A6) |
| Every source | negative facts (did *not* use, did *not* happen) unless positively recorded; concurrency; intent; argument-level causality | PROV has no closed world; order ≠ causation [landscape/prov_semantics.md §3.18, §3.19] | never asserted (NE-1, NE-9) |

---

## Appendix A. Traceability to the review items (SEM-*) and requirements (AR-*)

| Item [manuscript/review_feedback.md] | Where this section addresses it |
|---|---|
| SEM-1: `wasInformedBy` encoded execution order | NE-1, NE-7; E.1.6 (communications exist only through witnessed entities); order only as `apv:after*` |
| SEM-2: the exchanged entity and the evidential status of `used` | E.1.4 `aprov.use_context@1` on the invocation, with class and assumption; `apv:viaEntity` and `apv:premise` on every communication |
| SEM-3: validation claims stronger than the checks | E.5.5 (typed, bidirectional completeness; round trip with the unqualified layer removed; structural checks); constraints per bundle; time checks are MAY-flags only; skipped counts as failure |
| SEM-4: over-approximate sink taint | E.7: taint is an INFERRED assessment with its policy id; exposure is separate and carries the class of context membership; argument-level evidence in an opt-in inference bundle (E.1.7, deferred) |
| SEM-5: no span-level view | `aprov.n_part@1` (part entities); `apv:spanStart` and `apv:spanEnd` on assessments (E.7.3) |
| SEM-6: mislabelled trusted outputs | labels are INFERRED and versioned (F.1.2, F.1.8); census is a SEM-validator duty (E.7.3 item 3) |
| SEM-7: the sink taxonomy misses reply and egress goals | assistant messages and reply parts are entities (`aprov.n_message@1`, `aprov.n_part@1`); multi-class `apv:securityRole` includes `apv:ResponseSink` and `apv:EgressRead` (E.4.5) |
| SEM-8: machine-readable mapping | the rule catalogue `catalogue/agentprov-prov-0.1.toml` is the plan; every statement cites `apv:rule`; the semantic diff is `compat/semdiff-map.toml` |
| SEM-9: placeholder and ambiguous times | NE-6; E.5.3 item 7; statuses `apv:Ambiguous` and `apv:NotRecorded` |
| SEM-10: colliding tool-call ids | positional local names (E.1.2); provider ids are attributes (`apv:providerCallId`) |
| SEM-11: gated enrichments | R7 and R8 dropped (E.8.4) |
| AR-1 (evidence on every assertion), AR-5 (outcomes as provenance-bearing claims), AR-7 (assistant turns as entities) | E.1.5 item 6; `aprov.outcome@1` with the origin map, judge provenance and checker inputs; `aprov.n_message@1` |

## Appendix B. Challenges raised by this section, and their dispositions

| # | Against | Summary | Disposition (Addendum B; RESOLUTIONS §1.3) |
|---|---|---|---|
| 1 | D7 (adoption of prov_semantics §8 as written) | Six catalogue adjustments: (a) no request→message quotation, `apv:partOf` instead; (b) usage of the recorded message plus `apv:sentTransform`, instead of as-sent entities; (c) DERIVED context membership without a completeness condition; (d) `wasInformedBy` is the full Inference 6 closure; (e) no relation times; (f) payload containment and authorship as assessments | (a) rejected: `hadMember` with a `prov:Collection` message (A5, AD-19(a)); (b) accepted (R-06); (c)–(f) accepted (AD-19(c)(d)); derived-semantic bundle deferred to v0.2 |
| 2 | D2 (AER schema) | Interface needs: (a) per-input sent-transform declarations; (b) a `tools` reference on `model_call`; (c) a primary/secondary artefact flag; (d) longest-prefix `evf` semantics; (e) a local-id character set without `_`; (f) a named `execution.instrumentation` field | AD-03: (a) accepted; (b) already in C (fixture kind `tool_definitions`); (c) accepted as `prov_primary`; (d) accepted, normative in C.6.3; (e) rejected, C's grammar with `#`→`-` (AD-04); (f) already in C (R-2 shape) |
| 3 | D7 and D2 (the compat gate on an AER-regenerated view) | JCS loses member order (8,017 of 17,664 released graphs affected) and numeric form (270 graphs); the first draft proposed reading compat values from raw through `src` locators | rejected (AD-02): C's `ext.lex {ord, flt}`; the view reads nothing from raw |
| 3a | D7 and D9 (revisions at the top level) | Revision, alternate and validation links break the purity of `derive`; move them to a lineage document produced at packaging time | accepted; lineage documents deferred (AD-10); compat marking in manifest and index (R-55) |

Other dispositions of this section's open questions (RESOLUTIONS §1.3): w3id registration is user decision U-02;
`apv:FullContextResend` at every commit and the producing commit of the v1 release follow AD-05 (INFERRED unless U-01
supplies a pinned harness); the PROV-Dictionary round trip is moot while collection mode is deferred; the SEM field
names are closed by R-18; exposure only for security-relevant pairs is accepted as specified; the G3 release gate
follows AD-07; the per-call served model uses `model_call.served_model` when present and `apv:SingleModelPerActor`
only when absent; the derived-semantic bundle is deferred to v0.2.

## Appendix C. Reproduction of the measurements cited

All scripts are stdlib-only, read the baseline corpora at `579a908` read-only, and print no corpus content.

```bash
EV=~/Desktop/PhD/Labs/AgentPROV/investigation/spec/EF_evidence
C=~/Desktop/PhD/Labs/AgentDojo-PROV-framework/corpus
python3 $EV/ctx_volume.py $C/corpus-prov                     # -> released.json  (E.6.1, E.8.4)
python3 $EV/ctx_volume.py $C/corpus-og-agentdojo-runs-prov   # -> converted.json
python3 $EV/args_key_order.py $C/corpus-prov                 # -> args_key_order_corpus-prov.json (E.8.2)
python3 $EV/args_number_form.py $C/corpus-prov               # -> args_number_form_corpus-prov.json (E.8.2)
```

| Output | Released | Converted |
|---|---|---|
| Invocations (assistant turns) | 64,897 | 73,551 |
| Context usages under the prefix rule | 437,732 | 511,794 |
| `tool → llm` witnesses | 176,449 | 189,729 |
| `llm → llm` witnesses | 131,489 | 161,398 |
| Requests (`tool_calls` entries) | 64,829 | 68,773 |
| Activities with unsorted `args` keys | 12,676 (8,017 graphs) | 12,862 (8,173 graphs) |
| Activities with integral-float `args` | 313 (270 graphs) | 1,681 (1,288 graphs) |
| Traces with more than one pass in the transcript | 0 | 0 |

The 26,645 / 23,449 pair (E.1.6, E.8.4) is not reproduced by these scripts. Its two readings are identical by
construction: the 26,645 / 23,449 R6 taint-only `used` edges each entail, via Inference 6, exactly one
`wasInformedBy` the builder never asserts (entailed 99,278 / 91,661 minus asserted 72,633 / 68,212). The counts come
from [audit/provenance_evidence/evidence_stats.json] (`sink_taint_only_used_edges`) and
[landscape/prov_semantics_evidence/inference6_scan.json] (`entailed_wib_inference6`, `asserted_wib`,
`entailed_not_asserted`).

Observation on untrusted content: no text addressed to an AI agent was read. The scripts counted structure only,
and the reports cited were treated as data.
