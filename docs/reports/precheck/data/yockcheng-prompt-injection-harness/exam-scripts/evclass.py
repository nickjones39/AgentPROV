"""Evidence class by bundle kind x apv:rule (and adapter method refs) over the scratch PROV documents. Counts only."""
import json, sys
from collections import Counter
from pathlib import Path
C = Path(sys.argv[1])
by = Counter(); meth = Counter(); twin = Counter(); nontwin_adapter = Counter()
def cls(v):
    e = v.get("apv:evidenceClass")
    return (e or {}).get("$", "none").split(":")[-1] if isinstance(e, dict) else "none"
def walk(bkind, doc):
    for kind, items in doc.items():
        if kind in ("prefix", "bundle") or not isinstance(items, dict): continue
        for _id, v in items.items():
            for vv in (v if isinstance(v, list) else [v]):
                if not isinstance(vv, dict): continue
                c = cls(vv); rule = vv.get("apv:rule", "-")
                by[f"{bkind}|{c}|{kind}|{rule}"] += 1
                ms = vv.get("apv:method") or []
                ms = ms if isinstance(ms, list) else [ms]
                for m in ms:
                    m = str(m); meth[f"{bkind}|{c}|{m.split('@')[0]}"] += 1
                    if m.startswith("agentdojo.") and "_unverified" not in m:
                        nontwin_adapter[f"{bkind}|{c}|{m}"] += 1
for line in open(C / "executions.jsonl"):
    r = json.loads(line)
    d = json.load(open(C / r["paths"]["prov"]["agentprov-prov/0.1"]["json"]))
    walk("top", {k: v for k, v in d.items() if k != "bundle"})
    for bn, bv in d.get("bundle", {}).items():
        walk(bn.split(":")[1].split(".")[1], bv)
out = {"by_bundle_class_kind_rule": dict(sorted(by.items())), "methods": dict(sorted(meth.items())),
       "adapter_methods_without_unverified_suffix": dict(sorted(nontwin_adapter.items()))}
json.dump(out, open(sys.argv[2], "w"), indent=1, sort_keys=True)
cd = {k: v for k, v in by.items() if k.startswith("core|Derived")}
print("core Derived:", json.dumps(cd, indent=1))
print("adapter methods w/o _unverified:", json.dumps(out["adapter_methods_without_unverified_suffix"], indent=1))
