"""L1-04 / H19: classify the identical-trajectory groups of the L1 fingerprint file (_fp/mcphunt.head.jsonl) by
document pair, env_type/task_id agreement and whether the members share collection_timestamp and the event timestamp
list (copied record) or not (re-run with the same transcript). Counts and labels only.
usage: uv run python -I dups.py <staging-root> <fp.jsonl> <out.json>
"""
import collections, hashlib, json, os, sys
from agentprov.ingest.jsonstream import open_json_stream
from agentprov.ingest.limits import IngestLimits, MIB
root, fpp, outp = os.path.expanduser(sys.argv[1]), os.path.expanduser(sys.argv[2]), sys.argv[3]
fp = {}
for line in open(fpp):
    r = json.loads(line); fp[f"{r['label']}#{r['unit']}"] = r["fp"]
groups = collections.defaultdict(list)
for k, v in fp.items(): groups[v].append(k)
dup = {g: ls for g, ls in groups.items() if g and len(ls) > 1}
need = {l for ls in dup.values() for l in ls}
LIM = IngestLimits().replace(max_json_element_bytes=64 * MIB, max_jsonl_line_bytes=64 * MIB)
info = {}
for lab in sorted({l.split("#")[0] for l in need}):
    with open(os.path.join(root, lab), "rb") as fh:
        for it in open_json_stream(fh, LIM, arrays=("/traces",)):
            k = f"{lab}#/traces/{it.index}"
            if k not in need: continue
            t = it.value
            ets = hashlib.sha256(json.dumps([e.get("timestamp") for e in t.get("events") or []]).encode()).hexdigest()[:12]
            info[k] = {"ct": t.get("collection_timestamp"), "ets": ets, "env": t.get("env_type"), "task": t.get("task_id"),
                       "mech": t.get("risk_mechanism"), "ml": t.get("mitigation_level"), "model": t.get("model"),
                       "risk": bool((t.get("labeling") or {}).get("any_risk")),
                       "ver": bool((t.get("completion_checks") or {}).get("artifact_verified")), "nev": len(t.get("events") or [])}
C = collections.Counter
out = {"groups": len(dup), "units": len(need), "by_docset": C(), "same_task": C(), "same_env": C(), "copied": C(),
       "label_disagree": C(), "env_sets": C(), "zero_event_groups": 0, "copied_by_docset": C(), "copied_env": C(), "units_cross_doc": 0}
for g, ls in dup.items():
    docs = tuple(sorted({l.split("#")[0] for l in ls}))
    out["by_docset"][" + ".join(docs)] += 1
    xs = [info[l] for l in ls]
    if len(docs) > 1: out["units_cross_doc"] += len(ls)
    out["same_task"][len({x["task"] for x in xs}) == 1] += 1
    out["same_env"][len({x["env"] for x in xs}) == 1] += 1
    out["env_sets"]["|".join(sorted({x["env"] for x in xs}))] += 1
    out["copied"]["same_ct_and_event_ts" if len({(x["ct"], x["ets"]) for x in xs}) == 1 else
                  ("same_event_ts_only" if len({x["ets"] for x in xs}) == 1 else "distinct_runs")] += 1
    out["label_disagree"]["outcome_differs" if len({(x["risk"], x["ver"]) for x in xs}) > 1 else "same_outcome"] += 1
    out["zero_event_groups"] += all(x["nev"] == 0 for x in xs)
    if len({(x["ct"], x["ets"]) for x in xs}) == 1:
        out["copied_units"] = out.get("copied_units", 0) + len(ls); out["copied_by_docset"][" + ".join(docs)] += 1
        out["copied_env"][xs[0]["env"]] += 1
for k in list(out):
    if isinstance(out[k], C): out[k] = dict(out[k].most_common(25))
json.dump(out, open(outp, "w"), indent=1, default=str); print(json.dumps(out, indent=0, default=str))
