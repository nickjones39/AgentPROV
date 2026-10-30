# 03 Runs

## Job list and dashboard

```
┌ Runs ───────────────────────────────────────────────── [▶ Run live…] [+ New job ▾] [+ Batch] ────────┐
│ state      command     corpus     tier  started   elapsed   progress          outcome                 │
│ ● running  import      corpus-x   R1    09:12     1 h 30 m  ▮▮▮▮▮▯▯▯▯ 52 %    —                       │
│ ◐ draining run (live)  corpus-l   R2    08:40     2 h 02 m  cells 88/240      —                       │
│ ○ queued   derive      corpus-x   R1    —         —         batch step 2/5    —                       │
│ ✓ ended    verify      corpus-y   R0    yest.     4 m       —                 ok (exit 0)             │
│ ✕ ended    package     corpus-z   R1    yest.     12 s      —                 refused (exit 4)        │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
┌ import · corpus-x · release ───────────────────────────────────────────────────────────────────────────┐
│ argv: agentprov import src-a --corpus ~/.agentprov/corpora/corpus-x --input … --verify-against-pin     │
│       --release --jobs 12 --progress-file … --log-file … --summary-json …           [Copy command]     │
│ started 09:12 · elapsed 1 h 30 m · run 019… · segment 0 · events dropped 0                             │
│                                                                                                        │
│ Stages         done / total        failed   running                                                    │
│ map            20,117 / 38,281 ▮▮▮▮▮▯▯▯▯     3       11                                                │
│ seal           20,109              ▮▮▮▮▮▯▯▯▯     0                                                     │
│ sem            20,100              ▮▮▮▮▮▯▯▯▯     0                                                     │
│ prov           20,090              ▮▮▮▮▮▯▯▯▯     0                                                     │
│ validate       20,088              ▮▮▮▮▮▯▯▯▯     0                                                     │
│                                                                                                        │
│ Throughput 3.71 /s (EWMA) · mean 3.72 /s · ETA ≈ 1 h 22 m (1 h 15 m – 1 h 31 m)                        │
│ Counts: sealed 19,702 · with issues 385 · degenerate 4 · failed 3 · withheld 0 · dup 12 · resumed 0    │
│ Workers 11/12 busy        [System ▸]                                                                   │
│ Failures by code                      n                                                                │
│   map.adapter_defect                  3   [Logs ▸]                                                     │
│   code.example_a          381   [Logs ▸]                                                     │
│                                                                                                        │
│ [Pause (finish current units)] [Stop…] [Open log] [Open in Viewer]                                     │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## New job: Import (registry picker)

```
┌ New import ───────────────────────────────────────────────────────────────────────────────────────────┐
│ Sources (from the registry)                                                    filter [______]        │
│ [ ] source   part       family     licence (SPDX · policy)       import status  profile               │
│ [x] src-a    logs       agentdojo  MIT · include                 supported      src-a-logs@3          │
│ [ ] src-b    upstream   agentdojo  Apache-2.0 · include          partial        src-b@2               │
│ [-] src-c    runs       inspect    CC-BY-4.0 · include  ⚑restr   planned  (cannot select)             │
│                                                                                                       │
│ Origin  (•) local input [~/…/staging/src-a ▾] [x] verify against pin                                  │
│         ( ) fetch pinned origin  [ ] allow network (R2)  [ ] consent to downloads ≥ 100 MiB (R2)      │
│ Corpus  [~/.agentprov/corpora/src-a-p11      ]  id [auto]   Mode (•) release ( ) dev/scratch          │
│ Until   [validation ▾]   Jobs [0 = host default]   [ ] retry failed   [ ] dry run                     │
│ Filters (disabled in release mode): select [____] suite [__] attack [__] limit [__]                   │
│ ── Will run ──────────────────────────────────────────────────────────────────────────────────────────│
│ agentprov import src-a --corpus … --input … --verify-against-pin --release --jobs 0 …                 │
│ Tier R1: writes ~/.agentprov/corpora/src-a-p11.partial                    [Cancel] [Start]            │
└───────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Regeneration round (batch matrix)

```
┌ Batch "regen-round-1" · concurrency 1 · continue on failure [ ] ──────────────────────────────────────┐
│ corpus        import        derive        validate      verify chain   package      │
│ corpus-x      ✓ 38,281      ● 20,090/…    ○             ○              ○            │
│ corpus-y      ✓ 642         ✓ 642         ✓ 642         ✓              —            │
│ corpus-z      ✕ exit 4      ○             ○             ○              ○            │
│ (advances only while the GUI is open)                 [Pause batch] [Edit] [Remove] │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## Confirmations by tier

```
R1                                                  R2 (network)
┌ Write local data ─────────────────────────┐       ┌ Network access ────────────────────────────────┐
│ This job writes:                          │       │ This job contacts:                             │
│   ~/.agentprov/corpora/src-a-p11.partial  │       │   github.com (git pin …)                       │
│ It never writes inside a sealed corpus    │       │   zenodo.org (download, 1.9 GiB)               │
│ or the repository.                        │       │ [ ] I allow network access for this job        │
│              [Cancel] [Start]             │       │ [ ] I consent to downloads ≥ 100 MiB           │
└───────────────────────────────────────────┘       │              [Cancel] [Start] (disabled until ✓)│
                                                    └────────────────────────────────────────────────┘
Destructive (purge)                                 Force kill (only after Stop timed out)
┌ Purge object ─────────────────────────────┐       ┌ Force kill ─────────────────────────────────────┐
│ Irreversibly deletes sha256:1a2b3c4d…     │       │ The job did not stop within 120 s.              │
│ and writes a tombstone (reason: secret).  │       │ Force kill leaves a stale lock, may lose the    │
│ Type the first 8 hex digits to confirm:   │       │ unflushed index (import) and orphan staging.    │
│ [________]               [Cancel] [Purge] │       │ [Wait longer] [Force kill]                      │
└───────────────────────────────────────────┘       └─────────────────────────────────────────────────┘
```
