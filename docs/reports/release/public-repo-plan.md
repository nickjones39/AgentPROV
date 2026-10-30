# The public repository: pre-public scrub and fresh-history steps (D-911)

Date: 2026-10-29, Mac Studio. Branch `claude/reverent-blackwell-cc6b30` (base `4870173b`). Brief:
`~/.agentprov/handoff/release-prep-v0.1.0.md`, item 3. Class 0: a plan; nothing was changed, created or pushed.
**Updated 2026-10-29 after the Phase B rehearsal** (`public-export-rehearsal.md`; D-980): the two-commit history (P-7,
step 11), `git add --force -A` (step 9), the helper `tools/public_export.py` (steps 8–11) and the fingerprint count.

D-911: the development repository stays private (`nickjones39/agentprov-framework`); the public release goes to a new
`nickjones39/AgentPROV` that starts from a fresh history, and the building commits stay checkable through the snapshot
record. This plan makes the public tree **exactly the release commit's tree minus a listed set of exclusions**, so the
one fact an auditor needs ("the public code is commit R of the development repository") can be checked with the same
listing digest the snapshot tool writes. Every scrub is therefore a normal commit in the development repository
*before* R, never an edit in the exported tree.

All counts below are value-blind (paths, classes and counts; no secret, name or address was printed).

## Your decisions, in one list (each with my recommendation)

**Approved (the user, 2026-10-29, in the release-preparation window: "i approve your recommendation"): every
recommendation below, recorded as D-943.** Outward steps stay the user's to run.

