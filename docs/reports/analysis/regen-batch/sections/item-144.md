## Item 144 (D-601; bug pass bugpass-perf-10, pre-check PC-01/PC-02; user decision 2026-10-21: approved; held branch `bugpass-regen-d601`): WhistleBench redaction and withholding

- **Change:** `adapters/inspect/redact.py` adds the harness pointers `/code/repo` (actor) and
  `/ext/inspect/error_retries` (scope) and an optional `pointers` narrowing per rule (`family.schema.json`). Profile
  `whistlebench@2` adds `origin_userinfo` (literal `redacted`, on the two revision copies), `retry_account`
  (`<account:{span12}>`, on `error_retries` only), quirk `inspect.error_retries`, and `[withhold]` (secret,
  `github-token-shape`, scope `object`, `scan_rules = ["github-pat"]`). Version 1 is archived with main's bytes
  (`2275688dea24…`, recorded by the pre-check scratch partials; D-31).
- **Census** (pinned bare clone @ `9c27637c`, counts only): withhold pattern in 28 of 184 `header.json` members, 28
  `_journal/start.json`, **0 of 9,200 sample members**. 2 context `logs.json` blobs, which are not stored. 0 `.eval`
  containers as stored. URL userinfo: 1 distinct span in each of the 28 logs. Account #1: 260 samples, 722
  `error_retries` strings, nowhere else.
- **Expected at a release seal:** 28 `header.json` withheld (basis `profile_rule`) + 28 `.eval` (basis `container`),
  0 executions. Shown end to end on synthetic logs (`tests/adapters/inspect/test_whistlebench_withhold_e2e.py`).

| Output | Moves | Count (population) |
|---|---|---|
| AER, bench actor (`code.repo`, `ext.inspect.revision.origin`, `evf`, `rule`, `ext.inspect.redacted`) | yes | 1,400 executions (28 logs), 2,800 strings |
| AER, run scope (`ext.inspect.error_retries/*/traceback(_ansi)`, `evf`, `rule`, `ext.inspect.redacted`) | yes | 260 executions |
| AER header profile ref (`whistlebench@2`, digest) | yes | 9,200 executions |
| PROV, validation, index rows | follow the AER | 9,200 |
| SEM | none (no semantics profile) | 0 |
| `inspect` adapter code digest | yes (`redact.py`) | every Inspect corpus imported afterwards (code drift, D-430) |
| Other profiles' AER, golden pins | no (no other profile declares redaction rules) | 0 |

- **Scratch re-map (measured, every pinned log at version 2, in process, nothing kept):** 9,200 executions, 0 register,
  0 degenerate, 0 failures; `origin_userinfo` 2,800 strings / 1,400 executions, `retry_account` 722 strings / 260
  executions; residue 0 (token shape) and 0 (account #1) in the AER bytes. Golden pins unchanged: `tests/adapters/inspect`,
  `tests/golden/test_prov_derive.py` and `tests/golden/test_gate_d.py` pass on the branch.
- **Settled (user decisions 2026-10-21):** the semantics profile is item 146. The raw sample members holding account #1
  ship as pinned (D-186 (c)), disclosed by the datasheet statement `whistlebench-retry-traceback-account`.

