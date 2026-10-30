import json,re,time,urllib.request,urllib.error,os,sys,html
NOISE=re.compile(r"(uav|lidar|autonomous driving|vehicle|traffic|airport|drone|blockchain|v2x|quantum|power grid|medical image|trajectory prediction|physics|pybullet|reinforcement learning benchmark|multi-agent reinforcement|power system|drug design|lean 4)",re.I)
pool=json.load(open("pool_flags.json"))
C="probe_cache.json"
cache=json.load(open(C)) if os.path.exists(C) else {}
ids=[]
for k,p in pool.items():
    if p["stage1_rules"] and p["arxiv"] and not NOISE.search(p["title"] or "") and re.match(r"\d{4}\.\d{4,5}$",p["arxiv"]):
        ids.append(p["arxiv"])
ids=['2401.09002', '2403.06833', '2406.12814', '2410.05451', '2410.13919', '2410.22770', '2502.01241', '2502.01822', '2502.02260', '2502.08586', '2502.08745', '2502.20383', '2503.00061', '2503.01908', '2503.09648', '2503.16248', '2503.22738', '2504.05408', '2505.00843', '2505.04799', '2505.10924', '2505.11717', '2505.17735', '2505.18907', '2505.23559', '2506.00197', '2506.01245', '2506.07524', '2506.08837', '2506.11094', '2506.17318', '2509.05755', '2509.24240', '2509.25624', '2510.03417', '2510.09023', '2510.11851', '2510.19207', '2510.23675', '2510.23883', '2510.26037', '2510.27140', '2511.15203', '2511.17671', '2511.17959', '2512.11147', '2601.05755', '2601.10156', '2601.17549', '2601.19202', '2602.04197', '2602.07104', '2602.09433', '2602.10127', '2602.13597', '2602.16346', '2603.10749', '2603.11862', '2603.18096', '2603.19469', '2604.01194', '2604.04035', '2604.04989', '2604.11790', '2604.18652', '2604.20704', '2605.08442', '2605.12535', '2605.29659', '2606.00566', '2606.03024', '2606.04141', '2606.10304', '2606.12290', '2606.14517', '2606.31272', '2606.31639', '2607.10534', '2607.15143', '2607.18826', '2609.02035', '2609.10854']; print(len(ids),flush=True)
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
