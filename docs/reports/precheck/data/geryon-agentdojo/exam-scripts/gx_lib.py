"""geryon-agentdojo examiner helpers: read pinned blobs through the precheck git reader + agentprov.ingest strict JSON."""
import sys
from pathlib import Path
REPO = Path.cwd()  # run from the repository root
sys.path.insert(0, str(REPO / "tools/precheck"))
sys.path.insert(0, str(REPO / "tools/analysis2"))
import l1_scan  # noqa: E402
from agentprov.ingest.loaders import strict_json_loads  # noqa: E402
BARE = Path.home() / ".agentprov/staging/10c/geryon/geryon.git"
COMMIT = "905aae02c4185454ffbdb64a8bae6a042f6d7047"

def entries():
    return {e.label: e for e in l1_scan.GitSource(BARE, COMMIT).entries()}

class Reader:
    def __init__(self):
        self.r = l1_scan.GitBlobReader(str(BARE))
    def load(self, entry):
        return strict_json_loads(self.r.read(entry.sha1))
