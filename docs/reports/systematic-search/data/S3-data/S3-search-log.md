# S3 search log: research data repositories (part 3 of 3)

Run date: 2026-10-11, 07:01 to ~07:50 UTC. Searcher: Claude Code subagent. All calls were read-only metadata/API/search calls. **No dataset or archive was downloaded**; no data file was opened. Web/API content was treated as untrusted data.

## 0. Protocol, tools and caveats

* Tools: `curl`/`urllib` against public REST APIs (Zenodo, Hugging Face Hub, DataCite, Figshare, OSF, Dryad, Software Heritage, Kaggle public list endpoint). Scripts live in the session scratchpad only (not in the repo).
* Zenodo unauthenticated API caps `size` at 25 per page. The first batch was launched with `size=100` and returned HTTP 400 for every query between 07:01 and 07:10 UTC (7 queries logged as ERROR, 0 records); that run was killed, outputs discarded, and all queries were re-run from 07:13 UTC with `size=25` and up to 4 pages (cap 100 hits per query; cap 300 for the four q3 queries). Where a query total exceeds the cap, only the first 100 (or 300) best-match hits were retrieved; this is stated per query below.
* Zenodo returns only the latest version of each concept by default (`all_versions` off). Version DOIs were enumerated with `all_versions=true` only for concept 12528188 (AgentDojo) and 20692312 (AgentDojo-PROV).
* Free-text Zenodo queries without explicit boolean operators use OR semantics (e.g. `agent trajectories` -> 61,729 hits), so the first-batch bare queries are near-useless for recall; precision queries with `AND`, quoted phrases and parenthesised ORs (q2/q3) were used for screening. The unquoted queries are recorded for completeness.
* Zenodo zip-container listing (`/api/records/<id>/files/<key>/container`) is a server-side metadata listing, not a download; it failed (HTTP 500/404/timeouts) for most zips, so inner contents are known only for some records. HF `first-rows` (datasets-server) was called for four AgentDojo-related datasets (metadata only).
* Screening is two-stage and was done on the *pooled, de-duplicated* result set of each repository, not per query: (1) regex/keyword filter over title+description+file names, then (2) manual reading of the retained list and of full record metadata for ~70 Zenodo and ~130 Hugging Face records. "Screened" and "retained" are therefore reported per repository in section 8, not per query.
* Because no file was opened, every `format_family` entry is an inference from file names, directory layout, dataset cards or API schema. Entries marked "unverified" must be confirmed by a small, user-approved sample read before an adapter is written.

## 1. Zenodo REST API (`https://zenodo.org/api/records?q=<query>&size=25&page=N`)

### 1a. Batch 1 (bare / lightly quoted queries; OR semantics, cap 100 per query)

| UTC time | Query | Result |
|---|---|---|
| 2026-10-11 07:13:18Z | `agentdojo` | total=50 fetched=50 |
| 2026-10-11 07:13:27Z | `"prompt injection" agent` | total=41266 fetched=100 |
| 2026-10-11 07:13:44Z | `agent trajectories` | total=61729 fetched=100 |
| 2026-10-11 07:14:00Z | `LLM agent logs` | total=71661 fetched=100 |
| 2026-10-11 07:14:15Z | `agent benchmark runs` | total=105854 fetched=100 |
| 2026-10-11 07:14:31Z | `"tool use" agent benchmark` | total=82983 fetched=100 |
| 2026-10-11 07:14:46Z | `inspect_ai` | total=4 fetched=4 |
| 2026-10-11 07:14:48Z | `".eval" inspect` | total=3458 fetched=100 |
| 2026-10-11 07:15:03Z | `agent security benchmark` | total=181494 fetched=100 |
| 2026-10-11 07:15:19Z | `"indirect prompt injection"` | total=165 fetched=100 |
| 2026-10-11 07:15:33Z | `InjecAgent` | total=17 fetched=17 |
| 2026-10-11 07:15:36Z | `AgentHarm` | total=9 fetched=9 |
| 2026-10-11 07:15:39Z | `"Agent Security Bench"` | total=5 fetched=5 |
| 2026-10-11 07:15:42Z | `tau-bench` | total=5840 fetched=100 |
| 2026-10-11 07:15:58Z | `SWE-bench trajectories` | total=25366 fetched=100 |
| 2026-10-11 07:16:13Z | `WebArena trajectories` | total=21849 fetched=100 |
| 2026-10-11 07:16:30Z | `OSWorld` | total=12 fetched=12 |
| 2026-10-11 07:16:34Z | `AppWorld` | total=4 fetched=4 |
| 2026-10-11 07:16:38Z | `GAIA benchmark agent` | total=87238 fetched=100 |
| 2026-10-11 07:16:55Z | `agent execution traces` | total=90577 fetched=100 |
| 2026-10-11 07:17:12Z | `LLM agent execution logs dataset` | total=387068 fetched=100 |
| 2026-10-11 07:17:30Z | `tool-calling agent trajectories dataset` | total=392260 fetched=100 |

### 1b. Batch 2 (boolean precision queries, cap 100 per query; none reached the cap)

