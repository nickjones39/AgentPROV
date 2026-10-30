"""H1-H8 tallies over census.json (counts and labels only)."""
import sys, json
from collections import Counter, defaultdict
P = json.load(open(sys.argv[1]))["per_label"]
res = {}
# per cell table (tree, model, kind/attacked)
cell = Counter()
for lab, r in P.items():
    kind = "attacked" if r["attack"] == "important_instructions" else ("prepass" if r["kind"] == "prepass" else "benign")
    cell[(r["tree"], r["model"], r["benchmark_version"], kind)] += 1
res["cells"] = {"|".join(map(str, k)): v for k, v in sorted(cell.items())}
att = [r for r in P.values() if r["attack"] == "important_instructions"]
res["H1"] = {"attacked": len(att), "attacked_security_true": sum(r["security"] is True for r in att),
             "utility": dict(Counter(str(r["utility"]) for r in P.values())),
             "security_all": dict(Counter(str(r["security"]) for r in P.values())),
             "none_security": dict(Counter(str(r["security"]) for r in P.values() if r["attack"] == "none"))}
inc = {l: r for l, r in P.items() if r["variant"].endswith("incomplete")}
res["H2"] = {"incomplete": {l: {"model": r["model"], "roles": r["roles"], "error_null": r["error_null"], "kind": r["kind"],
              "utility": r["utility"], "security": r["security"]} for l, r in inc.items()},
             "retired_model_logs": sum(r["model"] in ("claude-3-7-sonnet-20250219", "claude-3-haiku-20240307") for r in P.values()),
             "retired_with_assistant": sum(r["model"] in ("claude-3-7-sonnet-20250219", "claude-3-haiku-20240307") and r["roles"].get("assistant", 0) > 0 for r in P.values())}
res["H3"] = dict(Counter(f"{r['tree']}|{r['ts_month']}" for r in P.values()))
res["H3_dates"] = dict(Counter(f"{r['tree']}|{r['ts_date']}" for r in P.values()))
res["H4"] = {"tree_vs_bench": dict(Counter(f"{r['tree']}|{r['benchmark_version']}" for r in P.values())),
             "inj6_13_bench": dict(Counter(r["benchmark_version"] for r in P.values()
                                         if (r["injection_task_id"] or "") in {f"injection_task_{i}" for i in range(6, 14)}
                                         or r["task"] in {f"injection_task_{i}" for i in range(6, 14)}))}
pre_v122_hi = {l: r["utility"] for l, r in P.items() if r["kind"] == "prepass" and r["task"] in {f"injection_task_{i}" for i in range(6, 14)}}
res["H5"] = {"prepass_inj6_13_utility": dict(Counter(str(v) for v in pre_v122_hi.values())), "n": len(pre_v122_hi),
             "ph_nonnull": sum(r["ph_nonnull"] for r in P.values()), "ph_absent": sum(r["ph_absent"] for r in P.values()),
             "ph_null": sum(r["ph_null"] for r in P.values())}
nd = defaultdict(Counter); ndl = defaultdict(Counter)
for r in P.values():
    for k, n in r["needles"].items():
        nd[f"{r['benchmark_version']}"][k] += n; ndl[f"{r['benchmark_version']}"][k] += 1
res["H6"] = {"occurrences": {k: dict(v) for k, v in nd.items()}, "logs": {k: dict(v) for k, v in ndl.items()}}
res["H7"] = {"models": dict(Counter(r["model"] for r in P.values())), "attacks": dict(Counter(str(r["attack_type"]) for r in P.values())),
             "suites": dict(Counter(r["suite_name"] for r in P.values()))}
# H8 grid: (tree, model, user task, injection task) cells: from the raw ids
g = Counter((r["tree"], r["model"], r["user_task_id"], r["injection_task_id"]) for r in P.values())
res["H8"] = {"cells": len(g), "dup_cells": sum(v > 1 for v in g.values())}
hk = [r for r in P.values() if r["model"] == "claude-haiku-4-5-20251001" and r["attack"] == "important_instructions"]
ut = sorted({r["user_task_id"] for r in hk}); it = sorted({r["injection_task_id"] for r in hk})
res["H8"]["haiku_attacked_grid"] = {"user_tasks": len(ut), "inj_tasks": len(it), "cells": len({(r['user_task_id'], r['injection_task_id']) for r in hk})}
res["raw_ids_vs_path"] = sum(1 for r in P.values() if not ((r["kind"] == "prepass" and r["user_task_id"] == r["task"]) or (r["kind"] != "prepass" and r["user_task_id"] == r["task"])))
res["inj_id_vs_file"] = dict(Counter(f"{r['file']==(r['injection_task_id'] or 'none')}" for r in P.values()))
# utility by arm
arm = defaultdict(Counter)
for r in P.values():
    kind = "attacked" if r["attack"] == "important_instructions" else r["kind"]
    arm[f"{r['model']}|{r['benchmark_version']}|{kind}"][f"u={r['utility']}|s={r['security']}"] += 1
res["arms"] = {k: dict(v) for k, v in sorted(arm.items())}
res["tool_err_logs"] = sum(r["tool_err"] > 0 for r in P.values())
print(json.dumps(res, indent=1, sort_keys=True))
