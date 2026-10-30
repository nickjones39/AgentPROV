"""Run records vs logs: per released log set, compare per-pair security/utility of the run record with the logs;
compute full-set collapsed rates from the run records (all 18 runs). Prints only model ids, labels, counts, dates and
the account-path class of path-valued provenance fields (never the value). Usage: runrec3.py EXAMDIR pop.json OUT.json"""
import sys, json, re
from collections import Counter, defaultdict
sys.path.insert(0, sys.argv[1])
import gx_lib
from exam2_lib import wilson
E = gx_lib.entries(); R = gx_lib.Reader()
rows = json.load(open(sys.argv[2]))
logs = defaultdict(dict)
for r in rows:
    if r["kind"] == "user":
        logs[(r["run_set"], f"{r['suite']}-{r['cond']}-r{r['rep']}")][f"{r['ut']}|{r['it']}"] = (r["security"], r["utility"])
recs = sorted(l for l in E if re.fullmatch(r"results/[^/]+/[a-z]+-[ABC]-r\d(-calibration)?\.json", l))
OUT = {"records": {}, "compare": {}, "collapsed": {}}
RR = {}
def acct(s):
    if not isinstance(s, str): return type(s).__name__
    for name, rx in gx_lib.l1_scan.ACCOUNT_PATTERNS.items():
        m = rx.search(s)
        if m: return f"account:{name}:" + ("generic" if m.group(1).lower() in gx_lib.l1_scan.GENERIC_ACCOUNTS else "named")
    return "no-account-path"
for l in recs:
    v = R.load(E[l]); p = v["provenance"]
    rs = l.split("/")[1]; name = l.split("/")[2].removesuffix(".json")
    RR[(rs, name)] = v
    ts = p.get("timestamp"); d = ts[:10] if isinstance(ts, str) and re.match(r"\d{4}-\d\d-\d\d", ts) else type(ts).__name__
    sk = p.get("skipped_pairs")
    OUT["records"][f"{rs}/{name}"] = {"agent_model": p.get("agent_model"), "policy_model": p.get("policy_model"), "condition": p.get("condition"),
        "defence_active": p.get("defence_active"), "repeat": p.get("repeat"), "pair_count": p.get("pair_count"), "n_security": len(v["security"]),
        "skipped_pairs": len(sk) if isinstance(sk, (list, dict)) else sk, "within_policy_only": p.get("within_policy_only"),
        "benchmark_version": p.get("benchmark_version"), "date": d, "agentdojo_path_class": acct(p.get("agentdojo_path")),
        "calibration_only": p.get("calibration_only"), "logs_released": (rs, name) in logs}
    if (rs, name) in logs:
        L = logs[(rs, name)]; c = Counter()
        for k, s in v["security"].items():
            if k not in L: c["record_pair_without_log"] += 1; continue
            c["security_equal" if L[k][0] == s else "security_differ"] += 1
            c["utility_equal" if L[k][1] == v["utility"].get(k) else "utility_differ"] += 1
        c["log_pair_without_record"] = len(set(L) - set(v["security"]))
        OUT["compare"][f"{rs}/{name}"] = dict(c)
def W(k, n):
    lo, hi = wilson(k, n); return {"k": k, "n": n, "pct": round(100 * k / n, 2), "wilson95": [round(100 * lo, 2), round(100 * hi, 2)]}
for su in ("banking", "slack", "travel"):
    for co in ("A", "B"):
        reps = [RR[("runs-full-set", f"{su}-{co}-r{i}")] for i in (1, 2, 3) if ("runs-full-set", f"{su}-{co}-r{i}") in RR]
        for m in ("security", "utility"):
            pairs = set().union(*(set(x[m]) for x in reps))
            k = sum(1 for pr in pairs if sum(x[m].get(pr) is True for x in reps) >= 2)
            npairs_all3 = sum(1 for pr in pairs if all(pr in x[m] for x in reps))
            OUT["collapsed"][f"runs-full-set|{su}|{co}|{m}"] = {"repeats": len(reps), "pairs": len(pairs), "pairs_in_all_repeats": npairs_all3, "maj3": W(k, len(pairs))}
b = [OUT["collapsed"][f"runs-full-set|{s}|B|security"]["maj3"] for s in ("banking", "slack", "travel")]
OUT["collapsed"]["pooled_B_security_maj3"] = W(sum(x["k"] for x in b), sum(x["n"] for x in b))
json.dump(OUT, open(sys.argv[3], "w"), indent=1, sort_keys=True)
for k, x in OUT["records"].items(): print(k, x)
for k, x in OUT["compare"].items(): print("CMP", k, x)
for k, x in OUT["collapsed"].items(): print("MAJ", k, x)
