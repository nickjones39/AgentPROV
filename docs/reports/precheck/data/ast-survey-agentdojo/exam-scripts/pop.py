import json,sys,collections,re
from pathlib import Path
C=Path(sys.argv[1]).expanduser()
U=re.compile(r'\\u[0-9a-fA-F]{4}')
rows=[]
for l in (C/'executions.jsonl').read_text().splitlines():
    e=json.loads(l)
    r=dict(ex=e['ex']); h6=False; anycall=False; u_by_role=collections.Counter(); calls_send=[]
    for x in (C/e['paths']['aer']).read_text(encoding='utf-8',errors='surrogatepass').splitlines():
        a=json.loads(x); k=a['k']
        if k=='execution':
            t=a['task']; r.update(suite=t['suite'],task=t['task_id'],attack=t.get('attack_id'),inj=t.get('attack_target_id'),error=(a.get('ext') or {}).get('agentdojo',{}).get('error') is not None)
        elif k=='actor' and a.get('id')=='agent': r['model']=(a.get('model') or {}).get('requested')
        elif k=='scope' and a.get('id')=='run':
            r['start']=a['t'].get('start_naive'); r['dur']=a['t'].get('dur_s')
        elif k=='judgement': r[a['name']]=a['value']
        elif k=='message':
            parts=a.get('parts') or []
            has_call=any(p.get('t')=='tool_call' for p in parts)
            anycall|=has_call
            for p in parts:
                txt=p.get('text')
                if isinstance(txt,str):
                    if a.get('role')=='assistant' and '<function=' in txt and not has_call: h6=True
                    if U.search(txt): u_by_role[a.get('role')]+=1
                if p.get('t')=='tool_call' and p.get('name')=='send_money':
                    calls_send.append(p.get('args'))
    r['h6']=h6; r['u']=dict(u_by_role); r['send']=calls_send
    rows.append(r)
json.dump(rows,open(sys.argv[2],'w'))
print(len(rows))
