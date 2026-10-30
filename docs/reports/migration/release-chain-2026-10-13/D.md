# Gate D (full, release mode): fail

- commit `3523336ac1528d5a2ae240b009834a6ef185080a`, started 2026-10-12T19:34:13Z, 2071.3 s, 10 workers
- executions 17664/17664 checked, 0 passed, 17664 failed
- profile `agentdojo.suites@1`; every D8 tier in release mode, a skipped check is a failure (MP-3)
- **accepted gaps:** converted

## release: 0/17664 passed

wall per execution: mean 1.1663 s, p95 2.7858 s, max 25.5837 s; statements: mean 245.8, max 7199

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

- `d8.tiers.release`: 17664 executions failing a D8 tier (a skipped check counts as a failure)
- `inputs.native.present`: no corpus classified as the native tree was given (J.3.5 inputs)
- `ex_2226siqs3zk4le5ekl3kvjqtxq`: d8.aer
- `ex_2243dm37th5cwqttgqtfqpnzs5`: d8.aer
- `ex_224hmyraai3ksg3h2boz4lsxat`: d8.aer
- `ex_22daldfvnvgju346z6ksaazaln`: d8.aer
- `ex_22fbutn5x24nue3z5rdxndms6m`: d8.aer
- `ex_22hpkmfrnlpsrjzebcdjdrwspk`: d8.aer
- `ex_22i35izuduiw2eykg2kjenaxme`: d8.aer
- `ex_22jjrsunefbcdskwmm6pih6juu`: d8.aer
- `ex_22kyuweoy6oh23arqpmpjpjoba`: d8.aer
- `ex_22mfionocnegak2q6zuxabxieu`: d8.aer
- `ex_22nicwefracxpfh4sq3qzz4fue`: d8.aer
- `ex_22o6rt7a3uo36wue7f7iyn3fhq`: d8.aer
- `ex_22ok4mtiadq2veiulsexh6kfn5`: d8.aer
- `ex_22pak72jgmivenuvtb5nrctsi7`: d8.aer
- `ex_22s7stsh5yomu4ofnbhqyfgvyn`: d8.aer
- `ex_22uubdmgk4uzqumnbfrcrreyc3`: d8.aer
- `ex_22v63zkgzlubfj7zz7zq6hpzqs`: d8.aer
- `ex_22xoe7ttoocrliqlb52gpcsblz`: d8.aer
- `ex_22zswwvfh4ttlbdwuinmakhktz`: d8.aer
- `ex_235a3yprsk33mbx4exgilzav4r`: d8.aer
