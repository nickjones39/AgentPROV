"""glitch-agentdojo cross-corpus duplicates from the _fp files (counts and labels only)."""
import json, sys
from collections import defaultdict
from pathlib import Path
FP = Path.home() / ".agentprov/migration-work/precheck/_fp"
g = {}
for line in open(FP / "glitch-agentdojo.head.jsonl"):
    r = json.loads(line)
    g.setdefault(r["fp"], []).append(r)
gsha = {}
for rs in g.values():
    for r in rs: gsha[r["sha256"]] = r["label"]
hits = defaultdict(list); bhits = defaultdict(list)
for f in sorted(FP.glob("*.jsonl")):
    if f.name.startswith("glitch-agentdojo"): continue
    for line in open(f):
        r = json.loads(line)
        if r.get("fp") in g: hits[r["fp"]].append((r["corpus_id"], r["part"], r["label"]))
        if r.get("sha256") in gsha: bhits[r["sha256"]].append((r["corpus_id"], r["label"]))
out = {"byte_identical_cross_corpus": len(bhits), "trajectory_groups_cross_corpus": len(hits), "groups": []}
und = 0
for fp, others in hits.items():
    mine = [r["label"] for r in g[fp]]
    out["groups"].append({"fp12": fp[:12], "glitch": mine, "others": others})
for line in open(FP / "glitch-agentdojo.head.jsonl"):
    r = json.loads(line)
    if "/gpt-4o-2024-05-13/" in r["label"] and r["fp"] in hits: und += 1
out["undefended_gpt4o_units_in_cross_groups"] = und
print(json.dumps(out, indent=1))
