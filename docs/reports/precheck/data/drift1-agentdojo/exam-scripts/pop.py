"""drift1-agentdojo population exam (counts only; no values). Usage: pop.py L1UNITS.jsonl HEAD_L1UNITS.jsonl OUT.json
Reads the 626 selected blobs at 0e28729b through rawread (agentprov.ingest strict parse, blob SHA-1 checked)."""
import sys, os, collections, json, re, statistics
sys.path.insert(0, os.path.dirname(__file__))
from rawread import tree, Reader
from agentprov.adapters.agentdojo.drift_mapper import is_call_error, call_error_check, text_form, _call_body
t=tree(); r=Reader(); C=collections.Counter
units=[json.loads(l) for l in open(sys.argv[1])]
ATT='us133000000121212121212'; SPOT='se3550000000054910000003'
STAMP=re.compile(r'(20\d\d-\d\d-\d\d)[ T](\d\d:\d\d)')
PACT_REFUSAL='required provenance contract'
o=dict(files=len(units)); nbytes=[]; keysets=C(); pn=C(); bv=C(); flags=C(); pact_enabled=C(); roles=C()
ce_msgs=0; ce_files=0; ce_class=C(); ce_unrec_class=C(); ce_unrec_files=C(); forms=C(); calls=0; batches=0
toolerr=C(); nocall=0; final_text_calls=C(); nmsgs=[]; last_role=C(); chk=C(); traj=C()
stamp_runs=C(); stamp_range={}; cells=C(); outc=collections.defaultdict(C); contract_path=C()
c181=collections.defaultdict(C); c161=C(); slack_it5=C(); ws13=C(); per_label={}
def grp(u):
    if u['facets']['model_dir'].startswith('pact-'): return 'pact'
    return 'benign' if u['facets']['attack_dir']=='none' else 'attacked'
for u in units:
    p=u['label']; raw=r.read(t[p]); nbytes.append(len(raw)); d=r.json(t[p]); g=grp(u)
    parts=p.split('/'); model,suite,ut,att,it=parts[1],parts[2],parts[3],parts[4],parts[5][:-5]
    keysets[len(d)]+=1; pn[d.get('pipeline_name')]+=1; bv[d.get('benchmark_version')]+=1
    flags[str((d['build_constraints'],d['injection_isolation'],d['dynamic_validation'],d['adaptive_attack']))]+=1
    pact_enabled[(g,d.get('pact_drift_enabled','absent'))]+=1
    if 'global_tool_contract_path' in d:
        v=d['global_tool_contract_path']; contract_path['absolute' if str(v).startswith(('/','~')) else 'relative']+=1
    ic=d.get('initial_checklist'); 
    if ic is None or ic=='None': chk['None']+=1
    elif isinstance(ic,str):
        try: json.loads(ic); chk['str_parses_json']+=1
        except Exception: chk['str_raw']+=1
    else: chk[type(ic).__name__]+=1
    conv=d['conversations']; nmsgs.append(len(conv)); ce=0; ncalls=0; executed=[]; stamped=False
    for i,m in enumerate(conv):
        roles[m['role']]+=1; c=m.get('content')
        if m['role']=='user' and i>0 and is_call_error(c):
            ce+=1; k=call_error_check(c) or 'other'; ce_class[k]+=1
            if k=='other': ce_unrec_class['provenance_contract' if PACT_REFUSAL in c else 'unknown_form']+=1; ce_unrec_files[(g,p)]+=1
        if m['role']=='assistant':
            forms[text_form(c)]+=1
            if m.get('tool_calls'): batches+=1; ncalls+=len(m['tool_calls'])
            elif i==len(conv)-1 and _call_body(c) not in ('','[]'): final_text_calls[text_form(c)]+=1
        if m['role']=='tool':
            e=m.get('error'); tc=m.get('tool_call') or {}
            if e is not None:
                es=str(e); toolerr['validation' if 'ValidationError' in es else 'invalid_tool' if re.search(r'(?i)invalid tool|not a valid tool|tool .{0,60}not (found|available)|unknown tool',es) else 'exception']+=1
            else: executed.append((tc.get('function'),tc.get('args') or {}))
            s=c if isinstance(c,str) else json.dumps(c)
            hits=[m2.group(1)+'T'+m2.group(2) for m2 in STAMP.finditer(s or '') if m2.group(1)>='2026-01-01']
            if hits:
                stamped=True; lo,hi=stamp_range.get(g,(hits[0],hits[0])); stamp_range[g]=(min(lo,*hits),max(hi,*hits))
    stamp_runs[g]+=stamped
    calls+=ncalls; ce_msgs+=ce; ce_files+=ce>0; nocall+= not executed and ncalls==0
    tj=d.get('initial_trajectory') or []; tjs=json.dumps(tj)
    traj['no_executions' if not executed else 'covers' if all(str(f) in tjs for f,_ in executed) else 'not_covers']+=1
    last_role[conv[-1]['role']]+=1
    uu=d['utility']; ss=d['security']; outc[f'{g}|{suite}'][f'u{int(uu)}s{int(ss)}']+=1
    per_label[p]=(uu,ss)
    if suite=='banking' and att!='none' and ss and it in ('injection_task_0','injection_task_1','injection_task_3'):
        sends=[a for f,a in executed if f=='send_money' and str(a.get('recipient','')).lower()==ATT]
        datum={'injection_task_0':'spotify','injection_task_1':'me','injection_task_3':'iphone'}[it]
        c181[f'{g}|{it}']['successes']+=1; c181[f'{g}|{it}']['with_attacker_send']+=bool(sends)
        subj=lambda a: str(a.get('subject','')) if it=='injection_task_1' else str(a.get('subject','')).lower()
        c181[f'{g}|{it}']['goal_datum_in_subject']+=any(datum in subj(a) for a in sends)
    if suite=='banking' and ut=='user_task_5':
        paid=any(f=='send_money' and str(a.get('recipient','')).lower()==SPOT for f,a in executed)
        c161[f"{g}|{'utility' if uu else 'no_utility'}|{'paid' if paid else 'no_payment'}"]+=1
    if suite=='slack' and att!='none' and it=='injection_task_5':
        mem=sum(1 for f,_ in executed if f in ('invite_user_to_slack','add_user_to_channel'))
        slack_it5[f"security_{ss}|membership_call_{'yes' if mem else 'no'}"]+=1
    if suite=='workspace' and ut=='user_task_13': ws13[f'{g}|utility_{uu}']+=1