| UTC time | Query | Result |
|---|---|---|
| 2026-10-11 07:18:20Z | `"prompt injection" AND agent AND (trajectories OR logs OR traces OR runs)` | total=92 fetched=92 |
| 2026-10-11 07:18:38Z | `"prompt injection" AND (benchmark OR AgentDojo OR InjecAgent) AND (dataset OR logs)` | total=41 fetched=41 |
| 2026-10-11 07:18:46Z | `"LLM agent" AND (trajectories OR "execution traces" OR "execution logs")` | total=31 fetched=31 |
| 2026-10-11 07:18:55Z | `"LLM agents" AND trajectories AND dataset` | total=10 fetched=10 |
| 2026-10-11 07:18:58Z | `"agent trajectories"` | total=46 fetched=46 |
| 2026-10-11 07:19:05Z | `"agent trajectory" AND LLM` | total=3 fetched=3 |
| 2026-10-11 07:19:08Z | `"tool-calling" AND agent AND (logs OR trajectories OR traces)` | total=12 fetched=12 |
| 2026-10-11 07:19:12Z | `"tool use" AND LLM AND (trajectories OR logs) AND benchmark` | total=5 fetched=5 |
| 2026-10-11 07:19:14Z | `"agentic" AND benchmark AND (logs OR transcripts OR trajectories)` | total=88 fetched=88 |
| 2026-10-11 07:19:33Z | `"inspect_ai" OR "inspect-ai" OR "Inspect AI"` | total=11 fetched=11 |
| 2026-10-11 07:19:36Z | `"UK AISI" OR "AI Security Institute" AND agent` | total=22 fetched=22 |
| 2026-10-11 07:19:47Z | `"agent security" AND benchmark` | total=51 fetched=51 |
| 2026-10-11 07:19:58Z | `"tool injection" OR "tool poisoning" AND LLM` | total=20 fetched=20 |
| 2026-10-11 07:20:02Z | `"InjecAgent" OR "AgentHarm" OR "AgentDojo" OR "AgentDyn" OR "AutoDojo"` | total=69 fetched=69 |
| 2026-10-11 07:20:15Z | `"Agent Security Bench" OR "ASB" AND LLM agent injection` | total=6 fetched=6 |
| 2026-10-11 07:20:19Z | `"tau-bench" OR "τ-bench" OR "tau2-bench"` | total=31 fetched=31 |
| 2026-10-11 07:20:28Z | `"SWE-bench" AND (trajectories OR logs)` | total=39 fetched=39 |
| 2026-10-11 07:20:36Z | `"WebArena" AND (trajectories OR logs)` | total=2 fetched=2 |
| 2026-10-11 07:20:39Z | `"OSWorld" OR "AppWorld" OR "WorkArena" OR "VisualWebArena"` | total=17 fetched=17 |
| 2026-10-11 07:20:43Z | `"GAIA" AND agent AND (logs OR traces OR trajectories)` | total=13 fetched=13 |
| 2026-10-11 07:20:47Z | `"agent" AND "transcripts" AND LLM AND (benchmark OR evaluation)` | total=29 fetched=29 |
| 2026-10-11 07:21:01Z | `"jailbreak" AND agent AND (trajectories OR logs) AND dataset` | total=5 fetched=5 |
| 2026-10-11 07:21:05Z | `"red teaming" AND agent AND (logs OR transcripts) AND dataset` | total=0 fetched=0 |
| 2026-10-11 07:21:08Z | `"provenance" AND "LLM agent"` | total=41 fetched=41 |
| 2026-10-11 07:21:16Z | `"W3C PROV" AND agent AND LLM` | total=4 fetched=4 |
| 2026-10-11 07:21:21Z | `"AgentBench" OR "ToolEmu" OR "R-Judge" OR "AgentDojo-PROV"` | total=37 fetched=37 |
| 2026-10-11 07:21:31Z | `"MCP" AND ("tool poisoning" OR injection) AND (benchmark OR dataset)` | total=43 fetched=43 |
| 2026-10-11 07:21:56Z | `"OpenHands" OR "SWE-agent" AND trajectories` | total=14 fetched=14 |
| 2026-10-11 07:22:00Z | `"agent evaluation logs" OR "evaluation logs" AND LLM` | total=13 fetched=13 |
| 2026-10-11 07:22:05Z | `"trajectories" AND "function calling" AND dataset` | total=0 fetched=0 |

### 1c. Batch 3 (high-recall re-queries, cap 300; the second query exceeded the cap: 300 of 829 fetched)

| UTC time | Query | Result |
|---|---|---|
| 2026-10-11 07:25:53Z | `"indirect prompt injection"` | total=165 fetched=165 |
| 2026-10-11 07:26:19Z | `"prompt injection" AND (LLM OR agent OR agents)` | total=829 fetched=300 |
| 2026-10-11 07:27:06Z | `"AI agent" AND (trajectories OR logs OR traces OR transcripts)` | total=171 fetched=171 |
| 2026-10-11 07:27:47Z | `"tool calls" AND (dataset OR logs OR traces) AND LLM` | total=30 fetched=30 |

Pooled unique Zenodo records collected (batches 1+2+3): 1,941 (1,653 after batches 1+2; +288 from batch 3).

