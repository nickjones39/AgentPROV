"""L1-04 trajectory-identical groups (l1_families fingerprint, CC-01) split by the arms they span, within and across
parts; restricted to groups whose members share suite/user task/injection task ('same-cell' = the census notion of a
content repeat across arms). Counts only. Usage: uv run python -I .../dup.py OUT.json"""
import json, os, sys
from collections import Counter, defaultdict
W = os.path.expanduser("~/.agentprov/migration-work/precheck/dca-agentdojo")
g = defaultdict(list)
for part in ("v1", "drift"):
    for l in open(f"{W}/l1-units-{part}.jsonl"):
        u = json.loads(l); f = u["facets"]; g[u["fp"]].append((f["model_dir"], f["suite"], f["task_dir"], f["file"]))
def cls(mds):
    s = sorted(set(mds))
    if len(s) == 1: return "same_arm"
    if all(m.startswith("camel/") for m in s) and len({m.rsplit("/", 1)[0] for m in s}) == 1: return "camel_vs_camel_secpol"
    if all("qwen36_27b_ollama" in m and m.startswith("dca_direct/") for m in s): return "qwen36_direct_vs_dca"
    return "other:" + "|".join(sorted({m.split("/")[0] + "/" + m.split("/")[1][:28] for m in s}))
R = Counter(); same = Counter()
for fp, us in g.items():
    if len(us) < 2: continue
    c = cls([u[0] for u in us]); R[f"groups|{c[:5] if c.startswith('other') else c}"] += 1; R[f"repeats|{c[:5] if c.startswith('other') else c}"] += len(us) - 1
    cells = Counter(u[1:] for u in us)
    sc = sum(n - 1 for n in cells.values() if n > 1); same[c if not c.startswith("other") else "other"] += sc
    if c.startswith("other"): R[c] += len(us) - 1
out = {"by_class": dict(sorted(R.items())), "same_cell_repeats": dict(same), "groups": sum(1 for v in g.values() if len(v) > 1)}
json.dump(out, open(sys.argv[1], "w"), indent=1, sort_keys=True); print(json.dumps(out, sort_keys=True))
