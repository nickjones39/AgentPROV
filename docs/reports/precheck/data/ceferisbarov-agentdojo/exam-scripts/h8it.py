"""H8 follow-up: literal {optim_str} by injection task in original x gemini-2.5-pro banking/workspace, outcome by
literal; population attacked security rate (L2 R6 comparison). Counts only. Usage: as extra.py."""
import hashlib, json, os, subprocess, sys
from collections import Counter
from agentprov.adapters.runner.importer import git_blob_sha1
from agentprov.ingest.loaders import strict_json_loads
UNITS, BARE, COMMIT, OUT = sys.argv[1], os.path.expanduser(sys.argv[2]), sys.argv[3], sys.argv[4]
ENV = {k: v for k, v in os.environ.items() if k in ("PATH", "TMPDIR", "HOME")} | {
    "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
H = ["-c", f"core.hooksPath={os.devnull}", "-c", "protocol.allow=never", "-c", "protocol.file.allow=always"]
tree = {}
for rec in subprocess.run(["git", *H, "--git-dir", BARE, "ls-tree", "-r", "-z", COMMIT, "reruns/"], capture_output=True,
                          env=ENV, check=True).stdout.split(b"\0"):
    if rec:
        meta, path = rec.split(b"\t", 1); tree[path.decode()] = meta.split()[2].decode()
p = subprocess.Popen(["git", *H, "--git-dir", BARE, "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.DEVNULL, env=ENV)
res = Counter(); pop = Counter()
for ln in open(UNITS, encoding="utf-8"):
    row = json.loads(ln); f = row["facets"]
    if f["task_kind"] == "user" and row["outcomes"]["security"] is not None:
        pop["n"] += 1; pop["sec"] += bool(row["outcomes"]["security"])
    if not (f["arm"] == "original" and f["pipeline_dir"] == "google_gemini-2.5-pro" and f["task_kind"] == "user"
            and f["suite"] in ("banking", "workspace")):
        continue
    oid = tree[row["label"]]
    p.stdin.write(oid.encode() + b"\n"); p.stdin.flush()
    h = p.stdout.readline().split(); d = p.stdout.read(int(h[2])); p.stdout.read(1)
    assert git_blob_sha1(d) == oid and hashlib.sha256(d).hexdigest() == row["sha256"]
    x = strict_json_loads(d)
    lit = any("{optim_str}" in v for v in (x.get("injections") or {}).values() if isinstance(v, str))
    res[f"{f['suite']}|{f['file']}|literal={lit}"] += 1
    if x.get("security") is not None:
        res[f"{f['suite']}|literal={lit}|n"] += 1; res[f"{f['suite']}|literal={lit}|sec"] += bool(x.get("security"))
p.stdin.close(); p.wait()
out = {"original_gemini25pro": dict(sorted(res.items())), "population_attacked": dict(pop)}
json.dump(out, open(OUT, "w"), indent=1, sort_keys=True); print(json.dumps(out))
