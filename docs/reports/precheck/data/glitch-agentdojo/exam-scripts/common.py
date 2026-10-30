"""Shared reader: the pinned Glitch bare clone through l1_scan's GitSource/GitBlobReader and agentprov.ingest strict_json_loads."""
import sys
from pathlib import Path
REPO = Path.cwd()  # run from the repository root
sys.path.insert(0, str(REPO / "tools/precheck"))
import l1_scan  # noqa: E402
from agentprov.ingest.limits import IngestLimits  # noqa: E402
from agentprov.ingest.loaders import strict_json_loads  # noqa: E402
BARE = Path.home() / ".agentprov/staging/10c/glitch/Glitch.git"
PIN = "713bb2961fa16980ca8085d372adb200a66cad71"
LIM = IngestLimits()

def logs():
    src = l1_scan.GitSource(BARE, PIN)
    rd = l1_scan.GitBlobReader(str(BARE))
    for e in src.entries():
        lab = e.label
        if not (lab.startswith("17_agentdojo/runs/") and lab.endswith(".json") and lab.count("/") == 6):
            continue
        data = rd.read(e.sha1)
        yield lab, strict_json_loads(data, LIM)
