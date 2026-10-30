Revision: 2026-10-07 r2 — review resolutions and Addendum B applied.

# AgentPROV v0.1 specification — H. Corpus architecture · L. Versioning and reproducibility

| Item | Value |
|---|---|
| Date | 2026-10-07 (r2) |
| Status | REVISED after review (r2). Owner of `corpus`, `release` and the version axes (RESOLUTIONS §0) |
| Binding brief | `investigation/DECISIONS.md` — precedence **Addendum B > Addendum A > main text**; primarily D3 and D9; also D2, D4, D5, D7, D8, D10, D11, D12; `spec/review/RESOLUTIONS.md` §3 (canonical names) as ruled in Addendum B |
| Normative language | MUST / MUST NOT / SHOULD / SHOULD NOT / MAY as in RFC 2119 and RFC 8174 |
| Evidence | Investigation reports cited as `[path §n]`; baseline code cited as `file:line` at AgentDojo-PROV `579a908354b93361efe0905ffb7623256aa96a06` |

Statements marked *proposal* are design choices made in this section. Everything else is either normative
specification or a fact taken from a cited report. Where a decision in the brief looked wrong or incomplete,
this section raised a **Challenge** box and did not silently diverge. All three challenges have since been ruled;
each box is replaced by a **Resolved** note (H.1.8, H.7.7, H.10.6).

**Changes after review (2026-10-07).** Applied (RESOLUTIONS §4.7 and the findings that name this section): R-01,
R-02, R-03, R-07, R-09, R-10, R-11, R-12, R-13, R-14, R-15, R-16, R-17, R-18, R-19, R-23, R-25, R-26, R-27, R-28,
R-29, R-32, R-40, R-41, R-43, R-44, R-45, R-48, R-49, R-51, R-55, R-57, R-59, R-60, R-61, R-62, R-63, R-64, with
the Addendum B deviations: generic AER kinds `activity` and `artefact` (13 kinds; AD-15), minimal `agentprov stats` and ported
`agentprov render` as read-only consumers (AD-10), and `requires-python = ">=3.14"` with the release-mode refusal
below 3.14.8 (AD-16). Collections, the build cache, the corpus SemVer checker, stored TriG, flattened core and
lineage documents, `corpus.prov.json` and views in deposits are deferred (AD-10). Names follow RESOLUTIONS §3.

Terminology note. In this section a bare **artefact** is a *raw* artefact: a byte string in the raw store (D3). The
AER record kind `artefact` (Addendum B AD-15; an agent-produced artefact such as a screenshot, a memory entry or a
generated file) is always written in code font with the word "record" (an AER `artefact` record).

---

## 0. Summary

**Corpus (H).**

1. A **corpus** is the unit of versioning, licensing, verification and release. It has exactly one source (D9).
   One source may contribute several pinned **snapshots**: for example, AgentDojo's June-2024 `runs/` tree and its
   current HEAD. One source MAY also yield several corpora when licence classes differ (the survey's AgentHarm
   logs, H.4.2). Live campaigns are their own corpora. Collection manifests are deferred (AD-10 row 6).
2. On disk, a corpus is a manifest-first tree: `corpus.json`, `executions.jsonl`, `register.jsonl`,
   content-addressed `raw/objects/` (with `raw/origins.jsonl` and `raw/members.jsonl`), and per-execution `aer/`,
   `sem/`, `prov/<spec>/` files sharded by `sha256(ex)`. It also holds `validation/`, `rules/`, `schemas/`,
   `LICENSES/`, `DATASHEET.md`, `CHANGELOG.md`, `derivation.json` and `checksums.sha256`. No path component is taken
   from source content or source paths. Each execution is one AER (AgentPROV Execution Record, `aer/0.1`) document.
3. Every JSON artefact the corpus layer writes is deterministic. Manifests carry no wall-clock time except an
   explicit, digest-excluded `release.created`. Manifests contain no floating-point numbers.
4. The digest chain runs raw sha256 (archive members included, as derived objects of the `expand` stage, AD-12) →
   AER execution digest → SEM digest → PROV digests → index → manifest `content_digest` → `checksums.sha256` (which
   covers every file, the manifests included) → **root digest**. The root digest is published outside the archive.
5. The rule is **seal, don't discard**. Every candidate artefact either becomes an execution row (possibly
   `failed`) or gets a register entry saying why it was not imported. `register.jsonl` replaces `EXCLUDED.json`.
6. **Deduplication** uses `source_key` (artefact sha256 + in-artefact locator) and declared ownership. Identical
   bytes found at two origins are one execution with two origin records. The **logical key** links replicate
   executions of the same experimental cell. It never deduplicates.
7. **Recompute** is a content-addressed derivation check, offered as `agentprov verify --corpus ROOT --level
   {checksums,chain,rederive}` and `agentprov recompute`. It re-runs `expand`, loads profiles and catalogues only from
   the package (AD-14), and always writes to a new tree, never in place. Any output change with an unchanged
   function version fails the check.
8. Raw evidence is **included**, **referenced** or **withheld** according to the registry licence policy of each
   part (H.4). Deposits are grouped by licence class `(spdx, sorted restrictions)` and the deposit builder refuses
   mixed classes (AD-20). Unlicensed or gated data is never released.
9. The datasheet is generated. Every number in it comes from the manifest, index or register, and every
   quantified sentence passes the one claims/lint library (AD-10 row 9).
10. The deposit builder (`agentprov package --deposit`) produces deterministic, sharded deposit archives plus
    metadata files. It has no network code and never publishes.
11. `agentprov stats` and `agentprov render` (Addendum B AD-10) are **consumers**: they read a corpus, write their
    output outside it, and nothing they produce enters a corpus or a deposit in v0.1.

**Versioning (L).**

12. Eleven version axes are independent: software, `aer`, `capture`, `sem`, PROV spec, ontology, adapters, rules
    and catalogues, profiles, corpus, and benchmark/framework identity. Each is recorded in named places and has
    written bump rules. Profiles and catalogues carry monotonic integer versions (AD-18). The corpus SemVer checker
    is deferred; corpus bumps are applied by hand and recorded in `CHANGELOG.md` (AD-10 row 10).
13. **Derivation reproducibility** is a verified property. **Execution reproducibility** is never claimed. Live
    runs record the metadata needed to interpret a run and to attempt a re-run. Imports declare which of those
    items the source left unobservable.
14. The software release is tagged `v0.1.0`. Each corpus version gets the tag `corpus/<corpus_id>/v<semver>`. The
    regression baseline is pinned by full commit `579a908…`, not by the `corpus-v2.3` tag. Core requires
    `requires-python = ">=3.14"`; release mode refuses archive and compressed-stream ingestion below 3.14.8
    (Addendum B AD-16).

**Challenges raised and their rulings:** C-D2 (execution-id mapping identity, H.7.7) accepted (AD-04); C-D9a
(layout omissions, H.1.8) accepted (AD-20(a)); C-D9b (single concept DOI vs licence partitions, H.10.6) accepted in
reduced form (AD-20(b)).

---

## H.0 Terms

| Term | Definition |
|---|---|
| Source | An upstream project or capture backend, identified by its registry **`source_id`** (I.1.1), e.g. `agentdojo`, `rope`, `agent-security-tools-survey`. A source is described by one or more **source profiles** (D4). |
| `source_id` / profile id / `corpus_id` | Three distinct identifiers (R-11). For AgentDojo upstream: `source_id` = `agentdojo` (registry id), `profile.id` = `agentdojo-upstream`, `corpus_id` = `agentdojo-upstream`. |
| Snapshot | One pinned origin of a source plus a selection rule, e.g. `ethz-spylab/agentdojo@c274885…:runs/**/*.json`. Its id SHOULD equal the registry part id (I.1.1), e.g. `2024-06`, `head`. |
| Candidate | A file, an archive member, or an addressable record inside either, matched by a snapshot's selection rule. |
| Artefact (raw artefact) | A byte string stored in the raw store, addressed by its sha256 (D3). Archive members are raw artefacts too: derived objects of the `expand` stage (AD-12). Not to be confused with an AER `artefact` record (Addendum B AD-15). |
| Execution | One AER document `<ex>.aer.jsonl` (D2). Its `execution.unit` (`agent_execution` \| `outcome_only` \| `scenario`, AD-03) says whether it records an agent execution. |
| `source_key` | Identity of the evidence an execution was mapped from (H.7.1). |
| Logical key | Identity of the experimental cell an execution instantiates (H.7.4). |
| Corpus | `corpus_id` + `corpus_version`; one source; immutable once sealed. |
| Collection | Deferred (AD-10 row 6). A future manifest over several sealed corpora (H.7.5). |
| Release / deposit | The archives and metadata files produced from one or more sealed corpora of one licence class (H.10). |
| Sealed | `corpus.json` has `"sealed": true`. Every AgentPROV writer refuses to modify a sealed tree. |
| Consumer | A command that reads a corpus and writes outside it: `stats`, `render` (Addendum B AD-10), `inspect`, `verify`. |

---

## H.1 Corpus layout on disk

### H.1.1 Granularity

1. A corpus MUST have exactly one source (D9). An **import corpus** MAY contain several snapshots of that source.
   Each snapshot is pinned to an immutable origin (D3).
2. A **live corpus** holds the executions of one backend (`agentdojo`, `autodojo`) for one named campaign
   (`corpus_id` = `<backend>-live-<campaign>`, MN N.2.1). Live and imported executions MUST NOT share a corpus,
   because their raw evidence has different attesting parties (`by: capture` vs `by: source`,
   [landscape/trace_formats.md §6.2]). A live corpus whose sessions declare a `test_only` instrumentation item (a
   scripted transport) is a test corpus: it is never deposited and never licenses a "Live Capture" claim (AD-08).
3. `corpus_id` MUST match `^[a-z0-9]+(-[a-z0-9]+)*$` and be at most 64 characters. A corpus id is never reused for
   a different source.
4. Rates are never pooled across corpora [manuscript/figure_pipeline.md §7.1(3)]. The collection-level
   "poolable" declaration that could relax this is deferred with collections (AD-10 row 6). One-corpus-per-source
   keeps the per-source populations the paper needs (AR-11, [manuscript/review_feedback.md §5]).

### H.1.2 Directory tree

This is the canonical tree of RESOLUTIONS §3.6 (owner HL). Everything not marked OPTIONAL or conditional is
REQUIRED (AD-20(a), H.1.8).

```
<corpus_root>/                          # directory name is informative only, e.g. agentdojo-upstream-0.1.0
  corpus.json                           # manifest (H.2)
  executions.jsonl                      # index, one row per execution (H.3)
  register.jsonl                        # issue / disposition register (H.6); may be empty, never absent
  derivation.json                       # stage definitions of the derivation DAG (H.8)
  checksums.sha256                      # every other file in the tree (H.5)
  DATASHEET.md                          # generated (H.9)
  CHANGELOG.md                          # corpus changelog, generated from rules/CHANGES.toml
  WITHHELD.json                         # present iff anything is withheld (A4; agentprov-withheld/0.1 or /0.2, G.9.5)
  LICENSES/
    DERIVED.txt                         # licence text applying to AgentPROV-derived artefacts
    <source_id>/LICENSE                 # verbatim upstream licence file(s)
    <source_id>/NOTICE.md               # generated attribution: repo, commit, copyright line, citation
  schemas/                              # the published JSON Schemas (AD-10 row 13), copied from the package
    aer-0.1.schema.json  corpus-0.1.schema.json  [capture-0.1.schema.json]   # capture: live corpora
    [withheld-0.1.schema.json]          # present iff WITHHELD.json is, in that version (H.4.5; D-230, D-312)
  rules/                                # a RECORD of what was used, not an authority (AD-14, H.5.5)
    corpus-spec.toml                    # the build input (H.1.6), verbatim
    CARD.md                             # corpus card (datasheet prose source, H.9)
    CHANGES.toml                        # changelog entries (input to CHANGELOG.md)
    <profile-id>.profile.toml           # source and semantics profiles, byte copies of package resources (D4, D6)
    <ns>.rules.toml                     # rule catalogues, byte copies (adapter, aer, corpus[, cap]) (R-09)
    prov/agentprov-prov-0.1.toml        # provenance spec rule catalogue (D7)
  raw/
    objects/<h0h1>/<sha256>.<ext>       # ALL included raw bytes: artefacts, blobs, capture logs, native logs,
                                        #   archive members (AD-12), v2.3 checksum lists (adprov corpora, R-26)
    origins.jsonl                       # one line per (object, origin)
    tombstones.jsonl                    # purged objects (G.9.6): JCS rows {sha256, reason, date}; present iff any
    members.jsonl                       # archive expansion record (AD-12): container → ordered members
    REFERENCES.json                     # referenced (not included) objects; present iff any (H.4.3)
  aer/<ss>/<ex>.aer.jsonl
  sem/<sem_profile_dir>/<ss>/<ex>.sem.jsonl
  prov/<spec_dir>/<ss>/<ex>.prov.json   # canonical PROV-JSON with bundles (D7)
  prov/adprov-v2.3-compat/<ss>/<ex>.prov.json   # compat graphs where built; flagged RegressionOracle (R-55)
  validation/
    results.jsonl                       # one row per execution: every check, version, verdict
    summary.json
  views/                                # OPTIONAL derived views, each a DAG node (H.8)
    transcript-v1/<ss>/<ex>.transcript.json      # AgentDojo-family only (D1)
```

`<ss>` is the execution shard (H.1.3), `<h0h1>` is the first two hex characters of the object's sha256, and
`<spec_dir>` / `<sem_profile_dir>` are version identifiers mapped to directory names (H.1.3).

`raw/tombstones.jsonl` is the purge tombstone file (G.9.6; R-51). `agentprov purge` writes it beside
`raw/origins.jsonl` when it deletes an object from a working corpus's raw store, and writes the same rows to
`<cache>/tombstones.jsonl` when it deletes an object from the fetch cache `<cache>` (`agentprov fetch --cache-dir`).
Each line is one JCS object `{"sha256": "sha256:<hex>", "reason": "secret" | "personal_data", "date": "YYYY-MM-DD"}`,
sorted by `sha256` (H.1.4(1)); no row contains the purged value or any fragment of it. The file exists only once an
object has been purged from that store. A sealed corpus is never purged (H.1.5(3)): a new corpus version is built
with the object withheld (H.4.5; G.9.5). As built (D-232): sealing a purged working corpus withholds every tombstoned
object and keeps `raw/tombstones.jsonl` in the sealed tree. `verify --level chain` accepts a tombstone exactly when
`WITHHELD.json` lists the object, and otherwise reports it `tombstoned` (failing release mode, H.5.5).

**Private sidecar `DIR.withheld/` (D-231).** When a seal withholds anything, the files that leave the corpus are
renamed, never deleted, into the sibling directory `DIR.withheld/` (mode 0700). It holds the files of the withheld
executions under their corpus-relative paths (`aer/`, `sem/`, `prov/`, `views/`), the stored withheld objects
(`raw/objects/`), the withheld index rows (`executions.jsonl`), their validation rows (`validation/results.jsonl`) and
a copy of `WITHHELD.json`. The sidecar is not a corpus, has no checksums, is never deposited, and is never
overwritten. Deleting it, and with it the private copies of a leaked value, is the user's decision.

Not in a v0.1 corpus (AD-10): stored TriG (`.prov.trig`; produced on demand by `agentprov derive --trig DIR`
outside the sealed tree, row 3), the flattened core `.prov-core.json` (row 4), per-execution lineage documents
`lineage/<ss>/<ex>.lineage.json` (row 5), collection manifests (row 6), `views/stats` and `corpus.prov.json`
(row 12). The output of `agentprov stats` and `agentprov render` never enters the tree (H.8.1). Live staging lives
outside every corpus, at `$AGENTPROV_HOME/staging/<session>/`; C's capture-log and blob staging sub-paths (C.11.5,
C.13) apply only there. At ingest, staged bytes become objects under `raw/objects/` like any import (A1, AD-13).

### H.1.3 File naming and sharding

1. **No source-derived names.** No path component may come from source file names, source paths, model names,
   task ids or any other content. Human-meaningful facets live only in the index (D9). This removes the
   path-arithmetic coupling found in six baseline modules [audit/corpus.md §2.2]. It also keeps untrusted names
   out of the file system.
2. **Execution shard.** `shard(ex) = sha256(ex.encode("ascii")).hexdigest()[:2]` (256 shards). With
   `layout.shard_depth = 2`, the path is `[:2]/[2:4]`. Depth 2 MUST be used above 1,000,000 executions and MAY be
   used below. *Rationale:* live ids are UUIDv7 (D2), whose leading characters are time-ordered. Sharding on the
   raw id would put a whole campaign into one directory. Hashing the id spreads both id forms evenly.
3. **Raw objects.** Every raw byte string is one content-addressed object at
   `raw/objects/<sha256[:2]>/<sha256>.<ext>`: primary artefacts, blobs, capture logs, native logs and archive
   members (AD-12; R-12). `<ext>` comes from a closed map of the media type the reader determined:
   `application/json`→`json`, JSONL→`jsonl`, `application/zip`→`zip`, `text/csv`→`csv` (stored only; CSV parsing is
   deferred, AD-10 row 16), Inspect eval archive→`eval`, otherwise `bin`. The extension is informative only. The
   address is the sha256.
4. **Version identifiers as directory names.** `dirname(v) = v.replace("/", "-").replace("@", "-")`. For example,
   `agentprov-prov/0.1` → `agentprov-prov-0.1` and the semantics profile `agentdojo.suites@1` →
   `agentdojo.suites-1` (RESOLUTIONS §3.5). The SEM path is `sem/<sem_profile_dir>/<ss>/<ex>.sem.jsonl`. The compat
   path is `prov/adprov-v2.3-compat/<ss>/<ex>.prov.json`. A flattened core, when it is built (deferred, AD-10
   row 4), takes the reserved path `prov/<spec_dir>/<ss>/<ex>.prov-core.json`.
5. Execution ids are `ex_` + 26 base32 characters (imports; `[0:26]` of the digest, AD-04, C.4) or `ex_` +
   canonical lower-case UUIDv7 text (live) (D2). Both are filename-safe. Paths MUST be ASCII, use `/` separators,
   be relative to the corpus root, and be at most 200 characters long.
6. `executions.jsonl` records each artefact's path (H.3). Validators MUST check that every recorded path equals the
   path computed from `ex` and the layout. The index is a convenience copy, not a second source of truth.

### H.1.4 Serialisation conventions (corpus layer)

1. **JSONL files** (`executions.jsonl`, `register.jsonl`, `raw/origins.jsonl`, `raw/members.jsonl`,
   `validation/results.jsonl`) hold one RFC 8785 (JCS) object per line. Lines are UTF-8 without BOM, LF-terminated,
   and sorted by the file's primary key (bytewise); `raw/members.jsonl` keeps each container's member order. An
   empty set is a 0-byte file. The file is never absent. A `raw/members.jsonl` `container` is the digest of the
   expanded object, which for an archive stored as byte parts is its split descriptor (D-244): the stored JCS bytes
   `{"archive": "zip", "format": "agentprov-split/0.1", "parts": [{"sha256": "sha256:<hex>", "size": n}, ...]}`, whose
   origin is `split` (H.2.3) and whose parts are stored objects with their own pinned origins.
2. **Single JSON documents** (`corpus.json`, `derivation.json`, `REFERENCES.json`, `WITHHELD.json`,
   `validation/summary.json`) are written with sorted keys, 2-space indentation, `ensure_ascii=False` and a final
   LF. Their *content digest* is always computed over the JCS form of the parsed object, so it is independent of
   formatting (H.5.4).
3. Corpus-layer JSON MUST NOT contain floating-point numbers. Counts are integers. Ratios are computed by
   consumers. This avoids the cross-serialiser drift the baseline recompute could not see (`True == 1 == 1.0`,
   [audit/corpus.md §3.3 R2]). Integers MUST be within ±2^53 [landscape/trace_formats.md §6.11].
4. Digests inside JSON are written `"sha256:<64 lower-case hex>"`. `checksums.sha256` uses bare hex for
   `sha256sum` compatibility (H.5.3).

### H.1.5 Immutability, sealing and writers

1. The writers (`agentprov import`, `run`, `derive`, `validate` on a working corpus) MUST write into
   `<DIR>.partial/`. `agentprov package` seals it and swaps it to `<DIR>` (`os.replace` / `atomic_swap_dir`) only after
   the manifest, validation and checksums succeed (MN N.1.5, N.2.11). This reuses the atomic build-and-swap of the
   baseline ML export [audit/corpus.md §3.5.1 rule 12]. A failure leaves no half-written corpus. This fixes the
   non-transactional recompute [audit/corpus.md §3.3 R4]. A seal killed between writing the sealed `corpus.json` and
   the swap is resumed by the next `package` run, or refused with `corpus.seal.interrupted` (MN N.2.11).
2. Every module that writes files (`agentprov.corpus.*`, `agentprov.release.*`, importers, live runners) MUST call
   `agentprov.corpus.layout.assert_writable(path)`. That function raises `SealedCorpusError` if any ancestor
   directory contains a `corpus.json` with `"sealed": true`. This replaces the name-based release-root guard
   [audit/legacy_replay.md §5].
3. A sealed corpus is never modified. Re-derivation writes a new tree (H.8.5). A correction is a new corpus version
   (H.6.1 R4).
4. The tree is closed-world. The builder MUST refuse stray files, including dotfiles such as `.DS_Store`, which sit
   unhashed inside the baseline release [baseline/BASELINE.md §8.6]. `verify` MUST fail on any file that is not
   listed in `checksums.sha256`.
5. The builder MUST refuse an output directory inside a git work tree unless the path is git-ignored
   (D9: exported corpora never in Git). Corpora are written under `$AGENTPROV_HOME` by default (MN M.1.6).
6. **Consumers never write into a corpus.** `agentprov stats` and `agentprov render` (Addendum B AD-10) open a
   corpus read-only and MUST refuse an output path inside any corpus root (exit 4). `assert_writable` (item 2) also
   guards them.

### H.1.6 Corpus spec (build input)

A corpus is built from a data-free, version-controlled spec at `corpora/<corpus_id>/corpus-spec.toml` in the
AgentPROV repository, next to `CARD.md` and `CHANGES.toml`. The builder copies all three into `rules/`. The spec is
loaded by `agentprov.corpus.spec.load_spec(path) -> CorpusSpec`.

