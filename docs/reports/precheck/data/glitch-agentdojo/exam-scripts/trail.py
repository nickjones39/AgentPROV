import sys, json
sys.path.insert(0, sys.argv[1])
import common
for lab, o in common.logs():
    m = (o.get("messages") or [{}])[-1]
    if m.get("role") == "assistant" and m.get("tool_calls"):
        print(json.dumps({"label": lab, "trailing_calls": len(m["tool_calls"]), "utility": o.get("utility"), "security": o.get("security")}))
