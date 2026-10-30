# Concurrency sweep: `Qwen3.5-4B-MLX-4bit`

Preset m5ultra v1; 24 cell(s) per arm; order [1, 2, 4, 6, 8, 12]; test_only false.

| jobs | status | wall s | traces/h | timeouts | failed | p50 ms | p90 ms | s/cell |
|---|---|---|---|---|---|---|---|---|
| 1 | ran | 79.389 | 453.463 | 0 | 0 | 855.9 | 2254.3 | 7.939 |
| 2 | skipped (after_campaign_stop) | | | | | | | |
| 4 | skipped (after_campaign_stop) | | | | | | | |
| 6 | skipped (after_campaign_stop) | | | | | | | |
| 8 | skipped (after_campaign_stop) | | | | | | | |
| 12 | skipped (after_campaign_stop) | | | | | | | |

Peak 453.463 traces/h; recommended jobs: **—** (smallest N ≥ 90% of peak, no timeouts, no failed cell).