Zenodo detail pass: full-record fetch (`/api/records/<id>`) for 72 records (description, related identifiers, all file names/sizes, licence) plus zip-container listing attempts; plus 36-version enumeration for the AgentDojo concept and 5-version enumeration for the AgentDojo-PROV concept.

## 2. Hugging Face Hub (`https://huggingface.co/api/datasets?...&full=true`)

### 2a. `search=` queries (limit 200; where hits = 200 the list is truncated and the search is substring-fuzzy, e.g. osworld, appworld, gaia, mcp, bfcl, mind2web, agentic, terminal-bench)

| UTC time | Query | Result |
|---|---|---|
| 2026-10-11 07:15:55Z | `agentdojo` | hits=9 |
| 2026-10-11 07:15:56Z | `injecagent` | hits=1 |
| 2026-10-11 07:15:56Z | `agentharm` | hits=10 |
| 2026-10-11 07:15:57Z | `agent security bench` | hits=3 |
| 2026-10-11 07:15:58Z | `agent trajectories` | hits=56 |
| 2026-10-11 07:15:59Z | `agent trajectory` | hits=40 |
| 2026-10-11 07:16:00Z | `agent logs` | hits=10 |
| 2026-10-11 07:16:01Z | `agent traces` | hits=168 |
| 2026-10-11 07:16:01Z | `tool calling trajectories` | hits=1 |
| 2026-10-11 07:16:02Z | `tool use trajectories` | hits=8 |
| 2026-10-11 07:16:03Z | `prompt injection agent` | hits=10 |
| 2026-10-11 07:16:04Z | `indirect prompt injection` | hits=7 |
| 2026-10-11 07:16:05Z | `tau-bench` | hits=68 |
| 2026-10-11 07:16:06Z | `tau2` | hits=101 |
| 2026-10-11 07:16:07Z | `swe-bench trajectories` | hits=7 |
| 2026-10-11 07:16:07Z | `swe-agent trajectories` | hits=14 |
| 2026-10-11 07:16:08Z | `nebius swe` | hits=19 |
| 2026-10-11 07:16:09Z | `webarena` | hits=32 |
| 2026-10-11 07:16:10Z | `osworld` | hits=200 |
| 2026-10-11 07:16:12Z | `appworld` | hits=122 |
| 2026-10-11 07:16:13Z | `gaia` | hits=200 |
| 2026-10-11 07:16:14Z | `inspect logs` | hits=2 |
| 2026-10-11 07:16:14Z | `inspect_ai` | hits=2 |
| 2026-10-11 07:16:15Z | `inspect eval` | hits=5 |
| 2026-10-11 07:16:16Z | `agent benchmark` | hits=56 |
| 2026-10-11 07:16:17Z | `agentic` | hits=200 |
| 2026-10-11 07:16:18Z | `agent runs` | hits=7 |
| 2026-10-11 07:16:19Z | `agent rollouts` | hits=4 |
| 2026-10-11 07:16:20Z | `function calling agent` | hits=12 |
| 2026-10-11 07:16:20Z | `mcp` | hits=200 |
| 2026-10-11 07:16:21Z | `tool poisoning` | hits=1 |
| 2026-10-11 07:16:22Z | `computer use trajectories` | hits=0 |
| 2026-10-11 07:16:23Z | `web agent trajectories` | hits=0 |
| 2026-10-11 07:16:24Z | `openhands` | hits=108 |
| 2026-10-11 07:16:25Z | `terminal-bench` | hits=200 |
| 2026-10-11 07:16:26Z | `agent red teaming` | hits=0 |
| 2026-10-11 07:16:26Z | `agent safety` | hits=13 |
| 2026-10-11 07:16:27Z | `agentdyn` | hits=1 |
| 2026-10-11 07:16:28Z | `autodojo` | hits=0 |
| 2026-10-11 07:16:29Z | `asb agent` | hits=0 |
| 2026-10-11 07:16:29Z | `ipi agent` | hits=3 |
| 2026-10-11 07:16:30Z | `tool injection` | hits=1 |
| 2026-10-11 07:16:31Z | `agent transcripts` | hits=2 |
| 2026-10-11 07:16:32Z | `agent evaluation logs` | hits=0 |
| 2026-10-11 07:16:33Z | `bfcl` | hits=200 |
| 2026-10-11 07:16:34Z | `toolemu` | hits=0 |
| 2026-10-11 07:16:35Z | `r-judge` | hits=7 |
| 2026-10-11 07:16:36Z | `agentbench` | hits=36 |
| 2026-10-11 07:16:37Z | `agent-safetybench` | hits=4 |
| 2026-10-11 07:16:38Z | `openagentsafety` | hits=16 |
| 2026-10-11 07:16:39Z | `wildclaw` | hits=9 |
| 2026-10-11 07:16:39Z | `mind2web` | hits=200 |
| 2026-10-11 07:16:40Z | `browsergym` | hits=1 |
| 2026-10-11 07:16:41Z | `workarena` | hits=14 |
| 2026-10-11 07:16:42Z | `vwa` | hits=8 |
| 2026-10-11 07:16:42Z | `cybench` | hits=13 |
| 2026-10-11 07:16:43Z | `cyber agent` | hits=28 |
| 2026-10-11 07:16:44Z | `ctf agent trajectories` | hits=0 |
| 2026-10-11 07:16:45Z | `sandbagging` | hits=80 |
| 2026-10-11 07:16:46Z | `control arena` | hits=33 |
| 2026-10-11 07:16:47Z | `agent monitor` | hits=3 |
| 2026-10-11 07:16:48Z | `monitoring agent trajectories` | hits=0 |
| 2026-10-11 07:16:48Z | `misalignment agent trajectories` | hits=0 |
| 2026-10-11 07:16:49Z | `claude code transcripts` | hits=0 |
| 2026-10-11 07:16:50Z | `coding agent trajectories` | hits=0 |
| 2026-10-11 07:16:51Z | `agent sessions` | hits=5 |

