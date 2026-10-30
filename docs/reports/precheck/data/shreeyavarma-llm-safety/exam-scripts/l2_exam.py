import json, sys, collections, os
from pathlib import Path
C=collections.Counter
corp=Path(sys.argv[1]); sample=json.load(open(sys.argv[2])); units={json.loads(l)['label']:json.loads(l) for l in open(sys.argv[3])}
by_sha={('sha256:'+v):k for k,v in sample['sha256'].items()}
out=[]; agg=C(); semk=C(); judg_cmp=C(); origins=C(); unk_text=C()
for l in open(corp/'executions.jsonl'):
    e=json.loads(l); label=by_sha[e['raw'][0]['sha256']]; u=units[label]
    recs=[json.loads(x) for x in open(corp/e['paths']['aer'])]
    kinds=C(r.get('k') for r in recs)
    j={r['name']:(r['value'],r['origin']) for r in recs if r.get('k')=='judgement' or ('name' in r and 'value' in r and 'origin' in r)}
    seal=[r for r in recs if 'accounting' in r]
    issues=sorted({i['code'] for s in seal for i in s.get('issues',[])})
    agent=[r for r in recs if r.get('kind')=='llm_agent']
    model_unk=agent[0].get('unk',{}).get('/model') if agent else None
    model=agent[0].get('model') if agent else None
    asst=[r for r in recs if r.get('role')=='assistant' and 'parts' in r]
    for a in asst:
        unk_text[(u['facets']['pipeline_dir'], a.get('unk',{}).get('/parts/0/text'), len(a.get('parts',[])), bool(a.get('ext',{}).get('agentdojo',{}).get('calls_form')))]+=1
    # raw vs mapped
    for m in ('utility','security'):
        rv=u['outcomes'].get(m); mv=j.get(m,(None,None))[0]
        judg_cmp[(m, str(rv), str(mv))]+=1
        if m in j: origins[(m,j[m][1], u['facets']['attack_dir'])]+=1
    semf=corp/e['paths']['sem']['agentdojo.suites@2']
    sem=[json.loads(x) for x in open(semf)]
    for s in sem:
        semk[(u['facets']['pipeline_dir'], u['facets']['attack_dir'], s.get('k') or s.get('type'), str(s.get('value') if not isinstance(s.get('value'),(dict,list)) else type(s.get('value')).__name__)[:40])]+=1
    out.append({'label':label,'status':e['status'],'unit':e['unit'],'observed':e['execution_observed'],'completeness':e['completeness'],
                'issues':issues,'kinds':dict(kinds),'judgements':{k:list(v) for k,v in j.items()},'model':model,'model_unk':model_unk})
print(json.dumps({'judgement_raw_vs_mapped':{'|'.join(k):v for k,v in judg_cmp.items()},
  'origins':{'|'.join(k):v for k,v in origins.items()},
  'assistant_text_unk':{str(k):v for k,v in unk_text.items()},
  'sem_kinds':{str(k):v for k,v in sorted(semk.items())}},indent=1))
json.dump(out,open(sys.argv[4],'w'),indent=1)
