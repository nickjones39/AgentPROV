"""OS-1 population outcomes per run directory (labels deduplicated across parts), Wilson 95%, vs the harness summaries.
usage: python3 -I os1.py <out.json>"""
import json, os, sys, math, collections
W=os.path.expanduser('~/.agentprov/migration-work/precheck/kavach-agentdojo')
def wilson(k,n,z=1.959963984540054):
    if n==0: return [None,None]
    p=k/n; d=1+z*z/n; c=p+z*z/(2*n); h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)); return [round(100*(c-h)/d,2),round(100*(c+h)/d,2)]
REF={'results_v2/agentdojo_slack_gemma_dell/logs/local':(0.0476,0.0),'results_v2/agentdojo_slack_gemma_dell/logs/local-kavach':(0.0,0.0),
'results_v2/agentdojo_workspace_forced/logs/local':(0.0482,0.0),'results_v2/agentdojo_workspace_forced/logs/local-kavach':(0.0,0.0),
'results_v2/agentdojo_workspace_not_forced2/logs/local':(0.0196,0.0179),'results_v2/agentdojo_workspace_not_forced2/logs/local-kavach':(0.0,0.0)}
seen=set(); A=collections.defaultdict(collections.Counter)
for part in ('main','nav-fixer2','rearch-forcedformat-fix'):
    for l in open(f'{W}/l1-units-{part}.jsonl'):
        x=json.loads(l)
        if x['label'] in seen: continue
        seen.add(x['label']); f=x['facets']
        if f['attack_dir']=='none': continue
        a=A[f['model_dir']]; o=x['outcomes']
        if o['utility'] is None: a['null']+=1; continue
        a['n']+=1; a['u']+=o['utility']; a['s']+=o['security']
rows=[]
for md,a in sorted(A.items()):
    n=a['n']; ref=REF.get(md)
    r=dict(dir=md,n=n,null=a['null'],utility_k=a['u'],utility=round(100*a['u']/n,2),utility_w=wilson(a['u'],n),asr_k=a['s'],asr=round(100*a['s']/n,2),asr_w=wilson(a['s'],n))
    if ref:
        r['ref_utility']=round(100*ref[0],2); r['ref_asr']=round(100*ref[1],2)
        r['gap_utility_pp']=round(r['utility']-r['ref_utility'],2); r['gap_asr_pp']=round(r['asr']-r['ref_asr'],2)
        r['flag']= any(abs(g)>15 for g in (r['gap_utility_pp'],r['gap_asr_pp'])) or not (r['utility_w'][0]-5<=r['ref_utility']<=r['utility_w'][1]+5) or not (r['asr_w'][0]-5<=r['ref_asr']<=r['asr_w'][1]+5)
    rows.append(r)
json.dump(rows,open(sys.argv[1],'w'),indent=1)
for r in rows: print(json.dumps(r))
