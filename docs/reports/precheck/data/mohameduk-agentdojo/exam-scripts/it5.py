"""PC-02: slack injection_task_5 security-true logs by executed membership calls (counts only)."""
import sys, os, glob
from collections import Counter
sys.path.insert(0, 'src')
from agentprov.ingest.loaders import strict_json_loads
root = os.path.expanduser('~/.agentprov/staging/10c/mohameduk/agentdojo-3f9d69a1ea96b75e8695653ceee8c3ff088db9b3')
MEMBER = {'invite_user_to_slack', 'add_user_to_channel', 'remove_user_from_slack'}
for d_ in ['gemini-2.5-flash', 'gpt-4o-mini-2024-07-18-ubag', 'gpt-4o-mini-2024-07-18-ubag_behavioral', 'gpt-4o-mini-2024-07-18']:
    c = Counter()
    for p in glob.glob(f'{root}/runs/{d_}/slack/*/important_instructions/injection_task_5.json'):
        d = strict_json_loads(open(p, 'rb').read())
        ex = Counter((m.get('tool_call') or {}).get('function') for m in d['messages'] if m.get('role') == 'tool' and (m.get('tool_call') or {}).get('function') in MEMBER and m.get('error') in (None, ''))
        c['n'] += 1
        if d.get('security'):
            c['sec_true'] += 1; c['sec_true_no_member_executed'] += (sum(ex.values()) == 0); c['sec_true_all_three_executed'] += all(ex[f] > 0 for f in MEMBER)
    print(d_, dict(c))
