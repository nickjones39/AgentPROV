# AgentPROV desktop GUI: native macOS visual and interaction design (no code)

Status: **approved as the direction** (2026-10-14; user decision, given in the session window and relayed by the
orchestrator session). As with D-390..D-399, the build comes after the regeneration round. Branch `gui-macos-design`,
from origin/main `f68dd683`. It is research and design
only: no application code was written. It extends [`design.md`](design.md) (approved as the direction, D-390..D-399 and
D-432) and keeps all of its constraints:
- no web server and no web view;
- plain-text rendering of untrusted corpus text (§11);
- writes only through the `agentprov` CLI, as detached jobs;
- live PROV preview off by default;
- keys in the OS keychain;
- the performance budgets of §10;
- Windows and Linux stay supported, each with its own conventions.

The decisions are **D-440 to D-449** (§13). Their full text, with rejected alternatives, is in
`docs/architecture/DECISIONS.md`. The mockups are in [`mockups/`](mockups/README.md), and the measured screenshots
are in [`mockups/evidence/`](mockups/evidence/).

## 0. Summary

- **Recommendation (D-440):** keep PySide6 / Qt Widgets on all three platforms (D-390). On macOS, add a small, optional
  **native chrome layer**: PyObjC calls into AppKit, confined to one module. It adds what Qt 6.12 lacks:
  - a real `NSToolbar` in the unified style, with Liquid Glass item groups, a title and subtitle, and an
    `NSSearchToolbarItem`;
  - Dock tile progress;
  - `UNUserNotificationCenter` notifications;
  - the standard Window menu actions;
  - the accessibility display flags that Qt does not expose.

  Measured on this Mac (macOS 27.0.1): a Qt window carrying the native toolbar is very close to a SwiftUI reference
  window (§2.1, M4 against M5). A second, native SwiftUI or AppKit front-end is **rejected for now**. It would double the
  UI work. Its security layer (`quote_untrusted`, `escape_untrusted_line`, the strict readers, `render.graph`) would
  have to be ported to Swift or put behind a helper process. It needs full Xcode, and it adds a macOS-only test stack.
  This **amends D-390** (approved 2026-10-14): one platform-conditional dependency plus a native module. The toolkit does
  not change.
- **Main executable SDK (D-441):** AppKit and Qt draw the current macOS design (Liquid Glass, Tahoe control metrics)
  only when the **main executable** was linked against SDK 26 or later. The uv-managed CPython 3.14.8 interpreter is
  linked against **SDK 15.0** (measured). A `uv run` therefore shows the older compatibility look, and the release bundle
  needs a launcher or PyInstaller bootloader built with the current SDK. Measured: the same Qt code switches to Tahoe
  metrics under an SDK-27 launcher (M1 against M2).
- **HIG structure (D-442):**
  - one main window: sidebar (corpora, jobs, release) | content | inspector;
  - a standard **Settings window** (⌘,) with a pane toolbar;
  - the standard **About** window from the App menu;
  - **New Live Run** as its own window;
  - every tier R1 and R2 confirmation as a **sheet**.

  Settings and About leave the sidebar on macOS. Each platform places them its own way (§3).
- **Visual system (D-443):**
  - system fonts everywhere, so no font files are bundled (SF Pro and SF Mono may only be used through the system on
    Apple platforms);
  - system semantic colours plus a token table for Light, Dark and Increase Contrast;
  - SF Symbols on macOS through `QIcon.fromTheme`; 52 names checked present (§4.4);
  - **Phosphor (MIT)** icons on Windows and Linux;
  - a 4-pt grid;
  - Reduce Motion honoured through Qt 6.12's `motionPreference`.
- **PROV graph (D-444):**
  - W3C hues kept on the fills in both appearances, with the dark and accessible strokes of design §12;
  - an accent-colour selection ring plus a thicker border;
  - the hover popover becomes a Qt `Popup`, which Qt maps to an `NSPanel` window;
  - the inspector shows the selected element;
  - trackpad pinch and smart zoom through `QNativeGestureEvent`, which `QGraphicsView` does not handle by itself.
- **Integration (D-445):**
  - Dock badge = running jobs; Dock progress = the selected or overall job;
  - a notification when a long job ends;
  - multiple windows, but no window tabs (Qt disables them);
  - state saved with `QSettings`;
  - native Full Screen;
  - **no Quick Look or Spotlight extension** (it would need sandboxed Swift extensions and a corpus package type);
  - the Windows and Linux equivalents are listed in §6.
- **Accessibility (D-446):**
  - every control named, enforced by a lint;
  - the graph exposed as an Elements list, plus a custom `QAccessibleInterface` (subclassable from PySide6);
  - full keyboard use;
  - in-app text size from 85 % to 200 %, because macOS has no Dynamic Type;
  - status shown by shape and text, never by colour alone.
- **Packaging (D-447):** a Developer ID-signed, hardened-runtime, notarised `.app`, **outside the App Sandbox and the Mac
  App Store**. Measured with an ad-hoc-signed sandboxed probe:
  - the venv CLI, Homebrew `dot` and `~/.agentprov` were all denied;
  - even with temporary-exception entitlements, the CLI's own `sandbox-exec` containment fails nested ("sandbox_apply:
    Operation not permitted").
- **Security (D-448):**
  - PyObjC's `objc._convenience` imports `socket`, so S11's fresh-interpreter `sys.modules` check is amended. The static
    import bans stay, and `ssl`, `http` and `urllib.request` stay banned.
  - New rule S15 confines the native layer and its strings.
- **Windows and Linux (D-449):** each follows its own conventions:
  - **Windows 11:** Qt's `windows11` style (verified as the default since Qt 6.7, which changes design §12's "Fusion on
    Windows"); a NavigationView-style pane with Settings pinned at the bottom; About inside Settings; taskbar progress
    through `ITaskbarList3`.
  - **GNOME:** a header-bar layout with a primary menu, and no menu bar.
  - **KDE:** a menu bar, with Ctrl+Shift+, for Configure.

## 1. Method and environment

- **Read first:** `AGENTS.md` §0 and the invariants, `CLAUDE.md`, [`research.md`](research.md), [`design.md`](design.md)
  (including §6, §8.3a, §11, §12 and the D-432 additions) and `DECISIONS.md` D-390..D-399 and D-432.
- **Primary-source research:**
  - Apple HIG pages, read through their JSON endpoints (`developer.apple.com/tutorials/data/design/…`);
  - Apple developer documentation, release notes and WWDC session pages;
  - Qt 6.12 documentation, release notes, the Qt blog and the Qt Jira (statuses read on 2026-10-14);
  - Qt source on the 6.12 branch, read as text only;
  - Microsoft Learn, the GNOME HIG, libadwaita docs, the KDE HIG and KDE source;
  - licence files of the font and icon projects, and PyPI.

  Everything was retrieved on 2026-10-14. Claims that no primary source confirms are marked *unverified*. Apple DTS
  forum answers are cited as Apple staff statements, not as documentation.
- **Machine:** Apple M2 Max (12 cores), 32 GiB, macOS 27.0.1 (26A434). Swift 6.4 from the Command Line Tools; no full
  Xcode is installed.
- **Throwaway environment** in the session scratchpad, with the user's approval in this window (2026-10-14):
  - a venv with PySide6-Essentials 6.12.0, installed **offline** from the local uv cache;
  - PyObjC 12.2.2 (`pyobjc-core`, `pyobjc-framework-Cocoa`, `pyobjc-framework-UserNotifications`), downloaded from PyPI
    after a separate yes;
  - small Swift programs compiled with the installed `swiftc` and ad-hoc signed;
  - window captures with `screencapture -l <window id>` (the user approved it).

  Nothing was installed into the core or any repository environment. The scratch environment is deleted after the
  study. Every window showed placeholder data only.
- **Machine load:** other sessions were running test suites, so timings are upper bounds.

## 2. Q1: toolkit fit for a native macOS feel

### 2.1 Measurements (this Mac, macOS 27.0.1)

