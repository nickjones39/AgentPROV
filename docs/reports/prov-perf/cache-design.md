# Tier-4 round-trip cache (D-550): design, trust model and proofs

Session: prov-perf, branch `prov-perf`. Status: **D-550**, requested by the user, push approved 2026-10-14; class 1 (regen-batch item 94). The `validate --corpus`
path is built. The `derive`/`recompute`/`verify --level rederive` call sites (corpus/derive.py, adapters/runner/provjob.py)
and the import call site (adapters/runner/importer.py) come after derive-bugpass and pipeline-perf's D-414 land, as the
orchestrator sequenced (§8).

## 1. Why

Tier 4's PROV-O round trip is 65–81% of the pipeline's CPU (pipeline-perf `profile.md` §1–2). It is also where
PROV processing peaks in memory (`memory-profile.md`). Each re-validation (`validate --corpus`, `recompute --dry-run`,
`verify --level rederive`, the post-check) redoes it for documents whose bytes have not changed since the first
validation. The cache keeps the outcome of the first round trip, so later ones reuse it.

## 2. What is cached, and what is not

**Only the round trip:** the five `pv.roundtrip.*` outcomes that `validate/roundtrip.py:check` returns
(`model_equality`, `graphs`, `completeness`, `datatypes`, `unqualified_layer`).

They depend on the PROV-JSON bytes and nothing else from the corpus. `check(doc, view)` receives the document decoded
by the strict loader and the `ProvView` parsed from it. Both are functions of the bytes. On a Mandate document, these
checks are about 91% of tier 4's time (§6.2).

**Not cached:** the canonical-bytes check, structure, PROV-CONSTRAINTS, evidence linkage and profile rules. They also
read the AER, the SEM documents and the rule registry, and together they take about 20–40 ms per document. Caching
them would put the AER digest, every SEM digest and the catalogues into the key, for little gain. They always run
whenever tier 4 runs.

**The library versions** in the report (`versions`) are computed by `validate_prov` on every call, as before.

## 3. Key

The entry for a document lives at `<root>/<context digest>/<doc[:2]>/<doc sha256>.json`. The *context*
(`validate/cache.py:context`) is computed once per process:

| Component | Why it is in the key |
|---|---|
| `agentprov_code_sha256`: sha256 over every `.py`/`.toml`/`.json`/`.ttl` file of the package, as the stage `code_sha256` | It covers the validation stage's `engine_code_sha256` (`validate/`, `aer/validate.py`, `aer/accounting.py`, `sem/validate.py`). It also covers the round trip's other code: the `prov` engine's `prov/serialise/nquads.py`, the strict loader `ingest/loaders.py`, `io/canonical.py` and the vocabulary. A change anywhere is a miss. That is wasteful during development, but it costs nothing in the regeneration round, which runs on one commit, and it needs no import-closure analysis that could miss a file |
| `validation_code_sha256` | The validation stage digest itself, recorded explicitly (the user's key list). It is subsumed by the row above |
| `libraries`: name, version and a digest of the installed code files (`.py`, `.so`, …) of `prov`, `rdflib`, `pyparsing`, `isodate`, `lxml`, `python-dateutil`, `six` (`absent` when not installed) | `prov` and `rdflib` compute the round trip. The others are what they may load. Hashing the files, not only the version, catches a locally patched or forked library under an unchanged version string (Part 2 discusses a fork) |
| `vocabulary`: `VOCAB_VERSION` and a digest of `vocab/` and `prov/vocab*` | The user's key list. Also subsumed by the package digest |
| `python`: `sys.version` (version, build date, compiler), implementation, `cache_tag`, machine | The interpreter and its standard library (`json`, `io`) |
| `options`: `scope = pv.roundtrip`, `roundtrip = true`, `MAX_FINDINGS`, the surrogate namespace pattern | The tier-4 options that shape the outcome. `roundtrip = False` never reaches the cache (§4) |
| `CACHE_FORMAT = agentprov-tier4-cache/1` | The entry format |

**Not in the key, deliberately.**
- The validation mode (`dev`/`release`, `--strict`): the mode decides how statuses become a verdict (`tier4_row`), not
  the statuses. The same outcome serves both. Release *trust* is §5.
- The AER, SEM documents, registry and `migration` flag: the round trip does not read them (§2).
- Computing the context costs about 0.1 s per process with a warm file cache (0.5 s cold), once in the parent and once
  per worker at module import, before the audit hook.

## 4. Value, storage, concurrency, eviction

- **Entry** (JCS bytes): `format`, the full `context`, `doc_sha256`, `context_sha256`, the `outcomes` exactly as
  `CheckOutcome.as_json()` (status, every finding, `reason`, `truncated`), `outcomes_sha256` over them, and
  `written` (seconds; diagnostic only, never compared).
- **Read** (`DiskCache._read`): at most 8 MiB, through the bounded strict loader. The entry is used only when
  `format` matches, `context` *equals* this process's (the whole object, not only its digest), `doc_sha256` is the
  requested digest, `outcomes_sha256` matches, and every outcome has exactly the expected shape and check ids in order
  (`from_json`). Anything else counts as `rejected`: the file is removed and the lookup is a miss. No exception
  escapes. An I/O error is a miss.
- **What is stored** (`storable`): the five checks in order, none `skipped`, and no `pv.roundtrip.load` finding. A
  library failure (`MemoryError`, `RecursionError`, a `prov` exception) may come from the environment, so it is never
  kept. The next validation round-trips again. An outcome that JCS cannot encode (a lone surrogate in a finding) is
  not stored either.
- **Writes**: a new file `<entry>.tmp-<pid>-<random>` (`O_EXCL`) in the entry's directory, then `os.replace`. A reader
  sees no entry or a whole one. Two writers of the same entry write the same bytes, apart from `written`, and the last
  rename wins. There is no fsync: a cache needs no durability, and a torn file after a power loss fails the parse and
  is a miss.
- **Hits** touch the entry's mtime. `evict()` runs after a command that stored entries. It removes stale temporaries
  older than an hour, then the least recently used entries of any context until the cache fits `max_bytes` (default
  2 GiB). It then removes empty directories. Entries of an old context are never touched again, so they are evicted
  first. The cost is one `scandir` walk.
- **Location**: `$AGENTPROV_HOME/cache/tier4` (default `~/.agentprov`). It is never inside a corpus, never in Git and
  never shipped. Entries are about 2.7 KB for a passing document (§6). A whole round of every stored corpus (about
  126k executions) is about 340 MB, plus file-system blocks.
- **Switch**: `validate --no-validation-cache` (the CLI passes no handle). Library callers pass `cache=None`.

## 5. Trust model and release policy

**What an entry can claim.** An entry says: "the round trip of the bytes with this sha256, in this exact context,
returned these outcomes". The code binds it to both. It cannot be served for other bytes (the digest is the path, and
the content and the job hint are checked against the bytes actually validated). It cannot be served under other code,
libraries or Python (the whole context is compared).

