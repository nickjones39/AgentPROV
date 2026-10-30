# Public export rehearsal (Phase B of `public-repo-plan.md`), 2026-10-29

Mac Studio, branch `claude/practical-almeida-1f1d9d`. Class 0. Everything ran locally: nothing was pushed, no GitHub
repository was created, Zenodo was not contacted, and no network was used (`uv` ran with `--offline` from its cache).
The stand-in for the release commit R is `origin/main` `94756891` (tree `63c38bbc`). It does not yet hold this
branch's licence-notice commit `4987c292`. Counts and digests only: no file content, secret, e-mail address or account
name is quoted. Scratch: `$AGENTPROV_HOME/release/rehearsal-2026-10-29/` (listed in section 6).

## 1. Result

| Step (plan §2) | Result |
|---|---|
| 7 EXCL | 7 files from R's own `public-export.toml` and its fixture rule: `CLAUDE.md`, `.claude/settings.json`, `docs/mac-studio-handoff.md`, and the 4 `restricted_use` AgentHarm entries (3 in `tests/fixtures/inspect/`, `tests/fixtures/LICENSES/AgentHarm-LICENSE.txt`). No copyleft fixture is excluded: since D-945 the five copyleft directories are synthetic. Every listed path matched. EXCL digest (sorted `path<TAB>reason` lines) `sha256:72884808…` |
| 8 export | `git archive` of R minus EXCL: 6,372 files, 108,032,000 B tar |
| 9 fresh repository | `git init -b main`, one root commit, author and committer the no-reply identity, dated at R's commit time, message naming R in full; annotated tag `v0.1.0` (unsigned in the rehearsal) |
| 10 equality | **equal** (after fix F-1): `listing_sha256` of R minus EXCL = the root commit's = `sha256:f3c63a1e…` |
| 11 scans | home path of this machine: 0 files; the maintainer's personal e-mail: 0 files; `gitleaks git`: 12 findings, the 12 accepted ones (F-3); `gitleaks dir --redact`: 36 hits in 18 files, as the release-prep count (still to triage, P-6); `tools/check_unicode.py`: clean; account paths: section 3 |
| 12 the export's gate | version checks pass (`agentprov info`: 0.1.0, `aer/0.2 sem/0.1 capture/0.1 agentprov-prov/0.1 apv 0.2.0 agentprov-corpus/0.2`); `uv lock --check` (core, `gui/`) current; `mkdocs build --strict` passes; full suite **5 failed**, 11,589 passed (section 4: F-11..F-13) |

## 2. Failures and surprises

