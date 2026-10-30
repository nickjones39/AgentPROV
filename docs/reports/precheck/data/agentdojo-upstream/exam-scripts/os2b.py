"""Pooled sample rates vs (a) stratum-matched population expectation and (b) paper-weighted expectation (prereg section 4)."""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, "tools/analysis2")
from exam2_lib import wilson

W = Path.home() / ".agentprov/migration-work/precheck/agentdojo-upstream"
# paper per-dir II values (UA, ASR) in percent; head = W (results page), 2024-06 = P1 (v1 Table 3 / Table 5)
PAPER = {
    "head": {"gpt-4o-2024-05-13": (50.08, 47.69), "claude-3-opus-20240229": (52.46, 11.29), "claude-3-sonnet-20240229": (33.23, 26.71),
             "command-r-plus": (25.12, 4.45), "gpt-3.5-turbo-0125": (34.66, 10.33), "gpt-4-turbo-2024-04-09": (54.05, 28.62),
             "gemini-1.5-flash-001": (34.18, 12.24), "gemini-1.5-pro-001": (28.93, 28.62), "meta-llama_Llama-3-70b-chat-hf": (18.28, 25.60),
             "claude-3-5-sonnet-20240620": (51.19, 33.86), "gpt-4o-2024-05-13-spotlighting_with_delimiting": (55.64, 41.65),
             "gpt-4o-2024-05-13-transformers_pi_detector": (21.14, 7.95), "gpt-4o-2024-05-13-repeat_user_prompt": (67.25, 27.82),
             "gpt-4o-2024-05-13-tool_filter": (56.28, 6.84), "claude-3-haiku-20240307": (33.39, 9.06), "command-r": (30.84, 3.34),
             "gpt-4-0125-preview": (40.70, 56.28), "gpt-4o-mini-2024-07-18": (49.92, 27.19), "gemini-1.5-flash-002": (32.43, 3.50),
             "gemini-1.5-pro-002": (47.06, 17.01), "claude-3-5-sonnet-20241022": (72.50, 1.11), "gemini-2.0-flash-exp": (39.90, 17.01)},
    "2024-06": {"gpt-4o-2024-05-13": (44.99, 53.10), "claude-3-opus-20240229": (49.60, 12.89), "claude-3-sonnet-20240229": (30.05, 30.52),
                "command-r-plus": (25.60, 0.95), "gpt-3.5-turbo-0125": (34.82, 8.90), "gpt-4-turbo-2024-04-09": (51.67, 31.96),
                "gemini-1.5-flash-001": (34.02, 13.35), "gemini-1.5-pro-001": (29.61, 27.50), "meta-llama_Llama-3-70b-chat-hf": (19.39, 15.10),
                "gpt-4o-2024-05-13-spotlighting_with_delimiting": (50.24, 46.26), "gpt-4o-2024-05-13-transformers_pi_detector": (20.67, 7.95),
                "gpt-4o-2024-05-13-repeat_user_prompt": (65.66, 30.84), "gpt-4o-2024-05-13-tool_filter": (53.26, 7.47)},
}
V12 = ("Meta-SecAlign-70B", "Meta-SecAlign-70B-repeat_user_prompt", "meta-llama_Llama-3.3-70B-Instruct",
       "meta-llama_Llama-3.3-70B-Instruct-repeat_user_prompt", "claude-3-7-sonnet-20250219", "gemini-2.0-flash-001")


def gap(k, n, exp):
    lo, hi = wilson(k, n)
    rate = k / n
    g = 100 * (rate - exp)
    excl = 100 * max(lo - exp, exp - hi, 0)
    flag = (abs(g) > 15 and n >= 20) or excl > 5
    return {"n": n, "k": k, "rate": round(100 * rate, 2), "wilson95": [round(100 * lo, 2), round(100 * hi, 2)],
            "expected": round(100 * exp, 2), "gap_pp": round(g, 2), "excluded_by_pp": round(excl, 2), "flag": flag}


OUT = {}
for part in ("head", "2024-06"):
    rows = [json.loads(l) for l in open(W / f"l1-units-{part}.jsonl")]
    bysha = {r["sha256"]: r for r in rows}
    st = defaultdict(Counter)
    for r in rows:
        if r["facets"]["task_kind"] == "prepass":
            continue
        c = st[r["stratum"]]
        c["n"] += 1; c["u"] += r["outcomes"].get("utility") is True; c["s"] += r["outcomes"].get("security") is True
    C = W / f"l2-{part}-j2.partial"
    acc = defaultdict(lambda: {"n": 0, "u": 0, "s": 0, "eu": 0.0, "es": 0.0, "pu": 0.0, "ps": 0.0, "pn": 0, "pk_u": 0, "pk_s": 0})
    for line in open(C / "executions.jsonl"):
        r = json.loads(line)
        u = bysha[r["raw"][0]["sha256"].split(":", 1)[1]]
        f = u["facets"]
        if f["task_kind"] == "prepass":
            continue
        recs = [json.loads(x) for x in open(C / r["paths"]["aer"])]
        j = {x["name"]: x.get("value") for x in recs if x["k"] == "judgement" and x.get("subject") == "run"}
        a, d = f["attack_dir"], f["pipeline_dir"]
        keys = []
        if a == "important_instructions":
            keys.append("II_753dirs" if d not in V12 else "II_v12dirs")
        elif a == "none":
            keys.append("benign")
        if d == "gpt-4o-2024-05-13" and a != "none":
            keys.append("gpt4o_base_attacked")
        if a not in ("none",):
            keys.append("all_attacked")
        c = st[u["stratum"]]
        for key in keys:
            x = acc[key]
            x["n"] += 1; x["u"] += j.get("utility") is True; x["s"] += j.get("security") is True
            x["eu"] += c["u"] / c["n"]; x["es"] += c["s"] / c["n"]
            if key.startswith("II_753") and d in PAPER[part]:
                pu, ps = PAPER[part][d]
                x["pn"] += 1; x["pu"] += pu / 100; x["ps"] += ps / 100
                x["pk_u"] += j.get("utility") is True; x["pk_s"] += j.get("security") is True
    res = {}
    for key, x in acc.items():
        n = x["n"]
        e = {"utility_vs_population_strata": gap(x["u"], n, x["eu"] / n),
             "asr_vs_population_strata" if key != "benign" else "security_vs_population_strata": gap(x["s"], n, x["es"] / n)}
        if x["pn"]:
            e["paper_subset_n"] = x["pn"]
            e["ua_vs_paper"] = gap(x["pk_u"], x["pn"], x["pu"] / x["pn"])
            e["asr_vs_paper"] = gap(x["pk_s"], x["pn"], x["ps"] / x["pn"])
        res[key] = e
    OUT[part] = res
json.dump(OUT, open(sys.argv[1], "w"), indent=1, sort_keys=True)
for p, res in OUT.items():
    for k, e in res.items():
        for m, g in e.items():
            if isinstance(g, dict):
                print(p, k, m, g)