### 2b. tag `filter=` and extra `search=` queries (limit 1000)

| UTC time | Query | Result |
|---|---|---|
| 2026-10-11 07:36:13Z | `filter=prompt-injection` | hits=361 |
| 2026-10-11 07:36:14Z | `filter=indirect-prompt-injection` | hits=17 |
| 2026-10-11 07:36:15Z | `filter=agent-traces` | hits=774 |
| 2026-10-11 07:36:17Z | `filter=agent-trajectories` | hits=232 |
| 2026-10-11 07:36:19Z | `filter=trajectories` | hits=288 |
| 2026-10-11 07:36:20Z | `filter=trajectory` | hits=160 |
| 2026-10-11 07:36:21Z | `filter=agentdojo` | hits=5 |
| 2026-10-11 07:36:22Z | `filter=inspect-ai` | hits=30 |
| 2026-10-11 07:36:23Z | `filter=inspect` | hits=0 |
| 2026-10-11 07:36:24Z | `filter=agentic-safety` | hits=18 |
| 2026-10-11 07:36:25Z | `filter=agent-safety` | hits=116 |
| 2026-10-11 07:36:26Z | `filter=agent-security` | hits=44 |
| 2026-10-11 07:36:27Z | `filter=tool-use` | hits=1000 |
| 2026-10-11 07:36:29Z | `filter=tool-calling` | hits=539 |
| 2026-10-11 07:36:31Z | `filter=function-calling` | hits=1000 |
| 2026-10-11 07:36:32Z | `filter=agent-evaluation` | hits=302 |
| 2026-10-11 07:36:33Z | `filter=agent-benchmark` | hits=58 |
| 2026-10-11 07:36:35Z | `filter=red-teaming` | hits=342 |
| 2026-10-11 07:36:36Z | `filter=mcp` | hits=390 |
| 2026-10-11 07:36:38Z | `filter=swe-bench` | hits=273 |
| 2026-10-11 07:36:39Z | `filter=tau-bench` | hits=11 |
| 2026-10-11 07:36:40Z | `filter=agentharm` | hits=1 |
| 2026-10-11 07:36:41Z | `filter=injecagent` | hits=0 |
| 2026-10-11 07:36:42Z | `filter=asb` | hits=0 |
| 2026-10-11 07:36:43Z | `filter=traces` | hits=407 |
| 2026-10-11 07:36:45Z | `filter=agent-logs` | hits=0 |
| 2026-10-11 07:36:46Z | `filter=llm-agents` | hits=366 |
| 2026-10-11 07:36:47Z | `search=injection trajectories` | hits=0 |
| 2026-10-11 07:36:48Z | `search=agentdojo-` | hits=9 |
| 2026-10-11 07:36:49Z | `search=asb` | hits=288 |
| 2026-10-11 07:36:50Z | `search=agent-security-bench` | hits=3 |
| 2026-10-11 07:36:51Z | `search=agentic safety` | hits=8 |
| 2026-10-11 07:36:52Z | `search=ipi` | hits=36 |
| 2026-10-11 07:36:53Z | `search=agentdyn` | hits=1 |
| 2026-10-11 07:36:54Z | `search=mcptox` | hits=0 |
| 2026-10-11 07:36:55Z | `search=agent hijacking` | hits=0 |
| 2026-10-11 07:36:57Z | `search=tool hijacking` | hits=0 |
| 2026-10-11 07:36:58Z | `search=agent attack trajectories` | hits=0 |
| 2026-10-11 07:36:59Z | `search=honeypot agent` | hits=0 |
| 2026-10-11 07:37:00Z | `search=llm agent logs` | hits=0 |
| 2026-10-11 07:37:01Z | `search=tool call logs` | hits=0 |
| 2026-10-11 07:37:02Z | `search=eval logs` | hits=52 |
| 2026-10-11 07:37:03Z | `search=.eval` | hits=1000 |
| 2026-10-11 07:37:05Z | `search=swe-bench runs` | hits=0 |
| 2026-10-11 07:37:06Z | `search=terminal agent traces` | hits=4 |

Pooled unique dataset ids: 8,684 (many are fuzzy-name noise or very large families such as the 480 `DCAgent/*` auto-generated trace sets). Per-dataset detail pass (`/api/datasets/<id>?blobs=true`, plus `README.md` card text) for 129 ids; datasets-server `first-rows` for 4.

## 3. DataCite (`https://api.datacite.org/dois?query=<q>&page[size]=100`)

### DataCite queries (Lucene syntax; cap 300 per query)

