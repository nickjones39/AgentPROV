# AgentPROV desktop GUI: build log

Branch `gui-build` (session "GUI build"), from origin/main `7f8f8cb3`. The direction is D-390..D-399, D-432 and
D-440..D-449 ([`design.md`](design.md), [`macos-design.md`](macos-design.md)). User decision 2026-10-14: the G1–G2
build starts before the regeneration round; G3 and later are unchanged (D-390 amendment).

Machine: Apple M2 Max (12 cores), 32 GiB, macOS 27. Measurements are offscreen (`QT_QPA_PLATFORM=offscreen`, about 2×
slower than native cocoa for paints, research §M5b) unless stated.

## G1: MVP viewer (done)

### What is built

`gui/` is a separate uv project (`agentprov-gui`, package `agentprov_gui`, Python ≥ 3.14, its own `uv.lock`):
PySide6-Essentials 6.12.0, psutil 7.2.2, the core as an editable path dependency, plus pytest, ruff and mypy.

| Part | Modules | Notes |
|---|---|---|
| Display text (S2, S3) | `text.py` | `line` (one-line `escape_untrusted_line`, cached), `clean` (no double escaping of CLI output), `fenced` / `fenced_full` (`quote_untrusted`), the content placeholder, and the content-vs-identifier classification of PROV values |
| Safe widgets (S1) | `ui/safe.py` | `SafeLabel` (plain text that cannot be switched to rich text), `safe_message_box`, `safe_tooltip` / `set_tooltip`, `ReadOnlyText`, `SafeForm`, `is_tooltip_role` |
| Read model (no Qt) | `readmodel/corpus.py`, `executions.py`, `detail.py` | discovery and summaries; the column table; the full row check on open; per-execution documents; validation and register lookup by binary search; LRU (64 entries or 256 MiB) |
| Graph (no Qt) | `graph/viewgraph.py`, `emit.py`, `dotjson.py`, `layered.py`, `layout.py` | overlay and full views; trusted-grammar DOT; `dot -Tjson` under the G.8.6 controls with a strict parser; layered engine (b); a digest-keyed layout cache in `$AGENTPROV_HOME/gui/cache/layout/` |
| Graph (Qt) | `graph/scene.py`, `ui/graphview.py` | native items, LOD tiers, an overview raster painted from layout data in a worker, bundle toggles, evidence filter, hover popover, inspector, search, k-hop focus, pinch and smart zoom, the Elements list |
| Viewer | `ui/viewer.py`, `ui/detail.py` | corpora list, G.8.6 banner, executions table (model-side sort and filter, pickers, id filter), tabs: Graph, PROV-JSON, AER, SEM, Register, Validation, Raw (artefact list only) |
| Window | `ui/mainwindow.py`, `ui/dialogs.py`, `ui/theme.py`, `settings.py`, `about.py`, `app.py`, `ui/worker.py` | sidebar navigation; menus with native roles (About and Settings… go to the App menu on macOS; ⌘,); Settings (paths, appearance, viewer limit); About (§6.8); follow-system / light / dark; text size 85–200 %; single-instance `QLockFile` (S10); `gui.log` 4 × 1 MiB (S12); core dumps off |

Run it: `uv run --project gui agentprov-gui [CORPUS]`.

### Exit criteria

| Criterion | Result |
|---|---|
| agentdyn-a-p10 (38,281 rows) opens in ≤ 3 s, read-only | **1.07 s** (`tests/test_real_corpus.py`, from the request to a filled table; 1.53 s in an earlier smoke run). Read-only: no write and no lock (the top-level entries' sizes and mtimes are unchanged; the synthetic-corpus tests hash every file before and after) |
| The largest document's graph is interactive | `ex_uxnvl53glmqbvlufuhg67vzjog` (3.68 MB PROV-JSON, 2,422 nodes and 7,387 edges in all-bundle mode). Default view (core layout by `dot` plus overlays): **1.43 s** from selection to a drawn graph, of which `dot` is 0.24–0.48 s (cached afterwards); frames of **5–11 ms** at 30 %, 60 % and 130 % zoom. Full layered layout: layout 0.07 s, build 1.4 s, frames 0.09 s below 50 % zoom and 0.3 s above it |
| S1, S2, S5, S11 tests green | `test_lint_safe.py` (S1), `test_viewer.py::test_content_hidden_by_default` and `test_text.py` (S2), `test_graph_security.py` (S5), `test_no_network.py` (S11); plus the D-391 allowlist (`test_core_allowlist.py`) and S7 (`test_env_guard.py`) |
| No core change | `src/agentprov/` is unchanged. Outside `gui/`: two D-391 rules in `tests/boundary/test_import_boundary.py`, `gui/uv.lock` in the CI osv-scanner list (the hygiene test requires every lock there), this log, and the D-390 amendment |

Gates on the G1 commit: gui tests 49 passed, 1 skipped (the real-corpus test, which runs only with
`AGENTPROV_GUI_REAL_CORPUS`); ruff and mypy (strict) clean for `gui/`; `tools/check_unicode.py` clean; the core full
suite through `tools/suite_queue.py` (result below).

### Other measurements (agentdyn-a-p10, read-only)

| Step | Time | Note |
|---|---|---|
| `CorpusReader.iter_index` (the core reader) | 16.4 s | 55 % JCS re-encoding, 37 % `IndexRow` validation: the reason for deviation 2 |
| GUI table load (strict loader, columns) | 1.84 s | same opener, same strict JSON loader |
| sort 38k rows by status / filter by id | 17 ms / 6 ms | model-side |
| full row check of one row on open | 9 ms | `IndexRow.from_json` + canonical line |
| execution detail (AER, SEM, PROV, validation row, register rows) | 20–100 ms | the largest document: 0.5 s read + 1.1 s `build_model` (validation) |
| `reader.register()` / `reader.validation_results()` | 24.9 s / 2.5 s | not used: deviation 3 |
| RSS: window / + table / + detail and default graph / + full graph of the largest document | 125 / 161 / 210 / 275–315 MiB | budget ≤ 300 MiB (design §10); 612 MiB before the BSP depth cap (deviation 9) |

### Deviations from the design

Deviations 2 and 3 were sent to the pipeline-perf session as core reader performance findings (orchestrator,
2026-10-14). The GUI keeps its workarounds until the core reader is fast, then switches to the core API.

1. **`agentprov.errors` added to the D-391 allowlist.** The allowlisted readers raise `AgentProvError` subclasses; the GUI
   catches them and shows their closed `code`. It is a module of exception classes only.
2. **The executions table does not use `CorpusReader.iter_index`** (16.4 s for 38k rows). It reads `executions.jsonl`
   through the same strict opener (`CorpusReader.open_file`) and loader (`strict_json_loads`, record limits), checks
   sorted and unique `ex`, and keeps display columns and line offsets. The full H.3.1 check (`IndexRow.from_json` against
   the layout, plus the canonical-JCS line test) runs on the one row being opened, before any of its files is read. If
   `executions.jsonl` was replaced after the table was read (inode, size, mtime), opening refuses and asks for a
   reload. Table cells are display-only and escaped.
3. **Validation and register rows are looked up per execution by binary search** (both files are sorted by `ex` /
   `subject_key`), not by decoding the whole files (2.5 s and 24.9 s). The validation row's bytes must hash to the
   index's `digests.validation`; register lines are decoded by the core's `decode_register`.
4. **`dot -Tjson` runs through the GUI's own copy of the G.8.6 controls** (`graph/dotjson.py`; checked by
   `test_dot_process_controls`), because `render.dot.run_dot` does not accept `json` until D-397 lands (CLI robustness
   session). Switch to `run_dot(..., "json")` when it does.
