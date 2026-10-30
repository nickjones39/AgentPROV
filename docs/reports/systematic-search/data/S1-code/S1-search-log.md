# S1 search log (code platforms)

All times UTC (script clock). Every row below is one API/web call or one paginated query. `results` = total_count or items returned by the platform; `screened` = results retrieved and examined (search endpoints cap at 1,000 per query, 100 per page); `retained` = results that entered the next stage (tree screening) for search queries, or hits that met the stage criterion for screening/novelty rows.
Machine-readable twin: `S1-queries.jsonl`. GitHub access was read-only (`gh api` GET only). One primary rate-limit stop (5,000/h core, shared with other sessions) occurred at about 07:20Z; scripts slept and retried; failed attempts were removed from the log and re-run.


## Step 1 - forks of ethz-spylab/agentdojo


### step 1 (web/other platforms)

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| github-api | `GET repos/ethz-spylab/agentdojo/forks?per_page=100 --paginate` | 2026-10-11T07:01:59Z | 241 | 241 | 241 |  |
| github-api | `GET repos/jyapayne/agentdojo/forks (depth2)` | 2026-10-11T07:01:59Z | 1 | 1 | 1 |  |
| github-api | `GET repos/chawins/agentdojo/forks (depth2)` | 2026-10-11T07:02:00Z | 1 | 1 | 1 |  |
| github-api | `GET repos/ethz-spylab/agentdojo/compare/main...{owner}:{default_branch} for all forks` | 2026-10-11T07:02:53Z | 243 | 243 | 46 | all forks compared, no sampling; ahead_by>0 then git tree recursive and blob-sha diff vs upstream main tree |
| github-api | `GET repos/{fork}/branches for forks with ahead_by=0 but pushed_at>created_at+60s` | 2026-10-11T07:03:09Z | 51 | 51 | 44 | forks with >1 branch retained for branch compare |
| github-api | `GET repos/ethz-spylab/agentdojo/branches` | 2026-10-11T07:03:18Z | 44 | 44 | 44 |  |
| github-api | `GET repos/ethz-spylab/agentdojo/compare/main...{owner}:{branch} for non-upstream branches of forks with >1 branch` | 2026-10-11T07:03:56Z | 112 | 112 | 98 |  |
| github-api | `GET repos/{fork}/git/trees/{branch}?recursive=1 for 23 candidate fork branches; path/sha diff vs upstream main` | 2026-10-11T07:04:44Z | 23 | 23 | 23 |  |
| github-api | `git tree (recursive, split if truncated) for 4 run-bearing fork branches: agentdojo-shaped run-log counts` | 2026-10-11T07:19:45Z | 4 | 4 | 4 |  |
| web-search | `"AgentDojo" fork new suite released run logs github 2026 prompt injection benchmark extension` | 2026-10-11T07:22:25Z | 10 | 10 | 2 | AgentDyn, agentdojo-inspect (known) |

## Step 2 - dependents and mentions


