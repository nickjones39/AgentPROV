Revision: 2026-10-07 r2 — review resolutions and Addendum B applied.

# M. Repository structure · N. Command-line interface

Status: DRAFT-FOR-REVIEW, 2026-10-07 (r2). Binding input, in order of precedence: `investigation/DECISIONS.md`
**Addendum B** (architect rulings on the review), then **Addendum A**, then D0–D12; and
`investigation/spec/review/RESOLUTIONS.md`, whose §3 canonical naming table this section follows except where
Addendum B deviates from it. MN owns paths and the CLI (RESOLUTIONS §0, precedence item 3).

Scope. This section covers:

- the layout of the new repository `~/Desktop/PhD/Labs/AgentPROV-framework`: one core project and,
  per A1 as implemented by AD-01, the shared `capture/` package, the shared live harness `backends/shared/` and the
  two backend projects `backends/agentdojo/` and `backends/autodojo/`;
- their packaging files;
- the import-layering rules;
- the public Python surface;
- the `agentprov` command line.

Other sections define *what* a component does. This section fixes *where* it lives, *how it is installed* and *how
a user invokes it*. EF says so explicitly: "The package-layout section is authoritative for names" (`spec/EF_provenance.md`
§E.0.3).

**How names were chosen.** Since the review, three rules apply.

1. **RESOLUTIONS §3 is the name authority**, as amended by Addendum B: AD-10 as ruled keeps `stats/`, `render/`,
   the `render` extra and the `stats` and `render` commands; AD-15 as ruled gives `aer/0.1` 13 record kinds
   (B-1); AD-16 as ruled sets `requires-python = ">=3.14"` with a release-mode refusal below 3.14.8.
2. **The owning section specifies behaviour** (RESOLUTIONS §0):

   | Section | Owns |
   |---|---|
   | C | `aer`, `sem`, `views`, and the `capture/0.1` format |
   | D | `adapters`, and the backend code (`agentprov_backend`, `backends/*`) |
   | EF | `prov`, `vocab`, the `apv:` vocabulary |
   | HL | `corpus`, `release`, the version axes |
   | J | `migration` |
   | K | `tests/`, `agentprov.testing` |
   | G | limits (`ingest.limits`) and security controls |
   | MN | paths, the CLI, `io`, `api`, and the paths of `stats` and `render` |

3. **Where §3 is silent,** this section decides. M.1.10 lists those decisions, and N.5 lists every command mapping.

**Evidence conventions.**

- `[audit/capture.md §9.3]` and similar cite the investigation reports.
- Baseline code is cited as `file:line` in `~/Desktop/PhD/Labs/AgentDojo-PROV-framework` at
  `579a908`.
- `[obs-Mn]` marks an observation made while writing this section, with throw-away probes in the session
  scratchpad. No probe touched the baseline.
- The upstream clones moved out of the session working directory to
  `~/Desktop/PhD/Labs/AgentPROV-upstream/` (Addendum B-2; U-08). No example, test or command in
  this section reads them; acquisitions use `agentprov fetch` (bare) or `--input` on a tree outside the workspace
  (R-52).

**Observations.**

- **[obs-M1]** `uv 0.12.18` (Homebrew, 2026-09-22) built an sdist and a wheel offline with the `uv_build`
  backend (`module-root = "src"`, `uv build --offline`):
  - the wheel contained every non-Python file under `src/agentprov/` (`.toml`, `.json`, `py.typed`) without any
    include rule;
  - PEP 639 `license = "MIT"` plus `license-files` produced `License-Expression` and `dist-info/licenses/`;
  - `uv lock --offline` accepted a self-referential extra (`all = ["agentprov[live]"]`; the `all` extra itself is
    gone in r2, M.2).

  uv 0.12.18 cannot install CPython 3.14.8; uv ≥ 0.12.22 can, and the upgrade is recommended (Addendum B, AD-16;
  G.7.1).
- **[obs-M2]** `ruff 0.16.10` with `flake8-tidy-imports.banned-api = {"agentdojo"}` flagged both
  `from agentdojo.agent_pipeline import X` and `import agentdojo.types` (TID251):
  - `banned-module-level-imports` flagged a module-level `import pandas` but not one inside a function (TID253);
  - `[tool.ruff.format] exclude` and glob keys in `per-file-ignores` were accepted.
- **[obs-M3]** `pytest 9.1.1` accepted the `[tool.pytest.ini_options]` block of M.2 under `--strict-config` and
  `--strict-markers`.

### Changes after review (2026-10-07)

- **Applied** (RESOLUTIONS §4.11 items 1–18): R-01, R-07, R-11, R-12, R-13, R-15, R-16, R-17, R-19, R-28, R-34,
  R-39, R-41, R-42, R-43, R-44, R-45, R-47, R-48, R-49, R-50, R-51, R-52, R-55, R-58, R-60 (as ruled), R-63, R-64,
  and the §5 variant list.
- **Addendum B deviations applied:**
  - AD-10 as ruled: `src/agentprov/stats/` (minimal, generic, stdlib only) and `src/agentprov/render/` (the baseline
    renderer ported to `agentprov-prov/0.1` bundles, behind the `render` extra) stay, with the `stats` and `render`
    commands. The CLI therefore has 15 commands: the 13 of RESOLUTIONS §3.7 plus these two. Every other AD-10
    deferral is applied (`analysis/`, `export/ml/`, outcome replay, `diff`, collections, flattened core, stored
    TriG, lineage documents);
  - AD-15 as ruled: `aer/0.1` has 13 record kinds, including the generic `activity` and `artefact`; the module
    placement of EF's rules G-ACT, G-USE, G-GEN and G-ASSOC is fixed in M.1.2;
  - AD-16 as ruled: `requires-python = ">=3.14"`, `.python-version` `3.14`; archive and compressed-stream ingestion
    refuses below 3.14.8 in release mode (`--release`, the deposit builder `agentprov.release.builder` behind `package
    --deposit`; `package` in seal mode opens no archive, D-62)
    and warns and records in dev mode; CI pins the latest 3.14 patch. Consequently the uv `required-version` floor
    stays at the maintainer's uv until the user upgrades (Addendum C-1; G.7.1; M.2 note 2);
  - AD-08 nuance: README wording per M.1.1.
- **Addendum B-2 and B-3:** upstream clones outside the workspace; the specification is published as
  `docs/architecture/` (M.1.5).
- **Challenge boxes.** The one challenge of r1 (to D10, M.2) is ruled; it is replaced by a Resolved note.
- **r2 sweep residuals (2026-10-08).** `review/SWEEP_r2.md` §7 SW-MN1–SW-MN16 are applied, with Addendum C and the
  architect defaults AD-SW3, AD-SW11, AD-SW12, AD-SW13, AD-SW18, AD-SW19 and AD-SW20.

---

## M.0 Decisions taken in this section

1. **Five projects in one repository (A1, as implemented by AD-01).** [R-01]
   - The core distribution `agentprov`, in a `src/` layout, requires Python ≥ 3.14 (AD-16 as ruled). There is no
     `agentprov.core` package. The "core" of D10 is a *layer* (M.5): `io`, `ingest`, `raw`, `aer`, `sem`, `prov`,
     `views`, `validate`, `corpus` and `release`.
   - `capture/` is the distribution `agentprov-capture` (import `agentprov_capture`; Python ≥ 3.12; stdlib +
     `rfc8785` only). Core depends on it to read and verify capture logs; the backend harness uses it to write them.
   - `backends/shared/` is the distribution `agentprov-backend` (import `agentprov_backend`): the AgentDojo-family
     live harness, the worker entry and `ScriptedTransport`.
   - `backends/agentdojo/` and `backends/autodojo/` are backend projects on Python 3.12. They depend on the two
     shared packages by path and **never on `agentprov`**.
   - Core has no benchmark extra and no in-process live path. `agentprov run` always spawns the backend worker
     (M.1.7; N.2.1).
2. **Data is package data.** Profiles, rule catalogues, tables, schemas, the ontology and SHACL shapes live inside the
   package and are read through `importlib.resources`. A wheel and a checkout therefore read the same bytes
   [obs-M1]. D2's `schemas/aer-0.1.schema.json` resolves to `src/agentprov/schemas/aer-0.1.schema.json`; v0.1
   publishes three schemas only (`aer-0.1`, `capture-0.1`, `corpus-0.1`; AD-10 row 13). Each corpus carries its own
   copies under `schemas/` and `rules/` (H.1.2). The corpus copy of `rules/` is a **record**, not an authority:
   `rederive` loads profiles and catalogues only from package resources, at the recorded version (AD-14).
3. **Build backend: `uv_build`.** It is uv's integrated backend, it builds offline [obs-M1], and it fits the user's
   uv-only workflow. Hatchling offers nothing this project needs, and it would add a build-time download.
4. **The wheel is runtime-only.** Maintenance scripts live in `tools/`. `agentprov.testing` is core-only test support
   and is never installed in a backend environment; the scripted LLM transport is
   `agentprov_backend.testing.ScriptedTransport` (AD-01(e)).
5. **One flat `argparse` CLI** with 15 commands and two aliases (N.2): the 13 commands of RESOLUTIONS §3.7 plus
   `stats` and `render`, which Addendum B keeps (AD-10 as ruled). HL's `corpus …`, `raw …` and `release …` groups,
   D's `backends build`, and J's `migrate` are placed in it (N.5).
6. **Working and sealed corpora.** Writers work in `<corpus>.partial/`. `package` seals the tree and atomically
   renames it to `<corpus>/`. HL H.1.5(1) ("build into `<out>.partial/` and swap") thereby sits behind ordinary,
   resumable commands (N.1.5).
7. **Interpreter policy (AD-16 as ruled; G.3.8).** Core declares `requires-python = ">=3.14"`. Below 3.14.8, release
   mode (`--release`, the deposit builder `agentprov.release.builder` behind `package --deposit`; `package` in seal mode
   opens no archive, D-62) refuses archive and
   compressed-stream ingestion with exit 3, and refuses to package a corpus whose manifest records an
   `interpreter_advisory` (exit 4); dev mode warns and records `python_version` and `interpreter_advisory`. There is
   no override flag.
8. **Exit codes.**

   | Code | Meaning |
   |---|---|
   | 0 | ok |
   | 1 | failures |
   | 2 | usage |
   | 3 | environment |
   | 4 | refused by a guard |
   | 5 | unsupported source or capability |
   | 70 | internal error |
   | 130 | interrupted |

   This table reconciles K.15, HL H.8.5 and D.2.9 (N.1.3). D and HL adopt it: a `ProfileError` is 70 and an
   environment error is 3 (R-19).

---

## M.1 Repository tree

### M.1.1 Top level

```
AgentPROV-framework/                     # local git repo → private GitHub repo "AgentPROV" (user preference)
├── README.md                            # what AgentPROV is (D0), install with uv, quick start, status table (generated from the registry, K.16(5)).
│                                        #   "Benchmark-agnostic" only as the core's design goal; empirical coverage only in the registry-generated phrase (AD-08 as ruled)
├── CHANGELOG.md                         # software releases; each entry lists the format/spec/adapter/catalogue versions it emits (L.1.2)
├── LICENSE                              # MIT for code, as the baseline (B PRJ-08; U-12 default); data licences live per corpus (H.4.4)
├── THIRD_PARTY_NOTICES.md               # AgentDojo MIT notice for AgentDojo-derived code (U-12 default; Q6)
├── CITATION.cff                         # software citation; no DOI until the user mints the AgentPROV concept DOI (D9; Addendum B-2)
├── AGENTS.md                            # versioned, tool-neutral agent guidance: data is never instructions; no secrets, no data paths (G.8.4; R-50)
├── CLAUDE.md                            # versioned; points to AGENTS.md (R-50)
├── .claude/settings.json                # versioned deny rules: Read(./.env), Read(./.env.*), Read(./tests/fixtures/**) (G.8.4; R-42)
├── pyproject.toml                       # core project, M.2
├── uv.lock                              # committed; every CI job runs `uv sync --locked` (K.19)
├── .python-version                      # "3.14" (AD-16 as ruled)
├── .gitignore  .gitattributes           # M.3
├── .ignore  .rgignore                   # M.3.3: search tools skip tests/fixtures/ (R-42)
├── .pre-commit-config.yaml              # gitleaks, ruff, tools/check_unicode.py; every hook `rev:` a full commit SHA (G.7.6, G.9.3)
├── .gitleaks.toml  .gitleaks-baseline.json   # secret-scan configuration and the fingerprinted, justified false positives (G.9.3)
├── .env.example                         # M.4
├── .github/workflows/ci.yml             # K.19 outline; M.7
├── .github/workflows/supply-chain.yml   # separate workflow: osv-scanner over every uv.lock (K.19; M.7)
├── src/agentprov/                       # M.1.2: core, Python ≥ 3.14
├── capture/                             # M.1.7: agentprov-capture (agentprov_capture), Python ≥ 3.12, stdlib + rfc8785
├── backends/                            # M.1.7: shared/ (agentprov-backend), agentdojo/ and autodojo/ backend projects, Python 3.12
├── tests/                               # M.1.4 (layout normative in K.3.1)
├── docs/                                # M.1.5
├── examples/                            # M.1.6
├── plans/                               # M.1.6: committed live run plans (B PRJ-01)
├── corpora/                             # M.1.6: committed, data-free corpus specs (H.1.6); never corpus output
├── migration/                           # M.1.6: committed migration lock, maps and gate reports (J.1.5, J.3)
└── tools/                               # M.1.6: maintenance scripts and git hooks (tools/hooks/); not shipped
```

There is no `fuzz_atheris/` directory in v0.1: coverage-guided fuzzing with atheris is deferred (AD-10 row 18).
There is no environment directory in the repository: backend environments are built outside it (M.1.7).

### M.1.2 `src/agentprov/` (one line per file)

This tree is RESOLUTIONS §3.2 as amended by Addendum B (AD-10 as ruled adds `stats/` and `render/`). Each comment
names the component's layer (M.5). Directories that hold only data have no `__init__.py`. Owner tags in brackets name
the section that specifies the module's behaviour. [R-17, R-01, R-34, R-45]

```
src/agentprov/
├── __init__.py                 # re-exports __version__ only; imports nothing else (import-light; K.14)
├── __main__.py                 # `python -m agentprov` → agentprov.cli.main:main
├── _version.py                 # __version__ = importlib.metadata.version("agentprov"); pyproject is the single source (L.1.1)
├── py.typed                    # PEP 561 marker
├── errors.py                   # AgentProvError base (`code`, `exit_code`; N.1.3); IngestError (+ IngestSafetyError); AdapterError hierarchy and Issue (D.2.7)
├── formats.py                  # closed set of format ids (HL L.1.1); require_supported() fails closed (L.1.2)
├── envinfo.py                  # capture_environment() -> RunEnvironment (L.2.2; never secrets); interpreter_advisory() and the AD-16 release-mode check (G.3.8)
├── api.py                      # stable public facade for external consumers, e.g. the paper (M.6)
├── worker.py                   # T1 job entry `python -I -B -m agentprov.worker` (protocol agentprov-job/0.1; A3; G.4)
│
├── io/                         # L0 [MN, G]
│   ├── __init__.py
│   ├── atomic.py               # atomic_write_bytes/text (tmp+fsync+rename), atomic_swap_dir (.partial → final), LockFile, stale-tmp sweep
│   ├── canonical.py            # jcs_bytes(obj) (sole importer of rfc8785), sha256_hex, sha256_ref ("sha256:<hex>"), base32 helpers
│   └── workers.py              # T1 pool: spawn context, `python -I -B`, minimal env, rlimits, RSS watchdog, wall timeout, network+subprocess audit hook (A3; G.4)
│
├── ingest/                     # L0 [G] tier-1 input safety, before any parse (D8; A2)
│   ├── __init__.py
│   ├── limits.py               # IngestLimits and its defaults (G.3.2); overrides recorded in corpus.json
│   ├── loaders.py              # strict_json_loads, iter_jsonl: byte caps, strict UTF-8, duplicate keys, no NaN/Infinity, iterative depth cap 256, (line, byte offset) locators
│   ├── archives.py             # zip without extraction: EOCD/ZIP64 size pre-check, methods {0, 8, 93}, per-member checks, iter_zip_members (A2; G.3.5)
│   ├── streams.py              # codec sniffing of single compressed streams; their decompression is deferred (AD-10 row 16; G.3.4)
│   ├── names.py                # logical_name(), collision_key(): member names are labels, never paths (G.3.6)
│   ├── paths.py                # discover(), open_evidence(): local `--input` trees and live staging; no-follow, S_ISREG, st_nlink == 1 (G.3.6)
│   ├── quote.py                # quote_untrusted (fenced, with locator and hash), escape_untrusted, escape_untrusted_line, escape_markdown (A4; G.8.2)
│   └── yamlsafe.py             # the ONLY importer of yaml: bounded, alias-free safe_load (AD-17); used by the SEM marker and the compat shim
│
├── raw/                        # L1 [D3, HL, G] raw evidence store
│   ├── __init__.py
│   ├── store.py                # raw/objects/<h0h1>/<sha256>.<ext> (all bytes, incl. blobs, capture logs, native logs, members), mode 0444
│   ├── origins.py              # Origin records (git | hf | zenodo | url | corpus | capture | member | local) → raw/origins.jsonl
│   ├── members.py              # the versioned `expand` stage: container → (label, method, crc32, size, sha256) rows in raw/members.jsonl (AD-12)
│   ├── fetch.py                # pinned, extraction-free acquisition: bare git fetch with blob SHA-1 check; HF/Zenodo/URL over https (G.7.5)
│   ├── references.py           # raw/REFERENCES.json: resolves only against in-package profile origins; stores no command string (R-43)
│   └── purge.py                # `agentprov purge`: delete one object, write a tombstone (R-51; G.9.6)
│
├── aer/                        # L1 [C] canonical execution record
│   ├── __init__.py             # AER_VERSION = "aer/0.1"; RECORD_KINDS: the 13 kinds of Addendum B-1
│   ├── types.py                # TypedDicts for the 13 kinds, incl. the generic `activity` and `artefact` (AD-15 as ruled); Locator; RuleRef
│   ├── canon.py                # dumps_line (JCS + "\n"); encode/decode ($-escapes); lex_hints() → sparse ext.lex {ord, flt} (AD-02)
│   ├── ids.py                  # import_execution_id (mapping id "<adapter id>/<profile id>", [0:26]; AD-04), live_execution_id, local-id grammar
│   ├── evidence.py             # effective class: record `ev` (existence class) + longest-prefix `evf`; weakest (O > D > I)
│   ├── rules.py                # RuleRef grammar <ns>.<rule>@<n>[#/ptr]; RuleCatalogue model, load_catalogue() (mappers, SEM, PROV)
│   ├── rules/aer.rules.toml    # catalogue `aer` (data directory, no __init__.py; read through importlib.resources)
│   ├── writer.py               # AerWriter: backward refs, id uniqueness, JCS, seal
│   ├── reader.py               # streaming reader; seal verification; record index
│   ├── locators.py             # resolve(loc, *, header, store); `line` 0-based; `a` names a member object (AD-12)
│   ├── accounting.py           # accounting, computed once by mapper and validator → consistent | inconsistent | unverifiable (R-13)
│   └── validate.py             # AerValidator (streaming, single pass; D8 tier 2), validate_file; `activity`/`artefact` type labels checked against the family catalogue
│
├── sem/                        # L2 [C, D6] semantic layer
│   ├── __init__.py
│   ├── types.py                # SEM annotation records (type, span, value; RESOLUTIONS §3.8), SemanticsProfile protocol, SEM digest
│   ├── engine.py               # apply(AER, profile) → SEM lines (JCS); three-valued integrity, unknown tools fail closed (B PRV-16)
│   └── validate.py             # validate_sem (D8 tier 3)
│
├── prov/                       # L2 [EF] provenance engine
│   ├── __init__.py             # derive, ProvOptions, ProvDerivation, AGENTPROV_PROV_0_1
│   ├── engine.py               # rule driver; bundle routing (core, inference, assessment, top); exactly the Inference-6 closure over named activities, incl. generic `activity` records (AD-19; AD-15 as ruled)
│   ├── evidence.py             # EvidenceClass and statement-class arithmetic; reads classes only (AD-05)
│   ├── specs.py                # ProvSpec protocol; spec-id resolution (compat loaded lazily, M.5.2(3))
│   ├── iri.py                  # instance IRIs https://w3id.org/agentprov/exec/<ex>#<L(id)> with `#` → `-`; statement ids; derivation keys (E.4.2)
│   ├── vocab.py                # apv term constants generated from vocab/apv-0.2.ttl
│   ├── diff.py                 # diff_documents(old, new): order-insensitive PROV diff for recompute --show-diff (B COR-21)
│   ├── rules/                  # aprov.* rule families (E.1, E.3, E.7)
│   │   ├── __init__.py
│   │   ├── nodes.py            # node rules, incl. G-ACT (generic `activity` → typed prov:Activity) and the entity rule for generic `artefact` records
│   │   ├── edges.py            # edge rules, incl. G-USE (one `used` per input; class = evf of the input link), G-GEN (wasGeneratedBy from artefact.generated_by), G-ASSOC
│   │   ├── assess.py           # assessment bundle: apv:Assessment for activities and relations, mentionOf of entities only (R-21)
│   │   └── top.py              # conversion provenance; hadPrimarySource only for prov_primary ∈ {native, byte_derived} (R-22)
│   ├── catalogue/agentprov-prov-0.1.toml   # catalogue `aprov` = the prov:Plan of the derive activity
│   ├── serialise/
│   │   ├── __init__.py
│   │   ├── provjson.py         # canonical bundled PROV-JSON writer (JCS)
│   │   ├── trig.py             # PROV-O TriG, on demand only (`derive --trig DIR`; AD-10 row 3), and the round-trip check
│   │   └── time.py             # xsd:dateTime predicate shared with validators (B VAL-11)
│   └── compat/                 # [EF E.8, J] adprov-v2.3-compat: frozen verbatim port; imports restricted (M.5.2(3))
│       ├── __init__.py
│       ├── semdiff-map.toml    # the one machine-readable semantic diff (R-33); gate E, J.3.6, E.8.4 and docs/compat/ are generated from it
│       └── adprov_v2_3/
│           ├── __init__.py     # glue (not part of the oracle): spec id "adprov-v2.3-compat" (never bumped), status apv:RegressionOracle, the ProvSpec object
│           ├── build_prov.py  prov_emit.py  labeling.py  validate.py  conformance.py   # the oracle: AST-equal to 579a908; import statements are the only change (R-31)
│           ├── serialise.py    # glue: baseline byte layout, json.dumps(doc, indent=2), UTF-8
│           ├── PORT_MANIFEST.json   # per-file baseline sha256 and AST digest; records the yaml → ingest.yamlsafe import rewrite (R-31)
│           └── adprov.ttl      # byte copy of baseline docs/ns/adprov.ttl (sha256 4a9dcf4a…dca3, K.16(3))
│
├── views/                      # L2 [C] derived views of AER; read nothing from raw (AD-02)
│   ├── __init__.py
│   ├── transcript.py           # render(aer) -> dict: generic message transcript view (D1)
│   ├── transcript_v1.py        # render(aer) -> dict, render_converted(aer) -> dict, serialise(dict) -> bytes: AgentDojo-PROV v1 view (compat oracle input)
│   └── transcript_v1_fields.toml   # the single v1 ↔ AER field table (R-30)
│
├── vocab/                      # data [EF E.4]
│   ├── apv-0.2.ttl             # apv ontology (owl:versionInfo "0.2.0"); docs/ns/apv-0.2.ttl is a checked copy
│   └── apv-adprov-map-0.1.ttl  # adprov → apv mapping
│
├── validate/                   # L3 [D8] validators and the check registry
│   ├── __init__.py
│   ├── tiers.py                # check registry; CheckOutcome(pass|fail|skipped|not_applicable); strict/release; write gate; validation/results.jsonl and summary.json with library versions
│   ├── prov_structure.py       # generic PROV-JSON structure; no `used` object is an activity; every mentionOf supra is a declared entity; core declares every node it references (R-21)
│   ├── constraints.py          # faithful PROV-CONSTRAINTS subset per bundle; time-based checks are "MAY flag" diagnostics, reported apart (A5)
│   ├── roundtrip.py            # PROV-JSON → PROV-O → PROV-JSON round trip; library-independent completeness
│   ├── linkage.py              # evidence linkage: apv:sourcePointer → AER field; AER src → raw bytes
│   ├── profiles.py             # profile rules of agentprov-prov/0.1, incl. the never-emit checks and the G-* rules; optional SHACL (pyshacl lazily)
│   ├── corpus.py               # tier-5 check definitions over parsed manifest, index, register and derivation rows; imports nothing from agentprov.corpus (M.1.10)
│   └── shapes/                 # SHACL shapes: prov-o-core.ttl, agentprov-prov-0.1.ttl, adprov-v2.3-compat.ttl (R-50)
│
├── adapters/                   # [D] adapter model; layer per module in M.5.1 (D.2.1)
│   ├── __init__.py             # re-exports the protocols; imports NO adapter family
│   ├── protocols.py            # L4: Reader, Mapper, SourceTree, MappingContext (typing.Protocol)
│   ├── types.py                # L4: ArtefactRef, Origin, Locator, LocatedItem, ExecutionUnit, SniffResult, ReaderResult, … (no live types, R-17)
│   ├── profiles.py             # L4: SourceProfile model + load_profile(); generic schema [profile] [source] [licence] [lineage] [import] + [family.<ns>] (R-38)
│   ├── runner/                 # L6: map_unit, job_map (__init__); import_source() (importer.py, D.2.9); T1 job prov (provjob.py); dispatches expand, map and prov jobs to io.workers (phase 6: a package)
│   ├── registry/               # L6 [D.3, I.5] the sole status store
│   │   ├── __init__.py         # REGISTRY data, lazy dotted-path factories, EXTERNAL_OWNERS
│   │   ├── claims.py           # the one claims/lint library: registry status phrases + I.4 must-not-claim (README, datasheets, paper)
│   │   └── render.py           # `info --matrix`, `info --must-not-claim`; generated README and docs/sources/status.md blocks
│   ├── agentdojo/              # L4 family [D.6, D.10.4]: TraceLogger dialect and capture/0.1 mapping; no live code
│   │   ├── __init__.py
│   │   ├── dialect.py          # TraceLoggerReader (variants v0.k11, v1.k14, v1.k14.incomplete, drift.k18.messages, drift.k18.conversations)
│   │   ├── mapper.py           # TraceLoggerMapper (adapter id "agentdojo.tracelogger")
│   │   ├── capture_reader.py   # CaptureLogReader (dialect {id: "agentprov.capture", variant: "0.1"}); chain verified with agentprov_capture
│   │   ├── capture_mapper.py   # AgentDojoCaptureMapper (adapter id "agentdojo.capture")
│   │   ├── identity.py         # identity resolution driven by profile tables (pure)
│   │   ├── ext.schema.json     # closed schema of ext.agentdojo (+ ext.rope/agentdyn/drift/mandate/survey)
│   │   ├── family.schema.json  # closed schema of [family.agentdojo] in profiles
│   │   ├── profiles/           # data: agentdojo-upstream, agentdojo-live, rope, autodojo-via-rope, autodojo-live, agentdyn,
│   │   │                       #   drift, mandate-agentdojo-eval, survey-runs (.profile.toml; D.4)
│   │   ├── tables/             # data: identity tables (e.g. AgentDyn's 76 pipeline directories)
│   │   ├── rules/              # data: {agentdojo,rope,agentdyn,drift,mandate,survey,autodojo}.rules.toml (D.5)
│   │   └── semantics/          # semantics profile `agentdojo.suites` (C.14, EF; D6)
│   │       ├── __init__.py
│   │       └── profile.py  tables.py  marker.py  scoring.py  coordinates.py
│   ├── adprov/                 # L4 family [D.7] AgentDojo-PROV transcript/v1 importer (writes ext.lex through aer.canon.lex_hints, AD-02)
│   │   ├── __init__.py
│   │   ├── dialect.py  mapper.py
│   │   ├── layout.py           # output_relpath inversion for upstream linkage (J)
│   │   ├── transcript_v1.schema.json   # corrected import schema (B DOC-06)
│   │   └── profiles/adprov-v1.profile.toml  rules/adprov.rules.toml
│   ├── inspect/                # L4 family [D.9] Inspect AI .eval importer, normative in v0.1 (AD-06); producer band inspect_ai 0.3.247.dev69
│   │   ├── __init__.py
│   │   ├── dialect.py  mapper.py  ext.schema.json  family.schema.json
│   │   └── profiles/survey-agentharm.profile.toml  rules/inspect.rules.toml
│   └── stac/                   # [D.8] planned: a design note only (DESIGN.md); no reader or mapper ships in v0.1
│
├── corpus/                     # L5 [HL] corpus layer
│   ├── __init__.py
│   ├── spec.py                 # corpus-spec.toml loader (load_spec) and synthesis from CLI options (N.2.2)
│   ├── layout.py               # paths of RESOLUTIONS §3.6, sharding sha256(ex)[:2], dirname(v), .partial resolution, assert_writable, git-ignore check
│   ├── manifest.py             # corpus.json: content/root digests; producer block (python_version, interpreter_advisory, isolation); compat outputs flagged apv:RegressionOracle (R-55)
│   ├── index.py                # executions.jsonl rows (incl. unit, execution_observed, completeness; R-28); source_key string "sha256:<hex>#" + JCS(loc); logical_key()
│   ├── register.py             # register.jsonl: <stage>.<code> entries, severity info|warning|error (R-13)
│   ├── derive.py               # derivation DAG expand → map → sem → prov → validation → views; derivation keys; derivation.json; rederive() (package catalogues only, AD-14)
│   ├── dedup.py                # source_key deduplication; ownership (EXTERNAL_OWNERS + profile [lineage]) injected by the caller (M.5.2(1))
│   ├── integrity.py            # checksums.sha256, digest chain, verify_corpus(level=checksums|chain|rederive); deposit archives verified without extraction (AD-14)
│   ├── datasheet.py            # DATASHEET.md and CHANGELOG.md from manifest/index/register only; claims checker and the stats.tables information-loss function injected (M.5.2(1))
│   ├── package.py              # seal(): manifest, checksums, .partial → final swap
│   └── rules/corpus.rules.toml # catalogue `corpus`
│
├── release/                    # L5 [HL H.10] deposit builder; MUST NOT import any network library
│   ├── __init__.py
│   ├── builder.py              # build_deposit(): deterministic sharded archives grouped by licence class (spdx, sorted restrictions); refuses mixed classes unless --allow-mixed-licence-classes (AD-20(b))
│   └── metadata.py             # release.toml → deposit metadata JSON (draft only; never publishes)
│
├── stats/                      # L7 [AD-10 as ruled] minimal, generic statistics; stdlib only
│   ├── __init__.py             # compute(corpora, tables) -> StatsReport
│   ├── tables.py               # the four tables of N.2.12: counts, statements, unknowns, field_groups
│   ├── field_groups.toml       # the fixed capability list: field groups and their AER pointers (R-57; O.3.5)
│   └── output.py               # deterministic text, CSV, JSON (JCS) and Markdown writers
│
├── render/                     # L7 [AD-10 as ruled] extra `render` (pydot) + the Graphviz `dot` binary
│   ├── __init__.py
│   ├── graph.py                # render_prov_graph(): port of the baseline renderer (agentdojo_prov/visualize.py:115-185) reading agentprov-prov/0.1 bundles; core bundle by default
│   ├── dot.py                  # builds DOT text only (pydot `to_string()`); runs `dot -T<fmt>` with stdin, a timeout and atomic writes (visualize.py:187-206; G.8.6)
│   └── style.py                # labels from trusted grammars by default; styling from assessment annotations only when drawn; unknown integrity never drawn as trusted
│
├── migration/                  # L7 [J] baseline → AgentPROV migration gates (J.3.0 API)
│   ├── __init__.py
│   ├── lock.py                 # BaselineLock, load_lock() (migration/baseline.lock.json), tree_listing()
│   ├── gates.py                # the J.3.0 gate functions: G0, A (A1, A2), B, R (R1–R5), C (diagnostic; C1 opt-in), D, E (AD-07)
│   └── reconcile.py            # project(aer) comparison records
│
├── testing/                    # side layer [K.3.2]: core-only test support; never installed in a backend environment
│   ├── __init__.py
│   └── netguard.py  fs_guard.py  projections.py  golden.py  inference6.py
│
├── schemas/                    # data: the three published JSON Schemas (AD-10 row 13); in-code validators are authoritative (D2)
│   └── aer-0.1.schema.json  capture-0.1.schema.json  corpus-0.1.schema.json
│
└── cli/                        # L8: entry point (N)
    ├── __init__.py
    ├── main.py                 # build_parser(); main(argv: Sequence[str] | None = None) -> int; exception → exit code
    ├── common.py               # shared option groups, logging, corpus path resolution, summary JSON; display only through ingest.quote
    ├── run.py                  # `run`: .env (live extra), consent, T2 spawn of the backend worker, staging ingest
    ├── import_.py              # `import` (alias `convert`), `fetch`
    ├── derive.py               # `derive`, `recompute`
    ├── checks.py               # `validate`, `verify`
    ├── info.py                 # `info` (alias `sources`), `inspect`
    ├── package.py              # `package`
    ├── reports.py              # `stats`, `render`
    ├── backends.py             # `backends build` (`uv sync` in a scrubbed environment; G.6.2)
    └── admin.py                # `migrate`, `purge`
```

**What left the core tree** (RESOLUTIONS §3.2; R-01, R-17, R-34). The capture writer, session, gateway, transports
and endpoint registry moved to `agentprov_capture` and `agentprov_backend` (M.1.7). The live backend, the outcome
replay plugin, the historical checkers and the confound probe, the AutoDojo launcher, the generic live orchestration
package, the ML export and the analysis frames are no longer in core; replay, the checkers, the probe, the ML export
and the analysis frames are deferred (AD-10 rows 1–2; `docs/roadmap.md`). The corpus-level diff, collections and
lineage documents are deferred (AD-10 rows 5, 6, 10). The `ScriptedTransport` test double is
`agentprov_backend.testing`. Only three schemas are published (AD-10 row 13); the CLI-summary schema is a test asset
(N.1.4).

### M.1.3 Package-data rules

1. **Access.** Data files MUST be read through `importlib.resources.files(<owning package>)`, never through
   `__file__` arithmetic.
2. **Versioning.** Every data file that affects a derived byte has its version in the file name or in a version
   field. Its `{id, version, sha256}` is recorded wherever it is used (D.4.1; H.2.5).
3. **Pinned digests.** Frozen data is pinned by digest in tests: `prov/compat/adprov_v2_3/adprov.ttl` (K.16(3)),
   `prov/compat/adprov_v2_3/PORT_MANIFEST.json` (R-31) and `adapters/adprov/transcript_v1.schema.json`.
4. **Content.** Data files MUST NOT contain secrets, absolute paths, or text copied from untrusted artefacts.
   `agentprov_capture/endpoints.toml` holds environment-variable *names*, https base URLs and hosts only (M.1.7).
5. **Catalogue homes** (R-09): `aer` in `aer/rules/aer.rules.toml`; `aprov` in
   `prov/catalogue/agentprov-prov-0.1.toml`; `cap` in `capture/agentprov_capture/rules/cap.rules.toml`; `corpus` in
   `corpus/rules/corpus.rules.toml`; adapter catalogues in `adapters/<family>/rules/<ns>.rules.toml`. Catalogues and
   profiles carry monotonic integer versions (AD-18). The package ships every released version of each catalogue and
   profile, because `rederive` loads them only from package resources at the recorded version; an absent version is
   `rules.unavailable` (AD-14). D owns the file layout of superseded versions.
6. **Generic kinds.** Every `activity.type` and `artefact.type` value (`<ns>:<name>`) is declared in the family's
   rule catalogue, which the AER validator reads (AD-15 as ruled; D.5.2).

### M.1.4 `tests/`

The layout is normative in **K.3.1** [R-48]; the tree below copies its directories (K owns test paths; AD-SW20).
`tests/migration/test_test_map.py` (J.5) is one of the three files that K.3.1 adds for other sections. At directory
level:

```
tests/
├── conftest.py   invariants.toml   strategies/
├── fixtures/              # FIXTURES.json, LICENSES/, per-source raw samples (agentdojo/{v0.k11,v1.k14}/, rope/, agentdyn/, drift/,
│                          #   mandate/, survey/, agentdojo_inspect/, autodojo_via_rope/, inspect/, stac/), capture/, foobench/,
│                          #   synthetic/, expected/ (K.4); golden pairs in fixtures/agentdojo_prov_v1/golden/ (R-48);
│                          #   `binary` in .gitattributes (R-42)
├── unit/{aer,ingest,raw,sem,prov,validate,corpus,stats,views}/   # incl. the generic kinds (K.5.1) and stats (K.5.11)
├── render/                # K.5.12; `render` gate
├── prov/{compat/adprov_v2_3,spec_agentprov_prov_0_1}/   # ported baseline tests (legacy behaviour pinned); rules of agentprov-prov/0.1
├── adapters/              # test_profile_schema.py, test_rule_catalogues.py, test_dialect_detection.py
│   └── {registry,agentdojo,adprov,inspect,stac,foobench}/   # registry tests under adapters/registry/ (R-48); agentdojo/profiles/;
│                          #   the future-framework test in foobench/ (K.6.4; D.12)
├── golden/  integration/  differential/  property/  fuzz/  security/  reproducibility/   # security/ incl. the interpreter
│                          #   guard (K.12.12, SEC-26) and the agent channels (K.12.13)
├── boundary/              # test_import_boundary.py, test_optional_extras.py, layers.toml (M.5.5)
├── cli/                   # test_cli_contract.py and others (N.6); schemas/cli-summary-0.1.schema.json (N.1.4)
├── migration/             # test_test_map.py (J.5)
├── docs/  repo/  perf/  full_corpus/
```

- `tests/__init__.py` MUST NOT exist (B TST-19). `--import-mode=importlib` permits duplicate basenames (K.3.1).
- **Backend tests live in the backend projects** (R-01): `capture/tests/` (writer, hash chain, `redact`; run on 3.12
  and 3.14), `backends/shared/tests/`, `backends/agentdojo/tests/` (every baseline test that imports `agentdojo`, at
  least 73 of 343; the executor-mirror differential; live-vs-native; the hostile-worker case of SEC-25) and
  `backends/autodojo/tests/` (the fake-client worker test, K.8.4). Their pytest markers `agentdojo` and `autodojo`
  mean "backend project", not "core extra".
- Core tests read committed `capture/0.1` fixtures; they never import `agentprov_backend` (AD-01(e)).

### M.1.5 `docs/`

```
docs/
├── README.md               # documentation index
├── architecture/           # the AgentPROV architecture specification (Addendum B-3, C-2; AD-SW11)
│   ├── README.md           # index, section A (executive architecture) and the decision record (A, B, C)
│   ├── B_audit.md  C_data_model.md  D_adapters.md  EF_provenance.md  G_security.md  HL_corpus_versioning.md
│   └── I_matrix.md  J_migration.md  K_testing.md  MN_repo_cli.md  O_manuscript.md  PQ_phases_dod.md
│                           #   one file per section, under its spec basename; the M.5 layer table is generated into
│                           #   MN_repo_cli.md (tools/gen_docs.py; M.5.5)
├── cli.md                  # workflows (N.4) plus a reference generated from the argparse tree (tools/gen_docs.py)
├── adapter-guide.md        # adding a framework (D4): dialect, mapper, profile, rule catalogue, semantics, tests;
│                           #   specialised kinds first, generic `activity`/`artefact` only where none fits (AD-15 as ruled)
├── sources/                # matrix.md (the reviewed matrix document, AD-10 row 8); status.md generated from the registry (K.16(5))
├── compat/                 # adprov-v2.3.md (frozen baseline §5–§7 plus errata, B DOC-03); semantic-diff.md generated from
│                           #   prov/compat/semdiff-map.toml (R-33)
├── threat-model.md         # G (PQ phase 12)
├── roadmap.md              # every AD-10 deferral with its reason (RESOLUTIONS §4.14)
├── reports/                # full-snapshot import counts (R-15; HON-10) and the phase-13 regression reports
├── ns/                     # index.html (generated), apv-0.2.ttl (checked copy), apv-0.1.ttl (0.1.0 release), HOSTING.md (w3id plan; not submitted without consent, D7; U-02)
└── port/                   # baseline-map.json (B.1.3, regenerated against M.1.2; R-17), README.md
```

Addenda B-3 and C-2 place the specification in `docs/architecture/`: `README.md` holds section A and the decision
record (Addenda A, B and C), and every other section ships as one file under its spec basename (AD-SW11). C-2
supersedes the single `docs/architecture.md` of RESOLUTIONS R-50 and the r1 directory of format specs `docs/spec/`,
which no longer exists. The normative format specifications are those section files: `aer/0.1`, `capture/0.1` and
`sem/0.1` in `C_data_model.md`, `agentprov-prov/0.1` in `EF_provenance.md`, the corpus layout in
`HL_corpus_versioning.md` and ingest safety in `G_security.md`. The ML-export policy page is deferred with the export
(AD-10 row 1).

### M.1.6 `examples/`, `plans/`, `corpora/`, `migration/`, `tools/`

```
examples/                                  # small; offline unless marked; corpora are written under $AGENTPROV_HOME, never in the repository (R-52)
├── README.md
├── smoke/agentdojo-banking-smoke.toml     # 2-cell run plan for --llm-script (no keys, no network; needs `agentprov backends build agentdojo`)
├── smoke/banking-smoke.script.json        # scripted LLM replies (agentprov_backend.testing.ScriptedTransport format)
└── python/
    ├── read_execution.py                  # stream one .aer.jsonl; print evidence class, rule ids, unknowns (no content)
    ├── query_core_bundle.py               # rdflib over the core named graph of a TriG file made on demand by `derive --trig` (AD-10 row 3)
    └── load_rows.py                       # agentprov.api.open_corpus + rows(), as the paper's data stage (O.3.5; M.6)

