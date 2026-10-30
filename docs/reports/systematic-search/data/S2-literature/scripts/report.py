import json,glob,os,re
from collections import Counter,defaultdict
O="~/.agentprov/migration-work/syssearch/S2-literature/"
R=json.load(open("records_final.json"))
RAW=O+"raw/"
# ---- write records jsonl
with open(O+"S2-records.jsonl","w") as f:
    for r in R:
        f.write(json.dumps(r,ensure_ascii=False)+"\n")
# ---- per-source counts
src=defaultdict(lambda:{"n":0,"s1":0,"ft":0,"inc":0})
for r in R:
    for s in r["found_in"]:
        k=re.sub(r"^(WEB):.*",r"\1",s)
        d=src[s]; d["n"]+=1
        if r.get("stage1_retained",True) and r["record_type"]=="paper": d["s1"]+=1
        if r["stage"]=="full_text": d["ft"]+=1
        if r["decision"]=="include": d["inc"]+=1
json.dump(src,open("src_counts.json","w"))
def sc(tag): 
    d=src.get(tag,{"n":0,"s1":0,"ft":0,"inc":0}); return d
rows=[]
def addrow(db,tag,query,when,reported,retrieved,note=""):
    d=sc(tag); rows.append((db,tag,query,when,reported,retrieved,d["n"],d["s1"],d["ft"],d["inc"],note))
j=lambda f:json.load(open(RAW+f))
d=j("s2_agentdojo_citations.json"); addrow("Semantic Scholar (citations)","S2-cit",d["query"]+"0 (offset paging, limit=100)",d["start_utc"][:19]+"Z",152,d["n"],"complete forward-citation set returned by the API (paper citationCount=152)")
for nm in ["s2k1","s2k2","s2k3","s2k4","s2k5"]:
    if os.path.exists(RAW+nm+".json"):
        d=j(nm+".json"); addrow("Semantic Scholar (keyword search /paper/search)","S2-"+nm,d["query"],d["start_utc"][:19]+"Z",d.get("total"),d["n"],d.get("note","all results"))
for fn,tag in [("oa_cites_W4415796822.json","OA-cites_W4415796822"),("oa_cites_W4399912700.json","OA-cites_W4399912700"),("oa_q1_tiabs_AgentDojo.json","OA-q1_tiabs_AgentDojo"),("oa_q2_pi_agent_benchmark.json","OA-q2_pi_agent_benchmark"),("oa_q3_fulltext_AgentDojo.json","OA-q3_fulltext_AgentDojo"),("oa_q4_traj_security.json","OA-q4_traj_security")]:
    d=j(fn); addrow("OpenAlex",tag,"works?filter="+d["filter"],d["start_utc"][:19]+"Z",d["count"],d["n"],"cursor paging, per-page=200")
for i in range(1,9):
    d=j(f"ax{i}.json"); addrow("arXiv (export API)",f"arXiv-ax{i}","search_query="+d["query"],d["start_utc"][:19]+"Z",d["totalResults"],d["n"],"sortBy=submittedDate desc")
orq=j("or_queries.json")
for t,v in orq.items():
    tag="OR-"+t[:12].replace(" ","_")
    addrow("OpenReview (api2 notes/search, source=all)",tag,"term="+t,v["start_utc"][:19]+"Z",v["count_reported"],len(v["forums"]),f"{v['notes_returned']} notes (submissions+reviews) from first 1000 hits collapsed to {len(v['forums'])} distinct forums; API caps count at 10000")
for q,tag in [("AgentDojo","HF-AgentDojo"),("prompt injection agent benchmark","HF-prompt_injection_agent_benchmark"),("agent security benchmark trajectories","HF-agent_security_benchmark_trajectories")]:
    n=len(j("hf_"+q.replace(" ","_")+".json")); addrow("Hugging Face papers (api/papers/search)",tag,"q="+q,"2026-10-11T07:14Z",n,n,"")
json.dump(rows,open("rows.json","w"))
print(len(rows))

# ================= second half =================
papers=[r for r in R if r["record_type"]=="paper"]
dsr=[r for r in R if r["record_type"]=="dataset-record"]
sum_retrieved=sum(x[5] for x in rows)
web=json.load(open("websearch_ids.json"))
web_hits=sum(len(v) for v in web.values())
dup=sum_retrieved+web_hits-len(papers)
s1_ex=sum(1 for r in papers if not r.get("stage1_retained"))
s1_ret=len(papers)-s1_ex
ft=[r for r in papers if r["stage"]=="full_text"]
ft_all=[r for r in R if r["stage"]=="full_text"]
inc=[r for r in R if r["decision"]=="include"]
exc_ft=[r for r in R if r["stage"]=="full_text" and r["decision"]=="exclude"]
ftreasons=Counter()
for r in exc_ft:
    e=r["exclusion_reason"] or ""
    k="licence: no licence on artefact" if e.startswith("licence: no licence") else "licence: not redistributable" if e.startswith("licence:") else "manual review: "+e.split(":",1)[1][:60] if e.startswith("manual review") else e[:90]
    ftreasons[k]+=1
