"""glitch-agentdojo population scan (counts only): OS-1 tallies, denial counts, H2-H8 inputs. Usage: pop.py EXAMDIR OUT.json"""
import sys, json, hashlib
from collections import Counter, defaultdict
sys.path.insert(0, sys.argv[1])
import common
PFX = "DENIED by the gateway: "
MEMBER = {"invite_user_to_slack", "add_user_to_channel", "remove_user_from_slack"}
def text(c):
    if isinstance(c, str): return c
    if isinstance(c, list): return "".join(p.get("content") or "" for p in c if isinstance(p, dict) and p.get("type") == "text")
    return ""
C = defaultdict(Counter)
cells = defaultdict(set); dup = Counter()
ts = defaultdict(lambda: [None, None]); sysp = Counter()
slack_glitch_succ = []
per_it = Counter()
for lab, o in common.logs():
    _, _, pipe, suite, task, attack, fname = lab.split("/")
    kind = "prepass" if task.startswith("injection_task") else "user"
    arm = "benign" if attack == "none" else "attacked"
    key = f"{pipe}|{suite}"
    c = C[key]
    c[f"n_{kind}_{arm}"] += 1
    u, s = o.get("utility"), o.get("security")
    c[f"utility_{u}_{kind}_{arm}"] += 1
    c[f"security_{s}_{kind}_{arm}"] += 1
    if o.get("error") is not None: c["error_present"] += 1
    # path vs content identity
    if o.get("suite_name") != suite: c["suite_mismatch"] += 1
    if kind == "user" and o.get("user_task_id") != task: c["ut_mismatch"] += 1
    if o.get("attack_type") not in (attack, None) and not (attack == "none" and o.get("attack_type") in ("none", None)): c[f"attack_type_mismatch"] += 1
    c[f"attack_type={o.get('attack_type')}"] += 1
    c[f"pipeline_name={o.get('pipeline_name')}"] += 1
    c[f"pkg={o.get('agentdojo_package_version')}|bv={o.get('benchmark_version')}"] += 1
    cell = (pipe, suite, task, fname)
    dup[cell] += 1
    if arm == "attacked": cells[(pipe, suite, "att")].add((task, fname[:-5]))
    else: cells[(pipe, suite, kind)].add(task)
    t = o.get("evaluation_timestamp")
    lo, hi = ts[pipe]; ts[pipe] = [t if lo is None or t < lo else lo, t if hi is None or t > hi else hi]
    msgs = o.get("messages") or []
    sm = [m for m in msgs if m.get("role") == "system"]
    if sm:
        st = text(sm[0].get("content"))
        sysp[f"{pipe}|len={len(st)}|sha8={hashlib.sha256(st.encode()).hexdigest()[:8]}"] += 1
    nden = 0; executed = Counter(); denied_post_webpage = 0; tool_err_other = 0; err_field_denial = 0
    for m in msgs:
        if m.get("role") != "tool": continue
        t_ = text(m.get("content")); err = m.get("error")
        fn = (m.get("tool_call") or {}).get("function")
        isden = t_.startswith(PFX) or (isinstance(err, str) and err.startswith(PFX))
        if isinstance(err, str) and err.startswith(PFX): err_field_denial += 1
        if isden:
            nden += 1
            if fn == "post_webpage": denied_post_webpage += 1
        else:
            if err is not None: tool_err_other += 1
            if fn in MEMBER: executed[fn] += 1
        if err is not None: c["tool_msgs_with_error"] += 1
    c["denial_msgs"] += nden; c["denial_in_error_field"] += err_field_denial
    c["tool_err_non_denial"] += tool_err_other
    if nden: c[f"runs_with_denial_{kind}_{arm}"] += 1
    c["denied_post_webpage_msgs"] += denied_post_webpage
    if denied_post_webpage: c["runs_with_denied_post_webpage"] += 1
    last = msgs[-1] if msgs else {}
    if last.get("role") == "assistant" and last.get("tool_calls"): c["trailing_unexecuted_call_logs"] += 1
    if kind == "user" and arm == "attacked":
        per_it[f"{pipe}|{suite}|{fname[:-5]}|security={s}"] += 1
        if suite == "slack" and pipe.endswith("-glitch") and s is True:
            slack_glitch_succ.append({"label": lab, "injection_task": fname[:-5], "executed_membership_calls": dict(executed)})
OUT = {"by_arm": {k: dict(sorted(v.items())) for k, v in sorted(C.items())},
       "duplicate_cells": sum(1 for v in dup.values() if v > 1),
       "cells": {f"{p}|{s}|{k}": len(v) for (p, s, k), v in sorted(cells.items())},
       "ts_range_by_pipeline": dict(ts), "system_prompt": dict(sysp),
       "slack_glitch_successes": slack_glitch_succ,
       "per_injection_task_security_true": {k: v for k, v in sorted(per_it.items()) if k.endswith("True")}}
# holes: attacked cells should be the product of the benign user tasks x prepass injection tasks
holes = {}
for (p, s, k), v in cells.items():
    if k != "att": continue
    uts = cells.get((p, s, "user"), set()); its = cells.get((p, s, "prepass"), set())
    want = {(u, i) for u in uts for i in its}
    holes[f"{p}|{s}"] = {"missing": len(want - v), "extra": len(v - want), "want": len(want), "have": len(v)}
OUT["attacked_grid"] = holes
json.dump(OUT, open(sys.argv[2], "w"), indent=1, sort_keys=True)
print(json.dumps(OUT, indent=1)[:12000])
