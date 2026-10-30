"""H20: traces with U+FFFD or mojibake (the l1_scan _MOJIBAKE pattern) in any string, by split; counts only.
usage: uv run python -I fffd.py <staging-root> <out.json>
"""
import collections, json, os, sys
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *[".."] * 6))
sys.path.insert(0, os.path.join(REPO, "tools", "precheck"))
from l1_scan import _MOJIBAKE  # noqa: E402
from agentprov.ingest.jsonstream import open_json_stream  # noqa: E402
from agentprov.ingest.limits import IngestLimits, MIB  # noqa: E402
root, outp = os.path.expanduser(sys.argv[1]), sys.argv[2]
LIM = IngestLimits().replace(max_json_element_bytes=64 * MIB, max_jsonl_line_bytes=64 * MIB)
C = collections.Counter(); N = collections.Counter()
def strs(v):
    if isinstance(v, dict):
        for x in v.values(): yield from strs(x)
    elif isinstance(v, list):
        for x in v: yield from strs(x)
    elif isinstance(v, str): yield v
for sp in ("main", "mitigation", "live_guard_defense", "browser_replication"):
    for f in sorted(os.listdir(os.path.join(root, sp))):
        with open(os.path.join(root, sp, f), "rb") as fh:
            for it in open_json_stream(fh, LIM, arrays=("/traces",)):
                N[sp] += 1; ff = mj = False
                for s in strs(it.value):
                    ff = ff or "�" in s; mj = mj or bool(_MOJIBAKE.search(s))
                C[f"{sp}|fffd"] += ff; C[f"{sp}|mojibake"] += mj
out = {"traces": dict(N), "with": dict(C)}
json.dump(out, open(outp, "w"), indent=1); print(out)
