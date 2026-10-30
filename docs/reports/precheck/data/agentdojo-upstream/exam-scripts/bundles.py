import json, re, sys
from collections import Counter
from pathlib import Path
H=Path.home()/'.agentprov'; part=sys.argv[1]
NEW=H/f'migration-work/precheck/agentdojo-upstream/l2-{part}-j2.partial'; OLD=H/f'corpora/agentdojo-upstream-{part}-p10.partial'
new={json.loads(l)['ex']:json.loads(l) for l in open(NEW/'executions.jsonl')}
old={}
for l in open(OLD/'executions.jsonl'):
    r=json.loads(l)
    if r['ex'] in new: old[r['ex']]=r
def names(p):
    d=json.load(open(p))
    return Counter(re.sub(r'\.[a-z2-7]{16,}$','',b.split(':',1)[1]) for b in d.get('bundle',{}))
co=Counter(); cn=Counter()
for ex in new:
    a=names(OLD/old[ex]['paths']['prov']['agentprov-prov/0.1']['json']); b=names(NEW/new[ex]['paths']['prov']['agentprov-prov/0.1']['json'])
    for k in set(a)|set(b):
        co[k]+= k in a; cn[k]+= k in b
for k in sorted(set(co)|set(cn)):
    if co[k]!=cn[k]: print(co[k], '->', cn[k], k)
