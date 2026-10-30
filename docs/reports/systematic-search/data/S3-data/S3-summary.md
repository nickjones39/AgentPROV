# S3 summary: research data repositories

Search date 2026-10-11 (UTC 07:01-07:50). Read-only API/metadata queries only; nothing downloaded, no data file opened. Details: `S3-search-log.md` (queries, timestamps, counts), `S3-records.jsonl` (156 records), `raw/` (raw hit lists and detail fetches), `scripts/`.

## 1. Counts per repository

| Repository | Pooled hits | Records written | include | include-gated | maybe | exclude |
|---|---|---|---|---|---|---|
| Zenodo | 1,941 unique (56 queries) | 65 (1 is our own AgentDojo-PROV deposit) | 19 | 0 | 19 | 26 |
| Hugging Face | 8,684 unique ids (111 queries) | 68 | 27 | 3 | 18 | 20 |
| Figshare | 529 | 8 | 1 | 0 | 4 | 3 |
| OSF | 10 nodes + 5 registrations | 5 | 0 | 0 | 3 | 2 |
| DataCite (cross-repository index) | 1,394 DOIs | 3 | 0 | 0 | 1 | 2 |
| Kaggle | 233 | 3 | 0 | 0 | 0 | 3 |
| Software Heritage | 539 origins | 1 | 0 | 0 | 1 | 0 |
| Dryad | 98 | 1 | 0 | 0 | 0 | 1 (nothing relevant) |
| Mendeley Data, Papers with Code | n/a | 2 | 0 | 0 | 0 | 2 (no usable search / service retired) |

"include" = public, machine-readable, per-run agent logs (judged from metadata only). "maybe" = plausible but contents unclear, derived or domain-specific. 45 of the include/include-gated records are NEW (not in our earlier notes): 29 Hugging Face, 15 Zenodo, 1 Figshare. The "include" totals for Hugging Face understate supply: hundreds of coding-agent SFT trajectory sets and about 480 `DCAgent/*` trace sets were deliberately not enumerated.

## 2. Known deposits: confirmation

* Zenodo 10.5281/zenodo.12528189 (AgentDojo v0.1.7): confirmed (MIT, 2024-06-25, 52,723,430 B). Concept 12528188 has 36 versions (v0.1.7 to v0.1.35; 17458493 = v0.1.35, 106,596,113 B). Note v0.1.7 has two version DOIs (12528189 and 12528333).
* Zenodo 22135957 / 22140262 (survey artefact): confirmed (cc-by-4.0, 2026-08-28, concept 22135956); inner contents not listable.
* AgentDojo-PROV: confirmed, concept 20692312, five versions, latest 2.3 = 23276620 (2026-10-10, 59 files, ~240 MB incl. `legacy-runs.part*.zip`).
* HF `ai-safety-institute/AgentHarm`: confirmed, but it holds only benchmark definitions (8 files, 0.3 MB). It is not a run-log source. AgentHarm trajectories are in the new `antieval/agentharm-trajectories` (below).
* HF `schaeff/CIAware-Bench-Data`: re-confirmed gated (auto), 2,538 `.eval`, 8.7 GB.

## 3. Most promising NEW deposits with per-run logs

Format claims are inferences from names, layout or cards; no file was opened.

AgentDojo family (highest value for the AgentDojo adapter):

1. **HF `sungjuncho/agentdojo-trajectories`** (mirror: `tomciotomcio/agentdojo-trajectories`, byte-identical listing). 15,095 `.json` files, 180 MB. Path layout `<model>/<suite>/<user_task>/<attack>/<injection_task>.json` is the AgentDojo `runs/` layout without the pipeline/benchmark-version level. Models `gemma-4-E4B-it` (7,915 files) and `qwen3.5-9B` (7,180); suites banking, slack, travel, workspace; attacks include `important_instructions`, `direct`, `ignore_previous`, `injecagent` plus non-standard `chunked_exfiltration`, `delayed_trigger`, `multi_injection_chaining`. No card, no licence tag (redistribution unclear). Viewer failure on heterogeneous tool-call `args` is consistent with AgentDojo `messages[].tool_calls[].args`. Whether files carry `suite_name`, `pipeline_name`, `user_task_id`, `messages`, `utility`, `security` is NOT verified; one ~5 KB sample read would settle it.
2. **Zenodo concept 22973265** (`22973266` v1.0.0 10.9 MB; `22996368` v2.0.0 39 MB; `23138310` v2.1.0; CC-BY-4.0): run-level dataset of 38,938 AgentDojo agent runs (36,679 extracted from the public logs of 22 models plus 2,259 new runs of Claude Haiku 4.5 and two GPT-6 variants) with raw trajectories and token usage for the new runs, plus authority codebook for 74 AgentDojo tools. Raw-trajectory schema unverified.
3. **Zenodo 22011266** (v4.0.0, concept 20731176; v3 `21418519` superseded for a trace-logging defect): per-instance traces (tar.gz) for AgentDojo banking, GPT-5.4-mini, GPT-5.4 and Claude Sonnet 4.6, five defences, "LOGDIR-patched" AgentDojo cell runner. CC-BY-4.0, 3.2 MB zip.
4. **Figshare 10.6084/m9.figshare.32657856** (MIT, 52.9 MB zip): DCA defence artefact with AgentDojo integration, "JSON evaluation logs, usage traces".
5. **HF `antieval/agentharm-trajectories`** (5 models: claude-opus-4.5, claude-sonnet-4.5, gpt-5.1, gpt-5.2, gpt-5.4; 1.5 MB JSONL; no licence) and `antieval/cybench-trajectories` (8.4 MB).

