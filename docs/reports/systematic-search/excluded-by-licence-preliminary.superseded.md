# Notable sources excluded by licence (preliminary)

> **Superseded** on 2026-10-11 by `included-excluded.md` (section 3, "Good sources excluded only by licence", and the
> full table) and `records-merged.jsonl`. Kept unchanged below as the preliminary record. In the final screening,
> Hugging Face datasets whose only licence evidence was a missing tag are `unknown` rather than `none` (LIC rule 1).

Status: **preliminary**, 2026-10-11. This table is generated from the S1 (code platforms) and S3 (data repositories)
screening records, which are copied under `data/`. It lists every screened record that appears to contain per-run logs
but is excluded under EX-LIC-1 (no licence) or EX-LIC-2 (no redistribution), or whose licence is still unresolved
(S3 `other`/`unknown`). The final included/excluded table, after the literature search (S2), de-duplication and
licence verification, replaces this file. Run counts and formats are the search agents' estimates from listings and
have not been verified. Names and URLs are third-party data, shown with their printable characters only.

| Search | Record | Licence | Format (estimated) | Runs (estimated) | Reason | URL |
|---|---|---|---|---|---|---|
| S3 | idacy/control-arena-runs | none | Inspect .eval (7,123) + csv/py (30,691 files, 28.7 GB) | 30691 files | licence: none | https://huggingface.co/datasets/idacy/control-arena-runs |
| S1 | Eden-Wang1710/SRFT | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 23961 | no_licence | https://github.com/Eden-Wang1710/SRFT |
| S1 | ch1y4n/MSFA | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 20878 | no_licence | https://github.com/ch1y4n/MSFA |
| S1 | AgentRewardBench | custom-restrictive | web agent trajectories + judgments JSON, screenshots | 20835 | restrictive_licence_(no_redistribution_of_derived_data_or_eval_only) | https://huggingface.co/datasets/McGill-NLP/agent-reward-bench |
| S3 | tomciotomcio/agentdojo-trajectories | none | byte-identical file listing to sungjuncho/agentdojo-trajectories | 15096 files | duplicate/mirror of sungjuncho/agentdojo-trajectories | https://huggingface.co/datasets/tomciotomcio/agentdojo-trajectories |
| S3 | sungjuncho/agentdojo-trajectories | none | AgentDojo run JSON per task (layout model/suite/user_task/attack/injection_task.json = AgentDojo TraceLogger layout, minus pipeline/benchmar | 15095 | licence: none | https://huggingface.co/datasets/sungjuncho/agentdojo-trajectories |
| S1 | sungjuncho/agentdojo-trajectories | none | AgentDojo TraceLogger JSON, one file per run (model/suite/user_task/attack/injection_task.json) | 15094 | no_licence | https://huggingface.co/datasets/sungjuncho/agentdojo-trajectories |
| S1 | timothytmzhou/elba | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 11101 | no_licence | https://github.com/timothytmzhou/elba |
| S3 | nvidia/Nemotron-AIQ-Agentic-Safety-Dataset-1.0 | other | parquet of workflow traces/logs (AIQ research-assistant; safety and security splits, with_defense / without_defense) | 10815 files | licence: other | https://huggingface.co/datasets/nvidia/Nemotron-AIQ-Agentic-Safety-Dataset-1.0 |
| S3 | schaeff/CIAware-Bench-Data | none | Inspect .eval (2,538 archives) + yaml/json | 9516 files | licence: none | https://huggingface.co/datasets/schaeff/CIAware-Bench-Data |
| S1 | idacy/control-arena-runs (ControlArena runs) | none | Inspect .eval (7,123 files) + csv/json analysis | 7123 | no_licence | https://huggingface.co/datasets/idacy/control-arena-runs |
| S1 | TheAgentCompany experiments | none | OpenHands trajectory/completions JSON(.gz) + eval result JSON + screenshots | 4000 | no_licence | https://github.com/TheAgentCompany/experiments |
| S1 | rohsequ/Agent-Sentry-Bounding-LLM-Agents | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 3732 | no_licence | https://github.com/rohsequ/Agent-Sentry-Bounding-LLM-Agents |
| S1 | meet-the-1337/AgenticAi-deployemnt-attack-analyzer | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 3731 | no_licence | https://github.com/meet-the-1337/AgenticAi-deployemnt-attack-analyzer |
| S1 | Eden-Wang1710/srft-repo | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 3041 | no_licence | https://github.com/Eden-Wang1710/srft-repo |
| S3 | stewy33/oai-hf-incident-replication | none | Inspect .eval (1,100) + md summaries + tsv | 2532 files | licence: none | https://huggingface.co/datasets/stewy33/oai-hf-incident-replication |
| S3 | aisa-group/instrumental-choices-agent-traces | none | Inspect .eval (210) + diagnostic jsonl.gz + viewer sessions JSONL (1,680) | 2105 files | licence: none | https://huggingface.co/datasets/aisa-group/instrumental-choices-agent-traces |
| S1 | Autumn1101/SentiAgent-data | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 1898 | no_licence | https://github.com/Autumn1101/SentiAgent-data |
| S1 | flo1166/Data_Security_Agentic_AI_Control_Flow | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 1740 | no_licence | https://github.com/flo1166/Data_Security_Agentic_AI_Control_Flow |
| S1 | veryzenzain/Agent-Dojo-Benchmarks-Defenses | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 1315 | no_licence | https://github.com/veryzenzain/Agent-Dojo-Benchmarks-Defenses |
| S3 | MaxDevv/real-pi-coding-agent-traces-sessions | other | jsonl sessions (1,292, 778 MB) | 1294 files | licence: other | https://huggingface.co/datasets/MaxDevv/real-pi-coding-agent-traces-sessions |
| S3 | jbostock/untrusted-monitoring-2026-paper | none | Inspect .eval/json logs (96 gz + 54 json) | 887 files | licence: none | https://huggingface.co/datasets/jbostock/untrusted-monitoring-2026-paper |
| S1 | AgentBenchAudit/evidence-bounds | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 600 | no_licence | https://github.com/AgentBenchAudit/evidence-bounds |
| S1 | gss10282023/benchmarkCount | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 600 | no_licence | https://github.com/gss10282023/benchmarkCount |
| S1 | Wang-Yanting/AgentWatcher | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 560 | no_licence | https://github.com/Wang-Yanting/AgentWatcher |
| S1 | pragup/agent-security-proxy | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 393 | no_licence | https://github.com/pragup/agent-security-proxy |
| S3 | anonymous-dataset-submission-warp/warp-taskgen-generated-ipi-tasks-50 | none | AgentLab browser-agent trajectories (artifacts/<model>/<task>.tar.gz) + runs/tasks/variants jsonl | 306 files | licence: none | https://huggingface.co/datasets/anonymous-dataset-submission-warp/warp-taskgen-generated-ipi-tasks-50 |
| S1 | RayaBuckley/Conflux | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 258 | no_licence | https://github.com/RayaBuckley/Conflux |
| S3 | neulab/agent-data-collection | none | Agent Data Protocol jsonl (92 files; 498 GB) | 130 files | licence: none | https://huggingface.co/datasets/neulab/agent-data-collection |
| S1 | zhuoer-GG/Agent-Compression-Aware-IPI | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 125 | no_licence | https://github.com/zhuoer-GG/Agent-Compression-Aware-IPI |
| S3 | jafarisbarov/mmaci-pilot-inspect-logs | none | Inspect .eval (6) + episodes.json | 69 files | licence: none | https://huggingface.co/datasets/jafarisbarov/mmaci-pilot-inspect-logs |
| S1 | MuneezaAzmat/RH_TrustyAI_POC | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 32 | no_licence | https://github.com/MuneezaAzmat/RH_TrustyAI_POC |
| S3 | AgentSuite/tau-bench-trajectories | none | JSONL per model (30 models x 165 tasks) | 32 files | licence: none | https://huggingface.co/datasets/AgentSuite/tau-bench-trajectories |
| S3 | AgentSuite/tau2-bench-trajectories | none | JSONL per model (30 models x 278 tasks) | 32 files | licence: none | https://huggingface.co/datasets/AgentSuite/tau2-bench-trajectories |
| S3 | cx-cmu/agent_trajectories | none | json/jsonl/parquet (2 GB) | 23 files | licence: none | https://huggingface.co/datasets/cx-cmu/agent_trajectories |
| S1 | kaustubhadhe1206/AgentDojo_POC | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 15 | no_licence | https://github.com/kaustubhadhe1206/AgentDojo_POC |
| S3 | Stage-jh-monitor/appworld-qwen35-4b-agent-rl-epoch3 | none | generations.jsonl + judged judgments (18.5 MB) | 10 files | licence: none | https://huggingface.co/datasets/Stage-jh-monitor/appworld-qwen35-4b-agent-rl-epoch3 |
| S1 | Juna1013/agentdojo | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 9 | no_licence | https://github.com/Juna1013/agentdojo |
| S1 | sohamtulsyan/deploymentinc-project-1 | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 6 | no_licence | https://github.com/sohamtulsyan/deploymentinc-project-1 |
| S1 | RhizoNymph/a2a-transmission-bench | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 3 | no_licence | https://github.com/RhizoNymph/a2a-transmission-bench |
| S1 | bnssaanirudh/NiyamTrace-X | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 2 | no_licence | https://github.com/bnssaanirudh/NiyamTrace-X |
| S1 | veera-vsn/ra-capbac | none | AgentDojo TraceLogger-shaped JSON (path pattern user_task_N/<attack>/injection_task_N.json) | 1 | no_licence | https://github.com/veera-vsn/ra-capbac |
| S1 | AgentLab traces (TMLR) | none | tar.gz parts of AgentLab/BrowserGym traces |  | no_licence | https://huggingface.co/datasets/agentlabtraces/agentlabtraces |
| S1 | OpenHandsCommunity/eval-output-webarena | none | jsonl + metadata |  | no_licence | https://huggingface.co/datasets/OpenHandsCommunity/eval-output-webarena |
| S3 | ffuuugor/agentdojo-dump | none | flattened tool-call rows (parquet): suite_name,user_task_id,injection_task_id,attack_name,tool_call_function,tool_call_args,tool_response,la | 3 files | licence: none | https://huggingface.co/datasets/ffuuugor/agentdojo-dump |
| S3 | Junzj/agentdojo-dump | none | same as ffuuugor/agentdojo-dump | 3 files | duplicate of ffuuugor/agentdojo-dump | https://huggingface.co/datasets/Junzj/agentdojo-dump |
| S3 | adityaasinha28/control_arena_agentdojo | none | parquet (verl-style prompt/reward_model/extra_info + trajectory_data string + misalignment evidence) | 2 files | licence: none | https://huggingface.co/datasets/adityaasinha28/control_arena_agentdojo |
| S3 | antieval/agentharm-trajectories | none | JSONL per model (5 files: claude-opus-4.5, claude-sonnet-4.5, gpt-5.1, gpt-5.2, gpt-5.4) | 6 files | licence: none | https://huggingface.co/datasets/antieval/agentharm-trajectories |
| S3 | antieval/cybench-trajectories | none | JSONL per model (6 files) | 7 files | licence: none | https://huggingface.co/datasets/antieval/cybench-trajectories |
| S3 | open-athena/glm52-datagen-r11-101-agentic-indirect-prompt-injection-v2-traces | none | parquet traces (7 files, 22.6 MB) | 8 files | licence: none | https://huggingface.co/datasets/open-athena/glm52-datagen-r11-101-agentic-indirect-prompt-injection-v2-traces |
| S3 | SWE-Gym/OpenHands-Sampled-Trajectories | none | parquet messages list (301 MB) | 5 files | licence: none | https://huggingface.co/datasets/SWE-Gym/OpenHands-Sampled-Trajectories |
| S3 | Composing Malice: Empirical Measurement of Compositional Prompt Injection Vulnerability in Agentic Pipelines | none | CSV of real trials (real_trials_*.csv) + composition_*.csv (24 MB) |  | licence: none | https://osf.io/za7gc |

52 records.
