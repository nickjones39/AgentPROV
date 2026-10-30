"""Outcome sanity: L1 population (rollout join from exam-census.json) and L2 sample (l2-<part>.json) vs the paper (GS).
    python3 -I S/outcomes.py D   (prints JSON; D = docs/reports/precheck/data/code-agent-misalignment)"""
import json, math, sys
from pathlib import Path
D = Path(sys.argv[1])
def wilson(k, n, z=1.959964):
    if n == 0: return None
    p = k / n; den = 1 + z * z / n; c = (p + z * z / (2 * n)) / den; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(c - h, 4), round(c + h, 4)]
paper = {"MiniMax-M2": 28, "claude-sonnet-4-6": 59, "gemini-2.5-pro": 120, "glm-4.7-probe": 107, "gpt-5.3-codex": 68}
cen = json.loads((D / "exam-census.json").read_text())["rollout_join"]
l2 = json.loads((D / "l2-results-raw.json").read_text())["outcomes"]["arms"]
out = {}
for m, kp in paper.items():
    j = cen[m]; k, n = j["stream:elicited"], j["stream"]
    s = l2[f"{m}|none|none"]["elicited"]
    rate = k / n
    flag_pop = abs(rate - kp / 500) > 0.15
    lo, hi = s["wilson95"]
    flag_s = s["n"] >= 20 and (abs(s["rate"] - rate) > 0.15 or rate < lo - 0.05 or rate > hi + 0.05)
    out[m] = {"paper": [kp, 500, round(kp / 500, 4)], "rollouts_all": [k + j.get("no_stream:elicited", 0), 500],
              "corpus_pop": [k, n, round(rate, 4), wilson(k, n)], "no_stream_elicited": j.get("no_stream:elicited", 0),
              "sample": [s["k"], s["n"], s["rate"], s["wilson95"]], "gap_pop_vs_paper_pp": round(100 * (rate - kp / 500), 2),
              "gap_sample_vs_pop_pp": round(100 * (s["rate"] - rate), 2), "flag": bool(flag_pop or flag_s)}
K = sum(v["corpus_pop"][0] for v in out.values()); N = sum(v["corpus_pop"][1] for v in out.values())
ks = sum(v["sample"][0] for v in out.values()); ns = sum(v["sample"][1] for v in out.values())
post = sum(v["corpus_pop"][1] * v["sample"][2] for v in out.values()) / N
out["all"] = {"paper": [382, 2500, 0.1528], "corpus_pop": [K, N, round(K / N, 4), wilson(K, N)],
              "sample": [ks, ns, round(ks / ns, 4), wilson(ks, ns)], "sample_post_stratified_by_model": round(post, 4)}
print(json.dumps(out, indent=1))
