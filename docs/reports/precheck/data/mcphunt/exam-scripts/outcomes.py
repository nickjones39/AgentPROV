"""Outcome comparison (L1 population vs paper Tables 3/6/7/14-17/19/20) from pop.json and rv1.json; Wilson 95%.
Paper counts are the prereg section 4 derived counts. usage: python3 -I outcomes.py <pop.json> <rv1.json> <out.json>
"""
import json, math, sys
pop, rv1 = json.load(open(sys.argv[1]))["tallies"], json.load(open(sys.argv[2]))
def wil(k, n, z=1.959964):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(100 * (c - h), 1), round(100 * (c + h), 1)]
def agg(name, pred): return sum(v for k, v in pop[name].items() if pred(k.split("|")))
rows = []
def row(arm, metric, k, n, pk, pn):
    rows.append({"arm": arm, "metric": metric, "k": k, "n": n, "rate": round(100 * k / n, 1), "wilson95": wil(k, n),
                 "paper_k": pk, "paper_n": pn, "paper_rate": round(100 * pk / pn, 1), "gap_pp": round(100 * (k / n - pk / pn), 1),
                 "gap_traces": k - pk, "verdict": "match" if abs(k - pk) <= 1 and n == pn else "GAP"})
PAPER = {"gpt_5_4": (90, 305, 39, 51), "gpt_5_2": (78, 330, 33, 45), "deepseek_v4_flash": (158, 275, 105, 53),
         "gemini_3_1_pro_preview": (141, 301, 78, 63), "MiniMax_M2_7": (175, 357, 119, 56)}
for d, (pp, pu, pv, pc) in PAPER.items():
    P = lambda s, d=d: s[0] == "main" and s[1] == d and s[4].startswith("risky")
    n = agg("n", P)
    row(f"main/{d} risky", "propagation", agg("prop", P), n, pp, 387)
    row(f"main/{d} risky", "utility", agg("util", P), n, pu, 387)
    row(f"main/{d} risky", "policy_violating", pop["pv"][f"main|{d}|none"], pop["pv_n"][f"main|{d}|none"], pv, 288)
    row(f"main/{d} risky", "crs", pop["crs"][f"main|{d}|none"], pop["crs_n"][f"main|{d}|none"], pc, 63)
for e, pk, pn in (("risky_v1", 28, 147), ("risky_v2", 32, 120), ("risky_v3", 30, 120), ("benign", 0, 147)):
    k = f"main|gpt_5_4|gpt-5.4|none|{e}"; row(f"main/gpt_5_4 {e}", "propagation", pop["prop"][k], pop["n"][k], pk, pn)
HN = lambda s: s[0] == "main" and s[1] == "gpt_5_4" and s[4].startswith("hard_neg")
row("main/gpt_5_4 hard_neg pooled", "propagation", agg("prop", HN), agg("n", HN), 22, 189)
M19 = ((88, 305), (64, 302), (18, 301), (9, 309)); NN = (384, 381, 381, 384)
for i, l in enumerate(("none", "generic", "moderate", "detailed")):
    P = lambda s, i=i: s[0] == "mitigation" and s[1] == f"gpt54_m{i}"
    row(f"mitigation/gpt54_m{i}", "propagation", agg("prop", P), agg("n", P), M19[i][0], NN[i])
    row(f"mitigation/gpt54_m{i}", "utility", agg("util", P), agg("n", P), M19[i][1], NN[i])
T7 = {"gpt54_m": (24.3, 19.6, 4.7, 1.9), "deepseek_m": (47.2, 47.2, 25.0, 12.0), "minimax_m": (50.9, 48.1, 30.6, 26.9)}
for fam, pcts in T7.items():
    for i, pct in enumerate(pcts):
        f = f"{fam}{i}.json" if fam == "gpt54_m" else f"{fam}{i}_rv1.json"
        k = n = 0
        for key, (p, c) in rv1[f].items():
            if key.startswith("bc=True") or key.split("pfx=")[1].startswith("hn_"): continue
            k += p; n += c
        row(f"mitigation/{f[:-5]} risky_v1 risk tasks", "propagation (Table 7)", k, n, round(pct * n / 100), n)
cells = {"table16_mech_x_model": 45, "table17_signals": 45, "table20_mech_x_level": 36, "table14_quadrants": 16}
out = {"rows": rows, "gaps": sum(r["verdict"] == "GAP" for r in rows), "rows_n": len(rows),
       "also_exact_by_recount": cells, "note": "L1 population = full census; Wilson shown for completeness (R6 n/a: no L2 sample)"}
json.dump(out, open(sys.argv[3], "w"), indent=1); print(out["rows_n"], "rows", out["gaps"], "gaps")
