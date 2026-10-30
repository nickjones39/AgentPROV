"""credleak-p15b: population runs holding each named non-generic account digest, and how many hold no [withhold] rule
hit (so would be released at seal). Raw cells via rawlib; run JSON re-serialised for the scan. Counts and digests only.
Usage (worktree root): python -I accpop.py <exam-scripts dir>"""
import sys, re, json, hashlib, collections
sys.path.insert(0, "tools/precheck"); sys.path.insert(0, sys.argv[1])
from l1_scan import GENERIC_ACCOUNTS
from rawlib import cells
WH = [re.compile(p) for p in ("CANARY[^_]", "[^_/]CANARY", "AKIA[0-9A-Z]{16}", r"sk-[A-Za-z0-9_\-]{20,256}")]
NAMED = re.compile(r"/(?:home|Users)/([^/\s\"'<>\\]{1,64})/")
c = collections.Counter()
for l, d in cells():
    for r in d["runs"]:
        s = json.dumps(r, ensure_ascii=False); wh = any(rx.search(s) for rx in WH)
        acc = {hashlib.sha256(m.group(1).encode("utf-8","surrogatepass")).hexdigest()[:12] for m in NAMED.finditer(s) if m.group(1).lower() not in GENERIC_ACCOUNTS}
        for a in acc: c[f"{a}:runs"] += 1; c[f"{a}:released"] += not wh
print(json.dumps(dict(sorted(c.items()))))
