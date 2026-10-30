# Recording the building commit in corpus manifests (design, decision D-780)

Status: **built** after the user's answers (below). Branch `producer-build-commit`, base `main` `53306617`.

## Answers and what changed from the first draft (2026-10-23)

1. `corpus-0.2` is amended in place, on two conditions, both met: the key is additive and optional (a test validates a
   manifest built without it), and no kept corpus is sealed (read-only check of `sealed` and `release.status` in each
   `corpus.json` under `~/.agentprov/corpora`: **33 corpora, 0 sealed**; no `DEPOSIT-MANIFEST.json` exists).
2. Release-mode `package` refuses a dirty build step, does not refuse an absent reason (the datasheet shows the reason, the
   version and `distributions_sha256`), and does not refuse a corpus with no steps (the datasheet says "building commit not
   recorded"; revisited with question 4).
3. `stages` is in every step: only what that process wrote, taken from the writer (an import or live run) or from the
   plan (a derivation), never inferred, by the names of `derivation.json`, sorted. One consequence found while building:
   a `derive` of a complete corpus recomputes nothing, so its step has `stages: []`; the `recompute --stages
   sem,prov,validation` case shows `aer` coming from the import.
4. The `--built-at` attestation is **not built here**. Section 7 stays a proposal, decided later with Option B
   (`docs/reports/regeneration/option-b-deferred.md`): re-running the round makes it unnecessary, keeping the current
   corpora gives it its own branch.

Also found while building: the writer cannot tell a stage it wrote from a layer a derivation copies through it, so a
derivation states its recomputed stages explicitly (`CorpusWriter.plan_build_stages`), and the caller's `GIT_*`
environment is now removed before git runs (`GIT_DIR` would name another repository).

**Byte class 0, proved.** Against `53306617`: 43 digests (`aer` and `adapter_code_sha256` per family, `sem` per family,
`prov`, `validation`, `compat`) computed with `stage_definitions.code_sha256` over `stage_scopes`: none moved.

## 1. The gap

`producer.git_commit` exists only in the **sealed** manifest (H.2.7, `corpus/package.py` ~l. 927), where it is the
*sealing* commit, read by `cli/package.py` `git_facts()`. Working manifests (import, run, derive, recompute) record
`agentprov_version`, interpreter, platform and the lockfile digest, but no commit. D-430 and H.8.4(5) already say
"the commit is `producer.git_commit` where recorded", and the stored round corpora had to be attributed to a commit by
matching code digests (`tools/regen/find_building_commit.py`).

Findings from reading the code:

* The three writers build the working `producer` block in three places: `adapters/runner/importer.py` `_manifest`
  (~l. 3173), `adapters/runner/session.py` `write_documents` (~l. 297, with the `producer_extra` hook) and
  `corpus/derive.py` `_manifest` (~l. 1838, which copies the base producer and overwrites some keys). All three write the
  file through `CorpusWriter.write_document`.
* The CLI already constructs every writer (`cli/import_.py:836`, `cli/derive.py:317`, `cli/run.py:2413`) and already
  injects a value into it (`git_ignored=`). `corpus/` and the runner run no subprocess, and this design keeps that.
* `corpus/spec.py`'s `producer_commit` is something else: the pinned commit of a *frozen corpus of another project*, an
  origin kind. It is not reused.
* The working manifest is not schema-validated; the sealed manifest is (`corpus/manifest.py` `PRODUCER`, published as
  `schemas/corpus-0.2.schema.json`).

## 2. Shape

Working manifest, `producer` gains:

| Key | Type | Meaning |
|---|---|---|
| `git_commit` | 40 hex | the commit of the AgentPROV checkout of the process that wrote this manifest |
| `git_tree_clean` | bool | `git status --porcelain` empty (the definition `cli/package.py` uses) |
| `git_commit_absent_reason` | enum | written **instead of** the two above when the code is not a git checkout: `not_a_source_checkout`, `git_unavailable`, `git_failed`. Same pattern as `lockfile_absent_reason`. Never a placeholder commit |
| `build_steps` | array, oldest first | one record per process that built the corpus content: `{command: import\|run\|derive\|recompute, agentprov_version, git_commit + git_tree_clean \| git_commit_absent_reason, stages?}` |

`git_commit` is the *writer's* commit; `build_steps` is the history. In a one-step corpus (every import, every live run)
the last step equals the top-level pair. `stages` (optional) lists the stages that step computed (`--until` for an
import, the recomputed stages for derive/recompute); I recommend writing it, because a derived corpus's AER comes from
one commit and its PROV from another.

A step is appended when the writer's record differs from the last step, so a resumed import at the same commit adds
nothing, and a resume at another commit adds a second `import` step. A dirty tree is recorded, not refused.

## 3. Lineage and the sealed manifest

* **import / run:** `build_steps = [step]`.
* **derive / recompute --out:** the base manifest's `build_steps` are carried and the derive step is appended. The
  base's old overwrite of `git_commit` no longer loses the import commit. A base without `build_steps` (every existing
  corpus) gives `build_steps = [derive step]` with `stages` stating what that step computed; the earlier commit stays
  *unrecorded*, never guessed.
