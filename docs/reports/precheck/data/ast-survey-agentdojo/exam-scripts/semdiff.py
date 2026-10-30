import json,sys,collections
from pathlib import Path
OLD=Path(sys.argv[1]).expanduser(); NEW=Path(sys.argv[2]).expanduser()
oi={r['ex']:r for r in map(json.loads,(OLD/'executions.jsonl').read_text().splitlines())}
ni=[json.loads(l) for l in (NEW/'executions.jsonl').read_text().splitlines() if l]
def anns(p):
    out={}; hdr=None
    for l in p.read_text(encoding='utf-8',errors='surrogatepass').splitlines():
        r=json.loads(l)
        if r['k']=='sem': hdr=r; continue
        key=(r.get('type'),json.dumps(r.get('target'),sort_keys=True))
        out.setdefault(key,[]).append(r)
    return hdr,out
tc_old=collections.Counter(); tc_new=collections.Counter(); only_old=collections.Counter(); only_new=collections.Counter(); only_new_ex=collections.defaultdict(set)
ruletr=collections.Counter(); evtr=collections.Counter(); valch=collections.Counter(); premch=collections.Counter(); hdrdiff=collections.Counter(); valtr=collections.Counter()
for row in ni:
    o=oi[row['ex']]
    ho,A=anns(OLD/list(o['paths']['sem'].values())[0]); hn,B=anns(NEW/list(row['paths']['sem'].values())[0])
    for k in set(ho)|set(hn):
        if ho.get(k)!=hn.get(k): hdrdiff[k]+=1
    for key,v in A.items(): tc_old[key[0]]+=len(v)
    for key,v in B.items(): tc_new[key[0]]+=len(v)
    for key in set(A)|set(B):
        a=A.get(key,[]); b=B.get(key,[])
        if len(a)!=len(b):
            if len(b)>len(a): only_new[key[0]]+=len(b)-len(a); only_new_ex[key[0]].add(row['ex'])
            else: only_old[key[0]]+=len(a)-len(b)
        for x,y in zip(a,b):
            if x.get('rule')!=y.get('rule'): ruletr[(key[0],' + '.join(x['rule']),' + '.join(y['rule']))]+=1
            if x.get('ev')!=y.get('ev'): evtr[(key[0],x.get('ev'),y.get('ev'))]+=1
            if x.get('value')!=y.get('value'):
                valch[key[0]]+=1
                if key[0] in ('outcome','injection_marker_status','marker') or not isinstance(x.get('value'),(str,dict)) or key[0]!='injection_marker':
                    valtr[(key[0],json.dumps(x.get('value'),sort_keys=True)[:80],json.dumps(y.get('value'),sort_keys=True)[:80])]+=1
            if x.get('premises')!=y.get('premises'): premch[key[0]]+=1
print('header diffs',dict(hdrdiff))
print('type counts old',dict(tc_old)); print('type counts new',dict(tc_new))
print('only_old',dict(only_old)); print('only_new',dict(only_new),{k:len(v) for k,v in only_new_ex.items()})
print('ev transitions'); [print(' ',k,v) for k,v in evtr.most_common()]
print('rule transitions'); [print(' ',k,v) for k,v in ruletr.most_common(40)]
print('value changes',dict(valch)); [print(' ',k,v) for k,v in valtr.most_common(20)]
print('premise changes',dict(premch))
