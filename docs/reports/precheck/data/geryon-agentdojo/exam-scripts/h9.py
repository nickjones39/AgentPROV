"""H9: identity of the condition-B run sets in the j2 sample (agent model, defence actor and its unk fields), and SEM /
execution-ext mentions that would distinguish them. Counts only."""
import json, collections
from pathlib import Path
W = Path.home() / ".agentprov/migration-work/precheck/geryon-agentdojo"
L1 = {json.loads(l)['sha256']: json.loads(l) for l in open(W / 'l1-units-head.jsonl')}
C = W / 'l2-head-j2.partial'
c = collections.Counter()
for line in open(C / 'executions.jsonl'):
    r = json.loads(line)
    u = L1[r['raw'][0]['sha256'].split(':')[1]]
    rs, ls = u['facets']['model_dir'].split('/')
    if '-B-' not in ls:
        continue
    aer = [json.loads(x) for x in open(C / r['paths']['aer'])]
    sem = open(C / r['paths']['sem']['agentdojo.suites@2']).read().lower()
    d0 = [x for x in aer if x['k'] == 'actor' and x.get('kind') == 'defense']
    ag = [x for x in aer if x['k'] == 'actor' and x.get('kind') == 'llm_agent']
    c[(rs, d0[0]['name'], json.dumps(d0[0].get('unk'), sort_keys=True), ag[0]['model']['requested'])] += 1
    ext = json.dumps([x for x in aer if x['k'] == 'execution'][0].get('ext')).lower()
    for w in ('caveat', 'unusable', 'broken', 'policy', 'strong-policy', 'claude'):
        c[('mentions', rs, w)] += (w in sem) + (w in ext)
for k, v in sorted(c.items(), key=str):
    print(v, k)
