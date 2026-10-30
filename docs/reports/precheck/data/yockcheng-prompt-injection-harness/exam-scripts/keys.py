"""Print the key structure (no values) of one selected log, read via the L1 scanner's git source."""
import sys, json
from pathlib import Path
REPO = Path(sys.argv[1])
sys.path.insert(0, str(REPO / "tools" / "precheck"))
import l1_scan as s
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.limits import IngestLimits
bare = Path.home() / ".agentprov/staging/10c/yockcheng/prompt-injection-harness.git"
src = s.GitSource(bare, "5f9137ff352c5e843a94cbe20a7f31aa6e2c8fc6")
ents = {e.label: e for e in src.entries()}
rd = s.GitBlobReader(str(bare))
lab = sys.argv[2]
e = ents[lab]
obj = strict_json_loads(rd.read(e.sha1), IngestLimits())
def shape(o, d=0):
    if isinstance(o, dict): return {k: shape(v, d+1) for k, v in o.items()} if d < 4 else "{...}"
    if isinstance(o, list): return [shape(o[0], d+1), f"len={len(o)}"] if o else []
    return type(o).__name__
print(json.dumps(shape(obj), indent=1)[:4000])