**Who can write the cache.**
1. *The parent (T0)*, from round trips it ran itself, or from a T1 job's frame. A frame is stored only when it names
   the parent's own context digest and the digest of the bytes the parent handed the job.
2. *A T1 worker*, indirectly through its frame. A compromised worker could hand back a forged frame for the document
   it was given. The same worker already decides that document's validation row in the run, so the cache adds
   persistence, not a new capability. The forged outcome would then outlive the run. §5.2 bounds this.
3. *Any process running as the user* (G.1.2: out of scope, like the corpora and the raw store, which the owner can
   also rewrite). This includes a compromised T2 backend (G.1.2: "a T2 compromise is a compromise of the user
   account"). It can plant an entry with a valid context and digests, and a non-audit run believes it. The test
   `test_a_forged_entry_is_served_but_audit_finds_and_replaces_it` shows this.

**Accidents (ADV-7).** Truncation, partial writes, bit flips, an entry from another version, or a hand edit that
breaks the outcome digest are all misses. `test_bad_entries_are_misses_and_are_removed` covers 11 corruptions,
in process and through jobs.

**Determinism.** An entry is correct only if the round trip is a pure function of its key. D-89/D-130 measured 690 of
690 tier-4 reports byte-identical across runs. §6 adds the cold-against-off comparison over real corpora: these are
independent computations, so each pair is an identity test.

There is one pre-existing, data-dependent caveat, not caused by the cache. `_model_diff` reports the first 20 lost or
added records `sorted(..., key=str)`. When more than 20 differ and some `str` forms tie, which 20 are shown can vary
with the hash seed. The cache then replays one valid run's findings. This affects failing documents only, and only in
their finding text, never in a status.

### 5.1 Decision for release, seal and deposit: always recompute (and audit the cache)

`validate --release` builds the cache in **audit** mode. It never serves an entry and round-trips every document. When
an entry exists, it compares the entry with the fresh outcome: the `audited` and `audit_mismatch` counters go to stderr,
and a mismatch is an error message. It then stores the fresh outcome, which replaces a bad entry.

The release outcome therefore never depends on the cache, and every release run also checks the cache, for free.

**Why not trust the binding for release.** The binding (document hash plus whole context) rules out *accidental*
staleness: an entry can only be reused for the same bytes under the same code. Two residual risks remain.
- *Forgery by a local writer* (§5 item 3). Corpora face the same writer. But a release is the point where a third party
  starts to rely on the result, and recomputing removes the cache from what they must trust.
- *Nondeterminism or a key gap* that no test has seen: a library behaving differently with an environment variable
  or a system library outside the key.

A full release validation costs about 3 h of the round's time on the M2 Max at W = 8 (pipeline-perf §5), once per
release. That is cheap against making the cache part of the trusted base.

**`--strict` (without `--release`) may read the cache.** It is the release *mode* of the checks, used in development and
by the round's post-checks. The orchestrator asked whether a cache populated during import could leak into a release
decision. It cannot: the decisions that certify a corpus for others are `validate --release` and the `package`/seal/deposit
gates, which read verification results, not the cache. `--release` never reads it. When the `derive`/`verify` call
sites are built (§8), `verify --level rederive` used as a release gate will take the same audit mode.

### 5.2 Composition with G2c-5 (`--skip-prov-conformance`, CLI-robustness session, agreed 2026-10-14)

The skip is decided by the callers (`corpus/validation.py`, the importer, the live session). With the skip, they do not
call the tier-4 conformance checks at all. The cache handle is consulted only inside `validate_prov`'s
`if roundtrip:` branch, so a skipped run never looks up and never writes an entry, and "skipped" is never stored
(`storable`). A later full `validate --corpus` may be served by the cache. The two branches touch
`corpus/validation.py`; whichever lands second rebases.

## 6. Proofs

### 6.1 Tests (`tests/corpus/test_validate_cache.py`, 18 cases)

- off, cold and warm give the same report bytes: in process and with `jobs` 1 and 3, in both modes;
- a cache made in process serves the jobs, and the reverse;
- a tampered PROV file is not served its old entry;
- 11 kinds of bad entry (empty, truncated, garbage, wrong JSON type, other context, other document, flipped status,
  missing checks, a stored `skipped`, other format, oversize) are misses, are removed, and are rewritten from a fresh
  round trip; in process and through jobs;
- a forged entry with valid digests is believed (the trust model, stated as a test); audit mode detects and replaces it;
- a round trip that fails (`MemoryError` in the library) is never stored;
- `roundtrip=False` never touches the cache;
- a job hint is used only for its own document and its own context;
- the outcomes survive an entry exactly; `storable` refuses load failures, missing and reordered checks;
- eviction keeps the most recently used entries within the bound and removes stale temporaries;
- 8 concurrent writers × 20 writes of one entry leave one whole entry and no temporaries;
- the CLI: `--no-validation-cache` creates nothing, and cold, warm (`--jobs 2`) and off print the same report; `--release` audits
  (the same report and exit code as `--release --no-validation-cache`) and never hits.

### 6.2 Real corpora (scratch clones under `~/.agentprov/migration-work/prov-perf/`)

Run through `tools/suite_queue.py --class import` at `690b3629` (the `src/` of the pushed commit), 2026-10-15, on the
8 stored corpora:
- for each corpus, `off -j2`, `cold -j2`, `warm --in-process`, `warm -j1` and `warm -j4`;
- for Mandate and AgentHarm, in full, also `off --in-process`, `cold --in-process` and `warm -j2` from that second
  cache.

**Every corpus gave one report digest across all its runs (46 runs).** The report file holds every row, the counters,
the failures, the notices, the summary and the D-40 member. Run log: `~/.agentprov/migration-work/prov-perf/runs/`.

| Corpus | Executions | Runs | Report bytes | Off -j2: wall / CPU | Cold -j2: wall / CPU | Warm in process: wall / CPU | Warm -j4: wall | CPU off -j2 ÷ warm in process |
|---|---|---|---|---|---|---|---|---|
| mandate-agentdojo-eval-p10 | 396 (all) | 8 | identical (`c7f3bc4084ac`) | 80 s / 128 s | 129 s / 154 s | 16 s / 16 s | 22 s | 8.0× |
| ast-survey-agentharm-p10 | 1056 (all) | 8 | identical (`66c59dc00f6b`) | 248 s / 368 s | 226 s / 325 s | 50 s / 50 s | 42 s | 7.3× |
| ast-survey-agentdojo-p10 | 300 (sample) | 5 | identical (`e42520bf774d`) | 60 s / 113 s | 60 s / 113 s | 14 s / 14 s | 10 s | 8.3× |
| rope-p10 | 300 (sample) | 5 | identical (`e3c77758f2c3`) | 117 s / 225 s | 118 s / 225 s | 26 s / 26 s | 16 s | 8.6× |
| agentdyn-a-p10 | 300 (sample) | 5 | identical (`f9d9fd2400fe`) | 104 s / 195 s | 104 s / 195 s | 26 s / 26 s | 18 s | 7.4× |
| agentdojo-upstream-head-p10 | 300 (sample) | 5 | identical (`9715e30bb865`) | 61 s / 109 s | 60 s / 109 s | 18 s / 18 s | 15 s | 6.0× |
| agentdojo-upstream-2024-06-p10 | 300 (sample) | 5 | identical (`12d41d389c7f`) | 57 s / 104 s | 56 s / 104 s | 15 s / 15 s | 12 s | 6.8× |
| adprov-v1-release-p10 | 300 (sample) | 5 | identical (`786372b548d9`) | 50 s / 92 s | 50 s / 92 s | 14 s / 14 s | 11 s | 6.6× |

In process, mandate-agentdojo-eval-p10: off 129.3 s CPU, cold 118.5 s, warm 16.1 s (8.0×).

In process, ast-survey-agentharm-p10: off 276.5 s CPU, cold 278.3 s, warm 50.4 s (5.5×).

The ratio column compares the CPU of a 2-worker run with the cache off (parent and workers, worker start-up included)
with a warm in-process run. The in-process pairs above are the like-for-like figures: **5.5× and 8.0× less CPU** when
warm, and **+0.7% or less** when cold. A warm `-j4` run is wall-bound by the parent's reads and the AER tier.

Every run exits 1, with the cache off too, with `validate.results.differ` on every row. Every row passes, but the stored
rows predate today's four `pv.constraints.*` checks (cycles, derivation_parts, ordering, unique_start; regen item 10).
This is a property of the stored corpora, which the round regenerates. It is not a property of the cache.

Single-document smoke on Mandate (5 executions, this machine under load): tier 4 off 0.23–0.67 s, warm
0.024–0.058 s (about 12×). The remainder is the strict JSON load, the JCS canonical check, structure, constraints,
linkage and profiles.

## 7. Byte classes and digests

- `validate/cache.py` (new) and `validate/prov.py` (the `fidelity` keyword) are inside the validation stage's
  `engine_code_sha256`. They move it for every corpus: regen-batch item 94. Rows, PROV and SEM bytes do not change.
  The validation stage definition's `fn_digest` moves with the code digest. `recompute` reports this as a code-digest-only
  change, which is not a declared version, so it passes when the outputs are identical (H.8.4).
- `corpus/validation.py`, `corpus/validation_job.py` and `cli/checks.py` are outside every stage digest (class 0).
- Later (§8): `adapters/runner/provjob.py` and `importer.py` are inside the AER stage digest (`adapters/runner`), so they
  move the AER engine digest, like D-414's item 42. They will join item 94.

## 8. Remaining call sites (sequenced by the orchestrator)

1. **`derive`/`recompute`/`verify --level rederive`: built** on `prov-perf-runner` after derive-bugpass landed.
   - `Derivation.validation_cache` is set by `cli/derive.py` and by `corpus/verify.py`, where `--release` makes it an
     audit cache.
   - `_stage_hints` stages, per `prov` job, the entry for the source row's stored PROV digest (input 1, role
     `fidelity`). The hint objects are reference-counted and removed when the last unit that uses them is finished.
   - `_prov_result` stores each frame against the PROV bytes it writes.
   - Fidelity params are built only when `validate` and `conformance` (G2c-5) hold.
   - Tests (`tests/unit/corpus/test_derive_cache.py`):
     - `recompute --dry-run` gives the same comparison with the cache off, cold and warm, in process and with
       `--jobs 2`;
     - a warm run serves both round trips from its hints and stores nothing;
     - `recompute --out` writes the same bytes;
     - `verify --level rederive` agrees.
2. **`import`: built** on `prov-perf-runner` after D-414 (b57006d0), to push after Part 1.
   - The importer's prov batch passes `{"fidelity": {"collect": true, "hint": false}}`.
   - `_prov_result` stores each `{"fidelity": …}` frame against the PROV bytes it writes, so the first validation (the
     import) fills the cache, and the post-import validation and the post-check are warm.
   - `import --no-validation-cache` turns it off.
   - Tests (`tests/corpus/test_validate_cache_import.py`):
     - the corpus bytes are identical with and without the cache, at `workers` 1 and 2 and in process;
     - every execution leaves one entry, and a later `validate --corpus` hits all of them with the same report, in
       process and through jobs;
     - the `prov` job uses a hint only for its own bytes, and emits a frame only when it ran the round trip.
   - The live session pipeline (`adapters/runner/session.py`) keeps no cache: `_Pipeline.validation_cache` defaults
     to `None`.
