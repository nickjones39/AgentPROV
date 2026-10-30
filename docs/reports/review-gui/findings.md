# GUI review: security and correctness of `gui/` (session "AgentPROV GUI security review")

Branch `review-gui`, own worktree. The review ran at origin/main `3a7896d4`. The fixes are on top of origin/main
`4f501cba`, which includes gui-build-3 `fe399912` (the Revalidate action); that surface was read as well.

Scope: the desktop GUI, about 6k lines under `gui/src/agentprov_gui`: the G1 viewer, the G2 job runner and the D-440
macOS chrome. The rules are design.md §1, §2.2, §4, §8.3a, §8.4 and §11 (S1–S15); macos-design.md §10 (S15); and
D-390..D-399, D-432, D-440..D-449, D-544 and D-545. The accepted deviations 1–25 in build-log.md were not reported.

Method (first wave): a Workflow with six read-only reviewers, one per area:
- G-A: untrusted display;
- G-B: the job manager;
- G-C: the read-only guarantee and the D-391 allowlist;
- G-D: settings and paths;
- G-E: the macOS chrome;
- G-F: secrets.

Every candidate went to its own adversarial verifier. The verifier tried to refute it, and kept it only when a run
reproduced it, quoting the output. All runs were offscreen, with a scratch `AGENTPROV_HOME` and no network; no real
corpus was touched. Of 46 candidates, 45 were reproduced and 1 was refuted. After merging duplicates across areas,
that leaves 40 findings, GR-1..GR-40. A second adversarial wave over the fixes added GR-41..GR-70 (see below). All 70 are fixed in `gui/`, except GR-70, which is routed to the GUI build session. GR-34 and GR-35 also have core parts that are routed.

The verifiers' repro scripts are kept outside the repository, in `~/.agentprov/migration-work/review-gui/repro/<area>-<n>/`.
The `<area>-<n>` tags are given in the table. Each fix carries a gui test that fails before the fix, which is the durable
reproduction. Severity is the verifier's re-assessment. The input that triggers each finding comes from one of: a
hostile corpus, a log, the user's own form input, or files under `$AGENTPROV_HOME/gui/` (mode 0700, same user).

## Summary

- **No finding allows rich text from data, a network import, a GUI write into a corpus, or an API key in argv.**
  - Every markup-capable sink is fed through `ui/safe.py`.
  - Every corpus read uses the strict core opener, which follows no links and caps sizes.
  - The only GUI-side writes are under `$AGENTPROV_HOME`.
- **Security findings: 16, all low or info.** They fall into five groups:
  - argv construction can carry refused or tier-raising options through other routes (GR-1, GR-2);
  - persisted `job.json` and batch files are trusted on resume and at start (GR-3, GR-4);
  - three helper subprocesses inherit the full environment (GR-5);
  - three S2/S3 display gaps (GR-6..GR-10);
  - several lint and guard gaps (GR-11..GR-16).
- **Asked explicitly:**
  - *Can the GUI write a corpus directly?* No (G-C).
  - *Can it run `--release` with the conformance skip?* Yes, through Additional options (GR-2). The CLI refuses the
    pair with exit 2, but the GUI's own guard is bypassed.
  - *Can a dev-run prune delete outside `dev-runs/`?* Only when `dev-runs/` itself is a symlink: then it deletes inside
    the link's target. It can also delete non-run folders in `dev-runs/` and a busy run (GR-25, GR-26).

## Findings

