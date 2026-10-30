import sys,os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from rawread import tree, Reader
t=tree(); r=Reader()
lab='runs/gpt-4o-spotlighting_with_delimiting/crypto_trading/user_task_4/important_instructions/injection_task_0.json'
d=r.json(t[lab])
print({k:(type(v).__name__ if not isinstance(v,(str,int,bool,type(None))) or isinstance(v,str) and len(v)>40 else v) for k,v in d.items()})
for m in d['messages']: print(m.get('role'), sorted(m.keys()), type(m.get('content')).__name__, len(str(m.get('content'))), [c.get('function') for c in (m.get('tool_calls') or [])])