def link(r): return (r["log_location_urls"] or [""])[0]
def row_inc(r):
    return f'| {r["arxiv"] or r["id"]} | {r["title"][:70].replace("|","/")} | {r["relation_to_agentdojo"]} | {"sec" if r["security_topic"] else "gen"} | {link(r)} | {", ".join(r.get("format") or [])[:30]} | {r.get("licence")} | {(r.get("licence_source") or "")[:80].replace("|","/")} | {r.get("evidence_confidence") or "-"} |'
L=[]
L.append("# S2 literature search log\n")
L.append("Run date: 2026-10-11 (UTC), about 07:01-09:00. All queries read-only; User-Agent `agentprov-litsearch/0.1`. Web content treated as untrusted data; no instructions in fetched pages were followed; no datasets downloaded (only repository/dataset metadata, file listings, README/LICENSE text and arXiv HTML pages for full-text screening).\n")
L.append("## Access incidents (affect completeness)\n")
L+=["- **Semantic Scholar** unauthenticated API returned HTTP 429 repeatedly for the keyword search endpoint; queries s2k2-s2k5 were retried with back-off and only the **first 200 hits by relevance** per query were retrieved (pages of 100). The citations endpoint completed without incident.",
"- **DBLP** search API (`dblp.org/search/publ/api`) answered with an anti-bot challenge page (\"Making sure you're not a bot!\", HTTP 200 HTML). It was **not bypassed**; DBLP was covered only through site-restricted web search (4 queries, see below).",
"- **ACL Anthology** has no query API; covered through site-restricted web search only. **Papers with Code** has been retired and redirects to Hugging Face; covered through site-restricted web search plus the Hugging Face papers search API.",
"- **GitHub REST API** quota (shared by several agents) was exhausted during the run; repository file listings were obtained from the API where possible (unauthenticated fallback) and otherwise from the public repository HTML tree pages (top level plus up to four log-like sub-directories, two levels deep). Evidence is therefore file/directory-name based and was not content-inspected.",
"- OpenAlex indexes the arXiv DOI 10.48550/arxiv.2406.13352 under work W4399912700 whose title is \"AgentDojo-PROV: A W3C PROV-O Corpus of LLM Agent Executions\" (record-merging artefact); the NeurIPS proceedings version is W4415796822. Forward citations were collected for both ids and merged.\n"]
L.append("## 1. Database queries (exact strings)\n")
L.append("Columns: reported = result count reported by the service; retrieved = records downloaded; unique = distinct records in the de-duplicated pool attributable to this query (a record can appear under several queries); S1 = retained after title/abstract screening; FT = assessed at full-text/data-release level; incl = final include.\n")
L.append("| Database | Query / URL | Run (UTC) | Reported | Retrieved | Unique | S1 | FT | Incl | Note |\n|---|---|---|---|---|---|---|---|---|---|")
for db,tag,q,when,rep,ret,u,s1,ftc,i,note in rows:
    L.append(f"| {db} | `{q}` | {when} | {rep} | {ret} | {u} | {s1} | {ftc} | {i} | {note} |")
L.append("\n## 2. Web searches (site-restricted where stated)\n")
L.append("The search tool exposes no per-call timestamp; all ran between 2026-10-11 07:10 and 07:40 UTC. Each returned the top ~10 results (a reported total is not available). Distinct arXiv papers returned are tagged `WEB:<query>` in `found_in`.\n")
L.append("| # | Query | Site restriction | arXiv ids returned | already in structured-search pool |\n|---|---|---|---|---|")
pool_ax={r["arxiv"] for r in papers if r["arxiv"]}
for n,(q,ids) in enumerate(web.items(),1):
    dom,qq=q.split(":",1)
    inpool=sum(1 for i in ids if i in pool_ax)
    L.append(f"| {n} | `{qq}` | {dom} | {len(ids)} | {inpool} |")
