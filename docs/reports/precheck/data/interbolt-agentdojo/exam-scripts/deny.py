import json, sys, os, collections
sys.path.insert(0, os.path.dirname(__file__))
from rawread import tree, Reader
C=os.path.expanduser(sys.argv[1]); t=tree(); r=Reader()
sample=json.load(open(sys.argv[2]))['labels']
raw=collections.Counter()
for p in sample:
    x=r.json(t[p])
    for m in x['messages']:
        if m.get('role')=='tool':
            raw['tool_msgs']+=1; raw['deny']+= m.get('error')=='Blocked by security policy.'; raw['other_err']+= (m.get('error') not in (None,'Blocked by security policy.'))
        for tc in (m.get('tool_calls') or []): raw['calls']+=1
aer=collections.Counter(); keys=collections.Counter(); te_status=collections.Counter(); dec_fields=collections.Counter()
for line in open(os.path.join(C,'executions.jsonl')):
    e=json.loads(line); recs=[json.loads(l) for l in open(os.path.join(C,e['paths']['aer']))]
    byid={x['id']:x for x in recs}
    for x in recs:
        if x.get('k')=='decision':
            aer['deny']+=1; keys.update(k for k in x.keys())
            for k in ('subject','target','call','about','on'):
                if k in x: dec_fields[k]+=1
        if x.get('k')=='tool_execution':
            aer['tool_exec']+=1; te_status[str(x.get('status'))]+=1
        if x.get('k')=='activity': aer['activity:'+str(x.get('kind'))]+=1
print('raw',dict(raw)); print('aer',dict(aer)); print('decision keys',dict(keys)); print('tool_exec status',dict(te_status))
