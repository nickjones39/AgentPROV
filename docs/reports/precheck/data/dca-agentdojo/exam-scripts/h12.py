"""H12 precursors at L1: logs with a negative or non-numeric top-level duration and logs with a tool call or tool message
whose function is the string 'none' (R-10j-4, R-10j-5), with arm and kind. Counts and facets only.
Usage (repo root): uv run python -I docs/reports/precheck/data/dca-agentdojo/exam-scripts/h12.py OUT.json"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zipread import Z
W = os.path.expanduser("~/.agentprov/migration-work/precheck/dca-agentdojo")
z = Z(verify=False); neg = []; none = []; missing = 0
for part in ("v1", "drift"):
    for l in open(f"{W}/l1-units-{part}.jsonl"):
        u = json.loads(l); f = u["facets"]; x = z.json(u["label"]); d = x.get("duration")
        cell = {"part": part, "arm": f["model_dir"], "suite": f["suite"], "task_dir": f["task_dir"], "file": f["file"]}
        if not isinstance(d, (int, float)): missing += 1
        elif d < 0: neg.append(cell)
        ms = x.get("messages") or x.get("conversations") or []
        if any(tc.get("function") == "none" for m in ms for tc in (m.get("tool_calls") or [])) or \
           any((m.get("tool_call") or {}).get("function") == "none" for m in ms): none.append(cell)
out = {"negative_duration": neg, "tool_named_none": none, "duration_missing_or_nonnumeric": missing}
json.dump(out, open(sys.argv[1], "w"), indent=1, sort_keys=True); print(json.dumps(out, sort_keys=True))