plans/                                     # committed live run plans (TOML; format owned by D, read by agentprov_backend.runner; Q10)
├── README.md
├── agentdojo-v1.2.2-release.toml          # baseline release grid: 4 suites × {benign, direct, injecagent, important_instructions}
│                                          #   [README.md:227-228]; v2.3 display names declared as a deviation (B F-13)
└── autodojo-cache-replay.example.toml     # AutoDojo cache-replay cells for one (model, defence) cache cell

corpora/                                   # committed corpus specs (H.1.6); corpus OUTPUT never goes here (M.3)
├── README.md
└── <corpus_id>/{corpus-spec.toml, CARD.md, CHANGES.toml}
    # v0.1 corpus ids (H.4.2): agentdojo-upstream, agentdojo-prov-v2, agentdyn, rope, mandate-agentdojo-eval,
    #   ast-survey-agentdojo, ast-survey-agentharm (separate restricted-use corpus, U-05); stretch: drift;
    #   live: agentdojo-live-<campaign>, autodojo-live-<campaign>. No STAC corpus is built in v0.1 (planned; AD-10 row 22)

migration/                                 # [J] committed; small
├── baseline.lock.json                     # J.1.5 frozen baseline identity and tree listings
├── baseline-requirements.txt              # J.1.6: hash-locked export of baseline/pip_freeze.txt (minus its -e line); .baseline/venv and the old-vs-new job (AD-SW19)
├── expected_differences.toml              # J tolerated-differences register
├── test_map.json  baseline_test_ids.txt   # J.5 per-test port map
├── reports/<gate>/…json                   # J.3 gate reports
└── semdiff/semdiff-<tree>.{json,md}       # gate E output, generated from prov/compat/semdiff-map.toml (R-33)
# migration/local.toml is gitignored (machine-local paths)

tools/                                     # maintenance only; not in the wheel; `uv run python tools/<x>.py`
├── README.md
├── regen_golden.py                        # K.7.3 golden regeneration (refuses unless a recorded version changed)
├── gates.py                               # K.20 release-gate runner
├── coverage_ratchet.py                    # per-area coverage ratchet from the first measured value (AD-10 row 18; K.18.2; K.19 `coverage` job)
├── sync_ns.py                             # vocab/apv-0.2.ttl → docs/ns/; --check
├── gen_docs.py                            # docs/sources/status.md, docs/cli.md reference, M.5 table; --check
├── check_unicode.py  unicode_allowlist.toml   # invisible, bidi and control characters (G.8.3)
├── release_scan.py                        # gitleaks over a corpus or deposit tree, plus home/account-path and secret-shape rules over files and archive members (D-600) → release-scan.json (G.9.4)
├── ci/install-gitleaks.sh                 # installs a pinned gitleaks release, verified by sha256 (K.19 `secrets` job; G.9.3)
├── hooks/                                 # repository-local git hooks: pre-commit, pre-push (G.7.6, G.9.3)
└── migration/{baseline_probe.py, make_synthetic_v1.py}   # J: the only callers of baseline code
```

### M.1.7 `capture/` and `backends/`: the shared packages and the backend projects (A1; AD-01; D5)

A1 splits live capture out of core, and AD-01 fixes how [R-01, R-49]. AgentDojo and AutoDojo cannot share an
environment, because AutoDojo ships as `agentdojo` 0.1.35, the same name and version as PyPI AgentDojo
[sources/autodojo.md §7; verify/autodojo.md #18]. Core (Python ≥ 3.14) cannot be installed in a 3.12 backend
environment either. Hence four repository-root projects besides core:

```
capture/                                  # distribution agentprov-capture, import agentprov_capture (AD-01(a)) [C format, D code]
├── pyproject.toml                        # requires-python >=3.12; dependency rfc8785 only; build backend uv_build; no-build
├── agentprov_capture/
│   ├── __init__.py
│   ├── events.py                         # capture/0.1 event model (C.13 names: session.start … session.end), CaptureLog writer, reader, hash-chain verifier
│   ├── redact.py                         # allowlist redaction with a hard denylist and the fail-closed literal-value scan (A4; G.6.4)
│   ├── redact_allowlist.toml             # data; changed only by a reviewed commit with a test (G.6.4)
│   ├── envstate.py                       # environment digests and diffs
│   ├── endpoints.toml                    # endpoint registry: env-var NAMES, https base URLs, hosts, declared request-id headers (G.6.4, G.9.2)
│   └── rules/cap.rules.toml              # catalogue `cap` (R-09)
└── tests/                                # run on 3.12 (backend jobs) and 3.14 (core job)
backends/
├── shared/                               # distribution agentprov-backend, import agentprov_backend (AD-01(b)) [D]
│   ├── pyproject.toml                    # requires-python >=3.12; deps agentprov-capture (path), httpx, openai; never agentdojo, never agentprov
│   ├── agentprov_backend/
│   │   ├── __init__.py
│   │   ├── runner.py                     # ExecutionBackend, CellSpec, BenchmarkIdentity, CaptureHooks (moved out of core, R-17); cell expansion; per-cell sessions
│   │   ├── transport.py                  # recording httpx transport + LLM-span brackets recording input_at and n_messages: the default `native` element (AD-09)
│   │   ├── gateway.py                    # `gateway_compat`, the port of _CompatLLM: opt-in, declared request_modifying / harness_policy (AD-09)
│   │   ├── pass_recorder.py  executor_mirror.py  runtime.py  attacks.py
│   │   ├── worker.py                     # `python -I -B -m agentprov_backend.worker`; protocol agentprov-backend/0.1; hello / hello_ok identity
│   │   └── testing/                      # backend test support (AD-01(e); K.3.2)
│   │       ├── __init__.py               # re-exports ScriptedTransport (agentprov_backend.testing.ScriptedTransport)
│   │       ├── transport.py              # ScriptedTransport on httpx.MockTransport; backs `run --llm-script`
│   │       └── netguard.py               # socket guard for the T2 worker: install() when AGENTPROV_BLOCK_NETWORK=1
│   └── tests/
├── agentdojo/                            # backend project (no package of its own)
│   ├── pyproject.toml  uv.lock           # below; committed, hash-locked
│   ├── .python-version                   # "3.12" (baseline 3.12.14)
│   └── tests/                            # baseline tests that import agentdojo (≥ 73 of 343), executor-mirror differential, live-vs-native, hostile worker
└── autodojo/                             # backend project
    ├── README.md                         # why it is isolated; build and verification; the fork deltas to expect
    ├── pyproject.toml  uv.lock           # below; committed, hash-locked
    ├── .python-version                   # "3.12"
    └── tests/                            # fake-client worker test (K.8.4; D.11.5)
```

The AgentDojo backend project:

```toml
[project]
name = "agentprov-backend-agentdojo"
version = "0.1.0"
description = "AgentPROV live backend environment: stock AgentDojo 0.1.35"
requires-python = "==3.12.*"
dependencies = [
    "agentprov-capture",            # path source below
    "agentprov-backend",            # path source below
    "agentdojo==0.1.35",            # deliberate pin (D5)
]

[tool.uv]
package = false
required-version = ">=0.12.18"      # as core (M.2 note 2)
exclude-newer = "YYYY-MM-DDT00:00:00Z"   # a FIXED RFC 3339 timestamp, set at the first `uv lock` and moved deliberately (G.7.1(4))
no-build-package = ["agentdojo", "..."]   # wheels only (G.7.1(5)); every registry package of uv.lock (see note below)

[tool.uv.sources]
agentprov-capture = { path = "../../capture" }
agentprov-backend = { path = "../shared" }
```

The AutoDojo backend project:

```toml
[project]
name = "agentprov-backend-autodojo"
version = "0.1.0"
description = "AgentPROV live backend environment: the AutoDojo fork of agentdojo 0.1.35"
requires-python = "==3.12.*"
dependencies = [
    "agentprov-capture",
    "agentprov-backend",
    "agentdojo",        # the AutoDojo fork, from the pinned git source below
    "json-repair",      # fork runtime need [sources/autodojo.md §7; D.11.2]
    "nltk",             # idem; punkt_tab is pre-provisioned at build time (D.11.2); variant_generation is never imported
]

[project.optional-dependencies]
filters = ["agentdojo[transformers]"]   # PromptGuard/PIGuard/ProtectAI/DataFilter defences; GPU [sources/autodojo.md §7]

[tool.uv]
package = false
required-version = ">=0.12.18"
exclude-newer = "YYYY-MM-DDT00:00:00Z"
# no `no-build`: the fork is built from git; tests/security/test_supply_chain.py asserts wheels for everything else (G.7.1(5))

[tool.uv.sources]
agentprov-capture = { path = "../../capture" }
agentprov-backend = { path = "../shared" }
agentdojo = { git = "https://github.com/xhOwenMa/AutoDojo", rev = "aa458794b7eb7f082e94daeac4c0f55bfc0c90cc", subdirectory = "agentdojo" }
```

**Implementation note (phase 2, 2026-10-08).**
- `no-build = true` cannot be used: the two path dependencies (`agentprov-capture`, `agentprov-backend`) are source
  trees that uv must build. The committed `backends/agentdojo/pyproject.toml` therefore lists every registry package of
  its `uv.lock` in `no-build-package`. This answers G.11.3 item 5: every registry package in the three backend locks
  has wheels. The list is re-derived from the lock whenever it is re-locked, and `tests/security/test_supply_chain.py`
  (phase 12) asserts that it equals the lock's registry package set.
- `--no-config` (rule 2) also drops the project's own `[tool.uv]` table, so `exclude-newer` and `no-build-package` are
  lost and `--locked` reports the lock as stale. `agentprov backends build` MUST therefore pass these settings
  explicitly on the command line (`--exclude-newer <value read from the project pyproject>` and one
  `--no-build-package` per listed name) together with `--no-config`. CI jobs, which run in a clean runner, omit
  `--no-config`.
- uv may reuse a cached build of an unchanged-version path package (`agentprov-capture`, `agentprov-backend`).
  `agentprov backends build` therefore passes `--reinstall-package` for both, so the RECORD digests checked by
  rule 4 describe the current sources.
- The pytest markers of the backend projects are the core's names, `backend_agentdojo` and `backend_autodojo`. They
  replace the `agentdojo` and `autodojo` of this section and K.19.
- The AutoDojo fork at `aa458794` builds with hatchling. It has no custom build hooks and no `setup.py`, so locking it
  runs no upstream code beyond the standard hatchling metadata build.

Rules:

1. **No backend project depends on `agentprov`** (A1; AD-01). The import-boundary test checks `backends/*/uv.lock`
   for it, and checks that no module under `capture/` or `backends/` imports `agentprov` (M.5.5).
2. **Build** (`agentprov backends build <backend> --allow-network`, N.2.10; G.6.2). It runs
   `uv sync --locked --no-config --project backends/<backend>` with `UV_PROJECT_ENVIRONMENT` set to
   `$AGENTPROV_HOME/envs/<backend>-<commit8>/`, outside the repository, so that no `.venv` is created inside it
   (AD-01(c)). Every other `UV_*` variable that redirects resolution, configuration or environment files is scrubbed.
   `<commit8>` is the first 8 hex digits of the pinned fork commit (AutoDojo); for a backend pinned by version
   (AgentDojo) it is the first 8 hex digits of the sha256 of its `uv.lock` (M.1.10). The build also provisions NLTK
   data (AutoDojo), writes the marker `AGENTPROV_ENV.json` (`commit`, `lock_sha256`, `python`, `nltk_sha256`) and
   records the result of the `sandbox-exec` feasibility probe used for real-model runs (AD-13(b); G.4.10).
3. **No uv at run time.** `agentprov run` execs the built interpreter directly:
   `<env>/bin/python -I -B -m agentprov_backend.worker` (protocol `agentprov-backend/0.1`), with `HOME` =
   `$AGENTPROV_HOME/t2home/<session>`, cwd = `$AGENTPROV_HOME/staging/<session>/` and an explicit environment
   allowlist (no `UV_*`, no real `HOME`; AD-13; N.1.11(4)).
4. **Identity** (R-39, R-49). Before spawning, the parent (T0) computes the commit, `lock_sha256`, the dist-info
   RECORD digest and the guarded-source digests from the built environment and the lock. It cross-checks them against
   the worker's `hello_ok` and the capture `identity` event. The commit comes from PEP 610 `direct_url.json`; there
   is no upstream working tree and no editable fork. On mismatch the run exits 3. The observed commit, never the
   version string, is the identity (D9).
5. **Python 3.12.** The fork's dependency set is unverified on 3.12; the source report gives Python ≥3.10 as the
   requirement [sources/autodojo.md §7]. The first `agentprov backends build autodojo` settles it (Q3).
6. **Shared packages are libraries.** `capture/` and `backends/shared/` are resolved inside the core and backend
   locks as path dependencies, installed non-editable (so RECORD digests exist). They MAY carry their own lock for
   their own test jobs (G.7.1(2)).

### M.1.8 What is deliberately absent

- **Vendored third-party checkouts.** None. Upstream bytes enter through `raw.fetch` at pinned commits, by bare fetch
  with no checkout (B EXT-03, EXT-05; D3; G.7.5). The investigation's clones live outside the repository and the
  workspace, at `~/Desktop/PhD/Labs/AgentPROV-upstream/` (Addendum B-2), and nothing reads them.
- **An `agentdojo_prov` compatibility shim.** None. The old manuscript stays pinned to `579a908` (D12), which
  supersedes the shim proposed in [audit/corpus.md §4].
- **Entry-point plugin loading.** None (D4).
- **Data in git.** No committed corpora, raw downloads, renders or statistics output (M.3; K.17).
- **Placeholder modules.** A planned dialect ships at most a design note (`adapters/stac/DESIGN.md`, D.8).
- **Deferred packages** (AD-10; `docs/roadmap.md`): `analysis/`, `export/ml/`, outcome replay, historical checkers
  and the confound probe; collection manifests; the corpus SemVer checker; per-execution lineage documents. The
  frozen baseline environment at `579a908` remains the home of the deferred analyses until they are ported.

### M.1.9 Ownership summary

| Package or path | Owner | Notes |
|---|---|---|
| `aer`, `sem`, `views`; the `capture/0.1` format | C | |
| `adapters`; `agentprov_backend`; `backends/*` | D | `adapters.agentdojo.semantics` content: D6/SEM. Statuses: I |
| `agentprov_capture` | C (format), D (code) | redaction rules: G |
| `prov`, `vocab` | EF | `prov.compat`: EF E.8 with J |
| `validate` | D8 (validation) | check ids and tier semantics follow D8, EF and K |
| `corpus`, `release` | HL | |
| `ingest` limits and every security control | G | |
| `stats` | this section (paths, CLI) | table semantics: N.2.12; field groups: O.3.5 (R-57) |
| `render` | this section (paths, CLI) | port of the baseline renderer (B); display controls: G.8.6 |
| `migration` | J | |
| `testing`, `tests/` | K | backend tests in the backend projects (M.1.4) |
| `io`, `cli`, `api`, top-level modules | this section | |

### M.1.10 Path decisions

The r1 table of path decisions where sections disagreed is replaced by the canonical naming table,
RESOLUTIONS §3 (paths: §3.1–§3.2; corpus files: §3.6; CLI: §3.7), as amended by Addendum B [R-17]. The decisions
below are the ones this section still makes, because §3 is silent or Addendum B changed it.

| # | Item | Decision | Reason |
|---|---|---|---|
| 1 | `stats/`, `render/` (deferred in §3.2) | `src/agentprov/stats/`, `src/agentprov/render/` at L7 | Addendum B, AD-10 as ruled |
| 2 | Endpoint registry (not placed by §3) | `capture/agentprov_capture/endpoints.toml` | Read by the core live CLI entry (host checks, consent text) and by the backend harness; `agentprov_capture` is the only package both install |
| 3 | `validate/corpus.py` (canonical in the §3.2 validation row, a variant in its corpus row) | kept, holding only tier-5 check definitions over parsed rows; `verify` itself is `corpus/integrity.py` | `corpus` imports `validate`; the reverse would form a package cycle |
| 4 | `<commit8>` for a backend pinned by version | first 8 hex digits of the sha256 of its `uv.lock` | §3.1 defines the path for a fork commit only |
| 5 | Subprocess homes (RESOLUTIONS §4.11 item 10 names two) | `io.workers`, `cli.run`, `cli.backends`, `raw.fetch`, `render.dot`, `migration.gates` | G.11.1 row 15 |
| 6 | CLI-summary schema (`agentprov-cli-summary/0.1` is a format, but only three schemas are published) | `tests/cli/schemas/cli-summary-0.1.schema.json` | AD-10 row 13 |
| 7 | Source ids versus aliases | registry source ids `agentdojo`, `adprov-v1` (D.3.3); `agentdojo-logs`, `agentdojo-upstream`, `agentdojo-prov-v1` are CLI aliases (N.3.1) | R-11: `source_id` = registry id, `profile.id` = `agentdojo-upstream`, `corpus_id` = `agentdojo-upstream` |
| 8 | `aer/rules.py` beside the data directory `aer/rules/` | kept as in §3.2; `rules/` has no `__init__.py`, so the module wins the import and the catalogue is read through `importlib.resources` | §3.2 lists both |

---

## M.2 `pyproject.toml`

> **Resolved (AD-17, AD-01(d), AD-10 as ruled / R-47, R-01, R-34):** the r1 challenge to D10 is ruled. (a) PyYAML is a
> core dependency, imported only by `ingest/yamlsafe.py` (AD-17). (b) The `live` extra (`python-dotenv>=1.2.2`) holds
> the only dependency of the live CLI entry (AD-01(d)); there is no benchmark extra. (c) is moot: `openai` and `httpx`
> are dependencies of `agentprov-backend`, never of core. `tenacity` stays dropped (the retry policy lives in the
> backend harness). Addendum B keeps the `render` extra (AD-10 as ruled); the `analysis` and `all` extras are gone.

This is the core project's file. The `capture/` and backend projects are in M.1.7. [R-01, R-47, R-52, AD-16 as
ruled, AD-17]

```toml
[project]
name = "agentprov"
version = "0.1.0"
description = "Evidence-qualified W3C PROV provenance of LLM-agent executions, from live capture and from released benchmark logs"
readme = "README.md"
requires-python = ">=3.14"
license = "MIT"
license-files = ["LICENSE", "THIRD_PARTY_NOTICES.md"]
authors = [{ name = "Nicholas Jones" }]
keywords = ["provenance", "W3C PROV", "PROV-O", "LLM agents", "prompt injection", "AgentDojo", "benchmark"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Science/Research",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3 :: Only",
    "Programming Language :: Python :: 3.14",
    "Topic :: Scientific/Engineering",
    "Topic :: Security",
    "Typing :: Typed",
]
dependencies = [
    "prov>=3.2.2,<4",          # PROV-DM model; PROV-JSON <-> PROV-O round trip (D7). Baseline ran 3.2.2 (pip_freeze.txt)
    "rdflib>=7.6,<8",          # PROV-O TriG, isomorphism, completeness (D7, D8). Baseline ran 7.6.0
    "rfc8785>=0.1.4,<0.2",     # RFC 8785 (JCS) for AER/SEM lines and every digest (D2) [landscape/trace_formats.md §6.11]
    "pyyaml>=6.0.3,<7",        # imported only by agentprov.ingest.yamlsafe (AD-17); locked at 6.0.3
    "agentprov-capture",       # capture/0.1 reading and hash-chain verification (A1; AD-01(a)); path source below
]

[project.optional-dependencies]
live = [
    "python-dotenv>=1.2.2",    # the live CLI entry reads .env (CVE-2026-28684 fixed in 1.2.2; G.9.2); imported lazily in cli.run and cli.backends only
]
render = [
    "pydot>=3.0",              # `agentprov render` (AD-10 as ruled); plus the Graphviz `dot` system binary, which pip cannot provide
]
shacl = [
    "pyshacl>=0.25",           # baseline ran 0.40.1
]
dev = [
    "pytest>=8.0",
    "pytest-xdist>=3.6",       # K.3.3
    "pytest-timeout>=2.3",     # K.3.3
    "coverage[toml]>=7.6",     # K.3.3
    "hypothesis>=6.100",       # D8 tier 7
    "jsonschema>=4.23",        # schema-vs-validator differential tests for the three published schemas (D2, K.9.3)
    "ruff>=0.16,<0.17",
    "mypy>=1.11",
    "types-PyYAML",
]

[project.scripts]
agentprov = "agentprov.cli.main:main"

[project.urls]
Repository = "https://github.com/nickjones39/AgentPROV"

[build-system]
requires = ["uv_build>=0.12.18,<0.13"]
build-backend = "uv_build"

[tool.uv]
required-version = ">=0.12.18"          # Addendum C-1: the maintainer's uv; CI uses uv >= 0.12.22; raised to ">=0.12.22" when uv is upgraded (G.7.1(1))
exclude-newer = "YYYY-MM-DDT00:00:00Z"  # a FIXED RFC 3339 timestamp, set at the first `uv lock`, moved deliberately (G.7.1(4))
no-build = true                         # wheels only for registry packages (G.7.1(5); Q8)

[tool.uv.sources]
agentprov-capture = { path = "capture" }

[tool.uv.build-backend]
module-name = "agentprov"
module-root = "src"
# The sdist holds src/, README, licences and pyproject. Tests and fixtures (some CC BY-NC) stay in git (K.4.2).

# ---------------------------------------------------------------- ruff
[tool.ruff]
line-length = 110
target-version = "py314"
src = ["src", "tests", "tools"]
extend-exclude = ["tests/fixtures"]

[tool.ruff.format]
exclude = ["src/agentprov/prov/compat/**"]    # verbatim baseline port: keep diff-able against 579a908

[tool.ruff.lint]
# Pinned explicitly, so results do not depend on the installed ruff's defaults (baseline pyproject.toml:50-53).
# PLE2502 flags bidirectional control characters in source (G.8.3; SEC-13).
select = ["E4", "E7", "E9", "F", "I", "B", "UP", "S", "BLE", "TID", "T20", "PLE2502"]

[tool.ruff.lint.isort]
known-first-party = ["agentprov"]

[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "all"
# Optional-extra packages may be imported only inside functions, except where allowed below (M.5.3).
banned-module-level-imports = ["dotenv", "pydot", "pyshacl"]

[tool.ruff.lint.flake8-tidy-imports.banned-api]
"agentdojo".msg = "core never imports benchmark code; live code lives in backends/ (A1; AD-01)"
"agentprov_backend".msg = "core never imports the backend harness (A1; AD-01)"
"openai".msg = "core has no model client (A1); the backend harness owns it"
"httpx".msg = "core has no HTTP client library; raw.fetch uses urllib (G.7.5)"
"yaml".msg = "import YAML only through agentprov.ingest.yamlsafe (AD-17)"
"pickle".msg = "never deserialise untrusted input with pickle (D8 tier 1, K.12.6)"
"marshal".msg = "never deserialise untrusted input with marshal (D8 tier 1, K.12.6)"

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "S603", "S607", "T20", "TID251", "TID253"]
"tools/**" = ["T20", "S603", "S607"]
"src/agentprov/cli/**" = ["T20"]
"src/agentprov/ingest/yamlsafe.py" = ["TID251"]                # the one yaml importer (AD-17)
"src/agentprov/render/**" = ["TID253", "S603"]                  # `dot` subprocess; DOT text on stdin only (G.8.6)
"src/agentprov/raw/fetch.py" = ["S603", "S310"]                 # `git` subprocess; urllib with pinned URLs
"src/agentprov/io/workers.py" = ["S603"]                        # T1 worker processes (A3)
"src/agentprov/cli/run.py" = ["S603"]                           # exec of the built backend interpreter (AD-01(c))
"src/agentprov/cli/backends.py" = ["S603", "S607"]              # `uv sync` at build time (G.6.2)
"src/agentprov/migration/gates.py" = ["S603"]                   # baseline probe interpreter (J)
"src/agentprov/prov/compat/**" = ["B", "BLE", "UP", "S", "E7"]  # verbatim port; behaviour frozen by the byte-identity gate

# ---------------------------------------------------------------- mypy
[tool.mypy]
python_version = "3.14"
mypy_path = "src"
packages = ["agentprov"]
strict = true
warn_unreachable = true
enable_error_code = ["ignore-without-code", "redundant-expr", "truthy-bool"]

[[tool.mypy.overrides]]
module = ["prov.*", "pydot.*", "pyshacl.*", "rfc8785.*"]
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = ["agentprov.prov.compat.adprov_v2_3.*"]
disallow_untyped_defs = false
disallow_incomplete_defs = false
disallow_untyped_calls = false
check_untyped_defs = true

# ---------------------------------------------------------------- pytest / coverage (normative in K.3.3)
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = ["--strict-markers", "--strict-config", "-ra", "--import-mode=importlib", "-p", "no:cacheprovider"]
xfail_strict = true
filterwarnings = [
    "error",
    # rdflib 7.x emits this from its own serialiser (693 occurrences in the baseline run, baseline/pytest.txt).
    "ignore:Dataset.default_context is deprecated:DeprecationWarning:rdflib.graph",
]
markers = [
    "slow: more than ~5 s per test, or long Hypothesis/fuzz budgets; gate",
    "network: needs outbound network; gate",
    "live_artefacts: consumes capture/0.1 and native logs produced by a backend job (K.8.5); gate",
    "full_corpus: needs the frozen baseline corpora / full pinned upstream logs on disk; gate",
    "old_package: needs agentdojo-prov 1.0.0 @ 579a908 in a separate interpreter; gate",
    "shacl: needs the shacl extra; gate",
    "render: needs the render extra (pydot) and the graphviz dot binary; gate",
    "invariant(id): traceability tag (not a gate)",
    "allow_skip(reason): permits a runtime skip under AGENTPROV_STRICT_SKIPS=1 (not a gate)",
]

[tool.coverage.run]
branch = true
source = ["agentprov"]
parallel = true
concurrency = ["multiprocessing"]
```

The backend markers (`agentdojo`, `autodojo`) are declared in the backend projects' own `pyproject.toml` files, where
those tests live (M.1.4; R-01).

Notes:

1. **Version.** The version is static in `[project].version`, and `uv_build` requires that. `_version.py` reads it
   from the installed metadata (L.1.1).
2. **Python and uv (AD-16 as ruled).** `requires-python = ">=3.14"`, `.python-version` `3.14`, ruff `py314`, mypy
   `3.14`.
   - The 3.14 line gives stdlib `compression.zstd` for Inspect `.eval` members and the 2025–26 parser fixes
     (A1; [landscape/secure_ingestion.md §2]).
   - Two parser fixes landed only in 3.14.8. Below it, release mode refuses archive and compressed-stream
     ingestion (exit 3) and `package` refuses a corpus that records an `interpreter_advisory` (exit 4); dev mode
     warns and records (M.0(7); G.3.8). There is no override flag.
   - The core CI job pins the latest 3.14 patch, installed with uv ≥ 0.12.22 (G.7.6). There is no upper bound.
   - The committed uv floor is `>=0.12.18`, the maintainer's current uv [obs-M1], and CI uses uv ≥ 0.12.22
     (Addendum C-1), because AD-16 as ruled says development must not block on the upgrade. The floor is raised to
     `">=0.12.22"` in the commit that upgrades uv, which is recommended (G.7.1(1); G.11.1 row 13). Q9 is closed.
   - Backend projects run 3.12 (M.1.7); `agentprov-capture` supports ≥ 3.12 so that both can install it.
3. **Pins.** The ranges serve consumers outside the lock. Exact versions come from `uv.lock`, resolved under the fixed
   `exclude-newer` timestamp (G.7.1(4)). Validation reports record the `prov`, `rdflib` and `pyshacl` versions
   [audit/validation.md V19].
4. **Manuscript dependencies.** `matplotlib` and the other manuscript-only dependencies are excluded; the paper has
   its own environment (O.3) [audit/corpus.md §3.9]. If it imports `agentprov.api`, it needs Python ≥ 3.14 and no
   extra (R-64, with the floor of AD-16 as ruled).
5. **Graphviz.** `dot` is a system binary. `agentprov info` reports whether it is present. `render` exits 3 when it
   is missing (G.8.6).
6. **Removed from r1.** The benchmark extra and its `openai`/`httpx` entries, the `analysis` extra and the `all` extra
   (AD-01, AD-10). `python-dotenv` rises to `>=1.2.2` (G.9.2).

---

## M.3 `.gitignore`, `.gitattributes`

### M.3.1 `.gitignore`

In `.gitignore` the last matching pattern wins. The fixture re-inclusion therefore comes *after* the data patterns
and *before* the OS-junk patterns, so `.DS_Store` and `._*` stay excluded inside `tests/fixtures/` too.

Corpora, raw stores, caches, built environments and live staging live under `$AGENTPROV_HOME` or a user path outside
the working tree (A4; G.8.1). The data patterns below are a safety net, not a place for corpora (R-52).

```gitignore
# ── Data never committed (D9: corpora go to Zenodo, never Git; user rule: no corpora in Git) ──
/out/
/work/
/corpus/
/runs/
/logs/
/downloads/
/upstream/
/third_party/
/*-main/
*.partial/
*-rendered/
# corpora/ holds committed, data-free build specs (H.1.6). Anything else written there is ignored.
/corpora/*/*
!/corpora/*/corpus-spec.toml
!/corpora/*/CARD.md
!/corpora/*/CHANGES.toml
# Migration scratch (J.1.6, J.2.6): baseline venv, work tree, machine-local config
/.baseline/
/.migration-work/
/migration/local.toml
# AgentPROV local state and atomic-write leftovers ($AGENTPROV_HOME defaults to ~/.agentprov, outside the repo)
/.agentprov/
.agentprov.lock
*.tmp-*
# Data-bearing file types anywhere outside committed fixtures
*.aer.jsonl
*.sem.jsonl
*.capture.jsonl
*.prov.json
*.prov.trig
*.parquet
*.eval
*.zip
*.log
!/tests/fixtures/**

# ── Secrets ──
.env
.env.*
!.env.example
*.pem
*.key

# ── Environments, caches, build output (backend environments are built under $AGENTPROV_HOME/envs/, M.1.7) ──
.venv/
/backends/*/.venv/
/capture/.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
.hypothesis/
.coverage
.coverage.*
htmlcov/
build/
dist/
*.egg-info/

# ── Editors / OS (after the fixture re-include, so junk stays out of fixtures too) ──
.DS_Store
._*
.idea/
.vscode/
*.swp

