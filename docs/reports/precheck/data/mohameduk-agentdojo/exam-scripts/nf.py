import sys, os, json
from collections import Counter
sys.path.insert(0, 'src')
from agentprov.ingest.loaders import strict_json_loads
W = os.path.expanduser('~/.agentprov/migration-work/precheck/mohameduk-agentdojo')
root = os.path.expanduser('~/.agentprov/staging/10c/mohameduk/agentdojo-3f9d69a1ea96b75e8695653ceee8c3ff088db9b3')
c = Counter(); allc = Counter()
for l in open(f'{W}/l1-units-head.jsonl'):
    r = json.loads(l)
    d = strict_json_loads(open(os.path.join(root, r['label']), 'rb').read())
    last = next((m for m in reversed(d['messages']) if m.get('role') == 'assistant'), None)
    v = last.get('content') if last else 'NOASSISTANT'
    if v is None: form = 'null'
    elif v == [] : form = 'empty_list'
    elif v == '': form = 'empty_str'
    elif isinstance(v, list) and all(isinstance(b, dict) and b.get('content') in ('', None) for b in v): form = f'blocks_all_empty({len(v)})'
    else: form = 'text'
    form += '|calls' if last and last.get('tool_calls') else ''
    allc[form] += 1
    if 'null_final' in r['flags']: c[form] += 1
print('null_final flagged:', dict(c)); print('all last-assistant forms:', dict(allc))
