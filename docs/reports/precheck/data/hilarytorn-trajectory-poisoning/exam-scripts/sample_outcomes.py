"""Sample outcome sanity keyed by the arm directory (from /artifacts/0/origin/path, since the AER has no arm field): mapped
AER judgements vs the raw L1 outcome of the same labels, per arm, with Wilson 95% (tools/analysis2/exam2_lib.wilson).
Also the post-stratified sample rate (R6: 5 of 105 drawn per arm, so the plain sample rate is the arm's rate).

usage: python3 -I sample_outcomes.py <scratch corpus> <l1-units.jsonl> <out.json>
"""
import collections
import glob
import json
import sys

sys.path.insert(0, __import__("os").getcwd() + "/tools/analysis2")  # run from the repository root
from exam2_lib import wilson  # noqa: E402

root, units, out = sys.argv[1], sys.argv[2], sys.argv[3]
raw = {}
with open(units) as fh:
    for line in fh:
        r = json.loads(line)
        raw[r["label"]] = r
rows = []
for f in glob.glob(root + "/aer/*/*.aer.jsonl"):
    ex = None
    j = {}
    with open(f) as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("k") == "execution":
                ex = r
            elif r.get("k") == "judgement":
                j[r["name"]] = (r.get("value"), r.get("origin"))
    label = ex["artifacts"][0]["origin"]["path"]
    rows.append((label, ex, j))
cells = collections.defaultdict(lambda: collections.Counter())
mismatch = collections.Counter()
origins = collections.Counter()
for label, ex, j in rows:
    r = raw[label]
    arm = r["facets"]["arm"]
    kind = r["facets"]["task_kind"]
    for name in ("utility", "security"):
        v, origin = j.get(name, (None, None))
        origins[f"{name}|{kind}|{origin}"] += 1
        if v != r["outcomes"][name]:
            mismatch[f"{arm}|{name}"] += 1
    if kind == "user":
        c = cells[arm]
        c["n"] += 1
        c["sec_aer"] += 1 if j["security"][0] is True else 0
        c["sec_raw"] += 1 if r["outcomes"]["security"] is True else 0
        c["util_aer"] += 1 if j["utility"][0] is True else 0
    else:
        cells[arm + "|prepass"]["n"] += 1
        cells[arm + "|prepass"]["util_aer"] += 1 if j["utility"][0] is True else 0
table = {}
for arm, c in sorted(cells.items()):
    row = {"n": c["n"]}
    for k in ("sec_aer", "sec_raw", "util_aer"):
        if k in c or k == "util_aer":
            row[k] = {"k": c[k], "rate": round(c[k] / c["n"], 4), "wilson95": [round(x, 4) for x in wilson(c[k], c["n"])]}
    table[arm] = row
tot = collections.Counter()
for arm, c in cells.items():
    if "|prepass" not in arm:
        tot["n"] += c["n"]
        tot["sec"] += c["sec_aer"]
res = {"n_executions": len(rows), "arms": table, "mismatch_aer_vs_raw": dict(mismatch), "judgement_origins": dict(origins),
       "attacked_total": {"n": tot["n"], "k": tot["sec"], "wilson95": [round(x, 4) for x in wilson(tot["sec"], tot["n"])]}}
with open(out, "w") as fh:
    json.dump(res, fh, indent=1, sort_keys=True)
print(json.dumps(res, indent=1, sort_keys=True))
