import json,sys,collections,re
from pathlib import Path
C=Path(sys.argv[1]).expanduser()
ids={json.loads(l)['ex'] for l in Path(sys.argv[2]).expanduser().read_text().splitlines() if l}
types=collections.Counter(); bundles=collections.Counter(); nb=collections.Counter(); topent=collections.Counter(); dispatch=collections.Counter(); rel=collections.Counter()
def bclass(name):
    for t in ('core','inf','assess'):
        if f'bundle.{t}.' in name: return t
    return '?'
def ty(st):
    t=st.get('prov:type'); 
    if isinstance(t,list): return tuple(sorted((x.get('$') if isinstance(x,dict) else x) for x in t))
    return t.get('$') if isinstance(t,dict) else t
for l in (C/'executions.jsonl').read_text().splitlines():
    r=json.loads(l)
    if r['ex'] not in ids: continue
    d=json.loads((C/list(r['paths']['prov'].values())[0]['json']).read_text(encoding='utf-8',errors='surrogatepass'))
    B=d.get('bundle') or {}
    nb[len(B)]+=0; bundles['total']+=len(B)
    for bn in B: bundles[bclass(bn)]+=1
    for sec in ('entity','activity','agent'):
        for sid,st in (d.get(sec) or {}).items(): topent[(sec,re.sub(r'[.:].*','',sid),str(ty(st)))]+=1
    for bn,b in B.items():
        bc=bclass(bn)
        for sec in ('entity','activity','agent'):
            for sid,st in (b.get(sec) or {}).items():
                types[(bc,sec,str(ty(st)))]+=1
                ds=st.get('apv:dispatchStatus')
                if ds: dispatch[(bc,json.dumps(ds)[:80], json.dumps(st.get('apv:issue') or st.get('apv:sealIssue') or '')[:60])]+=1
        for sec,v in b.items():
            if sec in ('entity','activity','agent') or not isinstance(v,dict): continue
            rel[(bc,sec)]+=len(v)
print('bundles',dict(bundles))
print('types:'); [print(' ',k,v) for k,v in sorted(types.items(),key=str)]
print('top:'); [print(' ',k,v) for k,v in sorted(topent.items(),key=str)]
print('dispatch:'); [print(' ',k,v) for k,v in dispatch.items()]