| # | Decision | Recommendation |
|---|---|---|
| P-1 | The five copyleft fixtures (gate, SENTRY, aiAuthZ, bookkeeper, llm-lock; the 2026-10-12 release blocker) | **Replace them with synthetic fixtures** in the development repository before R (the blocker's own wording), so the public test suite runs complete. Alternative: leave them out of the export and make their tests skip when absent; weaker, because the public suite then never exercises those dialects |
| P-2 | **U-06** (never decided; B-2 default "private only"): may real third-party fixtures be public? 556 permissive real-data entries in 33 fixture directories, 145 entries with no `licence_class` in 6 directories (`agentops`, `autogen`, `drift`, `mcphunt`, `memo-ozdincer`, `wirelog`), 4 `restricted_use` (AgentHarm) | **Publish the `permissive` fixtures** (their data is published in the corpora under the same licences; each has its `SOURCE.json` and licence text), **after** the 145 unclassified entries are classified; **leave out `restricted_use`** (the AgentHarm clause does not sit well in an MIT-licensed repository) and anything not classified. The model-provider terms stay "not assessed", as in the datasheets. The same answer applies to the snapshots (S-4) |
| P-3 | Development notes in the tree: `AGENTS.md` (2,643 lines), `CLAUDE.md`, `.claude/settings.json`, `docs/agents/` (103 files), `docs/workflow/id-ledger.jsonl`, `docs/mac-studio-handoff.md` | **Keep `AGENTS.md`, `docs/agents/` and `docs/workflow/`** (they are the decision record the spec and 229 code/test files cite, and `tools/gen_docs.py` builds from them); **leave out** `CLAUDE.md`, `.claude/` and `docs/mac-studio-handoff.md` (operating notes for this machine and its agents). Your call: these are about how the work was done, not what it is |
| P-3a | **User request (2026-10-30):** "make sure all AI files, such as claude files and .md files, and any unneeded files are stripped out too. making sure to keep the desktop guide and the landing page" | **Decided (user, 2026-10-30), recorded as D-1004; supersedes P-3's "keep" for agent files. Prepared and dry-run on 2026-10-30 (section 4); the "unneeded" candidates are still yours (section 4.4).** Nothing is removed from the development repository (user, 2026-10-30: "do not strip out these files now, we need to make a new repo that has been sanitised"); only the public export leaves them out, and the public repository's `.gitignore` lists them so they can never be committed there (user, 2026-10-30: "yes only in the new repo"). The same exclusion applies to every file of the Zenodo software record (user, 2026-10-30): the source archive, sdist, wheels and bundles come from the exported tree, and the building-commit snapshots are rebuilt with these paths excluded. Leave out every coding-agent file: `CLAUDE.md`, `.claude/`, `AGENTS.md`, `docs/agents/` (session briefs and history) and `docs/mac-studio-handoff.md`, plus any other agent instruction or memory file found by a sweep. **Also leave out** `docs/user-guide/_go-live.md` and `docs/user-guide/_findings.md`, the orchestrator's go-live checklist and the guide's findings log (the site already excludes every `_*.md`; `.github/workflows/pages.yml` and D-760 name `_go-live.md`; the user's decision of 2026-10-30, docs review v0.1.0 Q14). **Always keep** `site/` (the landing page), `docs/user-guide/` (including the desktop app chapters; apart from those two files), `README.md`, `LICENSE`, `CITATION.cff`, `THIRD_PARTY_NOTICES.md` and the release notes. Before R: a scoping pass lists the remaining "unneeded" candidates (`docs/workflow/`, `migration/`, internal parts of `docs/reports/`) with what cites each, for the user's yes; the public tree must still pass its own gate (step 12): tools and tests that read the dropped files skip or are left out, README and code comments stop linking them, and `public-export.toml` gains the entries under a new decision |
| P-4 | `docs/reports/` (2,416 files; pre-checks, post-checks, bug passes, regeneration, systematic search) | **Keep** (the evidence behind the datasheet statements; 229 files in `src/`, `tests/`, `tools/`, `gui/` and `corpora/` cite paths under it, and 84 tests read `docs/`), after the scans of P-5 and P-6 |
| P-5 | Account paths: your own home path in 52 files (20 bug-pass reports, 12 systematic-search, 2 tests, the rest spec examples and reports); 28 distinct `/Users/<name>` values, 161 files with `/home/<name>`, 19 with `C:\Users\` | Run the account-path classification (D-457 method, ordinals only) over the export; **mask your own home path** to `~` in a scrub commit before R; leave synthetic and benchmark persona paths (classified, as for the corpora) |
| P-6 | Secrets: gitleaks `dir` finds 36 redacted `generic-api-key` hits in 18 files (24 in benchmark fixtures, 7 in pre-check samples, 3 in docs, 2 in tests); your e-mail address is in 1 file (`docs/reports/systematic-search/data/S2-literature/scripts/oa.py`, an API contact) | Triage the 36 by origin (D-920 method), record it; replace the e-mail with an environment variable read at run time, in a scrub commit before R |
| P-7 | Commit identity of the fresh history | One root commit, author and committer **your GitHub no-reply address**, dated at R's commit time, message naming R in full (`AgentPROV v0.1.0, exported from agentprov-framework <R>`). Signed if you choose a signing key (v0.1.0 plan, V-6). **Amended by D-980 (user, 2026-10-29):** the root commit is followed by one commit that changes only `.gitleaksignore` (the accepted findings fingerprinted on the root commit, which the root commit itself cannot name), and the tag `v0.1.0` goes on that second commit (rehearsal F-3) |
| P-8 | Make the new repository public at once, or private first | **Private first:** push, check the rendering, Actions and the release draft, then switch to public (your explicit instruction) |
| P-9 | GitHub Pages for the user guide (D-760 deferred it) | **Corrected 2026-10-30 (D-1004):** the earlier "later" and step 15's "Pages off" contradicted D-1000. The project website goes live on GitHub Pages **from the public repository**: the landing page (`site/`) at the root and the MkDocs guide under `/docs/`, addressed as `https://w3id.org/agentprov/` and `https://w3id.org/agentprov/docs/`. It is enabled once the repository is public (step 19), with the existing `.github/workflows/pages.yml` (manual dispatch only, the D-431 pattern). Actions runners are free once the repository is public (D-431's billing block does not apply) |
| P-10 | How later releases reach the public repository | One commit per release on top of the previous public commit, each the release commit's tree minus the same exclusions, its message naming the development commit. Never a push of development history. (D-980: a later release's commit can carry its own `.gitleaksignore` fingerprints only in a following commit, as at v0.1.0) |

## 1. What leaves the tree, and why

| Path | Reason | Decided by |
|---|---|---|
| `tests/fixtures/{gate,sentry,aiauthz,bookkeeper,llm-lock}/` and their 5 `tests/fixtures/LICENSES/*` texts | AGPL/GPL fixtures approved for the private repository only | user, 2026-10-12; P-1 replaces them |
| `tests/fixtures/<dir>/` entries with `licence_class` `restricted_use` or none | B-2 / K.4.2 default until U-06 | P-2 |
| `CLAUDE.md`, `.claude/`, `docs/mac-studio-handoff.md` | operating notes for this machine's agents | P-3 |
| `AGENTS.md`, `docs/agents/`, `docs/review/`, `tools/review/`, `docs/reports/gui/todo-next-session.md` | coding-agent memory, session briefs and review tooling; the public `.gitignore` lists the agent files | P-3a, D-1004 |
| `docs/user-guide/_go-live.md`, `docs/user-guide/_findings.md` | the guide's internal orchestration checklists | Q14, D-1004 |
| `.gitleaksignore` (rewritten, not removed) | its 12 fingerprints (D-462 and its 2026-10-24 addendum) are commit-pinned (`commit:path:rule:line`) and name development commits; the fresh history needs new fingerprints for the same 12 findings, which you accept again (D-980: yes, 2026-10-29). The rewrite is the second commit (step 11), so the root commit stays exactly R minus `EXCL` | D-462, D-980 |
| nothing under `src/`, `capture/`, `zenodo/`, `gui/`, `backends/`, `tools/`, `corpora/`, `docs/architecture/` | the code, the spec and the corpus specs are the release | — |

`tests/repo/test_repository_hygiene.py` checks the K.12.13 agent-hygiene rules (a `.claude/settings.json` deny rule
among them). Leaving out `.claude/` therefore needs that test to accept its absence (a small test change before R), or
`.claude/settings.json` stays (it holds only deny rules).

## 2. The steps

### Phase A: in the development repository, before the release commit R (class 0; trains by the orchestrator)

1. **Copyleft fixtures** (P-1): synthetic fixtures for the five sources, in the shape `tests/adapters/agentdojo/
   phase10d_support.py` already builds synthetic variants with; the 7 test modules that import that helper pass; the
   THIRD_PARTY_NOTICES.md "Copyleft fixtures" paragraph is rewritten.
2. **U-06** (P-2): classify the 145 unclassified `SOURCE.json` entries; apply your answer (move `restricted_use` to
   `$AGENTPROV_RESTRICTED_FIXTURES` with `full_corpus` tests, or the export exclusion list).
3. **Scrub commit** (P-5, P-6): your home path → `~` in the 52 files; the e-mail → an environment variable; the one
   third-party account name the rehearsal's account scan found in `S1-dependents.jsonl` → `<account>` (D-980). The account
   classification and gitleaks triage are recorded in `docs/reports/release/` (classes and counts only).
4. **Links and wording:** the 3 files naming `agentprov-framework` (`CLAUDE.md`, `D-911`, `DECISIONS.md`) stay as the
   historical record (D-911 is about the private repository); the README gains a "Development history and building
   commits" paragraph pointing to the software record (D-911). The 81 files naming `nickjones39/AgentPROV` already name
   the public repository. Commit ids of the development history quoted in docs stay as they are: they resolve through
   the snapshot record, not through the public history.
5. **Release files:** `CITATION.cff`, the version checks and the release notes (v0.1.0 plan).
6. **R** is the commit on `main` after all of that and after wave 2 is sealed. Gate: the full suite through the queue,
   `tools/ci_local.py`, `uv lock --check`, `tools/check_unicode.py`, `mkdocs build --strict`.

### Phase B: local, no outward step (a session can do it, through the queue)

7. **Exclusion list** `EXCL` (P-1..P-3), written to `docs/reports/release/public-export.toml` with each path's reason.
8. **Export** R's tree minus `EXCL` into a new directory under `~/.agentprov/release/` (never the working tree, never a
   checkout with untracked files). `tools/public_export.py export` (D-980) does steps 8–10 in one run: `EXCL` from R's
   own `public-export.toml` and fixture rule, `git archive` with each path as `':(exclude,literal)PATH'` on the command
   line (`git archive` has no `--pathspec-from-file`; rehearsal F-2), unpacked into the new directory:

   ```bash
   uv run python tools/public_export.py export --commit R --out ~/.agentprov/release/public-tree --email NOREPLY
   ```

   `NOREPLY` is your GitHub no-reply address (GitHub › Settings › Emails, `<id>+nickjones39@users.noreply.github.com`);
   add `--sign` to sign the commits with your git signing key (V-6).