* **sealing:** `producer.git_commit` / `git_tree_clean` stay the sealing commit (H.2.7, unchanged, release mode still
  refuses unknown or dirty). The working `build_steps` are copied into a new optional `producer.build_steps`. Sealing
  is not a build step.
* `derivation.json` stays untouched: its stage entries are compared for reuse (D-30), so a commit there would break
  reuse.

**Format change?** Yes, one optional key. `agentprov-corpus/0.2` gains `producer.build_steps` (a `BUILD_STEP` shape in
`corpus/manifest.py`, `schemas/corpus-0.2.schema.json` regenerated, re-pinned in `tests/unit/test_format_freeze.py`).
That is the D-224 precedent: no corpus has been sealed in 0.2, so nothing sealed is invalidated. `agentprov-corpus/0.1`
stays frozen (D-163): sealing an aer/0.1 corpus omits the key. Because it is optional, every manifest without it (all
existing corpora) still validates and verifies; readers treat a missing key as "not recorded". `content_digest` covers
`producer`, so it differs for corpora that carry the key; nothing already sealed changes.
**For the user:** amend `corpus-0.2` in place (recommended), or cut `corpus-0.3`.

## 4. Where the commit is computed

In the CLI layer, once per process (cached), by a new `cli/gitinfo.py` that takes over `_git` and `git_facts` from
`cli/package.py` (re-exported; the sealing and deposit callers and their monkeypatched tests keep working). It runs
`git --no-optional-locks` against the **agentprov source root** (`REPO_ROOT`), never the cwd. One hardening is needed and
applies to sealing too: from an installed wheel, `REPO_ROOT` is a site-packages parent, and `git -C` there finds any
*enclosing* repository (a venv inside someone's project) and reports its HEAD. The new function requires
`git rev-parse --show-toplevel` to equal `REPO_ROOT` and `src/agentprov/__init__.py` to exist there; otherwise
`not_a_source_checkout`.

The CLI builds a `BuildStep` and passes it to `CorpusWriter(..., build_step=step)` (a new keyword, like `git_ignored`).
`CorpusWriter.write_document` merges it into the manifest's `producer` when it writes the manifest. No environment
variable can inject a commit. Tests inject the step through the constructor keyword; `tests/conftest.py` gets an autouse
stub for the CLI helper so the suite spawns no `git` and manifests stay deterministic. A writer without a step (library
use, scratch writers) writes nothing: the key is simply absent.

## 5. Byte classes (to be proven by a before/after run)

The design keeps every edit out of every stage scope. `importer.py` and `session.py` are in `AER_SEEDS`
(`adapters/runner`), so editing either would move the AER code digest of every family and make the change class 1. They
are not edited: the importer and session need no change because the writer merges the record. The files touched are
`corpus/writer.py`, `corpus/derive.py`, `corpus/manifest.py`, `corpus/package.py`, `corpus/datasheet.py`,
`cli/{gitinfo,package,import_,derive,run}.py`, schemas, docs and tests; none is in `AER_SEEDS`/`AER_CLOSURE`,
`SEM_*`, `PROV_*`, `VALIDATION_*` or any family closure (`stage_scopes.py`). Predicted: **class 0**, no stage
`code_sha256` moves, no AER/SEM/PROV byte changes, no existing corpus changes. Proof at build: `tests/unit/test_stage_scopes.py`
plus a before/after computation of `aer_scope(<each family>)`, `sem_scope`, `prov_scope`, `validation_scope`
digests, and `tools/regen_pins.py --check`. Output bytes change only for corpora built after this lands (their
`corpus.json`). If the proof shows a scope file is hit, I stop and report.

## 6. Determinism and comparisons

At one commit the record is a pure function of (commit, clean flag, version, command): manifests stay byte-identical
across runs, processes and `--jobs`. The step is computed once at process start, before the command writes anything.

| Place | Treatment |
|---|---|
| `recompute --dry-run`, `verify --level rederive` | compare per-execution outputs, not `corpus.json`; unaffected. A drift message gains "built at `<commit>` (`<command>`)" from `build_steps` when recorded |
| `tools/regen/tree_compare.py` / `d358_building_commit.sh` | byte-compares `corpus.json`; the new `/producer/git_commit`, `/producer/git_tree_clean`, `/producer/build_steps*` pointers are added to its default `--allow-pointer` list (a stored corpus lacks them) |
| `tools/regen/compare.py` | reads `corpus_id` only; unaffected |
| `tools/import_compare.py` | same commit, so identical; a dirty-versus-clean run would differ and rightly shows |
| `tests/unit/corpus/test_derive_cache.py` | already tolerates a `producer`-only difference |
| golden fixtures, migration gates (`migration/`) | hold no `corpus.json`; unaffected |

The key is producer metadata and never a drift finding (`version_drift` reads versions, not the commit).

## 7. Existing corpora: attestation (proposal, not built)

`package --built-at <commit>`: the user names a commit; the sealer reads, with `git ls-tree`/`cat-file` only (no
checkout, no code executed), that commit's `uv.lock` and `stage_scopes.py` constants, computes every stage
`code_sha256` and the family digest, and requires each to equal what `derivation.json` records; any difference refuses.
On success it writes a step `{command: "import", git_commit, basis: "stage_digests_match", ...}`. This proves "a commit
with equal stage digests", not that it was the one run, and the record says so. It would cover the 8 round corpora
(`find_building_commit.py` already does the matching, but its directory lists predate D-451's closures, so the sealer
version must read the scopes from that commit). **For the user to decide;** build only after a go.

## 8. Spec, tests, docs

Spec: H.2.7 (rows and the working-versus-sealed note), H.8.4(5) (the commit is a `build_steps` entry; D-430's wording
"`producer.git_commit` where recorded" is true for one-step corpora), H.5.4 (producer is inside `content_digest`),
HL tests (new HL-T entries), MN N.2.7 notes for `package`. Datasheet line: `Producer: agentprov X at commit <sealing>;
built at <commit> (import), <commit> (derive)` or "build commit not recorded". User guide chapters 4 and 13 (producer
and reproducibility) and the CLI reference if help text changes.

Tests: every writer records the commit; dirty tree gives `git_tree_clean: false`; no checkout gives the absent reason
and no commit; an enclosing foreign repo is not mistaken for a checkout; derive keeps the import step; the sealed
manifest carries both the sealing and the build commits; the schema and validator accept old manifests and reject a
step with both a commit and an absent reason; determinism at `-n 1` versus `-n 2` workers; `recompute --dry-run` gives 0
differences for a corpus rebuilt at the same commit.

## 9. Questions for the user

1. Amend `corpus-0.2` in place (recommended, D-224 precedent) or cut `corpus-0.3`?
2. Should release-mode `package` refuse a corpus with a **dirty** build step (as it refuses a dirty sealing tree)? I
   recommend yes for a dirty step, no for an absent reason (disclosed in the datasheet), and no refusal for a corpus
   with no steps (every existing corpus).
3. Write `stages` in each step (recommended)?
4. Build the `--built-at` attestation (section 7) in this branch, a later one, or not at all?

## 10. Draft decision (D-780)

See `docs/architecture/decisions/D-780.md`. Rejected alternatives: an environment-variable override (injects a commit
into a real run); editing `importer.py`/`session.py` (class 1, moves every AER digest); recording the commit in
`derivation.json` stage entries (breaks reuse keys, D-30); overwriting the base producer on derive (loses the import
commit); a placeholder commit such as `"unknown"` (invariant 7); deriving the commit by code-digest search at read time
(what the round had to do, and ambiguous); computing it inside `corpus/` (no subprocess there).
