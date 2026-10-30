# ruff: noqa  (precheck examiner script for fragfuse-agentharm; L2 sample outcomes vs L1 raw values of the same labels; counts only)
"""Usage: python -I os2.py <aer-pass.json> <l1-units-logs.jsonl> <out.json>"""
import json, math, sys
from collections import Counter, defaultdict


def wilson(k, n, z=1.96):
    if not n: return None
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - h) / d, 4), round((c + h) / d, 4)]


ap = json.load(open(sys.argv[1]))
l1 = {r["sha256"]: r for r in map(json.loads, open(sys.argv[2]))}
by = defaultdict(list)
for e in ap["per_execution"]:
    by[(e["container"] or "").removeprefix("sha256:")].append(e)
logs, mapping_mismatch, judg = {}, 0, Counter()
for sha, es in by.items():
    r = l1[sha]
    sc = Counter(str(float(e["score"])) for e in es if e["score"] is not None)
    rf = Counter(str(float(e["refusal"])) for e in es if e["refusal"] is not None)
    rs = Counter({str(float(k)): v for k, v in r["outcomes"].get("score.combined_scorer.score", {}).items()})
    rr = Counter({str(float(k)): v for k, v in r["outcomes"].get("score.combined_scorer.refusal", {}).items()})
    ok = (sc == rs and rf == rr)
    mapping_mismatch += not ok
    for e in es:
        judg[json.dumps(e["judgements"], sort_keys=True)] += 1
    n = len(es); nsc = sum(sc.values())
    full = sum(1 for e in es if e["score"] is not None and float(e["score"]) == 1.0)
    ref = sum(1 for e in es if e["refusal"] is not None and float(e["refusal"]) == 1.0)
    nonref = [float(e["score"]) for e in es if e["refusal"] is not None and float(e["refusal"]) == 0.0 and e["score"] is not None]
    scores = [float(e["score"]) for e in es if e["score"] is not None]
    mean = sum(scores) / len(scores) if scores else None
    sd = math.sqrt(sum((s - mean) ** 2 for s in scores) / (len(scores) - 1)) if len(scores) > 1 else None
    logs[r["label"]] = {"stratum": r["stratum"], "status": r["facets"].get("status"), "producer": r["facets"].get("producer"),
                        "task_args_d8": sorted({e["task_args_d8"] for e in es}), "n_exec": n, "n_scored": nsc,
                        "mean_score": round(mean, 4) if mean is not None else None,
                        "mean_score_ci95": [round(mean - 1.96 * sd / math.sqrt(len(scores)), 4), round(mean + 1.96 * sd / math.sqrt(len(scores)), 4)] if sd else None,
                        "full": full, "full_wilson": wilson(full, nsc), "refusals": ref, "refusal_wilson": wilson(ref, sum(rf.values())),
                        "nonrefusal_n": len(nonref), "nonrefusal_mean": round(sum(nonref) / len(nonref), 4) if nonref else None,
                        "with_tool_call": sum(1 for e in es if e["tool"]),
                        "statuses": dict(Counter(e["status"] for e in es)), "completeness": dict(Counter(e["completeness"] for e in es)),
                        "issues": dict(Counter(i for e in es for i in e["issues"])),
                        "attack_id": dict(Counter(str(e["attack_id"]) for e in es)),
                        "raw_equals_mapped": ok}
out = {"labels": len(by), "executions": len(ap["per_execution"]), "labels_mapping_mismatch": mapping_mismatch,
       "judgement_name_sets": dict(judg), "per_log": dict(sorted(logs.items()))}
open(sys.argv[3], "w").write(json.dumps(out, indent=1, sort_keys=True) + "\n")
