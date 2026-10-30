# S2 literature search - summary

## PRISMA-style counts

| Step | Count |
|---|---|
| Records identified, database queries (sum of retrieved over 27 queries) | 7500 |
| Records identified, web searches (arXiv ids returned) | 90 |
| Duplicates removed (cross-query and cross-database) | 3716 |
| Unique papers screened at title/abstract | 3874 |
| Excluded at title/abstract | 2109 |
| Retained for full-text / data-release assessment | 1765 |
| Full-text assessed (papers; arXiv HTML or Zenodo record retrieved) | 1444 |
| Excluded at full text (papers) | 1414 |
| Retained at stage 1 but not assessable (non-arXiv publisher pages) | 321 |
| Dataset-hub records added from Zenodo/Hugging Face dataset searches (curated, separate from paper screening) | 30 |
| **Included (papers + dataset records)** | **35** (30 papers, 5 dataset records) |
| of which security-topic | 24 |
| of which AgentDojo uses/extends | 8 |
| Qualifying logs but excluded by licence (none / custom-restrictive / ND) | 15 |
| Full-text records with `releases_logs=unclear` (manual follow-up) | 237 |

AgentDojo ecosystem sizes: Semantic Scholar forward citations 152; OpenAlex cites 102 (proceedings id) + 7 (arXiv-DOI id); OpenAlex full-text mentions of 'AgentDojo' since 2024: 1,188; arXiv title/abstract mentions: 114. Relation of pooled papers to AgentDojo: uses=223, cites_only=1044, extends=30, none=2577.

### Stage-1 exclusion reasons

- 1573: screened out: no benchmark/dataset+log-release signal and no AgentDojo link in title/abstract
- 390: out of scope: no LLM-agent signal in title/abstract
- 277: non-arXiv publication; publisher full text not retrieved; no statement of releasing logs/trajectories in the title/abstract
- 116: out of scope: non-LLM domain (title)
- 44: non-arXiv publication; abstract mentions release of logs/data but full text and data location not retrievable automatically (manual follow-up)
- 30: out of scope: published before 2023 (pre-LLM-agent era)

### Full-text exclusion reasons (top)

