import sys, os, collections, json
sys.path.insert(0, os.path.dirname(__file__))
from rawread import tree, Reader
t=tree(); r=Reader(); D="Blocked by security policy."
c=collections.Counter()
for p in sorted(t):
    s=p.split('/')
    if len(s)!=10: continue
    x=r.json(t[p]); ms=x['messages']
    ncalls=sum(len(m.get('tool_calls') or []) for m in ms)
    c['logs']+=1; c['logs_with_calls']+= ncalls>0; c['logs_zero_calls']+= ncalls==0
    den=sum(1 for m in ms if m.get('role')=='tool' and m.get('error')==D)
    benign = s[8]=='none'
    if benign and den: c[f'benign_with_denial|{s[3][:1]}|{"prepass" if s[7].startswith("injection") else "user"}']+=1; c[f'benign_denials|{s[3][:1]}']+=den
    if benign and ncalls==0 and x['utility']: c['benign_vacuous_utility_zero_calls']+=1
    c['other_tool_errors']+=sum(1 for m in ms if m.get('role')=='tool' and m.get('error') not in (None,D))
print(json.dumps(dict(sorted(c.items())),indent=0))
