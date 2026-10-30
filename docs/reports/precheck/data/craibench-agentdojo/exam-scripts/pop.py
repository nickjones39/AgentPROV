"""Population outcome tally of craibench-agentdojo from the L1 unit rows (raw booleans, no mapping); counts only."""
import json, os, re, math, sys
U=os.path.expanduser('~/.agentprov/migration-work/precheck/craibench-agentdojo/l1-units-head.jsonl')
def wilson(k,n,z=1.959964):
    if n==0: return None
    p=k/n; d=1+z*z/n; c=(p+z*z/(2*n))/d; h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [round(100*max(0,c-h),2), round(100*min(1,c+h),2)]
def cls(suite,ut):
    if suite=='crypto_trading': return 'multi' if ut<80 else 'single'
    if suite=='chain': return 'multi' if ut<25 else 'single'
    return 'n/a'
cells={}
rows=[json.loads(l) for l in open(U)]
for r in rows:
    f=r['facets']; lab=r['label']; parts=lab.split('/')
    pipe,suite,task,att,fn=parts[1],parts[2],parts[3],parts[4],parts[5][:-5]
    if att=='none': key=(pipe,suite,'prepass','-')
    else:
        ut=int(task.split('_')[-1]); inj=int(re.match(r'injection_task_(\d+)',fn).group(1))
        mode='MI' if fn.endswith('_memory_injection') else 'PI'
        key=(pipe,suite,mode,cls(suite,ut))
        if suite=='crypto_trading' and inj>4: key=key+('extra_inj',)
    c=cells.setdefault(key,{'n':0,'utility':0,'security':0})
    c['n']+=1; c['utility']+=bool(r['outcomes']['utility']); c['security']+=bool(r['outcomes']['security'])
# paper-comparable cells include extras (count_true_values divides by files present)
agg={}
for k,v in cells.items():
    k2=k[:4]
    a=agg.setdefault(k2,{'n':0,'utility':0,'security':0,'n_extra_inj':0})
    for m in ('n','utility','security'): a[m]+=v[m]
    if len(k)>4: a['n_extra_inj']+=v['n']
out=[]
for k,v in sorted(agg.items()):
    out.append({'cell':'|'.join(k),**v,'utility_pct':round(100*v['utility']/v['n'],2),'utility_w95':wilson(v['utility'],v['n']),
                'security_pct':round(100*v['security']/v['n'],2),'security_w95':wilson(v['security'],v['n'])})
json.dump({'source':'l1-units-head.jsonl','n':len(rows),'cells':out},sys.stdout,indent=1)
