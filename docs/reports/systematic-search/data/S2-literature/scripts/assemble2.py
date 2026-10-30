exec(open("assemble.py").read())
MANUAL={ # arxiv: (releases_logs, decision, reason)  -- manual review of automatic 'include' calls (directory-name evidence only)
 "2603.03543":("no","exclude","manual review: Tucano 2 is a Portuguese language-model release, not an LLM-agent benchmark/evaluation (non-agent LLM eval)"),
 "2609.20625":("no","exclude","manual review: the traces are test fixtures (26 small files) of a regression-testing tool, not benchmark run logs"),
 "2605.16626":("unclear","exclude","manual review: SLEIGHT-Bench repo is evaluation code; the HF dataset listed was not confirmed to hold per-run agent logs"),
 "2605.08442":("unclear","exclude","manual review: data/ holds attack documents and fixtures; per-run outputs not confirmed in results/"),
 "2609.21386":("unclear","exclude","manual review: video-QA benchmark; evidence of per-run agent logs not confirmed"),
 "2607.24882":("unclear","exclude","manual review: data/eval holds evaluation reports; per-run agent logs not confirmed"),
 "2510.15144":("unclear","exclude","manual review: human-simulation benchmark data and result tables, not agent execution logs"),
 "2604.26653":("no","exclude","manual review: simulated agent-trace corpus (search sessions) for IR research; simulated-only data"),
 "2609.10892":("no","exclude","manual review: DriftNet is a follow-up detector trained on the AgentDrift corpus released with 2609.06972; no separate release of logs"),
 "2608.16393":("unclear","exclude","manual review: repository is a security-scanner tool (data/eval = prompts and skills); per-run agent logs not confirmed"),
 "2609.11024":("unclear","exclude","manual review: repository is a security-scanner tool (data/eval = prompts and skills); per-run agent logs not confirmed"),
 "2609.36817":("unclear","exclude","manual review: repository is a security-scanner tool (data/eval = prompts and skills); per-run agent logs not confirmed"),
 "2607.14541":("unclear","exclude","manual review: evidence is a GPU-kernel wiki directory, not run logs"),
 "2604.14709":("unclear","exclude","manual review: only vendored dependency files matched; per-run trajectories not confirmed"),
 "2609.24165":("unclear","exclude","manual review: benchmark/results holds 13 aggregate result files; per-run traces not confirmed"),
 "2606.18829":("unclear","exclude","manual review: bench/data is benchmark input data (8 files), not run logs"),
}
PROMOTE={"2604.02022":"manual review: HF dataset AI45Research/ATBench holds ATBench/test.json (1,000 agent trajectories per the abstract); listing is file-name based"}
for r in records:
    if r.get("arxiv") in PROMOTE and r["decision"]=="exclude" and r.get("licence") not in (None,"none","custom-restrictive"):
        r["releases_logs"]="yes"; r["decision"]="include"; r["exclusion_reason"]=None; r["manual_review"]=PROMOTE[r["arxiv"]]; r["evidence_confidence"]="medium"
for r in records:
    if r.get("arxiv") in MANUAL and r["decision"]=="include":
        rl,dc,why=MANUAL[r["arxiv"]]; r["releases_logs"]=rl; r["decision"]=dc; r["exclusion_reason"]=why; r["manual_review"]=True
# ---------- dataset-hub records (Zenodo / HF dataset search; not papers) ----------
zq=json.load(open(O+"raw/zenodo_queries.json"))
zrec={}
for qn,v in zq.items():
    for r in v["records"]:
        zrec.setdefault(r["id"],{**r,"found_in":[]})["found_in"].append("Zenodo-"+qn)
