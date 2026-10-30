"""Byte-identical non-empty logs across/within parts (sha256 of the unit rows); counts and label prefixes only."""
import json, sys, pathlib, collections as C
W = pathlib.Path.home() / ".agentprov/migration-work/precheck/controlarena-persistent"
PARTS = ["zip-3-001", "zip-3-002", "zip-3-003", "batch-runs", "auditor"]
g = C.defaultdict(list)
for p in PARTS:
    for line in (W / f"l1-units-{p}.jsonl").open():
        r = json.loads(line)
        if r.get("size", 0) == 0: continue
        g[r["sha256"]].append((p, r["label"].split("/")[0] if "/" in r["label"] else r["label"][:20], r.get("n_units", 0), "no_header" in r.get("flags", []), r.get("facets", {}).get("experiment")))
pat = C.Counter(); units = C.Counter()
for s, v in g.items():
    if len(v) > 1:
        k = " + ".join(sorted(f"{p}:{e}{'(nohdr)' if nh else ''}" for p, _, n, nh, e in v))
        pat[k] += 1; units[k] += v[0][2]
out = {"groups": sum(pat.values()), "patterns": {k: [pat[k], units[k]] for k in pat}}
# per-part units, all vs first occurrence by part order
tot = C.Counter(); first = C.Counter(); seenp = {}
for p in PARTS:
    for line in (W / f"l1-units-{p}.jsonl").open():
        r = json.loads(line); n = r.get("n_units", 0); tot[p] += n
        if r.get("size", 0) and r["sha256"] in seenp: continue
        seenp[r["sha256"]] = p; first[p] += n
out["units_all"] = dict(tot); out["units_first_occurrence"] = dict(first)
print(json.dumps(out, indent=1))
