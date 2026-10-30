import json,sys,collections,re
from pathlib import Path
C=Path(sys.argv[1]).expanduser(); ids=None
if len(sys.argv)>2: ids={json.loads(l)['ex'] for l in Path(sys.argv[2]).expanduser().read_text().splitlines() if l}
rec=collections.Counter(); evf=collections.Counter(); drules=collections.Counter(); n=0
for l in (C/'executions.jsonl').read_text().splitlines():
    r=json.loads(l)
    if ids is not None and r['ex'] not in ids: continue
    n+=1
    for x in (C/r['paths']['aer']).read_text(encoding='utf-8',errors='surrogatepass').splitlines():
        a=json.loads(x)
        if 'ev' in a: rec[a['ev']]+=1
        for q,v in (a.get('evf') or {}).items(): evf[v]+=1
        if a.get('ev')=='D' or 'D' in (a.get('evf') or {}).values():
            for ru in a.get('rule') or []: drules[(a['k'],ru.split('#')[0])]+=1
tot=sum(evf.values()); rt=sum(rec.values())
print('executions',n)
print('record ev',dict(rec),{k:round(v/rt,3) for k,v in rec.items()})
print('evf',dict(evf),{k:round(v/tot,3) for k,v in evf.items()})
both=rec+evf; bt=sum(both.values()); print('both',dict(both),{k:round(v/bt,3) for k,v in both.items()})
print('rules on records with D (ev or evf):'); [print(' ',k,v) for k,v in drules.most_common(40)]
