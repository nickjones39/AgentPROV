"""OS-1 population tally per arm x suite from L1 unit rows (raw outcome fields)."""
import json, sys, os
from collections import defaultdict, Counter
sys.path.insert(0, 'tools/analysis2')
from exam2_lib import wilson
rows = [json.loads(l) for l in open(os.path.expanduser('~/.agentprov/migration-work/precheck/mohameduk-agentdojo/l1-units-head.jsonl'))]
T = defaultdict(Counter)
for r in rows:
    f = r['facets']; o = r['outcomes']
    k = (f['pipeline_dir'], f['attack_dir'], f['suite'])
    T[k]['n'] += 1; T[k]['sec'] += bool(o['security']); T[k]['uti'] += bool(o['utility']); T[k]['err'] += bool(o['error_present'])
    for kk in [(f['pipeline_dir'], f['attack_dir'], 'all')]:
        T[kk]['n'] += 1; T[kk]['sec'] += bool(o['security']); T[kk]['uti'] += bool(o['utility'])
out = {}
for k in sorted(T):
    c = T[k]; n = c['n']
    out['|'.join(k)] = {'n': n, 'security_true': c['sec'], 'utility_true': c['uti'], 'error_present': c['err'],
        'sec_wilson95': [round(x*100, 2) for x in wilson(c['sec'], n)], 'uti_wilson95': [round(x*100, 2) for x in wilson(c['uti'], n)]}
    print('|'.join(k), n, 'sec', c['sec'], 'uti', c['uti'])
json.dump(out, open(sys.argv[1], 'w'), indent=1, sort_keys=True)