9. **Fresh repository** in that directory: `git init -b main`, `git add --force -A` (a tracked file may match
   `.gitignore`: rehearsal F-1 found `tests/adapters/foobench/golden/trace-001.aer.jsonl`; the directory holds only
   the archive's files, so `--force` adds nothing else), one **root commit** with the P-7 identity and message. Hooks
   are off in the new repository.
10. **Equality proof:** the root commit's `git ls-tree -r` lines (mode, blob, path) equal R's minus `EXCL`, compared as
    the snapshot tool's `listing_sha256`; the helper refuses otherwise and writes the proof (R, its tree, the root
    commit and tree, the listing digest, `EXCL` with its digest and the export list's digest) to
    `public-tree.export-proof.json` beside the directory. It goes into the release notes and `docs/reports/release/`.
11. **Scans and the second commit** (D-980). On the root commit: `gitleaks git --redact --report-format json
    --report-path gitleaks.json` (the accepted findings, now fingerprinted on the root commit), then

    ```bash
    uv run python tools/public_export.py fingerprint --dir ~/.agentprov/release/public-tree --report gitleaks.json --tag v0.1.0 --accept
    ```

    It rewrites `.gitleaksignore` with the same comment blocks and one fingerprint per accepted entry (matched by path
    and rule), refuses any other or missing finding (a new one needs a new decision), commits that file alone with the
    root commit's identity and date, and puts the annotated tag `v0.1.0` (`--sign`: signed) on that commit. Without
    `--accept` it prints the candidate and commits nothing. A second `gitleaks git` then reports no leaks. Then
    `gitleaks dir --redact` (only the triaged classes of step 3 remain), the account-path scan (only classified
    ordinals), `tools/check_unicode.py`.
12. **The new repository's own gate:** `uv sync --frozen --group docs`, the full suite through the queue, `ci_local.py`,
    `mkdocs build --strict`, the G5 bundles (v0.1.0 plan).

### Phase C: yours (outward)

13. **First**, re-pin the Claude desktop app's pinned origin for this repository from the old name `nickjones39/AgentPROV` to `nickjones39/agentprov-framework` (Help → Troubleshooting); every local remote already uses the new name. Creating the new repository ends GitHub's rename redirect, so a stale pin would point the app's sync at the public repository (C-3 session finding, 2026-10-30). Then create `nickjones39/AgentPROV` on GitHub, **private** (P-8), with no README, licence or `.gitignore` from GitHub (the
    push brings them). Check that no Zenodo GitHub integration watches it (collection layout L-6).
