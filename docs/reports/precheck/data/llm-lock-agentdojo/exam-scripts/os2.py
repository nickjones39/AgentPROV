"""L2 outcome sanity for llm-lock-agentdojo: mapped AER outcomes (l2-head.json) vs raw values of the same labels (L1 rows)
and vs the population / results.json (pop.json); per defence arm, raw and post-stratified by attack (population weights).
Usage: python3 -I os2.py <l2-head.json> <sample_raw.json> <pop.json> <out.json>"""
import json, sys
from collections import Counter, defaultdict
L2, SR, POP, OUT = sys.argv[1:5]
l2 = json.load(open(L2))["outcomes"]["arms"]; sr = json.load(open(SR)); pop = json.load(open(POP))["arms"]
DIR = {"spotlighting_with_delimiting": "data-delimiter"}
def armdir(d):
    d = DIR.get(d, d)
    for p in ("transformer-", "hybrid-"):
        if d.startswith(p): return p[:-1] + "/" + d[len(p):]
    return d
def wil(k, n):
    if not n: return None
    z = 1.959963984540054; p = k / n; den = 1 + z * z / n; c = (p + z * z / (2 * n)) / den
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return [round(100 * p, 2), round(100 * max(0, c - h), 2), round(100 * min(1, c + h), 2)]
agg = defaultdict(Counter); mism = Counter()
for key, v in l2.items():
    _, d, att = key.split("|"); arm = armdir(d); raw = sr.get(f"{arm}|{att}", {})
    if att == "none":
        u = v["utility_user_tasks"]; agg[arm]["ben_k"] += u["k"]; agg[arm]["ben_n"] += u["n"]
        mism["benign_util_raw_vs_mapped_differs"] += u["k"] != raw.get("uti_user", 0)
    else:
        s = v["attack_success"]; agg[arm][f"{att}_k"] += s["k"]; agg[arm][f"{att}_n"] += s["n"]
        mism["security_raw_vs_mapped_differs"] += s["k"] != raw.get("sec", 0) or s["n"] != raw.get("n", 0)
    mism["arms_compared"] += 1
W = {a: 949 for a in ("direct", "ignore_previous", "important_instructions", "injecagent", "system_message", "tool_knowledge")} | {"dos": 97}
rows = {}
for arm, c in sorted(agg.items()):
    k = sum(c[f"{a}_k"] for a in W); n = sum(c[f"{a}_n"] for a in W)
    ps = sum(W[a] / 5791 * (c[f"{a}_k"] / c[f"{a}_n"]) for a in W if c[f"{a}_n"])
    P = pop[arm]
    rows[arm] = {"asr_n": n, "asr_sample": wil(k, n), "asr_poststrat": round(100 * ps, 2), "asr_pop": P["asr_incl_dos"][2][0],
                 "asr_gap_poststrat_pp": round(100 * ps - P["asr_incl_dos"][2][0], 2),
                 "ben_n": c["ben_n"], "ben_sample": wil(c["ben_k"], c["ben_n"]), "ben_pop": P["benign_utility"][2][0]}
    lo, hi = rows[arm]["asr_sample"][1], rows[arm]["asr_sample"][2]; pp = rows[arm]["asr_pop"]
    rows[arm]["asr_outside_wilson_by_pp"] = round(max(lo - pp, pp - hi, 0), 2)
out = {"mapping_check": dict(mism), "arms": rows}
json.dump(out, open(OUT, "w"), indent=1); print(json.dumps(out, indent=1))
