# ruff: noqa  (precheck examiner script for agentops-bench; read-only analysis)
"""L1-04 / H9: characterise identical-trajectory groups that span agents (L1 rows + raw through agentprov.ingest).
Usage: uv run python -I dupgrp.py <l1-units.jsonl> <traces.tar.gz> <out.json>"""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path
from agentprov.ingest.archives import open_archive
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

rows = [json.loads(l) for l in open(Path(sys.argv[1]).expanduser())]
g = defaultdict(list)
for r in rows:
    if r.get("fp"):
        g[r["fp"]].append(r)
multi = {k: v for k, v in g.items() if len(v) > 1}
xa = {k: v for k, v in multi.items() if len({r["facets"]["provider_model"] for r in v}) > 1}
xtask = {k: v for k, v in multi.items() if len({r["label"].rsplit("/", 1)[1].rsplit("_run", 1)[0] for r in v}) > 1}
labels = {r["label"] for v in xa.values() for r in v}
shape = {}
with open(Path(sys.argv[2]).expanduser(), "rb") as fp, open_archive(fp, IngestLimits(), release=False) as t:
    for m in t.iter_members(lambda l: l in labels, IngestLimits()):
        if m.disposition == "selected":
            tr = strict_json_loads(t.read_member(m)).get("trace") or {}
            st = tr.get("steps") or []
            shape[m.label] = (len(st), sum(1 for s in st if (s.get("reasoning") or "").strip()), sum(len(s.get("tool_calls") or []) for s in st))
c = Counter(); sz = Counter(); dom = Counter(); cond = Counter()
for v in xa.values():
    sz[len(v)] += 1
    dom["|".join(sorted({r["facets"]["domain"] for r in v}))] += 1
    cond["|".join(sorted({r["facets"]["condition"] for r in v}))] += 1
    for r in v:
        s = shape.get(r["label"])
        c[f"steps={s[0]},reasoning_steps={s[1]},calls={s[2]}"] += 1
out = {"groups": len(multi), "units_in_groups": sum(len(v) for v in multi.values()),
       "cross_agent_groups": len(xa), "cross_agent_units": len(labels), "cross_agent_sizes": dict(sz),
       "cross_agent_by_domain": dict(dom), "cross_agent_by_condition": dict(cond), "cross_agent_unit_shape": dict(c.most_common()),
       "cross_task_groups": len(xtask), "cross_task_units": sum(len(v) for v in xtask.values())}
Path(sys.argv[3]).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
print(json.dumps(out))
