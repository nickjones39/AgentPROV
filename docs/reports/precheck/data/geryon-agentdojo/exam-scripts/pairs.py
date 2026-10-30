"""Count pair classes in results/pairs.json and pairs-fork-v1.2.json (counts only)."""
import sys, json
from collections import Counter
sys.path.insert(0, sys.argv[1])
import gx_lib
E = gx_lib.entries(); R = gx_lib.Reader()
for lab in ("results/pairs.json", "results/pairs-fork-v1.2.json"):
    P = R.load(E[lab]); c = Counter()
    for p in P:
        c[(p["suite"], p["within_policy"], p["within_policy_arguments"])] += 1
    print(lab, sorted(c.items()))
