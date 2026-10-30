"""Print the key/type shape of the two pair files (no values)."""
import sys
sys.path.insert(0, sys.argv[1])
import gx_lib
E = gx_lib.entries(); R = gx_lib.Reader()
def shape(v, d=0):
    if isinstance(v, dict):
        ks = list(v)[:8]
        return {"dict": len(v), "keys_sample_types": {k if len(k) < 40 else k[:40]: shape(v[k], d+1) if d < 2 else type(v[k]).__name__ for k in ks}}
    if isinstance(v, list):
        return {"list": len(v), "first": shape(v[0], d+1) if v and d < 3 else None}
    return type(v).__name__
import json
for lab in ("results/pairs.json", "results/pairs-fork-v1.2.json"):
    print(lab, json.dumps(shape(R.load(E[lab])))[:1500])
