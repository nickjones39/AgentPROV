import json, sys, collections
from pathlib import Path
NEW = Path(sys.argv[1]).expanduser(); OLD = Path('~/.agentprov/corpora/rope-p10.partial').expanduser(); OUT = sys.argv[2]
L1 = {}
for l in open(Path('~/.agentprov/migration-work/precheck/rope/l1-units-head.jsonl').expanduser()):
    r = json.loads(l); L1[r['label']] = r
C = collections.Counter
def rows(p): return {r["ex"]: r for r in (json.loads(x) for x in (p / "executions.jsonl").read_bytes().splitlines() if x)}
new = rows(NEW); old = rows(OLD)
res = collections.defaultdict(C); per = []
def recs(p): return [json.loads(x) for x in p.read_bytes().splitlines() if x]
for ex, rn in sorted(new.items()):
    A = recs(NEW / rn['paths']['aer']); e = A[0]
    label = e['artifacts'][0]['origin']['path']; l1 = L1[label]
    t = e['task']; f = l1['facets']
    J = {(j['name'], j.get('origin'), bool(j.get('revises'))): j['value'] for j in A if j['k'] == 'judgement'}
    ru = J.get(('utility', 'checker', False)); rs = J.get(('security', 'checker', False), J.get(('security', 'harness_default', False)))
    rc = J.get(('security', 'recomputed', True))
    o = l1['outcomes']
    res['raw_vs_mapped'][f"utility:{o['utility']==ru}"] += 1; res['raw_vs_mapped'][f"security:{o['security']==rs}"] += 1
    ninj = (f['suite'], f['file']) in {('slack','injection_task_5'),('dailylife','injection_task_7'),('github','injection_task_1')}
    res['recomputed'][f"present={rc is not None}|corrected_task={ninj}|attacked={f['attack_dir']!='none'}"] += 1
    if rc is not None: res['recomputed_change'][f"{rs}->{rc}"] += 1
    acts = [a for a in A if a['k'] == 'activity']; fx = {a['id'] for a in A if a['k'] == 'fixture'}
    attacked = f['attack_dir'] != 'none'
    res['load_env'][f"attacked={attacked}|n_act={len(acts)}|inputs_eq_fixtures={bool(acts) and set(acts[0]['inputs'])==fx}|ev={acts[0]['ev'] if acts else '-'}"] += 1
    mc = [a for a in A if a['k'] == 'model_call']
    res['params'][f"model_calls_with_params_not_recorded"] += sum(1 for m in mc if (m.get('unk') or {}).get('/params') == 'not_recorded')
    res['params']['model_calls'] += len(mc)
    res['rules_hdr'][json.dumps(e['rules'], sort_keys=True) + '|' + f['attack_dir']] += 1
    seal = A[-1]
    for i in seal.get('issues') or []: res['seal_issue_by_arm'][f"{i.get('code')}|{f['model_dir']}|{f['attack_dir']}"] += 1
    res['completeness'][rn['completeness']] += 1
    res['model_map'][f"{f['model_dir']}->{next((a.get('model',{}).get('requested') for a in A if a['k']=='actor' and a['id']=='agent'), None)}"] += 1
    # SEM
    S = [a for a in recs(NEW / list(rn['paths']['sem'].values())[0]) if a.get('k')=='ann']
    so = old.get(ex); So = [a for a in recs(OLD / list(so['paths']['sem'].values())[0]) if a.get('k')=='ann'] if so else []
    ms = C(a['value']['status'] for a in S if a['type'] == 'injection_marker'); mo = C(a['value']['status'] for a in So if a['type'] == 'injection_marker')
    for k in set(ms) | set(mo): res['marker_status_new' ][k] += ms[k]; res['marker_status_old'][k] += mo[k]
    # per-marker transition by (target, fixture)
    key = lambda a: (a['target'], a['value']['fixture'], a.get('at'))
    dn = {key(a): a['value']['status'] for a in S if a['type'] == 'injection_marker'}; do = {key(a): a['value']['status'] for a in So if a['type'] == 'injection_marker'}
    for k in set(dn) | set(do): 
        if dn.get(k) != do.get(k): res['marker_transition'][f"{do.get(k)}->{dn.get(k)}|{f['attack_dir']}"] += 1
    if f['attack_dir'] == 'autodojo':
        res['autodojo_present'][f"new:{ms['present']>0}"] += 1; res['autodojo_present'][f"old:{mo['present']>0}"] += 1
    if attacked:
        res['attacked_present'][f"{f['attack_dir']}|new:{ms['present']>0}|old:{mo['present']>0}"] += 1
    for a in S:
        if a['type'] in ('agentdojo.success_without_visible_payload', 'agentdojo.partial_payload'):
            res['ns_ann'][f"{a['type']}|{f['attack_dir']}|{a['ev']}"] += 1
        if a['type'] == 'role':
            fam = 'agentdyn' if f['suite'] in ('github','shopping','dailylife') else 'agentdojo'
            res['role'][f"{fam}|unknown={a['value']==['unknown']}"] += 1
        res['sem_ev'][f"{a['type']}|{a['ev']}"] += 1
    swvp = [a for a in S if a['type'] == 'agentdojo.success_without_visible_payload']
    if swvp: res['swvp_labels'][label] += 1
    for a in A:
        res['aer_ev'][f"{a['k']}|{a.get('ev')}"] += 1
    per.append({'label': label, 'stratum': l1['stratum'], 'raw_u': o['utility'], 'raw_s': o['security'], 'aer_u': ru, 'aer_s': rs, 'aer_s_corr': rc if rc is not None else rs, 'attacked': attacked, 'model_dir': f['model_dir'], 'attack_dir': f['attack_dir'], 'suite': f['suite']})
out = {k: dict(sorted(v.items())) for k, v in res.items()}
json.dump({'summary': out, 'per': per}, open(OUT, 'w'), indent=1)
print(json.dumps(out, indent=1))
