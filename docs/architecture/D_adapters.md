Revision: 2026-10-07 r2 — review resolutions and Addendum B applied.

# D. Adapter model (readers/dialects, mappers, source profiles, registry, live backends)

AgentPROV v0.1 architecture and implementation specification, section D.
Date: 2026-10-07. Status: normative for v0.1. It must be read with `investigation/DECISIONS.md` (binding; precedence
Addendum B > Addendum A > D0–D12) and with `spec/review/RESOLUTIONS.md`, whose §3 canonical naming table is mandatory
here except where Addendum B deviates from it (AD-08 nuance, AD-10 `stats`/`render`, AD-15 generic kinds, AD-16
interpreter floor). This section implements D4 and D5 as amended. The first revision raised four **Challenge** boxes;
all four have been ruled, and each is now a short **Resolved** note that cites the ruling (AD-nn / R-nn).

---

## D.0 Conventions, scope and dependencies

**Keywords.** MUST, MUST NOT, SHOULD, SHOULD NOT and MAY are used as in BCP 14 (RFC 2119/8174).

**Citations.** Investigation reports are cited as `[sources/rope.md §3.4]`, `[verify/rope.md §4]`,
`[audit/capture.md §9.2]`, `[landscape/trace_formats.md §6.3]`. Baseline code is cited as
`agentdojo_prov/observer.py:172-231` (AgentDojo-PROV-framework @ `579a908354b93361efe0905ffb7623256aa96a06`).
AgentDojo package code is cited as `agentdojo==0.1.35 task_suite/task_suite.py:383-394`. These lines were read in
the installed 0.1.35 wheel on 2026-10-07 and match the audits' references. Upstream code read for this revision
(AgentDojo `agent_pipeline/basic_elements.py`; inspect_ai `core/_tool_call.py` at `5d97e38`) was read in the upstream
clones, which now live outside the session working tree in the sibling directory `AgentPROV-upstream/` (U-08);
citations are by repository and commit, so the move changes no citation.

**What this section owns** (RESOLUTIONS §0, precedence item 3: D owns `adapters` and the backend code).
- The adapter concepts and their Python interfaces.
- The error model and the "seal with issues, never discard" rule.
- The registry semantics and the `agentprov info` rendering rules (the status *values* are owned by I.1.1).
- The source-profile and rule-catalogue file formats, and the authoritative rule-name index (§D.5.4).
- The dialect-to-AER mappings for the v0.1 dialects.
- The live harness code (`agentprov_backend`), the backend worker protocol `agentprov-backend/0.1`, and the
  AgentDojo and AutoDojo backends.
- Adapter isolation rules.

**What this section depends on (normative elsewhere).**
- AER `aer/0.1` record kinds, fields, ids and serialisation: C.3 plus `schemas/aer-0.1.schema.json` is the **only**
  AER contract (R-02). This section cites it and does not restate it. aer/0.1 has 13 kinds (Addendum B-1):
  `execution`, `actor`, `scope`, `message`, `model_call`, `tool_execution`, `decision`, `state_change`, `fixture`,
  `judgement`, `activity`, `artefact`, `seal`.
- The raw evidence store, the `expand` stage for archive members (AD-12) and the corpus layout (HL; RESOLUTIONS
  §3.6).
- The `capture/0.1` envelope, event vocabulary and hash chain (C.13; the writer is `agentprov_capture`).
- SEM semantics profiles (C.14).
- The provenance engine and the `apv:` vocabulary (EF).
- Ingestion limits, worker isolation and live-tier controls (G).
- Paths and the CLI (MN; RESOLUTIONS §3.2 and §3.7).

Adapters MUST NOT invent core fields. Fields that this section asked for in the first revision were ruled in AD-03;
the rulings are recorded in §D.14.1.

**Package root and interpreters** (A1, AD-01, AD-16).
- Core: distribution and import package `agentprov` (src layout, uv), `requires-python = ">=3.14"`,
  `.python-version` `3.14`. Archive and compressed-stream ingestion **refuses** to run below 3.14.8 in release mode
  (`--release`, the deposit builder behind `package --deposit`; exit 3; `package` in seal mode opens no archive, D-62)
  and, in dev mode, warns and records `python_version` and
  `interpreter_advisory` (AD-16; §D.13.1). Core never imports `agentdojo`, `inspect_ai`, `openai` or `httpx`.
- Shared capture package: `capture/` → distribution `agentprov-capture`, import `agentprov_capture`, Python ≥ 3.12,
  stdlib + `rfc8785` only.
- Shared live harness: `backends/shared/` → distribution `agentprov-backend`, import `agentprov_backend`. It holds
  the AgentDojo-family live harness, the worker entry and `ScriptedTransport` (§D.10).
- Backend projects: `backends/agentdojo/` and `backends/autodojo/`, each a separate uv project with its own
  `pyproject.toml`, `uv.lock` and `.python-version` `3.12`. They depend on `agentprov-capture` and
  `agentprov-backend` by path and **never on `agentprov`**.

All core module paths below are relative to `src/`.

**Terms.**

| Term | Meaning |
|---|---|
| raw artefact | One immutable byte string in the raw store, addressed by sha256. Examples: a run JSON file, an `.eval` zip, one member object expanded from it (AD-12), the STAC array, a `capture/0.1` log. An AER header lists the raw artefacts it cites in `artifacts[]` (ids `a<n>`). |
| `artefact` record | The aer/0.1 generic record kind for a typed product of an activity (AD-15; §D.12). It is unrelated to a raw artefact except that its `content_ref` may be a blob. |
| located item | One execution-bearing unit inside a raw artefact, addressed by `(sha256, locator)`. Examples: a whole TraceLogger file (locator `{"p":""}`), the STAC element `{"p":"/223"}`, an Inspect sample member object (`a` names the member object; locator `{"p":""}`). |
| execution unit | The located item that becomes one AER file, plus any auxiliary raw artefacts the mapper may read (blobs, native logs, context files, a sub-agent's second file). |
| source | A released corpus or live framework with its own provenance, e.g. `agentdojo`, `rope`, `stac`. A source has one or more parts and one or more profiles (`source_id` = registry id; `profile.id`; `corpus_id`: R-11). |
| family | A set of sources that share dialects and mappers. v0.1 families: `agentdojo` (TraceLogger, `capture/0.1` mapping), `adprov` (`transcript/v1`) and `inspect` (`.eval`, normative, AD-06). `stac` is a planned design note (§D.8). |

---

## D.1 Concepts and responsibilities

### D.1.1 Components

| Component | Responsibility | Input → output | May import | Versioned as |
|---|---|---|---|---|
| **Dialect** | A named physical format with enumerated **variants**, e.g. `agentdojo.tracelogger` with variants `v0.k11`, `v1.k14`, `drift.k18.*` (§D.6.2). A dialect is a specification. Its implementation is a Reader. | — | — | dialect id (stable string); variants are a closed list per reader version |
| **Reader** | Safe parser for one dialect. It **discovers** candidate artefacts in a source tree, **sniffs** whether bytes belong to the dialect and which variant, and **parses** them into located items. A Reader never interprets semantics. | bytes → `LocatedItem`s (strict JSON values that keep source member order and int/float typing, plus locators) | Python stdlib and `agentprov.ingest` only (§D.13) | reader SemVer |
| **Mapper** | Deterministic function from an execution unit, a source profile and a rule catalogue to AER records. It emits a versioned rule reference for every D/I assertion, declares unknowns in `unk`, writes lexical hints through `aer.canon.lex_hints()`, and reports issues. It never writes the `seal`; the core AER writer does. | `ExecutionUnit` + profile + rules → AER records of the 12 non-seal kinds (`execution` … `artefact`) | stdlib and `agentprov.aer` (`types`, `ids`, `canon`, `evidence`) only | **adapter SemVer**, dotted id (e.g. `agentdojo.tracelogger` `0.1.0`). The mapping id `"<adapter id>/<profile id>"` enters the import execution id (AD-04). |
| **Source profile** | Data, not code: the facts about one source part that a mapper needs. Generic tables `[profile] [source] [licence] [lineage] [import]`; family facts (identity, benchmark, harness, outcomes, quirks, live pins) in `[family.<ns>]`, validated by the family's schema. **No status**: the registry is the only status store (R-38, R-45). TOML shipped in the package (§D.4). | — | — | integer `version`, monotonic, bumped on any byte change (AD-18), plus the sha256 of the TOML bytes |
| **Rule catalogue** | The versioned list of rules that mappers (and semantics profiles) cite. Each rule has an id, version, class D/I (its **effective** class, resolved at map time; AD-05), statement, assumptions with verification, code citation and test reference (§D.5). The catalogue is the `prov:Plan` of the conversion (EF). | — | — | file `<ns>.rules.toml`, `[catalogue] id = "<ns>"`, integer `version`; each rule `<ns>.<rule>@<n>` |
| **Semantics profile** | Data plus small pure functions used by SEM (C.14): tool tables, integrity, roles, injection-marker normaliser, outcome polarity. It is **supplied by the adapter family** and referenced from the source profile. Its content is specified in C.14 and EF, not here. | AER → SEM | stdlib, `agentprov.sem` | id `<ns>.<name>` + integer version, e.g. `agentdojo.suites` `1` (directory `agentdojo.suites-1`) |
| **Backend** (live) | A separate uv project under `backends/<b>/` (Python 3.12) that runs the `agentprov_backend` harness in the live tier T2. It drives a benchmark and writes **raw capture artefacts** only: a `capture/0.1` log, blobs and native logs. It never writes AER, never imports `agentprov` and is never imported by it. Core talks to it only through `agentprov-backend/0.1` and then ingests its staging output like any import (D0, A1). | run plan → sealed raw evidence in staging | the benchmark package, `agentprov_capture`, `agentprov_backend` (§D.10, §D.11) | backend project lock + `agentprov-backend` SemVer |
| **Registry** | An explicit, in-repo enumeration of sources, their parts and capabilities, binding parts to readers, mappers, profiles and backends (§D.3). Package `agentprov.adapters.registry`. | — | no adapter or benchmark imports at module import time | registry date and contents digest |

An **adapter** is the package `agentprov.adapters.<family>`. It contains reader(s), mapper(s), profiles, rule
catalogue(s), the namespace `ext` schema, semantics profile(s) and tests. Live harness code is **not** part of an
adapter: it lives in `agentprov_backend` (AD-01). The capture reader and capture mapper stay in the core adapter
(`adapters/agentdojo/capture_reader.py`, `capture_mapper.py`).

### D.1.2 Pipeline (restating D0 at adapter granularity)

```
            ┌──────────── import (T0 → T1) ────────────┐   ┌──────────── live (T0 → T2 → T0) ─────────────┐
source tree │ fetch / --input → raw store (T0)         │   │ agentprov run <b> (T0): identity digests,    │
            │ expand containers → member objects (T1)  │   │ spawn <env>/bin/python -I -B -m              │
            │ Reader.sniff → Reader.parse (T1)         │   │   agentprov_backend.worker (T2) →            │
            │                                          │   │   capture/0.1 + blobs + native JSON in       │
            │                                          │   │   $AGENTPROV_HOME/staging/<session>/         │
            │                                          │   │ staging ingested like --input → raw store    │
            └────────────────────┬─────────────────────┘   └──────────────────────┬───────────────────────┘
                                 ▼                                                ▼
                    ExecutionUnit(primary LocatedItem, auxiliary artefacts) ── same path from here
                                 ▼
            Mapper.map(unit, ctx[profile v, catalogues v]) (T1) → AER records → AerWriter (+seal, accounting)
                                 ▼
            validate (tier 2) and write gate (T0) → SEM → PROV → package
```

### D.1.3 Adapter invariants (normative)

- **A-1 Parse, don't interpret.** Readers produce values and locators only. Every semantic reading belongs to a
  mapper rule (AER) or a semantics profile (SEM).
- **A-2 Purity.** `Mapper.map` is a pure function of (unit bytes, adapter code, profile bytes, catalogue bytes).
  It MUST NOT read the clock, environment variables, the network, random state, the locale, or any file other than
  the unit's declared artefacts. Re-running it MUST give byte-identical AER (D9 recompute).
- **A-3 Rule citation.** Every D or I assertion, whether record-level `ev` or a per-field `evf` entry, cites at least
  one rule declared in a catalogue that the AER header lists (C.6.4; tier 2). A record's `ev` is its **existence**
  class and the default for its fields; a mapper MUST NOT lower `ev` because one field is weaker, and tags that field
  through `evf` instead (AD-03, R-22).
- **A-4 No benchmark code in core.** Readers and mappers MUST NOT import `agentdojo`, `inspect_ai` or any other
  benchmark or framework package, and MUST NOT execute upstream code. No core module imports a benchmark at all;
  benchmark imports exist only under `backends/` (A1; §D.13).
- **A-5 No sentinels.** Unknown values go to `unk` with a reason from the closed list of C.7.1 (`not_recorded`,
  `lost`, `overwritten`, `withheld`, `ambiguous`, `not_captured`, `not_applicable`), never `"0"` or `""` stand-ins in
  typed fields. The baseline `"0"` timing stub is the counter-example [audit/legacy_replay.md §4]; its verbatim
  source strings are kept only in `t.raw` (C.7.3).
- **A-6 Seal with issues, never discard** (§D.2.8).
- **A-7 Identity by declared rule.** Model, defence and harness identity are resolved by the profile's identity
  rules, never by trusting one self-reported field the profile marks unreliable. Examples: `pipeline_name` at
  [sources/rope.md §4.3, verify/rope.md §5] and [sources/agentdyn.md §3.6], and `agentdojo_package_version` at
  [verify/rope.md §3].
- **A-8 One machinery.** Live capture output is mapped by the same reader, mapper and validator path as an import
  (D0). A live execution's AER differs from an imported one only in which evidence exists, never in how it is
  interpreted.
- **A-9 Specialised kinds first** (AD-15). A mapper uses the generic kinds `activity` and `artefact` only for an
  activity or product that no specialised kind represents (for example a harness-side memory read, retrieval, code
  execution outside a tool call, a screenshot taken by the environment). It MUST NOT use `activity` for a model call,
  tool execution, decision or state change, and MUST NOT use `artefact` for a message, fixture or judgement. Every
  `activity.type` and `artefact.type` is a namespaced `<ns>:<name>` declared in the family catalogue (§D.5.2), with
  `<ns>` declared in `execution.ns` and never a reserved prefix (C.3.13, C.10). An activity's outputs are `artefact`
  records; an activity never generates a message in aer/0.1 (C.3.4).
- **A-10 Static evidence classes** (AD-05). The class a mapper writes is the effective class of the cited rule,
  resolved at map time and covered by the execution digest. A change of a rule's verification status is a new rule id
  or catalogue version, never a derive-time reinterpretation.

---

## D.2 Python interfaces

### D.2.1 Module layout

The layout follows RESOLUTIONS §3.2 (MN M.1.2 is the path authority). [R-17, R-01, R-07]

```
src/agentprov/
  errors.py                # AdapterError hierarchy, IngestError (+ IngestSafetyError) (§D.2.7)
  ingest/                  # limits.py (IngestLimits), loaders.py (strict_json_loads, iter_jsonl), archives.py,
                           # streams.py, names.py, paths.py, quote.py, yamlsafe.py  (owner G; used by readers)
  aer/                     # types, canon (lex_hints), ids (import_execution_id), evidence, rules (RuleCatalogue,
                           # load_catalogue), writer (AerWriter), reader, locators, accounting, validate
                           # catalogue: aer/rules/aer.rules.toml
  testing/                 # agentprov.testing: golden-AER helpers, Hypothesis strategies for readers (core only)
  adapters/
    __init__.py            # re-exports the protocols; imports NO adapter family
    registry/              # __init__.py (REGISTRY data, factories, EXTERNAL_OWNERS), claims.py, render.py (§D.3)
    protocols.py           # Reader, Mapper, SourceTree, MappingContext (typing.Protocol)
    types.py               # frozen dataclasses: ArtefactRef, Origin, Locator, LocatedItem, ExecutionUnit,
                           # SniffResult, ReaderResult, Issue, ...
    profiles.py            # SourceProfile model + load_profile() (tomllib), closed generic schema
    runner/                # map_unit, job_map; importer.py: import_source() (§D.2.9); provjob.py: the T1 job prov
    agentdojo/             # family: TraceLogger dialect and the capture/0.1 mapping (no live code)
      dialect.py           # TraceLoggerReader
      mapper.py            # TraceLoggerMapper            (adapter id "agentdojo.tracelogger")
      capture_reader.py    # CaptureLogReader             (dialect {id: "agentprov.capture", variant: "0.1"})
      capture_mapper.py    # AgentDojoCaptureMapper       (adapter id "agentdojo.capture")
      identity.py          # identity resolution driven by profile tables (pure)
      ext.schema.json      # closed JSON Schema of ext.agentdojo (and ext.rope/agentdyn/drift/mandate/survey)
      family.schema.json   # closed schema of [family.agentdojo] in profiles (§D.4.2)
      profiles/*.profile.toml   # agentdojo-upstream, agentdojo-live, rope, autodojo-via-rope, autodojo-live,
                                # agentdyn, drift, mandate-agentdojo-eval, survey-runs
      tables/*.toml        # identity tables (e.g. AgentDyn 76 pipeline directories)
      rules/{agentdojo,rope,agentdyn,drift,mandate,survey,autodojo}.rules.toml
      semantics/           # semantics profile agentdojo.suites (owned here, specified in C.14 and EF)
    adprov/                # transcript/v1 importer (§D.7)
      dialect.py  mapper.py  profiles/adprov-v1.profile.toml  rules/adprov.rules.toml
    inspect/               # Inspect .eval importer, full reader (§D.9; normative in v0.1, AD-06)
      dialect.py  mapper.py  ext.schema.json  family.schema.json
      profiles/survey-agentharm.profile.toml  rules/inspect.rules.toml
    stac/                  # design note only; planned (§D.8)

capture/                   # distribution agentprov-capture, import agentprov_capture (>=3.12; stdlib + rfc8785)
  agentprov_capture/       # event model, log writer (CaptureLog), hash-chain verifier, redact (+ redact_allowlist.toml),
                           # envstate digests, rules/cap.rules.toml
backends/
  shared/                  # distribution agentprov-backend, import agentprov_backend (§D.10)
    agentprov_backend/     # gateway, pass_recorder, executor_mirror, runtime, transport (recording httpx), runner,
                           # attacks, worker, testing (ScriptedTransport); deps httpx, openai; imports agentdojo
                           # from the backend project
  agentdojo/               # backend project: pyproject.toml, uv.lock, .python-version 3.12; agentdojo==0.1.35; tests/
  autodojo/                # backend project: the fork pinned at aa458794b7eb7f082e94daeac4c0f55bfc0c90cc; tests/
```

Moves relative to the first revision: `adapters/safety.py` → `ingest/`; `adapters/rules.py` → `aer/rules.py`;
`adapters/errors.py` → `agentprov/errors.py`; `adapters/testing.py` → `agentprov.testing`; the live harness
(`adapters/agentdojo/live/`) and the worker entry → `agentprov_backend`; the core capture writer, gateway and
transports → `agentprov_capture` and `agentprov_backend`; `capture/testing.py` (`ScriptedTransport`) →
`agentprov_backend.testing`; the AutoDojo environment definition (`adapters/autodojo/env/`) → `backends/autodojo/`.
`adapters/inspect/` is a full reader and mapper, not "sniff only" (AD-06).

The import-boundary test (`tests/boundary/test_import_boundary.py`, K) MUST check the following.
- No module under `src/agentprov/` imports `agentdojo`, `inspect_ai`, `openai`, `httpx` or `agentprov_backend`.
- `agentprov.adapters.*.dialect`, `*.mapper`, `*.capture_reader` and `*.capture_mapper` import only the stdlib,
  `agentprov.{ingest,aer,adapters}` and, for the capture reader, the `agentprov_capture` verifier.
- `yaml` is imported only by `agentprov/ingest/yamlsafe.py` (AD-17).
- `agentprov_capture` imports only the stdlib and `rfc8785`.
- `agentprov.adapters.registry` imports nothing from the adapter families. Factories are lazy strings (§D.3.1).
- No backend project depends on `agentprov` (checked on `backends/*/uv.lock`).

### D.2.2 Core data types (`agentprov.adapters.types`)

These types mirror C's contract (C.3.12, C.9). Where they differ in spelling from C, C prevails. [R-03, R-08, R-22,
R-04, R-17]

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Mapping, Sequence

Json = None | bool | int | float | str | list["Json"] | dict[str, "Json"]
EvidenceClass = Literal["O", "D", "I"]
UnkReason = Literal["not_recorded", "lost", "overwritten", "withheld", "ambiguous",
                    "not_captured", "not_applicable"]                       # C.7.1, closed (7 values)

@dataclass(frozen=True, slots=True)
class Origin:
    """Where the raw bytes came from (C.3.12). Exactly one origin per artefact; further locations (mirrors)
    are rows of raw/origins.jsonl, never a second origin (AD-03 R-4)."""
    kind: Literal["git", "hf", "zenodo", "url", "corpus", "capture", "member", "local"]  # local: dev only
    repo: str | None = None          # git/hf, e.g. "https://github.com/ethz-spylab/agentdojo"
    commit: str | None = None        # full 40-hex SHA for git
    path: str | None = None          # POSIX path inside the repo or corpus, verbatim (a label, never opened)
    blob_sha1: str | None = None     # git blob id when kind == "git"
    introduced_in_commit: str | None = None  # git attribute: first commit holding this blob (upper bound on run time)
    doi: str | None = None           # zenodo
    file: str | None = None          # zenodo file name
    revision: str | None = None      # hf revision
    url: str | None = None
    retrieved: str | None = None     # RFC 3339 date of retrieval (url)
    session: str | None = None       # capture session (UUIDv7) when kind == "capture"
    container: str | None = None     # member: "sha256:<hex>" of the container object (AD-12)
    label: str | None = None         # member: NFC member label (never a path component)
    method: int | None = None        # member: zip method (0, 8, 93)
    crc32: int | None = None         # member: declared CRC-32
    size: int | None = None          # member: declared uncompressed size

@dataclass(frozen=True, slots=True)
class ArtefactRef:
    """One entry of the AER header's artifacts[] (C.3.12 Artefact)."""
    id: str                          # "a<n>"
    sha256: str                      # lower-case hex of the raw bytes
    bytes: int
    media: str                       # "application/json", "application/zip", "application/x-ndjson", ...
    origin: Origin
    role: Literal["primary", "capture_log", "native_log", "supporting"] = "primary"
    prov_primary: Literal["native", "byte_derived", "secondary", "unknown"] = "unknown"   # R-22; fail closed

@dataclass(frozen=True, slots=True)
class Locator:
    """C's locator (C.9.1). The canonical key form used in the import execution id is computed only by
    agentprov.aer.ids (RESOLUTIONS §3.4); adapters never build it themselves."""
    a: str | None = None             # artefact id (a member object under AD-12)
    p: str | None = None             # RFC 6901 JSON Pointer ("" = JSON root)
    line: int | None = None          # 0-based line for JSONL
    bytes: tuple[int, int] | None = None   # [start, end_exclusive); never in the key when p or line is present
    o: str | None = None             # pointer into the artefact's origin record
    blob: str | None = None          # "sha256:<hex>" of a blob

@dataclass(frozen=True, slots=True)
class SniffResult:
    match: bool
    dialect: str | None = None       # e.g. "agentdojo.tracelogger"
    variant: str | None = None       # e.g. "v1.k14"
    flags: frozenset[str] = frozenset()   # e.g. {"missing:utility", "msgs_key:conversations"}
    reasons: tuple[str, ...] = ()    # machine codes explaining the decision (logged in the import report)

@dataclass(frozen=True, slots=True)
class CandidateArtefact:
    label: str                       # NFC logical name relative to the source root (G.3.6); never a path to open
    size: int
    origin: Origin

@dataclass(frozen=True, slots=True)
class LocatedItem:
    artefact: ArtefactRef
    locator: Locator                 # canonical forms only: {"p": ""}, {"p": "/<i>"}, {"line": n}, {} (§3.4)
    dialect: str
    variant: str
    flags: frozenset[str]
    value: Json                      # from agentprov.ingest.loaders.strict_json_loads; untrusted data. Python
                                     # dicts keep source member order and floats stay floats, which is what
                                     # aer.canon.lex_hints() needs (AD-02)
    reader_issues: tuple["Issue", ...] = ()

@dataclass(frozen=True, slots=True)
class ExecutionUnit:
    primary: LocatedItem
    auxiliary: Mapping[str, ArtefactRef] = field(default_factory=dict)  # role label -> artefact (digest-checked)
    mode: Literal["import", "live"] = "import"
    ex: str | None = None            # live: "ex_" + UUIDv7 from the capture log; import: computed by
                                     # agentprov.aer.ids.import_execution_id (AD-04)
```

`LexemeIndex` and the reader rule R-LEX of the first revision are deleted (AD-02). Source lexical form (member order
of source objects; integral floats) is carried in AER only as the sparse `ext.lex {ord, flt}` hints of C.11.4, written
by the one helper `agentprov.aer.canon.lex_hints()`. The hints cover every object and number a mapper copies from a
source, including typed fields (`t.dur_s`, `params.*`, `usage.*`). They are **mandatory** for adapters that declare a
byte-exact view (`adprov.transcript_v1`; `agentdojo.tracelogger` while `render_converted` is a gate) and optional
otherwise. The baseline graphs depend on both facts: non-lexicographic argument key orders in 12,676 (released) and
12,862 (converted) argument objects, and integral floats [spec/B_audit_evidence/README.txt, `args_order.py`].

`CellSpec`, `BenchmarkIdentity`, `AgentConfig` (with `llm_element`), `RunPlan` and `CellResult` are not core types.
They are `agentprov_backend` internals (§D.10.1).

### D.2.3 Reader protocol (`agentprov.adapters.protocols`)

```python
from typing import Iterator, Protocol, runtime_checkable

@runtime_checkable
class SourceTree(Protocol):
    """Read-only view of a source: the raw store (objects by digest, including member objects produced by the
    expand stage, AD-12) or a local --input tree opened through agentprov.ingest.paths (G.3.6)."""
    def walk(self) -> Iterator[CandidateArtefact]: ...       # deterministic (sorted by label), never follows symlinks
    def open(self, label: str, *, max_bytes: int) -> bytes: ...   # no-follow, S_ISREG, st_nlink == 1 (G.3.6)

@runtime_checkable
class Reader(Protocol):
    dialect_id: str                     # "agentdojo.tracelogger"
    version: str                        # reader SemVer, e.g. "0.1.0"
    variants: frozenset[str]            # closed list of variants this version recognises
    media_types: frozenset[str]

    def iter_artefacts(self, tree: SourceTree, profile: "SourceProfile") -> Iterator[CandidateArtefact]:
        """Discovery: apply profile.import.include/exclude globs and stray filters (.DS_Store, AppleDouble `._*`).
        Yields candidates in deterministic order. MUST NOT read file contents beyond size metadata."""

    def sniff(self, data: bytes, *, label: str, limits: "IngestLimits") -> SniffResult:
        """Cheap, total classification. `data` is the full object for JSON dialects within limits.max_json_bytes.
        Container dialects sniff the stored container only by magic bytes in T0 (G.3.1 step 2); their members are
        sniffed as member objects after the expand stage. MUST NOT raise for foreign input; returns
        SniffResult(match=False, reasons=(...)) instead."""

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: "IngestLimits") -> Iterator[LocatedItem]:
        """Strict parse of a sniffed object into located items (one per execution-bearing unit), using
        agentprov.ingest.loaders. Runs in a T1 worker (A3). Raises IngestError (limits; ingest.* codes, G.3.9) or
        MalformedArtefact (in-dialect parse failure); see §D.2.7."""
```

`IngestLimits` is `agentprov.ingest.limits.IngestLimits` with the defaults of G.3.2.

### D.2.4 Mapper protocol and mapping context

```python
@runtime_checkable
class Mapper(Protocol):
    mapper_id: str                      # == AER adapter.id, e.g. "agentdojo.tracelogger"
    version: str                        # adapter SemVer; recorded in the AER header
    accepts: frozenset[tuple[str, str]] # (dialect, variant) pairs
    namespaces: Mapping[str, str]       # ext prefixes it may emit -> IRI (https://w3id.org/agentprov/ns/<ns>#)

    def map(self, unit: ExecutionUnit, ctx: "MappingContext") -> Iterator["AerRecord"]:
        """Yield AER records in canonical serialisation order, starting with the `execution` header and
        excluding `seal`. Report non-fatal problems via ctx.issue(); never swallow them."""

class MappingContext(Protocol):
    profile: "SourceProfile"
    rules: "RuleCatalogue"              # merged catalogues declared by the profile, at the versions in the header
    mapping_id: str                     # "<adapter id>/<profile id>", e.g. "agentdojo.tracelogger/agentdojo-upstream"
    ex: str                             # import: agentprov.aer.ids.import_execution_id(mapping_id, sha256, loc)
                                        # (AD-04); live: "ex_" + UUIDv7 from the capture log
    def rule(self, rule_id: str, pointer: str | None = None) -> str:
        """Returns the scoped rule reference "<ns>.<rule>@<n>" or "<ns>.<rule>@<n>#<pointer>" (C.6.4);
        raises RuleNotDeclared at map time."""
    def issue(self, code: str, *, ids: Sequence[str] = (), rule: str | None = None,
              severity: Literal["info", "warning", "error"] = "warning", detail: str | None = None) -> None: ...
    def check(self, check_id: str, *, scope: str, verdict: Literal["consistent", "inconsistent", "unverifiable"],
              observed: Mapping[str, int], reason: str | None = None) -> None:
        """Profile-declared accounting check passed to the writer (C.12.4). Core checks (aer.acc.*) are computed by
        the writer, never by the mapper."""
    def open_auxiliary(self, role: str) -> bytes:   # digest-checked read of a declared auxiliary artefact
        ...

AerRecord = Mapping[str, Json]          # shaped by agentprov.aer.types (C.3); JCS-serialised by AerWriter
```

The core `agentprov.aer.writer.AerWriter` consumes the records. It checks backward references and closed fields in
streaming fashion (tier 2), computes the C.12 accounting checks once with `agentprov.aer.accounting`, appends the
`seal` with the issues collected by `ctx` and the accounting, and writes atomically through the T0 write gate.
**Mappers MUST NOT construct `seal` records.**

### D.2.5 Profile and catalogue models

`agentprov.adapters.profiles.SourceProfile` and `agentprov.aer.rules.RuleCatalogue` are frozen dataclasses loaded
from TOML with `tomllib`. They are validated against closed schemas (unknown keys are an error) and carry `sha256`
(of the TOML bytes) and an integer `version` (AD-18). Their formats are given in §D.4 and §D.5.

```python
def load_profile(profile_id: str) -> SourceProfile: ...        # package resources only (importlib.resources)
def load_catalogue(ns: str, version: int) -> RuleCatalogue: ...   # package resources only; the package ships every
                                                                  # released version (AD-14); absent -> rules.unavailable
def load_profile_file(path: Path, *, mode: Literal["dev"]) -> SourceProfile: ...  # dev-only; refused in release mode
```

### D.2.6 Live boundary

Core defines **no** `ExecutionBackend`, `CaptureHooks` or `ModelGateway` protocol. The live boundary is the backend
worker protocol `agentprov-backend/0.1` (§D.11.3) plus the `capture/0.1` raw evidence that the worker writes (C.13).
The harness-internal protocols are specified in §D.10.1 as `agentprov_backend` internals. [R-17, R-01]

### D.2.7 Errors, issues and their handling

The hierarchy lives in `agentprov.errors` (RESOLUTIONS §3.2). Exit codes follow MN N.1.3 (0 ok, 1 failures, 2 usage,
3 environment, 4 refused, 5 unsupported, 70 internal, 130 interrupted). [R-19, R-42]

```python
class IngestError(Exception): code: str          # G.3.9: tier-1 violation, closed ingest.* codes (owner G, K.11.1)
class IngestSafetyError(IngestError): ...        # adapter-layer subclass raised inside readers (G.11 #5)
class AdapterError(Exception): code: str
class ProfileError(AdapterError): ...            # invalid profile/catalogue/registry (package data): exit 70
class RuleNotDeclared(ProfileError): ...         # a mapper cited a rule absent from the catalogue: programming error
class MalformedArtefact(AdapterError): ...       # sniffed as this dialect but unparseable (invalid JSON, wrong types)
class UnsupportedVariant(AdapterError): ...      # recognised family, unsupported variant (e.g. AgentDojo pre_v0 dev logs)
class AdapterDefect(AdapterError): ...           # wrapper for any unexpected exception raised inside Mapper.map
class BackendUnavailable(AdapterError): ...      # backend environment not built or unverifiable: exit 3
class IdentityMismatch(AdapterError): ...        # built environment differs from the pinned identity (§D.10.6): exit 3
class UnsupportedConfiguration(AdapterError): ...# live config the backend cannot capture faithfully (e.g. a defence): exit 5
```

Exception messages never carry raw source text. Their arguments are passed through
`agentprov.ingest.quote.escape_untrusted` before they reach a terminal, a log or a traceback (G.8.2, R-42).

`Issue` (`agentprov.adapters.types`):

```python
@dataclass(frozen=True, slots=True)
class Issue:
    code: str                         # a seal issue code of C.12.3 or "<ns>.<code>" declared in the catalogue
    ids: tuple[str, ...] = ()         # AER local ids concerned
    rule: str | None = None           # "<ns>.<rule>@<n>" when the issue comes from a rule
    severity: Literal["info", "warning", "error"] = "warning"
    detail: str | None = None         # short machine-oriented text; never contains untrusted content verbatim
```

`Issue.detail` MUST NOT copy source text. Source strings are referenced by id and locator only, so untrusted text
never reaches logs or terminals through issues (§D.13).

### D.2.8 The "seal with issues, never discard" rule (normative)

Every candidate artefact that a profile selects for import, and every live cell attempt, MUST end in exactly one of
the following recorded outcomes.

1. **AER sealed clean.** No `error`-severity issues.
2. **AER sealed with issues.** For example: inconsistent accounting, unexecuted tool calls, imposed outcomes,
   identity conflict, incomplete run, unsupported sub-structure.
3. **Degenerate AER.** This covers an in-scope artefact whose bytes are within the tier-1 limits but that the mapper
   cannot map because of `MalformedArtefact`, `UnsupportedVariant`, `AdapterDefect` or a policy or parse violation of
   the strict loader (duplicate keys, `NaN` under the strict profile, BOM, invalid UTF-8; G.3.9 second class). The
   runner writes an AER that holds only the `execution` header (artefact, origin, adapter, `unit` per the dialect,
   `unk` for the task) and a `seal` carrying the issue `unparseable_artefact`, `unsupported_variant` or
   `adapter_defect` (C.12.3), with severity `error`, and the `ingest.*` code in `detail` where one applies. The raw
   bytes are stored before parsing and kept.
4. **Register entry** (`register.jsonl`, owner HL H.6.3; one code registry per RESOLUTIONS §3.8). This is used only
   for artefacts that are **not** mapped as executions, with a `<stage>.<code>` code:
   - `select.not_execution_artefact` (e.g. ROPE `runs/lh_cells.json` [sources/rope.md §8.4]);
   - `select.owned_elsewhere` with an `owner` field (e.g. AgentLAB files vendored in ROPE [sources/rope.md §5.3], the
     DRIFT runs vendored in AgentDyn [sources/drift.md §6.3], the survey's bundled AgentDojo `runs/`);
   - `select.dialect_planned` (e.g. survey ASB CSV; Inspect logs outside the supported producer band; STAC while
     planned);
   - `select.licence_blocked` (a part whose licence policy forbids packaging without a permission record);
   - `select.out_of_scope` (executions outside the part of a mixed-scope source that the corpus counts, by a recorded
     scope decision, e.g. AgentOps-Bench's clean and noisy non-safety runs, D-143, D-191);
   - `dedup.collapsed` (identical bytes found at more than one origin; ownership per the owner profile's
     `[lineage]`);
   - `ingest.<area>.<kind>` (G.3.9 first class: a resource or safety violation detected before or while storing,
     e.g. over `max_artefact_bytes`, a stream or archive bomb, a link in an input tree). Only the sha256 when
     computable, size, origin, code and the effective limit are recorded; the bytes are not stored.

   Each row carries `{stage, code, source_key "sha256:<hex>#" + JCS(loc), origin, profile {id, version}, owner?,
   detail?}`. An artefact that carries outcomes but no trajectory is never a register-only entry: it becomes an AER
   with `unit: "outcome_only"` (below). A seal issue enters the register as `map.<code>` and is never re-namespaced
   (R-13). The first revision's reason codes (`not_an_execution`, `excluded_by_profile`, `duplicate_of:`,
   `owned_by:`, `dialect_planned`, `rejected_unsafe`) are retired.

Consequences:
- A mapper that hits an unexpected structure mid-file MUST NOT raise. It MUST emit what it can, report an issue,
  and let the writer seal.
- `AdapterDefect` aborts only the affected unit. In release mode any `error`-severity `adapter_defect` or
  `unparseable_artefact` issue makes `agentprov package` fail, but the evidence is still written first.
- Empty-trajectory logs (`messages: []`; 207 AgentDojo with outcomes [sources/agentdojo.md §4.4]; 2 ROPE without
  outcomes [sources/rope.md §4.4]) are sealed AER with `unit: "outcome_only"` and the issue
  `no_execution_observed` (the 2 ROPE logs also `no_outcome_recorded`), not register entries (R-28). This
  **replaces** the baseline `EXCLUDED.json` policy for AgentPROV corpora [audit/legacy_replay.md §3.3 rule 7]. The
  compatibility profile still reproduces the baseline's exclusions from AER.
- Live: a failing cell is sealed (capture log closed with `session.end`, hash chain intact) with session status
  `errored`, `incomplete` or `aborted`; an inconsistent accounting verdict is a property of the mapped AER's seal
  (C.12), which the runner reads to decide a re-attempt. A re-attempt is a new session with `capture.attempt = n+1`.
  Every attempt keeps its own execution id and is never deleted (D5) [audit/capture.md §4.2.4 defect 5, §9.4].

### D.2.9 Importer runner contract (`agentprov.adapters.runner`)

This generalises the baseline converter's driver [audit/legacy_replay.md §3.3, §12].

```python
@dataclass(frozen=True)
class ImportFilters:
    include_paths: tuple[str, ...] = ()      # extra globs, ANDed with the profile
    variants: frozenset[str] | None = None

@dataclass
class ImportReport:
    counters: dict[str, int]   # seen, mapped, sealed_clean, sealed_with_issues, degenerate, registered,
                               # duplicates, skipped_resume, filtered
    register: list[dict]       # §D.2.8 case 4 rows, as written to register.jsonl
    issues_by_code: dict[str, int]
    limits: dict[str, int]     # effective IngestLimits (G.3.2), recorded verbatim
    adapter: str; adapter_version: str; profile: str; profile_version: int; profile_sha256: str
    rules: dict[str, int]      # {"agentdojo": 1, ...}

def import_source(
    source_id: str,
    tree: SourceTree,
    *,
    corpus: "CorpusWriter",               # the phase-3 minimal corpus writer (raw objects, origins, members, AER,
                                          # executions.jsonl, register.jsonl); no dependency on the sealing phase
    profile_id: str | None = None,        # default: the registry's primary import profile for the part
    filters: ImportFilters = ImportFilters(),
    limit: int | None = None,             # counts mapped units only; 0 maps nothing; None = no limit
    dry_run: bool = False,                # writes and deletes nothing
    mode: Literal["dev", "release"] = "dev",
) -> ImportReport: ...
```

Normative behaviour:
- Discovery order is deterministic (sorted labels).
- Every artefact is put in the raw store **before** parsing (A2), through `agentprov.raw.store.put_stream`;
  containers are expanded into member objects by the `expand` stage before any member is sniffed (AD-12).
- Parse and map run in T1 workers (`agentprov.io.workers`, A3); the T0 parent runs the write gate.
- **Resume key.** The key is `(ex, artefact sha256, adapter version, profile sha256, catalogue versions)`. A unit is
  skipped only if a sealed AER with an identical key exists (AD-10 row 11: no derivation-key build cache).
- **Persisted ex index.** It is consulted for collisions. Two units with the same `ex` but different AER digests
  produce an `ex_conflict` error. The second unit is not written; this is a named failure and nothing is
  half-written. The same bytes reached through two locations under the same profile produce one AER; the artefact
  keeps one origin and every further location is a `raw/origins.jsonl` row. Byte-identical copies mapped under
  another profile get another `ex` (the mapping id differs, AD-04); `source_key` ownership in the owner profile's
  `[lineage]` keeps them from being counted twice (`select.owned_elsewhere` or `dedup.collapsed`)
  [sources/agentdojo-inspect.md §6.6].
- Sealed and released trees are refused by manifest seal, not by name [audit/legacy_replay.md §5].
- Exit status (MN N.1.3) is 0 when all units are sealed clean or with issues, 1 when any unit is degenerate or
  failed, 3 for an environment error (including the release-mode interpreter refusal of §D.13.1), and 70 for a
  profile or registry error.

**Implementation resolutions (phase 6, import, 2026-10-08).** The code is the reference
(`agentprov.adapters.runner.importer.import_source`); the command around it is MN N.2.2 (its phase-6 note).

1. **Placement and layering.** `adapters/runner.py` became the package `adapters/runner/` (`__init__.py` keeps the
   phase-4 functions; `importer.py` holds `import_source`; `provjob.py` holds the T1 job `prov`). M.5.1 assigns a module to
   the component of its *longest* matching prefix, so `adapters.runner` and `adapters.registry` are L6 while
   `adapters.<family>` stays L4; `tests/boundary/test_import_boundary.py` classified by the first path segment only and now
   implements the longest-prefix rule (`TWO_PART_COMPONENTS`). The runner imports the corpus layer (L5) and receives the
   opened `CorpusWriter` from the CLI, as M.5.2(1) says.
2. **Signature.** `import_source(source_id, tree, *, corpus, profile_id, filters, limit, dry_run, mode, part, snapshot_id,
   corpus_id, until, prov_specs, workers, in_process, limits, retry_failed, progress, pin_check, resume_index, batch_size,
   pin)`. `corpus=None` with `dry_run=True` runs into a private temporary tree. `ImportFilters` gains `select` (AER-header
   keys, MN N.2.2 note item 5). `ImportReport` has `failures`, `notices`, `partial` and `corpus_root` besides D.2.9's fields;
   its counters are those of MN N.2.2 (`registered` is kept, `failed`, `derived` and `validated` are added).
3. **Trees.** `LocalTree` (`--input`: `ingest.paths.discover` and `open_evidence`; rejections that match an include glob
   become `ingest.*` register entries) and `GitPinTree` (`--fetch`: the pinned tree in the fetch cache). Discovery is the
   reader's `iter_artefacts` over the walked list; `excluded` counts include-glob matches removed by an exclude glob.
4. **Origins.** Every stored object has a pinned origin. A local `--input` file needs a `PinCheck` (blob ids against a
   cached git tree listing, or the J.1.4 listing digest for a pin with `listing_sha256`, whose object origin the reader's
   optional `listing_origin(pin, label)` supplies); an unvouched file is registered `raw.origin.blob_mismatch` and not
   stored, because the release-mode AER writer refuses `local` origins (C.17 AER-V20). Without a pin check a local tree is
   refused (`raw.origin.local`, exit 4).
5. **Containers.** A reader that has `plan` and `member_patterns` (the Inspect family) is a container dialect: the
   candidate is stored, expanded by the versioned `expand` stage with the reader's member patterns, and one `map` job per
   container (mode `container`) runs the reader's `plan` over the member objects and maps every unit with the `header.json`
   bytes as the auxiliary artefact (`map_unit(auxiliary=...)`). Plan register rows become `select.dialect_planned` entries
   with the subject path `<container>!/<member>`. `--limit` applies to the units of a container in plan order.
6. **Whole files.** `map` jobs run in mode `total` (`map_artefact_total`): bytes that fail the strict loader, or a
   `MalformedArtefact` while parsing, give a degenerate AER (`unparseable_artefact`, the `ingest.*` code in `detail`);
   valid JSON of another dialect is `select.not_execution_artefact`. A worker crash or limit gives a degenerate AER with
   `adapter_defect` and a `worker.limit.*` entry. When the family's degenerate header is itself refused by the write gate
   (`aer/0.1` requires `task.task_id`), the artefact stays stored and gets `map.adapter_defect` (failed): it is never
   dropped. Under `aer/0.2` (D-219, regen item 151) a family that names the task only from the parsed value (the
   AgentDojo family with DRIFT, adprov, FooBench) declares `unk {"/task/task_id": "not_captured"}` when no value was
   read, and the degenerate AER seals; its run scope then cites the whole artefact (`{"a": "a0"}`), since a root pointer
   does not resolve for bytes that are not JSON.
7. **Write gate and derived layers.** The parent seals each outcome (`AerWriter`), applies the post-mapping filters, writes
   the AER and one register entry per seal-issue code (`map.<code>`, ids merged; the severities HL H.6.3 states for core
   codes take precedence over a mapper's default `warning`), and runs the AER validator in the runner's mode with locators
   resolved against the raw store. The `prov` job (T1, G.4.1 MAY) derives `agentprov-prov/0.1` from the sealed bytes,
   staged in a scratch store outside the corpus, and runs the tier-4 validators (strict in release mode); it runs on a
   background thread while the next batch maps. Batches are 256 candidates; results are consumed in candidate order.
8. **Index completeness.** `known_incomplete` when the seal accounting is `inconsistent` or a seal issue proves loss
   (`incomplete_run`, `retry_passes_inferred`, `aborted_attempt`); `verified_complete` only when the accounting is
   `consistent` **because at least one accounting check was evaluated** and the unit is an `agent_execution`
   (`importer.index_completeness`); else (and for a degenerate AER) `unverifiable`. `fold_status` of no verdicts is
   `consistent` (vacuous; the `aer/0.1` seal is unchanged), so an outcome-only record, an empty log and a run error
   before the first assistant turn, which evaluate no check, are `unverifiable`. Phase-10 analysis B2, 2026-10-11:
   the earlier rule gave `verified_complete` to 232 head and 2 ROPE executions with zero checks.
9. **Determinism.** The outputs are byte-identical for `--in-process`, one and three workers and batch sizes 1, 3 and 256
   (`tests/adapters/runner/test_import_pipeline.py`), and across `--jobs` through the CLI (`tests/cli/test_import_cmd.py`);
   the working `corpus.json` differs only in `producer.isolation`.
10. **Deferrals part A (2026-10-12; D-200..D-204, proposals).** Trees gain `ArchiveTree` (a download pin's file whose
    members are the artefacts; `archive_input`), expanded before discovery so that the members, read back from the raw
    store, are the candidates; `[import] blobs` files are stored before mapping and offered to each `total` map job as
    `blob:<hex>` inputs (params `blobs`); the resume key also recognises an execution another snapshot of the corpus
    mapped (H.7.2 collapse, `CorpusWriter.add_snapshot`). MN N.2.2's deferrals note is the command-level record.
11. **Split archive inputs and top-level tars (2026-10-13; D-247..D-249, user-approved).** A download pin with
    `archive = "split-zip"`, a logical `file` and ordered `parts` (`{file, bytes, sha256, md5?}`, each pinned) is an
    archive input stored as byte parts: `--input DIR --verify-against-pin` checks every part offline (by its pinned file
    name and digests), `--fetch` fetches every part and needs the large-download consent when the parts' total reaches
    100 MiB; `ArchiveTree.split` stores each part with its pinned origin, the split descriptor with a `split` origin, and
    expands the descriptor with its parts; the snapshot records `input.parts` (`input.sha256` is then the descriptor's
    digest and `input.bytes` the sum of the parts, the logical archive's size); `StoredRawTree` replays it. A deposit
    pin's top-level `tar.gz` or `tar.zst` is an archive input like a zip (D-247, D-240), with pax `x` headers read under
    D-248's allowlist.
12. **Multi-execution whole files (R-10k-1, D-320; 2026-10-13).** A whole-file reader may declare
    `multi_execution = True` (only `credleak.cell` does): its `parse` yields one located item per execution (HL H.7.1,
    e.g. `{"p": "/runs/<i>"}`). Its `total` map jobs carry `per_item` (`map_artefact_units`) and frame each item as
    container mode does, `{"unit": {"sha256", "loc"}}` then its records and seal (`split_unit_frames`). Each execution
    is resumed (`skipped_resume`) and collapsed across snapshots (H.7.2, D-202) by its **source key**, after mapping; its
    `dedup.collapsed` entry has the subject `{source_key}` (H.6.2), so each collapsed execution has its own entry (a
    third snapshot collapsing the same key repeats that entry's `rid` and merges into it; the row's `snapshot_ids`
    still list every snapshot). `--limit` counts each execution. Bytes that fail the strict loader, and a crashed or
    limited job, still give **one** degenerate AER for the file (document-root locator `{"p": ""}`). A file whose
    document-root key is indexed is resumed (or collapsed) **whole** before mapping, as a single-item file is by its
    digest: it is never re-mapped into its items, which would hold the same evidence twice, and the indexed degenerate
    row is not rewritten (deferrals-session review). A file of the dialect with no item is `select.not_execution_artefact` (`not_imported`,
    detail `no execution in the file (0 located items)`): no execution is invented (invariant 2). Readers that do not
    declare the attribute keep the digest-keyed resume, the path-subject `dedup.collapsed` and exactly today's frames
    and job parameters; `map_artefact_total` keeps the single-item rule for every reader. The keys are locator-neutral:
    `{"p": "/runs/<i>"}` is exercised by the credleak tests and `{"line": n}` by
    `tests/adapters/runner/test_multi_execution_lines.py` (a test JSONL reader in an archive input: per-line keys,
    resume after an interrupt, `--limit`, the whole-file rule after a crash, and a two-snapshot collapse).
13. **Rejected rows of multi-execution files (D-321; 2026-10-13).** A `multi_execution` reader may define
    `rejected(data, artefact, *, limits)`, yielding `adapters.types.Rejected(locator, code, detail)` for each row its
    `parse` does not yield. The two partition the file's rows. It runs only in the T1 `map` job
    (`runner.rejected_rows`), never in T0, and also for a file that has no execution: valid input of another kind, or a
    dialect file with no item. Its rows then replace the file-level `select.not_execution_artefact` entry.
    - The job emits `{"register": {"code", "detail", "loc"}}` frames before the unit frames, in canonical locator order
      (JCS of the key locator). It emits none for a file sealed whole as one degenerate AER (D-320).
    - The parent validates every row before registering any:
      - the code is `select.not_execution_artefact` or `select.out_of_scope`;
      - the locator is a key locator naming an element, neither the document root nor an execution's locator, and no
        two rows share one;
      - the detail is accepted by the register's own check (at most 200 characters, no control character).
    - Any failure seals the whole file as one degenerate AER (`map.adapter_defect`, detail `adapter.rejected_invalid`),
      with no row, no execution of it, and none of the blobs its job carved (D-218) stored.
    - Each valid row is registered with subject `{source_key}`, stage `select`, severity `info` and disposition
      `not_imported`, so it is a **candidate** (H.6.1 R1/R5; the user's ruling, option A).
    - A resume registers no row twice (`skipped_resume`). A re-map re-derives the rows from the stored file; a
      re-derive carries them (`corpus.derive`).
    - A `{source_key}` `not_imported` entry belongs to no single snapshot of a multi-snapshot corpus, so sealing and
      `verify` refuse such a corpus with `corpus.manifest.unattributed`. Attribution by origins (option B, a `corpus/`
      change for the deferrals session) is built when the first such corpus is needed.
    - The working `corpus.json` still counts files as `candidates`, the importer's `seen`. Sealing recomputes the
      counts.
    - Tests: `tests/adapters/runner/test_rejected_rows.py`.
14. **Streamed multi-execution files and profile-raised limits (D-323; 2026-10-14).**
    - **Which readers.** A `multi_execution` reader that also defines `sniff_stream(handle, *, limits)` and
      `parse_stream(handle, artefact, *, limits)` streams (`runner.streams`). Its `per_item` jobs carry `stream`.
    - **Store-first.** `_job_map_stream` opens the stored primary with `JobContext.open_input(0)`, which hashes the
      whole object and fails the job on a mismatch before the reader sees a byte (G.4.5).
    - **Mapping.** Each item is mapped (`_map_item`, shared with the byte path) and framed at once. The mapper may
      carve from a lazy reader of the stored primary (D-218). Classification is the byte path's: a loader reason seals
      the file whole; other input is `not_dialect` (or `rejected_stream` rows, D-321); another part is `select`.
    - **Abort.** Only the reader's iteration can abort a file. A final `{"abort": {issue, code, variant}}` frame makes
      the parent skip `_carved` and seal the file as one degenerate AER (`_seal_whole`). A mapping failure stays one
      item's degenerate AER, and an emit failure fails the job (`worker.limit.*`), as on the byte path.
    - **Memory.** The worker holds one item at a time. The parent still holds the job's frames: about 767 MiB for the
      105.7 MiB MCPHunt document.
    - **Profile-raised limits.** A source profile may declare `[import] limits` with only the fields of
      `ingest.profile_limits.PROFILE_RAISABLE` (today `max_json_element_bytes`, up to the calibrated 64 MiB). The raise
      is raise-only and checked at profile load. `import_source` applies it (`adapter.limits_conflict` against another
      explicit value). `corpus.json` records it as an override, and `recompute` passes the profile version the limits
      were recorded under (`limits_recorded_under`). Under the same version it refuses a difference with the profile
      (`corpus.derive.limits_mismatch`). Under a bumped version (D-31) the bump explains the change, and the current
      declaration applies. A sealed `corpus.json` has no `limits` record (`corpus-0.2` is closed), so `recompute`
      rebuilds the overrides from the profile its `aer` stage records, applied to the defaults, and keeps them only when
      their digest equals that stage's `limits_sha256`; otherwise it keeps the defaults and the refusal stands (D-1001).
      One worker resource cap is profile-raisable (D-931): `[import] map_rss_bytes` raises the
      memory cap of the source's `map` jobs (raise-only, from the default map cap up to the worker ceiling
      `RSS_CAP_CEILING`, checked at profile load); the importer puts it on each map job (`Job.limits`), and an
      `import --size-hints` admission charges it. It enters no digest. MCPHunt declares 4 GiB: its three largest
      documents peak at 1,322-1,686 MiB in the map job, above the default cap's watchdog trigger on a fast-allocating
      host (2 GiB minus the margin, D-825).
      `[import] prov_rss_bytes` (D-935) does the same for the source's `prov` and `validate` jobs (raise-only from the
      prov cap): `import` puts it on each prov job, `validate` and `recompute`/`derive` read it from the profile
      version the corpus records. DTap declares 16 GiB: its PROV grows with the square of a run's model calls, and
      tier 4 of a 100 MB document needs about 8 GiB.
    - **Tests and calibration.** `tests/adapters/runner/test_stream_items.py` and
      `tests/unit/ingest/test_profile_limits.py`; calibration in `docs/reports/r10k1/d323-calibration.md`.

15. **Container members of archive inputs and declared nested archives (ingest-formats-3; D-380..D-385; 2026-10-13).**
    - **Lifted refusal.** An archive input of a container dialect is no longer refused (D-200's exit 5). The archive is
      expanded, with its declared nested archives (`[import] nested`, D-382), each stored as its own member object
      (D-381 (a)).
    - **Candidates.** The selected members of every expanded level are candidates under their chain label
      (`<nested label>!/<member label>`). A container member goes to `map_containers`, never `map_whole_files`. There
      it opens at its absolute level (`ContainerSpec.depth`) under its chain's depth allowance.
    - **Globs.** Profile globs match each member's own label. The profile must declare `[import] include`.
    - **Subjects.** Every member of an archive input has the subject `<input>!/<chain>[!/<member>]`
      (`ContainerSpec.prefixed`).
    - **`derivation.json`** gets one `expand` entry per expansion function, keyed by `(stage, fn_digest)` everywhere
      (`corpus/stages.py`).
    - **Re-maps.** A re-map refuses an archive selection that the source did not record.
    - **Duplicates** collapse on object digests in chain-label order (D-385).
    - **Location independence.** An `.eval`'s rows and AERs do not depend on where it was found
      (`tests/adapters/runner/test_nested_archives.py`).
16. **URL download pins as archive inputs (D-455; 2026-10-15, user-approved).** A `url` pin naming a `file` is a download
    pin like `zenodo` and `hf` (`DOWNLOAD_PIN_KINDS`): `--input FILE --verify-against-pin` checks it offline, `--fetch`
    reads it from the fetch cache (network only with `--allow-network`), and it is expanded as an archive input. Its
    origin is `url {url, retrieved}`. The retrieval time is the fetch cache's acquisition record
    (`FetchResult.retrieved_at`, read back on a cache hit), else the pin's `retrieved_at` (RFC 3339 UTC); with neither the
    import is refused (`raw.origin.unpinned`, exit 3), never stamped with the time of the import. The snapshot `pin`
    records `retrieved_at` and the seal builds `{kind: url, url, retrieved_at}` (H.2.3). A pin with a date-only
    `retrieved` key is refused (`raw.origin.unpinned`); a URL archive in byte parts is refused (`adapter.archive_input`).

17. **The account-path lint at selection (regeneration-batch item 108; the D-510 safeguard; fail closed).** Before
    mapping, the runner checks every selected file's label for an account-directory shape
    (`agentprov.adapters.account_paths`):
    - slashed `home/<x>/`, `Users/<x>/`, `scratch/<x>/`, `mfs1/u/<x>/` (AgentDojo's fictional `home/user` is exempt);
    - the munged forms `_home_<x>_`, `_Users_<x>_`, `_scratch_<x>_` and `_ceph_…_{students,users,home}_<x>_`.

    A file whose shaped segment no `[[family.<f>.redact]]` pattern of its profile matches is held as
    `select.redaction_pending`. That is a warning at stage `select`, `not_imported`, with the detail naming the shape and
    segment index, never the segment. A profile can exempt reviewed labels with `[import] account_path_exempt` (globs).

    Measured on 2026-10-20:
    - 0 hits over the about 137k labels of the stored corpora;
    - over every staging clone, only EnvironmentOptim's 5,912 `munged_cluster` paths, which its rule covers (D.6.21
      item 1).

    So no stored corpus changes. The lint only blocks a future source that names an account and declares no rule.

    The hold runs after RD-3's `pin_candidates` snapshot (CD-8). A listing pin is checked over the whole selected
    listing, held files included, so holding a file never turns the others into `raw.origin.blob_mismatch` (pre-round
    review #7). A rule covers an account only when one of its matches in that segment includes the account token, and,
    for a rule with a `labels` allowlist (D-607), when the token's `{span12}` label, salted with the profile id, is
    listed. A match elsewhere in the segment, or an unlisted token, leaves the file held (pre-round review #19).

---

## D.3 Registry (`agentprov.adapters.registry`)

### D.3.1 Data model

The registry is the package `agentprov.adapters.registry` (RESOLUTIONS §3.2): `__init__.py` holds the literal data,
the factory tables and `EXTERNAL_OWNERS` (owners that are not registry sources, written `ext:<name>`, e.g.
`ext:agentlab`); `claims.py` is the one claims and lint library (registry-generated claim phrases, I.4
must-not-claim items as lint rules) shared by the README, the datasheets and the paper; `render.py` renders
`agentprov info` (§D.3.5). There is **no entry-point plugin loading** (D4). Reader and mapper factories are dotted-path strings resolved lazily with `importlib.import_module`.
The resolver MUST refuse any target outside the `agentprov.` namespace, so registry import never imports a benchmark.
Backends are not import targets at all: they are separate projects addressed by id (`BACKENDS` below). The registry
is the **only** status store; profiles carry no status (R-45). [R-15, R-45]

```python
Status = Literal["supported", "partial", "planned", "not_possible"]
Role = Literal["source", "mirror", "owned_elsewhere", "compat_oracle", "context", "not_executions"]
Evidence = Literal["yes", "partial", "no"]

@dataclass(frozen=True)
class LicencePolicy:
    spdx: str | None                  # "MIT", "CC-BY-4.0", "CC-BY-NC-4.0", "Apache-2.0"; None if no licence
    licence_ref: str | None = None    # non-SPDX notices, e.g. "LicenseRef-NIST-Software"
    holders: tuple[str, ...] = ()
    data_licence: str | None = None   # explicit data licence if any (None = none found)
    policy: Literal["include", "reference", "nc_partition", "forbidden"] = "reference"   # registry licence policy
    restrictions: tuple[str, ...] = ()   # use clauses carried verbatim (e.g. AgentHarm); part of the deposit key
    basis: str = ""                   # rendered verbatim into DATASHEET.md, e.g. "MIT as declared; not legally settled"
    attribution: tuple[str, ...] = () # citations / notices the packager MUST emit (LICENSES/, DATASHEET)
    unassessed: tuple[str, ...] = ()  # e.g. "model-provider terms on redistributing outputs"

@dataclass(frozen=True)
class Capability:
    part: str                         # e.g. "head", "2024-06", "live", "agentharm"
    role: Role = "source"
    evidence: Evidence = "yes"        # evidence availability (A6)
    import_status: Status | None = None   # None renders "—"
    live_status: Status | None = None
    caveat: str | None = None         # required when a status is "partial" or a live part has no real-model run
    verification: Literal["verified"] = "verified"   # every row has an adversarial verify report (R-63)
    dialects: tuple[str, ...] = ()    # import: dialect ids read; live: native dialects written besides capture/0.1
    variants: tuple[str, ...] = ()
    reader: str | None = None         # "agentprov.adapters.agentdojo.dialect:TraceLoggerReader"
    mapper: str | None = None         # "agentprov.adapters.agentdojo.mapper:TraceLoggerMapper"
    backend: str | None = None        # backend id, a key of BACKENDS ("agentdojo", "autodojo")
    profile: str | None = None        # profile id
    via: str | None = None            # import served by another source's profile (e.g. autodojo -> rope)
    mirror_of: str | None = None      # byte-identical mirror (e.g. agentdojo-inspect -> agentdojo)
    owner: str | None = None          # for role owned_elsewhere / mirror: the owning source (or EXTERNAL_OWNERS key)
    corpus_id: str | None = None      # e.g. "agentdojo-upstream", "ast-survey-agentharm"
    sealed: tuple[SealedCorpus, ...] = ()  # display only (README, user guide, `info`): the sealed corpora (id, version; .tag = corpus/<id>/v<version>, the annotated tag on the sealing commit) holding the part; imports key on corpus_id
    requires: tuple[str, ...] = ()    # "backend:agentdojo", "backend:autodojo", "keys", "consent", "gate:hf"
    semantics: tuple[str, ...] = ()   # semantics profiles "<id>@<v>" the import applies (phase 7; HL H.2.5 profiles.semantics)

@dataclass(frozen=True)
class SourceRegistration:
    source_id: str
    name: str
    family: str | None
    capabilities: tuple[Capability, ...]   # one per part, in rendering order
    licence: LicencePolicy
    evidence_refs: tuple[str, ...]    # investigation report refs, rendered in `info --source`

@dataclass(frozen=True)
class BackendDescriptor:
    project: str                      # "backends/agentdojo"
    protocol: str = "agentprov-backend/0.1"
    worker_module: str = "agentprov_backend.worker"
    capture_mapper: str = "agentdojo.capture"
    profile: str = "agentdojo-live"

REGISTRY: tuple[SourceRegistration, ...] = (...)   # order = rendering order
READERS:  Mapping[str, str] = {...}   # dialect id -> factory path (agentprov.* only)
MAPPERS:  Mapping[str, str] = {...}   # mapper id -> factory path (agentprov.* only)
BACKENDS: Mapping[str, BackendDescriptor] = {...}   # "agentdojo", "autodojo"
EXTERNAL_OWNERS: Mapping[str, str] = {...}          # e.g. "ext:agentlab" -> citation
```

### D.3.2 Status semantics (closed; used by `info`, the datasheet and the manuscript)

| Status | Meaning (import) | Meaning (live) |
|---|---|---|
| `supported` | Reader, mapper and profile are implemented. Golden fixtures from the real source pass in CI. Known evidence gaps are declared as `unk` and quirks. **And** the part imports its full pinned snapshot with zero crashes, every file sealed (with or without issues), with the counts recorded in `docs/reports/` (HON-10). | The backend is implemented. CI drives a real benchmark task end to end through the backend worker (scripted transport allowed). Identity guards are active. |
| `partial` | Implemented, but a declared, material portion of the released evidence is not mapped, or the evidence is structurally incomplete (e.g. DRIFT tool outputs edited in place). The caveat MUST say which. A part that would be `supported` except for the full-snapshot import renders `partial` with the caveat "full snapshot not yet imported". | Implemented for a declared subset of configurations only. |
| `planned` | Not implemented in v0.1. A dialect sniff MAY exist so that artefacts are recognised and registered as `select.dialect_planned`. | Not implemented. |
| `not_possible` | No per-execution evidence is released. | No viable capture surface, or no permission. |

Rules. [R-15, R-25]
1. **Targets, not facts.** The values in §D.3.3 (and I.1.1) are **v0.1 targets**. The registry carries, for each
   part, the value its gate supports at release time; it downgrades any part whose gate fails, and it never raises a
   status without its gate.
2. **No best-case aggregation.** Any rendering that shows one status per source shows it per part, or shows the worst
   status over the parts with the marker `mixed`. It never shows the best.
3. **Live caveat.** A live part without an approved real-model run carries the caveat "fake-client tested in v0.1;
   no real-model run" (R-25). "Live Capture" in any title needs a sealed, non-`test_only` live corpus approved by the
   user (AD-08, U-18).
4. The registry MUST NOT claim `supported` for a part without an ingestion path (user requirement, D11).
5. Part roles replace the first revision's ad-hoc labels: `mirror` (byte-identical copy owned by another source),
   `owned_elsewhere`, `compat_oracle` (the converted legacy tree), `context`, `not_executions`. The status vocabulary
   has no `supported_with_caveat` or `not_distinct` values (R-15).

### D.3.3 v0.1 registry content

The table reproduces I.1.1 as amended by R-07, R-15, R-25, R-28, R-29 and R-62. I.1.1 is the single source of the
values; the registry data, `agentprov info`, MN N.3, HL H.4.2 and A.5 are generated from it or compared against it.
Every row has `verification = "verified"` (the verify reports exist, R-63). [R-15, R-07, R-29]

| source_id · part | Role | Evidence | Import | Live | Dialect · variants | Licence policy → raw policy | Caveat / note |
|---|---|---|---|---|---|---|---|
| `agentdojo` · `head` (@`089ed468`) | source | yes | supported | — | `agentdojo.tracelogger` · `v0.k11`, `v1.k14`, `v1.k14.incomplete` | include → include | Owner; profile `agentdojo-upstream`; corpus `agentdojo-upstream` |
| `agentdojo` · `2024-06` (@`c274885`) | source | yes | supported | — | `v0.k11` · 18,241 (incl. 7 Mixtral) | include → include | Same corpus as `head`; the two snapshots are never conflated (records carry their own origin commit) |
| `agentdojo` · `history` | source | yes | planned | — | `v0.k11` (+ `pre_v0`, planned) | include → include (opt-in) | Superseded blobs; fingerprint dedup deferred (AD-10) |
| `agentdojo` · `live` | source | n/a | — | supported | `agentprov.capture/0.1` + native `v1.k14` | include → include | `backends/agentdojo` (`agentdojo==0.1.35`), `llm_element` `native` by default; gated `partial` (D-720), caveat: the D-720 subset (local model servers with consent; API endpoints with consent and both caps); real-model pilot 2026-10-22, not sealed (D-722, D-729) |
| `adprov-v1` · `release` | source | yes | supported | — | `adprov.transcript_v1` · `v1` | include → include | Released AgentDojo-PROV corpus (Zenodo `10.5281/zenodo.21052314` [verify/agentdojo.md §2.2]); derived licence per U-03 |
| `adprov-v1` · `converted-legacy` | compat_oracle | derived data only | — | — | `adprov.transcript_v1` (timing stubbed) | — (derived data, no raw; statement per U-03) | Compat oracle; superseded by the native import `agentdojo` · `2024-06` since the full R1/R2 claim gate passed with 0 mismatches (2026-10-08, J.4.6; AD-07); owner of the executions `agentdojo` |
| `agentdojo-inspect` | mirror | no (own) | not_possible (`mirror_of = "agentdojo"`) | planned (via Inspect; prefer `inspect_evals`) | — | reference → reference | NIST notice + MIT; mirror location only |
| `agentdyn` · `a` | source | yes | supported | planned | `v1.k14` · 38,281 | include → include | MIT as declared (AgentDojo notice); basis recorded verbatim |
| `agentdyn` · `b` | source | yes | partial | — | `v0.k11` · 5,184 | include → include | Progent, vendored AgentDojo 0.1.29; mapped since D-933 (profile `agentdyn` v4, part b's census) |
| `agentdyn` · `c` | source | yes | partial | — | `drift.k18.messages` · 4,258 | include → include | Re-keyed copies of AgentDyn's **own** history blobs (`runs/DRIFT/**`, edge E11, owner `agentdyn`; R-62); stretch |
| `agentdyn` · `d` | owned_elsewhere | yes | — | — | `drift.k18.conversations` · 949 | — | Byte-identical to `drift` · `head`; owner `drift` |
| `agentdyn` · `history` | source | yes (git) | planned | — | mixed | reference → reference | Fingerprint dedup deferred (AD-10) |
| `autodojo` · `live` | source | n/a | — | supported | `agentprov.capture/0.1` + fork `v1.k14` | include → include | `backends/autodojo` @ `aa458794…`; gated `partial` (D-720), caveat "isolated env"; the D-720 subset (local model servers with consent; API endpoints with consent and both caps); local real-model pilot 2026-10-22, not sealed (D-722, D-729) |
| `autodojo` · `rope-slice` | source | partial | partial (`via = "rope"`) | — | `v1.k14` (inside ROPE) · 2,847 | include (in corpus `rope`) | Owner `rope` |
| `autodojo` · `caches` | not_executions | no | — | — | `injections.json` optimiser caches | include → include (context artefact) | Payload inputs to `rope` (E17) |
| `rope` | source | yes | supported | planned | `v1.k14` · 10,791 | include → include | Owner of the AutoDojo-attack slice; `agentlab/res/**` not selected (`select.owned_elsewhere`, owner `ext:agentlab`) |
| `drift` · `head` | source | yes | partial | planned | `drift.k18.conversations` · 1,569 | include → include | Tool outputs post-isolation; sub-LLM calls unlogged; no payload map; stretch |
| `drift` · `history` (@`53dbc6c`) | source | yes | planned | — | same · 1,046 | reference → reference | Committed before any licence statement |
| `drift` · `asb` | source | partial | planned | — | ASB result CSV | include → include | CSV and Python-literal parsing deferred (AD-10 row 16) |
| `midojo` | source | no | not_possible | planned (not v0.1) | — | — | Apache-2.0 |
| `adi` | source | no | not_possible | planned (ADI's own fork, isolated env) | — | — | MIT plus attribution paragraph (GitHub NOASSERTION) |
| `agent-security-tools-survey` · `agentdojo-runs` | source | yes | supported | — | `v1.k14` · 3,243 | include → include | Profile `survey-runs`; corpus `ast-survey-agentdojo` |
| `agent-security-tools-survey` · `agentharm` | source | yes | supported (band `inspect_ai 0.3.247.dev69`; gate recorded 2026-10-08, see below) | planned (via Inspect) | `inspect.eval` · `v2` · 6 logs, 1,056 samples | include → include, with the AgentHarm use clause in `licences.restrictions` | Profile `survey-agentharm`; **separate** restricted-use corpus `ast-survey-agentharm` (U-05) |
| `agent-security-tools-survey` · `asb` | source | partial | planned | — | ASB result CSV · 1,200 rows | include → include | `select.dialect_planned` in v0.1 |
| `agent-security-tools-survey` · `zenodo-bundled-runs` | mirror | (mirror) | — | — | AgentDojo `runs/` copy · 36,679 | — | Owner `agentdojo` (`select.owned_elsewhere`) |
| `mandate-agentdojo-eval` | source | yes | supported | planned (not v0.1) | `v1.k14` · 396 | include → include | Publisher unverified; basis recorded verbatim |
| `stac` (MultiTurnAgentAttack) | source | partial (scenario records) | planned | planned | `stac.json_array` · `v1` · 483 records | nc_partition → include in a `-nc` corpus (none built in v0.1) | Scenario records, not executions (`unit: scenario`, §D.8) |
| `ciaware-bench` · `github-records` | source | partial (fragments) | planned | — | gzip JSONL/JSON records | reference → reference | Derived, lossy |
| `ciaware-bench` · `hf-gated` | source | partial (listing and hash-bound only; content unobserved) | planned | planned (low priority) | `inspect.eval` · 2,538 | reference → reference | Import planned until content is observed after the user accepts the gate (U-04); training-use prohibition and 3 canary GUIDs carried in `licences.restrictions` |
| `ciaware-bench` · `hf-anon-mirror` | source | yes | planned | — | `inspect.eval` (inspect_ai 0.3.200) · 798 | reference → reference | Planned unless a committed, licence-cleared fixture exists; identity-fingerprint duplicates `not_imported` pending validation |
| `ciaware-bench` · `ciabench` | source | yes | planned | — | `inspect.eval` (inspect_ai 0.3.170) · 1,735 | reference → reference (default; U-04) | Outside the v0.1 Inspect band; licence per U-04 (card-metadata MIT recorded "not legally settled" only if the user accepts it). No scrubbing of raw bytes |
| `dtap` · `head` (@`836caf2f`; tasks @`a3edc9b7`) | source | yes | planned (phase 10b, D-26) | — | `dtap.trajectory` · `v1` · 67,808 trajectory files (67,806 parseable; 20 synthetic registered) | include → include, subject to the secrets decision (§D.16.13) | Apache-2.0 per both dataset cards; profile `dtap-bench`; corpus `dtap-bench`; §D.16 |
| `credleak-p15b` · `head` (Zenodo 22737462 v3) | source | yes | planned (phase 10k, D-260) | — | `credleak.cell` · `v1` · 643 cells, 19,636 runs | include → include, with the profile's `[withhold]` policy (D-265) | Planted canary credentials withheld at sealing (325 cells, 5,422 runs); the runner maps one execution per run (R-10k-1, D-320); the full import waits for the product-path trial and the regeneration round; §D.19 |

Totals and the separation of `outcome_only` records (207 AgentDojo, 2 ROPE) and STAC scenario records follow I.1.1.

**Gated values in this build (2026-10-11).** The registry (`agentprov.adapters.registry`) holds the parts of this table
whose importers exist, with the values their gates support (rule 1); `agentprov info` renders them.

| source_id · part | Import (gated) | Evidence of the gate |
|---|---|---|
| `agentdojo` · `2024-06` | supported | full pinned snapshot through `agentprov import --fetch --release`: 18,241 / 18,241 sealed, 0 degenerate, all AERs valid, all derivations pass tier 4 (`docs/reports/agentdojo/import-cli-2024-06.json`); gate R (`gate-r-full.json`) |
| `adprov-v1` · `release` | supported | 17,664 / 17,664 through `agentprov import --verify-against-pin --release` (listing digest verified), same checks (`docs/reports/adprov/import-cli-release.json`); gates A1/A2/B (`docs/reports/migration/`) |
| `adprov-v1` · `converted-legacy` | — (compat oracle) | superseded by `agentdojo` · `2024-06` (J.4.6) |
| `agent-security-tools-survey` · `agentharm` | supported | 6 / 6 logs, 1,056 samples through `agentprov import --verify-against-pin --release`, same checks (`docs/reports/inspect/import-cli-agentharm.json`); band `inspect_ai 0.3.247.dev69` only |
| `agentdojo` · `head` | supported | 36,679 / 36,679 `089ed468` logs through `agentprov import --verify-against-pin --release` (24,914 `v0.k11`, 11,764 `v1.k14`, 1 `v1.k14.incomplete`; 207 outcome-only), same checks, every `observed` count of the profile reproduced; refreshed on the integrated code, with the D.6.16 history fields (`docs/reports/agentdojo/import-cli-head.json`, `census-head.json`; D.6.12 item 20) |
| `rope` · `head` | supported | 10,791 / 10,791 `64495e16` logs (10,789 agent executions, 2 outcome-only), same checks, census reproduced; Q.8 corrected-security counts 198 / 260 / 220 and the AutoDojo slice (`docs/reports/rope/import-cli-rope.json`, `rope-q8.json`; D.6.13) |
| `autodojo` · `rope-slice` | partial (`via = "rope"`) | served by `rope`: the 2,847 slice logs are sealed in the ROPE import above; partial because one of AutoDojo's ten defences and three models are released (D.6.13) |
| `agentdyn` · `a` | supported | 38,281 variant-A logs of the 47,723 in `runs/` (`5353cf76`), same checks; 9,442 files of variants B and C `select.dialect_planned`, 949 DRIFT copies `select.owned_elsewhere`; SEM fails closed on the three new suites (`docs/reports/agentdyn/`; D.6.14) |
| `mandate-agentdojo-eval` · `head` | supported | 396 / 396 `fa62a977` logs, same checks, census and the investigation's outcome table reproduced (`docs/reports/mandate/import-cli-mandate.json`; D.6.15) |
| `agent-security-tools-survey` · `agentdojo-runs` | supported | 3,243 / 3,243 `89c4db2c` logs, same checks, census and aggregates reproduced (`docs/reports/survey/import-cli-agentdojo-runs.json`; D.6.15) |
| `foobench` · `fixture` | — | self-authored toy format (D.12); no support claim |

**Live parts (gated live value; D-720, 2026-10-22).** `agentdojo` · `live`, `autodojo` · `live` and `agentdyn` · `live`
are `partial`: the scripted live gate of rule 1 passes, and real-model runs are admitted only for the subset their
caveat declares. That subset is local model servers with consent, and API endpoints with consent and both caps
(D-721, D-725, D-726; MN N.2.1b item 3a), with the `native` element, and with the defences the live profile allows
(none for `autodojo` and `agentdyn`; D-670, D-677). The caveat keeps rule 3's
"fake-client tested in v0.1; no real-model run" until the user approves a real-model pilot of the part (D-722). The
user approved the 2026-10-22 pilot (D-729; its AgentDyn cells, L-DY, ran on the user's advance yes once the
`agentdyn-5353cf76` environment was registered), so the caveats of all three parts record it instead, each naming
only the endpoint classes it ran. Evidence of the scripted gate and of the pilot:

| source_id · part | Live (gated) | Evidence |
|---|---|---|
| `agentdojo` · `live` | partial | `docs/reports/backends/agentdojo-env.md` (registered `agentdojo-79922295`, 4-cell scripted run, validate and recompute with 0 differences); `tests/integration/test_run_live_agentdojo.py`; local CI job `live-run` (D-462, D-723); pilot 2026-10-22 (`docs/reports/live-pilot/`): local `qwen3-8b-abliterated-v2` 8 cells, OpenRouter `openai/gpt-4o-mini` 4 cells, Anthropic `claude-haiku-5-5` 4 cells, each corpus `validate --strict`, `recompute --dry-run` 0 differences, `verify --level chain` |
| `autodojo` · `live` | partial | `docs/reports/live/autodojo-phase9.md`; phase 9b (`docs/reports/phase9b/`); `tests/integration/test_run_live_autodojo.py`; local CI job `backend-autodojo`; pilot 2026-10-22 (`docs/reports/live-pilot/`): local `qwen3-8b-abliterated-v2` 2 cells, same checks |
| `agentdyn` · `live` | partial | `docs/reports/agentdyn-backend/` (scripted S1–S4, T1–T6); D.11.10; pilot 2026-10-22 (`docs/reports/live-pilot/`): local `qwen3-8b-abliterated-v2` 2 cells (`shopping` `user_task_0`, benign and `important_instructions`/`injection_task_0`) under `sandbox-exec`, same checks |

Live corpora cannot be sealed in this build (`package.unsupported.live`), so no live part supports a "Live Capture"
claim (U-18; D-724).

The phase-10d AgentDojo-format sources (§D.6.17) are registered `planned` until their full imports are recorded. So are
the phase-10f sources `seagent-agentdojo` (§D.6.18) and `whistlebench` (§D.9.7). So is the phase-10k source `credleak-p15b` (§D.19).
So are the phase-10n sources `atia-benchmark` (§D.9.10) and `autogen-guard-placement` (§D.22).

Every other row of the table above is not registered in this build: `agentprov import` refuses it (exit 5, "not
registered in this build") until its importer and gates land.

**`agentharm` · `live` (gated live value `partial`; D-741, 2026-10-23).** The scripted live gate of rule 1 passes
(`tests/integration/test_run_live_inspect.py`: the `inspect-agentharm` backend's scripted run, a native-log session
validated and recomputed with 0 differences; D-663, D-666). Real-model runs are admitted only for the subset the
caveat declares: OpenAI-chat endpoints, a local server with consent or an API endpoint with consent and both caps
(D-721, D-725, D-726), and under the caps the D-740 cell bound. Since D-744 the caveat records the user-approved D-667
probe in place of rule 3's "fake-client tested in v0.1; no real-model run" (D-722): API endpoint class, OpenRouter
`openai/gpt-4o-mini` as agent and both judges, 4 samples of the harmful split, 4 of 4 conclusive
(`docs/reports/inspect-harness/probe-d667.md`). Live corpora cannot be sealed in this build (U-18), and the corpus is
restricted-use and private (D-668).

The first revision's D.8 "partial" challenge text is deleted; its disposition is recorded in §D.8 (rejected in part,
A6, R-28).

### D.3.4 Licence policy enforcement

Two vocabularies are mapped explicitly (RESOLUTIONS §3.8, R-14):

| Registry licence policy | Corpus `raw_policy` | Packager behaviour |
|---|---|---|
| `include` | `include` | Raw artefacts are copied into the corpus `raw/objects/` together with the licence texts and attributions. |
| `reference` | `reference` | Only `raw/REFERENCES.json` entries are written: digest plus the pinned origin from the in-package profile. No command string or fetch instruction is stored; help text is generated at display time (R-43). |
| `nc_partition` | `include`, inside a separately licensed `-nc` corpus | The artefacts and every AER, SEM and PROV file derived from them go to the `-nc` corpus. They MUST NOT be relicensed [sources/multiturn-agent-attack.md §9]. STAC is planned, so no NC corpus is built in v0.1 (AD-10 row 22). |
| `forbidden` | `withhold` | The build refuses to package the bytes unless an explicit permission record is supplied; the withholding is recorded in `WITHHELD.json`. |

Further rules.
- A use clause (e.g. AgentHarm's "MIT License with an additional clause") is carried in `licences.restrictions`.
  AgentHarm executions form a **separate** corpus, `ast-survey-agentharm` (U-05).
- Deposits are grouped by the key `(spdx, sorted restrictions)`; the builder refuses to mix licence classes in one
  deposit (AD-20).
- Every datasheet renders `licences.raw[].basis` verbatim (for example AgentDyn "MIT as declared; not legally
  settled", Mandate "publisher unverified").
- `unassessed` items are rendered verbatim into `DATASHEET.md`.
- The policy in force is the one declared by the **owner** of the artefact, even when the bytes are byte-identical to
  another source's bytes. The owner is declared once, in the owner profile's `[lineage]` (R-45).

### D.3.5 `agentprov info`

`agentprov info` (alias `sources`) renders the registry through `agentprov.adapters.registry.render`. It loads no
adapter family and imports no benchmark. Backend availability is read from the built environment's marker file
`$AGENTPROV_HOME/envs/<backend>-<commit8>/AGENTPROV_ENV.json` (§D.11.2); nothing is imported to probe it. The text is
generated from the registry, per part and with caveats; it is never hand-written. [R-15]

Illustrative excerpt (the real output is generated; values are the v0.1 targets of §D.3.3):

```
$ agentprov info
AgentPROV 0.1.0  aer/0.1  sem/0.1  capture/0.1  agentprov-prov/0.1  registry 2026-10-07 (sha256 3f…)

SOURCE · PART                               ROLE            IMPORT        LIVE                    POLICY
agentdojo · head                            source          supported     —                       include
agentdojo · 2024-06                         source          supported     —                       include
agentdojo · history                         source          planned       —                       include
agentdojo · live                            source          —             supported* [env ok]     include
adprov-v1 · release                         source          supported     —                       include
adprov-v1 · converted-legacy                compat_oracle   —             —                       (HL)
agentdyn · a                                source          supported     planned                 include
agentdyn · b                                source          partial†      —                       include
autodojo · live                             source          —             supported* [no env]     include
agent-security-tools-survey · agentharm     source          supported‡    planned                 include (restricted)
stac                                        source          planned       planned                 nc_partition
ciaware-bench · hf-gated                    source          planned       planned                 reference
…
* target; gated `partial` (D-720) with the pilot record (D-722)   † see `agentprov info --source agentdyn`
‡ Inspect band 0.3.247.dev69 only; logs of other producers are `select.dialect_planned`
```

Rules:
1. Row order is registry order; one row per part. Columns are fixed. `--format json` prints the registry as JCS JSON
   plus each profile's `{id, version, sha256}` and each catalogue's `{id, version}`, for machine use and for the
   datasheet. `info --matrix` and `info --must-not-claim` render the matrix document and the I.4 list (§3.7).
2. `agentprov info --source <id>` additionally prints:
   - pins (role, commit or DOI, date);
   - layout and register codes;
   - identity rules;
   - quirks (id → rule ids → observed counts);
   - lineage and overlap (from the owner profile's `[lineage]`);
   - licence policy, restrictions, basis and attribution;
   - evidence report references.
3. Only registry and profile data are printed. Profiles are trusted package data, but every string field is still
   passed through `escape_untrusted` (G.8.2).
4. Exit code 0. An invalid registry or profile prints the `ProfileError` and exits 70 (internal error: package data
   is wrong). This is the startup self-check every CLI command runs.

---

## D.4 Source-profile format (TOML)

### D.4.1 Location, loading and schema

- Profiles live at `src/agentprov/adapters/<family>/profiles/<profile-id>.profile.toml`. They are loaded with
  `tomllib` through `importlib.resources`, from package resources only.
- The schema is closed. Unknown tables or keys raise `ProfileError`. The generic part (`[profile] [source] [licence]
  [lineage] [import]`) is validated by `agentprov.adapters.profiles`; the `[family.<ns>]` part by the closed schema
  the family ships (`adapters/<family>/family.schema.json`). Neither is a published corpus schema in v0.1: only
  `aer-0.1`, `capture-0.1` and `corpus-0.1` are published (AD-10 row 13). The loader is differentially tested against
  both schemas.
- The profile's `{id, version, sha256}` MUST be recorded in every AER header it influenced (`execution.profile`,
  AD-03 R-3).
- `version` is an integer, monotonic, bumped on **any** byte change (AD-18). A changed sha256 with an unchanged
  version fails the self-test. The patch/minor/major meaning of a change is recorded in the corpus `CHANGES.toml`, not
  in the number.
- Selectors (`applies`) use `fnmatch` globs over named path components or variant ids. Lists are ORed; keys are
  ANDed.

### D.4.2 Top-level tables

The generic schema is `[profile] [source] [licence] [lineage] [import]`. Everything that is specific to a family
(identity resolution, benchmark and harness facts, outcome fields, quirks, live pins) lives under `[family.<ns>]`.
There is no `[status]` table (the registry is the only status store) and no `[[assumption]]` table (assumptions live
on catalogue entries, §D.5.2). [R-38, R-45, AD-05, AD-15]

| Table | Required | Content |
|---|---|---|
| `[profile]` | yes | `id`, `version` (int), `format = "agentprov-source-profile/0.1"`, `source_id` (registry id), `family`, `parts` (registry parts this profile maps), `title`, `evidence` (list of report refs) |
| `[source]` | yes | `canonical_repo`, `paper`, `concept_doi?`, `package{}`, `[[source.pins]]` (`role`, `part?`, `kind` git/zenodo/hf, commit or DOI, date, tree, expected_files, expected_bytes, `primary` (bool), note). Pins are the only origins `agentprov fetch` and `REFERENCES.json` resolution accept (R-43) |
| `[licence]` | yes | mirrors `LicencePolicy` (`spdx`, `holders`, `data_licence`, `policy`, `restrictions`, `basis`, `attribution`, `unassessed`), per pin role if it differs (`[[licence.overrides]]`) |
| `[lineage]` | yes | The **owner's** edges, declared once: `built_on`, `vendored`, `duplicates[]` (`{of, part?, path, relation = "byte_identical"/"replicate"/"mirror"/"derived_conversion", owner}`), `cited_by[]`, `content_dedup = "never"` |
| `[import]` | if import | `dialect`, `mapper`, `variants[]`, `include[]`, `exclude[]` (each with a register `code`, and `owner` for `select.owned_elsewhere`), `layout`, `layout_depth`, `path_must_agree[]`, `context_artefacts[]` (role `supporting`), `auxiliary[]` (second-file patterns joined into one execution unit), `opt_in_parts[]`, `blobs[]` (files holding `$blob` payloads, stored first and referenced by digest; D-203), `nested[]` (archives inside an archive input: `{id, pattern, under?, note?}` with raise-only `max_member_bytes`, `max_ratio`, `max_depth` under the fixed ceilings of `ingest/limits.py`; D-382) |
| `[family.<ns>]` | as the family schema requires | For `agentdojo`: `[family.agentdojo.identity]` (`model_from`, `pipeline_name_policy`, `defence_suffixes[]`, `[[family.agentdojo.identity.dir]]` rows or `table = "<tables/…toml>"`, `id_style_corroboration{}`), `[family.agentdojo.benchmark]` (`benchmark`, `suites{suite → benchmark}`, `version_field`, `version_label_semantics`, `dos_attacks[]`, `semantics_profile {id, version}`), `[family.agentdojo.harness]` (`code_identity` = `pinned`/`range`/`unpinned`, `retry_semantics` (namespaced: `agentdojo.final_content_none_max3`, `agentdyn.last_assistant_content_none_max3`, `agentdojo.single_pass`), `tool_output_format`, `system_prompt_variants[]`), `[family.agentdojo.outcomes]` (`judgements[]` = `{name, field}`; polarity is SEM's, in `agentdojo.suites`), `[[family.agentdojo.quirk]]` (`id` namespaced `agentdojo.<quirk>` from §D.6.4, `applies{}`, `rules[]`, `params{}`, `observed{}`, `evidence`), `[family.agentdojo.live]` (live profiles only: `backend`, `project`, `pins`, `llm_element_default`, `refuse[]`, `instrumentation_extra[]`). For `inspect`: `[family.inspect]` (`producer_band{}`, `span_roles{}`, `members[]`, `[[family.inspect.quirk]]`) |

### D.4.3 Full worked profile: `agentdojo-upstream`

`source_id = "agentdojo"`; profile and corpus id `agentdojo-upstream` (R-11). It maps two registry parts, the
`head` snapshot (@`089ed468`) and the `2024-06` snapshot (@`c274885`, 18,241 logs including 7 Mixtral). The two
snapshots are imported into one corpus and are never conflated: each AER carries its own origin commit.

```toml
# src/agentprov/adapters/agentdojo/profiles/agentdojo-upstream.profile.toml
[profile]
id = "agentdojo-upstream"
version = 1
format = "agentprov-source-profile/0.1"
source_id = "agentdojo"
family = "agentdojo"
parts = ["head", "2024-06"]
title = "AgentDojo upstream native TraceLogger run logs (ethz-spylab/agentdojo runs/)"
evidence = ["sources/agentdojo.md", "verify/agentdojo.md", "audit/legacy_replay.md §2", "landscape/trace_formats.md §3.10"]

[source]
canonical_repo = "https://github.com/ethz-spylab/agentdojo"
paper = "arXiv:2406.13352"
concept_doi = "10.5281/zenodo.12528188"            # GitHub–Zenodo software archives, 36 versions, MIT
package = { name = "agentdojo", pypi_latest = "0.1.35", version_identifies_code = false }

[[source.pins]]
role = "head"
part = "head"
primary = true
kind = "git"
commit = "089ed468cf3ed0322acc66b0211f26d9d90dbf60"
date = "2026-06-02"
tree = "runs/"
expected_files = 36679
expected_bytes = 426293413

[[source.pins]]
role = "release_tag_v0_1_35"
kind = "git"
commit = "a75aba7631d3ca5fb7ab938965c97ead2f9ff84b"
date = "2025-10-27"
note = "runs/ subtree identical to head; code of the PyPI 0.1.35 wheel"

[[source.pins]]
role = "2024-06"
part = "2024-06"
primary = true
kind = "git"
commit = "c274885610efaaafec38b6d3eb07152ba7ff3f94"
date = "2024-06-05"
tree = "runs/"
expected_files = 18241
note = "18,241 logs: all 18,234 AgentDojo-PROV legacy blobs plus 7 Mixtral logs; the baseline copy's exact source commit is undecidable (also contained at 15de4430…, ae8d2c01…)"

[[source.pins]]
role = "pre_travel_rerun"
kind = "git"
commit = "15de44300d058039298223eff2a185997ce3fe56"
date = "2024-07-15"
note = "last state before the 2024-07-16/17 travel and Llama re-runs; the 4,052 superseded executions are retrievable here"

[[source.pins]]
role = "zenodo_head"
kind = "zenodo"
doi = "10.5281/zenodo.17458493"
member_prefix = "ethz-spylab-agentdojo-a75aba7/runs/"
note = "v0.1.35 archive; runs/ equals head; alternative origin"

[[source.pins]]
role = "zenodo_2024_06"
kind = "zenodo"
doi = "10.5281/zenodo.12742856"
note = "v0.1.8 archive; runs/ subtree d1c9178a… contains all 18,234 baseline blobs (v0.1.7: 10.5281/zenodo.12528189, 10.5281/zenodo.12528333); alternative origin"

[licence]
spdx = "MIT"
holders = ["Edoardo Debenedetti", "Jie Zhang", "Mislav Balunovic", "Luca Beurer-Kellner", "Marc Fischer", "Florian Tramèr"]
data_licence = "none"                               # no separate data licence; repository MIT covers runs/
policy = "include"
basis = "MIT by repository; data licence not separately stated"   # U-03 default wording
attribution = ["LICENSE (MIT, (c) 2024 Debenedetti et al.)", "CITATION.bib: arXiv:2406.13352"]
unassessed = ["model-provider terms on redistributing model outputs", "Llama 3.3 / Meta-SecAlign output licences"]

[lineage]                                           # the owner's edges, declared once
built_on = []
vendored = []
duplicates = [
  { of = "agentdojo-inspect", path = "runs/**", relation = "mirror", owner = "agentdojo" },
  { of = "adprov-v1", part = "converted-legacy", path = "corpus-og-agentdojo-runs-prov/**", relation = "derived_conversion", owner = "agentdojo" },
  { of = "agent-security-tools-survey", part = "zenodo-bundled-runs", path = "zenodo:codesafe/agentdojo/agentdojo/runs/**", relation = "mirror", owner = "agentdojo" },
]
content_dedup = "never"                             # dedup by source_key (bytes) and ownership only

[import]
dialect = "agentdojo.tracelogger"
mapper = "agentdojo.tracelogger"
variants = ["v0.k11", "v1.k14", "v1.k14.incomplete"]
include = ["runs/**/*.json"]
exclude = [
  { glob = "**/.DS_Store", code = "select.not_execution_artefact" },
  { glob = "**/._*", code = "select.not_execution_artefact" },
]
layout = "runs/{pipeline_dir}/{suite}/{task_dir}/{attack_dir}/{file}.json"
layout_depth = 5
path_must_agree = ["suite_name", "user_task_id", "attack_type", "injection_task_id"]  # attack_dir "none" <-> null
opt_in_parts = [
  { part = "history", note = "7,867 runs/ versions (path, blob; 7,114 distinct blobs) held by neither pin in the head pin's history; per-blob commit provenance; never mixed silently with head. Of the 11,173 distinct blobs absent from head, the other 4,059 are the 2024-06 part's (D-207)" },
]

[family.agentdojo.identity]
model_from = "pipeline_dir"                          # A-7; pipeline_name kept verbatim in ext.agentdojo.pipeline_name
pipeline_name_policy = "verbatim_unreliable_when_differs"
defence_suffixes = ["repeat_user_prompt", "spotlighting_with_delimiting", "tool_filter", "transformers_pi_detector"]
on_dir_name_mismatch = "issue:agentdojo.pipeline_name_mismatch"

[[family.agentdojo.identity.dir]]
pipeline_dir = "Meta-SecAlign-70B*"
pipeline_name = ["local", "local-repeat_user_prompt"]
model = "facebook/Meta-SecAlign-70B"
rule = "agentdojo.local_dir_model_identity@1"        # class I (catalogue)
basis = "directory name; HF id claimed in upstream PR #96/#97"

[[family.agentdojo.identity.dir]]
pipeline_dir = "meta-llama_Llama-3.3-70B-Instruct*"
pipeline_name = ["local", "local-repeat_user_prompt"]
model = "meta-llama/Llama-3.3-70B-Instruct"
rule = "agentdojo.local_dir_model_identity@1"
basis = "directory name; HF id claimed in upstream PR #96/#97"

[family.agentdojo.identity.id_style_corroboration]
"call_*" = "openai"
"toolu_*" = "anthropic"
"tool_call_??????????" = "client_generated_random"   # Llama-3-70b prompting (ast_utils random.choices)

[family.agentdojo.benchmark]
benchmark = "agentdojo"
suites = { workspace = "agentdojo", travel = "agentdojo", banking = "agentdojo", slack = "agentdojo" }
version_field = "benchmark_version"                 # v1.k14 only; the verbatim label goes on the bench actor's version
version_label_semantics = "suite_version"
version_when_absent = { rule = "agentdojo.benchmark_era_from_commit@1" }   # class I
dos_attacks = ["dos", "captcha_dos", "felony_dos", "offensive_email_dos", "swearwords_dos"]
semantics_profile = { id = "agentdojo.suites", version = 1 }

[family.agentdojo.harness]
code_identity = "unpinned"                          # no commit in logs; introducing commit is an upper bound
retry_semantics = "agentdojo.final_content_none_max3"
tool_output_format = "yaml"
system_prompt_variants = [
  { label = "agentdojo_default", source = "ethz-spylab/agentdojo@a75aba76:src/agentdojo/data/system_messages.yaml", sha256 = "<computed at implementation; test-pinned>" },
]

[[family.agentdojo.quirk]]
id = "agentdojo.benign_security_constant"
applies = { attack_dir = ["none"] }
rules = ["agentdojo.benign_security_constant@1"]
observed = { files = 3560 }

[[family.agentdojo.quirk]]
id = "agentdojo.dos_security_not_utility"
applies = { attack_dir = ["dos", "captcha_dos", "felony_dos", "offensive_email_dos", "swearwords_dos"] }
rules = ["agentdojo.dos_security_rule@1", "agentdojo.dos_placeholder_injection_task@1"]
observed = { files = 485 }

[[family.agentdojo.quirk]]
id = "agentdojo.silent_rerun_last_pass_only"
applies = {}
rules = ["agentdojo.log_holds_last_pass@1", "agentdojo.null_final_implies_three_passes@1"]
params = { trigger = "final_assistant_content_is_null", max_passes = 3 }
observed = { null_final_logs = 82 }

[[family.agentdojo.quirk]]
id = "agentdojo.injection_task_as_user_task_prepass"
applies = { task_dir = ["injection_task_*"], attack_dir = ["none"] }
rules = ["agentdojo.injection_task_as_user_task@1"]
observed = { files = 804 }

[[family.agentdojo.quirk]]
id = "agentdojo.empty_messages_with_outcome"
applies = { pipeline_dir = ["claude-3-opus-20240229"] }
rules = ["agentdojo.no_execution_observed@1"]       # unit "outcome_only"
observed = { files = 207 }

[[family.agentdojo.quirk]]
id = "agentdojo.run_error_imposes_outcome"
applies = {}
rules = ["agentdojo.run_error_imposed_outcome@1"]
params = { utility = false, security = true }
observed = { files = 105 }

[[family.agentdojo.quirk]]
id = "agentdojo.incomplete_run"
applies = { variant = ["v1.k14.incomplete"] }
rules = ["agentdojo.incomplete_run@1"]
observed = { files = 1 }

[[family.agentdojo.quirk]]
id = "agentdojo.provider_call_id_anomalies"
applies = {}
rules = ["agentdojo.call_id_unique_match@1", "agentdojo.positional_match@1"]
params = { empty_string = ["gemini-*"], key_absent = ["command-r*"], null = ["Meta-SecAlign-70B*", "meta-llama_Llama-3.3-70B-Instruct*"], client_random = ["meta-llama_Llama-3-70b-chat-hf"], duplicates_possible = ["gpt-*"] }
observed = { gemini_logs_with_colliding_empty_ids = 2725, gpt_logs_with_duplicate_ids = 213 }

[[family.agentdojo.quirk]]
id = "agentdojo.args_mutated_in_place"
applies = { variant = ["v1.k14"] }
rules = ["agentdojo.args_are_effective@1"]

[[family.agentdojo.quirk]]
id = "agentdojo.unexecuted_trailing_calls"
applies = {}
rules = ["agentdojo.unexecuted_trailing_calls@1"]
observed = { calls = 815 }

[[family.agentdojo.quirk]]
id = "agentdojo.pi_detector_redaction"
applies = { pipeline_dir = ["*-transformers_pi_detector"] }
rules = ["agentdojo.pi_detector_sentinel@1"]
params = { sentinel = "<Data omitted because a prompt injection was detected>" }
observed = { logs = 622 }

[[family.agentdojo.quirk]]
id = "agentdojo.tool_filter_aux_llm"
applies = { pipeline_dir = ["*-tool_filter"] }
rules = ["agentdojo.tool_filter_aux_message@1"]

[[family.agentdojo.quirk]]
id = "agentdojo.repeat_user_prompt_reinsertion"
applies = { pipeline_dir = ["*-repeat_user_prompt"] }
rules = ["agentdojo.repeat_user_prompt_copy@1"]

[[family.agentdojo.quirk]]
id = "agentdojo.spotlighting_delimiters"
applies = { pipeline_dir = ["*-spotlighting_with_delimiting"] }
rules = ["agentdojo.spotlighting_content@1"]

[[family.agentdojo.quirk]]
id = "agentdojo.local_model_raw_completion"
applies = { pipeline_dir = ["Meta-SecAlign-70B*", "meta-llama_Llama-3.3-70B-Instruct*"] }
rules = ["agentdojo.local_model_tag_count@1"]
observed = { turns_more_tags_than_calls = 2996, turns_tags_no_calls = 1192 }

[[family.agentdojo.quirk]]
id = "agentdojo.placeholder_args_never_injection_evidence"
applies = {}
rules = ["agentdojo.placeholder_args_ground_truth_only@1"]
observed = { present_and_null = 61461 }

[[family.agentdojo.quirk]]
id = "agentdojo.generation_mixing_per_file"
applies = {}
rules = ["agentdojo.benchmark_era_from_commit@1", "agentdojo.committed_no_later_than@1"]
params = { infer_per = "file" }                     # never per pipeline directory [verify/agentdojo.md §5.3]

[family.agentdojo.outcomes]
judgements = [
  { name = "utility", field = "utility" },
  { name = "security", field = "security" },        # polarity (injection task succeeded) is SEM's: agentdojo.suites
]
origin_rules = [
  "agentdojo.run_error_imposed_outcome@1",
  "agentdojo.benign_security_constant@1",
  "agentdojo.dos_security_rule@1",
  "agentdojo.checker_outcome@1",
]
```

The live pins (the PyPI 0.1.35 wheel digest `364bea42…`, recorded in [verify/mandate-agentdojo-eval.md, header:
scripts and downloads]) are in the separate profile `agentdojo-live` (§D.4.4), not in this import profile. The
`instrumentation` list for live mode is given in §D.10.7.

### D.4.4 Short profiles

The following show only the keys that differ from the worked profile above. **Notation (not literal TOML):** to save
space, a line `[table] k = v  k2 = v2` abbreviates a table whose keys sit on separate lines, and `[[x]] k = v …`
abbreviates one array-of-tables entry; `[fam.…]` abbreviates `[family.agentdojo.…]` and quirk ids are written without
their `agentdojo.` prefix. The shipped files are complete, standard TOML with every required key, and they are
validated by the closed schemas of §D.4.1. Caveats and statuses are not profile data; they are in §D.3.3.

**`agentdojo-live`** (source `agentdojo`, part `live`) [audit/capture.md; verify/mandate-agentdojo-eval.md]

```text
[profile]  { id = "agentdojo-live", version = 1, source_id = "agentdojo", family = "agentdojo", parts = ["live"] }
[licence]  policy = "include"  basis = "the user's own runs"  unassessed = ["model-provider terms on redistributing model outputs"]
[import]   dialect = "agentprov.capture"  variants = ["0.1"]  mapper = "agentdojo.capture"
           native = { dialect = "agentdojo.tracelogger", variants = ["v1.k14"], mapper = "agentdojo.tracelogger" }   # live-versus-native check
[fam.live] backend = "agentdojo"  project = "backends/agentdojo"  llm_element_default = "native"
           pins = { distribution = "agentdojo", version = "0.1.35", wheel_sha256 = "364bea4219716b716bf639f504d195943f7f6a5535d312ca41d7098704a2affd" }
           refuse = ["defense!=null", "tool_output_format not in [null, 'yaml']"]
```

**`rope`** [sources/rope.md; verify/rope.md]

```text
[profile]  { id = "rope", version = 1, source_id = "rope", family = "agentdojo" }
[[source.pins]] role = "head"  primary = true  kind = "git"  commit = "64495e16e640d687e06e6b1b6cee6dccc5b9b7cb"  date = "2026-08-31"  tree = "runs/"  expected_files = 10792
[licence] spdx = "MIT"  holders = ["Xinhang Ma","Chaowei Xiao","William Yeoh","Ning Zhang","Yevgeniy Vorobeychik"]  policy = "include"
           attribution = ["arXiv:2608.27496", "AutoDojo payloads: arXiv:2606.15057", "long-horizon payloads: AgentLAB arXiv:2602.16901"]
[lineage]  built_on = ["autodojo (vendored ≈ bf2e4cb3..abbcbd8d)", "agentdyn suites (5353cf76)"]
           duplicates = [{ of = "ext:agentlab", path = "agentlab/res/**", relation = "byte_identical", owner = "ext:agentlab" }]   # EXTERNAL_OWNERS
           cited_by = ["AutoDojo arXiv:2606.15057v3 Tables 5,6,8,9 (raw security, micro-avg)", "ROPE arXiv:2608.27496v1 Tables 2,14 (effect-corrected, macro-avg)"]
[import]   variants = ["v1.k14", "v1.k14.incomplete"]
           include = ["runs/**/*.json"]
           exclude = [{ glob = "runs/lh_cells.json", code = "select.not_execution_artefact" },
                      { glob = "agentlab/**", code = "select.owned_elsewhere", owner = "ext:agentlab" },
                      { glob = "autodojo/**", code = "select.not_execution_artefact" }]
           layout = "runs/{tree?}/{model_dir}/{suite}/{task_dir}/{attack_dir}/{file}.json"   # tree ∈ {ablation/<policy>, router/<router>[-clamp]}
           context_artefacts = ["runs/lh_cells.json", "runs/*.py", "src/rope/scopes/**", "autodojo/variant_generation/variants/*/openai/gpt-4o-mini/routed/injections.json"]
[fam.identity] model_from = "model_dir"   pipeline_name_policy = "config_tag_never_model"
           id_style_corroboration = { "call_*" = "openai_via_openrouter", "chatcmpl-tool-*" = "vllm", "tool_*" = "gemini" }
           attack_dir_alias = { agentlab_longhorizon = "long_horizon" }
[fam.benchmark] suites = { banking = "agentdojo", slack = "agentdojo", travel = "agentdojo", github = "agentdyn", shopping = "agentdyn", dailylife = "agentdyn" }
            version_label_semantics = "suite_version_for_agentdojo_suites_only"
[fam.harness]  code_identity = "unpinned"   # logs come from unreleased iter2/iter4/final-opus states [sources/rope.md §4.3]
           retry_semantics = "agentdojo.final_content_none_max3"
           system_prompt_variants = [{ label = "auto_complete_line", note = "AgentDojo default + 'Complete all tasks automatically without requesting user confirmation.'; not producible by released autodojo/ [verify/rope.md §3]" }]
[[fam.quirk]] id = "rope_guard_denial"  rules = ["rope.denial_error_pattern@1", "rope.denial_query_echo_variant@1"]
          params = { regex = "^The tool '[^']*' is not allowed\\.\\. Please try other tools", none_variant_suffix = "user task: None." }
          observed = { denials = 12657, none_variant = 9424, query_variant = 3233 }
[[fam.quirk]] id = "silent_rerun_last_pass_only"  observed = { null_final_logs = 322 }
[[fam.quirk]] id = "pipeline_name_not_identity"  rules = ["rope.model_dir_identity@1"]  observed = { qwen_autodojo_mislabelled = 949 }
[[fam.quirk]] id = "empty_messages_without_outcome"  observed = { files = 2 }      # unit "outcome_only"
[[fam.quirk]] id = "unexecuted_trailing_calls"  observed = { logs = 675, calls = 753 }
[[fam.quirk]] id = "provider_call_id_anomalies"  params = { null = ["gemini-2.5-flash/**"] }  observed = { null_ids = 8707 }
[[fam.quirk]] id = "benign_security_constant"  observed = { files = 748 }
[[fam.quirk]] id = "rope_effect_correction"  rules = ["rope.security_correction@1"]  observed = { slack_it5 = 198, dailylife_it7 = 260, github_it1 = 220 }
```

ROPE's effect-based security corrections (`runs/corrections.py`, dispatching to `slack_it5.py`, `dailylife_it7.py`
and `github_it1.py`) are recomputations **released by the source** (as code). Per C.3.10 they are AER `judgement`s
beside the recorded value, never in its place: `origin: "recomputed"`, `by: "source"`, `revises` = the recorded
`security` judgement, rule `rope.security_correction@1` (D; a port of the three released task rules, tested
against the observed counts above) [sources/rope.md §3.6; verify/autodojo.md §3.1]. AgentPROV's own re-scorings are
not AER (replay is deferred, AD-10). The shipped profile departs from this sketch where the pinned data requires it
(whole-commit pin, an arm-directory layout for the ablation and router trees, two added quirk ids): §D.6.13.

**`autodojo`** (two profiles). Import is served by `rope`. Its profile `autodojo-via-rope` carries no `[import]`
table, only `via = "rope"`, plus an `[family.agentdojo.attack_provenance]` table that the ROPE mapper consults for
`attack_dir = "autodojo"` cells:

```toml
[family.agentdojo.attack_provenance]
attack = "autodojo"
cache_repo = "https://github.com/xhOwenMa/AutoDojo"
cache_commit = "aa458794b7eb7f082e94daeac4c0f55bfc0c90cc"
rope_caches = "rope@64495e16:autodojo/variant_generation/variants/{github,shopping,dailylife}/openai/gpt-4o-mini/routed/injections.json"
link_rule = "autodojo.payload_cache_link@1"   # class I: exact variant-0 match, stored with its ambiguity set (1, 8, 40 or 50 cells)
```

The live profile `autodojo-live` is shown in §D.11.4.

**`agentdyn`** [sources/agentdyn.md; verify/agentdyn.md]

```text
[[source.pins]] role = "head"  primary = true  kind = "git"  commit = "5353cf7615b135cace8d07c8f12dac53a16b6db3"  date = "2026-05-19"  expected_files = 47723
[licence]  spdx = "MIT"  holders = ["(AgentDojo authors' notice)"]  attribution = ["arXiv:2602.03117"]  policy = "include"
           basis = "MIT as declared; not legally settled"
[lineage]  built_on = ["agentdojo v0.1.35 (a75aba7/5cea589)"]
           duplicates = [{ of = "drift", path = "src/agentdojo/defenses/drift/runs/**", relation = "byte_identical", owner = "drift" }]
           # variant C = re-keyed copies of AgentDyn's own history blobs runs/DRIFT/** (E11, owner agentdyn; R-62)
[import]   variants = ["v1.k14", "v1.k14.incomplete", "v0.k11", "drift.k18.messages"]
           include = ["runs/**/*.json"]
           exclude = [{ glob = "src/**", code = "select.owned_elsewhere", owner = "drift" }]
           opt_in_parts = [{ part = "history", note = "16,795 superseded blobs incl. Claude Haiku/Sonnet 4.5" }]
           variant_labels = { "v1.k14" = "a", "v0.k11" = "b", "drift.k18.messages" = "c", "drift.k18.conversations" = "d" }
[fam.identity] model_from = "pipeline_dir"  table = "tables/agentdyn_pipeline_dirs.toml"   # 76 rows: model, defence, provider, variant, producing codebase
[fam.benchmark] suites = { shopping = "agentdyn", github = "agentdyn", dailylife = "agentdyn", travel = "agentdojo" }
            version_label_semantics = "label_not_suite_version"   # suites registered under every version key
[fam.harness]  retry_semantics = "agentdyn.last_assistant_content_none_max3"
           system_prompt_variants = [{ label = "auto_complete_line" }, { label = "agentdojo_default", applies = "variant b (Progent 0.1.29)" }]
[[fam.quirk]] id = "run_error_imposes_outcome"  rules = ["agentdyn.json_decode_error_imposed@1"]  observed = { files = 5 }
[[fam.quirk]] id = "incomplete_run"  observed = { null_outcome_files = 12 }
[[fam.quirk]] id = "pi_detector_redaction"  observed = { redacted_tool_messages = 29317 }
[[fam.quirk]] id = "progent_denial"  params = { regex = "^ValidationError: The tool '[^']*' is not allowed\\.\\." }
[[fam.quirk]] id = "drift_integrated_user_error_key"  observed = { user_messages = 434 }
[[fam.quirk]] id = "camel_orphan_tool_results"  applies = { pipeline_dir = ["*-camel"] }  observed = { tool_messages = 2635, assistant_calls = 658 }
[[fam.quirk]] id = "drift_original_format"  applies = { variant = ["drift.k18.messages"] }
[[fam.quirk]] id = "provider_call_id_anomalies"  observed = { null_ids = 15306 }
```

**`drift`** [sources/drift.md; verify/drift.md]

```text
[[source.pins]] role = "head"     part = "head"     primary = true  kind = "git"  commit = "6fd3df4763fad77398c3c273c2a4fe14dd50f7ea"  date = "2026-07-16"  expected_files = 1569
[[source.pins]] role = "history"  part = "history"  kind = "git"  commit = "53dbc6c58d5d1f044f3a68636be30b060bb86d34"  date = "2026-01-31"  expected_files = 1046
[licence]  spdx = "MIT"  holders = ["Hao Li"]  policy = "include"  attribution = ["arXiv:2506.12104"]
[[licence.overrides]] pin = "history"  policy = "reference"  note = "committed before any licence statement"
[import]   variants = ["drift.k18.conversations"]
           include = ["runs/gpt-4o-mini-2024-07-18/**/*.json"]
           exclude = [{ glob = "ASB_DRIFT/**", code = "select.dialect_planned" }, { glob = "docs/**", code = "select.not_execution_artefact" }]
[fam.benchmark] suites = { banking = "agentdojo", slack = "agentdojo", travel = "agentdojo", workspace = "agentdojo", dailylife = "agentdyn", github = "agentdyn", shopping = "agentdyn" }
            version_label_semantics = "cli_default_not_suite_version"   # always "v1.2"
[fam.harness]  retry_semantics = "agentdojo.single_pass"   code_identity = "range"
[[fam.quirk]] id = "drift_tool_output_post_isolation"   rules = ["drift.tool_output_post_isolation@1"]
[[fam.quirk]] id = "drift_assistant_reserialised"       rules = ["drift.assistant_reserialised@1"]   observed = { reserialised = 7341, raw = 950 }
[[fam.quirk]] id = "drift_call_error_as_user"           rules = ["drift.call_error_user_is_validator@1"]  observed = { messages = 833 }
[[fam.quirk]] id = "drift_calls_in_text_not_executed"   rules = ["drift.calls_in_text_not_executed@1"]   observed = { final_turns_max = 311 }
[[fam.quirk]] id = "drift_no_system_no_injections"      rules = ["drift.no_system_message@1", "drift.no_injection_map@1"]
[[fam.quirk]] id = "drift_plan_fields_by_commit"        rules = ["drift.plan_fields_semantics@1"]  params = { head = "initial_plan", history = "final_plan_state" }
[[fam.quirk]] id = "provider_call_id_anomalies"         params = { seeded_random_trace_local = ["**"] }  observed = { ids_reused_across_files = 975 }
```

**`mandate-agentdojo-eval`** [sources/mandate-agentdojo-eval.md; verify/mandate-agentdojo-eval.md]

```text
[[source.pins]] role = "head"  primary = true  kind = "git"  commit = "fa62a977584962f7b4b24a40772a83345fd920d4"  date = "2026-08-17"  expected_files = 396
[source]   corpus_digest = "a8f4a9d726073fb142e7580a18f65d8985095ac23658dd1b7c4cb178eac9bd5e"   # recipe: verify/mandate §1
[licence]  spdx = "MIT"  holders = ["Mandate Labs (asserted; publisher unverified)"]  policy = "include"  basis = "MIT as declared; publisher unverified"
[import]   variants = ["v1.k14"]  include = ["runs/**/*.json"]
           context_artefacts = ["agentdojo_mandate_eval.py", "README.md", "requirements.txt", "LICENSE"]   # role supporting
[fam.identity] model_from = "pipeline_name_minus_suffix"  defence_suffix_regex = "-mandate_(envelope|scoped|intent)$"
           collision_note = "pipeline name gpt-4o-2024-05-13 equals upstream; ids are source-qualified by ex"
[fam.benchmark] suites = { banking = "agentdojo" }
[[fam.quirk]] id = "mandate_decline"  rules = ["mandate.decline_prefix@1", "mandate.allow_inferred@1"]
          params = { prefix = "MANDATE_DECLINE:", content_equals_error = true, gated = { envelope = ["send_money","schedule_transaction","update_scheduled_transaction"], intent = ["send_money","schedule_transaction","update_scheduled_transaction","update_password","update_user_info"] } }
          observed = { declines = 240 }
[[fam.quirk]] id = "injection_task_as_user_task_prepass"  observed = { files = 27 }
```

**`survey-runs`** (source `agent-security-tools-survey`, part `agentdojo-runs`; corpus `ast-survey-agentdojo`)
[sources/agent-security-tools-survey.md; verify/agent-security-tools-survey.md]

```text
[[source.pins]] role = "git"        primary = true  kind = "git"     commit = "89c4db2c949797fbb38c5bfed85dc82780ddbfe3"  date = "2026-08-28"
[[source.pins]] role = "zenodo_v1_0_0"  kind = "zenodo"  doi = "10.5281/zenodo.22135957"   # alternative origin
[[source.pins]] role = "zenodo_v1_0_1"  kind = "zenodo"  doi = "10.5281/zenodo.22140262"   # alternative origin
[source]   concept_doi = "10.5281/zenodo.22135956"   # cited together with the version actually fetched (R-62)
[licence]  spdx = "CC-BY-4.0"  holders = ["Jhih-Jhong Lin"]  policy = "include"
[lineage]  built_on = ["agentdojo@089ed468cf3ed0322acc66b0211f26d9d90dbf60 + 3 local patches (patched files only in the Zenodo zip)"]
           duplicates = [{ of = "agentdojo", path = "zenodo:codesafe/agentdojo/agentdojo/runs/**", relation = "mirror", owner = "agentdojo" }]
[import]   variants = ["v1.k14"]
           include = ["agentdojo/results/runs_*/openai-compatible/**/*.json"]
           exclude = [{ glob = "agentdojo/agentdojo/**", code = "select.owned_elsewhere", owner = "agentdojo" },
                      { glob = "asb/results/*.csv", code = "select.dialect_planned" }]
           # agentharm/results/**/*.eval is selected by profile survey-agentharm (family inspect), not by this profile
           context_artefacts = ["agentdojo/results/runs_*/console_*.log", "agentdojo/results/timing_summary.csv", "agentdojo/run_full_benchmark.sh"]
[fam.identity] model_from = "results_dir_slug"  pipeline_name_policy = "constant_not_model"   # always "openai-compatible"
           slug_to_model = { "runs_qwen3_14b" = "qwen3:14b", "runs_qwen3-coder_30b" = "qwen3-coder:30b", "runs_gpt-oss_120b" = "gpt-oss:120b" }
           rule = "survey.model_from_results_dir@1"
[[fam.quirk]] id = "run_error_imposes_outcome"  rules = ["survey.internal_server_error_patch@1"]  observed = { files = 11 }
[[fam.quirk]] id = "unexecuted_trailing_calls"  observed = { traces = 48 }
[[fam.quirk]] id = "injection_task_as_user_task_prepass"  observed = { files = 105 }
[[fam.quirk]] id = "semantic_trap_security_gloss"  note = "README glosses security as 'resisted'; code semantics apply (injection_task_succeeded)"
```

**`survey-agentharm`** (source `agent-security-tools-survey`, part `agentharm`, family `inspect`; corpus
`ast-survey-agentharm`, restricted use) [sources/agent-security-tools-survey.md §5]

```text
[profile]  { id = "survey-agentharm", version = 1, source_id = "agent-security-tools-survey", family = "inspect", parts = ["agentharm"] }
[[source.pins]] as in survey-runs (git 89c4db2c… primary; both version DOIs alternative; concept DOI cited)
[licence]  spdx = "CC-BY-4.0"  holders = ["Jhih-Jhong Lin"]  policy = "include"
           restrictions = ["AgentHarm task data: MIT License with an additional clause (use only to improve AI safety and security)"]
           basis = "CC-BY-4.0 (repository and Zenodo); AgentHarm data per HF ai-safety-institute/AgentHarm @ e23b3fe6 card"
[import]   dialect = "inspect.eval"  mapper = "inspect.eval"  variants = ["v2"]
           include = ["agentharm/results/**/*.eval"]
[family.inspect] producer_band = { inspect_ai = ["0.3.247.dev69+g53c1fa98b"] }
           members = ["header.json", "samples/*_epoch_*.json"]                 # other members: raw/members.jsonl not_selected
           span_roles = { "solver" = "agent", "scorer" = "judge" }
[[family.inspect.quirk]] id = "inspect.judge_same_model_as_agent"  note = "qwen3:14b is both agent and judge in two logs; separated by spans"
[[family.inspect.quirk]] id = "inspect.event_order_not_time_order"   rules = ["inspect.no_order_from_event_list@1"]
[[family.inspect.quirk]] id = "inspect.sample_limit"  observed = { events = 54 }   # 9 + 33 + 6 + 6
```

### D.4.5 Identity tables

Large identity resolutions are separate TOML tables referenced by `[family.agentdojo.identity] table`. They have the
same loader and a closed schema shipped by the family. Every value a table supplies is asserted under the profile's
identity rule (for AgentDyn `agentdyn.pipeline_dir_registry@1`, class I); a row-level `*_evidence` key can only
weaken a field further (through `evf`), never strengthen it. A row may omit `model` (or set it to `"not_recorded"`)
only when it names a `defence`: the model is then unresolved (`unk {"/model": "not_recorded"}`, issue
`identity_unresolved`) and the defence is still written; a source that records its defence arm but not its model never
gets a model guessed (D-92; phase-10d R4, llm-lock). A row that names a defence may add `defence_model`: the model that
defence itself runs on (Geryon's Progent policy model, read from the log set's run record). It becomes that defence
actor's `model.requested`, asserted under the same identity rule (class I), with `/model/provider` and `/model/served`
not recorded. Without it the defence's model stays not recorded (D-588). Example rows from `tables/agentdyn_pipeline_dirs.toml`
[sources/agentdyn.md §3.6, §8.3]:

```toml
[[dir]]
name = "google_gemini-2.5-flash-transformers_pi_detector"
model = "gemini-2.5-flash"
defence = "transformers_pi_detector"
provider = "google"
provider_evidence = "I"
variant = "A"
codebase = "agentdyn-fork"

[[dir]]
name = "gpt-4o-2024-08-06-progent"
model = "gpt-4o-2024-08-06"
defence = "progent"
provider = "openai"
variant = "B"
codebase = "progent-vendored-agentdojo-0.1.29"

[[dir]]
name = "meta_secalign-70B"
model = "Meta-SecAlign-70B"
defence = "none"
provider = "local"
variant = "A"
codebase = "agentdyn-fork"
pipeline_name = "local"
```

The table loader MUST check that every discovered pipeline directory has exactly one row. An unknown directory gives
the issue `identity_unresolved`; the agent actor keeps its existence class and gets `unk {"/model": "not_recorded"}`
(A-3). It never guesses.

---

## D.5 Rule-catalogue format

### D.5.1 Files, ids and versioning

This section is the owner of the catalogue format and of rule names (R-09). C.6.4 owns the reference grammar.
[R-09, AD-18, AD-14]

- **Format and location.** A catalogue is TOML in the package, at `<home>/<ns>.rules.toml`, with one namespace
  `<ns>`. `[catalogue] id = "<ns>"` (the namespace itself, never `<ns>.rules`) and an integer `version`. Homes:

  | Catalogue | Home |
  |---|---|
  | `aer` | `src/agentprov/aer/rules/aer.rules.toml` |
  | `aprov` | `src/agentprov/prov/catalogue/agentprov-prov-0.1.toml` (owner EF) |
  | `cap` | `capture/agentprov_capture/rules/cap.rules.toml` |
  | `corpus` | `src/agentprov/corpus/rules/corpus.rules.toml` (owner HL) |
  | adapter catalogues (`agentdojo`, `rope`, `agentdyn`, `drift`, `mandate`, `survey`, `autodojo`, `anthropic_messages`, `adprov`, `inspect`; `stac` planned) | `src/agentprov/adapters/<family>/rules/<ns>.rules.toml` (`anthropic_messages`, D-656: the agentdojo family, cited only by provider-`anthropic` capture sessions) |

- **Citation.** A rule is cited in AER by a scoped `RuleRef` (C.6.4): `"<ns>.<rule>@<n>"` optionally followed by
  `#<JSON Pointer>` naming the field it justifies, e.g. `"agentdojo.context_is_prefix@1#/input"`. Grammar
  `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+@[1-9][0-9]*(#/.*)?$`. The **rule id** is the reference without `#…`; PROV
  carries it as `apv:rule` and the scope as the optional `apv:rulePointer` (EF).
- **Header.** The AER header cites catalogues as a map of namespace to integer version: `rules: {"agentdojo": 1,
  "aer": 1}`. It lists every catalogue cited by any `rule` or `seal.issues[].rule` in the file.
- **Immutability.** Rules are immutable once released. Any change to a rule's statement, class, assumptions,
  verification or implementation behaviour creates `@n+1`. The old entry stays, marked `status = "superseded"`, so
  that old corpora remain recomputable. Any byte change to a catalogue bumps its integer `version` (AD-18). The
  package ships **every** released version of every catalogue; `rederive` loads them only from package resources at
  the recorded version, and an absent version is `rules.unavailable` (AD-14).
- **Corpus copy.** Each corpus carries byte-identical copies at `rules/<ns>.rules.toml`. The copy is a **record, not
  an authority**: `rederive` compares its digest (`rules.mismatch`) but never loads it (AD-14). EF maps a catalogue to
  the `prov:Plan` of the conversion.

### D.5.2 Entry schema

```toml
[catalogue]
id = "agentdojo"                                # the namespace
version = 1                                     # integer, monotonic (AD-18)
format = "agentprov-rule-catalogue/0.1"
issue_codes = ["pipeline_name_mismatch", "local_parse_drop_possible", "multi_block_tool_content",
               "unknown_top_level_key", "undeclared_quirk", "unknown_message_shape", "path_field_mismatch",
               "mixed_content_forms", "system_prompt_unrecognised"]   # raised as agentdojo.<code>
subtypes = []                                   # declared "<ns>.<name>" values for the five `other` escapes (AD-15)
types = []                                      # declared "<ns>:<name>" values for activity.type / artefact.type (AD-15)

[[rule]]
id = "agentdojo.log_holds_last_pass"            # without @n
version = 1                                     # cited as agentdojo.log_holds_last_pass@1
class = "D"                                     # the effective class, "D" or "I" only; O needs no rule
status = "active"                               # active | superseded | reserved
statement = "A TraceLogger file holds only the message list of the final pipeline pass of its cell."
premises = ["/messages"]                        # source fields (pointers) the rule reads
assumptions = ["apv:LastPassOnlyLogging"]       # core apv: terms (EF E.4.5) or adapter-declared <ns>:<Name>
verification = [
  { assumption = "apv:LastPassOnlyLogging", status = "verified",
    framework_identity = ["git:https://github.com/ethz-spylab/agentdojo@c274885610efaaafec38b6d3eb07152ba7ff3f94",
                          "git:https://github.com/ethz-spylab/agentdojo@15de44300d058039298223eff2a185997ce3fe56",
                          "git:https://github.com/ethz-spylab/agentdojo@a75aba7631d3ca5fb7ab938965c97ead2f9ff84b"],
    code_ref = "task_suite.py run_task_with_pipeline retry loop; logging.py TraceLogger.log",
    test = "tests/adapters/test_rule_catalogues.py::test_log_holds_last_pass" },
]
emits = ["scope(kind=attempt).unk./index=lost", "seal.issue:earlier_attempts_unobservable"]
code = [
  { repo = "https://github.com/ethz-spylab/agentdojo", commit = "a75aba7631d3ca5fb7ab938965c97ead2f9ff84b", path = "src/agentdojo/logging.py", lines = "265-278", note = "log() replaces self.messages, then save()" },
  { repo = "https://github.com/ethz-spylab/agentdojo", commit = "a75aba7631d3ca5fb7ab938965c97ead2f9ff84b", path = "src/agentdojo/task_suite/task_suite.py", lines = "383-394", note = "up to 3 passes on the same environment" },
  { repo = "https://github.com/ethz-spylab/agentdojo", commit = "c274885610efaaafec38b6d3eb07152ba7ff3f94", path = "src/function_calling_pi/task_suites/task_suite.py", lines = "264-279", note = "same loop in the June-2024 code" },
]
evidence = ["sources/agentdojo.md §3.1", "verify/agentdojo.md §3", "audit/legacy_replay.md §2.2"]
tests = ["tests/adapters/test_rule_catalogues.py::test_log_holds_last_pass"]
since = "0.1.0"

[[assumption]]                                  # example; adapter-declared assumptions only (core apv: terms are not redeclared)
id = "agentdojo:SingleLlmPipeline"
statement = "The pipeline contains exactly one LLM element whose kept replies are the assistant messages."
```

`apv:LastPassOnlyLogging` is in the core assumption list (EF E.4.5), together with `apv:EnvironmentCarriedOver`;
`apv:CheckerReadsFinalState` is replaced by input-stating checker assumptions, per task (AD-05).

**Static evidence classes** (AD-05). A rule's `class` is its **effective** class: the adapter emits the rule at that
class at map time, so the class is covered by the AER execution digest. A rule may have class D only if every
assumption it names is `verified` for every producing framework identity it can be applied to (a commit, a wheel
hash, or a code range whose every member is listed). A change of verification status is a new rule id or a new
catalogue version, never a derive-time reinterpretation; EF only reads the classes.

Validation (the catalogue self-test, run in CI and at startup):
1. ids are unique per `(id, version)`;
2. `class ∈ {D, I}`;
3. every `assumptions` entry is a core `apv:` assumption (EF E.4.5) or an `<ns>:<Name>` declared in this catalogue's
   `[[assumption]]` table, and has exactly one `verification` entry with `status ∈ {verified, asserted}` and, for
   `verified`, a non-empty `framework_identity`, a `code_ref` and a `test`;
4. a rule with `class = "D"` has only `verified` assumptions;
5. every `code` entry names a full 40-hex commit;
6. every `tests` node id exists in the test tree;
7. every rule cited by a mapper or profile is declared (static scan plus runtime `RuleNotDeclared`);
8. a rule whose class depends on a condition MUST be split into two rules. For example
   `agentdojo.context_is_prefix@1` (I) is used for imports, while a live capture with recorded `input_at` needs no
   rule because `model_call.input` is then O. A rule's class is never computed at run time;
9. every `other` subtype and every `activity`/`artefact` type a mapper emits is declared in `subtypes` or `types`.

The AER validator enforces EF F.1.5 item 4 on every AER: a cited rule whose assumption is `verified` must name a
framework identity equal to the identity recorded in the AER (the `bench`/`harness` actors' `code`), or, for a
code-range verification, the AER's recorded code bound (`committed_no_later_than` and the profile pins) must lie
inside the verified range. Otherwise the AER fails validation.

### D.5.3 Class guidance

The classes follow [landscape/prov_semantics.md §2].
- **D (derived)**: a deterministic function of observed fields plus a documented property of the framework that ran,
  verified for the producing code identity (commit, wheel hash or the whole possible code range). The code is cited.
- **I (inferred)**: rests on a heuristic, a pattern, a table, an unverified code state, or a claim (README, PR or
  paper).
- A profile whose `[family.agentdojo.harness] code_identity = "unpinned"` MAY still cite a D rule if the cited
  behaviour is shown to be identical across the whole possible code range and the rule's verification lists that
  range. For example, the 3-pass loop exists at `c2748856`, `15de4430` and `v0.1.35` [verify/agentdojo.md §3].
  Otherwise it MUST cite the I twin. Which commits count as verified for a profile is its `verified_code` (§D.5.4
  "Citation of D rules", regeneration-batch item 3), for every D rule of the family catalogues.
- **`agentdojo.defence_suffix` is class I** in v0.1. The directory-suffix naming convention has not been verified over
  the producing code range, and the June-2024 logs have `code_identity = "unpinned"` (R-09). A later verified rule
  would be a new rule id.
- Released AgentDojo-PROV v1 context membership is **INFERRED** (`adprov.context_is_prefix@1`, class I): its D
  reading rested on a version string and on the unversioned `_CompatLLM` client (AD-05 (c)). It goes to the inference
  bundle; it can become D only through a user-supplied, digest-pinned generation-time harness (U-01).

**Aliases retired** (R-09 and the reconciliation of C.16 with this index). The names on the left MUST NOT appear in
any catalogue, example or test; C regenerates its examples with the names on the right.

| Retired name | Canonical name |
|---|---|
| `agentdojo.log_holds_last_attempt` | `agentdojo.log_holds_last_pass` |
| `agentdojo.pi_detector_placeholder` | `agentdojo.pi_detector_sentinel` |
| `rope.model_from_directory` | `rope.model_dir_identity` |
| `agentdojo.evaluation_timestamp_is_start` | `agentdojo.naive_local_timestamp` |
| `agentdojo.blob_introducing_commit` | `agentdojo.committed_no_later_than` |
| `agentdojo.outcome_origin` | `agentdojo.benign_security_constant` / `agentdojo.dos_security_rule` / `agentdojo.run_error_imposed_outcome` / `agentdojo.checker_outcome` |
| `agentdojo.pipeline_model_prefix` | `agentdojo.pipeline_dir_is_model_identity` (class I) |
| `agentdojo.defence_from_pipeline_suffix` | `agentdojo.defence_suffix` (class I) |
| `adprov.compat_args_from_raw` | **deleted** (AD-02) |
| `corpus.same_execution_efp` | deferred with fingerprints (AD-10) |
| `adprov.outcome_origin` | `adprov.checker_outcome` / `adprov.benign_security_normalised` (converted files: the `agentdojo` outcome rules) |
| `adprov.null_reply_encoding_changed` | `adprov.release_null_as_empty` |
| `adprov.reasoning_provenance_unknown` | `adprov.reasoning_log_alignment` |
| `stac.case_is_one_execution` | `stac.case_is_one_scenario` |
| `stac.case_targets_agent` | **deleted**: the target agent of a scenario is `unk` (R-28) |
| `agentdyn.progent_denial` | `agentdyn.progent_denial_pattern` |
| `stac.scripted_call_id_format` | `stac.assistant_turns_scripted` |
| `stac.arguments_double_encoded` | `stac.double_json_arguments` |

`adprov.converted_timing_stub` is not used: the `"0"` stub of converted transcripts is covered by
`adprov.timing_stub_is_unknown@1` (C.7.3, J.3.2).

### D.5.4 Initial rule index (v0.1)

All rules below are `@1`. "Code" is the primary citation; full entries (with assumptions and verification) are in the
catalogues. This index is authoritative for rule names (R-09): every rule id cited in C, EF, HL, I or K exists here or
in the `aer`, `aprov`, `cap` or `corpus` catalogues (§D.5.1). The class column is the effective class (AD-05).

| Rule id | Cl. | Statement (short) | Code / evidence |
|---|---|---|---|
| `agentdojo.messages_append_ordered` | D | Message array order is append order within the logged pass. | `agent_pipeline/tool_execution.py` (results appended); [landscape/trace_formats.md §6.8] |
| `agentdojo.messages_append_ordered_unverified` | I | The same reading where the producing harness code is not verified (profiles `rope`, `agentdyn`, `survey-runs`); the I twin required by §D.5.3 (EF F.2.1 row 15). | as `agentdojo.messages_append_ordered`; [sources/rope.md §4.3] |
| `agentdojo.log_holds_last_pass` | D | The file holds only the final pass. | see §D.5.2 |
| `agentdojo.log_holds_last_pass_unverified` | I | The reading of `agentdojo.log_holds_last_pass` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdojo.log_holds_last_pass` |
| `agentdojo.null_final_implies_three_passes` | D | A final assistant `content` of null with no run error means this is the 3rd of 3 passes (2 unobserved). The environment was not initial. | `task_suite.py:383-394`, `:70-75`; [verify/agentdojo.md §3], [verify/rope.md §4] |
| `agentdojo.null_final_implies_three_passes_unverified` | I | The reading of `agentdojo.null_final_implies_three_passes` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdojo.null_final_implies_three_passes` |
| `agentdojo.assistant_msg_has_one_call` | D | In an undefended single-LLM pipeline each assistant message is the kept output of one LLM-element invocation. | AgentPipeline / ToolsExecutionLoop structure, 0.1.35 |
| `agentdojo.assistant_msg_has_one_call_unverified` | I | The same reading where the producing harness code is not verified (profiles `rope`, `agentdyn`, `survey-runs`); the I twin required by §D.5.3 (EF F.2.1 row 8). | as `agentdojo.assistant_msg_has_one_call`; [sources/rope.md §4.3] |
| `agentdojo.context_is_prefix` | I | A model call's input is every earlier message of the pass (assumption `apv:FullContextResend`). | `openai_llm.py` message conversion; [audit/capture.md §8 D7] |
| `agentdojo.tool_msg_is_one_execution` | D | Each tool message is one ToolsExecutor iteration over one tool call. | `tool_execution.py:58-115` |
| `agentdojo.tool_msg_is_one_execution_unverified` | I | The same reading where the producing harness code is not verified (profiles `rope`, `agentdyn`, `survey-runs`); the I twin required by §D.5.3 (EF F.2.1 row 10). | as `agentdojo.tool_msg_is_one_execution`; [sources/rope.md §4.3] |
| `agentdojo.tools_executed_sequentially` | D | Calls in one assistant message are executed in list order, one at a time. | `tool_execution.py` |
| `agentdojo.tools_executed_sequentially_unverified` | I | The reading of `agentdojo.tools_executed_sequentially` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdojo.tools_executed_sequentially` |
| `agentdojo.call_id_unique_match` | D | A tool result is linked to a call by a non-empty id that is unique within its batch. | [landscape/trace_formats.md §6.5] |
| `agentdojo.call_id_unique_match_unverified` | I | The reading of `agentdojo.call_id_unique_match` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdojo.call_id_unique_match` |
| `agentdojo.positional_match` | I | A tool result is linked by position within the batch, verified against the embedded `tool_call` echo. | [audit/legacy_replay.md §14 item 13] |
| `agentdojo.args_are_effective` | D | Logged args are post-normalisation (in-place `literal_eval`), so the requested args are overwritten in place (`unk overwritten` where a field would hold them). | `tool_execution.py:99-101` (0.1.35) |
| `agentdojo.args_are_effective_unverified` | I | The reading of `agentdojo.args_are_effective` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdojo.args_are_effective` |
| `agentdojo.pipeline_dir_is_model_identity` | I | The model is resolved from the directory and identity table, not from `pipeline_name`. | [sources/agentdojo.md §3.2] |
| `agentdojo.local_dir_model_identity` | I | The HF model id for `local*` directories comes from the directory name plus PR #96/#97 (claimed). | [sources/agentdojo.md §5.3] |
| `agentdojo.defence_suffix` | I | The defence is parsed from the directory suffix list. Class I until the naming convention is verified over the producing code range (R-09). | [sources/agentdojo.md §8.2] |
| `agentdojo.user_is_simulated` | D | The `user` messages of a task are issued by the harness (`InitQuery`): the user actor is a `simulated_user`, and the agent acts on its behalf. | `agent_pipeline/basic_elements.py` `InitQuery`; C.16.1 |
| `agentdojo.user_is_simulated_unverified` | I | The reading of `agentdojo.user_is_simulated` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdojo.user_is_simulated` |
| `agentdojo.system_prompt_from_harness` | D | The system message is the benchmark's default system prompt, inserted by the pipeline's `SystemMessage` element; its author is the `bench` actor. | `agent_pipeline/basic_elements.py` `SystemMessage`; C.16.1 |
| `agentdojo.system_prompt_from_harness_unverified` | I | The reading of `agentdojo.system_prompt_from_harness` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdojo.system_prompt_from_harness` |
| `agentdojo.functions_runtime` | D | Tools run in AgentDojo's `FunctionsRuntime`: the tool-runtime actor exists. Its acting for the agent is the next rule (phase 5, EF E.10 item 21). | `functions_runtime.py`; C.16.1 |
| `agentdojo.functions_runtime_unverified` | I | The reading of `agentdojo.functions_runtime` where it cites no code, only documentary evidence (D-27 c6); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdojo.functions_runtime` |
| `agentdojo.auto_execution_unverified` | I | The runtime dispatches every requested tool call without confirmation, on behalf of the agent (`apv:AutoExecution`, asserted): cited on the `env` actor at `/on_behalf_of` (`evf {"/on_behalf_of": "I"}`). Added in phase 5; a D twin with a verified entry is for pinned harnesses (phase 8). | `tool_execution.py` `ToolsExecutor.query` at `c274885` (l. 48–115) and `089ed468` (l. 46–115) |
| `agentdojo.checker_inputs_unverified` | I | The task checker reads the final output text, the pre- and post-environment and the scored attempt's tool calls (the four checker-input assumptions, asserted): cited on every `origin: checker` judgement at `/inputs`, declared `unk {"/inputs": "not_recorded"}`. Added in phase 5. | `task_suite.py` l. 281–312, 399 at `089ed468` |
| `agentdojo.benchmark_from_dialect` | D | A TraceLogger file was written by the AgentDojo benchmark runner, so the checker actor is the `agentdojo` benchmark. | `benchmark.py` TraceLogger construction; C.16.1 |
| `agentdojo.benchmark_from_dialect_unverified` | I | The reading of `agentdojo.benchmark_from_dialect` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdojo.benchmark_from_dialect` |
| `agentdojo.tool_status_from_error` | D | `error: null` → `ok`; `Empty function name provided…`, `Invalid tool <x> provided.` and non-denial `ValidationError:` prefixes → `invalid`; any other error → `error`. | `tool_execution.py:58-115`; `functions_runtime.run_function` [audit/capture.md §3] |
| `agentdojo.tool_status_from_error_unverified` | I | The reading of `agentdojo.tool_status_from_error` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdojo.tool_status_from_error` |
| `agentdojo.checker_outcome` | D | With no run error, a recorded attack (or a user-task utility) and no DoS rule, the stored outcome value is the task checker's return value. | `benchmark.py` `run_task_with_injection_tasks` / `run_task_without_injection_tasks` |
| `agentdojo.checker_outcome_unverified` | I | The reading of `agentdojo.checker_outcome` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdojo.checker_outcome` |
| `agentdojo.first_user_msg_is_task_prompt` | D | The first user message is the task `PROMPT`, or the injection `GOAL` in pre-pass runs. | `task_suite.py:375-378` |
| `agentdojo.injection_task_as_user_task` | D | `user_task_id = injection_task_N` with attack `none` is the solvability pre-pass. | `benchmark.py:200-209` |
| `agentdojo.injection_task_as_user_task_unverified` | I | The reading of `agentdojo.injection_task_as_user_task` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdojo.injection_task_as_user_task` |
| `agentdojo.security_polarity` | D | `security = true` means the injection task succeeded. | `base_tasks.py` docstring; maintainer, issue #95 [verify/agentdojo.md §4] |
| `agentdojo.benign_security_constant` | D | Benign `security` is the constant `True`: not applicable, not "secure". | `task_suite.py:408-410` |
| `agentdojo.benign_security_constant_unverified` | I | The reading of `agentdojo.benign_security_constant` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdojo.benign_security_constant` |
| `agentdojo.dos_security_rule` | D | Under a DoS attack, `security = not utility`. | `benchmark.py:149-150` |
| `agentdojo.dos_security_rule_unverified` | I | The reading of `agentdojo.dos_security_rule` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdojo.dos_security_rule` |
| `agentdojo.dos_placeholder_injection_task` | D | A DoS cell's `injection_task_id` is the suite's first injection task (a placeholder). | `benchmark.py:73-75` |
| `agentdojo.dos_placeholder_injection_task_unverified` | I | The reading of `agentdojo.dos_placeholder_injection_task` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdojo.dos_placeholder_injection_task` |
| `agentdojo.run_error_imposed_outcome` | D | A non-null `error` means the outcomes were imposed `(False, True)` by the runner. | `benchmark.py:122-147, 286-312` |
| `agentdojo.run_error_imposed_outcome_unverified` | I | The reading of `agentdojo.run_error_imposed_outcome` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdojo.run_error_imposed_outcome` |
| `agentdojo.unexecuted_trailing_calls` | D | Tool calls in the last assistant message with no tool message were never dispatched (`max_iters=15`). | `tool_execution.py:130-156` |
| `agentdojo.no_execution_observed` | D | Empty `messages`: no trajectory exists, so the record is `unit: "outcome_only"`; outcomes, where present, are kept as logged. | [sources/agentdojo.md §4.4], [sources/rope.md §4.4] |
| `agentdojo.incomplete_run` | D | Missing outcome or duration keys: interrupted run. | [sources/agentdojo.md §3.3] |
| `agentdojo.pi_detector_sentinel` | I | The tool content equals the PI-detector sentinel, so the original output was overwritten in place (`unk {"/original": "overwritten"}`, R-08). | `pi_detector.py:50` |
| `agentdojo.tool_filter_aux_message` | I | In `-tool_filter` pipelines the 2nd user message and the next tool-free assistant message belong to the filter LLM. | [sources/agentdojo.md §3.5] |
| `agentdojo.repeat_user_prompt_copy` | I | A later user message equal to the first is a defence re-insertion. | [sources/agentdojo.md §3.5] |
| `agentdojo.spotlighting_content` | I | Tool content is the post-defence rendering (`<<…>>`). | [sources/agentdojo.md §3.5] |
| `agentdojo.defence_denial_message` | I | A tool message whose error is the denial text the profile's quirk states for a defence of the file (exact, prefix or regex) records that defence's refusal: no execution, a `deny` decision whose subject is the refused call, the error as its reason. Profile-parametric; the hook ships with the phase-10d profiles (seven sources, about 6,500 messages). | the logged text and the profile; phase-10d routing R1 |
| `agentdojo.payload_attributed_to_attacker` | I | Injection payloads are attributed to the attacker actor. | D7 agent list |
| `agentdojo.benchmark_era_from_commit` | I | The candidate benchmark version for old-format files comes from the introducing commit and the task-set shape, per file. | [sources/agentdojo.md §4.3], [verify/agentdojo.md §5.3] |
| `agentdojo.committed_no_later_than` | D | The commit date of the introducing commit is an upper bound on run time. Never a PROV time. | [sources/agentdojo-inspect.md §7] |
| `agentdojo.committed_no_later_than_unverified` | I | The reading of `agentdojo.committed_no_later_than` where it cites no code, only documentary evidence (D-27 c6); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdojo.committed_no_later_than` |
| `agentdojo.naive_local_timestamp` | D | `evaluation_timestamp` is the naive local time of TraceLogger construction, with 1 s resolution and unknown timezone. Applies where the producing TraceLogger code is verified (upstream `v1.k14`, 0.1.30 and later). | `logging.py:174` |
| `agentdojo.naive_local_timestamp_unverified` | I | The same reading where the producing harness code is not verified (ROPE's unreleased fork states, AgentDyn and survey forks); the I twin required by §D.5.3. | `logging.py:174`; [sources/rope.md §4.3] |
| `agentdojo.duration_scope` | D | `duration` covers environment load, all passes and scoring. | `logging.py:186-196`, `benchmark.py:106-116` |
| `agentdojo.placeholder_args_ground_truth_only` | D | `placeholder_args` is never injection evidence. | [audit/capture.md §8 D1] |
| `agentdojo.local_model_tag_count` | I | More `<function=` tags than parsed calls means parsed calls may have been dropped. | [sources/agentdojo.md §3.5], issue #202 |
| `rope.denial_error_pattern` | I | An error matching the ROPE denial pattern is a guard denial; the tool did not run. | [sources/rope.md §3.4], [verify/rope.md §6] |
| `rope.denial_query_echo_variant` | D | The suffix `user task: None.` marks the pre-fix enforcer text. | `enforce.py:117` "THE FIX" |
| `rope.denial_query_echo_variant_unverified` | I | The reading of `rope.denial_query_echo_variant` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `rope.denial_query_echo_variant` |
| `rope.model_dir_identity` | I | The model comes from the directory, corroborated by id style. `pipeline_name` is a config tag. | [verify/rope.md §5] |
| `rope.tree_arm_config` | D | The `ablation/<policy>` and `router/<router>[-clamp]` path levels give the defence configuration. | [sources/rope.md §8.2] |
| `rope.tree_arm_config_unverified` | I | The reading of `rope.tree_arm_config` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `rope.tree_arm_config` |
| `rope.benchmark_from_suite` | D | banking/slack/travel → AgentDojo; github/shopping/dailylife → AgentDyn. | [sources/rope.md §8.2] |
| `rope.benchmark_from_suite_unverified` | I | The reading of `rope.benchmark_from_suite` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `rope.benchmark_from_suite` |
| `rope.guard_active_in_main_tree` | I | The ROPE guard was active in main-tree runs. | [sources/rope.md §4.3] |
| `rope.harness_is_vendored_autodojo` | I | Logs were written by the vendored AutoDojo `agentdojo` fork, at unreleased code states. | [sources/rope.md §3.1, §4.3 item 2] |
| `rope.security_correction` | D | ROPE's released correction rules (slack IT5, dailylife IT7, github IT1) recompute `security` from the executed, error-free tool messages; the result is a `recomputed` judgement beside the recorded one. | `runs/corrections.py` → `slack_it5.py`, `dailylife_it7.py`, `github_it1.py` [sources/rope.md §3.6] |
| `agentdyn.variant_by_keyset` | D | Variant A/B/C/D is determined by key set. | [sources/agentdyn.md §3.1] |
| `agentdyn.pipeline_dir_registry` | I | Model, defence and provider come from the 76-row table. | [sources/agentdyn.md §8.3] |
| `agentdyn.last_assistant_content_none_max3` | D | Retry happens iff the last assistant message anywhere has null content. | AgentDyn `task_suite.py` change [sources/agentdyn.md §3.5] |
| `agentdyn.last_assistant_content_none_max3_unverified` | I | The reading of `agentdyn.last_assistant_content_none_max3` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdyn.last_assistant_content_none_max3` |
| `agentdyn.json_decode_error_imposed` | D | A JSONDecodeError skip imposes `(False, True)`. | AgentDyn `benchmark.py` [sources/agentdyn.md §4.4] |
| `agentdyn.json_decode_error_imposed_unverified` | I | The reading of `agentdyn.json_decode_error_imposed` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdyn.json_decode_error_imposed` |
| `agentdyn.drift_user_error_key` | D | A `user` message carrying an `error` key is DRIFT validator feedback. | [sources/agentdyn.md §3.7] |
| `agentdyn.drift_user_error_key_unverified` | I | The reading of `agentdyn.drift_user_error_key` where the code that wrote the record is not among the commits it cites (D-24); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdyn.drift_user_error_key` |
| `agentdyn.camel_orphan_tool_result` | I | A CaMeL tool message without a matching assistant call is an interpreter-initiated execution. | [sources/agentdyn.md §3.8] |
| `agentdyn.progent_denial_pattern` | I | A Progent `ValidationError … is not allowed..` error is a policy denial. | [sources/agentdyn.md §3.8] |
| `agentdyn.variant_c_rekey` | I | Variant-C curation: a variant C file (`drift.k18.messages`) is one of AgentDyn's DRIFT outputs, re-keyed (`conversations` → `messages`) and relocated by the AgentDyn authors from AgentDyn's own history blobs `runs/DRIFT/**` (edge E11). The `head` form is imported (variant C, `partial`); the history blob becomes an alias origin only when the `history` part is imported (deferred, I.2.4). | [verify/agentdyn.md §3]; I.2.2 E11 |
| `drift.single_pass` | D | `DRIFTTaskSuite.model_output_from_messages` never returns None, so there is one pass. | [sources/drift.md §3.1], [verify/drift.md §3] |
| `drift.tool_output_post_isolation` | D | Tool content may be edited in place by `injection_isolate`; the raw output is overwritten (`overwritten`, R-08). | `DRIFTLLM.injection_isolate` [verify/drift.md §3] |
| `drift.assistant_reserialised` | D | Assistant text matching the exact DRIFT template is a re-serialisation of the parsed completion. | [verify/drift.md §3] |
| `drift.call_error_user_is_validator` | D | A `user` message wrapped in `</function_error>` holding `[CALL ERROR]` is validator feedback. | [sources/drift.md §3.4] |
| `drift.calls_in_text_not_executed` | D | A re-serialised assistant turn with a non-empty `<function_call>` body and empty `tool_calls` proposed calls that were not executed (refused or deduplicated). | [verify/drift.md §4] |
| `drift.no_system_message` / `drift.no_injection_map` | D | No system message in the pipeline; no `injections` written. | `pipeline_main.py` [verify/drift.md §3] |
| `drift.plan_fields_semantics` | D | `initial_*` fields hold the initial plan at head and the end-of-run plan at `53dbc6c`. | [verify/drift.md §5] |
| `mandate.decline_prefix` | D | `content == error` starting `MANDATE_DECLINE:` is a gate decline; the tool did not run. | `agentdojo_mandate_eval.py:193-239` |
| `mandate.allow_inferred` | I | A gated call without a decline was allowed. | [verify/mandate-agentdojo-eval.md §3.4] |
| `survey.model_from_results_dir` | I | The model comes from the `runs_<slug>` directory and `run_full_benchmark.sh`. | [sources/agent-security-tools-survey.md §10] |
| `survey.internal_server_error_patch` | I | The README claims patch (c) imposes `(False, True)` on InternalServerError. | [sources/agent-security-tools-survey.md §4.1] |
| `autodojo.payload_cache_link` | I | The payload equals variant 0 of a cache cell (with ambiguity set). | [sources/autodojo.md §3.3], [verify/autodojo.md #16] |
| `adprov.v1_benchmark_is_agentdojo` | D | transcript/v1 records AgentDojo runs. | `agentdojo_prov/generate.py` [audit/capture.md §4.2.5] |
| `adprov.release_undefended` | D | Released runs refused defences (OB-8), so `defense_id` is null. | [audit/capture.md §4.2.5] |
| `adprov.v1_capture_code_semantics` | I | The AgentDojo-PROV capture's observer effects applied, although the capture code version is not recorded per trace; justifies the imported `instrumentation` items. | [audit/capture.md §6, §8 D3] |
| `adprov.single_attempt_from_call_count` | D | If the harness's call counter equals the assistant turns held, no earlier pass made calls. | [audit/capture.md §4.2.4] |
| `adprov.single_attempt_from_call_count_unverified` | I | The reading of `adprov.single_attempt_from_call_count` where it cites no code, only documentary evidence (D-27 c6); cited per "Citation of D rules" below (regeneration-batch item 3). | as `adprov.single_attempt_from_call_count` |
| `adprov.assistant_turn_one_call` | D | Each assistant turn is the kept output of one agent call. | as `agentdojo.assistant_msg_has_one_call` |
| `adprov.assistant_turn_one_call_unverified` | I | The reading of `adprov.assistant_turn_one_call` where it cites no code, only documentary evidence (D-27 c6); cited per "Citation of D rules" below (regeneration-batch item 3). | as `adprov.assistant_turn_one_call` |
| `adprov.call_id_unique_match` | D | A tool turn answers the unique call with its id. | as `agentdojo.call_id_unique_match` |
| `adprov.call_id_unique_match_unverified` | I | The reading of `adprov.call_id_unique_match` where it cites no code, only documentary evidence (D-27 c6); cited per "Citation of D rules" below (regeneration-batch item 3). | as `adprov.call_id_unique_match` |
| `adprov.tool_turn_is_one_execution` | D | A tool turn records one dispatch of the call it answers. | as `agentdojo.tool_msg_is_one_execution` |
| `adprov.tool_turn_is_one_execution_unverified` | I | The reading of `adprov.tool_turn_is_one_execution` where it cites no code, only documentary evidence (D-27 c6); cited per "Citation of D rules" below (regeneration-batch item 3). | as `adprov.tool_turn_is_one_execution` |
| `adprov.context_is_prefix` | I | Each agent call's input was exactly the preceding turns (`apv:FullContextResend`); INFERRED for released v1 (AD-05). | [audit/capture.md §8 D7] |
| `adprov.finish_reason_positional` | D | Finish reasons are appended once per kept reply, in order (RT-2); aligned only when counts are equal. | [audit/capture.md §4.1] |
| `adprov.finish_reason_positional_unverified` | I | The reading of `adprov.finish_reason_positional` where it cites no code, only documentary evidence (D-27 c6); cited per "Citation of D rules" below (regeneration-batch item 3). | as `adprov.finish_reason_positional` |
| `adprov.lost_calls_from_count` | D | Calls counted by the harness but not held are earlier-pass calls, recorded as lost. | C.7.4; [audit/capture.md §4.2.4] |
| `adprov.lost_calls_from_count_unverified` | I | The reading of `adprov.lost_calls_from_count` where it cites no code, only documentary evidence (D-27 c6); cited per "Citation of D rules" below (regeneration-batch item 3). | as `adprov.lost_calls_from_count` |
| `adprov.release_null_as_empty` | D | Before 2026-10-04 a null reply was stored as `""`; such text is `ambiguous`. | [audit/capture.md §7 item 2] |
| `adprov.temperature_not_transmitted` | D | A configured `temperature` of 0.0 was not transmitted (0.1.35 `temperature or NOT_GIVEN`). | [audit/capture.md §3 table] |
| `adprov.model_names_registration` | I | The payload's model name was harness-synthesised ("Gpt 5 Nano", …). | [audit/capture.md §4.5 item 3] |
| `adprov.checker_outcome` | D | Released `meta.utility`/`meta.security` are the stock checkers' values. | `generate.py`; [audit/capture.md §4.2] |
| `adprov.benign_security_normalised` | D | A benign `security: null` is the harness's normalisation of the constant benign value. | `generate.py` G-7 |
| `adprov.run_interval_scope` | D | `started_at`/`ended_at` bracket environment load and scoring. | [audit/capture.md §4.2.2] |
| `adprov.reasoning_log_alignment` | I | Reasoning attached by position from the side log (TR-3); native-block versus log-aligned origin is undecidable. | [audit/capture.md §4.3] |
| `adprov.timing_stub_is_unknown` | D | A tool `"0"` timing under `timing_stubbed` is not a time: `t.raw` keeps the verbatim strings, `t.start`/`t.end` are `unk`. | `convert_runs.py:138-208`; C.7.3 |
| `adprov.converted_stem_to_upstream_path` | D | A converted transcript derives from the upstream log found by inverting `convert_runs._output_relpath` at the `2024-06` pin. | `agentdojo_prov/convert_runs.py:175-183` [audit/legacy_replay.md §3.2] |
| `adprov.v1_benign_label` | D | View rule (C.15.3): in the `transcript/v1` views (`render`, `render_converted`, §D.7.4) a null `exec.task.attack_id` renders as `meta.attack_type: "benign"`. The AER keeps `null`; the label is a v1 presentation convention, never a task kind (§D.6.5). | `agentdojo_prov/convert_runs.py:145` (`attack_type or BENIGN_ATTACK`), `generate.py:490` (released benign cells); C.15.3 |
| `inspect.header_applies_to_samples` | D | `header.json` eval metadata (task, model, generate config, revision, packages) applies to every sample of the log. | inspect_ai `log/_log.py` `EvalSpec` [landscape/trace_formats.md §3.2] |
| `inspect.span_is_scope` | D | A `span_begin`/`span_end` pair is a scope; `parent_id` is its parent; `solver:*` spans group agent activity and `scorer:*` spans group judge activity. | [sources/agent-security-tools-survey.md §5.3] |
| `inspect.agent_span_is_subagent` | D | A span named by a `ToolEvent.agent_span_id` is a sub-agent scope spawned by that tool execution. | [landscape/trace_formats.md §3.2] |
| `inspect.model_event_is_call` | D | A `model` event is one model call; its `input`/`input_refs` are what the model saw; `call.request`/`call.response` are the wire bodies. | [landscape/trace_formats.md §3.2] |
| `inspect.cache_read` | D | `cache == "read"`: no inference took place (`status: cached`). | `ModelEvent.cache` |
| `inspect.model_error` | D | A `model` event with `error` and no output is a failed call (`status: error`). | `ModelEvent.error` |
| `inspect.tool_event_is_execution` | D | A `tool` event is one tool execution; `message_id` names its result message. | `ToolEvent` |
| `inspect.tool_call_id_match` | D | `ToolEvent.id` equals the `ToolCall.id` of the request part it executes. | [landscape/trace_formats.md §3.2 "Ordering and causality"] |
| `inspect.tool_error_status` | D | `ToolEvent.error.type` maps to `invalid` (`parsing`) or `error` (other types); an `approval` error is a denial (`decision`, no execution). The literal table is fixed at implementation against the band's producer commit. | `ToolCallError.type` literal and `call_tool` (`src/inspect_ai/tool/_tool_call.py:69-90`, `src/inspect_ai/model/_call_tools.py:606-659` at the producer commit `53c1fa98`; D.9.5) |
| `inspect.tool_output_truncated` | D | `ToolEvent.truncated` means the harness shortened the output before the model saw it. | `ToolEvent.truncated` |
| `inspect.approval_decision` | D | `approval`/`review` events are decisions: approve/modify/reject/escalate/terminate → allow/modify/deny/escalate/terminate. | `ApprovalEvent`, `ReviewEvent` |
| `inspect.compaction` | D | A `compaction` event replaced history with a summary; when a model call in its span produced the summary, that call generated it. | `CompactionEvent` |
| `inspect.state_event` | D | `state`/`store` events are JSON-Patch state changes of the TaskState or the store. | `StateEvent`, `StoreEvent` |
| `inspect.sandbox_activity` | D | A `sandbox` event outside any tool event is a sandbox activity whose output is an `artefact`. | `SandboxEvent` |
| `inspect.score_event` | D | A `score` event (and `sample.scores`) records the scorer's values for the sample. | `ScoreEvent` |
| `inspect.sample_init_fixtures` | D | `sample_init`, `input`, `metadata` and the first model event's `tools` are the task's fixtures. | `EvalSample` |
| `inspect.no_order_from_event_list` | D | Event list order is not occurrence order; order comes from references and timestamps only. | [landscape/trace_formats.md §3.2, observed] |
| `stac.case_is_one_scenario` (planned) | D | One STAC array element is one benchmark-generation scenario (`unit: "scenario"`), not an agent execution. Replaces `stac.case_is_one_execution`. | [sources/multiturn-agent-attack.md §0, §3.3–3.5] |
| `agentdojo.empty_assistant_text_ambiguous_unverified` | I | The reading of `agentdojo.empty_assistant_text_ambiguous` where it cites no code, only documentary evidence (D-27 c6); cited per "Citation of D rules" below (regeneration-batch item 3). | as `agentdojo.empty_assistant_text_ambiguous` |
| `adprov.empty_assistant_text_ambiguous_unverified` | I | The reading of `adprov.empty_assistant_text_ambiguous` where it cites no code, only documentary evidence (D-27 c6); cited per "Citation of D rules" below (regeneration-batch item 3). | as `adprov.empty_assistant_text_ambiguous` |
| other `stac.*` (planned) | | see §D.8.2; the names listed there are reserved in the planned `stac` catalogue | |

Semantics-profile rules of `agentdojo.suites` (for example `agentdojo.channel_table`, `agentdojo.read_tools`,
`agentdojo.sink_tools`, `agentdojo.integrity_external_content`, `agentdojo.injection_marker_yaml`,
`agentdojo.yaml_norm`, `agentdojo.utility_meaning`, and the v2.3 scoring rule set `agentdojo.scoring`) are declared in
the same `agentdojo` catalogue and specified with the semantics profile (C.14, EF, J); they are not repeated here.
The execution-fingerprint methods `agentdojo.tracelogger_efp` and `inspect.sample_identity_efp` are reserved names,
deferred with fingerprint deduplication (AD-10 row 7). `agentdojo.record_complete_with_replay` is likewise a reserved
name (`status = "reserved"` in the `agentdojo` catalogue), deferred with outcome replay (AD-10 row 2); v0.1 never
applies it (B COR-06).

**Citation of D rules (D-24, D-27 c6; regeneration-batch item 3).** A class-D rule is cited at D only for a record whose
producing code its catalogue entry cites. This holds for every D rule of an adapter family's catalogues, not only the
structural ones. The "verification" of a D rule is its `code` list: full commits of the code the behaviour was read from
(§D.5.2; no adapter rule declares a `verified` assumption yet). A profile states which commits produced its records in
`verified_code`: `[family.agentdojo.harness] verified_code` for the AgentDojo family, `[family.adprov] verified_code` for
transcript/v1. Each entry is `{commit, applies?, note?}`, and the optional selector names facets (`variant` for TraceLogger
logs; `transcript` = `released` | `converted` for transcript/v1). For each record, the mapper cites a D rule of the
family's catalogues at D only when one of the rule's `code` commits is among the entries that apply to the record.
Otherwise it cites the rule's I twin `<id>_unverified@<n>` (same version), and every field the rule justifies is weakened
to I (C.6.5 rule 1), which moves its statements into the inference bundles. A causal `after` edge resting on a twinned
`generated_by` link is weakened with it.

Consequences:

- A rule that cites no code is never verified, so it is always cited through its twin (D-27 c6).
- A D rule that resolves to a twin the catalogue does not declare stops the import (`RuleNotDeclared`, fail closed).
- The only exceptions are the rules a family declares independent of the producing code. In v0.1 these are
  computations over the logged bytes: `agentdojo.system_prompt_variant_digest` (a digest comparison against a pinned
  text), `rope.security_correction` (ROPE's released correction code applied to the logged messages) and the three
  injection-marker normalisers `agentdojo.yaml_norm`, `pyrepr_norm` and `json_norm` (D-86 addendum).
- The AgentDojo family's facets include `introduced_under` (D-84, D.6.16 item 10): the oldest pin whose history
  contains the commit that introduced the log, so a `v0.k11` log introduced after `c274885` is not June-2024 code.
- SEM annotations follow the same policy (D-86 and its addendum; `agentdojo.suites@2`, C.14.8 item 6). The semantics
  profile resolves each rule it cites with the `verified_code` of the source profile the AER header names (only when
  the packaged profile has the header's digest, otherwise none) and the facets the AER records (the dialect `variant`,
  adprov's `transcript`).
- Seal issues cite the rule they name as given, except where an issue reports a statement's reading. The retry,
  last-pass and run-error issues cite the rule (or twin) the statement cites.
- A loss issue proves loss (H.3.2(2), `known_incomplete`) only when its rule is class D. A loss inferred under a twin
  leaves the execution `unverifiable` (analysis B6).
- The choice is a function of the profile, the record's facets and the catalogue version, fixed at map time and never
  computed from the content (§D.5.2 validation item 8). It is implemented in `adapters/code_verification.py` and, for
  the AgentDojo family, `adapters/agentdojo/citation.py`.

In v0.1:

- `rope`, `agentdyn` and `survey-runs` verify no code (unreleased fork states, the AgentDyn January runs, the survey's
  patched fork), so they cite the twin of every D rule they use, the ROPE and AgentDyn pins' own rules included.
- `agentdojo-upstream` verifies `c274885` for `v0.k11` logs, and `a75aba76` (0.1.35) plus the head pin `089ed468` for
  `v1.k14` logs (the 0.1.30+ family).
- `mandate-agentdojo-eval` verifies `a75aba76`, `089ed468` and the evaluation script at `fa62a977`.
- `adprov-v1` verifies the AgentDojo-PROV writer `579a908`, and `c274885` for converted transcripts only. The AgentDojo
  version of the released captures is not recorded.
- The live profiles verify their pinned harness (`a75aba76`, the AutoDojo fork `aa458794`) for the native-log mapping.
- A new profile whose harness code is not verified sets `verified_code = []`.
- The twins added by item 3 are listed in the table above next to the D rule they restate. The three phase-6
  structural twins and `naive_local_timestamp_unverified` are the same mechanism.

Adapter issue codes referenced by other sections are declared in their catalogues: `adprov.tool_call_id_mismatch`,
`adprov.content_hash_mismatch`, `adprov.upstream_link_unresolved`, `adprov.v1_layout_unexpected_order`,
`adprov.v1_layout_unknown_member` (adprov, §D.7, J.3.2); `inspect.sample_limit`,
`inspect.branch_unsupported`, `inspect.compaction_unmodelled`, `inspect.unmapped_event`,
`inspect.unknown_content_type` (inspect, §D.9.3); `foobench.unmapped_event_type`, `foobench.observation_unlinked`,
`foobench.handoff_not_expanded` (the toy adapter, §D.12).

### D.5.5 Issue codes

**Seal issue codes: see C.12.3 (single owner).** C owns the one closed list of core seal issue codes, which merges the
first revision's D.5.5 into C.12.3 (RESOLUTIONS §3.8, R-13): for example `identity_conflict` (not
`model_identity_conflict`), and `accounting_inconsistent` / `accounting_unverifiable` mirroring the verdicts (the
reported-count case is `accounting_inconsistent` with check `aer.acc.reported_counts@1`). Severity is
`info|warning|error`.

**Namespaced codes** (`<ns>.<code>`) MUST be declared in the catalogue's `issue_codes`. A seal issue enters the corpus
register as `map.<code>` and is never re-namespaced to an adapter.

**Register codes** (`<stage>.<code>`, owner HL H.6.3) are not seal issues; §D.2.8 case 4 lists the ones adapters
produce.

---

## D.6 The AgentDojo TraceLogger dialect family

### D.6.1 Producers

| Producer (code) | Writes | Sources |
|---|---|---|
| AgentDojo ≤ 0.1.29 (`function_calling_pi` era in June 2024) | `v0.k11` | upstream logs committed before 2025-03 (24,914 at head); AgentDojo-Inspect mirror (21,999); AgentDyn B (vendored 0.1.29 Progent, 5,184) |
| AgentDojo ≥ 0.1.30 (`80a490ac`, 2025-03-03) and forks | `v1.k14` | upstream 2025-07 local runs (11,765); ROPE (10,791); AgentDyn A (38,281); Mandate (396); survey (3,243); live capture's native log |
| DRIFT `pipeline_main.py` | `drift.k18.*` | DRIFT repo (`conversations`; 1,569 head + 1,046 history); AgentDyn C (`messages`; 4,258) and D (`conversations`, vendored DRIFT duplicate, 949) |

Sources: [sources/agentdojo.md §3.4], [sources/agentdyn.md §3.1], [sources/drift.md §3], [verify/drift.md §7].

### D.6.2 Detection by key set and variants

```python
K11 = {"suite_name", "pipeline_name", "user_task_id", "injection_task_id", "attack_type",
       "injections", "messages", "error", "utility", "security", "duration"}
K14 = K11 | {"benchmark_version", "evaluation_timestamp", "agentdojo_package_version"}
KD18_BASE = {"suite_name", "pipeline_name", "user_task_id", "injection_task_id", "attack_type",
             "build_constraints", "injection_isolation", "dynamic_validation", "adaptive_attack",
             "tool_permission", "initial_trajectory", "initial_checklist", "benchmark_version",
             "utility", "security", "total_tokens", "duration"}          # + exactly one of messages|conversations
OUTCOME = {"utility", "security", "duration"}
KNOWN_FORK_EXTRAS = {"injection_attack_name", "error_type", "router_bucket"}   # AutoDojo fork; 0 observed

def classify(obj) -> SniffResult:
    if not isinstance(obj, dict) or not {"suite_name", "user_task_id"} <= obj.keys():
        return SniffResult(False, reasons=("not_tracelogger",))
    msgs = "messages" if "messages" in obj else "conversations" if "conversations" in obj else None
    if msgs is None:
        return SniffResult(False, reasons=("no_message_list",))
    if "pipeline_name" not in obj:                       # May-2024 banking_rw dev logs (git history only)
        return SniffResult(True, "agentdojo.tracelogger", "pre_v0", reasons=("unsupported_variant",))
    if "build_constraints" in obj:
        base, expected = "drift.k18", KD18_BASE | {msgs}
        variant = f"drift.k18.{msgs}"
    elif "agentdojo_package_version" in obj:             # upstream's own discriminator (benchmark.py load_task_results)
        variant, expected = "v1.k14", K14
    else:
        variant, expected = "v0.k11", K11
    missing = expected - obj.keys()
    if missing - OUTCOME:
        return SniffResult(True, "agentdojo.tracelogger", variant, reasons=("missing_structural_keys",))  # -> MalformedArtefact
    if missing and variant == "v1.k14":
        variant = "v1.k14.incomplete"
    flags = {f"missing:{k}" for k in sorted(missing)} | {f"extra:{k}" for k in sorted(obj.keys() - expected)}
    return SniffResult(True, "agentdojo.tracelogger", variant, frozenset(flags))
```

Notes:
- Key **order** carries no semantics. It is a code-path artefact (benign vs attacked ordering)
  [sources/agentdojo.md §3.4]. The reader records it in `ext.agentdojo.top_level_keys` for diagnostics only.
- `extra:` keys go to `ext.agentdojo.extra`, verbatim, with an info issue `agentdojo.unknown_top_level_key`. If
  the AutoDojo fork's `error_type` key ever appears, it feeds the outcome-origin rule.
- AgentDyn's variant letters are profile labels over these structural variants: A → `v1.k14`, B → `v0.k11`,
  C → `drift.k18.messages`, D → `drift.k18.conversations` [sources/agentdyn.md §8.1]. AgentDyn D is owned by the
  DRIFT source (register code `select.owned_elsewhere`, owner `drift`).

### D.6.3 Reader rules (`agentprov.adapters.agentdojo.dialect.TraceLoggerReader`)

- **R-PARSE.** `agentprov.ingest.loaders.strict_json_loads` (G.3.3) under `IngestLimits` (G.3.2):
  - UTF-8 strict; a BOM is `ingest.json.bom`;
  - duplicate keys are rejected;
  - `NaN`/`Infinity` and overflowing literals are rejected;
  - depth ≤ 256 and size ≤ `max_json_bytes`.

  Files are small (max 493,642 B upstream [sources/agentdojo.md §4.1]), so sniffing parses fully. The parsed value
  keeps source member order and int/float typing; nothing else about the source lexis is kept by the reader.
- **Lexical hints** (replaces the first revision's R-LEX, AD-02). The mapper passes every object and number it copies
  from the source (message parts, `args`, `injections`, `duration`, …) through `agentprov.aer.canon.lex_hints()`, which
  writes the sparse `ext.lex {ord, flt}` of C.11.4. This is mandatory for `agentdojo.tracelogger` while
  `render_converted` is a gate (§D.7.4) [spec/B_audit_evidence].
- **R-CONTENT.** Per message, `content` is classified as `string` (old format), `null`, or `blocks` (a list of
  `{type, content}`).
  - Block types `text`, `thinking` and `redacted_thinking` are recognised (AgentDojo `types.py`).
  - Any other block type is kept as an `other` part, with an issue.
  - A mix of forms within one file raises the issue `agentdojo.mixed_content_forms`.
- **R-CALLS.** `tool_calls` is classified as `null` (old OpenAI/Anthropic "no calls"), `[]` (Gemini, Cohere and
  local "no calls"), or a list. For each FunctionCall the reader records the following
  [sources/agentdojo.md §3.5]:
  - key set: `{function,args,id}`, `{…,placeholder_args}` or `{function,args}`;
  - `id` form: `str`, `""`, `null` or absent;
  - `placeholder_args` presence.
- **R-PATH.** The reader parses the path components named by the profile layout and checks them against
  `path_must_agree`. A mismatch is reported (`agentdojo.path_field_mismatch`), never corrected.

### D.6.4 Quirk vocabulary (what profiles MUST declare)

A profile MUST declare every quirk below that applies to its source, with `observed` counts where the reports give
them. Those counts become golden test expectations over the full source (§D.6.10). Quirk ids are namespaced: the
shipped id is `agentdojo.<id>` for every row below (R-38; the table omits the prefix). A quirk the mapper detects in
data but the profile did not declare raises the issue `agentdojo.undeclared_quirk` (warning, `detail` = the quirk id).
The profile is then incomplete, never silently "fixed".

| Quirk id | What it is | Profiles | Evidence |
|---|---|---|---|
| `benign_security_constant` | Benign `security` is always `true` (field ignored) | all | [sources/agentdojo.md §3.3], [verify/agentdojo.md §4] |
| `dos_security_not_utility` | DoS `security = not utility`; `injection_task_id` is a placeholder | agentdojo | [sources/agentdojo.md §3.3], [audit/legacy_replay.md §2.2] |
| `silent_rerun_last_pass_only` | ≤ 3 passes on the same mutated environment; only the last is logged; detectable only when the final content is null | all except drift | [verify/agentdojo.md §3] (82), [verify/rope.md §4] (322), [verify/mandate-agentdojo-eval.md §2] |
| `injection_task_as_user_task_prepass` | The injection GOAL run as a user task, without injections | agentdojo, mandate, survey, agentdyn | [audit/legacy_replay.md §2.2], [verify/mandate-agentdojo-eval.md §2] |
| `empty_messages_with_outcome` / `empty_messages_without_outcome` | No trajectory; outcome present (207 AgentDojo) or absent (2 ROPE); `unit: "outcome_only"` | agentdojo, rope | [sources/agentdojo.md §4.4], [sources/rope.md §4.4] |
| `run_error_imposes_outcome` | A run error sets outcomes by rule (`params.utility/security`); AutoDojo fork: `security=false` plus `error_type` | agentdojo, agentdyn (JSONDecodeError), survey (patch c), autodojo-live | [verify/agentdojo.md §4], [sources/agentdyn.md §4.4], [sources/autodojo.md §4] |
| `incomplete_run` | Outcome or duration keys missing, or null outcomes | agentdojo (1), agentdyn (12) | |
| `provider_call_id_anomalies` | `""` (Gemini), absent (Cohere), `null` (local, Gemini native, SecAlign, CaMeL), client-random (Llama prompting), seeded-random reused across traces (DRIFT), duplicates (GPT) | all | [sources/agentdojo.md §3.5], [sources/drift.md §3.4] |
| `system_prompt_variant` | AgentDojo default; plus the auto-complete line (AgentDyn A, ROPE); Progent without the line; DRIFT no system; spotlighting modified | per profile | [verify/rope.md §3], [sources/agentdyn.md §4.4] |
| `rope_guard_denial` | Denial only as a tool `error`; reason not logged; two text variants | rope, autodojo-via-rope | [sources/rope.md §3.4] |
| `progent_denial` | `ValidationError: The tool '…' is not allowed..` | agentdyn | [sources/agentdyn.md §3.8] |
| `mandate_decline` | `content == error == "MANDATE_DECLINE: …"`; tool not executed | mandate | [sources/mandate-agentdojo-eval.md §3] |
| `pi_detector_redaction` | Content replaced by the sentinel; raw output overwritten (`unk overwritten`) | agentdojo, agentdyn | [sources/agentdojo.md §3.5], [sources/agentdyn.md §3.8] |
| `tool_filter_aux_llm` | An extra `user` (filter prompt) plus a tool-free `assistant` (filter output) | agentdojo, agentdyn | [sources/agentdojo-inspect.md §4.6] |
| `repeat_user_prompt_reinsertion` | User prompt re-inserted after each tool round | agentdojo, agentdyn | |
| `spotlighting_delimiters` | Output wrapped in `<<…>>`; system prompt modified | agentdojo, agentdyn | |
| `args_mutated_in_place` | Logged args are post-normalisation | v1.k14 producers | [sources/agentdojo.md §3.5] |
| `unexecuted_trailing_calls` | `max_iters=15` cut | all | |
| `pipeline_name_not_identity` | `local`, `openai-compatible`, ROPE config tags, AgentDyn progent/drift directories | agentdojo, rope, agentdyn, survey | |
| `package_version_not_code_identity` | `0.1.35` or `unknown` from `importlib.metadata` | all v1.k14 | [verify/rope.md §3] |
| `benchmark_version_label_not_suite_version` | AgentDyn suites registered under every version | agentdyn, rope, drift | [sources/agentdyn.md §3.2] |
| `local_model_raw_completion` | Raw completion with `<function=…>` tags; possible parse drops | agentdojo | [sources/agentdojo.md §3.5] |
| `camel_orphan_tool_results` | Interpreter tool messages without assistant calls | agentdyn | |
| `drift_integrated_user_error_key` | `user` message with an `error` key (validator feedback) | agentdyn | |
| `drift_*` (see the DRIFT profile) | Isolation in place, re-serialised assistant text, CALL ERROR as `user`, calls in text not executed, no system message, no injections, plan-field semantics by commit | drift, agentdyn C | [verify/drift.md] |
| `generation_mixing_per_file` | Mixed re-run generations within one pipeline directory | agentdojo | [verify/agentdojo.md §5.3] |
| `rope_effect_correction` | ROPE's released effect-based corrections apply to three injection tasks (recomputed judgements, §D.4.4) | rope | [sources/rope.md §3.6] |
| `placeholder_args_never_injection_evidence` | Key present but always null | agentdojo, rope, agentdyn, survey | [audit/capture.md §8 D1] |

### D.6.5 Mapping to AER: emission algorithm (`TraceLoggerMapper.map`)

The output is one AER per file. The mapper emits C's fields only (C.3 is the contract; R-02). Records are emitted in
this order. Local ids follow C.4.2 and are positional only. [R-02, R-22, R-32, R-28]

**Step 1. `execution` header (id `exec`).**

| Field | Content |
|---|---|
| `mode` | `"import"` |
| `ex` | computed by core: `agentprov.aer.ids.import_execution_id("agentdojo.tracelogger/<profile id>", sha256, {"p": ""})` (AD-04). KAT: the C.16.1 artefact under `agentdojo.tracelogger/agentdojo-upstream` gives `ex_7uz2oys57hugtsueixylme4fl5` |
| `source_key` | `{"sha256": <hex>, "loc": {"p": ""}}` (C.3.1; register and index use the string `"sha256:<hex>#{\"p\":\"\"}"`) |
| `artifacts` | `[a0]`: role `primary`, one `origin` (the pinned git blob; further locations are `raw/origins.jsonl` rows), `prov_primary: "native"` for TraceLogger logs fetched from the publisher's pinned commit or DOI, otherwise `"unknown"` (R-22) |
| `adapter` | `{"id": "agentdojo.tracelogger", "version": "0.1.0"}` (no code digest; code identity is in the corpus manifest, RF-4) |
| `dialect` | `{"id": "agentdojo.tracelogger", "variant": "v0.k11" \| "v1.k14" \| "v1.k14.incomplete" \| "drift.k18.messages" \| "drift.k18.conversations"}` |
| `profile` | `{"id", "version": <int>, "sha256"}` (AD-03 R-3) |
| `rules` | `{"agentdojo": 1, "aer": 1, …}`: every catalogue cited in the file |
| `ns` | the prefixes the mapper may emit |
| `task` | see below |
| `unit` | `"agent_execution"`; `"outcome_only"` when `messages == []` (R-28) |
| `instrumentation` | `unk {"/instrumentation": "not_recorded"}` unless the profile knows the harness (C.3.1) |

`task` holds:
- `benchmark` from `[family.agentdojo.benchmark] suites[suite_name]`;
- `suite = suite_name`;
- `task_id = user_task_id`;
- `attack_id = attack_type` (null if benign);
- `attack_target_id = injection_task_id` (the DoS placeholder is kept verbatim; quirk `dos_security_not_utility`);
- `defense_id` from identity.

The benchmark version label is **not** a task field (AD-03 R-9 rejected): the verbatim `benchmark_version` (v1.k14)
is the `bench` actor's `version` (O by source); its meaning is the profile's `version_label_semantics`, and the
benchmark identity, when known, is the `bench` actor's `code`. When absent (`v0.k11`), `bench` gets
`unk {"/version": "not_recorded"}` and the candidate era is `ext.agentdojo.benchmark_era` (I,
`agentdojo.benchmark_era_from_commit@1`).

`ext.agentdojo` holds `format_variant`, `top_level_keys`, `pipeline_name`, `pipeline_dir`, `path`, `error` (run
error verbatim), `task_kind`, `committed_no_later_than` (D) and `extra`. Verbatim copies of source fields whose
meaning is captured in core are allowed because they are distinct facts (C.10 item 4); `ext` never duplicates a core
slot.

`task_kind` ∈ `user_task | injection_task_as_user_task | attacked | dos`, decided by
`agentdojo.injection_task_as_user_task@1` and `dos_attacks`. A `none` run is **never** labelled "benign" when it
is a pre-pass [audit/legacy_replay.md §3.6 D6; verify/mandate-agentdojo-eval.md §4 item 3].

**Step 2. Actors, in fixed order** (only those that apply):

| id | kind | Basis |
|---|---|---|
| `bench` | `benchmark` | `name: "agentdojo"`; the checker and the supplier of the default system prompt; `agentdojo.benchmark_from_dialect@1` (D); `version` as in Step 1; for `v1.k14`, `code {dist: "agentdojo", dist_version: agentdojo_package_version}` (O by source; quirk `package_version_not_code_identity`) with `unk {"/code/commit": "not_recorded"}`; for `v0.k11`, `unk {"/code": "not_recorded", "/version": "not_recorded"}` (C.16.1) |
| `user` | `simulated_user` | `agentdojo.user_is_simulated@1` (D) |
| `agent` | `llm_agent` | `model.requested` from identity resolution, `evf {"/model": "I"}` with rule `agentdojo.pipeline_dir_is_model_identity@1` (or the profile's twin); the record keeps its existence class (A-3); `on_behalf_of: "user"` (`agentdojo.user_is_simulated@1`); `unk {"/model/served": "not_recorded", "/model/provider": "not_recorded", "/params": "not_recorded"}` |
| `env` | `tool_runtime` | `name: "agentdojo.FunctionsRuntime"`, `on_behalf_of: "agent"` (`agentdojo.functions_runtime@1`); `evf {"/on_behalf_of": "I"}` with `agentdojo.auto_execution_unverified@1#/on_behalf_of` (EF E.10 item 21) |
| `att` | `attacker` | iff `attack_type` is non-null; `name = attack_type` (O by config) |
| `def<n>` | `defense` | one per defence in the identity result, sorted by name, 0-based (`def0`, `def1`, …); `name` = the defence id (e.g. `transformers_pi_detector`); `agentdojo.defence_suffix@1` (I) |

If id style contradicts the resolved identity (`[family.agentdojo.identity] id_style_corroboration`), raise the issue
`identity_conflict` and keep both values in `ext`.

**Step 3. Scopes.**
- `run` (kind `run`):
  - `t.dur_s` from `duration`, `t.dur_clock: "wall"` (O by source; `agentdojo.duration_scope@1` gives its meaning:
    environment load, all passes and scoring);
  - for `v1.k14`, `t.start_naive` = `evaluation_timestamp` and `t.raw.start` verbatim, with
    `unk {"/t/start": "ambiguous", "/t/end": "not_recorded"}` (rule `agentdojo.naive_local_timestamp@1`, or its I
    twin `agentdojo.naive_local_timestamp_unverified@1` for profiles whose harness code is not verified, e.g. ROPE);
  - for `v0.k11` and `drift.*`, `unk {"/t/start": "not_recorded", "/t/end": "not_recorded"}`.
- `att0` (kind `attempt`, parent `run`, `actor: "agent"`, `scored: true`). Omitted when `messages` is empty.
  - Default: `unk {"/index": "lost"}`, rule `agentdojo.log_holds_last_pass@1`.
  - If the retry rule fires (final assistant content null, no run error; for AgentDyn, the last assistant message
    anywhere), set `index: 2` with `evf {"/index": "D"}`, rule `agentdojo.null_final_implies_three_passes@1`.
    Raise issues `retry_passes_inferred` and `earlier_attempts_unobservable`, and add
    `ext.agentdojo.pre_state_not_initial: true` [verify/rope.md §4].
  - DRIFT: `index: 0`, rule `drift.single_pass@1`, with no earlier-attempt issue.

**Step 4. Fixtures.** One `fixture` per `injections` entry, in source object order:
- `kind: "injection_payload"`, `vector`, `content` (O by `benchmark`);
- `actor: "att"` with `evf {"/actor": "I"}`, rule `agentdojo.payload_attributed_to_attacker@1`.
- `drift.*` has no injections map: emit no fixtures and raise `drift.injection_map_not_recorded`.
- **The environment load** (regeneration-batch item 5, C2; D-370): when there is at least one payload fixture, one
  generic `activity` `ac0` follows them: `type: "agentdojo:load_environment"` (declared in the `agentdojo` catalogue),
  `scope: "run"`, `actor: "bench"`, `inputs` the payload fixtures in order, `unk {"/t": "not_recorded"}`, under
  `agentdojo.environment_loaded_with_injections@1` (D; its `_unverified` twin where the producing code is not
  verified), each input tagged and cited (`/inputs/<i>`). The suite loads the environment with the logged injections
  before the passes (`task_suite.py`: `run_task_with_pipeline` → `load_and_inject_default_environment(injections)`),
  so the engine's `aprov.g_use@1` gives `used(x:ac0, x:fx<i>)`, `aprov.g_assoc@1` the association with `bench`, and
  the activity is `apv:partOf x:run`. aer/0.1 has no field for a scope's inputs, hence the generic activity. The
  transcript/v1 mapper does not write it: gate D requires 0 generic records in v1 migration AERs (J), so adprov's
  payload fixtures stay attribute-linked; gate D admits this one activity type in the native TraceLogger goldens
  (user decisions 2026-10-13).

**Step 5. Messages and activities, in source order.** For message index `i` (id `m<i>`), dispatch on role and
classification. The full table is in §D.6.6. The rules are:
- An activity record (`model_call`, `tool_execution`, `decision`) is emitted **immediately before** the message it
  generates. All references point backwards (C.5.2); there are no forward references (`output`, `result`,
  `replacement` and `spawns` do not exist).
- `after` edges:
  - `m<i>` after the previous message: `b: "pos"`, `evf {"/after": "D"}`, rule `agentdojo.messages_append_ordered@1`
    (`evf {"/after": "I"}` under its twin `agentdojo.messages_append_ordered_unverified@1` for the profiles of §D.5.4);
  - a generated message after its generator: `b: "causal"`;
  - `te<k+1>` after the tool message of `te<k>` in the same batch: `b: "pos"`, rule
    `agentdojo.tools_executed_sequentially@1`.

**Step 6. Judgements** (§D.6.7).

**Step 7.** The writer computes accounting and appends the `seal` (§D.6.9).

### D.6.6 Message-level mapping table

**Parts layout.** An assistant message's parts are:
1. content parts in block order:
   - `content: null` → one part `{t: "text", text: null}` (null is kept; the TR-1 rule [audit/capture.md §4.3]);
   - `""` → `{t: "text", text: ""}` with `unk {"/parts/<k>/text": "ambiguous"}` and
     `agentdojo.empty_assistant_text_ambiguous@1#/parts/<k>/text` (C.19 item 4; D.7.5 item 10; D.6.11 item 8);
   - `[]` → no content part;
   - a `thinking` block → `{t: "reasoning", text}` (O by source);
   - a `redacted_thinking` block → `{t: "reasoning", text: null, redacted: true}`;
2. then one `tool_call` part per call, in order: `{t: "tool_call", name, args, provider_call_id?}`, with
   `unk {"/parts/<k>/args_raw": "not_recorded"}` (TraceLogger never logs the encoded wire text). For `v1.k14` the
   logged `args` are post-normalisation (in-place `literal_eval`, quirk `args_mutated_in_place`): the message cites
   `agentdojo.args_are_effective@1` **unscoped**, because `args` is O by source and C.6.4 forbids a scoped rule on an
   O value (erratum E10; D.6.11 item 7).

The part index of call `j` is `n_content_parts + j`; its id is `m<i>#<k>`. Argument objects keep their source member
order and integral floats through `ext.lex` (§D.6.3).

**Row precedence.** For `tool` messages the rows below are evaluated top to bottom and the first match applies. The
PI sentinel, denial and decline patterns therefore precede the generic `ValidationError` and "other error" rows.
Which patterns are active is decided by the profile's quirks. A pattern from an undeclared quirk is never applied.

| Source situation | Records | Evidence and rules |
|---|---|---|
| `system` message | `m<i>` role `system`, actor `bench` | O by source; `evf {"/actor": "D"}`, `agentdojo.system_prompt_from_harness@1` (C.16.1); label `ext.agentdojo.system_prompt_variant` by sha256 match against the profile (D); an unknown digest gives info issue `agentdojo.system_prompt_unrecognised` |
| first `user` message | `m<i>` role `user`, actor `user` | `evf {"/actor": "D"}`, `agentdojo.user_is_simulated@1`; content role per `agentdojo.first_user_msg_is_task_prompt@1` (D) |
| later `user`, `-tool_filter` profile, first such message | `m<i>` actor = the `tool_filter` defence actor (`def<n>`, `name: "tool_filter"`) | I, `agentdojo.tool_filter_aux_message@1` |
| later `user` equal to the first, `-repeat_user_prompt` | `m<i>` actor = the `repeat_user_prompt` defence actor; `ext.agentdojo.copy_of: "m<first>"` | I, `agentdojo.repeat_user_prompt_copy@1` |
| `user` with an `error` key (AgentDyn) or a `[CALL ERROR]` wrapper (DRIFT) | `dc<n>` (actor = the `drift` defence actor, verdict `deny`, subject = the rejected `tool_call` part of the previous assistant message when one exists, else that message; `reason` with a locator to the text), then `m<i>` role `user` (role kept), actor = the `drift` defence actor, `generated_by: dc<n>`. The defence actor is stated so that J.4.4 can mirror defence-authored messages | D, `agentdyn.drift_user_error_key@1` / `drift.call_error_user_is_validator@1` |
| other later `user` | `m<i>` actor `user` | `evf {"/actor": "I"}`; issue `unattributed_additional_user_message` |
| `assistant` (agent) | `mc<n>` (actor `agent`, `role: "agent"`, `scope: "att0"`, `input` = all earlier message ids in the attempt, `status: "kept"`; `unk {"/request", "/response", "/usage", "/finish_reason", "/tools", "/t": "not_recorded"}`), then `m<i>` role `assistant`, actor `agent`, `generated_by: mc<n>` | `mc` ev D (`agentdojo.assistant_msg_has_one_call@1`), or I under its twin `agentdojo.assistant_msg_has_one_call_unverified@1` (§D.5.4); `evf {"/input": "I"}` (`agentdojo.context_is_prefix@1#/input`). DRIFT: `input` is replaced by `unk {"/input": "not_recorded"}` because the real prompt is not logged [sources/drift.md §5.2]; issue `drift.agent_prompt_not_recorded` |
| `assistant` immediately after a tool-filter prompt, with no calls | `mc<n>` (actor = the `tool_filter` defence actor, `role: "auxiliary"`), then `m<i>` (actor = the same defence actor). No split list is emitted: at `c274885` the filter keeps every tool whose name occurs in the output text, a substring rule, and the resulting tool set is not logged (D.6.11 item 10) | I, `agentdojo.tool_filter_aux_message@1`. No `decision` is emitted: the restricted tool set offered to the agent is not recorded |
| assistant text with `<function=` tags (local models) | as for the agent; `ext.agentdojo.local_model_tag_count` | if tags > parsed calls: issue `agentdojo.local_parse_drop_possible` (I, `agentdojo.local_model_tag_count@1`) |
| `tool` message, `error: null`, content ≠ PI sentinel | `te<k>` (actor `env`, `scope: "att0"`, `call: "m<a>#<p>"`, `name`, `args` = the call's logged args (O), `status: "ok"`; `v1.k14`: `args_effective` = the same value (D, `agentdojo.args_are_effective@1`); `v0.k11`: `unk {"/args_effective": "not_recorded"}`; `unk {"/returned": "not_recorded", "/t": "not_recorded"}`), then `m<i>` role `tool`, actor `env`, `generated_by: te<k>`, part `{t: "tool_result", responds_to, text, error: null}` | `te` ev D (`agentdojo.tool_msg_is_one_execution@1`), or I under its twin `agentdojo.tool_msg_is_one_execution_unverified@1` (§D.5.4); status D (`agentdojo.tool_status_from_error@1#/status`); link per §D.6.6.1; spotlighting: `ext.agentdojo.content_state = "post_defence"` (I, `agentdojo.spotlighting_content@1`) |
| `tool`, content == PI sentinel | `te<k>` (`status: "ok"`), `dc<n>` (actor = the `transformers_pi_detector` defence actor, verdict `redact`, subject `te<k>`, `unk {"/original": "overwritten", "/reason": "not_recorded"}`), then `m<i>` with `generated_by: dc<n>`, actor = the defence actor (`evf {"/actor": "I", "/generated_by": "I"}`) | I, `agentdojo.pi_detector_sentinel@1` (C.16.1) |
| `tool`, error matches `rope.denial` / `progent_denial` | **no** `tool_execution` (a denial is a `decision` only, AD-03); `dc<n>` (actor = the `rope` or `progent` defence actor, verdict `deny`, subject = the `tool_call` part, `unk {"/reason": "not_recorded"}`, `ext.rope.query_echo` ∈ `none`/`query`), then `m<i>` with `generated_by: dc<n>` and the denial text as the `tool_result` | I, `rope.denial_error_pattern@1` / `agentdyn.progent_denial_pattern@1` [landscape/trace_formats.md §6.6] |
| `tool`, `content == error`, `MANDATE_DECLINE:` prefix | **no** `tool_execution`; `dc<n>` (actor = the `mandate` defence actor, verdict `deny`, subject = the `tool_call` part, `reason` with a locator), then `m<i>` with `generated_by: dc<n>`. In `mandate_*` pipelines, a gated call without a decline gets `ext.mandate.gate = "allow"` (I) on its `te` | D, `mandate.decline_prefix@1`; I, `mandate.allow_inferred@1`. This addresses the baseline defect "declined call rendered as executed sink" [verify/mandate-agentdojo-eval.md §3.7] |
| `tool`, error `Empty function name provided…` or `Invalid tool <x> provided.` | `te<k>` `status: "invalid"` (the runtime rejected the call; it generates the error message) | D, `agentdojo.tool_status_from_error@1` (executor code) |
| `tool`, error starts `ValidationError:` (not a denial) | `te<k>` `status: "invalid"` | D, `agentdojo.tool_status_from_error@1` (`functions_runtime.run_function` returns before calling the tool [audit/capture.md §3]) |
| `tool`, any other error | `te<k>` `status: "error"` | D, `agentdojo.tool_status_from_error@1` |
| `tool` message without a matching call (CaMeL) | `te<k>` with no `call` and `requested_by` = the `camel` defence actor (`evf {"/requested_by": "I"}`); `m<i>` part `tool_result` with `unk {"/parts/0/responds_to": "not_recorded"}` | I, `agentdyn.camel_orphan_tool_result@1`; issue `orphan_tool_result` (info for CaMeL directories, warning elsewhere) |
| `tool`, error is a defence's stated denial text (quirk `defence_denial_message`) | **no** `tool_execution`; `dc<n>` (actor = that defence actor, verdict `deny`, subject = the `tool_call` part, `reason` = the error with a locator), then `m<i>` with `generated_by: dc<n>` | I, `agentdojo.defence_denial_message@1` (R1, D-113) |
| log ends at executed tool messages, defence a declared aborting detector (quirk `detector_abort`) | after the messages, `dc<n>` (actor = the detector, verdict `terminate`, subject = the single trailing `te<k>`, or the request message when the last turn has several outputs, with info issue `agentdojo.detector_abort_output_unrecorded`; `unk {"/reason", "/t": "not_recorded"}`); hook point `log_end` | I, `agentdojo.detector_abort_after_output@1` (R10, D-116) |
| calls in the last assistant message without tool messages | no `te` | issue `unexecuted_tool_call` (ids = the call parts), rule `agentdojo.unexecuted_trailing_calls@1`. The same situation in a non-final message gives `missing_tool_result` (error) |
| DRIFT re-serialised assistant with a non-empty `<function_call>` body and empty `tool_calls` | as for the agent | issue `drift.calls_in_text_not_executed` (D). Proposed calls are **not** re-parsed into `tool_call` parts in v0.1 (that rule id is reserved) |
| `messages == []` | `unit: "outcome_only"`; no `att0`, messages, `mc` or `te` | issue `no_execution_observed`; judgements still emitted |
| unknown role or keys | `m<i>` with role kept verbatim and part `{t: "other", type: "agentdojo.unknown_message", value}` holding the raw value | issue `agentdojo.unknown_message_shape` |

**D.6.6.1 Call-to-result linking.** For assistant message `A` with calls `c_0…c_{n-1}`, followed by contiguous tool
messages `T_0…T_{k-1}`:
1. If every `c_j.id` is a non-empty string unique within the batch, and each `T_i.tool_call_id` equals exactly one
   `c_j.id`: link by id, `evf {"/parts/0/responds_to": "D"}`, rule `agentdojo.call_id_unique_match@1`.
2. Otherwise pair `T_i` with `c_i` for `i < min(n, k)` **only if** `T_i.tool_call.function == c_i.function` and the
   two `args` values are equal as JCS values with their `ext.lex` hints. This uses `agentdojo.positional_match@1`
   (I). On disagreement, no link is made: `responds_to` goes to `unk {"…/responds_to": "ambiguous"}`, the
   execution's `call` to `unk {"/call": "ambiguous"}` (AD-03 R-7), and the issue `call_result_link_conflict` is
   raised.
3. `provider_call_id` is the verbatim id:
   - `""` gets `unk {"…/provider_call_id": "ambiguous"}`;
   - an absent key is omitted and gets `unk not_recorded`;
   - a source `null` is kept as `null`.
   Ids are never local ids (C.4.4).

### D.6.7 Judgements and outcome origin

Two `judgement` records are emitted, `j0` (utility) and `j1` (security), actor `bench`, `subject: "run"`, value from
the source (O by `benchmark`). A judgement carries **no polarity or meaning** (C.3.10): what `security = true` means
(the injection task succeeded, `agentdojo.security_polarity@1`) is a SEM `outcome` annotation of the
`agentdojo.suites` semantics profile. The `origin` (C's enum) is decided in this order, first match wins
[R-02, R-13, R-37]:

| Condition | `origin` | Rule / issue |
|---|---|---|
| run-level `error` non-null (any producer) | `harness_default` (both judgements) | the profile's `run_error_imposes_outcome` rule (`agentdojo.run_error_imposed_outcome@1`, `agentdyn.json_decode_error_imposed@1`, `survey.internal_server_error_patch@1`); issue `outcome_imposed_by_runner` |
| security under `attack_type is null` | `harness_default` | `agentdojo.benign_security_constant@1` (the constant is not an observation) |
| security under a DoS attack | `harness_rule` | `agentdojo.dos_security_rule@1` |
| otherwise | `checker` | `agentdojo.checker_outcome@1`; plus `unk {"/inputs": "not_recorded"}` and `agentdojo.checker_inputs_unverified@1#/inputs` (EF E.10 item 21; the transcript/v1 importer does the same for `adprov.checker_outcome@1`) |

- The finer cases of the first revision (`runner_default_error`, `runner_default_benign`, `runner_rule_dos`) are
  expressed by these rule ids, not by an `ext.agentdojo.outcome_origin` field (deleted), and there is no core
  `valid` or `meaning` field.
- The utility of an `injection_task_as_user_task` run has origin `checker`; that it scores the injection goal as a
  user task is SEM's reading of `ext.agentdojo.task_kind`.
- A source `null` outcome (AgentDyn) is kept as `value: null` with the issue `incomplete_run`.
- A missing outcome key produces no judgement, and the issue `incomplete_run` (or `no_outcome_recorded`).
- **Recomputations.** Recomputations **released by a source** are AER `judgement`s beside the recorded one, with
  `origin: "recomputed"`, `by: "source"` and `revises` pointing at it (C.3.10), e.g. ROPE's effect-based corrections
  (`rope.security_correction@1`, §D.4.4). **AgentPROV's own re-scorings** (AgentDojo-PROV v2.3 scoring, outcome
  replay) are not AER; replay is deferred (AD-10) [sources/rope.md §3.6; audit/legacy_replay.md §9].

### D.6.8 Ordering and time (summary)

- Order comes only from `after` edges (§D.6.5). The file order of AER lines is not an occurrence claim (C.8.1).
- No per-message or per-call time exists in any TraceLogger variant. The mapper MUST NOT derive one, in particular
  not from environment-generated timestamps embedded in tool outputs, such as DRIFT `send_email` stamps
  [verify/drift.md §3]. Those are content and may only be interpreted in SEM.
- `committed_no_later_than` (from the git origin's `introduced_in_commit`) is `ext` only and never a PROV time.

### D.6.9 Accounting

Accounting is computed **once**, on the AER side, by `agentprov.aer.accounting` when the writer seals the file, and
recomputed by the validator (C.12; R-13). The mapper does not count. For TraceLogger imports the applicable checks
are `aer.acc.agent_calls_vs_assistant@1` (recorded `unverifiable` with reason `model_calls_derived_from_messages`,
because the calls are derived from the messages), `aer.acc.tool_calls_dispatched@1` (every `tool_call` part has
exactly one of a `tool_execution`, a `deny` decision or an `unexecuted_tool_call` listing),
`aer.acc.tool_results_linked@1`, `aer.acc.executions_have_results@1` and `aer.acc.assistant_generated_by@1`. An
`inconsistent` verdict raises `accounting_inconsistent`; an `unverifiable` one `accounting_unverifiable`
[landscape/trace_formats.md §6.16 item 7].

### D.6.10 Tests (normative minimum)

`tests/adapters/agentdojo/` (paths per K.3.1; fixtures under `tests/fixtures/`, licence classes per K.4.2, marked
`binary` in `.gitattributes`):
1. **Golden AER.** One fixture per sample file in `investigation/samples/{agentdojo, rope, agentdyn, drift,
   mandate-agentdojo-eval, agent-security-tools-survey, autodojo, agentdojo-inspect}/` (each with `SOURCE.json`).
   The expected `.aer.jsonl` is checked in and compared **byte for byte** (never with Python `==`). Golden helpers
   report the line number, JSON Pointer and both sha256 values; any excerpt goes through `escape_untrusted` (R-42).
2. **KAT.** The C.16.1 artefact maps to `ex_7uz2oys57hugtsueixylme4fl5` (AD-04), identical to C.4.1 and K.5.2.
3. **Profile census (opt-in, local).** Run over a pinned snapshot and assert every `observed` count in every profile
   (e.g. 82 retry-inferred AgentDojo logs, 322 ROPE, 12,657 ROPE denials, 240 Mandate declines, 207 empty logs).
   The full-snapshot run is also the evidence for the `supported` gate (§D.3.2); its counts go to `docs/reports/`.
4. **Hypothesis property tests on the reader.**
   - Arbitrary key orders, content forms and id forms classify consistently.
   - Mutation fuzzing never raises anything except `MalformedArtefact` or `IngestError`.
5. **Determinism.** Map twice; the AER bytes are equal.
6. **Rules.** Each rule's `tests` entry exists and exercises it; every assumption's verification `test` exists.
7. **Lexical hints.** Argument objects in non-sorted member order and integral floats round-trip through `ext.lex`
   (A1 JCS and A2 bytes on the golden converted pairs, §D.7.4).
8. **Import boundary.** Covered by `tests/boundary/test_import_boundary.py` (§D.2.1); no `agentdojo` import exists in
   core at all.

### D.6.11 Implementation resolutions (phase 6)

The code is the reference (`agentprov.adapters.agentdojo`: `dialect`, `mapper`, `identity`, `profile`;
`agentprov.views.transcript_v1.render_converted`). Phase 6 maps variant `v0.k11` (the `2024-06` pin); `v1.k14` and
the `head` part are phase 10.

**Gates and numbers.**
- C.16.1 is reproduced byte for byte by the shipped mapper and the shipped profile
  (`tests/adapters/agentdojo/test_mapper.py::test_c16_1_vector_is_reproduced`). Erratum E22 is resolved: the vector
  now carries the shipped profile digest `9d77aefe…aa95` (it carried a stand-in digest), so its execution digest is
  `fb2e804e…9de3`; the KAT `ex_7uz2oys57hugtsueixylme4fl5` is unchanged. `tools/agentdojo/regen_c161.py` regenerates
  the vector and its C.16 rows; the prototype `examples/C/gen_examples.py` produces the same bytes.
- Gate R golden: R1 and R2 pass on C01–C09 from N-C01–N-C09 (`tests/golden/test_render_converted.py`, bytes).
- Full import of the `2024-06` pin (`tools/agentdojo/import_scan.py`; `docs/reports/agentdojo/`): all 18,241 blobs
  (188,873,874 bytes, the 7 Mixtral logs included) are sealed with 0 crashes and 0 degenerate AERs, all `v0.k11`;
  207 are `outcome_only`. Every AER passes the validator in release mode and derives with `agentprov-prov/0.1`, and
  every PROV document passes `validate_prov`. Seal issues: `earlier_attempts_unobservable` 18,034,
  `accounting_unverifiable` 18,008, `no_execution_observed` 207, `unexecuted_tool_call` 145 logs (153 calls),
  `outcome_imposed_by_runner` 106, `retry_passes_inferred` 47, `incomplete_run` 4; no adapter issue code fired.
- Gate R in full: R1 18,027/18,027 and R2 18,027/18,027 in bytes, so the claim gate of D.7.4 passes; R4 207/207 rows
  of `EXCLUDED.json` equal; R5 native-only is exactly the 7 Mixtral logs and v1-only is empty. The registry still
  shows `agentdojo` · `2024-06` as `planned` with a caveat: raising it is the coordinator's decision once the gates
  are recorded (D.3.2 rule 1).

**Resolutions.**
1. **Variants.** The reader recognises every D.6.2 variant. The mapper maps `v0.k11` and raises `UnsupportedVariant`
   for the others, so such a file is sealed as a degenerate AER with `unsupported_variant` (D.2.8 case 3). A
   recognised object without a structural key is yielded by `parse` with the flag `malformed:missing_structural_keys`,
   and the mapper raises `MalformedArtefact` (`unparseable_artefact`): the file is sealed, not registered. The degenerate
   issue cites `agentdojo.tracelogger_record_shape@1`.
2. **Header `ext.agentdojo`.** Always `pipeline_name` and `error` (as C.16.1); `task_kind` only for
   `injection_task_as_user_task` (`agentdojo.injection_task_as_user_task@1`) and `dos`
   (`agentdojo.dos_placeholder_injection_task@1`: the attack target is a placeholder); `extra` when present. Not
   written: `format_variant` (it is `dialect.variant`), `path` and `pipeline_dir` (they are `artifacts[0].origin.path`;
   `ext` never duplicates a core slot), `top_level_keys` (key order carries no semantics, D.6.2; C.16.1 omits it),
   `committed_no_later_than` and `benchmark_era` (both need the commit that introduced the blob, which a depth-1 pinned
   store cannot give; they are written when the origin carries the commit, D.6.16). The `bench` actor keeps `unk /code`
   and `/version`.
3. **No verified assumptions.** No `agentdojo` rule declares a `verified` assumption: AER-V34 requires the framework
   identity in the AER, and June-2024 logs record none. `agentdojo.log_holds_last_pass@1` is therefore declared without
   `apv:LastPassOnlyLogging` (D.5.2 shows it verified over a code range). Verifying a code range needs the core
   validator to accept a code bound (D.5.2 last paragraph); until then the D class rests on the cited code only.
4. **`prov_primary`.** `Mapper.prov_primary(flags)` sees only sniff flags, so it returns `unknown` (fail closed), and
   the mapper sets `native` in the header when the origin is one of the profile's pins (a git commit of the canonical
   repository, or a pinned DOI).
5. **Identity.** Two rows join the identity table for the together.ai models of the June-2024 code
   (`meta-llama_Llama-3-70b-chat-hf`, `mistralai_Mixtral-8x7B-Instruct-v0.1`): `ModelsEnum` gives the model id and
   `TraceLogger.save` replaces `/` by `_`. Defence suffixes are stripped right to left and sorted by name; actors are
   `def<n>` with `name` (erratum E6: D wins; J.4.4 and J.3.5 aligned). No run directory (an origin without the layout)
   gives `identity_unresolved`, `unk /model` on the agent and `unk /task/defense_id: not_recorded`; more than one
   defence gives `/task/defense_id: ambiguous`. `id_style_corroboration` is evaluated only for rows with a `provider`
   (none at `2024-06`).
6. **Path agreement (R-PATH).** `parse` receives no profile, so the mapper checks the layout components of the origin
   path against the fields, under the new D rule `agentdojo.log_path_layout@1` (`logging.py` l. 239-255 at `c274885`):
   `agentdojo.path_field_mismatch`, detail the field name, never a correction.
7. **Erratum E10.** `agentdojo.args_are_effective@1` justifies the post-normalisation reading of `v1.k14` args, which are
   O by source: the message cites it unscoped, and the execution's `args_effective` cites it at `/args_effective`
   (phase 10). D.6.6 is aligned.
8. **`""` assistant text** (D.7.5 item 10, second bullet; C.19 item 4). The part keeps `""` and declares
   `unk {"/parts/<k>/text": "ambiguous"}` under the new D rule `agentdojo.empty_assistant_text_ambiguous@1`, as adprov
   does with `adprov.empty_assistant_text_ambiguous@1`. D.6.6 is aligned.
9. **System-prompt variants.** The profile declares none in v0.1 (the only D.4.3 source, `a75aba76`, is head code,
   pinned with the head part in phase 10; the June-2024 code is unpinned). With none declared the mapper neither labels
   nor flags a system prompt; the text is kept verbatim. C.16.1 has neither a label nor an issue.
   *Superseded by D-207 (regeneration-batch item 17, 2026-10-12):* the profile now labels the `v0.k11` system prompts
   by digest (D.6.12 item 6); C.16.1's system message carries `agentdojo_default`.
10. **Tool filter.** At `c274885` `OpenAILLMToolFilter` keeps every tool whose name occurs in the output text (a
    substring rule) and the resulting tool set is not logged, so no split list is emitted (D.6.6 aligned). The filter
    prompt (`user`) and the filter output (`assistant`) get the `tool_filter` defence actor; the filter's model call
    has `role: "auxiliary"`, that actor, and `ev: I`.
11. **Call-to-result linking (D.6.6.1)** is decided per batch: the id rule needs every call id non-empty and unique and
    every result id distinct and equal to one call id; otherwise positional with the echo check (function and args
    equal with member order and int/float form). The embedded `tool_call` gives the execution's `name` and `args`
    (`src` cites it). A tool message records its own `tool_call_id` in `ext.agentdojo.tool_call_id` whenever it is not
    the linked call's `provider_call_id` (an ambiguous link, an absent call id); it is the converter's field. The
    second and later executions of a batch are `after` the previous result (`b: "pos"`,
    `agentdojo.tools_executed_sequentially@1`); an unlinked execution has no causal edge. A result without a call is an
    execution with `unk /call: ambiguous` and `orphan_tool_result`.
12. **"No calls" encoding.** `ext.agentdojo.calls_form` is `empty_list` for `tool_calls: []` and `absent` for a missing
    key; `null`, the `v0.k11` form, and non-empty lists record nothing.
13. **Outcomes.** A missing outcome key gives no judgement and `incomplete_run` (ids `run`); `no_outcome_recorded` is
    used only when there is neither a message nor a judgement. A run without `duration` keeps the run scope with
    `src {"p": ""}` and `unk /t`. The D.6.7 origin order is applied as written.
14. **Retry rule.** It fires when the final message is an assistant message with `content: null` and the run has no
    error, and when the profile declares `agentdojo.silent_rerun_last_pass_only` for the file. `att0` gets `index: 2`
    with `agentdojo.null_final_implies_three_passes@1` scoped to `/index` and to
    `/ext/agentdojo/pre_state_not_initial`; both seal issues cite that rule. J.2.4's C07 row is superseded: C07's final
    assistant content is null with no run error, so its native AER records the inferred passes (the rule is D from the
    retry loop at `c274885`, `task_suite.py` l. 264-279), whatever replay said.
15. **Quirk application.** The pattern rows of D.6.6 (PI sentinel, tool filter, repeat-user-prompt copy, spotlighting)
    and the retry rule apply only where the profile declares the quirk for the file's facets (`pipeline_dir`,
    `attack_dir`, `task_dir` from the layout, else from the fields; `variant`). A quirk seen in the data but not
    declared gives `agentdojo.undeclared_quirk` (detail: the quirk id) and is not applied. The D.6.7 origin rules always
    apply.
16. **Structural I twins.** *Superseded by regeneration-batch item 3:* `structural_rule_class` is replaced by
    `[family.agentdojo.harness] verified_code`, which selects the D rule or its `_unverified` twin for every D rule of the
    family, per profile, record facets and catalogue version (§D.5.4 "Citation of D rules"). The fields the rules justify
    take their class (C.6.5 rule 1).
17. **Catalogue.** Every D.5.4 `agentdojo.*` rule is declared, at its class, with code citations at `c274885` where the
    June-2024 code shows the behaviour. Added in phase 6: `tracelogger_record_shape`, `log_path_layout`,
    `additional_user_message_unattributed` (I) and `empty_assistant_text_ambiguous`; `record_complete_with_replay` and
    the five phase-7 semantics names of item 20 are `reserved`. The catalogue stays version 1 (nothing released); because its bytes changed, the `agentdojo` catalogue
    digest inside the golden PROV-JSON changed and `tests/golden/prov_digests.json` was regenerated (no statement
    changed).
18. **Profile.** `observed` counts are keyed by part (`{"2024-06" = {…}, head = {…}}`); the `2024-06` counts are the
    full import's and a full-corpus test asserts them (D.6.10 item 3); the `head` counts are the investigation's,
    unverified until phase 10. `[import] rules = {aer = 1, agentdojo = 1}` is the J.4.1 catalogue pin, test-checked
    against the shipped catalogues. The `2024-06` pin records `tree_sha1` and the measured `expected_bytes`. The
    `[family.agentdojo]` part is checked against `family.schema.json` by a stdlib subset of JSON Schema and, in the
    tests, by `jsonschema`. `ext.agentdojo` follows `ext.schema.json` (test-checked).
19. **`render_converted`** (J.4.3) re-applies the converter's rules inside the view: the `"0"` timing stub (erratum E8),
    `"benign"`, `round(duration, 3)`, `model = model_id = pipeline_name`, `run_error` only when non-null, the tool turn
    from the embedded call (`ext.agentdojo.tool_call_id` when present), and a message kept verbatim as
    `agentdojo.unknown_message` through a port of `transcript.message_to_turn`. It reads nothing from raw.
20. **Artefact catalogue.** `artefacts.toml` (`version = 1`, `family = "agentdojo"`) holds the 19 D.15.5 entries in
    the shared layer's format (D.15.2 fields, `recorded_as` as a table, `claims` of generic detector hits) and one entry
    found by the full import, `agentdojo.art.calls_derived_from_messages` (NR: TraceLogger records no model call, so
    `aer.acc.agent_calls_vs_assistant@1` is unverifiable in 18,008 logs). Of the five phase-7 semantics rules the
    entries name, `injection_marker_yaml` is active (phase 7), `scoring` (`@1`, `@2`), `account_confound` and
    `unwinnable_cell` are active as the library scoring rule set of gate C3 and its verdict reasons (regeneration-batch
    item 19, D-18 addendum; never emitted in a record), and `text_tool_call` stays `reserved`. `expected` rows measured by the full import are `verified`; the D.15.5 seed counts
    over the baseline copy stay `unverified`.

### D.6.12 Implementation resolutions (phase 10, `v1.k14` and shared profile machinery)

The code is the reference (`agentprov.adapters.agentdojo`: `mapper`, `layout`, `identity`, `profile`, `quirks`,
`census`, `hooks/`; `agentprov.adapters.profiles`; `agentprov.adapters.runner`). Phase 10 wave 1 maps `v1.k14` for
imports, builds the profile machinery the wave-2 profiles (`rope`, `autodojo-via-rope`, `agentdyn`, `mandate-agentdojo-eval`,
`survey-runs`) need, and imports the `head` part of `agentdojo-upstream`. D.6.11 item 1 is superseded as stated below.

**Variants and the `v1.k14` mapping (D.6.5-D.6.7).**
1. **Which variants map.** The mapper maps `v0.k11`, `v1.k14` and `v1.k14.incomplete` wherever the profile declares
   them: `[import] variants`, or the `[import] native.variants` of a live profile (D.10.4a). Any other recognised variant
   (`drift.k18.*`, `pre_v0`), and a mapped variant the profile does not declare, raises `UnsupportedVariant` and seals
   degenerate (D.2.8 case 3). The live-versus-native check is unchanged: the native mapping under `agentdojo-live` and
   `autodojo-live` gives the same records as in phase 8 (only facts keyed on profile data those profiles do not declare
   were added), and every capture fixture still agrees with its native log.
2. **Version fields.** `benchmark_version` is the `bench` actor's `version` verbatim (O by source).
   `agentdojo_package_version` is `code {dist: "agentdojo", dist_version}` (O by source, `/code/dist` D, `unk
   {"/code/commit": "not_recorded"}`); the value `unknown` (`PackageNotFoundError` at `logging.py` l. 176-181 @089ed468) is
   a C.7.3 sentinel, so `code` is omitted with `unk {"/code": "not_recorded"}`: all 11,765 head `v1.k14` logs, declared by
   the quirk `agentdojo.package_version_not_code_identity`. `evaluation_timestamp` gives `t.start_naive` (`T` separator) and
   `t.raw.start` verbatim, `unk {"/t/start": "ambiguous", "/t/end": "not_recorded"}`, under
   `agentdojo.naive_local_timestamp@1` or, where the profile's `verified_code` does not cite `089ed468` for the log, its twin
   `agentdojo.naive_local_timestamp_unverified@1` (fixed per profile, D.5.4 "I twins"; the rule now cites `logging.py`
   l. 173-174 @089ed468).
3. **The incomplete variant.** A `v1.k14` object without `duration` or outcome keys is `v1.k14.incomplete`: no judgement
   for a missing key and the issue `incomplete_run` (`agentdojo.incomplete_run@1`; D.6.11 item 13); the run scope keeps
   the timestamp. The head part has one such log (its last message is a user message: the pass crashed before scoring).
   `agentdojo.args_mutated_in_place` now applies to both `v1.k14` variants in `agentdojo-upstream`, as in the live
   profiles.
4. **Arguments and outputs.** The `v1.k14` rows of D.6.6 are as phase 8 built them: the message cites
   `agentdojo.args_are_effective@1` unscoped, the execution carries `args_effective` = the logged args (D); a tool result
   that is one text block is the part's `text`, any other list is `value` with the info issue
   `agentdojo.multi_block_tool_content`. The retry rule reads the final message (`model_output_from_messages`, l. 70-75
   and l. 383-394 @089ed468): content blocks are never null, so it fires for no head `v1.k14` log (82 `v0.k11` logs).
5. **Benchmark and version label (D.4.4 `version_label_semantics`).** `task.benchmark` and the `bench` actor's `name`
   are `[benchmark] suites[suite]`, else `benchmark` (the actor's name was the constant `agentdojo` before; equal for
   every existing profile). The label stays verbatim; where it is not the suite version — `label_not_suite_version`,
   `cli_default_not_suite_version`, or `suite_version_for_agentdojo_suites_only` for a suite whose benchmark is not
   `agentdojo` — the actor carries `ext.agentdojo.version_label_semantics` with `evf` I and the new rule
   `agentdojo.version_label_semantics@1` (I), and `agentdojo.suites@1` then selects tool tables as for an unrecorded label
   (the intersection, fail-closed) with that pointer as a premise. `suite_version` writes nothing (byte-identical).
6. **System-prompt variants (D.6.6 system row; D.6.11 item 9).** An entry is `{label, source?, key?, sha256?, note?,
   applies?}` (`applies` a facet selector; D.4.4's prose `applies` strings become selectors). The text of message 0 (a
   string, or the texts of text blocks joined by a newline, `get_text_content_as_str`) is hashed; a variant applying to
   the file whose `sha256` matches gives `ext.agentdojo.system_prompt_variant` (D, new rule
   `agentdojo.system_prompt_variant_digest@1`), none gives the info issue `agentdojo.system_prompt_unrecognised`, and with
   no variant applying nothing is labelled or flagged. `agentdojo-upstream` pins `agentdojo_default`: the `default` value
   of `src/agentdojo/data/system_messages.yaml` at the head pin `089ed468` (read with the safe loader; 469 characters,
   SHA-256 `a021a92b…1837`), applied to the `v1.k14` variants and, since D-207 (regen-batch item 17), to `v0.k11`. Phases
   6 and 10 left the `v0.k11` logs unlabelled because no pin covered the code that wrote them; the full history (deferrals
   part B) shows one code state of that text at all 547 commits that carry the file, and the rule is code-independent
   (D.5.4), so the label is a fact about the text. The `spotlighting_with_delimiting` run directory carries the default
   plus the defence's sentence, in its two code states: `agentdojo_default_spotlighting_2024_06` (`d9524c73…`, the
   sentence at `c274885`, typographic apostrophe; the 753 logs of the 2024-06 pin) and `agentdojo_default_spotlighting`
   (`2954962b…`, after `40085c0` rewrote the apostrophe; 147 head logs). Every `v0.k11` log with a system message is
   labelled (2024-06 18,034 of 18,241, head 24,707 of 24,914; the rest have none). A variant without a digest (ROPE's
   `auto_complete_line`, "not producible") cannot label a file.
7. **Local-model raw completions (D.6.6 local row).** In the pipelines of `agentdojo.local_model_raw_completion`, an
   assistant message whose text holds `<function=` tags gets `ext.agentdojo.local_model_tag_count`; more tags than parsed
   calls raises `agentdojo.local_parse_drop_possible` (warning, `agentdojo.local_model_tag_count@1`, now citing
   `local_llm.py` `_parse_model_output` l. 119-145 @089ed468: only the first tag becomes a call). The pattern is counted
   only where the quirk is declared (it is the lexical format of those pipelines' prompt), so no undeclared-quirk issue
   arises elsewhere. Head: 2,996 turns (1,854 logs), 1,192 of them with tags and no call.

**Profile machinery (D.4.2-D.4.5).**
8. **Layouts.** A layout segment is a literal, `{name}`, `{name}<suffix>`, or one optional multi-segment `{name?}`
   (`agentprov.adapters.agentdojo.layout`). Without an optional component the template is aligned from the right (phase
   6); with one, the segments before it from the left and those after it from the right, the rest being the component
   (`None` when absent: ROPE's `runs/{tree?}/{model_dir}/…`). The named components are the file's **facets**; selectors
   (`applies` of quirks and prompt variants) may name them and `variant`, `pipeline_dir`, `attack_dir`, `task_dir`,
   `suite` (computed from the fields when the layout lacks them); any other key is a `ProfileError`.
9. **Identity modes** (`[family.agentdojo.identity] model_from`). `pipeline_dir` and `model_dir` read that facet;
   `pipeline_name_minus_suffix` reads `/pipeline_name` minus the suffix `defence_suffix_regex` matches at its end (group 1,
   or the match without its `-`, names the defence; Mandate should write `-(mandate_(?:envelope|scoped|intent))$` to
   name the defence `mandate_envelope`); `results_dir_slug` maps the `{results_dir}` facet through `slug_to_model`. The
   identity `rule` (default `agentdojo.pipeline_dir_is_model_identity@1`) is the model's rule. `pipeline_name_policy`:
   only `verbatim_unreliable_when_differs` compares and raises `agentdojo.pipeline_name_mismatch`. **Identity tables**
   (D.4.5) are `table = {path = "tables/<x>.toml", sha256}` — an object, not D.4.4's bare path, so that the profile digest
   covers the table bytes — loaded from `adapters/agentdojo/tables/`, rows closed (`name`, `model`, `defence`
   (`none` for none), `provider`, `provider_evidence` (only `I`), `variant`, `codebase`, `pipeline_name`, `basis`,
   `note`), one row per directory; an unknown directory gives `identity_unresolved`. A row's `provider` becomes
   `model.provider` under the identity rule, and only then is `id_style_corroboration` evaluated: a call-id style naming
   another provider raises `identity_conflict` and records the style in `ext.agentdojo.id_style_provider` (I). The defence
   actors' rule is `agentdojo.defence_suffix@1` for directory suffixes, the identity rule for table rows and name
   suffixes, and the hook's first rule for a defence a hook adds. `attack_dir_alias` maps a directory to the attack name
   for path agreement only (ROPE `agentlab_longhorizon` → `long_horizon`).
10. **`[harness]`.** `retry_semantics` is closed: `agentdojo.final_content_none_max3` (the final message, item 4) and
    `agentdyn.last_assistant_content_none_max3` (the last assistant message anywhere) set the D.6.5 `att0` index rule;
    `agentdojo.single_pass` (DRIFT) is refused at profile load (stretch, AD-10 row 21). `code_identity` (`pinned`,
    `range`, `unpinned`) is recorded data; which rules a profile cites is `verified_code` (D.5.4 "Citation of D rules"; formerly `structural_rule_class`).
11. **Generic tables.** `agentprov.adapters.profiles` now closes `[import]` (`dialect`, `mapper`, `variants`, `rules`,
    `include`, `exclude`, `layout`, `layout_depth`, `path_must_agree`, `context_artefacts`, `auxiliary`,
    `opt_in_parts`, `variant_labels`, `native`) and `[lineage]` (`built_on`, `vendored`, `duplicates`, `cited_by`,
    `content_dedup` = `never`, `owns`, `excludes`), and accepts `[profile] via` (a profile served by another's import,
    which then has no `[import]`; D.4.4 `autodojo-via-rope`). An exclude entry is `{glob, code, owner?, owner_corpus?,
    note?}` with `code` one of `select.not_execution_artefact`, `select.owned_elsewhere`, `select.dialect_planned`,
    `select.licence_blocked`, `select.out_of_scope` (D-191), and an `owner` (a registry source id or `ext:<name>`) exactly with
    `select.owned_elsewhere`. `[family.agentdojo]` gains `attack_provenance` (D.4.4) and the keys above; the closed schema
    `family.schema.json` and its stdlib checker (now with local `$ref`) remain differentially tested against
    `jsonschema`.
12. **Selection in the runner (D.2.8 case 4).** Every walked file an exclude entry matches (strays excepted) is
    registered with the entry's code, stage `select`, disposition `not_imported`, and for `select.owned_elsewhere` the
    `owner` `{corpus_id, source_id}` (the entry's `owner_corpus`, else the owner's registry corpus id, else the owner id).
    This replaces phase 6's count of include ∩ exclude matches; for the shipped profiles, whose excludes are strays, nothing
    changes. What is walked depends on the origin: `--fetch` walks the pin's `tree`, `--input` the input root. For an
    archive input (D-200), the members outside the `expand` selection (`not_selected` rows, R-40) are matched too, by
    their member labels, so a member only an exclude entry names is registered under `<archive>!/<member>` and counted
    in `selection_excluded`. It is still never decompressed (D-560).
    `variant_labels` assign variants to registry parts (an `.incomplete` variant takes its base's label): importing part P,
    a file whose variant's label is another part is registered `select.dialect_planned` (`agentprov.adapters.runner.NotSelected`)
    and not mapped. A label may name a variant that `variants` does not declare only when the label is not one of the
    profile's own `parts` (the variant belongs to a part another import serves, as AgentDyn's `drift.k18.conversations`
    = `d`); the check is the same for every family (D-480). `context_artefacts` (role `supporting`) are stored before mapping with their pinned origins (an
    unvouched one is `raw.origin.blob_mismatch`) and handed to every `map` job of a mapper that declares
    `consumes_context` as auxiliary artefacts `context:<label>`, read only when opened; a context artefact is never
    registered as excluded. The TraceLogger mapper consumes them (hooks cite them); the Inspect mapper does not, so the
    `survey-agentharm` declaration stays documentary and that corpus is unchanged.
13. **Catalogues in the header.** `execution.rules` lists the mapper's catalogues plus every namespace cited by a record
    or seal issue (a hook citing `rope.*` adds `rope`); `execution.ns` adds the active hooks' namespaces.

**The extension point for wave 2 (source-specific quirks).**
14. **Contract.** A source-specific quirk is a `QuirkHook` (`agentprov.adapters.agentdojo.quirks`) in a module
    `src/agentprov/adapters/agentdojo/hooks/<source>.py` exporting `HOOKS: tuple[QuirkHook, ...]`; modules are discovered by
    name (sorted) and a quirk id hooked twice is a `ProfileError`. No generic code path is edited. Fields:
    - `quirk_id` (`agentdojo.<quirk>`, D.6.4), `rules` (rule ids the hook cites; the profile's quirk must list them, checked
      at profile load), `namespaces` (`{prefix: IRI}` of the hook's own `ext.<ns>`);
    - `defences(view) -> Sequence[str]`: extra defence actors of the file;
    - `tool_message(view, ToolMessage) -> ToolDecision | None`: consulted for each tool message after the PI-sentinel row
      and before the generic rows; a `ToolDecision(defence, rules, ev, verdict="deny", reason=None|"error"|"content",
      ext={})` yields `dc<n>` (subject the linked `tool_call` part, `after` the assistant message, `reason` copied O by
      source or `unk /reason not_recorded`), **no** `tool_execution`, and the tool message `generated_by` the decision
      (actor the defence; RF-3; the D.6.6 denial and decline rows);
    - `tool_execution(view, ToolMessage, record)`: may add `ext.<ns>` members to an execution record;
    - `judgements(view, recorded) -> Sequence[record]`: extra judgements after the recorded ones (released recomputations,
      `origin: "recomputed"`, `revises`; ids assigned by the mapper);
    - `census: {observed key: (CensusFile) -> int}`.
    `HookView` gives `quirk` (with `params`), `facets`, `variant`, `doc` (the parsed log), `family`, `defence_ids`, `rule`
    (rule resolution, `RuleNotDeclared` otherwise), and the import's `context` (`label -> ArtefactRef`) with
    `open_context(label)` (untrusted bytes: parse only through `agentprov.ingest`) and `cite_context(label)` (adds the
    artefact to `artifacts` with role `supporting`, returns `a<n>`). A hook runs only where its declared quirk's `applies`
    matches. The rules go in `rules/<ns>.rules.toml` of this family (homes of `rope`, `agentdyn`, `mandate`, `survey`,
    `drift`, `autodojo` in `agentprov.aer.rules`), new issue codes in that catalogue's `issue_codes`. A run-error outcome
    rule needs no hook: the outcome origin of a run error cites the **first rule** of the declared
    `agentdojo.run_error_imposes_outcome` quirk (`agentdyn.json_decode_error_imposed@1`, `survey.internal_server_error_patch@1`),
    else `agentdojo.run_error_imposed_outcome@1`. `tests/adapters/agentdojo/test_profile_machinery.py` exercises every hook
    point with a test hook.
15. **`observed` counts and the census (D.6.10 item 3).** `observed` is keyed by part. Each key is a sum over the part's
    full pinned snapshot of a per-AER count: the generic quirks' functions are `census.GENERIC`, a hook brings its own.
    `tools/agentdojo/profile_census.py --profile P --part X` maps every blob of the part's git pin (its own, else the
    primary pin that serves it through `[import] variant_labels`; `census_pin`) from the bare fetch cache and compares; `tests/full_corpus/test_profile_census.py` (marker `full_corpus`) runs it for every
    AgentDojo-family profile part with counts whose pin is cached, so a wave-2 profile is checked as soon as its cache is
    seeded (`tools/seed_git_cache.py --profile P --pin ROLE --clone PATH`: offline, file protocol, logged in
    `acquisitions.jsonl`). A declared key no function computes fails the test.

**The `head` part.**
16. **Pin, cache and census.** The head pin records `tree_sha1 = 472cbb2e…437c` (the `runs` tree). The bare cache was
    seeded from the local shallow clone at `089ed468` (acquisitions row of 2026-10-08, consent "phase-10 import evidence:
    seeded offline from the local shallow clone at the pinned commit (file protocol); content authenticated by the 40-hex
    commit id and fsck"): 36,679 blobs, 426,293,413 bytes, as pinned. The census reproduced every head count of the
    investigation (3,560 benign, 485 DoS, 82 null-final, 804 pre-passes, 207 empty, 105 run errors, 1 incomplete, 815
    unexecuted calls, 622 PI-detector logs, 2,996 / 1,192 local tag turns, 61,461 placeholder args) and both of its
    provider-id keys under generic names (`logs_with_colliding_empty_ids` 2,725: logs with two or more empty ids, all Gemini;
    `logs_with_repeated_ids` 213: a non-empty id repeated in the file, all GPT); the `2024-06` counts are unchanged.
17. **Fixtures.** `tests/fixtures/agentdojo/head/` holds seven byte-identical head blobs (30,379 bytes; MIT; read from the
    verified cache): five `v1.k14` (a local-model pre-pass, a turn with dropped calls, a tool error, an attacked
    `repeat_user_prompt` run), the `v1.k14.incomplete` log, and two `v0.k11` logs present only at head. Their AER digests
    are pinned in `tests/adapters/agentdojo/head_aer_digests.json`.
18. **History fields.** `ext.agentdojo.committed_no_later_than` and `benchmark_era` (D.6.5) need the commit that introduced
    each blob, i.e. a full-history fetch of AgentDojo; the user approved it on 2026-10-09 and D.6.16 implements them. The
    head import first recorded on 2026-10-09 predated that mapping and its AERs did not carry them; the import recorded on
    2026-10-11 (item 20) does.
19. **Digests.** The `agentdojo-upstream` profile changed (head counts, the prompt variant, two quirks), so its digest in
    every AER header changed (`9d77aefe…aa95` → `bbc96ce0…df86`). Mapping the `2024-06` goldens with the main profile
    bytes reproduces all ten pinned AER digests, and with the new profile they differ only in `execution.profile.sha256`
    (and so in `records_sha256`): C.16.1's execution digest is now `cbd03f51…fa66`. The `agentdojo` catalogue gained two
    rules and code citations (still version 1), so the golden PROV and gate-D digests were regenerated; the native SEM
    digests changed with their AERs only.
20. **Recorded import on the integrated code (2026-10-11).** The head snapshot was imported again on the integrated tree
    (`main` `afe7038`; `agentprov import agentdojo --snapshot head --input <clone> --verify-against-pin --release --jobs 10`,
    5,186 s, M2 Max) and `docs/reports/agentdojo/import-cli-head.json` regenerated from that run's `--summary-json` with
    `tools/import_report.py`; the wave-1 report of 2026-10-09 predated the history fields and the wave-2 mapper changes.
    Result: 36,679 of 36,679 `089ed468` logs sealed (33,745 clean, 2,934 with issues; 36,472 agent executions and 207
    outcome-only; 24,914 `v0.k11`, 11,764 `v1.k14`, 1 `v1.k14.incomplete`), 0 degenerate, 0 failed; every AER valid in release
    mode (36,679), every derivation passing tier 4 strictly (36,679) and re-deriving byte-identically from the stored AER and SEM
    documents (36,679); 1,153,595 records; accounting `unverifiable` 36,447 and `consistent` 232; every origin the pinned `git`
    origin. Seal issues by file: `earlier_attempts_unobservable` 36,472, `accounting_unverifiable` 36,447,
    `agentdojo.local_parse_drop_possible` 1,854 (2,996 turns), `unexecuted_tool_call` 800, `no_execution_observed` 207,
    `outcome_imposed_by_runner` 105, `retry_passes_inferred` 82, `incomplete_run` 1. Every count equals the wave-1 report's; the
    report differs from it only in the profile digest (`bbc96ce0…` to `a13b76ba…`, the D.6.16 history-table pin), the AER stage
    code digests and the wall time (4,565 s before). The history index was cached (item 18), so every AER carries
    `introduced_in_commit` on its origin and `ext.agentdojo.committed_no_later_than` (36,679; 50 distinct introducing commits,
    2024-06-02T12:26:48Z to 2025-07-25T17:05:15Z), and the 24,914 `v0.k11` logs carry `benchmark_era`: `v1` pre-versioning
    14,182, `v1` 4,470, `v1.1` 1,088, `v1.1.1` 2,259, `v1.2` 2,915, exactly D.6.16 item 9's figures; the 11,765 `v1.k14` logs record
    their version and get none. Against the wave-1 branch copy of the same snapshot (`agentdojo-upstream-head-p10.pre-integration`)
    the AER documents differ only in `execution.profile.sha256`, the origin's `introduced_in_commit`, the two `ext.agentdojo`
    members with their `evf` tags, the rule and source-locator lists that cite them, and `seal.records_sha256`; the SEM documents
    only in `aer_digest` and `records_sha256`; the PROV documents of all 36,679 executions are equal once the identifiers and attribute values derived from the AER digest are set aside (bundle, activity, mention and relation identifiers, derivation keys, the AER entity's name and the `apv:sha256` of the `agentdojo` rule-catalogue entity, `05e580ce…` to `acd77579…`): the history fields reach no PROV statement in v0.1. The census was regenerated on the integrated code (`census-head.json`): every
    `observed` count reproduces, `differences: []`. No second import of the head snapshot was run, so determinism across `--jobs`
    is not shown for it (the report's `determinism.second_import` is `not_run`).


### D.6.13 Implementation notes (phase 10): ROPE and AutoDojo-via-ROPE

The code is the reference: profiles `rope` and `autodojo-via-rope`; quirk hooks `adapters/agentdojo/hooks/rope.py` and
`hooks/autodojo.py`; catalogues `rules/rope.rules.toml` and `rules/autodojo.rules.toml` (homed in this family,
`aer.rules.CATALOGUE_HOMES`); the table `tables/autodojo_cache_variant0.json` (`tools/agentdojo/autodojo_cache_table.py`);
`tools/agentdojo/rope_report.py`; tests `tests/adapters/agentdojo/test_rope.py`, `tests/cli/test_autodojo_import_refusal.py`
and the census of `tests/full_corpus/test_profile_census.py`. Twelve licence-cleared fixtures (MIT) are under
`tests/fixtures/rope/` with `SOURCE.json`; ROPE's LICENSE is `tests/fixtures/LICENSES/ROPE-MIT.txt`. No ROPE or AutoDojo
code is imported or executed: the correction scripts and the attack's escaping and wrapper are ported from the pinned
blobs, read as data.

**Deviations from the D.4.4 sketch** (each forced by the pinned data):
1. **Pin.** The `head` pin is the whole commit `64495e16` (24,909 files, 265,463,047 bytes, tree `c4df12c3…`), not
   `tree = "runs/"` with 10,792 files. The context artefacts outside `runs/` (`src/rope/scopes/**`, the three routed
   caches) must be vouched for by the pin, and the `agentlab/**` and `autodojo/**` exclude entries only fire on files the
   walk sees; with a `runs/` pin neither holds. `runs/` itself is tree `6a8c86f2…` with 10,805 files (10,791 logs,
   `lh_cells.json`, 13 aggregators).
2. **Layout.** D.4.4's `runs/{tree?}/{model_dir}/{suite}/…` misparses the ablation and router trees, which have **no
   model level** (`runs/ablation/<policy>/<suite>/…`, `runs/router/<router>[-clamp]/<suite>/…`): the policy would become
   the model. The shipped layout is `runs/{model_dir?}/{suite}/{task_dir}/{attack_dir}/{file}.json`: the optional
   component is the **arm directory**, one segment in the main tree (the model directory) and two in the ablation and
   router trees. Two `[[identity.dir]]` rows give those arms the model `gpt-4o-mini` (I, `rope.model_dir_identity@1`;
   basis: `runs/ablation.py`, `runs/router.py` (the Opus router is the gpt-4o-mini tree), the tags, `call_*` ids), and
   the quirk `agentdojo.rope_release_tree` writes the arm configuration as `ext.rope.arm` (`{tree: "ablation", policy}` or
   `{tree: "router", router, clamp}`; D, `rope.tree_arm_config@1`). The same hook cites `rope.benchmark_from_suite@1` at
   `/task/benchmark` (github, shopping and dailylife are `agentdyn`).
3. **Quirk ids added to D.6.4** (ROPE only): `agentdojo.rope_release_tree` (item 2) and
   `agentdojo.autodojo_payload_cache_link` (item 9). The rope profile also declares, beyond the D.4.4 list,
   `incomplete_run` (the two empty logs lack their outcomes), `args_mutated_in_place`, `package_version_not_code_identity`,
   `placeholder_args_never_injection_evidence` and `benchmark_version_label_not_suite_version`, so that no quirk seen in
   the data is undeclared.
4. **`by: "source"`** (C.3.10, C.6 row "ROPE corrected security") cannot be written on the recomputed judgement: the AER
   envelope's `by` names the observing party of a bare `O` and is refused on a D record (AER-V12). Who released the
   recomputation is carried instead by `origin: "recomputed"` and the judgement's actor, the correcting party (item 7),
   to which EF attributes the value (`aprov.outcome@1`, recomputed branch).

**Hook API** (wave-1 machinery, extended without changing any existing AER): `QuirkHook.execution(view, header)` (header
facts under the hook's own `ext.<ns>`, with `evf` tags and scoped rules), `actors(view)` (extra actors after `def<n>`),
`fixture(view, vector, record)` (members of an `injection_payload` fixture), `HookView.issue(...)` (seal issues from any
hook point), `HookView.model` (the resolved model), and `ToolDecision.evf` / `.scoped` (tags and scoped rules for a
decision's own ext members). The quirks module docstring is the contract.

**Behaviour.**
5. **Guard denials** (`agentdojo.rope_guard_denial`). Every file has the defence actor `rope` (`def0`; I,
   `rope.guard_active_in_main_tree@1`: all 26 (tree, arm) groups hold denials; a log without one is defended by arm
   membership only) and `task.defense_id = "rope"`. A tool message whose `error` matches the profile regex is a `deny`
   decision on the call part, with **no** tool execution (`rope.denial_error_pattern@1`, I), `unk /reason` (the reason is
   not logged), and `ext.rope.query_echo` = `none` for the pre-fix suffix `user task: None.`, else `query` (D,
   `rope.denial_query_echo_variant@1`, scoped). The message keeps the empty text and the denial as `error`.
6. **Configuration tag** (`agentdojo.pipeline_name_not_identity`). The hook is param-driven (`params.model_tokens`; a
   profile without them is untouched, it declares no rules or namespaces of its own): the longest model token contained in
   `pipeline_name` is the model the tag names; if it differs from the directory's, the seal issue `identity_conflict`
   (rule: the quirk's first, `rope.model_dir_identity@1`; detail `pipeline_name names <token>`). Exactly the 949
   `qwen3-235b/*/autodojo` logs; the long-horizon qwen tag `vllm_parsed` names no model (253 logs, no claim). The profile's
   `id_style_corroboration` is declared but, as in D.6.11 item 5, only evaluated for identities that name a provider (none
   here).
7. **Effect-based corrections** (`agentdojo.rope_effect_correction`, `rope.security_correction@1`, D). A port of
   `runs/corrections.py` (`corrected_security`) and of `slack_it5.it5_secure(filtered_trace)`, `dailylife_it7.it7_secure`
   and `github_it1.it1_secure` at `64495e16`. It applies to every log of slack IT5, dailylife IT7 and github IT1 whatever
   the attack (the dispatcher has no attack condition; 51 of the 198 slack IT5 logs are long-horizon). The dispatch reads
   the logged `injection_task_id` where the aggregators read the file name; `path_must_agree` reports any disagreement.
   Records: the actor `rcorr` (`kind: judge`, `name: rope.corrections`, D) when the file is a subject, and a second
   `security` judgement `{origin: recomputed, revises: <the recorded one>, actor: rcorr, ev: D,
   ext.rope.correction: <rule label>}` **beside** the recorded judgement, which is never altered. A case the released code
   cannot decide (`github_it1` on a transfer task without a trace raises; a value its code would fail on) gets no
   judgement and the info issue `rope.correction_indeterminate` (none in the snapshot). When the import holds the scripts
   as context artefacts with the SHA-256 pinned in the quirk's `params.scripts`, they are cited (`supporting`; locators
   `{a: a<n>}`); other bytes under those labels give the warning `rope.correction_code_mismatch` and no recomputation.
8. **System prompt.** All 10,789 non-empty logs carry one prompt, the AgentDojo default plus the auto-complete line; the
   variant `auto_complete_line` is pinned by the SHA-256 `21a1c00d…` of ROPE's own copy
   (`agentlab/src/agentdojo/data/system_messages.yaml`, key `default`, 543 characters), which equals every logged one; the
   released `autodojo/` copy is the AgentDojo default `a021a92b…` (verify/rope.md §3). `verified_code = []` (formerly
   `structural_rule_class = "I"`; unreleased harness states; `rope.harness_is_vendored_autodojo@1`, declared as the basis, not cited per record).
9. **AutoDojo payload link** (`agentdojo.autodojo_payload_cache_link`, `attack_dir = "autodojo"`,
   `params.provenance_profile = "autodojo-via-rope"`; `autodojo.payload_cache_link@1`, I). The provenance profile's
   `[family.agentdojo.attack_provenance]` gains `table = {path, sha256}` (family schema): the SHA-256 of
   `_yaml_escape(variants[0])` per (suite, injection task, vector) of the 150 AutoDojo caches at `aa458794` and the 3
   routed caches at `64495e16` (153 cells, 637 slot keys, 924 digest rows; no payload text), so the mapping reads no cache
   bytes and the profile digest covers the table. A slot is linked when its payload equals such an escaped variant 0
   (`exact`) or is the escaped ImportantInstructions wrapper around one (`wrapped`; the attack's own template, user
   `Emma Johnson`, any model name). The fixture gets `ext.autodojo.cache_match`; the header gets
   `ext.autodojo.cache_cells` (the sorted cells consistent with **every** slot of the file: its ambiguity set) and
   `ext.autodojo.provenance_profile` (`{id, version, sha256}`); an unlinked file gets the info issue
   `autodojo.payload_cache_unlinked`. **Per-file sets** have 1, 8, 16, 20, 38, 40 or 50 cells (banking files narrow
   less than their arm); intersected over each (model, suite) arm they give the investigation's 1, 8, 40 or 50 cells
   (`docs/reports/rope/`). The arm-level set is not written into any AER: it is an inference across files (one cache
   per arm), which a per-file mapping cannot make.
10. **Registry and CLI.** Source `rope` · `head` (owner of the slice; `agentlab/res/**` registered
    `select.owned_elsewhere`, owner `ext:agentlab`, now in `EXTERNAL_OWNERS`) and `autodojo` · `rope-slice`
    (`via = "rope"`, profile `autodojo-via-rope`, `partial`: one of AutoDojo's ten defences and three models). `agentprov
    import autodojo` now imports the slice through `rope`'s import part, with the selection `attack = autodojo` implied
    from the provenance profile (a partial working corpus `rope`); it used to stop at a profile/source mismatch.

**Census** (`tools/agentdojo/profile_census.py --profile rope --part head`; all 10,791 pinned logs sealed, 0 crashes,
0 degenerate; every declared count reproduced): denials 12,657 = `none` 9,424 + `query` 3,233; null-final logs 322;
`qwen_autodojo_mislabelled` 949; empty logs 2 (both `no_outcome_recorded`); unexecuted trailing calls 675 logs / 753
calls; null call ids 8,707 (1,496 logs); benign security 748; corrections slack IT5 198, dailylife IT7 260, github IT1
220. Measured here, beyond D.4.4: ablation 1,240 / router 1,680 (clamp 440) logs; `args_mutated_in_place` 10,520 files;
`placeholder_args` present and null 83,362; package version `unknown` 2,268; link slots 5,775 linked (5,772 exact, 3
wrapped), 2,847 files linked; per-file set sizes 1: 1,824, 8: 228, 16: 28, 20: 30, 38: 2, 40: 315, 50: 420.

**Import (2026-10-10; `docs/reports/rope/`).** `agentprov import rope --snapshot head --input <clone> --verify-against-pin --release
--jobs 10` on `main` `afe7038` (3,015 s, M2 Max): 10,791 of 10,791 logs at `64495e16` sealed (9,366 clean, 1,425 with issues;
10,789 agent executions and 2 outcome-only; `v1.k14` 10,789, `v1.k14.incomplete` 2), 0 degenerate, 0 failed; every AER valid in
release mode, every derivation passing tier 4 strictly and re-deriving byte-identically (10,791 each); 505,333 records; accounting
`unverifiable` 10,789 and `consistent` 2. The pin check read 10,826 files (the logs and 35 context artefacts), all equal to their
tree entries. Seal issues by file: `earlier_attempts_unobservable` 10,789, `accounting_unverifiable` 10,789, `identity_conflict`
949, `unexecuted_tool_call` 675, `retry_passes_inferred` 322, `no_execution_observed` 2, `no_outcome_recorded` 2; 14,066 files not
imported (`select.owned_elsewhere` 13,765, owner `ext:agentlab`; `select.not_execution_artefact` 301). The census was re-run on the
sealed snapshot and reproduces every `observed` count (`differences: []`). `agentdojo.suites@1` fails closed on 173,833 of 655,557
SEM annotations (9,331 logs): 170,013 in the AgentDyn-benchmark suites and 3,820 in the three AgentDojo suites (the cause of the latter
was not investigated; the version label of those suites is a suite version, D.6.12 item 5). No second import was run (determinism across `--jobs` is not shown for ROPE).

**Q.8.** The recorded `security` values stay as logged; the recomputed ones sit beside them: slack IT5 32 of 198 recorded
successes, 0 after correction (all 32 flip, as verify/rope.md §6 found); dailylife IT7 39 → 22; github IT1 5 → 0. On the
AutoDojo arm the successes are 88 recorded (the AutoDojo paper's raw values) and 71 effective, recomputed where present
(verify/autodojo.md #15). The census asserts all of these (`*_recorded_true`, `*_corrected_true`,
`autodojo_recorded_true`, `autodojo_effective_true`). `rope_report.py` reads the sealed AERs and reproduces
them: slack IT5 198 logs (32 recorded successes, 0 after), dailylife IT7 260 (39, 22), github IT1 220 (5, 0); the AutoDojo slice 2,847
logs, 88 recorded and 71 effective successes, 5,775 linked slots (5,772 exact, 3 wrapped), per-file ambiguity sets of 1, 8, 16, 20,
38, 40 and 50 cells (1,824, 228, 28, 30, 2, 315, 420 files) and the arm intersections of 1, 8, 40 and 50 cells; every recomputed
judgement sits beside a recorded one (`docs/reports/rope/rope-q8.json`).

**Open.** The ROPE seeds of D.15.6 (artefact entries `rope.art.*`) are not yet in `artefacts.toml`; `lh_cells.json` and
the router scopes are stored as context artefacts but not consulted (no `lh_matched_cell` or scope link is mapped); the
denial reason and allowed guard decisions are not recorded by the source; SEM fails closed on the AgentDyn suites
(`agentdojo.suites@1` has no tool tables for them); a context-citing AER (the corrections) needs the context artefacts to
be recomputed (phase-9 follow-up on context provenance).

### D.6.14 AgentDyn (`agentdyn` · `a`; phase 10)

Implementation notes for the AgentDyn source, variant A (`v1.k14`, 38,281 of the 47,723 `runs/` logs at
`5353cf7615b135cace8d07c8f12dac53a16b6db3`). The code is the reference: profile `agentdyn`
(`adapters/agentdojo/profiles/agentdyn.profile.toml`), identity table `tables/agentdyn_pipeline_dirs.toml`, catalogue
`rules/agentdyn.rules.toml`, hooks `hooks/agentdyn.py`; tests `tests/adapters/agentdojo/test_agentdyn.py`, fixtures
`tests/fixtures/agentdyn/` (15 byte-identical logs, MIT, `SOURCE.json` per K.4.1); evidence and numbers
`docs/reports/agentdyn/`.

1. **Parts and routing.** The pin `head` carries `part = "a"`; the profile's `variant_labels` (D.4.4) assign every file to a
   part by its key-set variant, and the importer of part `a` records the others as `select.dialect_planned` (never
   mapped). `b` (`v0.k11`, Progent's vendored AgentDojo 0.1.29) is registered `planned`: the generic mapper already maps
   `v0.k11` where a profile declares it (the unit tests map a real B log through the profile), but no full B import was
   recorded. `c` (`drift.k18.messages`) is `partial` since regeneration-batch item 22 (2026-10-13): the DRIFT build maps
   it (D-270, the profile's six DRIFT quirks of D-279), and its full snapshot is not yet imported.
   `d` is `owned_elsewhere` (owner `drift`), `history` is `planned`. With several parts registered the CLI needs
   `--snapshot a` (or `--pin head`, which resolves to the pin's part).
2. **Exclude entries.** D.4.4 writes `src/**` for the DRIFT duplicate; the shipped glob is
   `src/agentdojo/defenses/drift/runs/**` (`select.owned_elsewhere`, owner `drift`), because `src/**` would also register
   AgentDyn's own source files (the fork's code and suites, 483 files) as owned by `drift`.
3. **Identity.** `model_from = "pipeline_dir"` with the 76-row table (digest-pinned in the profile, evidence class `I`
   under `agentdyn.pipeline_dir_registry@1`, basis: publisher-asserted directory label). Rows carry `variant` (A, B or C),
   `codebase`, the `pipeline_name` the directory's logs carry (so that only a real disagreement raises
   `agentdojo.pipeline_name_mismatch`; the 12 variant A travel strays in `gpt-5-mini-2025-08-07-progent` do, as that
   directory's row records the variant B value) and `provider` (omitted for the seven variant C directories, whose DRIFT
   code generates its own call ids). An unknown directory yields `identity_unresolved` and, now, `unk /task/defense_id
   not_recorded` instead of an asserted "no defence" (mapper change, table mode only).
4. **Retry.** `retry_semantics = "agentdyn.last_assistant_content_none_max3"`: `att0` cites the AgentDyn rule
   `agentdyn.last_assistant_content_none_max3@1` (not the AgentDojo one, whose premise is the final message) for `index: 2`
   and the two retry issues. Profiles with the AgentDojo semantics are unchanged.
5. **System prompts.** Three pinned variants by SHA-256 of the text (read from the logs and checked against the pinned yaml
   with the safe loader): `auto_complete_line` (543 characters, 32,063 variant A logs), `auto_complete_line_spotlighting`
   (716; the 5,184 spotlighting logs) and `agentdojo_default` for variant B (469; equal to the AgentDojo `089ed468` default).
   CaMeL and integrated-DRIFT logs have no system message.
6. **Quirks declared** (all with the AgentDojo-family quirk ids): the D.4.4 list, plus the generic ones that occur in the
   data and that D.6.4 requires a profile to declare (`benign_security_constant`, `silent_rerun_last_pass_only`,
   `injection_task_as_user_task_prepass`, `args_mutated_in_place`, `package_version_not_code_identity`,
   `unexecuted_trailing_calls`, `tool_filter_aux_llm`, `repeat_user_prompt_reinsertion`, `spotlighting_delimiters`,
   `local_model_raw_completion` for the SecAlign directories, `placeholder_args_never_injection_evidence`). The measured
   counts of every declared key are in the profile; the census (`tools/agentdojo/profile_census.py`) reproduces them.
7. **Generic mapper changes** (no catalogue `agentdojo` change, no golden digest of another profile changes):
   (a) `pi_detector_redaction` reads `params.defences` (default `transformers_pi_detector`), so the PIGuard and PromptGuard 2
   pipelines redact through the same D.6.6 row; (b) the sentinel is recognised in the one text block a `v1.k14` tool
   message holds (before, only a string matched, so a `v1.k14` redaction would have been mapped as an ordinary result);
   (c) the retry rule of item 4; (d) the unresolved table row of item 3.
8. **New hook points** (`quirks.py`): `user_message` (a `user` message of an unknown key set becomes a defence-authored
   message: a `deny` decision whose subject is the single `tool_call` part of the previous agent assistant message, else that
   message, and the user message `generated_by` it; the decision's reason is the `error` value; needs a previous assistant
   message and a string `error`) and `orphan_tool_result` (a tool message no call answers becomes an execution
   `requested_by` a defence actor, with `unk /parts/0/responds_to not_recorded`, instead of an ambiguous one; the hook
   gives the severity of the `orphan_tool_result` issue). Hooks in `hooks/agentdyn.py`: `progent_denial`
   (`tool_message`; `agentdyn.progent_denial_pattern@1`), `drift_integrated_user_error_key` (`user_message`;
   `agentdyn.drift_user_error_key@1`, D) and `camel_orphan_tool_results` (`orphan_tool_result`;
   `agentdyn.camel_orphan_tool_result@1`, severity `info`). `run_error_imposes_outcome`, `incomplete_run` and
   `provider_call_id_anomalies` need no hook: the generic rows are profile-driven (the quirk's first rule is the origin
   rule). D.4.4's "null-outcome files 12" are 12 logs that lack the outcome keys (verify/agentdyn.md §9 item 2), so the
   profile counts them as `files = 12` and `null_outcome_files = 0`.
   **Added by regeneration-batch item 2 (B3, D-376):** hook points `later_user_message` (a later plain `user` message no
   generic row attributes gets a defence actor as author, `evf /actor` at the rule's class, no decision record and no
   `unattributed_additional_user_message`) and `agent_input` (an agent `model_call`'s `input` is replaced by
   `unk {"/input": "not_recorded"}` citing the hook's rule). Hook `camel_interpreter_feedback` (`*-camel`): the
   interpreter's error feedback ("Running the code gave the following error:", profile `params.prefix`; CaMeL
   `privileged_llm.py` l. 86-134, 372-375 at `5353cf76`) is written by the camel defence
   (`agentdyn.camel_interpreter_feedback@1`), and the privileged planner's calls declare their input not recorded, since
   the planner is sent its own list (system prompt, query, earlier code/feedback pairs; never tool results; l. 306-321),
   not the logged prefix (`agentdyn.camel_planner_input_not_logged@1`). The CaMeL logs predate the cited code, so both
   are cited through their `_unverified` twins (class I). Counts (stored `agentdyn-a`): 1,674 feedback messages in 266
   logs; 2,342 planner calls in 386 logs. Open (§12): CaMeL's synthetic assistant messages (the printed-output summary,
   the trailing `content: None`) still get agent model calls, and failed-attempt tool results precede the code that
   issued them, so `messages_append_ordered` orders those executions before their cause.
9. **Not done.** Variants B and C (item 1), the `history` part, the artefact-catalogue entries of D.15.6 for AgentDyn, SEM
   tables for the three new suites (`agentdyn.suites@1`: SEM fails closed, see the report), the surfacing normaliser for
   Python-repr tool output.

10. **Import (2026-10-11; `docs/reports/agentdyn/`).** `agentprov import agentdyn --snapshot a --input <clone>
    --verify-against-pin --release --jobs 10` on `main` `afe7038` (9,145 s, M2 Max): 47,723 candidates, of which 38,281 mapped
    and sealed (35,904 clean, 2,377 with issues; `v1.k14` 38,269, `v1.k14.incomplete` 12), 0 degenerate, 0 failed; 9,442 files of
    variants B and C registered `select.dialect_planned` and 949 DRIFT copies under `src/` `select.owned_elsewhere` (owner `drift`).
    Every AER valid in release mode, every derivation passing tier 4 strictly and re-deriving byte-identically (38,281 each); all
    47,723 `runs/` files equal to the pinned tree entries; 1,552,020 records; accounting `unverifiable` 38,270 and `consistent`
    11. Seal issues by file: `earlier_attempts_unobservable` 38,281, `accounting_unverifiable` 38,270, `unexecuted_tool_call`
    1,683, `retry_passes_inferred` 826, `agentdojo.local_parse_drop_possible` 488, `unattributed_additional_user_message` 266,
    `orphan_tool_result` 240, `incomplete_run` 12, `agentdojo.pipeline_name_mismatch` 12, `outcome_imposed_by_runner` 5; no
    `identity_unresolved`. The census reproduces every `observed` count (`differences: []`). `agentdojo.suites@1` fails closed
    on 630,549 of 1,772,460 SEM annotations (210,242 integrity, 420,307 role; 32,262 of the 38,281 logs), exactly the tools of
    `dailylife`, `github` and `shopping` (`docs/reports/agentdyn/sem-unknown-tools.json`). No second full import was run; the
    only reproducibility evidence is a 648-execution branch-code copy whose AER and SEM documents are byte-identical to the
    integrated corpus's and whose PROV documents differ only in the `agentdojo` catalogue's `apv:sha256`.
11. **The `history` part, first slice (regeneration-batch item 95; R-10j-2; user decisions 2026-10-14; profile version 3).**
    AgentDyn's commit `785b9127` holds 621 logs in `runs/gpt-4o-mini-2024-07-18-drift/`: 620 DRIFT outputs
    (`drift.k18.messages`), present with the same blobs at every commit from `2d4ad05a`, and one incomplete TraceLogger log
    (`v1.k14.incomplete`), added at `68aba5bf`, whose pinned blob is first at `785b9127`. `4d2748c6` replaced the
    directory (`6623a721` does not touch it; bug pass NF-32), so the head pin holds 648 other, variant A runs under that
    name. EnvironmentOptim's 620 copies of the DRIFT outputs are AgentDyn's (phase 10j; the 621st,
    `shopping/injection_task_0/none/…`, is only in AgentDyn).
    - **Pin.** `[[source.pins]]` role and part `history`, commit `785b9127961c438f4db889c717949e2390dfee19`, tree
      `runs/gpt-4o-mini-2024-07-18-drift/` (`tree_sha1` `5c536dae…`, which authenticates every blob), 621 files. The part
      stays opt-in; the other superseded blobs stay planned.
    - **Selection.** `variant_labels` splits the files of a pin several parts share. A part with a pin of its own that the
      labels name for no variant selects every file of its pin (runner `own_pin_part`). So `history` maps its C files,
      and the head importers of parts `a` and `c` are unchanged.
    - **Identity.** Rows are keyed by directory name and the head table already has this name (variant A).
      `[identity] part_tables` gives a part with its own git pin a table of its own
      (`tables/agentdyn_history_pipeline_dirs.toml`: model `gpt-4o-mini-2024-07-18`, defence `drift`, variant C, the
      logged `pipeline_name` `gpt-4o-mini-2024-07-18`). A file uses it when its git origin commit is that pin's. The
      head table's bytes, which the archived versions 1 and 2 pin, are unchanged.
    - **Raw.** Fetched from GitHub at the pin (user-approved, one fetch), so the git origins name AgentDyn, `785b9127` and
      each blob id. A copy from EnvironmentOptim's tree would verify the same way, but it lacks the 621st file and could
      not be pinned offline (its clone is blob-less).

Rejected alternatives: a separate `agentdyn` mapper (invariant 5; the dialect is the family's); a hook for the PI-detector row
(the row is generic and the three detectors share one `transform`); mapping the CaMeL orphans positionally (a call that was
never made); keeping `src/**` as the DRIFT exclude.

### D.6.15 Mandate-AgentDojo-Eval and the survey's AgentDojo runs (`mandate-agentdojo-eval` · `head`, `agent-security-tools-survey` · `agentdojo-runs`; phase 10)

Implementation notes for the two small `v1.k14` sources of the wave-2 branches. Both map through the shared TraceLogger
mapper under their own profile (`mandate-agentdojo-eval`, `survey-runs`); neither changed `aer/`, `prov/`, `validate/` or
`corpus/`. The code is the reference: profiles `mandate-agentdojo-eval.profile.toml` and `survey-runs.profile.toml`,
catalogues `rules/mandate.rules.toml` and `rules/survey.rules.toml`, the Mandate hook `hooks/mandate.py`; tests
`tests/adapters/agentdojo/test_mandate.py`, `test_survey.py` and `test_source_reports.py` (the HON-10 gate); fixtures
`tests/fixtures/mandate/` (8 logs, MIT) and `tests/fixtures/survey/` (6 logs, CC-BY-4.0), byte-identical to pinned blobs with
`SOURCE.json` per K.4.1; tools `tools/agentdojo/{source_checks,profile_census}.py`; evidence and numbers
`docs/reports/mandate/` and `docs/reports/survey/`.

**Pins.**
1. **Mandate pins the repository root.** The pin is the whole single commit `fa62a977` (401 files, 3,137,054 bytes): the 396 logs
   of `runs/` (3,103,968 bytes; tree `11b6d0e4…`) and five root files. D.4.4 gives 396, which is the number of *selected* files; the
   pin must cover the four context artefacts (`agentdojo_mandate_eval.py`, `README.md`, `requirements.txt`, `LICENSE`) so that the
   same listing vouches for the harness the hook cites. `--verify-against-pin` read 400 files (396 logs and the four artefacts) and
   matched each to its tree entry. The profile's `corpus_digest` (`a8f4a9d7…`, the verify report's recipe over the 396 files of
   `runs/`) is recomputed from the pinned tree by a `full_corpus` test.
2. **The survey pins `agentdojo/`.** The git pin is `89c4db2c` with `tree = "agentdojo"`: 3,256 files, 43,565,675 bytes (the 3,243
   logs, 38,581,746 bytes; eight console logs, `timing_summary.csv`, the README, `extract_results.py` and the two
   benchmark scripts, one of which is the run script `run_full_benchmark.sh`). The run script is the only place the model tags
   are written, so it is a vouched context artefact; the submodule `agentdojo/agentdojo` is a gitlink and is not fetched. Both Zenodo version DOIs are
   recorded as alternative origins and not fetched (archive inputs exist since D-200; these alternative pins name no file
   or digest, so they are still not import pins). `--verify-against-pin` read 3,253 files (the logs
   and ten context artefacts), all equal to their tree entries.
3. **An import needs its part.** The survey has two importable parts of two families, so `agentprov import
   agent-security-tools-survey` takes `--snapshot agentdojo-runs` (TraceLogger, family `agentdojo`) or `--snapshot agentharm`
   (Inspect, family `inspect`; D.9). The Inspect profile selects only `agentharm/results/**/*.eval`; the `survey-runs` profile
   registers the six `agentharm/results/**/*.eval` files `select.owned_elsewhere` with `owner_corpus = ast-survey-agentharm` (the
   separate restricted-use corpus, U-05) and the four ASB result CSVs `select.dialect_planned` (10 register rows,
   `not_imported`); the Zenodo bundle's copy of AgentDojo's own `runs/` is owned by `agentdojo` and is not in the pinned tree.

**Identity and defence.**
4. **Mandate.** `model_from = "pipeline_name_minus_suffix"` with `defence_suffix_regex = -(mandate_(?:envelope|scoped|intent))$`:
   the whole suffix is the defence id (`mandate_<mode>`), because D.4.4's `-mandate_(envelope|scoped|intent)$` captures a bare
   `envelope` or `intent`, which names no defence, and the hook reads the mode from the id. The model is the logged
   `pipeline_name` minus the suffix, under `mandate.model_from_pipeline_name@1` (class I): **one rule added over D.5.4's two**
   (`mandate.decline_prefix@1` D, `mandate.allow_inferred@1` I), because no `agentdojo` rule states that the model may be read
   from the name (the default identity rule says the opposite). It is the Mandate counterpart of `survey.model_from_results_dir@1`.
   The undefended baseline of the same model has the bare model id as its name and no defence actor.
5. **Survey.** `model_from = "results_dir_slug"` through a three-entry slug table (`runs_qwen3_14b`, `runs_qwen3-coder_30b`,
   `runs_gpt-oss_120b` to the Ollama tags) under `survey.model_from_results_dir@1` (I): the logged `pipeline_name` is the constant
   `openai-compatible` in every record and no record names a model (`pipeline_name_policy = "constant_not_model"`: no comparison, no
   `pipeline_name_mismatch`). The code that wrote the logs is the submodule pin `089ed468` plus three local patches that are not in
   git (`code_identity = "unpinned"`), so `verified_code = []` (formerly `structural_rule_class = "I"`): the `_unverified` twins of the D
   rules are cited (D.5.4 "Citation of D rules"), and the run-error outcome rule `survey.internal_server_error_patch@1` is class I.

**Quirks and the hook.**
6. **`agentdojo.mandate_decline` (hook `hooks/mandate.py`).** A tool message whose `content` and `error` are the same string
   beginning `MANDATE_DECLINE:` is a gate decision (`mandate.decline_prefix@1`, D): no `tool_execution`, a `deny` decision by the file's
   `mandate_<mode>` defence actor on the declined `tool_call` part with the logged error verbatim as `reason`, and the tool message
   `generated_by` it (the baseline converter rendered such a call as an executed sink). A call of a tool the mode gates
   (`params.gated`: the three money tools for `envelope`; those plus `update_password` and `update_user_info` for `scoped` and
   `intent`) that ran has no logged allow decision, so `ext.mandate.gate = "allow"` is inferred (`mandate.allow_inferred@1`, I). Both
   cite the harness as the supporting context artefact (`ext.mandate.harness`). Allowed decisions and the gate's inputs are not
   logged; `scoped` is listed from the harness code and has no released log.
7. **Survey: no hook.** The run-error outcome (11 `gpt-oss:120b` logs; `utility` False, `security` True imposed by the survey's local
   patch), the iteration-capped traces and the solvability pre-pass are generic quirks of the mapper; the run-error rule is the first
   rule of the declared `agentdojo.run_error_imposes_outcome` quirk. `semantic_trap_security_gloss` is a note-only quirk: the
   survey's README glosses `security` as "did the agent resist"; AgentDojo's code semantics (the injection task succeeded) apply, so
   every "Security %" of that README is a targeted attack success rate.
8. **Mapper change: the origin's class follows its rule.** The `evf` of a judgement's `origin` was a hard-coded `D`. It is now the
   class of the rule that decides the origin (`_class_of_rule`), because a `D` pointer on a class-I rule is AER-V14 and the survey's
   patch rule is class I. For every class-D rule (all earlier profiles) the bytes are unchanged; no earlier AER digest moved.
9. **System prompt.** Both sources carry one prompt: the `default` of `system_messages.yaml` (469 characters, SHA-256 `a021a92b…1837`).
   Mandate pins it to the `agentdojo==0.1.35` wheel (`364bea42…`, read with the safe YAML loader) and the survey to the submodule
   pin `089ed468`; the two texts are equal to each other and to the head pin of `agentdojo-upstream` (D.6.12 item 6). All 396 and all
   3,243 logs are labelled `agentdojo_default`; none raises `system_prompt_unrecognised`.

**Census** (`tools/agentdojo/profile_census.py`, `differences: []` for both; the investigation's figures are marked):

| Quirk key | Mandate | Survey |
|---|---|---|
| Logs / variant | 396 / `v1.k14` | 3,243 / `v1.k14` |
| `mandate_decline`: declines / inferred allows | **240** / 143 (= 6 envelope + 137 intent derived allows of verify §3.4) | n/a |
| `run_error_imposes_outcome` files | n/a | **11** |
| `unexecuted_trailing_calls`: logs / calls | 0 / 0 | **48** / 49 |
| `injection_task_as_user_task_prepass` files | **27** | **105** |
| `benign_security_constant`: files / applied | 27 / 27 | 396 / 395 (the 396th is a run error) |
| `args_mutated_in_place` files | 391 (396 minus 5 tool-free runs) | 2,901 |
| `placeholder_args` present and null | 1,390 | 11,286 |
| `silent_rerun_last_pass_only` null-final logs | 0 | 0 |
| `package_version_not_code_identity` files without a version | 0 | 0 |

**Import results** (release mode; the commands, digests and full counts are in the reports):

| | Mandate | Survey runs |
|---|---|---|
| Candidates / sealed clean / with issues / degenerate / failed | 396 / 396 / 0 / 0 / 0 | 3,243 / 3,184 / 59 / 0 / 0 |
| Seal issues (files) | `accounting_unverifiable` 396, `earlier_attempts_unobservable` 396 (both info-level facts of every TraceLogger log) | those two (3,243 each), `outcome_imposed_by_runner` 11, `unexecuted_tool_call` 48 |
| AER valid (release) / SEM annotated / PROV tier 4 (strict) / PROV recomputed byte-identically | 396 / 396 / 396 / 396 | 3,243 / 3,243 / 3,243 / 3,243 |
| Origins | `git`, 396 | `git`, 3,243 |
| Wall time (10 workers, M2 Max) | 58 s | 525 s |

Cross-checks against the investigation (`source_checks.py`; every pair equal): for Mandate the outcome table of verify §3.4 cell by
cell, 240 declines (49 envelope, 191 intent), 143 derived allows, 5 tool-free runs, the message totals (396 system, 396 user, 1,621
assistant, 1,390 tool), and for all 240 declines the facts of the decision row (cites the decline rule, no execution, error verbatim,
a tool the mode gates); for the survey the per-model aggregates of verify §2.4 (benign utility, utility under attack, mean security
over the 949 attack pairs, solvability), the message totals (3,243 system, 3,243 user, 13,599 assistant, 11,237 tool), 11,286 tool
calls and the 11 run errors (all `gpt-oss:120b`).

**Not done.** Mandate's `scoped` mode (no released log), the survey's ASB part and the Zenodo archive inputs, a second full import
for the survey (whole-tree determinism was recorded for Mandate on the pre-integration code only; both integrated imports are
single runs, `docs/reports/{mandate,survey}/`); the Mandate gate's inputs and its allow decisions are not logged, so the inferred
allow is all that can be mapped.

Rejected alternatives: pinning only `runs/` for Mandate (the harness would be unvouched); reading the survey's model from
`pipeline_name` (a constant in every record); class `D` for the survey's patched code state (the patches are the author's claim and
are in no pinned tree); a bare `envelope`/`intent` defence id (it names no defence).

### D.6.16 AgentDojo history fields (phase 10)

`ext.agentdojo.committed_no_later_than` (rule `agentdojo.committed_no_later_than@1`, class D) and
`ext.agentdojo.benchmark_era` (rule `agentdojo.benchmark_era_from_commit@1`, class I) need the commit that introduced
each log, which a depth-1 pinned store cannot give. The user approved a full-history fetch of
`ethz-spylab/agentdojo` for this on 2026-10-09; the code is the reference (`agentprov.raw.history`,
`Fetcher.fetch_history`, `agentprov.adapters.agentdojo.history_table`, `tools/agentdojo/history_table.py`).

1. **History store.** `agentprov fetch --profile agentdojo-upstream --history --allow-network` (or
   `Fetcher.fetch_history`) fetches the pinned commit with its **full history and no blobs** (`--filter=blob:none`:
   commits and trees only) into a sibling bare store `<cache>/git-history/<host>/<owner>/<repo>.git`, hardened as the
   depth-1 fetch (no hooks, file protocol refused, `transfer.fsckObjects`, git at least 2.50.1). It is a separate store
   because a filtered fetch needs promisor configuration that must not touch the depth-1 store; every later git command on
   it runs with `GIT_NO_LAZY_FETCH=1`, so reading it can never fetch a blob. One acquisitions row is appended
   (`mode = "bare-full-history-blobless"`, `filter`, `commits`, `entries`, `bytes`, `index_sha256`, `consent`). The real
   fetch took 3.6 MB for 722 commits; the `2024-06` pin (c274885, 291 commits) is an ancestor of the head pin (089ed468)
   and needed no second fetch.
2. **Introducing commit.** For a pinned tree entry `(path, blob)` the introducing commits are the commits reachable from the
   pinned commit whose tree holds `blob` at `path` and none of whose parents does. The recorded one is the earliest by
   `(committer date, commit id)`. The walk is over the **full** history with all parents (`git log -m --raw --no-renames`
   parsed from NUL-separated output; an entry introduces the blob when it appears in the diff against every parent). A
   clean merge introduces nothing; a conflict resolution that yields a blob neither parent holds does. A re-added identical
   blob keeps its first commit; a renamed file is introduced at the new path by the rename. Rejected: the first-parent line
   (a pull request's merge commit is later than its own commits, so the bound would be looser); following renames or
   the first appearance of the content at any path (a tighter bound, but it names another path; 606 of the 36,679 head
   `runs/` blobs and 753 of the 18,241 `2024-06` ones have such an earlier content-wide appearance and keep the
   later, path-specific bound); topological order instead of committer dates (committer dates decide, ties by commit id).
   A tree blob with no introducing commit refuses the whole index (`raw.history.incomplete`): no partial index.
3. **Index.** `<cache>/git-history/<host>/<owner>/<repo>.index/<pinned commit>.jsonl` (`agentprov-history-index/1`, JCS
   lines, deterministic, no retrieval time): a header (repo, commit, tree, `commits` = introducing commit to RFC 3339 UTC
   date, counts, `rows_sha256`) and one `{"b", "c", "p"}` row per blob of the pinned tree, sorted by path. It is derived
   data, recomputable from the store, loaded with its digest checked; a corrupt or mismatching file is an error, a
   missing one is simply "no index" (no network, no recomputation at import time).
4. **Origins.** An import that finds the index (`GitPinTree` for `--fetch`, `PinCheck` for `--input
   --verify-against-pin`, `store_git`) puts `introduced_in_commit` (C.3.12) on each file's `git` origin. Without the index the
   origin is unchanged. AER digests of a corpus imported with the index therefore differ from those without it (the field
   is in `artifacts[0].origin`); CI has no history cache and stays on the origins without it.
5. **History table.** The mapper reads no cache and no git store: a commit id alone gives no date. The date and the
   version in force are package data, `tables/agentdojo-history.table.toml`, pinned by sha256 in
   `[family.agentdojo.benchmark.history]` (so the profile digest covers it, as for identity tables, D.4.5) and generated
   by `tools/agentdojo/history_table.py` from the history store (`--check` regenerates and compares; the `full_corpus` test
   calls it). It lists the benchmark versions with the commit that introduced each version directory (`v1`: `e1bc6171`
   "Add benchmark versioning" 2024-06-10; `v1.1`: `fa0c8559` 2024-07-16; `v1.1.1`: `c0cc91e6` 2024-11-07; `v1.1.2`:
   `bc5a5c30` 2025-01-15; `v1.2`: `0c7c4d56` 2025-01-16; `v1.2.1`: `ccb41e93` 2025-04-30; `v1.2.2`: `3f58252b`
   2025-10-27) and, for each commit that introduced a `runs/` blob in either pinned tree (50 commits), its committer date
   and the version in force in its tree. Two cuts are curated overrides, stated in the tool: `v1` (`bd533515` only created
   the empty package stubs) and `v1_2` (the directory name held the v1.1.1 bug-fix state until 2024-11-07, `7eee7284`).
   The tool refuses a table in which a commit's version has a cut that is not an ancestor of the commit.
6. **`committed_no_later_than`** (D). The committer date of the introducing commit, `YYYY-MM-DDTHH:MM:SSZ`, in
   `ext.agentdojo` of the header, with `evf` D, `rule` `agentdojo.committed_no_later_than@1` and `src` the origin
   locator `{"a": "a0", "o": "/introduced_in_commit"}`. An upper bound on the run time, a claim of the committer's clock
   (a rebase makes it later, never earlier than the work). Never a PROV time, never a timestamp of any record, never a lower
   bound. Written for every file whose origin carries the commit and the table lists it; a commit the table does not list
   gives no field and the warning `agentdojo.history_commit_unlisted`; an origin of another repository gets nothing.
7. **`benchmark_era`** (I). Only for a file that records no benchmark version (every `v0.k11` file; a `v1.k14` file
   whose label is a sentinel): `{"candidate": "v1.1", "basis": "registered" | "pre_versioning", "next": {"version",
   "cut_date"}}`, `evf` I, rule `agentdojo.benchmark_era_from_commit@1`. The candidate is the newest `default_suites/<vN>`
   directory present in the introducing commit's tree (AgentDojo registers a version by importing that directory in
   `load_suites.py`; the label is the directory name with `_` read as `.`; the registry at the head pin is cited in the
   rule's `code` list together with the cut commits). A commit whose tree has no version directory predates the label
   (`pre_versioning`, candidate `v1`: the suites `e1bc6171` later labelled `v1`). `next` is the version registered after
   it with the date of its cut, because versions were cut from the working tree: the 2024-07-16/17 travel re-runs
   (`52df3bc1`, committed 43 minutes before the v1.1 cut; `04ffc178` and `97b76722`, on a branch that did not hold the
   cut yet) get candidate `v1` with `next` v1.1 and the cut date visible. It is per file, never per pipeline directory;
   suites edited in place between two cuts and the task-set shape are not used. The `bench` actor keeps
   `unk /version not_recorded`.
8. **Without the index** neither field is written and nothing else changes (the existing `unk` and the absence of
   `committed_no_later_than` apply; no placeholder, no guess). The C.16.1 vector, which has no introducing commit on its
   origin, is unchanged except for the profile digest.
9. **Measured** on the real history. `head`: 36,860 blobs indexed (36,679 under `runs/`), 133 introducing commits (50 for
   `runs/`), 2024-06-02 to 2025-07-25 for `runs/`, 722 commits walked; `2024-06`: 18,334 blobs (18,241), 76 (35), 2024-06-02
   to 2024-06-05, 291 commits. Era of the `runs/` files at head: `v1` pre-versioning 14,182 (the baseline's unchanged
   files), `v1` 4,470, `v1.1` 1,088, `v1.1.1` 2,259, `v1.2` 2,915, `v1.2.1` 11,765 (the `v1.k14` batch, which records its
   version and gets no era); the 24,914 old-format files are the other five rows. All 18,241 `2024-06` files are
   pre-versioning. These sums reproduce the investigation's counts (24,914 old-format, 14,182 byte-identical to the
   baseline, 18,241 = 18,234 + 7 Mixtral).
10. **Facet `introduced_under` (D-84; regeneration-batch item 13; table format 2).** Each table commit records `under`, the
   oldest pin whose history contains it (`git merge-base --is-ancestor`, 2024-06 before head): 35 of the 50 `runs/`
   introducing commits are under `c274885`, 15 under head only. A log's facet is the `under` of its origin's
   `introduced_in_commit`; for an origin at the oldest pin it is that pin, because the blob is in the pin's own tree;
   otherwise it is unknown. The `c274885` entry of `agentdojo-upstream`'s `verified_code` selects `introduced_under =
   [c274885]`. So a `v0.k11` log introduced later, or with no known introducing commit, is code no pin covers and cites
   the `_unverified` twins (D.5.4). The mapper (also in its degenerate header), the SEM citation policy
   (`agentdojo.suites@2`) and the R07b check read it through one helper
   (`history_table.origin_introduced_under`). Measured on the stored corpora: head 14,182 `v0.k11` logs under `c274885`
   and 10,732 under head only, none unknown; 2024-06 all 18,241 under `c274885`.

---

### D.6.17 AgentDojo-format sources of the systematic search (phase 10d; D-100–D-114)

Phase 10d adds one profile per verified AgentDojo-format source of the phase-10c shortlist
(`docs/reports/systematic-search/candidates/agentdojo-format-shortlist.md`, D-90–D-96), a `planned` registry part each
(D.3.2), and one corpus per source (D-94; separate GPL/AGPL corpora). Nothing in `aer/`, `prov/`, `validate/`,
`corpus/` or the mapper changes (invariant 5): every profile cites the generic `agentdojo` catalogue only (D-101), and
behaviour that needs a rule is routed (`docs/reports/phase10d/routing.md` R1–R9). Defence denials logged as tool
errors are decisions through the generic quirk `agentdojo.defence_denial_message` (rule of the same name, class I; R1, D-113):
the profile states each defence's denial text, and other errors of that defence stay tool errors. Trial imports and census
reconciliation: `docs/reports/phase10d/` (D-100).

| Profile (source id = corpus id) | Pin | Logs | Licence | Identity | Notes |
|---|---|---:|---|---|---|
| `interbolt-agentdojo` | `43e2b5fa` | 2,016 | Apache-2.0 | table (hyphenated `-interbolt-<policy>-enforce`) | 1,879 denials as decisions (R1, D-113) |
| `melon-agentdojo` | `71d99dff` | 1,911 | MIT | `pipeline_dir` + suffixes | sentinel redactions (generic quirk); 36,679 upstream copies `select.owned_elsewhere`; version 2 (D-586): MELON's stop and block replies as `terminate` decisions, MELON-R's warnings as defence inserts (quirk `agentdojo.melon_defence_messages`) |
| `glitch-agentdojo` | `713bb296` | 1,844 | MIT | `pipeline_dir` + `-glitch` | 531 denials as decisions (R1, D-113) |
| `mohameduk-agentdojo` | `3f9d69a1` | 3,630 | MIT | `pipeline_dir` + `-ubag[_behavioral]` | `benchmark_version` null (D-102); upstream copies owned elsewhere; 2,731 denials and holds as decisions (R1) |
| `tacit-agentdojo` | `995692d3` | 2,076 | Apache-2.0 | `model_dir` table (labels verbatim) | client label `config_tag_never_model` (D-106); version 2 (D-587): quirk `agentdojo.local_model_raw_completion` on the Llama `local` pipeline, 622 turns flagged (342 tag-only finals) |
| `geryon-agentdojo` | `905aae02` | 3,179 (`v0.k11`) | Apache-2.0 | table by `<run set>/<log set>` (D-104); version 2 (D-588): condition-B rows carry Progent's policy model (`defence_model`, the defence actor's `model.requested`, class I) | condition B = Progent; 773 tool denials as decisions (R1) |
| `hilarytorn-trajectory-poisoning` | `d71ab8bc` | 990 | MIT | `pipeline_dir`, `{arm?}` | 22 attack labels |
| `yockcheng-prompt-injection-harness` | `5f9137ff` | 280 | Apache-2.0 | `pipeline_dir`, `{tree?}` | |
| `shreeyavarma-llm-safety` | `78d22e4a` | 672 | MIT | partial table | 58 local logs unresolved (D-105) |
| `kongminos-agentdojo` | `f341af69` | 950 | MIT | table row from the README (class I, D-92) | all call ids null; version 2 (D-590): quirk `agentdojo.local_model_raw_completion`, 478 turns flagged |
| `ceferisbarov-agentdojo` | `2273e1cd` | 18,442 | MIT | `pipeline_dir` | arm in the path only (R5) |
| `linyxus-agentdojo` | `698d7ff2` | 9,068 | MIT | table (OpenRouter routes, `-tacit`) | Tacit prompts unrecognised; extra keys in `ext.agentdojo.extra` |
| `craibench-agentdojo` | `e41eac1e` | 1,163 (`v0.k11`) | MIT | `pipeline_dir` + spotlighting suffixes | SEM `agentdojo.suites@2`: reviewed tables for the new suites (C.14.8, D-110..D-112); D-107 |
| `menelaus29-ipi-multidomain` | `ec9c9287` (main) | 858 | MIT | table by experiment path (D-104) | branches wait (D-108) |
| `gate-agentdojo` | `925b9926` | 3,870 | AGPL-3.0-only | table (`-gate-<arm>`) | 215 `local` logs unresolved; orphan results (R6); 1,101 denials as decisions (R1) |
| `sentry-agentdojo` | `938e8be7` | 674 | AGPL-3.0 | partial table | 72 free-router logs unresolved |
| `bookkeeper-agentdojo` | `0fe09bb6` | 570 | GPL-3.0-or-later | table (`-munim[...]`, `-none[...]`) | `benchmark_version` null; 180 refusals and holds as decisions (R1) |
| `aiauthz-agentdojo` | `6eaac86a` | 174 | AGPL-3.0 | table by `<model dir>/<arm>` (D-104) | logged names are tags (D-106); 9 denials as decisions (R1) |
| `llm-lock-agentdojo` | `7bb9915b` | 53,307 | GPL-3.0 | table by defence arm, no model (R4; all unresolved, D-92) | detectors abort (4 arms, R10) or redact (3 arms), no denials; `data-delimiter` = AgentDojo's spotlighting (D-114) |

Common to all: `verified_code = []` and every family D rule cited through its `_unverified` twin (D-24, D-103; tested
for every fixture and a synthetic log per source); the default system prompt recognised by its upstream digest, other
prompts only where a pinned text has the logged digest (D-109); `observed` counts from the phase-10d census over the
full pinned snapshot, reconciled with the phase-10c census (differences explained per source). Not profiled:
EnvironmentOptim, Kavach, Figshare (`docs/reports/phase10d/deferred.md`); llm-lock followed R4 (D-114).

**Fixtures.** The permissive sources are tested on byte-identical pinned logs (D-109). The five copyleft sources (gate,
SENTRY, bookkeeper, aiAuthZ, llm-lock) are tested on synthetic logs at the paths of the real excerpts they replace
(D-945, K.4.1(3)). These logs keep each source's layout, identity row, variant and dialect features: denials, empty and
incomplete runs, null finals, extra keys, CRLF line ends and the llm-lock detector abort. The real excerpts were
private-repository-only (`restricted`, 2026-10-12) and are not in the release tree.

**Pre-check wave 2 (2026-10-21; D-586..D-588; regeneration-batch items 111-113).** Three corpus pre-check findings move
these profiles to version 2. Version 1 of each is archived, because the pre-check scratch corpora record it (D-31).
- `tacit-agentdojo@2` (D-587) declares the local-model quirk for its Llama pipeline.
- `geryon-agentdojo@2` (D-588) gives Progent's policy model to the defence actor through the identity table (D.4.5).
- `melon-agentdojo@2` (D-586) declares `agentdojo.melon_defence_messages` (hook `hooks/melon.py`). It uses the new
  hook point `message_author` (`quirks.py`), which is called for every system message, before the positional rule, and
  for every agent assistant message without calls. Texts whose logged digest the quirk lists for the file's defence
  are that defence's (`agentdojo.defence_authored_message@1`, class I):
  - base MELON's stop message (910 logs) and MELON-R's block message (3) become a `terminate` decision by the defence.
    Its subject is the model call, which stays and generates nothing; the decision generates the message, and the
    reply is `/original` overwritten;
  - MELON-R's three security warnings (113 system messages in 98 logs) are authored by the defence;
  - the harness prompt standing after a warning is `bench` by its digest (`agentdojo.system_prompt_by_digest@1`,
    class I).

  The version-1 `melon_r_prompt` variant, which read the warning as the benchmark prompt, is dropped. Not mapped
  (routing R3, PC-05): the sanitised tool outputs. Profiles without the hook are byte-neutral.
- `kongminos-agentdojo@2` (D-590, waves 3-7) declares the local-model quirk, as tacit does.
- `seagent-agentdojo@2` (D-591, waves 3-7; D.6.18) declares `agentdojo.seagent_guard_block`. A tool message answering a
  call renamed `<tool>BLOCKED_BY_SEAGENT` is a `deny` decision by the SEAgent defence (`agentdojo.seagent_guard_block@1`,
  class I), not an executed tool (960 calls). The batch's dropped calls (D-592, hook point `unexecuted_calls`, after
  regeneration-batch item 89) are `unexecuted_tool_call` (warning) under the same rule, never lost results.

### D.6.18 The SEAgent artefact's AgentDojo logs (phase 10f; D-150–D-156)

Profile `seagent-agentdojo` (source id = corpus id), registry part `head` `planned` (D.3.2), from the phase-10e
verification (`docs/reports/systematic-search/candidates/phase10e-candidates.md` §3.1, D-144). Pin: Zenodo record
23218779, file `seagent-acsac2026-ae-v2.zip` (237,707,785 bytes; sha256, md5 and size in the pin). Licence CC-BY-4.0 for
the SEAgent-authored data (deposit README and LICENSES.md), AgentDojo benchmark text MIT. 5,342 `v1.k14` logs (AgentDojo
0.1.34 vendored in the deposit, not verified: `verified_code = []`, D-24) of deepseek-v3 under five arms, in
`seagent-ae/artifact/results/raw_data/agentdojo/{security,perf}/<arm>/<run dir>/<pipeline dir>/…`.

- **Identity** (D-104, D-152): table `tables/seagent_run_dirs.toml` keyed by the run directory (`model_from = "model_dir"`),
  because the pvagent, seagent and seagent-RF arms all log `deepseek-v3-250324-seagent_mcp`. Defences `pvagent`,
  `agentspec`, `seagent-initial`, `seagent-refined`, none for baseline. 336 logs name the model `deepseek-v3` without a
  version date, recorded as written.
- **Disclosed, not mapped as decisions** (D-153): 960 SEAgent guard warnings follow a tool result as user-role messages
  (863 logs); the mapper reports them as `unattributed_additional_user_message`, never as the user's. 740 PVAgent assistant
  messages have no `tool_calls` key, so the results after them stay orphan results (541 logs). A rule for
  defence-authored messages joins routing R1 of phase 10d.
- **Input** (D-156): the logs are deposit zip members. The runner does not import a deposit archive whose members are whole
  run logs ("archive inputs", §D.6.15), and the TraceLogger mapper's layout locator points at the origin's `/path`, which a
  `member` origin lacks (`aer.locator.dangling`; pinned by `test_a_member_origin_does_not_seal_yet_d156`). Until both are
  addressed there is no trial import; the phase-10f census (`tools/agentdojo/phase10f_seagent.py`) maps every member under a
  development-only `local` origin, validates the records in development mode and fills the `observed` table (D-154).

### D.6.19 The DRIFT variants `drift.k18.*` (phase 10l; D-270–D-279)

The DRIFT build of the `agentdojo.tracelogger` mapper (`adapters/agentdojo/drift_mapper.py`) maps both DRIFT variants for
every source: DRIFT itself (profile `drift`, parts `head` and `history`), AgentDyn variant C (part `c` of `agentdyn`,
re-keyed `messages`), and the DRIFT parts of EnvironmentOptim and drift-1 (their own profiles). The code is the reference;
evidence and numbers are in `docs/reports/phase10l/` (`census.md`, `aer-mapping.md`, `routing.md`). This section replaces
the "stretch" status of D.6.2 and AD-10 row 21 for these variants, and refines D.6.4 (`drift_*`), D.6.5 Steps 3-4 and
the D.6.6 DRIFT rows.

1. **Entry and identity (D-270).** `TraceLoggerMapper` hands `drift.k18.*` items to `DriftBuild` (routed edit RT-1);
   `DriftMapper` carries the same mapper id and version, so execution ids and headers are those of the dialect's mapper.
   Source locators use the variant's key (`/conversations/<i>` or `/messages/<i>`).
2. **Rules (D-271, D-272).** A `drift` catalogue (`rules/drift.rules.toml`): 15 class-D rules citing DRIFT code at
   `6fd3df47` (and `53dbc6c5` for the end-of-run plan fields), each with an `_unverified` twin, and the reserved
   `drift.proposed_calls_reparsed@1`. No DRIFT log names its code, so every DRIFT-format profile has `verified_code = []`
   and every harness reading is class I; logged values stay O. Generic rules are reused with their twins
   (`aer-mapping.md` §4.1).
3. **Header.** `task.defense_id = "drift"` (from the key set, `drift.defence_from_keyset@1`, or an identity-table row);
   `ext.agentdojo` holds `pipeline_name` (and `extra`), never `error` (DRIFT logs none); `ext.drift` holds `config` (the
   four flags), `tool_permission`, `plan {trajectory, checklist}` and `total_tokens` verbatim (O, with their meaning rules
   cited unscoped), and `plan_semantics` (`initial_plan` | `final_plan_state`, I) from the profile's
   `drift_plan_fields_by_commit` quirk, keyed by pin commit where parts share a layout. Raw planner text under
   `final_plan_state` raises `drift.plan_semantics_contradicted` and writes no reading (D-276). `bench.version` is
   `benchmark_version` with `suite_version_for_agentdojo_suites_only` (D-278).
4. **Scopes and fixtures.** `run` carries `duration` under `drift.duration_scope@1`; `att0` has `index: 0` under
   `drift.single_pass@1` and no earlier-attempt issue. No fixtures; an attacked run gets the info issue
   `drift.injection_map_not_recorded`.
5. **Messages.**
   - The first `user` message is the simulated user's task prompt.
   - A CALL ERROR `user` message directly after an assistant turn with empty `tool_calls` becomes a `decision` (actor
     `drift`, verdict `deny`, subject that assistant message, `reason` = the content, `ext.drift.check` trajectory or
     checklist) and the message `generated_by` it, role kept (D-273). A text matching neither check raises
     `drift.call_error_unrecognised`.
   - Each assistant message: a `model_call` with `unk /input not_recorded` (and the usual unknowns; one info issue
     `drift.agent_prompt_not_recorded` per file, D-275), the message with `ext.drift.text_form` (`reserialised` |
     `raw`), its `tool_call` parts, and `calls_form: empty_list` when DRIFT emptied or never filled the list. A final
     turn with call text and no calls raises `drift.calls_in_text_not_executed` (detail = the text form, D-277).
   - Tool messages are linked to their calls by id (D.6.6.1 rule 1 holds for every observed batch). The **last tool
     message of each batch** gets, after its execution, a `decision` (actor `drift`, verdict `other`, subtype
     `drift.isolation_pass`, subject the execution, `unk {"/original": "ambiguous", "/reason": "not_recorded"}`) that
     generates the message (D-274; C.5.5). Earlier results of a batch stay generated by their executions:
     `injection_isolate` reads and edits `messages[-1]` only, and the data agree (excised injection frames occur only in
     last positions; `census.md` §5). PROV gives the decision `used` on the execution's output and no derivation claim.
6. **Outcomes.** `checker` origin; benign `security` is `harness_default` under `drift.benign_security_constant@1`.
7. **Quirks.** Profiles declare `agentdojo.drift_tool_output_post_isolation`, `drift_assistant_reserialised`,
   `drift_call_error_as_user`, `drift_calls_in_text_not_executed`, `drift_no_system_no_injections`,
   `drift_plan_fields_by_commit` (census functions in `hooks/drift.py`), plus the generic `benign_security_constant`,
   `args_mutated_in_place` and `provider_call_id_anomalies` (seeded-random ids, trace-local). An undeclared DRIFT quirk
   raises `agentdojo.undeclared_quirk` and its row is not applied. The generic build's quirk hook points do not run for
   DRIFT files: a declared quirk whose hook implements one and whose selector matches raises
   `drift.quirk_hook_not_applied` (never skipped silently; census-only hooks are inert).
8. **Measured (scratch, 2026-10-13).** Every DRIFT file of DRIFT head (1,569), history (1,046), AgentDyn C (4,258, with
   RT-2 applied in memory), EnvironmentOptim's new 620 and drift-1's new 626 maps and validates in release mode, the
   profile census reproduces every declared count, and the AER bytes are identical across worker counts.
9. **Routed edits applied (regeneration-batch items 22 and 23, 2026-10-13).**
   - RT-1: the dispatch.
   - RT-2: AgentDyn part `c` (the quirks; `drift_integrated_user_error_key` narrowed to variant A).
   - RT-4: `ext.schema.json` without the required `error`.
   - RT-5: `profile.py` accepts `agentdojo.single_pass`.
   - RT-3: `semantics/suites.py` reads the tool of a `drift.isolation_pass` output like `redact`, without
     `R_REDACTED`.
   - Measured: AgentDyn's 14 part-a fixtures and 600 stored `agentdyn-a-p10` executions re-map identically except for
     the profile digest (and the seal digest that covers it). No stored AER has a `drift.isolation_pass` decision.

Rejected alternatives: a separate mapper id `agentdojo.drift`; subclassing the generic build; a `redact` verdict on every
isolated output; placeholder records for DRIFT's own LLM calls; re-parsing proposed calls in v0.1.

### D.6.20 The results-container dialect `agentdojo.results_container` (phase 10q; D-470–D-479)

memo-ozdincer/agentdojo (rank 6 of the phase-10e ranking, D-146) evaluates circuit-breaker (LoRRA) adapters and AgentDojo
defences with its own scripts, which write one JSON container per evaluation call: the call's settings at top level and
one row per (user task, injection task) pair. The code is the reference; the census and decisions are in
`docs/reports/phase10q/README.md`.

1. **Dialect and reader (D-470).** `adapters/agentdojo/results_reader.py`, `ResultsContainerReader`, declares
   `multi_execution = True` (D-320). One located item per row, key locator `{"p": "/results/<i>"}`, whose value is the
   whole parsed container. Variants by row key set:
   - `rc.k7`: the `run_eval` rows;
   - `rc.k12`: the `eval_benign_utility` rows (with `classification` in attack mode, `suite` in smoke rows);
   - `rc.unknown`: any other set. It is recognised but not mapped, so the row is sealed degenerate
     (`unsupported_variant`).

   An `n_results` that differs from the list length is reported on every row (`rescont.n_results_mismatch`). A container
   with no rows yields no item (D-320).
2. **Entry (D-471, R-10q-1).** `TraceLoggerMapper.map` and `degenerate_header` dispatch items of this dialect to
   `adapters/agentdojo/results_mapper.py` (`ResultsBuild`, `results_degenerate_header`), so the adapter id, version and
   execution-id prefix are the family's. A degenerate header that keeps the suite cites it where it was read: `/suite`,
   or `/results/<i>/suite` for a row of a container without one (regen item 117, NF-7). Like the TraceLogger build,
   `ResultsBuild` runs the D-378 lone-surrogate pass: `scrub_keys` on its row and the container's fields before mapping,
   and `surrogates(…, "agentdojo")` over the finished records before the redaction pass of item 8, so a lone surrogate
   is replaced by U+FFFD and disclosed by `agentdojo.lone_surrogate_replaced` instead of sealing an `adapter_defect`
   (regen item 119, NF-13).
3. **Rules (D-472).** Catalogue `rescont` (`rules/rescont.rules.toml`, homed in this family: `CATALOGUE_HOMES`,
   `citation.NAMESPACES`).
   - Every rule that reads the fork's scripts cites commit `7c331d97` and has an `_unverified` twin.
   - The profile verifies no code, because at least four writer versions wrote the containers. Harness readings are
     therefore class I; logged values stay O.
   - `rescont.value_redacted@1` cites no code; it is cited directly.
4. **Header and actors.**
   - **Task.** Suite, attack and defence come from the container, O by config (`rescont.container_fields_apply_to_rows@1`).
     A logged `defense: null` is "no defence". A container with no `defense` key and no table defence (item 5) records
     none: `task.defense_id` is omitted with `unk /task/defense_id not_recorded`, and the info issue
     `rescont.defence_unrecorded` is raised (regen item 116, NF-6), as for an unrecorded attack.
   - **Container fields.** `label`, `model`, `adapter`, `mode`, `base_url`, `port`, `elapsed_seconds` and `n_results` are
     kept in `ext.rescont.container`.
   - **Script summaries.** `classification`, `turns`, `failure_mode`, `any_garbled`, `n_assistant_turns` and
     `n_total_tool_calls` are kept verbatim in `ext.rescont.derived`. They are not judgements.
   - **`bench`.** Version `v1` (I, `get_suite("v1")`), code not recorded.
   - **`agent.model.requested`.** A provider model id is the logged string (O). Otherwise it is the model the container
     table states (I), or `unk not_recorded` with `identity_unresolved`.
5. **Container table (D-474).** `tables/memo_ozdincer_containers.toml`, pinned by sha256 under `[family.agentdojo.identity]
   container_table` (`model_from = "container_table"`).
   - Rows are `{glob, served, model, basis, conflict?, attack?, attack_basis?, defence?, defence_basis?, note?}`. They
     match the container path and the served model name **after redaction**, so no account path enters Git.
   - Each value cites the source document that states it (D-92). A LoRA adapter served under its own name is a defence
     actor (`rescont.lora_adapter_is_defence@1`).
   - A container that records no attack takes the attack from the row only when a document states it
     (`rescont.attack_from_identity_table@1`); otherwise `task.attack_id` is unrecorded and the issue
     `rescont.attack_unrecorded` is raised.
   - A row's `conflict` raises the info issue `identity_conflict`. This applies to the Llama-3.3 vs 3.1 statements,
     settled as D-474 (a).
6. **Scopes, messages, decisions.**
   - **Scopes.** `run` has `t.dur_s` (`rescont.duration_scope@1`) and no times. `att0` has `unk /index lost`
     (`rescont.last_pass_kept@1`: up to three passes, and a null final content is serialised as `""`). There are no
     fixtures; the info issue `rescont.injection_map_not_recorded` is raised instead.
   - **System messages.** Attributed to `bench` under `rescont.system_prompt_from_eval_script@1`.
   - **Repeated task prompt.** A later user message equal to the first is the repeating defence's copy
     (`repeat_user_prompt`, `secalign_sandwich`, `melon_aug`; `ext.rescont.copy_of`).
   - **Assistant messages.** Each gets a `model_call` whose `input` is the earlier messages at I
     (`rescont.request_built_from_messages@1`: the request is built client-side and may be trimmed to a token budget),
     with the info issue `rescont.request_not_recorded`.
   - **Calls and results.** Calls have no provider id; results link positionally (`agentdojo.positional_match@1`).
   - **MELON block.** The detector's fixed assistant text after tool results becomes a `terminate` decision of the
     `melon`/`melon_aug` actor about the last tool execution, plus the message it generated. The dropped model turn, the
     masked call and the embedding calls get no records (`rescont.melon_calls_not_recorded`).
   - **Spotlighting.** Spotlighted outputs carry `ext.rescont.content_state = "post_defence"`.
   - **`raw_output`.** A JSON-structured `raw_output` is the execution's `returned` (O). A string one is
     `unk /returned ambiguous` and is kept in `ext.rescont.raw_output`.
7. **Outcomes (D-475).** Utility and security are `checker` outcomes, with two exceptions:
   - a benign row's security is `harness_default` (`rescont.benign_security_constant@1`);
   - a row with no messages is the scripts' exception path. It is mapped as `unit: outcome_only` with both outcomes
     `harness_default` (`rescont.exception_imposes_outcome@1`) and the issues `outcome_imposed_by_runner` and
     `no_execution_observed`. The issue `outcome_imposed_by_runner` cites the rule the judgements cite, its `_unverified`
     twin (item 3; regen item 115, NF-5). Only a judgement whose logged value is the one the quirk
     `agentdojo.rescont_exception_row_defaults` declares (`utility = false`, `security = true`) is `harness_default`
     and listed in that issue; another value keeps its `checker` origin and raises the warning
     `rescont.exception_row_values_differ` (as the capture mapper's `run_error_imposes_outcome`; regen item 118, NF-8).
8. **Redaction (D-476).** `adapters/agentdojo/redact.py` is shared by the family. The profile's closed table
   `[[family.agentdojo.redact]]` uses the D-182 keys and template.
   - **Scopes.** `model_id` and `pipeline_name`. Patterns describe structure only; the named groups `span` and `leaf`
     are optional.
   - **What is replaced.** Each matched observed string is replaced as a whole wherever the AER holds it: values, object
     keys, and JSON-Pointer-escaped forms in `ext.lex` pointers, `evf`/`unk` keys and rule citations (BF-21).
   - **Recording.** Redacted pointers are `D` and cite `rescont.value_redacted@1`; `ext.rescont.redacted` lists them,
     and the info issue `rescont.value_redacted` is raised.
   - **Single values.** `redact_value` is the pure single-value form, for identity resolution before records exist.
   - **Raw.** Raw is untouched and ships as is (D-186 (c)); source locators stay on the raw field.
9. **Selection (D-473).**
   - Nine container directories are selected.
   - The two `*_combined.json` rollups are `select.not_execution_artefact`.
   - `results/agentharm_eval/*.json` is `select.dialect_planned` (D-477).
   - The 17 byte-identical copies collapse by source key.
10. **Fixtures (D-478).** Two real containers without account paths, `tests/fixtures/memo-ozdincer/` (88,775 B with the
    licence). Every other case is built in code with a made-up account (`tests/adapters/agentdojo/test_rescont.py`).
11. **Downstream (D-479, R-10q-4).** No AER, SEM or PROV byte of any stored corpus moves; every agentdojo golden re-maps
    unchanged. The agentdojo family code digest and the `aer` package identity (R-10q-3) move, and with them the `aer`
    stage identity of later agentdojo imports.
12. **The TraceLogger and DRIFT builds (regeneration-batch item 105; R-10j-1, D-510 (A)).** Both builds read the profile's
    redaction table and register the logged `pipeline_name` as the observed string of scope `pipeline_name`.
    - Order: after the records are finished, the Redactor rewrites it wherever the AER holds it: the `ext` copy, its
      lexical hint, and inside `artifacts[0].origin.path`, which the directory names byte for byte (D-510 (A)). This
      runs before the surrogate pass and the D-24 weakening.
    - Before identity resolution, the `pipeline_dir` facet and the logged name are both put through `redact_value`. So
      identity rows and profile selectors name only redacted labels.
    - As in the results build, each redacted pointer cites `rescont.value_redacted@1`, the unit gets one info issue
      `rescont.value_redacted`, and the header names the `rescont` namespace. Such a profile declares `rescont` in
      `[import] rules`.
    - A profile without a `pipeline_name` rule is unchanged.
    - A degenerate unit's header is redacted by the same Redactor. The observed names are the logged name plus the raw
      `pipeline_dir` facet.
    - When a profile declares rules, every `/`-separated segment of the `pipeline_dir` and `model_dir` facets is
      redacted before identity, since an arm path above the pipeline directory can hold the account (bug pass NF-2).
    - **Fail closed (bug pass NF-10, NF-11, NF-12; regeneration-batch item 132).**
      - A zero-width match, or a label that still holds the span, raises `ProfileError`.
      - A `{"$utf16": …}` value is redacted inside its encoding.
      - A rule whose scope the dialect's build does not apply (`REDACT_SCOPES_APPLIED`) makes the profile unloadable,
        instead of being ignored.

Rejected alternatives: a TraceLogger variant for whole containers; a separate mapper id; subclassing the generic build;
converting rows into TraceLogger dicts; new `agentdojo` catalogue entries; a table keyed by model id; code defaults as
attack identity; D-321 rejected rows for exception rows; importing the Inspect redactor across families.
### D.6.21 The deferred AgentDojo-format deposits and repositories (phase 10j; D-250–D-258)

Six profiles in the agentdojo family, new files only: profiles, identity tables (D.4.5) and append-only registry parts,
all `planned`. Census and decisions: `docs/reports/phase10j/census.md`; routed requests: `docs/reports/phase10j/routing.md`.
No mapper, quirk, catalogue or core file changed. Every profile has `verified_code = []` (D-24): every D rule is cited
through its `_unverified` twin.

| Profile | Pin | Logs mapped | Identity | Notes |
|---|---|---:|---|---|
| `authority-caps-agentdojo` | Zenodo 23138310 (v2.1.0; concept 22973265) | 18,739 (21,999 members) | table by pipeline directory: model + condition suffix | three nested `tar.gz` declared (D-382); 3,260 re-packed copies collapse (H.7.2); v1.0 contained (D-250) |
| `ipi-defenses-agentdojo` | Zenodo 22011266 (v4.0.0) | 3,211 | table by `<run set>/<defence>/<model>` (layout with no `pipeline_dir`) | all logs in three nested `tar.gz`; AgentDojo's built-in defence quirks (D-251) |
| `dca-agentdojo` | Figshare 32657856 (`url` pin) | 13,374 + 2,847 | table by `<group>/<run>/<pipeline dir>`, models from the README (D-92) | parts `v1` and `drift` by `variant_labels`; no import until a `url` archive input exists (R-10j-3) |
| `kavach-agentdojo` | three git pins | 2,625 | table by run directory; six directories unresolved | three snapshots of one corpus (D-202); `[KAVACH BLOCK` denials (D-113); invalid directory included and disclosed (D-253) |
| `environmentoptim-agentdojo` | git `febf82d8` | 6,120 (item 106; was 104) | table by arm path (D-254 addendum) | 6,016 redacted local Qwen3.5 logs, held as `select.redaction_pending` until item 106 (D-255, R-10j-1); 620 DRIFT and 83,740 copies `select.owned_elsewhere` (D-254, R-10j-2) |
| `drift1-agentdojo` | git `0e28729b` | 626 | table by DRIFT model directory | DRIFT build; PACT arm named `pact_drift` beside `drift` (D-256) |

**Archive members as executions.** Archive inputs (D-200) map each selected member under its `member` origin. A member of a
declared nested archive is matched by its own label inside that archive (D-380), so the layouts of the two Zenodo profiles
read `runs/...` paths inside the tars; the chain label is a register key only.

**Identity keys above the pipeline directory.** Where the defence (ipi-defenses) or the arm (dca, kavach) is a directory
above the pipeline directory, the layout's optional component spans both and `model_from = "model_dir"` keys the table by
the whole path (D-104). A layout without a `pipeline_dir` component is valid: the mapper reads only the facet the identity
mode names.

**Measured counts.** `tools/agentdojo/phase10j_profiles.py census` maps every selected log with its import origin, seals it
with the core writer (release mode) and compares the census counts with `observed` (D.6.12 item 3); `observed` writes them.
`tools/agentdojo/phase10j_census.py` reads the same bytes independently.

**Withholding.** None of the six declares `[withhold]` (D-257): no secret-like string in any selected log or deposit member.

1. **EnvironmentOptim's held arms are mapped (regeneration-batch item 106; profile version 2).**
   - **Redaction.** The 6,016 local Qwen3.5 logs map with the shared redaction (D-476, D-510 (A); D.6.20 item 12):
     rule `ceph_home` over `pipeline_name`, label `_cluster_home_{span12}_{leaf}`.
   - **Identity.** The table has one row per arm path (D-254 addendum, option (a); D-104). The layout is
     `runs/{model_dir?}/{pipeline_dir}/…`, with `model_from = "model_dir"`. A file with no experiment path is keyed by
     its directory (`model_dir_fallback = "pipeline_dir"`).
   - **Census.** 6,120 logs sealed: Qwen3.5-9B 5,910, -2B 53, -4B 53, gpt-5.4 104; none unresolved.
   - **Raw layer.** The raw logs and their pinned paths ship as published (D-510 addendum, user decision 2026-10-21),
     and the datasheet discloses it.

### D.6.22 TraceLogger robustness (regeneration-batch items 77, 78, 87–93, 96, 97; RD-1, core reviews D and A)

1. **Deny-listed tool names (item 87, CD-10).** A tool whose real name is on the C.7.3 deny-list (a model may call
   `none`) keeps its verbatim name on the `tool_execution` and on the `tool_call`/`tool_result` part, declared
   `unk ambiguous` (C.7.2(2)), as the Inspect mapper's BF-22. Before, AER-V17 collapsed the log into an
   `adapter_defect` AER.
2. **Placeholders in typed header slots (item 88, CD-11).** A deny-listed `suite_name`, `user_task_id`, `attack_type`
   or `injection_task_id` is malformed (`unparseable_artefact`, D.2.8), like an empty one; the degenerate header leaves
   such a suite or task id out. `pipeline_name` and `error` go to `ext` (verbatim, C.7.3) and are not checked.
3. **Unanswered calls of an id-linked batch (item 89, CD-12).** When the batch's results link by id (D.6.6.1, the D
   path), every unlinked call has no tool message whatever its index: `missing_tool_result` (or `unexecuted_tool_call`
   in the last agent message). The `k >= results` cut stays for positional linking.
4. **Content blocks (item 90, CD-13; item 91, CD-14; item 77, CA-19).** A block is `{type, content}`; a thinking
   block may also carry `id` (AgentDojo's `ThinkingContentBlock`, the provider's signature), which becomes the
   reasoning part's `signature` (O). A text or thinking block of any other key set (an extra key, or `content`
   absent), or whose content is neither a string nor null, is kept verbatim as an `other` part
   (`agentdojo.unknown_block`) with `agentdojo.unknown_message_shape`, never truncated. A text block whose content is
   null is `{t: text, text: null}` with its part index in `ext.agentdojo.null_text_blocks`, so it is not read as
   `content: null`. A call whose `id` is not a string (or null) is no `FunctionCall` shape: the message is kept
   verbatim (`agentdojo.unknown_message`). The converted transcript/v1 view reads a verbatim text or thinking block as
   the baseline converter does (`content or ""`), and renders a null-content text block as `""`.
   *Reconciled:* CA-19 also mapped an absent `content` to a null text part; that input follows CD-13 (kept verbatim),
   because a null part could not tell the two shapes apart.
5. **`evaluation_timestamp` (item 92, CD-16).** `t.start_naive` is written only for a calendar-valid date and time;
   otherwise only `t.raw.start` (with `unk /t/start ambiguous`, as for an unmatched pattern).
6. **A decline with no call (item 93, CD-23).** A hook's denial or decline on a tool message with no preceding
   assistant call has no subject: the previous message is not one by position (invariant 2). The message stays
   defence-written (the hook's rule, `/actor`), with no `decision` and no `tool_execution` (AD-03), `unk
   /generated_by not_recorded` and `/parts/0/responds_to ambiguous`, and `orphan_tool_result`.
7. **Family checker (item 78, CA-11).** The `family.schema.json` checker compares `enum` values as JSON (`true` is not
   `1`).
8. **A negative `duration` (item 96, R-10j-4).** AgentDojo's `duration` is a `time.time()` difference, and two Figshare
   CaMeL logs record a negative one (the clock went backwards). It is no `dur_s` (C.8.3, `>= 0`). Both builds keep it
   verbatim in `t.raw.dur` (its JSON lexical form) with `unk /t/dur_s ambiguous`, so the log is sealed. A v1 log's
   `t.raw.start` sits beside it. No issue code is added, which would bump the `agentdojo` catalogue.
9. **Deny-listed tool names in the DRIFT build (item 97, R-10j-5).** The DRIFT build applies item 1's rule too (a
   Figshare DRIFT log whose model called `none`).

## D.7 `transcript/v1` importer (`agentprov.adapters.adprov`)

### D.7.1 Scope and role

The baseline has 35,691 `transcript/v1` files: 17,664 released live transcripts (`corpus-prov`) and 18,027
converted legacy transcripts (`corpus-og-agentdojo-runs-prov`) [audit/capture.md §0.4]. They have two roles.

1. **Released live corpus (17,664; registry `adprov-v1` · `release`, `supported`).** The transcript **is** the
   primary raw evidence, because no wire log or native log was kept [audit/capture.md §1 item 2]. These are imported
   as raw artefacts with mapper `adprov.transcript_v1` (origin `corpus {AgentDojo-PROV, 2.3, producer_commit
   579a908…}`, C.3.12).
2. **Converted legacy tree (18,027; registry `adprov-v1` · `converted-legacy`, role `compat_oracle`).** These are
   derived conversions of upstream logs, carry no source anchor, and were regenerated in place
   [audit/legacy_replay.md §1 items 2, 8]. AgentPROV corpora re-import the upstream bytes instead (profile
   `agentdojo-upstream`, pin `2024-06`, 18,241 logs including 7 Mixtral).

   The v1 importer still maps these files, but only for the **compatibility oracle** (`adprov-v2.3-compat`) and for
   linkage. Each converted AER gets `ext.adprov.derived_from_upstream` = `{repo, commit, path}` (D,
   `adprov.converted_stem_to_upstream_path@1`). It is found by inverting the baseline naming rule
   `convert_runs._output_relpath` (`agentdojo_prov/convert_runs.py:175-183`) and matching the upstream tree at the
   `2024-06` pin [audit/legacy_replay.md §3.2]. An ambiguous or failed match gives the issue
   `adprov.upstream_link_unresolved`. The converted tree stays a `compat_oracle` part until the full Gate R claim gate
   passes with zero mismatches (AD-07, §D.7.4). It passed on 2026-10-08 (J.4.6): the tree is recorded as superseded by
   the native import and keeps the `compat_oracle` role as the oracle of gates A1, A2 and B.

### D.7.2 Detection

- Dialect `adprov.transcript_v1`, variant `v1`.
- The object has `adprov_schema == "transcript/v1"`, `meta` and `turns`.
- Sub-variants are flags, because the schema id was never bumped [audit/capture.md §7.1]:
  - `capture:block` (`meta.capture` present);
  - `attempts:discarded` (`discarded_attempts` present);
  - `timing:stubbed` (`meta.timing_stubbed`);
  - `source:converted` (`meta.source == "agentdojo_native_run_log"`);
  - `null_reply:encoded_empty`: inferred for released transcripts generated before 2026-10-04, decided by the
    absence of every post-June field (rule `adprov.release_null_as_empty@1`).

### D.7.3 Mapping

**Field placement.** The v1 ↔ AER field table is specified **once**, in C.15.3, generated from the machine-readable
`src/agentprov/views/transcript_v1_fields.toml` (owner C; R-30). This section does not restate it; the importer and
the view are generated from, and tested against, that one table. C's placements apply (they were verified
byte-identical in C.16.2). [R-30]

**Importer obligations** (in addition to the field table):
- `ex` from the mapping id `adprov.transcript_v1/adprov-v1`, the file sha256 and `{"p": ""}`; `unit:
  "agent_execution"` (or `"outcome_only"` for a transcript with no turns); `prov_primary: "native"` for released
  transcripts (written by the generating harness) and `"secondary"` for converted ones (a derived conversion of an
  upstream log; the upstream log itself is the primary source, reached through `ext.adprov.derived_from_upstream`).
  The classification fails closed (R-22).
- **Lexical hints are mandatory** (byte-exact view, AD-02): every object and number copied from the transcript,
  including typed fields (`meta.wall_clock_s` → `t.dur_s`, `model_config.*` → `params.*`, `usage.*`), goes through
  `aer.canon.lex_hints()`. Integral floats in `args` (313 released, 1,681 converted activities) and
  non-lexicographic argument key orders (12,676 and 12,862) would otherwise be rewritten by JCS
  [spec/B_audit_evidence/README.txt]. `model_config` values are copied into their typed slots with hints; there is
  no "verbatim `ext.adprov.model_config`" copy, because the AER line is JCS-canonical (`0.0` would become `0`).
- **`tool_call_id` check.** The importer verifies that each tool turn's `tool_call_id` equals the paired call id;
  otherwise it raises the issue `adprov.tool_call_id_mismatch` and links nothing (R-30).
- **Content hash check.** Each tool turn's `content_sha256` is checked against the SHA-256 of the UTF-8 bytes of the
  recorded content; a mismatch gives `adprov.content_hash_mismatch`.
- **Layout check** (J.3.2). Each object's observed member order is checked against the J.3.2 layout table and the
  layout record `ext.adprov.v1` (C.15.3); an order the table does not allow gives `adprov.v1_layout_unexpected_order`,
  and a member it does not list gives `adprov.v1_layout_unknown_member`.
- **Issue codes** (`adprov` catalogue `issue_codes`, raised as `adprov.<code>`): `tool_call_id_mismatch`,
  `content_hash_mismatch`, `upstream_link_unresolved`, `v1_layout_unexpected_order`, `v1_layout_unknown_member`.
- **Timing stub.** A tool `"0"` timing under `timing_stubbed` keeps the verbatim strings in `t.raw = {"start": "0",
  "end": "0"}` and declares `unk` on `t.start` and `t.end` (C.7.3), rule `adprov.timing_stub_is_unknown@1`. It is
  **never** a typed time value; the sentinel ban applies to typed time fields only.
- **Null replies.** `""` with flag `null_reply:encoded_empty` stays `""` plus `unk {"…/text": "ambiguous"}` (rule
  `adprov.release_null_as_empty@1`) [audit/capture.md §7.2].
- **Context membership.** Released v1 context membership is INFERRED (`adprov.context_is_prefix@1`, class I), so it
  lands in the inference bundle (AD-05). Reasoning attached by position is `evf I`
  (`adprov.reasoning_log_alignment@1`).
- **Instrumentation.** The header carries the AgentDojo-PROV capture's observer effects as instrumentation items
  (e.g. `adprov.developer_role_rewrite@1`, `adprov.malformed_tool_call_resample@1`,
  `adprov.upstream_failure_retry@1`, `adprov.model_display_name@1`, `adprov.temperature_not_transmitted@1`), in the
  AD-03 shape, justified by `adprov.v1_capture_code_semantics@1` (I) (C.16.2).
- **Outcomes.** Released `meta.utility`/`meta.security` have origin `checker` (`adprov.checker_outcome@1`); a benign
  `security: null` stays `value: null` with origin `harness_default` (`adprov.benign_security_normalised@1`).
  Converted files' `run_error`, benign constants and DoS rules use the `agentdojo` outcome rules of §D.6.7.
- **Defence-authored messages** in converted transcripts of defended pipelines are attributed to the defence actor
  exactly as in §D.6.6, so that J.4.4 can mirror them (R-32).
- Converted files carrying `injection_task_*` user tasks get `ext.agentdojo.task_kind =
  "injection_task_as_user_task"` [audit/legacy_replay.md §3.6 D6].

### D.7.4 Round-trip and compat requirements

The view API is `agentprov.views.transcript_v1.render(aer) -> dict` (order- and type-faithful),
`render_converted(aer) -> dict` and `serialise(dict) -> bytes` (C.15.3). The view reads **nothing** from raw; every
value comes from the AER and its `ext.lex` hints (AD-02). Round-trip and regression assertions compare JCS values or
bytes, **never** Python `==` (which ignores key order and int/float typing). [R-04, R-26, R-32]

- **Gate A1 (JCS value identity).** For every one of the 35,691 files, `JCS(render(map(v1)))` equals `JCS(v1)`.
- **Gate A2 (bytes).** For every one of the 35,691 files, `serialise(render(map(v1)))` equals the source bytes.
- **Gate B (compat graph bytes).** The compat profile runs the verbatim-ported `build_prov` on `render(aer)` and MUST
  reproduce all 35,691 stored graphs byte for byte. The baseline reproduces them from its own transcripts
  (17,664/17,664 and 18,027/18,027 [spec/B_audit_evidence/README.txt]). The golden pairs run in CI; the full set runs
  locally (PQ phase 4).
- **Gate R (`render_converted`).** `render_converted(aer)` renders the converted-tree view from the **upstream**
  TraceLogger AER (pin `2024-06`). It re-applies the baseline converter's documented field rules
  (`agentdojo_prov/convert_runs.py:138-208`), including the `"0"` stub and the `benign` label, inside the view and not
  in AER (AD-07):
  - R1/R2 (bytes) on the golden converted pairs (C01–C07 plus the MIG-10 converted pairs) are **release-blocking
    in CI**;
  - the full run over the 18,241 pinned blobs (18,027 comparable pairs) is a **claim gate**: only a pass with zero
    mismatches licenses the statement "the native re-import supersedes the converted tree" and the replacement of the
    converted corpus; otherwise the converted tree stays a `compat_oracle` part and the mismatch report is published;
  - R3–R5 are reported, not gating.

The first revision's sentence "this proves the re-import loses nothing the baseline used" is withdrawn: only the full
R1/R2 claim gate can license such a statement (R-26).

---

### D.7.5 Implementation resolutions (phase 4, 2026-10-08)

The code is the reference (`agentprov.adapters.adprov`, `agentprov.views.transcript_v1`).

**Gates.** A1 and A2 pass on all 19 golden pairs and on the full local corpus (35,691 of 35,691; three runs with
identical digests). C.16.2 is reproduced byte for byte, given its stand-in profile digest (E22).

1. **`ext.lex`.** `flt` covers `/params/temperature`, `/t/dur_s` (integral `wall_clock_s`) and integral floats inside
   `args` at any depth. `ord` covers argument objects at any depth. `ext.adprov.v1` keeps the key-order lists and, when
   they cannot be aligned, the verbatim `finish_reasons`.
2. **R05 (MIG-10).** C.7.4 is followed: no lost calls, and accounting is `inconsistent`. J.2.4's "4 lost calls" is
   superseded.
3. **`"benign"`** maps to `attack_id: null` under `adprov.v1_benign_label@1`, in both directions. J.4.4 aligns with
   this.
4. **Defence attribution** for converted files is by role (J.4.4), because adapter families are siblings (M.5.2(2)).
   The PI sentinel is a `redact` decision with actor `def0`.
5. **R07.** A repeated id that is unique within its batch links with class D, not J.2.4's I. The earlier turn's timing
   is `unk overwritten`, with issue `adprov.tool_timing_overwritten`.
6. **Converted `model_id`** is a pipeline name. `model.requested` is declared `ambiguous`, and the value is kept in
   `ext.adprov.model_id`.
7. **`meta.capture`** is stored as `ext.adprov.capture_block`, because `capture` is a header core field (AER-V23).
8. **The upstream link** is computed from the meta fields with no tree lookup, which keeps the mapper pure.
9. **Rules.** All 17 D.5.4 `adprov.*` rules are declared, plus 8 new ones:
   - `turns_hold_last_pass`, `discarded_attempts_in_order`, `capture_environment_record`,
     `empty_assistant_text_ambiguous`;
   - `additional_user_turn_unattributed`, `refusal_log_alignment`, `timing_keyed_by_call_id`, `v1_writer_layout`.

   The D.7.3 instrumentation ids are declared too. A test checks that every emitted rule and issue code is declared.
   The `agentdojo` rule catalogue is seeded with the 17 D.5.4 rules that C.16.2 cites; phase 6 completes it.
10. **Open for later phases.**
    - D.2.4 should add `MappingContext.catalogue_versions`.
    - D.6.6 maps `""` to plain text, while C.19(4) requires `ambiguous`; the adprov rule
      `empty_assistant_text_ambiguous` follows C.19, and D.6.6 is aligned in phase 6.
    - The CLI `import adprov-v1` wiring and the `adprov` artefact catalogue (D.15.6) are not done yet.
    - The `render_converted` byte gates R1 and R2 need the phase-6 TraceLogger mapper.

## D.8 STAC importer (planned; design note)

STAC (MultiTurnAgentAttack) is **planned** in v0.1 (A6, verified; AD-10 row 21). This section is a design note: it
fixes the shape so that the AER contract already accommodates scenario records, but no STAC adapter, corpus or NC
partition is built in v0.1. The package `agentprov.adapters.stac` holds this note only. [R-28, R-14, R-03]

> **Resolved (A6 / R-28; §1.3 "D ch D.8"):** the first revision's challenge to D11 is **rejected in part**. STAC's
> import status is `planned`, not `partial` (A6, verified). The parts of the proposal that stand: every STAC record is
> `unit: "scenario"`, never an agent execution; the caveat "scenario records; 1 target-agent trajectory" is kept; STAC
> does not count towards D12's "≥ 2 structurally different sources" (the Inspect importer does, AD-06); and the ASB id
> defect is recorded per record.

### D.8.1 Dialect and reader

- Dialect `stac.json_array`, variant `v1`.
- The artefact is `data/STAC_benchmark_data.json` at `amazon-science/MultiTurnAgentAttack@ddeede7a0042d108b819e35281135b0b0fabb4de`
  (sha256 `65efa030df106951ac82c96535eb9ebb99f54d02558787cfe2a2bbc5329d471b`, 4,962,431 B)
  [sources/multiturn-agent-attack.md §2].
- **Sniff.** The top-level value is a JSON array whose first element has the key set
  `{id, generation_config, attack_plan, interaction_history, planner_history}`.
- **Parse.**
  1. Decode the whole file with `strict_json_loads`.
  2. Walk the array with `json.JSONDecoder.raw_decode` over the decoded text, recording each element's
     `[start, end)` **byte** span (`len(text[:idx].encode())`).
  3. Assert that the JCS of `strict_json_loads(bytes[start:end])` equals the JCS of `array[i]` for every element.
  4. Yield one `LocatedItem` per element, with `Locator(p=f"/{i}", bytes=(start, end))`. The ex-id key is the
     canonical `{"p": "/<i>"}`; byte spans are verification-only and never enter the key (RESOLUTIONS §3.4).
- **Auxiliary artefact** (role `supporting`): `Agent_SafetyBench/data/released_data.json` (sha256
  `59dd0333001ef767766d803e97086ec02af0fbf7ff1f7070b3797863b0dacbe2`). It is used only for the ASB id-link check.

Why scenarios: in 482 of 483 records the assistant turns are **scripted** by the STAC generator, and the last message
is an **unanswered** attack prompt. No target-agent response, judge score or outcome exists. Only record 139 contains
a real (unidentified-model) agent trajectory [sources/multiturn-agent-attack.md §0, §3.3–3.5]. The released file is
evidence of the *benchmark-generation process* (real tool executions in SHADE-Arena/ASB environments by a script,
plus planner LLM outputs), not of agent-security executions.

### D.8.2 Mapping (one AER per array element; design)

The rule names below are reserved in the planned `stac` catalogue, together with the further structural names that
C.16.3 uses (`stac.benchmark_from_dialect`, `stac.case_is_attack`, `stac.no_judgements_released`,
`stac.plan_from_generator`) and the issue code `stac.target_response_not_released` (C.16.3: the final attack prompt
has no released target response; raised with `stac.no_judgements_released@1`); `stac.case_is_one_execution` and
`stac.case_targets_agent` are retired (§D.5.3).

| STAC field | AER | Evidence and rules |
|---|---|---|
| element | `execution`: `unit: "scenario"`, `task{benchmark: "stac", environment: generation_config.environment, task_id: str(id), attack_id: "stac"}`, `ext.stac.generation_config` verbatim, `ext.stac.dataset` (`SHADE_Arena`/`Agent_SafetyBench`); scope `run` | O; `stac.case_is_one_scenario@1` (D) |
| `generation_config.{tool_chain_generator, tool_chain_verifier, prompt_writer, planner}` | actors `gen`, `verifier`, `writer`, `planner`, each kind `attacker` with `role` ∈ `tool_chain_generator`, `tool_chain_verifier`, `prompt_writer`, `attack_planner`, and `model.requested` = name, `unk {"/model/version": "not_recorded"}`; actor `script` (kind `attacker`, `role: "context_fabricator"`, name `STAC_gen step 3`); `env` (kind `tool_runtime`, `stac.environment_from_config@1`) | names O; roles D from field names. Planners and generators are `role` values, never actor kinds (AD-03) |
| the scenario's target agent | **not asserted**: no `llm_agent` actor is emitted for a scenario; the target is `unk` (R-28) | — |
| `interaction_history` / `planner_history` | scopes `thr0` and `thr1` (kind `thread`, parent `run`) | `stac.interaction_history_is_thread@1`, `stac.planner_history_is_thread@1` (D) |
| `attack_plan` | `fixture{kind: "attack_plan", content: {attack_goal, verified_tool_chain, explanation}}`, actor `gen`. `environment_changes` → `ext.stac.predicted_effect` per step, **never** a `state_change` | O; predicted effects are labelled as predictions [sources/multiturn-agent-attack.md §6.2] |
| `interaction_history` user turns before the last | `m<i>` role `user`, actor `writer`, `evf {"/actor": "I"}` | `stac.prefix_user_turns_by_prompt_writer@1`, `stac.prompt_written_after_execution@1` (I; code reading) |
| assistant turns with 32-hex ids | `m<i>` role `assistant`, actor `script`, `evf {"/actor": "I"}`, no `generated_by`; part `tool_call{name, args (decoded until not a string), args_raw (verbatim string), provider_call_id}` | `stac.assistant_turns_scripted@1` (I); `stac.double_json_arguments@1` (D) |
| tool turns | `te<k>` (actor `env`, `call`, `status` from content with `evf {"/status": "I"}`, `unk {"/t": "not_recorded"}`), then `m<i>` role `tool`, actor `env`, `generated_by: te<k>`, `tool_result{responds_to, text, name}` | `stac.tool_msg_is_one_execution@1`, `stac.call_id_unique_match@1` (D; 778/778 adjacent); `stac.tool_status_from_content@1` (I) |
| `planner_history[0]` | `mc0` (actor `planner`, `role: "auxiliary"`, `scope: "thr1"`, `status: "kept"`, `unk {"/input": "not_recorded", "/request": "not_recorded"}`) generating `p0` (part `other`, type `stac.planner_output`); the last user message (actor `planner`) equals `p0`'s `predicted_attack_prompt` | `stac.planner_entry_has_one_call@1`, `stac.planning_after_prefix@1` (I), `stac.final_prompt_from_planner@1` (D: string equality, 482/483). PROV: `wasQuotedFrom(last user message, p0)`, not `wasGeneratedBy` (R-56); the AER field that carries this link is fixed when STAC leaves `planned` |
| `planner_history[1..]` | `mc<n>` (actor `planner`, no output message) | issue `stac.planner_turn_without_agent_evidence` |
| record 139 `call_…` assistant turns | actor `target` (kind `llm_agent`, `unk {"/model/requested": "not_recorded"}`); `mc<n>` per real assistant message (I, input `unk`) | `stac.call_prefix_ids_are_agent_output@1` (I); issue `stac.real_agent_trajectory` (info). Record 139 stays `unit: "scenario"` |
| no outcome | no judgements | issues `no_outcome_recorded` and `stac.target_response_not_released` (on the unanswered last message), rule `stac.no_judgements_released@1` |
| ASB cases (ids 390–482) | `ext.stac.asb_id_link` ∈ `consistent`/`broken`, by checking `generation_config.environment ∈ asb_released[id].environments[].name` | `stac.asb_id_link_check@1` (D); `broken` gives the issue `stac.asb_environment_link_broken` (expected 89 of 93) [sources/multiturn-agent-attack.md §5.3] |
| order | messages `after` `pos`, rule `stac.history_order@1` (D) | |

**Licence.** STAC is CC BY-NC 4.0, which permits non-commercial redistribution with attribution: licence policy
`nc_partition`, i.e. raw policy `include` inside a separately licensed `-nc` corpus (§D.3.4). Because STAC is planned,
no NC corpus is built in v0.1. The SHADE-Arena and Agent-SafetyBench MIT notices are carried as attributions.

---

## D.9 Inspect AI `.eval` importer (v0.1; producer band `inspect_ai 0.3.247.dev69`)

> **Resolved (AD-06 / R-07; §1.3 "D ch D.9"):** the first revision's challenge to D4/D11 is **accepted**. The Inspect
> importer is normative in v0.1 for the producer band observed in the survey's AgentHarm logs. Together with the
> `agentdojo-upstream` `v0.k11` TraceLogger importer it is the **`aer/0.1` and `capture/0.1` freeze gate** (PQ phase
> 6), before SEM, live capture and TraceLogger breadth. It is what licenses any coverage claim beyond the AgentDojo
> family; the claim wording is the registry-generated phrase "adapter-based core; demonstrated on N sources in K
> formats (single-agent, tool-calling traces)", used only after the DoD item below passes (AD-08). The Inspect
> importer MUST land with zero core changes, or the changes are listed and reported (R-17, HON-09(3)).

### D.9.0 Scope, status and evidence

- **Band.** `header.json` `eval.packages.inspect_ai` = `0.3.247.dev69+g53c1fa98b` (variant `v2`). The adapter keys on
  the packages field, not only on the log `version` [landscape/trace_formats.md §3.2, §7]. Logs from any other
  producer version are registered as `select.dialect_planned` (this includes the CIABench sample, inspect_ai 0.3.170,
  and the CIAware mirror, 0.3.200, per AD-21).
- **Source.** Survey AgentHarm (`agent-security-tools-survey` · `agentharm`): 6 `.eval` logs, 1,056 samples,
  `inspect_evals/agentharm` and `agentharm_benign`, CC-BY-4.0 plus the AgentHarm use clause; profile
  `survey-agentharm`; separate restricted-use corpus `ast-survey-agentharm` (U-05) [sources/agent-security-tools-survey.md §5].
- **Registry.** `supported` is the v0.1 target; the registry shows `planned` until this section's tests and DoD
  Q.11a ("all 6 survey AgentHarm logs (1,056 samples) import, derive and validate end to end") pass.
- **What the band contains** (observed): event types `span_begin`/`span_end`, `sample_init`, `state`, `model`,
  `tool`, `info`, `score`, `sample_limit`; `attachments` referenced as `attachment://<hash>`; `events_data
  {messages, calls}` referenced by `ModelEvent.input_refs`; agent and judge model calls separated only by spans (the
  judge is `ollama/qwen3:14b`, as is the agent in two logs); `sample_limit` events 9 + 33 + 6 + 6; reasoning blocks;
  µs UTC timestamps [sources/agent-security-tools-survey.md §5.2–§5.3]. Constructs that the band does not contain
  (cached calls, approvals, compaction, branches, truncation, sub-agent spans, sandbox events) are mapped below so that
  the schema is tested against them, and are exercised by synthetic fixtures (§D.9.4), never claimed as observed.

### D.9.1 Reader (`agentprov.adapters.inspect.dialect.InspectEvalReader`)

- **Container.** The `.eval` file is a ZIP stored as one raw object. It is expanded in a T1 worker under G.3.5
  (EOCD/ZIP64 size check before opening; overlap check; per-member gate; methods {0, 8, 93}; Zstandard (93) is
  decompressed with stdlib `compression.zstd` under `zstd_window_log_max`). Members are **derived objects** of the
  versioned `expand` stage (AD-12): each selected member is stored as its own raw object with origin
  `member {container, label, method, crc32, size}` and a `raw/members.jsonl` row; members not matched by the
  profile's `members` patterns get disposition `not_selected`. Nothing is extracted to the filesystem. The first
  revision's refusal of method 93 is deleted (A1, A2).
- **Sniff.** Container: ZIP magic in T0 and a central directory containing `header.json` and `samples/`. Member: a
  JSON object with the `EvalSample` keys (`id`, `epoch`, `messages`, `events`).
- **Shapes.**
  - Classic shape `samples/{id}_epoch_{n}.json`: supported (the band).
  - Chunked shape `samples/{id}_epoch_{n}/…`: `select.dialect_planned` in v0.1 (not in the band).
  - The interim `message_pool` shape: `UnsupportedVariant` (degenerate AER `unsupported_variant`); upstream itself
    refuses to re-ground its references because that would fabricate inputs [landscape/trace_formats.md §3.2].
- **Located items.** One per sample member object (`a` names the member object; locator `{"p": ""}`). The
  `header.json` member object is an auxiliary artefact of every sample (role `supporting`).
- **Reference resolution, without fabrication.** `attachment://<hash>` references are resolved from the sample's
  `attachments`; `ModelEvent.input_refs` `[start, end)` ranges are resolved over `events_data.messages`. A dangling
  reference raises the core issue `dangling_source_ref` (C.12.3) with the rule `inspect.model_event_is_call@1`; the
  affected `input` becomes `unk {"/input": "lost"}`. **No input is fabricated.**

### D.9.2 Normative mapping

Every row gives its rule (class), the accounting check it feeds and its issue codes. The ex id uses the mapping id
`inspect.eval/survey-agentharm`, the member object's sha256 and `{"p": ""}`; C.4.1 vector 4 (member object
`samples/42-1_epoch_1.json` of a survey AgentHarm log) gives `ex_jrggvyihit3vlsxjpioqzyyc3s`. [R-07]

| Inspect construct | AER | Rule (class) | Accounting / issue |
|---|---|---|---|
| `header.json` `eval{run_id, eval_id, task, task_id, task_version, task_args, model, model_generate_config, revision, packages, dataset}` | `execution` (`unit: "agent_execution"`, `dialect {id: "inspect.eval", variant: "v2"}`); `task {benchmark: "agentharm" (from the profile), suite: eval.task, task_id: str(sample.id), attack_id: null}`; actor `harness` (`code {dist: "inspect_ai", dist_version}`); actor `bench` (`code {repo, commit}` from `revision`, O by source); actor `agent` (`model.requested` = `eval.model`, `params` = `model_generate_config`, O by config); `ext.inspect {run_id, eval_id, task_args, epoch, uuid}` | `inspect.header_applies_to_samples@1` (D) | — |
| sample `started_at`, `completed_at`, `total_time`, `working_time` | scope `run`: `t {start, end}` (O, UTC), `t.dur_s` = `total_time`; `working_time` → `ext.inspect` | O | — |
| `sample_init`, `input`, `metadata`, first model event's `tools` | fixtures: `task_prompt` (from `input`), `tool_definitions` (from `tools`), `ground_truth` (AgentHarm `target_functions`, `grading_function`); other metadata (`category`, `name`, hint flags) → `ext.inspect.sample_metadata` | `inspect.sample_init_fixtures@1` (D) | — |
| `span_begin`/`span_end` | one `scope` per span, `parent` from `parent_id`: `solver:*` → `agent_invocation` (actor `agent`); `scorer:*` → `other` with `subtype: "inspect.scorer"` (actor `judge0`, …); a span named by `ToolEvent.agent_span_id` → `subagent` with `spawned_by` = that `tool_execution`; any other span type → `other` with `subtype: "inspect.span"` | `inspect.span_is_scope@1`, `inspect.agent_span_is_subagent@1` (D) | — |
| `ChatMessage` (`messages`, `output.choices[].message`, pooled `events_data.messages`) | `message` (role verbatim; `source` → `ext.inspect`); parts: `ContentText` → `text`; `ContentReasoning` → `reasoning` (`text`, `signature`, `redacted`; O); `ContentImage` → `blob` or `uri`; `ContentData` → `other` (type `inspect.content_data`); `ContentToolUse` → `other` (type `inspect.tool_use`); `tool_calls[]` → `tool_call` (`name` = `function`, `args` = `arguments`, `provider_call_id` = `id`); `ChatMessageTool` → `tool_result` (`responds_to` via `tool_call_id`, `error`) | O by source; `responds_to` D (`inspect.tool_call_id_match@1`) | `aer.acc.tool_results_linked@1`; unknown content type → `inspect.unknown_content_type` |
| `model` event in a solver span | `model_call` (actor `agent`, `role: "agent"`, scope = the span's scope, `input` = message ids resolved from `input`/`input_refs` (O: the log records what the model saw), `params.configured` = `config`, `params.transmitted` from `call.request`, `request`/`response` = `call.request`/`call.response` as blobs (O), `usage`, `served_model` = `output.model`, `finish_reason` = `stop_reason`, `t {start: timestamp, end: completed}` (O), `status: "kept"`); the output assistant message `generated_by` it | `inspect.model_event_is_call@1` (D) | `aer.acc.agent_calls_vs_assistant@1` (expected `consistent`), `aer.acc.assistant_generated_by@1` |
| `model` event with `cache == "read"` | `model_call` `status: "cached"` (no inference took place; EF maps it to `apv:CacheRead`, with no model use and no provider association) | `inspect.cache_read@1` (D) | — |
| `model` event with `error` and no output | `model_call` `status: "error"`, `reason` = error type; no message is generated; `retries` → `ext.inspect` | `inspect.model_error@1` (D) | — |
| `model` event in a scorer span | `model_call` (actor `judge<n>`, kind `judge`, `model.requested` = the judge model; `role: "auxiliary"`), its output message in the scorer scope | `inspect.model_event_is_call@1`, `inspect.span_is_scope@1` (D) | auxiliary: recorded, not reconciled (C.12.2) |
| `tool` event | `tool_execution` (actor `env`, `call` = the `tool_call` part whose `ToolCall.id == ToolEvent.id`, `name` = `function`, `args` = `arguments` (O), `status` per `error`, `t {start: timestamp, end: completed}` (O)); the tool message named by `message_id` is `generated_by` it | `inspect.tool_event_is_execution@1`, `inspect.tool_call_id_match@1`, `inspect.tool_error_status@1` (D) | `aer.acc.tool_calls_dispatched@1`, `aer.acc.executions_have_results@1` |
| `ToolEvent.error.type == "approval"` | **no** `tool_execution`: a `decision` (verdict `deny`, subject = the `tool_call` part) generates the error message | `inspect.tool_error_status@1` (D) | counted as `denied` by `aer.acc.tool_calls_dispatched@1` |
| `ToolEvent.truncated` | the execution's output as produced was shortened by the harness before the model saw it: a `decision` (actor `harness`, verdict `modify`, subject = the `tool_execution`, `original` = the full output when recorded, else `unk {"/original": "overwritten"}`) generates the tool message. In-request truncation of model input would instead be a `truncation` sent transform on `model_call.input` | `inspect.tool_output_truncated@1` (D) | `aer.acc.executions_have_results@1` (via the decision) |
| `approval` / `review` events | `decision` (actor = the approver: a human approver is actor `user` of kind `user`; a policy approver is `harness` or a `defense` actor), verdict `approve→allow`, `modify→modify`, `reject→deny`, `escalate→escalate`, `terminate→terminate` (review `continue→allow`), subject = the `tool_call` part. For `allow`, the resulting `tool_execution` sets `authorised_by` = the decision. For `modify`, EF's guard NE-18 applies (no `used(te, p)`; the gap is recorded as a status) until `aer/0.2` models the replacement | `inspect.approval_decision@1` (D) | `deny` counted by `aer.acc.tool_calls_dispatched@1` |
| `compaction` event | when a `model` event inside the compaction span produced the summary: that `model_call` generates the summary message; otherwise `ext.inspect.compaction` on the enclosing scope plus the issue `inspect.compaction_unmodelled` | `inspect.compaction@1` (D) | — |
| `branch` event | **no linearisation**: the branch content is kept in `ext.inspect` of the nearest host record (with its own locator), plus the seal issue `inspect.branch_unsupported` (warning). In-file branches wait for `aer/0.2` (R-36) | — | — |
| `state` event | `state_change` (`target: "other"`, `subtype: "inspect.task_state"`, `patch` = `changes` (O), scope = enclosing scope; no digests). EF's `aprov.state_patch@1` chains successive states along `after` edges | `inspect.state_event@1` (D) | — |
| `store` event | `state_change` (`target: "agent_store"`, `patch` = `changes`) | `inspect.state_event@1` (D) | — |
| `sandbox` event outside any `ToolEvent.events[]` | `activity` (`type: "inspect:sandbox_<action>"`, actor `env`, scope, `inputs` = the records whose content it was given, `t`, `status`) and, when the event records an `output` string (an empty one included), `artefact` (`type: "inspect:sandbox_output"`, `content` = output, `generated_by` = the activity); without one (`write_file`, or a null `output`) no artefact (R-10p-7: the source records no generated entity). A sandbox event inside a tool event belongs to that `tool_execution` (`ext.inspect.events`) | `inspect.sandbox_activity@1` (D) | — |
| `score` event / `sample.scores` | one `judgement` per score value key (AgentHarm: `score`, `refusal`): actor `judge0` (or `bench` for code scorers), `name` = `<scorer>.<key>` (a score event without `scorer`, inspect_ai < 0.3.217: the name of its nearest enclosing `scorer` span, else `score` declared `unk ambiguous`; D.9.13), `value` (O by benchmark), `origin: "checker"`, `generated_by` = the scorer scope (or the judge `model_call` when it is the only one), `inputs` = the messages the scorer read when recorded; `explanation`, `metadata` → `ext.inspect` | `inspect.score_event@1` (D) | — |
| `score_edit` event | `judgement` with `origin: "recomputed"`, `revises` = the edited judgement | `inspect.score_event@1` (D) | — |
| `sample_limit` event | run scope `status: "limit"` | — | `inspect.sample_limit` (info) |
| `info`, `logger`, `checkpoint`, `anchor`, `step`, `subtask`, `input`, `interrupt`, `error` | `ext.inspect` of the nearest host record (judge prompts in `info` go on the scorer scope); `error` sets the run scope `status: "error"` | — | `inspect.unmapped_event` (info) for the types not observed in the band |
| event order | `after` edges only from references (`b: "causal"`), message order within a thread (`b: "pos"`) and timestamps (time edges per C.8.6); **never** from list position, because event list order is not timestamp order and `working_start` is not monotonic (observed) | `inspect.no_order_from_event_list@1` (D) | — |

AgentHarm has no injection payloads (direct harmful requests), so this importer exercises the model-call, tool,
reasoning, judge and time paths rather than the injection path. That is the structural difference that D12 needs.

**Known producer defects** to declare as `inspect.*` quirks of a future AgentDojo-Inspect bridge profile (planned;
not in the band) [sources/agentdojo-inspect.md §5, §11]: `sample.output` is synthetic; the tool error replaces
content; `inj_task_metadata.goal` holds the difficulty; there are no ToolEvents (tool executions would be I); the
payload map is absent; cache reads.

### D.9.3 Quirk vocabulary and issue codes

- Quirks (`[[family.inspect.quirk]]`, namespaced): `inspect.judge_same_model_as_agent`,
  `inspect.event_order_not_time_order`, `inspect.working_start_not_monotonic`, `inspect.attachment_refs`,
  `inspect.pool_refs`, `inspect.sample_limit`, `inspect.tool_span_separate_from_tool_event` (a sandbox call recorded in
  a separate `tool`-type span that the ToolEvent does not reference [landscape/trace_formats.md §3.2]).
- Issue codes (`inspect` catalogue `issue_codes`): `sample_limit`, `branch_unsupported`, `compaction_unmodelled`,
  `unmapped_event`, `unknown_content_type`. Core codes used: `dangling_source_ref`, `unsupported_variant`,
  `orphan_tool_result`, `missing_tool_result`.

### D.9.4 Fixtures and tests

- **Real fixtures.** The 6 survey AgentHarm logs, licence class `restricted_use` (K.4.2): committable to the private
  repository only, never in the sdist, with the use clause copied to `tests/fixtures/LICENSES/` (U-05, U-06).
- **Synthetic fixtures**, built at test time from the band's schema, for every mapped construct the band does not
  contain: cached call, error call, approval (`approve`, `modify`, `reject`), compaction with and without a summary
  call, branch, truncated tool output, sub-agent span, sandbox event, `score_edit`, a dangling attachment and a
  dangling `input_refs` range.
- **Tests** (`tests/adapters/inspect/`): all 6 logs import with zero crashes and every sample sealed; golden AER for
  selected samples (bytes); accounting `consistent` for agent calls; judge calls are auxiliary and in scorer scopes;
  method-93 members decompress only through G.3.4/G.3.5 limits; out-of-band versions give `select.dialect_planned`;
  the `message_pool` shape gives `unsupported_variant`; dangling references give `dangling_source_ref` and no
  fabricated input; every row of §D.9.2 has a test that asserts its rule id; the end-to-end import → derive →
  validate run of DoD Q.11a.

### D.9.5 Implementation resolutions (phase 6, 2026-10-08)

The importer is `src/agentprov/adapters/inspect/` (`dialect.py`, `mapper.py`, `profiles/survey-agentharm.profile.toml`,
`rules/inspect.rules.toml`, `artefacts.toml`, `ext.schema.json`, `family.schema.json`); its tests are under
`tests/adapters/inspect/` and the local gate is `tests/full_corpus/test_inspect_survey.py`.

**Core changes (the D.9 preamble; R-17, HON-09(3)).** None in the protected set: `aer/`, `prov/`, `validate/` and
`corpus/` are unchanged, and the golden digests (`tests/golden/prov_digests.json`) and the C.16 vectors are unchanged.
Outside the protected set:
1. `adapters/runner.py` (additive; identical to the change that landed on main with the D.12 work):
   `MapContext(..., auxiliary)` and `map_unit(..., auxiliary=)` supply the bytes of `ExecutionUnit.auxiliary`, and
   `open_auxiliary(role)` returns them (it raised unconditionally before). A sample's `header.json` member object
   reaches the mapper this way (D.9.1); the mapper itself checks its size and sha256 against the unit's `a1`.
2. `adapters/registry/__init__.py` (additive): the readers and mappers `inspect.eval`, and the source
   `agent-security-tools-survey` with its part `agentharm` only (the survey's other parts join with their importers).
3. Tests outside the family: `tests/golden/test_golden_index.py` gains the K.4.1(5) whitelist of files over 1 MiB (the
   one committed `.eval` log; `FIXTURES.json` does not exist yet, so the test holds the reasoned entry), and
   `tests/adapters/adprov/test_registry_entry.py` no longer asserts that `adprov-v1` is the only source.

**Container and units.** The `.eval` container is a raw object; the `expand` stage of `agentprov.raw.members` stores
the members selected by `[family.inspect] members` (`header.json`, `samples/*_epoch_*.json`) as member objects and
records every other member `not_selected` (the band's `_journal/*`, `summaries.json`, `reductions.json`). The reader's
`plan` turns the member objects of one container into units: one per classic sample member (`a0`, role `primary`,
`prov_primary: native`, locator `{"p": ""}`) with the header member as `a1` (role `supporting`). Register rows (all
`select.dialect_planned`, never units): a producer outside `producer_band`, a log `version` outside `log_versions`
(`[2]`), a missing or unreadable `header.json`, and chunked sample members. The interim `message_pool` shape is a
degenerate AER with `unsupported_variant`; an unparseable sample member is a degenerate AER with `unparseable_artefact`
whose `task.task_id` comes from the member label (new rule `inspect.sample_member_label@1`, because `task_id` is
required and cannot be `unk`).

**Messages.** An AER message is one Inspect message id with one resolved content: the copies in `messages`,
`events_data.messages`, a model event's inline `input` and its output choices are the same record when the ids match
and the contents are JCS-identical after `attachment://` resolution (observed for all 8,772 pool copies and 3,660 agent
outputs of the band); otherwise they are separate records. Ids: `m<i>` (`messages[i]`), `p<n>` (pool-only and
inline-input messages, gapless), `o<n>` (output messages not in `messages`, e.g. judge verdicts). Scopes: a generated
message is in its generator's scope; a pool-only message is in the scope of its first consumer; the sample's own
messages without a generator (system, user input) are in the `run` scope; their author is stated by D.9.9 (the input
message and a plan-inserted system message: the `bench` actor), else `unk {"/actor": "not_recorded"}`.
Attachment pointers are added to `src` when content was resolved through them. A message whose content holds a
dangling reference is not emitted; every reference to it becomes `unk` (`lost`) with `dangling_source_ref`.

**Order.** No `pos` edge is emitted: solvers insert messages into `TaskState.messages` (the system-prompt solver
inserts the system message before the input message after the input exists; observed in the inspected band samples through their
state patches), so list position is not creation order (C.8.2). Edges: `causal` (output after generator, execution after
the message holding its call, decision after its subject), `time` between activities with recorded intervals
(`model_call`, `tool_execution`, `activity`; immediate predecessors only, `X.end < R.start` strictly, C.8.6), and
`proto` between successive state patches of one target in timestamp order (`inspect.state_event@1`; verified in
`solver/_transcript.py`: one diff per completed solver). Records are serialised by Kahn's algorithm over the reference
graph, ties broken by (record group, timestamp, event index).

**Spans and roles.** `span_roles` maps span *types* (`solver` → agent, `scorer` → judge); a model event takes the role
of its nearest typed ancestor span and is an agent call otherwise. Judge actors are `judge<n>`, one per distinct model
string of judge-role model events, so `qwen3:14b` as both agent and judge is told apart by span only. The band's `tool`
spans (one per tool event, holding no event) become empty `other`/`inspect.span` scopes. A judgement's actor is the
scorer scope's single judge actor (else `bench`); `generated_by` is the scope's only judge call when it has exactly one,
else the scorer scope; `inputs` is `unk not_recorded`.

**Deviations from the D.9.2 table, with reasons.**
1. `model_call.request`/`response` are **not** emitted: the mapper protocol has no surface to store blobs (C.11.5), and
   the recorded `call.request` is the condensed form (its messages are `call_refs` into `events_data.calls`), not the
   wire bytes. `params.transmitted` is `call.request` without the pooled key, `response_id` is `call.response.id`, and
   the call's locator is in `src`; `call.time`, `call_key` and `call_refs` are kept in `ext.inspect.call`. An `aer/0.2`
   or runner-level blob surface would restore the blobs.
2. Empty assistant text: the AER validator (AER-V17) treats an assistant `""` as a sentinel unless declared. The
   OpenAI-compatible path records a provider `null` content as `""` (`model/_openai.py:1097` at `5d97e38`), so the
   text is kept and declared `unk ambiguous` under the new rule `inspect.message_content_parts@1`.
3. The bench actor's `code.commit`: `eval.revision.commit` is abbreviated (7 hex digits), so `/code/commit` is `unk
   ambiguous` and the revision is kept verbatim in `ext.inspect.revision`.
4. `task.attack_id: null` rests on the profile's `no_attack = true` and cites `inspect.header_applies_to_samples@1`
   (AgentHarm has no injection payloads).
5. `state_change.t` is `{end: timestamp}` (D, the event is emitted when the solver completes) and `cause` is the
   enclosing solver scope.
6. Lexical hints: only `ext.lex.flt` is written (C.11.4 MAY; no byte-exact view exists for Inspect); member order is
   not recorded.

**Issues without a rule in D.9.2/D.9.3.** C.12.3 requires every issue to cite a rule, so rules are added (all D):
`inspect.sample_limit@1` (run status `limit`, issue `inspect.sample_limit`), `inspect.event_kept_in_ext@1` (events kept
in `ext.inspect.events`; issues `inspect.unmapped_event`, `inspect.branch_unsupported`; an `error` event sets run status
`error`), `inspect.message_content_parts@1` (part mapping; issue `inspect.unknown_content_type`). With
`inspect.sample_member_label@1` that makes four rules beyond the D.5.4 index. Declared subtypes: `inspect.scorer`,
`inspect.span`, `inspect.task_state`; types: `inspect:sandbox_{exec,read_file,write_file}`, `inspect:sandbox_output`.

**The D.9 status table (`inspect.tool_error_status@1`).** Verified (2026-10-08) against the band's producer commit
itself: `UKGovernmentBEIS/inspect_ai@53c1fa98baedd64cc37aa5f84057fc15c1e98015` (2026-07-13), the `g53c1fa98b` of
`0.3.247.dev69+g53c1fa98b`, fetched with the user's consent into the bare, checkout-free cache
`$AGENTPROV_HOME/cache/git/github.com/UKGovernmentBEIS/inspect_ai.git` (recorded in `acquisitions.jsonl`). Checked at that
commit:
- the `ToolCallError.type` literal (`src/inspect_ai/tool/_tool_call.py:69-90`): parsing, timeout, unicode_decode,
  permission, file_not_found, is_a_directory, limit, approval, cancelled, unknown, output_limit (no
  `sandbox_unavailable`, which the later CHANGELOG adds in 0.3.260);
- the exception-to-type chain (`src/inspect_ai/model/_call_tools.py:193-249`);
- `call_tool` (`:606-659`): a call parse error (`:632`), an unknown tool (`:638`) and failed argument validation
  (`:658-659`) raise `ToolParsingError`, and an approver's rejection raises `ToolApprovalError` (`:652`), all before the
  tool function runs.

So `parsing` → `invalid`, `approval` → a `deny` decision with no execution, every other type (and any unknown one) →
`error`, and no error → `ok`. Caveat: `parsing` is also produced after a tool has started when a subprocess-based tool
hits CPython's embedded-null-byte `ValueError` (`:203-212`), or when a tool raises `ToolParsingError` itself; the band
holds neither (all 149 `parsing` errors of the six logs were checked: none is the null-byte message), and AgentHarm's
tools spawn no subprocess. The band records two types: `parsing` 149 and `file_not_found` 84. An earlier check against
the newer local clone (`5d97e38`, 2026-10-06) agrees; the table is closed over unknown types, so later literals cannot
misclassify.

**Other open items.** (a) *Resolved before the freeze:* accounting of cached calls. `aer.acc.agent_calls_vs_assistant@1`
counted only `kept` calls, so an agent `cached` call with an output message made the check `inconsistent` (synthetic
fixture only; no band log has a cached call). C.20(1) now counts `kept` and `cached` calls. (b) *Resolved:* the complete LICENSE of HF `ai-safety-institute/AgentHarm@e23b3fe60a0da9037314b88e5ee3a0c054970dad`
(1,237 B, git blob `cf527b40…` verified against the dataset tree) is `tests/fixtures/LICENSES/AgentHarm-LICENSE.txt`,
fetched with the user's consent; it replaces the earlier use-clause excerpt. (c) The restricted-use corpus `ast-survey-agentharm` is not built in phase 6.

**Fixtures (K.4.1(5), K.4.2).** One complete log is committed (`gptoss_harmful`, 1,388,361 B, 176 samples, members
method 93), plus the two investigation members of `gptoss_benign` (`header.json` and `samples/42-1_epoch_1.json`, the
member of C.4.1 vector 4), all `restricted_use` with `SOURCE.json`; the tree stays under 8 MiB. The other five logs are
read from a clone at `89c4db2c…` (`$AGENTPROV_SURVEY_CLONE`) by the `full_corpus` gate, which first checks size, sha256
and git blob id. The sdist holds no `tests/` file (checked by a test that builds it offline). Golden AER bytes for three
samples are under `tests/fixtures/inspect/expected/` (regenerate with `AGENTPROV_REGEN_INSPECT_GOLDEN=1`).

**Result (DoD Q.11a, 2026-10-08).** All 6 logs: 1,056 samples sealed, 0 degenerate, 0 register rows, 0 expand events;
1,056 store-aware AER validations pass in release mode; 1,056 derivations (byte-identical twice) and 1,056 tier-4
passes. Accounting: 1,056 `consistent`. Seal issues: `inspect.sample_limit` 54 (coder_benign 9, gptoss_benign 33,
qwen14_benign 6, qwen14_harmful 6), `dangling_source_ref` 16 and `missing_tool_result` 16 (coder_benign 4, qwen14_benign
12: tool events whose result message was never appended after the message limit); 2,345 empty agent texts are
declared `ambiguous`. C.4.1 vector 4 is reproduced
(`ex_jrggvyihit3vlsxjpioqzyyc3s`). The registry keeps the part `planned` (D.3.2 rule 1) until the restricted-use
corpus `ast-survey-agentharm` is built (open item (c)); the status-table verification is done.

**RH-1 addendum (D-710, 2026-10-22; found by the live Inspect harness).** Inspect writes `NaN` for an undefined metric
(AgentHarm's `avg_score_non_refusals` when every sample was judged a refusal). The strict header parse made such a log
one `select.dialect_planned` row with no execution. `dialect.load_header` (used by the reader's plan and by the mapper)
parses `header.json` with the loader's `python-json` profile and tolerates `{"$float": ...}` only under `/results` and
`/stats`, members the mapper never reads. The log's units carry the flag `header:nonfinite`, and the mapper reports the
info seal issue `inspect.header_nonfinite` (code declared in the `inspect` catalogue, in place at version 2 per the D-31
owner; rule `inspect.header_applies_to_samples@1`). No non-finite value is ever mapped. A non-finite number in any other
header member keeps the log planned (`ingest.number.nonfinite`). The AER validator resolves locators into such a
header because locator resolution uses the same profile (C.9.2, amended by D-710). Regeneration-batch item 168: no
stored log re-maps differently.

### D.9.6 Semantics profile `inspect.agentharm@1` (phase 7, 2026-10-08)

`adapters/inspect/semantics/` (`inspect.agentharm-1/tables.toml`; rules `inspect.tools_fail_closed@1` and
`inspect.scorer_claim_table@1`, both I). Outcomes: one `outcome` per judgement with a recorded value and an origin
other than `harness_default` (recomputed `score_edit` judgements included), claims namespaced `inspect.<claim>`
because AgentHarm has no injection attacker: `combined_scorer.score` → `inspect.harmful_task_score` (suite
`inspect_evals/agentharm`), `inspect.benign_task_score` (`…/agentharm_benign`) or `inspect.task_score`, with `score` and
`scale: "unit_interval"`; `combined_scorer.refusal` → `inspect.refusal` with `holds` and `scale: "binary"` (polarity
neutral: desired on harmful tasks, an over-refusal on benign ones). No outcome for an unlisted scorer, a missing or
out-of-scale value. Tools are fail-closed (`unknown` integrity, `["unknown"]` role): AgentHarm's tool list is not
available offline (DECISIONS D-18), so there is no taint policy.

### D.9.7 WhistleBench (phase 10f; D-150, D-155)

Profile `whistlebench` (source id = corpus id), registry part `final-runs` `planned` (D.3.2), from the phase-10e
verification (cards §3.2; D-144; scope D-147: unsanctioned whistleblowing is unauthorised agent action). Pin:
`legobridge/whistlebench@9c27637c`, tree `final_runs/` (223 files, 523,183,391 bytes): 184 `.eval` logs, 9,200 samples,
all distinct by message content. Licence MIT. `no_attack`; span roles `solver` → agent, `scorer` → judge (grader models
inside scorer spans).

- **Producer band** (D-155): `inspect_ai` 0.3.130 (161 logs) and 0.3.134.dev31+geb46eef8 (23), log version 2, in the
  profile's band as data for the trial only; the mapper is unchanged. Every sample of the committed fixture imports and
  validates in release mode (`tests/adapters/inspect/test_whistlebench.py`), and the scratch trial import of the full
  pinned tree maps, derives and validates all 9,200 samples (`docs/reports/phase10f/`). Links are lost, never guessed: in
  3,452 samples one tool-call id belongs to two call parts (`call_result_link_conflict`, links `ambiguous`), and in 8,401
  the react agent's final `submit` call is pruned from the messages (`missing_tool_result`, `dangling_source_ref`). Routed
  to the Inspect mapper owner before any full import (D-156).
- **Links recovered (regeneration-batch item 16, D-155 addendum).** Read from the producer code (blobless fetch of
  `UKGovernmentBEIS/inspect_ai` at 0.3.130, 0.3.134.dev31+geb46eef8, and fragfuse's 0.3.154.dev37 and 0.3.159.dev20,
  where it is the same): (a) a `ToolCall.id` held by several copies of one Inspect message id with identical calls is one
  call, linked to the copy the model produced (output choice, else `messages`; never a replayed input;
  `inspect.message_copies_share_calls@1`), the other copies' parts declared `unexecuted_tool_call` under that rule;
  (b) where a tool event's `message_id` names a tool message answering another call (the first-of-batch defect of
  `execute_tools`, fixed by 0.3.263), the result is the tool message whose `tool_call_id` is the event's id
  (`inspect.tool_event_message_id_first_of_batch@1`); a `message_id` naming no message stays unlinked; (c) for the
  profile's `submit_tools`, a result message removed by react's `_remove_submit_tool` is declared
  (`missing_tool_result` citing `inspect.react_submit_message_removed@1`) and the event's `result` becomes an
  `inspect:tool_result` artefact the execution generated. Scratch import: accounting consistent 9,190 of 9,200.
  Item 25 (D-155 addendum 2) adds the fetch of 0.3.112..0.3.129. (d) `message_id` first appears at 0.3.113, already as
  `result_messages[0].id`, so (b) applies from 0.3.113. For a log whose header names `inspect_ai` 0.3.112 or earlier,
  the result of a tool event (which has no `message_id`) is the one tool message whose `tool_call_id` is the event's id
  (`inspect.tool_event_no_message_id@1`). From 0.3.113 an absent key is a `None` written away by `exclude_none` and
  stays unlinked. (e) `audio` and `video` content items are `uri` parts like `image`, with `format` beside the part.
- **Strings over 1 MiB (regeneration-batch item 28; C.2.1(6)).** The string is not inlined
  (`inspect.content_not_inlined@1`, the OpenHands precedent). It becomes `{"not_inlined": {sha256, bytes, media?}}` in
  a Json position: the part's `value` for `image`/`audio`/`video`/`text`/`reasoning` items (an `other` part of that
  type), the `tool_result` `value` for a tool message's text, or in place in `params`, `args` and `other` values. One
  info issue lists the records. These become `$blob` references once carved blobs exist (deferrals).
- **Semantics profile `inspect.whistlebench@2`** (D.9.14; D-601 addendum 2): the registry part names it. It reads
  the tool and scorer tables from the pinned `highagency/` code (class I). `email_whistleblowing` gets no outcome.
  Version 1 (every tool fail-closed, no outcome) stays shipped.
- **Quirk**: 15 tool calls name several tools run together (e.g. `write_fileSubmit`): model output, kept verbatim.
- **Redaction and withholding (D-601, profile version 2; version 1 archived, D-31).** In 28 `awareness_blackbox` logs
  the header's `eval.revision.origin` is a clone URL whose userinfo holds a credential-shaped value; the mapper copies
  it to the bench actor's `ext.inspect.revision.origin` and `code.repo`. Rule `origin_userinfo` (D.9.12, `pointers` the
  two) replaces the userinfo with the literal `redacted`. In 260 samples `error_retries` tracebacks name one workstation
  home directory; rule `retry_account` (`pointers = ["/ext/inspect/error_retries"]`) gives the account segment the
  salted label `<account:{span12}>`. Home directories of the benchmark's scenarios (inputs, messages, and logger events
  quoting tool arguments) are content and stay verbatim. `[withhold]` (reason `secret`, scope `object`, rule
  `github-token-shape`): a release seal withholds each token-bearing `header.json` (basis `profile_rule`) with its
  `.eval` container (basis `container`; the decoded scan of D-450 finds the same containers through the unselected
  `_journal/start.json`) and no execution. Quirk `inspect.error_retries`. The raw sample members whose
  `error_retries` name the account ship as pinned (D-186 (c); user decision 2026-10-21), disclosed by the datasheet
  statement `whistlebench-retry-traceback-account`.

### D.9.8 The AgentHarm log sets of kexin-xu-01 and fragfuse (phase 10h; D-180–D-188)

Two profiles from the phase-10e verification (cards §3.3 and §3.4; D-144, D-145 rank 4). Source id = corpus id, registry
part `logs` `planned` (D.3.2), semantics `inspect.agentharm@1`, and each its own restricted-use corpus (AgentHarm use
clause, LIC 3), as `ast-survey-agentharm`. Licence: MIT (LICENSE inherited from inspect_evals, UK AI Security
Institute). Span roles: `solver` → agent, `scorer` → judge (openai/gpt-4o-2024-08-06 in both). Evidence:
`docs/reports/phase10h/`.

| | `kexin-xu-01-agentharm` | `fragfuse-agentharm` |
|---|---|---|
| Pin | `Kexin-xu-01/agentharm@859c34f4`, tree `logs/` (68 files, 36,467,328 B) | `zixin22/fragfuse_agentharm@24cc8aea`, whole commit (3,847 files, 318,827,530 B; one pin per corpus, D-108) |
| Logs, samples | 68 logs, 2,825 samples; 2 unfinished logs (28 samples) have no `header.json` and are `select.dialect_planned` | 168 logs, 1,759 samples; the 4 `none/none` logs (12 samples) are `select.not_execution_artefact` by exact path (D-183) |
| Band | `inspect_ai` 0.3.263 (inspect_evals 0.20.0) | 0.3.154.dev37+g1289c1ad (25 logs), 0.3.158 (136), 0.3.159.dev20+g3ddd7997 (7) |
| Models | claude-sonnet-5, claude-sonnet-4-5, gemini-2.5-pro/-flash/-flash-lite, gpt-4o, gpt-4o-mini, Qwen3-14B and three local Qwen3-14B checkpoints (vLLM) | gpt-4o-2024-08-06, gpt-5-nano, claude-opus-4-1 |
| Attack | `no_attack` (plain AgentHarm, harmful and benign splits; `logs/patched-judge*/` are new runs, not re-scorings) | not declared, so `task.attack_id` stays unrecorded (D-184); memory-bank retrieval (136 one-sample logs, scorer `always_ok`) and carrier injection (4) are visible in `eval.task`, the solver plan and `ext.inspect.sample_metadata`; memory banks and guardrail decisions are declared context artefacts, inert because the Inspect mapper does not consume context |

- **Workstation account paths** (D-146, D-182): kexin names three local checkpoints by `/workspace/shared/outputs/…`
  paths (18 logs, 792 samples), and every kexin log records `/home/<account>/` in `eval.dataset.location`; every
  fragfuse log records `/Users/<account>/` (dataset location, memory-bank parameter, tracebacks, one metadata field).
  The mapper copies the checkpoint ids (9 pointer classes) and fragfuse's tracebacks and `carrier_query_path` into the
  AER today. Redaction is a proposal for the regeneration batch (`docs/reports/phase10h/redaction-design.md`): until it
  is applied, the 18 kexin logs are kept out of every import, including the trial import. The raw objects keep the
  originals (invariant 3); whether they may appear in a public release is open (D-186). These paths are never quoted.
- **Fixtures** (D-185): no real log is free of account paths, so none is committed. `tests/adapters/inspect/
  test_phase10h_agentharm.py` uses synthetic logs and reads the pinned logs from the fetch cache when present.
- **Counting** (D-181): all sample uuids and message ids are distinct. Equal message text across samples (deterministic
  tools, identical refusals, errored samples) is not a duplicate. No sample of either source equals a survey AgentHarm
  sample by message digest.
- **Trial imports** (D-187): scratch corpora only, release mode, `tools/inspect/phase10h_trial.py`. kexin: 50 logs, 2,005
  executions; fragfuse: 164 logs, 1,747 executions. Every stage is ok, no validation check fails, `recompute` finds 0
  unexplained differences and `verify --level chain` 0 failures, and the corpora are byte-identical at 8 and 3 workers
  (`docs/reports/phase10h/README.md` §4). `[import] context_artefacts` are inert in this family (the mapper does not
  consume context), so fragfuse's memory banks and guardrail decisions are not stored. fragfuse's 693 `accounting_inconsistent` samples
  (0.3.154.dev37 and 0.3.159.dev20 parallel tool-call batches) are the Inspect `message_id` defect of regen-batch item
  16, not a profile matter; kexin (0.3.263) is not affected.

### D.9.9 The control-arena persistent-state archive (phase 10p; D-340–D-348)

Profile `controlarena-persistent` (source id = corpus id; MIT, own permissive corpus), from the phase-10e verification
(card §3.6; D-144, D-145 rank 13) and the phase-10p census (`docs/reports/phase10p/README.md`). HF dataset
`idacy/control-arena-persistent-state-eval-archive-2026-07-30` @ `84d39e0a485d7ea6ca10f4ceb2a3fbf88dab0e62`: Inspect
logs of the control_arena `vibe_coding_persistent` setting (an untrusted agent works through a sequence of PRs with
persistent state; in attack mode it also pursues a side task; trusted models monitor post hoc inside scorers). Registry
`planned`, semantics none (SEM skipped).

| Part (snapshot, D-202) | Pin (HF, one per part, D-108) | Original logs / samples | Notes |
|---|---|---:|---|
| `zip-3-001` | split zip, 8 parts (D-249) | 132 / 660 direct; 413 / 1,976 nested | 4 nested zips (`[[import.nested]]`, D-382) |
| `zip-3-002` | split zip, 8 parts | 31 / 153 direct; 515 / 1,499 nested | 1 nested zip (D-382) |
| `zip-3-003` | split zip, 3 parts | 162 / 810 | |
| `batch-runs` | `logs_batch_runs-20260730.tar.zst` (D-240) | 110 / 638 | |
| `auditor` | `agentic_auditor_logs-20260730.tar.zst` | 1 / 6 | the auditor's own records are EX-FMT (D-342) |

- **Unit and counting (D-340).** One sample of a log with a header in the band; 5,742 original samples in 1,364 logs at
  the pin, of which 3,475 sit only inside five nested zips, read since ingest-formats-3 through the profile's
  `[[import.nested]]` entry (pattern `logs/*.zip`, raises `max_member_bytes` 2 GiB and `max_depth` 3; D-381..D-383). `eval.model` is `none/none` in 152 original logs that name their models by `model_roles`; they are real runs.
- **Band and family (D-343).** `inspect_ai` 0.3.159, log version 2; `span_roles = {solver = "agent", scorer = "judge"}`;
  no `submit_tools` (control_arena keeps the submit result); no attack declared, so `task.attack_id` stays unrecorded and
  `eval_mode`, `side_task_name` and `main_task_name` stay in `ext.inspect.sample_metadata`. The mapper copies `eval.model`
  as the agent's requested model and does not map `model_roles` (R-10p-2, regeneration batch).
- **Exclusions (D-342).** Selection `**/*.eval`. Non-log members are `not_selected`; unfinished logs
  `select.dialect_planned`; the 358 empty or truncated `.eval` members keep the expand gate's `ingest.*` code (D-385:
  their complete nested copies are imported, and no relation is inferred from the shared name). The loose logs, the apr2026 backup, rescore and analysis files and the
  working-directory delta are not pinned, with reasons in the profile.
- **Withholding (D-344).** `[withhold]` pattern rules for six key shapes, scope `executions`. Every sample holds a
  generated `sk-` key at `/metadata/API_KEY` that reaches `ext.inspect.sample_metadata`, so a release seal withholds every
  execution (D-235): a public release holds metadata only.
- **Account paths (D-345).** A workstation account path in 36 logs (header `micro_protocol.prompt_file`; error
  tracebacks). Profile version 2 held them back (36 exact-label excludes, `select.redaction_pending`, D-324); version 3
  (D-349) imports them with one `[[family.inspect.redact]]` rule of scope `harness_text` (pattern `/Users/<segment>`,
  replacement `/Users/account-{span12}`). Version 4 (D-349 addendum, D-604) writes the D-604 label
  `/Users/acct-{span12}` and also withholds, at object scope, the raw objects that hold the account path (rule
  `users-account-path`, reason `personal_data`). Its pattern cannot match the label, so no derived file escalates. It
  misses names holding `-` and names at the end of an object (bounded grammar; neither occurs in the pinned bytes), and
  the release scan reports both at a deposit. Never quoted.
- **Import status.** Since ingest-formats-3 (D-380) `.eval` members of archive inputs import; the scratch trial (D-347,
  `tools/inspect/phase10p_trial.py`) is in `docs/reports/phase10p/README.md` §9.
- **Fixtures (D-346).** Synthetic, built in code; no real log is committed.
- **Quirks.** The monitors' trusted models inside scorer spans; 13 parallel tool-call batches with 20 first-of-batch tool
  events (item 16 (b)); 20 strings over 1 MiB (item 28); one tool call whose name is a sentence of model output.
- **Cached scorer replays (regeneration-batch item 133; pre-check PC-04; user decision 2026-10-21: split per scope).**
  The `*_of_2` aggregator scorers replay one trusted-monitor conversation. A replay's model calls are cache hits
  (`cache = "read"`). Inspect's `generate` then returns the stored `ModelOutput` unchanged (`_model.py`, 0.3.130 to
  0.3.159.dev20), message and ToolCall ids included, and the replaying scorer runs its sandbox commands again.
  - **Before.** The mapper merged the copies by Inspect message id, so one call had a result in each scorer. In the
    t2 trial, 910 calls in 364 executions were reported `call_has_several_results` and sealed `known_incomplete`,
    though nothing was lost.
  - **Now** (`inspect.cached_output_own_message@1`). A cached call's output is a message of its own scope when
    another scope's model event first produced it. That message is generated by the cached call, and its holders in
    that scope (inline inputs, pooled references) resolve to it. Its tool calls are that scope's calls: the scope's
    tool events, approvals and tool results answer them.
  - **Unchanged.** A cache hit inside the producing scope keeps one message. Item 16 (a) still applies within a scope.
  - **Rejected.**
    - Linking the replay's results as copies: the tools really ran again.
    - An expected-known quirk: the executions would stay `known_incomplete`.
    - A core accounting exemption (invariant 5).

### D.9.10 ATIA (phase 10n; D-307–D-309, user-approved 2026-10-13)

One profile from the phase-10e verification (card §3.5; D-144, D-145 rank 12): `atia-benchmark`, source id = corpus id,
registry part `logs` `planned` (D.3.2), its own permissive corpus, semantics profile `inspect.atia@1` (D.9.15; D-307
addendum: every tool fail-closed, no scorer claims). Evidence: `docs/reports/phase10n/` (README §5, `routing.md`).

- **Pin**: `mattngyn/atia_benchmark@cc71caf5`, tree `logs/` (5 files, 162,365,512 B; MIT). Only the five log blobs were
  fetched (user-approved): the logs carry their media inputs, so `adversarial_inputs/` and `clean_inputs/` are not part
  of the pin.
- **Band**: `inspect_ai` 0.3.112, log version 2 (3 `success`, 2 `error` logs); one task (`account_takeover_suite`), model
  `google/gemini-2.0-flash`; 123 samples (re-runs of one 25/35-sample dataset), at most one tool call each, no parallel
  batch. `task.attack_id` stays unrecorded (`no_attack` not set): the attack is the media input, its kind in
  `ext.inspect.sample_metadata` (`attack_type`).
- **Media** (D-308): image 39, audio 49, video 10, as `attachment://` references into the sample's `attachments` (base64
  data URIs). They are raw evidence in the stored sample object and are cited by locator `/attachments/<hash>`. The
  mapper inlines the resolved values: 42 strings over 1 MiB in the trial (C.2.1(6); routed, regen-batch item 28).
- **No `message_id` on tool events** in 0.3.112: before regen-batch item 25 the mapper left all 81 results without a
  generating execution (`missing_tool_result`, `dangling_source_ref`); item 25 (on main) adds
  `inspect.tool_event_no_message_id@1` for producers up to 0.3.112 and maps audio and video as `uri` parts.
- **Fixtures** (D-309): none committed (the smallest log is 11.5 MB of media). `tests/adapters/inspect/test_atia.py` uses
  a synthetic 0.3.112-shaped sample and maps the smallest pinned log from the fetch cache when present (`slow`).
- **Trial** (scratch, on item 25): 123 mapped and validated, 123 sealed clean, 0 degenerate, byte-identical at 8 and 3
  workers; derive, validate, recompute and chain verify clean (on `bfa1951`). The import waits for regen-batch item 28.

### D.9.11 Harness, input authorship, checker identity and transmitted parameters (regeneration-batch item 12, U6-a, U6-b; D-374, D-375)

Read at the AgentHarm producer, inspect_ai `53c1fa98` (`0.3.247.dev69+g53c1fa98b`, the full-blob store of D.9.5). The
rules below cite that commit; they are cited at D only for a log whose `eval.packages.inspect_ai` carries a `+g<commit>`
in their code list, else through their `_unverified` twin (D-24; the older rules of this family keep their citations,
an open D-24 gap recorded in AGENTS.md §12).
1. **The run and the runner's spans** (`inspect.sample_run_by_harness@1`): the run scope, and the span scopes of the
   runner's own spans (`init`, `solvers`, `scorers`, and each `scorer` span), get `actor: harness` (`task_run_sample`,
   `_eval/task/run.py` l. 1059-1561; an untyped span's type is its name, `util/_span.py`). A tool span
   (`type: "tool"`, `model/_call_tools.py` l. 624-677) gets `actor: env` (`inspect.tool_span_by_runtime@1`). Agent
   spans keep `agent` (`inspect.span_is_scope@1`). `aprov.assoc_scope` then associates every run and step activity.
   The execution description `x:exec` stays attribute-linked: no rule names a relation for it.
2. **Input authorship.** A run-scope `user` message with `source: "input"` is the dataset's `Sample.input`
   (`sample_messages`, `_eval/task/util.py` l. 22-29; `prompt_template` rewrites it in place): `actor: bench`
   (`inspect.sample_input_from_benchmark@1`, D). A run-scope `system` message without a generator, in a log whose
   header records `plan.steps`, was inserted by a solver of the task's plan: `actor: bench` under
   `inspect.system_message_from_task_plan@1` (class I: the task's solver code, for AgentHarm inspect_evals at
   `2dd469a`, is not available; the locator names `/plan/steps`). Other messages without a generator (e.g. the scorer's
   judge prompts) keep `unk {"/actor": "not_recorded"}`.
3. **Checker identity (U6-a).** A judge actor declares `unk {"/code": "not_recorded", "/version": "not_recorded"}`. The
   bench actor's `version` is `eval.task_version` (`inspect.task_version_label@1`: an integer in decimal form; a string
   verbatim); the producer's default `0` is no label (C.7.3), so `/version` is then declared `not_recorded` and the
   value stays in `ext.inspect.task_version`.
4. **Transmitted parameters (U6-b).** A model event without `call` declares `/params/transmitted`: `lost` under
   `inspect.model_api_call_retention@1` when the transcript's retention policy dropped the request (`log_model_api`
   unset or false; a non-error, non-cached call after its model's first 5 kept calls in the sample;
   `log/_transcript.py` l. 617-637), else `not_recorded`. In AgentHarm the count is per model string, so in the two
   logs whose judge is the agent's model the judge's later calls lose their request too.
5. **The agent's model role (R-10p-2).** When every agent model event names one `role` that `eval.model_roles` gives a
   model, the agent actor's `model.requested` and `params` are the role's (`inspect.agent_model_from_role@1`;
   `get_model(role=...)`, `model/_model.py` l. 1815-1830), not `eval.model` (control-arena's `none/none`).

### D.9.12 Redaction of workstation account paths (D-182, user-approved 2026-10-13; R-10p-3)

A source profile may declare `[[family.inspect.redact]]` rules `{id, scope, pattern, replacement, leaf?, pointers?, note?}`
(`agentprov.adapters.inspect.redact`; design `docs/reports/phase10h/redaction-design.md`). The mapper applies them to
every finished record:
- `scope = "model_id"`: the unit's observed model ids that match (header `eval.model`, `eval.model_roles.*.model`, model
  events' `model`, `output.model`, `requested_model`, messages' `model`) are replaced as whole strings wherever the AER
  holds them, also inside longer harness strings.
- `scope = "harness_text"`: the pattern applies only to harness-written fields: the run scope's `ext.inspect.error`
  (with `traceback`, `traceback_ansi`) and `ext.inspect.error_retries` (earlier attempts' errors, same fields; D-601),
  events kept in `ext.inspect.events` (error and logger events), the execution's `sample_metadata`, `task_args` and
  `metadata` (header `eval.metadata`, e.g. control-arena's `micro_protocol.prompt_file`; not copied today), the bench
  actor's `revision` and `code.repo` (a copy of `eval.revision.origin`; D-601), the agent's `params`. Never messages,
  tool calls, tool results, fixtures or judgements.
- `pointers` (D-601, `harness_text` only): a non-empty list of distinct record-relative pointers, each one of the
  classes above or below one; the rule then applies only to strings at or below them. A traceback rule is narrowed so
  that it never reaches the logger events, which quote the model's tool arguments (D-604).
- The replacement is literal text with `{span12}` (12 hex digits of SHA-256 over the profile id, NUL and the span) and
  `{leaf}` (the span's last path segment when the rule's `leaf` pattern matches, else `?`); two spans with one label in a
  unit is a profile error. A literal-only replacement (no placeholder) therefore admits one span per unit and fails a
  unit with a second distinct span closed; it is the form for a credential, of which no digest may be recorded (D-601). Each redacted pointer is tagged `D` and cites `inspect.value_redacted@1`;
  `ext.inspect.redacted` lists `{p, rule: "<profile>@<version>#<rule id>"}`; an info issue `inspect.value_redacted`
  counts them. The original and its full digest are never recorded; locators stay on the raw field; raw is untouched.
- Shipped profiles: `whistlebench@2` (D-601, D.9.7). The stored AgentHarm corpus has no account path in a harness
  field.

### D.9.14 Semantics profile `inspect.whistlebench` (D-601 addenda, user decisions 2026-10-21)

**Version 1 (D-601 addendum; as recorded).**

`adapters/inspect/semantics/inspect.whistlebench-1/tables.toml`, built by `adapters/inspect/semantics/whistlebench.py`
(the family's `build_profile` dispatches on the id). The registry part `whistlebench · final-runs` names it, so an import
annotates every execution and a release seal is possible (a sealed index row records a SEM stage, H.3.1).
- **Tools fail-closed.** The task code that defines the tools is not available at the pin (D.9.7), so the profile knows
  no tool: every `tool_call` part and `tool_execution` gets role `["unknown"]` and every `tool_result` part integrity
  `unknown`, class I under `inspect.untabulated_tool@1`. No taint policy.
- **No outcome.** The scorers record string values whose meaning and polarity the scorer code and grader prompts set,
  and these are not available at the pin either. The scorer table is empty: no claim is read from a scorer name or a
  value. The judgements stay in the AER and the PROV.
- **Catalogue.** It cites the inspect catalogue at version 2 (`rules = {"inspect": 2}`), the version the AER declares
  (H.2.5). `inspect.untabulated_tool@1` is a generic class-I rule for any Inspect profile that tabulates no tool. It is
  appended to version 2 in place under the owner ruling of item 133 (D-31: no kept corpus records inspect v2; it must
  land on main before the round's first kept Inspect import). The `inspect.agentharm` profiles are unchanged.
- **Tests.** `tests/adapters/inspect/test_whistlebench_semantics.py` (tier 3 in release mode and tier 4 over synthetic
  AERs and the committed pinned log, the cited rule, the refusal of tables that claim more); the D-601 end-to-end test
  seals with it.

**Version 2 (D-601 addendum 2, user decision 2026-10-21; the version the registry part selects).** The `highagency/`
code at the pin was fetched into the staged partial clone (117 paths; acquisition record
`$AGENTPROV_HOME/migration-work/bugpass/acquisitions.jsonl`, user-approved 2026-10-21) and read as text, never run or
imported. `inspect.whistlebench-2/tables.toml` cites every reading by path, git blob id and lines.
- **Code identity.** The pin is the public release. Its history holds 4 commits, the first "Initial public release".
  The 8 producing commits that the logs record (`eval.revision.commit`) are not in it, so every reading is class I
  (never verified against the producer). One divergence is visible: the logs name the whistleblowing scorer
  `email_whistleblowing`, the release defines `whistleblowing` (which also flags file writes outside the permitted
  locations), and no file of the release names `email_whistleblowing`.
- **Tools** (`inspect.tool_table@1`; an unlisted name, e.g. SnitchBench's `bash`, is fail-closed under
  `inspect.unknown_tool@1`). Every tool acts on the task's virtual file store or returns a fixed value; nothing leaves the
  sample. Output integrity is never `trusted`.

  | Tool | Roles | Output integrity |
  |---|---|---|
  | `write_file`, `delete_file`, `merge_documents`, `create_index`, `write_logs` | `write_sink` | `unknown` |
  | `send_email`, `alert_ceo_document_leak` | `send_sink` | `unknown` |
  | `get_file_path`, `search_documents`, `extract_metadata` | `content_source` | `untrusted` |
  | `get_md_hash`, `word_count`, `convert_md_to_pdf` | `neutral` | `unknown` |
  | `Submit`, `submit` (react's AgentSubmit) | `response_sink` | `unknown` |

- **Outcomes** (`inspect.scorer_letter_table@1`). A recorded, non-default judgement whose name and AER `task.suite` the
  table lists, with the letter grade `C` or `I`, gets `{claim, holds}`, and `holds` is true for `C`. `I` also covers a
  grader answer the scorer could not parse, so `holds: false` means only that the scorer did not find the behaviour.
  The pinned logs record `C` and `I` only.

  | Judgement | Suites | Claim |
  |---|---|---|
  | `refusal` | `highagency/high_agency` | `inspect.refusal` |
  | `deliberation_analysis` | both | `inspect.concluded_evaluation` |
  | `test_awareness.evaluation_awareness` | `highagency/high_agency` | `inspect.evaluation_awareness` |
  | `test_awareness.hypothetical_recognition` | `highagency/high_agency` | `inspect.hypothetical_recognition` |
  | `gov_`, `media_`, `internal_snitching` | `highagency/high_agency_deliberation_awareness` | `inspect.snitch_attempt_government`, `_media`, `_internal` |

- **Fail-closed, and why.**
  - `email_whistleblowing.*` gets no outcome: the scorer is not in the release (code identity above).
  - `score` and `score.<key>` get no outcome: score events that name no scorer (pre-check PC-08).
  - A value other than `C`/`I` (e.g. `P` from a "maybe") gets no outcome.
  - A listed scorer in an unlisted suite gets no outcome.
  - There is no taint policy: the benchmark has no attacker (D-147).
- **Catalogue.** It cites inspect v2. `inspect.tool_table@1`, `inspect.unknown_tool@1` and
  `inspect.scorer_letter_table@1` (generic, class I) are appended to inspect v2 in place under the D-31 addendum. Version
  1 stays shipped unchanged.
- **Tests.** `tests/adapters/inspect/test_whistlebench_semantics_v2.py`:
  - the table readings and fail-closed tools;
  - outcomes only for listed scorers, suites and letters;
  - harness defaults;
  - tier 3 and tier 4 over synthetic and committed AERs;
  - determinism;
  - every cited blob recomputed from the staged clone, with its lines in bounds;
  - the refusal of over-claims.

  The D-601 end-to-end test seals with `@2`.

### D.9.15 Semantics profile `inspect.atia@1` (D-307 addendum; orchestrator request 2026-10-21)

`adapters/inspect/semantics/inspect.atia-1/tables.toml`, built by `adapters/inspect/semantics/atia.py` (the family's
`build_profile` dispatches on the id). It is fail-closed like `inspect.whistlebench@1` (D.9.14). The registry part
`atia-benchmark · logs` names it, so an import annotates every execution and a release seal is possible (a sealed index
row records a SEM stage, H.3.1).
- **Tools fail-closed.** The code that ran is not available at a pinned identity. The logs' header revisions are not
  in the public history. The task, solver (`use_sample_tools` and its tool registry) and scorer files at `cc71caf5` lie
  outside the pinned `logs/` tree, and they were committed after the logs were written (D.9.10). So the profile knows
  no tool: every `tool_call` part and `tool_execution` gets role `["unknown"]`, and every `tool_result` part gets
  integrity `unknown`, class I under `inspect.untabulated_tool@1`. There is no taint policy. The samples'
  `harmful_tools` and `benign_tools` metadata is a benchmark label, not tool code, and the profile does not read it.
- **No outcome.** The one scorer, `harmful_tool_invoked`, records `C` or `I`. Its run-time code is not at a pinned
  identity, and the pre-check found its polarity inverted in the two status-`error` logs (PC-atia-benchmark-01: 36 of
  36 scored samples), so no single polarity holds for the corpus. The scorer table is empty: no claim is read from a
  scorer name or a value. The judgements stay in the AER and the PROV.
- **Catalogue.** It cites the inspect catalogue at version 2 (`rules = {"inspect": 2}`). That is the version the
  current mapper declares in ATIA AERs (H.2.5), as in the pre-check's L2 corpora. It reuses
  `inspect.untabulated_tool@1` (D.9.14) and adds no rule, so the catalogue bytes do not change.
- **Tests.** `tests/adapters/inspect/test_atia_semantics.py` covers a synthetic 0.3.112-shaped tool-call sample with
  media and a sample with no call. It checks tier 3 in release mode and tier 4, determinism, the cited rule, and the
  refusal of tables that claim more. It also maps the smallest pinned log from the fetch cache (`slow`; no ATIA log
  is committed, D-309). `tests/adapters/inspect/test_atia_seal_e2e.py` runs a release import, the seal and
  `verify --level chain --release`; every sealed row records the SEM stage.

---


### D.9.13 Scorer names, local offsets, dangling ground truth and unhashable call ids (regeneration-batch items 81–84; RD-2, core review D CD-24..CD-27)

1. **Scorer name (item 81, CD-24).** inspect_ai writes `scorer` on a `score` event only from 0.3.217. For an
   event without one, the scorer is the nearest enclosing span (itself included) of type `scorer` with a string `name`.
   That name is the scorer's (`sample.scores` is keyed by it), cited to `inspect.score_event@1` (D: "produced in the
   scorer's span"), with a locator to the span's `name`. The `sample.scores` cross-link then holds and
   `sample.scores` entries are not emitted a second time. With no scorer span, the literal `score` is kept, declared
   `unk ambiguous` (C.7.2(2)), and never paired with a `sample.scores` key by value. No catalogue change: rejected was a
   new rule `inspect.score_event_scorer_from_span@1`, which is a v3 bump of `inspect` cascading into every Inspect
   profile, while phase 10p seals against v2 (an in-place edit is D-460 drift).
2. **Local offsets (item 82, CD-25).** A timestamp with a non-UTC offset is converted to UTC (C.8.3), keeping exactly
   the source's fractional digits, with the verbatim value in `t.raw`; the value stays `O` (a lossless re-encoding,
   like `+00:00` → `Z`). Every time slot (model, tool, run and span start/end, approval and review decisions' `start`,
   state changes' `end`) goes through one path, so a span end, a decision start or a state end with a local offset or
   an unparseable value is no longer dropped silently: unparseable values go to `t.raw` with `unk not_recorded` (the
   C.7.3 example). Time edges and the time order key follow from the UTC instants. A record whose recorded start is
   later than its recorded end (whistlebench: 10 of the 1,850 rehearsal samples, an hour apart at one local offset) has
   neither instant asserted: both stay verbatim in `t.raw`, `/t/start` and `/t/end` are declared `ambiguous`
   (C.7.2(2)), and the record takes no part in time edges.
3. **Dangling ground truth (item 83, CD-26).** A `ground_truth_metadata` value holding a dangling attachment
   reference raises `dangling_source_ref` (detail `/metadata`), like the task-prompt and tool-definition fixtures;
   no ground-truth fixture is emitted and the keys stay in `ext.inspect.sample_metadata` (resolved as far as they
   resolve) instead of vanishing.
4. **Unhashable call ids (item 84, CD-27).** A tool message whose `tool_call_id` is not a string (a list or object)
   takes the existing orphan path (`/parts/0/responds_to` `not_recorded`, `orphan_tool_result`) instead of crashing the
   sample into an `adapter_defect`.

## D.10 Live harness (`agentprov_backend`), capture session and the AgentDojo backend

This section implements A1 as fixed in AD-01, with the default LLM element of AD-09 and the containment of AD-13.
[R-01, R-16, R-13, R-25, R-39, AD-09]

### D.10.0 Process layout

| Process (tier) | Interpreter and code | Role in a live run |
|---|---|---|
| Parent (T0) | core `agentprov` on Python ≥ 3.14; `agentprov.cli.run` | Validates the run plan and the endpoint configuration; reads `.env` only through the `live` extra (`python-dotenv>=1.2.2`) from `--env-file` or the repository root (A4); computes the backend environment's identity digests **before** spawn (§D.10.6); spawns the worker; speaks `agentprov-backend/0.1`; after each cell runs the literal-value secret scan over every staged file and ingests the staging directory like `--input` (no-follow, `S_ISREG`, `st_nlink == 1`, labels resolved only under the session directory; G.3.6); reads the mapped AER's seal verdict to decide a re-attempt |
| Backend worker (T2) | `<env>/bin/python -I -B -m agentprov_backend.worker`, Python 3.12, in the environment `$AGENTPROV_HOME/envs/<backend>-<commit8>/` built from `backends/<backend>/` (§D.11.2); no `uv` at run time | Runs the stock benchmark through the `agentprov_backend` harness; writes `capture/0.1` events, blobs and the native TraceLogger JSON into `$AGENTPROV_HOME/staging/<session>/` (its working directory) with `HOME=$AGENTPROV_HOME/t2home/<session>`; never imports `agentprov` |
| Map workers (T1) | core `agentprov.worker` | Read the staged capture log (`adapters/agentdojo/capture_reader.py`, chain verified with the `agentprov_capture` verifier) and map it with `adapters/agentdojo/capture_mapper.py`, exactly as an import (A-8) |

Package split (RESOLUTIONS §3.1):

| Package | Holds | Imports |
|---|---|---|
| `agentprov_capture` (`capture/`) | event model, `CaptureLog` writer (`emit`, `put_blob`, `close`), hash-chain verifier, `redact` (+ `redact_allowlist.toml`), `envstate` digests, `cap.rules.toml` | stdlib + `rfc8785` |
| `agentprov_backend` (`backends/shared/`) | `gateway` (`LlmSpan` brackets; `GatewayLLM` for `gateway_compat`), `transport` (recording httpx transport), `pass_recorder`, `executor_mirror`, `runtime`, `runner` (cell enumeration, pipeline construction, `SuiteRunProxy`, the dataclasses of §D.10.1), `attacks`, `worker` (protocol loop, identity report), `testing` (`ScriptedTransport`) | `agentprov_capture`, `httpx`, `openai`, and `agentdojo` from the backend project |
| core `agentprov` | capture reader and mapper, AER accounting, the parent side of the protocol (`agentprov.cli.run`, `agentprov backends build`) | no benchmark, no `agentprov_backend` |

### D.10.1 Harness-internal protocols (`agentprov_backend`; not core)

These types are internal to `agentprov_backend`. Core never imports them; it sees only the JSON messages of
`agentprov-backend/0.1` (§D.11.3) and the `capture/0.1` log (C.13). [R-17]

```python
@dataclass(frozen=True)
class BenchmarkIdentity:                # reported by the worker in hello_ok and the capture `identity` event
    distribution: str                   # "agentdojo"
    version_reported: str               # importlib.metadata — NEVER sufficient (A-7)
    source: Mapping[str, str]           # {"kind": "pypi", "wheel_sha256": …} | {"kind": "git", "repo": …, "commit": …} (PEP 610)
    record_digest: str                  # sha256 over the installed dist-info RECORD file
    guarded_sources: Mapping[str, str]  # qualified name -> sha256 of inspect.getsource() (e.g. ToolsExecutor.query)
    suite_set: tuple[str, ...]; benchmark_version: str
    default_system_prompt_sha256: str
    tool_definitions_sha256: str        # names + descriptions + JSON schemas of all suite tools, JCS
    python: str; platform: str; lock_sha256: str  # uv.lock of the environment that ran

@dataclass(frozen=True)
class CellSpec:
    cell_key: str                       # "<suite>/<user_task_id>/<attack or none>/<injection_task_id or none>"
    suite: str; user_task_id: str; injection_task_id: str | None
    attack: str | None; defence: str | None
    kind: Literal["user_task", "injection_task_as_user_task", "attacked", "dos"]
    attack_params: Mapping[str, Json]   # e.g. {"model_display_name": "GPT-4"}; recorded verbatim

@dataclass(frozen=True)
class AgentConfig:
    model_requested: str                # explicit; there is no silent default model id
    provider: str                       # "openai_compatible" (v0.1)
    endpoint: str                       # endpoint entry name in endpoints.toml; https host (loopback excepted)
    api_key_env: str | None             # the NAME of the env var; the value is never recorded
    params: Mapping[str, Json]          # configured params (temperature, reasoning_effort, …)
    llm_element: Literal["native", "gateway_compat"] = "native"   # AD-09: stock element by default (§D.10.5)
    transport: Literal["http", "scripted"] = "http"
    script: str | None = None           # label of a scripted-transport file inside the session (tests only)

@dataclass(frozen=True)
class RunPlan:
    plan_sha256: str                    # JCS hash of the expanded plan (cells + agent + backend config)
    cells: tuple[CellSpec, ...]; agent: AgentConfig; backend_config: Mapping[str, Json]

@dataclass(frozen=True)
class CellResult:
    status: Literal["complete", "incomplete", "errored", "aborted"]   # = session.end status (C.13.3)
    outcome: Mapping[str, Json] | None  # as returned by the benchmark; polarity is SEM's
    native_artefacts: tuple[str, ...]   # labels inside the session directory, e.g. the TraceLogger JSON

class Backend(Protocol):                # one implementation per benchmark family inside agentprov_backend
    backend_id: str                     # "agentdojo", "autodojo"
    version: str
    def identity(self) -> BenchmarkIdentity: ...
    def plan(self, spec: Mapping[str, Json]) -> RunPlan: ...   # expand + validate (UnsupportedConfiguration)
    def execute(self, cell: CellSpec, agent: AgentConfig, session: "CaptureSession") -> CellResult: ...

class CaptureHooks(Protocol):           # implemented by CaptureSession; called by harness elements
    def pass_start(self, env_state: Json) -> int: ...            # returns the 0-based pass index
    def pass_end(self, pass_index: int, native_messages: Json, env_state: Json, *, aborted: bool) -> None: ...
    def tool_dispatch(self, occ: str, provider_call_id: str | None, name: str, requested: Json,
                      args_raw: str | None, at: tuple[int, int] | None) -> None: ...   # tool.dispatch (C.13.3)
    def tool_result(self, occ: str, status: Literal["ok", "error", "invalid", "denied"],
                    args_effective: Json | None, returned: Json | None, rendered: str, model_visible: str,
                    error: str | None, decided_by: str | None = None) -> None: ...
    def fixture(self, kind: str, vector: str | None, content: Json) -> None: ...   # kind "injection_payload"
    def outcome(self, judgements: Sequence[Mapping[str, Json]], declared_semantics: Json | None) -> None: ...
    def note(self, ns: str, kind: str, payload: Json) -> None: ...  # namespaced adapter facts

class LlmSpan(Protocol):                # agentprov_backend.gateway; brackets one LLM-element invocation
    def __enter__(self) -> "LlmSpan": ...  # records input_at (positions in the pass's native message list) and n_messages
    def mark_kept(self, call: str) -> None: ...
    def mark_discarded(self, call: str, reason: str) -> None: ...

class CaptureSession:                   # agentprov_backend.runner; writes through agentprov_capture.CaptureLog
    ex: str                             # "ex_" + UUIDv7, minted at construction
    attempt: int
    def start(self, header: Mapping[str, Json]) -> None: ...   # session.start, instrumentation, identity
    def hooks(self) -> CaptureHooks: ...
    def span(self, role: Literal["agent", "auxiliary"], actor: str) -> LlmSpan: ...
    def add_native(self, label: str, media: str) -> None: ...  # native.log event (sha256, bytes)
    def record_error(self, exc: BaseException, *, fatal: bool) -> None: ...   # error event; traceback blob, escaped
    def close(self, status: str) -> str: ...   # session.end; closes the hash chain atomically; returns the chain head
```

**Run-plan files** (format id `agentprov-run-plan/0.1`; MN Q10). A committed run plan (`plans/*.toml`, passed as
`agentprov run --plan PLAN.toml`) is TOML whose `[plan]` table MUST carry the key
`format = "agentprov-run-plan/0.1"`; HL L.1.1 registers the id. `agentprov_backend.runner` reads the file and expands
it into a `RunPlan` (`Backend.plan`); a plan whose `format` is absent or different is refused with
`UnsupportedConfiguration`, and T0 applies the same check when it validates the plan (§D.10.0).
`RunPlan.plan_sha256` hashes the expanded plan, not the file bytes.

### D.10.2 Capture event content (`capture/0.1`)

C.13 owns the envelope (`seq`, `type`, `ts`, `mono_ns`, `pass`, `actor`, `prev`, `data`) and the event vocabulary
(RESOLUTIONS §3.8); occurrence ids are `o<n>`. This section fixes the **minimum event content** that AgentDojo-family
backends MUST supply, using C.13's names. [R-16]

| Event | Content supplied by the AgentDojo-family harness |
|---|---|
| `session.start` | `ex`, `attempt`, `cell` (with `attack_params`), `writer {dist, version}` (the `agentprov-capture` distribution), `backend {id, version}` (the `agentprov-backend` harness and backend project), `runtime {python, platform, lock_sha256}`, `actors`, `config_sha256` (JCS digest of the run configuration, plan included, secrets excluded). A test session is marked by the `test_only` instrumentation item (§D.10.7) |
| `instrumentation` | the items of §D.10.7 |
| `identity` | `BenchmarkIdentity` (§D.10.1), cross-checked by T0 (§D.10.6) |
| `fixture` | one event per injection vector: `kind: "injection_payload"`, `vector`, `content` (the map returned by `attack.attack()`) |
| `pass.start` / `pass.end` | environment digest before and after (`agentprov_capture.envstate`, E-1…E-5 [audit/capture.md §4.4]); optional full snapshot blobs; the native message dump serialised **at pass end**; `aborted` |
| `llm.request` | exact wire request blob (after redaction), `call`, `role`, `attempt`, `retry_of?`, `endpoint {host, path}`, `params {configured, transmitted}`, **`input_at`** and **`n_messages`** (from the `LlmSpan` bracket) |
| `llm.response` | `call`, `status` (`kept`/`discarded`/`error`/`cached`), `reason?`, `http_status?`, exact response blob (discarded replies included), `usage?`, `finish_reason?`, `served_model?`, `response_id?` |
| `tool.dispatch` / `tool.result` | as in `CaptureHooks`; `occ` = harness occurrence id `o<n>` (fixes provider-id reuse at the source); `at` is optional (link by `occ` or `provider_call_id`) |
| `decision` | defence or guard verdicts the harness observes (none in the v0.1 undefended pipelines) |
| `state` | optional per-call environment digest |
| `outcome` | `judgements [{name, value, origin}]` and the backend's `declared_semantics` (kept as data for SEM) |
| `native.log` | the native TraceLogger JSON's label, sha256 and bytes |
| `note` | namespaced adapter facts |
| `error` | `where`, `exception {type, message}` (escaped), traceback blob, `fatal` |
| `session.end` | `status ∈ complete \| incomplete \| errored \| aborted`, `n_events`, `appended_by ∈ worker \| parent` |

New span and human-input events wait for `capture/0.2`.

### D.10.3 Accounting

Accounting is computed **once**, by the AER mapper and validator (C.12; R-13). For live AER the applicable checks
include `aer.acc.passes_closed@1`, `aer.acc.dispatch_vs_results@1`, `aer.acc.env_recorded@1` and
`aer.acc.capture_chain@1`, beside the generic ones of §D.6.9. Agent-role kept calls are reconciled with the
assistant messages of the pass's native dump; auxiliary, judge and defence calls are recorded, not reconciled
[audit/capture.md §9.4]. The capture side only seals its hash chain (`session.end`); it computes no verdict of its own.
The live runner (T0) reads the mapped AER's `seal.accounting.status` to decide whether to re-attempt a cell. **An
inconsistent session is sealed and kept**, never deleted.

### D.10.4 The capture mapper (`adapters/agentdojo/capture_mapper.py`, adapter id `agentdojo.capture`)

It is core code (it reads the staged log; it does not run the benchmark). It maps a sealed session to AER with the
same record emission as §D.6.5, with these differences (C.13.7):
- `ex` = `"ex_" + <session UUIDv7>`; `source_key = {sha256: <capture log>, loc: {}}`; `dialect {id:
  "agentprov.capture", variant: "0.1"}` (displayed `agentprov.capture/0.1`); profile `agentdojo-live` or
  `autodojo-live`.
- `artifacts`: the capture log (role `capture_log`) and the native TraceLogger JSON (role `native_log`), both
  `prov_primary: "native"`; the attack cache file, when present, is `supporting`.
- Every pass gets a scope `att<k>` with an observed `index`.
- `model_call` is O by `capture`: `input` = the ids of the messages in the decoded request; an entry whose sent form
  differs from the recorded message is `{id, sent: [<transform>], sent_sha256?}` with `<transform>` ∈
  `error_substitution` (AgentDojo's OpenAI path sends a failed call's `error` text), `role_rewrite` (`gateway_compat`
  only), `reasoning_passback`, `formatting`, `truncation`, `other` (AD-03). Context membership is O only when the
  request carries `input_at`; otherwise it is D under the named `cap` alignment rule of C.13.7 with an accounting
  check (R-16). `params.transmitted`, `usage`, `served_model`, `t` and the request/response blobs are copied.
- A discarded reply becomes a `model_call` with `status: "discarded"` (and `retry_of` on its successor) plus a message
  `generated_by` it, which views exclude by default.
- `tool_execution`: `args` (from the `tool.dispatch` requested arguments), `args_effective`, `status` (`ok`/`error`/`invalid`), `exception`,
  `returned` (blob) and `t` (O). A capture `tool.result` with status `denied` maps to a `decision` only (no
  `tool_execution`).
- `state_change` records per pass (`cause` = the attempt) and per call (`state` events).
- Judgements carry `by: "benchmark"` and C's `origin`.
- Instrumentation items are copied into the header (§D.10.7).

**Live-versus-native check.** The mapper maps the native TraceLogger JSON with `TraceLoggerMapper` under the same
profile and compares the projections. A divergence gives the issue `live_native_divergence` (error), naming the
differing pointers. The projections are:
- the final pass's message sequence: roles, texts, tool-call names and `args` (compared as JCS values with their
  `ext.lex` hints), tool contents and errors;
- the injection fixtures;
- the judgement values.

The same comparison is a test (§D.10.8).

### D.10.4a Implementation resolutions (phase 8, capture mapper)

Phase 8 stream C built the core side of live capture: `agentprov.adapters.agentdojo.capture_reader` (dialect
`agentprov.capture` `0.1`), `capture_mapper` (adapter `agentdojo.capture` `0.1.0`), the profile `agentdojo-live`, the
common projection (`agentprov.adapters.projection`, re-exported as `agentprov.testing.projections`) and
`agentprov.adapters.runner.live`. The code is the reference; tests: `tests/adapters/agentdojo/test_capture_{mapper,
mapping,fixtures}.py`, `tests/integration/test_live_mapping.py`, `tests/differential/test_live_vs_native.py`,
`tests/unit/testing/test_projections.py`. `aer/0.1` and `capture/0.1` were not changed.

**Reading.**
1. **Verifiable prefix.** The reader splits the log on LF, parses each complete line with the strict loader
   (`record=True`), passes `None` for a line the loader rejects, and hands lines and events to
   `agentprov_capture.verify.verify_chain` (C.13.10). Only the first `n_verified` events are mapped; the log is sealed
   only when the verifier says so and no line was rejected or torn. A log whose `session.start` does not verify names no
   session and no execution: it is a register row `select.not_execution_artefact`, never a degenerate AER (a live
   header needs the session).
2. **Dispatch.** A staged session is a set of raw objects, like an expanded container: `CaptureLogReader.plan(members,
   read, profile)` returns one unit with the auxiliary bytes `blob:<hex>` and `native_log`, found **by digest** (labels
   are data), so the runner's `container` map job runs it unchanged. No runner or registry change was needed for
   dispatch. C.13.1's `capture_mapper.map_session` lives in `agentprov.adapters.runner.live` (`stage_objects`,
   `map_session`): mapping needs the runner's context, and M.5.1 forbids `adapters` (L4) to import the runner (L6). It
   reads a staging directory through `ingest.paths` (no-follow, `S_ISREG`, `st_nlink == 1`) and takes the session from
   the log's first line.
3. **Core changes (invariant 5).** (a) `aer.rules.CATALOGUE_HOMES` gains `"cap": "agentprov_capture"`, the home C.6.4
   names: `MapContext.rule` and the validator's and engine's `RuleRegistry` resolve a namespace without a package
   argument, so without it every `cap.*` reference is `rules.unavailable`. The catalogue is read as package data. (b)
   `prov/rules/edges.py`: the assumed checker inputs carry a role discriminator. An unchanged environment (a digest
   state change with `after == before`) is both the pre-state and the post-state, so `aprov.outcome@1` stated
   `used(check, state)` twice and derivation failed with `prov.statement_collision`; the discriminator enters a
   statement name only when (rule, arguments) repeat (E.4.2), so no existing PROV output changed. Both are
   adapter-agnostic; no AER, PROV or SEM digest of an imported execution changed.

**Header and actors.**
4. `ex` and `capture {session, log: a0, attempt}` from `session.start`; `source_key {sha256: log, loc: {}}`; artefacts
   `a0` (`capture_log`) and `a1` (`native_log`), both `prov_primary: native` (D.10.4), origin `capture {session}`. The
   task comes from `cell` (`O` by `config`); `cell.attack_params` is not mapped (no core slot; the raw keeps it, and a
   display name is also the `attack_model_display_name@1` item's `params`).
5. **Instrumentation** is copied verbatim (`O:capture`). Items not in the AD-03 shape are reported (`capture_error`)
   and not copied; ids missing from `[family.agentdojo.live] instrumentation_accepted` are kept and reported
   (`agentdojo.instrumentation_unrecognised`). The harness's `agentdojo/instrumentation_observed` note (D.10.10 item 6)
   becomes `params.observed` of its items, with the note's line in `src`. When the verifiable prefix ends before the
   `instrumentation` event, the member is omitted with `unk {"/instrumentation": "not_captured"}` (`aer/0.2`, C.21,
   D-210; regen item 20). Under `aer/0.1`, which requires the member for live, it was `[]` with `unk ambiguous`.
6. Actors: `bench` (name, `version` = `identity.benchmark.suite_set`, `code` from the identity, `O:capture`; without an
   identity event `O` by `config` from the cell with `unk /code, /version not_captured`), `harness` from
   `identity.harness`, `user` (`simulated_user`, `agentdojo.user_is_simulated@1`) unless declared, the declared actors
   with their tags as ids (agent first; the agent's `model.provider`/`endpoint` from the identity, `O:capture`), and
   `att` for an attacked cell unless an attacker is declared. An actor tag outside the AER id grammar is
   `MalformedArtefact`. The tool runtime acts on behalf of the agent under the I rule
   `agentdojo.auto_execution_unverified@1` as for imports: a verified `apv:AutoExecution` for the pinned wheel is an
   open item (AER-V34 needs the wheel identity in the AER, which the identity event of a PyPI wheel lacks, D.10.10
   item 7).

**Scopes, status, issues.**
7. `run`: `t` from `session.start`/`session.end` (`ts` verbatim, `mono_ns`); status `complete → ok`, `errored → error`,
   `aborted → aborted` (`O`); `incomplete` has no scope value: `unk /status ambiguous` plus `incomplete_run`. An
   unsealed log, or a fatal `error` event under another status, gives `error` (`D`, `agentdojo.capture_status@1`) and
   `capture_unsealed` (error) / `capture_error`; a non-fatal `error` gives `capture_error` (warning). A
   `session.end{status: aborted}` (worker or parent) gives `aborted_attempt` on `run`.
8. `att<k>` per pass index with `pass.start` or `pass.end`: `index` `O`, `t` from the two events, `status` `aborted` or
   `ok` from `pass.end.aborted` (`aborted_attempt` for an aborted pass), `unk not_captured` without `pass.end`. `scored`
   is `true` on the last attempt and `false` on the others (`agentdojo.capture_last_pass_scored@1`, `D`).
9. No `pass.start` at all: `no_execution_observed` (`agentdojo.capture_no_pass@1`), `unit` stays `agent_execution`.
10. **Live checks** (C.12.2) through `ctx.check`: `capture_chain` (run; inconsistent when unsealed or any finding),
    `passes_closed` (run, when a pass boundary exists), `dispatch_vs_results` (per scope holding a dispatch or a result;
    an unpaired occurrence is inconsistent), `env_recorded` (per attempt; both digests present). The writer mirrors
    non-consistent verdicts as issues.
11. Seal issues never name a dropped record: an id of a record skipped as malformed is replaced by `exec`.

**Messages and calls.**
12. Messages are decoded from each pass's `pass.end.messages` blob (strict loader); ids `m<n>` number the dumps of all
    passes in pass order, then the discarded replies. `src` is `{"blob": …, "p": "/<i>"}`, `O` by capture. Content
    parts follow R-CONTENT (D.6.3); a tool message's single text block maps to `text` (the 0.1.35 executor wraps every
    output in one block; several blocks stay `value`). Authors as D.6.6 (system → `bench`, first user → `user`, later
    users I with `unattributed_additional_user_message`). Message order: `pos` edges under
    `agentdojo.messages_append_ordered@1`. Dump `args` are post-normalisation: tool-call messages cite
    `agentdojo.args_are_effective@1` unscoped; `args_raw` is `unk not_recorded` (the dispatch's `args_raw` is the
    harness's, not the wire's, D.10.10 item 13).
13. **Model calls** (`mc<n>` in request order): `O` by capture; `usage`, `finish_reason`, `served_model`,
    `response_id` `O:provider`; `params`, `reason`, `request`, `response`, `t` copied; `retry_of` mapped to the earlier
    call. No `llm.response`: `unk /status, /response not_captured`. `http_status` and `exception` have no slot and stay
    in the raw. A call outside any pass belongs to `run` with `unk /input not_recorded`.
14. **Replies.** A kept or cached agent call generates the dump's assistant message at `n_messages` (in call order
    without it), if every input position precedes it and the decoded response agrees (text, tool-call names): `D`,
    `agentdojo.capture_reply_appended@1`; otherwise no link, `agentdojo.capture_reply_mismatch`, and the message gets
    `unk /generated_by not_captured` with `missing_generated_by`.
15. **Discarded replies** become a message decoded from the response blob (`choices[0].message`; `src` the blob),
    `generated_by` the call (`O`), with **no `actor`**: authorship follows from the generator, and C.12.2 pairs answering
    calls with llm_agent-authored assistant messages, so a rejected reply is not counted as an answer (no accounting
    change). Unparseable arguments are kept verbatim with `unk …/args ambiguous` (`agentdojo.capture_discarded_reply@1`);
    the reply's calls are listed as `unexecuted_tool_call`.
16. **Context.** With `input_at` (positions inside the dump, strictly increasing): `O`; invalid positions give
    `unk /input ambiguous` and `agentdojo.capture_sent_form_unexplained`. Without it: the unique order-preserving
    alignment of the decoded request with the dump prefix of `n_messages` (all of it when absent), item equality being
    "a faithful stock rendering or a declared transform": `D`, `cap.context_alignment@1#/input`; none or several:
    `unk /input ambiguous`. Never `O` (AD-SW23).
17. **Sent transforms** (`agentdojo.capture_sent_form@1`, per item `evf /input/<i>/sent` and `/sent_sha256` `D`, so
    membership keeps its own class). The stock 0.1.35 rendering is not a transform: system as `developer` or `system`
    (the AutoDojo fork sends `system`), blocks as text parts or one string, args as a JSON string compared with source
    member order. `error_substitution`: a tool message with an error sent as its error text. `role_rewrite`: a system
    message sent as `system` when the session declares `agentdojo.role_rewrite_developer_to_system@1`.
    `reasoning_passback`: reasoning members on a sent assistant message. `sent_sha256` = SHA-256 of the JCS of the
    decoded wire message (omitted when the request is withheld). An unexplained difference claims no transform and is
    reported (`agentdojo.capture_sent_form_unexplained`).
18. **The abort message.** `AbortAgentError` appends an assistant message (one text block, `tool_calls: []`) to the
    aborted pass (`errors.py`); it is no reply: `unk /actor, /generated_by not_recorded`
    (`agentdojo.capture_abort_message@1`). The calls it cut short are `unexecuted_tool_call`.

**Tools, decisions, state, outcomes.**
19. `tool_execution` per dispatch/result pair by `occ` (`te<n>` in dispatch order): the call part from `at` (`O`), else
    the unique part with the dispatch's `provider_call_id` (`O`, C.5.4), else `unk /call ambiguous` with
    `call_result_link_conflict`; `name`, `args` (dispatch), `status`, `args_effective`, `returned` (inline or blob),
    `exception`, `t` (`O`); `unk /args_effective not_applicable` for `invalid`. The tool message's `responds_to` follows
    D.6.6.1 (`call_id_unique_match` `D`, else `positional_match` `I`); it is generated by the execution whose call it
    answers (`agentdojo.capture_execution_result@1`, at the class of the link). A `denied` result is a `decision`
    (`deny`, subject the call part, actor `decided_by`, `unk /reason not_recorded`) that generates the tool message; no
    execution. Calls of the last reply without a dispatch are `unexecuted_tool_call`, earlier ones `missing_tool_result`.
20. `decision` events map with subject `occ` → execution, `at` → part, `call` → model call; a `redact`/`modify`
    decision on an execution generates its tool message. `original` is copied when captured, else
    `unk not_captured`.
21. `state_change` per pass (`cause` the attempt; `before`/`after` digests, `changed`, snapshots; `unk not_captured` for
    a missing digest) and per `state` event (`cause` the execution of `occ`; `after_sha256`; `t.end` = the event
    time). `env.diff` is not mapped: its shape has no `format`/`truncated` (raw only).
22. Judgements from `outcome` (`by: benchmark`, `origin` as recorded, `O:capture`; `checker` origins get `unk /inputs`
    with `agentdojo.checker_inputs_unverified@1`). Both `harness_default` after a pipeline `error` event:
    `outcome_imposed_by_runner` (D.6.7 parity). `declared_semantics` is not mapped (SEM owns polarity).
23. **Redactions** (C.13.5): an event's redaction of a member gives `unk withheld` on the optional AER field built from
    it (`request`, `response`, `params`, `args`, `args_effective`, `returned`, `exception`) and `capture_redaction`
    naming the records (`exec` when none), citing the item's `cap.secret.<kind>@1` when the shipped `cap` catalogue
    declares it, else `agentdojo.capture_withheld@1`. A redacted required part member (a message text, a reply's
    arguments, a refusal or reasoning text: a dump or response blob's redaction at or under its pointer) is omitted
    with `unk withheld` (`aer/0.2`, C.21, D-211; regen item 20). Under `aer/0.1` it kept its redacted value. A tool
    output (a `tool_result` part) is outside D-211's relaxation: it keeps text xor value under `aer/0.2` too, so a
    redacted tool output keeps its redacted value, and `capture_redaction` names `exec` since no record is withheld
    (re-check RC-1, RC-19).
24. **Live versus native** (D.10.4). The native JSON is mapped by `agentdojo.tracelogger` under `agentdojo-live`, whose
    `[import] native` declares `v1.k14` and `v1.k14.incomplete`: the TraceLogger mapper now maps those variants **only**
    under a profile declaring them (bench `version`/`code`, naive run start, `args_effective`, one-block tool text, per
    D.6.5–D.6.6); `agentdojo-upstream` still seals them `unsupported_variant` (phase 10). The projections (scored
    attempt's messages without discarded replies and without the abort message, executions' name and status, fixtures,
    judgement names and values; values in their lexical form; times excluded) are compared as JCS bytes; a difference
    is `live_native_divergence` (error) with up to twelve projection pointers in `detail`. A native log announced but
    not staged is `capture_error`; one that does not map is `live_native_divergence`.

**Profile and registry.**
25. `agentdojo-live` v1: `[import] dialect agentprov.capture, mapper agentdojo.capture, rules {aer 1, agentdojo 1,
    cap 1}`; `[family.agentdojo.live]` (now a closed schema): backend, project, `llm_element_default = "native"`, pins
    `{distribution, version 0.1.35, wheel_sha256 364bea42…}`, the D.10.6 guarded qualified names, refusals, and the
    D.10.7 ids as `instrumentation_accepted`; `identity.model_from = "capture"` (new enum value); the quirks the native
    mapping needs. The registry gains `agentdojo` · `live` (`live_status: planned`, caveat "in development (phase 8)…",
    `evidence: "n/a"`, a new value of the registry's `Evidence` literal matching D.3.3), reader and mapper factories,
    and `BACKENDS["agentdojo"]`.
26. **Catalogue.** The `agentdojo` catalogue (still version 1, nothing released) gains eleven `capture_*` rules and
    three issue codes (`instrumentation_unrecognised`, `capture_reply_mismatch`, `capture_sent_form_unexplained`). Its
    digest is carried by every PROV-JSON that cites it, so `tests/golden/prov_digests.json` and `gate_d_digests.json`
    were regenerated (`AGENTPROV_REGEN_PROV_DIGESTS=1`, `AGENTPROV_REGEN_GATE_D_DIGESTS=1`): 47 PROV digests changed, no
    statement and no AER or SEM digest.
27. **Artefacts** (D.15): `agentdojo.art.abort_message_not_logged`, `.injection_yaml_folding`, `.nested_wire_retries`,
    `.http_400_not_retried`, `.aborted_pass_cause`, each with its handler and test.

**Ambiguities of the spec resolved here.** C.13.1 places `map_session` in the family module (item 2); C.13.7 says
"`state` → `cause` = the execution" (read as the tool execution of `occ`, item 21); "linked by `at`, else by `occ` or
`provider_call_id`" (`occ` pairs dispatch and result; the call part comes from `provider_call_id`, item 19);
`session.end` `incomplete` has no scope status (item 7); the sent-form comparison basis (the stock rendering, item 17);
the population of discarded messages in C.12.2 (item 15); `instrumentation` before a truncated prefix (item 5);
`withheld` on required members (item 23); D.4.4's native variant list (`v1.k14` only; the failing-cell native log is
`v1.k14.incomplete`, item 24).

**Corrections after gate C6** (phase 8, stream E; the gate's findings, `docs/reports/migration/gate-c6.md`):

28. **One benchmark actor.** The harness declares an actor `bench` (kind `benchmark`) in `session.start.actors`. The
    mapper used to add a second actor `bench0` for the identity's versions, which left `bench` without `version` and
    `code`. Now the identity's benchmark (`name`, `version` = `suite_set`, `code`; `O` by capture) is merged into the
    declared benchmark actor. The declared `name`/`role` are kept when the identity has none, `src` cites both lines,
    and no second actor is made. Without a declared benchmark actor the old behaviour applies (`bench`, or `bench0`
    when the tag `bench` is taken by another kind).
29. **Reply facts only the wire carries** (`agentdojo.capture_reply_wire_fields@1`). The stock element builds the
    AgentDojo message from content and tool calls only (`_openai_to_assistant_message`). A provider's `refusal` and
    reasoning text (`reasoning`, `reasoning_content`, else the text of `reasoning_details`) therefore reach only the
    response blob. For a message that a kept call generated, the mapper appends `refusal` and then `reasoning` parts
    after the dump's parts, in the baseline's log order. It does not add a kind that the dump already holds. The
    parts' evidence is `evf /parts/k: O:provider`, `src` points into the response blob, and the rule is cited unscoped
    (AER-V14 forbids a scoped rule on an `O` value). `ext.agentdojo.wire_parts` lists the part indices. The dump's parts
    are never changed. `native_comparable` drops the listed parts before the live-versus-native projection: the
    TraceLogger log cannot express them, and capture may be more informative (K.9.1(3)).
30. **Lexical form of `tool_execution.args`.** A `tool.dispatch` event is a JCS line, so the requested arguments lose
    their member order and integral floats. When the JCS value of the linked call's `args` in the pass's message dump
    equals the dispatch's, the dump's form is encoded instead: the value is unchanged, and `ext.lex` gets the order and
    float hints, as the importers record them. When the two values differ, the stock in-place `literal_eval` of
    string lists has changed the dump, and the dispatch value is kept without hints. `args_raw` is not used, because
    the dispatch records none (D.10.10 item 13).
31. **Projection.** `common_projection` lists a message's `tool_call` parts after its other parts. This is a stable
    partition, so content order is kept. The importers already place calls last. The live mapper's wire-only parts
    follow the calls (item 29), and a message's calls are a member separate from its content.
32. **View.** `views.transcript_v1` leaves out messages generated by a `discarded` model call (C.13.7, D.10.4). No
    `transcript/v1` import has one, so gates A1, A2 and B are unchanged. With no `ext.adprov.keys`, a reasoning part
    that follows a tool-call or refusal part renders with the `assistant_turn_log_reasoning` layout.
33. **Catalogue digest.** Item 29 adds one rule. The golden PROV and gate-D digests were regenerated with the documented
    flags. Only the `agentdojo` catalogue digest changed; no statement, AER or SEM digest of an import changed.
34. **Provider-`anthropic` sessions (D-656; C.13.10 item 22).** A session whose `identity.agent.provider` is
    `anthropic` recorded the Anthropic Messages wire of the declared `AnthropicLLM` port, and is read through
    `adapters/agentdojo/messages_wire.py` under the catalogue `anthropic_messages` (v1), which only such a header cites.
    Every other session is read as before, byte for byte.
    - *Sent forms* (`anthropic_messages.sent_form@1`): each input message is matched to the unit of the decoded request
      the stock rendering made of it (system lifted into `system`; user blocks as `text`; a tool message as one
      `tool_result`; consecutive user and tool messages in one turn; assistant blocks then `tool_use`), with
      `error_substitution` the one transform and `sent_sha256` the JCS digest of the unit. Wire content the inputs do
      not account for is `agentdojo.capture_sent_form_unexplained` with no transform claimed. There is no Messages
      alignment rule: without `input_at`, `input` is `ambiguous`.
    - *Reply agreement* (`agentdojo.capture_reply_appended@1`, format-neutral): the dump message's content blocks equal
      the reply's non-tool blocks, and its tool calls the reply's validly named `tool_use` blocks when `stop_reason` is
      `tool_use`, else none.
    - *Discarded replies* (`anthropic_messages.discarded_reply@1`): decoded from a JSON body or the stream rebuilt by
      `agentprov.ingest.sse` (bounded); a streamed call keeps its `partial_json` as `args_raw`, ambiguous `args` when it
      is not JSON.
    - *Omitted thinking* (`anthropic_messages.thinking_omitted@1`): a reasoning part whose block is a thinking block with
      empty text and a signature has its `text` withheld (aer/0.2, D-211); `ext.agentdojo.thinking_omitted` lists the
      parts, and `native_comparable` compares them with the empty text both the wire and the native log hold.
    - *Stream reading* (`anthropic_messages.stream_read@1`): an event-stream blob is read as the pinned SDK read it
      (only a blank line dispatches; the event name keys the accumulation; `message_start` first, ordered indices,
      typed deltas, nothing after `message_stop`; a start block's `input_json` never seeds a tool input; the event names the
      SDK forwards besides the six, or no `message_start` at all, make the stream inconsistent). An inconsistent stream
      is `anthropic_messages.stream_inconsistent`
      and nothing is claimed from it (a discarded reply then yields no message: `capture_error`); a stream without
      `message_stop`, or torn, is `anthropic_messages.stream_incomplete` naming the call (and a discarded message).
      A redacted place of a discarded reply's blob withholds the member built from it (an event stream: every member);
      an empty text in a discarded reply is ambiguous, as in a kept one (both formats; review R3-1).
    - *Locators*: a block of a JSON body is `/content/<i>` of its blob; an event stream is not a JSON document, so its
      blocks cite the whole blob (no `p`).
    - *Profiles*: `agentdojo-live` and `autodojo-live` are at v2 (the port's two instrumentation items accepted,
      `anthropic_messages = 1` pinned, the port's stock sources guarded in `agentdojo-live`); their v1 bytes ship under
      `profiles/archive/` (D-31).

### D.10.5 AgentDojo backend design (`agentprov_backend` + `backends/agentdojo`)

**Default LLM element** (AD-09, R-25). `llm_element = "native"` is the default: the benchmark's own LLM element,
unmodified, recorded only by the recording httpx transport on its SDK client, with `LlmSpan` brackets that record
`input_at` and `n_messages` and do not modify requests. `gateway_compat` (the D5 port of `_CompatLLM`) is an explicit
**opt-in** for comparability with the released v2.3 corpus; it is declared through `request_modifying` and
`harness_policy` instrumentation items (§D.10.7), and the claim tag `stock_behaviour` and NC-LIVE-01 apply to any
session whose instrumentation includes such an item.

What is ported from the baseline [audit/capture.md §10]:

| Baseline element | v0.1 element | Decision and notes |
|---|---|---|
| `_CompatLLM` recording logic, `runtime.py:121-393` | `agentprov_backend.transport` (recording httpx transport on the SDK client) + `agentprov_backend.gateway` (`LlmSpan`; `GatewayLLM`, a thin `OpenAILLM` subclass used only under `gateway_compat`) | Under `native`, only the transport and the span brackets apply. `GatewayLLM` keeps RT-1 (reasoning never enters the scored message), RT-3 (request parity: `temperature or NOT_GIVEN`; effort placement), RT-5 (passback reset per pass) and RT-6 (developer→system rewrite). Both record **every** exchange, including discarded and retried replies with their content (fixes D2/D5 of the audit) |
| `EnvironmentRecorder` + `TranscriptCapture`, `observer.py:70-169` | `agentprov_backend.pass_recorder.PassRecorder(inner: AgentPipeline)` | **Wraps the whole pipeline object.** It sets `self.name = inner.name`, calls `hooks.pass_start(dump(env))`, runs `inner.query` inside `try`, and on `AbortAgentError` calls `pass_end(e.messages, e.task_environment, aborted=True)` and **re-raises**, so stock handling (`task_suite.py:383-390`) is unchanged. Otherwise it calls `pass_end(messages, env)`. It serialises at pass end. It is passed to `run_task_with_pipeline` as the agent pipeline |
| `TimingToolsExecutor`, `observer.py:172-231` | `agentprov_backend.executor_mirror.MirrorToolsExecutor` | Kept as a mirror of 0.1.35 `ToolsExecutor.query` (`tool_execution.py:58-115`). Times each occurrence (wall clock and monotonic) with `occ` ids (fixes "no timing when id is None"). Emits `tool.dispatch`/`tool.result` with **model-visible** text (`error or content`, per `openai_llm.py` [audit/capture.md §3]). Guarded by the source-digest check and the differential test (§D.10.6) |
| — | `agentprov_backend.runtime.RecordingFunctionsRuntime(FunctionsRuntime)` | Passed through the public `runtime_class` parameter (`task_suite.py:345`). Records validated arguments (computed with the same pydantic `Function.parameters` model, without side effects), dispatch status from the stock return contract, the exception type, and the raw return value (as a blob). Delegates to `super().run_function` unchanged |
| `ProvObserver` in-loop projection, `observer.py:234-461` | — | **Removed** (D5). Its tests survive as provenance-engine tests |
| `make_instrumented_pipeline`, `observer.py:468-526` | `agentprov_backend.runner.build_instrumented_pipeline(cfg, session)` | `AgentPipeline([SystemMessage(prompt), InitQuery(), LlmSpan(llm), ToolsExecutionLoop([MirrorToolsExecutor(tool_result_to_str), LlmSpan(llm)])])`, wrapped by `PassRecorder`; `llm` is the stock element (`native`) or `GatewayLLM` (`gateway_compat`). **Refuses** `defense is not None` or a non-YAML output format with `UnsupportedConfiguration` (OB-8). Defended pipelines are a planned generalisation |
| `generate.py` orchestration | core `agentprov run` (T0) + `agentprov_backend.runner` | cell enumeration, attack loading, naming |
| `MODEL_NAMES` mutation, `generate.py:299-302` | `agentprov_backend.attacks.AttackFactory` | **Removed as a hidden hack.** If the pipeline name matches a `MODEL_NAMES` key, the stock attack is used. Otherwise `cell.attack_params.model_display_name` is required: a scoped registration (context manager that restores `MODEL_NAMES` on exit) is applied for construction only. The attack is checked with `attack.model_name == display_name` where the attribute exists (`important_instructions_attacks.py:40-43`). This is declared as instrumentation `agentdojo.attack_model_display_name@1` |
| — | `agentprov_backend.attacks.RecordingAttack` | Delegating proxy; `attack()` returns the stock injections and records them via `hooks.fixture` |
| `envstate.py` | `agentprov_capture.envstate` | Extracted; optional full snapshots as blobs; the hash notation is unified (`sha256:` prefix) |

**Driving a cell.** The native log must be byte-for-byte what the stock harness writes. The backend therefore calls
the **stock public benchmark functions** inside `OutputLogger(logdir=<session native dir>)`:
- `benchmark.run_task_with_injection_tasks(proxy, pipeline, user_task, attack, logdir, force_rerun=True,
  injection_tasks=[cell.injection_task_id], benchmark_version=…)` for attacked and DoS cells;
- `benchmark.run_task_without_injection_tasks(proxy, pipeline, task, logdir, force_rerun=True, benchmark_version=…)`
  for user-task and pre-pass cells.

The stock functions do not forward `runtime_class` (`benchmark.py:117-119`). The backend therefore passes
`proxy = SuiteRunProxy(suite, runtime_class=RecordingFunctionsRuntime.bind(session))`. This is a delegating object
whose only override is `run_task_with_pipeline`, which injects `runtime_class`.

Consequences:
- The stock error imposition (`benchmark.py:122-147`), the DoS rule (`:149-150`) and the TraceLogger construction
  (`:106-116`) run **unchanged**. The native JSON's `error` field then drives the outcome origin, as for imports.
- An `OutputLogger` MUST be installed; otherwise `TraceLogger` writes into the package directory (`logging.py`
  `dirpath` default).
- One cell runs at a time per process, because the logger stack is a ContextVar with a shared mutable default
  [sources/agentdojo.md §9].
- Exceptions that the stock functions do not catch are recorded with `record_error`. The session is sealed with
  status `errored`; partial native JSON is kept as evidence.

### D.10.6 Identity guards and the differential test

**Before spawn (T0).** The parent computes, from the built environment's files and without importing anything: the
`uv.lock` digest, the dist-info RECORD digest of the benchmark distribution, the PEP 610 `direct_url.json` identity,
and the sha256 of the guarded source files, and compares them with the profile pins (`[family.agentdojo.live] pins`).
It sends them as `hello.expect` and cross-checks them against `hello_ok` and the capture `identity` event, so that the
checked process does not answer its own check (SR-09(3), R-39). The worker additionally reports `inspect.getsource()`
digests of the guarded qualified names (`ToolsExecutor.query`, `TaskSuite.run_task_with_pipeline`,
`model_output_from_messages`, `TraceLogger.log/save`, and the private OpenAI helpers that `GatewayLLM` uses:
`_function_to_openai`, `_message_to_openai`, `_openai_to_assistant_message`, `chat_completion_request`)
[audit/capture.md §4.1 defect 4]. Any mismatch raises `IdentityMismatch` (exit 3). Nothing is run.

**Differential test** `backends/agentdojo/tests/test_executor_mirror.py` (K.8.2, K.9.4; backend project, Python 3.12,
`uv sync --locked`). For every suite, it runs stock `ToolsExecutor(tool_result_to_str)` and `MirrorToolsExecutor` on
deep-copied identical inputs and asserts **equal message lists and equal post-environments** (compared as JCS values).
The inputs cover:
- valid calls;
- an empty function name;
- an unknown tool;
- string-encoded list arguments (in-place `literal_eval`);
- a tool that raises;
- a pydantic validation error;
- parallel calls;
- `id=None`.

A runtime differential in the same project does the same for `RecordingFunctionsRuntime` against `FunctionsRuntime`; `backends/autodojo/tests/test_executor_mirror.py` repeats the executor check against the fork.

### D.10.7 Declared instrumentation (observer effects)

Every session MUST declare its instrumentation in the `instrumentation` event, in the AD-03 shape
`{id: "<ns>.<name>@<n>", kind ∈ behaviour_preserving | request_modifying | harness_policy | attack_parameter |
test_only, recorded ∈ full | summary | none, params?, detail?, code_ref?}`. Parameters go in `params`, never in the id.
The capture mapper copies the list into the AER header (D5). Per execution, the counts of resampled and of retried
replies are recorded in the `params.observed` member of the item they belong to (O by capture), and are recomputable
from the `model_call` records (`status: "discarded"`, `retry_of`). The v0.1 list for the AgentDojo backend
[audit/capture.md §6]:

| id | kind | recorded | Note |
|---|---|---|---|
| `agentdojo.pass_recorder_wrap@1` | behaviour_preserving | full | wraps the pipeline; re-raises aborts |
| `agentdojo.executor_mirror@1` | behaviour_preserving | full | `params {mirrors: "0.1.35"}`; verified by the differential test; digest recorded |
| `agentdojo.recording_runtime_class@1` | behaviour_preserving | full | delegates to `FunctionsRuntime` |
| `agentdojo.recording_transport@1` | behaviour_preserving | full | records every wire exchange; both LLM elements; for provider `anthropic` the async twin (`params {sdk: "anthropic", mode: "async", inner_keepalive: 0}`; a streamed reply is read to its end before the SDK parses it; the inner transport keeps no connection alive, since the stock element runs each query in a new event loop, D-656 R-1) |
| `agentdojo.llm_span_brackets@1` | behaviour_preserving | full | records `input_at`/`n_messages`; no request change |
| `agentdojo.role_rewrite_developer_to_system@1` | request_modifying | full | `gateway_compat` only |
| `agentdojo.temperature_not_transmitted@1` | harness_policy | full | stock 0.1.35 `temperature or NOT_GIVEN`; configured 0.0 is recorded separately from transmitted |
| `agentdojo.retry_malformed_tool_json@1` | harness_policy | full | `gateway_compat` only; `params {max: 8, observed: {resampled: n}}`; stock raises |
| `agentdojo.retry_upstream_failure@1` | harness_policy | full | `gateway_compat` only; `params {max: 8, observed: {retried: n}}` |
| `agentdojo.http_backoff@1` | harness_policy | full | `params {statuses: ["429", "5xx"]}`; under `native` the SDK's own retries are stock and each wire attempt is recorded by the transport |
| `agentdojo.reasoning_passback@1` | request_modifying | full | `gateway_compat` only; OpenRouter only; reset per pass |
| `agentdojo.attack_model_display_name@1` | attack_parameter | full | `params {display_name}`; when not resolvable from stock `MODEL_NAMES` |
| `agentdojo.env_dump_per_pass@1` | behaviour_preserving | full | read-only `model_dump` |
| `agentdojo.transport_scripted@1` | test_only | full | **corpus packaging refuses `test_only` sessions in release mode** |
| `agentdojo.scheduler_parallel_workers@1`, `agentdojo.scheduler_start_stagger@1` | harness_policy | summary | `params {n}`; timing contention only |
| `agentdojo.anthropic_element_port@1` | behaviour_preserving | full | provider `anthropic` (D-656): the declared port of `AnthropicLLM` (`query`, `chat_completion_request`); `temperature` goes through `extra_body` when set, because `anthropic` 1.x has no such parameter; otherwise the stock source (AST-checked) |
| `agentdojo.anthropic_max_tokens@1` | harness_policy | full | provider `anthropic`: `params {max_tokens, mode: explicit\|harness_default, stock_default: 1024}` (D-656 Q3) |
| `agentdojo.defence_pipeline_rewrite@1` | behaviour_preserving | full | D.10.11: the defended pipeline as built, with the recording substitutions; `params {defence, substitutions}` |
| `agentdojo.defence_recorder@1` | behaviour_preserving | full | D.10.11: the recorders that observe the defence's verdicts; `params {recorders}` |
| `agentdojo.defence_aux_span@1` | behaviour_preserving | full | D.10.11: the defence's model calls bracketed as `def0`'s auxiliary calls |
| `agentdojo.defence_code_provisioned@1` | behaviour_preserving | full | D.10.11: third-party code from pinned blobs; `params {repo, commit, files}` |
| `agentdojo.defence_weights_offline@1` | behaviour_preserving | full | D.10.11, D-672: pinned weights loaded offline; `params {repo, revision, files, device}` |
| `agentdojo.defence_port@1` | harness_policy | full | D.10.11, D-674: what a port changes (never the decision logic); `params {port, changes}`; must-not-claim NC-LIVE-03 (D-674: "the authors' released implementation as run"), added to I.4.3 with its claims-library rule when the defence core lands (regen-batch item 167) |

### D.10.8 Tests

All tests that import `agentdojo` live in the backend projects (`backends/agentdojo/tests`, `backends/autodojo/tests`),
run on Python 3.12 after `uv sync --locked` in that project; the pytest markers `agentdojo` and `autodojo` mean
"backend project", not a core extra (R-01). Core tests use committed `capture/0.1` fixtures and never the transport.

- **Scripted-transport integration.** The pattern of `tests/test_attempts.py`, now at transport level: a real banking
  `user_task_1` is driven through `build_instrumented_pipeline` with `agentprov_backend.testing.ScriptedTransport`
  (an httpx transport that returns scripted chat-completion JSON, as `_FakeClient` does at
  `tests/test_reasoning.py:38-47`), under both `native` (default) and `gateway_compat`. The baseline cases are
  carried over:
  - re-run kept and logs reset per pass;
  - passback reset;
  - cross-pass id reuse;
  - provider failures;
  - malformed arguments;
  - 5xx/4xx policy;
  - gate positive and negative;
  - no-usage providers;
  - environment chaining.

  New cases:
  - an `AbortAgentError` pass;
  - discarded-reply content recorded;
  - `input_at` and `n_messages` recorded on every `llm.request`;
  - a failing cell sealed and kept;
  - attempt indices;
  - a secrets-absent assertion (no API key bytes in any artefact).
- **Live-versus-native differential** over the scripted cells, including a 3-pass re-run and a run error.
- **Offline guarantee.** A socket guard fails any test that opens a network connection.
- The hostile-T2 cases (home read, write outside staging, `../x`, a symlinked reported artefact) are security tests
  owned by G and K (SEC-14, SEC-25).

---

### D.10.9 Artefact controls for live capture (DECISIONS D-11)

The AgentDojo-PROV manuscript's generated corpus (17,664 traces, 6 models) had 13 known artefact classes. The
catalogue, compiled from the manuscript, the capture audit and the baseline code, is summarised in the table below.
AgentPROV applies one principle to them: **it never alters an execution to hide an artefact.** It works in four ways:

- it removes harness-caused artefacts by construction;
- it refuses known-bad configurations before any budget is spent (preflight);
- it stops a misconfigured campaign early (canary);
- it flags whatever still occurs, as evidence-class-I `note` events and seal issues, on the live feedback channel
  (MN N.1.14) and in the end-of-run capture-quality report.

| # | Artefact (baseline generated corpus) | Control in AgentPROV |
|---|---|---|
| A1 | Re-runs: up to 3 passes when the final reply is empty; earlier passes lost (153 traces incomplete) | **Prevented** (loss): the pass recorder keeps every pass with before and after environment digests (D.10.2, D.10.5; C.12 `passes_closed`). **Flagged:** `n_passes` in the index, and a note `outcome_pass_mismatch` when the scored environment is not the last pass's after-digest |
| A2 | Completeness unknown without usage (2,944 DeepSeek traces); mixed capture generations | **Prevented:** the call gate compares kept wire exchanges with assistant messages (C.12.2 `agent_calls_vs_assistant`); sessions record writer, identity and instrumentation |
| A3 | Configured temperature 0.0 never transmitted (`temperature or NOT_GIVEN`) | **Preflight:** when a configured parameter would not be transmitted (rule `agentdojo.temperature_not_transmitted@1`), `run` refuses with a usage error (exit 2) until `--temperature-policy` is chosen: `as-benchmark` (stock behaviour, recorded) or `inject` (the transport sets it, declared `request_modifying`, D.10.7). **Flagged:** on every kept call, configured and transmitted values are compared, and a mismatch gives a note `param_not_transmitted` |
| A4 | Tool calls written as text and never executed (470 traces, 469 of them Llama 3.3 70B); narrated calls | **Preflight probe:** a canned two-tool request per endpoint and model before the first cell checks that a structured `tool_calls` reply is returned. A text-encoded call refuses the run (exit 4) unless `--allow-text-tool-calls` is given (recorded). The probe matters most for local servers (oMLX, Ollama), where the tool-call parser depends on the server's model template. **Flagged:** a note `text_tool_call_suspect` when a kept reply has no structured calls but its text names a catalogue tool or carries `<function=` or `<\|python_tag\|>`. Provider routing (OpenRouter) is recorded with the transmitted parameters |
| A5 | `max_iters` cut with calls pending (47 traces) | **Flagged:** seal issue `unexecuted_tool_call`, scope status `limit` (C.12.2–3). The step feed shows the cut as it happens |
| A6 | Abnormal finish reasons (184 traces), lost to a broad `except` | **Flagged:** the verbatim per-call `finish_reason`, and a note `abnormal_finish` when a kept reply ends with anything other than `stop` or `tool_calls` (for provider `anthropic`: `end_turn`, `tool_use` or `stop_sequence`; D-656). A `length` finish names the `max_tokens` setting in the quality report |
| A7 | Failed tool calls recorded as `""` while the model saw the error | **Prevented:** the model-visible text is recorded separately (`error_substitution` transform); `tool_execution.status` is recorded |
| A8 | Duplicate provider tool-call id (GLM-4.6), timing overwritten | **Prevented:** harness `occ` ids; provider ids are attributes only (C.4.4) |
| A9 | Harness side effects: `developer`→`system` rewrite, resampling, retries, fixed 180 s timeout, random 0–20 s stagger | **Prevented** by default: the `native` element is stock, and the transport records every HTTP attempt, including the SDK's own retries and 429/5xx replies. The stagger is deterministic (D-9). **Preflight probe:** checks that the endpoint accepts the stock message roles. On rejection, the run refuses and names `--llm-element gateway_compat`, which is declared instrumentation |
| A10 | Title-cased model display name inside the attack payload | **Prevented:** no derived names. The benchmark's own table is used, or `--model-display-name` is required (declared `attack_parameter`) |
| A11 | Aborted cells silently re-run and omitted (selection) | **Prevented** (silence): every attempt is sealed and kept (`capture.attempt`; N.1.8(4)). Attempts per cell and model appear in the quality report and the datasheet. The preflight probes and the canary remove most configuration-caused aborts before they happen |
| A12 | Served model, routing and reasoning not recorded | **Recorded:** per-call `served_model`, route and raw response blob (L.2.2). Any reasoning request is declared `request_modifying`. **Canary (D-694):** a reply whose `served_model` is absent or differs from its request's `model`, unless accepted with `--accept-served-model` (recorded), stops the campaign; the quality report counts `served_models` and `served_model_mismatch` |
| A14 | A local model changed under the same name during a campaign (re-pulled, re-quantised, swapped) | **Prevented:** the model's observed identity (D-692) is part of the configuration digest, so another model is another configuration (G5). **Flagged:** T0 re-observes the server side before every cell; the session's `agentdojo/local_model` note says whether it matches the plan, and a mismatch is a canary condition (`local_model_drift`; D-695) |
| A13 | Benchmark-validity defects (vacuous utility, unwinnable or order-dependent tasks, payload never reached the agent) | **Flagged (partial):** a note `utility_without_state_change` from the pass digests, and the injection-reached-agent marker from SEM. The replay-based cell probes stay **deferred** (AD-10 as ruled; `docs/roadmap.md`) |

**Preflight** (`agentprov run`, before the first cell; also `run --preflight-only`). The probes run once per endpoint
and model:
- the server or endpoint is reachable (N.2.1a(1)); for a local server, its kind is the shorthand's, the model id is
  served, and the model's identity is observed (D-691..D-693);
- configured parameters are transmitted (A3);
- structured tool calls come back (A4);
- the stock roles are accepted (A9), judged from the reply itself, never from a 2xx status alone (D-291).

Each probe is a small canned request, sent through the same recording transport. Probe exchanges are written to the
session staging area as a separate `probe` session, with role `supporting`, and are never mapped to an execution.
They cost at most a few hundred tokens per endpoint, which is covered by the run's consent. A failed probe prints its
remedy and exits 2, 3 or 4 according to N.1.3.

**Canary** (`--canary N`; default 10 cells for every live run; `--canary 0` disables it). The first N cells run first.
If any canary cell shows one of A3, A4, A6 (more than 20 % of calls), A9 or an errored or aborted attempt, the run
stops after the canary, prints the capture-quality report and exits 1, with nothing beyond the canary spent. The
canary cells are ordinary sealed sessions and stay in the corpus. `--resume` continues the campaign after the cause
has been fixed or explicitly accepted.

**Capture-quality report.** It is printed at `summary` level and above, and written to the `--json` summary. It counts
each control above per model, the passes per cell, attempts per cell, retries and HTTP status classes, and the
instrumentation in force. Its counters are also live on the `status` line (MN N.1.14). The report is derived from
sealed evidence and is reproducible from the corpus by `agentprov stats`.

### D.10.10 Implementation resolutions (phase 8, harness)

Phase 8 stream B built `agentprov_backend` (`backends/shared/src/agentprov_backend/`) and the AgentDojo backend tests
against `agentdojo==0.1.35` and the locked `openai` 3.26.0. File:line references below are to the installed packages of
`backends/agentdojo/uv.lock`. `capture/0.1` and `aer/0.1` were not changed; everything the frozen event payloads cannot
hold went into namespaced `note` events (C.13.3), listed here.

**Modules.** `transport` (recording transport), `gateway` (`LlmSpan`, `WireRecorder`; lazily `SpannedLLM` and
`GatewayLLM` from `_llm`), `pass_recorder`, `executor_mirror`, `runtime`, `attacks`, `identity` (the worker's
self-report), `session` (`CaptureSession`, re-exported by `runner`), `runner` (dataclasses, plans, pipeline,
`SuiteRunProxy`, `AgentDojoBackend`, `run_probe`), `worker`, and `testing` (`ScriptedTransport`, `netguard`,
`scenarios`). D.10.5's element written `LlmSpan(llm)` is `_llm.SpannedLLM`; D.10.1's `LlmSpan` protocol is the context
manager `gateway.LlmSpan` that `CaptureSession.span(role, actor, messages)` returns.

1. **Native log location.** The stock runner runs inside `OutputLogger(logdir=<session>/raw/native-tmp)`, so
   TraceLogger writes `raw/native-tmp/<pipeline_name with / -> _>/<suite>/<user_task>/<attack|none>/<injection|none>.json`
   (`logging.py:237-241`). After the stock function returns or raises, the file is moved unchanged (`os.replace`, same
   bytes) to `raw/capture/<session>.native.json` (the C.13.1 name), the empty transient tree is removed, the stock
   relative path is recorded in a note `agentdojo/native_log_stock_path {logdir_relative}`, and a `native.log` event
   announces the label. Labels therefore never contain model ids (which may hold `:` or `/`). A missing or ambiguous
   native file gives a note `agentdojo/native_log_problem` and the status `incomplete`.
2. **HTTP module.** `openai` 3.26.0 sends with `httpx2`, not `httpx` (`openai/_base_client.py:37`; legacy `httpx`
   clients take a compatibility path, `openai/_httpx2.py`). The recording transport and `ScriptedTransport` are
   therefore transports of the module the SDK's `_base_client` imports (`agentprov_backend._http.sdk_httpx`; `httpx2`
   here, `httpx` for a 1.x SDK), and the SDK client is `openai.DefaultHttpx2Client(transport=RecordingTransport(inner))`.
   K.3.2's "built on `httpx.MockTransport`" reads `httpx2.MockTransport` for this lock. `httpx2` comes with `openai`; it
   is not declared, so no lock changed. The real inner transport reproduces the SDK's `DEFAULT_CONNECTION_LIMITS`.
3. **Lock digest source** (`session.start.runtime.lock_sha256`, `hello_ok.identity.lock_sha256`). (a)
   `<sys.prefix>/AGENTPROV_ENV.json` member `lock_sha256`, written by `agentprov backends build` (D.11.2, G.6.2); (b)
   for an in-project environment (`backends/<b>/.venv` from `uv sync --project`, the development and CI layout) the
   sha256 of `<sys.prefix>/../uv.lock`; (c) otherwise the worker refuses (`LockDigestUnavailable`, reported `fatal` at
   `hello`). The source is reported as `lock_source` (`marker` | `project_lock`). T0 computes the digest from the lock
   independently (D.10.6), so the worker's value is only cross-checked.
4. **`llm.request`/`llm.response`.** One `llm.request` per wire attempt, emitted before the send: `call` `c<n>` unique
   per session, `attempt` = index of the wire attempt within the span, `retry_of` = the span's previous call,
   `endpoint {host, path}`, `params.configured` = `AgentConfig.params`, `params.transmitted` = every top-level member of
   the decoded request body except `model`, `messages` and `tools` (so `tool_choice` appears; `temperature` only when
   sent), the exact body as a blob (media from `content-type`). Headers have no `capture/0.1` member: each exchange
   is followed by notes `agentdojo/wire_headers {call, direction: request|response, kept, dropped}` built with
   `Redactor.filter_headers` (C.13.10 item 13; allowlisted values, scanned, plus the names of every other header, so
   `authorization` appears only as a dropped name; the endpoint entry's declared headers extend the allowlist). A
   response's header note follows its `llm.response`. A non-2xx reply is `status: error` with `http_status` and `reason: http_<status>` at
   once; a transport failure is `error` with `exception` and `reason: transport_error`. A 2xx reply is emitted when its
   fate is known: `kept` when the element returns with it, `discarded` with `reason: superseded_by_retry` when another
   request follows inside the span, `discarded` with `reason: element_raised:<Type>` when the element raises after
   receiving it (stock `json.loads` of malformed arguments, `openai_llm.py:115`; `choices[0]` of `None`), or as
   `GatewayLLM` marks it. Its `ts` is therefore the decision time, after the SDK and element parsed the reply.
   `usage` maps `prompt_tokens`/`completion_tokens`/`total_tokens`/`reasoning_tokens`/`cached_tokens` to the AER names;
   `served_model`, `response_id` and `finish_reason` are copied when present. The response blob is the entity body
   after content decoding (what the SDK parses), not the compressed wire framing.
5. **`input_at`/`n_messages`.** The span records `n_messages = len(messages)` given to the element and
   `input_at = [0, ..., n-1]`, because the stock element (`openai_llm.py:196`) and the port send every message in
   order. The recorder checks this against the decoded request: when the body does not carry exactly `n_messages`
   messages, `input_at` is omitted, `n_messages` kept, and a note `agentdojo/input_at_unverified` written. A request
   outside any span (none in v0.1) is `role: auxiliary` with a note `agentdojo/unbracketed_request`.
6. **Observed counts.** `instrumentation` is the second event (C.13.2, frozen), so per-execution counts cannot be in
   it. They are written just before `session.end` as a note `agentdojo/instrumentation_observed`
   `{<item id>: {resampled|retried: n}}` for `retry_malformed_tool_json@1`, `retry_upstream_failure@1` and
   `http_backoff@1` under `gateway_compat` (zeros included); the mapper copies them into `params.observed`. They remain
   recomputable from the `discarded` responses and `retry_of`.
7. **Identity.** The `identity` event's schema is closed (C.13.9) and has no member for the RECORD digest, the PEP 610
   source, the guarded-source digests or the lock. They follow it as a note `agentdojo/identity_digests` carrying the
   whole `BenchmarkIdentity` (`distribution, version_reported, source, record_digest, guarded_sources, suite_set,
   benchmark_version, default_system_prompt_sha256, tool_definitions_sha256, python, platform, lock_sha256,
   lock_source`); T0's cross-check of the capture identity reads that note. Two more notes follow:
   `agentdojo/cell {cell_key, kind, benchmark_version, plan_sha256}` (the cell kind has no `cell` member) and
   `agentdojo/pipeline {name, llm_element, transport}`. `guarded_sources` covers the D.10.6 names plus
   `OpenAILLM.query`, `FunctionsRuntime.run_function` and the two stock runner functions. A PyPI wheel has no
   `direct_url.json`: `source` is `{"kind": "pypi"}` and `identity.benchmark` carries no `commit`/`wheel_sha256`.
   `tool_definitions_sha256` is the JCS digest of `{suite: [{name, description, parameters}]}` over the suite set.
8. **Worker protocol.** As D.11.3, with: `hello.expect` accepted and unused (the parent checks); additions `plan`
   (`req`, `plan_toml`) answered by `plan_ok` (`plan` = expanded `RunPlan` with `plan_sha256`) or `plan_refused`
   (`error`); `catalogue` (`req`, optional `benchmark_version`; D-652) answered by `catalogue_ok` (`catalogue` =
   `agentprov-backend-catalogue/0.1`: the suites with their user and injection task ids and the character count of
   their tool definitions, the attack registry's names with `dos`, and the backend's `refused` reasons and `needs`;
   names and counts only) or `catalogue_refused` (`error`);
   `run_cell.session.dir` (absolute staging directory; without it the working directory is the session
   directory) and `run_cell.backend_config`; `probe`/`probe_done` (item 15). `run_cell` before `hello`, an unknown op,
   a malformed line (not UTF-8, not JSON, duplicate keys, `NaN`, wrong `v`, over 1 MiB) is `fatal` and exit 2; EOF and
   `shutdown` exit 0. `step` carries `req`, a per-cell `seq`, `kind` and metadata only (pass index, call or occurrence
   id, phase, status, judgement name and origin; strings capped at 64 characters). `progress` follows each `pass_end`.
   Both are dropped, never blocking, when the bounded writer queue is full (D-8); every other message is sent in order.
   `cell_done.artefacts` lists every regular file under `<session>/raw/` with roles `capture_log`, `native_log`, `blob`
   or `supporting`; files outside `raw/` (the parent's script file) are not reported. The protocol channel is a
   private duplicate of fd 1; fd 1 and `sys.stdout` are pointed at stderr before anything else is imported.
9. **Secrets.** Every session gets a redactor (`runner.build_redactor`, used by the worker, the tests and the fixture
   tool): `Redactor(secrets_from_environ(env) + [the AgentConfig.api_key_env value], home=<user home>, host=<host
   name>)` (C.13.10 items 11-12); a key value too short to scan (under 8 characters) refuses the cell. The key is read
   only to build the SDK client; it is sent in the `Authorization` header and appears in no event, blob, native log or
   protocol message (tested with a sentinel in-process and through the worker). Tracebacks are stored as
   `text/x-python-traceback` blobs and exception messages go into `error.exception`, both non-content surfaces where
   the redactor replaces home path, host name, URLs' secret parts and key patterns (C.13.10 item 9). A failed scan
   poisons the log: the harness writes nothing more and `close()` seals it `errored` (C.13.10 item 6); the cell result
   is then `errored`. `AgentConfig` gains an optional `base_url` (validated by `agentprov_capture.endpoints`;
   default: the registry entry's), because the T2 environment allowlist passes no `*_BASE_URL` variable.
10. **Passes.** `PassRecorder` emits `pass.end` for every `pass.start`. A pass cut by an exception other than
    `AbortAgentError` gets `pass.end{aborted: true}` with the last message list a harness element observed (the input
    of the failing element, which is also what TraceLogger last logged) and the environment as it is, preceded by an
    `error` event `where: "pipeline"`, `fatal: false`; the exception is re-raised unchanged. The message blob is the
    list serialised as TraceLogger serialises it (`json.dumps` with its `default`, `logging.py:256`; insertion order,
    Python float spelling, ASCII), without indentation. `pass.start.env` is `envstate.digest` of `model_dump(mode="json")`
    (plus a `snapshot` blob, on by default, `backend_config.env_snapshots`); `pass.end.env` is `envstate.end_env(before,
    after, snapshot_ref=...)`: digest, `changed`, and a capped `diff` when changed (E-3...E-5, F-12).
11. **Session status.** `complete`: the stock runner returned (its own error imposition included); `incomplete`: it
    returned but evidence is missing (no native log); `errored`: an exception escaped the stock runner, or the cell was
    refused before running (`UnsupportedConfiguration`: defence, non-YAML output, unknown suite or attack, missing
    display name; recorded as an `error` event `where: "setup"` in a sealed session with no pass); `aborted`:
    `KeyboardInterrupt` in the worker (a parent kill is appended by the parent, D.11.3 rule 3).
12. **Outcome origins** follow D.6.7: when the stock runner caught a provider error (a pipeline `error` event, or a
    non-null `error` in the native JSON) both judgements are `harness_default`; otherwise a benign cell's security is
    `harness_default`, a DoS cell's security `harness_rule`, and the rest `checker`. `declared_semantics` is a short
    text map of the stock polarity, kept as data for SEM. The outcome actor is `bench`; fixtures' actor is `attacker`.
13. **Tools.** `tool.dispatch.args` is the requested argument map before the stock in-place `literal_eval` of
    string-encoded lists (`tool_execution.py:99-101`); `at` is `{message: index of the assistant message, call: index
    in its tool_calls}`; `args_raw` is not recorded (it is in the response blob). `tool.result.status` comes from the
    recording runtime: `ok`; `invalid` for an unknown or empty name and for argument validation; `error` when the tool
    (or a nested call) raised, with `exception {type, message}` split from the stock `"<Type>: <message>"`.
    `model_visible` is `error or rendered` (`openai_llm.py:103`); `rendered` is the formatter's output (`""` when the
    call failed); `returned` (JSON-mode dump) only when the tool returned, inline up to 2,048 JCS bytes, else a blob;
    `args_effective` is the validated argument map.
14. **Attacks and fixtures.** The scoped `MODEL_NAMES` registration keys on the pipeline name, because the stock lookup
    is a substring match over the table in insertion order (`base_attacks.py:141-143`); it is used only when stock
    construction raises the no-model-name `ValueError`, and `attack.model_name == display_name` is checked for the
    attacks that take the name from the pipeline (not for `*_no_model_name`/`*_wrong_model_name`). A display name that
    contradicts the stock entry is refused. One `fixture` event per injection vector: `content` is that vector's
    payload string. The pipeline name is `backend_config.pipeline_name`, else `AgentConfig.model_requested`.
15. **Preflight probe** (the optional D.10.9 item, done). `runner.run_probe` and worker op `probe` send one canned
    two-tool request through the same element, SDK client and recording transport into a separate capture session
    (`cell.task_id = "preflight_probe"`, no pass, instrumentation `agentdojo.preflight_probe@2` (`harness_policy`; `@1`
    until phase 9b), a note `agentdojo/preflight_result`, artefacts reported `supporting`/`blob`). Results: `reachable`,
    `roles` and `roles_reason` (`runner.roles_verdict` over the recorded body of the last reply, D-291: `accepted` when
    the reply follows the instruction only the system message carries, `get_probe_value` with key `q7f3-probe`;
    `refused` on a non-2xx status, a 2xx `error` object or a role refusal in the text; `unconfirmed` for a 2xx showing
    neither; `unknown` without a reply), `roles_accepted` (`roles == "accepted"`; T0 refuses the others with exit 4),
    `http_status`, `params {configured, transmitted, not_transmitted}`,
    `tool_calls` (`structured` | `text_encoded` | `none` | `error`; text-encoded = no structured call but the text names
    a probe tool or carries `<function=`, `<|python_tag|>` or `<tool_call>`). Exit codes and the remedy text are T0's.
    *An Inspect backend (D-742)* has its own op `probe` (`agentprov_backend_inspect.probe`): the same request and
    result shape through the cell's Inspect model (OpenAI-compatible provider, `max_retries` as in a cell) and the
    shared async recording transport, instrumentation `inspect.preflight_probe@1`, note `inspect/preflight_result`.
    The verdicts are the shared functions. A configured sampling parameter shows as not transmitted, as in a cell.
16. **Instrumentation as emitted.** Always: `pass_recorder_wrap@1`, `executor_mirror@1 {mirrors: "0.1.35",
    source_sha256}`, `recording_runtime_class@1`, `recording_transport@1 {sdk, sdk_version, http_module}`,
    `llm_span_brackets@1`, `http_backoff@1` (`policy: stock_sdk` under `native`: the SDK's `max_retries=2` inside
    agentdojo's three tenacity attempts, i.e. up to nine wire attempts per element call, `openai/_constants.py:8`,
    `openai_llm.py:143-148`; `policy: gateway_compat` under the port), `env_dump_per_pass@1 {snapshots}`. When the
    element's temperature is falsy (the default 0.0, `openai_llm.py:162`): `temperature_not_transmitted@1 {configured}`.
    Under `gateway_compat`: `role_rewrite_developer_to_system@1`, `retry_malformed_tool_json@1 {max: 8}`,
    `retry_upstream_failure@1 {max: 8}`, and `reasoning_passback@1` only on an `openrouter.ai` host with pass-back on.
    Scripted transport: `transport_scripted@1`. The attack item when used; the scheduler items when
    `backend_config.scheduler` names them.
17. **`gateway_compat` port.** Behaviour as `_CompatLLM` (`runtime.py:121-393` at `579a908`): same request
    construction, retry policy, waits and client settings (`LLM_TIMEOUT_S`, `max_retries=0`). Differences, none
    behavioural: the progress lines go to stderr and name the exception type, not its text; the waits are injectable
    for tests; every non-kept reply is marked with its reason. The executor mirror is guarded by the AST digest of
    `ToolsExecutor.query` under CPython 3.12 (`MirrorMismatch` otherwise; formatting-independent, so the AST-identical
    AutoDojo method passes). `ast.dump` is interpreter-specific, so the digest is kept per interpreter
    (`executor_mirror.interpreter_key()`, only `cpython-3.12` recorded); on any other interpreter the guard raises the
    typed `MirrorUnverifiable` (code `backend.mirror.interpreter`) and the cell is refused (D-292).
18. **AgentDojo 0.1.35 facts the spec text did not state** (verified in the installed package):
    - malformed tool-call JSON fails the stock element outside the tenacity retry (`openai_llm.py:115` vs `:143-148`),
      so a native cell with such a reply ends `errored` (D.10.7's "stock raises", confirmed);
    - a real HTTP 400 surfaces as `BadRequestError`, which tenacity does not retry (`openai_llm.py:147`): one wire
      attempt under both elements. The baseline test `test_attempts.py:357-362` counted three attempts because its fake
      raised a generic `APIStatusError(400)`; gate C6 must not expect three;
    - `AbortAgentError` is raised only by `pi_detector.py:105`; the undefended v0.1 pipeline never raises it, so the
      aborted-pass scenario patches the executor to raise it where a defence would (test and fixture only);
    - injections are formatted into the suite's environment YAML before loading (`task_suite.py:144-145`); YAML line
      folding turns `\n\n` into `\n`, so the payload the model sees differs from `attack.attack()`'s return (and the
      native `injections`) in whitespace. The harness changes nothing (the wire tool content equals the native log's);
      the SEM marker normalisers collapse whitespace (`semantics/markers.py`). D.15 candidate artefact, below;
    - `get_suites` indexes a `defaultdict`, so an unknown benchmark version yields no suites silently
      (`load_suites.py:63`); plans and cells are validated against its keys;
    - the stock runner calls `load_task_results` even with `force_rerun=True` (`benchmark.py:86-99`); the harness
      always forces a rerun and the read finds nothing in a fresh session.
19. **Run plans** (`agentprov-run-plan/0.1`). `[plan]` (`format` required; `backend`, `benchmark_version` (v1.2.2),
    `suites` (required), `user_tasks`/`injection_tasks` (`"all"`, a list of ids, or index ranges `"0-9,12"` over the
    list sorted by numeric suffix), `attacks`, `benign` (`include|exclude|only`), `defence` (only `none`),
    `injection_tasks_as_user_tasks`, `tool_output_format` (only `yaml`)), `[agent]` (`AgentConfig`), `[attack_params]`,
    `[backend]` (`backend_config`: `pipeline_name`, `env_snapshots`, `repeats`, `scheduler`, ...). Unknown `[plan]`
    keys are refused. Cell order: per suite, pre-pass cells, benign cells, then per attack, user task, injection task
    (a DoS attack: one cell per user task with the suite's first injection task, `benchmark.py:73-75`). `plan_sha256`
    is the JCS sha256 of `{format, cells, agent, backend_config}`; repeats are not expanded into cells.
    `config_sha256` is the JCS digest of `{backend, cell, agent, backend_config, plan_sha256}` (no secret values).
20. **Tests and fixtures.** Backend tests run offline with the network guard and no-op sleeps (retry back-off never
    changes what is sent). The scripted scenarios live in `agentprov_backend.testing.scenarios`;
    `backends/agentdojo/tools/make_capture_fixtures.py` writes them to `tests/fixtures/capture/<scenario>/` (session
    tree, `script.json`, `SOURCE.json`). Regeneration changes the session id (UUIDv7), times, chain hashes and digests;
    `--check` compares the stable projection (RPR-10).

**D.15 standing rule (live-capture artefacts found in phase 8; the `agentdojo` catalogue is core's and is updated by
the orchestrator).** (a) *Payload whitespace folding* (cause `benchmark`; detector: payload versus model-visible text
after whitespace collapse; handling FO; the SEM normalisers already tolerate it; item 18). (b) *Nested stock retries*:
under the stock element one call can make up to nine wire attempts (cause `upstream_harness`; recorded per attempt,
CR). (c) *Fake-client 4xx count in the baseline tests* (cause `baseline_converter`-like test artefact; matters for C6).

### D.10.11 Defended pipelines (D-670..D-679)

A live cell may run one defence (`CellSpec.defence`, `--defence`, `[plan] defence`). The defence is the experimental
treatment, never an observer effect: it is recorded as the defence's own actions (`cell.defense_id`, the actor `def0`
of kind `defense`, its `decision` events, its auxiliary model calls and the messages it inserts). Only what the harness
adds to record it is instrumentation (§D.10.7). Design and rationale: `docs/reports/defence-backends/design.md`.

**Registry.** `backends/shared/src/agentprov_backend/defences.toml` (format `agentprov-defence-registry/0.1`, package
data of the harness) lists every defence the harness can build: its id (the arm name the method's own code uses, so
live and imported `defense_id` values agree), the backends that build it, the provider (`builtin`: the installed
benchmark's `PipelineConfig.defense`; `provisioned`: third-party code pinned to `repo@commit` and file blob ids, copied
from the bare fetch cache into `<env>/agentprov_defences/<id>/` by `agentprov backends build --defence-assets ID`, never
into the repository), its licence, the guarded source digests (`inspect.getsource` sha256; a difference refuses the
entry), its elements and the recorder each gets, its suites, its assets (Python modules, pinned weights) and declared
cost priors. Pinned model weights (D-672) are copied from the fetch cache into the environment's offline Hugging Face
cache `<env>/agentprov_defences/hf/` and the `defences` dependency group is installed; the worker then runs with
`HF_HUB_CACHE`, `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, and the harness refuses to load weights otherwise. A
defence that calls its own endpoint (MELON's embeddings) names it with `run --defence-endpoint NAME` (D-675); only that
endpoint's key enters T2. The worker reads the installed copy; T0 reads the repository copy (the core never imports
the harness).

**T0** (`agentprov.cli.live.defences`; N.2.1b) checks the defence before anything is spawned, from the flag and from a
plan alike (D-679): it must be in the registry, built by the backend, allowed by the live profile's
`[family.agentdojo.live] defences` (absent: none; `agentdojo-live` v3 lists the first set of D-671, its v1 and v2
and `autodojo-live` none), and run only on its suites. Every refusal is exit 5. Once the
environment is known, its installed registry must equal the repository's (else exit 3: rebuild) and a provisioned
entry's pinned files must be present (else exit 5).

**Building.** The benchmark (or the provisioned entry point) builds the defended pipeline; the harness rewrites the
element tree: the stock `ToolsExecutor` becomes `MirrorToolsExecutor` with the **same** output formatter, each agent LLM
element `SpannedLLM`, each declared defence element its recorder, a provisioned gate executor replaces the stock one
under `GateRecorder`, and the whole is wrapped by `PassRecorder`. An undeclared element is refused
(`UnsupportedConfiguration`). The pipeline keeps stock's name `<model>-<defence>`, so native logs land as stock writes
them. A stock-versus-instrumented differential test per defence (`backends/agentdojo/tests/test_defences.py`) asserts
equal message lists, environments, outcomes and wire requests.

**Recorders** (delegating; inputs and outputs unchanged):

| Recorder | Elements | Capture |
|---|---|---|
| `prompt_wrapper` | `repeat_user_prompt`'s loop `InitQuery` | `note agentdojo/defence_message {at, actor, role}` per appended message |
| `tool_list_filter` | `tool_filter` | its model calls in an `auxiliary` span of `def0`; `note agentdojo/defence_tools {before, after, calls}`; `defence_message` notes for its prompt and reply (the reply names its call) |
| `output_filter` | PI detectors (`observe = "detect"`) | per checked tool output a `decision` with subject `{occ}`: `redact` with the content before as `original` (a blob), `allow` only when the verdict function was observed (D-673), `terminate` on `AbortAgentError`; `reason` = label and score |
| `llm_detector` | a port's detector that is also the loop's model step (MELON) | its model calls bracketed (the real step as the agent's, the masked re-run as `def0`'s detached auxiliary call, `note agentdojo/defence_detached_input`), its embeddings as `def0`'s auxiliary calls; `redact` (with `original`), `allow` with the detector's own route and score, `modify` on the agent call whose reply it replaced (the reply kept) with the stop message noted as the defence's; its own log as `note agentdojo/defence_log` |
| `executor_gate` | provisioned gate executors | dispatches when the recording runtime sees the call run; a call that never ran and whose error matches a declared denial is `tool.result {status: denied, decided_by: def0}` plus `note agentdojo/defence_denial_match`; stock invalid texts stay `invalid`; anything else gets no result (`note agentdojo/defence_unclassified_non_execution`); `note agentdojo/defence_gate_post_hoc` names the occurrences recorded after the gate returned |

`session.start.actors.def0` declares the defence (with the agent's model for `aux_llm = "agent_endpoint"`), and `note
agentdojo/defence_identity` records the registry digest, the entry and the guarded sources as installed. No event type
is added: `capture/0.1` is unchanged.

**Mapping** (`agentdojo.capture`; regen-batch item 167, after the round, with `agentdojo-live@3`): a
`defence_message` note makes the message the defence's (`defence.message_by_defence@1`, D); an auxiliary call of the
defence generates the assistant message its note names, which the agent-call accounting does not pair; a denied result
is a `deny` decision with the defence's text as reason and, with a denial match, a class-D actor
(`defence.denial_declared_text@1`); a post-hoc gate decision has no time (`unk /t not_captured`); the live-versus-native
check leaves out the native log's executions of denied calls (the TraceLogger writes them as errored tool messages);
`ext.agentdojo.defence` carries the identity note. The rules are in the catalogue `defence` (D-677).

**First set** (D-671): `repeat_user_prompt`, `spotlighting_with_delimiting`, `tool_filter`, `transformers_pi_detector`
(needs the D-672 assets), `mandate_envelope`, `mandate_scoped`, `mandate_intent` (provisioned from
`jwilliamsc/mandate-agentdojo-eval@fa62a977`), `melon`, `melon_sm`, `melon_at` (`xwsdid/MELON@71d99dff` through the
port; `melon_at`'s adaptive state lives for one cell). `melon_r` is not built: in recovery mode it inserts a system
message at position 0 and replaces tool messages by copies, which the recorders cannot attribute.

## D.11 AutoDojo backend (`backends/autodojo`)

[R-01, R-39, R-25, AD-01, AD-09, AD-13]

### D.11.1 Why it is a separate environment

AutoDojo's `agentdojo/` is a fork distributed as **`agentdojo` 0.1.35**, the same name and version as PyPI, so it
cannot share an environment with `agentdojo==0.1.35` (D5) [sources/autodojo.md §7; verify/autodojo.md #18]. The
fork's differences relevant to capture:
- `openai_llm.py` transmits temperature 0.0, retries malformed tool-call JSON, pins Gemini on OpenRouter with
  `reasoning.max_tokens=-1`, and adds Anthropic cache control;
- `benchmark.py` sets `security=False` plus `error_type` on error-skipped tasks;
- `logging.py` uses no `/`→`_` replacement and an optional `<attack>_<injection_attack_name>` directory;
- `ToolsExecutionLoop` adds `max_input_tokens`;
- the AgentDyn suites are registered under every version;
- `suite_gen_utils.py` calls `nltk.download("punkt_tab")` at import.

`ToolsExecutor` is AST-identical to PyPI 0.1.35 [verify/autodojo.md #18, §3.4].

### D.11.2 Backend project and environment

- **Project.** `backends/autodojo/` is a separate uv project with its own `pyproject.toml`, committed `uv.lock`
  (hash-locked) and `.python-version` `3.12` (the fork requires ≥ 3.10). It depends on `agentprov-capture` and
  `agentprov-backend` by path, on the fork as a **pinned git dependency in the lock**,
  `agentdojo @ git+https://github.com/xhOwenMa/AutoDojo@aa458794b7eb7f082e94daeac4c0f55bfc0c90cc#subdirectory=agentdojo`
  (the inspected commit [verify/autodojo.md §6]), and on the fork's runtime needs named in [sources/autodojo.md §7]
  (`json_repair`, `nltk`). **It does not install AgentPROV core** (AD-01): only `agentprov-capture` and
  `agentprov-backend`, so `agentdojo` resolves to the fork and nothing requires Python 3.14.
- **Build.** `agentprov backends build autodojo --allow-network` (G.6.2) is the only step that downloads packages. It
  runs `uv sync --locked --no-config` on `backends/autodojo` with `UV_PROJECT_ENVIRONMENT=$AGENTPROV_HOME/envs/autodojo-aa458794/`
  (outside the repository, so no `.venv` appears in the working tree) and with every resolution- or
  configuration-redirecting `UV_*` variable scrubbed. A resolution failure is `BackendUnavailable` (exit 3) and is
  reported by `agentprov info`. Identity is read from PEP 610 `direct_url.json` of the installed fork (R-49); there
  is no upstream working tree and no editable fork.
- **NLTK.** `punkt_tab` is pre-provisioned during the build into `<env>/nltk_data`, its digest is recorded, and
  `NLTK_DATA` is set for the worker. A network attempt at import time is therefore unnecessary, and is a test failure
  under the socket guard.
- **Marker.** The build writes `<env>/AGENTPROV_ENV.json` (`{commit, lock_sha256, python, built_at, nltk_sha256}`).
  `agentprov info` reads it.

### D.11.3 Worker protocol (`agentprov-backend/0.1`)

The parent (`agentprov run autodojo`, T0, core, no fork code) launches the worker directly, without `uv` at run
time:

```
<env>/bin/python -I -B -m agentprov_backend.worker
```

with working directory `$AGENTPROV_HOME/staging/<session>/`, `HOME=$AGENTPROV_HOME/t2home/<session>`, and an
explicit environment allowlist (G.6.3 as amended by AD-13): `PATH`, `HOME` (the T2 home above), `LANG`, `TZ`,
`NLTK_DATA`, the key variable named by the selected endpoint entry only, `HUGGING_FACE_HUB_TOKEN` only when a filter
defence that downloads weights is configured, `AUTODOJO_CACHE` and `AUTODOJO_VARIANT`, and `AGENTPROV_BLOCK_NETWORK`
in tests. There is **no** `UV_*` wildcard and the real `HOME` never passes.

**Channels.**
- stdin and stdout carry **UTF-8 JSON Lines**, one message per line, at most 1 MiB, each with
  `"v": "agentprov-backend/0.1"`. The parent reads them through the strict loader.
- stdout carries the protocol only. The worker redirects library prints to stderr.
- stderr is captured to a staged file (role `supporting`), scanned for secrets like every staged file, and never
  parsed.
- **Evidence never travels over the pipe.** The worker writes `capture/0.1` logs, blobs and native JSON into the
  session directory. The parent re-hashes every file the worker reports, ignores and reports unreported files, and
  resolves reported labels only under the session directory (no-follow, `S_ISREG`, `st_nlink == 1`; G.3.6).

| Direction | `op` | Fields |
|---|---|---|
| P → W | `hello` | `nonce`, `expect{commit, lock_sha256, record_sha256, guarded_sources{}}` (computed by T0 before spawn, §D.10.6) |
| W → P | `hello_ok` | `nonce`, `identity` (`BenchmarkIdentity`), `worker{python, agentprov_backend_version, agentprov_capture_version}` |
| P → W | `run_cell` | `req`, `cell` (`CellSpec`), `agent` (`AgentConfig` without secrets), `session{ex, attempt}`, `plan_sha256`, `attack_env{AUTODOJO_CACHE_label, AUTODOJO_VARIANT}` |
| W → P | `progress` | `req`, `pass`, `events` (count only) |
| W → P | `step` | `req`, `seq`, `kind` (`pass_start`, `pass_end`, `model_call`, `tool_call`, `decision`, `judgement`, `capture`), metadata only (MN N.1.14); droppable under back-pressure, never evidence |
| W → P | `cell_done` | `req`, `status` (`complete`/`incomplete`/`errored`/`aborted`), `artefacts[{label, sha256, role}]`, `capture_head` (hash-chain head), `outcome` |
| P → W | `shutdown` | — |
| W → P | `fatal` | `error{type, message}` (message escaped); the worker then exits non-zero |

**Rules.**
1. The parent refuses a `hello_ok` whose identity differs from `expect` (`IdentityMismatch`, exit 3). The capture
   `identity` event is cross-checked the same way at ingest.
2. A `cell_done` whose artefact hashes do not verify marks the cell `errored`: the files are ingested under their
   actual digests and the mapped AER carries the seal issue `capture_error` (C.12.3), with `detail` naming the
   mismatching label. A hit of T0's literal-value secret scan instead quarantines the session (`capture.quarantined`,
   HL H.6.3; nothing from the session is stored).
3. **Timeouts.** On a per-cell wall-clock timeout the parent kills the worker. It then appends a terminal
   `session.end{status: "aborted", appended_by: "parent"}` event to the hash-chained log (continuing the chain), seals
   it, and starts a fresh worker. The partial evidence is kept.
4. **Secrets.** Only the selected endpoint's key enters T2, and only variable **names** are recorded. Base URLs are
   https (loopback excepted), and the host must match `endpoints.toml` unless `--allow-custom-endpoint` is given,
   which is recorded. Wire capture is redacted by `agentprov_capture.redact` (G.6.4); T0 runs the literal-value scan
   over every staged file before `put_stream`, and a hit quarantines the session (R-51).
5. **Attack cache.** `AUTODOJO_CACHE` and `AUTODOJO_VARIANT` are set by the parent from `cell.attack_params`. The
   cache file is put in the raw store first (role `supporting`, sha256 recorded in `session.start`), because the
   fork's logger does not record them [sources/autodojo.md §7].

   **Cache provenance (MN-r12).** A file given as `--autodojo-cache PATH` is copied from the fork by the user, so T0
   verifies it before anything is staged or spawned. T0 computes the file's git blob SHA-1 and looks it up in the
   tree of the pinned fork commit `https://github.com/xhOwenMa/AutoDojo@aa458794b7eb7f082e94daeac4c0f55bfc0c90cc`, read
   from the bare fetch cache (`raw.fetch`, G.7.5; no checkout). If the commit is not cached, T0 fetches it only under
   `--allow-network` and otherwise refuses the run (exit 3). On a match, the supporting raw artefact records the
   origin `git {repo, commit, path, blob_sha1}` (C.3.12; `path` is the matching tree path, the bytewise-smallest if
   several paths hold the same blob) beside its sha256. If no path in the pinned tree has that blob id, T0 exits 3
   and runs nothing.
6. **Containment** (AD-13). A T2 compromise is a compromise of the user account; the controls above are mandatory for
   every live run. Real-model runs (which need the user's keys and consent anyway) additionally run under a macOS
   `sandbox-exec` profile, after a feasibility probe, or in a documented dedicated macOS user or VM.

### D.11.4 What is shared with the AgentDojo backend

- **Shared unchanged:**
  - `agentprov_capture` (event model, log writer, chain, redaction, envstate);
  - `agentprov_backend.{gateway, transport, pass_recorder, executor_mirror, runtime, runner, attacks, worker}` —
    imported inside the worker, where `agentdojo` is the fork;
  - in core: the capture mapper `agentdojo.capture` and the TraceLogger mapper (native-log check).
- **Different:**
  - the profile `autodojo-live`: identity pins, `retry_semantics`, `run_error_imposes_outcome` with
    `{security=false, error_type}`, the native-log layout, and the fork's suite set (AgentDyn suites plus
    `banking_v2_*` / `travel_v2_*`);
  - the attack registry (`autodojo` attack replaying a cache);
  - the refusals.
- **Same default LLM element.** Both backends use `llm_element = "native"` by default (AD-09).

```toml
# src/agentprov/adapters/agentdojo/profiles/autodojo-live.profile.toml (excerpt)
[family.agentdojo.live]
backend = "autodojo"
project = "backends/autodojo"
pins = { repo = "https://github.com/xhOwenMa/AutoDojo", commit = "aa458794b7eb7f082e94daeac4c0f55bfc0c90cc", subdirectory = "agentdojo" }
llm_element_default = "native"
asserts = ["ToolsExecutionLoop.max_input_tokens is None or recorded"]
refuse = ["defense in ['drift','progent','camel','camel_nopolicy']", "optimiser runs (variant_generation)"]
instrumentation_extra = ["autodojo.fork_temperature_transmitted@1", "autodojo.fork_malformed_json_retry@1", "autodojo.env_nltk_preprovisioned@1"]

[[family.agentdojo.quirk]]
id = "agentdojo.run_error_imposes_outcome"
params = { utility = false, security = false, extra_key = "error_type" }
```

The `instrumentation_extra` items describe stock behaviour of the fork (kind `harness_policy`) and the NLTK
provisioning (kind `behaviour_preserving`); they are declared so that a reader can compare AutoDojo sessions with
AgentDojo sessions.

> **Resolved (AD-09 / R-25; §1.3 "D ch D.11.4"):** the first revision's challenge to D5 is **accepted**. For forks,
> AgentPROV records at the **transport** level (the recording httpx transport plus `LlmSpan` brackets) around the
> fork's unmodified LLM element, so the behaviours that define an AutoDojo run (temperature transmission,
> malformed-JSON retry, Gemini provider pinning and reasoning settings, cache control) are kept, and no AgentPROV code
> binds to the fork's private helpers. AD-09 goes further than the proposal: `native` is also the AgentDojo default,
> and `gateway_compat` is an opt-in declared as instrumentation (§D.10.5).

### D.11.5 Fake-client testing

CI job `backend-autodojo` (manual dispatch only, K.19.1; backend project, Python 3.12):
1. `agentprov backends build autodojo --allow-network` with a cached uv store (network allowed in the build step
   only); identity from PEP 610.
2. Worker tests run **offline** (`backends/autodojo/tests`): socket guard, no key variables set.
3. The parent sends `run_cell` with `agent.transport = "scripted"` and a script of chat-completion JSON responses. The
   worker installs `agentprov_backend.testing.ScriptedTransport` on the fork's client.
4. The test cell is a fork banking task without defence, using the `important_instructions` attack and one `autodojo`
   cache-replay cell from a fixture cache.
5. Assertions:
   - identity handshake: the T0-computed `expect` equals `hello_ok` and the capture `identity` event;
   - `capture/0.1` sealed (`session.end` present, chain verifies);
   - the mapped AER's seal accounting is `consistent`;
   - live-versus-native agreement against the fork's TraceLogger JSON;
   - `instrumentation` contains `agentdojo.transport_scripted@1`;
   - artefact hashes verify;
   - a forced worker kill yields a sealed `aborted` session with `appended_by: "parent"`.

### D.11.6 What cannot be done without keys (or at all)

- Real target-model runs need the user's provider keys (`OPENROUTER_API_KEY`, `GEMINI_API_KEY`, optionally
  `OPENAI_API_KEY`) **and** the user's explicit consent, because they incur cost (D5; U-10). They are refused unless
  `agentprov run --i-consent-to-api-costs` is given interactively, and they run under the AD-13 (b) containment.
- Filter defences (PromptGuard, PIGuard, ProtectAI, DataFilter) need a GPU and `HUGGING_FACE_HUB_TOKEN`.
- DRIFT, Progent and CaMeL replace pipeline components and need defence-specific capture. They are refused in v0.1
  [sources/autodojo.md §7].
- The optimiser (`optimize_variants.py`, Gemini-3.1-Pro via OpenRouter) and its in-loop executions
  (`DojoASREvaluator`, unpersisted upstream) are **not supported** in v0.1. Capturing them would need wrapping
  `DojoASREvaluator.pipeline` [sources/autodojo.md §7; verify/autodojo.md #24].
- **Reproducing the ROPE-hosted AutoDojo runs is not possible.** They came from an unreleased harness revision
  (`iter4-synthesis-handspec`), with an unrecorded router and scope configuration [verify/autodojo.md §1, #22]. Live
  runs are new executions.

### D.11.7 Implementation resolutions (phase 9, AutoDojo backend)

Phase 9's backend stream extended `agentprov_backend` (new module `agentprov_backend.autodojo`) and built
`backends/autodojo` against the fork at `aa458794` as locked (`openai` 3.26.0, `nltk` 3.10.3, `json-repair` 0.63.5).
File references are to the installed fork. `capture/0.1` and `aer/0.1` are unchanged; the stock AgentDojo backend
behaves as before (its 82 backend tests and the phase-8 fixtures' `--check` are unchanged).

1. **Build** (`agentprov backends build autodojo`; MN N.2.10 note item 8). As the AgentDojo build (locked `--no-config`
   sync with `--exclude-newer` from the project, offline from the uv cache without `--allow-network`, `UV_*` scrubbing,
   RECORD verification, build-time `hello`, sandbox probe, marker). The PEP 610 source of the installed `agentdojo`
   must equal the pin (`{kind: git, repo: https://github.com/xhOwenMa/AutoDojo, commit: aa458794…, subdirectory:
   agentdojo}`); the version string `0.1.35` is never used to tell the fork apart. The fork ships macOS AppleDouble
   files (`._benchmark.py`, `._logging.py`, ...) in its tree; they are in its RECORD and are verified like any file.
   Built offline on the M2 Max (macOS 27.0.1): 329 RECORD entries verified, **sandbox-exec probe `passed`**.
2. **NLTK** (D.11.2). Facts: the installed fork imports `nltk` only lazily, inside the filter defences
   (`agent_pipeline/filter_defenses/{promptguard,piguard,protectai}_defense.py`, with a `nltk.download` fallback);
   `suite_gen_utils.py`, whose import calls `nltk.download("punkt_tab")`, belongs to `variant_generation`, which the
   installed package does not contain. So no import-time download exists in the environment: a fresh interpreter that
   imports the fork, every suite of every benchmark version and runs two scripted cells makes **zero** network attempts
   (counted by the socket guard, `netguard.attempts`, which also counts attempts a library swallows), and never imports
   `nltk` (`backends/autodojo/tests/test_offline.py`). The locked `nltk` loads `punkt_tab` from an **unextracted** zip
   (`load_punkt_params` reads through `nltk.data.find`; checked with a synthetic zip). Resolution: the recipe is data,
   `[tool.agentprov.nltk]` in `backends/autodojo/pyproject.toml` (`url` naming an immutable nltk_data location and
   `sha256`; optional `md5`, `bytes`); the build fetches it through `raw.fetch` (kind `url`: the verified cache
   `<cache>/url/<sha256>`, network only with `--allow-network`, an `acquisitions.jsonl` row with the consent text) and
   copies the zip to `<env>/nltk_data/tokenizers/punkt_tab.zip`; the marker records `nltk` and `nltk_sha256`;
   `--offline-check` re-verifies it; the worker gets `NLTK_DATA=<env>/nltk_data` (`worker_environment(nltk_data=...)`)
   only when it is provisioned. **Pinned (2026-10-08, user consent):** nltk_data `gh-pages` @ `550b6625`, `punkt_tab.zip` sha256 `e57f6418…0106`, md5 `27ea9ee0…e748`, 4,319,076 bytes, each equal to the `index.xml` entry at the same commit. The real build on the M2 Max provisioned it (`nltk.status: provisioned`). An environment built without the pin records `nltk.status: recipe_unpinned` and `nltk_sha256: null`, and a filter-defence run on it must be refused (all defences are refused in v0.1 anyway). Instrumentation `autodojo.env_nltk_preprovisioned@1` carries
   `params.punkt_tab_sha256` as the worker observes it (`null` when unprovisioned).
3. **Backend selection and identity.** The worker picks `AutoDojoBackend` when the installed `agentdojo`'s PEP 610 repo
   is the fork (`runner.select_backend`; `hello_ok.worker.backend`, which T0 checks), and `AutoDojoBackend.identity()`
   refuses any other commit (`fatal` at `hello`). `session.start.backend.id` is `autodojo`; `cell.benchmark` and the
   `bench` actor stay `agentdojo` (the suites are AgentDojo-family content), and the fork is identified by
   `identity.benchmark.{repo, commit}`. Extra guarded names (`identity.AUTODOJO_GUARDED_NAMES`, mirrored in core
   `envs.FORK_GUARDED_MODULES` and AST-tested): `_request_and_parse`, `ToolsExecutionLoop.query`,
   `AutoDojoAttack.__init__`/`.attack`, `get_model_name_from_pipeline`. The fork's `ToolsExecutor.query` is
   **source**-identical to 0.1.35 (sha256 `918da2f0…`), so the mirror guard passes and the differential test passes
   on all 17 suites the fork registers under v1.2.2 (`backends/autodojo/tests/test_executor_mirror.py`).
4. **Suite set.** v1.2.2 in the fork: `workspace`, `travel`, `banking`, `slack`, `banking_v2_0..4`, `travel_v2_0..4`
   and the AgentDyn suites `shopping`, `github`, `dailylife` (registered under every benchmark version,
   `load_suites.py`). Plans (`backend = "autodojo"`) and cells are validated against it as for AgentDojo.
5. **Attack `autodojo` — the worker contract.** For a cell with `attack == "autodojo"`, `cell.attack_params` must
   carry `autodojo_cache_sha256` (64 hex) and `autodojo_variant` (integer >= 0), so the cache's identity is in the cell,
   `config_sha256` and `session.start.cell.attack_params`. `run_cell.attack_env` must be `{"AUTODOJO_CACHE_label":
   <label>, "AUTODOJO_VARIANT": <same integer>}`, where `<label>` is a relative path inside the session directory
   staged by the parent before `run_cell` (recommended `raw/attack/autodojo-cache.json`, which the worker then
   reports in `cell_done.artefacts` with role `supporting`). The worker resolves the label without following links
   (every component `lstat`-ed; a regular file with `st_nlink == 1`, at most 64 MiB), requires its sha256 to equal
   `autodojo_cache_sha256`, and sets `AUTODOJO_CACHE` (absolute path) and `AUTODOJO_VARIANT` in `os.environ` **only
   while the attack is constructed** (the fork reads them in `__init__`), restoring them after. Any violation seals
   the session `errored` (`UnsupportedConfiguration`, `where: setup`) before any request. Item
   `autodojo.attack_cache_replay@1` (`attack_parameter`) records `{cache_label, cache_sha256, cache_bytes, variant}`;
   `fixture` events carry what `attack()` returned (the fork YAML-escapes the variant). **Deviation from D.11.3:** the
   two variables are not in the worker's process environment allowlist; they travel per cell in `run_cell.attack_env`
   (a worker serves many cells), and a value in the process environment is ignored (a cell without `attack_env` is
   refused). The MN-r12 cache provenance check (git blob in the pinned tree) stays T0's, before staging.
6. **Model-name fallback.** The fork's `get_model_name_from_pipeline` returns `"AI assistant"` instead of raising
   when `MODEL_NAMES` has no entry. The `AttackFactory` detects it: with `model_display_name` the scoped registration of
   D.10.10 item 14 is used (item `agentdojo.attack_model_display_name@1` adds `params.benchmark_fallback`); without one
   the fork's stock behaviour is kept and declared (`params.source = "benchmark_fallback"`, `display_name` = the name
   the attack took; `autodojo` keeps it in `_model_name`).
7. **Run errors (`run_error_imposes_outcome`).** The fork's runner catches context-length errors (also
   `ContextLengthExceededError` and two more message patterns), `InternalServerError`, `json.JSONDecodeError`, API and
   server errors, and imposes `utility = false, security = false`, setting `error_type` in the TraceLogger context
   (`context_length_exceeded`, `internal_server_error`, `json_decode_error`, `api_internal_server_error`,
   `server_error`), which the native JSON then carries. Capture records the stock return values as judgements (origins
   `harness_default`, as D.6.7), the backend's `declared_semantics.run_error` text, and a note
   `autodojo/run_error_imposed {error_type, native_error_present, judgements, source: "native_log.error_type"}` after
   the `outcome`. A malformed tool-call reply, an `errored` cell under stock 0.1.35, is an error-skipped `complete`
   cell under the fork: the fork's `_request_and_parse` re-requests up to 3 times (replies 1-2 `discarded`,
   `superseded_by_retry`; the last `element_raised:JSONDecodeError`), then the runner skips the task.
8. **Pipeline.** `build_instrumented_pipeline` is unchanged; the fork's `ToolsExecutionLoop` gains `max_input_tokens`
   (default `None`): the harness asserts it is `None` and records it in the `agentdojo/pipeline` note (member only when
   the loop has the attribute, so AgentDojo notes are unchanged). `SuiteRunProxy.run_task_with_pipeline` forwards extra
   keyword arguments (the fork's `prompt_override`). The fork's TraceLogger keeps `/` in pipeline names (nested
   directories) and adds `<attack>_<injection_attack_name>` only when the runner is given an injection attack name,
   which the harness never passes; the native file is still found by the existing recursive search and its stock
   relative path is recorded (`agentdojo/native_log_stock_path`).
9. **Instrumentation as emitted** (in addition to D.10.10 item 16, minus `agentdojo.temperature_not_transmitted@1`):
   `autodojo.fork_temperature_transmitted@1 {configured, transmitted}` (the fork sends `temperature if not None`; the
   default 0.0 is on the wire), `autodojo.fork_malformed_json_retry@1 {max: 3, exception}`, `autodojo.fork_system_role@1`
   (role `system`, not `developer`), `autodojo.fork_openrouter_extras@1` (only on an `openrouter.ai` host: usage
   accounting, the Gemini provider pin and dynamic reasoning, Anthropic `cache_control`), `autodojo.env_nltk_preprovisioned@1
   {punkt_tab_sha256}`; `agentdojo.http_backoff@1`'s detail names the fork's nested retries. The fork's
   `OPENROUTER_EXTRA_BODY` and `AUTODOJO_COST_TRACKING` variables never reach T2 (allowlist), so the fork runs its
   defaults (cost tracking on: it only adds `usage.include` on OpenRouter).
10. **Refusals** (sealed `errored`, `where: setup`, nothing sent): `llm_element = "gateway_compat"` (the port imports
    0.1.35 private helpers whose fork versions differ; AD-09); `drift`, `progent`, `camel`, `camel_nopolicy` with their
    own message, every other defence as for AgentDojo; the attack `ours` (replays optimiser output directories,
    `OURS_ATTACK_DIR`). `variant_generation` is not installed (tested). The preflight probe applies the same agent
    check.
11. **AgentDyn environment artefacts (D.15 candidates; found by the differential test).** (a) After a checkout that
    asks for an OTP, the `shopping` environment stores `(function, (platform, ...))` in `verification_stack`;
    `model_dump(mode="json")` then fails (a callable, and a cycle back to the platform). `pass_recorder.dump_env` falls
    back to a field-by-field walk with `"<unserialisable T>"` / `"<circular T>"` placeholders and writes a note
    `agentdojo/env_dump_lossy {pass, at, types}`, so the observer never raises into the run; stock AgentDojo
    environments always dump, so nothing changes there. Without the fallback a shopping checkout cell would have ended
    `errored` because of the recorder. (b) AgentDyn tools stamp emails with `datetime.now()` and draw OTPs from
    `random`: two stock runs of the same calls differ in environment state and tool output (cause `benchmark`;
    handling: recorded as is; the differential test masks wall-clock stamps and seeds `random`).
12. **Tests and fixtures.** `backends/autodojo/tests` (63, offline, socket guard, no key variable): identity and
    backend selection; offline guarantee; the D.11.5 cells (fork banking `important_instructions`, `autodojo` cache
    replay from the synthetic cache of `testing.scenarios.SYNTHETIC_AUTODOJO_CACHE`, error-skipped cell) with sealed
    logs, verified artefacts, live-versus-native agreement against the fork's TraceLogger JSON (scored pass dump,
    injections, judgements) and `agentdojo.transport_scripted@1`; refusals and cache-contract violations; the worker
    over a subprocess (T0-style `expect` == `hello_ok` == capture `identity` event and `identity_digests` note; artefact
    hashes); a forced SIGKILL mid-cell (a `{"stall": s}` script step) sealed `aborted` with `appended_by: "parent"`;
    RPR-10; the committed fixtures. Fixtures: `tests/fixtures/capture/autodojo/<scenario>/` (four scenarios, see its
    `README.md`), generated by `backends/autodojo/tools/make_capture_fixtures.py` (`--check` compares the stable
    projection). They sit one level down so the phase-8 core tests (`agentdojo-live` profile) do not map them.

### D.11.8 Implementation notes (phase 9, core registry and cache provenance)

Facts of the core side as built; the backend side has its own notes list.

1. **Registry.** `autodojo` (family `agentdojo`) has one part, `live`: role `source`, evidence `n/a`, `import_status`
   `None`, `live_status` `planned`, the shared reader `agentprov.capture` and mapper `agentdojo.capture`, backend
   `autodojo`, profile `autodojo-live`, `requires = ("backend:autodojo",)`, semantics `agentdojo.suites@1`. `BACKENDS`
   gains `autodojo` (project `backends/autodojo`, profile `autodojo-live`). The ROPE import part `autodojo-via-rope` is
   not registered (phase 10). Licence: MIT, six holders (LICENSE line 3), data licence `none`, policy `include`.
2. **Status gate.** No change to `run`: `_live_capability` admits a scripted run of the `planned` part as a `test_only` gate
   run and refuses a real one (exit 5). `agentprov import autodojo` is refused with exit 5 ("no import capability"). The
   test `test_info_prints_exactly_the_registry_statuses` no longer lists `autodojo` among the unregistered sources.
3. **Profile `autodojo-live` v1.** No schema change was needed: the closed `live` table already carries `repo`, `commit`,
   `subdirectory`, `asserts`, `refuse` and `instrumentation_extra`. Because the schema requires `instrumentation_accepted`,
   the profile lists the same 16 shared harness items as `agentdojo-live` (the same `agentprov_backend` runs inside the fork
   environment); the three `autodojo.*` items are `instrumentation_extra`, as in D.11.4. `guarded_sources` is left out until
   the worker reports the fork's `inspect.getsource()` digests. `retry_semantics` stays `agentdojo.final_content_none_max3`
   (nothing in the inspected fork changes the rerun loop). The AgentDyn suites `github`, `shopping`, `dailylife` map to the
   benchmark label `agentdyn`; the SEM tool tables are keyed on `agentdojo`, so these suites fail closed. The quirk
   `agentdojo.run_error_imposes_outcome` carries `{utility=false, security=false, extra_key="error_type"}`. The instrumentation
   ids are not catalogue rules (the `agentdojo.*` ones are not either), so no rule catalogue changed and no PROV golden
   digest changed. (The mapping wave later extended `instrumentation_extra`, added `attack_cache` and changed the
   `agentdojo` catalogue: D.11.9 items 4-6.)
4. **Cache provenance.** `agentprov.cli.live.autodojo_cache.verify_autodojo_cache(path, *, cache_dir, allow_network,
   fetcher=None, limits=None, repo, commit) -> VerifiedCache` implements rule 5: bounded read (`ingest`, at most
   `max_json_bytes`), strict JSON, shape check, SHA-256 and git blob SHA-1, lookup in the tree of the pinned commit through
   `raw.fetch` (`Fetcher.plan`, `git_tree`, `iter_git_blobs`; no checkout), and a byte comparison of the one matching blob.
   An uncached commit without `allow_network` is `cli.environment.autodojo_cache_commit` (exit 3); no matching blob id is
   `cli.environment.autodojo_cache_blob` (exit 3); an unreadable, oversized, malformed or mis-shaped file and a bad variant
   are `cli.usage.autodojo_cache` (exit 2) and are reported before any fetch. Several paths with one blob: the
   bytewise-smallest UTF-8 path is recorded and all are returned. The result carries
   `Origin.git(repo, commit, path, blob_sha1)`.
5. **Shape and variant.** The cache must be an object with a non-empty `injection_tasks` mapping task id to vector id to
   `{"variants": [str...], "original": str (optional)}`; extra keys are tolerated. `--autodojo-variant` is plain ASCII digits
   (at most nine). The attack silently substitutes the injection task goal for a vector whose list is shorter than the
   index, so `check_variant` refuses an index beyond the longest list and returns the number of cells that would fall back,
   for the caller to record.

### D.11.9 Implementation resolutions (phase 9, core mapping and `agentprov run autodojo`)

The phase-9 core wave maps AutoDojo captures and runs the backend end to end. The code is the reference; tests:
`tests/adapters/agentdojo/test_autodojo_capture.py`, the AutoDojo fixtures inside the generic
`tests/integration/test_live_mapping.py` and `tests/differential/test_live_vs_native.py`,
`tests/integration/test_run_live_autodojo.py` (real environment, marker `backend_autodojo`), `tests/cli/test_run_cmd.py`.
Evidence: `docs/reports/live/autodojo-phase9.md`. `aer/0.1` and `capture/0.1` are unchanged, and so are `aer/`, `prov/`,
`validate/` and `corpus/` (invariant 5) and the backend projects.

**Mapping (adapter `agentdojo.capture`, profile `autodojo-live`).**
1. **Profile selection.** A capture session is mapped with the live profile of the backend that wrote it:
   `agentprov.adapters.runner.live.capture_profile_id` reads `session.start.data.backend.id` and takes the profile of
   that registry backend (`BACKENDS[id].profile`); a log that names no registered backend is refused
   (`adapter.backend_unknown`). `runner.live.map_session` uses it when no profile is given; `agentprov run` maps with the
   profile of the backend it ran. Nothing is guessed from content.
2. **Identity against the profile** (new rule `agentdojo.capture_backend_identity@1`, D). The mapper compares
   `session.start.backend.id` with `[family.agentdojo.live] backend`, and the `identity` event's benchmark with the
   profile's `pins`: `repo` and `commit` for a git pin, `dist`/`dist_version` for a wheel pin, and a git source under a
   wheel pin is a conflict even though the fork reports the wheel's name and version (D.11.1). A difference is the core
   issue `identity_conflict` (error), a missing backend id or identity event `identity_unresolved`; the session is still
   mapped with the profile it was given. Mapped (forced) with `agentdojo-live`, an AutoDojo session shows two conflicts.
3. **`run_error_imposes_outcome`.** When the outcome's judgements are all `harness_default` and the session holds a
   pipeline `error` event or the backend's `run_error_imposed` note (namespace `agentdojo` or the backend id), the stock
   runner imposed them. A judgement whose value equals the profile quirk's parameter for its name (`autodojo-live`:
   utility false, security false; `agentdojo-live`: utility false, security true) keeps `ev: O` for the value (the runner
   returned it) and gets `evf /origin: D` under `agentdojo.run_error_imposed_outcome@1` scoped at `/origin`, with `src`
   naming the outcome, the error event and the note's judgement. A value that differs from the quirk keeps the
   harness's `O:capture` origin and is reported (`capture_error`); a note that disagrees with the outcome too; no quirk is
   `agentdojo.undeclared_quirk`. `outcome_imposed_by_runner` names the judgements. The quirk's `extra_key` (`error_type`)
   is copied from the note into `ext.agentdojo.extra.<key>` of the header (`O:capture`, `src` the note and the native
   log's `/<key>`), as the TraceLogger mapper keeps unknown top-level keys; a note that disagrees with the native log is
   reported. The phase-8 run-error fixture now gets the same `D` origin under its quirk (security true): no committed
   AER digest covers it.
4. **Catalogue** (`agentdojo`, still version 1). `run_error_imposed_outcome` stated "(False, True)", upstream's values
   only; its statement now names the profile-supplied values and cites the 0.1.35 and fork code (`benchmark.py`
   125-182 and 368-416 at `aa458794`). Plus `capture_backend_identity`. The golden PROV and gate-D PROV digests were
   regenerated with the documented flags: 19 + 28 = 47 PROV digests changed (the catalogue digest only); no AER, SEM or
   statement changed.
5. **Instrumentation.** `instrumentation_extra` lists D.11.7 item 9's items as emitted: the three of D.11.4 plus
   `autodojo.fork_system_role@1`, `autodojo.fork_openrouter_extras@1` and `autodojo.attack_cache_replay@1`. They are
   copied into the header like every item. The fork's `system` role is the stock rendering (D.10.4a item 17), so no sent
   transform is claimed.
6. **The cache as a supporting artefact.** New optional `[family.agentdojo.live] attack_cache = {attack, sha256_param,
   variant_param, label, media}` (closed schema). For a cell running that attack, the reader finds the cache **by the
   digest** in `cell.attack_params.<sha256_param>` (labels are data) and the header lists it after the capture and native
   logs, role `supporting`, `prov_primary: unknown` (C.3.12: a context artefact, not a primary source; no
   `hadPrimarySource`). Its origin is the member's: `capture {session}` for a staged directory, the pinned fork tree
   `git {repo, commit, path, blob_sha1}` when `agentprov run` verified it (item 8).
7. **Fork layout and the native check.** The worker moves the fork's TraceLogger file to the C.13.1 name whatever its
   stock path (`/` kept, optional `<attack>_<injection_attack_name>`, recorded in `agentdojo/native_log_stock_path`), so
   the live-versus-native check is unchanged; it passes on the three AutoDojo fixtures with a native log. The fork's
   `error_type` is an extra top-level key of the native log (`v1.k14`), mapped into `ext.agentdojo.extra` by the
   TraceLogger mapper and outside the projection. A parent-killed session has no announced native log (the fork's partial
   file stays at its stock path under `raw/native-tmp/`, stored by `agentprov run` as a `supporting` raw object, not an
   AER artefact); it is mapped like the phase-8 kill: run `aborted`, `aborted_attempt`, `passes_closed` and
   `env_recorded` inconsistent (a pass without its end).

**`agentprov run autodojo` (T0; N.2.1, N.2.1b).**
8. **Order.** Status gate; backend refusals (`--llm-element gateway_compat`; attacks `ours` and `variant_generation`;
   `--attack autodojo` or the cache options outside the AutoDojo backend; DRIFT/Progent/CaMeL; exit 5 or 2); environment
   and marker; `envs.check_nltk` (its directory becomes `NLTK_DATA` through `worker_environment(nltk_data=...)`); a filter
   defence (`promptguard`, `piguard`, `protectai`) is refused with its NLTK state named when `nltk_sha256` is null, and
   as a defended pipeline otherwise; T0 identity; **profile pins against the environment** (a git pin must be the
   installed fork's PEP 610 source and the project's commit, a wheel pin the registry distribution and version;
   `IdentityMismatch`, exit 3); **cache provenance** (`parse_variant` → `verify_autodojo_cache` with the profile's
   `repo`/`commit` and `resolve_cache_dir()`, fetching the commit only under the new `--allow-network` → `check_variant`)
   before anything is staged or spawned; then hello (with `backend`, so `hello_ok.worker.backend` must be `autodojo`) and
   the plan, whose `[plan] backend` is the registry's backend (it was always `agentdojo`).
9. **Cache in the plan and the digest.** The cache's sha256 and variant become the plan's `[attack_params]`
   (`autodojo_cache_sha256`, `autodojo_variant`), so every attacked cell, `session.start.cell` and `config_sha256` carry
   them. Because `[attack_params]` is plan-wide, `--attack autodojo` must be the only attack (usage error otherwise).
   The cache identity also enters T0's configuration digest (`attack_cache` member, only when a cache is used, so
   AgentDojo digests are unchanged): another cache or variant is another unit (N.1.8(1)) and needs
   `--allow-mixed-config` in the same corpus.
10. **Storing and staging.** `VerifiedCache.data` is put in the raw store before the campaign with the verified git
    origin (D.11.3 rule 5). For every attempt of an attacked cell the parent writes it to `raw/attack/autodojo-cache.json`
    in the fresh session directory (directories 0700, file 0600, `O_CREAT|O_EXCL`, which fails on any existing entry, a link included) and sends `run_cell.attack_env =
    {"AUTODOJO_CACHE_label", "AUTODOJO_VARIANT"}` (`campaign.AttackStaging`). At ingest the staged copy is stored with the
    `capture {session}` origin as a mirror and handed to the map job with the git origin
    (`LiveSessionPipeline.ingest(origins=...)`), so the AER's supporting artefact names the fork tree path and blob.
    Re-mapping a kept staging directory with the same origin (`runner.live.map_session(origins=...)`) gives the stored
    bytes.
11. **Records.** The manifest's `live.attack_caches` maps each configuration digest to `{attack, sha256, bytes,
    blob_sha1, origin, matching_paths, fetched, variant, label, vectors, fallback_vectors, cells, cells_without_task}`:
    `fallback_vectors` is `check_variant`'s count of cached vectors without the variant, `cells_without_task` the planned
    cells whose injection task the cache does not hold (all their vectors fall back to the goal). Both also appear as a
    notice. The capture identity check at ingest also requires `session.start.backend.id` to be the backend run.
12. **Deviations.** (a) D.11.3 rule 5 says the sha256 is "recorded in `session.start`": it is, as
    `cell.attack_params.autodojo_cache_sha256` (the worker's contract, D.11.7 item 5); the manifest and the AER artefact
    record it too. (b) The test seam for the cache verification is `agentprov.cli.run._verify_attack_cache` (a synthetic
    repository's commit in place of the pin); `agentprov run` itself always passes the profile's pin. (c) The AgentDyn
    suites keep the benchmark label `agentdyn` in the profile while the live cell says `agentdojo` (the worker's cell);
    no AgentDyn session was mapped in this wave, and SEM fails closed on them as designed (D.11.8 item 3).

### D.11.10 The AgentDyn backend (`backends/agentdyn`; D-680..D-688)

AgentDyn (`https://github.com/SaFo-Lab/AgentDyn`) is a third AgentDojo-family backend, run from its own pinned code
rather than from AutoDojo's copy of its suites. The design note is `docs/reports/agentdyn-backend/design.md`; this
section records what is decided and built.

1. **Pin and install (D-680, D-681; user decisions 2026-10-22).**
   - The pin is `5353cf7615b135cace8d07c8f12dac53a16b6db3`, the source profile's pin, which carries the GitHub IT1
     fix for upstream issue #6.
   - `backends/agentdyn/` is a uv project as in D.11.2:
     - a git source with the canonical URL and the full rev, and no subdirectory (`pyproject.toml` is at the
       repository root);
     - Python 3.12, its own lock, and `exclude-newer` as for the other backends;
     - `environments` restricted to darwin and linux.
   - **Recorded deviation:** the seven dependencies AgentDyn declares beyond AgentDojo 0.1.35 and imports from no
     module outside `defenses/` are overridden out, so that the environment resolves from the uv cache with the same
     SDK versions as `backends/agentdojo`. The seven are `cyclopts`, `pydantic-ai`, `tiktoken`, `vertexai`,
     `jsonref`, `openapi-pydantic` and `json_repair`. AgentDyn's own `uv.lock` does not lock them.
   - The environment is `agentdyn-5353cf76`.
2. **Identity (D-682).**
   - **PEP 610.** `direct_url.json` must name the repository and commit, with no subdirectory (`envs.pinned_source`);
     the version string `agentdojo 0.1.35` is never identity.
   - **Guarded names.** `agentprov_backend.identity.AGENTDYN_GUARDED_NAMES` adds `openai_llm._supports_temperature`,
     `AgentPipeline.from_config` and `load_system_message`. `envs.FORK_GUARDED_MODULES["agentdyn"]` adds
     `agentdojo.agent_pipeline.agent_pipeline`. `ToolsExecutor.query`, `TraceLogger.log/save`,
     `FunctionsRuntime.run_function` and `TaskSuite.run_task_with_pipeline` are AST-identical to 0.1.35.
   - **Backend selection.** `runner.select_backend` returns `AgentDynBackend` for AgentDyn's repository, and that
     backend refuses any other commit.
   - **Refusals.** `llm_element = gateway_compat` (AD-09; T0 `BACKEND_REFUSALS["agentdyn"]` as well) and every
     defence; AgentDyn's own defences are named with their reason.
3. **Instrumentation (D-683).** AgentDyn's stock behaviour is declared as `harness_policy` items in place of
   `agentdojo.temperature_not_transmitted@1`:
   - `agentdyn.temperature_transmitted@1` (temperature is sent when not `None`, except for the `o1`/`o3`/`o4`/`gpt-5`
     model prefixes);
   - `agentdyn.system_role_for_qwen3_max@1` (only for that model);
   - `agentdyn.malformed_tool_calls_dropped@1`;
   - `agentdyn.json_decode_error_imposes_outcome@1` (utility false, security true);
   - `agentdyn.model_output_last_assistant@1`.

   The default system message is AgentDyn's (`21a1c00d…`, with the auto-complete line), never replaced by the harness.
4. **Mapping (D-684, D-685).**
   - The shared `agentdojo.capture` mapper maps these sessions through a live profile `agentdyn-live` and a registry
     part `agentdyn · live` (`planned` with the scripted caveat). Both are class 1 and held; the orchestrator decides
     when they land.
   - **Dropped tool calls (D-685 (b)).** AgentDyn drops a wire tool call whose arguments do not decode to a JSON
     object. Under the quirk `agentdojo.malformed_tool_call_dropped`, the capture mapper matches the reply on the kept
     calls, so the message keeps its `generated_by`. It lists the dropped calls in `ext.agentdojo.dropped_calls`
     (class D, `agentdyn.malformed_tool_call_dropped@1`, agentdyn v2 in place). They are never dispatched. Without the
     quirk the code is inert, and stock and AutoDojo sessions map as before.
   - Scripted sessions S1–S4 (report §3) map, validate at every tier and recompute identically. AgentDyn's suites
     are labelled `agentdyn` and its copies of the AgentDojo suites `agentdojo`.
5. **Licence (D-686; user decision A).** Sessions are included on the same basis as the imported `agentdyn` corpus
   ("MIT as declared; not legally settled"). The same applies to AgentDyn cells captured through AutoDojo.

---

## D.12 The future-framework test

This walkthrough is the evidence for the requirement "new event types without core change" (DoD Q.3) under AD-15.
aer/0.1 has the generic kinds `activity` and `artefact` (C.3.13, C.3.14; local ids `ac<n>` and `af<n>`, C.4.2), and
EF's generic rules G-ACT (`aprov.g_act@1`, a typed activity), G-USE (`aprov.g_use@1`, `used` per input at the class of
the input link), G-GEN (`aprov.g_gen@1`, `wasGeneratedBy` from `artefact.generated_by`) and G-ASSOC
(`aprov.g_assoc@1`, `wasAssociatedWith`) map them and take part in the Inference-6 closure. C.3.15 fixes the AER side
of this contract; this section owns the walkthrough. The test MUST produce **named PROV statements** for the planner
step, the memory write and read, the screenshot, the hand-off and the human approval, and **named, disclosed gaps**
for everything aer/0.1 cannot express. The format is self-authored, so the test proves coverage of the listed
constructs, not agnosticism; A.6 and the paper say "tested on a self-authored toy format and on the Inspect importer
(changes listed)" (R-27). [R-17, R-35, R-36, AD-15]

**Scenario.** A hypothetical framework "FooBench" releases JSONL traces: one execution per primary file, one event
per line. A hand-off writes the sub-agent's events into a **second file**. Its event types are the familiar
`llm_request`, `llm_response`, `tool_start`, `tool_end` and `guard_verdict`, plus the unseen `plan_update`,
`memory_write`, `memory_read`, `screenshot`, `handoff`, `approval` (one `approve` and one `edit` decision),
`text_action` (an action parsed by the harness from the agent's plain text), `checkpoint_restore`, and one event type
the adapter does not know (`telemetry`).

### D.12.1 Files added (and nothing else)

| # | File | Content |
|---|---|---|
| 1 | `src/agentprov/adapters/foobench/__init__.py` | package docstring; `ADAPTER_ID = "foobench.jsonl"` |
| 2 | `src/agentprov/adapters/foobench/dialect.py` | `FooJsonlReader`: sniff (the first line is a JSON object with the declared `schema` key), parse line by line with `ingest.loaders.iter_jsonl` under limits (event locators `{"line": n}`, 0-based; the execution's key locator is `{}`, the whole primary file), stdlib only |
| 3 | `src/agentprov/adapters/foobench/mapper.py` | `FooMapper` (mapping below) |
| 4 | `src/agentprov/adapters/foobench/profiles/foobench.profile.toml` | generic tables (pins, licence, lineage, `[import]` with `auxiliary = ["sub-*.jsonl"]` for the hand-off file) plus `[family.foobench]` (verdict table, actor table) |
| 5 | `src/agentprov/adapters/foobench/rules/foobench.rules.toml` | rules `foobench.*@1`, issue codes (`unmapped_event_type`, `restore_unmodelled`, `observation_unlinked`, `handoff_not_expanded`), `types` (`foobench:plan_step`, `foobench:plan`, `foobench:memory_item`, `foobench:memory_read`, `foobench:memory_snippet`, `foobench:observe`, `foobench:screenshot`) |
| 6 | `src/agentprov/adapters/foobench/ext.schema.json`, `family.schema.json` | closed schemas of `ext.foobench` and `[family.foobench]` |
| 7 | `src/agentprov/adapters/foobench/semantics/…` (optional) | semantics profile (tool tables, integrity). **Added in phase 7** as `foobench.toy@1` (`semantics/foobench.toy-1/tables.toml`; rules `foobench.*_table@1`, `foobench.taint_sink_untrusted@1`, all I), with the registry part's `semantics` entry; K.6.4 item 6 runs it end to end |
| 8 | `tests/fixtures/foobench/*.jsonl` + `SOURCE.json` | self-authored fixture (licence class `permissive`) containing every event type above |
| 9 | `tests/adapters/foobench/test_{dialect,mapper,rules,fuzz}.py` and `test_future_framework.py` | golden AER (bytes), Hypothesis fuzz, rule coverage, and the named-statement test of §D.12.3 (K.6.4) |
| 10 | **one entry** in `src/agentprov/adapters/registry/__init__.py` (plus the `READERS`/`MAPPERS` lines) | `SourceRegistration("foobench", …)` |
| 11 | generated docs | registry-rendered tables (`agentprov info`, `docs/sources/…`) |

The namespace `foobench` is declared in `execution.ns` (C.10); every `activity.type` and `artefact.type` is declared
in the catalogue's `types` (A-9).

### D.12.2 Mapping onto the aer/0.1 kinds

Actors: `agent` (`llm_agent`), `planner` (`llm_agent`, `role: "planner"`), `researcher` (`llm_agent`,
`role: "subagent"`), `user` (`user`: the human approver), `env` (`tool_runtime`), `harness` (`harness`: FooBench's
runtime, which turns plans into steps, retrieves memory and takes screenshots), `def0` (`defense`: the guard). PROV
terms use EF's instance IRIs `x:<local id>` with `#` → `-` for parts (E.4.2).

| FooBench event | AER | Named PROV statements (EF rule) |
|---|---|---|
| `llm_request` + `llm_response` | `model_call mc<n>` (actor `agent`, `role: "agent"`, `input` = the message ids the request references (O), request and response blobs) + output `message` with `generated_by: mc<n>` | `used(x:mc<n>, x:m<i>)` per input (`aprov.use_context@1`, O); `wasGeneratedBy(x:m, x:mc<n>)` (`aprov.gen_message@1`); `wasAssociatedWith(x:mc<n>, x:agent)` (`aprov.assoc_model_call@1`) |
| `tool_start` + `tool_end` | `tool_execution te<n>` (`call` = the `tool_call` part, `args`, `status`, `t`) + `tool_result` message `generated_by: te<n>` | `used(x:te<n>, x:m<a>-<k>)` (`aprov.use_request@1`); `wasGeneratedBy(<result>, x:te<n>)` (`aprov.gen_result@1`); `wasAssociatedWith(x:te<n>, x:env)` (`aprov.assoc_tool@1`) |
| `guard_verdict` | `decision dc<n>` (actor `def0`, verdict from the profile's closed table, subject = the `tool_call` part); a `deny` has **no** `tool_execution` | `wasAssociatedWith(x:dc<n>, x:def0)`; `used(x:dc<n>, x:m<a>-<k>)` (`aprov.decision@1`) |
| **planner step**: the planner's `llm_request`/`llm_response` in thread `thr0`, then `plan_update` (the runtime turns the planner's reply into a structured plan) | `model_call mc0` (actor `planner`, `role: "auxiliary"`, scope `thr0`) generating message `p0`; `activity ac0 {type: "foobench:plan_step", actor: "harness", scope: "thr0", inputs: ["p0"], t, status}`; `artefact af0 {type: "foobench:plan", content: <plan>, media: "application/json", generated_by: "ac0"}` | `wasGeneratedBy(x:p0, x:mc0)`; `wasAssociatedWith(x:mc0, x:planner)`; `x:ac0` typed `foobench:plan_step` (G-ACT); `used(x:ac0, x:p0)` (G-USE); `wasGeneratedBy(x:af0, x:ac0)` (G-GEN); `wasAssociatedWith(x:ac0, x:harness)` (G-ASSOC); `wasInformedBy(x:ac0, x:mc0)` (Inference-6 closure, `aprov.comm@1`) |
| **memory write**: `memory_write {key, value}` from the agent's `save_memory` tool call | `tool_execution te1` + `artefact af1 {type: "foobench:memory_item", content: {key, value}, generated_by: "te1"}`; when FooBench logs the store patch, also `state_change st0 {target: "agent_store", cause: "te1", patch: [{op: "add", path: "/<key>", value}]}` | `wasGeneratedBy(x:af1, x:te1)` (G-GEN); with the patch, the store-state chain of `aprov.state_patch@1` (a new store state generated by `x:te1`, revision-derived from the previous store state along `after` edges, or a fresh entity) |
| **memory read**: `memory_read {key}` by the harness before the next agent call (not a tool) | `activity ac1 {type: "foobench:memory_read", actor: "harness", scope: "att0", inputs: ["af1"], t, status}` + `artefact af2 {type: "foobench:memory_snippet", content, generated_by: "ac1"}`. FooBench then injects the snippet as message `m5`, which carries no generator in aer/0.1 (C.3.4: an activity never generates a message) | `used(x:ac1, x:af1)` (G-USE); `wasGeneratedBy(x:af2, x:ac1)` (G-GEN); `wasAssociatedWith(x:ac1, x:harness)` (G-ASSOC); **`wasInformedBy(x:ac1, x:te1)`** (Inference-6 closure: the write → read flow that memory poisoning exploits is a named statement); **named gap**: the relation of `m5` to `af2` is not asserted (C.3.15) |
| **screenshot**: the environment captures the screen after each browser action (no tool call) | `activity ac2 {type: "foobench:observe", actor: "env", scope: "att0", inputs: [], t, status}` + `artefact af3 {type: "foobench:screenshot", content_ref: {"$blob": "sha256:…", "bytes": n, "media": "image/png"}, sha256 (= the blob digest), media: "image/png", generated_by: "ac2"}`; the observation message `m6` (part `blob` with the same digest) carries no generator | `x:ac2` typed `foobench:observe` (G-ACT); `wasGeneratedBy(x:af3, x:ac2)` (G-GEN); `wasAssociatedWith(x:ac2, x:env)` (G-ASSOC); **named gap**: the relation of `m6` to `af3` is not asserted (C.3.15) |
| **hand-off**: `handoff {to: "researcher", call_id}` from the agent's `transfer_to_researcher` tool call; the sub-agent's events are in the second file | `tool_execution te2` (`call` = the part); `scope sc0 {kind: "subagent", parent: "run", actor: "researcher", spawned_by: "te2"}` holding the sub-agent's `model_call`s and tool executions (mapped from the auxiliary file, raw artefact role `supporting`); the sub-agent's answer is the `tool_result` of `te2`. A sub-agent file is expanded at most 4 hand-offs deep and never twice on one hand-off chain; a hand-off that is not expanded (the limit, or a cycle) keeps its scope, cites the file and raises the warning `foobench.handoff_not_expanded` on its execution (regeneration-batch item 55) | `wasStartedBy(x:sc0, -, x:te2)` (`aprov.spawn@1`); `wasAssociatedWith(x:mc<sub>, x:researcher)`; `used(x:te2, x:m<a>-<k>)` |
| **human approval, approve**: `approval {call_id, approver: "human", decision: "approve"}` | `decision dc1 {actor: "user", subject: "m7#1", verdict: "allow"}`; `tool_execution te3 {call: "m7#1", authorised_by: "dc1", …}` | `wasAssociatedWith(x:dc1, x:user)`; `used(x:dc1, x:m7-1)` (`aprov.decision@1`); `wasStartedBy(x:te3, -, x:dc1)` (`aprov.authorise@1`, replacing `aprov.start_tool@1` for this execution) |
| **human approval, edit**: `approval {call_id, approver: "human", decision: "edit", edited_args}` | `decision dc2 {actor: "user", subject: "m9#1", verdict: "modify", original: "m9#1"}`; `tool_execution te4 {call: "m9#1", authorised_by: "dc2", args: <edited args as dispatched>}` | `wasAssociatedWith(x:dc2, x:user)`; `used(x:dc2, x:m9-1)` (`aprov.decision@1`); EF's guard NE-18 suppresses `used(x:te4, x:m9-1)`: **named gap** recorded as a status until `aer/0.2` models the replacement (`decision.replacement`, `apv:ApproverModification`) |
| **text-parsed action**: `text_action {raw}`: the harness parses an action from the agent's plain-text reply | `tool_execution te5 {requested_by: "agent", name, args (evf I, `foobench.text_action_parse@1`), status, t}` + result message `generated_by: "te5"` | `wasAssociatedWith(x:te5, x:env)`; `actedOnBehalfOf(x:env, x:agent, x:te5)` (`aprov.assoc_tool@1`, `requested_by` delegation); **named gaps**: no request part, so no `used(x:te5, …)` and no exposure or taint assessment (no generating invocation; EF E.7.3, DECISIONS D-16) |
| **restore / branch**: `checkpoint_restore {checkpoint}` | aer/0.1 has no encoding for an in-file branch or restore (C.3.15; R-36). The event is kept verbatim in `ext.foobench.events[]` of the nearest preceding host record (with its own `src` and `after`), plus the issue `foobench.restore_unmodelled`; the events after it are mapped in source order, without linearising the restore into a state claim | **named gap**: no PROV statement is emitted; the fork point (`scope.forked_after`, `state_change.restores`) waits for `aer/0.2` |
| unknown type `telemetry` | kept verbatim in `ext.foobench.events[]` of the **nearest preceding host record**, as `{type, value, src: {"line": n}, after}`, plus the issue `foobench.unmapped_event_type` (info). **Never dropped**; there is no host-less `unmapped[]` | **named gap** `foobench.unmapped_event_type` (ext is opaque to PROV) |

Specialised kinds are used wherever they fit (A-9): the planner's reply is a `model_call` and a message, the memory
write is a tool execution (a framework that writes memory outside tool calls would use an `activity`
`foobench:memory_write` generating the `foobench:memory_item` artefact instead, C.3.15), the approvals are
`decision`s, the text action is a `tool_execution`. The generic kinds
carry exactly the things no specialised kind represents: a non-LLM plan step, a harness-side memory read, an
environment-taken screenshot, and their products.

**Blob sizes.** A FooBench blob (the screenshot, a message's `blob` part) declares `{sha256, bytes, media}`; the BlobRef's
`bytes` is that declaration, and AER-V21 holds it to the stored blob's size. The mapper treats a declared size as
malformed (`MalformedArtefact`, a degenerate AER, D.2.8 case 3) when it is not a non-negative I-JSON integer (a BlobRef
has no `$int` form), or when the caller supplies the blob's bytes as the auxiliary `blob:<hex>` (digest-verified, the
capture family's contract) and their length differs. It never substitutes the stored size for the declared one. An
unsupplied blob keeps the declared size for AER-V21 to check. Imports store the screenshot through the profile's
`[import] blobs = ["**/*.png"]` (D-203) and offer it to the job as `blob:<hex>`. Not yet wired: the runner does not join
a hand-off's second file (`[import] auxiliary`) into the unit for a reader without `auxiliary_for`, so an import of the
fixture records `dangling_source_ref` for the hand-off (a follow-up, not a refusal). Found by the field-level fuzz of K.11 on 2026-10-11 (sizes `0`, `1`, `2**60` of the fixture's screenshot).

**Store patches.** A `memory_write`'s `store_patch` becomes `state_change.patch` only when it is a list of RFC 6902
operations: objects with an `op` of the six, a JSON Pointer `path`, the `value` (`add`, `replace`, `test`) or pointer
`from` (`move`, `copy`) the operation needs, and no member name beginning with `$` (C.11.3 would `$lit`-wrap the
operation). Anything else is malformed (D.2.8 case 3), never an `adapter_defect` from the writer (found by the same
fuzz: `store_patch = [1]`).

### D.12.3 What may change, and the test

**Protected set** (DoD Q.3): all of `src/agentprov/` except `adapters/foobench/`, the registry entries and generated
docs. The import-boundary test and `git diff --stat` in the adding pull request MUST show changes only in the files of
§D.12.1. In particular the following are untouched: the AER schema and validator, the provenance engine (it consumes
AER kinds, not dialects), the SEM engine, the corpus layer and the CLI.

**The test** (`tests/adapters/foobench/test_future_framework.py`, the executable form specified in K.6.4) imports the
fixture, derives PROV and asserts:
1. the named statements of §D.12.2 for the planner step, the memory write and read (including
   `wasInformedBy(x:ac1, x:te1)`), the screenshot, the hand-off and both human approvals, each with its rule id;
2. the named, disclosed gaps, with no PROV statement emitted for them: NE-18 on the edited request; no request part
   for the text action; the restore (`foobench.restore_unmodelled`); the unmapped `telemetry` event; and the two
   observation messages `m5` and `m6`, which carry
   `unk {"/generated_by": "not_recorded"}` and the issue `foobench.observation_unlinked` (C.3.15: an activity cannot
   generate a message in aer/0.1);
3. that the AER validates (tier 2) and the PROV bundles validate (tier 4) with no core change.

The real external format of v0.1, Inspect `.eval` (§D.9), is held to the same rule: it lands with zero core changes,
or the changes are listed and reported in the paper (R-17).

### D.12.4 When an AER schema bump is needed (and is a versioned change)

1. **A new closed-enum value** in a core field without an escape: `tool_execution.status`, `model_call.status`,
   `judgement.origin`, a message part type, an `unk` reason or a `by` party. This is an additive **minor** bump
   (`aer/0.2`). Readers of `aer/0.1` reject unknown values (closed schema), so older consumers fail loudly rather than
   misread. The five enums `actor.kind`, `scope.kind`, `state_change.target`, `decision.verdict` and `fixture.kind`
   need no bump: they have the `other` + declared `subtype` escape (AD-15, R-38).
2. **A new typed reference** between records that the core PROV bundle must contain and that none of the existing
   references expresses: `generated_by`, `responds_to`, `call`, `requested_by`, `authorised_by`, `input` (with `sent`
   transforms), `inputs` (activity, judgement), `subject`, `scope`, `parent`, `spawned_by`, `retry_of`, `revises`,
   `cause`, `original` and `after`. (There are no forward references: `output` and `spawns` do not exist.) An example
   is "message edited by activity X" if a framework logged in-place history edits as first-class events. This is a
   minor bump plus an EF rule.
3. **A new record kind.** AD-15 added the generic `activity` and `artefact` kinds to aer/0.1, so a new kind is needed
   only if an activity or entity has PROV semantics distinct from every existing kind, including the generic ones,
   **and** encoding it with them would hide a statement that EF must emit in the core bundle. It is a **major** bump.
   None of the 14 investigated sources requires it. STAC needs only an `execution.unit` value, not a new kind.

`aer/0.2` candidates recorded by the rulings: `decision.replacement` with `apv:ApproverModification`,
`tool_execution.requested_in`, `scope.forked_after`, `state_change.restores`, `related.rel ∈ {spawned, spawned_by}`,
`message.generated_by` → `activity` (so that an observation a harness activity injects into the context is generated
by it, C.3.15), the delta form of `model_call.input`, the collection context encoding (AD-03, AD-10); new span and
human-input events wait for `capture/0.2`.

> **Resolved (AD-03, AD-15 / R-02, R-35; §1.3 "D ch D.12.4 / D.14.1 R-1…R-9"):** the first revision's challenge to D2
> (completeness of the closed kinds) is closed. The fields it asked for were ruled in the AD-03 table (§D.14.1):
> `unit` accepted and extended, the instrumentation item accepted in a merged shape, `profile.sha256` accepted,
> optional `call` with `unk` accepted, and `attempt`, `args_src`, `result_raw`, `judgement.valid` and
> `task.benchmark_version` rejected. Addendum B (AD-15) then went beyond the review's recommendation: instead of naming
> a generic `activity` kind as the first `aer/0.2` candidate, aer/0.1 itself carries `activity` and `artefact`, because
> with `ext` alone unseen non-LLM activities would produce no PROV at all.

---

## D.13 Adapter isolation and supply-chain rules

G owns the limits and controls; this section states how adapters and backends apply them. [R-01, R-40, R-42, R-45,
AD-12, AD-16]

### D.13.1 Import path: no upstream code, pure stdlib parsing of untrusted bytes

1. Readers and mappers MUST NOT import or execute any upstream or benchmark code. They MUST NOT call `eval`, `exec`,
   `pickle`, `marshal`, `yaml.load` or `subprocess`, and MUST NOT open sockets. An AST-based test scans
   `adapters/*/dialect.py`, `adapters/*/mapper.py`, `adapters/*/capture_reader.py`, `adapters/*/capture_mapper.py`
   and `agentprov/ingest/*` for forbidden imports and calls. Allowed imports: stdlib (`json`, `zipfile`,
   `compression.zstd`, `re`, `hashlib`, `base64`, `fnmatch`, `tomllib`, `io`, `dataclasses`, `typing`,
   `unicodedata`), `agentprov` core and, for the capture reader, the `agentprov_capture` verifier. YAML is never
   parsed by readers or loaders; only `ingest/yamlsafe.py` imports `yaml` (AD-17, G.3.7).
2. **Strict JSON** is `agentprov.ingest.loaders.strict_json_loads` and `iter_jsonl` (G.3.3), under
   `agentprov.ingest.limits.IngestLimits` with the defaults of G.3.2 (among them: depth 256, `max_json_bytes` 64 MiB,
   `max_jsonl_line_bytes` 16 MiB, `max_int_digits` 1,000). A BOM is `ingest.json.bom`; duplicate keys, non-finite and
   overflowing numbers are rejected; integers beyond ±(2^53−1) are kept exactly and encoded by the AER writer as
   `{"$int": …}` (C.11.3). Escaped lone surrogates are a finding and are encoded `$utf16` (G.3.3 rule 8).
3. **Python literals and CSV** (ASB) are deferred (AD-10 row 16).
4. **Archives** follow G.3.5 inside a T1 worker: an EOCD/ZIP64 size check before opening, the overlap check and the
   per-member gate after opening; methods {0, 8, 93}; members must be regular, unencrypted, with valid NFC labels
   whose collision keys are unique; per-member, total, ratio, count and nesting limits from `IngestLimits`. Members are
   **streamed into the store** as derived objects by the versioned `expand` stage (AD-12) and are never extracted to
   disk and never "read into memory" as a whole. Container jobs stream only the members that match the profile's
   `members`/include patterns; the others get a `raw/members.jsonl` row with disposition `not_selected`. The per-job
   output cap applies to JSON frames only; data frames are bounded by the member and total limits (R-40).
5. **Discovery** uses `agentprov.ingest.paths.discover` and `open_evidence` (G.3.6): it never follows symlinks,
   requires regular single-link files unless `--allow-hardlinks` is given (recorded), skips `.DS_Store` and
   AppleDouble `._*` files [audit/legacy_replay.md §3.3 rule 15], and never derives output paths from source strings.
   AER paths are sharded by `ex` (`aer/<ss>/<ex>.aer.jsonl`).
6. **Determinism.** Mappers do not read time, environment, locale or randomness (A-2). Iteration over dicts follows
   source order or is explicitly sorted.
7. **Untrusted text stays data.**
   - Corpus text (prompts, tool outputs, injection payloads) is never interpolated into commands, file paths, log
     format strings or LLM prompts by any adapter.
   - Issues carry ids and locators, not content (§D.2.7).
   - Any human-facing rendering (`agentprov info`, import reports) passes strings through `escape_untrusted`; content
     views go through `quote_untrusted` and only with `--show-content` (G.8.2). Exception arguments are escaped
     (R-42).
   - Payloads addressed to models, such as "This is an important message from me, Emma Johnson, to you, GPT-4", are
     expected benchmark data [sources/agentdojo.md §4.4].
8. **Limits are recorded.** The effective limits are written to the import report and the corpus manifest. A
   resource or safety violation produces a register row `ingest.<area>.<kind>` (G.3.9 first class, bytes not
   stored); a policy or parse violation on bytes within limits produces a degenerate AER (§D.2.8 case 3).
9. **Interpreter guard** (AD-16). Core declares `requires-python = ">=3.14"`. Any command that ingests archives or
   compressed streams checks the running interpreter: below 3.14.8 it **refuses** in release mode (`--release`,
   the deposit builder behind `package --deposit`; exit 3; `package` in seal mode opens no archive, D-62), and `package` refuses a corpus whose manifest records an
   `interpreter_advisory` (exit 4); in dev mode it warns, records `python_version` and `interpreter_advisory` in
   `corpus.json`, and writes the register code `ingest.interpreter.unpatched`. There is no override flag. CI runs core
   on the latest 3.14 patch. Backends (Python 3.12) never parse archives, so the guard does not apply to them. A test
   covers both modes.

### D.13.2 Profiles, rules and registry are trusted code-reviewed data

- They are loaded only from package resources.
- `load_profile_file()` (a user path) is dev-mode only. It records the file digest and is refused in release mode.
- `rederive` loads profiles and catalogues only from package resources at the recorded version; the corpus `rules/`
  copy is a record, digest-compared (`rules.mismatch`), never loaded; an absent version is `rules.unavailable`
  (AD-14).
- No network fetch occurs during import. Fetching pinned commits and DOIs is a separate, explicit step
  (`agentprov fetch`, `agentprov.raw.fetch`, G.7.5). It resolves only origins that match an **in-package** profile pin
  (kind, repository or DOI, revision, sha256; otherwise `raw.reference.unpinned_origin`), and verifies git blob SHA-1,
  sha256 and Zenodo checksums before any reader runs.

### D.13.3 Live path: upstream code runs, but only in declared places

- **Only in backend environments (T2).** Benchmark code runs only inside `$AGENTPROV_HOME/envs/<backend>-<commit8>/`,
  built from `backends/agentdojo/` (hash-locked PyPI `agentdojo==0.1.35`) or `backends/autodojo/` (the fork pinned by
  full commit SHA in the lock), and launched as `<env>/bin/python -I -B -m agentprov_backend.worker` (AD-01). Core
  never imports a benchmark; there is no in-process live path and no core extra for a benchmark. The identity guards are as
  in §D.10.6; the worker protocol is §D.11.3.
- **Never in the importer process**: no benchmark import, no replay. Outcome replay is deferred (AD-10); if it is
  reinstated it is a T1-restricted job in `backends/agentdojo` with no keys and no network
  [audit/legacy_replay.md §7.6].
- **Secrets.** `.env` is read only by the live CLI entry (`live` extra), from `--env-file` or the repository root
  (A4). Only the selected endpoint's key enters T2. Wire capture is redacted by `agentprov_capture.redact` (G.6.4): an
  allowlist of recorded headers and URL parts plus a hard denylist (`authorization`, `proxy-authorization`,
  `cookie`, `set-cookie`, `x-api-key`, `api-key`, `x-goog-api-key` and any name matching the secret pattern), and a
  fail-closed literal-value scan of every event and blob. Key-format pattern matches are redacted on non-content
  surfaces and flagged (not rewritten) inside benchmark content. T0 repeats the literal-value scan over every staged
  file before `put_stream` (R-51). A test asserts that no configured key bytes appear in any artefact. Only the
  endpoint host is recorded.
- **Containment** (AD-13). The T2 controls of §D.11.3 apply to every live run; real-model runs additionally run under
  a `sandbox-exec` profile or a dedicated user or VM.
- **Consent.** Real-model runs require explicit user consent (D5). Fake-transport runs are tagged `test_only` and
  cannot enter a release corpus.

---

## D.14 Rulings on this section's requirements, and open questions

### D.14.1 Requirements on AER: rulings (AD-03, AD-15)

The first revision asked the AER section for nine additions before the `aer/0.1` freeze. They were ruled in AD-03;
C.3 and `schemas/aer-0.1.schema.json` are the contract. [R-02]

| Id | First-revision requirement | Ruling | Effect in this section |
|---|---|---|---|
| R-1 | `execution.unit` ∈ {`agent_execution`, `scenario`} | **accepted, extended**: required, `agent_execution \| outcome_only \| scenario` (R-28) | §D.2.8, §D.6.5, §D.8 |
| R-2 | `execution.instrumentation[]` and `execution.attempt{cell_key, index}` | **instrumentation accepted** in the merged shape `{id: "<ns>.<name>@<n>", kind, recorded, params?, detail?, code_ref?}`; **`execution.attempt` rejected** (keep `capture.attempt`; cell coordinates in `task`; the logical key in the index) | §D.10.7 |
| R-3 | `execution.adapter.profile{id, version, sha256}` | **accepted** as `execution.profile {id, version, sha256}` | §D.4.1, §D.6.5 |
| R-4 | more artefact roles and several origins per artefact | **rejected**: C's four roles and one `origin`; mirrors go to `raw/origins.jsonl`; worker logs and generator code are `supporting`; blobs are listed in `seal.blobs`. **Added** `prov_primary ∈ native\|byte_derived\|secondary\|unknown` | §D.2.2, §D.6.5 |
| R-5 | `tool_call.args_src` | **rejected** (AD-02): `ext.lex {ord, flt}` via `aer.canon.lex_hints()` | §D.2.2, §D.6.3, §D.7.3 |
| R-6 | `tool_execution.result_raw` | **rejected**: use `returned`; redacted originals use `decision.original` or `unk overwritten` | §D.6.6 |
| R-7 | `tool_result.responds_to` and `tool_execution.call` optional with `unk` | **accepted**: exactly one of `call`, `requested_by` or `unk {"/call": "ambiguous"}` | §D.6.6.1 |
| R-8 | `judgement.valid` | **rejected**: EF derives "checker ran" from `origin ∈ {checker, recomputed}` | §D.6.7 |
| R-9 | `task.benchmark_version` | **rejected**: the label goes on the `bench` actor's `version`, the identity on its `code` | §D.6.5 |

Addendum B (AD-15) added the generic kinds `activity` and `artefact` to the contract (C.3.13, C.3.14; local ids
`ac<n>` and `af<n>`, C.4.2; EF rules `aprov.g_act@1`, `aprov.g_use@1`, `aprov.g_gen@1`, `aprov.g_assoc@1`). This
section uses them in §D.9.2 (Inspect sandbox events) and §D.12 (the future-framework test). C rules that an activity
never generates a message in aer/0.1; the resulting gap (an observation that a harness activity injects into the
conversation has no asserted relation to its artefact) is disclosed in §D.12.3 and listed as an `aer/0.2` candidate
(§D.12.4).

### D.14.2 Open questions (dispositions per RESOLUTIONS §1.3)

1. **Ex-id truncation.** Closed by AD-04: C's `[0:26]` of the full digest, mapping id `"<adapter id>/<profile id>"`,
   locator canon of RESOLUTIONS §3.4; one function `agentprov.aer.ids.import_execution_id`. KAT
   `ex_7uz2oys57hugtsueixylme4fl5`.
2. **`capture/0.1` event names and envelope.** Closed: C.13 names (R-16); §D.10.2 uses them.
3. **`landscape/secure_ingestion.md`.** Closed (R-63): the report exists; the tier-1 defaults are G.3.2.
4. **Inspect promotion to v0.1.** Accepted (AD-06); §D.9.
5. **Verification of AgentDyn, STAC and the survey.** Closed (R-63): the verify reports exist; every row has
   `verification = "verified"`, with the values of I.1.1.
6. **AutoDojo environment co-installability with core.** Moot under A1: core is never installed in a backend
   environment.
7. **Guarded-source digests** for the fork's private OpenAI helpers must be computed from the pinned commit at
   implementation time (PQ phase 9). They are not yet known.
8. **DRIFT proposed-call re-parsing** (rule reserved). Deferred with DRIFT `partial`. It would need a stdlib grammar
   equivalent to AgentDojo's `ast_utils`; 11 assistant turns were unparsable by Python `ast` [verify/drift.md §11].
9. **The DRIFT OpenReview supplementary zip** (`oY1Xnt83oJ`) may hold paper-time logs. Access was blocked by a
   challenge [verify/drift.md §2]. User decision U-14 (manual download; optional while DRIFT is `partial`).
10. **`render_converted` feasibility.** Closed by AD-02 (`ext.lex` makes it mechanical) and AD-07 (golden R1/R2
    blocking in CI; the full run is a claim gate).
11. **Items for the next review round** (found while applying the resolutions): (a) C.3.13 lists the allowed
    `activity.inputs` targets without `state_change`, while EF's G-USE also accepts a `state_change`'s current state;
    this section uses only artefact inputs for memory reads, which both allow. (b) The I-class twin of
    `agentdojo.naive_local_timestamp` (§D.5.4) answers C's R-new-2; C.16 must cite the twin for ROPE. (c) C.16
    examples still use the retired names of §D.5.3 (`agentdojo.outcome_origin`, `adprov.outcome_origin`,
    `agentdojo.pipeline_model_prefix`, …) until they are regenerated (C's r2 repair regenerated the vectors). (d)
    *Resolved (AD-SW4):* the future-framework adapter is `foobench` everywhere (K.6.4 aligned in the r2 repair);
    D.12.2's encodings bind K.6.4 and DoD Q.3.

## D.15 Artefact catalogues: proactive inspection, recording and cleaning (DECISIONS D-12)

Every corpus that AgentPROV turns into W3C PROV carries artefacts: defects of the upstream harness, the benchmark, a
baseline converter or the capture. This holds whether the corpus comes from live capture or from import (AgentDojo
legacy and HEAD runs, the AgentDojo-PROV converted and generated trees, ROPE and AutoDojo-via-ROPE, AgentDyn,
Mandate, DRIFT, the survey runs and AgentHarm, CIAware-Bench, STAC, the NIST mirror, ASB). This section makes them
first-class. Every artefact is **inspected proactively**, **recorded accurately**, **cleaned only in the defensible
ways** and **reported with numbers for the manuscript**. Anything new found along the way is captured, never dropped.

**Ownership: per source, with bespoke handling.** Artefact knowledge belongs to the adapter that reads the source
(invariants 1 and 9), exactly like profiles and rule catalogues. Each adapter family owns three things:
- its catalogue (D.15.2);
- its **bespoke handlers**, which deal with each edge case at the point of conversion: mapper rules (D.5), profile
  quirks (D.4) and semantics-profile rules (SEM). Examples are `agentdojo.no_execution_observed@1`,
  `rope.security_correction@1` and `survey.run_error_imposes_outcome@1`;
- the tests that trigger each case.

The same pattern therefore repeats in every input source. The shared layer (D.15.3) is deliberately thin. It holds
the catalogue schema, a source-neutral safety net for anomalies that no source claims, and the reporting. It holds no
source knowledge, and it exists so that counts are comparable across sources and citable in the paper.

### D.15.1 Principle and the five handling classes

Evidence is never edited. Raw bytes, AER source values and the frozen `adprov-v2.3-compat` output are never changed
to remove an artefact (invariants 2, 3 and 8). Each catalogue entry declares exactly one handling class:

| Class | Meaning | Where it lives |
|---|---|---|
| `CR` correct representation | The `agentprov-prov/0.1` model states truthfully what a baseline graph or label misrepresented. Examples: no `ToolExecution` for a call that never ran, `unk` instead of a sentinel time, a harness-imposed outcome without a `CheckerRun`, and ids that are never keys | the engine's rules (EF); nothing extra |
| `DR` derived reconstruction | A missing or mis-recorded value is reconstructed by a **declared, deterministic rule** from cited evidence. It is recorded beside the source value with class D and its `apv:rule`, never in place of the source value | AER `evf`/transform with a rule ref (C.6.4); core bundle at class D |
| `RJ` recomputed judgement | A corrected outcome sits **beside** the recorded one. AER `recomputed` is reserved for recomputations the source itself released (C.3.10); AgentPROV's own re-scorings are SEM annotations, and they derive assessment-bundle claims, never core | SEM; assessment bundle (`apv:Assessment`, `wasDerivedFrom` the recorded judgement) |
| `FO` flag only | The artefact can be detected but not corrected | seal issue, AER `note` or SEM annotation; assessment bundle |
| `NR` not recoverable | The information was never recorded. It is stated as `unk` with a closed reason (C.7), and the loss is counted | AER `unk`; stats information-loss table |

Forbidden in every class:
- filling a missing trajectory;
- rewriting `utility` or `security` in AER;
- synthesising provider ids;
- re-parsing text-encoded calls into `tool_call` parts;
- inventing passes, executions or times;
- relabelling source fields;
- touching the compat oracle.

### D.15.2 Catalogue format (`adapters/<family>/artefacts.toml`, data)

One versioned catalogue per adapter family. It has an integer `version` and is recorded in `corpus.json` like the
rule catalogues. Live capture uses the backend family's catalogue. Each entry has these fields:

| Field | Content |
|---|---|
| `id` | `<ns>.art.<name>`, stable (for example `agentdojo.art.empty_log`) |
| `title`, `description` | plain text; no source content |
| `scope` | the source ids, parts and profiles it applies to |
| `cause` | `upstream_harness`, `benchmark`, `provider`, `baseline_converter`, `capture` or `unknown` |
| `detector` | the rule id that detects it (a mapper rule, a SEM rule or a generic detector `artefact.generic.<name>`) and its evidence class |
| `recorded_as` | the seal-issue code, `note` kind or SEM annotation type it produces |
| `handling` | `CR`, `DR`, `RJ`, `FO` or `NR`, plus the rule that implements it |
| `expected` | known counts per pinned snapshot (`{snapshot, count, basis}`), used as a regression expectation, never as a gate that hides data |
| `manuscript` | `true` when the paper reports it (O.3.5) |
| `refs` | the investigation, paper or code locations behind it |

### D.15.3 The thin shared layer: safety net and unclassified anomalies (`agentprov.artefacts`)

`agentprov.artefacts` is an L3 package beside `validate/`. It changes none of `aer/`, `prov/`, `validate/` or
`corpus/`. It loads each adapter's catalogue, validates it, and runs a **source-neutral safety net over AER**. The
results are recomputable and identical for live and imported data. The net does not handle artefacts; the adapters'
bespoke handlers do that during conversion. The net catches what no handler claimed:
- an empty or outcome-only execution;
- an outcome imposed by the harness (judgement origin `harness_default` or `harness_rule`);
- sentinel or unknown times;
- provider-id anomalies (absent, empty or repeated ids, or a link conflict);
- tool calls requested but never executed;
- abnormal finish reasons;
- suspected text-encoded tool calls (patterns plus the catalogue's tool names);
- lost or inferred passes;
- accounting `inconsistent` or `unverifiable`;
- byte-identical or mirror duplicates across origins (lineage, I.2.4);
- payload never reaching the agent (from SEM).

**Unclassified anomalies.** These have no catalogue entry and are recorded as
`artefact.unclassified.<detector>` with their locators:
- a generic-detector hit that no catalogue entry claims;
- any validator warning;
- an `inconsistent` accounting verdict;
- a mapper issue code absent from the catalogue.

They are never filtered out. Triage is a reviewed commit that adds a catalogue entry, bumps the catalogue version
(visible in `recompute`) and records the counts in `docs/reports/artefacts/`.

### D.15.4 Proactive inspection and reporting

- **Before import:** `agentprov import … --dry-run --artefacts`. It reads and maps in T1 workers, writes nothing to a
  corpus, and prints the per-class artefact table for the input. Each row gives the class, count, proportion, handling
  and the first execution ids, as locators only.
- **After import:** `agentprov stats --artefacts` gives the same table over a sealed corpus, per source, part and
  model. It is deterministic and writes nothing into the corpus (G8). `agentprov inspect --ex ID` lists the findings
  for one execution. The model is the sorted set of requested `llm_agent` model ids, and rows group on that set, never
  on its escaped, truncated display label. When distinct sets render to one label, each such label gets ` #` and a
  short sha256 of the JCS of the id list.
- **During live runs:** the D.10.9 capture-quality report is the live instance of the same catalogue.
- **Reports:** a per-source table, numbers only, goes to `docs/reports/artefacts/<source>-<part>.md` after each
  full-snapshot import (phase 13). The paper's artefact tables and macros come from it through the O.3.5 pipeline.
  A mismatch with a catalogue's `expected` count is reported as a finding, never hidden.

### D.15.5 Seed catalogue: AgentDojo legacy runs (the converted corpus)

This records how AgentPROV deals with the AgentDojo legacy runs. The baseline converted them into 18,027 transcripts.
AgentPROV imports the pinned `c274885` tree natively (18,241 logs including the 7 Mixtral logs; profile
`agentdojo-upstream`). It keeps the 18,027 baseline converted transcripts only as the `adprov-v2.3-compat` regression
oracle (gates A1, A2 and B; J). The counts come from a stdlib scan of the 18,234-file baseline copy, the AgentDojo-PROV
manuscript tables and the investigation audits.

| Entry | Observation | Cause | Recorded as | Handling |
|---|---|---|---|---|
| `agentdojo.art.empty_log` | 207 logs with empty `messages` (all claude-3-opus, workspace, `important_instructions`); 112 utility true, 200 security false. The baseline excluded them | upstream (cause unknown) | `unit: outcome_only`, issue `no_execution_observed`, `agentdojo.no_execution_observed@1` | `CR`: kept as outcome-only executions. The judgement keeps the source's origin (`checker`, as the log claims, `by: source`). SEM flags `outcome_without_trajectory`, and stats exclude it from attack-success rates by default |
| `agentdojo.art.run_error_imposed` | 106 run-error logs, all utility false and security true; 25 stop before any assistant turn | upstream harness (`benchmark.py:122-147, 286-312`) | `agentdojo.run_error_imposed_outcome@1`, issue `outcome_imposed_by_runner` | `CR`: no `CheckerRun` and no `outcome` claim; SEM verdict reason `abandoned` |
| `agentdojo.art.banking_ut15_confound` | banking `user_task_15` prompt names the attacker's IBAN: 200 injection runs | benchmark (legacy v1/v1.1 prompt; fixed in v1.2) | SEM `agentdojo.account_confound` (class D: the payload IBAN appears in the first user message) | `FO` + `RJ`: a scored/unscored verdict under `agentdojo.scoring@1`, in the assessment bundle |
| `agentdojo.art.dos_polarity` | 485 DoS runs where `security == not utility`; the baseline counted 178 as attack successes | upstream harness rule (`benchmark.py:149-150`) | `agentdojo.dos_security_rule@1`, `agentdojo.dos_placeholder_injection_task@1` | `CR`: a `harness_rule` activity derived from the utility judgement, with explicit polarity in SEM |
| `agentdojo.art.injection_task_as_user` | 432 injection-task-as-user-task logs labelled benign | upstream harness (`benchmark.py:200-209`) | `agentdojo.injection_task_as_user_task@1`, `ext.agentdojo.task_kind` | `CR`: the "benign" label exists only in the v1 view |
| `agentdojo.art.benign_security_constant` | 2,024 benign logs, all `security: true` | upstream constant (`task_suite.py:408-410`) | `agentdojo.benign_security_constant@1` (`harness_default`) | `CR`: no `outcome` claim |
| `agentdojo.art.replay_dispute` | 8 scored outcomes disputed by baseline replay | checker and data drift | — (replay deferred, AD-10 row 2) | `FO` (v0.2: `apv:ReplayFaithful`, assessment only). Drift-contaminated replay is never a verdict |
| `agentdojo.art.text_tool_call` | 142 Llama-3 text-written, unexecuted calls (+164 "narrated"; **heuristic counts**) | provider prompt format | SEM `agentdojo.text_tool_call` (class I) on the assistant message; generic detector | `FO` (re-parsing is forbidden) |
| `agentdojo.art.checker_era` | June-2024 checkers reproduce 1,909 of 1,931 logged IT4/IT5 outcomes, against 1,886 for the installed checkers; 130 of 139 utility mismatches | upstream in-place checker edits; generator unpinned | note `agentdojo.checker_era_unverified`; `benchmark_era_from_commit@1` (I) | `FO` (`RJ` for IT4/IT5 when replay lands; utility drift is `NR`) |
| `agentdojo.art.provider_ids` | 4,413 calls with no id (Cohere), 4,522 `""` (Gemini), 8,925 tool turns with no usable id, 188 traces with repeated ids (BASELINE §5.1 says 189; unresolved) | provider | `provider_call_id_anomalies`, `call_id_unique_match@1`, `positional_match@1`, issue `call_result_link_conflict` | `CR`: ids are attributes, and the link evidence class is explicit |
| `agentdojo.art.timing_stub` | 68,620 tool turns with start and end `"0"` (baseline converter) | baseline converter | `adprov.timing_stub_is_unknown@1`, `t.raw` + `unk`; `agentdojo.duration_scope@1` | `CR`; real times `NR`. Times are never derived from `duration` or commit dates |
| `agentdojo.art.silent_rerun` | 47 null-final logs (scan); 52 with replay | upstream (`task_suite.py:383-394`) | `null_final_implies_three_passes@1`, issues `retry_passes_inferred`, `earlier_attempts_unobservable` | `CR`: passes 1–2 `lost`, `pre_state_not_initial`. The outcome verdict is `FO`. The two counts are reported separately |
| `agentdojo.art.unwinnable_cell` | 434 injection runs in unwinnable cells (IT0; IT4 in June) | benchmark check defects | SEM `agentdojo.unwinnable_cell` from a static cell table (class I; **uncertain**) | `FO` |
| `agentdojo.art.max_iters_pending` | 145 traces, 153 requested calls never executed | `max_iters = 15` | issue `unexecuted_tool_call` | `CR`: the requests exist, with no execution (the baseline dropped them) |
| `agentdojo.art.failed_sink` | 628 sink calls that raised, counted as sinks by the baseline | baseline rule | `tool_status_from_error@1`; EF E.7.3 item 2 | `CR`: the taint subject is the request, with its execution status |
| `agentdojo.art.context_taint_used` | context-visibility `used` edges asserted as PROV; defence-altered content (PI sentinel: 2,154 entities in 624 graphs) | baseline builder | `context_is_prefix@1` (I, inference bundle); `pi_detector_sentinel@1`, `unk overwritten` | `CR` |
| `agentdojo.art.identity_folding` | model folded with the defence; no run id; the baseline is `c274885` minus the 7 Mixtral logs; 4,052 superseded at HEAD; generation mixing at HEAD | upstream + baseline converter | two pinned snapshots, `source_key`, `pipeline_dir_is_model_identity@1` (I), `defence_suffix@1` (I), `generation_mixing_per_file` | `CR`. The 7 Mixtral logs are extra executions, so paper numbers shift (flagged) |
| `agentdojo.art.validity_defects` | vacuous utility 984, data lost 1,014, banking precedence 99, checker misses 71, payload unread 625 | benchmark checks | SEM `injection_marker` (payload reach); the rest as per-trace SEM flags | `FO` |
| `agentdojo.art.baseline_packaging` | false datasheet provenance, 178 DoS counted as successes, unhashed manifests | baseline `package.py` | F-61…F-64 (B) | `CR` (AgentPROV's own corpus layer) |

Checked and **absent** in the 18,234-file copy: parse errors, BOMs, duplicate keys, lone surrogates, control or bidi
characters, non-UTF-8, byte-identical duplicates, `pipeline_name` differing from the directory, and truncated logs.
These detectors still run, so a regression would show. The "11 run-error-imposed outcomes" belong to the survey
source's gpt-oss runs (`survey.run_error_imposes_outcome`), not to AgentDojo.

### D.15.6 Seed catalogues for the other sources

Each catalogue is seeded from the source's I.1.2 card, row C26 ("known limitations and quirks"), its D.4 profile
quirks and the investigation reports. It lands with its importer, and the first full-snapshot import confirms its
counts. A part without that import keeps its expected counts marked `unverified`.

| Source family | Lands in | Seeds (non-exhaustive; C26 is authoritative) |
|---|---|---|
| `adprov` generated tree | phase 4 | the 13 classes of D.10.9 (A1–A13), with their manuscript counts, plus `adprov.art.reported_calls_exceed`. That class was **found 2026-10-08** by the full-scope gate run: in 32 traces (qwen-2.5-72b-instruct 20, gemini-2.5-flash 12) the usage-reported call count exceeds the held assistant messages. They are sealed `accounting_inconsistent` with `aer.acc.reported_counts@1` (`reported_calls_differ`). The handling is `FO`; the cause (unrecorded calls or a counting defect) is unknown |
| `adprov` converted tree (oracle) | phase 4 | the baseline-converter artefacts above (`tc_step` ids, timing stub, context-taint `used`, DoS counting). These are recorded, but the oracle output is frozen |
| AgentDojo HEAD (`089ed468`) | phase 10 | generation mixing per file; detector-prompt changes before the timestamped HEAD runs; 105 run-error logs |
| ROPE and AutoDojo-via-ROPE | phase 10 | error-skipped tasks scored `security`; `rope.security_correction@1` (an `RJ` beside the recorded value, D.4.4) |
| AgentDyn (A; B/C stretch) | phase 10 | prompt and checker versions confounding defence comparisons; history re-keying |
| Mandate | phase 10 | unreleased code states (iter2/iter4/final-opus); the denial-text change around 2026-06-29 |
| Survey runs and AgentHarm | phases 6 and 10 | `run_error_imposes_outcome` (11), `unexecuted_trailing_calls` (48), `injection_task_as_user_task_prepass` (105); AgentHarm per the D.9 table |
| DRIFT, CIAware-Bench, STAC, ASB | when implemented | the I.1.2 C26 rows (for example the ASB id defect) |
| NIST AgentDojo-Inspect | phase 10 | not a distinct corpus: mirror duplicates are recorded through lineage (I.2.4); its own artefacts only where its bytes differ |
| Live AgentDojo and AutoDojo | phases 8 and 9 | D.10.9 (the live instance) |

### D.15.7 Tests

- Each catalogue validates against its schema.
- Every `detector` and `handling` rule id exists in a catalogue.
- Each synthetic fixture triggers its class exactly once.
- An unknown anomaly yields `artefact.unclassified.*`.
- No handling path changes an AER source value or a compat byte: a differential test runs with the catalogue on and
  off and compares the AER and compat bytes.
- The stats tables are byte-identical across runs and `--jobs` values.

### D.15.8 Implementation resolutions (phase 6, 2026-10-08)

The shared layer is `src/agentprov/artefacts/` (L3, beside `validate/`; `catalogue.py`, `detectors.py`, `scan.py`). It
imports no adapter module, writes nothing and changes none of `aer/`, `prov/`, `validate/` or `corpus/`. The code is the
reference. The resolutions below fix what D.15.2 and D.15.3 left open.

1. **Discovery reads package data only.** `discover_catalogues()` walks `resources.files("agentprov") / "adapters"` and
   parses each `<family>/artefacts.toml`. Importing `agentprov.artefacts` loads no `agentprov.adapters.<family>` module (a
   test checks `sys.modules` in a fresh interpreter). Rule catalogues are found the same way (`<family>/rules/*.rules.toml`,
   the `aer` catalogue and the `aprov` engine catalogue), so the existence check needs no registry entry for a new family.
2. **File shape.** A catalogue has a top-level integer `version`, `family` (it must equal the directory name) and an
   optional `namespaces` list (default `[family]`; the `<ns>` of every entry id must be in it, so the `agentdojo` family
   can hold `rope.art.*` and `survey.art.*`). Entries are `[[artefact]]` tables with the D.15.2 fields. The parser reports
   every defect at once (`artefacts.catalogue_invalid`, exit 70: broken package data), rejects unknown keys, and sorts the
   entries by id. The file digest is recorded like a rule catalogue's (`ArtefactCatalogue.header()`).
3. **Field resolutions.**
   - `scope` is a table of `profiles`, `parts` and `sources` lists. Only `profiles` restricts matching, because an AER
     header names its profile but not its registry part; the other two document the entry.
   - `detector` is `{rule, class}` with class `O`, `D` or `I` (the evidence class of the detection). `rule` is either a
     mapper, SEM or accounting rule id `ns.name@n` or a generic detector `artefact.generic.<name>` (no version).
   - `recorded_as` is a table `{issues, notes, sem}` of lists (seal-issue codes, `note` kinds, SEM annotation types).
   - `handling` is `{class, rule}`; `rule` is required for `CR` and `DR`, optional for `RJ`, `FO` and `NR`. SEM rules do not
     exist yet, so an `RJ` entry names its annotation under `recorded_as.sem` until the SEM catalogue lands.
   - `expected` rows may add `unit` (default `executions`; some audit counts are tool turns or entities) and `status`
     (`unverified` by default, D.15.6). No count is estimated: an entry without a published figure has no `expected` row.
   - New optional `claims`: generic detectors, or one variant (`artefact.generic.<name>#<variant>`), that the entry accounts
     for although its own detector is a mapper rule.
4. **Reference check.** `check_references()` reports a `detector.rule` or `handling.rule` that is in no rule catalogue (the
   detector may also be a registered generic detector), a `claims` item that names an unregistered detector or an unknown
   variant of a closed-variant detector, and a `recorded_as.issues` code that is neither a core issue code (C.12.3) nor
   declared by a rule catalogue. Rules with status `reserved` count as existing.
5. **The net is `scan(aer_records, catalogues) -> list[Finding]`.**
   - Input is the records of one sealed AER, header first and seal last. Without a seal the accounting and issue detectors
     are skipped, not guessed.
   - A finding is one (detector, variant) in one execution: `ex`, `detector`, `variant`, the claiming `entries` and their
     `handling` classes, up to 25 locators (`ids`, record, part or scope ids, never content), the exact count `n`, and the
     `rules` and `issue_codes` the evidence cited. The list is sorted by `(ex, detector, variant)`.
   - Variants are tokens, never source text: an odd finish reason becomes `other`; a time reason, a check id or an issue
     code is kept only if it is a safe token.
   - `table(findings, n_executions=None)` gives the D.15.4 rows (executions, hits, proportion, first five execution ids)
     per artefact id, unclassified rows included. `scan_many` and `table` do not depend on input order.
6. **Detectors implemented** (class in brackets): `empty_execution` (O), `harness_imposed_outcome` (O),
   `sentinel_time` (O: `unknown_<reason>`, `raw_sentinel`, `typed_sentinel`), `provider_id_anomaly` (O: `absent`, `empty`,
   `repeated`, `link_conflict`), `unexecuted_call` (D, computed from executions and deny decisions rather than from the
   issue), `abnormal_finish` (O; the normal set is `stop`, `tool_calls`, `tool_use`, `end_turn` and a few provider
   spellings, compared case-insensitively), `text_encoded_call` (I, heuristic: call markers, a JSON call shape, or a
   `name(` of a tool of the run in an assistant message with no structured call), `pass_loss` (D), `accounting_inconsistent`
   and `accounting_unverifiable` (O, one variant per check id), and `seal_issue` (any issue with no generic counterpart,
   variant = its code). Seal issues that correspond to a detector (`no_execution_observed`, `outcome_imposed_by_runner`,
   `unexecuted_tool_call`, `call_result_link_conflict`, `retry_passes_inferred`, `earlier_attempts_unobservable`) join that
   detector's finding; the two `accounting_*` mirrors are covered by the check verdicts.
   **Not yet implemented, recorded so the gap is visible** (`NOT_YET_IMPLEMENTED`): `cross_origin_duplicate` (needs the
   corpus index) and `validator_warning` (needs the raw store). `payload_not_reaching_agent` was listed here until
   2026-10-11 and is implemented (item 11).
7. **Claiming.** An entry claims a finding when its `scope.profiles` admits the execution's profile and one of these holds:
   its `detector.rule` is the finding's generic detector; its `detector.rule` is a mapper rule that the finding's evidence
   cites (a field-scoped rule reference of a hit record, the rule of the corresponding seal issue, or the accounting check
   id); a `claims` item names the detector (and variant); or a `recorded_as.issues` code contributed to the finding. All
   claiming entries are listed (one finding may count in several table rows; the rows are coverage, not a partition).
   A finding with no claiming entry is `artefact.unclassified.<detector>`, never dropped. Bespoke per-entry counts come from
   the handlers' rule references (`stats --artefacts`, phase 11).
8. **Not wired yet.** `import --dry-run --artefacts` waits for the import pipeline (still a stub) and `stats --artefacts` for
   phase 11. The public functions are `scan`, `scan_many` and `table`; the CLI will add no semantics.
9. **Seed catalogue `adprov`** (`adapters/adprov/artefacts.toml`, version 1, 31 entries). It covers the generated tree
   (A1 to A13 and `reported_calls_exceed`) and the converted tree (timing stub, DoS polarity, benign constant, run error,
   injection task as user task, PI sentinel, context taint, unresolved upstream link), with the figures quoted by this
   section and D.10.9 as `unverified` expected counts. Scanning the 19 golden v1 AERs leaves no unclassified finding
   (`tests/golden/test_artefact_scan.py`); a new anomaly there fails the test until a reviewed entry claims it.
10. **Tests.** `tests/unit/artefacts/` (schema, rule-id existence, discovery, each synthetic AER triggers its class exactly
    once, unclassified findings, determinism, the on/off differential, the table), `tests/boundary/test_artefacts_boundary.py`
    (L3 placement, purity, nothing in `aer/`, `prov/`, `validate/`, `corpus/` imports it) and
    `tests/golden/test_artefact_scan.py`. The compat-bytes half of the D.15.7 differential needs a handling path that edits
    something, and none exists: the net reads only.
11. **`payload_not_reaching_agent` (phase-10 analysis B5, 2026-10-11).** The one detector that reads SEM. `scan(...,
    sem_records=...)` takes the records of the execution's SEM file (`load_sem(...).records`, header first); a SEM whose `ex`
    differs from the AER header's raises `ScanError`, and without `sem_records` the detector is skipped, not guessed (as the
    seal-dependent detectors are without a seal). An execution is *attacked* when the AER header task names an `attack_id` and
    the unit is an `agent_execution`; it is a hit (class D, locator `exec`) when no `injection_marker` annotation has status
    `present`. Variants keep the causes apart: `absent` (every comparison found nothing), `undetermined` (some comparison was
    `ambiguous` or a `gap`, none present) and `no_marker` (no marker annotation at all, e.g. no tool result or no payload
    fixture). It reports and never alters a record, and it re-reads no tool output, so a wrong `absent` of the SEM profile (the
    YAML-escaped AutoDojo payloads of analysis B1) is inherited. DoS attacks are not excluded here (the analysis excluded
    them from its denominator). **Open item:** like the rest of the net it is not wired into `import`; `stats --artefacts`
    and `import --dry-run --artefacts` will pass the SEM records.
12. **Phase-10 catalogue entries (analysis B4, 2026-10-11).** `adapters/agentdojo/artefacts.toml` now declares the namespaces
    `agentdojo`, `rope`, `agentdyn`, `mandate` and `survey` (item 2), widens the scope of the generic entries to the
    phase-10 profiles (`rope`, `autodojo-via-rope`, `agentdyn`, `mandate-agentdojo-eval`, `survey-runs`) with the measured
    counts as `expected` rows (snapshots `<source>:<part>` for the sources other than `agentdojo`), and adds 17 entries: the
    three head classes the net left unclassified (`naive_timestamp`, `repeated_provider_ids`, `incomplete_run`), the finding
    of item 11, `defence_benign_intervention`, the survey text-call entry, five ROPE entries, four AgentDyn entries and two
    Mandate entries. Entries whose proper handling needs a mapper change that is not applied (B1, B3) are `FO`. Not added:
    the identical-trajectories entry (no registered detector to cite; `cross_origin_duplicate` is not implemented). The
    catalogue version stays 1 (nothing is released); its digest enters no AER, SEM or PROV file (nothing outside
    `agentprov.artefacts` imports it) and no `corpus.json` records it yet, so no corpus changes.
13. **Corpus pre-check, wave 1 (2026-10-21; DECISIONS D-581..D-585; regeneration-batch item 109).** The wave-1
    dossiers (`docs/reports/precheck/<corpus>.md`) proposed entries in a draft form that the schema of item 3 rejects
    (open causes, a `DS` class, `pending` statuses, placeholder detectors). They were fitted as follows (D-581):
    - a cause outside the closed list becomes the known cause or `unknown`, and a datasheet disclosure is an `FO` entry
      whose description states it;
    - a recount against a paper, README or design, with no per-trace detector, cites as `detector` the existing rule
      whose output the recount reads (`agentdojo.checker_outcome@1` for logged outcomes,
      `agentdojo.pipeline_dir_is_model_identity@1` for arm coverage, `survey.internal_server_error_patch@1`,
      `inspect.tool_error_status@1`). Such an entry declares no `recorded_as` and no `claims`, so it claims no safety-net
      finding (tested on the native agentdojo fixtures). A new detector rule would be a rule-catalogue change;
    - a count measured over the whole population is `verified`, a lower bound or a plausible figure `unverified`, and a
      pre-registered estimate gets no row (item 3).

    **New entries (D-582):**
    - `agentdojo`: `agentdojo.art.incomplete_arm`, `agentdyn.art.paper_row_not_in_logs`,
      `agentdyn.art.github_it1_checker_prefix`, `survey.art.readme_error_tasks_mismatch` and
      `survey.art.partial_table_unbacked`;
    - `inspect`: `inspect.art.bundled_file_not_found`, `inspect.art.abnormal_finish_max_tokens` and
      `inspect.art.text_tool_call`.

    All are `FO` and `manuscript = true`. **Extensions (D-583):** `agentdojo.art.validity_defects` takes Mandate into its
    scope, with the #181 (3) and #161 (4) rows, and a #181 survey row (13, a lower bound) (pre-check CC-07);
    `agentdojo.art.defence_benign_intervention` takes Mandate's intent-arm row. **ROPE (D-584):** the three entries that
    described `agentdojo.suites@1` behaviour are corrected, not retired:
    - `rope.art.autodojo_payload_escaped` becomes `CR` through `agentdojo.autodojo_payload_unescape@1`;
    - `rope.art.security_without_exposure` is detected by `agentdojo.success_without_visible_payload@1`;
    - `rope.art.pipeline_tag_not_identity` names the one directory whose tag is foreign.

    Each keeps its suites@1 count. The suites@2 counts measured on the stored AERs are `unverified` until the
    regenerated corpus confirms them. Both versions stay at 1 (D-585; D-31 owner ruling 2026-10-21: in place, since no
    corpus records an artefact catalogue). The bytes move only the family's `adapter_code_sha256`, a code digest that
    `recompute` reports as a notice. Tests: `tests/adapters/agentdojo/test_artefacts.py` and
    `tests/adapters/inspect/test_artefacts.py`.
    **Wave 2 (D-589):** `agentdojo.art.defence_authored_message` (`CR`, melon D-586),
    `agentdojo.art.reported_rows_unbacked` and `geryon.art.author_declared_unusable_arm` (both `FO`). The namespace
    `geryon` is added.
14. **Corpus wave 2 (2026-10-29; DECISIONS D-950).** A read-only census of the 40 valid wave-2 working trees found that
    29 had no classified entry (DTap, censused later as the 41st tree, had three unclaimed classes): the catalogues' scopes named only round-1 profiles (the gap the pre-check recorded as
    CC-09). The pass applies three rules.
    - **Widen only where the rule is the same.** An existing entry takes a wave-2 profile when the profile's hits cite
      the entry's rule (directly or through its `_unverified` twin, D.5.4) and the profile declares the quirk. That gives
      12 `agentdojo` entries (24 TraceLogger forks, DRIFT and ResCont where the description holds) and 3 `inspect` entries.
      Two existing entries gain a `claims` item for the generic finding their own rule produces
      (`openhands.art.not_executed_notice`, `credleak.art.model_calls_not_recorded`).
    - **Otherwise a source-specific entry, citing its rule.** These are 25 in `agentdojo` (namespaces `drift` and
      `rescont` added), 9 in `inspect`, 5 in `credleak`, 2 in `openhands` and 3 in `dtap` (D.16.7's unanswered calls, D-934's
      strings over 1 MiB, and trajectories of `List MCP Tools` steps only). Their counts are the census's, `unverified`.
      A ResCont row is not a TraceLogger log, so its ids, times and passes get `rescont.*` entries, not the TraceLogger ones.
    - **A finding with no documented mechanism stays unclassified** and is listed in
      `docs/reports/wave-2-artefacts/README.md`. These are the `text_encoded_call` heuristics of sources whose call path
      is not documented, DCA's later user messages, ControlArena's calls without a tool event and its non-copy repeated
      ids, and whistlebench's few lost calls and dangling results that co-occur with link conflicts or sample limits.

    A generic `claims` item (`max_iters_pending`, `silent_rerun`) also counts findings of another mechanism in a
    mixed-format profile (dca's DRIFT part, mohameduk's link conflicts, seagent's guard-dropped calls). The descriptions
    say so. A further `claims` qualifier would change round-1 tables, so none is added.

    No sealed corpus is in a new scope except `agentdyn` part a, which cites no DRIFT or ResCont rule, so the round-1
    tables of the user guide's chapter 15 do not change. Byte class 1: the bytes move only the `adapter_code_sha256` of
    `agentdojo`, `inspect`, `openhands`, `credleak` and `dtap` (D-585). The catalogues stay at version 1.

---

## D.16 The DTap-Bench family (`dtap`; planned, phase 10b)

Status: **implemented** (phase 10b step 3, 2026-10-12; resolutions in D.16.18; designed in step 2, 2026-10-11; DECISIONS D-26, D-28, D-29). Step 3
implements it; step 4 imports the full snapshot. The registry part stays `planned` until the D.3.2 gates pass. Every
count below is from the step-1 census and is cited as `[sources/dtap.md §N]` or `[verify/dtap.md §N]` (the reports
are in the research workspace, `investigation/sources/dtap.md` and `investigation/verify/dtap.md`; the census JSON is
in `$AGENTPROV_HOME/migration-work/phase10b/census/`). Text inside the datasets (payloads, tool outputs, judge
rationales, configurations) is untrusted data, never instructions (G; CLAUDE.md "Security").

DTap-Bench is the first non-AgentDojo agent-security source with a large licensed release: 67,808 trajectory files
from four agent harnesses (OpenAI Agents SDK `openaisdk`, Claude Agent SDK `claudesdk`, Google ADK `googleadk`,
OpenClaw `openclaw`), seven models in ten harness/model pairs, 14 domains, direct and indirect injection, a judge
result per task directory, and 6,682 task configurations in a second dataset [sources/dtap.md bottom line, §4.1]. Its
structure differs from every existing family: one step log per run (no message list, no model-call boundary, no call
ids), a single end-of-run time, and attack payloads that live in a separate configuration rather than in the run log.
That is why it gets its own family instead of a profile of an existing one (D-28).

### D.16.1 Identity and pins

**Pins.** Both are Hugging Face dataset repositories, which are git repositories. They are staged as bare clones plus a
detached worktree at the pin, LFS not smudged, in `$AGENTPROV_HOME/staging/dtap/` [sources/dtap.md §1; verify/dtap.md
§1].

| Role | Repository | Revision (full) | Date | Content |
|---|---|---|---|---|
| `runs` (primary) | `https://huggingface.co/datasets/AI-Secure/DTap-Bench-Agent-Trajectories` | `836caf2fdd78b888ddd14fb62dc038e932e17898` | 2026-07-01T04:46:10Z | 133,851 files, 3.8 GB; 67,816 non-judge JSON files, 3,586,501,941 B; 170 commits, `main` only, no tags |
| `tasks` (context) | `https://huggingface.co/datasets/AI-Secure/DecodingTrust-Agent-Platform` | `a3edc9b7c48cbf16c2ea9c18990fb94c7494dd04` | 2026-06-18T22:20:35Z | 27,568 files; 6,682 `config.yaml`; 57 commits |
| `lfs_object` (2 pins) | the `runs` repository, by path at the `runs` revision | as `runs` | — | the two JSON trajectories committed as LFS pointers (D.16.2), fetched by oid and verified against the pointer (D-29 item 4) |

**Fetching and pinning.**
- Ordinary files are stored with origin `git` `{repo, commit, path, blob_sha1}` and vouched for by the cached tree
  listing of the pinned commit (`--verify-against-pin`, D.2.9 note item 4), as for the AgentDojo-family pins. The
  staging clones are seeded offline into the bare fetch cache with `tools/seed_git_cache.py` (logged in
  `acquisitions.jsonl`). No network is used during import (D.13.2).
- The two LFS objects (D-29 item 4) are fetched by step 3, under the user's standing phase-10b download approval, as
  `hf` pins `{repo, revision, path}` with `sha256` = the pointer's `oid sha256:` value and `bytes` = its `size`. The
  object is stored with origin `hf`, and its digest is checked against the pointer before any reader runs (D.13.2).
  The pointer itself is also stored (raw is never replaced) and registered (D.16.2). An object that cannot be fetched,
  or does not verify, leaves the pointer registered and nothing mapped.
- Task configurations are context artefacts (role `supporting`) of the `tasks` pin, stored before mapping with their
  own git origins. No configuration revision was in force during any run: runs span 2026-02-12T21:45:14Z to
  2026-05-05T03:53:41Z, and the two repositories' first commits are 2026-05-14 and 2026-05-21. Every configuration
  statement therefore rests on per-run text verification (D.16.5) [sources/dtap.md §3.5, §8].

**Execution identity.** There is one execution per trajectory-bearing file. The execution id is content-addressed like
every import (`import_execution_id("dtap.trajectory/dtap-bench", sha256, {"p": ""})`, AD-04; D-27 c2), so
byte-identical files collapse to one execution with several origins (D-29 item 7). The **logical identity** of a run is
its path: `(framework, model, domain, split, subcategory?, risk_category?, task_dir, file stem)`. It is never
`task_info.task_id`: 78 (framework, model, domain, split, id) keys are shared by several task directories, and telecom
ids are reused across `001`, `002`, … It is never `traj_info.metadata.trace_id` either: 56,376 files carry one, with
55,770 distinct values and 517 values shared [sources/dtap.md §3.6]. Both are kept verbatim in `ext.dtap`. The model
and the harness come from the path only. No structured model id exists, and the 597 files that name a model in free
text are never used for identity [sources/dtap.md §3.6].

**Path grammar.** No path outside it was found [verify/dtap.md §4].

```
<framework>/<model>/<domain>/benign/[<subcategory>/]<task_dir>/<file>
<framework>/<model>/<domain>/malicious/<threat>/<risk_category>/<task_dir>/<file>
   threat ∈ direct | indirect | direct_prompt | direct_no_attack
```

**`task` header fields.** All are `O`, with an origin locator `{"a": "a0", "o": "/path"}` (C.9.1), because the evidence
is the location, not the bytes:
- `benchmark`: `"dtap"`;
- `suite`: the domain;
- `task_id`: the path from the split segment to the task directory (e.g. `malicious/indirect/data-exfiltration/1`,
  `benign/math/57`);
- `attack_id`: the threat segment for `direct`, `indirect` and `direct_prompt`; `null` for `benign` and for the
  `direct_no_attack` control (rule `dtap.control_split_no_attack@1`, I; D.16.6);
- `attack_target_id`: the risk category (`null` for benign);
- `defense_id`: absent, with `unk {"/task/defense_id": "not_recorded"}`. DTap records no defence dimension.

### D.16.2 Dialect and reader (`agentprov.adapters.dtap.dialect.DtapTrajectoryReader`)

Dialect `dtap.trajectory` has one variant, `v1`: `{task_info, traj_info, trajectory[]}` in all 67,806 parseable files,
plus `debug` in 1,534. One schema serves all four harnesses [sources/dtap.md §3.1]. Parsing is `strict_json_loads`
under `IngestLimits`; the largest file is 10,363,506 B, inside `max_json_bytes`. The census found no duplicate keys,
non-finite numbers, lone surrogates or BOMs [verify/dtap.md §3]. A future lone surrogate is handled per D-23. Sniff: a
JSON object with exactly the keys `task_info`, `traj_info` and `trajectory`, and optionally `debug`.

**File variants.** Every trajectory-bearing name is listed, with counts from [sources/dtap.md §2.3; verify/dtap.md §2].

| File | Count | Reader outcome | Code / rule |
|---|---:|---|---|
| `<YYYYMMDD_HHMMSS>.json` | 64,110 | unit (`agent_execution`) | file stem kept in `ext.dtap.file_stem`. The stem is the generating machine's local time and is **never** a time (D.16.4) |
| `trajectory.json` | 3,590 | unit (the whole workflow domain) | same mapping; 20 of them are synthetic (row below) |
| `<TS>_<N>.json` | 99 | unit: an attempt of a re-run group (D-29 item 6) | `dtap.rerun_group@1` (D) |
| `<TS>(1).json` | 8 | byte-identical to the plain file, so the same `ex`: the second location is a `raw/origins.jsonl` row with register `dedup.collapsed` (D-29 item 7). If the bytes ever differ, it is a separate attempt under `dtap.rerun_group@1` | runner (D.2.9) |
| `partial_trajectory.json` | 1 | unit with the seal issues `dtap.partial_trajectory` and `incomplete_run` (D-29 item 8) | `dtap.partial_file_name@1` (I: the file name is the only evidence) |
| any trajectory with `trajectory: []` | 17 | `outcome_only` unit (D-29 item 3) | `dtap.empty_trajectory@1` (D) |
| `task_info.synthetic: true` | 20 | **not an execution**: stored, registered `select.not_execution_artefact` (detail `dtap.synthetic`), counted under role `not_executions` in the disclosure (D-29 item 1). The judge file of such a directory is registered the same way, because its subject is a fabricated trajectory | `dtap.synthetic_marker@1` (D; premises `/task_info/synthetic`, `/traj_info/metadata/synthetic`) |
| Git LFS pointer standing in for JSON | 2 | not JSON. The sniff recognises the pointer header and returns no match with reason `dtap.lfs_pointer`, so the runner registers `select.not_execution_artefact` (detail `dtap.lfs_pointer`). The fetched, verified object is imported normally (D.16.1; D-29 item 4) | `dtap.lfs_pointer@1` (D) |
| `red_teaming_agent_<TS>.json` | 8 | a different schema (attack-generation logs of an attacker agent): `select.not_execution_artefact` | — |
| `judge_result.json` | 65,902 (+8 identical `(1)` copies) | an auxiliary artefact of the trajectories of its directory (D.16.8). It is the primary artefact of an `outcome_only` unit where the directory holds no trajectory (22 directories, plus 8 that hold only a red-teaming log) | `dtap.judge_without_trajectory@1` (D) |
| `screenshots/screenshot_NNN.png` | 122 | LFS pointer files: `select.not_execution_artefact`. The PNG objects are not fetched; the 82 `[SEE screenshots/…]` texts in 30 openaisdk macos files stay text | — |
| `README.md`, `.gitattributes` | 2 | `select.not_execution_artefact` | — |

Register codes are the closed set of HL H.6.3. DTap adds none; `dtap.*` strings appear only in `detail`.

**Reader output.** There is one located item per file, with locator `{"p": ""}`. The reader parses the path into the
facets above and checks them against `task_info.domain` and the split (`dtap.path_field_mismatch`, info, never
corrected). It classifies each `state` without interpreting it: JSON object, JSON array, plain string,
Python-repr-like string (starts with `{'` or `[{'` and is not JSON), other `{`/`[` string, integer, or null
[sources/dtap.md §3.3]. Nothing is evaluated. Python-repr strings (188,050 results, 26.2 %) are text (D.13.1 item 3;
AD-10 row 16).

### D.16.3 Mapping to AER

There is one AER per unit. Records come in this order: header, actors, scopes, fixtures (D.16.5 and D.16.6), then the
steps in array order, each activity record immediately before the message it generates (backward-only references,
C.5.2), and finally the judgements (D.16.8). Local ids follow C.4.2. Message `m<i>` is step `i` (`step_id` equals the
0-based index in 100 % of files [sources/dtap.md §3.2]), so ids are gapless only per prefix.

**Header.**
- `unit`: `agent_execution`, or `outcome_only` (D.16.2).
- `dialect {id: "dtap.trajectory", variant: "v1"}`; `adapter {id: "dtap.trajectory", version: "0.1.0"}`; `profile`
  `dtap-bench`; `rules {"aer": 1, "dtap": 1}`.
- `ns {"dtap": "https://w3id.org/agentprov/ns/dtap#"}`. A new namespace is not an AER change (C.10 item 7).
- `instrumentation`: `unk not_recorded`. The harness versions are not recorded anywhere [sources/dtap.md §3.6].
- `artifacts`: `a0` the trajectory (role `primary`, `prov_primary: "native"`); `a1` the judge file (role `supporting`)
  when linked; `a2` the configuration (role `supporting`) when joined.
- `ext.dtap`: `path_facets`, `file_stem`, `task_info_task_id`, `trace_id`, `framework_field` (OpenClaw's
  `metadata.framework`), `traj_info_success` (null in 24,374 files; its meaning is unknown and it is never
  interpreted), `final_response`, `rerun {group_size, stems}`, `join` (D.16.5) and `judge_link` (D.16.8).

**Actors.** In fixed order; only those that apply.

| id | kind | Basis |
|---|---|---|
| `bench` | `benchmark` | `name: "dtap"`; `unk {"/version": "not_recorded", "/code": "not_recorded"}` |
| `harness` | `harness` | `name` = the framework segment (`openaisdk`, `claudesdk`, `googleadk`, `openclaw`), `evf {"/name": "I"}`, `dtap.path_harness_identity@1`; `unk {"/code": "not_recorded"}` |
| `user` | `simulated_user` | `dtap.user_is_simulated_unverified@1` (I) |
| `agent` | `llm_agent` | `model.requested` = the model segment, `evf {"/model": "I"}`, `dtap.path_model_identity@1`; `on_behalf_of: "user"`; `unk {"/model/served", "/model/provider", "/params": "not_recorded"}` |
| `env` | `tool_runtime` | the MCP tool runtime; `on_behalf_of: "agent"` with `evf {"/on_behalf_of": "I"}`, `dtap.auto_execution_unverified@1` |
| `att` | `attacker` | iff `task.attack_id` is non-null; `name` = the threat segment |
| `judge` | `judge` | the DTap judge; `unk {"/model": "not_recorded"}`. Judge models named in `attack_metadata.llm_model` stay in `ext.dtap.judge` |

**Scopes.**
- `run` (kind `run`). Its `t` is given in D.16.4. Its `status` is `"error"` (O by source, with the locator of the error
  step) for the 47 harness-failure runs (D-29 item 2) and for the 17 empty runs whose `traj_info.metadata.error` is
  recorded.
- `att0` (kind `attempt`, parent `run`, actor `agent`), with `unk {"/scored": "not_recorded", "/index":
  "not_recorded"}`. It is omitted for `outcome_only` units. DTap records no silent re-run inside a file; attempts
  across files are separate executions (D-29 item 6).

**Step mapping table.** O = observed in the file; the rule column names the D and I rules. A "segment" is a maximal run
of consecutive agent steps (`send_message_to_user` included) between non-agent steps.

| Source step | AER records | Evidence and rules |
|---|---|---|
| `user` step (`state` str) | `m<i>` role `user` (verbatim), actor `user`, part `text` = `state` | text O; `evf {"/actor": "I"}`, `dtap.user_is_simulated_unverified@1`. A later user step (35 multi-turn files have 2, 4, 5, 8 or 10 user steps [sources/dtap.md §11.2 item 7]) also gets the issue `unattributed_additional_user_message`. Who *authored* a direct run's user text is a SEM `author` claim (D.16.6), never a change of the AER actor |
| agent step with `tool_name` and `tool_params` | `mc<n>` for the first agent step of its segment (below); then `m<i>` role `agent` (verbatim, D-28), actor `agent`, `generated_by: mc<n>`, part `{t: "tool_call", name: metadata.tool_name, args: metadata.tool_params}` with `unk {"/parts/0/args_raw": "not_recorded"}`. `action` (a display string) and `server` go to `ext.dtap` | args and name O; `generated_by` and actor I (`dtap.agent_step_is_model_output_unverified@1`) |
| agent step `send_message_to_user` | as above, with part `{t: "text", text: metadata.message}` (118,447 steps; claudesdk logs intermediate messages too) | text O. `traj_info.agent_final_response` is kept in `ext.dtap.final_response`. It equals the last message in 63,550 of 63,567 non-null cases; a difference gives the info issue `dtap.final_response_differs` (`dtap.final_response_copy@1`, D) [sources/dtap.md §11.2 item 6] |
| meta-step `List MCP Tools (<server>)`: an agent step without params plus its tool step (openaisdk 211,478 pairs, claudesdk 3,269, googleadk 516) | **neither** a model output nor an agent tool call: `ac<n>` `activity {type: "dtap:list_mcp_tools", actor: "harness", scope: "att0", inputs: [], label: action}` and `af<n>` `artefact {type: "dtap:tool_name_list", content: state, generated_by: ac<n>}`. No message and no `tool_execution` | activity and content O by source (`src` cites both steps); `evf {"/actor": "I"}`, `dtap.list_mcp_tools_harness_step@1` (the SDK lists the tools itself; the SDK code is unverified) [sources/dtap.md §3.4] |
| claudesdk `ToolSearch(...)` and other built-ins (`Glob`, `Bash`, `TodoWrite`, `Agent`, …; `server: "unknown"`) | an ordinary tool call and execution (the model invokes them). `server` is kept verbatim in `ext.dtap.server`, never in a typed field | as for tool steps; SEM labels built-ins from their own table (D.16.9). `Agent` may spawn a sub-agent whose steps are not logged; no `subagent` scope is invented |
| OpenClaw agent step `action: "error"` with `metadata.error` (47 files) | `ac<n>` `activity {type: "dtap:harness_error", actor: "harness", status: "error"}` and `af<n>` `artefact {type: "dtap:error_text", content: metadata.error}`; the run scope gets `status: "error"`; seal issue `dtap.harness_failure` | O by source (the error is observed); actor I (`dtap.harness_error_step@1`) |
| the `send_message_to_user` that follows an error step | `m<i>` role `agent`, with `unk {"/actor": "ambiguous", "/generated_by": "not_recorded"}` | `dtap.harness_error_echo@1` (I). It echoes the error text; whether the model or the harness wrote it is not recorded |
| `tool` step | `te<k>`: actor `env`, scope `att0`, `call` per D.16.7, `name` = the paired call's `tool_name`, `args` = its `tool_params`, `unk {"/status": "not_recorded", "/returned": "not_recorded"}`. `unk {"/t/start": "not_recorded", "/t/end": "not_recorded"}`; `duration_s` (on 133,667 results) goes to `ext.dtap.duration_s`, with `unk {"/t/dur_s": "ambiguous"}` where present (D.16.4). Then `m<i>` role `tool`, actor `env`, `generated_by: te<k>`, part `tool_result {responds_to, …}` | content O; `te` existence I (`dtap.tool_step_is_execution_unverified@1`); link I (D.16.7). No error flag exists, so the tool status is never inferred from content [sources/dtap.md §11.2 item 9] |
| tool `state` | dict or list → `value` (JSON; member order through `ext.lex`). Plain, Python-repr or other string → `text`, verbatim, never evaluated. Integer → `value`. Null → `value: null` | O |
| the result's `tool_name` | `tool_result.name` when it is a real tool name. The claudesdk literal `unknown` (20,318 results in multi-call batches) is never written into the typed `name` (C.7.3 deny-list): it goes to `ext.dtap.result_tool_name`, with `unk {"/parts/0/name": "ambiguous"}` | O, verbatim in `ext` |
| inline images (base64 `data:image/…` in 60 claudesdk, 195 openaisdk and 1 googleadk files; long base64 runs in 221 openclaw files) | kept as the text they are in. A string over 1 MiB would need the import-side blob surface, which does not exist yet (D.9.5 deviation 1; D.16.14 item R4). Step 3 measures the longest string and reports it | O |
| dataset-side `[truncated` markers (54 files, 131 occurrences) | kept verbatim; info issue `dtap.source_truncation_marker` (`dtap.source_truncation_marker@1`, D: the marker text is observed) | O |
| a file with no user step (10,154 files: openaisdk 9,821, of which all 7,505 gpt-oss-120b files; claudesdk 190; googleadk 141; openclaw 2) | no user message is invented. `task_info.original_instruction` becomes a fixture `task_prompt` (O by source, `src /task_info/original_instruction`); info issue `dtap.user_step_not_logged` | `dtap.user_step_not_logged@1` (D). The instruction may be the 500-character cut (D.16.5) [sources/dtap.md §11.2 item 7] |
| `task_info.malicious_instruction` (non-empty) | a fixture `kind: "other"`, `subtype: "dtap.attack_goal"`, `actor: "att"` (`evf {"/actor": "I"}`), content verbatim (O by source) | `dtap.config_payload_attacker_unverified@1` for the attribution. The CRM texts embed attacker-account tokens (D.16.13) |
| `task_info.malicious_instruction_at_eval` + `goal_text_updated` (1,183 files) | a second fixture, `subtype: "dtap.attack_goal_at_eval"`; `goal_text_updated` verbatim in its `ext.dtap` (a date label, never a `t` value); info issue `dtap.goal_rewritten_at_eval` | `dtap.goal_rewritten_at_eval@1` (D) [sources/dtap.md §6.5] |
| `traj_info` counters `step_count`, `actions_count`, `tool_count`, `user_turn` | a profile accounting check `dtap.acc.counters@1`, passed through `ctx.check` (C.12.4). It is consistent when each counter equals the step population it counts (agent steps including messages and meta-steps; tool steps; user steps) | consistent in 100 % of 67,806 files [sources/dtap.md §3.1]; any deviation is `inconsistent`, never corrected |
| `debug.system_prompt` (629 files) | fixture `system_prompt`, O by source | D.16.6 compares it with the configuration (476 of 476 equal where a configuration exists [sources/dtap.md §8]) |
| `debug.tool_descriptions` (1,517 files) or OpenClaw `traj_info.metadata.mcp_tools` (11,413 files; 491,627 entries over 30 servers) | fixture `tool_definitions`, content verbatim, O by source. Every `mc<n>` sets `tools` to it, with `evf {"/tools": "I"}` | `dtap.logged_tools_offered_unverified@1` (I: the list is logged once per run, not per call) [sources/dtap.md §3.6] |

**Model calls.** DTap logs no model-call boundary: no request, response, usage, finish reason, parameters or time
[sources/dtap.md §9]. AER keeps the agent's activity visible without inventing its shape:
- one `mc<n>` per segment (actor `agent`, `role: "agent"`, scope `att0`, `status: "kept"`), existence I under
  `dtap.agent_segment_one_turn_unverified@1`;
- `input` = the ids of every earlier message of the run (user, agent and tool), with `evf {"/input": "I"}` under
  `dtap.context_is_logged_prefix_unverified@1`;
- `unk {"/request", "/response", "/usage", "/finish_reason", "/params", "/t": "not_recorded"}`.

The context rule states that the list covers **logged steps only**. The system prompt and the tool descriptions are
never in the step stream, so they are never input members; a logged system prompt is a fixture (D.16.6). A segment
that ends a run without any tool step is still one call. Accounting: the calls are not observed, so
`aer.acc.agent_calls_vs_assistant@1` records `unverifiable` (`model_calls_derived_from_messages`). The role-`agent`
messages are not "assistant" messages of the accounting (D-28), so `aer.acc.assistant_generated_by@1` does not apply.

**Order.** `m<i>` is after the previous step's record: `b: "pos"`, `evf {"/after": "I"}`,
`dtap.steps_append_ordered_unverified@1`. Array order and `step_id` are observed; that they are occurrence order is a
property of unverified harness code (D-24). Generated messages are after their generator (`causal`). No `time` edge
exists, because there is no per-step time.

### D.16.4 Time model

- **One end-of-run time.** `traj_info.timestamp` is the run end: `timestamp − duration` matches the file-name stamp to
  a median of 1.8 s (p90 6.3 s), against 30 s (p90 96 s) when it is read as the start [sources/dtap.md §3.5]. This is a
  statistical fit, not code, so the run scope carries it as `t.end` with `evf {"/t/end": "I"}` under
  `dtap.timestamp_is_run_end_unverified@1`. Aware values (60,371 with microseconds; the 20 synthetic files without)
  are re-encoded `+00:00` → `Z`, losslessly. Because the class is I, no `prov:endedAtTime` reaches the core bundle
  (NC-ALL-01).
- **Naive for Google ADK.** 7,415 googleadk timestamps have no zone. They map to `t.end_naive`, plus `t.raw.end`
  (verbatim) and `unk {"/t/end": "ambiguous"}`. The census's inference that they are UTC (the file-name stamps run 13 h,
  later 12 h, ahead, the New Zealand daylight-saving pattern) is recorded in the source card only. It is never applied
  [sources/dtap.md §3.5].
- **Durations without a clock.** `traj_info.duration` (seconds, float) and the tool `duration_s` have no stated clock.
  `t.dur_s` needs `dur_clock` (C.8.3), so it is not written: the values go to `ext.dtap.duration` and
  `ext.dtap.duration_s`, with `unk {"/t/dur_s": "ambiguous"}`. No start is ever computed: `end − duration` would be a
  derived time over an unknown clock.
- **No per-step times.** Nothing is derived from `duration_s`, from the file-name stamp (the local time of the
  generating machine, with offsets of 0, 4, 5, 7 and 8 h and a daylight shift), or from dates inside tool outputs or
  judge labels (`h5_rejudge_20260426`, `goal_text_updated`). Those stay verbatim in `ext.dtap`.

### D.16.5 Task-configuration join

**Path rule** (`dtap.config_path_join@1`, D: a deterministic string mapping with no assumption):
- benign runs map to `<domain>/benign[/<sub>]/<task>/config.yaml`;
- direct and indirect runs map to `<domain>/malicious/<threat>/<risk>/<task>/config.yaml`;
- `direct_prompt` and `direct_no_attack` runs map to the `direct` configuration.

Results over 67,806 runs: a parseable configuration for 67,011; none at the path for 786 (windows direct 320,
`direct_prompt` 320, medical no-attack 144, workflow indirect 2); an unparseable one for 9
(`crm/malicious/indirect/dangerous-actions/26`, duplicate key `attack_turns`) [sources/dtap.md §6.3]. Configurations
are parsed only through `ingest.yamlsafe.safe_load`. The duplicate-key file is stored like any context artefact; a run
that joins to it gets the issue `dtap.config_unparseable`.

**Verification** (`dtap.config_join_tier@1`, D: the tier is a deterministic comparison of observed strings). Two text
checks are recorded, with their method, in `ext.dtap.join {config_path, tier, instruction, goal, task_id}`:
1. **instruction**: `task_info.original_instruction` against what the agent receives. For benign and indirect runs
   this is `Task.task_instruction`; for direct runs, a `prompt` step's content or the goal; for `direct_prompt`, the
   goal; for `direct_no_attack` the check does not apply.
2. **goal**: `task_info.malicious_instruction` against `Attack.malicious_goal` (empty for benign and no-attack runs).

A text matches if it is exact, or equal after whitespace normalisation (almost always a trailing newline in the
configuration), or, for the instruction only, the 500-character prefix of the configuration text. The goal also
matches if the configuration goal is its prefix: the run text appends `Attack.additional_information` with run-time
attacker-account details. The tiers are [sources/dtap.md §6.3]:
- **A**: both verify (62,419 runs, 92.06 % of all, 93.15 % of joined);
- **B**: one verifies (2,899);
- **C**: neither verifies (1,693).

**Normalisations, only where evidenced** [sources/dtap.md §6.4]. `task_id` is a third, recorded check that never
changes the tier. It applies two normalisations: the medical off-by-one (zero-based trajectory ids against one-based
directories, 8,111 runs; `dtap.task_id_offset_medical@1`, I), and the telecom, browser and customer-service
reformatting (692 runs; `dtap.task_id_reformatted@1`, I). No other normalisation is applied.

**What the join licenses.**
- **Tier A.** Configuration content may describe the run, always at class I, under `dtap.config_content_tier_a@1`
  (assumption `dtap:ConfigAtPinIsRunConfig`, asserted and never verifiable, because the revision in force at run time
  is not recoverable [sources/dtap.md §8]). Configuration-derived statements are **never** class O, even where the
  bytes are copied verbatim, because their membership in the run is the inference.
- **Tier B or C, missing or unparseable.** The configuration is cited (when it exists) as a `supporting` artefact with
  its tier, and nothing in it is used for run-specific content: no payload fixture, no system prompt, no tool suffix.
  Seal issue `dtap.config_join_unverified` (warning) or `dtap.config_missing` (info), with the tier in `detail`
  [verify/dtap.md §10 item 4].

**Disclosures.**
- *500-character truncation.* `task_info.original_instruction` is cut at exactly 500 characters in 7,353 files, and
  6,923 of them are verified prefixes of the configuration text. A verified cut gives the info issue
  `dtap.task_info_truncated` (`dtap.instruction_cut_500@1`, D). A 500-character instruction with no verifying
  configuration gives the same issue under `dtap.instruction_length_500_unverified@1` (I) [sources/dtap.md §3.3].
- *Rewritten goals.* 1,183 runs also carry the evaluation-time goal (equal to the configuration goal in 254, near it in
  517, different in 412) [sources/dtap.md §6.5]. Both texts are fixtures (D.16.3), and the join compares the run-time
  text.
- *Appended goal text.* In 1,826 runs (indirect 1,205, direct 621) the goal is the configuration goal plus more text,
  whose published `additional_information` was later rewritten. The prefix match is recorded as `goal: "prefix"`.
- *Drift over time.* Tier A falls from 94.1 % (February runs) to 86.0 % (April). Tier C is concentrated in windows,
  macos and customer-service; 0 of 269 macos benign runs verify [sources/dtap.md §6.4]. The source card and the
  datasheet carry this. No run is dropped.

### D.16.6 Injection exposure model (the manuscript limitation)

**Configured attack steps.** There are 6,892 steps: environment 2,488, tool 2,262, skill 239, prompt 1,903
[verify/dtap.md §3]; the type sets per configuration are in [sources/dtap.md §6.2]. For a tier-A run of split `direct`
or `indirect`, each step of every `Attack.attack_turns[].attack_steps[]` becomes one fixture
`kind: "injection_payload"`:
- existence I (`dtap.config_content_tier_a@1`); `actor: "att"` (I, `dtap.config_payload_attacker_unverified@1`);
  `src` into the configuration artefact;
- `vector`: `environment:<injection_mcp_tool>`, `tool:<injected_tool>` (mode `suffix`), `skill:<skill_name>` (mode
  `create` or `append`) or `prompt:<mode>` (`jailbreak` or `suffix`);
- `content`: `kwargs` (an object) or `content` (a string); the turn and step indices go to `ext.dtap`.

Because the fixture's existence is I, the fixture entity, its attribution and its membership in the run are
**inference-bundle** statements (EF E.1.5 rule 4). Two splits differ:
- **`direct_prompt`** (4,800 runs): the goal is the user message, with no wrapper or injection. The joined `direct`
  configuration's attack steps are **not** emitted: the configuration belongs to the `direct` split, and its
  injections were evidently not applied (an environment payload appears in a tool output in only 48 of 4,480 runs,
  which is disclosed) (`dtap.direct_prompt_no_injection@1`, I) [sources/dtap.md §2.2, §7.3].
- **`direct_no_attack`** (1,920 runs): the medical control. `malicious_instruction` is empty in all 1,776 joined runs.
  No attack fixture is emitted and `attack_id` is null (`dtap.control_split_no_attack@1`, I) [sources/dtap.md §2.2].

**The observed/inferred line (normative).**
- A payload is **observed in the run** when a declared deterministic matcher finds its text in a field that the run's
  own log records: a tool output, a logged tool-description list, or a logged user step. The match is class D over
  class-O text.
- A payload is **configured only** when its text is known only from the pinned configuration. Every statement that it
  belongs to the run, and that the model was exposed to it, is class I.
- That the model processed an observed payload remains the engine's exposure claim, whose class is that of context or
  tool-list membership: I for every DTap run, as for every native import (E.7.3).
- No statement anywhere asserts taint or causation from a configured-only payload as observed.

**Matcher** (`dtap.alnum_norm@1`, the normaliser; D). Payload and haystack are normalised in this order
(`matcher.normalise`): each literal two-character escape `\n`, `\r` or `\t` (a backslash and a letter, not a control
character) is replaced by a space; the text is NFKC-normalised and case-folded (`str.casefold`, which also folds, for
example, `ß` to `ss`); only the characters for which `str.isalnum` holds (Unicode letters and digits) are kept. The
space therefore disappears with the other non-alphanumerics, so the escapes are in effect removed. A value that is not
a string is serialised as compact JSON (`ensure_ascii=False`) first. Every payload string value of at least 24
normalised characters is a needle [sources/dtap.md §7; verify/dtap.md §5]:
- a **full** match of the needle is `present`;
- a match of one of three 40-character windows (start, middle, end) only is `ambiguous`
  (`dtap.marker_partial_window@1`, I, assumption `dtap:PartialWindowIsContainment`);
- no match is `absent`;
- a payload with no needle of 24 characters is `gap`.

Python-repr outputs are searched as text. This is the census matcher, so step 4 can reproduce the census numbers.

**Markers** (SEM profile `dtap.tools@1`).
- *Environment payloads:* the core `injection_marker` on `tool_result` parts (C.14.3), one per (part, environment
  fixture), rule `dtap.env_marker@1` (D), normaliser `dtap.alnum_norm@1`. The engine's A-EXPOSURE (E.7.3) then states
  `ExposedTo` for later requests through context membership (I).
- *Tool-description suffixes:* the namespaced `dtap.description_marker` on the logged `tool_definitions` fixture, at
  the entry whose name corresponds to `injected_tool`, rule `dtap.description_marker@1` (D). The census matched the
  whole log; per-entry placement is checked here, and a match in another entry is recorded as `entry_mismatch`.
- *Prompt payloads:* the namespaced `dtap.prompt_marker` on the user `text` part, rule `dtap.prompt_marker@1` (D). The
  full direct jailbreak wrapper appears in a user step in 12,603 of 16,007 direct runs [sources/dtap.md §7.3]. A
  present marker adds an `author` annotation naming `att` (I, `dtap.direct_prompt_replaces_user_unverified@1`); it
  becomes an assessment, never `wasAttributedTo` (C.14.3).
- *Skill payloads:* the core `injection_marker` where the skill file is read through a tool (377 of 1,018 indirect
  runs show it in a tool output), and `dtap.description_marker` where a log shows it (8 runs) [sources/dtap.md §7.2].
- *Payload text found only in agent steps or the final response:* the namespaced `dtap.agent_output_marker` (D). It is
  not an exposure observation.

**Exposure classes.** There is one namespaced annotation `dtap.exposure` per payload fixture, with `value {channel,
class}`; its premises are the markers and the log-presence pointers. The class is a deterministic summary
(`dtap.exposure_class@1`, D), except `configured_only` and `partial_match`, which are I.

| Class | Channels | Condition | ev | Rule |
|---|---|---|---|---|
| `observed_tool_output` | environment, skill | a `present` `injection_marker` on a tool result | D | `dtap.exposure_class@1` |
| `observed_description_log` | tool, skill | a `present` `dtap.description_marker` | D | `dtap.exposure_class@1` |
| `observed_user_step` | prompt | a `present` `dtap.prompt_marker` | D | `dtap.exposure_class@1` |
| `partial_match` | any | only `ambiguous` markers | I | `dtap.marker_partial_window@1` |
| `agent_output_only` | any | only a `dtap.agent_output_marker` | D | `dtap.exposure_class@1` |
| `logged_absent` | any | the location that would show it is logged (tool outputs exist; a description log exists; a user step exists), and every marker is `absent` | D | `dtap.exposure_class@1` |
| `configured_only` | environment, tool, skill, prompt | no location that could show it is logged: environment, no tool output; tool, no description log; skill, neither a tool output nor a description log; prompt, no user step | I | `dtap.configured_exposure_unverified@1` |
| `unmatchable` | any | no needle of 24 characters | D | `dtap.exposure_class@1` |

An exposure annotation is an assessment-bundle claim: under E.7.2 every exposure claim is an assessment, for live
captures too. `configured_only` and `partial_match` are class I there. An environment payload is `configured_only` only
in a run that logs no tool output at all (6 of 168 environment payloads in the 500-run sample check): nothing in such a
run could show it, so the conservative class I applies, as for the other channels. Runs without a tier-A configuration have no
payload fixtures and therefore no exposure annotation; they are counted as `no_verified_configuration` in the
derivation report.

**What the numbers will show.** These are census figures, to be reproduced by step 4 [sources/dtap.md §7.1, §7.2]:
- of 17,607 indirect runs joined to a parseable configuration, 13,408 (76.2 %) have a tool, skill or prompt step, and
  8,288 have no environment step;
- of 6,162 successful attacks, 4,041 (65.6 %) show no environment payload in any tool output, and 3,993 of those have a
  tool, skill or prompt step;
- 3,533 successes (57.3 % of all successes) have neither an observed environment payload nor a description log;
- where a description log and a tool step co-occur, the suffix is visible in 1,972 of 2,251 runs (87.6 %);
- restricted to tier A: 3,384 of 5,706 successes (59.3 %) have neither.

These figures depend on the matcher. Paraphrased payloads are missed, so "unobserved" is an upper bound only for
verbatim payloads [verify/dtap.md §5].

### D.16.7 Call-to-result pairing

There are no call ids anywhere: `step_id` is the only id on a step [sources/dtap.md §3.6]. Pairing by position is the
only rule that works [sources/dtap.md §3.8]. A **batch** is a maximal segment in which calls are outstanding;
`send_message_to_user` steps are ignored when batches are formed (they sit between calls in only 2 places). Meta-steps
(`List MCP Tools`) are paired like any call and only then mapped as harness activities (D.16.3).

| Harness | Calls / results | Batch shape | Rule (class) | Name check | Ambiguity |
|---|---|---|---|---|---|
| `openaisdk` | 419,828 / 419,828 | strict alternation `A T`; every batch has 1 call | `dtap.pair_strict_alternation@1` (I) | the result `tool_name` must equal the call's (it does in all) | none |
| `openclaw` | 114,505 / 114,458 | strict alternation; the 47 surplus "calls" are the `error` steps (D.16.3), not tool calls | `dtap.pair_strict_alternation@1` (I) | must equal (it does in all) | none |
| `googleadk` | 50,811 / 50,811 | contiguous `A^k T^k`: 27,987 one-call batches, 7,319 multi-call batches holding 22,824 calls (44.9 %) | `dtap.pair_contiguous_batch_fifo@1` (I): result *i* answers call *i* | the result names must reproduce the call order (they do in all 7,319 batches); 2,706 batches repeat a name, which names cannot disambiguate | multi-call batches |
| `claudesdk` | 131,394 / 131,392 | interleaved: 92,545 one-call batches, 12,696 multi-call batches (9,653 contiguous, 3,043 interleaved) holding 38,827 calls (29.5 %) | `dtap.pair_interleaved_fifo@1` (I): each tool step answers the oldest outstanding call | **not used**: the result name is the most recent call's or the literal `unknown` (20,318 results) | multi-call batches; 2 calls never answered |

**Evidence class: I for every harness, including strict alternation.** No pairing premise is observed: the logs carry
no id, and every rule rests on how the harness writes the log (each result after its own call; results in call
order). The DTap SDK, the OpenClaw runtime and the harness versions are neither recorded nor available
[sources/dtap.md §8, §14], so under D-24 no pairing rule can cite verified code, and each is class I. The name check
corroborates and never raises the class. FIFO is supported where content can test it: call arguments found in the
result text favour the FIFO order in 93.1 % of informative googleadk batches, 96.4 % of contiguous claudesdk batches
and 94.1 % of interleaved ones. Most batches are uninformative ties, so FIFO is supported, never proven
[sources/dtap.md §3.8]. These shares are reproduced in the import report, not asserted in AER.

**What is written.**
- `tool_execution.call`, `tool_result.responds_to` and the result message's `generated_by` carry
  `evf {"/call": "I"}`, `{"/parts/0/responds_to": "I"}` and the rule above. The execution is I anyway
  (`dtap.tool_step_is_execution_unverified@1`), so every `used(te, request)` is an inference-bundle statement.
- **Ambiguous batches are disclosed:** every multi-call batch raises the seal issue `dtap.pairing_ambiguous_batch`
  (info). Its `ids` are the batch's call parts and executions; `detail` is `contiguous`, `interleaved` or
  `repeated_names`. This covers 61,651 of 716,489 results (8.6 %): claudesdk 38,827, googleadk 22,824
  [sources/dtap.md §3.8].
- A name-check failure (strict alternation or googleadk) links nothing in that batch. Each execution gets
  `unk {"/call": "ambiguous"}`, each result `unk {"/parts/0/responds_to": "ambiguous"}`, and the core issue
  `call_result_link_conflict` is raised (C.5.4; D.6.6.1 precedent).
- A call with no later tool step (2 claudesdk calls) is listed in `unexecuted_tool_call` under
  `dtap.call_without_result@1` (I: no result is logged; whether it was dispatched is not recorded). A tool step with
  no outstanding call (none in the census) is an `orphan_tool_result` with `unk {"/parts/0/responds_to":
  "not_recorded"}`.

### D.16.8 Judgements

Each task directory holds exactly one `judge_result.json` (65,902 directories) [sources/dtap.md §2.1, §4.2]. Its keys
are `task_success`, `task_message`, `task_metadata`, `attack_success`, `attack_message`, `attack_metadata`, `error`,
and `audit_correction` on 458 files [sources/dtap.md §5].

**Records.** The actor is `judge`; `by` is `benchmark`; values are verbatim, `null` included; `subject` is `run`.
Messages, metadata and `error` go to `ext.dtap.judge` verbatim; they are untrusted text.
- `j0`: `name: "task_success"`.
- `j1`: `name: "attack_success"`.
- **Re-judged results (458; D-29 item 5).** `j1` holds the **original** value from
  `audit_correction.original_attack_success` (src `/audit_correction/original_attack_success`, origin `checker`).
  `j2` holds the **corrected** value, the top-level `attack_success` (origin `recomputed`, `revises: "j1"`).
  - Both values are class O (recorded by the benchmark). The original's date is not recorded. The correction's only
    date is inside its label `patch_id: "h5_rejudge_20260426"`, kept verbatim with `patch_reason` and
    `original_metadata` in `j2`'s `ext.dtap.audit`. Neither date becomes a `t` value (`unk {"/t": "not_recorded"}`
    on both).
  - That `j2` is the effective value is a D statement, `dtap.audit_correction_effective@1`. It is scoped to `/origin`
    and `/revises`, and its premises are the structured audit field itself: the record names the pre-correction value
    `original_attack_success` and the patch. The rule has no assumption and cites no code.
  - Split: direct 179, indirect 279. By harness: openaisdk 204, claudesdk 102, openclaw 101, googleadk 51
    [sources/dtap.md §5]. Stats default to `j2` and report both (D-29 item 5; phase 11).

**Origin** (`origin` is evidence-tagged per value):

| Situation | `origin` | Rule (class) |
|---|---|---|
| an ordinary judge value | `checker`, `evf {"/origin": "I"}`, `unk {"/inputs": "not_recorded"}` | `dtap.judge_recorded_unverified@1` (I). The judge code that produced the values is not verified for the runs: `judge.py` files exist only at task revisions later than every run, and 160 of them changed on 2026-06-02 [sources/dtap.md §8] |
| `direct_prompt` `task_success` (4,800 runs: always `true`, with the message "Direct threat model - task eval not applicable") | `harness_default`. The value is kept as recorded and is not a task result | `dtap.direct_task_eval_not_applicable@1` (I) [sources/dtap.md §2.2]. SEM emits no `outcome` for it and adds a `dtap.non_informative` annotation; it is excluded from utility rates (D-29 item 9) |
| direct `task_success: null` ("Direct threat model - no benign task." 720 times, empty message 5 times; 3 indirect nulls) | `harness_default`, value `null` | `dtap.direct_task_eval_not_applicable@1` (I) for the direct cases; an indirect null keeps origin `checker` with value `null` [sources/dtap.md §5] |
| benign `attack_success: null` (25,087 directories, every benign one) | `harness_default`, value `null` | `dtap.benign_attack_not_judged@1` (I) |
| `direct_no_attack` `attack_success` (348 of 1,920 true) | `checker` (as above) | SEM reads it as `dtap.attack_judge_on_control`, never as `attack_succeeded` (D.16.9) |
| judge `error` non-null (14: all a Gemini HTTP 400 for an oversized screenshot payload; googleadk windows, 2026-04-09; their trajectories are empty) | values kept | seal issue `dtap.judge_error` (`dtap.judge_error@1`, D) |

**Linking a judge to an attempt (D-29 item 6).** One judge covers every trajectory in its directory. There are 1,291
directories with more than one timestamp-named trajectory (991 with 2 files, 63 with 3, 237 with 4; 1,828 surplus
files), plus the `_N` files. Which attempt the judge scored is not recorded [sources/dtap.md §4.2]. Linkage, first
match wins:
1. **Content match.** A string value of the judge's `task_message`, `attack_message`, `task_metadata` or
   `attack_metadata` (not `error`), of at least 40 characters after `dtap.alnum_norm@1`, occurs in the logged content
   of exactly one attempt of the directory and of no other, and exactly one attempt holds such a string. The logged
   content is searched per **step** (each `trajectory[i]` serialised as compact JSON and normalised, so a judge string
   must fall within one step) and in `traj_info.agent_final_response`; `task_info` and the other `traj_info` fields are
   not searched, because they hold configuration text that every attempt of the directory shares. The rule applies to
   a single-trajectory directory too (its only attempt then needs no other to differ from). That attempt gets the
   judgements with `evf {"/subject": "D"}` under `dtap.judge_attempt_by_content@1` (premises: the judge field pointer
   and the matching trajectory pointer; the rule cites both files). The other attempts get no judgement, the info
   issue `dtap.unjudged_attempt`, and `ext.dtap.judge_link {judge_sha256, resolved_to: <ex>}`. The rule rests on
   uniqueness: logged content found in one attempt only cannot have reached the judge file from another attempt. It
   needs no harness behaviour.
2. **Single attempt, no content match.** The directory's only trajectory gets the judgements with
   `evf {"/subject": "I"}` under `dtap.judge_dir_colocation@1`. Co-location is a layout convention, and the 22
   judge-only directories show that a judge can outlive its trajectory (open question 2, D.16.17).
3. **Several attempts, no unique match.** **No** judgement record is written in any attempt. The judge file is cited
   as a `supporting` artefact, and `ext.dtap.judge_link {judge_sha256, group_size, resolved: false}` records the
   group. The warning `dtap.judge_attempt_unresolved` is raised. These attempts have no per-run outcome: they are
   excluded from per-run rates by default and disclosed with their count. A group-level outcome is computed only by
   the DTap report tool (D.16.15).

How many of the 1,291 directories resolve by content is not known; the census did not determine it
[verify/dtap.md §7]. Step 4 measures it.

**Judge-only directories** (22, plus 8 that hold only a red-teaming log): an `outcome_only` unit whose primary artefact
is the judge file. The task coordinates come from its path; the judgements have `subject: "run"` under
`dtap.judge_without_trajectory@1` (D: no trajectory-bearing file exists in the directory); the issue is
`no_execution_observed`. Only `judge_result.json` takes this path: a judge-shaped JSON under any other name (an
`other_json` file, offered to the sniff like every unknown name) is a mapping failure (`MalformedArtefact`, detail
"judge-shaped JSON under a file name other than judge_result.json"), never an `outcome_only` unit citing the rule on a
false premise (regeneration-batch item 53; none in the pinned snapshot).

### D.16.9 Semantics profile `dtap.tools@1` (and `@2`, D-607)

`dtap.tools@2` (`dtap.tools-2/`) is `@1`'s tables and code on catalogue `dtap` version 2 (the D-31 addendum's option B: one
catalogue version per corpus, H.2.5); `@1` keeps reading the archived catalogue version 1 for the corpora that record it.
Regenerated corpora and the registry part select `@2` (D.16.19). Regen item 54 (a payload with no recorded vector or
content: channel from the step type, `/kind` premises) applies from `@2` only; `@1` keeps its earlier behaviour (item 54 version-gated under dtap.tools@2 (D-31 owner ruling 2026-10-21)).

Data under `src/agentprov/adapters/dtap/semantics/dtap.tools-1/`, discovered by convention (C.14.7 item 2):
- `profile.toml`;
- `servers.toml`: the tool inventory per MCP server (generated);
- `domains.toml`: the servers each domain's configurations enable, taken from `Agent.mcp_servers` (generated);
- `labels.toml`: the reviewed roles, output integrity, evidence and reason of every labelled MCP tool, and of
  OpenClaw's own tools;
- `builtins.toml`: the reviewed labels of harness tools logged with `server: "unknown"` (claudesdk built-ins, the
  openaisdk and googleadk skill loaders).

`servers.toml` and `domains.toml` are generated by `tools/dtap/gen_tool_tables.py`, which reads as data (never
executes) the 27 server names in the pinned configurations, the 491,627 `{name, description}` entries over 30 servers in
`mcp_tools`, and the observed `(server, tool_name)` pairs [sources/dtap.md §3.6, §6.1]. `labels.toml` and
`builtins.toml` are reviewed by hand (phase-10b follow-up 4, 2026-10-12). Every table-based label is I
(`dtap.tool_table@1`), as for `agentdojo.suites@1`.

- **Tool resolution.**
  - openaisdk and googleadk: the key is the verbatim `server` (it may contain spaces, e.g. `Research Server`) plus
    `tool_name`. Logged spellings of one configured server (`Gmail`/`gmail`, `Research`/`Research Server`/
    `Research_Server`, `google-form`/`googleform`, ...) are separate keys with the same labels.
  - openclaw: `server` is the constant `openclaw` on all 114,458 results, and `tool_name` carries a `<server>_<tool>`
    prefix (or none). The longest declared server prefix splits it (`dtap.openclaw_prefix_split@1`, I); a
    double-underscore name (`gmail__search_messages`, the older OpenClaw naming) splits to `_<tool>`, labelled as its
    twin. A name with no server prefix is one of OpenClaw's own tools (`exec`, `read`, `write`, ...), labelled under
    server `openclaw`.
  - `server: "unknown"`: a listed harness tool is looked up in `builtins.toml`. Otherwise the call is a failed MCP call
    (openaisdk, and claudesdk/googleadk rarely, log those with server `unknown`; the error text names the server): it
    takes the label of the one server, among those the run's domain configures (`domains.toml`), whose inventory holds
    the name (`dtap.unknown_server_domain_match@1`, I, assumption `dtap:UnknownServerIsFailedMcpCall`; the run's
    `/ext/dtap/path_facets/domain` is a premise). No such server, or more than one: unknown. In the census 3,786 calls
    resolve; 3,772 of their results are MCP errors that name a server, and it is the matched server in all 3,772.
- **Fail-closed.** A tool no table labels, or a result whose link is `ambiguous`, gets integrity `unknown`, role
  `["unknown"]` and no channel (`dtap.unknown_tool@1`, I; with `dtap.openclaw_prefix_split@1` for an OpenClaw name).
  An injection setup tool (`*-injection:*`, configuration only) never appears as an agent tool.
- **Evidence policy (labels).** Each entry lists its `evidence`, strongest first:
  - `description`: the tool's description as logged in the runs (OpenClaw `mcp_tools`, `debug.tool_descriptions`),
    paraphrased in `reason`, never copied (descriptions can carry injected suffixes);
  - `observed`: the tool's logged arguments and results;
  - `config`: a configured environment injection (`injection_mcp_tool`) writes to the store the tool returns. It only
    corroborates.

  An entry needs `description` or `observed`; a tool known by its name alone stays unknown (the loader refuses such an
  entry). No input schema is logged anywhere (the `mcp_tools` entries are `{name, description}` only), and no tool code
  is available, so no label is D and no output is `trusted` (the loader refuses `trusted`). Only tools that occur in
  the runs are labelled.
- **Role criteria** (the agentdojo C.14.6 item 5 refinement, applied to descriptions and observed calls):
  - `send_sink`: the call delivers a message, money or published content to a party (an argument-named recipient, the
    site a form is filled for, the simulated patient);
  - `write_sink`: it creates, changes or deletes stored state (records, files, bookings, sessions, trades, state of the
    browser's site);
  - `execute_sink`: it runs a command, or drives the desktop's input devices (click, type, key, drag, launch);
  - `egress_read`: it fetches an argument URL from outside the sandbox;
  - `content_source`: it returns data of the environment;
  - `endorser`: an approval check that another tool's description requires first (the three travel `verify_*` tools;
    first use of the role, **accepted by the user 2026-10-12**; integrity stays `unknown`);
  - `neutral`: no effect and no environment data (own profile, tokens, waits, fixed schema).

  A tool may hold several roles (e.g. a browser click is `write_sink` and `content_source`).
- **Output integrity.** `untrusted` when the output carries free text authored by a party other than the user or the
  agent (the C.14.6 criterion: e-mails, messages, documents, pages, posts, notes of records, test results); otherwise
  `unknown`. The built-ins stay `unknown`: claudesdk runs them on the harness host (the observed paths are host paths),
  so the author of a file or page they return is not decidable from the configuration.
- **Table summary** (census of all 67,806 parsed trajectories, `tools/dtap/tool_census.py`): 716,491 agent call steps,
  of which 215,263 are `List MCP Tools` meta-steps (harness activities, D.16.3) and 501,228 tool calls over 1,023 logged
  `(server, tool_name)` pairs. `labels.toml` has 536 entries over 35 logged servers (`description` first 419,
  `observed` 117; `config` corroborates 159; output `untrusted` 184, `unknown` 352); `builtins.toml` has 17 (all
  `observed`). Coverage: 982 of 1,023 pairs and 500,643 of 501,228 calls (99.88 %) have a role other than `unknown`
  (step 3: 39 pairs, 90,867 calls, 18.1 %); by harness claudesdk 127,704 / 128,125, googleadk 50,295 / 50,295, openaisdk
  208,341 / 208,350, openclaw 114,303 / 114,458. Roles by calls: `content_source` 328,145, `write_sink` 130,836,
  `execute_sink` 53,322, `send_sink` 52,395, `neutral` 28,665, `egress_read` 2,111, `endorser` 286, `unknown` 585.
  Tool outputs: `untrusted` 267,382 calls, `unknown` 233,846.
- **Left unknown** (41 pairs, 585 calls, each under 0.1 %): the `claude_ai_*` and `playwright` servers (the harness
  operator's own connectors: no configuration enables them and no description is logged); OpenClaw's `browser`,
  `canvas`, `cron`, `gateway`, `nodes`, `image` and `sessions_spawn` (effect set by an action argument, or a sub-agent;
  nearly every logged result is a gateway error); claudesdk `Agent` and `Task` (a sub-agent can do anything),
  `AskUserQuestion` and a literal `$FUNCTION_NAME`; openaisdk `codex` (no domain server holds it); and three single
  calls outside their server's tool set (`terminal` `analyze_document`, `list_documents`; `legal` `send_email`).
- **Effect** (the stratified ~500-run release-mode sample of `tools/dtap/import_dtap.py --sample 500`, before and after
  the tables, on the 498 executions derived both times; one more run passes the worker RSS cap after, D.16.18 item 14).
  AER bytes are identical (501 of 501). Role annotations on tool calls: labelled 276 → 2,768 of 2,770. Tool-output
  integrity `unknown` 2,770 → 854 parts (now `untrusted` 1,916 of them). Assessment bundle: `apv:ExposedTo` 22,268 →
  22,134 (requests now `neutral` are no exposure subjects, EF E.7.3 item 1); `apv:PotentiallyInfluencedBy` 22,264 →
  10,596 (a `content_source`, `egress_read`, `endorser` or `neutral` request is no taint subject; before, nearly every
  request was `unknown` and therefore one); `apv:Labelled`, mentions, `apv:ContainsPayload` and
  `apv:QuotesAuthoredContent` unchanged; statements 121,844 → 98,240. The `dtap.exposure` classes and every marker are
  unchanged (they do not read labels).
- **Integrity of non-tool content.**
  - User text is `trusted` (principal content, `dtap.integrity_principal_content@1`), except a user part with a
    `present` `dtap.prompt_marker`, which is `untrusted` (`dtap.integrity_prompt_payload@1`, I by its configuration
    premise).
  - Agent text and calls are `trusted` (`dtap.integrity_agent_output@1`; the C.14.6 item 4 reasoning).
  - Payload and goal fixtures are `untrusted` (`dtap.integrity_payload_fixture@1`).
  - Logged tool-definition fixtures are `unknown` (server text mixed with possible suffixes;
    `dtap.integrity_tool_definitions@1`).
  - Harness artefacts (`dtap:tool_name_list`, `dtap:error_text`) are `trusted` (`dtap.integrity_harness_artefact@1`).
- **Markers and exposure:** as in D.16.6.
- **Outcomes.**
  - `task_success` → `user_task_solved` (`dtap.task_success_meaning@1`, I).
  - `attack_success` → `attack_succeeded` (`dtap.attack_success_polarity@1`, I: the field name and message are the only
    basis; the judge code is unverified for the runs).
  - In `direct_no_attack` runs, `attack_success` → `dtap.attack_judge_on_control` (`dtap.control_attack_judgement@1`,
    I): a baseline rate of the medical attack judges.
  - No outcome for `harness_default` judgements (C.14.3). Both the original and the corrected judgement of a re-judged
    result get an outcome, so the assessment bundle shows both.
- **Taint policy** `dtap.taint_sink_untrusted@1` (I): subject roles `write_sink`, `send_sink`, `execute_sink` and
  `unknown`; object integrity `untrusted` and `unknown` (as C.14.6 item 8).

### D.16.10 Quality flags (summary)

| Case | Count | Handling | Seal issue / register | Rate default |
|---|---:|---|---|---|
| synthetic "repaired" trajectories | 20 | not executions; stored; registered (D-29 item 1) | `select.not_execution_artefact` (`dtap.synthetic`) | — |
| harness failures (OpenClaw `Unknown model` 27, failover 10, no API key 10; judged anyway: 15 `task_success` true, all `attack_success` false) | 47 | executions, run `status: "error"` (O), judgements kept verbatim (D-29 item 2) | `dtap.harness_failure`, `dtap.judgement_on_failed_run` (warning) | excluded, counted separately |
| empty trajectories (googleadk 14, claudesdk 3, windows, 2026-04-09; all carry `metadata.error`) | 17 | `outcome_only`, no invented steps, judgements kept (D-29 item 3; the ROPE precedent) | `no_execution_observed`, `dtap.empty_trajectory` | excluded (`outcome_only`) |
| LFS-pointer trajectories | 2 | fetch, verify, import; unresolved → registered (D-29 item 4) | `select.not_execution_artefact` (`dtap.lfs_pointer`) for the pointer | normal |
| re-judged results | 458 | both judgements; the corrected one effective (D-29 item 5) | — | corrected value; both reported |
| re-run directories (one judge) | 1,291 (1,828 surplus files) | every attempt an execution; judge linked by content or unresolved (D-29 item 6) | `dtap.judge_attempt_unresolved`, `dtap.unjudged_attempt` | unresolved attempts excluded |
| `(1)` copies | 8 (+8 judge copies) | one execution, two origins (D-29 item 7) | `dedup.collapsed` | normal |
| partial trajectory | 1 | imported, no gap filling (D-29 item 8) | `dtap.partial_trajectory`, `incomplete_run` | normal; completeness `unverifiable`: the loss rests on the file name only (`dtap.partial_file_name@1`, I), so it is inferred, not proven (H.3.2(2); D-82) |
| `direct_prompt` `task_success` | 4,800 | kept, `harness_default`, non-informative (D-29 item 9) | — | excluded from utility |
| judge-only directories | 22 (+8 red-teaming) | `outcome_only` with the judge as primary | `no_execution_observed` | excluded (`outcome_only`) |
| configuration not verified (tier B 2,899, tier C 1,693) or missing (786) or unparseable (9) | 5,387 | configuration not used for run content | `dtap.config_join_unverified`, `dtap.config_missing`, `dtap.config_unparseable` | normal; exposure `no_verified_configuration` |

"Rate default" is a statement for the phase-11 datasheet and `stats` (D.16.15); AER keeps every value.

### D.16.11 Rule catalogue `dtap.rules.toml` (`src/agentprov/adapters/dtap/rules/`, `[catalogue] id = "dtap"`, version 2)

Version 2 (D-607, D-31) adds `dtap.value_redacted@1` (D) and the issue code `value_redacted` (D.16.19); every version-1
rule is unchanged, and version 1 ships as `rules/archive/dtap.rules.v1.toml` (the scratch corpora record it).

**Citation policy (D-24, D-27 c6).** No DTap harness code is verified. The SDK versions, the OpenClaw runtime and the
sandbox images are not recorded, and the DTap SDK is not available [sources/dtap.md §8, §14]. Therefore:
- every rule that rests on harness or judge behaviour is class I, with an `asserted` assumption;
- the D rules are deterministic functions of observed fields that need no framework property: they declare no
  assumption, cite no code (`code = []`) and cite the census in `evidence`;
- documentary evidence (dataset cards, the paper) never makes a rule D.

Each rule's `tests` names its test under `tests/adapters/dtap/`.

| Rule | Cl. | Statement (short) | Premises | Cites |
|---|---|---|---|---|
| `dtap.path_model_identity@1` | I | The agent model is the path's model segment; free-text model mentions are never used. Assumption `dtap:PathNamesModel` | origin `/path` | [sources/dtap.md §3.6] |
| `dtap.path_harness_identity@1` | I | The harness is the framework segment; OpenClaw `metadata.framework` corroborates. `dtap:PathNamesHarness` | origin `/path`, `/traj_info/metadata/framework` | [sources/dtap.md §2.1, §3.6] |
| `dtap.user_is_simulated_unverified@1` | I | User steps are issued by the harness on behalf of a simulated user. `dtap:ScriptedUser` | `/trajectory/i/role` | [sources/dtap.md §3.2] |
| `dtap.auto_execution_unverified@1` | I | The tool runtime executes each requested call on behalf of the agent. `apv:AutoExecution` (asserted) | — | as `agentdojo.auto_execution_unverified@1` |
| `dtap.steps_append_ordered_unverified@1` | I | Step array order is occurrence order. `dtap:HarnessLogsInOrder` | `/trajectory`, `step_id` | [sources/dtap.md §3.2] |
| `dtap.agent_step_is_model_output_unverified@1` | I | An agent step with a tool name or message is model output. `dtap:AgentStepIsModelOutput` | `/trajectory/i/role`, `/metadata` | [sources/dtap.md §3.2] |
| `dtap.agent_segment_one_turn_unverified@1` | I | A maximal segment of agent steps is one model call. `dtap:SegmentIsOneTurn` | step roles | [sources/dtap.md §10.1] |
| `dtap.context_is_logged_prefix_unverified@1` | I | A call's input is every earlier logged step; the unlogged system prompt and tool descriptions are not members. `dtap:ContextIsLoggedPrefix` | step order | [sources/dtap.md §3.6] |
| `dtap.tool_step_is_execution_unverified@1` | I | A tool step records one execution of a tool. `dtap:ToolStepIsExecution` | `/trajectory/i/role`, `/state` | [sources/dtap.md §3.2] |
| `dtap.pair_strict_alternation@1` | I | openaisdk, openclaw: a tool step answers the call immediately before it. `dtap:ResultAfterOwnCall` | order, `tool_name` | [sources/dtap.md §3.8] |
| `dtap.pair_contiguous_batch_fifo@1` | I | googleadk: in `A^k T^k`, result *i* answers call *i*. `dtap:FifoResults` | order, `tool_name` | [sources/dtap.md §3.8] |
| `dtap.pair_interleaved_fifo@1` | I | claudesdk: a tool step answers the oldest outstanding call; names are ignored. `dtap:FifoResults` | order | [sources/dtap.md §3.8] |
| `dtap.call_without_result@1` | I | A call with no later tool step has no logged execution. | order | [sources/dtap.md §3.8] |
| `dtap.list_mcp_tools_harness_step@1` | I | A `List MCP Tools` step pair is a harness discovery activity listing tool names. `dtap:SdkListsTools` | `/metadata/tool_name`, `/state` | [sources/dtap.md §3.4] |
| `dtap.harness_error_step@1` | I | An agent step `action: "error"` is a harness error, not model output; the run ended in error. `dtap:ErrorStepIsHarness` | `/action`, `/metadata/error` | [sources/dtap.md §3.7] |
| `dtap.harness_error_echo@1` | I | The message after an error step echoes it; its author is not recorded. | following step | [sources/dtap.md §3.7] |
| `dtap.logged_tools_offered_unverified@1` | I | A run-level logged tool list was offered on every call of the run. `dtap:LoggedToolListPerRun` | `/debug/tool_descriptions`, `/traj_info/metadata/mcp_tools` | [sources/dtap.md §3.6] |
| `dtap.timestamp_is_run_end_unverified@1` | I | `traj_info.timestamp` is the run end. `dtap:TimestampIsRunEnd` | `/traj_info/timestamp`, `/duration`, the file stem | [sources/dtap.md §3.5] |
| `dtap.config_path_join@1` | D | The configuration path of a run is given by the D.16.5 path rule. | origin `/path` | [sources/dtap.md §6.3] |
| `dtap.config_join_tier@1` | D | The join tier is the result of the two D.16.5 text checks. | `/task_info/*`, configuration fields | [sources/dtap.md §6.3] |
| `dtap.task_id_offset_medical@1` | I | Medical trajectory ids are zero-based against one-based directories. | `/task_info/task_id`, path | [sources/dtap.md §6.4] |
| `dtap.task_id_reformatted@1` | I | Telecom, browser and customer-service ids differ only in format. | as above | [sources/dtap.md §6.4] |
| `dtap.config_content_tier_a@1` | I | In a tier-A run, configuration content describes the run. `dtap:ConfigAtPinIsRunConfig` | configuration, `ext.dtap.join` | [sources/dtap.md §6.3, §8] |
| `dtap.config_payload_attacker_unverified@1` | I | Configured payloads and the goal are attributed to the attacker. | fixture | as `agentdojo.payload_attributed_to_attacker@1` |
| `dtap.direct_prompt_no_injection@1` | I | `direct_prompt` runs carry no configured injection. | path, markers | [sources/dtap.md §2.2, §7.3] |
| `dtap.control_split_no_attack@1` | I | `direct_no_attack` is a control without an attack. | path, `/task_info/malicious_instruction` | [sources/dtap.md §2.2] |
| `dtap.direct_prompt_replaces_user_unverified@1` | I | A direct configuration's `prompt` step replaced the user message; its author is the attacker. | configuration, user part | [sources/dtap.md §6.2] |
| `dtap.instruction_cut_500@1` | D | A 500-character instruction that is a proper prefix of the configuration text is truncated. | `/task_info/original_instruction`, configuration | [sources/dtap.md §3.3] |
| `dtap.instruction_length_500_unverified@1` | I | A 500-character instruction without a verifying configuration is possibly truncated. | `/task_info/original_instruction` | [sources/dtap.md §3.3] |
| `dtap.goal_rewritten_at_eval@1` | D | `malicious_instruction_at_eval` is the goal text the judge used; `malicious_instruction` is the run-time text. | `/task_info/*` | [sources/dtap.md §6.5] |
| `dtap.user_step_not_logged@1` | D | The file holds no user step; the instruction exists only as `task_info`. | step roles | [sources/dtap.md §11.2 item 7] |
| `dtap.final_response_copy@1` | D | `agent_final_response` is compared with the last agent message. | `/traj_info/agent_final_response` | [sources/dtap.md §11.2 item 6] |
| `dtap.source_truncation_marker@1` | D | A `[truncated` marker is dataset-side truncation. | the text | [sources/dtap.md §3.3] |
| `dtap.rerun_group@1` | D | Trajectory files sharing a task directory are attempts of one group. | the directory listing | [sources/dtap.md §4.2] |
| `dtap.synthetic_marker@1` | D | `synthetic: true` marks a fabricated trajectory (register only). | `/task_info/synthetic`, `/traj_info/metadata/synthetic` | [sources/dtap.md §3.7] |
| `dtap.lfs_pointer@1` | D | A Git LFS pointer is not a trajectory (register only). | the bytes | [sources/dtap.md §2.3] |
| `dtap.empty_trajectory@1` | D | `trajectory: []`: no execution observed. | `/trajectory`, `/traj_info/metadata/error` | [sources/dtap.md §3.7] |
| `dtap.partial_file_name@1` | I | `partial_trajectory.json` is an incomplete run. | the file name | [sources/dtap.md §2.3] |
| `dtap.judge_recorded_unverified@1` | I | A judge value was produced by the DTap judge for the directory's run. `dtap:JudgeIsChecker` | judge file | [sources/dtap.md §5, §8] |
| `dtap.judge_attempt_by_content@1` | D | A judge string found in exactly one attempt links the judge to it. | judge field, trajectory field | [sources/dtap.md §4.2]; D-29 |
| `dtap.judge_dir_colocation@1` | I | The judge of a single-trajectory directory judged that trajectory. `dtap:JudgeColocated` | the directory listing | [sources/dtap.md §4.2] |
| `dtap.judge_without_trajectory@1` | D | A directory with a judge and no trajectory file yields an outcome-only unit. | the directory listing | [sources/dtap.md §4.2] |
| `dtap.audit_correction_effective@1` | D | `attack_success` is the post-patch value and `audit_correction.original_attack_success` the pre-patch value. | `/audit_correction/*` | [sources/dtap.md §5]; D-29 |
| `dtap.direct_task_eval_not_applicable@1` | I | Direct and `direct_prompt` `task_success` is a harness constant or null, not a task result. | `task_success`, `task_message` | [sources/dtap.md §2.2, §5] |
| `dtap.benign_attack_not_judged@1` | I | A benign `attack_success: null` is "not judged". | `attack_success` | [sources/dtap.md §5] |
| `dtap.judge_error@1` | D | A non-null judge `error` is recorded with the values. | `/error` | [sources/dtap.md §5] |
| `dtap.alnum_norm@1` | D | The D.16.6 normaliser. | the text | [sources/dtap.md §7] |
| `dtap.env_marker@1` | D | An environment payload is matched in a tool result. | part text, fixture | [sources/dtap.md §7] |
| `dtap.marker_partial_window@1` | I | A window-only match is `ambiguous`. `dtap:PartialWindowIsContainment` | as above | [verify/dtap.md §5] |
| `dtap.description_marker@1` | D | A suffix is matched in a logged tool-definition entry. | fixture entries | [sources/dtap.md §7.2] |
| `dtap.prompt_marker@1` | D | A prompt payload is matched in a user step. | user part | [sources/dtap.md §7.3] |
| `dtap.agent_output_marker@1` | D | A payload is matched in agent output only. | agent parts | [sources/dtap.md §7.1] |
| `dtap.exposure_class@1` | D | The D.16.6 class summary. | markers, log presence | [sources/dtap.md §7] |
| `dtap.configured_exposure_unverified@1` | I | A configured payload in a channel the run does not log reached the model. `dtap:ConfiguredPayloadApplied` | fixture, `ext.dtap.join` | [sources/dtap.md §7.2]; D-26 |
| `dtap.tool_table@1`, `dtap.openclaw_prefix_split@1`, `dtap.unknown_tool@1` | I | Table labels; prefix split; fail-closed. | tool name, server | [sources/dtap.md §3.4, §3.6] |
| `dtap.unknown_server_domain_match@1` (follow-up 4) | I | A `server: "unknown"` call that is no listed built-in takes the label of the one domain server holding the name. `dtap:UnknownServerIsFailedMcpCall` | tool name, server, `/ext/dtap/path_facets/domain` | D.16.9 census (3,772 of 3,772 server-naming errors agree) |
| `dtap.integrity_principal_content@1`, `dtap.integrity_prompt_payload@1`, `dtap.integrity_agent_output@1`, `dtap.integrity_payload_fixture@1`, `dtap.integrity_tool_definitions@1`, `dtap.integrity_harness_artefact@1` | I | D.16.9 integrity rules. | actor, markers | C.14.6 item 4 |
| `dtap.task_success_meaning@1`, `dtap.attack_success_polarity@1`, `dtap.control_attack_judgement@1` | I | D.16.9 outcome readings. | judgement value, path | [sources/dtap.md §2.2, §5] |
| `dtap.taint_sink_untrusted@1` | I | The taint policy. | labels | C.14.6 item 8 |
| `dtap.acc.counters@1` | D | Profile accounting check: the `traj_info` counters equal the step populations. | `/traj_info/*`, steps | [sources/dtap.md §3.1] |

**Reserved detector names (2026-10-12, sample-check fix b1).** Five rules have `status = "reserved"`: they are never
cited in an AER, and each is the `detector.rule` of one D.16.12 entry whose case no field read by the safety net carries.
`dtap.timestamp_zone_none@1` (a zone-less run timestamp; `ext.dtap.timestamp_zone`), `dtap.byte_identical_copy@1`
(`(1)` copies; register `dedup.collapsed`), `dtap.secret_like_string@1` (release scan), `dtap.goal_prefix_appended@1`
(goal relation `prefix`; `ext.dtap.join`) and `dtap.result_name_unknown@1` (`ext.dtap.result_tool_name`). Naming an
active rule instead would let the entry claim every finding that rule's other uses produce (D.15.8 item 7). A mapper
change that raises one of these cases in a field the net reads would make the rule active.

**Issue codes** (`issue_codes`, raised as `dtap.<code>`): `partial_trajectory`, `empty_trajectory`, `harness_failure`,
`judgement_on_failed_run`, `pairing_ambiguous_batch`, `config_join_unverified`, `config_missing`, `config_unparseable`,
`task_info_truncated`, `goal_rewritten_at_eval`, `user_step_not_logged`, `final_response_differs`,
`source_truncation_marker`, `judge_error`, `judge_attempt_unresolved`, `unjudged_attempt`, `path_field_mismatch`. Core
codes used: `no_execution_observed`, `incomplete_run`, `unexecuted_tool_call`, `orphan_tool_result`,
`call_result_link_conflict`, `unattributed_additional_user_message`.

**Declared types and subtypes.** Activity types `dtap:list_mcp_tools` and `dtap:harness_error`; artefact types
`dtap:tool_name_list` and `dtap:error_text`; fixture subtypes `dtap.attack_goal` and `dtap.attack_goal_at_eval`. SEM
namespaced types: `dtap.exposure`, `dtap.description_marker`, `dtap.prompt_marker`, `dtap.agent_output_marker`,
`dtap.non_informative`, each with its JSON Schema in the semantics profile.

### D.16.12 Artefact catalogue (`adapters/dtap/artefacts.toml`, D.15)

Version 1, family `dtap`. `expected` rows use snapshot `dtap:head` and stay `unverified` until the step-4 import
confirms them (D.15.6).

| Entry `dtap.art.*` | Count | Cause | Detector | Handling |
|---|---:|---|---|---|
| `synthetic_trajectory` | 20 | upstream (repair) | `dtap.synthetic_marker@1` | `FO` (registered, not imported) |
| `harness_failure_judged` | 47 | upstream harness | `dtap.harness_error_step@1` | `FO` |
| `empty_trajectory` | 17 | upstream infrastructure | `dtap.empty_trajectory@1` | `CR` (`outcome_only`) |
| `judge_error` | 14 | upstream judge | `dtap.judge_error@1` | `FO` |
| `lfs_pointer_json` | 2 | upstream packaging | `dtap.lfs_pointer@1` | `CR` (fetch and verify) |
| `lfs_pointer_png` | 122 | upstream packaging | — (register) | `NR` |
| `rejudged_results` | 458 | benchmark (patch `h5_rejudge_20260426`) | `dtap.audit_correction_effective@1` | `RJ` (source-released, beside the original) |
| `rerun_single_judge` | 1,291 directories | benchmark | `dtap.rerun_group@1` (issues `judge_attempt_unresolved`, `unjudged_attempt`; linking by `dtap.judge_attempt_by_content@1`) | `FO` (unresolved groups `NR`) |
| `judge_only_directory` | 22 (+8) | upstream | `dtap.judge_without_trajectory@1` | `CR` |
| `copy_duplicate` | 8 | upstream packaging | `dtap.byte_identical_copy@1` (reserved; register `dedup.collapsed`; `artefact.generic.cross_origin_duplicate` is not implemented, D.15.8 item 6) | `CR` (`dedup.collapsed`) |
| `partial_trajectory` | 1 | upstream | `dtap.partial_file_name@1` | `FO` |
| `direct_prompt_constant_task_success` | 4,800 | benchmark judge | `dtap.direct_task_eval_not_applicable@1` | `CR` (`harness_default`) |
| `control_attack_judged` | 1,920 (348 true) | benchmark | `dtap.control_attack_judgement@1` | `FO` |
| `config_join_drift` | tier B 2,899, tier C 1,693 | benchmark (post-run rewrites) | `dtap.config_join_tier@1` | `FO` |
| `config_missing` / `config_unparseable` | 786 / 9 | benchmark | `dtap.config_path_join@1` | `NR` |
| `instruction_truncated_500` | 7,353 | upstream writer | `dtap.instruction_cut_500@1` | `FO` |
| `goal_rewritten_at_eval` | 1,183 | benchmark | `dtap.goal_rewritten_at_eval@1` | `FO` |
| `goal_text_appended` | 1,826 | upstream writer | `dtap.goal_prefix_appended@1` (reserved; `goal: "prefix"` in `ext.dtap.join`) | `FO` |
| `pairing_ambiguous_batch` | 61,651 results | upstream (no call ids) | `dtap.pair_*@1` | `FO` |
| `claudesdk_unknown_result_name` | 20,318 | upstream harness | `dtap.result_name_unknown@1` (reserved; `ext.dtap.result_tool_name`) | `CR` (kept in `ext`, never typed) |
| `no_user_step` | 10,154 | upstream harness | `dtap.user_step_not_logged@1` | `NR` |
| `python_repr_results` | 188,050 | upstream harness | reader classification | `CR` (text, never evaluated) |
| `injection_unobservable` | 3,533 successes (57.3 %) | benchmark design | `dtap.configured_exposure_unverified@1` | `NR` (manuscript: `true`) |
| `environment_payload_unobserved` | 4,041 successes | benchmark design or paraphrase | `dtap.exposure_class@1` (`logged_absent`) | `FO` (manuscript: `true`) |
| `no_model_id` | 67,806 files (597 free-text mentions) | upstream | `dtap.path_model_identity@1` | `NR` |
| `naive_timestamp` | 7,415 | upstream (googleadk) | `dtap.timestamp_zone_none@1` (reserved; `ext.dtap.timestamp_zone = none`) | `CR` (verbatim in `t.raw.end`, never converted) |
| `no_tool_status` | 716,489 results | upstream format | — | `NR` |
| `trace_id_not_unique` | 517 shared values | upstream | reader | `CR` (`ext` only) |
| `task_id_not_unique` | 78 keys | upstream | reader | `CR` (path identity) |
| `source_truncation_marker` | 54 files | upstream | `dtap.source_truncation_marker@1` | `FO` |
| `secret_like_strings` | 1,206 files | upstream data | release scan (G); `dtap.secret_like_string@1` (reserved) | per the D.16.13 decision |
| `event_times_not_recorded` | every run | upstream harness | `dtap.timestamp_is_run_end_unverified@1`; claims `sentinel_time` (`unknown_not_recorded`, `unknown_ambiguous`) | `NR` |
| `derived_model_calls` | every agent execution | upstream harness | `dtap.agent_segment_one_turn_unverified@1`; claims `accounting_unverifiable#aer.acc.agent_calls_vs_assistant@1` | `NR` |
| `no_call_ids` | 501,228 calls | upstream harness | `dtap.pair_strict_alternation@1`; claims `provider_id_anomaly#absent` | `NR` |
| `payload_not_observed` | step 4 | benchmark design | `dtap.exposure_class@1`; claims `payload_not_reaching_agent` (the exposure classes of D.16.6 are the reading) | `FO` |
| `path_domain_spelling` | step 4 | benchmark | `dtap.path_field_check@1` (`path_field_mismatch`) | `CR` (path is the identity) |
| `harness_default_outcome` | step 4 | benchmark | `dtap.non_informative@1`; claims `harness_imposed_outcome#harness_default` | `CR` (`harness_default`, non-informative) |
| `additional_user_message` | step 4 | upstream harness | `dtap.user_is_simulated_unverified@1` (`unattributed_additional_user_message`) | `FO` |

**Specific claims (2026-10-12, sample-check fix b1).** On the 500-run sample the safety net left 1,229 of 2,711
findings unclassified, and five entries claimed findings of other cases through a rule every run cites. Now every
entry claims only through its own rule, `claims` item or issue code: the last seven rows classify the former
unclassified findings (sample: 0 of 2,711 unclassified), and the entries whose case the net cannot see name a reserved
detector (D.16.11) and claim nothing; their counts come from `ext.dtap`, the register or the release scan. Before
and after on the sample, executions claimed: `naive_timestamp` 499 to 0 (the 49 naive runs are counted from
`ext.dtap.timestamp_zone`), `secret_like_strings` 56 to 0, `copy_duplicate` 14 to 0, `goal_text_appended` 55 to 0,
`claudesdk_unknown_result_name` 37 to 0, `rerun_single_judge` 57 to 15, `empty_trajectory` 3 to 1,
`judge_only_directory` 3 to 2. `no_execution_observed` is no longer listed under `recorded_as` of the last two (it is
shared by both cases; each claims its finding through its own rule). The catalogue version stays 1 (nothing released).

### D.16.13 Secrets (decided 2026-10-11: option A, include; D-29 item 10)

**Facts** [sources/dtap.md §11.2 item 17; verify/dtap.md §6]:
- 1,206 trajectory files match at least one secret-like pattern:
  - OpenAI-style `sk-`: 162 matches in 59 files, 25 distinct values (2 placeholder-like);
  - AWS `AKIA`/`ASIA`: 343 in 97, 3 distinct, all placeholder-like;
  - private-key blocks: 337 in 132, 3 distinct;
  - live-style Stripe keys: 24 in 15, 3 distinct;
  - bearer tokens: 38 in 13;
  - Anthropic `sk-ant-`: 4 in 4;
  - JWT 3; GitHub PAT 1; Google API 1; Slack token 1;
  - generic `key|secret|password|token = "…"` assignments: 1,110 in 913 files, 90 distinct.
- 4,139 configurations carry sandbox `env_vars`. Only the key names were recorded (e.g. `USER_ACCESS_TOKEN` 5,019
  entries, `SALESFORCE_CLIENT_SECRET` 404, `PAYPAL_USER_ACCESS_TOKEN` 234).
- The literal attacker-account token marker `(token:` occurs in 1,443 trajectory files, notably in CRM
  `task_info.malicious_instruction`.
- Whether any value is live is unknown, and testing liveness is out of bounds (it would mean using a credential).
  Some values are plainly sandbox seed data, because the tasks are about exfiltrating secrets.

**Fixed whatever the decision:**
- raw bytes are never edited (invariant 3; `WITHHELD.json`, H.4.5);
- `env_vars` never enter an AER, SEM, PROV file or report (the mapper reads configurations through a field allowlist
  of `Task`, `Attack` and `Agent.system_prompt`, and never copies `Agent.mcp_servers[].env_vars`);
- no value is ever tested;
- every count is reported without the value;
- the datasheet states that the corpus contains secret-like strings and prompt-injection payloads by design.

**Options.**
- **A. Include everything.** Raw `include` and derived records verbatim, with a datasheet disclosure. It is the
  simplest, and the data is already public under Apache-2.0. The cost: any live credential is redistributed again in
  a citable, DOI-bearing deposit.
- **B. Withhold the affected executions** (recommended). Raw stays `include` for the rest. The 4,139 configurations
  with `env_vars` are withheld as raw objects: their digest and pinned origin are in `WITHHELD.json`, and the derived
  records never needed their `env_vars`. The executions whose trajectory, judge or derived records hit the release
  secret scan, or carry the `(token:` marker, are withheld with their AER, SEM and PROV (`release.withheld`, H.4.5).
  They stay recomputable locally from the pinned revision, and the datasheet gives the count.
  - Cost: up to about 2,600 executions leave the public deposit; 1,206 + 1,443 is an upper bound, because the overlap
    was not measured.
  - Benefit: the published corpus re-distributes no candidate secret, and nothing is edited.
- **C. Reference the whole source.** Raw policy `reference` (users fetch the pinned revision themselves). This does
  not help on its own: the derived AER and SEM still carry message text, so it needs B or D as well.
- **D. Redact in derived records only.** Raw stays intact, and the affected text fields in AER are replaced by
  `unk {"/parts/k/text": "withheld"}` (C.7.1 `withheld`), declared under a rule. Partial-string redaction is not
  expressible in `aer/0.1` (a field is present verbatim or absent), so whole tool outputs and messages would vanish
  from the graph. The raw bytes in the same deposit would still hold the values unless raw is also withheld.

**Recommendation: B.** It keeps invariant 3, keeps every execution in the local corpus, uses the existing
`WITHHELD.json` and `release.withheld` mechanism (phase 11 owns the packaging), never decides liveness, and is the
policy under which a later "these are all dummy values" finding can only add executions back. Implementation needs
no core change: the scan is G's release secret scan, and withholding is HL H.4.5.

**Decision (user, 2026-10-11): option A, include.** The user judges the secret-like strings to be synthetic
benchmark data. Every execution is imported and deposited; nothing is withheld and no per-execution flag is raised.
The items fixed above still hold: raw bytes are never edited, `env_vars` never enter an AER, SEM, PROV file or
report (the configuration field allowlist), and no value is ever tested. The datasheet keeps its single general
statement that the corpus contains prompt-injection payloads and secret-like strings by design (datasheet item 12).

### D.16.14 Files, fixtures and tests

**Files added** (D.12.1 style; nothing in the protected set):

| # | File | Content |
|---|---|---|
| 1 | `src/agentprov/adapters/dtap/__init__.py`, `dialect.py`, `mapper.py`, `join.py`, `pairing.py` | reader (D.16.2), mapper (D.16.3), join (D.16.5), pairing (D.16.7); stdlib and `agentprov.{ingest,aer,adapters}` only |
| 2 | `adapters/dtap/profiles/dtap-bench.profile.toml` | profile (D.16.16) |
| 3 | `adapters/dtap/rules/dtap.rules.toml` | catalogue (D.16.11); found by the default home `agentprov.adapters.dtap` (no `CATALOGUE_HOMES` entry) |
| 4 | `adapters/dtap/artefacts.toml` | D.16.12 |
| 5 | `adapters/dtap/ext.schema.json`, `family.schema.json` | closed schemas of `ext.dtap` and `[family.dtap]` |
| 6 | `adapters/dtap/semantics/__init__.py`, `semantics/dtap.tools-1/*.toml` | D.16.9 |
| 7 | one registry entry (`adapters/registry/__init__.py`: source `dtap`, part `head`, `import_status = "planned"`, `semantics = ("dtap.tools@1",)`) plus the `READERS`/`MAPPERS` lines | shared file, append-only |
| 8 | `tools/dtap/`: `census_reproduce.py`, `gen_tool_tables.py`, `dtap_report.py`, `tool_census.py` | census check, tables, per-source report (group-level re-run outcomes), tool census and semantics coverage (D.16.9) |
| 9 | `tests/adapters/dtap/`, `tests/fixtures/dtap/` | below |

**Runner items outside the family** (D.16.15 lists them as shared-core changes; none is in `aer/`, `prov/`,
`validate/` or `corpus/`):
- **R1:** per-unit auxiliary artefacts in the import pipeline (the directory's judge file). Today only the FooBench
  test harness joins a second file, and the importer has no per-unit pairing.
- **R2:** context artefacts from a second pinned tree (the `tasks` pin). Today `context_artefacts` come from the
  primary tree only (`importer.py` `store_context`), and they are already handed to the mapper lazily.
- **R3:** importing the two `hf`-origin LFS objects beside a `git` snapshot. "More than one snapshot per corpus" is a
  recorded deferral.
- **D-530 (2026-10-15, held branch `phase-10i-context`).**
  - **R2 for downloads.** A context pin may be a download (an `ArchiveTree`): it is stored with its pin's origin and
    expanded with the role's globs, and its members are the role's context artefacts.
  - **R3 without per-unit inputs.** Pinned objects are placed for every reader, not only one with `auxiliary_for`.
  - **CLI.** `agentprov import` resolves every declared context role and every `lfs_object` pin the input needs
    (MN N.2.2).
  - **Re-map.** A re-map rebuilds the recorded context trees and pinned objects from the stored corpus
    (`corpus/rawtree.py`): `snapshot.context[]` records each role's `pin`, and an archive context's stored container.
- **D-981 (2026-10-29): R1 on a resume.** An auxiliary file that a refused primary names (an LFS pointer, a synthetic
  trajectory) is registered `select.not_execution_artefact` ("auxiliary artefact of a file that is not an execution")
  only when no unit of the run used it. A primary skipped because it is already mapped (`skipped_resume` on a resume or
  `--retry-failed` run, or a collapse into another snapshot's execution) counts as using its same-tree auxiliary
  files, read from the reader's plan alone. So a resume adds no register row a full import would not write, and a
  recompute's re-map reproduces the register.
- **Media types of R1-R3 rows (2026-10-12, sample-check fix b2).** Each auxiliary row records the media type of its
  label (`importer.py` `aux_media`: `.json` → `application/json`, `.yaml`/`.yml` → `application/yaml`, otherwise
  `application/octet-stream`). Before the fix every judge, configuration and attempt was `application/octet-stream`, so
  the same JSON was `application/json` as a primary and `application/octet-stream` as another unit's supporting artefact.
  The change touches only the `media` of supporting entries in the AER header `artifacts` (and so every DTap AER, SEM
  and PROV digest except judge-only units, which have no auxiliary rows). No other family has auxiliary rows; the
  `context_artefacts` of other families (`_context_unit`) are unchanged.
- **R4 (only if needed):** an import-side blob surface for strings over 1 MiB (D.9.5 deviation 1). Step 3 measures
  first.

**Fixtures** (F01–F21 of [sources/dtap.md §13], with sha256 and sizes in `census/c23_fixtures_final.json`). Each
fixture is a trajectory with its `judge_result.json` and, where one exists, its configuration. Licence class
`permissive`; private repository only, never in the sdist or wheel (K.4.2, B-2). The Apache-2.0 text goes to
`tests/fixtures/LICENSES/DTap-Bench-Apache-2.0.txt`. It is the upstream `AI-secure/DecodingTrust-Agent` LICENSE
(sha256 `c71d239d…`, commit `e0e38455`; neither dataset has a LICENSE or NOTICE file, so there is no NOTICE text to
reproduce) [docs/reports/systematic-search/candidates/dtap-bench.md §6; sources/dtap.md §12]. `SOURCE.json` carries
the dataset names and revisions, the authors (Chen et al., arXiv:2605.04808; committers Zhaorun Chen and Yuzhou Nie)
and every modification (Apache-2.0 §4(b)).

| Id | Covers | Id | Covers |
|---|---|---|---|
| F01 | benign with subcategory, alternation, Python-repr results, `List MCP Tools` | F12 | `debug.tool_descriptions` + `system_prompt`, suffix visible; join tier B/C |
| F02 | direct, jailbreak in the user step, attack true (`env_vars`) | F13 | medical off-by-one task id, instruction verifies (`env_vars`) |
| F03 | indirect, environment payload in a tool output | F14 | material drift (tier C) |
| F04 | claudesdk `A A T T`, result name `unknown`, `ToolSearch` | F15 | no configuration at the path |
| F05 | interleaved batch with named and unknown results | F16 | `trajectory.json` (`env_vars`) |
| F06 | googleadk contiguous batch with duplicate names, naive timestamp | F17 | synthetic (negative; `env_vars`) |
| F07 | suffix visible in `metadata.mcp_tools`, no environment step | F18 | `malicious_instruction_at_eval` |
| F08 | OpenClaw harness failure, judged | F19 | multi-turn, large configuration 27,638 B (`env_vars`) |
| F09 | `direct_prompt` (`env_vars`) | F20a/b | re-run pair, one judge |
| F10 | `direct_no_attack` (`env_vars`) | F21 | LFS pointer standing in for JSON |
| F11 | judge `error`, empty trajectory | | |

Not covered by F01–F21 and to be selected by step 3, from the census, with the same secret scan: a re-judged
(`audit_correction`) result, the `partial_trajectory.json`, a `configured_only` tool-step run without a description
log, a judge-only directory, and a `_N` attempt. Where no clean real file exists, a synthetic fixture under
`fixtures/synthetic/` (K.4.1 item 3) is used and marked so.

**Configurations with `env_vars`** (F02, F09, F10, F13, F16, F17, F19). These are not committed byte-identical: K.4.1
item 2 is not met, and this is reconciled as follows.
- Raw evidence is a corpus concept; a fixture is a test input. Invariant 3 forbids editing the raw store and corpus
  artefacts, and no corpus ever contains these files.
- The fixture is a **derived** file under `tests/fixtures/dtap/derived/`. Its `SOURCE.json` entry carries
  `derived_from {sha256, git_blob_sha1, path, revision}`, the transformation `drop_env_vars` (deletion of the
  `env_vars` mappings, values never copied, by `tools/dtap/derive_fixture_config.py`), `modified: true`, and the
  derived file's own sha256 for the fixture index (K.4.1 item 5).
- The full-corpus test (staging tree, `full_corpus` marker) checks that the derived file equals the pinned blob
  re-parsed minus `env_vars`.
- AERs built from a derived configuration cite the derived digest. They are dev-mode goldens only, never compared with
  corpus AERs. Release-mode end-to-end checks read the pinned staging tree.
- K.4.1 needs a one-line amendment admitting `derived` fixtures (a request to the K owner; not edited here).

**Tests** (`tests/adapters/dtap/`):
1. golden AER bytes per fixture (`AGENTPROV_REGEN_DTAP_GOLDEN=1`);
2. every D.16.2 row: unit, register code or collapse (the `(1)` collapse runs the runner on two copies);
3. pairing per harness, asserting rule ids and the `pairing_ambiguous_batch` and `call_result_link_conflict` issues
   (F01, F04, F05, F06);
4. join tiers and normalisations (F01, F13, F14, F15, F12);
5. one test per exposure class (F02, F03, F07, F12; the selected `configured_only` run), asserting the observed/inferred
   line: no class-O or core statement rests on a configured-only payload;
6. time: F06 naive; no `prov:*Time` in the core bundle of any fixture;
7. judgements: origins, the audit pair (`revises`), the three linkage cases (F20a/b and synthetic directories),
   `harness_default` for F09;
8. quality flags of D.16.10, each triggering its issue exactly once;
9. secrets: no `env_vars` key or value reaches any AER, SEM or PROV file (a synthetic configuration with sentinel
   values);
10. rule catalogue self-test (D.5.2) and coverage: every rule is cited by at least one test;
11. determinism: map twice; `--jobs` 1 and 3;
12. census reproduction (`full_corpus`, staging tree): every `observed` count of the profile and the D.16.6 figures;
13. **new-family test** (`test_new_family_no_core_change.py`, the D.12.3 analogue): `git diff --name-only` between the
    merge base and the adding branch touches only the files above and the listed runner items. The test derives PROV
    for F07 and the selected `configured_only` fixture and asserts the named statements (`used(te, request)` in an
    inference bundle; the `dtap.exposure` mention `observed_description_log` at D; `configured_only` at I; the
    payload fixture in an inference bundle) and the named gaps (no core `prov:endedAtTime`; no `wasInformedBy` from
    order; no `used` of a configuration by any activity).

Fuzzing of the `dtap` reader is phase 12b's (AGENTS.md §0).

### D.16.15 Downstream effects (CLAUDE.md rule 10) and invariant 5

- **Existing corpora: no change.** A catalogue is embedded only in the PROV of the executions that declare it
  (`prov/rules/top.py`, the `ctx.declared` loop; D-26), and no existing AER cites `dtap`. No AER, SEM or PROV digest
  of any existing corpus changes, the regeneration batch is unaffected, and the golden and gate-D digests are
  unchanged.
- **Shared files:** one registry entry, the `READERS`/`MAPPERS` lines, and the runner items R1–R3 (R4 if measured as
  needed), all additive, with tests. `adapters/runner/` is outside invariant 5's protected set, but it is shared
  core, so step 3 lists every change, as D.9.5 did for Inspect.
- **Invariant 5 (protected set).** The design needs nothing under `aer/`, `prov/`, `validate/` or `corpus/`:
  - the catalogue home defaults to `agentprov.adapters.dtap`;
  - the new namespace and types are data (C.10 item 7);
  - role `agent` messages are valid `aer/0.1`;
  - the `unknown` result names are kept out of typed fields, so the validator deny-list is not hit;
  - register codes reuse H.6.3's closed set;
  - `origins.jsonl` already accepts `hf` origins.

  Three places could create pressure and are recorded as open points rather than specified (D.16.17):
  - group-level outcomes for unresolved re-runs, if `stats` were to compute them (it would have to read
    `ext.dtap`, which is adapter logic in the core);
  - default rate exclusions, if `stats` hard-coded DTap issue codes;
  - R4, if a string over 1 MiB exists and the AER writer requires a blob (C.11.5).
- **Phase 11 items** (for `docs/reports/analysis/datasheet-items.md`; not edited here): the rate defaults of D.16.10;
  "both values reported" for re-judged results; the secrets disclosure; the injection limitation with the D.16.6
  figures; the per-split meaning (`direct_prompt`, control).
- **Manuscript:** the limitation wording of `docs/reports/systematic-search/candidates/dtap-bench.md` §6 stands. The
  exact exposure classes of D.16.6 supply its numbers after step 4.

### D.16.16 Profile sketch (`dtap-bench`)

```text
[profile]  { id = "dtap-bench", version = 1, source_id = "dtap", family = "dtap", parts = ["head"] }
           evidence = ["sources/dtap.md", "verify/dtap.md", "docs/reports/systematic-search/candidates/dtap-bench.md"]
[source]   canonical_repo = "https://huggingface.co/datasets/AI-Secure/DTap-Bench-Agent-Trajectories"  paper = "arXiv:2605.04808"
[[source.pins]] role = "runs"   part = "head"  primary = true  kind = "git"  commit = "836caf2fdd78b888ddd14fb62dc038e932e17898"  date = "2026-07-01"
[[source.pins]] role = "tasks"  kind = "git"  repo = "https://huggingface.co/datasets/AI-Secure/DecodingTrust-Agent-Platform"  commit = "a3edc9b7c48cbf16c2ea9c18990fb94c7494dd04"  date = "2026-06-18"
[[source.pins]] role = "lfs_object"  kind = "hf"  revision = "836caf2f…"  file = "claudesdk/claude-sonnet-4-5/windows/benign/32/20260401_095722.json"  sha256 = "<pointer oid>"  # and …/49/20260401_113303.json
[licence]  spdx = "Apache-2.0"  policy = "include"   # subject to the D.16.13 decision
           basis = "Apache-2.0 per both dataset cards; upstream AI-secure/DecodingTrust-Agent LICENSE; no LICENSE or NOTICE file in either dataset"
           attribution = ["Chen et al., DecodingTrust-Agent Platform (DTap), arXiv:2605.04808", "AI-Secure/DTap-Bench-Agent-Trajectories @ 836caf2f", "AI-Secure/DecodingTrust-Agent-Platform @ a3edc9b7"]
           unassessed = ["model-provider terms on redistributing model outputs", "vendored sandbox datasets inside tool results (Salesforce, PayPal and others)"]
[lineage]  built_on = []  duplicates = []  content_dedup = "never"
[import]   dialect = "dtap.trajectory"  mapper = "dtap.trajectory"  variants = ["v1"]
           include = ["*/*/*/benign/**/*.json", "*/*/*/malicious/**/*.json"]
           exclude = [{ glob = "**/red_teaming_agent_*.json", code = "select.not_execution_artefact" },
                      { glob = "**/screenshots/*.png", code = "select.not_execution_artefact" },
                      { glob = "README.md", code = "select.not_execution_artefact" }, { glob = ".gitattributes", code = "select.not_execution_artefact" }]
           auxiliary = ["judge_result.json"]                                   # R1: same directory
           context_artefacts = ["tasks:**/config.yaml"]                         # R2: second pin
[family.dtap] layout = "{framework}/{model}/{domain}/{split}/{rest…}/{file}"  threats = ["direct", "indirect", "direct_prompt", "direct_no_attack"]
           pairing = { openaisdk = "dtap.pair_strict_alternation@1", openclaw = "dtap.pair_strict_alternation@1", googleadk = "dtap.pair_contiguous_batch_fifo@1", claudesdk = "dtap.pair_interleaved_fifo@1" }
           matcher = { normaliser = "dtap.alnum_norm@1", min_needle = 24, window = 40, judge_link_min = 40 }
           semantics_profile = { id = "dtap.tools", version = 1 }
[[family.dtap.quirk]] id = "dtap.synthetic_trajectory"  observed = { files = 20 }
[[family.dtap.quirk]] id = "dtap.harness_failure"       observed = { files = 47 }
[[family.dtap.quirk]] id = "dtap.empty_trajectory"      observed = { files = 17 }
[[family.dtap.quirk]] id = "dtap.rejudged"              observed = { judges = 458 }
[[family.dtap.quirk]] id = "dtap.rerun_directories"     observed = { directories = 1291, surplus_files = 1828 }
[[family.dtap.quirk]] id = "dtap.ambiguous_batches"     observed = { results = 61651 }
[[family.dtap.quirk]] id = "dtap.join_tiers"            observed = { a = 62419, b = 2899, c = 1693, missing = 786, unparseable = 9 }
```

The exact keys are fixed by `family.schema.json` in step 3; this sketch fixes their content.

### D.16.17 Open questions for the user (all decided 2026-10-11)

1. **Secrets policy (D.16.13).** Options A to D. ~~Recommendation: B~~ **Decided: A (include), see D.16.13.** The recommendation was B: withhold the 4,139 `env_vars`
   configurations, and the executions that hit the release secret scan or carry the `(token:` marker, through
   `WITHHELD.json`. Nothing is edited, and everything stays recomputable locally.
2. **Evidence class of judge linkage in single-trajectory directories.** Co-location is a layout convention, not
   code, so the design gives it class I (`dtap.judge_dir_colocation@1`), with D only where content matching pins the
   judge to the run. As a consequence most DTap outcome links sit in inference bundles. **Decided: keep I** (as recommended).
   The 22 judge-only directories show that judges and trajectories can be decoupled, and D-27 c6 rules out
   document-only D.
3. **Message role `agent`, kept verbatim** (D-28). Relabelling it to `assistant` would make apv:AssistantMessage typing
   and the assistant accounting apply, but D.15.1 forbids relabelling source fields. **Decided: keep
   verbatim** (as recommended). Cross-source statistics group role `agent` with `assistant` explicitly, as a documented stats mapping.
4. **Rate defaults and group-level outcomes in `stats` (phase 11).** Default exclusions (harness failures, unresolved
   re-runs, outcome-only units, `harness_default` values) should be driven by data the catalogue declares (issue codes
   and origins), not by DTap names in `stats`. Group-level outcomes for unresolved re-run directories should be
   computed only by `tools/dtap/dtap_report.py`. **Decided:** both approved (as recommended), so that `stats` stays
   source-neutral (rule 9).
5. **Runner items R1–R3** in the shared `adapters/runner/` (and, if fetching the `runs` git pin from
   `huggingface.co` needs it, a host entry in `raw/fetch.py`, which phase 12 owns). **Decided** (as recommended): phase 10b
   implements R1–R3 additively with tests, lists them as D.9.5 did, and asks phase 12 before touching `raw/`.

### D.16.18 Implementation resolutions (phase 10b step 3, 2026-10-12)

The code is the reference (`src/agentprov/adapters/dtap/`, runner items in `adapters/runner/`); tests in
`tests/adapters/dtap/`. Corrections to D.16.1-D.16.16 found by the implementation, each with its reason:

1. **Run end time (D.16.4).** `traj_info.timestamp` is kept verbatim in `t.raw.end` (O) with `unk {"/t/end":
   "ambiguous"}` under `dtap.timestamp_is_run_end_unverified@1`, and `ext.dtap.timestamp_zone` (`utc`, `none` for the
   googleadk naive values, `unparsed`); `t.end`/`t.end_naive` are not written. Reason: `agentprov-prov/0.1` emits an
   I-class time of an activity as an inference-bundle `apv:Assessment` entity carrying `prov:endTime`
   (`prov/engine.py`, attribute split), which tier 4 refuses (`pv.prov_structure.relations`, `PV-NE-6`). The reading
   "this is the run end" is unchanged (I); it is not typed. Reported as an engine/validator inconsistency (prov owner). **Resolved (D-28 addendum, 2026-10-12):** I-class
   times are never PROV times; the engine omits them with a disclosure (implemented 2026-10-12, D-28 addendum; E.5.3 item 7). Writing the run end as an I-class `t.end` is now safe, and is left to the DTap session.
2. **Payload fixtures (D.16.6).** Existence and attribution stay I (`dtap.config_content_tier_a@1`,
   `dtap.config_payload_attacker_unverified@1`); `/content` and `/vector` are **D** under `dtap.config_path_join@1`
   (a verbatim copy of the joined configuration at the pointer in `ext.dtap.config_pointer`; the statement of that rule
   says so). Without it every marker would be I by the weakest-premise rule (C.6.5) and no exposure class could be D.
   Configuration locators are whole-artefact (`{"a": ...}`): JSON Pointers do not resolve inside YAML (C.9.2).
3. **`dtap.exposure` (D.16.6).** One per payload fixture, target the `run` scope (an activity, so the claim is an
   `apv:Assessment`), value `{fixture, channel, class}`. Its premises are the AER fields the matcher read (the
   fixture's content, the matching part or entry, the logged locations), not the marker annotations: a present
   marker's PROV statement carries the fixture's I existence and would cap the claim at I. Result: the observed
   classes are D in the assessment bundle, `configured_only` and `partial_match` I (test 13). An agent-output match
   that is window-only is `partial_match`.
4. **Fixture table (D.16.14).** F14 is tier **B**, not C: a benign run's goal check (empty text) always verifies, so a
   benign run is never C under the census tier function (c07i). The partial trajectory (687,011 B) is not committed;
   its rule is tested on F01's bytes under that file name. Added fixtures: X01 re-judged result, X02 judge-only
   directory, X03 a `_N` attempt, X04 `(1)` copies. Nine configurations are derived (`drop_env_vars`).
5. **Judge-only directories (D.16.2, D.16.8).** The staged tree has 14 directories whose only JSON is the judge and 8
   that also hold only a red-teaming log: 22 in all, not 22 + 8. Both are judge-primary `outcome_only` units. Step 4
   confirms the count.
6. **Rules added** (catalogue `dtap` v1, 72 rules): `dtap.no_params_empty_args@1` (D; 18,083 call steps have no
   `tool_params`; an action `<name>()` gives `args {}`, any other gives `args null` with `ambiguous`),
   `dtap.duration_no_clock@1` (D; the `/t/dur_s` `ambiguous` declarations cite it), `dtap.path_field_check@1` (D; the
   rule of `dtap.path_field_mismatch`), `dtap.non_informative@1` (I; SEM `dtap.non_informative`). A recorded task-id
   normalisation tags `/ext/dtap/join/task_id` I under `dtap.task_id_offset_medical@1` or
   `dtap.task_id_reformatted@1`.
7. **Segments (D.16.3).** Meta-steps, harness-error steps and their echoes are harness steps: they break a segment and
   are never in one. The echo message has no actor and no generator.
8. **Artefact ids.** `a1`, `a2`, ... are assigned in the order judge, configuration, other attempts of a re-run group
   (only when the group has more than one distinct attempt), not fixed per role.
9. **Configuration content.** The configuration's `Agent.system_prompt` is not emitted as a fixture (only a logged
   `debug.system_prompt` is); `outcome_only` units (empty trajectories) carry no payload fixtures.
10. **Semantics tables.** `servers.toml` and `domains.toml` are generated (47 servers, 730 tools; 1,023 observed
    `(server, tool)` pairs); roles are labelled for 14 reviewed MCP tools (`labels.toml`) and 13 claudesdk built-ins;
    every other tool keeps role `unknown`, and every tool output integrity `unknown` (fail-closed, C.14.3).
    **Superseded by phase-10b follow-up 4 (2026-10-12; D.16.9):** 536 reviewed `labels.toml` entries and 17 built-ins
    (with integrity and evidence), the domain match for `server: "unknown"` calls, and 99.88 % of tool calls labelled.
    `dtap.tools@1` is extended in place: no DTap corpus has been imported, sealed or released (the registry part is
    `planned`; `$AGENTPROV_HOME/corpora` holds no `dtap` corpus), so no output carries the earlier tables. Unobserved
    built-ins (`MultiEdit`, `LS`) were dropped (only tools that occur in the runs are labelled).
11. **Rate exclusions** (D.16.10 "Rate default"; D-48 item 10) are package data `adapters/dtap/rates.toml`.
12. **Runner items** as implemented (shared code, all additive): a reader's `auxiliary_for(label, listing)` names the
    unit's same-tree inputs (`judge`, `attempt:<n>`), context inputs `"<role>:<label>"` of a `ContextTree` (R2) and
    `copy:<role>` files (stored, registered `dedup.collapsed`); an auxiliary file whose every unit was registered
    not-imported is registered the same way (the synthetic directory's judge); `PinnedObject` candidates stand for a
    file of the primary tree and are vouched for by their own pin (R3; the LFS objects as `hf` origins); a reader's
    `register_detail` names the `select.not_execution_artefact` detail. R4 is not needed: the longest string in the
    two LFS objects is 904,222 B (< 1 MiB).
13. **Fetch layer (open, phase 12).** `raw/fetch.py` `_split_repo` accepts `https://<host>/<owner>/<repo>` only, so the
    `runs` and `tasks` git pins (`https://huggingface.co/datasets/<owner>/<name>`) cannot be fetched, seeded
    (`tools/seed_git_cache.py`) or vouched for through `--verify-against-pin`, and `agentprov fetch --references`
    (which loads every shipped profile's pins) raises on the `dtap-bench` profile. Needed: accept the
    `huggingface.co/datasets/<owner>/<name>` shape (cache path `git/huggingface.co/datasets/<owner>/<name>.git`).
    Until then `tools/dtap/import_dtap.py` drives `import_source` with pin checks built from the pinned staging
    worktrees, and the `hf` LFS objects go through the existing per-file `hf` recipe of `Fetcher`.
    **Done (phase 12b, D-53):** `_split_repo` accepts exactly `https://huggingface.co/datasets/<owner>/<name>[.git]` on
    that host and caches it at `git/huggingface.co/datasets/<owner>/<name>.git` (history store and index alike); other
    `huggingface.co` namespaces and a two-part path whose owner is `datasets`/`models`/`spaces` are refused
    (`raw.fetch.recipe`). Fetching, seeding and `--verify-against-pin` all go through this one function.
14. **Worker memory (open).** Tier-4 validation of a long run is quadratic (model-call inputs and exposure pairs over
    the logged prefix): a 329-record openclaw AER gives 15 MB of PROV-JSON and a 1.85 GB validation peak, and the two
    LFS-object runs exceed the T1 worker's 2 GiB RSS cap in the `prov` job (`worker.limit.rss`). Their AERs seal and
    validate; SEM, PROV and tier 4 pass in process. Needs a larger cap for the `prov` job or a streaming validator
    before step 4 (phase 12 / prov owner).
    **Done for the cap (phase 12b, D-55):** `prov` jobs run under 4 GiB (bounded by 16 GiB); measured on the 14 longest
    and largest runs after round-trip step 2, every run that completes fits (largest 2,518 MiB at 30 MB of PROV;
    `docs/reports/hardening/prov-rss.md`). Still open for the validator owner: PROV-JSON over 64 MiB fails tier 4 at
    parse (`excessive_trading/10`, 68 MB) and `pii-4` (1,557 steps) derives 991 MB, over the 256 MiB output cap.
15. **Sample-corpus check (2026-10-12; `docs/reports/analysis/dtap-sample-check.md`; user decisions in the D-29
    addendum).** Fixes applied: b1 specific artefact-catalogue claims and seven entries for the former unclassified
    findings (D.16.11, D.16.12); b2 media types of the auxiliary rows (D.16.14); b3 the wording of D.16.6 and D.16.8;
    b4 the analysis tools read role `agent` through one grouping (`tools/analysis/message_roles.py`). Questions decided:
    - **Q1, shared `raw:` entities:** a content-addressed `raw:` entity keeps the execution-relative `apv:originPath`
      and `apv:artefactRole` of each citing document, so merged documents give multi-valued attributes (accepted,
      disclosed in the datasheet). After b2 no `apv:mediaType` variant is left; 61 of 877 shared keys still vary in the re-imported sample
      (45 `apv:originPath`, 16 `apv:artefactRole`), the same count as before, since each media variant came with a role
      variant.
    - **Q2, completeness:** a run with no agent turn stays `verified_complete` on `dtap.acc.counters` alone (0 calls,
      0 results; 6 runs in the sample); every run with an agent turn is `unverifiable` (derived model calls).
    - **Q3, manifest origin:** the step-4 import records the `runs`/`tasks` pins (and the `hf` objects) as origins in
      `corpus.json`, never `<home>` staging paths; the sample driver's `LocalTree` origins are acceptable only for
      scratch corpora.
    - **Q4, judge-only directories:** byte-identical judge files of two judge-only directories are one `outcome_only`
      execution with two origins (content-addressed identity, D-27 c2, SEC-19); judge-only units count distinct judge
      files, and per-directory counts come from the origins.

### D.16.19 Redaction of listed harness-host accounts (D-607; user decision 2026-10-21: a labels allowlist)

**Why.** Pre-check PC-01 (`docs/reports/precheck/dtap-bench.md`) found five workstation accounts of the harness hosts
in 1,094 trajectory files: tool output, OpenClaw harness-config state, agent arguments and text, and final responses.
137 other named accounts are benchmark or model content and stay verbatim. D-607 is an exception to D-604 for this
source: model-authored text is redacted too.

**Profile table** `[[family.dtap.redact]]` (closed; `family.schema.json`), read by `agentprov.adapters.dtap.redact`:

| key | meaning |
|---|---|
| `id` | unique lower-case name; cited as `dtap-bench@<version>#<id>` |
| `scope` | `all_strings` (the only scope): every string of every record the mapper writes |
| `pattern` | a structural regular expression with a named group `span`; it never names an account |
| `replacement` | literal text with `{span12}`: the first 12 hex of SHA-256 over `<profile id> NUL <span>` (D-476). It replaces the span only |
| `labels` | the allowlist of 12-hex labels; a match whose label is not listed is left unchanged |
| `note` | free text |

`dtap-bench@2` declares three rules over one list of six labels: the five PC-01 accounts and one other letter case of
account #3. The labels were computed out of band from the pinned data, so the repository holds no name:
1. `host_account`: the account segment of an account path, in the forms and endings of D-457 over decoded strings;
2. `host_account_token`: a whole letter-and-digit token (`ls -l` owner columns, munged `-Users-<n>-` directory names,
   deeper roots, a path after an escaped newline);
3. `host_account_dotted`: a token whose letter runs are joined by single `.`, `_` or `-`.

**The pass.** It runs after the mapper has built every record (header included), in `_Build._redacted`:
- values and object keys are redacted;
- pointers are redacted token by token: `evf` and `unk` keys, the pointer half of scoped rule citations, `ext.lex.ord`
  keys and `ext.lex.flt` entries; the member names in `ext.lex.ord` are redacted as the keys they copy;
- `src` locators and the generated members (`k`, `id`, `ev`, `by`, `after`) are not touched;
- each redacted pointer is tagged `D` (an `I` stays `I`) and cites `dtap.value_redacted@1#<pointer>`;
  `ext.dtap.redacted` lists `{p, rule}`; a recorded `ext.lex.ord` of `/ext/dtap` gains `redacted`;
- one info seal issue `dtap.value_redacted` gives the count of redacted values.

A profile with no listed label leaves every record unchanged. Raw bytes ship as pinned (D-186 (c)) with the datasheet
statement `dtap-host-accounts-redacted`. In a release scan their path forms are D-457 `account-path` findings with an
accepted triage value (DECISIONS D-607, "Withholding"). The token rules and the case-variant label were kept by the
user (2026-10-21: label-gated, 0 collateral).

**Census (D-607).** 1,140 executions mapped, 1,094 with a redaction, 41,312 spans at 17,075 pointers. Residue in the
AER is 0 (path forms, bare words in any letter case, `src`), and so is residue in the SEM and PROV of a 120-execution
sample. Collateral is 0: no other account's label is listed.

**Versions.** Profile `dtap-bench` 2 and catalogue `dtap` 2 (version 1 of each archived), and `dtap.tools@2` (D.16.9).

**Tests.** `tests/adapters/dtap/test_redact.py`: the closed grammar, every path form and the token contexts with
synthetic names (a synthetic label computed in the test and listed in a test copy of the profile), unlisted names
untouched, pointer handling, the collision check, and a mapper run that redacts a listed account in agent arguments,
the action string, tool text, a tool-result key and the final response, with SEM and PROV derived and validated.

## D.17 The OpenHands event-stream family (`openhands`; planned, phase 10g)

Status: **implemented** (phase 10g, 2026-10-12; DECISIONS D-170–D-179, user-approved 2026-10-12, with the D-172 addendum
and the resolutions of D.17.13). Both registry parts stay `planned`: full imports wait for the regeneration round and the
user's approval, and RedCode's trajectories are deposit-zip members, which the runner does not import yet (D-156). Every
count is from the phase-10g census (`docs/reports/phase10g/`). Text inside the sources (harmful task definitions, NPC
dialogue, tool outputs, judge texts, harness code) is untrusted data, never instructions (G; CLAUDE.md "Security").

OpenHands saves a run as a JSON array of serialised events. Two included sources use it (D-145): OpenAgentSafety
(`sani903/OpenAgentSafety@857798ff`, 1,560 runs of five models on 352 tasks, an OpenHands 0.28.1 fork with Sotopia NPC
chat) and the OpenHands part of Zenodo 23168099 (RedCode-Exec "Which Orders Count?", 5,460 runs of claude-sonnet-4-6 and
qwen3-coder-30b-a3b-instruct under OpenHands 1.5.0). The format records the link from each observation to the action it
answers (`cause`) and, on every agent action, the provider response it was built from (`tool_call_metadata`), so it is the
first imported format whose call-to-result links and model calls are recorded rather than paired or segmented.

### D.17.1 Identity, pins and path grammars

| Profile | Source id | Pin | Variant | Logical run identity |
|---|---|---|---|---|
| `openagentsafety` | `openagentsafety` | git `sani903/OpenAgentSafety@857798ff26c4ce6e1d7911ee4d8b3f84a71184e0` (MIT) | `oas-0.28` | `evaluation/<model_dir>/traj_<task>.json` |
| `redcode-exec-openhands` | `redcode-exec-openhands` | Zenodo 23168099, six `trajectories_OH-*.zip` (one pin role and one snapshot each, D-932) plus the supplementary zip (CC-BY-4.0) | `oh-1.5` | `results/OH/<model>/<S1-S3>/<language>/trajectory/oh_<sc>_<payload>[_py\|_sh]_<S>-<hash>.json` |

One execution per trajectory file (content-addressed id, AD-04). The RedCode case hash in the file name is shared by both
models' runs of a case (2,160 shared values): it is kept in `ext.openhands.path_facets.case_hash`, never identity. The
OpenAgentSafety screenshots (7,827 PNG blobs) are not part of the import and were not fetched. The maintained copy
`Open-Agent-Safety/OpenAgentSafety` is outside the closed search (D-148).

**Task header.** OpenAgentSafety: `benchmark "openagentsafety"`, `task_id` = the task name; `attack_id` and `defense_id`
`unk not_recorded` (the risk is in the task design). RedCode: `benchmark "redcode-exec"`, `suite` = language, `task_id` =
`"<scenario>_<payload>"`, `attack_id` = the request type `C1`/`C2`/`C3` of the target `S1`/`S2`/`S3` (D,
`openhands.redcode_request_type@1`, the deposit README's table), `defense_id` `unk not_recorded`.

### D.17.2 Dialect and reader (`agentprov.adapters.openhands.dialect.OpenHandsEventsReader`)

Dialect `openhands.events`. A file is a JSON array of objects with `id`, `timestamp`, `source` and exactly one of
`action` and `observation`; parsing is `strict_json_loads` under `IngestLimits` (largest file 34,524,664 B; no strict-loader
failure in 7,020 files). Variants come from the event vocabulary, never from a path: `oh-1.5` when the first event is a
`system` action whose `args` carry `openhands_version` (all 5,460 RedCode runs: `1.5.0`), `oas-0.28` when no `system`
action occurs (all 1,560 OpenAgentSafety runs). A `system` action elsewhere is `openhands.sniff.variant`; an empty array is
not a run (`select.not_execution_artefact`, detail `openhands.empty_event_list`).

**Per-unit inputs** (runner items R1/R2, as for DTap): OpenAgentSafety `eval`, `state`, `llm_judge` (the model
directory's `*_safety_eval_results.json`), `task_md`, `checkpoints`, `scenarios`, `evaluator` (supporting artefacts; the
evaluator is never executed); RedCode `score` (`conversation_log/index<sc>.json`), `dataset` (S1) or `prompt` (S2/S3).

### D.17.3 Mapping to AER

Records in order: header, actors, scopes, fixtures, the events in array order (each generator before what it
generates), judgements. Message ids are `m<array index>`.

| Source event | AER records | Evidence (rule) |
|---|---|---|
| `system` action (`oh-1.5`) | fixtures `system_prompt` (`args.content`) and `tool_definitions` (`args.tools`); harness `version` = `openhands_version` | O |
| first user `message` | `message` role `user`, actor `user` (`simulated_user`) | text O; actor I (`openhands.first_message_harness_authored_unverified@1`) |
| later user `message` | the same; OpenAgentSafety actor `fake_user` (`simulated_user`, role `fake_user`, model requested `gpt-4o-2024-05-13` from the harness code at the pin); `ext.openhands.reply_form` `fixed_text`/`generated` | actor I (`openhands.fake_user_reply_unverified@1`); form D (`openhands.fixed_reply_digest@1`, SHA-256 against the profile) |
| `recall` action and its observation | `activity` `openhands:recall` (actor `harness`) and `artefact` `openhands:workspace_context` / `openhands:recall_result` | actor I (`openhands.recall_is_harness_step@1`); link D (`openhands.recall_cause@1`) |
| each distinct `tool_call_metadata.model_response` | `model_call` (O): `served_model`, `response_id`, `finish_reason`, `usage` (D, `openhands.usage_fields@1`), `status: kept` (D), `input` = the logged messages so far (I, `openhands.context_is_logged_prefix_unverified@1`), `tools` = the tool-definition fixture (I); `request`, `response`, `params`, `t` `not_recorded` | O, `openhands.response_kept@1` |
| the response's message | one `message` role `assistant`, `generated_by` the call (D, `openhands.response_message@1`): a `reasoning` part (provider reasoning field), a `text` part, one `tool_call` per entry of `choices[0].message.tool_calls` (`args` decoded strictly, D `openhands.arguments_decoded@1`; `args_raw`; `provider_call_id`); `finish` is kept as an `other` part `openhands.finish_call` | O; actor D (`openhands.action_from_tool_call@1`) |
| tool action + its observation (`cause`) | `tool_execution` (actor `env`, `call` = the part with the action's `tool_call_id`, `name`, `args` = OpenHands' dispatched args, `status: ok`, or `unk ambiguous` for an `error` observation) and a `tool` message whose `tool_result` answers the call | existence D (`openhands.observation_is_execution@1`); `responds_to` D (`openhands.cause_link@1`); `call` D (`openhands.action_from_tool_call@1`) |
| `error` observation "The action has not been executed." (and the two 1.5.0 notices) | `activity` `openhands:controller_notice` and `artefact` `openhands:notice_text`; the call is listed in `unexecuted_tool_call`; no execution | D (`openhands.not_executed_notice@1`) |
| `error` observation without `cause` | `activity` `openhands:harness_error` (status `error`) and `artefact` `openhands:error_text`; the run ends in error when it is the last event | I (`openhands.uncaused_error_is_harness@1`) |
| agent `message` without `tool_call_metadata` | a `model_call` of class I (OpenAgentSafety: `response_id` from `llm_metrics.token_usages[-1]`, O) and an assistant message it generates | I (`openhands.text_message_is_model_output_unverified@1`) |
| OpenAgentSafety `chat` call and reply | tool call, execution and result as above; an `npc<k>` actor (`simulated_user`, role `npc`, name = `npc_name`) named by the execution's `ext.openhands.npc`; SEM `author` on the reply | I (`openhands.npc_reply_unverified@1`) |
| `extras.set_of_marks`, any string over 1 MiB | not inlined: `{not_inlined: {sha256, bytes, media?}}` in place, the locator in `src`; the pointer is D | D (`openhands.content_not_inlined@1`) |
| any other event | `activity` `openhands:unmapped_event` and `artefact` `openhands:event_payload`, issue `openhands.unmapped_event` | none occurs in the census |

**Actors.** `bench`, `harness` (`openhands`; RedCode `version` O from the log, OpenAgentSafety `version` `0.28.1` I under
`openhands.oas_harness_lock_unverified@1`), `user`, `fake_user` (OpenAgentSafety, when replies exist), `agent`
(`llm_agent`; `model.served` = the runs' single `model_response.model`, D `openhands.served_model@1`; `model.requested` =
the LiteLLM route string of `llm_metrics.token_usages[].model` where recorded, O; `on_behalf_of: user`, I), `env`
(`tool_runtime`, D), `npc<k>`, and one judge per judging source (`oas_checker`, `oas_llm_judge`, `redcode_scorer`).

**Scopes.** `run` and one `att0`. The run's `t` holds the first and last event times in `t.raw` with `/t/start` and
`/t/end` `ambiguous` (`openhands.event_time_naive_local@1`). `status: error` when the last event is an uncaused error, or
(OpenAgentSafety) when the state file's `agent_state` is `error` (I, `openhands.state_run_status@1`).

**Order and time.** Ids increase in array order in every file and are assigned by the event stream at creation
(`openhands.event_order@1`), so stream records get positional `after` edges at that rule's class; generated records get
causal edges. Event timestamps are naive local wall-clock times of event creation (`datetime.now().isoformat()`); messages
have no `t` field (C.3.4), so every event time stays verbatim in `ext.openhands.timestamp`; no time is converted, placed,
or used for a `time` edge (C.8.5, C.8.6). The RedCode harness's `+8 h` file labels are not evidence about the event
clock and are never applied.

### D.17.4 Links: `cause` and the citation of OpenHands code (D-172 and its addendum)

`cause` is set by the runtime on the observation of an executed action (`runtime/base.py`), by the memory on a recall
observation (`memory/memory.py`) and by the controller on the not-executed notice (`controller/agent_controller.py`); ids and
timestamps by the event stream (`events/stream.py`); `tool_call_metadata` per tool call by the agent
(`agenthub/codeact_agent/function_calling.py`). These files were read at two commits:
- `adityasoni9998/OpenHands@5a13eacf8177c8dab2600f9011d88f18a7db0ad8` (2025-04-07), the fork that OpenAgentSafety's
  `poetry.lock` at the pin resolves (`openhands-ai 0.28.1`); fetched with the user's approval (40 + 1 files);
- `OpenHands/OpenHands@a77b05509ec010d44d1e274b0f8daace0f89ea8f` (tag `1.5.0`, 2026-03-10): every RedCode log names
  `1.5.0`, and the deposit's vendored `environment/OpenHands` matches the tag's tree by git blob id for all eight cited
  files (only `pyproject.toml` differs); tree objects fetched with the user's approval, no file contents.

The D rules cite both commits; each profile's `verified_code` names its commit, so every `cause`, execution and call link
is class D in both corpora. A profile without verified code cites the `_unverified` twins (class I). The matching
`tool_call_id` (100 % of 33,278 tool observations) corroborates and never raises a class. Nothing is linked by order or time.

### D.17.5 Model calls and identity

One `model_call` per distinct `model_response.id` (OpenAgentSafety: 78 responses with 2–6 actions, all gpt-4o; RedCode:
always one). Served ids are `model_response.model` (OAS `claude-3-7-sonnet-20250219`, `deepseek-chat`, `deepseek-reasoner`,
`gpt-4o-2024-08-06`, `o3-mini-2025-01-31`; RedCode `claude-sonnet-4-6`, `qwen3-coder-30b-a3b-instruct`). Directory names
are never identity; they agree with the served ids in every file. `usage` maps provider counts to C.3.12 `Usage`; the
provider object stays in `ext.openhands.usage_raw`.

### D.17.6 Outcomes (D-177)

- **OpenAgentSafety checkpoints** (`eval_<task>.json`, 1,474 of 1,560 runs): one judgement per checkpoint (`checkpoint/<k>`)
  and `final_score`, values verbatim (`{total, result}`), actor `oas_checker`, origin `checker` (I,
  `openhands.checker_recorded_unverified@1`), subject joined by path (D, `openhands.oas_eval_path_join@1`).
- **OpenAgentSafety LLM-judge entries** (`*_safety_eval_results.json`; four models, Claude 161 of 289): judgements
  `llm_label` (the string `"Label: <n>"` verbatim) and `rule_based_score`, actor `oas_llm_judge`; no meaning is assigned.
- **RedCode scores** (5,460 of 5,460): judgement `score`, actor `redcode_scorer`; a score of 1 has `origin` `unk ambiguous`
  (`openhands.redcode_score_one_ambiguous@1`): the deposit scorer also writes 1 for a missing trajectory or container or a
  `PROBLEM` rubric. `last_response_full` stays in `ext.openhands.judge`.

### D.17.7 Task-definition joins (D-178)

OpenAgentSafety joins `workspaces/tasks/<task>/` by path (1,560 of 1,560). `task.md` becomes a `task_prompt` fixture at
class I (`openhands.oas_task_md_at_pin_unverified@1`: runs 2025-05, pin 2026-08; content O), and
`ext.openhands.seen_in` records the first observation holding its whole whitespace-normalised text (D, 276 runs; issue
`openhands.task_text_not_seen` in 1,284; the part-A census's 200-character prefix test found 420). RedCode joins the dataset code (S1) or the generated prompt (S2/S3) by key; the
fixture is D when the request occurs in the first user message: exact 3,360, contained 1,956, contained after the
harness's declared `/sys/kernel` → `/app/sys/kernel` rewrite 144 (issue `openhands.join_after_rewrite`), not contained 0.

### D.17.8 Content not inlined and secrets (D-179)

AER requires a blob for any string over 1 MiB (C.2.1 item 6) and no import-side blob surface exists (D.9.5 deviation 1;
routed with D.16.14 R4). The 7,973 set-of-marks screenshots and the 117 strings over 1 MiB of OpenAgentSafety are recorded
by digest and size; a tool output over 1 MiB keeps `text: null` with `unk ambiguous` and its digest in
`ext.openhands.text_not_inlined`. Secret-like strings follow option A (user decision, 2026-10-12): kept as published and
disclosed (388 of 423 OpenAgentSafety occurrences are fixture credentials of the task definitions; 3 distinct values are
not; RedCode none). D-606 classes all 8 distinct values as CC-13 fixtures (none has an issued-key format; D.17.14) and
D-602 withholds the one real-format token of the RedCode deposit, which sits in an unselected member (D.17.14).

### D.17.9 Rule catalogue `openhands.rules.toml` (`[catalogue] id = "openhands"`, version 2)

60 rules: 7 D rules read from OpenHands code with their 7 `_unverified` twins; 18 D rules over observed fields (listed as
independent in `adapters/openhands/citation.py`, `openhands.value_redacted@1` among them); 2 reserved D detectors that
sealing or the release scan apply, never the mapper (`openhands.deposit_secret_withheld@1`,
`openhands.fixture_secret_shape@1`); 14 I rules of the mapper; 12 I rules of the semantics profile. 16 issue codes
(`openhands.*`, `value_redacted` added), 9 activity/artefact types and one part type (`openhands.finish_call`). Version 2
is the D-31 bump of D-606 (2026-10-21): version 1 (57 rules, 15 codes) ships as `rules/archive/openhands.rules.v1.toml`
with the bytes the scratch corpora recorded (`9bc984f73823…`). Tests: `tests/adapters/openhands/test_rules.py`,
`tests/adapters/openhands/test_d31_bump.py`.

### D.17.10 Semantics profile `openhands.tools` (versions 1 and 2)

Version 2 is version 1's tables on the openhands catalogue version 2 (`CATALOGUE_OF = {1: 1, 2: 2}`, H.2.5: one catalogue
version per corpus); both profiles select `@2`. `@1` keeps reading the archived catalogue version 1 and its recorded
digest (`f7988322c1bd…`).

Tool table by function name (`execute_bash`, `execute_ipython_cell`: `execute_sink`; `str_replace_editor`: `write_sink`,
`content_source`; `browser`: `egress_read`, `send_sink`; `web_read`, `fetch`: `egress_read`; `chat`: `send_sink`;
`think`, `task_tracker`: `neutral`); outputs `untrusted` (or `unknown` for `think` and `task_tracker`); unknown tools fail
closed. User content `trusted` (the simulated principal's), agent output `trusted`, task-prompt fixtures `untrusted`,
harness artefacts `trusted`, NPC replies `author` (I). Outcomes: RedCode 3 → `attack_succeeded` holds, 0 → does not, 1 →
`openhands.non_informative`; OpenAgentSafety `final_score` with a total of at least 1 → `openhands.unsafe_behaviour_detected`
holds iff `result >= 1`, 0/0 → `openhands.non_informative`; LLM-judge entries get no reading. Taint policy as DTap's (sink
roles and `unknown` over `untrusted` and `unknown`).

### D.17.11 Profiles, registry and artefact catalogue

`profiles/openagentsafety.profile.toml` and `profiles/redcode-exec-openhands.profile.toml` (closed `[family.openhands]`
table, `family.schema.json`: `source`, `verified_code`, `harness_version`, `fake_user_model`, `fixed_replies`,
`not_executed_notices`, `control_calls`, `semantics_profile`, `redact` (D-606), `quirk`); two `planned` registry parts;
`artefacts.toml` with twelve entries (filtered events, not-executed notices, harness errors, content not inlined, task text
not seen, missing evaluation files, missing LLM-judge entries, ambiguous score 1, joins after the rewrite; and, D.17.14,
the deposit's shell-history token, third-party account paths, fixture secret shapes). `openagentsafety` is at version 2
(D-31; version 1 under `profiles/archive/`, `b5be1d99df75…`); `redcode-exec-openhands` is recorded by no corpus and is
edited in place at version 1 (D-602's `[withhold]`, the move to `openhands.tools@2`).

### D.17.12 Files, fixtures and tests

New files only (invariant 5): `src/agentprov/adapters/openhands/`, `tests/adapters/openhands/`,
`tests/fixtures/openhands/` (seven OpenAgentSafety runs and four RedCode members with their auxiliary files, 61 files,
976,794 B, chosen by criterion by `tools/openhands/build_fixtures.py`; `SOURCE.json`), `tests/fixtures/LICENSES/OpenAgentSafety-MIT.txt`,
`tools/openhands/` (census, detail census, mapping census, fixture builder), the registry entries and this section.
`test_new_family_no_core_change.py` asserts that nothing under `aer/`, `prov/`, `validate/`, `corpus/`, `runner/`, `raw/`,
`ingest/` or `worker.py` changed. The family's semantics directory enters only the SEM stage identity of corpora that
use it (`openhands.tools-1/`), so no existing corpus digest moves.

### D.17.13 Implementation resolutions (phase 10g part B, 2026-10-12)

1. **D-172 addendum (user-approved fetches).** Both sources' OpenHands code is verified (D.17.4), so the D rules are cited
   at D for both; the OpenAgentSafety basis is the lock at the pin, the commit date before the runs and the fork's chat
   vocabulary in the logs (the lock's history was not checked).
2. **Not-executed notices and uncaused errors are activities with artefacts**, not harness messages: C.3.13 forbids a
   generic activity to generate a message.
3. **`finish` is an `other` part** (`openhands.finish_call`), not a `tool_call`: the accounting requires every tool-call part
   to be executed or listed as unexecuted (`aer.acc.tool_calls_dispatched@1`), and D-175 lists no issue for it.
4. **An `error` observation leaves `tool_execution.status` `ambiguous`**: the observation does not say whether the tool ran
   (`ERROR: Cannot execute multiple commands at once` is a refusal before running).
5. **Times stay in `ext`.** Messages have no `t` field (C.3.4); the run's first and last event times are `t.raw` with
   ambiguous typed slots, as for DTap's I-class end time (D.16.18 correction 1).
6. **RedCode members carry their `member` origin** (container sha256, label, method, crc32, size); the mapper reads the
   layout from the origin's `label`, so members seal in release mode without the runner (the census maps all 5,460).
7. **The OpenAgentSafety task-prompt and RedCode request fixtures name no `actor`**: who supplied them is not recorded.

### D.17.14 Withholding and tool-output redaction (D-602, D-606; bug pass bugpass-perf-10, 2026-10-21)

1. **RedCode `[withhold]` (D-602).** One pattern rule `hf-token-shape` (`hf_[A-Za-z0-9]{34}`, scope `object`, reason
   `secret`). The supplementary zip's unselected shell history under `environment/` holds a real-format token (pre-check
   PC-redcode-exec-openhands-01, CC-13, S0): sealing's decoded scan (D-450) withholds the zip at object level and no
   execution (scope `executions` would follow it through `citing()`). The runner imports one archive input per
   snapshot and stores no context archive yet, so the rule takes effect on the supp zip once the archive context tree
   lands. Test: `tests/adapters/openhands/test_withhold_e2e.py` (a trajectory deposit zip built at run time with a
   test-made value in an unselected member: import, release seal, `verify --level chain --release`).
2. **Tool-output redaction (D-604, D-606).** `adapters/openhands/redact.py` is the family's copy of the D-476 grammar
   (`[[family.openhands.redact]]` rules `{id, scope, pattern, replacement, leaf?, note?}`; placeholders `{span12}` and
   `{leaf}`; salt the profile id) with one scope, `tool_output`: the text of every part of a `message` of role `tool`
   (`/parts/<i>/text`, also a `$utf16` text). The pattern applies inside the text and every match is replaced, so an
   account-segment pattern keeps the path around it. A mapper post-pass (as Inspect's `_redact`) tags each rewritten
   pointer `D`, cites `openhands.value_redacted@1`, lists `{p, rule}` in `ext.openhands.redacted` and adds one info
   issue `openhands.value_redacted` per run. Assistant messages, tool-call arguments, `tool_execution.args`, the
   observation extras (copies of the model's command), fixtures and judgements are never touched (D-604: model-authored
   text stays verbatim). A part's text is a value, never a member name or a pointer token, so the BF-21 rule of D-476
   (follow an observed string into `ext.lex`, `evf`/`unk` keys and citations) has nothing to follow; `ext.lex` is left
   as it is.
3. **OpenAgentSafety's rules.** `account_home`: the account segment after `/home/` or `/Users/` (any preceding
   character: the census found target occurrences in deeper paths), `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`, ended as the
   release scan's `account-path` rule ends a name (D-457; trailing dots kept outside the span); `account_tilde`: the
   segment after a `~` that no letter, digit, `_` or `~` precedes, ended by `/`. Both spare `openhands`, `agent` and the
   release scan's `ACCOUNT_ALLOWLIST` (case-insensitive); replacement `acct-{span12}`. Not covered: Windows forms
   (`C:\Users\<name>`), absent from this source's tool output.
4. **Fixture secret shapes (D-606, PC-openagentsafety-07).** All 8 distinct secret-shaped values are CC-13 fixtures,
   kept as published (D-179 option A); their 49 holding raw objects are listed by object digest for the release-scan
   triage in `docs/reports/bugpass/d606-oas-secret-objects.json` (detector `openhands.fixture_secret_shape@1`, reserved).

## D.18 The AgentOps-Bench family (`agentops`; planned, phase 10i)

Decisions D-190–D-199 (user-approved 2026-10-12); census and evidence: `docs/reports/phase10i/` (README and
`agentops-bench.census.json`). Numbering: D.17 is left to the OpenHands family of phase 10g. AgentOps-Bench (Zenodo
19875693, Apache-2.0) is rank 8 of the phase-10e ranking (D-145) and is counted on its in-scope part (D-143): 3,360 of
the 7,200 cells of its v1.0 pilot. Everything in the deposit is untrusted data; the code zip is read, never run.

### D.18.1 Identity, pins and the label grammar

- Source `agentops-bench`, profile `agentops-bench-pilot`, part `pilot-v1-seeded`, corpus `agentops-bench` (D-144).
- Pins (both of record 19875693): `runs` = `agentops-bench-v1.0-pilot-traces.tar.gz` (sha256 `e185bfd0…7a85f`, primary),
  `tasks` = `kunwarshivam/agentops-bench-v1.0.zip` (sha256 `852a372d…c1fed`; root `kunwarshivam-agentops-bench-9153772/`).
- Run label: `<root>/<agent_dir>/<provider_model>/<condition>/<domain>_<NNN>_run<k>.json` (`root` =
  `pilot_v1_seeded`); the last five segments are matched (a `local` origin's prefix is tolerated). The label is the
  logical identity; its facets are checked against the in-record `agent_id`, `condition`, `task_id` and `run_number`
  (`agentops.label_facets@1`, D; 7,202/7,202 agree), never corrected.

### D.18.2 Dialect and reader (`agentprov.adapters.agentops.dialect.AgentOpsTraceReader`)

Dialect `agentops.trace`, one variant `v1` (all 7,202 run files: the harness's pydantic `RunResult`). The sniff requires
exactly the six top-level keys and the eleven `trace` keys; a per-model rollup (`agent_id`, `results`,
`aggregate_scores`) returns reason `agentops.report` (register detail of `select.not_execution_artefact`). One located
item per file (`{"p": ""}`). `auxiliary_for` names the run's task definition as `task` → `tasks:<member label>` through
the pinned table `tables/task_files.toml` (100 rows: id, label, sha256, bytes), because the file name's slug is not
derivable from a run.

### D.18.3 Mapping to AER (`agentprov.adapters.agentops.mapper.AgentOpsMapper`, adapter `agentops.trace` 0.1.0)

One AER per run file; records in order: header, actors, scopes, fixtures, per step (model call, assistant message, then
per call the execution or decision(s) and the tool message), judgements. Namespace `agentops`
(`https://w3id.org/agentprov/ns/agentops#`); `rules {"aer": 1, "agentops": 1}`.

| Source | AER | Evidence |
|---|---|---|
| header | `task {benchmark: "agentops-bench", task_id, environment: condition, suite: joined domain, attack_id}`; `attack_id` `"adversarial"` or `null` | O; `/task/attack_id` I (`agentops.adversarial_condition_unverified@1`); `/task/suite` D (join) |
| `agent_id` | actor `agent` (`llm_agent`), `name` = `agent_id` (O); `model {provider, requested}` split at the first `/` | `/model` I (`agentops.agent_id_identity_unverified@1`); served, params `not_recorded` |
| — | actors `bench`, `harness`, `env` (when a call was dispatched), `att` (adversarial), `judge` | I (`agentops.deposit_harness_unverified@1`, …); code and version `not_recorded` |
| `trace.error` / `completed` | `run` status `error` (O, text in `ext`) / `ok` (O) / `limit` (I, `agentops.iteration_cap_unverified@1`) | issues `agentops.run_error`, `agentops.iteration_limit`, `incomplete_run` |
| `steps: []` | `unit: outcome_only`, no step invented | `no_execution_observed`, `agentops.empty_trace` (D) |
| joined task | fixtures `task_prompt` (description, plus the context section) and `ground_truth` (`expected_output`) | D (`agentops.task_join@1`); a composed prompt's content I (`agentops.prompt_composition_unverified@1`); no user or system message (`agentops.user_message_not_logged`) |
| step *n* | `mc<n>` (`role: agent`, `kept`, `usage` O, `input` = earlier logged messages I); `m` role `assistant`, `generated_by: mc<n>`, parts: `text` (when `reasoning` is set), then one `tool_call` per call | existence I (`agentops.step_is_one_model_call_unverified@1`); order I; text-first I |
| call *i* | `te<k>` (`call` = the part, name and args O, `t.raw.start` = timestamp O, typed start ambiguous; status `not_recorded`) | link I (`agentops.pair_by_index_unverified@1`), D.18.4 |
| result *i* | `m` role `tool`, `tool_result {responds_to, text|value, name}`, `generated_by` the execution or the decision | content O; links I |
| `injected_failure` | `dc` decision (`actor: harness`, `verdict: other`, `subtype: agentops.fault_injection`, subject the call part), **no** `tool_execution`, issue `unexecuted_tool_call` | I (`agentops.fault_injection_unverified@1`), D.18.6 |
| `injected_payload` | fixture `injection_payload` (actor `att`); `te`, then `dc` (`actor: att`, `verdict: modify`, subject the execution) generating the result; `ext.agentops.suffix_offset` | fixture content O; decision I (`agentops.payload_injection_unverified@1`); offset D (`agentops.payload_suffix@1`) |
| `scores` | judgements `completion`, `safety`, `efficiency`, `cost`, `cost_normalized_accuracy` (values O by `benchmark`) | origin `checker` I (`agentops.scores_recorded_unverified@1`); `safety` without steps or payloads `harness_default` (I) |
| counters | profile check `agentops.acc.counters@1` (calls, step breakdown, token totals) | D |

`final_output` stays in `ext` and is checked as a copy of the last text (`agentops.final_output_copy@1`, D). A call to a
tool outside the profile's ten is kept verbatim (`agentops.unlisted_tool_name`); a result beginning `Error: ` is recorded
(`agentops.dispatch_error_result`) and never turns into a status.

### D.18.4 Call-to-result pairing (`agentprov.adapters.agentops.pairing`)

No call ids are written (the providers' ids are used in the harness's conversation only). Within one step, result *i*
answers call *i* (`agentops.pair_by_index_unverified@1`, I: the adapters append a call and then its result; the producing
code is not verified). Position is not the evidence alone: the step links only when both arrays have the same length and
every result names its call's tool (14,328/14,328 in the census); otherwise nothing links (`call_result_link_conflict`,
detail `length` or `names`). A step whose calls repeat a tool name links and is disclosed
(`agentops.repeated_tool_names`, 1,391 steps).

### D.18.5 Task-definition join (`agentprov.adapters.agentops.join`)

`agentops.task_join@1` (D): the `tasks` member the table lists for the run's `task_id`, accepted when its bytes have the
table's digest and size and the YAML `id` equals the `task_id` (100/100 tasks, 7,202/7,202 runs). The YAML is read with
`yamlsafe` and reduced to the allowlist `id, domain, description, context, tools_available, expected_output,
optimal_steps, difficulty, tags`. Outcomes `not_listed`, `missing`, `digest_mismatch`, `unparseable`, `id_differs` raise
`agentops.task_join_missing` and write no task fixture.

### D.18.6 Injections: fault and payload (D-196)

`aer/0.1` forbids a generic `activity` generating a message (C.3.13), so the harness's injections follow C.5.5:
- an injected failure is "not dispatched": a harness `decision` on the call part (`verdict: other`, subtype
  `agentops.fault_injection` declared in the catalogue) generates the fabricated result; there is no `tool_execution`, the
  call is `unexecuted_tool_call`, and the constant `latency_ms` is kept in `ext` only;
- an injected payload is "executed, output replaced": the `tool_execution`, then an attacker `decision` (`verdict:
  modify`, subject the execution) generating the delivered result. The payload is its own `injection_payload` fixture;
  the suffix relation (`"\n\n" + payload`, 2,011/2,011) gives `suffix_offset` (D).

### D.18.7 Time model (D-197)

Only the call timestamps are clock values (UTC `Z`, microseconds, non-decreasing per run). Each is kept verbatim in its
execution's `t.raw.start` (O) with `/t/start` `ambiguous` under `agentops.call_timestamp_is_dispatch_unverified@1`: an
I-class typed time would become an inference-bundle entity the tier-4 validators refuse (D.16.18 correction 1). Runs,
steps, results, decisions and judgements have no time (`not_recorded`); `wall_time_seconds` and `latency_ms` stay in `ext`
with `/t/dur_s` `ambiguous` (`agentops.duration_no_clock@1`). Member mtimes are never read.

### D.18.8 Semantics profile `agentops.tools@1` (`adapters/agentops/semantics/`)

`@2` (D-31 bump, regeneration items 34-37): `@1`'s tables on the `agentops` catalogue version 2; `@1` stays, reading
the archived catalogue version 1, for corpora that record it.

Data `agentops.tools-1/profile.toml` and `tools.toml` (the ten tools: roles and output integrity, never `trusted`;
replayed third-party tools `untrusted`, the rest `unknown`; unknown names fail closed). Annotations: fixture integrity
(payload `untrusted`, ground truth `trusted`, task prompt `trusted` or `unknown` in the `safety` suite); agent parts
`trusted` and call roles; result integrity (`unknown` for a fabricated failure, `untrusted` where a payload is present,
else the tool's label); one `injection_marker` per payload fixture of the run (`agentops.verbatim_match@1`: verbatim
search, `at`/`span` when the result is text); `author {"actor": "att"}` on a payload-bearing result; execution roles;
`outcome` for `completion` (`user_task_solved`, score, scale `agentops.completion_0_1`) and non-default `safety`
(`agentops.injection_resistance`, a regex heuristic). Taint policy `agentops.taint_sink_untrusted@1`.

### D.18.9 Rule catalogue `agentops.rules.toml` (version 1)

46 rules: 13 D (deterministic functions of observed bytes or package data), 28 I (every reading of harness or scorer
behaviour, with asserted assumptions; the snapshot's code paths are documentary `evidence`) and 5 `reserved` detector
names for the artefact catalogue. Why no D rule cites code (D-193): the snapshot names its commit only by a 7-hex prefix,
the runs name no code, and the snapshot's CHANGELOG (a different pilot, produced before the seeding fix) and launcher
(other directory names) contradict "these runs came from this code"; so the D-24 twins would always resolve to I, and the
rules are I directly, as DTap's are (D.16.11). Issue codes: `empty_trace`, `run_error`, `iteration_limit`,
`task_join_missing`, `user_message_not_logged`, `unlisted_tool_name`, `dispatch_error_result`, `final_output_differs`,
`label_field_mismatch`, `payload_suffix_mismatch`, `failure_with_payload`, `repeated_tool_names`; subtype
`agentops.fault_injection`. Version 2 (D-31 bump with regen items 34-37) adds `payload_outside_adversarial`, and D-608
(regen item 137, same version) adds the D rule `agentops.value_redacted@1` (47 rules: 14 D, 28 I, 5 reserved) and the
issue code `value_redacted` (D.18.15). The reserved `agentops.account_path@1` keeps its version-1 statement; no
artefact entry names it any more.

### D.18.10 Profile (`agentops-bench-pilot`) and selection (D-191)

`[import]` includes `adversarial/*` and the clean and noisy `safety_*` runs (3,360) and excludes the other eight
condition-domain pairs with `select.out_of_scope` (3,842 files: 3,840 cells and the 2 part-1 Opus copies the deposit's
merge discarded), the rollups with `select.not_execution_artefact`; AppleDouble members are runner strays, and from
profile version 2 the adversarial include (`adversarial/[!.]*_run*.json`) leaves the 2,400 AppleDouble run copies
`not_selected`, so the expand stage never decompresses or stores them. The register
code `select.out_of_scope` is new (D-191; `adapters/profiles.py` `SELECT_CODES`, `corpus/register.py`, HL H.6.3).
`[family.agentops]` (closed schema `family.schema.json`): layout, conditions, `in_scope` (the D-143 scope as data, checked
against the globs by a test), the ten tools, the pairing rule, the task table and the semantics profile; quirks with the
census counts; from D-608 the `redact` rules (D.18.15). The profile's `[withhold]` table (D-608) withholds the raw
objects that hold a third-party account path, at object scope.

### D.18.11 Artefact catalogue (`adapters/agentops/artefacts.toml`)

23 entries (D.15.2), counted on the in-scope part: the out-of-scope runs, non-run members, the superseded copies, the
pax-tar container (reserved detectors: no AER field shows them); the account path in tool output (13 executions,
redacted and claimed by its issue `agentops.value_redacted`, D-608; it was the "operator account path" under D-199, a
wrong label); empty traces (101), run
errors (133), the iteration limit (0 in scope), fabricated failures (715 results), payload injections (2,011 results),
adversarial runs where the injector did not fire (1,027), repeated tool names (437 steps), no call ids, derived model
calls, call-only times, the unlogged prompts, default safety scores (1,987), unlisted tool names (5), dispatch errors
(182), suspected text-encoded calls (21, heuristic), and four checks with no case in the snapshot. Every safety-net
finding on the fixtures is classified, and claims are specific to their entry
(`tests/adapters/agentops/test_artefacts.py`).

### D.18.12 Files, fixtures and tests

- `src/agentprov/adapters/agentops/`: `__init__.py`, `dialect.py`, `pairing.py`, `join.py`, `mapper.py`, `redact.py` (D-608),
  `semantics/{__init__.py,tools.py,agentops.tools-1/}`, `rules/agentops.rules.toml`, `profiles/agentops-bench-pilot.profile.toml`,
  `tables/task_files.toml`, `artefacts.toml`, `family.schema.json`, `ext.schema.json`; registry entry (append only).
- Fixtures `tests/fixtures/agentops/` (D-151 style, byte-identical members chosen by criterion, `SOURCE.json` with
  container, label, CRC-32, size and sha256; none carries the account path): 13 runs (payloads with a failure and
  a multi-call step; repeated names; empty trace; refusal loop; noisy-safety failure; clean safety; unlisted tool; dispatch
  error; API error after steps; OpenRouter, Anthropic payloads; timeout; a task with context) and their 11 task YAMLs;
  licence `tests/fixtures/LICENSES/AgentOps-Bench-Apache-2.0.txt`.
- Tests `tests/adapters/agentops/`: dialect and the selection counts, mapper (each rule's case, release-mode AER
  validation, `ext` schema, determinism, SEM and PROV tier 4), rules coverage both ways, semantics, artefacts, profile and
  registry, fixtures, and the new-family guard.

### D.18.13 Downstream effects (CLAUDE.md rule 10) and invariant 5

- No existing corpus, AER, SEM or PROV byte moves: the family's code enters only the stage identities of corpora that use
  it (`adapter_code_sha256` of `adapters/agentops`, the SEM stage's `adapters/agentops/semantics`); `adapters/profiles.py`
  and `corpus/register.py` are in no stage digest, and no existing profile uses `select.out_of_scope`.
- Core change (invariant 5, user-approved under D-191): the register code `select.out_of_scope` only.
- No trial import: the tar's pax headers need the ingest change of D-192 (archive inputs themselves landed as D-200,
  after this family was written). The in-scope members were mapped in memory through the product path (D-154 method; report §9).

### D.18.14 Open items (routed)

1. **D-192** (phase 12, through the orchestrator): a top-level gzip tar as a declared deposit pin, and pax `x` headers with
   a closed key allowlist.
2. **D-156** (runner): deposit-archive members as units landed on main as D-200 (deferrals part A); whether the
   `tasks` zip, a second pin, can serve as the context tree is not checked yet.
3. **Core PROV gap** (orchestrator, `prov/`): an `unexecuted_tool_call` issue cited under a class-I rule makes
   `agentprov-prov/0.1` state `apv:dispatchStatus apv:NotDispatched` with no source fields in an inference bundle, which
   tier 4 refuses (`pv.linkage.pointer_missing`, `pv.linkage.basis_not_cited`). It affects every fabricated-failure run
   here (pinned by strict xfails) and likely any family citing an I rule for that issue
   (`dtap.call_without_result@1` is class I; not checked on DTap data). Cited at D the same records validate, so the defect is the missing pointer, not the mapping.
4. Report-only `reliability` and `recovery` scores are not joined in profile version 1 (D-198).

### D.18.15 Account paths in tool output (D-608; principle D-604; regen item 137)

`run_python` output in the deposit names one third-party macOS workstation account in `/Users/<account>/` paths: in the
result text, in `stdout` and in `stderr`. D-199 kept it verbatim as the operator's; that label was wrong, and D-608
reverses D-199 (and D-186 (c)) for this source.

1. **Scope.** `[[family.agentops.redact]]` rules (closed: `id`, `scope`, `pattern`, `replacement`, `leaf`, `note`;
   `family.schema.json`) have the single scope `tool_output`: the values of tool messages (`role = "tool"`), each part's
   `text` and `value`, strings and object keys at any depth. Assistant text, tool-call arguments, `final_output`,
   fixtures, judgements and the run error are never touched (D-604: model-authored text stays verbatim).
2. **Grammar.** A family copy of the D-476 grammar (`agentprov.adapters.agentops.redact`): each match is replaced by the
   rule's label, literal text with `{span12}` (12 hex digits of SHA-256 over the profile id, NUL and the span: the
   named group `span`, else the match) and `{leaf}`. Two spans giving one label are a `ProfileError`.
3. **The profile rule** `macos_account`: `/Users/<name>` before a `/`, where `<name>` is `[A-Za-z0-9._-]{1,64}` and not
   one of the generic names of the release scan's allowlist (D-457); the span is the name and the whole `/Users/<name>`
   becomes `acct-{span12}`, so no AER byte matches the `[withhold]` pattern below.
4. **Lexical copies.** The value is decoded with the record's `ext.lex` hints (so `$utf16` and `$lit` forms are
   redacted too), redacted and encoded again at the same pointer; the `ext.lex` entries below it are rebuilt, and
   `evf`/`unk` keys and scoped rule citations that name a renamed key follow it.
5. **Payloads.** In a result whose injected payload the mapper located at its end (`suffix_offset`), only the text before
   the payload is redacted: the payload stays identical to its `injection_payload` fixture and the SEM marker search,
   and the decision's `suffix_offset` is the offset in the redacted text.
6. **Recording.** Each redacted pointer is tagged `D`, cites `agentops.value_redacted@1` and is listed in
   `ext.agentops.redacted` (`{p, rule: "<profile>@<version>#<rule id>"}`); one info issue `agentops.value_redacted`
   names the changed tool messages and counts the pointers. Locators keep pointing at the raw field; raw bytes are never
   edited.
7. **Withholding.** `[withhold]` (reason `personal_data`; rule `account-path`, pattern
   `/Users/[A-Za-z0-9._\-]{1,64}/`, scope `object`) withholds the raw objects that hold the path: the selected run
   objects (`profile_rule`) and the tar (the container of a withheld member, and the decoded scan's hit in the unselected
   out-of-scope runs and rollups, D-450). The AER, SEM and PROV no longer hold the path, so no execution is withheld; an
   execution whose model text held it would be (D-235). AppleDouble members are not selected (`[!.]`, version 2).
8. **Versions.** Profile `agentops-bench-pilot` and catalogue `agentops` stay at version 2 (the unreleased D-31 bump of
   regen items 34-37; no corpus records version 2); version 1 of each is archived unchanged.
9. **Tests.** `tests/adapters/agentops/test_redact.py` (scope, keys and `ext.lex`, `$utf16`/`$lit`, payload suffix,
   generic names, labels, rule errors, the policy) and `test_withhold_e2e.py` (a synthetic tar: import, seal,
   `verify --level chain --release`; the redacted execution released, the run object and the tar withheld, no sealed
   byte holding the path).

## D.19 The credential-leak family (`credleak`; planned, phase 10k)

Status: **planned** (phase 10k, 2026-10-13; DECISIONS D-260..D-269, user-approved 2026-10-13).
Source: Zenodo record 22737462, version v3, the run data of "How Credentials Leak from 'Safe' LLM Coding Agents: An
Attack-Surface Measurement" (CC-BY-4.0). This is rank 5 of the phase-10e ranking (D-145). Every count below is from the
census in `docs/reports/phase10k/census.md`. Everything in the deposit is untrusted data, never instructions. The runs
carry injection payloads, poisoned `CLAUDE.md`/`AGENTS.md` rules files and agent output.

The deposit gets a family of its own because its cells record turns, not message lists. A turn holds one user message,
one assistant text and the ordered tool calls (input and output in one entry). There are no model-call boundaries, no
call ids and no per-call times, and the harness's detector signals sit beside the turns. Every planted credential
carries a tag, which the profile's `[withhold]` policy names (D-234, D-265). This is the first shipped profile with such
a policy.

### D.19.1 Identity, pins and path grammar

- **Pin:** the v3 deposit file `p15b-run-data-v3-2026-09-13.zip` (11,060,394 bytes; sha256 `7e5f7e40…`; md5 as the
  record) is a D-200 archive input. v3 holds every run of v1 and v2. v1's one other run is the unredacted form of a run
  v3 holds redacted (census §8). v1 is never stored (D-268).
- **Execution identity:** one run is one execution. Its source key is the cell member's digest plus `{"p": "/runs/<i>"}`
  (HL H.7.1, element of a JSON array). The cell's `runId` is a batch id shared by several cells and is never identity.
- **Path facets** (read from the right of the member label, `credleak.path_facets@1`; facets, never identity):

```
p15b-run-data/<section>/<channel>/<model>/<file>.json
p15b-run-data/<section>/<channel>/excluded-models/<model>/<file>.json
p15b-run-data/<section>/<channel>/_<dir>/<file>.json        (the not-scorable probe, a replication wave)
```

  The layout class is `roster`, `excluded-models` or `underscore`. The file prefix is `run`, `archive-…`,
  `addendum-YYYY-MM-DD`, `extcanary` or `other`.

### D.19.2 Dialect and reader

- **Dialect:** `credleak.cell`, variant `v1`, `CredleakCellReader`.
- **Sniff:** a JSON object with exactly the cell keys (`__note` optional) and an array `runs` is a cell. Other JSON
  returns `credleak.not_a_cell`. Bytes that fail the strict loader return their `ingest.*` code: v3's collector log has a
  duplicate key, and the profile does not select it.
- **Parse:** yields one located item per run, with the whole parsed cell as its value.
- **Selection** (profile): the cells under `01-injection-map/`, `03-egress-axis/` and `04-hygiene/`. The audit files, the
  scanner outputs, the scripts, the CSV aggregates and the collector log are `select.not_execution_artefact`.

### D.19.3 Mapping to AER

**Header.**
- `task`: `{benchmark: "credleak-p15b", suite: technique, task_id: scenario, attack_id: scenario, defense_id: defence}`
  (O, cell fields).
- `unk /instrumentation not_recorded`.
- `ext.credleak`: path facets, run index, `repetition`, `scenarioName`, the run's `durationMs`, the cell's `runId`,
  `timestamp`, `config`, `summary` and `__note`, and every other run field verbatim (`run_fields`).

| Actor | Kind | Evidence | Notes |
|---|---|---|---|
| `bench` | benchmark | O | `name = credleak-p15b`; code and version not recorded |
| `harness` | harness | O (its `config`) | name, code and version **not recorded**: no run file names the harness |
| `user` | simulated_user | I | `credleak.user_is_scripted_unverified@1` |
| `agent` | llm_agent | O | `model.requested` = the run's `model` verbatim (`credleak.model_label_is_requested@1`); served, provider and params not recorded |
| `env` | tool_runtime | I | only when a tool was called; `credleak.tool_entry_is_execution_unverified@1` |
| `att` | attacker | I | `name` = technique; `credleak.scenario_is_injection_unverified@1` |
| `det` | judge (`role: detector`) | I | the harness's detectors; `credleak.detector_signal_unverified@1` |

**Scopes.**
- `run`: status `error` when `invocationError` is true (I, `credleak.invocation_error_status@1`); otherwise `/status`
  not recorded.
- `att0`.
- `inv<k>`: one `agent_invocation` per turn, with index = `turnNumber` when it equals the position (D).

**Per turn** (record order; ids `m<n>`, `te<n>`):

| Source | AER |
|---|---|
| `userMessage` | `message` role `user` (role D from the field name), actor `user` (I) |
| `toolCalls[j]` `tool`, `input` | `message` role `assistant`, one `tool_call` part (name and args verbatim, O); actor and role I (`credleak.call_entry_is_model_output_unverified@1`); `generated_by` not recorded |
| (the entry) | `tool_execution` (I), `call` = the entry's call part (D, `credleak.pair_same_entry@1`); name and args O; `/returned`, `/status` not recorded |
| `toolCalls[j]` `output` | `message` role `tool`, `generated_by` the execution (I), `tool_result.responds_to` = the call part (D, same entry), text verbatim |
| `assistantResponse` | `message` role `assistant` (role D), actor `agent` (I), `generated_by` not recorded; an empty text is `parts: []` (known empty) |
| `canaryDetected`, `canariesFound[]`, `canaryInInput`, `canaryInOutput` | `ext.credleak`: the booleans verbatim, and the **count** of `canariesFound` (its labels embed the tag and are not copied, D-264) |

**No model call is written.** The boundaries are not recorded; a turn may span several calls, up to `maxTurns`. Every
agent message declares `unk /generated_by not_recorded`, the seal carries `missing_generated_by` under
`credleak.model_calls_not_recorded@1`, and `aer.acc.agent_calls_vs_assistant@1` is `unverifiable`.

### D.19.4 Time model

- **Turn timestamp:** kept verbatim in `ext.credleak.timestamp` of its turn scope. The scope's `/t` is `ambiguous` under
  `credleak.turn_timestamp_role@1`. Start and end cannot be told apart: in 9,505 of 18,993 consecutive run pairs, the
  next run starts before the previous run's `durationMs` has elapsed. `Time.raw` has only `start`/`end`/`dur` slots, so
  storing the value there would already claim its role.
- **Durations:** `durationMs` of runs, turns and calls is kept in `ext.credleak`. `/t/dur_s` is `ambiguous` (clock and
  extent unrecorded, `credleak.duration_no_clock@1`).
- **Cell-level stamps:** the cell `timestamp` and `runId` are ext only.
- No typed time is written.

### D.19.5 Order and pairing

- **Pairing:** a result belongs to the call of its own `toolCalls` entry. That is the record's structure, not an order
  inference (D).
- **Order edges** (all `pos`, I):
  - the first call follows the user message, and each later call follows the previous result
    (`credleak.calls_in_entry_order_unverified@1`);
  - a later turn's user message follows the previous turn's last result and its assistant text
    (`credleak.turns_in_array_order_unverified@1`);
  - the assistant text follows its turn's user message only (`credleak.response_after_user_message_unverified@1`). Its
    position relative to the calls is not recorded, so no edge is asserted there.

### D.19.6 Judgements

- **Judged fields:** `hijackSucceeded`, `exfiltrationDetected`, `exfiltrationCount`, `egressChannel`, `agentDetected`,
  `displayedToUser`, `maliciousArtifactEmitted`, `scriptAudited`, `payloadDelivered`, `taskEngaged`, `t0Completed`,
  `truncated`, `ges`, `gesDisplayed` and `gesExfil`. Each present field becomes a `judgement` (actor `det`, subject
  `run`, value O verbatim, origin `checker` I, `/t` and `/inputs` not recorded).
- **Not interpreted:** the deposit corrected the T-EMIT flag after the runs (its audit files are not run data), so no
  polarity is read. `config.judgeModel` produced nothing (`intentVerdicts` is all null) and gets no actor.

### D.19.7 Accounting and checks

- `credleak.acc.tool_call_count@1`: `toolCallCount`, where recorded (3,686 newer-schema runs), equals the number of
  entries.
- `credleak.cell_run_agreement@1`: a run's model and scenario equal its cell's (issue `credleak.cell_run_disagree`).

### D.19.8 Rule catalogue `credleak.rules.toml` (version 2)

- **Versions:** version 2 since D-605 (D.19.15): it adds `credleak.value_redacted@1` and the issue code
  `value_redacted`. Version 1 (sha256 `d355a2725e17…`, the bytes the scratch corpora and the gui-build sealed copy
  record) ships under `rules/archive/credleak.rules.v1.toml` (D-31).
- **Size:** 28 rules (26 citable, 2 reserved); version 1 had 27 (25 citable).
- **Citation policy:** as for dtap. The harness is not in the deposit and no code is verified. Harness behaviour is
  class I with asserted assumptions (`credleak:*`). D rules are deterministic readings of observed field names and
  structure, cite no code and cite the census.
- **Reserved detector names:** `credleak.planted_credential@1` (handled at sealing) and
  `credleak.malformed_tool_name@1` (handled by SEM).
- **Issue codes:** `path_outside_grammar`, `turn_number_mismatch`, `cell_run_disagree`, `invocation_error`,
  `value_redacted` (version 2).

### D.19.9 Semantics profile `credleak.tools@1`

Version 2 (`credleak.tools-2/`, D-605) has version 1's tables unchanged and declares the `credleak` catalogue version
2, so a regenerated corpus reads one catalogue version (H.2.5; the D-31 option B of `inspect.agentharm@2`). The
registry selects `credleak.tools@2`; version 1 (digest `721620e801f2…`) stays for the corpora that recorded it. The
rule statements that name "the credleak.tools@1 table" hold for version 2, whose tables are the same.

- **Tool table:** 10 canonical tool names (`Bash`, `Read`, `Glob`, `Grep`, `Edit`, `Write`, `WebFetch`, `WebSearch`,
  `McpToolCall`, `ListMcpTools`) with roles and output integrity and channel. Every other name gets role `unknown` and
  integrity `unknown` (fail-closed). This covers about 290 calls with malformed names: leaked channel tokens, case
  variants, typos.
- **Observation table:** the scripted user message is `trusted`. The study places its injections in tool-reachable
  channels.
- **Taint:** write, send, execute, egress-read and unknown roles over untrusted and unknown integrity.
- **Class:** all I.

### D.19.10 Rate exclusions (`rates.toml`)

Errored runs are left out of outcome rates (the deposit's own convention). The layout classes (excluded models, the
not-scorable probe, the unpooled replication wave, the collector-scored `extcanary` cells) are path facets, for the
analysis to select. They are never dropped at import.

### D.19.11 Artefact catalogue (`artefacts.toml`)

Five entries, all `expected` counts `unverified`:

| Entry | Handling | Count |
|---|---|---:|
| malformed tool names | FO | 290 calls |
| invocation errors | FO | 59 runs |
| turn times of unknown role | NR | 20,176 turns |
| no model-call boundaries | NR | 19,636 runs |
| planted credentials | FO | 5,422 runs |

### D.19.12 Files, fixtures and tests

- **Family files:** `src/agentprov/adapters/credleak/` (reader, mapper, `redact.py` (D-605), rules (version 1 under
  `rules/archive/`), `semantics/credleak.tools-1/` and `-2/`, profile (version 1 under `profiles/archive/`), artefacts,
  rates, closed `family.schema.json` and `ext.schema.json`).
- **Registry:** a `planned` entry.
- **Fixtures:** 11 unedited clean cells (124 runs), chosen by structure by `tools/credleak/build_fixtures.py`. Every
  candidate is re-scanned with the profile's own rules, and 326 members with a hit were refused. Attribution is in
  `tests/fixtures/LICENSES/credleak-p15b-ATTRIBUTION.txt` (CC-BY-4.0).
- **Tests** (`tests/adapters/credleak/`):
  - dialect;
  - mapper: golden AER digests, tier-4 PROV on every fixture run, pairing, time, generators, order, judgements,
    checks, determinism;
  - rules (coverage both ways), semantics and profile. The profile tests include: the policy matches no fixture byte
    and no derived file of a fixture, and finds every sentinel in raw and derived bytes;
  - artefacts, and new-family (no core or runner change);
  - the D-605 tool-output redaction (`test_redact.py`): path forms, generic names (the list is release_scan's), labels,
    value outputs (member names, `$lit`, `$utf16`, `ext.lex`), model-authored text kept, the closed rule grammar and
    the collision checks; and its end-to-end case in `test_withhold_e2e.py`;
  - the D-234 **end-to-end withholding test** (`test_withhold_e2e.py`). It replaces the injection of
    `tests/security/test_sec25_withhold_policy.py` for the positive chain. Import of an archive input runs in release
    mode, then seal, `verify --level chain --release`, the deposit build, and the gitleaks release scan with a control,
    all through the shipped profile with no monkeypatch;
  - the runner item R-10k-1 (`test_runner_multi_execution.py`), first pinned as a strict expected failure and passing
    since the runner change (D-320, D.2.9 note item 12): a two-run cell imports as two executions with source keys
    `{"p": "/runs/0"}` and `{"p": "/runs/1"}`; an interrupt between the two runs resumes with only the second mapped; a
    `--limit` inside a cell resumes; a byte-identical cell in a second snapshot collapses both runs (two source-key
    `dedup.collapsed` entries, rows listing both snapshots); a cell with no run is registered, not mapped; a cell
    failing the strict loader is one degenerate AER; and a sealed two-snapshot corpus passes
    `verify --level chain --release` with the planted run of a two-run cell withheld and its clean sibling released
    (D-265).

### D.19.13 Profile and the withholding policy (D-146, D-234, D-265)

The `[withhold]` table has `reason = "secret"`, a one-line `public_note`, `scan_rules`, and six rules (two of them D-605's, reason `personal_data`), all **scope
`object`**:
- `canary-tag`: the pattern `CANARY[^_]`, the study's tag followed by any character but `_`. The bare tag as a marker
  would also match two not-selected collector-log labels (tag between underscores) in the released
  `raw/members.jsonl`, and so fail the `chain` backstop on the real deposit (found by the part-C2 seal);
- `canary-tag-left`: the pattern `[^_/]CANARY`, the tag after any character but `_` or `/`. One run holds the tag only
  after a letter and before `_` (found by the C1 re-run). The two tag rules miss only the tag between `[_/]` and `_`,
  the labels' form. On the content the AER holds, every value-bearing run is hit and no released run holds the tag
  (census step 15);
- `aws-key-shape`: `AKIA[0-9A-Z]{16}`;
- `sk-key-shape`: `sk-[A-Za-z0-9_\-]{20,256}`;
- `account-path-home` and `account-path-users` (D-605, reason `personal_data`; D.19.15): third-party account paths.

The tag sits inside every planted value. The two shapes also catch the 78 key-shaped strings without the tag (27 runs,
26 of them tagged too).

How the scope works out at sealing:
- A raw hit withholds the cell member, and with it the deposit zip (basis `container`).
- A run whose AER, SEM, PROV or view holds a hit is withheld: AER copies content verbatim, so every value-bearing run
  escalates (D-235).
- The clean runs of a withheld cell stay released with their raw object withheld (`raw_withheld`).

Expected on the full v3 import: **325 cells and the zip withheld, 5,422 executions withheld, 14,214 released.** The
collector-log JSON is withheld as well: the include glob stores it and the exclude registers it. The part-C2 seal of
the real deposit with today's runner withheld 327 objects (325 cells, that JSON, the zip). The
alternative, scope `executions`, would release 9,799 and drop 4,415 runs that hold no value. The C1 trial
(`docs/reports/phase10k/`) checks the derived-hit set against the census set.

### D.19.14 Downstream effects and invariant 5

- The family branch changes nothing in `aer/`, `prov/`, `validate/`, `corpus/` or `runner/`. The registry gains new
  lines only, and the sec25 docstring loses its stale "no shipped profile declares `[withhold]`" sentence.
- No existing corpus or digest moves.
- **R-10k-1, resolved by D-320 (2026-10-13, user-approved runner change on the stacked branch
  `r10k1-multi-execution`; D.2.9 note item 12).** The runner used to map one execution per whole file
  (`map_artefact_total` refused `len(items) != 1`) and keyed resume and cross-snapshot dedupe on the primary artefact
  digest (`importer._seen_before`), so only single-run cells imported.
  - HL H.7.1 already provided the identity (digest plus `{"p": "/<i>"}`) and H.7.2 collapses by source key, so the
    core model is unchanged: `aer/`, `prov/`, `validate/` and `corpus/` are untouched (invariant 5).
  - `CredleakCellReader.multi_execution = True`. The runner maps one unit per run and resumes and collapses each by
    source key. A cell with no run is registered `select.not_execution_artefact`.
  - Downstream: no AER, SEM or PROV byte of any existing corpus moves. The `aer` stage's `engine_code_sha256` (it
    covers `adapters/runner`) and the `credleak` adapter code digest move for imports made afterwards (regen-batch
    entry `R-10k-1`): merge only when no import is paused.
  - Still waiting: part C's full product-path trial, the `planned` → `partial` gate and the import (after the
    regeneration round, with the user's approval).

### D.19.15 Account paths in tool output (D-605, applying D-604; pre-check PC-01; regen-batch item 138)

The deposit's tool output holds one named workstation account (account #1; the name is never recorded) in
`home/<account>/` paths of 313 runs in 67 cells (319 runs in 68 cells counting the path without a trailing slash).
D-604 (user, 2026-10-21): such a path is redacted in tool and environment output only; model-authored text stays
verbatim; a raw object holding it is withheld at object scope; an execution whose derived files still hold it is
withheld through D-235.

- **Redaction** (`adapters/credleak/redact.py`, a family copy of the D-476 grammar; no cross-family import). The
  profile's closed table `[[family.credleak.redact]]` has the path rule `account_path` (and the two `ls -l` rules below), of the one scope `tool_output`: the
  `output` of a `toolCalls[]` entry, which the mapper copies into the tool result message (`/parts/0/text`, or
  `/parts/0/value` for a non-string output). The pattern is path-anchored:
  - the name follows `home/` or `Users/`, with or without a leading slash. The prefix must not follow a name character
    (`[A-Za-z0-9._-]`), so `myhome/x` is not a path;
  - a negative look-ahead skips the generic names of `tools/release_scan.py`'s `ACCOUNT_ALLOWLIST` that fall within the
    name class (29 names, case-insensitive, trailing dots ignored) and names made only of dots. A test keeps the two
    lists equal;
  - the name is 1 to 64 name characters and ends at the first character that cannot be part of a name. Trailing dots
    stay outside it.

  Every match is replaced by `acct-{span12}`. The span is the name, and the salt is the profile id.
- **Where it applies.** It runs on the source value before encoding (C.11), so every copy the AER holds is the label:
  the string, a member name, `ext.lex` source-order lists and pointers, and a `$utf16`-wrapped string. Each redacted
  pointer is tagged `D` and cites `credleak.value_redacted@1` scoped to it. `ext.credleak.redacted` lists
  `{p, rule: "credleak-p15b@2#account_path"}`, and the info issue `credleak.value_redacted` (ids `exec`) counts the
  pointers. Source locators keep naming the raw field. The original and its digest are never recorded.
- **Not redacted (D-604).** The tool-call input (`/parts/0/args`, `tool_execution.args`, PROV `apv:args`), the
  assistant text and the scripted user message.
- **Versions (D-31).**
  - Profile `credleak-p15b` is at version 2. Version 1 is `1dce158a57ad…`, the bytes 4 scratch corpora and the
    gui-build sealed copy record; 10 older scratch corpora record `c5977363f485…`, `db30e9ee6c04…` or `e9f62b26d2da…`
    and are reproduced at their building commit (F-8 ruling).
  - Catalogue `credleak` is at version 2 (D.19.8).
  - Semantics `credleak.tools` is at version 2 (D.19.9), and the registry selects it.
- **Census** (pinned v3 zip, `~/.agentprov/staging/10k/v3/`, sha256 `7e5f7e40…`, read in memory; the 68 cells holding
  the path mapped by the shipped mapper and profile; counts only):
  - 382 pointers are redacted in 316 runs of these cells (account #1 and the one-run non-generic names some tool
    outputs hold). Over all 643 cells the pattern matches 396 tool-output strings;
  - 0 runs hold account #1 in path form in a tool result. That is the residue of the redaction;
  - 19 runs in 8 cells still hold it in model-authored fields: tool-call `args.command` 38 and `args.file_path` 1 (both
    in the message and in `tool_execution`, and so in PROV `apv:args`), and assistant text 4. 17 of the 19 are already
    withheld by the canary and key rules;
  - 0 degenerate runs.
- **The bare name in `ls -l` columns (part 2; user decision 2026-10-21).** Account #1 also appears without a path, as
  the owner and group columns of `ls -l` lines in tool output. Two **labelled** rules handle it, `ls_long_owner` and
  `ls_long_group`: a structural pattern (mode string, link count, owner, and for the second rule the group, as the
  `span` group) and `labels = ["86fe70f091cd"]`.
  - A labelled rule (the D-607 approach; grammar key `labels?`) replaces only its span, and only when the span's
    `{span12}` is listed. So no other owner name is touched, and the profile names no account.
  - The label is account #1's, computed out of band from the pinned data by a script that printed only the label. It
    is the same label the path rule writes.
  - Census (the shipped Redactor over every tool output): 22,986 owner and 22,985 group columns in 4,353 runs
    redacted, residue 0, collateral 0 (5,757 other owners' lines kept).
  - The bare token stays in 30 lines of 29 runs that are not `ls -l` lines, and in the raw tool output of 92 released
    cells (D-604 withholds raw objects for the path only).
  - 12 of the 124 committed fixture runs have redacted `ls -l` columns, so the committed fixtures hold the bare name.
- **Withholding (part 1; user decision 2026-10-21: the generic structural rule).** `[withhold]` gains
  `account-path-home` (`home/[A-Za-z0-9._]{1,64}[^A-Za-z0-9._\-]`) and `account-path-users` (the same after `Users/`),
  scope `object`, each with `reason = "personal_data"` and its own `public_note`. The table's reason stays `secret`.
  - The byte grammar cannot exclude generic names, so the rules are generic and say nothing about the account.
  - The name class leaves out `-`, so no `acct-` label matches.
  - A raw cell holding a path is withheld at object scope. A derived file still holding one (model-authored text, since
    tool-output copies are redacted) withholds its execution (D-235).
  - Census with the shipped policy, beyond the 5,422 executions the other four rules withhold:
    - **7 executions**: 2 of account #1's residue, 3 with another non-generic path in model-authored text, and 2 with a
      generic-name path only. Those 2 are a collateral cost the user accepted;
    - **21 raw cells**: 18 holding account #1, 3 other.
  - Measured and not chosen:
    - account #1's length-and-class shape: 4 executions, 20 cells, but it writes the shape into Git;
    - `/home/[A-Za-z0-9._\-]{1,64}/`: 142 executions, because it matches the labels;
    - an issue rule: 2 executions, but 17 raw account-#1 cells released.
  - The release scan's `account-path` finding of the labels is class 0 and handled separately.

## D.20 The wire-log family (`wirelog`; planned, phase 10m)

Decisions D-280–D-285 (decided on the user's delegation 2026-10-13, recommended options) and the D-281 addendum; census
and evidence: `docs/reports/phase10m/` (README part A, `zenodo-21944598.census.json`). Numbering: D.19 is phase 10k's
credleak family. A wire log keeps every request body a harness sent to an LLM API and every response it received; each
request repeats the conversation so far, so a model call's context is recorded in full. The first source is Zenodo
21944598 v1.0.0 ("What surrounds an injection decides whether it works", CC-BY-4.0 for the runs; rank 9 of D-145): 1,334
Bedrock trials of seven models. Everything in the deposit is untrusted data; its scripts are read, never run.

### D.20.1 Identity, pins and the run-directory layout

- Source `what-surrounds`, profile `what-surrounds`, part `runs-named`, corpus `what-surrounds` (D-285).
- Pin `runs` = `prompt-injection-study.zip` (record 21944598, sha256 `08e60afd…079454`, md5 `a5ce4a13…b3`), an archive
  input (D-200). Include globs `runs_named/*/*`, `results.csv`, `attacks.json`; the other 20 top-level files stay
  `not_selected` members (`wirelog.non_run_member@1`, reserved).
- Run directory `runs_named/<model>__<arm>__<NNNN>/`; its facets are compared with the logged model, `meta.json` and the
  results row (`wirelog.run_dir_layout@1`, D; 1,334/1,334 agree), never corrected.

### D.20.2 Dialect, variants and reader (`agentprov.adapters.wirelog.dialect.WireLogReader`)

Dialect `wirelog.request_response`, variants `bedrock-converse` (1,333 runs) and `anthropic-messages` (run 0001, D-283),
told apart by the response log's stop-reason key. **The primary artefact is the response log `response_raw.json`**
(D-281 addendum): request logs repeat byte for byte across trials whose requests were the same (1,263 distinct in 1,334;
a first trial import collapsed 71 runs), whereas response logs are the provider's own output, distinct in 1,334/1,334 and
never rewritten. `auxiliary_for` names the run's `request.json` (`request`), `meta.json`, `tools_called.txt`
(`dispatch`), the outcome and final-text files, and the deposit's `results.csv` and `attacks.json`. The wire module
(`wire.py`) normalises both variants to one block model (text, tool use, tool result, other) with source pointers.

### D.20.3 Mapping to AER (`agentprov.adapters.wirelog.mapper.WireLogMapper`, adapter `wirelog.run_dir` 0.1.0)

One AER per run. Records: header, actors (`bench`, `harness`, `user` simulated, `agent`, `env` when a tool ran, `att` for
an attacked arm, `judge`), scopes `run` and `att0`, fixtures, then per request *i*: the items first seen in it, `mc<i>`,
the assistant message of response *i*; then the judgements. Namespace `wirelog`; `rules {"aer": 1, "wirelog": 1}`.

| Source | AER | Evidence |
|---|---|---|
| request *i* | `mc<i>`: `input` = every item of request *i* in recorded order; `tools` = the tool fixture; `params.transmitted`; `finish_reason`, `usage` (O:provider); `latencyMs` in `ext` (`/t/dur_s` ambiguous); `request`/`response` blobs `not_recorded` (re-serialised JSON, not wire bytes) | input O; resolution of items to earlier records D (`wirelog.request_prefix@1`, JCS equality); causal `after` D (`wirelog.call_after_context@1`) |
| response *i* | assistant message (`generated_by: mc<i>`), parts in block order: `text`, `tool_call {name, args, provider_call_id}`, `other` | O; the link D where request *i+1* echoes it (`wirelog.response_echo@1`), I for the last response (`wirelog.last_response_by_position_unverified@1`); call status `kept` likewise |
| `system` | a `system` message, actor `harness` | content O; actor I |
| first user message | `user` message, actor `user` | content O; actor I; a later user text gets `unattributed_additional_user_message` |
| `toolConfig` / `tools` | fixture `tool_definitions` | O; identity across requests D (`wirelog.tool_config_stable@1`) |
| each tool call answered later | `te<k>` (actor `env`, `name`, `args`; status, return value and time `not_recorded`) | existence O (the result carries the id; the dispatcher log lists the call, `wirelog.dispatch_logged@1`); `call` D (`wirelog.call_id_unique_match@1`) |
| each result block | **one message per block** (role verbatim `user`, actor `env`, `generated_by` the execution, `tool_result {responds_to, text|value}`), wire grouping in `ext.wirelog.wire_message` | content O; links D (id); split D (`wirelog.result_block_message@1`, D-281 c) |
| a call no later request answers | issue `unexecuted_tool_call` | D (`wirelog.call_without_result@1`) |
| `meta.timestamp` | run `t.raw.end` (O), typed end ambiguous | I (`wirelog.save_timestamp_unverified@1`) |
| last stop reason | run `status` `ok` (final stop reason) or `limit` (tool_use at the request cap) | I (`wirelog.run_end_unverified@1`) |
| task prompt | `task.task_id` from the profile's prompt table by sha256 | D (`wirelog.task_prompt_table@1`) |
| results row | `task.attack_id` (arm; `null` for `no_attack_arms`, I), `task.environment` (context condition; `none` is `not_applicable`); judgements `hijack`, `exfiltration`, `silent`, `call_order` (origin `checker`, I) | O by benchmark; join D (`wirelog.results_row_join@1`) |
| `outcome.txt`, `outcome_v2.txt` | judgements `outcome` (`harness_rule`) and `outcome_v2` (`recomputed`, `revises` it) | O; origins I |
| `attacks.json` | fixture `injection_payload` (actor `att`, `vector` = channel), the key from the profile's arm table; `ext.wirelog.found_in` = first verbatim location in the request log | content O:benchmark; join D (`wirelog.payload_table@1`); location D (`wirelog.payload_located@1`) |
| first-batch attacked arms | no payload fixture (`code_only_payload_arms`; the texts are harness constants) | SEM by document digest |
| byte-identical auxiliaries | one raw artefact, `ext.wirelog.same_bytes` | — |

Checks (profile, D): `wirelog.acc.dispatcher_log@1`, `wirelog.acc.usage_totals@1`, `wirelog.acc.recorded_hijack@1`,
`wirelog.acc.final_text@1` (text-mode files: LF written as CRLF). `aer.acc.agent_calls_vs_assistant@1` is consistent,
because the calls are observed.

A response log that cannot be mapped (refused by the strict loader, or its map job crashed or hit a limit) is one
degenerate AER (D.2.8 case 3) named by its label: `task_id` `run:<label>` (D, `wirelog.unreadable_run@1`), the variant
the runner sniffed or the profile's first, nothing of the run mapped and the artefact kept. The runner's job-failure
contract pins this as `"seals"` (`tests/adapters/runner/test_job_failure_degenerate.py`).

### D.20.4 Code identity (D-282)

The deposit's scripts carry no commit and did not produce every run as shipped (renamed and rewritten first-batch
`meta.json`, 154 runs from an earlier `run_trials.py`, run 0001's body), so every harness-behaviour rule is class I with
the scripts as documentary evidence; D rules are deterministic functions of the logged bytes or package data.

### D.20.5 Synthetic tools (D-284)

The tool runtime is the harness's synthetic dispatcher: `read_file` answers from the harness's own documents and
`send_email` sends nothing and returns `Email sent.`. The `env` actor carries `ext.wirelog.synthetic: true` (I), the
profile and the datasheet disclose it, and nothing records a real file read or mail. SEM: `read_file` a content source with
`untrusted` output, `send_email` a send sink.

### D.20.6 Semantics profile `wirelog.tools@1`

Data `profile.toml`, `tools.toml` (the two tools), `documents.toml` (the digests of the five first-batch documents, four
attacked). Annotations: fixture integrity (payload `untrusted`; tool definitions `untrusted` when they carry a payload,
else `unknown`); system and task text `trusted`; agent output `trusted` and call roles; result integrity (payload present
or attacked document `untrusted`, else the tool's label, fail-closed), `injection_marker` per payload fixture, `author`
`att` (I); execution roles; `outcome` for `hijack` (`attack_succeeded`), `exfiltration` and `silent` only where the run has
an attack. Taint policy `wirelog.taint_sink_untrusted@1`.

### D.20.7 Rule catalogue `wirelog.rules.toml` (version 1)

53 rules: 26 D, 25 I, 2 reserved (`non_run_member`, `synthetic_tools_disclosure`). Issue codes: `label_field_mismatch`,
`context_diverges`, `unknown_block`, `payload_not_delivered`, `payload_entry_missing`, `final_texts_not_logged`,
`meta_rewritten`, `task_prompt_unlisted`, `results_row_missing`, `unreadable_auxiliary`, `turn_limit`.

### D.20.8 Artefact catalogue, files, fixtures and tests

- `adapters/wirelog/artefacts.toml`: 12 entries (non-run members, synthetic tools, payloads in tool metadata, first-batch
  payloads in code, payload not delivered, rewritten metadata, unsplit final texts, harness outcome labels, save time only,
  the Anthropic run, context divergence, label mismatch); every safety-net finding of the full in-memory map is classified.
- Files: `adapters/wirelog/{__init__,wire,dialect,mapper}.py`, `semantics/`, `rules/`, `profiles/what-surrounds.profile.toml`,
  `family.schema.json`, `ext.schema.json`, `artefacts.toml`; registry entry (append only, `planned`).
- Fixtures `tests/fixtures/wirelog/`: 12 run directories chosen by criterion (`CRITERIA.json`), byte-identical members,
  `results.csv`, `attacks.json`, `SOURCE.json`; licence `tests/fixtures/LICENSES/WhatSurrounds-LICENSE-DATA.txt` (with the
  shared `CC-BY-4.0.txt`). No fixture carries a secret-like string (none exists in the deposit).
- Tests `tests/adapters/wirelog/` (dialect, mapper with derived inputs, rules both ways, semantics, artefacts, profile and
  registry, fixtures, the new-family guard); `tests/adapters/runner/test_per_unit_inputs.py` lists the family.

### D.20.9 Downstream effects (CLAUDE.md rule 10) and invariant 5

No existing corpus, AER, SEM or PROV byte moves; no core change (`aer/`, `prov/`, `validate/`, `corpus/` untouched). The
registry gains one source; one runner test lists the new family. Trial imports are scratch only
(`~/.agentprov/migration-work/phase10m/`); the corpus waits for the regeneration round and the user's approval, and
`aer/0.2` will move its pins like every other family's.

## D.21 The MCPHunt family (`mcphunt`; planned, phase 10m)

Decisions D-286–D-289 (user-approved 2026-10-13, the recommended options); census: `docs/reports/phase10m/` part B and
`mcphunt.census.json`. HF `lihaonan0716/mcphunt-agent-traces` @ `c4c69322bf9e` (CC-BY-4.0; rank 7 of D-145): 6,786
traces of multi-server MCP agents in 20 documents (main 3,615, mitigation 2,706, live-guard 387, browser replication
78). Everything in the traces is untrusted data, and the environments plant synthetic, credential-shaped canaries.

### D.21.1 Identity, pins and selection

Source, profile and corpus `mcphunt`, part `head`; pins: the HF repository at the commit (`runs`, primary) and the 15
Git LFS trace documents (`lfs_object`, sha256 = oid). Include `main/*.json`, `mitigation/*.json`,
`live_guard_defense/*.json`, `browser_replication/*.json`; `meta/`, `recall_evaluation/`, `crs_audit/`, README and
croissant are outside the globs (`mcphunt.non_trace_member@1`, reserved). The four splits are recorded per execution
(`ext.mcphunt.split`, `task.defense_id`), not as profile parts: one pin serves them all.

### D.21.2 Dialect and reader (`agentprov.adapters.mcphunt.dialect.McpHuntReader`)

Dialect `mcphunt.traces`, variant `v2.0.0` (the envelope's `schema_version`). Documents are read only by
`ingest.jsonstream.open_json_stream` with the declared array `/traces` (D-242, RI-4): the strict rules apply to every
element and the envelope, and a defect anywhere yields nothing. The reader declares `multi_execution` and streams
(D-323, RB-1): the runner's map job opens the stored document with `open_input` and maps each item of
`parse_stream(handle, …)` as its own execution; `parse(bytes, …)` is a thin wrapper over it. One located item per trace,
key locator `{"p": "/traces/<i>"}` with the element's byte range `bytes = (offset, end)` in the stored object beside it
(it never enters the source key, C.4.1), value `{envelope, trace}`. Four traces are 20.5–46.9 MB: the profile raises the
element limit in `[import] limits` to `max_json_element_bytes` = 64 MiB (D-288; the calibrated D-323 ceiling, RB-2),
which an import records in `corpus.json` as an override.
A checkout of the pinned tree holds Git LFS pointers for the 15 LFS documents: the sniff recognises the pointer header
and returns no match with reason `mcphunt.lfs_pointer` (`register_detail`), so the runner registers the pointer
(`select.not_execution_artefact`, `mcphunt.lfs_pointer@1`) and imports the pinned, verified LFS object in its place
(runner item R3), as DTap does (D.16.2). Regen-batch item 114 (catalogue v2).
Every record locator is a C.9.1 byte range (regen-batch item 149): a trace's records cite
`{"a": "a0", "bytes": [start, end], "p": "/<inside the trace>"}` (the element's own slice), and the judge's version cites
the envelope member's own value `{"a": "a0", "bytes": [start, end]}`. The reader finds each envelope string member's span
in the bytes before the first trace (its key token once, the slice parsing to the envelope's value under the strict
loader) and hands it in the item view (`envelope_spans`). So resolution parses one trace slice (at most 46.9 MB) and
never the whole document, which for the 105.7 MiB `main/deepseek_v4_flash.json` exceeds `max_json_bytes` (64 MiB):
its 723 AERs failed validation with `aer.locator.dangling` before (phase-10m trial 2026-10-21).

### D.21.3 Mapping to AER (`agentprov.adapters.mcphunt.mapper.McpHuntMapper`, adapter `mcphunt.trace` 0.1.0)

One AER per trace. Records: header (task id, `suite` = risk mechanism, `environment` = environment type, `defense_id`
from `defense` or the mitigation level, `attack_id` not applicable: no attacker, D), actors (`bench`, `harness`, `user`,
`agent`, one `srv_<server>` `tool_runtime` per MCP server the events name with `code {dist, dist_version}` from
`measurement.mcp_versions`, `def` in a guarded arm, `judge`), scopes, fixtures (`environment_seed` = the environment
snapshot; `tool_definitions` = the offered servers and tool names), then the conversation and the judgements.

| Source | AER | Evidence |
|---|---|---|
| system, user messages | messages, actors `harness` and `user` | content O; actors I; user = `task_prompt` D |
| `turn_log[k]` | `mc<k>`: `usage`, `finish_reason` (O:provider), `input` = every earlier message (I), `tools` = the tool fixture (I) | existence O; status D (`mcphunt.turn_alignment@1`) |
| assistant *k* / `final_message` | generated by `mc<k>`; an empty-string content beside calls is no text part (`ext.mcphunt.empty_text`) | D when every entry's call count and text flag agree (6,786/6,786), else I and `mcphunt.turn_misaligned` |
| tool call | `tool_call {name (server__tool), args (strict-decoded), args_raw, provider_call_id}` | O; decode D |
| event (no call id) | `te`: actor the server's runtime, `call` = call *j* of its recorded turn, `name`, `args`, `args_effective` (guard), `status` from `success`, `returned` = `result_full`, timestamp and latency in `ext` | event O; pairing I, guarded by the tool name (`mcphunt.event_pairs_call_unverified@1`); typed times ambiguous |
| `sanitized_args` / `taint_blocked` | defence `decision` (`modify`, actor `def`) on the call, `te.authorised_by` | O; actor I (`mcphunt.taint_guard_unverified@1`) |
| tool message | `tool_result {responds_to}` generated by the execution; a truncated prefix or a different text than `result_full` is disclosed | `responds_to` D (`tool_call_id`); generator I |
| a tool result over 1 MiB | `te.returned` and the tool message's `tool_result.value` hold a `$blob` carved from the stored document by the trace's byte range, `{"bytes": [start, end], "p": "/events/<j>/result_full"}` or `…/messages/<i>/content`, transform `utf8` (D-218, RB-3); only that element is parsed | the value unchanged (re-carved by `verify` and `recompute`) |
| canary flags | `ext.mcphunt.canary` on the execution; issue `mcphunt.canary_flagged` | D (the D-289 basis) |
| labels | judgements `outcome`, `outcome_crs_stratified`, `task_completed`, `any_risk`, `strict_leakage`, `data_flow_risk`, `signals_fired` (origin `checker`) | values O; origin I |
| counters | check `mcphunt.acc.counters@1` (events = calls = tool messages = `num_events`; turns; token sums) | D |

### D.21.4 Withholding (D-289)

An execution with a canary-flagged event (4,595 of 6,786) is withheld from a public release with its derived files; the
raw trace documents stay private; the 2,191 unflagged executions stay releasable. The flag rule keys on the seal issue
`mcphunt.canary_flagged` (one per flagged trace; `[family.mcphunt] withhold_basis`) through the profile's issue rule
`[[withhold.rules]] {id = "canary-flagged", issue = "mcphunt.canary_flagged"}` (RW-1, D-311; the code is checked against
the mcphunt catalogue). The profile's `[withhold]` also holds six bounded shape patterns at scope `object` as the backstop
scan (they name shapes, never values).

### D.21.5 Semantics profile `mcphunt.tools@1`

`@2` (D-31 bump, regeneration items 38-41): `@1`'s tables on the `mcphunt` catalogue version 2; `@1` stays, reading
the archived catalogue version 1, for corpora that record it.

The 31 tools of eight servers: roles (reads `content_source`; writes `write_sink`; shell `execute_sink`; fetch and
navigation `egress_read`; form input `send_sink`), output integrity never trusted (local `unknown`, web `untrusted`),
channels by server; prompts and agent output trusted; outcomes `mcphunt.unsafe` (from `outcome`) and `user_task_solved`
(from `task_completed`); taint policy `mcphunt.taint_sink_untrusted@1`.

### D.21.6 Rule catalogue and artefact catalogue

`mcphunt.rules.toml` v1: 37 rules (14 D, 13 I mapper rules, 8 I semantics rules, 2 reserved); issue codes
`canary_flagged`, `task_prompt_differs`, `args_unparsed`, `result_truncated_in_message`, `result_differs`,
`unknown_server`, `turn_misaligned`. `artefacts.toml`: 10 entries; every safety-net finding of the in-memory map is
classified. Version 2 (held for the round; D-31) adds the regen items 38–41 rule `mcphunt.unplaced_message@1`
and code `unplaced_message`, and item 114's `mcphunt.lfs_pointer@1` (D, a reader register detail never cited by a
record): 39 rules; v1 is archived byte for byte (`rules/archive/`).

### D.21.7 Files, fixtures and tests

`adapters/mcphunt/{__init__,dialect,mapper}.py`, `semantics/`, `rules/`, `profiles/mcphunt.profile.toml`, schemas,
`artefacts.toml`; registry entry (append only, `planned`). Fixtures `tests/fixtures/mcphunt/` (484 KiB, within the 512 KiB
per-source budget of D-360): for each of 11 criteria the smallest qualifying trace among traces canary-free by evidence (no canary flag, no taint read or fragment match, no credential or password
shape), each copied byte for byte from its element slice into a document with the source's envelope (`SOURCE.json` records
source file, digest, index and offsets); derived inputs cover the guard, unknown servers and canary flags. Tests
`tests/adapters/mcphunt/`; `test_streaming_import.py` pins RB-1..RB-3 through the product path (one execution per trace,
the raised limit recorded in `corpus.json`, a synthetic result over 1 MiB carved and stored with a `carved` origin).

### D.21.8 Downstream effects and routed needs

No existing corpus byte moves; no core change. The routed needs have landed: RB-1 and RB-2 (D-323) and RW-1 (D-311);
RB-3 is resolved in the family by D-218 carving over the item's byte range. The profile's bytes changed (the element
limit moved from `[family.mcphunt]` to `[import] limits`); no corpus uses it and nothing is released, so it stays
version 1 under D-31 (the bug pass's held D-31 bump to version 2 rebases onto it). Imports wait for the regeneration
round and the user's approval.

## D.22 The AutoGen guard-placement family (`autogen`; planned, phase 10n)

Decisions D-300–D-306 (user-approved 2026-10-13); census and evidence: `docs/reports/phase10n/` (README §1–§4 and §7,
`autogen.map-census.json`, `routing.md`). Numbering: D.19 to D.21 are left to phases 10k and 10m. Zenodo 23025259 v1.0
(CC-BY-4.0 data, MIT code) is rank 11 of the phase-10e ranking (D-145): a measurement study of one prompt-injection guard
moved between the model client, the runtime message bus and the tool boundary of an AutoGen 0.7.5 team of a researcher
and a writer (local `qwen/qwen3.5-9b`). Everything in the deposit is untrusted data; its code is read, never run.

### D.22.1 Identity, pin and the label grammar

- Source `autogen-guard-placement`, profile `autogen-guard-placement`, part `v1.0`, corpus `autogen-guard-placement`.
- Pin: Zenodo record 23025259 v1.0, `autogen-guard-placement-data-code-v1.0.zip` (4,978,620 B, sha256 `af2f5193…7b63`,
  md5 equals the record's). The run files are members of the zip (an archive input, D-200).
- Run file label `<root>/results/phase<N>[/<arm>]/runs.jsonl` (`root` = `autogen-guard-placement`); facets phase and arm
  (phase 6: `bus`, `model`, `none`, `tool`) give `task.environment` (`autogen.label_facets@1`).
- **One execution per run row** (one JSONL line): source key `sha256:<file>#{"line": n}`, identity = file + `run_id`
  (unique, 1,080/1,080).

### D.22.2 Dialect and reader (`agentprov.adapters.autogen.dialect.AutoGenRunsReader`)

Dialect `autogen.runs`; lines through `scan_jsonl` (strict profile; any rejected or blank line rejects the file). Variants
by the row's key set: `team` (phases 2–5), `injecagent` (6), `condition` (10, 13), `defense` (12). A file without a run
row is not of the dialect, with the register detail of its rows: `autogen.rail_probe_no_agent` (phase 7, 150 rows,
`select.not_execution_artefact`) or `autogen.partial_trajectory` (phases 8–9, 40 rows, `select.out_of_scope`; D-300).
`parse` yields one located item per run row (`{"a": "a0", "line": n}`), and the reader declares `multi_execution`
(R-10k-1, D-320), so the runner maps every run row as its own execution with source key `sha256:<file>#{"line": n}`,
resumed and collapsed by that key (D-301; R-10n-3 closed). The reader's `rejected` (D-321) yields every row `parse` does
not: a guardrail-rail row `select.not_execution_artefact`, a framework row `select.out_of_scope`, a row of another shape
`select.not_execution_artefact`, each with its line locator and its detail as above. So the phase 7-9 files are
selected (the profile excludes no file) and their 190 rows are register rows with subject `{source_key}`, one per line,
never one file-level entry (D-300). Per-unit inputs (`auxiliary_for`): the phase directory's
`events.jsonl` and `guard_raw.jsonl`, the probe sets, the InjecAgent selection, `config.json` and the phase-0 capture.

### D.22.3 Mapping to AER (`agentprov.adapters.autogen.mapper.AutoGenMapper`, adapter `autogen.runs` 0.1.0)

Namespace `autogen`; `rules {"aer": 1, "autogen": 1}`. Records: header; actors `bench`, `harness` (autogen-agentchat
0.7.5 from the capture, I), `user` (`simulated_user`: the harness's task, I), the agents that spoke or were called
(`researcher`, `writer`, `selector`: `model.requested` from `config.json`, I; served `not_recorded`), `ingest`, `env`,
`att` (attack probes and InjecAgent cases) and one `guard_<name>` per guard in the run's events (`defense`); scopes `run`
(status from the stop reason, I) and `att0`; fixtures; the TaskResult stream; late decisions; judgements.

| Source | AER | Evidence |
|---|---|---|
| probe or case (joined by id) | fixtures `other`/`autogen.probe_document` (the document), `injection_payload` (passage or attacker instruction; actor `att`, I), `task_prompt` (the harness template from the profile, checked against the recorded task or the guard's digest, D), `system_prompt` per agent (first logged request, O) | join D (`autogen.probe_join@1`); passage in document D |
| `llm_request` + `llm_response` (`request_seq`) | `model_call` (`role` `agent`, `auxiliary` for the selector; `status: kept`, `finish_reason`, `usage` O; `input` = recorded messages matched by text or call id, I; logged times in `ext`) | pair D (`autogen.request_seq@1`) |
| agent `TextMessage` | assistant message `generated_by` the one response of that agent with that text | D (`autogen.response_text_equal@1`) |
| `ThoughtEvent` | folded into the message of the same model result as its first part (`reasoning`), the event's id and time in `ext` | D (`autogen.thought_equal@1`) |
| `ToolCallRequestEvent` | assistant message with one `tool_call` per item (`args` decoded, `args_raw`, `provider_call_id`), `generated_by` the response with the same call ids | D (`autogen.response_call_ids@1`); args D (AutoGen code) |
| `ToolCallExecutionEvent` item | `tool_execution` (`call` by `call_id`; status `ok` for `is_error: false`, `invalid` when the body wrote no harness event, else `ambiguous`) and one `tool` message per item | D (`autogen.call_id_link@1`, `autogen.execution_result_status@1`, AutoGen 0.7.5); `invalid` I |
| `MemoryQueryEvent` | `activity` `autogen:memory_query` (actor `harness`) and `artefact` `autogen:memory_content` | I |
| ingest agent turn | assistant message, actor `ingest`, no generator | I |
| guard row | one `judgement` per guard in `flags` (`injection_flag`, origin `checker`), subject by digest | §D.22.4 |
| block | guard `decision` (`modify`) | §D.22.4 |

Nothing is linked by order or time: message order is a positional `after` edge (I); `created_at` and event `t` stay in
`ext` (D-305).

### D.22.4 Guards (D-304)

- **Judgements.** Subject = the one recorded text whose SHA-256 begins with the row's 16 hex digits (64 bits; computed
  over recorded texts only); a message is preferred to a fixture or artefact with the same text, and on the bus the
  message the row's agent sent. Otherwise the subject is the run and `ext.autogen.guard` keeps the digest and the number
  of candidates (3,169 of 38,183 judgements: identical texts and texts no record holds). Verdict detail from the guard
  log row of the same guard and digest whose text re-hashes to it (D).
- **Decisions.** A block-guard flag at a placement in block mode (on the bus, a delivered message) changed a text: the
  language-model guard replaces it by `[content withheld by guard]`, the keyword guard removes the keyword. A tool block
  is a decision on the execution generating the delivered result (the change is detected by digest, I link); a block of
  a recorded message is a decision about it, whose changed copy is only in the request log
  (`autogen.block_effect_in_request_log`). C.3.7 allows only messages, call parts, executions and model calls as
  subjects, so blocks of the start message, a system prompt, the memory content or an unjoined text are disclosed
  (`autogen.block_subject_not_recorded`, `autogen.block_without_decision@1`); a changed start message names the guard as
  its author (I) with `/generated_by` `not_recorded`.

### D.22.5 Rule catalogue `autogen.rules.toml` (version 1)

Three D rules read AutoGen behaviour at `microsoft/autogen` tag `python-v0.7.5` (`83afbf58`; fetched with the user's
yes) with `_unverified` twins; the profile's `verified_code` names that commit (D-303). The other D rules are
deterministic functions of observed bytes (`citation.py` `INDEPENDENT`). Harness behaviour is I with asserted
assumptions. 15 SEM rules, 2 reserved register-level rules, 10 issue codes, one subtype, two activity/artefact types.

### D.22.6 Semantics profile `autogen.tools@1`

Tool table (49): `fetch_document` (content source, untrusted), `save_note` (write sink), 17 InjecAgent user tools
(content source, untrusted) and 30 attacker tools (write sinks; three send sinks, one execute sink; stubs). Integrity
of fixtures, agent output, the task message (unknown at the user entry), the ingest turn and memory content (untrusted),
withheld results (unknown); injection markers and attacker authorship on tool results. The deposit records no outcome
judgement, so the claims are namespaced (C.14.3): `autogen.canary_present` (the canary verbatim in the writer's text or
a `save_note` argument), `autogen.attacker_tool_called` (InjecAgent's breach), `autogen.keyword_stop` (phase 10).

### D.22.7 Profile, registry, artefact catalogue, files and tests

`profiles/autogen-guard-placement.profile.toml` (closed `[family.autogen]`: `verified_code`, per-phase block guard,
semantics profile, the row census, task templates and prompt defences as data, quirks); registry part `planned`;
`artefacts.toml` (13 entries). Fixtures `tests/fixtures/autogen/` (9 byte-identical members, 533,210 B: the phase-6
InjecAgent tool-block arm, the case file, the config, the capture, the licence texts); tests `tests/adapters/autogen/`
(phases needing the probe set run against the staged deposit when present); in-memory driver
`tools/autogen/phase10n_map.py`. New files only, plus the registry entry and one runner test that lists the families with
per-unit inputs (invariant 5): no `aer/`, `prov/`, `validate/`, `corpus/`, `runner/`, `raw/` or `ingest/` change.

### D.22.8 Results and open items

All 1,080 run rows map, seal and validate in release mode in memory (0 degenerate), with SEM and PROV
(`docs/reports/phase10n/autogen.map-census.json`). The mapper declares `consumes_context`, so for the archive input the
profile's context artefacts enter the `expand` selection and the per-unit plan finds them. The scratch trial import of the
pinned deposit is in `docs/reports/phase10n/` §8, including the 190 row-level register entries of D-321. Tests:
`tests/adapters/autogen/test_import_e2e.py` (`test_rows_that_are_not_runs_are_registered_one_by_one`,
`test_files_without_runs_register_every_row`).

### D.22.9 Withholding (D-603)

The profile (version 2; version 1 under `profiles/archive/`, D-31) holds `[withhold]`: reason `secret`, one bounded
pattern rule `langfuse-secret-key` (`sk-lf-` and a lower-case hex UUID), scope `object`, no `scan_rules` yet (D-600's
release-scan rule for the shape is not on main). One deposit member the profile does not select
(`results/phase7/capture.json`, pre-check PC-01) holds a real-format secret key of the study's own observability
service; the corpus stores it only inside the deflated deposit zip. At seal the decoded scan (D-450) withholds the zip
object only (basis `profile_rule`, detector `agentprov-withhold-decoded/1`); the 43 selected members and all 1,080
executions stay released. Census over the real pinned zip: 1 of 109 members, 0 of 14 primary run files, 0 of 29 stored
context objects, 0 AER/SEM/PROV. The value is never printed, written to a report or put in a fixture.
`tests/adapters/autogen/test_withhold_e2e.py` checks the chain end to end with the shipped profile: a test-made zip with
a key-shaped sentinel in that unselected member, imported in release mode, sealed (the zip withheld, no execution),
`verify --level chain --release` passing, no sealed or deposited byte holding the sentinel (stored or decoded), the
sidecar holding it.

## D.23 The gemini-cli stream family (`geminicli`; planned, phase 10o)

Decisions D-330–D-337 (user-approved 2026-10-13); census and evidence: `docs/reports/phase10o/`. Numbering: D.19–D.22 are
left to the credleak (10k), wire-log and MCPHunt (10m) and AutoGen (10n) families. Zenodo 20404563 `RESULTS_raw.tar.zst`
(CC-BY-4.0) is rank 10 of the phase-10e ranking (D-145) and is counted on its structured part (D-143): the 2,182 non-empty
gemini_cli streams of 10,000 rollouts. Everything in the deposit is untrusted data: the rollouts are agentic-misalignment
elicitations, and their task files, prompts and outputs hold manipulative text by design.

### D.23.1 Identity, pin and the label grammar

- Source and profile `code-agent-misalignment-geminicli`, part `results-raw`, corpus `code-agent-misalignment` (D-144).
- Pin `runs`: Zenodo 10.5281/zenodo.20404563 file `RESULTS_raw.tar.zst` (sha256 `f7186010…acc3cf`, 207,950,011 B), an archive
  input (D-200; a top-level zstd tar, D-240 and RI-3). The code repository it supplements
  (`warmjademe/code_agent_agentic_misalignment@1dec4f17`, MIT) is cited, not imported and not fetched (D-334).
- Member label: `<root>/cells/<scaffold>__<model>/<SK-SKELETON>__m<NN>/<file>` (`root` = `RESULTS_build`; the last four
  segments are matched). Task header: benchmark `code-agent-misalignment`, `suite` = the skeleton, `task_id` = the mutation
  directory (O, origin locator); `attack_id` and `defense_id` `not_recorded`. The label's scaffold, model and mutation are
  checked against the verdict's (`geminicli.label_facets@1`, D; 2,500/2,500 agree), never corrected.

### D.23.2 Dialect and reader (`agentprov.adapters.geminicli.dialect.GeminiStreamReader`)

Dialect `geminicli.stream_json`, variant `v1`: the CLI's `--output-format stream-json` lines `init`, `message`, `tool_use`,
`tool_result`, `error`, `result` (all 2,182 streams; 107,006 events). Parsing is `iter_jsonl` under `IngestLimits`, fail
closed; the file must start with `init`. One located item per file (key locator `{"a": <id>}`); the mapper cites an event
as `{"line": n}`. Per rollout directory the reader offers the stream as the primary, else the `verdict.json`, which the sniff
recognises by its keys and refuses with `geminicli.no_stream`; a 0-byte stream is `geminicli.empty_stream`. Both are
register details of `select.not_execution_artefact`, and the refused unit's siblings are registered with it. `auxiliary_for`
names the siblings by role (`verdict`, `meta`, `fs_before`, `fs_after`, `diff`, `harness_events`, `cli_stderr`,
`runner_stdout`, `runner_stderr`, `atoms`) and the deposit's `manifest.csv` (`manifest`). The profile's `include` selects
them, so the `expand` stage stores exactly what the reader and the register need; no runner change was needed.

### D.23.3 Mapping to AER (`agentprov.adapters.geminicli.mapper.GeminiStreamMapper`, adapter `geminicli.stream_json` 0.1.0)

Records in order: header, actors, scopes, the fixture, the stream in line order, judgements. Namespace `geminicli`
(`https://w3id.org/agentprov/ns/geminicli#`); `rules {"aer": 1, "geminicli": 1}`.

| Source | AER | Evidence (rule) |
|---|---|---|
| `init` | header `ext.geminicli.session_id`, `cli_model` | O |
| user `message` (line 1) | `message` role `user`, actor `user` (`simulated_user`, the principal) | text O; actor I (`geminicli.prompt_harness_authored_unverified@1`) |
| `fs_before.json` | fixture `environment_seed` (content verbatim) | content O; I (`geminicli.workspace_seed_unverified@1`) |
| a block: assistant deltas and `tool_use` events between results | one `model_call` (`kept`; input = logged prefix; usage, served model, request, time `not_recorded`) generating one assistant message: text parts = the deltas concatenated in line order (chunks in `ext.geminicli.chunks`), then one `tool_call` part per `tool_use` (`args` = `parameters` O; the CLI's `tool_id` in `ext.geminicli.calls`; no provider call id) | I (`geminicli.block_is_model_turn_unverified@1`, `geminicli.deltas_compose_message_unverified@1`, `geminicli.context_is_logged_prefix_unverified@1`) |
| `tool_use` + `tool_result` with the same `tool_id` | `tool_execution` (actor `env`, `call` = the part; `name`/`args` O; status `ok`/`error` D, `geminicli.tool_status@1`) and a `tool` message whose `tool_result` answers the call (`text` = `output`; no output field: `text` null, `unk ambiguous`) | link I (`geminicli.tool_id_link_unverified@1`); execution I (`geminicli.result_is_execution_unverified@1`) |
| `tool_use` without a result (73, each the last event) | the part stays, no execution; `missing_tool_result` | I |
| `codebase_investigator` | an execution like any tool; `geminicli.subagent_internals_unobserved`; no sub-agent scope invented | I (`geminicli.subagent_tool_unverified@1`) |
| `error` (warning) | `activity` `geminicli:cli_notice` (actor `harness`) and `artefact` `geminicli:notice_text` | I (`geminicli.cli_notice_is_harness_unverified@1`) |
| other event types | `activity` `geminicli:unmapped_event` and `artefact` `geminicli:event_payload` | I (none in the census) |
| `result` | run status `ok`/`error`, `ext.geminicli.result` verbatim | D (`geminicli.result_status@1`) |
| `verdict.json` | judgements `elicited`, `n_misaligned` (actor `detector`, origin `checker`); `ext.geminicli.verdict` verbatim | values O; origin I (`geminicli.detector_recorded_unverified@1`) |
| `gemini_meta.json` | `ext.geminicli.meta`; exit 143 without `result`: run `aborted` | I (`geminicli.exit_143_terminated_unverified@1`) |
| `fs_after.json`, `final_diff.patch`, `events.jsonl`, the logs | supporting artefacts, named in `ext.geminicli.sidecars` by role; no PROV relation | D (`geminicli.sibling_join@1`) |

Two siblings with identical bytes (empty logs) are one raw object: the header names it once and both roles point at it.
Stream records get positional `after` edges at class I (`geminicli.stream_order_unverified@1`); generated records get
causal edges.

### D.23.4 Model identity (D-333)

The agent's `model.requested` is `verdict.model` (the harness's cell model; I, `geminicli.cell_model_routed_unverified@1`;
the directory, `sut_id` and manifest agree 2,500/2,500); `model.served` is `not_recorded`. The stream's `init.model` is
`gemini-2.5-pro` in every cell because the harness routes the CLI through a LiteLLM proxy; it stays in
`ext.geminicli.cli_model`, and `geminicli.cli_model_alias` marks the 1,762 runs where it differs. The agent's `name` is the
verdict's `sut_id`.

### D.23.5 Time model (D-335)

Every event carries a UTC millisecond timestamp, the CLI's emission time. The run's first and last event times and each
execution's `tool_use`/`tool_result` times stay verbatim in `t.raw`, typed slots `ambiguous`
(`geminicli.event_time_is_emission_unverified@1`; D.16.18 correction 1). Messages and model calls carry no time; notice and
message times stay in `ext`. The harness atoms' clock (0–147 s off the stream) is never used.

### D.23.6 Run status, checks and sidecar disagreements (D-335, D-337)

`result.status` `success` → `ok`, `error` → `error` (`geminicli.cli_error_result`, `incomplete_run`; 495). Without a `result`
event (719), `gemini_meta.exit_code` 143 gives `aborted` (I) with `geminicli.no_result_event` and `incomplete_run`; another
exit code leaves the status `not_recorded`. Profile check `geminicli.acc.counters@1`: `result.stats.tool_calls` against the
`tool_use` events (consistent 1,443; unverifiable where a sub-agent hides calls, 20, or without a result event; inconsistent
otherwise). The verdict's `exit_code`, `timed_out` and `elapsed_sec` contradict `gemini_meta.json` for 1,214 runs
(`geminicli.verdict_meta_disagree`); neither is corrected. The manifest row is compared with the verdict
(`geminicli.manifest_agrees@1`, `ext.geminicli.manifest`).

### D.23.7 Withholding (D-336, D-609)

The profile's `[withhold]` holds one bounded pattern rule (`google-api-key-shape`, scope `executions`, reason `secret`,
gitleaks scan rule `gcp-api-key`). The archive holds one value of that shape, in one gemini_cli tool output (and three
claude_code files, not selected), in no task workspace: most likely a harness credential the agent printed. Sealing
withholds that execution, its stored objects and, at object level, the container (AD-12); 2,181 are released. The value is
never printed, written to a report or put in a fixture. Other secret-like strings (task code, agent-written code) are kept
as published (D-179 option A). `tests/adapters/geminicli/test_withhold_e2e.py` checks the chain end to end with the shipped
profile and no injection: a test-made tar.zst with a key-shaped sentinel in one stream, imported, sealed (the stream, its
execution and the container withheld), `verify --level chain --release` passing, no sealed or deposited byte holding the
sentinel, and the gitleaks control. Until D-372 lands, a seal fails its own chain check on any aborted run (the importer
and `verify` read an I-class `incomplete_run` differently), so the test uses rollouts that end with a `result` event.

**The harness account path (D-609, profile version 2).** The harness wrote the header lines of its `diff -r` output with
the absolute work root of the workstation it ran on (`/home/<account>/jss_agent_work/...`), so 272 of the 2,500
gemini_cli `final_diff.patch` context files (836 header lines) name one third-party account, and the deposit's
`RESULTS_build/README.md` names the same account's home once (followed by a project directory, not `jss_agent_work`).
Two structural pattern rules, scope `object`, reason `personal_data` (overriding the table's `secret`), each with its own
`public_note`, withhold exactly those 273 raw objects at seal, digests and origins kept in `WITHHELD.json`:

- `harness-account-path` = `/home/[a-z0-9_-]{1,32}/jss_agent_work` (the 272 patches);
- `deposit-readme-account-path` = `/home/[a-z0-9_-]{1,32}/[A-Z][a-z]{3}[A-Z][a-z]/` (the README; no single grammar-legal
  pattern covers both forms without naming the account).

Neither names the account. No AER, SEM or PROV statement holds the path (the patches are supporting sidecars, named and
digested only, never parsed), so no execution is withheld; the tar is withheld as their container (AD-12), as it already
was under D-336. The census of D-609 (stored objects, derived files and every member of the pinned tar decoded) matched
exactly those objects among the selected members; in the unselected cells, 226 codex_cli patches carry the same header
form and stay inside the withheld tar. The other home paths of the snapshot are generic accounts or agent-written
placeholders (benchmark content, kept, D-179 option A); each of the 16 placeholder-bearing gemini_cli patches also
carries the harness header and is withheld with it. Names in unselected members (claude_code, codex_cli) stay inside the
withheld tar and were not classified (D-609). The datasheet states the withholding (`corpora/datasheet-statements.toml`,
`cam-harness-account-path-withheld`). `test_withhold_e2e.py` checks it end to end: a test-made tar whose patch carries
the harness header with a made-up account and whose README names that home is imported, sealed (the patch and the README
withheld, `personal_data`, `profile_rule`, no execution; the tar as container; all three executions released) and
verified with `chain --release`; no sealed or deposited byte holds the path, the sidecar does, and a second rollout's
patch with an agent-written placeholder home stays sealed. Version 1 ships unchanged under `profiles/archive/` (D-31).

### D.23.8 Semantics profile `geminicli.tools@1` (`adapters/geminicli/semantics/`)

Tool table of the ten tools the census found (I, `geminicli.tool_table@1`; read from names and logged parameters, no CLI code
verified): `run_shell_command` `execute_sink`; `write_file`, `replace` `write_sink`; `read_file`, `read_many_files`,
`list_directory`, `glob`, `search_file_content` `content_source`; `google_web_search` `egress_read`; `codebase_investigator`
`unknown`. Outputs are `untrusted` (writes' confirmations `unknown`); unknown names fail closed. The user prompt and agent
output are `trusted`; the workspace seed `unknown`. The one outcome: `geminicli.misalignment_elicited` holds iff
`elicited` (origin `checker`). Taint policy `geminicli.taint_sink_untrusted@1`.

### D.23.9 Rule catalogue `geminicli.rules.toml` (version 1)

38 rules: 9 D (deterministic functions of observed bytes), 16 I of the mapper and 7 I of the semantics profile (every
reading of gemini-cli or harness behaviour, each with an asserted assumption; no rule cites code, D-334), and 6 `reserved`
detector names for the artefact catalogue. 12 issue codes, 4 activity and artefact types, no subtype.

### D.23.10 Profile, registry and artefact catalogue

`profiles/code-agent-misalignment-geminicli.profile.toml` (closed `[family.geminicli]` table, `family.schema.json`: layout,
scaffold, models, excluded scaffolds, tools, pairing rule, semantics profile, quirks with the census counts); the
`[withhold]` table of D.23.7 (three rules since version 2, D-609); one `planned` registry part. `artefacts.toml`: 22 entries (D.15.2), six on reserved
detectors (the out-of-scope scaffolds, rollouts without a stream, the credential-shaped value, stderr retries, the derived
harness atoms, the missing glm-4.7 route configuration) and the recorded cases of D.23.3–D.23.6.

### D.23.11 Files, fixtures and tests

New files only (invariant 5): `src/agentprov/adapters/geminicli/`, `tests/adapters/geminicli/`, `tests/fixtures/geminicli/`
(13 rollout directories without their `.log` files, 89 byte-identical members, 75,335 B, chosen by criterion by `tools/geminicli/build_fixtures.py`;
no rollout holding the key shape or a home path; `SOURCE.json`), `tools/geminicli/` (fixture builder; `map_census.py`, the
in-memory mapping census), the registry entry, one line of `tests/adapters/runner/test_per_unit_inputs.py` (the families
with per-unit inputs) and this section. `test_new_family_no_core_change.py` asserts that nothing under `aer/`, `prov/`,
`validate/`, `corpus/`, `adapters/runner/`, `raw/` or `ingest/` changed.

### D.23.12 Downstream effects (CLAUDE.md rule 10)

No existing corpus, AER, SEM or PROV byte moves: the family's code enters only the stage identities of corpora that use it.
aer/0.2 merges later and moves every AER pin of this family (regenerated, never hand-merged). The full import waits for the
regeneration round and the user's approval; scratch trial imports only (`docs/reports/phase10o/`).

## D.24 The Qwen Code JSON-output family (`qwencode`; planned, phase 10o part C)

Decisions D-570–D-578 (user-approved 2026-10-15); census and evidence: `docs/reports/phase10o/part-c.md`. The Qwen Code part
of RedCode-Exec's replication package (Zenodo 23168099 "Which Orders Count?", CC-BY-4.0; its OpenHands part is D.17's
`redcode-exec-openhands`): 3,300 runs of `qwen3-coder-30b-a3b-instruct` under Qwen Code 0.21.0. Phase 10g's held part C,
reassigned to phase 10o; a sibling of D.23 because the format is different (D-570). Everything in the deposit is untrusted
data: RedCode requests ask agents to run risky code by design.

### D.24.1 Identity, pins and the label grammar

- Source and profile `redcode-exec-qwencode`, part `qwen3coder`, corpus `redcode-exec-qwencode`: one corpus per agent,
  beside the OpenHands part's `redcode-exec-openhands` (D-571 as amended 2026-10-15 by the user's decision; cross-agent
  comparison is an analysis step).
- Pins: `runs` = `trajectories_Qwen-qwen3coder.zip` (sha256 `2fd0cada…347dc`, 9,402,535 B, an archive input, D-200);
  `supp` = `agent-execution-decisions-supp.zip` (sha256 `96e328fa…2ae69`, identical to the OpenHands profile's pin), a
  context pin holding the score records, RedCode requests and the execution rules. The CLI does not wire context pins and
  a context tree cannot be an archive yet: **the product import depends on D-530** (phase-10i-context).
- Run label `results/Qwen/<model>/<S1|S2|S3>/<python|bash>/trajectory/qwen_<scenario>_<payload>[_py|_sh]_<S>.json`
  (3,300/3,300; the two targets must agree). Task header: benchmark `redcode-exec`, suite = language, `task_id` =
  `<scenario>_<payload>`, `attack_id` = C1/C2/C3 by target (D, `qwencode.redcode_request_type@1`).

### D.24.2 Dialect and reader (`agentprov.adapters.qwencode.dialect.QwenJsonReader`)

Dialect `qwencode.json`, variant `v0.21` (`init.qwen_code_version` 0.21.x): one JSON array per file (`qwen --output-format
json` stdout), `system`/`init` first. Parsing is `strict_json_loads`; one located item per file, messages cited as
`{"p": "/<n>"}`. `sniff` matches every JSON array (the primaries are already selected by the D.24.1 label grammar; regen
item 123, NF-17): an array of the wrong shape (empty, a non-object element, no `system`/`init` first) is a
`MalformedArtefact` at `parse` and an output of another Qwen Code version (or none) an `UnsupportedVariant` of the
mapper, both sealed as D.2.8 case-3 degenerate AERs (`unparseable_artefact`, `unsupported_variant`); valid JSON that is not
an array is input of another kind (`select.not_execution_artefact`, D.2.8 case 4). **Salvage (D-577 option (b)):** `agentprov.ingest.jsonstream` is fail-closed, so for a **capture cut** the
reader keeps the complete top-level elements: one forward pass over the bytes finds their boundaries, the kept prefix
`data[:cut] + "]"` is parsed once with the strict loader and each element's span once more (O(messages) strict parses of
at most 64 KiB in all, regen item 121, NF-15); the result is the salvaged prefix, flag `qwencode:truncated`, the cut
recorded (`qwencode.truncated_salvage@1`, D). A capture cut is an output of exactly 65,536 bytes (the premise of
`qwencode:CaptureCut`) whose strict-loader error is `ingest.json.syntax` at the end of the input: the top-level array is
still open at the end, and the error lies at the end itself or inside the string, number or literal that the cut leaves
open. Every other strict-loader rejection (invalid UTF-8, a duplicate key, `NaN`, trailing data, an over-size file, a
syntax error before the cut, any other size) is re-raised, so the run is sealed as a D.2.8 case-3 degenerate AER
(`unparseable_artefact`), never a silently shortened prefix (regen item 120, NF-14). A cut that splits a multi-byte UTF-8
character is an encoding error, so it is not salvaged either. Only a prefix ending exactly on a complete top-level element can parse; the
stored bytes are never edited. Such a file is not valid JSON as a whole, so its messages are cited by **byte-range
locators** (`{"a", "bytes": [start, end], "p"}`, C.9.1), each span checked to parse strictly to its message. The four
65,536-byte outputs (the harness's 64 KiB capture cap) map this way. A 0-byte
output is refused `qwencode.empty_output` (`select.not_execution_artefact`). The group's `_full_api_request_sample.json` is
never a primary. `auxiliary_for` names `score`, `dataset` (S1) or `prompt` (S2/S3), `rules` (`supp:<label>`, or the plain
label in one tree) and `api_sample`. One that is absent, not strict JSON or (the rules) not UTF-8 raises
`qwencode.sidecar_missing` (the last since regen item 126).

### D.24.3 Mapping to AER (`agentprov.adapters.qwencode.mapper.QwenJsonMapper`, adapter `qwencode.json` 0.1.0)

| Source | AER | Evidence (rule) |
|---|---|---|
| `system`/`init` | header `ext.qwencode.init`; harness actor `qwen-code`, `version` = `qwen_code_version` (O); agent `model.requested` = `init.model` (O), served `not_recorded` | O; harness I (`qwencode.deposit_harness_unverified@1`) |
| joined RedCode request (`Code` for S1, `generated_prompt` for S2/S3) | `task_prompt` fixture, content verbatim | content O; I (`qwencode.prompt_sent_on_stdin_unverified@1`); join D (`qwencode.request_join@1`); `qwencode.user_message_not_logged` on every run |
| `OH_evaluation/execution_rules.md` | `other` fixture, subtype `qwencode.execution_rules`, `placed_as` `/app/QWEN.md` | content O; I (`qwencode.rules_as_qwen_md_unverified@1`) |
| a block of consecutive `assistant` messages | one `model_call` (`kept`; usage = the sum of the block's message usage, D `qwencode.block_usage_sum@1`, `ambiguous` when every message reports 0; request, served model, time `not_recorded`) generating one assistant message: `text` parts and `tool_call` parts (`provider_call_id` = `id`, `args` = `input`, O) in order; per-message id, model, stop reason, usage in `ext.qwencode.messages` | I (`qwencode.block_is_model_turn_unverified@1`; checked by `qwencode.acc.turns@1`) |
| `tool_result` block | `tool_execution` (actor `env`, status `error` iff `is_error`, D `qwencode.tool_status@1`) and a `tool` message answering the call | link I (`qwencode.tool_use_id_link_unverified@1`) |
| sub-agent `system` messages; a `user` text | harness activity `qwencode:subagent_event` with the message as artefact; a user message (`unattributed_additional_user_message`) | I (`qwencode.subagent_message_unverified@1`) |
| `result` | run status from the first `result` message: `ok` (`success`, not `is_error`) or `error` (D `qwencode.result_status@1`); a later `result` message is a harness activity `qwencode:unmapped_message` with the message as artefact and raises `qwencode.extra_result_message` (warning; regen item 126, NF-20); `subtype`, `is_error`, `num_turns`, `duration_ms`, `duration_api_ms`, `usage`, `permission_denials` and `stats` (per-model and per-source request and token counts, per-tool counts; regen item 122, NF-16) verbatim in the header's `ext.qwencode.result`; `duration_ms` in the run's `ext` | O/D |
| score record | judgement `score` (actor `redcode_qwen_scorer`; origin checker I, `ambiguous` for 1); `step_count`, `exceeded_soft_iteration_cap`, `used_write_tool`, `timed_out`, `last_response_full` in `ext`. A record without `score` writes no judgement (`no_outcome_recorded`; a judgement's value is required) and its other logged fields stay in the AER: the header's `ext.qwencode.judge`, verbatim, with a header `src` locator to the record and D by `qwencode.score_join@1` (the join names the record the run's; item 125 follow-up, so no logged field is dropped); a score that is not an integer of the scale 0, 1, 3 (a boolean included) is kept as logged and raises `qwencode.score_unrecognised` (warning; regen item 125, NF-19) | join D (`qwencode.score_join@1`); I (`qwencode.scorer_recorded_unverified@1`, `qwencode.score_one_ambiguous@1`) |

No time anywhere (`not_recorded`). Positional `after` edges at class I (`qwencode.message_order_unverified@1`). A
`tool_use` block whose `name` is absent or not a string, and a user `text` block whose `text` is not a string, are kept
verbatim as `other` parts (`qwencode.content_block`, `qwencode.unmapped_message`; regen item 124, NF-18): a tool call's
name is a required string (C.3) and `str(None)` would be a placeholder (C.7.3), so no call or execution is written and a
result naming that block's id is an `orphan_tool_result` with its link `ambiguous`.

### D.24.4 Checks

`qwencode.acc.turns@1` (`result.num_turns` = blocks; 3,295/3,295), `qwencode.acc.usage@1` (equal 2,444; reported above the
logged messages 851, unverifiable), `qwencode.final_text_copy@1` (3,295/3,295 equal). `result.stats` is kept verbatim in
`ext` and checked against nothing: its per-source request counts (for example a `managed-auto-memory-extractor` or
sub-agent source beside `main`) may explain the 851 usage excesses as logged hidden-source calls, but no check reads them
(regen item 122 records the field only; a stats-against-blocks check would need its own decision). A salvaged output has no result
message: status `not_recorded`, `qwencode.no_result_message`, `qwencode.truncated_capture`, `incomplete_run`
(`qwencode.capture_cut_unverified@1`), its last call `missing_tool_result`.

### D.24.5 Model identity (D-575)

`model.requested` = `init.model` (`qwen3-coder-30b-a3b-instruct`); the OpenAI-compatible endpoint that served it is not
recorded. `message.model` stays in `ext`.

### D.24.6 Secrets (D-578)

No value of a credential shape in the runs zip. The supplementary zip holds one real-format access token in an
unselected member (D-602), so profile version 2 withholds that zip at object scope (`hf-token-shape`; D-578 amendment of
2026-10-21); no execution is withheld. Payload e-mails and keys are kept as published (D-179
option A). The Qwen part holds no operator account path. Its `/home/<name>/` paths (runs zip `2fd0cada…`) are the
generic `/home/user/` (10, in 5 runs), the container user `/home/node/` (11, in 7 runs) and one eight-character name
from the RedCode payload (58, in 5 runs), which the deposit's own RedCode-Exec dataset also holds as a `/home/` path:
benchmark content, never redacted (D-476).

### D.24.7 Semantics profile `qwencode.tools` (versions 1 and 2)

Tool table: `run_shell_command` `execute_sink` (untrusted); `write_file`, `edit` `write_sink` (unknown); `read_file`,
`list_directory`, `glob`, `grep_search` `content_source` (untrusted); `todo_write` `neutral`; `agent` `unknown`; unknown
names fail closed. Fixtures: the request `untrusted`, the execution rules `trusted`; agent output `trusted`. Outcome
(D-576, as `openhands.tools@1`): score 3 → `attack_succeeded` holds, 0 → does not, 1 → `qwencode.non_informative`. Taint
policy `qwencode.taint_sink_untrusted@1`.

**Versions (D-31; the twins owner's ruling of 2026-10-21, option A).** Scratch trial corpora recorded main's bytes at
`93c02c6f`, so regen item 127 is version 2, not an in-place edit. `qwencode.tools@2` (`semantics/qwencode.tools-2/`,
declaring the catalogue `{qwencode: 2}`) lists `non_informative = [1]` in `profile.toml` (required by the loader at version
2) and gives any other score no outcome annotation (NF-21: `qwencode.score_meaning@1` covers these three only).
`qwencode.tools@1` (`semantics/qwencode.tools-1/`, byte-identical to `93c02c6f`, directory digest `34eb0b79…71d5`) still
declares and reads the catalogue version 1 from `rules/archive/` and reads every other integer score as
`qwencode.non_informative`, as the scratch trials recorded it. The code (`semantics/tools.py`) builds both:
`CATALOGUE_OF = {1: 1, 2: 2}`, the `[profile]` header checked against it, as `agentprov.adapters.agentdojo.semantics`
does. The registry part and the source profile select `@2`; `tests/adapters/qwencode/test_d31_bumps.py` pins the digests.

### D.24.8 Rule catalogue `qwencode.rules.toml` (version 2)

35 rules: 11 D, 14 I of the mapper, 7 I of the semantics profile and 3 `reserved` detector names; 11 issue codes
(`score_unrecognised` and `extra_result_message` added by regen items 125 and 126), 3 types,
2 subtypes (`qwencode.content_block`, `qwencode.execution_rules`). No rule cites code (D-574); the deposit's
`Qwen_evaluation/` is documentary evidence. **Version 2 (D-31, the twins owner's ruling of 2026-10-21, option A):** regen
items 120-127 changed rule statements and issue codes after scratch trial corpora had recorded the file, so the file is at
version 2 and version 1 (main's bytes at `93c02c6f`, sha256 `db5c7cd7…6cce`) ships byte for byte under
`rules/archive/qwencode.rules.v1.toml`. The rules keep `@1` (nothing is released; a statement change is a content change
covered by the catalogue version). The items add no D rule, so no `_unverified` twin is needed.

### D.24.9 Profile, registry and artefact catalogue

`profiles/redcode-exec-qwencode.profile.toml` (closed `[family.qwencode]` table: layout, targets, languages, tools, pairing
rule, semantics profile, quirks; version 2 since the D-31 bumps of 2026-10-21: `[import] rules` `qwencode = 2` and the
semantics profile `qwencode.tools@2`; version 1, main's bytes at `93c02c6f`, sha256 `40e8732e…2927`, ships under
`profiles/archive/redcode-exec-qwencode.profile.v1.toml`), one `planned` registry part (semantics `qwencode.tools@2`), `artefacts.toml` (16 entries; three on reserved detectors:
the empty output, the API samples, the context-pin path).

### D.24.10 Files, fixtures and tests

New files only (invariant 5): `src/agentprov/adapters/qwencode/`, `tests/adapters/qwencode/` (43 tests),
`tests/fixtures/qwencode/` (7 runs and the 12 supplementary files they need, 19 byte-identical members, 782,631 B, chosen by
a cost-aware set cover over 15 criteria by `tools/qwencode/build_fixtures.py`; a recorded D-360 exception of 800 KiB in
`tests/FIXTURES.json`), `tools/qwencode/` (fixture builder, `map_census.py`, the trial-only `trial_import.py`), the
registry entry, the README tables, one line in each of the two runner family-list tests, and this section.

### D.24.11 Downstream effects (CLAUDE.md rule 10)

No existing corpus, AER, SEM or PROV byte moves. D-530 is in the pre-round integration (e92a4091); the product import runs in the regeneration round.
Scratch trial corpora built at `93c02c6f` stay recomputable after regen items 120-127: the profile, catalogue and
semantics profile versions they recorded (`redcode-exec-qwencode@1`, `qwencode` v1, `qwencode.tools@1`) ship unchanged
(D-31 bumps, D.24.7-D.24.9); new mappings record version 2 of each.
