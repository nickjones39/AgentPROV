import json,re
pool=json.load(open("pool_flags.json"))
TB=re.compile(r"(bench|dataset|corpus|arena|dojo|suite|testbed|gym|trajector)",re.I)
for k,p in pool.items():
    f=p["flags"]
    A=f["ag"] and f["bm"] and f["log"] and f["rel"]
    B=f["ad_abs"] and (f["bm"] or f["sec"])
    C=f["ag"] and f["sec"] and f["bm"] and bool(TB.search(p["title"] or ""))
    D=(f["ad_ft"] or f["ad_cit"]) and f["ag"]
    p["stage1_rules"]=[n for n,v in (("A_log_release",A),("B_agentdojo_abs",B),("C_sec_bench_title",C),("D_agentdojo_fulltext_or_citation",D)) if v]
json.dump(pool,open("pool_flags.json","w"))
