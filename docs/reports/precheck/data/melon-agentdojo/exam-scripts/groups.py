import json, sys
from collections import Counter, defaultdict
units, popf = sys.argv[1], sys.argv[2]
rows = {r["label"]: r for r in json.load(open(popf))["rows"]}
g = defaultdict(list)
for l in open(units):
    u = json.loads(l); g[u["fp"]].append(u["label"])
groups = [v for v in g.values() if len(v) > 1]
c = Counter()
for v in groups:
    rs = [rows[l] for l in v]
    for key, name in (("model", "span_model"), ("defence", "span_defence"), ("attack", "span_attack"), ("task", "span_task")):
        if len({r[key] for r in rs}) > 1: c[name] += 1
    if len({(r["utility"], r["security"]) for r in rs}) > 1: c["mixed_outcome"] += 1
    if any(r["counts"].get("stop_en") or r["counts"].get("sanitize_tool_msgs") for r in rs): c["any_intervention"] += 1
    if len({r["model"] for r in rs}) > 1: c["cross_model_msgs_" + "/".join(map(str, sorted({r["n_msgs"] for r in rs})))] += 1
print("groups", len(groups), "units", sum(map(len, groups)), dict(c))
