"""H5 detail: where the string 'BLOCKED by security policy' occurs in the 215 `local` logs (pointer classes, counts only).
Usage: uv run python -I localdeny.py <l1-units-head.jsonl> <bare> <commit>"""
import json, os, subprocess, sys, hashlib
from collections import Counter
from agentprov.ingest.loaders import strict_json_loads
UNITS, BARE, COMMIT = sys.argv[1], os.path.expanduser(sys.argv[2]), sys.argv[3]
ENV = {k: v for k, v in os.environ.items() if k in ("PATH", "TMPDIR", "HOME")} | {"GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
H = ["-c", f"core.hooksPath={os.devnull}", "-c", "protocol.allow=never", "-c", "protocol.file.allow=always"]
rows = [json.loads(l) for l in open(UNITS)]
rows = [r for r in rows if r["facets"].get("pipeline_dir") == "local"]
c = Counter()
def walk(v, p):
    if isinstance(v, dict):
        for k, x in v.items(): yield from walk(x, p + "/" + k)
    elif isinstance(v, list):
        for x in v: yield from walk(x, p + "/*")
    elif isinstance(v, str) and "BLOCKED by security policy" in v:
        yield p
for r in rows:
    raw = subprocess.run(["git", *H, "-C", BARE, "cat-file", "blob", f"{COMMIT}:{r['label']}"], capture_output=True, env=ENV, check=True).stdout
    assert hashlib.sha256(raw).hexdigest() == r["sha256"]
    x = strict_json_loads(raw); hits = list(walk(x, ""))
    c["logs"] += 1; c["logs_with_hit"] += bool(hits)
    for p in hits: c["ptr:" + p] += 1
print(json.dumps(dict(c)))
