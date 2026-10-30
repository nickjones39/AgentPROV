import json, sys, os, collections
sys.path.insert(0, sys.argv[1])
from tools.analysis2.exam2_lib import wilson
C=os.path.expanduser(sys.argv[2]); L1=os.path.expanduser(sys.argv[3])
l1={r['sha256']:r for r in map(json.loads,open(L1))}
kinds=collections.Counter(); diff=collections.Counter(); arms=collections.defaultdict(lambda:collections.Counter())
origins=collections.Counter(); dec=collections.Counter(); jn=collections.Counter(); denials_raw_sample=0
for line in open(os.path.join(C,'executions.jsonl')):
    e=json.loads(line); sha=e['raw'][0]['sha256'].split(':')[1]; row=l1[sha]; f=row['facets']
    recs=[json.loads(l) for l in open(os.path.join(C,e['paths']['aer']))]
    js={}
    for r in recs:
        kinds[r.get('k')]+=1
        if r.get('k')=='judgement':
            js[r.get('name')]=r.get('value'); origins[(r.get('name'),str(r.get('origin')))]+=1; jn[r.get('name')]+=1
        if r.get('k')=='decision':
            dec[str(r.get('kind') or r.get('decision') or r.get('verdict'))]+=1
    for m in ('utility','security'):
        rv=row['outcomes'][m]; av=js.get(m)
        diff['compared']+=1; diff['differ']+= (rv!=av)
    key=(f['suite'],f['experiment'],f['task_kind'])
    a=arms[key]; a['n']+=1; a['util_raw']+=bool(row['outcomes']['utility']); a['util_aer']+=bool(js.get('utility')); a['sec_raw']+=bool(row['outcomes']['security']); a['sec_aer']+=bool(js.get('security'))
print('record kinds',dict(kinds)); print('judgement names',dict(jn)); print('origins',{f'{a}|{b}':v for (a,b),v in origins.items()}); print('decision records',dict(dec)); print('OS-2',dict(diff))
out=[]
for (s,e,tk),a in sorted(arms.items()):
    m='security' if e[0] in 'BD' and tk=='user' else 'utility'
    k=a['sec_aer'] if m=='security' else a['util_aer']; n=a['n']; lo,hi=wilson(k,n)
    out.append(dict(suite=s,experiment=e,kind=tk,metric=m,n=n,k=k,raw_k=(a['sec_raw'] if m=='security' else a['util_raw']),rate=round(100*k/n,1),wilson95=[round(lo*100,1),round(hi*100,1)]))
for x in out: print(json.dumps(x))
json.dump(dict(os2=dict(diff),arms=out,decisions=dict(dec),record_kinds=dict(kinds)),open(sys.argv[4],'w'),indent=1)
