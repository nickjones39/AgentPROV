"""H4: REVIEW holds by arm, 10-minute block and tool; logs whose every governed (refused or executed) call is REVIEW."""
import sys, os, json
from collections import Counter, defaultdict
sys.path.insert(0, 'src')
from agentprov.ingest.loaders import strict_json_loads
W = os.path.expanduser('~/.agentprov/migration-work/precheck/mohameduk-agentdojo')
root = os.path.expanduser('~/.agentprov/staging/10c/mohameduk/agentdojo-3f9d69a1ea96b75e8695653ceee8c3ff088db9b3')
blk = defaultdict(Counter); tool = Counter(); allrev = Counter(); per_log = Counter()
for l in open(f'{W}/l1-units-head.jsonl'):
    r = json.loads(l); f = r['facets']; pd = f['pipeline_dir']
    if not pd.endswith(('ubag', 'ubag_behavioral')): continue
    d = strict_json_loads(open(os.path.join(root, r['label']), 'rb').read())
    ts = (d.get('evaluation_timestamp') or '')[:15]
    rev = tot = 0
    for m in d['messages']:
        if m.get('role') != 'tool': continue
        tot += 1
        if m.get('error') == 'ubag-blocked: REVIEW':
            rev += 1; tool[(pd.split('-')[-1], (m.get('tool_call') or {}).get('function'))] += 1
    blk[pd][ts] += rev
    if rev: per_log[pd] += 1
    if rev and rev == tot: allrev[pd] += 1
out = {'logs_with_review': dict(per_log), 'logs_all_tool_msgs_review': dict(allrev),
       'max_review_in_10min_block': {pd: max(c.values()) for pd, c in blk.items()},
       'blocks_with_review': {pd: sum(1 for v in c.values() if v) for pd, c in blk.items()},
       'blocks': {pd: len(c) for pd, c in blk.items()},
       'top_tools': [(f'{a}|{b}', n) for (a, b), n in tool.most_common(8)]}
json.dump(out, open(sys.argv[1], 'w'), indent=1, sort_keys=True); print(json.dumps(out, indent=1))
