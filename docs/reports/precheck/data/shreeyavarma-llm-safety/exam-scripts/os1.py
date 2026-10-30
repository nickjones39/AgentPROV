import json, sys, collections
sys.path.insert(0, 'tools/analysis2')
from exam2_lib import wilson
rows=[json.loads(l) for l in open(sys.argv[1])]
arms=collections.defaultdict(lambda: collections.Counter())
flags=collections.Counter(); flagged=collections.defaultdict(list)
for r in rows:
    f=r['facets']; o=r['outcomes']
    key=(f['h_pipeline'], f['attack_dir'], f['task_kind'])
    a=arms[key]; a['n']+=1
    for m in ('utility','security'):
        v=o.get(m)
        a[f'{m}:{v}']+=1
    for fl in r['flags']:
        flags[fl]+=1; flagged[fl].append((r['label'], o.get('utility'), o.get('security'), r['variant']))
out={}
for k,a in sorted(arms.items()):
    d=dict(a)
    for m in ('utility','security'):
        kk=a[f'{m}:True']; nn=a[f'{m}:True']+a[f'{m}:False']
        lo,hi=wilson(kk,nn); d[m]={'k':kk,'n':nn,'rate':round(kk/nn*100,2) if nn else None,'wilson95':[round(lo*100,2),round(hi*100,2)]}
    out['|'.join(k)]=d
print(json.dumps(out,indent=1))
print(flags)
for fl,v in flagged.items():
    for x in v: print(fl, x)