### step 2 (web/other platforms)

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| github-code-search | `agentdojo filename:requirements.txt` | 2026-10-11T07:07:39Z | 80 | 78 | 62 | paged to 1, max 1000 retrievable; of retained, 15 have log-like files |
| github-code-search | `agentdojo filename:pyproject.toml` | 2026-10-11T07:08:50Z | 819 | 787 | 647 | paged to 9, max 1000 retrievable; of retained, 47 have log-like files |
| github-code-search | `agentdojo filename:setup.py` | 2026-10-11T07:08:57Z | 8 | 8 | 6 | paged to 1, max 1000 retrievable; of retained, 1 have log-like files |
| github-code-search | `agentdojo filename:environment.yml` | 2026-10-11T07:09:05Z | 6 | 6 | 5 | paged to 1, max 1000 retrievable; of retained, 3 have log-like files |
| github-code-search | `"from agentdojo" language:Python` | 2026-10-11T07:10:25Z | 9056 | 138 | 124 | paged to 10, max 1000 retrievable; of retained, 39 have log-like files |
| github-code-search | `"import agentdojo" language:Python` | 2026-10-11T07:11:50Z | 1013 | 220 | 198 | paged to 10, max 1000 retrievable; of retained, 43 have log-like files |
| github-code-search | `agentdojo filename:uv.lock` | 2026-10-11T07:11:57Z | 11 | 11 | 10 | paged to 1, max 1000 retrievable; of retained, 0 have log-like files |
| github-code-search | `agentdojo filename:requirements-dev.txt` | 2026-10-11T07:12:05Z | 0 | 0 | 962 | paged to 1, max 1000 retrievable |
| github-code-search | `agentdojo filename:Dockerfile` | 2026-10-11T07:12:12Z | 8 | 7 | 7 | paged to 1, max 1000 retrievable; of retained, 3 have log-like files |
| github-code-search | `"agentdojo" language:Markdown filename:README.md` | 2026-10-11T07:13:33Z | 1216 | 579 | 442 | paged to 10, max 1000 retrievable; of retained, 90 have log-like files |
| github-code-search | `"agentdojo" extension:ipynb` | 2026-10-11T07:13:48Z | 146 | 60 | 55 | paged to 2, max 1000 retrievable; of retained, 16 have log-like files |
| github-code-search | `"injection_task_id" "pipeline_name" extension:json` | 2026-10-11T07:15:41Z | 365568 | 37 | 37 | paged to 10, max 1000 retrievable; of retained, 36 have log-like files |
| github-graphql | `repository(owner,name) metadata batch for cs1_names.json` | 2026-10-11T07:16:29Z | 1324 | 1324 | 1324 |  |
| github-code-search | `"suite_name" "user_task_id" "injection_task_id" extension:json` | 2026-10-11T07:17:02Z | 365568 | 37 | 37 | paged to 10, max 1000 retrievable; of retained, 36 have log-like files |
| github-code-search | `"attack_type" "injections" "utility" "security" extension:json` | 2026-10-11T07:18:29Z | 342528 | 34 | 34 | paged to 10, max 1000 retrievable; of retained, 33 have log-like files |
| github-code-search | `"user_task_id" "injection_task_id" extension:jsonl` | 2026-10-11T07:19:15Z | 436 | 15 | 13 | paged to 5, max 1000 retrievable; of retained, 7 have log-like files |
| github-code-search | `"from agentdojo" language:Python size:0..600` | 2026-10-11T07:20:10Z | 628 | 56 | 52 | paged to 7, max 1000 retrievable; of retained, 21 have log-like files |
| github-code-search | `"from agentdojo" language:Python size:600..1200` | 2026-10-11T07:20:50Z | 417 | 73 | 69 | paged to 5, max 1000 retrievable; of retained, 24 have log-like files |
| github-code-search | `"from agentdojo" language:Python size:1200..2000` | 2026-10-11T07:22:09Z | 943 | 86 | 80 | paged to 10, max 1000 retrievable; of retained, 30 have log-like files |
| web-fetch | `https://github.com/ethz-spylab/agentdojo/network/dependents (dependency graph 'Used by', repositories tab, pages 1-2)` | 2026-10-11T07:22:25Z | 60 | 49 | 49 | UI shows ~60 repositories; only 49 retrievable via fetch (pagination), 28 packages listed |
| web-fetch | `https://github.com/ethz-spylab/agentdojo/network/dependents?dependent_type=PACKAGE` | 2026-10-11T07:22:25Z | 28 | 28 | 28 | package names; most parents hidden |
| github-code-search | `"from agentdojo" language:Python size:2000..3200` | 2026-10-11T07:23:27Z | 982 | 134 | 120 | paged to 10, max 1000 retrievable; of retained, 40 have log-like files |
| github-code-search | `"from agentdojo" language:Python size:3200..5000` | 2026-10-11T07:24:47Z | 1208 | 120 | 107 | paged to 10, max 1000 retrievable; of retained, 38 have log-like files |
| github-code-search | `"from agentdojo" language:Python size:5000..8000` | 2026-10-11T07:26:08Z | 1090 | 153 | 138 | paged to 10, max 1000 retrievable; of retained, 40 have log-like files |
| github-code-search | `"from agentdojo" language:Python size:8000..14000` | 2026-10-11T07:27:28Z | 1876 | 155 | 141 | paged to 10, max 1000 retrievable; of retained, 44 have log-like files |
| github-code-search | `"from agentdojo" language:Python size:14000..30000` | 2026-10-11T07:28:48Z | 1308 | 174 | 156 | paged to 10, max 1000 retrievable; of retained, 48 have log-like files |
| github-code-search | `"from agentdojo" language:Python size:30000..100000` | 2026-10-11T07:29:28Z | 484 | 118 | 111 | paged to 5, max 1000 retrievable; of retained, 41 have log-like files |
| github-code-search | `agentdojo filename:requirements.in` | 2026-10-11T07:29:36Z | 2 | 2 | 1 | paged to 1, max 1000 retrievable; of retained, 0 have log-like files |
| github-code-search | `agentdojo filename:Pipfile` | 2026-10-11T07:29:44Z | 0 | 0 | 340 | paged to 1, max 1000 retrievable |
| github-code-search | `agentdojo filename:poetry.lock` | 2026-10-11T07:29:51Z | 1 | 1 | 0 | paged to 1, max 1000 retrievable; of retained, 0 have log-like files |
| github-code-search | `"agentdojo" filename:CITATION.cff` | 2026-10-11T07:29:59Z | 6 | 6 | 6 | paged to 1, max 1000 retrievable; of retained, 0 have log-like files |
| github-code-search | `agentdojo filename:requirements.lock` | 2026-10-11T07:30:06Z | 5 | 5 | 4 | paged to 1, max 1000 retrievable; of retained, 3 have log-like files |

### 2 (repo search: name/description/topics/README)

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| github-repo-search | `agentdojo in:name` | 2026-10-11T07:07:42Z | 51 | 51 | 50 | search API max 1000 retrievable; retained set filtered later; of retained, 18 have log-like files |
| github-repo-search | `agentdojo in:description` | 2026-10-11T07:07:46Z | 64 | 64 | 63 | search API max 1000 retrievable; retained set filtered later; of retained, 12 have log-like files |
| github-repo-search | `agentdojo in:readme` | 2026-10-11T07:08:45Z | 1496 | 1000 | 344 | search API max 1000 retrievable; retained set filtered later; of retained, 88 have log-like files |
| github-repo-search | `agentdojo in:topics` | 2026-10-11T07:08:49Z | 28 | 28 | 28 | search API max 1000 retrievable; retained set filtered later; of retained, 6 have log-like files |
| github-repo-search | `topic:agentdojo` | 2026-10-11T07:08:52Z | 28 | 28 | 28 | search API max 1000 retrievable; retained set filtered later; of retained, 6 have log-like files |
| github-repo-search | `agent-dojo in:name,description,readme` | 2026-10-11T07:09:56Z | 2864 | 1000 | 21 | search API max 1000 retrievable; retained set filtered later; of retained, 6 have log-like files |
| github-repo-search | `AgentDojo benchmark in:readme` | 2026-10-11T07:10:53Z | 1153 | 1000 | 309 | search API max 1000 retrievable; retained set filtered later; of retained, 75 have log-like files |

