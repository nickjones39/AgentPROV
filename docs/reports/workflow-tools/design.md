# Multi-agent workflow tooling: design (D-420–D-429, proposals for the user)

Session "multi-agent workflow tooling", branch `workflow-tools` (from origin/main `c4fd0dc2`), 2026-10-14.
Status: **design for the user's review. Nothing in this document is built yet.** Decisions D-420–D-429 are
proposals; none is approved.

## 0. Problem and scope

Up to 12 sessions work in parallel worktrees, coordinated by the orchestrator ("Phase 8 setup"). Costs observed
2026-10-12..14, and the deliverable that removes each one:

| Observed cost | Root cause | Deliverable |
|---|---|---|
| Every push moves `main`; each waiting branch re-merges and re-runs its 23–45 min suite (one branch three times) | one suite per branch per push, serialised through `main` | 1. merge train (§1) |
| Append-only conflicts on DECISIONS.md, AGENTS.md §0, regen-batch.md, D_adapters.md items, `registry/__init__.py` | many writers append at the same place in one file | 2. conflict-free shared docs (§2) |
| D-150 used twice; regen-batch item 29 twice; D.2.9 item 14 twice | numbers chosen by reading a file that other branches have not merged yet | 3. id ledger (§3) |
| Several branches regenerate the same golden, gate-D and C.16 pins, then conflict | pins hand-merged; no single regenerator | 4. `regen_pins.py` (§4) |
| Load 50–70 on 12 cores | suites, imports and rehearsals start independently | 5. heavy-job classes (§5) |
| Status known only by messaging each session; a 15-hour stall unnoticed overnight | no shared, machine-readable status | 6. session status files (§6) |

**Constraints applied throughout.** No product code under `src/` changes, except the registry list generation if
the user chooses it (§2.4, and it is asked separately). No force-push, no history rewrite, no branch or worktree
deletion (cleanup stays with the orchestrator); `review/*` and `review-base/*` are untouched. Every tool is tested in
temporary git repositories, never the real one. No tool performs network access unless a flag says so, and no session
runs such a flag without the user's yes. Restructuring shared files (§2 and any AGENTS.md change) waits until the
orchestrator says the merge queue has drained, then lands as one commit series in a dedicated slot. The tools of §1,
§3, §4, §5 and §6 are new files only and can land earlier.

**Build order (proposal).** (a) §6 status files and §3 id ledger, small and useful at once; (b) §1 merge train
(needs the suite queue on main); (c) §4 pin regenerator in `--check` mode, write mode family by family after D-31
and part C land; (d) §2 migration in the drained slot; (e) §5 is an interface proposal for the suite-perf session,
which owns `tools/suite_queue.py`.

---

## 1. Batched merge train (`tools/merge_train.py`) — D-420

### 1.1 What it does

```
uv run python tools/merge_train.py plan  BRANCH...            # merges only, in a scratch worktree; no suite
uv run python tools/merge_train.py run   BRANCH... [--bisect]  # merges, ONE full suite via the suite queue
uv run python tools/merge_train.py run   BRANCH... --push --approval "<user's words, verbatim>"
uv run python tools/merge_train.py status [RUN_ID]
```

1. **Base.** The train starts from the local `origin/main` ref as it is (`--fetch` runs `git fetch origin` first; it
   is the only network step and is opt-in). It records the base sha.
2. **Scratch worktree.** `git worktree add --detach ~/.agentprov/merge-train/<run-id>/wt <base>`. The train works
   on a detached HEAD, so it creates no branch (as built; the first draft named a `train/<run-id>` branch). It never
   writes in a session's worktree. The orchestrator removes old train worktrees; the tool only lists them
   (`status`).
3. **Admission checks per branch** (refused with a reason, or a warning with `--allow-unverified`):
   - the branch head equals the head recorded green in that session's status file (§6), i.e. the last full suite ran
     on this exact commit;
   - the branch contains no merge-base older than N days without a re-merge of main (warning only);
   - the branch is not `review/*` or `review-base/*` (always refused).
4. **Merge in order.** `git merge --no-ff --no-edit <branch>` for each branch, message
   `Merge branch '<b>' (merge train <run-id>, k/N)`. A conflict stops the train at that branch (or, with
   `--skip-conflicting`, drops it, reports it and continues). Conflicts in *generated* files only (§2 indexes, §4 pin
   files) are resolved by re-running the generator, never by hand, and the result is committed into the merge commit
   (it is local and unpublished, so this is not a history rewrite). A conflict in a pin file is resolved only if
   every changed pin is attributable to a branch that itself changed that pin (§4.4); otherwise the train stops.
5. **One suite.** The integration head is checked by one full suite through the suite queue
   (`tools/suite_queue.py -- pytest -n auto --dist loadgroup -p no:randomly`, the gate command of D-403), plus
   `ruff`, `mypy`, `tools/check_unicode.py`, `regen_pins.py --check` and the generated-docs check. The report
   (`~/.agentprov/merge-train/<run-id>/report.json`) records the exact commit, the command, counts and wall time.
6. **Green and `--push`.** `git push origin <train-head>:refs/heads/main` without `--force` and without `+`, so the
   remote refuses anything that is not a fast-forward. Before pushing, the tool checks that `origin/main` still equals
   the recorded base (after a `--fetch`); if `main` moved, it stops and asks for a new run (no automatic re-merge).
   The tool never pushes without both `--push` and a non-empty `--approval` text, which it writes into the report;
   the invoking session must have the user's approval in its own conversation (the tool cannot see that, so it is
   a recorded attestation, not a check). Merged branches are not deleted.
7. **Red.** Without `--bisect` it stops and reports. With `--bisect` (§1.2) it finds the failing branch, ejects it,
   and re-runs the rest as a new train (still needing `--push` for any push).

`plan` writes nothing outside `~/.agentprov/merge-train/` and is the dry-run mode: it shows the merge order, the
conflicts, which conflicts are generated-file conflicts the tool would resolve, and the admission warnings.

