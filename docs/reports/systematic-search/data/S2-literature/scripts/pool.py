import json,glob,re,os
O="~/.agentprov/migration-work/syssearch/S2-literature/raw/"
pool={}
def nt(t): return re.sub(r"[^a-z0-9]+"," ",(t or "").lower()).strip()
def key(ax,title):
    return ("arxiv:"+ax) if ax else ("t:"+nt(title))
def add(src,title,year,ax=None,doi=None,venue=None,abstract=None,url=None,cites=None,sid=None):
    if not title: return
    ax=re.sub(r"v\d+$","",ax) if ax else None
    if not ax and doi:
        m=re.match(r"(?:https://doi.org/)?10\.48550/arxiv\.(.+)",doi,re.I)
        if m: ax=m.group(1)
    k=key(ax,title)
    # merge by title if arxiv key not present but title key is
    tk="t:"+nt(title)
    if k not in pool and tk in pool and ax: pool[k]=pool.pop(tk)
    if k not in pool and ax is None:
        # find by title in arxiv-keyed
        for kk,v in pool.items():
            if nt(v["title"])==nt(title): k=kk;break
    p=pool.setdefault(k,{"title":re.sub(r"\s+"," ",title),"year":year,"arxiv":ax,"doi":None,"venue":None,"abstract":None,"url":None,"sources":[],"cites":None})
    if ax and not p["arxiv"]: p["arxiv"]=ax
    if doi and not p["doi"]: p["doi"]=doi.replace("https://doi.org/","")
    if venue and not p["venue"]: p["venue"]=venue
    if abstract and not p["abstract"]: p["abstract"]=abstract
    if url and not p["url"]: p["url"]=url
    if year and not p["year"]: p["year"]=year
    if cites is not None: p["cites"]=cites
    if src not in p["sources"]: p["sources"].append(src)
d=json.load(open(O+"s2_agentdojo_citations.json"))
for x in d["data"]:
    c=x["citingPaper"]; e=c.get("externalIds") or {}
    add("S2-cit",c["title"],c.get("year"),e.get("ArXiv"),e.get("DOI"),c.get("venue"),c.get("abstract"),c.get("url"),c.get("citationCount"))
for f in glob.glob(O+"s2k*.json"):
    d=json.load(open(f)); n=os.path.basename(f)[:-5]
    for c in d["results"]:
        e=c.get("externalIds") or {}
        add("S2-"+n,c["title"],c.get("year"),e.get("ArXiv"),e.get("DOI"),c.get("venue"),c.get("abstract"),c.get("url"),c.get("citationCount"))
for f in glob.glob(O+"oa_*.json"):
    d=json.load(open(f)); n=os.path.basename(f)[:-5]
    for w in d["results"]:
        pl=w.get("primary_location") or {}
        add("OA-"+n[3:],w["title"],w.get("publication_year"),None,w.get("doi"),(pl.get("source") or {}).get("display_name"),w.get("abstract"),w.get("id"),w.get("cited_by_count"))
for f in glob.glob(O+"ax*.json"):
    d=json.load(open(f)); n=os.path.basename(f)[:-5]
    for w in d["results"]:
        add("arXiv-"+n,w["title"],int(w["published"][:4]),w["id"],None,None,w["abstract"],"https://arxiv.org/abs/"+w["id"])
d=json.load(open(O+"or_queries.json"))
for t,v in d.items():
    for fo in v["forums"]:
        add("OR-"+t[:12].replace(" ","_"),fo["title"],None,None,None,fo["venue"],fo["abstract"],"https://openreview.net/forum?id="+fo["forum"])
for f in [x for x in glob.glob(O+"hf_*.json") if "dataset_checks" not in x]:
    for w in json.load(open(f)):
        p=w["paper"]; add("HF-"+os.path.basename(f)[3:-5],p.get("title") or w.get("title"),int(p.get("publishedAt","0000")[:4] or 0) if p.get("publishedAt") else None,p["id"],None,None,p.get("summary"),"https://huggingface.co/papers/"+p["id"])
ws=json.load(open("websearch_ids.json")); wn=json.load(open("ws_new.json"))
for q,ids in ws.items():
    for i in ids:
        k="arxiv:"+i
        if k not in pool and i in wn:
            add("WEB",wn[i]["title"],wn[i]["year"],i,None,None,wn[i]["abstract"],"https://arxiv.org/abs/"+i)
        if k in pool and ("WEB:"+q) not in pool[k]["sources"]: pool[k]["sources"].append("WEB:"+q)
json.dump(pool,open("pool.json","w"))
print(len(pool))
from collections import Counter
c=Counter(s for p in pool.values() for s in p["sources"]); print(c)
