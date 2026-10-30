"""credleak-p15b: for identical-trajectory groups spanning several cells, do members also share turn timestamps and
durationMs (the same run deposited twice) or differ (independent identical re-runs)? Counts only.
Usage: python -I dupts.py <exam-scripts dir>"""
import sys, os, json, collections
sys.path.insert(0, sys.argv[1]); from rawlib import cells
fp = collections.defaultdict(list)
for line in open(os.path.expanduser("~/.agentprov/migration-work/precheck/_fp/credleak-p15b.head.jsonl")):
    x = json.loads(line); fp[x["fp"]].append((x["label"], x["unit"]))
want = {u for g in fp.values() if len({l for l, _ in g}) > 1 for u in g}
sig = {}
for l, d in cells():
    for i, r in enumerate(d["runs"]):
        if (l, f"/runs/{i}") in want: sig[(l, f"/runs/{i}")] = (tuple(t["timestamp"] for t in r["turns"]), r.get("durationMs"))
c = collections.Counter()
for g in fp.values():
    if len({l for l, _ in g}) < 2: continue
    by = collections.Counter(sig[u] for u in g)
    c["groups"] += 1; c["runs"] += len(g); c["runs_sharing_ts_with_another"] += sum(v for v in by.values() if v > 1)
print(json.dumps(dict(c)))
