import json,re,time,urllib.request,os,html
from concurrent.futures import ThreadPoolExecutor
import threading
C="pass2s_cache.json"
cache=json.load(open(C)) if os.path.exists(C) else {}
ids=json.load(open("F_ids.json")); pool=json.load(open("pool_s1.json"))
byax={p["arxiv"]:p for p in pool.values() if p["arxiv"]}
HOST=re.compile(r"(github\.com/[\w.-]+/[\w.-]+|huggingface\.co/datasets/[\w.-]+/[\w.-]+|huggingface\.co/[\w.-]+/[\w.-]+|zenodo\.org/(records?|doi)/[\w./-]+|doi\.org/10\.5281/[\w./-]+|osf\.io/\w+|figshare\.com/[\w./-]+|[\w-]+\.github\.io/[\w./-]*|gitlab\.com/[\w./-]+)",re.I)
DENY=re.compile(r"github\.com/(arXiv|brucemiller|ethz-spylab/agentdojo|openai/|huggingface/|microsoft/|langchain|meta-llama|anthropics/|vllm-project|pytorch|google-research|google-deepmind)|arxiv\.org|latexml",re.I)
STRICT=re.compile(r"(\b(our|we|ours)\b\W+(\w+\W+){0,5}(releas|open-?sourc|publish|provid|mak|shar|host|upload|deposit)\w*)|((code|data|dataset|benchmark|logs|trajectories|traces|artifacts?|implementation|resources?)\W+(\w+\W+){0,8}(is|are|will be|can be)\W+(\w+\W+){0,3}(available|released|open-?sourced|found|hosted))|(available|released|hosted|found) (at|on|in|under)|reproducib|replication",re.I)
THIRD=re.compile(r"\b(built on|based on|adapted from|following|from|using|use|uses|extends?|forked? from|builds? on|derived from|introduced by|proposed by|of)\b[^.]{0,40}$",re.I)
STOP=set("the a an of for and in on to with from against under via using llm llms agent agents agentic benchmark benchmarking evaluating evaluation towards toward large language model models tool toolusing securing security attack attacks defense defenses".split())
def toks(s): return {t for t in re.findall(r"[a-z0-9]{4,}",re.sub(r"([a-z])([A-Z])",r"\1 \2",s or "").lower()) if t not in STOP}
def fetch(u):
    try: return urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"agentprov-litsearch/0.1 (academic)"}),timeout=60).read(4_000_000).decode("utf8","replace")
    except Exception: return None
lock=threading.Lock()
def work(i):
    if i in cache: return
    h=fetch(f"https://arxiv.org/html/{i}"); time.sleep(0.6)
    a=fetch(f"https://arxiv.org/abs/{i}"); time.sleep(0.6)
    com=""
    if a:
        m=re.search(r'class="tablecell comments">(.*?)</td>',a,re.S)
        if m: com=html.unescape(re.sub(r"<[^>]+>"," ",m.group(1)))
    p=byax[i]; tt=toks(p["title"])|toks(p.get("abstract","")[:0])
    links={}
    if h:
        t=re.sub(r"<script.*?</script>|<style.*?</style>","",h,flags=re.S)
        t=re.sub(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>',lambda m:" "+m.group(1)+" "+m.group(2)+" ",t,flags=re.S)
        plain=re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",t)))
        sents=re.split(r"(?<=[.!?])\s+",plain)
        pos=0
        for se in sents:
            for m in re.finditer(r"https?://[^\s\"'<>)\]]+",se):
                u=m.group(0).rstrip(".,;)")
                if not HOST.search(u) or DENY.search(u): continue
                d=links.setdefault(u,{"fn":False,"strict":0,"third":0,"n":0})
                d["n"]+=1
                if pos<4500: d["fn"]=True
                if len(se)<600 and STRICT.search(se): d["strict"]+=1
                pre=se[:m.start()][-80:]
                if THIRD.search(pre): d["third"]+=1
            pos+=len(se)+1
    for u in re.findall(r"https?://[^\s\"'<>)\]]+",com):
        u=u.rstrip(".,;)")
        if HOST.search(u) and not DENY.search(u):
            links.setdefault(u,{"fn":False,"strict":0,"third":0,"n":0})["comments"]=True
    out=[]
    for u,d in links.items():
        m=re.search(r"(?:github\.com|huggingface\.co/datasets|huggingface\.co|gitlab\.com)/[\w.-]+/([\w.-]+)",u)
        name=m.group(1) if m else ""
        ov=bool(toks(name)&tt) or bool(re.sub(r"[^a-z0-9]","",name.lower()) and re.sub(r"[^a-z0-9]","",name.lower()) in re.sub(r"[^a-z0-9]","",(p["title"] or "").lower()))
        score=(2 if d.get("comments") else 0)+(2 if d["fn"] else 0)+(2 if ov else 0)+(1 if d["strict"] else 0)-(1 if d["third"]>=d["n"] and d["n"] else 0)
        out.append({"url":u,"score":score,"fn":d["fn"],"strict":d["strict"],"third":d["third"],"overlap":ov,"comments":bool(d.get("comments"))})
    with lock: cache[i]={"links":sorted(out,key=lambda x:-x["score"])[:12],"html":bool(h)}
with ThreadPoolExecutor(4) as ex:
    futs=[ex.submit(work,i) for i in ids]
    for k,f in enumerate(futs):
        f.result()
        if k%50==0:
            with lock: json.dump(cache,open(C,"w")); print(k,flush=True)
json.dump(cache,open(C,"w")); print("done",len(cache))
