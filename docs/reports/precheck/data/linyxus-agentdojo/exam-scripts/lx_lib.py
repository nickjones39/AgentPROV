"""linyxus-agentdojo examiner helpers: pinned blobs through the precheck git reader + agentprov.ingest strict JSON."""
import sys
from pathlib import Path
REPO = Path.cwd()  # run from the repository root
sys.path.insert(0, str(REPO / "tools/precheck"))
sys.path.insert(0, str(REPO / "tools/analysis2"))
import l1_scan  # noqa: E402
from agentprov.ingest.loaders import strict_json_loads  # noqa: E402
BARE = Path.home() / ".agentprov/staging/10c/linyxus/agentdojo.git"
COMMIT = "698d7ff29cac4bb5dccb5ed2d06f5e8364547a97"
W = Path.home() / ".agentprov/migration-work/precheck/linyxus-agentdojo"

def entries():
    return {e.label: e for e in l1_scan.GitSource(BARE, COMMIT).entries()}

class Reader:
    def __init__(self):
        self.r = l1_scan.GitBlobReader(str(BARE))
    def load(self, entry):
        return strict_json_loads(self.r.read(entry.sha1))
    def raw(self, entry):
        return self.r.read(entry.sha1)
