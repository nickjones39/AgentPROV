"""H-04 initial_trajectory coverage under three definitions of 'executed' (counts only). Usage: traj.py L1UNITS.jsonl"""
import sys, os, collections, json
sys.path.insert(0, os.path.dirname(__file__))
from rawread import tree, Reader
t=tree(); r=Reader(); res=collections.defaultdict(collections.Counter)
for l in open(sys.argv[1]):
    d=r.json(t[json.loads(l)['label']]); tj=d.get('initial_trajectory') or []
    names={str(x.get('function') if isinstance(x,dict) else x) for x in tj} if isinstance(tj,list) else set()
    tools=[m for m in d['conversations'] if m['role']=='tool']
    for k,fs in {'all_tool_messages':[(m.get('tool_call') or {}).get('function') for m in tools],
                 'error_free':[(m.get('tool_call') or {}).get('function') for m in tools if m.get('error') is None]}.items():
        for mode,test in {'substring':lambda f: str(f) in json.dumps(tj),'exact_name':lambda f: str(f) in names}.items():
            res[f'{k}|{mode}']['no_executions' if not fs else 'covers' if all(test(f) for f in fs) else 'not_covers']+=1
print(json.dumps({k:dict(v) for k,v in res.items()}))
