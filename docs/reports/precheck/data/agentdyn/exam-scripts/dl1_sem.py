import json, sys, collections, os
OLD, NEW, OUT = (os.path.expanduser(x) for x in sys.argv[1:4])
def idx(root): return {r["ex"]: r for r in (json.loads(x) for x in open(f"{root}/executions.jsonl") if x.strip())}
oi, ni = idx(OLD), idx(NEW)
def anns(root, row):
    p = list(row["paths"]["sem"].values())[0]
    c = collections.Counter(); hdr = None
    for l in open(f"{root}/{p}"):
        r = json.loads(l)
        if r["k"] == "sem": hdr = (r["profile"], r.get("rules"))
        if r["k"] != "ann": continue
        rules = r.get("rule") if isinstance(r.get("rule"), list) else [r.get("rule")]
        c[(r["type"], "+".join(sorted(x.split("#")[0] for x in rules)), r["ev"], json.dumps(r.get("value"))[:40] if r["type"] in ("injection_marker", "channel", "integrity", "outcome") else "")] += 1
    return c, hdr
delta = collections.Counter(); ex_sig = collections.defaultdict(set); hdrs = collections.Counter()
unk_old = unk_new = 0; ev_old = collections.Counter(); ev_new = collections.Counter()
for ex in sorted(set(oi) & set(ni)):
    a, ha = anns(OLD, oi[ex]); b, hb = anns(NEW, ni[ex])
    hdrs[(json.dumps(ha), json.dumps(hb))] += 1
    unk_old += any("unknown_tool" in k[1] for k in a); unk_new += any("unknown_tool" in k[1] for k in b)
    for k, n in a.items(): ev_old[k[2]] += n
    for k, n in b.items(): ev_new[k[2]] += n
    for k in set(a) | set(b):
        if a[k] != b[k]:
            s = f"{k[0]} | {k[1]} | {k[2]} | {k[3]}"
            delta[s] += b[k] - a[k]; ex_sig[s].add(ex)
out = {"headers": {f"{a} -> {b}": n for (a, b), n in hdrs.items()}, "executions_with_unknown_tool": {"old": unk_old, "new": unk_new, "n": len(set(oi) & set(ni))},
       "ann_ev_old": dict(ev_old), "ann_ev_new": dict(ev_new),
       "ann_delta": {k: {"net": delta[k], "executions": len(ex_sig[k])} for k in sorted(delta, key=lambda k: -len(ex_sig[k]))}}
json.dump(out, open(OUT, "w"), indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "ann_delta"}, indent=0))
for k, v in list(out["ann_delta"].items())[:70]: print(v, k[:200])