# ── Agent tooling: local settings only; guidance files and .claude/settings.json are versioned (B EXT-01; G.8.4) ──
.claude/settings.local.json
CLAUDE.local.md
```

Comparison with the baseline `.gitignore`:

- **Kept:** `corpus/` (`:2`), `runs/` (`:8`) and `.env` (`:11`).
- **No longer ignored:** `CLAUDE.md` (`:14`). Agent guidance is versioned, as `AGENTS.md` plus a `CLAUDE.md` that
  points to it [audit/corpus.md §3.9; R-50].
- **Generalised:** the vendored `*-main/` directories (`:55-57`).
- **Dropped:** the local LaTeX report entries (B DOC-11; the paper has its own repository, D12).
- **New:**
  - `*.partial/` covers working corpora (N.1.5);
  - `*-rendered/` covers render trees (N.2.13);
  - the `/corpora/` rules allow specs to be committed, and hide any output accidentally written there;
  - `*.log` and `CLAUDE.local.md` (R-52); stray `.venv/` directories inside `backends/` and `capture/`, which
    AD-01(c) prevents by building environments under `$AGENTPROV_HOME/envs/`.

The enforcement is `tests/repo/test_repository_hygiene.py` (K.17), which checks `git ls-files`, not this file.

### M.3.2 `.gitattributes`

```gitattributes
* text=auto eol=lf
# Fixtures are compared byte for byte (compat byte identity, D7) and hold untrusted third-party text:
# `binary` = no EOL or encoding conversion, no textual diff and no merge, so `git diff` and `git log -p` never echo
# fixture text to a reader or a coding agent (R-42; G.8.1 item 5).
tests/fixtures/** binary
migration/baseline.lock.json -text
*.parquet binary
*.zip binary
```

### M.3.3 `.ignore` and `.rgignore`

Both files list `tests/fixtures/`, so that ripgrep-based search tools, including those that coding agents use, skip
fixture text by default (R-42; G.8.1 item 5). A deliberate search passes `--no-ignore`.
`tests/security/test_agent_channels.py` checks that both files exist and list the directory (SEC-13).

---

## M.4 `.env.example`

**Who reads `.env`.** Only the live CLI entry: `agentprov run` and `agentprov backends build` (A4; G.9.2; N.1.11).
It reads the file named by `--env-file`, or else `.env` at the **repository root**, never `./.env` from the current
directory (R-51; RESOLUTIONS §3.1). The repository root is the nearest ancestor of the current directory whose
`pyproject.toml` declares `name = "agentprov"`; without one, only `--env-file` works. The file is read with
`python-dotenv` (`live` extra) through `dotenv_values()` into a private mapping. No other command reads it.

**What the file contains.** Placeholders and public default URLs only: no values, and no default model ids. A model
id identifies the experiment, so it MUST be chosen explicitly (Q5, closed): `--model-id`, or the shorthand's
`*_MODEL` variable that the user sets. The baseline's silent code defaults (for example `OPENAI_MODEL` →
`gpt-4o-2024-08-06`, `runtime.py:441-443`) are not carried over.

**Endpoints** (R-39; G.9.2). Every base URL MUST be https, except loopback (`127.0.0.1`, `[::1]`, `localhost`). Its
host MUST match the endpoint's entry in `agentprov_capture/endpoints.toml` unless `--allow-custom-endpoint` is given,
which is recorded. A base URL with userinfo, a query or a fragment is refused, because a key could hide in it (G.6.4).

```dotenv
# AgentPROV — copy to `.env` at the repository root (or pass --env-file) and fill in. Never commit `.env`
# (it is gitignored); keep it mode 0600.
# Only `agentprov run` and `agentprov backends build` read this file.
# Values are never written to capture logs, AER, manifests, summaries or logs. Only the variable
# NAMES used and the endpoint host are recorded (L.2.2; D.10.1 AgentConfig.api_key_env).
# Base URLs must be https (loopback excepted) and match the hosts in agentprov_capture/endpoints.toml.

# ---- OpenAI-compatible endpoints (capture/agentprov_capture/endpoints.toml) ----
# DeepSeek  (--model deepseek  |  --endpoint deepseek --model-id ID)
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=

# OpenAI  (--model openai)
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=

# OpenRouter: one key serves the openrouter, gemini, llama, qwen and glm shorthands
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=
GEMINI_MODEL=
LLAMA_MODEL=
QWEN_MODEL=
GLM_MODEL=

# Local OpenAI-compatible server: Ollama, vLLM, llama.cpp  (--model ollama  |  --endpoint local)
LOCAL_LLM_BASE_URL=http://127.0.0.1:11434/v1
LOCAL_LLM_PORT=11434
LOCAL_MODEL_ID=
# Other local servers (D-690): set only to move a server off its default port (or use run --base-url)
OMLX_BASE_URL=
LMSTUDIO_BASE_URL=
MLX_LM_BASE_URL=
LLAMACPP_BASE_URL=
VLLM_BASE_URL=
LLM_TIMEOUT_S=180

# Reasoning controls. Leave empty for the provider default; the transmitted value is recorded either way.
REASONING_EFFORT=
REASONING_PASSBACK=1

# ---- AutoDojo worker (passed to the T2 worker only through the explicit allowlist of N.1.11(4); G.6.3) ----
# Native gemini-* targets through the fork's own LLM element (the default `native` element; AD-09; D.10.5)
GEMINI_API_KEY=
# Classifier-filter defences that download model weights (passed only when such a defence is configured)
HUGGING_FACE_HUB_TOKEN=
```

Where the names come from:

- `runtime.py:63,164,169,398-465,526-535`;
- the baseline README table (`README.md:205-220`);
- AutoDojo's `.env.example` and §7 [sources/autodojo.md §2, §7];
- D.11.3 rule 4, narrowed by G.6.3 (no `UV_*` wildcard).

**Ordinary environment variables.** Non-secret settings are environment variables, not `.env` entries, because
commands other than `run` need them:

| Variable | Purpose | Defined by |
|---|---|---|
| `AGENTPROV_HOME` | default `~/.agentprov`; holds `envs/`, `cache/`, `staging/`, `t2home/` and, by default, corpora (G.8.1) | D.11.2; AD-13 |
| `AGENTPROV_UPSTREAM_CACHE` | overrides the bare fetch cache | K, J; G.7.5 |
| `AGENTPROV_BASELINE_CORPUS`, `AGENTPROV_BASELINE_PYTHON`, `AGENTPROV_MIGRATION_WORK` | migration gates | J.2.6 |
| `AGENTPROV_GATES`, `AGENTPROV_STRICT_SKIPS`, `AGENTPROV_BLOCK_NETWORK` | test gates and guards | K.3.4 |

They are documented in `docs/cli.md`. There is no variable pointing at an upstream working tree: the AutoDojo fork
is resolved by uv from the pinned commit (R-49).

---

## M.5 Import layering

### M.5.1 Components and layers

A module belongs to the component of its **longest** matching prefix. It MAY import modules of its own component
and of lower layers only. M.5.2 lists the exceptions. The external `agentprov_capture` (stdlib + `rfc8785`) counts as
an L0 dependency.

| Layer | Components (module prefixes) | Role |
|---|---|---|
| L0 | `_version`, `errors`, `formats`, `envinfo`, `versions`, `host` (D-7), `progress` (N.1.14), `io` (incl. `io.workers`, which starts `agentprov.worker` by module name only), `ingest` | primitives; tier-1 safety; host capabilities; feedback sink; worker pool |
| L1 | `raw`, `aer`; `settings`, `keys`, `jobs` (application state, D-702/D-703/D-704: stdlib, `errors`, `ingest`, `io` only, plus `psutil` in `jobs`) | evidence and canonical record; the shared user settings and the keychain client |
| L2 | `sem`, `prov` (incl. `prov.compat`), `views`; `estimate` (D-701: reads AER documents, fetches through `raw.fetch`) | semantics, provenance engine, derived views. Within L2, `prov` may import `sem` and `views` |
| L3 | `validate`, `artefacts` (D.15), `stage_definitions` (D-623) | validators, check registry; artefact catalogues and safety net; the sem/prov/validation stage definitions the importer and `derive` share |
| L4 | `adapters.protocols`, `adapters.types`, `adapters.profiles`, `adapters.<family>` | readers, mappers, semantics profiles |
| L5 | `corpus`, `release` | corpus layer, deposits |
| L6 | `adapters.registry`, `adapters.runner`, `worker`, `presets` (N.2.1a) | orchestration; T1 job entry; host presets and local-model planning |
| L7 | `stats`, `render`, `migration` | consumers (`stats` and `render`: AD-10 as ruled) |
| L8 | `cli`, `api`, `__main__` | entry points |
| side | `testing` | MAY import L0–L6. It may be imported only by `tests/` and `tools/` |

### M.5.2 Rules (normative)

1. **No upward imports.** Dependency injection replaces them:
   - `corpus.derive` receives Mapper, SemanticsProvider and ProvSpec *objects*;
   - `validate.tiers` runs a spec's profile rules through the ProvSpec object;
   - `adapters.runner` receives a `CorpusWriter`;
   - `corpus.dedup` receives source-key ownership (registry `EXTERNAL_OWNERS` plus the profiles' `[lineage]`) from its
     caller, so there is no L5 → L6 import (R-17);
   - `corpus.datasheet` receives the claims checker of `adapters.registry.claims` from its caller;
   - `corpus.datasheet` (L5) receives the field-group/information-loss table function (`stats.tables`, L7) from its
     caller (`cli.package`) by injection, so the datasheet and `agentprov stats` share one computation without an
     L5 → L7 import.
2. **Families are siblings.** `adapters.X` MUST NOT import `adapters.Y` for X ≠ Y.
3. **Compat is quarantined.** `prov.compat` MAY be imported only by:
   - `agentprov.prov.specs`, lazily, when `adprov-v2.3-compat` is explicitly requested;
   - `agentprov.migration`;
   - tests.

   This is J's rule, extended by the spec loader that `derive --prov-spec adprov-v2.3-compat` needs. The oracle files
   import only the stdlib, `prov` and, through the rewritten import statements, `agentprov.ingest.yamlsafe` (R-31).
4. **Registry.** Only L6, L7, L8 and tests MAY import `adapters.registry`.
   - It imports no family module (D.2.1).
   - Its factories are `agentprov.`-namespace dotted strings, resolved lazily (D.3.1).
5. **No package cycles.** The package-level import graph MUST be a DAG consistent with the layer table.
6. **Nothing imports `cli`** except `__main__`. Nothing in `src/` imports `tests` or `tools`.
7. **Entry points import lazily.**
   - `cli` and `api` import `render`, the SHACL path of `validate.profiles`, `migration` and `dotenv` inside the
     function that needs them.
   - With core dependencies alone, these all work (K.14(4)): `--help`, `info`, `import`, `fetch`, `derive`,
     `recompute`, `validate`, `verify`, `inspect`, `package`, `stats` and `purge`. `run` and `backends` need the
     `live` extra and a built backend environment or `uv`; `render` needs the `render` extra and `dot`; `migrate`
     needs the baseline inputs (J).
8. **Startup self-check.** Every command validates the registry and profiles. A `ProfileError` there is a defect of
   the installed package, so it exits 70 (D.3.5 rule 4 said 2; see N.5; R-19).
9. **Process boundary (A1; AD-01).** Nothing under `src/agentprov/` imports `agentdojo`, `inspect_ai`, `openai`,
   `httpx` or `agentprov_backend`. Nothing under `capture/` or `backends/` imports `agentprov`. Core talks to a
   backend only through the worker protocol `agentprov-backend/0.1` and the staged `capture/0.1` files.

### M.5.3 Third-party import rules

| Package | Importers (module prefix) | How |
|---|---|---|
| `agentdojo`, `inspect_ai`, `openai`, `httpx`, `agentprov_backend` | none in `src/agentprov/` (backend projects only) | — |
| `agentprov_capture` | `adapters.agentdojo.capture_reader` (event model, chain verifier), `cli.run` (literal-value scan of staged files, `redact`), `presets` (endpoint registry; amended 2026-10-08, N.2.1a), `cli.keys` (the endpoint registry's key variables; D-702) | module level |
| `keyring` | `keys.helper` only (the keychain helper process, `python -I -m agentprov.keys.helper`; D-702) | inside the helper process only: the allowlisted back-end is constructed directly, never `keyring.get_keyring()` (D-655) |
| `psutil` | `jobs` only (`jobs.record`, `jobs.manager`, `jobs.supervisor`; D-704) | lazily, inside functions: process identity `(pid, create_time)` and process trees. psutil imports `socket` at module level for constants (as for the GUI, D-545); no `jobs` module opens a socket, and the allowance names psutil alone |
| `dotenv` | `cli.run`, `cli.backends` | lazily; `dotenv_values()` only; `load_dotenv`, `set_key`, `unset_key` forbidden (G.9.2) |
| `pydot`, `prov.dot` | `render` | module level allowed (extra). `pydot` builds DOT text only; its `create()` and `write_*()` are forbidden (G.8.6) |
| `pyshacl` | `validate.profiles` | lazily |
| `yaml` | `ingest.yamlsafe` only | bounded, alias-free `safe_load` (AD-17; G.3.7; K.12.6) |
| `rfc8785` | `io.canonical` | module level |
| `prov`, `rdflib` | `prov`, `validate`, `render`, `migration` | module level allowed |
| `zipfile`, `compression.zstd` | `ingest.archives`, `ingest.streams`, `raw.members` | inside T1 jobs; guarded by the AD-16 interpreter check (G.3.8) |
| `subprocess` | `raw.fetch` (git), `io.workers` (T1 workers), `cli.run` (the built backend interpreter), `cli.backends` (`uv sync`), `render.dot` (`dot`), `migration.gates` (baseline probe), `keys` (the keychain helper: this interpreter, `-I`, a fixed module; D-702), `jobs.manager` (a job's supervisor: this interpreter, `-I`, a fixed module) and `jobs.supervisor` (the job's argv: this interpreter's `agentprov`, or one resolved `tools/<name>.py` of the checkout; D-704) | absolute executable from `shutil.which`; argv built only from validated profile/config data (40-hex commits, relative paths), never from artefact content; never `shell=True` (G.11.1 row 15) |
| network (`urllib.request`, `http.client`, `socket`) | `raw.fetch`; `presets` (`http.client` only, for the loopback-only preflight of N.2.1a, which refuses any non-loopback host before connecting); `cli.live.localmodels` (`http.client` only, for local model discovery, D-691: loopback hosts only, the connected peer checked, no proxy, no redirect); `cli.live.providermodels` (`http.client` only, for an API provider's model list, D-730: HTTPS to the registry host, TLS verified, no proxy, no redirect); `io.worker_testjobs` (`socket`, for the hostile test job kinds that probe the G.4.4 audit hook; enabled only with `--test-kinds`); `cli.live.egress` (`socket`, D-664: the T0 egress proxy, a loopback listener that tunnels CONNECT to the run's exact endpoint pairs and forwards plain HTTP to its LAN model server's pair only (D-698), and the sandbox probe's loopback listeners; parent process only, never in a T1 or T2 worker); `testing.netguard` patches them | `release` MUST NOT import any of them (H.10.1). `agentprov_zenodo` (the `agentprov-zenodo` distribution in `zenodo/`, outside the `agentprov` package, which never imports it; `http.client` and `ssl`, D-790, D-880) is the one draft-only Zenodo client. T1 jobs run under a network and subprocess audit hook (G.4.4) |

**Globally forbidden in `src/agentprov/**`** (K.12.6 static list, extended by G):

- `eval`, `exec` or `compile` on non-literals;
- `pickle` or `marshal` loads;
- `yaml.load`, `yaml.unsafe_load`, `yaml.full_load`;
- `os.system`, `os.popen`, `shell=True`;
- `shutil.unpack_archive`, `tarfile` (tar is refused in v0.1), `zipfile.ZipFile.extract` and `extractall`;
- `dotenv.load_dotenv`, `set_key`, `unset_key` (G.9.2);
- `pydot` `create()` and `write_*()` (G.8.6).

### M.5.4 Rationale (evidence)

The baseline's "offline" `recompute` imported `agentdojo` through `recompute → generate → observer`, which an import
probe observed [audit/corpus.md §3.3 R1, App. A]. `convert_runs` had the same coupling [audit/legacy_replay.md §3.6
D8]. D10 forbids benchmark imports in core, and A1 removes benchmark code from the core environment altogether. The
rules above make that path impossible to write without a lint error and a test failure, and impossible to install.

### M.5.5 Enforcement

1. **Lint.** Ruff TID251 and TID253 run on every commit (M.2) [obs-M2]. Lint alone is insufficient: it cannot see
   transitive or dynamic imports.
2. **Static test** (`tests/boundary/test_import_boundary.py`).
   - It parses every module under `src/agentprov` with `ast`.
   - It collects imports at any nesting depth, plus string literals passed to `importlib.import_module` or used as
     registry factories.
   - It checks each edge against M.5.1–M.5.3, and checks the package graph for cycles.
   - It also checks the D.2.1 rules: `yaml` only in `ingest/yamlsafe.py`; `agentprov_capture` imports only the
     stdlib and `rfc8785`; no module under `capture/` or `backends/` imports `agentprov`; no `backends/*/uv.lock`
     contains `agentprov` (PQ Q.1).
   - The rule table is data (`tests/boundary/layers.toml`). `tools/gen_docs.py` renders it into
     `docs/architecture/MN_repo_cli.md` (M.1.5).
3. **Dynamic test** (K.14(1)).
   - Every module except `testing` and `render` is imported in a fresh interpreter (`render` is imported in the
     `extras` job).
   - No top-level package of K.14's `FORBIDDEN` set may appear in `sys.modules`: `agentdojo`, `agentprov_backend`,
     `inspect_ai`, `openai`, `anthropic`, `google`, `cohere`, `httpx`, `pandas`, `pyarrow`, `numpy`, `networkx`,
     `pydot`, `pyshacl`, `dotenv`.
4. **Install-level test** (K.14(3)). CI's `core` job asserts that `agentdojo`, `openai`, `httpx`, `inspect_ai` and
   `agentprov_backend` are not installed. Each backend job asserts that `agentprov` is not installed in the backend
   environment (AD-01).
5. **Registry test.** In the `core` job, every registry factory resolves, and its target's component is permitted for
   that use.

### M.5.6 Implementation resolutions (phase 11, 2026-10-12)

Notes only. Decisions: DECISIONS D-30 to D-49.

1. **M.1.2 files, as built.** `purge` is `corpus/purge.py` (engine) and `cli/purge.py`, not `raw/purge.py`, because `raw/`
   belonged to another session during phase 11 (D-46); moving it is a rename. Added or placed differently from the tree
   above: `corpus/{rawtree,reader,facets,shapes}.py` (the stored-raw candidate source for re-map, `CorpusReader`, the index
   facet functions, the closed row shapes), `corpus/derive.py` holds `derive`/`recompute` and the comparison (D-30) and
   `corpus/integrity.py` part 1 (checksums, set, content and root digests; the `chain` and `rederive` levels: U4,
   pending), `release/{builder,metadata}.py`, `stats/{source,tables,fieldgroups,exclusions,output,datasheet}.py`,
   `formats.py`, `api.py`, `testing/fs_guard.py`, `adapters/registry/claims.py` (D-36), `migration/gate_d.py` and
   `gate_d_worker.py` (D-49), `cli/{derive,deposit,inspect,package,purge,stats,checks}.py`, and `tools/release_scan.py`.
2. **M.5.3 (subprocess).** `cli.package` runs `git` as a subprocess (the cleanliness and commit of the producer, and the
   git-ignore check of H.1.5(5)); the call lives in `cli/` (L8), not in `corpus/` or `release/`, which import no process or
   network module (`corpus.package.seal` receives the result). `tools/release_scan.py` runs `gitleaks` (D-42).
3. **M.5.2(1) injection.** `corpus.derive` receives catalogues and profile digests from the CLI; `corpus.datasheet.render`
   receives the claims checker and the stats field-group table; `release.build_deposit` receives the scanner, verifier and
   lint (D-30, D-36, D-42).
4. **M.5.2(3).** `agentprov.prov.specs.load_compat_spec()` is the only importer of `prov.compat` outside `migration` and
   tests (D-37).

---

## M.6 Public Python API (`agentprov.api`)

**Why a facade.** The baseline's cross-repository API grew implicitly: the manuscript imported 18 symbols from 5
modules, and the documentation listed 5 of them [audit/corpus.md §4]. AgentPROV instead exposes one explicit facade.
Everything else is internal and may change in any 0.x release.

```python
# agentprov/api.py — stable within 0.1.x; tested by tests/cli/test_cli_contract.py::test_public_api; stdlib + core deps only
from agentprov._version import __version__
from agentprov.formats import FORMATS                       # format name -> version id

def open_corpus(root: str | os.PathLike[str], *, verify: Literal["none", "checksums", "chain"] = "checksums") -> Corpus: ...
    # sealed or working (.partial) corpus; raises IntegrityError when verification fails
def verify_corpus(root, *, level: Literal["checksums", "chain", "rederive"] = "chain",
                  sample: int | None = None, seed: int | None = None) -> VerifyReport: ...   # = corpus.integrity
def iter_executions(corpus: Corpus, *, select: Mapping[str, str | Sequence[str]] | None = None) -> Iterator[IndexRow]: ...
def read_aer(path_or_row) -> Execution: ...                 # seal-verified streaming read
def rows(corpus: Corpus, name: FrameName) -> Iterator[Mapping[str, JsonScalar]]: ...   # plain rows; the paper builds its own frames (R-34)
FRAME_NAMES: tuple[str, ...] = ("executions", "statements", "field_status", "validation", "profiles", "lineage")
def statistics(corpora: Sequence[Corpus], *,
               tables: Sequence[str] = ("counts", "statements", "unknowns", "field_groups")) -> StatsReport: ...
    # = agentprov.stats (AD-10 as ruled); one result per corpus, never pooled (N.2.12)
def field_groups() -> tuple[FieldGroup, ...]: ...           # stats/field_groups.toml: id and AER JSON Pointers per group
    # (the O.3.5 list; R-57); package-resource data, read-only
def semantics_profile(id: str, version: int) -> Mapping[str, JsonValue]: ...
    # package-resource data of a semantics profile at the recorded integer version, e.g. ("agentdojo.suites", 1);
    # read-only; imports no benchmark; the corpus `rules/` copy is only digest-compared (AD-14; O.3.5)
def source_registry() -> tuple[SourceRegistration, ...]: ...   # D.3 registry; feeds the `profiles` rows
def check_claim(source_ids: Iterable[str], tags: Iterable[ClaimTag], *,
                derivation: Mapping[str, str] | None = None, location: str = "",
                agent_executions_only: bool = False, phrase: str | None = None) -> list[ClaimViolation]: ...   # adapters.registry.claims (I.5.6; D-540)
