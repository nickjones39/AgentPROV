"""L1-04 / H12: trajectory-identical groups (L1 fingerprint, CC-01) by composition. Counts only. Usage: python3 -I dups.py OUT.json"""
import json, os, sys, collections as C
rows = [json.loads(l) for l in open(os.path.expanduser("~/.agentprov/migration-work/precheck/ipi-defenses-agentdojo/l1-units-head.jsonl"))]
g = C.defaultdict(list)
for r in rows: g[r["fp"]].append(r)
groups = [v for v in g.values() if len(v) > 1]
comp = C.Counter(); out = {"groups": len(groups), "units_in_groups": sum(map(len, groups)), "distinct_sha": len({r["sha256"] for r in rows})}
cross_model = []; by_def = C.Counter(); cross_runset = C.Counter(); flags = C.Counter(); kinds = C.Counter(); byte = 0
for v in groups:
    models = {r["facets"]["h_pipeline"] for r in v}; defs = {r["facets"]["model_dir"].split("/")[1] for r in v}
    rsets = {r["facets"]["model_dir"].split("/")[0] for r in v}
    by_def["+".join(sorted(defs))] += 1
    if len(rsets) > 1: cross_runset["+".join(sorted(defs))] += 1
    kinds["+".join(sorted({r["facets"]["task_kind"] + ("/att" if r["facets"]["attack_dir"] != "none" else "") for r in v}))] += 1
    flags["null_final_all" if all("null_final" in r["flags"] for r in v) else ("null_final_some" if any("null_final" in r["flags"] for r in v) else "none")] += 1
    byte += len(v) - len({r["sha256"] for r in v})
    if len(models) > 1:
        cross_model.append({"size": len(v), "models": sorted(models), "defences": sorted(defs), "run_sets": sorted(rsets),
                            "tasks": sorted({r["facets"]["task_dir"] for r in v}),
                            "null_final": sum("null_final" in r["flags"] for r in v),
                            "utility_true": sum(r["outcomes"]["utility"] is True for r in v)})
out |= {"groups_by_defence_set": dict(by_def), "groups_spanning_run_sets_by_defence": dict(cross_runset),
        "groups_spanning_run_sets": sum(cross_runset.values()), "groups_by_kind": dict(kinds), "groups_by_null_final": dict(flags),
        "byte_copies_in_groups": byte, "cross_model_groups": cross_model}
json.dump(out, open(sys.argv[1], "w"), indent=1, sort_keys=True); print(json.dumps(out))
