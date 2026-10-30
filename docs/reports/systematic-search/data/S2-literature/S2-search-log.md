# S2 literature search log

Run date: 2026-10-11 (UTC), about 07:01-09:00. All queries read-only; User-Agent `agentprov-litsearch/0.1`. Web content treated as untrusted data; no instructions in fetched pages were followed; no datasets downloaded (only repository/dataset metadata, file listings, README/LICENSE text and arXiv HTML pages for full-text screening).

## Access incidents (affect completeness)

- **Semantic Scholar** unauthenticated API returned HTTP 429 repeatedly for the keyword search endpoint; queries s2k2-s2k5 were retried with back-off and only the **first 200 hits by relevance** per query were retrieved (pages of 100). The citations endpoint completed without incident.
- **DBLP** search API (`dblp.org/search/publ/api`) answered with an anti-bot challenge page ("Making sure you're not a bot!", HTTP 200 HTML). It was **not bypassed**; DBLP was covered only through site-restricted web search (4 queries, see below).
- **ACL Anthology** has no query API; covered through site-restricted web search only. **Papers with Code** has been retired and redirects to Hugging Face; covered through site-restricted web search plus the Hugging Face papers search API.
- **GitHub REST API** quota (shared by several agents) was exhausted during the run; repository file listings were obtained from the API where possible (unauthenticated fallback) and otherwise from the public repository HTML tree pages (top level plus up to four log-like sub-directories, two levels deep). Evidence is therefore file/directory-name based and was not content-inspected.
- OpenAlex indexes the arXiv DOI 10.48550/arxiv.2406.13352 under work W4399912700 whose title is "AgentDojo-PROV: A W3C PROV-O Corpus of LLM Agent Executions" (record-merging artefact); the NeurIPS proceedings version is W4415796822. Forward citations were collected for both ids and merged.

## 1. Database queries (exact strings)

Columns: reported = result count reported by the service; retrieved = records downloaded; unique = distinct records in the de-duplicated pool attributable to this query (a record can appear under several queries); S1 = retained after title/abstract screening; FT = assessed at full-text/data-release level; incl = final include.