| # | What | Result | Evidence |
|---|---|---|---|
| M1 | Qt Widgets 6.12, default `macos` style, run by the uv CPython 3.14.8 (`LC_BUILD_VERSION` sdk **15.0**, minos 11.0) | **Native:** the window frame, the window-modal sheet, SF Symbols through `QIcon.fromTheme`, the accent colour (`QPalette.Accent` = `#0a60ff`), ⌘, for `QKeySequence.Preferences`, `setBadgeNumber`, `QFontDatabase.systemFont` = `.AppleSystemUIFont` 13 pt. **Not native:** a centred title with the `QToolBar` in a second row; a plain white list as the sidebar; a `QDockWidget` "Inspector" with its own close and float buttons; Aqua-era controls | [m1](mockups/evidence/m1-qt-default-sdk15.png), [sheet](mockups/evidence/m6-qt-window-modal-sheet.png) |
| M2 | The same code under a 30-line launcher linked against **SDK 27.0** (embeds `libpython3.14`, `Py_BytesMain`) | Qt's Tahoe paths switch on: a left-aligned title, the new traffic lights and control metrics. The toolbar still sits in its own row | [m2](mockups/evidence/m2-qt-default-sdk27.png) |
| M3 | "Tuned" Qt, SDK-27 launcher | Drawn by Qt: a sidebar from a `QListView` delegate (SF Symbols, rounded selection, section headers), a splitter inspector, a 24-px table row, a segmented tab row. Close to the macOS 14–15 look, but no glass toolbar and no title-row items. `NoTitleBarBackgroundHint` alone does not extend content under the title bar (`safeAreaMargins` top = 0) | [light](mockups/evidence/m3-qt-tuned-sdk27-light.png), [dark](mockups/evidence/m3-qt-tuned-sdk27-dark.png) |
| M4 | **Hybrid:** M3 plus a native `NSToolbar` attached to Qt's `QNSWindow` through PyObjC (`toolbarStyle` unified, icon-only, an `NSToolbarItemGroup`, an `NSSearchToolbarItem`, `subtitle`) | Title and subtitle in the toolbar row, Liquid Glass capsules, a native search field, in Light and Dark. The Qt content resized correctly (`contentLayoutRect` 1100 × 672). Toolbar actions reached Python | [light](mockups/evidence/m4-qt-hybrid-nstoolbar-light.png), [dark](mockups/evidence/m4-qt-hybrid-nstoolbar-dark.png) |
| M5 | SwiftUI reference: `NavigationSplitView`, `Table`, `.inspector`, `.searchable`, toolbar (SDK 27) | The macOS 27 look: an edge-to-edge sidebar, glass groups, a grouped inspector. **40 rows:** RSS 141 MB. **100k rows:** window in 1.9 s, RSS 190 MB. **1M rows:** 3.3 s, 580 MB | [light](mockups/evidence/m5-swiftui-reference-light.png), [dark](mockups/evidence/m5-swiftui-reference-dark.png) |
| M6 | SwiftUI build with the Command Line Tools only | `@State` fails: "plugin for module 'SwiftUIMacros' not found". A real SwiftUI front-end needs **full Xcode**. A first 60-line prototype also crashed in an Auto Layout update-constraints loop between `NavigationSplitView`, `.frame(minWidth:)` and `inspectorColumnWidth` (removing the modifiers fixed it) | logs in the scratchpad |
| M7 | Dock tile: `badgeLabel`, plus a `contentView` with an `NSProgressIndicator`, through PyObjC in a Qt process | Rendered (the tile view was rasterised to check it) | [m7](mockups/evidence/m7-dock-tile-progress.png) |
| M8 | `UNUserNotificationCenter` from an **ad-hoc-signed** `.app` (launched directly and through `open`) | `UNErrorDomain` 1 "Notifications are not allowed for this application". Expected to need a real signing identity; to be confirmed in G5 | — |
| M9 | PyObjC import cost and modules (SDK-27 launcher, warm) | `import AppKit, objc` costs 0.15–0.28 s; Qt Widgets costs 0.14–0.31 s. **`objc._convenience` imports `socket`** (line 21, for sockaddr helpers); Qt alone does not | — |
| M10 | Detached children | Python `Popen(start_new_session=True)` from a bare process and from inside a `.app` bundle: the child survives the parent (ppid becomes 1). The approved design §4.2 mechanism holds. A Swift `posix_spawn` with `POSIX_SPAWN_SETSID` child did **not** survive its parent; the cause was not established (a risk for any Swift front-end) | — |
| M11 | App Sandbox probe: ad-hoc-signed `.app` with `app-sandbox` + `network.client` | Denied: listing `~/.agentprov` (Cocoa 257), creating a job directory (513), executing the venv CLI and Homebrew `dot` ("doesn't exist" inside the sandbox). `sandbox-exec` exits 71: "sandbox_apply: Operation not permitted" | — |
| M12 | The same, plus temporary exceptions (`home-relative-path.read-write` `/.agentprov/`, `absolute-path.read-only` `/Users/`, `/opt/homebrew/`) | The CLI (`--version`) and `dot -V` run, and the job directory can be created. **Nested `sandbox-exec` still fails (exit 71)**, so the live run's containment cannot work under an App Sandbox | — |
| M13 | SF Symbol names used in §4.4, checked with `NSImage(systemSymbolName:)` | 52 of 52 present on macOS 27. `QIcon.hasThemeIcon` is False for an unknown name, so a missing symbol is detectable | — |

### 2.2 What Qt 6.12 gives on macOS, and what it does not

| Capability | Qt 6.12 | Gap and how it is closed | Source |
|---|---|---|---|
| Native controls with the current design | `macos` style; Tahoe metrics only when the main executable's SDK is 26 or later | Build the launcher with the current SDK (D-441). Umbrella bug QTBUG-138942 is open; QTBUG-150017 (check indicators invisible on macOS 27) is fixed only in **6.12.1** | [Q1], [Q19], M1/M2 |
| Unified toolbar | `setUnifiedTitleAndToolBarOnMac`: a Qt-drawn `QToolBar`, not an `NSToolbar`. 6.12 uses a transparent title bar on Tahoe | Native `NSToolbar` through the native layer (M4). Qt's unified mode stays off when the native toolbar is on | [Q2], [Q4] |
| Content under the title bar | `ExpandedClientAreaHint` (6.9) is documented but **not exposed in PySide6 6.12's `Qt.WindowType`** (measured); `NoTitleBarBackgroundHint` is exposed | Not needed with an `NSToolbar` | [Q3], M3 |
| Menu bar | Native `NSMenu`; roles merge About, Settings and Quit into the App menu; `setAsDockMenu` | **No standard Window menu API** (QTBUG-144123): add Minimize, Zoom, Bring All to Front and the tiling items through the native layer | [Q5], [Q6] |
| Sheets | `WindowModal` with a parent becomes a sheet (M1). On Tahoe a window-modal `QMessageBox` is Qt's widget fallback, not `NSAlert` (QTBUG-141689) | Acceptable; a sheet is the HIG form | [Q7] |
| Popovers | No `NSPopover` (QTBUG-61607) | A `Qt.Popup` widget (an `NSPanel`) styled as a popover | [Q19] |
| Accent, Dark Mode, Increase Contrast, Reduce Motion | `QPalette.Accent` (6.6), `colorScheme` (6.5) and `setColorScheme` (6.8), `contrastPreference` (6.10), **`motionPreference` (6.12)**, all measured present | **Reduce Transparency** and **Differentiate Without Colour** come from `NSWorkspace` through the native layer | [Q8], M1 |
| Vibrancy and Liquid Glass | None public (QTBUG-85310) | The toolbar gets glass natively (M4). The sidebar is drawn by Qt with system colours; an embedded native sidebar is a time-boxed spike only (§2.6) | [Q19] |
| SF Symbols | `QIcon.fromTheme(name)` maps unmapped names to `NSImage(systemSymbolName:)` | Use directly (M13) | [Q10] |
| Dock | `setBadgeNumber` (6.5); `QApplication.alert` bounces | **No progress API** (QTBUG-94008): `NSDockTile` through the native layer (M7) | [Q11], [Q12] |
| Notifications | `QSystemTrayIcon.showMessage` still uses the deprecated `NSUserNotification` (QTBUG-110998) | `UNUserNotificationCenter` through the native layer, in a signed bundle (M8) | [Q13] |
| Trackpad | `QNativeGestureEvent` (Zoom, SmartZoom, Rotate, Swipe), and `QWheelEvent` pixel deltas with phases | `QGraphicsView` has no pinch handling: the graph view handles the events itself (§5) | [Q14], [Q15] |
| Accessibility | NSAccessibility bridge for standard widgets; `QAccessibleInterface` subclassable from PySide6; no Python `QAccessibleTableInterface` | Custom graph interface plus the Elements list (§7). Open: QTBUG-110737 (checkable buttons) | [Q16] |
| Window tabs, state restoration | Qt sets `tabbingMode = disallowed` and `restorable = NO` | No tabs (§6). State through `QSettings` (`saveState`/`saveGeometry`) | [Q19] |
| Proxy icon, edited dot | `setWindowFilePath` gives the proxy icon; `setWindowModified` gives the edited dot | Used for an opened corpus (proxy icon only; the GUI edits nothing) | [Q6] |

### 2.3 Options compared

