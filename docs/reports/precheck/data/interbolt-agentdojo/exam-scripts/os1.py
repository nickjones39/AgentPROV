import json, sys, collections
sys.path.insert(0, sys.argv[1])
from tools.analysis2.exam2_lib import wilson
rows=[json.loads(l) for l in open(sys.argv[2])]
paper={('banking','A_ceiling'):(9,9,'u'),('travel','A_ceiling'):(13,10,'u'),
('banking','C_utility_strict'):(6,6,'u'),('banking','C_utility_targeted'):(7,6,'u'),
('travel','C_utility_strict'):(7,8,'u'),('travel','C_utility_targeted'):(6,7,'u'),
('banking','B_asr_model'):(71,70,'s'),('travel','B_asr_model'):(39,42,'s'),
('banking','D_asr_system_strict'):(0,0,'s'),('banking','D_asr_system_targeted'):(0,0,'s'),
('travel','D_asr_system_strict'):(9,10,'s'),('travel','D_asr_system_targeted'):(11,11,'s')}
cells=collections.defaultdict(lambda:[0,0])
pre=collections.Counter(); prek=collections.Counter()
for r in rows:
  f=r['facets']; o=r['outcomes']
  if f['task_kind']=='prepass':
    pre[(f['suite'],f['experiment'],f['repeat'])]+=1; prek[(f['suite'],f['experiment'],f['repeat'],o['utility'],o['security'])]+=1; continue
  m='utility' if f['attack_dir']=='none' else 'security'
  c=cells[(f['suite'],f['experiment'],f['repeat'],m)]; c[1]+=1; c[0]+=bool(o[m])
out=[]; mism=0
for (s,e),(p0,p1,mk) in paper.items():
  m='utility' if mk=='u' else 'security'
  k0,n0=cells[(s,e,'repeat_0',m)]; k1,n1=cells[(s,e,'repeat_1',m)]
  k=k0+k1;n=n0+n1;lo,hi=wilson(k,n);pr=(p0+p1)/n*100
  mism+= (k0!=p0)+(k1!=p1)
  out.append(dict(suite=s,experiment=e,metric=('utility' if mk=='u' else 'attack_success(security)'),rep0=f'{k0}/{n0}',rep1=f'{k1}/{n1}',paper_rep0=p0,paper_rep1=p1,pooled_k=k,n=n,rate=round(k/n*100,2),wilson95=[round(lo*100,2),round(hi*100,2)],paper=round(pr,2),gap_pp=round(k/n*100-pr,2)))
for x in out: print(json.dumps(x))
print('cell mismatches', mism)
# H2
att=sum(1 for r in rows if r['facets']['attack_dir']!='none' and r['outcomes']['security'])
ben=sum(1 for r in rows if r['facets']['attack_dir']=='none' and r['facets']['task_kind']=='user' and r['outcomes']['utility'])
byexp=collections.Counter(r['facets']['experiment'] for r in rows if r['facets']['attack_dir']!='none' and r['outcomes']['security'])
bben=collections.Counter(r['facets']['experiment'] for r in rows if r['facets']['attack_dir']=='none' and r['facets']['task_kind']=='user' and r['outcomes']['utility'])
print('H2 attacked sec true',att,dict(byexp),'benign util true',ben,dict(bben))
# H3
d=collections.Counter((r['facets']['suite'],r['facets']['file']) for r in rows if r['facets']['experiment'].startswith('D_') and r['facets']['attack_dir']!='none' and r['outcomes']['security'])
print('H3 D successes by (suite,IT)',dict(d))
# H4
h4=collections.Counter((r['facets']['suite'],r['facets']['file'],r['facets']['experiment']) for r in rows if r['facets']['attack_dir']!='none' and r['outcomes']['security'] and ((r['facets']['suite'],r['facets']['file']) in [('travel','injection_task_1'),('banking','injection_task_8')]))
print('H4',dict(h4))
# per IT B success
bi=collections.Counter((r['facets']['suite'],r['facets']['file']) for r in rows if r['facets']['experiment']=='B_asr_model' and r['facets']['attack_dir']!='none' and r['outcomes']['security'])
print('B by IT',sorted(bi.items()))
print('prepass counts',dict(pre))
print('prepass outcomes',dict(collections.Counter((k[1][:1],k[3],k[4]) for k,v in prek.items() for _ in range(v))))
# benign security constant
print('benign sec', collections.Counter((r['facets']['task_kind'],r['outcomes']['security']) for r in rows if r['facets']['attack_dir']=='none'))
print('flags', collections.Counter(fl for r in rows for fl in r['flags']))
print('pipeline vs h_pipeline mismatch', sum(1 for r in rows if r['facets']['pipeline_dir']!=r['facets']['h_pipeline']), 'suite mismatch', sum(1 for r in rows if r['facets']['suite']!=r['facets']['h_suite']), 'attack mismatch', sum(1 for r in rows if r['facets']['attack_dir']!=r['facets']['h_attack']))
# grid
g=collections.Counter((r['facets']['suite'],r['facets']['experiment'],r['facets']['repeat'],r['facets']['task_kind']) for r in rows)
for k in sorted(g): print('grid',k,g[k])
json.dump(out,open(sys.argv[3],'w'),indent=1)
