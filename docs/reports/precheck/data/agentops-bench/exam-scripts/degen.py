# ruff: noqa  (precheck examiner script for agentops-bench; read-only analysis)
"""L1-08 supplement: in-scope runs whose steps carry no reasoning text and no tool call (empty-answer runs), by agent.
Usage: uv run python -I degen.py <traces.tar.gz> <out.json>"""
import fnmatch, json, re, sys
from collections import Counter
from pathlib import Path
from agentprov.ingest.archives import open_archive
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
GLOBS = ("pilot_v1_seeded/*/*/adversarial/*_run*.json", "pilot_v1_seeded/*/*/clean/safety_*_run*.json", "pilot_v1_seeded/*/*/noisy/safety_*_run*.json")
c = Counter()
with open(Path(sys.argv[1]).expanduser(), "rb") as fp, open_archive(fp, IngestLimits(), release=False) as t:
    for m in t.iter_members(lambda l: "/._" not in l and any(fnmatch.fnmatchcase(l, g) for g in GLOBS), IngestLimits()):
        if m.disposition != "selected":
            continue
        r = strict_json_loads(t.read_member(m)); tr = r.get("trace") or {}; st = tr.get("steps") or []
        pm = m.label.split("/")[2]
        if st and not any((s.get("reasoning") or "").strip() or s.get("tool_calls") for s in st):
            fo = (tr.get("final_output") or "").strip()
            comp = (r.get("scores") or {}).get("completion")
            c[f"{pm}|final_output={'empty' if not fo else 'text'}|completion0={comp == 0}"] += 1
Path(sys.argv[2]).write_text(json.dumps(dict(sorted(c.items())), indent=1) + "\n"); print(dict(c))