| Option | macOS fidelity (measured or cited) | Shared with Windows and Linux | Security layer | Cost and risks | Verdict |
|---|---|---|---|---|---|
| **(a) Qt only, tuned** | M3: close to macOS 14–15; no glass toolbar, no Dock progress, deprecated notifications | everything | one implementation (S1–S14) | lowest | the fallback path |
| **(a+) Qt plus a native chrome layer (PyObjC)** | M4: native toolbar, title, subtitle, search and glass; Dock progress; modern notifications; system flags | everything except one darwin-only module (~300–500 lines expected) | one implementation; S11 amended, S15 added (D-448) | +1 dependency (PyObjC, MIT, cp314 wheels). Qt owns the `NSWindow`, so attaching an `NSToolbar` is not a Qt-supported configuration: a smoke test per Qt bump, and a switch back to (a) | **recommended (D-440)** |
| (b) SwiftUI or AppKit front-end on macOS, Qt on Windows and Linux | M5: full fidelity | the CLI, job-directory and progress contracts only | must be **ported to Swift** (`quote_untrusted`, `escape_untrusted_line`, strict JSON readers under `IngestLimits`, `render.graph`, the DOT emitter), or (b′) | two view layers for ~10 screens and the graph; full Xcode (M6); XCTest/XCUITest on macOS only, while CI is manual dispatch and macOS minutes cost 10× (D-431); SwiftUI `Table` scale reports and the M6 crash; the M10 spawn risk | rejected now |
| (b′) Swift front-end plus a Python view-model helper over stdio JSONL | as (b) | read model and security layer stay in Python | one implementation behind the pipe | still two view layers; an IPC protocol for tables, selection, LOD and search; startup and latency of the helper | rejected now; the most credible native-only variant if (a+) fails |
| (c) PyObjC AppKit front-end in Python | full (native controls) | read model shared in-process | one implementation | every `NSTableView`/`NSOutlineView` data source and the graph canvas rewritten for AppKit; little documentation for large PyObjC apps | rejected |
| wxPython 4.3.2 | native controls | yes | yes | `wxDataViewVirtualListModel` is "not supported by macOS" (no virtual list for 38k–100k rows); no PyPI Linux wheels; `wxAccessible` is MSW-only | rejected [L7] |
| Toga 0.5.7 | native widgets | yes | yes | the bulk-update issue #2747 is still open | rejected, as in research Q1 [L8] |
| Compose Multiplatform, Avalonia, .NET MAUI | own renderer (Compose, Avalonia) or Mac Catalyst (MAUI, no Linux) | — | — | not native on macOS, and not Python | rejected [L9] |

### 2.4 The cost of two front-ends (option b), made concrete

- **Shared:**
  - the CLI argv contracts (Appendix A);
  - `job.json`, `progress.jsonl` 0.2, `control.json`, `summary.json`;
  - the session-status files;
  - Graphviz `dot -Tjson`.
- **Not shared:**
  - every view and view model;
  - the graph scene, with LOD and the overview raster;
  - the log ring buffer;
  - the sampler UI;
  - the keychain wrapper (Swift `Security` instead of `keyring`);
  - the S1–S14 lints, re-expressed for Swift: no `AttributedString(markdown:)`, no `Text(LocalizedStringKey(var))`, no
    `Link` or `openURL` from data, `Text(verbatim:)` only for data [S45], `NSTextView` link detection off.
- **Testing:**
  - a second suite (XCTest/XCUITest) that runs only on macOS;
  - the GUI behaviour matrix (re-attach, tiers, keys) tested twice;
  - with D-431 (CI by dispatch only), the macOS suite would run locally only.
- **Estimate:** at least 1.8× the GUI UI effort of design §15 (G1–G4) for one researcher. The effort lands where the
  measured gap is smallest (content views), not where it is largest (window chrome).

### 2.5 Recommendation and the change to D-390

**Decided (D-440):** keep **PySide6 6.12 / Qt Widgets** as the toolkit on all platforms, as approved (D-390), and add a
**macOS native chrome layer**:
- **Dependencies:** `pyobjc-core`, `pyobjc-framework-Cocoa` and `pyobjc-framework-UserNotifications`, all with the marker
  `sys_platform == "darwin"`, pinned in `gui/uv.lock`.
- **Module:** one module, `agentprov_gui/platform/macos.py`.
- **Not a new toolkit:** this changes D-390's dependency list and adds one module.
- **Kept explicitly:**
  - D-391 (separate `gui/` project, core allowlist);
  - D-392 (detached jobs);
  - D-396 (S1–S14), with the S11 amendment of D-448.

**Re-evaluation trigger:** reconsider (b′) if any of these happens:
- a Qt release breaks the native toolbar attachment and no fix lands within one Qt patch release;
- Qt drops the Tahoe code paths;
- the user judges the measured M4 look insufficient.

Reconsider dropping the PyObjC parts if Qt ships public `NSToolbar` or glass APIs (QTBUG-85310).

### 2.6 Scope and rules of the native layer

- **What it does** (all on the main thread, after `QApplication` exists, before the first `show()` of the main window):
  1. **`NSToolbar`** on each main window:
     - identifier `main` with `toolbarStyle = unified`, icon-only display mode, autosave on;
     - `NSToolbarItem`s whose image is an SF Symbol and whose action calls the **same `QAction`** that the menu and
       shortcuts use (one action registry);
     - an `NSToolbarItemGroup` for related actions;
     - an `NSSearchToolbarItem` whose text goes into the screen's search model (the user's own input, not data);
     - `window.subtitle`;
     - the activity item (§3.3), as a custom view.
  2. **Dock tile:** badge (also available through `setBadgeNumber`) and a progress `contentView` (§6).
  3. **Notifications:** `UNUserNotificationCenter`, only in a signed bundle (§6).
  4. **Window menu** items through the AppKit selectors `performMiniaturize:`, `performZoom:` and `arrangeInFront:`; the
     system adds Move & Resize and Full Screen Tile itself.
  5. **Display flags:** `NSWorkspace` Reduce Transparency, Differentiate Without Colour, Reduce Motion (cross-check),
     Increase Contrast, and `NSWorkspace.accessibilityDisplayOptionsDidChangeNotification`.
- **Fallback:**
  - Setting › Experimental › "Native macOS toolbar" (**on** by default on macOS), plus the environment variable
    `AGENTPROV_GUI_NATIVE_CHROME=0`.
  - When the module fails to import or a smoke check fails (no `NSWindow`, toolbar not attached, `contentLayoutRect`
    not shrunk), the GUI uses the Qt toolbar of M3 and logs one line. Every action stays reachable from the menu bar.
- **Spike, not a commitment:** embedding a native `NSOutlineView` sidebar with `QWindow.fromWinId` +
  `createWindowContainer` (Qt 6.12 embeds foreign `NSView`s automatically). Time-boxed in G1. Kept only if focus,
  VoiceOver order and resizing behave. Otherwise the Qt-drawn sidebar of M3 is used.
- **Tests:**
  - a macOS-only smoke test (`QT_QPA_PLATFORM=cocoa`, skipped elsewhere): the toolbar is attached, every item maps to an
    existing `QAction`, and the content rect shrinks;
  - the S15 lint: PyObjC imported only in `platform/macos.py`;
  - the import-boundary test (D-448).

### 2.7 What the native layer does not change

- Content views (tables, trees, graph, logs, forms) stay Qt Widgets built through `ui/safe.py`.
- Every data string still passes `escape_untrusted_line` or `quote_untrusted` (S1–S3).
- No PyObjC object ever receives corpus text, except the window title and subtitle, which are passed through
  `escape_untrusted_line` and truncated first (S3, S15).

## 3. Q2: HIG mapping per screen

### 3.1 Window model (macOS)

| Element | macOS (HIG) | Windows 11 (Fluent) | GNOME (libadwaita) | KDE (Breeze, Qt Widgets) |
|---|---|---|---|---|
| Main window | sidebar \| content \| inspector, as split panes with a 1-pt divider [S3]; inspector a trailing pane [S4] | NavigationView left pane + content + details pane [W1] | `AdwNavigationSplitView`-like split, header bars [G1] | sidebar leading the content, toolbar above [K1] |
| Navigation | sidebar sections: **Corpora** (each opened corpus), **Jobs** (Runs, Logs, System), **Release** (Licences, Package) [S1] | nav items Viewer, Runs, Logs, System, Licences, Package; **Settings pinned at the bottom**; corpus picker in the Viewer page [W1, W3] | sidebar list; **primary menu above the list** [G2] | sidebar list; menu bar |
| Settings | separate **Settings window**, ⌘, from the App menu, pane toolbar, title = pane name, reopens on the last pane [S21] | full page with SettingsCards; changes apply at once [W3] | Preferences dialog from the primary menu, Ctrl+, [G2, G3] | Configure dialog (`KConfigDialog` style), Ctrl+Shift+, [K2] |
| About | App menu › About AgentPROV, standard About window [S8] | an expander at the bottom of Settings [W3] | primary menu › About AgentPROV (AdwAboutDialog pattern, with a Troubleshooting section) | Help › About AgentPROV |
| Run live | **New Live Run** window (⌘L, File menu): self-contained work = window [S5]; the estimate and consent is a **sheet** on it | a secondary window; consent is a ContentDialog [W11] | a secondary window; consent dialog | a secondary window; dialog |
| R1/R2 confirmations, purge | **sheets** on the owning window; alert form for destructive or warning cases; Cancel never the default [S5, S7] | ContentDialog: Close button rightmost, specific verbs [W11] | dialog: Cancel on the left, Return = affirmative unless destructive | QDialog with the KDE button order (Qt default) |
| Graph and job dashboard in their own window | "Open in New Window" (⌥-double-click, context menu); not by default [S-windows] | "Open in new window" | new window | new window |
| Job status | **toolbar activity item** (Xcode-style), sidebar "Runs" count; nothing at the bottom edge | in-window InfoBar or status strip, mirrored on the taskbar button | header-bar indicator + toasts | status bar (KDE apps keep one) |

### 3.2 Menu bar (macOS; Qt `QMenuBar` with native roles, plus Window-menu items from the native layer)

