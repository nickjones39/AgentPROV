"""Key/shape census of DRIFT head logs (types only, no values)."""
import sys, os, collections, json
sys.path.insert(0, os.path.dirname(__file__))
from rawread import tree, Reader
t=tree(); r=Reader()
logs=sorted(p for p in t if p.startswith('runs/') and p.endswith('.json'))
print(len(logs), logs[0].count('/'))
segs=collections.Counter(p.count('/') for p in logs); print(segs)
d=r.json(t[logs[0]])
print([(k,type(v).__name__) for k,v in d.items()])
mk=collections.Counter(); tc=collections.Counter()
for p in logs[:200]:
    d=r.json(t[p])
    for m in d['conversations']:
        mk[(m.get('role'),tuple(sorted(m.keys())))]+=1
        for c in (m.get('tool_calls') or []): tc[tuple(sorted(c.keys()))]+=1
        if isinstance(m.get('tool_call'),dict): tc[('single',)+tuple(sorted(m['tool_call'].keys()))]+=1
for k,v in mk.most_common(): print(v,k)
print(tc)
print('/'.join('<%d>'%i for i in range(logs[0].count('/')+1)), [s if i<3 else '*' for i,s in enumerate(logs[0].split('/'))])