**README source tables** (added 2026-10-14 for the README refresh's `tools/gen_readme_sources.py`). README.md is
hand-written except for one generated block between marker lines. A conflict there is resolved by merging the
hand-written parts normally, with the block blanked on all three sides; a conflict in those parts is a real
conflict. The generator then fills the block. Separately, the cheap generators (`gen_docs`, `gen_registry`,
`gen_readme_sources`, in that order) run after every merge, and any change is folded into that local merge commit.
So a block that merged cleanly but stale is fixed before the gate, and every bisect prefix is consistent.
`regen_pins` has a `readme-sources` family (skipped while the tool is not in the tree).

### 1.2 Bisect on red

The integration branch is already a chain of prefixes: merge commit `k` is `main + B1..Bk`. The train searches the
smallest `k` whose prefix is red, by binary search over the first-parent merge commits (`ceil(log2 N)` further suites;
for 6 branches, at most 3). Each probe is a full suite through the queue on that exact commit.

- **Culprit found** (`prefix k-1` green, `prefix k` red): `Bk` is ejected, its session is told through its status
  file (§6, `blocked`, with the failing test ids), and the train restarts from the green prefix with `B(k+1)..BN`
  merged on top. The known-green prefix is not re-tested; the new head is.
- **Interaction.** If `Bk` alone was green (its status file) but `prefix k` is red, the report says "Bk fails with
  B1..B(k-1)", not "Bk is broken".
- **No culprit** (every prefix green on re-test, but the full head was red): the report says "not reproducible",
  lists the failing test ids from both runs, and stops. The train never pushes a head that has not passed.

Optional heuristic (`--bisect=guided`): test first the prefix ending at the branch whose changed files intersect most
with the failing tests' files. It only reorders probes; the result is the same.

### 1.3 Cost compared with today

For N green branches: today `N` pushes and up to `N(N+1)/2` suite runs in the worst case (each later branch re-merges
and re-tests after every push). The train: one suite when green, `1 + ceil(log2 N)` (+1 for the restarted remainder)
when one branch is red.

### 1.4 GitHub merge queue: compared, not recommended

What follows is from GitHub's documentation as I know it. I could not re-check it in this session (no network), so
the user should confirm these points before deciding.

| | GitHub merge queue | `tools/merge_train.py` |
|---|---|---|
| Availability for `nickjones39/AgentPROV` | Merge queue needs an **organisation-owned** repository; for private repositories also **GitHub Enterprise Cloud**. A private repository owned by a personal account has no merge queue | available |
| Workflow | needs pull requests, required status checks, `merge_group` triggers | works on local branches; no PRs needed |
| Runners | GitHub-hosted. macOS minutes on private repositories bill at a 10× multiplier (Free plan 2,000 min/month, Pro 3,000). The full suite at 23–45 min per run would use about 230–450 billed minutes per macOS run, before bisecting | the local M2 Max, the machine every session already uses; the same `~/.agentprov` state and caches |
| Bisect | removes a failing PR and re-runs the rest; builds groups speculatively in parallel (more CI minutes) | sequential prefix bisect through one local queue |
| Gate parity | CI runs `-m "not network and not backend_* and not full_corpus"`, a narrower set than the local full suite; manual-dispatch jobs are not in it | runs the same gate command sessions run today |
| Project rules | CI is manual-run by the user's decision (2026-10-11, AGENTS.md §8, D-22); a queue would make it a required gate on every merge | no change to CI |

**Recommendation (D-420):** the local merge train. GitHub's merge queue is unavailable for this repository on its
current plan as far as I know. Even if it were available, it would turn the user's manual-CI decision into a paid,
required macOS gate. CI on push to `main` still runs as it does now; a train makes one push per batch instead of N, so
it also cuts the CI minutes that push-triggered runs use.

---

## 2. Conflict-free shared docs — D-421, D-422, D-426

### 2.1 Option A (`merge=union`) corrupts entries: shown, so rejected for these files

Git's union driver resolves a conflict by keeping both sides' lines, but it first removes the lines both sides have
in common at the edges of the conflict. I ran four merges in a scratch repository (git 2.54.0; the script is
Appendix A and becomes a test, §2.6). Each merge completed with no conflict reported:

| Case | Result after `merge=union` |
|---|---|
| Two branches each append a decision; the entries share their last lines (`` `  Status: proposed.` ``) | the shared trailing lines are kept **once**, under the second entry: the first entry **silently loses** its status and closing lines |
| One branch changes the last entry's status (`proposed` → `user-approved`); another appends a new entry after it | **both** versions of the status line are kept: the stale `proposed` line comes back next to `user-approved` |
| regen-batch table: one branch sets row 28 to `implemented` and adds row 29; another adds a different row 29 | row 28 appears **twice** (stale and new status), and **two rows 29** merge silently |
| Two branches append entries whose separating blank line is common | the blank line is kept once; the entries run together (cosmetic) |

Entries in DECISIONS.md, regen-batch.md and D_adapters.md are edited after they are written (status, addenda,
"user-approved"), and their last lines are often identical (`proposed.`, `user-approved 2026-10-13.`). So union merges
would corrupt them silently, and they would also hide number collisions instead of showing them. **Option A is
rejected for every shared doc.** Union is safe only for a file whose lines are self-contained, unique and never
edited. In this design that is just the id-ledger mirror (§3.1); a test checks that its lines are unique.

### 2.2 Option B: one file per entry with generated, committed indexes (recommended, D-421)

One generator, `tools/gen_docs.py`, with targets `decisions`, `regen-batch`, `agents` and (if chosen) `registry`:

```
uv run python tools/gen_docs.py --check            # test + merge train: exit 1 with a diff if a generated file is stale
uv run python tools/gen_docs.py --write [TARGET]   # regenerate
uv run python tools/gen_docs.py adopt TARGET       # move a branch's direct edits of a generated file into fragments
```

Common rules for every target:
- **Fragments are verbatim.** A fragment file holds the entry's exact Markdown lines (with their trailing blank
  lines), with no front matter, so the generated file is a plain concatenation.
- **Order with no shared order file to append to.** At migration, a frozen list `_legacy-order.txt` records today's
  order of the existing entries; it is written once and never appended. New entries follow the legacy ones, sorted
  by number (or label). No later branch edits a common file to add an entry.
- **Byte-identical migration.** The migration commit adds the fragments and leaves the generated file's bytes
  unchanged, and `--check` proves it. So `git log`, `git blame` and `git log -S'D-321'` on DECISIONS.md keep
  working across the migration. From then on, every change to an entry shows in both the fragment and the
  regenerated file, in the same commit.
- **The generated files are committed.** The repository stays readable as today: "Read AGENTS.md" and "see D-321 in
  DECISIONS.md" both still work. A test (`tests/repo/test_generated_docs.py`) runs `--check`. A one-line banner
  ("generated from `<dir>`; edit the fragment") is added in a separate, later commit, so the identity commit stays
  provable.
- **Conflicts in a generated file are resolved by regenerating it**, never by hand. Two branches that each add an
  entry change different fragment files (no conflict) and the same generated file (a conflict, or a clean but
  incomplete text merge). `gen_docs.py --write` fixes both cases, and `--check` catches a missed one. The merge train
  does this automatically (§1.1 step 4). An optional custom merge driver (`merge=agentprov-generated`, installed into
  the repository's git config by `gen_docs.py install-driver`, only with the user's yes, because it is persistent
  configuration) would avoid the conflict markers. Without it, git falls back to its normal text merge, which is safe
  because `--check` catches the result either way.
- **`adopt`** helps branches that were started before the migration: it reads the branch's diff of the generated file
  against its merge-base, writes each added or changed entry to its fragment, and regenerates. A stale branch never
  has to re-type an entry.

### 2.3 The targets

**DECISIONS.md** → `docs/architecture/decisions/`:
- `_preamble.md`: lines 1–383 (D0–D12, Addenda A–C, the Addendum D heading).
- One file per entry: `D-1.md` … `D-360.md` (226 entries today), named `D-<n>[-<suffix>].md` for top-level addenda
  such as phase 10m's `D-281 addendum` (`D-281-addendum.md`). Reserved stubs (`D-189`, `D-349`) are entries too.
  Nested addenda (inside D-28 and D-155) stay inside their entry.
- After line 383, every line belongs to an entry (each is a `- **D-…` line, an indented continuation or a blank
  line), so the split is complete. The generator refuses a fragment whose first line does not define the number in
  its file name.

