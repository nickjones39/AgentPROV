# DTap D-358 mapping after the seal (D-1002)

Evidence for check 7's `dtap-bench-w2c` row ("OK under the D-358 re-map rule, mapping recorded"). Produced on
2026-10-30 by `d358_diag.py`: the same `recompute --dry-run --jobs 12` of the sealed tree at `1adb6b36` with the D-964
reader, with two reporting patches in the parent process and nothing else changed. Its counters equal those of the
stopped D-358 run.

| File | Contents |
|---|---|
| `d358.json` | the run's CLI summary (exit 1: 66,878 identical, 830 unverified, 8 unexplained, 2 corpus files differ) |
| `changes.jsonl` | the 8 recompute-only executions, each with its unit kind, status, issues and raw references |
| `corpus-diff.jsonl` | the 121 differing lines of `register.jsonl` (6 removed, 111 added) and `raw/origins.jsonl` (4 removed), after the recompute's own accounted-token filter |
| `sets.json` | the recompute's sets: the 83 absent objects, the 830 executions needing one, the 3 withheld executions and the 1,625 accounted labels |
| `d358_diag.py` | the wrapper that wrote them |

The mapping (check 7, DTap addendum; D-1002 (i)–(iv)): every recompute-only execution is an outcome-only unit whose
single primary object is a `judge_result.json` beside a file the re-map drops; exactly 8 kept objects of the sealed tree
sit beside a dropped file, and they are these 8; every line of `corpus-diff.jsonl` concerns a path instance of one of
them or one of the 8 units.
