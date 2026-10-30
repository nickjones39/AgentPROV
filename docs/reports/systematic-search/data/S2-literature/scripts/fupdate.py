import json,re
pool=json.load(open("pool_s1.json")); pc=json.load(open("probe_cache.json"))
DENY=re.compile(r"github\.com/(arXiv|brucemiller|ethz-spylab/agentdojo|openai/|huggingface/|microsoft/|langchain|meta-llama|anthropics/|vllm-project|pytorch|google-research|google-deepmind)|latexml",re.I)
F=set()
for k,p in pool.items():
    if p.get("s1_exclusion") or not p["arxiv"]: continue
    v=pc.get(p["arxiv"])
    if not v or v.get("err"): p["probe"]="error"; continue
    links=[l for l in v["links"] if not DENY.search(l)]
    p["probe_links"]=links; p["probe"]="links" if links else "nolinks"
    if links: F.add(p["arxiv"])
json.dump(sorted(F),open("F_ids.json","w")); json.dump(pool,open("pool_s1.json","w")); print(len(F))
