import sys, os, collections, json
sys.path.insert(0, os.path.dirname(__file__))
from rawread import tree, Reader
t=tree(); r=Reader(); D="Blocked by security policy."
c=collections.Counter()
for p in sorted(t):
    s=p.split('/')
    if len(s)!=10 or not s[3].startswith('C_'): continue
    x=r.json(t[p]); den=sum(1 for m in x['messages'] if m.get('role')=='tool' and m.get('error')==D)
    if den: c[f'{s[2]}|{s[3]}|{s[4]}|blocked_and_utility={bool(x["utility"])}']+=1
    if den and s[2]=='banking' and x['utility']: c[f'banking_blocked_complete_task|{s[3]}|{s[4]}|{s[7]}']+=1
x=r.json(t['runs/published/travel/D_asr_system_strict/repeat_0/gpt-4o-mini-2024-07-18-interbolt-strict-enforce/travel/user_task_12/important_instructions/injection_task_3.json'])
ms=x['messages']
c['ut12_assistant_msgs']=sum(1 for m in ms if m.get('role')=='assistant'); c['ut12_assistant_with_calls']=sum(1 for m in ms if m.get('role')=='assistant' and m.get('tool_calls'))
c['ut12_tool_msgs']=sum(1 for m in ms if m.get('role')=='tool'); c['ut12_utility']=int(bool(x['utility'])); c['ut12_security']=int(bool(x['security']))
for k in sorted(c): print(k,c[k])
