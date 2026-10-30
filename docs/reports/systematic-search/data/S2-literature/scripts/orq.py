import json, time, urllib.request, urllib.parse, datetime
O="~/.agentprov/migration-work/syssearch/S2-literature/raw/"
TERMS=["AgentDojo","prompt injection agent benchmark","agent security benchmark","agent trajectories released benchmark tool use"]
out={}
for t in TERMS:
    t0=datetime.datetime.now(datetime.UTC).isoformat(); notes=[]; off=0
    while off<1000:
        u="https://api2.openreview.net/notes/search?"+urllib.parse.urlencode({"term":t,"limit":1000,"offset":off,"source":"all"})
        d=json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"agentprov-litsearch/0.1"}),timeout=90))
        notes+=d["notes"]; 
        if len(d["notes"])<1000: break
        off+=1000
    forums={}
    for n in notes:
        f=n["forum"]; fc=n.get("forumContent") or {}
        ti=(fc.get("title") or {}).get("value"); ab=(fc.get("abstract") or {}).get("value")
        v=(fc.get("venue") or {}).get("value") or ""
        if f not in forums: forums[f]={"forum":f,"title":ti,"abstract":ab,"venue":v,"domain":n.get("domain"),"n_notes":0}
        forums[f]["n_notes"]+=1
    out[t]={"start_utc":t0,"count_reported":d.get("count"),"notes_returned":len(notes),"forums":list(forums.values())}
    print(t,d.get("count"),len(notes),len(forums),flush=True); time.sleep(2)
json.dump(out,open(O+"or_queries.json","w"))
