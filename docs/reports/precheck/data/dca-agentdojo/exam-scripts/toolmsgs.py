"""Per arm: logs with zero tool messages, with zero proposed tool calls, and the tool-message functions seen in CaMeL arms
(function names only, benchmark tool names), to qualify the #161 count where the record cannot show a payment. Counts only.
Usage (repo root): uv run python -I docs/reports/precheck/data/dca-agentdojo/exam-scripts/toolmsgs.py OUT.json"""
import json, os, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zipread import Z
W = os.path.expanduser("~/.agentprov/migration-work/precheck/dca-agentdojo")
z = Z(verify=False); arm = defaultdict(Counter); fn = defaultdict(Counter)
for part in ("v1", "drift"):
    for l in open(f"{W}/l1-units-{part}.jsonl"):
        u = json.loads(l); md = u["facets"]["model_dir"]; x = z.json(u["label"]); ms = x.get("messages") or x.get("conversations") or []
        t = [m for m in ms if m.get("role") == "tool"]; p = [tc for m in ms if m.get("role") == "assistant" for tc in (m.get("tool_calls") or [])]
        a = arm[md]; a["n"] += 1; a["zero_tool_msgs"] += not t; a["zero_proposed_calls"] += not p
        if md.startswith("camel/"):
            for m in t: fn[md][(m.get("tool_call") or {}).get("function")] += 1
out = {"arms": {k: dict(v) for k, v in sorted(arm.items())}, "camel_tool_functions_top": {k: dict(v.most_common(6)) for k, v in sorted(fn.items())}}
json.dump(out, open(sys.argv[1], "w"), indent=1, sort_keys=True); print(json.dumps(out, sort_keys=True))