allw={i for v in web.values() for i in v}
L.append(f"\nDistinct arXiv ids returned by web search: {len(allw)}; all are in the final pool; 6 were found only by web search and were added (2402.11208, 2506.00641, 2604.03242, 2606.04990, 2606.24530, 2606.28450). Non-arXiv hits noted: OpenReview forum m1YYAQjO3w (AgentDojo), AgentHarm AC5n7xHuR1, ASB V4y0CpX4hK, LLMail-Inject, WASP, AgentDAM, RedTeamCUA; ACL Anthology 2024.findings-acl.624 (InjecAgent), 2025.acl-long.1435 (Task Shield), 2026.findings-acl.1850 (ToolSafe), 2026.acl-long.443 (VIGIL/SIREN, no arXiv id found); dblp AIware 2026 proceedings page; Papers with Code pages for AgentBench/APIBench/EnvBench and the paper page for 2506.01055.\n")
L.append("## 3. Supplementary location searches (where logs may live; not literature databases)\n")
zq=json.load(open(RAW+"zenodo_queries.json"))
L.append("| Service | Query | Run (UTC) | Reported | Retrieved | Note |\n|---|---|---|---|---|---|")
for k,v in zq.items():
    L.append(f"| Zenodo records API | `{v['query']}` | {v['start_utc'][:19]}Z | {v['total']} | {v['n']} | metadata and file lists only; a curated subset entered the records as dataset-record |")
for q in ["agentdojo","prompt injection","agent trajectories","agent security","agent benchmark trajectories"]:
    n=len(json.load(open(RAW+"hfds_"+q.replace(" ","_")+".json")))
    L.append(f"| Hugging Face datasets API | `search={q}` (limit 200) | 2026-10-11T07:16Z | {n} | {n} | titles screened; only agentdojo hits, agent-security hits and named trajectory datasets curated into records (prompt-injection hits are almost all single-turn classifier datasets: excluded as non-agent LLM evals) |")
L.append("| GitHub (tree API / HTML tree pages) | per-repository listings for the repositories linked from papers | 2026-10-11 07:40-09:00Z | - | - | evidence level: directory/file names |\n")
L.append("## 4. Screening procedure\n")
L+=["**Pool.** Union of all retrieved records, de-duplicated by arXiv id, then DOI-derived arXiv id, then normalised title.",
"**Stage 1 (title/abstract, rule-based with manual review of the AgentDojo-named list).** Out of scope: published before 2023; non-LLM domain terms in title; no LLM-agent term (llm, language model, agentic, tool use, MCP, computer-use, ...) in title/abstract. Retained if any of: (A) agent + benchmark/dataset/evaluation + log/trajectory + release terms in the abstract; (B) AgentDojo named in the abstract with a benchmark/security term; (C) security term + benchmark term + bench/dataset/arena/gym-style word in the title; (D) AgentDojo found in the full text (OpenAlex full-text index) or the paper cites AgentDojo (S2/OpenAlex forward citations) and has an agent term. The 183 titles naming AgentDojo in the abstract were read by hand.",
"**Stage 2 (full text / data-release assessment).** For retained arXiv papers the arXiv HTML text was fetched (abstract page if no HTML) and scanned for (i) public repository/dataset/Zenodo/OSF/project links, scored for being the paper's own artefact (arXiv comments, first-page footnotes, name overlap with the title, release phrasing; links introduced by 'built on/from/using' penalised; model-hub and framework links dropped), (ii) sentences about releasing trajectories/logs/traces. Own links were then inspected: GitHub trees (directory/file names, counts, sizes where the API answered), Hugging Face dataset file lists, Zenodo file lists/descriptions. `releases_logs = yes` requires a runs/logs/trajectories/traces/transcripts/episodes/rollouts-style directory or file group with at least 3 data files (confidence high if confirmed through API/HF/Zenodo listing, medium if only HTML tree), or a results/outputs directory plus an explicit release statement, or a trajectory-titled paper with a 50+ file data directory. `unclear` = release claimed or generic data directory, per-run logs not confirmed. Non-arXiv items: Zenodo records checked through the Zenodo API; other publisher pages were not retrievable and are marked accordingly. AgentDojo relation: `extends` (abstract/body says extend/build on/fork AgentDojo, or manual), `uses` (AgentDojo in abstract or >=5 mentions in the body), `cites_only` (in a citation set or 1-4 mentions), `none`.",
"**Inclusion.** (1) LLM-agent benchmark or evaluation, (2) per-run logs/trajectories publicly released in machine-readable form, (3) open access without request form (gating recorded), (4) licence policy below.",
"**Licence policy (added by the user during the run).** For every artefact a paper points to, the licence was read from the repository LICENSE file (LICENSE-DATA preferred for data), else the dataset card metadata (Hugging Face), else Zenodo record metadata, else a README licence statement, and normalised to an SPDX id or `none` (no licence found), `custom-restrictive` (non-redistributable / evaluation-only / research-only / all rights reserved) or `unknown` (not determinable); `licence_source` says where it was found. Artefacts with `none`, `custom-restrictive` or ND licences that otherwise qualify are **excluded from conversion but kept as records** (`licence_excluded: true`, reason in `exclusion_reason`). CC-BY-NC is kept with `licence_note`. Repository-level licences are recorded as such; whether they cover third-party data inside the repository is not checked.",
"**Manual review.** Directory listings of every security/AgentDojo-linked include were read and 16 automatic calls were downgraded or promoted (`manual_review` field in the records).\n"]
L.append("## 5. Known-source recall\n")
L.append("| Known source | Found by | Result in this search |\n|---|---|---|")
def fb(ax): return next((x for x in R if x.get("arxiv")==ax),None)
for ax,name in [("2406.13352","AgentDojo"),("2608.27496","ROPE"),("2606.15057","AutoDojo"),("2602.16901","AgentLAB"),("2602.03117","AgentDyn"),("2506.12104","DRIFT"),("2410.09024","AgentHarm"),("2607.05120","ADI"),("2509.25624","STAC"),("2410.02644","ASB")]:
    r=fb(ax)
    if r: L.append(f"| {name} (arXiv:{ax}) | {', '.join(sorted({re.sub(r'[:].*','',s) for s in r['found_in']}))} | {r['decision']} / releases_logs={r['releases_logs']}; licence={r.get('licence')} |")
