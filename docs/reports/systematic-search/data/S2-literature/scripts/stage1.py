import json,re
pool=json.load(open("pool_flags.json"))
LLM=re.compile(r"(\bllms?\b|language model|large language|agentic|\bgpt|claude|gemini|foundation model|tool[- ](use|using|calling|call|integrated|augmented)|function[- ]calling|\bmcp\b|model context protocol|computer[- ]use|web agents?|coding agents?|ai agents?|autonomous agents?|multi-agent|llm-based)",re.I)
NOISE=re.compile(r"(uav|lidar|autonomous driving|vehicle|traffic|airport|drone|blockchain|v2x|quantum|power grid|medical image|trajectory prediction|physics|pybullet|multi-agent reinforcement|power system|drug design|lean 4|pedestrian|robot manipulation|ais vessel|satellite)",re.I)
out={}
for k,p in pool.items():
    t=((p["title"] or "")+" "+(p["abstract"] or ""))
    f=p["flags"]; why=None
    if p["year"] and p["year"]<2023: why="out of scope: published before 2023 (pre-LLM-agent era)"
    elif NOISE.search(p["title"] or "") : why="out of scope: non-LLM domain (title)"
    elif not LLM.search(t): why="out of scope: no LLM-agent signal in title/abstract"
    elif not p["stage1_rules"]:
        # ad-hoc: AgentDojo-cited papers without rules still go to stage 1 check on citation
        if f["ad_cit"] : p["stage1_rules"]=["D_cites_agentdojo"]
        else: why="screened out: no benchmark/dataset+log-release signal and no AgentDojo link in title/abstract"
    p["s1_exclusion"]=why
    out[k]=p
json.dump(out,open("pool_s1.json","w"))
from collections import Counter
print(Counter(p["s1_exclusion"] or "retained" for p in out.values()))
