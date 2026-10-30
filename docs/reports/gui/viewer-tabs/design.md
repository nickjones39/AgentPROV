# Viewer: executions open in their own tabs (design note, D-840 … D-845)

Status: **approved as proposed by the user on 2026-10-28** (session `gui-viewer-tabs`); the decisions are D-840..D-845 in `docs/architecture/DECISIONS.md`.

The user's request (2026-10-28): double-clicking an execution should open its graph and PROV-JSON viewer in its own tab,
in a tab bar at the top of the Viewer, next to the "Corpora" title.

Context: design §6.1 and §7, macos-design §3.3 ("Viewer", "Execution detail"), wireframe 01. Today the Viewer is one
vertical splitter: the corpora list, the executions table, and one shared detail area (title row, Export Graph… and the
tabs Graph, PROV-JSON, AER, SEM, Register, Validation, Raw, Index Row) that a single click reloads.

## Recommendation in one paragraph

The "Corpora" heading becomes the first tab of a document tab bar. That first tab is today's Viewer (corpora list,
executions table and the single-click preview, unchanged) and it cannot be closed. Double-click, Return or "Open in New
Tab" on an execution opens it in a closable tab of its own. The tab's first sub-tab shows the Graph and the PROV-JSON
side by side, still linked both ways; AER, SEM, Register, Validation, Raw and Index Row follow as sub-tabs. An execution
that is already open gets focus instead of a second tab. At most 12 execution tabs are open; a 13th closes the least
recently viewed one and the status bar says which. Tabs survive opening another corpus; each one is a read-only snapshot
of what it loaded. ⌘W closes the current execution tab, ⌘⇧[ and ⌘⇧] switch tabs, and every command is also in a menu.

Mockup (placeholders only, light appearance): [`mockup-execution-tab-light.svg`](mockup-execution-tab-light.svg). It
shows four execution tabs from two corpora (so the corpus name appears in the tab), one still loading.

## The Corpora tab (first tab)

