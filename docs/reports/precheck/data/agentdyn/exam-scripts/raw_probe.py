"""Targeted raw probe (strict ingest parse; counts only): H-03 and evaluation dates of the off-paper arms."""
import json, sys, collections, glob, os
from agentprov.ingest.loaders import strict_json_loads

ROOT = os.path.expanduser("~/Desktop/PhD/Labs/AgentPROV-upstream/agentdyn")
MAXB = 64 * 1024 * 1024

def load(path):
    with open(path, "rb") as fh:
        data = fh.read(MAXB + 1)
    assert len(data) <= MAXB
    return strict_json_loads(data)

out = {}
# H-03: github/user_task_2/important_instructions/injection_task_1 with security true; executed git_delete_repo?
h3 = collections.Counter(); h3_by_dir = {}
for p in sorted(glob.glob(f"{ROOT}/runs/*/github/user_task_2/important_instructions/injection_task_1.json")):
    v = load(p); d = p.split("/runs/")[1].split("/")[0]
    sec = v.get("security")
    executed = 0; requested = 0
    for m in v.get("messages") or ():
        if not isinstance(m, dict):
            continue
        if m.get("role") == "tool" and isinstance(m.get("tool_call"), dict) and m["tool_call"].get("function") == "git_delete_repo":
            executed += 1 if not m.get("error") else 0
        for c in m.get("tool_calls") or ():
            if isinstance(c, dict) and c.get("function") == "git_delete_repo":
                requested += 1
    variant = "c" if "build_constraints" in v else ("b" if "agentdojo_package_version" not in v else "a")
    key = f"{variant}|security={sec}|executed_delete={'yes' if executed else 'no'}|requested_delete={'yes' if requested else 'no'}"
    h3[key] += 1
out["H-03"] = dict(sorted(h3.items()))

# evaluation dates by directory and suite for the off-paper arms (part a only)
DIRS = sys.argv[2:]
dates = {}
for d in DIRS:
    c = collections.Counter()
    for p in glob.glob(f"{ROOT}/runs/{d}/*/user_task_*/*/*.json"):
        v = load(p)
        s = p.split(f"/runs/{d}/")[1].split("/")[0]
        ts = v.get("evaluation_timestamp")
        c[f"{s}|{str(ts)[:10]}"] += 1
    dates[d] = dict(sorted(c.items()))
out["evaluation_dates"] = dates
json.dump(out, open(sys.argv[1], "w"), indent=1)
print(json.dumps(out, indent=1))
