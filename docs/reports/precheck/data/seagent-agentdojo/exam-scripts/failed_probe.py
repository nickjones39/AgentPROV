"""Skeletons (roles, call counts, link state) of the failed scratch executions; no content values."""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import C, raw, calls_of, result_id
rows = [json.loads(l) for l in open(os.path.join(C, 'executions.jsonl'))]
lab = {}
for l in open(os.path.join(C, 'raw', 'members.jsonl')):
    r = json.loads(l)
    if r.get('sha256'): lab[r['sha256'].split(':')[-1]] = r['label']
out = []
for r in rows:
    if r['status'] != 'failed': continue
    sha = r['raw'][0]['sha256'].split(':')[-1]
    x = raw(sha); ms = x['messages']
    res = {result_id(m) for m in ms if m.get('role') == 'tool'}
    sk = []
    for i, m in enumerate(ms):
        cs = calls_of(m)
        e = m['role'][0]
        if cs: e += '[' + ','.join(('+' if c.get('id') in res else '-') + c['function'] for c in cs) + ']'
        if m['role'] == 'tool': e += '(' + (m.get('tool_call') or {}).get('function', '?') + (',err' if m.get('error') else '') + ')'
        sk.append(e)
    out.append({'label': '/'.join(lab.get(sha, '?').split('/')[5:]), 'issues': r['issues'], 'skeleton': ' '.join(sk)})
print(json.dumps(out, indent=1))
