"""Population tallies from the scratch L1 unit rows (raw outcome histograms; no mapping). Counts only."""
import json, sys, math, pathlib, collections as C
W = pathlib.Path.home() / ".agentprov/migration-work/precheck/controlarena-persistent"
PARTS = ["zip-3-001", "zip-3-002", "zip-3-003", "batch-runs", "auditor"]
def wilson(k, n, z=1.959964):
    if n == 0: return None
    p = k / n; d = 1 + z*z/n; c = (p + z*z/(2*n)) / d; h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / d
    return [round(100*(c-h), 2), round(100*(c+h), 2)]
def num(v):
    try: return float(v)
    except Exception: return None
rows = []
for p in PARTS:
    for line in (W / f"l1-units-{p}.jsonl").open():
        r = json.loads(line); r["_part"] = p; rows.append(r)
out = {"rows": len(rows)}
# dedup by sha256 (byte-identical logs across parts) - keep first in import order 001,002,003,batch,auditor
seen = {}; dup = C.Counter(); dup_units = C.Counter()
for r in rows:
    if r.get("parse") != "ok" or not r.get("n_units"): continue
    if r["sha256"] in seen:
        dup[(seen[r["sha256"]], r["_part"])] += 1; dup_units[(seen[r["sha256"]], r["_part"])] += r["n_units"]; r["_dup"] = True
    else: seen[r["sha256"]] = r["_part"]
out["byte_dup_nonempty"] = {f"{a}->{b}": [dup[(a, b)], dup_units[(a, b)]] for a, b in dup}
# per experiment tallies
def exp(r): return r["facets"].get("experiment", "<none>")
arms = C.defaultdict(lambda: C.Counter())
score_vals = C.Counter(); score_out = C.Counter(); score_null = C.Counter()
hdr_none = C.Counter(); sizes = C.Counter()
noh = C.Counter()
for r in rows:
    if "no_header" in r.get("flags", []): noh[r["_part"]] += 1
    if r.get("parse") != "ok" or r.get("_dup"): continue
    f = r["facets"]; e = exp(r)
    st = "+".join(sorted(k for k in r.get("unit_facets", {}).get("side_task_name", {}) )) or "<none>"
    o = r.get("outcomes", {})
    side = o.get("score.side_task_success.side_task_success", {})
    c = side.get('"C"', 0); n = r.get("n_units", 0)
    td = [num(k) for k in o.get("score.score_pr_diff_task_sequence", {}) if num(k) is not None]
    key = (e, st, f.get("mode", "<none>"))
    a = arms[key]; a["logs"] += 1; a["samples"] += n; a["any_C"] += 1 if c else 0; a["C_samples"] += c
    a[f"len{n}"] += 1
    if f.get("model") == "none/none": hdr_none[r["_part"]] += 1
    if td:
        mx = max(td); a["td_logs"] += 1; a["td_gt6"] += mx > 6
        if c: a["succ_td"] += 1; a["succ_ev_le6"] += mx <= 6; a["succ_ev_lt6"] += mx < 6
    for k, h in o.items():
        if not k.startswith("score.") or "success" in k: continue
        for v, cnt in h.items():
            x = num(v)
            if x is None:
                score_null[v] += cnt
            else:
                score_vals["num"] += cnt
                if not (0 <= x <= 10): score_out[k] += cnt
out["no_header_artefacts"] = dict(noh)
out["none_none_header_logs"] = dict(hdr_none)
out["arms"] = {" | ".join(k): dict(v) for k, v in sorted(arms.items())}
out["H10"] = {"numeric_values": score_vals["num"], "outside_0_10": dict(score_out), "non_numeric": dict(score_null)}
g = {k: v for k, v in arms.items() if k[0] == "logs/gradual_f3m1.zip"}
out["H6_any_PR"] = {k[1]: {"runs": v["logs"], "any_C": v["any_C"], "wilson": wilson(v["any_C"], v["logs"]), "succ_td": v["succ_td"], "ev_le6": v["succ_ev_le6"], "ev_lt6": v["succ_ev_lt6"]} for k, v in g.items()}
json.dump(out, open(sys.argv[1], "w"), indent=1, sort_keys=True)
print(json.dumps(out, indent=None, sort_keys=True))
