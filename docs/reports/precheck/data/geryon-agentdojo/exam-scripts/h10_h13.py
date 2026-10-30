"""H10 (slack B IT5 security true with every attacker-goal call denied) and H13 (identical fingerprints across repeats)."""
import sys, json
from collections import Counter, defaultdict
rows = json.load(open(sys.argv[1]))
c = Counter()
for r in rows:
    if r["suite"] == "slack" and r["it"] == "injection_task_5" and r["kind"] == "user":
        k = f"cond={r['cond']}|security={r['security']}"
        c[k] += 1
        if r["security"] is True:
            c[f"{k}|goal_calls>0={r['goal5_calls'] > 0}"] += 1
            if r["goal5_calls"] and r["goal5_calls"] == r["goal5_denied"]:
                c[f"{k}|all_goal_calls_denied"] += 1
            if r["goal5_calls"] and r["goal5_denied"]:
                c[f"{k}|some_goal_call_denied"] += 1
            if r["goal5_calls"] == 0:
                c[f"{k}|no_goal_call"] += 1
print("H10", dict(sorted(c.items())))
# H13: groups = same (run_set, suite, cond, ut, it) over repeats
g = defaultdict(list)
for r in rows:
    g[(r["run_set"], r["suite"], r["cond"], r["ut"], r["it"])].append(r["fp"])
multi = {k: v for k, v in g.items() if len(v) >= 2}
same = sum(1 for v in multi.values() if len(set(v)) < len(v))
allsame = sum(1 for v in multi.values() if len(set(v)) == 1)
print("H13 pairs with >=2 repeats", len(multi), "with any identical repeat fp", same, f"{100*same/len(multi):.2f}%", "all repeats identical", allsame)
att = {k: v for k, v in multi.items() if k[3].startswith("user")}
print("  attacked", len(att), sum(1 for v in att.values() if len(set(v)) < len(v)), "prepass", len(multi) - len(att), sum(1 for k, v in multi.items() if not k[3].startswith('user') and len(set(v)) < len(v)))
# identical fp across conditions A vs B (same run_set, suite, ut, it)
ab = defaultdict(lambda: defaultdict(set))
for r in rows:
    ab[(r["run_set"], r["suite"], r["ut"], r["it"])][r["cond"]].add(r["fp"])
x = sum(1 for d in ab.values() if "A" in d and "B" in d and d["A"] & d["B"])
print("A/B identical fp cells", x, "of", sum(1 for d in ab.values() if 'A' in d and 'B' in d))
