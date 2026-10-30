import json,re,time,urllib.request,urllib.error,os,sys,html
NOISE=re.compile(r"(uav|lidar|autonomous driving|vehicle|traffic|airport|drone|blockchain|v2x|quantum|power grid|medical image|trajectory prediction|physics|pybullet|reinforcement learning benchmark|multi-agent reinforcement|power system|drug design|lean 4)",re.I)
pool=json.load(open("pool_flags.json"))
C="probe_cache.json"
cache=json.load(open(C)) if os.path.exists(C) else {}
pool=json.load(open("pool_s1.json"))
ids=[]
for k,p in pool.items():
    if (not p.get("s1_exclusion")) and p["arxiv"] and not NOISE.search(p["title"] or "") and re.match(r"\d{4}\.\d{4,5}$",p["arxiv"]):
        ids.append(p["arxiv"])
ids=sorted(i for i in set(ids) if i not in cache); print(len(ids),flush=True)
URLRE=re.compile(r"https?://[^\s\"'<>)\]]+")
KEEP=re.compile(r"(github\.com/[\w.-]+/[\w.-]+|huggingface\.co/(datasets|spaces)/[\w.-]+/[\w.-]+|huggingface\.co/[\w.-]+/[\w.-]+|zenodo\.org/(records?|doi)/[\w./-]+|doi\.org/10\.5281/[\w./-]+|osf\.io/\w+|figshare\.com/[\w./-]+|kaggle\.com/[\w./-]+|dataverse[\w./-]*|gitlab\.com/[\w./-]+)",re.I)
LOGSENT=re.compile(r"[^.]*?(trajector|execution log|run log|\blogs\b|\btraces?\b|transcripts?|rollouts?)[^.]*?(releas|publicly|open-?sourc|available|publish|share)[^.]*\.|[^.]*?(releas|publicly|open-?sourc|available|publish|share)[^.]*?(trajector|execution log|run log|\blogs\b|\btraces?\b|transcripts?|rollouts?)[^.]*\.",re.I)
LA=re.compile(r"trajector|execution logs?|run logs?|\\blogs\\b|\\btraces?\\b|transcripts?|rollouts?",re.I)
LB=re.compile(r"releas|publicly|open-?sourc|available|publish|we share|made public",re.I)
def fetch(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"agentprov-litsearch/0.1 (academic)"}),timeout=60) as r:
            return r.read(3_000_000).decode("utf8","replace")
    except urllib.error.HTTPError as e:
        return None if e.code in (404,403) else None
    except Exception as e:
        return None

from concurrent.futures import ThreadPoolExecutor
import threading
lock=threading.Lock()
def work(i):
    if i in cache: return
    t=fetch(f"https://arxiv.org/html/{i}"); src="html"
    time.sleep(1.0)
    if not t:
        t=fetch(f"https://arxiv.org/abs/{i}"); src="abs"; time.sleep(1.0)
    if not t:
        with lock: cache[i]={"err":True}
        return
    txt=re.sub(r"<script.*?</script>|<style.*?</style>","",t,flags=re.S)
    urls=set(m.group(0).rstrip(".,;") for m in URLRE.finditer(html.unescape(txt)))
    keep=sorted(set(m.group(0).rstrip(".,;") for u in urls for m in [KEEP.search(u)] if m))
    plain=html.unescape(re.sub(r"<[^>]+>"," ",txt)); plain=re.sub(r"\s+"," ",plain)
    sents=[]
    for se in re.split(r"(?<=[.!?])\s+",plain):
        if len(se)<400 and LA.search(se) and LB.search(se):
            sents.append(se[:300])
            if len(sents)>=4: break
    with lock: cache[i]={"src":src,"links":keep[:25],"log_sents":sents,"len":len(plain)}
with ThreadPoolExecutor(6) as ex:
    futs=[ex.submit(work,i) for i in ids]
    for k,f in enumerate(futs):
        f.result()
        if k%25==0:
            with lock: json.dump(cache,open(C,"w")); print(k,len(cache),flush=True)
json.dump(cache,open(C,"w")); print("done",len(cache))
