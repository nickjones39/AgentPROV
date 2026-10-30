"""H-04/H-09 content stamps in tool outputs: minute-level vs microsecond-level stamps (>= 2026), runs per group, range. Usage: stamps.py L1UNITS.jsonl"""
import sys, os, collections, json, re
sys.path.insert(0, os.path.dirname(__file__))
from rawread import tree, Reader
t=tree(); r=Reader()
RX={'minute':re.compile(r'(20\d\d-\d\d-\d\d)[ T](\d\d:\d\d)'),'microsecond':re.compile(r'(20\d\d-\d\d-\d\d)[ T](\d\d:\d\d):\d\d\.\d{6}')}
res={k:collections.Counter() for k in RX}; rng={k:{} for k in RX}
for l in open(sys.argv[1]):
    u=json.loads(l); g='pact' if u['facets']['model_dir'].startswith('pact-') else ('benign' if u['facets']['attack_dir']=='none' else 'attacked')
    d=r.json(t[u['label']])
    txt=' '.join(m['content'] if isinstance(m.get('content'),str) else json.dumps(m.get('content')) for m in d['conversations'] if m['role']=='tool')
    for k,rx in RX.items():
        h=[a+'T'+b for a,b in rx.findall(txt) if a>='2026-01-01']
        if h:
            res[k][g]+=1; lo,hi=rng[k].get(g,(h[0],h[0])); rng[k][g]=(min(lo,*h),max(hi,*h))
print(json.dumps({k:{'runs':dict(v),'total':sum(v.values()),'range':{g:list(x) for g,x in rng[k].items()}} for k,v in res.items()}))