**regen-batch.md** → `docs/reports/analysis/regen-batch/`:
- `_preamble.md` (the prose and the table header), `rows/<label>.md` (one table row each; labels `1`…`30`, `U6-a`,
  `R-10k-1`, and stable labels for today's `—` rows), `_notes.md` (the text between the table and the sections),
  `sections/<label>.md` (the `## Item N` sections) and `bundles/<slug>.md` (the bundle entries such as `ingest-formats`).
- Today's anomalies are kept exactly as they are (byte identity) and reported by `reserve_id.py scan`: items 18–20
  have sections but no table row, and sections run out of order (…, 28, 26–27).

**AGENTS.md** → `docs/agents/`: AGENTS.md entries are **replaced**, not appended, which is why union cannot be used
here. One file per §0 session entry (`docs/agents/sessions/<slug>.md`, today's ~35 top-level bullets) and per §13
History entry. The rest stays as hand-edited parts (`_head.md`, `_middle.md`, `_tail.md`) that the generator joins
around the two generated lists. A session then rewrites only its own entry file, so two sessions updating their
status lines never touch the same file. The fragment layout and the AGENTS.md rule change land only in the drained
slot.

**`adapters/registry/__init__.py`** → one module per source (D-426; **needs the user's yes**, the only `src/`
change in this design):
- `registry/sources/<source_id>.py` holds one `SourceRegistration` and its caveat constant (38 sources; the 19
  phase-10d factory calls become one file each).
- `registry/families/<family>.py` holds that family's `READERS`/`MAPPERS` lines. Today every new family adds sorted
  lines to the shared dicts, which is the last hotspot.
- `registry/_generated.py` is a **static, committed** list of explicit imports, in today's order, and builds
  `REGISTRY`, `READERS` and `MAPPERS`. Nothing is discovered at runtime and nothing is loaded by name (no plugin
  loading, per the CLAUDE.md security rule). A test checks the list is current.
- The dataclasses, `BACKENDS`, `EXTERNAL_OWNERS`, `_phase10d` and `get_source` stay in `__init__.py`. Its public
  names are unchanged, so none of the ~57 importers change.
- **Downstream effects:**
  - **Corpus digests:** none. Nothing hashes the registry: `code_sha256` covers `adapters/<family>`, and no test pins a
    registry digest (survey of origin/main). This is re-verified in the build; if any digest does move, the split
    stops and goes to regen-batch.md first.
  - **Output:** `agentprov info` output is unchanged, because the order is preserved. A migration test compares
    `REGISTRY` field by field with a snapshot taken before the split.
  - **Tests:** the allow-lists of the five "new family touches only the family" tests move from the one path to
    `registry/sources/*`, `registry/families/<family>.py` and the generated list.
  - **Spec text:** D_adapters.md says "one entry in `registry/__init__.py`" (lines 3407, 4863, 6192), and AGENTS.md
    line 475 lists `adapters/registry/` as a shared file.
- **Fallback if the user says no:** keep the module, and add the `gen_docs.py`-style rule that each new source is
  appended as one block with a unique marker comment, which keeps conflicts small but does not remove them.

**As built (`tools/gen_docs.py`, 2026-10-14; the tool only, no doc split yet).**
- CLI: `--check`, `--write`, `--split TARGET` and `--adopt TARGET`. A target without a fragment directory is "not
  migrated" and passes `--check`, so the tool can land before the drained slot.
- File names are taken from the stable part of an entry: `D-321.md`; `item-20.md`, whatever the heading's status;
  a session's title up to its first parenthesis, at most six words.
- A plain note bullet between decisions (`- D-388–D-389 are reserved.` on `ingest-formats-3`) becomes `D-388-note.md`.
- Splitting copies of today's three files from main and from ten in-flight branches is byte-identical on every branch
  except `deferrals-c` (§8 item 11).

**As built (`tools/gen_registry.py`, 2026-10-14; the tool only, `src/` untouched until the drained slot).**
- Layout: `_model.py` (dataclasses, literals, `_phase10d`, caveats shared by several sources), `sources/<id>.py` (38
  today, each with its own caveat), `families/<family>.py` (8 today; dict literals read with `ast.literal_eval`,
  never imported), the frozen `_legacy_order.py`, and the generated `_sources.py` and `_factories.py`.
  `__init__.py` keeps every public name.
- `--split` checks in subprocesses that every public name has the same `repr` before and after, and writes nothing
  otherwise. The one visible change is the dataclasses' `__module__` (`agentprov.adapters.registry._model`), which
  is still importable in spawned workers.
- On a copy of today's registry the split passes that check, ruff and mypy (53 files).
- Before the drained slot: the five "new family touches only its family" allow-lists and the D_adapters.md registry
  sentences (§2.3) must be updated in the same commit series.

### 2.4 Spec items: stable labels instead of positional numbers (part of D-422)

D_adapters.md is the specification; it is not split into fragments. Its 274 citations of the form "D.x.y item N"
(93 files: docs 134, `src/` 81, tests 43) must keep resolving, so:
1. **Today's numbers become the labels, frozen.** "D.2.9 item 13" means that item forever. Items are never renumbered:
   a withdrawn item stays as `N. (withdrawn: …)`, and a new item is never inserted in the middle.
2. **New item numbers come from the ledger** (`reserve_id.py reserve spec-item --list D.2.9`). Had it existed,
   ingest-formats-3 and d323-stream would have received 14 and 15 instead of both writing `14.` (a live collision
   today, §8).
3. **Anchors.** Each item gets an HTML anchor at the start of its title (`14. <a id="d.2.9-14"></a>**Title.**`), so
   a citation can link to it, and so the label survives a renderer that renumbers lists. CommonMark renders a list
   from its first number onwards, so a gap would show a wrong number; rule 1 therefore allows no gaps (an unused
   reservation becomes a withdrawn item).
4. **Mapping and check.** `gen_docs.py` writes `docs/architecture/item-labels.json` (label → section, list, title,
   anchor). A test resolves every "D.x.y item N" citation in the repository against it. Two sections hold two lists
   each (D.6.6 and D.9.5 "Deviations"). Their second lists get the qualifier `b` (`D.9.5b item 2`), and the test
   reports today's ambiguous citations of them for a one-time manual fix.

**As built (`tools/spec_labels.py`, 2026-10-14; the checker only, D_adapters.md untouched).**
- `--check` resolves every "D.x.y item N", "§D.x.y items a–b" and "D.x.y(N)" citation in the tracked text files. A
  bold label such as `**D.6.6.1 …**` opens a list like a heading does (the shared parser of `reserve_id.py`).
- `--write` produces `item-labels.json`.
- On main, 328 of 330 citations resolve. The two that do not are in `tests/unit/artefacts/test_catalogue.py`, whose
  docstring cites "D.15.7 items 1 and 2", but D.15.7 is a bullet list (§8 item 12).
- It joins the merge gate once those two are fixed in the drained slot. The HTML anchors of rule 3 are the only
  D_adapters.md edit left for that slot.

### 2.5 Migration plan (in the drained slot, one commit series)

Each commit passes the targeted tests. The last one passes the full suite on its exact commit before the push.
1. `tools/gen_docs.py`, `tools/reserve_id.py` and their tests (new files; may land earlier).
2. DECISIONS.md fragments, plus `_legacy-order.txt`. DECISIONS.md bytes unchanged, `--check` green.
3. regen-batch fragments. Bytes unchanged.
4. AGENTS.md fragments (§0 sessions, §13 history). Bytes unchanged.
5. Spec anchors, `item-labels.json` and the citation test (D_adapters.md changes: anchors only, no text).
6. Registry split, **only with the user's yes**: the before/after `REGISTRY` snapshot test and the allow-list updates.
7. Banners on the generated files; the AGENTS.md rules of §7; the CLAUDE.md shared-files line and the D_adapters.md
   registry sentences updated; the `.gitattributes` union rule for the ledger mirror.
8. `reserve_id.py seed` from the migrated tree; the mirror committed.

**History and citations preserved:** no file is deleted or renamed. Each generated file keeps its path and its full
git history, and fragments are new files. Every "D-321", "regen-batch item 16", "D.2.9 item 13" and AGENTS.md section
reference still resolves in the generated files, and the fragment files add a second, per-entry place to find them.

**Step 4 decisions (user, via the orchestrator, 2026-10-21).**
- **4a (built):** a split doc's merge-train resolver now runs `gen_docs.py --adopt` before `--write` when the merged
  branch's own commit lacks the fragment directory (it started before the split). Before this, `--write` regenerated
  from the fragments alone and silently dropped that branch's new entries. A conflicted generated file from such a
  branch is refused and goes back to its owner (merge main, keep both sides, `--adopt`, commit), because ours would
  lose the branch's entries and theirs main's. `spec_labels.py --check` joins ci_local's `generated` job.
- **4b:** the doc split (steps 2-4 and 7 above) runs right after the pre-round integration branch has merged the held
  branches, on the orchestrator's signal. The orchestrator adds the CLAUDE.md "shared docs are generated" line in the
  same push.
- **4c: D-426 not adopted** (user 2026-10-21): six held branches edit the registry, and after D-451 a split moves
  the aer digest. Step 6 is dropped; `tools/gen_registry.py` stays as an unused tool.
- The item anchors (step 5) and the merge driver stay dropped; the ledger is already seeded (step 8).

### 2.6 Tests

`tests/tools/` (new): the four union cases of §2.1 as a test that documents why union is not used. It runs in a
temporary git repository, and if a future git changes the behaviour, the test says so. Further tests cover
byte-identity round trips on copies of today's files, `adopt` on a synthetic pre-migration branch, the generated
registry list, and the citation resolver.

---

## 3. Id allocation (`tools/reserve_id.py`) — D-423

### 3.1 Where the ledger lives

**Decision proposed: the authority is machine-local, with a committed mirror.**

- **Authority:** `~/.agentprov/ids/ledger.jsonl`, appended under an exclusive `fcntl.flock` on
  `~/.agentprov/ids/ledger.lock`. All worktrees on the machine see it at once. A committed ledger cannot do this:
  two branches each read "next free is D-150" before either merges, and that is how D-150 was used twice.
- **Mirror:** `docs/workflow/id-ledger.jsonl` (committed). Each reservation is also appended to the mirror in the
  reserving session's worktree, and it reaches `main` with that branch. It is the audit trail and lets a second
  machine (the future Mac Studio) resume: `reserve_id.py sync` imports entries from the mirror on `origin/main` that
  the machine ledger lacks. The mirror is the one file in this design with `merge=union`, which is safe here (§2.2):
  every line is a self-contained JSON object carrying a unique `rid`, lines are never edited, and readers sort.

Rejected: committed ledger only (not atomic across unmerged branches); machine-only ledger (lost with the machine, no
audit trail in git); a lock on a remote (network, and GitHub has no lock primitive for this).

### 3.2 Interface

```
reserve_id.py reserve decision --count 10 --session workflow-tools --purpose "multi-agent workflow tooling"
   -> D-430–D-439
reserve_id.py reserve regen-item --session regen-items-2-12 --purpose "U6-d"      -> item 31
reserve_id.py reserve spec-item --list D.2.9 --session deferrals-c --purpose "..." -> D.2.9 item 15 (label D.2.9.i15)
reserve_id.py reserve routing --prefix R-10q --session phase-10q                  -> R-10q-1
reserve_id.py list [--kind K] [--session S]
reserve_id.py scan        # collisions and unreserved uses in the working tree (no write)
reserve_id.py seed        # one-time: builds the ledger from the existing files (§3.3)
reserve_id.py sync        # imports mirror entries from origin/main
```

A ledger line: `{"rid": "<uuid4>", "kind": "decision", "first": 430, "last": 439, "session": "...", "branch":
"...", "purpose": "...", "at": "2026-10-14T12:00:00Z", "host": "<hostname>"}`. Reservations are never released;
an unused number stays reserved and is reported as unused (as D-157–D-159 are today).

**Explicit claims and voids** (2026-10-14, after a D.6.20 collision):
- `reserve KIND --first N --count K` claims the exact numbers a branch already wrote. It is refused if another
  session holds any of them; pre-ledger `seed` records do not block.
- `void RID --reason …` withdraws a reservation by appending a void record to the ledger and the mirror. The
  ledger stays append-only, and the scan and next-number logic count only the reservations in force.
- The first void withdrew phase 10q's spurious D.6.20 items 12–22.
- ci_local's `ids` job (`reserve_id.py --scan-ref origin/main scan --strict --require-reserved`) fails the gate on
  a duplicate, or on a definition that is new against `origin/main` and has no reservation. It scans only the
  commit under test, so unrelated branches cannot turn it red.

### 3.3 Seeding and the collision scan

`seed` reads every defined number from the files: DECISIONS.md (or `decisions/*.md` after §2), regen-batch rows and
item sections, the numbered lists in D_adapters.md, and the announced ranges in AGENTS.md ("Decisions D-NNN–D-MMM").
It records each as `kind`, number, `source: "seed"`, and the session named in the range sentence when there is one.
The next number of a kind is `max(ledger, every number seen in the tree) + 1`, so a number used but never reserved
can never be handed out again.

`scan` (also run by the merge train and by a test, non-blocking at first) reports:
- **collisions:** a number defined twice (two `D-150` entries; two regen-batch item 29 rows; two `14.` in one list);
- **unreserved uses:** a defined number not in the ledger (warning);
- **foreign uses:** a number defined on branch X that the ledger gives to another session.

As built (step 1): the scanned refs are `origin/main` and every local branch except `review/*` and `review-base/*`,
read with `git cat-file`, plus the working tree (`--scan-ref` replaces the list). A duplicate that a branch inherited
from its merge-base with `main` is reported once, on `main` (`--all` shows every copy). A collision is a number
absent from `main` that two refs define with different content. Stacked branches that carry the same entry do not
count. Spec-list `jump`s (for example the stray `220.` at D_adapters.md:2620) are reported too. On the real refs, the
first scan (2026-10-14, read-only) found exactly the D.2.9 item 14 collision and that jump.

---

## 4. One pin regenerator (`tools/regen_pins.py`) — D-424, D-425

### 4.1 What exists today (survey of origin/main `c4fd0dc2`)

Almost every pin is regenerated by an environment variable that a test reads, not by a script. `.gitattributes`
marks `tests/golden/**` and `tests/fixtures/**` as binary, so two branches touching one of these pin files always
conflict as a whole file, and the only correct resolution is to regenerate.

| Family | Pin file(s) | Regenerator today |
|---|---|---|
| `history` | `agentdojo-upstream.profile.toml:167` (history table sha) | `tools/agentdojo/history_table.py` (has `--check`) |
| `agentdojo-aer` | 8 × `tests/adapters/agentdojo/*_aer_digests.json` | `AGENTPROV_REGEN_AGENTDOJO_AER`, `_AGENTDYN_AER`, `_DRIFT_AER` with the family's tests |
| `other-aer` | credleak, dtap (AER + SEM/PROV), foobench `trace-001.aer.jsonl`, `tests/fixtures/inspect/expected/*.aer.jsonl` | `AGENTPROV_REGEN_{CREDLEAK,DTAP,INSPECT}_GOLDEN=1`, `AGENTPROV_REGENERATE_GOLDEN=1` |
| `c161` | `examples/C/agentdojo_2024_pi_detector.aer.jsonl`, the C.16.1 block and digest row of `C_data_model.md` | `tools/agentdojo/regen_c161.py --write` |
| `c16-copies` | C.16.2–C.16.4 blocks and rows, the C.14.5 SEM example, `test_seal.py:59`, `test_mapping.py:50,61`, `test_history_fields.py:262`, `aer_digests.json["C.16.1"]` | **by hand**; no test compares the spec blocks with the vector files |
| `golden` | `tests/golden/prov_digests.json` (19), `tests/golden/gate_d_digests.json` (28; also read by `migration/gate_d.py` and `tests/migration/test_gate_d.py`) | `AGENTPROV_REGEN_PROV_DIGESTS=1`, `AGENTPROV_REGEN_GATE_D_DIGESTS=1` |
| `generated-tables` | `gen_vocab_py.py`, `gen_semdiff_tables.py`, `sync_ns.py`, `gen_foobench_fixture.py`, `agentdojo/gen_suite_tools.py`, `agentdojo/autodojo_cache_table.py` | each tool's own `--check` / `--write` |

Not in scope, by design: the format-freeze pins (`test_format_freeze.py`, changed only with a format version bump),
the compat oracle `PORT_MANIFEST.json` (needs the baseline repo at `579a908`; frozen by invariant 8), and data pins
for upstream bytes (fixture and zip digests, the split-download part pins of D-249 in profile tomls). These pin
*inputs*, not outputs; a tool that rewrote them would hide an input change. The brief's "registry part pins" are these
D-249 part pins: `adapters/registry/` holds no digest, and no test pins a registry or code digest (code digests are
computed into each corpus's `derivation.json`).

### 4.2 Design

`tools/regen_pins.py` is an **orchestrator over the existing regenerators**, not a re-implementation. It holds a
static table of families: name, pin paths, the write command, the check command, the input paths that move it, and
its dependencies. It runs them in dependency order: `history` → `agentdojo-aer`, `other-aer` → `c161` →
`c16-copies` → `golden` → `generated-tables`.

```
uv run python tools/regen_pins.py --check                 # CI and merge train: exit 1 and a diff if any pin is stale
uv run python tools/regen_pins.py --write [--family F...] # rewrite pins in this worktree
uv run python tools/regen_pins.py --affected [--base origin/main]   # families whose inputs changed
```

- **`--check` is read-only.** It creates a detached scratch worktree of `HEAD` under `~/.agentprov/regen-pins/`, runs
  every write command there, and diffs the pin files against `HEAD`. It requires a clean tree (otherwise it checks
  the working tree and says so). A pin that hand-merging made inconsistent fails here, even when each test passes on
  its own.
- **Determinism.** Each family runs twice in check mode (`--twice`, on by default in CI); a second run that differs
  from the first is an error (invariant 4).
- **No network**, and no corpus. Every input is a tracked fixture (the survey confirmed this for all families above).
- **`c16-copies`** is new code in the tool: each copy is declared as (source of truth, extractor) → (target file,
  anchored pattern). For example, the C.16.1 `records_sha256` in `test_seal.py:59` is computed from the vector file,
  and each spec block must equal its vector file byte for byte. C.16.2–C.16.4 vector *files* stay hand-maintained:
  the only generator is the prototype with stand-in profiles, and choosing a real generator is a semantics question
  for the spec owner, not for this tool. The tool checks their copies and digest rows and rewrites the copies, never
  the vectors.

### 4.3 Coordination with D-31 and deferrals part C

Both branches re-pin heavily, and they overlap with each other on both golden JSONs, seven agentdojo digest files,
the Inspect expected AERs, `C_data_model.md`, `test_seal.py`, `aer_support.py`, `test_mapping.py` and
`test_history_fields.py`. So:
1. `regen_pins.py` lands as a new file with `--check` for every family, plus `--write` for every family except
   `c16-copies`. It edits no pin file in this branch.
2. Before the first real `--write` on `main`, the D-31 and part-C sessions each run `--check` on their own heads
   (through the orchestrator). Any difference is a finding for that session, not a change by this one.
3. `c16-copies --write` is enabled only after both have merged, because it rewrites lines both of them edit by hand
   today.

**As built (step 3, 2026-10-14).**
- `c16-copies` is check-only. Run read-only on `main`, `claude/d31-bumps` and `deferrals-c`, it found the C.16.4
  defect of §8 item 10 on all three.
- On `deferrals-c`, the C.16.1/C.16.2 test copies point at the new `docs/architecture/examples/C/aer-0.2/` vectors, so
  the copies table must follow the vector set the tests reference once part C lands. That is part of enabling
  `--write`.
- `history` needs `~/.agentprov/cache` and is skipped without it. `gen_suite_tools.py` needs git object stores and
  `autodojo_cache_table.py` the cache, so they are not families: they stay manual.
- A real family (`dtap`) regenerated to identical pins with `--write` in this worktree in 23 s.
- The suite's write guard (D-402, `tests/conftest.py`) refuses the pin tests' writes. Every regenerator run, in
  `--write` and in the scratch runs of `--check`, therefore sets `AGENTPROV_TEST_WRITE_GUARD=off`; ordinary test runs
  keep the guard. Verified with `dtap` under the new conftest.

### 4.4 Pin conflicts in the merge train (D-425)

When the train merges a branch and a pin file conflicts, it takes `main`'s side, runs `--write` for the affected
families, and then checks **attribution**: every pin key whose value differs from `main` must be one that at least
one merged branch also changed (between its merge-base and its head). An unattributed change, for example a new
fixture's digest moved by another branch's mapper change, stops the train and is reported to the user with the keys.
It is not accepted automatically, because it is a digest change no session predicted (AGENTS.md: byte-moving changes
are recorded in regen-batch.md first).

Proposed rule for AGENTS.md (§7): *pin conflicts are resolved by re-running `tools/regen_pins.py`, never by
hand-merging digests.*

---

## 5. Heavy-job classes: an interface proposal for `tools/suite_queue.py` — D-427

`tools/suite_queue.py` belongs to the suite-perf session (D-403, built now on `suite-perf`). The orchestrator asked
for this part as an interface proposal, which it routes to suite-perf; this session writes none of that file.

**Agreement (2026-10-14, relayed by the orchestrator).** suite-perf reviewed §5 and accepted it with the four changes
in §5.3. This session implements it against suite-perf's landed `tools/suite_queue.py`, after suite-perf's phase 2
is on `main`. suite-perf's 13 tests in `tests/unit/test_tools_suite_queue.py` must pass unchanged, and suite-perf
reviews the diff. Where §5.2 and §5.3 differ, §5.3 wins.

### 5.1 Compatibility

The current command line, queue directory (`~/.agentprov/locks/suite-queue`), ticket format, `history.jsonl`, exit
codes (75, 124, 128+n), signal forwarding and `--targeted` (D-404) stay exactly as they are. The `suite` class is the
default class, so every existing invocation behaves the same, and suite-perf's tests pass unchanged.

### 5.2 Proposed additions

The extension point is suite-perf's proposed `--class` (relayed by the orchestrator 2026-10-14). The classes are
the brief's lanes.

```
suite_queue.py [--class suite|import|rehearsal] [--cpu N] [--mem-gib G] [--label L] ... -- <command>
suite_queue.py --status              # all classes, the running jobs, their declared costs and the budgets
```

- **Classes.** `suite` (full suites; 1 slot), `import` (imports and trial imports into scratch corpora; 2 slots),
  `rehearsal` (rehearsals, `recompute`, `derive`, `verify` in scratch; 2 slots). Each class is FIFO with its own
  tickets, the same ticket scheme as today (`<time_ns>-<pid>.json`, plus the new fields `class`, `cpu`, `mem_gib`).
- **Lock layout.** The `suite` class keeps today's directory and files unchanged. The new classes are siblings under
  `locks/`, with one lock file per slot:

  ```
  ~/.agentprov/locks/
    suite-queue/                 # unchanged: tickets/, suite.lock, holder.json, history.jsonl
    jobs-import/                 # tickets/, slot-0.lock, slot-1.lock, holder-<slot>.json, history.jsonl
    jobs-rehearsal/              # the same
    jobs-admit.lock              # held only while one admission decision is made (milliseconds)
    jobs-running/<class>-<ticket>.json   # cost and pid of every running job, all classes, for the budget
  ```

  A class head takes the first free `slot-<i>.lock` with a non-blocking `flock`, as the suite class takes
  `suite.lock` today. `$AGENTPROV_SUITE_QUEUE_DIR` keeps its meaning (the suite class directory). The other classes
  live next to it (`<parent of the suite queue dir>/jobs-*`), so a test's temporary queue root isolates them all.
- **Machine budget.** A job declares `--cpu` and `--mem-gib`. Defaults per class: suite 8 CPU / 12 GiB (xdist
  `-n auto`), import `workers` CPU / `4 × workers` GiB (the 4 GiB per-job cap of D-55), rehearsal the same. The
  budget is `cpu = ncpu − 2` (10 on this 12-core machine) and `mem = 75 %` of physical memory (24 GiB of 32), both
  overridable by `AGENTPROV_JOB_CPU_BUDGET` and `AGENTPROV_JOB_MEM_GIB_BUDGET`. A job larger than the whole budget is
  clamped to it and runs alone.
- **Admission.** A class head starts when (a) its class has a free slot, (b) its cost fits the remaining budget,
  and (c) no older class head is waiting for budget. Rule (c) is global FIFO among class heads: a small import cannot
  starve a queued suite. Admission is decided under a short `flock` on `jobs-admit.lock`, so two heads never
  admit against the same free budget. Running jobs are recorded in `jobs-running/` with
  their costs and pid. The `suite` class goes through the same admission and writes the same record, so suites
  count against the budget. This is the one behavioural change for the suite class: a queued suite may also wait for
  running imports to release budget. `--targeted` stays outside the queue and the budget (D-404).
- **Load guard (soft).** If the 1-minute load average is above `1.5 × ncpu` (load from work outside the queue), a
  head waits up to `--load-wait` (default 10 min), then starts anyway and logs it. This covers interactive work that
  does not go through the queue.
- **Stale recovery.** It is the same as today for tickets: dead pid, or pid reuse checked with `ps`. A `jobs-running/`
  record whose pid is dead is removed by the next admission, so its budget comes back. The slot locks are
  `flock`s, which the kernel releases when a holder dies.
- **`agentprov` through the queue.** No change to the CLI. Sessions run, for example,
  `uv run python tools/suite_queue.py --class import --cpu 3 --mem-gib 12 -- uv run agentprov import ... --corpus
  ~/.agentprov/migration-work/<session>/...`. The rule is proposed for AGENTS.md (§7).
- **Status integration.** Each start and end updates the session's status file (§6) through the writer in
  `tools/session_status.py`, if present (a soft import; no hard dependency between the two tools).


### 5.3 Changes agreed with suite-perf (supersede §5.2 where they differ)

1. **Load guard.** The 1-minute load average includes the queue's own running jobs (one `-n 8` suite alone pushes
   it to about 10–20), so a plain `1.5 × ncpu` threshold would block behind admitted work. The guard compares
   `loadavg − Σ declared CPU of running queued jobs` with about `0.5 × ncpu`. That is load from outside the queue
   only.
2. **Environment scope.** D-406 (bytecode prefix cache) and D-407 (checked-hash precompile) apply to test runs only.
   The `import` and `rehearsal` classes default to `--keep-bytecode-env --no-precompile`, so a corpus-producing
   `agentprov import` or `derive` runs with the session's environment unchanged. Only `suite` and `--targeted` keep
   today's behaviour.
3. **Stale records.** A `jobs-running/` record holds the **wrapper's** pid (the `suite_queue.py` process that holds
   the slot `flock`), not the child's. It gets the same pid-reuse check as tickets (the `ps` command contains
   `suite_queue.py`), so the budget comes back exactly when the slot lock is released.