- 430: full text: links found are code-only or unrelated; no statement of releasing logs/trajecto
- 361: full text: no public data/code repository link found
- 311: repository/dataset inspected: code, task definitions or aggregate results only; no per-run
- 194: unconfirmed: release of logs/trajectories possible or claimed but no per-run machine-reada
- 46: Zenodo record holds the paper/preprint or documents only; no run logs
- 26: Zenodo record: code/package or aggregate results; no per-run logs identified from the reco
- 15: licence: no licence on artefact
- 12: Zenodo record not retrievable (410/err)
- 5: Zenodo archive described as containing runs/traces; archive contents not machine-verified 
- 3: manual review:  repository is a security-scanner tool (data/eval = prompts 
- 2: known source (own / upstream), not a new finding
- 2: parquet dump, no README; contents/provenance not documented

## Included sources (per-run logs/trajectories released openly, acceptable licence)

Confidence: high = confirmed by API/HF/Zenodo file listing; medium = repository HTML tree or name-based inference; `-` = dataset record. Logs not downloaded or parsed.

| id | title | AgentDojo | topic | log location | format | licence | licence source | conf |
|---|---|---|---|---|---|---|---|---|
| 2604.02022 | ATBench: A Diverse and Realistic Agent Trajectory Benchmark for Safety | cites_only | sec | https://huggingface.co/datasets/AI45Research/ATBench | json | Apache-2.0 | HF dataset card metadata license: apache-2.0 | medium |
| 2609.06972 | AgentDrift: A Step-Labeled Benchmark of Injection-Hijacked LLM Agent T | uses | sec | https://github.com/Asif-0209/AgentDrift | json, jsonl | CC-BY-4.0 | repo file LICENSE; repository-level licence, data scope not stated separately | medium |
| 2602.03117 | AgentDyn: Are Your Agent Security Defenses Deployable in Real-World Dy | extends | sec | https://github.com/leolee99/AgentDyn |  | MIT | repo file LICENSE; repository-level licence, data scope not stated separately | medium |
| 2609.17527 | Agentic Societies Need a Social Harness | cites_only | sec | https://github.com/social-harness/social-harness-paper |  | MIT | README licence statement (no LICENSE file in repo root) | medium |
| 2609.34245 | Certified Multi-Source Integrity for Structured Agent Actions | cites_only | sec | https://github.com/anmolpandey299/certified-multisource-integrity |  | MIT | repo file LICENSE; repository-level licence, data scope not stated separately | medium |
| 2506.12104 | DRIFT: Dynamic Rule-Based Defense with Injection Isolation for Securin | uses | sec | https://github.com/safo-lab/drift |  | MIT | repo file LICENSE; repository-level licence, data scope not stated separately | high |
| 2601.04795 | Defense Against Indirect Prompt Injection via Tool Result Parsing | uses | sec | https://github.com/qiang-yu/agentdojo |  | MIT | repo file LICENSE; repository-level licence, data scope not stated separately | medium |
| zenodo:23138310 | Evaluating AI agent permission caps under prompt injection with refere | uses | sec | https://zenodo.org/records/23138310 | json (AgentDojo runs/ layout), | CC-BY-4.0 | Zenodo record metadata licence: cc-by-4.0 | - |
| 2502.01822 | Firewalls to Secure Dynamic LLM Agentic Networks | cites_only | sec | https://github.com/amrgomaaelhady/Firewall-Agentic-Networks |  | MIT | repo file LICENSE; repository-level licence, data scope not stated separately | medium |
| 2604.15368 | LogJack: Indirect Prompt Injection Through Cloud Logs Against LLM Debu | cites_only | sec | https://github.com/harshshah1997/logjack |  | MIT | repo file LICENSE; repository-level licence, data scope not stated separately | high |
| 2608.06909 | Long-Horizon Agent Trajectory Attribution: A Unified Benchmark and Fin | uses | sec | https://github.com/chenjing-2024/agent-trajectory-attribution |  | CC-BY-4.0 | repo file LICENSE-DATA; data-specific licence file | high |
| 2604.27819 | MCPHunt: An Evaluation Framework for Cross-Boundary Data Propagation i | cites_only | sec | https://huggingface.co/datasets/lihaonan0716/mcphunt-agent-traces | json | CC-BY-4.0 | HF dataset card metadata license: cc-by-4.0 | high |
| 2608.27496 | ROPE: Routed Origin Policy Enforcement against Indirect Prompt Injecti | extends | sec | https://github.com/xhOwenMa/ROPE |  | MIT | repo file LICENSE; repository-level licence, data scope not stated separately | medium |
| 2606.13757 | SEVRA-BENCH: Social Engineering of Vulnerabilities in Review Agents | cites_only | sec | https://huggingface.co/datasets/RedAI4Code/SEVRA | json, jsonl | MIT | HF dataset card metadata license: mit | high |
| zenodo:21631031 | TELOS Agentic Validation Evidence: AgentDojo (139 Evaluations; 100% In | uses | sec | https://zenodo.org/records/21631031 | jsonl | CC-BY-4.0 | Zenodo record metadata licence: cc-by-4.0 | - |
| 2604.07223 | TraceSafe: A Systematic Assessment of LLM Guardrails on Multi-Step Too | cites_only | sec | https://github.com/cycraft-corp/tracesafe | jsonl | Apache-2.0 | repo file LICENSE; repository-level licence, data scope not stated separately | medium |
| hf-dataset:AI-Secure/DTap-Bench-Agent-Trajectories | AI-Secure/DTap-Bench-Agent-Trajectories | none | sec | https://huggingface.co/datasets/AI-Secure/DTap-Bench-Agent-Trajectories | , json, md | Apache-2.0 | HF dataset card metadata license: apache-2.0 | - |
| 2608.22510 | ClawProBench: Trace-Aware Evaluation of AI Agents with Runtime Coverag | none | sec | https://github.com/suyoumo/clawprobench |  | Apache-2.0 | repo file LICENSE; repository-level licence, data scope not stated separately | medium |
| 2604.16706 | Evaluating Tool-Using Language Agents: Judge Reliability, Propagation  | none | sec | https://github.com/bhaskargurram-ai/agenthallu-bench | csv | MIT | repo file LICENSE; repository-level licence, data scope not stated separately | medium |
| 2609.14976 | MemRiskBench: Trace-Aware Risk-Preserving Evaluation for Long-Horizon  | none | sec | https://github.com/fuxue-mingzhu/memriskbench | json | MIT | README licence statement (no LICENSE file in repo root) | high |
| 2609.09203 | OpenDiscoveryTrace: Process Traces for Evaluating AI Scientist Workflo | none | sec | https://huggingface.co/datasets/aayambansall/OpenDiscoveryTrace | json | CC-BY-4.0 | HF dataset card metadata license: cc-by-4.0 | high |
| zenodo:23247488 | Replication package: Beyond Pass or Fail: Mining Agent Trajectories to | none | sec | https://zenodo.org/records/23247488 | zip | CC-BY-4.0 | Zenodo record metadata licence: cc-by-4.0 | - |
| 2604.20779 | SWE-chat: Coding Agent Interactions From Real Users in the Wild | none | sec | https://huggingface.co/datasets/SALT-NLP/SWE-chat | parquet | ODC-By-1.0 | HF dataset card metadata license: odc-by; dataset is gated (auto) | high |
| 2604.17596 | Terminal Wrench: A Dataset of 331 Reward-Hackable Environments and 3,6 | none | sec | https://github.com/few-sh/terminal-wrench |  | Apache-2.0 | repo file LICENSE; repository-level licence, data scope not stated separately | high |
| 2607.02255 | AgenticSTS: A Bounded-Memory Testbed for Long-Horizon LLM Agents | none | gen | https://github.com/alayalab/agenticsts | gz, tar | CC-BY-4.0 | repo file LICENSE; repository-level licence, data scope not stated separately | high |
| 2602.18998 | Evaluating Test-Time Scaling of General LLM Agents | none | gen | https://github.com/cxcscmu/general-agentbench |  | MIT | repo file LICENSE; repository-level licence, data scope not stated separately | high |
| 2610.00917 | Finding the Right Fit: Model-Harness Interactions across Agent Tasks | none | gen | https://huggingface.co/datasets/yixuanli97/finding-the-right-fit | csv, parquet | CC-BY-NC-4.0 | HF dataset card metadata license: cc-by-nc-4.0 | high |
| 2604.13072 | LiveClawBench: Benchmarking LLM Agents on Complex, Real-World Assistan | none | gen | https://github.com/mosi-ai/liveclawbench | parquet | MIT | repo file LICENSE; repository-level licence, data scope not stated separately | high |
| 2607.06411 | RuBench: A Repository-Level Agentic Coding Benchmark with Natively Aut | none | gen | https://github.com/eugeneshilow/rubench |  | CC-BY-4.0 | README licence statement (no LICENSE file in repo root) | high |
| 2608.05573 | SkillTV-Bench: Benchmarking How Well Judges Perform on Skill-Augmented | none | gen | https://github.com/HanZhi306/SkillTV-Bench |  | Apache-2.0 | repo file LICENSE; repository-level licence, data scope not stated separately | medium |
| 2505.08638 | TRAIL: Trace Reasoning and Agentic Issue Localization | none | gen | https://huggingface.co/datasets/PatronusAI/TRAIL | json | MIT | HF dataset card metadata license: mit; dataset is gated (auto) | medium |
| 2608.06346 | TRAJDEBUG: Tracing Error Lifecycle to Identify Critical Failures in Lo | none | gen | https://github.com/thu-keg/trajdebug |  | MIT | repo file LICENSE; repository-level licence, data scope not stated separately | medium |
| 2608.08239 | The Replay Gap: Static Evaluation of Model Switching in LLM Agents Sco | none | gen | https://github.com/ashrithag/replay-gap | gz, json, jsonl | MIT | repo file LICENSE; repository-level licence, data scope not stated separately | high |
| 2506.18824 | Understanding Software Engineering Agents: A Study of Thought-Action-R | none | gen | https://github.com/sola-st/llm-agents-study |  | MIT | repo file LICENSE; repository-level licence, data scope not stated separately | medium |
| zenodo:22151975 | What the score hides: an audit of BixBench — agent trajectories | none | gen | https://zenodo.org/records/22151975 | json, jsonl | CC-BY-4.0 | Zenodo record metadata licence: cc-by-4.0 | - |

## Most promising NEW sources (not in the known list), security first

- **ATBench: A Diverse and Realistic Agent Trajectory Benchmark for Safety Evaluation and Diag** (2604.02022; AgentDojo: cites_only; Apache-2.0) - https://huggingface.co/datasets/AI45Research/ATBench
- **AgentDrift: A Step-Labeled Benchmark of Injection-Hijacked LLM Agent Trajectories** (2609.06972; AgentDojo: uses; CC-BY-4.0) - https://github.com/Asif-0209/AgentDrift
- **Agentic Societies Need a Social Harness** (2609.17527; AgentDojo: cites_only; MIT) - https://github.com/social-harness/social-harness-paper
- **Certified Multi-Source Integrity for Structured Agent Actions** (2609.34245; AgentDojo: cites_only; MIT) - https://github.com/anmolpandey299/certified-multisource-integrity
- **Defense Against Indirect Prompt Injection via Tool Result Parsing** (2601.04795; AgentDojo: uses; MIT) - https://github.com/qiang-yu/agentdojo
- **Evaluating AI agent permission caps under prompt injection with reference scoring and enfo** (zenodo:23138310; AgentDojo: uses; CC-BY-4.0) - https://zenodo.org/records/23138310
- **Firewalls to Secure Dynamic LLM Agentic Networks** (2502.01822; AgentDojo: cites_only; MIT) - https://github.com/amrgomaaelhady/Firewall-Agentic-Networks
- **LogJack: Indirect Prompt Injection Through Cloud Logs Against LLM Debugging Agents** (2604.15368; AgentDojo: cites_only; MIT) - https://github.com/harshshah1997/logjack
- **Long-Horizon Agent Trajectory Attribution: A Unified Benchmark and Fine-Grained Annotation** (2608.06909; AgentDojo: uses; CC-BY-4.0) - https://github.com/chenjing-2024/agent-trajectory-attribution
- **MCPHunt: An Evaluation Framework for Cross-Boundary Data Propagation in Multi-Server MCP A** (2604.27819; AgentDojo: cites_only; CC-BY-4.0) - https://huggingface.co/datasets/lihaonan0716/mcphunt-agent-traces
- **SEVRA-BENCH: Social Engineering of Vulnerabilities in Review Agents** (2606.13757; AgentDojo: cites_only; MIT) - https://huggingface.co/datasets/RedAI4Code/SEVRA
- **TELOS Agentic Validation Evidence: AgentDojo (139 Evaluations; 100% Injection Detection, 5** (zenodo:21631031; AgentDojo: uses; CC-BY-4.0) - https://zenodo.org/records/21631031
- **TraceSafe: A Systematic Assessment of LLM Guardrails on Multi-Step Tool-Calling Trajectori** (2604.07223; AgentDojo: cites_only; Apache-2.0) - https://github.com/cycraft-corp/tracesafe
- **AI-Secure/DTap-Bench-Agent-Trajectories** (hf-dataset:AI-Secure/DTap-Bench-Agent-Trajectories; AgentDojo: none; Apache-2.0) - https://huggingface.co/datasets/AI-Secure/DTap-Bench-Agent-Trajectories
- **ClawProBench: Trace-Aware Evaluation of AI Agents with Runtime Coverage and Frozen Workpla** (2608.22510; AgentDojo: none; Apache-2.0) - https://github.com/suyoumo/clawprobench
- **Evaluating Tool-Using Language Agents: Judge Reliability, Propagation Cascades, and Runtim** (2604.16706; AgentDojo: none; MIT) - https://github.com/bhaskargurram-ai/agenthallu-bench
- **MemRiskBench: Trace-Aware Risk-Preserving Evaluation for Long-Horizon LLM Agents** (2609.14976; AgentDojo: none; MIT) - https://github.com/fuxue-mingzhu/memriskbench
- **OpenDiscoveryTrace: Process Traces for Evaluating AI Scientist Workflows** (2609.09203; AgentDojo: none; CC-BY-4.0) - https://huggingface.co/datasets/aayambansall/OpenDiscoveryTrace
- **Replication package: Beyond Pass or Fail: Mining Agent Trajectories to Attribute Failures ** (zenodo:23247488; AgentDojo: none; CC-BY-4.0) - https://zenodo.org/records/23247488
- **SWE-chat: Coding Agent Interactions From Real Users in the Wild** (2604.20779; AgentDojo: none; ODC-By-1.0) - https://huggingface.co/datasets/SALT-NLP/SWE-chat

AgentDojo-format run archives among them (best fit for the AgentDojo native-log adapter): 2601.04795 (qiang-yu/agentdojo `runs/`, 29 model directories), Zenodo 23138310 (agent-authority-caps, AgentDojo-layout `runs/`), Zenodo 21631031 (TELOS, 139 AgentDojo evaluations as JSONL). AgentDojo-derived HF dumps without a licence are excluded (see below).

## Excluded because of licence (logs otherwise qualify)

| id | title | licence | licence source | AgentDojo | log location |
|---|---|---|---|---|---|
| 2506.15253 | RAS-Eval: A Comprehensive Benchmark for Security Evaluation of LLM Age | none | no LICENSE file in repo root and no licence statement in README | uses | https://github.com/lanzer-tree/ras-eval |
| 2608.14132 | Act2Intention: A Benchmark For Developing Active Mobile Agents Through | none | no LICENSE file in repo root and no licence statement in README | none | https://github.com/npuNancy/Act2Intention |
| 2607.19913 | JANUS: Foreseeing Latent Risk for Long-Horizon Agent Safety | none | no LICENSE file in repo root and no licence statement in README | uses | https://github.com/xiongyuaay/JANUS |
| 2608.08939 | Not an A11y: How Android Accessibility Exposes Mobile AI Agents to Ind | none | no LICENSE file in repo root and no licence statement in README | cites_only | https://github.com/rahuldeiv/Not-An-A11y |
| 2607.01793 | Safety Testing LLM Agents at Scale: From Risk Discovery to Evidence-Gr | none | no LICENSE file in repo root and no licence statement in README | cites_only | https://github.com/Yunhao-Feng/Vera |
| 2606.22678 | RigorBench: Benchmarking Engineering Process Discipline in Autonomous  | none | no LICENSE file in repo root and no licence statement in README | none | https://github.com/meherbhaskar/rigorbench |
| 2605.08083 | LLMs Improving LLMs: Agentic Discovery for Test-Time Scaling | none | no LICENSE file in repo root and no licence statement in README | none | https://github.com/zhengkid/autotts |
| 2605.07177 | HyperEyes: Dual-Grained Efficiency-Aware Reinforcement Learning for Pa | none | no LICENSE file in repo root and no licence statement in README | none | https://github.com/deepexperience/hypereyes |
| 2601.21558 | ASTRA: Automated Synthesis of agentic Trajectories and Reinforcement A | none | no LICENSE file in repo root and no licence statement in README | none | https://github.com/LianjiaTech/astra |
| 2602.00133 | PredictionMarketBench: A SWE-bench-Style Framework for Backtesting Tra | none | no LICENSE file in repo root and no licence statement in README | none | https://github.com/oddpool/predictionmarketbench |
| 2511.19773 | Scaling Agentic Reinforcement Learning for Tool-Integrated Reasoning i | none | no LICENSE file in repo root and no licence statement in README | none | https://github.com/lucanyc/vista-gym |
| 2511.01093 | Continual Learning, Not Training: Online Adaptation For Agents | none | no LICENSE file in repo root and no licence statement in README | none | https://github.com/arc-computer/atlas-sdk |
| hf-dataset:sungjuncho/agentdojo-trajectories | sungjuncho/agentdojo-trajectories | none | HF dataset card has no license field or tag | uses | https://huggingface.co/datasets/sungjuncho/agentdojo-trajectories |
| hf-dataset:tomciotomcio/agentdojo-trajectories | tomciotomcio/agentdojo-trajectories | none | HF dataset card has no license field or tag | uses | https://huggingface.co/datasets/tomciotomcio/agentdojo-trajectories |
| hf-dataset:aksh-n/control_arena_agentdojo-monitor-labels | aksh-n/control_arena_agentdojo-monitor-labels | none | HF dataset card has no license field or tag | uses | https://huggingface.co/datasets/aksh-n/control_arena_agentdojo-monitor-labels |

## Release status of the known sources (from this search)

- AgentDyn (arXiv:2602.03117): decision=include, releases_logs=yes, licence=MIT
- ROPE (arXiv:2608.27496): decision=include, releases_logs=yes, licence=MIT
- DRIFT (arXiv:2506.12104): decision=include, releases_logs=yes, licence=MIT
- AutoDojo (arXiv:2606.15057): decision=exclude, releases_logs=no, licence=MIT - repository/dataset inspected: code, task definitions or aggregate results only; no per-run logs found
- AgentLAB (arXiv:2602.16901): decision=exclude, releases_logs=no, licence=None - repository/dataset inspected: code, task definitions or aggregate results only; no per-run logs found
- ADI (arXiv:2607.05120): decision=exclude, releases_logs=no, licence=None - repository/dataset inspected: code, task definitions or aggregate results only; no per-run logs found
- STAC (arXiv:2509.25624): decision=exclude, releases_logs=no, licence=CC-BY-NC-4.0 - repository/dataset inspected: code, task definitions or aggregate results only; no per-run logs found
- AgentHarm (arXiv:2410.09024): decision=exclude, releases_logs=no, licence=MIT - repository/dataset inspected: code, task definitions or aggregate results only; no per-run logs found
- ASB (reviewed by Agent Security Tools Survey) (arXiv:2410.02644): decision=exclude, releases_logs=no, licence=MIT - repository/dataset inspected: code, task definitions or aggregate results only; no per-run logs found

## Notes for the manuscript

- The include list is dominated by 2026 preprints; maturity and peer-review status vary. Venue is recorded where an index provided one.
- `unclear` records (releases_logs=unclear, stage full_text) are follow-up candidates: release claimed or generic data directory, per-run logs not confirmed.
- Zenodo AgentDojo-PROV record 23276620 (published 2026-10-10) appears in Zenodo search; treated as a known/own source.
- Provenance-related survey found by web search: arXiv:2606.04990 'From Agent Traces to Trust: A Survey of Evidence Tracing and Execution Provenance in LLM Agents' (not a benchmark; relevant to related work).

## Included but with gated (click-through / manual) access - note separately

- 2604.20779 SWE-chat: Coding Agent Interactions From Real Users in the Wild: https://huggingface.co/datasets/SALT-NLP/SWE-chat (taset card metadata license: odc-by; dataset is gated (auto))
- 2505.08638 TRAIL: Trace Reasoning and Agentic Issue Localization: https://huggingface.co/datasets/PatronusAI/TRAIL ( dataset card metadata license: mit; dataset is gated (auto))

## Files

- S2-search-log.md (queries, times, counts, screening rules, incidents)
- S2-records.jsonl (3,904 records: 3,874 papers + 30 dataset records; fields incl. licence, licence_source, evidence_confidence, manual_review)
- raw/ (raw API outputs: Semantic Scholar, OpenAlex, arXiv, OpenReview, HF, Zenodo; reproducible)

