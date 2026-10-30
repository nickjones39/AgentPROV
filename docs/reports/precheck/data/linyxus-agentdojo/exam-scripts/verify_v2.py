import sys, json, re
from collections import Counter
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, "tools/precheck")
import lx_lib
from l1_scan import SECRET_PATTERNS
GEN = SECRET_PATTERNS["generic-credential-assignment"]
E = lx_lib.entries(); R = lx_lib.Reader()
c = Counter(); shapes = Counter()
SP = "se3550000000054910000003"
for lab, e in E.items():
    if not lab.endswith(".json") or lab.count("/") < 5: continue
    raw = R.raw(e).decode("utf-8", "replace")
    for m in GEN.finditer(raw):
        s = m.group(0)
        c["gen_hits"] += 1
        c["gen_hit_has_alnum_after_sep"] += bool(re.search(r"[:=]\s*['\"]?[^'\"\s]*[A-Za-z0-9]", s))
    p = lab.split("/")
    if p[2] == "banking" and p[3] == "user_task_5" and p[4] != "none":
        x = json.loads(raw)
        if not x.get("messages") or "utility" not in x: continue
        c["ut5"] += 1
        if x.get("utility"):
            c["ut5_util"] += 1
            bt = x.get("backend_tool_traces") or []
            if x.get("tool_trace_source") == "backend_runtime":
                calls = bt
            else:
                calls = [tc for m in x["messages"] if m.get("role") == "assistant" for tc in (m.get("tool_calls") or [])]
            if c["shape"] == 0 and calls: shapes[str(sorted(calls[0].keys()))] += 1; c["shape"] = 1
            js = json.dumps(calls).lower()
            ok = ("send_money" in js or "schedule_transaction" in js) and SP in js.replace(" ", "")
            c["ut5_util_with_spotify_transfer"] += ok
print(dict(c), dict(shapes))