4. **Declared cost is a reservation, not a measurement.** An xdist suite at `-n 8` also starts worker pools
   (serial-group pools of up to 8, default `--jobs` pools of up to 6 per test), so its real peak is above 8 CPU. The
   default suite cost equals its `-n` value. The defaults are set from data once suite-perf reports the measured
   peak CPU and RSS (`docs/reports/suite-perf/results.md`).

**As built (2026-10-14, against suite-perf's landed `tools/suite_queue.py`; for suite-perf's review).**
- **Layout change from §5.2:** the new state lives *inside* the suite queue directory rather than beside it:
  `<queue-dir>/jobs/{import,rehearsal}/` (`tickets/`, `slot-<i>.lock`, `holder-<i>.json`, `history.jsonl`) and
  `<queue-dir>/jobs/{admit.lock,running/,waiting/}`. The reason is that with `--queue-dir tmp_path`, sibling
  directories would land in pytest's shared parent directory, and parallel tests would share one budget. The suite
  class's own files are unchanged.
- `waiting/` records the heads that hold a slot but are not yet admitted. That is what makes the global FIFO among
  class heads exact.
- History lines gain `admitted_at`, `cpu` and `mem_gib`. This is the data for setting the default reservations.
- `acquire()` keeps its signature. The new keywords (`extra_lock_fds`, `holders`, `admit`, `slot`) default to
  today's behaviour.