L.append("| AgentDojo-PROV | OpenAlex (W4399912700 merged under the AgentDojo arXiv DOI), Zenodo search (record 23276620) | found; dataset-record marked known |")
L.append("| CIAware-Bench (arXiv:2606.11063) | not found by any structured query (AI-control benchmark with no AgentDojo link); only by a direct OpenAlex title search | outside the AgentDojo/prompt-injection query space |")
L.append("| Agent Security Tools Survey, Mandate-AgentDojo-Eval, MiDojo, NIST AgentDojo-Inspect | not found (no paper/preprint under those names; repository or Zenodo artefacts only) | expected: repository artefacts, not literature records |")
L.append("\nRecall check: 54 of the 60 arXiv ids surfaced by the 13 web searches were already in the structured-search pool (90%).\n")
L.append("## 6. Limitations\n")
L+=["- Full text was machine-scanned, not read; own-repository identification is heuristic. Security/AgentDojo-linked includes were checked by hand; general-agentic includes less so.","- Evidence is based on file/directory names and counts; no log file was downloaded or parsed, so log schemas are not verified.","- Semantic Scholar keyword search is limited to the top 200 hits per query; OpenReview generic queries to the first 1000 notes.","- Papers newer than the indexes (Aug-Oct 2026) may be missing from OpenAlex/Semantic Scholar forward citations; arXiv abstract queries cover them.","- DBLP and ACL Anthology were not directly queryable (see incidents)."]
open(O+"S2-search-log.md","w").write("\n".join(L)+"\n")
S=[]
S.append("# S2 literature search - summary\n")
S.append("## PRISMA-style counts\n")
S.append("| Step | Count |\n|---|---|")
S.append(f"| Records identified, database queries (sum of retrieved over {len(rows)} queries) | {sum_retrieved} |")
S.append(f"| Records identified, web searches (arXiv ids returned) | {web_hits} |")
S.append(f"| Duplicates removed (cross-query and cross-database) | {dup} |")
S.append(f"| Unique papers screened at title/abstract | {len(papers)} |")
S.append(f"| Excluded at title/abstract | {s1_ex} |")
S.append(f"| Retained for full-text / data-release assessment | {s1_ret} |")
S.append(f"| Full-text assessed (papers; arXiv HTML or Zenodo record retrieved) | {len(ft)} |")
S.append(f"| Excluded at full text (papers) | {sum(1 for r in ft if r['decision']=='exclude')} |")
S.append(f"| Retained at stage 1 but not assessable (non-arXiv publisher pages) | {sum(1 for r in papers if r.get('stage1_retained') and r['stage']=='title_abstract')} |")
S.append(f"| Dataset-hub records added from Zenodo/Hugging Face dataset searches (curated, separate from paper screening) | {len(dsr)} |")
S.append(f"| **Included (papers + dataset records)** | **{len(inc)}** ({sum(1 for r in inc if r['record_type']=='paper')} papers, {sum(1 for r in inc if r['record_type']!='paper')} dataset records) |")
S.append(f"| of which security-topic | {sum(1 for r in inc if r['security_topic'])} |")
S.append(f"| of which AgentDojo uses/extends | {sum(1 for r in inc if r['relation_to_agentdojo'] in ('uses','extends'))} |")
S.append(f"| Qualifying logs but excluded by licence (none / custom-restrictive / ND) | {sum(1 for r in R if r.get('licence_excluded'))} |")
S.append(f"| Full-text records with `releases_logs=unclear` (manual follow-up) | {sum(1 for r in ft_all if r['releases_logs']=='unclear')} |")
S.append("\nAgentDojo ecosystem sizes: Semantic Scholar forward citations 152; OpenAlex cites 102 (proceedings id) + 7 (arXiv-DOI id); OpenAlex full-text mentions of 'AgentDojo' since 2024: 1,188; arXiv title/abstract mentions: 114. Relation of pooled papers to AgentDojo: "+", ".join(f"{k}={v}" for k,v in Counter(r['relation_to_agentdojo'] for r in papers).items())+".\n")
S.append("### Stage-1 exclusion reasons\n")
for k,v in Counter(r["exclusion_reason"] for r in R if r["stage"]=="title_abstract" and r["record_type"]=="paper").most_common(12): S.append(f"- {v}: {k}")
S.append("\n### Full-text exclusion reasons (top)\n")
for k,v in ftreasons.most_common(12): S.append(f"- {v}: {k}")
S.append("\n## Included sources (per-run logs/trajectories released openly, acceptable licence)\n")
S.append("Confidence: high = confirmed by API/HF/Zenodo file listing; medium = repository HTML tree or name-based inference; `-` = dataset record. Logs not downloaded or parsed.\n")
S.append("| id | title | AgentDojo | topic | log location | format | licence | licence source | conf |\n|---|---|---|---|---|---|---|---|---|")
for r in sorted(inc,key=lambda r:(not r["security_topic"], r["relation_to_agentdojo"]=="none", r["title"])): S.append(row_inc(r))
S.append("\n## Most promising NEW sources (not in the known list), security first\n")
newsrc=[r for r in inc if not r.get("known_already")]
sec=[r for r in newsrc if r["security_topic"]]
for r in sorted(sec,key=lambda r:(r["relation_to_agentdojo"]=="none", r["title"]))[:20]:
    S.append(f"- **{r['title'][:90]}** ({r['arxiv'] or r['id']}; AgentDojo: {r['relation_to_agentdojo']}; {r.get('licence')}) - {link(r)}")
