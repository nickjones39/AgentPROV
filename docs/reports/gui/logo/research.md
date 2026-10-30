# AgentPROV logo: design research (2026-10-28)

What the logo and app icon have to satisfy, and where each rule comes from. Apple's Human Interface Guidelines are the
style exemplar; the meaning comes from W3C PROV and from what AgentPROV does. Web pages were read as data. Nothing was
copied from them: no artwork, template, symbol or font.

## 1. Apple's app-icon guidance as it stands now

Source: [HIG, App icons](https://developer.apple.com/design/human-interface-guidelines/app-icons). The change log's latest
entry is 8 June 2026, "Refined guidance for Liquid Glass". The previous one (9 June 2025) introduced layered icons.

- **One canvas, square layers.** iOS, iPadOS and macOS share a 1024 × 1024 px layout. The system applies the
  rounded-rectangle mask, so layers handed to Icon Composer are square and unmasked. Pre-masked layers "negatively
  impact specular highlight effects and make edges look jagged".
- **Layers and Liquid Glass.** A background layer plus one or more foreground layers. The system adds the specular
  highlights, refraction, translucency and shadows, and they change with size and OS version. Apple advises against
  baking in drop shadows, bevels, glows or blurs.
- **Simplicity.** One idea, "a minimal number of shapes", and a plain solid or gradient background. Apple suggests
  overlapping filled shapes, with transparency, to give depth. The canvas doesn't need to be full.
- **No text** unless it is essential. Avoid very thin lines and sharp corners: they break up at small sizes.
- **Edges.** Prefer clearly defined edges; feathered edges spoil the system highlights.
- **Appearances.** Default, dark, clear (light and dark) and tinted (light and dark). The system generates any you
  don't provide. Keep the same features in every appearance; make the dark variant from the light one, and keep it
  subdued.
- **Formats.** Vector layers (SVG or PDF), with text converted to outlines. Colour spaces: sRGB, Gray Gamma 2.2,
  Display P3.
- **Prohibitions.** No replicas of Apple hardware. The [SF Symbols guidance](https://developer.apple.com/design/human-interface-guidelines/sf-symbols)
  prohibits SF Symbols, "or images that are confusingly similar", in app icons and logos. San Francisco (SF Pro) is
  licensed for Apple-platform interfaces, not for a logo. So the wordmark can't use it.

Apple's sessions add workflow detail:

- [WWDC25 "Create icons with Icon Composer"](https://developer.apple.com/videos/play/wwdc2025/361/): export SVG layers
  at full canvas size, numbered in z-order. Split colours into separate layers, so a dark variant is a fill change.
  Keep the art "flat, opaque, and easy to control later". Icon Composer's annotations are Default, Dark and Mono; Clear
  and Tinted are derived from them. For mono, make at least one prominent element white and map the rest to greys.
- [WWDC26 "Icon Composer for Beginners Group Lab"](https://developer.apple.com/videos/play/wwdc2026/8012/): bold, simple
  geometry; check the smallest sizes first. Glass effects are sensitive to the number of shapes, their size and their
  overlap. Make a strong mono annotation, and don't let colour alone carry meaning.

## 2. What this means for a Qt app shipped as an `.icns`

AgentPROV is a PySide6 app bundled by PyInstaller. It isn't an Xcode target. This machine has the Command Line Tools,
not Xcode, so `actool` and Icon Composer aren't available (`xcrun --find actool` fails). The macOS icon is therefore
a classic `.icns` built with `iconutil`, and that shapes the design:

- **Since macOS 26, "squircle jail" applies to bundled icons.** macOS 26 Tahoe shrinks a bundled icon that doesn't
  fit the rounded-rectangle shape and puts it on a grey tile
  ([Rogue Amoeba, "Free the icons", 2026-06-26](https://weblog.rogueamoeba.com/2026/06/26/free-the-icons/);
  [heise, "Icons in macOS 26"](https://heise.de/-11075561): it "detects when pixels protrude";
  [Michael Tsai's round-up](https://mjtsai.com/blog/2025/11/11/tahoes-terrible-icons/);
  [Daring Fireball](https://daringfireball.net/2025/08/macos_26_tahoes_dead_canary_utility_app_icons)).
  [MacStories' macOS 27 review](https://www.macstories.net/stories/macos-27-the-macstories-review/2/) reports that the
  rule still applies in macOS 27, and this machine runs macOS 27.2.
  **Consequence:** the `.icns` art must be a full, opaque rounded-rectangle tile at the standard inset, with nothing
  outside it: no outer drop shadow, no protruding element. Section 6 records an empirical check of the built bundle on
  this machine.
- **The tile and its depth are drawn into the art.** We can't hand Icon Composer square layers, so the tile is part of
  the SVG. We keep Apple's layer logic anyway: a gradient background and a few flat, overlapping foreground shapes with
  clean edges. Depth comes only from a gentle top-to-bottom light on the tile and a soft contact shadow under the
  foreground group, with no bevels or glows. The foreground shapes are separate groups, so they can later be exported
  as Icon Composer layers if the project moves to Xcode.
- **The tile shape is our own.** It's a superellipse (|x|ⁿ + |y|ⁿ = 1, n = 5), computed from the formula. It isn't
  traced from Apple's template, and it gives the continuous-curvature corner that macOS icons share. The tile is
  824 × 824 inside the 1024 canvas (a 100 px margin): the classic macOS icon inset.

## 3. Small sizes, mono and other platforms

- **Sizes that must stay readable:** 16 and 32 px (Finder list, menu bar and title bar, Windows context menus and title
  bar, browser favicons). 16 px gives about three distinguishable features, so the mark needs a dominant silhouette and
  thick strokes. The icon is designed to work at 32 px first, and at 16 px it is checked as a silhouette.
- **Windows** ([Microsoft Learn, "Construct your Windows app's icon"](https://learn.microsoft.com/en-us/windows/apps/design/style/iconography/app-icon-construction),
  updated 2026-08): an ICO needs at least 16, 24, 32, 48 and 256 px. Windows scales down, never up. Transparent
  backgrounds look best. A plated icon has to stand up on light and dark themes. We ship 16, 20, 24, 32, 40, 48, 64 and
  256 px, using the tile, which carries its own contrast.
- **Linux** ([freedesktop Icon Theme Specification](https://specifications.freedesktop.org/icon-theme-spec/latest/)):
  `hicolor/<size>x<size>/apps/<name>.png` at 16 to 512 px, plus `scalable/apps/<name>.svg`.
- **Mono and template:** a single-colour mark on a transparent background, for monochrome and template uses (a tinted
  appearance, a future menu-bar item, print). Its shapes must read from the silhouette alone, with overlaps shown as
  gaps.

## 4. The web

- [Material for MkDocs, "Changing the logo and icons"](https://squidfunk.github.io/mkdocs-material/setup/changing-the-logo-and-icons/):
  `theme.logo` takes an image file of any type, SVG included, inside `docs_dir`. `theme.favicon` takes an image path
  inside `docs_dir`. The page shows a PNG. SVG favicons work in current browsers but not in Safari before 2023, so a
  32 px PNG is the safe choice.
- [GitHub, "Specifying the theme an image is shown to"](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax#specifying-the-theme-an-image-is-shown-to):
  in a README, `<picture>` with `<source media="(prefers-color-scheme: dark)">` chooses the variant, so a wordmark can
  have dark text on GitHub's light theme and light text on its dark theme.

## 5. What the mark should say

From `README.md` and the specification:

- AgentPROV records how an agent's execution happened. It turns that record into **W3C PROV** graphs, keeps a
  **hash-chained** corpus from raw bytes to graph, and only states a relation when there is **evidence** for it.
- PROV's diagram convention ([PROV-O](https://www.w3.org/TR/prov-o/),
  [PROV-DM](https://www.w3.org/TR/prov-dm/), [the PROV WG diagram conventions](https://www.w3.org/2011/prov/wiki/Diagrams))
  draws **entities as yellow ellipses, activities as blue rectangles and agents as orange pentagons ("houses")**. The
  GUI and `render.style` use the same fills: entity `#FFFC87`, activity `#9FB1FC`, agent `#FED37F`
  (`src/agentprov/render/style.py`, `gui/src/agentprov_gui/ui/theme.py`). Researchers who use PROV recognise these three
  shapes, and no other tool's logo is built from them, so they are the natural vocabulary for the mark.
- The GUI follows macOS Light/Dark and the system accent. Its status colours are Apple-like system hues (`#248A3D`,
  `#0068D6` and so on). The icon should sit comfortably next to that chrome.

**Palette direction:** keep the three PROV hues, shifted slightly towards saturated, modern values so they hold up on a
coloured tile and in small sizes. Put them on a deep indigo tile, so the soft fills keep their contrast and the icon
doesn't disappear on a white Dock or Finder. A flat, saturated revision was tried after the "impactful colours"
direction; the owner kept these softer gradient colours (`concepts.md`, "Colour decision"). The values are in
`brand.md`.

## 6. Empirical checks on this machine

- **No grey plate on macOS 27.2:** a throwaway bundle with the final `AgentPROV.icns`, drawn through
  `NSWorkspace.icon(forFile:)`, comes back full size, with the system's own glass edge added. A control bundle whose
  `.icns` is the bare mark (no tile) comes back shrunk onto the grey plate, so the check can tell the two cases apart
  ([previews/macos-27-icon-check.png](previews/macos-27-icon-check.png)).
- **Sizes:** the 16, 32, 64, 256 and 1024 px renders on light and dark backgrounds were inspected
  ([previews/final-sheet.png](previews/final-sheet.png)). The A is still legible at 16 px, and every element reads from
  32 px.
- **Reproducibility:** two `make_icons.py` runs with rsvg-convert 2.63.4 and `iconutil` give byte-identical outputs.
