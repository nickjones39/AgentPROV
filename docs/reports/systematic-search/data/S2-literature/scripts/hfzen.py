import json,re,time
import verify_links as V
queue=json.load(open("queue.json"))
n=0
cache2={}
for i,c,links in queue:
    for u in links:
        m=re.search(r"huggingface\.co/datasets/([\w.-]+/[\w.-]+)",u)
        if m:
            V.cache.pop("hf:datasets/"+m.group(1),None)
            r=V.verify_hf("datasets",m.group(1)); cache2["hf:"+m.group(1)]=r; n+=1; time.sleep(0.5)
        m=re.search(r"zenodo\.(\d+)",u) or re.search(r"zenodo\.org/records?/(\d+)",u)
        if m:
            r=V.verify_zen(m.group(1)); cache2["zen:"+m.group(1)]=r; n+=1; time.sleep(0.5)
json.dump(cache2,open("hfzen_cache.json","w")); print(n,len(cache2))
