# ruff: noqa  (precheck examiner script for kexin-xu-01-agentharm; read-only; counts only)
"""L1 population outcome check: per-log refusal count and mean score (from l1-units rows) vs the author's docs
(prereg section 4). Local-path-model logs are matched to runs 40/42/56 by best fit (bucketed in L1).
Usage: python os1_population.py <l1-units-logs.jsonl> <out.json>"""
import json, math, sys
from collections import defaultdict
P = {  # model short: (H refusal %, H score, B refusal %, B score)
 "base": {"qwen": (20.5,.571,0,.716), "r42": (50.0,.352,0,.749), "r56": (61.4,.274,2.3,.720), "r40": (50.0,.369,0,.711),
          "gpt-4o": (45.5,.462,0,.853), "gpt-4o-mini": (25.0,.523,0,.762), "pro": (50.0,.444,6.8,.748),
          "flash": (59.1,.334,0,.774), "lite": (86.4,.235,72.7,.454), "claude5": (70.5,.091,61.4,.610)},
 "patched-judge": {"qwen": (13.6,.510,0,.733), "r42": (59.1,.355,0,.709), "r56": (63.6,.288,2.3,.733), "r40": (47.7,.388,0,.744),
          "gpt-4o": (54.5,.412,0,.844), "gpt-4o-mini": (25.0,.610,0,.751), "pro": (27.3,.514,0,.767), "flash": (54.5,.357,2.3,.794),
          "lite": (52.3,.236,0,.505), "claude5": (72.7,.091,43.2,.641)},
 "patched-judge-v2": {"claude5": (68.2,.091,9.1,.611)},
 "patched-judge-v3": {"qwen": (13.6,.533,0,.700), "r42": (54.5,.323,0,.715), "r56": (63.6,.260,2.3,.718), "r40": (50.0,.399,0,.713),
          "gpt-4o": (47.7,.472,0,.844), "gpt-4o-mini": (27.3,.545,0,.729), "pro": (25.0,.470,0,.715), "flash": (56.8,.373,2.3,.789),
          "lite": (59.1,.181,2.3,.551), "claude5": (84.1,.100,22.7,.578)}}
M = {"vllm/Qwen/Qwen3-14B": "qwen", "openai/gpt-4o-2024-08-06": "gpt-4o", "openai/gpt-4o-mini": "gpt-4o-mini",
     "google/gemini-2.5-pro": "pro", "google/gemini-2.5-flash": "flash", "google/gemini-2.5-flash-lite": "lite",
     "anthropic/claude-sonnet-5": "claude5"}
def wilson(k, n, z=1.96):
    if n == 0: return None
    p = k / n; d = 1 + z*z/n; c = (p + z*z/(2*n)) / d; h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / d
    return [round(c-h, 4), round(c+h, 4)]
rows = [json.loads(l) for l in open(sys.argv[1])]
out = {"logs": [], "matches": [], "gaps": [], "local_fit": {}}
local = defaultdict(list)
for r in rows:
    f = r["facets"]; o = r["outcomes"]
    ref = o.get("score.combined_scorer.refusal", {}); sc = o.get("score.combined_scorer.score", {})
    n = sum(sc.values()); k = int(ref.get("1.0", 0))
    mean = sum(float(v)*c for v, c in sc.items())/n if n else None
    split = "B" if f.get("task", "").endswith("benign") else "H"
    rec = {"label_tail": r["label"].rsplit("_", 1)[-1][:8], "judge_variant": f.get("judge_variant"), "model": f.get("model"),
           "split": split, "status": f.get("status"), "n_units": r["n_units"], "n_scored": n, "refusals": k,
           "mean_score": None if mean is None else round(mean, 4), "refusal_wilson95": wilson(k, n) if n else None}
    out["logs"].append(rec)
    if f.get("model") == "<local-path-model>":
        local[(f["judge_variant"], split)].append(rec); continue
    short = M.get(f.get("model")); ref_t = P.get(f.get("judge_variant"), {}).get(short)
    if not ref_t or f.get("status") != "success": continue
    rr, rs = (ref_t[0], ref_t[1]) if split == "H" else (ref_t[2], ref_t[3])
    kc = round(rr/100*44); ok = (k == kc and abs(mean - rs) <= 0.0005 + 1e-9)
    m = {**rec, "short": short, "ref_refusals": kc, "ref_mean": rs, "count_diff": k - kc, "mean_diff": round(mean - rs, 4), "match": ok,
         "gap_pp": round((k/n - kc/44)*100, 1)}
    out["matches"].append(m)
    if not ok: out["gaps"].append(m)
import itertools
for (jv, split), recs in sorted(local.items()):
    best = None
    for perm in itertools.permutations(["r40", "r42", "r56"]):
        cost = 0; det = []
        for rec, s in zip(recs, perm):
            t = P[jv][s]; rr, rs = (t[0], t[1]) if split == "H" else (t[2], t[3]); kc = round(rr/100*44)
            cost += abs(rec["refusals"]-kc)*10 + abs(rec["mean_score"]-rs); det.append({"run": s, "refusals": rec["refusals"], "ref": kc, "mean": rec["mean_score"], "ref_mean": rs})
        if best is None or cost < best[0]: best = (cost, det)
    out["local_fit"][f"{jv}|{split}"] = {"cost": round(best[0], 4), "assign": best[1],
        "all_match": all(d["refusals"] == d["ref"] and abs(d["mean"]-d["ref_mean"]) <= 0.0005+1e-9 for d in best[1])}
out["summary"] = {"compared": len(out["matches"]), "matching": sum(m["match"] for m in out["matches"]), "gaps": len(out["gaps"]),
                  "local_cells_all_match": sum(v["all_match"] for v in out["local_fit"].values()), "local_cells": len(out["local_fit"])}
json.dump(out, open(sys.argv[2], "w"), indent=1, sort_keys=True)
print(json.dumps(out["summary"])); print(json.dumps([{k: g[k] for k in ("judge_variant","short","split","n_scored","refusals","ref_refusals","mean_score","ref_mean","gap_pp")} for g in out["gaps"]]))
print(json.dumps({k: (v["all_match"], [(d["run"], d["refusals"], d["ref"], d["mean"], d["ref_mean"]) for d in v["assign"]]) for k, v in out["local_fit"].items()}))
