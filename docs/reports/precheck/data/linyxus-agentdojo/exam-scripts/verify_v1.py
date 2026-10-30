"""Verifier independent tally (counts only)."""
import sys, json, hashlib, re
from collections import Counter, defaultdict
sys.path.insert(0, sys.argv[1])
import lx_lib
E = lx_lib.entries(); R = lx_lib.Reader()
cell = defaultdict(Counter); notxt = Counter(); bt = Counter(); sp = defaultdict(Counter)
alt = defaultdict(Counter)
GEN = re.compile(r"[A-Za-z0-9]")
sec_out = Counter()
TXT = {k[:-len(".secure-channel.txt")]+".json" for k in E if k.endswith(".secure-channel.txt")}
for lab, e in E.items():
    if not lab.endswith(".json"): continue
    p = lab.split("/")
    if len(p) < 6: continue
    try: x = R.load(e)
    except Exception: sec_out["parse_fail"] += 1; continue
    if not isinstance(x, dict): continue
    root, pdir, suite, ut, att = p[0], p[1], p[2], p[3], p[4]
    if lab not in TXT: notxt[root] += 1
    tr = (x.get("ext") or {}) if False else None
    b = x.get("backend_tool_traces")
    if b: bt["logs"] += 1; bt["calls"] += len(b) if isinstance(b, list) else 0
    comp = "utility" in x and "security" in x and bool(x.get("messages"))
    attacked = att != "none"
    k = (root, pdir, suite)
    c = cell[k]
    if attacked and comp:
        c["n"] += 1; c["u"] += bool(x["utility"]); c["s"] += bool(x["security"])
    if attacked: c["n_all_att"] += 1; c["u_all_att"] += bool(x.get("utility"))
    else: c["n_pre"] += 1; c["u_pre"] += bool(x.get("utility"))
    if root == "runs-2" or root == "runs-4":
        if "slack" == suite and "gemini" in pdir and "tacit" in pdir:
            ms = x.get("messages") or []
            sysm = [m for m in ms if m.get("role") == "system"]
            if sysm:
                ct = sysm[0].get("content")
                sp[root][hashlib.sha256(json.dumps(ct, sort_keys=True).encode()).hexdigest()[:12]] += 1
    v = x.get("tacit_secure_output")
    if isinstance(v, str) and v and not GEN.search(v) and len(v) >= 16: sec_out["symbol_only_long"] += 1
out = {"cells": {"|".join(k): dict(v) for k, v in cell.items()}, "notxt": dict(notxt), "bt": dict(bt),
       "sysprompt": {k: dict(v) for k, v in sp.items()}, "sec_out": dict(sec_out)}
json.dump(out, open(sys.argv[2], "w"), indent=0)
print("done", len(cell))
