import hashlib, json, os, sys, collections
from agentprov.ingest.jsonstream import open_json_stream
from agentprov.ingest.limits import IngestLimits, MIB
root = os.path.expanduser(sys.argv[1]); LIM = IngestLimits().replace(max_json_element_bytes=64*MIB, max_jsonl_line_bytes=64*MIB)
H = lambda o: hashlib.sha256(json.dumps(o, sort_keys=True).encode()).hexdigest()[:16]
def it(lab):
    with open(os.path.join(root, lab), "rb") as fh:
        for x in open_json_stream(fh, LIM, arrays=("/traces",)): yield x.index, x.value
mains = {}
for f in sorted(os.listdir(os.path.join(root, "main"))):
    if not f.endswith(".json"): continue
    for i, t in it(f"main/{f}"):
        k = (t.get("collection_timestamp"), H([e.get("timestamp") for e in t.get("events") or []]))
        mains.setdefault(k, []).append((f, i, t))
out = {}
for f in sorted(os.listdir(os.path.join(root, "mitigation"))):
    if not f.endswith(".json"): continue
    c = collections.Counter(); diffk = collections.Counter()
    for i, t in it(f"mitigation/{f}"):
        c["n"] += 1
        k = (t.get("collection_timestamp"), H([e.get("timestamp") for e in t.get("events") or []]))
        m = mains.get(k)
        if not m: continue
        c["ct_ets_match"] += 1
        mf, mi, mt = m[0]
        c["msgs_equal"] += H(t.get("messages")) == H(mt.get("messages"))
        c["events_equal"] += H(t.get("events")) == H(mt.get("events"))
        c["same_index"] += mi == i
        c["multi_main"] += len(m) > 1
        for kk in set(t) | set(mt):
            if H(t.get(kk)) != H(mt.get(kk)): diffk[kk] += 1
    out[f] = {"counts": dict(c), "differing_top_keys": dict(diffk.most_common(12))}
print(json.dumps(out, indent=0))
