"""Keyed AER diff of the sampled executions: stored p10 vs scratch (counts and normalised pointers only)."""
import json, sys, re
from collections import Counter, defaultdict
from pathlib import Path
O = Path(sys.argv[1]).expanduser(); N = Path(sys.argv[2]).expanduser(); out = Path(sys.argv[3])
oi = {r["ex"]: r for r in map(json.loads, (O/"executions.jsonl").read_text().splitlines())}
ni = [json.loads(x) for x in (N/"executions.jsonl").read_text().splitlines()]
def recs(p):
    d = {}
    for l in p.read_text().splitlines():
        r = json.loads(l); d[(r["k"], r.get("id"))] = r
    return d
def norm(p):
    return re.sub(r"/\d+", "/*", p)
def leaves(x, p=""):
    if isinstance(x, dict):
        if not x: yield p, {}
        for k, v in x.items(): yield from leaves(v, p + "/" + k)
    elif isinstance(x, list):
        if not x: yield p, []
        for i, v in enumerate(x): yield from leaves(v, f"{p}/{i}")
    else: yield p, x
sig = Counter(); sig_ex = defaultdict(set); added = Counter(); removed = Counter(); rule_map = Counter(); ev_map = Counter()
added_by_ex = Counter(); hdr = Counter(); unk_added = Counter(); evf_tag = Counter()
for r in ni:
    o = oi[r["ex"]]
    a = recs(O/o["paths"]["aer"]); b = recs(N/r["paths"]["aer"])
    for key in set(a) - set(b): removed[f"{key[0]}:{key[1] if key[0] in ('execution','seal') else re.sub(r'\d+','*',str(key[1]))}"] += 1
    for key in set(b) - set(a):
        added[f"{key[0]}:{re.sub(r'\d+','*',str(key[1]))}:{b[key].get('type')}:{b[key].get('ev')}"] += 1; added_by_ex[r["ex"]] += 1
    for key in set(a) & set(b):
        la = dict(leaves(a[key])); lb = dict(leaves(b[key]))
        for p in set(la) | set(lb):
            va, vb = la.get(p, "<absent>"), lb.get(p, "<absent>")
            if va == vb: continue
            np_ = f"{key[0]}{norm(p)}"
            if p.startswith("/rule/") or p == "/rule" or "/rule/" in p:
                rule_map[f"{key[0]}: {va} -> {vb}"] += 1; np_ = f"{key[0]}/rule/*"
            elif p.startswith("/evf"):
                evf_tag[f"{key[0]}{norm(p)}: {va} -> {vb}"] += 1
            elif p == "/ev":
                ev_map[f"{key[0]}: {va} -> {vb}"] += 1
            elif key[0] == "execution" and (p.startswith("/profile") or p.startswith("/rules")):
                hdr[f"{p}: {va if 'sha' not in p else str(va)[:12]} -> {vb if 'sha' not in p else str(vb)[:12]}"] += 1
            elif p.startswith("/unk"):
                unk_added[f"{key[0]}{norm(p)}: {va} -> {vb}"] += 1
            sig[np_ + (":added" if va == "<absent>" else ":removed" if vb == "<absent>" else ":changed")] += 1
            sig_ex[np_].add(r["ex"])
res = {"executions": len(ni), "records_added": dict(added), "records_removed": dict(removed),
       "executions_with_added_records": len(added_by_ex),
       "leaf_signatures": dict(sorted(sig.items())), "executions_per_pointer": {k: len(v) for k, v in sorted(sig_ex.items())},
       "rule_ref_changes": dict(rule_map.most_common()), "ev_changes": dict(ev_map), "evf_changes": dict(evf_tag.most_common()),
       "header_changes": dict(hdr), "unk_changes": dict(unk_added)}
out.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
