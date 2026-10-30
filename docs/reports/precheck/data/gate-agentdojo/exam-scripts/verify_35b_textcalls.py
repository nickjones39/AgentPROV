"""35b non-empty-final logs without tool calls: markup counts only. Usage: uv run python -I v2.py <units> <bare> <commit>"""
import json, os, sys, hashlib, subprocess
from collections import Counter
from agentprov.ingest.loaders import strict_json_loads
U, B, C = sys.argv[1], os.path.expanduser(sys.argv[2]), sys.argv[3]
ENV = {k: v for k, v in os.environ.items() if k in ("PATH","TMPDIR","HOME")} | {"GIT_NO_LAZY_FETCH":"1","GIT_ALLOW_PROTOCOL":"file","GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":os.devnull}
H = ["-c", f"core.hooksPath={os.devnull}", "-c", "protocol.allow=never", "-c", "protocol.file.allow=always"]
c = Counter()
for ln in open(U):
    r = json.loads(ln); pd = r["facets"].get("pipeline_dir", "")
    if "qwen3-6-35b-a3b" not in pd or "null_final" in r["flags"]: continue
    raw = subprocess.run(["git",*H,"-C",B,"cat-file","blob",f"{C}:{r['label']}"],capture_output=True,env=ENV,check=True).stdout
    assert hashlib.sha256(raw).hexdigest()==r["sha256"]
    x = strict_json_loads(raw); ms = x.get("messages") or []
    a = [m for m in ms if m.get("role")=="assistant"]
    t = " ".join((b.get("content") or b.get("text") or "") if isinstance(b,dict) else str(b) for m in a for b in (m.get("content") or []) if not isinstance(m.get("content"),str)) + " ".join(m["content"] for m in a if isinstance(m.get("content"),str))
    c["logs"]+=1; c[f"assistant_turns={len(a)}"]+=1
    for mk in ("<tool_call>", "<function", "\"name\"", "<think>", "</think>"):
        c["has:"+mk]+= mk in t
print(json.dumps(dict(c)))
