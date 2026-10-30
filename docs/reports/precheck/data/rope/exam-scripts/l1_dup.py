import os, json, collections
U=os.path.expanduser('~/.agentprov/migration-work/precheck/rope/l1-units-head.jsonl')
rows=[json.loads(l) for l in open(U)]
g=collections.defaultdict(list)
for r in rows:
    if r['fp']: g[r['fp']].append(r)
G=[v for v in g.values() if len(v)>1]
print('all',len(G),sum(map(len,G)))
# within same model_dir/attack_dir/suite/task_dir
w=collections.defaultdict(list)
for r in rows:
    f=r['facets']
    if r['fp']: w[(r['fp'],f['model_dir'],f['attack_dir'],f['suite'],f['task_dir'])].append(r)
W=[v for v in w.values() if len(v)>1]
print('within cell across injection tasks',len(W),sum(map(len,W)))
c=collections.Counter()
for v in G:
    md=set(r['facets']['model_dir'] for r in v); ad=set(r['facets']['attack_dir'] for r in v)
    c[('multi_model' if len(md)>1 else 'one_model','multi_attack' if len(ad)>1 else 'one_attack')]+=1
print(c)
mm=collections.Counter()
for v in G:
    md=tuple(sorted(set(r['facets']['model_dir'] for r in v)))
    if len(md)>1: mm[md]+=1
print(mm.most_common(10))
ad=collections.Counter()
for v in G:
    a=tuple(sorted(set(r['facets']['attack_dir'] for r in v)))
    if len(a)>1: ad[a]+=1
print(ad)
# null_final by model
print(collections.Counter(r['facets']['model_dir'] for r in rows if 'null_final' in r['flags']))
