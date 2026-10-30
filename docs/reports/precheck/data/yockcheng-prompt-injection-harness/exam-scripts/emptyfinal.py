"""Final assistant message empty (content null, or all text blocks empty) without tool_calls; empty assistant turns
anywhere (E2 a03 definition); files with >= 1 tool call. Counts and labels only."""
import sys, json
from collections import Counter
from pathlib import Path
REPO = Path(sys.argv[1]); sys.path.insert(0, str(REPO / "tools" / "precheck"))
import l1_scan as s
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.limits import IngestLimits
bare = Path.home() / ".agentprov/staging/10c/yockcheng/prompt-injection-harness.git"
src = s.GitSource(bare, "5f9137ff352c5e843a94cbe20a7f31aa6e2c8fc6")
rows = {json.loads(l)["label"]: json.loads(l) for l in open(Path.home() / ".agentprov/migration-work/precheck/yockcheng-prompt-injection-harness/l1-units-head.jsonl")}
rd = s.GitBlobReader(str(bare)); c = Counter(); labs = []
def empty(m):
    if m.get("tool_calls"): return False
    cc = m.get("content")
    if cc is None: return "null"
    if isinstance(cc, str): return "str" if not cc.strip() else False
    if isinstance(cc, list): return "blocks" if all(not (b.get("content") or b.get("text") or "").strip() for b in cc if isinstance(b, dict)) else False
    return False
for e in src.entries():
    if e.label not in rows: continue
    o = strict_json_loads(rd.read(e.sha1), IngestLimits()); ms = o.get("messages") or []
    a = [m for m in ms if m.get("role") == "assistant"]
    if any(m.get("tool_calls") for m in ms): c["files_with_calls"] += 1
    if a:
        f = empty(a[-1]); 
        if f: c[f"final_empty_{f}"] += 1; labs.append(e.label)
        n = sum(1 for m in a if empty(m)); c["empty_turns"] += n; c["files_with_empty_turn"] += n > 0
    if ms and ms[-1].get("role") != "assistant": c[f"last_role_{ms[-1].get('role')}"] += 1
print(json.dumps(dict(c), indent=1)); print(json.dumps(labs[:10], indent=0))
