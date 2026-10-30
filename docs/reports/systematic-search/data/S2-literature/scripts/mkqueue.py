import json,re
pool=json.load(open("pool_s1.json")); p2=json.load(open("pass2_cache.json"))
byax={p["arxiv"]:p for p in pool.values() if p["arxiv"]}
STR=re.compile(r"trajector|\blogs?\b|traces?|transcripts?|rollouts?|episodes?|runs\b",re.I)
queue=[]
for i,v in p2.items():
    p=byax.get(i)
    if not p or p.get("s1_exclusion") or v.get("err"): continue
    f=p["flags"]; cls=[]
    if f["ad_abs"] or f["ad_cit"] or f["ad_ft"]: cls.append("AD")
    if "C_sec_bench_title" in p["stage1_rules"]: cls.append("SEC")
    if any(STR.search(s) for s in v.get("av_sents",[])) or (f["log"] and f["rel"]): cls.append("LOG")
    links=v.get("own_links",[])
    if not links and "AD" in cls: links=[l for l in p.get("probe_links",[]) if re.search(r"github\.com|huggingface|zenodo",l)][:3]
    if links and cls: queue.append((i,cls,links))
json.dump(queue,open("queue.json","w")); print(len(queue))