14. Push from the export directory: `git push origin refs/heads/main refs/tags/v0.1.0` (exact refs, never `--all` or
    `--tags`). `main` holds the two commits of steps 9 and 11.
15. Repository settings: secret scanning and push protection on; Dependabot alerts on; Actions with read-only
    `GITHUB_TOKEN` (the workflows already declare `contents: read`; `pages.yml` adds only `pages: write` and
    `id-token: write`); a branch protection rule on `main`. Pages is enabled at step 19, after the repository is public
    (P-9, D-1000).
    The About box: the description the development repository carries since 2026-10-30 ("Execution provenance for
    LLM-agent security research: converts live and released agent runs into evidence-qualified W3C PROV, with
    hash-chained corpora you can verify and recompute without re-running any model."), its eight topics, and the
    website `https://w3id.org/agentprov/` once the w3id rule is live.
16. Check the rendering of README, LICENSE, CITATION.cff ("Cite this repository"), THIRD_PARTY_NOTICES.md; dispatch
    `ci.yml` and `bundles.yml` once if you want the runners' evidence (manual dispatch only, D-431).
17. Create the GitHub Release **as a draft** from `v0.1.0` with the notes and assets of the v0.1.0 plan.
18. On your explicit instruction: make the repository public, then publish the release.
19. **The project website on GitHub Pages** (P-9, D-760, D-1000), on your instruction, after step 18 and the pre-release
    scans over the built site (`mkdocs build --strict`, then `site/` copied to `_site/`, as `pages.yml` does):
    Settings › Pages › Source "GitHub Actions" (yours), then one manual dispatch of the existing workflow,
    `gh workflow run pages.yml --ref main` (manual dispatch only, D-431). Check that
    `https://nickjones39.github.io/AgentPROV/` serves the landing page and `…/docs/` the guide; then the w3id pull
    request (`docs/reports/site/w3id/`, D-1000) makes `https://w3id.org/agentprov/` and `…/docs/` lead there. The
    development repository's go-live checklist (`docs/user-guide/_go-live.md`, not in the public tree) has the details.

## 3. What stays private

The development repository and its history (account paths and secrets masked only from `42a85025` on, and the
copyleft fixtures), the local `wave2/build-*` tags (pushed only to the development repository, S-1), the corpora's
`.withheld/` directories, `.env`, and everything under `~/.agentprov`. An auditor who needs more than the snapshots
gets the restricted-access `git bundle` (D-911) on request.

## 4. P-3a: export preparation and dry run (2026-10-30, D-1004)

Session `export-prep-p3a` (branch `claude/export-prep-p3a-a24b11`, base `def90e16`). Local only: nothing was pushed, no
repository or remote was created, no network beyond what the tests already do. Counts and digests only.

### 4.1 What the public export leaves out

`public-export.toml` (D-943, amended by D-1004 and its addendum) now lists 11 paths, 114 files, plus the 5 files the
fixture rule keeps private (119 in all). The dry run in 4.3 had the first 10 paths (117 files); 4.5 adds
`docs/workflow/`:

| Path | Files | Why |
|---|---|---|
| `CLAUDE.md`, `.claude/`, `docs/mac-studio-handoff.md` | 3 | P-3 (and P-3a) |
| `AGENTS.md`, `docs/agents/` | 104 | P-3a: coding-agent memory, session briefs and history |
| `docs/review/`, `tools/review/`, `docs/reports/gui/todo-next-session.md` | 4 | the P-3a sweep: the code-review agent's `REVIEW.md` and ultrareview plan, the ultrareview driver, a session's to-do brief; **confirmed by the user** (2026-10-30, "confirm the 3 sweep finds") |
| `docs/workflow/` | 2 | the multi-session id ledger and session-status schema; the user's answer to 4.4 (2026-10-30, "drop docs/workflow from the export") |
| `docs/user-guide/_go-live.md`, `docs/user-guide/_findings.md` | 2 | Q14 |

The sweep looked for every name the hygiene test knows as an agent file (`AGENTS.md`, `CLAUDE.md`, `SKILL.md`,
`GEMINI.md`, `.cursorrules`, `.windsurfrules`, `.clinerules`, `copilot-instructions.md`, `.claude/`, `.mcp.json`),
for hand-over, brief, prompt and session files outside `src/`, `tests/` and the corpora, and for files that address
the coding agent. Nothing else was found. Kept: `site/`, `docs/user-guide/` (16 chapters, including chapter 8, the
desktop app), `README.md`, `LICENSE`, `CITATION.cff`, `THIRD_PARTY_NOTICES.md`, the release notes and
`.github/workflows/pages.yml`.

**The public `.gitignore`.** The export list's new `[gitignore]` table adds 13 patterns (`CLAUDE.md`, `AGENTS.md`,
`.claude/`, `/docs/agents/`, `/docs/review/`, `/tools/review/`, `/docs/workflow/` (since 4.5), `/docs/mac-studio-handoff.md`, `GEMINI.md`,
`.cursorrules`, `.windsurfrules`, `.clinerules`, `copilot-instructions.md`). `tools/public_export.py export` appends
them to the public tree's `.gitignore` in the root commit, under a comment giving the reason. The equality proof checks
that exact blob, and `*.export-proof.json` records both blobs and the lines. The development repository's
`.gitignore` is unchanged.