from agentprov.adapters.registry.claims import coverage_phrase, lint_text   # re-exported unchanged (I.5.6; O.3.5)
```

**Row sets** (R-64, R-28; columns owned by O.3.5 and this section):

| Name | One row per | Columns include |
|---|---|---|
| `executions` | index row | `ex`, `source_id`, `profile`, `corpus_id`, `unit`, `execution_observed`, `completeness`, `status`, facets (incl. `defense_id`), digests. The paper computes `n_executions := unit == agent_execution ∧ execution_observed` |
| `statements` | PROV statement | bundle, relation, evidence class, rule id, `apv:sourcePointer` |
| `field_status` | (execution, field group) | class O/D/I, or the `unk` reason (R-57) |
| `validation` | row of the corpus `validation/results.jsonl` | check id and version, outcome `pass\|fail\|skipped\|not_applicable`; read, never re-run (R-64) |
| `profiles` | registry part and profile | statuses, caveat, licence policy, `[lineage]` |
| `lineage` | lineage edge | `from_node`, `to_node`, `relation`, `n`, `basis`; computed from `corpus.json`, `raw/origins.jsonl` (with `source_key` duplicates) and the owner declarations in each profile's `[lineage]` only, as recorded in a sealed manifest's `sources[].lineage` (D-541: `snapshot_of` to `repo@commit`, the declared edges, each declared duplicate with `n` its matching raw objects, and within-corpus `byte_identical`; a corpus without `sources[].lineage` raises `ApiUnavailable`) |

**Consumers.**

- The paper package MUST import only `agentprov.api` (O.3.5: "reads sealed corpora through the framework's public
  API only"). It needs Python ≥ 3.14 (M.2 note 4) and builds its own data frames from `rows()`; the framework ships
  no `analysis` package (AD-10 row 1).
- The paper reads through `agentprov.api` the field-group list (`field_groups()`), the `agentdojo.suites` profile
  data (`semantics_profile()`), the claims functions `lint_text` and `coverage_phrase` and the `lineage` rows
  (O.3.5).
- The r1 `frame()` (pandas), the `semdiff` frame and `score()` are removed: the gate-E report is J's file, which
  the paper pins and reads itself (O.3.5), and the flow baselines are deferred (AD-10 row 1). The `lineage` row set
  is not a lineage document: per-execution lineage documents and collection manifests stay deferred (AD-10 rows 5
  and 6).

---

## M.7 Continuous integration (summary)

The CI outline is normative in K.19, as amended [R-01, R-49, R-52; G.7.6; G.11.1 row 24]. The jobs of
`.github/workflows/ci.yml` carry K.19's names: `lint`, `core`, `capture`, `backend-shared`, `backend-agentdojo`,
`backend-autodojo`, `live-map`, `extras`, `coverage`, `secrets`, `thorough`, `network` and `old-vs-new`. Supply-chain
scanning is a separate workflow, `.github/workflows/supply-chain.yml`. This section adds these constraints:

- every job uses uv ≥ 0.12.22 (Addendum C-1) and installs only from a lock: `uv sync --locked` inside the project it
  tests, with the extras it needs; `lint` runs `uv lock --check` for every lock of the five projects;
- **`lint`**: ruff, mypy, `tools/gen_docs.py --check`, `tools/sync_ns.py --check`, `tools/check_unicode.py`;
- **`core`**: Python pinned to the latest 3.14 patch; no extra other than `dev`; asserts that `agentdojo`,
  `agentprov_backend`, `openai`, `httpx` and `inspect_ai` are not installed; includes the interpreter-guard test
  (SEC-26, monkeypatched version) and the boundary tests;
- **`capture`**: the `capture/` tests on Python 3.12 and 3.14;
- **`backend-shared`**: the `backends/shared/` tests on Python 3.12;
- **`backend-agentdojo`**: `uv sync --locked` in `backends/agentdojo` (Python 3.12), a check that `agentdojo` is
  0.1.35, the `agentdojo`-marked tests, and an upload of their live outputs for `live-map`;
- **`backend-autodojo`** (manual dispatch only; see the manual-run points below): installs core on 3.14, runs
  `agentprov backends build autodojo` (`uv sync --locked --no-config` on the backend project, Python 3.12, with the
  fork resolved by uv from its pinned commit and its identity read from PEP 610 `direct_url.json`), and runs the
  project's `autodojo`-marked tests in the built environment. There is no upstream working tree and no editable fork
  (R-49);
- **`live-map`**: the core side of the live runs, the `live_artefacts` tests over the `backend-agentdojo` outputs
  (K.8.5);
- **`extras`**: core plus the `render` extra and Graphviz `dot`, and the `shacl` extra;
- **`coverage`**: combines the `core` and `extras` coverage data and runs `tools/coverage_ratchet.py` (K.18.2);
- **`secrets`**: gitleaks, installed by `tools/ci/install-gitleaks.sh`, over the full history (G.9.3);
- **`thorough`** (manual dispatch only): the `slow` gate under the `thorough` Hypothesis profile;
- **`network`** (manual dispatch only): the `network` gate; pinned fetches are verified by digest;
- **`old-vs-new`** (manual dispatch only): installs the baseline from `migration/baseline-requirements.txt`,
  the hash-locked export of `baseline/pip_freeze.txt`, with `--require-hashes`, or from a mirrored wheel (R-49;
  AD-SW19), and runs the `old_package` gate;
- **supply-chain** (separate workflow, on changes to any `uv.lock` and by manual dispatch): osv-scanner over every
  `uv.lock` (AD-10 row 19; SEC-23);
- migration gates and full-corpus gates run locally only (J; K.20);
- **no scheduled CI** (D-22): the manual-dispatch jobs run at the points defined in K.19.1, namely before a software
  release tag, before building or depositing a corpus release, before submitting a thesis chapter or paper that
  reports live-backend or migration results, and after changing what they exercise (AGENTS.md §8 "Manual CI runs"
  repeats the list);
- no job holds model-provider secrets. Live tests use `agentprov_backend.testing.ScriptedTransport` (AD-01(e)).
  Every action is pinned by full commit SHA, with `permissions: contents: read` (G.7.6).

---

## N.1 CLI conventions

### N.1.1 Parser and entry point

1. **Library: `argparse` (stdlib).** Every baseline CLI used it (`generate.py:844`, `recompute.py:188`,
   `convert_runs.py:412`, `package.py:501`, `replay.py:534`, `ml_export.py:814`, `runtime.py:628`). Nothing needed
   here (subcommands, aliases, mutually exclusive groups, parent parsers) justifies a click or typer dependency in
   core.
2. **Entry function.** `agentprov.cli.main:main(argv: Sequence[str] | None = None) -> int`.
   - It builds the parser (`build_parser() -> argparse.ArgumentParser`), runs the startup self-check (M.5.2(8)),
     dispatches, and maps exceptions to exit codes (N.1.3).
   - The console script and `python -m agentprov` call it.
   - `main` never calls `sys.exit`. Tests call `main([...])` (K.15).
3. **Parser settings.**
   - `allow_abbrev=False` everywhere, so `--dry` never matches `--dry-run`.
   - Shared options live in parent parsers attached to the root *and* to every subparser, with
     `default=argparse.SUPPRESS`. `agentprov -v import …` therefore equals `agentprov import … -v`.
4. **Aliases.**
   - argparse aliases: `import`→`convert`, `info`→`sources`.
   - Source-id aliases are resolved by the CLI (N.3.1), not by argparse.

### N.1.2 Global options (every command)

| Option | Effect |
|---|---|
| `-h, --help` | help; exit 0 |
| `--version` | `agentprov 0.1.0` plus the format/spec versions emitted (`aer/0.1 sem/0.1 capture/0.1 agentprov-prov/0.1 apv 0.2.0`, corpus-layer format ids) and the interpreter version with its advisory status (`interpreter_advisory`, G.3.8); exit 0 |
| `-v, --verbose` (repeatable) / `-q, --quiet` | log level DEBUG / INFO (default) / WARNING |
| `--log-format {text,json}` | stderr log format (N.1.12) |
| `--log-file PATH` | additionally log to PATH (DEBUG, JSON lines) |
| `--log-content` | permit escaped content excerpts in DEBUG logs (N.1.12); off by default |
| `--progress {off,summary,status,steps,trace}` | live feedback level (N.1.14); default `status` when stderr is a terminal, else `summary`; `-q` implies `off` unless `--progress` is given; env `AGENTPROV_PROGRESS` |
| `--progress-format {auto,tty,plain,jsonl}` | feedback rendering (N.1.14); `auto` = `tty` on an interactive terminal, else `plain` |
| `--progress-file PATH` | additionally append every feedback event, at the selected level but never below `status`, as `agentprov-progress/0.2` JSON lines to PATH (N.1.14(2); D-393) |
| `--progress-interval SECONDS` | heartbeat interval of the progress file (default 2, minimum 1) |
| `--progress-max-bytes N` | rotate the progress file to `PATH.1` past N bytes (default 8 MiB, minimum 64 KiB) |
| `--control-file PATH` | writers: poll PATH for an `agentprov-control/0.1` request, `drain` or `stop` (N.1.10(5); D-394) |
| `--show-content` | at `steps` and `trace`, add escaped, truncated content excerpts to step lines (N.1.14); off by default |
| `--content-chars N` | excerpt length for `--show-content` (default 200, maximum 2000) |
| `--json` | summary document to stdout (N.1.4); human messages stay on stderr |
| `--summary-json PATH` | same document to PATH (atomic) |
| `--max-listed N` | cap on `failures[]` entries in the summary (default 100) |
| `--no-colour` (alias `--no-color`) | no ANSI colour. Colour is also off when stderr is not a TTY or `NO_COLOR` is set |
| `--break-stale-lock` | writers only: remove a lock whose pid is dead on this host (G6) |

### N.1.3 Exit codes

| Code | Name | Meaning |
|---|---|---|
| 0 | `ok` | Every requested unit was processed, and every requested check passed. Units sealed *with issues* count as processed (HL R2, D.2.9) |
| 1 | `failures` | The command completed, but something failed. A unit failed: a row with `status: failed`, a degenerate unit, an inconclusive or inconsistent live cell, or a stage error. Or a check failed: validation, verification, an *unexplained* `recompute` change, or a check `skipped`/`unverified` under `--strict`/`--release`. The summary says which |
| 2 | `usage` | argparse error, invalid combination, unknown source or backend id (with suggestions), missing or wrong-type path |
| 3 | `environment` | missing extra (`live`, `render`, `shacl`); missing binary (`git`, `uv`, `dot`); missing credential variable; backend environment absent, or identity mismatch between the T0 digests, `hello_ok` and the capture `identity` event (R-39); mutable (unpinned) origin (K.15); archive or compressed-stream ingestion below CPython 3.14.8 in release mode (`ingest.interpreter.unpatched`; AD-16 as ruled; G.3.8) |
| 4 | `refused` | a guard or policy refused (N.1.9): sealed corpus, overlapping trees, un-ignored output in a git work tree, mixed configuration or versions, lock held, partial corpus given to `package`, network needed without `--allow-network`, live run without consent, a real-model run without `--containment`, or with `--containment sandbox-exec` when the feasibility probe did not pass (AD-13(b); G.4.10), synthetic or `test_only` corpus given to `--deposit`, a corpus whose manifest records an `interpreter_advisory` given to `package` (AD-16 as ruled), `--release` with `--in-process` (G.4.9), mixed licence classes in one deposit without `--allow-mixed-licence-classes` (AD-20(b)), non-https or non-registered endpoint without `--allow-custom-endpoint` (R-39), an unconfirmed `purge` |
| 5 | `unsupported` | source or capability status `planned` or `not_possible` (incl. mirrors), or no capability for the requested mode (N.3) |
| 70 | `internal` | uncaught exception or broken package data (registry/profile self-check). One line on stderr; traceback frames with `-v` or in `--log-file`, with every exception argument passed through `escape_untrusted` (R-42) |
| 130 | `interrupted` | SIGINT, SIGTERM or SIGHUP; in-flight work sealed or rolled back (N.1.10) |

**Precedence.** Pre-flight conditions (2, 3, 4, 5) are raised before any unit is processed. After that, 130 beats
70, which beats 1, which beats 0.

**Reconciliation.**

- The baseline's `generate` used 1 for "all cells failed" and 2 for "some failed" (`generate.py:895-902`). That
  collided with argparse's 2. The distinction now lives in the summary (`counters.failed == counters.attempted`).
- HL H.8.5 used "2 = usage or environment", K.15 used "3 = environment", and D.2.9 used "2 = profile or registry
  error". These are reconciled here, and N.5 records each change. D and HL adopt this table (R-19).

### N.1.4 Output streams and the summary document

1. **Streams.** stdout carries only machine output: the `--json` summary, or the payload of `inspect`, `info` and
   `stats`. Progress, notices and errors go to stderr.
2. **Summary document.** `format: "agentprov-cli-summary/0.1"`. Its JSON Schema is a test asset,
   `tests/cli/schemas/cli-summary-0.1.schema.json`, not a published schema (AD-10 row 13; M.1.10 row 6). Its
   fields:

   | Field | Content |
   |---|---|
   | `command`, `agentprov_version`, `exit_code` | — |
   | `outcome` | `ok|failures|usage|environment|refused|unsupported|internal|interrupted` |
   | `dry_run` | — |
   | `corpus` | `{corpus_id, root, state: "working"|"sealed", content_digest|null}` |
   | `counters` | command-specific integers; for `import`, D.2.9's names |
   | `issues_by_code` | — |
   | `failures[]` | `{subject: {ex}|{cell}|{source_key}|{path}, stage, code, detail}`, sorted by subject, capped by `--max-listed`, with `failures_truncated`. `source_key` is the string `"sha256:<hex>#" + JCS(loc)`; `code` is a register code `<stage>.<code>` (R-13); `detail` passes `escape_untrusted` |
   | `refusal` | N.3, or for outcome `refused` (exit 4) the typed refusal `{id: <command>, mode: <command>, status: <error code>, lines: [reason]}` (P-3), or `null` |
   | `notices[]` | e.g. the compat notice whenever `adprov-v2.3-compat` output is written or loaded (R-55), and the dev-mode interpreter warning (G.3.8) |
   | `options` | normalised; never a secret or a credential value; `$HOME` written `<home>` (R-51) |

3. **Byte stability.** The summary is serialised as JCS. It holds no wall-clock times or durations, so two runs on
   the same input give byte-identical summaries (K.15(1)). Timings go to logs only.
4. **Paths.** Paths inside a corpus are reported relative to the corpus root (K.15(5)). Other paths are reported as
   given.

### N.1.5 Corpus paths: working and sealed

Every corpus-bearing command takes `--corpus DIR`. The CLI resolves it as follows.

| Situation | Writers (`run`, `import`, `derive`, `validate` on a working corpus, `purge`) | Readers (`inspect`, `verify`, `validate --report`, `stats`, `render`, `recompute`, `fetch`) |
|---|---|---|
| `DIR/corpus.json` has `"sealed": true` | refuse, exit 4: sealed corpora are immutable; build a new version (H.1.5(3)) | read `DIR` |
| `DIR.partial/` exists | write into `DIR.partial/` | read `DIR.partial/` (state `working`, stated in every message) |
| neither exists | create `DIR.partial/` | exit 2 |
| user passed `…/DIR.partial` explicitly | normalised to `DIR` first | idem |

`package` seals `DIR.partial/` and renames it to `DIR/` with `io.atomic.atomic_swap_dir` (N.2.11). A working tree's
name marks it as unsealed. A crash leaves a resumable working tree, or a sealed `DIR.partial/` that the next `package`
run finishes (N.2.11), never a half-sealed corpus (H.1.5(1)).

### N.1.6 Dry runs (`--dry-run`)

`--dry-run` is accepted by `run`, `import`, `fetch`, `derive`, `recompute`, `validate`, `package`, `render`,
`backends build` and `purge`. (`stats`, `verify`, `inspect` and `info` never write.)

1. **No writes.** Nothing is created, modified or deleted. That covers working trees, caches, locks, `.partial`
   directories and stale-temp sweeps. The only exceptions are the requested `--log-file` and `--summary-json`. No
   lock is taken.
2. **No network.** No model call, no fetch, no `uv sync`.
3. **Every in-memory stage runs.** That covers tier-1 safety, dialect detection, mapping, SEM, PROV, the full write
   gate and validation. A dry run therefore reports the same failures and dispositions as the real run would. This
   fixes the baseline recompute defect R3 [audit/corpus.md §3.3]. D.2.9 likewise: "writes and deletes nothing".
4. **Counters.** They carry the real-run names. `summary.dry_run = true` marks them hypothetical. Would-be paths are
   printed: the first 20 with `-v`, all of them with `--json`.
5. **Exit codes.** The same as the real run would give.

Command-specific behaviour:

- **`import --fetch --dry-run`** resolves the pinned origin and prints the fetch plan: repo, commit, tree, and the
  profile's `expected_files`/`expected_bytes`. It maps only if the pin is already cached.
- **`run --dry-run`**:
  1. resolves the backend, the plan, the endpoint, credential *presence* and the benchmark identity. The parent
     computes the T0 identity digests of the built backend environment and spawns the worker, which performs the
     `hello` handshake and expands the plan into cells without any model call; the benchmark is imported only
     there, in T2 (AD-01);
  2. enumerates the cells;
  3. computes `plan_sha256` and the `config_digest`;
  4. applies the resume rules and prints the plan.

  This replaces the baseline `runtime --dry-run` smoke test (`runtime.py:628-659`; B CAP-05). The worker's staging
  directory is a temporary one, removed afterwards; nothing enters a corpus.

### N.1.7 `--limit`, `--select`, `--sample`

**`--limit N`** (N ≥ 0; omitting it is the only way to say "no limit").

- It counts units **newly mapped/written** in this invocation:
  - `import`/`derive`: executions (D.2.9: "counts mapped units only; 0 maps nothing");
  - `run`: attempts newly executed;
  - `render`: graphs rendered.
- Resumed, filtered, excluded, duplicate and failed units do not consume the limit [audit/legacy_replay.md §3.3
  rule 13].
- The check precedes each unit, so `--limit 0` processes nothing but still runs every pre-flight check
  (`convert_runs.py:301-306`).
- Order is deterministic:
  - `import`: byte-sorted POSIX paths, then in-artefact locator (D.2.9);
  - `run`: plan order.
- With `--jobs > 1` the limit stays exact. Units are handed out while `written + in_flight < N`, and a failed unit
  frees its slot.

**`--select KEY=VALUE[,VALUE…]`** (repeatable).

- `KEY` is an index facet (H.3.3); `agentprov info --source ID` lists them.
- Values within one option are ORed. Repeated options are ANDed.
- For `import`, path-derivable keys apply before reading, and all other keys after mapping (counted `filtered`).
- A unit filtered before mapping is never this run's failure [audit/legacy_replay.md §3.3 rule 12].
- `--suite`, `--attack`, `--pipeline` and `--variant` are shorthands.

**`--sample N --seed S`** (`validate`, `verify`, `recompute`).

- It draws a seeded uniform sample, without replacement, over the sorted execution ids of the selection.
- This fixes the first-N bias of `conformance_summary` [audit/corpus.md §3.4.3 S3].
- It is forbidden with `--release` (H.8.5).

**Partial working corpora.**

- A working corpus written with `--limit`, any filter or `--sample` is marked `"partial": true` in its unsealed
  manifest, with the effective selection recorded (top-level `selection`: the last run's; its `limit` only while that
  run's limit still caps the snapshot, see below). Its `until` is the furthest stage the corpus holds, never lowered by a
  later `--until raw` or `--until aer` run; `derive` and `recompute` read the furthest of it, the recorded layers and
  `aer` when the index holds an execution (D-623).
- Each snapshot imported with a selection also records it in its own entry, `selection = {filters, limit[, sample]}`
  (NF-36, regen item 130). A snapshot imported whole records none, so an ordinary import's manifest is unchanged. The
  corpus stays `partial` while any snapshot records a selection: importing another snapshot whole never clears it. A
  sealed snapshot's `selection` (the spec's `{include, exclude}`, H.2), which a `derive` from a sealed corpus carries
  into the working manifest, is not an import selection: that snapshot is complete.
- A snapshot the corpus already lists is resumed with the selection of eligible units it recorded: the filters and the
  sample's `n`, `mode` and `seed` (none for a snapshot recorded whole). `--limit` is not part of it: it is an
  incremental cap, so `--limit 5` then `--limit 10`, or repeated `--limit` runs, extend one snapshot by design, and a
  pure `--limit` run is allowed on a snapshot recorded whole. Other filters or another sample are refused before
  anything is written (G4, exit 4, `corpus.identity_mismatch`), and so is a filter or sample on a snapshot recorded
  whole (it would declare a selection the snapshot does not have): one snapshot never mixes two selections; import it
  into another corpus instead.
- The snapshot's recorded `limit` is cumulative: the units held under it, so a re-map, which starts from no executions,
  maps the same ones (`--limit 1` then `--limit 2` record 3). A limited run that ran to the end and mapped fewer than
  its limit found nothing left: the snapshot is exhausted and the limit is dropped (with no filter or sample left the
  snapshot is whole and the corpus complete). A selection run with no limit that ran to the end drops it too. A limit
  never narrows a snapshot recorded without a cap (whole, or a selection run to the end); an interrupted run adds the
  units it indexed to the recorded cap (one it mapped but never indexed is mapped again by the resume). With
  `--until raw` nothing is mapped and the recorded limit (or a new snapshot's given one) stays, for a `derive` to map;
  it holds no unit, so a mapping resume of a snapshot that has no execution yet counts its cap from 0.
- `package` refuses a partial corpus with exit 4, and also a corpus any of whose snapshots records a selection.
  Re-run the same `import` without filters; it resumes. This selection-free, limit-free run is the completion path:
  once it has run to the end (at least to the AER stage) the snapshot's selection is dropped, and the corpus is
  complete when no snapshot keeps one. An interrupted completion keeps the recorded selection; for a snapshot that
  records only a cap it adds the units it indexed to it (with a filter or sample those units lie outside the
  selection, which no re-map reproduces).
- A working manifest written before the per-snapshot record (`partial: true`, no snapshot carrying a selection) gives
  every listed snapshot its top-level selection; a selection-free resume of each snapshot completes it.
- **A run that stopped early** (D-610, regen item 150) marks the snapshot it was importing
  `incomplete: {"reason": "drained" | "interrupted"}` and the corpus `partial`, whatever its selection (N.1.10(2), (5)).
  The mark records what happened, never a selection: no `--limit` is invented for the units a stopped run held. A
  **drain** that NF-36's cumulative cap already describes is not marked. That is a drained `--limit` run, or a drained
  completion or same-selection run of a capped snapshot without a filter or sample left out, mapping from the source
  (not `--until raw`), whose last mapped candidate ended in a unit the cap counts (a non-degenerate one). The snapshot
  stays partial through its selection, a re-map maps the same units, and an earlier mark is never hidden by it. An
  interrupted run is always marked: it can leave a mapped, stored, never-indexed batch. A drain whose last candidate was
  rejected or degenerate is marked too: a re-map under the cap stops right after its last counted unit. A later
  run of that snapshot clears it once it has run to the end with nothing left to map: it mapped (not `--until raw`) and
  had no `--limit`, or found fewer units than its limit. That is the same command re-run, with the same selection or
  none. A `--limit` run that stopped at its cap with units left keeps the mark, and a run of another snapshot never
  clears it. Until then `package` refuses the corpus (exit 4, `package.refused.incomplete`), and `derive` and
  `recompute` refuse it as their source (exit 4, `corpus.derive.incomplete`), since a re-map would map what the raw
  store holds, not what the corpus holds. `verify --level rederive` reports the re-derivation as unavailable. A corpus
  no run stopped carries no mark, so its manifest is unchanged.
- `derive`/`recompute` and `verify --level rederive` re-map each snapshot with the selection it recorded (its
  cumulative limit included); the re-mapped snapshot records that selection as replayed.
- This keeps HL R1/R5 (every candidate gets exactly one disposition) intact.

### N.1.8 Resumability

Every writer is idempotent. Repeating a command on unchanged inputs writes nothing new and leaves a byte-identical
tree (K.15(7)).

1. **Unit keys.**
   - Import: `(ex, artefact sha256, adapter version, profile sha256, catalogue version)` (D.2.9).
   - Live cell: `(cell_key, config_digest, repeat_index)`. `config_digest` covers `AgentConfig` (secret-free),
     `BenchmarkIdentity` (an `agentprov_backend` type, reported by the worker and checked against the T0 digests) and
     `attack_params` (B F-14; D.10.1).
2. **Write order** per unit: raw → AER → SEM → PROV → validation row → index row.
   - The index row comes last. A unit without one is incomplete.
   - Existing stage outputs are reused when their derivation keys match (H.8.3).
   - Raw evidence is never recomputed. A sealed capture is never re-run [audit/capture.md §4.5 G-1/G-2].
3. **Version mismatch.** A working corpus begun under different adapter, catalogue, profile or spec versions is
   refused (exit 4). Use `recompute --out NEW` (N.2.4). A `derive` or `recompute` resumed in an existing `NEW.partial`
   must match what began it: the semantics profiles and the function digests of the recomputed layers (BF-32), and with
   them the `--skip-prov-conformance` setting, which the validation stage's definition carries (pre-round review PR-7,
   D-525 addendum). Otherwise it is refused (exit 4, `corpus.derive.resume_mismatch`).
4. **Live attempts (HL R7).** Every attempt is its own sealed execution with its `capture.attempt` index (AD-03), and
   is never overwritten.
   - A cell is done when some attempt is *conclusive*: its capture session ended `complete`, and the accounting
     verdict in the AER seal is `consistent` or `unverifiable`. Accounting is computed once, by the AER mapper and
     validator; the parent reads the seal verdict to decide re-attempts (R-13).
   - Cells whose sessions ended `incomplete`, `errored` or `aborted`, including interrupted ones, are re-attempted
     until `--max-attempts` is exhausted. The default is 3, counted across invocations.
   - `--retry-inconsistent` also re-attempts cells whose attempts all carry the seal issue `accounting_inconsistent`
     (register code `map.accounting_inconsistent`).
5. **Failed import units** (`status: failed`, HL R3) are retried only with `--retry-failed`. The register keeps the
   history.

### N.1.9 Output-tree guards (exit 4)

| Id | Guard | Applies to |
|---|---|---|
| G1 | **Sealed is immutable.** No writer touches a tree any of whose ancestors holds `corpus.json` with `"sealed": true` (`corpus.layout.assert_writable`, H.1.5(2)). This replaces the name-based `corpus-prov` guard (`convert_runs.py:242-260`) [audit/legacy_replay.md §5] | all writers |
| G2 | **Disjoint trees.** The output is disjoint from every input: `--input`, the source corpus of `recompute`, the cache, `$AGENTPROV_HOME/envs/`, live staging, the installed package. Inputs are opened read-only, and tests snapshot them with `testing.fs_guard` | all writers |
| G3 | **Not in git unless ignored.** An output inside a git work tree must be reported by `git check-ignore` (H.1.5(5)). Corpora belong under `$AGENTPROV_HOME` or a user path outside the working tree (G.8.1); `/out/`, `/work/` and `*.partial/` are ignored only as a safety net (M.3) | all writers |
| G4 | **Identity.** No writing into a working corpus with a different `corpus_id`, source, snapshot set, mode (import/live) or format/spec versions (H.1.1) | `run`, `import`, `derive` |
| G5 | **Mixed live configuration.** A different `config_digest` in an existing live working corpus is refused unless `--allow-mixed-config`. With the flag, the manifest records `mixed_config: true` and the facets keep both configurations distinguishable. This generalises `ADPROV_ALLOW_MIXED_CONFIG` (`generate.py:347`) | `run` |
| G6 | **One writer.** `<corpus>.partial/.agentprov.lock` is created with `O_EXCL` and holds `{pid, host, command, started}`. A live lock refuses. A stale lock (dead pid, same host) is removed only with `--break-stale-lock` | all writers |
| G6a | **Shared state outside a corpus** (`agentprov.io.locks`). Advisory locks with the same record. **Exclusive:** the fetch cache's `<cache>/.agentprov.lock`, taken only around a write (a git fetch, a download, a history fetch, `purge --cache`; cached reads never lock), and a backend environment's build lock `$AGENTPROV_HOME/locks/envs/<env>.lock`. **Shared:** each `run` registers in `locks/envs/<env>.users/` and `locks/staging/`. A build refuses while the environment has a live user, and a run refuses during a build. Bounded: no lock waits, and none outlives its process. A dead holder on this host is removed, because every protected operation is idempotent; a live, foreign or unreadable holder refuses at once (exit 4, `io.resource_busy`), naming the pid, command and start time. A staging directory is an orphan only when `locks/staging/` has no live user | `fetch`, `import --fetch`, `verify --against-pins`, `purge --cache`, `backends build`, `run` |
| G7 | **No source-derived paths.** Output paths come only from execution ids, digests and version ids (H.1.3(1)). Path traversal is removed by construction | all writers |
| G8 | **Renders and statistics stay outside the corpus.** Renders go to `<corpus>-rendered/` or `--out`. Statistics go to stdout or `--out`. Neither writes inside a corpus; a sealed corpus is closed-world (H.1.5(4); G.8.6) | `render`, `stats` |
| G9 | **Atomicity.** Files are written as temp, then `fsync`, then rename. Tree results (`package`, `recompute --out`) are built in `<out>.partial/` and swapped. Leftover `*.tmp-<pid>` files of dead pids are swept on start | all writers |

### N.1.10 Parallelism, locking and interruption

1. **`--jobs N`.** Defaults: 1 for `run` (paid endpoints), and 0 (= `os.cpu_count()`) for offline commands. Outputs
   are byte-identical for every N (K.13). The baseline's hard-coded 18-process launcher becomes
   `run --plan … --jobs 18` (B PRJ-01). For `run` (DECISIONS D-9):
   - `--jobs N` is the number of **concurrent traces**: N backend workers, each running one cell at a time and each
     making its own API calls. A plan file may set `jobs`, and the command line overrides it.
   - N MUST be ≥ 1. `--jobs 0` is a usage error (exit 2), because a CPU count says nothing about API-bound work.
   - There is no built-in upper bound and no silent clamping. The parent computes the host maximum from the D-7 host
     constants (usable memory divided by the per-worker memory budget). A larger N is a usage error (exit 2) whose
     message names that maximum.
   - `--start-stagger SECONDS` (default 0) spreads the first cell start of each worker over the interval. Worker `i`
     starts at `i × SECONDS / N`. The schedule is deterministic, replacing the baseline's random 0–20 s sleep. It
     changes no request.
   - `jobs` and `start_stagger_s` are recorded in the `corpus.json` producer block and in each session's
     `session.start` run parameters. Concurrency affects provider load and rate limiting, so it is part of the
     recorded run conditions, never hidden configuration. There is no environment-variable default for `run`.
2. **First SIGINT, SIGTERM or SIGHUP.**
   - No new units are started, and in-flight atomic writes complete.
   - SIGHUP (the controlling terminal closed) takes this path too, so a hang-up never leaves a stale lock or loses
     `import`'s unflushed index rows. A SIGHUP inherited as ignored (`nohup`) stays ignored. The summary notice names
     the signal (`interrupted (SIGHUP)`).
   - In-flight live sessions are sealed with status `aborted` and their evidence kept (HL R7; D.11.3 rule 3).
   - `import` flushes what it holds and writes its working manifest with the snapshot marked
     `incomplete: {"reason": "interrupted"}` and the corpus `partial` (N.1.7; D-610), so `package`, `derive` and
     `recompute` refuse it until the same command has run to the end. The same holds for an import that raises for any
     other reason.
   - The summary is written, the lock is released, and the command exits 130.
3. **Second signal.** Abort immediately. The process trees of the live T2 workers are killed first, because a worker
   runs in its own session and would otherwise finish its cell, making paid calls. Temporary files are left for the
   G9 sweep, and the corpus stays resumable. Nothing is flushed, as after a SIGKILL: an import's index rows and manifest
   are written only at its end, so a fresh corpus has no `corpus.json` (which `package` refuses) and an existing one
   keeps its previous manifest and rows (D-610).
4. **Backend workers (T2)** are stopped with `shutdown`, then the process group is killed. A per-cell timeout follows
   D.11.3 rule 3. When a worker dies, the parent appends the terminal `session.end` event with
   `appended_by: "parent"` and status `aborted` (R-16).
5. **`--control-file PATH`** (D-394). A job manager writes `{"format":"agentprov-control/0.1","request":"drain"|"stop",
   "issued","nonce"}` to PATH atomically, and the CLI polls it (`agentprov.cli.control`).
   - **Polling.** A daemon thread `stat`s the file at most once a second and reads it only when it changed, at most
     4 KiB, with the strict loader.
   - **Ignored requests:** a request already in the file at start (it belongs to an earlier invocation) and a nonce
     seen before.
   - **Acknowledgement.** Every request is echoed as a `control` progress event `{request, nonce, accepted, effect}`. An
     invalid or unknown one is acknowledged as not accepted and stops nothing.
   - **`stop`** is the first SIGTERM on every OS (item 2). It is simulated in the main thread, so Windows gets a graceful
     path too, and the summary notice names the nonce.
   - **`drain`** finishes the in-flight units, flushes and exits 0 with progress outcome `drained`. It is resumable by
     re-running the same argv. A drained `import` records its snapshot `incomplete: {"reason": "drained"}` and the
     corpus `partial`, and its summary says so (N.1.7; D-610); the re-run that reaches the end clears the mark. A command opts in through `control.drain_supported()` and checks `control.draining()`
     at unit boundaries.
   - **Commands that do not opt in** degrade a drain to a stop and say so (`effect`). That is every command until
     `run`, `derive` and `recompute` are wired. `import` opts in (D-525). The importer honours a drain only when
     `import` asks it to (`import_source(..., drain=True)`), so the re-map inside `recompute`, `derive` and
     `verify --level rederive` never drains part-way (pre-round review PR-6): before, a drain sent to one of those
     truncated NEW, which was then reported as failures.

### N.1.11 Network, credentials and consent

1. **No implicit network.** Network use happens only in:
   - `import --fetch` and `fetch`;
   - `verify --against-pins`, when the pinned tree listing is not cached;
   - `backends build` (package download);
   - `run` (model endpoints, from the T2 worker).

   `fetch`, `verify --against-pins` without a cached listing, and `backends build` require `--allow-network` (exit 4
   without it). `import --fetch` without `--allow-network` reads the fetch cache only (D-220): a cached pin is imported
   offline, with no socket opened and no acquisitions row, and an uncached one is refused with `raw.fetch.not_cached`
   (exit 4). `--allow-network` lets it fetch what the cache lacks. `run` contacts only the configured endpoint host. Every network action is
   logged with host and purpose, never with payloads. Large downloads (Zenodo archives) happen only with the user's
   consent (U-07; Addendum B-2).
2. **Credentials** (A4; R-51; G.9.2).
   - Only the live CLI entry, `run` and `backends build`, reads `.env`: the file named by `--env-file`, or else
     `.env` at the repository root (M.4), never `./.env` from the current directory. It is read with python-dotenv
     (`live` extra; `dotenv_values()` only) into a private mapping. `os.environ` is not mutated.
   - **`run --env-stdin`** (D-395) replaces the file for a caller that keeps keys in a keychain (the GUI). Before any
     other step, `run` reads one strict JSON object of strings from stdin, at most 64 KiB. It accepts only names that
     `endpoints.toml` declares (plus `REASONING_EFFORT`), and each value is registered for redaction as soon as it is
     read. It is exclusive with `--env-file` and refused with `--llm-script`, and it disables the default `.env` read.
     A refusal names the variable, never the value. The mapping then follows the path below.
   - **The default key source (D-702 as amended 2026-10-22, user rule).** The OS keychain is the source of truth for
     keys. With none of `--keychain`, `--env-file` or `--env-stdin`, `run` takes the selected endpoint's key variable
     from the keychain (through the keychain helper process). If the keychain is unavailable or doesn't hold the key,
     it falls back to the root `.env`. The other variables (model id, base URL, `REASONING_EFFORT`) still come from
     `.env` when one exists. A worktree has no `.env`, so the keychain is what makes a real run work there.
   - Each explicit option names one source only: `--keychain` reads the keychain, `--env-file` reads that file, and
     `--env-stdin` reads stdin. A missing key names the variable and where it was looked for (exit 3), never a value.
   - `AGENTPROV_NO_KEYCHAIN=1` turns the keychain off for a process and its children (CI, headless hosts, the test
     suite); the default lookup then reads `.env` only.
   - Only variables named by the selected endpoint entry are read, and only they are passed to T2. T1 workers never
     receive any.
   - Base URLs MUST be https, except loopback, and their host MUST match `agentprov_capture/endpoints.toml` unless
     `--allow-custom-endpoint` is given, which is recorded in the manifest (exit 4 otherwise; R-39).
   - Values never reach arguments, summaries, logs, capture logs, AER or manifests (L.2.2). Before `put_stream`, T0
     runs the literal-value scan over **every** staged file, using the values it read from `.env`; a hit quarantines
     the session (`capture.quarantined`; R-51; G.6.4). A sentinel-secret test enforces all of this (SEC-25).
   - `fetch` reads gated-source credentials from the environment or an interactive prompt. It never accepts a gate,
     licence or terms on the user's behalf (H.4.3). A token is attached only to the host the profile declares, and
     dropped on any redirect to another host (R-43; G.7.5).
3. **Consent for paid runs (D5, D.11).** Before the first model call, `run` prints the following. The first model call
   is the preflight probe (D.10.9), so consent comes before the probe and covers it; `--preflight-only` with a real
   model asks for consent to the probe alone.
   - the preflight probe call, and the number of cells to execute and already complete;
   - endpoint host, model id and key *variable name*;
   - the LLM element (`native` or `gateway_compat`), and names the instrumentation the session will declare (listed per
     session in the capture log; D-543: the items are computed in the worker per session, so the parent cannot list
     them before a cell runs);
   - a statement that calls may be billed.

   - **Interactive:** it asks `Continue? [y/N]`.
   - **Non-interactive:** it requires `--i-consent-to-api-costs` (D.11.6); otherwise exit 4.
   - **No confirmation needed:** `--dry-run` and `--llm-script` (no network).
   - **Containment of real-model runs (AD-13(b); G.4.10; AD-SW13).** A run that contacts a real provider requires
     `--containment {sandbox-exec,dedicated-user,vm}`; without it, `run` refuses (exit 4).
     - `sandbox-exec` wraps the worker in the `sandbox-exec` profile and requires the passed feasibility probe
       recorded by `backends build` (exit 4 otherwise). It is recorded as `producer.sandbox = {kind: "sandbox_exec",
       declared_by: "probe", profile_sha256}` (HL H.2.7).
     - `dedicated-user` and `vm` are operator declarations that the run executes as a dedicated user account or
       inside a VM, following the documented procedure. They are recorded as `producer.sandbox = {kind, declared_by:
       "operator"}` (`kind` `dedicated_user` or `vm`; HL H.2.7). AgentPROV does not verify them.
     - Scripted runs (`--llm-script`) need no containment, use the G.6.3 controls only (AD-13(a)) and record
       `producer.sandbox = null`.
4. **T2 worker environment** (AD-13; G.6.3). The parent execs `<env>/bin/python -I -B -m agentprov_backend.worker`
   with cwd = `$AGENTPROV_HOME/staging/<session>/` and an explicit allowlist: `PATH`, `HOME` =
   `$AGENTPROV_HOME/t2home/<session>` (never the real home), `LANG`, `TZ`, `NLTK_DATA`, the selected endpoint's key
   variables, and `HUGGING_FACE_HUB_TOKEN` only when a weight-downloading filter defence is configured.
   `AUTODOJO_CACHE` and `AUTODOJO_VARIANT` are set by the parent from `attack_params`. In tests,
   `AGENTPROV_BLOCK_NETWORK` is also passed. No `UV_*` variable passes, and no `uv` process runs at live run time
   (AD-01(c)).

### N.1.12 Logging

1. **Libraries.** Library modules use `logging.getLogger(__name__)` and never configure handlers. `print` is banned
   outside `cli` (ruff T20). `cli.common.configure_logging(level, fmt, file)` installs one stderr handler, plus the
   optional file handler.
2. **Text format.** `LEVEL logger: message [key=value …]`. The context keys are `ex`, `cell`, `source_key`, `stage`
   and `code`.
3. **JSON format.** One JCS object per line: `{"ts": "<UTC ISO-8601 Z>", "level", "logger", "msg", …context}`.
4. **At INFO** the log records:
   - start (command, versions, normalised options);
   - progress, at most every 10 s or every 500 units;
   - every refusal, failure and notice, at WARNING or ERROR with its register code;
   - the end-of-run counters.
5. **Never logged:**
   - secret values;
   - prompt, tool-output or payload content at INFO or above.

   `--log-content` permits escaped DEBUG excerpts capped at 200 characters. Logs are shared routinely, and corpora
   carry prompt-injection payloads by design [audit/corpus.md §5(6)].
6. **Redaction (defence in depth).** A filter replaces any loaded credential value with `«redacted»`.
7. **Personal paths** (R-51; G.9.6). On non-content surfaces (log lines, tracebacks, summaries, register details,
   `local` origins) the user's home path is written `<home>` and the host name `<host>`.

### N.1.14 Live feedback (DECISIONS D-8)

Every long-running command reports how it is going on stderr: `run`, `import`, `derive`, `validate`, `recompute`,
`verify`, `package`, `fetch`, `render` and `stats`. Feedback is a separate channel from logging (N.1.12). `-v` and `-q` set the log
level, and `--progress` sets how much the user sees while the work runs.

1. **Levels.** Each level includes everything in the levels above it.

   | Level | Shows |
   |---|---|
   | `off` | nothing but errors; the exit code and the `--json` summary are unaffected |
   | `summary` | a start banner (command, source or backend, plan, versions, worker count and isolation grade) and the end-of-run summary table (counts by status and `unit`, issue codes, wall time) |
   | `status` | a live status line: units or cells done and total, percentage, rate, ETA, elapsed time, the current unit (cell id, or the execution id and source key), and counters for sealed, sealed with issues, failed and refused units |
   | `steps` | one line per completed unit (status, duration, issue codes). For a live run it also prints one line per execution step: pass start and end, each model call (endpoint id, model id, latency, recorded token counts, retries), each tool call (tool name, status, duration), defence decisions and judgement verdicts. For imports and derivation it prints one line per stage per unit (read, map, seal, SEM, PROV, validate) |
   | `trace` | capture and pipeline internals: event sequence numbers, the hash-chain head (first 8 hex digits), bytes and blobs written, redaction counts, worker pid, peak RSS against its cap, per-stage timings and feedback-queue drops |

2. **Formats.** `tty` keeps one status line redrawn in place, at most 10 times a second, and prints step lines above
   it. `plain` is append-only: at the `status` level it prints a status line at most every 10 s or every 500 units
   (N.1.12(4)), and step lines as they arrive. `jsonl` writes one `agentprov-progress/0.2` object per event
   (`{"v", "ts", "seq", "run", "level", "event", ...metadata}`), for dashboards and CI. `auto` picks `tty` when stderr is a
   terminal and `TERM` is not `dumb`; otherwise it picks `plain`.
   **`--progress-file`** receives the same events as JSON lines, at the `--progress` level but never below `status`.
   A job manager tails the file while stderr is a log at `summary` (the non-interactive default) or `off`. So the
   file has every unit event, and it is written even at `off`. Every command honours it. Commands without live
   feedback on stderr (`info`, `inspect`, `purge`, `backends`) write a `start` and an `end` line, and `backends build`
   also writes one unit per build stage. `fetch` reports one unit per recipe. `package` reports one unit per seal
   stage (`withhold`, `executions`, `manifest`, `write`, `checksums`, `chain`, `swap`), and `verify` reports its level
   as one unit.
   **`agentprov-progress/0.2`** (D-393; schema and reader algorithm in `docs/reports/gui/design.md` §5) is a superset
   of 0.1, and the 0.1 events keep their shape. Readers ignore unknown events and fields.
   - **Every line** carries the run id (a UUIDv7 per process) and a `seq`. The `seq` is assigned when the event is
     queued, so a gap means the D-8 queue dropped a line.
   - **`run` header.** Each file segment starts with one (seq 0 for the process's first), carrying pid, command,
     mode, dry run, jobs, the corpus root, the summary path, the software version and `segment`.
   - **`stage` events** mark the begin and end of a corpus-level stage. `package` seal stages, `verify` and
     `backends build` stages emit them, alongside their unit events.
   - **`heartbeat`** is an absolute snapshot written every `--progress-interval` seconds, at each stage end and before
     `end`. It holds units done and total, per-stage state, status counts, the top ten issue codes, workers (configured,
     alive, pids), the pending queue and the drop count. A reader that joins late recovers from the last one.
   - **`worker`, `session` and `control`** are new kinds, and `end` gains `outcome` and `summary`.
   - **The file is appended**, never truncated, so a resumed job extends its history. Past `--progress-max-bytes` it
     is renamed to `PATH.1`, replacing an older one, and the new file starts with a `run` line (next `segment`) and a
     heartbeat.
   - **Still to land:** the import stage and `unit_kind` events, the T1 pool's `worker` events, live `session`
     events and per-level `verify` counts. Their callers belong to other sessions (D-525).
3. **Content.** Feedback carries metadata, never content, by default. Every string that originates in a run or in
   imported data (tool names, model ids, task ids, issue details) is printed through `escape_untrusted`.
   `--show-content` adds excerpts of message and tool content at `steps` and `trace`, rendered through
   `quote_untrusted` and truncated to `--content-chars`. Secret values never appear (N.1.12(5–6)).
4. **Feedback never slows the capture.** These guarantees are binding and tested:
   - **F1, no effect on evidence.** Capture logs, raw objects, AER, SEM, PROV and every corpus file are
     byte-identical at every feedback level and format. Feedback state never enters the corpus. Drop counts go to the
     summary and the `jsonl` stream only.
   - **F2, no back-pressure.** In the backend worker, the capture thread only enqueues a small metadata record (O(1))
     on a bounded queue (4,096 events). A sender thread serialises and writes it. When the queue is full, the
     enqueue drops the event and counts it. Protocol replies (`hello_ok`, `cell_done`, `fatal`) never share the
     droppable queue. In the parent, a dedicated reader thread drains the worker's stdout continuously, so the pipe
     never fills, and rendering runs on its own thread at its throttled rate. The T1 pool reports per-job progress
     the same way. A stalled terminal or a stalled `--progress-file` can delay only the display.
   - **F3, bounded overhead.** At `trace`, the capture-side cost stays within a reported budget against `off`. A
     `slow`-marked benchmark on a scripted cell measures it and reports the result (not a hard gate).
   - **F4, determinism.** No pipeline decision reads the feedback level.
5. **Protocol.** The backend protocol `agentprov-backend/0.1` (D.11.3) gains the droppable W → P op `step`, carrying
   `req`, `seq`, `kind` and the metadata of item 1 for that kind. The existing `progress` op is kept. Both ops are
   metadata only and never evidence (D.11.3: evidence never travels over the pipe).
6. **Implementation.** `agentprov.cli.feedback` holds the levels, the renderers, the throttling and the `jsonl`
   writer. Library code reports through a small `Progress` sink interface, with a no-op default, and never prints
   (N.1.12(1)). The worker-side emitter lives in `agentprov_backend` (phase 8). The core renderer and the
   import/derive/validate hooks arrive with the CLI skeleton (phase 3) and with each command.

### N.1.13 Untrusted content on the terminal

**Principle.** Artefact content is data, never instructions (D3).

**Display helpers** (`agentprov.ingest.quote`; A4; G.8.2; RESOLUTIONS §3.7 "content display"). [R-42]

- `escape_untrusted` applies to every data-derived label that reaches stdout or stderr (model ids, tool names, facet
  values, task ids, exception arguments): Cc/Cf/Cs/Zl/Zp characters, including C0/C1 controls, `DEL`, `ESC`, bidi
  overrides, zero-width and tag characters, are written as unambiguous `<U+XXXX>` escapes, and the text is truncated
  (`--max-chars`, default 500 per field).
- `quote_untrusted` applies to content (messages, tool outputs, payloads, raw excerpts). It escapes as above and
  fences the text with its locator and sha256, so that a reader, human or agent, sees where it came from.
- Content is shown only by `inspect … --show-content` (N.2.8) and `render --show-content` (N.2.13). By default
  every command prints locators, hashes, sizes and labels from trusted grammars.
- `inspect` prints a one-line banner saying the output contains untrusted third-party content.

**Other outputs.** Markdown and HTML generators escape the same way (K.12.6(c), (e); D.3.5 rule 3). No command
executes artefact content, renders it as markup, or forwards it to a model.

---

## N.2 Commands

Fifteen commands, plus the aliases `convert` (`import`) and `sources` (`info`): the 13 commands of RESOLUTIONS §3.7
and the two that Addendum B keeps, `stats` and `render` (AD-10 as ruled). The command list here MUST equal that set
(RESOLUTIONS §5 consistency assertion, amended by Addendum B). [R-19, R-34, R-51] **Application commands** added by
later decisions are listed apart in N.2.17 and never change the fifteen.

| Command | Purpose |
|---|---|
| `run` | live capture through a backend worker |
| `import`, `fetch` | ingestion |
| `derive`, `recompute` | derivation |
| `validate`, `verify` | checks |
| `inspect`, `info` | inspection |
| `backends` | backend environments |
| `package` | sealing and deposit drafts |
| `stats`, `render` | consumers (AD-10 as ruled) |
| `migrate` | baseline migration |
| `purge` | removal of a leaked object from a working store (R-51) |

Options common to many commands: `--corpus DIR` (N.1.5), `--dry-run` (N.1.6), `--limit/--select/--sample` (N.1.7),
`--jobs` (N.1.10), `--format` (output format of `info`, `stats`; N.2.9, N.2.12) and `--in-process` (debugging only:
run `expand` and `map` jobs in the CLI process, recorded as `producer.isolation = "in-process"`; refused with
`--release`, exit 4; A3; G.4.9).

**Deferred commands and flags** (AD-10; `docs/roadmap.md`): the corpus diff and its SemVer check, outcome replay,
collection building and verification, the ML export, flattened core output, the collection context encoding, and
`info --card`. There is no `--allow-unpatched-interpreter` (AD-16 as ruled).

### N.2.1 `run` — execute a live backend and capture raw evidence (D5; A1; AD-01)

```
agentprov run SOURCE --corpus DIR (--campaign NAME | --corpus-id ID)
      (--plan PLAN.toml | --spec SPEC.toml | CELL-OPTIONS)
      (--model SHORTHAND | --endpoint NAME --model-id ID | --llm-script SCRIPT.json)
      [--llm-element {native,gateway_compat}] [--model-display-name NAME] [--temperature T]
      [--reasoning-effort LEVEL] [--max-tokens N|harness-default] [--repeats N] [--max-attempts N] [--retry-inconsistent]
      [--allow-mixed-config] [--env-file PATH | --env-stdin] [--allow-custom-endpoint] [--i-consent-to-api-costs]
      [--containment {sandbox-exec,dedicated-user,vm}] [--limit N] [--jobs N] [--start-stagger SECONDS] [--dry-run]
      [--autodojo-cache PATH --autodojo-variant K]
CELL-OPTIONS: --suite S[,S…] [--benchmark-version V] [--user-tasks SPEC] [--attack A[,A…]]
              [--injection-tasks SPEC] [--benign {include,exclude,only}] [--defence NAME]
