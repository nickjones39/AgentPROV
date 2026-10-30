import json,re,subprocess,time,sys,os
import ghv
from verify_links import verify_hf,verify_zen,cache as vcache
queue=json.load(open("queue.json"))
prio=lambda c:(0 if "AD" in c else 1 if "SEC" in c else 2)
queue.sort(key=lambda q:(prio(q[1]), -len(q[1])))
def gh_tree(o,r):
    k=f"{o}/{r}".lower()
    if k in ghv.cache: return ghv.cache[k]
    # authed first
    for attempt in range(40):
        p=subprocess.run(["gh","api",f"repos/{o}/{r}/git/trees/HEAD?recursive=1"],capture_output=True,text=True,timeout=120)
        if p.returncode==0:
            t=json.loads(p.stdout); return fin(o,r,t)
        err=p.stderr+p.stdout
        if "rate limit" in err.lower():
            res=ghv.verify(o,r)   # unauth fallback
            if "err" in res and res["err"]=="unauth rate limit":
                time.sleep(120); continue
            return res
        if "404" in err or "409" in err or "Not Found" in err or "empty" in err.lower():
            res={"url":f"https://github.com/{o}/{r}","err":"not found/empty (404/409)"}; ghv.cache[k]=res; json.dump(ghv.cache,open(ghv.C,"w")); return res
        time.sleep(5)
    return {"err":"gave up"}
def fin(o,r,t):
    k=f"{o}/{r}".lower()
    files=[x for x in t.get("tree",[]) if x["type"]=="blob"]
    lf=[x for x in files if ghv.LOGPAT.search(x["path"]) and ghv.DATAEXT.search(x["path"])]
    dirs={}
    for x in lf:
        d="/".join(x["path"].split("/")[:2]); a=dirs.setdefault(d,[0,0]); a[0]+=1; a[1]+=x.get("size",0)
    top=sorted(dirs.items(),key=lambda kv:-kv[1][0])[:8]
    lic=None
    for nm in ("LICENSE","LICENSE.md","LICENSE.txt","LICENCE"):
        if any(x["path"]==nm for x in files):
            tx,_=ghv.get(f"https://raw.githubusercontent.com/{o}/{r}/HEAD/{nm}")
            if tx: lic=tx.strip().splitlines()[0][:80]
            break
    res={"url":f"https://github.com/{o}/{r}","n_files":len(files),"truncated":t.get("truncated"),"n_dataish":len(lf),"dataish_dirs":[(d,v[0],v[1]) for d,v in top],"sample":[x["path"] for x in lf[:4]],"licence_line":lic,"top_level":sorted({x["path"].split("/")[0] for x in t.get("tree",[])})[:25]}
    ghv.cache[k]=res; json.dump(ghv.cache,open(ghv.C,"w")); return res
n=0
for i,c,links in queue:
    for u in links:
        m=re.search(r"github\.com/([\w.-]+)/([\w.-]+)",u)
        if m:
            gh_tree(m.group(1).lower(),re.sub(r"\.git$","",m.group(2)).lower()); n+=1
        m=re.search(r"huggingface\.co/datasets/([\w.-]+/[\w.-]+)",u)
        if m: verify_hf("datasets",m.group(1))
        m=re.search(r"zenodo\.(\d+)",u) or re.search(r"zenodo\.org/records?/(\d+)",u)
        if m: verify_zen(m.group(1))
    if n%10==0: json.dump(vcache,open("verify_cache.json","w")); print(i,n,flush=True)
json.dump(vcache,open("verify_cache.json","w")); print("done",n)