**For the snapshot list.** `building-commit-exclude.toml` matches the export on every agent and checklist entry
except the three sweep finds (`docs/review/`, `tools/review/`, `docs/reports/gui/todo-next-session.md`) and
`docs/workflow/`. The user said yes to adding the sweep finds and rebuilding (2026-10-30); the rehearsal session does
that rebuild, not this branch.

### 4.2 What the dry run changed in the development repository (all class 0)

- `tools/public_export.py`: the `[gitignore]` append in the root commit, with its proof fields and refusals. The
  fingerprint commit now **drops** a `.gitleaksignore` entry that has no finding in the root commit, and reports it.
  The dry run found one: the entry pinned to `docs/architecture/DECISIONS.md` from before the D-1003 split. That text
  now lives in `decisions/D-269.md` and its decision-log part, which have their own entries. A fresh history cannot
  hold the old entry, and dropping an accepted fingerprint hides nothing. Any new finding is still refused. The
  public `.gitleaksignore` therefore holds 12 fingerprints, not 13.
- `tools/regen_pins.py --check` reused one scratch worktree of the development repository, so in the export it failed
  at `git checkout` ("unable to read tree"). A second repository now gets its own `regen-pins/repos/<digest>/`.
- `tools/gen_docs.py` reports a target with neither its file nor its fragments in the tree as `absent` and passes. The
  public tree has neither `AGENTS.md` nor `docs/agents/`.