- The holder-ticket fix (orchestrator, 2026-10-14) is included. `--status` shows the running holder's own ticket as
  `running.` and numbers the waiters after it, and the waiting display's position no longer counts it.
  `tools/queue_status.py` already left it out; a test now pins that.
- Tests: suite-perf's 17 pass unchanged, plus 8 new ones in `tests/unit/test_tools_suite_queue_classes.py`.
- **suite-perf's review (2026-10-14), applied:**
  1. A live suite holder with no reservation (an old-version wrapper during the rollout) counts with the default
     suite reservation.
  2. Only heads blocked by the budget, or waiting behind one, hold younger heads back. Waiting records carry
     `blocked: budget|fifo|load`, and a head held only by the load guard never stalls a queued suite.
  3. `-n 0` reserves `max(1, n)`.
  4. An import or rehearsal with `--jobs 0` or no `--jobs` reserves the CLI's host default,
     min(CPUs, ⌊0.75 · RAM / 4 GiB⌋).
  5. The default suite reservation is `-n` + 2, for the worker pools, until suite-perf sets it from measured data.
- **Mixed-version deadlock** (2026-10-21, reported by regen-items-2-12). A suite waiter running a pre-7b7c5189 copy
  of the tool (from a held worktree) waited, under the old global FIFO, behind an older import head. The import ran
  the new tool and held the headroom for that suite, so neither ran for about 3 h at 0 of 10 CPUs. Now an import or
  rehearsal holds no headroom while a suite head's waiting record says `blocked: fifo`: a current suite never
  writes that because of an import. That suite runs after the import, as under the old rule. A waiter keeps the
  code it started with, so the deadlock seen that day was broken by restarting the suite waiter with main's tool.
  At the orchestrator's request there is also a second guard: a wait that traces back to the headroom is written
  as `blocked: load`, with the real reason in `held` and `via_headroom`. `load` is the one tag every older version
  lets a suite pass, so an old suite waiter runs first, as intended; FIFO among imports reads `held`. A test runs
  the real pre-headroom code (`git show 7b7c5189~1:tools/suite_queue.py`) against the new records. `--status`
  prints `DEADLOCK?` when nothing runs, 0 CPUs are reserved and every head has waited longer than
  `--deadlock-minutes` (15).
