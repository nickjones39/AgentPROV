# Building-commit snapshots (D-911, D-940): the tool, the round-1 dry run, the tag push plan

Date: 2026-10-29, Mac Studio. Branch `claude/reverent-blackwell-cc6b30` (base `4870173b`). Brief:
`~/.agentprov/handoff/release-prep-v0.1.0.md`, item 2. Class 0: a new file under `tools/`, its tests, this report and
D-940; no file of any stage scope changes.

**Nothing was pushed, uploaded or published.** The dry run wrote only into the session scratchpad; the corpora were
read, never written. The tag push in section 4 is yours to run.

## Your decisions, in one list

**Approved (the user, 2026-10-29, in the release-preparation window: "i approve your recommendation"): every
recommendation below, recorded as D-942.** Outward steps stay the user's to run.

| # | Decision | Recommendation |
|---|---|---|
| S-1 | Push the 6 local `wave2/build-*` tags to the development repository (section 4) | **Yes**, with the exact refspecs below. Two of their commits (`0ea673f7`, `3bb905d9`) are reachable from no branch, only from their local tag |
| S-2 | Also tag round 1's commits on the development repository (`round1/build-5b1f6fdf`, `round1/build-5fc39c16`, `round1/build-d93aa261`, `round1/seal-8bb6bc92`) | Yes (optional). They are already on `origin/main`, so they are safe today; a tag names them for an auditor |
| S-3 | Snapshot the **sealing** commits too (role `sealing`; no stage checks) | Yes (the default). Sealing ran `package`, which wrote the sealed manifest, datasheet and checksums; one more snapshot (~29 MB) per sealing commit |
| S-4 | What the snapshots leave out | The 5 copyleft fixtures (D-911) **and**, unless you decide U-06 otherwise, the rest of the real third-party fixtures (finding below). Recommendation in `public-repo-plan.md` P-2 |
| S-5 | The 36 redacted gitleaks findings in every snapshot (section 3) | Triage them by class (D-920 method, value-blind) before the snapshots go on an open-access record |

**Finding (affects S-4 and the public repository).** D-911 leaves out only the copyleft fixtures. But Addendum B-2 and
K.4.2 keep *every* fixture that holds third-party model outputs in the private repository "until the user decides
otherwise" (U-06, model-provider terms; not yet decided): 556 permissive real-data `SOURCE.json` entries in 33
fixture directories, 145 entries with no `licence_class` in 6 more, and 4 `restricted_use` (AgentHarm) entries. An open-access snapshot of a building
commit publishes them. The same data is published in the corpora under their source licences, so publishing the
permissive fixtures is consistent with the release; it is still U-06, and yours. The tool takes `--exclude PATH` for
whatever you decide (the stage digests do not depend on `tests/`).

## 1. The tool

`tools/building_commit_snapshots.py` (standard library only; it never imports `agentprov` itself):

```bash
uv run python -I tools/building_commit_snapshots.py plan --corpus DIR ...
uv run python -I tools/building_commit_snapshots.py build --corpus DIR ... --out NEW_DIR \
    --exclude-list docs/reports/release/building-commit-exclude.toml
uv run python -I tools/building_commit_snapshots.py verify --manifest NEW_DIR/BUILDING-COMMITS.json [--corpus DIR ...]
```

* **Commits.** From each corpus: `producer.build_steps[].git_commit` (D-780; per step, the `stages` it wrote); else the
  datasheet statement `building-commit-by-digest-<abbrev>` (round 1; the full id must also appear in the sealed
  `DATASHEET.md`); else `--attribute DIR=COMMIT`, recorded as an operator attribution. No commit is ever guessed. A dirty
  build step is refused. The sealing commit (`producer.git_commit` of a sealed manifest) is added as role `sealing`.
* **Snapshot.** `git archive --format=tar --prefix=agentprov-<commit12>/` minus the exclusions, gzipped with mtime 0 and
  no file name: `agentprov-src-<commit>.tar.gz`. Exclusions are found in each commit's own tree: every
  `tests/fixtures/<dir>/` whose `SOURCE.json` marks a sample `licence_class: restricted`, the matching
  `tests/fixtures/LICENSES/<dir>-*` texts, `--exclude` paths (each must match at every commit), and the
  `[[exclude]]` tables (`path`, `reason`) of `--exclude-list` files, the format of `public-export.toml`. A listed path
  may be absent at some commits, but it must match at one; a typo refuses before any archive is written. Each excluded
  path is listed in the manifest with its blob id and reason.
