"""H15 detail: claudesdk/claude-sonnet-4-5 files mentioning the sonnet-4 snapshot id, by exact normalised pointer, domain
and whether the mention sits in a tool-call argument, an agent message or the final response. Counts only.
Usage: python -I h15.py <runs_root> <l1-units.jsonl> <out.json>"""
import collections, json, re, sys
from agentprov.ingest.limits import MIB, IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.paths import open_evidence
runs, units, out = sys.argv[1:4]; LIM = IngestLimits().replace(max_json_bytes=512 * MIB); S = "claude-sonnet-4-20250514"
SELF = re.compile(r"(?i)\b(I am|I'm|my model|model (id|name)|running on|powered by)\b")
ptr = collections.Counter(); dom = collections.Counter(); selfish = collections.Counter()
def walk(o, p):
    if isinstance(o, dict):
        for k, v in o.items(): yield from walk(v, p + "/" + k)
    elif isinstance(o, list):
        for v in o: yield from walk(v, p + "/*")
    elif isinstance(o, str): yield p, o
for l in open(units):
    r = json.loads(l); f = r["facets"]
    if f["framework"] != "claudesdk" or f["model"] != "claude-sonnet-4-5" or "judge_only_unit" in r["flags"]:
        continue
    with open_evidence(runs, r["label"], LIM) as h: data = h.read()
    if data.startswith(b"version https://git-lfs"):
        selfish["lfs_pointer_skipped"] += 1; continue
    d = strict_json_loads(data)
    hit = set()
    for p, s in walk(d, ""):
        if S in s:
            hit.add(p)
            if not re.match(r"/trajectory/\*/(state|metadata/tool_params)", p) and SELF.search(s[max(0, s.find(S) - 120): s.find(S) + 40]):
                selfish["self_report_like_strings"] += 1
    if hit:
        dom[f["domain"]] += 1
        for p in hit: ptr[p] += 1
json.dump({"pointers": dict(ptr), "domains": dict(dom), "self_report": dict(selfish)}, open(out, "w"), indent=1)
print(dict(ptr), dict(dom), dict(selfish))