- Tests that read `AGENTS.md` now fall back to the README or skip in the public export:
  `test_repository_hygiene` (`AGENTS.md`, and 12 fingerprints there), `test_slow_lane` and `test_ci_local` (the gate
  command, now read from the README as well), and `test_gen_docs`.
- Public-facing text: `docs/adapter-guide.md` no longer sends contributors to `AGENTS.md`. `pages.yml` and
  `mkdocs.yml` point to step 19 rather than `_go-live.md`. A `gui/tools/screenshots.py` comment no longer names the
  to-do brief. No Markdown link anywhere in the public tree points to a dropped file. Plain mentions remain, for
  example `AGENTS.md §8` in `ci.yml` comments, `AGENTS.md` in the roadmap, and the decision record's history.
- Plan fixes: P-9 and step 15 (Pages per D-1000, new step 19), `v0.1.0-plan.md` (the venue is KBS), spec O.1 (the
  manuscript file is `paper/agentprov.tex`).

### 4.3 Dry-run results

**All green.** The final run exported `91b84a53`, this branch after merging `origin/main` at `4955058c`, so the tree
carries the real software DOI. The export went into `~/.agentprov/scratch/p3a-dryrun-2026-10-30/run-3/public-tree`
with a placeholder no-reply address. Step 11 was rehearsed there with `--accept`, in the throwaway repository only: it
is not your release-day yes.

| Check | Result |
|---|---|
| Equality proof (step 10) | refused nothing; root `88a5dcbf`, 6,350 files, 117 excluded, `listing_sha256` `sha256:d7e3edad…f7d8c2`. `.gitignore` is development blob `d90e48d1` → public blob `84ff78bb` (12 lines appended) |
| Excluded paths in the tree | none of the 10 paths on disk or in the index; 0 of the 117 excluded files present |
| Public `.gitignore` | all 12 lines present; `git check-ignore` matches `CLAUDE.md`, `AGENTS.md`, `.claude/…`, `docs/agents/…`, `docs/review/…` and `tools/review/…` (6 of 6). The development `.gitignore` is unchanged against `origin/main` |
| `gitleaks git` on the root commit | 12 findings, all accepted ones; fingerprint candidate 12 entries, one dropped (`DECISIONS.md`, development history only) |
| `gitleaks git` after the second commit | no leaks found |
| `gitleaks dir --redact` | 36 hits in 18 files: 24 in the fixture tree and the 12 accepted findings, the same count and classes as the P-6 / S-5 triage |
| Account paths (D-457, value-blind) | 53 distinct names, as in the rehearsal after its mask; this machine's home path, its account name and the maintainer's personal e-mail: 0 files |
| `tools/check_unicode.py` | clean |
| `uv sync --frozen --group docs` | done (Python 3.14.8) |
| Full suite, through main's queue (`-n 24`, `--cpu 24`) | **11,671 passed, 156 skipped, 0 failed** (7 min 6 s). The first run, before the fixes, had 5 failures (4.2) |
| `mkdocs build --strict` | passes, 0 warnings |
| `tools/regen_pins.py --check` (queue, rehearsal class) | all 19 families current |
| `tools/gen_docs.py --check` | decisions and regen-batch current; agents `absent` |
| Working tree after all of it | clean |

