"""OS-2: mapped AER judgements vs raw L1 outcomes on the sampled labels; decisions vs raw refusals; issue labels."""
import sys, os, json
from collections import Counter, defaultdict
sys.path.insert(0, 'tools/analysis2'); sys.path.insert(0, 'src')
from exam2_lib import wilson
from agentprov.ingest.loaders import strict_json_loads
W = os.path.expanduser('~/.agentprov/migration-work/precheck/mohameduk-agentdojo')
C = f'{W}/l2-head-j2.partial'
root = os.path.expanduser('~/.agentprov/staging/10c/mohameduk/agentdojo-3f9d69a1ea96b75e8695653ceee8c3ff088db9b3')
l1 = {json.loads(l)['sha256']: json.loads(l) for l in open(f'{W}/l1-units-head.jsonl')}
diff = Counter(); arms = defaultdict(Counter); dec = Counter(); issues_by_label = defaultdict(list)
defence_actor = Counter(); model_names = Counter(); n = 0; unexec = Counter(); empty_final = Counter()
raw_ref = Counter()
for line in open(f'{C}/executions.jsonl'):
    ix = json.loads(line)
    sha = ix['raw'][0]['sha256'].split(':', 1)[1]
    r = l1[sha]; f = r['facets']; lab = r['label']; n += 1
    recs = [json.loads(x) for x in open(f"{C}/{ix['paths']['aer']}")]
    j = {x['name']: x.get('value') for x in recs if x.get('k') == 'judgement'}
    for name in ('utility', 'security'):
        if j.get(name) != r['outcomes'][name]: diff[name] += 1
    key = f"{f['pipeline_dir']}|{f['attack_dir']}"
    a = arms[key]; a['n'] += 1; a['uti'] += bool(j.get('utility')); a['sec'] += bool(j.get('security'))
    a2 = arms[f"{key}|{f['suite']}"]; a2['n'] += 1; a2['uti'] += bool(j.get('utility')); a2['sec'] += bool(j.get('security'))
    for x in recs:
        if x.get('k') == 'decision': dec[(f['pipeline_dir'], x.get('verdict'), x.get('reason'), x.get('ev'))] += 1
        if x.get('k') == 'actor' and x.get('kind') == 'defense': defence_actor[(f['pipeline_dir'], x.get('name'))] += 1
        if x.get('k') == 'actor' and x.get('kind') == 'llm_agent': model_names[(f['pipeline_dir'], json.dumps(x.get('model'), sort_keys=True)[:80])] += 1
    if not any(x.get('k') == 'actor' and x.get('kind') == 'defense' for x in recs): defence_actor[(f['pipeline_dir'], '<no defence actor>')] += 1
    for code in ix.get('issues', []):
        if code not in ('map.accounting_unverifiable', 'map.earlier_attempts_unobservable'): issues_by_label[code].append(lab)
    if 'null_final' in r['flags']: empty_final['sampled_null_final'] += 1
    d = strict_json_loads(open(os.path.join(root, lab), 'rb').read())
    for m in d['messages']:
        e = m.get('error')
        if isinstance(e, str) and e.startswith('ubag-blocked'): raw_ref[(f['pipeline_dir'], e)] += 1
out = {'n': n, 'judgement_value_differences': dict(diff),
       'arms': {k: dict(v, sec_wilson95=[round(x*100, 2) for x in wilson(v['sec'], v['n'])], uti_wilson95=[round(x*100, 2) for x in wilson(v['uti'], v['n'])]) for k, v in sorted(arms.items())},
       'decisions': {'|'.join(map(str, k)): v for k, v in sorted(dec.items(), key=str)},
       'raw_refusals_in_sample': {'|'.join(k): v for k, v in sorted(raw_ref.items())},
       'defence_actor': {'|'.join(k): v for k, v in sorted(defence_actor.items())},
       'model_actor': {'|'.join(k): v for k, v in sorted(model_names.items())},
       'issue_labels': dict(issues_by_label), 'null_final_sampled': dict(empty_final)}
json.dump(out, open(sys.argv[1], 'w'), indent=1, sort_keys=True)
print(json.dumps(out, indent=1, sort_keys=True))