* **Tree check.** Every member's git blob id and mode must equal the commit's `ls-tree` entry, the member set must equal
  the tree minus the exclusions, and the archive's pax comment must name the commit. `listing_sha256` (sha256 of the
  sorted `<mode> <blob> <path>` lines) can be recomputed from the snapshot alone or from the commit.
* **Stage digests by the snapshot's own code.** The snapshot's `src/agentprov` is extracted to a temporary directory
  and a child `python -I -B` imports *that* `agentprov` (checked) and computes `expand`, `aer` (engine and adapter),
  `sem` (engine and each semantics profile digest), `prov`, `validation`, `views` and `compat` digests over
  `stage_scopes`. Each is compared with every `derivation.json` entry the commit wrote. The source profile and rule
  catalogues named by digest must be in the snapshot with those bytes; the lockfile digest must equal the snapshot's
  `uv.lock` for a one-commit corpus. Any difference refuses the build, and nothing is written.
* **Scrub ancestry.** Each snapshot commit must descend from `42a85025` (the commit that masked account paths and
  secrets in earlier files).
* **`verify`** needs no repository: archive size, sha256 and md5, the pax comment, the listing digest, the excluded
  paths' absence, and the stage digests recomputed by each snapshot's code, compared with the manifest and (with
  `--corpus`) with the corpora again. This is what a reader of the software record can run.
* **Manifest** `BUILDING-COMMITS.json` (`agentprov-building-commits/0.1`): per snapshot the commit, tree, commit date and
  subject, the roles (corpus, build or sealing, basis, stages), the scrub ancestor, the archive (name, prefix, tar and
  gzip sizes and digests, md5, member count, listing digest), the exclusions, and every check with its recorded and
  computed value.

Tests: `tests/unit/release/test_building_commit_snapshots.py` (16 tests, synthetic git repositories with a stand-in
package): the attribution paths and refusals, exclusions, the tree check, a derived corpus checked stage by stage at
two commits, a commit that recurs in the build steps (DTap's import, import, recompute: each stage is the commit of its
last step), an annotated tag's id peeling to its commit, an exclude list (a path present at only one of two commits, its reason
recorded, `verify` clean; a path matching no commit and an entry without a reason refused), an unequal digest or an uncheckable known stage refusing the build, byte-identical rebuilds, and `verify` on a clean and a tampered
archive.

## 2. Dry run on round 1 (scratch)

Run through main's queue (`--class import --cpu 2`) at this branch, Python 3.14.8, git 2.54.0, over the 8 sealed
round-1 corpora, into the session scratchpad (`snapshots-r1/`):

| Commit | Roles | Tree | Members | Excluded | `.tar.gz` | Checks (all equal) |
|---|---|---|---:|---:|---:|---|
| `5b1f6fdf309c` (2026-10-22) | build: mandate, adprov, rope, 2024-06, head, agentdyn-a (statement) | `1a117e676b3f` | 5,409 | 24 | 23.1 MB | 37 code digests (aer ×12, sem ×12, prov ×6, validation ×6, compat ×1), 29 files by digest, 6 lockfiles |
| `5fc39c1601ce` (2026-10-24) | build: ast-survey-agentharm (build step) | `b02c3a58ab26` | 5,867 | 24 | 26.3 MB | 7 (expand, aer ×2, sem ×2, prov, validation), 4 files, 1 lockfile |
| `d93aa26138bd` (2026-10-23) | build: ast-survey-agentdojo (statement) | `bbb7673202fd` | 5,606 | 24 | 25.9 MB | 6, 5 files, 1 lockfile |
| `8bb6bc92bc45` (2026-10-29) | sealing: all 8 | `45c28c5c75bd` | 6,101 | 24 | 29.1 MB | none (sealing) |

* Total 104 MB for 4 snapshots. The 24 exclusions per commit are the 5 copyleft fixture directories and their 5 licence
  texts.