| Menu | Items (shortcut) |
|---|---|
| **AgentPROV** | About AgentPROV · Settings… (⌘,) · Services · Hide AgentPROV (⌘H) · Hide Others (⌥⌘H) · Show All · Quit AgentPROV (⌘Q; jobs keep running: §4 of design) |
| **File** | New Job ▸ (Import…, Derive…, Recompute…, Validate…, Verify…, Render…, Fetch…, Package…) · New Live Run… (⌘L) · Open Corpus… (⌘O) · Open Recent ▸ · Close Window (⌘W) · Export Graph… (render job, ⇧⌘E) · Copy Command (⌥⌘C) |
| **Edit** | Undo/Redo where a form has them · Cut/Copy/Paste · Select All (⌘A) · Find ▸ (Find… ⌘F, Find Next ⌘G, Find Previous ⇧⌘G, Use Selection for Find ⌘E, Jump to Selection ⌘J) · Dictation and Emoji added by AppKit (needs the menu titled "Edit"; Qt maps it) |
| **View** | Show/Hide Sidebar (⌃⌘S, *unverified* system default; Mail-style) · Show/Hide Inspector (⌥⌘I, HIG table; SwiftUI's `InspectorCommands` uses ⌃⌘I) · Show/Hide Toolbar (⌥⌘T) · Show Content (per pane; deliberately no shortcut, so content is never revealed by a stray key; never persisted, S2) · Zoom In/Out/Actual Size/Fit (⌘+ ⌘− ⌘0 ⌘9; *unverified* as HIG standard, Preview convention) · Text Size ▸ Bigger/Smaller/Default (⌥⌘+ ⌥⌘− ⌥⌘0) · Enter Full Screen (⌃⌘F) |
| **Go** | Viewer (⌘1) · Runs (⌘2) · Logs (⌘3) · System (⌘4) · Licences (⌘5) · Package (⌘6) · Back (⌘[) · Forward (⌘]) |
| **Job** | Pause (Drain) (⌥⌘P) · Stop… (⌘.) · Resume (⌥⌘R) · Open in Viewer · Open Log · Reveal Job Folder in Finder |
| **Window** | Minimize (⌘M) · Zoom · Move & Resize ▸ / Full Screen Tile ▸ (system) · Bring All to Front · window list (provided by AppKit once `NSApp.windowsMenu` is set by the native layer) |
| **Help** | AgentPROV Help (opens the bundled plain-text help in-app: no web view, no browser) · Keyboard Shortcuts · Acknowledgements |

On Windows there is no menu bar. Commands live in the CommandBar, the "…" overflow and the context menus, and keyboard
accelerators are shown in tooltips [W4]. GNOME has no menu bar either: it uses a primary menu with Preferences,
Keyboard Shortcuts, Help and About AgentPROV [G2]. KDE keeps a menu bar, which can be hidden with Ctrl+M [K1, K2].

### 3.3 Per screen

The mockups are linked by number from [`mockups/README.md`](mockups/README.md). Toolbar items run from leading to
trailing. "Sheet" means a window-modal sheet.

| Screen | macOS structure | Toolbar | Sheets, windows, popovers | Keys | Windows | GNOME / KDE |
|---|---|---|---|---|---|---|
| **Viewer** (01) | the sidebar selects a corpus; content = filter row (closed-vocabulary pop-ups + "Issues only") + executions table; inspector = the selected execution (grouped sections, Show content switch) | sidebar toggle · title "corpus-x", subtitle "state · executions" · activity item · Reload · **Run Live…** (prominent) · Inspector toggle · Search (filters ids; tokens for facets) | opening a corpus without verification shows an inline banner, not a modal; Return or double-click opens the detail | ⌘F search, ↑↓ rows, Return open, Space toggles the inspector focus | NavigationView + CommandBar (Run live, Refresh F5, Filter, Export) + details pane; status strip (20) | primary menu, header-bar title and subtitle, search toggle (21); KDE: menu bar + toolbar |
| **Execution detail** (02) | the content column becomes a navigation stack (Back/Forward); a **segmented control in the toolbar** with the tabs Graph, PROV-JSON, AER, SEM, Register, Validation, Raw (≤ 7, HIG) | back/forward · title "ex_…", subtitle "corpus · source" · tab segments · Export Graph · Inspector | the hover popover (§5); "Show content" per pane | ⌘[ ⌘] navigation; ⌃Tab/⌃⇧Tab next/previous tab | Pivot/TabView on the page | `AdwViewSwitcher` in the header bar; KDE `QTabBar` |
| **Runs** (03) | content = job list (top) + dashboard of the selected job (bottom); inspector = job facts, argv (copyable), actions | New Job ▾ · group Pause, Stop, Resume · **Run Live…** · Inspector · Search | New Job opens the command form as a **sheet** with its tier badge and argv preview; R1/R2 confirmations are sheets | ⌥⌘P drain, ⌘. stop (asks), ⌥⌘R resume | same layout; taskbar progress | same; GNOME toasts for job end while focused |
| **Run live** (04) | own window, segmented steps Configure / Estimate / Monitor; grouped form | — | Tune… and Preflight Only… as sheets; **Estimate and consent as a sheet** with the consent tick (tier R2) | ⌘L opens; ⌘Return starts (only when consent is ticked) | secondary window + ContentDialog | secondary window + dialog |
| **Logs** (05) | content = level/stage/code filter row + virtualised plain-text table; a status line with buffer and lag facts (not a control bar) | Copy · Export · Pause following · Search (tokens: ex, code) | none | ⌘F, ⌘G, ⌥⌘P pauses following | same; Ctrl+F, F3 | same |
| **System** (06) | content = CPU-per-core cards, memory, disk, process table of the selected job | Pause sampling · Inspector | none | — | same | same |
| **Licences** (07) | segmented Included / Excluded; table with flag chips (text + colour); inspector = joined record and the rule behind each flag | Filter · Inspector · Search | none (read-only) | — | same | same |
| **Package** (08) | a step list (assistant pattern) at the left of the content; the current step at the right; Back / Continue at the bottom-right of the content | Reload | Seal and Deposit confirmations as sheets (R1); the finish page states that nothing is uploaded | ⌘Return Continue | wizard pattern (steps + Next) | same |
| **Settings** (09, 10) | Settings window; panes General, Appearance, Viewer, Jobs, Compute, Live, CI, Experimental; grouped form rows; changes apply at once, except the R2 actions (CI_ON_PUSH), which confirm with a sheet | pane toolbar (not customisable) [S21] | Set Key… as a sheet (secure field); R2 confirmation sheets | ⌘, opens; ⌘W closes | Settings page (SettingsCards, About expander at the bottom) | Preferences dialog (GNOME) / Configure dialog (KDE) |
| **Conformance-check warning** (11, design §8.3a) | unticking the box shows an **alert sheet**: caution symbol, the §8.3a text, buttons **Keep the Check** (default) and **Skip the Check** (destructive style); logged in `job.json` and Logs | — | alert sheet each time | Esc or ⌘. = Keep | ContentDialog: Close = "Keep the check" | dialog, the destructive button not the default |
| **About** (12) | standard About window: icon, name, versions, formats, commit, repository **as plain text**, MIT, author, Acknowledgements… | — | Acknowledgements opens a plain-text window | — | About expander in Settings | AdwAboutDialog pattern / KAboutData dialog |

### 3.4 Keyboard shortcuts per platform

| Command | macOS | Windows | GNOME | KDE |
|---|---|---|---|---|
| Settings / Preferences | ⌘, [S9] | Ctrl+, (extra; Settings is a nav item) | Ctrl+, [G3] (Qt leaves it empty on GNOME: bind it explicitly [Q18]) | Ctrl+Shift+, [K2] |
| Find / filter | ⌘F, ⌥⌘F to the search field | Ctrl+F, F3 next [W4] | Ctrl+F | Ctrl+F |
| Reload | ⌘R | F5 or Ctrl+R [W4] | Ctrl+R | F5 [K2] |
| Run live | ⌘L | Ctrl+L | Ctrl+L | Ctrl+L |
| Toggle sidebar | ⌃⌘S (*unverified* default) | — (pane button) | F9 [G3] | — |
| Toggle inspector | ⌥⌘I [S9] | Ctrl+I | Ctrl+I | Ctrl+I |
| Zoom graph | ⌘+ ⌘− ⌘0 ⌘9 | Ctrl+Plus/Minus/0 [W4] | Ctrl+Plus/Minus/0 | Ctrl+Plus/Minus/0 |
| Stop job | ⌘. (asks) | Ctrl+Shift+X (asks) | Ctrl+Shift+X | Ctrl+Shift+X |
| Full screen | ⌃⌘F | F11 | F11 | Ctrl+Shift+F [K2] |
| Next pane | ⌃F6 (Full Keyboard Access) | F6 / Shift+F6 [W4] | F6 | F6 |
| Keyboard shortcuts list | Help › Keyboard Shortcuts | ? in Settings | Ctrl+? [G3] | Ctrl+Alt+, [K2] |

## 4. Q3: visual system

### 4.1 Typography

- **macOS:**
  - the system font through `QFontDatabase.systemFont(GeneralFont)` (measured: `.AppleSystemUIFont` 13 pt = SF Pro) and
    `FixedFont` (the user's fixed-pitch font; measured Menlo 10 pt).
  - **Licence:** the SF fonts (licence EA1370) may be used only for mock-ups of interfaces for Apple platforms, and may
    not be embedded or redistributed [S27]. The app therefore **never bundles** SF Pro or SF Mono, and uses them only
    through the system.
- **Text styles:**
  - Mapped to Apple's macOS table [S10]: Large Title 26/32, Title 1 22/26, Title 2 17/22, Title 3 15/20, Headline 13
    bold, Body 13/16, Callout 12/15, Subheadline 11/14, Footnote 10/13, Caption 10/13.
  - Usage: body 13 (tables, forms), headline 13 bold (group titles), title 3 15 (window title in the toolbar), title 2
    17 (inspector title), caption 11 (secondary rows).
  - The minimum is 10 pt.
- **Windows:**
  - Segoe UI Variable through the system. It must not be redistributed or used off Windows [W10].
  - The type ramp is Caption 12, Body 14, Body Strong 14, Subtitle 20, Title 28 [W5].
  - Fallback where it is missing (Windows 10): Segoe UI, then Selawik (OFL-1.1).
- **Linux:**
  - the system font through the platform theme: Adwaita Sans (GNOME 48+; OFL-1.1, derived from Inter), Cantarell on
    older GNOME, Noto Sans 10 pt on KDE;
  - sizes relative to the system font [G4], never hard-coded.
- **Monospace:** the system fixed font on every platform: Menlo or SF Mono on macOS, Cascadia Mono or Consolas on
  Windows, Adwaita Mono, Hack or DejaVu Sans Mono on Linux.
- **Bundled fonts:** none. Inter and JetBrains Mono (both OFL-1.1) are the documented fallback if a platform lacks a
  usable font; bundling them would add their licence texts to `THIRD_PARTY_NOTICES`.

### 4.2 Colour

- **Chrome:** colours come only from `QPalette` roles (Window, Base, AlternateBase, Text, PlaceholderText, Highlight,
  **Accent**). These follow Light, Dark and Increase Contrast and the user's accent colour on macOS (measured), Windows
  and GNOME 47+ (through the portal [G6]).
- **The app's accent** is the system accent. Following the HIG it applies only when the user picks Multicolour [S11]. No
  custom tint.
- **Semantic status colours:** on macOS, read `NSColor.system{Green,Orange,Red,Blue,Yellow,Purple,Gray}Color` through the
  native layer, so they follow Increase Contrast. On Windows and Linux, a token table with the same hues; the light,
  dark and IC values are from Apple's published table [S11], used as defaults:

  | Token | Light | Dark | IC light | IC dark | Shape (never colour alone) |
  |---|---|---|---|---|---|
  | `status.sealed` / ok | #34C759 | #30D158 | #008932 | #4AD968 | filled circle + check |
  | `status.issues` / warning | #FF8D28 | #FF9230 | #C55300 | #FFA056 | triangle + "!" |
  | `status.failed` / error | #FF383C | #FF4245 | #E9152D | #FF6165 | octagon + "×" |
  | `status.running` | #0088FF | #0091FF | #1E6EF4 | #5CB8FF | half-filled circle |
  | `status.draining` | #FFCC00 | #FFD600 | #A16A00 | #FEDF43 | circle + pause bars |
  | `status.degenerate` | #CB30E0 | #DB34F2 | #B02FC2 | #EA8DFF | diamond + bar |
  | `status.queued`, `excluded` | #8E8E93 | #8E8E93 | system grey | system grey | outline clock / outline minus |

  Every status cell shows the glyph **and** its word ("sealed", "with issues", …).
  - Several light hues are under 3:1 on white (for example #34C759 is about 2.2:1).
  - WCAG 1.4.11 treats them as non-essential because the word carries the meaning.
  - Increase Contrast swaps in the IC column.
- **Surfaces, sampled from the SwiftUI reference (M5)** and used where Qt draws its own surfaces:

  | Surface | Light | Dark |
  |---|---|---|
  | sidebar and inspector | #EEEDEC | #2A2A2C |
  | inspector group | #E7E6E5 | #323234 |
  | content | #FFFFFF | #1E1E1E |
  | alternate row | #F4F5F5 | #262628 |
  | unemphasised selection | #DCDCDC | #3A3A3C |

  The dark values are neutralised: the measured inactive window was tinted by the wallpaper. On macOS the build reads
  `NSColor.windowBackgroundColor`, `controlBackgroundColor`, `alternatingContentBackgroundColors` and
  `unemphasizedSelectedContentBackgroundColor` through the native layer. The table is the fallback and the source for the
  other platforms' "follow the system" mapping.
- **Window-wide translucency:** none, beyond what AppKit gives the native toolbar. Reduce Transparency is still read, so
  the drawn surfaces never fake vibrancy.

### 4.3 Spacing and layout

| Metric | macOS | Windows 11 | GNOME |
|---|---|---|---|
| Base grid | 4 pt (HIG gives no numeric grid [S14]; Apple's 20×20 / 28×28 control sizes [S18]) | 4 epx [W12] | 6 / 12 px (Adwaita) |
| Window minimum | 900 × 560 | 640 (NavigationView minimal) | 360 wide (adaptive) |
| Sidebar width | 232 (min 180, max 320) | 320 open / 48 compact [W1] | 260 |
| Inspector width | 292 (min 240, max 420) | 300 | 300 |
| Toolbar height | 52 (system) | title bar 48 with search [W2] | header bar 47 |
| Table row / header | 24 / 28 (NSTableView regular) | 32–40 / 32 | 34 / 32 |
| Sidebar row | 28 (follows the user's sidebar icon size: small 24, medium 28, large 32 [S1]) | 36–40 | 36 |
| Grouped form row | 30, group radius 10, 14 between groups | SettingsCard 64 | AdwActionRow 50 |
| Content margins | 16 (tables edge to edge) | 24 | 12 |
| Corner radii | system (window, sheets); controls 7, groups 10, capsules h/2 | 4 (controls), 8 (layers) | 6 (controls), 12 (cards) |

### 4.4 Icons

- **macOS: SF Symbols** through `QIcon.fromTheme(name)`. All 52 names were checked present (M13). SF Symbols may be used
  only in interfaces for Apple platforms, never in app icons or logos [S15, S28]. They are rendered by the system and
  never exported or bundled.
- **Windows and Linux: Phosphor Icons** (MIT [L1]), regular weight, bundled as SVG with the licence text in
  `THIRD_PARTY_NOTICES`. Reasons:
  - one set for both platforms;
  - a weight axis like SF Symbols';
  - neutral next to both Fluent and Adwaita.

  Rejected:
  - **Segoe Fluent Icons:** Windows-only and not redistributable [W7]. Qt's own `ThemeIcon` still uses it on Windows for
    standard dialog icons.
  - **Fluent UI System Icons** (MIT [L3]): look Windows-specific on GNOME.
  - **Freedesktop themes:** coverage varies, and Windows has none.
  - **Lucide** (ISC [L2]): one weight. It is the second choice.
  - **Material Symbols:** an Android look.
  - **Remix Icon:** its custom licence of 2026 [L4].

  The Phosphor names are to be verified against the pinned release at build time.

| Action / item | SF Symbol (macOS) | Phosphor (Win/Linux) |
|---|---|---|
| Toggle sidebar / inspector | `sidebar.left` / `sidebar.right` | `sidebar-simple` |
| Run live / pause / stop / resume | `play.fill` / `pause.fill` / `stop.fill` / `arrow.uturn.backward` | `play` / `pause` / `stop` / `arrow-counter-clockwise` |
| Reload | `arrow.clockwise` | `arrow-clockwise` |
| New job | `plus` | `plus` |
| Export / copy | `square.and.arrow.up` / `doc.on.doc` | `export` / `copy` |
| Search / filter | `magnifyingglass` / `line.3.horizontal.decrease` | `magnifying-glass` / `funnel-simple` |
| Corpus / Licences / Package | `square.stack.3d.up` / `checkmark.seal` / `shippingbox` | `stack` / `seal-check` / `package` |
| Runs / Logs / System | `play.circle` / `text.alignleft` / `gauge.with.dots.needle.33percent` | `play-circle` / `text-align-left` / `gauge` |
| Settings panes | `gearshape`, `circle.lefthalf.filled`, `eye`, `cpu`, `key`, `arrow.triangle.branch`, `hammer` | `gear-six`, `circle-half`, `eye`, `cpu`, `key`, `git-branch`, `hammer` |
| Graph zoom / fit / focus | `plus.magnifyingglass` / `minus.magnifyingglass` / `arrow.up.left.and.arrow.down.right` / `scope` | `magnifying-glass-plus` / `-minus` / `arrows-out` / `crosshair` |
| Status | `checkmark.circle.fill`, `exclamationmark.triangle.fill`, `xmark.octagon.fill`, `circle.lefthalf.filled`, `pause.circle.fill`, `clock`, `minus.circle`, `diamond.fill` | `check-circle`, `warning`, `x-circle`, `circle-half`, `pause-circle`, `clock`, `minus-circle`, `diamond` |
| Network (R2) / lock / info | `network` / `lock.fill` / `info.circle` | `globe` / `lock` / `info` |

- **Rules:**
  - toolbar items are symbol-only with a tooltip and an accessible name;
  - sidebar symbols are tinted with the accent [S1];
  - on macOS 27 menu items carry no symbols by default [S29], and the app adds none.

### 4.5 Motion

- **Default:** system animations only (sheets, popovers, sidebar collapse); the app adds none for frequent actions [S16].
- **Graph:** "Fit", "Focus" and "Reveal" animate the view transform for ≤ 200 ms (ease-out). They are **instant** when
  `QStyleHints.accessibility().motionPreference()` is reduced (Qt 6.12, measured present) or `NSWorkspace` reports
  Reduce Motion.
- **Progress:** bars move in steps on each heartbeat, never as a continuous animation. Indeterminate spinners are used
  only before the first heartbeat.
- **Windows:** Fluent durations (167–333 ms) on Windows [W-motion]. GNOME's `enable-animations` is read by Qt 6.12.

### 4.6 App icon

- **macOS 26+:** a layered 1024 × 1024 icon made in Icon Composer:
  - a background layer plus three foreground shapes (an entity oval, an activity rectangle and an agent pentagon in the
    W3C hues, connected as in PROV-DM);
  - no text, no SF Symbols, no photos;
  - the system applies the mask, highlights and the Dark, Clear and Tinted variants [S17];
  - concept in mockup 13.
- **Fallbacks:** an `.icns` for older systems; on Windows an `.ico` (16–256 px); on Linux hicolor PNG and SVG plus a
  symbolic SVG.
- **Before release:** the icon designer checks it against the HIG.

## 5. Q4: the PROV graph in a native style

- **Notation:**
  - shapes and hues follow `render.style` (design §7, research Q5): entity an oval in #FFFC87, activity a box in
    #9FB1FC, agent a pentagon "house" in #FED37F;
  - evidence class as line style (O solid, D dashed, I dotted);
  - bundle as colour plus a cluster frame;
  - the "Accessible" light palette is the default.
- **Light and Dark:**
  - The canvas is `Base` (#FFFFFF / #1E1E1E), with a 24-pt dotted grid at 35 % of the tertiary label colour, hidden
    below LOD 0.5.
  - Fills keep their W3C hue in both appearances; node text stays black on the fills (10.2–19.5:1).
  - Strokes and edges switch to the measured dark variants of design §12 (≥ 6.6:1 on #1E1E1E).
  - Increase Contrast adds 2-px strokes, and moves "W3C exact" or "Accessible" relation colours to their darker variants
    (agent relations #8A6408, influence #5E5E5E).
- **Selection:**
  - an accent-colour ring (3 pt, 6 pt outset, rounded) **plus** a doubled stroke width on the node, so selection does
    not rely on colour;
  - the incident edges get thicker;
  - the inspector shows the element: QName, types, rule, evidence class, bundle, degree, relations, and the AER source
    locator with "Show AER Record".
  - Mockup 02.
- **Hover:**
  - after 400 ms, a `Qt.Popup` styled as a popover with an arrow towards the node (an `NSPanel` on macOS; Qt has no
    `NSPopover`);
  - a plain-text table; values that are data appear as `‹text, n chars, sha256:…›` until Show content (design §7.2);
  - a click pins it to the inspector instead of keeping a floating panel; Esc closes it.
- **Zoom and pan (macOS):**
  - **pinch:** `QNativeGestureEvent.ZoomNativeGesture`, zooming around the cursor;
  - **smart zoom** (two-finger double-tap): toggles Fit and 100 %;
  - **two-finger pan:** `QWheelEvent.pixelDelta` with phases and momentum;
  - **⌥-scroll:** zoom with a mouse wheel;
  - **⌘+ ⌘− ⌘0 ⌘9:** keyboard zoom.
  - Rotation is ignored. Minimum and maximum zoom are 5 % and 800 % [S20].
  - The cursor is the open hand on the background and the closed hand while dragging [S20].
- **Windows and Linux:** Ctrl+wheel zooms and the wheel pans. Windows precision touchpads and Linux Wayland pinch arrive
  as Ctrl+wheel or native zoom gestures; *unverified* per device.
- **Controls:**
  - a floating glass group at the bottom-right (zoom −, +, Fit, Focus) and the legend at the bottom-left; both are
    controls over content, so glass is allowed [S13];
  - on Windows and Linux they are plain toolbar buttons;
  - bundle toggles and the evidence filter sit in a row above the canvas.

## 6. Q5: native platform integration

| Feature | macOS | Windows | Linux |
|---|---|---|---|
| Menu bar, Window menu | §3.2; Window menu items from the native layer | no menu bar; CommandBar + overflow | GNOME: primary menu; KDE: menu bar |
| Badge | `setBadgeNumber(n running)` (measured) | `setBadgeNumber` → taskbar overlay [Q11] | `setBadgeNumber` (Unity LauncherEntry where supported) |
| Progress for running jobs | `NSDockTile.contentView` with a progress bar for the job shown in the activity item (M7); cleared at the end | `ITaskbarList3::SetProgressValue/State` through ctypes (normal, paused = draining, error = failed) [W8]; hidden in contrast themes, so it is always mirrored in-window | Unity `LauncherEntry` over QtDBus: native in Plasma [K3]; GNOME only with Dash to Dock |
| Notification when a long job ends | `UNUserNotificationCenter` (signed bundle; M8): "Job finished: import corpus-y: ok", plus actions "Open in Viewer" and "Show Log"; only for jobs longer than 2 min and only when the app is not frontmost; `passive` interruption level for success, `active` for failure; never data text | toast (needs a Start-menu shortcut with an AppUserModelID, set by the installer [W9]) | `org.freedesktop.Notifications` over QtDBus (GNOME/KDE rules [G7, K4]) |
| Fallback (dev runs, unsigned) | Dock bounce (`QApplication.alert`) + an in-app banner | taskbar flash | urgency hint |
| **As built (GR-67, 2026-10-21)** | notification authorisation is requested when the native layer is installed in a signed bundle; the text is "Job finished" plus the command, the corpus id (escaped) and the outcome; the interruption levels (`passive`/`active`) and the actions "Open in Viewer" and "Show Log" are **not built** | not built | not built |
| Multiple windows | yes: main windows (⌘N, one per corpus), graph and dashboard windows | yes | yes |
| Window tabs | **no** (Qt forces `tabbingMode = disallowed`, QTBUG-110782) | n/a | n/a |
| State restoration | `QSettings`: geometry, splitter, sidebar and inspector state, last corpus and pane per window; honours "Close windows when quitting an app" (read through the native layer). The Show content toggles are never restored (S2) | same | same |
| Full Screen, Split View, Stage Manager | native Spaces full screen (⌃⌘F); tiling from the system Window menu; sensible minimum sizes; secondary windows `fullScreenAuxiliary` | maximise / Snap layouts | WM-managed |
| Proxy icon | `setWindowFilePath(corpus root)` for an opened corpus | n/a | n/a |
| Quick Look / Spotlight | **not provided.** Previews need a sandboxed Swift `.appex`; macOS has no working `CSImportExtension` (Spotlight needs an `.mdimporter`); corpora are plain folders without a package UTType [S43]; a preview would also be a new display surface for untrusted text | n/a | n/a |
| Services, Share | none | none | none |

## 7. Q6: accessibility

- **Names:**
  - every widget made by `ui/safe.py` requires an accessible name; the S1 lint is extended to fail on a widget without
    one;
  - toolbar items carry labels and tooltips;
  - status cells expose "status: with issues";
  - graph legend items expose their meaning.
- **Graph:**
  - the **Elements** list (design §12) stays the primary accessible view: a table of id, type, evidence class, bundle
    and degree, sorted by rank, with selection kept in sync both ways;
  - in addition, a custom `QAccessibleInterface` for the graph view exposes nodes as children with role, name ("call:1,
    ToolCallRequest, observed"), rectangle and state. PySide6 exposes the class as subclassable [Q16]. Lifetime under the
    Python garbage collector is *unverified*: a G1 test with VoiceOver decides, and the list alone is the fallback;
  - focus moves along edges: ←/→ go to the predecessor or successor in time order, Tab to the next element in list
    order;
  - VoiceOver announces the selection and the hover facts.
- **Keyboard:**
  - every action has a menu item, and most have a shortcut;
  - the tab order is explicit;
  - Full Keyboard Access is supported (⌃F5 reaches the toolbar, ⌃F6 the panes);
  - sheets have default and cancel buttons (Return and Esc / ⌘.);
  - the graph is fully keyboard-operable.
- **Text size:**
  - macOS has **no Dynamic Type** for AppKit [S10, S-DTS];
  - the app offers View › Text Size (85–200 %) and Settings › Appearance › Text size; HIG: enlarge to at least 200 %
    [S18];
  - tables scale their row height with it;
  - Windows text scaling and GNOME and KDE font scaling come through the system font.
- **Contrast:**
  - text ≥ 4.5:1, non-text ≥ 3:1 (design §12);
  - Increase Contrast is detected (`contrastPreference`) and swaps the IC tokens and the 2-px graph strokes;
  - Windows contrast themes use only system colours: no custom colour is drawn when `QStyleHints` reports high contrast
    [W6].
- **Colour blindness:** status always has a shape and a word; the bundle has a frame and a legend; the evidence class
  has a line style. Differentiate Without Colour (native layer) additionally adds bundle letters (C, I, A) to node
  labels at LOD ≥ 0.5.
- **Tests:**
  - an offscreen test checks that every widget has an accessible name;
  - a manual VoiceOver and Narrator/Orca checklist goes into the G1/G2 exit criteria: open a corpus, filter, open an
    execution, walk the graph, start a scripted job.

## 8. Q7: packaging on macOS

- **Distribution:**
  - **Developer ID Application** signing;
  - **hardened runtime**, secure timestamp, no `get-task-allow`;
  - **notarised** with `notarytool` and stapled [S36], distributed as a `.dmg` or `.zip` outside the Mac App Store.
- **Not sandboxed:** the App Sandbox is required only for the Mac App Store [S31, S34, S47], and it breaks the design
  (M11, M12):
  - children inherit the sandbox [S32];
  - the CLI lives in the user's checkout, `dot` in Homebrew, jobs in `~/.agentprov`;
  - live containment uses `sandbox-exec`, which cannot nest [S48];
  - App Review 2.4.5(iii) forbids processes that outlive the app without consent, but detached jobs are the design.
- **The Mac App Store is rejected.**
- **Entitlements:**
  - start with **none**;
  - add `com.apple.security.cs.disable-library-validation` and/or `cs.allow-unsigned-executable-memory` only if the G5
    bundle test shows a need (test by elimination) [S35];
  - never `allow-jit` unless measured;
  - no sandbox entitlements.
- **Launcher SDK (D-441):**
  - the main executable must be linked against the **current macOS SDK (≥ 26)**;
  - PyInstaller's prebuilt bootloader SDK must be checked (`otool -l`). If it is older, rebuild the bootloader from
    source on the build Mac with the current Xcode;
  - for development, an optional `gui/tools/launcher.c` (a 30-line `Py_BytesMain` wrapper, as in M2) gives the current
    look under `uv run`; without it the GUI works with the compatibility look;
  - **Qt ≥ 6.12.1 on macOS 27** (QTBUG-150017).
- **Keychain:**
  - `keyring` writes generic passwords into the login keychain with an ACL trusting the creating executable [L11, S38];
  - keys entered in the **signed bundle** are trusted by its stable Developer ID designated requirement, so there is no
    prompt after updates;
  - a key created during `uv run` (a different executable) prompts once when the bundle first reads it;
  - the CLI never reads the keychain: keys still travel only on stdin through `--env-stdin` (D-395).
- **Notifications** need the signed bundle (M8). Dev runs use the fallback (§6).
- **Gatekeeper on macOS 15+:** an unsigned or ad-hoc build from someone else must be allowed in System Settings › Privacy
  & Security [S37]. So unsigned bundles are for the developer's own Mac only (design §16 question 1 stays open: a Developer
  ID is needed for any distribution).
- **LGPL relinking** (design §13) is unchanged. PyObjC is MIT (notice only).

## 9. Per-platform differences (summary)

| Topic | macOS | Windows 11 | GNOME | KDE Plasma |
|---|---|---|---|---|
| Qt style | `macos` (+ native chrome layer) | **`windows11`** (default since Qt 6.7 [Q17]; Fusion fallback on Windows 10) | Fusion with the portal palette (`gtk3` theme if available) | Breeze when installed (system), else Fusion |
| Navigation | sidebar with Corpora / Jobs / Release | NavigationView pane, Settings at the bottom | sidebar + primary menu above it | sidebar + menu bar |
| Toolbar | native `NSToolbar` (glass) | CommandBar in the page; search in the title bar | header bar buttons | `QToolBar` |
| Settings / About | Settings window ⌘, / App menu | Settings page, About expander | Preferences / About from the primary menu | Configure dialog / Help › About |
| Job status | toolbar activity item + Dock | InfoBar strip + taskbar progress | header indicator + toasts + LauncherEntry (if supported) | status bar + task manager progress |
| Confirmations | sheets | ContentDialog | dialog | dialog |
| Icons | SF Symbols (system) | Phosphor (bundled) | Phosphor | Phosphor |
| Fonts | system SF (never bundled) | system Segoe UI Variable | system Adwaita Sans / Cantarell | system Noto Sans |

## 10. Security notes (D-448)

- **S11 amended:**
  - The static ban on GUI sources importing `socket`, `ssl`, `http`, `urllib.request`, `QtNetwork` and `QtWebEngine*`
    stays.
  - The fresh-interpreter `sys.modules` check keeps banning `ssl`, `_ssl`, `http.client`, `urllib.request`, `QtNetwork`
    and `QtWebEngine*`.
  - It allows `socket` and `_socket` **only** when `objc._convenience` imported them (asserted by checking
    `sys.modules['objc._convenience']`) and only on macOS.
  - QtDBus (Linux notifications and LauncherEntry) is local IPC, not network. It is allowed only in
    `platform/linux.py`.
- **S15 (new): the native layer.**
  - PyObjC imports are allowed only in `agentprov_gui/platform/macos.py`; ctypes Windows calls only in
    `platform/windows.py`.
  - These modules receive only fixed strings, numbers and already-escaped single-line ids (window title and subtitle,
    notification text built from templates plus `escape_untrusted_line` ids).
  - Never content, never an `NSAttributedString`, never an `NSTextView`.
  - Notifications carry no corpus text and no paths beyond the corpus id.
  - The `NSSearchToolbarItem` text is user input and goes only into the in-process filter model.
  - **Test:** an AST lint over `gui/src`.
- **Unchanged:** S1–S10, S12–S14. If a Swift front-end is ever reconsidered (b′), the Swift rules in §2.4 apply.

## 11. Changes to `design.md`

These are the earlier choices that change now that D-440..D-449 are approved as the direction. `design.md` gets a short addendum that points
here.

| `design.md` place | Was | Becomes |
|---|---|---|
| §0, §2.2 dependencies | PySide6-Essentials, psutil, keyring | + PyObjC (darwin only) (D-440) |
| §2.2 layout | `ui/`, `about.py`, … | + `platform/macos.py`, `platform/windows.py`, `platform/linux.py` |
| §6 navigation rail | Viewer, Runs, Logs, System, Licences, Package, then Settings and About at the bottom | per platform (§3.1): on macOS a sidebar with Corpora / Jobs / Release; Settings in its own window; About in the App menu |
| §6 status strip at the bottom | always | macOS: toolbar activity item (HIG: avoid bottom bars); Windows/Linux keep a strip |
| §6.6 Settings › Appearance "theme: Follow system, Light or Dark" | in-app override | kept, but "Follow system" is the default and recommended; the HIG discourages app-specific appearance switches [S12] |
| §6.6 "font scale" | font scale | Text size 85–200 % (§7) |
| §7.2 interaction | wheel zooms, left-drag pans | trackpad: pinch zooms, two-finger scroll pans; mouse: ⌥/Ctrl+wheel zooms (§5) |
| §7.2 popover | frameless child widget | `Qt.Popup` styled popover; a click pins it to the inspector |
| §11 S11 | no `socket` in `sys.modules` | amended (D-448) |
| §11 | S1–S14 | + S15 |
| §12 style | macOS native, **Fusion on Windows and Linux** | `windows11` on Windows 11 (verified [Q17]), Fusion fallback; Breeze on KDE when present (D-449) |
| §12 colour tokens | PROV notation + dark variants | + status tokens with IC values, surface tokens, IC graph strokes (D-443, D-444) |
| §13 macOS bundle | signed, notarised | + not sandboxed, Developer ID only, **bootloader/launcher linked against SDK ≥ 26**, Qt ≥ 6.12.1 on macOS 27, notifications need the signed bundle (D-441, D-447) |
| §15 phases | G1–G5 | G1 adds the native toolbar and the sidebar spike; G2 adds Dock progress and notifications; G5 adds the bootloader SDK check |

## 12. Mockups

- **Format:** 30 SVG files (15 screens × Light and Dark), 1360 × 880, under [`mockups/`](mockups/README.md), plus the 10
  measured screenshots under [`mockups/evidence/`](mockups/evidence/).
- **Data:** placeholder only (`ex_0001`, `src-a`, `corpus-x`, `model-a`, `api.endpoint-a.example`, `‹input dir›`).
- **Icons:** generic placeholder glyphs that stand for the SF Symbol or Phosphor names of §4.4, so no Apple or third-party
  artwork is reproduced.
- **Fonts:** the files name the system font stacks (`-apple-system`, `Segoe UI Variable`, `Adwaita Sans`) and embed no
  font.

## 13. Decisions (D-440 … D-449, approved as the direction 2026-10-14)

Summaries only. The full text, with the rejected alternatives and downstream effects, is in
`docs/architecture/DECISIONS.md`.

- **D-440:** PySide6 / Qt Widgets on all platforms, plus a darwin-only PyObjC native chrome layer (amends D-390).
  Rejected: a SwiftUI or AppKit front-end, a Swift front-end with a Python helper, a PyObjC AppKit front-end, wxPython,
  Toga, Compose, Avalonia, MAUI, and Qt-only.
- **D-441:** the main executable is linked against the current macOS SDK; Qt ≥ 6.12.1 on macOS 27.
- **D-442:** the window model and HIG mapping of §3 (sidebar sections, Settings window, About, Run-live window, sheets
  for R1/R2, toolbar activity item, menu bar).
- **D-443:** the visual system: system fonts only, semantic and status tokens with IC values, the 4-pt grid and metrics,
  SF Symbols on macOS, Phosphor elsewhere, Reduce Motion, the app icon.
- **D-444:** the PROV graph appearance and interaction (selection ring + stroke, popover, gestures, IC strokes).
- **D-445:** the integration matrix (Dock badge and progress, notifications, windows, no tabs, `QSettings` restoration,
  no Quick Look or Spotlight).
- **D-446:** the accessibility rules (names lint, graph accessible interface + Elements list, text size 85–200 %, shape +
  word for status).
- **D-447:** Developer ID + hardened runtime + notarisation; no App Sandbox; no Mac App Store; minimal entitlements.
- **D-448:** the S11 amendment for PyObjC's `socket` import, and the new rule S15.
- **D-449:** the Windows and Linux conventions of §3 and §9 (`windows11` style, NavigationView, About in Settings,
  GNOME primary menu, KDE menu bar, per-platform shortcuts).

**Downstream effects:**
- All touch only `gui/` (not yet built) and the GUI documents.
- None changes AER, SEM or PROV bytes, the compat oracle, any corpus, any core module, the core lock or any manuscript
  number.
- D-448 changes a GUI test only.
- The core boundary rule (D-391) is unchanged.

## 14. Open questions (decided at build time)

1. *(Settled 2026-10-14: D-440 approved, so PyObjC is a darwin-only GUI dependency.)*
2. **Developer ID:** the signing identity (design §16 question 1). Needed for notarisation and notifications, and for
   any copy that runs on another Mac without the Privacy & Security override.
3. **The sidebar spike** (native `NSOutlineView` embedded in Qt): worth a time-boxed G1 trial, or keep the Qt-drawn
   sidebar?
4. **Appearance override:** keep the in-app Light/Dark override (design §6.6), which the HIG discourages, or follow the
   system only?

## 15. Risks

- **Not a supported Qt configuration:** attaching an `NSToolbar` to Qt's `NSWindow` worked on Qt 6.12.0 / macOS 27.0.1
  (M4). Mitigation: pinned Qt, the smoke test, and the automatic fallback (§2.6).
- **Open style bugs:** Qt's macOS 26 style umbrella bug QTBUG-138942 is open, and the macOS 27 fixes ship in 6.12.1.
- **Notifications:** unproven until a Developer ID build exists (M8).
- **Graph accessibility:** the Python-implemented `QAccessibleInterface` for the graph is unproven (§7).
- **Timings:** Swift and SwiftUI timings (M5) were taken on a loaded machine and are upper bounds. The SwiftUI data
  were a Swift array, not the Python read model.
- **Fast-moving guidance:** macOS 27's HIG text still describes floating sidebars, while the system draws edge-to-edge
  sidebars (M5). The mockups follow the measured system.

## Sources

Retrieved 2026-10-14. HIG pages are at `https://developer.apple.com/design/human-interface-guidelines/<page>`.

- **[S1]** sidebars
- **[S3]** split-views
- **[S4]** panels (inspectors)
- **[S5]** sheets
- **[S7]** alerts
- **[S8]** the-menu-bar
- **[S9]** keyboards
- **[S10]** typography
- **[S11]** color
- **[S12]** dark-mode
- **[S13]** materials
- **[S14]** layout
- **[S15]** sf-symbols
- **[S16]** motion
- **[S17]** app-icons
- **[S18]** accessibility
- **[S20]** pointing-devices
- **[S21]** settings
- **[S27]** https://developer.apple.com/fonts/ (licence EA1370)
- **[S28]** https://developer.apple.com/sf-symbols/
- **[S29]** https://developer.apple.com/documentation/macos-release-notes/macos-27-release-notes
- **[S31]** https://developer.apple.com/documentation/security/app-sandbox
- **[S32]** https://developer.apple.com/documentation/foundation/process
- **[S34]** https://developer.apple.com/app-store/review/guidelines/ (2.4.5)
- **[S35]** https://developer.apple.com/documentation/security/hardened-runtime
- **[S36]** https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution
- **[S37]** https://developer.apple.com/news/?id=saqachfa
- **[S38]** https://developer.apple.com/documentation/technotes/tn3137-on-mac-keychains
- **[S43]** https://developer.apple.com/documentation/corespotlight/csimportextension
- **[S45]** https://developer.apple.com/documentation/swiftui/text
- **[S47]** https://developer.apple.com/forums/thread/798886 (Apple DTS)
- **[S48]** https://developer.apple.com/forums/thread/747880 (Apple DTS)
- **[S-DTS]** https://developer.apple.com/forums/thread/818858 (Apple DTS: no Dynamic Type on macOS)
- **[S-windows]** windows (HIG)
- **WWDC26 session 289:** https://developer.apple.com/videos/play/wwdc2026/289/
- **[Q1]** https://www.qt.io/blog/qt-on-macos-26-tahoe
- **[Q2]** https://doc.qt.io/qt-6/qmainwindow.html
- **[Q3]** https://doc.qt.io/qt-6/qt.html#WindowType-enum
- **[Q4]** https://doc.qt.io/qt-6/whatsnew612.html
- **[Q5]** https://doc.qt.io/qt-6/qaction.html
- **[Q6]** https://doc.qt.io/qt-6/macos-issues.html
- **[Q7]** https://doc.qt.io/qt-6/qmessagebox.html
- **[Q8]** https://doc.qt.io/qt-6/qstylehints.html and https://doc.qt.io/qt-6/qaccessibilityhints.html
- **[Q10]** https://doc.qt.io/qt-6/qicon.html
- **[Q11]** https://doc.qt.io/qt-6/qguiapplication.html
- **[Q12]** https://doc.qt.io/qt-6/extras-changes-qt6.html
- **[Q13]** https://doc.qt.io/qt-6/qsystemtrayicon.html
- **[Q14]** https://doc.qt.io/qt-6/qnativegestureevent.html
- **[Q15]** https://doc.qt.io/qt-6/qwheelevent.html
- **[Q16]** https://doc.qt.io/qtforpython-6/PySide6/QtGui/QAccessibleInterface.html
- **[Q17]** https://doc.qt.io/qt-6/whatsnew67.html
- **[Q18]** https://doc.qt.io/qt-6/qkeysequence.html
- **[Q19]** Qt Jira (qt-project.atlassian.net): QTBUG-138942, -150017, -141689, -61607, -85310, -94008, -110998,
  -110782, -144123, -110737
- **[W1]** https://learn.microsoft.com/en-us/windows/apps/design/controls/navigationview
- **[W2]** https://learn.microsoft.com/en-us/windows/apps/design/basics/titlebar-design
- **[W3]** https://learn.microsoft.com/en-us/windows/apps/design/app-settings/guidelines-for-app-settings
- **[W4]** https://learn.microsoft.com/en-us/windows/apps/design/input/keyboard-accelerators
- **[W5]** https://learn.microsoft.com/en-us/windows/apps/design/signature-experiences/typography
- **[W6]** https://learn.microsoft.com/en-us/windows/apps/design/accessibility/high-contrast-themes
- **[W7]** https://learn.microsoft.com/en-us/windows/apps/design/style/segoe-fluent-icons-font
- **[W8]** https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-itaskbarlist3-setprogressstate
- **[W9]** https://learn.microsoft.com/en-us/windows/win32/shell/enable-desktop-toast-with-appusermodelid
- **[W10]** https://learn.microsoft.com/en-us/typography/fonts/font-faq
- **[W11]** https://learn.microsoft.com/en-us/windows/apps/design/controls/dialogs-and-flyouts/dialogs
- **[W12]** https://fluent2.microsoft.design/layout
- **[W-motion]** https://learn.microsoft.com/en-us/windows/apps/design/signature-experiences/motion
- **[G1]** https://developer.gnome.org/hig/patterns/containers/header-bars.html
- **[G2]** https://developer.gnome.org/hig/patterns/controls/menus.html
- **[G3]** https://developer.gnome.org/hig/reference/keyboard.html
- **[G4]** https://developer.gnome.org/hig/guidelines/typography.html
- **[G6]** https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Settings.html
- **[G7]** https://developer.gnome.org/hig/patterns/feedback/notifications.html
- **[K1]** https://develop.kde.org/hig/layout_and_nav/
- **[K2]** https://invent.kde.org/frameworks/kconfig/-/blob/master/src/gui/kstandardshortcut.cpp
- **[K3]** https://invent.kde.org/plasma/plasma-desktop/-/blob/master/applets/taskmanager/smartlauncherbackend.cpp
- **[K4]** https://develop.kde.org/hig/status_changes/
- **[L1]** https://github.com/phosphor-icons/core/blob/main/LICENSE (MIT)
- **[L2]** https://github.com/lucide-icons/lucide/blob/main/LICENSE (ISC)
- **[L3]** https://github.com/microsoft/fluentui-system-icons/blob/main/LICENSE (MIT)
- **[L4]** https://github.com/Remix-Design/RemixIcon/blob/master/License
- **[L7]** https://pypi.org/project/wxPython/ and https://docs.wxwidgets.org/3.2/classwx_data_view_virtual_list_model.html
- **[L8]** https://github.com/beeware/toga/issues/2747
- **[L9]** https://docs.avaloniaui.net/docs/overview/what-is-avalonia and https://learn.microsoft.com/en-us/dotnet/maui/what-is-maui
- **[L11]** https://github.com/jaraco/keyring
- **PyObjC:** https://pypi.org/project/pyobjc/
- **PyInstaller:** https://pyinstaller.org/en/stable/feature-notes.html#macos-binary-code-signing
