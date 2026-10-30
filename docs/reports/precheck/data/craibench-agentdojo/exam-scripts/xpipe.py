"""L1-04 trajectory-identical pairs across pipeline dirs (H4): shape, equality of assistant text, durations. Counts only."""
import sys,os,json,hashlib
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from rawread import tree, Reader
t=tree(); r=Reader(); out={}
for tail in ['crypto_trading/user_task_67/important_instructions/injection_task_4_memory_injection.json','crypto_trading/user_task_91/important_instructions/injection_task_1_memory_injection.json']:
    a=r.json(t['runs/gpt-4o-mini-2024-07-18-spotlighting_with_delimiting/'+tail]); b=r.json(t['runs/gpt-4o-spotlighting_with_delimiting/'+tail])
    h=lambda d,role: hashlib.sha256(json.dumps([m.get('content') for m in d['messages'] if m['role']==role]).encode()).hexdigest()[:10]
    out[tail]={'msgs':[len(a['messages']),len(b['messages'])],
      'calls':[sum(len(m.get('tool_calls') or []) for m in d['messages']) for d in (a,b)],
      'assistant_text_equal':h(a,'assistant')==h(b,'assistant'),'tool_text_equal':h(a,'tool')==h(b,'tool'),
      'sys_equal':a['messages'][0]['content']==b['messages'][0]['content'],
      'whole_messages_equal':a['messages']==b['messages'],
      'tool_call_ids_equal':[m.get('tool_call_id') for m in a['messages']]==[m.get('tool_call_id') for m in b['messages']],
      'duration':[round(a['duration'],1),round(b['duration'],1)],
      'utility':[a['utility'],b['utility']],'security':[a['security'],b['security']],'pipeline_name_eq_dir':[a['pipeline_name'].startswith('gpt-4o-mini'),b['pipeline_name']=='gpt-4o-spotlighting_with_delimiting']}
print(json.dumps(out,indent=1))