* `verify` with the 8 corpora: 0 problems. A second `build` gave byte-identical archives and manifest.
* The gzip bytes depend on the zlib build; the tar digest and `listing_sha256` do not. Build the deposit's snapshots
  once, on the machine that makes the deposit.
* **Re-run with U-06 applied (D-942, D-943; 2026-10-29).** The same 4 commits, the tool keeping only `permissive` and
  synthetic fixtures: 180 paths left out per commit (24 copyleft as before, 4 `restricted_use` AgentHarm entries, 152
  paths of fixtures with no `licence_class` yet), 5,253 / 5,711 / 5,450 / 5,945 members, 97 MB in all. Every recorded
  digest is still equal (the stage digests never depend on `tests/`), and `verify` with the 8 corpora reports 0
  problems. Once D-946 classifies the unclassified entries in the development repository, a snapshot of a *later*
  commit keeps the permissive ones; snapshots of these four commits keep excluding them, because the rule reads each
  commit's own `SOURCE.json` files. An explicit classification list for older commits would be a tool option, not built.
* Wave 2, by `plan` (read-only): `0ea673f7` (25 trees), `7285a516` (9), `3bb905d9` (5), `296418cb` (3), `f8b5d62b` (3),
  plus `1adb6b36` for the DTap re-import still running. With their sealing commit(s), about 11 snapshots and 0.3 GB for
  the whole release.

## 3. Value-blind secret scan of the snapshots

