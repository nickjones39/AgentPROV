"""credleak-p15b exam: read the pinned v3 zip through agentprov.ingest (no extraction, strict parse). Counts only."""
import os, fnmatch
from agentprov.ingest.archives import open_zip, iter_zip_members
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.limits import IngestLimits
ZIP = os.path.expanduser("~/.agentprov/staging/10k/v3/p15b-run-data-v3-2026-09-13.zip")
INC = ["p15b-run-data/01-injection-map/**/*.json", "p15b-run-data/03-egress-axis/**/*.json", "p15b-run-data/04-hygiene/**/*.json"]
LOG = "p15b-run-data/03-egress-axis/external-canary-collector-log/"
def is_cell(label):
    return any(fnmatch.fnmatch(label, g.replace("**/", "*")) for g in INC) and not label.startswith(LOG)
def members(pred):
    """Yield (label, bytes) for members whose label satisfies pred."""
    lim = IngestLimits()
    with open(ZIP, "rb") as fp, open_zip(fp, lim, release=False) as z:
        for m in iter_zip_members(z, include=pred):
            if m.disposition == "selected" and m.label:
                yield m.label, b"".join(m.iter_chunks())
def cells():
    for label, data in members(is_cell):
        yield label, strict_json_loads(data)
