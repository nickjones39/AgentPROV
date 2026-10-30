# D-530 (proposal): an archive download pin as a per-unit context tree (runner item R2), in import and re-map

Phase 10i follow-up, 2026-10-14. **Status: approved by the user on 2026-10-14 (DECISIONS D-530), with the archive
form of §2.1–§2.2 dropped.** AgentOps-Bench's tasks are byte-identical at GitHub tag v1.0 (commit `c7b29be6`). The user
chose that git pin as the context tree, with the Zenodo zip as its archival twin (README §10). The runner already accepts
a git context tree. Still to build, sequenced by the orchestrator: the re-map fix (§2.3) and the CLI (§2.4). Item 4 is
built on branch `d530-zenodo-key`. The text below is the proposal as written.

## 1. The problem

AgentOps-Bench (spec §D.18) has two pins in Zenodo record 19875693:

- `runs`, the primary pin: a top-level `tar.gz`, imported as an archive input (D-200, D-247, D-248).
- `tasks`: a **zip**, the code snapshot. Its 100 `tasks/<domain>/<NNN>_<slug>.yaml` members are the task definitions.

The reader names a run's task through `auxiliary_for` as `tasks:<member label>` (D-194). The profile declares the role
in `[import] context_artefacts = ["tasks:kunwarshivam-agentops-bench-9153772/tasks/*/*.yaml"]`.

Runner item R2 (D.16.14) exists for exactly this, but three things stop it from taking the zip:

1. **ContextTree takes a walked file tree only.** `ContextTree.tree` is documented and used as a `LocalTree` or
   `GitPinTree`. `_discover_per_unit` walks it, and `store_unit_context` reads each selected file and stores it. The
   archive path, which stores the container first and expands it (AD-12), exists only for the *primary* input
   (`_Pipeline.archive_members`). An `ArchiveTree` given as a context tree would yield the zip itself as its one
   candidate, and no `tasks:` glob matches that.
2. **The CLI never builds a context tree.** `agentprov import` passes no `context_trees`. Only the DTap driver
   (`tools/dtap/import_dtap.py`) does. The CLI gate also refuses a `planned` part.
3. **A re-map drops context trees.** `agentprov recompute` / `derive` re-maps the `expand`/`aer` stages through
   `import_source` with a `StoredRawTree`. `corpus.derive.import_arguments` and `cli/derive.py::_remap` pass no
   `context_trees`. During a re-map, `_AuxListing` therefore knows no `<role>:` labels, `auxiliary_for` returns `{}`,
   and each AER is re-mapped **without** its task join. So `recompute --dry-run` on any corpus whose import used a
   context tree (DTap, and AgentOps-Bench once imported) should report AER differences that no version bump explains.
   This is from reading the code. The phase-10i trial measures it (§5); the result will be added here.

Item 3 already affects DTap. It is not specific to archives.

4. **The fetch layer refuses this pin's file key.** The tasks pin's Zenodo file key is
   `kunwarshivam/agentops-bench-v1.0.zip`: a GitHub-integration snapshot whose key holds a `/`. `raw.fetch.Recipe`
   requires a Zenodo `file` to match `_FILENAME`, which has no `/`, so `Recipe.from_pin` raises `raw.fetch.recipe`, and
   `verify_download`, `--verify-against-pin` and `--fetch` cannot check this pin at all. `Origin.zenodo` accepts the key.
   Found by the phase-10i trial (2026-10-14). The trial driver checks size, MD5 and SHA-256 by hand instead. D-530's
   CLI part depends on this being fixed: the Zenodo `file` should accept a relative key (`_check_relpath`, as `hf`
   does), with the download URL built from the percent-encoded key.

5. **A re-map refuses DTap corpora with LFS objects** (measured 2026-10-14). On a fresh 30-run DTap sample at one
   commit, `recompute --dry-run` exits 1 with `corpus.rawtree.invalid` ("two stored objects claim one input label").
   `StoredRawTree.label_for` treats every non-member origin as a primary input label. A Git LFS pointer (`git` origin)
   and the object that stands for it (runner item R3, `hf` origin) carry the same label: 2 collisions. Context-tree
   files (R2) are walked as primary inputs too. **DTap's recompute gate has therefore never run on a corpus that holds
   its LFS special cases, so "0 differences" was never claimed for them.** There is no hidden error, but the
   regeneration round must close the gap. Folded into the re-map fix (§2.3) on 2026-10-14 by the orchestrator. No
   in-flight branch touches `corpus/rawtree.py` (checked against every unmerged local branch).

