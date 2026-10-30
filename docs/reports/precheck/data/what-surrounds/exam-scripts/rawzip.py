"""Read the pinned what-surrounds zip in memory through agentprov.ingest (no extraction); helpers only."""
import os, hashlib
from agentprov.ingest.archives import open_zip, iter_zip_members
from agentprov.ingest.loaders import strict_json_loads
ZIP = os.path.expanduser('~/.agentprov/staging/10m/zenodo_21944598/prompt-injection-study.zip')
PIN = '08e60afd5ba0c0c044afd005c015cbc539428255240f1ea2a555feb800079454'
def members():
    with open(ZIP, 'rb') as fp:
        assert hashlib.sha256(fp.read()).hexdigest() == PIN
        fp.seek(0)
        with open_zip(fp, release=False) as z:
            out = {}
            for m in iter_zip_members(z):
                if m.disposition == 'selected' and m.label:
                    out[m.label] = z.read_member(m)
            return out
def runs(mem):
    r = {}
    for lab, b in mem.items():
        p = lab.split('/')
        if len(p) == 3 and p[0] == 'runs_named':
            r.setdefault(p[1], {})[p[2]] = b
    return r
def js(b): return strict_json_loads(b)
