import json,sys,re,collections
from pathlib import Path
OLD=Path(sys.argv[1]).expanduser(); NEW=Path(sys.argv[2]).expanduser()
oi={r['ex']:r for r in map(json.loads,(OLD/'executions.jsonl').read_text().splitlines()) if r}
ni=[json.loads(l) for l in (NEW/'executions.jsonl').read_text().splitlines() if l]
def nk(k): return '*' if k.isdigit() else k
def diff(a,b,path,out,depth=0):
    if a==b: return
    if isinstance(a,dict) and isinstance(b,dict) and depth<8:
        for k in set(a)|set(b):
            # evf/unk keys are JSON pointers: keep them (they are our pointers) but mask digits
            kk=re.sub(r'/\d+','/*',k)
            if k not in a: out.add(f"{path}/{kk}:added")
            elif k not in b: out.add(f"{path}/{kk}:removed")
            else: diff(a[k],b[k],f"{path}/{kk}",out,depth+1)
    elif isinstance(a,list) and isinstance(b,list) and len(a)==len(b) and depth<8 and not (a and isinstance(a[0],str)):
        for x,y in zip(a,b): diff(x,y,f"{path}/*",out,depth+1)
    else: out.add(f"{path}:changed")
def recs(p):
    d={}
    for l in p.read_text(encoding='utf-8',errors='surrogatepass').splitlines():
        if l: r=json.loads(l); d[(r['k'],r.get('id'))]=r
    return d
def strip(rule): return rule.split('#')[0]
ptr=collections.Counter(); ptr_ex=collections.defaultdict(set)
added=collections.Counter(); removed=collections.Counter(); added_ex=collections.defaultdict(set)
ruletrans=collections.Counter(); evtrans=collections.Counter(); unkadd=collections.Counter()
sigs=collections.Counter()
for row in ni:
    o=oi[row['ex']]
    A=recs(OLD/o['paths']['aer']); B=recs(NEW/row['paths']['aer'])
    s=set()
    for key in set(A)|set(B):
        k=key[0]
        if key not in A: added[k]+=1; added_ex[k].add(row['ex']); s.add(f"{k}:record_added"); continue
        if key not in B: removed[k]+=1; s.add(f"{k}:record_removed"); continue
        a,b=A[key],B[key]
        out=set(); diff(a,b,k,out)
        for p in out: ptr[p]+=1; ptr_ex[p].add(row['ex']); s.add(p)
        ra=[strip(x) for x in a.get('rule',[]) or []]; rb=[strip(x) for x in b.get('rule',[]) or []]
        if ra!=rb:
            for x,y in zip(sorted(set(ra)),sorted(set(rb))):
                if x!=y: ruletrans[f"{x} -> {y}"]+=1
            if len(set(ra))!=len(set(rb)): ruletrans[f"len {len(set(ra))}->{len(set(rb))} ({k})"]+=1
        if a.get('ev')!=b.get('ev'): evtrans[f"{k}/ev {a.get('ev')}->{b.get('ev')}"]+=1
        fa=a.get('evf') or {}; fb=b.get('evf') or {}
        for q in set(fa)|set(fb):
            if fa.get(q)!=fb.get(q): evtrans[f"{k}/evf{re.sub(r'/[0-9]+','/*',q)} {fa.get(q)}->{fb.get(q)}"]+=1
        ua=a.get('unk') or {}; ub=b.get('unk') or {}
        for q in set(ub)-set(ua): unkadd[f"{k}{re.sub(r'/[0-9]+','/*',q)}={ub[q] if isinstance(ub[q],str) else type(ub[q]).__name__}"]+=1
        for q in set(ua)-set(ub): unkadd[f"REMOVED {k}{q}"]+=1
    sigs[' | '.join(sorted(s))]+=1
res={'executions':len(ni),'pointer_records':dict(ptr.most_common()),'pointer_executions':{p:len(v) for p,v in ptr_ex.items()},
     'records_added':dict(added),'records_added_executions':{k:len(v) for k,v in added_ex.items()},'records_removed':dict(removed),
     'rule_transitions':dict(ruletrans.most_common()),'evidence_transitions':dict(evtrans.most_common()),'unk_added':dict(unkadd),
     'distinct_signatures':len(sigs)}
json.dump(res,open(sys.argv[3],'w'),indent=1,sort_keys=True)