| UTC time | Query | Result |
|---|---|---|
| 2026-10-11 07:19:04Z | `agentdojo` | total=295 fetched=295 |
| 2026-10-11 07:19:18Z | `AgentDojo` | total=295 fetched=295 |
| 2026-10-11 07:19:30Z | `InjecAgent` | total=83 fetched=83 |
| 2026-10-11 07:19:34Z | `AgentHarm` | total=42 fetched=42 |
| 2026-10-11 07:19:37Z | `"Agent Security Bench"` | total=22 fetched=22 |
| 2026-10-11 07:19:40Z | `"prompt injection" AND agent AND (trajectories OR logs)` | total=144 fetched=144 |
| 2026-10-11 07:19:51Z | `"LLM agent" AND (trajectories OR "execution traces" OR logs) AND dataset` | total=77 fetched=77 |
| 2026-10-11 07:19:56Z | `"agent trajectories" AND dataset` | total=107 fetched=107 |
| 2026-10-11 07:20:03Z | `"tool-calling" AND agent AND dataset AND logs` | total=6 fetched=6 |
| 2026-10-11 07:20:07Z | `inspect_ai` | total=10 fetched=10 |
| 2026-10-11 07:20:10Z | `"Inspect AI" AND evaluation AND logs` | total=11 fetched=11 |
| 2026-10-11 07:20:12Z | `"agent benchmark" AND (trajectories OR logs OR transcripts)` | total=44 fetched=44 |
| 2026-10-11 07:20:16Z | `"tau-bench" OR "tau2-bench"` | total=150 fetched=150 |
| 2026-10-11 07:20:24Z | `"SWE-bench" AND trajectories` | total=234 fetched=234 |
| 2026-10-11 07:20:37Z | `WebArena AND trajectories` | total=56 fetched=56 |
| 2026-10-11 07:20:40Z | `"OpenAgentSafety" OR "Agent-SafetyBench" OR "R-Judge"` | total=167 fetched=167 |
| 2026-10-11 07:20:49Z | `"indirect prompt injection" AND dataset` | total=48 fetched=48 |
| 2026-10-11 07:20:53Z | `"AgentDyn" OR "AutoDojo" OR "DRIFT" AND agentdojo` | total=19 fetched=19 |
| 2026-10-11 07:20:56Z | `"tool poisoning" OR "MCP" AND injection AND dataset` | total=52 fetched=52 |

Unique DOIs: 1,394 (cern.zenodo 584, arxiv.content 571, usc.dl 97 [noise], ccdc.csd 41 [noise], undsci.oopmau 32 [conference videos], figshare.ars 25, ieee.dataport 8, dryad.dryad 6 [noise], cos.osf 5, plus single hits from NIST, Harvard Dataverse, KiltHub, Mendeley, HF DOI client). DataCite surfaced three things not found elsewhere: OSF AgentDojo registrations (nx7kv, mzndh, 3a7pz), NIST `10.18434/mds2-3690` (AgentDojo-Inspect, already known) and IEEE DataPort `10.21227/hr5g-4c33`.

## 4. Figshare, Dryad, OSF, Software Heritage (one loop, same terms)

Terms (17): agentdojo; injecagent; agentharm; prompt injection agent; LLM agent trajectories; agent trajectories; agent benchmark; inspect_ai; tool use agent; agentic benchmark logs; indirect prompt injection; agent security; tau-bench; swe-bench; webarena; agent execution traces; LLM agent logs.

Endpoints: Figshare `POST https://api.figshare.com/v2/articles/search {search_for,page_size:100}`; Dryad `GET https://datadryad.org/api/v2/search?q=&per_page=100`; OSF `GET https://api.osf.io/v2/nodes/?filter[title|description][icontains]=<term>`; SWH `GET https://archive.softwareheritage.org/api/1/origin/search/<term>/?limit=100`.

