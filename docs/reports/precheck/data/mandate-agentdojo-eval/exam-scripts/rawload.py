import json, hashlib, sys
from pathlib import Path
from agentprov.ingest.loaders import strict_json_loads
STORE = Path("~/.agentprov/corpora/mandate-agentdojo-eval-p10.partial/raw").expanduser()
def load_all():
    out = {}
    for l in (STORE / "origins.jsonl").read_text().splitlines():
        o = json.loads(l); sha = o["sha256"].split(":")[1]; path = o["origin"]["path"]
        if not path.startswith("runs/"): continue
        b = (STORE / "objects" / sha[:2] / f"{sha}.json").read_bytes()
        assert hashlib.sha256(b).hexdigest() == sha
        out[path] = strict_json_loads(b)
    return out
