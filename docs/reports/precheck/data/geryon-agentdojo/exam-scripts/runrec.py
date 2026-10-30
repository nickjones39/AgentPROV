"""Run records (not selected by the profile): key names, benchmark_repo_commit values (40-hex only), per-pair/skipped
markers, and security/utility array lengths. Counts and commit ids only."""
import sys, json, re
from collections import Counter
sys.path.insert(0, sys.argv[1])
import gx_lib
E = gx_lib.entries(); R = gx_lib.Reader()
recs = [l for l in E if re.fullmatch(r"results/[^/]+/[a-z]+-[ABC]-r\d(-calibration)?\.json", l)]
print("run records", len(recs))
keys = Counter(); commits = Counter(); repos = Counter(); rows = []
HEX = re.compile(r"[0-9a-f]{7,40}")
for l in sorted(recs):
    v = R.load(E[l])
    if not isinstance(v, dict):
        print(l, type(v).__name__); continue
    keys.update(v.keys())
    def find(o, name):
        if isinstance(o, dict):
            for k, x in o.items():
                if k == name: yield x
                yield from find(x, name)
        elif isinstance(o, list):
            for x in o: yield from find(x, name)
    bc = [x for x in find(v, "benchmark_repo_commit")]
    for x in bc:
        commits[x if isinstance(x, str) and HEX.fullmatch(x) else f"<non-hex:{type(x).__name__}>"] += 1
    br = [x for x in find(v, "benchmark_repo")]
    for x in br:
        repos[x if isinstance(x, str) and x.startswith("https://github.com/") and len(x) < 80 else f"<{type(x).__name__}>"] += 1
    sk = list(find(v, "skipped_pairs")); pp = list(find(v, "per_pair"))
    rows.append((l.split("/", 1)[1], len(sk[0]) if sk and isinstance(sk[0], list) else (sk[0] if sk and isinstance(sk[0], (int, bool)) else None),
                 pp[0] if pp and isinstance(pp[0], bool) else None))
print("top-level keys", dict(keys))
print("benchmark_repo_commit", dict(commits)); print("benchmark_repo", dict(repos))
for r in rows: print(r)