| Database | Query / URL | Run (UTC) | Reported | Retrieved | Unique | S1 | FT | Incl | Note |
|---|---|---|---|---|---|---|---|---|---|
| Semantic Scholar (citations) | `https://api.semanticscholar.org/graph/v1/paper/arXiv:2406.13352/citations?fields=title,year,venue,externalIds,url,abstract,citationCount&limit=100&offset=0 (offset paging, limit=100)` | 2026-10-11T07:01:58Z | 152 | 152 | 146 | 139 | 117 | 2 | complete forward-citation set returned by the API (paper citationCount=152) |
| Semantic Scholar (keyword search /paper/search) | `AgentDojo` | 2026-10-11T07:14:44Z | 126 | 126 | 123 | 119 | 110 | 2 | all results |
| Semantic Scholar (keyword search /paper/search) | `prompt injection benchmark LLM agents tool use` | 2026-10-11T07:50:33Z | 4466 | 200 | 195 | 90 | 81 | 6 | first 200 by relevance |
| Semantic Scholar (keyword search /paper/search) | `agent security benchmark execution trajectories released` | 2026-10-11T08:10:45Z | 1576 | 200 | 200 | 92 | 89 | 6 | first 200 by relevance |
| Semantic Scholar (keyword search /paper/search) | `LLM agent benchmark tool misuse harmful behavior` | 2026-10-11T08:21:04Z | 603 | 200 | 199 | 87 | 78 | 5 | first 200 by relevance |
| Semantic Scholar (keyword search /paper/search) | `agent benchmark released trajectories logs dataset` | 2026-10-11T08:23:47Z | 2049 | 200 | 198 | 67 | 66 | 5 | first 200 by relevance |
| OpenAlex | `works?filter=cites:W4415796822` | 2026-10-11T07:02:21Z | 102 | 102 | 102 | 88 | 4 | 0 | cursor paging, per-page=200 |
| OpenAlex | `works?filter=cites:W4399912700` | 2026-10-11T07:02:23Z | 7 | 7 | 7 | 6 | 1 | 0 | cursor paging, per-page=200 |
| OpenAlex | `works?filter=title_and_abstract.search:AgentDojo` | 2026-10-11T07:13:36Z | 187 | 187 | 178 | 166 | 140 | 2 | cursor paging, per-page=200 |
| OpenAlex | `works?filter=title_and_abstract.search:(prompt injection) AND (agent benchmark),publication_year:>2023` | 2026-10-11T07:13:38Z | 551 | 552 | 505 | 262 | 219 | 5 | cursor paging, per-page=200 |
| OpenAlex | `works?filter=fulltext.search:AgentDojo,publication_year:>2023` | 2026-10-11T07:13:45Z | 1188 | 1189 | 1159 | 988 | 824 | 13 | cursor paging, per-page=200 |
| OpenAlex | `works?filter=title_and_abstract.search:(agent trajectories) AND (security benchmark),publication_year:>2023` | 2026-10-11T07:13:56Z | 112 | 112 | 107 | 48 | 40 | 3 | cursor paging, per-page=200 |
| arXiv (export API) | `search_query=all:"AgentDojo"` | 2026-10-11T07:02:32Z | 114 | 114 | 114 | 111 | 111 | 2 | sortBy=submittedDate desc |
| arXiv (export API) | `search_query=abs:"prompt injection" AND abs:agent AND abs:benchmark` | 2026-10-11T07:02:37Z | 228 | 228 | 228 | 157 | 157 | 5 | sortBy=submittedDate desc |
| arXiv (export API) | `search_query=abs:agent AND abs:trajectories AND abs:security` | 2026-10-11T07:02:45Z | 165 | 165 | 165 | 69 | 69 | 4 | sortBy=submittedDate desc |
| arXiv (export API) | `search_query=abs:"tool-use" AND abs:benchmark AND abs:logs` | 2026-10-11T07:02:49Z | 29 | 29 | 29 | 13 | 13 | 0 | sortBy=submittedDate desc |
| arXiv (export API) | `search_query=abs:"agent" AND abs:"benchmark" AND (abs:"trajectories" OR abs:"execution logs" OR abs:"traces") AND (abs:"released" OR abs:"open-source" OR abs:"publicly available")` | 2026-10-11T07:02:53Z | 623 | 623 | 623 | 420 | 420 | 16 | sortBy=submittedDate desc |
| arXiv (export API) | `search_query=abs:"indirect prompt injection" AND abs:agents` | 2026-10-11T07:03:12Z | 164 | 164 | 164 | 118 | 118 | 6 | sortBy=submittedDate desc |
| arXiv (export API) | `search_query=abs:"harmful" AND abs:agent AND abs:benchmark AND abs:"tool"` | 2026-10-11T07:03:16Z | 107 | 107 | 107 | 65 | 65 | 1 | sortBy=submittedDate desc |
| arXiv (export API) | `search_query=abs:"AgentDojo" OR ti:"AgentDojo"` | 2026-10-11T07:03:20Z | 114 | 114 | 114 | 111 | 111 | 2 | sortBy=submittedDate desc |
| OpenReview (api2 notes/search, source=all) | `term=AgentDojo` | 2026-10-11T07:14:50Z | 355 | 170 | 54 | 37 | 28 | 1 | 355 notes (submissions+reviews) from first 1000 hits collapsed to 170 distinct forums; API caps count at 10000 |
| OpenReview (api2 notes/search, source=all) | `term=prompt injection agent benchmark` | 2026-10-11T07:14:53Z | 10000 | 780 | 414 | 63 | 34 | 0 | 1000 notes (submissions+reviews) from first 1000 hits collapsed to 780 distinct forums; API caps count at 10000 |
| OpenReview (api2 notes/search, source=all) | `term=agent security benchmark` | 2026-10-11T07:14:57Z | 10000 | 779 | 481 | 73 | 35 | 0 | 1000 notes (submissions+reviews) from first 1000 hits collapsed to 779 distinct forums; API caps count at 10000 |
| OpenReview (api2 notes/search, source=all) | `term=agent trajectories released benchmark tool use` | 2026-10-11T07:15:02Z | 10000 | 727 | 444 | 55 | 25 | 2 | 1000 notes (submissions+reviews) from first 1000 hits collapsed to 727 distinct forums; API caps count at 10000 |
| Hugging Face papers (api/papers/search) | `q=AgentDojo` | 2026-10-11T07:14Z | 33 | 33 | 33 | 33 | 33 | 2 |  |
| Hugging Face papers (api/papers/search) | `q=prompt injection agent benchmark` | 2026-10-11T07:14Z | 120 | 120 | 120 | 51 | 51 | 2 |  |
| Hugging Face papers (api/papers/search) | `q=agent security benchmark trajectories` | 2026-10-11T07:14Z | 120 | 120 | 120 | 69 | 69 | 6 |  |