```

`SOURCE` must have a live part in the registry: `agentdojo`, `autodojo` or `agentdyn`. All three are `partial`
(D-720): real-model runs are admitted for the subset of item 3a, and each caveat records the approved real-model
pilot of that part or, until it has one, "fake-client tested in v0.1; no real-model run" (D.3.2 rule 3; D-722;
R-25). The registry renders them `supported` only once their full gates pass (I.0.2). Anything else goes through the status gate (N.3) and exits 5. The `live` extra is required (exit 3
with the hint `uv sync --extra live`).

| Option | Default | Meaning |
|---|---|---|
| `--campaign NAME` | — | corpus id `<source>-live-<NAME>` (H.1.1(2), H.4.2). Required unless `--corpus-id` is given |
| `--plan PLAN.toml` | — | committed run plan (format owned by D; Q10); excludes CELL-OPTIONS |
| `--spec SPEC.toml` | — | corpus spec with `[live]` (H.1.6); supplies corpus id, version and plan |
| `--suite` | required without plan | validated by the worker against the loaded benchmark |
| `--benchmark-version` | `v1.2.2` | AgentDojo's CLI default [sources/agentdojo.md §1.2] |
| `--user-tasks SPEC` | `all` | `all`, comma ids (`user_task_3`) or index ranges `0-9,12` over the sorted task list. Replaces `--n/--task_start` (`generate.py:847-850`) |
| `--attack A[,A…]` | none (benign only) | e.g. `important_instructions`, `direct`, `injecagent`, `autodojo` |
| `--injection-tasks SPEC` | `all` | as `--user-tasks` |
| `--benign` | `include` | benign cells as their own cells, never a by-product of an attack batch [audit/capture.md §4.6] |
| `--defence NAME` (alias `--defense`) | `none` | a registry id (`backends/shared/src/agentprov_backend/defences.toml`, D.10.11) the backend builds and the live profile's `defences` allows; checked by T0 before spawn, from the flag and from `[plan] defence` alike, every refusal exit 5 (D-679). `agentdojo-live` v3 allows the first set (D-671); its v1 and v2 and `autodojo-live` allow none. Defences that replace pipeline components (`progent`, `drift`, `camel`, `camel_nopolicy`) are refused with a typed refusal, exit 5 [sources/autodojo.md §7; D.11] |
| `--defence-endpoint NAME` | — | the endpoint (`endpoints.toml` shorthand) a defence calls for its own model or embedding calls (D-675; MELON); only its key enters T2; required for a real run of such a defence, unused by a scripted one |
| `--model SHORTHAND` | — | `agentprov_capture/endpoints.toml` shorthands: `deepseek`, `openai`, `openrouter`, `gemini`, `llama`, `qwen`, `glm`, `ollama` (baseline set, `runtime.py:494-503`), plus `omlx` (N.2.1a) and the local servers `lmstudio`, `mlx_lm`, `llamacpp`, `vllm` (D-690). The model id comes from `--model-id` or from the shorthand's `*_MODEL` variable; if neither is set, exit 3 (for a local endpoint the message names the served ids, and a terminal offers a numbered pick, D-691). There are no default model ids (M.4; Q5 closed) |
| `--endpoint NAME --model-id ID` | — | explicit endpoint (`deepseek`, `openai`, `openrouter`, `anthropic`, `local`, or any local shorthand of D-690) and model id → `AgentConfig.{endpoint_host, api_key_env, model_requested}`; an endpoint whose registry `api` is `anthropic_messages` sets `provider: anthropic` (D-656) |
| `--base-url URL` | `.env` `*_BASE_URL`, then the setting `endpoints.<name>.base_url` (D-699), then the registry default | a local endpoint's base URL: loopback, or a literal private address with `--allow-lan-endpoint` (D-691, D-698); recorded |
| `--allow-lan-endpoint` | off | a local endpoint on a private LAN address (10/8, 172.16/12, 192.168/16, 100.64/10, fc00::/7; literal IPs only), per run; keyless; prompts and replies leave the machine over plain http; recorded (`network: "lan"`). Under `sandbox-exec` it needs the D-664 egress proxy's HTTP forward mode (D-698) |
| `--accept-served-model ID` | none | repeatable: a served model id that may differ from the requested one without the A12 canary stop (D-694); recorded as `live.accepted_served_models` |
| `--no-hash-weights` | off | a local model's weight files are recorded by size only (`weights_hashed: false`; D-692) |
| `--preflight-only` | — | run the D.10.9 preflight probes for the selected endpoint and model, print the result and exit |
| `--canary N` | `10` | run the first N cells as a canary and stop the campaign after them if a D.10.9 canary condition appears (exit 1); `0` disables |
| `--temperature-policy {as-benchmark,inject}` | required when a configured parameter would not be transmitted | `as-benchmark` keeps stock behaviour (recorded); `inject` sets the value at the transport, declared `request_modifying` (D.10.9 A3) |
| `--allow-text-tool-calls` | off | run an endpoint whose preflight returned text-encoded tool calls (recorded; D.10.9 A4) |
| `--llm-script PATH` | — | the worker installs `agentprov_backend.testing.ScriptedTransport`: no network, no keys. The session is declared `test_only` instrumentation; the corpus is marked `synthetic: true`, cannot enter a release corpus, and `package --deposit` refuses it |
| `--llm-element` | `native` (both backends; AD-09) | `native` keeps the benchmark's own LLM element and records at the transport level (recording httpx transport plus LLM-span brackets that record `input_at` and `n_messages`, R-16). `gateway_compat` (the `_CompatLLM` port) is an opt-in for v2.3 comparability, declared as `request_modifying`/`harness_policy` instrumentation; NC-LIVE-01 then applies (R-25) |
| `--model-display-name NAME` | — | explicit `attack_params.model_display_name` for attacks that name the model, declared as `attack_parameter` instrumentation. Required when the benchmark's table lacks the model, because stock AgentDojo raises `ValueError` [audit/capture.md §3, §4.5]. Replaces the `MODEL_NAMES` mutation (`generate.py:299-302`) |
| `--temperature T` | unset (provider default) | configured value. The transmitted value is recorded; AgentDojo 0.1.35 drops a falsy temperature (`README.md:336-338`) |
| `--reasoning-effort LEVEL` | `$REASONING_EFFORT` from `.env`, else provider default | as the baseline (`runtime.py:57-70`); configured and transmitted values are both recorded. Refused for Anthropic endpoints (the element sends no effort; `$REASONING_EFFORT` is then not used, with a notice; D-656) |
| `--max-tokens N\|harness-default` | none: **required** for Anthropic endpoints, refused for the others | D-656 (user decision 2026-10-22): the reply cap, stated (`max_tokens_mode: explicit`) or the harness default 16000 (`harness_default`, declared `agentdojo.anthropic_max_tokens@1`); with neither, the run is refused naming both. AgentDojo's own 1024 is never used silently |
| `--repeats N` | 1 | independent repeats per cell (`repeat_index`; logical key H.7.4) |
| `--max-attempts N` | 3 | N.1.8(4) |
| `--env-file PATH` | the key from the OS keychain, else `.env` at the repository root (with `--env-file`: that file only) | M.4; N.1.11(2); D-702 as amended |
| `--env-stdin` | off: one JSON object of endpoint variables on stdin instead of `.env` | N.1.11(2); D-395 |
| `--keychain` | off: the selected endpoint's key variable from the OS keychain (`agentprov keys`) instead of `.env`; exclusive with `--env-file` and `--env-stdin`; a missing key is exit 3 naming the variable | D-702 |
| `--allow-custom-endpoint` | off | permits a base-URL host outside `endpoints.toml`; recorded in the manifest (R-39) |
| `--containment {sandbox-exec,dedicated-user,vm}` | none; required for real-model runs | the AD-13(b) containment of the worker (G.4.10; AD-SW13). `sandbox-exec` needs the passed probe recorded by `backends build`; `dedicated-user` and `vm` are operator declarations. Recorded as `producer.sandbox` (HL H.2.7); N.1.11(3) |
| `--autodojo-cache PATH`, `--autodojo-variant K` | required with `--attack autodojo` | become `attack_params`. The cache file goes into the raw store first, as a `supporting` artefact with its sha256, because the fork's logger records neither (D.11.3 rule 5) [sources/autodojo.md §7] |
| `--allow-network` | off | lets T0 fetch the pinned AutoDojo commit into the fetch cache when it is not there, to verify `--autodojo-cache` (D.11.3 rule 5); nothing else in `run` uses the network for T0 (D.11.9 item 8) |

**Behaviour.**

1. **Pre-flight** (T0).
   - Run the status gate and load the plan.
   - Read `.env` (N.1.11(2)); resolve the endpoint, its https base URL and host, and credential presence (exit 3 if
     missing).
   - Locate the built environment `$AGENTPROV_HOME/envs/<backend>-<commit8>/` and its `AGENTPROV_ENV.json` (exit 3,
     with the hint `agentprov backends build <backend>`).
   - Compute the identity digests (commit, `lock_sha256`, RECORD, guarded sources) and compare them with the
     profile (M.1.7 rule 4).
   - For a real-model run, check `--containment` and, for `sandbox-exec`, the recorded probe (AD-13(b); N.1.11(3)).
2. **Spawn and plan.** Exec `<env>/bin/python -I -B -m agentprov_backend.worker` (protocol `agentprov-backend/0.1`)
   with the T2 environment of N.1.11(4). The worker answers `hello` with `hello_ok`; the parent cross-checks its
   identity (exit 3 on mismatch). The worker expands the cells. The parent computes `config_digest`, applies G1–G6
   and the resume rules, prints the plan and obtains consent (N.1.11(3)).
3. **Per cell:**
   - the worker writes `capture/0.1` plus the native TraceLogger JSON into its staging directory (C's capture and
     blob directory names apply only there, never in a corpus; RESOLUTIONS §3.6);
   - the worker ends the session with `session.end` (`complete`, `incomplete`, `errored` or `aborted`); if it dies,
     the parent appends it (`appended_by: "parent"`);
   - T0 ingests the staging directory exactly like an `--input` tree (`ingest.paths`; no-follow, `S_ISREG`,
     `st_nlink == 1`, never `--allow-hardlinks`); reported paths are labels resolved only under the session
     directory; unreported files are ignored and reported (G.6.3);
   - T0 re-hashes every reported file and runs the literal-value scan before `put_stream` (N.1.11(2));
   - the capture hash chain is verified in T1; `corpus.derive` maps with `agentdojo.capture` (D.10.4), derives SEM
     and PROV, validates and writes — the same machinery as an import (D0; A1);
   - the AER seal's accounting verdict decides re-attempts (N.1.8(4));
   - the index row is written last.
4. **Declarations.** Every harness deviation is declared as instrumentation in the execution header (D5; D.10.7;
   `{id, kind, recorded, …}`, RESOLUTIONS §3.3). Resample and retry counts are recorded per execution (AD-09).

**Outputs.** `<DIR>.partial/` (H.1.2). Counters: `cells_planned`, `cells_done_before`, `attempted`, `conclusive`,
`inconsistent`, `inconclusive`, `derived`, `failed`.

**Exit codes.**

| Code | When |
|---|---|
| 0 | every attempted cell was conclusive and derived |
| 1 | any inconclusive or inconsistent cell, or any derivation failure (resumable) |
| 2–5, 130 | as N.1.3 |

### N.2.1a Local models and host presets (DECISIONS D-10)

1. **Local endpoints.** `agentprov_capture/endpoints.toml` carries six loopback, OpenAI-compatible entries (two
   until D-690; each names its `server` kind). All are http on `127.0.0.1` (allowed, G.9.2) and need no key: `ollama`,
   `omlx`, `lmstudio` (`:1234`), `mlx_lm` (`:8080`), `llamacpp` (`:8080`), `vllm` (`:8000`). **Amended (D-827):** a
   local entry may name an optional `api_key_env`; `omlx` names `OMLX_API_KEY`, because oMLX can be set up with an
   API key. When the key is set (the keychain first, then `.env`, D-702; or the one source `--keychain`, `--env-file`
   or `--env-stdin` names), it is sent as `Authorization: Bearer` to the loopback server: by `agentprov models`, the
   preflight, the per-cell re-observation and the worker. When it is not set, nothing is sent and the agent's
   `api_key_env` is null, so the configuration digest is that of a keyless run. A key is never sent to a LAN address
   (`cli.refused.lan_key` / `run.local.lan_key`, exit 4). A listing refused with HTTP 401 or 403 is
   `run.local.unauthorized` (exit 3), naming the variable, never a value. The two that were first:
   - `ollama`: base `http://127.0.0.1:11434/v1`, the baseline's set.
   - `omlx`: base `http://127.0.0.1:8000/v1`. This is oMLX, an MLX inference server for Apple Silicon with continuous
     batching and a tiered KV cache. Its server limit `--max-concurrent-requests` defaults to 8. The model id is the
     oMLX model directory name or alias, given with `--model-id`.

   `--model ollama` and `--model omlx` select them; the generic `--endpoint local` with `LOCAL_LLM_BASE_URL` remains.
   Before the first cell, a **server preflight** runs: `GET <base>/models` on loopback only, through the stdlib with a
   5 s timeout. It checks that the server is up and that `--model-id` is listed, and records the listing digest. If it
   fails, the run exits 3. **As built (D-691..D-693):** the preflight is `agentprov.cli.live.localmodels` (the same code
   as `agentprov models`, N.2.18): it also fingerprints the server kind (the wrong kind for the shorthand, as on the
   shared default ports 8000 and 8080, exits 4) and observes the model's identity record, which becomes
   `agent.local_model` (plan and config digests) and is re-observed before every cell (D.10.9 A14).
2. **Presets.** `--preset NAME` loads a named preset from package data (`agentprov/presets/presets.toml`). Presets are
   data, read through `importlib.resources`. `--m5ultra` is shorthand for `--preset m5ultra`, the only preset in v0.1:
   - **Host:** Mac Studio M5 Ultra, 80-core GPU, 256 GB unified memory, about 1.2 TB/s.
   - **Endpoint:** `omlx`.
   - **Start stagger:** 1 s per worker. The first request then warms oMLX's prefix cache with the shared system prompt
     and tool schema before the others arrive.
   - **Request timeout:** 900 s.

   The preset states the host it expects (D-7 `HostProfile`: `darwin`, `arm64`, physical memory ≥ 240 GiB). On a
   mismatch the run warns and records the mismatch; it is not refused. Every value the preset sets is recorded in the
   `corpus.json` producer block as `preset{name, version, resolved{…}}`. An explicit flag overrides the preset value.
   **As built (D-822, D-823):**
   - **Recording.** In the working `corpus.json`, the record's non-integer values are decimal strings (`"0.75"`),
     because corpus-layer JSON holds no float (H.1.4(3)). Its place in the sealed schema comes with live sealing
     (D-724).
   - **Which presets run live.** Only a preset with `calibrated = true` runs live; `m5ultra` v1 was not calibrated,
     so it ran in `--dry-run` and in the `--tune-jobs` sweep only. v2 (2026-10-28) is calibrated. `calibrated` needs `calibration` (the committed
     report) and a `basis` (`measured` or `provisional`) on every `compute_caps` row.
   - **What a preset run sets.** Its `jobs` (unless `--jobs`), its stagger (unless `--start-stagger`) and its request
     timeout, as `agent.params.timeout_s`, which the worker gives the SDK client; the timeout therefore enters the
     configuration digest.
   - **LLM element.** A preset run uses `--llm-element gateway_compat` unless one is given. `native` is refused
     (exit 2), because stock `OpenAILLM` ignores the timeout.
   - **Declared subset (D-829).** The declared subset of `agentdojo · live` (D-720) admits `gateway_compat` for a local
     model server, by the user's decision; the pilot ran `native` only. The registry caveat that `run` prints keeps
     "native only" until a class-1 change after the round-1 seal.
3. **Model-aware concurrency.** For a local endpoint, unless `--jobs` is given, `run` computes
   `jobs = max(1, min(J_compute, J_memory, J_server))` with a pure function
   (`agentprov.presets.local_concurrency`). Its inputs are model facts, from `--model-dir` or from manual flags:
   - `J_compute` comes from the active parameter count `A` (billions) of the preset's `compute_caps` table. For
     `m5ultra`: `A ≤ 15` gives 8, `15 < A ≤ 40` gives 6, and `A > 40` gives 4. AgentDojo traces are prefill-heavy
     (several thousand prompt tokens per call, short replies). Prefill cost grows with active parameters, so the
     benefit of batching falls with them.
   - `J_memory = floor((M_budget − W − R) / KV_trace)`:
     - `M_budget` is the preset's GPU working-set budget, 0.75 × physical memory;
     - `W` is the weight bytes;
     - `R` is a reserve of 16 GiB plus 0.5 GiB per backend worker;
     - `KV_trace = 2 × layers × kv_heads × head_dim × context_tokens × kv_bytes`. Its defaults are
       `context_tokens = 32768` and `kv_bytes = 2`.
     If `W + R ≥ M_budget`, the run is a usage error (exit 2): the model does not fit.
   - `J_server` is the server's concurrent-request limit: `--server-max-concurrency`, default 8 for `omlx`. Raising
     `--jobs` above it only queues requests at the server.
   - **Model facts.** `--model-dir PATH` reads the model's `config.json` through `agentprov.ingest` (bounded, strict;
     it is untrusted input). It takes `num_hidden_layers`, `num_key_value_heads`, `head_dim` (else
     `hidden_size / num_attention_heads`) and any MoE expert counts, and it sums the `*.safetensors` sizes for `W`
     (**D-828:** with none, the `*.gguf` shards, top-level or in oMLX's `split/` subfolder). The manual flags
     `--model-size-gb`, `--active-params-b`, `--context-tokens` and `--kv-gb-per-trace` override or replace these. If
     neither source gives `A`, `J_compute` falls back to the most conservative row. If `KV_trace` is unknown, it
     defaults to 4 GiB.
   - **Settings (D-828).** The same facts may be stored per local model as `agentprov settings` keys
     `local_models.<endpoint>.<model id>.{model_dir, model_size_gb, active_params_b, context_tokens, kv_gb_per_trace}`
     (GUI: Settings › Local Models), looked up when `--model-id` is given. Precedence: **flag > setting > the model's
     folder > the preset**. The setting's folder is used where `--model-dir` would be (the plan and the identity record
     of N.2.18), and a stored folder that is no longer a directory is a usage error naming the key (exit 2).
   - `--dry-run` prints the resolved preset, the three terms, the binding one and the inputs with their sources
     (`model_dir`, `flag`, `settings`, `preset`, `default`).
4. **Evidence and caveats.** The table values are provisional:
   - oMLX's published benchmark on an M3 Ultra (Qwen3.5-122B-A10B, 4-bit) gives aggregate generation throughput of
     56.6, 92.1, 135.1 and 190.2 tok/s at 1, 2, 4 and 8 concurrent requests;
   - SiliconBench (arXiv 2609.19169) found that oMLX scales less on agent prompts of about 4.3K tokens than on chat
     prompts;
   - MacStories measured 108 tok/s from a single stream on an M5 Ultra.

   They are re-calibrated on the target machine with the concurrency sweep `run --tune-jobs 1,2,4,6,8,12` (phase 8).
   The sweep runs a fixed, small cell sample per value and recommends the smallest N reaching ≥ 90 % of peak traces
   per hour with no request timeouts. The calibrated table is committed with its measurements.

   **As built (D-820, D-821; `agentprov.cli.live.tune`).**
   - **Command and refusals.** `run SOURCE --m5ultra --tune-jobs N[,N…] [--tune-out DIR]` takes 1–12 distinct values
     ≥ 1, within the host maximum, in the order given. It needs a preset, and real runs need a `local` endpoint class;
     `--llm-script` makes it a `test_only` sweep. `--jobs`, `--corpus`, `--campaign`, `--corpus-id`, `--limit`,
     `--repeats`, `--spec`, `--preflight-only`, `--plan-json`, `--allow-mixed-config` and a defence are refused
     (exit 2).
   - **The sample.** With no plan or cell option it is the four AgentDojo suites × user tasks 0–2 × {benign,
     `important_instructions`/`injection_task_0`}: 24 cells.
   - **Before the arms.** One consent and one preflight probe cover the sweep. A warm-up cell at `jobs = 1` runs into
     `<out>/warmup-<stamp>/`, unmeasured.
   - **Each arm.** Every arm runs the same cells into its own working corpus `<out>/jobs-<N>/`, with
     `max_attempts = 2` and the preset's stagger.
     - **Skipped arms:** an arm above `J_memory` is skipped (`memory`). After an arm with a request timeout or a failed
       cell, and after a canary, setup or cap stop, the higher arms are skipped.
     - **Above the server limit:** an arm above `J_server` runs and is flagged.
     - **Resume:** a finished arm writes `<out>/arms/jobs-<N>.json` and is reused on a re-run with the same
       configuration digest. An unfinished arm's corpus is renamed `*.interrupted-<stamp>` (never deleted) and run
       again.
   - **Metrics.** They come from T0's clock (`wall_s`) and the stored capture logs (no prompt, reply or tool text):
     - traces per hour (conclusive cells ÷ hours) and seconds per cell (`wall_s × N ÷ conclusive`);
     - call latency p50/p90/max (`mono_ns`, `llm.request` → `llm.response`);
     - request timeouts (an `exception.type` naming a timeout, plus cells killed at `--cell-timeout`);
     - call errors, and prompt and completion tokens per second.
   - **Rule.** The peak is the highest rate of any arm that ran. The recommendation is the smallest N with at least
     0.9 × peak, no request timeout, no failed cell and every cell conclusive. Without one, the exit is 1.
   - **Report.** `<out>/tune-jobs.json` (`agentprov-tune-jobs/0.1`: software, preset, host, endpoint and server, the
     model's identity digest and facts, the sample, the run settings, the order, the warm-up, reused arms, the arms
     and the recommendation) and `<out>/tune-jobs.md`.
   - **Dry run.** `--dry-run --tune-jobs` lists the arms that would run or be skipped and a rough time.

   **Research caveat:**
   batched inference is not guaranteed batch-invariant, so the same prompt can decode differently at different
   concurrency. `jobs`, the server limit and the preset are therefore part of the recorded run conditions.

5. **Implementation resolutions (phase 3, 2026-10-08).** The code is the reference (`agentprov.presets`,
   `agentprov/presets/presets.toml`, `agentprov_capture/endpoints.toml`).
   - `R` depends on `jobs`, so the memory term is solved in closed form:
     `J_memory = floor((M_budget − W − 16 GiB) / (KV_trace + 0.5 GiB))`. The "does not fit" check uses one worker's
     reserve. If no KV slot fits, jobs is 1 with a warning.
   - An unknown weight size is a usage error (`run.model.facts_missing`, exit 2) and is never guessed.
   - `-gb` flags are decimal GB (10^9). The reserves and the 4 GiB KV fallback are GiB.
   - Active parameters are derived from `config.json` only for known gated-MLP model types. Other architectures
     (latent or hybrid attention, mixed dense and sparse layers) leave `A` unknown. KV geometry counts every layer,
     which gives an upper bound for hybrid models.
   - `--model-dir` is user configuration, not raw evidence. It follows symlinks, so Hugging Face cache layouts work:
     each resolved target must be a regular file. Weights are only `stat`-ed. `config.json` is read from its resolved
     target under the ingest byte cap, through `strict_json_loads`. `followed_symlinks` is recorded.
   - Preflight refusals of a non-loopback, non-https, query, userinfo or fragment URL exit 4 (refused). An unreachable
     server, a bad listing or an unlisted model exits 3.
   - Worked plans (256 GiB host, 192 GiB budget, 4-bit weights):
     - a 30B-A3B MoE gives 8, bound by compute and server;
     - a 70B dense model gives 4, bound by compute;
     - a 235B-A22B model gives 6, bound by compute, with memory at 8.

### N.2.1b Implementation resolutions (phase 8)

Phase 8 stream D built the parent (T0) side of live runs: `agentprov.cli.run` (orchestration), `agentprov.cli.backends`
(N.2.10), `agentprov.cli.live` (`envs`, `sandbox`, `worker`, `staging`, `quality`, `campaign`) and
`agentprov.adapters.runner.session` (`LiveSessionPipeline`). The code is the reference; tests:
`tests/integration/test_run_spawn.py` (fake backend environment, default suite), `tests/integration/test_run_live_agentdojo.py`
(real environment, `backend_agentdojo`), `tests/cli/test_run_cmd.py`, `tests/cli/test_backends_cmd.py`,
`tests/cli/test_live_units.py`; CI job `live-run`. `aer/0.1` and `capture/0.1` were not changed.

1. **Status gate.** The live part is found in the registry (`live_status` and `backend`; `BACKENDS[backend]` names the
   capture mapper and the live profile). While it is `planned`, only scripted runs (`--llm-script`) are admitted, with a
   notice: they are `test_only`, synthetic and never released, so they make no claim, and the live gates (Q.4) are such
   runs. A real-model run of a `planned` part exits 5; `not_possible` refuses both. `supported`/`partial` proceed with
   the caveat, under the endpoint-class rules of item 3a. Since D-720 the three live parts are `partial`. The `live` extra (python-dotenv) is required only where `.env` is read, i.e. for real-model runs (exit 3
   otherwise); scripted runs read no `.env`.
2. **Repository checkout.** `run`, like `backends build`, needs the checkout (M.4 root rule; exit 3 outside): the
   environment name is computed from `backends/<b>/uv.lock`.
3. **Real-model path, up to and through the gates (never exercised in tests).** The key comes from the OS keychain
   first, then from `.env` (D-702 as amended; `--keychain`, `--env-file` and `--env-stdin` each name one source).
   `.env` (`--env-file` or the root's `.env`) is read through `dotenv_values`; only the endpoint entry's `api_key_env`, `base_url_env`, `model_env` and
   `REASONING_EFFORT` are used. Missing model id or key: exit 3. The base URL passes `check_base_url` (exit 4 on a rule or
   host violation without `--allow-custom-endpoint`). `--containment` is required (exit 4); `sandbox-exec` requires the
   marker's probe `passed` **for the profile digest in force** (exit 4 otherwise) and wraps the worker argv in
   `/usr/bin/sandbox-exec -D STAGING=… -D T2HOME=… -D REPO=… -D HOME=… -D EGRESS_PORT=… -D LOOPBACK_PORT=… -p <profile>`.
   For a remote endpoint T0 first starts the egress proxy (D-664, G.4.10) for the endpoint's host and port, and gives
   the worker `AGENTPROV_EGRESS_PROXY` and `HTTPS_PROXY`; for a loopback endpoint the two ports are the endpoint's. A
   marker probed under the pre-D-664 profile no longer matches the digest in force, so the environment is rebuilt (or
   re-probed) once. The preflight probe (worker op
   `probe`, its own capture session in staging, removed afterwards, never mapped or stored) runs before consent; its
   exits are D.10.9's (unreachable 3, roles rejected 4, text-encoded tool call 4 without `--allow-text-tool-calls`, a
   configured parameter not transmitted 2 without `--temperature-policy`). The probe is repeated, up to 3 calls, only
   while its verdict is `unconfirmed` (a 2xx reply with no evidence that the system message was followed). The first
   `accepted` reply ends it; a refusal or an unreachable endpoint is final at once. Each call is charged to the caps
   (D-729). Consent: an interactive `y` on a terminal or
   a consent flag by endpoint class (item 3a; exit 4 otherwise). The key value enters only the T2 environment and the literal-value scan;
   it is registered with the display redaction. Deferred, each a typed refusal (exit 5): `--temperature-policy inject`
   (the harness does not inject parameters), `--preset`/`--m5ultra` with an uncalibrated preset outside `--dry-run`
   and `--tune-jobs` (D-823; before D-823 every preset live run), `--spec`, any `--defence` other than `none`.
3a. **Endpoint classes and API caps (D-721, D-725, D-726; `agentprov.cli.live.policy`).** A real-model run is
   `local` when its `endpoints.toml` entry has `local = true` and the resolved base URL's host is loopback; every other
   real-model run is `api` (a LAN address counts as `api` until the egress proxy forwards LAN traffic). The class is
   decided after the status gate and before consent, the preflight probe or any spawn, and is noted in the run's
   notices and recorded as `live.endpoint_class`.
   - **Consent.** `local`: interactive, `--i-consent-to-local-run` or `--i-consent-to-api-costs`. `api`: interactive or
     `--i-consent-to-api-costs`; `--i-consent-to-local-run` alone is refused (`cli.refused.consent`, exit 4).
   - **Caps.** An `api` campaign needs `--max-calls N` and `--max-cost-usd X` with `--price-in` and `--price-out` (USD
     per million tokens), else `cli.refused.api_caps` (exit 4). For an entry that is not `local` this is checked before
     `.env` is read; a `local` entry is classed again once its base URL is resolved. `--preflight-only` (one call) takes
     no caps (exit 2 if given); incomplete pricing is exit 2. Caps are optional for `local` and scripted runs and
     behave the same there.
   - **Budget.** T0 counts the corpus's billed calls (every `llm.response` with an HTTP 2xx status) and their recorded
     `usage` in each attempt's capture log, earlier invocations included, plus one call per preflight probe. A cell
     starts only if the spend plus the worst case of every in-flight cell and of the new one fits both caps. The
     worst case is 48 billed calls (3 passes × (1 + `max_iters` 15)), each at the per-call bound: input 32,000 tokens
     or the largest seen; output the transmitted `max_tokens`, else 4,096, or the largest seen. Spend is an upper
     bound: every input-side token (input, cache read and cache write) at `--price-in`; a billed reply without usage at
     the per-call bound; a parent-ended attempt one more call; an attempt without a log a whole cell. A cap that stops
     the campaign is `cap_reached` (exit 1, `live.partial`). A cell that spends more than its bound is
     `cap_bound_exceeded`, and no further cell starts. `live.caps` records the caps, the bound, `billed_calls` and
     `spend_upper_bound_usd` (decimal strings). The provider's own key or workspace limit is the backstop (U-10).
   - **Inspect cells (D-740).** The worst case of an Inspect cell is `n × E × ((M − 1) × (1 + a) + j) × (1 + K)`
     billed calls. Here `n` is `--cell-size` (default 1 under caps), `E` the epochs, `M` the message limit, `a` and
     `j` the task's judge calls per agent call and per sample, and `K` the worker's fixed retries (1). T0 computes it
     from its own plan document. A task without a recorded bound for the environment's task code
     (`task_files_sha256`), or a judge on another model than the agent, is refused (`cli.refused.api_caps`).
     Since D-741 `agentharm` · `live` is `partial`, and a real-model Inspect run also needs an OpenAI-chat endpoint
     (the worker has no other provider; `cli.refused.endpoint` before consent, the plan or any spawn).
4. **Scripted runs.** The script file is copied into each session directory as `llm-script.json` (outside `raw/`, so the
   worker never reports it and T0 does not count it as unreported); `agent = {model_requested: --model-id or
   "scripted-fake", endpoint: "scripted", transport: "scripted", script: "llm-script.json"}`; the T2 environment always
   carries `AGENTPROV_BLOCK_NETWORK=1`; the script's digest is `live.llm_script_sha256`. Preflight is skipped (no
   endpoint), except `--preflight-only --llm-script`, which runs the probe against the script.
5. **Plan.** T0 writes an `agentprov-run-plan/0.1` TOML document (from the cell options, or from `--plan` with its
   `format` checked by T0, D.10.1) with the `[agent]` table always taken from the command line, and the worker expands
   it (`plan` → `plan_ok`; `plan_refused` exits 2). `--dry-run` spawns one worker in a temporary directory outside
   `$AGENTPROV_HOME` (hello and plan only), prints the cells, `plan_sha256`, the configuration digest and the resume
   state, and writes nothing. **`--plan-json`** (D-651, with `--dry-run` only; not with a host preset or the global
   `--json`) also prints the expanded plan on stdout as one JCS document `agentprov-run-dry-plan/0.1`:
   `{plan_sha256, config_digest, backend, corpus_id, benchmark_version, repeats, max_attempts, units, settled,
   attempts_due, cells[{cell_key, suite, user_task_id, injection_task_id, attack, kind, settled}]}`. `settled` per cell
   counts its settled units by the campaign's rule, so the totals equal the `cells_planned` and `cells_done_before`
   counters; every string is escaped. The human lines are unchanged. It feeds the GUI's cost estimate (design §8.3).
   An Inspect plan (D-770) has no suite or kind: each cell row adds `task` and `samples` (its sample count), and the
   document adds `inspect: {task, epochs, message_limit, max_connections, judges{role: model}}` from the worker's
   backend configuration.
   **`--catalogue`** (D-652; only SOURCE and `--benchmark-version`, not the global `--json`) asks one offline,
   keyless worker (as for hello and plan, in a temporary directory) for what a plan can select and prints it as one
   JCS document `agentprov-backend-catalogue/0.1`: `{backend, benchmark_version, benchmark_versions[],
   suites[{name, user_tasks[], injection_tasks[], tool_definition_chars}], attacks[{name, dos, refused, needs[]}]}`
   (names, ids and counts only, rebuilt by T0 from checked members; a name outside `[A-Za-z0-9_][A-Za-z0-9_.:@+-]{0,199}` is a protocol error,
   exit 3). A worker built before the op answers `fatal`: exit 5 with "rebuild the environment". It writes nothing
   and makes no model call (summary `dry_run: true`).
6. **Configuration digest** (N.1.8(1)) = `sha256(JCS({backend, agent, identity: hello_ok.identity, backend_config}))`; the
   unit key is `(cell_key, config_digest, repeat)`. A working corpus holding sessions of another digest refuses (exit 4,
   G5) unless `--allow-mixed-config` (recorded as `live.mixed_config`, all digests in `live.config_digests`).
   Scripted and real-model sessions never share a corpus (exit 4; H.1.1(2)).
7. **Workers and directories.** `--jobs N` keeps N worker slots (threads), each one long-lived worker with its own
   `HOME=$AGENTPROV_HOME/t2home/worker-<id>` and empty working directory `$AGENTPROV_HOME/staging/worker-<id>` (both 0700;
   G.6.3's `<session>` is read as the worker session, because one worker serves many cells); every cell gets a fresh
   session directory `$AGENTPROV_HOME/staging/<session>/` (0700) passed as `run_cell.session.dir`; the session UUIDv7 is
   minted by T0 (`uuid.uuid7`) and is the execution id `ex_<session>`. Every spawn is followed by `hello` and the
   identity cross-check. Worker stderr goes to `worker.stderr.log` in the worker directory; it is scanned with every
   session and removed with the worker directory at the end (it is not evidence of one execution, so it is not stored).
   `LANG=C.UTF-8` and `TZ=UTC` are fixed values, not the user's. `--start-stagger` delays worker `i`'s first cell by
   `i × S / N`. A T2 home left non-empty is kept and reported.
8. **Timeouts and dead workers.** `--cell-timeout SECONDS` (new option; default 1800) bounds each `run_cell`. On a
   timeout, EOF, `fatal` or a protocol violation (a line over 1 MiB, not strict JSON, not `agentprov-backend/0.1`, an
   unexpected `op`, a `cell_done` for another `req`) the worker tree is killed, the capture log path is checked through
   the no-follow opener, `append_terminal(…, "aborted")` continues the chain (`appended_by: parent`), the session is
   ingested with every regular file under `raw/` as its artefact set, and the next attempt gets a fresh worker. First
   SIGINT: in-flight workers are killed, their sessions sealed `aborted` and ingested, the manifest written, exit 130.
9. **Ingest** (`cli.live.staging`, then the runner). Rejected reported labels and links, hard links and special files
   become register rows `ingest.*` (stage `ingest`, `not_imported`, subject `{snapshot_id: "live", path:
   "<session>/<label>"}`) and keep the staging directory for inspection. A reported digest that does not verify (or a
   blob whose content does not match its address) makes the attempt non-conclusive; the files are stored under their
   actual digests. **Deviation from D.11.3 rule 2:** this is recorded as a register row `map.capture_error` (rule
   `null`, detail naming the label) on the execution, not as an AER seal issue: no shipped rule states this T0 protocol
   check, and adding one to a catalogue changes the catalogue digests that every golden PROV document records. The
   mapper's own checks still flag every evidence-level inconsistency inside the AER. The secret scan uses
   `Redactor.contains_secret` with the secrets in T0's environment (K.3.4 name pattern) plus the `.env` values used; a hit
   gives `capture.quarantined` (subject `{snapshot_id: "live", path: "<session>"}`), nothing stored, staging kept, exit 1.
   A capture log the worker sealed after a failed redaction scan (its `error` event `where: "capture.redact"`, C.13.10
   item 6) is quarantined the same way, whatever the literal scan finds (D-290; the detail names the reason). The ledger
   entry's `index_status` is the status of the execution's index row (D-293).
   The capture identity check compares the `agentdojo/identity_digests` note with `hello_ok.identity` (JCS, member by
   member) and the identity event's benchmark facts; a mismatch aborts the campaign (exit 3) and keeps the session in
   staging. Verified files are stored with origin `capture {session}` and mapped by one T1 `map` job in `container` mode
   (D.10.4a item 2); SEM, PROV and tiers 3-4 run in T1 `prov` jobs; the index row (mode `live`, `attempt`) is written
   last. A clean session's staging directory is removed after it is stored, unless `--keep-staging` (new option; used by
   CI to feed the `live_artefacts` tests).
10. **Core change (invariant 5; H.3.1, H.7.1).** `corpus.index` and `corpus.writer` required exactly one raw entry with
    role `primary`, an import-era assumption: a live AER has no `primary` artefact, and a live row's source key and
    `n_origins` name its capture log. `corpus.index.primary_role(mode)` makes that artefact `capture_log` for `mode:
    live` (`primary` otherwise). No import row, AER, SEM or PROV byte changed. The import pipeline's index mode and
    attempt became overridable hooks (`_Pipeline.index_mode`, `attempt_of`).
11. **Attempts and resume** (N.1.8(4)). The working manifest's `live.sessions` is the attempt ledger (session, `ex`,
    `cell_key`, `config_digest`, `repeat`, `attempt`, the capture log's `session.end` status read back from the stored
    log, the seal's accounting verdict, `capture_sha256`, index status, `parent_appended`, `capture_error`), rewritten
    after every attempt. On resume an entry counts only while the capture log it names is in the raw store (resume is
    keyed on sealed raw evidence; a lost manifest loses no evidence, only skips). A unit is **conclusive** when an attempt
    ended `complete` with accounting `consistent` or `unverifiable` and no capture error; one that ended `complete` but
    `inconsistent` is settled unless `--retry-inconsistent`; anything else is re-attempted at once while `--max-attempts`
    (default 3, counted across invocations) allows. A quarantined attempt counts and is not re-attempted automatically.
    `--limit` counts attempts started. `--repeats N` is supported (the repeat index lives in the ledger; the capture has no
    member for it). Counters: N.2.1's plus `quarantined`, `rejected_files`, `unreported_files`. Exit 1 when any unit is
    inconclusive or inconsistent, any execution failed, a session was quarantined, a file was rejected, or the canary
    stopped the campaign.
    - **Setup refusal (live pilot 2026-10-22).** An attempt whose capture log records a fatal `UnsupportedConfiguration`
      at `where: setup` (for example an attack that names the model, for a model id with no stock AgentDojo name and
      no `--model-display-name`) stops the campaign: no further cell and no re-attempt starts. The refusal belongs to
      the configuration, so all of them would fail alike. The refusal is noted, and the run exits 1 with a partial
      corpus.
    - **Display-name hint.** Before consent, a real-model plan with an attack that names the model and no display name
      gets a notice. It is not a refusal, because only the worker knows AgentDojo's `MODEL_NAMES` table (the core never
      imports it).
12. **Canary and quality report** (`cli.live.quality`). Both are computed from the stored capture logs and their blobs
    (strict loader), never from feedback. Canary: the first `--canary N` pending units (default 10) run to the end; A3
    (a configured `temperature`/`reasoning_effort`/`top_p`/`seed`/`max_tokens` not transmitted), A4 (a kept reply with no
    structured call whose text names a request tool or carries a function tag), A6 (abnormal finish in more than 20 % of
    kept calls) or an errored, aborted or unsealed attempt stops the campaign before the rest (exit 1; partial corpus);
    A9 is a preflight condition only. The report (`agentprov-capture-quality/0.1`: per model, statuses, passes, kept,
    discarded and error calls, retries, HTTP classes, the controls, instrumentation, parent-appended sessions; attempts per
    unit) is `live.quality` in the working manifest and printed at `summary`; the CLI summary schema has no member for it.
13. **Manifest.** Mode `live`, `synthetic: true` for scripted runs, `formats.capture = "capture/0.1"`,
    `producer.sandbox` (`null` for scripted runs; N.1.11(3)), the snapshot origin `{kind: capture, session_ids}`, and the
    `live` block (backend, environment name, backend lock digest, benchmark identity, agent facts without secrets,
    `test_only`, plan and configuration digests, run conditions: `jobs`, `start_stagger_ms`, `cell_timeout_s`,
    `max_attempts`, `repeats`, `temperature_policy`, the instrumentation in force, the ledger and the quality report).
14. **Import boundary (M.5.3, amended).** `agentprov_capture` may also be imported under `cli/live/` (the redactor's scan,
    `append_terminal`, secret names for the `uv` environment); the core still imports neither `agentdojo` nor
    `agentprov_backend`.
15. **AutoDojo (phase 9).** `run autodojo` reuses every path above, generalised by backend: the plan's backend, the
    hello and capture-identity checks against the backend id, `NLTK_DATA` from the marker's verified NLTK data, the live
    profile's pins checked against the environment, the backend refusals, and the attack-cache verification, storage,
    per-session staging and recording. The decisions are D.11.9 items 8-12; the evidence is
    `docs/reports/live/autodojo-phase9.md`.

### N.2.2 `import` (alias `convert`) and `fetch` — ingest released artefacts (D3, D4)

```
agentprov import SOURCE --corpus DIR (--input PATH | --fetch --allow-network)
      [--profile ID] [--pin ROLE] [--snapshot ID] [--spec SPEC.toml] [--corpus-id ID] [--verify-against-pin]
      [--suite S] [--attack A] [--pipeline P] [--variant V] [--select K=V…]
      [--limit N | --sample N [--sample-mode {first,spread,random}] [--seed S]]
      [--until {raw,aer,sem,prov,validation}] [--prov-spec SPEC…]
      [--retry-failed] [--release] [--cache-dir DIR] [--jobs N] [--in-process] [--allow-hardlinks] [--dry-run]
      [--no-validation-cache] [--max-file-bytes N] [--max-json-depth N] [--context ROLE=PATH…] [--no-context ROLE…]
agentprov import --spec SPEC.toml --corpus DIR (--input PATH | --fetch --allow-network) …
```

