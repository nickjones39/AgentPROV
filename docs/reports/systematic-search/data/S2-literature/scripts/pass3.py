import json,re,time,urllib.request,os,html
from concurrent.futures import ThreadPoolExecutor
import threading
C="pass3_cache.json"
cache=json.load(open(C)) if os.path.exists(C) else {}
ids=json.load(open("F_ids.json"))
EXT=re.compile(r"(extend|extension|build[s]? (up)?on|built (up)?on|based on|fork|derived from|adapt|variant|augment|modif|port)",re.I)
lock=threading.Lock()
def work(i):
    if i in cache: return
    try:
        h=urllib.request.urlopen(urllib.request.Request(f"https://arxiv.org/html/{i}",headers={"User-Agent":"agentprov-litsearch/0.1 (academic)"}),timeout=60).read(4_000_000).decode("utf8","replace")
    except Exception:
        with lock: cache[i]={"err":True}
        return
    t=re.sub(r"<script.*?</script>|<style.*?</style>","",h,flags=re.S)
    plain=re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",t)))
    # cut references: find last 'References' heading occurrence
    ri=plain.rfind(" References ")
    body=plain[:ri] if ri>len(plain)*0.5 else plain
    n=len(re.findall(r"agentdojo|agent dojo",body,re.I)); nall=len(re.findall(r"agentdojo|agent dojo",plain,re.I))
    ext=[]
    if n:
        for se in re.split(r"(?<=[.!?])\s+",body):
            if re.search(r"agentdojo",se,re.I) and EXT.search(se) and len(se)<500:
                ext.append(se[:260]); 
                if len(ext)>=2: break
    with lock: cache[i]={"n_body":n,"n_all":nall,"ext":ext}
    time.sleep(0.8)
with ThreadPoolExecutor(4) as ex:
    futs=[ex.submit(work,i) for i in ids]
    for k,f in enumerate(futs):
        f.result()
        if k%50==0:
            with lock: json.dump(cache,open(C,"w")); print(k,flush=True)
json.dump(cache,open(C,"w")); print("done",len(cache))