Item 4 was found after the orchestrator relayed approval of items 1–3. It is a `raw/fetch.py` change, outside every
stage digest: **class 0** (no corpus byte or digest moves; the fetch cache path of a key with `/` is nested). The
orchestrator relayed the user's approval of it on 2026-10-14; this session awaits the user's direct confirmation before
calling it approved. Implemented as its own change (`Recipe._check_http`, `download_url`, `cache_path`; tests in
`tests/unit/raw/test_fetch.py`), so it can land before the rest of D-530.

## 2. Proposed contract

### 2.1 Profile (no schema change)

A context role names a **non-primary pin** of the same part, `[[source.pins]] role = "<role>"`, as now. What the role
denotes depends on that pin's `kind`:

| Pin kind | Context tree | Candidate labels | Origins |
|---|---|---|---|
| `git` | `GitPinTree` (or `LocalTree` + `PinCheck("blob")`), as now | tree paths | `git` |
| `zenodo`, `hf` with one `file` (**new**) | the pin's file as an **archive context**: stored, then expanded | member labels (chain labels for nested members, D-380/D-384) | the container: `zenodo`/`hf` from the pin; each member: `member` |
| split archive (`archive = "split-zip"`) | as above through the split descriptor (D-249) | as above | `split` + `member` |

The `"<role>:<glob>"` entries of `[import] context_artefacts` are the context selection. For an archive context they
are the **expand selection** of that container: only matching members are decompressed, and every other member is
recorded `not_selected` (R-40). The profile changes nothing: agentops-bench-pilot@1 already says exactly this.

### 2.2 Runner (`adapters/runner/importer.py`)

- `ContextTree` gains an archive form. Either `ContextTree(role, tree=ArchiveTree(...), pin_check=None)`, recognised by
  `archive_input = True`, or a separate `ArchiveContext(role, archive)`. The owner picks one.
- New `_Pipeline.store_archive_context(role)`, run before `_discover_per_unit`:
  1. store the container with its pinned origin (store-first, A2);
  2. expand it with `ContainerSpec(sha, f"{snapshot_id}:{role}", label, (Selection(include=role_globs),), prefixed=True)`;
  3. use the selected members (read back by digest, re-hashed, as `_MemberTree` does) as `role_candidates[role]`,
     each carrying its `member` origin.

  `store_unit_context` then needs no pin check: the container was verified against its pin before the tree was built.
  A container that `expand` rejects is registered by the writer and fails the import, as for a primary archive input.
- The stage definitions gain one `expand` definition per archive context (its own `fn_digest`; D-380 already keys
  `expand` by digest).
