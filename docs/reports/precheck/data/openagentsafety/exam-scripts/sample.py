"""L2 sample checks for openagentsafety: H13 value identity of every AER judgement against its source pointer (raw blob,
strict parse), sample outcome tallies per model, and raw-trajectory facts of the 30 sampled runs (H8 tool-call ids, H9
latest timestamp, H10 first event / finish / notice). Counts only.
usage: python -I sample.py <scratch corpus> <out.json>"""
import sys, os, json, re, glob, collections
sys.path.insert(0, os.path.dirname(__file__))
from rawread import Reader
import math
def wilson(k,n,z=1.96):
    if n==0: return None
    p=k/n; d=1+z*z/n; c=(p+z*z/(2*n))/d; h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [round(100*p,2),round(100*(c-h),2),round(100*(c+h),2)]
def ptr(o,p):
    for seg in [s.replace('~1','/').replace('~0','~') for s in p.split('/')[1:]]:
        o=o[int(seg)] if isinstance(o,list) else o[seg]
    return o
r=Reader(); out={'judgements':collections.Counter(),'per_model':{},'raw':{}}
TOOLU=re.compile(r'^toolu_\d{2,}$')
for f in sorted(glob.glob(os.path.join(sys.argv[1],'aer','*','*.aer.jsonl'))):
    rows=[json.loads(l) for l in open(f)]
    arts={a['id']:a for a in rows[0]['artifacts']}
    prim=[a for a in arts.values() if a['role']=='primary'][0]['origin']['path']; model=prim.split('/')[1]
    pm=out['per_model'].setdefault(model,{'n':0,'labels':collections.Counter(),'final':collections.Counter(),'rule':collections.Counter(),'issues':collections.Counter()})
    pm['n']+=1
    cache={}
    for j in (x for x in rows if x.get('k')=='judgement'):
        s=j['src'][0]; a=arts[s['a']]; oid=a['origin']['blob_sha1']
        if oid not in cache: cache[oid]=r.json(oid)
        try: ok=ptr(cache[oid],s['p'])==j['value']
        except Exception: ok=False
        out['judgements']['match' if ok else 'mismatch']+=1; out['judgements'][j['name'].split('/')[0]]+=1
        if j['name']=='llm_label': pm['labels'][j['value']]+=1
        if j['name']=='rule_based_score': pm['rule'][str(j['value'])]+=1
        if j['name']=='final_score': pm['final'][f"{j['value']['result']}/{j['value']['total']}"]+=1
    for x in rows:
        if x.get('k')=='execution':
            for i in x.get('issues',[]) or []: pm['issues'][i if isinstance(i,str) else i.get('code')]+=1
    ev=r.json([a for a in arts.values() if a['role']=='primary'][0]['origin']['blob_sha1'])
    rm=out['raw'].setdefault(model,{'tool_call_ids':0,'toolu':0,'first_event_user_message':0,'finish':0,'notice_last':0,'max_ts':''})
    for e in ev:
        for tc in (((e.get('tool_call_metadata') or {}).get('model_response') or {}).get('choices') or [{}])[0].get('message',{}).get('tool_calls') or []:
            rm['tool_call_ids']+=1; rm['toolu']+=bool(TOOLU.match(str(tc.get('id',''))))
        rm['max_ts']=max(rm['max_ts'],str(e.get('timestamp','')))
    rm['first_event_user_message']+= ev[0].get('source')=='user' and ev[0].get('action')=='message'
    rm['finish']+= any(e.get('action')=='finish' for e in ev)
    rm['notice_last']+= 'has not been executed' in str(ev[-1].get('content',''))
for m,pm in out['per_model'].items():
    L=pm['labels']; N=sum(L.values()); neg=L.get('Label: -1',0); nn=N-neg; uns=nn-L.get('Label: 0',0)
    pm['judged']=N; pm['rates']={'judge_unsafe':wilson(uns,nn),'failure':wilson(neg,N)}
    for k in ('labels','final','rule','issues'): pm[k]=dict(pm[k])
out['judgements']=dict(out['judgements'])
json.dump(out,open(sys.argv[2],'w'),indent=1,sort_keys=True)
