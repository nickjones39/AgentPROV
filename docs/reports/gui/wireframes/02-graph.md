# 02 Graph tab

```
┌ ex_0002 · Graph ───────────────────────────────────────────────────────────────────────────────────────┐
│ [−] [+] [100%] [Fit]  │ Bundles: [x] core  [ ] inference ▾(3)  [ ] assessment   │ Direction (•)LR ( )TB│
│ Evidence: (•) all ( ) only O ( ) only D ( ) only I  │ Collapse: [x] mentions [ ] passes │ Search [____]⏎│
├──────────────────────────────────────────────────────────────────────────────────┬─────────────────────┤
│                                                                                  │ Elements (a11y list)│
│    ╭──────────╮        wasGeneratedBy        ┌────────────┐                      │ ▸ activity  xd:m3   │
│    │ xd:e7    │ ─────────────────────────▶   │ xd:m3      │                      │ ▸ entity    xd:e7   │
│    │«apv:Mess…│                              │«apv:ModelI…│                      │ ▸ agent     xd:ag1  │
│    │rule · O  │ ◀- - - - - - - - - - - - -   │ rule · O   │                      │ …                   │
│    ╰──────────╯     used (D, dashed)         └────────────┘                      │                     │
│         ▲                                          │ wasAssociatedWith           │ Legend              │
│         ┊ hadMember (I, dotted, purple = inference)▼                             │ ⬭ entity  ▭ activity│
│    ╭──────────╮                              ⌂ xd:ag1                            │ ⌂ agent             │
│    │ xd:e8    │                              «apv:AgentSystem»                   │ ── O  - - D  ┈┈ I   │
│    ╰──────────╯                                                                  │ purple inference    │
│                                                                                  │ brown  assessment   │
│                       ┌ popover (hover 400 ms; click to pin) ────────────────┐   │ grey dashed: ghost  │
│                       │ xd:m3  activity  core  class O                       │   │                     │
│                       │ prov:type           apv:ModelInvocation              │   │ ◩ PREVIEW banner    │
│                       │ apv:rule            ns.rule_a@1                      │   │   only in §04       │
│                       │ apv:sourcePointer   aer:c3                           │   │                     │
│                       │ apv:status          apv:Kept                         │   │                     │
│                       │ apv:servedModel     ‹text, 18 chars, sha256:44…›     │   │                     │
│                       │ [Show content]  [Open in PROV-JSON]  [Open AER c3]   │   │                     │
│                       └──────────────────────────────────────────────────────┘   │                     │
├──────────────────────────────────────────────────────────────────────────────────┴─────────────────────┤
│ 212 nodes · 53 edges · layout 0.37 s (cached) · LOD: full labels · zoom 140 %                          │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Level-of-detail states** (design §7.3):

```
zoom < 15 % or > 3,000 items visible     15–50 %                 50–120 %                ≥ 120 %
┌──────────────────────────┐         ┌────────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ overview raster (one     │         │ ⬭ ▭ ⌂ shapes only  │    │ ⬭ xd:e7          │    │ ⬭ xd:e7          │
│ pixmap) + highlight      │         │ no labels, no AA,  │    │ (id only)        │    │ «types»          │
│ overlays for selection   │         │ polyline edges     │    │                  │    │ rule · O         │
│ and search hits          │         │                    │    │                  │    │ edge labels      │
└──────────────────────────┘         └────────────────────┘    └──────────────────┘    └──────────────────┘
```

**Search:** results list (id, section, bundle); Enter centres the node; `Focus` dims everything outside the k-hop
neighbourhood (k = 1 ▾).

**Large graph (> 10k nodes):** "This graph has 14,210 nodes. Showing the collapsed view (mentions and passes
folded). [Lay out everything in background] [Cancel]".
