# The AgentPROV website: design note (2026-10-29, D-1000)

The landing page (`site/`) introduces AgentPROV to researchers who arrive from the paper, a citation or a search, and
gives people who only want the desktop app a direct download. It sits at the root of the project website; the user
guide is under `/docs/`. This note records the principles behind it, the decisions they led to, and how to keep the
page true as the project changes.

## Sources

- Apple's Human Interface Guidelines, *Design principles* (reintroduced 2026-06-08): purpose, agency, responsibility,
  familiarity, flexibility, simplicity, craft and delight. <https://developer.apple.com/design/human-interface-guidelines/design-principles>
- The HIG's *Motion* guidance: motion should explain, stay brief, give way to Reduce Motion, and never decorate for its
  own sake. <https://developer.apple.com/design/human-interface-guidelines/motion>
- Third-party analyses of apple.com product pages (scroll-triggered reveals, pinned stages, one feature per chapter,
  colour changes between sections in place of dividers, headlines that make small claims a reader can check). We read
  them for structure only. The page uses no Apple asset, wording, typeface or trademark, and it does not imitate an
  Apple page.

## The principles we applied

| Principle | What it became on this page |
|---|---|
| **Purpose**: decide what matters most | One job per chapter, in the order a researcher asks: what is it, how does it work, what does the app look like, what can it read, where is the data, how do I get it, how do I cite it. |
| **Simplicity**: every element earns its place | One accent colour (the logo's indigo). The three PROV hues of the logo appear only where they mean something: the node shapes and the evidence classes. No stock imagery and no icons for decoration. |
| **Familiarity**: use what people know | The app's own visual language: entities as ovals, activities as boxes, agents as house shapes, and observed, derived and inferred drawn as solid, dashed and dotted lines. The hero headline uses the same three line styles as underlines. |
| **Responsibility**: be transparent and protect people | The copy is bound to the project's claims lint, so it says no more than the paper may. The page sets no cookie, runs no analytics and loads nothing from another host; a CSP meta tag enforces that. First-launch notes for the unsigned bundles are next to the buttons, not hidden. |
| **Agency**: let people explore and recover | The app tour is driven by the visitor (tabs, arrows, numbered points), never autoplays, and every zoom has a "Show the whole window" control and Escape. The theme follows the system unless the visitor picks one. |
| **Flexibility**: design for everyone | Keyboard operable throughout (a roving tab list, real buttons, a visible focus ring, a skip link); text alternatives for every screenshot; WCAG AA contrast in both themes; one column at phone width; everything readable without JavaScript. |
| **Craft**: care about detail | Light and dark screenshots of the app swap with the theme. Hotspots sit on the controls they name. Commands are shown as the CLI equivalent of each app page, because every action in the app has one. |
| **Delight, not decoration** | One orchestrated moment: the logo assembles as a PROV graph on load (the agent, the entity and the activity, then the three relations), labelled with the node types. Everything else moves only to explain: packets travel along the pipeline, and tour screenshots zoom to the point being described. |

Motion follows the HIG: short (under a second), on transform and opacity only (compositor-friendly), and with
`prefers-reduced-motion: reduce` the page is static. Scroll-linked settling uses the CSS scroll timeline, so browsers
without it simply show the page at rest. Nothing waits at zero opacity for a script.

## Decisions

- **Typography.** The platforms' own faces (`ui-sans-serif`, `-apple-system`, Segoe UI Variable, Noto Sans, …) and
  their monospace faces. No font file means no licence, no download and no layout shift; the guide makes the same
  choice (`theme.font: false`). The brand guide forbids setting "AgentPROV" in a font, so the wordmark is the
  brand's own stroke drawing, inlined so its colours follow the theme.
- **Colour.** Cool neutrals with a slight indigo bias; the brand indigo (`#3A4DB8`, `#A9B8FF` in dark) as the only
  accent. The app tour sits on a deep indigo band, the colour of the app icon's tile, in both themes: the one bold
  move on the page.
- **Screenshots.** Taken on 2026-10-29 by `gui/tools/screenshots.py` (with the colour scheme forced to light and to dark
  by a wrapper outside the repository) on the synthetic AgentDojo test corpora, with its leak guard on. Run Live and
  the model dialogs use stub answers; the page says so. Saved as WebP (quality 86), about 650 KiB per theme.
- **Downloads.** GitHub's stable `releases/latest/download/<asset>` URLs, so the page needs no edit per release while
  the asset names stay the same. The visitor's platform is guessed in the browser (User-Agent Client Hints where
  available) only to highlight a card and label the main button; every file stays listed. Nothing is sent anywhere.
- **No generator.** One page does not need a build step; the workflow copies `site/` beside the MkDocs output.

## Keeping it true

- `tests/repo/test_site.py` runs the claims lint over the visible text, checks the coverage phrase against the
  registry, the live-capture wording, self-hosting, alt text, the brand files, the download URLs and asset names, and
  the release-day placeholders. When a fact changes (a version, an asset name, the coverage phrase), the test fails
  until the page is updated.
- **Release day:** fill the elements marked `data-placeholder` (collection and software DOIs, the paper and Zenodo
  links) and update `PLACEHOLDERS` in the test. Go-live is `docs/user-guide/_go-live.md`, which now covers the whole
  website, and its last step is the prepared w3id pull request (`docs/reports/site/w3id/PR.md`).
- **New screenshots:** run the screenshot script for the scenes the tour uses (`agentprov-app`, `viewer-graph`,
  `viewer-outcomes`, `viewer-aer`, `new-job`, `runs-jobs`, `run-live`, `package`) in both schemes, convert with
  `cwebp -q 86 -m 6 -metadata none`, and check that each hotspot still sits on its control.
