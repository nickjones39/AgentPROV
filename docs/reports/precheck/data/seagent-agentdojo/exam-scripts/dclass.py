"""Class-D PROV statements of the scratch corpus by bundle kind and rule (product reader ProvView); blocked-call tool
executions (`*BLOCKED_BY_SEAGENT`) in AER by status. Counts only."""
import collections, glob, json, os, sys
from agentprov.validate._provdoc import ProvView
C = os.path.expanduser('~/.agentprov/migration-work/precheck/seagent-agentdojo/l2-head-j2.partial')
d = collections.Counter(); te = collections.Counter()
for p in glob.glob(os.path.join(C, 'prov', '*', '*', '*.prov.json')):
    v = ProvView.parse(json.load(open(p)))
    for kind, sts in [('top', v.top)] + [(b.kind, b.statements) for b in v.bundles.values()]:
        for st in sts:
            if st.cls == 'D': d[f'{kind}|{st.rule}|{st.section}'] += 1
for p in glob.glob(os.path.join(C, 'aer', '*', '*.aer.jsonl')):
    for l in open(p):
        r = json.loads(l)
        if r.get('k') == 'tool_execution':
            te[f"blocked={str(r.get('name', '')).endswith('BLOCKED_BY_SEAGENT')}|status={r.get('status')}"] += 1
out = {'class_D_statements': dict(d.most_common()), 'tool_executions': dict(te)}
json.dump(out, open(sys.argv[1], 'w'), indent=1); print(json.dumps(out))
