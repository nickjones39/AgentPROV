"""A2-style error classes on a scratch corpus (counts only): tool_execution and model_call status, run error, decisions, empty finals."""
import json, glob, sys, collections
c = collections.Counter()
for p in glob.glob(f"{sys.argv[1]}/aer/*/*.aer.jsonl"):
    recs = [json.loads(l) for l in open(p)]
    ex = recs[0]
    c["executions"] += 1
    c["run_error_present"] += (ex.get("ext") or {}).get("agentdojo", {}).get("error") not in (None, "")
    for r in recs:
        if r["k"] == "tool_execution": c[f"tool_execution:status={r.get('status')}"] += 1
        elif r["k"] == "model_call": c[f"model_call:status={r.get('status')}"] += 1
        elif r["k"] == "decision": c[f"decision:verdict={r.get('verdict')}"] += 1
    seal = recs[-1]
    for i in seal.get("issues") or []: c[f"seal:{i.get('code')}"] += 1
print(json.dumps(dict(sorted(c.items()))))
