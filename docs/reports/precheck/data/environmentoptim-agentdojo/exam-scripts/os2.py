"""OS-2: mapped AER judgements of the 35 sampled executions vs the raw L1 outcomes of the same labels; per-suite
sample rates with Wilson 95 %; judgement origins and AER record kinds. Reads the scratch corpus read-only.
Usage: python3 -I os2.py CORPUS L1_UNITS OUT.json"""
import json, sys, os, math, collections as C
def wilson(k, n, z=1.959964):
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(100 * (c - h) / d, 2), round(100 * (c + h) / d, 2)]
CORP = os.path.expanduser(sys.argv[1]); l1 = {r["sha256"]: r for r in map(json.loads, open(os.path.expanduser(sys.argv[2])))}
diff = C.Counter(); arms = C.defaultdict(C.Counter); origins = C.Counter(); kinds = C.Counter(); ev = C.Counter()
for line in open(os.path.join(CORP, "executions.jsonl")):
    e = json.loads(line); row = l1[e["raw"][0]["sha256"].split(":")[1]]
    js = {}
    for r in map(json.loads, open(os.path.join(CORP, e["paths"]["aer"]))):
        kinds[r.get("k")] += 1
        if r.get("k") == "judgement":
            js[r.get("name")] = r.get("value"); origins[f"{r.get('name')}|{r.get('origin')}"] += 1
    for m in ("utility", "security"):
        diff["compared"] += 1; diff["differ"] += row["outcomes"][m] != js.get(m)
    a = arms[row["facets"]["suite"]]; a["n"] += 1; a["util_raw"] += bool(row["outcomes"]["utility"]); a["util_aer"] += bool(js.get("utility"))
out = {"os2": dict(diff), "origins": dict(origins), "record_kinds": dict(kinds),
       "by_suite": {s: {"n": a["n"], "k": a["util_aer"], "raw_k": a["util_raw"], "rate": round(100 * a["util_aer"] / a["n"], 1),
                        "wilson95": wilson(a["util_aer"], a["n"])} for s, a in sorted(arms.items())}}
json.dump(out, open(sys.argv[3], "w"), indent=1, sort_keys=True); print(json.dumps(out, indent=1, sort_keys=True))
