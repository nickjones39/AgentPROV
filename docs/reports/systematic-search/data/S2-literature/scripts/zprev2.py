import sys,re,html,urllib.request,urllib.parse
zid,name=sys.argv[1],sys.argv[2]
u=f"https://zenodo.org/records/{zid}/preview/{urllib.parse.quote(name)}"
t=urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"agentprov-litsearch/0.1"}),timeout=60).read().decode("utf8","replace")
txt=re.sub(r"<[^>]+>","\n",t); L=[l.strip() for l in html.unescape(txt).splitlines() if l.strip()]
print(len(L)); print(" | ".join(L[2:int(sys.argv[3]) if len(sys.argv)>3 else 160])[:3000])
