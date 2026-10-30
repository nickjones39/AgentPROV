import sys,re,html,urllib.request,urllib.parse,json
def preview(zid,name):
    u=f"https://zenodo.org/records/{zid}/preview/{urllib.parse.quote(name)}"
    t=urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"agentprov-litsearch/0.1"}),timeout=60).read().decode("utf8","replace")
    txt=re.sub(r"<[^>]+>","\n",t); lines=[l.strip() for l in html.unescape(txt).splitlines() if l.strip()]
    return lines
if __name__=="__main__":
    zid,name=sys.argv[1],sys.argv[2]
    L=preview(zid,name)
    # print compact: dirs/files with sizes
    out=[]
    for l in L[3:]:
        out.append(l)
    print(" | ".join(out)[:2500])