5. **Layout runs in a worker thread with `subprocess`**, not a `QProcess` started from the UI thread. Same controls,
   simpler to test, and no Qt object outlives the job.
6. **PySide6 6.12.0, not ≥ 6.12.1.** 6.12.1 is not on PyPI (resolved 2026-10-14 with `exclude-newer` 2026-10-14). On
   macOS 27, QTBUG-150017 makes check-box indicators invisible in the `macos` style (D-441, D-447). **To do: bump to
   ≥ 6.12.1 when it is on PyPI, before any macOS 27 packaging (G5)** (orchestrator, 2026-10-14). `gui/pyproject.toml` has its own `exclude-newer` (2026-10-14), later than the core's 2026-10-07,
   because 6.12.0 was published on 2026-10-08.
7. **`dot` packs components** (`pack=true, packmode=graph`). Most core nodes of a large document are unconnected in the
   core bundle; without packing they stack into one column (1,130 × 13,317 pt for the largest document, 3,188 × 3,152 pt
   packed). This adds 0.7 s to the first, uncached layout of the largest document.
8. **The layered engine wraps tall ranks and grids isolated nodes** (rank height ≤ max(30, 1.5·√n)). Without this, the
   unconnected elements of the largest all-bundle document fill one rank 3,000 rows tall: a 19,768 × 196,460 pt drawing
   where every edge crosses the viewport.
9. **The BSP tree depth is capped at 10.** Qt chose depth 15 for the full layout of the largest document, and each long
   edge's bounding rectangle filled thousands of leaves: +315 MiB. Depth 10 costs +26 MiB with the same paint and
   hit-test times.
10. **One Python `paint()` override**, for straight edges (`ClippedLineItem`). Qt dashes a whole path before clipping it,
    so the long dashed and dotted edges of a layered layout cost 0.8 s per frame (0.13 s with solid pens). The item
    clips its line to the exposed rectangle and offsets the dash pattern, so it draws the same pixels. Below 50 % zoom
    (LOD "shapes") edges are drawn solid and arrowheads are hidden, as design §7.3 allows.
11. **The overview raster is painted from the layout data** (boxes and lines, no text) in a worker thread, not by
    rendering the scene, whose items belong to the UI thread.
12. **Popover:** a frameless `Qt.ToolTip`-type window holding a plain-text table (not a `QToolTip`); a click selects the
    node and fills the inspector panel ("pins" it, macos-design §5). Data values are hidden as `‹text, n chars,
    sha256:…›` until the graph tab's own Show content switch is on.
13. **What counts as content in PROV values:** a plain or `xsd:string` / language-tagged string that does not read as an
    identifier, locator, digest or rule id (`[A-Za-z0-9_.:@#/+-]{1,200}`). QNames, numbers, booleans and other typed
    literals are metadata and always shown (escaped). For AER records, a fixed set of structural members is always
    shown; every other member is content.
14. **The PROV-JSON tab's raw text pane is filled only when its Show content switch is on**, then shows the whole
    document fenced by `quote_untrusted` with no truncation: design §7.2 makes this tab the place to read the complete
    text.
15. **No `logging.handlers`:** it imports `socket` (S11). `gui.log` rotation is a small `FileHandler` subclass.
16. **Navigation in G1:** the Qt sidebar has the Corpora section only (Viewer); Jobs and Release come with G2. The
    macOS native chrome (D-440) is left for the end of G2, as the task allows. Settings has General, Appearance and
    Viewer panes.
17. **"Not verified" banner:** without a verify job record (G2), every corpus opened shows the G.8.6 banner.
18. **Test corpora:** the GUI tests build their corpus with the core's own helper `tests/unit/corpus/seal_support.py`
    (three golden AgentDojo logs, release mode), loaded from the repository. It is a test-only coupling to a core test
    helper.

## G2: job runner (built; gates below)

### What is built