## 2. Web searches (site-restricted where stated)

The search tool exposes no per-call timestamp; all ran between 2026-10-11 07:10 and 07:40 UTC. Each returned the top ~10 results (a reported total is not available). Distinct arXiv papers returned are tagged `WEB:<query>` in `found_in`.

| # | Query | Site restriction | arXiv ids returned | already in structured-search pool |
|---|---|---|---|---|
| 1 | `AgentDojo prompt injection agents` | dblp-site | 10 | 10 |
| 2 | `AgentDojo agent security benchmark prompt injection` | aclanthology-site | 10 | 10 |
| 3 | `AgentDojo benchmark Papers with Code` | paperswithcode/hf-site | 7 | 7 |
| 4 | `dblp agent security benchmark LLM agents trajectories dataset released` | dblp-site | 9 | 9 |
| 5 | `benchmark LLM agent trajectories released agent logs dataset tool misuse harmful agent behaviour` | aclanthology-site | 8 | 8 |
| 6 | `AgentHarm OR ASB OR InjecAgent` | paperswithcode-site | 10 | 10 |
| 7 | `dataset of agent trajectories prompt injection released HF AgentDojo runs logs` | web | 5 | 5 |
| 8 | `NeurIPS D&B agent security benchmark prompt injection AgentDojo extension` | openreview-site | 4 | 4 |
| 9 | `Agent Security Tools Survey zenodo` | web | 7 | 7 |
| 10 | `AgentDojo extension benchmark dynamic environments` | hf-site | 4 | 4 |
| 11 | `LLM agent prompt injection benchmark tool-integrated` | aclanthology-site | 5 | 5 |
| 12 | `AgentDojo 2025 NeurIPS ICLR defense` | dblp-site | 9 | 9 |
| 13 | `AgentDojo benchmark dataset` | paperswithcode-site | 2 | 2 |

Distinct arXiv ids returned by web search: 60; all are in the final pool; 6 were found only by web search and were added (2402.11208, 2506.00641, 2604.03242, 2606.04990, 2606.24530, 2606.28450). Non-arXiv hits noted: OpenReview forum m1YYAQjO3w (AgentDojo), AgentHarm AC5n7xHuR1, ASB V4y0CpX4hK, LLMail-Inject, WASP, AgentDAM, RedTeamCUA; ACL Anthology 2024.findings-acl.624 (InjecAgent), 2025.acl-long.1435 (Task Shield), 2026.findings-acl.1850 (ToolSafe), 2026.acl-long.443 (VIGIL/SIREN, no arXiv id found); dblp AIware 2026 proceedings page; Papers with Code pages for AgentBench/APIBench/EnvBench and the paper page for 2506.01055.

## 3. Supplementary location searches (where logs may live; not literature databases)

| Service | Query | Run (UTC) | Reported | Retrieved | Note |
|---|---|---|---|---|---|
| Zenodo records API | `AgentDojo` | 2026-10-11T07:20:48Z | 50 | 50 | metadata and file lists only; a curated subset entered the records as dataset-record |
| Zenodo records API | `"prompt injection" AND (agent OR agents) AND (trajectories OR logs OR traces)` | 2026-10-11T07:20:55Z | 60 | 60 | metadata and file lists only; a curated subset entered the records as dataset-record |
| Zenodo records API | `("LLM agent" OR "LLM agents") AND benchmark AND (trajectories OR "execution logs" OR transcripts)` | 2026-10-11T07:21:06Z | 31 | 31 | metadata and file lists only; a curated subset entered the records as dataset-record |
| Hugging Face datasets API | `search=agentdojo` (limit 200) | 2026-10-11T07:16Z | 9 | 9 | titles screened; only agentdojo hits, agent-security hits and named trajectory datasets curated into records (prompt-injection hits are almost all single-turn classifier datasets: excluded as non-agent LLM evals) |
| Hugging Face datasets API | `search=prompt injection` (limit 200) | 2026-10-11T07:16Z | 200 | 200 | titles screened; only agentdojo hits, agent-security hits and named trajectory datasets curated into records (prompt-injection hits are almost all single-turn classifier datasets: excluded as non-agent LLM evals) |
| Hugging Face datasets API | `search=agent trajectories` (limit 200) | 2026-10-11T07:16Z | 56 | 56 | titles screened; only agentdojo hits, agent-security hits and named trajectory datasets curated into records (prompt-injection hits are almost all single-turn classifier datasets: excluded as non-agent LLM evals) |
| Hugging Face datasets API | `search=agent security` (limit 200) | 2026-10-11T07:16Z | 21 | 21 | titles screened; only agentdojo hits, agent-security hits and named trajectory datasets curated into records (prompt-injection hits are almost all single-turn classifier datasets: excluded as non-agent LLM evals) |
| Hugging Face datasets API | `search=agent benchmark trajectories` (limit 200) | 2026-10-11T07:16Z | 0 | 0 | titles screened; only agentdojo hits, agent-security hits and named trajectory datasets curated into records (prompt-injection hits are almost all single-turn classifier datasets: excluded as non-agent LLM evals) |
| GitHub (tree API / HTML tree pages) | per-repository listings for the repositories linked from papers | 2026-10-11 07:40-09:00Z | - | - | evidence level: directory/file names |

