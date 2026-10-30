"""OS-1 (population, L1 raw outcome fields) and OS-2 (sample, mapped AER judgements) rates with Wilson 95%."""
import collections as co, json, os, sys
sys.path.insert(0, sys.argv[1] + "/tools/analysis2"); from exam2_lib import wilson
W = os.path.expanduser("~/.agentprov/migration-work/precheck/tacit-agentdojo")
rows = [json.loads(l) for l in open(f"{W}/l1-units-head.jsonl")]
def rate(k, n):
    lo, hi = wilson(k, n); return {"k": k, "n": n, "rate_pct": round(100 * k / n, 2) if n else None, "wilson95_pct": [round(100 * lo, 2), round(100 * hi, 2)]}
pop = co.defaultdict(lambda: co.Counter())
for r in rows:
    f = r["facets"]; o = r["outcomes"]
    for arm in (f"{f['model_dir']}|{f['attack_dir']}|{f['suite']}", f"{f['model_dir']}|{f['attack_dir']}|ALL", f"ALL|{f['attack_dir']}|ALL", "ALL|ALL|ALL"):
        c = pop[arm]; c["n"] += 1
        for m in ("utility", "security"):
            if o[m] is None: c[f"{m}_none"] += 1
            else: c[f"{m}_n"] += 1; c[f"{m}_k"] += bool(o[m])
P = {}
for arm, c in sorted(pop.items()):
    P[arm] = {"n_logs": c["n"], "utility": rate(c["utility_k"], c["utility_n"]), "security_raw": rate(c["security_k"], c["security_n"]),
              "none": {"utility": c["utility_none"], "security": c["security_none"]}}
# sample: mapped judgements from scratch AER
corp = f"{W}/l2-head-j2.partial"; S = co.defaultdict(co.Counter); pw = co.defaultdict(co.Counter)
lab2row = {r["label"]: r for r in rows}
strata_n = co.Counter(r["stratum"] for r in rows)
for l in open(f"{corp}/executions.jsonl"):
    e = json.loads(l); recs = [json.loads(x) for x in open(f"{corp}/{e['paths']['aer']}")]
    lab = recs[0]["artifacts"][0]["origin"]["path"]; f = lab2row[lab]["facets"]; st = lab2row[lab]["stratum"]
    j = {r["name"]: r.get("value") for r in recs if r.get("k") == "judgement"}
    arm = f"{f['model_dir']}|{f['attack_dir']}"
    S[arm]["n"] += 1; S[arm]["u"] += bool(j.get("utility")); S[arm]["s"] += bool(j.get("security"))
    pw[(arm, st)]["n"] += 1; pw[(arm, st)]["u"] += bool(j.get("utility")); pw[(arm, st)]["s"] += bool(j.get("security"))
Sm = {}
for arm, c in sorted(S.items()):
    ps = {}
    for m, key in (("utility", "u"), ("security", "s")):
        tot = sum(strata_n[st] for (a, st) in pw if a == arm)
        ps[m] = round(100 * sum(strata_n[st] * pw[(a, st)][key] / pw[(a, st)]["n"] for (a, st) in pw if a == arm) / tot, 2)
    Sm[arm] = {"n": c["n"], "utility": rate(c["u"], c["n"]), "security_raw": rate(c["s"], c["n"]), "post_stratified_pct": ps}
out = {"format": "tacit-agentdojo-os/1", "note": "security_raw on attacked arms = targeted ASR (security true = injection goal reached, AgentDojo #95); on benign arms it is the harness constant (benign_security_constant), never an ASR. Counts only.",
       "population_L1": P, "sample_L2_mapped": Sm,
       "paper_targets": {"security_true": 369, "security_false": 1706, "security_missing": 1, "derived_attacked_security_true": 175, "utility_true_false_none": [750, 1325, 1]}}
json.dump(out, open(sys.argv[2], "w"), indent=1, sort_keys=True)
for a, v in P.items(): print("P", a, v["n_logs"], "U", v["utility"]["k"], v["utility"]["n"], v["utility"]["rate_pct"], v["utility"]["wilson95_pct"], "S", v["security_raw"]["k"], v["security_raw"]["n"], v["security_raw"]["rate_pct"], v["security_raw"]["wilson95_pct"])
for a, v in Sm.items(): print("S", a, v)
