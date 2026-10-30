"""OS-2: mapped AER judgements vs raw L1 outcome fields on the same labels; sample rates per directory with Wilson 95%."""
import json, sys, glob, collections, os
sys.path.insert(0, "tools/analysis2")
from exam2_lib import wilson
W = os.path.expanduser("~/.agentprov/migration-work/precheck/agentdyn")
out = {}
for part in sys.argv[2:]:
    l1 = {}
    for line in open(f"{W}/l1-units-{part}.jsonl"):
        r = json.loads(line); l1[r["label"]] = r
    corp = f"{W}/l2-{part}-j2.partial"
    agree = collections.Counter(); mism = []
    rates = collections.defaultdict(lambda: collections.Counter())
    for p in glob.glob(f"{corp}/aer/*/*.aer.jsonl"):
        label = None; j = {}; origin = {}
        for line in open(p):
            r = json.loads(line)
            if r["k"] == "execution":
                label = r["artifacts"][0]["origin"]["path"]
            elif r["k"] == "judgement":
                j[r["name"]] = r.get("value"); origin[r["name"]] = r.get("origin")
        row = l1[label]; f = row["facets"]; raw = row["outcomes"]
        for name in ("utility", "security"):
            mv = j.get(name, "<absent>"); rv = raw.get(name)
            rv = "<absent>" if rv is None else rv
            agree["agree" if mv == rv else "differ"] += 1
            if mv != rv:
                mism.append((label.split("/")[1], name, str(rv), str(mv)))
        if f["task_kind"] != "user" or j.get("utility") is None:
            continue
        d = f["pipeline_dir"]
        if f["attack_dir"] == "none":
            rates[d]["bu_n"] += 1; rates[d]["bu_k"] += j["utility"] is True
        elif f["attack_dir"] == "important_instructions":
            rates[d]["at_n"] += 1; rates[d]["ua_k"] += j["utility"] is True; rates[d]["asr_k"] += j.get("security") is True
    per = {}
    for d, c in sorted(rates.items()):
        e = {}
        for m, k, n in (("BU", c["bu_k"], c["bu_n"]), ("UA", c["ua_k"], c["at_n"]), ("ASR", c["asr_k"], c["at_n"])):
            lo, hi = wilson(k, n)
            e[m] = {"k": k, "n": n, "rate": round(100 * k / n, 2) if n else None, "wilson95": [round(100 * lo, 1), round(100 * hi, 1)]}
        per[d] = e
    out[part] = {"label_outcome_agreement": dict(agree), "mismatches": mism, "per_dir": per,
                 "max_n_per_metric": max((v[m]["n"] for v in per.values() for m in v), default=0)}
    print(part, dict(agree), mism[:10], "max n per metric", out[part]["max_n_per_metric"])
json.dump(out, open(sys.argv[1], "w"), indent=1)
