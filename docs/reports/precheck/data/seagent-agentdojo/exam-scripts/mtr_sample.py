"""How many sampled labels are among the population logs with a non-final call left without a result (the
missing_tool_result rule of the family mapper); counts only."""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import units, raw, result_id
samp = set(json.load(open(sys.argv[1]))['labels']); n = s = 0
for u in units():
    ms = raw(u['sha256'])['messages']; res = {result_id(m) for m in ms if m.get('role') == 'tool'}
    asst = [i for i, m in enumerate(ms) if m.get('role') == 'assistant']; hit = False
    for i in asst[:-1]:
        cs = ms[i].get('tool_calls') or []; j = i + 1; nr = 0
        while j < len(ms) and ms[j].get('role') == 'tool': nr += 1; j += 1
        hit |= any(c.get('id') not in res and k >= nr for k, c in enumerate(cs))
    n += hit; s += hit and u['label'] in samp
print(json.dumps({'population_logs': n, 'sampled_among_them': s}))
