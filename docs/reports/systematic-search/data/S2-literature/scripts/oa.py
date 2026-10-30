import json, os, time, urllib.request, urllib.parse, datetime
OUT="~/.agentprov/migration-work/syssearch/S2-literature/raw/"
SEL="id,title,publication_year,doi,ids,primary_location,abstract_inverted_index,cited_by_count,type"
def get(url):
    for i in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"agentprov-litsearch/0.1 (mailto:"+os.environ.get("AGENTPROV_LITSEARCH_MAILTO","")+")"}),timeout=60) as r: return json.load(r)
        except Exception as e:
            print("retry",e); time.sleep(5)
    raise SystemExit
def abst(w):
    ii=w.pop("abstract_inverted_index",None)
    if not ii: w["abstract"]=None; return
    pos={}
    for k,v in ii.items():
        for p in v: pos[p]=k
    w["abstract"]=" ".join(pos[i] for i in sorted(pos))
def run(filt,name,search=None):
    res=[];cur="*"; t0=datetime.datetime.now(datetime.UTC).isoformat(); count=None
    while cur:
        q={"select":SEL,"per-page":"200","cursor":cur}
        if filt: q["filter"]=filt
        if search: q["search"]=search
        d=get("https://api.openalex.org/works?"+urllib.parse.urlencode(q))
        count=d["meta"]["count"]
        for w in d["results"]: abst(w); res.append(w)
        cur=d["meta"].get("next_cursor")
        if search and len(res)>=1000: break
    json.dump({"filter":filt,"search":search,"start_utc":t0,"count":count,"n":len(res),"results":res},open(OUT+name,"w"))
    print(name,count,len(res))
run("cites:W4415796822","oa_cites_W4415796822.json")
run("cites:W4399912700","oa_cites_W4399912700.json")
