"""Attacked logs whose tool outputs never contain the injection marker (payload unread): labels and outcomes only."""
import json, re, sys
from pathlib import Path
REPO = Path.cwd()  # run from the repository root
sys.path.insert(0, str(REPO / "tools" / "precheck"))
import l1_scan as s
from agentprov.ingest.limits import IngestLimits
bare, commit = sys.argv[1], sys.argv[2]
src = s.GitSource(Path(bare), commit); rd = s.GitBlobReader(bare); L = IngestLimits()
samp = set(json.load(open(REPO / "docs/reports/precheck/data/hilarytorn-trajectory-poisoning/l2-sample-head.json"))["labels"])
for e in src.entries():
    if not re.match(r"^data/traces/.+/user_task_\d+/[^/]+/injection_task_\d\.json$", e.label) or e.disposition == "absent_blob": continue
    v = s.parse_json(rd.read(e.sha1), L).value
    texts = []
    for m in v["messages"]:
        if m["role"] == "tool":
            c = m.get("content")
            texts += [c] if isinstance(c, str) else [b.get("content", "") for b in c or [] if isinstance(b, dict)]
    if not any("<INFORMATION>" in t for t in texts if isinstance(t, str)):
        n_tool = sum(1 for m in v["messages"] if m["role"] == "tool")
        print(e.label, "security", v.get("security"), "utility", v.get("utility"), "tool_msgs", n_tool, "in_sample", e.label in samp)
