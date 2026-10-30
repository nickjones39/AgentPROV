# Gate D (full, release mode): pass

- commit `f0410684baf0f46b3cc50b4255e8e33a59f9a3f5`, started 2026-10-22T14:20:29Z, 1762.3 s, 8 workers
- executions 35905/35905 checked, 35905 passed, 0 failed
- profile `agentdojo.suites@1`; every D8 tier in release mode, a skipped check is a failure (MP-3)
- **accepted gaps:** converted

## native: 18241/18241 passed

wall per execution: mean 0.3598 s, p95 0.7692 s, max 5.3288 s; statements: mean 263.2, max 4129

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
| activity_records | 0 | 0 | ok |
| artefact_records | 0 | 0 | ok |
| generic_rule_statements | 0 | 0 | ok |
| environment_load_activities (item 5) | 16003 | 16003 derived | ok |

reported separately (mixtral): 7 executions

reported separately (outcome_only): 207 executions

## release: 17664/17664 passed

wall per execution: mean 0.4245 s, p95 0.9129 s, max 12.232 s; statements: mean 287.6, max 8373

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
| environment_load_activities (item 5) | 0 | 0 derived | ok |
