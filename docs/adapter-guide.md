# Adding a framework to AgentPROV: the adapter guide

This guide is for someone who wants AgentPROV to read the logs of a new agent framework or benchmark. It walks through
**FooBench**, the self-authored toy format that the future-framework test uses, file by file, and ends with a checklist.
The normative text is [`docs/architecture/D_adapters.md`](architecture/D_adapters.md) (D.1 concepts, D.2 interfaces,
D.4 profiles, D.5 catalogues, D.12 the FooBench test, D.13 isolation, D.15 artefacts); this guide does not override it.

**The promise, and its limit.** A new framework normally needs a reader, a mapper, a source profile, a rule catalogue
and tests, and **nothing** under `aer/`, `prov/`, `validate/` or `corpus/` (spec A.3, "Extensibility"). This is the
design goal. What has been shown is narrower: FooBench (self-authored) and the Inspect `.eval` importer landed with the core
changes listed in C.20, and nothing else. Say exactly that: "tested on a self-authored toy format and on the Inspect
importer (changes listed)". If your framework seems to need a core change, stop and record why as a decision first
(`docs/architecture/decisions/`, indexed in `DECISIONS.md`).

## 1. The pieces and where they live

An adapter family is the package `src/agentprov/adapters/<family>/`. For FooBench:

| # | File | What it is | Code or data |
|---|---|---|---|
| 1 | `adapters/foobench/__init__.py` | the package; `ADAPTER_ID = "foobench.jsonl"` | code |
| 2 | `adapters/foobench/dialect.py` | `FooJsonlReader`: discover, `sniff`, `parse` | code (stdlib + `agentprov.ingest` only) |
| 3 | `adapters/foobench/mapper.py` | `FooMapper`: a unit and a profile in, AER records out | code (stdlib + `agentprov.aer` only) |
| 4 | `adapters/foobench/profiles/foobench.profile.toml` | the source profile: pins, licence, lineage, import selection, family facts | data |
| 5 | `adapters/foobench/rules/foobench.rules.toml` | the rule catalogue: every D/I assertion the mapper makes, issue codes, generic `types` | data |
| 6 | `adapters/foobench/ext.schema.json`, `family.schema.json` | closed schemas of `ext.foobench` and of `[family.foobench]` | data |
| 7 | `adapters/foobench/semantics/foobench.toy-1/tables.toml` | the semantics profile (tool tables, integrity) for SEM | data |
| 8 | `adapters/foobench/artefacts.toml` | the artefact catalogue (D.15): known quirks and how they are handled | data |
| 9 | `tests/fixtures/foobench/*.jsonl` + `SOURCE.json` | a licence-cleared fixture with every event type | data |
| 10 | `tests/adapters/foobench/test_*.py` | dialect, mapper, rules, semantics, fuzz and the future-framework test | tests |
| 11 | one `SourceRegistration` in `adapters/registry/__init__.py` (+ a `READERS` and a `MAPPERS` line) | the only status store | data |

Everything framework-specific is data the engine reads (profiles, catalogues, tables), or code that only produces AER.
PROV statements come only from the engine's rule catalogue (`prov/`), never from an adapter.

## 2. Walkthrough: FooBench

**The scenario** (D.12). FooBench releases JSONL traces: one execution per primary file, one event per line. A
hand-off writes the sub-agent's events into a second file. Its event types are the familiar `llm_request`,
`llm_response`, `tool_start`, `tool_end`, `guard_verdict`, plus `plan_update`, `memory_write`, `memory_read`,
`screenshot`, `handoff`, `approval` (approve and edit), `text_action`, `checkpoint_restore` and one the adapter does not
know (`telemetry`).

### Step 1: register the source (the registry is the only status store)

Add one `SourceRegistration` and the two factory strings. Factories are lazy `"agentprov.<module>:<Class>"` strings;
anything outside the `agentprov.` namespace is refused (`adapter.factory`), and importing the registry imports no
adapter family. There is no plugin loading.

