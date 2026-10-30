import json,re,time,urllib.request,urllib.error,os,sys
C="ghweb_cache2.json"
cache=json.load(open(C)) if os.path.exists(C) else {}
LOGDIR=re.compile(r"^(runs?|logs?|data|datasets?|results?|trajector\w*|traces?|transcripts?|episodes?|outputs?|raw\w*|experiments?|artifacts?|evaluations?|eval\w*|records?|rollouts?|conversations?|benchmark\w*|release\w*|samples?)$",re.I)
def lst(o,r,path=""):
    u=f"https://github.com/{o}/{r}/tree/HEAD/{path}".rstrip("/")
    for a in range(3):
        try:
            t=urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0 (agentprov-litsearch/0.1 research)"}),timeout=40).read().decode("utf8","replace"); break
        except urllib.error.HTTPError as e:
            if e.code==404: return None
            if e.code==429: time.sleep(60); continue
            return None
        except Exception: time.sleep(5)
    else: return None
    m=re.search(r'"items":(\[.*?\]),"totalCount":(\d+)',t)
    if not m: return None
    try: items=json.loads(m.group(1))
    except Exception: return None
    return {"items":[(i["name"],i["contentType"]) for i in items],"total":int(m.group(2))}
def survey(o,r):
    k=f"{o}/{r}".lower()
    if k in cache: return cache[k]
    top=lst(o,r); time.sleep(1.0)
    if top is None: cache[k]={"err":"not reachable/404"}; return cache[k]
    res={"url":f"https://github.com/{o}/{r}","top":top["items"][:40],"dirs":{}}
    n=0
    for nm,ct in top["items"]:
        if ct=="directory" and LOGDIR.match(nm) and n<4:
            sub=lst(o,r,nm); time.sleep(1.0); n+=1
            if sub:
                res["dirs"][nm]={"total":sub["total"],"items":sub["items"][:14]}
                # one deeper for first 2 sub-directories
                for sn,sct in sub["items"][:2]:
                    if sct=="directory":
                        s2=lst(o,r,nm+"/"+sn); time.sleep(1.0)
                        if s2: res["dirs"][nm+"/"+sn]={"total":s2["total"],"items":s2["items"][:10]}
    cache[k]=res; return res
if __name__=="__main__":
    queue=json.load(open("queue.json"))
    prio=lambda c:(0 if "AD" in c else 1 if "SEC" in c else 2)
    queue.sort(key=lambda q:(prio(q[1]),-len(q[1])))
    if len(sys.argv)>1 and sys.argv[1]=="rev": queue=queue[::-1]
    n=0
    for i,c,links in queue:
        for u in links:
            m=re.search(r"github\.com/([\w.-]+)/([\w.-]+)",u)
            if m:
                survey(m.group(1),re.sub(r"\.git$","",m.group(2))); n+=1
                if n%10==0: json.dump(cache,open(C,"w")); print(n,flush=True)
    json.dump(cache,open(C,"w")); print("done",n)
