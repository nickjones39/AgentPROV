"""L1-03 mojibake: by role, model, suite and matched sequence (escaped code points only)."""
import sys, os, json, re
from collections import Counter
sys.path.insert(0, 'src'); sys.path.insert(0, 'tools/precheck')
from agentprov.ingest.loaders import strict_json_loads
from l1_scan import _MOJIBAKE
W = os.path.expanduser('~/.agentprov/migration-work/precheck/mohameduk-agentdojo')
root = os.path.expanduser('~/.agentprov/staging/10c/mohameduk/agentdojo-3f9d69a1ea96b75e8695653ceee8c3ff088db9b3')
role = Counter(); seq = Counter(); arm = Counter(); suite = Counter(); proper = Counter()
def strings(v):
    if isinstance(v, str): yield v
    elif isinstance(v, dict):
        for x in v.values(): yield from strings(x)
    elif isinstance(v, list):
        for x in v: yield from strings(x)
for l in open(f'{W}/l1-units-head.jsonl'):
    r = json.loads(l); f = r['facets']
    d = strict_json_loads(open(os.path.join(root, r['label']), 'rb').read())
    hit = False
    for m in d['messages']:
        for s in strings(m):
            for mm in _MOJIBAKE.finditer(s):
                role[m.get('role')] += 1; seq[mm.group(0).encode('unicode_escape').decode()] += 1; hit = True
            if re.search('[éèüöäç]', s): proper[m.get('role')] += 1
    if hit: arm[f['pipeline_dir']] += 1; suite[f['suite']] += 1
print(json.dumps({'by_role_matches': role, 'sequences': seq.most_common(10), 'artefacts_by_dir': arm, 'artefacts_by_suite': suite, 'strings_with_proper_accents_by_role': proper}, indent=1))
