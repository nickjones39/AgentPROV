"""L1-04 trajectory-identical groups (CC-01 fingerprint) split by arm span and attack class; counts only."""
import collections, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import units
g = collections.defaultdict(list)
for u in units(): g[u['fp']].append(u['facets'])
c = collections.Counter()
for fp, fs in g.items():
    if len(fs) < 2: continue
    arms = {f['arm'].lower() for f in fs}; att = {f['attack_class'] for f in fs}; files = {f['file'] for f in fs}
    c['groups'] += 1; c['units'] += len(fs)
    c[f"span_arms={'multi' if len(arms) > 1 else 'one'}|attack={'+'.join(sorted(att))}"] += 1
    if 'attacked' in att and len(arms) > 1: c['attacked_multi_arm_units'] += len(fs)
    if len(files) > 1 and att == {'attacked'}: c['attacked_groups_differing_injection_task'] += 1
    c[f"pipelines={len({f['h_pipeline'] for f in fs})}"] += 1
r = dict(sorted(c.items())); json.dump(r, open(sys.argv[1], 'w'), indent=1); print(r)
