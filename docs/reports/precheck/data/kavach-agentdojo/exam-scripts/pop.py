"""kavach-agentdojo population exam over the three pins (raw via agentprov.ingest; counts only).
usage: uv run python -I pop.py <out.json>"""
import sys, os, json, collections, hashlib, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rawread import tree, Reader, PINS
W=os.path.expanduser('~/.agentprov/migration-work/precheck/kavach-agentdojo')
C=collections.Counter; DD=lambda: collections.defaultdict(C)
def txt(c):
    if c is None: return None
    if isinstance(c,str): return c
    return ''.join((b.get('content') or '') for b in c if isinstance(b,dict))
def rundir(md):  # run directory without the pipeline dir
    return md.rsplit('/',1)[0]
BOUND={'agentdojo_slack_gemma_dell':'2026-07-06T13:22','banking_qwen25_7b':'2026-07-15T13:57','agentdojo_dell':'2026-07-16T12:38','agentdojo_llama3.1':'2026-07-16T12:38','agentdojo_forced_llama3.1':'2026-07-16T12:38','agentdojo_workspace_forced':'2026-07-16T13:01','agentdojo_workspace_forced2':'2026-07-16T13:01','agentdojo_workspace_not_forced':'2026-07-16T15:34','agentdojo_workspace_not_forced2':'2026-07-16T15:34','results_v2/logs':'2026-07-21T19:19'}
def bkey(md):
    if md.startswith('results_v2/logs/'): return 'results_v2/logs'
    return md.split('/')[1]
out={}; r=Reader()
rows={}; seen={}  # blob oid -> analysis (distinct)
per_part={}
for part,commit in PINS.items():
    t=tree(commit)
    L=[json.loads(l) for l in open(f'{W}/l1-units-{part}.jsonl')]
    per_part[part]=[(x, t['benchmarks/'+x['label'][len('benchmarks/'):]] ) for x in L]
# distinct union
sha_by_part={p:{x['sha256'] for x,_ in v} for p,v in per_part.items()}
U=set().union(*sha_by_part.values())
out['union_distinct_sha256']=len(U)
out['distinct_per_part']={p:len(s) for p,s in sha_by_part.items()}
out['overlap']={'main&nav':len(sha_by_part['main']&sha_by_part['nav-fixer2']),'main&rearch':len(sha_by_part['main']&sha_by_part['rearch-forcedformat-fix']),'nav&rearch':len(sha_by_part['nav-fixer2']&sha_by_part['rearch-forcedformat-fix']),'all3':len(set.intersection(*sha_by_part.values()))}
out['import_order_new']={'main':len(sha_by_part['main']),'nav-fixer2':len(sha_by_part['nav-fixer2']-sha_by_part['main']),'rearch-forcedformat-fix':len(sha_by_part['rearch-forcedformat-fix']-sha_by_part['main']-sha_by_part['nav-fixer2'])}
# H4: nav in-pin copies and rearch not_forced vs nav results_v2/logs/local
nav=per_part['nav-fixer2']; byS=collections.defaultdict(list)
for x,_ in nav: byS[x['sha256']].append(x)
grp=[g for g in byS.values() if len(g)>1]
pairdirs=C(); copy_out=C()
for g in grp:
    pairdirs['|'.join(sorted(rundir(x['facets']['model_dir']) for x in g))]+=1
    x=g[0]; copy_out[f"{x['facets']['task_kind']}|u={x['outcomes']['utility']}|s={x['outcomes']['security']}"]+=1
out['H4_nav_copies']={'groups':len(grp),'dir_pairs':dict(pairdirs),'outcomes_of_copies':dict(copy_out)}
logs_local={x['label'].split('results_v2/logs/local/')[1]:x['sha256'] for x,_ in nav if x['facets']['model_dir']=='results_v2/logs/local'}
forced_sha={x['sha256'] for x,_ in nav if x['facets']['model_dir']=='results_v2/agentdojo_workspace_forced/logs/local'}
nf={x['label'].split('agentdojo_workspace_not_forced/logs/local/')[1]:x for x,_ in per_part['rearch-forcedformat-fix'] if x['facets']['model_dir']=='results_v2/agentdojo_workspace_not_forced/logs/local'}
out['H4_notforced_vs_navlogs']={'not_forced':len(nf),'results_v2_logs_local':len(logs_local),'same_suffix_same_bytes':sum(1 for k,x in nf.items() if logs_local.get(k)==x['sha256']),
  'not_forced_equal_to_a_forced_log':sum(1 for x in nf.values() if x['sha256'] in forced_sha),
  'not_forced_equal_to_forced_by_kind_outcome':dict(C(f"{x['facets']['task_kind']}|u={x['outcomes']['utility']}|s={x['outcomes']['security']}" for x in nf.values() if x['sha256'] in forced_sha)),
  'not_forced_not_in_forced_by_kind_outcome':dict(C(f"{x['facets']['task_kind']}|u={x['outcomes']['utility']}|s={x['outcomes']['security']}" for x in nf.values() if x['sha256'] not in forced_sha))}
