"""OS-1 (population, from pop.json) and OS-2 (sample, l2-head.json) outcome tables with Wilson 95% and the prereg gap rule."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "tools/analysis2"))
from exam2_lib import wilson
R = str(Path.cwd()) + "/docs/reports/precheck/data/glitch-agentdojo/"
pop = json.load(open(sys.argv[1]))["by_arm"]
PAPER = {  # prereg section 4 (RESULTS.md / README at the pin): (benign k, UA k, ASR k, denial benign, denial attacked)
 "gpt-4o-2024-05-13|workspace": (24, 48, 97, None, None), "gpt-4o-2024-05-13-glitch|workspace": (23, 110, 2, 3, 131),
 "gpt-4o-2024-05-13|banking": (15, 116, 96, None, None), "gpt-4o-2024-05-13-glitch|banking": (14, 98, 5, 1, 96),
 "gpt-4o-2024-05-13|travel": (14, 45, 54, None, None), "gpt-4o-2024-05-13-glitch|travel": (12, 63, 29, 1, 34),
 "gpt-4o-2024-05-13|slack": (17, 71, 97, None, None), "gpt-4o-2024-05-13-glitch|slack": (13, 32, 7, 8, 104),
 "claude-haiku-4-5|banking": (7, 75, 0, None, None), "claude-haiku-4-5-glitch|banking": (9, 74, 0, 0, 0)}
def row(arm, level, metric, k, n, pk, pn=None):
    pn = pn or n
    lo, hi = wilson(k, n); rate = k / n; paper = pk / pn if pk is not None else None
    gap = None if paper is None else round(100 * (rate - paper), 2)
    outside = paper is not None and (paper < lo - 0.05 or paper > hi + 0.05)
    flag = paper is not None and ((n >= 20 and abs(gap) > 15) or outside)
    return {"arm": arm, "level": level, "metric": metric, "k": k, "n": n, "rate": round(100 * rate, 2),
            "wilson95": [round(100 * lo, 2), round(100 * hi, 2)], "paper": None if paper is None else round(100 * paper, 2),
            "paper_k": pk, "gap_pp": gap, "flag": flag}
os1 = []; tot = {}
for arm, c in pop.items():
    p = PAPER[arm]
    nb, na = c["n_user_benign"], c["n_user_attacked"]
    kb, ku, ks = c.get("utility_True_user_benign", 0), c.get("utility_True_user_attacked", 0), c.get("security_True_user_attacked", 0)
    os1 += [row(arm, "L1-population", "benign_utility", kb, nb, p[0]), row(arm, "L1-population", "utility_under_attack", ku, na, p[1]),
            row(arm, "L1-population", "targeted_asr", ks, na, p[2])]
    if p[3] is not None:
        os1 += [row(arm, "L1-population", "runs_with_denial_benign", c.get("runs_with_denial_user_benign", 0), nb, p[3]),
                row(arm, "L1-population", "runs_with_denial_attacked", c.get("runs_with_denial_user_attacked", 0), na, p[4])]
    pipe = arm.split("|")[0]
    if pipe.startswith("gpt-4o"):
        t = tot.setdefault(pipe, [0, 0, 0, 0, 0])
        t[0] += kb; t[1] += nb; t[2] += ku; t[3] += ks; t[4] += na
PALL = {"gpt-4o-2024-05-13": (70, 280, 344), "gpt-4o-2024-05-13-glitch": (62, 303, 43)}
for pipe, t in tot.items():
    os1 += [row(pipe + "|all four", "L1-population", "benign_utility", t[0], t[1], PALL[pipe][0]),
            row(pipe + "|all four", "L1-population", "utility_under_attack", t[2], t[4], PALL[pipe][1]),
            row(pipe + "|all four", "L1-population", "targeted_asr", t[3], t[4], PALL[pipe][2])]
# by-effect (#168 slack IT5: 7 successes, every target call denied) - informational
os1.append(row("gpt-4o-2024-05-13-glitch|all four (by effect, excl. 7 slack IT5 #168)", "L1-population", "targeted_asr", 36, 629, 36))
# OS-2: sample arms (model|defence|attack) vs post-stratified population expectation (R6: 5 per stratum, equal weights)
l2 = json.load(open(R + "l2-head.json"))["outcomes"]["arms"]
def strat_rate(pipe, kind):
    vals = []
    for arm, c in pop.items():
        if arm.split("|")[0] != pipe: continue
        if kind == "asr": vals.append(c.get("security_True_user_attacked", 0) / c["n_user_attacked"])
        if kind == "ua": vals.append(c.get("utility_True_user_attacked", 0) / c["n_user_attacked"])
    return sum(vals) / len(vals)
os2 = []
for key, a in l2.items():
    model, dfn, att = key.split("|")
    pipe = model + ("-glitch" if dfn == "glitch" else "")
    if att == "important_instructions":
        for m, kind in (("attack_success", "asr"), ("utility_user_tasks", "ua")):
            k, n = a[m]["k"], a[m]["n"]; ps = strat_rate(pipe, kind)
            r = row(key, "L2-sample", m, k, n, None); r["paper"] = round(100 * ps, 2); r["paper_basis"] = "post-stratified L1 population (R6)"
            r["gap_pp"] = round(100 * (k / n - ps), 2); lo, hi = wilson(k, n)
            r["flag"] = (n >= 20 and abs(r["gap_pp"]) > 15) or ps < lo - 0.05 or ps > hi + 0.05
            os2.append(r)
    else:
        k, n = a["utility_user_tasks"]["k"], a["utility_user_tasks"]["n"]
        r = row(key, "L2-sample", "benign_utility_user_tasks", k, n, None); os2.append(r)
os2_map = json.load(open(sys.argv[2]))
json.dump({"format": "glitch-agentdojo-os1/1", "source": "raw outcome fields of the 1,844 logs (pinned clone, agentprov.ingest); paper = prereg section 4", "rows": os1}, open(R + "os1-population.json", "w"), indent=1)
json.dump({"format": "glitch-agentdojo-os2/1", "rows": os2, "raw_vs_mapped": os2_map}, open(R + "os2-sample.json", "w"), indent=1)
for r in os1 + os2: print(r["arm"], r["metric"], f'{r["k"]}/{r["n"]}', r["rate"], r["wilson95"], r["paper"], r["gap_pp"], r["flag"])
