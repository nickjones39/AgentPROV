"""H8: composition of L1 trajectory-identical groups (CC-01 fingerprint)."""
import sys, os, json
from collections import Counter, defaultdict
W = os.path.expanduser('~/.agentprov/migration-work/precheck/mohameduk-agentdojo')
G = defaultdict(list)
for l in open(f'{W}/l1-units-head.jsonl'):
    r = json.loads(l); f = r['facets']
    model = f['pipeline_dir'].removesuffix('-ubag_behavioral').removesuffix('-ubag')
    G[r['fp']].append((model, f['pipeline_dir'], f['suite'], f['task_dir'], f['attack_dir'], f['file'], r['label']))
c = Counter(); repeats = Counter(); pairs = Counter()
for fp, m in G.items():
    if len(m) < 2: continue
    c['groups'] += 1; c['units_in_groups'] += len(m); c['repeats_beyond_first'] += len(m) - 1
    models = {x[0] for x in m}; dirs = {x[1] for x in m}
    cells = {(x[2], x[3], x[4], x[5]) for x in m}; utasks = {(x[2], x[3]) for x in m}
    if len(models) > 1: c['groups_cross_model'] += 1
    if len(utasks) > 1: c['groups_cross_user_task'] += 1
    if len(cells) == 1: c['groups_single_cell'] += 1; repeats['single_cell'] += len(m) - 1
    else:
        c['groups_multi_cell_same_user_task'] += 1; repeats['multi_cell'] += len(m) - 1
        if len({x[4] for x in m}) > 1: c['groups_attacked_and_benign'] += 1
    # cross-arm pairs on the same cell
    by_cell = defaultdict(set)
    for x in m: by_cell[(x[2], x[3], x[4], x[5])].add(x[1])
    for cell, ds in by_cell.items():
        if len(ds) > 1: pairs['|'.join(sorted(ds))] += 1
    c['dirs_in_group_' + str(len(dirs))] += 1
print(json.dumps({'counts': dict(c), 'repeats': dict(repeats), 'same_cell_cross_arm_dir_sets': dict(pairs.most_common())}, indent=1))
json.dump({'counts': dict(c), 'repeats': dict(repeats), 'same_cell_cross_arm_dir_sets': dict(pairs)}, open(sys.argv[1], 'w'), indent=1, sort_keys=True)