# curated judgement from record description / file list (no archive downloaded)
ZJ={ # id: (releases_logs, relation, benchmark/study, format, reason_if_not_yes, security)
 23138310:("yes","uses","agent-authority-caps (AgentDojo mock environments)",["json (AgentDojo runs/ layout)","csv"],None,True),
 21631031:("yes","uses","TELOS evidence (139 AgentDojo evaluations)",["jsonl"],None,True),
 20034379:("yes","none","CUA-HandCrafted Browser Benchmark",["json (per-episode)","zip"],None,True),
 23084446:("yes","none","AstroAgentBench",["tar.zst"],None,False),
 22151975:("yes","none","BixBench audit trajectories",["json","jsonl"],None,False),
 23247488:("yes","none","InterCode-CTF / NYU CTF trajectories",["zip"],None,True),
 21895484:("unclear","uses","Trace Sufficiency (984-case AgentDojo execution layer)",["zip"],"described as execution-pipeline traces derived from AgentDojo; archive holds normalised records, per-run native logs not confirmed",True),
 22529663:("unclear","none","Agentic Action Boundary (InjectSim)",["zip (per-episode JSON)"],"1,851 per-episode result records on synthetic clinical/injection environments; message-level trajectories not confirmed",True),
 22011266:("unclear","uses","IPI defences replication package (AgentDojo)",["zip"],"described as data and traces; archive contents not machine-verified",True),
 21944598:("unclear","none","What surrounds an injection (1,334 trials)",["zip"],"trial data in one zip; per-run logs not confirmed",True),
 23235225:("unclear","none","IPI in bounded OT monitoring",["zip"],"raw agent and arbiter logs described; archive contents not machine-verified; synthetic OT telemetry",True),
 23025259:("unclear","none","AutoGen guard placement",["zip"],"raw per-phase run logs described; contents not machine-verified; guard probe set rather than agent benchmark",True),
 22010471:("unclear","none","Signed to Stop (per-trial data)",["zip"],"per-trial data described; contents not machine-verified",True),
 22895043:("unclear","uses","mastyf evidence bundle",["zip"],"evidence bundle; per-run logs not confirmed",True),
 23218779:("unclear","none","SEAgent artefact (ACSAC 2026)",["zip"],"experimental records inside a 238 MB artefact; contents not machine-verified",True),
 22140262:("no","none","Reproduction artefact: agentic LLM security benchmarks for education",["zip"],"tool assessment results and scripts; not agent-run trajectories",True),
 23250885:("no","uses","AgentGuard-ZT dataset",["zip (3 KB)"],"3 KB archive of aggregate per-configuration outcomes (210 evaluations); no messages/tool calls",True),
 22217485:("no","uses","AgentDojo Trace Audit",["whl","zip"],"software layer that audits a frozen AgentDojo v1.2.1 corpus; does not itself release the run logs",True),
 17458493:("no","uses","ethz-spylab/agentdojo v0.1.35 archive",["zip"],"software snapshot (known source: AgentDojo); runs/ handled in source report",True),
 23276620:("yes","uses","AgentDojo-PROV W3C PROV-O corpora",["zip parts"],None,True),
}
KNOWNZ={23276620:"AgentDojo-PROV",17458493:"AgentDojo (software archive)"}
for zid,v in ZJ.items():
    z=zrec.get(zid)
    if not z:
        # may be present only as pool Zenodo DOI; still fetch minimal record
        continue
    rl,rel,bn,fm,why,sec=v
    r={"id":f"zenodo:{zid}","title":z["title"],"year":int(z["date"][:4]) if z.get("date") else None,"venue":"Zenodo","doi":z.get("doi"),"arxiv":None,"url":f"https://zenodo.org/records/{zid}","relation_to_agentdojo":rel,"benchmark_name":bn,"security_topic":sec,"found_in":z["found_in"],"known_already":KNOWNZ.get(zid),"record_type":"dataset-record","releases_logs":rl,"log_location_urls":[f"https://zenodo.org/records/{zid}"],"format":fm,"decision":"include" if rl=="yes" else "exclude","exclusion_reason":None if rl=="yes" else why,"stage":"full_text","evidence":{"zenodo_files":z["files"][:6],"description":re.sub(r"\\s+"," ",re.sub(r"<[^>]+>"," ",z["desc"]))[:300]}}
    if zid in (23276620,17458493): r["decision"]="exclude"; r["exclusion_reason"]="known source (own / upstream), not a new finding"
    apply_licence(r); records.append(r)
