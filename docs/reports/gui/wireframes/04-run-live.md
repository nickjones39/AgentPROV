# 04 Run live (first-class flow)

## Configure

```
┌ Run live ─────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1 Backend   (•) agentdojo  ( ) autodojo     env: agentdojo-…  complete ✓ [Check] [Build…]             │
│ 2 Model     (•) shorthand [openrouter ▾]  ( ) endpoint [▾] + model id [______]  ( ) scripted [file…]  │
│             key OPENROUTER_API_KEY: set in keychain ✓ (2026-10-01)        [Settings ▸ Keys]           │
│             temperature [__]  reasoning effort [▾]  LLM element (•) native ( ) gateway_compat         │
│ 3 Cells     suites [workspace, banking ▾]  user tasks [all]  injection tasks [all]                    │
│             attacks [important_instructions ▾]  benign (•) include ( ) exclude ( ) only  repeats [1]  │
│             defence [none ▾]  (others: unsupported, exit 5)   or plan [PLAN.toml…]                    │
│ 4 Concur.   jobs [6]  start stagger [6.0] s     [Tune ▸ preset m5ultra]                               │
│ 5 Safety    containment [sandbox-exec ▾] (probe ✓)  cell timeout [1800] s  max attempts [3]           │
│             canary [10]  [ ] keep staging   [ ] allow custom endpoint ⚠                               │
│ 6 Corpus    campaign [pilot-1] → id agentdojo-live-pilot-1   path ~/.agentprov/corpora/…              │
│ ── Gate ──────────────────────────────────────────────────────────────────────────────────────────────│
│ ⓘ Real-model runs of agentdojo·live are "planned" (exit 5). Start is disabled; scripted runs work.     │
│                               [Preflight only… (1 paid call)]  [Estimate & start…]                    │
└───────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Tune (preset plan from `run --dry-run --m5ultra --json`)

```
┌ Concurrency plan · preset m5ultra ─────────────────────────────┐
│ model size [  ] GB  active params [  ] B  context [   ] tokens │
│ compute cap 8 · memory cap 7 · server cap 8 → jobs 7           │
│ stagger 1.0 s/worker → 7.0 s                                   │
│ host check: matches preset facts ✓                             │
│                                     [Close] [Apply to form]    │
└────────────────────────────────────────────────────────────────┘
```

## Estimate and consent (R2)

```
┌ Confirm a paid live run ─────────────────────────────────────────────────────────────────────────────┐
│ Endpoint  openrouter.ai   model model-a   key variable OPENROUTER_API_KEY (value never shown)        │
│ Containment sandbox-exec   cells 240 (0 done) × repeats 1   jobs 7                                   │
│                                                                                                      │
│ Estimate (from 1,180 earlier executions of these suites with model-a; prices you entered 2026-10-01) │
│   model calls per cell   p50 9   p90 17                                                              │
│   cost                   ≈ $41   (p90 $77)   + preflight probe (1 call)                              │
│   time                   ≈ 3 h 10 m (p90 5 h 20 m)                                                   │
│ Model calls may be billed by the provider.                                                           │
│ [ ] I consent to API costs for up to 240 cell attempts                                               │
│                                                   [Cancel] [Start] (disabled until ticked)           │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Live dashboard

```
┌ run · agentdojo-live-pilot-1 ─────────────────────────────────────────────────────────────────────────┐
│ cells 88 / 240 ▮▮▮▮▯▯▯▯▯▯  canary 10/10 ✓   conclusive 85 · inconsistent 1 · inconclusive 2 · failed 0│
│ quarantined 0   ETA ≈ 2 h 05 m (1 h 40 m – 3 h 10 m)                                                  │
│ In flight  slot  cell                          session    since                                       │
│            1     workspace/user_task_3/…       019…a1     2 m 10 s                                    │
│            2     banking/user_task_7/…         019…b4     0 m 42 s                                    │
│ [Pause (finish current cells)] [Stop…] [Logs ▸] [System ▸] [ ] Live PROV preview (experimental)       │
└───────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Live PROV preview window (off by default)

```
┌ ◩ PREVIEW — provisional graph from the capture stream. Not corpus provenance; ───────────────────────┐
│   the engine derives the real PROV after recording.                         session 019…a1 ▾        │
├───────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  ⌂ agent ─ ─ ▭ Run ─ ─ ▭ Pass 0 ─ ─ ▭ ModelInvocation c1 ─ ─ ▭ ToolExecution o1 ─ ─ ▭ ModelInvoc. c2 │
│                                     (dashed, desaturated; ids only; tool names hidden)                │
│ events 412 · redraw ≤ 1 Hz · helper CPU 0.2 %                          [Pause preview] [Close]        │
└───────────────────────────────────────────────────────────────────────────────────────────────────────┘
```
