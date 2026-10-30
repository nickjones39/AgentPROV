"""credleak-p15b: the tool call(s) with an empty tool name: cell label, run index, sampled or not. Labels only.
Usage (worktree root): python -I emptyname.py <exam-scripts dir>"""
import sys, json
sys.path.insert(0, sys.argv[1]); from rawlib import cells
S = set(json.load(open("docs/reports/precheck/data/credleak-p15b/l2-sample-head.json"))["labels"])
for l, d in cells():
    for i, r in enumerate(d["runs"]):
        for t in r["turns"]:
            for c in t.get("toolCalls") or []:
                if c.get("tool") in ("", None, "-", "0", "nan"): print(json.dumps(dict(label=l, run=i, sampled=l in S, name=repr(c.get("tool")))))