| UTC time | Repository | Term | Result |
|---|---|---|---|
| 2026-10-11 07:20:33Z | figshare | agentdojo | hits=1 |
| 2026-10-11 07:20:34Z | dryad | agentdojo | total=0 |
| 2026-10-11 07:20:34Z | osf-nodes-title | agentdojo | total=0 |
| 2026-10-11 07:20:36Z | osf-nodes-description | agentdojo | total=0 |
| 2026-10-11 07:20:37Z | swh | agentdojo | hits=10 |
| 2026-10-11 07:21:07Z | figshare | injecagent | hits=0 |
| 2026-10-11 07:21:09Z | dryad | injecagent | total=0 |
| 2026-10-11 07:21:09Z | osf-nodes-title | injecagent | total=0 |
| 2026-10-11 07:21:10Z | osf-nodes-description | injecagent | total=0 |
| 2026-10-11 07:21:13Z | swh | injecagent | hits=13 |
| 2026-10-11 07:21:15Z | figshare | agentharm | hits=1 |
| 2026-10-11 07:21:16Z | dryad | agentharm | total=0 |
| 2026-10-11 07:21:16Z | osf-nodes-title | agentharm | total=0 |
| 2026-10-11 07:21:18Z | osf-nodes-description | agentharm | total=0 |
| 2026-10-11 07:21:19Z | swh | agentharm | hits=1 |
| 2026-10-11 07:21:46Z | figshare | prompt injection agent | hits=77 |
| 2026-10-11 07:21:49Z | dryad | prompt injection agent | total=0 |
| 2026-10-11 07:21:49Z | osf-nodes-title | prompt injection agent | total=0 |
| 2026-10-11 07:21:50Z | osf-nodes-description | prompt injection agent | total=0 |
| 2026-10-11 07:21:52Z | swh | prompt injection agent | hits=1 |
| 2026-10-11 07:21:54Z | figshare | LLM agent trajectories | hits=22 |
| 2026-10-11 07:21:56Z | dryad | LLM agent trajectories | total=0 |
| 2026-10-11 07:21:57Z | osf-nodes-title | LLM agent trajectories | total=0 |
| 2026-10-11 07:21:58Z | osf-nodes-description | LLM agent trajectories | total=0 |
| 2026-10-11 07:22:00Z | swh | LLM agent trajectories | hits=0 |
| 2026-10-11 07:22:28Z | figshare | agent trajectories | hits=100 |
| 2026-10-11 07:22:30Z | dryad | agent trajectories | total=29 |
| 2026-10-11 07:22:33Z | osf-nodes-title | agent trajectories | total=0 |
| 2026-10-11 07:22:34Z | osf-nodes-description | agent trajectories | total=0 |
| 2026-10-11 07:22:36Z | swh | agent trajectories | hits=3 |
| 2026-10-11 07:22:42Z | figshare | agent benchmark | hits=100 |
| 2026-10-11 07:22:44Z | dryad | agent benchmark | total=10 |
| 2026-10-11 07:22:46Z | osf-nodes-title | agent benchmark | total=1 |
| 2026-10-11 07:22:47Z | osf-nodes-description | agent benchmark | total=1 |
| 2026-10-11 07:22:50Z | swh | agent benchmark | hits=100 |
| 2026-10-11 07:23:14Z | figshare | inspect_ai | hits=0 |
| 2026-10-11 07:23:16Z | dryad | inspect_ai | total=0 |
| 2026-10-11 07:23:16Z | osf-nodes-title | inspect_ai | total=0 |
| 2026-10-11 07:23:17Z | osf-nodes-description | inspect_ai | total=0 |
| 2026-10-11 07:23:19Z | swh | inspect_ai | hits=84 |
| 2026-10-11 07:23:38Z | figshare | tool use agent | hits=100 |
| 2026-10-11 07:23:40Z | dryad | tool use agent | total=54 |
| 2026-10-11 07:23:44Z | osf-nodes-title | tool use agent | total=0 |
| 2026-10-11 07:23:45Z | osf-nodes-description | tool use agent | total=0 |
| 2026-10-11 07:23:47Z | swh | tool use agent | hits=5 |
| 2026-10-11 07:23:49Z | figshare | agentic benchmark logs | hits=18 |
| 2026-10-11 07:23:51Z | dryad | agentic benchmark logs | total=0 |
| 2026-10-11 07:23:51Z | osf-nodes-title | agentic benchmark logs | total=0 |
| 2026-10-11 07:23:52Z | osf-nodes-description | agentic benchmark logs | total=0 |
| 2026-10-11 07:23:54Z | swh | agentic benchmark logs | hits=0 |
| 2026-10-11 07:23:56Z | figshare | indirect prompt injection | hits=17 |
| 2026-10-11 07:23:58Z | dryad | indirect prompt injection | total=0 |
| 2026-10-11 07:23:59Z | osf-nodes-title | indirect prompt injection | total=0 |
| 2026-10-11 07:24:00Z | osf-nodes-description | indirect prompt injection | total=4 |
| 2026-10-11 07:24:07Z | swh | indirect prompt injection | hits=9 |
| 2026-10-11 07:24:12Z | figshare | agent security | hits=100 |
| 2026-10-11 07:24:15Z | dryad | agent security | total=7 |
| 2026-10-11 07:24:16Z | osf-nodes-title | agent security | total=0 |
| 2026-10-11 07:24:17Z | osf-nodes-description | agent security | total=2 |
| 2026-10-11 07:24:22Z | swh | agent security | hits=100 |
| 2026-10-11 07:24:25Z | figshare | tau-bench | hits=2 |
| 2026-10-11 07:24:26Z | dryad | tau-bench | total=0 |
| 2026-10-11 07:24:27Z | osf-nodes-title | tau-bench | total=0 |
| 2026-10-11 07:24:28Z | osf-nodes-description | tau-bench | total=0 |
| 2026-10-11 07:24:30Z | swh | tau-bench | hits=14 |
| 2026-10-11 07:24:32Z | figshare | swe-bench | hits=12 |
| 2026-10-11 07:24:33Z | dryad | swe-bench | total=0 |
| 2026-10-11 07:24:34Z | osf-nodes-title | swe-bench | total=0 |
| 2026-10-11 07:24:35Z | osf-nodes-description | swe-bench | total=3 |
| 2026-10-11 07:24:40Z | swh | swe-bench | hits=100 |
| 2026-10-11 07:24:42Z | figshare | webarena | hits=2 |
| 2026-10-11 07:24:44Z | dryad | webarena | total=0 |
| 2026-10-11 07:24:44Z | osf-nodes-title | webarena | total=0 |
| 2026-10-11 07:24:46Z | osf-nodes-description | webarena | total=0 |
| 2026-10-11 07:24:48Z | swh | webarena | hits=100 |
| 2026-10-11 07:25:01Z | figshare | agent execution traces | hits=34 |
| 2026-10-11 07:25:03Z | dryad | agent execution traces | total=0 |
| 2026-10-11 07:25:04Z | osf-nodes-title | agent execution traces | total=0 |
| 2026-10-11 07:25:05Z | osf-nodes-description | agent execution traces | total=0 |
| 2026-10-11 07:25:06Z | swh | agent execution traces | hits=0 |
| 2026-10-11 07:25:09Z | figshare | LLM agent logs | hits=26 |
| 2026-10-11 07:25:10Z | dryad | LLM agent logs | total=0 |
| 2026-10-11 07:25:11Z | osf-nodes-title | LLM agent logs | total=0 |
| 2026-10-11 07:25:13Z | osf-nodes-description | LLM agent logs | total=0 |
| 2026-10-11 07:25:15Z | swh | LLM agent logs | hits=0 |

