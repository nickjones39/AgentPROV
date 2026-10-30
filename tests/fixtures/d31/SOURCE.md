# D-31 fixture (regeneration-batch item 30)

`r01.aer.jsonl` and `r01.sem.jsonl` are the stored AER and `agentdojo.suites@1` SEM of execution
`ex_ayrs42tkhjtgxuwnlgmrhpapg3`, copied unchanged from the stored corpus `adprov-v1-release-p10` (2026-10-13). This is
golden v1 pair R01 (its released transcript is already a repository golden, `tests/golden/test_v1_round_trip.py`), so
no new source data enters the repository. Both files were written with the catalogue `agentdojo` at version 1 and the
profile `adprov-v1` at version 1, the versions now archived. `tests/unit/test_d31_bumps.py` rebuilds the SEM byte for
byte from the AER.
