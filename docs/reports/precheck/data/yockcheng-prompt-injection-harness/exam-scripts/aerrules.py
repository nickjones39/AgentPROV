"""AER and SEM rule references by catalogue class (D rules cited directly vs via twins) and record ev tags. Counts only.
Usage: aerrules.py <repo> <corpus> <out.json>"""
import tomllib, json, sys, collections
from pathlib import Path
d = tomllib.load(open(f"{sys.argv[1]}/src/agentprov/adapters/agentdojo/rules/agentdojo.rules.toml", "rb"))
cls = {r["id"]: r.get("class") for r in d["rule"]}
C = Path(sys.argv[2]); refs = collections.Counter(); ev = collections.Counter(); direct_d = collections.Counter()
def rr(x):
    for key in ("rule", "rules"):
        v = x.get(key)
        if isinstance(v, str): yield v
        elif isinstance(v, list):
            for i in v:
                if isinstance(i, str): yield i
def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values(): yield from walk(v)
    elif isinstance(o, list):
        for v in o: yield from walk(v)
for line in open(C / "executions.jsonl"):
    r = json.loads(line)
    for layer, p in (("aer", r["paths"]["aer"]), ("sem", r["paths"]["sem"]["agentdojo.suites@2"])):
        for x in (json.loads(l) for l in open(C / p)):
            ev[f"{layer}|{x.get('k')}|{x.get('ev')}"] += 1
            for o in walk(x):
                for ref in rr(o):
                    rid = ref.split("#")[0].split("@")[0]
                    if rid.startswith("agentdojo."):
                        c = cls.get(rid, "?"); refs[f"{layer}|{c}"] += 1
                        if c == "D": direct_d[f"{layer}|{rid}"] += 1
out = {"ev_tags": dict(sorted(ev.items())), "adapter_refs_by_class": dict(refs), "direct_D_refs": dict(direct_d)}
json.dump(out, open(sys.argv[3], "w"), indent=1); print(json.dumps({k: v for k, v in out.items() if k != "ev_tags"}, indent=1))
print({k: v for k, v in out["ev_tags"].items() if not k.endswith("None")})
