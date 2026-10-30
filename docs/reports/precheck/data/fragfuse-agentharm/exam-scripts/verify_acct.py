# ruff: noqa  (precheck verifier script, fragfuse-agentharm PC-01: /Users segments in AER/SEM/PROV; digests and counts only)
import json,re,sys,hashlib,os
from pathlib import Path
from collections import Counter,defaultdict
R=Path(sys.argv[1]).expanduser()
rx=re.compile(r"/Users/([^/\s\"'\\<>:]+)/")
GEN={"shared","user","username","runner","name","you","me","example"}
op=hashlib.sha256(Path.home().name.encode()).hexdigest()[:8]
d8=lambda s:hashlib.sha256(s.encode()).hexdigest()[:8]
out={}
for stage,glob in (("aer","aer/**/*.aer.jsonl"),("sem","sem/**/*.sem.jsonl"),("prov","prov/**/*.prov.json")):
    ex=Counter(); segs=Counter(); gen=Counter(); ptr=Counter(); opn=0
    for f in R.glob(glob):
        t=f.read_text(errors="replace"); hit=False
        for m in rx.finditer(t):
            s=m.group(1)
            if s.lower() in GEN: gen[s.lower()]+=1; continue
            segs[d8(s)]+=1; hit=True
            if d8(s)==op: opn+=1
        if hit: ex[f.name]+=1
        if hit and stage=="aer":
            for line in t.splitlines():
                rec=json.loads(line); kind=rec.get("kind") or rec.get("type") or "?"
                def w(o,p):
                    if isinstance(o,dict):
                        for k,v in o.items(): w(v,p+"/"+str(k))
                    elif isinstance(o,list):
                        for v in o: w(v,p+"/*")
                    elif isinstance(o,str):
                        for m in rx.finditer(o):
                            if m.group(1).lower() not in GEN: ptr[f"{kind}:{re.sub(r'/[0-9]+','/N',p)}"]+=1
                w(rec,"")
    out[stage]=dict(executions=len(ex),distinct=len(segs),seg_counts=dict(segs),operator=opn,generic=dict(gen),pointers=dict(ptr.most_common(12)))
print(json.dumps(out,indent=1))
