"""toolConfig digests per arm (Converse runs) and per request position; tool names per config. Digests and counts only."""
import sys, json, collections, re, hashlib
sys.path.insert(0, sys.argv[1]); from rawzip import members, runs, js
R = runs(members()); g = collections.defaultdict(collections.Counter); names = {}
for d, f in R.items():
    model, arm, num = re.fullmatch(r'(.+?)__(.+)__(\d{4})', d).groups()
    if num == '0001': continue
    for i, q in enumerate(js(f['request.json'])):
        t = q.get('toolConfig'); k = hashlib.sha256(json.dumps(t, sort_keys=True).encode()).hexdigest()[:8]
        g[k][f'{arm}@{"first" if i == 0 else "later"}'] += 1
        names[k] = [x.get('toolSpec', {}).get('name') for x in (t or {}).get('tools', [])] + sorted(set((t or {})) - {'tools'})
for k, v in g.items(): print(k, names[k], dict(sorted(v.items()))[:0] if False else sorted(v.items())[:12], 'total', sum(v.values()))
