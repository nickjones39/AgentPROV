import sys, json
sys.path.insert(0, sys.argv[1])
import common
for lab, o in common.logs():
    if lab.endswith("gpt-4o-2024-05-13-glitch/slack/user_task_3/none/none.json"):
        out = []
        for m in o["messages"]:
            ct = m.get("content")
            t = "".join(p.get("content") or "" for p in ct) if isinstance(ct, list) else (ct or "")
            out.append({"role": m["role"], "text_len": len(t), "calls": [c.get("function") for c in m.get("tool_calls") or []], "denied": isinstance(m.get("error"), str) and m["error"].startswith("DENIED")})
        print(json.dumps(out)); print(o.get("utility"))