| GR | area | severity | file:line (at review) | reproduction | status |
|---|---|---|---|---|---|
| GR-1 | G-B/G-F | low, **security** | `jobs/commands.py:327-361` (`build_spec`, `_text`) | G-F-1: a positional or list field value `--log-content`, `--show-content` or `--log-file X` becomes a CLI flag; core `build_parser().parse_args` gives `log_content=True` (S2 refusals bypassed; content excerpts reach the job log) | fixed 09324529 |
| GR-2 | G-B | low, **security** | `jobs/commands.py:42,363-375` | G-B-3: `--skip-prov-conformance` typed in Additional options is accepted with `--release`, without the §8.3a warning and without the job note. `--release` with `--limit=5` or `--select=…` passes the release filter check (exact-token compare). `--control-file` is not refused | fixed f90ccb1b |
| GR-3 | G-B | low, **security** | `ui/runs.py:459-473` (`resume`) | G-B-2: resuming a purge reuses the stored `--yes`, so there is no typed 8-hex check. The tier is taken from `job.json`, not recomputed. G-B-9: resuming a raw CI job puts the CLI in front of the python argv | fixed d33be7b0 |
| GR-4 | G-B | low, **security** | `jobs/batch.py:47` (`BatchStep.from_json`), `manager.py:213` | G-B-5: a planted `gui/batches/*.json` runs at GUI start with no confirmation. `extra.raw` runs any program. An agentprov step runs with `--show-content`, `--allow-network` and `--fetch` at the file's tier R0 (needs same-user write to the 0700 directory) | fixed 574ab7dc |
| GR-5 | G-F/G-B | low, **security** | `ui/mainwindow.py:191`, `ui/runs.py:596`, `about.py:43` | G-F-0: the `--version` probe, `queue_status.py` and `git` inherit the whole environment (`*_API_KEY`, `UV_*`), against §4.2/S8. Job spawns and `cli_options` are correct | fixed 7d483d6d |
| GR-6 | G-E | low, **security** | `ui/mainwindow.py:170`, `platform/macos.py:239-251,84` | G-E-3: the notification body carries `job.command` and `job.outcome` from job files unescaped; a U+202E or LF reaches `UNNotificationContent` (S15: only escaped ids cross) | fixed 3a1732fb |
| GR-7 | G-A | low, **security** | `ui/package.py:281` (`_preconditions`) | G-A-6: `corpus.json` `partial` and `release` are shown raw. A string with LF forges precondition lines ("partial: False (must be false)"); bidi controls pass (S3, S9) | fixed e1747f19 |
| GR-8 | G-A | low, **security** | `ui/detail.py:200-208` (`ProvJsonTab._summary`) | G-A-0: free text in `prov:type` or `apv:rule` is shown in the statement row while Show content is off; the attribute rows hide the same value (S2) | fixed c2780227 |
| GR-9 | G-A | low, **security** | `ui/detail.py:214`, `ui/graphview.py:209-213` | G-A-3: content shown in the PROV-JSON tree, the popover and the inspector is not fenced by `quote_untrusted`, and Cmd+C copies it unfenced (S2, S13) | fixed 062e8669 |
| GR-10 | G-A | low, **security** | `ui/graphview.py:489` and the popover hide paths | G-A-2: the hover popover stays on screen after the mouse leaves, after a tab or page switch, and after Show content is turned off (S2) | fixed 43791049 |
| GR-11 | G-A | low, **security** (lint gap) | `gui/tests/test_lint_safe.py:17` | G-A-8: the S1 lint misses `QProgressDialog` (AutoText label), `QErrorMessage`, `QStaticText` (AutoText), `WhatsThisRole`, `set*WhatsThis`, `fromHtml` and `QSystemTrayIcon`. No current use | fixed 6b86975e |
| GR-12 | G-C | low, **security** (lint gap) | `gui/tests/test_core_allowlist.py:36`, `_ast_support.py` | G-C-1: `import agentprov.corpus` plus attribute access, an alias chain, or `importlib.import_module("agentprov.cli")` passes all three D-391 tests. No current use | fixed 97e9f24c |
| GR-13 | G-C | low, **security** (lint gap) | `gui/tests/test_no_network.py:49` | G-C-2: `importlib.import_module("socket")` after psutil is attributed to psutil by the `__import__` hook, and the static half sees only `importlib` (S11). No current use | fixed 0b5580db |
| GR-14 | G-C | low, **security** (lint gap) | `gui/tests/test_lint_native.py:16` | G-C-3: `ctypes`, `cffi`, `shiboken6` and string imports of `objc`/`AppKit` outside `platform/` pass the S15 lint. No current use | fixed f1100008 |
| GR-15 | G-F | low, **security** | `gui/tools/screenshots.py:28,34-78` | G-F-2: the leak guard misses `AIza…`, `hf_…`, `github_pat_…`, Bearer/JWT and 40-character AWS secrets. It does not read QGroupBox titles, QTextEdit, tree children, header sections or the native subtitle. Nothing has leaked | fixed abb5fa69 |
| GR-16 | G-F | info, **security** | `app.py:53-62` | G-F-3: the S12 "key redaction filter" on `gui.log` does not exist. Latent: the GUI holds no key before G3 | fixed 77123099 |
| GR-17 | G-B | medium | `jobs/manager.py:392` (`kill`) | G-B-0: Force Kill of a queued job SIGKILLs the `suite_queue.py` wrapper's group only. The CLI (its own session) keeps running and writing while the GUI shows the job as ended, and the identity check then refuses further kills | fixed 6d00c336 |
| GR-18 | G-B/G-D | medium | `jobs/manager.py:289` (`spawn`), `jobs/batch.py:141`, `ui/runs.py:329` | G-B-1, G-D-3: an `OSError`/`ValueError` from `Popen` escapes the Qt slot and leaves a job directory marked "unobserved". A batch step retries every second and leaves one more directory each tick | fixed 90c4fc2c |
| GR-19 | G-D | low | `jobs/devrun.py:154-158` (`queue_prefix`) | G-D-2: with the `uv run --project` CLI fallback (no `.venv`), queued jobs still start `<checkout>/.venv/bin/python` and fail with `FileNotFoundError` | fixed 14ef4b5e |
| GR-20 | G-B/G-D | medium | `jobs/commands.py:336-346` | G-B-4, G-D-1: a `~` or relative form path is written by the CLI inside the job directory, while the single-writer and lock checks and Open in Viewer resolve it against the GUI's cwd | fixed 8f6af776 |
| GR-21 | G-D | low | `paths.py:20`, `jobs/manager.py:195` | G-D-0: a relative `AGENTPROV_HOME` gives the child relative job-file paths with cwd set to the job directory; progress, log and summary go elsewhere | fixed 6e87fcb0 |
| GR-22 | G-A | medium | `ui/detail.py:223` (`ProvJsonTab._toggle`) | G-A-1: Show content on a 4 MB JCS document (one line) blocks the UI thread for about 9 s, and each horizontal scroll step for about 3 s | fixed ef8e847c |
| GR-23 | G-A/G-C | medium | `ui/package.py:143-145`, `_show` | G-A-4, G-C-4: a 1 s timer re-sets every step's text, so scroll and selection reset and the datasheet is unreadable past the first screen. Each tick re-reads `corpus.json`, `DATASHEET.md` (2 GiB cap) and `WITHHELD.json` on the UI thread (§2.3) | fixed e61774ce |
| GR-24 | G-B | low | `jobs/manager.py:367` (`_stale_lock`) | G-B-6: the stale-lock report never fires for queued or `uv run` jobs: the lock holds the CLI's pid, `job.pid` is the wrapper's | fixed a37b5668 |
| GR-25 | G-B/G-D | low | `ui/runs.py:466,554-556` | G-B-7: Resume drops the record's `devrun` key, so the next dev run prunes the folder under the running resumed job. G-D-4: a run whose batch still has pending steps is pruned too | fixed d59950a1 |
| GR-26 | G-D | low | `jobs/devrun.py:212` (`prune`) | G-D-5: `RUN_DIR_RE.match` is a prefix match, so `20150101T000000Z_my_notes` is deleted. Folders without `devrun.json` count as runs. A symlinked `dev-runs/` is followed. `-10` sorts before `-2` | fixed 64ca7c2a |
| GR-27 | G-B | low | `ui/runs.py:349`, `jobs/follow.py` | G-B-8: each followed job keeps `progress.jsonl` open for the window's lifetime; at a 256-fd soft limit a long batch hits EMFILE (then GR-18) | fixed 98c04584 |
| GR-28 | G-A | low | `ui/runs.py:423` (`_dashboard`) | G-A-5: the stderr tail is re-set every 250 ms or 1 s and scrolls to its oldest line, so the newest lines (the error) cannot be read | fixed a3227678 |
| GR-29 | G-A | low | `ui/viewer.py:501`, `ui/graphview.py:334` | G-A-7: the graph popover and inspector always use 500 characters and ignore Settings › Viewer content limit | fixed 873a5af8 |
| GR-30 | G-D | low | `ui/settings_panes.py:126` (`budget_env`) | G-D-6: a memory budget of `nan` or `inf` passes to `AGENTPROV_JOB_MEM_GIB_BUDGET` and disables the queue's memory admission for GUI jobs. `²` passes the CPU `isdigit()` check | fixed a2f0aa29 |
| GR-31 | G-D | low | `ui/settings_panes.py:34,57,86,96`, `jobs/devrun.py:96`, `ui/runs.py:328` | G-D-7: a corrupted settings value (string, NaN/Infinity, ≥ 2^31, wrong JSON type) crashes the Settings dialog, Dev Run and every heavy job start, with no way to fix it in the app | fixed 447c8030 |
| GR-32 | G-D | low | `ui/mainwindow.py:95-101,333` | G-D-8: after a Settings change of the checkout or the Compute budgets, jobs still run the old CLI until restart, while About shows the new checkout | fixed 7ce989d4 |
| GR-33 | G-D | low | `ui/settings_panes.py:53-66,145-166`, `jobs/manager.py:410-431` | G-D-9: Settings › Jobs (retention, continue-on-failure) and Settings › CI target are saved but never read; job retention (§4.1) is not built and is not listed as a deviation | fixed 43cbaae1 |
| GR-34 | G-C | low | `readmodel/corpus.py:20` (transitive through `agentprov.corpus`) | G-C-0: importing the GUI loads `agentprov.corpus.writer`, `io.workers`, `raw.*` and `host` (55 non-allowlisted core modules). The D-391 check is purely syntactic. Root cause in the core's eager `corpus/__init__.py` re-export | gui test pin fixed 0cd4726f; core part fixed on pipeline-perf (2026-10-21): lazy re-exports in `corpus/__init__.py` and `raw/__init__.py`, lazy `raw.members` in `corpus.reader`/`corpus.register`; design §2.2 amended; the strict xfail removed |
| GR-35 | G-C | low | `readmodel/corpus.py:70` (`summarise`) | G-C-5: discovery reads each `corpus.json` up to 2 GiB (twice) on the UI thread before the 64 MiB JSON limit applies (core `_sealed_flag`/`read_document`) | gui part fixed 494e6e69; core part fixed on pipeline-perf (2026-10-21): `_sealed_flag` and `read_document` open under `max_json_bytes` (`corpus.reader.json_document_limits`) |
| GR-36 | G-C | low (test gap) | `gui/tests/_corpus_support.py:46` (`tree_state`) | G-C-6: the read-only tests record only regular files inside the tree. Created directories and siblings of the tree (sidecars) go unseen, and the default layout-cache placement is never exercised | fixed 48757989 |
| GR-37 | G-E | low | `platform/macos.py:48` | G-E-0: `_UNIFIED = 1` is `NSWindowToolbarStyleExpanded`, not `Unified` (3), so the window gets a separate title row (80 pt of chrome, against 52 pt). D-440 and macos-design §2.6 require unified | fixed 9cd33346 |
| GR-38 | G-E | low | `platform/macos.py:327` (`install`) | G-E-1: an exception after `setToolbar_` leaves the native toolbar attached with a released delegate (dead buttons) next to the Qt fallback toolbar | fixed f73c570b |
| GR-39 | G-E | low | `platform/macos.py:239-256` (`_notify`, `signed_bundle`) | G-E-4: notification authorisation is never requested, so a signed `.app` shows nothing. Every request has the identifier "Job finished", so the newer one replaces the older. A framework `Python.app` counts as signed | fixed 300af912 |
| GR-40 | G-A | info | `ui/mainwindow.py:368`, `ui/jobdialog.py:60` | G-A-9: `[*]` in a corpus name or job label disappears from the window title (Qt's modified placeholder) | fixed acdf82bf |

### Refuted

- G-E-2: "`requestUserAttention_(0)` is a critical (continuous) Dock bounce." The value is right, but Qt's own
  `QApplication.alert` sends the same request (disassembled `libqcocoa.dylib`), and macos-design §6 names that as the
  fallback. Only the source comment (`# NSInformationalRequest`) is wrong.

## Second wave: adversarial check of the fixes

Six checkers, one per fix group (argv, processes, display, lints, settings, macOS), tried to bypass each fix, looked
for regressions and checked for gaps that were still open. Each claim went to an independent confirmer. Of 32 claims, all
32 were reproduced. Four were regressions or new bugs introduced by first-wave fixes: GR-41, GR-42, GR-43 and GR-44.
One was routed (GR-70). The rest were fixed as GR-41..GR-69, again one commit each with a failing-first gui test. Their
scripts are in `~/.agentprov/migration-work/review-gui/fixcheck/`. The "fixes" column names the first-wave finding the
issue follows from, and the issue kind.

| GR | fixes | severity | file:line (at check) | reproduction | status |
|---|---|---|---|---|---|
| GR-41 | GR-24 (new-bug) | low | `jobs/manager.py:202` | fixcheck/confirm-procs-0: A lock with a non-positive pid makes _pid_alive raise ValueError; RunsPage (and so the main window) cannot be built, on every start | fixed 933c7893 |
| GR-42 | GR-6 (regression) | low | `platform/macos.py:90` | fixcheck/confirm-display-4: Subtitle and notification text are escaped twice: '<U+202E>' from the caller's T.line becomes '<U+003C>U+202E>' | fixed b66a3631 |
| GR-43 | GR-16 (new-bug) | low | `app.py:70` | fixcheck/confirm-lints-0, fixcheck/confirm-lints-1: RedactingFilter calls record.getMessage() unguarded: once any secret is registered, a malformed log call raises into the caller / Exception tracebacks (exc_info) carry registered secrets into gui.log unredacted | fixed 5c3e09fa |
| GR-44 | GR-27 (regression) | low | `ui/runs.py:91` | fixcheck/confirm-procs-4: Follower.finish() folds the whole progress.jsonl in one call on the UI thread, so selecting a large ended job freezes the GUI for seconds | fixed 04965d10 |
| GR-45 | GR-3 (bypass) | low | `jobs/commands.py:117` | fixcheck/confirm-argv-0: Local CI tool job: argparse abbreviations (--allow-net, --allow, --a) turn on the network while the GUI computes tier R1 (no network consent box); a second -C points the run at another checkout | fixed dc3c6ee8 |
| GR-46 | GR-3 (incomplete) | low | `jobs/commands.py:456` | fixcheck/confirm-argv-1: resume_spec does not check that the recorded argv starts with the form's words: a planted job.json with command 'info'/'stats' resumes an import, a package seal or a backends build at R0, and confirm() then shows no dialog at all | fixed 7ee0c37c |
| GR-47 | GR-20 (incomplete) | low | `jobs/commands.py:389` | fixcheck/confirm-argv-2: Additional options '--out /x' (derive, recompute) or '--corpus /x' (import, package seal) change the corpus the CLI writes, but JobSpec.writes keeps the form field, so the single-writer and lock checks look at the wrong tree | fixed 5d3d9a62 |
| GR-48 | GR-4 (incomplete) | low | `jobs/batch.py:76` | fixcheck/confirm-argv-3: A planted batch step that records tier R2 still runs --fetch --allow-network --i-consent-to-large-download at GUI start with no confirmation | fixed a3c0fcd6 |
| GR-49 | GR-24 (incomplete) | low | `jobs/manager.py:425` | fixcheck/confirm-procs-1: The stale-lock notice disagrees with the core's own staleness test: a live holder that reuses job.pid, and a pid above the maximum, are both reported stale | fixed dacd5f3a |
| GR-50 | GR-21 (incomplete) | low | `jobs/manager.py:240` | fixcheck/confirm-procs-2: Only AGENTPROV_HOME is made absolute: a relative AGENTPROV_SUITE_QUEUE_DIR gives every queued job a private queue in its own job dir, and the Sessions tab's queue_status.py resolves a relative home against the checkout | fixed 07cd8c44 |
| GR-51 | GR-18 (incomplete) | low | `jobs/manager.py:135` | fixcheck/confirm-procs-3: A relative or '~' checkout is still not normalised: the job is refused with gui.spawn.failed, or the CLI is reported missing | fixed aa47b1e9 |
| GR-52 | GR-18 (incomplete) | low | `jobs/manager.py:321` | fixcheck/confirm-procs-5: A UnicodeEncodeError from writing job.json (a path that is not UTF-8 or holds a lone surrogate) escapes spawn outside the new try, leaves an empty job dir, and is not caught by RunsPage.start | fixed 175250d1 |
| GR-53 | GR-9 (incomplete) | low | `ui/detail.py:229` | fixcheck/confirm-display-0: PROV-JSON tree keeps fenced content on screen after Show content is turned off (collapsed statements and escaped attribute names are skipped by _toggle) | fixed 7630321a |
| GR-54 | GR-23 (incomplete) | low | `ui/package.py:268` | fixcheck/confirm-display-1: Package timer still re-reads corpus.json (4 opens per tick) and runs 2 git processes per tick on step 0, the landing step; step 4 reads corpus.json twice per tick | fixed cd9d9f86 |
| GR-55 | GR-8/GR-9 (incomplete) | low | `text.py:167` | fixcheck/confirm-display-2: Free text typed as prov:QUALIFIED_NAME / xsd:anyURI / xsd:dateTime, or placed in a prefix value, is shown unfenced while Show content is off (PROV tree and graph popover/inspector) | fixed 8551d838 |
| GR-56 | GR-40 (incomplete) | low | `ui/jobdialog.py:61` | fixcheck/confirm-display-3: Confirm dialog title takes spec.label without T.line, so bidi/isolate/NBSP code points from a corpus directory name reach the window title | fixed 6ff59ef4 |
| GR-57 | GR-28 (incomplete) | low | `ui/runs.py:458` | fixcheck/confirm-display-5, fixcheck/confirm-display-7: Kept stderr scroll value points at different lines once the 64 KiB tail window slides (the user's reading position drifts) / Runs stderr pane (NoWrap) still lays out one escaped 512K-char line: about 2 s UI stall when selecting a job | fixed 3478e0f8 |
| GR-58 | GR-22 (incomplete) | info | `text.py:135` | fixcheck/confirm-display-6: The 're-indented for display' copy also reorders keys and reformats numbers, so it is not the file text with whitespace changed | fixed 66b63448 |
| GR-59 | GR-11 (incomplete) | low | `gui/tests/test_lint_safe.py:26` | fixcheck/confirm-lints-2: S1 lint still allows two markup-capable Qt APIs: QToolBox.setItemToolTip and QSplashScreen.showMessage | fixed fc5ad9c3 |
| GR-60 | GR-13 (incomplete) | low | `gui/tests/test_no_network.py:31` | fixcheck/confirm-lints-3: psutil's tolerated socket import re-exports socket: `from psutil._common import socket` passes both the static and the dynamic S11 check | fixed e244062b |
| GR-61 | GR-12 (incomplete) | low | `gui/tests/_ast_support.py:17` | fixcheck/confirm-lints-4: pkgutil.resolve_name and runpy.run_module import by string past the static D-391 allowlist and the static S11 check | fixed 9eac19e6 |
| GR-62 | GR-36 (incomplete) | low | `gui/tests/_corpus_support.py:55` | fixcheck/confirm-lints-5: tree_state ignores permission bits, so a chmod under the corpora root passes the read-only tests | fixed c6330f50 |
| GR-63 | GR-15 (incomplete) | info | `gui/tools/screenshots.py:30` | fixcheck/confirm-lints-6: AWS-secret leak shape misses a key next to '/' or '+' (its boundary class includes them) | fixed f7d7d0b5 |
| GR-64 | GR-31 (incomplete) | low | `ui/runs.py:317` | fixcheck/confirm-settings-1: A stored Compute default --jobs of 2^31 or more still crashes Runs › New Job (OverflowError in QSpinBox.setValue) | fixed 6a2cba3a |
| GR-65 | GR-31 (incomplete) | low | `ui/settings_panes.py:154` | fixcheck/confirm-settings-2: Deeply nested JSON in a stored setting still crashes MainWindow start-up (compute/settings) and the Dev Runs pane/dev run (devrun/settings) with RecursionError | fixed 67e0dff1 |
| GR-66 | GR-31 (incomplete) | low | `settings.py:85` | fixcheck/confirm-settings-3: Other settings keys: a NUL character in paths/checkout or paths/corpus_roots crashes MainWindow at start-up (ValueError) | fixed 09ba31fc |
| GR-67 | GR-39 (incomplete) | low | `platform/macos.py:300` | fixcheck/confirm-macos-0, fixcheck/confirm-macos-1: Authorisation is requested only when the first notification fires, so that notification always becomes a Dock bounce, even for a user who allowed notifications in an earlier session / A refusal is cached for the whole process: notifications enabled later in System Settings are ignored until restart | fixed 04f54368 |
| GR-68 | GR-20 (incomplete) | info | `jobs/commands.py:299` | fixcheck/confirm-argv-4: Relative or '~' paths are still accepted for path-taking options outside the form table: validate --aer/--store and --licence-file NAME=PATH | fixed 9efe0cf6 |
| GR-69 | — | low (test hygiene) | `gui/tests/test_g2_pages.py` | a test left a top-level ViewerPage open (offscreen, it caught later mouse events) | fixed 360de1cb |
| GR-70 | GR-32 (regression) | low | `ui/mainwindow.py` (Settings OK) | fixcheck/confirm-settings-0: after Settings OK changes the checkout, the pending steps of an already-confirmed batch, dev runs included, run the new checkout's CLI | routed to the GUI build session: its queued batch guard records the checkout path, HEAD and dirty state when a batch starts, and blocks later steps on any change |

## Routed outside `gui/`

- **GR-34 (core, pipeline-perf after D-416).** `src/agentprov/corpus/__init__.py` re-exports `CorpusWriter`
  eagerly, so importing `agentprov.corpus.reader` loads `corpus.writer`, `io.*`, `raw.*` and `agentprov.host` into the
  GUI process. Proposed: a lazy re-export (a module `__getattr__`) or dropping it. Then either amend design §2.2 to
  accept `raw.store/members/origins` and `io.*` as transitive dependencies of `CorpusReader`, or make `raw/members.py`
  import `io.atomic`/`io.workers` lazily. Test: `gui/tests/test_review_core_loaded.py::test_corpus_writer_not_loaded`
  is a strict xfail that will XPASS once the re-export is lazy; remove the xfail then.
- **GR-35 (core, pipeline-perf after D-416).** `corpus/reader.py` `_sealed_flag` and `CorpusReader.read_document`
  read JSON documents under `max_artefact_bytes` (2 GiB) before the 64 MiB JSON limit applies. Proposed: open them with
  `max_artefact_bytes` capped at `max_json_bytes`. The GUI already passes the tighter limits
  (`test_review_manifest_limits.py`).
- **GR-45 (tools).** `tools/ci_local.py` builds its `ArgumentParser` without `allow_abbrev=False`, so `--allow-net`
  enables the network. The GUI now accepts only that form's exact option strings.
- **GR-30 (tools, optional).** `tools/suite_queue.py` `budget()` should itself reject non-finite or non-positive
  `AGENTPROV_JOB_MEM_GIB_BUDGET` and non-ASCII CPU budgets, because a shell export bypasses admission the same way.
- **GR-8 (core, optional).** A public rule-token helper in `render/style.py`, so the GUI no longer reads the private
  `_RULE_RE`.
- **Docs, for the GUI build session (build-log, design, README):**
  - deviation 25: re-measure after GR-37 (unified toolbar, about 28 → 52 pt), re-run the Cocoa smoke test and re-shoot
    the README screenshots;
  - record that job retention (§4.1), the Settings › CI default target and the batch continue-on-failure setting are not
    built (GR-33; the panes now say so);
  - S12's redaction filter exists (GR-16, GR-43); G3's keychain path must call `app.register_secret`;
  - macos-design §6: the interruption levels and the notification actions are not built; authorisation is requested at
    install time (GR-67);
  - design §19.1: "never while its batch is unfinished" (GR-25);
  - macos-design §10 S15: name the extended FFI set (GR-14).
