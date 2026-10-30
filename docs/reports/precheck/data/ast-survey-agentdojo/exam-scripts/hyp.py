import json,sys,collections
rows=json.load(open(sys.argv[1]))
def kind(r): return 'attack' if r['attack'] else ('solv' if r['task'].startswith('injection_task') else 'benign')
PART={'workspace':{'user_task_0','user_task_13','user_task_26'},'travel':{'user_task_0','user_task_7','user_task_14'},'banking':{'user_task_0','user_task_5','user_task_10'},'slack':{'user_task_0','user_task_7','user_task_14'}}
def partial(r):
    if kind(r)!='attack': return False
    s=PART[r['suite']]
    if r['model']=='gpt-oss:120b' and r['suite']=='workspace': s={'user_task_0','user_task_13','user_task_20'}
    return r['task'] in s
print('models',collections.Counter(r['model'] for r in rows))
print('== H4/H5')
for m in sorted({r['model'] for r in rows}):
    R=[r for r in rows if r['model']==m]
    P=[r for r in R if partial(r)]; O=[r for r in R if kind(r)=='attack' and not partial(r)]; B=[r for r in R if kind(r)=='benign']; SV=[r for r in R if kind(r)=='solv']
    mo=min(r['start'] for r in O); 
    earlier=sum(r['start']<mo for r in P)
    u=sum(bool(r['utility']) for r in P); s=sum(bool(r['security']) for r in P)
    print(m,'partial n',len(P),'earlier than min(other attack)',earlier,'u',u,'s',s,
          '| ranges: partial',min(r['start'] for r in P),max(r['start'] for r in P),'other',mo,max(r['start'] for r in O),
          'benign',min(r['start'] for r in B),max(r['start'] for r in B),'solv',min(r['start'] for r in SV),max(r['start'] for r in SV))
    print('   benign later than max(partial):',sum(r['start']>max(x['start'] for x in P) for r in B),'of',len(B),'; benign earlier than min(partial):',sum(r['start']<min(x['start'] for x in P) for r in B))
    # per-suite partial counts
    for su in ('workspace','travel','banking','slack'):
        ps=[r for r in P if r['suite']==su]; print('     partial',su,len(ps),'u',sum(bool(r['utility']) for r in ps),'s',sum(bool(r['security']) for r in ps))
print('== H8 durations (h)')
for m in sorted({r['model'] for r in rows}):
    R=[r for r in rows if r['model']==m]
    d=collections.Counter()
    for r in R: d[kind(r)]+=r['dur'] or 0
    print(m,{k:round(v/3600,2) for k,v in d.items()},'total',round(sum(d.values())/3600,2))
print('all',round(sum((r['dur'] or 0) for r in rows)/3600,2),'missing dur',sum(r['dur'] is None for r in rows))
print('== H6 text-encoded calls')
h6=[r for r in rows if r['h6']]; print(len(h6),collections.Counter(r['model'] for r in h6))
print('== H7 literal \\uXXXX strings by role (text parts)')
c=collections.Counter()
for r in rows:
    for k,v in r['u'].items(): c[k]+=v
print(dict(c), 'executions', sum(1 for r in rows if r['u']))
print('== H9: gpt-oss benign travel/user_task_19 error:', [r['error'] for r in rows if r['model']=='gpt-oss:120b' and kind(r)=='benign' and r['suite']=='travel' and r['task']=='user_task_19'])
print('== H2/H3 errors')
E=[r for r in rows if r['error']]; print(len(E),collections.Counter((r['model'],kind(r)) for r in E))
aff=[r for r in rows if r['model']=='gpt-oss:120b' and kind(r)=='attack' and ((r['suite']=='workspace' and r['task'] in ('user_task_26','user_task_30')) or (r['suite']=='travel' and r['task']=='user_task_19'))]
print('H3 affected pairs',len(aff),'with error',sum(r['error'] for r in aff),'without',sum(not r['error'] for r in aff))
print('== H10 banking injection_task_0/1/3 successes')
for inj in ('injection_task_0','injection_task_1','injection_task_3'):
    S=[r for r in rows if r['suite']=='banking' and r['inj']==inj and r['security']]
    print(inj,'successes',len(S),'with any send_money call',sum(bool(r['send']) for r in S))
json.dump({},open('/dev/null','w'))
