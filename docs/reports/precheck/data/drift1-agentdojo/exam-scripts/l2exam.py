"""L2 scratch-corpus checks (H-12..H-15, H-18, prereg section 8): counts only.
Usage: l2exam.py CORPUS BASELINE_10JT_CORPUS OUT.json"""
import sys, os, collections, json, glob
sys.path.insert(0, os.path.dirname(__file__))
from rawread import tree, Reader
from agentprov.ingest.loaders import strict_json_loads
from agentprov.adapters.agentdojo.drift_mapper import is_call_error
CORP=os.path.expanduser(sys.argv[1]); BASE=os.path.expanduser(sys.argv[2]); t=tree(); r=Reader(); C=collections.Counter
def recs_of(f): return [strict_json_loads(l) for l in open(f,'rb') if l.strip()]
tot=C(); dec_mismatch=[]; judg=C(); evD=C(); mc_params=C(); sec_origin=C(); defs=C(); load_env=0
unk_tool=C(); base_cmp=C(); base_diff_kinds=C(); dec_sub=C()
for f in sorted(glob.glob(f'{CORP}/aer/*/*.aer.jsonl')):
    recs=recs_of(f); ex=next(x for x in recs if x['k']=='execution'); path=ex['artifacts'][0]['origin']['path']
    pact=path.split('/')[1].startswith('pact-'); benign=path.split('/')[4]=='none'; g='pact' if pact else 'benign' if benign else 'attacked'
    raw=r.json(t[path]); conv=raw['conversations']
    batches=sum(1 for m in conv if m['role']=='assistant' and m.get('tool_calls'))
    ce=sum(1 for i,m in enumerate(conv) if m['role']=='user' and i>0 and is_call_error(m.get('content')))
    k=C(x['k'] for x in recs); tot.update(k)
    decs=[x for x in recs if x['k']=='decision']; dec_sub.update(str(x.get('subtype')) for x in decs)
    if len(decs)!=batches+ce: dec_mismatch.append({'group':g,'decisions':len(decs),'batches':batches,'call_errors':ce})
    tot['decisions_expected']+=batches+ce
    if k['message']!=len(conv): tot['message_count_mismatch']+=1
    if k['tool_execution']!=sum(1 for m in conv if m['role']=='tool'): tot['tool_exec_mismatch']+=1
    if k['model_call']!=sum(1 for m in conv if m['role']=='assistant'): tot['model_call_mismatch']+=1
    defs[(g,tuple(sorted(x.get('name') for x in recs if x.get('kind')=='defense')),ex['task'].get('defense_id'),(ex.get('unk') or {}).get('/task/defense_id'))]+=1
    if 'load_environment' in json.dumps(recs): load_env+=1
    for x in recs:
        if x.get('ev')=='D': evD['record_ev_D']+=1
        for v in (x.get('evf') or {}).values():
            if v=='D': evD['field_ev_D']+=1
        if x['k']=='model_call': mc_params[(x.get('unk') or {}).get('/params')]+=1
        if x['k']=='judgement':
            judg[(x['name'], x['value']==raw[x['name']])]+=1
            if x['name']=='security': sec_origin[(g,x.get('origin'),tuple(sorted(set(y.split('#')[0] for y in x.get('rule') or []))))]+=1
    toolmsgs={x['id'] for x in recs if x['k']=='message' and x.get('role')=='tool'}; unk_tool['tool_messages']+=len(toolmsgs)
    sem=glob.glob(f"{CORP}/sem/*/*/{ex['ex']}.sem.jsonl"); tg=set()
    for l in open(sem[0],'rb'):
        a=strict_json_loads(l)
        if a.get('k')=='ann' and any('unknown_tool' in str(y) for y in a.get('rule',[])): tg.add(str(a.get('target','')).split('#')[0])
    unk_tool['tool_messages_unknown_tool_label']+=len(tg & toolmsgs)
    bf=glob.glob(f"{BASE}/aer/*/{ex['ex']}.aer.jsonl")
    if not bf: base_cmp['absent_in_baseline']+=1; continue
    bk=C(x['k'] for x in recs_of(bf[0]))
    base_cmp['same_record_kind_counts' if bk==k else 'record_kind_counts_differ']+=1
    for kk in set(bk)|set(k):
        if bk[kk]!=k[kk]: base_diff_kinds[f'{kk}:{bk[kk]}->{k[kk]}']+=1
    base_cmp['bytes_identical' if open(bf[0],'rb').read()==open(f,'rb').read() else 'bytes_differ']+=1
out={'executions':len(glob.glob(f'{CORP}/aer/*/*.aer.jsonl')),'records':dict(tot),'decision_subtypes':dict(dec_sub),
 'decisions_ne_batches_plus_call_errors':dec_mismatch,'judgements_raw_eq_mapped':{f'{a}|{b}':v for (a,b),v in judg.items()},
 'class_D_in_aer':dict(evD),'model_call_params_unk':{str(k):v for k,v in mc_params.items()},
 'security_origin':{f'{a}|{b}|{"+".join(c)}':v for (a,b,c),v in sec_origin.items()},
 'defence_actors':{f'{a}|{"+".join(b)}|defense_id={c}|unk={d}':v for (a,b,c,d),v in defs.items()},
 'aer_files_mentioning_load_environment':load_env,
 'unknown_tool_label':dict(unk_tool,share=round(unk_tool['tool_messages_unknown_tool_label']/max(unk_tool['tool_messages'],1),4)),
 'vs_10jt_baseline':dict(base_cmp),'vs_10jt_kind_diffs':dict(base_diff_kinds)}
json.dump(out,open(sys.argv[3],'w'),indent=1); print(json.dumps(out))
