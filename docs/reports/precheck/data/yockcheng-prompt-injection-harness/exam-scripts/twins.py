"""Method references in the scratch PROV split into catalogue twins (X_unverified where X is a rule) and native
class-I *_unverified rules (CC-08 recount). Usage: twins.py <repo> <evclass.json> <out.json>"""
import tomllib, json, sys, collections
d = tomllib.load(open(f"{sys.argv[1]}/src/agentprov/adapters/agentdojo/rules/agentdojo.rules.toml", "rb"))
ids = {r["id"] for r in d["rule"]}
tw = {i for i in ids if i.endswith("_unverified") and i[:-11] in ids}
ev = json.load(open(sys.argv[2]))["methods"]
c = collections.Counter(); per = collections.Counter()
for k, v in ev.items():
    b, cl, m = k.split("|")
    if m.endswith("_unverified"):
        kind = "twin" if m in tw else "native_I"
        c[f"{b}|{cl}|{kind}"] += v; per[f"{kind}|{m}"] += v
out = {"by_bundle": dict(sorted(c.items())), "by_rule": dict(sorted(per.items()))}
json.dump(out, open(sys.argv[3], "w"), indent=1); print(json.dumps(out, indent=1))
