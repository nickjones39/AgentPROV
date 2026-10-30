# Concurrency sweep: `Qwen3.8-Flash-Next-UD-Q4_K_XL`

Preset m5ultra v1; 24 cell(s) per arm; order [4, 6]; test_only false.

| jobs | status | wall s | traces/h | timeouts | failed | p50 ms | p90 ms | s/cell |
|---|---|---|---|---|---|---|---|---|
| 4 | ran | 85.642 | 1008.854 | 0 | 0 | 1908.5 | 6997.3 | 14.274 |
| 6 | ran | 103.606 | 833.928 | 0 | 0 | 4015.8 | 10360.6 | 25.902 |

Peak 1008.854 traces/h; recommended jobs: **4** (smallest N ≥ 90% of peak, no timeouts, no failed cell).