| Option | Meaning |
|---|---|
| `SOURCE` | registry source id or alias (N.3.1). Optional with `--spec` |
| `--input PATH` | local origin: directory, file or `.zip`, outside the repository and the workspace (R-52). Opened read-only through `ingest.paths` (no-follow, `S_ISREG`, `st_nlink == 1`; G.3.6). A zip is read in place, never extracted: its members are derived objects of the versioned `expand` stage (AD-12) |
| `--fetch` | acquire the pin into `--cache-dir` (default `$AGENTPROV_UPSTREAM_CACHE`, else `$AGENTPROV_HOME/cache`) by bare, extraction-free fetch, verifying sha256 and git blob ids (`raw.fetch`; G.7.5). Mutable refs are refused (exit 3) |
| `--profile ID` | import profile; default is the registry's primary import profile for `SOURCE` (D.2.9) |
| `--sample N` | dev runs (D-529): a deterministic sample of N executions, chosen once from every execution of the import before anything is mapped, so it never depends on `--batch-size`, `--jobs` or the resume order. `--sample-mode first` (default) takes the first N sample keys in order; `random` the N with the smallest `sha256(S ‖ 0x00 ‖ key)` (`--seed S` required, and only there); `spread` the reader's strata (arms) round-robin (`sample_stratum`; `inspect.eval`, whose stratum is the `.eval` log, the part of the key before its last `!/` (a log inside a declared nested archive included; another head has none, NF-37), `autogen.runs` and `credleak.cell`), refused (exit 5) for a reader that names none, before anything is stored or written (a working corpus keeps its manifest byte for byte; NF-35). The sample key is the file label, `label!/member` for a container's planned unit, or `label#<source key>` for a multi-execution item (`label#` for a file sealed whole, which stays a candidate when a resume or a collapse from another snapshot skips it, so a resumed sample draws the same set; NF-34). A pinned object (runner item R3) is keyed `label` + NUL + `pinned` apart from its LFS pointer, and the pointer, which maps no execution, passes exactly when its object does (D-530 addendum, PR-8 and RC-5). Whole files are listed by label and only the chosen ones are stored; containers are expanded and planned, and multi-execution files mapped once to list their items, in a first pass, and only the chosen units are mapped (members) or sealed (items). Exclusive with `--limit`, refused with `--release`. The working manifest records `selection.sample = {n, mode, seed, candidates, selected, stratum}`, the same in the snapshot's own `selection` (N.1.7), and `partial: true`; the summary counts `sampled_out`. A listed snapshot is resumed with the same `n`, `mode` and `seed` (or with no selection, to complete it); another sample, `--limit` or a filter is refused (exit 4, NF-36) |
| `--pin ROLE` | profile pin role (D.4.3), e.g. `2024-06`, `head`; default from the profile: the part's one primary pin. A part with several primary pins (one per input archive, each its own snapshot) is refused without `--pin` (D-932) |
| `--snapshot ID` | snapshot id inside the corpus (HL H.2.3), a registry part id (I.1.1) such as `head` or `2024-06`; default = the pin role. Several snapshots may share one corpus, one per invocation (H.1.1(1); implemented by D-202, see the deferrals note below) |
| `--spec SPEC.toml` | committed corpus spec (H.1.6). Without one, the CLI synthesises a spec from profile and options and writes it to `rules/corpus-spec.toml` |
| `--verify-against-pin` | with `--input`, compare each file's git blob id with the pin's tree (cached listing, or `--allow-network`). A match records the pinned `git` origin (`repo`, `commit`, `path`, `blob_sha1`). **v0.1 (DECISIONS D-15):** `--input` requires this check; without it the import is refused (exit 4, `raw.origin.local`), because a `local` origin can never be released (H origin table) and the AER writer seals in release mode. *Superseded text:* "without the check, the origin is `local` (dev only) and a notice is printed" |
| `--suite/--attack/--pipeline/--variant/--select/--limit` | filters (N.1.7) → partial working corpus. A listed snapshot is resumed with its recorded filters and sample; `--limit` is an incremental cap, not part of that selection: another limit (or none) extends the snapshot, which records the cumulative cap, and a limited run that runs out of units completes it (NF-36) |
| `--until STAGE` | stop after the stage; continue later with `derive`. Default: the spec's `[derive]` stages |
| `--prov-spec SPEC` | repeatable; default `agentprov-prov/0.1`. `adprov-v2.3-compat` is accepted for `adprov-v1` and `agentdojo` only; its output is flagged `apv:RegressionOracle` and a notice is printed (R-55) |
| `--release` | runner mode `release` (D.2.9): strict checks, no filters, no `--limit`, no `--in-process`. Below CPython 3.14.8, archive and compressed-stream ingestion is refused before any object is opened (exit 3, `ingest.interpreter.unpatched`; AD-16 as ruled; G.3.8) |
| `--in-process` | debugging only; recorded (N.2) |
| `--allow-hardlinks` | accept `st_nlink > 1` files in an `--input` tree; recorded in the manifest (G.3.6). Never applies to live staging |
| `--context ROLE=PATH` | repeatable (D-530). A local copy of the context pin `ROLE`: every role a profile declares in `[import] context_artefacts` (`"<role>:<glob>"`; runner item R2, D.16.14) is a context tree. A download pin is checked with `verify_download` and read as an archive context (stored with the pin's origin, expanded with the role's globs, AD-12). A git pin's directory is checked blob by blob against the cached tree. Without this option, each declared role is resolved from the verified fetch cache (fetched with `--allow-network`). A role that resolves neither way is refused (exit 4, `raw.fetch.not_cached`) |
| `--no-context ROLE` | repeatable (D-530): map without the declared context role. The units lose its per-unit artefacts. It is reported as a notice in the command summary and recorded in the snapshot's `context_skipped` (the working manifest and the sealed `agentprov-corpus/0.2` form; D-221, NF-29); a re-map skips the role too, and the family's join issues show which units lack it. Never implied. A role given twice to `--context` is refused (exit 2), as is a git-pinned role's PATH that holds none of the pin's role files (NF-27). A context download pin or an `lfs_object` pin without a sha256 is refused (exit 4, NF-28) |
| *(LFS objects)* | each `lfs_object` pin whose file the input holds as an LFS pointer is acquired from the fetch cache (or with `--allow-network`), verified by its sha256, and imported beside the pointer (runner item R3; D-530 item 6) |
| `--no-validation-cache` | do not store the tier-4 round trips. By default, each completed round trip of the `validation` stage is stored in the round-trip cache (D-550; N.2.5 item 9). Later validations of the same PROV bytes then reuse it. The import never reads the cache: its PROV is new. Corpus bytes are the same either way |
| `--max-file-bytes`, `--max-json-depth` | tier-1 overrides of `ingest.limits.IngestLimits`, recorded in `corpus.json`. Defaults: G.3.2 (Q1, closed) |

**Behaviour** (`adapters.runner.import_source`, D.2.9).

1. **Status gate** (N.3). `planned` and `not_possible` exit 5. `via` redirects (`autodojo` → `rope`). Caveat and
   partial notices are printed and recorded.
2. **Acquisition.** Apply G1–G4 and G7. Every artefact goes into the raw store *before* mapping, with origin records
   (D3; A2).
   - Identical bytes at two origins become one object with two origin records (`dedup.collapsed`, H.7.2).
   - In dev mode below CPython 3.14.8, archive or compressed-stream ingestion prints the
     `ingest.interpreter.unpatched` warning and records `python_version` and `interpreter_advisory` in `corpus.json`
     and `register.jsonl` (G.3.8).
3. **Expansion** (AD-12). Archives are expanded in T1 by the versioned `expand` stage: profile-selected members
   become member objects (origin kind `member`), with rows in `raw/members.jsonl`; other members get a
   `not_selected` row (R-40).
4. **Discovery.** The profile include/exclude globs run in sorted order. Strays (`.DS_Store`, `._*`) are not
   candidates (`convert_runs.py:232-239`). Every candidate gets exactly one disposition (HL R1): a row (possibly
   failed) or a register entry. Examples:
   - `select.owned_elsewhere` (with `owner`) for AgentDyn's DRIFT copies;
   - `select.not_execution_artefact` for ROPE's `lh_cells.json`;
   - `select.dialect_planned` for ASB result CSVs and for Inspect `.eval` logs outside the supported producer band
     (`inspect_ai 0.3.247.dev69`; AD-06). Inspect logs inside the band are imported by `adapters.inspect`.
5. **Per unit:** tier 1, dialect sniff, mapping (T1 jobs, A3), SEM, PROV, validation (`corpus.derive`), write gate,
   index row.
   - Outcome-only logs become sealed `outcome_only` records with the seal issue `no_execution_observed` (register
     `map.no_execution_observed`; R-28). HL R2 replaces `EXCLUDED.json`.
   - An `ex` conflict is a named failure, and nothing is half-written (D.2.9).
6. **Close.** Write the register, `derivation.json` and the working manifest.

**Outputs.** `<DIR>.partial/`. Counters (D.2.9): `seen`, `mapped`, `sealed_clean`, `sealed_with_issues`,
`degenerate`, `excluded`, `duplicates`, `skipped_resume`, `filtered`.

**Exit codes.**

| Code | When |
|---|---|
| 0 | all units sealed, clean or with issues |
| 1 | any degenerate or failed unit |
| 2–5, 130 | as N.1.3 |

**`fetch`.** Populates referenced raw (H.4.3).

```
agentprov fetch --corpus DIR [--only sha256:HEX…] [--cache-dir DIR] --allow-network [--dry-run]
```

It downloads the objects of `raw/REFERENCES.json` into the cache, verifying each by sha256 before storing it. The
file is corpus-supplied and therefore untrusted (R-43; G.7.5):

- an entry resolves only if it matches an **in-package** profile origin (kind, repo, dataset or DOI, pinned revision,
  sha256); any other entry is not fetched and is reported as `raw.reference.unpinned_origin`;
- a gated-source token is attached only to the host the profile declares and is dropped on any redirect;
- it never accepts gates or licences, and reports objects that need `hf-gate-acceptance` or `authors-permission` as
  `unverified`;
- it never writes into the corpus.

Exit 0 when all are present and verified; 1 otherwise. `REFERENCES.json` stores no command string; the CLI generates
the help text `agentprov fetch --corpus <root> --only sha256:<hex>` at display time (RESOLUTIONS §3.7; N.5).

**Implementation resolutions (phase 6, 2026-10-08).** The code is the reference (`agentprov.raw.fetch`,
`agentprov.raw.references`, `agentprov.cli.fetch`).

1. **A second mode: `fetch --profile ID [--pin ROLE…] [--path PREFIX…]`.** N.2.2 specifies only `--corpus`, which fetches
   referenced raw. Acquiring a profile's pins (the "pinned-fetch recipes" of the phase-6 row) needs a command of its own, so
   exactly one of `--corpus DIR` and `--profile ID` is required (exit 2 otherwise; `--only` goes with `--corpus`, `--pin`
   and `--path` with `--profile`). Without `--pin` the profile's `primary` pins are fetched; `--pin` names any fetchable
   role; `--path` replaces a git pin's tree prefix. The names `--profile` and `--pin` are those of `import`.
2. **`--allow-network` is always required** by `fetch` unless `--dry-run` (exit 4, N.1.11(1)), even when the cache would
   satisfy the request. The library is finer-grained: `Fetcher(allow_network=False)` answers from the cache and raises
   `raw.fetch.network_refused` only when it must contact a host. `--dry-run` prints the plan (what is cached, the host, the
   size when pinned) and writes nothing.
3. **Large downloads (U-07).** A download of 100 MiB or more (`LARGE_DOWNLOAD_BYTES`, by the pinned size or the announced
   `Content-Length`) also needs `--i-consent-to-large-download` (exit 4 `raw.fetch.consent_required`, naming file, host and
   size). A download with neither a pinned size nor an announced length is counted as it streams and refused, its partial
   file removed, once it reaches the threshold without consent; `--dry-run` marks such a pin as large (as for an unsized
   split part, D-249). The only consent recorded in the log is the flags given.
4. **Recipes are data.** `Recipe.from_pin()` reads a `[[source.pins]]` row: a git pin needs a 40-hex `commit`
   (`raw.origin.unpinned`, exit 3, otherwise) and takes the `repo` from the pin or `canonical_repo`, the path prefixes from
   `tree`, and `expected_files`/`expected_bytes` as expectations that are **reported** (exit 1, `raw.fetch.expectation`),
   never silently accepted. A download pin (`zenodo`, `hf`, `url`) needs a file name and at least one digest
   (`sha256`, the pin; `md5`, a transport check; `bytes`); a DOI alone, as D.4.3 lists the alternative origins, is skipped with
   a notice and is not a recipe. A download verified by MD5 alone succeeds with a reminder to pin the SHA-256 in the profile.
5. **Layout and verification.** The cache is `<cache>/git/<host>/<owner>/<repo>.git` (a Hugging Face dataset
   repository `https://huggingface.co/datasets/<owner>/<name>` at `<cache>/git/huggingface.co/datasets/<owner>/<name>.git`;
   other `huggingface.co` namespaces, and a two-part path whose owner is `datasets`, `models` or `spaces`, are refused; D-53) (bare, `git fetch --depth 1` of the
   pinned commit, `init --template=`, hooks off, https only with file protocol off and `http.followRedirects=false`, `transfer.fsckObjects`), `<cache>/zenodo/<record>/<file>`,
   `<cache>/hf/…` and `<cache>/url/<sha256>`; downloads are streamed to a hidden `.part` file, checked, made read-only
   (0444) and renamed. `fetch --profile` reads every blob of a git pin back (`git cat-file --batch`) and recomputes its
   SHA-1 and size against the tree entry; a mismatch is `raw.fetch.blob_sha1`. A cached file that no longer matches its pin
   is `raw.fetch.digest` and is never overwritten. The `git` environment is built from an allow-list (no `HOME`, no
   `GIT_DIR`; `GIT_NO_LAZY_FETCH=1` always, and an absent blob is `raw.fetch.blob_absent`, D-54), git ≥ 2.50.1 is required (exit 3 otherwise) and the cache must lie outside every git repository (exit 3).
6. **Acquisitions log.** Each real retrieval appends one JCS line to `<cache>/acquisitions.jsonl`: for downloads the keys
   `bytes consent doi file kind md5 md5_published record retrieved_at sha256 url verified`, for git
   `bytes commit consent files kind mode paths repo retrieved_at store tree`. A cache hit appends nothing. A row never carries
   a credential (the writer refuses one).
7. **`--corpus` mode.** `raw/REFERENCES.json` is opened through `ingest.paths` (no symlink) and parsed strictly
   (`agentprov.raw.references`): exactly `format` and `objects`, closed `reason` and `requires` lists, no other member.
   Each object resolves only against the fetchable pins of the **shipped** profiles (kind, repository or DOI or dataset,
   commit or revision, a path at or below a pin path read as a git pathspec, `logs` and `logs/` alike but never `logsX/`,
   and the pinned digest); the rest is `raw.reference.unpinned_origin`
   (exit 1, no contact). An object that `requires` `hf-gate-acceptance` or `authors-permission` is reported `unverified`
   (exit 1) and never attempted. A fetched object whose SHA-256 or size differs is `raw.reference.digest`. The corpus is
   never written.
8. **Credentials.** A download recipe may name `token_env` and `token_host`; the value is read from the environment mapping
   the Fetcher was given, attached with `add_unredirected_header` and only when the request host equals `token_host`; it is
   not written to the log, the summary or the cache. The redirect handler (`SafeRedirectHandler`) requires https on every
   hop, follows only the recipe's host allow-list, refuses credentials in a URL and drops `Authorization`, `Cookie` and
   `Proxy-Authorization` on any host change.
9. **Where it lives.** The command is `cli/fetch.py` (registered in `cli/main.py`), not `import_.py`, so the importers can
   rework `import_.py` independently. `raw/fetch.py` is the one raw module that imports `subprocess`, `shutil`, `ssl` and
   `urllib.request` (M.5.3); `tests/security/test_raw_store.py` exempts it from its import scan and
   `tests/security/test_fetch_hardening.py` scans it for shell use, extraction helpers and credential handling.
10. **Not done.** No real download was performed in this phase; the first real fetch of the pinned trees (U-07) is the
    user's call. `import --fetch` and `verify --against-pins` will call `Fetcher` (`fetch`, `git_tree`, `iter_git_blobs`,
    `store_git`) when the import pipeline lands.

**Implementation resolutions (phase 6, import, 2026-10-08).** The code is the reference
(`agentprov.adapters.runner.importer`, `agentprov.adapters.runner.provjob`, `agentprov.cli.import_`); the runner contract is
D.2.9 and its resolutions are in D.2.9's note.

1. **Status gate.** As N.3.1. The part is `--snapshot`, else the part of the `--pin` role, else the source's one importable
   part. `supported` and `partial` proceed and their caveat is printed and recorded in `notices`; `planned`,
   `not_possible`, a part role without an import (`compat_oracle`) and an import status of `None` (`foobench`) exit 5 with
   the N.3.2 refusal. An id that is not registered is a usage error with suggestions (exit 2, N.1.3); a v0.1 source id of
   D.3.3 that this build does not register yet (`midojo`, `rope`, …) exits 5 "not registered in this build". The aliases of
   N.3.1 resolve with a notice. The registry rendered `planned` for the three parts until this command existed; they are
   `partial` ("full snapshot not yet imported") from the commit that adds it, and `supported` only from the commit that
   records their full-snapshot imports (D.3.2; HON-10).
2. **`--fetch`** reads the profile's git pin from the fetch cache (`GitPinTree`: `git ls-tree`, `cat-file --batch`, every
   blob's SHA-1 recomputed). `--allow-network` stays required (N.1.11(1)), but `Fetcher` contacts the host only when the
   pinned commit is missing from the cache; a cached pin is read with no network call. `--fetch --dry-run` needs no
   `--allow-network`: it prints the plan and maps only a cached pin (N.1.6). Download pins (Zenodo, HF, URL) deliver
   archives and are deferred (exit 5).
3. **`--input` needs `--verify-against-pin`** (exit 4 `raw.origin.local` otherwise). This is a deviation from the table
   above ("without the check, the origin is `local` (dev only) and a notice is printed"): the AER writer validates every
   record in release mode, where a `local` origin is an error (C.17 AER-V20 `local_origin`), so a local-origin AER cannot be
   sealed at all. Making the writer mode-dependent is a core change and was not made. **Decided (2026-10-08, DECISIONS
   D-15):** the refusal is the v0.1 behaviour, and the table row above is amended. Two pin checks exist:
   - a **git pin** whose tree listing is in the cache (or is fetched with `--allow-network`): a file whose label is a path
     of the pin's tree and whose git blob id matches gets the pinned `git` origin;
   - a pin that records a **J.1.4 tree-listing digest** (`listing_sha256`, the AgentDojo-PROV trees, which are git-ignored
     at their pinned commit): when the digest over the candidates equals the pin, every file gets the origin the family's
     reader names in `listing_origin(pin, label)` (adprov: `corpus {AgentDojo-PROV, 2.3, producer_commit, path}`, the
     origin the migration gates record, J.4).

   A file the pin does not vouch for is not stored or mapped; it gets the register entry `raw.origin.blob_mismatch`
   (stage `ingest`, error, `not_imported`) and the command exits 1. `--input` of a `.zip` is deferred (exit 5); `--input`
   names the pin's tree root for a listing pin and the repository root for a git pin (labels are compared with tree
   paths).
4. **Stages.** `--until raw` stores and expands only; `aer` maps, seals and runs the AER validator; `sem` adds the
   registry part's semantics profiles (`Capability.semantics`; phase 7, C.14.7 item 5; a part with none stops after
   `aer` with a notice); `prov` adds `agentprov-prov/0.1` with one assessment bundle per SEM document; `validation` (the
   default) adds the tier-3 (SEM) and tier-4 validators. `--prov-spec` accepts only `agentprov-prov/0.1`; `adprov-v2.3-compat` exits 5 (the oracle's byte identity
   runs through `agentprov migrate gate B`), any other value exits 2.
5. **Filters.** Index facets need SEM (phase 7), so `--select` keys are fields of the AER header, applied after mapping:
   `suite`, `task`, `attack` (`none` when benign), `defense` (`none`), `benchmark`, `unit` and `variant`; `--suite`,
   `--attack` and `--variant` are shorthands; an unknown key exits 2. `--pipeline` exits 5 (an index facet). A filtered unit
   is counted `filtered` and not written; any filter or `--limit` marks the working manifest `"partial": true`.
6. **Counters.** N.2.2's names plus `failed` (a unit that is not degenerate but failed a stage or carries an error issue),
   `registered` (register-only dispositions), `derived` and `validated`. `seen` counts candidates (for Inspect, `.eval`
   containers, not samples); `excluded` counts exclude-glob matches; `mapped` counts AERs sealed in this run, degenerate
   ones included. Exit 1 when any unit is degenerate or failed or any failure is listed.
7. **Resume and identity.** A candidate whose primary artefact already has an index row is `skipped_resume` (a byte
   identical tree on a second run, K.15(7)). G4 is checked on the working `corpus.json` (corpus id, source, mode, snapshot)
   and on `derivation.json` (the `fn_digest` of every stage both runs define): a mismatch exits 4. *Superseded by the
   deferrals note (D-202):* a second snapshot is added, not refused; G4 compares corpus id, source, mode and profile. `--retry-failed` drops the rows, register entries and validation
   rows of failed units and re-processes them. An interruption flushes the units sealed so far, writes the documents,
   releases the lock and exits 130; the next run resumes. A flush writes `executions.jsonl` last, after the register
   and the validation files, so the index is the commit point: a flush that fails part-way leaves no index row without
   its validation row, and the next run re-processes the unit.
8. **Dry run.** The pipeline runs into a private temporary tree that is removed afterwards; an existing working index is
   read (read-only) for the resume decisions. Nothing is created under `--corpus`.
9. **Guards.** G1 (sealed manifest) and the destination guard of the writer; G2: the `.partial` tree may not overlap the
   input or the fetch cache (exit 4); G3: the CLI may not run `git` (M.5.3), so an output inside a git work tree is refused
   (fail closed); G6 is the writer's lock.
10. **`info`** renders the registry per part (D.3.5) through `adapters.registry.render`, and `info SOURCE` prints the parts,
    profiles and pins, licence and evidence references. `--matrix` and `--must-not-claim` need the claims library of D.3.1,
    which is not part of this build, and exit 5.
11. **Deferred** (each with a refusal or a usage message): `--spec` and the synthesised `rules/corpus-spec.toml`, the
    `rules/` byte copies, `--prov-spec adprov-v2.3-compat`, `--pipeline`, and the `git check-ignore` exception of G3.
    Sealing, `checksums.sha256`, the datasheet and `verify` stay phase 11. Archive `--input`, download pins with
    `--fetch`, several snapshots per corpus and the storage of `$blob` payloads were deferred here and are lifted by the
    deferrals note below.

**Implementation resolutions (deferrals part A, 2026-10-12; D-200..D-204, proposals).** The code is the reference
(`adapters/runner/importer.py`, `cli/import_.py`, `raw/fetch.py`, `corpus/{rawtree,writer,manifest,package,derive,verify}.py`).

1. **Archive inputs (D-200).** When the profile's pin is a download pin (a Zenodo or Hugging Face file), `--input FILE
   --verify-against-pin` checks the file offline against the pin (name, size, MD5 when pinned, SHA-256;
   `raw.fetch.verify_download`) and `--fetch` reads the verified file from the cache (100 MiB or more also needs
   `--i-consent-to-large-download`, U-07). The file is stored with the pin's origin, expanded in place by the versioned
   `expand` stage with the profile's `include`, `blobs` and context globs as the selection, and every selected member is
   mapped as a whole file with its `member` origin. Member register subjects are `<file>!/<member>`; the snapshot records
   `input {kind: archive, label, sha256, bytes}`; `recompute` re-expands the stored file. Refused (exit 5): a `.zip` under
   a git pin, a URL pin with `--fetch`. Since D-380 (ingest-formats-3) an archive of a container dialect is expanded at
   level 2, and archives declared in `[import] nested` at level 3 (D-382); the profile must declare `[import]
   include`. The member-origin interface for mappers is
   D-204 (a mapper reads a member origin's `label` where it reads a git origin's `path`).
2. **The download-pin record (D-201).** A Zenodo pin may record `record` (must equal the DOI's) and `version`; the
   snapshot's `pin` is the whole record (DOI, record, version, file, size, digests). A pin without a SHA-256 cannot vouch
   for an import (`raw.fetch.unverifiable`).
3. **Several snapshots per corpus (D-202; replaces the refusal of item 7).** G4 refuses another corpus id, source, mode or
   source profile, not another snapshot. H.7.2 is implemented: bytes another snapshot already mapped are not mapped
   again; the row lists both snapshots, the second origin is a `raw/origins.jsonl` row (`n_origins` recounted) and
   `dedup.collapsed` records it. The AER keeps the first importer's origin; the manifest keeps the snapshots in import
   order (each with its `part` once there are two), and `recompute` and `verify --level rederive` replay them in that
   order. `agentdojo-upstream` is still released as two corpora (D-35).
4. **Blob payloads (D-203).** `[import] blobs` globs name files holding `$blob` payloads: stored first with pinned
   origins, never mapped, offered to the map jobs of units in their directory or above as `blob:<hex>`.

### N.2.3 `derive` — add or complete derived layers

```
agentprov derive --corpus DIR [--stages sem,prov,validation,views] [--prov-spec SPEC…]
      [--semantics-profile ID] [--views transcript-v1] [--trig DIR]
      [--select K=V…] [--limit N] [--jobs N] [--in-process] [--no-validation-cache] [--dry-run]
```

**Behaviour.**

1. Working corpora only (G1). The one exception is `--trig DIR` on its own, which also reads a sealed corpus.
2. **Missing stages.** For each selected execution with a sealed AER, run the missing DAG stages (H.8) for the
   requested SEM profile (e.g. `agentdojo.suites`, integer version, directory `agentdojo.suites-1`), PROV specs and
   views.
   - Each spec writes its own `prov/<spec_dir>/<ss>/<ex>.prov.json`: bundled canonical PROV-JSON only. The flattened
     core document is deferred (AD-10 row 4).
   - `--views transcript-v1` writes the optional `views/transcript-v1/` (RESOLUTIONS §3.6) for AgentDojo-family and
     `adprov-v1` executions only (D1; EF E.8.2). The view reads nothing from raw (AD-02).
   - SEM, PROV and validation MAY run in the T1 pool or in-process (AD-10 row 17); the choice is recorded in
     `producer.isolation` (G.4.9).
   - Writing or loading `adprov-v2.3-compat` output prints the compat notice; the manifest and index flag it
     `apv:RegressionOracle` (R-55).
3. **`--trig DIR`.** Writes PROV-O TriG (one named graph per bundle) for the selection into `DIR`, which must lie
   outside the corpus (G2, G8). TriG is produced on demand and never stored or hashed in the corpus (AD-10 row 3).
4. **Version guard.** A layer present at a *different* version of the same spec or profile is refused (exit 4) — use
   `recompute --out`.

Outcome replay (the r1 `derive` option that executed benchmark checkers) is deferred (AD-10 row 2). If it returns, it
is a T1-restricted job in `backends/agentdojo` with no keys and no network (R-34).

5. **Round-trip cache (D-550; N.2.5 item 9).** Each `prov` job that validates gets the cache's entry for the
   source row's stored PROV digest as a hint. It uses the hint only if the PROV it derives has exactly that digest
   (and under its own context). A job that ran the round trip returns it for the parent to store. Outputs are identical
   with and without the cache. A job that skips tier 4 (G2c-5, `conformance: false`) never reads or returns an entry.
   `--no-validation-cache` turns it off. The same applies to `recompute` (N.2.4) and to `verify --level rederive`
   (N.2.6), whose `--release` audits the cache and never reads it.

Counters: `selected`, `stages_run`, `reused`, `failed`. Exit 0, 1 or 2–5.

### N.2.4 `recompute` — content-addressed re-derivation (D9; HL H.8)

```
agentprov recompute --corpus DIR (--out NEWDIR | --dry-run) [--stages expand,aer,sem,prov,validation,views]
      [--prov-spec SPEC…] [--select K=V…] [--sample N --seed S] [--show-diff N] [--strict] [--jobs N]
      [--no-validation-cache]
