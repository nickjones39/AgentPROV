"""Quick look at a scanner output file (counts only): ``python exam2_peek.py OUT.jsonl [prefix ...]``."""

import json
import sys
from collections import Counter

c: Counter = Counter()
h: Counter = Counter()
errors = 0
n = 0
for line in open(sys.argv[1], encoding="utf-8"):
    d = json.loads(line)
    n += 1
    if "error" in d:
        errors += 1
        if errors < 5:
            print("ERROR", d["ex"], d["error"])
    c.update(d.get("c", {}))
    h.update(d.get("hits", {}))
prefixes = tuple(sys.argv[2:]) or None
print("executions", n, "errors", errors)
for k, v in sorted(c.items()):
    if prefixes is None and k.startswith(("p09deg", "a01k", "a01t")):
        continue
    if prefixes is None or k.startswith(prefixes):
        print(k, v)
print("--- hits")
for k, v in h.most_common(200):
    if prefixes is None or k.startswith(prefixes):
        print(k, v)
