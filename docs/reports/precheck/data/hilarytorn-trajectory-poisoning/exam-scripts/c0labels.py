"""Labels of logs with C0 code points in tool-call string args (labels only); intersect with the L2 sample."""
import json, re, sys
from pathlib import Path
REPO = Path.cwd()  # run from the repository root
sys.path.insert(0, str(REPO / "tools" / "precheck"))
import l1_scan as s
from agentprov.ingest.limits import IngestLimits
bare, commit = sys.argv[1], sys.argv[2]
LOG = re.compile(r"^data/traces/.*\.json$")
src = s.GitSource(Path(bare), commit); rd = s.GitBlobReader(bare); L = IngestLimits()
c0 = lambda t: any((ord(ch) < 0x20 and ch not in "\n\t\r") or ch == "\x7f" for ch in t)
labs = []
for e in src.entries():
    if not LOG.match(e.label) or e.label.endswith("successful_injections.json") or e.disposition == "absent_blob": continue
    v = s.parse_json(rd.read(e.sha1), L).value
    if any(c0("".join(x for x in (tc.get("args") or {}).values() if isinstance(x, str))) for m in v.get("messages") or [] for tc in m.get("tool_calls") or []):
        labs.append(e.label)
samp = set(json.load(open(REPO / "docs/reports/precheck/data/hilarytorn-trajectory-poisoning/l2-sample-head.json"))["labels"])
print(len(labs), "in sample:", sorted(set(labs) & samp))
