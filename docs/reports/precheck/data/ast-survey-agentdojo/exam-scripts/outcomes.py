import json,sys,collections,math
from pathlib import Path
sys.path.insert(0,sys.argv[4]); from exam2_lib import wilson
L1=[json.loads(l) for l in open(Path(sys.argv[1]).expanduser())]
N=Path(sys.argv[2]).expanduser()
by_sha={r['sha256']:r for r in L1}
def kind(f): return 'attack' if f['attack_dir']!='none' else ('solv' if f['task_kind']=='prepass' else 'benign')
pop=collections.Counter()
for r in L1:
    f=r['facets']; pop[(f['results_dir'],kind(f),f['suite'])]+=1
README={('runs_qwen3_14b','benign'):(67,None,97),('runs_qwen3-coder_30b','benign'):(56,None,97),('runs_gpt-oss_120b','benign'):(65,None,97),
 ('runs_qwen3_14b','attack'):(501,167,949),('runs_qwen3-coder_30b','attack'):(347,208,949),('runs_gpt-oss_120b','attack'):(521,256,949),
 ('runs_qwen3_14b','solv'):(22,None,35),('runs_qwen3-coder_30b','solv'):(21,None,35),('runs_gpt-oss_120b','solv'):(24,None,35)}
rows=[]; mism=collections.Counter()
for l in (N/'executions.jsonl').read_text().splitlines():
    e=json.loads(l); sha=e['raw'][0]['sha256'].split(':',1)[1]; r=by_sha[sha]
    j={}
    for x in (N/e['paths']['aer']).read_text().splitlines():
        a=json.loads(x)
        if a['k']=='judgement': j[a['name']]=a['value']
    f=r['facets']; o=r['outcomes']
    for nm in ('utility','security'):
        if j.get(nm)!=o[nm]: mism[nm]+=1
    rows.append(dict(model=f['results_dir'],kind=kind(f),suite=f['suite'],u=j['utility'],s=j['security'],err=o['error_present']))
out=[]
for (m,kd),(pu,ps,pn) in sorted(README.items()):
    sub=[x for x in rows if x['model']==m and x['kind']==kd]; n=len(sub)
    for metric,key,paper in (('utility','u',pu),('attack_success','s',ps)):
        if paper is None: continue
        k=sum(bool(x[key]) for x in sub)
        num=den=var=0.0
        tot=sum(pop[(m,kd,su)] for su in ('workspace','travel','banking','slack') if [x for x in sub if x['suite']==su])
        for su in ('workspace','travel','banking','slack'):
            ss=[x for x in sub if x['suite']==su]
            if not ss: continue
            w=pop[(m,kd,su)]/tot; p=sum(bool(x[key]) for x in ss)/len(ss); num+=w*p; var+=w*w*p*(1-p)/len(ss)
        pr=paper/pn; lo,hi=wilson(k,n); gap=(num-pr)*100
        outside=(pr<lo-0.05 or pr>hi+0.05); flag=n>=20 and (abs(gap)>15 or outside)
        out.append(dict(model=m,kind=kd,metric=metric,n=n,k=k,raw_rate=round(k/n,4),weighted=round(num,4),weighted_normal95=[round(num-1.96*math.sqrt(var),3),round(num+1.96*math.sqrt(var),3)],wilson95=f"[{lo:.3f}, {hi:.3f}]",paper=round(pr,4),gap_pp=round(gap,1),outside_wilson_by_5=outside,flag=flag))
res={'n':len(rows),'raw_vs_mapped_mismatches':dict(mism),'sample_run_errors':sum(x['err'] for x in rows),'arms':out}
json.dump(res,open(sys.argv[5],'w'),indent=1)
for o in out: print(o)
print(res['raw_vs_mapped_mismatches'],res['sample_run_errors'])