## 4. Screening procedure

**Pool.** Union of all retrieved records, de-duplicated by arXiv id, then DOI-derived arXiv id, then normalised title.
**Stage 1 (title/abstract, rule-based with manual review of the AgentDojo-named list).** Out of scope: published before 2023; non-LLM domain terms in title; no LLM-agent term (llm, language model, agentic, tool use, MCP, computer-use, ...) in title/abstract. Retained if any of: (A) agent + benchmark/dataset/evaluation + log/trajectory + release terms in the abstract; (B) AgentDojo named in the abstract with a benchmark/security term; (C) security term + benchmark term + bench/dataset/arena/gym-style word in the title; (D) AgentDojo found in the full text (OpenAlex full-text index) or the paper cites AgentDojo (S2/OpenAlex forward citations) and has an agent term. The 183 titles naming AgentDojo in the abstract were read by hand.
**Stage 2 (full text / data-release assessment).** For retained arXiv papers the arXiv HTML text was fetched (abstract page if no HTML) and scanned for (i) public repository/dataset/Zenodo/OSF/project links, scored for being the paper's own artefact (arXiv comments, first-page footnotes, name overlap with the title, release phrasing; links introduced by 'built on/from/using' penalised; model-hub and framework links dropped), (ii) sentences about releasing trajectories/logs/traces. Own links were then inspected: GitHub trees (directory/file names, counts, sizes where the API answered), Hugging Face dataset file lists, Zenodo file lists/descriptions. `releases_logs = yes` requires a runs/logs/trajectories/traces/transcripts/episodes/rollouts-style directory or file group with at least 3 data files (confidence high if confirmed through API/HF/Zenodo listing, medium if only HTML tree), or a results/outputs directory plus an explicit release statement, or a trajectory-titled paper with a 50+ file data directory. `unclear` = release claimed or generic data directory, per-run logs not confirmed. Non-arXiv items: Zenodo records checked through the Zenodo API; other publisher pages were not retrievable and are marked accordingly. AgentDojo relation: `extends` (abstract/body says extend/build on/fork AgentDojo, or manual), `uses` (AgentDojo in abstract or >=5 mentions in the body), `cites_only` (in a citation set or 1-4 mentions), `none`.
**Inclusion.** (1) LLM-agent benchmark or evaluation, (2) per-run logs/trajectories publicly released in machine-readable form, (3) open access without request form (gating recorded), (4) licence policy below.
**Licence policy (added by the user during the run).** For every artefact a paper points to, the licence was read from the repository LICENSE file (LICENSE-DATA preferred for data), else the dataset card metadata (Hugging Face), else Zenodo record metadata, else a README licence statement, and normalised to an SPDX id or `none` (no licence found), `custom-restrictive` (non-redistributable / evaluation-only / research-only / all rights reserved) or `unknown` (not determinable); `licence_source` says where it was found. Artefacts with `none`, `custom-restrictive` or ND licences that otherwise qualify are **excluded from conversion but kept as records** (`licence_excluded: true`, reason in `exclusion_reason`). CC-BY-NC is kept with `licence_note`. Repository-level licences are recorded as such; whether they cover third-party data inside the repository is not checked.
**Manual review.** Directory listings of every security/AgentDojo-linked include were read and 16 automatic calls were downgraded or promoted (`manual_review` field in the records).

## 5. Known-source recall

