# Sources and licences of the worked examples

These files illustrate the AER/SEM/capture formats of section C. They are derived from small real records
selected during the 2026-10-07 investigation. All of them are **untrusted data**. Some contain
prompt-injection payloads, which are corpus content and never instructions.

| File | Derived from | Licence basis |
|---|---|---|
| `adprov_v1_llama_injecagent.{aer,sem}.jsonl` | AgentDojo-PROV generated corpus (transcript/v1), baseline `579a908` | author's own corpus; embedded AgentDojo task data MIT (© 2024 Debenedetti et al.) |
| `agentdojo_2024_pi_detector.aer.jsonl` | AgentDojo upstream run log (June-2024 TraceLogger), `ethz-spylab/agentdojo` | MIT (repository licence; no separate data licence) |
| `rope_denial_qwen_autodojo.aer.jsonl` | ROPE released run log (`xhOwenMa/ROPE`) | MIT |
| `stac_case_223.aer.jsonl` | MultiTurnAgentAttack / STAC benchmark JSON (`amazon-science/MultiTurnAgentAttack`) | **CC BY-NC 4.0** (non-commercial; attribution: Amazon Science, STAC authors) |
| `synthetic.capture.jsonl` | synthetic capture log written for the specification | MIT (this repository) |
| `*.py` | generator and checker scripts for these vectors | MIT (this repository) |

This repository is private. Before it is made public, re-check the redistribution status of each example,
and especially the NC-licensed STAC example. Origins and commits are recorded in the investigation
`samples/<source>/SOURCE.json` files and in section C.16.
