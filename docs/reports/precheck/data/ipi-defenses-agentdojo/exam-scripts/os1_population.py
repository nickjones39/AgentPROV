"""OS-1 population tally per cell from the L1 rows (raw outcome fields, no mapping). Counts only."""
import json, sys, re, math, collections, os
rows = [json.loads(l) for l in open(os.path.expanduser(sys.argv[1]))]
def wilson(k, n, z=1.96):
    if n == 0: return None
    p = k/n; d = 1+z*z/n; c = (p+z*z/(2*n))/d; h = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [round(c-h, 4), round(c+h, 4)]
cells = collections.defaultdict(lambda: collections.Counter())
pairs = {}
flags = collections.defaultdict(collections.Counter)
prepass_goals = collections.defaultdict(set)
attack_goals = collections.defaultdict(set)
for r in rows:
    f = r["facets"]; cell = f["model_dir"]; o = r["outcomes"]
    c = cells[cell]
    for fl in r["flags"]: flags[cell][fl] += 1
    if f["task_kind"] == "prepass":
        c["pre_n"] += 1; c["pre_util"] += o["utility"] is True; c["pre_sec_true"] += o["security"] is True
        if o["utility"] is True: prepass_goals[cell].add(f["task_dir"])
    elif f["attack_dir"] == "none":
        c["bu_n"] += 1; c["bu_k"] += o["utility"] is True; c["benign_sec_true"] += o["security"] is True
    else:
        c["att_n"] += 1; c["asr_k"] += o["security"] is True; c["uua_k"] += o["utility"] is True
        m = re.search(r"/(user_task_\d+)/important_instructions/(injection_task_\d+)\.json$", r["label"])
        pairs[(cell, m.group(1), m.group(2))] = o["security"] is True
        if o["security"] is True: attack_goals[cell].add(m.group(2))
out = {}
for cell, c in sorted(cells.items()):
    out[cell] = dict(c, asr_wilson=wilson(c["asr_k"], c["att_n"]), bu_wilson=wilson(c["bu_k"], c["bu_n"]),
                     flags=dict(flags[cell]), prepass_util_goals=sorted(prepass_goals[cell]),
                     attack_success_goals=sorted(attack_goals[cell]))
# Table 11: mini_rerun, each defence vs none, paired (fixed = none success -> defence fail; caused = reverse)
t11 = {}
for d in ["spotlighting_with_delimiting", "transformers_pi_detector", "tool_filter", "repeat_user_prompt"]:
    for rs in ["mini_rerun", "agentdojo_banking_pdef"]:
        base = f"{rs}/none/gpt-5.4-mini-2026-03-17"; dc = f"{rs}/{d}/gpt-5.4-mini-2026-03-17"
        fx = cs = 0
        for (cell, u, i), s in pairs.items():
            if cell != base: continue
            s2 = pairs[(dc, u, i)]
            fx += s and not s2; cs += (not s) and s2
        t11[f"{rs}/{d}"] = {"fixed": fx, "caused": cs}
tot = {k: sum(c[k] for c in cells.values()) for k in ["att_n", "asr_k", "uua_k", "bu_n", "bu_k", "pre_n", "pre_util", "pre_sec_true", "benign_sec_true"]}
mini_uua = collections.Counter(); front_uua = 0
for cell, c in cells.items():
    rs, d, m = cell.split("/")
    if m.startswith("gpt-5.4-mini"): mini_uua[d] += c["uua_k"]
    else: front_uua += c["uua_k"]
json.dump({"cells": out, "table11": t11, "totals": tot, "mini_uua_pooled": dict(mini_uua), "frontier_run2_uua_sum": front_uua,
           "frontier_uua_plus_prepass_util": front_uua + tot["pre_util"]}, sys.stdout, indent=1, sort_keys=True)
