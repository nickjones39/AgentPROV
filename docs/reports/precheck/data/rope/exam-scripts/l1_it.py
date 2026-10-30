import os, json, collections
U=os.path.expanduser('~/.agentprov/migration-work/precheck/rope/l1-units-head.jsonl')
rows=[json.loads(l) for l in open(U)]
C=collections.Counter()
corr={('slack','injection_task_5'),('dailylife','injection_task_7'),('github','injection_task_1')}
cc=collections.Counter(); paper=collections.Counter(); ad=collections.Counter()
for r in rows:
    f=r['facets'];o=r['outcomes']
    if f['attack_dir']=='none' or o.get('security') is not True: continue
    key=(f['suite'],f['file'])
    if key in corr: cc[(f['suite'],f['file'],f['model_dir'],f['attack_dir'])]+=1
    ismain=f['model_dir'] in ('gpt-4o-mini','gemini-2.5-flash','qwen3-235b') or (f['model_dir']=='gpt-4o' and f['suite'] in ('github','shopping','dailylife'))
    if f['attack_dir']=='important_instructions' and ismain and key not in corr:
        paper[(f['suite'],f['file'])]+=1; paper[('model',f['model_dir'])]+=1
    if f['attack_dir']=='autodojo':
        ad[(f['model_dir'], 'corr' if key in corr else 'keep')]+=1
for k,v in sorted(cc.items()): print('CORR',k,v)
tot=collections.Counter()
for (s,i,m,a),v in cc.items(): tot[(s,i)]+=v
print(tot)
print('PAPER', sum(v for k,v in paper.items() if k[0]!='model'), sorted(paper.items()))
print('AD', sorted(ad.items()))
# H-06
h6=collections.Counter()
for r in rows:
    f=r['facets']
    if f['suite']=='github' and f['task_dir'] in ('user_task_5','user_task_7','user_task_8','user_task_11'):
        h6[r['outcomes'].get('utility')]+=1
print('H06',h6)
# H-23 banking security true
print('H23', sum(1 for r in rows if r['facets']['suite']=='banking' and r['facets']['attack_dir']!='none' and r['outcomes'].get('security') is True))
# H-08 tags
t=collections.Counter((r['facets']['model_dir'],r['facets']['h_pipeline']) for r in rows if r['facets']['model_dir']=='gpt-4o-mini')
print('H08',t)
# H-10 LH
lh=[r for r in rows if r['facets']['attack_dir']=='agentlab_longhorizon']
print('LH',len(lh), collections.Counter(r['outcomes'].get('security') for r in lh), collections.Counter(r['variant'] for r in lh))
print('LHempty',[ (r['label'].split('/')[1], r['facets']['task_dir'], r['facets']['file'], r['flags']) for r in lh if r['outcomes'].get('security') is None])
tr=collections.defaultdict(set)
for r in lh:
    if r['facets']['suite']=='travel': tr[r['facets']['model_dir']].add((r['facets']['task_dir'],r['facets']['file']))
allc=set().union(*tr.values())
for m,s in tr.items(): print('LH travel missing',m,sorted(allc-s), len(s))
# flags
print(collections.Counter(fl for r in rows for fl in r['flags']))
# H-21 qwen autodojo dates? not in rows
