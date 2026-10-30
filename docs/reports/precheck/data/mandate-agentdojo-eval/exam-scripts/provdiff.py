import json, sys, collections
from pathlib import Path
from agentprov.validate._provdoc import ProvView
O = Path(sys.argv[1]).expanduser(); N = Path(sys.argv[2]).expanduser()
oi = {r["ex"]: r for r in map(json.loads, (O/"executions.jsonl").read_text().splitlines())}
ev = {"old": collections.Counter(), "new": collections.Counter()}; sec = {"old": collections.Counter(), "new": collections.Counter()}
top_ent = {"old": collections.Counter(), "new": collections.Counter()}; nb = {"old": collections.Counter(), "new": collections.Counter()}
digest_attr = collections.Counter(); core_I = collections.Counter(); time_attrs = collections.Counter()
used_fx = collections.Counter()
for l in (N/"executions.jsonl").read_text().splitlines():
    r = json.loads(l); o = oi[r["ex"]]
    for tag, base, row in (("old", O, o), ("new", N, r)):
        doc = json.loads((base/row["paths"]["prov"]["agentprov-prov/0.1"]["json"]).read_text())
        v = ProvView.parse(doc)
        conts = [("top", v.top)] + [(b.kind, b.statements) for b in v.bundles.values()]
        nb[tag]["bundles"] += len(v.bundles)
        for kind, sts in conts:
            for st in sts:
                ev[tag][f"{kind}:{st.cls or 'none'}"] += 1; sec[tag][f"{kind}:{st.section}"] += 1
                if kind == "core" and st.cls == "I": core_I[tag] += 1
                for k in st.attrs:
                    if k in ("prov:time", "prov:startTime", "prov:endTime"): time_attrs[(tag, kind, k)] += 1
                if tag == "new" and kind == "core" and st.section == "used" and str(st.arg("prov:entity") or "").startswith("x:fx"): used_fx["core_used_fixture"] += 1
        for k in doc.get("entity", {}):
            if k.startswith("rules:"): top_ent[tag][k] += 1
res = {"evidence": {t: dict(sorted(c.items())) for t, c in ev.items()}, "sections": {t: dict(sorted(c.items())) for t, c in sec.items()},
       "rules_entities": {t: dict(c) for t, c in top_ent.items()}, "bundles": {t: dict(c) for t, c in nb.items()},
       "core_I": dict(core_I), "time_attrs": {str(k): v for k, v in time_attrs.items()}, "new_core_used_fixture": dict(used_fx)}
for t in ("old", "new"):
    tot = sum(v for k, v in ev[t].items() if not k.startswith("top:")); core = sum(v for k, v in ev[t].items() if k.startswith("core:"))
    res[f"core_share_{t}"] = round(core / tot, 3)
print(json.dumps(res, indent=1))
