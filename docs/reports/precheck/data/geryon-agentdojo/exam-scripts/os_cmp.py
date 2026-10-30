"""Population (L1 raw) vs sample (mapped AER) per model|defence on attacked logs, with a post-stratified sample rate
(per log-set stratum weights). Usage: os_cmp.py pop.json os2.json OUT.json"""
import sys, json
from collections import Counter, defaultdict
sys.path.insert(0, __import__("os").getcwd() + "/tools/analysis2")  # run from the repository root
from exam2_lib import wilson
from pathlib import Path
rows = json.load(open(sys.argv[1])); os2 = json.load(open(sys.argv[2]))
W = Path.home() / ".agentprov/migration-work/precheck/geryon-agentdojo"
C = W / "l2-head-j2.partial"
L1 = {json.loads(l)["sha256"]: json.loads(l) for l in open(W / "l1-units-head.jsonl")}
POP = {r["label"]: r for r in rows}
pop = defaultdict(Counter); strata_pop = defaultdict(Counter); strata_s = defaultdict(Counter)
for r in rows:
    if r["kind"] != "user": continue
    a = f"{r['model']}|{'progent' if r['cond']=='B' else 'none'}"
    pop[a]["n"] += 1; pop[a]["asr"] += r["security"] is True; pop[a]["util"] += r["utility"] is True
    strata_pop[(a, r["run_set"] + "/" + r["logset"])]["n"] += 1
for line in open(C / "executions.jsonl"):
    e = json.loads(line); u = L1[e["raw"][0]["sha256"].split(":", 1)[1]]; p = POP[u["label"]]
    if p["kind"] != "user": continue
    a = f"{p['model']}|{'progent' if p['cond']=='B' else 'none'}"
    recs = [json.loads(x) for x in open(C / e["paths"]["aer"])]
    j = {x["name"]: x.get("value") for x in recs if x["k"] == "judgement" and x.get("subject") == "run"}
    s = strata_s[(a, p["run_set"] + "/" + p["logset"])]
    s["n"] += 1; s["asr"] += j.get("security") is True; s["util"] += j.get("utility") is True
OUT = {}
for a in sorted(pop):
    smp = os2["sample_arms"]["model_defence:" + a]
    ps = {}
    for m in ("asr", "util"):
        tot = sum(c["n"] for (aa, _), c in strata_pop.items() if aa == a)
        ps[m] = round(100 * sum(strata_pop[(aa, st)]["n"] / tot * (c[m] / c["n"]) for (aa, st), c in strata_s.items() if aa == a), 2)
    out = {}
    for m, mm in (("asr", "asr"), ("util", "utility")):
        k, n = pop[a][m], pop[a]["n"]; lo, hi = wilson(k, n)
        sk, sn = smp[mm]["k"], smp[mm]["n"]; slo, shi = wilson(sk, sn)
        out[mm] = {"population": {"k": k, "n": n, "pct": round(100 * k / n, 2), "wilson95": [round(100 * lo, 2), round(100 * hi, 2)]},
                   "sample": smp[mm], "sample_post_stratified_pct": ps[m],
                   "gap_sample_minus_population_pp": round(smp[mm]["pct"] - 100 * k / n, 2)}
    OUT[a] = out
json.dump(OUT, open(sys.argv[3], "w"), indent=1, sort_keys=True)
for a, d in OUT.items():
    for m, x in d.items():
        print(a, m, "pop", x["population"]["k"], "/", x["population"]["n"], x["population"]["pct"], "sample", x["sample"]["k"], "/", x["sample"]["n"], x["sample"]["pct"], x["sample"]["wilson95"], "poststrat", x["sample_post_stratified_pct"], "gap", x["gap_sample_minus_population_pp"])
