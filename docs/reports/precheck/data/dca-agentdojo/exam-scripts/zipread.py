"""Read members of the staged dca-agentdojo zip through agentprov.ingest (no extraction; bounded strict parse)."""
import hashlib, os
from agentprov.ingest.archives import open_zip, iter_zip_members
from agentprov.ingest.loaders import strict_json_loads
ZIP = os.path.expanduser("~/.agentprov/staging/10c/figshare-32657856/DCA_AgentDojo_artifact_v1_20260612.zip")
SHA = "ed500ca30d4420ed268d0798d4296296d6acfb0a2f82411c5a2f0ec5cbe40ce3"
class Z:
    def __init__(self, verify=True):
        if verify:
            h = hashlib.sha256()
            with open(ZIP, "rb") as f:
                for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
            assert h.hexdigest() == SHA, "pin mismatch"
        self.fp = open(ZIP, "rb"); self.z = open_zip(self.fp, release=False)
        self.m = {m.label: m for m in iter_zip_members(self.z) if m.label and m.disposition != "rejected"}
    def read(self, label): return self.z.read_member(self.m[label])
    def json(self, label): return strict_json_loads(self.read(label))