- **Import starvation** (2026-10-21, orchestrator request). With held-branch suites queued back to back, one import
  head too big for the headroom (`--cpu 4`) never fitted and held the FIFO import lane, 12 imports, for 4 h.
  - **Two options:** pause new suites once an import or rehearsal head has waited long enough, or let smaller imports
    backfill behind it.
  - **Chosen: the pause.** It is the only one of the two that guarantees the big head ever starts, and FIFO among
    imports stays.
  - **The rule:** an import or rehearsal head that has waited `--starve-minutes` (60) on the headroom or the budget
    ignores the headroom. No new suite starts until that head has; the running suite is never pre-empted.
  - **No new waits:** the paused suite's record is `blocked: load` with `held: starve`, so no waiter (an older
    version included) defers to it.
  - **After it starts:** suites resume and wait only for the budget, and a younger import queues behind the suite
    again.
  - `--status` prints `starvation: suites paused for <label>`.
  - **Mixed versions again** (same day, r107-coverage). New suites paused for a starving import head that ran the
    pre-ae3eb427 waiter: it still honoured the headroom, so nothing ran. Now suites pause only for a head whose
    record has `starve_override` (written by ae3eb427+ waiters). An older head keeps the older rule, and the
    compatibility guard already lets suites pass it. The test runs the real `ae3eb427~1` code and fails without the
    fix.
  - **Rule for later changes:** a rule that makes one side wait for another must check that the other side's record
    shows it runs the matching code.
- **Section-heading numbers** (requested by the orchestrator, 2026-10-15, after `### D.6.21` was taken twice:
  phase 10j's on main and regen-items' held one; both had reserved only items). `tools/reserve_id.py scan` reads
  every numbered heading in `docs/architecture/*.md` (kind `spec-section`, outside fences; a lettered `D.10.4a` is
  its own number).
  - It reports two headings with one number on one ref as a `duplicate`, in one file or two.
  - A ref (the working tree included) that defines a number the base gained after their merge-base, with another
    title, is a `collision`. The full scan finds the D.6.21 case on `review-core-d-regen-cd13` and nothing else.
  - Both fail `--strict`, so the ci_local `ids` job fails on a held branch before and after it merges main.
  - Headings can be reserved (`reserve spec-section --list D.6` gives the next free D.6.n; `--first` claims one).
    `--require-reserved-sections` makes a new unlettered heading need a reservation. ci_local does not pass that
    flag yet: no heading has ever been reserved, so every held branch that adds one would fail. `seed` never records
    headings.
