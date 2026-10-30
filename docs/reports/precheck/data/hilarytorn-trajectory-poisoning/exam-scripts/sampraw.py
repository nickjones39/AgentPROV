"""Raw message/tool-error counts for the 90 sampled labels (vs the scratch AER)."""
import collections, json, sys
from pathlib import Path
REPO = Path.cwd()  # run from the repository root
sys.path.insert(0, str(REPO / "tools" / "precheck"))
import l1_scan as s
from agentprov.ingest.limits import IngestLimits
bare, commit = sys.argv[1], sys.argv[2]
samp = set(json.load(open(REPO / "docs/reports/precheck/data/hilarytorn-trajectory-poisoning/l2-sample-head.json"))["labels"])
src = s.GitSource(Path(bare), commit); rd = s.GitBlobReader(bare); L = IngestLimits(); c = collections.Counter()
for e in src.entries():
    if e.label not in samp: continue
    v = s.parse_json(rd.read(e.sha1), L).value
    for m in v["messages"]:
        c["msg|" + m["role"]] += 1
        c["calls"] += len(m.get("tool_calls") or [])
        if m["role"] == "tool" and m.get("error") is not None: c["tool_errors"] += 1
print(dict(c))
