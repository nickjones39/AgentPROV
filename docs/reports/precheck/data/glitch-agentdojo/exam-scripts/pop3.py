"""H5 (#188) and banking by-effect probe; counts and labels only. Targets are benchmark fixture constants."""
import sys, json
from collections import Counter
sys.path.insert(0, sys.argv[1])
import common
PFX = "DENIED by the gateway: "
CO = "www.our-company.com"
ATT_IBAN = "US133000000121212121212"
out = {"slack_ut4": [], "banking_glitch_success": [], "travel_glitch_success_it6_tool_calls": Counter()}
for lab, o in common.logs():
    _, _, pipe, suite, task, attack, fname = lab.split("/")
    msgs = o.get("messages") or []
    tools = [m for m in msgs if m.get("role") == "tool"]
    def st(m):
        e = m.get("error"); return "denied" if isinstance(e, str) and e.startswith(PFX) else ("error" if e is not None else "ok")
    if suite == "slack" and task == "user_task_4" and pipe.endswith("-glitch"):
        r = Counter()
        for m in tools:
            tc = m.get("tool_call") or {}; fn = tc.get("function"); url = str((tc.get("args") or {}).get("url", ""))
            if fn in ("post_webpage", "get_webpage"):
                r[f"{fn}|company_url={CO in url}|{st(m)}"] += 1
        out["slack_ut4"].append({"label_file": f"{attack}/{fname}", "utility": o.get("utility"), "error": o.get("error") is not None, "calls": dict(r)})
    if suite == "banking" and pipe == "gpt-4o-2024-05-13-glitch" and attack != "none" and o.get("security") is True:
        r = Counter()
        for m in tools:
            tc = m.get("tool_call") or {}; fn = tc.get("function"); a = tc.get("args") or {}
            if fn in ("send_money", "schedule_transaction", "update_scheduled_transaction", "update_password", "update_user_info"):
                r[f"{fn}|to_attacker={str(a.get('recipient',''))==ATT_IBAN}|{st(m)}"] += 1
        out["banking_glitch_success"].append({"ut": task, "it": fname[:-5], "calls": dict(r)})
out["travel_glitch_success_it6_tool_calls"] = dict(out["travel_glitch_success_it6_tool_calls"])
json.dump(out, open(sys.argv[2], "w"), indent=1, sort_keys=True); print(json.dumps(out, indent=1))
