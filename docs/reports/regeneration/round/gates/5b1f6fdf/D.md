# Gate D (full, release mode): fail

- commit `5b1f6fdf309cb7c365aeaeb3dd459d85fbabecf7`, started 2026-10-22T08:20:26Z, 2157.3 s, 8 workers
- executions 35905/35905 checked, 35905 passed, 0 failed
- profile `agentdojo.suites@1`; every D8 tier in release mode, a skipped check is a failure (MP-3)

## native: 18241/18241 passed

wall per execution: mean 0.3864 s, p95 0.8377 s, max 5.7431 s; statements: mean 263.2, max 4129

| invariant | observed | J.3.5 | result |
|---|---|---|---|
| tool_execution_activities | 68620 | 68620 | ok |
| tool_call_request_entities | 68773 | 68773 | ok |
| requests_without_execution | 153 | 153 | ok |
| model_invocations_generating_assistant_message | 73551 | 73551 | ok |
| user_message_entities | 21658 | 21658 | ok |
| system_message_entities | 18027 | 18027 | ok |
| executions_without_tool_execution | 762 | 762 | ok |
| wasGeneratedBy_tool_result_tool_execution | 68620 | 68620 | ok |
| activity_records | 16003 | 0 | FAIL |
| artefact_records | 0 | 0 | ok |
| generic_rule_statements | 0 | 0 | ok |

reported separately (mixtral): 7 executions

reported separately (outcome_only): 207 executions

## release: 17664/17664 passed

wall per execution: mean 0.5756 s, p95 1.2541 s, max 17.8738 s; statements: mean 287.6, max 8373

| invariant | observed | J.3.5 | result |
|---|---|---|---|
| tool_execution_activities | 64781 | 64781 | ok |
| tool_call_request_entities | 64829 | 64829 | ok |
| requests_without_execution | 48 | 48 | ok |
| model_invocations_generating_assistant_message | 64897 | 64897 | ok |
| user_message_entities | 17664 | 17664 | ok |
| system_message_entities | 17664 | 17664 | ok |
| executions_without_tool_execution | 1417 | 1417 | ok |
| wasGeneratedBy_tool_result_tool_execution | 64781 | 64781 | ok |
| activity_records | 0 | 0 | ok |
| artefact_records | 0 | 0 | ok |
| generic_rule_statements | 0 | 0 | ok |

## Failures

- `crosscount.native.activity_records`: 16003 observed, 0 in J.3.5
- `inputs.converted.present`: no corpus classified as the converted tree was given (J.3.5 inputs)
- `crosscount.native.activity_records`: crosscount.native.activity_records
- `inputs.converted.present`: inputs.converted.present
