# 05 Logs and System

## Logs

```
┌ Logs ── job: import corpus-x ▾ ── source (•) log.jsonl ( ) stderr ───────────────────────────────────────┐
│ Level [x] info [x] warning [x] error [ ] debug   stage [any ▾]  code [any ▾]  ex [______]              │
│ Search [________________] [ ] regex   (•) Follow  ( ) Paused    buffer 50,000 lines · lagging 0 MB     │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ts            level  logger                 stage  code                     message                     │
│ 10:41:02.113  INFO   agentprov.import       map    —                        unit sealed ex_0001          │
│ 10:41:02.540  WARN   agentprov.import       map    code.example_a  field not recorded (…)       │
│ 10:41:03.007  ERROR  agentprov.adapters…    map    map.adapter_defect       adapter defect at {line:…}   │
│ …                                                                                                        │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ⓘ Paused: 1,204 older lines left the buffer; the full log is on disk. [Open log folder]                  │
│ [Copy selected (plain text)]  [Clear filters]                                                            │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## System

```
┌ System ── sampling 1 Hz while visible · [ ] keep sampling in background ────────────────────────────────┐
│ CPU per core (120 s)                                    Memory                                         │
│ c0 ▁▂▅▇█▇▆  c1 ▃▅▇██▇▆  c2 ▅▆▇████ … c11 ▂▃▅▆▇▇▆         used 21.4 / 32 GiB ▮▮▮▮▮▮▮▯▯▯  swap 0.2 GiB    │
│                                                         free under AGENTPROV_HOME: 412 GiB             │
│ Disk I/O  read 38 MB/s  write 61 MB/s  (system)         Temperature: not available on this OS          │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Processes of job "import corpus-x"   (from progress worker events)                                       │
│ pid     tier  role          CPU %   RSS       threads  open files  I/O (Linux/Windows only)              │
│ 51200   T0    agentprov     6.1     412 MiB   9        31          —                                     │
│ 51210   T1    worker 1      98.7    288 MiB   1        7           —                                     │
│ 51211   T1    worker 2      97.9    301 MiB   1        7           —                                     │
│ …                                                                                                        │
│ sampler cost: 0.4 ms/sample                                                                              │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```