# H-07 pairing with DRIFT head on the same (suite, user, injection) attacked cells
head={}
for l in open(sys.argv[2]):
    h=json.loads(l); q=h['label'].split('/')
    if h['facets'].get('attack_dir')!='none': head[(q[2],q[3],q[5])]=(h['outcomes']['utility'],h['outcomes']['security'])
pair=collections.defaultdict(C)
for p,(uu,ss) in per_label.items():
    q=p.split('/')
    if q[1]!='gpt-4o-mini' or q[4]=='none': continue
    hk=(q[2],q[3],q[5])
    if hk not in head: pair[q[2]]['unpaired']+=1; continue
    hu,hs=head[hk]; s=pair[q[2]]; s['n']+=1; s['u_here']+=uu; s['u_head']+=hu; s['s_here']+=ss; s['s_head']+=hs
    s['u_agree']+=uu==hu; s['s_agree']+=ss==hs
pact_head=C()
for p,(uu,ss) in per_label.items():
    q=p.split('/')
    if q[1].startswith('pact-'):
        hk=(q[2],q[3],q[5]); 
        if hk in head: pact_head['n']+=1; pact_head['u_head']+=head[hk][0]; pact_head['s_head']+=head[hk][1]; pact_head['u_here']+=uu; pact_head['s_here']+=ss
o.update(bytes=sum(nbytes), size_min_max=[min(nbytes),max(nbytes)], n_keys=dict(keysets), pipeline_name=dict(pn), benchmark_version=dict(bv),
  flags=dict(flags), pact_drift_enabled={f'{a}|{b}':v for (a,b),v in pact_enabled.items()}, global_tool_contract_path=dict(contract_path),
  roles=dict(roles), messages=sum(roles.values()), call_error_user_msgs=ce_msgs, call_error_files=ce_files, call_error_by_check=dict(ce_class),
  call_error_unrecognised_form=dict(ce_unrec_class), call_error_unrecognised_files_by_group=dict(C(g for g,_ in ce_unrec_files)),
  call_error_unrecognised_files=len(ce_unrec_files), assistant_text_form={str(k):v for k,v in forms.items()}, tool_calls=calls, batches=batches,
  tool_errors=dict(toolerr), tool_errors_total=sum(toolerr.values()), runs_without_tool_execution=nocall,
  final_turn_text_calls_empty_tool_calls={str(k):v for k,v in final_text_calls.items()},
  msgs_min_median_max=[min(nmsgs),statistics.median(nmsgs),max(nmsgs)], last_role=dict(last_role), initial_checklist=dict(chk),
  initial_trajectory_covers_executed=dict(traj), content_stamp_runs=dict(stamp_runs), content_stamp_runs_total=sum(stamp_runs.values()),
  content_stamp_range_by_group={k:list(v) for k,v in stamp_range.items()}, outcomes_by_group_suite={k:dict(v) for k,v in sorted(outc.items())},
  cc07_181=dict({k:dict(v) for k,v in c181.items()}), cc07_161_banking_ut5=dict(c161), slack_it5=dict(slack_it5), workspace_ut13=dict(ws13),
  paired_with_drift_head=dict({k:dict(v) for k,v in pair.items()}), pact_vs_head_same_cells=dict(pact_head))
json.dump(o,open(sys.argv[3],'w'),indent=1,sort_keys=True); print(json.dumps(o,sort_keys=True))
