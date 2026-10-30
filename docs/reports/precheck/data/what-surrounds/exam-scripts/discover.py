"""Shapes only: file-set sizes, meta key sets, results.csv header, tools_called.txt line shape (no values)."""
import sys, csv, io, json, collections, re
sys.path.insert(0, sys.argv[1]); from rawzip import members, runs, js
mem = members(); R = runs(mem)
print('members', len(mem), 'rundirs', len(R))
print('filesets', collections.Counter(tuple(sorted(v)) for v in R.values()).most_common())
print('meta keysets', collections.Counter(tuple(sorted(js(v['meta.json']))) for v in R.values()).most_common())
t = mem['results.csv'].decode('utf-8'); rows = list(csv.DictReader(io.StringIO(t, newline='')))
print('csv header', list(rows[0].keys()), 'rows', len(rows))
for k in rows[0]:
    vals = collections.Counter(r[k] for r in rows)
    print(' col', k, 'distinct', len(vals), (sorted(vals.items())[:8] if len(vals) < 9 else ''))
tc = [v.get('tools_called.txt') for v in R.values()]
print('tools_called present', sum(x is not None for x in tc))
shape = collections.Counter(re.sub(r'[A-Za-z0-9]', 'x', l)[:40] for x in tc if x for l in x.decode().splitlines()[:1])
print('tc first-line shapes', shape.most_common(5))
