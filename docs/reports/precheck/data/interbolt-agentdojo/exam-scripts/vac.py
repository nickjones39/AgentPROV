import sys, os, collections, json
sys.path.insert(0, os.path.dirname(__file__))
from rawread import tree, Reader
t=tree(); r=Reader(); c=collections.Counter()
for p in sorted(t):
    s=p.split('/')
    if len(s)!=10: continue
    x=r.json(t[p]); n=sum(len(m.get('tool_calls') or []) for m in x['messages'])
    if n==0: c[f'zero_calls|{s[2]}|{s[7]}|{s[3][:1]}|attacked={s[8]!="none"}|utility={bool(x["utility"])}']+=1
print(json.dumps(dict(sorted(c.items())),indent=0))