### 2 (tree-screen named repos)

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| github-api | `GET repos/{repo}/git/trees/HEAD?recursive=1 screening (scr_2a_named.txt)` | 2026-10-11T07:12:55Z | 108 | 108 | 33 |  |

### 2 (tree-screen code-search repos, batch 1)

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| github-api | `GET repos/{repo}/git/trees/HEAD?recursive=1 screening (scr_cs1.txt)` | 2026-10-11T07:18:40Z | 1012 | 1012 | 149 |  |

### 2 (novelty vs known sources)

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| github-api | `novelty check: recursive tree blob-sha vs upstream HEAD+30 historical trees+known sources for nov1.txt` | 2026-10-11T07:59:34Z | 72 | 72 | 56 |  |

### 2 (tree-screen dependency-graph repos)

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| github-api | `GET repos/{repo}/git/trees/HEAD?recursive=1 screening (dependents_web.txt)` | 2026-10-11T07:55:55Z | 47 | 47 | 12 |  |

### 2 (GraphQL metadata, code-search batch 2)

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| github-graphql | `repository(owner,name) metadata batch for cs2_new_names.json` | 2026-10-11T07:30:24Z | 36 | 36 | 36 |  |

### 2 (tree-screen code-search repos, batch 2)

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| github-api | `GET repos/{repo}/git/trees/HEAD?recursive=1 screening (scr_cs2.txt)` | 2026-10-11T07:58:17Z | 26 | 26 | 8 |  |

### 2 (novelty, batch 2)

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| github-api | `novelty check: recursive tree blob-sha vs upstream HEAD+30 historical trees+known sources for nov2.txt` | 2026-10-11T07:59:36Z | 3 | 3 | 2 |  |

## Step 3 - other benchmarks with released runs


### step 3 (web/other platforms)

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| github-api | `git tree SWE-bench/experiments` | 2026-10-11T07:14:03Z | 1 | 1 | 1 |  |
| github-repo-search | `AgentLAB` | 2026-10-11T07:18:10Z | 325 | 8 | 8 |  |
| github-repo-search | `AgentDrift` | 2026-10-11T07:18:11Z | 11 | 8 | 8 |  |
| github-repo-search | `StepShield` | 2026-10-11T07:18:11Z | 7 | 7 | 7 |  |
| github-repo-search | `PI-Hunter` | 2026-10-11T07:18:12Z | 635 | 8 | 8 |  |
| github-repo-search | `AgentDoG` | 2026-10-11T07:18:13Z | 17 | 8 | 8 |  |
| github-repo-search | `tanqiujiang AgentLAB` | 2026-10-11T07:18:13Z | 0 | 0 | 0 |  |
| github-repo-search | `OpenAgentSafety` | 2026-10-11T07:18:14Z | 5 | 5 | 5 |  |
| github-repo-search | `Agent-SafetyBench` | 2026-10-11T07:18:15Z | 6 | 6 | 6 |  |
| github-repo-search | `TheAgentCompany` | 2026-10-11T07:18:15Z | 16 | 8 | 8 |  |
| web-search | `agent security benchmark released trajectories logs github prompt injection "trajectories" released dataset 2026` | 2026-10-11T07:22:25Z | 9 | 9 | 4 | leads: AgentDrift, ATBench, StepShield, Agent-Sentry |
| web-search | `AgentLAB benchmark long-horizon attacks LLM agents github logs` | 2026-10-11T07:22:25Z | 9 | 9 | 1 | AgentLAB = TanqiuJiang/AgentLAB (repo search); no run logs located |
| web-search | `OSWorld verified leaderboard submission trajectories results download agent run logs` | 2026-10-11T07:22:25Z | 9 | 9 | 0 | no official trajectory download located |
| web-search | `AgentHarm inspect_evals evaluation logs released .eval files trajectories huggingface` | 2026-10-11T07:22:25Z | 9 | 9 | 0 | no official .eval release located (note: survey repo contains AgentHarm .eval, known) |
| web-search | `InjecAgent ASB Agent Security Bench WASP released agent trajectories raw logs per-run outputs github release` | 2026-10-11T07:22:25Z | 9 | 9 | 1 | InjecAgent README claims model outputs released (aggregate-level; unverified) |

