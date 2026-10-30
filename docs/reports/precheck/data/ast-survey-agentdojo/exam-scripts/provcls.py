import json,sys,collections,re
from pathlib import Path
C=Path(sys.argv[1]).expanduser()
ids={json.loads(l)['ex'] for l in Path(sys.argv[2]).expanduser().read_text().splitlines() if l}
cnt=collections.Counter(); rules=collections.Counter(); secs=collections.Counter(); n=0
def bclass(name):
    for t in ('core','inf','assess'):
        if f'bundle.{t}.' in name: return t
    return '?'
def walk(doc,bc):
    for sec,v in doc.items():
        if sec in ('prefix','bundle') or not isinstance(v,dict): continue
        for sid,st in v.items():
            if not isinstance(st,dict): continue
            ev=st.get('apv:evidenceClass'); ev=ev.get('$') if isinstance(ev,dict) else ev
            ru=st.get('apv:rule'); ru=ru if isinstance(ru,list) else [ru] if ru else []
            cnt[(bc,ev)]+=1; secs[(bc,sec)]+=1
            if ev=='apv:Derived':
                for r in ru: rules[(bc,sec,r)]+=1
for l in (C/'executions.jsonl').read_text().splitlines():
    r=json.loads(l)
    if r['ex'] not in ids: continue
    n+=1
    d=json.loads((C/list(r['paths']['prov'].values())[0]['json']).read_text(encoding='utf-8',errors='surrogatepass'))
    walk(d,'top')
    for bn,b in (d.get('bundle') or {}).items(): walk(b,bclass(bn))
print('executions',n)
for k,v in sorted(cnt.items(),key=str): print(' ',k,v)
print('sections'); [print(' ',k,v) for k,v in sorted(secs.items(),key=str)]
print('Derived-class rules'); [print(' ',k,v) for k,v in rules.most_common(40)]