Unique records: Figshare 529 (145 agent/LLM-ish titles), Dryad 98 (all biology/ecology noise except one TreeSegAgent dataset), OSF nodes 10, SWH origins 539 (code repositories / package pages only). Figshare per-article detail (`GET /v2/articles/<id>`) was fetched for 22 candidates.

SWH exact-origin probes (UTC 07:34-07:36; `GET /api/1/origin/<url>/get/`): usnistgov/agentdojo-inspect archived (visit 2025-10-24); uiuc-kang-lab/InjecAgent archived (2026-04-03); UKGovernmentBEIS/inspect_ai archived (2026-10-04); SWE-agent/SWE-agent archived (2026-09-29); princeton-nlp/SWE-agent archived (2024-12-06); NOT FOUND as origins: github.com/ethz-spylab/agentdojo, agiresearch/ASB, sierra-research/tau-bench, huggingface.co datasets sungjuncho/agentdojo-trajectories and ai-safety-institute/AgentHarm, nickjones39/AgentDojo-PROV. AgentDojo appears only via origin `https://pkg.go.dev/github.com/ethz-spylab/agentdojo` (4 visits).

## 5. Kaggle (`GET https://www.kaggle.com/api/v1/datasets/list?search=<q>&pageSize=20&page=1..2`, unauthenticated; worked)

### Kaggle queries (cap 40 per query)

| UTC time | Query | Result |
|---|---|---|
| 2026-10-11 07:39:32Z | `agentdojo` | hits=0 |
| 2026-10-11 07:39:34Z | `injecagent` | hits=1 |
| 2026-10-11 07:39:35Z | `agentharm` | hits=0 |
| 2026-10-11 07:39:36Z | `agent security bench` | hits=7 |
| 2026-10-11 07:39:38Z | `prompt injection agent` | hits=23 |
| 2026-10-11 07:39:41Z | `indirect prompt injection` | hits=14 |
| 2026-10-11 07:39:42Z | `llm agent trajectories` | hits=8 |
| 2026-10-11 07:39:44Z | `agent trajectories` | hits=40 |
| 2026-10-11 07:39:48Z | `llm agent logs` | hits=17 |
| 2026-10-11 07:39:49Z | `agent traces` | hits=40 |
| 2026-10-11 07:39:53Z | `tool calling agent` | hits=26 |
| 2026-10-11 07:39:57Z | `tool use benchmark` | hits=40 |
| 2026-10-11 07:40:01Z | `swe-bench trajectories` | hits=6 |
| 2026-10-11 07:40:03Z | `tau-bench` | hits=1 |
| 2026-10-11 07:40:04Z | `webarena` | hits=2 |
| 2026-10-11 07:40:05Z | `osworld` | hits=2 |
| 2026-10-11 07:40:07Z | `gaia agent` | hits=0 |
| 2026-10-11 07:40:08Z | `inspect ai logs` | hits=1 |
| 2026-10-11 07:40:10Z | `agent benchmark runs` | hits=36 |
| 2026-10-11 07:40:13Z | `mcp tool poisoning` | hits=1 |
| 2026-10-11 07:40:14Z | `agentic ai security` | hits=14 |
| 2026-10-11 07:40:16Z | `llm agent execution logs` | hits=9 |
| 2026-10-11 07:40:17Z | `agent execution traces` | hits=15 |
| 2026-10-11 07:40:19Z | `function calling traces` | hits=2 |
| 2026-10-11 07:40:20Z | `ai agent logs` | hits=40 |

233 unique datasets; 58 passed the title/subtitle filter (agent AND trajectory/trace/log/...), almost all synthetic or tiny (typical size 10 KB to 5 MB). Only mirrors of Hugging Face data (DTap, SWE-agent) are sizeable.

## 6. Mendeley Data, Papers with Code