### 3 (topic / description repo searches)

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| github-repo-search | `topic:agent-security` | 2026-10-11T07:12:00Z | 1822 | 1000 | 271 | search API max 1000 retrievable; retained set filtered later; of retained, 18 have log-like files |
| github-repo-search | `topic:prompt-injection topic:benchmark` | 2026-10-11T07:12:11Z | 169 | 169 | 66 | search API max 1000 retrievable; retained set filtered later; of retained, 15 have log-like files |
| github-repo-search | `topic:agent-benchmark` | 2026-10-11T07:12:17Z | 94 | 94 | 39 | search API max 1000 retrievable; retained set filtered later; of retained, 3 have log-like files |
| github-repo-search | `topic:llm-agent topic:benchmark` | 2026-10-11T07:12:21Z | 53 | 53 | 26 | search API max 1000 retrievable; retained set filtered later; of retained, 1 have log-like files |
| github-repo-search | `topic:inspect-ai` | 2026-10-11T07:12:31Z | 107 | 107 | 35 | search API max 1000 retrievable; retained set filtered later; of retained, 12 have log-like files |
| github-repo-search | `prompt injection benchmark agent trajectories in:readme` | 2026-10-11T07:13:28Z | 4152 | 1000 | 82 | search API max 1000 retrievable; retained set filtered later; of retained, 6 have log-like files |
| github-repo-search | `llm agent benchmark released trajectories in:readme` | 2026-10-11T07:14:26Z | 6260 | 1000 | 132 | search API max 1000 retrievable; retained set filtered later; of retained, 9 have log-like files |
| github-repo-search | `agent security benchmark in:description` | 2026-10-11T07:14:42Z | 225 | 225 | 75 | search API max 1000 retrievable; retained set filtered later; of retained, 4 have log-like files |
| github-repo-search | `agent safety benchmark in:description` | 2026-10-11T07:14:53Z | 190 | 190 | 67 | search API max 1000 retrievable; retained set filtered later; of retained, 9 have log-like files |
| github-repo-search | `indirect prompt injection tool-using agents benchmark in:description` | 2026-10-11T07:14:56Z | 3 | 3 | 0 | search API max 1000 retrievable; retained set filtered later; of retained, 0 have log-like files |
| github-repo-search | `agent trajectories logs dataset in:description` | 2026-10-11T07:14:59Z | 2 | 2 | 0 | search API max 1000 retrievable; retained set filtered later; of retained, 0 have log-like files |
| github-repo-search | `inspect_ai eval logs agent in:readme` | 2026-10-11T07:15:49Z | 850 | 799 | 76 | search API max 1000 retrievable; retained set filtered later; of retained, 27 have log-like files |
| github-repo-search | `tool-calling agent benchmark runs logs in:readme` | 2026-10-11T07:16:47Z | 6832 | 1000 | 62 | search API max 1000 retrievable; retained set filtered later; of retained, 8 have log-like files |

### 3 (benchmark-name repo searches)

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| github-repo-search | `injecagent` | 2026-10-11T07:11:04Z | 10 | 10 | 10 | search API max 1000 retrievable; retained set filtered later; of retained, 0 have log-like files |
| github-repo-search | `agentharm` | 2026-10-11T07:11:08Z | 14 | 14 | 4 | search API max 1000 retrievable; retained set filtered later; of retained, 3 have log-like files |
| github-repo-search | `agent security bench ASB` | 2026-10-11T07:11:11Z | 4 | 4 | 3 | search API max 1000 retrievable; retained set filtered later; of retained, 0 have log-like files |
| github-repo-search | `wasp web agent security` | 2026-10-11T07:11:14Z | 1 | 1 | 1 | search API max 1000 retrievable; retained set filtered later; of retained, 0 have log-like files |
| github-repo-search | `agentpoison` | 2026-10-11T07:11:18Z | 12 | 12 | 5 | search API max 1000 retrievable; retained set filtered later; of retained, 0 have log-like files |
| github-repo-search | `toolemu` | 2026-10-11T07:11:21Z | 5 | 5 | 4 | search API max 1000 retrievable; retained set filtered later; of retained, 0 have log-like files |
| github-repo-search | `r-judge agent safety` | 2026-10-11T07:11:24Z | 2 | 2 | 1 | search API max 1000 retrievable; retained set filtered later; of retained, 0 have log-like files |
| github-repo-search | `safearena` | 2026-10-11T07:11:27Z | 3 | 3 | 3 | search API max 1000 retrievable; retained set filtered later; of retained, 0 have log-like files |
| github-repo-search | `st-webagentbench` | 2026-10-11T07:11:30Z | 2 | 2 | 2 | search API max 1000 retrievable; retained set filtered later; of retained, 0 have log-like files |
| github-repo-search | `browserart` | 2026-10-11T07:11:34Z | 6 | 6 | 2 | search API max 1000 retrievable; retained set filtered later; of retained, 0 have log-like files |
| github-repo-search | `doomarena` | 2026-10-11T07:11:37Z | 6 | 6 | 4 | search API max 1000 retrievable; retained set filtered later; of retained, 0 have log-like files |
| github-repo-search | `agentdam` | 2026-10-11T07:11:40Z | 2 | 2 | 1 | search API max 1000 retrievable; retained set filtered later; of retained, 1 have log-like files |
| github-repo-search | `tau-bench` | 2026-10-11T07:11:56Z | 216 | 216 | 8 | search API max 1000 retrievable; retained set filtered later; of retained, 1 have log-like files |
| github-repo-search | `appworld` | 2026-10-11T07:12:09Z | 159 | 159 | 7 | search API max 1000 retrievable; retained set filtered later; of retained, 0 have log-like files |
| github-repo-search | `osworld` | 2026-10-11T07:12:26Z | 215 | 215 | 10 | search API max 1000 retrievable; retained set filtered later; of retained, 0 have log-like files |
| github-repo-search | `swe-bench experiments` | 2026-10-11T07:12:30Z | 24 | 24 | 4 | search API max 1000 retrievable; retained set filtered later; of retained, 1 have log-like files |
| github-repo-search | `webarena` | 2026-10-11T07:12:43Z | 198 | 198 | 7 | search API max 1000 retrievable; retained set filtered later; of retained, 0 have log-like files |
| github-repo-search | `agentbench` | 2026-10-11T07:13:00Z | 244 | 244 | 8 | search API max 1000 retrievable; retained set filtered later; of retained, 2 have log-like files |
| github-repo-search | `gaia benchmark` | 2026-10-11T07:13:11Z | 169 | 169 | 4 | search API max 1000 retrievable; retained set filtered later; of retained, 0 have log-like files |
| github-repo-search | `inspect_evals` | 2026-10-11T07:13:21Z | 108 | 108 | 9 | search API max 1000 retrievable; retained set filtered later; of retained, 2 have log-like files |
| github-repo-search | `metr task` | 2026-10-11T07:14:14Z | 704 | 704 | 4 | search API max 1000 retrievable; retained set filtered later; of retained, 0 have log-like files |
| github-repo-search | `cybench` | 2026-10-11T07:14:18Z | 45 | 45 | 7 | search API max 1000 retrievable; retained set filtered later; of retained, 1 have log-like files |

