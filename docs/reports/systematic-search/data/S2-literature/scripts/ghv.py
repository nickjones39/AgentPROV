import json,re,subprocess,urllib.request,urllib.error,os,time,sys
C="ghv_cache.json"
cache=json.load(open(C)) if os.path.exists(C) else {}
LOGPAT=re.compile(r"(^|/)(runs?|logs?|trajector\w*|traces?|transcripts?|rollouts?|episodes?|outputs?|results?|raw_?(data|outputs?)|conversations?|records?|data|dataset|datasets|eval_?results?)(/|$)|\.eval$|(trajector|trace|transcript|rollout|episode|conversation)\w*\.(jsonl?|parquet|csv|gz|zip)$",re.I)
DATAEXT=re.compile(r"\.(jsonl?|parquet|csv|eval|gz|zip|tar|tgz|xz|zst|bz2|db|sqlite|pkl|pickle|txt)$",re.I)
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"agentprov-litsearch/0.1"}),timeout=60) as r: return r.read().decode("utf8","replace"),r.status
    except urllib.error.HTTPError as e: return None,e.code
    except Exception as e: return None,str(e)[:60]
def verify(o,r):
    k=f"{o}/{r}".lower()
    if k in cache: return cache[k]
    txt,st=get(f"https://api.github.com/repos/{o}/{r}/git/trees/HEAD?recursive=1")
    if txt is None:
        if st in (403,429): return {"err":"unauth rate limit"}
        res={"url":f"https://github.com/{o}/{r}","err":f"tree {st}"}; cache[k]=res; return res
    t=json.loads(txt); files=[x for x in t.get("tree",[]) if x["type"]=="blob"]
    lf=[x for x in files if LOGPAT.search(x["path"]) and DATAEXT.search(x["path"])]
    dirs={}
    for x in lf:
        d="/".join(x["path"].split("/")[:2]); a=dirs.setdefault(d,[0,0]); a[0]+=1; a[1]+=x.get("size",0)
    top=sorted(dirs.items(),key=lambda kv:-kv[1][0])[:8]
    lic=None
    for nm in ("LICENSE","LICENSE.md","LICENSE.txt"):
        if any(x["path"]==nm for x in files):
            tx,_=get(f"https://raw.githubusercontent.com/{o}/{r}/HEAD/{nm}")
            if tx: lic=tx.strip().splitlines()[0][:80]
            break
    res={"url":f"https://github.com/{o}/{r}","n_files":len(files),"truncated":t.get("truncated"),"n_dataish":len(lf),"dataish_dirs":[(d,v[0],v[1]) for d,v in top],"sample":[x["path"] for x in lf[:4]],"licence_line":lic,"top_level":sorted({x["path"].split("/")[0] for x in t.get("tree",[])})[:25]}
    cache[k]=res; json.dump(cache,open(C,"w")); return res
if __name__=="__main__":
    for a in sys.argv[1:]:
        m=re.search(r"github\.com/([\w.-]+)/([\w.-]+)",a); o,r=m.group(1),re.sub(r"\.git$","",m.group(2))
        print(a,json.dumps(verify(o,r))[:1100]); time.sleep(1)