```python
READERS["foobench.jsonl"] = "agentprov.adapters.foobench.dialect:FooJsonlReader"
MAPPERS["foobench.jsonl"] = "agentprov.adapters.foobench.mapper:FooMapper"

SourceRegistration(
    source_id="foobench", name="FooBench (self-authored toy format, D.12)", family="foobench",
    capabilities=(Capability(part="fixture", role="source", evidence="yes", import_status=None, caveat=...,
                             dialects=("foobench.jsonl",), variants=("v1",), reader=READERS["foobench.jsonl"],
                             mapper=MAPPERS["foobench.jsonl"], profile="foobench", semantics=("foobench.toy@1",)),),
    licence=LicencePolicy(spdx="MIT", holders=("AgentPROV authors",), data_licence="MIT", policy="include", basis=...),
    evidence_refs=("docs/architecture/D_adapters.md D.12", "docs/architecture/K_testing.md K.6.4"),
)
```

A new real source starts with `import_status` `planned` or `in development`. It becomes `supported` only after a
recorded full import passes (HON-10). Status words are generated from the registry everywhere (README, datasheets,
paper); never type them by hand.

### Step 2: write the reader (parse, don't interpret)

`FooJsonlReader` (D.12.1 row 2) has three jobs, and no semantic ones (invariant A-1):

- **sniff** the bytes: the first line is a JSON object with the declared `schema` key. `sniff` must never raise.
- **parse** line by line with `agentprov.ingest.loaders.iter_jsonl` under `IngestLimits`, yielding `LocatedItem`s
  whose locators are `{"line": n}` (0-based) and `{}` for the whole file.
- fail **typed**: a defect is `MalformedArtefact` (the adapter layer) or `IngestError` with a G.3.9 code. Any other
  exception is a bug.

Rules that bind every reader:

- Untrusted bytes are parsed only through `agentprov.ingest` (strict JSON: no duplicate keys, no `NaN`, a digit cap, a
  depth cap; JSONL split on LF only, never `splitlines()`).
- No `eval`, `exec`, `pickle`, `marshal`, `yaml.load`, `subprocess` or sockets; no benchmark import. A static AST scan
  enforces this (`tests/security/test_static_dangerous_calls.py`, `tests/boundary/`).
- File and member names are **labels**, never paths. Archives are never extracted; members are stored by digest by the
  `expand` stage, and the reader receives bytes.
- Readers run in T1 workers (rlimited, no network, scrubbed environment), so a hostile input kills a worker, not the
  import.

### Step 3: write the profile (the facts about the source, as data)

`profiles/foobench.profile.toml` has the generic tables of D.4 and the family table `[family.foobench]`:

```toml
[profile]
id = "foobench"
version = 1                       # bumped on any byte change (AD-18)
format = "agentprov-source-profile/0.1"
source_id = "foobench"
family = "foobench"
parts = ["fixture"]

[licence]
spdx = "MIT"
data_licence = "MIT"
policy = "include"                # NC and restricted data go to their own corpora (D-25)

[lineage]
content_dedup = "never"           # ownership is declared once, here; a non-owner records select.owned_elsewhere

[import]
dialect = "foobench.jsonl"
mapper = "foobench.jsonl"
include = ["**/*.jsonl"]
exclude = [{ glob = "**/.DS_Store", code = "select.not_execution_artefact" }]
auxiliary = ["**/sub-*.jsonl"]    # the hand-off's second file joins the parent's execution unit

[family.foobench.guard_verdicts]  # closed tables the mapper reads; validated by family.schema.json
pass = "allow"
block = "deny"
```

A real source also carries **pins**: an exact 40-hex commit (or a DOI and file) and the sha256 recorded at first
acquisition. Imports refuse unpinned input (D-15): `--input` needs `--verify-against-pin`, or the pin comes through
`--fetch`. Identity rules (which field names the model, the defence) live here too, and are pinned by digest. Never
identify anything by a single self-reported field the source might get wrong (invariant A-7).

### Step 4: write the mapper (one function from a unit to AER)

