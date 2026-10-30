import json, time, urllib.request, urllib.parse, datetime, re, sys
import xml.etree.ElementTree as ET
OUT="~/.agentprov/migration-work/syssearch/S2-literature/raw/"
NS={"a":"http://www.w3.org/2005/Atom","o":"http://a9.com/-/spec/opensearch/1.1/"}
QS=[
 ("ax1",'all:"AgentDojo"'),
 ("ax2",'abs:"prompt injection" AND abs:agent AND abs:benchmark'),
 ("ax3",'abs:agent AND abs:trajectories AND abs:security'),
 ("ax4",'abs:"tool-use" AND abs:benchmark AND abs:logs'),
 ("ax5",'abs:"agent" AND abs:"benchmark" AND (abs:"trajectories" OR abs:"execution logs" OR abs:"traces") AND (abs:"released" OR abs:"open-source" OR abs:"publicly available")'),
 ("ax6",'abs:"indirect prompt injection" AND abs:agents'),
 ("ax7",'abs:"harmful" AND abs:agent AND abs:benchmark AND abs:"tool"'),
 ("ax8",'abs:"AgentDojo" OR ti:"AgentDojo"'),
]
meta={}
for name,q in QS:
    res=[];start=0;total=None;t0=datetime.datetime.now(datetime.UTC).isoformat()
    while True:
        url="http://export.arxiv.org/api/query?"+urllib.parse.urlencode({"search_query":q,"start":start,"max_results":200,"sortBy":"submittedDate","sortOrder":"descending"})
        for i in range(5):
            try:
                x=urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"agentprov-litsearch/0.1"}),timeout=90).read(); break
            except Exception as e: print("retry",e); time.sleep(10)
        r=ET.fromstring(x); total=int(r.find("o:totalResults",NS).text)
        es=r.findall("a:entry",NS)
        for e in es:
            g=lambda t:(e.find("a:"+t,NS).text or "").strip()
            res.append({"id":g("id").split("/abs/")[-1],"title":re.sub(r"\s+"," ",g("title")),"published":g("published"),"abstract":re.sub(r"\s+"," ",g("summary")),"cats":[c.get("term") for c in e.findall("a:category",NS)]})
        start+=len(es)
        time.sleep(3.5)
        if not es or start>=total or start>=1000: break
    json.dump({"query":q,"start_utc":t0,"totalResults":total,"n":len(res),"results":res},open(OUT+name+".json","w"))
    print(name,q,total,len(res),flush=True)
