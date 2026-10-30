"""L1 population analysis of authority-caps-agentdojo from the committed-sample L1 rows (no raw read). Counts only.
Location = container (nested tar) or model_dir; directory = pipeline_dir. Byte-distinct = sha256.
Usage: python3 -I pop.py OUT.json"""
import json, sys, math, collections as C
from pathlib import Path
ROWS = Path.home() / ".agentprov/migration-work/precheck/authority-caps-agentdojo/l1-units-head.jsonl"
LOC = {"original-study/experiments/current_models/runs": "L1cur", "original-study/experiments/pilot/runs": "L1pilot",
       "original-study/experiments/reexecuted_caps/runs_exp4.tar.gz": "exp4",
       "original-study/experiments/templates_and_autoconfirm/runs_exp5.tar.gz": "exp5", "raw-additions/runs_exp7.tar.gz": "exp7"}
def wilson(k, n, z=1.959964):
    if n == 0: return None
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(100 * (c - h) / d, 2), round(100 * (c + h) / d, 2)]
def model(pd):
    for s in ("-autoconfirm", "-capA3", "-capA4", "-noegress", "-rep1", "-rep2", "-rep3"): pd = pd.replace(s, "")
    return pd
rows = [json.loads(l) for l in open(ROWS)]
KIND = lambda f: "prepass" if f["task_kind"] == "prepass" else ("benign" if f["attack_dir"] == "none" else "attacked")
out = {}
for u in rows:
    lab = u["label"]; f = u["facets"]
    u["loc"] = LOC[lab.split("!/")[0]] if "!/" in lab else LOC[f["model_dir"]]
    u["dir"] = f"{u['loc']}/{f['pipeline_dir']}"
out["members"] = len(rows); out["distinct_sha"] = len({u["sha256"] for u in rows}); out["distinct_fp"] = len({u["fp"] for u in rows})
out["members_by_dir"] = dict(sorted(C.Counter(u["dir"] for u in rows).items()))
out["members_by_loc"] = dict(C.Counter(u["loc"] for u in rows))
# byte copies and their directory groups
g = C.defaultdict(list)
for u in rows: g[u["sha256"]].append(u)
grp = C.Counter()
for s, us in g.items():
    if len(us) > 1: grp["+".join(sorted(x["dir"] for x in us))] += len(us) - 1
gg = C.Counter()
for k, n in grp.items():
    dirs = k.split("+"); gg["|".join(sorted(set(d.split("/", 1)[1] for d in dirs))) + f" x{len(dirs)}"] += n
out["extra_copies"] = sum(grp.values()); out["copy_groups_by_pipeline_dir"] = dict(gg)
# distinct per model / attack / suite
first = {s: us[0] for s, us in g.items()}
out["distinct_by_model"] = dict(C.Counter(model(u["facets"]["pipeline_dir"]) for u in first.values()))
out["distinct_by_attack"] = dict(C.Counter(u["facets"]["attack_dir"] for u in first.values()))
out["distinct_by_suite"] = dict(C.Counter(u["facets"]["suite"] for u in first.values()))
out["distinct_by_variant"] = dict(C.Counter(u["variant"] for u in first.values()))
# fp groups with different bytes
fpg = C.defaultdict(set)
for u in rows: fpg[u["fp"]].add(u["sha256"])
multi = {k: v for k, v in fpg.items() if len(v) > 1}
out["fp_groups_different_bytes"] = {"groups": len(multi), "distinct_files": sum(len(v) for v in multi.values())}
# arms: per directory x attack
arms = C.defaultdict(C.Counter)
for u in rows:
    f = u["facets"]; o = u["outcomes"]; a = f["attack_dir"]; kind = KIND(f)
    key = f"{u['dir']}|{a}"
    A = arms[key]; A["n"] += 1; A[f"kind:{kind}"] += 1
    err = o["error_present"] is True; inc = "incomplete" in u["flags"]
    if err: A["error"] += 1
    if inc: A["incomplete"] += 1
    if kind == "attacked":
        A["att_n"] += 1; A["att_sec"] += o["security"] is True; A["att_uti"] += o["utility"] is True
        if not err and not inc:
            A["att_ok_n"] += 1; A["att_ok_sec"] += o["security"] is True; A["att_ok_uti"] += o["utility"] is True
    elif kind == "benign":
        A["ben_n"] += 1; A["ben_uti"] += o["utility"] is True
        if not err and not inc: A["ben_ok_n"] += 1; A["ben_ok_uti"] += o["utility"] is True
    elif kind == "prepass":
        A["pre_n"] += 1; A["pre_uti"] += o["utility"] is True