`FooMapper.map(unit, ctx)` yields AER records (the 12 non-seal kinds); the core writer adds the seal. The mapping table
of D.12.2 is the specification. In short:

| FooBench event | AER | What PROV the engine then derives |
|---|---|---|
| `llm_request` + `llm_response` | `model_call` + output `message` (`generated_by`) | `used` per input message, `wasGeneratedBy`, `wasAssociatedWith` |
| `tool_start` + `tool_end` | `tool_execution` + `tool_result` message | `used(te, request)` only, `wasGeneratedBy` |
| `guard_verdict` | `decision` (verdict from the profile's closed table) | association and `used` of the subject |
| `plan_update` | generic `activity` `foobench:plan_step` + `artefact` `foobench:plan` | G-ACT, G-USE, G-GEN, G-ASSOC |
| `memory_write` / `memory_read` | `tool_execution` + `artefact`; a harness `activity` reading it | the write → read flow as a named `wasInformedBy` |
| `screenshot` | `activity` `foobench:observe` + `artefact` with a `$blob` | the screenshot's generation |
| `handoff` | `tool_execution` + a `scope` of kind `subagent`, `spawned_by` (the sub-agent file is expanded at most 4 deep and never twice on one chain; otherwise the warning `foobench.handoff_not_expanded`, never a silent stop) | `wasStartedBy(scope, te)` |
| `approval` | `decision` by the user; `authorised_by` on the execution | `wasStartedBy(te, decision)` |
| `checkpoint_restore`, `telemetry` | kept verbatim in `ext.foobench.events[]` with an issue | nothing: a **named, disclosed gap** |

The rules a mapper lives by (D.1.3):

- **Specialised kinds first.** Use `activity` and `artefact` only for what no specialised kind represents. Every
  `activity.type` and `artefact.type` is `<ns>:<name>`, declared in the catalogue's `types`; the validator rejects any
  other.
- **Every D or I assertion cites a rule** of a catalogue the header lists, and its class is that rule's effective
  class. Record `ev` is the existence class; weaker fields are tagged through `evf`.
- **No sentinels.** An unknown value goes to `unk` with a reason from the closed list (`not_recorded`, `lost`,
  `overwritten`, `withheld`, `ambiguous`, `not_captured`, `not_applicable`). Never `"0"` or `""`. Never invent a time.
- **Purity.** `map` reads nothing but the unit's declared artefacts: no clock, environment, network, random state or
  locale. Same bytes in, same AER bytes out, in any process, with any worker count.
- **Seal with issues, never discard.** A malformed file becomes a degenerate AER (D.2.8 case 3) with
  `unparseable_artefact`; it is never dropped and never an `adapter_defect` (an unexpected exception is a bug).
- **In-band claims are data.** A version, digest or "provenance" field the source writes about itself is recorded as
  `O` data `by: source`. It never becomes identity and never a PROV statement (`tests/security/test_inband_claims.py`).
- **Times are claims.** They are recorded as they are; they never order records and never create a relation
  (`tests/security/test_time_claims.py`).

### Step 5: write the rule catalogue

`rules/foobench.rules.toml` lists every rule the mapper cites, with its class, statement, premises, assumptions,
evidence and tests, and the family's issue codes and generic `types`:

```toml
[catalogue]
id = "foobench"
version = 1
format = "agentprov-rule-catalogue/0.1"
issue_codes = ["unmapped_event_type", "restore_unmodelled", "observation_unlinked"]
types = ["foobench:plan_step", "foobench:plan", "foobench:memory_item", "foobench:memory_read",
         "foobench:memory_snippet", "foobench:observe", "foobench:screenshot"]

[[rule]]
id = "foobench.schema_is_foobench"
version = 1
class = "D"
status = "active"
statement = "A file whose first line declares the schema foobench/1 is a FooBench trace ..."
premises = ["/schema"]
assumptions = []
evidence = ["docs/architecture/D_adapters.md D.12"]
tests = ["tests/adapters/foobench/test_rules.py::test_every_declared_rule_is_exercised"]
since = "0.1.0"
```

Rules are immutable once released: a change of statement, class or behaviour is `@n+1` and a catalogue version bump.
A class-D rule whose assumption cannot be verified against code at a pin stays class I, or gets an `_unverified` twin.

### Step 6: semantics, artefacts and schemas

- **Semantics profile** (`semantics/foobench.toy-1/tables.toml`): tool tables, integrity and roles for SEM. Unknown
  tools fail closed. Found by convention; `sem` and `prov` never import a family.
- **Artefact catalogue** (`artefacts.toml`, D.15): every quirk you find in the source is recorded with its cause,
  detector rule, handling class (CR/DR/RJ/FO/NR), expected counts and references, and gets a handler and a test.
  Anything unclaimed shows up as `artefact.unclassified.*`. Never fix a quirk by editing raw bytes or dropping traces.
- **Closed schemas** for `ext.<ns>` and `[family.<ns>]`.

### Step 7: fixtures and tests

Fixtures are small, licence-cleared, indexed in `SOURCE.json`, and treated as untrusted data (agent-security fixtures
contain injection payloads; `.gitattributes` marks them binary, search tools ignore them, and coding agents are denied
reading them). FooBench's tests show the minimum:

- `test_dialect.py`: sniff and parse, every locator form, typed failures.
- `test_mapper.py`: the golden AER bytes (`tests/adapters/foobench/golden/trace-001.aer.jsonl`).
- `test_rules.py`: every declared rule is exercised, and every cited rule is declared.
- `test_semantics.py`: the semantics profile end to end.
- `test_fuzz.py`: Hypothesis over bytes, lines (framing damage, split, merge, CRLF), event selections and field values:
  the reader fails typed, the mapper always seals a valid AER, and the bytes are deterministic (K.11.1 F-1…F-5).
- `test_future_framework.py`: the named PROV statements of D.12.2, each by rule id; the named gaps with no statement
  emitted; tier-2 and tier-4 validation; and **no change in the protected set** (all of `src/agentprov/` except the
  family, the registry lines and generated docs).

Then run the gates that guard everyone else's bytes:

```bash
uv run pytest tests/golden tests/prov tests/adapters/<family>
uv run pytest tests/security tests/fuzz tests/boundary
uv run ruff check . && uv run python tools/check_unicode.py
```

## 3. When the core really must change

If the framework has a construct aer/0.1 cannot express, prefer a **named, disclosed gap** (FooBench's restore and
unknown event) over a workaround. D.12.4 lists what forces a versioned change: a new closed-enum value without an
escape, a new typed reference the core bundle needs, or a new record kind. Each is `aer/0.2` (or `capture/0.2`), never
an in-place edit of the frozen formats (D-14). Record the reason as a decision (with its rejected alternatives)
before touching `aer/`, `prov/`, `validate/` or `corpus/`.

## 4. Checklist

- [ ] Source licence read (LICENSE file, not only a platform tag); licence class decided (D-25); NC data in its own
      `-nc` corpus; restricted data never committed.
- [ ] Pins: exact commit or DOI, per-file digest; no branch or tag.
- [ ] Reader: stdlib + `agentprov.ingest` only; total `sniff`; typed failures; LF-only JSONL; no paths from names.
- [ ] Mapper: pure; every D/I assertion cites a rule; no sentinels; `unk` reasons from the closed list; specialised
      kinds first; in-band claims as `O` data `by: source`; malformed input → degenerate AER.
- [ ] Profile, catalogue, schemas, semantics and artefact catalogue as data; versions bumped on any byte change.
- [ ] One registry entry; status `planned` or `in development` until a recorded full import passes.
- [ ] Fixtures licence-cleared and indexed; no agent-instruction files among them.
- [ ] Tests: dialect, golden AER, rules coverage, semantics, fuzz, and a future-framework-style test of named
      statements and named gaps.
- [ ] Golden, PROV, security, fuzz and boundary gates pass; `git diff --stat` touches only the family, its tests and
      the registry lines.
- [ ] Every quirk found is in `artefacts.toml` with a handler and a test, and in a decision if it bears on claims.
