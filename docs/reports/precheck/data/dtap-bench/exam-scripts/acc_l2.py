"""Which named-account digests (raw.json) reach the scratch AER/SEM/PROV files of the L2 sample; and per-file counts by
pointer class of the top raw accounts. Digests (16 hex, pattern-prefixed) and counts only.
Usage: python -I acc_l2.py <scratch corpus> <raw.json> <out.json>"""
import collections, hashlib, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../../../tools/precheck"))
from l1_scan import ACCOUNT_PATTERNS, GENERIC_ACCOUNTS  # noqa: E402
root, rawj, out = sys.argv[1:4]
raw = json.load(open(rawj))["named_accounts"]
hits = collections.defaultdict(lambda: collections.Counter())
for stage in ("aer", "sem", "prov"):
    for dp, _, fs in os.walk(os.path.join(root, stage)):
        for fn in fs:
            t = open(os.path.join(dp, fn), encoding="utf-8").read().replace("\\\\", "\\")
            seen = set()
            for name, rx in ACCOUNT_PATTERNS.items():
                for m in rx.finditer(t):
                    a = m.group(1)
                    if a.lower() in GENERIC_ACCOUNTS or (name == "users-dir" and a.lower() == "shared"):
                        continue
                    seen.add(name + ":" + hashlib.sha256(a.encode("utf-8", "surrogatepass")).hexdigest()[:16])
            for d in seen:
                hits[d][stage] += 1
res = {d: {"files_by_stage": dict(c), "raw_files": raw.get(d, {}).get("files"), "in_task_tree": raw.get(d, {}).get("in_task_tree"),
           "raw_classes": sorted(raw.get(d, {}).get("classes", {}))} for d, c in sorted(hits.items())}
json.dump(res, open(out, "w"), indent=1)
print(json.dumps({d[:14]: v for d, v in res.items()}))
