import json,collections,sys
from pathlib import Path
corp=Path(sys.argv[1]); sample=json.load(open(sys.argv[2])); units={json.loads(l)['label']:json.loads(l) for l in open(sys.argv[3])}
by_sha={('sha256:'+v):k for k,v in sample['sha256'].items()}
per=collections.Counter(); keys=collections.Counter()
for l in open(corp/'executions.jsonl'):
    e=json.loads(l); lab=by_sha[e['raw'][0]['sha256']]; u=units[lab]; f=u['facets']
    if f['attack_dir']!='tool_knowledge': continue
    st=collections.Counter()
    for x in open(corp/e['paths']['sem']['agentdojo.suites@2']):
        r=json.loads(x)
        if r.get('k')=='ann' and r['type']=='injection_marker':
            v=r['value']; keys[tuple(sorted(v))]+=1; st[v.get('status')]+=1
    per[(f['pipeline_dir'], lab.split('/')[-1], str(u['outcomes'].get('security')), json.dumps(dict(st)))]+=1
print(dict(keys))
for k,v in sorted(per.items()): print(v,k)
