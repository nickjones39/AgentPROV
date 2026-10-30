# ruff: noqa  (precheck examiner script for fragfuse-agentharm; L1 population outcomes per log and per stratum; counts only)
"""Usage: python -I os1.py <l1-units-logs.jsonl> <out.json>"""
import json, math, sys
from collections import Counter, defaultdict


def wilson(k, n, z=1.96):
    if not n: return None
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - h) / d, 4), round((c + h) / d, 4)]


def summ(sc, rf):
    # sc, rf: Counter of value-string -> count (per-sample values; joint not available at L1, so non-refusal harm is not computed)
    n = sum(sc.values()); nr = sum(rf.values())
    mean = sum(float(v) * c for v, c in sc.items()) / n if n else None
    full = sum(c for v, c in sc.items() if float(v) == 1.0)
    ref = sum(c for v, c in rf.items() if float(v) == 1.0)
    return {"n_score": n, "mean_score": round(mean, 4) if mean is not None else None, "full_score": full,
            "full_rate": round(full / n, 4) if n else None, "full_wilson": wilson(full, n),
            "n_refusal": nr, "refusals": ref, "refusal_rate": round(ref / nr, 4) if nr else None,
            "refusal_wilson": wilson(ref, nr)}


rows = [json.loads(l) for l in open(sys.argv[1])]
per_log, per_stratum = {}, defaultdict(lambda: [Counter(), Counter(), 0, 0])
other_keys = Counter()
for r in rows:
    o = r["outcomes"]
    for k in o:
        if k not in ("score.combined_scorer.score", "score.combined_scorer.refusal"): other_keys[k] += 1
    sc, rf = Counter(o.get("score.combined_scorer.score", {})), Counter(o.get("score.combined_scorer.refusal", {}))
    s = per_stratum[r["stratum"]]; s[0].update(sc); s[1].update(rf); s[2] += r["n_units"]; s[3] += 1
    if sc or rf:
        per_log[r["label"]] = {"stratum": r["stratum"], "status": r["facets"].get("status"), "producer": r["facets"].get("producer"),
                               "n_units": r["n_units"], **summ(sc, rf)}
out = {"logs_with_outcomes": len(per_log), "logs": len(rows), "other_outcome_keys": dict(other_keys),
       "per_log": per_log,
       "per_stratum": {k: {"logs": v[3], "units": v[2], **summ(v[0], v[1])} for k, v in sorted(per_stratum.items())}}
open(sys.argv[2], "w").write(json.dumps(out, indent=1, sort_keys=True) + "\n")
