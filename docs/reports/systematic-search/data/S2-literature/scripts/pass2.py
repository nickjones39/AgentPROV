import json,re,time,urllib.request,urllib.error,os,sys,html
from concurrent.futures import ThreadPoolExecutor
C="pass2_cache.json"
cache=json.load(open(C)) if os.path.exists(C) else {}
ids=json.load(open("F_ids.json"))
DENY=re.compile(r"github\.com/(arXiv|brucemiller|ethz-spylab/agentdojo|openai/|huggingface/transformers|microsoft/|langchain|meta-llama|anthropics/|vllm-project|pytorch|google-research|google-deepmind|EdisonScientific)|arxiv\.org|latexml|doi\.org/10\.48550",re.I)
LINK=re.compile(r"https?://[^\s\"'<>)\]]+")
HOSTS=re.compile(r"(github\.com/[\w.-]+/[\w.-]+|huggingface\.co/(datasets/)?[\w.-]+/[\w.-]+|zenodo\.org/[\w./-]+|doi\.org/10\.5281/[\w./-]+|osf\.io/\w+|figshare\.com/[\w./-]+|kaggle\.com/[\w./-]+|github\.io[\w./-]*|[\w-]+\.github\.io/[\w./-]*|gitlab\.com/[\w./-]+|drive\.google\.com[\w./?=-]*|dataverse[\w./-]*|openreview\.net/[\w./?=-]+)",re.I)
AV=re.compile(r"(data and code|code and data|data availability|code availability|availability|reproducib|released|release|publicly available|open-?source|available at|available on|we (publish|share|provide))",re.I)
TOPIC=re.compile(r"(trajector|logs?\b|traces?\b|transcripts?|rollouts?|dataset|benchmark|data|code|artifacts?|results)",re.I)
def fetch(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"agentprov-litsearch/0.1 (academic)"}),timeout=60) as r: return r.read(4_000_000).decode("utf8","replace")
    except Exception: return None
lock=__import__("threading").Lock()
def work(i):
    if i in cache: return
    h=fetch(f"https://arxiv.org/html/{i}"); time.sleep(0.7)
    a=fetch(f"https://arxiv.org/abs/{i}"); time.sleep(0.7)
    com=None
    if a:
        m=re.search(r'class="tablecell comments">(.*?)</td>',a,re.S)
        if m: com=re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",m.group(1)))).strip()[:300]
    if not h and not a:
        with lock: cache[i]={"err":True}; return
    own=[];sents=[];fn=[]
    if h:
        t=re.sub(r"<script.*?</script>|<style.*?</style>","",h,flags=re.S)
        t=re.sub(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>',lambda m:" "+m.group(1)+" "+m.group(2)+" ",t,flags=re.S)
        plain=html.unescape(re.sub(r"<[^>]+>"," ",t)); plain=re.sub(r"\s+"," ",plain)
        for se in re.split(r"(?<=[.!?])\s+",plain):
            if len(se)>600: continue
            if AV.search(se) and TOPIC.search(se) and HOSTS.search(se):
                sents.append(se[:320])
                for m in LINK.finditer(se):
                    u=m.group(0).rstrip(".,;")
                    if HOSTS.search(u) and not DENY.search(u): own.append(u)
        for m in LINK.finditer(plain[:4500]):
            u=m.group(0).rstrip(".,;")
            if HOSTS.search(u) and not DENY.search(u): fn.append(u)
        pl=plain
    ev=[]
    if h:
        for kw in ("Data Availability","Code Availability","Data and Code","Reproducibility Statement","Ethics Statement","Broader Impact"):
            k=pl.find(kw)
            if k>=0 and k>len(pl)*0.3: ev.append(pl[k:k+420])
    with lock: cache[i]={"comments":com,"own_links":sorted(set(own+fn))[:12],"av_sents":sents[:5],"av_sections":ev[:3],"html":bool(h)}
if __name__=="__main__":
    with ThreadPoolExecutor(4) as ex:
        futs=[ex.submit(work,i) for i in ids]
        for k,f in enumerate(futs):
            f.result()
            if k%25==0:
                with lock: json.dump(cache,open(C,"w")); print(k,len(cache),flush=True)
    json.dump(cache,open(C,"w")); print("done",len(cache))