| Key | Type | Meaning |
|---|---|---|
| `corpus_id`, `corpus_version`, `title`, `mode` | string | As in H.2 |
| `[[sources]] source_id`, `profile` | string (registry id), string `"<profile id>@<int>"` | Source profile from the package registry (D4), e.g. `source_id = "agentdojo"`, `profile = "agentdojo-upstream@1"` (R-11, AD-18) |
| `[[sources.snapshots]] snapshot_id` | string | Unique within the corpus; SHOULD equal the registry part id |
| `…origin` | inline table | Pinned origin (H.2.3). Mutable refs ("main", "latest") MUST be rejected. It MUST match an origin declared in the in-package profile (R-43) |
| `…alt_origins` | array of tables | Alternative retrieval origins, verified by sha256 |
| `…include` / `…exclude` | array of globs / array of `{glob, code, owner?}` | Selection rule; every exclusion carries a register code (H.6.3) |
| `…raw_policy` | `"include"` \| `"reference"` \| `"withhold"` | H.4; derived from the registry licence policy (H.4.1) |
| `[derive] sem_profiles`, `prov_specs`, `views` | arrays of version ids | Stages to run (H.8). `views` ⊆ `{"transcript-v1"}` in v0.1 |
| `[derive] options` | table | `context_encoding = "members"`, the only v0.1 value (D7; `collection` deferred, AD-10 row 14) |
| `[licence] derived` | SPDX id or `"inherit"` | Licence of derived artefacts, decided by the user (H.4.2) |
| `[layout] shard_depth` | 1 \| 2 | H.1.3 |
| `[live] campaign`, `run_plan` | string, path | Live corpora only (D5) |
| `[scan] personas` | array of `{path, sha256}` | Optional (D-810). Persona files, next to the spec (`path` relative to it, at most one leading `../`, a `<name>.personas.toml` file), each with the sha256 of its bytes. A persona file (`agentprov-personas/0.1`, `agentprov.corpus.personas`) holds the **digests**, never the addresses, of reviewed e-mail addresses by class (G.9.4): `upstream-data` (the default; the benchmark's fictional people, grouped by the upstream file they occur in with the source id, repository and pinned commit or DOI), `benchmark-input`, `model-generated` and `withhold` (by where the address first appears in this corpus's AER; evidence: execution, record, pointer, actor kind), `withhold-object` (only in raw objects no execution indexes; evidence: the object's sha256) and `file-name` (file-name-shaped strings, cleared as `false-positive`). A group evidenced by the corpus's own records names its `corpus_id` and applies to that corpus only. Sealing writes each to `rules/personas/<name>` after checking it against the spec's digest, and refuses one that is missing, unreferenced or invalid; the release scan (G.9.4) clears an address only through its own corpus's list, read from the sealed tree, and the spec's digest (`files.spec`) binds the list to the root digest. A spec without `[scan]` is valid and clears nothing |
| `[withhold]` | table: `decided_by` (string, at most 300 characters), `objects` (array of `"sha256:<hex>"`), `executions` (array of execution ids) | Optional (D-964; C-8). What a release-scan review decided to withhold that no source-profile rule describes, named by digest and id, never by value: each listed stored raw object is withheld alone, each listed execution with its primary object (as a derived-file hit is; used for a finding in a derived file). Reason `secret`; the rule id `secret-withheld` (kind `object`) joins the profile's `[withhold]` policy, as D-810's `email-withheld` does. At least one list, each non-empty and without duplicates; a listed object the corpus does not store, or a listed execution it does not hold, refuses the seal. Changing the table of a released corpus is a new corpus version |

### H.1.7 Legacy layouts

The AgentDojo-PROV trees (`corpus/corpus-prov/`, `corpus/corpus-og-agentdojo-runs-prov/`, `corpus/corpus-ml/`)
are read-only inputs. They are read only by the transcript/v1 importer and by the compatibility regression gate
(D7). AgentPROV MUST NOT write or reproduce their file contracts: per-model `manifest.json` with `traces[].split`,
`outcome_replay.json`, `EXCLUDED.json`, `corpus-ml/*/splits/REPORT.json` [audit/corpus.md §4]. The old manuscript
stays pinned to the frozen baseline, which provides those contracts (D12). The legacy `split` field
(`md5("suite/user_task") % 10`) is not a corpus property. Its frozen definition stays in the baseline. Splits for
new corpora are defined by an export view [audit/corpus.md §3.1.3 decision].

### H.1.8 Layout additions to D9

> **Resolved (AD-20(a) / R-12):** C-D9a is accepted and amends D9. `register.jsonl`, `validation/`,
> `derivation.json`, `schemas/`, `raw/origins.jsonl`, `raw/members.jsonl` (AD-12) and `CHANGELOG.md` are REQUIRED;
> `views/` is OPTIONAL; included and referenced raw artefacts MAY coexist in one corpus. Nothing in D9 is removed,
> but the corpus `rules/` is a record, not an authority (AD-14).

Rationale (evidence for the additions). D9's layout list omitted artefacts that the evidence requires inside the
integrity boundary:

1. **an issue register.** The baseline's `EXCLUDED.json` sat outside every checksum [audit/corpus.md §3.1.3 P3],
   and the replay audit asks for an exclusion register with hashes and reason codes
   [audit/legacy_replay.md §4, §12.1];
2. **validation results keyed by artefact digest.** The manuscript's conformance caches could predate 569
   regenerated graphs with no way to tell [manuscript/figure_pipeline.md §3.5, §7.4], and no corpus-level
   validation exists today [audit/validation.md §9, L7];
3. **a changelog inside the archive** (AR-10, REP-2/REP-3 [manuscript/review_feedback.md §1.5, §5]);
4. **the stage definitions of the derivation DAG**, the JSON Schemas and raw-origin records, without which the
   "pure function" claim cannot be checked from the artefacts alone [audit/corpus.md §3.3 R6]; the archive
   expansion record is the same requirement for member objects (AD-12).

D9 also read as if `raw/` and `raw/REFERENCES.json` were mutually exclusive. DRIFT shows they are not: its HEAD
logs are MIT, while its pre-licence history blobs should only be cited [sources/drift.md §11].

---

## H.2 Corpus manifest `corpus.json`

### H.2.1 Schema and validator

1. The format id is `agentprov-corpus/0.1`. The JSON Schema (draft 2020-12) ships in the package at
   `src/agentprov/schemas/corpus-0.1.schema.json` and is copied to `<corpus>/schemas/`. It is one of the three
   published schemas (AD-10 row 13). The index row (`agentprov-index/0.1`), register entry
   (`agentprov-register/0.1`), derivation document and `raw/members.jsonl` row are `$defs` of this schema, not
   separate published files (*proposal*, consistent with row 13).
   **`agentprov-corpus/0.2`** (D-212, C.21): the same manifest with `formats.aer` = `aer/0.2`, published as
   `corpus-0.2.schema.json` beside the frozen 0.1 file (D-163); the builder generates both, and the 0.1 file is
   byte-identical. A corpus carries the schema pair of its own format (`aer-0.1`/`corpus-0.1` or
   `aer-0.2`/`corpus-0.2`) in `schemas/`. New corpora are written as 0.2; a 0.1 corpus stays readable and verifiable,
   and its re-derivations keep its format.
2. The authoritative validator is `agentprov.corpus.manifest.validate_manifest(obj: Mapping) -> list[Issue]`, as
   D2 specifies for AER. It is differentially tested against the schema with Hypothesis-generated manifests (D8
   tier 7). Every object in the schema is closed (`additionalProperties: false`), except the
   adapter-namespaced `x` facet objects.
3. Every field below is REQUIRED unless marked optional. "Computed" means the builder derives the value from AER,
   SEM, the register or the file system. It is never taken from a build constant. The baseline stamped build
   constants into manifests and datasheets: `CORPUS_VERSION`, `dataset`, `license`, `AGENTDOJO_VERSION`
   (`package.py:31-42`, `package.py:160-170`; [audit/corpus.md §3.1.3 P1, P7]).

### H.2.2 Top-level fields

| Field | Type | Source of value | Notes |
|---|---|---|---|
| `format` | const `"agentprov-corpus/0.1"` | constant | |
| `corpus_id` | string (H.1.1) | spec | |
| `corpus_version` | string, SemVer 2.0.0 | spec | Bump rules in L.1.3 |
| `title` | string, ≤ 200 chars | spec | |
| `mode` | `"import"` \| `"live"` | spec | |
| `sources` | array of `SourceEntry`, length 1 | spec + computed counts | H.2.3 |
| `framework_identities` | array of `FrameworkIdentity` | computed from AER | H.2.4 |
| `adapters` | array of `AdapterRef` | registry | H.2.5 |
| `profiles` | `{ "source": [ProfileRef], "semantics": [ProfileRef] }` | registry | H.2.5 |
| `rule_catalogues` | array of `CatalogueRef` | registry | H.2.5 |
| `formats` | `Formats` | constants of the running code | H.2.6 |
| `prov_specs` | array of string, e.g. `["agentprov-prov/0.1"]` | spec | One `prov/<spec_dir>/` per entry |
| `oracle_specs` | array of `{ "spec": string, "status": "apv:RegressionOracle", "gate_report": "sha256:…" \| null }` | spec + gate reports | Every entry of `prov_specs` that is a frozen regression oracle; in v0.1 only `adprov-v2.3-compat` (R-55). Empty when none. The CLI prints a notice whenever such output is written or loaded |
| `ontology` | `{ "prefix": "apv", "iri": string, "version": "0.1.0" }` | package | D7; `owl:versionInfo "0.1.0"` (RESOLUTIONS §3.5) |
| `producer` | `Producer` | runtime | H.2.7 |
| `live` | `LiveBlock` \| `null` | capture logs | `null` for imports. For live corpora: backend id, session ids, LLM element (`native` default or `gateway_compat` opt-in, AD-09), the instrumentation items declared per session, per-execution resample/retry counts summed, and `test_only: bool` (H.1.1(2)). With D-664 the working manifest's live block also carries `egress`: the T0 egress proxy's summary, `{kind: "connect_proxy", allow, tunnels, forwards, refused, refused_targets_distinct, refused_targets_capped}` (counts per allowed pair and per closed refusal kind, never a string the worker chose; DECISIONS D-664, G.4.10), or `null` when no proxy ran. Like the run's other live bookkeeping (`quality`, `attack_caches`), it is not yet a member of the closed published `LiveBlock` shape (`corpus/manifest.py`); test-only live corpora are never deposited |
| `models` | array of `ModelSummary` | computed from AER `actor` records | H.2.8 |
| `counts` | `Counts` | computed | H.2.9 |
| `duplicates` | `DuplicateSummary` | computed | H.7 |
| `licences` | `Licences` | profile + spec | H.2.10 |
| `facet_schema` | array of `FacetDecl` | profile + core | H.3.3 |
| `files` | map role → `FileRef` | computed | H.2.11 |
| `digests` | `Digests` | computed | H.2.11 |
| `validation` | `ValidationSummary` | computed | H.2.12 |
| `datasheet` | `{ "card_sha256": string, "claims": [{ "id": string, "holds": boolean }] }` | computed | H.9 |
| `content_digest` | `"sha256:<hex>"` | computed | H.5.4 |
| `release` | `Release` | build arguments | H.2.13; excluded from `content_digest` |
| `sealed` | boolean | set last | excluded from `content_digest` |

### H.2.3 `SourceEntry`, `Snapshot` and `Origin`

`SourceEntry`:

| Field | Type | Notes |
|---|---|---|
| `source_id` | string | The registry source id (e.g. `agentdojo`), **not** the profile id (R-11) |
| `profile` | `ProfileRef` | e.g. `{id: "agentdojo-upstream", version: 1, …}` |
| `parts` | array of string | The registry part ids (I.1.1) this corpus covers, e.g. `["2024-06", "head"]` |
| `snapshots` | array of `Snapshot` (≥ 1) | |
| `lineage` | array of `LineageDecl` | Copied from the owner profile's `[lineage]`, where lineage is declared once (R-45; H.7.5) |
| `mirrors` | array of `Origin` | Known byte-identical mirrors that are not imported (e.g. AgentDojo-Inspect, H.7.6) |

`Snapshot`:

| Field | Type | Notes |
|---|---|---|
| `snapshot_id` | string | SHOULD equal the registry part id, e.g. `"2024-06"`, `"head"` |
| `origin` | `Origin` | Pinned. Commit SHAs MUST be the full 40 hex characters |
| `alt_origins` | array of `Origin` | Retrieval alternatives. Each artefact is verified by sha256 |
| `selection` | `{ "include": [glob], "exclude": [{ "glob": string, "code": string, "owner": OwnerRef \| null }] }` | |
| `raw_policy` | `"include"` \| `"reference"` \| `"withhold"` | H.4 |
| `counts` | `{ "candidates": int, "executions": int, "not_imported": int, "selection_excluded": { code: int } }` | MUST satisfy `candidates == executions + not_imported`. In `executions`, one execution with N origins in this snapshot counts once |
| `input` | `{ "kind": "archive", "label": string, "sha256": Digest, "bytes": int, "parts"?: [{ "file", "sha256", "bytes" }] }` | `agentprov-corpus/0.2` only (D-223), optional: the stored archive the snapshot was imported from (D-200; a split archive's byte parts in order, D-249), so a re-map re-expands it. A corpus/0.1 seal of such a snapshot is refused (`package.refused.archive_input`) |
| `context` | array of `{ "role": string, "origin": Origin, "verification": { "kind": "download" \| "blob", "verified": int, "unverified": 0 }, "stored": int, "input"?: … }` | `agentprov-corpus/0.2` only (D-221), optional, sorted by role: the second pinned trees of D.16.14 R2. `verification.kind`: `download` (a download pin's archive, checked by sha256 and size) or `blob` (each file's git blob id: the fetch cache or a `--context` copy checked blob by blob) (D-221 addendum; the schema holds the closed set, re-check RC-15). `origin` is built from the role's pin recorded at import, as the snapshot's own (D-33); `input` as above for an archive context pin. `package` refuses a role with no recorded pin or whose pin did not vouch for every file. A re-map matches the role's objects by this origin |
| `pinned_objects` | array of `{ "label": string, "origin": object Origin, "sha256": Digest, "bytes": int }` | `agentprov-corpus/0.2` only (D-221), optional, sorted by label: objects fetched by their own pin (D.16.14 R3, LFS objects). Each must be stored with that origin |
| `context_skipped` | array of role | `agentprov-corpus/0.2` only (D-221), optional: the context roles imported with `--no-context` (NF-29); a re-map skips them too |

A corpus/0.1 seal of a snapshot with `context` or `pinned_objects` is refused (`package.refused.context`, NF-24): the
frozen corpus-0.1 snapshot has none of these members, and a re-map of the sealed corpus would lose the `<role>:` joins.

`Origin` is a tagged union on `kind`. The kinds are those of AER artefact origins (C.3; RESOLUTIONS §3.3), so one
vocabulary serves `corpus.json` snapshots, `raw/origins.jsonl` rows and AER `artifacts[].origin`. Snapshot-level
origins name a tree; object-level origins (in `raw/origins.jsonl`) name one object.

| `kind` | Fields |
|---|---|
| `git` | `repo` (https URL), `commit` (40 hex). Snapshot level: `subtree` (path or `""`), `subtree_sha1` (optional, 40 hex). Object level: `path`, `blob_sha1`, and optional `introduced_in` (the introducing commit; source of rule `agentdojo.committed_no_later_than@1`, D.5.4) |
| `zenodo` | `doi`, `file`, `md5` (as Zenodo lists it, optional), `member_prefix` (optional), `parts` (`agentprov-corpus/0.2` only, D-217: an archive stored as byte parts, `file` its logical name and `parts` two or more `{file, bytes, sha256, md5?}` in the pin's order) |
| `hf` | `dataset`, `revision` (40 hex), `path` (optional), `gated` (bool). A snapshot imported from an archive stored as byte parts (D-249) seals with `path` = the directory holding the parts; the parts are named by their object origins in `raw/origins.jsonl`. A Zenodo snapshot of that kind cannot be sealed under `corpus-0.1` (frozen, D-163): `file` names one deposit file and the schema has no `parts`. Under `agentprov-corpus/0.2` (D-217) both kinds also list `parts`, and a Zenodo split snapshot seals as `{kind: zenodo, doi, file, parts}` |
| `url` | `url`, `retrieved_at` (RFC 3339 UTC; REQUIRED because the origin is mutable) |
| `corpus` | `corpus`, `version`, `producer_commit` (40 hex): a frozen corpus of another project, e.g. `{corpus: "AgentDojo-PROV", version: "2.3", producer_commit: "579a908354b93361efe0905ffb7623256aa96a06"}` (R-26) |
| `capture` | Object level: `session`. Snapshot level: `session_ids` (array of string) |
| `member` | Object level only: `container` (sha256 of the archive object, or of a split descriptor, D-244), `label`, `method`, `crc32`, `size` (AD-12). Written by the `expand` stage, never by an adapter |
| `split` | Object level only (D-249): `archive` (`zip`), `label` (the logical archive's name), `parts` (the part digests, 64 hex, in the declared order). The origin of a split descriptor; not an AER artefact origin |
| `carved` | Object level only (D-218): `from` (the 64-hex digest of the stored source object), `loc` (a key locator: `p`, optionally `line` or `bytes`), `transform` (`utf8` or `base64`). The origin of a carved blob, the exact bytes of one string value of the source (C.11.5); not an AER artefact origin. A re-map carves it again; `verify --level chain` checks that its source object is stored |
| `local` | Development only: `container` (free-text description of a local collection), `path_prefix`. Release mode refuses a corpus with a `local` origin |

A snapshot's sealed origin is built from its pin and the object-level origins of its primary objects. A `member` or
`carved` origin is followed to the object it derives from, and on up to the root of the chain, however deep the nesting
(a log in an `.eval` in a tar.zst, a nested zip or a split zip; D-380, D-381). With several snapshots (D-202) only the
roots the snapshot's pin vouched for count; for a single-file `hf` pin that means the pinned file, not just the revision.

Immutable origins (`git`, `zenodo`, `hf`, `corpus`) MUST NOT carry retrieval times. Retrieval facts (`retrieved_at`,
the fetched tree id; G.7.5) live in the local fetch log outside the corpus, so a rebuild from the same pinned origin
is byte-identical (H.2.13).

### H.2.4 `FrameworkIdentity`

The identity of a benchmark or framework consists of observed commits and digests, never version strings
(D9). AgentDyn and AutoDojo both report `agentdojo 0.1.35` ([audit/capture.md §9.6], [sources/autodojo.md §0]),
and `agentdojo_version` in transcript/v1 is ambiguous for forks [audit/capture.md §8 D9].

| Field | Type | Notes |
|---|---|---|
| `fw` | string `fw_` + 16 base32 chars | `= "fw_" + b32(sha256("aer-fw/1\n" + JCS(core)))[:16]`, where `core = {distribution, source, source_tree_sha256, suite_set}` |
| `distribution` | string \| null | As reported, e.g. `"agentdojo"` |
| `reported_version` | string \| null | Verbatim, including literals such as `"unknown"` [verify/agentdojo.md §3] |
| `source` | `Origin` \| null | Commit or wheel origin |
| `source_tree_sha256` | string \| null | Live only: digest of the installed package tree in the backend environment (L.2.2) |
| `suite_set` | string \| null | Reported or inferred label, e.g. `"v1.2.2"`, `"v1"` |
| `tool_definitions_sha256` | string \| null | JCS digest of names, descriptions and JSON schemas [audit/capture.md §9.2]; the content of the AER `tool_definitions` fixture |
| `system_prompt_sha256` | string \| null | Default system prompt digest |
| `ev` | map field → `"O"` \| `"D"` \| `"I"` | Evidence class of each non-null field |
| `executions` | int | |

### H.2.5 `AdapterRef`, `ProfileRef`, `CatalogueRef`

- `AdapterRef = { "id": string, "version": SemVer, "code_sha256": string, "dialects": [string] }`, with a dotted
  id, e.g. `{id: "agentdojo.tracelogger", version: "0.1.0", …}`; its corpus-layer citation is
  `agentdojo.tracelogger@0.1.0` (RESOLUTIONS §3.5). `code_sha256` is the sha256 of the JCS array
  `[[relpath, sha256(file)] …]` over the adapter package's source files, sorted by `relpath`
  (`agentprov.adapters.registry.code_digest(adapter_id)`). Code identity lives here, not in the AER header (RF-4);
  EF's `aprov.t_agents@1` reads it from this manifest.
- `ProfileRef = { "id": string, "version": int, "sha256": string, "path": string }`, e.g.
  `{id: "agentdojo-upstream", version: 1, path: "rules/agentdojo-upstream.profile.toml"}`; the semantics profile is
  `{id: "agentdojo.suites", version: 1, …}`. Versions are monotonic integers (AD-18).
- `CatalogueRef = { "id": "<ns>", "version": int, "sha256": string, "path": "rules/<ns>.rules.toml", "n_rules": int,
  "rules_used": [string] }`, e.g. `{id: "agentdojo", version: 1, path: "rules/agentdojo.rules.toml", …}`.
  `rules_used` lists every rule id `<ns>.<rule>@<n>` (the rule reference without its `#…` scope, C.6.4) that
  appears in this corpus's AER, SEM or PROV, including EF's generic rules G-ACT, G-USE, G-GEN and G-ASSOC whenever
  the corpus holds `activity` or `artefact` records (Addendum B AD-15).

The `rules/` files are byte copies of package resources and form a **record**: `recompute` and
`verify --level rederive` load profiles and catalogues only from the installed package at the recorded version,
and compare digests with `rules/**` (AD-14; H.5.5). A release-mode build MUST fail if two versions of the same
adapter, profile or catalogue contributed to one corpus version.

### H.2.6 `Formats`

`{ "corpus": "agentprov-corpus/0.1", "index": "agentprov-index/0.1", "register": "agentprov-register/0.1",
"aer": "aer/0.1", "sem": "sem/0.1" | null, "capture": "capture/0.1" | null }`. `capture` is non-null only for live
corpora. In `agentprov-corpus/0.2` `corpus` and `aer` are `agentprov-corpus/0.2` and `aer/0.2` (H.2.1).

### H.2.7 `Producer`

| Field | Type | Notes |
|---|---|---|
| `agentprov_version` | string | `importlib.metadata.version("agentprov")` |
| `git_commit` | string, 40 hex | Release mode MUST refuse to run from an unknown or dirty tree |
| `git_tree_clean` | boolean | MUST be `true` in release mode |
| `build_steps` | array of `BuildStep`, oldest first; optional | **D-780** (`agentprov-corpus/0.2` only; `agentprov-corpus/0.1` is frozen and has no such key). One record per process that built part of the corpus, copied from the working manifest at sealing (sealing is not a build step). See below |
| `python` | `{ "implementation": string, "version": string }` | The core interpreter (`requires-python = ">=3.14"`, AD-16); `version` is the `python_version` that AD-16 requires to be recorded |
| `interpreter_advisory` | `{ "floor": "3.14.8", "python_version": string, "missing": [string] }` \| null | The record of `agentprov.envinfo.interpreter_advisory()` (G.3.8). Written in dev mode when archive or compressed-stream ingestion ran below 3.14.8 (register code `ingest.interpreter.unpatched`). Release mode refuses that ingestion below 3.14.8 (exit 3), and `package` refuses a corpus that carries an advisory, so a released corpus always has `null` here (Addendum B AD-16) |
| `platform` | `{ "system": string, "release": string, "machine": string }` | `$HOME` and the host name never appear (R-51) |
| `lockfile_sha256` | string \| null | sha256 of the core `uv.lock` used. `null` only with `lockfile_absent_reason`. Live corpora also record each backend project's `uv.lock` digest in `live` (L.2.2) |
| `distributions_sha256` | string | sha256 of the sorted `name==version\n` lines of all installed distributions |
| `key_distributions` | map name → version | At least `prov`, `rdflib`, `rfc8785`, `pyyaml`, `agentprov-capture`, plus every serialiser or validator library used (`pyshacl` when used) |
| `zlib_version` | string | Archive determinism depends on it (H.10.4) |
| `isolation` | `"t1"` \| `"in-process"` | Where the `expand` and `map` jobs ran (A3; G.4): `"t1"` in T1 workers (`python -I -B -m agentprov.worker`, protocol `agentprov-job/0.1`); `"in-process"` in the CLI process under the `--in-process` debugging mode, which `--release` refuses (exit 4) (G.4.9) |
| `sandbox` | `null` \| `{ "kind": "sandbox_exec" \| "dedicated_user" \| "vm", "declared_by": "probe" \| "operator", "profile_sha256"?: string }` | Live corpora: the AD-13(b) containment of the backend worker in a real-model run (G.4.10), chosen with `run --containment sandbox-exec\|dedicated-user\|vm` (MN N.2.1, N.1.11(3)). `sandbox_exec` has `declared_by: "probe"`, requires the passed feasibility probe recorded by `backends build`, and carries `profile_sha256` (`"sha256:<hex>"`, the digest of the `sandbox-exec` profile used); `dedicated_user` and `vm` are operator declarations (`declared_by: "operator"`, no `profile_sha256`). `null` for imports and for fake-client live runs (AD-13(a)); a real-model run without containment is refused (exit 4) |

**Working manifests and the building commit (D-780).** A working `corpus.json` written by `import`, `run`, `derive` or
`recompute --out` records, in `producer`, `git_commit` and `git_tree_clean` of the AgentPROV checkout that wrote it, or
`git_commit_absent_reason` (`not_a_source_checkout`, `git_unavailable` or `git_failed`) when the code does not run from a
git checkout; never a placeholder commit. In a sealed manifest `git_commit` and `git_tree_clean` stay the **sealing**
process's (above). A `BuildStep` is `{agentprov_version, command: import|run|derive|recompute, stages, git_commit +
git_tree_clean | git_commit_absent_reason + distributions_sha256}`. `stages` lists, sorted, only the stages that
process wrote, by the names of `derivation.json`: the writer's own record for an import or live run, the stages a
derivation recomputes (not the layers it copies) for `derive` and `recompute`. A derivation carries its source's
`build_steps` and appends its own, so an import and a later derive are two steps and the commit of each stage is
recoverable; a source without `build_steps` is carried as none. The CLI computes the facts (`corpus/` runs no
subprocess): from the agentprov source root, never the working directory, only when git's top level is that root,
with no environment override. `package` in release mode refuses a corpus with a step whose `git_tree_clean` is `false`
(`package.refused.build_dirty`); an absent reason is not refused, and the datasheet shows it with the version and the
distributions digest; a corpus with no steps (built before D-780) seals, and the datasheet says "building commit not
recorded". A manifest without the key is valid in every format. `producer` is inside `content_digest` (H.5.4), so the key
is covered by the root digest of a corpus that carries it. It is producer metadata, never a drift finding.

"Release mode" is any command run with `--release` (runner mode `release`, D.2.9), `agentprov package`, and the
deposit builder `agentprov.release.builder` (Addendum B AD-16; G.3.8(3)). There, on an interpreter below 3.14.8,
every step that would decompress or expand an archive or a compressed stream (container expansion at import,
`expand` at `rederive`, `verify` of a deposit archive) refuses before opening the object, exit 3. There is no
override flag.

### H.2.8 `ModelSummary`

`{ "requested": string|null, "served": [string], "provider": string|null, "ev": {"requested": "O"|"D"|"I",
"served": "O"|null}, "executions": int }`. It is computed from AER `actor.model` fields. Model identity MUST NOT be
taken from configuration alone. The served model is listed only when the provider reported it (CAP-6
[manuscript/review_feedback.md §1.2]).

### H.2.9 `Counts`

All values are integers:

- `candidates`, `executions`, `not_imported`
- `by_unit`: `{agent_execution, outcome_only, scenario}` (AD-03, R-28)
- `by_status`: `{ok, ok_with_issues, failed}`
- `by_completeness`: `{verified_complete, known_incomplete, unverifiable}`
- `execution_observed`: `{true, false}`
- `by_stage`: `{expand: {ok, failed}, aer: {ok, failed, skipped}, sem: {<profile>: {…}}, prov: {<spec>: {…}}}`;
  `expand.ok` counts the containers with rows in `raw/members.jsonl` and `expand.failed` the distinct
  (snapshot, source key or path) pairs among the `expand` error entries of the register
- `issues_by_code`, `not_imported_by_code`, `selection_excluded_by_code`
- `records_by_kind`: AER records per kind, over all 13 kinds of `aer/0.1` (Addendum B B-1): `execution`, `actor`,
  `scope`, `message`, `model_call`, `tool_execution`, `decision`, `state_change`, `fixture`, `judgement`,
  `activity`, `artefact`, `seal`
- `generic_types`: `{ "activity": { "<ns>:<name>": int }, "artefact": { "<ns>:<name>": int } }`: the namespaced
  `type` values of the generic records (Addendum B AD-15). The datasheet discloses them (H.9), because a generic
  record marks an event that no specialised kind represents
- `members` (corpora with archives): `{containers, selected, not_selected}` from `raw/members.jsonl` (AD-12, R-40)
- `attempts` (live only): `{cells, executions, max_attempt}`

Counts are taken over all index rows. In a corpus that withholds (H.4.5; D-231) the index holds only the released
executions, so every count, including `records_by_kind`, `models` and `framework_identities`, covers the released
set. The withheld executions are counted in `WITHHELD.json`, in `issues_by_code["release.withheld"]` and in the
datasheet. `executions` counts AER documents of every `unit`; a claim about agent
executions uses rows with `unit == "agent_execution"` and `execution_observed == true` (R-28; NC-ALL-13). Unknown is
never folded into false: tri-states are kept separate, as the baseline's tallies did
[audit/corpus.md §3.1.2 rule 8].

### H.2.10 `Licences`

| Field | Type | Notes |
|---|---|---|
| `raw` | array of `{ source_id, spdx \| null, licence_files: [path], copyright: [string], basis: string, data_licence_explicit: bool }` | `basis` cites the evidence, e.g. "repo LICENSE at commit …; no separate data licence". The datasheet renders every `basis` **verbatim** (R-14), e.g. AgentDyn "MIT as declared; not legally settled", Mandate "publisher unverified" |
| `policy` | `{ licence_policy: "include" \| "reference" \| "nc_partition" \| "forbidden", raw_policy: "include" \| "reference" \| "withhold" }` | The registry licence policy and the corpus raw policy it maps to (H.4.1) |
| `derived` | `{ spdx: string, basis: "inherit" \| "user-decision", decided_by: string, text_path: "LICENSES/DERIVED.txt" }` | The derived licence is the user's decision (U-03; default `inherit`) |
| `redistribution` | `"permitted"` \| `"permitted-non-commercial"` \| `"not-permitted"` | `"permitted-non-commercial"` when `derived.spdx` has a non-commercial term (the H.10.6 per-term test, e.g. `CC-BY-NC-4.0`, `PolyForm-Noncommercial-1.0.0`); otherwise from the licence policy |
| `attribution` | array of string | Citations that MUST accompany the data (e.g. arXiv ids) |
| `embedded` | array of `{ what: string, status: string }` | e.g. `{what: "model outputs (OpenAI, Google, …)", status: "provider terms not assessed"}` [sources/agentdojo.md §10], [sources/agentdyn.md §10]; `agentdojo-prov-v2` carries AgentDojo's MIT notice for the embedded benchmark content (U-03) |
| `restrictions` | array of string, sorted | e.g. the AgentHarm use clause (U-05), the CIAware gated card's training-use prohibition and its 3 canary GUIDs (AD-21), the SHADE-Arena canary-string retention |
| `class` | `{ spdx: string, restrictions: [string] }` | The licence class `(derived.spdx, sorted restrictions)`. Deposits are grouped by it, and the deposit builder refuses mixed classes (AD-20(b), H.10.6) |
| `assessment` | string | Date and scope of the licence reading. MUST state "not legal advice" [verify/autodojo.md claim 27] |

### H.2.11 `files` and `digests`

`files` maps roles to `FileRef = { path, sha256, bytes, lines|null }`. The roles are `index`, `register`, `origins`,
`members`, `references` (optional), `withheld` (optional), `derivation`, `validation_results`,
`validation_summary`, `spec`, `card`, `changes`. Sealing declares `references` exactly when `raw/REFERENCES.json` is
present and `withheld` exactly when `WITHHELD.json` is; `chain` fails an undeclared one (`references.undeclared`,
D-237; `withheld.undeclared`, D-163). The role list deliberately excludes `DATASHEET.md` and
`CHANGELOG.md`, which are generated *from* the manifest (H.9); `checksums.sha256` covers them.

`Digests`:

| Field | Definition |
|---|---|
| `raw_set` | `set_digest((sha256, disposition) for every raw object)`, `disposition` ∈ `included` \| `referenced` \| `withheld`; member objects and blobs included. As built (D-237): every stored object `included` unless withheld, every `WITHHELD.json` object `withheld`, every `raw/REFERENCES.json` object `referenced` (`agentprov.corpus.manifest.raw_dispositions`) |
| `aer_set` | `set_digest((ex, aer_digest) for every execution with an AER)` |
| `sem_set` | map profile → `set_digest((ex, sem_digest))` |
| `prov_set` | map spec → `{ json }`, a `set_digest((ex, digest))`. No `trig` or `core` member in v0.1 (AD-10 rows 3–4) |
| `validation_set` | `set_digest((ex, sha256(JCS(results row))))` |
| `index` | sha256 of the `executions.jsonl` bytes |
| `register` | sha256 of the `register.jsonl` bytes |
| `members` | sha256 of the `raw/members.jsonl` bytes |

`set_digest(pairs) = "sha256:" + sha256( "".join(sorted(f"{a} {b}\n" for a, b in pairs)) )`. It is computed by
streaming over the sorted lines (H.11).

### H.2.12 `ValidationSummary`

`{ "mode": "strict"|"dev", "checks": [{ "id": string, "version": string, "tier": int, "pass": int, "fail": int,
"skipped": int, "not_applicable": int }], "libraries": { name: version } }`. Per-execution results take the values
`pass|fail|skipped|not_applicable` (R-64), which the paper reads from `validation/` rather than re-running the
validator. Tiers follow D8. In `strict` (release) mode, `skipped` MUST be 0 for every gating check: skipped checks
never count as passed (D8; baseline defect [audit/validation.md §7 V11]). `fail` MUST be 0 for gating checks, unless
the execution is `failed` and its row in the register says so. This is judged per execution over
`validation/results.jsonl`: every execution with a failed gating check must have index status `failed` and a register
entry with code `validate.failed`, or `prov.failed` / `sem.failed` (which derive and import register instead when PROV or
SEM failed while the tier-3 checks still ran). The summed `fail` MUST NOT exceed the failed gating checks of those
executions.

### H.2.13 `Release` and the timestamp policy

| Field | Type | Notes |
|---|---|---|
| `status` | `"dev"` \| `"release-candidate"` \| `"sealed"` | |
| `created` | RFC 3339 UTC string \| null | Release mode MUST take it from `--release-date` or `SOURCE_DATE_EPOCH` (ASCII digits, 0..253402300799); a value that names no real instant is refused (`package.release_date`, exit 2) and is a semantic manifest issue. Dev builds MUST write `null` |
| `source_date_epoch` | int \| null | |
| `version_doi`, `concept_doi` | string \| null | Written only when the user passes them explicitly. Never fetched |
| `previous` | `{ corpus_version, content_digest }` \| null | The predecessor version |

Policy:

- No wall-clock value may appear anywhere else in the corpus tree.
- AER, SEM and PROV files MUST NOT contain build, retrieval or derivation times.
- Retrieval times appear only for mutable `url` origins.

The baseline's `generated_utc` made every manifest unreproducible [audit/corpus.md §3.1.3 P3]; this policy
removes it.

### H.2.14 Example (abridged, values illustrative)

```json
{
  "format": "agentprov-corpus/0.1",
  "corpus_id": "agentdojo-upstream",
  "corpus_version": "0.1.0",
  "mode": "import",
  "sources": [{
    "source_id": "agentdojo",
    "profile": {"id": "agentdojo-upstream", "version": 1, "sha256": "sha256:…", "path": "rules/agentdojo-upstream.profile.toml"},
    "parts": ["2024-06", "head"],
    "snapshots": [
      {"snapshot_id": "2024-06",
       "origin": {"kind": "git", "repo": "https://github.com/ethz-spylab/agentdojo",
                  "commit": "c274885610efaaafec38b6d3eb07152ba7ff3f94", "subtree": "runs",
                  "subtree_sha1": "1227480d637f06ac435c809ab39803afa72f78fc"},
       "alt_origins": [{"kind": "zenodo", "doi": "10.5281/zenodo.12528189", "file": "ethz-spylab/agentdojo-v0.1.7.zip"}],
       "selection": {"include": ["runs/**/*.json"], "exclude": []},
       "raw_policy": "include",
       "counts": {"candidates": 18241, "executions": 18241, "not_imported": 0, "selection_excluded": {}}},
      {"snapshot_id": "head",
       "origin": {"kind": "git", "repo": "https://github.com/ethz-spylab/agentdojo",
                  "commit": "089ed468cf3ed0322acc66b0211f26d9d90dbf60", "subtree": "runs"},
       "alt_origins": [{"kind": "zenodo", "doi": "10.5281/zenodo.17458493", "file": "ethz-spylab/agentdojo-v0.1.35.zip",
                        "md5": "d2dad4b4dca23bcc846fac3cae684d65"}],
       "selection": {"include": ["runs/**/*.json"], "exclude": []},
       "raw_policy": "include",
       "counts": {"candidates": 36679, "executions": 36679, "not_imported": 0, "selection_excluded": {}}}],
    "lineage": [{"relation": "mirrored_by", "target": {"kind": "git", "repo": "https://github.com/usnistgov/agentdojo-inspect", "commit": "a491020f…"}}],
    "mirrors": []
  }],
  "formats": {"corpus": "agentprov-corpus/0.1", "index": "agentprov-index/0.1", "register": "agentprov-register/0.1",
              "aer": "aer/0.1", "sem": "sem/0.1", "capture": null},
  "prov_specs": ["agentprov-prov/0.1"],
  "oracle_specs": [],
  "counts": {"candidates": 54920, "executions": 40738, "by_unit": {"…": "…"}, "…": "…"},
  "content_digest": "sha256:…",
  "release": {"status": "dev", "created": null, "source_date_epoch": null, "version_doi": null, "concept_doi": null, "previous": null},
  "sealed": false
}
```

The counts in the example are an inference from the reports. The June snapshot has 18,241 JSON blobs, the
baseline's 18,234 plus 7 Mixtral logs [audit/legacy_replay.md §2.1]. HEAD has 36,679 [verify/agentdojo.md §2].
14,182 files are byte-identical at the same path [sources/agentdojo.md §5.1]. That gives at most 40,738 distinct
AER documents (I.1.1 totals: 36,679 + 4,059). Of these, the 207 empty logs are `outcome_only` records, not agent
executions (R-28). The build establishes the real figures. The two snapshots' distinct records are never
conflated; only byte-identical files collapse (H.7.2).

---

## H.3 Execution index `executions.jsonl`

### H.3.1 Row fields

One JCS line per execution, sorted by `ex`. Format id `agentprov-index/0.1`; defined as a `$defs` entry of
`schemas/corpus-0.1.schema.json` (H.2.1). The Python type is `agentprov.corpus.index.IndexRow` (frozen dataclass). `IndexRow.to_json() -> dict` and
`IndexRow.from_json(d) -> IndexRow` validate on the way in and out.

| Field | Type | Req | Meaning |
|---|---|---|---|
| `ex` | string | MUST | Execution id (D2) |
| `mode` | `"import"` \| `"live"` | MUST | |
| `unit` | `"agent_execution"` \| `"outcome_only"` \| `"scenario"` | MUST | Copied from the AER header `execution.unit` (AD-03, R-28) |
| `source_id`, `snapshot_ids` | string (registry id), array of string | MUST | Snapshots in which the source key was found (≥ 1) |
| `source_key` | string | MUST | `"sha256:<hex>#" + JCS(loc)` (H.7.1) |
| `raw` | array of `{ sha256, role, included }` | MUST | One entry per AER header `artifacts[]` item, with C's role ∈ `primary` \| `capture_log` \| `native_log` \| `supporting` (RESOLUTIONS §3.3). `included` is false for referenced objects. Blobs (`seal.blobs`) are not listed here; their objects are in `raw/objects/` and in `digests.raw_set` |
| `n_origins` | int | MUST | Number of lines for the primary artefact in `raw/origins.jsonl` |
| `adapter`, `profile` | `"<id>@<version>"` | MUST | e.g. `agentdojo.tracelogger@0.1.0` (SemVer) and `agentdojo-upstream@1` (integer, AD-18) |
| `logical_key` | string `lk_…` \| null | MUST | H.7.4. `null` when the cell cannot be determined |
| `cell` | object | MUST | Adapter-declared coordinates used for the logical key (may be `{}`) |
| `facets` | object | MUST | Declared in `facet_schema` (H.3.3) |
| `ev` | map facet name → `"O"` \| `"D"` \| `"I"` | MUST | Evidence class of every present facet and of every `cell` member (keys `cell.<name>`) |
| `digests` | `{ aer, sem: {profile: d}, prov: {spec: {json}}, validation }` | MUST | Values `"sha256:…"` or `null` when the stage did not produce output |
| `paths` | `{ aer, sem: {…}, prov: {spec: {json}} }` | MUST | Relative paths. Validators recompute them (H.1.3) |
| `oracles` | map spec → `{ "status": "apv:RegressionOracle", "gate_report": "sha256:…" \| null }` | MUST | Present for each regression-oracle spec in `paths.prov` (`adprov-v2.3-compat`); `{}` otherwise (R-55; AD-10 row 5: compat digest + gate report reference in the index) |
| `stages` | `{ raw, aer, sem: {…}, prov: {…}, validation }` | MUST | Values ∈ `ok` \| `failed` \| `skipped` \| `not_applicable`. `raw` covers ingest and, for member objects, `expand` |
| `status` | `"ok"` \| `"ok_with_issues"` \| `"failed"` | MUST | H.3.2 |
| `completeness` | `"verified_complete"` \| `"known_incomplete"` \| `"unverifiable"` | MUST | H.3.2 |
| `execution_observed` | boolean | MUST | False when the source holds an outcome but no trajectory (e.g. 207 empty AgentDojo logs, 2 ROPE; `unit: outcome_only`) |
| `issues` | array of string | MUST | Sorted, unique **register** codes (H.6.3): AER seal issues appear as `map.<code>` (adapter codes as `map.<ns>.<code>`). Details are in `register.jsonl` |
| `attempt` | int \| null | MUST | Live: attempt index of this cell (0-based). Imports: `null` |

`digests.aer` is the AER **execution digest** (`seal.records_sha256`, D2). It is not the file's byte hash; the
byte hash is in `checksums.sha256`.

### H.3.2 Status, stages and completeness

1. `status` is computed from `stages` and the issue severities (H.6.3):
   - `failed` if any required stage is `failed` or any issue has severity `error`;
   - else `ok_with_issues` if any issue has severity `warning`;
   - else `ok`.

   `info` issues document limitations inherent to the source format. They do not change the status.
2. `completeness` is AR-3's verified, recorded property ([manuscript/review_feedback.md §5], CAP-1). Accounting is
   computed once, by the AER mapper and validator, and read from the AER seal (`seal.accounting.status` ∈
   `consistent|inconsistent|unverifiable`; R-13). The capture side only seals its hash chain.
   - **Live:** `verified_complete` iff the seal's accounting verdict is `consistent`, every `pass.start` event has
     a `pass.end`, and `session.end.status` is `complete` [audit/capture.md §9.4]. `known_incomplete` iff the
     verdict is `inconsistent`, a pass aborted, or a declared loss exists. Otherwise `unverifiable`.
   - **Imports:** `known_incomplete` iff an adapter rule proves loss, that is, a seal issue of a loss code
     (`incomplete_run`, `retry_passes_inferred`, `aborted_attempt`) cites a class-D rule; under an `_unverified` twin
     (D.5.4 "Citation of D rules") the loss is inferred, not proven (regeneration-batch item 3, analysis B6). Examples: AgentDojo logs ending on a `null`
     assistant reply, which are provably the third of three passes (82 at upstream HEAD) [verify/agentdojo.md §3];
     the transcript/v1 rule `usage.n_llm_calls > assistant turns` (153 release traces)
     [baseline/BASELINE.md §5.1]. `verified_complete` only where the source records enough to reconcile.
     Otherwise `unverifiable`. Most AgentDojo-family logs are `unverifiable`.
   - **Vacuous accounting is not verification.** The fold of no verdicts is `consistent`, but `verified_complete`
     additionally requires that at least one accounting check was evaluated (the seal's `accounting.checks` is not
     empty) and that `unit == "agent_execution"`. An outcome-only record, an empty log and a run error before the
     first assistant turn evaluate no check and are `unverifiable`. Index rows written before this rule (phase-10
     corpora: head 232, ROPE 2; the 2024-06 corpus likewise) keep `verified_complete` until their next
     regeneration, so a consumer that needs the strict meaning must also require `unit == "agent_execution"` and a
     non-empty `accounting.checks` in the AER seal (phase-10 analysis B2, 2026-10-11).
3. Analyses that need complete records MUST filter on `completeness == "verified_complete"` and fail closed.
   Filters are views. They never remove rows (H.6.1 R6).

### H.3.3 Facets and `facet_schema`

1. `FacetDecl = { "name": string, "type": "string"|"integer"|"boolean"|"string[]"|"object", "from": string,
   "may_be_inferred": boolean, "core": boolean }`. `from` is a JSON Pointer into AER or SEM, or a rule id.
   Adapter facets are namespaced `x.<ns>.<name>` (e.g. `x.agentdojo.pipeline_dir`, `x.agentdojo.task_kind`).
2. Core facets, always present:

   | Facet | Value |
   |---|---|
   | `task` | Verbatim copy of the AER header `task` object, so field names follow the AER section |
   | `framework` | `fw` id (H.2.4) |
   | `model.requested`, `model.served` | string arrays |
   | `n.messages`, `n.model_calls`, `n.tool_executions`, `n.decisions`, `n.judgements`, `n.state_changes`, `n.activities`, `n.artefacts` | integers; the last two count the generic `activity` and `artefact` records (Addendum B AD-15) |
   | `generic_types` | string array: the sorted, unique namespaced `type` values (`<ns>:<name>`) of the execution's `activity` and `artefact` records; `[]` when none |
   | `outcome` | Array of `{ name, value, origin, claim, holds, score, scale, ev }`. `name`, `value` and `origin` (`checker` \| `harness_default` \| `harness_rule` \| `recomputed`) come from the AER `judgement`; `claim`, `holds`, `score` and `scale` come from the SEM `outcome` annotation on it, where polarity lives (R-18) [landscape/trace_formats.md §6.3]. Members absent from SEM are `null` |

3. Every facet MUST be a pure function of the execution's AER and SEM files. The index is therefore re-derivable,
   and `verify --level chain` re-derives it (H.5.5).
4. Facets carry evidence classes in `ev`. A facet obtained by inference, such as a model id taken from a directory
   name, is marked `I` with the rule recorded in AER. This answers the baseline's practice of publishing fields of
   different epistemic status side by side [audit/corpus.md §5.1].

### H.3.4 Example row (abridged, illustrative values)

```json
{"adapter":"agentdojo.tracelogger@0.1.0","attempt":null,
 "cell":{"attack":"important_instructions","benchmark":"agentdojo","injection_task":"injection_task_7",
         "model":"gpt-4o-2024-05-13","pipeline":"gpt-4o-2024-05-13","suite":"banking","suite_set":"v1",
         "user_task":"user_task_7"},
 "completeness":"unverifiable",
 "digests":{"aer":"sha256:…","prov":{"agentprov-prov/0.1":{"json":"sha256:…"}},
            "sem":{"agentdojo.suites@1":"sha256:…"},"validation":"sha256:…"},
 "ev":{"cell.model":"I","cell.suite_set":"I","framework":"D","model.requested":"I","outcome":"O"},
 "ex":"ex_…","execution_observed":true,"facets":{"…":"…"},
 "issues":["map.earlier_attempts_unobservable"],"logical_key":"lk_…","mode":"import","n_origins":2,
 "oracles":{},
 "paths":{"aer":"aer/3f/ex_….aer.jsonl","prov":{"agentprov-prov/0.1":{"json":"prov/agentprov-prov-0.1/3f/ex_….prov.json"}},
          "sem":{"agentdojo.suites@1":"sem/agentdojo.suites-1/3f/ex_….sem.jsonl"}},
 "profile":"agentdojo-upstream@1",
 "raw":[{"included":true,"role":"primary","sha256":"sha256:6faf6900fd2ef0ece7745b66f407323b2766652e45c06a7faed571a37f76111a"}],
 "snapshot_ids":["2024-06","head"],
 "source_id":"agentdojo",
 "source_key":"sha256:6faf6900fd2ef0ece7745b66f407323b2766652e45c06a7faed571a37f76111a#{\"p\":\"\"}",
 "stages":{"aer":"ok","prov":{"agentprov-prov/0.1":"ok"},"raw":"ok","sem":{"agentdojo.suites@1":"ok"},"validation":"ok"},
 "status":"ok","unit":"agent_execution"}
```

The sha256 is that of the AgentDojo sample used in [landscape/trace_formats.md §6.13]. That file is byte-identical
in the baseline copy, so it is plausibly present in both snapshots [sources/agentdojo.md §11].

---

## H.4 Raw evidence: include, reference or withhold

### H.4.1 Policies

| Policy | Raw artefacts | Derived content (AER/SEM/PROV/views) | Releasable |
|---|---|---|---|
| `include` | Stored in `raw/objects/`, listed in `raw/origins.jsonl` | Included | Yes |
| `reference` | Listed in `raw/REFERENCES.json` (digest, size, pinned origins; H.4.3). Not stored in the release | Included only if `licences.redistribution` permits derived data. Otherwise the snapshot MUST be `withhold` | Yes, without raw bytes |
| `withhold` | Kept in the local raw store only; in a sealed corpus listed in `WITHHELD.json` and moved to the private sidecar (H.4.5) | Not released: the snapshot's executions are withheld | A corpus whose every snapshot is `withhold` is refused by `agentprov package --deposit`; a `withhold` snapshot beside released ones is accepted with its `WITHHELD.json` (D-233) |

1. The policy is chosen per snapshot from the registry licence policy of the part (I.1.1; D3, D4) and confirmed in
   the spec. Changing a released snapshot from `include` to `reference` or `withhold` is a MAJOR corpus bump
   (L.1.3).
2. **Licence policy → raw policy** (R-14; RESOLUTIONS §3.8). The registry carries the *licence policy* of a part;
   the corpus carries the *raw policy* of a snapshot:

   | Registry licence policy | Corpus raw policy |
   |---|---|
   | `include` | `include` |
   | `reference` | `reference` |
   | `nc_partition` | `include`, but only inside a separately licensed `-nc` corpus (none is built in v0.1: STAC is planned; AD-10 row 22) |
   | `forbidden` | `withhold` |

   A part *role* (`source`, `mirror`, `owned_elsewhere`, `compat_oracle`, `context`, `not_executions`) is not a
   policy; `excluded` is not a policy value.
3. Prompt-injection payloads are expected content in every agent-security source. The datasheet MUST say so
   [sources/rope.md §9]. Raw artefacts are untrusted data and are never executed or interpreted beyond parsing
   (D3, D8 tier 1). Raw bytes are never scrubbed or edited: a value that must not be released is handled through
   `WITHHELD.json` (H.4.5) or a private test corpus (AD-21).
4. **Per snapshot (D-233).** A `withhold` snapshot releases nothing. Every execution that a row of that snapshot
   records is withheld, including a row shared with another snapshot (*withhold wins*). So is every object such a row
   cites, and every object whose origin the snapshot's pin vouched for (members follow their container); the reason is
   `licence`. The released snapshots share one raw policy, recorded in `licences.policy.raw_policy`. When every
   snapshot is `withhold`, that policy is `withhold`: the sealed corpus is a private record and is never deposited.
   Withholding only narrows a release, so `withhold` is accepted under every licence policy except `forbidden`, which
   sealing still refuses (D.3.4).

### H.4.2 Per-source decisions for v0.1

Licence readings are those of the investigation. They are not legal advice. The derived-data licence is the
user's decision (U-03; `derived = "inherit"` is the proposed default, which avoids any relicensing question).

Statuses are the v0.1 **targets** of I.1.1 as amended (R-07, R-15, R-25, R-29); I.1.1 is the single source of
these values and this table is compared against it (RESOLUTIONS §5). The registry renders a part `planned` until
its gates pass, and `supported` additionally requires a full pinned-snapshot import with zero crashes, every file
sealed and the counts recorded in `docs/reports/` (R-15). A one-status-per-row rendering is per part or worst-case
with `mixed`, never best-case.

| corpus_id | Source id · parts (I.1.1) · v0.1 target | Pinned origin(s) | Selection (and exclusions) | Upstream licence (evidence) | Licence policy → raw policy | Derived licence (proposal) | Notes |
|---|---|---|---|---|---|---|---|
| `agentdojo-upstream` | `agentdojo` · `2024-06` and `head` (#1): supported; `history`: planned | `ethz-spylab/agentdojo@c274885610efaaafec38b6d3eb07152ba7ff3f94:runs/` (subtree `1227480d…`, June 2024; 18,241 blobs incl. 7 Mixtral) and `@089ed468cf3ed0322acc66b0211f26d9d90dbf60:runs/` (HEAD; 36,679). Alternatives: Zenodo `10.5281/zenodo.12528189` (v0.1.7, a superset runs tree) and `10.5281/zenodo.17458493` (v0.1.35 = HEAD runs); concept DOI `10.5281/zenodo.12528188` (A6) [verify/agentdojo.md §2.1] | `runs/**/*.json`. Released as two corpora, one per snapshot (D-35); one corpus holding both snapshots is supported (H.7.2, D-202) and used for comparisons only. Distinct records are never conflated, and only byte-identical files collapse. Superseded history blobs (11,173) belong to neither snapshot (part `history`, planned) | MIT repo-wide; Zenodo records declare `mit-license`; no separate data licence [verify/agentdojo.md §1] | include → include | inherit (MIT) | Carry `LICENSE` and `CITATION.bib` [sources/agentdojo.md §10]. `basis`: "MIT by repository; data licence not separately stated" (U-03). Provider terms on model outputs not assessed. The 207 empty logs are `outcome_only` records |
| `agentdojo-prov-v2` | `adprov-v1` · `release` (#2): supported | AgentDojo-PROV v2.3 release transcripts, local; v2.3 deposited on Zenodo 2026-10-10 (`10.5281/zenodo.23276620`, D-900); origin `{kind: corpus, corpus: "AgentDojo-PROV", version: "2.3", producer_commit: "579a908…"}`. the previous deposit is v2.2, `10.5281/zenodo.21052314`; byte equality with the v2.3 deposit not verified (U-07) [baseline/BASELINE.md §8.1] | `*/prov/*/*.transcript.json` (17,664), plus the frozen v2.3 checksum evidence as raw objects: 6 release + 17 converted `checksums.sha256` lists (about 10.4 MB) and J.1.4's five listing digests (R-26). Baseline graphs are not raw: they are compatibility-gate oracles, read from the frozen baseline | Data CC-BY-4.0 as stamped by the author (`package.py:170`); code MIT | include → include | CC-BY-4.0, carrying AgentDojo's MIT notice for the embedded benchmark content (U-03) | Author's own live data. Provider terms not assessed. Verifying against the v2.2 zip needs the user's consent to download about 106 MB (U-07). Released v1 context membership is INFERRED (AD-05). Compat graphs, where built, are flagged `apv:RegressionOracle` (R-55) |
| (none) converted legacy tree | `adprov-v1` · `converted-legacy` (#3): — (role `compat_oracle`) | baseline `corpus/corpus-og-agentdojo-runs-prov/` at `579a908…` (18,027) | — (not imported) | stamped CC-BY-4.0, not carried; MIT by inclusion | — | — | Read only by migration gate R (J). See the paragraph below the table |
| `agentdyn` | `agentdyn` · `a` (#5): supported; `b`, `c`: partial (stretch, AD-10 row 21); `d`: role `owned_elsewhere`; `history`: planned | `SaFo-Lab/AgentDyn@5353cf7615b135cace8d07c8f12dac53a16b6db3:runs/` | `runs/**/*.json` (A 38,281; B 5,184; C 4,258); exclude `src/agentdojo/defenses/drift/runs/**` (code `select.owned_elsewhere`, owner `drift`) [sources/agentdyn.md §5]. Until the B and C profiles pass their gates, those candidates get `select.dialect_planned` | MIT (AgentDojo copyright line); `basis`: "MIT as declared; not legally settled" (R-14) | include → include | inherit (MIT) | Never use the unlicensed HF dataset `agentdyn-dataset/agentdyn` [sources/agentdyn.md §10]. Variant C holds author-rekeyed copies of AgentDyn's **own** history blobs; the curation step is recorded (A6, R-62). The 16,795 history-only blobs are not in v0.1 |
| `drift` | `drift` · `head` (#8): partial (stretch; built only after the DoD set, AD-10 row 21); `history`, `asb`: planned | `SaFo-Lab/DRIFT@6fd3df4763fad77398c3c273c2a4fe14dd50f7ea:runs/` | `runs/**/*.json` (1,569); exclude `ASB_DRIFT/logs/**` (code `select.dialect_planned`) | MIT, added only in `6fd3df4` [sources/drift.md §1, verify/drift.md §1] | include → include (HEAD) | inherit (MIT) | Pre-licence history blobs (`53dbc6c`) are not imported in v0.1. If ever imported they MUST be `reference` [sources/drift.md §11]. DRIFT owns the 949 logs vendored as AgentDyn `d` (lineage edges E09/E10; R-62) |
| `rope` | `rope` (#7): supported | `xhOwenMa/ROPE@64495e16e640d687e06e6b1b6cee6dccc5b9b7cb:runs/` | `runs/**/*.json`; exclude `runs/lh_cells.json` (`select.not_execution_artefact`) and `agentlab/**` (`select.owned_elsewhere`, owner AgentLAB, not a v0.1 source) | MIT; payloads from AutoDojo (MIT) and AgentLAB (MIT) [sources/rope.md §9] | include → include | inherit (MIT) | Contains the AutoDojo-attack slice (2,847 runs) as facet `x.rope.attack_family` [sources/autodojo.md summary]; `security_raw` and ROPE-corrected values stay separate (A6). The 2 empty logs are `outcome_only` records |
| `mandate-agentdojo-eval` | `mandate-agentdojo-eval` (#12): supported | `jwilliamsc/mandate-agentdojo-eval@fa62a977584962f7b4b24a40772a83345fd920d4:runs/` | `runs/**/*.json` (396) | MIT, (c) Mandate Labs [verify/mandate-agentdojo-eval.md §1]; `basis`: "publisher unverified" (R-14) | include → include | inherit (MIT) | Model outputs subject to OpenAI terms (not assessed). Its import needs `decision` records (I.1.1) |
| `ast-survey-agentdojo` | `agent-security-tools-survey` · `agentdojo-runs` (#11): supported | git `Forever-CodingNoob/agent-security-tools-survey@89c4db2c949797fbb38c5bfed85dc82780ddbfe3` (primary). Alternatives: Zenodo v1.0.0 `10.5281/zenodo.22135957` and v1.0.1 `10.5281/zenodo.22140262`; every object verified by sha256; cite the concept DOI `10.5281/zenodo.22135956` with the version fetched (R-62) | The survey's own AgentDojo runs (3,243); exclude the bundled upstream AgentDojo `runs/` (`select.owned_elsewhere`, owner corpus `agentdojo-upstream`), the AgentHarm Inspect logs (`select.owned_elsewhere`, owner corpus `ast-survey-agentharm`) and the ASB CSV (`select.dialect_planned`; part `asb` planned) | CC-BY-4.0 [sources/agent-security-tools-survey.finding.json], [verify/agent-security-tools-survey.md §2.1] | include → include | CC-BY-4.0 | New executions on AgentDojo `089ed468` plus 3 local patches (I.1.1). 2,385 outputs are Python repr, not YAML (A6) |
| `ast-survey-agentharm` | `agent-security-tools-survey` · `agentharm` (#11): supported as a v0.1 target (dialect `inspect.eval`, producer band `inspect_ai 0.3.247.dev69`); registry `planned` until the D.9 and DoD gates pass (AD-06) | same pinned origin as `ast-survey-agentdojo` | `agentharm/results/*/*.eval` (6 logs, 1,056 samples) [verify/agent-security-tools-survey.md §2.2–§2.3]. Archive methods {0, 8, 93} are allowed (A2); members become objects through `expand` (AD-12) | Survey CC-BY-4.0; the AgentHarm data is MIT "with an additional clause" restricting use to improving AI safety and security [verify/agent-security-tools-survey.md §2.1] | include → include; the use clause is carried in `licences.restrictions` | CC-BY-4.0 (proposal; U-03), clause carried | A separate corpus and deposit because of the restricted-use clause (U-05): its licence class differs (AD-20(b)). The AgentHarm dataset revision `e23b3fe6` is code-inferred (I), not in-record [verify/agent-security-tools-survey.md §2.5]. The first non-AgentDojo-lineage corpus (A7 item 4) |
| (none in v0.1) `stac` | `stac` (#13): planned (scenario records, not executions) | `amazon-science/MultiTurnAgentAttack@ddeede7a0042d108b819e35281135b0b0fabb4de:data/STAC_benchmark_data.json` (483 records, locators `{"p":"/<i>"}`) | the single JSON file | CC BY-NC 4.0 [sources/multiturn-agent-attack.md §9] | nc_partition → include, only in a `-nc` corpus | **CC BY-NC 4.0 (mandatory)** | No v0.1 corpus (AD-10 row 22). When built: `unit: scenario`; a separately licensed `-nc` corpus and deposit; keep the SHADE-Arena and Agent-SafetyBench MIT notices and the SHADE canary string |
| (none) `ciaware-bench` | `ciaware-bench` (#14), AD-21 conservative: `hf-gated` evidence partial, import planned; `hf-anon-mirror` and `github-records` planned; `ciabench` per U-04 | HF `schaeff/CIAware-Bench-Data@0b26bb90…` (gated) and the other parts of I.1.1 | — | none [sources/ciaware-bench.md §1]; `ciabench` card metadata MIT, "not legally settled" | reference → reference (`ciabench`: `reference` unless the user accepts the MIT basis in writing, U-04). No derived release without permission, so in practice `withhold` (H.4.1) | — | No v0.1 corpus and no phase-gate sample. Needs the user's gate acceptance and the authors' written permission. Raw bytes are never scrubbed: `WITHHELD.json` or a private test corpus. The gated card's training-use prohibition and its 3 canary GUIDs go into `licences.restrictions` |
| (none) AgentDojo-Inspect | `agentdojo-inspect` (#4): not_possible (`mirror_of = "agentdojo"`) | mirror of AgentDojo upstream | — | NIST notice + MIT | reference | — | Not a corpus (D4, D11). Recorded in corpus `agentdojo-upstream`, `sources[0].mirrors` (H.7.6) |
| (none) MiDojo, ADI | `midojo`, `adi`: not_possible | — | — | — | — | — | No execution data released (D11; A6) |
| `agentdojo-live-<campaign>`, `autodojo-live-<campaign>` | `agentdojo` · `live` (#1), `autodojo` · `live` (#6): supported (target; `partial` since D-720), caveat: the D-720 subset (local model servers with consent; API endpoints with consent and both caps); real-model pilot 2026-10-22 (AutoDojo: local only), not sealed (R-25; D-722, D-729) | `capture/0.1` logs + native TraceLogger JSON (D3), produced by the backend projects `backends/agentdojo` (`agentdojo==0.1.35`) and `backends/autodojo` (fork @`aa458794b7eb7f082e94daeac4c0f55bfc0c90cc`) | all artefacts of the campaign | the user's own | include → include | user decision (U-03; proposal: CC-BY-4.0, as for the baseline) | Provider terms on model outputs not assessed. Secrets never recorded (L.2.2). Real-model runs need the user's consent (U-10), the AD-13(b) containment and, for an API endpoint, the user's key and both caps (D-721, D-725). A `test_only` corpus is never deposited (H.1.1(2)) |

The baseline's converted tree `corpus-og-agentdojo-runs-prov` is **not** imported as a corpus. It stays a
`compat_oracle` part of `adprov-v1`, read only by migration gate R. Only a full R1/R2 claim-gate pass with 0
mismatches over its 18,027 graphs licenses the statement that the `2024-06` snapshot of `agentdojo-upstream`,
re-imported with source anchoring [audit/legacy_replay.md §13], supersedes it (AD-07, R-32). Otherwise the
mismatch report is published and the tree keeps its oracle role. Its `CC-BY-4.0` stamp is not carried forward: the
licence of data derived from AgentDojo's 2024 logs is MIT by inclusion, and the stamp was a build constant
[audit/corpus.md §9 item 16].

### H.4.3 `raw/REFERENCES.json`

```json
{"format": "agentprov-raw-references/0.1",
 "objects": [{
   "sha256": "sha256:…", "bytes": 12345, "media_type": "application/json",
   "origins": [{"kind": "git", "repo": "…", "commit": "…", "path": "…", "blob_sha1": "…"}],
   "reason": "licence-unclear",
   "requires": ["network"]}]}
```

`reason` ∈ `licence-no-redistribution` | `licence-unclear` | `gated` | `size`. `requires` ⊆ `network`,
`hf-gate-acceptance`, `authors-permission`, `credentials`. The file is corpus-supplied data and is therefore not
trusted (R-43):

- **No stored instructions.** It holds no command string, no fetch method and no free text. The help text
  (`agentprov fetch --corpus <root> --only sha256:<hex>`) is generated at display time by the CLI (MN N.2.2).
- **Pinned origins only.** A reference resolves only if its origin matches an origin declared in the
  **in-package** profile of the corpus's source: kind, repo, dataset or DOI, pinned revision, and sha256. Any other
  reference is refused with register code `raw.reference.unpinned_origin` and never contacted.

`agentprov fetch` MUST:

- verify every fetched object by sha256 before storing it;
- never accept a gate, licence or terms on the user's behalf;
- read credentials only from the environment or an interactive prompt, and never write them anywhere;
- attach a token only to the host that the in-package profile declares (`add_unredirected_header`);
- follow redirects only through a handler that requires https, enforces the host allowlist and drops credentials on
  any host change (G; SEC-24).

### H.4.4 `LICENSES/`

- `LICENSES/<source_id>/LICENSE` is the verbatim upstream licence file at the pinned commit. Where the upstream
  ships several, all relevant ones are included: AutoDojo's `agentdojo/LICENSE`, `ASB_DRIFT/LICENSE`, the SHADE-Arena
  and Agent-SafetyBench licences.
- `NOTICE.md` is generated. It lists repo, commit, copyright lines, required citations and restrictions from the
  profile.
- `LICENSES/DERIVED.txt` is the licence text of the derived artefacts. Its SPDX id is in `licences.derived.spdx`.
- `agentdojo-prov-v2` carries AgentDojo's MIT notice for the embedded benchmark content (U-03). Every `NOTICE.md`
  lists the part's `licences.restrictions` verbatim.

### H.4.5 `WITHHELD.json`

Raw evidence is never edited (D3). When a real secret, a personal datum, a licence problem or a takedown request
affects released raw, the artefact is withheld from the public release, a **new corpus version** is built, and its
root carries `WITHHELD.json` (format `agentprov-withheld/0.1`, covered by `checksums.sha256`), as specified in G.9.5
(A4). The AER, SEM and PROV of affected executions are withheld with it; each gets register code
`release.withheld` (H.6.3), and the datasheet reports the count. No entry contains the withheld value or any
fragment of it.

**As built (D-230..D-236; `agentprov.corpus.withheld`, `agentprov.corpus.withhold`).**

1. **What a sealed corpus is.** The sealed tree is what is released. A withheld object's bytes and a withheld
   execution's index row, validation row and AER, SEM, PROV and view files are not in it. Sealing renames them into the
   private sidecar `DIR.withheld/` (H.1.2). The register keeps every entry of a withheld execution, and
   `raw/origins.jsonl`, `raw/members.jsonl` and `raw/tombstones.jsonl` keep their rows.
2. **The format.** `{format, entries, executions, policies}`, a corpus-layer single document (H.1.4(2)) with the
   published schema `schemas/withheld-0.1.schema.json`. A sealed corpus that holds `WITHHELD.json` also holds a copy of
   that schema. **`agentprov-withheld/0.2`** (D-312) differs only in admitting the rule kind `issue` in `policies`; a
   document is `/0.2` exactly when one of its policies has an issue rule, and then the corpus holds
   `schemas/withheld-0.2.schema.json` instead. **`agentprov-withheld/0.3`** (D-454) differs from `/0.2` only in
   admitting the basis `unscanned`; a document is `/0.3` exactly when one of its entries has that basis, with
   `schemas/withheld-0.3.schema.json`. **`agentprov-withheld/0.4`** (D-810) admits the rule kind `address` (digests of
   e-mail addresses, never a literal) and every basis of `/0.3`; a document is `/0.4` exactly when a policy has an address
   rule. **`agentprov-withheld/0.5`** (D-964) admits the rule kind `object` (the stored raw objects and executions a corpus
   spec's `[withhold]` table lists) and everything of `/0.4`; a document is `/0.5` exactly when a policy has an object
   rule, with `schemas/withheld-0.5.schema.json`. Every other document keeps the bytes of its earlier version.
   - `entries` (sorted by `sha256`) follow G.9.5 and add `basis` ∈ `purge` | `raw_policy` | `profile_rule` |
     `container` | `unscanned` (`/0.3` only, last in the order). `bytes`, `media_type`, `finding` and `decided_on` are `null` when unknown, never a placeholder.
     `origins` are the object's `raw/origins.jsonl` origins (at least one). `finding` (exactly for `profile_rule`) is
     `{detector: "agentprov-withhold/1", rule: "<profile>@<v>:<rule id>", fingerprint: "<corpus path>:<rule id>"}`.
     `affected_executions` are the executions withheld because of the object; an execution that cites it but is not
     listed stays released (object-level withholding).
   - `executions` (sorted by `ex`) give each withheld execution's `snapshot_ids` and the index row's stage
     `digests`. The source key is not kept, because its locator can hold source-derived names.
   - `policies` name the source-profile `[withhold]` policy that was applied: profile id, version and digest; rule
     ids, kinds and scopes; `scan_rules`.
3. **Causes.** One entry per object; when several causes apply, the first reason of `secret`, `personal_data`,
   `takedown`, `licence` wins, then the first basis in the order above.
   - **purge**: every tombstone (G.9.6), with the executions that cite the object or, for a container, a member
     of it;
   - **raw_policy**: a `withhold` snapshot (H.4.1(4));
   - **profile_rule**: the source profile's `[withhold]` policy (item 5);
   - **container**: an archive that holds a withheld member (object level). The same closure, both ways (D-315),
     joins a split descriptor and its byte parts (the parts are the archive's bytes; a value can straddle two parts)
     and a carved blob and its source (the same value, possibly decoded): each group is withheld whole, with a
     generated note, and no execution is withheld by the closure itself.

   A `release.withheld` register entry that no cause explains refuses the seal (`corpus.withhold.unexplained`). So
   does a withheld object without an origin (`corpus.withhold.no_origin`).
4. **Accounting.** H.2.9 counts cover the released executions (snapshot `candidates == executions + not_imported`
   holds over them). Each withheld execution has exactly one `release.withheld` entry (stage `package`, disposition
   `withheld`); its fixed `detail` names the basis of a cause that withheld the execution (`purge`, `raw_policy` or
   `profile_rule`), never `container` or `unscanned`, which withhold no execution. `digests.raw_set` gives withheld objects the disposition `withheld`.
5. **Profile policy (D-234, D-235).** A source profile may declare `[withhold]`:
   - `reason`, `public_note` (one line, at most 200 characters), and optionally `scan_rules`;
   - `[[withhold.rules]]`, each with an `id` and either a literal `marker` (4 to 256 characters; a tag, never a secret)
     or a bounded `pattern`, plus `scope` = `executions` (the default) or `object`. A pattern is atoms (an ASCII
     literal, escaped punctuation, `\d`, `\w`, `\s`, a class), each with `?`, `{n}` or `{m,n}` (n ≤ 256); there are
     no groups, alternation, `.`, `*`, `+` or anchors.

   At sealing, every stored raw object and every derived file is scanned (1 MiB chunks, overlapping by the longest
   match). A raw hit withholds the object, and with scope `executions` its citing executions. A derived hit withholds
   the execution and its primary object. Only rule ids are recorded. The stored archives are also read decoded (D-450,
   D-452, D-453; G.9.5 states what is recognised and read): a hit there withholds the archive at object level. An
   archive that cannot be read decoded, and that no other cause withholds, is withheld unread (basis `unscanned`, the
   policy's reason, object level; its containers follow; D-454). The seal report counts it (`withheld_unscanned`) and
   prints its container chain, and counts the archives read by their local headers (`scanned_partial`, D-453).
   `chain` and the deposit builder repeat the decoded scan over the released tree; a released archive it cannot read
   is `withheld.unscanned` (failed) and `release.refused.withhold_unscanned`.

   **Issue rules (D-311, D-313).** A rule may instead name an AER seal issue code, `issue = "<namespace>.<code>"`
   (no `scope`). Every execution whose index row lists `map.<namespace>.<code>`, or that has a register entry with
   that code, is withheld with its primary object, as for a derived hit; the other executions that cite that object
   stay released (object level, D-235). The code must be declared by the `issue_codes` of the catalogue of its
   namespace, at the version the corpus records; otherwise the policy is refused (`corpus.withhold.policy`). The
   rule's finding has fingerprint `<AER path>:<rule id>`; neither the code nor any value enters `WITHHELD.json`, only
   the rule id and kind. This lets a source's own record of which executions expose a value (MCPHunt's canary flags,
   D-289 (c)) decide withholding, with marker and pattern rules as the byte-level backstop.
6. **Recomputing a withheld execution.** Fetch the object by its digest from a listed origin (`agentprov fetch`;
   verified by sha256), re-import the snapshot into a scratch working corpus, derive, and compare the execution's
   digests with `WITHHELD.json` `executions[]`. Re-deriving a sealed corpus that withholds an object its released
   executions need (object level) reports those outputs `unverified` until the object is in the fetch cache.
7. **Verification.** See H.5.5 `chain`, the withholding checks.
8. **Deposit.** See H.10.1(4) and G.9.4.
9. **Known limit.** An object's origin rows are not withheld: an origin path is public metadata of the pinned
   source. A value in a source path is a profile matter (D-146: redaction of workstation account paths).

---

## H.5 Checksums and digest chain

### H.5.1 The chain

```
raw artefact bytes ──sha256──► raw object id (file name)                      [H.1.3]
        │  archive container ──expand(fn_digest)──► member objects, each (label, method, crc32, size, sha256)
        │                                            recorded in raw/members.jsonl                  [AD-12]
        │  (AER header lists artifacts[].sha256; src locators resolve against digest-checked bytes, D2/D8)
        ▼
AER file ──seal.records_sha256──► execution digest  (index digests.aer)       [D2]
        ▼  (SEM header MUST record the AER execution digest it annotates)
SEM file ──SEM digest──► index digests.sem[profile]                           [D6]
        ▼  (PROV top level records raw, AER and SEM digests and the rule-catalogue digest;
        ▼   hashes live outside the bundles they cover) [landscape/prov_semantics.md §10.2(5)]
PROV-JSON file ──sha256(bytes)──► index digests.prov[spec].json   (TriG is not stored, AD-10 row 3)
        ▼
validation/results.jsonl row ──sha256(JCS(row))──► index digests.validation
        ▼
executions.jsonl ──sha256(bytes)──► corpus.json digests.index ; set digests per stage
        ▼
corpus.json ──content_digest (JCS minus release/sealed/content_digest)──► corpus identity
        ▼
checksums.sha256 (every file incl. corpus.json, DATASHEET.md, register, LICENSES) ──sha256──► ROOT DIGEST
```

### H.5.2 Requirements on upstream stages

1. The AER validator (D8 tier 2) MUST re-hash every referenced raw artefact before resolving locators.
2. SEM and PROV documents MUST record the digests of their inputs. The PROV top-level statements give the raw,
   canonical-record and rule-set hashes [landscape/prov_semantics.md §10.1]. This lets a single PROV file be
   checked against its inputs without the index.

### H.5.3 `checksums.sha256`

1. The format is that of `sha256sum` and `shasum -a 256 -c`: `<64 hex><space><space><posix relpath>\n`. This keeps
   the baseline format (`package.py:471-497`), which the baseline verification used on 107,112 entries
   [baseline/BASELINE.md §4.4].
2. It covers **every regular file** under the corpus root except itself, including `corpus.json`, `DATASHEET.md`,
   `CHANGELOG.md`, `register.jsonl`, `raw/members.jsonl`, `WITHHELD.json`, `LICENSES/**`, `rules/**`, `schemas/**`
   and `views/**`. This fixes the baseline gaps, where `manifest.json`, `DATASHEET.md` and `EXCLUDED.json` were
   unhashed [audit/corpus.md §3.1.3 P3].
3. Lines are sorted bytewise by path. The file ends with LF. No dotfiles exist (H.1.5).
4. It is written last, after `corpus.json` is complete with `release` and `sealed`.

### H.5.4 Content digest and root digest

- `content_digest = "sha256:" + sha256(JCS(manifest without "content_digest", "release", "sealed"))`. It is
  identical across rebuilds from the same inputs and function versions, whatever the release date.
- `root_digest = "sha256:" + sha256(bytes(checksums.sha256))`. It fingerprints a specific release tree. A
  bundle cannot contain its own hash [landscape/prov_semantics.md §10.2(5)], so the root digest MUST NOT appear
  inside the corpus. It is published in the deposit manifest (H.10.3), in the corpus tag annotation (L.3.2) and in
  the release notes.
- Python API (`agentprov.corpus.integrity`):
  ```python
  def write_checksums(root: Path) -> Path
  def verify_checksums(root: Path, *, closed_world: bool = True) -> ChecksumReport
  def root_digest(root: Path) -> str
  def content_digest(manifest: Mapping[str, Any]) -> str
  def set_digest(pairs: Iterable[tuple[str, str]]) -> str
  ```

### H.5.5 Verification levels

The command is `agentprov verify --corpus ROOT --level {checksums,chain,rederive}` (MN N.2.6).

| Level | Checks | Needs |
|---|---|---|
| `checksums` | Every listed file matches. No unlisted file (closed world) | stdlib only |
| `chain` | `checksums`, plus: manifest schema; `content_digest`; `digests.*` recomputed from files; index paths recomputed; every AER seal re-hashed; included raw objects re-hashed and AER `artifacts[].sha256` matched; a referenced (not stored) object only for a snapshot whose declared raw policy is `reference` (`raw.reference.not_permitted`, failed; D-160); **each member object's CRC32 and size checked against `raw/members.jsonl`** (AD-12); SEM and PROV input digests matched; index facets re-derived from AER/SEM; every execution file present under `aer/`, `sem/`, `prov/` named by an index row (`index.orphan`, sealed corpora; P-1, D-162); register ↔ index ↔ counts reconciliation (H.6.1 R5), including every snapshot id a row names declared in `sources[].snapshots` (`index.snapshot.undeclared`) a row's `n_origins` equal to the `raw/origins.jsonl` lines of its primary artefact (`index.n_origins`; H.7.2(1)), and a row's `status` equal to the one its stages and its issues' register severities give (`index.status`; H.3.2(1), CB-11); snapshot `candidates == executions + not_imported`; `rules/**` digests compared with the installed package's catalogues at the recorded versions (`rules.mismatch`, `rules.unavailable`); `schemas/**` compared byte for byte with the package's published schemas (`schemas.mismatch`, `schemas.unavailable`), `WITHHELD.json` declared in `files` (`withheld.undeclared`), `raw/REFERENCES.json` declared in `files` (`references.undeclared`; D-237) and every `views/` file backed by a `views` stage and an index row (`views.undeclared`) (sealed corpora; P-2, D-163); **withholding** (sealed corpora; H.4.5; D-230..D-236): `WITHHELD.json` valid (`withheld.invalid`) with its schema copy, a tombstoned or otherwise absent object accepted exactly when `WITHHELD.json` lists it, no listed object or file of a listed execution in the tree (`withheld.present`), no index row for a listed execution (`withheld.row`), a `release.withheld` entry for each listed execution (`withheld.unregistered`) and a listed execution for each such entry (`withheld.unlisted`), each entry's origins equal to its `raw/origins.jsonl` origins (`withheld.origins`), no row of a `withhold` snapshot (`withheld.policy`), and no released file outside `rules/**` and `schemas/**` matching a rule of the source profile's `[withhold]` policy (`withheld.rule_hit`; `withheld.policy_invalid`); for an issue rule, no released execution carrying its code in its index row, a register entry or its AER seal (`withheld.issue_released`), and every finding of the rule naming an execution the register records with the code (`withheld.issue_unsupported`; D-314); nothing the corpus spec's `[withhold]` table lists released, neither an
object among the files nor an execution in the index (`withheld.listed_released`; D-964); a split descriptor and its parts listed all or none (`withheld.split_part`), and a carved blob and its source likewise (`withheld.carved`; D-315); no container of a withheld object, at any level of `raw/members.jsonl`, released (`withheld.container`; AD-12, D-461); every released stored archive read decoded by the rule rescan, and one it cannot read failed (`withheld.unscanned`; D-450) | core deps only (D10) |
| `rederive` | `chain`, plus re-running every stage from raw (H.8.5) and requiring identical digests; on a sealed corpus, index rows that differ from the re-derivation outside their outputs (status, issues, completeness) are `rederive.index_refreshed` (failed, or unverified when a declared version differs; CB-11). Executions that need an object the corpus accounts for as absent (tombstoned, withheld, referenced) are `unverified`, not refused (H.4.5(6); BF-20, CB-6). It re-runs `expand` in T1 and requires identical member digests (AD-12). It loads profiles and catalogues **only from package resources** at the recorded version; the corpus `rules/` copy is never loaded (AD-14). The package ships every released catalogue version; an absent version is `rules.unavailable` | core deps; referenced objects must already be in the fetch cache (`agentprov fetch`), otherwise reported `unverified` (not passed) |

Inputs are opened safely (R-44):

- **Tree mode.** Every relpath is validated with `logical_name` and the H.1.3 grammar before it is opened
  (no-follow, `S_ISREG`; G.3.6).
- **Archive mode.** `verify` reads deposit archives directly, extraction-free, in T1 (G.3.5). Member labels are
  checked against the closed-world `checksums.sha256`; nothing is written to the filesystem.

Release mode needs `--root-digest` (a root digest published outside the corpus) in tree mode and in archive mode, for
a deposit directory as for a lone meta archive: no file inside a corpus or a deposit anchors it (exit 2; D-39, D-620).
For a deposit directory it needs one for **every** corpus of the deposit: a corpus no given digest matches is
`root_digest.missing` (failed, naming the corpus; D-641).

`verify` MUST exit 0 only if every requested check passed. A skipped check (for example, unavailable referenced
raw) is reported as such and produces exit status 1 in release mode (D8). An object listed in `raw/tombstones.jsonl`
or, for referenced raw, in `<cache>/tombstones.jsonl` (H.1.2; G.9.6) is reported as `tombstoned`, with its reason
and date, never as silently missing; a check that would need its bytes is reported skipped. A tombstoned object that
`WITHHELD.json` lists is not a finding: the corpus version withheld it (counter `tombstoned_withheld`; D-232). Release-mode
verification that reads archives refuses to run below Python 3.14.8 (exit 3; AD-16).

---

## H.6 Issue register and "seal, don't discard"

### H.6.1 The rule

- **R1 (accounting).** Every candidate matched by a snapshot's include globs, and not removed by an exclude glob,
  MUST receive exactly one disposition: an execution row in `executions.jsonl`, possibly with `status: failed`, or a
  `register.jsonl` entry with `disposition: not_imported` and a reason code. In a sealed corpus that withholds
  (H.4.5), a withheld execution's disposition is its `release.withheld` entry (`disposition: withheld`) together with
  its `WITHHELD.json` listing; it has no row and is not among the snapshot's `candidates` (D-231). Every exclude glob carries a code, and
  its matches are counted in `selection_excluded` (H.2.3). For a `multi_execution` file (D-320, D-321) the candidates
  are its located items, each an execution row, and its rejected rows, each a `not_imported` entry with the subject
  `{source_key}`. The file itself is then a candidate only when it is sealed whole (one degenerate AER, `{"p": ""}`)
  or registered whole (no execution and no rejected row). Such a `{source_key}` entry can be attributed only in a
  single-snapshot corpus (`corpus.manifest.unattributed` otherwise; D-321).
- **R2 (sealing).** Any candidate that passes ingest safety (D8 tier 1) and is accepted by a reader MUST yield a
  sealed AER, even when it records no execution. Such an AER has `unit: outcome_only`, a header, judgements and a
  seal with issue `no_execution_observed` (register code `map.no_execution_observed`). No empty trajectory is
  fabricated [landscape/trace_formats.md §6.7].
- **R3 (failures kept).** If mapping, semantics or PROV derivation fails for an execution, its raw evidence and any
  stage outputs that succeeded are kept. The row gets `status: failed` and a register entry gives the stage and
  rule.
- **R4 (no deletion).** Nothing is removed from a sealed corpus version. A correction is a new corpus version. Its
  `CHANGELOG.md` entry and register entries (`subject.previous`) name what changed.
- **R5 (reconciliation).** For every snapshot, `candidates == executions + not_imported`. `counts.issues_by_code`
  equals the register's tallies. Every code in a row's `issues` has a register entry with that `ex`. `verify
  --level chain` enforces all three.
- **R6 (filters are views).** Completeness classes, outcome validity, scored/unscored and similar selections are
  computed over the index. They never remove rows or files.
- **R7 (live attempts).** Every live attempt, including exceptions, aborted passes and accounting-inconsistent runs,
  is sealed as its own execution with an `attempt` index. A re-attempt never overwrites. This makes selection
  effects measurable (D5; CAP-5 [manuscript/review_feedback.md §1.2]; [audit/capture.md §9.4]).

### H.6.2 `register.jsonl`

Format id `agentprov-register/0.1`; defined as a `$defs` entry of `schemas/corpus-0.1.schema.json` (H.2.1); Python
type `agentprov.corpus.register.RegisterEntry`. Rows are sorted by `(subject_key, code)`. G's former
`rejections.jsonl` is merged into this file (stage `ingest`; R-13): there is one register.

| Field | Type | Meaning |
|---|---|---|
| `rid` | string `r_` + 20 base32 chars | `b32(sha256("agentprov-reg/1\n" + JCS({subject, code, stage})))[:20]` (stable) |
| `subject` | `{ "ex": string }` \| `{ "source_key": string }` \| `{ "snapshot_id": string, "path": string }` | `path` is the candidate's origin-relative path (an archive member's label for members), used only when no object was stored |
| `subject_key` | string | Sort key: `ex`, else `source_key`, else `snapshot_id + ":" + path` |
| `code` | string | H.6.3 |
| `severity` | `"info"` \| `"warning"` \| `"error"` | |
| `stage` | `"select"` \| `"ingest"` \| `"expand"` \| `"map"` \| `"sem"` \| `"prov"` \| `"validate"` \| `"capture"` \| `"package"` | RESOLUTIONS §3.8 |
| `disposition` | `"sealed"` \| `"not_imported"` \| `"failed"` \| `"withheld"` | `withheld` only with `release.withheld` (H.4.5) |
| `rule` | string \| null | `<ns>.<rule>@<n>` that raised it |
| `detail` | string, ≤ 200 chars | Generated text. It MUST NOT quote raw content (payloads are untrusted) |
| `owner` | `{ corpus_id, source_id }` \| null | For `select.owned_elsewhere` and `dedup.*` |
| `ids` | array of string | AER local ids concerned (from `seal.issues[].ids`) |
| `previous` | `{ corpus_version, rid }` \| null | Links to a superseded entry (R4) |

### H.6.3 Code vocabulary

There is **one code registry with two layers** (R-13; RESOLUTIONS §3.8):

1. **AER seal issues** are one closed list owned by C (C.12.3 ∪ D.5.5, synonyms merged: `identity_conflict`,
   `accounting_inconsistent`, `accounting_unverifiable`). Adapter codes are `<ns>.<code>`, declared with a default
   severity in the catalogue's `issue_codes` (D.5.5).
2. **Register codes** are `<area>.<code>`. For stage codes the area is the register stage; the cross-stage areas
   are `dedup`, `worker`, `time`, `release`, `rules` and `raw`. A seal issue enters the register as `map.<code>`
   (adapter codes as `map.<ns>.<code>`) and is never re-namespaced to an adapter.

Severity is `info|warning|error`. The core register codes form a closed set:

| Code | Stage | Sev. | Disposition | Meaning |
|---|---|---|---|---|
| `select.owned_elsewhere` (+ `owner`) | select | info | not_imported | The source key belongs to another corpus (H.7.3) |
| `select.not_execution_artefact` | select | info | not_imported | Aggregators, cell lists, caches |
| `select.dialect_planned` | select | info | not_imported | No v0.1 reader or profile for the format, variant or producer band (e.g. ASB CSV; DRIFT's ASB logs; Inspect `.eval` outside band `0.3.247.dev69`; AgentDyn B/C until their profiles pass) |
| `select.licence_blocked` | select | info | not_imported | Licence forbids even local import for this corpus's purpose |
| `select.out_of_scope` | select | info | not_imported | An execution outside the in-scope part of a mixed-scope source, excluded by a profile rule that cites the scope decision (D-143, D-191; e.g. AgentOps-Bench clean and noisy non-safety runs) |
| `select.redaction_pending` | select | info | not_imported | An execution a profile holds back, by an `[import] exclude` entry, until a pending redaction covers it (D-182; D-324, R-10p-5). It is in scope and not owned elsewhere, so `out_of_scope` would mislabel it. It counts in `selection_excluded`, and a later profile version that can redact imports it |
| `ingest.<area>.<kind>` (G.3.9 closed list, e.g. `ingest.size.file`, `ingest.archive.traversal`, `ingest.archive.crc`) | ingest | error | not_imported | D8 tier 1 **resource or safety** violation (G.3.9): no bytes kept beyond sha256 (when computable), size, origin and the effective limit; an archive member also gets its `raw/members.jsonl` row. A **policy or parse** violation on bytes within limits is not an `ingest.*` row: the bytes are stored, a degenerate AER is sealed, and the seal issue (`unparseable_artefact`, `unsupported_variant`) enters as `map.<code>` with the `ingest.*` code in `detail` |
| `ingest.interpreter.unpatched` | ingest | warning | sealed | Dev mode only: archive or compressed-stream ingestion ran below Python 3.14.8; recorded with `producer.interpreter_advisory` (G.3.8; AD-16). Release mode refuses instead (exit 3), and `package` refuses a corpus that carries the advisory |
| `expand.*` | expand | error | failed | The `expand` stage failed for a container, or a re-expansion at `rederive` gave member digests that differ from `raw/members.jsonl` (AD-12). Format violations inside the archive use `ingest.archive.*` |
| `map.<seal code>` | map | per C.12.3 / D.5.5 or the catalogue | sealed (failed for `unparseable_artefact`, `adapter_defect`, `ex_conflict`) | Every AER seal issue, e.g. `map.no_execution_observed` (warning; outcome without trajectory: 207 AgentDojo empty logs, 2 ROPE; `unit: outcome_only`), `map.incomplete_run` (warning; source lacks outcome fields: 1 AgentDojo HEAD log [audit/legacy_replay.md §2.1]), `map.accounting_inconsistent` (warning) and `map.accounting_unverifiable` (info) [audit/capture.md §9.4], `map.aborted_attempt`, `map.capture_error`, `map.adapter_defect` (error; the reader or mapper raised; raw is kept) |
| `worker.limit.<cpu\|rss\|wall\|output>` | (stage of the job) | error | failed | A T1 worker exceeded a resource limit (A3; G.4.6); the unit is also sealed as `adapter_defect` where an AER exists |
| `time.implausible` | validate | warning | sealed | A §6.2 "MAY flag" diagnostic (A5): a claimed run time later than the `committed_no_later_than` date of its blob or than acquisition. The value is never corrected (G T-15) |
| `capture.quarantined` | capture | error | not_imported | T0's literal-value secret scan hit a staged file; nothing from the session is stored (R-51; G.6). Subject `{snapshot_id: <campaign>, path: <session id>}` |
| `sem.failed`, `prov.failed` | sem, prov | error | failed | Stage failure |
| `validate.failed` | validate | error | failed | A gating check failed. The check id is in `detail` |
| `dedup.collapsed` | select | info | sealed | Identical bytes found at more than one origin (H.7.2) |
| `release.withheld` | package | info | withheld | The execution's raw and derived files are withheld (H.4.5; G.9.5) |
| `rules.mismatch` † | validate | error | — | A corpus `rules/**` copy differs from the package catalogue at the recorded version (AD-14) |
| `rules.unavailable` † | validate | error | — | The recorded catalogue version is not shipped by the installed package (AD-14) |
| `aer.rules.drift` † | validate | error | — | The `aer` stage records a catalogue version the package ships, with other bytes: the corpus was built while that catalogue was edited in place. Reported once per catalogue by `validate`, `verify` (chain) and `recompute`; the rows that declare it get the one check `aer.rules.drift` in place of the AER-rule and tier-4 checks, `recompute --out` refuses, and `verify --level rederive` does not re-derive. Checked at the building commit (D-460, D-430) |
| `raw.reference.unpinned_origin` † | ingest | error | not_imported | A `REFERENCES.json` origin matches no in-package profile origin; it is never contacted (R-43; G.7.5) |
| `raw.origin.unpinned` † | ingest | error | — | A git origin names a branch, a tag or nothing instead of a 40-hex commit; the command refuses (exit 3) (G.7.5) |
| `raw.origin.blob_mismatch` † | ingest | error | failed | An object does not match its pinned git blob id or digest (`verify --against-pins`; G T-14) |

† These codes arise before a build, or during `verify`, `recompute` or `fetch` on an existing corpus. They are
reported in the command summary (`agentprov-cli-summary/0.1`) and, for `recompute --out`, in the new tree's
register; they are never written into a sealed corpus.

Examples of seal issues as register codes: `map.earlier_attempts_unobservable` (info),
`map.retry_passes_inferred` (warning; the third-pass `null` rule, 82 logs at upstream HEAD),
`map.outcome_imposed_by_runner` (warning; run errors). Adapter-namespaced examples, declared in the `agentdojo`
catalogue's `issue_codes` (D.5.2): `map.agentdojo.pipeline_name_mismatch` (warning; 11,765 HEAD logs)
[verify/agentdojo.md §3], `map.agentdojo.path_field_mismatch` (a path component named by the profile layout
disagrees with the log's field; reported, never corrected; D.6.3 R-PATH).

### H.6.4 Replacing `EXCLUDED.json`

The baseline wrote the 207 empty logs to `EXCLUDED.json` as `{reason, count, logs: [{log, trace, pipeline, suite,
user_task_id, injection_task_id, attack_type, utility, security, wall_clock_s, reason}]}`
(`convert_runs.py:80-84`; [baseline/BASELINE.md §4.7]). Under R2 they become sealed executions with
`execution_observed: false` and issue `map.no_execution_observed`:

- their logged outcomes are AER `judgement` records (O, `by: source`), and so appear in the `outcome` facet;
- their identities come from AER and the index;
- the "excluded" count the old manuscript read (`conv_excluded.json`, [manuscript/figure_pipeline.md §3.5]) is
  `counts.issues_by_code["map.no_execution_observed"]`;
- their rows have `unit: outcome_only`, so they are counted in `counts.by_unit.outcome_only` and never as agent
  executions (R-28; NC-ALL-13).

---

## H.7 Duplicates and lineage

### H.7.1 `source_key`

```
source_key = "sha256:" + artefact_sha256_hex + "#" + JCS(loc)        # always with "#" (R-03, AD-04)
```

In the AER the same key is C's object `source_key {sha256, loc}`; the index and the register use the string form
above. `loc` is the AER in-artefact locator in C's canonical form (C.9; RESOLUTIONS §3.4)
[landscape/trace_formats.md §6.9]:

| Case | `loc` |
|---|---|
| Whole artefact, not parsed | `{}` |
| JSON document root (every AgentDojo-family log, one execution per file) | `{"p":""}` |
| Element of a JSON array (STAC records, planned) | `{"p":"/<i>"}` |
| JSONL line (**0-based**) | `{"line":n}` |
| Archive member (e.g. an Inspect `.eval` sample) | the member is its own object (AD-12), so `artefact_sha256_hex` is the **member object's** sha256 and `loc` addresses inside it; there is no archive-member locator member |

`bytes` never enters the key when `line` or `p` is present. A live execution's source key is the digest of its
capture log plus `{}`, or a locator when the log covers several executions. The function is
`agentprov.corpus.dedup.source_key(artefact_sha256: str, loc: Mapping) -> str`; `corpus/dedup.py` also applies
ownership, received by dependency injection from the registry (MN M.5). Its key vectors are generated from the same
function as C's and K's execution-id KATs.

### H.7.2 Within a corpus: collapse

1. Two candidates with the same source key and the same mapping identity (H.7.7) MUST be mapped once. The single
   execution row lists every snapshot in `snapshot_ids`, and every origin appears in `raw/origins.jsonl`. As built
   (D-202): the AER records the origin of the snapshot imported first; the manifest keeps the snapshots in import order,
   which `recompute` replays, so a re-map is byte-identical.
2. A `dedup.collapsed` info entry records the collapse.
3. For example, the 14,182 AgentDojo files that are byte-identical at the June-2024 and HEAD commits are 14,182
   executions with two origins each in a corpus holding both snapshots [sources/agentdojo.md §5.1]. The released
   layout for `agentdojo-upstream` is two corpora (D-35), where they are one execution in each.

### H.7.3 Across corpora: ownership

1. Each source key MUST have exactly one **owner** corpus.
2. Ownership is declared once, in the owner profile's `[lineage]` table (`owns`, `excludes`; R-45). The precedence
   is: original publisher, then re-packager, then mirror. The registry is the only status store.
3. A non-owner's selection MUST exclude the artefact with `select.owned_elsewhere` and an `owner`. If it was
   discovered anyway, its register entry carries `owner`. `corpus/dedup.py` applies this at selection time.
4. Cross-corpus ownership checks over sealed corpora (formerly the collection builder's failure on a source key that
   is an execution in two corpora, and `verify --collection`) are deferred with collections (AD-10 row 6). In v0.1,
   ownership is enforced at selection time only.

### H.7.4 Logical key

```
logical_key = "lk_" + b32(sha256("aer-lk/1\n" + JCS(cell)))[:26]      # agentprov.corpus.index.logical_key(cell)
```

1. `cell` is the adapter-declared coordinate object. The AgentDojo family uses `benchmark`, `suite_set`, `suite`,
   `user_task`, `injection_task`, `attack`, `pipeline` (with defence), `model` (requested),
   `attack_params_sha256` (for example the addressed model display name, CAP-8) and `repeat` (live repeat index, or
   `null`).
2. The logical key links **replicates and re-runs**. It MUST NOT be used to deduplicate. Its reliability is only
   as good as the evidence class of its weakest member, which the row's `ev["cell.*"]` records.
3. `logical_key` is `null` when a required coordinate is unknown.

### H.7.5 Collection manifest (deferred, AD-10 row 6)

Collections, `package --collection` and `verify --collection` are **not in v0.1**; the deferral is recorded in
`docs/roadmap.md`. The design below is kept as the v0.2 starting point. Only `LineageDecl` is used in v0.1: in the
owner profile's `[lineage]` and in `corpus.json` `sources[].lineage`.

`collection.json` (format `agentprov-collection/0.1`, deferred) holds:

- `collection_id`, `collection_version`;
- `corpora: [{corpus_id, corpus_version, content_digest, root_digest, licence_spdx}]`;
- `duplicates: {path: "duplicates.jsonl", sha256, n}`. Each row of `duplicates.jsonl` is
  `{source_key, owner: {corpus_id, ex}, others: [{corpus_id, disposition}]}`;
- `lineage: [LineageDecl]`;
- `poolable: [[corpus_id, corpus_id, basis]]` (empty by default);
- `content_digest`.

A future builder would read only sealed corpora; no module is reserved for it in v0.1 (RESOLUTIONS §3.2).

`LineageDecl = {relation, target: Origin | {corpus_id}, basis, ev}`, with `relation` ∈ `mirrored_by`,
`vendors_tasks_from`, `fork_of`, `replicates_cells_of`, `repackages`, `owned_by`.

### H.7.6 Concrete cases (v0.1)

| Case | Evidence | Treatment |
|---|---|---|
| Baseline `runs/` ⊂ upstream | All 18,234 baseline blobs are in the `runs/` trees of `c2748856`, `9d7d1391`, `7d1de5a1`, `ae8d2c01` and `15de4430`; the exact copy commit is undecidable [verify/agentdojo.md §5.1] | The origin is always the pinned upstream commit, never the baseline copy or the Google Drive archive [audit/legacy_replay.md §2.1, §12.2]. The local baseline `runs/` MAY serve as a fetch cache, but only after each file's git blob SHA-1 and sha256 are checked against the pinned tree; migration uses it only for gate G0 (AD-07). The `2024-06` snapshot (`c274885…`, 18,241 blobs = baseline 18,234 + 7 Mixtral) supersedes the converted tree only after the full R1/R2 claim gate passes with 0 mismatches (AD-07; H.4.2) |
| June-2024 vs HEAD generations | 4,052 baseline paths differ at HEAD (distinct executions, re-runs of 2024-07-16/17); HEAD mixes generations *within* pipelines [verify/agentdojo.md §5.1–§5.3] | Both snapshots are in one corpus; their distinct records are never conflated. Generation is per file: object-level `git` origins SHOULD carry `introduced_in` (the introducing commit). Rule `agentdojo.committed_no_later_than@1` (D) turns its date into an upper bound on run time, kept in `ext` only and never a PROV time (D.5.4) [sources/agentdojo.md §8.1]. Facet `x.agentdojo.upstream_generation` is derived from it. Superseded history blobs (11,173) are part `history`, planned |
| AgentDojo-Inspect | `runs/` is a 100 % byte-identical inheritance of AgentDojo logs; no Inspect logs [sources/agentdojo-inspect.md summary], [verify/agentdojo-inspect.md] | No corpus. Listed in corpus `agentdojo-upstream`, `sources[0].mirrors` and `lineage` (`mirrored_by`, `usnistgov/agentdojo-inspect@a491020f…`). Any import of it resolves to source keys owned by corpus `agentdojo-upstream` (source `agentdojo`) |
| ROPE ⊃ AutoDojo-attack runs | AutoDojo executions exist only in ROPE (2,847); the AutoDojo repo holds caches, not executions [sources/autodojo.md summary], [verify/autodojo.md claim 21] | No AutoDojo import corpus. Facet `x.rope.attack_family = "autodojo"`. AutoDojo caches are not imported (`select.not_execution_artefact` if discovered) |
| ROPE ↔ AgentLAB | `agentlab/res` (13,525 files) is byte-identical AgentLAB content, not ROPE executions [sources/rope.md §2] | Excluded by selection (`select.owned_elsewhere`, owner AgentLAB) |
| ROPE ↔ AgentDyn | ROPE vendors AgentDyn suites; same task ids, different executions, and `shopping` injection-task ground truths differ [sources/agentdyn.md §5], [verify/autodojo.md claim 19] | Not duplicates. `suite_set` identities differ, so logical keys differ. Analyses join on `task` facets, with evidence classes |
| DRIFT ↔ AgentDyn | 949 AgentDyn `src/…/drift/runs` logs are byte-identical to DRIFT HEAD runs; AgentDyn `runs/*-drift` are distinct replicates; 620 DRIFT AgentDyn-suite logs equal AgentDyn history `4d2748c` [sources/agentdyn.md §5] | DRIFT owns the 949 (AgentDyn excludes them; edges E09/E10). Replicates are linked by logical key where cells match. History is not imported |
| AgentDyn variant C ↔ AgentDyn history | Variant C's executions are author-rekeyed copies of **AgentDyn's own** history blobs (`runs/DRIFT/**`), not of `SaFo-Lab/DRIFT` history (A6 as corrected, R-62) | Owner `agentdyn`; edge E11 targets `agentdyn` · `history`; the curation step is recorded. Variant C is `partial` (stretch) |
| Survey ↔ AgentDojo | The survey's Zenodo zip re-packages upstream `runs/` (36,679) [sources/agent-security-tools-survey.finding.json] | Excluded by selection; owner corpus `agentdojo-upstream` (source `agentdojo`) |
| Survey AgentDojo runs ↔ survey AgentHarm logs | Same source and origin, different licence classes (AgentHarm use clause) [verify/agent-security-tools-survey.md §2.1] | Two corpora: `ast-survey-agentdojo` excludes the AgentHarm logs with `select.owned_elsewhere`, owner `ast-survey-agentharm` (H.4.2) |
| Mandate ↔ AgentDojo | Independent re-runs of the same banking cells as upstream 2024 gpt-4o; 0 byte-identical; pipeline-name collision [verify/mandate-agentdojo-eval.md §3.3] | Not duplicates. Different `suite_set` and pipeline give different logical keys. Execution paths are id-based, so the name collision that broke the baseline converter cannot occur [verify/agentdojo.md §6] |

### H.7.7 Execution-id mapping identity

> **Resolved (AD-04 / R-03):** C-D2 is accepted and amends D2. The import execution id is
> `"ex_" + lower(base32_nopad(sha256(b"aer-ex/1\n" + mapping_id + b"\n" + sha256_lower_hex + b"\n" + JCS(loc))))[0:26]`,
> computed by the one function `agentprov.aer.ids.import_execution_id`, with mapping id
> `"<adapter id>/<profile id>"` (e.g. `agentdojo.tracelogger/agentdojo-upstream`) and the locator canon of H.7.1.
> Adapter and profile *versions* stay excluded. The C.16.1 artefact with `{"p":""}` gives
> `ex_7uz2oys57hugtsueixylme4fl5`; C.4.1 and K.5.2 own the vectors and carry them identically.

Rationale (kept from the challenge). D4 makes **one** AgentDojo-family importer serve several sources through
profiles with different rules (ROPE system-prompt line, DRIFT-extended dialect, AgentDyn variants). Had the formula
used the importer id alone, the same bytes mapped under two profiles would get the same `ex`. The resulting AERs
differ, but their instance IRIs `https://w3id.org/agentprov/exec/<ex>#…` (D7) would collide. That recreates the
cross-graph node-conflation defect D7 is meant to remove [audit/validation.md §7 V13], [audit/corpus.md §3.5.3 M3].
Real byte-identical cross-source copies exist (DRIFT ⊂ AgentDyn `src/`, the survey ⊃ AgentDojo `runs/`). With the
mapping identity, ownership (H.7.3) ensures each source key is published once, and `source_key` stays
mapping-independent, so cross-profile duplicates are still detected.

---

## H.8 Derivation DAG, recompute and verify

### H.8.1 Nodes and edges

```
archive containers ─expand(fn@v)─► member objects (raw/members.jsonl)                       [AD-12]
raw objects ─map(adapter/profile@v, rules@v)─► AER ─semantics(profile@v)─► SEM ─provenance(spec@v)─► PROV
     │                                           │                         │                          │
     └──────────────────────────────────────────┴─────────────────────────┴──► validate(checks@v) ──► results
                                                                                                         │
            index (facets from AER/SEM) ◄───────────────────────────────────────────────────────────────┘
                 └─► manifest ─► datasheet, changelog ─► checksums ─► archives ─► deposit
views/transcript-v1  = an optional further function of the AER, its own node (AgentDojo family only)

outside the DAG (consumers; nothing re-enters the corpus):
  stats(corpus)  ─► per-source tables          render(PROV bundles) ─► images        derive --trig ─► TriG
```

Every per-execution node is a pure function of its inputs (D0). Corpus-level nodes (index, manifest, datasheet,
checksums) are pure functions of the per-execution nodes, the spec and the release arguments. The `expand` stage
is a pure function of the container bytes and the effective ingest limits; its output member objects are derived
objects, re-derived by `rederive` (AD-12).

**Consumers (Addendum B AD-10).** Two consumers are kept in v0.1 and live outside the DAG:

- `agentprov stats` (`src/agentprov/stats/`) computes minimal, generic statistics from a corpus: counts per source
  and status; PROV statements by evidence class, bundle and rule; unknown-reason proportions; and the per-source
  information-loss table that the paper needs. It reads the manifest, index, register, AER and PROV files only. Its
  output carries the corpus `content_digest` and its own function digest, and any cache of it MUST be keyed by
  `(content_digest, fn_digest)` (H.8.3).
- `agentprov render` (`src/agentprov/render/`, optional `render` extra: pydot + graphviz) is the baseline
  `visualize.render_prov_graph` ported to read `agentprov-prov/0.1` bundles, the core bundle only by default. Renders
  are not byte-reproducible, so they are never part of a corpus or a deposit; the output records the renderer
  versions.

Neither writes into a corpus (H.1.5(6)). `views/stats`, views in deposits, the ML export and the other AD-10
deferrals remain deferred; the frozen baseline stays the home of the deferred analyses until they are ported.

### H.8.2 Function identity (`derivation.json`)

`derivation.json` lists the stage definitions used for this corpus:

```json
{"format": "agentprov-derivation/0.1",
 "stages": [
  {"stage": "expand", "fn": "expand", "engine": "agentprov@0.1.0", "engine_code_sha256": "sha256:…",
   "limits_sha256": "sha256:…", "fn_digest": "sha256:…"},
  {"stage": "aer", "fn": "map", "adapter": "agentdojo.tracelogger@0.1.0", "adapter_code_sha256": "sha256:…",
   "profile": "agentdojo-upstream@1", "profile_sha256": "sha256:…",
   "rules": {"agentdojo": 1, "aer": 1}, "rules_sha256": {"agentdojo": "sha256:…", "aer": "sha256:…"},
   "format": "aer/0.1", "fn_digest": "sha256:…"},
  {"stage": "sem", "fn": "semantics", "profile": "agentdojo.suites@1", "profile_sha256": "sha256:…",
   "engine": "agentprov@0.1.0", "engine_code_sha256": "sha256:…", "format": "sem/0.1", "fn_digest": "sha256:…"},
  {"stage": "prov", "fn": "provenance", "spec": "agentprov-prov/0.1", "rules": {"aprov": 2}, "rules_sha256": "sha256:…",
   "engine": "agentprov@0.1.0", "engine_code_sha256": "sha256:…",
   "options": {"context_encoding": "members"},
   "serialisers": {"prov": "3.2.2", "rdflib": "7.6.0"}, "fn_digest": "sha256:…"},
  {"stage": "validation", "fn": "validate", "checks": ["…@…"], "libraries": {"…": "…"}, "fn_digest": "sha256:…"}],
 "lockfile_sha256": "sha256:…",
 "python": {"implementation": "cpython", "version": "3.14.…"}}
```

1. `fn_digest = sha256(JCS(stage definition without fn_digest))`. `rules` uses the AER header form
   `{"<ns>": <int>}` (AD-18). In `expand`, `limits_sha256` is the JCS digest of the effective `IngestLimits`
   (G.3.2), so a recorded limit override changes the function identity. The interpreter is recorded beside the
   lockfile, outside every `fn_digest`, so that an interpreter-induced output change surfaces as
   `unexplained_change` (H.8.4) rather than being hidden. A `validation` stage run with tier 4 skipped lists those
   checks under `skipped` (G2c-5); the `agentprov-corpus/0.2` derivation shape takes the member (pre-round
   verification V-7; `agentprov-corpus/0.1` stays as released, D-163).
2. `engine_code_sha256` is computed as `adapter_code_sha256` is (H.2.5), over the `agentprov` modules of that
   stage. For `sem`, `prov` and `validation` these are the stage's seed directories and files plus the transitive
   `agentprov` import closure of those seeds (D-451): a pinned list in `agentprov.stage_scopes`, read by both the
   importer and `derive`, that a test recomputes from the source. `prov/compat/` stays outside the `prov` scope even
   though `prov/specs.py` looks its spec up lazily: the frozen oracle is its own stage. For `expand` the modules are
   `raw/members.py` and its import closure (`raw.members.EXPAND_MODULES`, recomputed by the same test; D-451 addendum,
   BF-39). For `aer` they are `adapters/runner/` and `aer/`, plus the import closure
   of the map path and `aer/`, plus what the profile's family imports from outside `adapters/<family>/`
   (`stage_scopes.aer_scope`).
3. **Several `expand` entries (D-380).** One import may run several expansions: an archive input, the nested
   archives it declares (D-382), and a container dialect's members, each with its own `selection_sha256`. Each is
   one `expand` entry with its own `fn_digest`, and a member row carries the `fn_digest` of the expansion that listed
   it. Every reader of `derivation.json` keys `expand` entries by `(stage, fn_digest)` (`agentprov.corpus.stages`)
   and compares them as a set (H.8.4). `selection_sha256` covers a selection's declared nested archives
   (`children`) only when it has some, so every earlier digest is unchanged.
4. The serialiser and validator library versions are part of the function identity. RDF output details are
   library behaviour, and the baseline recorded none of them [audit/validation.md §7 V19],
   [audit/corpus.md §3.7 V4]. The version values above are those of the baseline environment
   [baseline/BASELINE.md §1.2]. They are illustrative only. The real values come from the lockfile.

### H.8.3 Derivation keys (the build cache is deferred)

```
dk(stage, ex) = "sha256:" + sha256(JCS({"fn": fn_digest(stage), "in": [input digests in role order]}))
```

`dk` is the identity of one derivation step; EF uses it for bundle identity. The content-addressed build cache keyed
by `dk` is **deferred** (AD-10 row 11). In v0.1, resume is keyed on the sealed-AER key (D.2.9), never on the
existence of an output file. The baseline keyed resume on file existence and wrote no derivation versions
[audit/legacy_replay.md §5], [audit/corpus.md §3.3 R6]. When the cache returns, it lives outside every corpus
(default `$XDG_CACHE_HOME/agentprov/derive/`) and maps `dk` → output digest + content-addressed output bytes.

Caches of derived statistics (`agentprov stats` output, paper inputs) MUST be keyed by `(content_digest, fn_digest)`.
They MUST NOT be keyed by a hand-bumped version number or column presence [audit/corpus.md §3.4.3 S2],
[manuscript/figure_pipeline.md §7.4].

### H.8.4 Determinism and version-bump discipline

1. **Determinism.** The same inputs and the same `fn_digest` MUST give byte-identical outputs. This covers member
   objects from `expand`, AER, SEM, PROV-JSON (JCS or the deterministic key order of D7), validation rows, the index
   and the manifest. TriG is not stored (AD-10 row 3); when produced on demand by `derive --trig DIR` it is
   deterministic under the same serialiser versions but is not hashed into the corpus. CI checks determinism two
   ways: by building the golden mini-corpora twice, and by building with `jobs=1` and `jobs=N` (H.11). Two builds at different
   commits differ in the manifest's `producer` (the building commit, D-780) and nowhere else this item covers.
2. **Bump discipline.** If an output digest changes while the stage's *declared versions* (adapter, profile, rule
   ids, spec, format) are unchanged, `recompute` (and `verify --level rederive`) MUST report `unexplained_change`
   and exit 1. This holds even if the code digest changed. An intended change requires a visible version bump
   (D9). If the code digest changes and every output is identical, the change is a refactor and passes. The
   `fn_digest` that each `raw/members.jsonl` row records labels the function, and is not an output. Rows that differ
   only in it, for an expansion that pairs one to one by declared identity with the source's (a code or limits
   change), compare as identical, with a notice. Any other difference of a row is still unexplained (HL-T14;
   integration review P-2).
3. **Comparison.** `rederive` compares canonical bytes, never parsed-object equality. The baseline's
   `old_doc == new_doc` (`recompute.py:151-152`) could not see `True`→`1`→`1.0` or serialiser drift
   [audit/corpus.md §3.3 R2]. Semantic diffs are reported in addition (`recompute --show-diff N`), through the
   baseline's order-insensitive `diff_documents`, kept as `agentprov.prov.diff.diff_documents` (MN M.1.2)
   [audit/corpus.md §3.3 decision].
4. **RDF serialiser drift.** TriG is no longer a stored artefact, so no corpus file can show serialiser drift. The
   PROV-JSON → PROV-O → PROV-JSON round trip stays a validation check (AD-10 row 3). If the lockfile differs from
   the one recorded in `derivation.json`, a difference in that round trip's intermediate RDF serialisation is
   reported as `serialiser_drift` and judged by RDF graph isomorphism; the mode is recorded in the report. JCS
   artefacts never get this exception.
5. **Corpora built under older versions (D-430).** A re-map runs under the package's current source profile and
   catalogues. For a corpus whose recorded versions differ, `recompute` at this package is a **drift report**, not a
   reproduction: it lists the drift per stage (`version drift: ...` notices) and classifies as above. A writing
   `recompute` (`--out`) refuses (exit 4, `corpus.derive.version_drift`), because the output would mix versions
   (H.2.5): "re-import to upgrade, or recompute at the building commit". Reproduction of such a corpus is checked at the
   commit and lockfile that built it, where it MUST give 0 differences. The commit is the corpus's `producer.build_steps`
   entry for that stage where recorded (D-780: `producer.git_commit` for a one-step corpus), and a drift report or refusal
   prints them (`source import at commit <hash> wrote aer, ...`); otherwise it is the commit whose code digests in `derivation.json` and core lockfile digest match.

### H.8.5 Commands

The corpus operations map onto MN's flat command set (RESOLUTIONS §3.7; MN N.2, N.5). Flags not shown here are
owned by MN.

```
agentprov import    SOURCE --spec SPEC.toml --corpus DIR (--input PATH | --fetch --allow-network) [--release] [--jobs N] [--dry-run]
agentprov run       SOURCE --spec SPEC.toml --corpus DIR …                                  # live corpora (MN N.2.1)
agentprov derive    --corpus DIR [--stages sem,prov,validation,views] [--trig DIR]
agentprov validate  --corpus DIR [--release] | --card CARD.md
agentprov package   --corpus DIR --corpus-version X.Y.Z [--release-date YYYY-MM-DD]
agentprov verify    --corpus ROOT [--level checksums|chain|rederive] [--sample N --seed S] [--release] [--jobs N]
agentprov recompute --corpus ROOT (--out NEWROOT | --dry-run) [--stages expand,aer,sem,prov,validation] [--show-diff N] [--jobs N]
agentprov fetch     --corpus ROOT [--only sha256:<hex>] [--cache-dir DIR] --allow-network
agentprov stats     --corpus ROOT --out DIR …                                              # consumer (AD-10)
agentprov render    --corpus ROOT --out DIR …                                              # consumer (AD-10)
```

| Operation (r1 name) | Command | Python entry point | Behaviour |
|---|---|---|---|
| build a corpus (`corpus build`) | `import --spec` (live: `run --spec`), then `derive`/`validate` as needed, then `package` | `adapters.runner.import_source` (D.2.9) writing through `corpus.layout`, `corpus.index` and `corpus.register`; sealing by `corpus.package.seal(root: Path, *, corpus_version: str, release: ReleaseArgs \| None = None, dry_run: bool = False) -> SealReport` | Writers fill `<DIR>.partial/`; `package` seals and swaps (H.1.5). Dry-run writes nothing and returns the counts and dispositions it would produce |
| verify (`corpus verify`) | `verify` | `corpus.integrity.verify_corpus(root: Path, *, level: Literal["checksums","chain","rederive"] = "chain", jobs: int = 0, sample: int \| None = None, seed: int \| None = None) -> VerifyReport` | Read-only; tree or archive mode (H.5.5). `--sample` draws a seeded uniform random sample of executions (fixing the first-N bias of `conformance_summary`, [audit/corpus.md §3.4.3 S3]). Release mode forbids `--sample` |
| re-derive (`corpus rederive`) | `recompute` | `corpus.derive.rederive(root: Path, out: Path \| None, *, stages: Sequence[str], jobs: int = 0, dry_run: bool = False) -> RederiveReport` | Never in place. Raw-evidence digests are verified first (fixing [audit/corpus.md §3.3 R5]); `expand` is re-run; catalogues come from the package (AD-14). Dry-run **does** validate (fixing R3). Reports per execution `identical` \| `changed_explained` \| `unexplained_change` \| `failed` \| `unverified`. A source recorded under other declared versions (profile, catalogue, record or corpus format, `apv` vocabulary) is a drift report; `--out` then refuses (H.8.4(5), D-430) |
| fetch referenced raw (`raw fetch`) | `fetch` | `raw.fetch` | H.4.3 |
| deposit (`release build`) | `package --deposit` | `release.builder.build_deposit` | H.10 |
| corpus diff, SemVer check, collections | — | — | **Deferred** (AD-10 rows 6 and 10): bumps are applied by hand and recorded in `CHANGELOG.md` |

Exit codes follow MN N.1.3: 0 ok; 1 failures (differences, failed units or checks, `unverified` under `--release`);
2 usage; 3 environment (including the release-mode interpreter refusal, AD-16); 4 refused (sealed corpus, guards);
5 unsupported; 70 internal (including profile or registry errors); 130 interrupted.

### H.8.6 Relation to the baseline recompute (what is kept, what changes)

| Baseline behaviour | Status in AgentPROV |
|---|---|
| Transcripts never rewritten (`recompute.py:180`) | Kept: raw is immutable, and so are sealed corpora |
| 0 changed on 17,664 + 18,027 [baseline/BASELINE.md §3] | Becomes migration gates A1 (JCS), A2 (bytes) and B (compat graph bytes) (J; AD-07): byte identity of `adprov-v2.3-compat` graphs regenerated from the AER alone through the deterministic transcript/v1 view (AD-02). The 18,027 converted tree is gate R: R1/R2 on golden pairs block in CI, and the full run is a claim gate |
| Enrichments never written into the release (`recompute.py:116-122`) | Generalised: every output goes to a new tree |
| Recompute imports `agentdojo` [audit/corpus.md §3.3 R1] | Forbidden. Core imports no benchmark and no `agentprov_backend`; `agentprov.corpus.*` and `agentprov.prov.*` MUST pass the import-boundary test `tests/boundary/test_import_boundary.py` (D10; A1) |
| Dict equality, no dry-run validation, non-transactional, inputs unverified, no derivation versions (R2–R6) | Fixed by H.8.3 and H.8.4 and the commands above |

### H.8.7 Provenance of the release (deferred, AD-10 row 12)

`corpus.prov.json` is not built in v0.1; the design is kept for v0.2. A future corpus MAY ship `corpus.prov.json`.
It is a PROV document that describes the corpus as a `prov:Collection` that `hadMember` each execution's PROV
document. The collection `wasGeneratedBy` the package activity, which
`wasAssociatedWith` the AgentPROV software agent (version and commit), and it is a `specializationOf` the version
DOI entity once one exists [landscape/prov_semantics.md §10.2(5)]. It uses digests, never embedded hashes of
itself. Being a derived node, it is covered by `checksums.sha256`.

---

## H.9 Datasheet generation (computed numbers only)

1. `DATASHEET.md` is generated by `agentprov.corpus.datasheet.render(manifest: Mapping, card: str,
   register_stats: Mapping, index_stats: Mapping) -> str` when `agentprov package` seals the corpus. It is written
   inside the corpus, so it lies within the checksums and the archive (REP-3 [manuscript/review_feedback.md §1.5]).
2. The prose comes only from `rules/CARD.md`, the per-corpus card in the repo. That card is written from the
   source profile's documented quirks and adapter capabilities. **No build constant may appear in the prose.** The
   baseline interpolated `AGENTDOJO_VERSION`/`BENCHMARK_VERSION` and release-specific literals into the converted
   tree's datasheet. The result was a false collection-process claim, "Generated by instrumenting AgentDojo 0.1.35
   … records per-call timing", attached to AgentDojo's own 2024 logs (`package.py:390-396`, `335-342`, `413-438`;
   [audit/corpus.md §3.1.3 P1]).
3. **Placeholders.** Numbers enter only through placeholders:
   - `{{v:<JSON Pointer into corpus.json>}}` inserts a value;
   - `{{t:<table id>}}` inserts a generated table. The generated composition section includes the `context` table (a
     snapshot's context trees, pinned objects and skipped roles, D-221) only when a snapshot has them;
   - `{{claim:<id>}}` marks a quantified sentence.

   The card lint (`agentprov validate --card CARD.md`) rejects any digit outside placeholders, except tokens
   matching an allow-list: version ids (`aer/0.1`), ISO dates, DOIs, arXiv ids, commit SHAs and section numbers.
   This mirrors the manuscript's "no number is hand-typed" discipline [manuscript/figure_pipeline.md §1, §7.1(1)]
   and answers REP-6.
4. **Claims.** A claim is a predicate over manifest values, registered in the **one claims/lint library**
   `agentprov.adapters.registry.claims`, which also serves the README and the paper (AD-10 row 9; R-45). There is
   no separate datasheet claims registry or card linter. Examples: `"no_execution_observed is nonzero"`, `"every
   execution has completeness unverifiable"`. A failing claim fails the build. Results are recorded in
   `corpus.json.datasheet.claims` [manuscript/figure_pipeline.md §7.6]. Scope words ("lossless", "complete",
   "first", "faithful") are allowed only inside a claim with an explicit scope (AR-12). The library also enforces
   the canonical claim phrases (RESOLUTIONS §3.8): "derivation-reproducible", "integrity-verifiable", "traceable
   statement by statement", and the registry-generated coverage phrase "adapter-based core; demonstrated on N
   sources in K formats (single-agent, tool-calling traces)", which is allowed only after the Inspect DoD item
   passes. A datasheet makes empirical statements, so the bare architectural phrase for the design goal is never
   used in it (AD-08 as ruled), and the I.4 must-not-claim items are lint rules.
5. **Mode guard.** A card declares `mode: import|live` in its front matter. The renderer MUST refuse a card whose
   mode differs from `corpus.json.mode`. This structurally prevents the P1 defect.
6. **Sections.** The baseline's datasheet sections are kept: Motivation, Composition, Collection process,
   Preprocessing/labelling, Uses, Distribution and licensing, Maintenance [audit/corpus.md §3.2]. Three generated
   sections are added:
   - **Evidence and information loss.** The headline is **field-group coverage** (R-57): per field group, the share
     of executions whose fields are O or D, against a fixed capability list. The observed share is reported only as
     composition. Below it, for every core AER field (and selected `ext` fields), counts of executions where it is
     O, D or I, or unknown by each of the seven `unk` reasons (`not_recorded`, `lost`, `overwritten`, `withheld`,
     `ambiguous`, `not_captured`, `not_applicable`). `not_applicable` is used only for groups that cannot exist for
     the source. This is the per-source information-loss measure D12 requires, and it is the same generic
     computation as the information-loss table of `agentprov stats` (Addendum B AD-10), so the datasheet and the
     paper cannot disagree. If any execution cannot be read or evaluated for this table, `package` refuses
     (`stats.datasheet.failures`, exit 1, listing the failure codes and counts) instead of sealing an incomplete
     table. Counts of `activity` and `artefact` records by `type`, and of the PROV statements that
     EF's generic rules G-ACT, G-USE, G-GEN and G-ASSOC produced, are listed here as disclosed extensions
     (Addendum B AD-15).
   - **Integrity and verification.** `content_digest`, the verify commands, version axes (L.1), the interpreter
     and licences.
   - **Known issues and validity caveats.** Issue-code tallies with the rule-catalogue text of each code;
     `outcome_only` and `scenario` records counted separately from agent executions (R-28); the registry status of
     each part with its caveat (R-15); compat outputs flagged `apv:RegressionOracle` (R-55).
7. The datasheet MUST state:
   - the provider-terms status and the presence of prompt-injection payloads (H.4);
   - every `licences.raw[].basis` verbatim, and every `licences.restrictions` entry (R-14);
   - NC-PROV-01: the core PROV bundles contain configuration ground truth (attack and target ids, payload fixtures,
     attacker attributions, outcomes), so they are not a blind input for detectors (AD-11);
   - for live corpora, the LLM element (`native` or `gateway_compat`) and the caveat "fake-client tested in v0.1; no
     real-model run" where it applies (AD-09, R-25);
   - the number of withheld items (H.4.5). As built (D-230): when nothing is withheld, the one line "Withheld items: 0
     (H.4.5)."; otherwise the number of objects plus executions, a sentence saying where they are listed and how a
     withheld execution can be recomputed, and a table by reason and basis with the object and execution counts and
     the public notes. The notes come from the source profile or are generated, and are escaped as in item 8. No value
     appears.
8. **Escaping (G.8.2, G.8.6, K.12.6(e); F-12C-03).** Every manifest value the renderer writes (table cells, `{{v:...}}`
   values, and the identifiers of the heading and the generated sections) is one display line: it passes
   `escape_untrusted_line` (every control, line terminator and TAB as `<U+XXXX>`) and then `escape_markdown` (`\` and
   `|` backslash-escaped; a backtick, `[` and `]` as numeric references; `<` as `&lt;` unless it opens a `<U+XXXX>`
   marker; `&` before a letter, digit or `#` as `&amp;`; for a `{{v:...}}` value at the start of a line, the marker of
   a block construct backslash-escaped). A value shown as a code span keeps its backticks only when it needs no
   escaping; otherwise it is written as escaped text, because nothing inside a code span is interpreted. Text that
   needs no escaping is written unchanged, so ordinary datasheets are byte-identical to the unescaped rendering. The
   `licences` lines are the exception: they come from the in-package source profile and are quoted verbatim
   (item 7).

---

## H.10 Deposit builder and Zenodo strategy

### H.10.1 Principles

1. The deposit builder (`agentprov package --deposit`, module `agentprov.release.builder`) is **offline**. The
   `agentprov.release` package MUST NOT import a network library or contain an upload or publish call. A test
   asserts this.
2. Nothing is published without the user's explicit instruction (D9). Publishing, which mints a DOI irreversibly,
   is always a manual action by the user. The user decided (2026-10-23, D-790) to build the upload helper, now the
   distribution `agentprov-zenodo` (`zenodo/`, module `agentprov_zenodo`; `tools/zenodo_draft.py` is its checkout
   entry; D-880). It lives outside `agentprov.release` and outside the `agentprov` package, which never imports it
   (rule 1 stands for `release`), uses the standard library only for the network, and **creates drafts only**: it needs `--create-draft`, an interactive
   confirmation (a terminal and a typed phrase naming the host; there is no `--yes`) and a token read from the
   environment (`ZENODO_TOKEN`; `ZENODO_SANDBOX_TOKEN` for the sandbox). `--target sandbox|production` is required, with
   no default. Before any network access it verifies the deposit directory offline (closed-world listing, size, sha256
   and md5 of every file against `DEPOSIT-MANIFEST.json`, archive-mode `verify` in release mode). Every request is
   checked against an allowlist of method and path before it is sent: creating a deposition, setting its metadata, a
   bucket `PUT` per file, reads, and `actions/newversion` only on the AgentPROV concept DOI recorded in the release
   metadata (never the AgentDojo-PROV concept). It never calls a publish, edit or discard action and never deletes.
   After each upload it compares the md5 Zenodo returns with the manifest's, and it reads the draft back at the end. A
   receipt beside the deposit directory prevents a second create and supports `--resume`. For a release of several
   records (D-870), `--community` asks Zenodo communities to include a draft. The receipt (format 0.2) records the
   draft's reserved DOI, read from Zenodo's answers and never reserved twice. A separate `--cross-link` step takes the
   receipts of a collection and writes `isPartOf` and `hasPart` between the umbrella draft and its member drafts. It
   writes drafts only, reads every deposition before it writes any, and refuses a published one or a receipt without a
   reserved DOI. The GUI (D-880) runs the same uploader under a pseudo-terminal where the user types each phrase,
   with `--keychain` so the token comes from the OS keychain and never passes through the GUI; Settings › Zenodo only
   prefills (`zenodo.*` settings), and `release.toml` stays the record. The token is sent only in
   the `Authorization` header and removed from everything the tool prints. Until the user decides otherwise (Addendum B
   B-2): no Zenodo deposit is made (the user runs the helper, sandbox first, in their own terminal), `package --deposit` only prepares files,
   no w3id registration is submitted (U-02; corpora carrying unregistered IRIs are not deposited), and corpus tags
   stay local.
3. Only sealed corpora with `validation.mode == "strict"` and `verify --level chain` passing can be released. The
   builder runs `verify` itself. It also requires a `release-scan.json` for the same root digest with every finding
   triaged and none `real` outside `WITHHELD.json` (G.9.4). `release-scan.json` lives beside the sealed corpus as
   `<corpus>.release-scan.json`, outside the checksummed tree, bound to the root digest (G.9.4).
4. Corpora whose `licences.policy.raw_policy` is `withhold` (every snapshot withheld), a `withhold` snapshot without a
   `WITHHELD.json`, `test_only` live corpora (H.1.1(2)) and corpora that carry an `interpreter_advisory` (H.2.7; AD-16)
   are refused. A corpus with a withholding policy in its source profile also passes the withholding backstop (D-236;
   G.9.4): no released file matches a rule of the policy (`release.refused.withhold_rule`), and a release-scan finding
   whose rule the policy's `scan_rules` names is triaged `false-positive` (`release.refused.withhold_scan`). Below 3.14.8 the builder refuses any archive or
   compressed-stream decompression before opening the object (exit 3) and refuses corpora that record
   `interpreter_advisory` (exit 4) (G.3.8(3)).
5. Corpora of different licence classes are not mixed in one deposit without the explicit override (H.10.6).

### H.10.2 Command and API

```
agentprov package --corpus ROOT [--corpus ROOT ...] --deposit DEPOSIT_DIR --metadata release.toml
                  --release-date YYYY-MM-DD [--max-archive-bytes N]
```

`agentprov.release.builder.build_deposit(corpora: Sequence[Path], metadata: ReleaseMetadata, out: Path, *,
release_date: date, max_archive_bytes: int = 2**31) -> DepositReport`

```
agentprov package --index INDEX_DIR --part RECEIPT [--part RECEIPT ...] --corpus ROOT [--corpus ROOT ...]
                  --metadata release.toml --release-date YYYY-MM-DD [--dry-run]
```

`agentprov.release.index.build_index(parts, corpora, metadata, out, *, release_date, producer) -> IndexReport` builds
the index-only umbrella deposit of a collection (H.10.7; D-947).

Collections (`--collection`) and views in deposits (`--views`) are deferred (AD-10 rows 6 and 12); MN N.2.11 owns
the final flag list. The index-only umbrella of H.10.7 lists the records of a release; it is not a collection
deposit and computes no collection-level digest.

`release.toml` is supplied by the user. The builder never infers creators from git. It contains:

- `title`;
- `creators` (name, optional ORCID, optional affiliation);
- `keywords`;
- `description_preamble`;
- `concept_doi` (null on first release);
- `related` identifiers.

### H.10.3 Deposit composition

```
DEPOSIT_DIR/
  README.md                         # generated: contents, verify instructions, root digests, citation
  CHANGELOG.md                      # deposit-level, generated from the corpora's CHANGES.toml
  DATASHEET-<corpus_id>.md          # copies, visible without unpacking (REP-3)
  <corpus_id>-v<ver>.meta.zip       # everything except raw/aer/sem/prov/views trees; small, self-describing
  <corpus_id>-v<ver>.raw.<nnn>.zip  # raw/objects (incl. member objects and, for adprov corpora, the v2.3 checksum lists)
  <corpus_id>-v<ver>.aer.<nnn>.zip
  <corpus_id>-v<ver>.sem-<profile_dir>.<nnn>.zip
  <corpus_id>-v<ver>.prov-<spec_dir>.<nnn>.zip
  DEPOSIT-MANIFEST.json             # archives, digests, coverage, root digests
  deposit-metadata.json             # descriptive metadata for the user to enter or upload
```

Views are not deposited in v0.1 (AD-10 row 12); a corpus's optional `views/` tree stays local.

1. Every archive member path starts with `<corpus_id>-v<ver>/`, so the archives of a corpus are a faithful image
   of the corpus tree. `agentprov verify` reads the deposit archives directly (extraction-free, in T1; archive mode
   of H.5.5) and checks member labels against the closed-world `checksums.sha256` (R-44, AD-14). No AgentPROV
   command extracts a deposit. `DEPOSIT-MANIFEST.json` lies beside the archives it describes and anchors nothing, so
   release-mode `verify` of a deposit directory needs a root digest published outside the deposit (`--root-digest`;
   exit 2 before anything is read), as tree mode and a lone meta archive do (D-39, D-620), and one for every corpus
   of the deposit (`root_digest.missing`; D-641). Each corpus's root digest is in its own tag annotation (L.3.2).
2. `DEPOSIT-MANIFEST.json` lists, per archive:
   - `name`, `bytes`, `sha256` and `md5` (Zenodo lists md5 checksums for deposited files
     [baseline/BASELINE.md §8.1]);
   - `corpus_id`, `stage`, shard range, `n_members`, and `members_sha256` (sha256 of the sorted member list).

   Per corpus it gives `content_digest` and `root_digest` (collection-level digests are deferred with collections).
   Every listed archive belongs to exactly one corpus entry and is named `<corpus_id>-v<ver>.<...>.zip`; archive-mode
   `verify` fails an archive that no corpus names, that two corpus entries name or that is listed twice
   (`deposit.archive.orphan`), and a deposit manifest that lists no corpus (`deposit.manifest.invalid`).

   `documents` lists exactly `README.md`, `CHANGELOG.md`, `deposit-metadata.json` and one `DATASHEET-<corpus_id>.md`
   per corpus entry, each once. Any other name, or a missing one, is `deposit.manifest.invalid` (D-490).
   `mixed_licence_classes` must be a boolean. Each datasheet copy is compared with the corpus's archived
   `DATASHEET.md`, read from the meta archive, which the archived checksums and the root digest cover. Without mixed
   licence classes the copy must be byte-equal. With them it must be the sealed datasheet (trailing line feeds folded
   into one) followed by the builder's deposit note, which names the corpus's own licence class and the deposit's
   classes. `verify` rebuilds that copy in full from the archived `DATASHEET.md` and the licence classes of the
   archived `corpus.json` files, with the builder's own function, and compares the bytes (D-620); the deposit
   manifest's `mixed_licence_classes` must agree with those classes (`deposit.manifest.invalid`). A mismatch is
   `deposit.document.datasheet` (D-490).
   `README.md`, `CHANGELOG.md` and `deposit-metadata.json` are generated for the deposit and have no sealed
   counterpart, so they stay covered only by the deposit manifest (size, `sha256`, `md5`), which no published root
   digest anchors.
3. The meta archive also contains `schemas/` and `rules/`. A third party can therefore validate a corpus's
   structure with only the meta archive and the specification. `rules/` documents which catalogues were used;
   `rederive` loads the package's own copies at the recorded versions and compares digests (AD-14).
4. Rendered graphs are never part of a corpus or a deposit in v0.1. Renders are not byte-reproducible, and the
   baseline never recorded renderer versions [audit/corpus.md §3.7 V4]. `agentprov render` (Addendum B AD-10)
   writes outside the corpus and records the pydot and graphviz versions with its output.

### H.10.4 Deterministic archives

- Members are sorted by path.
- Timestamps come from the release date. ZIP represents years 1980..2107 only: earlier dates are clamped, and
  `package --deposit` refuses a release date after 2107-12-31 as a usage error (exit 2).
- Permissions are fixed (0644), with no extra fields.
- Compression is DEFLATE at a fixed level.

Archive *bytes* are reproducible given the same zlib version (`producer.zlib_version`). *Content* reproducibility
is guaranteed independently by the member checksums. Archives are split at `--max-archive-bytes` on shard
boundaries, never inside a shard. The default of 2 GiB is a proposal: Zenodo's per-file limits were not verified in
the investigation and must be checked by the user; the value is re-examined when phase 11 measures real archives.

### H.10.5 Metadata and DOIs

`deposit-metadata.json` (AgentPROV format `agentprov-deposit/0.1`) holds:

- `title`, `version` (deposit or corpus version), `publication_date` (= release date);
- `resource_type: "dataset"`;
- `creators`;
- `description` (generated: summary counts from the manifests, claim-scoped wording, verify instructions, root
  digests);
- `licences` (per archive group);
- `keywords`;
- `related_identifiers` (relation names from the DataCite relationType vocabulary).

Related identifiers include:

- upstream sources: the AgentDojo concept DOI `10.5281/zenodo.12528188` and version DOIs; the survey concept DOI
  `10.5281/zenodo.22135956` together with the version DOI actually fetched (v1.0.0 `10.5281/zenodo.22135957` or
  v1.0.1 `10.5281/zenodo.22140262`; the git commit `89c4db2c…` is the primary origin, R-62); arXiv ids from the
  licence attribution lists;
- the predecessor AgentDojo-PROV concept DOI `10.5281/zenodo.20692312` [manuscript/review_feedback.md §0.3];
- each context tree's pinned origin of a corpus/0.2 snapshot (D-221): a git commit URL (`IsDerivedFrom`) or a Zenodo
  DOI (`IsDerivedFrom`);
- the AgentPROV software identity: version + commit, plus a software DOI if the user creates one.

The user maps this file onto Zenodo's deposit form or API. The builder does not claim fidelity to Zenodo's API
schema.

1. **Concept DOI.** The first published AgentPROV corpus release creates a **new AgentPROV concept DOI** (D9).
   Later releases are new versions of it. The AgentDojo-PROV concept DOI stays with the AgentDojo-PROV corpora.
   AgentPROV does not deposit under it. The user deposited AgentDojo-PROV v2.3 (REP-2) on 2026-10-10
   (`10.5281/zenodo.23276620`, D-900). Regardless of it, `agentdojo-prov-v2` ships the frozen v2.3 checksum lists as raw objects
   (R-26), and the paper cites the v2.3 deposit with the commit and digests. Separate concept DOIs per licence
   class are decided when the first non-permissive deposit is prepared (H.10.6).
2. **DOIs inside archives.** A DOI is written into `release.version_doi` and `concept_doi` only when the user passes
   it. A DOI obtained after publication goes into the next version's CHANGELOG. Archives are never rebuilt after
   publication.
3. The paper cites version DOI, concept DOI and root digest together (REP-4).

### H.10.6 Licence partitions

> **Resolved (AD-20(b) / R-14):** C-D9b is accepted in reduced form and amends D9. Deposits are grouped by the
> licence class `(licences.derived.spdx, sorted licences.restrictions)` (H.2.10 `class`). The deposit builder
> refuses corpora of different classes in one deposit unless the user gives an explicit override flag, for a user
> who has verified record-level multi-licence support (MN N.2.11 owns the flag's name). Separate concept DOIs per
> class are decided when the first non-permissive deposit is prepared. The NC partition is deferred with STAC
> (AD-10 row 22), so no `-nc` corpus exists in v0.1; `ast-survey-agentharm` forms its own class through its
> `restrictions` (U-05).

A copyleft (GPL, AGPL, LGPL) or non-commercial source licence is never relicensed (D-25, D-42). Both are family tests
on each term of the SPDX expression, so `GPL-2.0+`, `GPL-2.0-with-classpath-exception`, `GPL-3.0-only WITH
GCC-exception-3.1` and `PolyForm-Noncommercial-1.0.0` are covered. Any such term fails closed, also inside an `OR`
expression: the derived licence must equal the source expression, or the elected alternative is recorded as the
source licence.

Rationale (evidence). The STAC-derived data must stay CC BY-NC 4.0 and, per its licence reading, cannot be
relicensed under CC BY or MIT, so it needs a separately licensed partition [sources/multiturn-agent-attack.md §9].
Every Zenodo record observed in the investigation declares one record-level licence: AgentDojo-PROV `cc-by-4.0`
[manuscript/review_feedback.md §0.3], the survey `cc-by-4.0` [sources/agent-security-tools-survey.md §1], AgentDojo
`mit-license` [verify/agentdojo.md §1]. Whether a record can declare per-file licences was not verified. A mixed
record would therefore risk misdescribing part of its content, and the same holds for a record that mixes
restricted-use and unrestricted data.

### H.10.7 The index-only umbrella deposit

A release of several records (one per licence class and harness family, D-941 L-1) is gathered by an umbrella record
that holds **no corpus data** (D-941 L-5; built as D-947). `agentprov package --index` (`agentprov.release.index`,
offline like the builder, H.10.1(1)) writes it as a deposit directory:

```
INDEX_DIR/
  README.md                 # generated: the part records, each corpus's digests, how to verify, related records
  COLLECTION-INDEX.json     # agentprov-collection-index/0.1
  DATASHEET-<corpus_id>.md  # a byte copy of each sealed DATASHEET.md, except copyleft corpora's (item 3; D-949)
  deposit-metadata.json     # agentprov-deposit/0.1; one licence, CC-BY-4.0, over the index's own documents
  DEPOSIT-MANIFEST.json     # agentprov-index-manifest/0.1, kind "index": the documents, sizes, sha256, md5
```

1. **Inputs.** Each `--part` is the draft receipt of a part record (`agentprov-zenodo-draft-receipt/0.2`, H.10.1(2)):
   status `complete`, a reserved DOI and record id, all receipts of one target, no DOI, record, deposition or
   directory twice. The part's deposit directory is the one the receipt names (`draft_dir`), **beside the receipt**,
   and only its `DEPOSIT-MANIFEST.json` is read: its size, sha256 and md5 must equal the receipt's entry, and the
   receipt's file list must equal the manifest's archives and documents, so the manifest is the one uploaded. A part
   is a corpus deposit of one licence class, not mixed. The `--corpus` directories are exactly the sealed corpora the
   parts hold, each in **exactly one** part (`release.refused.index_corpus_missing`, `_corpus_extra`, `_duplicate`).
2. **Digests.** Each corpus's root digest is recomputed from its `checksums.sha256` (H.5.4); `corpus.json` and
   `DATASHEET.md` must match their checksum entries, so every value read is anchored by that root digest. Its id,
   version, content digest, root digest and licence class must equal the part manifest's corpus entry, and its
   datasheet the part's copy (`release.refused.index_corpus_mismatch`). The chain verification and the release scan
   stay the part deposit's (H.10.1(3)); the index repeats neither and copies no corpus file but the datasheet.
3. **`COLLECTION-INDEX.json`** holds `format`, `title`, `version`, `release_date`, `status: "draft-unpublished"`,
   `target` (`name`, `host`), `licence` (the index's own), `producer`, a `notice` and `parts`, sorted by record name.
   A part row has `record` (its deposit directory name), `title`, `reserved_doi`, `record_id`, `deposition_id`,
   `communities`, `licence_class`, `deposit_manifest_sha256` and `corpora`, sorted by id. A corpus row has
   `corpus_id`, `corpus_version`, `title`, `content_digest`, `root_digest`, `licence_class`, `archives` (their names
   in the part record) and `datasheet` (`location`, `name`, `bytes`, `sha256`, `md5`). `location` is `index` (the copy
   is in this record) unless the corpus's licence class has a copyleft term (GPL, AGPL, LGPL;
   `agentprov.corpus.licences.is_copyleft`), when it is `part`: the CC-BY-4.0 index holds no copyleft corpus's
   datasheet, and the row names the part record's copy by its digests (D-949). A reserved DOI is registered only when
   its record is published; the README and the notice say so.
4. **Metadata.** `deposit-metadata.json` keeps the corpus deposit's shape (H.10.5) with no archive, corpus, release
   scan or root digest of its own. Its related identifiers are `release.toml` `[[related]]` plus `HasPart` each
   part's reserved DOI, the pair the uploader's `--cross-link` writes, so linking again changes nothing. The index is
   CC-BY-4.0 (D-941). Each corpus keeps its own licence, stated in its part record and its datasheet.
5. **The uploader** takes an index directory like a deposit directory. The closed-world check and the size, sha256
   and md5 of every file are unchanged. Archive-mode `verify` is replaced by
   `agentprov.release.index.check_index_deposit`: the formats and kind, the parts' distinct reserved DOIs, each corpus
   once, each datasheet copy against the index's digest, each datasheet's `location` against its corpus's class, and
   the CC-BY-4.0 licence. `--root-digest` is refused (the
   index holds no corpus), and so is an index built from another target's receipts. The consent screen adds one line
   naming the kind; the typed phrase, the request allowlist, the receipt, `--community`, `--resume` and
   `--cross-link` (the index's receipt as `--umbrella`) are unchanged, except that `--cross-link` with an index
   umbrella (its receipt lists `COLLECTION-INDEX.json`) refuses, before any request, members that are not exactly the
   part records the index lists (by reserved DOI and deposition) and an index beside the receipt whose sha256 is not
   the uploaded file's (D-949). No request kind is added and nothing is published. Archive-mode `verify` of an index directory reports `deposit.manifest.invalid` with that reason.
6. **Order (D-941 L-8).** Part drafts first; then `package --index` from their receipts; then the umbrella draft;
   then `--cross-link`. A collection is drafted from the terminal (D-949); the desktop app's *Create Zenodo drafts…*
   (D-880) is for single records. It takes the index alone on its first line, with no root digest, skips the complete
   parts after it and runs the cross-link step, and it asks before it cross-links two or more lines.
7. Two builds from the same inputs are byte-identical (Q.20). Corpus deposits, their manifests (format 0.1, no
   `kind`) and the sealed corpus format are unchanged.
8. **Format ids.** `agentprov-index-manifest/0.1` and `agentprov-collection-index/0.1` are written here, and the
   uploader's receipts `agentprov-zenodo-draft-receipt/0.2` (and the superseded 0.1, named only to refuse it) are read
   here; all four are in `formats.AS_BUILT_FORMATS` (L.1.2, the closed set).

---

## H.11 Performance and scale

### H.11.1 Reference sizes

| Source | Size |
|---|---|
| Baseline release | 17,664 transcripts (344 MB) |
| Baseline converted tree | 18,027 transcripts (312 MB) [baseline/BASELINE.md §4] |
| AgentDojo HEAD `runs/` | 36,679 logs, 426 MB [verify/agentdojo.md §1] |
| AgentDyn `runs/` | 47,723 logs, 598 MB [sources/agentdyn.md §1] |
| ROPE `runs/` | 188 MB [sources/rope.md §2] |

Baseline timings: recompute dry-run took 19 s for 17,664 traces. The full five-check conformance took 89 s on 10
workers [baseline/BASELINE.md §3, §6]. The RDF round-trip costs about 0.4 ms per relation, and the old taint policy
makes `used` edges grow quadratically on long traces [audit/validation.md §6.5].

### H.11.2 Requirements

1. **Streaming.** Readers, mappers and validators MUST process one execution at a time. Backward-only AER references
   allow single-pass validation (D2). Raw artefacts are hashed in 1 MiB chunks. JSONL outputs are written through
   `agentprov.corpus.index.SortedJsonlWriter`, which spills sorted runs to a temporary directory inside
   `<out>.partial` and merges them. No corpus-wide list of rows is held in memory.
2. **Bounded memory.** Peak memory MUST be O(largest execution + in-flight executions × per-execution working set +
   writer buffers). It MUST NOT grow with corpus size. Acceptance test: `verify --level chain` on the full
   `agentdojo-upstream` corpus, peak RSS recorded in the test report. The target is under 2 GiB. That target is a
   proposal, to be revised after the phase-11 measurement.
3. **Parallel determinism.** `--jobs N` uses the T1 worker pool over executions (`agentprov.io.workers`,
   `python -I -B -m agentprov.worker`; A3). Container expansion and parse/map MUST run there; SEM, PROV and validation
   MAY run in the pool or in-process (AD-10 row 17). Per-execution outputs depend only on that execution's inputs.
   Aggregated files are sorted before writing. Nothing may depend on completion order, worker id, PID or wall
   clock. CI test: building a golden mini-corpus with `--jobs 1` and `--jobs 4` gives identical `root_digest`.
4. **Atomicity.** Per-file writes use a temporary name in the same directory plus `os.replace`. Sealing a corpus
   is atomic as a whole (H.1.5).
5. **Resume.** An interrupted build resumes on the sealed-AER key (D.2.9); the content-addressed build cache is
   deferred (H.8.3). Resume is never keyed on the existence of an output file.
6. **Long traces.** The `collection` context encoding for long traces (D7) is deferred to `aer/0.2` (AD-10 row 14).
   v0.1 uses `members` only; the option is recorded in `derivation.json`, and the size of per-execution PROV on long
   traces is measured in the phase-13 full-corpus run rather than assumed.
7. **Sharded archives** (H.10.4). A consumer can download and verify the meta archive alone, or one stage's
   archives, using `members_sha256`.
8. **Sampling** is only for development (`verify --sample`). Release verification is exhaustive.

---

## L.1 Version axes

### L.1.1 The axes and where each is recorded

| # | Axis | Form (v0.1 value) | Recorded in |
|---|---|---|---|
| 1 | Software | PEP 440 / SemVer `0.1.0` | `pyproject.toml` `[project].version` (single source); `agentprov.__version__` via `importlib.metadata`; git tag `v0.1.0`; `corpus.json.producer`; PROV top-level engine agent `apv:version` + `apv:commit` [landscape/prov_semantics.md §10.1]; capture session event |
| 2 | Canonical record | `aer/0.1` (AgentPROV Execution Record; 13 record kinds, Addendum B B-1); `aer/0.2` since D-212 (C.21), with `aer/0.1` readable | AER `execution.aer`; `schemas/aer-0.1.schema.json`, `schemas/aer-0.2.schema.json`; `corpus.json.formats.aer` |
| 3 | Capture log | `capture/0.1` (dialect displayed `agentprov.capture/0.1`) | Capture log header; `formats.capture` (live corpora) |
| 4 | Semantics format | `sem/0.1` | SEM header; `formats.sem` |
| 5 | Provenance spec + rule catalogue | `agentprov-prov/0.1`; compat `adprov-v2.3-compat` (frozen, `apv:RegressionOracle`) | PROV top level; `prov/<spec_dir>/`; `corpus.json.prov_specs` and `oracle_specs`; `rules/prov/agentprov-prov-0.1.toml` |
| 6 | Ontology | `apv` `0.2.0` (`owl:versionInfo "0.2.0"`; minor, additive over `0.1.0`: D-500, D-501) | the ontology file `vocab/apv-0.2.ttl` (`docs/ns/apv-0.1.ttl` keeps the 0.1.0 release); PROV `apv:vocabularyVersion` and the `aprov` catalogue `vocabulary`; `corpus.json.ontology.version` (still `0.1.0` in `agentprov-corpus/0.1`; it moves with `agentprov-corpus/0.2`, deferrals part C) |
| 7 | Adapters | dotted id + SemVer, e.g. `agentdojo.tracelogger` `0.1.0`; corpus-layer citation `agentdojo.tracelogger@0.1.0` | `agentprov.adapters.registry` entry (id, version, code digest); AER `execution.adapter`; `corpus.json.adapters`; index `adapter` |
| 8 | Rules and catalogues | rule id `<ns>.<rule>@<n>` (a reference may add a `#/<pointer>` scope); catalogue `[catalogue] id = "<ns>"` with an **integer** `version` (AD-18) | Every D/I assertion in AER, SEM and PROV (`rule`, `apv:rule`, `apv:rulePointer`); AER header `rules: {"<ns>": <int>}`; `corpus.json.rule_catalogues[].rules_used` |
| 9 | Source and semantics profiles | **integer** `version`, monotonic (AD-18), e.g. `agentdojo-upstream@1`, `agentdojo.suites@1` | Profile files; AER header `profile {id, version, sha256}`; `corpus.json.profiles`; index `profile` |
| 10 | Corpus | SemVer per `corpus_id` | `corpus.json.corpus_version`; tag `corpus/<id>/v<ver>`; deposit version |
| 11 | Benchmark / framework identity | observed record, not a version | AER header (identity block, see B.1); `corpus.json.framework_identities`; facet `framework` |

The interpreter is not a version axis but is recorded with every corpus (`producer.python`, `derivation.json`) and
in live sessions for both the core and the backend interpreter (L.2.2; AD-16).

The format ids form one closed set, held by `agentprov.formats` (MN M.1.2), which fails closed on any other id
(L.1.2). The complete v0.1 set is:

- record and log formats: `aer/0.1`, `aer/0.2` (C.21), `sem/0.1`, `capture/0.1`;
- corpus-layer formats: `agentprov-corpus/0.1`, `agentprov-corpus/0.2` (H.2.1), `agentprov-index/0.1`, `agentprov-register/0.1`,
  `agentprov-derivation/0.1`, `agentprov-raw-references/0.1`, `agentprov-withheld/0.1` (and `/0.2`, D-312),
  `agentprov-deposit/0.1`;
- the command summary `agentprov-cli-summary/0.1` (MN N.1.4);
- package resources: `agentprov-source-profile/0.1` and `agentprov-rule-catalogue/0.1` (D.4, D.5);
- the transcript view `agentprov-transcript/0.1` (C.15.2);
- the migration gate report `agentprov-migration-gate/0.1` (J.3);
- the worker protocols `agentprov-job/0.1` (T1; G.4.6) and `agentprov-backend/0.1` (T2; D.11.3);
- the live run plan `agentprov-run-plan/0.1` (`plans/*.toml`; `RunPlan`, D.10.1).

All of them follow the rules of axes 2–4 (L.1.2). `agentprov-collection/0.1` is reserved for the deferred
collections and is not in the set. The compatibility profile id `adprov-v2.3-compat` is frozen: it is never bumped,
and any change needs a new id (D7).

### L.1.2 Bump rules

| Axis | Rule |
|---|---|
| Formats (`aer`, `capture`, `sem`, corpus-layer formats) | `<name>/<major>.<minor>`. **Any** change to schema or field semantics produces a new version, because formats are closed and readers MUST reject unknown versions (fail closed). The bump is *minor* if the change is purely additive (new optional fields or values whose absence keeps the old meaning). Otherwise it is *major*. No upgrade module exists: corpora are re-mapped from raw under the new version (D9). transcript/v1 was never bumped despite field additions and a semantic change (`null` vs `""`) [audit/capture.md §7, §8 D3]; this rule forbids a repeat |
| Provenance spec | Bump whenever the set of statements emitted for some valid AER+SEM input changes. *Minor* if the change is purely additive (no statement removed or altered, which includes bundle placement). *Major* otherwise. The spec and its rule catalogue are versioned together (D9) |
| Ontology | Adding a term is *minor*. Changing a term's meaning, or deprecating one, is *major*. Terms are never deleted. They are marked deprecated. Instance IRIs never encode the ontology version (D7) |
| Rule ids `@n` | Increment `n` whenever the rule's output can differ for any input. Catalogues are append-only. A retired rule keeps its text with `retired_in` |
| Catalogues and profiles | The integer `version` increases by one on **any** byte change (AD-18). The kind of change is recorded in `CHANGES.toml`, not in the number: *documentation* (text only); *additive* (a rule added or a rule's `@n` bumped); *breaking* (a rule retired, or a profile's selection, quirk or ownership semantics changed). The package ships every released catalogue version, so `rederive` can load the recorded one (AD-14). A change of an assumption's verification status is a new rule id or catalogue version (AD-05) |
| Adapters | *Patch*: no AER byte changes on the adapter's golden fixtures. *Minor*: new dialect or feature, or output changes, all accompanied by rule `@n` bumps. *Major*: a dialect removed, or a change to the mapping identity or locator scheme (which changes execution ids) |
| Software (pre-1.0) | `0.MINOR.PATCH`. *Minor*: any change to public API or default outputs. *Patch*: fixes that change no default output byte on the regression corpora. Every software release lists the format, spec, adapter and catalogue versions it emits |
| Corpus | See L.1.3 |

### L.1.3 Corpus SemVer (applied by hand in v0.1)

The rule below is normative. Its automatic checker (the former corpus diff with a SemVer check) is deferred (AD-10
row 10): in v0.1 the maintainer applies the bump by hand and records the reason in `CHANGELOG.md`.

| Bump | When |
|---|---|
| MAJOR | Corpus or index format major change; execution-id scheme change; a snapshot removed; a snapshot's raw policy restricted; derived licence changed; executions removed |
| MINOR | Snapshot or executions added; any execution digest (AER, SEM or PROV) changed through a version bump; a derived stage, spec or view added or removed |
| PATCH | Only datasheet prose, card, notices, metadata or `release` changed. Every execution digest, every set digest and `digests.index` are unchanged |

The baseline used one hand-bumped `CORPUS_VERSION` for code and data changes alike, and never bumped
`EXPORT_VERSION` across content changes [audit/corpus.md §3.5.3 M1, §3.9]. Here the bump rule is written down,
separates code from data, and is recorded per version in `CHANGELOG.md`; the computed check returns with the
deferred checker.

---

## L.2 Reproducibility

### L.2.1 Two different properties

| Property | Definition | Status in AgentPROV |
|---|---|---|
| **Derivation reproducibility** | Given a corpus's raw evidence, the AgentPROV commit and the lockfile, re-derivation gives byte-identical member objects, AER, SEM and PROV-JSON (H.8.4); TriG produced on demand is identical under the same serialisers | **Guaranteed and verified** (`verify --level rederive`, `recompute`). This is the reproducibility the paper may claim (D12), as "derivation-reproducible" |
| **Execution reproducibility** | Re-running the same cell gives the same trajectory | **Never claimed** |

Execution reproducibility fails for documented reasons:

- providers re-route aliases (`deepseek-chat` routed to a different model on the run date, CAP-6);
- configured sampling parameters were not transmitted (CAP-7);
- aliases retire;
- the availability of 2024 snapshots today is unknown [sources/agentdojo.md §9];
- REP-1 [manuscript/review_feedback.md §1.5].

AgentPROV records what is needed to *interpret* a run and to *attempt* a re-run. Outcome replay (re-executing
recorded tool calls) would be a separate semantics-layer check whose results are *inferred* annotations
[audit/legacy_replay.md §7]; it is deferred (AD-10 row 2), and the frozen baseline environment at `579a908` serves
it for the old corpus. Documentation and datasheets MUST use the term "derivation-reproducible" and never an
unqualified "reproducible" (AR-12).

### L.2.2 Metadata recorded for live runs

Every item is raw evidence in `capture/0.1`, attested `by: capture` (or `provider`/`config` as noted). It reaches
the AER through `src` locators, at locations defined by the AER and capture sections (C.13). The capture
requirements are those of [audit/capture.md §9.3] and AR-4. Live runs always execute in a spawned backend worker
(`<env>/bin/python -I -B -m agentprov_backend.worker`, protocol `agentprov-backend/0.1`) from a backend project
(`backends/agentdojo`, `backends/autodojo`; Python 3.12) whose environment is built by `agentprov backends build`
under `$AGENTPROV_HOME/envs/<backend>-<commit8>/` (A1, AD-01). The worker writes events through `agentprov_capture`;
core maps the staged evidence like any import.

| Item | Capture point | Evidence | Notes |
|---|---|---|---|
| Benchmark/framework identity | Session start (`identity` event) | O | Distribution name; reported version; **`source_tree_sha256`**: sha256 of the JCS list of `(relpath, sha256)` over the installed package's files; source commit when installed from git (PEP 610 `direct_url.json`); lockfile artefact hash; suite-set label; tool-definitions digest; default system-prompt digest [audit/capture.md §9.2]. AutoDojo shares AgentDojo's name and version, so only the tree digest and commit (`aa458794b7eb7f082e94daeac4c0f55bfc0c90cc` when pinned) identify it (D5). Before spawn, T0 computes the lock, RECORD and guarded-source digests itself and cross-checks them against the worker's `hello_ok` and this event; the worker's report is never the only evidence (AD-13, R-39) |
| Model requested | Per call (`llm.request`) | O (`config`) | Never inferred from the folder name. An explicit model id is required (no silent defaults) |
| Context positions | Per call (`llm.request.input_at`, `n_messages`) | O | Positions of the sent messages in the pass's native message list, recorded by the LLM-span bracket (R-16, AD-09). Without them, live context membership is D under a named alignment rule |
| Model served, `system_fingerprint`, provider route | Per call (`llm.response`) | O (`provider`) when returned | Allow-listed response headers only. Absent → `unk: not_recorded` |
| Provider and endpoint host | Session + per call | O | Scheme, host, port and path without query. Never credentials or auth headers |
| SDK versions | Session start | O | `openai`, `anthropic`, `httpx` and every client library in the call path |
| Sampling parameters: configured vs transmitted | Run plan / per call wire request | O (`config`) / O (`capture`) | Both kept. The baseline recorded configured `temperature` as if transmitted [audit/capture.md §8 D6] |
| System prompt digest | Per call (first system/developer message as sent) | O | sha256 of the exact bytes. Role rewrites are visible because the wire request is kept |
| Tool schema digest | Per call (`tools` as sent) | O | JCS sha256. Plus the catalogue digest at identity level |
| Seed | Run plan / wire | O (`config`) / O (`capture`) | Recorded if configured or transmitted. Otherwise `unk: not_recorded`; `not_applicable` only where the endpoint has no seed parameter (R-57). AgentPROV's own randomness (scheduling stagger, sampling) MUST be seeded and recorded, or removed |
| Dependency lockfile digests | Session start | O | sha256 of the backend project's `backends/<b>/uv.lock` that built the worker environment and of the core `uv.lock` that maps the evidence, plus the installed-distributions digest of the backend environment (`AGENTPROV_ENV.json`) (A1, R-01) |
| OS and Python | Session start | O | `platform.system/release/machine`; `sys.implementation`, `sys.version` of **both** interpreters: the backend worker (3.12) and the core (3.14.x, with `interpreter_advisory` when below 3.14.8, AD-16). `$HOME` and the host name are redacted on non-content surfaces (R-51) |
| AgentPROV version, commit, capture code digest | Session start | O | Also in `corpus.json.producer` |
| Adapter id and version | Session start | O | Live backend adapter |
| Attack instantiation parameters | Cell start | O (`config`) | e.g. `model_display_name` (CAP-8), declared as `attack_parameter` instrumentation; replaces the `MODEL_NAMES` mutation [audit/capture.md §4.5] |
| Attempt and repeat index; run-plan digest; config hash | Cell start | O | Generalises the single-field mixed-config guard [audit/capture.md §4.5 G-4, defect 2] |
| Instrumentation declaration (observer effects) | Session start | O | Items `{id, kind, recorded}` (C.3): role rewrite, retries, resampling, transmitted-vs-configured differences, timeouts, parallelism [audit/capture.md §6] (D5). The default LLM element is `native` (stock, recorded at the transport level); `gateway_compat` is an opt-in declared as `request_modifying`/`harness_policy` (AD-09). Per execution, the counts of resampled and retried replies |
| Clocks | Every event | O | Wall-clock UTC (`ts`) and monotonic time (`mono_ns`) in the capture envelope [audit/capture.md §9.3] |

The run-environment block of a live session is produced in the backend worker by `agentprov_capture` (environment
digests) and written as the capture `identity` event; core fills `corpus.json.producer` with the same field set
for its own process (module placement per MN M.1.2). Secrets MUST NOT be recorded: no API keys, `Authorization` or
cookie headers, or `.env` content. `.env` is read only by the live CLI entry, from `--env-file` or the repository
root (A4). T0 runs the literal-value scan over every staged file before storing it; a hit quarantines the session
(`capture.quarantined`, R-51). A test injects sentinel secrets and asserts that they appear in no output byte.

### L.2.3 What imports can observe

The table summarises the source reports. Where an item is not recorded, the AER MUST declare it with `unk`
(`not_recorded`, `lost`, `overwritten`, `ambiguous`, …; seven reasons, C.7.1). It MUST NOT be filled from the
source's README or from a paper. Upper bounds and code-inferred values carry evidence class D or I with a rule id.
`not_applicable` is used only where a value cannot exist for the source (R-57). "O (`config`)" below means an
observed value attested by the producer's configuration, not by an observation of the request.

| Item | AgentDojo native, 2024 (`v0.k11`) | AgentDojo native, 2025+ (`v1.k14`) | AgentDojo-PROV transcript/v1 (v2.3 release) | Other AgentDojo-family logs (AgentDyn, DRIFT, ROPE, Mandate, survey) | Inspect `.eval` (survey AgentHarm) | STAC (planned; scenario records) |
|---|---|---|---|---|---|---|
| Framework/benchmark commit | Not recorded. Upper bound from the introducing commit, rule `agentdojo.committed_no_later_than@1` (D; `ext` only, never a PROV time) [audit/legacy_replay.md §2.1] | Reported `benchmark_version` (e.g. `v1.2.1`) and `agentdojo_package_version` (`"unknown"` literal) (O as reported) [verify/agentdojo.md §3] | `agentdojo_version` from installed metadata (O, ambiguous for forks); `benchmark_version` a constant stamped by the producer (O (`config`); a label, not an identity) [audit/capture.md §5.2] | Repository commit as upper bound (D); version strings where present (O) | `eval.revision` (`inspect_evals` commit) and package versions in the header (O); AgentHarm dataset revision code-inferred (I) [verify/agent-security-tools-survey.md §2.3, §2.5] | Not recorded |
| Model requested | `pipeline_name` / directory (I; rule `agentdojo.pipeline_dir_is_model_identity`) | Directory only for local models (I; `pipeline_name: local`) | `model_id` (O (`config`)) | Directory or pipeline name (I); ROPE `pipeline_name` wrong for 949 qwen logs [sources/rope.md summary] | In-record model tag (O) [verify/agent-security-tools-survey.md §2.7] | Planner/generator names only; target agent `unk` |
| Model served, fingerprint, route | not recorded | not recorded | not recorded (`model_config.response` absent) | not recorded | per the D.9 mapping (not assessed in this section) | not recorded |
| Provider, endpoint host | not recorded | not recorded | not recorded (paper text only: claimed) | not recorded | provider prefix of the in-record model tag, e.g. `ollama/…` (O); host per D.9 | not recorded |
| SDK versions, OS, Python, lockfile | not recorded | not recorded | not recorded | not recorded (upstream `uv.lock` at the commit MAY be cited as I) | `inspect_ai` and `inspect_evals` package versions in the header (O); the rest not recorded | not recorded |
| Sampling parameters | not recorded | not recorded | `temperature` configured (O (`config`)), **not transmitted** (CAP-7); usage aggregated | not recorded (survey: temperature 0.0 inferred from code, I) | transmitted values in `call.request` where the call record is present (O) [verify/agent-security-tools-survey.md §2.3] | code defaults only (I) |
| System prompt digest | D (system message in log) | D | D | D, except DRIFT/CaMeL (no system message) | per D.9 (messages resolved through `input_refs`) | System prompt omitted (not recorded) |
| Tool schema digest | not recorded (MAY be I from benchmark code at the commit) | same | same | same | `tools` in `call.request` where present (O) | not recorded |
| Seed | `not_recorded` | `not_recorded` | `not_recorded` | `not_recorded` (R-57: the AgentDyn seed is `not_recorded`, not `not_applicable`) | `seed` in `call.request` where present (O), else `not_recorded` | not recorded |
| Timing | `duration` only | Naive-local `evaluation_timestamp` + `duration` (tz `ambiguous`) | `started_at`/`ended_at` + per-tool wall times; the `"0"` stub kept verbatim in `t.raw` with `unk` on typed fields (C.7.3) | Naive-local run start + duration (varies by variant) | per-event UTC timestamps at µs resolution (O) [verify/agent-security-tools-survey.md §2.3] | none |
| Attempt / earlier passes | lost (last pass only) | lost | lost (no `discarded_attempts` in any trace) [baseline/BASELINE.md §5.1] | lost | per D.9 | n/a |
| AgentPROV adapter + version | O | O | O | O | O | O |

---

## L.3 Release, tagging and the baseline pin

### L.3.1 Software release `v0.1.0`

1. A release commit MUST meet five conditions:
   - `pyproject.toml` version equals the tag without `v`, and `CHANGELOG.md` has a dated `0.1.0` entry listing the
     format, spec, ontology, adapter and catalogue versions emitted (L.1.1);
   - the working tree is clean and every project's `uv.lock` is committed (core, `capture/`, `backends/shared/`,
     `backends/agentdojo/`, `backends/autodojo/`; A1, AD-01);
   - every CI gate passes: the core job on the latest Python 3.14 patch and the backend jobs on Python 3.12
     (`uv sync --locked`); unit and property tests; the import-boundary test (D10;
     `tests/boundary/test_import_boundary.py`); the adapter golden fixtures; the migration release gates G0, A1
     (JCS), A2 (bytes), B (compat graph bytes), D and E in that order, with R1/R2 on the golden converted pairs
     (AD-07); `rederive` on the golden mini-corpora; and the `jobs=1` vs `jobs=N` determinism test;
   - the full-corpus compatibility gates A/B on all 35,691 baseline graphs (D7) were run locally on the release
     commit, with their report digest quoted in the release notes. The full R1/R2 run over 18,027 converted graphs
     is a **claim gate**: its result is reported, and only a 0-mismatch pass licenses the supersession claim (H.4.2);
   - the release commands run on Python ≥ 3.14.8 (release mode refuses archive ingestion below it, AD-16).
2. The tag is annotated, `v0.1.0`, on that commit. Pre-releases MAY use `v0.1.0rcN`. Tags stay local unless the
   user decides to push them (Addendum B B-2).
3. Corpora, exports and secrets are never committed (D9). The repository's `.gitignore` excludes corpus output
   directories and `.env`; corpora are written under `$AGENTPROV_HOME` (MN M.1.6).

### L.3.2 Corpus release tags

Each released corpus version gets an annotated tag `corpus/<corpus_id>/v<corpus_version>` on the AgentPROV commit
that built it. This is the code tag per corpus version that REP-4 asked for. The tag message MUST contain the
corpus's `content_digest` and `root_digest`. Because the tag is outside the archive, it can hold the root digest
(H.5.4). The baseline's `corpus-v2.3` tag shows why a tag must point at the producing commit: it sits 26 commits
behind the code that produced the on-disk v2.3 tree [baseline/BASELINE.md §8.1]. Corpus tags stay local unless the
user decides to push them (Addendum B B-2); signing them is optional (U-09).

### L.3.3 Baseline pin

| Pinned item | Value |
|---|---|
| AgentDojo-PROV framework | `579a908354b93361efe0905ffb7623256aa96a06` (`git describe` `corpus-v2.3-26-g579a908`). Pinned **by commit**, not by tag `corpus-v2.3` (→ `a7002b49d74ef873364c2e093613651acad170f6`) [baseline/BASELINE.md §0, §8.1]. The annotated tag `agentprov-baseline-2026-10-07` already points at it (RESOLUTIONS, consolidator check 2) |
| Manuscript | `24ac03f26e97cec96b5bbb77cd876d671a37c4e4` (working tree not clean at observation) [baseline/BASELINE.md §1.4] |
| Baseline environment | CPython 3.12.14, `agentdojo==0.1.35`, `prov==3.2.2`, `rdflib==7.6.0`, `pyshacl==0.40.1` (full freeze in `baseline/pip_freeze.txt`; the `old-vs-new` job installs it from a hash-locked export with `--require-hashes`, R-49) [baseline/BASELINE.md §1.2] |
| Golden fixtures | 15 transcript+graph pairs, 7 native logs, 2 test fixtures, with sha256s in `golden/golden_index.json` [baseline/BASELINE.md §7]; plus the four MIG-10 pairs and the converted pairs' native logs (R-59). In the new repository they live under `tests/fixtures/agentdojo_prov_v1/golden/`, in the private repository only and never in the sdist (U-06; Addendum B B-2) |

1. The AgentPROV repository MUST hold `migration/baseline.lock.json` (J.1.5), recording the framework and
   manuscript commits, the environment versions above, the sha256 of every golden fixture, and the per-tree expected
   counts (17,664 / 18,027; 0 changed).
2. The full-corpus gates read the baseline repository **read-only** from `AGENTPROV_BASELINE_CORPUS` (the old
   repository root; J owns the gates). Before reading, the gate MUST verify that `HEAD` equals the pin and that
   `git status --porcelain` is empty, and it MUST refuse otherwise. It never writes there, and it runs with
   `PYTHONDONTWRITEBYTECODE=1`.
3. AgentPROV creates no tags or other refs in the baseline repository. The existing local tag
   `agentprov-baseline-2026-10-07` stays local; pushing it, and archiving the baseline's git-ignored `corpus/` and
   `runs/` offline, are the user's decisions (U-16).
4. The old manuscript stays on `579a908` (D12). AgentPROV ships no `agentdojo_prov` compatibility shim for it.

---

## Appendix A. Acceptance tests owned by this section

K owns the suites (paths per K.3.1, e.g. `tests/unit/corpus/test_dedup.py`); this section owns the assertions.

| Id | Test |
|---|---|
| HL-T1 | Manifest, index row, register entry and `raw/members.jsonl` row: differential test of the in-code validator against `corpus-0.1.schema.json` and its `$defs` (Hypothesis) |
| HL-T2 | `checksums.sha256` closed world: a stray `.DS_Store` makes `verify` fail. Coverage includes `corpus.json`, `DATASHEET.md`, `raw/members.jsonl` and `WITHHELD.json` |
| HL-T3 | Reconciliation (R1, R5) on a mini-corpus with an empty log (`unit: outcome_only`, `map.no_execution_observed`), an oversize file (`ingest.size.file`), a duplicate across snapshots, an owned-elsewhere file, and a zip with selected and `not_selected` members |
| HL-T4 | Determinism: two builds, and `--jobs 1` vs `--jobs 4`, give equal `root_digest`. `content_digest` is unchanged when only `--release-date` changes |
| HL-T5 | Bump discipline: an injected output change without a rule bump makes `recompute` report `unexplained_change`, exit 1 |
| HL-T6 | Type-only change (`true`→`1`) in a PROV attribute is detected (baseline gap [audit/corpus.md §3.10]) |
| HL-T7 | Sealed corpus: every writer raises `SealedCorpusError`; `stats` and `render` refuse an output path inside a corpus root (exit 4) and leave the corpus bytes unchanged |
| HL-T8 | Datasheet: `validate --card` rejects a literal number; a failing claim fails the build; an import corpus with a live card is refused; the claims lint rejects the banned bare phrases (RESOLUTIONS §3.8); every `licences.raw[].basis` appears verbatim |
| HL-T9 | Deposit builder: offline (no network import); `withhold`, `test_only` and advisory-carrying corpora refused; mixed licence classes refused without the explicit override; `verify` in archive mode reads the deposit without extraction and passes `chain` |
| HL-T10 | Secrets: sentinel API keys and headers never appear in capture, AER, corpus or deposit bytes |
| HL-T11 | Execution-id mapping identity (AD-04): the same bytes under two profiles give distinct `ex` and equal `source_key`; the non-owner's selection gives `select.owned_elsewhere`. The C.16.1 KAT `ex_7uz2oys57hugtsueixylme4fl5` is reproduced through `agentprov.aer.ids.import_execution_id` |
| HL-T12 | (Deferred with the corpus SemVer checker, AD-10 row 10.) Until then: `CHANGELOG.md` has an entry for every corpus version |
| HL-T13 | Baseline gate pre-conditions: a wrong HEAD or dirty baseline tree is refused |
| HL-T14 | Member objects (AD-12): `verify --level chain` detects a member whose CRC32 or size disagrees with `raw/members.jsonl`; `recompute` re-runs `expand` and fails on a differing member digest |
| HL-T15 | Catalogue authority (AD-14): a corpus whose `rules/` copy was swapped gives `rules.mismatch`, and `recompute` still derives from the package catalogues; an unshipped catalogue version gives `rules.unavailable` |
| HL-T16 | References (R-43): a `REFERENCES.json` origin that matches no in-package profile origin gives `raw.reference.unpinned_origin` and no network contact; the file holds no command string |
| HL-T17 | Interpreter guard (AD-16), with the reported interpreter version patched below 3.14.8: release mode (`import --release`, `package`, deposit build, archive-mode `verify`) refuses archive ingestion with exit 3 before opening the object; dev mode warns, writes `producer.interpreter_advisory` and an `ingest.interpreter.unpatched` register row, and continues |
| HL-T18 | Generic kinds (Addendum B AD-15): an AER with `activity` and `artefact` records yields `counts.records_by_kind` over the 13 kinds, `counts.generic_types`, facets `n.activities`, `n.artefacts` and `generic_types`, `rules_used` containing the G-ACT/G-USE/G-GEN/G-ASSOC rule ids, and the datasheet disclosure |
| HL-T19 | Index and manifest flags: `unit`, `execution_observed` and `completeness` on every row; compat outputs flagged `apv:RegressionOracle` in `oracle_specs` and in the row's `oracles` (R-55) |
| HL-T20 | Consumers (Addendum B AD-10): `stats` output carries the corpus `content_digest` and its `fn_digest`, and its information-loss table equals the datasheet's; `render` reads the core bundle by default and records the renderer versions |
| HL-T22 | Building commit (D-780): every writer records its commit and the stages it wrote; a dirty tree gives `git_tree_clean: false` and a seal refuses it; not a checkout gives the absent reason and no commit (an enclosing foreign repository is not mistaken for the checkout); `derive` keeps the import's step; the sealed manifest carries the sealing commit and the building steps; a manifest without the key validates unchanged, `agentprov-corpus/0.1` has no key; the manifest is byte-identical across worker counts; `recompute --dry-run` of a corpus rebuilt at the same commit reports no difference |
| HL-T21 | Withholding (H.4.5; D-230..D-237): a purged working corpus seals as a new version (purge -> re-version -> seal) that verifies `chain` in release mode with no byte of the value in the sealed tree or the deposit; the withheld files are in the private sidecar; `WITHHELD.json` round-trips and agrees with its schema; a tombstone it does not list still fails; the tamper rows of `WITHHELD.json` and `raw/REFERENCES.json`; a profile policy with a fake canary withholds it, and its backstops refuse a corpus sealed without it (`tests/security/test_sec25_withholding.py`, `test_sec25_withhold_policy.py`, `test_sec15_tamper_matrix.py`; `tests/unit/corpus/test_withheld.py`, `test_withhold.py`) |

## Appendix B. Requirements placed on other sections

1. **AER section (C).** C.3 plus `schemas/aer-0.1.schema.json` is the only AER contract; this section cites it and
   does not restate it (R-02). The execution header needs:
   - a framework-identity block (H.2.4);
   - `unit` (`agent_execution` \| `outcome_only` \| `scenario`) and `profile {id, version, sha256}` (AD-03);
   - the instrumentation declaration (D5; items `{id, kind, recorded, …}`);
   - for live runs, the run-environment block or `src` locators to it (L.2.2);
   - the in-artefact locator object used by `source_key` (H.7.1), in C's canon;
   - the 13 record kinds of Addendum B B-1, including the generic `activity` and `artefact` records with their
     namespaced `type`, which the index counts (H.2.9, H.3.3).

   Execution-id mapping identity is as ruled in AD-04 (C.4).
2. **SEM section (C).** The SEM header records the AER execution digest it annotates. A SEM digest is defined. The
   `outcome` annotation `{claim, holds?, score?, scale?}` (R-18) feeds the `outcome` facet; polarity lives there,
   never in the AER `judgement`.
3. **Provenance section (EF).** The PROV top level records raw, AER and SEM digests and the rule-catalogue digest.
   The PROV-JSON serialisation is deterministic. The `context_encoding` option is recorded. Compat outputs carry the
   `apv:RegressionOracle` status (R-55). The generic rules G-ACT, G-USE, G-GEN and G-ASSOC have rule ids in the
   `aprov` catalogue, so `rules_used` and the datasheet can name them (Addendum B AD-15).
4. **Validation section.** The check ids and versions, the tier numbers and the per-execution result row format
   used in `validation/results.jsonl`, with values `pass|fail|skipped|not_applicable`. Tier-1 resource and safety
   codes are the `ingest.<area>.<kind>` codes of G.3.9 (H.6.3).
5. **Capture section (C.13).** Every L.2.2 item exists as an event field, including `llm.request.input_at` and
   `n_messages`. The AER seal's accounting verdict feeds `completeness` (R-13).
6. **Security section (G).** The `ingest.*`, `worker.limit.*`, `time.implausible`, `release.withheld`,
   `capture.quarantined`, `rules.*` and `raw.*` codes (H.6.3); `WITHHELD.json` (G.9.5); the interpreter advisory
   record (G.3.8); `release-scan.json` (G.9.4).
7. **Repository and CLI section (MN).** The command mapping of H.8.5; the explicit override flag for mixed licence
   classes in `package --deposit` (H.10.6); `stats` and `render` as read-only consumers that refuse output paths
   inside a corpus (H.1.5(6)); `src/agentprov/stats/` and `src/agentprov/render/` (optional `render` extra) per
   Addendum B AD-10.

## Appendix C. Open questions and their dispositions

Dispositions follow RESOLUTIONS §1.3 and Addendum B. Items marked U-nn are forwarded to the user; until the user
answers, the Addendum B B-2 defaults apply.

1. **Derived-data licence per corpus** → U-03. The proposed default is to inherit the upstream licence and carry
   upstream notices; CC-BY-4.0 is proposed for live corpora; bases are recorded verbatim. Provider terms on
   redistributing model outputs were not assessed for any source [sources/agentdojo.md §10].
2. **Separate concept DOI for CC BY-NC corpora** (C-D9b) → ruled in reduced form (AD-20(b); H.10.6): deposits are
   grouped by licence class and mixed classes are refused without an explicit override; per-class concept DOIs are
   decided when the first non-permissive deposit is prepared. Moot in v0.1, because STAC is planned. Verifying
   whether Zenodo records support per-file licences remains useful.
3. **Code in deposits** → U-13. Recommendation: `uv.lock` + commit hash yes; the sdist only when the repository is
   public. Doing so makes a "corpus and pinned code" snapshot true (REP-4).
4. **The AgentDojo-PROV v2.3 deposit** under the old concept DOI (REP-2) → U-01, done by the user on 2026-10-10 (D-900). It is outside AgentPROV v0.1; the
   v2.3 checksum lists ship in `agentdojo-prov-v2` regardless (R-26).
5. **Verifying the local v2.3 release transcripts against the Zenodo v2.3 deposit** (D-900; formerly the v2.2 archive) → U-07: only
   with the user's consent to download it.
6. **Shipping per-source statistics frames** (`views/stats`) in the deposit → rejected for v0.1 (AD-10 row 12). The
   minimal generic `agentprov stats` kept by Addendum B (AD-10) computes the per-source tables the paper needs from
   a sealed corpus, outside it, keyed by `(content_digest, fn_digest)` (H.8.1, H.8.3)
   [manuscript/figure_pipeline.md §7.4, §7.9].
7. **HEAD `089ed468` in v0.1** → accepted: both snapshots are in `agentdojo-upstream`, records never conflated;
   history blobs are planned.
8. **The 2 GiB archive split and the 2 GiB memory target** → closed as proposals; measured in phase 11.
9. **Tagging the baseline** → closed: the tag `agentprov-baseline-2026-10-07` exists on `579a908` (RESOLUTIONS,
   consolidator check 2). Pushing it is U-16.
10. **Name of the canonical record** → AD-22: keep "AER", always expanded as "AgentPROV Execution Record"; the
    user has the final say before the phase-6 freeze (U-15).

## HL.R Implementation resolutions (phase 3, 2026-10-08)

The code is the reference (`agentprov.raw`, `agentprov.corpus`).

1. **Origin shape.** H.2.3 and C.3.12 differ, and C.3.12 is followed, because the `aer-0.1` schema already enforces
   it. `retrieved` is a date, the field names are `hf.repo` and `introduced_in_commit`, a member's `container` is
   bare hex, and `crc32` is 8 hex digits. Snapshot-level origins arrive in phase 11.
2. **`origins.jsonl`** rows are `{"origin": {…}, "sha256": "sha256:<hex>"}`, sorted by `(sha256, JCS(origin))`.
3. **`members.jsonl`** rows have the keys `container`, `crc32`, `disposition`, `fn_digest`, `label`, `method`, `sha256`
   and `size`. A rejected row also has `code`. The `expand` stage definition (H.8.2) includes `selection_sha256`,
   because rows depend on the include and nested patterns.
4. **`register.jsonl`** rows have 12 members (`rid`, `subject`, `subject_key`, `code`, `severity`, `stage`,
   `disposition`, `rule`, `detail`, `owner`, `ids`, `previous`).
   - A member's subject is its label; a nested member's is prefixed `<parent>!/`, and a member whose name was
     rejected is `#<index>`. Every member of an archive input, at any level, is `<input>!/<chain>!/<member>`
     (D-384): one rule for the importer's and the `expand` stage's entries. A container may itself be a member object
     (a declared nested archive, or a container member of an archive input; D-380/D-381).
   - An expand worker crash is `expand.failed`.
   - A nested archive that the archive's content reaches again with another selection (one inner archive at two
     declared levels) is not expanded twice: that reach is `expand.conflict`, and the rest of the archive imports
     (CB-22). A conflict that involves a caller-supplied container still raises `raw.members.conflict`.
   - A repeat of the same (subject, code, stage) collapses into one entry.
5. **`executions.jsonl`** rows omit every later-phase field (facets, `logical_key`, SEM and PROV stages) rather than
   holding placeholders. `status` and `n_origins` are derived from the register and the origins at flush.
6. **Writer.** M.1.2 names no corpus writer module, so `corpus/writer.py` (`CorpusWriter`) is added. The git-ignore
   check of H.1.5(5) is supplied by the caller, because M.5.3 forbids `subprocess` in `corpus`.
7. **Known gaps.**
   - The `expand` job reads a container fully into T1 memory, so a container near the RSS cap fails as
     `worker.limit.rss`. The largest in-scope container is 244 MB. Seeking on a store file descriptor is a phase-11
     follow-up, done with the SEC-07 calibration.
   - The Windows `os.link` path is untested.

## HL.R6 Implementation resolutions (phase 6, import, 2026-10-08)

The code is the reference (`agentprov.corpus`, `agentprov.adapters.runner.importer`); `agentprov import` writes these files
into `<DIR>.partial/` (MN N.2.2 note).

1. **Index rows** gain the PROV and validation members of H.3.1 **only when those stages ran** (`import --until aer` writes
   phase-3 rows): `digests.prov.<spec>.json` (sha256 of the PROV-JSON file bytes, `null` without output),
   `paths.prov.<spec>.json` (only with output; checked against the layout), `stages.prov.<spec>`, `digests.validation`
   (sha256 of the JCS bytes of the execution's `validation/results.jsonl` row) and `stages.validation`. `status` folds the
   nested stage states (H.3.2(1)). `sem`, `facets`, `ev`, `cell`, `logical_key` and `oracles` stay omitted until SEM.
2. **`validation/results.jsonl`**: one JCS row per execution, sorted by `ex`: `{aer: {errors, mode, skipped, verdict},
   checks: {<check id>: pass|fail|skipped|not_applicable}, ex, spec, verdict, versions}`. `checks` holds `aer.validator` and
   every tier-4 check of the spec; only ids and statuses are stored (finding details may quote identifiers derived from
   source data). **`validation/summary.json`** (format `agentprov-validation-summary/0.1`, a subset of H.2.12) counts the
   executions per check and status.
3. **`derivation.json`** has the stages `expand` (container dialects), `aer` (`adapter`, `adapter_code_sha256` over the
   family's package, `profile`, `profile_sha256`, `rules`, `rules_sha256`, `format`, the runner's `engine` and
   `engine_code_sha256`, `limits_sha256`, and `mode: "release"` for a release-mode import only (D-623); `rules` are
   every catalogue the corpus's AERs were sealed with, kept across the runs of one `aer` function (D-623), not only the
   last run's), `prov` (`spec`, `rules` = `{"aprov": <catalogue version>}` and `rules_sha256` of that catalogue (D-640;
   `rules` is absent before D-640 and in `agentprov-corpus/0.1`, and the version is then read off the digest: the
   current catalogue or a byte-exact archive, D-621), `engine`
   `agentprov@<version>` and `engine_code_sha256` over `prov/` (without `prov/compat/`), `vocab/` and their import
   closure, `options`, `serialisers`) and `validation` (`checks`, `mode`, `engine`, `engine_code_sha256` over
   `validate/`, `aer/validate.py`, `aer/accounting.py`, `sem/validate.py` and their import closure (H.8.2(2), D-451),
   `libraries`), each with `fn_digest`; then `lockfile_sha256` (the core `uv.lock` of a source
   checkout, else `null`) and `python`. This is DECISIONS D-13's record of the engine version and code digest. A resumed
   import compares the `fn_digest` of every stage both runs define (G4).
4. **The working `corpus.json`** is a phase-6 subset of H.2 with `"sealed": false` and `"state": "working"`: identity,
   `partial` and the effective selection, the source with its profile reference and one snapshot (origin, the pin's
   identifying fields, the pin-check counts, candidates/executions/not_imported/selection_excluded, and the snapshot's
   own `selection` when it was imported with one; MN N.1.7, NF-36, and `incomplete: {"reason": "drained" |
   "interrupted"}` when the last run of it stopped before it ran to the end; MN N.1.7, N.1.10, D-610), the adapter reference
   with its code digest, formats, the producer block (version, interpreter and advisory, platform, isolation, key
   distributions, lockfile digest), the effective limits and overrides, and counts read back from the index and the
   register. It holds no time. Sealing writes the full manifest (phase 11).
5. **Register severities** for seal issues follow the severities H.6.3 states for core codes; adapter codes keep the
   mapper's. Several issues of one code in one execution become one entry (`ids` merged; `detail` "<n> issues").
6. **Origins** of `--input` files come from a pin check: `git` (blob id matches a cached tree listing) or the family's
   listing origin (adprov: `corpus`). A file the pin does not vouch for is `raw.origin.blob_mismatch` (ingest, error,
   `not_imported`) and its bytes are not stored (MN N.2.2 note item 3).

## HL.R11 Implementation resolutions (phase 11, 2026-10-12)

Notes only; the normative text above is unchanged. The code is the reference (`agentprov.corpus`, `agentprov.release`).
Decisions: DECISIONS D-30 to D-49.

1. **H.1.6 (corpus spec).** `[licence]` gains `decided_by` (a non-empty string naming who decided the derived licence;
   D-44) and `files` (the names of the verbatim upstream licence files written to `LICENSES/<source_id>/`, supplied from
   the corpus's own raw store or by `package --licence-file NAME=PATH`). No two `files` names may share a G.3.6
   collision key (case and Unicode normalisation), and none may share one with the generated `NOTICE.md`; `package`
   also refuses two sealed labels that collide (`package.refused.label_collision`). `[layout] shard_depth` is
   required. `derived = "inherit"` takes the source licence (D-44). The corpus id is the spec's, never the working
   manifest's (D-35).
2. **H.2 (manifest), additions to the as-built `corpus-0.1` schema** (`src/agentprov/corpus/manifest.py`):
   - `layout {shard_depth}` records H.1.3's depth.
   - `datasheet {card_sha256, statements_sha256, statements[], claims[]}`: the decided statements (datasheet-items.md)
     emitted for this corpus, with the digest of the statements table.
   - `profiles.semantics[]` entries (`ProfileRef`) carry `paths` (an array of `rules/<name>.profile.toml`, at least
     one) where a source-profile entry carries one `path`.
   - `validation` is the D-40 shape: `mode`, `checks[] {id, version, tier, pass, fail, skipped, not_applicable}`,
     `tiers[]`, `linkage {spec, applicable, resolved}`, `linkage_resolved_pct` (a decimal object, `null` when nothing is
     applicable) and `libraries`.
   - `counts.members` gains `rejected` beside `containers`, `selected` and `not_selected`; snapshot counts follow D-33
     (`candidates == executions + not_imported`; exclusions in `selection_excluded`).
   - `sources[].lineage` is the profile's `[lineage]` table verbatim and `duplicates` is the tally object (D-41).
   - A working manifest written by `derive` or `recompute` has `derived_from {command, corpus_id, corpus_version|null,
     fn_digests, manifest_sha256, recomputed, root_digest|null, semantics, state}`; `command` and `recomputed` are
     additions to H.8.5's shape (D-30). `semantics` (the semantics profile refs) and `fn_digests` (the `fn_digest` of each
     recomputed `sem`/`prov`/`validation` definition) are part of what a resume must match, so a resume under another
     `--semantics-profile` or another build is refused, exit 4 (N.1.8(3); BF-32).
   - A git snapshot origin has exactly one of `subtree` (a string) and `subtrees` (a sorted array of two or more
     paths) (D-33).
3. **H.8.2 (`derivation.json`).** New stage entries: `views` (the view and its engine), `compat` (`{stage: compat, fn:
   provenance, spec, status, view, engine, engine_code_sha256}`; D-37) and `reuse` (`{enabled, reused, recomputed,
   recomputed_executions}`; D-30). The `reuse` entry records the invocation that finished the corpus. The `views` and
   `compat` entries are separate from `prov`, so the importer's resume check (by stage name) is unaffected.
4. **H.8.4 (comparison classes).** As built: `identical`, `changed_explained`, `unexplained_change`, `failed`,
   `unverified`, plus `index_refreshed` counted apart. The *declared identity* of a stage is its definition minus
   `fn_digest`, `engine_code_sha256`, `adapter_code_sha256` and the digests beside an integer version (D-30, D-31).
5. **H.3.1 / H.3.3 (index).** Facets are the core facets only; `x.*` facets and `--pipeline` are deferred (D-34).
   `logical_key` is `null` when a cell member is unrecorded.
6. **H.10.2 / H.10.4 (deposit).** The default and maximum `--max-archive-bytes` is `2**31 - 1`, because the archives carry
   no ZIP64 extra field (H.10.4 forbids extra fields); membership is planned on a deterministic upper bound of each
   member's stored size, so it never depends on the zlib version (D-42). `--corpus-version` is a seal-mode option;
   `--deposit` takes the version from each sealed corpus. Two format ids are added to `formats.AS_BUILT_FORMATS`:
   `agentprov-deposit-manifest/0.1` and `agentprov-release-scan/0.1`; `agentprov-stats/0.1` is the third phase-11
   addition (D-48).
7. **H.10.1 (verification before archiving).** The builder takes the verifier as an injected callable; `agentprov package --deposit`
   injects `verify --level chain` in release mode (D-38), and the level recorded in `DEPOSIT-MANIFEST.json` says which
   level ran. `seal()` also runs the chain level before the swap (N.2.11 step 3).
8. **HL.R7 (expand streaming)** remains open and moves to phase 12 (D-47). **Done (phase 12b, D-58):** the `expand` job
   opens its container by digest, hashes it in chunks and reads it through the handle (`JobContext.open_input`); the
   container is never held whole (peak 134 MiB against 505 MiB for a 380 MB archive; members and rows unchanged).
