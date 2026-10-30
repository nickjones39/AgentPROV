"""Read-only counts over the stored rope-p10.partial AER (H-09 executions, H-10 versions, H-11, H-20 recount). Counts only."""
import json, collections, hashlib
from pathlib import Path
O = Path('~/.agentprov/corpora/rope-p10.partial').expanduser()
C = collections.Counter
var, slack, bver = C(), C(), C()
g_with, g_without = collections.defaultdict(int), collections.defaultdict(int)
for l in (O / 'executions.jsonl').read_bytes().splitlines():
    r = json.loads(l); lines = (O / r['paths']['aer']).read_bytes().splitlines()
    recs = [json.loads(x) for x in lines]; e = recs[0]; seg = e['artifacts'][0]['origin']['path'].split('/')
    v = {((a.get('ext') or {}).get('rope') or {}).get('query_echo') for a in recs if a['k'] == 'decision'}
    for q in v: var[f'executions:{q}'] += 1
    if seg[1] == 'gpt-4o':
        for q in v: var[f'gpt-4o:{seg[-2]}:{q}'] += 1
    b = recs[1]; bver[(seg[-2] == 'agentlab_longhorizon', b.get('version'), (b.get('code') or {}).get('dist_version'))] += 1
    if seg[-4] == 'slack':
        calls = {f"{a['id']}#{i}": p.get('name') for a in recs if a['k'] == 'message' for i, p in enumerate(a.get('parts') or []) if p.get('t') == 'tool_call'}
        denied = {calls.get(a.get('subject')) for a in recs if a['k'] == 'decision'}
        util = any(a['k'] == 'judgement' and a.get('name') == 'utility' and not a.get('revises') for a in recs)
        slack[f"denied_post_webpage={'post_webpage' in denied}|utility_present={util}"] += 1
    msgs = [[a.get('role'), a.get('parts')] for a in recs if a['k'] == 'message']
    if msgs:
        g_with[hashlib.sha256(json.dumps(msgs, sort_keys=True).encode()).hexdigest()] += 1
        st = [[m[0], [{k: v for k, v in q.items() if k != 'provider_call_id'} for q in (m[1] or [])]] for m in msgs]
        g_without[hashlib.sha256(json.dumps(st, sort_keys=True).encode()).hexdigest()] += 1
print('denial variants', dict(var)); print('slack', dict(slack)); print('benchmark version', dict(bver))
for n, g in (('with_provider_ids', g_with), ('without_provider_ids', g_without)):
    print(n, sum(1 for v in g.values() if v > 1), sum(v for v in g.values() if v > 1))
