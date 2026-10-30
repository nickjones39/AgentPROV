"""Skeletons (roles, call link state, tool-result error flag) of selected logs: banking UT5 per arm, agentspec slack IT5
successes, the null-final log. Function names only; no content values."""
import collections, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import units, raw, result_id
def sk(ms):
    res = {result_id(m) for m in ms if m.get('role') == 'tool'}; o = []
    for m in ms:
        e = m['role'][0]; cs = m.get('tool_calls')
        if cs: e += '[' + ','.join(('+' if c.get('id') in res else '-') + c['function'] for c in cs) + ']'
        if m['role'] == 'assistant' and cs is None: e += '{nokey}'
        if m['role'] == 'tool': e += '(' + str((m.get('tool_call') or {}).get('function')) + (',err' if m.get('error') else '') + (',id' if result_id(m) else ',noid') + ')'
        o.append(e)
    return ' '.join(o)
seen = collections.Counter(); out = []
for u in units():
    f = u['facets']; a = f['arm']; x = raw(u['sha256'])
    tag = None
    if f['suite'] == 'banking' and f['task_dir'] == 'user_task_5' and f['kind'] == 'security' and seen[a + 'ut5'] < 1: tag = a + 'ut5'
    if a == 'agentspec' and f['suite'] == 'slack' and f['file'] == 'injection_task_5' and x.get('security') and seen['as5'] < 2: tag = 'as5'
    if f['suite'] == 'slack' and a == 'baseline' and 'null_final' in u.get('flags', []): tag = 'nf'
    if tag: seen[tag] += 1; out.append({'tag': tag, 'path': '/'.join(u['label'].split('/')[5:]), 'skeleton': sk(x['messages'])})
print(json.dumps(out, indent=1))
# null-final shape: type/length of the last assistant content (no values)
for u in units():
    if 'null_final' in u.get('flags', []):
        m = [m for m in raw(u['sha256'])['messages'] if m.get('role') == 'assistant'][-1]
        c = m.get('content')
        print('null_final_shape', type(c).__name__, [(b.get('type'), len(b.get('content') or '')) for b in c] if isinstance(c, list) else c, 'error=', raw(u['sha256']).get('error') is None)
