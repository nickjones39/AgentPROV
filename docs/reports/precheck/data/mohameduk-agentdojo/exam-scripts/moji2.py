"""Compare mojibake vs proper accents in tool results: fork arms vs the upstream gpt-4o-mini copy in the same tree."""
import sys, os, json, re, glob
from collections import Counter
sys.path.insert(0, 'src'); sys.path.insert(0, 'tools/precheck')
from agentprov.ingest.loaders import strict_json_loads
from l1_scan import _MOJIBAKE
root = os.path.expanduser('~/.agentprov/staging/10c/mohameduk/agentdojo-3f9d69a1ea96b75e8695653ceee8c3ff088db9b3')
def strings(v):
    if isinstance(v, str): yield v
    elif isinstance(v, dict):
        for x in v.values(): yield from strings(x)
    elif isinstance(v, list):
        for x in v: yield from strings(x)
ACC = re.compile('[éö]')
for d_ in ['gpt-4o-mini-2024-07-18', 'gpt-4o-mini-2024-07-18-ubag', 'gemini-2.5-flash', 'gpt-4o-2024-05-13']:
    c = Counter()
    for suite in ('travel', 'slack'):
        for p in glob.glob(f'{root}/runs/{d_}/{suite}/*/none/none.json'):
            d = strict_json_loads(open(p, 'rb').read())
            for m in d['messages']:
                if m.get('role') != 'tool': continue
                for s in strings(m.get('content')):
                    c[f'{suite}:moji'] += len(_MOJIBAKE.findall(s)); c[f'{suite}:proper'] += len(ACC.findall(s))
    print(d_, dict(c))
