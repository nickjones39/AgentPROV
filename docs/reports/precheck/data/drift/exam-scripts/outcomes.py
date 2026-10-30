"""OS-1 (population, from pop.json) and OS-2 (L2 sample labels, raw = mapped per l2exam) with Wilson 95%. Usage: outcomes.py POP.json SAMPLE.json L1UNITS.jsonl OUT1 OUT2"""
import sys, json, math
def wil(k,n,z=1.959964):
    if n==0: return [None,None]
    p=k/n; d=1+z*z/n; c=(p+z*z/(2*n))/d; h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [round(100*(c-h),2), round(100*(c+h),2)]
pop=json.load(open(sys.argv[1]))['outcomes_by_cell']
PAPER={('banking','UA'):40.97,('banking','ASR'):4.86,('slack','UA'):49.52,('slack','ASR'):0.0,('travel','UA'):53.57,('travel','ASR'):0.0,
 ('workspace','UA'):59.64,('workspace','ASR'):0.54,('shopping','BU'):10.0,('shopping','UA'):12.22,('shopping','ASR'):1.67,
 ('github','BU'):30.0,('github','UA'):32.78,('github','ASR'):0.56,('dailylife','BU'):15.0,('dailylife','UA'):16.0,('dailylife','ASR'):7.0}
def rows(cells):
    out=[]
    for (suite,m),paper in PAPER.items():
        att='none' if m=='BU' else 'important_instructions'; c=cells.get(f'{suite}|{att}',{})
        n=sum(c.values()); k=sum(v for kk,v in c.items() if (kk[1]=='1' if m!='ASR' else kk[3]=='1'))
        rate=round(100*k/n,2) if n else None; lo,hi=wil(k,n); gap=round(rate-paper,2) if n else None
        flag = n>=20 and (abs(gap)>15 or paper<lo-5 or paper>hi+5)
        out.append(dict(suite=suite,metric=m,n=n,k=k,rate=rate,wilson95=[lo,hi],paper=paper,gap_pp=gap,flag=bool(flag) if n>=20 else 'n<20'))
    return out
r1=rows(pop)
def macro(rs,suites,m): v=[x['rate'] for x in rs if x['suite'] in suites and x['metric']==m]; return round(sum(v)/len(v),2)
AGD=['banking','slack','travel','workspace']; ADY=['shopping','github','dailylife']
mac={'agentdojo_UA':[macro(r1,AGD,'UA'),50.93],'agentdojo_ASR':[macro(r1,AGD,'ASR'),1.35],'agentdyn_BU':[macro(r1,ADY,'BU'),18.33],'agentdyn_UA':[macro(r1,ADY,'UA'),20.33],'agentdyn_ASR':[macro(r1,ADY,'ASR'),3.07]}
json.dump({'rows':r1,'macro_logs_vs_paper':mac},open(sys.argv[4],'w'),indent=1)
labels=set(json.load(open(sys.argv[2]))['labels'])
cells={}
for l in open(sys.argv[3]):
    u=json.loads(l)
    if u['label'] in labels:
        o=u['outcomes']; key=f"{u['facets']['suite']}|{u['facets']['attack_dir']}"; kk=f"u{int(o['utility'])}s{int(o['security'])}"
        cells.setdefault(key,{}); cells[key][kk]=cells[key].get(kk,0)+1
r2=rows(cells); json.dump({'rows':r2,'note':'n=5 per stratum; no verdict (amendment 2.2, R6)'},open(sys.argv[5],'w'),indent=1)
for x in r1: print('L1',x)
print(mac)
for x in r2: print('L2',x['suite'],x['metric'],x['n'],x['k'],x['rate'],x['wilson95'],x['paper'],x['gap_pp'])
