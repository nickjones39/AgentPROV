"""OS-2: raw outcomes of the 200 sampled labels (L1 rows) per defence x metric vs the mapped L2 arms (l2-head.json, summed
over model ids), plus post-stratified population references from os1-population.json. Counts only."""
import collections, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import units
D = sys.argv[1]
samp = set(json.load(open(os.path.join(D, 'l2-sample-head.json')))['labels'])
l2 = json.load(open(os.path.join(D, 'l2-head.json')))['outcomes']['arms']
DEF = {'agentspec': 'agentspec', 'baseline': 'none', 'pvagent': 'pvagent', 'seagent': 'seagent-initial', 'seagent-rf': 'seagent-refined'}
raw = collections.Counter(); mapped = collections.Counter()
for u in units():
    if u['label'] not in samp: continue
    f = u['facets']; d = DEF[f['arm'].lower()]; o = u['outcomes']
    if f['kind'] == 'security' and f['file'] != 'none':
        raw[f'{d}|asr|n'] += 1; raw[f'{d}|asr|k'] += bool(o['security']); raw[f'{d}|uua|k'] += bool(o['utility'])
    elif f['kind'] == 'perf':
        raw[f'{d}|benign|n'] += 1; raw[f'{d}|benign|k'] += bool(o['utility'])
    else: raw[f'{d}|prepass|n'] += 1
for arm, v in l2.items():
    m, d, a = arm.split('|')
    if a == 'important_instructions':
        mapped[f'{d}|asr|n'] += v['attack_success']['n']; mapped[f'{d}|asr|k'] += v['attack_success']['k']; mapped[f'{d}|uua|k'] += v['utility']['k']
    else:
        mapped[f'{d}|nonattacked_user|n'] += v['utility_user_tasks']['n']; mapped[f'{d}|nonattacked_user|k'] += v['utility_user_tasks']['k']
        mapped[f'{d}|prepass|n'] += v.get('prepass_runs', 0)
out = {'raw_sample': dict(sorted(raw.items())), 'mapped_sample': dict(sorted(mapped.items())),
       'asr_uua_raw_eq_mapped': all(raw[f'{d}|{x}'] == mapped[f'{d}|{x}'] for d in DEF.values() for x in ('asr|n', 'asr|k', 'uua|k'))}
json.dump(out, open(os.path.join(D, 'os2-sample.json'), 'w'), indent=1); print(json.dumps(out))
