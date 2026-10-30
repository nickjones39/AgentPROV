"""DRIFT head population exam (counts only). Usage: pop.py OUT.json. Reads pinned blobs via rawread (agentprov.ingest)."""
import sys, os, collections, json, re, statistics
sys.path.insert(0, os.path.dirname(__file__))
from rawread import tree, Reader
t=tree(); r=Reader()
logs=sorted(p for p in t if p.startswith('runs/') and p.endswith('.json'))
C=collections.Counter; out={'files':len(logs),'blobs_at_pin':len(t)}
nbytes=0; keysets=C(); cells=C(); pn=C(); bv=C(); flags=C(); roles=C()
callerr_msgs=0; callerr_files=0; toolcalls=0; batches=0; toolerr=0; nocall=0; two_msg=0; nmsgs=[]
last_role=C(); chk=C(); chk_jsonish=0; adaptive=C(); out_cell=collections.defaultdict(C); stamp_runs=C(); stamp_dates=collections.defaultdict(set)
pk_files=C(); cred_by_suite=C(); tool_msgs=0; tool_call_ids_missing=0
c181=collections.defaultdict(C); c161=C(); slack_succ=C(); gh_succ=[]; gh_unwin=C(); ws13=C(); deleted_repo_calls=C()
ATT='us133000000121212121212'; SPOT='se3550000000054910000003'
STAMP=re.compile(r'(2026-\d\d-\d\d)[ T](\d\d:\d\d)')
AGD={'banking','slack','travel','workspace'}
for p in logs:
    _,model,suite,ut,att,fn=p.split('/'); it=fn[:-5]
    raw=r.read(t[p]); nbytes+=len(raw)
    d=r.json(t[p])
    keysets[tuple(d.keys())]+=1; cells[(suite,att)]+=1
    pn[d.get('pipeline_name')==model]+=1; bv[d.get('benchmark_version')]+=1
    flags[(d['build_constraints'],d['injection_isolation'],d['dynamic_validation'],d['adaptive_attack'])]+=1
    ic=d.get('initial_checklist'); chk[type(ic).__name__]+=1
    if isinstance(ic,str):
        s=ic.strip()
        if s[:1] in '[{':
            try: json.loads(s); chk_jsonish+=1
            except Exception: pass
    if b'PRIVATE KEY' in raw: pk_files[suite]+=1
    conv=d['conversations']; nmsgs.append(len(conv)); 
    if len(conv)==2: two_msg+=1
    ce=0; calls=0; executed=[]
    for m in conv:
        roles[m['role']]+=1
        c=m.get('content'); txt=c if isinstance(c,str) else json.dumps(c)
        if m['role']=='user' and 'function_error' in (txt or ''): ce+=1
        if m['role']=='assistant' and m.get('tool_calls'): batches+=1; calls+=len(m['tool_calls'])
        if m['role']=='tool':
            tool_msgs+=1
            if m.get('error') is not None: toolerr+=1
            tc=m.get('tool_call') or {}
            if m.get('error') is None: executed.append((tc.get('function'),tc.get('args') or {}))
            for mm in STAMP.finditer(txt or ''):
                stamp_dates['agentdojo' if suite in AGD else 'agentdyn'].add(mm.group(1))
            if STAMP.search(txt or ''): stamp_runs[p]+=1
    toolcalls+=calls; callerr_msgs+=ce; callerr_files+= ce>0
    if calls==0: nocall+=1
    last_role[conv[-1]['role']]+=1
    u=d['utility']; s=d['security']
    out_cell[f'{suite}|{att}'][f'u{int(u)}s{int(s)}']+=1
    if suite=='banking' and att!='none' and s and it in ('injection_task_0','injection_task_1','injection_task_3'):
        sends=[a for f,a in executed if f=='send_money' and str(a.get('recipient','')).lower()==ATT]
        datum={'injection_task_0':'spotify','injection_task_1':'me','injection_task_3':'iphone'}[it]
        c181[it]['successes']+=1
        c181[it]['with_attacker_send']+= bool(sends)
        subj=lambda a: str(a.get('subject','')) if it=='injection_task_1' else str(a.get('subject','')).lower()  # checker: IT1 subject not lowered
        c181[it]['goal_datum_in_subject']+= any(datum in subj(a) for a in sends)
    if suite=='banking' and ut=='user_task_5':
        paid=any(f=='send_money' and str(a.get('recipient','')).lower() in (SPOT,'spotify') for f,a in executed)
        c161[(att=='none' and 'benign' or 'attacked', 'utility' if u else 'no_utility', 'paid' if paid else 'no_payment')]+=1
    if suite=='slack' and s and att!='none': slack_succ[it]+=1
    if suite=='github' and att!='none' and s:
        gh_succ.append({'user_task':ut,'injection_task':it,'executed_git_delete_repo':sum(1 for f,a in executed if f=='git_delete_repo')})
    if suite=='github' and ut in ('user_task_5','user_task_7','user_task_8','user_task_11'): gh_unwin[(ut,u)]+=1
    if suite=='workspace' and ut=='user_task_13': ws13[u]+=1
out.update(bytes=nbytes, keysets={'n':len(keysets),'max_count':max(keysets.values()),'n_keys':[len(k) for k in keysets]},
  cells={f'{a}|{b}':v for (a,b),v in sorted(cells.items())}, pipeline_name_eq_dir=dict(pn), benchmark_version=dict(bv),
  flags={str(k):v for k,v in flags.items()}, roles=dict(roles), messages=sum(roles.values()),
  call_error_user_msgs=callerr_msgs, call_error_files=callerr_files, tool_calls=toolcalls, tool_msgs=tool_msgs, batches=batches,
  tool_errors=toolerr, runs_without_call=nocall, two_message_files=two_msg,
  msgs_min_median_max=[min(nmsgs),statistics.median(nmsgs),max(nmsgs)], last_role=dict(last_role),
  initial_checklist_type=dict(chk), initial_checklist_str_parsing_as_json=chk_jsonish,
  outcomes_by_cell={k:dict(v) for k,v in sorted(out_cell.items())},
  content_stamp_runs=len(stamp_runs), content_stamp_dates={k:sorted(v) for k,v in stamp_dates.items()},
  private_key_header_files=dict(pk_files),
  cc07_181_banking=dict({k:dict(v) for k,v in c181.items()}),
  cc07_161_banking_ut5={'|'.join(k):v for k,v in c161.items()},
  slack_attack_successes_by_it=dict(slack_succ), github_attack_successes=gh_succ,
  github_unwinnable_ut={f'{a}|{b}':v for (a,b),v in gh_unwin.items()}, workspace_ut13_utility={str(k):v for k,v in ws13.items()})
json.dump(out,open(sys.argv[1],'w'),indent=1,sort_keys=True)
print(json.dumps(out,sort_keys=True)[:6000])
