import os, json, collections, sys
U=os.path.expanduser('~/.agentprov/migration-work/precheck/rope/l1-units-head.jsonl')
rows=[json.loads(l) for l in open(U)]
C=collections.Counter
cell=collections.defaultdict(lambda: C())
for r in rows:
    f=r['facets'];o=r.get('outcomes',{})
    k=(f['model_dir'],f['attack_dir'],f['suite'])
    c=cell[k]; c['n']+=1
    for m in ('utility','security'):
        v=o.get(m); c[f'{m}:{v}']+=1
    if o.get('error_present'): c['err']+=1
out={}
for k in sorted(cell):
    c=cell[k]; out['|'.join(k)]=dict(c)
    print(k, c['n'], 'U', c['utility:True'], 'S', c['security:True'], 'Snull', c['security:None'])
json.dump(out, open(sys.argv[1],'w'), indent=1, sort_keys=True)
