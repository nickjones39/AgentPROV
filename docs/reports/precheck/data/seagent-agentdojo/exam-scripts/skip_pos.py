"""Position of the guard-skipped calls in a blocked batch (before / after the `*BLOCKED_BY_SEAGENT` call); logs per class
and per arm. Counts only."""
import collections, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import units, raw, result_id
BL = 'BLOCKED_BY_SEAGENT'; o = collections.Counter()
for u in units():
    a = u['facets']['arm'].replace('seagent-rf', 'seagent-RF'); ms = raw(u['sha256'])['messages']
    res = {result_id(m) for m in ms if m.get('role') == 'tool'}; before = after = 0
    for m in ms:
        cs = m.get('tool_calls') or []
        b = [k for k, c in enumerate(cs) if str(c.get('function', '')).endswith(BL)]
        if not b: continue
        for k, c in enumerate(cs):
            if c.get('id') in res: continue
            if k < b[0]: before += 1
            else: after += 1
    if before or after:
        o[f'logs|before={bool(before)}|after={bool(after)}'] += 1; o[f'calls_before|{a}'] += before; o[f'calls_after|{a}'] += after
r = dict(sorted(o.items())); json.dump(r, open(sys.argv[1], 'w'), indent=1); print(r)
