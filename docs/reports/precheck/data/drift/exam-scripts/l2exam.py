"""L2 scratch-corpus checks (H-12..H-15, OS-2, section 8): counts only. Usage: l2exam.py CORPUS OUT.json"""
import sys, os, collections, json, glob
sys.path.insert(0, os.path.dirname(__file__))
from rawread import tree, Reader
from agentprov.ingest.loaders import strict_json_loads
CORP=os.path.expanduser(sys.argv[1]); t=tree(); r=Reader(); C=collections.Counter
AGD={'banking','slack','travel','workspace'}
tot=C(); dec_mismatch=[]; judg=C(); evD=C(); unk=collections.defaultdict(C); subtypes=C(); mc_params=C(); per=[]
for f in sorted(glob.glob(f'{CORP}/aer/*/*.aer.jsonl')):
    recs=[strict_json_loads(l) for l in open(f,'rb') if l.strip()]
    ex=next(x for x in recs if x['k']=='execution'); path=ex['artifacts'][0]['origin']['path']; suite=ex['task']['suite']
    grp='agentdojo' if suite in AGD else 'agentdyn'
    raw=r.json(t[path]); conv=raw['conversations']
    batches=sum(1 for m in conv if m['role']=='assistant' and m.get('tool_calls'))
    ce=sum(1 for m in conv if m['role']=='user' and 'function_error' in (m.get('content') if isinstance(m.get('content'),str) else json.dumps(m.get('content'))))
    k=C(x['k'] for x in recs); tot.update(k)
    decs=[x for x in recs if x['k']=='decision']; subtypes.update(x.get('subtype') for x in decs)
    if len(decs)!=batches+ce: dec_mismatch.append({'suite':suite,'decisions':len(decs),'batches':batches,'call_errors':ce})
    if k['message']!=len(conv): tot['message_count_mismatch']+=1
    if k['tool_execution']!=sum(1 for m in conv if m['role']=='tool'): tot['tool_exec_mismatch']+=1
    if k['model_call']!=sum(1 for m in conv if m['role']=='assistant'): tot['model_call_mismatch']+=1
    for x in recs:
        if x.get('ev')=='D': evD['record_ev_D']+=1
        for v in (x.get('evf') or {}).values():
            if v=='D': evD['field_ev_D']+=1
        if x['k']=='model_call': mc_params[(x.get('unk') or {}).get('/params')]+=1
        if x['k']=='judgement':
            judg[(x['name'], x['value']==raw[x['name']])]+=1
    toolmsgs={x['id'] for x in recs if x['k']=='message' and x.get('role')=='tool'}
    unk[grp]['tool_messages']+=len(toolmsgs)
    sem=glob.glob(f"{CORP}/sem/*/*/{ex['ex']}.sem.jsonl")
    tg=set()
    for l in open(sem[0],'rb'):
        a=strict_json_loads(l)
        if a.get('k')=='ann' and a.get('type')=='integrity' and 'agentdojo.unknown_tool@1' in a.get('rule',[]):
            tg.add(a['target'].split('#')[0])
    unk[grp]['tool_messages_unknown_integrity']+=len(tg & toolmsgs)
    unk[grp]['executions']+=1
out={'executions':sum(u['executions'] for u in unk.values()),'records':dict(tot),'decisions_ne_batches_plus_call_errors':dec_mismatch,
 'decision_subtypes':dict(subtypes),'judgements_raw_eq_mapped':{f'{a}|{b}':v for (a,b),v in judg.items()},'class_D_in_aer':dict(evD),
 'model_call_params_unk':{str(k):v for k,v in mc_params.items()},
 'unknown_tool_integrity':{g:dict(v, share=round(v['tool_messages_unknown_integrity']/max(v['tool_messages'],1),4)) for g,v in unk.items()}}
json.dump(out,open(sys.argv[2],'w'),indent=1); print(json.dumps(out))