gitleaks 8.30.1 (`dir --redact`, the snapshot's own `.gitleaks.toml` and `.gitleaksignore`) on the 4 extracted
snapshots: **36 findings in 18 files in each, all `generic-api-key`, the same files in all four.** By place: 24 in
benchmark fixtures (`tests/fixtures/geminicli`, `openhands`), 7 in pre-check sample records
(`docs/reports/precheck/data/`), 3 in docs and decision text (`D-269`, its generated copy in `DECISIONS.md`, a phase-10k
trial report), 2 in tests. The key names are `password`, `API_KEY`, `x-api-key`, `CACHED_TOKEN` and file-name contexts;
no value was looked at. The repository's own CI scan runs in git mode, where `.gitleaksignore` fingerprints apply; in
dir mode they do not. Before the snapshots go on an open-access record, classify these by origin (the D-920 method:
benchmark data, synthetic test value, model output) and record the decision; S-5.

**S-5 done (2026-10-30), on the 13 final snapshots of section 6.** The method was the same: gitleaks 8.30.1 `dir
--redact`, with each snapshot's own `.gitleaks.toml` and `.gitleaksignore`. It ran through the queue (`--class import
--cpu 4`, `GOMAXPROCS=4`) on trees extracted outside the repository (`~/.agentprov/release/s5-gitleaks-2026-10-30/`).
Only rule, file and line were read, never a value.

**Every snapshot has the same 36 `generic-api-key` findings in the same 18 files.** They match the four scanned above,
and only lines in `DECISIONS.md` and `test_repository_hygiene.py` move between commits. The two wave-2 sealing commits
(`c0e711f4`, `3000b220`) add no file and no finding. Classes by origin:

| Files | Findings | Origin and class | Basis |
|---|---:|---|---|
| `tests/fixtures/geminicli/…/SK-PWHASH__m05`, `SK-BACKDOOR__m02` `fs_before.json`, `fs_after.json` (8 files) | 16 | 8 `benchmark-input`, `synthetic-benchmark` (keys `test_auth.py`, `test_auth_pw.py`); 8 `false-positive`, the deposit's file-to-SHA-256 manifest (keys `auth.py`, `auth_pw.py`; the 293 group decided in check 4b of the wave-2 seal report) | each file is byte-identical to a raw object of the sealed `code-agent-misalignment` corpus (sha256 in its `raw/origins.jsonl`, not withheld), and each finding is a row of `wave-2-pre-release-checks/gitleaks-code-agent-misalignment.tsv` (same object, same line) |
| `tests/fixtures/openhands/redcode/…/S2/bash/conversation_log/index20.json` | 7 | `model-generated` | a raw object of `redcode-exec-openhands`; 7 rows of `gitleaks-redcode-exec-openhands.tsv` |
| `tests/fixtures/openhands/oas/…/safety-old-token/utils/evaluator.py` | 1 | `upstream-data` (`synthetic-benchmark`): OpenAgentSafety's own task code for its `safety-old-token` task | a raw object of `openagentsafety` (task workspace, pinned `857798ff`); not in that corpus's release-scan table, so the class rests on the file's origin |
| `docs/reports/precheck/data/{controlarena-persistent,kexin-xu-01-agentharm,openagentsafety}/l2-sample-*.json` (3 files) | 7 | sampled corpus records: ControlArena test keys, kexin-xu values and OpenAgentSafety logins, `synthetic-benchmark` (decision 11 of the wave-2 seal report) | accepted fingerprints in `.gitleaksignore` |
| `D-269` (its entry, its copy in `DECISIONS.md`), `docs/reports/phase10k/trials.md` | 3 | the D-269 placeholder (synthetic) | accepted fingerprints in `.gitleaksignore` |
| `backends/agentdojo/tests/test_probe.py`, `tests/repo/test_repository_hygiene.py` | 2 | synthetic test values | accepted fingerprints in `.gitleaksignore` |

**Result: nothing points to a real secret, and no snapshot needs an `--exclude` (S-4).** The 24 fixture findings are
the corpora's own released bytes, triaged with them. The other 12 are the repository's accepted fingerprints, which
gitleaks applies only in git mode, so dir mode reports them. The fixtures were never opened: they were matched by
digest only.

## 4. Tag push plan (S-1, S-2; for your yes)

**Done (2026-10-29).** On the user's typed yes ("I approve. Do as you recommend for this"), the orchestrator pushed exactly
these 10 tags to `origin` (`nickjones39/agentprov-framework`): `wave2/build-0ea673f7`, `wave2/build-3bb905d9`,
`wave2/build-f8b5d62b`, `wave2/build-7285a516`, `wave2/build-296418cb`, `wave2/build-1adb6b36`, and the newly created
`round1/build-5b1f6fdf`, `round1/build-5fc39c16`, `round1/build-d93aa261` and `round1/seal-8bb6bc92`. `git ls-remote`
showed each remote tag naming the commit in the table below. The steps are kept as the record and for later tags.

**Added (2026-10-29): `wave2/build-2efe7ca0`**, an **annotated** tag on `2efe7ca03691cd3118a07228daefd9345443c2e9`,
pushed by the orchestrator on the user's yes. `dtap-bench-w2c` records three build steps: import at `1adb6b36`, import at
`2efe7ca0` ("WIP D-971"), then recompute at `1adb6b36`. `2efe7ca0` was reachable from no ref, so a gc could have pruned
it. The tool never reads tags: it resolves the commit ids that corpora record with `rev-parse <id>^{commit}`, so an
annotated tag's object id peels to its commit and a ref name is refused (test above).

**`stage_owner` fix (2026-10-29, class 0).** The tool credited each stage to a commit by the commit's *first* appearance
in the build steps, so it put every DTap stage under `2efe7ca0`. The manifest of the 2026-10-29 build lists 0 checks under
`1adb6b36`. The digests were not affected: both commits compute DTap's 6 recorded digests. The tool now walks the steps
in order, and each stage is the commit of the last step that wrote it. The final rebuild after the wave-2 seals records it
correctly.

State on 2026-10-29 (local; `origin` as of the last fetch):

| Tag (lightweight) | Commit | Reachable from |
|---|---|---|
| `wave2/build-0ea673f7` | `0ea673f70371226e7af51798207551894c3e3c8d` | **the tag only** (no local or remote branch) |
| `wave2/build-3bb905d9` | `3bb905d94bff1bc4558a8c377f0a52e1353ad67c` | **the tag only** |
| `wave2/build-f8b5d62b` | `f8b5d62b3b8b5d5f7d9278f635b6ab649f9b0613` | the local branch `claude/wave-2-build2-70da04` only |
| `wave2/build-7285a516` | `7285a51609228ac0dd6828309ca8709026055f7c` | `origin/main` |
| `wave2/build-296418cb` | `296418cbf5147eb3f5a6b285fe5dd5a6cc0449b0` | `origin/main` |
| `wave2/build-1adb6b36` | `1adb6b368f8d89a4222372df086db39e7d56f27a` | `origin/main` |
| `wave2/build-2efe7ca0` (annotated, added later) | `2efe7ca03691cd3118a07228daefd9345443c2e9` | **the tag only** |

Steps (your terminal, in the main checkout):

```bash
git fetch origin
```

```bash
git ls-remote --tags origin 'refs/tags/wave2/*'
```

The second should print nothing (no tag of that name exists remotely). Then push exactly these refs, never `--tags`:

```bash
git push origin refs/tags/wave2/build-0ea673f7 refs/tags/wave2/build-3bb905d9 refs/tags/wave2/build-f8b5d62b refs/tags/wave2/build-7285a516 refs/tags/wave2/build-296418cb refs/tags/wave2/build-1adb6b36
```

Check that each remote tag names the same commit as the table:

```bash
git ls-remote --tags origin 'refs/tags/wave2/*'
```

Optional (S-2), round 1 named on the development repository:

```bash
git tag round1/build-5b1f6fdf 5b1f6fdf309cb7c365aeaeb3dd459d85fbabecf7 && git tag round1/build-5fc39c16 5fc39c1601ced7a4f3227e4bba0524caac18a205 && git tag round1/build-d93aa261 d93aa26138bd848cbe4db613cd4856a75da0c899 && git tag round1/seal-8bb6bc92 8bb6bc92bc458c5f03df86a2d1b81f3492e67ad0
```

```bash
git push origin refs/tags/round1/build-5b1f6fdf refs/tags/round1/build-5fc39c16 refs/tags/round1/build-d93aa261 refs/tags/round1/seal-8bb6bc92
```

Wave 2's sealing commit(s) get a `wave2/seal-<abbrev>` tag the same way once sealed. A new building commit (a
re-import) gets its `wave2/build-*` tag before its corpus is sealed.

## 5. At deposit time

1. After wave 2 is sealed: `build` over all deposited corpora (round 1 and wave 2) into a new directory, through the
   queue, then `verify --corpus ...` over the same corpora. **Done 2026-10-30, section 6.**
2. Triage the gitleaks classes (S-5) and apply U-06 with `--exclude` if you choose so (S-4); rebuild. **S-5 done
   2026-10-30 (section 3): no exclusion needed, so no rebuild.**
3. The snapshots and `BUILDING-COMMITS.json` go on the software record (collection layout, L-6). The public README and
   the datasheets point to that record for building commits (D-911).
4. Optionally a full `git bundle` of the development repository as a restricted-access file (D-911).

## 6. Final rebuild after the wave-2 seals (2026-10-30)

**Superseded by section 7** (the same 13 snapshots without the coding-agent files). This build is kept as the record of
the archives that hold them; the deposit takes section 7's.

Run on the orchestrator's request after the wave-2 seals, with nothing pushed or uploaded. The build used the tool at
`4bae887d`, which includes the `stage_owner` fix, and main's `.venv` (Python 3.14.8, git 2.54.0). It ran through the
queue (`--class import --cpu 4`, label `snapshots-final`) over the **52 sealed corpora**: round 1's 8 and wave 2's 44,
DTap included. The corpora were only read: no `corpus.json` changed after the build started.

Output: `~/.agentprov/release/snapshots-2026-10-30/`. The script and queue log are in `snapshots-2026-10-30.work/`,
outside the record directory. **`build` exit 0; `verify` over the same 52 corpora: 13 snapshots, 0 problems.**

| Commit | Role | Tag | Members | Excluded | Code digests equal |
|---|---|---|---:|---:|---:|
| `5b1f6fdf309c` | build: 6 round-1 corpora | `round1/build-5b1f6fdf` | 5,253 | 180 | 37 |
| `5fc39c1601ce` | build: ast-survey-agentharm | `round1/build-5fc39c16` | 5,711 | 180 | 7 |
| `d93aa26138bd` | build: ast-survey-agentdojo | `round1/build-d93aa261` | 5,450 | 180 | 6 |
| `8bb6bc92bc45` | sealing: 8 round-1 corpora | `round1/seal-8bb6bc92` | 5,945 | 180 | (sealing) |
| `0ea673f70371` | build: 25 wave-2 corpora | `wave2/build-0ea673f7` | 5,778 | 180 | 155 |
| `7285a5160922` | build: 7 | `wave2/build-7285a516` | 5,935 | 180 | 49 |
| `3bb905d94bff` | build: 5 | `wave2/build-3bb905d9` | 5,867 | 180 | 34 |
| `296418cbf514` | build: 3 | `wave2/build-296418cb` | 5,966 | 180 | 20 |
| `f8b5d62b3b8b` | build: 3 | `wave2/build-f8b5d62b` | 5,974 | 180 | 20 |
| `1adb6b368f8d` | build: dtap-bench (import, then recompute) | `wave2/build-1adb6b36` | 5,986 | 180 | 6 |
| `2efe7ca03691` | build: dtap-bench (import) | `wave2/build-2efe7ca0` | 6,357 | 4 | 0 |
| **`c0e711f4b585`** | sealing: 43 wave-2 corpora | `wave2/seal-c0e711f4` | 6,393 | 4 | (sealing) |
| **`3000b220aa8f`** | sealing: dtap-bench | `wave2/seal-3000b220` | 6,426 | 4 | (sealing) |

* **Size.** 13 archives of 346,319,481 bytes, plus `BUILDING-COMMITS.json` (893,318 bytes; 52 corpora,
  `agentprov-building-commits/0.1`). That is 14 files, about 347 MB, for the software record.
* **Reproducible.** The 11 commits also built on 2026-10-29 (section 4's set) gave byte-identical archives (equal
  sha256). Only the manifest differs: it now lists the 52 sealed corpora and the two wave-2 sealing commits.
* **DTap, after the `stage_owner` fix.** DTap's 6 stage checks are now under `1adb6b36`, the commit of its last
  (recompute) step, and none are under `2efe7ca0`. On 2026-10-29 it was the other way round. There are 334 code-digest
  checks in all, as on 2026-10-29.
* **Exclusions.** Like `2efe7ca0`, the two wave-2 sealing commits come after D-945 and D-946, so their own trees exclude
  only the 4 `restricted_use` AgentHarm paths (U-06, D-943).
* The per-corpus tags `corpus/<corpus_id>/v0.1.0` are on the three sealing commits (`8bb6bc92`, `c0e711f4`,
  `3000b220`). The tool does not read tags, and the manifest records commit ids.
* **S-5** (the gitleaks triage of the contents) is done for all 13 snapshots (section 3): 36 findings, each with an
  origin, and nothing to exclude.

## 7. The snapshots without the coding-agent files (P-3a, 2026-10-30)

**Superseded by section 8**, which also leaves out the two user-guide checklists; section 8's folder is the deposit's
set.

**Why.** The user's decision of 2026-10-30 (public-repo plan P-3a, relayed by the orchestrator): "yes only in the new
repo, also when making the software doi make sure to exclude these files too for this in zenodo". The coding-agent
instruction and memory files stay in the development repository, but no file of the Zenodo software record holds them.
The snapshots are `git archive`s of development commits, so they did, and they are built again without them.

**Sweep.** Every member list of the 13 section-6 archives was searched for agent instruction and memory files:
`CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md`, `GEMINI.md`, `SKILL.md`, `.claude/`, `.cursor/`, `.cursorrules`,
`.windsurf*`, `.opencode/`, `opencode.json`, `.aider*`, `.codex/`, `.continue/`, `copilot-instructions.md`,
`.clinerules`, `.roo/`, `.kiro/`, `.mcp.json`, `.gemini/`, `.junie/` (at any depth), `docs/agents/` and hand-over
notes. Only the paths P-3a names are found, and no nested `CLAUDE.md` or `AGENTS.md` exists:

| Commit | `CLAUDE.md` | `.claude/` | `AGENTS.md` | `docs/agents/` | `docs/mac-studio-handoff.md` | Files left out |
|---|:---:|---|:---:|---:|:---:|---:|
| `5b1f6fdf309c` | yes | `settings.json` | yes | 82 | no | 85 |
| `5fc39c1601ce` | yes | `settings.json` | yes | 88 | no | 91 |
| `d93aa26138bd` | yes | `settings.json` | yes | 85 | no | 88 |
| `8bb6bc92bc45` | yes | `settings.json` | yes | 102 | yes | 106 |
| `0ea673f70371` | yes | `settings.json` | yes | 91 | yes | 95 |
| `7285a5160922`, `3bb905d94bff` | yes | `settings.json` | yes | 102 | yes | 106 |
| `296418cbf514`, `f8b5d62b3b8b`, `1adb6b368f8d`, `2efe7ca03691`, `c0e711f4b585`, `3000b220aa8f` | yes | `settings.json` | yes | 103 | yes | 107 |

The list is `docs/reports/release/building-commit-exclude.toml`, with these five entries and their reasons:

| Path | Reason recorded in the manifest |
|---|---|
| `CLAUDE.md` | coding-agent operating notes (P-3a) |
| `.claude/` | coding-agent permission settings of the development checkout (P-3a) |
| `AGENTS.md` | coding-agent project memory (P-3a) |
| `docs/agents/` | coding-agent session briefs and history (P-3a) |
| `docs/mac-studio-handoff.md` | machine hand-over notes for coding agents (P-3a) |

Two other files concern sessions but are project records, not agent instructions or memory, so they stay (P-3a's
"unneeded" candidates are for the user's yes): `docs/reports/gui/todo-next-session.md`, a GUI to-do list, and
`docs/workflow/` (the id ledger and the session-status schema of the workflow tools).

**Build.** The tool at this commit, with `--exclude-list docs/reports/release/building-commit-exclude.toml`, the same
52 sealed corpora, main's `.venv` (Python 3.14.8) and the queue (`--class import --cpu 4`). Output:
`~/.agentprov/release/snapshots-2026-10-30b/`, 13 archives of 343,809,861 bytes plus `BUILDING-COMMITS.json`, 14 files
of 345,030,859 bytes. **`build` exit 0; `verify` over the 52 corpora: 13 snapshots, 0 problems.**

| Commit | Members | Excluded (fixtures + agent files) | Code digests equal |
|---|---:|---:|---:|
| `5b1f6fdf309c` | 5,168 | 265 (180 + 85) | 37 |
| `5fc39c1601ce` | 5,620 | 271 (180 + 91) | 7 |
| `d93aa26138bd` | 5,362 | 268 (180 + 88) | 6 |
| `8bb6bc92bc45` | 5,839 | 286 (180 + 106) | (sealing) |
| `0ea673f70371` | 5,683 | 275 (180 + 95) | 155 |
| `7285a5160922` | 5,829 | 286 (180 + 106) | 49 |
| `3bb905d94bff` | 5,761 | 286 (180 + 106) | 34 |
| `296418cbf514` | 5,859 | 287 (180 + 107) | 20 |
| `f8b5d62b3b8b` | 5,867 | 287 (180 + 107) | 20 |
| `1adb6b368f8d` | 5,879 | 287 (180 + 107) | 6 |
| `2efe7ca03691` | 6,250 | 111 (4 + 107) | 0 |
| `c0e711f4b585` | 6,286 | 111 (4 + 107) | (sealing) |
| `3000b220aa8f` | 6,319 | 111 (4 + 107) | (sealing) |

* **Every stage digest is still checked.** The agent files sit in no stage scope: the scopes are directories under
  `src/agentprov/`, plus the profiles, the rule catalogues and `uv.lock`. Each snapshot's `stage_checks` (the code
  digests, the files checked by digest, the lockfile and the unchecked list) are identical, value for value, to section
  6's: 334 code-digest checks, all equal, and none unchecked.
* **No excluded path is in any archive.** The tree check refuses an excluded member at build time, and `verify` checks
  it again. Read back independently, the 13 archives hold 0 members matching the sweep's patterns.
* **S-5 again.** gitleaks 8.30.1 with the section-3 method, through the queue (`--cpu 4`, `GOMAXPROCS=4`), on the
  new archives found the same 36 `generic-api-key` findings in the same 18 files in each of the 13. None of the 18 is an
  agent file, so section 3's classes stand and nothing needs excluding.
* The section-6 folder `snapshots-2026-10-30/` was trashed on the user's yes.

## 8. The snapshots without the user guide's checklists (Q14, 2026-10-30)

**Superseded by section 9**, which also leaves out the review and workflow files; section 9's folder is the deposit's
set.

**Why.** The user's yes (2026-10-30, relayed by the orchestrator): the snapshots should leave out what the public export
leaves out. The export also drops two internal orchestration checklists of the user guide (Q14):
`docs/user-guide/_go-live.md` and `docs/user-guide/_findings.md`. Both are added to
`docs/reports/release/building-commit-exclude.toml`, with the reason "internal orchestration checklists of the user
guide (Q14, user 2026-10-30)". They exist at 12 of the 13 commits; `5b1f6fdf` lacks them, which `--exclude-list`
allows.

**Build.** The same tool, list, 52 sealed corpora, `.venv` and queue as section 7. It ran at `--cpu 1` beside the
deposit builds. Output: `~/.agentprov/release/snapshots-2026-10-30c/`, 13 archives of 343,754,486 bytes plus
`BUILDING-COMMITS.json`, 14 files of 344,981,664 bytes. **`build` exit 0; `verify` over the 52 corpora: 13 snapshots, 0
problems.**

* **Two more files left out at each of the 12 commits that have them**, so each archive holds 2 members fewer than
  section 7's. The `5b1f6fdf` archive is byte-identical to section 7's.
* **Every stage digest is still checked.** Each snapshot's `stage_checks` equal section 7's, value for value: 334
  code-digest checks, all equal, 0 unchecked. Neither file is in a stage scope.
* **No excluded path is in any archive.** Read back, the 13 archives hold 0 members matching the agent-file patterns
  of section 7 or the two checklists.
* **S-5 again** (section-3 method, queue `--cpu 2`, `GOMAXPROCS=2`): the same 36 `generic-api-key` findings in the same
  18 files in each of the 13, none in the user guide. Section 3's classes stand.
* `snapshots-2026-10-30b/` (section 7) stays until the orchestrator says otherwise.

## 9. The snapshots matching the public export (D-1004, 2026-10-30): the deposit's set

**Why.** On the user's yes (2026-10-30, relayed by the orchestrator: "add them to the snapshot exclusions and rebuild"),
the software record leaves out what the public export leaves out (D-1004). Four entries are added to
`docs/reports/release/building-commit-exclude.toml`, which now has 11:

| Path | Files | Reason recorded |
|---|---|---|
| `docs/review/` | `REVIEW.md`, `ultrareview-plan.md` | the code-review agent's REVIEW.md and the ultrareview plan (D-1004, the user's decisions of 2026-10-30) |
| `tools/review/` | `ultrareview_areas.sh` | the ultrareview driver (D-1004, the user's decisions of 2026-10-30) |
| `docs/reports/gui/todo-next-session.md` | itself | a coding session's to-do brief (D-1004, the user's decisions of 2026-10-30) |
| `docs/workflow/` | `id-ledger.jsonl`, `schemas/session-status-1.schema.json` | the multi-session workflow ledger and schemas, dropped from the public export by the user (2026-10-30; D-1004) |

`todo-next-session.md` is absent at the three round-1 build commits (`5b1f6fdf`, `5fc39c16`, `d93aa261`). The other
five files are at all 13.

**Build.** The same tool, the same 52 sealed corpora, `.venv` and queue as sections 7 and 8, at `--cpu 1`, after the
last deposit records. Output: `~/.agentprov/release/snapshots-2026-10-30d/`, 13 archives of 343,416,126 bytes plus
`BUILDING-COMMITS.json`, 14 files of 344,664,665 bytes. **`build` exit 0; `verify` over the 52 corpora: 13 snapshots, 0
problems.**

* **5 or 6 more files left out per commit** (6 where `todo-next-session.md` exists), so each archive has that many
  fewer members than section 8's.
* **Every stage digest is still checked.** Each snapshot's `stage_checks` equal section 8's, value for value: 334
  code-digest checks, all equal, 0 unchecked. None of these files is in a stage scope; `tools/review/` is outside
  `src/agentprov/`.
* **No excluded path is in any archive.** Read back, the 13 archives hold 0 members matching any entry of the list or
  the agent-file patterns of section 7.
* **S-5 again** (section-3 method, queue `--cpu 2`, `GOMAXPROCS=2`): the same 36 `generic-api-key` findings in the same
  18 files in each of the 13. Section 3's classes stand.
* `snapshots-2026-10-30c/` (section 8) stays until the orchestrator says otherwise. The software record takes this
  section's 14 files.
