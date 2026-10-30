"""Rules cited by evidence-class-D PROV statements in the scratch corpus (rule ids and counts only)."""
import collections, glob, json, sys
root = sys.argv[1]
c = collections.Counter(); keys = collections.Counter()
def visit(doc, bundle):
    for sec, items in doc.items():
        if sec in ("prefix", "bundle") or not isinstance(items, dict):
            continue
        for sid, attrs in items.items():
            for a in (attrs if isinstance(attrs, list) else [attrs]):
                if not isinstance(a, dict): continue
                ev = a.get("apv:evidence") or a.get("apv:evidenceClass")
                evs = json.dumps(ev)
                if ev is not None and ("D" in evs and "apv:D" in evs or evs.strip('"') == "D"):
                    r = a.get("apv:rule")
                    c[(bundle, sec, json.dumps(r)[:90])] += 1
                for k in a:
                    if k.startswith("apv:ev"): keys[k] += 1
for f in glob.glob(root + "/prov/*/*/*.json"):
    d = json.load(open(f))
    visit(d, "top")
    for bid, b in (d.get("bundle") or {}).items():
        visit(b, bid.split(".")[1] if bid.count(".") >= 2 else bid)
print(dict(keys))
agg = collections.Counter()
for (b, s, r), v in c.items(): agg[(b, s, r)] += v
for k, v in agg.most_common(30): print(v, k)
