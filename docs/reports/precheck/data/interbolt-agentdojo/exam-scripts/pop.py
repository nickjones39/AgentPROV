import sys, os, collections, json, re
sys.path.insert(0, os.path.dirname(__file__))
from rawread import tree, Reader
t=tree(); r=Reader()
DENY="Blocked by security policy."
logs=sorted(p for p in t if p.startswith('runs/published/') and p.endswith('.json') and not p.endswith('run_manifest.json') and p.count('/')==9)
res=collections.defaultdict(collections.Counter)
den_cell=collections.Counter(); den_cell_tasks=collections.Counter()
nullfinal=[]; trailing=[]; ts=[]; pn_mismatch=0; meta_mismatch=collections.Counter()
it1=collections.Counter(); it1_files=[]
errs=collections.Counter(); toolmsgs=0; calls=0; ph_null=0; ph_present=0
sysp=collections.Counter()
for p in logs:
    seg=p.split('/'); suite,exp,rep,pdir,suite2,task,att,fn=seg[2],seg[3],seg[4],seg[5],seg[6],seg[7],seg[8],seg[9][:-5]
    d=r.json(t[p])
    if d.get('pipeline_name')!=pdir: pn_mismatch+=1
    if d.get('suite_name')!=suite: meta_mismatch['suite']+=1
    if d.get('user_task_id')!=task: meta_mismatch['user_task']+=1
    if (d.get('attack_type') or 'none')!=att: meta_mismatch['attack']+=1
    if (d.get('injection_task_id') or 'none')!=fn: meta_mismatch['injection_task']+=1
    res['pkg'][d.get('agentdojo_package_version')]+=1; res['bench'][d.get('benchmark_version')]+=1
    res['error_field'][repr(type(d.get('error')).__name__)]+=1
    ts.append(d.get('evaluation_timestamp'))
    msgs=d['messages']
    if msgs and msgs[0].get('role')=='system':
        import hashlib; c=msgs[0]['content']; txt=''.join(b.get('content') or '' for b in c) if isinstance(c,list) else (c or '')
        sysp[hashlib.sha256(txt.encode()).hexdigest()[:8]+':'+str(len(txt))]+=1
    nd=0
    for m in msgs:
        if m.get('role')=='tool':
            toolmsgs+=1
            e=m.get('error')
            if e is not None:
                errs['tool_error']+=1
                if e==DENY: nd+=1
        for tc in (m.get('tool_calls') or []):
            calls+=1
            if 'placeholder_args' in tc:
                ph_present+=1; ph_null+= tc['placeholder_args'] is None
    if nd:
        den_cell[(suite,exp,rep)]+=nd; den_cell_tasks[(suite,exp,rep)]+=1
    # final
    last=msgs[-1]
    if last.get('role')=='assistant':
        if last.get('tool_calls'): trailing.append((p,len(last['tool_calls'])))
        c=last.get('content'); txt=''.join(b.get('content') or '' for b in c) if isinstance(c,list) else (c or '')
        if not txt.strip() and not last.get('tool_calls'): nullfinal.append(p)
        if c is None: res['final_content_none'][1]+=1
    else:
        res['last_role'][last.get('role')]+=1
    if suite=='travel' and fn=='injection_task_1' and att!='none':
        fns=collections.Counter(tc['function'] for m in msgs for tc in (m.get('tool_calls') or []))
        key='success' if d.get('security') else 'fail'
        it1[(key,'send_email' in fns)]+=1
        if d.get('security'): it1_files.append((exp,rep,task,dict(fns)))
den_total=sum(den_cell.values())
by_exp=collections.Counter(); 
for (s,e,rp),v in den_cell.items(): by_exp[e]+=v
cC=collections.Counter()
for (s,e,rp),v in den_cell.items():
    if e.startswith('C_'): cC[(e,rp)]+=v
cCb=collections.Counter({(e,rp):v for (s,e,rp),v in den_cell.items() if e.startswith('C_') and s=='banking'})
cCt=collections.Counter({(e,rp):v for (s,e,rp),v in den_cell.items() if e.startswith('C_') and s=='travel'})
cTasks=collections.Counter({(s,e,rp):v for (s,e,rp),v in den_cell_tasks.items() if e.startswith('C_')})
tsv=sorted(x for x in ts if x)
man={}
for p in sorted(x for x in t if x.endswith('run_manifest.json')):
    m=r.json(t[p]); man[p]=m
mv=collections.Counter((m['agentdojo']['version'],m['agentdojo']['install_mode'],m['agentdojo']['dirty'],m['interbolt']['version'],m['interbolt']['install_mode'],m['interbolt']['dirty'],m['interbolt']['commit']) for m in man.values())
mdef=collections.Counter((p.split('/')[3],str(m.get('defense')),str(m.get('attack')),m.get('model'),m.get('benchmark_version'),m.get('repeats')) for p,m in man.items())
# window bracketing: each log's ts within its dir manifest? manifests are Z, logs naive
win=[]
for p,m in man.items():
    d=os.path.dirname(p)
    lts=sorted(ts[i] for i,l in enumerate(logs) if l.startswith(d+'/'))
    win.append((p.split('/')[2]+'/'+p.split('/')[3]+'/'+p.split('/')[4],m['run_started_at'],m['run_finished_at'],lts[0],lts[-1],len(lts)))
out=dict(n_logs=len(logs),pipeline_name_mismatch=pn_mismatch,meta_mismatch=dict(meta_mismatch),pkg={str(k):v for k,v in res['pkg'].items()},bench={str(k):v for k,v in res['bench'].items()},
 error_field=dict(res['error_field']),final_last_role_not_assistant=dict(res['last_role']),final_content_none=res['final_content_none'][1],
 tool_messages=toolmsgs,tool_calls=calls,tool_errors=errs['tool_error'],placeholder_present=ph_present,placeholder_null=ph_null,
 system_prompt_variants=dict(sysp),
 denials_total=den_total,denials_by_experiment=dict(by_exp),denials_C_both_suites={f'{e}|{rp}':v for (e,rp),v in sorted(cC.items())},
 denials_C_banking={f'{e}|{rp}':v for (e,rp),v in sorted(cCb.items())},denials_C_travel={f'{e}|{rp}':v for (e,rp),v in sorted(cCt.items())},
 C_logs_with_denial={'|'.join(k):v for k,v in sorted(cTasks.items())},
 null_final=nullfinal,trailing_calls=trailing,
 ts_min=tsv[0],ts_max=tsv[-1],ts_count=len(tsv),
 travel_it1_attacked={f'{a}|send_email={b}':v for (a,b),v in it1.items()},travel_it1_success_detail=[(e,rp,tk,sorted(f)) for e,rp,tk,f in it1_files],
 manifests=len(man),manifest_versions=[list(map(str,k))+[v] for k,v in mv.items()],manifest_cfg=[list(map(str,k))+[v] for k,v in mdef.items()])
print(json.dumps(out,indent=1))
print('WINDOWS')
for w in sorted(win): print(w)
json.dump(out,open(sys.argv[1],'w'),indent=1)
