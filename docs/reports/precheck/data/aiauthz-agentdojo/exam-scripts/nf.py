"""Null-final shape per model x kind: logs, logs with >=1 tool call, logs whose every assistant message has null/empty content.
usage: uv run python -I nf.py <l1-units.jsonl>"""
import collections, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rawread import tree, Reader
l1 = {r["label"]: r for r in map(json.loads, open(os.path.expanduser(sys.argv[1])))}
t = tree(); r = Reader(); c = collections.Counter()
for lab in sorted(p for p in t if p.startswith("experiments/agentdojo/runs/")):
    p = lab.split("/"); kind = "clean" if p[4].endswith("_clean") else ("prepass" if p[7].startswith("injection_task") else "attacked")
    k = f"{p[3]}|{kind}|nf={'null_final' in l1[lab]['flags']}"
    ms = r.json(t[lab])["messages"]; asst = [m for m in ms if m.get("role") == "assistant"]
    c[k + "|logs"] += 1
    c[k + "|with_calls"] += any(m.get("tool_calls") for m in asst)
    c[k + "|n_assistant_eq_1"] += len(asst) == 1
print(json.dumps(dict(sorted(c.items())), indent=0))
