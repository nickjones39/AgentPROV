import json, time, urllib.request, urllib.error, urllib.parse, datetime
OUT="~/.agentprov/migration-work/syssearch/S2-literature/raw/"
QS=[("s2k2","prompt injection benchmark LLM agents tool use"),("s2k3","agent security benchmark execution trajectories released"),("s2k4","LLM agent benchmark tool misuse harmful behavior"),("s2k5","agent benchmark released trajectories logs dataset")]
F="title,year,venue,externalIds,url,abstract,citationCount,openAccessPdf"
def get(url):
    for i in range(80):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"agentprov-litsearch/0.1"}),timeout=60) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(45); continue
            raise
    raise SystemExit("fail")
for name,q in QS:
    t0=datetime.datetime.now(datetime.UTC).isoformat(); res=[]; off=0; total=None
    while off<200:
        d=get("https://api.semanticscholar.org/graph/v1/paper/search?"+urllib.parse.urlencode({"query":q,"fields":F,"limit":100,"offset":off}))
        total=d.get("total"); res+=d.get("data",[]); print(name,off,len(d.get("data",[])),total,flush=True)
        json.dump({"query":q,"start_utc":t0,"total":total,"n":len(res),"results":res,"note":"first 200 by relevance"},open(OUT+name+".json","w"))
        if "next" not in d: break
        off=d["next"]; time.sleep(8)
    time.sleep(8)
