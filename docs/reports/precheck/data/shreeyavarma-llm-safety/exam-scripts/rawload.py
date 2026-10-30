"""Load the 672 selected logs of the pin through agentprov.ingest (strict); yields (label, obj). No values printed."""
import json, os, sys
from pathlib import Path
REPO = Path(os.environ['PRECHECK_REPO'])
sys.path.insert(0, str(REPO / 'tools' / 'precheck'))
import l1_scan  # noqa
from agentprov.ingest.loaders import strict_json_loads
BARE = Path.home() / '.agentprov/staging/10c/shreeyavarma/llm_safety.git'
COMMIT = '78d22e4a3daa5e76c77b75076c30ceb1faab22c1'
UNITS = Path.home() / '.agentprov/migration-work/precheck/shreeyavarma-llm-safety/l1-units-head.jsonl'
def load():
    rows = {json.loads(l)['label']: json.loads(l) for l in open(UNITS)}
    src = l1_scan.GitSource(BARE, COMMIT)
    ents = {e.label: e for e in src.entries()}
    rd = l1_scan.GitBlobReader(str(BARE))
    for label in sorted(rows):
        e = ents[label]
        data = rd.read(e.sha1)
        yield label, rows[label], strict_json_loads(data)
