"""Evidence classes by bundle kind and rule over the scratch PROV docs (j2), with twin vs native-I split (CC-08 rule)."""
import sys, json
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "tools/precheck"))
from l2_check import is_twin, _UNVERIFIED_REF, _as_list
from agentprov.validate._provdoc import ProvView
C = Path.home() / ".agentprov/migration-work/precheck/glitch-agentdojo/l2-head-j2.partial"
by_rule = Counter(); twin = Counter(); native = Counter(); deny = Counter(); bundles = Counter()
for p in sorted((C / "prov").rglob("*.prov.json")):
    v = ProvView.parse(json.loads(p.read_text()))
    ub = {i for i in v.bundles if "_unverified" in i}
    for b in v.bundles.values(): bundles[b.kind] += 1
    for kind, sts in [("top", v.top)] + [(b.kind, b.statements) for b in v.bundles.values()]:
        for st in sts:
            cls = st.cls or "none"
            r = (st.rule or "-").split("#")[0].rsplit("/", 1)[-1]
            by_rule[f"{kind}|{cls}|{r}"] += 1
            basis = [b for b in _as_list(st.attrs.get("apv:basisRule")) if isinstance(b, str)]
            refs = [x for x in [*basis, *(_UNVERIFIED_REF.findall(st.bundle) if st.bundle in ub else [])] if "_unverified" in x]
            if refs:
                (twin if any(is_twin(x) for x in refs) else native)[f"{kind}:{cls}"] += 1
            if "denial" in r: deny[f"{kind}|{cls}|{st.section}"] += 1
core_d = {k: n for k, n in by_rule.items() if k.startswith("core|D")}
out = {"core_D_by_rule": core_d, "twin_by_bundle_class": dict(twin), "native_unverified_by_bundle_class": dict(native),
       "denial_rule_statements": dict(deny), "bundles": dict(bundles),
       "rules_with_D_anywhere": sorted({k.split('|',2)[2] for k in by_rule if k.split('|')[1]=='D'})}
json.dump(out, open(sys.argv[1], "w"), indent=1, sort_keys=True); print(json.dumps(out, indent=1))