```
┌─────────────────────────────────────────────────────────────────────────────────────────── [Reload] ┐
│ [▤ Corpora] │ ex_0002 corpus-x ✕ │ ex_0007 corpus-x ✕ │ ex_0002 corpus-y ✕ │            4 of 12 open    │
├──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ corpora list                          (unchanged)                                                    │
│ verification banner · filters · CLI line                                                             │
│ executions table   ← click: preview below · double-click / Return / context menu: open in a tab      │
│ preview: ex_0005 · src-a · ok · …   [Open in New Tab] [Export Graph…]                                │
│ [Graph] [PROV-JSON] [AER] [SEM] [Register] [Validation] [Raw] [Index Row]   (unchanged)               │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Decisions

### D-840: a document tab bar whose first tab is the corpus browser

- A `QTabWidget` in document mode replaces the "Corpora" heading row. Tab 0 is **Corpora**: the corpus browser. It has no
  close button and stays first (tabs can be reordered by dragging, but not in front of it).
- Every other tab is one execution, with a close button.
  - **Title:** the execution id, elided in the middle to about 20 characters (`ex_22nv7…mj5xqaiqzd`).
  - **Corpus name:** added in secondary text only while execution tabs from more than one corpus are open.
  - **Tooltip:** the full execution id, the corpus name and the corpus path.
  - **While loading:** "· loading…"; on failure, "· cannot be opened" and the reason in the tab.
- **Reload** (the corpora list) moves to the trailing end of the tab bar.
- **Safety (S1):** ids and corpus names are data.
  - Tab text goes through `T.line` and has `&` doubled, because `QTabBar` treats `&` as a mnemonic.
  - Tooltips go through a new `safe.set_tab_tooltip`, since `setTabToolTip` is banned outside `ui/safe.py` by
    `test_lint_safe`.
- **Rejected:**
  - a separate tab bar above the whole page (the user asked for the tabs next to the Corpora title);
  - one window per execution (macos-design §3.1 keeps "Open in New Window" an option, not the default);
  - a navigation stack with Back and Forward, as in macos-design §3.3 (it shows one execution at a time, and the user
    wants several open side by side).

### D-841: what an execution tab holds

- **Structure:** each tab is one `ExecutionPane`, a class extracted from today's detail area. It has its own `GraphTab`,
  `ProvJsonTab`, `AerTab`, `SemTab`, `RegisterTab`, `ValidationTab`, Raw table and Index Row text, its own load
  generation counter (the supersede rule, per tab) and its own content switches. Nothing is shared between tabs except
  the read-only `DetailCache` and the layout cache on disk.
- **Title row:** "ex · source · status · completeness · corpus (state, read-only)", then **Show in Corpora** (selects
  the row in the first tab) and **Export Graph…** (as today: the `agentprov render` job form).
- **First sub-tab, "Graph + PROV-JSON":** the graph (canvas and its side panel) on the left and the PROV-JSON on the
  right, in a horizontal splitter (60:40 by default; dragging the splitter to an edge hides a side). Inside this layout
  the PROV-JSON tree sits above its raw-text pane, because there is no width for both side by side. The two stay linked
  both ways: "Show in PROV-JSON" and a click on a node select the statement, and a tree selection selects the node.
- **Other sub-tabs:** AER, SEM, Register, Validation, Raw and Index Row, unchanged.
- **Show content (S2):** off in every new tab, per pane, and never carried from one tab to another.
- **Rejected:**
  - Graph and PROV-JSON as two sub-tabs, as today. It is simpler, but the user named them together, and the link
    between them is easier to follow when both are visible.
  - A tab that holds only the graph and the PROV-JSON, with AER and the rest left in the preview. Then the record that
    a graph statement points to would be one tab away, in a different execution's context.

### D-842: single-click keeps the quick preview in the Corpora tab

- A click or the arrow keys in the executions table fill the preview area below the table. This is today's behaviour:
  the same `ExecutionPane` in its compact form, with Graph and PROV-JSON as separate sub-tabs.
- The preview gets an **Open in New Tab** button.
- **Opening an execution:** double-click, Return or the table's context menu (Open in New Tab, Copy Execution Id).
- **Rejected:** dropping the preview so the table takes the whole height. Stepping through rows with ↑↓ and seeing each
  graph at once is the quickest way to scan a corpus. The splitter can already collapse the preview for a taller
  table.

### D-843: lifecycle, the cap and memory

- **Identity:** a tab is keyed by (the corpus root, resolved; the execution id). Opening a key that is already open
  focuses its tab; nothing is reloaded.
- **Cap:** 12 execution tabs, a fixed number with no Settings key, so there is no new CLI-parity row.
  - Opening a 13th closes the least recently viewed tab (never the current one).
  - The status bar names the tab that was closed.
  - The counter "n of 12 open" sits at the trailing end of the tab bar.
- **Loading:** a tab reuses the `DetailCache` entry when there is one. Otherwise it loads in a worker thread, as the
  preview does today. Closing a tab cancels its pending loads through the generation counter, and their late results are
  dropped.
- **Memory:** the parsed detail is shared with the `DetailCache` object, not copied. Graph scenes are the large part.
  - Only the current tab and the 3 most recently viewed keep a live `QGraphicsScene` and overview raster.
  - Older tabs drop the scene and keep the layout result, so showing them again rebuilds the scene without re-running
    `dot`.
  - The build measures this against the §10 budget (≤ 300 MiB with one 3k-node graph), with 12 tabs on the largest
    real document, and records it in the build log. If 4 live scenes break the budget, the number goes down.
  - **As measured (build log entry 53):** the parsed documents dominate, not the scenes: 687 MiB with the 12 largest
    documents, 228 MiB with 12 median ones. The user accepted this on 2026-10-28 and kept the cap at 12.
- **Closing a tab** frees its widgets (`deleteLater`), hides its popover and releases its scene.
- **Rejected:**
  - no cap (memory grows without bound on large graphs);
  - refusing the 13th tab with a warning (an extra dialog for no gain, since a closed tab reopens with one
    double-click);
  - a cap in Settings (it would need a reverse-parity entry for a purely presentational limit).

### D-844: opening another corpus, Reload and working corpora

- **Opening another corpus** replaces the Corpora tab's contents, as today. The execution tabs stay open.
  - Each one holds its own loaded detail and its corpus path; it keeps no open reader.
  - Comparing the same execution in two corpora (for example a corpus and its regenerated twin) is the main use.
  - The corpus suffix in the tab titles appears as soon as two corpora are represented.
- **Reload** (the corpora list, ⌘R) does not touch execution tabs.
- **Snapshots:** an execution tab is a read-only snapshot of what it loaded.
  - If the corpus is a working tree being written by a job, the title row says "snapshot loaded at HH:MM:SS".
  - The tab's context menu has **Reload Execution**, which re-reads the detail and replaces the snapshot.
  - Nothing is ever written inside a corpus. As now, there is no lock and no cache inside it.
- **A missing corpus:** if the corpus is gone or cannot be read on Reload Execution, the tab says so and keeps the old
  snapshot until it is closed.
- **Rejected:** closing every execution tab when another corpus opens. It is simpler, but it loses the cross-corpus
  comparison, and opening a corpus would silently discard the user's work.

### D-845: keys, menus and accessibility

- **Keys (macOS; the Qt standard keys map them on Windows and Linux):**
  - Return in the executions table: Open in New Tab.
  - ⌘W: close the current execution tab. On the Corpora tab it closes the window, as today (the Safari and Xcode
    pattern).
  - ⌥⌘W: close the other execution tabs.
  - ⌘⇧] and ⌘⇧[: next and previous tab (`QKeySequence.NextChild`/`PreviousChild`; Ctrl+Tab and Ctrl+Shift+Tab
    elsewhere).
  - ⌃Tab and ⌃⇧Tab: the sub-tabs inside the current tab, as macos-design §3.3 already assigns them.
  - Middle-click on a tab closes it.
- **Menus (parity, design §6):**
  - **File:** Open in New Tab · Close Tab (⌘W; on the Corpora tab it closes the window) · Close Other Tabs (⌥⌘W) ·
    Close Window (⇧⌘W, always).
  - **Go:** Corpora · Next Tab (⌘⇧]) · Previous Tab (⌘⇧[).
  - **Tab context menu:** Close · Close Other Tabs · Show in Corpora · Reload Execution · Copy Execution Id.
- **Accessibility:**
  - The tab bar is named "Viewer tabs".
  - Each tab's accessible description is "Execution ‹id› in corpus ‹name›, ‹ready|loading|cannot be opened›".
  - Close buttons are named "Close ‹id›". The Corpora tab is named "Corpora browser".
  - The executions table announces "Return opens the execution in a new tab".
  - `test_every_control_is_named` covers the new widgets.

## Effects

- **Files:** `gui/` only. That is `ui/viewer.py` (split: `ExecutionPane` and the tab management),
  `ui/mainwindow.py` (menus; `viewer.graph` users move to the panes), `ui/safe.py` (`set_tab_tooltip`, tab text),
  `gui/tools/screenshots.py` (scenes) and new tests. Docs: `docs/user-guide/08-desktop-app.md`, the build log, design
  §6.1 (a pointer here), and the decision fragments D-840..D-845 after approval.
- **No core change:** no AER, SEM, PROV, corpus or CLI change, no byte class, no regeneration. Class 0.
- **Settings:** the Appearance "W3C exact" palette and the Show-content limit apply to every open pane.
- **The held branch `gui-g5-held`:** it touches `dialogs.py`, `livepanes.py`, `runlive.py`, `runs.py`,
  `settings_panes.py`, `system.py` and the bundle tools. None of these is in this work, so there should be no overlap.
  Any overlap found during the build will be reported.
- **Tests (new):** open, focus an open tab, close, cap and eviction order, corpus switching, Reload Execution, ⌘W on
  each tab kind, the linked selection inside a tab, loads superseded per tab, a hostile id in the tab title (escaping,
  `&`), and no write inside the corpus (`test_open_is_read_only` extended to tabs).
