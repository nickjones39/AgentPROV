import json,sys,collections,re
from pathlib import Path
C=Path(sys.argv[1]).expanduser()
ids={json.loads(l)['ex'] for l in Path(sys.argv[2]).expanduser().read_text().splitlines() if l}
c=collections.Counter()
def q(v): return v.get('$') if isinstance(v,dict) else v
for l in (C/'executions.jsonl').read_text().splitlines():
    r=json.loads(l)
    if r['ex'] not in ids: continue
    d=json.loads((C/list(r['paths']['prov'].values())[0]['json']).read_text())
    for bn,b in d['bundle'].items():
        for sid,st in (b.get('entity') or {}).items():
            if q(st.get('prov:type'))=='apv:Gap':
                p=q(st.get('apv:property')); p=p if isinstance(p,str) else json.dumps(p)
                c[(bn.split('.')[1], re.sub(r'\d+','N',str(q(st.get('apv:about'))))[:20], str(p)[:60], str(q(st.get('apv:status'))))]+=1
for k,v in sorted(c.items(),key=str): print(k,v)