- **Suite headroom** (requested by the orchestrator, 2026-10-15). While any suite ticket is queued or running, an
  import or rehearsal head starts only if the CPUs reserved by running imports and rehearsals plus its own stay
  within the budget minus the suite's reservation. That reservation is the largest present suite's ticket `cpu`
  (suite tickets now record it), or for an older wrapper's ticket the default for its command; with 8 of 10 CPUs
  that leaves 2. With no suite ticket, admission is unchanged, and running jobs are never pre-empted. Waiting
  records carry `blocked: headroom` and the reason text (`why`), and `--status` prints it. One refinement was
  needed: a suite never waits behind an older import or rehearsal head. Those heads yield to it, so if each waited
  for the other the queue would deadlock. A head that waits behind a headroom-blocked one would complete such a
  cycle too. FIFO among imports and rehearsals is unchanged. Tests: `tests/unit/workflow/test_suite_headroom.py`.
- **Priority** (requested by suite-perf after a gate-integrity jump, 2026-10-14): `--before-head --reason TEXT` names
  the ticket midway between the last earlier priority job (or the running holder) and the class's first ordinary
  waiter. Priority jobs therefore run first-come among themselves, after the holder and before that waiter. They take
  the same place in the budget FIFO. The reason goes into the ticket, `--status` and `history.jsonl`.
  Renaming a waiting ticket by hand deadlocks, because the waiter rewrites its own ticket.
- **Two fixes from suite-perf's code review (2026-10-14, relayed by the user):**
  1. *pgid reuse.* `orphan()` trusted a recorded `child_pgid`. Process-group ids are recycled pids, so an unrelated
     later group could have been waited for and, after the dead holder's run timeout, killed. `holder.json` now also
     records the leader's `ps` start time and command line at spawn. A group is treated as the orphan only while its
     leader still matches both. A mismatch, or an old record without them, counts as gone and is never waited for or
     signalled, and `_stop_pgid` checks again before sending anything.
  2. *Admission before the slot lock.* A head used to take its slot lock and then wait for the budget, so a
     `--before-head` ticket could not get past it. This happened when phase 10o held `suite.lock` waiting for an
     import. Now a head is admitted first (serialised by `admit.lock`) and only then takes the slot lock. A ticket
     that stops being a head withdraws its waiting record.
  suite-perf's orphan helper now records the leader identity, as a real holder does. Its other tests are unchanged.
  A follow-up from the review: a job admitted but still waiting for the slot lock, and then pushed back by a
  `--before-head` ticket, gives its reservation back and is admitted again when it is a head again. Otherwise the
  priority job's admission would wait for it while it waited for the head position, a deadlock.
---

### 5.4 Follow-up batch (2026-10-14; bug pass BF-1, BF-2, BF-6, BF-7 and orchestrator items)

- **BF-1.** `agentprov.worker` starts its own session, so stopping the suite's process group missed it, and it kept
  CPU that the budget counted as free. `run_child` records the process tree below the child every 2 s, and again
  right before a timeout or signal stop. Afterwards it stops every recorded process that still runs as the same
  process (pid and start time: SIGTERM, then SIGKILL after the grace period) and waits until they are gone, before
  the slot is released. One limit is documented: a process started in the last 2 s before the suite exits on its
  own can escape.
- **BF-2.** The size-triggered cache clear renames the tree aside (atomic) and removes it while tolerating a writer
  that still drops files into it. Leftovers go with the next clear, and a failed clear never stops the gate.
- **BF-6.** The generated-docs resolvers are per target, and each owns its file only once that target's fragment
  directory exists. Before the migration, an AGENTS.md or DECISIONS.md conflict stays a real conflict.
- **BF-7.** The pin resolver's files come from `regen_pins`' own family table. Partially generated files
  (`C_data_model.md`, `README.md`) and families that can be skipped are left out, and `item-labels.json` belongs to
  `spec_labels`.
