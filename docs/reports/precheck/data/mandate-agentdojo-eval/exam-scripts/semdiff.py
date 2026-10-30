import json, sys, re, collections
from pathlib import Path
O = Path(sys.argv[1]).expanduser(); N = Path(sys.argv[2]).expanduser()
oi = {r["ex"]: r for r in map(json.loads, (O/"executions.jsonl").read_text().splitlines())}
def leaves(x, p=""):
    if isinstance(x, dict):
        for k, v in x.items(): yield from leaves(v, p + "/" + k)
    elif isinstance(x, list):
        for i, v in enumerate(x): yield from leaves(v, f"{p}/{i}")
    else: yield p, x
sig = collections.Counter(); exs = collections.defaultdict(set); markers = collections.Counter(); nrec = collections.Counter(); hdr = collections.Counter()
for l in (N/"executions.jsonl").read_text().splitlines():
    r = json.loads(l); o = oi[r["ex"]]
    a = {x["id"]: x for x in map(json.loads, (O/list(o["paths"]["sem"].values())[0]).read_text().splitlines())}
    b = {x["id"]: x for x in map(json.loads, (N/list(r["paths"]["sem"].values())[0]).read_text().splitlines())}
    nrec["same_ids" if set(a) == set(b) else "ids_differ"] += 1
    for tag, dd in (("old", a), ("new", b)):
        for x in dd.values():
            if x.get("type") == "injection_marker": markers[(tag, x["value"]["status"])] += 1
            if x.get("type", "").startswith("agentdojo."): markers[(tag, x["type"])] += 1
    for i in set(a) | set(b):
        if i not in a or i not in b: sig[f"{i[:1]}:{'added' if i not in a else 'removed'}"] += 1; continue
        la, lb = dict(leaves(a[i])), dict(leaves(b[i]))
        for p in set(la) | set(lb):
            if la.get(p) != lb.get(p):
                t = a[i].get("type") or a[i]["k"]
                if p in ("/aer_digest", "/records_sha256", "/profile/version", "/rules/agentdojo") or p.startswith("/ns"):
                    key = f"{t}{re.sub(r'/[0-9]+', '/*', p)}"
                else:
                    key = f"{t}{re.sub(r'/[0-9]+', '/*', p)}: {la.get(p, '<absent>')} -> {lb.get(p, '<absent>')}"
                sig[key] += 1; exs[key].add(r["ex"])
print(json.dumps({"records": dict(nrec), "signatures": dict(sorted(sig.items())), "executions": {k: len(v) for k, v in sorted(exs.items())}, "markers": {f"{a}:{b}": v for (a, b), v in sorted(markers.items())}}, indent=1))