Also run on the development branch: the full suite (11,715 passed, 112 skipped, 0 failed), then `tests/repo` and
`tests/unit/release` again after the merge (724 passed), plus `ruff`, `mypy`, `check_unicode` and `uv lock --check`.
Not run: `tools/ci_local.py` and the G5 bundles (step 12; they need network or VMs).

### 4.4 The "unneeded" candidates

**Answered by the user (2026-10-30, relayed by the orchestrator): "drop docs/workflow from the export, keep migration
and docs/reports"** (D-1004 addendum; 4.5). The table below is the question as it was put.

| Candidate | Files | What cites it | Recommendation |
|---|---|---|---|
| `docs/workflow/` (`id-ledger.jsonl`, the session-status schema) | 2 | `tools/reserve_id.py`, `tools/session_status.py`, `tests/unit/workflow`, one qwencode test, `.gitattributes`, 2 release reports, one decision | Leave out: this is the multi-session id ledger and session tooling. It needs `reserve_id`/`session_status` and their tests to skip when the ledger is absent, a small change like 4.2 |
| `migration/` (the frozen baseline's requirements, lock, build constraints, `expected_differences.toml`) | 4 | `src/agentprov/migration` (3), `tools/migration` (4), `tests/migration`, `backends/shared` testing (2), spec J (5), 4 reports | **Keep:** gate C (old vs new) and the migration tests need it. It is not "unneeded" |
| `docs/reports/` parts cited by no code, test or tool | 198 | `bugpass-new-families` (52), `review-core-c` (2), `review-core-d` (58), `review-gui` (1) and `m5ultra-performance` (1): nothing outside `docs/reports/`. `review-core-a` (57), `review-core-b` (2), `anthropic-endpoint` (1), `deferrals` (8), `ingest-formats` (6), `local-llm` (1), `pipeline-perf` (7) and `backends` (2): only decisions or the spec (D-490, D-500, D-656, D-207..D-215, D-240..D-386, D-412..D-416, D_adapters, J, G) and, for the last two, guide chapter 7 | Keep (P-4): these are the review and bug-pass evidence behind decisions the spec cites. Leaving them out would leave those citations dangling in the public spec. If you want them out, the first five groups (114 files) are cited by nothing outside `docs/reports/` |
| `docs/reports/systematic-search/` | 86 | the manuscript, by URL in the public repository (`…/AgentPROV/tree/main/docs/reports/systematic-search`); 51 code, test or tool files; the datasheets | **Keep, cited by the paper** (orchestrator, 2026-10-30). The P-6 scrub (D-948, `c033f594`) is in: the exported `S2-literature/scripts/oa.py` holds no address-shaped literal and reads `AGENTPROV_LITSEARCH_MAILTO` |
| the rest of `docs/reports/` (`precheck` 1,177 files, `analysis` 234, `postcheck` 212, `regeneration` 124, `release` 69, …) | 2,189 | 1 to 31 code, test or tool files each (`precheck` and `phase10d` 31 each) and the datasheets | Keep (P-4): the tests read them |

### 4.5 `docs/workflow/` left out (D-1004 addendum)

`tools/reserve_id.py` writes no mirror where `.gitignore` ignores `docs/workflow/id-ledger.jsonl`, which the public
`.gitignore` now does; the reservation stays in the machine ledger and the tool says so (test in
`tests/unit/workflow/test_reserve_id.py`). The session-status tests check the JSON schema only where the file is.
Nothing else reads the folder: `.gitattributes` keeps its `merge=union` line, which is harmless without the file, and
one qwencode test only names the path in a list of allowed changes.

**Re-export check (affected checks only, as the orchestrator asked).** Export of `623f83e5` into a throwaway
directory: equality proof passed (root `fccb968e`, 6,348 files, 119 excluded, 13 `.gitignore` lines appended). No
`docs/workflow/` on disk or in the index, and `git check-ignore` ignores it. The fingerprint step was rehearsed there
(12 fingerprints, the `DECISIONS.md` entry dropped as before). Inside the export, `tests/repo`, `tests/unit/workflow`,
`tests/unit/release`, the slow-lane test and the qwencode boundary test gave 923 passed and 13 skipped. `gen_docs
--check` passed, `reserve_id.py list` ran, and the tree was clean afterwards. The full suite was not rerun: the change
touches only `reserve_id.py`'s mirror path and two test modules.