### 3 (tree-screen named benchmark repos)

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| github-api | `GET repos/{repo}/git/trees/HEAD?recursive=1 screening (b.txt)` | 2026-10-11T07:13:06Z | 58 | 58 | 11 |  |

### 3 (tree-screen additional benchmark repos)

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| github-api | `GET repos/{repo}/git/trees/HEAD?recursive=1 screening (b2.txt)` | 2026-10-11T07:18:22Z | 7 | 7 | 0 |  |

### 3 (tree-screen generic-search repos)

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| github-api | `GET repos/{repo}/git/trees/HEAD?recursive=1 screening (scr_3e.txt)` | 2026-10-11T07:58:09Z | 766 | 766 | 151 |  |

### 3 (GraphQL metadata)

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| github-graphql | `repository(owner,name) metadata batch for cur_names.json` | 2026-10-11T07:26:02Z | 115 | 105 | 105 |  |

## Step 4 - Hugging Face, GitLab, Codeberg, Zenodo


### step 4 (web/other platforms)

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| huggingface-api | `https://huggingface.co/api/datasets?search=agentdojo&limit=100` | 2026-10-11T07:09:45Z | 9 | 9 | 9 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=agent%20dojo&limit=100` | 2026-10-11T07:09:45Z | 9 | 9 | 9 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=prompt%20injection%20agent&limit=100` | 2026-10-11T07:09:46Z | 10 | 10 | 10 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=injecagent&limit=100` | 2026-10-11T07:09:46Z | 1 | 1 | 1 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=agentharm&limit=100` | 2026-10-11T07:09:46Z | 10 | 10 | 10 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=agent%20security%20bench&limit=100` | 2026-10-11T07:09:47Z | 3 | 3 | 3 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=agent%20trajectories&limit=100` | 2026-10-11T07:09:47Z | 56 | 56 | 56 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=agent%20trajectory&limit=100` | 2026-10-11T07:09:47Z | 40 | 40 | 40 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=tool%20use%20trajectories&limit=100` | 2026-10-11T07:09:48Z | 8 | 8 | 8 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=tau-bench&limit=100` | 2026-10-11T07:09:48Z | 68 | 68 | 68 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=tau2&limit=100` | 2026-10-11T07:09:48Z | 100 | 100 | 100 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=appworld&limit=100` | 2026-10-11T07:09:49Z | 100 | 100 | 100 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=osworld&limit=100` | 2026-10-11T07:09:49Z | 100 | 100 | 100 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=webarena&limit=100` | 2026-10-11T07:09:49Z | 32 | 32 | 32 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=swe-bench%20trajectories&limit=100` | 2026-10-11T07:09:50Z | 7 | 7 | 7 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=agentbench&limit=100` | 2026-10-11T07:09:50Z | 36 | 36 | 36 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=gaia&limit=100` | 2026-10-11T07:09:50Z | 100 | 100 | 100 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=cybench&limit=100` | 2026-10-11T07:09:51Z | 13 | 13 | 13 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=wasp&limit=100` | 2026-10-11T07:09:51Z | 12 | 12 | 12 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=agentdyn&limit=100` | 2026-10-11T07:09:51Z | 1 | 1 | 1 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=browsergym&limit=100` | 2026-10-11T07:09:51Z | 1 | 1 | 1 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=prompt-injection%20benchmark&limit=100` | 2026-10-11T07:09:52Z | 3 | 3 | 3 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=safearena&limit=100` | 2026-10-11T07:09:52Z | 1 | 1 | 1 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=agent-safety&limit=100` | 2026-10-11T07:09:52Z | 13 | 13 | 13 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=toolemu&limit=100` | 2026-10-11T07:09:52Z | 0 | 0 | 0 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=r-judge&limit=100` | 2026-10-11T07:09:53Z | 7 | 7 | 7 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=doomarena&limit=100` | 2026-10-11T07:09:53Z | 0 | 0 | 0 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=agentdam&limit=100` | 2026-10-11T07:09:53Z | 1 | 1 | 1 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=st-webagentbench&limit=100` | 2026-10-11T07:09:54Z | 3 | 3 | 3 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=agentpoison&limit=100` | 2026-10-11T07:09:54Z | 0 | 0 | 0 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=inspect%20eval%20logs&limit=100` | 2026-10-11T07:09:54Z | 0 | 0 | 0 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=agent%20logs&limit=100` | 2026-10-11T07:09:54Z | 10 | 10 | 10 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=swe-agent%20trajectories&limit=100` | 2026-10-11T07:09:55Z | 14 | 14 | 14 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=openhands%20trajectories&limit=100` | 2026-10-11T07:09:55Z | 17 | 17 | 17 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=terminal-bench&limit=100` | 2026-10-11T07:09:55Z | 100 | 100 | 100 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=nemotron%20agentic&limit=100` | 2026-10-11T07:09:56Z | 56 | 56 | 56 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets?search=agent%20red%20teaming&limit=100` | 2026-10-11T07:09:56Z | 0 | 0 | 0 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/spaces?search=agentdojo&limit=100` | 2026-10-11T07:09:56Z | 0 | 0 | 0 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/spaces?search=prompt%20injection%20agent&limit=100` | 2026-10-11T07:09:56Z | 1 | 1 | 1 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/spaces?search=agentharm&limit=100` | 2026-10-11T07:09:57Z | 0 | 0 | 0 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/spaces?search=agent%20security%20bench&limit=100` | 2026-10-11T07:09:57Z | 0 | 0 | 0 | limit=100 cap |
| huggingface-api | `https://huggingface.co/api/datasets/Genteki/agentdojo_tiny` | 2026-10-11T07:10:12Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/ffuuugor/agentdojo-dump` | 2026-10-11T07:10:12Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/Junzj/agentdojo-dump` | 2026-10-11T07:10:13Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/adityaasinha28/control_arena_agentdojo` | 2026-10-11T07:10:13Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/sungjuncho/agentdojo-trajectories` | 2026-10-11T07:10:14Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/aksh-n/control_arena_agentdojo-monitor-labels` | 2026-10-11T07:10:15Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/Jinming2002/drift-agentdojo-slim` | 2026-10-11T07:10:15Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/tomciotomcio/agentdojo-trajectories` | 2026-10-11T07:10:16Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/tuandunghcmut/trustsight-agentdojo` | 2026-10-11T07:10:16Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/tuandunghcmut/trustsight-wasp` | 2026-10-11T07:10:17Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/agentdyn-dataset/agentdyn` | 2026-10-11T07:10:17Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/antieval/agentharm-trajectories` | 2026-10-11T07:10:17Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/antieval/swebench-trajectories` | 2026-10-11T07:10:18Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/antieval/cybench-trajectories` | 2026-10-11T07:10:18Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/Z-Edgar/Indirect-Prompt-Injection-in-Agent-Structured-Interaction-Datasets` | 2026-10-11T07:10:18Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/nvidia/Nemotron-RL-Agentic-Indirect-Prompt-Injection-v1` | 2026-10-11T07:10:18Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/open-athena/glm52-datagen-r11-101-agentic-indirect-prompt-injection-v2-traces` | 2026-10-11T07:10:19Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/ai-safety-institute/AgentHarm` | 2026-10-11T07:10:19Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/thu-coai/Agent-SafetyBench` | 2026-10-11T07:10:19Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/McGill-NLP/safearena` | 2026-10-11T07:10:19Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/ST-WebAgentBench/st-webagentbench` | 2026-10-11T07:10:20Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/webarena-x/webarena-infinity-trajectories` | 2026-10-11T07:10:21Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/AmineHA/Webarena-Verified-Submissions` | 2026-10-11T07:10:21Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/OpenHandsCommunity/eval-output-webarena` | 2026-10-11T07:10:21Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/JetBrains-Research/agent-trajectories-swe-bench-test-minus-verified` | 2026-10-11T07:10:22Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/nebius/SWE-agent-trajectories` | 2026-10-11T07:10:22Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/lvogel123/cybench-results` | 2026-10-11T07:10:22Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/lvogel123/cybench-all` | 2026-10-11T07:10:23Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/masahiroid/injecagent-ja` | 2026-10-11T07:10:23Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/Lakera/b3-agent-security-benchmark-weak` | 2026-10-11T07:10:23Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/zachz/prompt-injection-benchmark` | 2026-10-11T07:10:24Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/Toprak1yu/agent-tool-use-trajectories` | 2026-10-11T07:10:24Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/3nesdeniz/agentic-prompt-injection-5k` | 2026-10-11T07:10:24Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/3nesdeniz/agentic-prompt-injection-boundary-pairs` | 2026-10-11T07:10:24Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/schaeff/CIAware-Bench-Data` | 2026-10-11T07:10:26Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/webarenapro/agent_trajectory_reviews` | 2026-10-11T07:10:26Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/karanxa/agent-action-safety-dataset` | 2026-10-11T07:10:26Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/aradhye/agent-safety-bench` | 2026-10-11T07:10:27Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| gitlab-api | `https://gitlab.com/api/v4/projects?search=agentdojo&per_page=100&simple=true&order_by=last_activity_at` | 2026-10-11T07:11:19Z | 1 | 1 | 1 |  |
| codeberg-api | `https://codeberg.org/api/v1/repos/search?q=agentdojo&limit=50` | 2026-10-11T07:11:28Z | 0 | 0 | 0 |  |
| gitlab-api | `https://gitlab.com/api/v4/projects?search=agent-dojo&per_page=100&simple=true&order_by=last_activity_at` | 2026-10-11T07:11:28Z | 0 | 0 | 0 |  |
| codeberg-api | `https://codeberg.org/api/v1/repos/search?q=agent-dojo&limit=50` | 2026-10-11T07:11:36Z | 0 | 0 | 0 |  |
| gitlab-api | `https://gitlab.com/api/v4/projects?search=agentharm&per_page=100&simple=true&order_by=last_activity_at` | 2026-10-11T07:11:37Z | 0 | 0 | 0 |  |
| codeberg-api | `https://codeberg.org/api/v1/repos/search?q=agentharm&limit=50` | 2026-10-11T07:11:43Z | 0 | 0 | 0 |  |
| gitlab-api | `https://gitlab.com/api/v4/projects?search=injecagent&per_page=100&simple=true&order_by=last_activity_at` | 2026-10-11T07:11:44Z | 0 | 0 | 0 |  |
| codeberg-api | `https://codeberg.org/api/v1/repos/search?q=injecagent&limit=50` | 2026-10-11T07:11:52Z | 0 | 0 | 0 |  |
| gitlab-api | `https://gitlab.com/api/v4/projects?search=prompt%20injection%20benchmark%20agent&per_page=100&simple=true&order_by=last_activity_at` | 2026-10-11T07:11:54Z | 0 | 0 | 0 |  |
| codeberg-api | `https://codeberg.org/api/v1/repos/search?q=prompt%20injection%20benchmark%20agent&limit=50` | 2026-10-11T07:12:02Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=AgentDrift&limit=30` | 2026-10-11T07:17:58Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=StepShield&limit=30` | 2026-10-11T07:17:58Z | 1 | 1 | 1 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=ATBench&limit=30` | 2026-10-11T07:17:58Z | 6 | 6 | 6 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=PI-Hunter&limit=30` | 2026-10-11T07:17:59Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=AgentLAB&limit=30` | 2026-10-11T07:17:59Z | 1 | 1 | 1 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=OpenAgentSafety&limit=30` | 2026-10-11T07:17:59Z | 16 | 16 | 16 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=agentdoG&limit=30` | 2026-10-11T07:17:59Z | 2 | 2 | 2 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=AgentDyn&limit=30` | 2026-10-11T07:18:00Z | 1 | 1 | 1 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=tau2&limit=30` | 2026-10-11T07:18:00Z | 30 | 30 | 30 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=MCPSecBench&limit=30` | 2026-10-11T07:18:00Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=AgentSentry&limit=30` | 2026-10-11T07:18:00Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=control_arena&limit=30` | 2026-10-11T07:18:01Z | 30 | 30 | 30 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=ControlArena&limit=30` | 2026-10-11T07:18:01Z | 27 | 27 | 27 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=SHADE-Arena&limit=30` | 2026-10-11T07:18:01Z | 6 | 6 | 6 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=inspect_ai%20logs&limit=30` | 2026-10-11T07:18:01Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets/AI45Research/ATBench` | 2026-10-11T07:21:20Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/idacy/control-arena-runs` | 2026-10-11T07:21:21Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/sani903/openagentsafety` | 2026-10-11T07:21:21Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/agentlabtraces/agentlabtraces` | 2026-10-11T07:21:21Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/MichaelEniolade/stepshield` | 2026-10-11T07:21:22Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/HuggingFaceH4/tau2-bench-data` | 2026-10-11T07:21:22Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/redwoodresearch/basharena_public` | 2026-10-11T07:21:22Z | 0 | 1 | 0 | not found/error HTTP Error 401: Unauthorized |
| huggingface-api | `https://huggingface.co/api/datasets/UKGovernmentBEIS/inspect_evals` | 2026-10-11T07:21:22Z | 0 | 1 | 0 | not found/error HTTP Error 401: Unauthorized |
| huggingface-api | `https://huggingface.co/api/datasets/hf-internal-testing/agentdojo` | 2026-10-11T07:21:23Z | 0 | 1 | 0 | not found/error HTTP Error 401: Unauthorized |
| huggingface-api | `https://huggingface.co/api/datasets/ethz-spylab/agentdojo` | 2026-10-11T07:21:23Z | 0 | 1 | 0 | not found/error HTTP Error 401: Unauthorized |
| huggingface-api | `https://huggingface.co/api/datasets/gaia-benchmark/GAIA` | 2026-10-11T07:21:23Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/princeton-nlp/SWE-bench` | 2026-10-11T07:21:24Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/SWE-bench/SWE-smith-trajectories` | 2026-10-11T07:21:25Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/TheAgentCompany/trajectories` | 2026-10-11T07:21:25Z | 0 | 1 | 0 | not found/error HTTP Error 401: Unauthorized |
| huggingface-api | `https://huggingface.co/api/datasets/xlang-ai/OSWorld` | 2026-10-11T07:21:25Z | 0 | 1 | 0 | not found/error HTTP Error 401: Unauthorized |
| huggingface-api | `https://huggingface.co/api/datasets/ucsc-vlaa/AgentSafetyBench` | 2026-10-11T07:21:25Z | 0 | 1 | 0 | not found/error HTTP Error 401: Unauthorized |
| huggingface-api | `https://huggingface.co/api/datasets/jplhughes/agentharm-logs` | 2026-10-11T07:21:26Z | 0 | 1 | 0 | not found/error HTTP Error 401: Unauthorized |
| huggingface-api | `https://huggingface.co/api/datasets/AgentSafetyBench/Agent-SafetyBench` | 2026-10-11T07:21:26Z | 0 | 1 | 0 | not found/error HTTP Error 401: Unauthorized |
| huggingface-api | `https://huggingface.co/api/datasets/Hugging-Face-Aegis/agent-runs` | 2026-10-11T07:21:26Z | 0 | 1 | 0 | not found/error HTTP Error 401: Unauthorized |
| huggingface-api | `https://huggingface.co/api/datasets/METR/vivaria-runs` | 2026-10-11T07:21:26Z | 0 | 1 | 0 | not found/error HTTP Error 401: Unauthorized |
| huggingface-api | `https://huggingface.co/api/datasets/METR/hcast-public-runs` | 2026-10-11T07:21:27Z | 0 | 1 | 0 | not found/error HTTP Error 401: Unauthorized |
| huggingface-api | `https://huggingface.co/api/datasets/AgentRewardBench/AgentRewardBench` | 2026-10-11T07:21:27Z | 0 | 1 | 0 | not found/error HTTP Error 401: Unauthorized |
| huggingface-api | `https://huggingface.co/api/datasets/McGill-NLP/agent-reward-bench` | 2026-10-11T07:21:29Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/nvidia/Nemotron-Agentic-v1` | 2026-10-11T07:21:29Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/open-athena/nemotron-gym-agentic-indirect-prompt-injection` | 2026-10-11T07:21:29Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/ScaleAI/mrt` | 2026-10-11T07:21:31Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/adityaasinha28/control_arena_shade` | 2026-10-11T07:21:31Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/inspect-ai/logs` | 2026-10-11T07:21:33Z | 0 | 1 | 0 | not found/error HTTP Error 401: Unauthorized |
| huggingface-api | `https://huggingface.co/api/datasets/Genteki/agentharm_tiny` | 2026-10-11T07:21:33Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| web-search | `agentdojo gitlab.com repository fork prompt injection benchmark agent` | 2026-10-11T07:22:25Z | 9 | 9 | 1 | no GitLab copy found |
| web-search | `codeberg.org agentdojo prompt injection agent benchmark` | 2026-10-11T07:22:25Z | 9 | 9 | 0 | no Codeberg repo found |
| web-search | `AgentDojo released run logs trajectories dataset Hugging Face prompt injection agent traces` | 2026-10-11T07:22:25Z | 9 | 9 | 1 |  |
| zenodo-api | `https://zenodo.org/api/records?q=agentdojo&size=25` | 2026-10-11T07:22:58Z | 50 | 25 | 25 |  |
| zenodo-api | `https://zenodo.org/api/records?q=AgentDojo%20trajectories&size=25` | 2026-10-11T07:23:00Z | 21877 | 25 | 25 |  |
| zenodo-api | `https://zenodo.org/api/records?q=prompt%20injection%20agent%20benchmark%20logs&size=25` | 2026-10-11T07:23:02Z | 120029 | 25 | 25 |  |
| zenodo-api | `https://zenodo.org/api/records?q=agent%20trajectories%20prompt%20injection&size=25` | 2026-10-11T07:23:05Z | 87974 | 25 | 25 |  |
| zenodo-api | `https://zenodo.org/api/records?q=agentdojo&size=25&page=1` | 2026-10-11T07:23:15Z | 50 | 25 | 25 |  |
| zenodo-api | `https://zenodo.org/api/records?q=agentdojo&size=25&page=2` | 2026-10-11T07:23:17Z | 50 | 25 | 25 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=injection_task&limit=100` | 2026-10-11T07:34:53Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=user_task%20banking%20slack%20travel%20workspace&limit=100` | 2026-10-11T07:34:53Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=agent%20hijacking&limit=100` | 2026-10-11T07:34:54Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=indirect%20prompt%20injection%20trajectories&limit=100` | 2026-10-11T07:34:54Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=tool-calling%20attack&limit=100` | 2026-10-11T07:34:54Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=ipi%20agent&limit=100` | 2026-10-11T07:34:54Z | 3 | 3 | 3 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=agentdojo-style&limit=100` | 2026-10-11T07:34:55Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=important_instructions&limit=100` | 2026-10-11T07:34:55Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=meta%20secalign&limit=100` | 2026-10-11T07:34:55Z | 1 | 1 | 1 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=camel%20prompt%20injection&limit=100` | 2026-10-11T07:34:56Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=melon&limit=100` | 2026-10-11T07:34:56Z | 48 | 48 | 48 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=agent%20defense%20benchmark&limit=100` | 2026-10-11T07:34:56Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=mcp%20security%20benchmark&limit=100` | 2026-10-11T07:34:56Z | 2 | 2 | 2 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=agent%20red%20team%20trajectories&limit=100` | 2026-10-11T07:34:57Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=control%20arena&limit=100` | 2026-10-11T07:34:57Z | 33 | 33 | 33 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=shade%20arena&limit=100` | 2026-10-11T07:34:57Z | 6 | 6 | 6 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=openagentsafety&limit=100` | 2026-10-11T07:34:57Z | 16 | 16 | 16 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=agent%20safety%20trajectories&limit=100` | 2026-10-11T07:34:58Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=jailbreak%20agent%20trajectories&limit=100` | 2026-10-11T07:34:58Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets?search=web%20agent%20prompt%20injection&limit=100` | 2026-10-11T07:34:58Z | 0 | 0 | 0 |  |
| huggingface-api | `https://huggingface.co/api/datasets/Z-Edgar/Agent-IPI-Structured-Interaction-Datasets` | 2026-10-11T07:35:04Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/Z-Edgar/Agent-IPI-Structured-Interaction-Datasets-v2` | 2026-10-11T07:35:05Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/idacy/control-arena-injection-dataset` | 2026-10-11T07:35:05Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/CieveHe/mcp-security-benchmark` | 2026-10-11T07:35:05Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |
| huggingface-api | `https://huggingface.co/api/datasets/idacy/control-arena-persistent-state-eval-archive-2026-07-30` | 2026-10-11T07:35:06Z | 1 | 1 | 1 | dataset metadata (siblings list), no file download |

## 5


### step 5

| platform | query / endpoint | time (UTC) | results | screened | retained | note |
|---|---|---|---|---|---|---|
| github-graphql | `repository{licenseInfo; LICENSE/LICENSE.md/LICENSE.txt/COPYING blobs; README.md text} batches of 12 for licence determination` | 2026-10-11T08:02:13Z | 222 | 222 | 222 | licence audit requested by coordinator; classification rule in lic.py |
| huggingface-api | `GET /api/datasets/{id} cardData.license + README/LICENSE sibling check` | 2026-10-11T08:02:13Z | 17 | 17 | 17 | licence audit |
