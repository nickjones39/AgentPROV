"""H7 refined (#188 crash condition): a refused post_webpage to URL U, no executed post_webpage to U, and an executed
get_webpage/download_file of U (so U is in web_requests but not web_content). URLs compared after the upstream
standardize_url rule (strip http:// / https://), by digest only."""
import sys, os, json
from collections import Counter
sys.path.insert(0, 'src')
from agentprov.ingest.loaders import strict_json_loads
W = os.path.expanduser('~/.agentprov/migration-work/precheck/mohameduk-agentdojo')
root = os.path.expanduser('~/.agentprov/staging/10c/mohameduk/agentdojo-3f9d69a1ea96b75e8695653ceee8c3ff088db9b3')
def std(u):
    u = str(u)
    for p in ('https://', 'http://'):
        if u.startswith(p): u = u[len(p):]
    return u
c = Counter()
for l in open(f'{W}/l1-units-head.jsonl'):
    r = json.loads(l); f = r['facets']
    if f['suite'] != 'slack' or not f['pipeline_dir'].endswith(('ubag', 'ubag_behavioral')): continue
    d = strict_json_loads(open(os.path.join(root, r['label']), 'rb').read())
    ref, posted, requested = set(), set(), set()
    for m in d['messages']:
        if m.get('role') != 'tool': continue
        tc = m.get('tool_call') or {}; fn = tc.get('function'); u = std((tc.get('args') or {}).get('url'))
        e = m.get('error'); ok = e in (None, '')
        if fn == 'post_webpage':
            (posted if ok else ref).add(u) if (ok or (isinstance(e, str) and e.startswith('ubag-blocked'))) else None
        if fn in ('get_webpage', 'download_file') and ok: requested.add(u)
    crash = (ref - posted) & requested
    if crash:
        c[f"{f['task_dir']}|{f['attack_dir']}|utility={d.get('utility')}"] += 1
print(json.dumps(dict(sorted(c.items())), indent=1), sum(c.values()))
json.dump({'crash_condition_logs': dict(c), 'total': sum(c.values())}, open(sys.argv[1], 'w'), indent=1, sort_keys=True)