| # | What | Effect | Proposed fix (before R) |
|---|---|---|---|
| F-1 | `git add -A` in the export drops `tests/adapters/foobench/golden/trace-001.aer.jsonl`: tracked in R, but matched by `.gitignore`'s `*.aer.jsonl` | the first run's listing digests differed by that one file | step 9 uses `git add --force -A` (safe: the directory holds only the archive's files); or un-ignore the path in `.gitignore` |
| F-2 | `git archive` has no `--pathspec-from-file` | none (the exclusions fit on the command line) | the plan's command form is the right one; keep it |
| F-3 | `.gitleaksignore`: every entry names a development commit, and `tests/repo/test_repository_hygiene.py::test_gitleaksignore_holds_only_commit_pinned_fingerprints` runs `git cat-file -e <commit>:<path>`, so the public repository fails it as exported. A rewritten file cannot name the root commit it is part of (the commit id depends on the file) | the plan's single root commit (P-7) and the `[rewrite]` of `public-export.toml` cannot both hold | **decision for the user**, see section 5 |
| F-4 | Three of the 12 accepted findings sit on other lines now (DECISIONS.md, `phase10k/trials.md`, the hygiene test); the 12 path/rule pairs are unchanged | none for the export: the fresh history fingerprints the current lines | the candidate file has the current lines |
| F-5 | The source archive `AgentPROV-0.1.0.tar.gz` and the sdist `agentprov-0.1.0.tar.gz` differ only in case: on this case-insensitive APFS volume (and on default macOS and Windows) one overwrites the other | the first build lost one of the two silently; a user downloading both release assets into one folder would too | rename the source archive (for example `AgentPROV-0.1.0-source.tar.gz`) in the v0.1.0 plan §4 and `SHA256SUMS` |
| F-6 | `bundle-report.json` names neither the version nor the commit | the v0.1.0 plan's step-8 check ("the reports name `0.1.0` and the `v0.1.0` commit") has nothing to read | add `version` and `commit` (from `git rev-parse HEAD` of the building tree) to the report in `gui/tools/build_bundle.py` |
| F-7 | The macOS report's `signature` text still says "right-click › Open" | the known D-657 wording issue (v0.1.0 plan §5) reaches the shipped report | the same wording fix as README and the guide |
| F-8 | The Linux and Windows bundles cannot be built here offline: `driver.py build` copies the archive into a VM whose guest runs `uv sync --locked --project gui` from PyPI | not built (section 4) | the G5 builds need a network yes; build them **from the export tree** so `driver.py`'s `REPO` is the public repository and `--checkout v0.1.0` resolves there |
| F-9 | The `.dmg` built with the stock PyInstaller 6.22.3 bootloader of a fresh `gui/` environment reports launcher SDK 26.2, restored by `vtool` (`sdk_current: true`) | none: `install_bootloader.py` was not needed on this Mac | — |
| F-10 | `public-repo-plan.md` §1 speaks of 4 `.gitleaksignore` fingerprints; the file holds 12 (D-462 and its 2026-10-24 addendum) | wording only | correct the count when the plan is next edited |

## 3. Account paths (D-457 method, value-blind)

54 distinct `/Users/<x>`, `/home/<x>` or `C:\Users\<x>` names in the export; none is this machine's account. By class,
from a reading of each match's context (names are kept in a local ordinal table, not here):
- synthetic or placeholder (`user`, `acct-…`/`account-…` test values, `x`, `u`, `foo`, regex fragments such as `.`,
  `..`, `...`, directory words such as `Desktop`, `Downloads`, `Shared`, `Public`): the large majority;
- CI runners and the G5 VM accounts (`runner`, `ubuntu`, `agentprov` classes): as the hygiene test's allowlist;
- benchmark personas and containers (`alice`, `bob`, `emma`, `openhands`, `docker`, `root`, `sandbox`, `node`);
- an illustrative pair in a bug-pass finding (a prefix-boundary example);
- **one third-party account** name in a public repository's file path, quoted in systematic-search data
  (`docs/reports/systematic-search/data/S1-code/S1-dependents.jsonl`, 1 hit). It is public on GitHub, but the
  pre-check rule (w3-7) masks such names. **For the user:** keep it as quoted public data, or mask it in a scrub commit
  before R.

## 4. Builds

Built from the exported tree at `v0.1.0` (the rehearsal commit), offline, through the queue (`--class import --cpu 2`
for the bundle).

| Artefact | Built | Size | Notes |
|---|---|---|---|
| `AgentPROV-macos-arm64.dmg` | yes, all `build_bundle.py` checks pass, `--smoke` 0 | 38,482,673 B (app 90.4 MB) | ad hoc signature; a real `cocoa` start was not run (it opens a window on the user's screen) |
| `AgentPROV-linux-aarch64.tar.gz` | no (F-8) | 2026-10-28 G5 build: 63 MB dir | needs the guest's PyPI download |
| `AgentPROV-linux-x86_64.tar.gz` | no (F-8) | 2026-10-28: 66 MB dir | as above; 1–3 h under QEMU |
| `AgentPROV-windows-arm64.zip` | no (F-8) | 2026-10-28: 31 MB dir | as above |
| `AgentPROV-windows-x64.zip` | no (F-8) | 2026-10-28: 41 MB dir | as above |
| source archive (`git archive --prefix=AgentPROV-0.1.0/ v0.1.0`) | yes | 28,474,695 B, 6,372 files | holds the public fixtures, as the public tree does; see F-5 |
| `agentprov` sdist / wheel | yes | 2,652,549 B (775 files) / 3,151,156 B | no `tests/fixtures/` member (K.4.2 holds) |
| `agentprov-capture` sdist / wheel | yes | 36,623 B / 42,032 B | no fixture |
| `agentprov-zenodo` sdist / wheel | yes | 21,156 B / 22,434 B | no fixture |

**The export's full suite** (`-n 8`, through the queue, in the exported tree at the second commit of variant (a),
section 5, with its own offline environment, `uv sync --frozen --group docs`): **5 failed, 11,589 passed, 152 skipped**
in 5 min 58 s. The tree stayed clean. `mkdocs build --strict` passes. The rewritten `.gitleaksignore` passes its hygiene
test, and the two `.claude/`/`CLAUDE.md` hygiene tests skip as D-948 designed.

| # | Failure | Cause | Proposed fix (before R) |
|---|---|---|---|
| F-11 | `tests/adapters/inspect/test_survey.py`: `test_the_committed_log_is_the_pinned_blob`, `test_c41_vector_4_known_answer` | they read the AgentHarm `restricted_use` fixtures that EXCL leaves out, and fail instead of skipping | skip when the fixture is absent (as the module's other tests already do) |
| F-12 | `tests/repo/test_fixture_caps.py::test_the_repository_tree_is_within_its_caps` and `tests/golden/test_golden_index.py::test_the_fixture_tree_holds_no_agent_instruction_files_and_respects_the_size_caps` | `tests/FIXTURES.json` lists an `oversize_files` entry for the excluded AgentHarm `.eval`; the caps check refuses an entry whose file is absent | accept the absence of an oversize file that the export rule leaves out (the check can read the same `SOURCE.json` classes), or move the restricted fixtures out as plan step 2 offers |
| F-13 | `tests/adapters/foobench/test_future_framework.py::test_the_commit_that_adds_the_adapter_changes_only_the_files_of_d121` | it finds "the commit that adds the adapter" in the history; in the fresh history that is the root commit, which adds all 6,346 files | skip when that commit is not the pinned development commit (as the `8c244150 is not in this checkout's history` tests do) |

The export also skips **33 Inspect tests** (16 "the committed Inspect fixture log is absent", 15 "the committed survey
AgentHarm log is not present", 2 for the `.eval`): with the AgentHarm fixtures out, the public suite never runs the
Inspect adapter on real data. Synthetic Inspect fixtures, as D-945 did for the copyleft five, would close that gap. The
other skips (`full_corpus`, the `render` extra, history-only checks) are the development checkout's too.

## 5. Decision for the user (through the orchestrator)

**F-3, `.gitleaksignore` in the fresh history.** Rehearsed variant (a) worked: a second commit on the root changes only
`.gitleaksignore` (the 12 findings re-fingerprinted on the root commit, the comment blocks kept), and `gitleaks git` then
reports no leaks; the equality proof still holds for the root commit.
- **(a) Recommended:** v0.1.0 is two commits, the root (R minus EXCL, equality proof) and a `.gitleaksignore` commit
  that names the root; the tag goes on the second. The proof states that the tag's tree differs from the root's only in
  `.gitleaksignore`. Your yes accepts the 12 findings again (D-462), as the plan already foresaw.
- (b) Leave `.gitleaksignore` out of the export (an EXCL entry) and make the hygiene test skip outside the development
  checkout. One commit, but the public history then has 12 unacknowledged gitleaks findings.

## 6. Scratch (for cleanup; nothing deleted)

Under `$AGENTPROV_HOME/release/` (sizes from `du -sh`), 1.8 GB in all:

| Path | Size | What |
|---|---|---|
| `rehearsal-2026-10-29/run-1/` | 245 MB | the first run (F-1: listing digests differed); tree, tar, EXCL |
| `rehearsal-2026-10-29/run-2/public-tree/` | 380 MB | the fresh repository (2 commits, tag `v0.1.0`), with its `.venv` (226 MB) |
| `rehearsal-2026-10-29/run-2/public-tree.tar` | 103 MB | the `git archive` output |
| `rehearsal-2026-10-29/run-2/gui-venv/` | 498 MB | the offline `gui/` environment the bundle was built with |
| `rehearsal-2026-10-29/run-2/bundle-macos/` | 231 MB | the `.dmg`, its report and PyInstaller's work tree |
| `rehearsal-2026-10-29/run-2/dist-py/`, `dist-src/`, `dist/` | 36 MB | sdists, wheels, the source archive (`dist/` is the first build of F-5) |
| `rehearsal-2026-10-29/run-2/site/`, `scans/`, logs | 8 MB | the mkdocs site, the redacted gitleaks reports, the candidate `.gitleaksignore`, suite and bundle logs; `accounts-private.json` holds the account ordinal table (local only) |
| `sandbox-trial-2026-10-29/` | 317 MB | the Zenodo sandbox-trial kit (its own README; keep until the trial is read back) |

The script that ran steps 7–11 is in this session's scratchpad (`rehearse_export.py`), outside the repository.

## 7. After the fixes (D-980): the re-rehearsal, 2026-10-29

The user approved every proposal above (relayed by the orchestrator): the two-commit history (section 5, variant (a)),
the account-name mask, and the fixes for F-1, F-5..F-7, F-10 and F-11..F-13. They are on branch
`claude/public-export-fixes` (D-980): a scrub commit (`<account>` in `S1-dependents.jsonl`), the test fixes, the
bundle report's `versions` and `source` and the Open Anyway wording, `tools/public_export.py` and the plan text. Steps
8–12 were then run again with the helper, R being the branch head (scratch `run-3`, `run-4`):

| Check | run-3 (R `e47aa156`) | run-4 (R `25a3df2c`) |
|---|---|---|
| `public_export.py export` | root commit equals R minus EXCL (7 files, the same EXCL digest as run 2), 6,378 files | the same |
| `gitleaks git` on the root commit | the 12 accepted findings | the same |
| `public_export.py fingerprint --accept` | second commit changes only `.gitleaksignore`; tag `v0.1.0` on it | the same |
| `gitleaks git` again | no leaks | no leaks |
| home path, maintainer e-mail, the masked account name | 0, 0, 0 files | — |
| `tools/check_unicode.py`, `mkdocs build --strict` | clean, passes | — |
| the exported full suite (`-n 8`, queue) | 1 failed, 11,598 passed: the new notice-registry test read the left-out `AgentHarm-LICENSE.txt` (fixed in `25a3df2c`) | **0 failed**, 11,599 passed, 155 skipped (6 min 48 s); the tree stayed clean |
| macOS bundle report | `ok`; `versions` 0.1.0 / 0.1.0; `source.commit` = the `v0.1.0` tag commit, `tree_clean: true`; Open Anyway wording (built with run 2's `gui/` environment, so it checks the report fields, not a release bundle) | — |

Every step of Phase B now passes on the branch. What stays open is outside it: the restricted Inspect fixtures (33
skipped tests, section 4), the Linux and Windows bundles (F-8, a network yes) and the real release commit R.

Scratch added by the re-rehearsals (for cleanup, nothing deleted): `rehearsal-2026-10-29/run-3/` and `run-4/` (each a
public tree with its `.venv`, the proof file and logs; run 3 also a bundle work tree).

## 8. Re-rehearsal at `origin/main` `df5cc4ae` (2026-10-29, after D-1000 and the snapshot fix)

Main then held the landing page (`site/`, `pages.yml`, MkDocs building to `_site/docs`, D-1000) and the `stage_owner`
fix. Steps 8–12 were run with the helper at R = `df5cc4ae`, offline, through the queue (`--class import --cpu 4`). A
placeholder no-reply address was used. Scratch: `$AGENTPROV_HOME/release/rehearsal-df5cc4ae/`.

| Check | Result |
|---|---|
| `public_export.py export` | root commit equals R minus EXCL: 6,421 files, the same 7 excluded; listing digest `sha256:eee46d0e…` |
| `site/` in the export | 24 files, `ls-tree` entries identical to R's; `pages.yml` and `mkdocs.yml` present |
| `gitleaks git` on the root commit | the 12 accepted findings (`generic-api-key`) |
| `fingerprint`: candidate, then `--accept` | second commit changes only `.gitleaksignore`; annotated tag `v0.1.0` on it |
| `gitleaks git` again | no leaks |
| `gitleaks dir --redact` | 36 hits in 18 files, the same count as before (P-6 / S-5 triage still open) |
| home path, the maintainer's personal e-mail, this machine's account name | 0, 0, 0 files; the `S1-dependents.jsonl` mask is present; 53 distinct account-path names (54 before the mask) |
| `tools/check_unicode.py`, `agentprov info`, `uv lock --check` (core, `gui/`) | clean; 0.1.0 with the expected format axes; both current |
| exported full suite (`-n 4`, queue) | **0 failed**, 11,638 passed, 155 skipped (9 min 42 s); the tree stayed clean |
| Pages build as `pages.yml` | `mkdocs build --strict` into `_site/docs`, then `site/` copied to `_site/`: passes, with no root `index.html` before the copy; every relative `href` and `src` of the landing page resolves in `_site`. The workflow's own environment (`uv sync --frozen --only-group docs`, then `mkdocs build --strict`) also builds |

No new finding. The Linux and Windows bundles (F-8) and the restricted Inspect fixtures are still open, as before.