| Known source | Found by | Result in this search |
|---|---|---|
| AgentDojo (arXiv:2406.13352) | HF-AgentDojo, OA-q1_tiabs_AgentDojo, OA-q2_pi_agent_benchmark, OA-q3_fulltext_AgentDojo, S2-s2k1, S2-s2k2, WEB, arXiv-ax1, arXiv-ax8 | exclude / releases_logs=yes; licence=MIT |
| ROPE (arXiv:2608.27496) | OA-q3_fulltext_AgentDojo, arXiv-ax3, arXiv-ax6 | include / releases_logs=yes; licence=MIT |
| AutoDojo (arXiv:2606.15057) | HF-AgentDojo, HF-prompt_injection_agent_benchmark, OA-q1_tiabs_AgentDojo, OA-q2_pi_agent_benchmark, OA-q3_fulltext_AgentDojo, S2-s2k1, S2-s2k2, WEB, arXiv-ax1, arXiv-ax2, arXiv-ax6, arXiv-ax8 | exclude / releases_logs=no; licence=MIT |
| AgentLAB (arXiv:2602.16901) | HF-agent_security_benchmark_trajectories, OR-agent_securi, S2-s2k2 | exclude / releases_logs=no; licence=None |
| AgentDyn (arXiv:2602.03117) | HF-AgentDojo, HF-agent_security_benchmark_trajectories, HF-prompt_injection_agent_benchmark, OA-q2_pi_agent_benchmark, OA-q3_fulltext_AgentDojo, WEB, arXiv-ax2, arXiv-ax6 | include / releases_logs=yes; licence=MIT |
| DRIFT (arXiv:2506.12104) | OA-q1_tiabs_AgentDojo, OA-q2_pi_agent_benchmark, OA-q3_fulltext_AgentDojo, OA-q4_traj_security, OR-AgentDojo, S2-s2k1, S2-s2k2, S2-s2k4, arXiv-ax1, arXiv-ax2, arXiv-ax3, arXiv-ax8 | include / releases_logs=yes; licence=MIT |
| AgentHarm (arXiv:2410.09024) | OA-q3_fulltext_AgentDojo, OR-AgentDojo, OR-agent_securi, OR-prompt_injec, S2-cit, S2-s2k2, S2-s2k4, S2-s2k5, WEB, arXiv-ax7 | exclude / releases_logs=no; licence=MIT |
| ADI (arXiv:2607.05120) | OA-q3_fulltext_AgentDojo, arXiv-ax6 | exclude / releases_logs=no; licence=None |
| STAC (arXiv:2509.25624) | S2-cit, S2-s2k2 | exclude / releases_logs=no; licence=CC-BY-NC-4.0 |
| ASB (arXiv:2410.02644) | HF-agent_security_benchmark_trajectories, HF-prompt_injection_agent_benchmark, OA-q2_pi_agent_benchmark, OA-q3_fulltext_AgentDojo, OR-AgentDojo, OR-agent_securi, OR-prompt_injec, S2-s2k2, WEB, arXiv-ax2 | exclude / releases_logs=no; licence=MIT |
| AgentDojo-PROV | OpenAlex (W4399912700 merged under the AgentDojo arXiv DOI), Zenodo search (record 23276620) | found; dataset-record marked known |
| CIAware-Bench (arXiv:2606.11063) | not found by any structured query (AI-control benchmark with no AgentDojo link); only by a direct OpenAlex title search | outside the AgentDojo/prompt-injection query space |
| Agent Security Tools Survey, Mandate-AgentDojo-Eval, MiDojo, NIST AgentDojo-Inspect | not found (no paper/preprint under those names; repository or Zenodo artefacts only) | expected: repository artefacts, not literature records |

Recall check: 54 of the 60 arXiv ids surfaced by the 13 web searches were already in the structured-search pool (90%).

## 6. Limitations

- Full text was machine-scanned, not read; own-repository identification is heuristic. Security/AgentDojo-linked includes were checked by hand; general-agentic includes less so.
- Evidence is based on file/directory names and counts; no log file was downloaded or parsed, so log schemas are not verified.
- Semantic Scholar keyword search is limited to the top 200 hits per query; OpenReview generic queries to the first 1000 notes.
- Papers newer than the indexes (Aug-Oct 2026) may be missing from OpenAlex/Semantic Scholar forward citations; arXiv abstract queries cover them.
- DBLP and ACL Anthology were not directly queryable (see incidents).
