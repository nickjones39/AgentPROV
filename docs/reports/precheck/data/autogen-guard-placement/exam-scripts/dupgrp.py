# ruff: noqa  (precheck examiner script for autogen-guard-placement, committed as run; read-only analysis)
"""H-17: describe trajectory-identical groups (L1 fingerprint definition) that span probes or entries. Counts and labels only.
Usage: python -I dupgrp.py <zip> <out.json>"""
import hashlib, json, sys
from collections import Counter, defaultdict
from pathlib import Path
from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
g = defaultdict(list)
probes = {}
with Path(sys.argv[1]).expanduser().open("rb") as fp, open_zip(fp, IngestLimits(), release=False) as z:
    ms = list(iter_zip_members(z))
    for m in ms:
        if m.label.endswith("probes/probes.jsonl"):
            for l in z.read_member(m).splitlines():
                p = strict_json_loads(l); probes[p["id"]] = p.get("label")
    for m in ms:
        if not m.label.endswith("runs.jsonl"):
            continue
        for i, l in enumerate(z.read_member(m).splitlines()):
            r = strict_json_loads(l)
            if "run_id" not in r:
                continue
            steps = [[x.get("type"), x.get("source"), x.get("text"), (x.get("raw") or {}).get("content")] for x in r["messages"]]
            fp_ = hashlib.sha256(json.dumps(steps, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            g[fp_].append({"label": m.label.split("results/")[1] + f"#line:{i}", "probe": r.get("probe_id"), "entry": r.get("entry"),
                           "probe_label": probes.get(r.get("probe_id")), "modes": r.get("modes"),
                           "shape": [f"{x.get('type')}/{x.get('source')}" for x in r["messages"]],
                           "text_sha8": [hashlib.sha256(str(x.get("text")).encode()).hexdigest()[:8] for x in r["messages"]]})
out = []
for k, v in g.items():
    if len(v) > 1 and len({(x["probe"], x["entry"]) for x in v}) > 1:
        out.append({"size": len(v), "fp12": k[:12], "probes": len({x["probe"] for x in v}), "entries": dict(Counter(x["entry"] for x in v)),
                    "probe_labels": dict(Counter(str(x["probe_label"]) for x in v)), "shapes": dict(Counter(" > ".join(x["shape"]) for x in v)),
                    "modes": dict(Counter(json.dumps(x["modes"], sort_keys=True) for x in v)), "labels": [x["label"] for x in v],
                    "distinct_user_text_sha8": len({x["text_sha8"][0] for x in v})})
sizes = Counter(len({(x["probe"], x["entry"]) for x in v}) for v in g.values() if len(v) > 1)
Path(sys.argv[2]).write_text(json.dumps({"cross_groups": out, "groups_by_distinct_probe_entry": dict(sizes)}, indent=1) + "\n")
