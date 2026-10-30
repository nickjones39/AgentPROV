import sys, json
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import common
W = Path.home() / ".agentprov/migration-work/precheck/glitch-agentdojo"
s = json.load(open(str(Path.cwd()) + "/docs/reports/precheck/data/glitch-agentdojo/l2-sample-head.json"))
labs = set()
def walk(o):
    if isinstance(o, str) and o.startswith("17_agentdojo/"): labs.add(o)
    elif isinstance(o, dict): [walk(v) for v in o.values()]
    elif isinstance(o, list): [walk(v) for v in o]
walk(s)
tm = den = 0
for lab, o in common.logs():
    if lab in labs:
        for m in o.get("messages") or []:
            if m.get("role") == "tool":
                tm += 1
                if isinstance(m.get("error"), str) and m["error"].startswith("DENIED by the gateway: "): den += 1
print(json.dumps({"sample_labels": len(labs), "tool_messages": tm, "denied": den, "non_denied": tm - den}))
