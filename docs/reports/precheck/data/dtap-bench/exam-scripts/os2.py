"""dtap-bench L2 mapping check: mapped AER judgements and identity of the sampled executions vs the raw L1 values of the
same labels, plus Wilson rates per pair x split on the sample. Counts only.
Usage: python -I os2.py <scratch corpus> <l1-units.jsonl> <out.json>"""
import collections, json, math, os, sys

root, units, out = sys.argv[1:4]
L1 = {json.loads(l)["label"]: json.loads(l) for l in open(units)}


def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(100 * (c - h) / d, 1), round(100 * (c + h) / d, 1)]


m = collections.Counter(); arms = collections.defaultdict(lambda: [0, 0]); origins = collections.Counter()
for line in open(os.path.join(root, "executions.jsonl")):
    ex = json.loads(line)
    recs = [json.loads(l) for l in open(os.path.join(root, ex["paths"]["aer"]))]
    head = recs[0]; lab = head["artifacts"][0]["origin"]["path"]; r = L1.get(lab)
    if r is None:
        m["label_not_in_l1"] += 1; continue
    f = r["facets"]; pf = head["ext"]["dtap"]["path_facets"]
    agent = next(x for x in recs if x.get("k") == "actor" and x.get("id") == "agent")
    m["framework_ok" if pf["framework"] == f["framework"] else "framework_mismatch"] += 1
    m["model_ok" if agent["model"]["requested"] == f["model"] else "model_mismatch"] += 1
    m["split_ok" if pf["split"] == f["split_label"] or (f["split_label"] == "benign" and pf["split"] == "benign") else "split_diff:" + str(pf["split"]) + "|" + f["split_label"]] += 1
    js = {x["name"]: x for x in recs if x.get("k") == "judgement"}
    for name in ("task_success", "attack_success"):
        raw = r["outcomes"].get(f"aux.{name}") if "judge_only_unit" not in r["flags"] else r["outcomes"].get(name)
        jj = js.get(name); val = jj.get("value") if jj else None
        origins[f"{name}:{jj.get('origin') if jj else 'absent'}"] += 1
        m[f"{name}:{'equal' if val == raw else 'differ'}"] += 1
    split = f["split_label"]; metric = "task_success" if split == "benign" else "attack_success"
    jj = js.get(metric)
    if jj and jj.get("value") is not None and jj.get("origin") != "harness_default":
        a = arms[f"{f['framework']}|{f['model']}|{split}"]; a[0] += int(jj["value"] is True); a[1] += 1
json.dump({"mapping": dict(m), "judgement_origins": dict(origins),
           "sample_rates": {k: {"k": v[0], "n": v[1], "rate": round(100 * v[0] / v[1], 1), "wilson95": wilson(*v)}
                            for k, v in sorted(arms.items())}}, open(out, "w"), indent=1)
print(json.dumps({"mapping": m, "origins": origins}, default=dict))
