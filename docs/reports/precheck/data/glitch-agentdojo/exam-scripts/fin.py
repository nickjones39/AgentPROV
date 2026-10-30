import sys, json
from collections import Counter
sys.path.insert(0, sys.argv[1])
import common
c = Counter()
for lab, o in common.logs():
    msgs = o.get("messages") or []
    asst = [m for m in msgs if m.get("role") == "assistant"]
    last = msgs[-1] if msgs else {}
    def empty(m):
        ct = m.get("content")
        if ct is None: return "none"
        if isinstance(ct, list):
            t = "".join((p.get("content") or "") for p in ct if isinstance(p, dict) and p.get("type") == "text")
            return "empty_list" if not ct else ("empty_text" if not t.strip() else "")
        return "empty_str" if not str(ct).strip() else ""
    c[f"last_role={last.get('role')}"] += 1
    if last.get("role") == "assistant" and not last.get("tool_calls"):
        e = empty(last)
        if e: c[f"final_no_call_{e}"] += 1
    for m in asst:
        e = empty(m)
        if e and not m.get("tool_calls"): c[f"any_assistant_no_call_{e}"] += 1
        if e and m.get("tool_calls"): c[f"assistant_with_call_{e}"] += 1
print(json.dumps(dict(sorted(c.items())), indent=1))
