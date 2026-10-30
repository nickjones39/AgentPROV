"""OS-1 population outcome rates (raw L1 outcomes; counts only). Usage: os1.py EXAMDIR pop.json OUT.json"""
import sys, json
from collections import defaultdict, Counter
sys.path.insert(0, sys.argv[1])
import gx_lib
from exam2_lib import wilson
rows = json.load(open(sys.argv[2]))
E = gx_lib.entries(); R = gx_lib.Reader()
P42 = {(p["user_task"], p["injection_task"]) for p in R.load(E["results/pairs.json"]) if p["suite"] == "banking" and p["within_policy"]}
OUT = {"pairs42": len(P42)}
att = [r for r in rows if r["kind"] == "user"]
def W(k, n):
    lo, hi = wilson(k, n); return [round(100 * lo, 2), round(100 * hi, 2)]
def rate(k, n): return {"k": k, "n": n, "pct": round(100 * k / n, 2) if n else None, "wilson95": W(k, n)}
# per log set, per run
per = defaultdict(lambda: Counter())
for r in att:
    s = per[f"{r['run_set']}/{r['logset']}"]
    s["n"] += 1; s["asr"] += r["security"] is True; s["util"] += r["utility"] is True
    if (r["ut"], r["it"]) in P42 and r["suite"] == "banking":
        s["n42"] += 1; s["asr42"] += r["security"] is True; s["util42"] += r["utility"] is True
OUT["per_set_per_run"] = {k: {"n": v["n"], "asr": rate(v["asr"], v["n"]), "utility": rate(v["util"], v["n"]),
                               "n42": v["n42"], "asr42": rate(v["asr42"], v["n42"]) if v["n42"] else None} for k, v in sorted(per.items())}
# pairs by arm
arms = defaultdict(lambda: defaultdict(dict))
for r in att:
    arms[(r["run_set"], r["suite"], r["cond"])][(r["ut"], r["it"])][r["rep"]] = r
def collapse(arm, metric, restrict=None, mode="auto"):
    out = Counter()
    for pair, reps in arm.items():
        if restrict is not None and pair not in restrict:
            continue
        vals = [reps[k][metric] is True for k in sorted(reps)]
        out["pairs"] += 1; out[f"reps{len(vals)}"] += 1
        m = mode if mode != "auto" else ("maj" if len(vals) >= 3 else "any")
        if m == "maj": out["true"] += sum(vals) >= 2
        elif m == "any": out["true"] += any(vals)
        elif m == "all": out["true"] += all(vals)
        out["and"] += all(vals); out["or"] += any(vals); out["sum_runs"] += sum(vals); out["runs"] += len(vals)
    return out
agg = {}
for (rs, su, co), arm in sorted(arms.items()):
    key = f"{rs}|{su}|{co}"
    d = {}
    for metric, name in (("security", "asr"), ("utility", "utility")):
        c = collapse(arm, metric)
        d[name] = {"pairs": c["pairs"], "repeats": {k: v for k, v in c.items() if k.startswith("reps")},
                   "collapsed(maj3 if 3 repeats else any)": rate(c["true"], c["pairs"]), "and": c["and"], "or": c["or"],
                   "per_run_mean": rate(c["sum_runs"], c["runs"])}
        if su == "banking" and rs in ("runs", "runs-strong-agent", "runs-strong-policy", "runs-strong-policy-fixed", "runs-claude-policy"):
            c42 = collapse(arm, metric, P42)
            d[name + "_42"] = {"pairs": c42["pairs"], "collapsed": rate(c42["true"], c42["pairs"]) if c42["pairs"] else None,
                               "and": c42["and"], "or": c42["or"]}
    agg[key] = d
OUT["arms"] = agg
# pooled full-set B
b = {s: collapse(arms[("runs-full-set", s, "B")], "security") for s in ("banking", "slack", "travel")}
OUT["pooled_fullset_B_asr"] = {"collapsed_any_for_travel": rate(sum(c["true"] for c in b.values()), sum(c["pairs"] for c in b.values())),
    "travel_and": b["travel"]["and"], "travel_or": b["travel"]["or"],
    "bounds_numerator": [b["banking"]["true"] + b["slack"]["true"] + b["travel"]["and"], b["banking"]["true"] + b["slack"]["true"] + b["travel"]["or"]],
    "pairs": sum(c["pairs"] for c in b.values())}
json.dump(OUT, open(sys.argv[3], "w"), indent=1, sort_keys=True)
print("pairs42", len(P42), "pairs42 in runs grid", len(P42 & {(r['ut'], r['it']) for r in att if r['run_set'] == 'runs'}))
for k, v in OUT["per_set_per_run"].items():
    print(f"{k:48s} n={v['n']:3d} ASR {v['asr']['k']:3d} {v['asr']['pct']:6.2f} U {v['utility']['k']:3d} {v['utility']['pct']:6.2f}", f"n42={v['n42']} asr42={v['asr42']['k'] if v['asr42'] else ''}")
for k, d in agg.items():
    print(k, {m: (x["pairs"], x.get("collapsed(maj3 if 3 repeats else any)", x.get("collapsed")), "and", x["and"], "or", x["or"]) for m, x in d.items()})
print(OUT["pooled_fullset_B_asr"])
