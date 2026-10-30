"""L2 gate decisions: raw denial tool messages in the 300 sampled logs, by path class (counts only).
Usage: uv run python -I sampledeny.py <l1-units> <l2-sample.json> <bare> <commit>"""
import json, os, subprocess, sys, hashlib
from collections import Counter
from agentprov.ingest.loaders import strict_json_loads
U, S, BARE, COMMIT = sys.argv[1], sys.argv[2], os.path.expanduser(sys.argv[3]), sys.argv[4]
ENV = {k: v for k, v in os.environ.items() if k in ("PATH", "TMPDIR", "HOME")} | {"GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
H = ["-c", f"core.hooksPath={os.devnull}", "-c", "protocol.allow=never", "-c", "protocol.file.allow=always"]
samp = set(json.load(open(S))["labels"]); c = Counter()
for r in (json.loads(l) for l in open(U)):
    if r["label"] not in samp: continue
    raw = subprocess.run(["git", *H, "-C", BARE, "cat-file", "blob", f"{COMMIT}:{r['label']}"], capture_output=True, env=ENV, check=True).stdout
    assert hashlib.sha256(raw).hexdigest() == r["sha256"]
    x = strict_json_loads(raw)
    n = sum(1 for m in x.get("messages") or [] if m.get("role") == "tool" and isinstance(m.get("error"), str) and m["error"].startswith("BLOCKED by security policy"))
    k = "demo" if r["label"].startswith("results/demo/") else "run"
    c[f"{k}_denials"] += n; c[f"{k}_logs_with_denial"] += bool(n)
print(json.dumps(dict(c)))