# H19: trajectory groups within part
h19={}
for part,v in per_part.items():
    byF=collections.defaultdict(list)
    for x,_ in v:
        if x['fp']: byF[x['fp']].append(x)
    gs=[g for g in byF.values() if len(g)>1]
    kinds=C(); dis=C()
    for g in gs:
        rd={rundir(x['facets']['model_dir']) for x in g}; pip={x['facets']['h_pipeline'] for x in g}
        cells={(x['facets']['task_dir'],x['facets']['file']) for x in g}
        k='same_dir_local+kavach_same_cell' if len(rd)==1 and pip=={'local','local-kavach'} and len(cells)==1 else ('same_cell_other' if len(cells)==1 else 'cross_cell')
        kinds[k]+=1
        oc={(x['outcomes']['utility'],x['outcomes']['security']) for x in g}
        dis['groups_outcome_disagree' if len(oc)>1 else 'agree']+=1
        if len(oc)>1: dis['disagree_'+k]+=1
    h19[part]={'groups':len(gs),'files':sum(len(g) for g in gs),'kinds':dict(kinds),'outcomes':dict(dis)}
out['H19']=h19
# raw pass over distinct blobs (first part seen)
A=DD(); ts_max={}; ts_min={}; sysd=C(); nf_detail=C(); ban0={}
done=set()
for part,v in per_part.items():
    for x,oid in v:
        if x['sha256'] in done: continue
        done.add(x['sha256'])
        f=x['facets']; md=f['model_dir']; kind=f['task_kind']; att=f['attack_dir']
        d=r.json(oid); msgs=d['messages']
        cell=f"{md}|{att}"
        a=A[cell]; a['n']+=1
        ntool=sum(1 for m in msgs if m.get('role')=='tool'); ncalls=sum(len(m.get('tool_calls') or []) for m in msgs)
        a['logs_with_tool_exec']+= ntool>0; a['tool_msgs']+=ntool; a['calls']+=ncalls
        den=0
        for m in msgs:
            if m.get('role')=='tool':
                s=(txt(m.get('content')) or '')+' '+str(m.get('error') or '')
                if '[KAVACH BLOCK' in s: den+=1
        a['denial_msgs']+=den; a['logs_with_denial']+= den>0
        a['denial_msgs_'+kind]+=den
        last=[m for m in msgs if m.get('role')=='assistant']
        lt=txt(last[-1].get('content')) if last else None
        if att!='none' and lt is not None and '<|tool_response>' in lt: a['last_asst_tool_response_token']+=1
        if lt is None or (lt.strip()=='' and not last[-1].get('tool_calls')):
            a['final_asst_empty_no_calls']+=1
            nf_detail[f"{bkey(md)}|content={'null' if lt is None else 'empty'}|last_role={msgs[-1].get('role')}"]+=1
        if lt is None: a['final_asst_content_null']+=1
        # system prompt digest
        if msgs and msgs[0].get('role')=='system':
            sysd[f"{bkey(md)}|{hashlib.sha256((txt(msgs[0]['content']) or '').encode()).hexdigest()[:8]}"]+=1
        a['bv_'+str(d.get('benchmark_version'))]+=1
        a['error_'+type(d.get('error')).__name__]+=1
        a['msg_error_present']+= any(m.get('error') for m in msgs)
        ts=d.get('evaluation_timestamp'); b=bkey(md)
        if ts:
            ts_max[b]=max(ts_max.get(b,ts),ts); ts_min[b]=min(ts_min.get(b,ts),ts)
        if 'incomplete' in x['flags']: a['incomplete']+=1
        if 'null_final' in x['flags']: a['l1_null_final']+=1
        if 'trailing_calls' in x['flags']: a['l1_trailing_calls']+=1
        if md.startswith('agentdojo_live/banking') and f['task_dir']=='user_task_0':
            ban0={'variant':x['variant'],'flags':x['flags'],'error_field':type(d.get('error')).__name__,'tool_msgs_with_error':sum(1 for m in msgs if m.get('role')=='tool' and m.get('error')),'n_msgs':len(msgs),'utility':d.get('utility'),'security':d.get('security')}
out['cells_distinct']={k:dict(v) for k,v in sorted(A.items())}
out['timestamps']={b:{'min':ts_min[b],'max':ts_max[b],'bound':BOUND[b],'max_le_bound':ts_max[b].replace(' ','T')[:16]<=BOUND[b]} for b in sorted(ts_max)}
out['system_prompt_digest']=dict(sysd); out['null_final_detail']=dict(nf_detail); out['banking_ut0']=ban0
json.dump(out,open(sys.argv[1],'w'),indent=1,sort_keys=True)
print(json.dumps(out)[:200])
