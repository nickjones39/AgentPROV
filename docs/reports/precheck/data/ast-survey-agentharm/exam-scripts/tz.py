# ruff: noqa  (precheck examiner script for ast-survey-agentharm, committed as run; read-only analysis)
import json, re, sys
from collections import Counter
from pathlib import Path
from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
C = Path(sys.argv[1]).expanduser(); c = Counter()
for line in (C / "raw/origins.jsonl").read_text().splitlines():
    r = json.loads(line)
    if r.get("origin", {}).get("kind") != "git": continue
    sha = r["sha256"].split(":", 1)[1]
    p = next((C / "raw/objects" / sha[:2]).glob(sha + "*"))
    with p.open("rb") as fp, open_zip(fp, IngestLimits(), release=False) as z:
        for m in iter_zip_members(z):
            if not (m.label or "").startswith("samples/"): continue
            s = strict_json_loads(z.read_member(m))
            for e in s.get("events") or []:
                for k in ("timestamp", "completed"):
                    t = e.get(k)
                    if isinstance(t, str):
                        mm = re.search(r"(Z|[+-]\d\d:\d\d)$", t); c[f"{k}:{mm.group(1) if mm else 'none'}"] += 1
            for k in ("started_at", "completed_at"):
                mm = re.search(r"(Z|[+-]\d\d:\d\d)$", s.get(k) or ""); c[f"{k}:{mm.group(1) if mm else 'none'}"] += 1
print(dict(c))
