"""OS-2 mapping check for kavach-agentdojo L2 scratch corpora: mapped judgements vs raw L1 values (by sha256), identity, origins. Counts only.
usage: python3 -I os2.py <out.json>"""
import json, os, sys, collections
W=os.path.expanduser('~/.agentprov/migration-work/precheck/kavach-agentdojo'); C=collections.Counter
res={}
for part in ('main','nav-fixer2','rearch-forcedformat-fix'):
    l1=collections.defaultdict(list)
    for l in open(f'{W}/l1-units-{part}.jsonl'):
        x=json.loads(l); l1[x['sha256']].append(x)
    P=f'{W}/l2-{part}-j2.partial'; c=C(); kinds=C(); jor=C(); multi=[]
    for line in open(f'{P}/executions.jsonl'):
        e=json.loads(line); sha=e['raw'][0]['sha256'].split(':')[1]; rows=l1[sha]
        recs=[json.loads(l) for l in open(os.path.join(P,e['paths']['aer']))]
        js={}; model=None; paths=[]
        for r in recs:
            kinds[r.get('k')]+=1
            if r.get('k')=='judgement': js[r['name']]=r.get('value'); jor[f"{r['name']}|{r.get('origin')}"]+=1
            if r.get('k')=='actor' and r.get('id')=='agent': model=(r.get('model') or {}).get('requested')
            if r.get('k')=='execution': paths=[a['origin']['path'] for a in r.get('artifacts',[]) if a.get('role')=='primary']
        for m in ('utility','security'):
            rv={x['outcomes'][m] for x in rows}; c['compared']+=1; c['differ']+= (js.get(m) not in rv) or len(rv)>1
        if e.get('n_origins',1)>1:
            dirs=sorted({x['facets']['model_dir'].split('/')[1] if not x['facets']['model_dir'].startswith('results_v2/logs') else 'results_v2/logs' for x in rows})
            multi.append({'n_origins':e['n_origins'],'l1_dirs':dirs,'aer_primary_dir':[p.split('/')[2] for p in paths],'model':model})
    res[part]={'os2':dict(c),'record_kinds':dict(kinds),'judgement_origins':dict(jor),'multi_origin_executions':multi}
json.dump(res,open(sys.argv[1],'w'),indent=1)
for p,v in res.items(): print(p,json.dumps(v))
