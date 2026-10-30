"""Shared reader for seagent-agentdojo exam scripts: raw objects of the scratch L2 corpus (content-addressed,
sha256-checked) parsed through agentprov.ingest; L1 unit rows for labels/facets. Counts and skeletons only."""
import hashlib, json, os
from agentprov.ingest.loaders import strict_json_loads
W = os.path.expanduser('~/.agentprov/migration-work/precheck/seagent-agentdojo')
C = os.path.join(W, 'l2-head-j2.partial')
def units():
    with open(os.path.join(W, 'l1-units-head.jsonl')) as f:
        return [json.loads(l) for l in f if l.strip()]
def raw(sha):
    p = os.path.join(C, 'raw', 'objects', sha[:2], sha + '.json')
    b = open(p, 'rb').read()
    assert hashlib.sha256(b).hexdigest() == sha, 'digest'
    return strict_json_loads(b)
def calls_of(m):
    tc = m.get('tool_calls') or []
    return tc
def result_id(m):
    if m.get('role') != 'tool': return None
    tc = m.get('tool_call') or {}
    return m.get('tool_call_id') or tc.get('id')
