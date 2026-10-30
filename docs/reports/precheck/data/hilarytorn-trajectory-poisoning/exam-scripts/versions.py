"""H6: counts of version fields, suite_name, pipeline_name, attack_type and system-prompt digest over the 990 logs."""
import collections, hashlib, json, re, sys
from pathlib import Path
REPO = Path.cwd()  # run from the repository root
sys.path.insert(0, str(REPO / "tools" / "precheck"))
import l1_scan as s
from agentprov.ingest.limits import IngestLimits
bare, commit = sys.argv[1], sys.argv[2]
LOG = re.compile(r"^data/traces/(?:e2e/[^/]+/)?[^/]+/[^/]+/[^/]+/[^/]+/[^/]+\.json$")
src = s.GitSource(Path(bare), commit); rd = s.GitBlobReader(bare); L = IngestLimits()
c = collections.Counter()
for e in src.entries():
    if not LOG.match(e.label) or e.disposition == "absent_blob": continue
    v = s.parse_json(rd.read(e.sha1), L).value
    for k in ("agentdojo_package_version", "benchmark_version", "suite_name", "pipeline_name", "error"):
        c[f"{k}={v.get(k)}"] += 1
    c["attack_type_labels"] += 0
    c[f"attack_type:{v.get('attack_type')}"] += 1
    m0 = (v.get("messages") or [{}])[0]
    cont = m0.get("content")
    txt = cont if isinstance(cont, str) else "".join(b.get("content", "") for b in cont or [] if isinstance(b, dict))
    c[f"sys_sha256_prefix={hashlib.sha256(txt.encode()).hexdigest()[:8]}|len={len(txt)}"] += 1
print(json.dumps({k: v for k, v in sorted(c.items()) if not k.startswith("attack_type:")}, indent=0))
print("distinct attack_type labels:", len([k for k in c if k.startswith("attack_type:")]))