S.append("\nAgentDojo-format run archives among them (best fit for the AgentDojo native-log adapter): 2601.04795 (qiang-yu/agentdojo `runs/`, 29 model directories), Zenodo 23138310 (agent-authority-caps, AgentDojo-layout `runs/`), Zenodo 21631031 (TELOS, 139 AgentDojo evaluations as JSONL). AgentDojo-derived HF dumps without a licence are excluded (see below).\n")
S.append("## Excluded because of licence (logs otherwise qualify)\n")
S.append("| id | title | licence | licence source | AgentDojo | log location |\n|---|---|---|---|---|---|")
for r in R:
    if r.get("licence_excluded"): S.append(f"| {r['arxiv'] or r['id']} | {r['title'][:70]} | {r['licence']} | {(r.get('licence_source') or '')[:90]} | {r['relation_to_agentdojo']} | {link(r)} |")
S.append("\n## Release status of the known sources (from this search)\n")
for ax in ["2602.03117","2608.27496","2506.12104","2606.15057","2602.16901","2607.05120","2509.25624","2410.09024","2410.02644"]:
    r=fb(ax)
    if r: S.append(f"- {r['known_already']} (arXiv:{ax}): decision={r['decision']}, releases_logs={r['releases_logs']}, licence={r.get('licence')}" + (f" - {r['exclusion_reason'][:110]}" if r['exclusion_reason'] else ""))
S.append("\n## Notes for the manuscript\n")
S+=["- The include list is dominated by 2026 preprints; maturity and peer-review status vary. Venue is recorded where an index provided one.","- `unclear` records (releases_logs=unclear, stage full_text) are follow-up candidates: release claimed or generic data directory, per-run logs not confirmed.","- Zenodo AgentDojo-PROV record 23276620 (published 2026-10-10) appears in Zenodo search; treated as a known/own source.","- Provenance-related survey found by web search: arXiv:2606.04990 'From Agent Traces to Trust: A Survey of Evidence Tracing and Execution Provenance in LLM Agents' (not a benchmark; relevant to related work)."]
open(O+"S2-summary.md","w").write("\n".join(S)+"\n")
print("written",len(inc),len(papers),dup)
