import json,re,subprocess,sys,urllib.request,urllib.error,os,time
C="verify_cache.json"
cache=json.load(open(C)) if os.path.exists(C) else {}
LOGPAT=re.compile(r"(^|/)(runs?|logs?|trajector\w*|traces?|transcripts?|rollouts?|episodes?|outputs?|results?|raw_?(data|outputs?)|conversations?|records?)(/|$)|\.eval$|(trajector|trace|transcript|rollout|episode|conversation)\w*\.(jsonl?|parquet|csv|gz|zip)$",re.I)
DATAEXT=re.compile(r"\.(jsonl?|parquet|csv|eval|gz|zip|tar|tgz|xz|zst|bz2|db|sqlite)$",re.I)
def gh(path):
    for a in range(4):
        time.sleep(0.8)
        r=subprocess.run(["gh","api",path],capture_output=True,text=True,timeout=120)
        if r.returncode and "rate limit" in r.stderr.lower(): time.sleep(30*(a+1)); continue
        break
    if r.returncode: return {"_err":r.stderr.strip()[:200]}
    return json.loads(r.stdout)
def verify_gh(o,r):
    k=f"gh:{o}/{r}"
    if k in cache: return cache[k]
    meta=gh(f"repos/{o}/{r}")
    if "_err" in meta: return {"err":meta["_err"]}
    t=gh(f"repos/{o}/{r}/git/trees/{meta['default_branch']}?recursive=1")
    files=[x for x in t.get("tree",[]) if x["type"]=="blob"]
    lf=[x for x in files if LOGPAT.search(x["path"]) and DATAEXT.search(x["path"])]
    lfs=[x for x in files if x["path"].endswith(".gitattributes")]
    dirs={}
    for x in lf:
        d="/".join(x["path"].split("/")[:2]); dirs.setdefault(d,[0,0]); dirs[d][0]+=1; dirs[d][1]+=x.get("size",0)
    top=sorted(dirs.items(),key=lambda kv:-kv[1][0])[:8]
    cache[k]={"url":f"https://github.com/{o}/{r}","license":(meta.get("license") or {}).get("spdx_id"),"archived":meta.get("archived"),"pushed":meta.get("pushed_at"),"size_kb":meta.get("size"),"n_files":len(files),"truncated":t.get("truncated"),"n_logish_files":len(lf),"logish_dirs":[(d,v[0],v[1]) for d,v in top],"sample":[x["path"] for x in lf[:5]],"stars":meta.get("stargazers_count")}
    return cache[k]
def hget(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"agentprov-litsearch/0.1"}),timeout=60) as r: return json.load(r)
    except urllib.error.HTTPError as e: return {"_err":e.code}
    except Exception as e: return {"_err":str(e)[:100]}
def verify_hf(kind,path):
    k=f"hf:{kind}/{path}"
    if k in cache: return cache[k]
    d=hget(f"https://huggingface.co/api/{kind}/{path}")
    if "_err" in d: cache[k]={"err":d["_err"]}; return cache[k]
    sib=[s["rfilename"] for s in d.get("siblings",[])]
    cd=d.get("cardData") or {}
    cache[k]={"url":f"https://huggingface.co/{kind}/{path}","license":cd.get("license") or [t for t in d.get("tags",[]) if t.startswith("license:")],"gated":d.get("gated"),"private":d.get("private"),"n_files":len(sib),"files":sib[:15],"downloads":d.get("downloads"),"lastModified":d.get("lastModified")}
    return cache[k]
def verify_zen(rid):
    k=f"zen:{rid}"
    if k in cache: return cache[k]
    d=hget(f"https://zenodo.org/api/records/{rid}")
    if "_err" in d: cache[k]={"err":d["_err"]}; return cache[k]
    m=d.get("metadata",{})
    cache[k]={"url":f"https://zenodo.org/records/{rid}","title":m.get("title"),"license":(m.get("license") or {}).get("id"),"access":m.get("access_right"),"files":[(f["key"],f["size"]) for f in d.get("files",[])][:15],"n_files":len(d.get("files",[]))}
    return cache[k]
def verify(link):
    m=re.match(r"github\.com/([\w.-]+)/([\w.-]+)",link.split("://")[-1])
    if m: return verify_gh(m.group(1),re.sub(r"\.git$","",m.group(2)))
    m=re.match(r"huggingface\.co/(datasets|spaces)/([\w.-]+/[\w.-]+)",link.split("://")[-1])
    if m: return verify_hf(m.group(1),m.group(2))
    m=re.search(r"zenodo\.org/(?:records?|doi)/(?:10\.5281/zenodo\.)?(\d+)",link)
    if m: return verify_zen(m.group(1))
    m=re.search(r"10\.5281/zenodo\.(\d+)",link)
    if m: return verify_zen(m.group(1))
    return {"note":"unverified host","url":link}
if __name__=="__main__":
    for l in sys.argv[1:]:
        print(l, json.dumps(verify(l),indent=1)[:1500])
    json.dump(cache,open(C,"w"))
