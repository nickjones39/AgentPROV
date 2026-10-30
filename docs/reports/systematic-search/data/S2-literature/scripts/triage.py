import json,re
from collections import Counter
pool=json.load(open("pool.json"))
def T(p): return ((p["title"] or "")+" "+(p["abstract"] or "")).lower()
AG=re.compile(r"\b(llm[- ]agents?|agents?|agentic|tool[- ]use|tool[- ]calling|function[- ]calling|computer[- ]use|mcp)\b")
BM=re.compile(r"\b(benchmark|bench|dataset|testbed|suite|evaluation|environment|corpus|arena)\b")
SEC=re.compile(r"(prompt injection|injection|jailbreak|harm|misuse|safety|malicious|adversarial|red[- ]team|attack|security|risk|unsafe|backdoor|poison)")
LOG=re.compile(r"(trajector|execution logs?|\blogs\b|\btraces?\b|transcripts?|rollouts?|run logs?|interaction logs?|tool[- ]call logs?)")
REL=re.compile(r"(release|open[- ]source|publicly available|made available|we (publish|share|provide)|available at|github|hugging ?face|zenodo)")
AD=re.compile(r"agentdojo|agent dojo")
rows=[]
for k,p in pool.items():
    t=T(p); s=p["sources"]
    ad_abs=bool(AD.search(t)); ad_cit=any(x in ("S2-cit","OA-cites_W4415796822","OA-cites_W4399912700") for x in s); ad_ft=any("fulltext" in x for x in s)
    p["flags"]={"ag":bool(AG.search(t)),"bm":bool(BM.search(t)),"sec":bool(SEC.search(t)),"log":bool(LOG.search(t)),"rel":bool(REL.search(t)),"ad_abs":ad_abs,"ad_cit":ad_cit,"ad_ft":ad_ft}
    rows.append(p)
json.dump(pool,open("pool_flags.json","w"))
c=Counter()
for p in rows:
    f=p["flags"]
    c["total"]+=1
    if f["ag"]: c["agent"]+=1
    if f["ag"] and f["bm"]: c["agent+bm"]+=1
    if f["ag"] and f["bm"] and f["sec"]: c["agent+bm+sec"]+=1
    if f["ag"] and f["log"]: c["agent+log"]+=1
    if f["ag"] and f["log"] and f["rel"]: c["agent+log+rel"]+=1
    if f["ad_abs"]: c["ad_abs"]+=1
    if f["ad_cit"]: c["ad_cit"]+=1
    if f["ad_ft"]: c["ad_ft"]+=1
    if not p["abstract"]: c["noabs"]+=1
print(c)
