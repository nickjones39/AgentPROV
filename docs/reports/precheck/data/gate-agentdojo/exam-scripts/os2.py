"""OS-2: L2 sample, mapped AER arm outcomes (l2-head.json) vs raw L1 outcome fields of the same labels, and the
L1 population rate per arm (Wilson 95 %). Counts only. Usage: python3 -I os2.py <l1-units> <l2-sample> <l2-head.json> <out>"""
import json, sys
from collections import defaultdict, Counter
U, S, L2, OUT = sys.argv[1:5]
rows = [json.loads(l) for l in open(U)]
samp = set(json.load(open(S))["labels"])
arms = json.load(open(L2))["outcomes"]["arms"]
DEF = {"off": "none", "all": "gate-all", "gatellm": "gate-gatellm", "gatellm-echo": "gate-gatellm-echo"}
def arm(f):
    p = f.get("pipeline_dir")
    if not p: return None
    if p == "local": return "none|none|" + f["attack_dir"]
    m, d = p[6:].split("-gate-")
    return f"{m}|{DEF[d]}|{f['attack_dir']}"
def wil(k, n):
    if not n: return None
    z = 1.959963984540054; p = k / n; d = 1 + z*z/n; c = (p + z*z/(2*n))/d; h = z*((p*(1-p)/n + z*z/(4*n*n))**.5)/d
    return [round(100*p, 2), round(100*max(0, c-h), 2), round(100*min(1, c+h), 2)]
pop = defaultdict(Counter); smp = defaultdict(Counter)
for r in rows:
    a = arm(r["facets"])
    if a is None or r["outcomes"]["security"] is None: continue
    att = r["facets"]["attack_class"] == "attacked"; pre = r["facets"]["task_kind"] == "prepass"
    for tgt in ([pop[a]] + ([smp[a]] if r["label"] in samp else [])):
        if att and not pre:
            tgt["asr_n"] += 1; tgt["asr_k"] += r["outcomes"]["security"] is True
        if not pre:
            tgt["u_n"] += 1; tgt["u_k"] += r["outcomes"]["utility"] is True
out = {}; mism = 0
for a in sorted(pop):
    m = arms.get(a, {})
    e = {"pop_asr": wil(pop[a]["asr_k"], pop[a]["asr_n"]), "pop_asr_kn": [pop[a]["asr_k"], pop[a]["asr_n"]],
         "pop_util_user": wil(pop[a]["u_k"], pop[a]["u_n"]), "pop_util_kn": [pop[a]["u_k"], pop[a]["u_n"]],
         "sample_raw_asr_kn": [smp[a]["asr_k"], smp[a]["asr_n"]], "sample_raw_util_kn": [smp[a]["u_k"], smp[a]["u_n"]]}
    if "attack_success" in m: e["sample_aer_asr_kn"] = [m["attack_success"]["k"], m["attack_success"]["n"]]
    if "utility_user_tasks" in m: e["sample_aer_util_kn"] = [m["utility_user_tasks"]["k"], m["utility_user_tasks"]["n"]]
    e["raw_eq_aer"] = (e.get("sample_aer_asr_kn", [0, 0]) == e["sample_raw_asr_kn"] or not smp[a]["asr_n"]) and (e.get("sample_aer_util_kn", [0, 0]) == e["sample_raw_util_kn"] or not smp[a]["u_n"])
    mism += not e["raw_eq_aer"]
    out[a] = e
res = {"arms": out, "arms_n": len(out), "arms_raw_ne_aer": mism, "aer_arms_not_in_l1": sorted(set(arms) - set(out))}
json.dump(res, open(OUT, "w"), indent=1)
print(res["arms_n"], res["arms_raw_ne_aer"], res["aer_arms_not_in_l1"])
for a, e in out.items():
    if not e["raw_eq_aer"]: print(a, e)