# HF dataset records
hfc=json.load(open(O+"raw/hf_dataset_checks.json"))
HJ={ # id: (releases_logs, relation, bn, reason)
 "sungjuncho/agentdojo-trajectories":("yes","uses","AgentDojo trajectories (Gemma-4/Qwen3.5 runs)",None),
 "tomciotomcio/agentdojo-trajectories":("yes","uses","AgentDojo trajectories (mirror of sungjuncho)",None),
 "aksh-n/control_arena_agentdojo-monitor-labels":("yes","uses","ControlArena AgentDojo monitor judge logs",None),
 "ffuuugor/agentdojo-dump":("unclear","uses","AgentDojo dump (parquet)","parquet dump, no README; contents/provenance not documented"),
 "Junzj/agentdojo-dump":("unclear","uses","AgentDojo dump (parquet)","parquet dump, no README; contents/provenance not documented"),
 "adityaasinha28/control_arena_agentdojo":("unclear","uses","ControlArena AgentDojo (parquet)","single parquet, no README"),
 "Genteki/agentdojo_tiny":("no","uses","agentdojo_tiny","tiny dataset.json, no documentation"),
 "Jinming2002/drift-agentdojo-slim":("no","uses","DRIFT AgentDojo slim docker release","Docker images/scripts to run DRIFT+AgentDojo; no run logs"),
 "tuandunghcmut/trustsight-agentdojo":("unclear","uses","TrustSight AgentDojo security suite","parquet per-suite; appears to be task/test-case data rather than run logs"),
 "AI-Secure/DTap-Bench-Agent-Trajectories":("yes","none","DecodingTrust-Agent Platform (DTap-Bench) trajectories",None),
 "SecureAI-SE/fuzz-agent-trajectories":("unclear","none","Agentic web-API fuzzing trajectories","trajectory corpus for training/verification of a fuzzing agent; not a benchmark evaluation of agents"),
 "Lakera/b3-agent-security-benchmark-weak":("no","none","b3 backbone breaker benchmark","threat snapshots and attack prompts; no agent run logs"),
}
for did,(rl,rel,bn,why) in HJ.items():
    c=hfc.get(did,{})
    r={"id":f"hf-dataset:{did}","title":did,"year":int(c["modified"][:4]) if c.get("modified") else None,"venue":"Hugging Face Datasets","doi":None,"arxiv":None,"url":f"https://huggingface.co/datasets/{did}","relation_to_agentdojo":rel,"benchmark_name":bn,"security_topic":True,"found_in":["HF-datasets-search"],"known_already":None,"record_type":"dataset-record","releases_logs":rl,"log_location_urls":[f"https://huggingface.co/datasets/{did}"],"format":sorted({os.path.splitext(f)[1].lstrip('.') for f in c.get("files",[]) if '.' in f}),"decision":"include" if rl=="yes" else "exclude","exclusion_reason":why,"stage":"full_text","evidence":{"n_files":c.get("n_files"),"files":c.get("files",[])[:4]}}
    if did=="Jinming2002/drift-agentdojo-slim": r["known_already"]="DRIFT (related release)"
    apply_licence(r); records.append(r)
# changdae (private/401) - record without licence check
records.append({"id":"hf-dataset:changdae/agentdojo-trajectories-qwen35-gemma4","title":"changdae/agentdojo-trajectories-qwen35-gemma4","year":2026,"venue":"Hugging Face Datasets","doi":None,"arxiv":None,"url":"https://huggingface.co/datasets/changdae/agentdojo-trajectories-qwen35-gemma4","relation_to_agentdojo":"uses","benchmark_name":"AgentDojo trajectories (Qwen3.5-9B, Gemma-4-E4B)","security_topic":True,"found_in":["WEB:dataset of agent trajectories prompt injection released HF AgentDojo runs logs"],"known_already":None,"record_type":"dataset-record","releases_logs":"unclear","log_location_urls":[],"format":[],"decision":"exclude","exclusion_reason":"dataset page returned in web search but HF API returns 401 (private, gated or removed); cannot verify files or licence","licence":"unknown","licence_source":"HF API 401; dataset card not retrievable","stage":"full_text"})
for r in records:
    r.setdefault("record_type","paper")
    if r["record_type"]=="paper": r.setdefault("licence_source",None)
json.dump(records,open("records_final.json","w"))
print(len(records))
from collections import Counter
print(Counter((r["stage"],r["decision"]) for r in records))
print(Counter(r["releases_logs"] for r in records if r["stage"]=="full_text"))
print(Counter(r.get("licence") for r in records if r["decision"]=="include"))
