"""OS-2 on the L2 sample (scratch j2): AER judgements vs raw L1 outcomes per execution; issue codes by directory kind;
identity of autoconfirm / repN directories; model ids. Counts and labels' directory facets only.
usage: python3 -I os2.py <scratch corpus> <l1-units.jsonl> <out.json>"""
import collections as C, json, os, sys
D = os.path.expanduser(sys.argv[1]); rows = C.defaultdict(list)
for r in map(json.loads, open(os.path.expanduser(sys.argv[2]))): rows[r["sha256"]].append(r)
o = C.defaultdict(C.Counter)
for line in open(os.path.join(D, "executions.jsonl")):
    e = json.loads(line); rs = rows[e["raw"][0]["sha256"].split(":")[1]]; r = rs[0]
    pds = sorted({x["facets"]["pipeline_dir"] for x in rs})
    recs = [json.loads(l) for l in open(os.path.join(D, e["paths"]["aer"]))]
    js = {x["name"]: x["value"] for x in recs if x.get("k") == "judgement"}
    for m in ("utility", "security"):
        o["os2"]["compared"] += 1; o["os2"]["differ"] += r["outcomes"][m] != js.get(m)
    for c in e["issues"]:
        if c not in ("map.accounting_unverifiable", "map.earlier_attempts_unobservable"):
            o["issues_by_dir"][f"{c}|{'+'.join(pds)}|{r['facets']['task_kind']}"] += 1
    ctx = [x for x in recs if x.get("k") in ("execution", "context", "header")]
    for x in recs:
        if x.get("k") == "execution":
            for key in ("model", "defence", "harness", "settings", "condition"):
                if key in x: o[f"exec_{key}"][f"{'+'.join(pds)} -> {json.dumps(x[key])[:80]}"] += 1
out = {k: dict(v) for k, v in o.items()}
json.dump(out, open(os.path.expanduser(sys.argv[3]), "w"), indent=1, sort_keys=True); print(json.dumps(out, sort_keys=True)[:4000])
