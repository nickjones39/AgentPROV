"""OS-2: L2 mapped sample rates per model|defence (pooled over run sets) vs the paper (ASR Table 10, BU Table 10, mini UUA
Table 9 pooled) and the L1 population; Wilson 95%; gap rule only for n >= 20 (amendment 2.2). Usage: python3 -I os2.py OUT.json"""
import json, sys
from pathlib import Path
D = Path(__file__).resolve().parents[1]
arms = json.load(open(D / "l2-head.json"))["outcomes"]["arms"]
pop = json.load(open(D / "os1-population.json"))["cells"]
P_ASR = {"mini": {"none": 11, "spotlighting_with_delimiting": 9, "transformers_pi_detector": 2, "tool_filter": 0, "repeat_user_prompt": 5}}
P_BU = {"gpt-5.4-mini-2026-03-17": {"none": 24, "spotlighting_with_delimiting": 19, "transformers_pi_detector": 12, "tool_filter": 8, "repeat_user_prompt": 26},
        "gpt-5.4-2026-03-05": {"none": 9, "spotlighting_with_delimiting": 8, "transformers_pi_detector": 5, "tool_filter": 10, "repeat_user_prompt": 8},
        "claude-sonnet-4-6": {"none": 13, "spotlighting_with_delimiting": 12, "transformers_pi_detector": 6, "repeat_user_prompt": 14}}
P_UUA_MINI = {"none": 168, "spotlighting_with_delimiting": 168, "transformers_pi_detector": 88, "tool_filter": 91, "repeat_user_prompt": 170}
def popsum(model, defence, key, n):
    k = sum(v[key] for c, v in pop.items() if c.endswith("/" + model) and f"/{defence}/" in c)
    m = sum(v[n] for c, v in pop.items() if c.endswith("/" + model) and f"/{defence}/" in c)
    return k, m
rows = []
for arm, v in sorted(arms.items()):
    model, defence, attack = arm.split("|")
    if attack == "none":
        s = v["utility_user_tasks"]; metric = "BU"; pk, pn = P_BU[model][defence], (32 if "mini" in model else 16)
        lk, ln = popsum(model, defence, "bu_k", "bu_n")
        rows.append((metric, model, defence, s, pk, pn, lk, ln))
    else:
        s = v["attack_success"]; lk, ln = popsum(model, defence, "asr_k", "att_n")
        pk, pn = (P_ASR["mini"][defence], 288) if "mini" in model else (0, 144)
        rows.append(("ASR", model, defence, s, pk, pn, lk, ln))
        s2 = v["utility_user_tasks"]; lk2, ln2 = popsum(model, defence, "uua_k", "att_n")
        rows.append(("UUA", model, defence, s2, P_UUA_MINI[defence] if "mini" in model else None, 288 if "mini" in model else None, lk2, ln2))
out = []
for metric, model, defence, s, pk, pn, lk, ln in rows:
    lo, hi = s["wilson95"]; ref = pk / pn if pk is not None else lk / ln
    out.append({"metric": metric, "model": model, "defence": defence, "k": s["k"], "n": s["n"], "rate": s["rate"], "wilson95": s["wilson95"],
                "paper": f"{pk}/{pn}" if pk is not None else None, "paper_rate": round(pk / pn, 4) if pk is not None else None,
                "population": f"{lk}/{ln}", "population_rate": round(lk / ln, 4),
                "ref_inside_wilson": lo <= ref <= hi, "ref_outside_by_more_than_5pp": ref < lo - 0.05 or ref > hi + 0.05,
                "gap_rule_applicable": s["n"] >= 20})
json.dump({"rows": out, "n_rows": len(out), "ref_outside_wilson": sum(not r["ref_inside_wilson"] for r in out),
           "ref_outside_by_more_than_5pp": sum(r["ref_outside_by_more_than_5pp"] for r in out),
           "gap_rule_applicable_rows": sum(r["gap_rule_applicable"] for r in out)}, open(sys.argv[1], "w"), indent=1)
print(json.dumps({k: v for k, v in json.load(open(sys.argv[1])).items() if k != "rows"}))
for r in out:
    if not r["ref_inside_wilson"]: print(r)
