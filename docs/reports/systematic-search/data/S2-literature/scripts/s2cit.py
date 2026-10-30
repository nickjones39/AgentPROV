import json, time, urllib.request, urllib.error, sys, datetime
OUT="~/.agentprov/migration-work/syssearch/S2-literature/raw/"
base="https://api.semanticscholar.org/graph/v1/paper/arXiv:2406.13352/citations?fields=title,year,venue,externalIds,url,abstract,citationCount&limit=100&offset="
def get(url):
    for i in range(12):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"agentprov-litsearch/0.1 (academic; read-only)"}),timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(10+i*10); continue
            raise
    raise SystemExit("fail")
off=0; allr=[]; log=[]
start=datetime.datetime.utcnow().isoformat()
while True:
    d=get(base+str(off)); data=d.get("data",[]); allr+=data
    print(off,len(data),d.get("next"),flush=True)
    if "next" not in d or not data: break
    off=d["next"]; time.sleep(3)
json.dump({"query":base,"start_utc":start,"end_utc":datetime.datetime.utcnow().isoformat(),"n":len(allr),"data":allr},open(OUT+"s2_agentdojo_citations.json","w"))
print(len(allr))
