"""OS-2 mapping check on the L2 sample: AER judgements vs raw L1 outcomes per label; decision records vs tool_execution.
usage: uv run python -I os2.py <scratch corpus> <l1-units.jsonl> <out.json>"""
import collections, json, os, sys
C = os.path.expanduser(sys.argv[1]); l1 = {r["sha256"]: r for r in map(json.loads, open(os.path.expanduser(sys.argv[2])))}
diff = collections.Counter(); dec = collections.Counter(); te = collections.Counter(); deckeys = set(); den_kind = collections.Counter()
for line in open(os.path.join(C, "executions.jsonl")):
    e = json.loads(line); row = l1[e["raw"][0]["sha256"].split(":")[1]]
    recs = [json.loads(l) for l in open(os.path.join(C, e["paths"]["aer"]))]
    js = {r["name"]: r["value"] for r in recs if r.get("k") == "judgement"}
    for m in ("utility", "security"):
        diff["compared"] += 1; diff["differ"] += row["outcomes"][m] != js.get(m)
    execs = {r.get("call"): r.get("status") for r in recs if r.get("k") == "tool_execution"}
    for r in recs:
        if r.get("k") == "tool_execution": te[str(r.get("status"))] += 1
        if r.get("k") == "decision":
            deckeys |= set(r.keys()); dec[f"{r.get('kind') or r.get('decision')}|{r.get('rule')}"] += 1
            subj = r.get("subject") or r.get("call") or r.get("target")
            st = execs.get(subj) if isinstance(subj, str) else None
            dec[f"call_has_tool_execution:{st is not None}|status:{st}"] += 1
            den_kind[f"{row['facets']['model_dir']}|{row['facets']['task_kind']}"] += 1
out = dict(os2=dict(diff), decisions=dict(dec), decision_keys=sorted(deckeys), tool_execution_status=dict(te), decisions_by_dir_kind=dict(den_kind))
json.dump(out, open(os.path.expanduser(sys.argv[3]), "w"), indent=1, sort_keys=True); print(json.dumps(out, sort_keys=True))
