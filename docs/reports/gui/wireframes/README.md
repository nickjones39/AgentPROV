# Wireframes (low fidelity, text)

Monospace sketches of each screen for [`../design.md`](../design.md) §6. They show layout, controls and states, not
visual style.

**Contents.** All identifiers, counts and values are invented placeholders: `ex_0001…`, `src-a`, `corpus-x`. No corpus
text, model output, tool data or real execution id appears. Where content would be shown, the sketches put a
`‹text, n chars, sha256:…›` placeholder or an `<<UNTRUSTED …>>` fence with placeholder dots.

| File | Screens |
|---|---|
| [01-viewer.md](01-viewer.md) | main window frame and navigation rail; Viewer: corpora, executions table, execution detail tabs (PROV-JSON, AER, Raw) |
| [02-graph.md](02-graph.md) | Graph tab: toolbar, bundle and evidence controls, popover, search, LOD states, Elements list |
| [03-runs.md](03-runs.md) | Runs: job list, job dashboard, new-job form (import with registry picker), regeneration matrix, confirmation dialogs by tier |
| [04-run-live.md](04-run-live.md) | Run live: configuration, Tune (preset plan), estimate and consent, live dashboard, preview window |
| [05-logs-system.md](05-logs-system.md) | Logs pane; System tab |
| [06-licences-package.md](06-licences-package.md) | Licences view; Package flow (steps 1–9) |
| [07-settings-about.md](07-settings-about.md) | Settings (keys, appearance, paths); About box |

Conventions:
- `[Button]` is a button and `( ) / (•)` a radio button.
- `[x] / [ ]` is a check box and `▾` a drop-down.
- `▮▮▮▯▯` is a progress bar.
- `R0`–`R2` are risk-tier badges (design §8.4).
- `⟲` is refresh and `⋯` overflow.
