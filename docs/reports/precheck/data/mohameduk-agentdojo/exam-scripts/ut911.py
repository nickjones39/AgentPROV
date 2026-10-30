"""Travel user_task_9 / user_task_11 (checks need the accented restaurant name): utility and the form of the accent in
the final assistant text, fork arms vs upstream arms in the same tree. Counts only."""
import sys, os, json, re, glob
from collections import Counter, defaultdict
sys.path.insert(0, 'src'); sys.path.insert(0, 'tools/precheck')
from agentprov.ingest.loaders import strict_json_loads
root = os.path.expanduser('~/.agentprov/staging/10c/mohameduk/agentdojo-3f9d69a1ea96b75e8695653ceee8c3ff088db9b3')
MOJ = 'CafÃ©'; OK = 'Café'
def text(c):
    if isinstance(c, str): return c
    if isinstance(c, list): return ' '.join(str(b.get('content') or b.get('text') or '') for b in c if isinstance(b, dict))
    return ''
out = {}
for d_ in ['gemini-2.5-flash', 'gemini-2.5-flash-ubag', 'gemini-2.5-flash-ubag_behavioral', 'gpt-4o-mini-2024-07-18-ubag', 'gpt-4o-mini-2024-07-18-ubag_behavioral', 'gpt-4o-mini-2024-07-18', 'gpt-4o-2024-05-13', 'gemini-2.0-flash-001']:
    for ut in ('user_task_9', 'user_task_11'):
        c = Counter()
        for p in glob.glob(f'{root}/runs/{d_}/travel/{ut}/*/*.json'):
            d = strict_json_loads(open(p, 'rb').read())
            last = next((m for m in reversed(d['messages']) if m.get('role') == 'assistant'), {})
            t = text(last.get('content'))
            c['n'] += 1; c['utility'] += bool(d.get('utility'))
            c['final_moji'] += MOJ in t; c['final_proper'] += (OK in t)
        out[f'{d_}|{ut}'] = dict(c)
        print(d_, ut, dict(c))
json.dump(out, open(sys.argv[1], 'w'), indent=1, sort_keys=True)