out["task_kinds"] = dict(C.Counter(KIND(u["facets"]) for u in rows))
out["arms"] = {k: dict(v) for k, v in sorted(arms.items())}
# errors / incompletes / flags by dir and kind
out["errors_by_dir_kind"] = dict(C.Counter(f"{u['dir']}|{KIND(u['facets'])}" for u in rows if u["outcomes"]["error_present"] is True))
out["errors_distinct"] = len({u["sha256"] for u in rows if u["outcomes"]["error_present"] is True})
out["incomplete_by_dir"] = dict(C.Counter(u["dir"] for u in rows if "incomplete" in u["flags"]))
out["trailing_calls_members"] = sum("trailing_calls" in u["flags"] for u in rows)
out["trailing_calls_distinct"] = len({u["sha256"] for u in rows if "trailing_calls" in u["flags"]})
out["flags"] = dict(C.Counter(fl for u in rows for fl in u["flags"]))
# pilot composition
pil = [u for u in rows if u["loc"] == "L1pilot"]
out["pilot"] = dict(C.Counter(f"{u['facets']['pipeline_dir']}|{u['facets']['suite']}|{KIND(u['facets'])}|{u['facets']['attack_dir']}" for u in pil))
# rep cell sets
cells = C.defaultdict(set)
for u in rows:
    f = u["facets"]; cells[u["dir"]].add((f["suite"], f["task_dir"], f["file"], f["attack_dir"]))
reps = {d: c for d, c in cells.items() if "-rep" in d}
out["reps"] = {}
for d, c in sorted(reps.items()):
    base = cells[{"gpt-6-luna": "L1cur/gpt-6-luna"}.get(model(d.split("/", 1)[1]), "exp7/" + model(d.split("/", 1)[1]))]
    out["reps"][d] = {"n": len(c), "suites": dict(C.Counter(x[0] for x in c)), "kinds": dict(C.Counter(
        "attacked" if x[3] != "none" else ("prepass" if x[1].startswith("injection_task") else "benign") for x in c)),
        "subset_of_base": c <= base, "same_as_rep1": c == reps[d.rsplit("-rep", 1)[0] + "-rep1"]}
# 4-run agreement on rep attacked cells
BASE = {"gpt-4o-mini-2024-07-18": "exp7/gpt-4o-mini-2024-07-18", "gpt-6-luna": "L1cur/gpt-6-luna"}
for m in ("gpt-4o-mini-2024-07-18", "gpt-6-luna"):
    att = sorted(x for x in reps[f"exp7/{m}-rep1"] if x[3] != "none")
    sec = {}
    for d in [BASE[m]] + [f"exp7/{m}-rep{i}" for i in (1, 2, 3)]:
        sec[d] = {(u["facets"]["suite"], u["facets"]["task_dir"], u["facets"]["file"], u["facets"]["attack_dir"]): u["outcomes"]["security"] is True for u in rows if u["dir"] == d}
    per = {d: sum(s[c] for c in att) for d, s in sec.items()}
    agree = sum(len({sec[d][c] for d in sec}) == 1 for c in att)
    out["reps"][f"agree|{m}"] = {"cells": len(att), "asr_per_run": per, "all_four_agree": agree}
# slack IT5 in cap/noegress dirs
out["slack_it5_capdirs"] = dict(C.Counter(f"{u['dir']}|sec={u['outcomes']['security']}" for u in rows if u["facets"]["suite"] == "slack" and u["facets"]["file"] == "injection_task_5" and any(s in u["dir"] for s in ("-capA3", "-capA4", "-noegress"))))
json.dump(out, open(sys.argv[1], "w"), indent=1, sort_keys=True)
print("ok", out["members"], out["distinct_sha"], out["extra_copies"])
