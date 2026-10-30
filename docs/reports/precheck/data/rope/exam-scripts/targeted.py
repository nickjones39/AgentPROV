"""Builds l2-targeted-head.json: labels of the stored rope-p10 executions with no security judgement (the 2 empty logs) or
with recorded security true and no present/ambiguous injection marker under agentdojo.suites@1 (read-only). Run from the
repository root: python3 docs/reports/precheck/data/rope/exam-scripts/targeted.py --print (counts only)."""
import json, collections, sys
from pathlib import Path
O = Path('~/.agentprov/corpora/rope-p10.partial').expanduser()
groups = collections.defaultdict(list)
for l in (O / 'executions.jsonl').read_bytes().splitlines():
    r = json.loads(l); lines = (O / r['paths']['aer']).read_bytes().splitlines()
    e = json.loads(lines[0]); path = e['artifacts'][0]['origin']['path']; att = e['task'].get('attack_id')
    if not att: continue
    rs = next((j['value'] for j in map(json.loads, (x for x in lines if b'"judgement"' in x))
               if j.get('k') == 'judgement' and j['name'] == 'security' and j.get('origin') == 'checker' and not j.get('revises')), None)
    if rs is None: groups['empty_logs'].append(path); continue
    if rs is not True: continue
    S = [json.loads(x) for x in (O / list(r['paths']['sem'].values())[0]).read_bytes().splitlines()]
    st = collections.Counter(a['value']['status'] for a in S if a.get('type') == 'injection_marker')
    if not st['present'] and not st['ambiguous']: groups[f'security_true_no_visible_marker_suites1:{att}'].append(path)
print({k: len(v) for k, v in sorted(groups.items())})
