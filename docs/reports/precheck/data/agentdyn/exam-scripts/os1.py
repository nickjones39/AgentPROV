"""agentdyn OS-1: whole-population raw outcome recount per pipeline directory (L1 rows) against the paper (prereg s4).

BU = utility on user_task_*/none/none files; UA/ASR = utility/security on important_instructions files; overall = unweighted
mean of the three suite rates (paper convention). Pre-pass, direct and travel files are in no metric. Files without outcome
keys are excluded from denominators and counted. Gap rule (README s4) on the population: |gap| > 15 pp with n >= 20, or the
pooled Wilson 95% interval excludes the paper value by more than 5 pp. Counts only.
Usage (from the worktree root): python3 os1.py <out.json>
"""
import json, collections, re, sys, os
sys.path.insert(0, "tools/analysis2")
from exam2_lib import wilson

W = os.path.expanduser("~/.agentprov/migration-work/precheck/agentdyn")
R = json.load(open("docs/reports/precheck/data/agentdyn/research.json"))
SUITES = ("shopping", "github", "dailylife")
MET = {"benign_utility": "BU", "utility_under_attack": "UA", "asr": "ASR"}

paper = {}
for r in R["reported_results"]:
    m = re.match(r"([abc]):(\S+) ", r["arm"])
    key = r["metric"].split(" ")[0]
    if not m or key not in MET:
        continue
    v = re.match(r"([\d.]+) \(([\d.]+)/([\d.]+)/([\d.]+)\)", r["value"])
    if not v:
        continue  # the v1 row of gpt-4o-mini drift (superseded by v3)
    paper[(m.group(1), m.group(2), MET[key])] = (float(v.group(1)), tuple(float(x) for x in v.group(2, 3, 4)))

cnt = collections.defaultdict(lambda: [0, 0, 0, 0])  # n, utility true, security true, missing outcome
gh = collections.Counter()
for p in "abc":
    for line in open(f"{W}/l1-units-{p}.jsonl"):
        r = json.loads(line); f = r["facets"]; o = r["outcomes"]
        if f["task_kind"] != "user" or f["attack_dir"] not in ("none", "important_instructions"):
            continue
        if f["suite"] == "github" and f["task_dir"] in ("user_task_5", "user_task_7", "user_task_8", "user_task_11"):
            gh[(p, f["task_dir"], str(o.get("utility")))] += 1
        c = cnt[(p, f["pipeline_dir"], f["attack_dir"], f["suite"])]
        if o.get("utility") is None or o.get("security") is None:
            c[3] += 1; continue
        c[0] += 1; c[1] += o["utility"] is True; c[2] += o["security"] is True

rows = []
for (p, d) in sorted({(k[0], k[1]) for k in cnt} | {(k[0], k[1]) for k in paper}):
    for met in ("BU", "UA", "ASR"):
        ad = "none" if met == "BU" else "important_instructions"
        per, ns, ks, miss = [], [], [], 0
        for s in SUITES:
            c = cnt.get((p, d, ad, s))
            miss += c[3] if c else 0
            if not c or c[0] == 0:
                per.append(None); ns.append(0); ks.append(0); continue
            k = c[2] if met == "ASR" else c[1]
            per.append(100 * k / c[0]); ns.append(c[0]); ks.append(k)
        valid = [x for x in per if x is not None]
        macro = sum(valid) / len(valid) if valid else None
        n, k = sum(ns), sum(ks)
        lo, hi = wilson(k, n) if n else (None, None)
        pv = paper.get((p, d, met))
        gap = None if (pv is None or macro is None) else macro - pv[0]
        flag = bool(pv is not None and n and ((n >= 20 and abs(gap) > 15) or pv[0] < 100 * lo - 5 or pv[0] > 100 * hi + 5))
        if pv is None and macro is None:
            continue
        rows.append({"part": p, "dir": d, "metric": met, "n": n, "k": k, "missing_outcome": miss, "suite_n": ns,
                     "suite_rate": [None if x is None else round(x, 2) for x in per],
                     "macro": None if macro is None else round(macro, 2), "pooled": round(100 * k / n, 2) if n else None,
                     "wilson95_pooled": None if lo is None else [round(100 * lo, 2), round(100 * hi, 2)],
                     "paper": None if pv is None else pv[0], "paper_suite": None if pv is None else list(pv[1]),
                     "gap_pp": None if gap is None else round(gap, 2),
                     "suite_gap_pp": None if pv is None else [None if x is None else round(x - y, 2) for x, y in zip(per, pv[1])],
                     "flag": flag})
comparable = [r for r in rows if r["paper"] is not None and r["macro"] is not None]
out = {"note": __doc__.strip().splitlines()[0], "paper_values": len(paper), "comparable": len(comparable),
       "within_0.05pp": sum(abs(r["gap_pp"]) <= 0.05 for r in comparable),
       "off_gt_0.05pp": [[r["part"], r["dir"], r["metric"], r["macro"], r["paper"], r["gap_pp"], r["suite_gap_pp"]] for r in comparable if abs(r["gap_pp"]) > 0.05],
       "off_gt_5pp": [[r["part"], r["dir"], r["metric"], r["gap_pp"]] for r in comparable if abs(r["gap_pp"]) > 5],
       "flagged_by_gap_rule": [[r["part"], r["dir"], r["metric"], r["gap_pp"], r["n"]] for r in rows if r["flag"]],
       "paper_without_log_support": [[r["part"], r["dir"], r["metric"]] for r in rows if r["paper"] is not None and r["macro"] is None],
       "issue8_github_tasks_utility": {f"{p}|{t}|utility={u}": n for (p, t, u), n in sorted(gh.items())},
       "rows": rows}
json.dump(out, open(sys.argv[1], "w"), indent=1)
print(out["paper_values"], "paper values;", out["comparable"], "comparable;", out["within_0.05pp"], "within 0.05 pp;", len(out["off_gt_5pp"]), "> 5 pp")
print("flagged", out["flagged_by_gap_rule"]); print("no log support", out["paper_without_log_support"]); print("issue8", out["issue8_github_tasks_utility"])