| Part | Modules | Notes |
|---|---|---|
| Forms and tiers | `jobs/commands.py` | a declarative table of 13 forms (design Appendix A); the tier is computed from the final argv, so typed options raise it too; refused options (`--show-content`, `--log-content`, the environment-file option, the job manager's own files); release-mode filter rules; purge needs `sha256:` + 64 hex; the D-432 box per command (§8.3a and its addendum) |
| Job manager | `jobs/manager.py` | detached spawn (own session, environment allowlist, stdout/stderr as files, stdin `/dev/null`); `job.json` with pid + create time; re-attach; pid-reuse defence; `ended.json`; stale-lock report (never removed); one SIGTERM stop; identity-checked force kill of the process group; single writer per corpus and global slots (fetch cache, backend builds); `control.json` only when the CLI accepts `--control-file` (D-394); heavy jobs wrapped in `tools/suite_queue.py --class import --cpu N` |
| Followers | `jobs/follow.py` | tail reader (partial lines, 64 KiB line cap, 1 MiB per tick, rotation), progress 0.1 fold and 0.2 heartbeat snapshot, EWMA rates and the ETA range, log ring (50k) |
| Batches | `jobs/batch.py` | persisted, ordered, concurrency 1 by default, blocked after exit 4/70 unless continue-on-failure; advance only while the GUI is open |
| Dev runs | `jobs/devrun.py` | D-544: plan from the registry, per-part overrides, include/exclude, first-N (spread/random when the CLI has `--sample-mode`, D-529), the three steps through the queue, `devrun.json` with the CLI commit, retention of the last 5 |
| Pages | `ui/runs.py`, `ui/jobdialog.py`, `ui/logs.py`, `ui/system.py`, `ui/licences.py`, `ui/package.py`, `ui/settings_panes.py` | Runs (jobs, batches, dev runs, read-only sessions), New Job forms with argv preview and tier confirmations, Logs, System (1 Hz while visible), Licences (included and 708 excluded records), Package (9 steps), Settings › Jobs, Compute, CI, Dev Runs |

### Exit criteria

| Criterion | Result |
|---|---|
| Re-attach after kill | `test_jobs.py::test_reattach_after_the_gui_is_gone`: the GUI's manager is dropped while the fake CLI runs in its own session; a new manager re-attaches from `job.json` and observes the end from `summary.json`. Pid reuse, stale locks, SIGTERM stop (exit 130) and the identity check before a kill are tested too |
| Every R-tier dialog | R0 runs with the argv shown; R1 names what is written; R2 needs the tick box; purge needs the typed 8-hex check and then adds `--yes`; the conformance warning has "Keep the Check" as the default (`test_g2_pages.py`) |
| Package dry run → seal → verify → deposit → verify on a copy of `phase10k/trial/c2seal` | **Passed** on a copy of its working corpus `c2.partial` in `~/.agentprov/migration-work/gui-build/pkg/` (2026-10-14/15), every step a GUI job: dry run (exit 0; 642 executions; 327 objects and 1 execution to withhold); seal (exit 0; content `sha256:8283f5ee…`, root `sha256:f73a8507…`; 7.4 s of work after 5 h in the shared queue); `verify --level chain --release --root-digest` (exit 0; 642 executions, 2,270 files, 0 findings); deposit (first refused with `release.refused.scan_missing`, as designed: the release scan is a terminal step; after `tools/release_scan.py` with the trial's reviewed triage file (D-269) it built 5 archives, 7.6 MB); verify of the `.meta.zip` (exit 0; the data archives are not opened by a meta-only verify). The GUI's Package views showed the withholding counts (327 entries by reason and basis, 1 execution withheld whole, 4 rule ids; no value), the datasheet as plain text, the release scan, and the finish page's upload list with "Nothing has been uploaded" |
| Works with today's CLI and progress 0.1 | yes: `info`, `fetch`-free commands and `package`/`verify` write no progress events today, and the dashboard says so; the 0.2 heartbeat and `--control-file` are used when present |

Found and fixed by the end-to-end run: the CLI prints the seal's root digest on stderr, not stdout; WITHHELD.json's
members are `affected_executions`, `executions` and `policies[].rules`.

### Deviations from the design (G2)

19. **D-545 (S11):** `psutil` imports `socket` at module level (constants only); the fresh-interpreter S11 test tolerates
    `socket` only when `psutil` is its importer (user decision 2026-10-15: approved).
20. **The System sampler runs as 1 Hz pool tasks**, not in a page-owned `QThread`: a `QThread` destroyed while running
    aborts Qt (seen once in the test suite).
21. **Tiers:** `import --fetch` is R2, as in design §8.4, even though without `--allow-network` it reads the verified
    fetch cache offline (it may need a large-download consent); it takes the fetch-cache slot. The dev-run import step
    takes its tier from its argv the same way (corrected 2026-10-15: an earlier version of this log said R1).
22. **Heavy GUI jobs go through the shared job queue** (`--class import`, Settings › Compute, on by default), so a GUI
    job never starves a gate. In the end-to-end run each light job waited hours behind other sessions' work; the
    last three package steps (seconds each) were run directly.
23. **Not built in G2:** the macOS native chrome (D-440: PyObjC is a new download that needs the user's yes), the
    registry-picker batch dialog (dev runs cover sampled imports), and the Mac Studio CI target (no runner). The Local CI target runs `tools/ci_local.py` (D-462, on main since
    2e9c13a5) as a tool job from Runs › New Job; it queues itself in the shared suite queue. CI actions that change repository variables are not run by this session.
24. **Validate has no conformance box** (it is the check); recompute offers it only with `--out`; dev runs skip at the
    import step and validate `aer,sem,linkage` only (design §8.3a addendum).

## D-440: macOS native chrome (built 2026-10-15)

**Download (logged):** the user approved adding PyObjC 12.2.2 on 2026-10-15, both through the orchestrator and in this
session's window: `pyobjc-core`, `pyobjc-framework-Cocoa` and `pyobjc-framework-UserNotifications`, each with the
marker `sys_platform == 'darwin'`, in `gui/` only (never the core). `uv lock` read PyPI metadata (`exclude-newer`
2026-10-14); the three universal2 cp314 wheels were already in the local uv cache from the macOS design research, so
nothing was downloaded.

**Built:** `platform/macos.py`, the only module that imports PyObjC (S15):
- an `NSToolbar` (unified style, icon-only, autosaved), whose SF Symbol items trigger the same `QAction`s as the menus
  (Toggle Sidebar, Open Corpus, Reload, New Job, Dev Run); an `NSSearchToolbarItem` that feeds the Viewer's id filter
  only; an activity label with a fixed-format job count; the window subtitle (escaped ids only);
- the Dock badge (running jobs) and a Dock progress bar for the selected running job;
- notifications through `UNUserNotificationCenter` in a signed `.app` only, for jobs longer than 2 minutes that end
  while the app is not in front; a dev run falls back to a Dock bounce (`requestUserAttention_`);
- the Window menu (`NSApp.setWindowsMenu_` with Minimize, Zoom, Bring All to Front);
- the display flags (Reduce Transparency, Differentiate Without Colour, Reduce Motion, Increase Contrast) and their
  change notification. Differentiate Without Colour adds bundle letters ([C], [I], [A]) to the graph's full labels;
  Increase Contrast thickens node and edge strokes.

**Fallback:** the Qt toolbar with the same actions and a search field: on Windows and Linux, on macOS when Settings ›
Appearance › "native macOS toolbar" is off or `AGENTPROV_GUI_NATIVE_CHROME=0`, when PyObjC is missing, under the
`offscreen` or `minimal` platform plugins (a window id is not an `NSView` pointer there; treating it as one crashed the
test suite once), and when the smoke check fails.

**Deviation 25:** macos-design §2.6's smoke check "the content rect shrinks" does not hold: AppKit keeps the content size
and grows the window frame (measured on macOS 27 after GR-37: chrome above the content 28 → 52 pt with the Unified
style, content 552 pt unchanged; the first build passed `1`, which is the Expanded style with a separate title row, and
measured 76 pt). The check is
"the toolbar is attached and the chrome above the content grew". The toolbar identity is compared with `==` (PyObjC
proxies).

**Tests:** `tests/test_lint_native.py` (S15 lint; no rich text in the native module; fallback gating; the Qt toolbar
carries every action; accessibility flags change the graph); the Cocoa smoke test (opt-in:
`AGENTPROV_GUI_COCOA_TESTS=1`; passed 2026-10-15 on macOS 27: toolbar attached, every item mapped to a `QAction`,
Dock badge and progress set and cleared); `tests/test_no_network.py` now records every importer of `socket` and
accepts only `psutil` (D-545) and `objc._convenience` (D-448, macOS only), with AppKit, Foundation and
UserNotifications imported in the fresh interpreter.

**README screenshots** (re-shot 2026-10-15 with the native chrome, handed over by the finished README session):
`gui/tools/screenshots.py` builds the synthetic corpus, opens it through a relative root, shows the program as
`agentprov`, renders each window with AppKit (`cacheDisplayInRect`, so no screen-recording permission) and refuses to save
when visible text matches an account path, an e-mail address or a key shape. The re-shoot found and fixed: the window
title repeated the corpus name next to the native subtitle; form fields kept their size hint under the macOS style
(paths were cut); the dev-run plan stretched the Settings window to 2,000 pt (it wraps now); the executions pane showed
two rows by default.

**Not done:** the native `NSOutlineView` sidebar spike (time-boxed by the design, not attempted), the custom
`QAccessibleInterface` for graph nodes, and `screencapture` (it needs Screen Recording permission; the AppKit rendering above is
used instead).

## Conformance mark: revalidation by full recompute (2026-10-15)

User decision 2026-10-15 (relayed by the orchestrator from the CLI robustness session): only a full recompute clears the
"unvalidated" mark of `--skip-prov-conformance`, as `recompute --corpus OLD --out NEW --stages sem,prov,validation`,
written into a new corpus. `validate --corpus` stays read-only and records nothing, and a derive never carries a
skipped validation layer (`version_mismatch`). The GUI follows it:

- design §8.3a and its addendum, the conformance warning, the job note, the Package and Runs texts, the Viewer banner
  and the README no longer say that `validate --corpus` clears the mark;
- **Revalidate (full recompute)…** appears on the Viewer banner of a marked corpus and replaces Seal in the Package
  flow. It opens the Recompute form pre-filled with `--out <corpus>-revalidated` (`-2`, `-3`, … when that exists) and
  `--stages sem,prov,validation`, with the check on, and runs it as a detached job. The old corpus is never written.

## Follow-ups after the GUI security review (2026-10-21)

The independent GUI security review (branch `review-gui`, GR-1 to GR-69 fixed, landed on main 25ccea78) routed the items
below here; the orchestrator relayed the user's resume on 2026-10-21.

- **GR-70, batch checkout pinning.** A batch records the checkout's resolved path, its commit (with "(modified)") and the
  sha256 of `git diff HEAD` when it is created (`about.checkout_identity`). Before a step starts the identity is
  compared with the manager's current checkout; a branch switch, a new commit, an edit or Settings › General naming
  another checkout (GR-32) blocks every remaining step ("the checkout changed since this batch started"). Untracked
  files are not part of the identity. Found by the first dev-run end-to-end run, whose validate ran newer code than its
  import after a branch switch (3 of 3 failed with `aer.rules.drift`).
- **D-529 in dev runs.** `--sample N --sample-mode M` replaces `--limit N` when the CLI offers it; `--seed` goes only with
  `random` (the CLI refuses it otherwise: the second dev-run end-to-end run found this). When a part's import ends with
  exit 5 and `import.sample.unsupported`, a first-N import of the part is inserted after it, rebuilt through the same
  path as a restored batch step (GR-4), and keeps the note "fallback: …" in the summary. Any other failed import skips
  the part's validate and recompute steps instead of queueing them.
- **Dev-run end-to-end runs** (agentdojo/2024-06, 3 executions, every step a GUI job through the shared queue
  `--class import --cpu 2`; scratch `AGENTPROV_HOME` under `~/.agentprov/migration-work/gui-build/`):
  1. 2026-10-15, `--limit 3`: the import sealed 3 executions (exit 0); validate failed 3 of 3 because the checkout
     changed between the steps (`aer.rules.drift`, rows "made by other validator versions") — the GR-70 case;
  2. 2026-10-15, `--sample 3 --sample-mode first --seed 0` (main 8916be94): the import was refused at once (exit 2,
     "--seed goes with --sample-mode random"), and validate and recompute still ran after hours in the queue and ended
     `corpus.missing` — the seed rule and the skip-after-failed-import fix;
  3. 2026-10-21, `--sample 3 --sample-mode spread` (main 37be83cd plus this change): the import ended with exit 5,
     `import.sample.unsupported` ("the agentdojo.tracelogger reader names no stratum"), and the batch inserted the
     first-N import with its fallback note, as designed. The first-N import sealed 3 executions (exit 0: 3 mapped,
     derived and validated, none failed or degenerate). Its validate was cancelled while still queued, when the job
     moved to the current queue tool (run 4);
  4. 2026-10-21, `--sample 3 --sample-mode first` (main ae3eb427, no local change): import, validate and recompute all
     ended with exit 0. The import saw 18,241 executions, sampled out 18,238 and sealed 3 clean (issues: 3
     `map.accounting_unverifiable`, 3 `map.earlier_attempts_unobservable`); validate passed; recompute recomputed 3
     with 3 identical and 0 unexplained changes. The batch took 9.7 hours from start to end, almost all of it waiting
     in the shared queue; recompute itself took 4 s.
- **GR-37.** The native toolbar style constant is 3 (Unified); deviation 25 is re-measured (28 → 52 pt), the Cocoa smoke
  test passes again, and the README screenshots are re-shot.
- **GR-33:** job retention (Settings › Jobs), the default CI target (Settings › CI) and batch continue-on-failure as a
  per-batch choice are **not built**; the panes say so.
- **GR-16/43:** the S12 redaction filter of the GUI's own log exists as `app.register_secret`; the G3 keychain path
  must register every key value it reads before any logging.
- **GR-67:** notifications request authorisation when the native layer is installed in a signed bundle; the
  interruption levels and the notification actions are not built (macos-design §6 "As built").
- **GR-25:** design §19.1 now says a dev-run folder is kept while its batch is unfinished.

### Notes for later phases

- The Raw tab lists artefacts (role, sha256, included) only; "Show content" for raw bytes is G2 or later.
- The CI workflow has no job for the GUI project yet (CI is manual dispatch only, D-431); the osv scan covers
  `gui/uv.lock`.
- A graph-node `QAccessibleInterface` (D-446) is not built; the Elements list is the accessible view.

## G3: Run live (built 2026-10-22; branch `gui-g3`)

Session "GUI build G3–G5", from the integration head `66513065` (not main). Decisions D-650–D-655 (D-656, a direct
Anthropic endpoint, belongs to its own harness session). User yeses typed in this session's window on 2026-10-22:
- the GUI venv sync (offline: PySide6 6.12.0 from the uv cache);
- `keyring` (25.7.0, gui/ only);
- PySide6 ≥ 6.12.1 (**not on PyPI yet**: the latest is 6.12.0, published 2026-10-08; it stays open for G5);
- one fetch of the price pages (OpenRouter's model API, OpenAI, DeepSeek; Anthropic's pricing page at the user's
  later request).

### What is built

| Part | Modules | Notes |
|---|---|---|
| Core (class 0) | `cli/run.py`, `backends/shared` | D-651 `run --dry-run --plan-json`; D-652 `run SOURCE --catalogue` and the worker op `catalogue` (suites, task ids, tool-definition sizes, attacks with DoS flag, refusals and needs). Checked against `backends/agentdojo/.venv` (agentdojo 0.1.35: 4 suites, 97/35 tasks, 17 attacks) and `autodojo-aa458794` (17 suites, 20 attacks) |
| Prices (D-650) | `live/prices.py`, `data/prices.json`, `tools/build_price_table.py`, `tools/price_direct.toml`, `tools/fetch_prices.py` | 394 rows as of 2026-10-21; overrides, refreshed snapshots and the shipped table, in that order; Refresh prices is a confirmed R2 tool job, imported strictly |
| Estimate (D-653) | `live/estimate.py`, `live/usage.py`, `live/priors.py`, `tools/gen_estimate_priors.py` | p50/p90, worst case, time, per suite and per attack; opened corpus → priors → defaults; provider-aware tokens (D-656) |
| Keys (D-655) | `keychain_helper.py`, `live/keychain.py` | keyring only in a helper process; the key line goes from the helper's pipe to the job's stdin |
| CLI parity (D-654) | `jobs/commands.py`, `tests/test_cli_parity.py` | forms for run, inspect and every migrate gate; every option a field, global, managed or excluded with a reason |
| UI | `ui/runlive.py`, `ui/livepanes.py`, `ui/runs.py` | the Run Live dialog with the backend picker, Settings › Keys / Prices / Estimate, ▶ Run Live… (Ctrl+L), Live Dev Run… |

### Deviations from the design

26. **No shipped prices → shipped dated prices (D-650).** User decision 2026-10-22; §8.3 is amended.
27. **keyring in a helper process (D-655).** Not in the GUI process: its dependency loads `urllib.request` (S11).
28. **The estimate's dry run uses a scripted stand-in** while the live part is `planned` or the key is absent. A
    real-model dry run needs the key and is refused for a planned live part. The estimate says when the resume state
    is therefore not counted.
29. **Token priors from AgentDojo-family corpora are estimates.** Those corpora record no usage, so the priors use
    message characters / 4 plus the suite's tool-definition size (D-652). Recorded usage is used where present.
30. **The live dev run's call cap needs progress level `steps`.** `model_call` steps are not emitted at `status`
    level. The job is drained at the cap (one SIGTERM without a control file); calls already in flight finish.
31. **Backend env status comes from the catalogue call** (exit 3 "not built"), not from `backends build
    --offline-check`. An environment built before D-652 answers exit 5 and asks for a rebuild.

### Open

- ~~`gen_estimate_priors.py` has not been run yet~~ **done:** rebuilt 2026-10-24 from the round's corpora, with the
  judge split and each corpus's building commit (D-770; `tools/estimate/gen_estimate_priors.py`).
- ~~The scripted end-to-end run~~ **done 2026-10-22** (below).
- ~~The D-656 `anthropic` endpoint's max-tokens control~~ **done:** `run --max-tokens N|harness-default` is a Run Live
  field (`jobs/commands.py`).

### Scripted end-to-end run (the G3 exit criterion; 2026-10-22)

- **Environment:** a scratch environment, as the orchestrator directed (the registered environments are rebuilt only
  after D-652 reaches main). `AGENTPROV_HOME=~/.agentprov/migration-work/gui-g3/home agentprov backends build autodojo`,
  offline from the uv cache, with the pinned NLTK data from the verified fetch cache (`AGENTPROV_UPSTREAM_CACHE`):
  329 files verified, sandbox-exec probe passed. Its `run autodojo --catalogue` gives 17 suites and 20 attacks.
- **Driver:** the Run Live dialog, offscreen, with the real CLI; only the R1 confirmation was accepted by the driver.
  - Backend autodojo, suite banking, user tasks `0-1`, attack `direct`, injection task `0`, scripted transport (the
    shipped dev script). The job went through the queue (`--class import --cpu 2`).
- **First attempt:** exit 3, `backend.repository_missing`. GUI jobs started in their job directory, but `run`,
  `backends build` and `migrate` find the repository from their cwd (M.4). **Fixed (deviation 34):** those commands
  now start in the configured checkout; every other job keeps its job directory. All job paths are absolute (GR-20).
- **Second attempt:** exit 0. Attempted 4, conclusive 4, derived 4, failed 0, quarantined 0; 13.0 s of run time.
  - Catalogue 6.4 s and estimate 12.9 s after opening (priors: 4 units, no cost, "≈ 33 s, p90 4 m").
  - The follower saw all 4 `session` events.
  - The live preview drew one session: Run, its 4 actor tags, a Pass, a model call, the Outcome; 26 edges; no stop.
    The other three were stored, and their staging removed, before the helper's next 250 ms poll: a scripted cell
    takes about 3 s. With real models (minutes per cell) every session is visible. `--keep-staging` keeps short ones.
- **Not measured:** the preview's overhead on the run (G4 exit criterion). That needs a paired run with and without
  the preview on longer cells.

## G4: experimental live preview (built 2026-10-22; branch `gui-g3`)

| Part | Modules | Notes |
|---|---|---|
| Data | `preview/model.py` | `CaptureTail`: offset reader, partial lines, strict JSON (4 MiB lines), the `prev` chain checked on every line; a break, a shrink or a malformed line stops that tail with a reason. `PreviewGraph`: design §9's mapping from envelope metadata only |
| Helper | `preview/__main__.py` | `python -I -m agentprov_gui.preview HOME`, nice 10; `{"watch": session}` on stdin, deltas on stdout, a 250 ms poll, ends on EOF or a broken pipe, writes nothing |
| Window | `ui/preview.py`, `ui/runs.py` | the banner and a PREVIEW watermark; layered placement in event order, dashed and desaturated; at most 1 Hz; opened only from the dashboard for a running `run` job |

Tests: `gui/tests/test_g4_preview.py`. The synthetic logs carry an injection-like string in every content member; the
test asserts that no delta, label or scene text contains it. Also covered: tool names, the chain break, partial lines,
a shrunk log, ids that could name paths, the helper's EOF exit, and the window's helper shutdown.

Deviations:

32. **Tool names are never previewed**, not even with Show content (§9 allowed them escaped): the helper reads no
    data-derived name, so the window has nothing that needs content gating.
33. **The overhead re-measurement** (G4 exit criterion) was open: the scripted end-to-end run's cells were too short to
    show it (see G3 "Scripted end-to-end run"). **Closed 2026-10-24:** measured on longer scripted cells, within the
    pre-stated criteria (below, "Overhead measured").
34. **`run`, `backends build` and `migrate` jobs start in the configured checkout**, not in their job directory
    (design §4.2 said the job directory): they find the repository from their cwd (M.4). Found by the end-to-end run.

### Overhead measured (deviation 33; 2026-10-24)

The user chose a scripted run (option (b), no model) over a local-model one; no local model server was running.
- **Setup:** `gui/tools/preview_overhead.py` and its script `preview_overhead_script.json`, from main `b8a190eb`, on
  the M2 Max with the machine otherwise idle (load average 3.7, falling to 1.4 during the series). Each run was
  `agentprov run agentdojo --llm-script … --suite banking --benign only --repeats 3 --jobs 2` on the defended
  environment `agentdojo-db3901f1`: 48 cells, each with 14 read-only tool calls and 15 model calls.
  - **Order:** six runs, a b b a a b (a: no preview; b: the GUI's helper watching every session, as the dashboard
    does), in one queued job (`--class import --cpu 3`).
  - **Pre-stated criteria:** run wall time and mean cell time within ±3 %, and within the a runs' own spread; helper
    CPU at most 1 % of one core.
- **Results:**

| | a (no preview) | b (preview) | b − a (medians) |
|---|---|---|---|
| Run wall time, s | 127.9, 124.0, 121.4 (spread 6.5) | 129.4, 126.6, 121.9 | +2.7 s (+2.15 %) |
| Mean cell time, s | 4.80, 4.66, 4.50 (spread 0.30) | 4.86, 4.73, 4.47 | +0.07 s (+1.55 %; means +0.74 %) |
| Helper CPU | | 0.16–0.17 % of one core (about 0.2 s per run); 48 sessions and 4,800 deltas each | |

- **Verdict: within the criteria, so the G4 exit criterion is met.** The helper costs far less CPU than design §9's
  bound (about 0.8 % including start; a one-cell run shows 0.55–0.57 %, mostly start-up).
- **Caveat:**
  - each b run was slightly slower than the a run beside it;
  - a fit with a linear drift term (the load was falling) puts the preview's effect at +1.7 % of run time (+1.3 % of
    cell time), against a residual sd of 0.5 s, so a small real effect of that size is not ruled out by six runs;
  - the scripted cells call the "model" far faster than a real one does, so this is an upper bound for real runs;
  - the driver polls the progress file in the b arm only.

## G5: packaging (scaffolding, 2026-10-22)

- PyInstaller 6.22.3 (gui/ dev group; user yes 2026-10-22). One-folder build; `packaging/agentprov-gui.spec`;
  `packaging/entry.py` (frozen dispatch of `--keychain-helper` and `--preview-helper`); `app.main --smoke`.
- LGPL: the canonical LGPL-3.0 and GPL-3.0 texts (sha256 pinned; copied from local package metadata) and
  `gui/THIRD_PARTY_NOTICES.md`, generated by `gui/tools/gen_notices.py` from the lock's runtime closure and each
  package's metadata, with the Qt/PySide6 statement of design §13.
- `gui/tools/build_bundle.py` builds outside the repository and checks the excluded Qt libraries, the licences, the
  launcher SDK (`otool -l`, D-441), the signature (`codesign -dv`) and a smoke start of the GUI and both helpers.
- **Signing (D-657, user decision 2026-10-22):** no Apple Developer ID is bought. The macOS bundle is signed ad hoc,
  and that is G5's target: it starts on this Mac, and the first launch elsewhere needs right-click › Open
  (Gatekeeper). `build_bundle.py --sign-identity NAME` is the no-cost hook for a real identity later (hardened
  runtime; notarisation would be a separate step). The Windows and Linux bundles need their own build hosts.
- **PySide6 6.12.1** (QTBUG-150017) is not on PyPI: bundles carry 6.12.0 and its invisible check-box indicators in the
  `macos` style on macOS 27.

### First macOS bundle (2026-10-22)

`gui/tools/build_bundle.py` on the M2 Max (macOS 27), into `~/.agentprov/migration-work/gui-g5/` (outside the
repository): `AgentPROV.app`, 202 MB as reported (over-counted: symlinked files twice, fixed in 46), 21 s.

| Check | Result |
|---|---|
| Excluded Qt modules | The first build carried `QtNetwork.framework`: Qt's TUIO touch plugin (`plugins/generic/libqtuiotouchplugin`, touch input over UDP) links it, and module excludes do not catch a plugin's binary dependency. The spec now drops that plugin and every QtNetwork file (deviation 35); the rebuild has none |
| LGPL texts and notices | present (sha256 checked) |
| Signature | ad hoc: the G5 target (D-657) |
| Smoke start | `--smoke` GUI start, `--keychain-helper` (`status`: the allowlisted macOS Keychain back-end) and `--preview-helper` all exit 0, under `QT_QPA_PLATFORM=offscreen` with a scratch home |
| Launcher SDK | **27.0** after two steps (user yes 2026-10-22 for the source download). (1) The PyInstaller 6.22.3 sdist (sha256 `05eb2f56…`, as PyPI publishes) was extracted into its own folder, and its bootloader built with `./waf all` and Xcode CLT (SDK 27.0, clang 21); `gui/tools/install_bootloader.py` installed it into gui/.venv, keeping the prebuilt files as `*.prebuilt`. (2) PyInstaller still lowers the executable's SDK field to the Python library's (uv's CPython 3.14: SDK 15), for Tk's sake. `build_bundle.py` restores the field to the bootloader's real SDK with `vtool` and re-signs ad hoc (deviation 36); the smoke start passes |

36. **The launcher's SDK field is restored after PyInstaller.** PyInstaller rewrites it to the Python library's SDK,
    to protect Tk's dark mode; tkinter is excluded, and Qt draws the UI. `build_bundle.py` sets it back to the SDK the
    bootloader was really built with (never another value), only when that is ≥ 26, and re-signs the bundle.
35. **Qt plugins are filtered by binary, not only by module.** The TUIO plugin brought QtNetwork in through a
    module exclusion; the spec filters the collected binaries, and the build check stays the safety net.

### Live-pilot caps, ready before the CLI (D-725, D-726; 2026-10-22)

The live-pilot branch (`live-pilot-cli`) adds `--max-calls`, `--max-cost-usd`, `--price-in`, `--price-out` and
`--i-consent-to-local-run` to `run`. The GUI ships ahead of it, and the D-654 parity test stays green either way:

- **Cap fields.** The four caps are pending fields (D-725), shown in Run Live's Model group only when the endpoint is
  an API endpoint (`local = false`) and `run --help` lists `--max-calls`. Both caps are required to start. The
  prices are filled once per endpoint and model from the price table: the input side is the highest of input,
  cached input and cache write, as the CLI's upper bound.
- **Local consent.** `--i-consent-to-local-run` is a pending managed option. For a local endpoint, the consent tick
  adds it instead of the API-cost consent when the CLI has it, and the dialog says no provider bills those calls.
- **Tier.** All five flags are R2.

## Train 2: reverse CLI parity (D-700; branch `gui-cli-parity`, 2026-10-22)

Each GUI setting or action that changes stored state, a run or the estimate becomes a CLI command, and the GUI calls
that command. The CLI side is the one implementation.

| Piece | Core | GUI |
|---|---|---|
| D-703 settings | `agentprov.settings`, `agentprov settings list\|get\|set\|unset` (closed schema) | the forms (route recorded for D-654); the panes follow |
| D-702 keys | `agentprov.keys` (helper process, the only `keyring` importer), `agentprov keys`, `run --keychain` | Settings › Keys and Run Live call the CLI; the GUI's helper and `keyring` dependency are gone |
| D-701 prices and estimate | `agentprov.estimate` (moved from `gui/live/`), `agentprov prices list\|get\|set\|unset\|refresh`, `agentprov estimate` | Run Live shows `agentprov estimate --format json`; Settings › Prices and Estimate write through `prices` and `settings`; Refresh model prices is `prices refresh --allow-network` |

37. **The estimate costs one more worker spawn.** `agentprov estimate` reads the catalogue itself for the
    tool-definition sizes. Warm on the scratch AutoDojo environment, it takes about 10 s per estimate (28 s cold), the
    same order as the dry run alone took before. The dialog's estimate stays debounced and in the background.
38. **The bundle no longer carries price or priors data.** They are core package data now; the GUI reads them only
    through the checkout's CLI.
| D-704 jobs and batches | `agentprov.jobs` (record, follow, tiers, manager, supervisor, batch), `agentprov jobs`, `agentprov batch`; psutil a core dependency | Runs starts, follows and controls jobs through `agentprov jobs`; batches are created, started and resumed through `agentprov batch`, and each runs as its own driver job |

39. **Exit codes come from a supervisor, not from the GUI.** The GUI waited for the children it spawned. The CLI that
    starts a job exits at once, so each job runs under a small detached supervisor that waits and writes `ended.json`.
    A job killed from outside, supervisor included, shows as `unobserved`; `jobs kill` records `how: killed` itself.
40. **Batches no longer need the GUI open.** This was a user decision. One driver job per running batch replaces the
    GUI's 1 s advance timer, and Runs › Batches shows the batch file.
41. **The GUI suite takes longer: about 100 s, against 75 s before.** Every job a test starts is now an
    `agentprov jobs start` call, which starts a CLI first.
| D-705 dev runs | `agentprov.devrun.plan` (settings, plan, summary; read-only), `agentprov devrun plan\|start\|list\|prune` | Start Dev Run and Settings › Dev Runs go through `devrun` and `settings`; the preview and the summary use the core planner |

| D-700 settings panes and registry | `jobs start` applies `compute.*_budget`; `jobs prune` and `batch create` default to the `jobs.*` settings; `jobs follow --log` | Jobs, Compute and CI panes are `agentprov settings` keys (one base pane, Dev Runs moved onto it); `agentprov_gui/parity.py` and `tests/test_reverse_parity.py` |

42. **Settings › OK now runs one `agentprov settings` call per changed key.** Before, the panes wrote Qt's store
    in-process. A save that changes nothing runs nothing; the panes load in the background and stay disabled (and
    save nothing) until their values arrive, or when no CLI is configured. Values saved by earlier builds under the
    Qt keys `jobs/settings`, `compute/settings` and `ci/settings` are not migrated: they read as the defaults (user
    decision, 2026-10-22, relayed by the orchestrator: no migration).

43. **The Viewer's task and outcome columns read more per row (D-706).** Each row now also reads its `cell` and
    `outcome` facet while the table loads: still one strict JSON parse per line, plus a few dict reads. Measured
    2026-10-22 on `agentdyn-a-p10.partial` (38,281 working rows, warm): 0.50–0.59 s before, 0.66–0.70 s after, well
    inside the G1 budget of 3 s. **Full rows, measured 2026-10-23** while the regeneration round was running (load
    average about 9, so noisy): `rope-r1.partial`, the largest derived corpus on this machine (10,791 full rows, with
    `cell` and the outcome facet), loads in 0.39–0.43 s warm, against 0.23–0.32 s for its working twin
    `rope-rg1.partial` (same 10,791 executions). That is about 1.6 times the per-row cost, so a derived corpus of
    38,281 rows should load in about 1.5 s (projected, not measured), inside the 3 s budget. `agentdyn-a-rg1.partial`
    (38,281 working rows) measured 0.75–1.47 s under the same load. The round has not derived a corpus of that size
    yet; re-measure when one exists.

44. **The screenshot leak guard splits this repository's own GitHub links before scanning (F-11).** Their path runs
    (`com/nickjones39/AgentPROV/blob/main/docs`) matched the AWS-secret shape. Each segment of such a link is still
    scanned. **Limitation (accepted 2026-10-22):** a secret containing '/' inside one of these links is no longer
    caught by the AWS shape; every other URL and all other text get the full scan.

45. **The README keeps one GUI picture (F-7).** The trimmed README shows only `viewer-graph.png`, so the stale
    `new-job.png` (a relative corpus path, the conformance box disabled) and the unreferenced `settings-dev-runs.png`
    are removed from `docs/images/gui/`. The user guide keeps its own `new-job` capture. `viewer-graph.png` is
    re-shot from the current Viewer (source filter, derive hint, CLI line, Export Graph, Index Row). The re-shoot
    showed that the CLI line, and the corpus Export Graph passes to the render form, named the tree read
    (`DIR.partial`) for a working corpus. Both now name the final `DIR`, as `--corpus` does elsewhere (N.1.5; the
    core resolves `DIR` to `DIR.partial`).

### macOS bundle rebuild from main (2026-10-23)

`gui/tools/build_bundle.py` from origin/main `d7e6e0ee` (train 3, the Viewer, the models picker, the G5
cross-platform checks, F-7 and the screenshot cleanup) on the M2 Max (macOS 27), into
`~/.agentprov/migration-work/gui-g5/`, outside the repository. PySide6 6.12.0 (6.12.1 is not on PyPI),
PyInstaller 6.22.3 with the bootloader built on 2026-10-22, `uv --offline`: nothing was downloaded. Built at low
priority (`nice 10`) while the post-check and two environment builds ran: 20 s, exit 0, report `ok: true`.

| Check | Result |
|---|---|
| Layout, Qt dynamic libraries, plugins (P-7) | no problems |
| Excluded Qt modules | none found; an independent search of the bundle finds no QtNetwork, QtWebEngine, QtQml or QtQuick file |
| LGPL texts and notices | present (sha256 checked): `THIRD_PARTY_NOTICES.md`, `licenses/` |
| Launcher SDK | 27.0 (restored after PyInstaller, deviation 36); `minos 11.0` |
| Signature | ad hoc (D-657); `codesign --verify --deep --strict` passes |
| Smoke start | `--smoke` GUI start and `--preview-helper` exit 0 (offscreen, scratch home) |
| Keychain | no `--keychain-helper` check and no `keyring` file in the bundle: D-702 moved the helper into the core CLI, which the GUI calls |
| Size | **89.6 MB** of regular files (86 MB on disk). The build's report said 200.4 MB; with 46 fixed, `--no-build` on the same bundle reports 89.6 MB |

46. **The bundle report over-counts its size.** `build_bundle.py` sums `st_size` over every path that `is_file()`
    accepts. That follows symlinks, and PyInstaller's macOS layout links 53 files between `Frameworks/` and
    `Resources/`, so they count twice: 200.4 MB reported, against 89.6 MB of regular files. The 2026-10-22 figure
    (202 MB) was counted the same way. The checks are unaffected; only the size line was wrong. **Fixed:**
    `size_mb()` counts each regular file once, by `lstat`, and skips symlinks; a fixture with a file link and a
    directory link tests it (`test_g5_bundle_layouts.py`). The rebuilt bundle is 89.6 MB.

47. **Known, not fixed (2026-10-24): `gui/tools/screenshots.py` without OUT_DIR writes every scene into
    `docs/images/gui/`.** The README keeps only `viewer-graph.png` (entry 45), and the user guide's scenes belong in
    `docs/user-guide/images/gui/`, so a run without arguments recreates the dropped README pictures. Until the default
    changes, pass OUT_DIR and the scene names.
    **Fixed (A2, 2026-10-28, branch `claude/gui-viewer-tabs-416834`):** without OUT_DIR the tool writes to a new
    temporary folder outside the repository and prints its path. An OUT_DIR of `docs/images/gui/` takes only
    `README_SCENES` (`viewer-graph`), and any other scene, or no scene names, is refused with exit 2. The leak guard is
    unchanged. Tests: `test_screenshot_out_dir.py`.

48. **Known, not built (2026-10-24): Run Live has no Inspect mode.** Its backend picker comes from the registry, so it
    offers `agentharm` (backend `inspect-agentharm`). But `live/plan.py`'s `parse_catalogue` accepts only
    `agentprov-backend-catalogue/0.1` and refuses the Inspect catalogue (`agentprov-inspect-catalogue/0.1`, D-663) as
    "not a backend catalogue", so the dialog has no task, sample or judge pickers. An Inspect run starts from the New
    Job form for `run` instead, which has every Inspect option (`--task`, `--samples`, `--message-limit`,
    `--cell-size`, `--judge`; D-654 parity), and its estimate works since D-770. A Run Live Inspect mode, or hiding
    Inspect backends from the picker, is later work.


## Viewer execution tabs (D-840..D-845; branch `claude/gui-viewer-tabs-416834`, 2026-10-28)

User request (2026-10-28): double-clicking an execution opens its graph and PROV-JSON in a tab of its own, next to the
Corpora title. Design note and mockup: [`viewer-tabs/design.md`](viewer-tabs/design.md); approved as proposed.

### What is built

- `ui/execution.py` `ExecutionPane`: the detail area, extracted from `ViewerPage`, one instance per tab plus the
  compact preview. Each pane has its own Graph, PROV-JSON, AER, SEM, Register, Validation, Raw and Index Row widgets,
  its own load generation counter and its own Show-content switches. A tab keeps its detail and its corpus path, never
  an open reader. Reload Execution re-opens the corpus and keeps the snapshot when that fails.
- `ui/viewer.py`: a document-mode tab bar. Tab 0 is the corpus browser (not closable, kept first). Opening an open
  `(corpus root, ex)` focuses its tab. At most `MAX_TABS` = 12; the least recently viewed other tab closes first, and the
  status bar names it. `LIVE_SCENES` = 4 keep a live graph scene (`GraphTab.release_scene` / `restore_scene`, which
  rebuilds from the kept layout result). Tab titles are elided in the middle; the corpus name is added while two corpora
  are open. There are tooltips, accessible tab names, named close buttons, a middle-click close, a tab context menu and a
  table context menu.
- `ui/mainwindow.py`:
  - File › Open in New Tab, Close Tab ⌘W, Close Other Tabs ⌥⌘W, Close Window ⇧⌘W;
  - Go › Corpora, Next Tab, Previous Tab;
  - the Keyboard Shortcuts text.
- `ui/safe.py`: `set_tab_tooltip` and `tab_text` (`&` doubled). `parity.py`: the tab actions are presentational.
- **Tests:** `test_viewer_tabs.py` (12 tests: open, focus, close, keys, cap and eviction order, live scenes, two
  corpora, Reload Execution and a missing corpus, closing a loading tab, read-only, escaped titles, names). The
  existing Viewer tests use `viewer.preview`.
- **GUI suite:** 676 passed, 2 skipped (the cocoa smoke test and the real-corpus test, as before).

### Deviations and findings

49. **⌘W was not bound before this change.** `_action` passed a standard key through `QKeySequence(key)`, which keeps
    only the first platform binding. On macOS that is ⌘F4, so "Close Window" never had ⌘W. **Fixed:** standard keys go
    through `QAction.setShortcuts`, so Open, Reload, Settings and Close Tab get every platform binding.
50. **Next and Previous Tab are explicit keys.** Qt's `NextChild` on macOS is ⌘Tab (the app switcher), so the actions
    bind ⌘⇧] / ⌘⇧[ (`Ctrl+}`, `Ctrl+Shift+]`); elsewhere Ctrl+PgDown / Ctrl+PgUp, leaving Ctrl+Tab to the sub-tabs.
    ⌃Tab / ⌃⇧Tab switch sub-tabs inside a tab on macOS (`Meta+Tab` shortcuts on the pane).
51. **A late worker result for a closed tab** used to raise in the pool thread: the signal object is a child of the
    pane, deleted with it. `worker._Runnable` now drops a result whose receiver is gone.
52. **Beside the PROV-JSON pane the graph toolbar takes two rows** (`GraphTab(two_rows=True)`), and the PROV-JSON facts
    line wraps on its own line (`ProvJsonTab(stacked=True)`). Without them the toolbar combos were squeezed and the
    pane's minimum width held the splitter near 50:50 instead of 60:40.
53. **Memory (D-843), measured 2026-10-28 with `gui/tools/tabs_memory.py`** through `tools/suite_queue.py --class
    import`, offscreen, on `agentdyn-a-rg1` (RSS of the GUI process):

    | Tabs opened | Live scenes | PROV-JSON per document | RSS: corpus open → 12 tabs |
    |---|---|---|---|
    | the 12 largest | 4 | 2.98–3.96 MB | 171 → **687 MiB** |
    | the 12 largest | 12 | 2.98–3.96 MB | 182 → 689 MiB |
    | 12 around the median | 4 | 285 KB | 172 → 228 MiB |

    The design note expected graph scenes to be the large part. They are not: at about 200 nodes (core layout) the
    scenes add almost nothing, and the cost is the parsed detail, about 43 MiB per tab for a 3.9 MB document. Twelve
    median tabs stay within design §10 (≤ 300 MiB); twelve of the largest documents do not. **User decision
    (2026-10-28): accepted as it is; the cap stays at 12 and the worst case (687 MiB) is recorded here and in D-843.**
54. **Opening from the preview while it loads.** The preview's `ex` changes when a load starts, while its `detail` is
    still the previous row's. A tab opened in that window reused the stale detail. **Fixed:** the detail is shared only
    when the preview is ready and `detail.ex` matches (the Return-key test caught it).

### Screenshots

`viewer-outcomes`, `viewer-aer` and the new `viewer-tabs` scenes were retaken into `docs/user-guide/images/gui/` with
`--max-width 1200`, and `viewer-graph` with `--max-width 1100` (at 1200 px it was 335 KB, over the guide's 300 KiB
image limit). `viewer-graph` was also retaken into `docs/images/gui/` at full width. All went through
`gui/tools/screenshots.py` (cocoa, leak guard on). The README's top picture `docs/images/gui/agentprov-app.png` (a masked real-corpus shot, not a
scene) still shows the earlier "Corpora" heading. *Correction (2026-10-28, orchestrator): since `e53c23ba` that picture is a
generated Viewer-with-tabs scene from `gui/tools/screenshots.py`, not a masked capture.*
