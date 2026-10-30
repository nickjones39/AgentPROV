"""H18 detail: cross-pair identical-trajectory groups with > 3 steps: pairs, domain/split, and how many steps carry
non-empty agent text (message/action strings), max agent-text length. Counts only.
Usage: python -I h18.py <runs_root> <l1-units.jsonl> <xpair-labels.json> <out.json>"""
import collections, json, sys
from agentprov.ingest.limits import MIB, IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.paths import open_evidence
runs, units, xp, out = sys.argv[1:5]; LIM = IngestLimits().replace(max_json_bytes=512 * MIB)
rows = {json.loads(l)["label"]: json.loads(l) for l in open(units)}
res = []
for g in json.load(open(xp))["xpair_labels"]:
    with open_evidence(runs, g[0], LIM) as h:
        d = strict_json_loads(h.read())
    t = d.get("trajectory") or []
    if len(t) <= 3:
        continue
    agent = [s for s in t if isinstance(s, dict) and s.get("role") == "agent"]
    txt = [len(str((s.get("metadata") or {}).get("message") or "")) for s in agent]
    fs = [rows[l]["facets"] for l in g]
    res.append({"pairs": sorted({f["framework"] + "/" + f["model"] for f in fs}), "domain": fs[0]["domain"],
                "split": fs[0]["split_label"], "units": len(g), "steps": len(t), "agent_steps": len(agent),
                "agent_steps_with_text": sum(x > 0 for x in txt), "max_agent_text_len": max(txt or [0]),
                "same_task_dir_suffix": len({"/".join(l.split("/")[2:-1]) for l in g}) == 1})
c = collections.Counter((tuple(r["pairs"]), r["domain"], r["split"], r["agent_steps_with_text"] > 0, r["same_task_dir_suffix"]) for r in res)
json.dump({"groups": res, "summary": {str(k): v for k, v in c.items()}}, open(out, "w"), indent=1)
[print(v, k) for k, v in c.items()]; print(max(r["max_agent_text_len"] for r in res))