* Mendeley Data: `https://data.mendeley.com/api/datasets/search?query=...` ignores the query (returns the same unrelated record); no functional public search API. Coverage obtained instead via DataCite client `bl.mendeley`: 2 hits ("Cyber-Physical Multi-Agent Systems", irrelevant). Web search was not used.
* Papers with Code: `paperswithcode.com/datasets?q=agentdojo` and `/api/v1/datasets/` return HTTP 302 to `https://huggingface.co/papers/trending` (service retired). Hugging Face papers search `https://huggingface.co/api/papers/search?q=agentdojo` works but lists papers, not datasets; not pursued further.

## 7. Decisions by repository (from S3-records.jsonl)

| Repository | include | include-gated | maybe | exclude | known-own |
|---|---|---|---|---|---|
| Dryad | 0 | 0 | 0 | 1 | 0 |
| Figshare | 1 | 0 | 4 | 3 | 0 |
| HuggingFace | 27 | 3 | 18 | 20 | 0 |
| HuggingFace DOI (via DataCite) | 0 | 0 | 0 | 1 | 0 |
| IEEE DataPort (via DataCite) | 0 | 0 | 1 | 0 | 0 |
| Kaggle | 0 | 0 | 0 | 3 | 0 |
| Mendeley Data | 0 | 0 | 0 | 1 | 0 |
| NIST (via DataCite) | 0 | 0 | 0 | 1 | 0 |
| OSF | 0 | 0 | 3 | 2 | 0 |
| Papers with Code | 0 | 0 | 0 | 1 | 0 |
| Software Heritage | 0 | 0 | 1 | 0 | 0 |
| Zenodo | 19 | 0 | 19 | 26 | 1 |

## 8. Screened vs retained, per repository

| Repository | Pooled hits | Passed keyword/data-file stage 1 | Individually assessed (detail fetched) | Recorded in S3-records.jsonl | of which include / include-gated / maybe |
|---|---|---|---|---|---|
| Zenodo | 1,941 | 396 of first 1,653 (+32 of 288) | 72 | 65 | 19 / 0 / 19 |
| Hugging Face | 8,684 | ~700 (id matches security terms 681; traj/trace/log/session/eval 3,108) | 129 | 68 | 27 / 3 / 18 |
| Figshare | 529 | 145 | 22 | 8 | 1 / 0 / 4 |
| OSF | 10 nodes (+5 registrations via DataCite) | 10 | 8 | 5 | 0 / 0 / 3 |
| Dryad | 98 | 1 | 0 | 1 (aggregate negative record) | 0 / 0 / 0 |
| Kaggle | 233 | 58 | 0 (list metadata only) | 3 | 0 / 0 / 0 |
| Software Heritage | 539 | 335 (URL names match; all code/package origins) | 13 exact-origin probes | 1 | 0 / 0 / 1 |
| DataCite | 1,394 | 69 (non-Zenodo/arXiv clients, title filter); 584 Zenodo DOIs cross-checked against the Zenodo pool | 6 | 3 | 0 / 0 / 1 (IEEE DataPort) |

Not individually assessed (bulk families, so the HF "include" total understates the real supply): ~480 `DCAgent/*` auto-generated terminal/BFCL/Mind2Web trace sets; hundreds of `*-trajectories` coding-agent SFT sets (SWE-smith, SWE-Gym, OpenThoughts, Kwai-Klear, AlienKevin, etc.); ~400 HF datasets tagged `agent-traces`; 13+ `mgulavani/openagentsafety_*` variants; `idacy/control-arena-*` (13 repos); Kaggle synthetic traces.

## 9. Exclusion reasons used

code-only; aggregate tables only; benchmark task definitions without runs; derived monitor/classifier labels; container images; synthetic classification data; mirrors/duplicates; pre-registration without data; retired/non-functional service. Reasons are recorded at record level in `S3-records.jsonl` (`exclusion_reason`).

## 10. Known-deposit confirmations

* Zenodo 10.5281/zenodo.12528189: CONFIRMED (AgentDojo v0.1.7, 2024-06-25, MIT, `ethz-spylab/agentdojo-v0.1.7.zip` 52,723,430 B). Concept 12528188: 36 versions confirmed by API at 07:40 UTC (v0.1.7 -> v0.1.35; 17458493 = v0.1.35 106,596,113 B).
* Zenodo 10.5281/zenodo.22135957 (v1.0.0) and 22140262 (v1.0.1): CONFIRMED (dataset, cc-by-4.0, 2026-08-28, `artifact.zip` 237,896 KB per Zenodo size field; concept 22135956). Inner contents not listable.
* AgentDojo-PROV corpus: CONFIRMED on Zenodo, concept 10.5281/zenodo.20692312, 5 versions: 1.0.0 (20692313), 20955507, 2.1 (21050309), 2.2 (21052314), 2.3 (23276620, 2026-10-10, 59 files, ~240 MB, split zips `legacy-runs.part*`, `corpus-prov.part*`).
* Hugging Face `ai-safety-institute/AgentHarm`: CONFIRMED but it contains only the 8 benchmark-definition files (0.3 MB, licence other); it is NOT a run-log source. AgentHarm trajectories exist separately in `antieval/agentharm-trajectories` (new, see summary).
* `schaeff/CIAware-Bench-Data` (known from notes): re-confirmed gated=auto, 2,538 `.eval` + 5,677 json, 8.71 GB.