Security benchmarks, other formats (need new adapter families):

6. **HF `AI-Secure/DTap-Bench-Agent-Trajectories`** (apache-2.0): DecodingTrust-Agent Platform, 6,682 tasks (2,806 benign, 3,876 malicious, direct and indirect threat models), 14 domains, SDK dirs claudesdk/googleadk/openaisdk/openclaw, per-run trajectory JSON plus `judge_result.json`. API listing is capped at 100,000 files (2.6 GB is a lower bound). Mirrored partly on Kaggle (1.39 GB).
7. **HF `nvidia/Nemotron-AIQ-Agentic-Safety-Dataset-1.0`**: workflow traces for safety and security splits, with/without defence, 3.3 GB parquet, NVIDIA evaluation-dataset licence (restrictive).
8. **HF `anonymous-dataset-submission-warp/warp-taskgen-generated-ipi-tasks-50`**: AgentLab browser-agent trajectories on WebArena GitLab/Postmill with injected tasks, 6 models, 2.3 GB, no licence tag.
9. **Zenodo** `22737462` (credential-exfiltration transcripts, 16 coding agents), `20404563` (10,000 code-agent misalignment rollouts, 203 MB), `23168099` (OpenHands/Qwen Code trajectories on RedCode-Exec), `18703256` (3,274 IPI trials, 4,694 evidence JSON), `21944598` (1,334 tool-metadata injection runs). All CC-BY-4.0, custom formats.
10. **HF `neurips-adaptive-adversaries/adaptive-adversaries-data`** (cc-by-4.0, 478 MB): 945 attacker-vs-defender battle transcripts plus competition traces.

Inspect `.eval` (fits the Inspect adapter family): Zenodo `20754656` (GAIA scaffold study, 831 MB, 5 models x 3 scaffolds x 3 attempts, cc-by-4.0, best-documented), HF `ai-safety-institute/reward-hacking-olmo3.1-32b-kl0.0-seed2-rollouts` (401 `.eval`, apache-2.0), `stewy33/oai-hf-incident-replication` (1,100 `.eval`), `aisa-group/instrumental-choices-agent-traces` (210 `.eval`), `jbostock/untrusted-monitoring-2026-paper`, `idacy/control-arena-runs` (7,123 `.eval`, 28.7 GB), `rustmizan-org/rustmizan-eval-logs`, `naderalfares/epoch_ai_swebench_verified` (76 GB).

General agentic (lower priority): `AgentSuite/tau-bench-trajectories` and `tau2-bench-trajectories` (30 models each), `nebius/SWE-agent-trajectories` and `SWE-rebench-openhands-trajectories` (cc-by-4.0), `xlangai/ubuntu_osworld_verified_trajs` (500 GB), `mlfoundations/gelato-osworld-agent-trajectories`, `internlm/WildClawBench-Trajectories` (MIT), Zenodo SWE-agent trajectories `21465785` and `17364210`.

## 4. Negative findings

* No Dryad, Mendeley, OSF or Software Heritage deposit of AgentDojo-format run logs. OSF has only AgentDojo pre-registrations (nx7kv, mzndh, 3a7pz), i.e. protocols whose runs may be deposited later.
* No deposit of InjecAgent or Agent Security Bench run logs found as such. ASB outputs appear only inside Zenodo 20198985 and IEEE DataPort 10.21227/hr5g-4c33 (ten frameworks, unclear content).
* AgentDojo is archived in Software Heritage only through the `pkg.go.dev` origin, not the GitHub URL.
* Several AgentDojo-named deposits are not logs: TELOS (detector evidence, prompts redacted), AgentGuard-ZT (3 KB), Simurgh (deterministic key-free pipeline), AgentDojo Trace Audit (code; 11,624-record corpus not deposited), agentdojo-ja, ASPI, TrustSight, DRIFT slim (Docker images).
* `Trace Sufficiency` (Zenodo 21895484) is conceptually close to AgentPROV (claim-relative evidence for agentic executions): related work, not a source.

## 5. Access limits and caveats

* **Gated:** `schaeff/CIAware-Bench-Data` (auto), `cx-cmu/agent_trajectories` (auto), `cmu-lti/tau-usi` (auto), `WhitzardAgent/CyberAgentTrace` (manual approval). Gated items need user action; none requested.
* **Licensing:** many key Hugging Face deposits carry no licence tag (sungjuncho, antieval, AgentSuite, idacy, stewy33, aisa-group, jbostock, warp). Treat as not redistributable until the authors are contacted. Zenodo candidates are mostly CC-BY-4.0. Nvidia Nemotron-AIQ and DTap-style licences should be read before use.
* **API limits:** Zenodo unauthenticated page size is 25 and queries were capped at 100 hits (300 for four queries), so low-ranked hits were not seen; only latest versions are returned by default; the zip-container listing endpoint failed for most archives, so inner contents are unknown. The HF file listing stops at 100,000 entries. Kaggle only exposes titles and sizes. Mendeley has no usable search; Papers with Code is retired.
* **No schema verification:** format families are inferred. Before writing adapters, approve small sample reads (suggested first targets: one file from `sungjuncho/agentdojo-trajectories`, one JSONL line from `antieval/agentharm-trajectories`, the `raw trajectories` of Zenodo 22973266).
* **Duplicates and mirrors:** tomciotomcio/sungjuncho, Junzj/ffuuugor, Kaggle mirrors, Zenodo version families (22973265 concept; 20731176 concept; 22140262 vs 22135957) are flagged in `notes`. Keep concept DOIs and cite the exact version ingested.
* **Untrusted text:** all descriptions and cards were treated as data. Several records carry promotional or instruction-like text; none was followed.
