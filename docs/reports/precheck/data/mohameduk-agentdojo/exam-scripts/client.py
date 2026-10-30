"""Client-version evidence: per (pipeline_dir, attack_dir) time range, and multi-call turns with all-null ids split by
whether the tool messages keep distinct positional echoes (no collapse) or repeat one (by_id collapse)."""
import sys, os, json
from collections import Counter, defaultdict
sys.path.insert(0, 'src')
from agentprov.ingest.loaders import strict_json_loads
W = os.path.expanduser('~/.agentprov/migration-work/precheck/mohameduk-agentdojo')
root = os.path.expanduser('~/.agentprov/staging/10c/mohameduk/agentdojo-3f9d69a1ea96b75e8695653ceee8c3ff088db9b3')
lex = lambda v: json.dumps(v, sort_keys=True)
T = defaultdict(list); M = defaultdict(Counter)
for l in open(f'{W}/l1-units-head.jsonl'):
    r = json.loads(l); lab = r['label']; f = r['facets']
    d = strict_json_loads(open(os.path.join(root, lab), 'rb').read()); msgs = d['messages']
    key = f"{f['pipeline_dir']}|{f['attack_dir']}"
    T[key].append(d.get('evaluation_timestamp'))
    for i, m in enumerate(msgs):
        calls = m.get('tool_calls') or []
        if m.get('role') != 'assistant' or len(calls) < 2: continue
        if not all(c.get('id') in (None, '') for c in calls): continue
        if len({lex([c.get('function'), c.get('args')]) for c in calls}) < 2: continue   # distinct calls only
        results = []; j = i + 1
        while j < len(msgs) and msgs[j].get('role') == 'tool': results.append(msgs[j]); j += 1
        echoes = [lex([(x.get('tool_call') or {}).get('function'), (x.get('tool_call') or {}).get('args')]) for x in results]
        M[key]['distinct_null_id_multicall_turns'] += 1
        if len(set(echoes)) < len(echoes): M[key]['collapsed'] += 1
        else: M[key]['positional_ok'] += 1
out = {k: {'n': len(v), 'ts_min': min(v), 'ts_max': max(v), **M.get(k, {})} for k, v in sorted(T.items())}
json.dump(out, open(sys.argv[1], 'w'), indent=1, sort_keys=True); print(json.dumps(out, indent=1, sort_keys=True))
