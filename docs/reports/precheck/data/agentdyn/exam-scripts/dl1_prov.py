"""DL-1 PROV: per-execution multiset of (bundle kind, statement type, rule (twin-normalised), class); residual after normalisation."""
import json, sys, collections, os, re
OLD, NEW, OUT = (os.path.expanduser(x) for x in sys.argv[1:4])
def idx(root): return {r["ex"]: r for r in (json.loads(x) for x in open(f"{root}/executions.jsonl") if x.strip())}
oi, ni = idx(OLD), idx(NEW)
def val(x): return x.get("$") if isinstance(x, dict) else x
def stmts(root, row, twin_norm):
    p = list(row["paths"]["prov"].values())[0]["json"]
    d = json.load(open(f"{root}/{p}"))
    c = collections.Counter()
    def add(bk, sec, body):
        for sid, st in body.items():
            r = val(st.get("apv:rule")) if isinstance(st, dict) else None
            ec = val(st.get("apv:evidenceClass")) if isinstance(st, dict) else None
            r = str(r)
            if twin_norm:
                r = r.replace("_unverified", "")
            c[(bk, sec, r, str(ec))] += 1
    for bk, b in (d.get("bundle") or {}).items():
        kind = bk.split(".")[1]
        if kind == "assess": kind = "assess"
        for sec, body in b.items():
            if isinstance(body, dict): add(kind, sec, body)
    for sec, body in d.items():
        if sec not in ("bundle", "prefix") and isinstance(body, dict): add("top", sec, body)
    return c
res = collections.Counter(); ex_res = collections.defaultdict(set); raw_changed = 0
for ex in sorted(set(oi) & set(ni)):
    a, b = stmts(OLD, oi[ex], True), stmts(NEW, ni[ex], True)
    for k in set(a) | set(b):
        if a[k] != b[k]:
            s = " | ".join(k)
            res[s] += b[k] - a[k]; ex_res[s].add(ex)
out = {"n": len(set(oi) & set(ni)), "residual_after_twin_normalisation": {k: {"net": res[k], "executions": len(ex_res[k])} for k in sorted(res, key=lambda k: -len(ex_res[k]))}}
json.dump(out, open(OUT, "w"), indent=1)
for k, v in out["residual_after_twin_normalisation"].items(): print(v, k[:220])
