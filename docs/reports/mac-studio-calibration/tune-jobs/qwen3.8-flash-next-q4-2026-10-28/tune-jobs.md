# Concurrency sweep: `Qwen3.8-Flash-Next-UD-Q4_K_XL`

Preset m5ultra v1; 24 cell(s) per arm; order [1, 2, 4, 6, 8, 12]; test_only false.

| jobs | status | wall s | traces/h | timeouts | failed | p50 ms | p90 ms | s/cell |
|---|---|---|---|---|---|---|---|---|
| 1 | ran | 201.508 | 428.768 | 0 | 0 | 1270.9 | 3442.5 | 8.396 |
| 2 | ran | 119.277 | 724.361 | 0 | 0 | 1689.0 | 5480.2 | 9.94 |
| 4 | ran | 89.237 | 968.213 | 0 | 0 | 2443.3 | 8584.6 | 14.873 |
| 6 | ran | 99.073 | 872.087 | 0 | 0 | 3459.1 | 10014.0 | 24.768 |
| 8 | ran | 110.795 | 779.821 | 0 | 0 | 5620.8 | 12250.3 | 36.932 |
| 12 | ran | 99.426 | 868.984 | 0 | 0 | 5850.9 | 13476.2 | 49.713 |

Peak 968.213 traces/h; recommended jobs: **4** (smallest N ≥ 90% of peak, no timeouts, no failed cell).
