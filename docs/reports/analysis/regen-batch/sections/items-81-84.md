## Items 81–84 (RD-2, core review D CD-24..CD-27; approved for the round; held branch `rd2-inspect`): the Inspect mapper

Routed to this session because it owns `adapters/inspect/mapper.py`. One commit and `tests/adapters/inspect/test_rd2.py`
(5 tests fail on the unfixed mapper, 2 guard unchanged behaviour). Spec: D.9.2 score row, D.9.13.

- **81 (CD-24):** a score event without `scorer` (inspect_ai < 0.3.217) is named by its nearest `scorer` span, cited to
  `inspect.score_event@1`. Without such a span, `score` is kept with `unk ambiguous`.
- **82 (CD-25):** non-UTC offsets are converted to UTC with the verbatim value in `t.raw` (C.8.3). Span ends, decision
  starts and state ends go through the same path, so none is dropped silently.
- **83 (CD-26):** a dangling ground-truth reference raises `dangling_source_ref` and keeps the keys in
  `ext.inspect.sample_metadata`.
- **84 (CD-27):** a non-string `tool_call_id` takes the orphan path.

**No catalogue or profile change, no bump.** Rejected: a new rule for item 81, because it would mean an `inspect` v3 bump
and profile bumps while phase 10p seals against v2 (D-460).

**Predicted.**
- The `map` code digest moves for every Inspect corpus.
- **Stored (`ast-survey-agentharm-p10`, inspect_ai 0.3.247.dev69): no AER, SEM or PROV byte moves.** Measured on its
  1,056 AERs: every judgement is named `combined_scorer.*` (the producer writes `scorer`); there are 0 `t.raw` and
  0 `/t/*` unknowns (all instants are `+00:00`); 0 `orphan_tool_result`; and no ground-truth reference dangles (its 4
  AERs with `dangling_source_ref` concern `message_id`). Items 83 and 84 change bytes only where those defects occur.
- **Not stored; bytes move at their import:**
  - whistlebench (0.3.130, 0.3.134.dev31): items 81 and 82. Core review D measured every score event without
    `scorer` and every timestamp at `-05:00`/`-07:00`. Each sample's judgements halve (one sample: 12 → 6), and all
    `t`, `t.raw`, unknowns and time edges change.
  - fragfuse-agentharm (0.3.154.dev37..0.3.159.dev20): item 81, and item 82 for any non-UTC log.
  - control-arena (phase 10p, 0.3.159) and ATIA (0.3.112): item 81.
- **Pending (a queued rehearsal re-map when the orchestrator allows):** the per-source counts of judgements and
  converted instants on the 184 staged whistlebench logs and the other staged pre-0.3.217 logs.

**Measured so far.** `tests/adapters/inspect` 207 passed; `regen_pins --check`: every family unchanged.

**Rehearsal (2026-10-15, mapper-level re-map, base main 654cef4c vs held 965041c9, same inputs).** `recompute --out`
refuses every stored corpus across versions (D-430, `corpus.derive.version_drift`), so each stored raw object was
re-mapped in process with both codes and the AERs compared byte for byte
(`~/.agentprov/migration-work/regen-items-2-12/rd-rehearsal/`).
- Byte-identical: mandate 396, survey AgentDojo 3,243, ROPE 10,791, upstream 2024-06 18,241, upstream head 36,679,
  AgentDyn 38,281 and survey AgentHarm 1,056. So RD-1 and RD-2 move no stored AER byte, items 89 and 93 included.
- Whistlebench sample (phase 10f's every-5th-log corpus, 1,850 samples, not stored): all 1,850 changed.
  - Every sample has fewer judgements (item 81's duplicates gone).
  - 1,840 gained `t.raw` and time edges; no `/t/*` unknowns are left (item 82).
  - 10 samples became `adapter_defect`. In those logs a span and a model call record an end an hour before their start
    at one local offset (AER-V19 `start_after_end`, which the old `not_recorded` reading had hidden). Fixed on the held
    branch: such a record keeps both instants verbatim, declared `ambiguous`, with no time edges (D.9.13 item 2;
    `test_rd2.py`).
- **Re-run on the fix** (held at 8f1dc0ce, 2026-10-15):
  - whistlebench: 1,850 of 1,850 samples changed, 0 `adapter_defect`. All have fewer judgements, `t.raw` and time
    edges, and fewer `/t/*` unknowns. The 10 records whose start is after their end now carry `ambiguous` instants
    instead of failing.
  - survey AgentHarm: still byte-identical (1,056).

