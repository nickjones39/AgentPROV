"""H6: emulate the positional echo check (mapper._link) over the population; for conflicts, test the by_id collapse
(tool messages of one batch repeating one result). Labels only (paths in the public repo), counts."""
import sys, os, json
from collections import Counter, defaultdict
sys.path.insert(0, 'src')
from agentprov.ingest.loaders import strict_json_loads
W = os.path.expanduser('~/.agentprov/migration-work/precheck/mohameduk-agentdojo')
root = os.path.expanduser('~/.agentprov/staging/10c/mohameduk/agentdojo-3f9d69a1ea96b75e8695653ceee8c3ff088db9b3')
lex = lambda v: json.dumps(v, sort_keys=True)
res = defaultdict(list); summary = Counter()
for l in open(f'{W}/l1-units-head.jsonl'):
    r = json.loads(l); lab = r['label']; f = r['facets']
    d = strict_json_loads(open(os.path.join(root, lab), 'rb').read()); msgs = d['messages']
    conflicts = 0; repeated = 0; dup_tcid = 0
    for i, m in enumerate(msgs):
        calls = m.get('tool_calls') or []
        if m.get('role') != 'assistant' or not calls: continue
        results = []; j = i + 1
        while j < len(msgs) and msgs[j].get('role') == 'tool': results.append(msgs[j]); j += 1
        ids = [c.get('id') for c in calls]
        unique = all(isinstance(x, str) and x for x in ids) and len(set(ids)) == len(ids)
        tc = [x.get('tool_call_id') for x in results]
        if unique and all(t in ids for t in tc) and len(set(map(str, tc))) == len(tc): continue
        bc = 0
        for p, x in enumerate(results):
            if p >= len(calls): continue
            e = x.get('tool_call') or {}
            if not (e.get('function') == calls[p].get('function') and lex(e.get('args')) == lex(calls[p].get('args'))): bc += 1
        if bc:
            conflicts += bc
            contents = [lex(x.get('content')) + '|' + str(x.get('error')) for x in results]
            if len(set(contents)) < len(contents): repeated += 1
            echoes = [lex(x.get('tool_call')) for x in results]
            if len(set(echoes)) < len(echoes): dup_tcid += 1
    if conflicts:
        arm = f"{f['pipeline_dir']}|{f['attack_dir']}"
        res[arm].append({'label': lab, 'conflict_parts': conflicts, 'batches_with_repeated_result': repeated, 'batches_with_repeated_echo': dup_tcid})
        summary['logs'] += 1; summary['with_repeated_result'] += bool(repeated); summary['with_repeated_echo'] += bool(dup_tcid)
out = {'summary': dict(summary), 'by_arm': {k: len(v) for k, v in sorted(res.items())}, 'logs': dict(res)}
json.dump(out, open(sys.argv[1], 'w'), indent=1, sort_keys=True); print(json.dumps(out, indent=1, sort_keys=True))
