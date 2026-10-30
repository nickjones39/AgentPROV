"""Follow-up counts: user tasks of the glitch successes; slack IT5 membership calls by target (Fred = IT5 target, a
benchmark fixture name) and execution status; denied post_webpage runs by user task. Counts and labels only."""
import sys, json
from collections import Counter
sys.path.insert(0, sys.argv[1])
import common
MEMBER = {"invite_user_to_slack", "add_user_to_channel", "remove_user_from_slack"}
PFX = "DENIED by the gateway: "
def text(c):
    if isinstance(c, list): return "".join(p.get("content") or "" for p in c if isinstance(p, dict) and p.get("type") == "text")
    return c if isinstance(c, str) else ""
succ = Counter(); slack = []; dpw = Counter(); dpw_util = Counter()
for lab, o in common.logs():
    _, _, pipe, suite, task, attack, fname = lab.split("/")
    if not pipe.endswith("-glitch") or attack == "none":
        if not (pipe.endswith("-glitch") and suite == "slack"): continue
    msgs = o.get("messages") or []
    if attack != "none" and o.get("security") is True:
        succ[f"{pipe}|{suite}|{task}|{fname[:-5]}"] += 1
    if suite == "slack":
        calls = {}
        for m in msgs:
            for tc in m.get("tool_calls") or []:
                calls[tc.get("id")] = tc
        rows = Counter(); denied_pw = False
        for m in msgs:
            if m.get("role") != "tool": continue
            fn = (m.get("tool_call") or {}).get("function"); err = m.get("error")
            if fn == "post_webpage" and isinstance(err, str) and err.startswith(PFX): denied_pw = True
            if fn in MEMBER:
                args = (m.get("tool_call") or {}).get("args") or {}
                fred = str(args.get("user", "")).strip().lower() == "fred"
                st = "denied" if isinstance(err, str) and err.startswith(PFX) else ("error" if err is not None else "ok")
                rows[f"{fn}|target_fred={fred}|{st}"] += 1
        if denied_pw:
            dpw[f"{task}|{attack}"] += 1
            dpw_util[f"utility={o.get('utility')}|error={o.get('error') is not None}"] += 1
        if attack != "none" and o.get("security") is True:
            slack.append({"user_task": task, "it": fname[:-5], "membership_tool_results": dict(rows)})
out = {"glitch_successes": dict(sorted(succ.items())), "slack_glitch_successes": slack,
       "slack_glitch_denied_post_webpage_runs_by_task": dict(sorted(dpw.items())), "denied_post_webpage_outcomes": dict(dpw_util)}
json.dump(out, open(sys.argv[2], "w"), indent=1, sort_keys=True); print(json.dumps(out, indent=1))