- `--cpu N` alone scales the memory reservation (N × the class's GiB per CPU). The merge train's default suite gate
  is `-n 10`. A queued suite keeps an existing session status file current (waiting, running, result); no file is
  created, and `--no-session-status` turns it off.
- The hand-kept C.16.1 variant digest in `test_history_fields.py` is now a regenerated pin
  (`history_aer_digests.json`, family `agentdojo-aer`). A scan of the tests found no other hand-kept output digest
  outside `c16-copies` and the frozen spec constants.
- suite-perf's review of the batch: (a) a status update can never reach the gate, because any exception from it
  returns nothing and output is decoded with replacement; (b) the sweep spares detached `git gc` and `git
  maintenance`, which a test's git may leave behind.

### 5.5 Local CI and the GitHub CI switches (D-462, 2026-10-14)

`tools/ci_local.py` runs the `ci.yml` jobs on this machine. Its `core` job is the merge gate, the full suite through
the queue, and the merge train's default gate is `ci_local.py --skip secrets`. `ci.yml` regains push (main) and
pull-request triggers, with every job gated on `CI_ON_PUSH`; `CI_RUNNER` names a self-hosted runner, and the Windows
leg always stays GitHub-hosted. The details and rejected alternatives are in DECISIONS D-462. The first local run
found 4 historical gitleaks false positives (D-462: a `.gitleaksignore` proposal, not applied).

### 5.6 Follow-ups (2026-10-14)

- **Suite reservation from data:** ⌈0.8 × workers⌉ CPUs, which is 8 at `-n 10`. suite-perf measured the gate at an
  average of 6.5–7.0 CPUs, with short peaks above 10. Memory stays at 1.5 GiB per CPU, because the tree's total RSS
  was not measured.
- **`regen_pins` keeps the write guard on.** Regenerators run with `AGENTPROV_TEST_WRITE_ALLOW` naming only the
  family's declared pins (a glob pin allows its directory). An undeclared write fails instead of passing.

- **README corpora block** (2026-10-14): README.md now has a second generated block (`tools/gen_readme_corpora.py`).
  The merge train's README resolver blanks every generated block whose tool is present, merges the hand-written
  parts, and runs each generator. `regen_pins` has a `readme-corpora` family, and ci_local's `readme-sources` job
  checks both blocks.

## 6. Session status files — D-428

### 6.1 File and schema

`~/.agentprov/sessions/<name>.json`, where `<name>` is the session's branch name made safe for a file name. Schema
`agentprov-session-status/1` (a JSON Schema file committed under `docs/workflow/schemas/`):

```json
{
  "schema": "agentprov-session-status/1",
  "name": "workflow-tools",
  "title": "multi-agent workflow tooling",
  "worktree": "/…/.claude/worktrees/agentprov-workflow-tools-8a0461",
  "branch": "workflow-tools",
  "head": "<sha>",
  "base": {"ref": "origin/main", "sha": "<sha>", "ahead": 3, "behind": 0},
  "state": "building",
  "detail": "drafting design.md",
  "waits_on": {"kind": "user", "what": "approval of design D-420..D-429", "since": "2026-10-14T13:00:00Z"},
  "last_suite": {"commit": "<sha>", "result": "green", "passed": 6912, "failed": 0, "skipped": 107,
                 "started_at": "…", "ended_at": "…", "command": "pytest -n auto --dist loadgroup -p no:randomly"},
  "decisions": "D-420–D-429",
  "updated_at": "2026-10-14T13:05:00Z",
  "heartbeat_at": "2026-10-14T13:05:00Z"
}
```

States: `building`, `suite-running`, `green` (last suite green on the current head), `waiting-for-user`,
`waiting-for-slot`, `waiting-on-session`, `blocked`, `parked` (idle by design, e.g. "held by the user"), `done`.
`waits_on.kind` is one of `user`, `orchestrator`, `session`, `slot`, `job`, `none`.

### 6.2 Writer (session side)

```
uv run python tools/session_status.py set --state waiting-for-user --waits-on user "approval of D-420..D-429"
uv run python tools/session_status.py suite --result green --passed 6912 --failed 0 --skipped 107
uv run python tools/session_status.py touch          # heartbeat only
uv run python tools/session_status.py show
```

`branch`, `head`, `ahead`/`behind` and `worktree` are computed from git in the current directory, so a session never
types a sha. Writes are atomic (temporary file, `os.replace`), and the file is only ever written by its own session.
`suite` refuses to record `green` for a commit that is not the current `HEAD` with a clean tree.

### 6.3 Reader (`tools/queue_status.py`)

It prints one row per session: name, state, head, ahead/behind, last suite (result and age, and whether it ran on the
current head), what it waits on and for how long. Then it prints the merge-train candidates (state `green` or
`waiting-for-slot`, suite on the current head, behind `main` by 0 or only by train-mergeable commits), and the suite
queue and classes (§5).

**Stall flags:**
- `STALE`: no update for more than `--stale-hours` (default 2) while the state is `building` or `suite-running`;
- `DEAD`: state `suite-running`, but no live suite-queue ticket or holder for that worktree;
- `WAITING-ON-USER`: shown separately with its age, because a long wait for the user is not a session fault but is
  what went unnoticed overnight;
- `GONE`: the worktree path no longer exists.

`parked` and `done` are never flagged. All text from the files is printed with control characters escaped, because a
status file is input written by another process.

---

## 7. Proposed AGENTS.md rules (land only in the drained slot) — D-429

1. **Push discipline.** A session does not push to `main` itself once the train is in use. It records `green` on its
   exact head (§6) and sets `waiting-for-slot`. The orchestrator runs the train over the waiting branches and pushes
   only with `--push` and the user's approval quoted in `--approval`. Never force; never rewrite history.
2. **Numbers.** D-numbers, regen-batch items, spec item labels and routing ids come from `tools/reserve_id.py`, never
   from reading a file.
3. **Pins.** Pin conflicts are resolved by re-running `tools/regen_pins.py`, never by hand-merging digests.
4. **Generated docs.** Generated indexes are never edited by hand. A conflict in one is resolved by re-running its
   generator.
5. **Heavy jobs.** Full suites, imports, rehearsals and recomputes run through the job queue (§5).
6. **Status.** Each session updates its status file on every state change and at least every 2 hours while working.

---

## 8. Findings from the survey (for routing by the orchestrator; this session changes none of them)

1. **Live collision, D.2.9 item 14.** `ingest-formats-3` (D_adapters.md:680, "Container members of archive inputs…")
   and `d323-stream` (D_adapters.md:681, "Streamed multi-execution files…") both add `14.`. The second to merge
   should take 15. Neither is cited yet.
2. **Stale item number on `claude/d31-bumps`.** Its DECISIONS.md:980 (D-31 addendum) says "regeneration-batch item
   29", but the branch's own row is 30 (row 29 is carved blobs, D-218, on main).
3. **Ambiguous bare "item 29"**: `docs/architecture/J_migration.md:834` and `docs/reports/migration/gate-c6.md:134`
   mean D.10.4a item 29, not regen-batch item 29.
4. **Stray list item** at D_adapters.md:2620: a wrapped line that starts with `220.` renders as a new list item.
5. **regen-batch rows 18–20** exist only as sections, not as table rows.
6. **D-150:** no number has two defining entries on main or on any local branch ahead of main today. The double use
   seen 2026-10-12 was renumbered before merge; the ledger prevents it rather than repairing it.
7. **Spec text vs code:** HL_corpus_versioning.md:446 names `registry.code_digest(adapter_id)`, which does not exist.
   The registry docstring says 18 phase-10d sources; there are 19.
8. **C.16 copies are untested:** no test compares the C.16.1–C.16.4 blocks in `C_data_model.md` with the vector files
   (`regen_pins.py --check` would, §4.2).
9. **Forward reference:** DECISIONS.md:3055 on main cites D-300, which is defined only on `phase-10n-small`.
10. **The C.16.4 spec block is not a valid AER.** Commit `7279b284` (2026-10-08, "AgentDojo assumption I-twins")
    added `evf {"/on_behalf_of":"I"}` and two `_unverified` citations to the C.16.4 block in `C_data_model.md`
    (lines 2421–2444) but did not reseal it, and did not change the vector file. The block's seal still claims
    `1d6d2c59…`, but its records hash to `d51fa9d0…`. The vector file `rope_denial_qwen_autodojo.aer.jsonl` is
    self-consistent (`1d6d2c59…`) and matches the digest row. The same holds on `main`, `claude/d31-bumps` and
    `deferrals-c`. Either the vector is regenerated with the I-twins and the block, row and seal updated, or the block
    is reverted to the vector. This is for the spec owner (it touches lines D-31 and part C edit).
11. **D-219 sits above the DECISIONS.md title on `deferrals-c`.** Commit `8c0e3169` inserted the D-219 entry as
    lines 1–10, before `# AgentPROV v0.1 — Architecture decision brief`. The `--split` refuses that file, which is
    correct. The entry belongs in the part-C block with D-216/D-217, and moving it there before the merge is enough.
12. **Citations of an unnumbered list.** `tests/unit/artefacts/test_catalogue.py:1` cites "D.15.7 items 1 and 2", but
    D.15.7 lists its tests as bullets. Cite the bullets by name, or number the list. It is the only unresolvable
    citation among 330.

## 9. Decisions proposed (for the user)

| Id | Proposal |
|---|---|
| D-420 | A local batched merge train (`tools/merge_train.py`), not GitHub's merge queue: one suite per batch, prefix bisect on red, fast-forward push only with `--push` and the user's approval quoted, never force |
| D-421 | Option B (one file per entry, generated and committed indexes) for DECISIONS.md, regen-batch.md, AGENTS.md §0/§13 and the registry; `merge=union` only for the id-ledger mirror, because union is shown to corrupt entries (§2.1) |
| D-422 | Fragment layout, frozen legacy order, byte-identical migration, conflicts in generated files resolved by regeneration, `adopt` for stale branches; spec items keep frozen numbers as labels, with anchors, ledger-allocated new numbers and a citation-resolving test |
| D-423 | The id ledger: machine-local authority under `flock` in `~/.agentprov/ids/`, a committed mirror; seeded from the tree; `scan` reports collisions |
| D-424 | `tools/regen_pins.py` orchestrates the existing regenerators in dependency order; `--check` in a scratch worktree, run twice; input pins out of scope; `c16-copies --write` only after D-31 and part C merge |
| D-425 | Pin conflicts are resolved by regeneration with attribution; an unattributed pin move stops the train for the user |
| D-426 | Registry split into per-source and per-family modules with a generated static import list (`src/` change; asks the user) |
| D-427 | Job classes for `tools/suite_queue.py` (`--class suite|import|rehearsal`, slot locks, CPU/memory budget, global FIFO among class heads, soft load guard); an interface proposal for the suite-perf session |
| D-428 | Session status files (`agentprov-session-status/1`), writer `tools/session_status.py`, reader `tools/queue_status.py` with stall flags |
| D-429 | The AGENTS.md rules of §7 (push via the train, numbers from the ledger, pins and generated docs by regeneration, heavy jobs through the queue, status updates) |

## Appendix A. Union-merge reproduction

```sh
git init -q r && cd r && git config user.email t@t && git config user.name t
echo 'D.md merge=union' > .gitattributes
printf '# Decisions\n\n- **D-1.** First.\n  - user-approved.\n\n- **D-2.** Second, proposed.\n' > D.md
git add -A && git commit -qm base && git branch base
# case 1: shared trailing lines
git switch -qc e base
printf '\n- **D-421.** Alpha.\n\n  Rejected alternatives:\n  - none.\n\n  Status: proposed.\n' >> D.md
git commit -qam e
git switch -qc f base
printf '\n- **D-401.** Beta, longer first line.\n  extra beta line\n\n  Rejected alternatives:\n  - pytest-parallel.\n\n  Status: proposed.\n' >> D.md
git commit -qam f
git merge -q --no-edit e    # D-401 (ours) loses its "Status: proposed." and its separating blank line
# case 2: status edit of the last entry next to an append
git switch -qc g base; sed -i '' 's/Second, proposed./Second, user-approved./' D.md; git commit -qam g
git switch -qc h base; printf '\n- **D-3.** Third.\n' >> D.md; git commit -qam h
git switch -q g; git merge -q --no-edit h   # both "Second, user-approved." and "Second, proposed." remain
```
