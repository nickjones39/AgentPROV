# Mockups (high fidelity, SVG)

The mockups belong to [`../macos-design.md`](../macos-design.md). They are SVG files of 1360 × 880. Each screen comes in
**Light** and **Dark** (`-light.svg`, `-dark.svg`). The macOS screens follow the look measured on macOS 27.0.1: the
SwiftUI reference and the Qt + native-toolbar hybrid in [`evidence/`](evidence/).

**Contents.** All identifiers, counts, hosts and paths are invented placeholders: `ex_0001`, `src-a`, `corpus-x`,
`model-a`, `api.endpoint-a.example`, `‹input dir›`, `‹AGENTPROV_HOME›`. No corpus text, model output, tool data, real
model id or real path appears. Where a value is data, it is shown as `‹text, n chars, sha256:…›`.

**Icons and fonts.**
- **Icons:** the icons are generic placeholder glyphs. Each one stands for the SF Symbol (macOS) or Phosphor (Windows
  and Linux) name listed in [`../macos-design.md`](../macos-design.md) §4.4. No Apple or third-party artwork is copied.
- **Fonts:** the files name the system font stacks (`-apple-system` / SF Pro, `Segoe UI Variable`, `Adwaita Sans`) and
  embed no font. They render with whatever the viewer has, so on a non-Apple system the macOS screens fall back to
  Helvetica or Arial.

**Authoring.** The files are plain SVG text. They were produced once by a throwaway generator in the design session's
scratchpad, which is not kept. Edit the SVG text directly.

| File | Screen | Design reference |
|---|---|---|
| `01-viewer-{light,dark}.svg` | Main window, Viewer: sidebar (Corpora / Jobs / Release), filter row, executions table, execution inspector, toolbar with the activity item | design §6.1; macos-design §3.3 |
| `02-graph-{light,dark}.svg` | Execution detail, Graph tab: tab segments in the toolbar, bundle toggles, evidence filter, PROV graph, hover popover, legend, zoom controls, element inspector | design §7; macos-design §5 |
| `03-runs-{light,dark}.svg` | Runs: job list and dashboard (stage strip, throughput, ETA, counts, failures by code), job inspector with argv | design §6.2 |
| `04-run-live-{light,dark}.svg` | New Live Run window with the estimate and consent sheet (tier R2) | design §8 |
| `05-logs-{light,dark}.svg` | Logs: level, stage and code filters, following, plain-text rows | design §6.3 |
| `06-system-{light,dark}.svg` | System: CPU per core, memory, disk, process table of a job | design §6.4 |
| `07-licences-{light,dark}.svg` | Licences: flags as text chips, the joined record in the inspector | design §6.5 |
| `08-package-{light,dark}.svg` | Package: step list, withholding review | design §6.7 |
| `09-settings-compute-{light,dark}.svg` | Settings window, Compute pane (D-432) | design §6.6 |
| `10-settings-ci-{light,dark}.svg` | Settings window, CI pane (D-431, D-432) | design §6.6 |
| `11-conformance-warning-{light,dark}.svg` | New Import Job with the PROV conformance-check warning alert | design §8.3a (D-432) |
| `12-about-{light,dark}.svg` | About window | design §6.8 |
| `13-app-icon-{light,dark}.svg` | App icon concept (layered 1024 pt) and small sizes | macos-design §4.6 |
| `20-windows-viewer-{light,dark}.svg` | The Viewer on Windows 11 (NavigationView, Settings at the bottom, CommandBar, status strip) | macos-design §3, §9 |
| `21-gnome-viewer-{light,dark}.svg` | The Viewer on GNOME (sidebar with the primary menu open, header bar) | macos-design §3, §9 |

## Evidence (measured screenshots, placeholder data)

Each file is a window captured with `screencapture -l` on macOS 27.0.1 during the study (macos-design §2.1).

| File | Measurement |
|---|---|
| `evidence/m1-qt-default-sdk15.png` | M1: Qt 6.12 defaults under the uv CPython (SDK 15.0) |
| `evidence/m6-qt-window-modal-sheet.png` | M1: window-modal `QMessageBox` as a sheet |
| `evidence/m2-qt-default-sdk27.png` | M2: the same code under an SDK-27 launcher |
| `evidence/m3-qt-tuned-sdk27-{light,dark}.png` | M3: tuned Qt Widgets |
| `evidence/m4-qt-hybrid-nstoolbar-{light,dark}.png` | M4: tuned Qt + native `NSToolbar` through PyObjC (the recommended path) |
| `evidence/m5-swiftui-reference-{light,dark}.png` | M5: SwiftUI reference (the dark capture is an inactive window) |
| `evidence/m7-dock-tile-progress.png` | M7: Dock tile with a progress bar, rendered from a Qt process |
