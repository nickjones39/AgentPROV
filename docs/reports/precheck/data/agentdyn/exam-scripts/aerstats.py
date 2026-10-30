import json, glob, collections, sys
c = sys.argv[1]
ev = collections.Counter(); evf = collections.Counter(); rules = collections.Counter(); mc = collections.Counter(); hdr = collections.Counter()
for p in glob.glob(f"{c}/aer/*/*.aer.jsonl"):
    for l in open(p):
        r = json.loads(l)
        if r["k"] == "execution": hdr[json.dumps(r.get("rules"), sort_keys=True)] += 1
        if "ev" in r: ev[(r["k"], r["ev"])] += 1
        for pp, cl in (r.get("evf") or {}).items(): evf[cl] += 1
        rl = r.get("rule"); rl = rl if isinstance(rl, list) else [rl] if rl else []
        for x in rl: rules[x.split("#")[0]] += 1
        if r["k"] == "model_call": mc["params_not_recorded" if (r.get("unk") or {}).get("/params") == "not_recorded" else "params_other"] += 1
print("headers", dict(hdr))
print("ev D:", {f"{k[0]}": v for k, v in ev.items() if k[1] == "D"}, "ev totals", dict(collections.Counter({k[1]: 0 for k in ev}) + collections.Counter({cl: n for (kk, cl), n in ev.items()})))
print("evf", dict(evf)); print("model_call", dict(mc))
print("rules without _unverified:", sorted((k, v) for k, v in rules.items() if "_unverified" not in k))
