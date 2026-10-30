"""L2 sample arms (l2-head.json, key model|defence|attack) beside the L1 population of the same key (members of the
frame, pooled over directories and copies, error/incomplete logs included as in the sample). Wilson 95%; gap rule.
usage: python3 -I osl2.py <l2-head.json> <l1-units.jsonl> <out.json>"""
import json, math, os, sys, collections as C
def wil(k, n, z=1.959964):
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)); return [round(100 * (c - h) / d, 2), round(100 * (c + h) / d, 2)]
def model(pd):
    for s in ("-autoconfirm", "-capA3", "-capA4", "-noegress", "-rep1", "-rep2", "-rep3"): pd = pd.replace(s, "")
    return pd
DEF = lambda pd: "authority_cap_a3" if "-capA3" in pd else "authority_cap_a4" if "-capA4" in pd else "no_egress" if "-noegress" in pd else "none"
L2 = json.load(open(sys.argv[1]))["outcomes"]["arms"]; pop = C.defaultdict(C.Counter)
for r in map(json.loads, open(os.path.expanduser(sys.argv[2]))):
    f = r["facets"]; key = f"{model(f['pipeline_dir'])}|{DEF(f['pipeline_dir'])}|{f['attack_dir']}"; o = r["outcomes"]
    if f["task_kind"] == "prepass": continue
    if f["attack_dir"] != "none": pop[key]["att_n"] += 1; pop[key]["att_k"] += o["security"] is True
    pop[key]["ut_n"] += 1; pop[key]["ut_k"] += o["utility"] is True
rows = []
for key, a in sorted(L2.items()):
    p = pop[key]
    for met, sk, pk in (("ASR", "attack_success", "att"), ("utility", "utility_user_tasks", "ut")):
        if sk not in a: continue
        s = a[sk]; pr = 100 * p[f"{pk}_k"] / p[f"{pk}_n"]; sr = 100 * s["k"] / s["n"]; w = [round(100 * x, 2) for x in s["wilson95"]]
        outside = max(w[0] - pr, pr - w[1], 0)
        rows.append({"arm": key, "metric": met, "n": s["n"], "k": s["k"], "rate": round(sr, 2), "wilson95": w, "pop_k": p[f"{pk}_k"], "pop_n": p[f"{pk}_n"],
                     "pop_rate": round(pr, 2), "gap_pp": round(sr - pr, 2), "pp_outside_wilson": round(outside, 2),
                     "verdict": ("gap" if abs(sr - pr) > 15 or outside > 5 else "match") if s["n"] >= 20 else "n<20"})
json.dump(rows, open(sys.argv[3], "w"), indent=1)
for r in rows: print(r["arm"], r["metric"], f'{r["k"]}/{r["n"]}', r["wilson95"], r["pop_rate"], r["gap_pp"], r["pp_outside_wilson"], r["verdict"])