- The working manifest's `snapshot.context[]` entry records enough to rebuild the tree on a re-map: `role`; `origin`
  (the container's, with `sha256` and `bytes`, as `ArchiveTree.snapshot_origin`); `input: {kind: "archive", sha256}`;
  `selection` (the role's globs); `verification: {kind: "download"}`; `stored`. Today the entry holds only role, origin,
  verification and count, which is not enough to replay (item 3).

### 2.3 Re-map (`corpus/derive.py`, `cli/derive.py`, `corpus/rawtree.py`)

This is the fix for §1 item 3, for every kind of context tree. `derive.import_arguments(snapshot_id)` returns
`context_trees` rebuilt from the recorded `snapshot.context[]`:

- **Archive context:** the stored container, copied by the re-map like any non-member object, is expanded again with
  the recorded selection, inside the new working tree.
- **Git and local context:** a `StoredContextTree` reads the context objects already stored for that role (their
  labels and digests are in the units' auxiliary rows and in `raw/origins.jsonl`) and yields them with their recorded
  origins.

`StoredRawTree` walks only the primary inputs. An R3 pinned object is offered as the overlay of its pointer's label (a
`PinnedObject` rebuilt from its stored `hf` origin), never as a second candidate. R2 context objects go to their
context tree. Regression test: a corpus with an LFS pointer, its `hf` object and a context file re-maps with 0
differences. Acceptance: `recompute --dry-run` runs on a DTap sample that includes the LFS special cases.

The re-map never reaches the network and never reads the original input. A corpus whose `snapshot.context[]` lacks the
new fields (any corpus imported before this change) is re-mapped as today, with a notice that context could not be
replayed. It is not refused, so old corpora keep the F-8 behaviour: reproduce at the building commit.

### 2.4 CLI (`cli/import_.py`)

- New repeatable `--context ROLE=PATH` for `--input` imports. Each PATH is checked offline against the pin `ROLE` names:
  `verify_download` for a download pin, the blob listing for a git pin, as `--verify-against-pin` already does for the
  primary input. With `--fetch`, every role named in `[import] context_artefacts` is fetched with its own pin, under the
  same `--allow-network` and large-download consent.
- A per-unit reader whose profile declares a `<role>:` context, imported **without** that role, is refused (exit 2,
  usage) unless `--no-context ROLE` is given. *As built:* the flag is reported as a notice in the command summary
  only; the corpus keeps no record of it (bug pass NF-29) until deferrals part C (D-221) records `context_skipped` in
  corpus/0.2. The units' family join issues show the missing context. This stops a CLI import from
  quietly producing un-joined AERs.
- **Gate (unchanged):** `planned` parts stay refused by the CLI (D.3.2: the registry never raises a status without its
  gate). Trial imports of planned parts keep using drivers (DTap, phase 10i). The new options work for `partial` and
  `supported` parts.

## 3. Byte and digest impact

| What | Effect |
|---|---|
| **AER bytes of existing corpora** | none. The mapping of a unit does not change when its context is unchanged |
| **`aer` stage definition** | `engine_code_sha256` covers `adapters/runner` and `aer`, so the stage digest moves for **every** import after the change (class 1: a stage-definition digest, not record bytes). `recompute` at main then reports drift in the stage definition for older corpora, as the F-8 ruling expects |
| **`expand` stage definitions** | one more for each corpus with an archive context (agentops only, at present) |
| **working `corpus.json`** | `snapshot.context[]` gains fields only for corpora that use context trees (DTap; agentops). Sealed manifests: unaffected. Package does not carry `snapshot.context`, and corpus-0.1 is frozen (D-163). |
| **`raw/members.jsonl`** | gains the container's rows: 100 selected, the others `not_selected` (agentops) |
| **re-map of DTap** | changes from "joins dropped" to "joins replayed"; existing DTap scratch corpora become re-mappable at main |
| **compat gate, PROV, SEM** | none |

Tests the owner would add:

- the runner with a zip context: members stored with `member` origins, AD-12 closure and `verify --level chain` clean;
- a re-map of a corpus with git and archive contexts that reports 0 differences;
- the CLI refuses a missing role;
- the CLI accepts `--context`, checked against the pin.

## 4. Why not the alternatives

- **The family extracts or reads the zip itself.** Rejected. Readers do not open other pins, invariant 3 requires the
  bounded ingest path for archives, and it would bypass store-first and the member origins.
- **Commit the 100 task YAMLs as a pinned table.** Rejected. That is copying source bytes into the repository, and
  their provenance would become the repository rather than the deposit.
- **A second snapshot for the tasks zip.** Rejected. The tasks are not executions, and a snapshot's object origins
  must be its pinned file and that file's members (`_zenodo_snapshot_origin`).
- **Fix only the CLI.** Not enough. Without item 3 every re-map silently drops the joins.

## 5. What the phase-10i trial does meanwhile

The driver is `~/.agentprov/migration-work/phase10i/scripts/p20_trial_import.py`, outside Git; the orchestrator agreed
to this approach on 2026-10-14. It does by hand what §2.2 proposes:

1. check both files against their pins;
2. store the zip with its `zenodo` origin;
3. expand it through `CorpusWriter.expand` with the context glob;
4. pass the selected members as a `ContextTree("tasks", …)` to `import_source`.

The registry part's caveat says that a CLI import has no task joins until D-530 lands. Measured results, including
whether `recompute --dry-run` shows the item-3 differences, are added to `README.md` §10.
