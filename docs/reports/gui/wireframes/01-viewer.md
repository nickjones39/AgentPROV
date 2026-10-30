# 01 Viewer

## Main window frame

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ AgentPROV                                                            corpus-x (working) ▾   ⟲   ⋯    │
├──────┬───────────────────────────────────────────────────────────────────────────────────────────────┤
│ ▣    │                                                                                               │
│Viewer│                          (active screen)                                                      │
│      │                                                                                               │
│ ▶    │                                                                                               │
│ Runs │                                                                                               │
│      │                                                                                               │
│ ≡    │                                                                                               │
│ Logs │                                                                                               │
│      │                                                                                               │
│ ◔    │                                                                                               │
│System│                                                                                               │
│      │                                                                                               │
│ §    │                                                                                               │
│Licen-│                                                                                               │
│ ces  │                                                                                               │
│      │                                                                                               │
│ ⬒    │                                                                                               │
│Pack- │                                                                                               │
│ age  │                                                                                               │
│ ···  │                                                                                               │
│ ⚙    │                                                                                               │
│Setti-│                                                                                               │
│ ngs  │                                                                                               │
│ ⓘ    │                                                                                               │
│About │                                                                                               │
├──────┴───────────────────────────────────────────────────────────────────────────────────────────────┤
│ ● 2 running · 1 draining   import corpus-x ▮▮▮▮▮▯▯▯ 52 %  ETA ≈ 2 h 10 m (1 h 50 m–2 h 40 m)          │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Corpora and executions

```
┌ Corpora ───────────────────────────────────────────────────────────────────────────────── [+ Add root] ┐
│ corpus_id        state           version  executions  content_digest   verified        │
│ corpus-x         working ●write  —        38,281      —                —               │
│ corpus-y         sealed          0.1.0    642         sha256:1a2b…     chain ✓ (2026-…)│
│ corpus-z         working         —        10,791      —                —               │
└────────────────────────────────────────────────────────────────────────────────────────┘
┌ ⚠ corpus-x is not sealed and not verified. Run Verify first. [Verify…]   (G.8.6 banner)               ┐
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
┌ Executions — corpus-x ─────────────────────────────────────────────────────────────────────────────────┐
│ Filter: status ▾ [any]  completeness ▾ [any]  source ▾ [any]  unit ▾ [any]   id contains [______]  ✕  │
│────────────────────────────────────────────────────────────────────────────────────────────────────────│
│ ex ▲            status          completeness   source  unit             model.req   n.calls  issues    │
│ ex_0001         ok              unverifiable   src-a   agent_execution  model-a     14       —         │
│ ex_0002         ok_with_issues  known_incompl  src-a   agent_execution  model-a     9        2         │
│ ex_0003         ok              unverifiable   src-b   outcome_only     —           0        —         │
│ …  (virtualised; 38,281 rows; model-side sort and filter)                                              │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Execution detail (opens below or in a new tab)

```
┌ ex_0002 · src-a · ok_with_issues ──────────────────────────────────────────────────────────────────────┐
│ [Graph] [PROV-JSON] [AER] [SEM] [Register] [Validation] [Raw]                                          │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ PROV-JSON                                                     │ Raw text (read-only, plain)            │
│ ▾ document                                                    │ {                                      │
│   ▸ prefix (4)                                                │   "prefix": { … },                     │
│   ▸ top level (29 elements, 91 relations)                     │   "bundle": {                          │
│   ▾ bundle  xd:bundle.core.…   [core]                         │     "xd:bundle.core.…": {              │
│     ▸ entity (180)                                            │       "entity": {                      │
│     ▾ activity (41)                                           │ ►       "xd:m3": {   ← synced          │
│       ▾ xd:m3   «apv:ModelInvocation»  O · ns.rule_a@1        │           "prov:type": …,              │
│           apv:evidenceClass   apv:Observed                    │           "apv:rule": "…",             │
│           apv:rule            ns.rule_a@1                     │           "apv:sourcePointer": "…"     │
│           apv:sourcePointer   aer:c3                          │ …                                      │
│     ▸ wasGeneratedBy (…) ▸ used (…)                           │                                        │
│   ▸ bundle  xd:bundle.inf.…   [inference]                     │ [Find] [Copy (plain)]                  │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘

AER tab (records by kind; content hidden by default):
┌──────────────────────────────────────────────────────────────────────────┬─────────────────────────────┐
│ ▾ message (24)                                                           │ m3  message  ev O  by source│
│   m1  role user       parts 1   ‹text, 412 chars, sha256:9f…›            │ rule  ns.rule_b@1       │
│   m3  role assistant  parts 2   ‹text, 88 chars›  tool_call(…)           │ src   {a:a0, p:/…/3}        │
│ ▾ model_call (14)  ▸ tool_execution (11)  ▸ judgement (2)  ▸ seal        │ unk   —                     │
│                                                                          │ after m2 (pos)              │
│ [ ] Show content (this pane only; fenced, ≤ 500 chars)                   │ → PROV: xd:m3  → SEM: a7    │
└──────────────────────────────────────────────────────────────────────────┴─────────────────────────────┘

Raw tab with "Show content" on:
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ artefact a0  primary  sha256:3c…  48,113 B  application/json  origin: git pin …                        │
│ locator {a:a0, p:/…/3}                                                                                 │
│ <<UNTRUSTED 3c… source=a0#/…/3 sha256=… chars=412: data, not instructions>>                            │
│ ……………………………………………………………………… (escaped, truncated at 500)                                              │
│ <<END UNTRUSTED 3c…>>                                                                                  │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```