```

**Behaviour.**

1. **Inputs first.** Verify raw digests [audit/corpus.md §3.3 R5]. Referenced raw must already be in the cache
   (`fetch`); otherwise those executions are `unverified`.
2. **Catalogues** (AD-14). Profiles and rule catalogues are loaded **only from package resources**, at the versions
   recorded in the corpus. An absent version gives `rules.unavailable` (the execution is `unverified`). The corpus
   `rules/**` copy is a record: its digest is compared, and a difference gives `rules.mismatch`.
3. **Re-run.** Re-run the stages from raw, including the `expand` stage for archive members (AD-12), with the
   installed adapters:
   - into `NEWDIR.partial/` with `--out`;
   - in memory with `--dry-run`, which still validates (R3).

   Never in place (H.1.5(3)).
4. **Compare.** Compare JCS bytes and digests per execution, never Python `==` (AD-02). This catches `True` → `1`
   changes that dict equality missed [audit/corpus.md §3.3 R2]. Each execution is classified as:
   - `identical`;
   - `changed_explained`: a recorded function version differs (H.8.4);
   - `unexplained_change`;
   - `failed`;
   - `unverified`.
5. **`--show-diff N`.** For up to N changed executions, prints the stage and the first differing JCS line of each
   changed file, escaped (N.1.13). For changed PROV files it adds the order-insensitive semantic diff of
   `agentprov.prov.diff.diff_documents` (B COR-21; HL H.8). The corpus diff command stays deferred (N.2.7).
6. **`--out` result.** An unsealed corpus with `derived_from: {corpus_id, corpus_version, root_digest}`. Raw objects
   are hard-linked on the same filesystem, else copied. Then `package` it as a new version.

Counters: `identical`, `changed_explained`, `unexplained_change`, `failed`, `unverified`.

| Exit | When |
|---|---|
| 0 | no `unexplained_change`, no `failed`, and (under `--strict`) no `unverified` |
| 1 | otherwise |

The baseline's standing check ("0 changed" on 17,664 and 18,027 traces; `README.md:249-251`; [audit/corpus.md §8
invariant 2]) becomes `migrate gate-b` (N.2.14).

### N.2.5 `validate` — tiers 2–4 and 6 (D8)

```
agentprov validate (--corpus DIR | FILE…) [--tiers aer,sem,prov,linkage,shacl,regression]
      [--prov-spec SPEC] [--strict | --release] [--report PATH] [--sample N --seed S]
      [--card CARD.md] [--jobs N] [--in-process] [--no-validation-cache] [--dry-run]
```

**Behaviour.**

1. **Tiers.** The default tiers are `aer,sem,prov,linkage`. `--release` implies `--strict`, adds every applicable
   tier including `shacl` and `regression`, and forbids sampling. Under `--strict`, a `skipped` check fails (D8;
   validation audit V11). `regression` is the v1 → AER → v1 round trip where the source is `adprov-v1`: A1 (JCS) and
   A2 (bytes), from the AER alone (AD-02; AD-07).
2. **AER tier.** It includes the 13 record kinds of aer/0.1 (Addendum B-1). For the generic `activity` and
   `artefact` records, every `type` must be declared in the family catalogue, and specialised kinds come first
   (AD-15 as ruled; D.1.3 A-9).
3. **PROV tier.** It includes the never-emit checks and the profile rules of `agentprov-prov/0.1`, among them EF's
   generic rules G-ACT, G-USE, G-GEN and G-ASSOC, whose activities take part in the Inference-6 closure (EF).
4. **Working corpus.** It writes the `validation/` stage (`results.jsonl`, `summary.json`; H.1.2), unless
   `--dry-run`.
5. **Sealed corpus or files.** Read-only. The report goes to `--report` or to stdout (`--json`), with check ids,
   check versions and library versions.
6. **File mode.** The type is detected by suffix and header: `.aer.jsonl`, `.sem.jsonl`, `.prov.json`, `.prov.trig`.
7. **`--card CARD.md`.** Lints a corpus card with the one claims/lint library (`adapters/registry/claims.py`):
   no digits outside placeholders (H.9), the registry status phrases and the I.4 must-not-claim items, and the
   untrusted-content section (G.8.5). This replaces HL's `corpus lint-card` (AD-10 row 9).
8. **Workers (`--corpus`; D-413).**
   - Tiers `sem`, `prov` and `linkage` run in T1 `validate` jobs. `--jobs N` sets the worker count; 0 is the host
     default (N.1.10).
   - The parent reads and verifies every stored document, runs the `aer` tier with the corpus raw store, and hands each
     job the exact verified bytes by digest from a private scratch store. The job reaches nothing else (G.4.5).
   - Rows are recorded in index order. The report is byte-identical to the in-process path's, with the same exit code.
   - `--in-process` runs every tier in the CLI process. It is the AD-10 row 17 option, allowed with `--release` (G.4.9).
   - A job that is stopped (`worker.limit.*`) or crashes fails its row with the check id `validate.worker`. The limit
     code goes to a report notice, and the run exits 1.
9. **Round-trip cache (`--corpus`; D-550).** The tier-4 PROV-O round trip (the `pv.roundtrip.*` checks, E.5.5) of a
   document is kept under `$AGENTPROV_HOME/cache/tier4`, keyed by the PROV document's sha256 and the context that
   decides its outcome: the `agentprov` source digest, the round-trip libraries' versions and file digests, the Python
   build and the round-trip options. A later validation of the same bytes in the same context reuses the outcome
   instead of round-tripping again. Every other check runs. The report, the rows and the exit code are the same with
   the cache off, cold or warm.
   - The parent does every cache read and write. A job gets the parent's entry for its document as an input and uses
     it only for those exact bytes (G.4.5). A job returns a completed round trip in a second frame, which the parent
     stores.
   - Only a completed round trip is kept: never a `skipped` check or a `pv.roundtrip.load` failure.
   - A corrupt, partial or foreign entry is a miss and is removed. The cache's size is bounded, and the least recently
     used entries are evicted.
   - `--no-validation-cache` turns it off. `--release` never reads an entry. It recomputes every round trip, compares it
     with the entry it finds (the counts are reported on stderr, and a mismatch is an error message), and stores the
     fresh outcome. The cache's counters are diagnostics on stderr, never in the report.

Exit 0 when all checks pass; 1 on any failure or a strict skip; 2–3 as N.1.3. The printed summary line names every
requested tier that did not run, with its reason, as "skipped, not passed", and under `--strict` or `--release` says
that the skip fails the run, so an exit 1 with "0 failed" executions is explained on the same line. Byte-identity of
the compat graphs over the baseline trees is J's gate B (N.2.14), not a `validate` tier.

### N.2.6 `verify` — corpus integrity (D8 tier 5; H.5.5)

```
agentprov verify --corpus PATH [--level {checksums,chain,rederive}] [--against-pins [--allow-network]]
      [--root-digest sha256:HEX ...] [--profile-counts SOURCE --raw DIR] [--sample N --seed S] [--release] [--jobs N]
      [--in-process] [--no-validation-cache]
```

`PATH` is a corpus tree or a deposit archive. **Archive mode** verifies a deposit archive extraction-free, in T1
(G.3.5), checking member labels against the closed-world `checksums.sha256`. **Tree mode** validates every relpath
with `logical_name` and the H.1.3 grammar before opening it (R-44; AD-14).

**Levels** (H.5.5; default `chain`).

| Level | Checks |
|---|---|
| `checksums` | closed-world `checksums.sha256` |
| `chain` | plus manifest schema, content digest, recomputed digests and paths, AER seals, raw re-hash, each archive member's CRC32 (AD-12), SEM/PROV input digests, re-derived facets, and register ↔ index ↔ counts reconciliation |
| `rederive` | plus `recompute --dry-run` over the selection, including the `expand` stage, with package catalogues only (AD-14) |

**Options and rules.**

- `--against-pins` compares every `git`-origin raw object with the in-package profile pin (commit, path, blob id);
  a difference is `raw.origin.blob_mismatch` (G.5.3). It needs the cached tree listing, or the network with
  `--allow-network`.
- `--profile-counts SOURCE --raw DIR` asserts the profile's `full_scan` counts against locally fetched raw evidence
  (I.5.9 item 4; it replaces I's separate command). A count that cannot be checked is `unverified`, never passed.
- The command is read-only and needs core dependencies only.
- `--root-digest sha256:HEX` (repeatable) is a root digest published outside the corpus; each must match (tree mode)
  or match one corpus of the deposit (archive mode), else `root_digest.mismatch`. `--release` requires it in tree mode
  and in archive mode alike: a deposit manifest lies beside the archives and anchors nothing (exit 2; D-39, D-620).
  For a deposit directory it needs one per corpus: a corpus no given digest matches fails `root_digest.missing`
  (D-641). Without `--release` one digest that matches some corpus is enough, as before.
- Under `--release`, `unverified` fails and `--sample` is forbidden. Verifying a deposit archive or running
  `rederive` in release mode below CPython 3.14.8 is refused before any member is opened (exit 3; G.3.8).
- Cross-corpus collection checks are deferred (AD-10 row 6).

Exit 0 when every requested check passed; 1 otherwise.

### N.2.7 `diff` — deferred

The corpus diff and its SemVer check are deferred (AD-10 rows 1 and 10; `docs/roadmap.md`). In v0.1 a corpus version
bump is manual and recorded in `CHANGELOG.md`; `recompute` covers re-derivation checks (N.2.4). This number is kept so
that references to N.2.8 onwards stay stable.

### N.2.8 `inspect` — look at one execution, artefact or corpus

```
agentprov inspect TARGET [--corpus DIR]
      [--view {summary,records,transcript,transcript-v1,timeline,evidence,sem,prov,raw,detect}]
      [--record ID] [--bundle {core,inference,assessment,toplevel,all}] [--show-content] [--max-chars N] [--json]
```

**`TARGET`** is one of:

- an execution id (with `--corpus`);
- a path to `.aer.jsonl`, `.sem.jsonl`, PROV-JSON or TriG;
- a raw file (with `--view detect`);
- a corpus root.

**Views.**

| View | Shows |
|---|---|
| `summary` | identity, `unit`, facets, status/issues, digests |
| `records` | AER records with envelopes, for all 13 kinds; generic `activity`/`artefact` records show their declared `type`; artefact content appears only as its `$blob` reference and sha256, and is never decoded |
| `transcript` | `views.transcript` (D1) |
| `transcript-v1` | `views.transcript_v1` (AgentDojo family) |
| `timeline` | `after` edges. A missing edge prints as "order unknown", never as concurrency (D2) |
| `evidence` | per-field `ev`/`evf`, rule ids and `unk` reasons |
| `sem`, `prov` | annotations, or statements per bundle |
| `raw` | locators resolved to excerpts |
| `detect` | dialect sniff result (`SniffResult`) and key set, without mapping |

**Content** (R-42; G prevails over r1). Without `--show-content`, every view prints structure only: ids, kinds,
locators, sha256 digests, lengths, rule ids and labels from trusted grammars. Values from closed grammars are structure
too, and print as is when they fit their grammar: the evidence classes and tags (`ev`, the values of `evf`; C.6), the
unknown reasons (the values of `unk`; C.7.1) and the manifest's format ids (`formats`). A value that does not fit is
treated as content. With `--show-content`, message and tool content, payloads, raw excerpts and data-derived values
are printed through `quote_untrusted` (N.1.13).

Read-only. Exit 0, or 2 for an unknown target.

### N.2.9 `info` (alias `sources`) — registry, sources, installation

```
agentprov info [SOURCE | --source SOURCE] [--matrix | --must-not-claim] [--format {text,markdown,json}] [--json]
```

**No argument.** It prints D.3.5's rendering:

- the header line, with versions (`aer/0.1`, `sem/0.1`, `capture/0.1`, `agentprov-prov/0.1`, `apv 0.2.0`) and the
  registry date and digest;
- the registry table, per part, on the two axes of I.0.2: evidence availability, and implementation status with its
  caveat, for import and live. A one-row-per-source rendering shows the worst case with a `mixed` marker, never the
  best case (R-15). Live parts carry availability tags such as `[built]` and `[env missing]`.

It then adds an installation block:

- installed extras (`live`, `render`, `shacl`);
- `git`, `uv` (with its version; ≥ 0.12.22 recommended) and `dot` presence;
- the interpreter version and its `interpreter_advisory` (G.3.8);
- `$AGENTPROV_HOME` and the cache directory;
- each built backend environment's marker (`AGENTPROV_ENV.json`: commit, lock sha256, Python, sandbox probe).

**`--matrix`** prints the I.1.1 summary from the registry (`adapters.registry.render`). **`--must-not-claim`**
prints the I.4 items, for one source or for all. `--format` selects text, Markdown or JSON (JCS). I.5.7's per-source
card and lineage renderings are deferred with the matrix cards (AD-10 row 8; RESOLUTIONS §3.7).

**`SOURCE` / `--source`.** It prints D.3.5 rule 2:

- pins, layout and exclusions;
- identity rules;
- quirks with observed counts;
- lineage (the owner profile's `[lineage]`), licence attribution and evidence references.

It also prints the facets usable with `--select`, the profile and catalogue ids, integer versions and digests, and
the live profile's allowed and refused defences. Every data-derived string passes `escape_untrusted`.

It loads no adapter family and no benchmark (D.3.5), and uses no network. Exit 0; 2 for an unknown source; 70 when
the self-check fails.

### N.2.10 `backends` — backend environments (A1; AD-01; D.11.2; G.6.2)

```
agentprov backends build {agentdojo,autodojo,agentdyn} [--offline-check] [--allow-network] [--env-file PATH] [--dry-run]
                         [--defence-assets ID[,ID...]] [--defence-source DIR]
```

**Behaviour.**

- It needs the repository checkout, because the backend projects are not in the wheel (M.4 defines the repository
  root); outside one it exits 3.
- It builds `$AGENTPROV_HOME/envs/<backend>-<commit8>/` from `backends/<backend>/` (M.1.7 rule 2). The steps are:
  1. `uv sync --locked --no-config --project backends/<backend>` with `UV_PROJECT_ENVIRONMENT` set to that
     directory and every other resolution-, configuration- or env-file-redirecting `UV_*` variable scrubbed;
  2. NLTK provisioning (AutoDojo);
  3. the `AGENTPROV_ENV.json` marker (`commit`, `lock_sha256`, `python`, `nltk_sha256`);
  4. the `sandbox-exec` feasibility probe for real-model runs, whose result goes into the marker (AD-13(b)).

  This needs `--allow-network`.
- `--defence-assets ID[,ID...]` (D.10.11) also provisions the named registry defences: their pinned code (from the
  bare fetch cache, or with `--defence-source DIR` from a local tree that holds all of an entry's files, each accepted
  only by its sha256 and git blob id; an entry the tree lacks still comes from the fetch cache, so one build provisions
  every named entry), their pinned weights (D-672, from the fetch cache into `<env>/agentprov_defences/hf/`) and the backend's
  `defences` dependency group; the marker records them (`defence_assets`, `groups`), `--offline-check` re-verifies them.
- `--offline-check` verifies an existing build without network: marker, lock sha256, the RECORD and guarded-source
  digests, the `hello` identity, and, for AutoDojo, that the worker imports nothing from `variant_generation`.
- Resolution failure → exit 3 (`BackendUnavailable`, D.11.2). Missing `uv` → exit 3.
- Like `run`, it is a live CLI entry: it may read `.env` (`--env-file` or the repository root; G.9.2), and no value
  read from it is passed to `uv`.

`backends` has no other subcommand in 0.1.

**Implementation resolution (phase 8; code `agentprov.cli.backends`, `agentprov.cli.live.envs`, `agentprov.cli.live.sandbox`).**
1. **Environment name.** For AgentDojo (pinned by version from PyPI) `<commit8>` is the first 8 hex digits of the sha256 of
   `backends/agentdojo/uv.lock` (M.1.7 rule 2): a wheel has no commit, the lock pins every wheel by hash, and a deliberate
   re-lock yields a new directory instead of mutating the old one. The marker records `commit: null`,
   `commit8_source: "lock_sha256"` and the lock's `agentdojo` wheel hash (`lock_wheel`). For AutoDojo it is the fork
   commit (`commit8_source: "fork_commit"`), and likewise for AgentDyn, the pinned AgentDyn commit (D.11.10).
2. **Network.** Without `--allow-network` the sync runs `uv … --offline`: it builds from the uv cache and cannot touch the
   network (a missing package is `BackendUnavailable`, exit 3, with the hint). This replaces N.1.11(1)'s exit 4 for
   `backends build` without the flag: no network use is implicit either way, and offline rebuilds from the cache are the
   common development case. Dry runs never call `uv`.
3. **Command.** `uv sync --locked --no-config --no-dev --link-mode copy [--offline] --exclude-newer <project value>
   --no-build-package <each listed name> --reinstall-package agentprov-capture --reinstall-package agentprov-backend
   --project backends/<b>`; verified: `--no-config` alone fails `--locked` ("removal of global exclude newer"). `--no-dev`:
   the worker needs no test tools. `--link-mode copy`: the environment never shares inodes with the cache (uv hard-links
   on Linux by default), so its RECORD digests describe files only the build wrote. Environment of `uv`: the parent's
   minus every `UV_*` variable except `UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR`, `UV_PYTHON_BIN_DIR` (a superset of G.6.2's
   list), minus `VIRTUAL_ENV` and every secret-named variable (K.3.4), plus `UV_PROJECT_ENVIRONMENT`. `.env` is never
   read for AgentDojo (it needs no value); `--env-file` is accepted.
4. **Marker** `AGENTPROV_ENV.json` (`agentprov-backend-env/0.1`): `backend`, `status` (`building` until the end, then
   `complete`; `run` and `--offline-check` refuse anything else), `env_name`, `commit`, `commit8`, `commit8_source`,
   `lock_sha256`, `lock_wheel`, `python` (run by the built interpreter), `nltk_sha256` (`null`), `built_at`, `uv` (version,
   argv with `<home>`, offline), `t0_identity`, `hello_identity` and `hello_worker` (one `hello` to the built worker; the
   worker reads `lock_sha256` from the preliminary marker, D.10.10 item 3), `sandbox_probe`, `sandbox_status`.
5. **T0 identity** (D.10.6, M.1.7 rule 4), from files only: each of `agentdojo`, `agentprov-backend`, `agentprov-capture`
   has its RECORD digest computed and **every hashed RECORD entry verified** against the installed file (no symlinks, no
   path outside the environment); the PEP 610 source (`{"kind": "pypi"}` without `direct_url.json`); the sha256 of the
   guarded source *files* (the modules of D.10.6's guarded names, which must be listed with a hash in the RECORD); the lock
   digest. `hello.expect` carries them. `hello_ok` must equal T0 on the lock, RECORD digest, source and version, and the
   build record on the members T0 cannot compute without importing (the `inspect.getsource` digests, suite set, tool
   definitions and system prompt digests, interpreter). Any difference is `IdentityMismatch`, exit 3, and nothing runs.
   A same-user process can rewrite the environment and its marker consistently; that residual risk is G.6.6's.
6. **Sandbox probe** (G.4.10): the fixed profile of `cli.live.sandbox` with `-D` parameters; the probe runs the built
   interpreter under it with a scratch staging, T2 home, repository and home (fake credential files only), checking that
   writes inside staging and the T2 home succeed, that a write elsewhere and reads of the repository, a credential file
   and a `.env` file are denied, and that the worker module imports. `passed` only when all hold; `not_applicable` off
   macOS; `failed` with the reason otherwise (e.g. a nested sandbox). Measured 2026-10-08 on macOS 27.0.1 (M2 Max):
   `passed`.
7. **`--offline-check`** recomputes the T0 identity, compares it with the marker and the checkout's lock, and runs one
   `hello` (scratch directories under `$AGENTPROV_HOME/staging` and `t2home`, removed afterwards; nothing in the
   environment is written).
8. **AutoDojo** (phase 9; D.11.7 items 1-3). The same steps on `backends/autodojo` (environment `autodojo-aa458794`),
   plus: T0 requires the installed fork's PEP 610 `direct_url.json` to equal the pin of `[tool.uv.sources] agentdojo`
   (`{kind: git, repo, commit, subdirectory}`; else `IdentityMismatch`, exit 3) and hashes the fork-only guarded
   modules (`envs.FORK_GUARDED_MODULES`); `hello_ok.worker.backend` must be `autodojo`; NLTK `punkt_tab` is provisioned
   from the recipe `[tool.agentprov.nltk]` of `backends/autodojo/pyproject.toml` through `raw.fetch` (verified cache,
   network only with `--allow-network`, acquisition logged) as the unextracted zip `<env>/nltk_data/tokenizers/
   punkt_tab.zip`. The marker adds `fork` and `nltk` (`status` `provisioned` | `recipe_unpinned` | `not_cached`) and sets
   `nltk_sha256` (`null` unless provisioned, with a notice). `--offline-check` re-verifies the zip's digest. The
   `variant_generation` check of the behaviour list above is structural: the installed fork does not contain that
   package (tested in `backends/autodojo/tests/test_offline.py`), so there is nothing for the worker to import. Measured
   2026-10-08 on macOS 27.0.1 (M2 Max), offline from the uv cache: built, 329 RECORD entries verified, sandbox-exec probe
   `passed`, `nltk_sha256: null` (`recipe_unpinned`).

### N.2.11 `package` — seal; optionally build a deposit draft (D9; H.1.5, H.10)

```
agentprov package --corpus DIR --corpus-version X.Y.Z [--release-date YYYY-MM-DD]
      [--deposit OUT --metadata release.toml [--max-archive-bytes N] [--allow-mixed-licence-classes]] [--dry-run]
```

`package` is release mode for the interpreter guard (G.3.8).

**Seal mode** (`--corpus`).

*Preconditions* (each refuses with exit 4):

- the working corpus exists and is not partial;
- no snapshot was imported with context trees or pinned objects (D.16.14 R2, R3): the sealed
  `agentprov-corpus/0.1` snapshot cannot hold `context` or `pinned_objects`, and a re-map of the sealed corpus would
  run without those joins. Such a corpus is refused (`package.refused.context`) until corpus/0.2 carries both (NF-24;
  user decision 2026-10-21);
- every spec'd stage is complete;
- the validation stage ran strict;
- the card lint passes (N.2.5 item 7);
- `corpus.json` records no `interpreter_advisory`: a corpus built in dev mode below CPython 3.14.8 is re-imported on
  a patched interpreter first (AD-16 as ruled);
- `CHANGELOG.md` has an entry for `X.Y.Z` (manual bump; the SemVer checker is deferred, AD-10 row 10);
- the licence policy permits packaging (D.3.4; R-14): `forbidden` maps to raw policy `withhold` unless a permission
  record is supplied; `nc_partition` maps to `include` inside a separately licensed `-nc` corpus (none is built in
  v0.1, AD-10 row 22).

A live corpus (`corpus.json` `mode: live`) is refused with exit 5 (`package.unsupported.live`): this build seals
imports only. The check reads the manifest's mode, not only the rows', because a native-log live corpus (D-666, the
Inspect harness) holds `mode: import` rows whose primary artefact is the backend's native log.

*Steps.*

1. Write `DATASHEET.md`, with its untrusted-content section (G.8.5), and `CHANGELOG.md` (H.9); `rules/` (byte copies
   of the package catalogues and profiles: a record, not an authority, AD-14), `schemas/` (the three published
   schemas) and `LICENSES/`. The AD-20 layout files (`register.jsonl`, `validation/`, `derivation.json`,
   `raw/origins.jsonl`, `raw/members.jsonl`) are already in place. Compat outputs are flagged
   `apv:RegressionOracle` in the manifest and index (R-55). Lineage documents are deferred (AD-10 row 5).
2. Write `corpus.json` (`sealed: true`, `corpus_version`, content digest) and `checksums.sha256` over every file.
3. Run `verify --level chain`.
4. `atomic_swap_dir` `DIR.partial/` → `DIR/`. If `DIR` already exists, exit 4.
5. Print the root digest (H.5.4).

Failed execution rows are data ("seal, don't discard", HL R3). They are reported but do not block sealing. A
corpus-level check failure does block it (exit 1).

*Interrupted seal.* A failure that raises rolls `DIR.partial/` back to a working tree. A seal killed with no exception
(SIGKILL, the OOM killer, power loss) after step 2 writes `corpus.json` and before step 4 leaves `DIR.partial/` with a
sealed manifest. Rerunning `package` with the same inputs resumes it: the manifest must validate, name the corpus and
version asked for, recompute its content digest and record the supplied spec, card, changes and release arguments; the
missing parts of step 2 are finished, the checksums and step 3 must pass, and step 4 swaps the tree. If a check fails,
`package` refuses with `corpus.seal.interrupted` (exit 4) and names the state; the working files were rewritten, so
the recovery is a rerun with the original inputs or a rebuilt working corpus.

**Deposit mode** (`--deposit`). Only for sealed corpora that pass `verify --level chain` under strict validation.

- Corpora marked `synthetic`, or holding `test_only` sessions, are refused (exit 4).
- The builder refuses unless `release-scan.json` exists for the same root digest with every finding triaged and none
  `real` outside `WITHHELD.json` (G.9.4).
- It builds deterministic sharded archives and metadata (H.10.3–H.10.5), grouped by licence class (spdx, sorted
  restrictions). A deposit that mixes licence classes is refused (exit 4) unless `--allow-mixed-licence-classes` is
  given; the flag is recorded in the deposit metadata (`deposit-metadata.json`) and in the deposit's datasheet
  (`DATASHEET-<corpus_id>.md`, H.10.3), never by modifying the sealed corpus (AD-20(b); AD-SW12).
- `release` has no network code. The command ends with "nothing has been uploaded or published" (D9). The optional
  draft-only upload helper is the `agentprov-zenodo` distribution (`python -I -m agentprov_zenodo`, or
  `tools/zenodo_draft.py` in a checkout; H.10.1(2), D-790, D-880): not part of the `agentprov` package, not a
  subcommand of `agentprov`, standard library only for the network, run by the user in a terminal (their own, or the
  GUI's pseudo-terminal pane, where they type every phrase) after `package --deposit`.
  Nothing is deposited without the user's explicit instruction (Addendum B-2).

Collection manifests are deferred (AD-10 row 6).

Counters: `executions`, `failed_rows`, `files`, `bytes`. Exit 0, 1 or 2–4.

### N.2.12 `stats` — minimal, generic statistics (AD-10 as ruled)

```
agentprov stats --corpus DIR [--corpus DIR …] [--tables counts,statements,unknowns,field_groups]
      [--prov-spec SPEC] [--select K=V…] [--format {text,csv,json,markdown}] [--out PATH]
```

Addendum B keeps this command because the paper needs its tables. It is stdlib-only and works with core dependencies
alone (`src/agentprov/stats/`).

**Inputs** (G.8.6). The corpus index, register, `validation/`, SEM and PROV files, read in T0 through
`strict_json_loads`/`iter_jsonl` under `IngestLimits`. No raw artefact is read. A corpus is opened with
`verify="checksums"`; an unsealed or unverified corpus gets a notice recommending `verify`.

**Tables.**

| Table | Content |
|---|---|
| `counts` | per source and part: records by index status (`ok`, `ok_with_issues`, `failed`), by `unit` (`agent_execution`, `outcome_only`, `scenario`) and by `execution_observed` (R-28); register dispositions by code |
| `statements` | PROV statements by evidence class (`apv:Observed`, `apv:Derived`, `apv:Inferred`), by bundle (core, inference, assessment, top level) and by rule id, the generic rules G-ACT, G-USE, G-GEN and G-ASSOC included |
| `unknowns` | the proportions of the seven `unk` reasons, per field group |
| `field_groups` | the per-source information-loss table: for each field group of `stats/field_groups.toml`, the share of agent executions (`unit == agent_execution ∧ execution_observed`) in which the group is O or D, i.e. field-group coverage (R-57). The observed share is reported only as composition |

**Rules.**

- Rates are never pooled across corpora: each table is computed per corpus and labelled with `corpus_id` and its root
  digest (sealed) or content digest (working) [manuscript/figure_pipeline.md §7.1(3)]. A manifest `corpus_id` outside
  the corpus id grammar (H.1.1(3), at most 64 characters) or a recorded `content_digest` that is not
  `sha256:<64 hex>` is not a label: it is dropped with a notice, since a self-consistent sealed corpus passes `checksums`
  with either. The `text` and `csv` labels still pass `escape_untrusted_line` (one line, no raw control character).
- Output is deterministic: sorted rows, no wall-clock values; `json` is JCS. It goes to stdout, or to `--out PATH`
  outside every corpus (G8).
- Only aggregates are printed. Source ids, rule ids, evidence classes and `apv:` statuses come from closed
  vocabularies; any other label passes `escape_untrusted` (G.8.6).
- Per-source rows carry the registry status phrases of the claims library (I.5.1); the figure pipeline calls
  `check_claim` on every value it turns into a macro (I.5.6).

The r1 frame set (Parquet), the `views/stats/` DAG node and the ML export stay deferred (AD-10 rows 1, 12).

Exit 0; 1 when a corpus fails the `checksums` check; 2 for usage.

### N.2.13 `render` — PROV graph renders (AD-10 as ruled; `render` extra and Graphviz `dot`)

```
agentprov render --corpus DIR [--ex ID…] [--select K=V…] [--bundle {core,all}] [--show-content]
      [--format svg,png,pdf] [--direction {LR,TB}] [--out DIR] [--limit N] [--max-edges N] [--jobs N] [--dry-run]
```

- **Port.** The baseline's `render_prov_graph` (`agentdojo_prov/visualize.py:115-185`: `prov.dot.prov_to_dot`, then
  pydot post-processing), ported to read bundled `agentprov-prov/0.1` PROV-JSON. `--bundle core` (the default) draws
  the core bundle; `--bundle all` also draws the inference and assessment bundles, each node marked with its bundle.
- **Input spec.** In v0.1 `render` reads only `agentprov-prov/0.1` bundles; there is no `--prov-spec` option (AD-10;
  AD-SW18). `adprov-v2.3-compat` graphs are not rendered.
- **Labels** (G.8.6). By default a node label is its local id, its PROV type and its rule id, all from trusted
  grammars. Data-derived strings appear only with `--show-content`, after `escape_untrusted` and DOT string
  escaping; HTML-like labels are never built from data, and no `URL`, `href`, `tooltip`, `image` or `shapefile`
  attribute is set from data.
- **Integrity.** Unknown integrity is never styled as trusted [audit/corpus.md §5(4)]. The baseline's integrity and
  role colours (`visualize.py:70-104`) come from the assessment bundle, so they are drawn only with `--bundle all`.
- **Process.** `pydot` builds the DOT text only. `dot -T<svg|png|pdf>` is resolved with `shutil.which` and run with
  the DOT text on stdin, a minimal environment, an empty temporary cwd, `start_new_session`, a 120 s wall timeout and
  a 64 MiB output cap; files are written atomically (the baseline's `_write_with_dot`, `visualize.py:187-206`). PDF
  comes from `dot -Tpdf`; the baseline's EPS and `epstopdf` fallback (`visualize.py:208-231`) is not ported, because
  `dot` is the only process `render` may start.
- **Layout limit.** `dot` time grows sharply with the edges of a `--bundle all` graph. With edge labels, 715 edges
  took 29 s, 983 took 114 s and 1,714 more than 320 s (GUI research §M7b). So an image is laid out only for a graph of
  at most `--max-edges` edges (default 800; 0 = no limit, and the timeout still applies). Above the limit the `.dot`
  text is written, `dot` is not started, and the execution fails with `render.graph_too_large` (exit 1, the others
  still rendered). A dry run reports it too. One message names the remedies: `--bundle core`, an offline layout of the
  `.dot`, or a higher `--max-edges`. `--format dot` alone lays nothing out, so the limit does not apply.
- **Output.** Defaults to `<corpus>-rendered/<spec_dir>/<ss>/<ex>.<fmt>` (G8), keeping the baseline's render-path
  rule [audit/corpus.md §8 invariant 5]; never inside a corpus, nor inside its twin: the final `C` that a working
  `C.partial` is sealed into, or an existing `C.partial` beside `C` (exit 4, `render.output_in_corpus`). `<corpus>` is the name of the resolved corpus path (so
  `--corpus .` or `C/sub/..` names `C`); a corpus at the filesystem root has no default and needs `--out` (exit 2,
  `render.output_required`). The DOT text is deterministic; image bytes depend on
  the Graphviz version, which the summary records.
- **Errors.** A missing `render` extra exits 3 with the hint `uv sync --extra render`; a missing `dot` exits 3.

> **Implementation note (`render`, as built).** The command is `src/agentprov/cli/render.py` over `src/agentprov/render/`
> (`errors`, `style`, `graph`, `dot`, `source`, `output`).
>
> - **On demand.** One of `--ex ID…`, `--select KEY=VALUE[,VALUE…]`, `--limit N` or `--all` is required; there is no default
>   selection, so a bare `render --corpus DIR` cannot start thousands of Graphviz runs. `--select` takes the keys of
>   `import --select` (`SELECT_KEYS`, AER header fields) and reads line 0 of each execution's AER; `--ex` names must be in
>   the index. An execution with no `agentprov-prov/0.1` output is skipped (counted, noticed), or a failure when named
>   with `--ex`. `--limit` takes the first N in index order.
> - **Formats.** `--format` is a comma list from `svg,png,pdf,dot`; the `.dot` text is always written beside the images,
>   and `--format dot` needs `pydot` but not the Graphviz binary. `--jobs` runs that many `dot` processes at once
>   (0 = the host default worker count, `host.py`; min(4, CPUs) before 2026-10-28); output does not depend on it.
>   `--dry-run` builds the DOT text in memory and writes and runs nothing.
> - **Corpus.** `--corpus DIR` may be sealed, working, or absent with only `DIR.partial` present (an import in
>   progress); a corpus that is not sealed gets a notice. The index is read with `decode_index`, files are opened through
>   `ingest.paths`, and a recorded path is accepted only if it equals the layout's.
> - **Output.** `<out>/<spec_dir>/<ss>/<ex>.{dot,svg,png,pdf}`; the default `<out>` is `<corpus>-rendered` (the `.partial`
>   suffix dropped). The output is checked before the extras: inside the corpus, inside any directory holding a
>   `corpus.json` or `executions.jsonl`, or through a symlink into one is exit 4; a sealed ancestor raises the sealed-corpus
>   refusal. Files are written atomically and overwritten in place on a re-run.
> - **Look.** The W3C PROV notation of `prov.dot` is rebuilt directly with `pydot` (not through `prov.dot`, which sets a
>   `URL` from every identifier, forbidden by G.8.6). Evidence class is the border and line style (Observed solid and
>   thick, Derived dashed, Inferred dotted, none thin grey); bundle is the colour (inference purple, assessment brown);
>   with `--bundle all` each bundle that declares a drawn node is a cluster, `apv:subject` and `apv:object` of assessment
>   claims are drawn as dashed annotation links, and the baseline's integrity and role colours are taken from the
>   assessment mentions and `Labelled` claims (weakest integrity, sink over endorser over unknown over neutral; an
>   unlabelled node is not drawn as trusted or neutral). A relation endpoint that no drawn bundle declares is drawn as a
>   dashed grey node.
> - **Labels.** Local id, PROV types, rule id and class letter, each only if it matches its grammar (else `(id)` or
>   `(rule)`). With `--show-content`, every other attribute follows as `name: value`, through `escape_untrusted`, one line,
>   truncated at `--content-chars` (default 200). The text comes from the PROV-JSON only: message and tool text appears
>   if the corpus was derived with `emit_content` or as `apv:args`, `apv:toolName` and similar attributes; the AER is not read for it.
> - **Determinism.** Node ids are `n` plus 12 hex digits of the key's SHA-256; nodes, edges and clusters are added in
>   sorted order; the DOT text is byte-identical across runs, processes, hash seeds and `--jobs`. The summary records the
>   Graphviz version as a notice.

### N.2.14 `migrate` — baseline migration gates (J)

```
agentprov migrate {verify-baseline,gate-a,gate-b,reconcile,gate-c,gate-d,gate-e,all}
      [--scope {golden,full}] [--config migration/local.toml] [--workers N] [--release]
```

**Behaviour.** It runs `agentprov.migration.gates` exactly as J specifies (J.3.0, J.3), reading the J.2.6
environment variables or `migration/local.toml`. The sub-command spellings are J.3.0's, which bind (AD-SW3):
`verify-baseline` is G0 and `reconcile` is gate R. Reports go to `$AGENTPROV_HOME/migration/reports/<gate>/` and gate
E's semantic diff to `$AGENTPROV_HOME/migration/semdiff/`; `migrate` never writes into the checkout unless
`--reports-dir` or `--semdiff-dir` names it (a report meant to be committed is written there on purpose). The gate-order
check also reads the checkout's `migration/reports/`, so committed reports keep counting. The release gates, in
order, are G0, A (A1, A2), B, D and E (AD-07); `all` runs them in that order plus `reconcile`, and `gate-c` runs
only on request. Notable gates:

- `gate-a`: the v1 → AER → v1 view, compared as JCS (A1) and as bytes (A2), from the AER alone (AD-02);
- `gate-b` is the compat byte-identity gate (D7): the golden set (with the MIG-10 pairs, R-59) in CI, 35,691/35,691
  full (local);
- `reconcile` (gate R, `render_converted`): R1/R2 bytes on the golden converted pairs block in CI; the full
  18,027-file run is a local claim gate; R3–R5 are reported (AD-07);
- `gate-c` is a port-fidelity diagnostic, not a release gate: C1 is optional (manual dispatch, K.19.1), and C4 is
  deferred with replay;
- `gate-e` writes the semantic diff, generated from `prov/compat/semdiff-map.toml` (R-33).

**Release mode** (`--release`; AD-SW3). It sets `params.strict: true` in every report (J.3.0). Below CPython 3.14.8,
archive and compressed-stream ingestion (for example the Zenodo fallback of J.4.2) is then refused before any object
is opened (exit 3, `ingest.interpreter.unpatched`; AD-16 as ruled; Addendum C-1). Without `--release`, such a run
records `environment.interpreter_advisory`. The reports a release relies on are produced in release mode (J.2.6).

**Scope.**

- `full` needs `AGENTPROV_BASELINE_CORPUS`; otherwise exit 3.
- Only the baseline probe interpreter touches baseline code (`tools/migration/baseline_probe.py`).

**Exit status.**

| Code | When |
|---|---|
| 0 | the gate passed (J.3.0) |
| 1 | the gate failed |
| 3 | missing baseline inputs; or, with `--release`, archive or compressed-stream ingestion below CPython 3.14.8 (release-mode interpreter refusal; Addendum C-1) |
| 2, 4, 70, 130 | as N.1.3 |

### N.2.15 `purge` — remove a leaked object from a working store (R-51; G.9.6)

```
agentprov purge sha256:HEX --reason {secret,personal_data} (--corpus DIR | --cache) [--dry-run]
```

- It deletes one object from a working corpus's raw store, or from the fetch cache, and writes a tombstone record
  (digest, reason, date; never the value or any fragment of it) beside that store's origin records. HL owns the
  tombstone file name.
- D3 forbids changing bytes; it does not forbid removing a leaked credential. Executions that cite the object get the
  register code `release.withheld` and are withheld at packaging (G.9.5).
- A sealed corpus is never modified (exit 4): build a new version with the object listed in `WITHHELD.json` (G.9.5).
- Purging is irreversible. It asks for interactive confirmation; a non-interactive invocation is refused (exit 4).
  `--dry-run` prints what would be removed.

Exit 0; 2 for an unknown object; 4 as above.

### N.2.16 Implementation resolutions (phase 11, 2026-10-12)

Notes only; the synopses above stay the contract unless a note says otherwise. (Application commands outside the fifteen, `settings`
and `models`, are in N.2.17.) All fifteen commands now exist (info,
validate, import, fetch, run, backends, migrate, render, inspect, purge, stats, package, derive, recompute, verify);
`tests/cli/test_cli_contract.py` pins the set. Decisions: DECISIONS D-30 to D-49. `verify` (levels `checksums`,
`chain`, `rederive`; deposit archive mode; `--root-digest`; D-38, D-39) and `validate --corpus` (tiers aer, sem, prov,
linkage; read-only, report `agentprov-validation-report/0.1` outside the corpus) are built.

- **N.2.3 `derive`.** As built: `agentprov derive --corpus SRC [--out NEW] [--stages sem,prov,validation,views]
  [--prov-spec SPEC] [--semantics-profile ID@N] [--views VIEW] [--trig DIR] [--jobs N] [--in-process] [--link-raw]
  [--dry-run] [--no-reuse]`. It is **never in place**: output is a new corpus `NEW` (written as `NEW.partial`), and `SRC`
  (sealed, working or `.partial`) is read-only (D-30). `--trig DIR` alone writes TriG for `SRC` outside every corpus.
  `--select`/`--limit` are not built. `--prov-spec adprov-v2.3-compat` writes the regression oracle and prints the R-55
  notice (D-37); only the adprov-v1 corpus is built with it.
- **N.2.4 `recompute`.** As built: `agentprov recompute --corpus SRC (--out NEW | --dry-run) [--stages
  expand,aer,sem,prov,validation,views] [--prov-spec SPEC] [--show-diff N] [--strict] [--jobs N] [--in-process]
  [--link-raw] [--no-reuse]`. Never in place; `--out` is `NEW.partial`. Raw objects are **copied by default** and
  hard-linked with `--link-raw` (D-32, which supersedes item 6 of N.2.4); `--out` reuses unchanged outputs by
  default, `--no-reuse` forces a full recompute and `--dry-run` never reuses (D-30). A live corpus cannot be re-mapped
  (`--stages` with `expand` or `aer` exits 5; D-43). `--select` and `--sample/--seed` are not built. A corpus built
  under other declared versions is a drift report (D-430): the source profile and catalogue versions, and (P-1) the
  record format (`aer: format aer/0.1 recorded, aer/0.2 current`), the corpus format and the `apv` vocabulary its
  format records. A dry run names each as a `version drift:` notice; `--out` refuses (exit 4,
  `corpus.derive.version_drift`) before `NEW.partial` exists, with the reason in `summary.refusal`. Upgrading is a fresh
  re-import. When `--out` finishes with failures (outcome `failures`, exit 1), `NEW.partial` is kept as written: it is
  never the source, and it holds the failing executions' rows for inspection. Do not seal it: re-run the recompute
  clean first (P-4; `package` does not check how a working corpus was produced).
- **N.2.8 `inspect`.** As built: `agentprov inspect TARGET [--corpus DIR] [--view V] [--record ID] [--bundle B]
  [--max-chars N] [--format {text,json}]`, with the global `--show-content` and `--json`. Views and `TARGET` kinds are as
  specified; without `--show-content` only structure is printed, and with it content passes `quote_untrusted`.
- **N.2.11 `package`.** `--corpus-version` is **seal-mode only** (the deposit takes each sealed corpus's version).
  Seal mode adds `--spec PATH` (the corpus spec, CARD.md and CHANGES.toml beside it), `--licence-file NAME=PATH`
  (repeatable) and `--release-date` (a real calendar date; otherwise, or with a `SOURCE_DATE_EPOCH` after
  9999-12-31T23:59:59Z, exit 2; a `SOURCE_DATE_EPOCH` that is not ASCII digits is ignored). Deposit mode: `--deposit OUT --corpus DIR (repeatable) [--metadata release.toml]
  [--max-archive-bytes N] [--allow-mixed-licence-classes]`; `--max-archive-bytes` defaults to and is capped at
  `2**31 - 1` (no ZIP64; H.10.4). An `-nc` class is never mixed, even with the override (D-42). A corpus with a `views/`
  tree exits 5. Seal and deposit both run `verify --level chain` (release mode) before writing; deposits are verified in archive mode
  without extraction (`verify --corpus DEPOSIT_DIR`, D-38).
- **N.2.12 `stats`.** As built: `agentprov stats --corpus DIR (repeatable) [--tables counts,statements,unknowns,field_groups]
  [--artefacts] [--per-execution] [--prov-spec {agentprov-prov/0.1,adprov-v2.3-compat}] [--select K=V[,V...]] [--format
  {text,csv,json,markdown}] [--out PATH]`. `--per-execution` requires the statements table. `--select` keys are the index
  members `source_id, profile, unit, status, mode, completeness, execution_observed, adapter, snapshot`, `issue` (any
  of a row's issue codes), `facet.<name>`, `cell.<member>` (a known H.7.4 cell member: `suite`, `task_id`, `attack_id`,
  `attack_target_id`, `defense_id`, `model`, `repeat`…; an unknown member never matches) and `outcome.<claim>=true|false|none`
  (an `outcome` element with that SEM claim holds, does not hold, or none has a `holds`: not judged; D-706). These are the
  Viewer's filters (D-700). A working corpus is `verification: not_sealed`; `chain` and `rederive` raise exit 5 until U4 (D-48).
- **N.2.13 `render`.** `--all` was **removed** and `--select` requires `--limit`; a bare `render --corpus DIR` is a usage
  error. Selections: `--ex ID...`, `--limit N`, or `--select ... --limit N` (D-45; K.5.12 item 3 follows).
- **N.2.14 `migrate`.** `agentprov migrate gate-d [--scope golden|full] [--release] [--workers N] [--corpus DIR ...]
  [--limit N] [--accept-gap TREE ...] [--report PATH]` exists (also spelled `gate D`; D-49). Full scope reads stored AERs
  read-only and needs `--accept-gap converted` because no converted-tree AERs are stored.
- **N.2.15 `purge`.** As built: `agentprov purge sha256:HEX --reason {secret,personal_data} (--corpus DIR | --cache)
  [--cache-dir DIR] [--yes] [--dry-run]`. A non-interactive run needs `--yes` (exit 4 otherwise); on a terminal the command
  asks for the first eight digits. The tombstone is the JCS row `{date, reason, sha256}` in `raw/tombstones.jsonl` (the
  cache: `<cache>/tombstones.jsonl`). Counts and index issues are refreshed by `derive`/seal, not by `purge` (D-46).
  The plan lists, and leaves stored, the other objects that can hold the same bytes: the member objects of a purged
  container, the containers that hold it, and its D-315 links (the rest of a split archive; a carved blob or its source).
- **N.2.2 `import --dry-run --artefacts`** prints the per-class artefact table (D.15.4); the other import deferrals
  (AGENTS.md section 0) are unchanged.

---


### N.2.17 Application commands (reverse CLI parity, D-700; 2026-10-22)

The desktop GUI's state-changing settings and actions have CLI equivalents, which the GUI itself calls (one
implementation; user requirement 2026-10-22). They are application commands, outside the fifteen of N.2 (and outside
every stage digest: byte class 0). Each keeps its tier as explicit flags (`--yes` for removals, `--allow-network`
for fetches).

| Command | Purpose | Decision |
|---|---|---|
| `settings list\|get\|set\|unset` | the shared user settings in `$AGENTPROV_HOME/settings.json` (`agentprov-settings/0.1`), a closed schema: dev-run defaults and caps, estimate defaults, compute defaults and the job queue's budget, the default CI target, job retention, local endpoint base URLs. A corrupt file is refused (exit 2) by the commands that read it | D-703 |
| `keys status\|list\|set\|delete` | endpoint keys in the OS keychain through the keychain helper process (`agentprov.keys.helper`, the only importer of `keyring`; allowlisted back-ends only). `list` shows names and presence, never values; `set` reads the value from a no-echo prompt or one line on stdin (`--stdin`), never argv, and only for a key variable of `endpoints.toml`; `delete` needs `--yes` when not interactive. `run --keychain` reads the selected endpoint's key the same way (exclusive with `--env-file` and `--env-stdin`) | D-702 |
| `prices list\|get\|set\|unset\|refresh` | the model prices the estimate uses (`agentprov.estimate.prices`): the shipped table, the newest refreshed OpenRouter snapshot (`$AGENTPROV_HOME/prices/`) and per-model overrides (`prices/overrides.json`), resolved per endpoint of `endpoints.toml`. `refresh` fetches one public URL and needs `--allow-network` (exit 4), or imports a saved response (`--from-file`); only ids and prices are kept | D-701 |
| `jobs start\|list\|show\|follow\|stop\|kill\|drain\|resume\|prune` | detached jobs in `$AGENTPROV_HOME/jobs/<id>/` (`agentprov.jobs`): `start -- ARGV` runs `agentprov ARGV` (or `--tool tools/<name>.py` of this checkout, resolved inside `tools/`, no symlink) under a supervisor that records the real exit code; relative paths of ARGV (path options, path positionals, `inspect TARGET` when it is a path; and `--writes`/`--reads`) are made absolute against the caller's cwd first, as `batch create` does for its steps (D-704 amendment). One writer per corpus and one job per slot are refused at start (exit 4); `stop` is one SIGTERM, `kill --yes` kills the process tree after the `(pid, create_time)` identity check, `drain` writes the D-394 control file, `follow` prints the progress records (`--log`: the log records) until the job ends, `prune` lists (and with `--yes` deletes) old ended jobs beyond `--keep` (default `jobs.retention`, else 200) or `--max-age-days` (default `jobs.retention_days`, else 90). `start` gives a queued job the budget `compute.cpu_budget` / `compute.mem_gib_budget` unless the environment sets one | D-704 |
| `batch create\|start\|run\|resume\|stop\|list\|show` | ordered job lists in `$AGENTPROV_HOME/batches/<id>.json` (`agentprov.jobs.batch`), run as one driver job (`batch start` launches `batch run ID` through `jobs`). Steps are checked by the CLI's own parser at `create` and again before each starts (no job- or batch-starting step, no destructive step, no raised tier); R2 steps run only under a driver started with `--confirm-r2` (else exit 4 at `start`, `held` under a later driver); a changed checkout pin blocks the remaining steps; exit 4 or 70 blocks the rest unless `--continue-on-failure` (default: the setting `jobs.continue_on_failure`; `--no-continue-on-failure` overrides it) | D-704 |
| `devrun plan\|start\|list\|prune` | dev runs (`agentprov.devrun`): a few samples of every chosen part imported into `$AGENTPROV_HOME/dev-runs/<stamp>/` and checked as one batch (import, validate, `recompute --dry-run` per part; never `--release`, never a stored corpus). Settings are `agentprov settings` `devrun.*`; `start` needs `--confirm-r2` (the imports read the fetch cache) and prunes old runs that nothing uses | D-705 |
| `estimate SOURCE <run options>` | the cost and time of a live run before it starts: a dry plan (N.2.1 item 5) and the catalogue, cell statistics from `--stats-corpus` corpora, the shipped priors or `estimate.default.*`, priced by `prices`; p50/p90 cost and time, worst case, per suite and per attack (`--format json`: `agentprov-estimate/0.1`). Takes run's options less the run-only ones; no model call, nothing written. An Inspect plan is priced per sample × epoch, the agent's calls and the judges' calls apart, each judge at its model's price at the agent's endpoint, with D-740's bound of billed calls per sample | D-701, D-770 |
| `models [--endpoint NAME \| --base-url URL] [--model-id ID] [--allow-network \| --refresh-if-stale]` | the models a running local model server serves, and one model's observed identity (read-only, loopback or opted-in LAN; N.2.18); an API provider's dated model list, fetched with `--allow-network` (R2) or under `models.auto_refresh` (D-730..D-735); the GUI's model picker | D-691, D-730 |

### N.2.18 `models` — local model servers (D-691, D-692)

```
agentprov models [--endpoint NAME | --base-url URL] [--model-id ID] [--model-dir PATH] [--no-hash-weights]
                 [--allow-lan-endpoint] [--format {text,json}]
agentprov models [--endpoint NAME] --model-id ID --find-folders [--format {text,json}]
```

**`--find-folders` (D-828).** It lists the folders on this machine that may hold the model's files, for the user to
pick from (the GUI's Find Folder):
- oMLX's `models/` (`NAME` or `ORG/NAME`) and `gguf/` (`NAME` or `NAME-<hex>`), under `OMLX_HOME` or `~/.omlx`;
- the Hugging Face cache (`models--ORG--NAME`, its `refs/main` snapshot);
- LM Studio's models folder.

A `:suffix` (an oMLX context alias or an Ollama tag) is not part of a folder name. Only directory listings are made:
no server, no keychain, no file opened. Ids are compared as names and never joined into paths, and path-like ids
find nothing. The output is `agentprov-model-folders/0.1` (`folders[{path, source}]`, and the folder the setting
names).

Read-only; no inference and no model load; no credential. Without an option it lists every `local = true` endpoint of
`endpoints.toml` (`up`, `down` or `refused`, the server kind and version, the models). With `--endpoint` or
`--base-url` it lists one server; with `--model-id` it prints the `agentprov-local-model/0.2` identity record a live run
records (D-692; 0.2 since D-736: load and serving state is `observed_state`, outside the identity digest). `--format json` puts the document (`agentprov-local-models/0.1` or `agentprov-local-model/0.2`) on
stdout; the GUI's Run live model picker reads it (D-654: the GUI calls the CLI).

Rules (G.9.2, D-697): loopback hosts only, or a literal private address with `--allow-lan-endpoint` (D-698); the
connected peer is checked (loopback, or exactly the LAN address); `http.client`, no proxy, no redirect, 5 s timeouts,
8 MiB bodies, strict JSON through `agentprov.ingest`. Files are found in the HF cache, LM Studio's models folder or
`--model-dir`, hashed and never parsed; weight digests are cached in `$AGENTPROV_HOME/cache/model-digests.jsonl`; no
absolute path is recorded.

Exit 0; 2 usage; 3 unreachable, a malformed listing, or a model id the server does not serve (the message lists the
served ids); 4 a non-loopback URL without the opt-in, the wrong server kind, a model the server marks remote.

**API providers (D-730..D-735).** `--endpoint openrouter|anthropic|openai|deepseek|gemini|llama|qwen|glm` shows the
provider's model list (`agentprov-provider-models/0.1`) from `$AGENTPROV_HOME/models-cache/<endpoint>.json`, dated and
marked `stale` after 24 h. `--allow-network` (R2) fetches it now from the registry host only (HTTPS, TLS verified, no
proxy, no redirect, strict bounded JSON); `--refresh-if-stale` fetches only when the setting `models.auto_refresh` is
on (the user's standing consent for these free list calls, D-733) and the cache is older than 24 h. Keys for
Anthropic, OpenAI and DeepSeek: the OS keychain first (the source of truth), then the default `.env`; `--keychain`,
`--env-stdin` or `--env-file` name one source only; never argv. OpenRouter's list is public. Each model carries `price_status` (`priced` | `no_price`) from the price table (D-701), and priced models the
provider no longer lists appear under `not_listed`. A failed refresh shows the cached list with `refresh_error`; with no
cache, `source` is `none` and the list is empty. Exit 0; 2 usage; 3 a failed fetch with no cache, or a keyed provider
without its key.
## N.3 Source status gate and honest refusals

### N.3.1 Ids, aliases and statuses

**Source ids** come from the registry (D.3.3): `agentdojo`, `adprov-v1`, `rope`, `autodojo`, `agentdyn`, `drift`,
`mandate-agentdojo-eval`, `agent-security-tools-survey`, `stac`, `ciaware-bench`, `agentdojo-inspect`, `midojo`,
`adi`. A source id is the registry id; a profile id (e.g. `agentdojo-upstream`) and a corpus id are separate axes
(R-11).

**CLI aliases.** Each alias prints a one-line notice.

| Alias | Resolves to | Origin |
|---|---|---|
| `agentdojo-logs` | `agentdojo` (import) | task brief |
| `agentdojo-upstream` | `agentdojo` (import, profile `agentdojo-upstream`) | HL |
| `agentdojo-prov-v1` | `adprov-v1` | task brief |
| `multiturn-agent-attack` | `stac` | finding id |
| `inspect` | the Inspect `.eval` dialect, not a source: the registry profiles whose dialect is `inspect.eval`. In v0.1 that is `survey-agentharm` (source `agent-security-tools-survey`, part `agentharm`; corpus `ast-survey-agentharm`) | dialect alias (R-07) |

**Statuses** are D.3.2's closed set on two axes (I.0.2; R-15): evidence availability `yes | partial | no`, and
implementation status `supported | partial | planned | not_possible` with a non-empty `caveat` where required, per
part, for import and live. Parts that are not sources of their own carry a role instead (`mirror`,
`owned_elsewhere`, `compat_oracle`, `not_executions`), with `via` or `mirror_of` where they apply. The I.1.1 values
are v0.1 **targets**: the registry renders a part `supported` only after its gates pass, including a full
pinned-snapshot import with zero crashes; otherwise the part renders `partial` with the caveat "full snapshot not yet
imported" (R-15; HON-10). The registry is the only status store.

| Status (requested mode) | CLI behaviour |
|---|---|
| `supported` | proceed. A `caveat` is printed and recorded |
| `partial` | proceed. The caveat is printed and recorded in `corpus.json` and the datasheet |
| `via = X` | proceed as source `X`, with a notice |
| `planned`, `not_possible` (incl. `mirror_of`), a part role without an import, or no capability for the mode | refuse, exit 5 |

No flag overrides a refusal. A status change is a registry and profile change, never a code change.

### N.3.2 Refusal template

Written to stderr, and to `summary.refusal` with `--json`:

```
agentprov: cannot <import|run> '<id>': <status label>.
  <reason: 1 to 3 lines, from the profile/registry>
  Checked: <locations> (as of <checked_on>).
  <alternatives, one per line, if any>
  Details: agentprov info <id>
```

### N.3.3 Texts for v0.1

The texts below are generated from the registry and the profiles (R-15, R-58); they are snapshots of the I.1.1 values
as of 2026-10-07. Where they differ from the registry, the registry wins, and `tests/adapters/registry/test_status.py`
fails until this section is regenerated. Any data-derived string in them (a path, a producer version) passes
`escape_untrusted`.

**`agentprov import midojo`** exits 5 [verify/midojo.md §0]:

```
agentprov: cannot import 'midojo': not possible — no execution evidence is released.
  asago-ai/midojo publishes no per-execution trajectories. The only execution-derived records are 92
  outcome-only rows in 9 JSON files on the unmerged branch dev/attack-library: no messages, tool calls or
  tool outputs, so no AER, SEM or PROV can be derived.
  Checked: main, releases, PyPI, Hugging Face, Zenodo, arXiv, forks, sibling repositories (as of 2026-10-07).
  Live capture: planned, not available in AgentPROV 0.1.
  Details: agentprov info midojo
```

**`agentprov import adi`** exits 5 [sources/adi.finding.json `data_location`, `live_execution`]:

```
agentprov: cannot import 'adi': not possible — no execution data is released.
  compsec-snu/adi@1a3ddf8 git-ignores its run outputs (runs/, results/, *.log). The paper reports
  aggregate attack-success and utility tables only.
  Checked: GitHub repository and forks, Hugging Face, Zenodo (as of 2026-10-07).
  Live capture is planned, not available in 0.1: ADI vendors a modified agentdojo 0.1.35 that installs
  under the same name and version, so it needs an isolated environment like AutoDojo's.
  Details: agentprov info adi
```

`agentprov run adi` exits 5 with the same last two lines.

**`agentprov import ciaware-bench`** exits 5 [sources/ciaware-bench.finding.json; verify/ciaware-bench.md; I.1.1
row 14; AD-21]:

```
agentprov: cannot import 'ciaware-bench': planned, not implemented in AgentPROV 0.1.
  Its execution logs are Inspect AI .eval archives. The gated Hugging Face cohort is bound only by listing
  and hash (content unobserved; import waits until the gate is accepted and the content observed); the
  anonymous public mirror has no licence-cleared fixture; the CIABench precursor's MIT declaration is card
  metadata only and not legally settled. No part is redistributable: raw policy reference.
  Checked: JoachimSchaeffer/CIAware-Bench@a2bc2419, Hugging Face dataset cards (as of 2026-10-07).
  Details: agentprov info ciaware-bench
```

**`agentprov import inspect`** resolves to the Inspect importer (R-07; AD-06). Inspect logs of the supported
producer band are imported under `survey-agentharm`; logs of any other producer version are stored and registered as
`select.dialect_planned`, never dropped silently. While the registry still renders the `agentharm` part `planned`
(until its D.9 and DoD Q.11a gates pass), the status gate refuses with the planned text. When no input is in the
band, the command exits 5:

```
agentprov: cannot import '<path>': Inspect AI .eval producer <version> is planned, not implemented in AgentPROV 0.1.
  The v0.1 Inspect importer supports producer inspect_ai 0.3.247.dev69 only (survey AgentHarm logs).
  The files are stored and registered as select.dialect_planned.
  Details: agentprov info agent-security-tools-survey
```

**`agentprov import agentdojo-inspect`** exits 5 [sources/agentdojo-inspect.md header; D4; D.3.3 `mirror_of`]:

```
agentprov: cannot import 'agentdojo-inspect': not possible as a distinct source (mirror of 'agentdojo').
  usnistgov/agentdojo-inspect@a491020 (archived) carries AgentDojo's runs/ unchanged; NIST released no
  Inspect per-execution data. Import the runs once:
    agentprov import agentdojo --corpus <dir> ...
  Duplicates are collapsed by source_key; the mirror is recorded in the agentdojo-upstream manifest.
  Live capture via Inspect: planned.
  Details: agentprov info agentdojo-inspect
```

**`agentprov import autodojo`** proceeds through `via` [sources/autodojo.md §0; verify/autodojo.md #5; D.3.3]:

```
agentprov: 'autodojo' import is served by 'rope' (status: partial). The only released AutoDojo-attack
  runs (2,847) are hosted by ROPE (xhOwenMa/ROPE@64495e16). Importing source 'rope'; AutoDojo is recorded
  as attack provenance, and the slice is selectable with --select attack=autodojo.
```

The whole ROPE snapshot is imported, so the corpus is complete and can be packaged (N.1.7). The ROPE-corrected
outcomes and the raw `security` values stay separate (A6).

**`agentprov import stac`** exits 5 [sources/multiturn-agent-attack.finding.json; verify/multiturn-agent-attack.md;
A6; R-28]:

```
agentprov: cannot import 'stac': planned, not implemented in AgentPROV 0.1.
  Its 483 records are attack scenarios, not executions: the interaction history was scripted by the
  generator (775 of 781 assistant messages are scripted tool calls) and no outcomes are recorded. When
  imported they will be unit "scenario" records, never counted as executions. Licence CC BY-NC 4.0: any
  derived corpus is a separately licensed -nc partition.
  Checked: amazon-science/MultiTurnAgentAttack@ddeede7a (as of 2026-10-07).
  Details: agentprov info stac
```

**`agentprov run rope`** exits 5. From I.1.1, the same applies, with live `planned`, to `agentdyn`, `drift`, `stac`,
`midojo`, `adi`, `agentdojo-inspect`, `mandate-agentdojo-eval` (not v0.1), `agent-security-tools-survey` (AgentHarm,
via Inspect) and `ciaware-bench`, and, with "no live capability", to `adprov-v1` (its successor is `agentdojo` live):

```
agentprov: cannot run 'rope': live capture is planned, not available in AgentPROV 0.1.
  Its released runs can be imported: agentprov import rope --help
```

**Notices** (the command proceeds, and the notice is recorded):

- **`drift`** [sources/drift.md verdict]:

  ```
  notice: drift is partial. Stored tool outputs are the text after DRIFT's injection isolation, with no
  flag marking the edit; planner, detector and judge LLM calls are not recorded; there are no system
  prompts and no injection-payload maps.
  ```

- **`agentdojo`** (live) [I.1.1 row 1; R-25]:

  ```
  notice: partial: real-model runs are admitted for local model servers with consent, and for API endpoints
  with consent and both caps (D-720); real-model pilot 2026-10-22, working corpora, not sealed. The default
  LLM element is the stock one, recorded at the transport level.
  ```

- **`autodojo`** (live) [I.1.1 row 6; sources/autodojo.md §7]:

  ```
  notice: isolated env; partial: the subset of agentdojo · live (D-720); local real-model pilot 2026-10-22,
  not sealed. The fork transmits temperature 0.0, retries malformed tool-call JSON and scores
  error-skipped tasks security=False; these are declared as instrumentation in every execution.
  ```

---

## N.4 Worked examples (one per requested framework)

```bash
C="${AGENTPROV_HOME:-$HOME/.agentprov}/corpora"   # corpora live outside every repository and workspace (G.8.1; R-52)
BASELINE=~/Desktop/PhD/Labs/AgentDojo-PROV-framework   # read-only; never modified (J)
```

Upstream bytes come only from `--fetch` (bare, pinned, extraction-free; G.7.5) or from `--input` on a tree outside
the workspace. No example reads a working-tree clone: the investigation's clones at
`~/Desktop/PhD/Labs/AgentPROV-upstream/` are not inputs (R-52; Addendum B-2). Any `import` below can
first be run with `--dry-run`. Large downloads (Zenodo archives) need the user's consent (U-07).

**AgentDojo, live.**

```bash
agentprov info && agentprov info agentdojo
agentprov backends build agentdojo --allow-network      # once: $AGENTPROV_HOME/envs/agentdojo-<commit8>/

# Offline smoke test: scripted transport in the worker, no keys, no network (test_only; never released)
agentprov run agentdojo --plan examples/smoke/agentdojo-banking-smoke.toml \
    --llm-script examples/smoke/banking-smoke.script.json --campaign smoke --corpus "$C/agentdojo-live-smoke"

# Plan and cost check: no model call, no corpus writes. The model id comes from DEEPSEEK_MODEL in .env (no default).
agentprov run agentdojo --model deepseek --suite workspace --attack important_instructions \
    --user-tasks all --injection-tasks 0-4 --model-display-name "Deepseek Chat" \
    --containment sandbox-exec --campaign deepseek-ws --corpus "$C/agentdojo-live-deepseek-ws" --dry-run

# Execute (real model: the user's keys, consent and the AD-13(b) containment, here the probed sandbox-exec
# profile; N.1.11(3)).
# Re-issue the same command after an interruption to resume.
agentprov run agentdojo --model deepseek --suite workspace --attack important_instructions \
    --user-tasks all --injection-tasks 0-4 --model-display-name "Deepseek Chat" \
    --containment sandbox-exec --campaign deepseek-ws --corpus "$C/agentdojo-live-deepseek-ws" --jobs 6 \
    --i-consent-to-api-costs

# The baseline release grid (replaces scripts/run_full_corpus.sh)
agentprov run agentdojo --plan plans/agentdojo-v1.2.2-release.toml --model deepseek --containment sandbox-exec \
    --campaign deepseek-release --corpus "$C/agentdojo-live-deepseek-release" --jobs 18 --i-consent-to-api-costs

agentprov validate --corpus "$C/agentdojo-live-deepseek-release" --strict
agentprov stats    --corpus "$C/agentdojo-live-deepseek-release" --tables counts,statements
agentprov package  --corpus "$C/agentdojo-live-deepseek-release" --corpus-version 0.1.0
```

"Deepseek Chat" reproduces the baseline release's payload naming, for comparability. It is now an explicit,
recorded attack parameter [audit/capture.md §4.5 item 3]. No real-model run was part of v0.1's evidence (R-25; U-10); the
2026-10-22 pilot's corpora are working corpora, not sealed (D-729).

**AutoDojo, live.**

```bash
agentprov backends build autodojo --allow-network          # once; then: agentprov info shows the env marker
# The cache file comes from the pinned fork (variant_generation/variants/…), copied outside the workspace;
# it is stored as a `supporting` raw artefact with its sha256.
agentprov run autodojo --endpoint openrouter --model-id google/gemini-2.5-flash \
    --suite banking --attack autodojo --defence datafilter \
    --autodojo-cache ~/autodojo-caches/banking/google/gemini-2.5-flash/datafilter/injections.json \
    --autodojo-variant 0 --containment sandbox-exec \
    --campaign gemini-datafilter --corpus "$C/autodojo-live-gemini-datafilter" --dry-run
```

- The cache cell is one observed in the investigation [verify/autodojo.md #16].
- `datafilter` needs the environment's `filters` extra and a GPU [sources/autodojo.md §7].
- The fake-client worker test runs the same command with `--llm-script` and a committed script, and without
  `--containment` (AD-13(a)), in the `backend-autodojo` CI job (K.8.4; D.11.5).

**AgentDojo native logs** (`agentdojo`, profile `agentdojo-upstream`; alias `agentdojo-logs`).

```bash
# June-2024 logs at the `2024-06` pin: 18,241 JSON logs (the baseline's 18,234 + 7 Mixtral logs,
# [audit/legacy_replay.md §2.1]); the 207 outcome-only logs become sealed `outcome_only` records
# (seal issue no_execution_observed; R-28)
agentprov import agentdojo-logs --pin 2024-06 --snapshot 2024-06 --fetch --allow-network --corpus "$C/agentdojo-upstream"
# The same snapshot from the Drive archive the baseline README points to (a tree outside the workspace),
# anchored to the pin. The archive lacks the 7 Mixtral logs, so this snapshot records 18,234 candidates, not 18,241.
agentprov import agentdojo-logs --pin 2024-06 --snapshot 2024-06 --input ~/Downloads/agentdojo_runs/runs \
    --verify-against-pin --allow-network --corpus "$C/agentdojo-upstream"
# HEAD logs as a second snapshot of the same corpus (36,679 files)
agentprov import agentdojo-logs --pin head --snapshot head --fetch --allow-network --corpus "$C/agentdojo-upstream"
```

**AgentDojo-PROV transcript/v1** (`adprov-v1`, alias `agentdojo-prov-v1`; corpus id `agentdojo-prov-v2`, H.4.2).

```bash
agentprov import agentdojo-prov-v1 --input "$BASELINE/corpus/corpus-prov" \
    --prov-spec agentprov-prov/0.1 --prov-spec adprov-v2.3-compat --corpus "$C/agentdojo-prov-v2"
# prints the compat notice: the adprov-v2.3-compat graphs are a regression oracle (apv:RegressionOracle; R-55)
# Byte identity of compat graphs over both baseline trees: J's gate B (local, read-only on the baseline)
AGENTPROV_BASELINE_CORPUS="$BASELINE" agentprov migrate gate-b --scope full
```

The converted tree is not a source. The `2024-06` snapshot supersedes it only if the full gate-R claim gate passes
with zero mismatches; until then it stays a `compat_oracle` part (H.4.2; D.7.1; AD-07).

**ROPE** (includes the AutoDojo-attack slice).

```bash
agentprov import rope --fetch --allow-network --corpus "$C/rope"
# or a local tree outside the workspace at 64495e16, anchored to the pin:
agentprov import rope --input ~/src/rope --verify-against-pin --allow-network --corpus "$C/rope"
```

**AgentDyn.**

```bash
agentprov import agentdyn --fetch --allow-network --corpus "$C/agentdyn" --limit 50 --dry-run
agentprov import agentdyn --fetch --allow-network --corpus "$C/agentdyn"
# src/agentdojo/defenses/drift/runs/** → select.owned_elsewhere (owner: drift)
```

**DRIFT** (stretch; `partial`).

```bash
agentprov import drift --fetch --allow-network --corpus "$C/drift"
# 1,569 HEAD runs; ASB_DRIFT/logs → select.dialect_planned; history blobs (53dbc6c) are not imported in 0.1
```

**Mandate-AgentDojo-Eval.**

```bash
agentprov import mandate-agentdojo-eval --fetch --allow-network --corpus "$C/mandate-agentdojo-eval"   # 396 logs
```

**Agent Security Tools Survey** (two corpora: its own AgentDojo runs, and the AgentHarm Inspect logs as a separate
restricted-use corpus, U-05). The primary origin is the git commit `89c4db2c…`; the version DOIs are alternatives
(R-62).

```bash
agentprov import agent-security-tools-survey --profile survey-runs --fetch --allow-network --corpus "$C/ast-survey-agentdojo"
# AgentHarm: 6 Inspect .eval logs, 1,056 samples, producer inspect_ai 0.3.247.dev69 (AD-06; DoD Q.11a)
agentprov import agent-security-tools-survey --profile survey-agentharm --fetch --allow-network --corpus "$C/ast-survey-agentharm"
```

**Refusals** (exit 5; texts in N.3.3).

```bash
agentprov import midojo --corpus "$C/x" --input ~/x
agentprov import adi --corpus "$C/x" --input ~/x
agentprov import ciaware-bench --corpus "$C/x" --input ~/x
agentprov import stac --corpus "$C/x" --fetch --allow-network        # planned: scenario records, not executions
agentprov import inspect --corpus "$C/x" --input ~/x/other.eval      # exit 5 when no log is in the supported producer band
agentprov import agentdojo-inspect --corpus "$C/x" --input ~/x
agentprov run rope --corpus "$C/x" --campaign x --model deepseek --suite banking
```

**After sealing.**

```bash
agentprov verify    --corpus "$C/rope" --level chain
agentprov verify    --corpus "$C/rope" --against-pins --allow-network
agentprov recompute --corpus "$C/rope" --dry-run --show-diff 5
agentprov recompute --corpus "$C/rope" --out "$C/rope-0.2.0" \
  && agentprov package --corpus "$C/rope-0.2.0" --corpus-version 0.2.0      # after a CHANGELOG.md entry for 0.2.0
agentprov inspect ex_… --corpus "$C/rope" --view evidence
agentprov derive  --corpus "$C/rope" --select attack=autodojo --trig ~/rope-trig      # TriG on demand, outside the corpus
agentprov render  --corpus "$C/rope" --select attack=autodojo --limit 20             # needs the render extra and dot
agentprov stats   --corpus "$C/agentdojo-upstream" --corpus "$C/ast-survey-agentharm" \
    --tables field_groups --format csv --out ~/paper-data/field-groups.csv          # one table per corpus, never pooled
agentprov package --deposit ~/deposits/rope --metadata release.toml --release-date 2026-11-01 --corpus "$C/rope"
agentprov verify  --corpus ~/deposits/rope/<archive>.zip --level checksums          # archive mode, extraction-free
```

---

## N.5 Reconciliation with commands and codes named elsewhere

This table records history: the "There" column lists forms that other sections used in r1; the "Here" column is
binding (RESOLUTIONS §3.7, amended by Addendum B).

| Named in | There | Here |
|---|---|---|
| HL H.8.5 | `agentprov corpus build SPEC --out DIR [--release …]` | `import --spec SPEC --corpus DIR` (live: `run --spec`), then `package --corpus DIR --corpus-version V [--release-date D]` |
| HL H.8.5 | `agentprov corpus verify ROOT --level …` | `verify --corpus ROOT --level …` |
| HL H.8.5 | `agentprov corpus rederive ROOT --out NEW` | `recompute --corpus ROOT --out NEW` |
| HL H.8.5 | `agentprov corpus diff OLD NEW […]` | deferred (AD-10 rows 1, 10; N.2.7) |
| HL H.4.3 | `agentprov raw fetch ROOT --only sha256:…` | `fetch --corpus ROOT --only sha256:…`. `REFERENCES.json` stores no command string; the help text is generated at display time (R-43) |
| HL H.8.5 | `agentprov collection build ROOT… --out DIR` | deferred (AD-10 row 6) |
| HL H.10.2 | `agentprov release build …` | `package --deposit OUT --metadata … --release-date … --corpus …` |
| HL H.9 | `agentprov corpus lint-card CARD.md` | `validate --card CARD.md` |
| I.5.7, I.5.9 | `info --matrix`, `info <source> --must-not-claim`; `info <source> --card`, `info --lineage`; a separate profile-count command | `info --matrix`, `info [SOURCE] --must-not-claim`; `--card` and `--lineage` deferred (AD-10 row 8); `verify --profile-counts SOURCE --raw DIR` |
| D.3.5 | `agentprov info`, `agentprov info --source <id>` | adopted; also `info <id>` and alias `sources` |
| D.11.2 | `agentprov backends build autodojo [--offline-check]` | `backends build {agentdojo,autodojo}` (N.2.10) |
| D.11.6 | `agentprov run --i-consent-to-api-costs` | adopted (N.1.11(3)); an interactive prompt suffices on a TTY |
| D.3.5 / D.2.9 | exit 2 on profile or registry error | exit 70 (defect of the installed package, not of the invocation) |
| r1 MN N.2.1 | AgentDojo run in the CLI process | every `run` spawns the backend worker (AD-01(c)) |
| r1 MN N.2.3 | `derive` with outcome replay | deferred (AD-10 row 2) |
| RESOLUTIONS §3.7 | `stats`, `render` deferred | kept (Addendum B, AD-10 as ruled; N.2.12, N.2.13) |
| G.3.8 (r1 proposal) | an override flag for unpatched interpreters | none (AD-16 as ruled) |
| J.3.0 | `agentprov migrate {…}` | adopted with J.3.0's spellings (N.2.14; AD-SW3), plus `--release` |
| B.11 | `agentprov compat verify --corpus <path>` | `migrate gate-b` |
| B.11 | `agentprov corpus rederive --dry-run` | `recompute --corpus … --dry-run` |
| B CAP-05, PRJ-01, COR-07 | `run --dry-run`, `run --plan`, `corpus package` | `run SOURCE … --dry-run`, `run agentdojo --plan …`, `package` |
| K.15 | exit 3 = environment | adopted |
| HL H.8.5 | exit 2 = usage or environment | split into 2 and 3 |
| Previous plan §11 | `agentprov convert <bench> --input …`; `agentprov info --benchmark …` | `convert` aliases `import`; `info SOURCE` |

---

## N.6 Acceptance checks for this section (owned by the K suites in brackets)

1. **Contract** [tests/cli]:
   - every `--help` exits 0;
   - `build_parser()` has exactly the 15 commands of N.2 (the 13 of RESOLUTIONS §3.7 plus `stats` and `render`)
     plus the aliases `convert` and `sources`; no deferred command (`diff`) and no `--allow-unpatched-interpreter`
     flag exist;
   - every N.2 option exists, with its stated default;
   - `allow_abbrev` is off everywhere;
   - `--json` validates against `tests/cli/schemas/cli-summary-0.1.schema.json` and is byte-stable across two runs.
2. **Exit codes** [tests/cli]: one test per code in N.1.3, plus the precedence rules.
3. **Dry run** [tests/cli, `testing.fs_guard`]: every command that accepts `--dry-run` leaves the corpus root, the
   cache and `$HOME` unchanged and opens no socket. `import --dry-run` reports the same dispositions as the real
   import on the fixture set.
4. **Limit** [tests/cli]:
   - `--limit 0` processes nothing and still runs the pre-flight checks;
   - `--limit N --jobs 4` maps exactly N units;
   - failed units do not consume the limit;
   - `package` refuses a limited working corpus.
5. **Resume and idempotence** [tests/reproducibility]:
   - an import killed after k units completes on the next run;
   - running `import` and `package` again yields a byte-identical sealed tree.
6. **Guards** [tests/security, tests/cli]:
   - each of G1–G9 has a test in which it refuses;
   - for G2, the input tree's `fs_guard` snapshot is unchanged after a real import.
7. **Refusals** [tests/adapters/registry/test_status.py]:
   - every `planned`, `not_possible`, role-only or no-capability case exits 5 with the registry text, and the N.3.3
     texts equal what the registry generates;
   - aliases resolve as in N.3.1; `import stac` exits 5; `import inspect` with only out-of-band logs exits 5;
   - `import autodojo` imports `rope`;
   - no flag bypasses a refusal.
8. **Layering** [tests/boundary]: the four M.5.5 tests (static, dynamic, install-level, registry), including the
   process-boundary rule M.5.2(9).
9. **Packaging** [tests/repo]:
   - `uv build` produces a wheel that contains every M.1.3 data file and contains no `tests/`, `tools/`,
     `migration/`, `capture/` or `backends/` tree;
   - in a fresh core-only virtual environment, `agentprov --version`, `agentprov info` and `agentprov stats` on a
     fixture corpus exit 0, and `agentprov render` exits 3 with the extra hint.
10. **Secrets** [tests/security; SEC-25]: sentinel `.env` values never appear in any output byte of a
    `run --llm-script` session (summary, logs, raw, AER, manifest); `.env` is read only from `--env-file` or the
    repository root; a staged file holding the sentinel quarantines the session.
11. **Interpreter guard** [tests/security/test_interpreter_guard.py; K.12.12; SEC-26]: with a monkeypatched version
    below 3.14.8, `import --release` of a zip exits 3 before the archive is opened; dev mode warns and records
    `python_version` and `interpreter_advisory`; `package` refuses a corpus recording an advisory (exit 4); at or
    above 3.14.8 there is no warning, record or refusal.
12. **`stats`** [K.5.11]: tables are byte-identical across runs and `--jobs` values; rates are never pooled across
    corpora; no content is printed and data-derived labels are escaped; the field-group table counts only agent
    executions.
13. **`render`** [K.5.12; SEC-12]: the default DOT text carries no data-derived text; the `--show-content` DOT is
    escaped; the SVG has no script and no data-derived `href`, `URL`, `image` or `shapefile`; `dot` is the only
    process started; a missing `dot` exits 3.
14. **Content display** [SEC-12]: `inspect` without `--show-content` prints no content; exception arguments in
    tracebacks are escaped.
15. **Live spawn** [K.8; SEC-14, SEC-25]: `run --llm-script` execs `<env>/bin/python -I -B -m agentprov_backend.worker`
    with the N.1.11(4) environment, `HOME` under `t2home/` and no `uv` process; a hostile scripted worker cannot get a
    hardlinked, symlinked or `../`-labelled staged file ingested; an identity mismatch exits 3.
16. **Generic kinds** [K.5.1, K.6.4]: `inspect --view records` and `validate` handle `activity` and `artefact`
    records; on the future-framework fixture, `derive` produces named PROV statements through G-ACT, G-USE, G-GEN
    and G-ASSOC (D.12; EF).

---

## Challenges raised in this section

> **Resolved (AD-17, AD-01(d) / R-47, R-01):** the challenge to D10 (M.2) is ruled. (a) `pyyaml` is a core
> dependency, imported only by `ingest/yamlsafe.py` (AD-17). (b) The `live` extra (`python-dotenv>=1.2.2`) is
> accepted (AD-01(d)); no backend environment installs AgentPROV at all (AD-01). (c) is moot: `openai` and `httpx`
> are dependencies of `agentprov-backend`. `tenacity` stays dropped.

**No separate D9 challenge.** The corpus-layout additions the CLI relies on (`register.jsonl`, `validation/`,
`derivation.json`, `schemas/`, `raw/origins.jsonl`, `raw/members.jsonl`, `CHANGELOG.md`) were raised by HL H.1.8
(C-D9a) and accepted (AD-20). `views/stats/` is deferred (AD-10 row 12).

## Open questions

Dispositions follow RESOLUTIONS §1.3 and Addendum B.

**Q1. Tier-1 limit defaults.** **Closed** (R-63): `landscape/secure_ingestion.md` exists, and G.3.2 fixes the
defaults behind `--max-file-bytes` and `--max-json-depth`.

**Q2. STAC's status.** **Closed** (A6; R-15; R-63): import `planned`; the records are scenarios (`unit: scenario`,
R-28). The verifier reports for STAC, AgentDyn, the survey, ADI and CIAware exist; statuses follow I.1.1.

**Q3. The AutoDojo environment is untested.** Open; settled by the first `agentprov backends build autodojo`.

- Unknown: whether the fork's dependency set resolves on Python 3.12.
- Unknown: whether `json-repair` and `nltk` are needed on the benchmark path, or only by `variant_generation`.

**Q4. Ids and paths owned by several sections.** **Closed** by RESOLUTIONS §3 (R-11, R-17). HL's manifest example
uses `source_id: "agentdojo"` with `profile.id: "agentdojo-upstream"`.

**Q5. The baseline's default model ids are dropped (M.4).** **Closed:** an explicit model id is required (no silent
defaults).

**Q6. Code licence and notices.** Forwarded to the user (U-12). Default until the user decides (Addendum B-2): MIT,
with `THIRD_PARTY_NOTICES.md` carrying AgentDojo's MIT notice for AgentDojo-derived code. The verbatim June-2024
checkers (`legacy_checkers.py:1-30`), whose notice the baseline repository omits (`LICENSE`), return only with replay
(AD-10 row 2).

**Q7. Name of the agent-guidance file.** **Closed** (R-50): both `AGENTS.md` and a `CLAUDE.md` that points to it.

**Q8. `no-build` and local path builds** (new). Whether `no-build = true` also blocks building the local projects
(`agentprov`, `agentprov-capture`, `agentprov-backend`) under uv 0.12.x is unverified. If it does, the registry
packages are listed with `no-build-package` instead. The first `uv lock` (phase 2) settles it.

**Q9. uv floor** (G.11.1 row 13). **Closed** by Addendum C-1: the committed floor is `required-version =
">=0.12.18"` (the local uv), CI uses uv ≥ 0.12.22, and the release-mode interpreter refusal exits 3 (M.2 note 2). The
floor rises to `">=0.12.22"` when the user upgrades uv.

**Q10. Run-plan format id** (new). `plans/*.toml` and `run --plan` need a format id; RESOLUTIONS §3.5 lists none (r1
used `run-plan/0.1`). D, which owns the backend harness that reads plans, should register one.

**Q11. Recording dedicated-user or VM containment** (AD-13(b)). **Closed** (AD-SW13): real-model runs take
`run --containment {sandbox-exec,dedicated-user,vm}` (N.2.1, N.1.11(3)). `sandbox-exec` requires the passed probe
recorded by `backends build`; `dedicated-user` and `vm` are operator declarations recorded as
`producer.sandbox = {kind, declared_by: "operator"}` (HL H.2.7).

**Q12. `purge` tombstone file** (new; R-51). G.9.6 places the tombstone "beside the store's origin records"; the file
name is not in RESOLUTIONS §3.6. HL to add it.
