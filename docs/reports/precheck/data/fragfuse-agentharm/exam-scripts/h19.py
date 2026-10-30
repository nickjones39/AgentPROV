# ruff: noqa  (precheck examiner script for fragfuse-agentharm; H-19: eval-set listings vs the pin tree; labels and counts only)
"""Usage: python -I h19.py <bare git dir> <commit>   (git run with GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file)"""
import json, os, subprocess, sys
from agentprov.ingest.loaders import strict_json_loads

env = {**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file"}
g = lambda *a: subprocess.run(["git", "--git-dir", sys.argv[1], *a], env=env, check=True, capture_output=True).stdout
tree = [l.split("\t", 1) for l in g("ls-tree", "-r", sys.argv[2]).decode().splitlines()]
paths = {p for _, p in tree}
out = {}
for meta, p in tree:
    if p.endswith("logs.json") and "logs_archive" in p:
        obj = strict_json_loads(g("cat-file", "blob", meta.split()[2]))
        names = list(obj) if isinstance(obj, dict) else [x if isinstance(x, str) else (x or {}).get("name") for x in obj]
        base = p.rsplit("/", 1)[0]
        missing = [n for n in names if f"{base}/{n}" not in paths]
        out[p] = {"listed": len(names), "missing": len(missing), "missing_labels": missing[:10]}
print(json.dumps(out, indent=1, sort_keys=True))
