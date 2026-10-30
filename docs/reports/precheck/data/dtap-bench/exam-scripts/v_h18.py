import collections, json, re, sys
from agentprov.ingest.limits import MIB, IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.paths import open_evidence
runs, xp, out = sys.argv[1:4]; LIM = IngestLimits().replace(max_json_bytes=512 * MIB)
def flat(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items(): yield from flat(v, f"{p}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o): yield from flat(v, f"{p}/{i}")
    else: yield p, o
def norm(p): return re.sub(r"/\d+", "/*", p)
diff = collections.Counter(); n = 0; tsdelta = []; sameagenttext = 0; modelfield = collections.Counter(); ident_judge = 0
for g in json.load(open(xp))["xpair_labels"]:
    ds = []
    for l in g:
        with open_evidence(runs, l, LIM) as h: ds.append(strict_json_loads(h.read()))
    if len(ds[0].get("trajectory") or []) <= 3: continue
    n += 1
    a, b = dict(flat(ds[0])), dict(flat(ds[1]))
    for k in set(a) | set(b):
        if a.get(k) != b.get(k): diff[norm(k)] += 1
    for k in a:
        if re.search(r"model", k, re.I) and isinstance(a[k], str): modelfield[(norm(k), a[k] == b.get(k))] += 1
    jd = []
    for l in g:
        jl = "/".join(l.split("/")[:-1]) + "/judge_result.json"
        try:
            with open_evidence(runs, jl, LIM) as h: jd.append(h.read())
        except Exception: jd.append(None)
    ident_judge += jd[0] is not None and jd[0] == jd[1]
print(n); print(json.dumps(sorted(diff.items(), key=lambda x: -x[1])[:25]))
print(modelfield); print("judge bytes identical", ident_judge)
json.dump({"groups": n, "differing_pointers": dict(diff), "model_fields": {str(k): v for k, v in modelfield.items()}, "judge_bytes_identical": ident_judge}, open(out, "w"), indent=1)
