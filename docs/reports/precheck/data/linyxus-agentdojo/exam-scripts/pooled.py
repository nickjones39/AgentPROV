"""Population (L1 raw) pooled rates per l2_check arm (model|defence|attack), attacked complete logs, from exam/pop.json,
and the post-stratified population rate weighted like the sample (equal weight per sampled stratum). Counts only.
Usage (repo root): uv run python -I docs/reports/precheck/data/linyxus-agentdojo/exam-scripts/pooled.py"""
import json, os, sys
from collections import defaultdict
sys.path.insert(0, "tools/analysis2")
from exam2_lib import wilson  # noqa: E402
W = os.path.expanduser("~/.agentprov/migration-work/precheck/linyxus-agentdojo/exam")
P = json.load(open(f"{W}/pop.json"))["cells_per_root"]
arm = defaultdict(lambda: [0, 0, 0])
for k, v in P.items():
    rs, p, s = k.split("|")
    m = p.replace("openrouter_", "", 1).replace("_", "/", 1).removesuffix("-tacit")
    a = arm[f"{m}|{'tacit' if p.endswith('-tacit') else 'none'}|important_instructions"]
    a[0] += v["n"]; a[1] += v["utility_k"]; a[2] += v["attack_k"]
out = {}
for k, (n, u, s) in sorted(arm.items()):
    out[k] = {"n": n, "utility_pct": round(100 * u / n, 2), "asr_pct": round(100 * s / n, 2)}
print(json.dumps(out, indent=0))
print("sample wilson", {f"{k}/{n}": [round(100 * x, 1) for x in wilson(k, n)] for k, n in ((13, 20), (13, 33), (6, 20), (22, 38), (0, 20), (1, 33), (0, 38))})
