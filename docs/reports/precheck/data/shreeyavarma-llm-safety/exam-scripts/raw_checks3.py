import sys, collections, json, re
sys.path.insert(0, sys.argv[1])
from rawload import load
C=collections.Counter
r=C(); by_it=collections.defaultdict(C); ex=[]
def text_of(c):
    if c is None: return ''
    if isinstance(c,str): return c
    return ''.join(x.get('content') or '' for x in c if isinstance(x,dict))
def norm(s): return re.sub(r'[\s\\"\']+',' ',s)
for label,row,o in load():
    f=row['facets']
    if f['attack_dir']!='tool_knowledge' or f['pipeline_dir']!='gpt-4o-2024-05-13': continue
    msgs=o['messages']; tt=norm('\n'.join(text_of(m.get('content')) for m in msgs if m['role']=='tool'))
    a='important message from me' in tt
    b='INFORMATION>' in tt
    calls=[tc.get('function') for m in msgs if m['role']=='assistant' for tc in (m.get('tool_calls') or [])]
    sec=bool(o.get('security'))
    r[(a,b,sec, len(calls)>0)]+=1
    if sec and not b: by_it[o['injection_task_id']][o['user_task_id']]+=1
print({str(k):v for k,v in r.items()})
print(json.dumps({k:dict(v) for k,v in by_it.items()},indent=0))
