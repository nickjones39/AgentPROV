"""Outcome sanity: L1 population and L2 mapped sample per (pipeline_dir, attack) vs the repository reference (prereg s4).
usage: python os.py <repo> <l1-units.jsonl> <scratch corpus> <out.json>; counts only."""
import json, sys, os, collections
sys.path.insert(0, sys.argv[1])
from tools.analysis2.exam2_lib import wilson
REF={('glm-5.3-flash-none','important_instructions'):(18,0),('glm-5.3-flash-none','tool_knowledge'):(18,0),
('glm-5.3-flash-munim','important_instructions'):(18,0),('glm-5.3-flash-munim-cap2-g2','important_instructions'):(17,0),
('glm-5.3-flash-munim-cap2-g2','tool_knowledge'):(16,0),('glm-5.3-flash-none-g4','important_instructions'):(18,0),
('glm-5.3-flash-none-g4','tool_knowledge'):(18,0),('glm-5.3-flash-munim-g4-cap2','important_instructions'):(18,0),
('glm-5.3-flash-munim-g4-cap2','tool_knowledge'):(18,0),('gpt-oss-120b-none','important_instructions'):(11,20),
('gpt-oss-120b-none','tool_knowledge'):(12,14),('gpt-oss-120b-munim-cap2-g2','important_instructions'):(6,0),
('gpt-oss-120b-none-g4','important_instructions'):(11,20),('gpt-oss-120b-none-g4','tool_knowledge'):(13,14),
('gpt-oss-120b-munim-g4-cap2','important_instructions'):(12,0),('gpt-oss-120b-munim-g4-cap2','tool_knowledge'):(11,0)}
rows=[json.loads(l) for l in open(sys.argv[2])]; l1={r['sha256']:r for r in rows}
def rate(k,n):
    lo,hi=wilson(k,n) if n else (0,0); return dict(k=k,n=n,rate=round(100*k/n,2) if n else None,wilson95=[round(100*lo,2),round(100*hi,2)])
def verdict(k,n,ref,lo,hi,minn):
    if ref is None: return 'no reference'
    gap=100*k/n-ref
    if n<minn: return 'n<20'
    flag=abs(gap)>15 or ref<100*lo-5 or ref>100*hi+5
    return 'GAP' if flag else ('match' if abs(gap)<1e-9 else 'within rule')
pop=collections.defaultdict(lambda:[0,0,0])
for r in rows:
    f=r['facets']; o=r['outcomes']
    if f['attack_dir']=='none' or o['utility'] is None: 
        if f['attack_dir']!='none': pop[(f['pipeline_dir'],f['attack_dir'])][2]+=1
        continue
    c=pop[(f['pipeline_dir'],f['attack_dir'])]; c[0]+=1; c[1]+=bool(o['utility']); c.append(bool(o['security'])) 
out_pop=[]
for key in sorted(pop):
    c=pop[key]; n=c[0]; ku=c[1]; ks=sum(c[3:]); ref=REF.get(key)
    for m,k,rv in (('utility',ku,None if ref is None else 100*ref[0]/27),('asr',ks,None if ref is None else 100*ref[1]/27)):
        x=rate(k,n); x.update(arm='|'.join(key),metric=m,null_outcome_logs=c[2],ref=None if rv is None else round(rv,2),
          gap_pp=None if rv is None else round(x['rate']-rv,2),verdict=verdict(k,n,rv,x['wilson95'][0]/100,x['wilson95'][1]/100,0))
        out_pop.append(x)
C=os.path.expanduser(sys.argv[3]); diff=collections.Counter(); smp=collections.defaultdict(lambda:collections.Counter()); origins=collections.Counter(); kinds=collections.Counter(); dec=collections.Counter()
for line in open(os.path.join(C,'executions.jsonl')):
    e=json.loads(line); row=l1[e['raw'][0]['sha256'].split(':')[1]]; f=row['facets']; js={}
    for l in open(os.path.join(C,e['paths']['aer'])):
        r=json.loads(l); kinds[r.get('k')]+=1
        if r.get('k')=='judgement': js[r.get('name')]=r.get('value'); origins[f"{r.get('name')}|{r.get('origin')}|{f['attack_dir']=='none'}"]+=1
        if r.get('k')=='decision': dec[str(r.get('kind') or r.get('decision') or r.get('verdict'))]+=1
    for m in ('utility','security'):
        diff['compared']+=1; diff['differ']+=(row['outcomes'][m]!=js.get(m)); diff['raw_null']+=row['outcomes'][m] is None
    if f['attack_dir']!='none' and row['outcomes']['utility'] is not None:
        a=smp[(f['pipeline_dir'],f['attack_dir'])]; a['n']+=1; a['u']+=bool(js.get('utility')); a['s']+=bool(js.get('security'))
out_s=[]
for key in sorted(smp):
    a=smp[key]; ref=REF.get(key)
    for m,k,rv in (('utility',a['u'],None if ref is None else 100*ref[0]/27),('asr',a['s'],None if ref is None else 100*ref[1]/27)):
        x=rate(k,a['n']); x.update(arm='|'.join(key),metric=m,ref=None if rv is None else round(rv,2),gap_pp=None if rv is None else round(x['rate']-rv,2),
          verdict=verdict(k,a['n'],rv,x['wilson95'][0]/100,x['wilson95'][1]/100,20)); out_s.append(x)
res=dict(population=out_pop,sample=out_s,os2_raw_vs_mapped=dict(diff),judgement_origins=dict(origins),decision_records=dict(dec),aer_record_kinds=dict(kinds))
json.dump(res,open(sys.argv[4],'w'),indent=1)
print('GAPS pop',[x['arm']+'/'+x['metric'] for x in out_pop if x['verdict']=='GAP']); print('GAPS sample',[x['arm'] for x in out_s if x['verdict']=='GAP'])
print(dict(diff)); print(dict(origins)); print(dict(dec)); print(dict(kinds))
