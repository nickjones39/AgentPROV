"""L1-03 escape residues by message role and tree (counts only)."""
import sys, json, re
from collections import Counter
from pathlib import Path
REPO = Path(sys.argv[1]); sys.path.insert(0, str(REPO / "tools" / "precheck"))
import l1_scan as s
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.limits import IngestLimits
bare = Path.home() / ".agentprov/staging/10c/yockcheng/prompt-injection-harness.git"
src = s.GitSource(bare, "5f9137ff352c5e843a94cbe20a7f31aa6e2c8fc6")
rows = {json.loads(l)["label"]: json.loads(l) for l in open(Path.home() / ".agentprov/migration-work/precheck/yockcheng-prompt-injection-harness/l1-units-head.jsonl")}
rd = s.GitBlobReader(str(bare)); c = Counter(); files = Counter()
PAT = {"escaped_newline": re.compile(r"\\n"), "escaped_unicode": re.compile(r"\\u[0-9a-fA-F]{4}"), "escaped_quote": re.compile(r"\\\"")}
for e in src.entries():
    if e.label not in rows: continue
    o = strict_json_loads(rd.read(e.sha1), IngestLimits()); seen = set()
    for m in o.get("messages") or []:
        cc = m.get("content")
        for b in (cc if isinstance(cc, list) else []):
            t = b.get("content") if isinstance(b, dict) else None
            if isinstance(t, str):
                for k, p in PAT.items():
                    if p.search(t):
                        c[f"{k}|{m.get('role')}|{rows[e.label]['facets']['tree']}"] += 1; seen.add(f"{k}|{m.get('role')}")
    for k in seen: files[k] += 1
print(json.dumps({"strings": dict(sorted(c.items())), "files": dict(sorted(files.items()))}, indent=1))
